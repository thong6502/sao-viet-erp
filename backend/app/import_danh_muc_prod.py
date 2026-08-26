"""Nạp DATA ĐA DẠNG cho "Cấu hình danh mục" trên PROD — chạy TRONG container.

    docker compose run --rm backend python -m app.import_danh_muc_prod

IDEMPOTENT theo `ma` (đơn vị/lý do theo mã hoặc cặp): chạy lại chỉ THÊM dòng còn thiếu, KHÔNG
đụng dòng đã có (kể cả dòng người dùng đã sửa tay). An toàn bấm nhiều lần.

Gồm: đơn vị bổ sung · chủng loại giấy · giấy nguyên · vật tư · máy (+ nhóm máy) · bù hao ·
công đoạn (nối bù hao + gắn tổ qua seed_san_xuat_org) · công việc khoán · khuôn · lý do & lỗi SX ·
và bù NCC + kho + lô tồn cho mọi giấy/vật tư có đơn vị (seed_kho_ncc).

KHÔNG gồm BẬC TAY NGHỀ (bộ đóng 5 bậc, giữ nguyên) và KHÔNG bật SEED_DEMO (không đẻ dữ liệu nghiệp
vụ mẫu). Danh mục NỀN (đơn vị/máy/công đoạn base) gọi thẳng seed function, cố ý bỏ qua cổng demo —
xem memory `don-vi-quy-doi-khong-gate-seed-demo`.

Công thức bám TỪ ĐIỂN BIẾN `services/bien_cong_thuc.py`:
  - Công đoạn `cong_thuc_gia`: KHÔNG có biến đơn giá → nhét số thẳng vào công thức.
  - Vật tư `cong_thuc_gia`: dùng `don_gia_vat_tu` (suy ngược ra lượng khi đặt đơn giá = 1).
  - Giấy `cong_thuc_luong`: dùng chung `_CT_LUONG_GIAY_CAN` (định lượng × khổ nguyên × tờ nguyên).
  - Máy `cong_thuc_luong`: lượng theo đơn vị tốc độ (máy N màu → `sl_vao * so_mau / N`).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models.bu_hao import BuHao
from .models.cong_doan import CongDoan
from .models.don_vi_do import DonViDo, DonViQuyDoi
from .models.khuon_be import KhuonBe
from .models.may_thiet_bi import MayThietBi
from .models.piece_work import PieceRate
from .models.san_xuat_ly_do import SanXuatLyDo
from .models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn
from .repositories.rbac_repo import DepartmentRepository
from .seed import seed_departments, seed_san_xuat_org
from .seed_kho_ncc import seed_kho_ncc
from .seed_rebuild import (
    _CT_LUONG_GIAY_CAN,
    seed_don_vi_do,
    seed_nhom_may,
    seed_rebuild_catalog,
)

# Tên nhóm máy (khớp `nhom_may.ten` — 5 mặc định + 4 nhóm MỚI script này thêm).
_IN, _INX, _CM, _BOI, _BE = "Máy in", "In ngoài", "Cán màng / UV", "Bồi", "Bế"
_CB, _XEN, _GAP, _DG = "Chế bản", "Xén", "Gấp / Dán", "Đóng gói"


# ---------------------------------------------------------------------------------------------
# Helper idempotent: chỉ thêm dòng có `ma` chưa tồn tại.
# ---------------------------------------------------------------------------------------------
def _ma_da_co(db: Session, model) -> set[str]:
    return set(db.execute(select(model.ma)).scalars())


def _them_thieu(db: Session, model, rows: list[dict]) -> int:
    co = _ma_da_co(db, model)
    moi = [model(**r) for r in rows if r["ma"] not in co]
    if moi:
        db.add_all(moi)
        db.commit()
    return len(moi)


# ---------------------------------------------------------------------------------------------
# 0) Đơn vị bổ sung: lít + ml (cho vật tư lỏng) — theo lối `seed_don_vi_do` (mã/cặp còn thiếu).
# ---------------------------------------------------------------------------------------------
_DON_VI_BO_SUNG = [
    ("lit", "lít", "the_tich", "Đơn vị đo chất lỏng (cồn, dầu bóng, hoá chất)."),
    ("ml", "ml", "the_tich", ""),
]
_QUY_DOI_BO_SUNG = [("lit", "ml", 1000)]  # 1 lít = 1.000 ml


def _import_don_vi_bo_sung(db: Session) -> int:
    co = {d.ma for d in db.execute(select(DonViDo)).scalars()}
    moi = [DonViDo(ma=ma, ten=ten, ho=ho, ghi_chu=gc or None)
           for ma, ten, ho, gc in _DON_VI_BO_SUNG if ma not in co]
    if moi:
        db.add_all(moi)
        db.commit()
    by_ma = {d.ma: d.id for d in db.execute(select(DonViDo)).scalars()}
    da_co = {(c.tu_id, c.den_id) for c in db.execute(select(DonViQuyDoi)).scalars()}
    caps = []
    for tu, den, hs in _QUY_DOI_BO_SUNG:
        tu_id, den_id = by_ma.get(tu), by_ma.get(den)
        if not tu_id or not den_id:
            continue
        if (tu_id, den_id) in da_co or (den_id, tu_id) in da_co:
            continue
        caps.append(DonViQuyDoi(tu_id=tu_id, den_id=den_id, he_so=hs))
    if caps:
        db.add_all(caps)
        db.commit()
    return len(moi)


# ---------------------------------------------------------------------------------------------
# 1) Chủng loại giấy (thêm 12 họ giấy ngoài 6 họ base).
# ---------------------------------------------------------------------------------------------
_CHUNG_LOAI = [
    dict(ma="ART", ten="Art (tráng phủ cao cấp)", mo_ta="Giấy tráng phủ 2 mặt, độ trắng cao."),
    dict(ma="COUCHE-MATT", ten="Couché mờ (matt)", mo_ta="Couché tráng mờ, không phản quang."),
    dict(ma="OFFSET-MAU", ten="Offset màu", mo_ta="Giấy in offset đã nhuộm màu."),
    dict(ma="KRAFT-TRANG", ten="Kraft trắng", mo_ta="Giấy kraft tẩy trắng, dai."),
    dict(ma="DECAL", ten="Decal (đế keo)", mo_ta="Giấy có lớp keo + đế, in tem nhãn."),
    dict(ma="CARBONLESS", ten="Carbonless (in liên/NCR)", mo_ta="Giấy tự nhân bản, in hoá đơn liên."),
    dict(ma="CALQUE", ten="Giấy can (calque)", mo_ta="Giấy mờ trong, in bản vẽ/thiệp."),
    dict(ma="FANCY", ten="Giấy mỹ thuật (fancy)", mo_ta="Giấy vân/ánh đặc biệt, cao cấp."),
    dict(ma="METALIZE", ten="Metalize (ánh kim)", mo_ta="Giấy phủ lớp ánh kim."),
    dict(ma="GHEP-MANG", ten="Giấy ghép màng (metpet)", mo_ta="Giấy ghép sẵn màng metpet."),
    dict(ma="BOI-CARTON", ten="Giấy bồi carton", mo_ta="Lớp mặt để bồi lên carton/sóng."),
    dict(ma="TESTLINER", ten="Testliner (mặt thùng sóng)", mo_ta="Lớp mặt của thùng carton sóng."),
]


def _import_chung_loai(db: Session) -> int:
    return _them_thieu(db, ChungLoaiGiay, _CHUNG_LOAI)


# ---------------------------------------------------------------------------------------------
# 2) Giấy nguyên (thêm 20 loại). don_vi_gia="kg", cong_thuc_luong = định lượng × khổ nguyên × tờ.
# ---------------------------------------------------------------------------------------------
def _giay(ma, ten, cl_ma, dai, rong, gsm, cal, tho, don_gia):
    return dict(ma=ma, ten=ten, _cl_ma=cl_ma, kho_dai=dai, kho_rong=rong, gsm=gsm,
                caliper_micron=cal, tho=tho, don_vi_gia="kg", don_gia=don_gia,
                cong_thuc_luong=_CT_LUONG_GIAY_CAN)


_GIAY = [
    _giay("COUCHE-100-79x109", "Couché 100 79×109", "COUCHE", 1090, 790, 100, 100, "canh_dai", 27000),
    _giay("COUCHE-200-65x86", "Couché 200 65×86", "COUCHE", 860, 650, 200, 205, "canh_dai", 29000),
    _giay("COUCHE-250-79x109", "Couché 250 79×109", "COUCHE", 1090, 790, 250, 255, "canh_dai", 30500),
    _giay("COUCHE-350-79x109", "Couché bìa 350 79×109", "COUCHE", 1090, 790, 350, 360, "canh_dai", 33000),
    _giay("COUCHE-MATT-150-79x109", "Couché mờ 150 79×109", "COUCHE-MATT", 1090, 790, 150, 155, "canh_dai", 28500),
    _giay("FORD-80-79x109", "Ford 80 79×109", "FORD", 1090, 790, 80, 105, "canh_dai", 26500),
    _giay("FORD-100-65x86", "Ford 100 65×86", "FORD", 860, 650, 100, 125, "canh_ngan", 27000),
    _giay("FORD-120-79x109", "Ford 120 79×109", "FORD", 1090, 790, 120, 150, "canh_dai", 28000),
    _giay("OFFSET-MAU-80-79x109", "Offset màu 80 79×109", "OFFSET-MAU", 1090, 790, 80, 105, "canh_dai", 27500),
    _giay("IVORY-250-79x109", "Ivory 250 79×109", "IVORY", 1090, 790, 250, 300, "canh_dai", 31000),
    _giay("IVORY-300-79x109", "Ivory 300 79×109", "IVORY", 1090, 790, 300, 370, "canh_dai", 31500),
    _giay("BRISTOL-230-79x109", "Bristol 230 79×109", "BRISTOL", 1090, 790, 230, 250, "canh_dai", 30000),
    _giay("BRISTOL-300-65x86", "Bristol 300 65×86", "BRISTOL", 860, 650, 300, 330, "canh_dai", 31000),
    _giay("DUPLEX-350-79x109", "Duplex 350 79×109", "DUPLEX", 1090, 790, 350, 450, "canh_dai", 18500),
    _giay("DUPLEX-400-79x109", "Duplex 400 79×109", "DUPLEX", 1090, 790, 400, 520, "canh_dai", 19000),
    _giay("KRAFT-125-79x109", "Kraft nâu 125 79×109", "KRAFT", 1090, 790, 125, 180, "canh_ngan", 15000),
    _giay("KRAFT-TRANG-150-79x109", "Kraft trắng 150 79×109", "KRAFT-TRANG", 1090, 790, 150, 200, "canh_ngan", 17000),
    _giay("ART-128-65x86", "Art 128 65×86", "ART", 860, 650, 128, 120, "canh_dai", 29000),
    _giay("DECAL-90-70x100", "Decal couché 90 70×100", "DECAL", 1000, 700, 90, 200, "canh_dai", 45000),
    _giay("FANCY-250-72x102", "Giấy mỹ thuật 250 72×102", "FANCY", 1020, 720, 250, 300, "canh_dai", 60000),
]


def _import_giay(db: Session) -> int:
    cl = {c.ma: c.id for c in db.execute(select(ChungLoaiGiay)).scalars()}
    co = _ma_da_co(db, GiayNguyen)
    moi = []
    for r in _GIAY:
        if r["ma"] in co:
            continue
        d = {k: v for k, v in r.items() if k != "_cl_ma"}
        d["chung_loai_giay_id"] = cl.get(r["_cl_ma"])
        moi.append(GiayNguyen(**d))
    if moi:
        db.add_all(moi)
        db.commit()
    return len(moi)


# ---------------------------------------------------------------------------------------------
# 3) Vật tư (thêm 20). Nhóm CÓ công thức tiền (mực/màng/dầu/kẽm) + nhóm phụ liệu giá phẳng.
#    Công thức mực: diện tích in × số tờ × đơn giá × ĐỊNH MỨC (kg/m²/màu). Đặt đơn giá=1 ⇒ ra lượng.
# ---------------------------------------------------------------------------------------------
_CT_MUC = "so_mau * dai_in * rong_in * don_gia_vat_tu * to_dau_vao * {dm}"   # nhiều màu
_CT_MUC_1 = "dai_in * rong_in * don_gia_vat_tu * to_dau_vao * {dm}"          # 1 màu named
_CT_PHU_MAT = "dai_in * rong_in * don_gia_vat_tu * to_sau_in"               # phủ theo diện tích tờ tốt
_CT_KEM = "so_kem * don_gia_vat_tu"                                          # theo số bản kẽm

_VAT_TU = [
    # --- Mực (kg, có công thức tiêu hao theo diện tích in) ---
    dict(ma="MUC-DEN", ten="Mực đen process", don_vi_gia="kg", don_gia=220000,
         cong_thuc_gia=_CT_MUC_1.format(dm=0.0003)),
    dict(ma="MUC-TRANG", ten="Mực trắng phủ nền", don_vi_gia="kg", don_gia=320000,
         cong_thuc_gia=_CT_MUC_1.format(dm=0.0004)),
    dict(ma="MUC-METALLIC", ten="Mực nhũ ánh kim (vàng/bạc)", don_vi_gia="kg", don_gia=480000,
         cong_thuc_gia=_CT_MUC_1.format(dm=0.0005)),
    dict(ma="MUC-UV", ten="Mực UV", don_vi_gia="kg", don_gia=350000,
         cong_thuc_gia=_CT_MUC.format(dm=0.00035)),
    # --- Màng / phủ (theo diện tích tờ tốt) ---
    dict(ma="MANG-MO", ten="Màng cán mờ", don_vi_gia="m2", don_gia=3500, cong_thuc_gia=_CT_PHU_MAT),
    dict(ma="MANG-METPET", ten="Màng metpet ánh kim", don_vi_gia="m2", don_gia=6000, cong_thuc_gia=_CT_PHU_MAT),
    dict(ma="MANG-NHAM-XUOC", ten="Màng nhám vân xước", don_vi_gia="m2", don_gia=5000, cong_thuc_gia=_CT_PHU_MAT),
    dict(ma="DAU-BONG-UV", ten="Dầu bóng UV", don_vi_gia="kg", don_gia=90000,
         cong_thuc_gia="dai_in * rong_in * don_gia_vat_tu * to_sau_in * 0.05"),
    # --- Kẽm (theo số bản) ---
    dict(ma="KEM-45", ten="Bản kẽm khổ 45", don_vi_gia="kem", don_gia=60000, cong_thuc_gia=_CT_KEM),
    dict(ma="KEM-88", ten="Bản kẽm khổ 88", don_vi_gia="kem", don_gia=150000, cong_thuc_gia=_CT_KEM),
    # --- Phụ liệu / hoá chất (mua theo tồn kho, KHÔNG có công thức tính trên phiếu) ---
    dict(ma="KEO-SUA", ten="Keo sữa dán hộp", don_vi_gia="kg", don_gia=38000,
         ghi_chu="Mua theo tồn, không tính vào phiếu tính giá."),
    dict(ma="KEO-NHIET", ten="Keo nhiệt đóng sách", don_vi_gia="kg", don_gia=52000,
         ghi_chu="Mua theo tồn."),
    dict(ma="CON-LAU", ten="Cồn lau máy", don_vi_gia="lit", don_gia=35000, ghi_chu="Vật tư tiêu hao xưởng."),
    dict(ma="HOA-CHAT-RUA", ten="Hoá chất rửa lô", don_vi_gia="lit", don_gia=42000, ghi_chu="Vật tư tiêu hao xưởng."),
    dict(ma="BOT-CHONG-DINH", ten="Bột chống dính (phun)", don_vi_gia="kg", don_gia=28000, ghi_chu="Vật tư tiêu hao xưởng."),
    dict(ma="CHI-KHAU", ten="Chỉ khâu sách", don_vi_gia="cuon", don_gia=15000, ghi_chu="Phụ liệu đóng sách."),
    dict(ma="GHIM-DONG", ten="Ghim đóng sách", don_vi_gia="hop", don_gia=25000, ghi_chu="Phụ liệu đóng sách."),
    dict(ma="DAY-RUT", ten="Dây rút quai xách túi", don_vi_gia="con", don_gia=500, ghi_chu="Phụ liệu túi giấy."),
    dict(ma="BANG-KEO", ten="Băng keo dán thùng", don_vi_gia="cuon", don_gia=12000, ghi_chu="Phụ liệu đóng gói."),
    dict(ma="NUT-BAM", ten="Nút bấm / đinh tán túi", don_vi_gia="con", don_gia=300, ghi_chu="Phụ liệu túi giấy."),
]


def _import_vat_tu(db: Session) -> int:
    return _them_thieu(db, VatTuInAn, _VAT_TU)


# ---------------------------------------------------------------------------------------------
# 4) Máy (thêm 14, gồm 4 nhóm máy MỚI). cong_thuc_luong = lượng theo đơn vị tốc độ.
# ---------------------------------------------------------------------------------------------
_CHUA_IN = {"nhip_giay_mm": 10, "le_hong_mm": 5, "duoi_thang_mau_mm": 5}


def _may(ma, ten, loai, toc_do, dv_toc_do, makeready, ct_luong, **extra):
    return dict(ma=ma, ten=ten, loai_may=loai, toc_do=toc_do, don_vi_toc_do=dv_toc_do,
                makeready_time_default=makeready, cong_thuc_luong=ct_luong, **extra)


_MAY = [
    # --- Máy in (thêm màu / khổ / máy số) ---
    _may("IN-11", "Máy 4 màu Komori 72×102", _IN, 8000, "to_gio", 35, "sl_vao * so_mau / 4",
         kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
         vung_in_rong=710, vung_in_dai=1010, kho_kem_rong=800, kho_kem_dai=1030, **_CHUA_IN),
    _may("IN-12", "Máy 1 màu Ryobi 52×74 (in đen/số)", _IN, 9000, "to_gio", 20, "sl_vao * so_mau / 1",
         kho_min_rong=320, kho_min_dai=420, kho_max_rong=520, kho_max_dai=740,
         vung_in_rong=510, vung_in_dai=730, kho_kem_rong=605, kho_kem_dai=745, **_CHUA_IN),
    _may("IN-13", "Máy in số HP Indigo 33×48", _IN, 3000, "to_gio", 10, "sl_vao * so_mau / 4",
         kho_min_rong=210, kho_min_dai=297, kho_max_rong=330, kho_max_dai=480,
         vung_in_rong=320, vung_in_dai=470, ghi_chu="Máy in kỹ thuật số, không cần kẽm."),
    # --- Chế bản (nhóm MỚI) — đơn vị tốc độ kẽm/giờ, lượng = số kẽm ---
    _may("CTP-01", "Máy ghi kẽm CTP Kodak 102", _CB, 25, "kem_gio", 5, "so_kem",
         kho_kem_rong=1030, kho_kem_dai=790, ghi_chu="Ghi kẽm trực tiếp (CTP)."),
    _may("CTP-02", "Máy phơi kẽm PS 74", _CB, 18, "kem_gio", 8, "so_kem",
         kho_kem_rong=745, kho_kem_dai=605, ghi_chu="Phơi kẽm qua phim (PS)."),
    # --- Xén (nhóm MỚI) ---
    _may("XEN-01", "Máy xén Polar 115", _XEN, 1500, "to_gio", 15, "sl_vao",
         kho_min_rong=100, kho_min_dai=100, kho_max_rong=1150, kho_max_dai=1150),
    _may("XEN-02", "Máy xén Polar 78", _XEN, 2000, "to_gio", 12, "sl_vao",
         kho_min_rong=80, kho_min_dai=80, kho_max_rong=780, kho_max_dai=780),
    # --- Gấp / Dán (nhóm MỚI) ---
    _may("GAP-01", "Máy gấp Stahl 78", _GAP, 6000, "to_gio", 25, "sl_vao",
         kho_min_rong=200, kho_min_dai=200, kho_max_rong=780, kho_max_dai=1100),
    _may("DAN-01", "Máy dán hộp tự động 650", _GAP, 5000, "to_gio", 30, "sl_vao",
         kho_min_rong=150, kho_min_dai=150, kho_max_rong=650, kho_max_dai=900),
    # --- Cán màng / UV (thêm spot UV) ---
    _may("CM-05", "Máy phủ UV cục bộ (spot) 720", _CM, 3000, "to_gio", 30, "sl_vao",
         kho_min_rong=280, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1020),
    # --- Bồi (thêm bồi phẳng) ---
    _may("BOI-05", "Máy bồi phẳng tự động 1100", _BOI, 2500, "to_gio", 20, "sl_vao",
         kho_min_rong=280, kho_min_dai=380, kho_max_rong=700, kho_max_dai=1000),
    # --- Bế (thêm bế phẳng tự động) ---
    _may("BE-07", "Máy bế phẳng tự động 1060", _BE, 5000, "to_gio", 30, "sl_vao",
         kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1060),
    # --- Đóng gói (nhóm MỚI) ---
    _may("DG-01", "Máy co màng đóng thùng 500", _DG, 1200, "to_gio", 10, "sl_vao",
         kho_min_rong=100, kho_min_dai=100, kho_max_rong=500, kho_max_dai=700),
]


def _import_may(db: Session) -> int:
    return _them_thieu(db, MayThietBi, _MAY)


# ---------------------------------------------------------------------------------------------
# 5) Bù hao (thêm 10 bảng). 6 bậc số tờ (theo SL) + 1 bậc % cho SL > 30.000.
# ---------------------------------------------------------------------------------------------
_SL_BAC = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]


def _bac(sau_to: list[int], pct: float) -> list[dict]:
    b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"}
         for (t, d), v in zip(_SL_BAC, sau_to)]
    b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
    return b


_BU_HAO = [
    dict(ma="BH-CAN-MANG", ten="Cán màng", bac=_bac([30, 50, 80, 100, 120, 150], 0.8)),
    dict(ma="BH-UV", ten="Phủ UV", bac=_bac([50, 80, 100, 130, 160, 200], 1.0)),
    dict(ma="BH-BE-TU-DONG", ten="Bế tự động", bac=_bac([80, 120, 150, 200, 250, 300], 1.5)),
    dict(ma="BH-BE-TAY", ten="Bế tay", bac=_bac([50, 70, 100, 120, 150, 180], 1.2)),
    dict(ma="BH-GAP", ten="Gấp", bac=_bac([40, 60, 80, 100, 120, 150], 1.0)),
    dict(ma="BH-XEN", ten="Xén / cắt", bac=_bac([20, 30, 40, 50, 60, 80], 0.5)),
    dict(ma="BH-EP-KIM", ten="Ép kim / ép nhũ", bac=_bac([60, 90, 120, 150, 180, 220], 1.3)),
    dict(ma="BH-DECAL", ten="In decal", bac=_bac([180, 230, 280, 330, 380, 430], 2.0)),
    dict(ma="BH-IN-7-8", ten="In 7-8 màu", bac=_bac([300, 350, 400, 500, 550, 650], 3.0)),
    dict(ma="BH-DONG-CUON", ten="Đóng cuốn", bac=_bac([30, 40, 60, 80, 100, 120], 0.8)),
]


def _import_bu_hao(db: Session) -> int:
    return _them_thieu(db, BuHao, _BU_HAO)


# ---------------------------------------------------------------------------------------------
# 6) Công đoạn (thêm 20). pricing_basis=per_other, đơn giá NHÉT vào công thức (không có biến giá).
#    tra_bang → nối `bu_hao_id` sau khi bù hao đã có (bảng _LINK_BU_HAO).
# ---------------------------------------------------------------------------------------------
def _cd(ma, ten, nhom, ct, **extra):
    return dict(ma=ma, ten=ten, nhom=nhom, che_do_tinh="theo_san_luong",
                pricing_basis="per_other", cong_thuc_gia=ct, **extra)


_MAY_IN = [_IN, _INX]
_CONG_DOAN = [
    # --- Chế bản (không đơn vị dòng giấy; kieu_bu_hao khong) ---
    _cd("CD-1001", "Phơi kẽm PS", "prepress", "so_kem * 55000",
        nhom_may_cho_phep=[_CB], cong_thuc_san_luong="so_kem", run_rate=55000),
    _cd("CD-1002", "Bình bài điện tử", "prepress", "so_mau * 25000",
        nhom_may_cho_phep=[_CB], run_rate=25000),
    _cd("CD-1003", "Xuất film / ghi phim", "prepress", "so_kem * 40000",
        nhom_may_cho_phep=[_CB], cong_thuc_san_luong="so_kem", run_rate=40000),
    # --- In (đơn vị to→to; kieu_bu_hao tra_bang → nối mã bù hao) ---
    _cd("CD-1004", "In offset 1 mặt (1-2 màu)", "print", "to_dau_vao * so_mat * 300",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=_MAY_IN, don_vi_vao="to", don_vi_ra="to", run_rate=300),
    _cd("CD-1005", "In offset 4 màu", "print", "to_dau_vao * so_mat * 380",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=_MAY_IN, don_vi_vao="to", don_vi_ra="to", run_rate=380),
    _cd("CD-1006", "In offset 5-6 màu", "print", "to_dau_vao * so_mat * 450",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=_MAY_IN, don_vi_vao="to", don_vi_ra="to", run_rate=450),
    _cd("CD-1007", "In UV (mực UV)", "print", "to_dau_vao * so_mat * 520",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=[_IN], don_vi_vao="to", don_vi_ra="to", run_rate=520),
    _cd("CD-1008", "In decal", "print", "to_dau_vao * so_mat * 600",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=[_IN], don_vi_vao="to", don_vi_ra="to", run_rate=600),
    # --- Gia công máy (co_dinh / tra_bang) ---
    _cd("CD-1009", "Cán màng mờ", "finishing",
        "max(dai_in * rong_in * 10000 * so_mat * to_dau_vao * 2.0, 100000)",
        kieu_bu_hao="co_dinh", so_to_bu_hao=50, nhom_may_cho_phep=[_CM],
        don_vi_vao="to", don_vi_ra="to", run_rate=2.0, min_charge=100000),
    _cd("CD-1010", "Phủ UV toàn phần", "finishing",
        "max(dai_in * rong_in * 10000 * to_dau_vao * 1.8, 90000)",
        kieu_bu_hao="co_dinh", so_to_bu_hao=40, nhom_may_cho_phep=[_CM],
        don_vi_vao="to", don_vi_ra="to", run_rate=1.8, min_charge=90000),
    _cd("CD-1011", "Phủ UV cục bộ (spot)", "finishing",
        "max(dai_in * rong_in * 10000 * to_dau_vao * 3.5, 200000)",
        kieu_bu_hao="co_dinh", so_to_bu_hao=60, nhom_may_cho_phep=[_CM],
        don_vi_vao="to", don_vi_ra="to", run_rate=3.5, min_charge=200000),
    _cd("CD-1012", "Bồi carton phẳng", "finishing", "to_dau_vao * 350",
        kieu_bu_hao="co_dinh", so_to_bu_hao=50, nhom_may_cho_phep=[_BOI],
        don_vi_vao="to", don_vi_ra="to", run_rate=350),
    _cd("CD-1013", "Gấp máy", "finishing", "to_dau_vao * 120",
        kieu_bu_hao="tra_bang", nhom_may_cho_phep=[_GAP],
        don_vi_vao="to", don_vi_ra="to", run_rate=120),
    _cd("CD-1014", "Xén thành phẩm (máy)", "finishing", "to_dau_vao * 80",
        kieu_bu_hao="co_dinh", so_to_bu_hao=20, nhom_may_cho_phep=[_XEN],
        don_vi_vao="to", don_vi_ra="con", run_rate=80),
    _cd("CD-1015", "Bế tự động", "finishing", "to_dau_vao * 300",
        kieu_bu_hao="co_dinh", so_to_bu_hao=30, requires_tooling=True, tooling_type="khuon_be",
        nhom_may_cho_phep=[_BE], don_vi_vao="to", don_vi_ra="con", run_rate=300),
    _cd("CD-1016", "Ép nhũ (khuôn ép)", "finishing", "so_luong * 350",
        kieu_bu_hao="co_dinh", so_to_bu_hao=50, requires_tooling=True, tooling_type="khuon_ep",
        nhom_may_cho_phep=[_BE], don_vi_vao="to", don_vi_ra="to", run_rate=350),
    # --- Khoán tay (nhom_may = None → không ràng buộc máy; ghi khoán theo NGƯỜI) ---
    _cd("CD-1017", "Gấp tay", "finishing", "so_luong * 30",
        khoan_ghi_theo="nguoi", don_vi_vao="to", don_vi_ra="cai", run_rate=30),
    _cd("CD-1018", "Dán hộp thủ công", "finishing", "so_luong * 120",
        khoan_ghi_theo="nguoi", don_vi_vao="to", don_vi_ra="cai", run_rate=120),
    _cd("CD-1019", "Đóng cuốn (keo nhiệt)", "finishing", "so_luong * 200",
        kieu_bu_hao="tra_bang", khoan_ghi_theo="nguoi", don_vi_vao="to", don_vi_ra="cai", run_rate=200),
    _cd("CD-1020", "Luồn dây / xỏ quai túi", "finishing", "so_luong * 80",
        khoan_ghi_theo="nguoi", don_vi_vao="to", don_vi_ra="cai", run_rate=80),
]

# Công đoạn tra_bang → mã bù hao mặc định (nối sau khi cả hai đã có).
_LINK_BU_HAO = [
    ("CD-1004", "BH-IN-1-2"), ("CD-1005", "BH-IN-3-4"), ("CD-1006", "BH-IN-5"),
    ("CD-1007", "BH-IN-3-4"), ("CD-1008", "BH-DECAL"), ("CD-1013", "BH-GAP"),
    ("CD-1019", "BH-DONG-CUON"),
]


def _import_cong_doan(db: Session) -> int:
    n = _them_thieu(db, CongDoan, _CONG_DOAN)
    # Nối bù hao cho công đoạn tra_bang chưa có bu_hao_id (idempotent).
    bh = {b.ma: b.id for b in db.execute(select(BuHao)).scalars()}
    doi = False
    for cd_ma, bh_ma in _LINK_BU_HAO:
        cd = db.execute(select(CongDoan).where(CongDoan.ma == cd_ma)).scalars().first()
        if cd is not None and cd.kieu_bu_hao == "tra_bang" and cd.bu_hao_id is None and bh.get(bh_ma):
            cd.bu_hao_id = bh[bh_ma]
            doi = True
    if doi:
        db.commit()
    return n


# ---------------------------------------------------------------------------------------------
# 7) Công việc khoán (piece_rates). `unit` = CHỮ đơn vị (khớp `don_vi_do.ten`) để khoán quy đổi.
#    department_id tra theo tên TỔ (sau seed_san_xuat_org). `ma` KHÔNG unique ở DB → tự kiểm.
# ---------------------------------------------------------------------------------------------
# (ma, ten, tên TỔ, group_name, đơn vị (ten), đơn giá, công thức lượng | None)
_KHOAN = [
    ("KH-1001", "Canh máy in", "Tổ In offset", "to_in", "lượt", 50000, None),
    ("KH-1002", "In offset (khoán tờ)", "Tổ In offset", "to_in", "tờ", 8, "to_dau_vao"),
    ("KH-1003", "Bình bài", "Tổ Chế bản", "to_che_ban", "bài in", 30000, None),
    ("KH-1004", "Ghi kẽm", "Tổ Chế bản", "to_che_ban", "bản kẽm", 25000, "so_kem"),
    ("KH-1005", "Cán màng (khoán tờ)", "Tổ Cán màng", "to_can_mang", "tờ", 5, "to_sau_in"),
    ("KH-1006", "Phủ UV (khoán tờ)", "Tổ Cán màng", "to_can_mang", "tờ", 6, "to_sau_in"),
    ("KH-1007", "Bế thủ công", "Tổ Bế & Xén", "to_be_xen", "tờ", 15, "to_dau_vao"),
    ("KH-1008", "Xén định hình", "Tổ Bế & Xén", "to_be_xen", "tờ", 10, "to_dau_vao"),
    ("KH-1009", "Bóc bế / bóc rìa", "Tổ Bế & Xén", "to_be_xen", "con", 2, "so_tp"),
    ("KH-1010", "Gấp tay", "Tổ Đóng gói", "to_dong_goi", "cái", 30, "so_luong"),
    ("KH-1011", "Dán hộp", "Tổ Đóng gói", "to_dong_goi", "cái", 120, "so_luong"),
    ("KH-1012", "Đóng cuốn keo nhiệt", "Tổ Đóng gói", "to_dong_goi", "cuốn", 200, "so_luong"),
    ("KH-1013", "Vào bìa / bắt tay sách", "Tổ Đóng gói", "to_dong_goi", "cuốn", 150, "so_luong"),
    ("KH-1014", "Luồn dây / xỏ quai", "Tổ Đóng gói", "to_dong_goi", "cái", 80, "so_luong"),
    ("KH-1015", "Dán tem / dán decal", "Tổ Đóng gói", "to_dong_goi", "con", 2, "so_tp"),
    ("KH-1016", "Đếm & vô lốc", "Tổ Đóng gói", "to_dong_goi", "cái", 5, "so_luong"),
    ("KH-1017", "Đóng gói thùng", "Tổ Đóng gói", "to_dong_goi", "thùng", 3000, None),
    ("KH-1018", "Kiểm đếm giao hàng", "Tổ Đóng gói", "to_dong_goi", "cái", 2, "so_luong"),
    ("KH-1019", "Kiểm hàng KCS", "Tổ KCS", "to_kcs", "tờ", 3, "to_sau_in"),
    ("KH-1020", "Soạn mẫu / kiểm bù trừ", "Tổ KCS", "to_kcs", "lượt", 40000, None),
]


def _import_khoan(db: Session) -> int:
    depts = DepartmentRepository(db)
    co = {m for m in db.execute(select(PieceRate.ma)).scalars() if m}
    moi = []
    for ma, ten, to_ten, grp, unit, gia, ct in _KHOAN:
        if ma in co:
            continue
        d = depts.get_by_name(to_ten)
        moi.append(PieceRate(
            ma=ma, ten=ten, group_name=grp, department_id=(d.id if d else None),
            unit=unit, unit_price=gia, cong_thuc_luong=ct, active=True,
        ))
    if moi:
        db.add_all(moi)
        db.commit()
    return len(moi)


# ---------------------------------------------------------------------------------------------
# 8) Khuôn (thêm 20). loai khuon_be/khuon_ep · tình trạng · số kệ · ngày có khuôn (dự kiến).
# ---------------------------------------------------------------------------------------------
def _kb(ma, ten, loai, so_ke, tinh_trang, ngay=None, ghi_chu=None):
    return dict(ma=ma, ten=ten, loai=loai, so_ke=so_ke, tinh_trang=tinh_trang,
                ngay_ve_du_kien=ngay, ghi_chu=ghi_chu)


_KHUON = [
    _kb("KB-1001", "Khuôn bế hộp mỹ phẩm 8×8×12", "khuon_be", "Kệ A3 — xưởng sau in", "dang_dung"),
    _kb("KB-1002", "Khuôn bế hộp bánh trung thu 4 trứng", "khuon_be", "Kệ A4 — xưởng sau in", "dang_dung"),
    _kb("KB-1003", "Khuôn bế hộp giày 30×20×12", "khuon_be", "Kệ A5 — xưởng sau in", "dang_dung"),
    _kb("KB-1004", "Khuôn bế tem tròn Ø30", "khuon_be", "Kệ B2 — kho khuôn", "dang_dung"),
    _kb("KB-1005", "Khuôn bế tem chữ nhật 40×25", "khuon_be", "Kệ B3 — kho khuôn", "dang_dung"),
    _kb("KB-1006", "Khuôn bế nhãn treo (hang tag)", "khuon_be", "Kệ B5 — kho khuôn", "dang_dung"),
    _kb("KB-1007", "Khuôn bế túi giấy đáy vuông", "khuon_be", "Kệ C1 — kho khuôn", "dang_dung"),
    _kb("KB-1008", "Khuôn bế túi giấy quai lụa", "khuon_be", "Kệ C2 — kho khuôn", "dang_dung"),
    _kb("KB-1009", "Khuôn bế thùng carton A3 sóng B", "khuon_be", "Kệ C4 — kho khuôn", "dang_dung"),
    _kb("KB-1010", "Khuôn bế folder kẹp tài liệu", "khuon_be", "Kệ D1 — kho khuôn", "dang_dung"),
    _kb("KB-1011", "Khuôn bế thiệp cưới bế biên", "khuon_be", "Kệ D2 — kho khuôn", "dang_dung"),
    _kb("KB-1012", "Khuôn bế lịch để bàn chân gấp", "khuon_be", "Kệ D3 — kho khuôn", "dang_dung"),
    _kb("KB-1013", "Khuôn bế hộp pizza 30cm", "khuon_be", "Kệ C5 — kho khuôn", "dang_dat_lam",
        ngay=date(2026, 9, 15), ghi_chu="Đặt thợ ngoài làm dao."),
    _kb("KB-1014", "Khuôn bế hộp cơm giấy", "khuon_be", "Kệ C6 — kho khuôn", "dang_dat_lam",
        ngay=date(2026, 9, 30), ghi_chu="Chờ dao mới cho đơn hàng chuỗi F&B."),
    _kb("KB-1015", "Khuôn ép nhũ logo thương hiệu A", "khuon_ep", "Kệ E1 — kho khuôn", "dang_dung"),
    _kb("KB-1016", "Khuôn ép nhũ tiêu đề thiệp", "khuon_ep", "Kệ E2 — kho khuôn", "dang_dung"),
    _kb("KB-1017", "Khuôn ép chìm (deboss) hộp quà", "khuon_ep", "Kệ E3 — kho khuôn", "dang_dung"),
    _kb("KB-1018", "Khuôn ép nổi (emboss) bìa sách", "khuon_ep", "Kệ E4 — kho khuôn", "dang_dung"),
    _kb("KB-1019", "Khuôn ép nhũ khung viền name card", "khuon_ep", "Kệ E5 — kho khuôn", "hong",
        ghi_chu="Khuôn mòn, cần thay trước khi dùng lại."),
    _kb("KB-1020", "Khuôn bế hộp mẫu cũ (khách đổi thiết kế)", "khuon_be", "Kệ F1 — kho khuôn", "thanh_ly",
        ghi_chu="Giữ tra cứu, không còn dùng."),
]


def _import_khuon(db: Session) -> int:
    return _them_thieu(db, KhuonBe, _KHUON)


# ---------------------------------------------------------------------------------------------
# 9) Lý do & lỗi SX — bộ mặc định phủ đủ 8 nhóm (§15). KHÔNG có công thức.
# ---------------------------------------------------------------------------------------------
def _ld(nhom: str, cap: list[tuple[str, str, str]]) -> list[dict]:
    """cap = list (ma, ten, mo_ta); thu_tu chạy theo thứ tự khai."""
    return [dict(ma=ma, nhom=nhom, ten=ten, mo_ta=(mo or None), thu_tu=i)
            for i, (ma, ten, mo) in enumerate(cap, start=1)]


_LY_DO = (
    _ld("loi", [
        ("LD-LOI-01", "Nhăn giấy", "Giấy nhăn/gấp mép khi chạy máy."),
        ("LD-LOI-02", "Lệch màu", "Màu in lệch so với tờ ký mẫu."),
        ("LD-LOI-03", "Bavia / răng cưa bế", "Cạnh bế bị xơ, răng cưa."),
        ("LD-LOI-04", "Trầy xước bề mặt", "Bề mặt in bị trầy khi gia công."),
        ("LD-LOI-05", "Bong tróc màng", "Màng cán bị bong, phồng rộp."),
        ("LD-LOI-06", "Lem mực / dây mực", "Mực lem, dây bẩn sang tờ khác."),
        ("LD-LOI-07", "Sai kích thước thành phẩm", "Thành phẩm sai khổ cắt/bế."),
        ("LD-LOI-08", "Rách / hư tờ in", "Tờ in bị rách trong quá trình chạy."),
    ]),
    _ld("tam_dung", [
        ("LD-TD-01", "Chờ mực", "Dừng chờ pha/cấp mực."),
        ("LD-TD-02", "Chờ kẽm", "Dừng chờ ghi/phơi kẽm."),
        ("LD-TD-03", "Kẹt giấy", "Máy kẹt giấy phải xử lý."),
        ("LD-TD-04", "Sự cố máy", "Máy hỏng/trục trặc kỹ thuật."),
        ("LD-TD-05", "Mất điện", "Mất điện lưới/nguồn."),
        ("LD-TD-06", "Chờ lệnh / chờ duyệt", "Dừng chờ lệnh hoặc duyệt bài."),
        ("LD-TD-07", "Vệ sinh máy", "Dừng vệ sinh, rửa lô."),
        ("LD-TD-08", "Hết ca / giao ca", "Dừng theo ca làm việc."),
    ]),
    _ld("bat_dau_tre", [
        ("LD-BDT-01", "Vật tư về trễ", "Giấy/vật tư chưa về kịp giờ chạy."),
        ("LD-BDT-02", "Kẽm ra trễ", "Chế bản ra kẽm chậm."),
        ("LD-BDT-03", "Máy bận lệnh trước", "Máy chưa xong lệnh trước đó."),
        ("LD-BDT-04", "Chờ duyệt bài", "Bài chưa được duyệt để in."),
        ("LD-BDT-05", "Thiếu nhân sự đầu ca", "Chưa đủ người vào đầu ca."),
    ]),
    _ld("lech_nhan_su", [
        ("LD-NS-01", "Nghỉ phép", "Người trong tổ nghỉ phép."),
        ("LD-NS-02", "Nghỉ ốm", "Người trong tổ nghỉ ốm."),
        ("LD-NS-03", "Điều động tổ khác", "Điều người sang hỗ trợ tổ khác."),
        ("LD-NS-04", "Tăng cường hỗ trợ", "Thêm người từ tổ khác sang."),
        ("LD-NS-05", "Đào tạo / học việc", "Người bận đào tạo, học việc."),
    ]),
    _ld("thieu_vat_tu", [
        ("LD-VT-01", "Thiếu giấy", "Không đủ giấy để chạy hết lệnh."),
        ("LD-VT-02", "Thiếu mực pha", "Chưa đủ mực pha theo màu."),
        ("LD-VT-03", "Thiếu màng cán", "Chưa đủ màng cho gia công."),
        ("LD-VT-04", "Thiếu keo", "Chưa đủ keo dán/đóng."),
        ("LD-VT-05", "Khuôn chưa về", "Dao/khuôn chưa có trong tay."),
    ]),
    _ld("dieu_chinh_ban_giao", [
        ("LD-BG-01", "Bù hàng lỗi", "Chạy bù cho phần hàng lỗi."),
        ("LD-BG-02", "Khách đổi số lượng", "Khách thay đổi số lượng đặt."),
        ("LD-BG-03", "Điều chỉnh do hụt bù hao", "Bù hao không đủ, phải chỉnh giao."),
        ("LD-BG-04", "Giao bổ sung", "Giao thêm phần còn thiếu."),
        ("LD-BG-05", "Thu hồi hàng lỗi", "Thu lại hàng lỗi đã giao."),
    ]),
    _ld("mo_lai_phan_bo", [
        ("LD-PB-01", "Sửa sai phân bổ", "Phân bổ chi phí/sản lượng sai, mở lại."),
        ("LD-PB-02", "Bổ sung công đoạn thiếu", "Thiếu công đoạn, thêm vào lệnh."),
        ("LD-PB-03", "Khách khiếu nại chất lượng", "Xử lý khiếu nại, tính lại."),
        ("LD-PB-04", "Tính lại đơn giá", "Đơn giá sai, tính lại."),
        ("LD-PB-05", "Gộp / tách lệnh", "Gộp hoặc tách lệnh sản xuất."),
    ]),
    _ld("dong_thieu", [
        ("LD-DT-01", "Hụt do bù hao không đủ", "Bù hao thiếu nên giao hụt."),
        ("LD-DT-02", "Hỏng vượt định mức", "Hàng hỏng nhiều hơn định mức cho phép."),
        ("LD-DT-03", "Khách chấp nhận giao thiếu", "Khách đồng ý nhận thiếu."),
        ("LD-DT-04", "Dừng đơn giữa chừng", "Đơn dừng, đóng theo số đã làm."),
        ("LD-DT-05", "Thiếu vật tư không bù kịp", "Vật tư thiếu, không bù kịp hạn."),
    ]),
)


def _import_ly_do(db: Session) -> int:
    rows = [r for nhom_rows in _LY_DO for r in nhom_rows]
    return _them_thieu(db, SanXuatLyDo, rows)


# ---------------------------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------------------------
def run(db: Session) -> dict[str, int]:
    kq: dict[str, int] = {}

    # Nền: phòng ban (cần "Sản xuất" cho tổ) + đơn vị + nhóm máy + danh mục base (bỏ qua nếu đã có).
    seed_departments(db)
    seed_don_vi_do(db)
    kq["don_vi_bo_sung"] = _import_don_vi_bo_sung(db)
    seed_nhom_may(db)
    seed_rebuild_catalog(db)

    # Danh mục đa dạng (additive theo mã).
    kq["chung_loai_giay"] = _import_chung_loai(db)
    kq["giay"] = _import_giay(db)
    kq["vat_tu"] = _import_vat_tu(db)
    kq["may"] = _import_may(db)
    seed_nhom_may(db)          # bắt 4 nhóm máy MỚI (Chế bản/Xén/Gấp-Dán/Đóng gói)
    kq["bu_hao"] = _import_bu_hao(db)
    kq["cong_doan"] = _import_cong_doan(db)
    kq["khuon"] = _import_khuon(db)
    kq["ly_do_san_xuat"] = _import_ly_do(db)

    # Tổ sản xuất + gắn công đoạn → tổ (mở cổng: gọi thẳng, không qua SEED_DEMO).
    seed_san_xuat_org(db)
    kq["cong_viec_khoan"] = _import_khoan(db)   # cần tổ đã có để tra department_id

    # Bù NCC + kho + lô tồn + ngưỡng cho mọi giấy/vật tư có đơn vị.
    seed_kho_ncc(db)
    return kq


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        kq = run(db)
    finally:
        db.close()
    print("== Import danh mục PROD xong ==")
    for k, v in kq.items():
        print(f"  + {k}: {v} dòng mới")
    print("  (số 0 = đã có sẵn, không thêm — idempotent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
