"""Router — BÁO CÁO KHO (kế toán): sổ nhập-xuất + khóa kỳ (chốt sổ) + export MISA.

docs/spec-bao-cao-kho.md. CHỈ kế toán kho vào (quyền `close_book`): xem báo cáo + export Excel +
khóa/mở kỳ. Đăng ký TRƯỚC `kho.router` trong main.py vì `/api/kho/khoa-so` là path 1 đoạn sẽ bị
`/api/kho/{kho_id}` nuốt nếu khai sau (FastAPI khớp theo thứ tự).
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.kho_hang import KhoHang
from ..models.material import Material
from ..models.stock_lot import StockLot
from ..models.stock_request import StockRequest
from ..models.stock_voucher import (
    VOUCHER_NHAP,
    VOUCHER_POSTED,
    VOUCHER_XUAT,
    StockVoucher,
    StockVoucherLine,
)
from ..models.user import User
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.kho_khoa_so_repo import KhoKhoaSoRepository
from ..repositories.user_repo import UserRepository
from ..schemas.stock import (
    BaoCaoKhoPage,
    BaoCaoKhoRow,
    KhoaSoKyRow,
    KhoKhoaSoIn,
    KhoKhoaSoRow,
)

router = APIRouter(prefix="/api/kho", tags=["kho-bao-cao"])
MODULE = "kho"

Db = Annotated[Session, Depends(get_db)]
CloseBookUser = Annotated[User, Depends(require_permission(MODULE, "close_book"))]


# --- Truy vấn dòng nhập-xuất (chỉ phiếu ĐÃ GHI SỔ) -----------------------------

def _report_rows(
    db: Session, *, tu: date | None, den: date | None, kho_id: int | None,
    loai: str | None, q: str | None = None,
) -> list[BaoCaoKhoRow]:
    # `q` = tìm số CT / mã hàng / tên hàng (khớp ô Tìm ở màn) → để "lọc gì = xuất nấy".
    ql = (q or "").strip().lower()
    stmt = (
        select(StockVoucher, StockVoucherLine, Material, StockRequest, KhoHang, StockLot)
        .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
        .join(Material, Material.id == StockVoucherLine.material_id, isouter=True)
        .join(StockRequest, StockRequest.id == StockVoucher.request_id, isouter=True)
        .join(KhoHang, KhoHang.id == StockVoucher.kho_id, isouter=True)
        .join(StockLot, StockLot.id == StockVoucherLine.lot_id, isouter=True)
        .where(StockVoucher.trang_thai == VOUCHER_POSTED)
    )
    if loai:
        stmt = stmt.where(StockVoucher.loai == loai)
    if kho_id:
        stmt = stmt.where(StockVoucher.kho_id == kho_id)
    stmt = stmt.order_by(StockVoucher.ghi_so_luc, StockVoucher.id, StockVoucherLine.id)

    rows: list[BaoCaoKhoRow] = []
    for v, ln, m, req, kho, lot in db.execute(stmt).all():
        # Lọc theo ngày GHI SỔ ở Python (tránh func.date lệ thuộc dialect + parse tz của SQLite).
        d = v.ghi_so_luc.date() if v.ghi_so_luc else None
        if tu and (d is None or d < tu):
            continue
        if den and (d is None or d > den):
            continue
        qty = float(ln.so_luong or 0)
        # NHẬP: đơn giá ở dòng phiếu. XUẤT: dòng phiếu không có đơn giá → lấy GIÁ VỐN của lô đã
        # xuất (don_gia_nhap). Coalesce để cả 2 chiều đều ra tiền.
        raw_price = ln.don_gia if ln.don_gia is not None else getattr(lot, "don_gia_nhap", None)
        price = int(raw_price) if raw_price is not None else None
        row = BaoCaoKhoRow(
            voucher_id=v.id,
            ngay_ghi_so=d,
            ngay_ct=v.ngay,
            so_ct=v.ma,
            loai=v.loai,
            loai_kho=req.loai_kho if req else None,
            ma_hang=getattr(m, "code", None),
            ten_hang=getattr(m, "name", None),
            dvt=getattr(m, "unit", None),
            so_luong=qty,
            don_gia=price,
            thanh_tien=round(price * qty) if price is not None else None,
            kho_id=v.kho_id,
            kho_ten=getattr(kho, "ten", None),
        )
        if ql and not any(
            ql in (val or "").lower() for val in (row.so_ct, row.ma_hang, row.ten_hang)
        ):
            continue
        rows.append(row)
    return rows


@router.get("/bao-cao/dong", response_model=BaoCaoKhoPage)
def bao_cao_dong(
    db: Db,
    _: CloseBookUser,
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    loai: str | None = Query(default=None, pattern="^(NHAP|XUAT)$"),
    q: str | None = Query(default=None),
) -> BaoCaoKhoPage:
    rows = _report_rows(db, tu=tu, den=den, kho_id=kho_id, loai=loai, q=q)
    return BaoCaoKhoPage(items=rows, total=len(rows))


# --- Khóa kỳ (chốt sổ) ---------------------------------------------------------

def _khoa_row(db: Session, row) -> KhoKhoaSoRow:
    kho = KhoHangRepository(db).get(row.kho_id) if row.kho_id else None
    nguoi = UserRepository(db).get_by_id(row.nguoi_khoa_id) if row.nguoi_khoa_id else None
    return KhoKhoaSoRow(
        id=row.id,
        kho_id=row.kho_id,
        kho_ten=getattr(kho, "ten", None),
        tu_ngay=row.tu_ngay,
        den_ngay=row.den_ngay,
        hanh_dong=row.hanh_dong,
        nguoi_khoa_ten=getattr(nguoi, "name", None),
        khoa_luc=row.khoa_luc,
    )


@router.get("/khoa-so", response_model=list[KhoKhoaSoRow])
def get_khoa_so(db: Db, _: CloseBookUser) -> list[KhoKhoaSoRow]:
    """Lịch sử thao tác khóa/mở kỳ (mới nhất trước) — dùng cho tab Lịch sử + đối chiếu đang khóa."""
    return [_khoa_row(db, r) for r in KhoKhoaSoRepository(db).history()]


@router.get("/khoa-so/ky", response_model=list[KhoaSoKyRow])
def get_khoa_so_ky(db: Db, _: CloseBookUser) -> list[KhoaSoKyRow]:
    """Các KỲ CÒN đang khóa (đã gộp khoảng liền mạch) — cho tab 'Kỳ đã khóa' chọn nhanh + xuất."""
    kho_repo = KhoHangRepository(db)
    out: list[KhoaSoKyRow] = []
    for kho_id, tu, den, khoa_luc in KhoKhoaSoRepository(db).locked_periods():
        kho = kho_repo.get(kho_id) if kho_id else None
        out.append(KhoaSoKyRow(
            kho_id=kho_id, kho_ten=getattr(kho, "ten", None),
            tu_ngay=tu, den_ngay=den, khoa_luc=khoa_luc,
        ))
    return out


@router.post("/khoa-so", response_model=KhoKhoaSoRow, status_code=status.HTTP_201_CREATED)
def set_khoa_so(payload: KhoKhoaSoIn, db: Db, user: CloseBookUser) -> KhoKhoaSoRow:
    if payload.kho_id is not None and KhoHangRepository(db).get(payload.kho_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy kho")
    repo = KhoKhoaSoRepository(db)
    # KHÓA: không cho khóa ĐÈ lên kỳ đã khóa (kỳ mới phải bắt đầu sau ngày đã khóa gần nhất).
    if payload.hanh_dong == "khoa" and repo.overlaps_locked(
        payload.kho_id, payload.tu_ngay, payload.den_ngay
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khoảng này chồng lấn kỳ đã khóa — chọn khoảng bắt đầu sau ngày đã khóa gần nhất.",
        )
    # MỞ: khóa sổ TUẦN TỰ — chỉ mở được phần ĐUÔI vùng khóa, tính từ NGÀY CUỐI đang khóa (cutoff).
    # → mở được cả vùng [đầu..cutoff] hoặc một đuôi [giữa..cutoff]; KHÔNG mở phần giữa/đầu để hở
    #   kỳ mới hơn, cũng không mở vượt quá vùng khóa.
    if payload.hanh_dong == "mo":
        cutoff = repo.locked_cutoff(payload.kho_id)
        if cutoff is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không có kỳ nào đang khóa để mở.",
            )
        if payload.den_ngay != cutoff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Mở sổ phải tính từ NGÀY CUỐI đang khóa — đặt 'Đến ngày' = "
                    f"{cutoff.strftime('%d/%m/%Y')} (chọn 'Từ ngày' tùy ý để mở phần đuôi kỳ khóa)."
                ),
            )
    row = repo.add(
        kho_id=payload.kho_id, tu_ngay=payload.tu_ngay, den_ngay=payload.den_ngay,
        hanh_dong=payload.hanh_dong, nguoi_khoa_id=user.id,
    )
    return _khoa_row(db, row)


# --- Export Excel theo mẫu MISA -----------------------------------------------

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Cột đúng thứ tự mẫu MISA (Copy of Nhap_kho.xls 33 cột / Copy of Xuat_kho.xls 51 cột).
_NHAP_HEADERS = [
    "Hiển thị trên sổ", "Loại nhập kho", "Ngày hạch toán (*)", "Ngày chứng từ (*)",
    "Số chứng từ (*)", "Mã đối tượng", "Tên đối tượng", "Người giao hàng", "Diễn giải",
    "Nhân viên bán hàng", "Kèm theo", "Loại tiền", "Tỷ giá", "Mã hàng (*)", "Tên hàng",
    "Kho (*)", "Hàng hóa giữ hộ/bán hộ", "TK Nợ (*)", "TK Có (*)", "ĐVT", "Số lượng",
    "Đơn giá", "Thành tiền", "Thành tiền quy đổi", "Số lô", "Hạn sử dụng", "Khoản mục CP",
    "Đơn vị", "Đối tượng THCP", "Công trình", "Đơn đặt hàng", "Hợp đồng bán", "Mã thống kê",
]
_XUAT_HEADERS = [
    "Hiển thị trên sổ", "Loại xuất kho", "Ngày hạch toán (*)", "Ngày chứng từ (*)",
    "Số chứng từ (*)", "Mẫu số HĐ", "Ký hiệu HĐ", "Mã đối tượng", "Tên đối tượng",
    "Địa chỉ/Bộ phận", "Tên người nhận/Của", "Lý do xuất/Về việc", "Nhân viên bán hàng",
    "Kèm theo", "Số lệnh điều động", "Ngày lệnh điều động", "Người vận chuyển",
    "Tên người vận chuyển", "Hợp đồng số", "Phương tiện vận chuyển", "Xuất tại kho",
    "Địa chỉ kho xuất", "Nhập tại chi nhánh", "Tên chi nhánh", "MST chi nhánh", "Nhập tại kho",
    "Địa chỉ kho nhập", "Mã hàng (*)", "Tên hàng", "Là hàng khuyến mại", "Kho (*)",
    "Hàng hóa giữ hộ/bán hộ", "TK Nợ (*)", "TK Có (*)", "ĐVT", "Số lượng", "Đơn giá bán",
    "Thành tiền", "Đơn giá vốn", "Tiền vốn", "Số lô", "Hạn sử dụng", "Đối tượng",
    "Khoản mục CP", "Đơn vị", "Đối tượng THCP", "Công trình", "Đơn đặt hàng", "Hợp đồng bán",
    "CP không hợp lý", "Mã thống kê",
]


# Cột SỐ cần format phân cách hàng nghìn (Excel hiện "." theo locale VN). Giá trị vẫn là số →
# MISA import đọc đúng; number_format chỉ đổi cách HIỂN THỊ.
_MONEY_COLS = {"Đơn giá", "Thành tiền", "Đơn giá bán", "Đơn giá vốn", "Tiền vốn", "Thành tiền quy đổi"}
_QTY_COLS = {"Số lượng"}


def _fmt_date(d: date | None) -> str | None:
    return d.strftime("%d/%m/%Y") if d else None


def _map_nhap(r: BaoCaoKhoRow) -> dict:
    return {
        # "Loại nhập kho" để TRỐNG — kế toán tự gõ mã 0/1/2/3 trong Excel/MISA.
        "Ngày hạch toán (*)": _fmt_date(r.ngay_ghi_so),
        "Ngày chứng từ (*)": _fmt_date(r.ngay_ct),
        "Số chứng từ (*)": r.so_ct,
        "Mã hàng (*)": r.ma_hang,
        "Tên hàng": r.ten_hang,
        "Kho (*)": r.kho_ten,
        "ĐVT": r.dvt,
        "Số lượng": r.so_luong,
        "Đơn giá": r.don_gia,
        "Thành tiền": r.thanh_tien,
    }


def _map_xuat(r: BaoCaoKhoRow) -> dict:
    return {
        # "Loại xuất kho" để TRỐNG — kế toán tự gõ mã 0/1/2/3 trong Excel/MISA.
        "Ngày hạch toán (*)": _fmt_date(r.ngay_ghi_so),
        "Ngày chứng từ (*)": _fmt_date(r.ngay_ct),
        "Số chứng từ (*)": r.so_ct,
        "Mã hàng (*)": r.ma_hang,
        "Tên hàng": r.ten_hang,
        "Xuất tại kho": r.kho_ten,
        "Kho (*)": r.kho_ten,
        "ĐVT": r.dvt,
        "Số lượng": r.so_luong,
        "Đơn giá vốn": r.don_gia,
        "Tiền vốn": r.thanh_tien,
    }


# Mẫu Excel MISA (đã chuyển .xls→.xlsx, GIỮ màu cột + gợi ý (data-validation) + độ rộng + freeze).
# Header ở dòng 1; data ghi từ dòng 2. Xem backend/app/templates/kho/.
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "kho"


def _build_xlsx(rows: list[BaoCaoKhoRow], loai: str) -> bytes:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font

    is_nhap = loai == VOUCHER_NHAP
    headers = _NHAP_HEADERS if is_nhap else _XUAT_HEADERS
    mapper = _map_nhap if is_nhap else _map_xuat
    template = _TEMPLATE_DIR / ("nhap_kho.xlsx" if is_nhap else "xuat_kho.xlsx")

    if template.exists():
        # Dùng mẫu MISA thật (màu + gợi ý cột + độ rộng); header ở dòng 1, data ghi từ dòng 2.
        wb = load_workbook(template)
        ws = wb.active
    else:
        # Dự phòng nếu mẫu chưa deploy: dựng header trơn để export vẫn chạy.
        wb = Workbook()
        ws = wb.active
        ws.title = "Nhập kho" if is_nhap else "Xuất kho"
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
    for i, r in enumerate(rows):
        vals = mapper(r)
        for ci, h in enumerate(headers, start=1):
            v = vals.get(h)
            if v is None:
                continue
            cell = ws.cell(row=2 + i, column=ci, value=v)
            if h in _MONEY_COLS:
                cell.number_format = "#,##0"      # phân cách hàng nghìn (Excel VN hiện ".")
            elif h in _QTY_COLS:
                cell.number_format = "#,##0.###"  # SL có thể lẻ, tối đa 3 số thập phân
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/bao-cao/export.xlsx")
def export_bao_cao(
    db: Db,
    _: CloseBookUser,
    loai: str = Query(pattern="^(NHAP|XUAT)$"),
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> Response:
    rows = _report_rows(db, tu=tu, den=den, kho_id=kho_id, loai=loai, q=q)
    content = _build_xlsx(rows, loai)
    fname = f"bao-cao-kho-{'nhap' if loai == VOUCHER_NHAP else 'xuat'}.xlsx"
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
