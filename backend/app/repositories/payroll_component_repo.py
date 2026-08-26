"""Danh mục khoản thu nhập / khấu trừ (module `luong`) — data access.

BA TẦNG, mỗi tầng một vai:
  - `payroll_components`         — Tầng 1, DANH MỤC: khoản là gì, có chịu thuế TNCN không.
  - `employee_salary_components` — Tầng 2, số tiền CỐ ĐỊNH hàng tháng của một người.
  - `payroll_line_components`    — Tầng 3, SNAPSHOT lên từng dòng lương + khoản phát sinh 1 lần.

Không có luật nghiệp vụ ở đây (nằm ở `PayrollComponentService`).
"""
from __future__ import annotations

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from ..models.payroll import (
    COMPONENT_SOURCE_AUTO,
    COMPONENT_SOURCE_EMPLOYEE,
    COMPONENT_SOURCE_LINE,
    EmployeeSalaryComponent,
    PayrollComponent,
    PayrollLine,
    PayrollLineComponent,
)


class PayrollComponentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Tầng 1: danh mục ---------------------------------------------------

    def list_components(self, *, active_only: bool = False) -> list[PayrollComponent]:
        stmt = select(PayrollComponent)
        if active_only:
            stmt = stmt.where(PayrollComponent.is_active.is_(True))
        return list(self.db.execute(
            stmt.order_by(PayrollComponent.sort_order, PayrollComponent.id)
        ).scalars())

    def get_component(self, component_id: int) -> PayrollComponent | None:
        return self.db.get(PayrollComponent, component_id)

    def get_by_code(self, code: str) -> PayrollComponent | None:
        return self.db.execute(
            select(PayrollComponent).where(PayrollComponent.code == code)
        ).scalars().first()

    def create_component(self, **fields) -> PayrollComponent:
        c = PayrollComponent(**fields)
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return c

    def update_component(self, c: PayrollComponent, **fields) -> PayrollComponent:
        for k, v in fields.items():
            setattr(c, k, v)
        self.db.commit()
        self.db.refresh(c)
        return c

    def delete_component(self, c: PayrollComponent) -> None:
        self.db.delete(c)
        self.db.commit()

    def employee_count(self, component_id: int) -> int:
        """Số NHÂN VIÊN đang được gán khoản này — để nói "đã gán cho N nhân viên"."""
        return self.db.execute(
            select(func.count(distinct(EmployeeSalaryComponent.employee_id)))
            .where(EmployeeSalaryComponent.component_id == component_id)
        ).scalar_one()

    def period_count(self, component_id: int) -> int:
        """Số KỲ LƯƠNG đã có khoản này — để nói "đã chốt M kỳ lương".

        Đếm kỳ chứ không đếm dòng: 100 dòng của cùng một tháng vẫn là MỘT kỳ, nói "100" làm HR
        tưởng ảnh hưởng rộng gấp trăm lần thực tế."""
        return self.db.execute(
            select(func.count(distinct(PayrollLine.period_id)))
            .select_from(PayrollLineComponent)
            .join(PayrollLine, PayrollLine.id == PayrollLineComponent.line_id)
            .where(PayrollLineComponent.component_id == component_id)
        ).scalar_one()

    def rows_of_component(self, component_id: int) -> list[EmployeeSalaryComponent]:
        """Mọi dòng gán của MỘT khoản (kèm số tiền) — cho gán hàng loạt biết ai đã có và mức
        bao nhiêu, để hiện "đã có 500.000đ" và đếm số bị bỏ qua / bị ghi đè."""
        return list(self.db.execute(
            select(EmployeeSalaryComponent)
            .where(EmployeeSalaryComponent.component_id == component_id)
        ).scalars())

    def employees_holding(self, component_id: int) -> list[int]:
        """ID các NV còn được gán khoản này — để cảnh báo khi khoản đã NGỪNG ÁP DỤNG."""
        return list(self.db.execute(
            select(EmployeeSalaryComponent.employee_id)
            .where(EmployeeSalaryComponent.component_id == component_id)
        ).scalars())

    # --- Tầng 2: mức cố định theo NGƯỜI -------------------------------------

    def employee_rows(self, employee_id: int) -> list[EmployeeSalaryComponent]:
        return list(self.db.execute(
            select(EmployeeSalaryComponent)
            .where(EmployeeSalaryComponent.employee_id == employee_id)
        ).scalars())

    def set_employee_value(self, *, employee_id: int, component_id: int, amount: float,
                           note: str | None = None) -> None:
        row = self.db.execute(
            select(EmployeeSalaryComponent).where(
                EmployeeSalaryComponent.employee_id == employee_id,
                EmployeeSalaryComponent.component_id == component_id,
            )
        ).scalars().first()
        if row is None:
            self.db.add(EmployeeSalaryComponent(
                employee_id=employee_id, component_id=component_id,
                amount=amount, note=note))
        else:
            row.amount = amount
            row.note = note

    def clear_employee_value(self, *, employee_id: int, component_id: int) -> None:
        """GỠ khoản khỏi người này — kỳ sau không còn trả nữa."""
        self.db.execute(
            delete(EmployeeSalaryComponent).where(
                EmployeeSalaryComponent.employee_id == employee_id,
                EmployeeSalaryComponent.component_id == component_id,
            )
        )

    # --- Tầng 3: snapshot + khoản phát sinh trên dòng lương -----------------

    def replace_employee_line_components(self, line_id: int, rows: list[dict]) -> None:
        """Ghi lại phần snapshot TỪ HỒ SƠ của một dòng lương.

        ⚠️ CHỈ xoá dòng `source='employee'`. Dòng `source='line'` (thưởng nóng HCNS thêm tay cho
        riêng kỳ này) PHẢI sống sót qua mọi lần bấm "Tính lại" — xoá cả hai là mất tiền của người
        lao động mà không một thông báo nào."""
        # ⚠️ CHỪA RA dòng ĐÃ ĐÈ TAY (`da_de_tay`): HCNS sửa số cho riêng kỳ này thì "Tính lại"
        # KHÔNG được ghi đè, nếu không sửa xong bấm Tính lại là mất số âm thầm — đúng lý do trước
        # 12/08/2026 phải chặn hẳn đường sửa.
        self.db.execute(
            delete(PayrollLineComponent).where(
                PayrollLineComponent.line_id == line_id,
                PayrollLineComponent.source == COMPONENT_SOURCE_EMPLOYEE,
                PayrollLineComponent.da_de_tay.is_(False),
            )
        )
        for r in rows:
            self.db.add(PayrollLineComponent(
                line_id=line_id, source=COMPONENT_SOURCE_EMPLOYEE, **r))

    def replace_auto_line_components(self, line_id: int, rows: list[dict]) -> None:
        """Ghi lại phần HỆ TỰ TÍNH của một dòng lương (hoa hồng KD).

        Xoá sạch rồi ghi mới: số hoa hồng chạy theo hoá đơn phát sinh thêm, nên mỗi lần "Tính lại"
        phải ra số mới chứ không cộng dồn.

        ⚠️ CHỈ xoá `source='auto'`. Đụng vào `line` là xoá mất thưởng nóng HCNS thêm tay; đụng vào
        `employee` là xoá khoản của hồ sơ — cả hai đều mất tiền của người lao động mà không một
        thông báo nào.

        KHÔNG cần chừa `da_de_tay` như `replace_employee_line_components`: dòng `auto` không sửa
        tay được (chốt lại 24/08/2026 — *"kệ nó ăn theo đơn hàng cho chắc"*) nên không bao giờ
        mang cờ đó. Thêm điều kiện lọc ở đây là viết một nhánh không đường nào chạy tới.
        """
        self.db.execute(
            delete(PayrollLineComponent).where(
                PayrollLineComponent.line_id == line_id,
                PayrollLineComponent.source == COMPONENT_SOURCE_AUTO,
            )
        )
        for r in rows:
            self.db.add(PayrollLineComponent(
                line_id=line_id, source=COMPONENT_SOURCE_AUTO, **r))

    def line_components(self, line_id: int, *, source: str | None = None
                        ) -> list[PayrollLineComponent]:
        stmt = select(PayrollLineComponent).where(PayrollLineComponent.line_id == line_id)
        if source is not None:
            stmt = stmt.where(PayrollLineComponent.source == source)
        return list(self.db.execute(stmt.order_by(PayrollLineComponent.id)).scalars())

    def line_components_map(self, line_ids: list[int]) -> dict[int, list[PayrollLineComponent]]:
        """Khoản của NHIỀU dòng lương trong MỘT truy vấn — bảng lương có ~100 dòng, gọi
        `line_components` cho từng dòng là 100 round-trip mỗi lần mở màn."""
        if not line_ids:
            return {}
        rows = self.db.execute(
            select(PayrollLineComponent)
            .where(PayrollLineComponent.line_id.in_(line_ids))
            .order_by(PayrollLineComponent.line_id, PayrollLineComponent.id)
        ).scalars()
        out: dict[int, list[PayrollLineComponent]] = {}
        for r in rows:
            out.setdefault(r.line_id, []).append(r)
        return out

    def get_line_component(self, row_id: int) -> PayrollLineComponent | None:
        return self.db.get(PayrollLineComponent, row_id)

    def add_line_component(self, **fields) -> PayrollLineComponent:
        """Khoản PHÁT SINH cho riêng một kỳ (thưởng nóng) — luôn `source='line'`."""
        row = PayrollLineComponent(source=COMPONENT_SOURCE_LINE, **fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_line_component(self, row: PayrollLineComponent, **fields) -> PayrollLineComponent:
        for k, v in fields.items():
            setattr(row, k, v)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_line_component(self, row: PayrollLineComponent) -> None:
        self.db.delete(row)
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()
