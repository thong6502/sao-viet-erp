"""Service Xếp lịch công đoạn — biến routing đã "sẵn sàng" thành công việc CÓ MÁY + GIỜ.

Lát 1 (MVP máy-chỉ-ghi-nhận): người kế hoạch "Đưa vào kế hoạch" 1 lệnh / 1 bài ghép → sinh dòng lịch,
rồi GÁN máy/tổ/NCC + giờ bắt đầu; hệ TÍNH thời lượng + giờ kết thúc + sớm-nhất/muộn-nhất/độ-dư + nhãn
nguy cơ + phát hiện trùng máy. Không auto-scheduler, không chia nhỏ, không versioning.

XẾP THEO GIỜ (intraday): mọi mốc là DateTime "giờ nhà máy" (không đổi múi giờ — nhà máy một múi). Ngày
làm việc = [08:00, 16:00) (8h liền, chưa tách nghỉ trưa/đa ca — seam lát sau); nhảy ngày nghỉ/lễ theo
`CalendarService.is_working_day`. Cộng/lùi thời lượng chỉ trong giờ làm; tràn 8h → sang đầu ngày làm kế.

Số DẪN XUẤT tính LÚC ĐỌC (không lưu cột): thời lượng (`thoi_luong_buoc`), sớm-nhất/muộn-nhất/độ-dư,
nhãn nguy cơ, cờ xung đột. Tái dùng LsxRepository/BaiGhepRepository + BaiGhepService.tinh_so_to.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bai_ghep import (
    TT_DA_LAP_KE_HOACH as BG_DA_LAP, TT_DA_PHAT_HANH as BG_DA_PHAT_HANH,
    TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien,
)
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.attendance import WorkShift
from ..models.department import Department
from ..models.lsx import (
    DV_TO, LB_MAY, NS_TO_GIO,
    TT_DA_LAP_KE_HOACH as LSX_DA_LAP, TT_DA_PHAT_HANH as LSX_DA_PHAT_HANH,
    TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from ..models.machine_unavailable import LY_DO_BAO_TRI, LY_DO_KHOA, MachineUnavailablePeriod
from ..models.may_thiet_bi import MayThietBi
from ..models.xep_lich import (
    LY_DO_CHO_TIEN_DE, LY_DO_THIEU_MAY, LY_DO_THIEU_THOI_LUONG,
    NGUON_IN_GHEP, NGUON_LSX, TT_CHO_XEP, TT_DA_XEP, XepLichCongDoan,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.bai_ghep_repo import BaiGhepRepository
from ..repositories.calendar_repo import CalendarRepository
from ..repositories.lsx_repo import LsxRepository
from ..repositories.machine_unavailable_repo import MachineUnavailableRepository
from ..services.bai_ghep_service import BaiGhepService
from ..services.calendar_service import CalendarService
from ..services._may_fit import kiem_kha_nang
from ..services.lsx_service import _f, thoi_luong_buoc

NHOM_PRINT = "print"
GIO_BAT_DAU = 8          # 08:00 — giờ bắt đầu ca ngày (giờ nhà máy)
PHUT_LAM_NGAY = 8 * 60   # 8h/ngày làm việc
NGUONG_SAP_TOI_HAN = 2   # độ dư ≤ 2 ngày làm việc → "sắp tới hạn"
GOP_KHE_PHUT = 180       # gộp đoạn chiếm máy qua khe nghỉ ≤ 3h (nghỉ trưa/giải lao) → Gantt vẽ 1 thanh liền


class XepLichError(Exception):
    """Lỗi nghiệp vụ xếp lịch (router map sang HTTP)."""


class XepLichNotFound(XepLichError):
    pass


class XepLichValidationError(XepLichError):
    pass


class XepLichConflict(XepLichError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Chuẩn hóa về tz-aware (FE gửi `datetime-local` naive → coi là giờ nhà máy)."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _naive(dt: datetime | None) -> datetime | None:
    """Bỏ tzinfo để serialize dạng WALL-CLOCK (giờ nhà máy) — FE `new Date(iso)` KHÔNG dịch múi (tránh
    lệch +7h). Nhất quán `start_at` (SQLite trả naive). CHỈ cho ĐẦU RA hiển thị, KHÔNG cho tính toán."""
    return dt.replace(tzinfo=None) if dt is not None else None


def _dau_ngay(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, GIO_BAT_DAU, tzinfo=timezone.utc)


def _cuoi_ngay(d: date) -> datetime:
    return _dau_ngay(d) + timedelta(minutes=PHUT_LAM_NGAY)


# ---- Khung giờ làm của xưởng theo CA THẬT + cộng/lùi thời lượng theo GIỜ LÀM VIỆC ----

class LichXuong:
    """Khung GIỜ LÀM của xưởng (đọc-lúc-tính, máy-bất-khả-tri): tập ca `dung_cho_lich_may` chồng lên
    lịch ngày nghỉ (`CalendarService`). Cấp khoảng làm-việc để engine cộng/lùi thời lượng theo GIỜ.

    - Mỗi ca → 1 khoảng/ngày; ca đêm (`is_overnight` hoặc end≤start) vắt sang ngày sau.
    - Nghỉ trưa = KHE giữa 2 ca liên tiếp (không mô hình riêng).
    - Ca gate theo `is_working_day(ngày-bắt-đầu-ca)`; nhiều ca chồng giờ → MERGE (không đếm trùng).
    - TẬP CA RỖNG → fallback 8h phẳng [08:00,16:00) giữ hành vi lát 1.
    Giờ "nhà máy" một múi — mọi mốc tz-aware UTC danh nghĩa (không đổi múi).
    """

    _MAX_NGAY = 400  # chặn vòng khi gặp chuỗi ngày nghỉ dài (Tết) — vẫn dừng

    def __init__(self, cal: CalendarService, ca_rows: list) -> None:
        self.cal = cal
        # (start_minute, end_minute, is_overnight) — tách khỏi ORM; end≤start ⇒ coi qua đêm.
        self.cas = [
            (int(c.start_minute), int(c.end_minute),
             bool(c.is_overnight) or int(c.end_minute) <= int(c.start_minute))
            for c in ca_rows
        ]

    @staticmethod
    def _midnight(d: date) -> datetime:
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    @staticmethod
    def _merge(iv: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        out: list[tuple[datetime, datetime]] = []
        for s, e in sorted(iv):
            if out and s <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], e))
            else:
                out.append((s, e))
        return out

    def _khung_ngay(self, d: date) -> list[tuple[datetime, datetime]]:
        """Khoảng làm-việc CHẠM ngày `d`: ca bắt-đầu-trong-`d` + đuôi ca đêm bắt-đầu-`d-1`."""
        if not self.cas:
            if self.cal.is_working_day(d):
                m = self._midnight(d)
                return [(m + timedelta(minutes=GIO_BAT_DAU * 60),
                         m + timedelta(minutes=GIO_BAT_DAU * 60 + PHUT_LAM_NGAY))]
            return []
        out: list[tuple[datetime, datetime]] = []
        for base, chi_duoi_dem in ((d, False), (d - timedelta(days=1), True)):
            if not self.cal.is_working_day(base):
                continue
            m = self._midnight(base)
            for start_min, end_min, overnight in self.cas:
                if chi_duoi_dem and not overnight:
                    continue  # ngày trước chỉ đóng góp ĐUÔI ca đêm
                s = m + timedelta(minutes=start_min)
                e = m + timedelta(minutes=(1440 + end_min) if overnight else end_min)
                out.append((s, e))
        return self._merge(out)

    def next_interval(self, cursor: datetime) -> tuple[datetime, datetime] | None:
        """Khoảng làm-việc SỚM NHẤT có `end > cursor` (chứa cursor hoặc kế sau)."""
        d = cursor.date()
        for _ in range(self._MAX_NGAY):
            for s, e in self._khung_ngay(d):
                if e > cursor:
                    return (s, e)
            d = d + timedelta(days=1)
        return None

    def prev_interval(self, cursor: datetime) -> tuple[datetime, datetime] | None:
        """Khoảng làm-việc MUỘN NHẤT có `start < cursor` (chứa cursor hoặc ngay trước)."""
        d = cursor.date()
        for _ in range(self._MAX_NGAY):
            for s, e in reversed(self._khung_ngay(d)):
                if s < cursor:
                    return (s, e)
            d = d - timedelta(days=1)
        return None


def _chan_sau(cur: datetime, seg_end: datetime, chan: tuple) -> tuple[datetime, datetime] | None:
    """Vùng khóa SỚM NHẤT giao `[cur, seg_end)` (be>cur và bs<seg_end)."""
    best = None
    for bs, be in chan:
        if be > cur and bs < seg_end and (best is None or bs < best[0]):
            best = (bs, be)
    return best


def _chan_truoc(seg_start: datetime, cur: datetime, chan: tuple) -> tuple[datetime, datetime] | None:
    """Vùng khóa MUỘN NHẤT giao `[seg_start, cur)` (bs<cur và be>seg_start)."""
    best = None
    for bs, be in chan:
        if bs < cur and be > seg_start and (best is None or be > best[1]):
            best = (bs, be)
    return best


def _dau_ca(dt: datetime, lich: LichXuong) -> datetime:
    """Thời điểm bắt đầu làm việc hợp lệ SỚM NHẤT ≥ dt."""
    iv = lich.next_interval(dt)
    return dt if iv is None else max(dt, iv[0])


def _cuoi_ca(dt: datetime, lich: LichXuong) -> datetime:
    """Thời điểm kết thúc làm việc hợp lệ MUỘN NHẤT ≤ dt."""
    iv = lich.prev_interval(dt)
    return dt if iv is None else min(dt, iv[1])


def _cong_gio_lam(bat_dau: datetime, phut: float, lich: LichXuong, chan: tuple = ()) -> datetime:
    """Cộng `phut` phút LÀM VIỆC từ `bat_dau`, nhảy qua ngoài-ca/nghỉ/ngày-nghỉ và vùng khóa `chan`."""
    cur = _dau_ca(bat_dau, lich)
    con = float(phut)
    for _ in range(5000):
        if con <= 0:
            return cur
        iv = lich.next_interval(cur)
        if iv is None:
            return cur
        seg_start, seg_end = iv
        if cur < seg_start:
            cur = seg_start
        blk = _chan_sau(cur, seg_end, chan)
        if blk is not None:
            bs, be = blk
            if bs <= cur:                       # cur đang trong vùng khóa → nhảy hết khóa
                cur = _dau_ca(be, lich)
                continue
            seg_end = bs                        # chỉ làm được tới khi vùng khóa bắt đầu
        rong = (seg_end - cur).total_seconds() / 60.0
        if con <= rong:
            return cur + timedelta(minutes=con)
        con -= rong
        cur = _dau_ca(seg_end, lich)
    return cur


def _lui_gio_lam(ket_thuc: datetime, phut: float, lich: LichXuong, chan: tuple = ()) -> datetime:
    """Lùi `phut` phút LÀM VIỆC từ `ket_thuc` (đối xứng `_cong_gio_lam`)."""
    cur = _cuoi_ca(ket_thuc, lich)
    con = float(phut)
    for _ in range(5000):
        if con <= 0:
            return cur
        iv = lich.prev_interval(cur)
        if iv is None:
            return cur
        seg_start, seg_end = iv
        if cur > seg_end:
            cur = seg_end
        blk = _chan_truoc(seg_start, cur, chan)
        if blk is not None:
            bs, be = blk
            if be >= cur:                       # cur đang trong vùng khóa → lùi qua đầu khóa
                cur = _cuoi_ca(bs, lich)
                continue
            seg_start = be                      # chỉ làm được từ khi vùng khóa kết thúc
        rong = (cur - seg_start).total_seconds() / 60.0
        if con <= rong:
            return cur - timedelta(minutes=con)
        con -= rong
        cur = _cuoi_ca(seg_start, lich)
    return cur


def _dur_0() -> dict:
    """Thời lượng 0 (dòng chưa đủ dữ liệu) — kèm breakdown để DTO nhất quán."""
    return {"chiem_may_phut": 0.0, "tong_phut": 0.0,
            "setup_phut": 0.0, "chay_phut": 0.0, "ve_sinh_phut": 0.0,
            "theo_may": False, "canh_bao": None}


def _mo_ta_gan(truoc: tuple, sau: tuple) -> str:
    """Chuỗi mô tả thay đổi gán (máy/tổ/NCC/ca/giờ) cho audit lịch sử."""
    nhan = ("máy", "tổ", "NCC", "ca", "giờ")
    parts = [f"{nhan[i]} {truoc[i]}→{sau[i]}" for i in range(len(nhan)) if truoc[i] != sau[i]]
    return "; ".join(parts) or "cập nhật"


def _thoi_luong_in_ghep(bg: BaiGhep, tong_to: int, may: MayThietBi | None) -> dict:
    """Thời lượng công đoạn IN CHUNG của bài ghép: makeready + số tờ / tốc độ + rửa mực. Không có máy /
    chưa khai tốc độ → 0 (dòng bị chặn `thieu_thoi_luong`)."""
    setup = _f(may.makeready_time_default) if may else 0.0
    ve_sinh = _f(may.thoi_gian_rua_muc) if may else 0.0
    toc_do = _f(may.toc_do) if may else 0.0
    chay = (float(tong_to) / toc_do * 60.0) if toc_do > 0 and tong_to > 0 else 0.0
    chiem = round(setup + chay + ve_sinh, 2)
    return {"chiem_may_phut": chiem, "tong_phut": chiem,
            "setup_phut": round(setup, 2), "chay_phut": round(chay, 2), "ve_sinh_phut": round(ve_sinh, 2)}


class XepLichService:
    def __init__(self, db: Session, repo, audit: AuditLogRepository) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.lsx_repo = LsxRepository(db)
        self.bg_repo = BaiGhepRepository(db)
        self.bg_svc = BaiGhepService(db, self.bg_repo, audit, None)
        self.cal = CalendarService(CalendarRepository(db), audit)
        # Khung giờ làm của xưởng theo CA THẬT (nghỉ trưa/đa ca/ca đêm); tập ca rỗng → 8h phẳng.
        self.lich = LichXuong(self.cal, self._ca_lich_may())
        self.unavail_repo = MachineUnavailableRepository(db)

    def _ca_lich_may(self) -> list[WorkShift]:
        """Tập ca thuộc lịch chạy máy (active + `dung_cho_lich_may`), sort theo giờ vào."""
        return list(self.db.execute(
            select(WorkShift)
            .where(WorkShift.is_active.is_(True), WorkShift.dung_cho_lich_may.is_(True))
            .order_by(WorkShift.start_minute)
        ).scalars())

    def _chan_may(self, may_id: int | None) -> tuple[tuple[datetime, datetime], ...]:
        """Các khoảng KHÓA của máy (bảo trì/hỏng/nghỉ) — tz-aware, để engine né khi cộng giờ / tìm khe."""
        if not may_id:
            return ()
        return tuple(
            (_aware(p.unavailable_from), _aware(p.unavailable_to))
            for p in self.unavail_repo.list_by_may(may_id)
        )

    # ================= tra cứu phụ trợ =================

    def _get_dong(self, dong_id: int) -> XepLichCongDoan:
        d = self.repo.get(dong_id)
        if d is None:
            raise XepLichNotFound("Không tìm thấy dòng xếp lịch")
        return d

    def _lcd(self, lcd_id: int | None) -> LsxCongDoan | None:
        return self.db.get(LsxCongDoan, lcd_id) if lcd_id else None

    def _dept_names(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(select(Department.id, Department.name).where(Department.id.in_(ids))).all()
        return {i: n for i, n in rows}

    def _may_by_ids(self, ids: set[int]) -> dict[int, MayThietBi]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(select(MayThietBi).where(MayThietBi.id.in_(ids))).scalars()
        return {m.id: m for m in rows}

    def _nap_lo(self, rows: list[XepLichCongDoan]) -> tuple[dict, dict, dict]:
        """Nạp LÔ bối cảnh cho cả tập dòng lịch — 3 query thay vì 3-5 query MỖI dòng (né N+1):
        Lsx kèm công đoạn (identity map ấm → `_lcd` khỏi query), bài ghép kèm thành viên, máy full
        spec (nạp TRƯỚC vòng `_thoi_luong` để `db.get(MayThietBi)` trúng identity map)."""
        lsx_map = self.bg_repo.lsx_by_ids(list({r.lsx_id for r in rows if r.lsx_id}))
        bg_map = self.bg_repo.by_ids(list({r.bai_ghep_id for r in rows if r.bai_ghep_id}))
        may_map = self._may_by_ids({r.may_id for r in rows if r.may_id})
        return lsx_map, bg_map, may_map

    # ================= THỜI LƯỢNG 1 DÒNG =================

    def _thoi_luong(self, dong: XepLichCongDoan, bg: BaiGhep | None = None) -> dict:
        """{chiem_may_phut, tong_phut, setup_phut, chay_phut, ve_sinh_phut, theo_may, canh_bao}.

        In ghép: theo số tờ / tốc độ máy in. Bước nội bộ: nếu có máy khai tốc độ + đơn vị khớp
        (máy `to_gio` ⟷ bước vào `to`) → TÍNH LẠI theo máy đang gán (HM3); ngược lại snapshot bước.
        `bg` truyền từ vòng lặp bảng (đã nạp lô ở `_nap_lo`) để khỏi query lại từng dòng."""
        if dong.nguon == NGUON_IN_GHEP:
            # Dòng neo ĐÍCH DANH bước chung → thời lượng lấy từ chính bước đó (máy, năng suất,
            # `chay_phut` gõ đè, số lượt) — cùng công thức với bước của lệnh, vì nó CŨNG là một
            # bước có kế hoạch. Trước đây mọi dòng bài đều tính theo máy của bài + tổng tờ, tức là
            # vứt sạch những gì người dùng khai trong drawer bước chung.
            bgcd = (
                self.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
                if dong.bai_ghep_cong_doan_id else None
            )
            if bgcd is not None:
                return self._thoi_luong_noi_bo(dong, bgcd)
            if bg is None:
                bg = self.bg_repo.get(dong.bai_ghep_id) if dong.bai_ghep_id else None
            if bg is None:
                return _dur_0()
            lsx_map = self.bg_repo.lsx_by_ids([tv.lsx_id for tv in bg.thanh_viens])
            tong_to = self.bg_svc.tinh_so_to(bg, lsx_map)["tong_to"]
            may = self.db.get(MayThietBi, dong.may_id) if dong.may_id else None
            d = _thoi_luong_in_ghep(bg, tong_to, may)
            d["theo_may"] = bool(may and _f(may.toc_do) > 0)
            d["canh_bao"] = None if d["theo_may"] or not dong.may_id else "may_chua_toc_do"
            return d
        lcd = self._lcd(dong.lsx_cong_doan_id)
        if lcd is None:
            return _dur_0()
        return self._thoi_luong_noi_bo(dong, lcd)

    def _thoi_luong_noi_bo(
        self, dong: XepLichCongDoan, lcd: LsxCongDoan | BaiGhepCongDoan,
    ) -> dict:
        """Bước THEO MÁY (HM3) — dùng chung cho bước của lệnh lẫn bước chạy chung của bài, vì cả
        hai đều là "một bước có kế hoạch" với cùng bộ trường (`BaiGhepCongDoan` mirror
        `LsxCongDoan`). Máy đang gán khai tốc độ + đơn vị khớp (`to_gio`⟷`to`) → tính
        LIVE, TÁCH BẠCH — setup = makeready máy, chạy = SL_vào / tốc độ × lượt / nhân-công, vệ sinh =
        rửa mực máy (đúng BC: makeready theo máy, chạy theo tốc độ). Ngược lại fallback snapshot bước.
        `chay_phut` người kế hoạch gõ đè vẫn THẮNG công thức. `chờ`/`di chuyển` giữ theo bước (lag,
        không chiếm máy). `canh_bao` báo vì sao KHÔNG tính-theo-máy được (đơn vị lệch / máy chưa khai
        tốc độ) để UI nhắc số đang là snapshot."""
        may = self.db.get(MayThietBi, dong.may_id) if dong.may_id else None
        toc_do = _f(may.toc_do) if may else 0.0
        dv_khop = bool(may and may.don_vi_toc_do == NS_TO_GIO and lcd.don_vi_vao == DV_TO)
        cho, di_chuyen = _f(lcd.cho_phut), _f(lcd.di_chuyen_phut)
        if toc_do > 0 and dv_khop:
            setup, ve_sinh = _f(may.makeready_time_default), _f(may.thoi_gian_rua_muc)
            if lcd.chay_phut is not None:
                chay = _f(lcd.chay_phut)
            else:
                vao = _f(lcd.so_luong_vao)
                luot = max(int(lcd.so_luot_chay or 1), 1)
                # Kíp vận hành không làm máy chạy nhanh hơn. Chỉ số lượt qua máy nhân thời gian.
                chay = (vao / toc_do * 60.0 * luot) if vao > 0 else 0.0
            chiem = round(setup + chay + ve_sinh, 2)
            return {"chiem_may_phut": chiem, "tong_phut": round(chiem + cho + di_chuyen, 2),
                    "setup_phut": round(setup, 2), "chay_phut": round(chay, 2),
                    "ve_sinh_phut": round(ve_sinh, 2), "theo_may": True, "canh_bao": None}
        t = thoi_luong_buoc(lcd)
        canh_bao = "thieu_nang_suat" if t["dien_giai"]["phuong_phap"] == "thieu_nang_suat" else None
        if canh_bao is None and dong.may_id:
            canh_bao = "may_chua_toc_do" if (may is None or toc_do <= 0) else "don_vi_lech"
        return {"chiem_may_phut": t["chiem_may_phut"], "tong_phut": t["tong_phut"],
                "setup_phut": _f(lcd.setup_phut), "chay_phut": t["chay_phut"],
                "ve_sinh_phut": _f(lcd.ve_sinh_phut), "theo_may": False, "canh_bao": canh_bao}

    def _kiem_kha_nang(self, dong: XepLichCongDoan, lsx: Lsx | None = None,
                       may: MayThietBi | None = None) -> list[str]:
        """Lý do 'cần xác nhận' khi máy đang gán có thể không kham nổi công đoạn (khổ/số màu/định lượng).
        Soft — KHÔNG chặn. Chỉ bước nội bộ có máy; in ghép / chưa gán máy → rỗng. `lsx`/`may` truyền vào
        để tái dùng cache (tránh query lại trong `danh_sach`)."""
        if not dong.may_id or dong.nguon != NGUON_LSX or not dong.lsx_id:
            return []
        if lsx is None:
            lsx = self.lsx_repo.get(dong.lsx_id)
        if may is None:
            may = self.db.get(MayThietBi, dong.may_id)
        return kiem_kha_nang(lsx.quy_cach_json if lsx else None, may)

    # ================= SINH DÒNG (Đưa vào kế hoạch) =================

    def _dong_moi(self, lsx: Lsx, cd: LsxCongDoan, actor) -> XepLichCongDoan:
        return XepLichCongDoan(
            nguon=NGUON_LSX, lsx_id=lsx.id, lsx_cong_doan_id=cd.id,
            source_thu_tu=cd.thu_tu, loai_buoc=cd.loai_buoc,
            may_id=cd.may_id, department_id=cd.department_id, nha_cung_cap=cd.nha_cung_cap,
            trang_thai=TT_CHO_XEP, created_by=getattr(actor, "id", None),
        )

    def _sinh_dong(self, lsx: Lsx, *, bo_qua_in: bool, actor) -> list[XepLichCongDoan]:
        """Dòng lịch cho mọi công đoạn của LSX; bỏ ĐÚNG các bước đang chạy chung ở bài ghép.

        Bỏ theo lớp đè `bai_ghep_cong_doan_map` chứ không quét cả nhóm `print`: lệnh in 2 lượt
        (mặt trước / mặt sau tách dòng) thì quét cả nhóm là làm BỐC HƠI cả hai lượt khỏi board,
        trong khi bài chỉ ghép một lượt. Bài còn gộp cả CTP/cán/bế, nên tập bỏ là mọi bước bị đè,
        không riêng bước in.
        """
        bo_keys = self._buoc_ghep_keys(lsx.id) if bo_qua_in else set()
        out: list[XepLichCongDoan] = []
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
            if bo_qua_in and cd.step_key in bo_keys:
                continue
            out.append(self._dong_moi(lsx, cd, actor))
        return out

    def _buoc_ghep_keys(self, lsx_id: int) -> set[str]:
        """Các bước của lệnh đang bị bài ghép đè — bài xếp lịch cho chúng một dòng chung."""
        return set(self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key).where(BaiGhepCongDoanMap.lsx_id == lsx_id)
        ).scalars())

    def dua_vao_lsx(self, *, lsx_id: int, actor) -> Lsx:
        lsx = self.lsx_repo.get(lsx_id)
        if lsx is None:
            raise XepLichNotFound("Không tìm thấy lệnh sản xuất")
        if lsx.trang_thai == LSX_DA_LAP:
            raise XepLichConflict(f"Lệnh {lsx.ma} đã lập kế hoạch")
        if lsx.trang_thai != LSX_SAN_SANG:
            raise XepLichConflict(f"Lệnh {lsx.ma} chưa sẵn sàng xếp lịch")
        if self.bg_repo.lsx_da_ghep([lsx_id]):
            raise XepLichConflict("Lệnh nằm trong bài ghép — lập kế hoạch qua bài ghép")
        self.repo.add_all(self._sinh_dong(lsx, bo_qua_in=False, actor=actor))
        lsx.trang_thai = LSX_DA_LAP
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_dua_vao",
            target=f"lsx:{lsx.id}", detail=f"Đưa lệnh {lsx.ma} vào kế hoạch",
        )
        self.repo.commit()
        return lsx

    def dua_vao_bai_ghep(self, *, bai_ghep_id: int, actor) -> BaiGhep:
        bg = self.bg_repo.get(bai_ghep_id)
        if bg is None:
            raise XepLichNotFound("Không tìm thấy bài ghép")
        if bg.trang_thai == BG_DA_LAP:
            raise XepLichConflict(f"Bài ghép {bg.ma} đã lập kế hoạch")
        if bg.trang_thai != BG_SAN_SANG or self.bg_svc.thieu_cua(bg):
            raise XepLichConflict(f"Bài ghép {bg.ma} chưa sẵn sàng xếp lịch")
        # MỖI bước chạy chung một dòng — không phải một dòng "in ghép" duy nhất. `_sinh_dong` loại
        # mọi bước bị đè khỏi routing lệnh, nên gộp CTP + In + Cán mà chỉ đẻ một dòng là hai bước
        # kia bốc hơi khỏi board. Máy / tổ / NCC lấy từ chính bước chung (người vừa khai ở drawer),
        # không lấy `bg.may_id` — lấy máy của bài là vứt kế hoạch người dùng vừa lập.
        chungs = self.bg_svc._buoc_chungs(bg)
        if chungs:
            for c in chungs:
                self.repo.add(XepLichCongDoan(
                    nguon=NGUON_IN_GHEP, bai_ghep_id=bg.id, bai_ghep_cong_doan_id=c.id,
                    source_thu_tu=int(c.thu_tu or 0), loai_buoc=c.loai_buoc or LB_MAY,
                    may_id=c.may_id, department_id=c.department_id, nha_cung_cap=c.nha_cung_cap,
                    trang_thai=TT_CHO_XEP, created_by=getattr(actor, "id", None),
                ))
        else:
            # Bài cũ chưa có lớp đè (dữ liệu trước lát này) — giữ nguyên hành vi một dòng theo bài.
            self.repo.add(XepLichCongDoan(
                nguon=NGUON_IN_GHEP, bai_ghep_id=bg.id, source_thu_tu=0, loai_buoc=LB_MAY,
                may_id=bg.may_id, trang_thai=TT_CHO_XEP, created_by=getattr(actor, "id", None),
            ))
        lsx_map = self.bg_repo.lsx_by_ids([tv.lsx_id for tv in bg.thanh_viens])
        for tv in bg.thanh_viens:
            lsx = lsx_map.get(tv.lsx_id)
            if lsx is None:
                continue
            self.repo.add_all(self._sinh_dong(lsx, bo_qua_in=True, actor=actor))
            lsx.trang_thai = LSX_DA_LAP
        bg.trang_thai = BG_DA_LAP
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_dua_vao",
            target=f"bai_ghep:{bg.id}", detail=f"Đưa bài ghép {bg.ma} vào kế hoạch",
        )
        self.repo.commit()
        return bg

    def _go(self, rows: list[XepLichCongDoan]) -> None:
        if any(r.is_locked for r in rows):
            raise XepLichConflict("Có dòng đã khóa — mở khóa trước khi gỡ kế hoạch")
        self.repo.delete_rows(rows)

    def go_lsx(self, *, lsx_id: int, actor) -> None:
        lsx = self.lsx_repo.get(lsx_id)
        if lsx is None:
            raise XepLichNotFound("Không tìm thấy lệnh sản xuất")
        if lsx.trang_thai == LSX_DA_PHAT_HANH:
            raise XepLichConflict("Lệnh đã phát hành — thu hồi phát hành trước khi gỡ kế hoạch")
        if self.bg_repo.lsx_da_ghep([lsx_id]):
            raise XepLichConflict("Lệnh nằm trong bài ghép — gỡ kế hoạch qua bài ghép")
        self._go(self.repo.by_lsx(lsx_id))
        lsx.trang_thai = LSX_SAN_SANG
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_go",
            target=f"lsx:{lsx.id}", detail=f"Gỡ kế hoạch lệnh {lsx.ma}",
        )
        self.repo.commit()

    def go_bai_ghep(self, *, bai_ghep_id: int, actor) -> None:
        bg = self.bg_repo.get(bai_ghep_id)
        if bg is None:
            raise XepLichNotFound("Không tìm thấy bài ghép")
        if bg.trang_thai == BG_DA_PHAT_HANH:
            raise XepLichConflict("Bài ghép đã phát hành — thu hồi phát hành trước khi gỡ kế hoạch")
        member_ids = [tv.lsx_id for tv in bg.thanh_viens]
        rows = self.repo.by_bai_ghep(bai_ghep_id)
        for mid in member_ids:
            rows += self.repo.by_lsx(mid)
        self._go(rows)
        bg.trang_thai = BG_SAN_SANG
        lsx_map = self.bg_repo.lsx_by_ids(member_ids)
        for lsx in lsx_map.values():
            lsx.trang_thai = LSX_SAN_SANG
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_go",
            target=f"bai_ghep:{bg.id}", detail=f"Gỡ kế hoạch bài ghép {bg.ma}",
        )
        self.repo.commit()

    # ================= GÁN MÁY / CA / GIỜ =================

    def gan(self, *, dong_id: int, patch: dict, actor) -> XepLichCongDoan:
        dong = self._get_dong(dong_id)
        if dong.is_locked:
            raise XepLichConflict("Dòng đã khóa — mở khóa trước khi sửa")
        truoc = (dong.may_id, dong.department_id, dong.nha_cung_cap,
                 dong.work_shift_id, _aware(dong.start_at))
        for field in ("may_id", "department_id", "nha_cung_cap", "work_shift_id"):
            if field in patch:
                setattr(dong, field, patch[field])
        if "start_at" in patch:
            dong.start_at = _aware(patch["start_at"])
        # start_at đã lưu từ SQLite đọc lên là naive → phải chuẩn hóa tz-aware TRƯỚC khi
        # tính giờ. Nếu không, patch một phần (chỉ đổi máy/tổ/NCC, không kèm start_at) trên
        # dòng đã có giờ sẽ đẩy naive vào `_cong_gio_lam` → so naive vs aware → TypeError → 500.
        start = _aware(dong.start_at)
        dong.start_at = start
        duration = self._thoi_luong(dong)
        chiem = duration["chiem_may_phut"]
        thieu_thoi_luong = duration.get("canh_bao") == "thieu_nang_suat"
        if start is not None and chiem > 0:
            dong.finish_at = _cong_gio_lam(start, chiem, self.lich, self._chan_may(dong.may_id))
        else:
            dong.finish_at = None
        co_tai_nguyen = bool(dong.may_id or dong.department_id or (dong.nha_cung_cap or "").strip())
        if start is not None and co_tai_nguyen and chiem > 0 and not thieu_thoi_luong:
            dong.trang_thai, dong.blocked_reason = TT_DA_XEP, None
        else:
            dong.trang_thai = TT_CHO_XEP
            dong.blocked_reason = (
                LY_DO_THIEU_THOI_LUONG if chiem <= 0 or thieu_thoi_luong
                else LY_DO_THIEU_MAY if not co_tai_nguyen else LY_DO_CHO_TIEN_DE
            )
        # Lịch sử thay đổi (HM6): ghi vết đổi máy/giờ — gộp chuỗi kéo-thả liên tiếp cùng dòng.
        sau = (dong.may_id, dong.department_id, dong.nha_cung_cap, dong.work_shift_id, start)
        if sau != truoc:
            self.audit.create_collapsing(
                actor_user_id=getattr(actor, "id", None), action="xep_lich_gan",
                target=f"xep_lich:{dong.id}", detail=_mo_ta_gan(truoc, sau),
            )
        self.repo.commit()
        return self._get_dong(dong_id)

    def gan_loat(self, *, rows: list[dict], actor) -> list[XepLichCongDoan]:
        out = []
        for r in rows:
            dong_id = r.get("id")
            if dong_id is None:
                continue
            patch = {k: v for k, v in r.items() if k != "id"}
            out.append(self.gan(dong_id=dong_id, patch=patch, actor=actor))
        return out

    def khoa(self, *, dong_id: int, khoa: bool, actor) -> XepLichCongDoan:
        dong = self._get_dong(dong_id)
        dong.is_locked = bool(khoa)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None),
            action="xep_lich_khoa" if khoa else "xep_lich_mo_khoa",
            target=f"xep_lich:{dong.id}",
            detail="Khóa dòng lịch" if khoa else "Mở khóa dòng lịch",
        )
        self.repo.commit()
        return self._get_dong(dong_id)

    # ================= CHUỖI THỜI GIAN (dẫn xuất) =================

    def _san_thoi_gian(self, lsx: Lsx | None) -> datetime:
        now = _utcnow()
        bg = _aware(lsx.ban_giao_at) if lsx else None
        return max(now, bg) if bg else now

    def _han(self, lsx: Lsx | None) -> date | None:
        if lsx is None:
            return None
        return lsx.han_hoan_thanh_sx or lsx.han_giao_khach

    def _chuoi(self, rows: list[XepLichCongDoan], *, san: datetime, gang_finish: datetime | None,
               han: date | None, dur: dict[int, dict],
               override_finish: dict[int, datetime] | None = None) -> dict[int, dict]:
        """Forward (sớm nhất) + backward (muộn nhất) + độ dư + nhãn nguy cơ cho chuỗi 1 LSX.

        `dur[dong_id] = {chiem_may_phut, tong_phut}`. `gang_finish` = kết thúc in bài ghép (tiền đề bước
        đầu, nếu LSX là thành viên gang). `han` = hạn hoàn thành. `override_finish` = finish GIẢ ĐỊNH của
        một số dòng (xem-trước kéo-thả HM5) → bước sau bị đẩy theo finish giả định thay vì finish thật.
        """
        override_finish = override_finish or {}
        rows = sorted(rows, key=lambda r: r.source_thu_tu)
        info: dict[int, dict] = {}
        # --- forward ---
        prev_finish: datetime | None = None
        for i, r in enumerate(rows):
            chiem = dur[r.id]["chiem_may_phut"]
            cho = dur[r.id]["tong_phut"] - chiem
            if i == 0:
                es = max(san, gang_finish) if gang_finish else san
            else:
                es = prev_finish
            ef = _cong_gio_lam(es, chiem, self.lich) if chiem > 0 else es
            info[r.id] = {"som_nhat": es, "earliest_finish": ef}
            # Mốc cho bước sau ưu tiên lịch THỰC đã gán của bước này (finish_at) thay vì "sớm nhất lý
            # thuyết": bước sau không thể bắt đầu trước khi bước trước KẾT THÚC thật → "sớm nhất" phản
            # ánh đúng lịch, và cột Sớm nhất tự cảnh báo (đỏ) khi có ai gán bước sau chạy trước bước trước.
            base = override_finish.get(r.id) or _aware(r.finish_at) or ef
            prev_finish = base + timedelta(minutes=cho)
        # --- backward ---
        if han is not None:
            lf = _cuoi_ngay(han)
            for i in range(len(rows) - 1, -1, -1):
                r = rows[i]
                chiem = dur[r.id]["chiem_may_phut"]
                ls = _lui_gio_lam(lf, chiem, self.lich) if chiem > 0 else lf
                info[r.id]["muon_nhat"] = lf
                if i > 0:
                    cho_truoc = dur[rows[i - 1].id]["tong_phut"] - dur[rows[i - 1].id]["chiem_may_phut"]
                    lf = ls - timedelta(minutes=cho_truoc)
        # --- độ dư + nhãn ---
        today = _utcnow().date()
        for r in rows:
            it = info[r.id]
            muon = it.get("muon_nhat")
            ef = it["earliest_finish"]
            if muon is None:
                it["slack_ngay"], it["nhan_rui_ro"] = None, "chua_co_han"
                continue
            slack = self.cal.working_days_between(ef.date(), muon.date())
            if muon.date() < ef.date():
                slack = -self.cal.working_days_between(muon.date(), ef.date())
            it["slack_ngay"] = slack
            if han is not None and (han < today or ef > _cuoi_ngay(han)):
                it["nhan_rui_ro"] = "da_tre"
            elif slack < 0:
                it["nhan_rui_ro"] = "nguy_co_tre"
            elif slack <= NGUONG_SAP_TOI_HAN:
                it["nhan_rui_ro"] = "sap_toi_han"
            else:
                it["nhan_rui_ro"] = "an_toan"
        return info

    def _do_thi(self, rows: list[XepLichCongDoan], *, dur: dict[int, dict],
                lsx_map: dict[int, Lsx | None]) -> dict[int, dict]:
        """CPM trên DAG routing, kể cả cạnh xuyên LSX trong cùng đơn hàng.

        `thu_tu` không tạo quan hệ ngầm ở đây; quan hệ duy nhất là bảng phụ thuộc. Tiền nhiệm chưa
        được đưa vào kế hoạch vẫn được nhận diện để UI báo `cho_tien_de` thay vì cho bước sau chạy.
        """
        by_step = {r.lsx_cong_doan_id: r for r in rows if r.lsx_cong_doan_id}
        row_by_id = {r.id: r for r in rows}
        step_ids = set(by_step)
        # Chỉ nạp cạnh TRỎ TỚI bước trong kế hoạch (đủ cho preds + cờ cho_tien_de) — không quét cả bảng.
        edges = list(self.db.execute(
            select(LsxCongDoanPhuThuoc).where(LsxCongDoanPhuThuoc.buoc_sau_id.in_(step_ids))
        ).scalars()) if step_ids else []
        preds: dict[int, list[int]] = {r.id: [] for r in rows}
        succs: dict[int, list[int]] = {r.id: [] for r in rows}
        missing: set[int] = set()
        for e in edges:
            sau = by_step.get(e.buoc_sau_id)
            if sau is None:
                continue
            truoc = by_step.get(e.buoc_truoc_id)
            if truoc is None:
                missing.add(sau.id)
                continue
            preds[sau.id].append(truoc.id)
            succs[truoc.id].append(sau.id)

        indeg = {rid: len(ps) for rid, ps in preds.items()}
        queue = sorted((rid for rid, n in indeg.items() if n == 0),
                       key=lambda rid: (row_by_id[rid].lsx_id or 0, row_by_id[rid].source_thu_tu))
        topo: list[int] = []
        while queue:
            rid = queue.pop(0)
            topo.append(rid)
            for sid in succs[rid]:
                indeg[sid] -= 1
                if indeg[sid] == 0:
                    queue.append(sid)
        if len(topo) != len(rows):
            raise XepLichValidationError("Routing có chu trình nên không thể tính lịch")

        gang_map = self._gang_finish_map({r.lsx_id for r in rows if r.lsx_id})
        info: dict[int, dict] = {}
        for rid in topo:
            r = row_by_id[rid]
            lsx = lsx_map.get(r.lsx_id) if r.lsx_id else None
            floor = self._san_thoi_gian(lsx)
            gang = gang_map.get(r.lsx_id)
            if gang:
                floor = max(floor, gang)
            pred_finishes: list[datetime] = []
            for pid in preds[rid]:
                pr = row_by_id[pid]
                pfinish = _aware(pr.finish_at) or info[pid]["earliest_finish"]
                lag = dur[pid]["tong_phut"] - dur[pid]["chiem_may_phut"]
                pred_finishes.append(pfinish + timedelta(minutes=lag))
            es = max([floor, *pred_finishes])
            chiem = dur[rid]["chiem_may_phut"]
            ef = _cong_gio_lam(es, chiem, self.lich) if chiem > 0 else es
            info[rid] = {"som_nhat": es, "earliest_finish": ef,
                         "blocked_reason": LY_DO_CHO_TIEN_DE if rid in missing else None}

        latest_start: dict[int, datetime] = {}
        for rid in reversed(topo):
            r = row_by_id[rid]
            lsx = lsx_map.get(r.lsx_id) if r.lsx_id else None
            candidates: list[datetime] = []
            han = self._han(lsx)
            if han:
                candidates.append(_cuoi_ngay(han))
            candidates.extend(latest_start[sid] for sid in succs[rid] if sid in latest_start)
            if not candidates:
                continue
            lf = min(candidates)
            info[rid]["muon_nhat"] = lf
            chiem = dur[rid]["chiem_may_phut"]
            ls = _lui_gio_lam(lf, chiem, self.lich) if chiem > 0 else lf
            lag = dur[rid]["tong_phut"] - chiem
            latest_start[rid] = ls - timedelta(minutes=lag)

        today = _utcnow().date()
        for rid, it in info.items():
            muon, ef = it.get("muon_nhat"), it["earliest_finish"]
            if muon is None:
                it.update(slack_ngay=None, nhan_rui_ro="chua_co_han")
                continue
            slack = self.cal.working_days_between(ef.date(), muon.date())
            if muon.date() < ef.date():
                slack = -self.cal.working_days_between(muon.date(), ef.date())
            han = self._han(lsx_map.get(row_by_id[rid].lsx_id)) if row_by_id[rid].lsx_id else None
            risk = "da_tre" if han and (han < today or ef > _cuoi_ngay(han)) else (
                "nguy_co_tre" if slack < 0 else "sap_toi_han" if slack <= NGUONG_SAP_TOI_HAN else "an_toan")
            it.update(slack_ngay=slack, nhan_rui_ro=risk)
        return info

    # ================= XUNG ĐỘT MÁY =================

    def _xung_dot_ids(self) -> set[int]:
        """Id các dòng trùng lịch máy (cùng máy, khoảng [start, finish) chồng nhau)."""
        theo_may: dict[int, list[XepLichCongDoan]] = {}
        for r in self.repo.rows_da_xep_co_may():
            theo_may.setdefault(r.may_id, []).append(r)
        bad: set[int] = set()
        for rows in theo_may.values():
            rows.sort(key=lambda r: _aware(r.start_at))
            for a, b in zip(rows, rows[1:]):
                if _aware(b.start_at) < _aware(a.finish_at):
                    bad.add(a.id)
                    bad.add(b.id)
        return bad

    # ================= GỢI Ý (cơ bản) =================

    def goi_y(self, *, dong_id: int) -> dict:
        """Máy trống sớm nhất (trên máy đã gán/máy chính) + hạn lùi còn kịp giao. CHỈ ĐỌC."""
        dong = self._get_dong(dong_id)
        chiem = self._thoi_luong(dong)["chiem_may_phut"]
        may_id = dong.may_id
        san, gang_finish, han = self._boi_canh_chuoi(dong)
        rows = self.repo.list_dong() if dong.nguon == NGUON_LSX else self.repo.by_bai_ghep(dong.bai_ghep_id)
        lsx_map, bg_map, _ = self._nap_lo(rows)
        dur = {r.id: self._thoi_luong(r, bg=bg_map.get(r.bai_ghep_id)) for r in rows}
        if dong.nguon == NGUON_LSX:
            chuoi = self._do_thi([r for r in rows if r.nguon == NGUON_LSX], dur=dur, lsx_map=lsx_map)
        else:
            chuoi = self._chuoi(rows, san=san, gang_finish=gang_finish, han=han, dur=dur)
        it = chuoi.get(dong_id, {})
        som = it.get("som_nhat", san)
        chan = self._chan_may(may_id)
        khe = self._khe_trong(may_id, som, chiem, exclude_id=dong_id) if (may_id and chiem > 0) else None
        han_lui = None
        muon = it.get("muon_nhat")
        if muon is not None and chiem > 0:
            han_lui = _lui_gio_lam(muon, chiem, self.lich, chan)
        return {
            "may_id": may_id,
            "khe_trong": khe,
            "finish_neu_xep": _cong_gio_lam(khe, chiem, self.lich, chan) if khe else None,
            "han_lui": han_lui,
        }

    def _boi_canh_chuoi(self, dong: XepLichCongDoan) -> tuple[datetime, datetime | None, date | None]:
        if dong.nguon == NGUON_IN_GHEP:
            return self._san_thoi_gian(None), None, None
        lsx = self.lsx_repo.get(dong.lsx_id) if dong.lsx_id else None
        gang_finish = self._gang_finish_cho_lsx(dong.lsx_id)
        return self._san_thoi_gian(lsx), gang_finish, self._han(lsx)

    def _gang_finish_cho_lsx(self, lsx_id: int | None) -> datetime | None:
        """Nếu LSX là thành viên bài ghép: kết thúc in ghép (đã xếp) làm tiền đề bước xả tờ."""
        if not lsx_id:
            return None
        return self._gang_finish_map({lsx_id}).get(lsx_id)

    def _gang_finish_map(self, lsx_ids: set[int]) -> dict[int, datetime | None]:
        """lsx_id → kết thúc in ghép của bài ghép chứa nó — 2 query cho CẢ TẬP (`_do_thi` cần mốc này
        cho từng dòng, gọi lẻ là N+1). LSX không thuộc bài nào → không có key; bài chưa xếp giờ → None."""
        lsx_ids = {i for i in lsx_ids if i}
        if not lsx_ids:
            return {}
        bg_cua_lsx = {
            lid: bgid for lid, bgid in self.db.execute(
                select(BaiGhepThanhVien.lsx_id, BaiGhepThanhVien.bai_ghep_id)
                .where(BaiGhepThanhVien.lsx_id.in_(lsx_ids))
            ).all()
        }
        if not bg_cua_lsx:
            return {}
        finish_max: dict[int, datetime] = {}
        for bgid, fin in self.db.execute(
            select(XepLichCongDoan.bai_ghep_id, XepLichCongDoan.finish_at).where(
                XepLichCongDoan.bai_ghep_id.in_(set(bg_cua_lsx.values())),
                XepLichCongDoan.finish_at.is_not(None),
            )
        ).all():
            f = _aware(fin)
            if bgid not in finish_max or f > finish_max[bgid]:
                finish_max[bgid] = f
        return {lid: finish_max.get(bgid) for lid, bgid in bg_cua_lsx.items()}

    def _khe_trong(self, may_id: int, tu: datetime, chiem: float, *, exclude_id: int) -> datetime | None:
        """Khe trống sớm nhất ≥ `tu` trên `may_id` đủ chỗ `chiem` phút — né dòng đã xếp + VÙNG KHÓA máy."""
        chan = self._chan_may(may_id)
        ban = sorted(
            [(_aware(r.start_at), _aware(r.finish_at))
             for r in self.repo.rows_da_xep_co_may() if r.may_id == may_id and r.id != exclude_id]
            + list(chan)
        )
        cur = _dau_ca(tu, self.lich)
        for s, e in ban:
            if e <= cur:
                continue
            if _cong_gio_lam(cur, chiem, self.lich, chan) <= s:
                return cur
            cur = _dau_ca(e, self.lich)
        return cur

    # ================= XEM TRƯỚC ẢNH HƯỞNG (kéo-thả) =================

    def _xung_dot_gia_dinh(self, may_id: int | None, start: datetime | None,
                           finish: datetime | None, *, exclude_id: int) -> list[int]:
        """Dòng đã xếp trên `may_id` sẽ CHỒNG khối [start, finish) giả định (trừ chính dòng đang kéo)."""
        if not may_id or start is None or finish is None:
            return []
        out: list[int] = []
        for r in self.repo.rows_da_xep_co_may():
            if r.may_id == may_id and r.id != exclude_id \
                    and _aware(r.start_at) < finish and start < _aware(r.finish_at):
                out.append(r.id)
        return out

    def xem_truoc(self, *, dong_id: int, may_id: int | None, start_at: datetime) -> dict:
        """Mô phỏng gán (máy, giờ) cho 1 dòng — KHÔNG commit/không đổi DB (`no_autoflush` + hoàn nguyên).
        Trả finish giả định · xung đột máy · bước SAU bị đẩy (som_nhat mới) · hạn hoàn thành mới · nhãn
        rủi ro · cờ cần-xác-nhận. Cho preview trước khi thả (chỉ hộp thoại khi có downstream/xung đột)."""
        dong = self._get_dong(dong_id)
        start = _aware(start_at)
        if may_id is None:
            may_id = dong.may_id           # None = giữ máy hiện tại (nudge giờ, không đổi lane)
        with self.db.no_autoflush:
            old_may = dong.may_id
            dong.may_id = may_id
            try:
                d = self._thoi_luong(dong)
                chiem = d["chiem_may_phut"]
                finish = (_cong_gio_lam(start, chiem, self.lich, self._chan_may(may_id))
                          if start is not None and chiem > 0 else None)
                ly_do_xn = self._kiem_kha_nang(dong)
                xung_dot = self._xung_dot_gia_dinh(may_id, start, finish, exclude_id=dong_id)
                day_doi: list[dict] = []
                han_moi: date | None = None
                nhan: str | None = None
                if dong.nguon == NGUON_LSX and dong.lsx_id:
                    lsx = self.lsx_repo.get(dong.lsx_id)
                    rows = self.repo.by_lsx(dong.lsx_id)
                    dur = {r.id: self._thoi_luong(r) for r in rows}
                    chuoi = self._chuoi(
                        rows, san=self._san_thoi_gian(lsx),
                        gang_finish=self._gang_finish_cho_lsx(dong.lsx_id),
                        han=self._han(lsx), dur=dur,
                        override_finish={dong_id: finish} if finish else None,
                    )
                    nhan = chuoi.get(dong_id, {}).get("nhan_rui_ro")
                    fins = [finish if rid == dong_id else info.get("earliest_finish")
                            for rid, info in chuoi.items()]
                    fins = [f for f in fins if f is not None]
                    han_moi = max(fins).date() if fins else None
                    for r in sorted(rows, key=lambda x: x.source_thu_tu):
                        if r.source_thu_tu > dong.source_thu_tu and r.id in chuoi:
                            lcd = self._lcd(r.lsx_cong_doan_id)
                            day_doi.append({"id": r.id, "cong_doan_ten": lcd.ten if lcd else None,
                                            "som_nhat": _naive(chuoi[r.id].get("som_nhat"))})
            finally:
                dong.may_id = old_may
        return {
            "finish_at": _naive(finish),
            "chiem_may_phut": chiem, "setup_phut": d["setup_phut"],
            "chay_phut": d["chay_phut"], "ve_sinh_phut": d["ve_sinh_phut"],
            "theo_may": d.get("theo_may", False),
            "xung_dot_ids": xung_dot, "day_doi": day_doi,
            "han_hoan_thanh_moi": han_moi, "nhan_rui_ro": nhan,
            "can_xac_nhan": bool(ly_do_xn), "ly_do_xac_nhan": ly_do_xn,
        }

    # ================= LỊCH NỀN + ĐOẠN CHIẾM MÁY (Gantt) =================

    def _doan_chiem(self, start: datetime | None, chiem: float, chan: tuple = ()) -> list[dict]:
        """Chia khối chiếm máy [start, +`chiem` phút LÀM VIỆC] thành các ĐOẠN để Gantt vẽ. Gộp qua khe
        nghỉ ngắn (≤ GOP_KHE_PHUT: nghỉ trưa/giải lao → 1 thanh liền, nền loang), TÁCH qua khe dài
        (ngoài-ca/đêm/ngày-nghỉ = ngắt thật). Dẫn xuất lúc đọc, KHÔNG lưu."""
        start = _aware(start)
        if start is None or chiem <= 0:
            return []
        cur = _dau_ca(start, self.lich)
        con = float(chiem)
        occ: list[tuple[datetime, datetime]] = []
        for _ in range(5000):
            if con <= 0:
                break
            iv = self.lich.next_interval(cur)
            if iv is None:
                break
            seg_start, seg_end = iv
            if cur < seg_start:
                cur = seg_start
            blk = _chan_sau(cur, seg_end, chan)
            if blk is not None:
                bs, be = blk
                if bs <= cur:
                    cur = _dau_ca(be, self.lich)
                    continue
                seg_end = bs
            rong = (seg_end - cur).total_seconds() / 60.0
            lay = min(con, rong)
            occ.append((cur, cur + timedelta(minutes=lay)))
            con -= lay
            cur = _dau_ca(seg_end, self.lich) if lay >= rong else cur + timedelta(minutes=lay)
        doan: list[dict] = []
        for s, e in occ:
            if doan and (s - doan[-1]["finish"]).total_seconds() / 60.0 <= GOP_KHE_PHUT:
                doan[-1]["finish"] = e
            else:
                doan.append({"start": s, "finish": e})
        return doan

    def lich_nen_may(self, *, may_id: int, tu: date, den: date) -> dict:
        """Nền lịch máy cho Gantt: khoảng LÀM VIỆC của xưởng (theo ca) trong [tu, den] + vùng KHÓA máy."""
        khoang_lam: list[dict] = []
        d = tu
        while d <= den:
            for s, e in self.lich._khung_ngay(d):
                if s.date() == d:  # mỗi khoảng tính 1 lần theo ngày bắt đầu (đuôi ca đêm thuộc ngày trước)
                    khoang_lam.append({"start": _naive(s), "finish": _naive(e)})
            d = d + timedelta(days=1)
        khoang_khoa = [
            {"start": _naive(p.unavailable_from), "finish": _naive(p.unavailable_to), "ly_do": p.reason}
            for p in self.unavail_repo.list_range(tu=tu, den=den, may_id=may_id)
        ]
        return {"may_id": may_id, "khoang_lam": khoang_lam, "khoang_khoa": khoang_khoa}

    # ---- Vùng khóa máy (bảo trì/hỏng/nghỉ) — CRUD tối thiểu + dải cho Gantt overlay ----

    def _khoa_dict(self, p: MachineUnavailablePeriod) -> dict:
        return {"id": p.id, "may_id": p.may_id, "start": _naive(p.unavailable_from),
                "finish": _naive(p.unavailable_to), "ly_do": p.reason, "note": p.note}

    def vung_khoa_range(self, *, tu: date, den: date) -> list[dict]:
        """Mọi khoảng khóa GIAO [tu, den] (MỌI máy) — Gantt overlay theo từng lane."""
        return [self._khoa_dict(p) for p in self.unavail_repo.list_range(tu=tu, den=den)]

    def list_vung_khoa(self, *, may_id: int) -> list[dict]:
        return [self._khoa_dict(p) for p in self.unavail_repo.list_by_may(may_id)]

    def tao_vung_khoa(self, *, may_id: int, tu: datetime, den: datetime, ly_do: str,
                      note: str | None, actor) -> dict:
        tu, den = _aware(tu), _aware(den)
        if tu is None or den is None or tu >= den:
            raise XepLichValidationError("Khoảng khóa không hợp lệ: 'từ' phải trước 'đến'")
        row = self.unavail_repo.add(MachineUnavailablePeriod(
            may_id=may_id, reason=ly_do if ly_do in LY_DO_KHOA else LY_DO_BAO_TRI,
            unavailable_from=tu, unavailable_to=den, note=note, created_by=getattr(actor, "id", None),
        ))
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_khoa_may",
                          target=f"may:{may_id}", detail=f"Khóa máy {row.reason}: {tu}→{den}")
        self.unavail_repo.commit()
        return self._khoa_dict(row)

    def xoa_vung_khoa(self, *, pid: int, actor) -> None:
        row = self.unavail_repo.get(pid)
        if row is None:
            raise XepLichNotFound("Không tìm thấy vùng khóa máy")
        may_id = row.may_id
        self.unavail_repo.delete(row)
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_mo_khoa_may",
                          target=f"may:{may_id}", detail=f"Bỏ khóa máy #{pid}")
        self.unavail_repo.commit()

    # ================= BẢNG + HÀNG CHỜ (DTO cho router) =================

    def hang_cho(self) -> dict:
        """Order-pool: nguồn `san_sang` CHƯA đưa vào kế hoạch (LSX độc lập + bài ghép)."""
        lsxs = self.repo.nguon_cho_xep_lsx()
        bgs = self.repo.nguon_cho_xep_bai_ghep()
        lsx_items = [{
            "nguon": NGUON_LSX, "id": l.id, "ma": l.ma, "ten": l.ten,
            "so_cong_doan": len(l.cong_doans), "is_rush": bool(l.is_rush),
            "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
        } for l in lsxs]
        bg_items = [{
            "nguon": NGUON_IN_GHEP, "id": b.id, "ma": b.ma, "ten": None,
            "so_cong_doan": len(b.thanh_viens), "is_rush": False, "han_hoan_thanh_sx": None,
        } for b in bgs]
        items = lsx_items + bg_items
        return {"items": items, "total": len(items)}

    def danh_sach(self, *, may_id: int | None = None, q: str | None = None) -> dict:
        # Luôn tính DAG trên TOÀN bộ dòng đã đưa vào kế hoạch; lọc máy chỉ là lọc hiển thị. Nếu
        # lọc trước, tiền nhiệm nằm ở máy khác bị hiểu nhầm là "chưa vào kế hoạch".
        rows = self.repo.list_dong()
        lsx_map, bg_map, may_objs = self._nap_lo(rows)
        dur = {r.id: self._thoi_luong(r, bg=bg_map.get(r.bai_ghep_id)) for r in rows}
        xung_dot = self._xung_dot_ids()

        noi_bo = [r for r in rows if r.nguon == NGUON_LSX]
        chuoi = self._do_thi(noi_bo, dur=dur, lsx_map=lsx_map) if noi_bo else {}
        for r in rows:
            if r.nguon == NGUON_IN_GHEP:
                chuoi.update(self._chuoi([r], san=self._san_thoi_gian(None), gang_finish=None,
                                         han=None, dur=dur))

        may_names = {i: m.ten for i, m in may_objs.items()}
        dept_names = self._dept_names({r.department_id for r in rows})

        items: list[dict] = []
        for r in rows:
            lsx = lsx_map.get(r.lsx_id)
            bg = bg_map.get(r.bai_ghep_id)
            lcd = self._lcd(r.lsx_cong_doan_id)
            ly_do_xn = self._kiem_kha_nang(r, lsx=lsx, may=may_objs.get(r.may_id))
            ma = (lsx.ma if lsx else None) if r.nguon == NGUON_LSX else (bg.ma if bg else None)
            if r.nguon == NGUON_LSX:
                ten = lcd.ten if lcd else None
            else:
                # Tên THẬT của bước chạy chung ("Cán màng", "Ghi kẽm CTP"…). Gọi mọi dòng của bài
                # là "In chung" thì board có 3 dòng trùng tên, không biết dòng nào là bước nào.
                bgcd = (
                    self.db.get(BaiGhepCongDoan, r.bai_ghep_cong_doan_id)
                    if r.bai_ghep_cong_doan_id else None
                )
                ten = bgcd.ten if bgcd else "In chung"
            ch = chuoi.get(r.id, {})
            d = dur[r.id]
            items.append({
                "id": r.id, "nguon": r.nguon,
                "lsx_id": r.lsx_id, "bai_ghep_id": r.bai_ghep_id,
                "lsx_ma": ma, "cong_doan_ten": ten, "loai_buoc": r.loai_buoc,
                "so_luong_vao": _f(lcd.so_luong_vao) if lcd else None,
                "don_vi_vao": lcd.don_vi_vao if lcd else None,
                "may_id": r.may_id, "may_ten": may_names.get(r.may_id),
                "department_id": r.department_id, "department_ten": dept_names.get(r.department_id),
                "nha_cung_cap": r.nha_cung_cap, "work_shift_id": r.work_shift_id,
                "som_nhat": ch.get("som_nhat"), "muon_nhat": ch.get("muon_nhat"),
                "start_at": r.start_at, "finish_at": r.finish_at,
                "chiem_may_phut": d["chiem_may_phut"], "tong_phut": d["tong_phut"],
                "setup_phut": d.get("setup_phut", 0.0), "chay_phut": d.get("chay_phut", 0.0),
                "ve_sinh_phut": d.get("ve_sinh_phut", 0.0),
                "theo_may": d.get("theo_may", False), "canh_bao_thoi_luong": d.get("canh_bao"),
                "slack_ngay": ch.get("slack_ngay"), "nhan_rui_ro": ch.get("nhan_rui_ro"),
                "trang_thai": r.trang_thai, "is_locked": bool(r.is_locked),
                "co_xung_dot": r.id in xung_dot,
                "blocked_reason": ch.get("blocked_reason") or (
                    LY_DO_THIEU_THOI_LUONG if d.get("canh_bao") == "thieu_nang_suat"
                    else r.blocked_reason
                ),
                "can_xac_nhan": bool(ly_do_xn), "ly_do_xac_nhan": ly_do_xn,
                "is_rush": bool(lsx.is_rush) if lsx else False,
            })
        if q:
            like = q.strip().lower()
            items = [it for it in items if like in (it["lsx_ma"] or "").lower()
                     or like in (it["cong_doan_ten"] or "").lower()]
        if may_id is not None:
            items = [it for it in items if it["may_id"] == may_id]
        return {"items": items, "total": len(items)}
