"""Nguồn SẢN LƯỢNG THEO NGƯỜI cho bảng lương (§12, seam của `PieceWorkService`).

`PieceWorkService.khoan_map/defect_map` gọi `list_nguoi_by_period(year, month)` và cộng
`unit_price × quantity` vào cột `khoan` của payroll_lines. Repo này biến DÒNG CHIA SẢN LƯỢNG ĐÃ
CHỐT (§12.2) + DÒNG BÙ TRỪ đã sang kỳ (§12.3) thành các "phiếu sản lượng theo người" seam cần.

**`unit_price` LUÔN 0 từ 11/09/2026** — và đó là chủ ý, không phải thiếu sót. Sản xuất ghi SỐ
LƯỢNG, kế toán lương đổi ra tiền; ba cột `don_gia` ở tầng sản xuất đã bỏ (mg 0296). Hệ quả phải
nói trước: cột `payroll_lines.khoan` = 0 cho MỌI người tới khi dựng màn "Khoán theo kỳ" của kế
toán lương — màn đó đọc chính các dòng sản lượng ở đây rồi tra `piece_rates` theo kỳ. Xem
`docs/superpowers/specs/2026-09-11-san-xuat-chi-ghi-so-luong-design.md`.

Sản lượng thì vẫn THẬT: đó là số tổ đã ghi và đã chốt. An toàn cho lương SỐNG: CHỈ đọc dòng thuộc
header `finalized` (chưa chốt ⇒ công nhân chưa xem) + bù trừ có `ky_bu` đúng kỳ.

Hàng trả về là bản ghi THUẦN (`_DongKhoan`) đúng hợp đồng seam: `.employee_id`, `.tinh_khoan`,
`.unit_price`, `.quantity`, `.defect_deduction`. §12.2: KHÔNG tự trừ lỗi cá nhân ⇒ `defect_deduction`
luôn 0 (trừ lỗi nằm ở tầng batch/KCS, không rơi vào phiếu khoán cá nhân)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.san_xuat_phan_bo import (
    PB_DA_CHOT,
    SanXuatPhanBo,
    SanXuatPhanBoBuTru,
    SanXuatPhanBoDong,
)


@dataclass
class _DongKhoan:
    """Một phiếu sản lượng theo người — đúng hình dạng seam `PieceWorkService` mong đợi."""

    employee_id: int
    tinh_khoan: bool
    unit_price: float
    quantity: float
    defect_deduction: float = 0.0


def _khoang_thang(year: int, month: int) -> tuple[date, date]:
    """[đầu tháng, đầu tháng kế) — lọc theo khoảng ngày (portable SQLite + Postgres, tránh extract)."""
    dau = date(year, month, 1)
    ke = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return dau, ke


class ProductionOutputRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_nguoi_by_period(self, year: int, month: int) -> list[_DongKhoan]:
        dau, ke = _khoang_thang(year, month)
        rows: list[_DongKhoan] = []

        # (1) Dòng phân bổ ĐÃ CHỐT có ngày rơi trong kỳ — phần chính của tiền khoán.
        dong_stmt = (
            select(SanXuatPhanBoDong)
            .join(SanXuatPhanBo, SanXuatPhanBoDong.phan_bo_id == SanXuatPhanBo.id)
            .where(
                SanXuatPhanBo.trang_thai == PB_DA_CHOT,
                SanXuatPhanBoDong.ngay >= dau,
                SanXuatPhanBoDong.ngay < ke,
            )
        )
        for d in self.db.scalars(dong_stmt):
            rows.append(
                _DongKhoan(
                    employee_id=d.employee_id,
                    tinh_khoan=True,
                    unit_price=0.0,   # sản xuất không định giá — xem docstring module
                    quantity=float(d.so_luong_tra_luong or 0),
                )
            )

        # (2) Dòng bù trừ có KỲ BÙ đúng kỳ này (§12.3) — chênh lệch có thể âm.
        bu_stmt = select(SanXuatPhanBoBuTru).where(
            SanXuatPhanBoBuTru.ky_bu_nam == year,
            SanXuatPhanBoBuTru.ky_bu_thang == month,
        )
        for b in self.db.scalars(bu_stmt):
            rows.append(
                _DongKhoan(
                    employee_id=b.employee_id,
                    tinh_khoan=True,
                    unit_price=0.0,   # sản xuất không định giá — xem docstring module
                    quantity=float(b.so_luong_tra_luong or 0),
                )
            )

        return rows
