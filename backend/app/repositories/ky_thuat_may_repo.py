"""Repository — Kỹ thuật máy (phiếu sửa chữa · phiếu bảo trì · ảnh minh chứng).

Ba câu hỏi service hỏi nhiều nhất, gom hết vào đây để lớp trên không phải viết SQL:
  · gói này còn phiếu bảo trì nào ĐANG MỞ không (chặn sinh trùng),
  · gói này HOÀN THÀNH lần chót ngày nào (mốc tính kỳ sau),
  · phiếu này đã có ảnh "sau" chưa (cửa đóng phiếu).
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    MA_PREFIX_BAO_TRI,
    MA_PREFIX_SUA_CHUA,
    TT_BT_DANG_MO,
    TT_BT_HOAN_THANH,
    TT_SC_DA_SUA_XONG,
    TT_SC_DANG_MO,
    BaoTriMay,
    KyThuatMayAnh,
    SuaChuaMay,
)

# Field client được phép gán. `ma` / `trang_thai` / mốc hoàn thành do SERVICE quản — cho client tự
# đặt trạng thái là mở cửa hậu đi vòng qua cửa "phải có ảnh mới đóng phiếu".
ASSIGNABLE_SUA_CHUA = (
    "may_id", "bo_phan_hong", "mo_ta", "muc_do",
    "nguoi_bao_id", "nguoi_bao_ten", "thoi_diem",
    "nguyen_nhan_phuong_an", "ghi_chu",
)
# `nguoi_thuc_hien*` KHÔNG nằm ở đây: người nhận việc do SERVICE gán từ tài khoản đang đăng nhập
# lúc bấm "Đang thực hiện" (chủ chốt 12/08/2026 — bỏ ô gõ tay). Cho client set là mở lại cửa hậu
# ghi tên người khác vào việc mình làm.
ASSIGNABLE_BAO_TRI = (
    "may_id", "goi_id", "goi_ten", "chu_ky_so", "chu_ky_don_vi", "loai",
    "ngay_ke_hoach", "hang_muc", "ghi_chu",
)


class KyThuatMayRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ================= Phiếu sửa chữa =================

    def get_sua_chua(self, phieu_id: int) -> SuaChuaMay | None:
        return self.db.get(SuaChuaMay, phieu_id)

    def next_ma_sua_chua(self) -> str:
        return self._next_ma(SuaChuaMay.ma, MA_PREFIX_SUA_CHUA)

    def list_sua_chua(self, *, q: str | None = None, may_id: int | None = None,
                      trang_thai: str | None = None, page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(SuaChuaMay.ma).like(like),
                func.lower(SuaChuaMay.bo_phan_hong).like(like),
                func.lower(func.coalesce(SuaChuaMay.mo_ta, "")).like(like),
            ))
        if may_id:
            conds.append(SuaChuaMay.may_id == may_id)
        if trang_thai == "can_lam":
            conds.append(SuaChuaMay.trang_thai.in_(TT_SC_DANG_MO))
        elif trang_thai:
            conds.append(SuaChuaMay.trang_thai == trang_thai)
        base, total = self._paged(select(SuaChuaMay), SuaChuaMay, conds, page, size)
        # Máy CÒN NẰM lên trước, rồi mới tới phiếu đã đóng; trong mỗi nhóm thì mới nhất lên đầu.
        base = base.order_by(
            case((SuaChuaMay.trang_thai == TT_SC_DA_SUA_XONG, 1), else_=0).asc(),
            SuaChuaMay.thoi_diem.desc(),
            SuaChuaMay.id.desc(),
        )
        return list(self.db.execute(base).scalars()), total

    def dem_theo_trang_thai_sua_chua(self) -> dict[str, int]:
        """{trang_thai: số phiếu} — số trên tab, đếm ở DB thay vì tải cả bảng về đếm."""
        rows = self.db.execute(
            select(SuaChuaMay.trang_thai, func.count()).group_by(SuaChuaMay.trang_thai)
        ).all()
        return {str(k): int(v) for k, v in rows}

    def create_sua_chua(self, data: dict, *, ma: str) -> SuaChuaMay:
        phieu = SuaChuaMay(ma=ma, may_id=int(data["may_id"]),
                           bo_phan_hong=(data.get("bo_phan_hong") or "").strip())
        self._apply(phieu, data, ASSIGNABLE_SUA_CHUA)
        self.db.add(phieu)
        self.db.commit()
        self.db.refresh(phieu)
        return phieu

    def update_sua_chua(self, phieu: SuaChuaMay, data: dict) -> SuaChuaMay:
        self._apply(phieu, data, ASSIGNABLE_SUA_CHUA)
        self.db.commit()
        self.db.refresh(phieu)
        return phieu

    # `delete_sua_chua` ĐÃ GỠ 12/08/2026 cùng cả đường xoá phiếu — xem router/service.

    # ================= Phiếu bảo trì =================

    def get_bao_tri(self, phieu_id: int) -> BaoTriMay | None:
        return self.db.get(BaoTriMay, phieu_id)

    def next_ma_bao_tri(self) -> str:
        return self._next_ma(BaoTriMay.ma, MA_PREFIX_BAO_TRI)

    def list_bao_tri(self, *, q: str | None = None, may_id: int | None = None,
                     trang_thai: str | None = None, tu: date | None = None,
                     den: date | None = None, page: int = 1, size: int = 50):
        """`trang_thai` nhận cả 2 giá trị DẪN XUẤT: `can_lam` (chưa xong) và `qua_han` (trễ ngày).

        Chúng phải lọc Ở ĐÂY chứ không phải trên mảng FE đã tải: có phân trang rồi thì lọc phía
        client chỉ lọc được đúng trang đang xem, và con số trên tab sẽ nói dối.
        """
        conds = []
        if tu:
            conds.append(BaoTriMay.ngay_ke_hoach >= tu)
        if den:
            conds.append(BaoTriMay.ngay_ke_hoach <= den)
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(BaoTriMay.ma).like(like),
                func.lower(func.coalesce(BaoTriMay.goi_ten, "")).like(like),
                func.lower(func.coalesce(BaoTriMay.nguoi_thuc_hien, "")).like(like),
            ))
        if may_id:
            conds.append(BaoTriMay.may_id == may_id)
        if trang_thai == "can_lam":
            # Bộ lọc DẪN XUẤT (không phải giá trị lưu): mọi phiếu chưa xong. Đây là câu hỏi thợ hỏi
            # mỗi sáng, gộp hai trạng thái lại cho khỏi bấm hai tab.
            conds.append(BaoTriMay.trang_thai.in_(TT_BT_DANG_MO))
        elif trang_thai == "qua_han":
            conds.append(BaoTriMay.trang_thai.in_(TT_BT_DANG_MO))
            conds.append(BaoTriMay.ngay_ke_hoach < date.today())
        elif trang_thai:
            conds.append(BaoTriMay.trang_thai == trang_thai)
        base, total = self._paged(select(BaoTriMay), BaoTriMay, conds, page, size)
        # VIỆC CÒN DỞ LÊN TRƯỚC, rồi mới tới phiếu đã xong; trong mỗi nhóm thì hạn sớm nhất (quá
        # hạn) lên đầu. Sắp thuần theo ngày như trước là phiếu hoàn thành cùng ngày chen lẫn vào
        # giữa việc phải làm, và càng chạy lâu càng phải cuộn.
        base = base.order_by(
            case((BaoTriMay.trang_thai == TT_BT_HOAN_THANH, 1), else_=0).asc(),
            BaoTriMay.ngay_ke_hoach.asc(),
            BaoTriMay.id.asc(),
        )
        return list(self.db.execute(base).scalars()), total

    def dem_theo_trang_thai_bao_tri(self) -> dict[str, int]:
        rows = self.db.execute(
            select(BaoTriMay.trang_thai, func.count()).group_by(BaoTriMay.trang_thai)
        ).all()
        return {str(k): int(v) for k, v in rows}

    def phieu_dang_mo_cua_goi(self, may_id: int, goi_id: str) -> BaoTriMay | None:
        """Phiếu CHƯA xong của gói.

        Dùng để lịch KHÔNG vẽ ô "kỳ dự kiến" chồng lên kỳ đã thành phiếu thật, và để dòng "Kỳ tới"
        ở màn Thiết bị trỏ được sang phiếu đang mở."""
        return self.db.execute(
            select(BaoTriMay).where(
                BaoTriMay.may_id == may_id,
                BaoTriMay.goi_id == goi_id,
                BaoTriMay.trang_thai.in_(TT_BT_DANG_MO),
            )
        ).scalars().first()

    def ngay_hoan_thanh_gan_nhat(self, may_id: int, goi_id: str) -> date | None:
        """Mốc tính kỳ sau. `max` chứ không "phiếu mới nhất theo id": phiếu bị dời lịch/nhập bù có
        thể tạo sau nhưng làm trước, lấy theo id là ra mốc sai."""
        return self.db.execute(
            select(func.max(BaoTriMay.ngay_hoan_thanh)).where(
                BaoTriMay.may_id == may_id,
                BaoTriMay.goi_id == goi_id,
                BaoTriMay.trang_thai == TT_BT_HOAN_THANH,
            )
        ).scalar()

    def create_bao_tri(self, data: dict, *, ma: str) -> BaoTriMay:
        phieu = BaoTriMay(ma=ma, may_id=int(data["may_id"]),
                          ngay_ke_hoach=data["ngay_ke_hoach"])
        # Ngày dự kiến BAN ĐẦU chốt ngay lúc sinh — "Đã dời" sau này so với mốc này.
        phieu.ngay_ke_hoach_goc = data["ngay_ke_hoach"]
        self._apply(phieu, data, ASSIGNABLE_BAO_TRI)
        self.db.add(phieu)
        self.db.commit()
        self.db.refresh(phieu)
        return phieu

    def update_bao_tri(self, phieu: BaoTriMay, data: dict) -> BaoTriMay:
        self._apply(phieu, data, ASSIGNABLE_BAO_TRI)
        self.db.commit()
        self.db.refresh(phieu)
        return phieu

    # `delete_bao_tri` ĐÃ GỠ 12/08/2026 — phiếu không xoá được, kể cả bằng API.

    # ================= Ảnh =================

    def list_anh(self, loai_phieu: str, phieu_id: int) -> list[KyThuatMayAnh]:
        return list(self.db.execute(
            select(KyThuatMayAnh)
            .where(KyThuatMayAnh.loai_phieu == loai_phieu, KyThuatMayAnh.phieu_id == phieu_id)
            .order_by(KyThuatMayAnh.uploaded_at.asc(), KyThuatMayAnh.id.asc())
        ).scalars())

    def anh_map(self, loai_phieu: str, phieu_ids: list[int]) -> dict[int, int]:
        """{phieu_id: số ảnh} cho CẢ TRANG danh sách — cột "Ảnh" mà query từng dòng là N+1."""
        if not phieu_ids:
            return {}
        rows = self.db.execute(
            select(KyThuatMayAnh.phieu_id, func.count())
            .where(KyThuatMayAnh.loai_phieu == loai_phieu, KyThuatMayAnh.phieu_id.in_(phieu_ids))
            .group_by(KyThuatMayAnh.phieu_id)
        ).all()
        return {int(k): int(v) for k, v in rows}

    def dem_anh_sau(self, loai_phieu: str, phieu_id: int) -> int:
        """Đếm ảnh CHỨNG THỰC — con số quyết định đóng được phiếu hay không."""
        return int(self.db.execute(
            select(func.count()).select_from(KyThuatMayAnh).where(
                KyThuatMayAnh.loai_phieu == loai_phieu,
                KyThuatMayAnh.phieu_id == phieu_id,
                KyThuatMayAnh.giai_doan == GIAI_DOAN_SAU,
            )
        ).scalar_one())

    def get_anh(self, anh_id: int) -> KyThuatMayAnh | None:
        return self.db.get(KyThuatMayAnh, anh_id)

    def add_anh(self, **kw) -> KyThuatMayAnh:
        anh = KyThuatMayAnh(**kw)
        self.db.add(anh)
        self.db.commit()
        self.db.refresh(anh)
        return anh

    def delete_anh(self, anh: KyThuatMayAnh) -> None:
        self.db.delete(anh)
        self.db.commit()

    # ================= Dùng chung =================

    def _next_ma(self, col, prefix: str) -> str:
        """Mã kế tiếp tính trên MỌI hàng — chỉ tăng, chấp nhận có khoảng trống (giống `khuon_be`)."""
        rx = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        mx = 0
        for ma in self.db.execute(select(col)).scalars():
            m = rx.match((ma or "").strip().upper())
            if m:
                mx = max(mx, int(m.group(1)))
        return f"{prefix}{mx + 1:04d}"

    def _paged(self, base, model, conds, page: int, size: int):
        count_stmt = select(func.count()).select_from(model)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = int(self.db.execute(count_stmt).scalar_one())
        page = max(1, page)
        size = max(1, min(size, 200))
        return base.offset((page - 1) * size).limit(size), total

    @staticmethod
    def _apply(obj, data: dict, fields: tuple[str, ...]) -> None:
        for k in fields:
            if k in data:
                setattr(obj, k, data[k])
