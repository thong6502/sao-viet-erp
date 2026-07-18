"""Kế hoạch & Lệnh sản xuất — tầng nghiệp vụ P0 (RECORD-ONLY), spec `docs/spec-ke-hoach-san-xuat.md`.

KIM CHỈ NAM: **MÁY CHỈ GHI NHẬN**. Người kế hoạch/tổ trưởng quyết; máy ghi + suy trạng thái theo
routing. KHÔNG tự lọc "ghép cùng loại", KHÔNG MRP, KHÔNG tính khoán/chi phí (P1/P2). Trạng thái
SUY RA, không bấm tay — trừ cổng cứng §8.

Chỉ còn KẾ HOẠCH (module theo dõi thực thi xưởng — sản lượng/bàn giao/QC/nhập kho — đã GỠ):
  - Kế hoạch: `bung_lenh`/`tao_lenh` · routing (§13.2) · `ghep`/placement · `gan_may` · `duyet_mau`
    · `phat` (cổng AND) · `huy_lenh`.

Trả về ORM (record-only) — schema/router/DTO là Chunk 3. Đọc quy cách/routing/SL đặt từ PTG + Đơn
qua repo (không chép). Không audit ở đây (real-time notify + audit = Chunk 3).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.department import Department
from ..models.employee import Employee
from ..models.lenh_san_xuat import (
    LENH_DANG_CHAY,
    LENH_HUY,
    LENH_NHAP,
    LENH_XONG,
    PF_CHO_GHEP,
    PF_DA_PHAT,
    PF_DU_DIEU_KIEN,
    PF_IN_XONG,
    LenhSanXuat,
    PrintForm,
    RoutingStep,
)
from ..models.order import STATUS_CANCELLED, STATUS_ORDERED, Order
from ..models.user import User
from ..models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn
from ..repositories.lenh_san_xuat_repo import LenhSanXuatRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LenhSXError(Exception):
    """Base — Chunk 3 router map sang HTTP."""


class LenhSXNotFound(LenhSXError):
    pass


class LenhSXValidationError(LenhSXError):
    pass


class LenhSXConflict(LenhSXError):
    pass


class LenhSanXuatService:
    def __init__(self, db: Session, repo: LenhSanXuatRepository | None = None) -> None:
        self.db = db
        self.repo = repo or LenhSanXuatRepository(db)

    # ---------------------------------------------------------------- helpers
    def _get_lenh(self, lenh_id: int) -> LenhSanXuat:
        lenh = self.repo.get_lenh(lenh_id)
        if lenh is None:
            raise LenhSXNotFound("Không tìm thấy lệnh sản xuất")
        return lenh

    def _get_form(self, form_id: int) -> PrintForm:
        form = self.repo.get_form(form_id)
        if form is None:
            raise LenhSXNotFound("Không tìm thấy tờ in")
        return form

    def _approver_snapshot(self, user_id: int | None) -> dict:
        """Đóng băng danh tính người duyệt mẫu: {to, chuc_vu, ten} (đọc HỒ SƠ, không suy từ hành động).

        Mirror `actor_display`: hồ sơ nhân sự (Employee theo user_id) giữ vai thật (tổ + chức vụ);
        thiếu phần nào để trống, lùi `User.name` khi chưa có hồ sơ. Đóng băng để con dấu bất biến.
        """
        snap = {"user_id": user_id, "to": None, "chuc_vu": None, "ten": None}
        if not user_id:
            return snap
        emp = self.db.execute(
            select(Employee.full_name, Employee.position, Employee.department_id)
            .where(Employee.user_id == user_id)
        ).first()
        if emp is not None:
            snap["ten"] = (emp.full_name or "").strip() or None
            snap["chuc_vu"] = (emp.position or "").strip() or None
            if emp.department_id:
                dept_name = self.db.execute(
                    select(Department.name).where(Department.id == emp.department_id)
                ).scalar_one_or_none()
                snap["to"] = dept_name
        if not snap["ten"]:
            snap["ten"] = self.db.execute(
                select(User.name).where(User.id == user_id)
            ).scalar_one_or_none()
        return snap

    def _form_readiness(self, form: PrintForm) -> tuple[bool, list[str]]:
        """Cổng PHÁT (§7): đã gán máy **AND** MỌI lệnh trên tờ đã duyệt mẫu (+ có ≥1 lệnh)."""
        blockers: list[str] = []
        placements = self.repo.placements_by_form(form.id)
        if not placements:
            blockers.append("Tờ in chưa ghép lệnh nào")
        if form.may_id is None:
            blockers.append("Tờ in chưa gán máy")
        chua_duyet = [l for l in self.repo.lenh_on_form(form.id) if l.mau_approved_at is None]
        if chua_duyet:
            blockers.append(f"Còn {len(chua_duyet)} lệnh chưa duyệt mẫu")
        return (not blockers), blockers

    def _sync_form_status(self, form: PrintForm) -> None:
        """Suy trạng thái tờ in (KHÔNG bấm tay): chờ ghép ⇄ đủ điều kiện. KHÔNG hạ cấp khi đã phát.

        Không commit ở đây — caller gộp commit.
        """
        if form.trang_thai in (PF_DA_PHAT, PF_IN_XONG):
            return
        ready, _ = self._form_readiness(form)
        form.trang_thai = PF_DU_DIEU_KIEN if ready else PF_CHO_GHEP

    # =============================================================== KẾ HOẠCH
    def _load_order_for_planning(self, order_id: int) -> Order:
        """Đơn phải tồn tại + ĐÃ CHỐT (chưa hủy) mới cho lên kế hoạch (cổng cấu trúc, không phán)."""
        order = self.db.get(Order, order_id)
        if order is None:
            raise LenhSXNotFound("Không tìm thấy đơn hàng")
        if order.status == STATUS_CANCELLED:
            raise LenhSXConflict("Đơn đã hủy — không đề lệnh sản xuất")
        if order.status != STATUS_ORDERED:
            raise LenhSXConflict("Đơn chưa chốt — chưa thể lên kế hoạch sản xuất")
        return order

    def tao_lenh(self, *, order_id: int, phieu_thanh_phan_ids: list[int]) -> LenhSanXuat:
        """Người kế hoạch PICK gom các ấn phẩm (cùng 1 đơn) → 1 LỆNH nháp + n BÀI CON (§ pick).

        MÁY CHỈ GHI NHẬN — KHÔNG phán "đủ giống để gộp". Cổng CẤU TRÚC (toàn vẹn, không phải nghiệp
        vụ): đơn đã chốt; mỗi ptp phải THUỘC đơn + CHƯA nằm trong lệnh khác (chống trùng). Routing
        CHUNG copy từ ptp ĐẦU; `lenh_sx.phieu_thanh_phan_id` = ptp đầu (đại diện, để tương thích);
        may_id gợi ý = PTP đầu. Ghép xuyên đơn KHÔNG ở đây (làm ở tầng tờ in)."""
        order = self._load_order_for_planning(order_id)
        raw = [int(p) for p in (phieu_thanh_phan_ids or [])]
        if not raw:
            raise LenhSXValidationError("Chưa chọn ấn phẩm nào để tạo lệnh")
        # ptp → dòng đơn (chỉ dòng thuộc đơn này, có ấn phẩm); giữ dòng đầu nếu ptp lặp ở nhiều dòng.
        lines_by_ptp: dict[int, object] = {}
        for ln in order.lines:
            if ln.phieu_thanh_phan_id is not None and ln.phieu_thanh_phan_id not in lines_by_ptp:
                lines_by_ptp[ln.phieu_thanh_phan_id] = ln
        da_co = self.repo.ptp_ids_in_order(order_id)
        picked: list[int] = []
        seen: set[int] = set()
        for pid in raw:
            if pid in seen:
                continue  # khử trùng trong 1 lần pick
            seen.add(pid)
            if pid not in lines_by_ptp:
                raise LenhSXValidationError(f"Ấn phẩm #{pid} không thuộc đơn này")
            if pid in da_co:
                raise LenhSXConflict(f"Ấn phẩm #{pid} đã nằm trong một lệnh khác")
            picked.append(pid)
        dai_dien = picked[0]
        ptp0 = self.repo.get_phieu_thanh_phan(dai_dien)
        lenh = self.repo.create_lenh(
            order_id=order_id,
            phieu_thanh_phan_id=dai_dien,
            may_id=(ptp0.may_id if ptp0 is not None else None),
        )
        for i, pid in enumerate(picked, start=1):
            ln = lines_by_ptp.get(pid)
            self.repo.create_lenh_item(
                lenh_sx_id=lenh.id, phieu_thanh_phan_id=pid,
                order_line_id=(ln.id if ln is not None else None), thu_tu=i,
            )
        self._copy_routing_from_ptp(lenh.id, dai_dien)
        return lenh

    def bung_lenh(self, *, order_id: int) -> list[LenhSanXuat]:
        """Tiện ích "mỗi ấn phẩm 1 lệnh" (§2, §5.1) — nay dựng trên `tao_lenh` (mỗi ptp = 1 lệnh + 1
        bài con). IDEMPOTENT theo (đơn, ấn phẩm): chỉ tạo cho ấn phẩm CHƯA có lệnh. Đơn hủy/chưa
        chốt → chặn. Người kế hoạch chủ động gom nhiều ấn phẩm/1 lệnh thì dùng `tao_lenh` trực tiếp."""
        order = self._load_order_for_planning(order_id)
        seen = set(self.repo.ptp_ids_in_order(order_id))
        created: list[LenhSanXuat] = []
        for line in order.lines:
            ptp_id = line.phieu_thanh_phan_id
            if ptp_id is None or ptp_id in seen:
                continue  # dòng không gắn ấn phẩm / đã có lệnh → bỏ (idempotent)
            seen.add(ptp_id)
            created.append(self.tao_lenh(order_id=order_id, phieu_thanh_phan_ids=[ptp_id]))
        return created

    def hang_cho(self) -> list[dict]:
        """Đơn ĐÃ CHỐT chờ lên kế hoạch (handoff §5.1) — MÁY CHỈ liệt kê; người kế hoạch bấm 'Lên kế
        hoạch' (= bung) để đề lệnh. Kèm ngữ cảnh đơn (gấp/hạn/khách/lưu ý SX) + các ấn phẩm sẽ đề lệnh.
        Đọc sống từ Đơn (không chép). Batch 3 truy vấn: đơn · tên khách · dòng đơn."""
        orders = self.repo.orders_waiting_for_planning()
        if not orders:
            return []
        cust_ids = [o.customer_id for o in orders if o.customer_id is not None]
        names = self.repo.customer_names_by_ids(cust_ids)
        covered = self.repo.covered_ptp_ids()  # ptp đã lên lệnh → ẩn khỏi sổ (pick dần)
        lines_by_order: dict[int, list] = {}
        for ln in self.repo.order_lines_by_order_ids([o.id for o in orders]):
            if ln.phieu_thanh_phan_id is None or ln.phieu_thanh_phan_id in covered:
                continue  # dòng nhập tay / ấn phẩm ĐÃ lên lệnh → không hiện ở sổ chờ
            lines_by_order.setdefault(ln.order_id, []).append(ln)
        # Quy cách rút gọn cho sổ (khổ TP · số màu · giấy) — batch đọc ấn phẩm, KỸ THUẬT (không giá).
        ptp_map = self.repo.phieu_thanh_phan_by_ids(
            [ln.phieu_thanh_phan_id for lns in lines_by_order.values() for ln in lns]
        )
        return [
            {
                "order_id": o.id,
                "order_no": o.order_no,
                "khach": names.get(o.customer_id) if o.customer_id else None,
                "is_rush": o.is_rush,
                "delivery_committed_date": o.delivery_committed_date,
                "production_note": o.production_note,
                "an_pham": [
                    {
                        "phieu_thanh_phan_id": ln.phieu_thanh_phan_id,
                        "description": ln.description,
                        "qty": ln.qty,
                        "don_vi_tinh": ln.don_vi_tinh,
                        "spec_tom_tat": self._spec_tom_tat(ptp_map.get(ln.phieu_thanh_phan_id)),
                    }
                    for ln in lines_by_order.get(o.id, [])
                ],
            }
            for o in orders
        ]

    @staticmethod
    def _spec_tom_tat(ptp) -> str:
        """Quy cách rút gọn 1 dòng cho sổ hàng chờ (KỸ THUẬT — không giá): khổ TP · số màu · nhãn giấy."""
        if ptp is None:
            return ""
        parts: list[str] = []
        if (ptp.dai_thanh_pham or 0) > 0 and (ptp.rong_thanh_pham or 0) > 0:
            parts.append(f"{ptp.dai_thanh_pham}×{ptp.rong_thanh_pham}mm")
        if (ptp.so_mau_a or 0) > 0 or (ptp.so_mau_b or 0) > 0:
            parts.append(f"{ptp.so_mau_a}/{ptp.so_mau_b} màu")
        if ptp.kho_nguyen:
            parts.append(str(ptp.kho_nguyen))
        return " · ".join(parts)

    # ============ Routing riêng mỗi lệnh (§13.2): copy từ job spec + kế hoạch sửa ============
    def _copy_routing_from_ptp(self, lenh_id: int, ptp_id: int | None) -> None:
        """Copy công đoạn từ job spec (`PhieuThanhPham` theo `thu_tu`) → `routing_step`. Tổ = ảnh
        chụp `cong_doan.department_id`; tên = tên bước (fallback tên công đoạn). Idempotent: chỉ copy
        khi lệnh CHƯA có routing (bung lại không nhân đôi). Máy CHỈ copy — không thêm/bịa bước."""
        if self.repo.routing_by_lenh(lenh_id):
            return
        for i, pham in enumerate(self.repo.routing_of_ptp(ptp_id), start=1):
            cd = self.repo.cong_doan_by_id(pham.cong_doan_id)
            ten = (pham.ten or "").strip() or (
                str(cd.ten_hien_thi or cd.ten) if cd is not None else ""
            )
            self.repo.create_routing_step(
                lenh_sx_id=lenh_id, thu_tu=i, cong_doan_id=pham.cong_doan_id,
                to_id=(cd.department_id if cd is not None else None), ten=ten,
            )

    def get_routing(self, lenh_id: int) -> list[RoutingStep]:
        if self.repo.get_lenh(lenh_id) is None:
            raise LenhSXNotFound("Không tìm thấy lệnh sản xuất")
        return self.repo.routing_by_lenh(lenh_id)

    def them_buoc_routing(
        self, *, lenh_id: int, cong_doan_id: int | None, to_id: int | None = None
    ) -> RoutingStep:
        """Kế hoạch thêm 1 bước vào CUỐI routing. Tổ mặc định = `cong_doan.department_id` (đổi được)."""
        lenh = self.repo.get_lenh(lenh_id)
        if lenh is None:
            raise LenhSXNotFound("Không tìm thấy lệnh sản xuất")
        if lenh.trang_thai in (LENH_XONG, LENH_HUY):
            raise LenhSXConflict("Lệnh đã xong/hủy — không sửa routing")
        cd = self.repo.cong_doan_by_id(cong_doan_id)
        ten = str(cd.ten_hien_thi or cd.ten) if cd is not None else ""
        resolved_to = to_id if to_id is not None else (cd.department_id if cd is not None else None)
        return self.repo.create_routing_step(
            lenh_sx_id=lenh_id, thu_tu=self.repo.max_thu_tu(lenh_id) + 1,
            cong_doan_id=cong_doan_id, to_id=resolved_to, ten=ten,
        )

    def sua_buoc_routing(
        self, *, step_id: int, cong_doan_id: int | None, to_id: int | None
    ) -> RoutingStep:
        """Đổi công đoạn / tổ của 1 bước. Kế hoạch tự quyết tổ (`to_id` gửi lên); đổi công đoạn thì
        cập nhật tên hiển thị."""
        step = self.repo.get_routing_step(step_id)
        if step is None:
            raise LenhSXNotFound("Không tìm thấy bước routing")
        cd = self.repo.cong_doan_by_id(cong_doan_id)
        ten = str(cd.ten_hien_thi or cd.ten) if cd is not None else step.ten
        return self.repo.update_routing_step(
            step, cong_doan_id=cong_doan_id, to_id=to_id, ten=ten
        )

    def xoa_buoc_routing(self, *, step_id: int) -> int:
        step = self.repo.get_routing_step(step_id)
        if step is None:
            raise LenhSXNotFound("Không tìm thấy bước routing")
        lenh_id = step.lenh_sx_id
        self.repo.delete_routing_step(step)
        return lenh_id

    def doi_thu_tu_routing(self, *, lenh_id: int, step_ids: list[int]) -> list[RoutingStep]:
        """Đổi thứ tự routing — CHỈ khi lệnh còn NHÁP (mọi bước đang chờ, trước khi phát)."""
        lenh = self.repo.get_lenh(lenh_id)
        if lenh is None:
            raise LenhSXNotFound("Không tìm thấy lệnh sản xuất")
        if lenh.trang_thai != LENH_NHAP:
            raise LenhSXConflict("Chỉ đổi thứ tự khi lệnh còn nháp (trước khi phát)")
        by_id = {s.id: s for s in self.repo.routing_by_lenh(lenh_id)}
        for i, sid in enumerate(step_ids, start=1):
            s = by_id.get(sid)
            if s is not None:
                self.repo.update_routing_step(s, thu_tu=i)
        return self.repo.routing_by_lenh(lenh_id)

    def ghep(
        self,
        *,
        giay_id: int | None = None,
        giay_label: str | None = None,
        kho_in_dai: int = 0,
        kho_in_rong: int = 0,
        so_mau: int = 0,
        may_id: int | None = None,
        so_to_chay: int = 0,
        so_kem: int = 0,
        placements: list[dict] | None = None,
    ) -> PrintForm:
        """Tạo 1 TỜ IN + các dòng xếp bài (số con NHẬP TAY). MÁY CHỈ GHI — KHÔNG lọc/chặn "cùng loại".

        `placements` = [{lenh_sx_id, so_con}]. Giấy/khổ/màu là ẢNH CHỤP để người dễ nhìn (UI đọc gợi ý
        từ PTG, truyền vào đây). Trạng thái tờ suy ngay sau khi ghép (chờ ghép / đủ điều kiện).
        """
        rows = placements or []
        # Kiểm lệnh tồn tại TRƯỚC khi tạo tờ (tránh để lại tờ mồ côi khi input sai).
        for p in rows:
            if self.repo.get_lenh(p["lenh_sx_id"]) is None:
                raise LenhSXValidationError(f"Lệnh #{p['lenh_sx_id']} không tồn tại")
        form = self.repo.create_form(
            giay_id=giay_id, giay_label=giay_label,
            kho_in_dai=kho_in_dai, kho_in_rong=kho_in_rong,
            so_mau=so_mau, may_id=may_id, so_to_chay=so_to_chay, so_kem=so_kem,
        )
        for p in rows:
            self.repo.add_placement(
                print_form_id=form.id, lenh_sx_id=p["lenh_sx_id"], so_con=int(p.get("so_con", 0)),
            )
        self._sync_form_status(form)
        self.db.commit()
        self.db.refresh(form)
        return form

    def _assert_form_editable(self, form: PrintForm) -> None:
        """Chặn sửa xếp bài SAU khi đã phát/in xong (đã xuống xưởng — sửa = in bù/hủy, P1). §GIẢ ĐỊNH."""
        if form.trang_thai in (PF_DA_PHAT, PF_IN_XONG):
            raise LenhSXConflict("Tờ in đã phát xuống xưởng — không sửa xếp bài (dùng in bù/hủy)")

    def them_placement(self, *, form_id: int, lenh_sx_id: int, so_con: int) -> PrintForm:
        form = self._get_form(form_id)
        self._assert_form_editable(form)
        if self.repo.get_lenh(lenh_sx_id) is None:
            raise LenhSXValidationError(f"Lệnh #{lenh_sx_id} không tồn tại")
        self.repo.add_placement(print_form_id=form_id, lenh_sx_id=lenh_sx_id, so_con=so_con)
        self._sync_form_status(form)
        self.db.commit()
        self.db.refresh(form)
        return form

    def sua_placement(self, *, placement_id: int, so_con: int) -> PrintForm:
        pl = self.repo.get_placement(placement_id)
        if pl is None:
            raise LenhSXNotFound("Không tìm thấy dòng xếp bài")
        form = self._get_form(pl.print_form_id)
        self._assert_form_editable(form)
        self.repo.update_placement(pl, so_con=so_con)
        return form

    def xoa_placement(self, *, placement_id: int) -> PrintForm:
        pl = self.repo.get_placement(placement_id)
        if pl is None:
            raise LenhSXNotFound("Không tìm thấy dòng xếp bài")
        form = self._get_form(pl.print_form_id)
        self._assert_form_editable(form)
        self.repo.delete_placement(pl)
        self._sync_form_status(form)
        self.db.commit()
        self.db.refresh(form)
        return form

    def gan_may(self, *, form_id: int, may_id: int | None) -> PrintForm:
        """Gán máy cho tờ in (máy chạy THỰC). Suy lại trạng thái tờ (có thể → đủ điều kiện)."""
        form = self._get_form(form_id)
        form.may_id = may_id
        self._sync_form_status(form)
        self.db.commit()
        self.db.refresh(form)
        return form

    def duyet_mau(self, *, lenh_id: int, actor_id: int | None) -> LenhSanXuat:
        """Duyệt mẫu 1 lệnh (§5): con dấu người + giờ + snapshot {tổ·chức vụ·tên} ĐÓNG BĂNG.

        Idempotent — đã duyệt thì GIỮ dấu cũ (đóng băng, không đóng lại). Sau duyệt: đồng bộ trạng
        thái MỌI tờ in chứa lệnh (duyệt mẫu là 1 vế cổng AND).
        """
        lenh = self._get_lenh(lenh_id)
        if lenh.mau_approved_at is not None:
            return lenh  # đã duyệt — giữ nguyên con dấu (đóng băng)
        lenh.mau_approved_at = _utcnow()
        lenh.mau_approved_by = actor_id
        lenh.mau_approved_snapshot = self._approver_snapshot(actor_id)
        for form in self.repo.forms_of_lenh(lenh_id):
            self._sync_form_status(form)
        self.db.commit()
        self.db.refresh(lenh)
        return lenh

    def phat(self, *, form_id: int) -> PrintForm:
        """PHÁT tờ in xuống xưởng — CỔNG AND (§7): đã gán máy + MỌI lệnh trên tờ đã duyệt mẫu.

        Mở cổng → `print_form.trang_thai = da_phat`; các lệnh còn NHÁP trên tờ → `dang_chay` (mở cổng
        cứng ghi sản lượng, §8). Idempotent: đã phát thì trả nguyên trạng.
        """
        form = self._get_form(form_id)
        if form.trang_thai in (PF_DA_PHAT, PF_IN_XONG):
            return form  # đã phát — idempotent
        ready, blockers = self._form_readiness(form)
        if not ready:
            raise LenhSXValidationError("Chưa đủ điều kiện phát: " + "; ".join(blockers))
        form.trang_thai = PF_DA_PHAT
        for lenh in self.repo.lenh_on_form(form.id):
            if lenh.trang_thai == LENH_NHAP:
                lenh.trang_thai = LENH_DANG_CHAY
        self.db.commit()
        self.db.refresh(form)
        return form

    # ================================================================ ĐÍCH SL (đọc sống từ Đơn/PTP)
    def _muc_tieu_ptp(self, order_id: int, ptp_id: int | None, order_line_id: int | None) -> int:
        """Đích SL 1 ấn phẩm = SL đặt (OrderLine.qty) — ưu tiên dòng theo `order_line_id` (bài con giữ),
        lùi dòng trỏ ptp, rồi PTP.so_luong. 0 = chưa biết. Đọc SỐNG (không chép)."""
        line = self.repo.order_line_by_id(order_line_id)
        if line is None:
            line = self.repo.order_line_for_ptp(order_id, ptp_id)
        if line is not None and (line.qty or 0) > 0:
            return int(line.qty)
        ptp = self.repo.get_phieu_thanh_phan(ptp_id)
        if ptp is not None and (ptp.so_luong or 0) > 0:
            return int(ptp.so_luong)
        return 0

    def _muc_tieu_sl(self, lenh: LenhSanXuat) -> int:
        """Đích 'đủ SL' của lệnh = Σ đích các BÀI CON; lệnh cũ (chưa có bài con) → ấn phẩm đại diện."""
        items = self.repo.items_of_lenh(lenh.id)
        if items:
            return sum(
                self._muc_tieu_ptp(lenh.order_id, it.phieu_thanh_phan_id, it.order_line_id)
                for it in items
            )
        return self._muc_tieu_ptp(lenh.order_id, lenh.phieu_thanh_phan_id, None)

    def _item_dto(
        self, order_id: int, ptp_id: int | None, order_line_id: int | None,
        item_id: int | None = None,
    ) -> dict:
        """1 BÀI CON cho DTO lệnh (giữ chi tiết): id (bài con) + tên + SL + ĐVT (đọc sống từ Đơn/PTP)."""
        line = self.repo.order_line_by_id(order_line_id)
        if line is None:
            line = self.repo.order_line_for_ptp(order_id, ptp_id)
        ptp = self.repo.get_phieu_thanh_phan(ptp_id)
        ten = (
            (line.description if line is not None and line.description else None)
            or (ptp.ten if ptp is not None and ptp.ten else None)
            or (f"Ấn phẩm #{ptp_id}" if ptp_id else "—")
        )
        qty = self._muc_tieu_ptp(order_id, ptp_id, order_line_id)
        dvt = (
            (line.don_vi_tinh if line is not None and line.don_vi_tinh else None)
            or (ptp.don_vi_tinh if ptp is not None else None)
            or ""
        )
        return {
            "id": item_id, "phieu_thanh_phan_id": ptp_id,
            "ten": ten, "qty": qty, "don_vi_tinh": dvt,
        }

    def _lenh_items_dto(self, lenh: LenhSanXuat) -> list[dict]:
        """Bài con của lệnh (giữ ĐỦ chi tiết). Lệnh cũ chưa có bài con → 1 bài con từ ấn phẩm đại diện."""
        items = self.repo.items_of_lenh(lenh.id)
        if not items:
            return [self._item_dto(lenh.order_id, lenh.phieu_thanh_phan_id, None)]
        return [
            self._item_dto(lenh.order_id, it.phieu_thanh_phan_id, it.order_line_id, item_id=it.id)
            for it in items
        ]

    def huy_lenh(self, *, lenh_id: int) -> LenhSanXuat:
        """Hủy 1 lệnh (§GIẢ ĐỊNH — hủy giữa chừng chi tiết P1): đánh dấu HUY. Không cho hủy khi đã XONG."""
        lenh = self._get_lenh(lenh_id)
        if lenh.trang_thai == LENH_XONG:
            raise LenhSXConflict("Lệnh đã xong — không hủy")
        if lenh.trang_thai == LENH_HUY:
            return lenh
        return self.repo.update_lenh(lenh, trang_thai=LENH_HUY)

    # ================================================================= ĐỌC (DTO)
    # Chunk 3 — helper ĐỌC thuần cho router/DTO (append-only, KHÔNG đổi logic mutate ở trên).
    def list_lenh(
        self, *, order_id: int | None = None, trang_thai: str | None = None,
        page: int = 1, size: int = 50,
    ) -> tuple[list[LenhSanXuat], int]:
        return self.repo.list_lenh(order_id=order_id, trang_thai=trang_thai, page=page, size=size)

    def lenh_detail(self, lenh_id: int) -> dict:
        """Lệnh + bài con + routing + tờ in chứa nó + đích SL — nuôi màn chi tiết lệnh (kế hoạch)."""
        lenh = self._get_lenh(lenh_id)
        return {
            "lenh": lenh,
            "items": self._lenh_items_dto(lenh),
            "routing": self.repo.routing_by_lenh(lenh_id),
            "forms": self.repo.forms_of_lenh(lenh_id),
            "muc_tieu_sl": self._muc_tieu_sl(lenh),
        }

    # Quy cách in được phép OVERRIDE tại LỆNH (kế thừa báo giá làm mặc định; sửa khi nháp).
    _QUY_CACH_OVERRIDE_FIELDS = (
        "giay_id", "dai_thanh_pham", "rong_thanh_pham", "kho_thanh_pham", "kho_mo_rong",
        "tay_gap", "so_to_per_sp", "kho_nguyen_dai", "kho_nguyen_rong", "nguon_giay",
        "quy_cach_in", "kho_in_dai", "kho_in_rong", "so_con", "con_auto",
        "che_ban_loai", "so_mau_a", "so_mau_b",
    )

    @staticmethod
    def _so_kem_eff(so_mau_a, so_mau_b, quy_cach_in, so_to_per_sp) -> int:
        """Số kẽm theo giá trị HIỆU LỰC: 1 mặt / tự trở = màu A × số tờ/SP; 2 mặt = (A+B) × số tờ."""
        a, b = int(so_mau_a or 0), int(so_mau_b or 0)
        per = int(so_to_per_sp or 1)
        kem_mau = a if quy_cach_in in ("mot_mat", "tu_tro") else (a + b)
        return kem_mau * per

    def _engine_comp(self, ptp) -> dict | None:
        """Component tương ứng ấn phẩm trong SNAPSHOT engine (`PhieuTinhGia.result_json`) — match theo
        vị trí thành phần (sort thu_tu,id → idx). Trả None nếu phiếu chưa tính (chưa có result_json)."""
        phieu = getattr(ptp, "phieu", None)
        result = getattr(phieu, "result_json", None) if phieu is not None else None
        if not result:
            return None
        comps = (result.get("meta") or {}).get("components") or []
        tps = sorted(phieu.thanh_phans, key=lambda t: (t.thu_tu or 0, t.id or 0))
        try:
            idx = [t.id for t in tps].index(ptp.id)
        except ValueError:
            return None
        for c in comps:
            if c.get("idx") == idx:
                return c
        return comps[idx] if 0 <= idx < len(comps) else None

    def an_pham_chi_tiet(self, ptp_id: int, lenh_item_id: int | None = None) -> dict:
        """Chi tiết ĐẦY ĐỦ 1 ấn phẩm cho DRAWER (mirror phiếu công đoạn), giá trị HIỆU LỰC = báo giá +
        OVERRIDE tại lệnh. Mở kèm `lenh_item_id` (từ lệnh) → trộn override + cờ `editable` (lệnh nháp);
        không có → thuần báo giá (sổ chờ, read-only). Số kẽm tính theo giá trị hiệu lực.

        CÔ LẬP THƯƠNG MẠI: CHỈ trường KỸ THUẬT; LỌC SẠCH mọi cột/giá trị giá — không xuống kỹ thuật.
        """
        ptp = self.repo.get_phieu_thanh_phan(ptp_id)
        if ptp is None:
            raise LenhSXNotFound("Không tìm thấy ấn phẩm")

        # Override + editable từ BÀI CON (khi mở từ lệnh). Chỉ nhận override đúng bài con của ptp này.
        override: dict = {}
        editable = False
        item = None
        if lenh_item_id is not None:
            item = self.repo.get_lenh_item(lenh_item_id)
            if item is not None and item.phieu_thanh_phan_id == ptp_id:
                override = item.quy_cach_override or {}
                lenh = self.repo.get_lenh(item.lenh_sx_id)
                editable = lenh is not None and lenh.trang_thai == LENH_NHAP
            else:
                item = None

        def eff(key: str):
            v = override.get(key) if override else None
            return v if v is not None else getattr(ptp, key, None)

        # Giấy: resolve tên + chủng loại theo giay_id HIỆU LỰC (server-side db.get — không cần RBAC list).
        giay_id_eff = eff("giay_id")
        giay_ten = gsm = chung_loai_ten = None
        if giay_id_eff is not None:
            giay = self.db.get(GiayNguyen, giay_id_eff)
            if giay is not None:
                giay_ten, gsm = giay.ten, giay.gsm
                if giay.chung_loai_giay_id is not None:
                    cl = self.db.get(ChungLoaiGiay, giay.chung_loai_giay_id)
                    chung_loai_ten = cl.ten if cl is not None else None

        # SL cần/thực tế/nguyên từ SNAPSHOT engine (THEO BÁO GIÁ — không đổi theo override; FE ghi chú).
        comp = self._engine_comp(ptp)

        def _ci(key: str) -> int | None:
            v = comp.get(key) if comp else None
            return int(v) if isinstance(v, (int, float)) else None

        so_kem = self._so_kem_eff(
            eff("so_mau_a"), eff("so_mau_b"), eff("quy_cach_in"), eff("so_to_per_sp")
        )

        # Vật tư thêm (vecni bóng/mờ · cán màng…) — tên + ghi chú, KHÔNG giá.
        vat_tu = []
        for vt in (getattr(ptp, "vat_tus", None) or []):
            ten = vt.ten
            if not ten and vt.vat_tu_id is not None:
                v = self.db.get(VatTuInAn, vt.vat_tu_id)
                ten = v.ten if v is not None else None
            vat_tu.append({"ten": ten or "—", "ghi_chu": vt.ghi_chu})

        routing = [
            {
                "thu_tu": r.thu_tu, "cong_doan_id": r.cong_doan_id, "ten": r.ten,
                "nha_cung_cap": r.nha_cung_cap, "ghi_chu": r.ghi_chu,
            }
            for r in self.repo.routing_of_ptp(ptp_id)
        ]

        overridden = [k for k in self._QUY_CACH_OVERRIDE_FIELDS if override.get(k) is not None]

        return {
            "phieu_thanh_phan_id": ptp.id,
            "lenh_item_id": (item.id if item is not None else None),
            "editable": editable,
            "overridden": overridden,
            # nhận dạng / thành phẩm (giá trị hiệu lực)
            "ten": ptp.ten,
            "loai_thanh_phan": ptp.loai_thanh_phan,
            "kho_thanh_pham": eff("kho_thanh_pham"),
            "dai_thanh_pham": eff("dai_thanh_pham"),
            "rong_thanh_pham": eff("rong_thanh_pham"),
            "kho_mo_rong": eff("kho_mo_rong"),
            "tay_gap": eff("tay_gap"),
            "so_to_per_sp": eff("so_to_per_sp"),
            "so_luong": ptp.so_luong,
            "don_vi_tinh": ptp.don_vi_tinh,
            # giấy
            "giay_id": giay_id_eff,
            "giay_ten": giay_ten,
            "chung_loai_ten": chung_loai_ten,
            "gsm": gsm,
            "kho_nguyen": ptp.kho_nguyen,
            "kho_nguyen_dai": eff("kho_nguyen_dai"),
            "kho_nguyen_rong": eff("kho_nguyen_rong"),
            "nguon_giay": eff("nguon_giay"),
            # in & màu
            "co_in": ptp.co_in,
            "che_ban_loai": eff("che_ban_loai"),
            "quy_cach_in": eff("quy_cach_in"),
            "kho_in_dai": eff("kho_in_dai"),
            "kho_in_rong": eff("kho_in_rong"),
            "so_con": eff("so_con"),
            "con_auto": eff("con_auto"),
            "may_id": ptp.may_id,
            "so_mau_a": eff("so_mau_a"),
            "so_mau_b": eff("so_mau_b"),
            "so_kem": so_kem,
            # số lượng (engine snapshot theo báo giá — None nếu phiếu chưa tính)
            "so_luong_can": _ci("to_net"),
            "so_to_thuc_te": _ci("to_dau_vao"),
            "so_to_sau_in": _ci("to_sau_in"),
            "so_to_nguyen": _ci("to_nguyen"),
            "con_tren_to": _ci("con"),
            "bu_hao_auto": _ci("bu_hao_auto"),
            "bu_hao_so_to": ptp.bu_hao_so_to,
            "hao_so_to": ptp.hao_so_to,
            "tinh_bu_hao_cd": ptp.tinh_bu_hao_cd,
            # note kỹ thuật theo sản phẩm
            "ghi_chu_ky_thuat": ptp.ghi_chu_ky_thuat,
            # vật tư + routing
            "vat_tu": vat_tu,
            "routing": routing,
        }

    def sua_quy_cach_bai_con(self, *, item_id: int, override: dict) -> dict:
        """Kế hoạch SỬA quy cách in của 1 bài con (override báo giá) — CHỈ khi lệnh còn NHÁP (cổng toàn
        vẹn trạng thái, không phải máy phán). Chỉ nhận field trong danh sách cho phép; giá trị None =
        gỡ override (kế thừa lại). KHÔNG đụng bảng tính giá. Trả chi tiết HIỆU LỰC mới."""
        item = self.repo.get_lenh_item(item_id)
        if item is None:
            raise LenhSXNotFound("Không tìm thấy bài con")
        lenh = self.repo.get_lenh(item.lenh_sx_id)
        if lenh is None:
            raise LenhSXNotFound("Không tìm thấy lệnh sản xuất")
        if lenh.trang_thai != LENH_NHAP:
            raise LenhSXConflict("Lệnh đã phát/xong — chỉ sửa quy cách khi lệnh còn nháp")
        clean = {
            k: v for k, v in (override or {}).items()
            if k in self._QUY_CACH_OVERRIDE_FIELDS and v is not None
        }
        self.repo.update_lenh_item(item, quy_cach_override=(clean or None))
        return self.an_pham_chi_tiet(item.phieu_thanh_phan_id, lenh_item_id=item.id)

    def list_forms(
        self, *, trang_thai: str | None = None, may_id: int | None = None,
        page: int = 1, size: int = 50,
    ) -> tuple[list[PrintForm], int]:
        return self.repo.list_forms(trang_thai=trang_thai, may_id=may_id, page=page, size=size)

    def form_detail(self, form_id: int) -> dict:
        """Tờ in + danh sách xếp bài + các lệnh trên tờ — nuôi màn ghép bài / theo máy."""
        form = self._get_form(form_id)
        return {
            "form": form,
            "placements": self.repo.placements_by_form(form_id),
            "lenhs": self.repo.lenh_on_form(form_id),
        }

    def lenh_on_form(self, form_id: int) -> list[LenhSanXuat]:
        """Các lệnh trên 1 tờ in (dùng để lấy lenh_ids đẩy sự kiện real-time khi phát)."""
        return self.repo.lenh_on_form(form_id)
