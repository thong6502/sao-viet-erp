"""Repository — Danh mục "Công việc khoán" (bảng `piece_rates`). CRUD + lọc theo tổ + đếm tab.

Bảng này đã có từ trước dưới tên "đơn giá khoán" và vẫn là bảng giá mà Lương khoán tra; đợt
17/08/2026 chỉ chuyển CHỖ KHAI về Cấu hình danh mục. Vì vậy ở đây không dựng bảng mới, chỉ cho nó
đi vào nền `CatalogRepo` như 8 repo danh mục kia.

Mọi đường GHI vào `piece_rates` đi qua đây — hai đường ghi thì đường nào không qua `CongViecKhoanService` sẽ không
ghi nhật ký, và tab Nhật ký của màn lặng lẽ thiếu dòng.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..models.don_vi_do import DonViDo
from ..models.piece_work import PieceRate, ViecPhatSinh
from .catalog_base import CatalogRepo

ASSIGNABLE = (
    "ten", "group_name", "department_id", "unit", "unit_price", "note", "active",
)


class CongViecKhoanRepository(CatalogRepo):
    model = PieceRate
    fields = ASSIGNABLE
    commit_on_write = False   # `CongViecKhoanService` chốt sau khi ghi nhật ký — xem `catalog_base`
    # Mã do MÁY cấp (`KH-0001`…) — xưởng không gõ mã cho từng dòng đơn giá. Mã đời cũ của bảng giấy
    # (A–F, `BE-01`, `XEN-01`) giữ nguyên: `next_ma` chỉ đếm các mã đúng khuôn `KH-####`.
    ma_prefix = "KH-"
    # Gom theo TỔ rồi mới tới mã: bảng này người ta đọc theo tổ ("tổ Bế có những việc gì"), không
    # đọc theo thứ tự mã.
    order_cols = ("group_name", "ma")

    def _base_select(self):
        """Nạp kèm việc phát sinh — cột "Việc phát sinh" của bảng vẽ tên các việc con cho MỌI dòng
        trên trang, để lazy là mỗi dòng một truy vấn."""
        return select(PieceRate).options(selectinload(PieceRate.viec_phat_sinh))

    def _sau_gan(self, obj: PieceRate, data: dict) -> None:
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

        * `?to=Tổ Bế & Xén` → so `group_name`. Đây là dạng của TAB LỌC trên màn: nhãn tổ đọc được,
          và dòng đời cũ chưa gắn `department_id` nào vẫn nằm trong một tab có tên.
        * `?to=17` (toàn chữ số) → so `department_id`. Dạng của panel "Đơn giá khoán của tổ" trong
          Cấu hình lương: nó đứng trong ngữ cảnh MỘT tổ và biết id, so bằng id thì không bao giờ
          hụt dòng vì nhãn lệch một chữ.

        Một tham số hai cách hiểu là có giá, nhưng rẻ hơn hai đường vào: `make_catalog_router` chỉ
        sinh MỘT bộ lọc riêng cho mỗi màn, thêm cái thứ hai là phải khai route thủ công bên ngoài
        factory — và route ngoài factory là chỗ quyền/nhật ký bắt đầu lệch với phần còn lại.
        """
        s = str(to).strip() if to else ""
        if not s:
            return []
        if s.isdigit():
            return [PieceRate.department_id == int(s)]
        return [PieceRate.group_name == s]

    def dem_theo_to(self, *, q: str | None = None, active: bool | None = None) -> dict[str, int]:
        """Số dòng của TỪNG tổ — số hiện trên tab lọc. Không áp điều kiện `to` (tab đang không được
        chọn vẫn phải khoe số của nó), nhưng CÓ áp `q` và `active` để số trên tab và số dòng trong
        bảng không bao giờ nói hai chuyện khác nhau."""
        stmt = select(PieceRate.group_name, func.count()).group_by(PieceRate.group_name)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(PieceRate.active.is_(active))
        # Tổ khuyết gom vào khoá rỗng "" (xem `cong_doan_repo.dem_theo_nhom`).
        return {(str(g).strip() if g is not None else ""): int(n)
                for g, n in self.db.execute(stmt)}

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

    def ten_to(self, department_id: int | None) -> str | None:
        """Tên tổ hiện tại (`departments.name`), hoặc None nếu id không có thật.

        Service gọi lúc ghi để `group_name` luôn là tên tổ ĐANG dùng — nhãn tự khai một lần rồi
        không ai cập nhật là chỗ dữ liệu bắt đầu lệch với cây tổ chức.
        """
        if department_id is None:
            return None
        from ..models.department import Department

        ten = self.db.execute(
            select(Department.name).where(Department.id == department_id)
        ).scalar_one_or_none()
        return str(ten) if ten else None
