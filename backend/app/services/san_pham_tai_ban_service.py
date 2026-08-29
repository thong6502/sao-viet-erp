"""Kho SẢN PHẨM TÁI BẢN — tra cứu theo tên để nạp lại cấu hình kỹ thuật đã từng chốt đơn.

Nguồn ghi DUY NHẤT là `OrderService.confirm()` (gọi `snapshot_tu_thanh_phan` cùng transaction với
chốt đơn) — module này không có API tạo/sửa tay. Xem docs/spec-san-pham-tai-ban.md.
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.phieu_tinh_gia import PhieuThanhPhan, SanPhamTaiBan
from ..schemas.phieu_tinh_gia import ThanhPhamIn, ThanhPhanIn, VatTuLineIn

_DAU_MAP = str.maketrans({"đ": "d", "Đ": "D"})


def chuan_hoa_ten(s: str | None) -> str:
    """Bỏ dấu tiếng Việt + lowercase + gộp khoảng trắng — khoá tìm/so trùng tên tái bản."""
    s = (s or "").translate(_DAU_MAP)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = " ".join(s.split())
    return s.lower()


def _cau_hinh_tu_thanh_phan(tp: PhieuThanhPhan) -> dict:
    """Ảnh chụp CẤU HÌNH KỸ THUẬT dạng `ThanhPhanIn` — CỐ Ý bỏ qua `so_luong` (số lượng của đơn
    cũ), `so_to_per_sp`/`so_mau_a`/`so_mau_b`/`so_mau_pha` (dẫn xuất, engine tự tính lại khi nạp),
    và `gia_von_tp` (giá vốn đã tính, không thuộc `ThanhPhanIn`)."""
    data = ThanhPhanIn(
        loai_thanh_phan=tp.loai_thanh_phan,
        ten=tp.ten,
        dai_thanh_pham=tp.dai_thanh_pham,
        rong_thanh_pham=tp.rong_thanh_pham,
        so_trang=tp.so_trang,
        trang_moi_tay=tp.trang_moi_tay,
        don_vi_tinh=tp.don_vi_tinh,
        nhom_bao_gia=tp.nhom_bao_gia,
        loai_san_pham_id=tp.loai_san_pham_id,
        giay_id=tp.giay_id,
        kho_nguyen=tp.kho_nguyen,
        kho_nguyen_dai=tp.kho_nguyen_dai,
        kho_nguyen_rong=tp.kho_nguyen_rong,
        don_gia_giay=tp.don_gia_giay,
        don_gia_don_vi=tp.don_gia_don_vi,
        nguon_giay=tp.nguon_giay,
        chua_nhip=tp.chua_nhip,
        bleed_mm=tp.bleed_mm,
        khe_cat_mm=tp.khe_cat_mm,
        co_in=tp.co_in,
        che_ban_loai=tp.che_ban_loai,
        che_ban_don_gia=tp.che_ban_don_gia,
        quy_cach_in=tp.quy_cach_in,
        kho_in_dai=tp.kho_in_dai,
        kho_in_rong=tp.kho_in_rong,
        so_con=tp.so_con,
        con_auto=tp.con_auto,
        may_id=tp.may_id,
        don_gia_cong_in=tp.don_gia_cong_in,
        muc_a=list(tp.muc_a or []),
        muc_b=list(tp.muc_b or []),
        ghi_chu_ky_thuat=tp.ghi_chu_ky_thuat,
        thanh_phams=[
            ThanhPhamIn(
                cong_doan_id=cd.cong_doan_id,
                ten=cd.ten,
                don_gia=cd.don_gia,
                bu_hao=cd.bu_hao,
                so_mat=cd.so_mat,
                so_vi_tri=cd.so_vi_tri,
                dien_tich=cd.dien_tich,
                nha_cung_cap=cd.nha_cung_cap,
                ghi_chu=cd.ghi_chu,
                phi_khuon=cd.phi_khuon,
            )
            for cd in sorted(tp.thanh_phams, key=lambda x: x.thu_tu)
        ],
        vat_tus=[
            VatTuLineIn(vat_tu_id=v.vat_tu_id, ten=v.ten, don_gia=v.don_gia, ghi_chu=v.ghi_chu)
            for v in sorted(tp.vat_tus, key=lambda x: x.thu_tu)
        ],
    )
    return data.model_dump(mode="json")


def snapshot_tu_thanh_phan(db: Session, nguon: PhieuThanhPhan, actor_id: int | None) -> None:
    """Upsert 1 mẫu tái bản từ `nguon` (khoá = tên chuẩn hoá). Không tự `commit` — chạy trong
    transaction của người gọi (`OrderService.confirm()`). Tên rỗng thì bỏ qua — không có gì để
    tra cứu."""
    ten = (nguon.ten or "").strip()
    if not ten:
        return
    ten_chuan_hoa = chuan_hoa_ten(ten)
    cau_hinh = _cau_hinh_tu_thanh_phan(nguon)
    row = db.scalar(select(SanPhamTaiBan).where(SanPhamTaiBan.ten_chuan_hoa == ten_chuan_hoa))
    if row is None:
        row = SanPhamTaiBan(ten_chuan_hoa=ten_chuan_hoa)
        db.add(row)
    row.ten = ten
    row.cau_hinh_json = cau_hinh
    row.updated_by = actor_id


def tim_kiem(db: Session, q: str, size: int = 20) -> list[SanPhamTaiBan]:
    """Gợi ý theo tên — bỏ dấu, không phân biệt hoa/thường. Rỗng `q` → mới cập nhật trước."""
    stmt = select(SanPhamTaiBan).order_by(SanPhamTaiBan.updated_at.desc()).limit(size)
    q = (q or "").strip()
    if q:
        stmt = stmt.where(SanPhamTaiBan.ten_chuan_hoa.contains(chuan_hoa_ten(q)))
    return list(db.scalars(stmt).all())


def lay_chi_tiet(db: Session, id: int) -> SanPhamTaiBan | None:
    return db.get(SanPhamTaiBan, id)
