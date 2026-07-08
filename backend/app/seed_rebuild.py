"""Seed data cho các module rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP).

Theo seed §7 của từng spec. Idempotent (bỏ qua nếu bảng đã có dòng). Gọi 1 lần từ seed_all.
Direct model instantiation — đơn giản, đủ để UI có dữ liệu + engine (Phase D) có nền.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.cong_doan import CongDoan
from .models.loai_san_pham import LoaiSanPham
from .models.may_thiet_bi import MayThietBi
from .models.vat_lieu_kho import BanKem, GiayNguyen, Muc


def _empty(db: Session, model) -> bool:
    return db.execute(select(model).limit(1)).first() is None


def seed_rebuild_catalog(db: Session) -> None:
    # --- Máy (spec-may-thiet-bi §7) ---
    if _empty(db, MayThietBi):
        db.add_all([
            MayThietBi(ma="OFF-74-4C", ten="Offset 4 màu khổ 74", loai_may="press_offset_sheet",
                       trang_thai="active", khoa_class="74", kho_max_dai=740, kho_max_rong=530,
                       kho_min_dai=280, kho_min_rong=210, gripper_mm=12, so_units=4,
                       von_dau_tu=4_000_000_000, gia_tri_thu_hoi=400_000_000, nam_khau_hao=8,
                       lai_von_pct=10, gio_lam_nam=2000, availability_pct=90, productivity_pct=83,
                       so_nhan_cong=2, luong_gio=60000, cong_suat_kW=80, don_gia_dien=3000,
                       toc_do=13000, don_vi_toc_do="to_gio", markup_pct=15),
            MayThietBi(ma="OFF-102-5C", ten="Offset 5 màu khổ 102 (perfector)", loai_may="press_offset_sheet",
                       trang_thai="active", khoa_class="102", kho_max_dai=1020, kho_max_rong=720,
                       kho_min_dai=350, kho_min_rong=250, gripper_mm=12, so_units=5, toc_do=15000,
                       don_vi_toc_do="to_gio", von_dau_tu=9_000_000_000, nam_khau_hao=8),
            MayThietBi(ma="DIG-SRA3", ten="Kỹ thuật số SRA3 (toner)", loai_may="press_digital",
                       trang_thai="active", kho_max_dai=487, kho_max_rong=330, toc_do=4000,
                       don_vi_toc_do="to_gio"),
            MayThietBi(ma="CTP-B1", ten="Ghi kẽm CTP khổ B1", loai_may="prepress_ctp",
                       trang_thai="active", toc_do=20, don_vi_toc_do="to_gio"),
            MayThietBi(ma="XEN-115", ten="Máy xén 1150", loai_may="finishing",
                       finishing_subtype="guillotine", trang_thai="active"),
            MayThietBi(ma="CAN-BONG", ten="Máy cán màng bóng", loai_may="finishing",
                       finishing_subtype="laminator", trang_thai="active"),
            MayThietBi(ma="GC-CANMANG", ten="Gia công cán màng (thuê ngoài)", loai_may="thue_ngoai",
                       trang_thai="active"),
        ])
        db.commit()

    # --- Vật liệu Kho (spec-tinh-gia §3.1) ---
    if _empty(db, GiayNguyen):
        db.add_all([
            GiayNguyen(ma="COUCHE-300-65x86", ten="Couché 300 65×86", kho_dai=860, kho_rong=650,
                       gsm=300, caliper_micron=310, tho="canh_dai", don_vi_gia="kg", don_gia=30000, ton=500),
            GiayNguyen(ma="COUCHE-150-79x109", ten="Couché 150 79×109", kho_dai=1090, kho_rong=790,
                       gsm=150, caliper_micron=150, tho="canh_dai", don_vi_gia="kg", don_gia=28000, ton=800),
            GiayNguyen(ma="FORD-70-65x86", ten="Ford 70 65×86", kho_dai=860, kho_rong=650, gsm=70,
                       caliper_micron=95, tho="canh_ngan", don_vi_gia="kg", don_gia=26000, ton=1200),
            GiayNguyen(ma="IVORY-350-79x109", ten="Ivory 350 79×109", kho_dai=1090, kho_rong=790,
                       gsm=350, caliper_micron=430, tho="canh_dai", don_vi_gia="kg", don_gia=32000, ton=300),
            GiayNguyen(ma="DUPLEX-300", ten="Duplex 300", kho_dai=1090, kho_rong=790, gsm=300,
                       caliper_micron=380, don_vi_gia="kg", don_gia=18000, ton=600),
        ])
        db.commit()
    if _empty(db, Muc):
        db.add_all([
            Muc(ma="MUC-CMYK", ten="Mực process CMYK", loai_muc="process", don_gia=8000),
            Muc(ma="MUC-PANTONE", ten="Mực pha Pantone", loai_muc="pantone", don_gia=15000),
        ])
        db.commit()
    if _empty(db, BanKem):
        db.add_all([
            BanKem(ma="KEM-74", ten="Bản kẽm khổ 74", khoa_class="74", don_gia_kem=100000, ton=200),
            BanKem(ma="KEM-102", ten="Bản kẽm khổ 102", khoa_class="102", don_gia_kem=180000, ton=150),
            BanKem(ma="KEM-52", ten="Bản kẽm khổ 52", khoa_class="52", don_gia_kem=70000, ton=100),
        ])
        db.commit()

    # --- Công đoạn (spec-cong-doan §9); may_id nối máy vừa seed ---
    if _empty(db, CongDoan):
        may = {m.ma: m.id for m in db.execute(select(MayThietBi)).scalars()}
        db.add_all([
            CongDoan(ma="GHI-KEM", ten="Ghi kẽm CTP", nhom="prepress", may_id=may.get("CTP-B1"),
                     che_do_tinh="theo_gio", setup_time=10),
            CongDoan(ma="IN", ten="In offset", nhom="print", may_id=may.get("OFF-74-4C"),
                     che_do_tinh="theo_san_luong", pricing_basis="per_1000_luot", run_rate=8000,
                     first_unit_floor=350000, requires_tooling=True, tooling_type="kem"),
            CongDoan(ma="XEN", ten="Cắt xén", nhom="finishing", may_id=may.get("XEN-115"),
                     che_do_tinh="theo_san_luong", pricing_basis="per_ram", run_rate=60000, min_charge=60000),
            CongDoan(ma="CAN-BONG", ten="Cán màng bóng", nhom="finishing", may_id=may.get("CAN-BONG"),
                     che_do_tinh="theo_san_luong", pricing_basis="per_m2", run_rate=2200, min_charge=110000),
            CongDoan(ma="BE", ten="Bế", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_pass", run_rate=180, requires_tooling=True, tooling_type="khuon_be"),
            CongDoan(ma="EP-KIM", ten="Ép kim", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_pass", run_rate=400, requires_tooling=True, tooling_type="khuon_ep"),
            CongDoan(ma="DONG-KEO", ten="Đóng keo (vào bìa)", nhom="finishing",
                     che_do_tinh="theo_san_luong", pricing_basis="per_book", run_rate=180),
            CongDoan(ma="SO-NHAY", ten="Đánh số nhảy", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_number", run_rate=10),
        ])
        db.commit()

    # --- Loại sản phẩm (spec-san-pham §7) ---
    if _empty(db, LoaiSanPham):
        cd = {c.ma: c.id for c in db.execute(select(CongDoan)).scalars()}
        rt_flat = [cd.get("GHI-KEM"), cd.get("IN"), cd.get("BE"), cd.get("XEN")]
        rt_book = [cd.get("GHI-KEM"), cd.get("IN"), cd.get("CAN-BONG"), cd.get("DONG-KEO"), cd.get("XEN")]
        db.add_all([
            LoaiSanPham(ma="NAMECARD", ten="Name card", structural_type="flat", default_so_mat=2,
                        vat_rate=8, routing_template=[x for x in rt_flat if x]),
            LoaiSanPham(ma="TORPHOI", ten="Tờ phơi / brochure gấp", structural_type="flat",
                        default_so_mat=2, vat_rate=8),
            LoaiSanPham(ma="CATALOGUE", ten="Catalogue đóng keo", structural_type="multipage",
                        has_cover=True, cover_type="bia_roi", default_binding="keo", vat_rate=5,
                        routing_template=[x for x in rt_book if x]),
            LoaiSanPham(ma="SACH-GHIM", ten="Sách đóng ghim", structural_type="multipage",
                        has_cover=True, cover_type="tu_bia", default_binding="ghim", vat_rate=5),
            LoaiSanPham(ma="HOP-IVORY", ten="Hộp giấy Ivory", structural_type="box",
                        box_sub_type="folding_carton", vat_rate=8),
            LoaiSanPham(ma="THUNG-SONG", ten="Thùng carton sóng", structural_type="box",
                        box_sub_type="corrugated", vat_rate=8),
            LoaiSanPham(ma="TEM-DECAL", ten="Tem decal cuộn", structural_type="label", vat_rate=8),
        ])
        db.commit()
