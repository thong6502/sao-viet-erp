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

from datetime import date, datetime, timedelta, timezone
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.khuon_be import KhuonBe
from ..models.lsx import (
    DV_BAI,
    DV_CAI,
    DV_KEM,
    DV_TO,
    LB_CHO,
    LB_KCS,
    LB_MAY,
    LB_THUE_NGOAI,
    LB_TO,
    LB_XA_TO,
    LOAI_BUOC_THEO_TO,
    LOAI_MOI,
    NS_BAI_GIO,
    NS_CAI_GIO,
    NS_KEM_GIO,
    NS_TO_GIO,
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
# Công đoạn cần khuôn bế (checklist "chờ bổ sung"). Cũng là bước ĐỔI ĐƠN VỊ tờ → con.
_TEN_CAN_KHUON = ("bế", "be ", "cấn")
# Đơn vị năng suất luôn ĐI THEO đơn vị đầu vào của bước (công thức là `so_luong_vao / nang_suat`),
# nên suy ra chứ không lưu cột riêng — lưu riêng là mở đường cho hai thứ lệch nhau.
_DV_VAO_SANG_NS = {DV_TO: NS_TO_GIO, DV_CAI: NS_CAI_GIO, DV_KEM: NS_KEM_GIO, DV_BAI: NS_BAI_GIO}


def _don_vi_theo_buoc(ten: str | None, nhom: str | None, *, con: int = 1) -> tuple[str, str, float]:
    """Đơn vị VÀO/RA + hệ số quy đổi mặc định của 1 bước, suy từ nhóm + tên công đoạn.

    Tách riêng để `_default_buoc` (lúc bung lệnh) và `mac_dinh_buoc` (lúc kế hoạch ĐỔI công đoạn
    giữa chừng) dùng CHUNG một luật — nhân bản sang frontend là đẻ nguồn sai lệch.
    """
    low = _norm(ten)
    if nhom == "prepress":
        return DV_KEM, DV_KEM, 1.0
    if nhom == "print":
        return DV_TO, DV_TO, 1.0
    if any(k in low for k in _TEN_CAN_KHUON):
        # BẾ = ranh giới đổi đơn vị: tờ vào → CON ra (ví dụ §4.2 của tài liệu nghiệp vụ).
        return DV_TO, DV_CAI, float(max(con, 1))
    if any(k in low for k in _TEN_DEM_CON):
        return DV_CAI, DV_CAI, 1.0
    return DV_TO, DV_TO, 1.0


def _nang_suat_buoc(may, cd_obj, dv_vao: str) -> tuple[float | None, str | None]:
    """Năng suất + đơn vị của 1 bước: MÁY trước, không có thì lấy danh mục công đoạn (việc làm tay).

    Máy khai đơn vị tốc độ khác `to_gio` thì BỎ QUA — xưởng chỉ in offset tờ, dùng số đó làm
    tờ/giờ là sai thầm lặng. Đơn vị năng suất SUY từ đơn vị vào, không đọc cột nào.
    """
    ns = None
    if may is not None and _f(may.toc_do) > 0 and may.don_vi_toc_do == NS_TO_GIO and dv_vao == DV_TO:
        ns = _f(may.toc_do)
    elif cd_obj is not None and _f(cd_obj.nang_suat) > 0:
        ns = _f(cd_obj.nang_suat)
    return ns, (_DV_VAO_SANG_NS.get(dv_vao) if ns else None)
# Heuristic suy LOẠI BƯỚC từ tên (§3). Chỉ để điền mặc định — người kế hoạch đổi được ở drawer.
_TEN_KCS = ("kcs", "kiểm tra", "duyệt màu")
_TEN_CHO = ("chờ", "khô mực", "khô keo", "ủ ")
_TEN_XA_TO = ("xả tờ", "chia bán thành phẩm", "xả bán thành phẩm")
# Bước làm bằng TAY theo tổ (nhiều người làm song song được → `so_nhan_cong` mới có nghĩa).
_TEN_LAM_TAY = ("dán", "gấp", "đóng gói", "vào bìa", "đóng cuốn", "bao bì", "thùng")

# Số giờ làm việc quy ước 1 ngày, dùng quy đổi lead-time phút → ngày. CHƯA đấu `work_calendar`
# (nghỉ lễ/ca kíp) — lát này chỉ cần con số thô để cảnh báo "có nguy cơ trễ hạn giao".
GIO_LAM_MOI_NGAY = 8.0


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _suy_loai_buoc(ten: str | None, nhom: str | None, thue_ngoai: bool) -> str:
    """Loại bước MẶC ĐỊNH khi bung routing từ bài tính giá. Thuê ngoài thắng trước, rồi tới tên."""
    if thue_ngoai:
        return LB_THUE_NGOAI
    low = _norm(ten)
    if any(k in low for k in _TEN_CHO):
        return LB_CHO
    if any(k in low for k in _TEN_XA_TO):
        return LB_XA_TO
    if any(k in low for k in _TEN_KCS):
        return LB_KCS
    if nhom in ("prepress", "print"):
        return LB_MAY
    if any(k in low for k in _TEN_LAM_TAY):
        return LB_TO
    return LB_MAY


def _so_luot_chay(comp: dict) -> int:
    """Số lượt tờ chạy qua máy in (1 mặt = 1, in trở = 2).

    Engine chỉ xuất `so_luot` = TỔNG lượt tờ (`to_dau_vao × số mặt`) chứ không xuất số mặt, nên
    chia ngược ra. Lấy nhầm `so_luot` sẽ nhân thời gian chạy lên hàng nghìn lần.
    """
    to_vao = _f(comp.get("to_dau_vao"))
    tong_luot = _f(comp.get("so_luot"))
    if to_vao <= 0 or tong_luot <= 0:
        return 1
    return max(round(tong_luot / to_vao), 1)


def _routing_van_tay(cong_doans) -> list[dict]:
    """Vân tay routing để so "đã đổi so với bài tính giá" — chỉ giữ phần CẤU TRÚC (bước nào, làm
    ở đâu). Cố tình KHÔNG chụp số lượng/thời gian: sửa số là việc thường ngày của kế hoạch, chỉ
    thêm/bớt/đổi-thứ-tự/đổi-thuê-ngoài mới đáng cảnh báo."""
    return [
        {"ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc}
        for cd in sorted(cong_doans, key=lambda c: c.thu_tu)
    ]


def thoi_luong_buoc(cd) -> dict:
    """Thời lượng 1 bước, tính TẠI CHỖ (không lưu cột) — nguồn số cho Gantt.

    Tách hai con số vì chúng dùng khác nhau (đúng Dynamics 365 BC, nền của print MIS PrintVis):
    - `chiem_may_phut` = setup + chạy + vệ sinh → ĂN capacity, vẽ thành thanh trên Gantt máy/tổ.
    - `tong_phut` = thêm chờ + di chuyển → chỉ ĐẨY bước sau, không ăn capacity.
    Chờ khô mực 4 tiếng KHÔNG có nghĩa máy in bị chiếm thêm 4 tiếng.

    `chay_phut` người kế hoạch gõ đè thì THẮNG công thức năng suất. `so_nhan_cong` chia thời gian
    CHẠY (5 người dán thì nhanh gấp 5) nhưng KHÔNG chia setup — setup vẫn phải làm một lần.
    """
    setup = _f(cd.setup_phut)
    ve_sinh = _f(cd.ve_sinh_phut)
    cho = _f(cd.cho_phut)
    di_chuyen = _f(cd.di_chuyen_phut)
    if cd.chay_phut is not None:
        chay = _f(cd.chay_phut)
    else:
        ns, vao = _f(cd.nang_suat), _f(cd.so_luong_vao)
        luot = max(int(cd.so_luot_chay or 1), 1)
        nhan_cong = max(int(cd.so_nhan_cong or 1), 1)
        chay = (vao / ns * 60.0 * luot / nhan_cong) if ns > 0 and vao > 0 else 0.0
    chiem_may = setup + chay + ve_sinh
    return {
        "chay_phut": round(chay, 2),
        "chiem_may_phut": round(chiem_may, 2),
        "tong_phut": round(chiem_may + cho + di_chuyen, 2),
    }


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
            ten = row.get("ten") or cd.get("ten") or "Công đoạn"
            nhom = cd.get("nhom")
            routing.append({
                "thu_tu": i,
                "cong_doan_id": cd_id,
                "ten": ten,
                "nhom": nhom,
                "department_id": cd.get("department_id"),
                # Suy loại bước NGAY TỪ ĐÂY để màn "lệnh dự kiến" và màn lệnh đã tạo nói cùng một
                # thứ tiếng — trước đó preview chỉ có cờ thuê-ngoài nên hai màn hiển thị lệch nhau.
                "loai_buoc": _suy_loai_buoc(ten, nhom, bool(row.get("nha_cung_cap"))),
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

    def _default_buoc(self, r: dict, *, comp: dict, so_luong_dat: int, bu_hao: int,
                      nhan_bu_hao: bool, lsx_may_id: int | None) -> dict:
        """Toàn bộ giá trị MẶC ĐỊNH của 1 bước khi bung routing từ bài tính giá.

        "Kế thừa" ở đây = GIÁ TRỊ KHỞI ĐIỂM, không phải read-only: kế hoạch sửa được hết ở drawer.
        Số lấy từ danh mục (`cong_doan.setup_time`/`may_id`/`nang_suat`, `may_thiet_bi.toc_do`/
        `thoi_gian_rua_muc`) chứ không bịa; danh mục thiếu thì để TRỐNG cho người khai, KHÔNG đoán
        bừa — thời lượng hiện "—" là tín hiệu đúng để đi khai danh mục, số 0 giả thì không.
        """
        nhom, ten = r.get("nhom"), r.get("ten")
        low = _norm(ten)
        # `_tinh_dong` đã suy sẵn khi bung routing — dùng lại để preview và lệnh tạo ra KHỚP nhau.
        loai_buoc = r.get("loai_buoc") or _suy_loai_buoc(ten, nhom, bool(r.get("nha_cung_cap")))
        cd_obj = self.db.get(CongDoan, r["cong_doan_id"]) if r.get("cong_doan_id") else None
        may_id = (cd_obj.may_id if cd_obj else None) or (lsx_may_id if nhom == "print" else None)
        may = self.db.get(MayThietBi, may_id) if may_id else None

        to_vao = _f(comp.get("to_dau_vao"))
        to_ra = _f(comp.get("to_sau_in")) or to_vao
        con = max(int(comp.get("con") or 1), 1)

        # --- Đơn vị vào/ra + hệ số (luật dùng chung với `mac_dinh_buoc`) rồi mới ra SỐ ---
        dv_vao, dv_ra, he_so = _don_vi_theo_buoc(ten, nhom, con=con)
        if nhom == "prepress":
            vao = ra = _f(comp.get("so_kem"))
        elif nhom == "print":
            vao, ra = to_vao, to_ra
        elif dv_vao == DV_TO and dv_ra == DV_CAI:      # bước bế: tờ vào → con ra
            vao, ra = to_ra, to_ra * con
        elif dv_vao == DV_CAI:
            # Sau bế thì đếm CON. KHÔNG cộng `bu_hao` vào đây — bù hao là số TỜ ở máy in, cộng vào
            # bước đếm con là lẫn đơn vị (lỗi của lát 1). Hao của bước này nằm ở `hao_hut_pct`.
            vao = ra = float(so_luong_dat)
        else:
            vao = ra = to_ra

        nang_suat, dv_nang_suat = _nang_suat_buoc(may, cd_obj, dv_vao)

        return {
            "loai_buoc": loai_buoc,
            "so_luong_vao": vao,
            "so_luong_ra": ra,
            "don_vi_vao": dv_vao,
            "don_vi_ra": dv_ra,
            "he_so_quy_doi": he_so,
            # Bù hao mà engine tính giá đã cộng là MỘT CỤC (`to_dau_vao` gồm sẵn) → chỉ đặt vào
            # ĐÚNG MỘT bước (bước in đầu tiên), nếu không "tính ngược" sẽ đếm hao hai lần.
            "hao_hut": float(bu_hao) if nhan_bu_hao else 0.0,
            # Hao hụt % ĐỂ TRỐNG cho người kế hoạch gõ tay tại lệnh. KHÔNG kế thừa từ danh mục:
            # module Bù hao đã bao cả hai kiểu hao (mỗi bậc tự chọn `to` | `pct`, `tra_bac` quy %
            # về số tờ), và toàn bộ đã chảy vào `hao_hut` ở trên — lấy thêm % nữa là ĐẾM HAI LẦN.
            # (`cong_doan.spoilage_pct` chỉ còn `routing_engine` của hệ tính giá CŨ dùng, không có
            # ô nhập nên thực tế luôn 0 — neo vào đó chỉ trông có vẻ hợp lý.)
            "hao_hut_pct": 0.0,
            # CẨN THẬN: `comp["so_luot"]` của engine là TỔNG LƯỢT TỜ (`to_dau_vao × số mặt`),
            # KHÔNG phải số lượt chạy. Số lượt chạy = so_luot ÷ số tờ (in trở 2 mặt → 2).
            "so_luot_chay": _so_luot_chay(comp) if nhom == "print" else 1,
            "setup_phut": _f(cd_obj.setup_time) if cd_obj else 0.0,
            "nang_suat": nang_suat,
            "don_vi_nang_suat": dv_nang_suat,
            # Rửa mực chỉ có ở bước IN — bước sau in không rửa mực.
            "ve_sinh_phut": _f(may.thoi_gian_rua_muc) if (may is not None and nhom == "print") else 0.0,
            "may_id": may_id,
        }

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
            da_gan_bu_hao = False
            for r in calc["routing"]:
                # Cục bù hao của engine chỉ gắn vào bước IN ĐẦU TIÊN (xem `_default_buoc`).
                nhan_bu_hao = r.get("nhom") == "print" and not da_gan_bu_hao
                d = self._default_buoc(
                    r, comp=comp, so_luong_dat=so_luong_dat, bu_hao=bu_hao,
                    nhan_bu_hao=nhan_bu_hao, lsx_may_id=lsx.may_id,
                )
                da_gan_bu_hao = da_gan_bu_hao or nhan_bu_hao
                lsx.cong_doans.append(LsxCongDoan(
                    thu_tu=r["thu_tu"],
                    cong_doan_id=r.get("cong_doan_id"),
                    ten=r.get("ten") or "Công đoạn",
                    nhom=r.get("nhom"),
                    department_id=r.get("department_id"),
                    nha_cung_cap=r.get("nha_cung_cap"),
                    **d,
                ))
            lsx.routing_goc_json = _routing_van_tay(lsx.cong_doans)
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
        """Checklist CHẶN — còn mã nào thì không cho đánh dấu "Sẵn sàng lập kế hoạch" (§12)."""
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

        # --- Điều kiện "sẵn sàng xếp lịch" của từng bước (§12) ---
        for cd in lsx.cong_doans:
            # Bước NỘI BỘ phải biết ai/máy nào làm thì Gantt mới có chỗ đặt. Bước `cho` không chiếm
            # tài nguyên nên miễn.
            if cd.loai_buoc in (LB_MAY, LB_TO, LB_KCS, LB_XA_TO) and not (cd.department_id or cd.may_id):
                if "thieu_to_may" not in thieu:
                    thieu.append("thieu_to_may")
            if cd.loai_buoc == LB_THUE_NGOAI:
                if not (cd.nha_cung_cap or "").strip() and "thieu_ncc" not in thieu:
                    thieu.append("thieu_ncc")
                if not (cd.ngay_gui_dk and cd.ngay_nhan_dk) and "thieu_tg_thue_ngoai" not in thieu:
                    thieu.append("thieu_tg_thue_ngoai")
            # Đổi đơn vị mà hệ số vẫn 1 = chưa khai (bế 1 tờ ra 1 con là vô lý) → chặn.
            if cd.don_vi_vao != cd.don_vi_ra and _f(cd.he_so_quy_doi) <= 1 and "thieu_he_so" not in thieu:
                thieu.append("thieu_he_so")
        # tp chỉ dùng để xác nhận nguồn còn sống — lệnh vẫn chạy được khi PTG đã đổi/xoá.
        del tp
        return thieu

    # ================= TÍNH NGƯỢC · LEAD TIME · CẢNH BÁO =================

    def mac_dinh_buoc(self, *, lsx_id: int, cong_doan_id: int) -> dict:
        """Bộ mặc định khi kế hoạch ĐỔI một bước sang công đoạn khác giữa chừng.

        Không có hàm này thì bước đổi xong vẫn đeo nguyên số của công đoạn CŨ (loại bước, tổ, máy,
        đơn vị, năng suất) — thời lượng và đơn vị sai mà chẳng cảnh báo gì.

        KHÔNG trả số lượng vào/ra: chúng thuộc CHUỖI (bước trước giao bao nhiêu thì bước này nhận
        bấy nhiêu), không thuộc công đoạn — người kế hoạch giữ số đang cân, lệch thì đã có cảnh báo
        `dut_chuyen` và nút "Tính ngược từ SL thành phẩm".
        """
        lsx = self.get(lsx_id)
        cd = self.db.get(CongDoan, cong_doan_id)
        if cd is None:
            raise LsxNotFound("Không tìm thấy công đoạn")

        dv_vao, dv_ra, he_so = _don_vi_theo_buoc(cd.ten, cd.nhom, con=int(lsx.so_con or 1))
        # Bước IN chưa gán máy riêng thì dùng máy đã chọn ở phiếu tính giá (như lúc bung lệnh).
        may_id = cd.may_id or (lsx.may_id if cd.nhom == "print" else None)
        may = self.db.get(MayThietBi, may_id) if may_id else None
        nang_suat, dv_nang_suat = _nang_suat_buoc(may, cd, dv_vao)
        return {
            "cong_doan_id": cd.id,
            "ten": cd.ten,
            "nhom": cd.nhom,
            "loai_buoc": _suy_loai_buoc(cd.ten, cd.nhom, False),
            "department_id": cd.department_id,
            "may_id": may_id,
            "don_vi_vao": dv_vao,
            "don_vi_ra": dv_ra,
            "he_so_quy_doi": he_so,
            "setup_phut": _f(cd.setup_time),
            "nang_suat": nang_suat,
            "don_vi_nang_suat": dv_nang_suat,
            # Rửa mực chỉ có ở bước IN — bước sau in không rửa mực.
            "ve_sinh_phut": _f(may.thoi_gian_rua_muc) if (may is not None and cd.nhom == "print") else 0.0,
        }

    def tinh_nguoc_routing(self, lsx: Lsx) -> list[dict]:
        """Chạy NGƯỢC chuỗi công đoạn từ SL thành phẩm → SL vào/ra gợi ý cho từng bước.

        Đúng chiều tư duy xưởng và đúng mô hình BC (`Input = Output × (1 + Scrap%) + FixedScrap`,
        cộng dồn từ bước CUỐI về bước ĐẦU): *cần 20.500 hộp tốt thì phải in bao nhiêu tờ*.

        Hàm THUẦN — chỉ trả số gợi ý, KHÔNG ghi DB. Người kế hoạch xem diff rồi mới bấm áp dụng.
        """
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        if not buoc:
            return []
        out: list[dict] = [{} for _ in buoc]
        # Đích của bước cuối = SL khách đặt (tính theo đơn vị RA của chính bước đó).
        can_ra = float(lsx.so_luong_dat or 0)
        for i in range(len(buoc) - 1, -1, -1):
            cd = buoc[i]
            he_so = _f(cd.he_so_quy_doi) or 1.0
            # Quy đổi về đơn vị VÀO trước, rồi mới bù hao (hao tính trên đầu vào).
            vao_truoc_hao = can_ra / he_so if cd.don_vi_vao != cd.don_vi_ra else can_ra
            vao = vao_truoc_hao * (1 + _f(cd.hao_hut_pct) / 100.0) + _f(cd.hao_hut)
            vao = float(ceil(vao))
            out[i] = {
                "id": cd.id,
                "thu_tu": cd.thu_tu,
                "ten": cd.ten,
                "so_luong_vao": vao,
                "so_luong_ra": float(ceil(can_ra)),
                "don_vi_vao": cd.don_vi_vao,
                "don_vi_ra": cd.don_vi_ra,
            }
            can_ra = vao  # bước trước phải GIAO đủ chừng này
        return out

    def lead_time(self, lsx: Lsx) -> dict:
        """Tổng thời gian dẫn của cả lệnh + ngày dự kiến xong (thô, 8h/ngày, chưa trừ nghỉ lễ)."""
        tong = chiem_may = 0.0
        for cd in lsx.cong_doans:
            t = thoi_luong_buoc(cd)
            tong += t["tong_phut"]
            chiem_may += t["chiem_may_phut"]
        so_ngay = tong / 60.0 / GIO_LAM_MOI_NGAY if tong else 0.0
        han = lsx.han_giao_khach
        con_lai = (han - date.today()).days if han else None
        return {
            "tong_phut": round(tong, 2),
            "chiem_may_phut": round(chiem_may, 2),
            "so_ngay": round(so_ngay, 2),
            "ngay_du_kien_xong": date.today() + timedelta(days=ceil(so_ngay)) if tong else None,
            "ngay_con_lai": con_lai,
        }

    def canh_bao_cua(self, lsx: Lsx) -> list[str]:
        """Rổ cảnh báo MỀM (§14) — chỉ tô màu, KHÔNG chặn lưu và KHÔNG chặn "Sẵn sàng".

        Toàn là phán đoán nghề: máy nêu nghi vấn, người kế hoạch quyết. Ví dụ "đứt chuyền" có thể
        đúng ý (chừa bán thành phẩm cho lệnh khác), nên chặn là sai.
        """
        canh_bao: list[str] = []
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)

        for i, cd in enumerate(buoc):
            vao, ra = _f(cd.so_luong_vao), _f(cd.so_luong_ra)
            if cd.don_vi_vao == cd.don_vi_ra and vao > 0 and ra > vao and "ra_lon_hon_vao" not in canh_bao:
                canh_bao.append("ra_lon_hon_vao")
            if i + 1 < len(buoc):
                sau = buoc[i + 1]
                if (cd.don_vi_ra == sau.don_vi_vao and ra > 0 and _f(sau.so_luong_vao) > ra
                        and "dut_chuyen" not in canh_bao):
                    canh_bao.append("dut_chuyen")

        lt = self.lead_time(lsx)
        if lt["ngay_con_lai"] is not None and lt["so_ngay"] > lt["ngay_con_lai"]:
            canh_bao.append("vuot_han_giao")

        goc = lsx.routing_goc_json
        if goc is not None and goc != _routing_van_tay(lsx.cong_doans):
            canh_bao.append("khac_bai_tinh_gia")

        if self._may_khong_hop_kho(lsx):
            canh_bao.append("may_khong_hop_kho")
        return canh_bao

    def _may_khong_hop_kho(self, lsx: Lsx) -> bool:
        """Khổ tờ in vượt khổ tối đa của máy đã gán (xoay 90° vẫn không lọt)."""
        qc = lsx.quy_cach_json or {}
        dai, rong = _f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong"))
        if dai <= 0 or rong <= 0:
            return False
        may_ids = {cd.may_id for cd in lsx.cong_doans if cd.may_id}
        if lsx.may_id:
            may_ids.add(lsx.may_id)
        for mid in may_ids:
            may = self.db.get(MayThietBi, mid)
            max_d, max_r = _f(may.kho_max_dai) if may else 0, _f(may.kho_max_rong) if may else 0
            if max_d <= 0 or max_r <= 0:
                continue
            lot = (dai <= max_d and rong <= max_r) or (rong <= max_d and dai <= max_r)
            if not lot:
                return True
        return False

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
            "canh_bao": self.canh_bao_cua(lsx),
            "lead_time": self.lead_time(lsx),
            "cong_doans": [self._cong_doan_dict(cd, dept_names, may_names) for cd in lsx.cong_doans],
        }

    def _cong_doan_dict(self, cd, dept_names: dict, may_names: dict) -> dict:
        vao = _f(cd.so_luong_vao)
        t = thoi_luong_buoc(cd)
        return {
            "id": cd.id, "thu_tu": cd.thu_tu, "cong_doan_id": cd.cong_doan_id,
            "ten": cd.ten, "nhom": cd.nhom, "loai_buoc": cd.loai_buoc, "bat_buoc": bool(cd.bat_buoc),
            "department_id": cd.department_id,
            "department_ten": dept_names.get(cd.department_id),
            "may_id": cd.may_id, "may_ten": may_names.get(cd.may_id),
            "may_thay_the_ids": cd.may_thay_the_ids or [],
            "so_luong_vao": vao, "so_luong_ra": _f(cd.so_luong_ra),
            "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
            "he_so_quy_doi": _f(cd.he_so_quy_doi),
            "hao_hut": _f(cd.hao_hut), "hao_hut_pct": _f(cd.hao_hut_pct),
            # % thực tế suy từ số — KHÔNG lưu cột, tránh hai nguồn sự thật với `hao_hut`.
            "ty_le_hao_hut": round(_f(cd.hao_hut) / vao * 100, 2) if vao > 0 else 0.0,
            "so_luot_chay": cd.so_luot_chay, "so_nhan_cong": cd.so_nhan_cong,
            "setup_phut": _f(cd.setup_phut), "nang_suat": cd.nang_suat and _f(cd.nang_suat),
            "don_vi_nang_suat": cd.don_vi_nang_suat,
            "chay_phut": cd.chay_phut if cd.chay_phut is None else _f(cd.chay_phut),
            "ve_sinh_phut": _f(cd.ve_sinh_phut), "cho_phut": _f(cd.cho_phut),
            "di_chuyen_phut": _f(cd.di_chuyen_phut),
            "dieu_kien_json": cd.dieu_kien_json or [],
            "nha_cung_cap": cd.nha_cung_cap, "sl_gui": cd.sl_gui and _f(cd.sl_gui),
            "ngay_gui_dk": cd.ngay_gui_dk, "ngay_nhan_dk": cd.ngay_nhan_dk,
            "van_chuyen_ngay": cd.van_chuyen_ngay and _f(cd.van_chuyen_ngay),
            "gia_cong_ngay": cd.gia_cong_ngay and _f(cd.gia_cong_ngay),
            "hao_hut_cho_phep": cd.hao_hut_cho_phep and _f(cd.hao_hut_cho_phep),
            "don_gia_gia_cong": cd.don_gia_gia_cong and _f(cd.don_gia_gia_cong),
            "yeu_cau_ky_thuat": cd.yeu_cau_ky_thuat,
            "nguoi_giao_nhan_id": cd.nguoi_giao_nhan_id,
            "nguoi_giao_nhan_ten": self._user_name(cd.nguoi_giao_nhan_id),
            "ghi_chu": cd.ghi_chu,
            # CHỈ lấy hai số DẪN XUẤT. KHÔNG spread cả `thoi_luong_buoc` vào đây: nó cũng có key
            # `chay_phut` và sẽ GHI ĐÈ giá trị đã lưu ở trên — client nhận số đã-tính, tưởng là
            # người dùng gõ đè, lưu ngược lại, thế là hợp đồng "để trống = máy tự tính" vỡ vĩnh
            # viễn ngay sau lần lưu đầu (bước chưa khai năng suất bị đóng băng ở 0 phút).
            "chiem_may_phut": t["chiem_may_phut"],
            "tong_phut": t["tong_phut"],
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

    # Cột nhận thẳng từ client, không cần suy diễn gì thêm.
    _ROUTING_FIELD_THUAN = (
        "may_id", "bat_buoc", "he_so_quy_doi", "hao_hut", "hao_hut_pct", "so_luot_chay",
        "so_nhan_cong", "setup_phut", "nang_suat", "don_vi_nang_suat", "chay_phut",
        "ve_sinh_phut", "cho_phut", "di_chuyen_phut", "may_thay_the_ids", "dieu_kien_json",
        "nha_cung_cap", "sl_gui", "ngay_gui_dk", "van_chuyen_ngay", "gia_cong_ngay",
        "ngay_nhan_dk", "hao_hut_cho_phep", "don_gia_gia_cong", "yeu_cau_ky_thuat",
        "nguoi_giao_nhan_id", "ghi_chu",
    )

    def replace_routing(self, *, lsx_id: int, rows_in, actor, ly_do: str | None = None) -> Lsx:
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
            dv_vao = d.get("don_vi_vao") or DV_TO
            row = LsxCongDoan(
                thu_tu=d.get("thu_tu", i),
                cong_doan_id=cd_id,
                ten=ten or "Công đoạn",
                nhom=nhom,
                department_id=dept,
                loai_buoc=d.get("loai_buoc") or _suy_loai_buoc(ten, nhom, False),
                so_luong_vao=d.get("so_luong_vao") or 0,
                so_luong_ra=d.get("so_luong_ra") or 0,
                don_vi_vao=dv_vao,
                # Bỏ trống đơn vị RA = không đổi đơn vị ở bước này (đỡ bắt khai 2 lần cho đa số bước).
                don_vi_ra=d.get("don_vi_ra") or dv_vao,
            )
            for f in self._ROUTING_FIELD_THUAN:
                if d.get(f) is not None:
                    setattr(row, f, d[f])
            rows.append(row)
        self.repo.replace_cong_doans(lsx, rows)
        thieu = self.thieu_cua(lsx)
        if thieu and lsx.trang_thai != TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_CHO_BO_SUNG
        elif not thieu and lsx.trang_thai == TT_CHO_BO_SUNG:
            lsx.trang_thai = TT_NHAP
        # §10: routing lệch bài tính giá thì phải lưu NGƯỜI xác nhận (audit đã có) + LÝ DO.
        detail = f"Sửa routing lệnh {lsx.ma}: {truoc} → {len(rows)} công đoạn"
        if (ly_do or "").strip():
            detail += f" — lý do: {ly_do.strip()}"
        self.audit.create(
            actor_user_id=actor.id, action="update_lsx_routing", target=f"lsx:{lsx.id}",
            detail=detail,
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
