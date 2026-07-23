"""Service Lệnh sản xuất (LSX) — Kế hoạch nhận đơn Sale đã bàn giao → bung lệnh dự kiến → tạo lệnh.

Ba tầng như print MIS: Job (`orders`) → Part (`lsx`) → Operation (`lsx_cong_doan`).

Nguyên tắc:
- **Nguồn sinh lệnh là DÒNG ĐƠN** (`order_lines`), không quét thẳng phiếu tính giá — vì khách có thể
  chốt MỘT PHẦN báo giá, và đơn mới là bản cam kết bán.
- **Số lượng lấy từ ĐƠN**: chạy lại engine (hàm THUẦN) với `so_luong = order_lines.qty` để ra số tờ
  đúng cam kết. KHÔNG gọi `compute_phieu_snapshot` (hàm đó ghi đè ảnh chụp lên phiếu tính giá).
- **Máy chỉ đề xuất**: routing/đơn vị/số lượng vào-ra copy sang lệnh là MẶC ĐỊNH, kế hoạch sửa hết.
- **Snapshot**: quy cách + routing chụp lúc tạo; sửa phiếu tính giá về sau không lay lệnh đã tạo.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.khuon_be import KhuonBe
from ..models.lsx import (
    DV_CAI,
    DV_KEM,
    DV_TO,
    LOAI_MOI,
    TT_CHO_BO_SUNG,
    TT_NHAP,
    TT_SAN_SANG,
    TRANG_THAI_LSX,
    Lsx,
    LsxCongDoan,
)
from ..models.may_thiet_bi import MayThietBi
from ..models.order import STATUS_ORDERED, Order, OrderLine
from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from ..models.quotation import QuoteVersion
from ..models.user import User
from ..services.thanh_phan_engine import compute_phieu
from ..services.tinh_gia_service import _bu_hao_to_dict, _resolve_thanh_phan

# Công đoạn sau xén → đếm bằng CON (thành phẩm); còn lại đếm bằng TỜ. Heuristic theo tên để điền
# MẶC ĐỊNH cho kế hoạch, không phải luật — mọi dòng sửa được.
_TEN_DEM_CON = ("dán", "gấp", "đóng gói", "cắt thành phẩm", "kcs", "thùng", "bao bì", "vào bìa",
                "đóng cuốn", "thành phẩm", "nhập kho")
# Công đoạn cần khuôn bế (checklist "chờ bổ sung").
_TEN_CAN_KHUON = ("bế", "be ", "cấn")


class LsxError(Exception):
    """Lỗi nghiệp vụ LSX (router map sang HTTP)."""


class LsxNotFound(LsxError):
    pass


class LsxValidationError(LsxError):
    pass


class LsxConflict(LsxError):
    pass


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


class LsxService:
    def __init__(self, db: Session, repo, audit, sequence) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.sequence = sequence

    # ================= tra cứu phụ trợ =================

    def _bu_hao_rows(self) -> list[dict]:
        return [
            _bu_hao_to_dict(b)
            for b in self.db.execute(select(BuHao).where(BuHao.active.is_(True))).scalars()
        ]

    def _customer_name(self, order: Order) -> str | None:
        if not order.customer_id:
            return None
        c = self.db.get(Customer, order.customer_id)
        return c.name if c else None

    def _user_name(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        u = self.db.get(User, user_id)
        return (u.name or u.username) if u else None

    def _dept_names(self, ids: set[int]) -> dict[int, str]:
        from ..models.department import Department

        if not ids:
            return {}
        rows = self.db.execute(select(Department.id, Department.name).where(Department.id.in_(ids))).all()
        return {i: n for i, n in rows}

    def _may_names(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        rows = self.db.execute(
            select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(ids))
        ).all()
        return {i: n for i, n in rows}

    def _thanh_phan(self, tp_id: int | None) -> PhieuThanhPhan | None:
        if not tp_id:
            return None
        return self.db.execute(
            select(PhieuThanhPhan)
            .where(PhieuThanhPhan.id == tp_id)
            .options(
                selectinload(PhieuThanhPhan.thanh_phams),
                selectinload(PhieuThanhPhan.vat_tus),
            )
        ).scalar_one_or_none()

    # ================= HÀNG CHỜ =================

    def hang_cho(self) -> list[dict]:
        """Đơn Sale đã chuyển xuống SX mà CÒN dòng chưa lên lệnh."""
        orders = self.repo.orders_ban_giao()
        if not orders:
            return []
        line_ids = [ln.id for o in orders for ln in o.lines]
        da_co = self.repo.by_order_lines(line_ids)
        out: list[dict] = []
        for o in orders:
            so_dong = len(o.lines)
            so_co = sum(1 for ln in o.lines if ln.id in da_co)
            if so_dong and so_co >= so_dong:
                continue  # đã đủ lệnh → rời hàng chờ
            out.append({
                "order_id": o.id,
                "order_no": o.order_no,
                "customer_name": self._customer_name(o),
                "sale_name": self._user_name(o.sale_user_id),
                "delivery_committed_date": o.delivery_committed_date,
                "is_rush": bool(o.is_rush),
                "production_note": o.production_note,
                "san_xuat_released_at": o.san_xuat_released_at,
                "so_dong": so_dong,
                "so_dong_co_lsx": so_co,
            })
        return out

    # ================= tính số cho 1 dòng đơn =================

    def _tinh_dong(self, line: OrderLine, tp: PhieuThanhPhan | None, warnings: list[str]) -> dict:
        """Chạy engine (hàm thuần) cho 1 dòng đơn với SL CỦA ĐƠN → số tờ / bù hao / kẽm / lượt.

        Trả `{comp, quy_cach, routing, sl_ptg}`. `tp=None` (đơn nhập giá tay) → số 0, routing rỗng.
        """
        qty = int(line.qty or 0)
        if tp is None:
            return {"comp": {}, "quy_cach": None, "routing": [], "sl_ptg": None}

        resolved = _resolve_thanh_phan(self.db, tp)
        sl_ptg = int(resolved.get("so_luong") or 0)
        # ÉP số lượng theo ĐƠN: engine ưu tiên `tp["so_luong"]` nếu > 0, nên phải ghi đè.
        resolved["so_luong"] = qty
        result = compute_phieu(
            so_luong=qty, thanh_phans=[resolved], bu_hao_rows=self._bu_hao_rows(), warnings=warnings
        )
        comps = result.get("meta", {}).get("components") or []
        comp = comps[0] if comps else {}

        quy_cach = {
            "dai_thanh_pham": resolved.get("dai_thanh_pham"),
            "rong_thanh_pham": resolved.get("rong_thanh_pham"),
            "kho_thanh_pham": resolved.get("kho_thanh_pham"),
            "kho_mo_rong": resolved.get("kho_mo_rong"),
            "tay_gap": resolved.get("tay_gap"),
            "so_to_per_sp": resolved.get("so_to_per_sp"),
            "giay_id": resolved.get("giay_id"),
            "giay_ten": resolved.get("giay_ten") or resolved.get("kho_nguyen"),
            "gsm": resolved.get("gsm"),
            "nguon_giay": resolved.get("nguon_giay"),
            "kho_nguyen_dai": resolved.get("kho_dai") or resolved.get("kho_nguyen_dai"),
            "kho_nguyen_rong": resolved.get("kho_rong") or resolved.get("kho_nguyen_rong"),
            "kho_in_dai": resolved.get("kho_in_dai"),
            "kho_in_rong": resolved.get("kho_in_rong"),
            "quy_cach_in": resolved.get("quy_cach_in"),
            "so_mau_a": resolved.get("so_mau_a"),
            "so_mau_b": resolved.get("so_mau_b"),
            "chua_xen": resolved.get("chua_xen"),
            "chua_tay_ke": resolved.get("chua_tay_ke"),
            "chua_nhip": resolved.get("chua_nhip"),
            "chua_duoi": resolved.get("chua_duoi"),
            "chua_ca_gay": resolved.get("chua_ca_gay"),
            "so_kem": comp.get("so_kem"),
            "so_luot": comp.get("so_luot"),
            "so_con": comp.get("con"),
            "so_manh_xa": comp.get("so_manh_xa"),
            "ghi_chu_ky_thuat": getattr(tp, "ghi_chu_ky_thuat", None),
        }

        routing: list[dict] = []
        for i, row in enumerate(resolved.get("thanh_phams") or []):
            cd = row.get("cong_doan") or {}
            cd_id = row.get("cong_doan_id")
            if not cd and cd_id:
                obj = self.db.get(CongDoan, cd_id)
                if obj is not None:
                    cd = {"nhom": obj.nhom, "ten": obj.ten, "department_id": obj.department_id}
            else:
                # `_cong_doan_to_dict` không bơm department_id → lấy thêm.
                if cd_id:
                    obj = self.db.get(CongDoan, cd_id)
                    if obj is not None:
                        cd = {**cd, "department_id": obj.department_id}
            routing.append({
                "thu_tu": i,
                "cong_doan_id": cd_id,
                "ten": row.get("ten") or cd.get("ten") or "Công đoạn",
                "nhom": cd.get("nhom"),
                "department_id": cd.get("department_id"),
                "thue_ngoai": bool(row.get("nha_cung_cap")),
                "nha_cung_cap": row.get("nha_cung_cap"),
            })
        return {"comp": comp, "quy_cach": quy_cach, "routing": routing, "sl_ptg": sl_ptg}

    def _thieu(self, *, order: Order, tp: PhieuThanhPhan | None, quy_cach: dict | None,
               routing: list[dict], khuon_be_id: int | None) -> list[str]:
        """Checklist 'job readiness' — thiếu gì thì lệnh nằm ở CHỜ BỔ SUNG."""
        thieu: list[str] = []
        if tp is None:
            thieu.append("khong_co_ptg")
        else:
            qc = quy_cach or {}
            if not qc.get("giay_id"):
                thieu.append("thieu_giay")
            if not (qc.get("dai_thanh_pham") and qc.get("rong_thanh_pham")):
                thieu.append("thieu_kho")
            if not routing:
                thieu.append("thieu_routing")
        if order.delivery_committed_date is None:
            thieu.append("thieu_ngay_giao")
        can_khuon = any(any(k in _norm(r.get("ten")) for k in _TEN_CAN_KHUON) for r in routing)
        if can_khuon and not khuon_be_id:
            thieu.append("thieu_khuon")
        return thieu

    # ================= PREVIEW =================

    def preview(self, order_id: int) -> dict:
        order = self.repo.order_with_lines(order_id)
        if order is None:
            raise LsxNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED or order.san_xuat_released_at is None:
            raise LsxConflict("Đơn chưa được chuyển xuống sản xuất")

        da_co = self.repo.by_order_lines([ln.id for ln in order.lines])
        warnings: list[str] = []
        lines: list[dict] = []
        for line in order.lines:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp, warnings)
            comp = calc["comp"]
            existing = da_co.get(line.id)
            ptg_ma = None
            if tp is not None:
                ptg = self.db.get(PhieuTinhGia, tp.phieu_id)
                ptg_ma = ptg.ma if ptg else None
            dept_ids = {r["department_id"] for r in calc["routing"] if r.get("department_id")}
            dept_names = self._dept_names(dept_ids)
            lines.append({
                "order_line_id": line.id,
                "ten": line.description or (tp.ten if tp else "") or "Sản phẩm",
                "so_luong_dat": int(line.qty or 0),
                "don_vi_tinh": line.don_vi_tinh or "cái",
                "phieu_thanh_phan_id": line.phieu_thanh_phan_id,
                "ptg_ma": ptg_ma,
                "bu_hao_to": int(round(float(comp.get("bu_hao_auto") or 0) + float(comp.get("bu_hao_tay") or 0))),
                "so_to_ke_hoach": int(round(float(comp.get("to_dau_vao") or 0))),
                "so_to_nguyen": int(comp.get("to_nguyen") or 0),
                "so_con": int(comp.get("con") or 1),
                "so_kem": int(comp.get("so_kem") or 0),
                "so_luot": int(round(float(comp.get("so_luot") or 0))),
                "routing": [
                    {**r, "department_ten": dept_names.get(r.get("department_id"))}
                    for r in calc["routing"]
                ],
                "quy_cach": calc["quy_cach"],
                "thieu": self._thieu(
                    order=order, tp=tp, quy_cach=calc["quy_cach"],
                    routing=calc["routing"], khuon_be_id=None,
                ),
                "sl_ptg": calc["sl_ptg"] if calc["sl_ptg"] and calc["sl_ptg"] != int(line.qty or 0) else None,
                "lsx_id": existing.id if existing else None,
                "lsx_ma": existing.ma if existing else None,
            })
        return {
            "order_id": order.id,
            "order_no": order.order_no,
            "customer_name": self._customer_name(order),
            "sale_name": self._user_name(order.sale_user_id),
            "delivery_committed_date": order.delivery_committed_date,
            "is_rush": bool(order.is_rush),
            "production_note": order.production_note,
            "lines": lines,
            "warnings": warnings,
        }

    # ================= TẠO LỆNH =================

    def _default_qty_don_vi(self, r: dict, *, comp: dict, so_luong_dat: int, bu_hao: int) -> tuple[float, float, str]:
        """SL vào/ra + đơn vị MẶC ĐỊNH của 1 bước (kế hoạch sửa được)."""
        nhom = r.get("nhom")
        to_vao = float(comp.get("to_dau_vao") or 0)
        to_ra = float(comp.get("to_sau_in") or to_vao)
        if nhom == "prepress":
            kem = float(comp.get("so_kem") or 0)
            return kem, kem, DV_KEM
        if nhom == "print":
            return to_vao, to_ra, DV_TO
        if any(k in _norm(r.get("ten")) for k in _TEN_DEM_CON):
            return float(so_luong_dat + bu_hao), float(so_luong_dat), DV_CAI
        return to_ra, to_ra, DV_TO

    def tao(self, *, order_id: int, order_line_ids: list[int], actor) -> list[Lsx]:
        order = self.repo.order_with_lines(order_id)
        if order is None:
            raise LsxNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED:
            raise LsxConflict("Đơn chưa chốt / đã hủy — không tạo lệnh sản xuất")
        if order.san_xuat_released_at is None:
            raise LsxConflict("Sale chưa chuyển đơn xuống sản xuất")

        by_id = {ln.id: ln for ln in order.lines}
        chosen = [by_id[i] for i in order_line_ids if i in by_id]
        if not chosen:
            raise LsxValidationError("Chưa chọn dòng nào của đơn để tạo lệnh")
        if len(chosen) != len(set(order_line_ids)):
            raise LsxValidationError("Có dòng không thuộc đơn hàng này")

        da_co = self.repo.by_order_lines([ln.id for ln in chosen])
        trung = [ln.id for ln in chosen if ln.id in da_co]
        if trung:
            raise LsxConflict("Dòng đã có lệnh sản xuất — không tạo trùng")

        quote_version_id = order.quotation_id and self._quote_version_id(order.quotation_id)
        warnings: list[str] = []
        created: list[Lsx] = []
        for line in chosen:
            tp = self._thanh_phan(line.phieu_thanh_phan_id)
            calc = self._tinh_dong(line, tp, warnings)
            comp = calc["comp"]
            bu_hao = int(round(float(comp.get("bu_hao_auto") or 0) + float(comp.get("bu_hao_tay") or 0)))
            so_luong_dat = int(line.qty or 0)
            thieu = self._thieu(
                order=order, tp=tp, quy_cach=calc["quy_cach"], routing=calc["routing"],
                khuon_be_id=None,
            )
            lsx = Lsx(
                ma=self.sequence.generate_code("job"),
                loai=LOAI_MOI,
                ten=line.description or (tp.ten if tp else "") or "Sản phẩm",
                order_id=order.id,
                order_line_id=line.id,
                quote_version_id=quote_version_id or None,
                phieu_thanh_phan_id=line.phieu_thanh_phan_id,
                so_luong_dat=so_luong_dat,
                don_vi_tinh=line.don_vi_tinh or "cái",
                bu_hao_to=bu_hao,
                so_to_ke_hoach=int(round(float(comp.get("to_dau_vao") or 0))),
                so_to_nguyen=int(comp.get("to_nguyen") or 0),
                so_con=int(comp.get("con") or 1),
                ban_giao_at=order.san_xuat_released_at,
                han_giao_khach=order.delivery_committed_date,
                is_rush=bool(order.is_rush),
                quy_cach_json=calc["quy_cach"],
                may_id=(calc["quy_cach"] or {}).get("may_id") or (tp.may_id if tp else None),
                trang_thai=TT_CHO_BO_SUNG if thieu else TT_NHAP,
                nguoi_phu_trach_id=actor.id,
                created_by=actor.id,
            )
            for r in calc["routing"]:
                vao, ra, dv = self._default_qty_don_vi(
                    r, comp=comp, so_luong_dat=so_luong_dat, bu_hao=bu_hao
                )
                lsx.cong_doans.append(LsxCongDoan(
                    thu_tu=r["thu_tu"],
                    cong_doan_id=r.get("cong_doan_id"),
                    ten=r.get("ten") or "Công đoạn",
                    nhom=r.get("nhom"),
                    department_id=r.get("department_id"),
                    so_luong_vao=vao,
                    so_luong_ra=ra,
                    don_vi=dv,
                    thue_ngoai=bool(r.get("thue_ngoai")),
                    nha_cung_cap=r.get("nha_cung_cap"),
                ))
            self.repo.add(lsx)
            created.append(lsx)
            self.audit.create(
                actor_user_id=actor.id, action="create_lsx", target=f"lsx:{lsx.id}",
                detail=f"Tạo lệnh {lsx.ma} — {lsx.ten} (đơn {order.order_no}, "
                       f"{so_luong_dat:,} {lsx.don_vi_tinh})".replace(",", "."),
            )
        self.repo.commit()
        return created

    def _quote_version_id(self, quotation_id: int) -> int | None:
        from ..models.quotation import Quote

        q = self.db.get(Quote, quotation_id)
        return q.current_version_id if q else None

    # ================= ĐỌC / SỬA =================

    def get(self, lsx_id: int) -> Lsx:
        lsx = self.repo.get(lsx_id)
        if lsx is None:
            raise LsxNotFound("Không tìm thấy lệnh sản xuất")
        return lsx

    def thieu_cua(self, lsx: Lsx) -> list[str]:
        order = self.db.get(Order, lsx.order_id)
        tp = self._thanh_phan(lsx.phieu_thanh_phan_id)
        routing = [{"ten": cd.ten, "nhom": cd.nhom} for cd in lsx.cong_doans]
        thieu: list[str] = []
        qc = lsx.quy_cach_json or {}
        if lsx.phieu_thanh_phan_id is None:
            thieu.append("khong_co_ptg")
        else:
            if not qc.get("giay_id"):
                thieu.append("thieu_giay")
            if not (qc.get("dai_thanh_pham") and qc.get("rong_thanh_pham")):
                thieu.append("thieu_kho")
            if not routing:
                thieu.append("thieu_routing")
        if (order.delivery_committed_date if order else None) is None and lsx.han_giao_khach is None:
            thieu.append("thieu_ngay_giao")
        if any(any(k in _norm(r["ten"]) for k in _TEN_CAN_KHUON) for r in routing) and not lsx.khuon_be_id:
            thieu.append("thieu_khuon")
        # tp chỉ dùng để xác nhận nguồn còn sống — lệnh vẫn chạy được khi PTG đã đổi/xoá.
        del tp
        return thieu

    def detail_dict(self, lsx: Lsx) -> dict:
        """Ghép dữ liệu hiển thị (tên đơn/khách/máy/tổ/khuôn) cho 1 lệnh."""
        order = self.db.get(Order, lsx.order_id)
        dept_ids = {cd.department_id for cd in lsx.cong_doans if cd.department_id}
        may_ids = {cd.may_id for cd in lsx.cong_doans if cd.may_id}
        if lsx.may_id:
            may_ids.add(lsx.may_id)
        dept_names = self._dept_names(dept_ids)
        may_names = self._may_names(may_ids)
        khuon = self.db.get(KhuonBe, lsx.khuon_be_id) if lsx.khuon_be_id else None
        ptg_id = ptg_ma = None
        tp = self._thanh_phan(lsx.phieu_thanh_phan_id)
        if tp is not None:
            ptg = self.db.get(PhieuTinhGia, tp.phieu_id)
            ptg_id, ptg_ma = (ptg.id, ptg.ma) if ptg else (None, None)
        quote_number = quote_version_number = None
        if lsx.quote_version_id:
            ver = self.db.get(QuoteVersion, lsx.quote_version_id)
            if ver is not None:
                quote_version_number = ver.version_number
                from ..models.quotation import Quote

                quote = self.db.get(Quote, ver.quote_id)
                quote_number = quote.quote_number if quote else None
        return {
            "order_no": order.order_no if order else None,
            "customer_name": self._customer_name(order) if order else None,
            "customer_po_no": order.customer_po_no if order else None,
            "sale_name": self._user_name(order.sale_user_id) if order else None,
            "quote_number": quote_number,
            "quote_version_number": quote_version_number,
            "ptg_id": ptg_id,
            "ptg_ma": ptg_ma,
            "khuon_be_ten": (khuon.ten if khuon else None),
            "may_ten": may_names.get(lsx.may_id),
            "nguoi_phu_trach_ten": self._user_name(lsx.nguoi_phu_trach_id),
            "thieu": self.thieu_cua(lsx),
            "cong_doans": [
                {
                    "id": cd.id, "thu_tu": cd.thu_tu, "cong_doan_id": cd.cong_doan_id,
                    "ten": cd.ten, "nhom": cd.nhom,
                    "department_id": cd.department_id,
                    "department_ten": dept_names.get(cd.department_id),
                    "may_id": cd.may_id, "may_ten": may_names.get(cd.may_id),
                    "so_luong_vao": float(cd.so_luong_vao or 0),
                    "so_luong_ra": float(cd.so_luong_ra or 0),
                    "don_vi": cd.don_vi, "hao_hut": float(cd.hao_hut or 0),
                    "thue_ngoai": bool(cd.thue_ngoai), "nha_cung_cap": cd.nha_cung_cap,
                    "ghi_chu": cd.ghi_chu,
                }
                for cd in lsx.cong_doans
            ],
        }

    def list_rows(self, **kw) -> list[dict]:
        rows = self.repo.list(**kw)
        order_ids = {r.order_id for r in rows}
        orders = {
            o.id: o for o in self.db.execute(select(Order).where(Order.id.in_(order_ids))).scalars()
        } if order_ids else {}
        dept_ids = {cd.department_id for r in rows for cd in r.cong_doans if cd.department_id}
        dept_names = self._dept_names(dept_ids)
        out: list[dict] = []
        for r in rows:
            o = orders.get(r.order_id)
            first = r.cong_doans[0] if r.cong_doans else None
            out.append({
                "id": r.id, "ma": r.ma, "loai": r.loai, "ten": r.ten, "trang_thai": r.trang_thai,
                "order_id": r.order_id,
                "order_no": o.order_no if o else None,
                "customer_name": self._customer_name(o) if o else None,
                "so_luong_dat": r.so_luong_dat, "don_vi_tinh": r.don_vi_tinh,
                "so_to_ke_hoach": r.so_to_ke_hoach,
                "han_giao_khach": r.han_giao_khach, "han_hoan_thanh_sx": r.han_hoan_thanh_sx,
                "is_rush": bool(r.is_rush),
                "to_dau_ten": dept_names.get(first.department_id) if first else None,
                "so_cong_doan": len(r.cong_doans),
            })
        return out

    def update(self, *, lsx_id: int, payload, actor) -> Lsx:
        lsx = self.get(lsx_id)
        data = payload.model_dump(exclude_unset=True)
        changed: list[str] = []
        for field in (
            "ten", "so_luong_dat", "don_vi_tinh", "bu_hao_to", "so_to_ke_hoach", "so_to_nguyen",
            "so_con", "han_hoan_thanh_sx", "is_rush", "khuon_be_id", "may_id",
            "nguoi_phu_trach_id", "ghi_chu",
        ):
            if field in data and getattr(lsx, field) != data[field]:
                setattr(lsx, field, data[field])
                changed.append(field)
        if changed:
            # Sửa xong mà hết thiếu → về NHÁP; còn thiếu → CHỜ BỔ SUNG (giữ nguyên nếu đã SẴN SÀNG
            # và vẫn đủ dữ liệu).
            thieu = self.thieu_cua(lsx)
            if thieu:
                lsx.trang_thai = TT_CHO_BO_SUNG
            elif lsx.trang_thai == TT_CHO_BO_SUNG:
                lsx.trang_thai = TT_NHAP
            self.audit.create(
                actor_user_id=actor.id, action="update_lsx", target=f"lsx:{lsx.id}",
                detail=f"Sửa lệnh {lsx.ma}: {', '.join(changed)}",
            )
        self.repo.commit()
        return self.get(lsx_id)

    def replace_routing(self, *, lsx_id: int, rows_in, actor) -> Lsx:
        lsx = self.get(lsx_id)
        truoc = len(lsx.cong_doans)
        rows: list[LsxCongDoan] = []
        for i, r in enumerate(rows_in):
            d = r.model_dump(exclude_unset=True)
            cd_id = d.get("cong_doan_id")
            ten = d.get("ten")
            nhom = d.get("nhom")
            dept = d.get("department_id")
            if cd_id and (not ten or nhom is None or dept is None):
                cd = self.db.get(CongDoan, cd_id)
                if cd is not None:
                    ten = ten or cd.ten
                    nhom = nhom if nhom is not None else cd.nhom
                    dept = dept if dept is not None else cd.department_id
            rows.append(LsxCongDoan(
                thu_tu=d.get("thu_tu", i),
                cong_doan_id=cd_id,
                ten=ten or "Công đoạn",
                nhom=nhom,
                department_id=dept,
                may_id=d.get("may_id"),
                so_luong_vao=d.get("so_luong_vao") or 0,
                so_luong_ra=d.get("so_luong_ra") or 0,
                don_vi=d.get("don_vi") or DV_TO,
                hao_hut=d.get("hao_hut") or 0,
                thue_ngoai=bool(d.get("thue_ngoai")),
                nha_cung_cap=d.get("nha_cung_cap"),
                ghi_chu=d.get("ghi_chu"),
            ))
        self.repo.replace_cong_doans(lsx, rows)
        thieu = self.thieu_cua(lsx)
        if thieu and lsx.trang_thai != TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_CHO_BO_SUNG
        elif not thieu and lsx.trang_thai == TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_NHAP
        self.audit.create(
            actor_user_id=actor.id, action="update_lsx_routing", target=f"lsx:{lsx.id}",
            detail=f"Sửa routing lệnh {lsx.ma}: {truoc} → {len(rows)} công đoạn",
        )
        self.repo.commit()
        return self.get(lsx_id)

    def set_trang_thai(self, *, lsx_id: int, trang_thai: str, actor) -> Lsx:
        lsx = self.get(lsx_id)
        if trang_thai not in TRANG_THAI_LSX:
            raise LsxValidationError("Trạng thái không hợp lệ")
        if trang_thai == TT_SAN_SANG:
            thieu = self.thieu_cua(lsx)
            if thieu:
                raise LsxConflict("Còn thiếu dữ liệu — bổ sung xong mới đánh dấu sẵn sàng")
        lsx.trang_thai = trang_thai
        self.audit.create(
            actor_user_id=actor.id, action="lsx_trang_thai", target=f"lsx:{lsx.id}",
            detail=f"Lệnh {lsx.ma} → {trang_thai}",
        )
        self.repo.commit()
        return self.get(lsx_id)

    def xoa(self, *, lsx_id: int, actor) -> int:
        """Xoá lệnh chưa phát hành → dòng đơn quay lại hàng chờ. Trả `order_id` để router bắn SSE."""
        lsx = self.get(lsx_id)
        order_id, ma = lsx.order_id, lsx.ma
        self.repo.delete(lsx)
        self.audit.create(
            actor_user_id=actor.id, action="delete_lsx", target=f"lsx:{lsx_id}",
            detail=f"Xoá lệnh {ma}",
        )
        self.repo.commit()
        return order_id
