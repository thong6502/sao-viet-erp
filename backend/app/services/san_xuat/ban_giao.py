"""Thực hiện sản xuất — BÀN GIAO công đoạn (Giai đoạn 3, §11.2 · §11.3).

Một số lượng THỐNG NHẤT mỗi lần giao — không lưu hai con số cạnh tranh. Cùng tổ + cùng LSX thì
tự `confirmed`; khác tổ/khác LSX thì `proposed` → bên NHẬN xác nhận đúng con số cuối. Điều chỉnh
KHÔNG xoá cứng: đẻ dòng lịch sử trước/sau; giảm dưới lượng công đoạn sau đã dùng ⇒ cờ không nhất quán.

Quyền (§6): ĐỀ XUẤT/SỬA là tổ trưởng tổ NGUỒN; XÁC NHẬN là tổ trưởng tổ ĐÍCH; ĐIỀU CHỈNH cho phép
tổ trưởng một trong hai bên (người nhập sai sửa lại). Tất cả siết ở service, router chỉ gác coarse.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.san_xuat_ly_do import NHOM_DIEU_CHINH_BAN_GIAO
from ...models.san_xuat_san_luong import (
    BG_DE_XUAT,
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    SanXuatBanGiao,
    SanXuatBanGiaoDieuChinh,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from .thuc_thi import _gate, _kiem_version, _moc
from .san_luong import _EPS, _so_khong_am


def _head(db: Session, department_id: int | None) -> int | None:
    dept = db.get(Department, department_id) if department_id else None
    return dept.head_user_id if dept else None


def _gate_hai_ben(db: Session, user, nguon_cv, dich_cv) -> None:
    """Điều chỉnh: tổ trưởng NGUỒN hoặc ĐÍCH đều được (người nhập sai sửa lại, §11.3)."""
    uid = getattr(user, "id", None)
    if uid is not None and uid in {
        _head(db, nguon_cv.department_id),
        _head(db, dich_cv.department_id) if dich_cv else None,
    }:
        return
    raise PermissionError("Chỉ tổ trưởng tổ nguồn hoặc tổ đích mới được điều chỉnh bàn giao.")


def _la_cung_to(nguon_cv, dich_cv) -> bool:
    """Tự xác nhận ⇔ cùng tổ VÀ cùng LSX (§11.2). Bước ghép gộp nhiều LSX ⇒ luôn khác LSX ⇒ cần
    xác nhận hai bên (khớp cổng §10.2)."""
    if dich_cv is None:
        return False
    return (
        nguon_cv.department_id is not None
        and nguon_cv.department_id == dich_cv.department_id
        and nguon_cv.lsx_id is not None
        and nguon_cv.lsx_id == dich_cv.lsx_id
    )


def _ket_qua(bg: SanXuatBanGiao, nguon_cv, dich_cv, *, notify_user_id: int | None = None) -> dict:
    return {
        "ban_giao_id": bg.id,
        "trang_thai_ban_giao": bg.trang_thai,
        "so_luong": float(bg.so_luong),
        "khong_nhat_quan": bg.khong_nhat_quan,
        "version": bg.version,
        "nguon_cong_viec_id": bg.nguon_cong_viec_id,
        "dich_cong_viec_id": bg.dich_cong_viec_id,
        "nguon_department_id": nguon_cv.department_id if nguon_cv else None,
        "dich_department_id": dich_cv.department_id if dich_cv else None,
        "notify_user_id": notify_user_id,
    }


def de_xuat(
    db: Session,
    *,
    user,
    nguon_cong_viec_id: int,
    dich_cong_viec_id: int | None,
    so_luong,
    don_vi: str | None = None,
) -> dict:
    """Bên NGUỒN đề xuất giao một lượng sản lượng tốt sang công đoạn sau (§11.2).

    Cùng tổ + cùng LSX → `confirmed` ngay. Khác → `proposed`, chờ bên đích xác nhận. Không giao vượt
    (tổng tốt − đã giao)."""
    repo = SanXuatSanLuongRepository(db)
    nguon_cv = repo.cong_viec(nguon_cong_viec_id)
    if nguon_cv is None:
        raise ValueError("Không tìm thấy công việc nguồn.")
    _gate(db, user, nguon_cv)

    dich_cv = repo.cong_viec(dich_cong_viec_id) if dich_cong_viec_id else None
    if dich_cong_viec_id and dich_cv is None:
        raise ValueError("Không tìm thấy công việc đích.")

    sl = _so_khong_am(so_luong, "Số lượng bàn giao")
    if sl <= 0:
        raise ValueError("Số lượng bàn giao phải lớn hơn 0.")
    con_lai = repo.tong_tot(nguon_cong_viec_id) - repo.tong_da_giao(nguon_cong_viec_id)
    if sl > con_lai + _EPS:
        raise ValueError(
            f"Vượt sản lượng tốt còn lại để giao ({con_lai:g})."
        )

    don_vi_bg = (don_vi or nguon_cv.don_vi_ra or "").strip()
    if not don_vi_bg:
        raise ValueError("Bàn giao chưa có đơn vị.")

    cung_to = _la_cung_to(nguon_cv, dich_cv)
    now = _moc()
    bg = SanXuatBanGiao(
        nguon_cong_viec_id=nguon_cv.id,
        dich_cong_viec_id=dich_cv.id if dich_cv else None,
        cung_to=cung_to,
        so_luong=sl,
        don_vi=don_vi_bg,
        trang_thai=BG_XAC_NHAN if cung_to else BG_DE_XUAT,
        de_xuat_by_id=getattr(user, "id", None),
        de_xuat_luc=now,
        xac_nhan_by_id=getattr(user, "id", None) if cung_to else None,
        xac_nhan_luc=now if cung_to else None,
    )
    repo.add(bg)
    repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_de_xuat",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"nguon={nguon_cv.id} dich={dich_cv.id if dich_cv else '-'} sl={sl} {'cung_to' if cung_to else 'de_xuat'}",
    )
    db.commit()
    # Chờ xác nhận → báo tổ trưởng ĐÍCH; tự xác nhận → không cần báo ai đợi.
    notify = None if cung_to else _head(db, dich_cv.department_id if dich_cv else None)
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_id=notify)


def sua_de_xuat(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    so_luong,
    expected_version: int | None = None,
) -> dict:
    """Bên NGUỒN sửa số lượng khi bàn giao còn `proposed` (§11.2 "bên giao sửa số đề xuất")."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai != BG_DE_XUAT:
        raise ValueError("Chỉ sửa được đề xuất chưa xác nhận.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id) if bg.dich_cong_viec_id else None
    _gate(db, user, nguon_cv)
    _kiem_version(bg, expected_version)

    sl = _so_khong_am(so_luong, "Số lượng bàn giao")
    if sl <= 0:
        raise ValueError("Số lượng bàn giao phải lớn hơn 0.")
    # Trần loại trừ chính đề xuất này (đang tính trong tổng đã giao).
    con_lai = repo.tong_tot(bg.nguon_cong_viec_id) - (
        repo.tong_da_giao(bg.nguon_cong_viec_id) - float(bg.so_luong)
    )
    if sl > con_lai + _EPS:
        raise ValueError(f"Vượt sản lượng tốt còn lại để giao ({con_lai:g}).")

    bg.so_luong = sl
    bg.version += 1
    db.commit()
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_id=_head(db, dich_cv.department_id if dich_cv else None))


def xac_nhan(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    expected_version: int | None = None,
) -> dict:
    """Bên ĐÍCH xác nhận đúng con số cuối (§11.2). Số này thành đầu ra được chấp nhận + đầu vào khả dụng."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai != BG_DE_XUAT:
        raise ValueError("Bàn giao này không ở trạng thái chờ xác nhận.")
    if bg.dich_cong_viec_id is None:
        raise ValueError("Bàn giao ra ngoài chưa neo công đoạn sau, không xác nhận tại tổ.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id)
    _gate(db, user, dich_cv)
    _kiem_version(bg, expected_version)

    bg.trang_thai = BG_XAC_NHAN
    bg.xac_nhan_by_id = getattr(user, "id", None)
    bg.xac_nhan_luc = _moc()
    bg.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_xac_nhan",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"sl={float(bg.so_luong)}",
    )
    db.commit()
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_id=_head(db, nguon_cv.department_id if nguon_cv else None))


def dieu_chinh(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    so_luong_sau,
    ly_do_id: int | None = None,
    mo_ta: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Điều chỉnh số lượng đã xác nhận (§11.3): đẻ dòng lịch sử trước/sau, cập nhật bàn giao.

    Giảm dưới lượng công đoạn sau ĐÃ DÙNG ⇒ đánh dấu không nhất quán (chặn chốt phân bổ/đóng nhóm).
    Bắt buộc lý do (nhóm `dieu_chinh_ban_giao`)."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai not in (BG_XAC_NHAN, BG_DIEU_CHINH):
        raise ValueError("Chỉ điều chỉnh bàn giao đã xác nhận.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id) if bg.dich_cong_viec_id else None
    _gate_hai_ben(db, user, nguon_cv, dich_cv)
    _kiem_version(bg, expected_version)

    if not ly_do_id:
        raise ValueError("Điều chỉnh bàn giao phải kèm lý do.")
    ld = repo.ly_do(int(ly_do_id))
    if ld is None or ld.nhom != NHOM_DIEU_CHINH_BAN_GIAO:
        raise ValueError("Lý do điều chỉnh không hợp lệ.")

    sl_sau = _so_khong_am(so_luong_sau, "Số lượng sau điều chỉnh")
    sl_truoc = float(bg.so_luong)

    # Không nhất quán nếu giảm dưới lượng công đoạn sau đã tiêu thụ (truy vết qua lot đầu vào).
    da_dung = 0.0
    if dich_cv is not None:
        da_dung = repo.da_dung_tu_nguon(bg.nguon_cong_viec_id, bg.dich_cong_viec_id)
    khong_nhat_quan = sl_sau < da_dung - _EPS

    repo.add(
        SanXuatBanGiaoDieuChinh(
            ban_giao_id=bg.id,
            so_luong_truoc=sl_truoc,
            so_luong_sau=sl_sau,
            ly_do_id=int(ly_do_id),
            mo_ta=(mo_ta or "").strip() or None,
            khong_nhat_quan=khong_nhat_quan,
            created_by=getattr(user, "id", None),
        )
    )
    bg.so_luong = sl_sau
    bg.trang_thai = BG_DIEU_CHINH
    bg.khong_nhat_quan = khong_nhat_quan
    bg.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_dieu_chinh",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"{sl_truoc} -> {sl_sau}{' KHONG_NHAT_QUAN' if khong_nhat_quan else ''}",
    )
    db.commit()
    # Báo bên còn lại (không phải người vừa điều chỉnh) — ưu tiên báo tổ đích, nếu chính họ sửa thì báo nguồn.
    uid = getattr(user, "id", None)
    dich_head = _head(db, dich_cv.department_id if dich_cv else None)
    notify = _head(db, nguon_cv.department_id if nguon_cv else None) if uid == dich_head else dich_head
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_id=notify)
