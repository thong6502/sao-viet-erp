"""Repository — Danh mục Đơn vị đo + CẶP quy đổi. CRUD + tra theo mã + liệt kê loại đo đã dùng."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from ..models.don_vi_do import DonViDo, DonViQuyDoi
from .catalog_base import CatalogRepo

_FIELDS = ("ten", "ho", "hieu_luc_tu", "ghi_chu", "active", "dung_lam_toc_do",
           "tram_dong_giay", "cong_thuc")
# `cong_thuc` KHÔNG còn trong danh sách ghi được của CẶP (14/08/2026) — cặp chỉ mang hệ số cố định.
# Cột `don_vi_do.cong_thuc` ở `_FIELDS` là chuyện khác: đó là CÁCH ĐO của chính đơn vị, trả LƯỢNG.
_CAP_FIELDS = ("tu_id", "den_id", "he_so", "ghi_chu")


@dataclass
class CapRow:
    """1 cặp quy đổi KÈM MÃ hai đầu — `quy_doi_service` là hàm thuần nên không tự truy DB được."""

    id: int
    tu_id: int
    den_id: int
    tu_ma: str
    den_ma: str
    tu_ten: str
    den_ten: str
    he_so: float
    ghi_chu: str | None = None


class DonViDoRepository(CatalogRepo):
    model = DonViDo
    fields = _FIELDS
    # Mã đơn vị viết THƯỜNG (`kg`, `to`, `m2`) — khác 6 danh mục còn lại. Không phải nhầm lẫn:
    # mã này nằm nguyên trong dữ liệu sống (`cong_doan.don_vi_vao/ra`, công thức tính giá,
    # `giay.don_vi_gia`) nên đổi sang HOA là vỡ hết chỗ so mã. Ghi và tra đều `lower()`.
    ma_case = "lower"
    # Xếp theo HỌ trước rồi mới tới mã: bảng gom `kg · g · tấn` liền nhau chứ không trộn lẫn.
    order_cols = ("ho", "ma")
    # `DonViDoService` chốt sau khi ghi nhật ký — xem `services/catalog_base`. Chỉ áp cho CRUD của
    # ĐƠN VỊ; ba hàm `*_cap` bên dưới là bảng khác và vẫn tự commit.
    commit_on_write = False

    def extra_conds(self, *, ho: str | None = None, **_) -> list:
        return [func.lower(DonViDo.ho) == ho.strip().lower()] if ho else []

    def all_active(self) -> list[DonViDo]:
        """Đơn vị ĐANG DÙNG — cho Ô CHỌN: không mời người ta gán mới thứ đã ngừng.

        Tra cứu / dựng lại số của chứng từ cũ thì dùng `all_rows()`, ĐỪNG dùng hàm này.
        """
        return list(
            self.db.execute(
                select(DonViDo).where(DonViDo.active.is_(True)).order_by(DonViDo.ho, DonViDo.ma)
            ).scalars()
        )

    def all_rows(self) -> list[DonViDo]:
        """Toàn bộ đơn vị, KỂ CẢ đã ngừng dùng — cho đường ĐỌC / tra cứu.

        Đơn vị ngừng dùng mà chứng từ cũ còn trỏ tới thì vẫn phải đổi ra số và hiện ra tên. Lọc
        `active` ở đường đọc là làm tiền khoán của lệnh lịch sử tụt về rỗng và cột ĐVT trống trơn —
        cùng một luật đã chốt cho lương 27/07 (`payroll_service.py:501`): ngừng áp dụng thì chặn
        GÁN MỚI, không chặn ĐỌC LẠI.
        """
        return list(
            self.db.execute(select(DonViDo).order_by(DonViDo.ho, DonViDo.ma)).scalars()
        )

    def distinct_ho(self) -> list[str]:
        """Họ đã có trong dữ liệu — gợi ý cho ô "Họ" (form MỞ, không phải whitelist)."""
        rows = self.db.execute(
            select(DonViDo.ho).where(DonViDo.ho.is_not(None)).distinct()
        ).scalars()
        return sorted({(h or "").strip() for h in rows if (h or "").strip()})

    # --- cặp quy đổi ---------------------------------------------------------

    def cap_rows(self, *, bo_qua_id: int | None = None) -> list[CapRow]:
        """Mọi cặp kèm mã/tên hai đầu. `bo_qua_id` để dò đường KHÔNG tính cặp đang sửa (nếu tính,
        nó tự mâu thuẫn với chính bản cũ của mình)."""
        tu, den = aliased(DonViDo), aliased(DonViDo)
        stmt = (
            select(DonViQuyDoi.id, DonViQuyDoi.tu_id, DonViQuyDoi.den_id,
                   tu.ma, den.ma, tu.ten, den.ten, DonViQuyDoi.he_so, DonViQuyDoi.ghi_chu)
            .join(tu, tu.id == DonViQuyDoi.tu_id)
            .join(den, den.id == DonViQuyDoi.den_id)
            .order_by(tu.ma.asc(), den.ma.asc())
        )
        if bo_qua_id is not None:
            stmt = stmt.where(DonViQuyDoi.id != bo_qua_id)
        return [
            CapRow(id=r[0], tu_id=r[1], den_id=r[2], tu_ma=r[3], den_ma=r[4],
                   tu_ten=r[5], den_ten=r[6], he_so=float(r[7]), ghi_chu=r[8])
            for r in self.db.execute(stmt).all()
        ]

    def list_cap(self, *, q: str | None = None, page: int = 1, size: int = 50):
        rows = self.cap_rows()
        if q:
            needle = q.strip().lower()
            rows = [r for r in rows
                    if needle in f"{r.tu_ma} {r.den_ma} {r.tu_ten} {r.den_ten}".lower()]
        total = len(rows)
        page, size = max(1, page), max(1, min(size, 200))
        return rows[(page - 1) * size: (page - 1) * size + size], total

    def get_cap(self, cap_id: int):
        return self.db.get(DonViQuyDoi, cap_id)

    def find_cap(self, tu_id: int, den_id: int):
        """Cặp giữa hai đơn vị theo CHIỀU NÀO CŨNG TÍNH — khai `tấn → kg` rồi khai tiếp `kg → tấn`
        là hai dòng nói cùng một chuyện, sớm muộn lệch nhau."""
        return self.db.execute(
            select(DonViQuyDoi).where(
                or_(
                    (DonViQuyDoi.tu_id == tu_id) & (DonViQuyDoi.den_id == den_id),
                    (DonViQuyDoi.tu_id == den_id) & (DonViQuyDoi.den_id == tu_id),
                )
            )
        ).scalars().first()


    def cong_doan_lay_lam_don_vi_ra(self, ma: str) -> list[str]:
        """Tên công đoạn đang lấy `ma` làm ĐƠN VỊ RA, và CẢ HAI vế đều ngoài dòng giấy.

        Dùng để chặn chiều ngược của luật vòng tròn: công đoạn khai xong xuôi rồi mới có người vào
        sửa công thức của đơn vị thêm `sl_vao`. Chỉ kể ca hai-vế-ngoài-dòng vì chỉ ở đó công thức
        của đơn vị RA mới được đọc.
        """
        from ..models.cong_doan import CongDoan
        from ..models.don_vi_do import DonViDo

        if not ma:
            return []
        tram = {d.ma: d.tram_dong_giay for d in self.db.execute(select(DonViDo)).scalars()}
        ra: list[str] = []
        for cd in self.db.execute(
            select(CongDoan).where(CongDoan.don_vi_ra == ma)
        ).scalars():
            if tram.get(cd.don_vi_vao) is None and tram.get(cd.don_vi_ra) is None:
                ra.append(cd.ten)
        return ra

    def create_cap(self, data: dict):
        obj = DonViQuyDoi(tu_id=data["tu_id"], den_id=data["den_id"], he_so=data["he_so"])
        if "ghi_chu" in data:
            obj.ghi_chu = data["ghi_chu"]
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update_cap(self, obj, data: dict):
        for k in _CAP_FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete_cap(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()
