"""Seed DEMO cho **Nhà cung cấp** + **Kho**: làm cho hai màn này có số thật.

- Mỗi mặt hàng trong danh mục (Giấy + Vật tư) được NHIỀU nhà cung cấp báo giá (lệch nhau) ⇒ bảng
  so giá của màn NCC mới có cái để so.
- Mỗi mặt hàng có lô tồn ở kho + ngưỡng tồn (đủ / cần mua) ⇒ màn Kho hiện tồn + đèn tín hiệu.

Nguyên tắc:
  · LẶP TRÊN MẶT HÀNG THẬT trong DB (`giay_nguyen` + `vat_tu_in_an`), tra theo bản ghi — KHÔNG
    hardcode id. Thêm/bớt mặt hàng ở danh mục là seeder tự bám theo.
  · Đơn vị của báo giá & lô = ĐƠN VỊ GỐC của mặt hàng (`don_vi_gia`); mặt hàng chưa chọn đơn vị
    thì bỏ qua (không đoán "kg").
  · "Ngẫu nhiên nhưng ổn định": số liệu sinh từ `crc32(khoá)` nên trông ngẫu nhiên mà chạy lại
    vẫn y hệt — không phụ thuộc PYTHONHASHSEED, không đẻ trùng.

Idempotent theo khoá tự nhiên: NCC theo tên, kho theo mã, lô theo `ma_lo`, ngưỡng theo bộ ba
(hang_loai, hang_id, kho_id). Chạy lại chỉ BÙ phần thiếu. KHÔNG đụng schema, không migration.

CHỦ Ý (chốt 2026-08-20): seed tồn cho MỌI mặt hàng, kể cả Ivory 350 & Duplex 300 — hai giấy mà
`seed_kh_vat_tu` để tồn=0 cho ca đỏ/vàng/về-muộn. Người dùng đã đồng ý màn Kế hoạch vật tư đổi
màu hai ca đó để đổi lấy màn Kho đầy đủ.
"""
from __future__ import annotations

import zlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.kho_hang import KhoHang
from .models.purchase import Supplier, SupplierItem
from .models.stock_lot import LOT_AVAILABLE, LOT_QC_WAIT, StockLot, StockThreshold
from .models.vat_lieu_kho import HANG_GIAY, HANG_VAT_TU, GiayNguyen, VatTuInAn


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jit(*parts) -> int:
    """Số giả-ngẫu-nhiên ỔN ĐỊNH theo khoá (crc32, không dính PYTHONHASHSEED)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode())


# Hệ số lệch giá giữa các NCC — bảng so giá cần chênh nhau mới có cái để so.
_FACTORS = (0.90, 0.95, 1.0, 1.04, 1.08, 1.12)

# Giá neo mặc định theo đơn vị (chỉ dùng khi danh mục để đơn giá = 0).
_ANCHOR_MAC_DINH = {"kg": 100_000, "kem": 100_000, "m2": 3_000}

# Khoảng LƯỢNG một lô theo (loại hàng, đơn vị): (nền, biên) → nền..nền+biên.
_LOT_QTY = {
    (HANG_GIAY, "kg"): (500, 1200),      # giấy tính theo cân — nhập cả kiện
    (HANG_VAT_TU, "kg"): (25, 60),       # mực / keo — thùng vài chục kg
    (HANG_VAT_TU, "kem"): (10, 35),      # bản kẽm — đếm theo tấm
    (HANG_VAT_TU, "m2"): (1500, 4500),   # màng cán — cuộn nghìn mét vuông
}
_LOT_QTY_MAC_DINH = (50, 150)

# Ngưỡng tồn theo (loại hàng, đơn vị): (cần mua khi ≤, dư khi >).
_THRESH = {
    (HANG_GIAY, "kg"): (300, 2500),
    (HANG_VAT_TU, "kg"): (15, 120),
    (HANG_VAT_TU, "kem"): (6, 60),
    (HANG_VAT_TU, "m2"): (1000, 8000),
}
_THRESH_MAC_DINH = (30, 300)

# ── Kho: giấy về KHO-GIAY, vật tư về KHO-VT (không đụng kho cũ "vsd"/"KHO-0001") ──
_KHOS = [
    {"ma": "KHO-GIAY", "ten": "Kho Giấy",
     "vi_tri": "Xưởng A — khu kệ giấy tờ", "ghi_chu": "Giấy nguyên khổ mua, xếp theo chủng loại."},
    {"ma": "KHO-VT", "ten": "Kho Vật tư & Mực",
     "vi_tri": "Xưởng A — kho hoá chất", "ghi_chu": "Mực, bản kẽm, màng cán, keo."},
]

# ── Nhà cung cấp. `covers` = nhóm hàng báo giá; `only_prefix` = lọc theo mã (NCC chuyên món). ──
#   Hai NCC đầu ("Giấy Vĩnh Tiến", "Vật tư ngành in Sài Gòn") đã do `seed_kh_vat_tu` tạo (rỗng
#   supplier_items) — ở đây chỉ BÙ báo giá cho chúng.
_SUPPLIERS = [
    {"name": "Giấy Vĩnh Tiến", "tax_code": "0301234567", "phone": "028 3765 4321",
     "email": "kinhdoanh@giayvinhtien.vn", "contact": "Anh Tuấn", "group": "giay",
     "address": "Lô 12 KCN Vĩnh Lộc, Bình Tân, TP.HCM", "credit_days": 30,
     "credit_limit": 500_000_000, "covers": ("giay",)},
    {"name": "Giấy Tân Mai", "tax_code": "0302456789", "phone": "028 3822 1177",
     "email": "sales@tanmaipaper.vn", "contact": "Chị Hương", "group": "giay",
     "address": "27 Nguyễn Văn Trỗi, Phú Nhuận, TP.HCM", "credit_days": 45,
     "credit_limit": 800_000_000, "covers": ("giay",)},
    {"name": "Giấy An Bình", "tax_code": "0303987654", "phone": "0274 3756 900",
     "email": "anbinh.paper@gmail.com", "contact": "Anh Dũng", "group": "giay",
     "address": "KCN Sóng Thần 1, Dĩ An, Bình Dương", "credit_days": 15,
     "credit_limit": 300_000_000, "covers": ("giay",)},
    {"name": "Vật tư ngành in Sài Gòn", "tax_code": "0309876543", "phone": "028 3833 0099",
     "email": "vattuin.sg@gmail.com", "contact": "Chị Lan", "group": "vat_tu",
     "address": "45 Lý Thường Kiệt, Q.10, TP.HCM", "credit_days": 15,
     "credit_limit": 200_000_000, "covers": ("vat_tu",)},
    {"name": "Mực in Toyo Việt Nam", "tax_code": "0304112233", "phone": "028 3948 5566",
     "email": "order@toyoink.com.vn", "contact": "Anh Khoa", "group": "vat_tu",
     "address": "Tầng 5, Etown 2, Cộng Hoà, Tân Bình, TP.HCM", "credit_days": 30,
     "credit_limit": 600_000_000, "covers": ("vat_tu",), "only_prefix": ("MUC", "MANG")},
    {"name": "Kẽm CTP Minh Khang", "tax_code": "0305221144", "phone": "028 3971 2020",
     "email": "minhkhang.ctp@gmail.com", "contact": "Anh Sơn", "group": "vat_tu",
     "address": "312 Âu Cơ, Tân Bình, TP.HCM", "credit_days": 20,
     "credit_limit": 250_000_000, "covers": ("vat_tu",), "only_prefix": ("KEM",)},
    {"name": "Hoá chất & Vật tư in Đại Phát", "tax_code": "0306778899", "phone": "0251 3866 345",
     "email": "daiphat.vt@gmail.com", "contact": "Chị Mai", "group": "vat_tu",
     "address": "KCN Biên Hoà 2, Đồng Nai", "credit_days": 30,
     "credit_limit": 400_000_000, "covers": ("vat_tu",)},
]


def _round_price(x: float) -> int:
    """Làm tròn giá cho gọn mắt: <10k → 100đ, <100k → 500đ, còn lại → 1.000đ."""
    x = max(0, x)
    step = 100 if x < 10_000 else (500 if x < 100_000 else 1_000)
    return int(round(x / step) * step)


def _catalog(db: Session) -> list[tuple[str, object]]:
    """Mọi mặt hàng gốc CÓ đơn vị gốc — bỏ mặt hàng chưa chọn đơn vị (không đoán 'kg')."""
    ra: list[tuple[str, object]] = []
    for g in db.execute(select(GiayNguyen).order_by(GiayNguyen.ma)).scalars():
        if g.don_vi_gia:
            ra.append((HANG_GIAY, g))
    for v in db.execute(select(VatTuInAn).order_by(VatTuInAn.ma)).scalars():
        if v.don_vi_gia:
            ra.append((HANG_VAT_TU, v))
    return ra


def _covers(sup: dict, item, hang_loai: str) -> bool:
    if hang_loai not in sup["covers"]:
        return False
    pref = sup.get("only_prefix")
    return not pref or any(item.ma.startswith(p) for p in pref)


def _ensure_suppliers(db: Session) -> dict[str, Supplier]:
    co = {s.name: s for s in db.execute(select(Supplier)).scalars()}
    for spec in _SUPPLIERS:
        s = co.get(spec["name"])
        if s is None:
            s = Supplier(
                name=spec["name"], tax_code=spec["tax_code"], phone=spec["phone"],
                email=spec["email"], contact_name=spec["contact"],
                supplier_group=spec["group"], address=spec["address"],
                credit_days=spec["credit_days"], credit_limit=spec["credit_limit"],
                payment_terms=f"Công nợ {spec['credit_days']} ngày kể từ ngày hóa đơn",
                note="Nhà cung cấp demo — dữ liệu mẫu.",
            )
            db.add(s)
            co[spec["name"]] = s
    db.flush()
    return co


def _ensure_supplier_items(db: Session, sups: dict[str, Supplier],
                           catalog: list[tuple[str, object]]) -> int:
    """Mỗi NCC báo giá cho các mặt hàng nó phủ; giá lệch nhau theo hệ số ổn định."""
    n = 0
    for spec in _SUPPLIERS:
        s = sups[spec["name"]]
        co = {(it.hang_loai, it.hang_id) for it in s.items}
        for hang_loai, item in catalog:
            if not _covers(spec, item, hang_loai):
                continue
            if (hang_loai, item.id) in co:
                continue
            unit = item.don_vi_gia
            anchor = float(item.don_gia or 0) or _ANCHOR_MAC_DINH.get(unit, 50_000)
            gia = _round_price(anchor * _FACTORS[_jit(spec["name"], item.ma) % len(_FACTORS)])
            vat = 8 if _jit("vat", spec["name"], item.ma) % 2 else 10
            db.add(SupplierItem(
                supplier_id=s.id, hang_loai=hang_loai, hang_id=item.id,
                item_name=item.ten, unit=unit, unit_price=gia, vat_percent=vat,
                is_active=True,
            ))
            co.add((hang_loai, item.id))
            n += 1
    db.flush()
    return n


def _ensure_khos(db: Session) -> dict[str, KhoHang]:
    co = {k.ma: k for k in db.execute(select(KhoHang)).scalars()}
    for spec in _KHOS:
        if spec["ma"] not in co:
            k = KhoHang(ma=spec["ma"], ten=spec["ten"],
                        vi_tri=spec["vi_tri"], ghi_chu=spec["ghi_chu"])
            db.add(k)
            co[spec["ma"]] = k
    db.flush()
    return co


def _nguon_ncc(item, hang_loai: str) -> list[str]:
    """Tên các NCC phủ mặt hàng — để gán trường `ncc` (chuỗi) cho lô."""
    return [sp["name"] for sp in _SUPPLIERS if _covers(sp, item, hang_loai)]


def _ensure_lots(db: Session, khos: dict[str, KhoHang],
                 catalog: list[tuple[str, object]], hom_nay: date) -> int:
    co = {r.ma_lo for r in db.execute(select(StockLot.ma_lo)).all()}  # type: ignore[arg-type]
    n = 0
    for hang_loai, item in catalog:
        unit = item.don_vi_gia
        kho = khos["KHO-GIAY" if hang_loai == HANG_GIAY else "KHO-VT"]
        anchor = float(item.don_gia or 0) or _ANCHOR_MAC_DINH.get(unit, 50_000)
        nen, bien = _LOT_QTY.get((hang_loai, unit), _LOT_QTY_MAC_DINH)
        nccs = _nguon_ncc(item, hang_loai) or ["Nhà cung cấp lẻ"]
        # Giấy & mực nhập 2 đợt (lô đích danh); còn lại 1 đợt.
        so_lo = 2 if (hang_loai == HANG_GIAY or unit == "kg") else 1
        buoc = 25 if unit == "kg" else (50 if unit == "m2" else 1)
        for seq in range(so_lo):
            ma_lo = f"LOT-DEMO-{item.ma}-{seq + 1}"
            if ma_lo in co:
                continue
            sl = nen + _jit(item.ma, seq, "sl") % bien
            sl = round(sl / buoc) * buoc or buoc
            # Lô cũ (seq 0) đã tiêu một phần; lô mới nhất còn nguyên.
            con = sl if seq == so_lo - 1 else round(sl * (0.4 + _jit(item.ma, seq, "c") % 40 / 100), 2)
            ngay = hom_nay - timedelta(days=3 + (so_lo - 1 - seq) * 30 + _jit(item.ma, seq, "d") % 20)
            gia = _round_price(anchor * (0.9 + _jit(item.ma, seq, "g") % 20 / 100))
            db.add(StockLot(
                ma_lo=ma_lo, hang_loai=hang_loai, hang_id=item.id, kho_id=kho.id,
                ngay_nhap=ngay, ncc=nccs[_jit(item.ma, seq) % len(nccs)],
                don_gia_nhap=gia, sl_ban_dau=sl, sl_con_lai=con, trang_thai=LOT_AVAILABLE,
            ))
            co.add(ma_lo)
            n += 1
        # Rải vài lô CHỜ KCS cho màn Kho có trạng thái ngoài 'khả dụng'.
        if _jit(item.ma) % 5 == 0:
            ma_qc = f"LOT-DEMO-{item.ma}-QC"
            if ma_qc not in co:
                sl_qc = round((nen * 0.3) / buoc) * buoc or buoc
                db.add(StockLot(
                    ma_lo=ma_qc, hang_loai=hang_loai, hang_id=item.id, kho_id=kho.id,
                    ngay_nhap=hom_nay - timedelta(days=1), ncc=nccs[0],
                    don_gia_nhap=_round_price(anchor), sl_ban_dau=sl_qc, sl_con_lai=sl_qc,
                    trang_thai=LOT_QC_WAIT,
                ))
                co.add(ma_qc)
                n += 1
    db.flush()
    return n


def _ensure_thresholds(db: Session, khos: dict[str, KhoHang],
                       catalog: list[tuple[str, object]]) -> int:
    co = {
        (t.hang_loai, t.hang_id, t.kho_id)
        for t in db.execute(select(StockThreshold)).scalars()
    }
    n = 0
    for hang_loai, item in catalog:
        unit = item.don_vi_gia
        kho = khos["KHO-GIAY" if hang_loai == HANG_GIAY else "KHO-VT"]
        if (hang_loai, item.id, kho.id) in co:
            continue
        ton, toi_da = _THRESH.get((hang_loai, unit), _THRESH_MAC_DINH)
        # Lệch nhẹ mỗi mặt hàng cho tự nhiên.
        ton = round(ton * (0.9 + _jit(item.ma, "nt") % 20 / 100))
        toi_da = round(toi_da * (0.95 + _jit(item.ma, "td") % 20 / 100))
        db.add(StockThreshold(
            hang_loai=hang_loai, hang_id=item.id, kho_id=kho.id,
            nguong_ton=ton, nguong_toi_da=toi_da, canh_bao=True,
        ))
        co.add((hang_loai, item.id, kho.id))
        n += 1
    db.flush()
    return n


def seed_kho_ncc(db: Session) -> None:
    """Bù báo giá NCC + lô tồn + ngưỡng cho mọi mặt hàng trong danh mục. Idempotent."""
    catalog = _catalog(db)
    if not catalog:
        return  # chưa có danh mục giấy/vật tư → không có gì để treo NCC/kho
    hom_nay = _utcnow().date()
    sups = _ensure_suppliers(db)
    _ensure_supplier_items(db, sups, catalog)
    khos = _ensure_khos(db)
    _ensure_lots(db, khos, catalog, hom_nay)
    _ensure_thresholds(db, khos, catalog)
    db.commit()
