"""Thực hiện sản xuất — SẢN LƯỢNG: ghi batch + lot đầu vào (Giai đoạn 3, §10.3 · §11.1).

Điều phối lệnh GHI batch sản lượng. Tuân §18 như lát phiên-chạy: kiểm quyền tại service (đúng
tổ trưởng) → transaction → ghi audit → (SSE do router phát sau commit). Truy vấn/ghi DB nằm ở
`repositories/san_xuat_san_luong_repo.py`; ở đây chỉ luật.

Luật cứng (§11.1): `tong = tot + hong` (dung sai làm tròn 3 số lẻ); có `hong` thì bắt buộc
`nhom_loi_id` là một lý do nhóm `loi` (mô tả tự do chỉ bổ sung, không thay danh mục). Chọn lot
đầu vào (§10.3) dựng quan hệ truy vết nguyên liệu/BTP → batch đầu ra.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ...models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG
from ...models.san_xuat_ly_do import NHOM_LOI
from ...models.san_xuat_san_luong import (
    LOT_TU_BATCH,
    LOT_TU_KHO,
    NGUON_LOT,
    SanXuatBatch,
    SanXuatBatchLotVao,
)
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from .thuc_thi import _aware, _gate, _moc

# Dung sai làm tròn cho ràng buộc tong = tot + hong: cột Numeric(18,3) nên nửa bậc số lẻ cuối là
# 0.0005 — quá ngưỡng này coi như nhập lệch chứ không phải sai số làm tròn.
_EPS = 0.0005
# Chỉ ghi sản lượng cho công việc ĐÃ khởi động (đang chạy / tạm dừng / đã xong) — chưa bắt đầu thì
# chưa có gì để ghi.
_TRANG_THAI_GHI_DUOC = (CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)


def _so_khong_am(x, ten: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{ten} không hợp lệ.")
    if v != v or v in (float("inf"), float("-inf")):  # NaN/inf
        raise ValueError(f"{ten} không hợp lệ.")
    if v < 0:
        raise ValueError(f"{ten} không được âm.")
    return v


def _ket_qua_batch(cv, batch: SanXuatBatch | None) -> dict:
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "batch_id": batch.id if batch is not None else None,
    }


def _chuan_hoa_lot(repo: SanXuatSanLuongRepository, cong_viec_id: int, don_vi_mac_dinh: str, raw: dict) -> SanXuatBatchLotVao:
    """Dựng một dòng lot đầu vào từ payload thô, kiểm §10.3. KHÔNG add vào session (caller làm)."""
    nguon_loai = (raw.get("nguon_loai") or LOT_TU_BATCH).strip()
    if nguon_loai not in NGUON_LOT:
        raise ValueError(f"Nguồn lot không hợp lệ: {nguon_loai}.")
    so_luong = _so_khong_am(raw.get("so_luong"), "Số lượng lot")
    if so_luong <= 0:
        raise ValueError("Số lượng lot phải lớn hơn 0.")
    don_vi = (raw.get("don_vi") or don_vi_mac_dinh or "").strip()
    if not don_vi:
        raise ValueError("Lot đầu vào chưa có đơn vị.")

    nguon_batch_id = raw.get("nguon_batch_id")
    nguon_lot_id = raw.get("nguon_lot_id")
    if nguon_loai == LOT_TU_BATCH:
        if not nguon_batch_id:
            raise ValueError("Lot từ công đoạn trước phải chọn batch nguồn.")
        nguon = repo.batch(int(nguon_batch_id))
        if nguon is None:
            raise ValueError("Không tìm thấy batch nguồn của lot đầu vào.")
        if nguon.cong_viec_id == cong_viec_id:
            raise ValueError("Batch nguồn không được trùng chính công việc đang ghi.")
        nguon_lot_id = None
    else:  # LOT_TU_KHO
        if not nguon_lot_id:
            raise ValueError("Lot BTP kho phải có mã lot.")
        nguon_batch_id = None

    return SanXuatBatchLotVao(
        nguon_loai=nguon_loai,
        nguon_batch_id=int(nguon_batch_id) if nguon_batch_id else None,
        nguon_lot_id=int(nguon_lot_id) if nguon_lot_id else None,
        so_luong=so_luong,
        don_vi=don_vi,
    )


def tao_batch(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    bat_dau: datetime,
    ket_thuc: datetime,
    tong,
    tot,
    hong=0,
    don_vi: str | None = None,
    nhom_loi_id: int | None = None,
    mo_ta_loi: str | None = None,
    ghi_chu: str | None = None,
    lot_vao: list[dict] | None = None,
) -> dict:
    """Ghi MỘT batch sản lượng (§11.1) + các lot đầu vào (§10.3). Cho nhiều batch một phần / công đoạn.

    Ràng buộc: `tong = tot + hong`; `hong > 0` bắt buộc `nhom_loi_id` thuộc nhóm `loi`. Đơn vị bỏ
    trống ⇒ lấy `don_vi_ra` của công việc (đơn vị bản địa công đoạn)."""
    repo = SanXuatSanLuongRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate(db, user, cv)
    if cv.trang_thai not in _TRANG_THAI_GHI_DUOC:
        raise ValueError("Chỉ ghi sản lượng cho công việc đã bắt đầu.")

    tong_f = _so_khong_am(tong, "Tổng số lượng")
    tot_f = _so_khong_am(tot, "Số lượng tốt")
    hong_f = _so_khong_am(hong, "Số lượng hỏng")
    if tong_f <= 0:
        raise ValueError("Tổng số lượng phải lớn hơn 0.")
    if abs(tong_f - (tot_f + hong_f)) > _EPS:
        raise ValueError("Tổng số lượng phải bằng Tốt + Hỏng.")

    if bat_dau is None or ket_thuc is None:
        raise ValueError("Batch phải có khoảng thời gian bắt đầu và kết thúc.")
    if _aware(ket_thuc) < _aware(bat_dau):
        raise ValueError("Kết thúc batch không được trước khi bắt đầu.")

    if hong_f > _EPS:
        if not nhom_loi_id:
            raise ValueError("Có số lượng hỏng thì phải chọn nhóm lỗi.")
        ld = repo.ly_do(int(nhom_loi_id))
        if ld is None or ld.nhom != NHOM_LOI:
            raise ValueError("Nhóm lỗi không hợp lệ (phải là một lỗi trong danh mục).")
    else:
        nhom_loi_id = None  # không hỏng thì không neo nhóm lỗi

    don_vi_batch = (don_vi or cv.don_vi_ra or "").strip()
    if not don_vi_batch:
        raise ValueError("Batch chưa có đơn vị.")

    # Dựng lot TRƯỚC khi add batch để bắt lỗi sớm (chưa chạm session cho tới khi hợp lệ hết).
    don_vi_lot_mac_dinh = (cv.don_vi_vao or don_vi_batch or "").strip()
    cac_lot = [
        _chuan_hoa_lot(repo, cong_viec_id, don_vi_lot_mac_dinh, r)
        for r in (lot_vao or [])
    ]

    batch = SanXuatBatch(
        cong_viec_id=cv.id,
        bat_dau=_aware(bat_dau),
        ket_thuc=_aware(ket_thuc),
        tong=tong_f,
        tot=tot_f,
        hong=hong_f,
        don_vi=don_vi_batch,
        nhom_loi_id=nhom_loi_id,
        mo_ta_loi=(mo_ta_loi or "").strip() or None,
        ghi_chu=(ghi_chu or "").strip() or None,
        created_by=getattr(user, "id", None),
    )
    repo.add(batch)
    repo.flush()  # cần batch.id để neo lot
    for lot in cac_lot:
        lot.batch_id = batch.id
        repo.add(lot)

    from ...repositories.audit_repo import AuditLogRepository
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_tao_batch",
        target=f"san_xuat_batch:{batch.id}",
        detail=f"cong_viec={cv.id} tot={tot_f} hong={hong_f}",
    )
    db.commit()
    return _ket_qua_batch(cv, batch)


def them_lot(
    db: Session,
    *,
    user,
    batch_id: int,
    nguon_loai: str = LOT_TU_BATCH,
    nguon_batch_id: int | None = None,
    nguon_lot_id: int | None = None,
    so_luong=0,
    don_vi: str | None = None,
) -> dict:
    """Bổ sung MỘT lot đầu vào cho batch đã tạo (§10.3) — khi tổ trưởng nhập truy vết sau."""
    repo = SanXuatSanLuongRepository(db)
    batch = repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch.")
    cv = repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    don_vi_lot_mac_dinh = (cv.don_vi_vao or batch.don_vi or "").strip()
    lot = _chuan_hoa_lot(
        repo,
        cv.id,
        don_vi_lot_mac_dinh,
        {
            "nguon_loai": nguon_loai,
            "nguon_batch_id": nguon_batch_id,
            "nguon_lot_id": nguon_lot_id,
            "so_luong": so_luong,
            "don_vi": don_vi,
        },
    )
    lot.batch_id = batch.id
    repo.add(lot)
    db.commit()
    return _ket_qua_batch(cv, batch)
