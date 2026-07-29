"""Danh mục khoản thu nhập / khấu trừ (module `luong`) — nghiệp vụ.

Chủ chốt 27/07/2026: *"có danh mục list các mục đóng thuế; tích vào thì cái đó chịu thuế, không
tích thì thôi; và họ có thể thêm hoặc xoá"*.

Ba luật đáng nhớ:
1. **Quy trình 2 bước**: muốn có khoản mới thì tạo ở DANH MỤC trước, rồi mới chọn gán cho người.
   Không có đường nào tạo khoản mới từ màn hồ sơ nhân sự.
2. **Xoá**: khoản chưa có số liệu ⇒ xoá hẳn. Đã gán cho NV hoặc đã vào kỳ lương ⇒ CHỈ ngưng dùng
   (`is_active = False`), giữ dữ liệu cũ nguyên vẹn.
3. **Ngừng áp dụng KHÔNG cắt lương**: NV còn được gán khoản đã tắt thì VẪN TRẢ, chỉ cảnh báo để
   HCNS chủ động gỡ (chốt của chủ 27/07) — không tự ý cắt tiền của ai.
"""
from __future__ import annotations

import re
import unicodedata

from ..models.employee import STATUS_ACTIVE, STATUS_PROBATION
from ..models.payroll import COMPONENT_KINDS, COMPONENT_KIND_THU, PayrollComponent
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.payroll_component_repo import PayrollComponentRepository


# Những khoản ENGINE ĐÃ TỰ TÍNH và đã có ô khai riêng. Tạo thêm khoản danh mục trùng ý nghĩa là
# TRẢ TIỀN HAI LẦN mà không ai thấy — nên chặn ngay lúc gõ tên. Khoá là SLUG nên "Chuyên cần",
# "chuyen can", "CHUYÊN CẦN" đều bị bắt. Giá trị = nơi khoản đó đã tồn tại (để báo cho đúng chỗ).
_RESERVED: dict[str, str] = {
    "chuyen_can": "ô \"Thưởng chuyên cần\" trong hồ sơ lương",
    "phu_cap_ca": "ô \"Phụ cấp ca\" trong hồ sơ lương",
    "phu_cap_ca_dem": "ô \"Phụ cấp ca\" trong hồ sơ lương",
    "ca_dem": "ô \"Phụ cấp ca\" trong hồ sơ lương",
    "phu_cap_tham_nien": "ô \"Phụ cấp thâm niên\" trong hồ sơ lương",
    "luong_vi_tri": "ô \"Lương cơ bản (đóng BH)\" trong hồ sơ lương",
    "luong_trach_nhiem": "ô \"Lương trách nhiệm\" trong hồ sơ lương",
    "tang_ca": "tiền tăng ca — engine tự tính từ chấm công",
    "them_gio": "tiền tăng ca — engine tự tính từ chấm công",
    "lam_them": "tiền tăng ca — engine tự tính từ chấm công",
    "luong_khoan": "tiền khoán — engine tự tính theo sản lượng",
    "luong_san_luong": "tiền khoán — engine tự tính theo sản lượng",
    "san_luong": "tiền khoán — engine tự tính theo sản lượng",
    # ❗ Thưởng 5S / doanh số / thành tích / trả đồng phục CỐ Ý KHÔNG còn ở đây (28/07/2026):
    # ô tay của chúng đã bị gỡ khỏi màn Sửa lương, nay khai bằng chính danh mục này để cờ
    # "Chịu thuế" khai được (trước bị đóng đinh chịu thuế). Thêm lại là chặn nhầm chính đường
    # duy nhất còn khai được.
    "phep_nam": "tiền ngày nghỉ phép — engine tự tính từ chấm công",
    "tien_phep": "tiền ngày nghỉ phép — engine tự tính từ chấm công",
    "luong_ngay_phep": "tiền ngày nghỉ phép — engine tự tính từ chấm công",
    "di_tre": "cột \"Đi trễ/về sớm\" trên bảng lương (tự tính từ chấm công)",
    "ve_som": "cột \"Đi trễ/về sớm\" trên bảng lương (tự tính từ chấm công)",
    "phat_bien_ban": "cột \"Phạt biên bản vi phạm\" trên bảng lương",
    "dt_vuot_troi": "cột \"Điện thoại vượt trội\" trên bảng lương",
    "phat_5s": "cột \"Tiền đồng phục / phạt 5S\" trên bảng lương",
    "tam_ung": "phiếu tạm ứng (màn Lương → Tạm ứng)",
    "luong_dot_1": "phiếu thanh toán lương đợt 1",
}


class ComponentError(Exception):
    """Base cho lỗi miền danh mục khoản thu nhập."""


class ComponentValidationError(ComponentError):
    """Sai dữ liệu hoặc vi phạm luật nghiệp vụ."""


class ComponentNotFound(ComponentError):
    """Không tìm thấy khoản."""


def _slug(name: str) -> str:
    """Tên tiếng Việt → mã ASCII an toàn (chủ chỉ gõ tên, hệ thống tự sinh mã).

    Tách dấu bằng NFD rồi bỏ ký tự tổ hợp — đếm tay bảng chữ có dấu là sai sót."""
    s = unicodedata.normalize("NFD", (name or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("đ", "d")          # NFD không tách được đ/Đ
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "khoan"


def _guard_reserved(name: str) -> None:
    """Chặn tạo khoản trùng ý nghĩa với thứ engine đã tự tính.

    Không chặn thì HCNS gõ lại "Chuyên cần" là NV nhận hai lần tiền chuyên cần, mà phiếu lương
    trông vẫn bình thường vì hai dòng nằm ở hai chỗ khác nhau."""
    where = _RESERVED.get(_slug(name))
    if where:
        raise ComponentValidationError(
            f"Hệ thống đã có khoản này ở {where} và đã tự tính. Thêm vào danh mục nữa là trả "
            f"tiền HAI LẦN. Nếu đây là khoản khác thật thì đặt tên khác cho phân biệt."
        )


class PayrollComponentService:
    def __init__(self, components: PayrollComponentRepository,
                 audit: AuditLogRepository, employees=None) -> None:
        self.components = components
        self.audit = audit
        # Chỉ cần cho `bulk_assign` (lọc NV theo scope). Optional để test unit dựng service gọn.
        self.employees = employees

    # --- danh mục -----------------------------------------------------------

    def list_components(self, *, active_only: bool = False) -> list[PayrollComponent]:
        return self.components.list_components(active_only=active_only)

    def _unique_code(self, name: str) -> str:
        base = _slug(name)
        code, n = base, 2
        while self.components.get_by_code(code) is not None:
            suffix = f"_{n}"
            code = base[: 40 - len(suffix)] + suffix
            n += 1
        return code

    def create_component(self, *, actor, name: str, kind: str = COMPONENT_KIND_THU,
                         is_taxable: bool = True, in_insurance_base: bool = False,
                         sort_order: int = 0, note: str | None = None) -> PayrollComponent:
        name = (name or "").strip()
        if not name:
            raise ComponentValidationError("Phải nhập tên khoản.")
        if kind not in COMPONENT_KINDS:
            raise ComponentValidationError("Loại khoản phải là Thu hoặc Trừ.")
        _guard_reserved(name)
        c = self.components.create_component(
            code=self._unique_code(name), name=name, kind=kind, is_taxable=bool(is_taxable),
            in_insurance_base=bool(in_insurance_base), sort_order=int(sort_order or 0),
            note=(note or None),
        )
        self.audit.create(actor_user_id=actor.id, action="create_payroll_component",
                          target=f"payroll_component:{c.id}",
                          detail=f"{c.name} ({c.kind}) chịu thuế={c.is_taxable}")
        return c

    def update_component(self, *, actor, component_id: int, **fields) -> PayrollComponent:
        c = self.components.get_component(component_id)
        if c is None:
            raise ComponentNotFound("Không tìm thấy khoản thu nhập.")
        data = {k: v for k, v in fields.items() if v is not None}
        if "name" in data:
            data["name"] = str(data["name"]).strip()
            if not data["name"]:
                raise ComponentValidationError("Phải nhập tên khoản.")
            if _slug(data["name"]) != _slug(c.name):
                _guard_reserved(data["name"])
        if "kind" in data and data["kind"] not in COMPONENT_KINDS:
            raise ComponentValidationError("Loại khoản phải là Thu hoặc Trừ.")
        before = c.is_taxable
        c = self.components.update_component(c, **data)
        if "is_taxable" in data and bool(before) != bool(c.is_taxable):
            # Đổi cờ chịu thuế là đổi TIỀN THUẾ — ghi audit riêng để còn truy được về sau.
            self.audit.create(
                actor_user_id=actor.id, action="payroll_component_taxable_changed",
                target=f"payroll_component:{c.id}",
                detail=f"{c.name}: chịu thuế {before} → {c.is_taxable} (áp từ kỳ tính tiếp theo)")
        return c

    def delete_component(self, *, actor, component_id: int) -> dict:
        """Chưa có số liệu ⇒ xoá hẳn. Đã dùng ⇒ CHỈ ngừng áp dụng, giữ nguyên dữ liệu cũ.

        Trả `{deleted, deactivated, employee_count, period_count, message}` — màn hình phải nói
        ĐÚNG việc vừa xảy ra, không được báo "đã xoá" khi thực ra chỉ tắt đi."""
        c = self.components.get_component(component_id)
        if c is None:
            raise ComponentNotFound("Không tìm thấy khoản thu nhập.")
        emp_n = self.components.employee_count(component_id)
        period_n = self.components.period_count(component_id)
        if emp_n or period_n:
            if not c.is_active:
                raise ComponentValidationError("Khoản này đã ngừng áp dụng rồi.")
            self.components.update_component(c, is_active=False)
            self.audit.create(actor_user_id=actor.id, action="deactivate_payroll_component",
                              target=f"payroll_component:{c.id}",
                              detail=f"{c.name} — {emp_n} NV, {period_n} kỳ lương")
            return {
                "deleted": False, "deactivated": True,
                "employee_count": emp_n, "period_count": period_n,
                "message": (
                    f"Khoản thu nhập này đã có phát sinh dữ liệu (gán cho {emp_n} nhân viên, "
                    f"đã chốt {period_n} kỳ lương) nên KHÔNG THỂ XOÁ vĩnh viễn. Hệ thống đã "
                    f"chuyển sang trạng thái NGỪNG SỬ DỤNG. Dữ liệu cũ vẫn được bảo lưu."
                ),
            }
        name = c.name
        self.components.delete_component(c)
        self.audit.create(actor_user_id=actor.id, action="delete_payroll_component",
                          target=f"payroll_component:{component_id}", detail=name)
        return {"deleted": True, "deactivated": False, "employee_count": 0,
                "period_count": 0, "message": "Đã xoá khoản thu nhập."}

    def employees_holding_inactive(self, component_id: int) -> list[int]:
        """NV còn được gán một khoản ĐÃ NGỪNG ÁP DỤNG — nuôi cảnh báo đỏ ở màn danh mục."""
        c = self.components.get_component(component_id)
        if c is None or c.is_active:
            return []
        return self.components.employees_holding(component_id)

    # --- Tầng 2: gán khoản cho NGƯỜI ----------------------------------------

    def set_employee_values(self, *, actor, employee_id: int, items: list[dict]) -> int:
        """Gán/sửa/gỡ khoản cho một người. `amount = None` ⇒ GỠ khỏi người đó.

        ⚠️ CHỈ nhận `component_id` có sẵn trong danh mục — đây là chốt của "quy trình 2 bước":
        không có đường nào đẻ ra khoản mới từ màn hồ sơ nhân sự. Cờ `is_taxable` KHÔNG nhận ở đây
        (kể cả gửi lên cũng bỏ qua) — quy tắc chỉ sống ở Tầng 1."""
        n = 0
        for it in items or []:
            cid = int(it["component_id"])
            c = self.components.get_component(cid)
            if c is None:
                raise ComponentValidationError(
                    f"Khoản #{cid} không có trong danh mục. Tạo ở Cấu hình lương → "
                    f"Danh mục khoản thu nhập trước, rồi mới gán cho nhân viên."
                )
            amount = it.get("amount")
            if amount is None:
                self.components.clear_employee_value(employee_id=employee_id, component_id=cid)
            else:
                if float(amount) < 0:
                    raise ComponentValidationError(f"Số tiền của \"{c.name}\" không được âm.")
                # Khoản đã NGỪNG ÁP DỤNG: không cho gán MỚI, nhưng vẫn cho sửa/gỡ khoản đang có
                # (để HCNS đưa về 0 hoặc gỡ hẳn theo cảnh báo).
                existing = {r.component_id for r in self.components.employee_rows(employee_id)}
                if not c.is_active and cid not in existing:
                    raise ComponentValidationError(
                        f"\"{c.name}\" đã ngừng áp dụng, không gán mới được."
                    )
                self.components.set_employee_value(
                    employee_id=employee_id, component_id=cid,
                    amount=float(amount), note=(it.get("note") or None))
            n += 1
        self.components.commit()
        self.audit.create(actor_user_id=actor.id, action="set_employee_components",
                          target=f"employee:{employee_id}", detail=f"{n} khoản")
        return n

    def bulk_assign(self, *, actor, component_id: int, amount: float, note: str | None = None,
                    employee_ids: list[int] | None = None, all_active: bool = False,
                    overwrite: bool = False, scope: str | None = None) -> dict:
        """Rải MỘT khoản cho NHIỀU người trong một thao tác (chủ 28/07/2026).

        Trước đây tạo một phụ cấp mới rồi phải mở hồ sơ từng người để thêm — nhà máy ~40–100
        người thì không dùng được.

        ⚠️ `overwrite=False` là MẶC ĐỊNH VÀ PHẢI GIỮ NGUYÊN: bật lên là xoá mức riêng đã khai cho
        từng người, mà `employee_salary_components` cố ý không version theo ngày hiệu lực nên
        KHÔNG có đường hoàn tác. Backend không được tự suy ra `True` khi client quên gửi cờ.

        Trả `assigned` (thêm mới) và `overwritten` (đè) TÁCH RIÊNG — gộp một số là người bấm
        không thấy mình vừa đè mức riêng của ai."""
        c = self.components.get_component(component_id)
        if c is None:
            raise ComponentValidationError(
                f"Khoản #{component_id} không có trong danh mục. Tạo ở Cấu hình lương → "
                f"Danh mục khoản thu nhập trước, rồi mới gán cho nhân viên."
            )
        if not c.is_active:
            raise ComponentValidationError(
                f"\"{c.name}\" đã ngừng áp dụng, không gán mới được."
            )
        if amount is None or float(amount) < 0:
            raise ComponentValidationError(f"Số tiền của \"{c.name}\" không được âm.")
        if not all_active and not employee_ids:
            raise ComponentValidationError("Chưa chọn nhân viên nào để gán.")
        if self.employees is None:
            raise ComponentValidationError("Chưa cấu hình được danh sách nhân viên.")

        # Tập trong PHẠM VI của người bấm — tổ trưởng không gán được ra ngoài tổ. Dùng lại đúng
        # hàm engine lương đang dùng để hai bên không lệch nhau.
        in_scope = {e.id: e for e in self.employees.list_scoped_all(scope=scope, actor=actor)}
        if all_active:
            # "Tất cả" = ĐANG LÀM VIỆC (chính thức + thử việc). Người đã nghỉ việc bị loại —
            # rải phụ cấp cho người đã nghỉ là đẻ tiền cho hồ sơ chết.
            targets = [e for e in in_scope.values()
                       if e.status in (STATUS_ACTIVE, STATUS_PROBATION)]
            skipped_out_of_scope = 0
        else:
            targets = [in_scope[i] for i in employee_ids if i in in_scope]
            skipped_out_of_scope = len([i for i in employee_ids if i not in in_scope])

        holders = {r.employee_id for r in self.components.rows_of_component(component_id)}
        assigned = overwritten = skipped_existing = 0
        for emp in targets:
            if emp.id in holders:
                if not overwrite:
                    skipped_existing += 1
                    continue
                overwritten += 1
            else:
                assigned += 1
            self.components.set_employee_value(
                employee_id=emp.id, component_id=component_id,
                amount=float(amount), note=(note or None))
        self.components.commit()
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="bulk_assign_component",
            target=f"payroll_component:{component_id}",
            detail=(f"{c.name}: thêm mới {assigned} NV"
                    + (f", GHI ĐÈ {overwritten} NV" if overwritten else "")
                    + (f", bỏ qua {skipped_existing} NV đã có" if skipped_existing else "")),
        )
        return {"assigned": assigned, "overwritten": overwritten,
                "skipped_existing": skipped_existing,
                "skipped_out_of_scope": skipped_out_of_scope,
                "total": len(targets)}

    def resolve_for(self, *, employee_id: int) -> list[dict]:
        """Khoản CỐ ĐỊNH HÀNG THÁNG của một người (Tầng 2), kèm quy tắc kế thừa từ danh mục.

        Dùng chung cho cả engine tính lương lẫn màn hồ sơ ⇒ số trên màn và số ra tiền không lệch.

        KHÔNG lọc `is_active`: khoản đã NGỪNG ÁP DỤNG mà NV còn giữ thì VẪN TRẢ (chốt của chủ);
        cờ `is_active` trả kèm để màn hình bật cảnh báo đỏ."""
        by_id = {c.id: c for c in self.components.list_components()}
        out: list[dict] = []
        for row in self.components.employee_rows(employee_id):
            c = by_id.get(row.component_id)
            if c is None or not row.amount:
                continue
            out.append({
                "component_id": c.id, "code": c.code, "name": c.name, "kind": c.kind,
                "is_taxable": bool(c.is_taxable), "amount": float(row.amount),
                "note": row.note, "is_active": bool(c.is_active),
            })
        out.sort(key=lambda r: by_id[r["component_id"]].sort_order)
        return out
