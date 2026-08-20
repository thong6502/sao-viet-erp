"""Thực hiện sản xuất — XÁC NHẬN VẬT TƯ đã nhận (Giai đoạn 3, §10.1).

Tổ trưởng xác nhận đã nhận vật tư của MỘT phiếu xuất ĐÃ GHI SỔ, NGUYÊN TRẠNG — không đẻ con số
"tổ nhận" đối nghịch "kho giao". Nếu số lệch, kho sửa chứng từ TRƯỚC. Chỉ phần đã xác nhận mới coi
là tồn khả dụng cho công đoạn (đọc ở nơi khác). Một phiếu chỉ xác nhận một lần (`voucher_id` UNIQUE).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.san_xuat_san_luong import SanXuatVatTuNhan
from ...models.stock_voucher import VOUCHER_POSTED, VOUCHER_XUAT
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from .thuc_thi import _moc


def _gate_to_truong(db: Session, user, department_id: int) -> Department:
    """Chỉ tổ trưởng ĐÚNG tổ nhận mới được xác nhận (§6, giống `_gate` của công việc)."""
    dept = db.get(Department, department_id) if department_id else None
    uid = getattr(user, "id", None)
    if dept is None or dept.head_user_id is None or dept.head_user_id != uid:
        raise PermissionError("Chỉ tổ trưởng của tổ nhận mới được xác nhận vật tư.")
    return dept


def xac_nhan_vat_tu(
    db: Session,
    *,
    user,
    voucher_id: int,
    department_id: int,
    ghi_chu: str | None = None,
) -> dict:
    """Xác nhận đã nhận vật tư của một phiếu xuất đã ghi sổ (§10.1). Phiếu phải là XUẤT + posted."""
    repo = SanXuatSanLuongRepository(db)
    _gate_to_truong(db, user, department_id)

    voucher = repo.voucher(voucher_id)
    if voucher is None:
        raise ValueError("Không tìm thấy phiếu xuất.")
    if voucher.loai != VOUCHER_XUAT or voucher.trang_thai != VOUCHER_POSTED:
        raise ValueError("Chỉ xác nhận phiếu XUẤT đã ghi sổ.")
    if repo.vat_tu_nhan_cua_voucher(voucher_id) is not None:
        raise ValueError("Phiếu này đã được xác nhận nhận.")

    nhan = SanXuatVatTuNhan(
        voucher_id=voucher_id,
        department_id=department_id,
        xac_nhan_by_id=getattr(user, "id", None),
        xac_nhan_luc=_moc(),
        ghi_chu=(ghi_chu or "").strip() or None,
    )
    repo.add(nhan)
    repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_xac_nhan_vat_tu",
        target=f"stock_voucher:{voucher_id}",
        detail=f"to={department_id}",
    )
    db.commit()
    return {
        "voucher_id": voucher_id,
        "department_id": department_id,
        "nhan_id": nhan.id,
    }
