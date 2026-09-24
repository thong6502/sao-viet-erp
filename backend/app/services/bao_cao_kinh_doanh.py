"""BÁO CÁO KINH DOANH theo khách hàng (24/09/2026).

Trả lời: *"Trong kỳ này khách X đặt những đơn nào, mỗi đơn gồm sản phẩm gì, đơn giá bao nhiêu,
cọc bao nhiêu và đã nhận cọc chưa?"* — xem trên màn và xuất Excel (một khách hoặc mọi khách).

Chủ chốt 24/09/2026:
  • Chỉ ĐƠN ĐÃ CHỐT (`ordered`). Nháp chưa phải doanh số, đơn hủy không còn là đơn.
  • Vào kỳ theo NGÀY CHỐT ĐƠN (`ordered_at`, giờ VN) — không theo ngày tạo.
  • Phạm vi theo ô quyền riêng `bao_cao_kinh_doanh`, cùng nghĩa với màn Đơn hàng bán: `own` = đơn
    do chính mình bán, `department` = cả phòng (và phòng con), `all` = toàn công ty.

Mọi con số đi qua ĐÚNG công thức của màn Đơn hàng bán (`OrderService._money`): tổng có VAT từ
`OrderRepository.money_sums`, cọc phải thu = % cọc × tổng có VAT, cọc đã nhận = Σ phiếu thu cọc
đã thu (`AccountingRepository.received_deposit_sums`). Tự viết lại công thức ở đây là hai màn hiện
hai con số cho cùng một đơn.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

_VN = timezone(timedelta(hours=7))


def _moc_utc(ngay: date) -> datetime:
    """0 giờ sáng ngày `ngay` GIỜ VN, đổi ra UTC — mốc so với `orders.ordered_at` (timestamptz)."""
    return datetime.combine(ngay, time.min, tzinfo=_VN).astimezone(timezone.utc)


def _ngay_vn(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:           # SQLite trong test trả datetime trần (đã là UTC)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_VN).date()


def lap_bao_cao(
    orders_repo, accounting_repo, *, tu_ngay: date, den_ngay: date, scope: str, actor,
    customer_id: int | None = None,
) -> dict:
    """Báo cáo `[tu_ngay, den_ngay]` (tính cả hai đầu, giờ VN), gom theo khách → đơn → dòng."""
    don = orders_repo.chot_trong_khoang(
        tu=_moc_utc(tu_ngay), den=_moc_utc(den_ngay + timedelta(days=1)),
        scope=scope, actor=actor, customer_id=customer_id,
    )
    ids = [o.id for o in don]
    tien = orders_repo.money_sums(ids)
    coc_nhan = accounting_repo.received_deposit_sums(ids)
    khach = orders_repo.khach_theo_ids({o.customer_id for o in don if o.customer_id})
    sale = orders_repo.ten_nguoi_dung({o.sale_user_id for o in don if o.sale_user_id})

    theo_khach: dict[int | None, dict] = {}
    for o in don:
        k = khach.get(o.customer_id) if o.customer_id else None
        muc = theo_khach.get(o.customer_id)
        if muc is None:
            muc = theo_khach[o.customer_id] = {
                "customer_id": o.customer_id,
                "ma": k.code if k else None,
                "ten": (k.name if k else None) or "(Không gắn khách hàng)",
                "don": [],
            }
        agg = tien.get(o.id, {})
        tong = int(agg.get("total") or 0)
        tong_vat = int(agg.get("total_with_vat") or 0)
        pct = float(o.deposit_pct) if o.deposit_pct else 0.0
        # Cùng công thức `OrderService._money` — xem đầu file.
        coc_phai = int(round(pct * tong_vat / 100)) if pct else 0
        coc_da = int(coc_nhan.get(o.id, 0))
        muc["don"].append({
            "order_id": o.id,
            "order_no": o.order_no,
            "ngay_chot": _ngay_vn(o.ordered_at),
            "sale": sale.get(o.sale_user_id) if o.sale_user_id else None,
            "po_khach": o.customer_po_no,
            "ngay_giao": o.delivery_committed_date,
            "tong": tong,
            "tong_vat": tong_vat,
            "coc_pct": pct,
            "coc_phai_thu": coc_phai,
            "coc_da_nhan": coc_da,
            "coc_con_thieu": max(0, coc_phai - coc_da),
            "dong": [
                {
                    "ten": (ln.description or "").strip(),
                    "so_luong": int(ln.qty or 0),
                    "dvt": ln.don_vi_tinh,
                    "don_gia": int(ln.unit_price_snapshot) if ln.unit_price_snapshot is not None else None,
                    "vat_pct": int(ln.vat_pct_estimate or 0),
                    "thanh_tien": int(ln.line_total) if ln.line_total is not None else None,
                }
                for ln in o.lines
            ],
        })

    _cot = ("tong", "tong_vat", "coc_phai_thu", "coc_da_nhan", "coc_con_thieu")
    ds = []
    for muc in theo_khach.values():
        for c in _cot:
            muc[c] = sum(d[c] for d in muc["don"])
        muc["so_don"] = len(muc["don"])
        ds.append(muc)
    # Khách xếp theo tên; dòng "không gắn khách" xuống cuối — cùng lối sổ công nợ.
    ds.sort(key=lambda m: (m["customer_id"] is None, (m["ten"] or "").lower()))
    return {
        "tu_ngay": tu_ngay,
        "den_ngay": den_ngay,
        "khach": ds,
        "tong": {
            "so_khach": len(ds),
            "so_don": sum(m["so_don"] for m in ds),
            **{c: sum(m[c] for m in ds) for c in _cot},
        },
    }
