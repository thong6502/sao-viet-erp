"""RESEED 5 module tính giá bằng DATA THỰC TẾ — chạy engine + IN BẢNG GIÁ để soi công thức.

Xóa sạch + nạp lại: Giấy (chủng loại + giấy nguyên) · Vật tư in ấn · Công đoạn (kèm Bù hao) ·
Loại sản phẩm · Phiếu tính giá mẫu. MỌI công đoạn có `cong_thuc_gia` TƯỜNG MINH (che_do_tinh=
theo_san_luong, pricing_basis=per_other → don_gia bơm vào công thức = run_rate, KHÔNG bị
min_charge/tier bóp méo). Giấy tính theo cân (công thức khối lượng).

CHỈ tác động dev.db (đã backup). KHÔNG đụng seed_rebuild.py/seed.py (ảnh hưởng test).

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/reseed_tinh_gia_5.py
"""
from __future__ import annotations

import sys
from sqlalchemy import delete

sys.path.insert(0, ".")
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.bu_hao import BuHao  # noqa: E402
from app.models.cong_doan import CongDoan  # noqa: E402
from app.models.loai_san_pham import LoaiSanPham  # noqa: E402
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn  # noqa: E402
from app.models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia, PhieuVatTu  # noqa: E402
from app.services.tinh_gia_service import compute_phieu_snapshot  # noqa: E402

# Công thức giấy tính theo cân: tiền = định lượng(kg/m²) × dài × rộng (m) × đơn giá/kg × số tờ nguyên.
WEIGHT = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen"


def _vi(n) -> str:
    n = float(n or 0)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def wipe(db):
    # Con → cha (FK cascade thật ở phiếu); catalog xoá thẳng (soft-FK).
    for model in (PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia,
                  GiayNguyen, ChungLoaiGiay, VatTuInAn,
                  CongDoan, BuHao, LoaiSanPham):
        db.execute(delete(model))
    db.commit()


def seed_giay(db):
    cls = [
        ChungLoaiGiay(ma="COUCHE", ten="Couché", be_mat="bong", mo_ta="Tráng phủ 2 mặt, bóng."),
        ChungLoaiGiay(ma="FORD", ten="Ford (giấy in thường)", be_mat="nham"),
        ChungLoaiGiay(ma="IVORY", ten="Ivory (bìa 1 mặt bóng)", be_mat="bong"),
        ChungLoaiGiay(ma="DUPLEX", ten="Duplex (2 mặt: 1 bóng 1 xám)", be_mat="nham"),
        ChungLoaiGiay(ma="BRISTOL", ten="Bristol", be_mat="mo"),
        ChungLoaiGiay(ma="KRAFT", ten="Kraft (giấy nâu)", be_mat="nham"),
    ]
    db.add_all(cls)
    db.flush()
    clid = {c.ma: c.id for c in cls}
    # (ma, ten, chủng loại, gsm, rộng mm, dài mm, đ/kg)
    G = [
        ("COUCHE-120-79x109", "Couché C120 79×109", "COUCHE", 120, 790, 1090, 28000),
        ("COUCHE-150-79x109", "Couché C150 79×109", "COUCHE", 150, 790, 1090, 28000),
        ("COUCHE-200-79x109", "Couché C200 79×109", "COUCHE", 200, 790, 1090, 29000),
        ("COUCHE-250-79x109", "Couché C250 79×109", "COUCHE", 250, 790, 1090, 29000),
        ("COUCHE-300-65x86", "Couché C300 65×86", "COUCHE", 300, 650, 860, 30000),
        ("FORD-70-65x86", "Ford 70 65×86", "FORD", 70, 650, 860, 26000),
        ("FORD-80-79x109", "Ford 80 79×109", "FORD", 80, 790, 1090, 27000),
        ("IVORY-250-79x109", "Ivory 250 79×109", "IVORY", 250, 790, 1090, 31000),
        ("IVORY-300-79x109", "Ivory 300 79×109", "IVORY", 300, 790, 1090, 31000),
        ("IVORY-350-79x109", "Ivory 350 79×109", "IVORY", 350, 790, 1090, 32000),
        ("DUPLEX-300-79x109", "Duplex 300 79×109", "DUPLEX", 300, 790, 1090, 18000),
        ("DUPLEX-350-79x109", "Duplex 350 79×109", "DUPLEX", 350, 790, 1090, 18000),
        ("BRISTOL-230-79x109", "Bristol 230 79×109", "BRISTOL", 230, 790, 1090, 30000),
        ("KRAFT-150-79x109", "Kraft 150 79×109", "KRAFT", 150, 790, 1090, 22000),
    ]
    giay = [GiayNguyen(ma=ma, ten=ten, chung_loai_giay_id=clid[cl], gsm=gsm,
                       kho_rong=r, kho_dai=d, tho="canh_dai", don_vi_gia="kg", don_gia=dg,
                       cong_thuc_gia=WEIGHT) for ma, ten, cl, gsm, r, d, dg in G]
    db.add_all(giay)
    db.flush()
    return {g.ma: g.id for g in giay}


def seed_vat_tu(db):
    # Mực: mỗi vật tư TỰ MANG công thức (giống giấy) → engine thế biến vào. Tiền mực =
    # số_màu × diện_tích_tờ_in(m²) × độ_phủ(0,0003 kg/m²/màu) × đơn_giá/kg × số_tờ_vào_máy.
    MUC_CT = "so_mau * dai_in * rong_in * don_gia_kg * to_dau_vao * 0.0003"
    # (ma, ten, đvt, đơn giá, công thức) — kẽm/màng/keo để TRỐNG công thức (chi phí nằm ở CÔNG ĐOẠN).
    V = [
        ("MUC-CMYK", "Mực offset process (CMYK)", "kg", 250000, MUC_CT),
        ("MUC-PANTONE", "Mực pha Pantone", "kg", 420000, MUC_CT),
        ("MUC-UV", "Mực / vẹc-ni UV", "kg", 320000, MUC_CT),
        ("KEM-102", "Bản kẽm CTP khổ 102 (máy 79×109)", "ban", 95000, None),
        ("KEM-74", "Bản kẽm CTP khổ 74 (máy 72×102)", "ban", 72000, None),
        ("KEM-54", "Bản kẽm CTP khổ 54 (máy 54×79)", "ban", 48000, None),
        ("MANG-BONG", "Màng cán bóng BOPP", "m2", 2200, None),
        ("MANG-MO", "Màng cán mờ BOPP", "m2", 2600, None),
        ("KEO-GAY", "Keo nhiệt vào gáy (EVA)", "kg", 55000, None),
    ]
    objs = [VatTuInAn(ma=m, ten=t, don_vi_gia=u, don_gia=g, cong_thuc_gia=ct) for m, t, u, g, ct in V]
    db.add_all(objs)
    db.flush()
    return {o.ma: o.id for o in objs}


def seed_bu_hao(db):
    _SL = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]

    def _bac(sau_to, pct):
        b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"} for (t, d), v in zip(_SL, sau_to)]
        b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
        return b

    B = [
        BuHao(ma="BH-KHONG-IN", ten="Hàng không in", bac=_bac([50, 70, 100, 130, 150, 200], 1)),
        BuHao(ma="BH-IN-1-2", ten="In 1-2 màu", bac=_bac([120, 150, 200, 250, 300, 350], 1.5)),
        BuHao(ma="BH-IN-3-4", ten="In 3-4 màu", bac=_bac([150, 200, 250, 300, 350, 400], 1.7)),
        BuHao(ma="BH-IN-5", ten="In 5 màu", bac=_bac([200, 250, 300, 350, 400, 450], 2)),
        BuHao(ma="BH-IN-6", ten="In 6 màu", bac=_bac([250, 300, 350, 450, 500, 600], 2.5)),
        BuHao(ma="BH-SONG-1CON", ten="Bồi sóng — 1 con", bac=_bac([70, 100, 150, 170, 200, 250], 1)),
    ]
    db.add_all(B)
    db.flush()
    return {b.ma: b.id for b in B}


def seed_cong_doan(db, bh):
    # Mọi công đoạn: theo_san_luong + per_other + cong_thuc_gia tường minh; don_gia (trong CT) = run_rate.
    C = [
        dict(ma="CD-0001", ten="Ghi kẽm CTP", nhom="prepress",
             cong_thuc_gia="so_kem * don_gia", run_rate=95000, kieu_bu_hao="khong"),
        dict(ma="CD-0002", ten="In offset", nhom="print",
             cong_thuc_gia="to_dau_vao * so_mat * don_gia", run_rate=280,
             kieu_bu_hao="tra_bang", bu_hao_ma="BH-IN-3-4"),
        dict(ma="CD-0003", ten="Cán màng bóng", nhom="finishing",
             cong_thuc_gia="to_sau_in * dai_in * rong_in * so_mat * don_gia", run_rate=2500,
             kieu_bu_hao="co_dinh", so_to_bu_hao=50),
        dict(ma="CD-0004", ten="Cán màng mờ", nhom="finishing",
             cong_thuc_gia="to_sau_in * dai_in * rong_in * so_mat * don_gia", run_rate=2900,
             kieu_bu_hao="co_dinh", so_to_bu_hao=50),
        dict(ma="CD-0005", ten="Bồi sóng", nhom="finishing",
             cong_thuc_gia="to_sau_in * don_gia", run_rate=350,
             kieu_bu_hao="tra_bang", bu_hao_ma="BH-SONG-1CON"),
        dict(ma="CD-0006", ten="Bế thành phẩm", nhom="finishing",
             cong_thuc_gia="to_sau_in * don_gia", run_rate=250, requires_tooling=True,
             tooling_type="khuon_be", kieu_bu_hao="co_dinh", so_to_bu_hao=30),
        dict(ma="CD-0007", ten="Ép kim", nhom="finishing",
             cong_thuc_gia="so_luong * so_vi_tri * don_gia", run_rate=180, requires_tooling=True,
             tooling_type="khuon_ep", kieu_bu_hao="co_dinh", so_to_bu_hao=50),
        dict(ma="CD-0008", ten="Khuôn bế (một lần)", nhom="finishing",
             cong_thuc_gia="don_gia", run_rate=600000, kieu_bu_hao="khong"),
        dict(ma="CD-0009", ten="Gấp thành phẩm", nhom="finishing",
             cong_thuc_gia="so_luong * don_gia", run_rate=40, kieu_bu_hao="khong"),
        dict(ma="CD-0010", ten="Đóng cuốn keo nhiệt", nhom="finishing",
             cong_thuc_gia="so_luong * don_gia", run_rate=850, kieu_bu_hao="khong"),
        dict(ma="CD-0011", ten="Khuôn ép kim (một lần)", nhom="finishing",
             cong_thuc_gia="don_gia", run_rate=450000, kieu_bu_hao="khong"),
    ]
    objs = []
    for c in C:
        bh_ma = c.pop("bu_hao_ma", None)
        cd = CongDoan(che_do_tinh="theo_san_luong", pricing_basis="per_other", **c)
        if bh_ma:
            cd.bu_hao_id = bh[bh_ma]
        objs.append(cd)
    db.add_all(objs)
    db.flush()
    return {c.ma: c.id for c in objs}


def seed_loai_sp(db, cd):
    def rt(*mas):
        return [cd[m] for m in mas]

    L = [
        LoaiSanPham(ma="LSP-0001", ten="Name card", structural_type="flat",
                    routing_template=rt("CD-0001", "CD-0002", "CD-0003", "CD-0006", "CD-0008")),
        LoaiSanPham(ma="LSP-0002", ten="Tờ rơi / brochure gấp", structural_type="flat",
                    routing_template=rt("CD-0001", "CD-0002", "CD-0009")),
        LoaiSanPham(ma="LSP-0003", ten="Catalogue đóng keo", structural_type="multipage",
                    has_cover=True, cover_type="bia_roi", default_binding="keo",
                    routing_template=rt("CD-0001", "CD-0002", "CD-0010")),
        LoaiSanPham(ma="LSP-0004", ten="Sách đóng ghim", structural_type="multipage",
                    has_cover=True, cover_type="tu_bia", default_binding="ghim",
                    routing_template=rt("CD-0001", "CD-0002")),
        LoaiSanPham(ma="LSP-0005", ten="Hộp giấy Ivory", structural_type="box",
                    box_sub_type="folding_carton",
                    routing_template=rt("CD-0001", "CD-0002", "CD-0004", "CD-0006", "CD-0008")),
        LoaiSanPham(ma="LSP-0006", ten="Thùng carton sóng", structural_type="box",
                    box_sub_type="corrugated", routing_template=rt("CD-0005", "CD-0006")),
        LoaiSanPham(ma="LSP-0007", ten="Tem decal cuộn", structural_type="label",
                    routing_template=rt("CD-0001", "CD-0002", "CD-0006")),
    ]
    db.add_all(L)
    db.flush()
    return {x.ma: x.id for x in L}


def _row(cd_id, ten, thu_tu, bu_hao=False, so_mat=1, so_vi_tri=0):
    return PhieuThanhPham(thu_tu=thu_tu, cong_doan_id=cd_id, ten=ten, don_gia=0,
                          bu_hao=bu_hao, so_mat=so_mat, so_vi_tri=so_vi_tri)


def _vt(vt_id, ten, thu_tu=0):
    """1 dòng vật tư (mực) gắn vào thành phần → engine tính thành dòng NVL."""
    return PhieuVatTu(thu_tu=thu_tu, vat_tu_id=vt_id, ten=ten, don_gia=0)


def seed_phieu(db, giay, vt, cd, lsp):
    phieus = []
    muc = vt["MUC-CMYK"]

    # ── PHIẾU 1: Name card 4/4 cán bóng 1 mặt + bế ─────────────────────────────
    p1 = PhieuTinhGia(ma="PTG-2026-0001", ten_san_pham="Name card 4/4 cán bóng, bế bo góc",
                      kho_thanh_pham="9×5,4 cm", so_luong=4000, loai_san_pham_id=lsp["LSP-0001"],
                      ktv="Kỹ thuật A")
    tp = PhieuThanhPhan(thu_tu=0, ten="Danh thiếp", loai_san_pham_id=lsp["LSP-0001"],
                        giay_id=giay["COUCHE-300-65x86"], quy_cach_in="hai_mat",
                        so_mau_a=4, so_mau_b=4, dai_thanh_pham=90, rong_thanh_pham=54, con_auto=True)
    tp.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP", 0),
        _row(cd["CD-0002"], "In offset 4/4", 1, bu_hao=True),
        _row(cd["CD-0003"], "Cán màng bóng (1 mặt)", 2, bu_hao=True, so_mat=1),
        _row(cd["CD-0006"], "Bế bo góc", 3, bu_hao=True),
        _row(cd["CD-0008"], "Khuôn bế", 4),
    ]
    tp.vat_tus = [_vt(muc, "Mực in CMYK")]
    p1.thanh_phans = [tp]
    phieus.append(p1)

    # ── PHIẾU 2: Tờ rơi A5 4/4 gấp đôi ─────────────────────────────────────────
    p2 = PhieuTinhGia(ma="PTG-2026-0002", ten_san_pham="Tờ rơi A5 4/4 gấp đôi",
                      kho_thanh_pham="A5 (14,8×21 cm)", so_luong=20000, loai_san_pham_id=lsp["LSP-0002"],
                      ktv="Kỹ thuật A")
    tp = PhieuThanhPhan(thu_tu=0, ten="Tờ rơi", loai_san_pham_id=lsp["LSP-0002"],
                        giay_id=giay["COUCHE-150-79x109"], quy_cach_in="hai_mat",
                        so_mau_a=4, so_mau_b=4, dai_thanh_pham=210, rong_thanh_pham=148, con_auto=True)
    tp.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP", 0),
        _row(cd["CD-0002"], "In offset 4/4", 1, bu_hao=True),
        _row(cd["CD-0009"], "Gấp đôi", 2),
    ]
    tp.vat_tus = [_vt(muc, "Mực in CMYK")]
    p2.thanh_phans = [tp]
    phieus.append(p2)

    # ── PHIẾU 3: Hộp giấy Ivory 300 in 4/0 cán bóng + bế ───────────────────────
    p3 = PhieuTinhGia(ma="PTG-2026-0003", ten_san_pham="Hộp giấy Ivory 300 — 4/0 cán bóng, bế",
                      kho_thanh_pham="Hộp gấp (trải 38×25 cm)", so_luong=10000,
                      loai_san_pham_id=lsp["LSP-0005"], ktv="Kỹ thuật B")
    tp = PhieuThanhPhan(thu_tu=0, ten="Vỏ hộp", loai_san_pham_id=lsp["LSP-0005"],
                        giay_id=giay["IVORY-300-79x109"], quy_cach_in="mot_mat",
                        so_mau_a=4, so_mau_b=0, dai_thanh_pham=380, rong_thanh_pham=250, con_auto=True)
    tp.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP", 0),
        _row(cd["CD-0002"], "In offset 4/0", 1, bu_hao=True),
        _row(cd["CD-0003"], "Cán màng bóng (1 mặt)", 2, bu_hao=True, so_mat=1),
        _row(cd["CD-0006"], "Bế hộp", 3, bu_hao=True),
        _row(cd["CD-0008"], "Khuôn bế", 4),
    ]
    tp.vat_tus = [_vt(muc, "Mực in CMYK")]
    p3.thanh_phans = [tp]
    phieus.append(p3)

    # ── PHIẾU 4: Catalogue — GỘP 2 SẢN PHẨM (ruột + bìa) ───────────────────────
    p4 = PhieuTinhGia(ma="PTG-2026-0004", ten_san_pham="Catalogue A4 — ruột + bìa (đóng keo)",
                      kho_thanh_pham="A4 (21×29,7 cm)", so_luong=3000,
                      loai_san_pham_id=lsp["LSP-0003"], ktv="Kỹ thuật B")
    ruot = PhieuThanhPhan(thu_tu=0, ten="Ruột", loai_san_pham_id=lsp["LSP-0003"],
                          giay_id=giay["COUCHE-150-79x109"], quy_cach_in="hai_mat",
                          so_mau_a=4, so_mau_b=4, dai_thanh_pham=297, rong_thanh_pham=210, con_auto=True)
    ruot.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP (ruột)", 0),
        _row(cd["CD-0002"], "In offset 4/4 (ruột)", 1, bu_hao=True),
    ]
    bia = PhieuThanhPhan(thu_tu=1, ten="Bìa", loai_san_pham_id=lsp["LSP-0003"],
                         giay_id=giay["COUCHE-300-65x86"], quy_cach_in="hai_mat",
                         so_mau_a=4, so_mau_b=4, dai_thanh_pham=440, rong_thanh_pham=310, con_auto=True)
    bia.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP (bìa)", 0),
        _row(cd["CD-0002"], "In offset 4/4 (bìa)", 1, bu_hao=True),
        _row(cd["CD-0003"], "Cán màng bóng bìa (1 mặt)", 2, bu_hao=True, so_mat=1),
    ]
    ruot.vat_tus = [_vt(muc, "Mực in CMYK (ruột)")]
    bia.vat_tus = [_vt(muc, "Mực in CMYK (bìa)")]
    p4.thanh_phans = [ruot, bia]
    phieus.append(p4)

    # ── PHIẾU 5: Thiệp cưới ép kim + cán mờ ────────────────────────────────────
    p5 = PhieuTinhGia(ma="PTG-2026-0005", ten_san_pham="Thiệp cưới 4/4 cán mờ, ép kim 1 vị trí",
                      kho_thanh_pham="20×14 cm", so_luong=1000, loai_san_pham_id=lsp["LSP-0001"],
                      ktv="Kỹ thuật A")
    tp = PhieuThanhPhan(thu_tu=0, ten="Thiệp", loai_san_pham_id=lsp["LSP-0001"],
                        giay_id=giay["COUCHE-300-65x86"], quy_cach_in="hai_mat",
                        so_mau_a=4, so_mau_b=4, dai_thanh_pham=200, rong_thanh_pham=140, con_auto=True)
    tp.thanh_phams = [
        _row(cd["CD-0001"], "Ghi kẽm CTP", 0),
        _row(cd["CD-0002"], "In offset 4/4", 1, bu_hao=True),
        _row(cd["CD-0004"], "Cán màng mờ (1 mặt)", 2, bu_hao=True, so_mat=1),
        _row(cd["CD-0007"], "Ép kim 1 vị trí", 3, bu_hao=True, so_vi_tri=1),
        _row(cd["CD-0011"], "Khuôn ép kim", 4),
    ]
    tp.vat_tus = [_vt(muc, "Mực in CMYK")]
    p5.thanh_phans = [tp]
    phieus.append(p5)

    for p in phieus:
        db.add(p)
    db.flush()
    for p in phieus:
        compute_phieu_snapshot(db, p)
    db.commit()
    return phieus


def dump(phieus):
    for p in phieus:
        r = p.result_json
        m = r["meta"]
        print("\n" + "=" * 96)
        print(f"[{p.ma}] {p.ten_san_pham}   —   SL đặt {_vi(p.so_luong)}")
        print(f"  TỔNG GIÁ VỐN {_vi(p.tong_gia_von)}đ   |   ĐƠN GIÁ {_vi(p.gia_von_don)}đ/sp"
              f"   |   {m['so_thanh_phan']} sản phẩm, Σ SL {_vi(m['tong_so_luong'])}")
        for c in m["components"]:
            print(f"    · {c['name']}: con/tờ={c['con']} · tờ net={c['to_net']} · "
                  f"tờ vào máy={c['to_dau_vao']} · tờ nguyên={c['to_nguyen']} · "
                  f"kẽm={c['so_kem']} · vốn {_vi(c['gia_von_tp'])}đ ({_vi(c['gia_von_don'])}đ/sp)")
        for g in r["groups"]:
            print(f"\n  ── {g['name']}  (Σ {_vi(g['subtotal'])}đ) ──")
            for row in g["rows"]:
                tt = _vi(row.get("thanh_tien"))
                sp = _vi(row.get("gia_don_sp"))
                print(f"     {row['ten'][:40]:40} {tt:>14}đ  {sp:>10}đ/sp   [{row.get('cong_thuc','')}]")
        if r.get("warnings"):
            print("  ⚠ CẢNH BÁO:", r["warnings"])
    print("\n" + "=" * 96)


def main():
    Base.metadata.create_all(bind=engine)   # đảm bảo bảng MỚI phieu_vat_tu tồn tại trên dev.db
    db = SessionLocal()
    try:
        wipe(db)
        giay = seed_giay(db)
        vt = seed_vat_tu(db)
        bh = seed_bu_hao(db)
        cd = seed_cong_doan(db, bh)
        lsp = seed_loai_sp(db, cd)
        db.commit()
        phieus = seed_phieu(db, giay, vt, cd, lsp)
        print(f"✔ Reseed xong: {len(giay)} giấy · {len(vt)} vật tư · {len(cd)} công đoạn · "
              f"{len(bh)} bù hao · {len(lsp)} loại SP · {len(phieus)} phiếu")
        dump(phieus)
    finally:
        db.close()


if __name__ == "__main__":
    main()
