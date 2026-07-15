"""Service tính giá — LOAD danh mục (Giấy · Kẽm · Công đoạn · Bù hao) rồi gọi engine thuần.

Rút ra từ router `tinh_gia.py` để cả `/preview` (stateless) lẫn phiếu lưu (`phieu_tinh_gia`)
dùng CHUNG một code path (DRY). Router chỉ còn map payload → gọi `load_and_compute`.

Quy tắc load giữ NGUYÊN như router cũ:
  - Giấy: `db.get(GiayNguyen, giay_id)` → 404 nếu không có.
  - Kẽm: ép từ tham số `kem`; None → tra `VatTuInAn` active đầu tiên có "kem"/"kẽm" trong mã/tên.
  - Công đoạn: `cong_doan_ids` (giữ ĐÚNG thứ tự) hoặc `routing_template` của loại SP.
  - Bù hao: toàn bộ dòng đang active.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan
from ..models.loai_san_pham import LoaiSanPham
from ..models.may_thiet_bi import MayThietBi
from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn
from .thanh_phan_engine import compute_phieu
from .tinh_gia_engine import tinh_gia


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
        "so_to_bu_hao": cd.so_to_bu_hao,
        "che_do_tinh": cd.che_do_tinh,
        "pricing_basis": cd.pricing_basis,
        "setup_cost": _f(cd.setup_cost),
        "setup_time": _f(cd.setup_time),
        "run_rate": _f(cd.run_rate) if cd.run_rate is not None else None,
        "rate_tiers": cd.rate_tiers,
        "size_tiers": cd.size_tiers,
        "first_unit_floor": _f(cd.first_unit_floor) if cd.first_unit_floor is not None else None,
        "min_charge": _f(cd.min_charge) if cd.min_charge is not None else None,
        "spoilage_pct": _f(cd.spoilage_pct),
    }


def _bu_hao_to_dict(b: BuHao) -> dict:
    return {"truc": b.truc, "key_tu": b.key_tu, "key_den": b.key_den, "bac": b.bac}


def load_and_compute(
    db: Session,
    *,
    qty: int,
    pieces_per_sheet: int,
    so_mau: int,
    so_mat: int,
    so_con: int,
    giay_id: int | None,
    kem: float | None,
    loai_san_pham_id: int | None,
    cong_doan_ids: list[int] | None,
    dt_to_in_cm2: float = 0,
    dt_thanh_pham_cm2: float = 0,
) -> tuple[dict, dict]:
    """Load danh mục + gọi engine.

    Trả `(result, resolved)`:
      - `result`: dict engine đầy đủ `{meta, groups, grand_total, warnings}`.
      - `resolved`: dict phụ để snapshot, hiện có `{"giay_ten": str|None}`.
    """
    # --- Giấy ---
    giay_dict: dict | None = None
    giay_ten: str | None = None
    if giay_id is not None:
        giay = db.get(GiayNguyen, giay_id)
        if giay is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy giấy")
        giay_ten = giay.ten
        giay_dict = {
            "id": giay.id, "ten": giay.ten, "don_gia": _f(giay.don_gia),
            "don_vi_gia": giay.don_vi_gia, "gsm": giay.gsm,
        }

    # --- Kẽm: ép từ tham số, else tra VatTuInAn loại kẽm đầu tiên ---
    kem_don_gia = kem
    if kem_don_gia is None:
        rows = db.execute(
            select(VatTuInAn).where(VatTuInAn.active.is_(True)).order_by(VatTuInAn.ma.asc())
        ).scalars().all()
        # loai_vat_tu không có trên VatTuInAn phẳng → nhận diện kẽm qua tên/mã.
        pick = next((v for v in rows if "kem" in (v.ma or "").lower()
                     or "kẽm" in (v.ten or "").lower() or "kem" in (v.ten or "").lower()), None)
        kem_don_gia = _f(pick.don_gia) if pick else 0.0

    # --- Công đoạn: cong_doan_ids (giữ thứ tự) hoặc routing_template của loại SP ---
    ids: list[int] | None = cong_doan_ids
    if not ids and loai_san_pham_id is not None:
        sp = db.get(LoaiSanPham, loai_san_pham_id)
        if sp is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy loại sản phẩm")
        ids = [int(x) for x in (sp.routing_template or [])]
    ids = ids or []
    found = {cd.id: cd for cd in db.execute(
        select(CongDoan).where(CongDoan.id.in_(ids))
    ).scalars()} if ids else {}
    # giữ ĐÚNG thứ tự routing; bỏ id không tồn tại.
    cong_doans = [_cong_doan_to_dict(found[i]) for i in ids if i in found]

    # --- Bù hao rows (toàn bộ đang active) ---
    bu_hao_rows = [_bu_hao_to_dict(b) for b in db.execute(
        select(BuHao).where(BuHao.active.is_(True))
    ).scalars()]

    result = tinh_gia(
        qty=qty,
        pieces_per_sheet=pieces_per_sheet,
        so_mau=so_mau,
        so_mat=so_mat,
        so_con=so_con,
        giay=giay_dict,
        kem_don_gia=_f(kem_don_gia),
        cong_doans=cong_doans,
        bu_hao_rows=bu_hao_rows,
        dt_to_in_cm2=dt_to_in_cm2,
        dt_thanh_pham_cm2=dt_thanh_pham_cm2,
    )
    return result, {"giay_ten": giay_ten}


# ============================ Mô hình THEO THÀNH PHẦN ============================
_TP_SCALAR_FIELDS = (
    "thu_tu", "loai_thanh_phan", "ten", "kho_thanh_pham", "dai_thanh_pham", "rong_thanh_pham",
    "kho_mo_rong", "tay_gap", "so_to_per_sp", "so_luong", "loai_san_pham_id",
    "giay_id", "kho_nguyen", "don_gia_giay",
    "don_gia_don_vi", "nguon_giay", "bu_hao_so_to", "chua_xen", "chua_tay_ke", "chua_nhip",
    "chua_duoi", "chua_ca_gay", "co_in", "che_ban_loai", "che_ban_don_gia", "quy_cach_in",
    "kho_in_dai", "kho_in_rong", "so_con", "con_auto", "may_id", "don_gia_cong_in",
    "so_mau_a", "so_mau_b",
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

    # Giấy: bơm khổ (mm) + định lượng + tên; fallback đơn giá nếu component để trống.
    if tp.giay_id is not None:
        giay = db.get(GiayNguyen, tp.giay_id)
        if giay is not None:
            d["kho_dai"] = giay.kho_dai
            d["kho_rong"] = giay.kho_rong
            d["gsm"] = giay.gsm
            d["giay_ten"] = giay.ten
            if not _f(d.get("don_gia_giay")) and giay.don_vi_gia == "to":
                d["don_gia_giay"] = _f(giay.don_gia)

    # Máy: bơm khổ tờ in ② (kho_max) khi thành phần CHƯA set khổ in (để xả giấy + bình bài).
    if (not _f(d.get("kho_in_dai")) or not _f(d.get("kho_in_rong"))) and tp.may_id is not None:
        may = db.get(MayThietBi, tp.may_id)
        if may is not None:
            if not _f(d.get("kho_in_dai")):
                d["kho_in_dai"] = may.kho_max_dai or 0
            if not _f(d.get("kho_in_rong")):
                d["kho_in_rong"] = may.kho_max_rong or 0

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
    return d


def compute_phieu_snapshot(db: Session, phieu) -> dict:
    """Resolve danh mục cho MỌI thành phần + gọi engine + GHI ảnh chụp lên `phieu` (in-place).

    KHÔNG commit (caller commit). Trả `result` dict engine đầy đủ.
    """
    so_luong = int(phieu.so_luong or 0)
    tps = sorted(phieu.thanh_phans, key=lambda t: (t.thu_tu or 0, t.id or 0))
    resolved = [_resolve_thanh_phan(db, tp) for tp in tps]
    result = compute_phieu(so_luong=so_luong, thanh_phans=resolved)

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
