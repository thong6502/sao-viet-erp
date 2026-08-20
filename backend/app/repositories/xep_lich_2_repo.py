"""Repository Xếp lịch 2 — TRUY VẤN riêng của lớp v2, ĐÈ LÊN kho chung `xep_lich_cong_doan`.

Kế thừa `XepLichRepository` (get / by_lsx / add_all / commit… dùng lại nguyên) và chỉ thêm đúng
mấy câu lệnh v2 cần: khoảng đã-xếp trên cùng máy / cùng tổ (TRỪ chính dòng đang xét) để dò trùng
máy và đỉnh quân số. KHÔNG đẻ bảng mới — lưu vẫn vào một bảng lịch THẬT (spec §1: hai cửa, một lịch).
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import Integer, case, cast, exists, func, literal, select, union_all

from ..models.bai_ghep import TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
from ..models.lsx import TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan
from ..models.work_calendar import SpecialDay
from ..models.xep_lich import NGUON_IN_GHEP, NGUON_LSX, TT_DA_XEP, XepLichCongDoan
from .xep_lich_repo import XepLichRepository


class XepLich2Repository(XepLichRepository):
    def da_xep_khac_tren_may(
        self, may_id: int | None, exclude_id: int | None = None,
    ) -> list[XepLichCongDoan]:
        """Dòng đã xếp + có giờ trên CÙNG máy, TRỪ chính dòng đang xét — nền dò `trung_may` (§7.1)."""
        if not may_id:
            return []
        q = select(XepLichCongDoan).where(
            XepLichCongDoan.trang_thai == TT_DA_XEP,
            XepLichCongDoan.may_id == may_id,
            XepLichCongDoan.start_at.is_not(None),
            XepLichCongDoan.finish_at.is_not(None),
        )
        if exclude_id is not None:
            q = q.where(XepLichCongDoan.id != exclude_id)
        return list(self.db.execute(q).scalars())

    def da_xep_trong_khoang(self, tu: date, den: date) -> list[XepLichCongDoan]:
        """Dòng đã xếp có giờ CHẠM cửa sổ [tu, den] — nền vẽ một bàn làm việc (§8)."""
        from datetime import datetime, time, timezone

        dau = datetime.combine(tu, time.min, tzinfo=timezone.utc)
        cuoi = datetime.combine(den, time.max, tzinfo=timezone.utc)
        q = select(XepLichCongDoan).where(
            XepLichCongDoan.trang_thai == TT_DA_XEP,
            XepLichCongDoan.start_at.is_not(None),
            XepLichCongDoan.finish_at.is_not(None),
            XepLichCongDoan.start_at <= cuoi,
            XepLichCongDoan.finish_at >= dau,
        ).order_by(XepLichCongDoan.start_at)
        return list(self.db.execute(q).scalars())

    def nhap_chua_gio(self) -> list[XepLichCongDoan]:
        """Dòng nháp CHƯA đặt giờ (`start_at` rỗng) — không gắn cửa sổ nào vì chưa có ngày.

        Vừa 'Đưa vào kế hoạch' xong, mỗi công đoạn thành một dòng nháp thừa hưởng máy/tổ của routing
        nhưng CHƯA có giờ bắt đầu. Board phải bày chúng ra (chip trong lane máy/tổ hoặc cụm 'Chưa đặt
        giờ') thì người dùng mới xếp được; không trả về là lệnh vừa xếp BỐC HƠI khỏi bàn (§8, §12.10).
        Hiện trên MỌI bàn tới khi được đặt giờ — việc chưa xếp không thuộc tuần nào."""
        q = select(XepLichCongDoan).where(
            XepLichCongDoan.start_at.is_(None),
        ).order_by(XepLichCongDoan.source_thu_tu, XepLichCongDoan.id)
        return list(self.db.execute(q).scalars())

    def ngay_le(self, tu: date, den: date) -> list[SpecialDay]:
        """Ngày lễ/nghỉ trong cửa sổ — v2 chỉ TÔ NỀN + ghi chú, vẫn xếp được (§3, §12.2)."""
        q = select(SpecialDay).where(
            SpecialDay.day >= tu, SpecialDay.day <= den,
        ).order_by(SpecialDay.day)
        return list(self.db.execute(q).scalars())

    def da_xep_khac_theo_to(
        self, department_id: int | None, exclude_id: int | None = None,
    ) -> list[XepLichCongDoan]:
        """Dòng đã xếp + có giờ của MỘT tổ, TRỪ chính dòng đang xét — nền dò `vuot_quan_so_to` (§4)."""
        if not department_id:
            return []
        q = select(XepLichCongDoan).where(
            XepLichCongDoan.trang_thai == TT_DA_XEP,
            XepLichCongDoan.department_id == department_id,
            XepLichCongDoan.start_at.is_not(None),
            XepLichCongDoan.finish_at.is_not(None),
        )
        if exclude_id is not None:
            q = q.where(XepLichCongDoan.id != exclude_id)
        return list(self.db.execute(q).scalars())

    # ================= NHÃN DẪN XUẤT (nạp theo LÔ, tránh N+1) =================
    # Dòng lịch chỉ neo id (lsx_id / bai_ghep_id / *_cong_doan_id) chứ không mang mã/tên. Board cần
    # mã lệnh + tên sản phẩm + tên công đoạn để nhãn thanh đọc được ⇒ gom hết id một lượt rồi tra
    # bốn map dưới đây, KHÔNG join-trong-vòng-lặp (workspace có thể trả cả nghìn dòng).
    @staticmethod
    def _ids(values: Iterable[int | None]) -> list[int]:
        return sorted({v for v in values if v})

    def lsx_map(self, ids: Iterable[int | None]) -> dict[int, Lsx]:
        keys = self._ids(ids)
        if not keys:
            return {}
        q = select(Lsx).where(Lsx.id.in_(keys))
        return {r.id: r for r in self.db.execute(q).scalars()}

    def bai_ghep_map(self, ids: Iterable[int | None]) -> dict[int, BaiGhep]:
        keys = self._ids(ids)
        if not keys:
            return {}
        q = select(BaiGhep).where(BaiGhep.id.in_(keys))
        return {r.id: r for r in self.db.execute(q).scalars()}

    def lsx_cong_doan_ten_map(self, ids: Iterable[int | None]) -> dict[int, str]:
        keys = self._ids(ids)
        if not keys:
            return {}
        q = select(LsxCongDoan.id, LsxCongDoan.ten).where(LsxCongDoan.id.in_(keys))
        return {row_id: ten for row_id, ten in self.db.execute(q)}

    def bai_ghep_cong_doan_ten_map(self, ids: Iterable[int | None]) -> dict[int, str]:
        keys = self._ids(ids)
        if not keys:
            return {}
        q = select(BaiGhepCongDoan.id, BaiGhepCongDoan.ten).where(BaiGhepCongDoan.id.in_(keys))
        return {row_id: ten for row_id, ten in self.db.execute(q)}

    # ================= HÀNG CHỜ — CẮT TRANG + LỌC + ĐẾM Ở MÁY CHỦ (§12.7) ======
    def hang_cho_trang(
        self, *, offset: int, limit: int, q: str | None = None, loc: str = "all",
    ) -> tuple[list[tuple[str, int]], int, dict[str, int]]:
        """Một TRANG hàng chờ — cắt trang + lọc + ĐẾM đều Ở DB (cấm cắt/lọc/đếm ở JS). Gộp hai nguồn —
        LSX độc lập (không thuộc bài ghép) + bài ghép `san_sang` — qua `union_all`, sắp GẤP-trước rồi
        MỚI-trước, RỒI mới offset/limit; hàng chờ trăm nghìn lệnh vẫn chỉ kéo về đúng một trang.

        `q` lọc theo MÃ (ILIKE); `loc` ∈ {all,tre,gap}: `tre` = hạn hoàn thành SX (rơi về hạn giao) đã
        quá hôm nay, `gap` = cờ ưu tiên. Trả `(refs, tong, facets)`:
          · `refs`  = [(nguon, id)] của trang (đã lọc theo q + loc);
          · `tong`  = tổng dòng KHỚP q + loc (để dựng thanh phân trang khớp kết quả đang xem);
          · `facets`= đếm TOÀN hàng chờ theo từng chip {all,tre,gap} — KHÔNG theo q/loc (số gợi ý điều
            hướng, giữ nguyên dù đang tìm/lọc). Rổ vật tư (xếp-được / bị-chặn) do service tính SAU chỉ
            trên số dòng của trang — không quét cả hàng chờ (giữ chỗ là truy vấn đắt)."""
        kw = (q or "").strip()

        # Facets: đếm TOÀN hàng chờ theo từng chip (một lượt quét, KHÔNG theo q/loc).
        u_all = union_all(self._nhanh_lsx(), self._nhanh_bg()).subquery()
        f_all, f_tre, f_gap = self.db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(cast(u_all.c.is_tre, Integer)), 0),
                func.coalesce(func.sum(cast(u_all.c.is_rush, Integer)), 0),
            )
        ).one()
        facets = {"all": int(f_all or 0), "tre": int(f_tre or 0), "gap": int(f_gap or 0)}

        # Trang: q lọc NGAY trong từng nhánh theo mã của CHÍNH bảng đó (id hai nguồn trùng dải nên
        # KHÔNG được gộp id để lọc chéo); loc lọc trên union; rồi mới offset/limit.
        u = union_all(self._nhanh_lsx(kw), self._nhanh_bg(kw)).subquery()
        page = select(u.c.nguon, u.c.id, u.c.is_rush, u.c.created_at)
        if loc == "tre":
            page = page.where(u.c.is_tre.is_(True))
        elif loc == "gap":
            page = page.where(u.c.is_rush.is_(True))
        tong = int(self.db.scalar(select(func.count()).select_from(page.subquery())) or 0)
        rows = self.db.execute(
            page.order_by(u.c.is_rush.desc(), u.c.created_at.desc(), u.c.nguon, u.c.id)
            .offset(max(0, offset))
            .limit(max(1, limit))
        ).all()
        return [(r.nguon, r.id) for r in rows], tong, facets

    def _nhanh_lsx(self, kw: str = ""):
        """Nhánh LSX của hàng chờ (độc lập, không thuộc bài ghép) — cột chuẩn cho union_all + `is_tre`
        (hạn hoàn thành SX rơi về hạn giao đã quá hôm nay). `kw` lọc theo MÃ trên chính bảng Lsx."""
        tre = func.coalesce(Lsx.han_hoan_thanh_sx, Lsx.han_giao_khach) < date.today()
        q = select(
            literal(NGUON_LSX).label("nguon"),
            Lsx.id.label("id"),
            Lsx.is_rush.label("is_rush"),
            Lsx.created_at.label("created_at"),
            case((tre, True), else_=False).label("is_tre"),
        ).where(
            Lsx.trang_thai == LSX_SAN_SANG,
            ~exists(select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)),
        )
        return q.where(Lsx.ma.ilike(f"%{kw}%")) if kw else q

    def _nhanh_bg(self, kw: str = ""):
        """Nhánh bài ghép `san_sang` — song song `_nhanh_lsx` (bài ghép chỉ có hạn hoàn thành SX)."""
        tre = BaiGhep.han_hoan_thanh_sx < date.today()
        q = select(
            literal(NGUON_IN_GHEP).label("nguon"),
            BaiGhep.id.label("id"),
            BaiGhep.is_rush.label("is_rush"),
            BaiGhep.created_at.label("created_at"),
            case((tre, True), else_=False).label("is_tre"),
        ).where(BaiGhep.trang_thai == BG_SAN_SANG)
        return q.where(BaiGhep.ma.ilike(f"%{kw}%")) if kw else q

    def lsx_so_cong_doan_map(self, ids: Iterable[int | None]) -> dict[int, int]:
        """Số công đoạn (routing) của mỗi LSX — hàng chờ hiện 'còn mấy công đoạn phải xếp'."""
        keys = self._ids(ids)
        if not keys:
            return {}
        q = (
            select(LsxCongDoan.lsx_id, func.count(LsxCongDoan.id))
            .where(LsxCongDoan.lsx_id.in_(keys))
            .group_by(LsxCongDoan.lsx_id)
        )
        return {lsx_id: int(n) for lsx_id, n in self.db.execute(q)}

    def bai_ghep_so_cong_doan_map(self, ids: Iterable[int | None]) -> dict[int, int]:
        """Số công đoạn CHUNG của mỗi bài ghép — song song với LSX ở hàng chờ."""
        keys = self._ids(ids)
        if not keys:
            return {}
        q = (
            select(BaiGhepCongDoan.bai_ghep_id, func.count(BaiGhepCongDoan.id))
            .where(BaiGhepCongDoan.bai_ghep_id.in_(keys))
            .group_by(BaiGhepCongDoan.bai_ghep_id)
        )
        return {bg_id: int(n) for bg_id, n in self.db.execute(q)}
