"""Guard: mọi mã `audit_logs.action` mà code đang ghi phải được khai ở `app/audit_registry.py`.

Vì sao cần guard: nhãn tiếng Việt của nhật ký trước đây khai ở FRONTEND — 16 mã trong khi backend
ghi gần 300, nên 93% dòng hiện ra dưới dạng title-case tên cột giữa một giao diện tiếng Việt và
không lọc được theo nhóm. Chuyển nhãn về máy chủ chỉ đúng được nếu có người canh: thêm một action
mới mà quên khai thì test này đỏ ngay, thay vì hỏng im lặng trên màn Nhật ký.

Cách quét: đọc AST của `app/`, tìm lời gọi `*.create(...)` / `*.create_collapsing(...)` có tham số
`action=`, lấy giá trị hằng chuỗi. Hằng module-level (`ACTION_TAO = "dm_tao"`) được tra ngược.
Mã SINH ĐỘNG (f-string, biểu thức điều kiện) máy không đọc được — chúng khai tay ở `_MA_SINH_DONG`
kèm chỗ sinh, và test kiểm luôn rằng những chỗ sinh ấy còn tồn tại.
"""
from __future__ import annotations

import ast
import pathlib

from app import audit_registry as reg

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
GHI = {"create", "create_collapsing"}

# Mã không đến từ một hằng chuỗi. Mỗi dòng: (mã, file sinh ra nó, mảnh biểu thức phải còn trong file).
_MA_SINH_DONG: tuple[tuple[str, str, str], ...] = (
    *[(f"employee_{e}", "services/employee_service.py", 'f"employee_{event_type}"') for e in (
        "hired", "probation_ended", "confirmed", "transferred", "promoted", "leave_start",
        "leave_end", "suspended", "unsuspended", "resigned", "reinstated")],
    *[(f"leave_{s}", "services/leave_service.py", 'f"leave_{new_status}"') for s in (
        "approved", "rejected", "cancelled")],
    *[(f"overtime_{s}", "services/overtime_service.py", 'f"overtime_{new_status}"') for s in (
        "approved", "rejected", "cancelled")],
    *[(f"late_early_{s}", "services/late_early_service.py", 'f"late_early_{new_status}"') for s in (
        "approved", "rejected", "cancelled")],
    ("create_late_early_request", "services/late_early_service.py", '"create_late_early_request"'),
    ("create_late_early_request_approved", "services/late_early_service.py", '("_approved" if approved else "")' ),
    ("create_overtime_request", "services/overtime_service.py", '"create_overtime_request"'),
    ("create_overtime_request_approved", "services/overtime_service.py", '("_approved" if approved else "")' ),
    *[(f"quote_exception_{d}", "services/quotation_service.py", 'f"quote_exception_{decision}"')
      for d in ("approved", "rejected")],
    *[(f"transition_{s}", "services/quotation_service.py", 'f"transition_{to_status}"') for s in (
        "draft", "pending_approval", "approved", "sent", "accepted", "rejected", "expired",
        "converted_to_order", "cancelled")],
    ("lock_user", "services/user_admin_service.py", '"lock_user" if not is_active'),
    ("unlock_user", "services/user_admin_service.py", '"lock_user" if not is_active'),
    ("xep_lich_khoa", "services/xep_lich_service.py", '"xep_lich_khoa" if khoa'),
    ("xep_lich_mo_khoa", "services/xep_lich_service.py", '"xep_lich_khoa" if khoa'),
)


def _hang_chuoi_module(tree: ast.Module) -> dict[str, str]:
    ra: dict[str, str] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    ra[t.id] = n.value.value
    return ra


def _wrapper_chuyen_tiep(tree: ast.Module) -> dict[str, int]:
    """Hàm bọc chuyển thẳng tham số `action` của mình xuống `audit.create(...)` → tên hàm + vị trí
    của tham số đó (đã trừ `self`).

    Cần vì nhiều service không gọi `audit.create` trực tiếp mà qua một hàm bọc riêng
    (`ky_thuat_may_service._ghi`, `payroll_service._audit`, `san_xuat/thuc_thi._ghi`…). Bỏ qua lớp
    này thì guard mù đúng những họ mã đông nhất — và đó chính là lý do vòng đầu khai thiếu.
    """
    ra: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        ten_tham_so = [a.arg for a in node.args.args]
        if "action" not in ten_tham_so:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or getattr(sub.func, "attr", None) not in GHI:
                continue
            if any(kw.arg == "action" and isinstance(kw.value, ast.Name)
                   and kw.value.id == "action" for kw in sub.keywords):
                i = ten_tham_so.index("action")
                ra[node.name] = i - 1 if ten_tham_so[:1] == ["self"] else i
    return ra


def _gia_tri_ma(v: ast.AST, hang: dict[str, str]) -> str | None:
    if isinstance(v, ast.Constant) and isinstance(v.value, str):
        return v.value
    if isinstance(v, ast.Name):
        return hang.get(v.id)
    if isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name):
        return hang.get(v.attr)
    return None


def _quet() -> dict[str, str]:
    """mã action → "file:dòng" đầu tiên tìm thấy."""
    ra: dict[str, str] = {}
    for p in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        hang = _hang_chuoi_module(tree)
        boc = _wrapper_chuyen_tiep(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            ten = getattr(node.func, "attr", getattr(node.func, "id", None))
            val = None
            if ten in GHI:
                for kw in node.keywords:
                    if kw.arg == "action":
                        val = kw.value
            elif ten in boc:
                i = boc[ten]
                for kw in node.keywords:
                    if kw.arg == "action":
                        val = kw.value
                if val is None and len(node.args) > i:
                    val = node.args[i]
            if val is None:
                continue
            ma = _gia_tri_ma(val, hang)
            if ma:
                ra.setdefault(ma, f"{p.relative_to(APP)}:{node.lineno}")
    return ra


def test_moi_action_trong_code_deu_duoc_khai():
    thieu = {ma: cho for ma, cho in _quet().items() if ma not in reg.THEO_MA}
    assert not thieu, (
        "Mã action chưa khai trong app/audit_registry.py — màn Nhật ký sẽ hiện nhãn tự chế:\n"
        + "\n".join(f"  {ma}  ({cho})" for ma, cho in sorted(thieu.items()))
    )


def test_ma_sinh_dong_van_con_cho_sinh():
    for ma, tep, manh in _MA_SINH_DONG:
        assert ma in reg.THEO_MA, f"Mã sinh động {ma} chưa khai ở audit_registry"
        noi_dung = (APP / tep).read_text(encoding="utf-8")
        assert manh in noi_dung or manh.replace('"', "'") in noi_dung, (
            f"Chỗ sinh mã {ma} không còn trong {tep}: {manh}. "
            "Sửa lại _MA_SINH_DONG cho khớp, đừng xoá cho hết đỏ."
        )


def test_moi_dong_thuoc_mot_nhom_co_that():
    khoa_nhom = {k for k, _ in reg.NHOM}
    la = {h.ma: h.nhom for h in reg.HANH_DONG if h.nhom not in khoa_nhom}
    assert not la, f"Nhóm lạ: {la}"


def test_module_khai_la_khoa_quyen_that():
    from app.seed import ALL_MODULE_KEYS

    hop_le = set(ALL_MODULE_KEYS)
    la = {h.ma: h.module for h in reg.HANH_DONG if h.module and h.module not in hop_le}
    assert not la, (
        "Khoá quyền không có trong ma trận — khai sai là CHE NHẦM dòng nhật ký khỏi đúng người "
        f"cần đọc: {la}"
    )


def test_khong_trung_ma():
    mas = [h.ma for h in reg.HANH_DONG]
    assert len(mas) == len(set(mas)), "Mã action khai trùng"


def test_tra_ma_la_khong_no():
    hd = reg.tra("mot_ma_chua_tung_co")
    assert hd.nhom == reg.NHOM_KHAC and hd.module is None


def test_tra_danh_muc_lay_nhan_va_quyen_theo_target():
    hd = reg.tra("dm_sua", "giay:12")
    assert hd.nhan == "Sửa · Giấy"
    assert hd.module == "dm_giay"
    # Tên loại đời cũ còn nằm trong audit_logs vẫn phải tra ra.
    assert reg.tra("dm_tao", "machine:3").module == "dm_thiet_bi"
    # Không có target thì vẫn trả nhãn chung, không gác.
    assert reg.module_cua("dm_xoa") is None
