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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import (
    TT_DA_LAP_KE_HOACH as BG_DA_LAP, TT_DA_PHAT_HANH as BG_DA_PHAT_HANH,
    TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien,
)
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.attendance import WorkShift
from ..models.cong_doan import CongDoan
from ..models.department import Department
from ..models.employee import (
    STATUS_ACTIVE as EMP_ACTIVE, STATUS_PROBATION as EMP_PROBATION,
    STATUS_PROBATION_ENDED as EMP_PROBATION_ENDED, Employee,
)
from ..models.leave import STATUS_APPROVED as LEAVE_APPROVED, LeaveRequest
from ..models.to_quan_so import ToQuanSoNgay
from ..models.lsx import (
    LB_MAY,
    TT_DA_LAP_KE_HOACH as LSX_DA_LAP, TT_DA_PHAT_HANH as LSX_DA_PHAT_HANH,
    TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from ..models.machine_unavailable import (
    KIEU_CHAN,
    KIEU_KHOANG,
    KIEU_MO_THEM,
    LY_DO_BAO_TRI,
    LY_DO_KHAC,
    LY_DO_KHOA,
    MachineUnavailablePeriod,
)
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
from ..repositories.rbac_repo import DepartmentRepository
from ..services.bai_ghep_service import BaiGhepService
from ..services.calendar_service import CalendarService
from ..services._may_fit import kiem_kha_nang
from ..services.lsx_service import _f, thoi_luong_buoc

NHOM_PRINT = "print"
GIO_BAT_DAU = 8          # 08:00 — giờ bắt đầu ca ngày (giờ nhà máy)
PHUT_LAM_NGAY = 8 * 60   # 8h/ngày làm việc
NGUONG_SAP_TOI_HAN = 2   # độ dư ≤ 2 ngày làm việc → "sắp tới hạn"
GOP_KHE_PHUT = 180       # gộp đoạn chiếm máy qua khe nghỉ ≤ 3h (nghỉ trưa/giải lao) → Gantt vẽ 1 thanh liền

# --- Cảnh báo lúc XEM TRƯỚC (mục 2f) — nói NGAY tại chỗ vừa thả, KHÔNG chặn -----------------
# Chốt 18/08/2026: xưởng luôn còn cách xử lý mà phần mềm không biết, nên bốn thứ dưới chỉ BÁO.
# Gom vào MỘT danh sách để hộp thoại xem-trước không phải đẻ thêm khối nào cho từng loại.
CB_KHOA_MAY = "khoa_may"        # thả đè lên khoảng bảo trì/khóa của máy
CB_NGOAI_GIO = "ngoai_gio"      # thả ra ngoài giờ làm / ngày nghỉ
CB_THIEU_NGUOI = "thieu_nguoi"  # tổ không đủ quân cho các việc chạy cùng lúc
CB_KHO_MAY = "kho_may"          # khổ / số màu / định lượng vượt khả năng máy


class XepLichError(Exception):
    """Lỗi nghiệp vụ xếp lịch (router map sang HTTP)."""


class XepLichNotFound(XepLichError):
    pass


class XepLichValidationError(XepLichError):
    pass


class XepLichConflict(XepLichError):
    pass


def _utcnow() -> datetime:
    """UTC THẬT — chỉ dùng cho DẤU THỜI GIAN BẢN GHI (`created_at`, `resolved_at`), KHÔNG dùng làm
    mốc xếp lịch. Muốn "bây giờ" để tính lịch thì gọi `_gio_xuong()`."""
    return datetime.now(timezone.utc)


def _gio_xuong() -> datetime:
    """Bây giờ theo ĐỒNG HỒ XƯỞNG — mốc sàn cho mọi phép xếp lịch.

    Cả module này dán nhãn `timezone.utc` lên GIỜ TƯỜNG của nhà máy: `_aware()` coi giờ naive FE gửi
    lên là giờ nhà máy, `_naive()` trả ra wall-clock để `new Date(iso)` bên FE không dịch múi, phút ca
    (`start_minute=360` → 06:00) cũng là phút-trong-ngày theo giờ tường. Chỉ riêng `_utcnow()` là UTC
    THẬT ⇒ ở VN nó lùi 7 tiếng so với mọi giá trị khác trên bảng: 09:14 giờ xưởng vào engine thành
    02:14, rơi vào Ca 3 (22:00–06:00) trong khi xưởng đang Ca 1, và engine xếp việc vào những giờ đã
    trôi qua. (Phát hiện 22/08/2026 trên màn Xếp lịch 2.)

    GIỮ `_utcnow()` NGUYÊN VẸN: nó còn là `default=` của `created_at` (`xep_lich_van_de`, `audit`) và
    là giá trị của `resolved_at` — dấu thời gian BẢN GHI là chuyện khác, đổi ở đó là dời lịch sử.
    """
    return datetime.now().replace(tzinfo=timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Chuẩn hóa về tz-aware (FE gửi `datetime-local` naive → coi là giờ nhà máy)."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _naive(dt: datetime | None) -> datetime | None:
    """Bỏ tzinfo để serialize dạng WALL-CLOCK (giờ nhà máy) — FE `new Date(iso)` KHÔNG dịch múi (tránh
    lệch +7h). Nhất quán `start_at` (SQLite trả naive). CHỈ cho ĐẦU RA hiển thị, KHÔNG cho tính toán."""
    return dt.replace(tzinfo=None) if dt is not None else None


def _fmt_gio(dt: datetime) -> str:
    """`14:30 21/08` — đủ để người đang kéo thanh nhận ra mốc, khỏi dài dòng năm."""
    return _aware(dt).strftime("%H:%M %d/%m")


def _dau_ngay(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, GIO_BAT_DAU, tzinfo=timezone.utc)


def _cuoi_ngay(d: date) -> datetime:
    return _dau_ngay(d) + timedelta(minutes=PHUT_LAM_NGAY)


# ---- Khung giờ làm của xưởng theo CA THẬT + cộng/lùi thời lượng theo GIỜ LÀM VIỆC ----

class LichXuong:
    """Khung GIỜ LÀM của xưởng (đọc-lúc-tính, máy-bất-khả-tri): tập ca ĐANG HOẠT ĐỘNG chồng lên
    lịch ngày nghỉ (`CalendarService`). Cấp khoảng làm-việc để engine cộng/lùi thời lượng theo GIỜ.

    - Mỗi ca → 1 khoảng/ngày; ca đêm (`is_overnight` hoặc end≤start) vắt sang ngày sau.
    - Nghỉ trưa = KHE giữa 2 ca liên tiếp (không mô hình riêng).
    - Ca gate theo `is_working_day(ngày-bắt-đầu-ca)`; nhiều ca chồng giờ → MERGE (không đếm trùng).
    - TẬP CA RỖNG → fallback 8h phẳng [08:00,16:00) giữ hành vi lát 1.
    Giờ "nhà máy" một múi — mọi mốc tz-aware UTC danh nghĩa (không đổi múi).

    **`lien_tuc=True` — khung của MÁY (2026-08-10):** máy là THIẾT BỊ, chạy được cả ngày; ca là
    chuyện của người nên không khai ở máy nữa. Khung = trọn ngày làm việc [00:00, 24:00), chỉ dừng
    vì ngày nghỉ/lễ và vì vùng KHOÁ máy (đi đường `chan`). Tập ca vẫn giữ cho DÒNG KHÔNG CÓ MÁY
    (bước tay của tổ) — ở đó giờ làm của người mới là thứ có thật.

    **Vùng MỞ THÊM (mg 0179):** `mo_them` là các khoảng máy chạy NGOÀI khung ("chủ nhật máy in 2
    chạy thêm 3 tiếng"). Cộng thẳng vào khung giờ làm — kể cả ngày nghỉ, vì đó chính là ý nghĩa của
    "làm thêm". Vùng CHẶN đi đường khác (tham số `chan` của `_cong_gio_lam`), không lẫn vào đây.
    """

    _MAX_NGAY = 400  # chặn vòng khi gặp chuỗi ngày nghỉ dài (Tết) — vẫn dừng

    def __init__(self, cal: CalendarService, ca_rows: list, mo_them: tuple = (),
                 lien_tuc: bool = False) -> None:
        self.cal = cal
        # (start_minute, end_minute, is_overnight) — tách khỏi ORM; end≤start ⇒ coi qua đêm.
        self.cas = [
            (int(c.start_minute), int(c.end_minute),
             bool(c.is_overnight) or int(c.end_minute) <= int(c.start_minute))
            for c in ca_rows
        ]
        self.mo_them = tuple(mo_them)
        self.lien_tuc = bool(lien_tuc)

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

    def _mo_them_ngay(self, d: date) -> list[tuple[datetime, datetime]]:
        """Phần vùng MỞ THÊM rơi vào ngày `d`. Cắt theo ngày để hoà chung với khung ca.

        Cố ý KHÔNG gate theo `is_working_day`: "chạy thêm" thường rơi đúng vào tối/chủ nhật — gate
        thì cái duy nhất nó dùng được lại bị chặn.
        """
        if not self.mo_them:
            return []
        dau, cuoi = self._midnight(d), self._midnight(d) + timedelta(days=1)
        ra: list[tuple[datetime, datetime]] = []
        for s, e in self.mo_them:
            if s is None or e is None or e <= dau or s >= cuoi:
                continue
            ra.append((max(s, dau), min(e, cuoi)))
        return ra

    def _khung_ngay(self, d: date) -> list[tuple[datetime, datetime]]:
        """Khoảng làm-việc CHẠM ngày `d`: ca bắt-đầu-trong-`d` + đuôi ca đêm bắt-đầu-`d-1`
        + vùng MỞ THÊM của riêng máy."""
        them = self._mo_them_ngay(d)
        if self.lien_tuc:
            # Máy: trọn ngày làm việc. Hai ngày liền kề cho hai khoảng dính nhau ở nửa đêm —
            # `_cong_gio_lam` bước qua bình thường (mỗi vòng ăn hết 1440' rồi nhảy khoảng kế).
            if self.cal.is_working_day(d):
                m = self._midnight(d)
                return self._merge([(m, m + timedelta(days=1)), *them])
            return self._merge(them)
        if not self.cas:
            if self.cal.is_working_day(d):
                m = self._midnight(d)
                return self._merge([
                    (m + timedelta(minutes=GIO_BAT_DAU * 60),
                     m + timedelta(minutes=GIO_BAT_DAU * 60 + PHUT_LAM_NGAY)),
                    *them,
                ])
            return self._merge(them)
        out: list[tuple[datetime, datetime]] = list(them)
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


def _vao_gio_lam(dt: datetime, lich: LichXuong, chan: tuple = ()) -> datetime:
    """Nhích `dt` tới thời điểm LÀM VIỆC hợp lệ sớm nhất ≥ dt — qua ngoài-ca/ngày-nghỉ VÀ vùng khóa.

    Khác `_dau_ca`: `_dau_ca` chỉ biết ca, không biết vùng khóa máy. Chèn việc đúng vào giữa khoảng
    bảo trì thì `_dau_ca` gật đầu, xong `_cong_gio_lam` mới lặng lẽ nhảy qua — giờ bắt đầu hiện trên
    bảng xem trước lệch với giờ thật sự chạy. Ở đây trả về ĐÚNG mốc mà việc bắt đầu.
    """
    cur = _dau_ca(dt, lich)
    for _ in range(500):
        iv = lich.next_interval(cur)
        if iv is None:
            return cur
        seg_start, seg_end = iv
        if cur < seg_start:
            cur = seg_start
        blk = _chan_sau(cur, seg_end, chan)
        if blk is not None and blk[0] <= cur:
            cur = _dau_ca(blk[1], lich)     # đang nằm trong vùng khóa → nhảy hết khóa rồi xét lại
            continue
        return cur
    return cur


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
    return {"chiem_may_phut": 0.0, "chiem_may_phut_min": 0.0, "chiem_may_phut_max": 0.0,
            "tong_phut": 0.0, "setup_phut": 0.0, "chay_phut": 0.0, "phat_sinh_phut": 0.0,
            "theo_may": False, "canh_bao": None}


def _mo_ta_gan(truoc: tuple, sau: tuple) -> str:
    """Chuỗi mô tả thay đổi gán (máy/tổ/NCC/ca/giờ) cho audit lịch sử."""
    nhan = ("máy", "tổ", "NCC", "ca", "giờ")
    parts = [f"{nhan[i]} {truoc[i]}→{sau[i]}" for i in range(len(nhan)) if truoc[i] != sau[i]]
    return "; ".join(parts) or "cập nhật"


def _thoi_luong_in_ghep(bg: BaiGhep, tong_to: int, may: MayThietBi | None) -> dict:
    """Thời lượng công đoạn IN CHUNG của bài ghép: makeready + số tờ / tốc độ. Không có máy /
    chưa khai tốc độ → 0 (dòng bị chặn `thieu_thoi_luong`).

    Vệ sinh/rửa mực đã BỎ khỏi hệ (2026-08-04): không còn cộng vào thời gian chiếm máy."""
    setup = _f(may.makeready_time_default) if may else 0.0
    toc_do = _f(may.toc_do) if may else 0.0

    def _chay(v: float) -> float:
        return (float(tong_to) * 60.0 / v) if v > 0 and tong_to > 0 else 0.0

    chay = _chay(toc_do)
    cao = _f(may.toc_do_max) if may else 0.0      # tốc độ TỐI ĐA ⇒ thời lượng NHỎ nhất
    thap = _f(may.toc_do_min) if may else 0.0
    chay_nhanh = _chay(cao) if cao > 0 else chay
    chay_cham = _chay(thap) if thap > 0 else chay
    chiem = round(setup + chay, 2)
    return {"chiem_may_phut": chiem, "tong_phut": chiem,
            "chiem_may_phut_min": round(setup + chay_nhanh, 2),
            "chiem_may_phut_max": round(setup + chay_cham, 2),
            "setup_phut": round(setup, 2), "chay_phut": round(chay, 2),
            "phat_sinh_phut": 0.0}


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
        # Lịch riêng TỪNG MÁY (vùng mở thêm khác nhau) — dựng trễ, cache trong vòng đời service.
        # Một lần vẽ bảng gọi `_lich_may` hàng trăm lần; không cache là mỗi dòng thêm 1 query.
        self._lich_cache: dict[int, LichXuong] = {}

    def _ca_lich_may(self) -> list[WorkShift]:
        """Tập ca CHUNG của xưởng = ca đang dùng VÀ có tick "chạy dưới xưởng", sort theo giờ vào.

        Đây là cửa DUY NHẤT đọc `work_shifts` cho Xếp lịch: nó vừa là khung giờ hợp lệ để đặt việc
        (§7.1 soi giờ bắt đầu), vừa là MẪU SỐ đo % tải máy. Ca văn phòng không được vào đây: xưởng
        khai Hành chính 08:00–17:00 cạnh Ca 1 · Ca 2 · Ca 3 — hôm nay nó nằm gọn trong Ca 1 + Ca 2
        nên không nới thêm phút nào, nhưng tắt Ca 2 đi là mẫu số phồng từ 8 lên 11 tiếng ⇒ mọi %
        tải thấp giả 27%.

        ⚠ KHÔNG ca nào tick ⇒ trả TẤT CẢ ca đang dùng, KHÔNG trả rỗng. Chính chỗ này giết cờ đời
        trước (`dung_cho_lich_may`, mg 0095 → gỡ ở mg 0226): cờ mặc định TẮT và không có ô khai nên
        4/4 ca đều FALSE, hàm này trả rỗng rồi `LichXuong` rơi về fallback 08:00–16:00 — im lặng,
        không ai thấy. Nay cờ mặc định BẬT (mg 0227) và có ô ở màn Ca kíp; vẫn giữ đường lùi này
        cho DB cũ / xưởng lỡ tắt hết: thà đo bằng mọi ca còn hơn đo bằng một ca tưởng tượng.

        Ca đã tắt (`is_active=False`) vẫn là đường loại hẳn một ca ra khỏi lịch xưởng.
        """
        cas = list(self.db.execute(
            select(WorkShift)
            .where(WorkShift.is_active.is_(True))
            .order_by(WorkShift.start_minute)
        ).scalars())
        return [s for s in cas if bool(getattr(s, "ca_san_xuat", True))] or cas

    def _lich_may(self, may_id: int | None) -> LichXuong:
        """Khung giờ của MÁY — chạy LIÊN TỤC (2026-08-10: bỏ ca riêng của máy và của tổ).

        Máy là thiết bị, không phải người: cần chạy tới 22h hay qua đêm thì cứ xếp, khỏi khai ca
        cho từng máy rồi mỗi lần tăng ca lại phải sửa danh mục. Cái vẫn dừng máy: **ngày nghỉ/lễ**
        của xưởng và **vùng KHOÁ** (bảo trì/hỏng — đi đường `chan`). Vùng **mở thêm** của máy vẫn
        cộng vào, vì đó là cách duy nhất cho máy chạy vào ngày nghỉ.

        `may_id` rỗng (dòng chưa gán máy) → lịch chung của xưởng: chưa có thiết bị nào để nói
        "chạy liên tục". CACHE theo máy — một lần dựng bảng gọi hàm này hàng trăm lần.
        """
        if not may_id:
            return self.lich
        if may_id in self._lich_cache:
            return self._lich_cache[may_id]
        lich = LichXuong(self.cal, [], self._mo_them_may(may_id), lien_tuc=True)
        self._lich_cache[may_id] = lich
        return lich

    def _lich_dong(self, dong: XepLichCongDoan) -> LichXuong:
        """Lịch của một DÒNG: bước có máy chạy liên tục; bước tay của tổ theo ca chung của xưởng."""
        if dong.may_id:
            return self._lich_may(dong.may_id)
        return self.lich

    @staticmethod
    def _gom_key(lsx: Lsx | None) -> str | None:
        """Khoá GOM (mục E): giấy + khổ tờ in + bộ mực. Hai việc cùng khoá = đổi qua lại gần như
        không tốn công canh máy (không thay giấy, không đổi khuôn khổ, không rửa mực).

        CHỈ để SẮP THỨ TỰ đề xuất — không đụng công thức thời gian, không khai thêm gì. Cố ý KHÔNG
        dựng bảng changeover ("đổi loại tốn bao nhiêu phút"): bảng đó phải khai và duy trì cho MỌI
        cặp, khai sai thì lịch lệch, mà lệch kiểu đó không ai bắt được.

        Thiếu quy cách → None ⇒ dòng đó không gom với ai, giữ nguyên thứ tự cũ (không đoán).
        """
        qc = (lsx.quy_cach_json or {}) if lsx else {}
        giay = qc.get("giay_id")
        dai, rong = qc.get("kho_in_dai"), qc.get("kho_in_rong")
        if not giay or not dai or not rong:
            return None
        muc = sorted({
            str(m).strip().upper()
            for m in (qc.get("muc_a") or []) + (qc.get("muc_b") or [])
            if str(m or "").strip()
        })
        return f"{giay}|{dai}x{rong}|{','.join(muc)}"

    # ================= QUÂN SỐ & QUỸ GIỜ-NGƯỜI CỦA TỔ (mục I) =================

    def quan_so_tu_tinh(self, department_id: int, ngay: date) -> int:
        """Số người của tổ trong ngày, SUY từ hồ sơ nhân sự — không tính người tầng giữa.

        · đếm `employees.department_id` == ĐÚNG tổ đó (nút lá), trạng thái đang đi làm;
        · trừ đơn phép **đã duyệt** phủ ngày đó.

        Người gắn ở tầng giữa ("thuộc Xưởng in", không thuộc tổ lá nào) KHÔNG tính vào tổ nào —
        cộng họ vào một tổ nào đó là đếm thừa người, và lịch sẽ hứa một năng lực không có thật.
        """
        # Hết thử việc chờ xác nhận vẫn đi làm ⇒ vẫn phải xếp được ca.
        dang_lam = (EMP_ACTIVE, EMP_PROBATION, EMP_PROBATION_ENDED)
        tong = self.db.execute(
            select(func.count()).select_from(Employee).where(
                Employee.department_id == department_id, Employee.status.in_(dang_lam),
            )
        ).scalar_one()
        nghi = self.db.execute(
            select(func.count(func.distinct(LeaveRequest.employee_id)))
            .select_from(LeaveRequest).join(Employee, Employee.id == LeaveRequest.employee_id)
            .where(
                Employee.department_id == department_id,
                Employee.status.in_(dang_lam),
                LeaveRequest.status == LEAVE_APPROVED,
                LeaveRequest.start_date <= ngay,
                LeaveRequest.end_date >= ngay,
            )
        ).scalar_one()
        return max(0, int(tong) - int(nghi))

    def quan_so_ngay(self, department_id: int, ngay: date) -> dict:
        """Quân số CÓ HIỆU LỰC của tổ trong ngày: dòng gõ đè nếu có, không thì số tự tính.

        Trả cả hai con số + nguồn, để màn hiện được "tự tính 8, đang gõ đè 5 — mượn 3 sang tổ Bế".
        Chỉ trả mỗi số cuối thì người xem không biết vì sao nó khác hồ sơ nhân sự.

        CỐ Ý KHÔNG cache ở tầng service: quân số đổi ngay khi ai đó gõ đè, mà một service khác
        trong cùng tiến trình có thể vừa ghi xong — cache ở đây là trả số cũ cho người vừa sửa.
        Vòng lặp nóng (`khoang_tai_to`) tự nhớ trong PHẠM VI một lần gọi, xem ở đó.
        """
        tu_tinh = self.quan_so_tu_tinh(department_id, ngay)
        row = self.db.execute(
            select(ToQuanSoNgay).where(
                ToQuanSoNgay.department_id == department_id, ToQuanSoNgay.ngay == ngay,
            )
        ).scalar_one_or_none()
        if row is None:
            return {"department_id": department_id, "ngay": ngay, "so_nguoi": tu_tinh,
                    "tu_tinh": tu_tinh, "go_de": False, "ly_do": None}
        return {"department_id": department_id, "ngay": ngay, "so_nguoi": int(row.so_nguoi),
                "tu_tinh": tu_tinh, "go_de": True, "ly_do": row.ly_do or None}

    def dat_quan_so(self, *, department_id: int, ngay: date, so_nguoi: int | None,
                    ly_do: str, actor) -> dict:
        """Gõ đè quân số một ngày (`so_nguoi=None` = BỎ gõ đè, quay về số tự tính).

        Bắt lý do: một con số đè lên dữ liệu nhân sự mà không nói vì sao thì tháng sau không ai
        giải thích nổi hôm đó lịch tính ra như vậy — và cũng không cãi lại được.
        """
        row = self.db.execute(
            select(ToQuanSoNgay).where(
                ToQuanSoNgay.department_id == department_id, ToQuanSoNgay.ngay == ngay,
            )
        ).scalar_one_or_none()
        if so_nguoi is None:
            if row is not None:
                self.db.delete(row)
                self.audit.create(actor_user_id=getattr(actor, "id", None),
                                  action="xep_lich_quan_so_bo_go_de",
                                  target=f"to:{department_id}", detail=f"{ngay}")
                self.repo.commit()
            return self.quan_so_ngay(department_id, ngay)
        if so_nguoi < 0:
            raise XepLichValidationError("Số người không được âm")
        ly_do = (ly_do or "").strip()
        if len(ly_do) < 3:
            raise XepLichValidationError("Ghi lý do gõ đè quân số (tối thiểu 3 ký tự)")
        if row is None:
            row = ToQuanSoNgay(department_id=department_id, ngay=ngay)
            self.db.add(row)
        row.so_nguoi, row.ly_do = int(so_nguoi), ly_do
        row.nguoi_sua_id = getattr(actor, "id", None)
        self.audit.create(actor_user_id=getattr(actor, "id", None),
                          action="xep_lich_quan_so_go_de",
                          target=f"to:{department_id}",
                          detail=f"{ngay}: {so_nguoi} người — {ly_do}")
        self.repo.commit()
        return self.quan_so_ngay(department_id, ngay)

    def khoang_tai_to(self, rows: list[dict] | None = None) -> list[dict]:
        """Mức dùng NGƯỜI của từng tổ theo từng khoảng giờ — nền để Gantt tô và để detector phán.

        MỘT nguồn sự thật cho cả hai: bảng Gantt tô đỏ chỗ nào thì detector `qua_tai_to` chặn đúng
        chỗ đó. Hai nơi tự quét lấy là kiểu gì cũng có ngày Gantt xanh mà cửa phát hành đỏ.

        Quét theo MỐC (sweep-line): cắt trục thời gian tại mọi điểm bắt-đầu / kết-thúc của tổ, mỗi
        khoảng giữa hai mốc có mức dùng không đổi. So từng cặp việc sẽ sai — ba việc 3+3+3 người
        chồng nhau từng đôi vẫn vừa quân số 9.

        Quân số 0 mà KHÔNG ai gõ đè = **chưa khai nhân sự**, bỏ qua tổ đó: chặn vì thiếu dữ liệu ở
        phân hệ khác là kiểu báo đỏ dạy người dùng bỏ qua báo đỏ. Gõ đè 0 thì khác — đó là câu
        người ta nói ra ("cả tổ nghỉ") ⇒ vẫn tính.
        """
        rows = self.danh_sach()["items"] if rows is None else rows
        theo_to: dict[int, list[dict]] = {}
        for r in rows:
            if r.get("trang_thai") != TT_DA_XEP or not r.get("department_id"):
                continue
            if not r.get("start_at") or not r.get("finish_at"):
                continue
            theo_to.setdefault(r["department_id"], []).append(r)

        # Nhớ quân số trong PHẠM VI một lần gọi: một bàn lịch dày là hàng trăm khoảng, mỗi khoảng
        # 3 query nếu tra lại. Cache chết theo hàm nên không bao giờ ôi.
        nho: dict[tuple[int, date], dict] = {}

        def _qs(dept: int, d: date) -> dict:
            if (dept, d) not in nho:
                nho[(dept, d)] = self.quan_so_ngay(dept, d)
            return nho[(dept, d)]

        ra: list[dict] = []
        for dept_id, rs in theo_to.items():
            mocs = sorted({_aware(r["start_at"]) for r in rs}
                          | {_aware(r["finish_at"]) for r in rs})
            for i in range(len(mocs) - 1):
                s, e = mocs[i], mocs[i + 1]
                chay = [r for r in rs
                        if _aware(r["start_at"]) <= s and _aware(r["finish_at"]) >= e]
                if not chay:
                    continue
                dung = sum(int(r.get("so_nhan_cong") or 1) for r in chay)
                qs = _qs(dept_id, s.date())
                if qs["so_nguoi"] <= 0 and not qs["go_de"]:
                    continue                    # chưa khai nhân sự — không kết luận
                ra.append({
                    "department_id": dept_id,
                    "department_ten": chay[0].get("department_ten"),
                    "start": _naive(s), "finish": _naive(e),
                    "dung": dung, "quan_so": qs["so_nguoi"],
                    "qua_tai": dung > qs["so_nguoi"],
                    "dong_ids": [r["id"] for r in chay],
                })
        return ra

    def nguoi_tang_giua(self) -> list[dict]:
        """Người thuộc khối SX nhưng gắn ở TẦNG GIỮA — không nằm trong tổ lá nào (mục I).

        Ai gắn ở "Xưởng in" (nút cha) thì KHÔNG được cộng vào tổ con nào: cộng vào là đếm thừa
        người, và lịch hứa một năng lực không có thật. Nhưng im lặng bỏ họ cũng sai kiểu khác —
        quỹ giờ-người hụt so với thực tế mà không ai biết vì sao.

        Nên: không đếm, nhưng NÓI RA. Màn xếp lịch hiện dòng nhắc *"2 người thuộc Xưởng in chưa
        gắn tổ"* để người quản lý đi gắn, chứ không phải để hệ thống tự đoán hộ.
        """
        repo = DepartmentRepository(self.db)
        tos = {d.id for d in repo.to_san_xuat()}
        giua = [d for d in repo.production_departments(fallback_all=False) if d.id not in tos]
        if not giua:
            return []
        dem = dict(self.db.execute(
            select(Employee.department_id, func.count())
            .where(
                Employee.department_id.in_([d.id for d in giua]),
                Employee.status.in_((EMP_ACTIVE, EMP_PROBATION, EMP_PROBATION_ENDED)),
            )
            .group_by(Employee.department_id)
        ).all())
        return [
            {"department_id": d.id, "department_ten": d.name, "so_nguoi": int(dem[d.id])}
            for d in giua if dem.get(d.id)
        ]

    def gio_ca_cua_to(self, department_id: int, ngay: date) -> float:
        """Số GIỜ ca của tổ trong một ngày — theo ca CHUNG của xưởng.

        Ca riêng của tổ đã bỏ (2026-08-10): ca khai một chỗ duy nhất ở Nhân sự → Ca kíp.
        `department_id` giữ trong chữ ký vì quỹ giờ-người vẫn tính theo TỔ
        (quân số của tổ), chỉ có số GIỜ là dùng chung.
        """
        lich = self.lich
        return round(sum(
            (e - s).total_seconds() / 3600.0 for s, e in lich._khung_ngay(ngay)
        ), 2)

    def quy_gio_nguoi(self, department_id: int, ngay: date) -> dict:
        """Quỹ giờ-người của tổ trong ngày = quân số × giờ ca CỦA TỔ.

        Nhân với giờ ca của tổ chứ không phải của xưởng: tổ chạy 1 ca mà lấy 2 ca là tự cho mình
        gấp đôi năng lực, rồi lịch nhận thêm việc trên một quỹ không có thật.
        """
        qs = self.quan_so_ngay(department_id, ngay)
        gio = self.gio_ca_cua_to(department_id, ngay)
        return {**qs, "gio_ca": gio, "quy_gio_nguoi": round(qs["so_nguoi"] * gio, 2)}

    # ================= TẦNG KẾ HOẠCH TUẦN (mục J) =================

    def ke_hoach_tuan(self, *, tu: date, so_tuan: int = 4) -> dict:
        """Tải theo TUẦN của từng nhóm máy / tổ — bảng thô, KHÔNG xếp giờ, tính lúc đọc.

        Câu hỏi màn này trả lời là "tuần sau còn nhận thêm việc được không", chứ không phải "việc
        nào chạy lúc mấy giờ" — nên nó cố tình KHÔNG có lịch giờ.

        **Cần** gồm cả việc CHƯA XẾP: việc chưa có giờ tính vào tuần chứa HẠN của nó. Chỉ đếm việc
        đã xếp thì bảng báo "còn rỗng" trong khi hàng chờ đang đầy — đúng cái sai khiến người ta
        nhận thêm đơn rồi vỡ trận.

        **Khả dụng**: máy = Σ giờ ca × ngày làm − vùng khóa (vùng mở thêm đã nằm trong khung giờ);
        tổ = Σ quỹ giờ-người các ngày trong tuần.
        """
        rows = self.repo.list_dong()
        lsx_map, bg_map, may_map = self._nap_lo(rows)
        dur = {r.id: self._thoi_luong(r, bg=bg_map.get(r.bai_ghep_id)) for r in rows}

        dau_tuan = tu - timedelta(days=tu.weekday())          # về thứ Hai
        tuans = [dau_tuan + timedelta(weeks=i) for i in range(max(1, so_tuan))]
        khoa_tuan = {t: i for i, t in enumerate(tuans)}

        def _tuan_cua(d: date | None) -> date | None:
            if d is None:
                return None
            t = d - timedelta(days=d.weekday())
            return t if t in khoa_tuan else None

        # Máy gom theo NHÓM (`may_thiet_bi.loai_may`), không theo từng máy lẻ — plan viết
        # *"nhóm Máy in 92/88 giờ · nhóm Bế 60/80"*. Xưởng có 3 máy in thì câu hỏi thật là "khâu in
        # tuần sau còn chỗ không", chứ không phải "máy in số 2 còn chỗ không": việc chuyển giữa các
        # máy cùng nhóm là chuyện thường. Bảng theo từng máy lẻ vừa dài vừa trả lời sai câu hỏi.
        # Máy chưa khai nhóm → lấy tên máy làm nhóm riêng, không dồn chung vào một rổ "(trống)".
        may_all = self._may_by_ids({r.may_id for r in rows if r.may_id})
        nhom_cua_may = {
            i: ((m.loai_may or "").strip() or m.ten) for i, m in may_all.items()
        }
        may_theo_nhom: dict[str, set[int]] = {}
        for i, nhom in nhom_cua_may.items():
            may_theo_nhom.setdefault(nhom, set()).add(i)

        # --- CẦN: gom giờ theo (tuần, loại, khoá) — khoá máy là TÊN NHÓM, khoá tổ là id ---
        can: dict[tuple[date, str, object], float] = {}
        for r in rows:
            gio = _f(dur[r.id]["chiem_may_phut"]) / 60.0
            if gio <= 0:
                continue
            if r.may_id:
                loai, khoa = "may", nhom_cua_may.get(r.may_id)
                if khoa is None:
                    continue
            elif r.department_id:
                # Tổ tính theo GIỜ-NGƯỜI: một việc 5 người trong 2 giờ ăn 10 giờ-người của quỹ.
                loai, khoa = "to", r.department_id
                gio *= max(1, int(self._so_nguoi_dong(r) or 1))
            else:
                continue
            ngay = _aware(r.start_at).date() if r.start_at else self._han(lsx_map.get(r.lsx_id))
            t = _tuan_cua(ngay)
            if t is None:
                continue
            can[(t, loai, khoa)] = can.get((t, loai, khoa), 0.0) + gio

        # --- KHẢ DỤNG + dựng dòng ---
        nhoms = sorted({k for (_t, loai, k) in can if loai == "may"})
        to_ids = sorted({k for (_t, loai, k) in can if loai == "to"})
        to_ten = self._dept_names(set(to_ids))

        items: list[dict] = []
        for t in tuans:
            ngays = [t + timedelta(days=i) for i in range(7)]
            for nhom in nhoms:
                # Khả dụng của NHÓM = tổng khả dụng các máy trong nhóm (mỗi máy đã trừ vùng khóa).
                kd = sum(
                    self._gio_kha_dung_may(mid, d)
                    for mid in may_theo_nhom.get(nhom, ())
                    for d in ngays
                )
                items.append(self._dong_tuan(t, "may", None, nhom,
                                             can.get((t, "may", nhom), 0.0), kd, nhom=nhom))
            for rid in to_ids:
                kd = sum(self.quy_gio_nguoi(rid, d)["quy_gio_nguoi"] for d in ngays)
                items.append(self._dong_tuan(t, "to", rid, to_ten.get(rid),
                                             can.get((t, "to", rid), 0.0), kd))
        return {"tu": dau_tuan, "so_tuan": len(tuans), "items": items}

    @staticmethod
    def _dong_tuan(tuan: date, loai: str, res_id: int | None, ten: str | None,
                   can: float, kha_dung: float, nhom: str | None = None) -> dict:
        """Một ô của bảng tuần. Ngưỡng: ≥100% đỏ · ≥85% vàng · còn lại xanh.

        Khả dụng 0 (tổ chưa khai ai, máy nghỉ cả tuần) mà vẫn có việc ⇒ ĐỎ, không phải chia-cho-0:
        xếp việc vào một tài nguyên không có giờ nào chính là thứ cần báo to nhất.
        """
        pct = round(can / kha_dung * 100, 1) if kha_dung > 0 else (999.0 if can > 0 else 0.0)
        mau = "do" if pct >= 100 else "vang" if pct >= 85 else "xanh"
        return {
            "tuan": tuan, "iso_tuan": tuan.isocalendar()[1],
            # Máy: `res_id=None` + `nhom` = tên nhóm (bảng gom theo NHÓM, không theo máy lẻ).
            # Tổ:  `res_id` = id phòng ban, `nhom=None`.
            "loai": loai, "res_id": res_id, "nhom": nhom, "ten": ten or f"#{res_id}",
            "can_gio": round(can, 1), "kha_dung_gio": round(kha_dung, 1),
            "pct": pct, "mau": mau,
        }

    def _gio_kha_dung_may(self, may_id: int, ngay: date) -> float:
        """Giờ máy chạy được trong một ngày = khung của máy − phần bị vùng KHÓA cắt vào.

        Máy chạy liên tục (2026-08-10) nên trần này là 24h/ngày làm việc: đèn quá tải máy chỉ còn
        sáng khi vùng khoá ăn gần hết ngày. Trần thật của xưởng nằm ở quỹ giờ-NGƯỜI của tổ.
        """
        lich = self._lich_may(may_id)
        chan = self._chan_may(may_id)
        tong = 0.0
        for s, e in lich._khung_ngay(ngay):
            con = (e - s).total_seconds() / 3600.0
            for bs, be in chan:
                lap = (min(e, be) - max(s, bs)).total_seconds() / 3600.0
                if lap > 0:
                    con -= lap
            tong += max(0.0, con)
        return round(tong, 2)

    def _so_nguoi_dong(self, r: XepLichCongDoan) -> int | None:
        """Số người bố trí cho một dòng — bước lệnh đọc `lsx_cong_doan`, bài ghép đọc bước chung."""
        buoc = (
            self._lcd(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
            else self.db.get(BaiGhepCongDoan, r.bai_ghep_cong_doan_id)
            if r.bai_ghep_cong_doan_id else None
        )
        return int(getattr(buoc, "so_nhan_cong", 1) or 1) if buoc else None

    def _khoang_may(self, may_id: int | None, kieu: str) -> tuple[tuple[datetime, datetime], ...]:
        if not may_id:
            return ()
        return tuple(
            (_aware(p.unavailable_from), _aware(p.unavailable_to))
            for p in self.unavail_repo.list_by_may(may_id)
            if (getattr(p, "kieu", KIEU_CHAN) or KIEU_CHAN) == kieu
        )

    def _chan_may(self, may_id: int | None) -> tuple[tuple[datetime, datetime], ...]:
        """Các khoảng KHÓA của máy (bảo trì/hỏng/nghỉ) — tz-aware, để engine né khi cộng giờ / tìm khe.

        CHỈ kiểu `chan` (mg 0179): khoảng `mo_them` là giờ làm CỘNG THÊM, đi qua `LichXuong`, trả
        nó về đây thì máy tự khoá đúng vào lúc được mở thêm.
        """
        return self._khoang_may(may_id, KIEU_CHAN)

    def _mo_them_may(self, may_id: int | None) -> tuple[tuple[datetime, datetime], ...]:
        """Khoảng máy chạy THÊM ngoài ca (mg 0179) — hoà vào khung giờ làm của riêng máy đó."""
        return self._khoang_may(may_id, KIEU_MO_THEM)

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
        """{chiem_may_phut(+_min/_max), tong_phut, setup_phut, chay_phut, theo_may, canh_bao}.

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

    def _sl_tinh(self, lcd, may):
        """SL vào của bước quy về đơn vị TỐC ĐỘ — cùng một hàm với drawer lệnh.

        Bắt buộc đi qua `LsxService.sl_tinh_cua_buoc`: xếp lịch tự suy đích hay tự nhân hệ số là
        Gantt và màn lệnh chia hai số khác nhau, mà chênh giờ thì không ai soi ra ngay.
        """
        from .bien_cong_thuc import quy_cach_bien

        lsx = self.lsx_repo.get(lcd.lsx_id) if getattr(lcd, "lsx_id", None) else None
        qc = quy_cach_bien(lsx) if lsx is not None else {}
        return self.bg_svc._lsx_svc().sl_tinh_cua_buoc(lcd, may, qc)

    def _thoi_luong_noi_bo(
        self, dong: XepLichCongDoan, lcd: LsxCongDoan | BaiGhepCongDoan,
    ) -> dict:
        """Bước THEO MÁY — dùng chung cho bước của lệnh lẫn bước chạy chung của bài, vì cả hai đều
        là "một bước có kế hoạch" với cùng bộ trường (`BaiGhepCongDoan` mirror `LsxCongDoan`).

        Từ 2026-08-04 hàm này KHÔNG tự tính nữa mà ủy thác cho `thoi_luong_buoc(lcd, may)` — công
        thức chỉ còn MỘT bản, khỏi cảnh hai nơi tính hai kiểu rồi lệch nhau::

            thời lượng = thời gian khác + chuẩn bị (từ MÁY) + SL vào × 60 ÷ tốc độ × số lượt

        `min`/`max` là cùng công thức với tốc độ tối đa / tối thiểu của máy → Gantt vẽ râu ở đuôi
        thanh. `theo_may` = tính được từ máy đang gán; sai thì `canh_bao` nói vì sao (máy chưa khai
        tốc độ / đơn vị lệch) để UI nhắc, thay vì im lặng ra số 0."""
        may = self.db.get(MayThietBi, dong.may_id) if dong.may_id else None
        t = thoi_luong_buoc(lcd, may, self._sl_tinh(lcd, may))
        pp = t["dien_giai"]["phuong_phap"]
        canh_bao = None
        if pp == "thieu_nang_suat":
            canh_bao = "may_chua_toc_do"
        elif pp == "chua_quy_doi":
            canh_bao = "chua_quy_doi"
        return {
            "chiem_may_phut": t["chiem_may_phut"],
            "chiem_may_phut_min": t["chiem_may_phut_min"],
            "chiem_may_phut_max": t["chiem_may_phut_max"],
            "tong_phut": t["tong_phut"],
            "setup_phut": t["dien_giai"]["setup_phut"],
            "chay_phut": t["chay_phut"],
            "phat_sinh_phut": t["dien_giai"]["phat_sinh_phut"],
            "theo_may": pp == "may",
            "canh_bao": canh_bao,
        }

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

    def _chan_chua_giu_du(self, *, ma: str, lsx_id: int | None = None,
                          bai_ghep_id: int | None = None) -> None:
        """DÂY KHOÁ THỨ HAI: chưa giữ đủ vật tư thì chưa được vào kế hoạch (17/08/2026).

        Cả mạch chỉ có một chiều — `ghép bài → giữ chỗ → xếp lịch`. Chặn ở đây là thứ làm cho lịch
        đáng tin: **đã xếp lịch nghĩa là vật tư đã có chủ**, không còn chuyện lệnh khác lĩnh mất rồi
        lịch thành lịch ma mà không ai báo.

        Điểm đẹp của giữ chỗ: nó chỉ cần SỐ LƯỢNG, không cần ngày. Nên cửa này không phải hỏi lại
        "bao giờ cần" — vòng luẩn quẩn *xếp lịch mới biết ngày cần / ngày cần mới biết đủ hay thiếu*
        bị cắt ở đây.

        Service giữ chỗ dựng TRỄ (chỉ khi thật sự chặn tới) vì nó kéo theo cả bảng cân đối; và bọc
        `try` để bảng cân đối hỏng KHÔNG khoá chết cả bàn xếp lịch — nhưng hỏng thì NÓI ra chứ
        không im lặng cho qua, im lặng ở đây là mở cửa cho lệnh không có giấy.
        """
        try:
            from ..repositories.bai_ghep_repo import BaiGhepRepository
            from ..repositories.don_vi_do_repo import DonViDoRepository
            from ..repositories.lsx_repo import LsxRepository
            from ..repositories.purchase_repo import (
                PurchaseRequestRepository, SupplierRepository,
            )
            from ..repositories.stock_lot_repo import StockLotRepository
            from ..repositories.stock_request_repo import StockRequestRepository
            from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
            from .giu_cho_service import GiuChoService
            from .ke_hoach_vat_tu_service import KeHoachVatTuService
            from .vat_lieu_kho_service import VatLieuKhoService

            kh = KeHoachVatTuService(
                self.db, lsx_repo=LsxRepository(self.db),
                bai_ghep_repo=BaiGhepRepository(self.db),
                hang=VatLieuKhoService(VatLieuKhoRepository(self.db),
                                       DonViDoRepository(self.db)),
                lots=StockLotRepository(self.db), requests=StockRequestRepository(self.db),
                purchases=PurchaseRequestRepository(self.db),
                suppliers=SupplierRepository(self.db), don_vi=DonViDoRepository(self.db),
            )
            tt = GiuChoService(self.db, kh).trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
        except Exception as exc:                                    # noqa: BLE001
            raise XepLichConflict(
                f"Chưa kiểm được vật tư của {ma} ({type(exc).__name__}) — mở màn Kế hoạch vật tư "
                "xem lỗi thật rồi thử lại. Không xếp lịch khi chưa biết có đủ hàng hay không."
            ) from None
        if tt["du"]:
            return
        if not tt["bat"]:
            raise XepLichConflict(
                f"{ma} chưa giữ chỗ vật tư — vào màn Kế hoạch vật tư bấm Giữ chỗ trước khi xếp lịch."
            )
        if tt["khong_ro"]:
            raise XepLichConflict(
                f"{ma} có vật tư chưa quy đổi được về đơn vị kho nên không biết cần bao nhiêu — "
                "kiểm lại đơn vị của mặt hàng ở màn Kế hoạch vật tư."
            )
        raise XepLichConflict(
            f"{ma} mới giữ được một phần vật tư, còn thiếu {len(tt['thieu'])} mặt hàng — "
            "lập yêu cầu mua ở màn Kế hoạch vật tư, hàng về là hệ tự giữ nốt."
        )

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
        self._chan_chua_giu_du(lsx_id=lsx_id, ma=lsx.ma)
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
        self._chan_chua_giu_du(bai_ghep_id=bg.id, ma=bg.ma)
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
            dong.finish_at = _cong_gio_lam(
                start, chiem, self._lich_dong(dong), self._chan_may(dong.may_id)
            )
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
        now = _gio_xuong()
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
            ef = _cong_gio_lam(es, chiem, self._lich_dong(r)) if chiem > 0 else es
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
                ls = _lui_gio_lam(lf, chiem, self._lich_dong(r)) if chiem > 0 else lf
                info[r.id]["muon_nhat"] = lf
                if i > 0:
                    cho_truoc = dur[rows[i - 1].id]["tong_phut"] - dur[rows[i - 1].id]["chiem_may_phut"]
                    lf = ls - timedelta(minutes=cho_truoc)
        # --- độ dư + nhãn ---
        today = _gio_xuong().date()
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
            ef = _cong_gio_lam(es, chiem, self._lich_dong(r)) if chiem > 0 else es
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
            ls = _lui_gio_lam(lf, chiem, self._lich_dong(r)) if chiem > 0 else lf
            lag = dur[rid]["tong_phut"] - chiem
            latest_start[rid] = ls - timedelta(minutes=lag)

        today = _gio_xuong().date()
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

    def _may_lam_duoc(self, dong: XepLichCongDoan) -> list[MayThietBi]:
        """Máy LÀM ĐƯỢC công đoạn của dòng — theo `cong_doan.nhom_may_cho_phep` (khớp `may.loai_may`).

        Chưa khai ràng buộc ⇒ MỌI máy. Máy đang gán luôn có mặt kể cả khi sai loại, không thì gợi
        ý tự loại chính lựa chọn hiện tại và người dùng tưởng mình gán bậy.

        LỌC `active` (cột thêm lại ở mg `0202`, 15/08/2026 — lần này CÓ ô nhập, là nút "Ngừng dùng"
        của màn Máy): máy đã thanh lý thì đừng mời xếp việc vào. Khác hẳn cột `trang_thai` gỡ hồi
        11/08 — cái đó trộn ba nghĩa và không ô nhập nào nên lọc chẳng loại được gì.

        Máy dừng TẠM (bảo trì, hỏng) vẫn `active=True` và bị loại đúng chỗ khác: engine né
        `machine_unavailable_periods` khi tìm khe, nên máy đang khoá không ra khe sớm.

        Máy ĐANG GÁN luôn có mặt kể cả khi đã ngừng dùng — không thì mở một lệnh cũ ra là ô máy
        trống trơn và người xếp lịch tưởng chưa ai gán.
        """
        cd = None
        if dong.nguon == NGUON_LSX:
            lcd = self._lcd(dong.lsx_cong_doan_id)
            cd = self.db.get(CongDoan, lcd.cong_doan_id) if lcd and lcd.cong_doan_id else None
        elif dong.bai_ghep_cong_doan_id:
            bgcd = self.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
            cd = self.db.get(CongDoan, bgcd.cong_doan_id) if bgcd and bgcd.cong_doan_id else None
        allow = (getattr(cd, "nhom_may_cho_phep", None) or []) if cd is not None else []
        mays = [m for m in self.db.execute(select(MayThietBi)).scalars()
                if m.active or m.id == dong.may_id]
        if allow:
            mays = [m for m in mays if m.loai_may in allow or m.id == dong.may_id]
        return mays

    def goi_y(self, *, dong_id: int) -> dict:
        """Gợi ý MÁY cho một dòng — top 3 sắp theo **GIỜ XONG**, không phải theo giờ trống.

        Máy rảnh sớm hơn CHƯA CHẮC xong sớm hơn: tốc độ khai theo từng máy, máy chậm rảnh lúc 8h
        vẫn có thể xong sau máy nhanh rảnh lúc 10h. Sắp theo giờ trống là đưa ra lời khuyên sai
        đúng lúc người ta tin nó nhất.

        Chạy được CẢ KHI CHƯA GÁN MÁY — đúng lúc cần gợi ý nhất. Trước đây hàm này chỉ tìm khe trên
        chính máy đã gán, nên dòng trắng máy hỏi gì cũng ra rỗng.
        """
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
            han_lui = _lui_gio_lam(muon, chiem, self._lich_may(may_id), chan)
        return {
            "may_id": may_id,
            "khe_trong": khe,
            "finish_neu_xep": (
                _cong_gio_lam(khe, chiem, self._lich_may(may_id), chan) if khe else None
            ),
            "han_lui": han_lui,
            "goi_y_may": self._top_may(dong, som=som, exclude_id=dong_id),
        }

    def _top_may(self, dong: XepLichCongDoan, *, som: datetime, exclude_id: int,
                 top: int = 3) -> list[dict]:
        """Top máy làm được công đoạn, sắp theo GIỜ XONG tăng dần.

        Thời lượng tính LẠI theo TỪNG máy (`thoi_luong_buoc(lcd, may)`): tốc độ và thời gian chuẩn
        bị là thuộc tính của MÁY, nên cùng một bước trên hai máy ra hai con số khác nhau — dùng
        chung một thời lượng thì bảng gợi ý chỉ đang so "máy nào rảnh trước", đúng cái sai cần tránh.

        Máy KHÔNG hợp khổ vẫn liệt kê (kèm cờ) nhưng bị đẩy xuống cuối: chặn cứng ở đây là quyết
        thay người, mà chủ đã chốt "máy đề xuất, người quyết".
        """
        lcd = (
            self._lcd(dong.lsx_cong_doan_id) if dong.nguon == NGUON_LSX
            else self.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
            if dong.bai_ghep_cong_doan_id else None
        )
        if lcd is None:
            return []
        qc = None
        lsx = None
        if dong.lsx_id:
            lsx = self.lsx_repo.get(dong.lsx_id)
            qc = lsx.quy_cach_json if lsx else None
        gom = self._gom_key(lsx)
        ra: list[dict] = []
        for may in self._may_lam_duoc(dong):
            chiem = thoi_luong_buoc(lcd, may, self._sl_tinh(lcd, may))["chiem_may_phut"]
            if chiem <= 0:
                continue                      # máy chưa khai tốc độ → không hứa được giờ xong nào
            khe = self._khe_trong(may.id, som, chiem, exclude_id=exclude_id)
            if khe is None:
                continue
            khong_hop_kho = bool(kiem_kha_nang(qc, may))
            ra.append({
                "may_id": may.id,
                "may_ten": may.ten,
                "khe_trong": khe,
                "finish": _cong_gio_lam(
                    khe, chiem, self._lich_may(may.id), self._chan_may(may.id)
                ),
                "chiem_may_phut": round(chiem, 2),
                "khong_hop_kho": khong_hop_kho,
                # (E) Việc NGAY TRƯỚC khe này trên máy đó có cùng giấy · khổ · bộ mực không.
                "cung_gom": self._lien_ke_cung_gom(may.id, khe, gom, exclude_id=exclude_id),
            })
        # Máy không hợp khổ xuống cuối; còn lại theo GIỜ XONG, hoà giờ thì ưu tiên máy đang chạy
        # VIỆC CÙNG LOẠI (mục E) — đổi từ việc cùng giấy/khổ/mực sang nhau gần như khỏi canh lại máy.
        # Gom là TIÊU CHÍ PHỤ, không được lật ngược thứ tự giờ xong: sớm hơn vẫn thắng.
        ra.sort(key=lambda d: (d["khong_hop_kho"], d["finish"], not d["cung_gom"]))
        return ra[:top]

    def _lien_ke_cung_gom(self, may_id: int, khe: datetime, gom: str | None,
                          *, exclude_id: int) -> bool:
        """Việc chạy NGAY TRƯỚC `khe` trên máy này có cùng khoá gom (giấy · khổ · bộ mực) không.

        Nền cho mục E ở nhánh GỢI Ý: xếp việc ngay sau một việc cùng loại thì thợ gần như không
        phải canh lại máy — cùng giấy nên không chỉnh nạp, cùng khổ nên không chỉnh nhíp, cùng bộ
        mực nên không rửa lô.

        Chỉ xét việc LIỀN TRƯỚC, không xét cả ngày: lợi ích của việc gom nằm ở chỗ hai việc chạy
        SÁT nhau. Cách nhau ba job thì máy đã bị canh lại giữa chừng rồi, gom hay không cũng thế.
        """
        if not gom:
            return False
        truoc = None
        for r in self.repo.rows_da_xep_co_may():
            if r.may_id != may_id or r.id == exclude_id or not r.finish_at:
                continue
            f = _aware(r.finish_at)
            if f <= khe and (truoc is None or f > _aware(truoc.finish_at)):
                truoc = r
        if truoc is None or not truoc.lsx_id:
            return False
        return self._gom_key(self.lsx_repo.get(truoc.lsx_id)) == gom

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
        lich = self._lich_may(may_id)
        cur = _dau_ca(tu, lich)
        for s, e in ban:
            if e <= cur:
                continue
            if _cong_gio_lam(cur, chiem, lich, chan) <= s:
                return cur
            cur = _dau_ca(e, lich)
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

    def _canh_bao_tha(self, dong: XepLichCongDoan, may_id: int | None,
                      start: datetime | None, finish: datetime | None,
                      ly_do_kho: list[str]) -> list[dict]:
        """Bốn thứ người kéo thanh cần biết NGAY lúc thả, gom vào MỘT danh sách `{loai, chu}`.

        Vì sao bồi vào `xem_truoc` chứ không viết lớp cảnh báo mới: đường kéo-thả ĐÃ gọi xem-trước
        trước khi ghi (`GanttBoard.onBarDown`). Dựng đường thứ hai là hai nơi cùng phán một việc,
        kiểu gì cũng có ngày hộp thoại nói khác cái Gantt tô.

        KHÔNG chặn — chỉ cửa Phát hành mới chặn. Nhưng im lặng thì người kéo không hề biết mình
        vừa thả vào giữa khoảng bảo trì, hay vào 2h sáng chủ nhật.
        """
        out: list[dict] = []
        if start is None:
            return out
        lich = self._lich_may(may_id) if may_id else self.lich
        het = finish or start

        # 1) Đè vùng khóa máy. `_cong_gio_lam` tự nhảy qua ⇒ giờ CHẠY THẬT lệch giờ vừa thả.
        for p in (self.unavail_repo.list_by_may(may_id) if may_id else []):
            if (getattr(p, "kieu", KIEU_CHAN) or KIEU_CHAN) != KIEU_CHAN:
                continue
            ps, pe = _aware(p.unavailable_from), _aware(p.unavailable_to)
            if ps < het and start < pe:
                ly = f" ({p.reason})" if getattr(p, "reason", None) else ""
                out.append({"loai": CB_KHOA_MAY,
                            "chu": (f"Đè khoảng khóa máy {_fmt_gio(ps)}–{_fmt_gio(pe)}{ly}"
                                    " — máy chỉ chạy ngoài khoảng này")})

        # 2) Ngoài giờ làm. Bước có máy chạy liên tục nên chỉ vướng ngày nghỉ/lễ; bước tay của tổ
        #    mới thật sự vướng ca.
        thuc = _dau_ca(start, lich)   # CỐ Ý không dùng `_vao_gio_lam`: nó nhảy qua cả vùng khóa,
        if thuc > start:              # mà vùng khóa đã có câu riêng ở trên — nói hai lần là nhiễu.
            out.append({"loai": CB_NGOAI_GIO,
                        "chu": f"Ngoài giờ làm — việc chỉ bắt đầu được lúc {_fmt_gio(thuc)}"})

        # 3) Quân số tổ. Tái dùng NGUYÊN `khoang_tai_to` (quét theo mốc) thay vì so từng cặp: ba
        #    việc 3+3+3 người chồng nhau từng đôi vẫn vừa tổ 9 người. Chỉ nạp dòng CÙNG TỔ có giao
        #    khoảng — kéo cả bàn lịch cho mỗi lần thả chuột là quá đắt.
        dept = dong.department_id
        if dept and finish is not None:
            gia_dinh = [{"id": dong.id, "trang_thai": TT_DA_XEP, "department_id": dept,
                         "department_ten": None, "start_at": _naive(start),
                         "finish_at": _naive(finish), "so_nhan_cong": self._so_nguoi_dong(dong)}]
            for r in self.repo.rows_da_xep_theo_to(dept):
                if r.id == dong.id:
                    continue
                if _aware(r.start_at) >= finish or start >= _aware(r.finish_at):
                    continue
                gia_dinh.append({"id": r.id, "trang_thai": TT_DA_XEP, "department_id": dept,
                                 "department_ten": None, "start_at": r.start_at,
                                 "finish_at": r.finish_at, "so_nhan_cong": self._so_nguoi_dong(r)})
            for k in self.khoang_tai_to(gia_dinh):
                if k["qua_tai"]:
                    out.append({"loai": CB_THIEU_NGUOI,
                                "chu": (f"Tổ thiếu người từ {_fmt_gio(_aware(k['start']))}: cần "
                                        f"{k['dung']} người, có mặt {k['quan_so']}")})
                    break                      # một câu là đủ; liệt kê mọi khoảng chỉ làm dài hộp

        # 4) Khổ / số màu / định lượng vượt máy — CẢNH BÁO, không chặn (chốt 18/08/2026).
        out += [{"loai": CB_KHO_MAY, "chu": c} for c in ly_do_kho]
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
                finish = (_cong_gio_lam(start, chiem, self._lich_may(may_id),
                                        self._chan_may(may_id))
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
            "chay_phut": d["chay_phut"],
            "chiem_may_phut_min": d.get("chiem_may_phut_min", chiem),
            "chiem_may_phut_max": d.get("chiem_may_phut_max", chiem),
            "theo_may": d.get("theo_may", False),
            "xung_dot_ids": xung_dot, "day_doi": day_doi,
            "han_hoan_thanh_moi": han_moi, "nhan_rui_ro": nhan,
            "can_xac_nhan": bool(ly_do_xn), "ly_do_xac_nhan": ly_do_xn,
            "canh_bao": self._canh_bao_tha(dong, may_id, start, finish, ly_do_xn),
        }

    # ================= CHÈN LỆNH GẤP & ĐẨY (G1) =================

    def _chiem_tren_may(self, dong: XepLichCongDoan, may_id: int) -> float:
        """Thời lượng chiếm máy của `dong` NẾU chạy trên `may_id` — tính tạm, không đổi DB."""
        with self.db.no_autoflush:
            cu = dong.may_id
            dong.may_id = may_id
            try:
                return self._thoi_luong(dong)["chiem_may_phut"]
            finally:
                dong.may_id = cu

    def chen_xem_truoc(self, *, dong_id: int, may_id: int | None, tai: datetime) -> dict:
        """Xem trước việc CHÈN một dòng vào máy tại mốc `tai` — **KHÔNG đụng DB** (mục G1).

        Hôm nay chen lệnh gấp vào ngày đã kín nghĩa là kéo tay từng việc, mỗi lần một lần báo đỏ
        trùng máy, tự nhìn hạn bằng mắt. Hàm này trả về TRỌN bảng *giờ cũ → giờ mới* để người xếp
        nhìn một lần rồi quyết; ghi thật là việc của `gan_loat` sau khi bấm Lưu.

        Bốn luật, đều là chỗ dễ làm sai:

        1. **Không cắt đôi việc đang xếp.** `tai` rơi vào giữa một việc thì mốc chèn nhích tới lúc
           việc đó xong — chèn ở RANH GIỚI, không xẻ ngang.
        2. **Việc sau chỉ lùi VỪA ĐỦ hết chồng lấn**, không lùi cứng bằng thời lượng việc chèn. Gặp
           khe trống đủ nuốt là **dừng lan**: 0126 xong 14:00, 0127 bắt đầu 16:00, chèn việc 2 giờ
           vào 14:00 ⇒ lọt vừa khe, 0127 KHÔNG phải lùi. Lùi cứng sẽ đẩy oan cả dây.
        3. **Đúng MỘT tầng.** Lệnh nào bị đẩy thì CẢ CHUỖI của nó lùi chừng ấy; nhưng bước lùi tới
           mà đụng việc của lệnh thứ ba thì **không đẩy tiếp** — chỉ tô đỏ trong bảng để người
           quyết. Lan tầng ba là kéo cả xưởng đi theo một cái chèn.
        4. **Gặp dòng đã KHÓA thì dừng tại đó** và nói ra. Khóa là người đã chốt; máy tự dời là phá.
        """
        dong = self._get_dong(dong_id)
        may_id = may_id or dong.may_id
        if not may_id:
            raise XepLichValidationError("Chọn máy trước khi chèn")
        tai = _aware(tai)
        if tai is None:
            raise XepLichValidationError("Thiếu mốc giờ để chèn")
        chiem = self._chiem_tren_may(dong, may_id)
        if chiem <= 0:
            raise XepLichValidationError(
                "Chưa tính được thời lượng bước này trên máy đã chọn — khai tốc độ máy trước."
            )
        lich = self._lich_may(may_id)
        chan = self._chan_may(may_id)

        tren_may = sorted(
            (r for r in self.repo.rows_da_xep_co_may()
             if r.may_id == may_id and r.id != dong_id and r.start_at is not None),
            key=lambda r: _aware(r.start_at),
        )
        bat_dau = _vao_gio_lam(tai, lich, chan)
        # Luật 1 — mốc rơi vào GIỮA một việc thì đẩy tới ranh giới sau của việc đó.
        # So sánh NGẶT hai đầu (`s < bat_dau < f`): chèn đúng vào giờ BẮT ĐẦU của một việc chính là
        # "chèn tại ranh giới giữa hai việc" mà plan mô tả — đó là thao tác hợp lệ, phải đẩy việc
        # kia lùi. Dùng `s <= bat_dau` sẽ hiểu nhầm thành cắt đôi rồi nhảy ra SAU nó, tức chèn
        # trượt mất đúng khe người dùng vừa chỉ.
        for r in tren_may:
            s, f = _aware(r.start_at), _aware(r.finish_at)
            if f is not None and s < bat_dau < f:
                bat_dau = _vao_gio_lam(f, lich, chan)
        ket = _cong_gio_lam(bat_dau, chiem, lich, chan)

        ke_hoach: dict[int, datetime] = {dong_id: bat_dau}
        bi_day: list[tuple[XepLichCongDoan, timedelta]] = []
        chan_ly_do: str | None = None
        moc = ket
        for r in tren_may:
            s, f = _aware(r.start_at), _aware(r.finish_at)
            # Việc nằm TRỌN phía trước mốc chèn thì không liên quan — nó đã chạy xong trước khi
            # việc chèn bắt đầu. Thiếu dòng này thì chèn vào 09:00 lại đẩy cả việc 08:00–09:00 đi,
            # vì nó vẫn "bắt đầu trước `moc`".
            if f is not None and f <= bat_dau:
                continue
            if s >= moc:
                break                       # Luật 2 — khe trống nuốt vừa, thôi lan
            if r.is_locked:
                chan_ly_do = "gap_khoa"     # Luật 4
                break
            moi = _vao_gio_lam(moc, lich, chan)
            delta = moi - s
            if delta <= timedelta(0):
                break
            ke_hoach[r.id] = moi
            bi_day.append((r, delta))
            moc = _cong_gio_lam(moi, self._thoi_luong(r)["chiem_may_phut"], lich, chan)

        # Luật 3 — cả chuỗi của lệnh bị đẩy lùi CHỪNG ẤY thời gian, rồi nhích vào giờ làm của
        # chính tài nguyên bước đó. Không nhích thì bước lùi tới có thể rơi vào 2 giờ sáng.
        for r, delta in bi_day:
            if r.nguon != NGUON_LSX or not r.lsx_id:
                continue
            for buoc in self.repo.by_lsx(r.lsx_id):
                if buoc.id in ke_hoach or buoc.start_at is None:
                    continue
                ke_hoach[buoc.id] = _vao_gio_lam(
                    _aware(buoc.start_at) + delta,
                    self._lich_dong(buoc), self._chan_may(buoc.may_id),
                )

        return self._chen_bang(dong, may_id, ke_hoach, chiem, chan_ly_do)

    def _chen_bang(self, dong: XepLichCongDoan, may_id: int, ke_hoach: dict[int, datetime],
                   chiem_chen: float, chan_ly_do: str | None) -> dict:
        """Dựng bảng *giờ cũ → giờ mới* + cờ đụng-việc-khác và trễ-hạn cho `chen_xem_truoc`."""
        tat_ca = {r.id: r for r in self.repo.list_dong()}
        trong_kh = [tat_ca[rid] for rid in ke_hoach if rid in tat_ca]
        lsx_map, bg_map, may_map = self._nap_lo(trong_kh)     # nạp lô, né N+1

        # Khoảng [start, finish) MỚI của từng dòng trong kế hoạch — nền để dò đụng độ.
        khoang: dict[int, tuple[int | None, datetime, datetime]] = {}
        for r in trong_kh:
            moi = ke_hoach[r.id]
            mid = may_id if r.id == dong.id else r.may_id
            ch = (chiem_chen if r.id == dong.id
                  else self._thoi_luong(r, bg=bg_map.get(r.bai_ghep_id))["chiem_may_phut"])
            if ch <= 0:
                continue
            lich = self._lich_may(mid) if mid else self._lich_dong(r)
            khoang[r.id] = (mid, moi, _cong_gio_lam(moi, ch, lich, self._chan_may(mid)))

        # ĐỤNG việc của lệnh THỨ BA: dòng đã xếp, cùng máy, KHÔNG nằm trong kế hoạch mà chồng giờ.
        # Chỉ TÔ ĐỎ chứ không đẩy tiếp (luật 3) — người xếp nhìn rồi tự quyết.
        ngoai = [r for r in self.repo.rows_da_xep_co_may()
                 if r.id not in ke_hoach and r.start_at and r.finish_at]
        ma_ngoai = self._ma_theo_dong(ngoai)
        dung_do: dict[int, list[str]] = {}
        for rid, (mid, s, f) in khoang.items():
            if not mid:
                continue
            for o in ngoai:
                if o.may_id == mid and _aware(o.start_at) < f and s < _aware(o.finish_at):
                    dung_do.setdefault(rid, []).append(ma_ngoai.get(o.id) or f"#{o.id}")

        # TRỄ HẠN: so kết thúc MỚI muộn nhất của từng lệnh với hạn SX của chính lệnh đó.
        fin_theo_lsx: dict[int, datetime] = {}
        for rid, (_m, _s, f) in khoang.items():
            r = tat_ca[rid]
            if r.lsx_id:
                fin_theo_lsx[r.lsx_id] = max(fin_theo_lsx.get(r.lsx_id, f), f)
        tre = {
            lsx_id for lsx_id, f in fin_theo_lsx.items()
            if (han := self._han(lsx_map.get(lsx_id) or self.lsx_repo.get(lsx_id))) is not None
            and f.date() > han
        }

        ma_trong = self._ma_theo_dong(trong_kh, lsx_map=lsx_map, bg_map=bg_map)
        may_ten = {i: m.ten for i, m in may_map.items()}
        may_ten.update({i: m.ten for i, m in self._may_by_ids({may_id}).items()})

        rows: list[dict] = []
        for r in sorted(trong_kh, key=lambda x: ke_hoach[x.id]):
            mid = may_id if r.id == dong.id else r.may_id
            rows.append({
                "id": r.id,
                "lsx_ma": ma_trong.get(r.id),
                "cong_doan_ten": self._ten_buoc(r),
                "may_id": mid,
                "may_ten": may_ten.get(mid),
                "cu": _naive(_aware(r.start_at)),
                "moi": _naive(ke_hoach[r.id]),
                "finish_moi": _naive(khoang[r.id][2]) if r.id in khoang else None,
                "la_viec_chen": r.id == dong.id,
                "tre_han": bool(r.lsx_id and r.lsx_id in tre),
                "dung_do": dung_do.get(r.id, []),
                "is_locked": bool(r.is_locked),
            })
        return {
            "dong_id": dong.id, "may_id": may_id,
            "start_at": _naive(ke_hoach.get(dong.id)),
            "finish_at": _naive(khoang.get(dong.id, (None, None, None))[2]),
            "chiem_may_phut": round(chiem_chen, 2),
            "chan": chan_ly_do,
            "rows": rows,
        }

    def _ma_theo_dong(self, rows: list[XepLichCongDoan], *, lsx_map: dict | None = None,
                      bg_map: dict | None = None) -> dict[int, str | None]:
        """id dòng → MÃ lệnh (hoặc mã bài ghép). Nạp lô nếu chỗ gọi chưa có sẵn map."""
        if lsx_map is None or bg_map is None:
            lsx_map, bg_map, _ = self._nap_lo(rows)
        ra: dict[int, str | None] = {}
        for r in rows:
            if r.nguon == NGUON_LSX:
                lsx = lsx_map.get(r.lsx_id)
                ra[r.id] = lsx.ma if lsx else None
            else:
                bg = bg_map.get(r.bai_ghep_id)
                ra[r.id] = bg.ma if bg else None
        return ra

    def _ten_buoc(self, r: XepLichCongDoan) -> str | None:
        """Tên công đoạn của một dòng lịch — lệnh lấy ở `lsx_cong_doan`, bài ghép ở bước chung."""
        if r.nguon == NGUON_LSX:
            lcd = self._lcd(r.lsx_cong_doan_id)
            return lcd.ten if lcd else None
        bgcd = (self.db.get(BaiGhepCongDoan, r.bai_ghep_cong_doan_id)
                if r.bai_ghep_cong_doan_id else None)
        return bgcd.ten if bgcd else "In chung"

    # ================= LỊCH NỀN + ĐOẠN CHIẾM MÁY (Gantt) =================

    def _doan_chiem(self, start: datetime | None, chiem: float, chan: tuple = (),
                    lich: LichXuong | None = None) -> list[dict]:
        """Chia khối chiếm máy [start, +`chiem` phút LÀM VIỆC] thành các ĐOẠN để Gantt vẽ. Gộp qua khe
        nghỉ ngắn (≤ GOP_KHE_PHUT: nghỉ trưa/giải lao → 1 thanh liền, nền loang), TÁCH qua khe dài
        (ngoài-ca/đêm/ngày-nghỉ = ngắt thật). Dẫn xuất lúc đọc, KHÔNG lưu.

        `lich` = khung giờ của ĐÚNG tài nguyên (mg 0178/0179). Bỏ trống thì lùi về lịch chung —
        thanh sẽ bị cắt theo ca của xưởng thay vì ca của máy, tức vẽ khác với giờ engine đã tính."""
        start = _aware(start)
        if start is None or chiem <= 0:
            return []
        lich = lich or self.lich          # `lich or lich` là no-op — bỏ trống sẽ nổ ở `_dau_ca`
        cur = _dau_ca(start, lich)
        con = float(chiem)
        occ: list[tuple[datetime, datetime]] = []
        for _ in range(5000):
            if con <= 0:
                break
            iv = lich.next_interval(cur)
            if iv is None:
                break
            seg_start, seg_end = iv
            if cur < seg_start:
                cur = seg_start
            blk = _chan_sau(cur, seg_end, chan)
            if blk is not None:
                bs, be = blk
                if bs <= cur:
                    cur = _dau_ca(be, lich)
                    continue
                seg_end = bs
            rong = (seg_end - cur).total_seconds() / 60.0
            lay = min(con, rong)
            occ.append((cur, cur + timedelta(minutes=lay)))
            con -= lay
            cur = _dau_ca(seg_end, lich) if lay >= rong else cur + timedelta(minutes=lay)
        doan: list[dict] = []
        for s, e in occ:
            if doan and (s - doan[-1]["finish"]).total_seconds() / 60.0 <= GOP_KHE_PHUT:
                doan[-1]["finish"] = e
            else:
                doan.append({"start": s, "finish": e})
        return doan

    def lich_nen_may(self, *, may_id: int, tu: date, den: date) -> dict:
        """Nền lịch máy cho Gantt: khoảng CHẠY ĐƯỢC của máy trong [tu, den] + vùng KHÓA máy.

        Máy chạy liên tục (2026-08-10) ⇒ nền = trọn ngày làm việc; ngày nghỉ/lễ vẫn để trống.
        """
        khoang_lam: list[dict] = []
        # Nền vẽ theo lịch CỦA CHÍNH MÁY (mg 0179): máy có vùng mở thêm mà nền vẫn vẽ theo lịch
        # xưởng thì thanh việc nằm ngoài nền — người xem tưởng lịch sai.
        lich = self._lich_may(may_id)
        d = tu
        while d <= den:
            for s, e in lich._khung_ngay(d):
                if s.date() == d:  # mỗi khoảng tính 1 lần theo ngày bắt đầu (đuôi ca đêm thuộc ngày trước)
                    khoang_lam.append({"start": _naive(s), "finish": _naive(e)})
            d = d + timedelta(days=1)
        # `kieu` đi kèm để Gantt vẽ KHÁC MÀU: vùng chặn (máy nghỉ) và vùng mở thêm (máy chạy thêm)
        # là hai chuyện ngược nhau, cùng một màu là đọc ngược ý.
        khoang_khoa = [
            {"start": _naive(p.unavailable_from), "finish": _naive(p.unavailable_to),
             "ly_do": p.reason, "kieu": getattr(p, "kieu", KIEU_CHAN) or KIEU_CHAN}
            for p in self.unavail_repo.list_range(tu=tu, den=den, may_id=may_id)
        ]
        return {"may_id": may_id, "khoang_lam": khoang_lam, "khoang_khoa": khoang_khoa}

    # ---- Vùng khóa máy (bảo trì/hỏng/nghỉ) — CRUD tối thiểu + dải cho Gantt overlay ----

    def _khoa_dict(self, p: MachineUnavailablePeriod) -> dict:
        return {"id": p.id, "may_id": p.may_id, "start": _naive(p.unavailable_from),
                "finish": _naive(p.unavailable_to), "ly_do": p.reason, "note": p.note,
                "kieu": getattr(p, "kieu", KIEU_CHAN) or KIEU_CHAN}

    def vung_khoa_range(self, *, tu: date, den: date) -> list[dict]:
        """Mọi khoảng khóa GIAO [tu, den] (MỌI máy) — Gantt overlay theo từng lane."""
        return [self._khoa_dict(p) for p in self.unavail_repo.list_range(tu=tu, den=den)]

    def list_vung_khoa(self, *, may_id: int) -> list[dict]:
        return [self._khoa_dict(p) for p in self.unavail_repo.list_by_may(may_id)]

    def tao_vung_khoa(self, *, may_id: int, tu: datetime, den: datetime, ly_do: str,
                      note: str | None, actor, kieu: str = KIEU_CHAN) -> dict:
        """Tạo khoảng giờ riêng của máy — `chan` (nghỉ) hoặc `mo_them` (chạy thêm ngoài ca, G3).

        `mo_them` KHÔNG mang lý do nghỉ: "tối thứ Tư chạy thêm 3 tiếng" mà lưu lý do `bao_tri` thì
        đọc lại là hiểu ngược. Ép về `khac` và để phần giải thích cho ô ghi chú.
        """
        tu, den = _aware(tu), _aware(den)
        if tu is None or den is None or tu >= den:
            raise XepLichValidationError("Khoảng khóa không hợp lệ: 'từ' phải trước 'đến'")
        kieu = kieu if kieu in KIEU_KHOANG else KIEU_CHAN
        reason = LY_DO_KHAC if kieu == KIEU_MO_THEM else (ly_do if ly_do in LY_DO_KHOA else LY_DO_BAO_TRI)
        row = self.unavail_repo.add(MachineUnavailablePeriod(
            may_id=may_id, reason=reason, kieu=kieu,
            unavailable_from=tu, unavailable_to=den, note=note, created_by=getattr(actor, "id", None),
        ))
        nhan = "Máy chạy thêm" if kieu == KIEU_MO_THEM else f"Khóa máy {row.reason}"
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_khoa_may",
                          target=f"may:{may_id}", detail=f"{nhan}: {tu}→{den}")
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
            bgcd = None
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
            # Nguồn của hai số dưới KHÁC NHAU theo loại dòng: bước lệnh đọc `lsx_cong_doan`, lượt
            # chạy chung của bài đọc `bai_ghep_cong_doan`. Chỉ đọc `lcd` thì mọi dòng bài ghép ra
            # None ⇒ detector "thiếu người" bỏ qua trọn lượt chạy chung, đúng chỗ nhiều lệnh chạy
            # cùng lúc nên sai là sai to nhất.
            buoc = lcd if r.nguon == NGUON_LSX else bgcd
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
                "chiem_may_phut_min": d.get("chiem_may_phut_min", d["chiem_may_phut"]),
                "chiem_may_phut_max": d.get("chiem_may_phut_max", d["chiem_may_phut"]),
                "setup_phut": d.get("setup_phut", 0.0), "chay_phut": d.get("chay_phut", 0.0),
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
                # --- Nền cho detector số người tối thiểu (G) ---
                "so_nhan_cong": int(getattr(buoc, "so_nhan_cong", 1) or 1) if buoc else None,
                "so_nhan_cong_toi_thieu": (
                    getattr(buoc, "so_nhan_cong_toi_thieu", None) if buoc else None
                ),
                # (E) Khoá GOM việc cùng loại — cùng giấy · cùng khổ tờ in · cùng bộ mực. Hai việc
                # cùng khoá thì đổi từ việc này sang việc kia gần như không phải canh lại máy.
                "gom_key": self._gom_key(lsx),
            })
        if q:
            like = q.strip().lower()
            items = [it for it in items if like in (it["lsx_ma"] or "").lower()
                     or like in (it["cong_doan_ten"] or "").lower()]
        if may_id is not None:
            items = [it for it in items if it["may_id"] == may_id]
        return {"items": items, "total": len(items)}
