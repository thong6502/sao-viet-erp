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
    TT_DA_LAP_KE_HOACH as BG_DA_LAP, TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien,
)
from ..models.department import Department
from ..models.lsx import (
    LB_BAI_GHEP, LB_MAY,
    TT_DA_LAP_KE_HOACH as LSX_DA_LAP, TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan,
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
from ..services.bai_ghep_service import BaiGhepService
from ..services.calendar_service import CalendarService
from ..services.lsx_service import _f, thoi_luong_buoc

NHOM_PRINT = "print"
GIO_BAT_DAU = 8          # 08:00 — giờ bắt đầu ca ngày (giờ nhà máy)
PHUT_LAM_NGAY = 8 * 60   # 8h/ngày làm việc
NGUONG_SAP_TOI_HAN = 2   # độ dư ≤ 2 ngày làm việc → "sắp tới hạn"


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


def _dau_ngay(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, GIO_BAT_DAU, tzinfo=timezone.utc)


def _cuoi_ngay(d: date) -> datetime:
    return _dau_ngay(d) + timedelta(minutes=PHUT_LAM_NGAY)


# ---- Cộng / lùi thời lượng theo GIỜ LÀM VIỆC (nhảy ngày nghỉ) ----

def _dau_ca(dt: datetime, cal: CalendarService) -> datetime:
    """Dời `dt` TỚI thời điểm bắt đầu làm việc hợp lệ SỚM NHẤT ≥ dt."""
    d = dt.date()
    while True:
        if cal.is_working_day(d):
            start, end = _dau_ngay(d), _cuoi_ngay(d)
            if dt < start:
                return start
            if dt < end:
                return dt
        d = d + timedelta(days=1)
        dt = _dau_ngay(d)


def _cuoi_ca(dt: datetime, cal: CalendarService) -> datetime:
    """Dời `dt` VỀ thời điểm kết thúc làm việc hợp lệ MUỘN NHẤT ≤ dt."""
    d = dt.date()
    while True:
        if cal.is_working_day(d):
            start, end = _dau_ngay(d), _cuoi_ngay(d)
            if dt > end:
                return end
            if dt > start:
                return dt
        d = d - timedelta(days=1)
        dt = _cuoi_ngay(d)


def _cong_gio_lam(bat_dau: datetime, phut: float, cal: CalendarService) -> datetime:
    cur = _dau_ca(bat_dau, cal)
    con = float(phut)
    while con > 0:
        rong = (_cuoi_ngay(cur.date()) - cur).total_seconds() / 60.0
        if con <= rong:
            return cur + timedelta(minutes=con)
        con -= rong
        cur = _dau_ca(_cuoi_ngay(cur.date()) + timedelta(minutes=1), cal)
    return cur


def _lui_gio_lam(ket_thuc: datetime, phut: float, cal: CalendarService) -> datetime:
    cur = _cuoi_ca(ket_thuc, cal)
    con = float(phut)
    while con > 0:
        rong = (cur - _dau_ngay(cur.date())).total_seconds() / 60.0
        if con <= rong:
            return cur - timedelta(minutes=con)
        con -= rong
        cur = _cuoi_ca(_dau_ngay(cur.date()) - timedelta(minutes=1), cal)
    return cur


def _thoi_luong_in_ghep(bg: BaiGhep, tong_to: int, may: MayThietBi | None) -> dict:
    """Thời lượng công đoạn IN CHUNG của bài ghép: makeready + số tờ / tốc độ + rửa mực. Không có máy /
    chưa khai tốc độ → 0 (dòng bị chặn `thieu_thoi_luong`)."""
    setup = _f(may.makeready_time_default) if may else 0.0
    ve_sinh = _f(may.thoi_gian_rua_muc) if may else 0.0
    toc_do = _f(may.toc_do) if may else 0.0
    chay = (float(tong_to) / toc_do * 60.0) if toc_do > 0 and tong_to > 0 else 0.0
    chiem = round(setup + chay + ve_sinh, 2)
    return {"chiem_may_phut": chiem, "tong_phut": chiem}


class XepLichService:
    def __init__(self, db: Session, repo, audit: AuditLogRepository) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.lsx_repo = LsxRepository(db)
        self.bg_repo = BaiGhepRepository(db)
        self.bg_svc = BaiGhepService(db, self.bg_repo, audit, None)
        self.cal = CalendarService(CalendarRepository(db), audit)

    # ================= tra cứu phụ trợ =================

    def _get_dong(self, dong_id: int) -> XepLichCongDoan:
        d = self.repo.get(dong_id)
        if d is None:
            raise XepLichNotFound("Không tìm thấy dòng xếp lịch")
        return d

    def _lcd(self, lcd_id: int | None) -> LsxCongDoan | None:
        return self.db.get(LsxCongDoan, lcd_id) if lcd_id else None

    def _may_names(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(ids))).all()
        return {i: n for i, n in rows}

    def _dept_names(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(select(Department.id, Department.name).where(Department.id.in_(ids))).all()
        return {i: n for i, n in rows}

    # ================= THỜI LƯỢNG 1 DÒNG =================

    def _thoi_luong(self, dong: XepLichCongDoan) -> dict:
        """{chiem_may_phut, tong_phut} — nội bộ theo `thoi_luong_buoc`, in ghép theo số tờ/tốc độ."""
        if dong.nguon == NGUON_IN_GHEP:
            bg = self.bg_repo.get(dong.bai_ghep_id) if dong.bai_ghep_id else None
            if bg is None:
                return {"chiem_may_phut": 0.0, "tong_phut": 0.0}
            lsx_map = self.bg_repo.lsx_by_ids([tv.lsx_id for tv in bg.thanh_viens])
            tong_to = self.bg_svc.tinh_so_to(bg, lsx_map)["tong_to"]
            may = self.db.get(MayThietBi, dong.may_id) if dong.may_id else None
            return _thoi_luong_in_ghep(bg, tong_to, may)
        lcd = self._lcd(dong.lsx_cong_doan_id)
        if lcd is None:
            return {"chiem_may_phut": 0.0, "tong_phut": 0.0}
        t = thoi_luong_buoc(lcd)
        return {"chiem_may_phut": t["chiem_may_phut"], "tong_phut": t["tong_phut"]}

    # ================= SINH DÒNG (Đưa vào kế hoạch) =================

    def _dong_moi(self, lsx: Lsx, cd: LsxCongDoan, actor) -> XepLichCongDoan:
        return XepLichCongDoan(
            nguon=NGUON_LSX, lsx_id=lsx.id, lsx_cong_doan_id=cd.id,
            source_thu_tu=cd.thu_tu, loai_buoc=cd.loai_buoc,
            may_id=cd.may_id, department_id=cd.department_id, nha_cung_cap=cd.nha_cung_cap,
            trang_thai=TT_CHO_XEP, created_by=getattr(actor, "id", None),
        )

    def _sinh_dong(self, lsx: Lsx, *, bo_qua_in: bool, actor) -> list[XepLichCongDoan]:
        """Dòng lịch cho mọi công đoạn của LSX, NGOẠI TRỪ: công đoạn in (nếu `bo_qua_in` — đã chạy chung
        ở bài ghép) và bước `bai_ghep` (đặt chỗ pha sau)."""
        out: list[XepLichCongDoan] = []
        for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
            if cd.loai_buoc == LB_BAI_GHEP:
                continue
            if bo_qua_in and cd.nhom == NHOM_PRINT and cd.loai_buoc == LB_MAY:
                continue
            out.append(self._dong_moi(lsx, cd, actor))
        return out

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
        # Dòng in chạy chung — chiếm máy in của bài ghép.
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
        for field in ("may_id", "department_id", "nha_cung_cap", "work_shift_id"):
            if field in patch:
                setattr(dong, field, patch[field])
        if "start_at" in patch:
            dong.start_at = _aware(patch["start_at"])
        chiem = self._thoi_luong(dong)["chiem_may_phut"]
        if dong.start_at is not None and chiem > 0:
            dong.finish_at = _cong_gio_lam(dong.start_at, chiem, self.cal)
        else:
            dong.finish_at = None
        co_tai_nguyen = bool(dong.may_id or dong.department_id or (dong.nha_cung_cap or "").strip())
        if dong.start_at is not None and co_tai_nguyen and chiem > 0:
            dong.trang_thai, dong.blocked_reason = TT_DA_XEP, None
        else:
            dong.trang_thai = TT_CHO_XEP
            dong.blocked_reason = (
                LY_DO_THIEU_THOI_LUONG if chiem <= 0
                else LY_DO_THIEU_MAY if not co_tai_nguyen else LY_DO_CHO_TIEN_DE
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
               han: date | None, dur: dict[int, dict]) -> dict[int, dict]:
        """Forward (sớm nhất) + backward (muộn nhất) + độ dư + nhãn nguy cơ cho chuỗi 1 LSX.

        `dur[dong_id] = {chiem_may_phut, tong_phut}`. `gang_finish` = kết thúc in bài ghép (tiền đề bước
        đầu, nếu LSX là thành viên gang). `han` = hạn hoàn thành.
        """
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
            ef = _cong_gio_lam(es, chiem, self.cal) if chiem > 0 else es
            info[r.id] = {"som_nhat": es, "earliest_finish": ef}
            # Mốc cho bước sau ưu tiên lịch THỰC đã gán của bước này (finish_at) thay vì "sớm nhất lý
            # thuyết": bước sau không thể bắt đầu trước khi bước trước KẾT THÚC thật → "sớm nhất" phản
            # ánh đúng lịch, và cột Sớm nhất tự cảnh báo (đỏ) khi có ai gán bước sau chạy trước bước trước.
            base = _aware(r.finish_at) or ef
            prev_finish = base + timedelta(minutes=cho)
        # --- backward ---
        if han is not None:
            lf = _cuoi_ngay(han)
            for i in range(len(rows) - 1, -1, -1):
                r = rows[i]
                chiem = dur[r.id]["chiem_may_phut"]
                ls = _lui_gio_lam(lf, chiem, self.cal) if chiem > 0 else lf
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
        # Chuỗi của LSX để lấy sớm-nhất + muộn-nhất của chính dòng này.
        san, gang_finish, han = self._boi_canh_chuoi(dong)
        rows = (self.repo.by_lsx(dong.lsx_id) if dong.nguon == NGUON_LSX
                else self.repo.by_bai_ghep(dong.bai_ghep_id))
        dur = {r.id: self._thoi_luong(r) for r in rows}
        chuoi = self._chuoi(rows, san=san, gang_finish=gang_finish, han=han, dur=dur)
        it = chuoi.get(dong_id, {})
        som = it.get("som_nhat", san)
        khe = self._khe_trong(may_id, som, chiem, exclude_id=dong_id) if (may_id and chiem > 0) else None
        han_lui = None
        muon = it.get("muon_nhat")
        if muon is not None and chiem > 0:
            han_lui = _lui_gio_lam(muon, chiem, self.cal)
        return {
            "may_id": may_id,
            "khe_trong": khe,
            "finish_neu_xep": _cong_gio_lam(khe, chiem, self.cal) if khe else None,
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
        bg_id = self.db.execute(
            select(BaiGhepThanhVien.bai_ghep_id).where(BaiGhepThanhVien.lsx_id == lsx_id)
        ).scalars().first()
        if bg_id is None:
            return None
        finishes = [_aware(r.finish_at) for r in self.repo.by_bai_ghep(bg_id) if r.finish_at]
        return max(finishes) if finishes else None

    def _khe_trong(self, may_id: int, tu: datetime, chiem: float, *, exclude_id: int) -> datetime | None:
        """Khe trống sớm nhất ≥ `tu` trên `may_id` đủ chỗ cho `chiem` phút (né các dòng đã xếp)."""
        ban = sorted(
            [r for r in self.repo.rows_da_xep_co_may() if r.may_id == may_id and r.id != exclude_id],
            key=lambda r: _aware(r.start_at),
        )
        cur = _dau_ca(tu, self.cal)
        for r in ban:
            s, e = _aware(r.start_at), _aware(r.finish_at)
            if e <= cur:
                continue
            if _cong_gio_lam(cur, chiem, self.cal) <= s:
                return cur
            cur = _dau_ca(e, self.cal)
        return cur

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
        rows = self.repo.list_dong(may_id=may_id)
        lsx_ids = {r.lsx_id for r in rows if r.lsx_id}
        bg_ids = {r.bai_ghep_id for r in rows if r.bai_ghep_id}
        lsx_map = {i: self.lsx_repo.get(i) for i in lsx_ids}
        bg_map = {i: self.bg_repo.get(i) for i in bg_ids}
        dur = {r.id: self._thoi_luong(r) for r in rows}
        xung_dot = self._xung_dot_ids()

        # Chuỗi theo từng LSX (bài ghép: dòng in ghép là chuỗi 1 phần tử, không hạn).
        chuoi: dict[int, dict] = {}
        theo_lsx: dict[int, list[XepLichCongDoan]] = {}
        for r in rows:
            if r.nguon == NGUON_LSX and r.lsx_id:
                theo_lsx.setdefault(r.lsx_id, []).append(r)
        for lid, lrows in theo_lsx.items():
            lsx = lsx_map.get(lid)
            chuoi.update(self._chuoi(
                lrows, san=self._san_thoi_gian(lsx),
                gang_finish=self._gang_finish_cho_lsx(lid), han=self._han(lsx), dur=dur,
            ))

        may_names = self._may_names({r.may_id for r in rows})
        dept_names = self._dept_names({r.department_id for r in rows})

        items: list[dict] = []
        for r in rows:
            lsx = lsx_map.get(r.lsx_id)
            bg = bg_map.get(r.bai_ghep_id)
            lcd = self._lcd(r.lsx_cong_doan_id)
            ma = (lsx.ma if lsx else None) if r.nguon == NGUON_LSX else (bg.ma if bg else None)
            ten = (lcd.ten if lcd else None) if r.nguon == NGUON_LSX else "In chung"
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
                "slack_ngay": ch.get("slack_ngay"), "nhan_rui_ro": ch.get("nhan_rui_ro"),
                "trang_thai": r.trang_thai, "is_locked": bool(r.is_locked),
                "co_xung_dot": r.id in xung_dot, "blocked_reason": r.blocked_reason,
                "is_rush": bool(lsx.is_rush) if lsx else False,
            })
        if q:
            like = q.strip().lower()
            items = [it for it in items if like in (it["lsx_ma"] or "").lower()
                     or like in (it["cong_doan_ten"] or "").lower()]
        return {"items": items, "total": len(items)}
