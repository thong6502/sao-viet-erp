"""Xếp lịch 3 — điều phối bàn xếp lịch cấp LỆNH SẢN XUẤT.

Mục tiêu DUY NHẤT của màn: người đặt giờ bắt đầu cho một lệnh, hệ trả ngay ngày kết thúc. Không
gán máy, không xếp từng công đoạn, và **không chặn gì hết** — thiếu vật tư hay trễ hạn thì bày
MÀU, người điều độ vẫn quyết.

MÁY của một bước đọc theo thứ tự: `san_xuat_cong_viec.may_id` (máy ĐANG GIAO CHẠY, `doi_may` ghi
vào đây) → `lsx_cong_doan.may_id` (máy kế hoạch, dùng khi lệnh chưa phát hành). Chốt 10/09/2026:
trước đó màn chỉ đọc máy kế hoạch nên lệnh đã phát hành hiện sai máy ở 4/7 bước, và vì tốc độ
treo ở CẶP (công đoạn × máy) nên cả thời lượng lẫn ngày kết thúc đều tính trên máy không chạy.

Số dẫn xuất tính lúc đọc qua `trai_lich`. Ranh giới hiệu năng (spec §4.1): khung giờ làm dựng ĐÚNG
MỘT LẦN mỗi request, routing cả lô nạp bằng MỘT truy vấn, mọi đường đọc cắt theo cửa sổ hoặc theo
tập id.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from ...models.lsx import (
    LB_MAY, LB_THUE_NGOAI, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH, TT_SAN_SANG,
)
from ...models.san_xuat import CV_HOAN_THANH, CV_PHAT_HANH
from ...models.xep_lich_lenh import XepLichLenh
from ..gio_xuong import gio_xuong, lich_hien_thi, thuc_te_hien_thi, ve_gio_xuong
from ..xep_lich_service import _aware, _naive
from .trai_lich import BuocVao, KetQuaTrai, MocBuoc, trai_lich


class XepLich3Error(Exception):
    """Lỗi nghiệp vụ chung → 400."""


class XepLich3NotFound(XepLich3Error):
    """→ 404."""


class XepLich3Conflict(XepLich3Error):
    """Người khác vừa đổi mốc → 409."""


# Lệnh được phép nằm trên bàn xếp lịch. `da_phat_hanh` vẫn giữ mốc để bàn tổ đọc, nhưng không
# quay lại hàng chờ.
TT_XEP_DUOC = (TT_SAN_SANG, TT_DA_LAP_KE_HOACH)


def _chu(v: object) -> str | None:
    """Ép một ô quy cách về CHUỖI cho `ChiTietOut`.

    `quy_cach_json` là ảnh chụp lúc tạo lệnh, giá trị có thể là SỐ (`so_kem: 4`, `so_mau: 4`) chứ
    không phải chuỗi. Schema khai `str | None`, trả thẳng số là `ResponseValidationError` — mà lỗi
    đó ném NGOÀI `CORSMiddleware` nên trình duyệt chỉ thấy "blocked by CORS policy", không thấy 500.
    """
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _ngay_thue_ngoai(cd) -> int | None:
    """Số NGÀY LỊCH một bước gia công ngoài chiếm chỗ. `None` = chưa khai đủ để biết.

    Hai nguồn, ưu tiên nguồn KHAI TAY vì nó là cam kết của nhà cung cấp:
      1. `van_chuyen_ngay` (MỘT chiều, nên nhân 2) + `gia_cong_ngay`;
      2. `ngay_nhan_dk - ngay_gui_dk` nếu khai cả hai mốc.

    Cờ nhận biết bước thuê ngoài là `loai_buoc == LB_THUE_NGOAI` — KHÔNG có cột boolean nào.
    """
    vc, gc = getattr(cd, "van_chuyen_ngay", None), getattr(cd, "gia_cong_ngay", None)
    if vc is not None or gc is not None:
        return int(round(float(vc or 0) * 2 + float(gc or 0)))
    gui, nhan = getattr(cd, "ngay_gui_dk", None), getattr(cd, "ngay_nhan_dk", None)
    if gui and nhan:
        return max(0, (nhan - gui).days)
    return None


class _LsxCoRouting:
    """Proxy đọc-thuộc-tính cho `quy_cach_bien`: ép nó dùng routing ĐÃ NẠP SẴN.

    `quy_cach_bien` duyệt `lsx.cong_doans` để tìm bước in; quan hệ đó lazy-load, nên gọi thẳng
    trong vòng lặp là N+1 đúng nghĩa — một truy vấn routing cho MỖI lệnh, ngay bên cạnh truy vấn
    theo lô vừa nạp đủ. Test `test_lich_khong_N_cong_1_truy_van_routing` chốt đúng chỗ này.
    """

    def __init__(self, lsx, cds) -> None:
        self._lsx = lsx
        self.cong_doans = cds

    def __getattr__(self, k):
        return getattr(self._lsx, k)


class XepLich3Service:
    def __init__(self, db: Session, repo, audit=None) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self._lich = None       # khung giờ làm — dựng LƯỜI, đúng một lần mỗi request
        self._svc_dur = None    # LsxService rút gọn, chỉ để hỏi thời lượng bước
        self._nho_don: dict[int, object] = {}   # order_id -> Order (nhớ trong MỘT request)
        self._nho_kh: dict[int, object] = {}    # customer_id -> Customer
        # lsx_id -> {("id", cd_id) | ("key", step_key): may_id} — máy ĐANG GIAO CHẠY, nạp theo LÔ
        self._may_giao: dict[int, dict[tuple[str, object], int]] = {}
        self._nho_may: dict[int, object] = {}   # may_id -> MayThietBi
        # lsx_id -> {("id", cd_id) | ("key", step_key): dict lớp thực tế} — nạp theo LÔ
        self._thuc_te: dict[int, dict[tuple[str, object], dict]] = {}

    # ================= nền tính =================

    def _khung(self):
        """Khung giờ làm của xưởng — dựng ĐÚNG MỘT LẦN mỗi request rồi dùng lại.

        Mỗi lần dựng là một lượt đọc `work_shifts` + lịch nghỉ; gọi trong vòng lặp là nhân số truy
        vấn theo số lệnh. `lien_tuc` để mặc định `False`: khung THEO CA, nên thời gian ngoài ca
        được cộng vào thanh — đúng mục tiêu của module.

        Dựng lại hai mảnh của `XepLichService` (`_ca_lich_may` + `nghi_xuong`) chứ KHÔNG khởi tạo
        cả service đó: nó kéo theo `BaiGhepService` + năm repository mà màn này không dùng. Hai
        mảnh đều là wrapper mỏng nên nguồn SQL và luật nghỉ vẫn là MỘT chỗ duy nhất.
        """
        if self._lich is None:
            from ...repositories.attendance_repo import AttendanceRepository
            from ...repositories.audit_repo import AuditLogRepository
            from ...repositories.calendar_repo import CalendarRepository
            from ..calendar_service import CalendarService
            from ..xep_lich_2 import constraint as C
            from ..xep_lich_service import LichXuong

            ca = AttendanceRepository(self.db).ca_lich_xuong()
            nghi = tuple(C.doan_nghi_trong_ngay([
                (int(s.start_minute), int(s.end_minute),
                 bool(s.is_overnight) or int(s.end_minute) <= int(s.start_minute),
                 getattr(s, "break_start_minute", None), getattr(s, "break_end_minute", None))
                for s in ca
            ]))
            cal = CalendarService(
                CalendarRepository(self.db), self.audit or AuditLogRepository(self.db)
            )
            self._lich = LichXuong(cal, ca, nghi=nghi)
        return self._lich

    def _dur(self):
        """`LsxService` rút gọn — chỉ để hỏi thời lượng bước.

        Bám precedent `ke_hoach_vat_tu_service.py:911` và `san_xuat/snapshot.py:63`: constructor
        chỉ dựng cache rỗng, `repo` là thứ duy nhất thật sự dùng tới.
        """
        if self._svc_dur is None:
            from ...repositories.lsx_repo import LsxRepository
            from ..lsx_service import LsxService

            self._svc_dur = LsxService(self.db, LsxRepository(self.db), None, None)
        return self._svc_dur

    # ---------------------------------------------------------------- máy đang giao chạy

    def _nap_may(self, lsx_ids: list[int]) -> None:
        """Nạp máy ĐANG GIAO CHẠY cho cả lô — MỘT truy vấn, gọi TRƯỚC mọi vòng lặp.

        Chỉ hỏi những `lsx_id` chưa có trong cache, và đánh dấu cả những lệnh KHÔNG có công việc
        thực thi (dict rỗng) để lần sau không hỏi lại — nếu không thì lệnh chưa phát hành sẽ bị
        hỏi lại ở mỗi bước, đúng bài N+1 mà `test_lich_khong_N_cong_1_truy_van_routing` canh.
        """
        thieu = [i for i in dict.fromkeys(lsx_ids) if i is not None and i not in self._may_giao]
        if not thieu:
            return
        theo_lsx = self.repo.may_dang_chay(thieu)
        for i in thieu:
            ban: dict[tuple[str, object], int] = {}
            # Dòng tới TRƯỚC thắng: repo sắp `phien_ban_so DESC, phan_doan_so, id` nên đó là phiên
            # bản mới nhất, phân đoạn đầu. Bước bị TÁCH LẦN CHẠY có nhiều dòng cùng máy hoặc khác
            # máy — bàn cấp lệnh chỉ bày được một máy, lấy phân đoạn đầu là máy đang cầm việc.
            for cd_id, key, may_id in theo_lsx.get(i, []):
                if cd_id is not None:
                    ban.setdefault(("id", int(cd_id)), int(may_id))
                if key:
                    ban.setdefault(("key", str(key)), int(may_id))
            self._may_giao[i] = ban

    # ---------------------------------------------------------------- lớp thực tế

    def _nap_thuc_te(self, lsx_ids: list[int]) -> None:
        """Nạp lớp THỰC TẾ của cả lô — hai truy vấn, gọi TRƯỚC mọi vòng lặp (cùng lối `_nap_may`).

        Đánh dấu cả lệnh KHÔNG có công việc thực thi (dict rỗng) để lần sau khỏi hỏi lại, nếu
        không thì lệnh chưa phát hành bị hỏi lại ở mỗi bước — đúng bài N+1 mà
        `test_lich_khong_N_cong_1_truy_van_routing` canh.
        """
        thieu = [i for i in dict.fromkeys(lsx_ids) if i is not None and i not in self._thuc_te]
        if not thieu:
            return
        theo_lsx = self.repo.thuc_te_buoc(thieu)
        for i in thieu:
            ban: dict[tuple[str, object], dict] = {}
            for cd_id, key, tt, kh_bd, kh_kt, xong, thuc_bd in theo_lsx.get(i, []):
                # Dòng tới TRƯỚC thắng (repo sắp `phien_ban_so DESC, phan_doan_so, id`): bước bị
                # TÁCH LẦN CHẠY có nhiều dòng, bàn cấp lệnh chỉ bày được một — lấy phân đoạn đầu.
                o = {
                    "trang_thai": tt,
                    "ke_hoach_bat_dau": lich_hien_thi(kh_bd),
                    "ke_hoach_ket_thuc": lich_hien_thi(kh_kt),
                    "thuc_bat_dau": thuc_te_hien_thi(thuc_bd),
                    "thuc_ket_thuc": thuc_te_hien_thi(xong) if tt == CV_HOAN_THANH else None,
                }
                # LỆCH đo ở mốc KẾT THÚC và chỉ khi bước ĐÃ ĐÓNG: dương = xong muộn hơn kế hoạch,
                # âm = xong sớm. Hai vế phải cùng thang — `ve_gio_xuong` kéo mốc thực (UTC thật)
                # về thang giờ xưởng của `du_kien_*`, trừ thẳng là lệch đúng offset máy chủ.
                o["lech_phut"] = (
                    round((ve_gio_xuong(xong) - _aware(kh_kt)).total_seconds() / 60.0)
                    if tt == CV_HOAN_THANH and xong is not None and kh_kt is not None else None
                )
                if cd_id is not None:
                    ban.setdefault(("id", int(cd_id)), o)
                if key:
                    ban.setdefault(("key", str(key)), o)
            self._thuc_te[i] = ban

    def _thuc_te_cua(self, cd, lsx_id: int | None) -> dict:
        """Lớp thực tế của MỘT bước. `{}` = lệnh chưa phát hành / bước không có công việc.

        Thứ tự neo giống `_may_id_cua`: id công đoạn trước (chính xác tuyệt đối), `step_key` là
        lưới hứng khi `replace_routing` đã tái sinh id sau lúc phát hành.
        """
        ban = self._thuc_te.get(lsx_id or -1) or {}
        o = ban.get(("id", int(cd.id))) if getattr(cd, "id", None) else None
        if o is None and getattr(cd, "step_key", None):
            o = ban.get(("key", str(cd.step_key)))
        return o or {}

    def _may_id_cua(self, cd, lsx_id: int | None) -> tuple[int | None, str | None]:
        """`(may_id, nguồn)` của một bước. Nguồn: `thuc_thi` · `ke_hoach` · `None` (chưa có máy).

        Thứ tự: id công đoạn → `step_key` → máy kế hoạch. Neo bằng id trước vì nó chính xác tuyệt
        đối; `step_key` là lưới hứng cho trường hợp routing đã bị `replace_routing` tái sinh id sau
        khi phát hành (id trên công việc thành số chết, `step_key` thì không đổi).
        """
        ban = self._may_giao.get(lsx_id or -1) or {}
        giao = ban.get(("id", int(cd.id))) if getattr(cd, "id", None) else None
        if giao is None and getattr(cd, "step_key", None):
            giao = ban.get(("key", str(cd.step_key)))
        if giao is not None:
            return int(giao), "thuc_thi"
        return (int(cd.may_id), "ke_hoach") if getattr(cd, "may_id", None) else (None, None)

    def _may(self, may_id: int | None):
        if not may_id:
            return None
        if may_id not in self._nho_may:
            from ...models.may_thiet_bi import MayThietBi

            self._nho_may[may_id] = self.db.get(MayThietBi, may_id)
        return self._nho_may[may_id]

    # ---------------------------------------------------------------- thời lượng

    def _tinh_buoc(self, lsx, cds) -> tuple[list[BuocVao], dict[int, dict]]:
        """Tính thời lượng cả routing MỘT LẦN — nguồn DUY NHẤT cho thanh Gantt và bảng công đoạn.

        Dùng `chiem_may_phut` (đã gồm chuẩn bị) chứ không `chay_phut`: thứ chiếm chỗ trên trục thời
        gian là toàn bộ thời lượng bước, kể cả canh máy. Máy đọc SỐNG (`_may_id_cua` → module Máy)
        — tốc độ và thời gian chuẩn bị kế thừa từ đó, không có máy là tốc độ 0 ⇒ chạy 0.

        Vế thứ hai của kết quả là số ĐÃ TÍNH của từng bước, để panel bày lại đúng con số đã trải.
        Trước 10/09/2026 panel tự tính lần hai và truyền `None` chỗ quy cách, nên mọi bước rơi về
        "chưa quy đổi" ⇒ chỉ còn thời gian chuẩn bị: cùng một lệnh, bảng cộng ra 1 443′ trong khi
        thanh dài 2 362′. Gộp về một đường thì hai chỗ KHÔNG THỂ lệch nữa.
        """
        from ..bien_cong_thuc import quy_cach_bien
        from ..lsx_service import thoi_luong_buoc

        svc = self._dur()
        qc = quy_cach_bien(_LsxCoRouting(lsx, cds))
        lsx_id = getattr(lsx, "id", None)
        self._nap_may([lsx_id] if lsx_id else [])
        ra: list[BuocVao] = []
        tin: dict[int, dict] = {}
        for cd in cds:
            tt = int(cd.thu_tu or 0)
            may_id, nguon = self._may_id_cua(cd, lsx_id)
            may = self._may(may_id)
            ngoai = (cd.loai_buoc or LB_MAY) == LB_THUE_NGOAI
            t = thoi_luong_buoc(cd, may, svc.sl_tinh_cua_buoc(cd, may, qc))
            dg = t.get("dien_giai") or {}
            phut = 0.0 if ngoai else float(t.get("chiem_may_phut") or 0.0)
            tin[cd.id] = {
                "may_id": may_id, "may_ten": getattr(may, "ten", None), "may_nguon": nguon,
                "may_ke_hoach_id": cd.may_id,
                "may_ke_hoach_ten": (
                    getattr(self._may(cd.may_id), "ten", None)
                    if nguon == "thuc_thi" and cd.may_id and cd.may_id != may_id else None
                ),
                "chay_phut": phut,
                "phuong_phap": dg.get("phuong_phap"),
                # Câu cảnh báo của chính `thoi_luong_buoc` — nó biết bước tịt vì THIẾU MÁY hay vì
                # thiếu cầu quy đổi. Panel bày lại nguyên văn thay vì tự dịch "0 phút" thành
                # "Chờ chạy", câu vô nghĩa với người đang tìm xem thiếu gì.
                "canh_bao": (dg.get("canh_bao") or [None])[0] if not ngoai else None,
            }
            if ngoai:
                ra.append(BuocVao(lsx_cong_doan_id=cd.id, thu_tu=tt, chay_phut=0.0,
                                  thue_ngoai_ngay=_ngay_thue_ngoai(cd), la_thue_ngoai=True))
            else:
                ra.append(BuocVao(lsx_cong_doan_id=cd.id, thu_tu=tt, chay_phut=phut,
                                  canh_bao=tin[cd.id]["canh_bao"]))
        return ra, tin

    def _buoc_vao(self, lsx, cds) -> list[BuocVao]:
        return self._tinh_buoc(lsx, cds)[0]

    def _trai(self, lsx, cds, moc: datetime) -> KetQuaTrai:
        return trai_lich(moc, self._buoc_vao(lsx, cds), self._khung())

    # ================= đọc =================

    def hang_cho(self, *, tim: str | None = None, trang: int = 1, cd_trang: int = 20) -> dict:
        """Thẻ chờ xếp: lệnh đủ điều kiện mà chưa có mốc. Lọc + phân trang ở MÁY CHỦ."""
        rows, tong = self.repo.hang_cho(
            trang_thai=TT_XEP_DUOC, tim=tim, trang=trang, cd_trang=cd_trang,
        )
        routing = self.repo.routing_theo_lo([r.id for r in rows])
        self._nap_may([r.id for r in rows])
        dong = []
        for l in rows:
            cds = routing.get(l.id, [])
            phut = sum(b.chay_phut for b in self._buoc_vao(l, cds))
            dong.append({
                "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
                "customer_name": self._ten_khach(l),
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
                "han_giao_khach": l.han_giao_khach,
                "is_rush": bool(l.is_rush),
                "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
                "so_luong_dat": int(l.so_luong_dat or 0),
                "don_vi_tinh": l.don_vi_tinh,
                "chay_phut": round(phut, 2),
                "so_buoc": len(cds),
            })
        return {"dong": dong, "tong": tong}

    def lich(self, *, tu: date, den: date) -> dict:
        """Các lệnh CHẠM cửa sổ `[tu, den]`, mỗi lệnh một dòng đã trải sẵn.

        Cắt hai nhịp: SQL loại lệnh bắt đầu sau mép phải, rồi sau khi trải mới loại được lệnh kết
        thúc trước mép trái — `ket_thuc` không có cột nên SQL không biết nó.
        """
        d_tu = datetime.combine(tu, time.min)
        d_den = datetime.combine(den, time.max)
        moc_rows = self.repo.truoc_moc(_aware(d_den))
        lsx_map = self.repo.lsx_theo_ids([m.lsx_id for m in moc_rows])
        routing = self.repo.routing_theo_lo(list(lsx_map))
        self._nap_may(list(lsx_map))
        self._nap_thuc_te(list(lsx_map))

        dong = []
        for m in moc_rows:
            l = lsx_map.get(m.lsx_id)
            if l is None:                        # lệnh đã xoá, FK CASCADE dọn sau
                continue
            cds = routing.get(l.id, [])
            buoc, tin = self._tinh_buoc(l, cds)
            kq = trai_lich(_naive(m.bat_dau_at), buoc, self._khung())
            tt = self._du_kien_theo_thuc_te(l, cds, buoc, m, kq)
            kq_con = tt.pop("_kq_con_lai", None)
            # Mép PHẢI để cắt cửa sổ phải là mép sẽ VẼ, không phải mép kế hoạch: lệnh đã chạy dở
            # kết thúc theo `ket_thuc_thuc_te`, có thể sớm hơn hẳn mốc kế hoạch.
            if (tt.get("ket_thuc_thuc_te") or kq.ket_thuc) < d_tu:
                continue
            dong.append(self._dong(l, m, kq, tin, tt, kq_con))
        return {"dong": dong, "tong": len(dong), "ngay_nghi": self._ngay_nghi(d_tu, d_den)}

    def _ngay_nghi(self, tu: datetime, den: datetime) -> list[date]:
        """Ngày KHÔNG làm việc trong cửa sổ đang xem — để bàn tô nền đúng thay vì đoán T7/CN.

        Trước 10/09/2026 màn tự suy "cuối tuần = thứ 7 + chủ nhật" ngay ở FE, trong khi xưởng khai
        `works_sat = true`: bàn tô thứ 7 là ngày nghỉ còn engine vẫn xếp việc vào đó. Ngày lễ và
        ngày làm bù thì FE không có cách nào biết. Nguồn duy nhất đúng là `is_working_day`, đã
        tính lễ + làm bù + cấu hình tuần.

        Rẻ: `CalendarService` cache cấu hình tuần và ngày đặc biệt theo NĂM, nên 7–30 ngày ở đây
        chỉ tốn hai lượt đọc, không phải mỗi ngày một lượt.
        """
        cal = self._khung().cal
        ra: list[date] = []
        d = tu.date()
        cuoi = den.date()
        while d <= cuoi:
            if not cal.is_working_day(d):
                ra.append(d)
            d = d + timedelta(days=1)
        return ra

    def chi_tiet(self, lsx_id: int) -> dict:
        """Panel dưới: thông tin THẬT của một lệnh + bảng công đoạn.

        Bảng công đoạn KHÔNG có cột mốc bắt đầu/kết thúc: đây là màn cấp LỆNH, mốc từng bước là số
        thừa ở đây (bốn chỗ khác cần thì lấy qua `moc_cong_doan`).
        """
        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        cds = self.repo.routing_theo_lo([lsx_id]).get(lsx_id, [])
        m = self.repo.theo_lsx(lsx_id)
        # MỘT lượt tính cho cả thanh lẫn bảng — `tin` là số đã trải, panel không tính lại.
        buoc, tin = self._tinh_buoc(l, cds)
        self._nap_thuc_te([lsx_id])
        kq = trai_lich(_naive(m.bat_dau_at), buoc, self._khung()) if m else None
        lop = self._lop(cds)
        dong_lop: dict[int, int] = {}
        for v in lop.values():
            dong_lop[v] = dong_lop.get(v, 0) + 1
        ten_dv = self.repo.ten_don_vi(
            sorted({str(c.don_vi_vao) for c in cds if c.don_vi_vao})
        )

        qc = dict(l.quy_cach_json or {})         # ẢNH CHỤP lúc tạo lệnh — khoá có thể trống
        don = self._don_cua(l)
        ra = {
            "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
            "trang_thai": l.trang_thai,
            "is_rush": bool(l.is_rush),
            "customer_name": self._ten_khach(l),
            "order_no": getattr(don, "order_no", None),
            "customer_po_no": getattr(don, "customer_po_no", None),
            "sale_name": self._ten_nguoi(getattr(don, "sale_user_id", None)),
            "so_luong_dat": int(l.so_luong_dat or 0),
            "don_vi_tinh": l.don_vi_tinh,
            "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
            "so_to_nguyen": int(l.so_to_nguyen or 0),
            "so_con": int(l.so_con or 1),
            "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
            "han_giao_khach": l.han_giao_khach,
            "nguoi_phu_trach_ten": self._ten_nguoi(l.nguoi_phu_trach_id),
            "luu_y_gui_xuong": l.ghi_chu,
            "giay": _chu(qc.get("giay_ten") or qc.get("giay")),
            "kho_in": _chu(qc.get("kho_in") or qc.get("kho")),
            "so_mau": _chu(qc.get("so_mau") or qc.get("mau")),
            "so_kem": _chu(qc.get("so_kem")),
            "so_nguoi_tong": sum(int(c.so_nhan_cong_tieu_chuan or 0) for c in cds),
            "cong_doans": [
                self._cd_dict(c, i, tin.get(c.id) or {}, ten_dv,
                              lop.get(c.id, 0), dong_lop.get(lop.get(c.id, 0), 1) > 1,
                              self._thuc_te_cua(c, l.id))
                for i, c in enumerate(cds)
            ],
        }
        ra.update(self._so_lich(m, kq))
        tt = self._du_kien_theo_thuc_te(l, cds, buoc, m, kq)
        tt.pop("_kq_con_lai", None)
        tt.pop("_doan_that", None)
        ra.update(tt)
        return ra

    def so_sanh_phien_ban(self, lsx_id: int, a: int, b: int) -> dict:
        """So HAI phiên bản lịch đã phát hành của một lệnh, từng bước một.

        CÁCH ĐỌC "trạng thái của bước X ở phiên bản N" — chỗ dễ đọc sai nhất của cả tính năng:

            N >= cv.phien_ban_so          ⇒ dòng SỐNG (`san_xuat_cong_viec`)
            ngược lại                     ⇒ dòng lịch sử có `phien_ban_so` LỚN NHẤT mà <= N

        Vì `phat_hanh_cap_nhat` chỉ tái chụp việc CHƯA bắt đầu, một bước có thể đứng yên qua nhiều
        phiên bản: bước đi v1 → v3 → v5 chỉ có dòng lịch sử `so=1` và `so=3`, và phiên bản 2 phải
        đọc ra đúng dòng `so=1` — "không có dòng cho v2" nghĩa là KHÔNG ĐỔI, không phải "trống".
        Lấy `so == N` là mất hết những bước không đổi ở đúng phiên bản đang xem.

        GIỚI HẠN CÓ Ý THỨC: phiên bản MỚI NHẤT đọc trên dòng sống, mà `thuc_thi.doi_may` ghi thẳng
        `cv.may_id` không qua versioning — nên máy của phiên bản mới nhất là máy ĐANG CHẠY, có thể
        khác máy lúc phát hành. Đó cũng chính là thứ `may_nguon` ở panel đang nói ra.

        Và: dữ liệu chỉ có TỪ 10/09/2026 (mg `0294`). Phiên bản cũ hơn đọc ra dòng sống cho mọi
        bước ⇒ bảng so sánh sẽ nói "không đổi" — đúng theo dữ liệu còn lại, không dựng lại được.
        """
        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        if a == b:
            raise XepLich3Error("Chọn hai phiên bản khác nhau để so.")
        a, b = (a, b) if a < b else (b, a)
        cvs, ls = self.repo.lich_su_lich(lsx_id)
        if not cvs:
            raise XepLich3Error("Lệnh chưa phát hành nên chưa có phiên bản nào để so.")
        theo_cv: dict[int, list] = {}
        for r in ls:
            theo_cv.setdefault(r.cong_viec_id, []).append(r)

        def o(cv, n: int) -> dict:
            nguon = cv
            if n < int(cv.phien_ban_so or 1):
                truoc = [r for r in theo_cv.get(cv.id, []) if int(r.phien_ban_so) <= n]
                nguon = max(truoc, key=lambda r: int(r.phien_ban_so)) if truoc else cv
            return {
                "may_ten": getattr(self._may(nguon.may_id), "ten", None),
                "bat_dau": lich_hien_thi(nguon.du_kien_bat_dau),
                "ket_thuc": lich_hien_thi(nguon.du_kien_ket_thuc),
            }

        dong = []
        for cv in sorted(cvs, key=lambda c: (c.lsx_cong_doan_id or 0, c.phan_doan_so, c.id)):
            va, vb = o(cv, a), o(cv, b)
            dong.append({
                "cong_viec_id": cv.id,
                "ten": cv.ten_cong_doan,
                "phan_doan_so": int(cv.phan_doan_so or 1),
                "phan_doan_tong": int(cv.phan_doan_tong or 1),
                "a": va, "b": vb,
                "doi_gio": va["bat_dau"] != vb["bat_dau"] or va["ket_thuc"] != vb["ket_thuc"],
                "doi_may": va["may_ten"] != vb["may_ten"],
            })
        return {"lsx_id": lsx_id, "a": a, "b": b, "dong": dong}

    def moc_cong_doan(self, lsx_ids: list[int]) -> dict[int, list[MocBuoc]]:
        """Mốc DẪN XUẤT của từng bước — đường riêng cho bốn chỗ tiêu thụ lịch.

        Không nằm trong payload của màn (spec §4): bàn xếp lịch cấp lệnh cố ý không bày mốc bước.

        BƯỚC ĐÃ CHẠY TRẢ GIỜ THẬT, không trả giờ dẫn xuất. Từ lúc mốc của lệnh chạy dở đổi nghĩa
        thành "bắt đầu phần còn lại", trải lại cả routing từ mốc mới sẽ đặt bước ĐÃ XONG vào tương
        lai — và bốn nơi tiêu thụ sẽ nói theo một kế hoạch không còn tồn tại: "ngày cần" của giấy
        lùi ra sau lúc giấy đã dùng, cột "máy đang chạy lệnh nào" chỉ sang bước đã đóng. Bước đang
        chạy lấy mốc vào việc THẬT + mốc kết thúc KẾ HOẠCH đã phát hành (tổ đang làm theo mốc đó).
        """
        moc = self.repo.theo_nhieu_lsx(lsx_ids)
        if not moc:
            return {}
        lsx_map = self.repo.lsx_theo_ids(list(moc))
        routing = self.repo.routing_theo_lo(list(moc))
        self._nap_may(list(moc))
        self._nap_thuc_te(list(moc))
        ra: dict[int, list[MocBuoc]] = {}
        for lsx_id, m in moc.items():
            l = lsx_map.get(lsx_id)
            if l is None:
                continue
            cds = routing.get(lsx_id, [])
            buoc, tin = self._tinh_buoc(l, cds)
            san, da_bat_dau, _co = self._san(l, cds)
            if not da_bat_dau:
                ra[lsx_id] = trai_lich(_naive(m.bat_dau_at), buoc, self._khung()).buoc
                continue
            a = max(_naive(m.bat_dau_at), san) if san is not None else _naive(m.bat_dau_at)
            con_lai = [b for b in buoc if b.lsx_cong_doan_id not in da_bat_dau]
            dong = list(trai_lich(a, con_lai, self._khung()).buoc)
            for cd in cds:
                if cd.id not in da_bat_dau:
                    continue
                t = self._thuc_te_cua(cd, lsx_id)
                bd = t.get("thuc_bat_dau") or t.get("ke_hoach_bat_dau")
                kt = t.get("thuc_ket_thuc") or t.get("ke_hoach_ket_thuc") or bd
                if bd is None or kt is None:
                    continue
                dong.append(MocBuoc(
                    lsx_cong_doan_id=cd.id, thu_tu=int(cd.thu_tu or 0),
                    bat_dau=bd, ket_thuc=max(bd, kt),
                    chay_phut=float((tin.get(cd.id) or {}).get("chay_phut") or 0.0),
                ))
            ra[lsx_id] = sorted(dong, key=lambda b: (b.thu_tu, b.lsx_cong_doan_id))
        return ra

    # ================= ghi =================

    def dat_moc(self, lsx_id: int, moc: datetime,
                expected_updated_at: datetime | None = None, *, nguoi_id: int | None = None) -> dict:
        """Đặt / dời mốc bắt đầu của một lệnh. KHÔNG chặn gì hết.

        Mốc rơi ngoài giờ chạy thì TRƯỢT vào đầu khoảng chạy được gần nhất và lưu MỐC ĐÃ TRƯỢT —
        lưu mốc người thả thì mỗi lần đọc lại trượt thêm một nhát nữa, và thanh tự đi.
        """
        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        if moc is None:
            raise XepLich3Error("Thiếu giờ bắt đầu.")

        row = self.repo.theo_lsx(lsx_id)
        if row is not None and expected_updated_at is not None:
            hien = _aware(row.updated_at)
            if hien is not None and abs((hien - _aware(expected_updated_at)).total_seconds()) > 1:
                raise XepLich3Conflict(
                    "Lệnh vừa được người khác dời — màn đã cập nhật theo bản mới nhất."
                )

        cds = self.repo.routing_theo_lo([lsx_id]).get(lsx_id, [])
        buoc, tin = self._tinh_buoc(l, cds)
        # SÀN của việc ĐÃ XẢY RA. Lệnh chạy dở thì mốc đổi nghĩa thành "bắt đầu phần còn lại", và
        # phần còn lại không thể khởi hành trước lúc bước cuối cùng đã đóng — lùi xuống dưới đó là
        # phát hành một kế hoạch nằm trong quá khứ, tổ cầm giấy in ra ngày hôm kia.
        # TRƯỢT RỒI BÁO, không chặn cứng: chặn cứng phá triết lý "không chặn gì" của cả màn (§1),
        # còn trượt-và-nói-ra thì vừa giữ triết lý vừa không đẻ lịch ngược thời gian. Cùng đường
        # với câu báo ngoài-giờ-chạy đang chạy tốt.
        self._nap_thuc_te([lsx_id])
        san, _da_bat_dau, _co = self._san(l, cds)
        bao_san = None
        if san is not None and _naive(moc) < san:
            bao_san = (
                f"Đã có bước xong lúc {san.strftime('%H:%M %d/%m')} — "
                "không lùi lịch xuống dưới mốc đó."
            )
            moc = san
        kq = trai_lich(moc, buoc, self._khung())
        if row is None:
            row = self.repo.them(XepLichLenh(
                lsx_id=lsx_id, bat_dau_at=_aware(kq.bat_dau), created_by=nguoi_id,
            ))
        else:
            row.bat_dau_at = _aware(kq.bat_dau)
        self.db.flush()
        self.db.commit()
        self.db.refresh(row)

        # Dòng trả về phải mang CẢ lớp thực tế: màn vẽ ngay bằng dòng này, thiếu nó thì thanh nháy
        # về hình "trải cả routing từ mốc" cho tới lúc lượt tải lại kịp về.
        tt = self._du_kien_theo_thuc_te(l, cds, buoc, row, kq)
        kq_con = tt.pop("_kq_con_lai", None)
        ra = self._dong(l, row, kq, tin, tt, kq_con)
        ra["da_doi"] = kq.da_doi or bao_san is not None
        # Hai câu báo có thể cùng bật (lùi xuống dưới sàn RỒI sàn lại rơi ngoài ca) — nối lại chứ
        # đừng để câu sau nuốt câu trước: người dùng cần biết cả hai lý do mốc không nằm ở chỗ họ
        # vừa gõ, không thì lần sau họ gõ lại y hệt.
        cau = [c for c in (bao_san, (
            f"Ngoài giờ chạy — đã dời sang {kq.bat_dau.strftime('%H:%M ngày %d/%m')}."
            if kq.da_doi else None
        )) if c]
        ra["thong_bao"] = " ".join(cau) or None
        return ra

    def xoa_moc(self, lsx_id: int, *, nguoi_id: int | None = None) -> None:
        """Bỏ lịch của lệnh — thẻ quay lại hàng chờ. Không đụng trạng thái lệnh."""
        row = self.repo.theo_lsx(lsx_id)
        if row is None:
            raise XepLich3NotFound("Lệnh chưa được xếp lịch.")
        self.repo.xoa(row)
        self.db.commit()

    def phat_hanh(self, lsx_id: int, *, actor=None) -> dict:
        """Phát hành xuống xưởng — BẤM LÀ ĐI.

        KHÔNG gọi `XepLichVanDeService.phat_hanh_lsx`: dù truyền `bo_qua_xung_dot=True` thì hàm đó
        vẫn còn BỐN cửa gác — lệnh phải đang `da_lap_ke_hoach`, cả cụm liên thông phải đã lập kế
        hoạch, vật tư phải giữ đủ, mỗi nhóm thành phẩm phải có đúng một bước KCS cuối. Spec §1 của
        màn 3 là "KHÔNG CHẶN GÌ HẾT", nên ở đây làm thẳng phần THẬT của việc phát hành: đổi trạng
        thái cả cụm + đóng băng gói công việc. Vướng gì thì bày MÀU trên thanh, người điều độ quyết.

        ĐỪNG "sửa lại" thành gọi `phat_hanh_lsx` cho gọn — đó là màn 2, cố ý khác.

        Đơn vị phát hành vẫn là CẢ CỤM liên thông (cùng nhóm thành phẩm · phụ thuộc chéo · bài
        ghép), giống màn 2: gói công việc dưới xưởng dựng theo cụm, thả nửa cụm là snapshot lệch.
        """
        from ...models.bai_ghep import TT_DA_PHAT_HANH as BG_PHAT_HANH
        from ...models.lsx import TT_DA_PHAT_HANH
        from ...repositories.san_xuat_repo import SanXuatRepository
        from ..san_xuat.component import thanh_phan_lien_thong
        from ..san_xuat.release import phat_hanh as _sx_phat_hanh

        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        if l.trang_thai == TT_DA_PHAT_HANH:
            # Không phải cửa gác mà là chống bấm hai lần: phát hành lại đè lên gói đang chạy.
            raise XepLich3Conflict(f"Lệnh {l.ma} đã phát hành rồi — thu hồi trước nếu muốn làm lại.")
        if self.repo.theo_lsx(lsx_id) is None:
            raise XepLich3Error("Lệnh chưa có giờ bắt đầu — đặt mốc trước khi phát hành.")

        sx_repo = SanXuatRepository(self.db)
        tp = thanh_phan_lien_thong(sx_repo, {lsx_id})
        for x in self.repo.lsx_theo_ids(sorted(tp.lsx_ids)).values():
            if x.trang_thai != TT_DA_PHAT_HANH:
                x.trang_thai = TT_DA_PHAT_HANH
        for bg in self._bai_ghep(tp.bai_ghep_ids):
            if bg.trang_thai != BG_PHAT_HANH:
                bg.trang_thai = BG_PHAT_HANH
        _sx_phat_hanh(self.db, lsx_ids=tp.lsx_ids, bai_ghep_ids=tp.bai_ghep_ids, actor=actor)
        if self.audit is not None:
            self.audit.create(
                actor_user_id=getattr(actor, "id", None), action="xep_lich_3_phat_hanh",
                target=f"lsx:{l.id}",
                detail=f"Phát hành lệnh {l.ma} (cụm {len(tp.lsx_ids)} LSX + "
                       f"{len(tp.bai_ghep_ids)} bài ghép) — màn Xếp lịch 3, không cửa gác",
            )
        self.db.commit()
        return {"lsx_id": l.id, "trang_thai": l.trang_thai,
                "cum_lsx": sorted(tp.lsx_ids), "cum_bai_ghep": sorted(tp.bai_ghep_ids)}

    def thu_hoi(self, lsx_id: int, *, actor=None, ly_do: str | None = None) -> dict:
        """Thu hồi phát hành. Đi ĐƯỜNG CHUNG `go_phat_hanh_lsx` — hai điều kiện của nó KHÔNG phải
        cửa gác xếp lịch mà là chuyện dưới xưởng: bắt gõ LÝ DO (đảo một quyết định đã thả xuống
        thì thứ duy nhất còn lại là cái vết), và chặn khi đã có công việc BẮT ĐẦU chạy (§4.3) —
        rút gói lúc thợ đang làm là xoá việc đang chạy, không phải "không chặn gì hết".
        """
        from ..xep_lich_van_de_service import XepLichVanDeService

        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        # Chặn TRƯỚC để ra 400: đường chung ném `XepLichConflict` cho thiếu lý do, mà 409 nghĩa là
        # "người khác vừa đổi" — FE bắt theo mã sẽ hiện sai câu. Cùng ngưỡng 3 ký tự.
        if len((ly_do or "").strip()) < 3:
            raise XepLich3Error(
                "Thu hồi phát hành phải ghi lý do — lệnh đã xuống xưởng, cần vết để đối chiếu sau."
            )
        XepLichVanDeService(self.db, self.audit).go_phat_hanh_lsx(
            lsx_id=lsx_id, actor=actor, ly_do=ly_do,
        )
        return {"lsx_id": lsx_id, "trang_thai": l.trang_thai}

    def goi_phat_hanh(self, lsx_id: int) -> dict:
        """Trạng thái gói công việc đã thả xuống xưởng — CHỈ ĐỌC, để màn biết bày nút nào.

        Panel phải hỏi câu này TRƯỚC khi bày nút: nếu gói đã có việc bắt đầu thì "Thu hồi phát
        hành" là việc bất khả thi (§4.3) — mời người dùng gõ lý do rồi mới ném 409 là bắt họ đâm
        vào tường. `cho_phep_thu_hoi` / `cho_phep_cap_nhat` do `thong_tin_goi` tính sẵn, cùng
        nguồn với luật chặn nên không lệch.

        `co_goi=False` khi lệnh chưa phát hành (hoặc phát hành từ trước khi có lớp thực hiện).
        """
        from ..san_xuat import release_update

        if self.repo.lsx_theo_ids([lsx_id]).get(lsx_id) is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        return release_update.thong_tin_goi(self.db, nguon="lsx", id=lsx_id)

    def phat_hanh_cap_nhat(self, lsx_id: int, *, actor=None, ly_do: str | None = None) -> dict:
        """Đẩy lịch MỚI xuống xưởng cho phần chưa bắt đầu, giữ nguyên việc đang/đã chạy (§4.3).

        Đây là lối ra khi thu hồi bị chặn: đổi giờ hoặc đổi máy xong vẫn xuống được xưởng mà không
        xoá việc thợ đã làm. KHÔNG đi qua `XepLich2Service.phat_hanh_cap_nhat` vì hàm đó mở đầu
        bằng `_chan_phat_hanh` — đúng bốn cửa gác mà `phat_hanh` của màn này cố ý không có. Gọi
        thẳng service san_xuat, cùng lối với `phat_hanh`.
        """
        from ..san_xuat import release_update

        if self.repo.lsx_theo_ids([lsx_id]).get(lsx_id) is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        # Chặn TRƯỚC để ra 400 kèm câu của màn này: service dưới ném `ValueError` cho cả "thiếu lý
        # do" lẫn "không còn gì để cập nhật", hai chuyện khác hẳn nhau.
        if len((ly_do or "").strip()) < 3:
            raise XepLich3Error(
                "Phát hành cập nhật phải ghi lý do — xưởng cần biết vì sao lịch đổi giữa chừng."
            )
        try:
            return release_update.phat_hanh_cap_nhat(
                self.db, nguon="lsx", id=lsx_id, ly_do=ly_do or "", actor=actor,
            )
        except ValueError as exc:
            raise XepLich3Error(str(exc)) from exc

    def _bai_ghep(self, ids) -> list:
        if not ids:
            return []
        from sqlalchemy import select

        from ...models.bai_ghep import BaiGhep

        return list(self.db.execute(select(BaiGhep).where(BaiGhep.id.in_(sorted(ids)))).scalars())

    # ================= dựng payload =================

    def _dong(self, l, m: XepLichLenh, kq: KetQuaTrai, tin: dict[int, dict] | None = None,
              tt: dict | None = None, kq_con: KetQuaTrai | None = None) -> dict:
        """Một dòng bàn Gantt.

        `tt` + `kq_con` là lớp THỰC TẾ (rỗng khi lệnh chưa chạy). Có nó thì thanh KHÔNG còn là
        "trải cả routing từ mốc" nữa — xem `DongLichOut`: mép trái là lúc lệnh thật sự vào việc,
        còn khối chạy/giờ chạy chỉ tính PHẦN CÒN LẠI. Trải cả routing từ mốc mới sẽ vẽ bước đã
        xong nằm trong tương lai, và bàn sẽ nói lệnh chưa bắt đầu trong khi tổ đã làm xong một bước.
        """
        ra = {
            "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
            "customer_name": self._ten_khach(l),
            "trang_thai": l.trang_thai,
            "is_rush": bool(l.is_rush),
            "so_luong_dat": int(l.so_luong_dat or 0),
            "don_vi_tinh": l.don_vi_tinh,
            "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
            "so_con": int(l.so_con or 1),
            "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
            "han_giao_khach": l.han_giao_khach,
            "may_ten": self._ten_may_chinh(l, tin),
        }
        ra.update(self._so_lich(m, kq))
        if tt:
            ra["thuc_bat_dau_lenh"] = tt.get("thuc_bat_dau_lenh")
            ra["ket_thuc_thuc_te"] = tt.get("ket_thuc_thuc_te")
            ra["doan_thuc_te"] = tt.get("_doan_that") or []
        if kq_con is not None:
            # Ba số này mô tả CÙNG một lượt trải nên phải thay cùng nhau, không thay lẻ.
            ra.update(self._so_lich(m, kq_con))
            ra["bat_dau_at"] = _naive(m.bat_dau_at)   # mốc vẫn là thứ kéo-thả ghi vào, giữ nguyên
        return ra

    def _so_lich(self, m: XepLichLenh | None, kq: KetQuaTrai | None) -> dict:
        """Phần LỊCH của payload — tách ra vì cả dòng Gantt lẫn panel đều cần đúng khối này."""
        if m is None or kq is None:
            return {
                "bat_dau_at": None, "ket_thuc": None, "chay_phut": 0.0,
                "nghi_ngoai_ca_phut": 0.0, "doan": [], "ghi_chu": [], "updated_at": None,
            }
        tong = (kq.ket_thuc - kq.bat_dau).total_seconds() / 60.0
        return {
            "bat_dau_at": kq.bat_dau,
            "ket_thuc": kq.ket_thuc,
            "chay_phut": round(kq.chay_phut, 2),
            # Khoảng hở giữa các đoạn: nghỉ giữa ca + ngoài ca + ngày nghỉ. Đây là con số trả lời
            # đúng câu hỏi của người dùng: "vì sao thanh dài hơn giờ chạy?".
            "nghi_ngoai_ca_phut": round(max(0.0, tong - kq.chay_phut), 2),
            "doan": [
                {"tu": d.tu, "den": d.den, "buoc_index": d.buoc_index} for d in kq.doan
            ],
            "ghi_chu": kq.ghi_chu,
            "updated_at": _naive(m.updated_at),
        }

    def _san(self, l, cds) -> tuple[datetime | None, set[int], bool]:
        """`(SÀN, id bước đã bắt đầu, lệnh đã phát hành chưa)` — thang giờ xưởng, naive.

        SÀN = mốc sớm nhất mà phần việc CÒN LẠI có thể khởi hành:

            max( mọi `hoan_thanh_luc` của bước đã xong  ∪  {bây giờ, nếu còn bước đang dở} )

        "Bây giờ" vào sàn khi có bước đang chạy/tạm dừng vì phần còn lại không thể bắt đầu trước
        lúc này. `None` = chưa bước nào động tới ⇒ không có sàn, mốc đi đâu cũng được (§1).

        Bước `released` (đã phát hành, tổ chưa bấm gì) KHÔNG tính là đã bắt đầu: nó vẫn được trải
        lại bình thường — đó chính là "phần còn lại".

        Gọi sau `_nap_thuc_te`.
        """
        san: datetime | None = None
        da_bat_dau: set[int] = set()
        co = False
        for cd in cds:
            t = self._thuc_te_cua(cd, l.id)
            tt = t.get("trang_thai")
            if tt is None:
                continue
            co = True
            if tt == CV_PHAT_HANH:
                continue
            da_bat_dau.add(cd.id)
            # `thuc_ket_thuc` chỉ có khi bước ĐÃ ĐÓNG; bước còn dở lấy "bây giờ" làm sàn.
            moc = t.get("thuc_ket_thuc") or lich_hien_thi(gio_xuong())
            san = moc if san is None else max(san, moc)
        return san, da_bat_dau, co

    def _du_kien_theo_thuc_te(self, l, cds, buoc, m, kq) -> dict:
        """Mốc xong TÍNH LẠI THEO VIỆC ĐÃ XẢY RA — số thứ hai của panel, cạnh mốc kế hoạch.

        Kế hoạch không bao giờ đúng tuyệt đối: bước xong SỚM kéo mốc xong lùi lại, bước xong MUỘN
        đẩy nó ra. Con số này trả lời đúng câu đó, và chỉ có nghĩa khi lệnh ĐÃ PHÁT HÀNH — chưa
        phát hành thì không có gì để so, trả `None` để màn giữ nguyên một số như cũ.

        CÔNG THỨC (`docs/design-xep-lich-3-thuc-te-va-phien-ban.md` §2.3):

          SÀN = max(mọi `hoan_thanh_luc` của bước đã xong  ∪  {bây giờ, nếu còn bước đang dở})
          A   = max(SÀN, mốc lệnh)
          kết quả = trải lịch CHỈ những bước CHƯA BẮT ĐẦU, từ A

        Bước đã bắt đầu KHÔNG được trải lại: giờ của nó là chuyện đã rồi, trải lại là đẻ ra một kế
        hoạch nằm trong quá khứ. "Bây giờ" vào sàn khi còn bước dở vì phần việc còn lại sớm nhất
        cũng chỉ khởi hành được từ lúc này.

        CHỈ ĐỌC, KHÔNG ghi đè `xep_lich_lenh.bat_dau_at` — `docs/spec-thuc-te-vs-ke-hoach.md` §3:
        máy không tự dời lịch theo thực tế, người điều độ nhìn rồi tự quyết.
        """
        rong = {
            "ket_thuc_thuc_te": None, "lech_ket_thuc_phut": None, "co_thuc_te": False,
            "thuc_bat_dau_lenh": None, "so_buoc_xong": 0, "so_buoc": len(cds),
        }
        if m is None or kq is None:
            return rong
        san, da_bat_dau, co = self._san(l, cds)
        if not co:
            return rong
        con_lai = [b for b in buoc if b.lsx_cong_doan_id not in da_bat_dau]
        a = max(_naive(m.bat_dau_at), san) if san is not None else _naive(m.bat_dau_at)
        kq_con = trai_lich(a, con_lai, self._khung()) if con_lai else None
        if kq_con is not None:
            xong = kq_con.ket_thuc
        else:
            xong = san or kq.ket_thuc      # hết bước để trải ⇒ mốc xong là mốc thực cuối cùng
        # Mốc CẢ LỆNH thật sự vào việc — phiên chạy sớm nhất của mọi bước. Nó KHÔNG đổi khi người
        # dùng dời mốc: lệnh đã bắt đầu lúc nào là chuyện đã rồi, thứ dời được chỉ là phần còn lại.
        # Không có nó thì màn bày mốc mới (11/09) và người đọc tưởng cả lệnh dời sang 11/09.
        vao = [t for cd in cds if (t := self._thuc_te_cua(cd, l.id).get("thuc_bat_dau"))]
        xongs = [cd for cd in cds
                 if self._thuc_te_cua(cd, l.id).get("trang_thai") == CV_HOAN_THANH]
        return {
            "ket_thuc_thuc_te": xong,
            "lech_ket_thuc_phut": round((xong - kq.ket_thuc).total_seconds() / 60.0),
            "co_thuc_te": True,
            "thuc_bat_dau_lenh": min(vao) if vao else None,
            "so_buoc_xong": len(xongs),
            "so_buoc": len(cds),
            # Lượt trải PHẦN CÒN LẠI, để dòng Gantt khỏi trải lại lần nữa. Khoá gạch dưới = nội
            # bộ: `chi_tiet` phải `pop` trước khi trả, panel không cần và schema không khai.
            "_kq_con_lai": kq_con,
            "_doan_that": self._doan_da_chay(l, cds),
        }

    def _doan_da_chay(self, l, cds) -> list[dict]:
        """Các quãng lệnh THẬT SỰ chạy — gộp phần chồng lấn, bước còn dở tính tới BÂY GIỜ.

        Đừng nhầm với `thuc_bat_dau_lenh → bat_dau_at`: quãng đó là "đã vào việc rồi NẰM CHỜ",
        dài đúng bằng khoảng người điều độ đẩy mốc đi. Lệnh chạy 13 phút hôm 09/09 rồi chờ tới
        06:00 14/09 mà tô hết 5 ngày một tông "đã chạy" thì bàn đang nói dối; hai thứ phải là hai
        lớp khác nhau.

        Không thêm truy vấn: đọc lại `_nap_thuc_te` đã nạp sẵn cho cả lô.
        """
        tho: list[list[datetime]] = []
        for cd in cds:
            t = self._thuc_te_cua(cd, l.id)
            bd = t.get("thuc_bat_dau")
            if bd is None:
                continue
            # Bước chưa đóng thì quãng chạy kéo tới hiện tại — cùng quy ước với `_san`.
            kt = t.get("thuc_ket_thuc") or lich_hien_thi(gio_xuong())
            if kt > bd:
                tho.append([bd, kt])
        tho.sort()
        gop: list[list[datetime]] = []
        for a, b in tho:
            # Bước SONG SONG chạy chồng giờ nhau — gộp lại, nếu không lớp đậm vẽ đè hai lần.
            if gop and a <= gop[-1][1]:
                gop[-1][1] = max(gop[-1][1], b)
            else:
                gop.append([a, b])
        return [{"tu": a, "den": b} for a, b in gop]

    def _lop(self, cds) -> dict[int, int]:
        """`{buoc_id: lớp phụ thuộc}` — dùng lại ĐÚNG hàm màn Hồ sơ LSX đang dùng.

        Lớp = đường phụ thuộc dài nhất tới bước, KHÔNG phải `thu_tu` (thứ tự bảng). Hai bước cùng
        lớp là hai bước không chặn nhau — bìa và ruột chạy song song vẫn mang `thu_tu` 1 và 2.
        Bàn cấp lệnh vẫn trải TUẦN TỰ theo `thu_tu` (xem `trai_lich`), nên con số này chỉ để NÓI
        THẬT rằng chuỗi 1→7 trên bảng không phải quan hệ chặn — đừng dùng nó để đổi cách trải.
        """
        from ..lenh_sx.ho_so import _lop_topo

        ids = [c.id for c in cds]
        return _lop_topo(ids, self.repo.phu_thuoc_theo_lo(ids)) if ids else {}

    def _cd_dict(self, cd, i: int, tin: dict, ten_dv: dict[str, str],
                 lop: int, song_song: bool, thuc: dict | None = None) -> dict:
        """Một dòng bảng công đoạn. Số giờ + máy lấy TỪ `tin` (lượt tính duy nhất), không tính lại.

        `thuc` là lớp THỰC TẾ của bước (`_thuc_te_cua`) — rỗng khi lệnh chưa phát hành, và khi đó
        cả sáu khoá dưới đều `None` để màn giữ nguyên hình dạng cũ (spec §4: bàn cấp lệnh không
        bày mốc bước KẾ HOẠCH). Lệnh ĐÃ phát hành thì mốc bước không còn là số thừa: nó là thứ
        duy nhất so được kế hoạch với việc đã xảy ra.
        """
        ngoai = (cd.loai_buoc or LB_MAY) == LB_THUE_NGOAI
        dv = str(cd.don_vi_vao) if cd.don_vi_vao else None
        # `lsx_cong_doan.so_luong_vao` là `NOT NULL default 0`, nên 0 CHÍNH LÀ "chưa khai" — không
        # có bước nào thật sự nhận vào 0 đơn vị. Đổi về `None` ngay ở mép API để màn khỏi phải in
        # "0 tờ", câu đọc như "bước này không nhận gì" trong khi thật ra kế hoạch chưa điền.
        sl = float(cd.so_luong_vao or 0)
        return {
            "id": cd.id, "thu_tu": int(cd.thu_tu or 0), "ten": cd.ten,
            "loai_buoc": cd.loai_buoc,
            "may_id": tin.get("may_id"),
            "may_ten": tin.get("may_ten"),
            "may_nguon": tin.get("may_nguon"),
            "may_ke_hoach_ten": tin.get("may_ke_hoach_ten"),
            "to_ten": self._ten_to(cd.department_id),
            "so_luong_vao": sl if sl > 0 else None,
            "don_vi_vao": dv,
            "don_vi_vao_ten": ten_dv.get(dv) if dv else None,
            "so_nguoi_chuan": int(cd.so_nhan_cong_tieu_chuan or 0),
            "chay_phut": round(float(tin.get("chay_phut") or 0.0), 2),
            "phuong_phap": tin.get("phuong_phap"),
            "canh_bao": tin.get("canh_bao"),
            "lop": lop,
            "song_song": song_song,
            "thue_ngoai_ngay": _ngay_thue_ngoai(cd) if ngoai else None,
            "mau_index": i % 4,     # sắc độ khối chạy — mã hoá THỨ TỰ bước, không mã hoá loại
            # --- lớp THỰC TẾ (chỉ có khi lệnh đã phát hành) ---
            "trang_thai": (thuc or {}).get("trang_thai"),
            "ke_hoach_bat_dau": (thuc or {}).get("ke_hoach_bat_dau"),
            "ke_hoach_ket_thuc": (thuc or {}).get("ke_hoach_ket_thuc"),
            "thuc_bat_dau": (thuc or {}).get("thuc_bat_dau"),
            "thuc_ket_thuc": (thuc or {}).get("thuc_ket_thuc"),
            "lech_phut": (thuc or {}).get("lech_phut"),
        }

    # ================= tra tên =================

    def _don_cua(self, l):
        """Đơn hàng nguồn của lệnh.

        `Lsx` KHÔNG khai relationship `order` — chỉ có FK `order_id` — nên `getattr(l, "order")`
        luôn trả None và bốn ô đầu panel (khách · đơn · PO · sale) hiện "—" mà không lỗi gì. Đọc
        thẳng bằng id, và NHỚ theo id: `_ten_khach` chạy trên từng dòng của hàng chờ lẫn lưới, đọc
        lại mỗi dòng là hoá N+1.
        """
        oid = getattr(l, "order_id", None)
        if not oid:
            return None
        if oid not in self._nho_don:
            from ...models.order import Order

            self._nho_don[oid] = self.db.get(Order, oid)
        return self._nho_don[oid]

    def _ten_khach(self, l) -> str | None:
        cid = getattr(self._don_cua(l), "customer_id", None)
        if not cid:
            return None
        if cid not in self._nho_kh:
            from ...models.customer import Customer

            self._nho_kh[cid] = self.db.get(Customer, cid)
        return getattr(self._nho_kh[cid], "name", None)

    def _ten_nguoi(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        from ...models.user import User

        u = self.db.get(User, user_id)
        return getattr(u, "full_name", None) or getattr(u, "username", None)

    def _ten_to(self, dept_id: int | None) -> str | None:
        if not dept_id:
            return None
        from ...models.department import Department

        return getattr(self.db.get(Department, dept_id), "name", None)

    def _ten_may_chinh(self, l, tin: dict[int, dict] | None = None) -> str | None:
        """Máy của bước IN — nhãn nhận diện dòng trên Gantt, không phải danh sách đủ máy.

        `Lsx.may_id` là ảnh chụp máy in lúc TẠO lệnh. Bước in đó nay có thể đang giao cho máy
        khác; nhãn phải nói máy đang chạy, không thì lưới và bảng công đoạn của cùng một lệnh
        bày ra hai cái tên máy khác nhau.
        """
        if not l.may_id:
            return None
        for t in (tin or {}).values():
            if t.get("may_ke_hoach_id") == l.may_id and t.get("may_id"):
                return t.get("may_ten")
        return getattr(self._may(l.may_id), "ten", None)
