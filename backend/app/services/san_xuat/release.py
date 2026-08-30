"""Phát hành NGUYÊN TỬ + snapshot (spec §4).

Điểm neo của Giai đoạn 1: mỗi lần phát hành (từ MÀN XẾP LỊCH CŨ hoặc Xếp lịch 2) đóng băng một
gói phát hành = ảnh chụp routing/tổ/máy/định mức/khoán/vật tư của những LSX + bài ghép ĐANG được
thả xuống xưởng, cùng cạnh phụ thuộc chéo giữa chúng (bước ghép). Cả hai cửa gọi CHUNG `phat_hanh`
ở đây — "một lịch, hai cửa" (§4.1), không có đường vòng nào phát hành mà bỏ qua snapshot.

Phạm vi lát này (backbone): dựng gói/phiên bản/công việc/phụ thuộc + suy nhóm thành phẩm + đánh
KCS-cuối khi rõ ràng. `phat_hanh` KHÔNG commit (chủ giao dịch là service gọi nó — cùng một
transaction với thao tác đổi trạng thái LSX). CHƯA làm: phát hành-cập-nhật đẻ phiên bản mới (§4.3)
và thu-hồi gói (§4.3) — gặp gói đang hiệu lực thì trả lại gói cũ, không đẻ trùng.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import (
    PB_PHAT_HANH,
    SanXuatGoiPhatHanh,
    SanXuatPhienBan,
)
from ...repositories.document_sequence_repo import DocumentSequenceRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ..sequence_service import SequenceService
from .nhom import dam_bao_nhom
from .snapshot import (
    danh_dau_kcs_cuoi,
    dung_cong_viec,
    dung_diem_toa,
    dung_phu_thuoc,
)


def phat_hanh(
    db: Session,
    *,
    lsx_ids: set[int],
    bai_ghep_ids: set[int] | None = None,
    actor=None,
) -> SanXuatGoiPhatHanh:
    """Đóng băng một gói phát hành cho tập LSX + bài ghép đang được thả xuống. Idempotent ở mức
    gói: đã có gói hiệu lực trỏ tới nhóm này thì trả lại, không đẻ trùng."""
    bai_ghep_ids = set(bai_ghep_ids or set())
    lsx_ids = set(lsx_ids)
    repo = SanXuatRepository(db)

    da_co = repo.goi_hien_tai_cua(lsx_ids, bai_ghep_ids)
    if da_co is not None:
        return da_co

    seq = SequenceService(DocumentSequenceRepository(db))
    goi = SanXuatGoiPhatHanh(ma=seq.generate_code("san_xuat_goi"), version_hien_tai=1)
    repo.add(goi)
    repo.flush()
    repo.add(SanXuatPhienBan(
        goi_id=goi.id, so=1, loai=PB_PHAT_HANH,
        phat_hanh_by_id=getattr(actor, "id", None),
    ))
    repo.flush()

    nhom_by_lsx = dam_bao_nhom(repo, lsx_ids)

    # Checklist KCS (Task 3): gom cong_doan_id của MỌI bước trong gói (LSX riêng + bài ghép chung)
    # rồi tra MỘT LẦN — tránh N+1 (mỗi bước một truy vấn) trong vòng lặp của `dung_cong_viec`.
    cong_doan_ids = {
        cd.cong_doan_id
        for lsx_id in lsx_ids
        for cd in repo.routing_steps(lsx_id)
        if cd.cong_doan_id
    } | {
        cd.cong_doan_id
        for bg_id in bai_ghep_ids
        for cd in repo.bai_ghep_cong_doans(bg_id)
        if cd.cong_doan_id
    }
    tieu_chi_theo_cd = repo.checklist_theo_cong_doan(cong_doan_ids)

    cv_by_step = dung_cong_viec(
        repo, goi=goi, phien_ban_so=1,
        lsx_ids=lsx_ids, bai_ghep_ids=bai_ghep_ids,
        nhom_by_lsx=nhom_by_lsx,
        tieu_chi_theo_cd=tieu_chi_theo_cd,
    )
    than_chinh = danh_dau_kcs_cuoi(
        repo, lsx_ids=lsx_ids, nhom_by_lsx=nhom_by_lsx,
        cv_by_step=cv_by_step,
    )
    for nhom_id, lsx_id in than_chinh.items():
        grp = nhom_by_lsx.get(lsx_id)
        if grp is not None:
            grp.than_chinh_lsx_id = lsx_id
        member = repo.member_of_lsx(lsx_id)
        if member is not None:
            member.la_than_chinh = True

    dung_phu_thuoc(
        repo, goi=goi, phien_ban_so=1,
        lsx_ids=lsx_ids, nhom_by_lsx=nhom_by_lsx, cv_by_step=cv_by_step,
    )
    dung_diem_toa(
        repo, goi=goi, phien_ban_so=1,
        lsx_ids=lsx_ids, bai_ghep_ids=bai_ghep_ids,
        nhom_by_lsx=nhom_by_lsx, cv_by_step=cv_by_step,
    )
    repo.flush()
    return goi


def van_de_phat_hanh(
    db: Session,
    *,
    lsx_ids: set[int],
    bai_ghep_ids: set[int] | None = None,
) -> list[dict]:
    """Cửa SOI (read-only) cho hộp thoại phát hành FE: mỗi nhóm thành phẩm phải có ĐÚNG MỘT bước
    KCS-cuối (§4.4). Không có → chưa chốt được thành phẩm; nhiều hơn một → mập mờ thân chính.

    KHÔNG ghi DB (khác `phat_hanh`): gom LSX theo nhóm bằng cách đọc nguồn, rồi đếm ứng viên
    KCS-cuối (bước KCS nằm cuối routing). Trả danh sách vấn đề rỗng nghĩa là không chặn.
    """
    from ..xep_lich_2.constraint import MUC_CHAN_PHAT_HANH, issue

    lsx_ids = set(lsx_ids)
    repo = SanXuatRepository(db)
    kcs = repo.kcs_department_ids()
    # Đọc routing MỘT LẦN cho mỗi LSX — dùng lại cho cả suy KCS-cuối lẫn luật 5 dưới đây, khỏi
    # query trùng cùng một bảng cho cùng một lsx_id.
    steps_by_lsx = {lsx_id: repo.routing_steps(lsx_id) for lsx_id in lsx_ids}

    # Gom LSX theo (order_id, khoa) — không đụng DB.
    from .nhom import _khoa
    nhom_lsx: dict[tuple[int, str], list[int]] = {}
    nhan: dict[tuple[int, str], str] = {}
    for lsx_id in lsx_ids:
        nguon = repo.nguon_nhom_cua_lsx(lsx_id)
        if nguon is None:
            continue
        order_id, order_line_id, nhom, mo_ta = nguon
        key = (order_id, _khoa(order_line_id, nhom))
        nhom_lsx.setdefault(key, []).append(lsx_id)
        nhan[key] = nhom or (mo_ta or "").strip() or f"Dòng {order_line_id}"

    van_de: list[dict] = []
    for key, members in nhom_lsx.items():
        so_kcs_cuoi = 0
        for lsx_id in members:
            steps = steps_by_lsx[lsx_id]
            if steps and steps[-1].la_kcs:
                so_kcs_cuoi += 1
        ten = nhan.get(key, "")
        if so_kcs_cuoi == 0:
            van_de.append(issue(
                "kcs_cuoi_thieu", MUC_CHAN_PHAT_HANH,
                f"Nhóm thành phẩm “{ten}” chưa có bước KCS cuối — không chốt được nghiệm thu.",
                goi_y="Thêm một công đoạn KCS ở cuối routing của lệnh thân chính trong nhóm.",
            ))
        elif so_kcs_cuoi > 1:
            van_de.append(issue(
                "kcs_cuoi_nhieu", MUC_CHAN_PHAT_HANH,
                f"Nhóm thành phẩm “{ten}” có {so_kcs_cuoi} bước KCS cuối — mập mờ lệnh thân chính.",
                goi_y="Chỉ giữ KCS cuối trên MỘT lệnh thân chính; các lệnh khác kết ở bước ghép.",
            ))

    # Luật 5: bước khai la_kcs=true nhưng TỔ thực hiện không có năng lực KCS (department.is_kcs) —
    # sai cấu hình phải CHẶN phát hành, chỉ đích danh bước + tổ (không chỉ "cấu hình sai" chung
    # chung). Quét TOÀN BỘ bước của TOÀN BỘ LSX trong `lsx_ids` (không riêng bước cuối) — bước dùng
    # chung của bài ghép NGOÀI phạm vi Task 2 (chưa có ca thật nào KCS sống trong bài ghép).
    sai_to = [
        cd for steps in steps_by_lsx.values() for cd in steps
        if cd.la_kcs and cd.department_id not in kcs
    ]
    ten_to_by_id = repo.to_ten_nhan({cd.department_id for cd in sai_to if cd.department_id})
    for cd in sai_to:
        ten_to = ten_to_by_id.get(cd.department_id) or "(chưa gán tổ)"
        van_de.append(issue(
            "kcs_sai_to", MUC_CHAN_PHAT_HANH,
            f"Bước “{cd.ten}” khai là KCS nhưng tổ “{ten_to}” không có năng lực KCS.",
            goi_y="Bật cờ KCS cho tổ này ở danh mục Phòng ban, hoặc bỏ cờ KCS khỏi bước.",
        ))
    return van_de
