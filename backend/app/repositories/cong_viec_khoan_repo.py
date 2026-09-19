"""Repository — Danh mục "Công việc khoán" (bảng `piece_rates`). CRUD + lọc theo tổ + đếm tab.

Bảng này đã có từ trước dưới tên "đơn giá khoán" và vẫn là bảng giá mà Lương khoán tra; đợt
17/08/2026 chỉ chuyển CHỖ KHAI về Cấu hình danh mục. Vì vậy ở đây không dựng bảng mới, chỉ cho nó
đi vào nền `CatalogRepo` như 8 repo danh mục kia.

Mọi đường GHI vào `piece_rates` đi qua đây — hai đường ghi thì đường nào không qua `CongViecKhoanService` sẽ không
ghi nhật ký, và tab Nhật ký của màn lặng lẽ thiếu dòng.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from ..models.department import Department
from ..models.don_vi_do import DonViDo
from ..models.piece_work import CongViecKhoanTo, PieceRate, ViecPhatSinh
from .catalog_base import CatalogRepo
from .tim_khong_dau import like_khong_dau

# `department_ids` là DANH SÁCH tổ (bảng nối `cong_viec_khoan_to`) — setter ở model thay trọn danh
# sách, nên `_gan` gán thẳng như một cột.
ASSIGNABLE = ("ten", "department_ids", "unit", "unit_price", "cong_thuc_khoan", "note", "active")


class CongViecKhoanRepository(CatalogRepo):
    model = PieceRate
    fields = ASSIGNABLE
    commit_on_write = False   # `CongViecKhoanService` chốt sau khi ghi nhật ký — xem `catalog_base`
    # Mã do MÁY cấp (`KH-0001`…) — xưởng không gõ mã cho từng dòng đơn giá. Mã đời cũ của bảng giấy
    # (A–F, `BE-01`, `XEN-01`) giữ nguyên: `next_ma` chỉ đếm các mã đúng khuôn `KH-####`.
    ma_prefix = "KH-"
    # Trước 17/09/2026 gom theo nhãn tổ trên dòng; một việc nay thuộc NHIỀU tổ nên không còn một
    # trục gom duy nhất — đọc theo tổ thì bấm tab tổ đó.
    order_cols = ("ma",)

    def _loc_q(self, q: str | None):
        """Ô tìm TƯƠNG ĐỐI: bỏ dấu cả hai phía nên gõ `can mang` ra "Cán màng" (18/09/2026).

        Ghi đè `CatalogRepo._loc_q` (chỉ `lower().like()`) chứ không sửa nền: 12 màn danh mục kia
        chưa có yêu cầu này, và phép bỏ dấu bằng REPLACE lồng thì không nên áp cho bảng lớn khi
        chưa ai cần. Dùng CHUNG một hàm với ô tìm việc khoán ở bàn tổ để hai chỗ khớp giống nhau.
        """
        if not q:
            return None
        dk = [like_khong_dau(getattr(self.model, c), q) for c in self.search_fields]
        return or_(*[d for d in dk if d is not None])

    def _base_select(self):
        """Nạp kèm việc phát sinh + tổ — cột "Việc phát sinh" và "Tổ" của bảng vẽ cho MỌI dòng trên
        trang, để lazy là mỗi dòng một truy vấn."""
        return select(PieceRate).options(
            selectinload(PieceRate.viec_phat_sinh), selectinload(PieceRate.to_lam))

    def _sau_gan(self, obj: PieceRate, data: dict) -> None:
        self._khop_viec_phat_sinh(obj, data)

    @staticmethod
    def _khop_viec_phat_sinh(obj: PieceRate, data: dict) -> None:
        """Khớp danh sách VIỆC PHÁT SINH theo id — sửa tại chỗ, không xoá-rồi-chèn lại.

        Khoá `viec_phat_sinh` VẮNG (nhập Excel, `dat_active`, client không biết tới việc phát sinh)
        ⇒ giữ nguyên. Có mặt ⇒ đó là TRỌN danh sách: dòng mang id của chính công việc này thì sửa
        đúng hàng đó (id sống qua các lần lưu — sau này sản xuất trỏ vào id), dòng không id hoặc id
        lạ (của công việc khác) thì chèn mới, hàng cũ không còn trong danh sách thì `delete-orphan`
        xoá. Không có ràng buộc UNIQUE ở DB nên đổi tên chéo hai dòng trong một lần lưu không vấp
        thứ tự INSERT/DELETE của flush (bẫy `_replace_dinh_muc` bên Công đoạn).
        """
        rows = data.get("viec_phat_sinh")
        if not isinstance(rows, list):
            return
        cu = {v.id: v for v in obj.viec_phat_sinh if v.id is not None}
        moi: list[ViecPhatSinh] = []
        for i, r in enumerate(rows):
            v = cu.pop(r.get("id"), None) or ViecPhatSinh()
            v.ten = r["ten"]
            v.don_gia = r["don_gia"]
            v.don_vi = r["don_vi"]
            v.thu_tu = i
            moi.append(v)
        obj.viec_phat_sinh = moi

    def extra_conds(self, *, to: str | None = None, **_) -> list:
        """Lọc theo TỔ — nhận HAI dạng, cố ý:

        * `?to=Tổ Bế & Xén` → TÊN tổ (`departments.name`, duy nhất). Dạng của TAB LỌC trên màn —
          khoá của `dem_theo_to` là tên tổ đọc được.
        * `?to=17` (toàn chữ số) → id tổ. Dạng của panel "Đơn giá khoán của tổ" trong Cấu hình
          lương: nó đứng trong ngữ cảnh MỘT tổ và biết id.

        Cả hai khớp "tổ đó CÓ TRONG danh sách tổ của việc" — việc làm ở hai tổ hiện ở cả hai tab.

        Một tham số hai cách hiểu là có giá, nhưng rẻ hơn hai đường vào: `make_catalog_router` chỉ
        sinh MỘT bộ lọc riêng cho mỗi màn, thêm cái thứ hai là phải khai route thủ công bên ngoài
        factory — và route ngoài factory là chỗ quyền/nhật ký bắt đầu lệch với phần còn lại.
        """
        s = str(to).strip() if to else ""
        if not s:
            return []
        if s.isdigit():
            return [PieceRate.to_lam.any(CongViecKhoanTo.department_id == int(s))]
        ids_theo_ten = select(Department.id).where(Department.name == s)
        return [PieceRate.to_lam.any(CongViecKhoanTo.department_id.in_(ids_theo_ten))]

    def _loc_chung(self, stmt, *, q: str | None, active: bool | None):
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(PieceRate.active.is_(active))
        return stmt

    def dem_theo_to(self, *, q: str | None = None, active: bool | None = None) -> dict[str, int]:
        """Số dòng của TỪNG tổ (khoá = TÊN tổ) — số hiện trên tab lọc. Không áp điều kiện `to` (tab
        đang không được chọn vẫn phải khoe số của nó), nhưng CÓ áp `q` và `active` để số trên tab và
        số dòng trong bảng không bao giờ nói hai chuyện khác nhau.

        Một việc làm ở hai tổ được đếm ở CẢ HAI tab — nên tab "Tất cả" đọc `dem_tong`, không cộng
        các số này. Dòng chưa có tổ nào (hoặc chỉ trỏ tổ đã xoá) gom vào khoá rỗng "".
        """
        stmt = self._loc_chung(
            select(Department.name, func.count(func.distinct(PieceRate.id)))
            .select_from(PieceRate)
            .join(CongViecKhoanTo, CongViecKhoanTo.piece_rate_id == PieceRate.id)
            .join(Department, Department.id == CongViecKhoanTo.department_id)
            .group_by(Department.name),
            q=q, active=active)
        ra = {str(ten).strip(): int(n) for ten, n in self.db.execute(stmt) if ten}
        co_to_that = (select(CongViecKhoanTo.piece_rate_id)
                      .join(Department, Department.id == CongViecKhoanTo.department_id))
        khong_to = self.db.execute(self._loc_chung(
            select(func.count()).select_from(PieceRate).where(PieceRate.id.not_in(co_to_that)),
            q=q, active=active)).scalar_one()
        if khong_to:
            ra[""] = int(khong_to)
        return ra

    def dem_tong(self, *, q: str | None = None, active: bool | None = None) -> int:
        """Tổng dòng khớp ô tìm (bỏ qua tab tổ) — số của tab "Tất cả", đếm mỗi việc MỘT lần."""
        return int(self.db.execute(self._loc_chung(
            select(func.count()).select_from(PieceRate), q=q, active=active)).scalar_one())

    def ten_don_vi(self, mas: set[str]) -> dict[str, str]:
        """`{mã đơn vị: tên đọc được}` cho các mã CÓ THẬT trong danh mục Đơn vị.

        Một truy vấn cho cả trang. Mã không có trong danh mục thì KHÔNG có khoá — màn phân biệt
        được "chưa khai đơn vị" với "khai một mã lạ" (hai ca cần hai câu trả lời khác nhau).
        So không phân biệt hoa/thường vì mã đơn vị lưu chữ thường (xem `don_vi_do_repo.ma_case`).
        """
        mas = {m.strip().lower() for m in mas if (m or "").strip()}
        if not mas:
            return {}
        rows = self.db.execute(
            select(DonViDo.ma, DonViDo.ten).where(func.lower(DonViDo.ma).in_(mas))
        ).all()
        return {str(ma).strip().lower(): str(ten) for ma, ten in rows}

    # ⚠️ `cong_doan_khai_viec()` GỠ 18/09/2026 (mg `0320`): công đoạn thôi khai đầu việc nên không
    #    còn ai trỏ vào `piece_rates` từ bên đó. Tổ không có việc khoán nay bị chặn ở CỔNG
    #    "Sẵn sàng lập kế hoạch" của lệnh (`lsx_service.thieu_cua` → `thieu_viec_khoan_to`), đúng
    #    chỗ hậu quả xảy ra.

    def theo_to(self, department_id: int | None, *, chi_active: bool = True) -> list[PieceRate]:
        """Các công việc khoán của MỘT tổ, nạp kèm việc phát sinh — bàn tổ bày cho thợ chọn lúc ghi mẻ.

        Lọc tổ ở SQL (bảng nối `cong_viec_khoan_to`) chứ không kéo cả bảng về rồi lọc trong Python:
        một tổ có 1-17 việc mà bảng đã hơn trăm dòng. Luật khớp chỉ một dòng — tổ nằm trong danh
        sách tổ làm việc.

        `chi_active`: mẻ MỚI chỉ chọn được việc còn dùng; băng "Danh mục đã đổi" của mẻ cũ thì gọi
        `False` để còn đọc được việc đã ngừng mà mẻ đang trỏ.
        """
        if department_id is None:
            return []
        stmt = (
            select(PieceRate)
            .join(CongViecKhoanTo, CongViecKhoanTo.piece_rate_id == PieceRate.id)
            .where(CongViecKhoanTo.department_id == int(department_id))
            .options(selectinload(PieceRate.viec_phat_sinh))
            .order_by(PieceRate.ma, PieceRate.id)
        )
        if chi_active:
            stmt = stmt.where(PieceRate.active.is_(True))
        return list(self.db.execute(stmt).scalars().unique())

    def phat_sinh_theo_id(self, ids) -> dict[int, ViecPhatSinh]:
        """`{id: dòng việc phát sinh}` cho các id CÓ THẬT — một truy vấn. Id vắng = đã xoá khỏi
        danh mục, băng của mẻ nói thẳng "đã xoá khỏi danh mục" chứ không tự gỡ khỏi mẻ."""
        ids = {int(i) for i in ids if i is not None}
        if not ids:
            return {}
        rows = self.db.execute(
            select(ViecPhatSinh).where(ViecPhatSinh.id.in_(ids))
        ).scalars().all()
        return {int(r.id): r for r in rows}

    def to_theo_id(self, ids) -> dict[int, tuple[str | None, str]]:
        """`{id tổ: (mã, tên)}` cho các id CÓ THẬT trong cây tổ chức — một truy vấn cho cả trang.

        Id vắng trong kết quả = tổ đã bị xoá: service dùng để chặn chọn tổ không có thật, và màn
        dùng để đánh dấu tổ cũ cần gỡ.
        """
        ids = {int(i) for i in ids if i is not None}
        if not ids:
            return {}
        rows = self.db.execute(
            select(Department.id, Department.code, Department.name).where(Department.id.in_(ids))
        ).all()
        return {int(i): (str(ma) if ma else None, str(ten or "")) for i, ma, ten in rows}
