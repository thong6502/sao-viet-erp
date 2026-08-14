"""Repository — Kỹ thuật máy (phiếu sửa chữa · phiếu bảo trì · ảnh minh chứng).

Ba câu hỏi service hỏi nhiều nhất, gom hết vào đây để lớp trên không phải viết SQL:
  · gói này còn phiếu bảo trì nào ĐANG MỞ không (chặn sinh trùng),
  · gói này HOÀN THÀNH lần chót ngày nào (mốc tính kỳ sau),
  · phiếu này đã có ảnh "sau" chưa (cửa đóng phiếu).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    MA_PREFIX_BAO_TRI,
    MA_PREFIX_SUA_CHUA,
    MUC_DO,
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
# `nguoi_thuc_hien*` KHÔNG nằm ở đây: người làm do SERVICE gán từ tài khoản bấm "Xác nhận đã bảo
# trì xong" (không có bước nhận việc riêng). Cho client set là mở lại cửa hậu ghi tên người khác
# vào việc mình làm.
ASSIGNABLE_BAO_TRI = (
    "may_id", "goi_id", "goi_ten", "chu_ky_so", "chu_ky_don_vi", "loai",
    "ngay_ke_hoach", "hang_muc", "ghi_chu",
)
# SỬA nội dung thì hẹp hơn TẠO: bốn field dưới đây chỉ đặt được lúc sinh phiếu.
#   · `may_id`/`goi_id`/`loai` — phiếu neo vào gói của một máy để tính kỳ kế tiếp; đổi giữa chừng
#     là mốc của gói cũ mất và gói mới nhận một mốc chưa từng làm.
#   · `ngay_ke_hoach` — đổi ngày phải đi qua "dời lịch" (bắt buộc lý do), không lặng lẽ sửa.
# Trước đây `update_bao_tri` dùng chung tuple TẠO; không thủng qua HTTP vì `BaoTriPatch` không khai
# bốn field này, nhưng đó là cửa mở sẵn chờ người sau thêm một dòng vào schema là lọt.
SUA_DUOC_BAO_TRI = tuple(
    f for f in ASSIGNABLE_BAO_TRI
    if f not in ("may_id", "goi_id", "loai", "ngay_ke_hoach")
)


class KyThuatMayRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ================= Phiếu sửa chữa =================

    def get_sua_chua(self, phieu_id: int) -> SuaChuaMay | None:
        return self.db.get(SuaChuaMay, phieu_id)

    def next_ma_sua_chua(self) -> str:
        return self._next_ma(SuaChuaMay.ma, MA_PREFIX_SUA_CHUA)

    def _conds_sua_chua(self, *, q: str | None, may_id: int | None,
                        muc_do: str | None = None) -> list:
        """Điều kiện lọc DÙNG CHUNG cho `list_sua_chua` và `dem_sua_chua` — viết một chỗ để hai nơi
        không lệch (bảng lọc còn 3 dòng mà tab đếm cả bảng là con số trên tab hết nghĩa)."""
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
        if muc_do:
            conds.append(SuaChuaMay.muc_do == muc_do)
        return conds

    def _uu_tien_muc_do(self):
        """Nặng trước nhẹ sau, thứ tự lấy từ chính `MUC_DO` của model — thêm mức mới vào tuple đó là
        chỗ này tự đúng theo, không phải nhớ sửa hai nơi."""
        return case(
            {m: i for i, m in enumerate(MUC_DO)}, value=SuaChuaMay.muc_do, else_=-1,
        ).desc()

    def list_sua_chua(self, *, q: str | None = None, may_id: int | None = None,
                      trang_thai: str | None = None, muc_do: str | None = None,
                      sort: str | None = None, page: int = 1, size: int = 50):
        """`sort`: `moi_nhat` (mặc định) · `cu_nhat` · `muc_do`.

        Mọi kiểu sắp đều giữ NGUYÊN luật "việc còn dở lên trước": phiếu đã đóng trộn lẫn vào giữa
        việc phải làm là thứ khiến người ta phải cuộn tìm, đổi kiểu sắp không phải để bỏ luật đó.
        `cu_nhat` là để lôi phiếu treo lâu nhất lên đầu — câu hỏi "cái nào nằm đó lâu rồi".
        """
        conds = self._conds_sua_chua(q=q, may_id=may_id, muc_do=muc_do)
        if trang_thai == "can_lam":
            conds.append(SuaChuaMay.trang_thai.in_(TT_SC_DANG_MO))
        elif trang_thai:
            conds.append(SuaChuaMay.trang_thai == trang_thai)
        base, total = self._paged(select(SuaChuaMay), SuaChuaMay, conds, page, size)
        # Máy CÒN NẰM lên trước, rồi mới tới phiếu đã đóng; trong mỗi nhóm thì theo `sort`.
        con_do = case((SuaChuaMay.trang_thai == TT_SC_DA_SUA_XONG, 1), else_=0).asc()
        if sort == "cu_nhat":
            base = base.order_by(con_do, SuaChuaMay.thoi_diem.asc(), SuaChuaMay.id.asc())
        elif sort == "muc_do":
            base = base.order_by(con_do, self._uu_tien_muc_do(),
                                 SuaChuaMay.thoi_diem.desc(), SuaChuaMay.id.desc())
        else:
            base = base.order_by(con_do, SuaChuaMay.thoi_diem.desc(), SuaChuaMay.id.desc())
        return list(self.db.execute(base).scalars()), total

    def dem_sua_chua(self, *, q: str | None = None, may_id: int | None = None,
                     muc_do: str | None = None) -> dict[str, int]:
        """{trang_thai: số phiếu} theo ĐÚNG bộ lọc đang xem — đếm ở DB, không tải cả bảng về đếm."""
        stmt = select(SuaChuaMay.trang_thai, func.count()).group_by(SuaChuaMay.trang_thai)
        for c in self._conds_sua_chua(q=q, may_id=may_id, muc_do=muc_do):
            stmt = stmt.where(c)
        return {str(k): int(v) for k, v in self.db.execute(stmt).all()}

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

    def _conds_bao_tri(self, *, q: str | None, may_id: int | None,
                       tu: date | None, den: date | None) -> list:
        """Bộ điều kiện lọc DÙNG CHUNG cho `list_bao_tri` và `dem_bao_tri`.

        Viết một chỗ vì hai nơi lệch nhau là số trên tab lại nói dối lần nữa: bảng lọc theo tháng 8
        mà con số trên tab đếm cả năm thì người ta chỉ còn cách tự đếm tay.
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
        return conds

    def list_bao_tri(self, *, hom_nay: date, q: str | None = None, may_id: int | None = None,
                     trang_thai: str | None = None, tu: date | None = None,
                     den: date | None = None, sort: str | None = None,
                     page: int = 1, size: int = 50):
        """`trang_thai` nhận cả 2 giá trị DẪN XUẤT: `can_lam` (chưa xong) và `qua_han` (trễ ngày).

        Chúng phải lọc Ở ĐÂY chứ không phải trên mảng FE đã tải: có phân trang rồi thì lọc phía
        client chỉ lọc được đúng trang đang xem, và con số trên tab sẽ nói dối.

        `hom_nay` do SERVICE truyền xuống (giờ VN), repo không tự hỏi ngày: `date.today()` ở đây đọc
        giờ MÁY CHỦ — container chạy UTC thì từ 0h đến 7h sáng giờ VN nó vẫn tưởng là hôm qua.

        `sort`: `han_som` (mặc định — trễ nhất lên đầu) · `han_muon`. Việc còn dở vẫn luôn lên trước.
        """
        conds = self._conds_bao_tri(q=q, may_id=may_id, tu=tu, den=den)
        if trang_thai == "can_lam":
            # Bộ lọc DẪN XUẤT (không phải giá trị lưu): mọi phiếu chưa xong. Đây là câu hỏi thợ hỏi
            # mỗi sáng, gộp hai trạng thái lại cho khỏi bấm hai tab.
            conds.append(BaoTriMay.trang_thai.in_(TT_BT_DANG_MO))
        elif trang_thai == "qua_han":
            conds.append(BaoTriMay.trang_thai.in_(TT_BT_DANG_MO))
            conds.append(BaoTriMay.ngay_ke_hoach < hom_nay)
        elif trang_thai:
            conds.append(BaoTriMay.trang_thai == trang_thai)
        base, total = self._paged(select(BaoTriMay), BaoTriMay, conds, page, size)
        # VIỆC CÒN DỞ LÊN TRƯỚC, rồi mới tới phiếu đã xong; trong mỗi nhóm thì hạn sớm nhất (quá
        # hạn) lên đầu. Sắp thuần theo ngày như trước là phiếu hoàn thành cùng ngày chen lẫn vào
        # giữa việc phải làm, và càng chạy lâu càng phải cuộn.
        con_do = case((BaoTriMay.trang_thai == TT_BT_HOAN_THANH, 1), else_=0).asc()
        if sort == "han_muon":
            base = base.order_by(con_do, BaoTriMay.ngay_ke_hoach.desc(), BaoTriMay.id.desc())
        else:
            base = base.order_by(con_do, BaoTriMay.ngay_ke_hoach.asc(), BaoTriMay.id.asc())
        return list(self.db.execute(base).scalars()), total

    def dem_bao_tri(self, *, hom_nay: date, q: str | None = None, may_id: int | None = None,
                    tu: date | None = None, den: date | None = None) -> dict[str, int]:
        """{trang_thai: số phiếu} + 3 số DẪN XUẤT theo ngày, trong MỘT query, THEO ĐÚNG bộ lọc.

        Trả thêm:
          · `qua_han`     — còn dở mà hạn đã qua;
          · `den_hom_nay` — còn dở và hạn ≤ hôm nay (đúng con số badge thanh bên);
          · `tuan_nay`    — còn dở và hạn ≤ hôm nay + 6 ngày (bao gồm cả phần quá hạn).

        Ba số này phụ thuộc NGÀY nên không suy được từ bảng đếm theo trạng thái — trước đây FE phải
        bịa mẹo "chỉ hiện số Quá hạn khi đang đứng ở tab đó".
        """
        dang_mo = BaoTriMay.trang_thai.in_(TT_BT_DANG_MO)
        cuoi_tuan = hom_nay + timedelta(days=6)

        def _sum(dieu_kien):
            return func.sum(case((and_(dang_mo, dieu_kien), 1), else_=0))

        stmt = select(
            BaoTriMay.trang_thai,
            func.count(),
            _sum(BaoTriMay.ngay_ke_hoach < hom_nay),
            _sum(BaoTriMay.ngay_ke_hoach <= hom_nay),
            _sum(BaoTriMay.ngay_ke_hoach <= cuoi_tuan),
        ).group_by(BaoTriMay.trang_thai)
        for c in self._conds_bao_tri(q=q, may_id=may_id, tu=tu, den=den):
            stmt = stmt.where(c)

        out: dict[str, int] = {"qua_han": 0, "den_hom_nay": 0, "tuan_nay": 0}
        for tt, tong, qua, den_nay, tuan in self.db.execute(stmt).all():
            out[str(tt)] = int(tong)
            out["qua_han"] += int(qua or 0)
            out["den_hom_nay"] += int(den_nay or 0)
            out["tuan_nay"] += int(tuan or 0)
        return out

    def phieu_dang_mo_cua_goi(self, may_id: int, goi_id: str) -> BaoTriMay | None:
        """Phiếu CHƯA xong của gói.

        Dùng để lịch KHÔNG vẽ ô "kỳ dự kiến" chồng lên kỳ đã thành phiếu thật, và để dòng "Kỳ tới"
        ở màn Thiết bị trỏ được sang phiếu đang mở. Có `order_by` để hai phiếu cùng mở thì luôn ra
        cùng một cái — `first()` trần là thứ tự do DB quyết, hôm nay ra phiếu này mai ra phiếu kia."""
        return self.db.execute(
            select(BaoTriMay).where(
                BaoTriMay.may_id == may_id,
                BaoTriMay.goi_id == goi_id,
                BaoTriMay.trang_thai.in_(TT_BT_DANG_MO),
            ).order_by(BaoTriMay.ngay_ke_hoach.asc(), BaoTriMay.id.asc())
        ).scalars().first()

    # ---- Hai bảng tra NẠP SẴN cho màn Lịch & ticker -------------------------------------------
    # Cả hai màn đều duyệt MỌI máy × MỌI gói. Hỏi lẻ từng gói (2 query/gói) là 40 máy × 3 gói ≈ 240
    # query cho một lần mở lịch — mà Lịch là view mặc định. Nạp trước thành dict, tra trong RAM.

    def moc_hoan_thanh_map(self, may_id: int | None = None) -> dict[tuple[int, str], date]:
        """{(may_id, goi_id): ngày hoàn thành GẦN NHẤT} — gốc để cộng chu kỳ ra kỳ kế tiếp.

        `may_id` để hỏi cho MỘT máy (tab Lịch bảo trì màn Thiết bị, khối "Kỳ kế tiếp" trong drawer)
        mà vẫn đi chung một đường với màn Lịch."""
        stmt = (
            select(BaoTriMay.may_id, BaoTriMay.goi_id, func.max(BaoTriMay.ngay_hoan_thanh))
            .where(BaoTriMay.trang_thai == TT_BT_HOAN_THANH, BaoTriMay.goi_id.isnot(None))
            .group_by(BaoTriMay.may_id, BaoTriMay.goi_id)
        )
        if may_id:
            stmt = stmt.where(BaoTriMay.may_id == may_id)
        return {(int(m), str(g)): d for m, g, d in self.db.execute(stmt).all() if d is not None}

    def phieu_dang_mo_map(self, may_id: int | None = None) -> dict[tuple[int, str], BaoTriMay]:
        """{(may_id, goi_id): phiếu chưa xong}. Cùng thứ tự với `phieu_dang_mo_cua_goi` để một gói
        có hai phiếu mở thì lịch và ticker nhìn thấy CÙNG một phiếu."""
        stmt = (
            select(BaoTriMay)
            .where(BaoTriMay.trang_thai.in_(TT_BT_DANG_MO), BaoTriMay.goi_id.isnot(None))
            .order_by(BaoTriMay.ngay_ke_hoach.asc(), BaoTriMay.id.asc())
        )
        if may_id:
            stmt = stmt.where(BaoTriMay.may_id == may_id)
        out: dict[tuple[int, str], BaoTriMay] = {}
        for p in self.db.execute(stmt).scalars():
            out.setdefault((int(p.may_id), str(p.goi_id)), p)
        return out

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

    def create_bao_tri(self, data: dict, *, ma: str, commit: bool = True) -> BaoTriMay:
        """`commit=False` cho người gọi sinh NHIỀU phiếu một lượt (ticker tới hạn) tự chốt một lần
        ở cuối — commit từng phiếu là mỗi phiếu một vòng ghi đĩa, và nửa chừng lỗi thì để lại một
        đống phiếu đã lưu dở. Vẫn `flush()` để phiếu có `id` dùng ngay được trong vòng lặp."""
        phieu = BaoTriMay(ma=ma, may_id=int(data["may_id"]),
                          ngay_ke_hoach=data["ngay_ke_hoach"])
        # Ngày dự kiến BAN ĐẦU chốt ngay lúc sinh — "Đã dời" sau này so với mốc này.
        phieu.ngay_ke_hoach_goc = data["ngay_ke_hoach"]
        self._apply(phieu, data, ASSIGNABLE_BAO_TRI)
        self.db.add(phieu)
        if commit:
            self.db.commit()
            self.db.refresh(phieu)
        else:
            self.db.flush()
        return phieu

    def update_bao_tri(self, phieu: BaoTriMay, data: dict) -> BaoTriMay:
        self._apply(phieu, data, SUA_DUOC_BAO_TRI)
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

    def anh_thong_ke(self, loai_phieu: str, phieu_ids: list[int]) -> dict[int, tuple[int, int]]:
        """{phieu_id: (tổng ảnh, số ảnh "sau")} cho CẢ TRANG — MỘT query cho cả hai con số.

        Trước đây là hai đường: `anh_map` đếm tổng cho cả trang, còn `co_anh_sau` gọi `dem_anh_sau`
        cho TỪNG dòng ⇒ 20 query thừa mỗi trang danh sách, 60+ mỗi lần mở lịch.
        """
        if not phieu_ids:
            return {}
        rows = self.db.execute(
            select(
                KyThuatMayAnh.phieu_id,
                func.count(),
                func.sum(case((KyThuatMayAnh.giai_doan == GIAI_DOAN_SAU, 1), else_=0)),
            )
            .where(KyThuatMayAnh.loai_phieu == loai_phieu, KyThuatMayAnh.phieu_id.in_(phieu_ids))
            .group_by(KyThuatMayAnh.phieu_id)
        ).all()
        return {int(k): (int(tong), int(sau or 0)) for k, tong, sau in rows}

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
        """Mã kế tiếp — chỉ tăng, chấp nhận có khoảng trống.

        Hỏi DB đúng vài dòng thay vì kéo CẢ cột mã về rồi regex từng dòng (ticker sinh 10 phiếu là
        10 lần kéo cả bảng). Sắp **dài trước, lớn sau** nên vẫn đúng khi vượt 4 chữ số: `PBT-10000`
        dài hơn `PBT-9999`, còn trong cùng độ dài thì mã có đệm số 0 so chuỗi cũng là so số.
        `limit(5)` để một mã lạc kiểu `PBT-XX` không làm tắc — bỏ qua nó và lấy mã hợp lệ kế tiếp.
        """
        rx = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        rows = self.db.execute(
            select(col)
            .where(col.like(f"{prefix}%"))
            .order_by(func.length(col).desc(), col.desc())
            .limit(5)
        ).scalars()
        for ma in rows:
            m = rx.match((ma or "").strip().upper())
            if m:
                return f"{prefix}{int(m.group(1)) + 1:04d}"
        # Cả 5 dòng đầu đều không khớp khuôn ⇒ quét đủ. Không được trả `0001` bừa: mã đó có thể đã
        # tồn tại và cột `ma` là UNIQUE — vỡ ngay lúc lưu.
        mx = 0
        for ma in self.db.execute(select(col).where(col.like(f"{prefix}%"))).scalars():
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
