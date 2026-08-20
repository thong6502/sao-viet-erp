"""Bối cảnh Xếp lịch 2 — BÓC dữ liệu sống thành đúng hình dạng mà `constraint.py` cần.

Tầng này là ranh giới: nó GỌI engine cũ (`XepLichService`) và repo để lấy ca, vùng khoá máy, việc
đã xếp, quân số, ngày vật tư… rồi trả về các tuple thuần (giờ/phút/số người). Nhờ vậy luật thời gian
ở `constraint.py` không phải biết gì về ORM hay DB.

KHÔNG có bất kỳ phép so khớp máy theo khổ/màu/định lượng ở đây (spec §6): máy hợp hay không là việc
con người tự cân, v2 chỉ dò trùng-máy / đè-khoá / vượt-quân-số theo GIỜ.

**Đóng băng (`dong_bang`)** — mở riêng cho các vòng QUÉT CHỈ-ĐỌC (gợi ý khe · gợi ý máy). Một lượt
chấm `_van_de_dat_lich` hỏi ~7 thứ (ca · khoá máy · việc trên máy · việc của tổ · quân số · tiền
nhiệm · hai hạn); quét vài trăm mốc thì thành vài nghìn truy vấn cho CÙNG một câu hỏi. Trong khối
`with ctx.dong_bang():` mỗi câu hỏi chỉ chạy MỘT lần. CỐ Ý bắt phải xin (opt-in): đường GHI (`luu`,
`phat_hanh`, `dua_vao`, `xoa_nhap`) không đi qua đây nên không có cửa nào đọc phải số cũ.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.bai_ghep import BaiGhep
from ...models.bai_ghep_cong_doan import BaiGhepCongDoan
from ...models.lsx import LsxCongDoan, LsxCongDoanPhuThuoc
from ...models.xep_lich import NGUON_IN_GHEP, XepLichCongDoan
from ..xep_lich_service import XepLichService, _aware
from .constraint import GIO_BAT_DAU, PHUT_LAM_NGAY

#: Tên thứ trong tuần — để gọi tên ngày nghỉ khi lịch không khai tên riêng ("Chủ nhật").
_THU = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]


class XepLich2Context:
    def __init__(self, db: Session, core: XepLichService, repo) -> None:
        self.db = db
        self.core = core
        self.repo = repo
        #: Nhớ ngày vật tư theo (lsx, bài) trong vòng đời một request: `kiem_phat_hanh` gọi cho từng
        #: dòng của cùng lệnh nên không được hỏi bảng giữ chỗ lặp lại.
        self._ngay_vt_cache: dict[tuple, date | None] = {}
        #: None = KHÔNG nhớ gì (mặc định, mọi đường ghi). dict = đang trong khối `dong_bang`.
        self._snap: dict[tuple, object] | None = None

    # --- Đóng băng cho vòng quét chỉ-đọc ------------------------------------
    @contextmanager
    def dong_bang(self):
        """Trong khối này mỗi câu hỏi nền chỉ chạm DB MỘT lần (xem docstring đầu file).

        Lồng nhau thì khối trong dùng chung kho của khối ngoài; thoát khối trả lại đúng trạng thái
        trước đó, nên một request vừa quét vừa ghi vẫn an toàn.
        """
        truoc = self._snap
        if truoc is None:
            self._snap = {}
        try:
            yield self
        finally:
            self._snap = truoc

    def _nho(self, khoa: tuple, tinh):
        if self._snap is None:
            return tinh()
        if khoa not in self._snap:
            self._snap[khoa] = tinh()
        return self._snap[khoa]

    # --- Ca làm ------------------------------------------------------------
    def ca_windows(self) -> list[tuple[int, int, bool]]:
        """Ca chung của xưởng dưới dạng `(bat_dau_phut, ket_thuc_phut, qua_dem)`.

        Chưa khai ca nào (test / xưởng mới) → fallback một ca ngày 08:00–16:00 để giờ bắt đầu ban
        ngày vẫn hợp lệ. Đây là cửa DUY NHẤT của ca — chỉ soi GIỜ BẮT ĐẦU (§7.1).
        """
        return self._nho(("ca",), self._ca_windows_moi)

    def _ca_windows_moi(self) -> list[tuple[int, int, bool]]:
        cas = [
            (int(s.start_minute), int(s.end_minute),
             bool(s.is_overnight) or int(s.end_minute) <= int(s.start_minute))
            for s in self.core._ca_lich_may()
        ]
        return cas or [(GIO_BAT_DAU * 60, GIO_BAT_DAU * 60 + PHUT_LAM_NGAY, False)]

    # --- Máy ---------------------------------------------------------------
    def khoang_chan_may(self, may_id: int | None) -> list[tuple]:
        """Vùng KHOÁ (bảo trì/hỏng/nghỉ) của máy — đã tz-aware sẵn từ engine cũ."""
        return self._nho(("chan_may", may_id), lambda: list(self.core._chan_may(may_id)))

    def khoang_may_da_xep(
        self, may_id: int | None, exclude_id: int | None = None,
    ) -> list[tuple]:
        """Các khoảng việc khác ĐÃ chiếm trên cùng máy (nền dò `trung_may`)."""
        return self._nho(("may_da_xep", may_id, exclude_id), lambda: [
            (_aware(r.start_at), _aware(r.finish_at))
            for r in self.repo.da_xep_khac_tren_may(may_id, exclude_id)
        ])

    # --- Tổ / quân số ------------------------------------------------------
    def _so_nguoi(self, dong: XepLichCongDoan) -> int:
        """Số nhân công MỘT dòng tiêu thụ — lấy đúng con số đã khai ở bước (§4)."""
        op = None
        if dong.nguon == NGUON_IN_GHEP and dong.bai_ghep_cong_doan_id:
            op = self.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
        elif dong.lsx_cong_doan_id:
            op = self.db.get(LsxCongDoan, dong.lsx_cong_doan_id)
        return max(1, int(getattr(op, "so_nhan_cong", 1) or 1))

    def placements_to(
        self, department_id: int | None, exclude_id: int | None = None,
    ) -> list[tuple]:
        """`(start, finish, so_nguoi)` của các việc CÙNG TỔ đã xếp — nền dò đỉnh quân số.

        Trả BẢN SAO: nơi gọi (`_vuot_quan_so`) nối thêm chính việc đang đặt vào danh sách, mà khi
        đóng băng thì danh sách gốc nằm trong kho dùng chung — cho ghi thẳng thì mỗi mốc quét lại
        cộng dồn thêm một người ma.
        """
        return list(self._nho(("to", department_id, exclude_id), lambda: [
            (_aware(r.start_at), _aware(r.finish_at), self._so_nguoi(r))
            for r in self.repo.da_xep_khac_theo_to(department_id, exclude_id)
        ]))

    def quan_so(self, department_id: int | None, ngay: date) -> dict:
        """Quân số CÓ HIỆU LỰC của tổ trong ngày (số tự tính hoặc dòng gõ đè) — mượn engine cũ."""
        return self._nho(("quan_so", department_id, ngay),
                         lambda: self.core.quan_so_ngay(department_id, ngay))

    # --- Tiền nhiệm (DAG routing) -----------------------------------------
    def tien_nhiem_finish(self, dong) -> list[datetime]:
        """Giờ KẾT THÚC của các bước tiền nhiệm ĐÃ xếp — nền dò `sai_tien_nhiem` (§5, §7.1).

        Hai nguồn tiền đề, cùng một ý "chưa xong thì bước sau chưa chạy được":
        1. Cạnh routing trong bảng phụ thuộc: bước trực tiếp trước bước này, CHỈ tính bước đã có giờ
           (`finish_at`). Khoá theo `lsx_cong_doan_id` nên bắt được cả cạnh xuyên LSX cùng đơn hàng.
        2. Sàn IN-CHUNG: LSX là thành viên bài ghép thì mọi bước (chạy sau in) phải đợi in ghép xong —
           đúng cách engine cũ lấy `_gang_finish` làm sàn (`_do_thi`).
        """
        khoa = ("tien_nhiem", getattr(dong, "lsx_id", None),
                getattr(dong, "lsx_cong_doan_id", None))
        return self._nho(khoa, lambda: self._tien_nhiem_moi(dong))

    def _tien_nhiem_moi(self, dong) -> list[datetime]:
        finishes: list[datetime] = []
        if getattr(dong, "lsx_id", None):
            gang = self.core._gang_finish_cho_lsx(dong.lsx_id)
            if gang:
                finishes.append(_aware(gang))
        step_id = getattr(dong, "lsx_cong_doan_id", None)
        if step_id:
            truoc_ids = list(self.db.execute(
                select(LsxCongDoanPhuThuoc.buoc_truoc_id)
                .where(LsxCongDoanPhuThuoc.buoc_sau_id == step_id)
            ).scalars())
            if truoc_ids:
                for f in self.db.execute(
                    select(XepLichCongDoan.finish_at).where(
                        XepLichCongDoan.lsx_cong_doan_id.in_(truoc_ids),
                        XepLichCongDoan.finish_at.is_not(None),
                    )
                ).scalars():
                    finishes.append(_aware(f))
        return finishes

    # --- Hạn ---------------------------------------------------------------
    def hai_han(self, dong) -> tuple[date | None, date | None]:
        """(hạn hoàn thành SX, hạn giao khách) của lệnh/bài — bài ghép chỉ có hạn SX (§5)."""
        khoa = ("hai_han", getattr(dong, "lsx_id", None), getattr(dong, "bai_ghep_id", None))
        return self._nho(khoa, lambda: self._hai_han_moi(dong))

    def _hai_han_moi(self, dong) -> tuple[date | None, date | None]:
        if getattr(dong, "lsx_id", None):
            lsx = self.core.lsx_repo.get(dong.lsx_id)
            if lsx is not None:
                return (lsx.han_hoan_thanh_sx, lsx.han_giao_khach)
        if getattr(dong, "bai_ghep_id", None):
            bg = self.db.get(BaiGhep, dong.bai_ghep_id)
            if bg is not None:
                return (getattr(bg, "han_hoan_thanh_sx", None), None)
        return (None, None)

    # --- Vật tư ------------------------------------------------------------
    def ngay_vat_tu(self, dong: XepLichCongDoan) -> date | None:
        """Ngày vật tư HỨA VỀ MUỘN NHẤT của lệnh/bài — chặn bắt đầu trước ca đầu ngày đó (§5, §12.6).

        Lấy TỪ GIỮ CHỖ chứ KHÔNG chạy lại engine cân đối: `xep_som_nhat` của trạng thái giữ chỗ
        chính là `max(ngày về)` của các dòng nguồn "đang về". Đọc thẳng bảng giữ chỗ (một truy vấn
        có index) cho nhẹ — xem-trước kéo-thả gọi hàm này liên tục, không được kéo theo cả bảng cân
        đối. Chưa giữ dòng "đang về" nào ⇒ None ⇒ luật `truoc_ngay_vat_tu` không chặn (thiếu vật tư
        chỉ chặn lúc phát hành, không cấm đặt nháp).
        """
        khoa = (getattr(dong, "lsx_id", None), getattr(dong, "bai_ghep_id", None))
        if khoa == (None, None):
            return None
        if khoa not in self._ngay_vt_cache:
            from ...models.vat_tu_giu_cho import NGUON_DANG_VE
            from ...repositories.giu_cho_repo import GiuChoRepository
            rows = GiuChoRepository(self.db).cua_chu_the(lsx_id=khoa[0], bai_ghep_id=khoa[1])
            ngays = [r.ngay_ve for r in rows if r.nguon == NGUON_DANG_VE and r.ngay_ve]
            self._ngay_vt_cache[khoa] = max(ngays) if ngays else None
        return self._ngay_vt_cache[khoa]

    # --- Lịch nền ----------------------------------------------------------
    def ngay_le(self, tu: date, den: date) -> list[dict]:
        return [
            {"ngay": r.day, "ten": r.name or "", "kind": r.kind}
            for r in self.repo.ngay_le(tu, den)
        ]

    def ten_ngay_nghi(self, d: date) -> str | None:
        """Tên ngày nghỉ của `d`, hoặc None nếu `d` là ngày làm việc bình thường.

        v2 VẪN xếp được vào ngày nghỉ (§3, §12.2 — máy chạy liên tục, xưởng có thể huy động làm
        thêm) nên đây KHÔNG phải luật chặn, không đưa vào `_van_de_dat_lich`. Nhưng một khe rơi vào
        Chủ nhật mà thẻ gợi ý ghi "lý tưởng" thì là nói dối — nhãn này để thẻ nói đúng cái người xếp
        cần biết TRƯỚC khi bấm.
        """
        return self._nho(("ten_nghi", d), lambda: self._ten_ngay_nghi_moi(d))

    def _ten_ngay_nghi_moi(self, d: date) -> str | None:
        if self.core.cal.is_working_day(d):
            return None
        ten = next((r.name for r in self.repo.ngay_le(d, d) if r.name), None)
        return ten or _THU[d.weekday()]
