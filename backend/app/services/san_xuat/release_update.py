"""Thực hiện sản xuất — PHÁT HÀNH CẬP NHẬT & THU HỒI GÓI khi lịch đổi sau phát hành (§4.3).

Bối cảnh: sau phát hành, người lập kế hoạch có thể sửa THỜI GIAN / NGUỒN LỰC (máy) của công việc
CHƯA BẮT ĐẦU ở màn Xếp lịch 2. Thay đổi đó nằm ở lịch sống (`xep_lich_cong_doan`) — là "bản nháp";
chỉ có hiệu lực khi bấm **Phát hành cập nhật** ở đây, khi ấy snapshot của các việc chưa bắt đầu được
CHỤP LẠI theo lịch hiện tại và gói lên một phiên bản mới.

Luật §4.3 (chốt bởi chủ dự án):
  · Chỉ việc CHƯA bắt đầu mới được cập nhật. "Đã bắt đầu" = trạng thái ≠ `released` HOẶC đã có ≥1
    phiên chạy — hai tín hiệu này do `bat_dau` đặt cùng lúc, soi cả hai cho chắc.
  · Mỗi lần cập nhật: tăng `goi.version_hien_tai`, đẻ một `san_xuat_phien_ban(loai=cap_nhat)` kèm
    LÝ DO bắt buộc (giữ lịch sử phiên bản đủ) — KHÔNG xoá phiên bản cũ.
  · Việc chưa bắt đầu được tái chụp (máy + giờ dự kiến) theo lịch hiện tại, gắn `phien_ban_so` mới;
    MỌI phân công trước + thỏa thuận hỗ trợ của nó bị HUỶ ⇒ các tổ phải xác nhận lại.
  · Việc ĐÃ bắt đầu: giữ nguyên snapshot (không đổi lịch/tuyến/tỷ lệ ghép/dữ liệu) — không đụng tới.
  · Khi BẤT KỲ việc nào trong gói đã bắt đầu ⇒ KHÔNG được thu hồi toàn bộ gói (chỉ chặn thu-hồi,
    không chặn cập-nhật phần còn chưa bắt đầu).

Chỉ TÁI CHỤP thời gian + máy (thứ Xếp lịch 2 đổi được sau phát hành). Định mức/khoán/vật tư/tuyến
là dữ liệu routing đã KHOÁ (`da_phat_hanh`) nên KHÔNG đọc-sống lại — đúng tinh thần đóng băng §4.2.

Hàm ở đây CHỦ GIAO DỊCH cho nhánh cập-nhật (tự commit); còn `thu_hoi_goi` nằm TRONG giao dịch gỡ
phát hành của `xep_lich_van_de_service` nên KHÔNG commit. Router phát SSE sau khi service trả về.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import (
    CV_PHAT_HANH,
    GOI_DA_THU_HOI,
    GOI_DANG_PHAT_HANH,
    PB_CAP_NHAT,
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatPhienBan,
)
from ...models.san_xuat_thuc_thi import PC_DA_RUT
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from . import ho_tro

_LY_DO_RUT = "Phát hành cập nhật — phân công cần xác nhận lại."


# --- Trợ giúp ------------------------------------------------------------------------------
def _refs(repo: SanXuatRepository, nguon: str, id: int) -> tuple[set[int], set[int]]:
    """(lsx_ids, bai_ghep_ids) để tìm gói đang hiệu lực. Bài ghép kéo theo các LSX thành viên."""
    if nguon == "lsx":
        return {id}, set()
    if nguon == "in_ghep":
        return set(repo.lsx_ids_cua_bai_ghep({id})), {id}
    raise ValueError(f"Nguồn không hợp lệ: {nguon!r} (cần 'lsx' hoặc 'in_ghep').")


def _da_bat_dau_ids(
    thuc: SanXuatThucThiRepository, all_cv: list[SanXuatCongViec]
) -> set[int]:
    """Id các công việc ĐÃ bắt đầu: có phiên chạy HOẶC trạng thái đã rời `released`."""
    ids = {cv.id for cv in all_cv}
    da = thuc.cong_viec_co_phien(ids)
    da |= {cv.id for cv in all_cv if cv.trang_thai != CV_PHAT_HANH}
    return da


def _thoi_gian_nguon(repo: SanXuatRepository, cv: SanXuatCongViec):
    """(may_id, start, finish) hiện tại từ lịch của công đoạn nguồn của công việc."""
    if cv.bai_ghep_cong_doan_id is not None:
        return repo.thoi_gian_bg_step(cv.bai_ghep_cong_doan_id)
    if cv.lsx_cong_doan_id is not None:
        return repo.thoi_gian_lsx_step(cv.lsx_cong_doan_id)
    return (None, None, None)


def _huy_phan_cong_ho_tro(
    db: Session, thuc: SanXuatThucThiRepository, cv: SanXuatCongViec, actor_uid: int | None
) -> tuple[int, int]:
    """Huỷ phân công + thỏa thuận hỗ trợ của một việc chưa bắt đầu. Trả (số PC, số HT) đã huỷ.
    Việc chưa bắt đầu không có khoảng tham gia mở, nên chỉ cần rút dòng roster."""
    n_pc = 0
    for pc in thuc.phan_cong_hoat_dong(cv.id):
        pc.trang_thai = PC_DA_RUT
        pc.ly_do_rut = _LY_DO_RUT
        pc.version += 1
        n_pc += 1
    n_ht = ho_tro.huy_ho_tro_phat_hanh_lai(db, cong_viec_id=cv.id, actor_user_id=actor_uid)
    cv.version += 1
    return n_pc, n_ht


# --- Đọc: thông tin gói (cho UI quyết nút Cập nhật / Thu hồi) --------------------------------
def thong_tin_goi(db: Session, *, nguon: str, id: int) -> dict:
    """Trạng thái gói phát hành của một LSX/bài ghép + lịch sử phiên bản + số việc đã/chưa bắt đầu.

    `co_goi=False` khi chưa phát hành (hoặc lệnh phát hành trước khi có lớp thực hiện). Chỉ đọc."""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return {"co_goi": False}
    all_cv = repo.cong_viec_cua_goi(goi.id)
    so_da = len(_da_bat_dau_ids(thuc, all_cv))
    so_chua = len(all_cv) - so_da
    dang = goi.trang_thai == GOI_DANG_PHAT_HANH
    phien_bans = sorted(goi.phien_bans, key=lambda p: p.so)
    return {
        "co_goi": True,
        "goi_id": goi.id,
        "ma": goi.ma,
        "trang_thai": goi.trang_thai,
        "version_hien_tai": goi.version_hien_tai,
        "so_cong_viec": len(all_cv),
        "so_da_bat_dau": so_da,
        "so_chua_bat_dau": so_chua,
        "cho_phep_cap_nhat": dang and so_chua > 0,
        "cho_phep_thu_hoi": dang and so_da == 0,
        "phien_bans": [
            {
                "so": p.so,
                "loai": p.loai,
                "ly_do": p.ly_do,
                "phat_hanh_by_id": p.phat_hanh_by_id,
                "luc": p.created_at.isoformat() if p.created_at else None,
            }
            for p in phien_bans
        ],
    }


# --- Ghi: phát hành cập nhật (chủ giao dịch) ------------------------------------------------
def phat_hanh_cap_nhat(db: Session, *, nguon: str, id: int, ly_do: str, actor) -> dict:
    """Tái chụp các việc CHƯA bắt đầu theo lịch hiện tại → phiên bản mới (§4.3). Tự commit.

    Chặn nếu chưa có gói / gói đã thu hồi / không còn việc nào chưa bắt đầu. Việc đã bắt đầu giữ
    nguyên; các việc cập nhật bị huỷ phân công + hỗ trợ (buộc tổ xác nhận lại)."""
    ly_do = (ly_do or "").strip()
    if len(ly_do) < 3:
        raise ValueError("Phát hành cập nhật phải ghi lý do (tối thiểu 3 ký tự).")
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        raise ValueError("Chưa phát hành — không có gói để cập nhật.")
    if goi.trang_thai != GOI_DANG_PHAT_HANH:
        raise ValueError("Gói đã thu hồi — không thể cập nhật.")

    all_cv = repo.cong_viec_cua_goi(goi.id)
    da_bat_dau = _da_bat_dau_ids(thuc, all_cv)
    chua = [cv for cv in all_cv if cv.id not in da_bat_dau]
    if not chua:
        raise ValueError("Mọi công việc trong gói đã bắt đầu — không còn gì để cập nhật.")

    actor_uid = getattr(actor, "id", None)
    new_ver = goi.version_hien_tai + 1
    repo.add(SanXuatPhienBan(
        goi_id=goi.id, so=new_ver, loai=PB_CAP_NHAT, ly_do=ly_do[:500],
        phat_hanh_by_id=actor_uid,
    ))
    goi.version_hien_tai = new_ver
    goi.version += 1

    so_huy_pc = so_huy_ht = 0
    for cv in chua:
        may_id, start, finish = _thoi_gian_nguon(repo, cv)
        if may_id is not None:          # giữ máy cũ nếu lịch mới chưa gán (bước tổ/thuê ngoài)
            cv.may_id = may_id
        cv.du_kien_bat_dau = start
        cv.du_kien_ket_thuc = finish
        cv.phien_ban_so = new_ver
        n_pc, n_ht = _huy_phan_cong_ho_tro(db, thuc, cv, actor_uid)
        so_huy_pc += n_pc
        so_huy_ht += n_ht

    AuditLogRepository(db).create(
        actor_user_id=actor_uid,
        action="san_xuat.phat_hanh_cap_nhat",
        target=f"san_xuat_goi:{goi.id}",
        detail=(f"Cập nhật lịch → phiên bản {new_ver}: tái chụp {len(chua)} việc chưa bắt đầu, "
                f"giữ nguyên {len(da_bat_dau)} việc đã bắt đầu; huỷ {so_huy_pc} phân công + "
                f"{so_huy_ht} hỗ trợ. Lý do: {ly_do[:200]}"),
    )
    repo.commit()
    return {
        "goi_id": goi.id,
        "ma": goi.ma,
        "version_hien_tai": new_ver,
        "so_cong_viec_cap_nhat": len(chua),
        "so_giu_nguyen": len(da_bat_dau),
        "so_huy_phan_cong": so_huy_pc,
        "so_huy_ho_tro": so_huy_ht,
    }


# --- Thu hồi gói (nằm trong giao dịch gỡ-phát-hành — KHÔNG commit) ---------------------------
def co_cong_viec_da_bat_dau(db: Session, *, nguon: str, id: int) -> bool:
    """Gói đang hiệu lực của LSX/bài ghép có việc nào đã bắt đầu? (Chặn thu hồi toàn gói — §4.3.)"""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return False
    return bool(_da_bat_dau_ids(thuc, repo.cong_viec_cua_goi(goi.id)))


def thu_hoi_goi(db: Session, *, nguon: str, id: int, actor) -> int:
    """Thu hồi gói phát hành khi CHƯA việc nào bắt đầu: đánh `da_thu_hoi` (biến khỏi bàn tổ) + huỷ
    phân công/hỗ trợ còn treo. KHÔNG commit — nằm trong giao dịch gỡ-phát-hành của caller. Trả số
    công việc trong gói (0 nếu không có gói). Người gọi phải chặn trước bằng `co_cong_viec_da_bat_dau`."""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return 0
    all_cv = repo.cong_viec_cua_goi(goi.id)
    actor_uid = getattr(actor, "id", None)
    for cv in all_cv:
        _huy_phan_cong_ho_tro(db, thuc, cv, actor_uid)
    goi.trang_thai = GOI_DA_THU_HOI
    goi.version += 1
    AuditLogRepository(db).create(
        actor_user_id=actor_uid,
        action="san_xuat.thu_hoi_goi",
        target=f"san_xuat_goi:{goi.id}",
        detail=f"Thu hồi gói phát hành {goi.ma} ({len(all_cv)} công việc) — gỡ phát hành khi chưa việc nào bắt đầu.",
    )
    repo.flush()
    return len(all_cv)
