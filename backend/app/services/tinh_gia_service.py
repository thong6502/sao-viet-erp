"""Service tính giá THEO THÀNH PHẦN — resolve danh mục cho phiếu rồi gọi `thanh_phan_engine`.

`compute_phieu_snapshot(db, phieu)` bơm khổ/gsm/công thức giấy + máy + công đoạn (kèm
`cong_thuc_gia`) cho mọi thành phần, chạy engine, ghi ảnh chụp kết quả lên phiếu.
1 engine duy nhất (`thanh_phan_engine`); engine `/preview` cũ đã bỏ.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan
from ..models.may_thiet_bi import MayThietBi
from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn
from .thanh_phan_engine import compute_phieu


def _f(v, d: float = 0.0) -> float:
    if v is None:
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _cong_doan_to_dict(cd: CongDoan) -> dict:
    return {
        "id": cd.id,
        "ma": cd.ma,
        "ten": cd.ten,
        "nhom": cd.nhom,
        "kieu_bu_hao": cd.kieu_bu_hao,
        "bu_hao_id": cd.bu_hao_id,
        "so_to_bu_hao": cd.so_to_bu_hao,
        "che_do_tinh": cd.che_do_tinh,
        "pricing_basis": cd.pricing_basis,
        "cong_thuc_gia": cd.cong_thuc_gia,   # G2: bơm công thức cấu hình → engine dùng thay pricing_basis cũ
        "setup_cost": _f(cd.setup_cost),
        "setup_time": _f(cd.setup_time),
        "run_rate": _f(cd.run_rate) if cd.run_rate is not None else None,
        "rate_tiers": cd.rate_tiers,
        "size_tiers": cd.size_tiers,
        "first_unit_floor": _f(cd.first_unit_floor) if cd.first_unit_floor is not None else None,
        "min_charge": _f(cd.min_charge) if cd.min_charge is not None else None,
        "spoilage_pct": _f(cd.spoilage_pct),
        # Đơn vị vào/ra khai ở danh mục — engine cần để tra bù hao ĐÚNG đơn vị và biết bước nào là
        # ranh giới quy đổi. Hệ số thì engine tự có (`con`, `so_manh_xa` của chính phiếu).
        "don_vi_vao": cd.don_vi_vao,
        "don_vi_ra": cd.don_vi_ra,
    }


def _bu_hao_to_dict(b: BuHao) -> dict:
    return {"id": b.id, "ma": b.ma, "bac": b.bac}


# ============================ Mô hình THEO THÀNH PHẦN ============================
_TP_SCALAR_FIELDS = (
    "thu_tu", "loai_thanh_phan", "ten", "dai_thanh_pham", "rong_thanh_pham",
    # `don_vi_tinh` đi qua engine như mọi trường khác → lệnh sản xuất kế thừa được ĐVT từ PHIẾU,
    # thôi cảnh mỗi tầng tự lấy một đường rồi không ai kiểm chúng có khớp nhau không.
    "don_vi_tinh", "so_to_per_sp", "so_luong", "loai_san_pham_id",
    "giay_id", "kho_nguyen", "kho_nguyen_dai", "kho_nguyen_rong", "don_gia_giay",
    "don_gia_don_vi", "nguon_giay", "bu_hao_so_to", "hao_so_to", "tinh_bu_hao_cd",
    "chua_nhip", "bleed_mm", "khe_cat_mm",
    "co_in", "che_ban_loai", "che_ban_don_gia", "quy_cach_in",
    "kho_in_dai", "kho_in_rong", "so_con", "con_auto", "may_id", "don_gia_cong_in",
    "so_mau_a", "so_mau_b", "so_mau_pha",
)
_ROW_SCALAR_FIELDS = (
    "thu_tu", "cong_doan_id", "ten", "don_gia", "so_luong", "bu_hao",
    "so_mat", "so_vi_tri", "dien_tich", "nha_cung_cap", "ghi_chu",
)


def _resolve_thanh_phan(db: Session, tp) -> dict:
    """ORM PhieuThanhPhan → dict phẳng ĐÃ resolve danh mục (giấy khổ/gsm + công đoạn) cho engine."""
    d: dict = {}
    for k in _TP_SCALAR_FIELDS:
        v = getattr(tp, k, None)
        if isinstance(v, (int, str, bool)) or v is None:
            d[k] = v
        else:
            d[k] = _f(v)  # Decimal → float

    # Giấy: bơm định lượng + tên + CÔNG THỨC + đơn giá. Đơn giá/kg CHỐT CỨNG ở danh mục Giấy —
    # luôn lấy theo record (phiếu không sửa). Khổ KHÔNG còn ở danh mục → nhập tay ở phiếu (kho_nguyen).
    if tp.giay_id is not None:
        giay = db.get(GiayNguyen, tp.giay_id)
        if giay is not None:
            d["gsm"] = giay.gsm
            d["giay_ten"] = giay.ten
            d["cong_thuc_gia"] = giay.cong_thuc_gia   # G1: bơm công thức cấu hình từ danh mục Giấy
            d["don_gia_giay"] = _f(giay.don_gia)      # chốt cứng: đơn giá/kg theo danh mục
            d["don_gia_don_vi"] = giay.don_vi_gia

    # Khổ giấy nguyên ①: nhập tay ở phiếu (kho_nguyen_dai/rong). Áp cả khi khách cấp giấy.
    if _f(d.get("kho_nguyen_dai")):
        d["kho_dai"] = _f(d.get("kho_nguyen_dai"))
    if _f(d.get("kho_nguyen_rong")):
        d["kho_rong"] = _f(d.get("kho_nguyen_rong"))

    # Máy: bơm 3 nhóm KHÁC nhau (đừng gộp):
    #  · kho_may_*  = khổ giấy CHẠY máy (kho_max) → dùng XẢ GIẤY (cắt tờ in từ giấy nguyên). Luôn lấy.
    #  · kho_in_*   = khổ tờ in ② = khổ giấy in THẬT, CHƯA trừ gì. Engine tự trừ chừa khi bình bài.
    #                 KHÔNG đổ vùng in vào đây nữa: vùng in đã trừ sẵn nhíp/lề, đổ vào rồi trừ chừa
    #                 lần nữa là TRỪ HAI LẦN (hụt 14-19% số con). Thiếu → fallback khổ giấy máy.
    #  · chừa + vùng in = thông số kỹ thuật để engine trừ đúng chiều / cảnh báo. Phiếu để trống thì
    #                 lấy theo máy (xem `_compute_one`). `gripper_mm` là nhíp KẼM — KHÔNG dùng ở đây.
    if tp.may_id is not None:
        may = db.get(MayThietBi, tp.may_id)
        if may is not None:
            if may.kho_max_dai:
                d["kho_may_dai"] = may.kho_max_dai
            if may.kho_max_rong:
                d["kho_may_rong"] = may.kho_max_rong
            if not _f(d.get("kho_in_dai")):
                d["kho_in_dai"] = may.kho_max_dai or 0
            if not _f(d.get("kho_in_rong")):
                d["kho_in_rong"] = may.kho_max_rong or 0
            d["nhip_giay_mm"] = may.nhip_giay_mm or 0
            d["le_hong_mm"] = may.le_hong_mm or 0
            d["duoi_thang_mau_mm"] = may.duoi_thang_mau_mm or 0
            d["vung_in_dai"] = may.vung_in_dai or 0
            d["vung_in_rong"] = may.vung_in_rong or 0

    # Dòng gia công sau in: bơm cấu hình công đoạn khi dòng KHÔNG có đơn giá phẳng.
    rows: list[dict] = []
    for row in sorted(tp.thanh_phams, key=lambda r: (r.thu_tu or 0, r.id or 0)):
        rd: dict = {}
        for k in _ROW_SCALAR_FIELDS:
            v = getattr(row, k, None)
            rd[k] = v if (isinstance(v, (int, str, bool)) or v is None) else _f(v)
        if not _f(rd.get("don_gia")) and row.cong_doan_id is not None:
            cd = db.get(CongDoan, row.cong_doan_id)
            if cd is not None:
                rd["cong_doan"] = _cong_doan_to_dict(cd)
        rows.append(rd)
    d["thanh_phams"] = rows

    # Vật tư in ấn thêm tay → dòng NVL: kéo CÔNG THỨC + đơn giá + đơn vị + tên từ danh mục
    # (giống Giấy). don_gia dòng = ghi đè; 0 → lấy danh mục.
    vts: list[dict] = []
    for vt in sorted(getattr(tp, "vat_tus", []) or [], key=lambda r: (r.thu_tu or 0, r.id or 0)):
        vd: dict = {
            "vat_tu_id": vt.vat_tu_id,
            "ten": vt.ten or "",
            "don_gia": _f(vt.don_gia),
            "so_luong": vt.so_luong,
            "ghi_chu": vt.ghi_chu,
        }
        if vt.vat_tu_id is not None:
            m = db.get(VatTuInAn, vt.vat_tu_id)
            if m is not None:
                vd["cong_thuc_gia"] = m.cong_thuc_gia
                vd["don_vi_gia"] = m.don_vi_gia
                if not vd["ten"]:
                    vd["ten"] = m.ten
                if not vd["don_gia"]:
                    vd["don_gia"] = _f(m.don_gia)
        vts.append(vd)
    d["vat_tus"] = vts
    return d


def compute_phieu_snapshot(db: Session, phieu) -> dict:
    """Resolve danh mục cho MỌI thành phần + gọi engine + GHI ảnh chụp lên `phieu` (in-place).

    KHÔNG commit (caller commit). Trả `result` dict engine đầy đủ.
    """
    so_luong = int(phieu.so_luong or 0)
    tps = sorted(phieu.thanh_phans, key=lambda t: (t.thu_tu or 0, t.id or 0))
    resolved = [_resolve_thanh_phan(db, tp) for tp in tps]
    bu_hao_rows = [_bu_hao_to_dict(b) for b in db.execute(
        select(BuHao).where(BuHao.active.is_(True))
    ).scalars()]
    result = compute_phieu(so_luong=so_luong, thanh_phans=resolved, bu_hao_rows=bu_hao_rows)

    # gán giá vốn từng thành phần.
    for comp in result["meta"]["components"]:
        idx = comp["idx"]
        if 0 <= idx < len(tps):
            tps[idx].gia_von_tp = comp["gia_von_tp"]

    tong = float(result.get("grand_total") or 0)
    phieu.tong_gia_von = tong
    phieu.gia_von_don = float(result.get("meta", {}).get("gia_von_don") or 0)  # đơn giá bình quân (Σ vốn / Σ SL)
    phieu.result_json = result
    phieu.warnings_json = result.get("warnings") or []
    return result
