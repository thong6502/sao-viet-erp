"""Idempotent startup seed: RBAC catalog + the initial admin user.

Safe to call on every startup — every step creates rows only if absent, so re-runs
do not duplicate. Seeds only the Kinh doanh + Hành chính nhân sự scope for now; the
module catalog is data and grows as other departments come online (spec-02-rbac.md).
Credentials come from config/env (SEED_ADMIN_*).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
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
    ("don_hang_ban", "Đơn hàng bán"),
    ("bao_gia", "Báo giá in ấn"),
    ("tinh_gia_thanh", "Tính giá thành"),
    ("san_pham", "Sản phẩm"),
    ("hop_dong", "Hợp đồng"),
    ("phong_ban", "Phòng ban"),
    ("vai_tro", "Vai trò"),
    ("nguoi_dung", "Người dùng"),
    ("activity_log", "Nhật ký hoạt động"),
]

ALL_MODULE_KEYS = [k for k, _ in MODULES]
KD_MODULE_KEYS = [
    "dashboard",
    "khach_hang",
    "don_hang_ban",
    "bao_gia",
    "tinh_gia_thanh",
    "san_pham",
    "hop_dong",
]

DEPARTMENTS = ["Ban giám đốc", "Hành chính nhân sự", "Kinh doanh"]

# Default org tiers (spec-06 / PBI-4009): (name, rank cao→thấp, head_title). Data, not schema —
# admins add/edit more via the catalog screen.
UNIT_LEVELS: list[tuple[str, int, str]] = [
    ("Khối", 1, "Trưởng khối"),
    ("Phòng", 2, "Trưởng phòng"),
    ("Tổ", 3, "Tổ trưởng"),
]

ADMIN_DEPARTMENT = "Ban giám đốc"
ADMIN_ROLE = "Giám đốc"


def _full(scope: str) -> dict:
    return dict(can_read=True, can_create=True, can_update=True, can_delete=True, scope=scope)


def _rcu(scope: str) -> dict:
    return dict(can_read=True, can_create=True, can_update=True, can_delete=False, scope=scope)


def _read(scope: str) -> dict:
    return dict(
        can_read=True, can_create=False, can_update=False, can_delete=False, scope=scope
    )


# Roles: (department_name, role_name, {module_key: permission}). The minimal default
# role ("Nhân viên") is Read-only on Dashboard, scope own.
ROLES: list[tuple[str, str, dict[str, dict]]] = [
    (ADMIN_DEPARTMENT, ADMIN_ROLE, {k: _full(SCOPE_ALL) for k in ALL_MODULE_KEYS}),
    (
        "Hành chính nhân sự",
        "Trưởng phòng HCNS",
        {
            "dashboard": _read(SCOPE_ALL),
            "nguoi_dung": _rcu(SCOPE_ALL),
            "phong_ban": _read(SCOPE_ALL),
            "vai_tro": _read(SCOPE_ALL),
            "activity_log": _read(SCOPE_ALL),
        },
    ),
    ("Hành chính nhân sự", "Nhân viên", {"dashboard": _read(SCOPE_OWN)}),
    ("Kinh doanh", "Trưởng phòng KD", {k: _full(SCOPE_DEPARTMENT) for k in KD_MODULE_KEYS}),
    (
        "Kinh doanh",
        "NV Sales",
        {
            "dashboard": _read(SCOPE_OWN),
            "khach_hang": _rcu(SCOPE_OWN),
            "don_hang_ban": _rcu(SCOPE_OWN),
            "bao_gia": _rcu(SCOPE_OWN),
        },
    ),
]


# --- Seed steps (each idempotent) ------------------------------------------


def seed_modules(db: Session) -> None:
    modules = ModuleRepository(db)
    for key, label in MODULES:
        if modules.get_by_key(key) is None:
            modules.create(key=key, label=label)


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
        STATUS_ON_HOLD,
        STATUS_ORDERED,
        Order,
        OrderLine,
    )
    from .models.quotation import (
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_SENT,
        Quotation,
    )
    from .repositories.order_repo import OrderRepository
    from .repositories.quotation_repo import QuotationRepository

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

    def _mk_order(customer, sale_id, months_ago, lines, status=STATUS_ORDERED, day=15):
        created = _month_mid(months_ago, day)
        o = Order(
            order_no=OrderRepository(db)._next_order_no(),
            customer_id=customer.id,
            order_type="theo_yc",
            order_kind="moi",
            sale_user_id=sale_id,
            status=status,
            has_customer_paper=False,
            vat_pct_estimate=8,
            created_at=created,
        )
        for desc, qty, unit in lines:
            o.lines.append(
                OrderLine(
                    description=desc,
                    qty=qty,
                    unit_price_snapshot=unit,  # P0 snapshot: đơn kế thừa giá đã chốt
                    line_total=qty * unit,
                    vat_pct_estimate=8,
                )
            )
        db.add(o)
        db.flush()  # so the next _next_order_no() sees this row (unique DH###)

    def _mk_quote(customer, sale_id, months_ago, total, status=STATUS_SENT, day=10):
        created = _month_mid(months_ago, day)
        valid = date(created.year + (1 if created.month == 12 else 0),
                     1 if created.month == 12 else created.month + 1,
                     min(created.day, 28))
        q = Quotation(
            code=QuotationRepository(db)._next_code(),
            version=1,
            customer_id=customer.id,
            cost_von_total=int(total * 0.8),
            margin=int(total * 0.2),
            discount=0,
            total=total,
            valid_until=valid,
            sale_user_id=sale_id,
            status=status,
            row_version=1,
            created_at=created,
        )
        db.add(q)
        db.flush()  # so the next _next_code() sees this row (unique BG###)

    sale1 = users.get_by_username("sale1")
    sale2 = users.get_by_username("sale2")

    # --- KH: Công ty TNHH An Phát (sale1) — khách thân thiết, mua đều 12 tháng ------
    # Sản phẩm in thật: catalogue / tờ rơi / name card / lịch. Spread mọi tháng để bar
    # chart 12T KHÔNG có lỗ, donut đủ 4 nhóm SP, heatmap rải nhiều thứ trong tuần.
    if an_phat is not None and sale1 is not None:
        _mk_order(an_phat, sale1.id, 11, [("Catalogue A4 32 trang", 2000, 15_000)], day=8)
        _mk_order(an_phat, sale1.id, 10, [("Tờ rơi A5 4 màu", 10000, 1_200)], day=22)
        _mk_order(an_phat, sale1.id, 9, [("Name card 4 màu", 5000, 900),
                                         ("Tờ rơi A5 4 màu", 8000, 1_200)], day=5)
        _mk_order(an_phat, sale1.id, 7, [("Catalogue A4 32 trang", 1500, 15_000)], day=17)
        _mk_order(an_phat, sale1.id, 6, [("Name card 4 màu", 3000, 900)],
                  status=STATUS_ON_HOLD, day=12)
        _mk_order(an_phat, sale1.id, 4, [("Lịch tết 2026 (bộ 7 tờ)", 500, 45_000)], day=26)
        _mk_order(an_phat, sale1.id, 3, [("Tờ rơi A5 4 màu", 12000, 1_200),
                                         ("Name card 4 màu", 2000, 900)], day=9)
        _mk_order(an_phat, sale1.id, 1, [("Catalogue A4 32 trang", 1000, 15_000)], day=20)
        _mk_order(an_phat, sale1.id, 0, [("Name card 4 màu", 4000, 900)], day=3)
        # Báo giá: đủ trạng thái (duyệt / gửi / từ chối) cho lịch sử báo giá + win-rate.
        _mk_quote(an_phat, sale1.id, 11, 30_000_000, status=STATUS_APPROVED)
        _mk_quote(an_phat, sale1.id, 7, 22_500_000, status=STATUS_APPROVED)
        _mk_quote(an_phat, sale1.id, 4, 18_000_000, status=STATUS_REJECTED)
        _mk_quote(an_phat, sale1.id, 1, 15_000_000, status=STATUS_APPROVED)
        _mk_quote(an_phat, sale1.id, 0, 3_600_000, status=STATUS_SENT)

    # --- KH: Công ty CP Bao Bì Việt (sale2) — bao bì, đơn to thưa, có đơn hủy/nháp ---
    if bao_bi is not None and sale2 is not None:
        _mk_order(bao_bi, sale2.id, 10, [("Hộp giấy cao cấp", 5000, 6_000)], day=14)
        _mk_order(bao_bi, sale2.id, 8, [("Túi giấy in offset", 20000, 3_500)], day=19)
        _mk_order(bao_bi, sale2.id, 6, [("Tem nhãn decal", 50000, 500)],
                  status=STATUS_CANCELLED, day=11)  # đã hủy → loại khỏi doanh số
        _mk_order(bao_bi, sale2.id, 5, [("Hộp giấy cao cấp", 8000, 6_000)], day=24)
        _mk_order(bao_bi, sale2.id, 2, [("Túi giấy in offset", 15000, 3_500)], day=7)
        _mk_order(bao_bi, sale2.id, 1, [("Hộp giấy cao cấp", 3000, 6_000)],
                  status=STATUS_DRAFT, day=16)  # đang lập
        _mk_quote(bao_bi, sale2.id, 10, 30_000_000, status=STATUS_APPROVED)
        _mk_quote(bao_bi, sale2.id, 5, 48_000_000, status=STATUS_APPROVED)
        _mk_quote(bao_bi, sale2.id, 2, 52_500_000, status=STATUS_SENT)

    # --- KH: Nhà in Minh Khai (sale1) — khách vừa, vài đơn để không trống ------------
    if minh_khai is not None and sale1 is not None:
        _mk_order(minh_khai, sale1.id, 9, [("Tờ rơi A5 4 màu", 5000, 1_200)], day=13)
        _mk_order(minh_khai, sale1.id, 5, [("Name card 4 màu", 2000, 900)], day=21)
        _mk_order(minh_khai, sale1.id, 2, [("Catalogue A4 32 trang", 800, 15_000)], day=6)
        _mk_quote(minh_khai, sale1.id, 5, 6_000_000, status=STATUS_APPROVED)
        _mk_quote(minh_khai, sale1.id, 2, 12_000_000, status=STATUS_SENT)

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
    if settings.seed_demo:
        seed_kd_staff(db)
        seed_customers(db)
        seed_products(db)
        seed_sales_history(db)
