"""Kế hoạch & Lệnh sản xuất — tầng nghiệp vụ P0 (RECORD-ONLY), spec `docs/spec-ke-hoach-san-xuat.md`.

KIM CHỈ NAM: **MÁY CHỈ GHI NHẬN**. Người kế hoạch/tổ trưởng quyết; máy ghi + suy trạng thái theo
routing. KHÔNG tự lọc "ghép cùng loại", KHÔNG MRP, KHÔNG tính khoán/chi phí (P1/P2). Trạng thái
SUY RA, không bấm tay — trừ cổng cứng §8.

Các vai (1 service, nhóm theo mục spec):
  - Kế hoạch: `bung_lenh` · `ghep`/placement · `gan_may` · `duyet_mau` · `phat` (cổng AND).
  - Tổ chạy:  `ghi_san_luong` · `ban_giao`/`xac_nhan_nhan` · `ghi_loi_qc`/`to_truong_xac_nhan_qc`.
  - Kết thúc: `nhap_kho_thanh_pham` → suy lệnh XONG (đủ SL) → suy đơn xong (mọi lệnh XONG).

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
    QC_CHO,
    QC_XAC_NHAN,
    RS_CHO,
    RS_DANG,
    RS_XONG,
    LenhSanXuat,
    PrintForm,
    RoutingStep,
)
from ..models.order import STATUS_CANCELLED, Order
from ..models.user import User
from ..repositories.lenh_san_xuat_repo import LenhSanXuatRepository
from ..repositories.rbac_repo import DepartmentRepository


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
    def bung_lenh(self, *, order_id: int) -> list[LenhSanXuat]:
        """Đơn chốt → tự đề LỆNH NHÁP: mỗi `OrderLine` có `phieu_thanh_phan_id` = 1 lệnh (§2, §5.1).

        IDEMPOTENT theo (đơn, ấn phẩm): chốt lại / gọi lại KHÔNG nhân đôi — chỉ tạo lệnh cho ấn phẩm
        CHƯA có lệnh (bung mở rộng, §GIẢ ĐỊNH). Đơn đã hủy → không bung. may_id gợi ý = PTP.may_id
        (máy chạy THỰC gán ở tờ in). Đọc `order.lines` (cầu ptp) qua ORM Order.
        """
        order = self.db.get(Order, order_id)
        if order is None:
            raise LenhSXNotFound("Không tìm thấy đơn hàng")
        if order.status == STATUS_CANCELLED:
            raise LenhSXConflict("Đơn đã hủy — không đề lệnh sản xuất")

        da_co = self.repo.ptp_ids_with_lenh(order_id)
        created: list[LenhSanXuat] = []
        for line in order.lines:
            ptp_id = line.phieu_thanh_phan_id
            if ptp_id is None or ptp_id in da_co:
                continue  # dòng không gắn ấn phẩm / đã có lệnh → bỏ (idempotent)
            ptp = self.repo.get_phieu_thanh_phan(ptp_id)
            lenh = self.repo.create_lenh(
                order_id=order_id,
                phieu_thanh_phan_id=ptp_id,
                may_id=(ptp.may_id if ptp is not None else None),
            )
            self._copy_routing_from_ptp(lenh.id, ptp_id)
            created.append(lenh)
            da_co.add(ptp_id)
        return created

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
        """Đổi công đoạn / tổ của 1 bước — CHỈ khi bước còn CHỜ (chưa/không chạy). Kế hoạch tự quyết
        tổ (`to_id` gửi lên); đổi công đoạn thì cập nhật tên hiển thị."""
        step = self.repo.get_routing_step(step_id)
        if step is None:
            raise LenhSXNotFound("Không tìm thấy bước routing")
        if step.trang_thai != RS_CHO:
            raise LenhSXConflict("Bước đã/đang chạy — không sửa được")
        cd = self.repo.cong_doan_by_id(cong_doan_id)
        ten = str(cd.ten_hien_thi or cd.ten) if cd is not None else step.ten
        return self.repo.update_routing_step(
            step, cong_doan_id=cong_doan_id, to_id=to_id, ten=ten
        )

    def xoa_buoc_routing(self, *, step_id: int) -> int:
        step = self.repo.get_routing_step(step_id)
        if step is None:
            raise LenhSXNotFound("Không tìm thấy bước routing")
        if step.trang_thai != RS_CHO:
            raise LenhSXConflict("Bước đã/đang chạy — không xóa được")
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

    # ---------- Thực thi routing ở màn TỔ (§13.4 — bắt đầu/hoàn thành qua quét QR) ----------
    @staticmethod
    def _current_step_id(routing: list[RoutingStep]) -> int | None:
        """'Đến lượt' = bước đầu tiên (theo thứ tự) CHƯA xong. Routing tuyến tính: 1 bước chạy 1 lúc.

        None = mọi bước đã xong (routing hết) → không còn bước đến lượt.
        """
        for s in routing:  # repo trả theo thu_tu asc
            if s.trang_thai != RS_XONG:
                return s.id
        return None

    def _get_step_on_lenh(self, step_id: int) -> tuple[RoutingStep, LenhSanXuat]:
        step = self.repo.get_routing_step(step_id)
        if step is None:
            raise LenhSXNotFound("Không tìm thấy bước routing")
        lenh = self._get_lenh(step.lenh_sx_id)
        return step, lenh

    def bat_dau_buoc(self, *, step_id: int) -> tuple[list[RoutingStep], int | None]:
        """Tổ BẮT ĐẦU bước routing của mình (quét QR). Chỉ mở khi lệnh đã phát + đúng bước đến lượt.

        Cổng toàn vẹn (không phải máy phán nghiệp vụ): lệnh đang chạy · bước còn CHỜ · bước là bước
        ĐẾN LƯỢT (mọi bước trước đã xong). Trả routing mới + tổ của bước đến lượt (để đẩy real-time).
        """
        step, lenh = self._get_step_on_lenh(step_id)
        if lenh.trang_thai != LENH_DANG_CHAY:
            raise LenhSXConflict("Lệnh chưa được phát (hoặc đã xong/hủy) — chưa bắt đầu được")
        if step.trang_thai == RS_DANG:
            return self.repo.routing_by_lenh(lenh.id), step.to_id  # idempotent
        if step.trang_thai != RS_CHO:
            raise LenhSXConflict("Bước đã xong — không bắt đầu lại")
        routing = self.repo.routing_by_lenh(lenh.id)
        if self._current_step_id(routing) != step.id:
            raise LenhSXConflict("Chưa tới lượt bước này — bước trước chưa xong")
        self.repo.update_routing_step(step, trang_thai=RS_DANG, bat_dau_at=_utcnow())
        return self.repo.routing_by_lenh(lenh.id), step.to_id

    def hoan_thanh_buoc(self, *, step_id: int) -> tuple[list[RoutingStep], int | None]:
        """Tổ HOÀN THÀNH bước đang chạy (quét QR) → xong. Trả routing mới + tổ của bước KẾ (đến lượt
        mới) để đẩy real-time đích danh 'đến lượt' (tổ B ting sang tổ A lấy hàng). None = routing hết.
        """
        step, lenh = self._get_step_on_lenh(step_id)
        if lenh.trang_thai != LENH_DANG_CHAY:
            raise LenhSXConflict("Lệnh chưa được phát (hoặc đã xong/hủy) — chưa hoàn thành được")
        if step.trang_thai == RS_XONG:
            routing = self.repo.routing_by_lenh(lenh.id)
            return routing, self._next_to_id(routing, step.id)  # idempotent
        if step.trang_thai != RS_DANG:
            raise LenhSXConflict("Bước chưa bắt đầu — không hoàn thành được")
        self.repo.update_routing_step(step, trang_thai=RS_XONG, hoan_thanh_at=_utcnow())
        routing = self.repo.routing_by_lenh(lenh.id)
        return routing, self._next_to_id(routing, step.id)

    @staticmethod
    def _next_to_id(routing: list[RoutingStep], done_step_id: int) -> int | None:
        """Tổ của bước ĐẾN LƯỢT sau khi 1 bước xong = bước đầu tiên chưa xong (nếu không phải chính nó)."""
        for s in routing:
            if s.trang_thai != RS_XONG and s.id != done_step_id:
                return s.to_id
        return None

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

    # ================================================================ TỔ CHẠY
    def ghi_san_luong(
        self, *, lenh_id: int, cong_doan_id: int | None, to_id: int | None,
        so_dat: int, so_hong: int, nguoi_ghi: int | None,
    ):
        """Tổ trưởng ghi sản lượng 1 công đoạn (số đạt + số hỏng). Log thuần — không state-machine.

        CỔNG CỨNG (§8): chỉ ghi khi lệnh ĐÃ PHÁT (đang chạy) — chưa phát thì chặn.
        """
        lenh = self._get_lenh(lenh_id)
        if lenh.trang_thai not in (LENH_DANG_CHAY, LENH_XONG):
            raise LenhSXConflict("Lệnh chưa được phát (chưa qua cổng phát tờ in) — không ghi sản lượng")
        if so_dat < 0 or so_hong < 0:
            raise LenhSXValidationError("Số đạt / số hỏng không được âm")
        return self.repo.add_san_luong(
            lenh_sx_id=lenh_id, cong_doan_id=cong_doan_id, to_id=to_id,
            so_dat=so_dat, so_hong=so_hong, nguoi_ghi=nguoi_ghi,
        )

    def ban_giao(
        self, *, lenh_id: int, cong_doan_tu_id: int | None, cong_doan_toi_id: int | None,
        so_giao: int, to_giao_id: int | None, to_nhan_id: int | None,
    ):
        """Tổ trưởng GIAO số đạt sang công đoạn/tổ kế. `nhan_at` NULL tới khi tổ kế xác nhận (§8)."""
        lenh = self._get_lenh(lenh_id)
        if lenh.trang_thai not in (LENH_DANG_CHAY, LENH_XONG):
            raise LenhSXConflict("Lệnh chưa được phát — không bàn giao")
        if so_giao < 0:
            raise LenhSXValidationError("Số giao không được âm")
        return self.repo.add_ban_giao(
            lenh_sx_id=lenh_id, cong_doan_tu_id=cong_doan_tu_id, cong_doan_toi_id=cong_doan_toi_id,
            so_giao=so_giao, to_giao_id=to_giao_id, to_nhan_id=to_nhan_id,
        )

    def xac_nhan_nhan(self, *, ban_giao_id: int):
        """Tổ kế XÁC NHẬN NHẬN (real-time ở Chunk 3) → set `nhan_at`. Idempotent: giữ mốc nhận đầu."""
        bg = self.repo.get_ban_giao(ban_giao_id)
        if bg is None:
            raise LenhSXNotFound("Không tìm thấy phiếu bàn giao")
        if bg.nhan_at is not None:
            return bg  # đã xác nhận — giữ nguyên
        return self.repo.update_ban_giao(bg, nhan_at=_utcnow())

    def ghi_loi_qc(
        self, *, lenh_id: int, cong_doan_id: int | None, to_bi_quy_id: int | None,
        anh_url: str | None = None, mo_ta: str | None = None,
    ):
        """QC/KCS nêu lỗi = ảnh + tổ bị quy + công đoạn + mô tả → trạng thái CHỜ tổ trưởng xác nhận (§8).

        Chưa xác nhận = CHƯA thành lỗi chính thức. KHÔNG tự quy lỗi / trừ khoán — disposition P1.
        """
        self._get_lenh(lenh_id)  # đảm bảo lệnh tồn tại
        return self.repo.add_qc_defect(
            lenh_sx_id=lenh_id, cong_doan_id=cong_doan_id, to_bi_quy_id=to_bi_quy_id,
            anh_url=anh_url, mo_ta=mo_ta, trang_thai=QC_CHO,
        )

    def to_truong_xac_nhan_qc(self, *, qc_id: int):
        """Tổ trưởng tổ bị quy XÁC NHẬN → lỗi ghi nhận chính thức (`xac_nhan_at` + trạng thái). Idempotent."""
        qc = self.repo.get_qc_defect(qc_id)
        if qc is None:
            raise LenhSXNotFound("Không tìm thấy phiếu lỗi QC")
        if qc.trang_thai == QC_XAC_NHAN and qc.xac_nhan_at is not None:
            return qc
        return self.repo.update_qc_defect(qc, trang_thai=QC_XAC_NHAN, xac_nhan_at=_utcnow())

    # ================================================================ KẾT THÚC
    def _muc_tieu_sl(self, lenh: LenhSanXuat) -> int:
        """Đích 'đủ SL' của lệnh = SL đặt trên dòng đơn (qty) của ấn phẩm; lùi PTP.so_luong. 0 = chưa biết."""
        line = self.repo.order_line_for_ptp(lenh.order_id, lenh.phieu_thanh_phan_id)
        if line is not None and (line.qty or 0) > 0:
            return int(line.qty)
        ptp = self.repo.get_phieu_thanh_phan(lenh.phieu_thanh_phan_id)
        if ptp is not None and (ptp.so_luong or 0) > 0:
            return int(ptp.so_luong)
        return 0

    def nhap_kho_thanh_pham(self, *, lenh_id: int, so_luong_nhap: int) -> dict:
        """Ghi nhận NHẬP KHO thành phẩm của lệnh → suy lệnh XONG khi ĐỦ SL (§8); rồi suy đơn xong.

        GIẢ ĐỊNH (chưa nối API Kho): nhập kho THẬT ở module Kho; ở đây nhận `so_luong_nhap` = tổng SL
        thành phẩm đã nhập kho cho lệnh (caller/Chunk 3 cộng dồn từ phiếu nhập kho) + đánh dấu trạng
        thái. `so_luong_nhap ≥ đích` ⇒ lệnh XONG. Đơn "xong sản xuất" = SUY RA (mọi lệnh XONG) — KHÔNG
        ghi vào `orders.status` (Order module sở hữu vòng đời đơn; chưa có trạng thái 'xong SX').
        """
        lenh = self._get_lenh(lenh_id)
        if lenh.trang_thai == LENH_HUY:
            raise LenhSXConflict("Lệnh đã hủy — không nhập kho thành phẩm")
        if so_luong_nhap < 0:
            raise LenhSXValidationError("Số lượng nhập không được âm")
        muc_tieu = self._muc_tieu_sl(lenh)
        du_sl = muc_tieu > 0 and so_luong_nhap >= muc_tieu
        if du_sl and lenh.trang_thai != LENH_XONG:
            self.repo.update_lenh(lenh, trang_thai=LENH_XONG)
        order_done = self.order_production_done(lenh.order_id)
        return {
            "lenh": lenh,
            "muc_tieu_sl": muc_tieu,
            "so_luong_nhap": so_luong_nhap,
            "lenh_xong": lenh.trang_thai == LENH_XONG,
            "order_production_done": order_done,
        }

    def order_production_done(self, order_id: int) -> bool:
        """Đơn XONG sản xuất (suy ra): có ≥1 lệnh và MỌI lệnh (không hủy) đều XONG."""
        lenhs = [l for l in self.repo.lenh_by_order(order_id) if l.trang_thai != LENH_HUY]
        return bool(lenhs) and all(l.trang_thai == LENH_XONG for l in lenhs)

    def huy_lenh(self, *, lenh_id: int) -> LenhSanXuat:
        """Hủy 1 lệnh (§GIẢ ĐỊNH — hủy giữa chừng chi tiết P1): đánh dấu HUY, giữ mọi bản ghi log.

        Record-only: KHÔNG rollback sản lượng/bàn giao/QC (dữ liệu lịch sử giữ để truy). Không cho hủy
        khi đã XONG (đã nhập kho thành phẩm).
        """
        lenh = self._get_lenh(lenh_id)
        if lenh.trang_thai == LENH_XONG:
            raise LenhSXConflict("Lệnh đã xong (đã nhập kho) — không hủy")
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
        """Lệnh + tờ in chứa nó + log sản lượng/bàn giao/QC + đích SL & Σ đạt — nuôi màn tracking."""
        lenh = self._get_lenh(lenh_id)
        return {
            "lenh": lenh,
            "routing": self.repo.routing_by_lenh(lenh_id),
            "forms": self.repo.forms_of_lenh(lenh_id),
            "san_luong": self.repo.san_luong_by_lenh(lenh_id),
            "ban_giao": self.repo.ban_giao_by_lenh(lenh_id),
            "qc": self.repo.qc_by_lenh(lenh_id),
            "muc_tieu_sl": self._muc_tieu_sl(lenh),
            "tong_dat": self.repo.sum_dat(lenh_id),
        }

    def san_luong_of(self, lenh_id: int) -> list:
        self._get_lenh(lenh_id)
        return self.repo.san_luong_by_lenh(lenh_id)

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

    # ================================================================= TỔ VIEW (§13.3–13.4)
    def to_board(self) -> list[dict]:
        """Cây tổ SẢN XUẤT + đếm việc: mỗi tổ kèm số lệnh ĐANG CHẠY 'của tổ' (`so_lenh`) và số lệnh
        ĐẾN LƯỢT tổ (`so_den_luot` = bước hiện hành thuộc tổ) — để chủ xưởng NHÌN xưởng đang làm gì.
        Máy CHỈ đếm, không phán. Cây do FE dựng từ `parent_id` (một nguồn sự thật §13.1)."""
        depts = DepartmentRepository(self.db).production_departments()
        live, _ = self.repo.list_lenh(trang_thai=LENH_DANG_CHAY, size=200)
        steps = self.repo.routing_steps_by_lenh_ids([l.id for l in live])
        by_lenh: dict[int, list[RoutingStep]] = {}
        for s in steps:
            by_lenh.setdefault(s.lenh_sx_id, []).append(s)
        so_lenh: dict[int, int] = {}       # tổ có ≥1 bước trên 1 lệnh đang chạy
        so_den_luot: dict[int, int] = {}   # bước đến lượt (hiện hành) thuộc tổ
        for rs in by_lenh.values():
            cur_id = self._current_step_id(rs)  # rs đã theo thu_tu asc từ repo
            for t in {s.to_id for s in rs if s.to_id is not None}:
                so_lenh[t] = so_lenh.get(t, 0) + 1
            cur = next((s for s in rs if s.id == cur_id), None) if cur_id else None
            if cur is not None and cur.to_id is not None:
                so_den_luot[cur.to_id] = so_den_luot.get(cur.to_id, 0) + 1
        return [
            {
                "id": d.id, "name": d.name, "code": d.code, "parent_id": d.parent_id,
                "head_user_id": d.head_user_id, "la_san_xuat": d.la_san_xuat,
                "so_lenh": so_lenh.get(d.id, 0), "so_den_luot": so_den_luot.get(d.id, 0),
            }
            for d in depts
        ]

    def lenh_of_to(self, to_id: int) -> list[dict]:
        """Lệnh 'của tổ' (§13.4): lệnh đã phát (đang chạy/xong) có ≥1 bước routing thuộc tổ. Kèm bước
        ĐẾN LƯỢT (ai đang giữ) + cờ `den_luot` (đến lượt tổ này) + tiến độ. Đến-lượt lên đầu."""
        out: list[dict] = []
        for lid in self.repo.lenh_ids_for_to(to_id):
            lenh = self.repo.get_lenh(lid)
            if lenh is None or lenh.trang_thai in (LENH_NHAP, LENH_HUY):
                continue  # chưa phát / đã hủy → không xuống tổ
            rs = self.repo.routing_by_lenh(lid)
            cur_id = self._current_step_id(rs)
            cur = next((s for s in rs if s.id == cur_id), None) if cur_id else None
            out.append({
                "id": lenh.id, "order_id": lenh.order_id,
                "phieu_thanh_phan_id": lenh.phieu_thanh_phan_id, "trang_thai": lenh.trang_thai,
                "den_luot": bool(cur is not None and cur.to_id == to_id),
                "cur_thu_tu": cur.thu_tu if cur else None,
                "cur_ten": cur.ten if cur else None,
                "cur_to_id": cur.to_id if cur else None,
                "so_buoc": len(rs),
                "so_buoc_xong": sum(1 for s in rs if s.trang_thai == RS_XONG),
                "muc_tieu_sl": self._muc_tieu_sl(lenh),
                "tong_dat": self.repo.sum_dat(lid),
                "updated_at": lenh.updated_at,
            })
        # đến lượt trước → đang chạy → xong; trong nhóm: mới cập nhật lên đầu
        rank = {LENH_DANG_CHAY: 0, LENH_XONG: 1}
        out.sort(key=lambda r: (
            0 if r["den_luot"] else 1,
            rank.get(r["trang_thai"], 9),
            -(r["updated_at"].timestamp() if r["updated_at"] else 0),
        ))
        return out
