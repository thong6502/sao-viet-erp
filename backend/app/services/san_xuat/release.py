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
    # CỐ Ý KHÔNG ghi `SanXuatCongViecLichSu` cho v1 ở đây (thiết kế ban đầu định ghi, lý do "không
    # thì v1 trống" KHÔNG đứng vững): dòng SỐNG chính là trạng thái của mọi phiên bản kể từ
    # `cv.phien_ban_so` trở đi, nên bước chưa lần nào bị cập nhật đọc v1 ngay trên dòng sống. Ghi
    # thêm ở đây chỉ đẻ một dòng v1 TRÙNG cho mọi bước về sau bị đè — xem cách đọc ở
    # `XepLich3Service.so_sanh_phien_ban`.
    return goi


def van_de_phat_hanh(
    db: Session,
    *,
    lsx_ids: set[int],
    bai_ghep_ids: set[int] | None = None,
) -> list[dict]:
    """Cửa SOI (read-only) cho hộp thoại phát hành FE: mỗi nhóm thành phẩm phải có KHÔNG QUÁ MỘT
    công đoạn cuối (luật ở `snapshot.cong_doan_cuoi_theo_nhom`). Nhiều hơn một → không rõ công đoạn
    nào ra thành phẩm, KCS không biết đề xuất nhập kho ở đâu.

    Không còn chặn "thiếu bước KCS cuối" (KCS theo lệnh, mg 0306): công đoạn cuối do tổ nào làm cũng
    được, KCS kiểm được mọi công đoạn.

    KHÔNG ghi DB (khác `phat_hanh`). Trả danh sách vấn đề rỗng nghĩa là không chặn.
    """
    from ..xep_lich_2.constraint import MUC_CHAN_PHAT_HANH, issue
    from .snapshot import cong_doan_cuoi_theo_nhom

    lsx_ids = set(lsx_ids)
    repo = SanXuatRepository(db)

    # Gom LSX theo (order_id, khoa) — cùng khoá `dam_bao_nhom` dùng lúc phát hành.
    from .nhom import _khoa
    nhom_cua_lsx: dict[int, tuple[int, str]] = {}
    nhan: dict[tuple[int, str], str] = {}
    for lsx_id in lsx_ids:
        nguon = repo.nguon_nhom_cua_lsx(lsx_id)
        if nguon is None:
            continue
        order_id, order_line_id, nhom, mo_ta = nguon
        key = (order_id, _khoa(order_line_id, nhom))
        nhom_cua_lsx[lsx_id] = key
        nhan[key] = nhom or (mo_ta or "").strip() or f"Dòng {order_line_id}"

    # Bước lệnh bị bài ghép phủ chạy CHUNG một công việc — định danh bằng bước chung của bài ghép.
    buoc_chung: dict[str, int] = {}
    for bg_id in sorted(bai_ghep_ids or ()):
        for cd in repo.bai_ghep_cong_doans(bg_id):
            for sk in repo.covered_step_keys_of_cd(cd.id):
                buoc_chung[sk] = cd.id

    def dinh_danh(_lsx_id, buoc):
        bg_cd = buoc_chung.get(buoc.step_key)
        return ("bai_ghep", bg_cd) if bg_cd is not None else ("lsx", buoc.id)

    van_de: list[dict] = []
    for key, ung_vien in cong_doan_cuoi_theo_nhom(
        repo, nhom_cua_lsx=nhom_cua_lsx, dinh_danh=dinh_danh
    ).items():
        if len(ung_vien) > 1:
            ten = nhan.get(key, "")
            van_de.append(issue(
                "kcs_cuoi_nhieu", MUC_CHAN_PHAT_HANH,
                f"Nhóm thành phẩm “{ten}” có {len(ung_vien)} công đoạn cuối — chưa rõ công đoạn "
                "nào ra thành phẩm.",
                goi_y="Nối công đoạn cuối của các lệnh phụ vào công đoạn ghép của lệnh thân chính.",
            ))
    return van_de
