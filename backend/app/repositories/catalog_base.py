"""Nền chung cho các repository DANH MỤC (`kho_hang`, `bu_hao`, `khuon_be`, `don_vi_do`,
`loai_san_pham`, `may_thiet_bi`, `cong_doan`…).

Vì sao có file này: tám repo danh mục viết đi viết lại đúng một khuôn — `list()` (đếm + lọc +
cắt trang), `find_by_ma()` (chuẩn hoá mã rồi so không phân biệt hoa/thường), `create/update`
(gán các cột được phép ghi rồi commit), `delete()`. Chỗ khác nhau chỉ là MODEL, danh sách cột
ghi được và vài bộ lọc riêng. Gom vào đây thì sửa một lần ăn cả họ (ví dụ trần `size`, hay cách
`next_ma` lọc ở SQL thay vì kéo cả cột về Python).

CÁCH DÙNG — repo con chỉ khai thuộc tính, không chép lại thân hàm::

    class KhoHangRepository(CatalogRepo):
        model = KhoHang
        fields = ("ten", "vi_tri", "ghi_chu", "active")
        ma_prefix = "KHO-"

Ba điểm mở rộng, dùng khi danh mục có nét riêng — KHÔNG nhồi thêm cờ vào nền:

* `extra_conds(**kw)` — bộ lọc riêng của màn (`ho`, `tinh_trang`, `loai_may`, `nhom`,
  `structural_type`…). Nhận đúng các keyword lạ mà `list()` được gọi kèm.
* `_base_select()` — câu SELECT gốc, để repo cần nạp kèm quan hệ (`selectinload`) chèn options.
* `_sau_gan(obj, data)` — chạy sau khi gán xong `fields`, trước khi commit; dành cho bảng con
  (ví dụ định mức đầu việc của công đoạn).

⚠️ HOA/THƯỜNG CỦA MÃ: mỗi danh mục có quy ước RIÊNG và cả hai đều đúng — `kho_hang`/`bu_hao`/
`khuon_be` ghi mã HOA và tra bằng `upper()`, `don_vi_do` ghi mã thường và tra bằng `lower()`.
Cờ `ma_case` giữ nguyên quy ước của từng cái. ĐỪNG "đồng bộ" chúng về một kiểu: mã đơn vị đã
nằm trong dữ liệu sống (`cong_doan.don_vi_vao/ra`, công thức tính giá) dưới dạng chữ thường.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

# Trần số dòng một trang — chặn client gõ `?size=99999` để kéo cả bảng về.
SIZE_TRAN = 200


class CatalogRepo:
    """Khuôn CRUD của một danh mục. Repo con khai `model` + `fields` là chạy được."""

    # -- khai báo của repo con --
    model: ClassVar[Any] = None
    """Model SQLAlchemy của danh mục. BẮT BUỘC khai."""

    fields: ClassVar[tuple[str, ...]] = ()
    """Các cột client được phép ghi. `ma` KHÔNG nằm đây — nó đi đường chuẩn hoá riêng."""

    search_fields: ClassVar[tuple[str, ...]] = ("ma", "ten")
    """Các cột đưa vào ô tìm `q` (so `LIKE` sau khi hạ chữ thường)."""

    ma_prefix: ClassVar[str | None] = None
    """Tiền tố mã tự sinh (`"KHO-"`, `"KB-"`). None = danh mục khai mã tay, không có `next_ma`."""

    ma_case: ClassVar[str] = "upper"
    """`"upper"` | `"lower"` — chuẩn hoá mã lúc GHI và lúc TRA. Xem cảnh báo ở docstring module."""

    order_cols: ClassVar[tuple[str, ...]] = ("ma",)
    """Thứ tự sắp xếp mặc định của `list()`."""

    commit_on_write: ClassVar[bool] = True
    """False = chỉ `flush()`, để nơi gọi tự chốt bằng `chot_giao_dich()`.

    Tắt cờ này cho danh mục nào thì việc ghi bản ghi và việc ghi NHẬT KÝ của nó đi chung MỘT giao
    dịch (xem `services/catalog_base.CatalogService`): audit nổ ⇒ bản ghi cũng không vào, thay vì
    "mất vết mà bản ghi vẫn nằm đó". Bật/tắt được từng repo một — nền service chạy đúng với cả
    hai chế độ."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- chuẩn hoá mã -----------------------------------------------------------------

    def _chuan_ma(self, ma: str | None) -> str:
        """Mã sau khi bỏ khoảng trắng thừa và đưa về đúng hoa/thường của danh mục."""
        ma = (ma or "").strip()
        return ma.lower() if self.ma_case == "lower" else ma.upper()

    def _cot_ma_chuan(self):
        """Biểu thức SQL đưa cột `ma` về cùng hoa/thường với `_chuan_ma` để so sánh.

        CỐ Ý không bọc `trim()`: `create/update` đã `.strip()` mã trước khi ghi nên trong DB
        không có mã dính khoảng trắng, mà `trim(x)` thì Postgres parse đặc biệt chứ không phải
        hàm thường — thêm vào là rước rủi ro cho một ca không tồn tại.
        """
        col = self.model.ma
        return func.lower(col) if self.ma_case == "lower" else func.upper(col)

    # -- đọc --------------------------------------------------------------------------

    def get(self, item_id: int):
        return self.db.get(self.model, item_id)

    def find_by_ma(self, ma: str):
        ma = self._chuan_ma(ma)
        if not ma:
            return None
        return self.db.execute(
            select(self.model).where(self._cot_ma_chuan() == ma)
        ).scalars().first()

    def next_ma(self) -> str:
        """Mã kế tiếp `<tiền tố>####` tính trên MỌI hàng (kể cả đã xóa mềm) → không đụng mã cũ
        đã kẹt trong DB (`ma` unique). Chỉ tăng, chấp nhận có khoảng trống.

        Lọc `LIKE '<tiền tố>%'` NGAY Ở SQL rồi mới regex trên tập nhỏ. Trước 15/08/2026 hàm này
        kéo TOÀN BỘ cột `ma` của danh mục về Python rồi mới lọc — mã kế tiếp ra y hệt, nhưng
        phải tải cả bảng chỉ để lấy một con số. `LIKE` so trên `upper()`/`lower()` nên mã lỡ
        viết sai hoa/thường vẫn được kể vào, y như bản cũ.
        """
        if not self.ma_prefix:
            raise NotImplementedError(
                f"{type(self).__name__} không khai `ma_prefix` — danh mục này khai mã tay."
            )
        rx = re.compile(rf"^{re.escape(self.ma_prefix)}(\d+)$")
        stmt = select(self.model.ma).where(self._cot_ma_chuan().like(f"{self.ma_prefix}%"))
        mx = 0
        for ma in self.db.execute(stmt).scalars():
            m = rx.match(self._chuan_ma(ma))
            if m:
                mx = max(mx, int(m.group(1)))
        return f"{self.ma_prefix}{mx + 1:04d}"

    def _loc_q(self, q: str | None):
        """Điều kiện của ô tìm — dùng chung cho `list` và các hàm ĐẾM THEO NHÓM (facets) để số
        dòng trong bảng và số trên tab không bao giờ nói hai chuyện khác nhau."""
        if not q:
            return None
        like = f"%{q.strip().lower()}%"
        return or_(*(func.lower(getattr(self.model, c)).like(like) for c in self.search_fields))

    def extra_conds(self, **kw) -> list:
        """Bộ lọc riêng của danh mục con. Mặc định: không có. Xem `khuon_be_repo` làm mẫu."""
        return []

    def _base_select(self):
        """SELECT gốc của `list()` — repo con ghi đè để chèn `selectinload` cho quan hệ con."""
        return select(self.model)

    def _dieu_kien(self, *, q: str | None, active: bool | None, **kw) -> list:
        conds = []
        loc_q = self._loc_q(q)
        if loc_q is not None:
            conds.append(loc_q)
        if active is not None:
            conds.append(self.model.active.is_(active))
        conds.extend(self.extra_conds(**kw))
        return conds

    def list(self, *, q: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50, **kw):
        """`(danh sách dòng của trang, TỔNG số dòng khớp lọc)`.

        Cắt trang và lọc đều Ở MÁY CHỦ — `total` là tổng THẬT chứ không phải `len(items)`.
        """
        conds = self._dieu_kien(q=q, active=active, **kw)
        base = self._base_select()
        count_stmt = select(func.count()).select_from(self.model)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, SIZE_TRAN))
        base = base.order_by(*(getattr(self.model, c).asc() for c in self.order_cols))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # -- ghi --------------------------------------------------------------------------

    def _gan(self, obj, data: dict) -> None:
        """Gán các cột được phép ghi. Khoá VẮNG trong `data` thì giữ nguyên giá trị cũ —
        nhờ vậy `PATCH` một phần không xoá trắng các cột không gửi lên."""
        for k in self.fields:
            if k in data:
                setattr(obj, k, data[k])

    def _sau_gan(self, obj, data: dict) -> None:
        """Chạy sau `_gan`, trước khi chốt — cho repo có bảng con phải thay theo (mặc định: không)."""

    def _chot(self, obj=None):
        if self.commit_on_write:
            self.db.commit()
        else:
            self.db.flush()
        if obj is not None:
            self.db.refresh(obj)
        return obj

    def chot_giao_dich(self) -> None:
        """Chốt giao dịch khi nơi gọi (service) làm chủ — xem `commit_on_write`.

        Có mặt để service KHÔNG phải với tay vào `repo.db` mà commit: đó là việc của tầng repo.
        Repo còn `commit_on_write = True` thì đây là no-op (nó đã commit trong `create/update/
        delete` rồi), nên service gọi vô điều kiện được.
        """
        if not self.commit_on_write:
            self.db.commit()

    def create(self, data: dict):
        obj = self.model(ma=self._chuan_ma(data["ma"]))
        self._gan(obj, data)
        self._sau_gan(obj, data)
        self.db.add(obj)
        return self._chot(obj)

    def update(self, obj, data: dict):
        if data.get("ma"):
            obj.ma = self._chuan_ma(data["ma"])
        self._gan(obj, data)
        self._sau_gan(obj, data)
        return self._chot(obj)

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self._chot()
