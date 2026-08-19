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

import json

from ..db import get_db
from ..deps import require_permission
from ..models.kho_hang import KhoHang
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
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.kho_khoa_so_repo import KhoKhoaSoRepository
from ..repositories.user_repo import UserRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..services.vat_lieu_kho_service import VatLieuKhoService
from ..schemas.stock import (
    BaoCaoChuyenKhoPage,
    BaoCaoChuyenKhoRow,
    BaoCaoKhoPage,
    BaoCaoKhoRow,
    KhoaSoKyRow,
    KhoExportLogRow,
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
        select(StockVoucher, StockVoucherLine, StockRequest, KhoHang, StockLot)
        .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
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

    results = db.execute(stmt).all()
    # Mã / tên / ĐVT mặt hàng tra từ DANH MỤC GỐC theo (hang_loai, hang_id) — bảng `materials` đã bỏ.
    hang_svc = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    hang_map = hang_svc.map_theo_cap(
        list({(ln.hang_loai, ln.hang_id) for _v, ln, _req, _kho, _lot in results})
    )
    # ĐVT trên báo cáo hiện TÊN có dấu (tờ · cái · bản kẽm) thay vì MÃ ascii (to · cai · kem) —
    # `mh.don_vi_gia` là MÃ đơn vị; tra danh mục `don_vi_do` để đổi sang tên hiển thị (khớp danh mục).
    dv_ten = {d.ma: d.ten for d in DonViDoRepository(db).all_active()}

    rows: list[BaoCaoKhoRow] = []
    for v, ln, req, kho, lot in results:
        mh = hang_map.get((ln.hang_loai, ln.hang_id))
        # Lọc theo ngày GHI SỔ ở Python (tránh func.date lệ thuộc dialect + parse tz của SQLite).
        d = v.ghi_so_luc.date() if v.ghi_so_luc else None
        if tu and (d is None or d < tu):
            continue
        if den and (d is None or d > den):
            continue
        # SỐ LƯỢNG · ĐƠN GIÁ · THÀNH TIỀN đều theo ĐƠN VỊ GỐC — khớp tồn kho + ĐVT danh mục và
        # khớp cách tính giá vốn phiếu (`cost_of`): NHẬP quy đơn giá về ĐV gốc, XUẤT lấy giá vốn
        # lô (vốn đã theo ĐV gốc) × `sl_goc`. Nhân nhầm `so_luong` là lệch đúng bằng hệ số quy đổi.
        qty = float(ln.sl_goc or 0)
        if v.loai == VOUCHER_NHAP:
            so = float(ln.so_luong or 0)
            price = round(float(ln.don_gia) * so / qty) if (qty and ln.don_gia is not None) else None
        else:
            price = int(lot.don_gia_nhap) if (lot is not None and lot.don_gia_nhap is not None) else None
        row = BaoCaoKhoRow(
            voucher_id=v.id,
            ngay_ghi_so=d,
            ngay_ct=v.ngay,
            so_ct=v.ma,
            loai=v.loai,
            loai_kho=req.loai_kho if req else None,
            ma_hang=getattr(mh, "ma", None),
            ten_hang=getattr(mh, "ten", None),
            dvt=dv_ten.get(getattr(mh, "don_vi_gia", None), getattr(mh, "don_vi_gia", None)),
            so_luong=qty,
            don_gia=price,
            thanh_tien=round(price * qty) if price is not None else None,
            kho_id=v.kho_id,
            kho_ten=getattr(kho, "ten", None),
            dieu_chuyen=bool(getattr(v, "dieu_chuyen", False)),
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


# --- Điều chuyển kho: 1 dòng/mặt hàng (Xuất tại kho → Nhập tại kho) --------------

def _chuyen_kho_rows(
    db: Session, *, tu: date | None, den: date | None, kho_id: int | None, q: str | None = None,
) -> list[BaoCaoChuyenKhoRow]:
    """Dòng điều chuyển ĐÃ GHI SỔ: mỗi dòng phiếu NHẬP đích (đại diện điều chuyển) → gộp kho nguồn
    (Xuất tại kho) + kho đích (Nhập tại kho) trên cùng 1 dòng, giá vốn chốt từ nguồn."""
    ql = (q or "").strip().lower()
    stmt = (
        select(StockVoucher, StockVoucherLine, StockRequest, KhoHang)
        .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
        .join(StockRequest, StockRequest.id == StockVoucher.request_id, isouter=True)
        .join(KhoHang, KhoHang.id == StockVoucher.kho_id, isouter=True)  # kho ĐÍCH (nhập về)
        .where(
            StockVoucher.trang_thai == VOUCHER_POSTED,
            StockVoucher.dieu_chuyen.is_(True),
            StockVoucher.loai == VOUCHER_NHAP,  # vế NHẬP đích = đại diện cho cả điều chuyển
        )
        .order_by(StockVoucher.ghi_so_luc, StockVoucher.id, StockVoucherLine.id)
    )
    results = db.execute(stmt).all()
    # Tên kho NGUỒN (Xuất tại kho) tra từ `stock_requests.kho_nguon_id` — 1 lượt, tránh N+1.
    kho_repo = KhoHangRepository(db)
    nguon_map = {
        kid: getattr(kho_repo.get(kid), "ten", None)
        for kid in {req.kho_nguon_id for _v, _ln, req, _k in results if req and req.kho_nguon_id}
    }
    hang_svc = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    hang_map = hang_svc.map_theo_cap(
        list({(ln.hang_loai, ln.hang_id) for _v, ln, _req, _k in results})
    )
    dv_ten = {d.ma: d.ten for d in DonViDoRepository(db).all_active()}

    rows: list[BaoCaoChuyenKhoRow] = []
    for v, ln, req, kho in results:
        mh = hang_map.get((ln.hang_loai, ln.hang_id))
        d = v.ghi_so_luc.date() if v.ghi_so_luc else None
        if tu and (d is None or d < tu):
            continue
        if den and (d is None or d > den):
            continue
        nguon_id = getattr(req, "kho_nguon_id", None) if req else None
        # Lọc theo kho: giữ điều chuyển LIÊN QUAN kho này (xuất khỏi hoặc nhập vào).
        if kho_id and kho_id not in (v.kho_id, nguon_id):
            continue
        # SL · đơn giá vốn theo ĐƠN VỊ GỐC (khớp tồn + cách tính nhập): don_gia quy về đv gốc.
        qty = float(ln.sl_goc or 0)
        so = float(ln.so_luong or 0)
        price = round(float(ln.don_gia) * so / qty) if (qty and ln.don_gia is not None) else None
        row = BaoCaoChuyenKhoRow(
            voucher_id=v.id,
            ngay_ghi_so=d,
            ngay_ct=v.ngay,
            so_ct=v.ma,
            ma_hang=getattr(mh, "ma", None),
            ten_hang=getattr(mh, "ten", None),
            dvt=dv_ten.get(getattr(mh, "don_vi_gia", None), getattr(mh, "don_vi_gia", None)),
            so_luong=qty,
            don_gia_von=price,
            tien_von=round(price * qty) if price is not None else None,
            kho_xuat_ten=nguon_map.get(nguon_id),
            kho_nhap_ten=getattr(kho, "ten", None),
            dien_giai=v.ghi_chu or (req.ghi_chu if req else None),
        )
        if ql and not any(
            ql in (val or "").lower() for val in (row.so_ct, row.ma_hang, row.ten_hang)
        ):
            continue
        rows.append(row)
    return rows


@router.get("/bao-cao/chuyen-kho", response_model=BaoCaoChuyenKhoPage)
def bao_cao_chuyen_kho(
    db: Db,
    _: CloseBookUser,
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> BaoCaoChuyenKhoPage:
    rows = _chuyen_kho_rows(db, tu=tu, den=den, kho_id=kho_id, q=q)
    return BaoCaoChuyenKhoPage(items=rows, total=len(rows))


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
        ten=row.ten,
    )


@router.get("/khoa-so", response_model=list[KhoKhoaSoRow])
def get_khoa_so(db: Db, _: CloseBookUser) -> list[KhoKhoaSoRow]:
    """Lịch sử thao tác khóa/mở kỳ (mới nhất trước) — dùng cho tab Lịch sử + đối chiếu đang khóa."""
    return [_khoa_row(db, r) for r in KhoKhoaSoRepository(db).history()]


@router.get("/khoa-so/ky", response_model=list[KhoaSoKyRow])
def get_khoa_so_ky(db: Db, _: CloseBookUser) -> list[KhoaSoKyRow]:
    """Các KỲ CÒN đang khóa (đã gộp khoảng liền mạch) — cho tab 'Kỳ đã khóa' chọn nhanh + xuất."""
    kho_repo = KhoHangRepository(db)
    repo = KhoKhoaSoRepository(db)
    out: list[KhoaSoKyRow] = []
    for kho_id, tu, den, khoa_luc, ten in repo.locked_periods():
        kho = kho_repo.get(kho_id) if kho_id else None
        # Kỳ TOÀN KHO: liệt kê các kho đã MỞ RIÊNG trong kỳ (miễn trừ) để hiển thị "trừ: …".
        mien_tru: list[str] = []
        if kho_id is None:
            for kid in repo.exempted_khos(tu, den):
                k = kho_repo.get(kid)
                mien_tru.append(getattr(k, "ten", None) or f"Kho #{kid}")
        out.append(KhoaSoKyRow(
            kho_id=kho_id, kho_ten=getattr(kho, "ten", None),
            tu_ngay=tu, den_ngay=den, khoa_luc=khoa_luc, ten=ten, mien_tru=mien_tru,
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
    # KHÓA: TÊN kỳ không được TRÙNG tên một kỳ ĐANG KHÓA khác (so không phân biệt hoa/thường) —
    # chặn nhầm lẫn khi có nhiều kỳ. Bỏ trống thì không kiểm.
    if payload.hanh_dong == "khoa" and (payload.ten or "").strip():
        ten_norm = (payload.ten or "").strip().casefold()
        dang_dung = {(t[4] or "").strip().casefold() for t in repo.locked_periods() if t[4]}
        if ten_norm in dang_dung:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tên kỳ '{payload.ten.strip()}' đã dùng cho một kỳ đang khóa — đặt tên khác.",
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
        # KHÔNG cho mở VẮT QUA kẽ hở / ôm luôn kỳ cũ hơn: [tu_ngay, cutoff] phải LIỀN MẠCH đang khóa.
        # → muốn mở kỳ cũ thì phải mở kỳ mới hơn TRƯỚC (mở lần lượt từ đuôi về).
        run_start = repo.locked_run_start(payload.kho_id, cutoff)
        if payload.tu_ngay < run_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Khoảng mở vắt qua kỳ khác hoặc ngày chưa khóa — chỉ mở được phần ĐUÔI LIỀN MẠCH "
                    f"của kỳ đang khóa (đặt 'Từ ngày' ≥ {run_start.strftime('%d/%m/%Y')}). Muốn mở kỳ "
                    f"cũ hơn thì phải mở kỳ mới hơn ({run_start.strftime('%d/%m/%Y')}–"
                    f"{cutoff.strftime('%d/%m/%Y')}) TRƯỚC."
                ),
            )
    row = repo.add(
        kho_id=payload.kho_id, tu_ngay=payload.tu_ngay, den_ngay=payload.den_ngay,
        hanh_dong=payload.hanh_dong, nguoi_khoa_id=user.id,
        ten=((payload.ten or "").strip() or None) if payload.hanh_dong == "khoa" else None,
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


# Cột đúng thứ tự mẫu MISA "Chuyển kho" (Copy of Mau_chuyen_kho.xls — 36 cột).
_CHUYEN_HEADERS = [
    "Hiển thị trên sổ", "Hình thức chuyển kho", "Ngày chứng từ (*)", "Ngày hạch toán (*)",
    "Số chứng từ (*)", "Mẫu số hóa đơn", "Ký hiệu HĐ", "Hợp đồng KT số/Lệnh điều động", "Ngày",
    "Của", "Về việc/Diễn giải", "Đại lý/Đơn vị nhận", "Tên đại lý/Tên đơn vị nhận",
    "Mã số thuế đại lý/đơn vị nhận", "Người vận chuyển", "Tên người VC", "Hợp đồng số",
    "Phương tiện VC", "Mã hàng (*)", "Tên hàng", "Xuất tại kho (*)", "Địa chỉ kho xuất",
    "Nhập tại kho (*)", "Địa chỉ kho nhập", "Hàng hóa giữ hộ/bán hộ", "TK Nợ (*)", "TK Có (*)",
    "ĐVT", "Số lượng", "Đơn giá bán", "Thành tiền", "Đơn giá vốn", "Tiền vốn", "Số lô",
    "Hạn sử dụng", "Mã thống kê",
]


def _map_chuyen(r: BaoCaoChuyenKhoRow) -> dict:
    # CHỈ fill cột có sẵn dữ liệu (Xuất/Nhập tại kho, mặt hàng, SL, giá vốn); còn lại để TRỐNG cho
    # kế toán tự khai trong Excel/MISA ("Hình thức chuyển kho", đối tượng, vận chuyển, TK…).
    return {
        "Ngày chứng từ (*)": _fmt_date(r.ngay_ct),
        "Ngày hạch toán (*)": _fmt_date(r.ngay_ghi_so),
        "Số chứng từ (*)": r.so_ct,
        "Về việc/Diễn giải": r.dien_giai,
        "Mã hàng (*)": r.ma_hang,
        "Tên hàng": r.ten_hang,
        "Xuất tại kho (*)": r.kho_xuat_ten,
        "Nhập tại kho (*)": r.kho_nhap_ten,
        "ĐVT": r.dvt,
        "Số lượng": r.so_luong,
        "Đơn giá vốn": r.don_gia_von,
        "Tiền vốn": r.tien_von,
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


# --- Ghi NHẬT KÝ mỗi lần xuất Excel (vào audit_logs) → hiện ở tab "Lịch sử thao tác" ------------
_ACTION_EXPORT = "kho_export"


def _log_export(db: Session, user: User, *, loai_label: str,
                kho_id: int | None, tu: date | None, den: date | None) -> None:
    """Ghi 1 dòng nhật ký 'xuất Excel' (ai · lúc nào · báo cáo gì · kho · khoảng ngày)."""
    kho_ten = None
    if kho_id is not None:
        kho_ten = getattr(KhoHangRepository(db).get(kho_id), "ten", None)
    pham_vi = f"{loai_label} · {kho_ten or 'Tất cả kho'}"
    khoang = (
        f"{_fmt_date(tu) or '…'} – {_fmt_date(den) or '…'}" if (tu or den) else None
    )
    # Tên kỳ: xuất TOÀN BỘ (không lọc ngày) → "Toàn bộ"; khoảng ngày TRÙNG ĐÚNG một kỳ đã khóa
    # (cùng phạm vi kho) → tên kỳ đó; khoảng ngày lẻ (không trùng kỳ) → để trống.
    ten_ky: str | None = None
    if tu is None and den is None:
        ten_ky = "Toàn bộ"
    elif tu is not None and den is not None:
        for k_kho, k_tu, k_den, _luc, k_ten in KhoKhoaSoRepository(db).locked_periods():
            if k_tu == tu and k_den == den and k_kho == kho_id:
                ten_ky = k_ten or None
                break
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action=_ACTION_EXPORT,
        target=loai_label,
        detail=json.dumps(
            {"pham_vi": pham_vi, "khoang_ngay": khoang, "ten_ky": ten_ky},
            ensure_ascii=False,
        ),
    )


@router.get("/bao-cao/lich-su-export", response_model=list[KhoExportLogRow])
def get_lich_su_export(db: Db, _: CloseBookUser) -> list[KhoExportLogRow]:
    """Lịch sử các lần XUẤT EXCEL báo cáo kho (mới nhất trước) — gộp vào tab 'Lịch sử thao tác'."""
    users = UserRepository(db)
    out: list[KhoExportLogRow] = []
    for r in AuditLogRepository(db).list_by_action(_ACTION_EXPORT, limit=200):
        try:
            d = json.loads(r.detail or "{}")
        except (ValueError, TypeError):
            d = {}
        u = users.get_by_id(r.actor_user_id) if r.actor_user_id else None
        out.append(KhoExportLogRow(
            thoi_diem=r.created_at,
            loai=r.target or "Xuất Excel",
            pham_vi=d.get("pham_vi") or r.target or "—",
            khoang_ngay=d.get("khoang_ngay"),
            ten_ky=d.get("ten_ky"),
            nguoi_ten=getattr(u, "name", None),
        ))
    return out


@router.get("/bao-cao/export.xlsx")
def export_bao_cao(
    db: Db,
    user: CloseBookUser,
    loai: str = Query(pattern="^(NHAP|XUAT)$"),
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> Response:
    rows = _report_rows(db, tu=tu, den=den, kho_id=kho_id, loai=loai, q=q)
    content = _build_xlsx(rows, loai)
    _log_export(db, user, loai_label="Nhập kho" if loai == VOUCHER_NHAP else "Xuất kho",
                kho_id=kho_id, tu=tu, den=den)
    fname = f"bao-cao-kho-{'nhap' if loai == VOUCHER_NHAP else 'xuat'}.xlsx"
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _build_chuyen_xlsx(rows: list[BaoCaoChuyenKhoRow]) -> bytes:
    """Export điều chuyển theo mẫu MISA 'Chuyển kho' — chỉ fill cột có dữ liệu, còn lại để trống."""
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font

    template = _TEMPLATE_DIR / "chuyen_kho.xlsx"
    if template.exists():
        wb = load_workbook(template)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Chuyển kho"
        ws.append(_CHUYEN_HEADERS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
    for i, r in enumerate(rows):
        vals = _map_chuyen(r)
        for ci, h in enumerate(_CHUYEN_HEADERS, start=1):
            v = vals.get(h)
            if v is None:
                continue
            cell = ws.cell(row=2 + i, column=ci, value=v)
            if h in _MONEY_COLS:
                cell.number_format = "#,##0"
            elif h in _QTY_COLS:
                cell.number_format = "#,##0.###"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/bao-cao/chuyen-kho/export.xlsx")
def export_chuyen_kho(
    db: Db,
    user: CloseBookUser,
    tu: date | None = Query(default=None),
    den: date | None = Query(default=None),
    kho_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
) -> Response:
    rows = _chuyen_kho_rows(db, tu=tu, den=den, kho_id=kho_id, q=q)
    content = _build_chuyen_xlsx(rows)
    _log_export(db, user, loai_label="Chuyển kho", kho_id=kho_id, tu=tu, den=den)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="bao-cao-kho-chuyen-kho.xlsx"'},
    )
