"""Idempotent startup seed: RBAC catalog + the initial admin user.

Safe to call on every startup — every step creates rows only if absent, so re-runs
do not duplicate. Seeds only the Kinh doanh + Hành chính nhân sự scope for now; the
module catalog is data and grows as other departments come online (spec-02-rbac.md).
Credentials come from config/env (SEED_ADMIN_*).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .config import settings
from .models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from .models.work_calendar import KIND_OFF, SpecialDay
from .repositories.calendar_repo import CalendarRepository
from .repositories.customer_repo import CustomerRepository
from .repositories.rbac_repo import (
    DepartmentRepository,
    ModuleRepository,
    RoleRepository,
    UnitLevelRepository,
)
from .repositories.user_repo import UserRepository
from .security import hash_password

# --- Catalog (seed data; expandable) ---------------------------------------

# Module catalog: (key, label). Kinh doanh + Hành chính nhân sự / quản trị only.
MODULES: list[tuple[str, str]] = [
    ("dashboard", "Dashboard"),
    ("khach_hang", "Khách hàng"),
    ("bao_gia", "Báo giá in ấn"),
    ("don_hang_ban", "Đơn hàng bán"),
    ("tinh_gia_thanh", "Tính giá thành"),
    ("thu_mua", "Thu mua"),
    ("ke_toan", "Kế toán"),
    ("san_xuat", "Sản xuất"),
    ("kho", "Kho hàng"),
    ("khuon_be", "Khuôn bế"),
    ("phong_ban", "Phòng ban"),
    ("vai_tro", "Vai trò"),
    ("nguoi_dung", "Người dùng"),
    ("activity_log", "Nhật ký hoạt động"),
    # Cấu hình danh mục (spec-06): mỗi trang là một module quyền riêng để tích quyền độc lập.
    # Chỉ liệt kê module CÓ MÀN dùng tới — module không màn = dòng ma trong ma trận, tick vào
    # không đổi gì. Đã gỡ (migration 0069): san_pham · dm_gia_click · dm_gia_khuon_ban ·
    # dm_dinh_muc · dm_binh_bai. Dữ liệu norms/plate_die_rates/products GIỮ NGUYÊN — engine
    # tính giá đọc thẳng repo, không qua ma trận quyền.
    ("dm_loai_san_pham", "Loại sản phẩm"),
    ("dm_giay_vat_tu", "Vật liệu & Giá"),
    ("dm_thiet_bi", "Thiết bị & Máy in"),
    ("dm_cong_doan", "Công đoạn gia công"),
    ("nhan_su", "Nhân sự"),
    ("nghi_phep", "Nghỉ phép"),
    ("tang_ca", "Tăng ca"),
    ("di_muon", "Đi muộn / về sớm"),
    ("luong", "Lương"),
    # Nội quy công ty (chủ 30/07/2026): CHỈ Giám đốc soạn/ban hành — vai GĐ nhận toàn quyền
    # qua `ALL_MODULE_KEYS` ở dưới, các vai khác khai module tường minh nên không dính.
    # Việc ĐỌC nội quy KHÔNG gác bằng module này: `GET /api/noi-quy/current` chỉ đòi đăng
    # nhập, để không vai nào bị bỏ sót mà mất quyền đọc nội quy.
    ("noi_quy", "Nội quy công ty"),
]

ALL_MODULE_KEYS = [k for k, _ in MODULES]
KD_MODULE_KEYS = [
    "dashboard",
    "khach_hang",
    "bao_gia",
    "don_hang_ban",
    "tinh_gia_thanh",
]

DEPARTMENTS = [
    "Ban giám đốc", "Hành chính nhân sự", "Kinh doanh",
    # Phòng ban vận hành Kho (BRD Module Kho §1.4) — để gắn vai trò tiếp cận kho.
    "Kho", "Kế toán", "Sản xuất", "Mua hàng",
]

# Default org tiers (spec-06 / PBI-4009): (name, rank cao→thấp, head_title). Data, not schema —
# admins add/edit more via the catalog screen.
UNIT_LEVELS: list[tuple[str, int, str]] = [
    ("Khối", 1, "Trưởng khối"),
    ("Phòng", 2, "Trưởng phòng"),
    ("Tổ", 3, "Tổ trưởng"),
]

ADMIN_DEPARTMENT = "Ban giám đốc"
ADMIN_ROLE = "Giám đốc"


def _full(scope: str, *, can_approve_exception: bool = False) -> dict:
    # `can_approve_exception` (A2: GĐ duyệt "đơn đặc thù" trên don_hang_ban) MẶC ĐỊNH TẮT — vì
    # _full dùng CHUNG cho cả GĐ lẫn Trưởng phòng KD; chỉ GĐ được bật (override riêng ở ROLES),
    # nếu bật thẳng trong _full thì TP KD cũng nhận → tự miễn cho đơn của mình (phản biện #1).
    return dict(
        can_read=True,
        can_create=True,
        can_update=True,
        can_delete=True,
        scope=scope,
        can_reassign=True,
        can_export=True,
        can_view_debt=True,
        can_view_discount=True,
        can_approve=True,
        can_manage_status=True,
        can_reset_password=True,
        can_lock=True,
        can_revoke_sessions=True,
        can_assign_role=True,
        can_transfer=True,
        can_set_head=True,
        can_requote=True,
        can_manage_price=True,
        can_cancel=True,
        can_manage_permissions=True,
        can_clone=True,
        can_toggle_active=True,
        can_reparent=True,
        can_view_salary=True,
        can_edit_salary=True,
        can_adjust=True,
        can_approve_exception=can_approve_exception,
        # khach_hang: thiết lập điều khoản tín dụng khách — bật cho vai quản lý (_full dùng chung
        # cho Giám đốc + GĐ KD + Trưởng phòng KD). NV Sales dùng _rcu → KHÔNG có (chỉ xem read-only).
        can_set_credit_terms=True,
        # kho (spec-kho-de-nghi §9.2): 4 ô quyền chi tiết. Chỉ CÓ NGHĨA trên module `kho`, mà
        # `_full` chỉ chạm module đó ở vai Giám đốc → thực chất đây là "GĐ toàn quyền kho".
        # Quản lý kho KHÔNG dùng `_full` (khai riêng bên dưới) vì không được sửa giá vốn.
        can_request=True,
        can_view_stock=True,
        can_view_cost=True,
        can_set_threshold=True,
        can_post=True,  # GĐ toàn quyền kho → được GHI SỔ (chốt tồn)
    )


def _rcu(scope: str) -> dict:
    return dict(can_read=True, can_create=True, can_update=True, can_delete=False, scope=scope)


def _read(scope: str) -> dict:
    return dict(
        can_read=True, can_create=False, can_update=False, can_delete=False, scope=scope
    )


# Cụm quyền KHO — TÁCH "Ghi sổ" (can_post) khỏi "Xem kho" để giữ SoD (BRD §3.19, khớp model
# RolePermission.can_post): Thủ kho LẬP phiếu + xem kho NHƯNG KHÔNG ghi sổ; QL kho / Kế toán kho
# mới ghi sổ (chốt tồn). Trên ma trận là 2 công tắc riêng.
#   _KHO_VIEW = xem tồn + xem giá vốn/giá trị tồn + khai ngưỡng tồn.
#   _KHO_QL   = _KHO_VIEW + ghi sổ phiếu (can_post).
# KHÔNG kèm `can_approve` — DUYỆT đề nghị là việc của quản lý bộ phận đề nghị, kho KHÔNG tự duyệt.
_KHO_VIEW = {
    "can_view_stock": True, "can_view_cost": True, "can_set_threshold": True,
}
_KHO_QL = {**_KHO_VIEW, "can_post": True}


def _leave_self(scope: str = SCOPE_OWN) -> dict:
    """Quyền self-service Nghỉ phép cho MỌI nhân viên: xem đơn của mình (scope own),
    tự tạo + tự hủy đơn. KHÔNG duyệt, KHÔNG quản loại nghỉ (những cái đó gate `approve`)."""
    return dict(
        can_read=True, can_create=True, can_update=False, can_delete=False,
        scope=scope, can_cancel=True,
    )


def _leave_admin(scope: str = SCOPE_ALL) -> dict:
    """Quyền quản trị Nghỉ phép (HCNS): xem mọi đơn theo scope + duyệt/từ chối +
    quản loại nghỉ (`can_approve` = cờ 'leave admin' gate cả duyệt lẫn CRUD loại nghỉ)."""
    return dict(
        can_read=True, can_create=True, can_update=True, can_delete=True,
        scope=scope, can_approve=True, can_cancel=True,
    )


def _leave_lead(scope: str = SCOPE_DEPARTMENT) -> dict:
    """Quyền DUYỆT đơn nghỉ phép cho TỔ TRƯỞNG (chủ 29/07/2026: "nghỉ phép thì để cho tổ trưởng
    duyệt mà phạm vi trong tổ nó thôi").

    Khác `_leave_admin` ở đúng một chỗ và đó là chỗ quan trọng: `can_update=False`. Ba endpoint
    THÊM/SỬA/XOÁ danh mục LOẠI NGHỈ gác bằng ô `update` (xem `routers/leaves.py`), nên tổ trưởng
    duyệt được đơn của tổ mình mà KHÔNG đụng được danh mục loại nghỉ của cả công ty — cái đó là
    chính sách toàn công ty, giữ ở HCNS.

    Scope `department` = tổ mình + cây con; service `_guard_scope` là thứ thi hành thật."""
    return dict(
        can_read=True, can_create=True, can_update=False, can_delete=False,
        scope=scope, can_approve=True, can_cancel=True,
    )


def _ot_self(scope: str = SCOPE_OWN) -> dict:
    """Tự phục vụ Phiếu tăng ca cho MỌI nhân viên: xem phiếu của mình + tự gửi + tự hủy.
    KHÔNG duyệt (duyệt gate bằng `can_approve`)."""
    return dict(
        can_read=True, can_create=True, can_update=False, can_delete=False,
        scope=scope, can_cancel=True,
    )


def _ot_lead(scope: str = SCOPE_DEPARTMENT) -> dict:
    """Quyền DUYỆT phiếu tăng ca (+ tạo hộ cho thợ, tạo hộ là duyệt luôn). Scope `department`
    = tổ mình + cây con ⇒ tổ trưởng CHỈ duyệt được người trong tổ; HCNS/Admin dùng scope `all`."""
    return dict(
        can_read=True, can_create=True, can_update=True, can_delete=False,
        scope=scope, can_approve=True, can_cancel=True,
    )


# Phiếu ĐI MUỘN / VỀ SỚM / NGHỈ NỬA BUỔI — cùng luồng duyệt với tăng ca (tổ trưởng duyệt tổ mình).
def _el_self(scope: str = SCOPE_OWN) -> dict:
    """Tự phục vụ cho MỌI nhân viên: xem phiếu của mình + tự gửi + tự hủy. KHÔNG duyệt."""
    return dict(
        can_read=True, can_create=True, can_update=False, can_delete=False,
        scope=scope, can_cancel=True,
    )


def _el_lead(scope: str = SCOPE_DEPARTMENT) -> dict:
    """Quyền DUYỆT phiếu đi muộn/về sớm (+ khai hộ cho thợ, khai hộ là duyệt luôn)."""
    return dict(
        can_read=True, can_create=True, can_update=True, can_delete=False,
        scope=scope, can_approve=True, can_cancel=True,
    )


# Roles: (department_name, role_name, {module_key: permission}). The minimal default
# role ("Nhân viên") is Read-only on Dashboard, scope own.
ROLES: list[tuple[str, str, dict[str, dict]]] = [
    (
        ADMIN_DEPARTMENT,
        ADMIN_ROLE,
        {
            **{k: _full(SCOPE_ALL) for k in ALL_MODULE_KEYS},
            # Chỉ GĐ được DUYỆT "báo giá đặc thù" (BG-2) — TP KD giữ _full nhưng KHÔNG có quyền này.
            "bao_gia": _full(SCOPE_ALL, can_approve_exception=True),
            # Đơn hàng bán: GĐ duyệt "đơn đặc thù" + hủy đơn đã chốt + ghi cọc (GĐ toàn quyền).
            # SoD: `can_record_deposit` KHÔNG ở `_full` (TP KD/GĐ KD không tự ghi cọc) — chỉ GĐ + vai Kế toán.
            "don_hang_ban": {**_full(SCOPE_ALL, can_approve_exception=True), "can_record_deposit": True},
        },
    ),
    (
        "Hành chính nhân sự",
        "Trưởng phòng HCNS",
        {
            "dashboard": _read(SCOPE_ALL),
            # HCNS quản trị nhân sự trọn: CRU + quyền chi tiết (xem lương/BHXH, vòng đời,
            # điều chuyển, duyệt yêu cầu cập nhật, xuất Excel).
            "nhan_su": {
                **_rcu(SCOPE_ALL),
                "can_view_salary": True,
                "can_edit_salary": True,
                "can_manage_status": True,
                "can_transfer": True,
                "can_approve": True,
                "can_export": True,
                "can_adjust": True,   # Chấm công: chấm bù / sửa công qua punch nguồn
            },
            # Nghỉ phép: HCNS là nơi DUYỆT tập trung (mọi đơn toàn công ty) + quản loại nghỉ.
            "nghi_phep": _leave_admin(SCOPE_ALL),
            "tang_ca": _ot_lead(SCOPE_ALL),
            "di_muon": _el_lead(SCOPE_ALL),
            # Lương: HCNS/kế toán chạy trọn (tạo kỳ, duyệt tạm ứng, chốt, xuất).
            "luong": _full(SCOPE_ALL),
            # HCNS quản trị người dùng → giữ trọn các thao tác quản trị (tách khỏi "sửa"):
            # đặt lại MK, khóa/mở, thu hồi phiên, gán vai trò, chuyển phòng ban.
            "nguoi_dung": {
                **_rcu(SCOPE_ALL),
                "can_reset_password": True,
                "can_lock": True,
                "can_revoke_sessions": True,
                "can_assign_role": True,
                "can_transfer": True,
            },
            "phong_ban": _read(SCOPE_ALL),
            "vai_tro": _read(SCOPE_ALL),
            "activity_log": _read(SCOPE_ALL),
        },
    ),
    # Vai "Nhân viên" tối thiểu: Dashboard + tự phục vụ Nghỉ phép (cửa vào self-service).
    ("Hành chính nhân sự", "Nhân viên",
     {"dashboard": _read(SCOPE_OWN), "nghi_phep": _leave_self(), "tang_ca": _ot_self(), "di_muon": _el_self()}),
    # --- Khối SẢN XUẤT (Lát 1 — hộp việc 2 tầng, gate theo Ô QUYỀN, không theo chức danh) ---
    # Kế hoạch SX: cấu hình lệnh + PHÁT (can_approve), thấy mọi tổ (scope all). KHÔNG gán thợ.
    (
        "Sản xuất",
        "Kế hoạch SX",
        {
            "dashboard": _read(SCOPE_OWN),
            # can_approve = phát hành kế hoạch; can_approve_exception = duyệt ngoại lệ (bỏ qua cảnh
            # báo khi phát hành) — Kế hoạch SX (trưởng điều độ) cầm cả hai.
            "san_xuat": {**_rcu(SCOPE_ALL), "can_approve": True, "can_approve_exception": True},
            "khuon_be": _read(SCOPE_ALL),  # ③ điều độ đọc danh mục khuôn để gán vào lệnh có bế
            # Sửa routing của lệnh cần ĐỌC danh mục: công đoạn (thêm bước), máy (gán máy), tổ
            # (đổi tổ phụ trách). Chỉ READ — cấu hình danh mục vẫn là việc của phòng khác.
            "dm_cong_doan": _read(SCOPE_ALL),
            "dm_thiet_bi": _read(SCOPE_ALL),
            "phong_ban": _read(SCOPE_ALL),
            "nghi_phep": _leave_self(),
            "tang_ca": _ot_self(),
            "di_muon": _el_self(),
        },
    ),
    # Tổ trưởng SX: xem tổ mình (scope own) + GÁN thợ (can_assign_work) → hộp việc FULL + nút gán.
    (
        "Sản xuất",
        "Tổ trưởng SX",
        {
            "dashboard": _read(SCOPE_OWN),
            "san_xuat": {**_read(SCOPE_OWN), "can_assign_work": True, "can_record_output": True, "can_handover": True},
            # Kho: đề nghị lĩnh vật tư cho tổ + DUYỆT cấp 1 đề nghị của tổ mình (BRD §2.8 b5 —
            # "Tổ trưởng/Quản lý duyệt đề xuất cấp phát"). Scope DEPARTMENT: phải thấy đề nghị của
            # NV trong phòng mới duyệt được (own chỉ thấy của mình → không có gì để duyệt).
            "kho": {**_read(SCOPE_DEPARTMENT), "can_request": True, "can_approve": True},
            # "nghi_phep": _leave_self(),
            # Tổ trưởng DUYỆT phiếu tăng ca của tổ mình (scope department = tổ + cây con).
            # Tổ trưởng DUYỆT đơn nghỉ phép + phiếu tăng ca + đi muộn CỦA TỔ MÌNH
            # (scope department = tổ + cây con). Tạm ứng và YC cập nhật hồ sơ KHÔNG cấp —
            # chủ chốt hai thứ đó để bên nhân sự duyệt.
            "nghi_phep": _leave_lead(SCOPE_DEPARTMENT),
            "tang_ca": _ot_lead(SCOPE_DEPARTMENT),
            "di_muon": _el_lead(SCOPE_DEPARTMENT),
        },
    ),
    # Thợ SX: CHỈ xem việc được gán (read scope own, không gán) → hộp việc lọc theo bước được gán.
    (
        "Sản xuất",
        "Thợ SX",
        {"dashboard": _read(SCOPE_OWN), "san_xuat": _read(SCOPE_OWN),
         "nghi_phep": _leave_self(), "tang_ca": _ot_self(), "di_muon": _el_self()},
    ),
    # QC: xem mọi tổ (scope all) để soi công đoạn bất kỳ (ghi lỗi = Lát 3, thêm can_report_defect sau).
    (
        "Sản xuất",
        "QC",
        {"dashboard": _read(SCOPE_OWN), "san_xuat": _read(SCOPE_ALL),
         "nghi_phep": _leave_self(), "tang_ca": _ot_self(), "di_muon": _el_self()},
    ),
    (
        "Kinh doanh",
        "Trưởng phòng KD",
        {
            **{k: _full(SCOPE_DEPARTMENT) for k in KD_MODULE_KEYS},
            # TP KD DUYỆT được "báo giá đặc thù" (cùng Giám đốc Kinh doanh) — chủ đầu tư chốt sau P7.
            "bao_gia": _full(SCOPE_DEPARTMENT, can_approve_exception=True),
            # Đơn hàng bán: TP KD duyệt đơn đặc thù + hủy đơn đã chốt (cùng GĐ KD).
            "don_hang_ban": _full(SCOPE_DEPARTMENT, can_approve_exception=True),
            "nghi_phep": _leave_self(),
        },
    ),
    # Giám đốc Kinh doanh: toàn quyền KD scope Tất cả + DUYỆT "báo giá / đơn ĐẶC THÙ" (BG-2 + A2)
    # — CHỈ vai này (không phải TP KD) được `can_approve_exception`, kèm quyền xem số biên/giá vốn
    # (gắn với approve_exception ở router). redesign-bao-gia §10 / redesign-luong-kinh-doanh §11.
    (
        "Kinh doanh",
        "Giám đốc Kinh doanh",
        {
            **{k: _full(SCOPE_ALL) for k in KD_MODULE_KEYS},
            "bao_gia": _full(SCOPE_ALL, can_approve_exception=True),
            "don_hang_ban": _full(SCOPE_ALL, can_approve_exception=True),
            "nghi_phep": _leave_self(),
        },
    ),
    (
        "Kinh doanh",
        "NV Sales",
        {
            "dashboard": _read(SCOPE_OWN),
            "khach_hang": _rcu(SCOPE_OWN),
            # Báo giá: NV Sales có ĐỦ thao tác thường trên phiếu CỦA MÌNH (gửi khách, ghi nhận khách
            # đồng ý/từ chối, hủy, xuất PDF, tạo bản mới) — các quyền này KHÔNG tách vụn, ai làm KD cũng có.
            # Riêng báo giá ĐẶC THÙ (biên thấp / giá trị cao) phải TRÌNH DUYỆT: chỉ TP KD / GĐ KD cầm
            # `can_approve_exception` mới duyệt được (redesign-bao-gia §10). NV Sales KHÔNG có cờ đó.
            "bao_gia": _full(SCOPE_OWN),
            # Đơn hàng bán: NV KD lập/sửa/chốt đơn CỦA MÌNH (_rcu own + quản trạng thái). Đơn đặc thù
            # (nhập tay/bổ sung) phải TRÌNH lên TP/GĐ (can_approve_exception). Ghi cọc = Kế toán (P2).
            "don_hang_ban": {**_rcu(SCOPE_OWN), "can_manage_status": True},
            # Tính giá: NV Sales tự lập phiếu tính giá của mình; phạm vi "Của tôi" (chỉ thấy phiếu mình lập),
            # TP KD/GĐ scope phòng/tất cả thấy hết (lọc theo `created_by`).
            "tinh_gia_thanh": _rcu(SCOPE_OWN),
            "nghi_phep": _leave_self(),
        },
    ),
    # === Vai trò tiếp cận Kho (BRD Module Kho §1.4/§1.5 · spec-kho-de-nghi §9.2) ==========
    # GỘP QUYỀN (2026-07-29, mentor): 5 cột kho (duyệt · ghi sổ · xem tồn · xem giá vốn · khai
    # ngưỡng) = 1 công tắc "Quản lý kho" trên ma trận → vai làm việc với kho bật cả cụm. `_KHO_QL`
    # = cụm đó. Người đề nghị scope `own` (chỉ đèn tín hiệu, không thấy tồn/giá).
    # Thủ kho: LẬP PHIẾU + XEM KHO (tồn/giá vốn/ngưỡng) — KHÔNG ghi sổ (SoD: QL kho / Kế toán kho
    # chốt tồn). Khai rõ create/update/delete để công tắc "Lập phiếu" trên ma trận hiện ĐÚNG là bật.
    (
        "Kho",
        "Thủ kho",
        {
            "dashboard": _read(SCOPE_OWN),
            "kho": {
                "can_read": True, "can_create": True, "can_update": True, "can_delete": True,
                "scope": SCOPE_ALL, **_KHO_VIEW,
            },
            "san_xuat": _read(SCOPE_ALL),    # xem kế hoạch SX để tham chiếu khi lập phiếu
        },
    ),
    # Quản lý kho: LẬP PHIẾU + Quản lý kho (ghi sổ + xem tồn/giá vốn + ngưỡng). KHÔNG duyệt đề nghị
    # (việc của quản lý bộ phận đề nghị) và KHÔNG tự tạo đề nghị (kho cấp phát, không xin).
    (
        "Kho",
        "Quản lý kho",
        {
            "dashboard": _read(SCOPE_ALL),
            "kho": {
                "can_read": True, "can_create": True, "can_update": True, "can_delete": True,
                "scope": SCOPE_ALL, **_KHO_QL,
            },
            "san_xuat": _read(SCOPE_ALL),
        },
    ),
    # Kế toán bán hàng: xem mọi đơn + GHI PHIẾU THU CỌC (can_record_deposit). Không đụng thương mại.
    (
        "Kế toán",
        "Kế toán bán hàng",
        {
            "dashboard": _read(SCOPE_ALL),
            "don_hang_ban": {**_read(SCOPE_ALL), "can_record_deposit": True},
        },
    ),
    # Kế toán kho: Quản lý kho (đủ cụm: duyệt + ghi sổ + xem tồn/giá vốn + ngưỡng) để đối chiếu,
    # KHÔNG lập phiếu (không create — thủ kho cầm hàng, kế toán chốt sổ).
    (
        "Kế toán",
        "Kế toán kho",
        {
            "dashboard": _read(SCOPE_ALL),
            "kho": {**_read(SCOPE_ALL), **_KHO_QL},
        },
    ),
    # --- Phía ĐỀ NGHỊ: scope `own` (chỉ thấy đề nghị CỦA MÌNH), KHÔNG `can_view_stock`,
    # KHÔNG `can_view_cost`, KHÔNG `can_create` (không lập phiếu). Họ biết khi nào cần đề
    # nghị nhờ hệ thống ĐẨY cảnh báo ngưỡng tồn xuống, không phải tự đi soi kho (spec §8).
    # Nhân viên sản xuất: đề nghị lĩnh NVL cho tổ.
    (
        "Sản xuất",
        "Nhân viên sản xuất",
        {
            "dashboard": _read(SCOPE_OWN),
            "kho": {**_read(SCOPE_OWN), "can_request": True},
            "san_xuat": _rcu(SCOPE_ALL),
        },
    ),
    # Quản lý sản xuất: như NV sản xuất + duyệt (cấp leo thang khi vượt ngưỡng/gấp).
    # Scope kho = DEPARTMENT: PHẢI thấy đề nghị của cả phòng SX (do NV tạo) mới duyệt được —
    # scope `own` chỉ thấy đề nghị của chính mình nên không có gì để duyệt.
    (
        "Sản xuất",
        "Quản lý sản xuất",
        {
            "dashboard": _read(SCOPE_ALL),
            "kho": {**_read(SCOPE_DEPARTMENT), "can_request": True, "can_approve": True},
            "san_xuat": _full(SCOPE_ALL),
        },
    ),
    # Nhân viên mua hàng: đề nghị NHẬP khi tồn chạm ngưỡng (nguồn của phiếu nhập mua NCC).
    (
        "Mua hàng",
        "Nhân viên mua hàng",
        {
            "dashboard": _read(SCOPE_OWN),
            "kho": {**_read(SCOPE_OWN), "can_request": True},
        },
    ),
]


# --- Seed steps (each idempotent) ------------------------------------------


def seed_modules(db: Session) -> None:
    modules = ModuleRepository(db)
    for key, label in MODULES:
        existing = modules.get_by_key(key)
        if existing is None:
            modules.create(key=key, label=label)
        elif existing.label != label:
            # Keep labels in sync when a module is renamed (data, not schema).
            existing.label = label
            db.commit()


def seed_departments(db: Session) -> None:
    depts = DepartmentRepository(db)
    for name in DEPARTMENTS:
        if depts.get_by_name(name) is None:
            depts.create(name=name)


def seed_unit_levels(db: Session) -> None:
    """Seed the default org tiers (Khối/Phòng/Tổ) if absent (spec-06 / PBI-4009)."""
    levels = UnitLevelRepository(db)
    for name, rank, head_title in UNIT_LEVELS:
        if levels.get_by_name(name) is None and levels.get_by_rank(rank) is None:
            levels.create(name=name, rank=rank, head_title=head_title)


def seed_roles(db: Session) -> None:
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)
    for dept_name, role_name, perms in ROLES:
        dept = depts.get_by_name(dept_name)
        if dept is None:
            continue
        role = roles.get_by_name_and_department(role_name, dept.id)
        if role is None:
            role = roles.create(name=role_name, department_id=dept.id)
        # Upsert permissions (no-op row-count on re-run; keeps the matrix in sync).
        for module_key, perm in perms.items():
            roles.set_permission(role_id=role.id, module_key=module_key, **perm)


def seed_admin(db: Session) -> None:
    """Create the initial admin user if absent (no self-registration this spec).
    Identity is the username (spec-0001)."""
    users = UserRepository(db)
    if users.get_by_username(settings.seed_admin_username) is not None:
        return
    users.create(
        username=settings.seed_admin_username,
        name=settings.seed_admin_name,
        password_hash=hash_password(settings.seed_admin_password),
    )


def link_admin(db: Session) -> None:
    """Attach the admin user to the Ban giám đốc department + Giám đốc role, and make
    them that department's head. Idempotent."""
    users = UserRepository(db)
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)

    admin = users.get_by_username(settings.seed_admin_username)
    dept = depts.get_by_name(ADMIN_DEPARTMENT)
    if admin is None or dept is None:
        return
    role = roles.get_by_name_and_department(ADMIN_ROLE, dept.id)
    if role is None:
        return
    if admin.department_id != dept.id or admin.role_id != role.id or not admin.is_active:
        users.set_assignment(admin, department_id=dept.id, role_id=role.id, is_active=True)
    if dept.head_user_id != admin.id:
        depts.set_head(dept, admin.id)


# --- Sample Kinh doanh staff + customers (spec-06 demo data) ---------------

# (username, display name, role_name in Kinh doanh) — password = default_user_password.
KD_STAFF: list[tuple[str, str, str]] = [
    ("tpkd", "Trần Phòng KD", "Trưởng phòng KD"),
    ("sale1", "Lê Sale Một", "NV Sales"),
    ("sale2", "Phạm Sale Hai", "NV Sales"),
]

# Sample customers keyed by owning Sale username:
# (name, tax_code, phone, credit_limit). One pair shares an MST to demo the soft
# duplicate warning without blocking.
KD_CUSTOMERS: dict[str, list[tuple[str, str | None, str | None, int]]] = {
    "sale1": [
        ("Công ty TNHH An Phát", "0101234567", "0901000001", 50_000_000),
        ("Nhà in Minh Khai", "0102345678", "0901000002", 20_000_000),
        ("Khách lẻ Nguyễn Văn A", None, "0901000003", 0),
    ],
    "sale2": [
        ("Công ty CP Bao Bì Việt", "0103456789", "0902000001", 80_000_000),
        ("Cửa hàng Hồng Phúc", "0101234567", "0902000002", 10_000_000),
    ],
}


def seed_kd_staff(db: Session) -> None:
    """Create sample Kinh doanh staff (TP KD + 2 NV Sales) if absent, so the CRM screen
    has scoped owners to demonstrate own/department/all. Idempotent."""
    users = UserRepository(db)
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)
    kd = depts.get_by_name("Kinh doanh")
    if kd is None:
        return
    for username, name, role_name in KD_STAFF:
        u = users.get_by_username(username)
        if u is None:
            u = users.create(
                username=username,
                name=name,
                password_hash=hash_password(settings.default_user_password),
            )
        role = roles.get_by_name_and_department(role_name, kd.id)
        role_id = role.id if role is not None else None
        if u.department_id != kd.id or u.role_id != role_id or not u.is_active:
            users.set_assignment(u, department_id=kd.id, role_id=role_id, is_active=True)


# Tài khoản demo cho các vai trò tiếp cận kho: (username, tên, phòng ban, vai trò).
# Mật khẩu = default_user_password. Chỉ seed khi SEED_DEMO=true.
KHO_STAFF: list[tuple[str, str, str, str]] = [
    ("thukho", "Trần Thủ Kho", "Kho", "Thủ kho"),
    ("qlkho", "Lê Quản Lý Kho", "Kho", "Quản lý kho"),
    ("ketoankho", "Phạm Kế Toán", "Kế toán", "Kế toán kho"),
    ("nvsx", "Ngô Sản Xuất", "Sản xuất", "Nhân viên sản xuất"),
    ("totruongsx", "Bùi Tổ Trưởng", "Sản xuất", "Tổ trưởng SX"),
    ("qlsx", "Vũ Quản Lý SX", "Sản xuất", "Quản lý sản xuất"),
    ("muahang", "Đỗ Mua Hàng", "Mua hàng", "Nhân viên mua hàng"),
]


def seed_kho_staff(db: Session) -> None:
    """Tài khoản demo cho từng vai trò tiếp cận kho (BRD §1.4) để test phân quyền. Idempotent."""
    users = UserRepository(db)
    depts = DepartmentRepository(db)
    roles = RoleRepository(db)
    for username, name, dept_name, role_name in KHO_STAFF:
        dept = depts.get_by_name(dept_name)
        if dept is None:
            continue
        u = users.get_by_username(username)
        if u is None:
            u = users.create(
                username=username, name=name,
                password_hash=hash_password(settings.default_user_password),
            )
        role = roles.get_by_name_and_department(role_name, dept.id)
        role_id = role.id if role is not None else None
        if u.department_id != dept.id or u.role_id != role_id or not u.is_active:
            users.set_assignment(u, department_id=dept.id, role_id=role_id, is_active=True)


def seed_customers(db: Session) -> None:
    """Seed a handful of customers owned by the sample Sales (spec-06). Idempotent:
    skips creation once any customer exists so re-runs never duplicate."""
    customers = CustomerRepository(db)
    users = UserRepository(db)
    # Cheap idempotency guard: if the table already has rows, assume seeded.
    if customers.list(scope="all", actor=_SeedActor(), size=1)[1] > 0:
        return
    for owner_username, rows in KD_CUSTOMERS.items():
        owner = users.get_by_username(owner_username)
        if owner is None:
            continue
        for name, tax_code, phone, credit_limit in rows:
            customers.create(
                name=name,
                tax_code=tax_code,
                phone=phone,
                email=None,
                address=None,
                contact_name=None,
                credit_limit=credit_limit,
                sale_user_id=owner.id,
                status="active",
            )


class _SeedActor:
    """Minimal stand-in for a user when seeding needs an `all`-scope list count."""

    id = 0
    department_id = None


# --- Sample products (spec-07 demo data) -----------------------------------

# (name, product_type, binding_type|None, [components]) where each component is
# (component_type, colors_front, colors_back, page_count, finished_w, finished_h,
#  bleed, grain_direction). paper_master_id stays None (SEAM-03 — Danh mục Giấy chưa build).
KD_PRODUCTS: list[tuple[str, str, str | None, list[tuple]]] = [
    ("Name card công ty", "name_card", None, []),
    ("Tờ rơi khuyến mãi A5", "to_roi", None, []),
    (
        "Sách giới thiệu 32 trang",
        "sach",
        "saddle",
        [
            ("cover", 4, 4, 4, 20.5, 29.0, 3.0, "short"),
            ("body", 4, 4, 32, 20.0, 28.5, 3.0, "long"),
        ],
    ),
]


def seed_products(db: Session) -> None:
    """Seed a few sample products (spec-07). Idempotent: skips once any product exists."""
    from .repositories.product_repo import ComponentInput, ProductRepository

    products = ProductRepository(db)
    if products.list(size=1)[1] > 0:
        return
    for name, product_type, binding_type, comps in KD_PRODUCTS:
        components = [
            ComponentInput(
                component_type=ctype,
                paper_master_id=None,
                colors_front=cf,
                colors_back=cb,
                page_count=pc,
                finished_w=fw,
                finished_h=fh,
                bleed=bl,
                grain_direction=gd,
                sequence=i,
            )
            for i, (ctype, cf, cb, pc, fw, fh, bl, gd) in enumerate(comps)
        ]
        products.create(
            name=name,
            product_type=product_type,
            binding_type=binding_type,
            note=None,
            components=components,
        )


# --- Sample sales history (spec-06 CRM-360 demo data) ----------------------
# Real orders + quotations tied to seeded customers so the Object-page Dashboard
# has genuine 12-month revenue / product-mix / frequency to render (never faked).


def seed_sales_history(db: Session) -> None:
    """Seed a rich spread of orders (with priced lines) + quotations for a few seeded
    customers, dated across the full trailing 12 calendar months, so the CRM-360 Object-page
    Dashboard renders EVERY chart with real numbers (12-month revenue bar, product-mix donut,
    frequency heatmap, mua-hàng + báo-giá history) instead of an empty state.

    Dates are anchored to the MIDDLE of each target calendar month (never a naive N*30 offset)
    so every one of the 12 month buckets in :class:`CustomerAnalyticsService` lands where
    intended and the bar chart has no accidental holes. Statuses are deliberately varied
    (đang lập / đã chốt / tạm giữ / đã hủy) and the đã-hủy order is excluded from realised
    revenue by design (so numbers stay believable, not inflated).

    Idempotent: skips entirely once any order exists — re-runs never duplicate.
    """
    from datetime import date, datetime, timezone

    from .models.order import (
        STATUS_CANCELLED,
        STATUS_DRAFT,
        STATUS_ORDERED,
        Order,
        OrderLine,
    )
    from .models.accounting import (
        PAYMENT_RECEIPT_RECEIVED,
        RECEIPT_SOURCE_ORDER,
        PaymentReceipt,
    )
    from .models.quotation import (
        STATUS_SENT,
        STATUS_ACCEPTED,
        STATUS_REJECTED,
        Quote,
        QuoteVersion,
        QuoteItem,
    )
    from .models.estimate import Estimate, EstimateOption

    # Spec mẫu cho phiếu tính giá seed (khổ thành phẩm A4, 4 màu 2 mặt).
    _CATALOGUE_SPEC = {"finished_width": 21, "finished_height": 29.7, "colors": 4, "sides": 2}
    _CATALOGUE_SPEC_TEXT = "21×29,7 cm · 4 màu/2 mặt"
    _FLYER_SPEC = {"finished_width": 14.8, "finished_height": 21, "colors": 4, "sides": 2}
    _FLYER_SPEC_TEXT = "14,8×21 cm · 4 màu/2 mặt"

    # Guard: any order already present → assume seeded.
    if db.query(Order).first() is not None:
        return

    customers = CustomerRepository(db)
    users = UserRepository(db)
    an_phat = None
    bao_bi = None
    minh_khai = None
    for c in customers.list_scoped_all(scope="all", actor=_SeedActor()):
        if "An Phát" in c.name:
            an_phat = c
        elif "Bao Bì Việt" in c.name:
            bao_bi = c
        elif "Minh Khai" in c.name:
            minh_khai = c
    if an_phat is None and bao_bi is None and minh_khai is None:
        return

    now = datetime.now(timezone.utc)

    def _month_mid(months_ago: int, day: int = 15) -> datetime:
        """Datetime at ~mid of the calendar month `months_ago` months before now, so it
        falls squarely inside the corresponding 12-month analytics bucket. `day` shifts
        within the month to spread the frequency heatmap across weekdays."""
        y, m = now.year, now.month
        m -= months_ago
        while m <= 0:
            m += 12
            y -= 1
        # Clamp day into the month (28 is always valid) and offset for weekday variety.
        d = min(max(day, 1), 28)
        return datetime(y, m, d, 10, 0, 0, tzinfo=timezone.utc)

    def _mk_order(customer, sale_id, months_ago, lines, status=STATUS_ORDERED, day=15,
                  quote=None, qv=None, deposit_pct=30.0):
        """Đơn demo — CHỈ status draft/ordered/cancelled (không dùng dormant on_hold/change_order).
        quote!=None → đơn TỪ BÁO GIÁ: ghim quotation + snapshot giá vốn (cost_basis=quote), đánh dấu
        quote `converted_to_order`, và nếu đã chốt thì seed %cọc (đặt tại đơn) + 1 phiếu cọc đủ ngưỡng.
        quote=None → đơn NHẬP TAY: không giá vốn → biên 'không xác định' (cost_basis=none)."""
        created = _month_mid(months_ago, day)
        from_quote = quote is not None
        o = Order(
            order_no=OrderRepository(db)._next_order_no(),
            customer_id=customer.id,
            source_type="bao_gia" if from_quote else "nhap_tay",
            order_kind="moi",
            sale_user_id=sale_id,
            status=status,
            has_customer_paper=False,
            vat_pct_estimate=8,
            cost_basis="quote" if from_quote else "none",
            deposit_pct=(deposit_pct if from_quote else None),
            created_at=created,
        )
        if from_quote:
            o.quotation_id = quote.id
            o.quotation_version = (qv.version_number if qv else 1)
            o.quotation_effective_from = created.date()
            quote.status = "converted_to_order"  # → báo giá tab "Đã lên đơn"
            if status == STATUS_ORDERED:
                o.ordered_at = created
                o.ordered_by = sale_id
        subtotal = 0
        for desc, qty, unit in lines:
            subtotal += qty * unit
            o.lines.append(
                OrderLine(
                    description=desc,
                    qty=qty,
                    unit_price_snapshot=unit,  # P0 snapshot: đơn kế thừa giá đã chốt
                    cost_snapshot=(int(qty * unit * 0.8) if from_quote else None),
                    line_total=qty * unit,
                    vat_pct_estimate=8,
                )
            )
        db.add(o)
        db.flush()  # so the next _next_order_no() sees this row (unique DH###) + o.id cho phiếu thu
        # V5: đơn báo giá đã chốt → seed 1 PHIẾU THU CỌC THẬT (PaymentReceipt nguồn đơn, received)
        # đủ ngưỡng — thay OrderDeposit cũ. Cổng đủ cọc đọc Σ phiếu thu received.
        if from_quote and status == STATUS_ORDERED and deposit_pct:
            required = int(round(deposit_pct * subtotal * 1.08 / 100))
            db.add(PaymentReceipt(
                code=f"PT-SEED-{o.id}",
                source_type=RECEIPT_SOURCE_ORDER,
                order_id=o.id,
                payer_name=customer.name,
                receipt_method="bank_transfer",
                status=PAYMENT_RECEIPT_RECEIVED,
                receipt_date=created.date(),
                amount=required,
                amount_vnd=required,
                currency="VND",
                exchange_rate=1,
                content=f"Thu cọc đơn {o.order_no}",
                customer_name_snapshot=customer.name,
                order_no_snapshot=o.order_no,
                created_by_user_id=sale_id,
                received_by_user_id=sale_id,
                received_at=created,
                created_at=created,
            ))
            db.flush()
        return o

    from .repositories.order_repo import OrderRepository

    from .repositories.document_sequence_repo import DocumentSequenceRepository
    from .services.sequence_service import SequenceService

    _seq = SequenceService(DocumentSequenceRepository(db))

    def _mk_estimate(customer, sale_id, product_name, product_type, spec, quantity,
                     total_cost, created, status="converted_to_quote"):
        """Phiếu tính giá (Estimate) + 1 mức SL — nguồn giá vốn KHÓA cho báo giá.
        status='converted_to_quote' = đã pick vào báo giá (khóa khỏi picker); mã TG26 sinh
        qua SequenceService như báo giá. Trả (estimate, option)."""
        est = Estimate(
            estimate_number=_seq.generate_code("costing", at_date=created.date()),
            customer_id=customer.id if customer else None,
            product_type=product_type,
            product_name=product_name,
            status=status,
            input_spec_json=spec,
            quantity_list_json=[quantity],
            created_by=sale_id,
            created_at=created,
        )
        db.add(est)
        db.flush()
        selling = total_cost / 0.8  # biên 20% trên giá vốn → giữ số khớp báo giá
        opt = EstimateOption(
            estimate_id=est.id, quantity=quantity, total_cost=total_cost, warnings_json=[],
            margin_percent=20.0, selling_price=selling, vat_percent=10.0,
            vat_amount=selling * 0.10, final_price=selling * 1.10,
            unit_price=selling / quantity, actual_margin=20.0, included_in_quote=True,
        )
        db.add(opt)
        db.flush()
        return est, opt

    def _mk_quote(customer, sale_id, months_ago, total, status=STATUS_SENT, day=10,
                  product_name="Catalogue A4 in offset", product_type="brochure",
                  spec=None, spec_text=None, quantity=1000):
        created = _month_mid(months_ago, day)
        valid = date(created.year + (1 if created.month == 12 else 0),
                     1 if created.month == 12 else created.month + 1,
                     min(created.day, 28))
        spec = spec or _CATALOGUE_SPEC
        spec_text = spec_text or _CATALOGUE_SPEC_TEXT
        cost = int(total * 0.8)

        # Phiếu tính giá NGUỒN — báo giá khóa giá vốn từ đây (↳ tham chiếu + "Xem phiếu tính giá").
        est, opt = _mk_estimate(customer, sale_id, product_name, product_type, spec,
                                quantity, cost, created)

        # Sinh mã qua SequenceService (KHÔNG đếm tay) — giữ counter đồng bộ để
        # báo giá tạo sau seed không đụng UNIQUE quote_number.
        quote_number = _seq.generate_code("quotation", at_date=created.date())
        q = Quote(
            quote_number=quote_number,
            customer_id=customer.id,
            customer_name_snapshot=customer.name,
            estimate_id=est.id,  # phiếu đầu tiên ở header (tương thích 1-phiếu)
            salesperson_id=sale_id,
            status="accepted" if status == STATUS_ACCEPTED else status,
            valid_until=valid,
            created_at=created,
        )
        db.add(q)
        db.flush()

        qv = QuoteVersion(
            quote_id=q.id,
            version_number=1,
            status="sent" if status == STATUS_SENT else ("accepted" if status == STATUS_ACCEPTED else "rejected"),
            total_cost_snapshot=cost,
            subtotal_amount=total,
            discount_amount=0.0,
            vat_percent=10.0,
            vat_amount=int(total * 0.1),
            final_amount=int(total * 1.1),
            created_at=created,
        )
        db.add(qv)
        db.flush()
        q.current_version_id = qv.id

        qi = QuoteItem(
            quote_version_id=qv.id,
            estimate_id=est.id,
            estimate_option_id=opt.id,
            line_no=1,
            product_type=product_type,
            product_name=product_name,
            product_spec_text=spec_text,
            product_spec_snapshot_json=spec,
            quantity=quantity,
            unit="cái",
            total_cost_snapshot=cost,
            margin_percent=20.0,
            selling_price=total,
            unit_price=total / quantity,
            discount_amount=0.0,
            vat_percent=10.0,
            vat_amount=int(total * 0.1),
            final_amount=int(total * 1.1),
        )
        db.add(qi)
        db.flush()
        return q, qv

    def _mk_order_bg(customer, sale_id, months_ago, desc, qty, unit,
                     status=STATUS_ORDERED, day=15, deposit_pct=30.0):
        """Đơn TỪ BÁO GIÁ: tạo báo giá ĐÃ DUYỆT khớp SP rồi chốt thành đơn (ghim + snapshot)."""
        q, qv = _mk_quote(customer, sale_id, months_ago, qty * unit, status=STATUS_ACCEPTED,
                          product_name=desc, quantity=qty, day=max(day - 2, 1))
        return _mk_order(customer, sale_id, months_ago, [(desc, qty, unit)],
                         status=status, day=day, quote=q, qv=qv, deposit_pct=deposit_pct)

    sale1 = users.get_by_username("sale1")
    sale2 = users.get_by_username("sale2")

    # --- KH: Công ty TNHH An Phát (sale1) — khách thân thiết, mua đều 12 tháng ------
    # Sản phẩm in thật: catalogue / tờ rơi / name card / lịch. Spread mọi tháng để bar
    # chart 12T KHÔNG có lỗ, donut đủ 4 nhóm SP, heatmap rải nhiều thứ trong tuần.
    if an_phat is not None and sale1 is not None:
        _mk_order_bg(an_phat, sale1.id, 11, "Catalogue A4 32 trang", 2000, 15_000, day=8)
        _mk_order(an_phat, sale1.id, 10, [("Tờ rơi A5 4 màu", 10000, 1_200)], day=22)
        _mk_order(an_phat, sale1.id, 9, [("Name card 4 màu", 5000, 900),
                                         ("Tờ rơi A5 4 màu", 8000, 1_200)], day=5)
        _mk_order_bg(an_phat, sale1.id, 7, "Catalogue A4 32 trang", 1500, 15_000, day=17)
        _mk_order(an_phat, sale1.id, 6, [("Name card 4 màu", 3000, 900)], day=12)
        _mk_order(an_phat, sale1.id, 4, [("Lịch tết 2026 (bộ 7 tờ)", 500, 45_000)], day=26)
        _mk_order(an_phat, sale1.id, 3, [("Tờ rơi A5 4 màu", 12000, 1_200),
                                         ("Name card 4 màu", 2000, 900)], day=9)
        _mk_order_bg(an_phat, sale1.id, 1, "Catalogue A4 32 trang", 1000, 15_000, day=20)
        _mk_order(an_phat, sale1.id, 0, [("Name card 4 màu", 4000, 900)], day=3)
        # Báo giá: đủ trạng thái (duyệt / gửi / từ chối) cho lịch sử báo giá + win-rate.
        _mk_quote(an_phat, sale1.id, 11, 30_000_000, status=STATUS_ACCEPTED)
        _mk_quote(an_phat, sale1.id, 7, 22_500_000, status=STATUS_ACCEPTED)
        _mk_quote(an_phat, sale1.id, 4, 18_000_000, status=STATUS_REJECTED)
        _mk_quote(an_phat, sale1.id, 1, 15_000_000, status=STATUS_ACCEPTED)
        _mk_quote(an_phat, sale1.id, 0, 3_600_000, status=STATUS_SENT)

    # --- KH: Công ty CP Bao Bì Việt (sale2) — bao bì, đơn to thưa, có đơn hủy/nháp ---
    if bao_bi is not None and sale2 is not None:
        _mk_order_bg(bao_bi, sale2.id, 10, "Hộp giấy cao cấp", 5000, 6_000, day=14)
        _mk_order(bao_bi, sale2.id, 8, [("Túi giấy in offset", 20000, 3_500)], day=19)
        _mk_order(bao_bi, sale2.id, 6, [("Tem nhãn decal", 50000, 500)],
                  status=STATUS_CANCELLED, day=11)  # đã hủy → loại khỏi doanh số
        _mk_order_bg(bao_bi, sale2.id, 5, "Hộp giấy cao cấp", 8000, 6_000, day=24)
        _mk_order(bao_bi, sale2.id, 2, [("Túi giấy in offset", 15000, 3_500)], day=7)
        _mk_order(bao_bi, sale2.id, 1, [("Hộp giấy cao cấp", 3000, 6_000)],
                  status=STATUS_DRAFT, day=16)  # đang lập
        _mk_quote(bao_bi, sale2.id, 10, 30_000_000, status=STATUS_ACCEPTED)
        _mk_quote(bao_bi, sale2.id, 5, 48_000_000, status=STATUS_ACCEPTED)
        _mk_quote(bao_bi, sale2.id, 2, 52_500_000, status=STATUS_SENT)

    # --- KH: Nhà in Minh Khai (sale1) — khách vừa, vài đơn để không trống ------------
    if minh_khai is not None and sale1 is not None:
        _mk_order(minh_khai, sale1.id, 9, [("Tờ rơi A5 4 màu", 5000, 1_200)], day=13)
        _mk_order(minh_khai, sale1.id, 5, [("Name card 4 màu", 2000, 900)], day=21)
        _mk_order_bg(minh_khai, sale1.id, 2, "Catalogue A4 32 trang", 800, 15_000, day=6)
        _mk_quote(minh_khai, sale1.id, 5, 6_000_000, status=STATUS_ACCEPTED)
        _mk_quote(minh_khai, sale1.id, 2, 12_000_000, status=STATUS_SENT)

    # --- Báo giá NHÁP nhiều dòng: 1 báo giá gộp 2 phiếu tính giá (Catalogue + Tờ rơi) ---
    # Giữ demo "1 báo giá nhiều dòng" (như BG26-0011 trước đây) — mỗi dòng khóa 1 phiếu tính giá.
    if an_phat is not None and sale1 is not None:
        created = _month_mid(0, day=14)
        # Cột cuối = DIỄN GIẢI quy cách in dưới tên sản phẩm (mỗi dòng = 1 gạch đầu dòng trên bản in).
        ml_lines = [
            ("Catalogue A4 công ty", "brochure", _CATALOGUE_SPEC, _CATALOGUE_SPEC_TEXT, 1000, 3_264_000,
             "KT: 210×297mm\nGiấy Couche 150g\nIn 4 màu 2 mặt\nCán màng mờ · Gấp · Đóng ghim"),
            ("Tờ rơi A5 khuyến mãi", "flyer", _FLYER_SPEC, _FLYER_SPEC_TEXT, 5000, 3_655_500,
             "KT: 148×210mm\nGiấy Couche 120g\nIn 4 màu 2 mặt\nCắt thành phẩm"),
        ]
        q = Quote(
            quote_number=_seq.generate_code("quotation", at_date=created.date()),
            customer_id=an_phat.id, customer_name_snapshot=an_phat.name,
            salesperson_id=sale1.id, status="draft",
            valid_until=date(created.year, min(created.month + 1, 12), min(created.day, 28)),
            created_at=created,
        )
        db.add(q)
        db.flush()
        qv = QuoteVersion(quote_id=q.id, version_number=1, status="draft",
                          vat_percent=10.0, created_at=created)
        db.add(qv)
        db.flush()
        q.current_version_id = qv.id
        sub = disc = vat = fin = tc = 0.0
        for i, (pname, ptype, spec, stext, qty, cost, dgiai) in enumerate(ml_lines, start=1):
            est, opt = _mk_estimate(an_phat, sale1.id, pname, ptype, spec, qty, cost, created)
            if i == 1:
                q.estimate_id = est.id
            selling = cost / 0.88  # markup 12% (gói "Cạnh tranh") → khớp demo cũ
            v = selling * 0.10
            db.add(QuoteItem(
                quote_version_id=qv.id, estimate_id=est.id, estimate_option_id=opt.id,
                line_no=i, product_type=ptype, product_name=pname, product_spec_text=stext,
                dien_giai=dgiai,
                product_spec_snapshot_json=spec, quantity=qty, unit="cái",
                total_cost_snapshot=cost, margin_percent=12.0, selling_price=selling,
                unit_price=selling / qty, discount_amount=0.0, vat_percent=10.0,
                vat_amount=v, final_amount=selling + v,
            ))
            sub += selling; vat += v; fin += selling + v; tc += cost
        qv.total_cost_snapshot = tc
        qv.subtotal_amount = sub
        qv.discount_amount = disc
        qv.vat_amount = vat
        qv.final_amount = fin
        db.flush()

    # --- Phiếu tính giá ĐỘC LẬP (chưa pick) — để "Báo giá mới" luôn có phiếu để chọn ---
    if an_phat is not None and sale1 is not None:
        now0 = _month_mid(0, day=17)
        _mk_estimate(an_phat, sale1.id, "Name card 4 màu 2 mặt", "business_card",
                     {"finished_width": 9, "finished_height": 5.5, "colors": 4, "sides": 2},
                     5000, 1_200_000, now0, status="calculated")
        _mk_estimate(an_phat, sale1.id, "Tờ rơi A5 quảng cáo", "flyer",
                     _FLYER_SPEC, 10000, 4_800_000, now0, status="calculated")

    db.commit()


def seed_product_types(db: Session) -> None:
    from sqlalchemy import select
    from .models.product_type_catalog import ProductTypeCatalog

    # Bộ field hiển thị nền cho ấn phẩm tờ rời (spec §B). required ⊆ shown.
    SHEET_SHOWN = ["finished_w", "finished_h", "quantity", "colors", "sides", "paper", "machine", "sheet_size", "operations"]
    SHEET_REQ = ["finished_w", "finished_h", "quantity", "paper", "machine"]
    AREA_SHOWN = ["finished_w", "finished_h", "quantity", "colors", "paper", "machine", "operations"]
    AREA_REQ = ["finished_w", "finished_h", "quantity", "paper", "machine"]
    BOX_SHOWN = ["finished_w", "finished_h", "finished_d", "spread_w", "spread_h", "quantity", "colors", "paper", "machine", "sheet_size", "operations"]
    BOX_REQ = ["spread_w", "spread_h", "quantity", "paper", "machine"]
    PAGE_SHOWN = ["finished_w", "finished_h", "quantity", "colors", "page_count", "cover_paper", "body_paper", "machine", "sheet_size", "operations"]
    PAGE_REQ = ["finished_w", "finished_h", "quantity", "page_count", "cover_paper", "body_paper", "machine"]

    # (code, name, group, strategy, tech, shown, required, default_ops, required_ops, allowed_mats,
    #  comp_techs, dim_rule, bleed, gutter, trim, sheet_mode, has_page, cover_body, has_tooling,
    #  tooling_type, has_packaging)
    types = [
        ("business_card", "Name card", "an_pham", "sheet_based", "offset", SHEET_SHOWN, SHEET_REQ,
         ["be", "dong_goi"], [], ["paper"], ["offset", "digital"], "finished", 2, 2, 3, "by_pieces", False, False, False, None, True),
        ("flyer", "Tờ rơi", "an_pham", "sheet_based", "offset", SHEET_SHOWN, SHEET_REQ,
         ["be", "dong_goi"], [], ["paper"], ["offset", "digital"], "finished", 3, 3, 5, "by_pieces", False, False, False, None, True),
        ("brochure", "Brochure", "an_pham", "sheet_based", "offset", SHEET_SHOWN, SHEET_REQ,
         ["gap", "dong_goi"], [], ["paper"], ["offset", "digital"], "finished", 3, 3, 5, "by_pieces", False, False, False, None, True),
        ("catalogue", "Catalogue", "sach", "page_based", "offset", PAGE_SHOWN, PAGE_REQ,
         ["dong_cuon", "dong_goi"], ["dong_cuon"], ["paper"], ["offset", "digital"], "finished", 3, 3, 5, "by_pages", True, True, False, None, True),
        ("book", "Sách", "sach", "page_based", "offset", PAGE_SHOWN, PAGE_REQ,
         ["dong_cuon", "dong_goi"], ["dong_cuon"], ["paper"], ["offset", "digital"], "finished", 3, 3, 5, "by_pages", True, True, False, None, True),
        ("sticker", "Sticker", "nhan", "area_based", "offset", AREA_SHOWN, AREA_REQ,
         ["be", "dong_goi"], [], ["decal"], ["offset", "digital"], "finished", 2, 2, 3, "by_pieces", False, False, True, "khuon_be", True),
        ("label", "Tem nhãn", "nhan", "area_based", "offset", AREA_SHOWN, AREA_REQ,
         ["be", "dong_goi"], [], ["decal", "pp"], ["offset", "digital"], "finished", 2, 2, 3, "by_pieces", False, False, True, "khuon_be", True),
        ("paper_box", "Hộp giấy", "bao_bi", "box_based", "offset", BOX_SHOWN, BOX_REQ,
         ["be", "dan_hop", "dong_goi"], ["be", "dan_hop"], ["paper", "carton"], ["offset", "flexo"], "spread", 3, 3, 5, "by_pieces", False, False, True, "khuon_be", True),
        ("paper_bag", "Túi giấy", "bao_bi", "box_based", "offset", BOX_SHOWN, BOX_REQ,
         ["be", "dan_hop", "dong_goi"], ["be", "dan_hop"], ["paper"], ["offset"], "spread", 3, 3, 5, "by_pieces", False, False, True, "khuon_be", True),
        ("banner", "Banner", "an_pham", "area_based", "large_format", AREA_SHOWN, AREA_REQ,
         ["dong_goi"], [], ["pp", "canvas"], ["large_format"], "finished", 0, 0, 0, "manual", False, False, False, None, True),
        ("envelope", "Bao thư", "bao_bi", "sheet_based", "offset", SHEET_SHOWN, SHEET_REQ,
         ["be", "dan_hop", "dong_goi"], ["dan_hop"], ["paper"], ["offset"], "spread", 3, 3, 5, "by_pieces", False, False, True, "khuon_be", True),
    ]

    for row in types:
        (code, name, group, strategy, tech, shown, required, default_ops, required_ops, allowed_mats,
         comp_techs, dim_rule, bleed, gutter, trim, sheet_mode, has_page, cover_body, has_tooling,
         tooling_type, has_packaging) = row
        # box_based dùng khổ trải nhưng nếu dim_rule='spread' thì shown đã có spread_w/h (BOX_SHOWN).
        existing = db.execute(
            select(ProductTypeCatalog).where(ProductTypeCatalog.product_type == code)
        ).scalars().first()
        if not existing:
            db.add(ProductTypeCatalog(
                product_type=code, name=name, product_group=group, calculation_strategy=strategy,
                technology=tech, shown_fields=shown, required_fields=required,
                default_operations=default_ops, required_operations=required_ops,
                allowed_materials=allowed_mats, compatible_technologies=comp_techs,
                dimension_rule_type=dim_rule, default_bleed_mm=bleed, default_gutter_mm=gutter,
                default_trim_mm=trim, sheet_count_mode=sheet_mode, has_page_count=has_page,
                has_cover_body_split=cover_body, has_tooling=has_tooling, default_tooling_type=tooling_type,
                has_packaging=has_packaging, default_pack_qty=(50 if has_packaging else 0),
                is_active=True,
            ))
    db.commit()


def seed_materials(db: Session) -> None:
    from sqlalchemy import select
    from .models.material import Material, MaterialCost, GROUP_FROM_TYPE
    from .repositories.material_repo import MaterialRepository
    from datetime import date

    repo = MaterialRepository(db)
    if db.execute(select(Material)).first() is not None:
        return

    eff = date(2026, 1, 1)

    def mk(*, name, material_type, unit, price_unit, unit_price, group=None, **extra):
        """Tạo vật tư + 1 dòng giá (dữ liệu mẫu §10 — docs/VAT_TU_DON_GIA.md)."""
        m = repo.create(
            name=name, material_type=material_type, unit=unit,
            width_cm=extra.pop("width_cm", None), height_cm=extra.pop("height_cm", None),
            gsm=extra.pop("gsm", None), paper_family=extra.pop("paper_family", None),
            surface=extra.pop("surface", None),
            default_waste_pct=extra.pop("default_waste_pct", 0.0),
        )
        m.material_group = group or GROUP_FROM_TYPE.get(material_type)
        m.base_uom = extra.pop("base_uom", unit)
        m.purchase_uom = extra.pop("purchase_uom", price_unit)
        m.consumption_uom = extra.pop("consumption_uom", unit)
        m.conversion_method = extra.pop("conversion_method", None)
        for k, v in extra.items():
            setattr(m, k, v)
        db.add(m)
        db.flush()
        db.add(MaterialCost(material_id=m.id, price_unit=price_unit, unit_price=unit_price, effective_from=eff))
        return m

    # ── Bộ vật tư nền (luôn seed) — giữ đúng bộ test cũ để golden/stat không đổi ──
    mk(name="Couche 150gsm 65x86", material_type="paper", unit="to", price_unit="ram", unit_price=750000,
       width_cm=65, height_cm=86, gsm=150, paper_family="Couche", surface="bong",
       conversion_method="ream_500", consumption_uom="to")
    mk(name="Couche 300gsm 79x109", material_type="paper", unit="to", price_unit="ram", unit_price=1200000,
       width_cm=79, height_cm=109, gsm=300, paper_family="Couche", surface="mo",
       conversion_method="ream_500", consumption_uom="to")
    mk(name="Decal giấy đế vàng", material_type="decal", unit="m2", price_unit="m2", unit_price=15000,
       conversion_method="area_m2", default_waste_pct=2.0)
    mk(name="Màng mờ nhiệt", material_type="lamination", unit="m2", price_unit="m2", unit_price=2500,
       group="film", film_type="matt", conversion_method="area_m2", default_waste_pct=1.0)

    # ── Mẫu mở rộng §10 (gồm MỰC) — demo-gate. Mực làm phát sinh dòng chi phí mực cho mọi job offset
    # nên KHÔNG seed trong test (golden đóng băng không có mực), giống seed_norms ink trước đây. ──
    if settings.seed_demo:
        mk(name="Ivory 300gsm 79x109", material_type="paper", unit="to", price_unit="kg", unit_price=31000,
           width_cm=79, height_cm=109, gsm=300, paper_family="Ivory", surface="bong",
           conversion_method="gsm_area", consumption_uom="to")
        mk(name="Duplex 350gsm 79x109", material_type="carton", unit="to", price_unit="kg", unit_price=25000,
           width_cm=79, height_cm=109, gsm=350, paper_family="Duplex",
           conversion_method="gsm_area", consumption_uom="to")
        # Mực (đ/1.000 lượt-màu — engine đọc TỪ ĐÂY). INK_CMYK = mực offset mặc định (id nhỏ nhất nhóm ink).
        mk(name="Mực offset CMYK", material_type="chemical", unit="kg", price_unit="nghin_luot", unit_price=500,
           group="ink", ink_type="offset", ink_color_system="CMYK", consumption_uom="luot", conversion_method="none")
        mk(name="Mực Pantone", material_type="chemical", unit="kg", price_unit="nghin_luot", unit_price=1200,
           group="ink", ink_type="pantone", ink_color_system="spot", consumption_uom="luot", conversion_method="none")
        mk(name="Màng bóng nhiệt", material_type="lamination", unit="m2", price_unit="m2", unit_price=2000,
           group="film", film_type="gloss", conversion_method="area_m2", default_waste_pct=1.0)
        mk(name="Keo dán hộp", material_type="glue", unit="kg", price_unit="kg", unit_price=45000,
           group="glue", consumption_uom="gram", conversion_method="none")
        mk(name="Thùng carton đóng gói", material_type="chemical", unit="cai", price_unit="cai", unit_price=8000,
           group="packaging", conversion_method="none")

    db.commit()


def seed_machines(db: Session) -> None:
    from sqlalchemy import select
    from .models.machine import Machine
    from .repositories.machine_repo import MachineRepository
    from datetime import date
    
    repo = MachineRepository(db)
    
    if db.execute(select(Machine)).first() is None:
        # Máy in offset — khổ tính bằng CM (toàn hệ dùng cm). Setup hạt (giờ): base + 0.1/màu,
        # vệ sinh 0.25, đổi kẽm 0.05/bản → khớp ví dụ spec (OFFSET_102: 4 màu/4 bản = setup 0.9 +
        # 0.25 + 0.2). (code, tên, giấy w×h, in w×h, tốc độ, base_setup_h, num_units, đơn giá, min_charge)
        offsets = [
            ("OFFSET_52_01", "Máy Offset 52 - 2 màu", 36, 52, 34, 50, 4000, 0.4, 2, 300000, 800000),
            ("OFFSET_72_01", "Máy Offset 72 - 4 màu", 52, 72, 50, 70, 5000, 0.5, 4, 400000, 1200000),
            ("OFFSET_102_01", "Máy Offset 102 - 4 màu", 72, 102, 70, 100, 6000, 0.5, 4, 500000, 1500000),
            ("OFFSET_109_01", "Máy Offset 109 - 5 màu", 79, 109, 77, 107, 6000, 0.6, 5, 600000, 1800000),
        ]
        for code, name, gw, gh, pw, ph, spd, base_h, units, rate, minc in offsets:
            m = repo.create(
                code=code, name=name, machine_type="offset", process_type="in",
                machine_group="may_in", status="active",
                speed=spd, speed_unit="to/gio",
                max_width_cm=gw, max_height_cm=gh, min_width_cm=round(gw / 2), min_height_cm=round(gh / 2),
                max_print_width_cm=pw, max_print_height_cm=ph,
                gripper_cm=1.0, side_margin_cm=0.5, top_bottom_margin_cm=0.5,
                setup_time_base_hour=base_h, setup_time_per_color_hour=0.1,
                cleaning_time_hour=0.25, plate_change_time_per_plate_hour=0.05,
                setup_waste_sheets=200, num_ink_units=units, supports_perfecting=False,
                rounding_hour_policy="0.01", overhead_included=True, operator_included=True,
            )
            repo.add_machine_rate(
                machine_id=m.id, hourly_rate=rate, min_charge=minc, effective_from=date(2026, 1, 1),
            )

        # Máy in kỹ thuật số (giữ 1 máy digital minh hoạ).
        digital = repo.create(
            code="DIGITAL_01", name="Konica Minolta C6085", machine_type="digital", process_type="in",
            machine_group="may_in", speed=85, speed_unit="trang/phut",
            max_width_cm=33, max_height_cm=48, min_width_cm=10, min_height_cm=15,
            setup_time_mins=5, setup_waste_sheets=5,
        )
        repo.add_machine_rate(machine_id=digital.id, hourly_rate=200000, min_charge=50000, effective_from=date(2026, 1, 1))

        # Máy sau in (dùng chung DM Máy cho công đoạn nội bộ) — nhóm cán/bế/xén.
        post = [
            ("LAM_01", "Máy cán màng 01", "can_mang", "may_can", 3000, 250000),
            ("DIECUT_01", "Máy bế 01", "be", "may_be", 2000, 300000),
            ("CUT_01", "Máy xén 01", "xen", "may_xen", 1000, 200000),
        ]
        for code, name, ptype, grp, spd, rate in post:
            m = repo.create(
                code=code, name=name, machine_type="other", process_type=ptype,
                machine_group=grp, status="active", speed=spd, speed_unit="to/gio",
                setup_time_base_hour=0.3, cleaning_time_hour=0.1,
            )
            repo.add_machine_rate(machine_id=m.id, hourly_rate=rate, min_charge=100000, effective_from=date(2026, 1, 1))

        db.commit()


def seed_operations(db: Session) -> None:
    from sqlalchemy import select
    from .models.operation import Operation
    from .repositories.operation_repo import OperationRepository
    from datetime import date
    
    repo = OperationRepository(db)
    
    if db.execute(select(Operation)).first() is None:
        # spec §5 — dữ liệu mẫu công đoạn kèm cấu hình §A–§G. internal_pricing_method='per_qty' +
        # pricing_method='theo_sp' tái tạo đúng công thức gia công cũ; các field khác là metadata
        # (nhóm/thứ tự/công thức lượng/khuôn/hao hụt) để engine & UI dùng đúng theo spec.
        can = repo.create(
            name="Cán màng mờ",
            operation_type="can_mang",
            unit="m2",
            basis_quantity="m2",
            pricing_method="theo_sp",
            process_group="sau_in",
            process_type="both",
            default_sequence=30,
            quantity_formula_type="area_m2",
            internal_pricing_method="per_qty",
            has_yield_loss=True,
            default_yield_rate=98.0,
            default_yield_rule="YIELD_LAMINATION",
            allow_outsource=True,
        )
        repo.add_operation_rate(operation_id=can.id, setup_fee=100000, run_rate=1200, labor_rate=300, min_charge=250000, speed=1500, setup_time_mins=20, hourly_rate=250000, outsource_supplier="NCC Cán màng A", outsource_unit_price=1000, outsource_min_charge=300000, outsource_setup_fee=100000, effective_from=date(2026, 1, 1))

        be = repo.create(
            name="Bế hộp",
            operation_type="be",
            unit="cai",
            basis_quantity="to",
            pricing_method="theo_sp",
            process_group="sau_in",
            process_type="both",
            default_sequence=40,
            quantity_formula_type="print_sheet_qty",
            internal_pricing_method="per_qty",
            has_tooling=True,
            tooling_type="khuon_be",
            has_yield_loss=True,
            default_yield_rate=98.0,
            default_yield_rule="YIELD_DIECUT",
            allow_outsource=True,
        )
        repo.add_operation_rate(operation_id=be.id, setup_fee=300000, run_rate=500, labor_rate=100, min_charge=500000, speed=2000, setup_time_mins=30, tooling_unit_price=800000, outsource_supplier="NCC Bế A", outsource_unit_price=250, outsource_min_charge=300000, outsource_setup_fee=100000, outsource_transport_fee=200000, effective_from=date(2026, 1, 1))

        dong = repo.create(
            name="Đóng gói thùng carton",
            operation_type="dong_goi",
            unit="thung",
            basis_quantity="thung",
            pricing_method="theo_sp",
            process_group="dong_goi",
            process_type="internal",
            default_sequence=90,
            quantity_formula_type="pack_qty",
            internal_pricing_method="per_qty",
            allow_outsource=False,
        )
        repo.add_operation_rate(operation_id=dong.id, setup_fee=0, run_rate=20000, labor_rate=5000, min_charge=50000, speed=20, setup_time_mins=0, effective_from=date(2026, 1, 1))

        # #8 — bổ sung công đoạn mà seed_product_types tham chiếu (gap/dong_cuon/dan_hop) để lookup không treo.
        gap = repo.create(name="Gấp thành phẩm", operation_type="gap", unit="to", basis_quantity="to", pricing_method="theo_sp", process_group="sau_in", default_sequence=50, quantity_formula_type="print_sheet_qty", allow_outsource=False)
        repo.add_operation_rate(operation_id=gap.id, setup_fee=50000, run_rate=100, labor_rate=50, min_charge=100000, speed=3000, setup_time_mins=15, effective_from=date(2026, 1, 1))

        dong_cuon = repo.create(name="Đóng cuốn (keo nhiệt)", operation_type="dong_cuon", unit="cuon", basis_quantity="cuon", pricing_method="theo_sp", process_group="sau_in", process_type="both", default_sequence=70, quantity_formula_type="book_qty", allow_outsource=True)
        repo.add_operation_rate(operation_id=dong_cuon.id, setup_fee=200000, run_rate=800, labor_rate=200, min_charge=300000, speed=500, setup_time_mins=20, outsource_supplier="NCC Đóng cuốn A", outsource_unit_price=700, outsource_min_charge=400000, effective_from=date(2026, 1, 1))

        dan_hop = repo.create(name="Dán hộp", operation_type="dan_hop", unit="cai", basis_quantity="cai", pricing_method="theo_sp", process_group="sau_in", default_sequence=60, quantity_formula_type="finished_qty", allow_outsource=False)
        repo.add_operation_rate(operation_id=dan_hop.id, setup_fee=100000, run_rate=300, labor_rate=100, min_charge=200000, speed=1000, setup_time_mins=15, effective_from=date(2026, 1, 1))

        db.commit()


def seed_plate_die_rates(db: Session) -> None:
    from sqlalchemy import select
    from .models.plate_die_rate import PlateDieRate
    from .models.machine import Machine
    from .repositories.plate_die_rate_repo import PlateDieRateRepository
    from datetime import date

    repo = PlateDieRateRepository(db)
    if db.execute(select(PlateDieRate)).first() is not None:
        return
    eff = date(2026, 1, 1)
    offset_ids = [m.id for m in db.execute(
        select(Machine).where(Machine.machine_type == "offset")
    ).scalars()] or None

    # A. Kẽm offset — chọn theo máy (PLATE_72 gắn máy offset thật; 102/52 là mẫu mọi-máy).
    repo.add_rate(code="PLATE_72", name="Kẽm CTP máy 72", plate_type="ban_kem_offset",
                  technology="offset", unit="ban", plate_kind="ctp",
                  plate_width_mm=605, plate_height_mm=745, machine_ids=offset_ids,
                  unit_price=100000, pricing_method="fixed", effective_from=eff)
    repo.add_rate(code="PLATE_102", name="Kẽm CTP máy 102", plate_type="ban_kem_offset",
                  technology="offset", unit="ban", plate_kind="ctp",
                  plate_width_mm=790, plate_height_mm=1030, machine_ids=None,
                  unit_price=120000, pricing_method="fixed", effective_from=eff)
    repo.add_rate(code="PLATE_52", name="Kẽm CTP máy 52", plate_type="ban_kem_offset",
                  technology="offset", unit="ban", plate_kind="ctp",
                  plate_width_mm=510, plate_height_mm=400, machine_ids=None,
                  unit_price=60000, pricing_method="fixed", effective_from=eff)

    # B. Khuôn — pricing_method + dùng lại.
    repo.add_rate(code="DIE_BOX_STD", name="Khuôn bế hộp tiêu chuẩn", plate_type="khuon_be",
                  technology="be", unit="bo", unit_price=800000, min_charge=500000,
                  pricing_method="fixed", reusable=True, reuse_price_method="maintenance_fee",
                  maintenance_fee=100000, effective_from=eff)
    repo.add_rate(code="FOIL_AREA", name="Khuôn ép kim (theo diện tích)", plate_type="khuon_ep_kim",
                  technology="ep_kim", unit="cm2", unit_price=0, unit_price_area=2000,
                  min_charge=300000, pricing_method="area", reusable=True,
                  reuse_price_method="zero", effective_from=eff)
    repo.add_rate(code="EMBOSS_STD", name="Khuôn dập nổi tiêu chuẩn", plate_type="khuon_dap_noi",
                  technology="dap_noi", unit="bo", unit_price=700000, min_charge=500000,
                  pricing_method="fixed", reusable=True, reuse_price_method="maintenance_fee",
                  maintenance_fee=100000, effective_from=eff)
    db.commit()


def seed_norms(db: Session) -> None:
    from sqlalchemy import select
    from .models.norm import Norm
    from .repositories.norm_repo import NormRepository
    from .services.norm_service import canonicalize_context
    from datetime import date
    
    from .models.norm import GROUP_TO_KEY

    repo = NormRepository(db)
    if db.execute(select(Norm)).first() is not None:
        return

    eff = date(2026, 1, 1)

    def mk(group: str, method: str, code: str, name: str, *, value: float = 0.0, **kw) -> None:
        """Dựng 1 rule định mức (dữ liệu mẫu §5 — docs/DINH_MUC_BU_HAO.md)."""
        norm_key = GROUP_TO_KEY.get(group, group)
        ctx = kw.pop("context", None)
        db.add(Norm(
            norm_key=norm_key, waste_group=group, calculation_method=method,
            code=code, name=name, value=value,
            context=ctx, context_key=canonicalize_context(ctx),
            effective_from=eff, **kw,
        ))

    # ── A. Tỷ lệ đạt theo công đoạn (YIELD_RATE) ──
    mk("YIELD_RATE", "PERCENT", "YIELD_PRINT_STD", "Tỷ lệ đạt in offset", value=0.97)  # khâu in (no-op)
    mk("YIELD_RATE", "PERCENT", "YIELD_LAMINATION", "Tỷ lệ đạt cán màng", value=0.99, operation_key="can_mang")
    mk("YIELD_RATE", "PERCENT", "YIELD_DIECUT", "Tỷ lệ đạt bế", value=0.98, operation_key="be")
    mk("YIELD_RATE", "PERCENT", "YIELD_GLUE_BOX", "Tỷ lệ đạt dán hộp", value=0.99, operation_key="dan_hop")

    # ── B. Bù hao setup / makeready (SETUP_WASTE) ──
    mk("SETUP_WASTE", "COMBINED", "MR_PRINT", "Makeready in offset",
       setup_waste_qty=100, setup_waste_per_color=30, setup_waste_per_side=50,
       min_waste_qty=100, max_waste_qty=1000)
    mk("SETUP_WASTE", "FIXED", "MR_DIECUT", "Setup bế", setup_waste_qty=30, operation_key="be")
    mk("SETUP_WASTE", "FIXED", "MR_LAMINATION", "Setup cán màng", setup_waste_qty=20, operation_key="can_mang")

    # ── C. Bù hao chạy máy (RUNNING_WASTE) theo bậc sản lượng ──
    mk("RUNNING_WASTE", "PERCENT", "RW_PRINT_SMALL", "Hao chạy in ≤500", value=0.05, qty_min=1, qty_max=500, min_waste_qty=20)
    mk("RUNNING_WASTE", "PERCENT", "RW_PRINT_MEDIUM", "Hao chạy in 501–2.000", value=0.03, qty_min=501, qty_max=2000, min_waste_qty=20)
    mk("RUNNING_WASTE", "PERCENT", "RW_PRINT_LARGE", "Hao chạy in >2.000", value=0.02, qty_min=2001, qty_max=None)
    mk("RUNNING_WASTE", "PERCENT", "RW_DIECUT", "Hao chạy bế", value=0.015, operation_key="be")

    # ── D. Hao giấy riêng (PAPER_EXTRA_WASTE) — cộng vào số tờ mua ──
    mk("PAPER_EXTRA_WASTE", "PERCENT", "PAPER_CUT_WASTE", "Hao cắt giấy", value=0.01, min_waste_qty=10, paper_add_to_purchase=True)

    # Đơn giá mực đã DỜI sang danh mục Vật tư (#2) — xem seed_materials (Mực offset CMYK, price_unit=nghin_luot).
    db.commit()


def seed_document_sequences(db: Session) -> None:
    from sqlalchemy import select
    from .models.document_sequence import DocumentSequence
    from .repositories.document_sequence_repo import DocumentSequenceRepository
    
    repo = DocumentSequenceRepository(db)
    if db.execute(select(DocumentSequence)).first() is None:
        for doc_type in ["costing", "quotation", "order", "job"]:
            repo.increment_and_get(doc_type, 2026)
        db.commit()


def seed_employees(db: Session) -> None:
    """Seed a spread of sample employees (Hồ sơ nhân sự demo, module `nhan_su`) covering
    every status + a Quá trình công tác timeline + one account link (🔑). Idempotent:
    skips entirely once any employee exists so re-runs never duplicate."""
    from datetime import date, timedelta

    from .models.employee import (
        EVENT_CONFIRMED,
        EVENT_HIRED,
        EVENT_LEAVE_START,
        EVENT_PROMOTED,
        EVENT_RESIGNED,
        STATUS_ACTIVE,
        STATUS_ON_LEAVE,
        STATUS_PROBATION,
        STATUS_RESIGNED,
    )
    from .repositories.employee_repo import EmployeeRepository

    repo = EmployeeRepository(db)
    # Cheap idempotency guard: if the table already has rows, assume seeded.
    if repo.list(scope="all", actor=_SeedActor(), size=1)[1] > 0:
        return

    depts = DepartmentRepository(db)
    users = UserRepository(db)
    today = date.today()

    def _dept(name: str) -> int | None:
        d = depts.get_by_name(name)
        return d.id if d is not None else None

    hcns = _dept("Hành chính nhân sự")
    kd = _dept("Kinh doanh")

    def mk(
        *, full_name, department_id, position, status, hire_date,
        gender=None, national_id=None, phone=None, social_insurance_no=None,
        job_grade=None, probation_end_date=None, link_username=None,
    ):
        emp = repo.create(
            full_name=full_name, department_id=department_id, position=position,
            status=status, hire_date=hire_date, gender=gender, national_id=national_id,
            phone=phone, social_insurance_no=social_insurance_no, job_grade=job_grade,
            probation_end_date=probation_end_date,
        )
        # Quá trình công tác: hired (thử việc) → confirmed → (nâng bậc) → (nghỉ dài hạn/việc).
        repo.add_event(employee_id=emp.id, event_type=EVENT_HIRED, effective_date=hire_date,
                       field="status", from_value=None, to_value=STATUS_PROBATION,
                       note="Vào làm", actor_user_id=None)
        confirmed = hire_date + timedelta(days=60)
        if status in (STATUS_ACTIVE, STATUS_ON_LEAVE, STATUS_RESIGNED):
            repo.add_event(employee_id=emp.id, event_type=EVENT_CONFIRMED, effective_date=confirmed,
                           field="status", from_value=STATUS_PROBATION, to_value=STATUS_ACTIVE,
                           note="Đạt yêu cầu thử việc", actor_user_id=None)
        if job_grade:
            repo.add_event(employee_id=emp.id, event_type=EVENT_PROMOTED,
                           effective_date=confirmed + timedelta(days=400), field="job_grade",
                           from_value=None, to_value=job_grade, note="Nâng bậc thợ", actor_user_id=None)
        if status == STATUS_ON_LEAVE:
            repo.add_event(employee_id=emp.id, event_type=EVENT_LEAVE_START,
                           effective_date=today - timedelta(days=20), field="status",
                           from_value=STATUS_ACTIVE, to_value=STATUS_ON_LEAVE,
                           note="Nghỉ thai sản", actor_user_id=None)
        if status == STATUS_RESIGNED:
            resigned_on = today - timedelta(days=40)
            repo.add_event(employee_id=emp.id, event_type=EVENT_RESIGNED, effective_date=resigned_on,
                           field="status", from_value=STATUS_ACTIVE, to_value=STATUS_RESIGNED,
                           note="Tự xin nghỉ", actor_user_id=None)
            repo.update(emp, resign_date=resigned_on, resign_reason="Tự xin nghỉ")
        # Nối 1 tài khoản login sẵn có để demo 🔑 (nếu user tồn tại và chưa gắn NV khác).
        if link_username:
            u = users.get_by_username(link_username)
            if u is not None and repo.get_by_user_id(u.id) is None:
                repo.update(emp, user_id=u.id)
        return emp

    mk(full_name="Trần Văn An", department_id=hcns, position="Trưởng phòng HCNS",
       status=STATUS_ACTIVE, hire_date=date(2019, 3, 1), gender="male",
       national_id="079083001234", phone="0903001234", social_insurance_no="7900010001")
    mk(full_name="Lê Thị Bình", department_id=hcns, position="Nhân viên nhân sự",
       status=STATUS_ACTIVE, hire_date=date(2021, 6, 15), gender="female",
       national_id="079185002345", phone="0903002345")
    mk(full_name="Phạm Minh Cường", department_id=kd, position="Nhân viên Sales",
       status=STATUS_ACTIVE, hire_date=date(2022, 1, 10), gender="male",
       national_id="079090003456", phone="0903003456", link_username="sale1")
    mk(full_name="Nguyễn Thị Dung", department_id=kd, position="Nhân viên Sales",
       status=STATUS_PROBATION, hire_date=today - timedelta(days=45), gender="female",
       national_id="079193004567", phone="0903004567", probation_end_date=today + timedelta(days=15))
    mk(full_name="Vũ Đức Em", department_id=hcns, position="Thợ in offset", job_grade="3/7",
       status=STATUS_ACTIVE, hire_date=date(2018, 9, 20), gender="male",
       national_id="079088005678", phone="0903005678")
    mk(full_name="Hoàng Văn Phúc", department_id=hcns, position="Thợ chế bản", job_grade="2/7",
       status=STATUS_ON_LEAVE, hire_date=date(2020, 2, 3), gender="male",
       national_id="079091006789", phone="0903006789")
    mk(full_name="Đặng Thị Giang", department_id=hcns, position="Nhân viên văn thư",
       status=STATUS_RESIGNED, hire_date=date(2019, 7, 1), gender="female",
       national_id="079192007890", phone="0903007890")
    mk(full_name="Bùi Quốc Hùng", department_id=hcns, position="Thợ xén-bế", job_grade="4/7",
       status=STATUS_ACTIVE, hire_date=date(2017, 4, 12), gender="male",
       national_id="079085008901", phone="0903008901")
    # Nối tài khoản admin vào 1 hồ sơ (để demo tự chấm công GPS bằng chính tài khoản admin).
    mk(full_name="Nguyễn Văn Giám", department_id=_dept("Ban giám đốc"), position="Giám đốc",
       status=STATUS_ACTIVE, hire_date=date(2015, 1, 5), gender="male",
       national_id="079080000001", phone="0903000000", link_username="admin")

    db.commit()


def seed_work_shifts(db: Session) -> None:
    """Seed ca làm việc demo (Ca kíp) + gán ca mặc định cho NV demo (theo họ tên). Idempotent."""
    from .repositories.attendance_repo import AttendanceRepository
    from .repositories.employee_repo import EmployeeRepository

    repo = AttendanceRepository(db)
    if repo.list_shifts():
        return
    shifts = {
        "Hành chính": repo.create_shift(name="Hành chính", start_minute=8 * 60, end_minute=17 * 60,
                                        is_overnight=False, grace_minutes=5, is_active=True),
        "Ca 1": repo.create_shift(name="Ca 1", start_minute=6 * 60, end_minute=14 * 60,
                                  is_overnight=False, grace_minutes=5, is_active=True),
        "Ca 2": repo.create_shift(name="Ca 2", start_minute=14 * 60, end_minute=22 * 60,
                                  is_overnight=False, grace_minutes=5, is_active=True),
        "Ca 3": repo.create_shift(name="Ca 3", start_minute=22 * 60, end_minute=6 * 60,
                                  is_overnight=True, grace_minutes=5, is_active=True),
    }
    assign = {
        "Trần Văn An": "Hành chính", "Lê Thị Bình": "Hành chính", "Phạm Minh Cường": "Hành chính",
        "Nguyễn Văn Giám": "Hành chính", "Nguyễn Thị Dung": "Hành chính",
        "Vũ Đức Em": "Ca 1", "Hoàng Văn Phúc": "Ca 2", "Bùi Quốc Hùng": "Ca 3",
    }
    emps = EmployeeRepository(db)
    for e in emps.list_scoped_all(scope="all", actor=_SeedActor()):
        sh = assign.get(e.full_name)
        if sh and shifts.get(sh) is not None:
            emps.update(e, default_shift_id=shifts[sh].id)


def seed_work_locations(db: Session) -> None:
    """Seed 1 điểm chấm công demo (module `nhan_su`). Idempotent."""
    from .repositories.attendance_repo import AttendanceRepository

    repo = AttendanceRepository(db)
    if repo.list_locations():
        return
    repo.create_location(
        name="Xưởng in Sao Việt Nhật (demo)",
        latitude=10.7769000, longitude=106.7009000, radius_m=150,
        note="Toạ độ demo (TP.HCM) — HCNS chỉnh lại theo thực địa.", is_active=True,
    )


def seed_attendance(db: Session) -> None:
    """Seed vài bản ghi chấm công demo cho NV có tài khoản (tại điểm demo, trong phạm vi),
    để Bảng chấm công + lịch sử không trống. Idempotent."""
    from datetime import datetime, timedelta, timezone

    from .repositories.attendance_repo import AttendanceRepository
    from .repositories.employee_repo import EmployeeRepository
    from .repositories.user_repo import UserRepository

    repo = AttendanceRepository(db)
    if repo.list_all(limit=1):
        return
    loc = repo.list_locations(active_only=True)
    if not loc:
        return
    loc = loc[0]

    users = UserRepository(db)
    emps = EmployeeRepository(db)
    now = datetime.now(timezone.utc)

    # NV chấm công demo = những người có tài khoản (admin↔GĐ, sale1↔NV003).
    targets = []
    for username in ("admin", "sale1"):
        u = users.get_by_username(username)
        if u is None:
            continue
        e = emps.get_by_user_id(u.id)
        if e is not None:
            targets.append(e)

    # 2 ngày ĐÃ TRỌN gần nhất (không phải hôm nay), mỗi ngày 1 cặp VÀO/RA tại điểm demo.
    # KHÔNG seed hôm nay: RA ~17h có thể rơi vào TƯƠNG LAI so với "now" → làm hỏng logic
    # tự-luân-phiên (last_log tương lai khiến nút cứ đề nghị VÀO). Xem _next_check_type.
    for emp in targets:
        for days_ago in (2, 1):
            day_in = now - timedelta(days=days_ago, hours=(now.hour - 1))  # ~sáng
            day_out = day_in + timedelta(hours=9)
            for checked_at, ctype in ((day_in, "in"), (day_out, "out")):
                repo.create_log(
                    employee_id=emp.id, work_location_id=loc.id, check_type=ctype,
                    checked_at=checked_at, latitude=float(loc.latitude), longitude=float(loc.longitude),
                    distance_m=12.0, within_range=True,
                )
    db.commit()


def backfill_user_codes(db: Session) -> None:
    """Assign an 'NV' code (spec-07) to any user still missing one, oldest id first.
    Idempotent: users created via the repository already get a code, so on a fresh DB
    this is a no-op; it only fills legacy rows that predate the code column."""
    users = UserRepository(db)
    changed = False
    for u in users.list_all():
        if not u.code:
            u.code = users.next_code()
            changed = True
    if changed:
        db.commit()


def backfill_employee_profiles(db: Session) -> None:
    """LUẬT: mọi tài khoản đăng nhập PHẢI thuộc một hồ sơ nhân viên — KHÔNG trừ ai, kể cả tài
    khoản hệ thống `admin` (chủ đầu tư chốt: admin có hồ sơ TRỐNG, HCNS sửa sau). Tạo hồ sơ cho
    mọi tài khoản còn mồ côi (tài khoản demo cũ hoặc dữ liệu cũ có trước luật này). Idempotent:
    tài khoản đã có hồ sơ thì bỏ qua — nên chạy SAU `seed_employees` (admin đã nối NV009 ở dev
    thì backfill không đụng vào).

    Hồ sơ admin có mặt ⇒ luật "nghỉ việc ⇒ chặn login" (auth_service) vươn tới cả admin; chốt
    chặn ở nguồn: `EmployeeService._apply_status` cấm cho-nghỉ-việc hồ sơ gắn tài khoản hệ thống,
    nên không ai khóa cứng được đường vào hệ thống."""
    from datetime import date

    from .models.employee import STATUS_ACTIVE
    from .repositories.employee_repo import EmployeeRepository

    repo = EmployeeRepository(db)
    users = UserRepository(db)
    for u in users.list_all():
        if repo.get_by_user_id(u.id) is not None:
            continue
        emp = repo.create(
            full_name=u.name or u.username,
            department_id=u.department_id,
            status=STATUS_ACTIVE,
            hire_date=date.today(),
        )
        repo.update(emp, user_id=u.id)


def seed_leaves(db: Session) -> None:
    """Seed loại nghỉ demo (Nghỉ phép) + 1 đơn đã duyệt + 1 đơn chờ cho NV admin-linked.
    Idempotent."""
    from datetime import date, datetime, timezone

    from .models.leave import STATUS_APPROVED, STATUS_PENDING
    from .repositories.employee_repo import EmployeeRepository
    from .repositories.leave_repo import LeaveRepository
    from .repositories.user_repo import UserRepository

    repo = LeaveRepository(db)
    if repo.list_types():
        return
    annual = repo.create_type(name="Phép năm", is_paid=True, annual_quota=12, is_active=True)
    repo.create_type(name="Nghỉ ốm", is_paid=True, annual_quota=0, is_active=True)
    unpaid = repo.create_type(name="Không lương", is_paid=False, annual_quota=0, is_active=True)
    repo.create_type(name="Việc riêng", is_paid=False, annual_quota=0, is_active=True)

    u = UserRepository(db).get_by_username("admin")
    emp = EmployeeRepository(db).get_by_user_id(u.id) if u is not None else None
    if emp is not None:
        today = date.today()
        y, m = today.year, today.month
        # Đơn ĐÃ DUYỆT (phép năm, ngày 10–11) → Bảng công tháng hiện "P".
        repo.create_request(employee_id=emp.id, leave_type_id=annual.id,
                            start_date=date(y, m, 10), end_date=date(y, m, 11), days=2,
                            reason="Về quê", status=STATUS_APPROVED, created_by=u.id,
                            decided_by=u.id, decided_at=datetime.now(timezone.utc))
        # Đơn CHỜ DUYỆT (không lương, ngày 20) → tab Duyệt đơn có việc.
        repo.create_request(employee_id=emp.id, leave_type_id=unpaid.id,
                            start_date=date(y, m, 20), end_date=date(y, m, 20), days=1,
                            reason="Việc gia đình", status=STATUS_PENDING, created_by=u.id)


def seed_payroll(db: Session) -> None:
    """Seed cấu hình + demo Lương (module `luong`): tham số, quy tắc mức lương (khớp bảng
    thật: tổ In theo bậc thợ, tổ sản xuất theo thâm niên×giới), gán nhóm lương cho NV demo,
    một ít lương ấn định + tạm ứng. Idempotent: bỏ qua nếu đã có quy tắc."""
    from datetime import date

    from .models.employee import Employee
    from .models.payroll import AMOUNT_MANUAL, BAND_LT1, BAND_Y1_5, BAND_Y5_10, BAND_GT10
    from .repositories.payroll_repo import PayrollRepository
    from .repositories.user_repo import UserRepository

    repo = PayrollRepository(db)
    if repo.list_rules():
        return  # đã seed
    if repo.get_params() is None:
        repo.create_params()

    # Quy tắc mức lương (số hóa bảng lương thật 2026).
    # Tổ In — theo BẬC THỢ.
    for key, amount in (("tho_1", 25_000_000), ("tho_2", 22_000_000), ("tho_3", 20_000_000),
                        ("phu_1", 14_500_000), ("phu_2", 10_500_000)):
        repo.create_rule(payroll_group="to_in", pay_grade_key=key, monthly_amount=amount,
                         effective_from=date(2026, 1, 1), note="Tổ In theo bậc thợ")
    # Tổ sản xuất (Dán/Bồi/Thành phẩm…) — theo THÂM NIÊN × GIỚI TÍNH.
    prod = [
        (BAND_LT1, "male", 8_000_000), (BAND_LT1, "female", 7_000_000),
        (BAND_Y1_5, "male", 8_500_000), (BAND_Y1_5, "female", 7_500_000),
        (BAND_Y5_10, "male", 10_000_000), (BAND_Y5_10, "female", 9_000_000),
        (BAND_GT10, "male", 10_000_000), (BAND_GT10, "female", 9_000_000),
    ]
    for band, gender, amount in prod:
        repo.create_rule(payroll_group="san_xuat", seniority_band=band, gender=gender,
                         monthly_amount=amount, effective_from=date(2026, 1, 1),
                         note="Tổ sản xuất theo thâm niên × giới tính")
    # Văn phòng — mức chung (theo vị trí, demo 1 mức nền).
    repo.create_rule(payroll_group="van_phong", monthly_amount=10_000_000,
                     effective_from=date(2026, 1, 1), note="Khối văn phòng (nền)")

    # Gán nhóm lương cho NV demo theo vị trí + tạo lương ấn định (rule).
    def _group_of(pos: str | None) -> tuple[str, str | None]:
        p = (pos or "").lower()
        if "in" in p and "kinh" not in p:  # thợ in / máy in (tránh "kinh doanh")
            grade = "phu_1" if ("phụ" in p or "phu" in p) else "tho_3"
            return "to_in", grade
        for kw in ("dán", "dan", "bồi", "boi", "bế", "be", "cắt", "cat", "cán", "can",
                   "thành phẩm", "thanh pham", "giao", "gia công", "gia cong"):
            if kw in p:
                return "san_xuat", None
        return "van_phong", None

    users = UserRepository(db)
    admin = users.get_by_username(settings.seed_admin_username)
    admin_emp_id = None
    if admin is not None:
        row = db.query(Employee).filter(Employee.user_id == admin.id).first()
        admin_emp_id = row.id if row is not None else None

    for emp in db.query(Employee).all():
        group, grade = _group_of(emp.position)
        emp.payroll_group = group
        emp.pay_grade_key = grade
        # Lương ấn định: GĐ (admin) nhập tay 40tr; còn lại theo quy tắc.
        if emp.id == admin_emp_id:
            repo.create_salary(employee_id=emp.id, effective_from=date(2026, 1, 1),
                               amount_mode=AMOUNT_MANUAL, base_amount=40_000_000,
                               allowance=500_000, note="Giám đốc — theo kết quả")
        else:
            repo.create_salary(employee_id=emp.id, effective_from=date(2026, 1, 1),
                               amount_mode="rule", allowance=300_000)
    db.commit()

    # Vài tạm ứng demo cho GĐ trong kỳ hiện tại.
    if admin_emp_id is not None:
        today = date.today()
        a1 = repo.create_advance(employee_id=admin_emp_id, period_year=today.year,
                                 period_month=today.month, advance_date=today,
                                 amount=2_000_000, reason="Ứng đợt 1")
        repo.update_advance(a1, status="approved")
        repo.create_advance(employee_id=admin_emp_id, period_year=today.year,
                            period_month=today.month, advance_date=today,
                            amount=1_500_000, reason="Ứng đợt 2 (chờ duyệt)")


def seed_piece_work(db: Session) -> None:
    """Seed đơn giá khoán demo (Lương khoán nhịp 2) — số hóa các bảng CÔNG KHOÁN thật.
    Idempotent: bỏ qua nếu đã có đơn giá. (Tiền khoán = Phiếu sản lượng theo người, không seed.)"""
    from .repositories.piece_work_repo import PieceWorkRepository

    repo = PieceWorkRepository(db)
    if repo.list_rates():
        return
    # (group, code, name, unit, price)
    rates = [
        ("to_boi", None, "Bồi carton 3 lớp E,B", "m2", 170),
        ("to_boi", None, "Bồi carton 5 lớp BE,BC", "m2", 200),
        ("to_boi", None, "Bồi tay", "m2", 250),
        ("to_can_phu", None, "Cán bóng / mờ / phủ UV", "m2", 150),
        ("to_can_phu", None, "Ghép màng matelize", "m2", 250),
        ("to_cat", None, "Cắt giấy cuộn", "tan", 100_000),
        ("to_cat", None, "Cắt tờ / cắt sóng", "tan", 120_000),
        ("to_cat", None, "Cắt demi", "luot", 40),
        ("to_cat", None, "Gỡ hàng hộp (carton 3 lớp)", "hop", 20),
        # ĐVT là CHỮ HIỂN THỊ (khớp `don_vi_do.ten`), không phải mã gạch dưới: gõ "bai_in" thì
        # module quy đổi không tra ra đơn vị nào → 3 dòng này mất khả năng đổi sang SL của bước.
        ("may_in_5mau", "A", "Bài in 1–2 màu", "bài in", 120_000),
        ("may_in_5mau", "B", "Bài in 3–4 màu", "bài in", 150_000),
        ("may_in_5mau", "C", "Bài in 4 màu có màu pha", "bài in", 175_000),
    ]
    for g, code, name, unit, price in rates:
        repo.create_rate(group_name=g, code=code, name=name, unit=unit, unit_price=price,
                         note="Đơn giá khoán demo")


# --- Sample phiếu tính giá (costing tickets) demo data ---------------------

# Mỗi phiếu: (ma, ten_san_pham, kho_thanh_pham, so_luong, ktv, [components]).
# Mỗi component (thành phần = 1 tờ giấy): (ten, giay_ma, so_con, so_mau_sel, quy_cach, [finishing]).
# Mỗi finishing: (ten, cong_doan_ma|None, don_gia_phang). don_gia_phang>0 → tính phẳng; else dùng
# cấu hình công đoạn (compute_step_cost).
PTG_SAMPLES: list[tuple] = [
    ("PTG-2026-0211", "HANGTAG LAVELLO BLACK", "5×10 cm", 5000, "Lê Văn C (KTV)", [
        ("Thẻ treo", "IVORY-350-79x109", 60, 4, "hai_mat",
         [("Cán màng bóng", "CD-0003", 0.0), ("Bế nổi", None, 300.0)]),
    ]),
    ("PTG-2026-0204", "Hộp giấy offset", "20×30×5 cm", 10000, "Phạm Văn D (KTV)", [
        ("Thân hộp", "IVORY-350-79x109", 2, 4, "mot_mat",
         [("Cán màng bóng", "CD-0003", 0.0), ("Bế", None, 250.0)]),
        ("Nắp hộp", "DUPLEX-300", 4, 2, "mot_mat", []),
    ]),
    ("PTG-2026-0206", "Tờ rơi A4", "21×29.7 cm", 30000, "Lê Văn C (KTV)", [
        ("Tờ rơi", "COUCHE-150-79x109", 4, 4, "hai_mat", []),
    ]),
    ("PTG-2026-0203", "Catalogue", "21×28 cm", 5000, "Phạm Văn D (KTV)", [
        ("Ruột", "COUCHE-150-79x109", 4, 4, "hai_mat", []),
        ("Bìa", "COUCHE-300-65x86", 2, 4, "hai_mat",
         [("Cán màng bóng", "CD-0003", 0.0)]),
    ]),
    ("PTG-2026-0202", "Danh thiếp cao cấp", "9×5.4 cm", 8000, "Lê Văn C (KTV)", [
        ("Danh thiếp", "COUCHE-300-65x86", 24, 4, "hai_mat",
         [("Ép kim", None, 500.0)]),
    ]),
]


def seed_phieu_tinh_gia(db: Session) -> None:
    """Seed ~5 phiếu tính giá mẫu THEO THÀNH PHẦN — CHỈ khi bảng rỗng (idempotent). Chạy sau
    seed_rebuild_catalog nên có sẵn Giấy + Công đoạn để tính giá thật (khớp engine, không bịa)."""
    from sqlalchemy import select
    from .models.cong_doan import CongDoan
    from .models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia
    from .models.vat_lieu_kho import GiayNguyen
    from .services.tinh_gia_service import compute_phieu_snapshot

    if db.execute(select(PhieuTinhGia)).first() is not None:
        return

    giay_by_ma = {g.ma: g for g in db.execute(select(GiayNguyen)).scalars()}
    cd_by_ma = {c.ma: c.id for c in db.execute(select(CongDoan)).scalars()}
    # Giấy dự phòng khi mã mẫu không có trong danh mục rebuild.
    fallback_giay = next(iter(giay_by_ma.values()), None)

    for ma, ten, kho, sl, ktv, comps in PTG_SAMPLES:
        p = PhieuTinhGia(ma=ma, ten_san_pham=ten, kho_thanh_pham=kho, so_luong=sl, ktv=ktv)
        for i, (c_ten, giay_ma, so_con, so_mau, quy_cach, finishing) in enumerate(comps):
            giay = giay_by_ma.get(giay_ma) or fallback_giay
            tp = PhieuThanhPhan(
                thu_tu=i, ten=c_ten, so_con=so_con, quy_cach_in=quy_cach,
                giay_id=(giay.id if giay else None),
                don_gia_giay=float(giay.don_gia) if (giay and giay.don_vi_gia == "to") else 2000,
                don_gia_don_vi="to", so_mau_a=so_mau, so_mau_b=(so_mau if quy_cach == "hai_mat" else 0),
                che_ban_don_gia=90000, don_gia_cong_in=120,
            )
            for j, (f_ten, f_cd_ma, f_don_gia) in enumerate(finishing):
                tp.thanh_phams.append(PhieuThanhPham(
                    thu_tu=j, ten=f_ten, cong_doan_id=cd_by_ma.get(f_cd_ma) if f_cd_ma else None,
                    don_gia=f_don_gia, so_mat=1, dien_tich=50,
                ))
            p.thanh_phans.append(tp)
        db.add(p)
        db.flush()
        compute_phieu_snapshot(db, p)
    db.commit()


# Ngày nghỉ lễ DƯƠNG cố định (điều 112 BLLĐ). CHỈ các ngày dương chắc chắn — Tết Nguyên đán
# (5 ngày) + Giỗ Tổ 10/3 ÂL + ngày kề Quốc khánh là ÂM/biến động theo thông báo Chính phủ hằng
# năm → admin tự khai qua UI (FE cảnh báo khi năm chưa đủ 11 ngày nghỉ-có-lương).
_SEED_HOLIDAYS_2026: list[tuple[date, str]] = [
    (date(2026, 1, 1), "Tết Dương lịch"),
    (date(2026, 4, 30), "Ngày Giải phóng miền Nam"),
    (date(2026, 5, 1), "Ngày Quốc tế Lao động"),
    (date(2026, 9, 2), "Quốc khánh"),
]
_SEED_HOLIDAY_NOTE = "Nghỉ lễ theo luật. Bổ sung Tết Nguyên đán + Giỗ Tổ + ngày kề Quốc khánh theo thông báo Chính phủ."


def seed_special_days(db: Session) -> None:
    """Seed ngày nghỉ lễ dương cố định. SEED-ONCE: nếu bảng đã có hàng thì bỏ qua, nên
    admin sửa/xóa (vd công ty xử lý 30/4 khác) KHÔNG bị mọc lại sau restart."""
    if CalendarRepository(db).count() > 0:
        return
    for d, name in _SEED_HOLIDAYS_2026:
        db.add(SpecialDay(day=d, kind=KIND_OFF, name=name, is_paid=True, note=_SEED_HOLIDAY_NOTE))
    db.commit()


# Biểu thuế TNCN lũy tiến từng phần 2026 — (seq, trần thu nhập tính thuế/tháng, thuế suất).
# 5 bậc theo Luật Thuế TNCN 109/2025/QH15 (áp cho kỳ tính thuế 2026). None = bậc cao nhất.
_PIT_BRACKETS_2026 = [
    (1, 10_000_000, 0.05),
    (2, 30_000_000, 0.10),
    (3, 60_000_000, 0.20),
    (4, 100_000_000, 0.30),
    (5, None, 0.35),
]


def seed_pit_brackets(db: Session) -> None:
    """Biểu thuế TNCN — SEED-ONCE (admin sửa/thêm bậc KHÔNG bị mọc lại sau restart)."""
    from sqlalchemy import func, select

    from .models.payroll import PitTaxBracket
    if db.execute(select(func.count(PitTaxBracket.id))).scalar_one() > 0:
        return
    for seq, up_to, rate in _PIT_BRACKETS_2026:
        db.add(PitTaxBracket(seq=seq, up_to=up_to, rate=rate))
    db.commit()


# Danh mục KHOẢN THU NHẬP mặc định (chủ 2026-07-27).
#
# ⚠️ KHÔNG seed những khoản ĐÃ CÓ CỘT RIÊNG và đã được engine TỰ TÍNH: tăng ca (`ot_pay` suy từ
# chấm công) · phụ cấp ca (`phu_cap_ca` → `night_pay`) · chuyên cần · lương khoán/sản lượng ·
# TIỀN NGÀY NGHỈ PHÉP (`luong_ngay_phep`, nằm trong `luong_cong`) · các khoản phạt.
# Seed trùng những khoản đó là TRẢ TIỀN HAI LẦN. Danh sách chặn ở `_RESERVED`
# (`payroll_component_service.py`) canh đúng ranh giới này.
#
# (code, tên, kind, is_taxable, sort_order) — `is_taxable=False` = MIỄN thuế TNCN.
# 4 khoản miễn lấy đúng theo sheet TÍNH THUẾ TNCN của kế toán (`lương thuế T 05.2026.xlsx`).
_PAYROLL_COMPONENTS_SEED = [
    ("trang_phuc",         "Trang phục",             "thu", False, 10),
    ("tro_cap_nha_o",      "Trợ cấp tiền nhà ở",     "thu", False, 20),
    ("ho_tro_di_lai",      "Hỗ trợ chi phí đi lại",  "thu", False, 30),
    ("tien_com",           "Tiền ăn ca / CN / giờ",  "thu", False, 40),
    ("phu_cap_dien_thoai", "Phụ cấp điện thoại",     "thu", True,  50),
    ("phu_cap_xang",       "Phụ cấp xăng xe",        "thu", True,  60),
    ("phu_cap_kiem_nhiem", "Phụ cấp kiêm nhiệm",     "thu", True,  70),
    # 4 khoản THƯỞNG chuyển từ ô tay sang danh mục (chủ 28/07/2026: "khoản 5s hay thưởng gì thì
    # cho nó select từ quy tắc, để coi nó chịu thuế hay không"). Cột cũ trên `payroll_lines` vẫn
    # còn để kỳ ĐÃ CHỐT giữ nguyên số, nhưng không ai ghi mới được nữa ⇒ KHÔNG trả hai lần.
    # `is_taxable=True` giữ ĐÚNG hành vi cũ (5 ô tay vốn bị đóng đinh chịu thuế); chủ tự bỏ tích
    # cho khoản nào thực chất là hoàn tiền (điển hình: Trả đồng phục).
    ("thuong_5s",          "Thưởng 5S",              "thu", True,  100),
    ("thuong_doanh_so",    "Thưởng doanh số",        "thu", True,  110),
    ("thuong_thanh_tich",  "Thưởng thành tích",      "thu", True,  120),
    ("tra_dong_phuc",      "Trả đồng phục",          "thu", True,  130),
    # Hai khoản MỞ (chủ 27/07/2026): khoản lặt vặt phát sinh một lần (thưởng nóng của Sếp) thì
    # dùng luôn hai khoản này + ghi chú, KHÔNG phải đẻ một danh mục mới dùng một lần rồi bỏ.
    ("thu_nhap_khac_ct",   "Thu nhập khác (chịu thuế)", "thu", True,  900),
    ("thu_nhap_khac_mt",   "Thu nhập khác (miễn thuế)", "thu", False, 910),
]


def seed_payroll_components(db: Session) -> None:
    """Danh mục khoản thu nhập — SEED-ONCE (chủ tự thêm/xoá/đổi cờ thì KHÔNG bị mọc lại sau restart)."""
    from sqlalchemy import func, select

    from .models.payroll import PayrollComponent
    if db.execute(select(func.count(PayrollComponent.id))).scalar_one() > 0:
        return
    for code, name, kind, taxable, order in _PAYROLL_COMPONENTS_SEED:
        db.add(PayrollComponent(code=code, name=name, kind=kind,
                                is_taxable=taxable, sort_order=order))
    db.commit()


def seed_job_grades(db: Session) -> None:
    """Danh mục BẬC TAY NGHỀ — SEED-ONCE (chủ sửa tên/tắt bậc thì KHÔNG bị mọc lại sau restart).

    Bộ chủ chốt 29/07/2026: 3 bậc chính + 2 bậc phụ, Bậc 1 là bậc CAO NHẤT. Không tiền, không
    hệ số — đúng "khai bậc thôi".

    ⚠️ Trùng ý với migration 0127 là CỐ Ý, và cần cả hai:
      - DB thật đang chạy: `schema_migrations` chưa có 0127 ⇒ migration seed + backfill bậc cũ.
      - DB dựng mới / test: test wipe bảng bằng `drop_all` nhưng `schema_migrations` KHÔNG phải
        bảng model nên sống sót ⇒ migration bị coi là "đã chạy" và bỏ qua. Không có seeder này
        thì danh mục rỗng, màn hồ sơ không có bậc nào để chọn.
    Cả hai đều guard "đã có dòng thì thôi" nên chạy chồng cũng không nhân đôi."""
    from sqlalchemy import func, select

    from .models.employee import JOB_GRADE_SEED, JobGrade
    if db.execute(select(func.count(JobGrade.id))).scalar_one() > 0:
        return
    for code, name, seq in JOB_GRADE_SEED:
        db.add(JobGrade(code=code, name=name, seq=seq))
    db.commit()


def seed_san_xuat_org(db: Session) -> None:
    """Nền phòng ban SẢN XUẤT: đánh dấu "Sản xuất" là khối sản
    xuất + dựng cây TỔ con (Chế bản/In/Cán/Bế/Đóng gói/KCS, cấp "Tổ"), gắn công đoạn → tổ, chuyển
    thợ demo từ HCNS về đúng tổ. Idempotent (bấm lại an toàn). Chạy trong SEED_DEMO (cần công đoạn
    + nhân sự demo). Thực tế: con người tự cấu hình tổ trong màn Phòng ban — đây chỉ là dữ liệu mẫu."""
    from sqlalchemy import select
    from .models.cong_doan import CongDoan
    from .models.department import Department
    from .models.employee import Employee
    from .models.unit_level import UnitLevel

    depts = DepartmentRepository(db)
    sx = depts.get_by_name("Sản xuất")
    if sx is None:
        return
    # 1) Đánh dấu khối "Sản xuất" → cả cây con lên phân hệ Sản xuất (effective theo tổ tiên).
    if not sx.la_san_xuat:
        depts.set_la_san_xuat(sx, True)

    # 2) Cấp "Tổ" (để chức danh đầu = Tổ trưởng).
    to_level = db.execute(select(UnitLevel).where(UnitLevel.name == "Tổ")).scalar_one_or_none()

    # 3) Dựng các TỔ con dưới "Sản xuất" (idempotent theo tên).
    to_names = ["Tổ Chế bản", "Tổ In offset", "Tổ Cán màng", "Tổ Bế & Xén", "Tổ Đóng gói", "Tổ KCS"]
    to_by_name: dict[str, Department] = {}
    for name in to_names:
        d = depts.get_by_name(name)
        if d is None:
            d = depts.create(name=name, parent_id=sx.id)
        if to_level is not None and d.level_id != to_level.id:
            depts.set_level(d, to_level.id)
        to_by_name[name] = d

    def _to_for_cd(cd: CongDoan) -> Department:
        nhom = (cd.nhom or "").lower()
        ten = f"{cd.ten or ''} {cd.ten_hien_thi or ''} {cd.ma or ''}".lower()
        if nhom == "prepress":
            return to_by_name["Tổ Chế bản"]
        if nhom == "print":
            return to_by_name["Tổ In offset"]
        if any(k in ten for k in ("cán", "màng", "uv", "nhũ", "phủ", "ép")):
            return to_by_name["Tổ Cán màng"]
        if any(k in ten for k in ("bế", "xén", "cắt", "cấn")):
            return to_by_name["Tổ Bế & Xén"]
        if any(k in ten for k in ("kcs", "kiểm", "nhập kho")):
            return to_by_name["Tổ KCS"]
        return to_by_name["Tổ Đóng gói"]  # gấp/dán/đóng cuốn/thành phẩm + mặc định finishing

    # 4) Gắn công đoạn → tổ (chỉ set khi chưa gắn hoặc đang trỏ chung phòng "Sản xuất").
    for cd in db.execute(select(CongDoan)).scalars():
        if cd.department_id in (None, sx.id):
            cd.department_id = _to_for_cd(cd).id

    # 5) Chuyển thợ demo từ HCNS về đúng tổ (theo chức danh). Chỉ đụng "thợ".
    pos_map = [("in offset", "Tổ In offset"), ("chế bản", "Tổ Chế bản"),
               ("xén", "Tổ Bế & Xén"), ("bế", "Tổ Bế & Xén"), ("cán", "Tổ Cán màng")]
    for emp in db.execute(select(Employee)).scalars():
        pos = (emp.position or "").lower()
        if "thợ" not in pos:
            continue
        for key, tname in pos_map:
            if key in pos:
                emp.department_id = to_by_name[tname].id
                break

    db.commit()


def seed_san_xuat_accounts(db: Session) -> None:
    """Tài khoản demo khối SẢN XUẤT (Lát 1) — để đăng nhập XEM LUỒNG phát→hộp tổ→gán→thợ.
    Mỗi tổ: 1 tổ trưởng (đặt `head_user_id` + vai Tổ trưởng SX = read+assign_work) + 2 thợ (vai
    Thợ SX = chỉ xem); thêm 1 Kế hoạch SX (phát, scope all) + 1 QC (xem mọi tổ). Mật khẩu chung
    `123456` (quy ước 1 hồ sơ = 1 tài khoản — Employee tự sinh qua `backfill_employee_profiles`,
    kế thừa `department_id` từ user → thợ HIỆN trong drawer gán). Idempotent theo username. SEED_DEMO."""
    from .repositories.rbac_repo import RoleRepository
    from .security import hash_password as _hash

    depts = DepartmentRepository(db)
    users = UserRepository(db)
    roles = RoleRepository(db)
    sx = depts.get_by_name("Sản xuất")
    if sx is None:
        return

    def _role_id(name: str) -> int | None:
        r = roles.get_by_name_and_department(name, sx.id)
        return r.id if r is not None else None

    r_ke_hoach = _role_id("Kế hoạch SX")
    r_to_truong = _role_id("Tổ trưởng SX")
    r_tho = _role_id("Thợ SX")
    r_qc = _role_id("QC")

    def _mk(username: str, name: str, dept_id: int | None, role_id: int | None, *, head_of=None):
        u = users.get_by_username(username)
        if u is None:
            u = users.create(username=username, name=name, password_hash=_hash("123456"))
        users.set_assignment(u, department_id=dept_id, role_id=role_id, is_active=True)
        if head_of is not None:
            depts.set_head(head_of, u.id)
        return u

    _mk("kehoach", "Kế hoạch sản xuất", sx.id, r_ke_hoach)
    _mk("qc1", "QC / KCS", sx.id, r_qc)

    slugs = {
        "Tổ Chế bản": "cheban", "Tổ In offset": "in", "Tổ Cán màng": "can",
        "Tổ Bế & Xén": "be", "Tổ Đóng gói": "donggoi", "Tổ KCS": "kcs",
    }
    for tname, slug in slugs.items():
        to = depts.get_by_name(tname)
        if to is None:
            continue
        _mk(f"tt_{slug}", f"Tổ trưởng {tname}", to.id, r_to_truong, head_of=to)
        for i in (1, 2):
            _mk(f"tho_{slug}{i}", f"Thợ {tname} {i}", to.id, r_tho)
    db.commit()


def seed_all(db: Session) -> None:
    """Full idempotent seed: RBAC catalog/roles, the admin user and its assignment.

    Sample Kinh doanh staff + customers (spec-06 demo data) are seeded ONLY when
    `SEED_DEMO=true` (dev / browser-validate) — off by default so the automated test
    suite keeps a minimal, predictable dataset (e.g. RBAC delete-guard tests that assume
    the Kinh doanh department has no users).
    """
    seed_modules(db)
    seed_departments(db)
    seed_unit_levels(db)
    seed_roles(db)
    seed_admin(db)
    link_admin(db)
    seed_product_types(db)
    seed_materials(db)
    seed_machines(db)
    seed_operations(db)
    seed_special_days(db)  # dữ liệu vận hành thật (không gated demo) — nền lịch/lễ dùng chung
    # Đơn vị đo & quy đổi: nền cho khoán · kho · mua hàng. KHÔNG gated demo — DB thật không bật
    # SEED_DEMO, mà thiếu bảng này thì mọi quy đổi trả "đơn vị chưa khai".
    from .seed_rebuild import seed_don_vi_do
    seed_don_vi_do(db)
    seed_payroll_components(db)  # danh mục khoản thu nhập + cờ chịu thuế TNCN
    seed_job_grades(db)  # danh mục bậc tay nghề (khối SX) — vận hành thật, không gated demo
    seed_pit_brackets(db)  # biểu thuế TNCN — dữ liệu vận hành thật (Lương đọc tính thuế)
    if settings.seed_demo:
        seed_kd_staff(db)
        seed_kho_staff(db)
        seed_employees(db)
        seed_work_shifts(db)
        seed_work_locations(db)
        seed_attendance(db)
        seed_leaves(db)
        seed_payroll(db)
        seed_piece_work(db)
        seed_customers(db)
        seed_products(db)
        seed_sales_history(db)
        seed_plate_die_rates(db)
        seed_norms(db)
        from .seed_rebuild import seed_rebuild_catalog
        seed_rebuild_catalog(db)
        seed_phieu_tinh_gia(db)
        seed_document_sequences(db)
        seed_san_xuat_org(db)  # nền tổ SX (§13.1): tag "Sản xuất" + cây tổ + gắn công đoạn/thợ
        seed_san_xuat_accounts(db)  # Lát 1: tài khoản tổ trưởng/thợ/kế hoạch/QC + head_user_id
        # Luồng THẬT đầu-cuối (tính giá → báo giá → đơn hàng bán → lệnh SX). CHẠY CUỐI: cần đủ
        # khách + sale + danh mục giấy/công đoạn + tổ SX + tài khoản kế hoạch ở trên.
        from .seed_luong_ban_sx import seed_luong_ban_sx
        seed_luong_ban_sx(db)
    backfill_user_codes(db)
    # Chạy NGOÀI khối demo: luật "mọi tài khoản phải có hồ sơ" áp cho mọi DB (dev/live),
    # và phải chạy SAU các seed tài khoản demo ở trên để dọn luôn đám vừa tạo.
    backfill_employee_profiles(db)
