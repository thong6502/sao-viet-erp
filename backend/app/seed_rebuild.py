"""Seed data cho các module rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP).

Theo seed §7 của từng spec. Idempotent (bỏ qua nếu bảng đã có dòng). Gọi 1 lần từ seed_all.
Direct model instantiation — đơn giản, đủ để UI có dữ liệu + engine (Phase D) có nền.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.bu_hao import BuHao
from .models.cong_doan import CongDoan
from .models.loai_san_pham import LoaiSanPham
from .models.may_thiet_bi import MayThietBi
from .models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, KhoGiayChuan, VatTuInAn


def _empty(db: Session, model) -> bool:
    return db.execute(select(model).limit(1)).first() is None


def seed_rebuild_catalog(db: Session) -> None:
    # --- Máy (spec-may-thiet-bi §7) ---
    if _empty(db, MayThietBi):
        # Dữ liệu THẬT của xưởng. Dim mm, rộng = số đầu, dài = số sau (vd "800*1030" = rộng 800, dài 1030).
        # Nhóm máy = chữ tự do (form MỞ). Chủ xưởng tự đặt tên nhóm để nhóm/lọc.
        _IN = "Máy in"              # máy in nội bộ
        _INX = "In ngoài"          # xưởng in ngoài
        _CM = "Cán màng / UV"      # cán màng / UV
        _BOI = "Bồi"               # bồi sóng / duplex
        _BE = "Bế"                 # bế / ép kim
        db.add_all([
            # ── MÁY IN nội bộ — kẽm / nhíp / khổ giấy / vùng in ───────────────────────
            MayThietBi(ma="IN-01", ten="Máy 2 màu Mitsubishi 72×102", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44,
                       kho_min_rong=390, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Có in UV được",
                       ghi_chu_2="Hàng bồi sóng phải chạy in tay kề nghịch, đặt tay kề sẵn trên bài in"),
            MayThietBi(ma="IN-02", ten="Máy 4 màu Mitsubishi 79×109", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=930, kho_kem_dai=1130, gripper_mm=60,
                       kho_min_rong=540, kho_min_dai=750, kho_max_rong=800, kho_max_dai=1090,
                       vung_in_rong=780, vung_in_dai=1080),
            MayThietBi(ma="IN-03", ten="Máy 5 màu Mitsubishi 54×79", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=645, kho_kem_dai=830, gripper_mm=50,
                       kho_min_rong=320, kho_min_dai=420, kho_max_rong=540, kho_max_dai=790,
                       vung_in_rong=535, vung_in_dai=780),
            MayThietBi(ma="IN-04", ten="Máy 6 màu Mitsubishi 72×102", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Có in UV được"),
            MayThietBi(ma="IN-05", ten="Máy 6 màu Heidelberg 72×102", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=765, kho_kem_dai=1030, gripper_mm=44,
                       kho_min_rong=395, kho_min_dai=560, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=690, vung_in_dai=1000, ghi_chu="Có in UV được",
                       ghi_chu_2="Vùng in lớn hơn 69cm thì nhíp kẽm 38mm; chỉ in được giấy từ 150g trở lên"),
            MayThietBi(ma="IN-06", ten="Máy 7 màu Heidelberg 72×102", loai_may=_IN, trang_thai="active",
                       kho_kem_rong=765, kho_kem_dai=1030, gripper_mm=44,
                       kho_min_rong=395, kho_min_dai=560, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=690, vung_in_dai=1000),
            # ── IN ngoài (xưởng in ngoài) ────────────────────────────────────────────
            MayThietBi(ma="IN-07", ten="Minh Tiến 72×102 - 5 màu", loai_may=_INX, trang_thai="active",
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=48,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu_2="Xưởng in ngoài"),
            MayThietBi(ma="IN-08", ten="Hoàng Anh 1020×1420 - 6 màu", loai_may=_INX, trang_thai="active",
                       kho_min_rong=575, kho_min_dai=810, kho_max_rong=1020, kho_max_dai=1420,
                       vung_in_rong=1000, vung_in_dai=1400, ghi_chu_2="Xưởng in ngoài"),
            MayThietBi(ma="IN-09", ten="Bảo Tiến 72×102 - 6 màu", loai_may=_INX, trang_thai="active",
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=50,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Có in UV", ghi_chu_2="Xưởng in ngoài"),
            MayThietBi(ma="IN-10", ten="Đỉnh Việt 72×102 - 5 màu", loai_may=_INX, trang_thai="active",
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu_2="Xưởng in ngoài"),
            # ── MÁY CÁN MÀNG + UV ĐỊNH HÌNH — chỉ khổ giấy min/max ────────────────────
            MayThietBi(ma="CM-01", ten="Máy UV toàn phần 790×1090", loai_may=_CM, trang_thai="active",
                       kho_min_rong=280, kho_min_dai=380, kho_max_rong=790, kho_max_dai=1090,
                       ghi_chu="Lớn hơn nửa thì thả tay dọc được"),
            MayThietBi(ma="CM-02", ten="Máy UV định hình 720×1020", loai_may=_CM, trang_thai="active",
                       kho_min_rong=360, kho_min_dai=440, kho_max_rong=720, kho_max_dai=1020,
                       ghi_chu="Xuất film để chụp lụa kéo",
                       ghi_chu_2="Phim đế 100k để chụp nét nội dung"),
            MayThietBi(ma="CM-03", ten="Máy cán màng 800×1080", loai_may=_CM, trang_thai="active",
                       kho_min_rong=300, kho_min_dai=300, kho_max_rong=800, kho_max_dai=1080),
            MayThietBi(ma="CM-04", ten="Máy cán màng 1250×1500", loai_may=_CM, trang_thai="active",
                       kho_min_rong=300, kho_min_dai=300, kho_max_rong=1250, kho_max_dai=1500),
            # ── MÁY BỒI SÓNG + BỒI DUPLEX ────────────────────────────────────────────
            MayThietBi(ma="BOI-01", ten="Bồi sóng 1450×1450", loai_may=_BOI, trang_thai="active",
                       kho_min_rong=395, kho_min_dai=395, kho_max_rong=1450, kho_max_dai=1450,
                       ghi_chu="Sóng luôn ghi chiều khổ trước",
                       ghi_chu_2="Tem luôn lớn hơn sóng mỗi chiều 5mm; trừ khi ăn gian giấy thì bằng ĐC nhưng phải báo"),
            MayThietBi(ma="BOI-02", ten="Bồi sóng 1700×1700", loai_may=_BOI, trang_thai="active",
                       kho_min_rong=395, kho_min_dai=395, kho_max_rong=1700, kho_max_dai=1700),
            MayThietBi(ma="BOI-03", ten="Bồi duplex với duplex 1100", loai_may=_BOI, trang_thai="active",
                       kho_min_rong=280, kho_min_dai=380, kho_max_rong=700, kho_max_dai=1000),
            MayThietBi(ma="BOI-04", ten="Bồi thủ công 1100", loai_may=_BOI, trang_thai="active",
                       kho_min_rong=200, kho_min_dai=200, kho_max_rong=700, kho_max_dai=1000),
            # ── MÁY BẾ TỰ ĐỘNG + BẾ TAY ──────────────────────────────────────────────
            MayThietBi(ma="BE-01", ten="Máy bế tự động Yawa 1050", loai_may=_BE, trang_thai="active",
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1050,
                       ghi_chu="Tự động trừ nhíp bế 8mm; chỉ ăn gian được tại dán ở nhíp thì phải tháo dao lạng hoặc tháo bớt nhíp gấp, phải hỏi thợ trước",
                       ghi_chu_2="Ván min 450×650, ván thực lỗ min 450×450"),
            MayThietBi(ma="BE-02", ten="Máy ép kim bế tự động Aoer 1050", loai_may=_BE, trang_thai="active",
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1050),
            MayThietBi(ma="BE-03", ten="Máy bế tự động Aoer 1500", loai_may=_BE, trang_thai="active",
                       kho_min_rong=400, kho_min_dai=420, kho_max_rong=1100, kho_max_dai=1500),
            MayThietBi(ma="BE-04", ten="Máy bế tự động Brouse 145", loai_may=_BE, trang_thai="active",
                       kho_min_rong=400, kho_min_dai=420, kho_max_rong=1050, kho_max_dai=1450),
            MayThietBi(ma="BE-05", ten="Máy ép kim bế tự động Diamon 1020", loai_may=_BE, trang_thai="active",
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1020),
            MayThietBi(ma="BE-06", ten="Máy bế tay 720/930/1100/1500", loai_may=_BE, trang_thai="active",
                       kho_min_rong=150, kho_min_dai=150, kho_max_rong=1050, kho_max_dai=1450,
                       ghi_chu="Bế tay bế SL ít, bế hàng ăn gian nhíp"),
        ])
        db.commit()

    # --- Danh mục Giấy & Vật tư (Cấu hình danh mục) ---
    if _empty(db, ChungLoaiGiay):
        db.add_all([
            ChungLoaiGiay(ma="COUCHE", ten="Couché", be_mat="bong", mo_ta="Giấy tráng phủ 2 mặt, bóng."),
            ChungLoaiGiay(ma="FORD", ten="Ford (giấy in thường)", be_mat="nham"),
            ChungLoaiGiay(ma="IVORY", ten="Ivory (bìa 1 mặt)", be_mat="bong"),
            ChungLoaiGiay(ma="DUPLEX", ten="Duplex (bồi 2 lớp)", be_mat="nham"),
            ChungLoaiGiay(ma="BRISTOL", ten="Bristol", be_mat="mo"),
            ChungLoaiGiay(ma="KRAFT", ten="Kraft (giấy nâu)", be_mat="nham"),
        ])
        db.commit()
    _cl = {c.ma: c.id for c in db.execute(select(ChungLoaiGiay)).scalars()}
    if _empty(db, GiayNguyen):
        db.add_all([
            GiayNguyen(ma="COUCHE-300-65x86", ten="Couché 300 65×86", chung_loai_giay_id=_cl.get("COUCHE"),
                       kho_dai=860, kho_rong=650, gsm=300, caliper_micron=310, tho="canh_dai",
                       don_vi_gia="kg", don_gia=30000),
            GiayNguyen(ma="COUCHE-150-79x109", ten="Couché 150 79×109", chung_loai_giay_id=_cl.get("COUCHE"),
                       kho_dai=1090, kho_rong=790, gsm=150, caliper_micron=150, tho="canh_dai",
                       don_vi_gia="kg", don_gia=28000),
            GiayNguyen(ma="FORD-70-65x86", ten="Ford 70 65×86", chung_loai_giay_id=_cl.get("FORD"),
                       kho_dai=860, kho_rong=650, gsm=70, caliper_micron=95, tho="canh_ngan",
                       don_vi_gia="kg", don_gia=26000),
            GiayNguyen(ma="IVORY-350-79x109", ten="Ivory 350 79×109", chung_loai_giay_id=_cl.get("IVORY"),
                       kho_dai=1090, kho_rong=790, gsm=350, caliper_micron=430, tho="canh_dai",
                       don_vi_gia="kg", don_gia=32000),
            GiayNguyen(ma="DUPLEX-300", ten="Duplex 300", chung_loai_giay_id=_cl.get("DUPLEX"),
                       kho_dai=1090, kho_rong=790, gsm=300, caliper_micron=380,
                       don_vi_gia="kg", don_gia=18000),
        ])
        db.commit()
    # Backfill chủng loại cho giấy chưa gắn (dev data / sau migration) theo tiền tố mã.
    _unlinked = list(db.execute(select(GiayNguyen).where(GiayNguyen.chung_loai_giay_id.is_(None))).scalars())
    if _unlinked:
        for g in _unlinked:
            for pfx, clid in _cl.items():
                if g.ma.upper().startswith(pfx):
                    g.chung_loai_giay_id = clid
                    break
        db.commit()

    if _empty(db, VatTuInAn):
        db.add_all([
            VatTuInAn(ma="MUC-CMYK", ten="Mực process CMYK", don_vi_gia="kg", don_gia=8000),
            VatTuInAn(ma="MUC-PANTONE", ten="Mực pha Pantone", don_vi_gia="kg", don_gia=15000),
            VatTuInAn(ma="KEM-74", ten="Bản kẽm khổ 74", don_vi_gia="ban", don_gia=100000),
            VatTuInAn(ma="KEM-102", ten="Bản kẽm khổ 102", don_vi_gia="ban", don_gia=180000),
            VatTuInAn(ma="KEM-52", ten="Bản kẽm khổ 52", don_vi_gia="ban", don_gia=70000),
            VatTuInAn(ma="MANG-BONG", ten="Màng cán bóng", don_vi_gia="m2", don_gia=3000),
            VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45000,
                      ghi_chu="UV định hình 1 thùng = 3kg"),
        ])
        db.commit()

    # --- Khổ giấy chuẩn (DANH MỤC KHỔ GIẤY CHUẨN, cm) — Duplex/Ivory cuộn, Ford/Couché ream ---
    if _empty(db, KhoGiayChuan):
        cuon = {  # chủng loại cuộn (dai=None) → (khổ rộng chuẩn, khổ rộng hiếm)
            "DUPLEX": ([60, 65, 79, 84, 86, 89, 109, 120], [70, 72, 75, 100, 102, 105, 140]),
            "IVORY": ([60, 65, 79, 84, 86, 89, 109, 120], [70, 72, 75, 100, 102, 105, 144]),
        }
        ream = {  # chủng loại ream → ([(rộng,dài) chuẩn], [rộng cuộn hiếm])
            "FORD": ([(60, 84), (65, 86), (79, 109)], [60, 65, 79, 86]),
            "COUCHE": ([(60, 84), (65, 86), (79, 109)], [60, 65, 79, 86]),
        }
        rows = []
        for cl_ma, (chuan, hiem) in cuon.items():
            clid = _cl.get(cl_ma)
            for w in chuan:
                rows.append(KhoGiayChuan(ma=f"KGC-{cl_ma}-{w}", ten=f"{cl_ma} khổ {w} (cuộn)",
                                         chung_loai_giay_id=clid, rong=w, la_hiem=False))
            for w in hiem:
                rows.append(KhoGiayChuan(ma=f"KGC-{cl_ma}-{w}H", ten=f"{cl_ma} khổ {w} (cuộn, hiếm)",
                                         chung_loai_giay_id=clid, rong=w, la_hiem=True))
        for cl_ma, (chuan, hiem_cuon) in ream.items():
            clid = _cl.get(cl_ma)
            for (w, d) in chuan:
                rows.append(KhoGiayChuan(ma=f"KGC-{cl_ma}-{w}x{d}", ten=f"{cl_ma} {w}×{d} (ream)",
                                         chung_loai_giay_id=clid, rong=w, dai=d, la_hiem=False))
            for w in hiem_cuon:
                rows.append(KhoGiayChuan(ma=f"KGC-{cl_ma}-{w}C", ten=f"{cl_ma} khổ {w} (cuộn, hiếm)",
                                         chung_loai_giay_id=clid, rong=w, la_hiem=True))
        db.add_all(rows)
        db.commit()

    # --- Công đoạn: seed ÍT (6 mẫu) đủ minh hoạ 4 kiểu bù hao (khong/số màu/số con/cố định) ---
    if _empty(db, CongDoan):
        db.add_all([
            CongDoan(ma="CD-0001", ten="Ghi kẽm CTP", nhom="prepress", che_do_tinh="theo_gio",
                     setup_time=10, kieu_bu_hao="khong"),
            CongDoan(ma="CD-0002", ten="In offset", nhom="print", che_do_tinh="theo_san_luong",
                     pricing_basis="per_sheet", run_rate=350, kieu_bu_hao="theo_so_mau"),
            CongDoan(ma="CD-0003", ten="Cán màng bóng", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_area_sides", run_rate=2.2, min_charge=110000,
                     kieu_bu_hao="co_dinh", so_to_bu_hao=50),
            CongDoan(ma="CD-0004", ten="Bồi sóng", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_sheet", run_rate=200, kieu_bu_hao="theo_so_con"),
            CongDoan(ma="CD-0005", ten="Ép kim", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_position", run_rate=400, requires_tooling=True,
                     tooling_type="khuon_ep", kieu_bu_hao="co_dinh", so_to_bu_hao=50),
            CongDoan(ma="CD-0006", ten="Bế nổi", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_finished_qty", run_rate=20, requires_tooling=True,
                     tooling_type="khuon_be", kieu_bu_hao="co_dinh", so_to_bu_hao=30),
        ])
        db.commit()

    # --- Bù hao (tra theo trục số màu/số con × bậc SL động) — số THẬT của xưởng ---
    if _empty(db, BuHao):
        _SL = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]

        def _bac(sau_to, pct):  # 6 bậc đầu = số tờ, bậc >30.000 = %
            b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"} for (t, d), v in zip(_SL, sau_to)]
            b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
            return b

        db.add_all([
            # Giấy in + thành phẩm — tra theo SỐ MÀU
            BuHao(ma="BH-KHONG-IN", ten="Hàng không in", truc="so_mau", key_tu=0, key_den=0,
                  bac=_bac([50, 70, 100, 130, 150, 200], 1)),
            BuHao(ma="BH-IN-1-2", ten="In 1-2 màu", truc="so_mau", key_tu=1, key_den=2,
                  bac=_bac([120, 150, 200, 250, 300, 350], 1.5)),
            BuHao(ma="BH-IN-3-4", ten="In 3-4 màu", truc="so_mau", key_tu=3, key_den=4,
                  bac=_bac([150, 200, 250, 300, 350, 400], 1.7)),
            BuHao(ma="BH-IN-5", ten="In 5 màu", truc="so_mau", key_tu=5, key_den=5,
                  bac=_bac([200, 250, 300, 350, 400, 450], 2)),
            BuHao(ma="BH-IN-6", ten="In 6 màu", truc="so_mau", key_tu=6, key_den=6,
                  bac=_bac([250, 300, 350, 450, 500, 600], 2.5)),
            # Sóng (bồi/bế) — tra theo SỐ CON
            BuHao(ma="BH-SONG-1CON", ten="Sóng — 1 con", truc="so_con", key_tu=1, key_den=1,
                  bac=_bac([70, 100, 150, 170, 200, 250], 1), ghi_chu="Sóng E, B, BC, BE — lưu ý chiều sóng trước"),
            BuHao(ma="BH-SONG-NHIEU", ten="Sóng — nhiều con", truc="so_con", key_tu=2, key_den=999,
                  bac=_bac([50, 70, 120, 150, 170, 200], 0.7)),
        ])
        db.commit()

    # --- Loại sản phẩm (spec-san-pham §7) ---
    if _empty(db, LoaiSanPham):
        cd = {c.ma: c.id for c in db.execute(select(CongDoan)).scalars()}
        rt_flat = [cd.get("CD-0001"), cd.get("CD-0002"), cd.get("CD-0005"), cd.get("CD-0003")]
        rt_book = [cd.get("CD-0001"), cd.get("CD-0002"), cd.get("CD-0004"), cd.get("CD-0007"), cd.get("CD-0003")]
        db.add_all([
            LoaiSanPham(ma="LSP-0001", ten="Name card", structural_type="flat",
                        routing_template=[x for x in rt_flat if x]),
            LoaiSanPham(ma="LSP-0002", ten="Tờ phơi / brochure gấp", structural_type="flat"),
            LoaiSanPham(ma="LSP-0003", ten="Catalogue đóng keo", structural_type="multipage",
                        has_cover=True, cover_type="bia_roi", default_binding="keo",
                        routing_template=[x for x in rt_book if x]),
            LoaiSanPham(ma="LSP-0004", ten="Sách đóng ghim", structural_type="multipage",
                        has_cover=True, cover_type="tu_bia", default_binding="ghim"),
            LoaiSanPham(ma="LSP-0005", ten="Hộp giấy Ivory", structural_type="box",
                        box_sub_type="folding_carton"),
            LoaiSanPham(ma="LSP-0006", ten="Thùng carton sóng", structural_type="box",
                        box_sub_type="corrugated"),
            LoaiSanPham(ma="LSP-0007", ten="Tem decal cuộn", structural_type="label"),
        ])
        db.commit()
