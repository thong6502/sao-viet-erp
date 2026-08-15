"""Router CÔNG KHAI (KHÔNG đăng nhập) — trang tra kho khi quét tem QR dán kệ.

Chỉ trả dữ liệu vị trí/tồn tối thiểu, TUYỆT ĐỐI không giá vốn/đơn giá. Mã trong QR là chữ
ký HMAC (services/qr_token) nên không dò id tuần tự được. Không dùng require_permission —
đây là router công khai DUY NHẤT của phân hệ kho.
"""
from __future__ import annotations

import mimetypes
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.stock_voucher import VOUCHER_POSTED, StockVoucher, StockVoucherLine
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.stock_lot_repo import StockLotRepository
from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from ..schemas.stock import PublicScanLot, PublicScanMove, PublicScanOut
from ..services.qr_token import verify_scan
from ..services.vat_lieu_kho_service import VatLieuKhoService
from ..storage import StorageFileNotFound, get_storage, is_safe_key, key_from_url

router = APIRouter(prefix="/api/public", tags=["public"])

Db = Annotated[Session, Depends(get_db)]


@router.get("/kho-scan", response_model=PublicScanOut)
def public_kho_scan(db: Db, t: Annotated[str, Query(description="Mã QR đã ký")]) -> PublicScanOut:
    parsed = verify_scan(t)
    if parsed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mã QR không hợp lệ")
    kho_id, hang_loai, hang_id = parsed
    hang = (hang_loai, hang_id)

    dv_repo = DonViDoRepository(db)
    hang_svc = VatLieuKhoService(VatLieuKhoRepository(db), dv_repo)
    m = hang_svc.map_theo_cap([hang]).get(hang)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy vật tư")

    # `m.don_vi_gia` là MÃ đơn vị (to/cai/kem…); tra danh mục để hiện TÊN có dấu (tờ/cái/bản kẽm),
    # khớp với màn danh mục & báo cáo — nếu không QR sẽ hiện đơn vị không dấu.
    dv_ten = {d.ma: d.ten for d in dv_repo.all_active()}
    dvt_code = getattr(m, "don_vi_gia", None)

    kho = KhoHangRepository(db).get(kho_id)
    lots_repo = StockLotRepository(db)
    lots = lots_repo.list_lots(hang=hang, kho_id=kho_id, con_hang=False)

    # Lịch sử nhập/xuất gần đây (phiếu ĐÃ GHI SỔ) — CÔNG KHAI, TUYỆT ĐỐI không kèm tiền.
    moves_stmt = (
        select(StockVoucher.loai, StockVoucher.ngay, StockVoucher.ma, StockVoucherLine.so_luong)
        .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
        .where(
            StockVoucherLine.hang_loai == hang_loai,
            StockVoucherLine.hang_id == hang_id,
            StockVoucher.kho_id == kho_id,
            StockVoucher.trang_thai == VOUCHER_POSTED,
        )
        .order_by(StockVoucher.ngay.desc(), StockVoucher.id.desc())
        .limit(15)
    )

    return PublicScanOut(
        material_code=getattr(m, "ma", None),
        material_name=getattr(m, "ten", None),
        dvt=dv_ten.get(dvt_code, dvt_code),
        kho_ten=getattr(kho, "ten", None),
        on_hand=lots_repo.on_hand(hang, kho_id),
        # Có ảnh thì trả đường CÔNG KHAI (serve lại bằng chính token này) — không lộ key kho file.
        anh_url=(f"/api/public/vat-lieu-anh?t={quote(t, safe='')}"
                 if getattr(m, "anh_url", None) else None),
        lots=[
            PublicScanLot(
                ma_lo=lot.ma_lo,
                ngay_nhap=lot.ngay_nhap,
                hsd=lot.hsd,
                vi_tri=lot.vi_tri,
                sl_con_lai=lot.sl_con_lai,
            )
            for lot in lots
        ],
        history=[
            PublicScanMove(loai=loai, ngay=ngay, so_ct=ma, so_luong=float(sl or 0))
            for loai, ngay, ma, sl in db.execute(moves_stmt).all()
        ],
    )


@router.get("/vat-lieu-anh")
def public_vat_lieu_anh(db: Db, t: Annotated[str, Query(description="Mã QR đã ký")]) -> StreamingResponse:
    """Serve ẢNH minh hoạ vật tư CÔNG KHAI (không đăng nhập) — bảo vệ bằng chính token QR đã ký,
    chỉ trả ảnh đúng mặt hàng mà token trỏ tới. Không phơi key kho file, không dò id tuần tự."""
    parsed = verify_scan(t)
    if parsed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mã QR không hợp lệ")
    _kho_id, hang_loai, hang_id = parsed
    hang = (hang_loai, hang_id)

    hang_svc = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    m = hang_svc.map_theo_cap([hang]).get(hang)
    key = key_from_url(getattr(m, "anh_url", None) if m else None)
    if not key or not is_safe_key(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có ảnh")
    try:
        stream, size, content_type = get_storage().open_stream(key)
    except StorageFileNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy ảnh") from None

    headers = {"Cache-Control": "public, max-age=300"}
    if size is not None:
        headers["Content-Length"] = str(size)
    media = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
    return StreamingResponse(stream, media_type=media, headers=headers)
