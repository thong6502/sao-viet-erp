"""Điều phối Xếp lịch 2 — RÁP luật thời gian thuần (`constraint`) với dữ liệu sống (`context`) và
cửa phát hành dùng chung (`release`), lưu vẫn vào `xep_lich_cong_doan`.

Khác engine cũ ở HAI điểm cốt lõi (spec §3.3, §7):
1. Đã bắt đầu thì CHẠY LIÊN TỤC tới xong — `finish = start + chiếm-máy` theo đồng hồ tường, KHÔNG đi
   bộ qua từng ca như `_cong_gio_lam`. Ca chỉ soi GIỜ BẮT ĐẦU.
2. Nháp CHO PHÉP thiếu vật tư (bỏ dây khoá giữ-chỗ của engine cũ ở bước tạo nháp); vật tư chỉ chặn
   đúng lúc PHÁT HÀNH, qua `release` — cửa dùng chung với màn cũ.

Không sở hữu bảng riêng: COMPOSE `XepLichService` qua `self.core` để tái dùng sinh dòng / thời lượng
/ vùng khoá máy / quân số, rồi tự quyết luật xếp trên dữ liệu đó.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ...models.bai_ghep import BaiGhep
from ...models.bai_ghep_cong_doan import BaiGhepCongDoan
from ...models.department import Department
from ...models.lsx import LB_MAY, LB_THUE_NGOAI, Lsx
from ...models.may_thiet_bi import MayThietBi
from ...models.xep_lich import (
    LY_DO_CHO_TIEN_DE, LY_DO_THIEU_MAY, NGUON_IN_GHEP, NGUON_LSX,
    TT_CHO_XEP, TT_DA_XEP, XepLichCongDoan,
)
from ...models.xep_lich_van_de import TT_NGOAI_LE
from ...repositories.xep_lich_van_de_repo import XepLichVanDeRepository
from ..lsx_service import _f
from ..xep_lich_service import XepLichNotFound, XepLichService, _aware, _naive
from . import constraint as C
from . import overlay, release, suggestion
from .context import XepLich2Context

_CANH_BAO_TEXT = {
    "may_chua_toc_do": "Máy chưa khai tốc độ nên chưa tính được thời lượng.",
    "chua_quy_doi": "Đơn vị của bước chưa quy đổi được về đơn vị tốc độ máy.",
    "thue_ngoai_chua_lich": "Bước thuê ngoài chưa khai ngày gửi/nhận nên chưa tính được thời gian gia công.",
}

# Khi ĐÃ chọn giờ mà engine không tính nổi thời lượng, thiếu dữ liệu này biến lịch thành vô nghĩa
# ⇒ nâng từ cảnh báo lên CHẶN ĐẶT LỊCH (spec §7.1: thieu_thoi_luong / thieu_quy_doi). Còn lúc mới
# tạo nháp (chưa có giờ) thì vẫn chỉ nhắc, không cản người đưa lệnh vào kế hoạch.
# Mỗi mục là (ma_chan, mo_ta, goi_y) — gợi ý riêng theo đúng thứ dữ liệu đang thiếu.
_CANH_BAO_CHAN = {
    "may_chua_toc_do": ("thieu_thoi_luong",
                        "Máy chưa khai tốc độ nên chưa tính được thời lượng chạy.",
                        "Khai tốc độ máy rồi xếp lại."),
    "chua_quy_doi": ("thieu_quy_doi",
                     "Đơn vị của bước chưa quy đổi được về đơn vị tốc độ máy.",
                     "Quy đổi đơn vị bước về đơn vị tốc độ máy rồi xếp lại."),
    "thue_ngoai_chua_lich": (
        "thieu_lead_thue_ngoai",
        "Bước thuê ngoài chưa khai ngày gửi/nhận (hoặc số ngày gia công) nên chưa tính được thời gian.",
        "Khai ngày gửi & ngày nhận dự kiến — hoặc số ngày gia công + vận chuyển — rồi xếp lại.",
    ),
}

# Nhãn ĐỐI TƯỢNG tĩnh cho các loại vấn đề không neo vào một máy/tổ cụ thể (điền lúc trình bày).
_DOI_TUONG_TINH = {
    "han": "Hạn lệnh",
    "tien_nhiem": "Bước tiền nhiệm",
    "vat_tu": "Vật tư",
    "ca": "Ca làm việc",
    "buoc": "Công đoạn",
}

# Xếp hạng 3 mức để rút MỨC NẶNG NHẤT của một cách đặt: chặn-đặt-lịch > chặn-phát-hành > cảnh-báo.
_XL2_MUC_RANK = {C.MUC_CHAN_DAT_LICH: 3, C.MUC_CHAN_PHAT_HANH: 2, C.MUC_CANH_BAO: 1}


def _muc_worst(van_de: list[dict]) -> str | None:
    """Mức nặng nhất trong danh sách vấn đề (None nếu sạch) — để dải chân bàn đếm theo mức."""
    best, br = None, 0
    for i in van_de:
        r = _XL2_MUC_RANK.get(i.get("muc"), 0)
        if r > br:
            br, best = r, i.get("muc")
    return best


@dataclass
class _NhanMaps:
    """Bốn map nhãn nạp theo lô cho một lượt `workspace` — mã lệnh · mã bài · tên hai loại công đoạn."""

    lsx: dict[int, Lsx] = field(default_factory=dict)
    bai_ghep: dict[int, BaiGhep] = field(default_factory=dict)
    lsx_cd: dict[int, str] = field(default_factory=dict)
    bg_cd: dict[int, str] = field(default_factory=dict)


class XepLich2Error(Exception):
    """Lỗi nghiệp vụ Xếp lịch 2 (router map sang HTTP)."""


class XepLich2Conflict(XepLich2Error):
    """Xung đột phiên bản (409) — dòng vừa bị người khác sửa, không ghi đè."""


class XepLich2Blocked(XepLich2Error):
    """Vướng luật CHẶN ĐẶT LỊCH — mang theo danh sách `van_de` để router trả cho UI."""

    def __init__(self, van_de: list[dict]) -> None:
        self.van_de = van_de
        super().__init__("; ".join(i.get("mo_ta", i.get("ma", "")) for i in van_de))


class XepLich2Service:
    def __init__(self, db: Session, repo, audit) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.core = XepLichService(db, repo, audit)
        # v2: nháp CHO PHÉP thiếu vật tư — gỡ dây khoá giữ-chỗ của engine cũ trên bản core RIÊNG
        # này (không đụng engine cũ ở màn khác). Vật tư chỉ chặn lúc phát hành, qua `release`.
        self.core._chan_chua_giu_du = lambda **_: None
        self.ctx = XepLich2Context(db, self.core, repo)
        # Cache nhãn cho `_dien_doi_tuong` — một service sống trong một request nên tra một lần đủ.
        self._ten_may_cache: dict[int, str | None] = {}
        self._ten_to_cache: dict[int, str | None] = {}

    # ================= TẠO NHÁP (đưa vào kế hoạch) =================
    def tao_nhap(self, *, nguon: str, id: int, actor):
        """Đưa một LSX / bài ghép vào kế hoạch dưới dạng NHÁP — không đòi vật tư đủ (§5, §12.10)."""
        if nguon == NGUON_LSX:
            return self.core.dua_vao_lsx(lsx_id=id, actor=actor)
        return self.core.dua_vao_bai_ghep(bai_ghep_id=id, actor=actor)

    def xoa_nhap(self, *, nguon: str, id: int, actor):
        """Bỏ một LSX / bài ghép RA KHỎI kế hoạch nháp — tái dùng `go_lsx`/`go_bai_ghep` engine cũ:
        xoá các dòng nháp và đưa trạng thái nguồn về SẴN SÀNG. Đã phát hành / đang khoá / đang nằm
        trong bài ghép thì engine cũ tự chặn (XepLichConflict) → router map 409, không gỡ nửa vời."""
        if nguon == NGUON_LSX:
            return self.core.go_lsx(lsx_id=id, actor=actor)
        return self.core.go_bai_ghep(bai_ghep_id=id, actor=actor)

    # ================= TÍNH MỘT DÒNG (dẫn xuất, không ghi) =================
    def _shadow(self, dong: XepLichCongDoan, patch: dict) -> SimpleNamespace:
        """Bản sao CHỈ-ĐỌC của dòng đã áp patch — để tính thời lượng/luật mà KHÔNG chạm ORM thật
        (tránh autoflush ghi nhầm một bản xem-trước)."""
        return SimpleNamespace(
            nguon=dong.nguon,
            loai_buoc=getattr(dong, "loai_buoc", LB_MAY),
            lsx_id=dong.lsx_id,
            lsx_cong_doan_id=dong.lsx_cong_doan_id,
            bai_ghep_id=dong.bai_ghep_id,
            bai_ghep_cong_doan_id=dong.bai_ghep_cong_doan_id,
            may_id=patch.get("may_id", dong.may_id),
            department_id=patch.get("department_id", dong.department_id),
            nha_cung_cap=patch.get("nha_cung_cap", dong.nha_cung_cap),
        )

    def _tinh(self, dong: XepLichCongDoan, patch: dict) -> dict:
        shadow = self._shadow(dong, patch)
        start = _aware(patch["start_at"]) if "start_at" in patch else _aware(dong.start_at)
        dur = self._thoi_luong_v2(shadow)
        chiem = int(dur.get("chiem_may_phut") or 0)
        chiem_min = int(dur.get("chiem_may_phut_min") or chiem)
        chiem_max = int(dur.get("chiem_may_phut_max") or chiem)
        canh_bao = dur.get("canh_bao")
        finish = C.finish_lien_tuc(start, chiem) if start is not None else None
        finish_max = C.finish_lien_tuc(start, chiem_max) if start is not None else None
        van_de = self._van_de_dat_lich(
            shadow, start=start, finish=finish, finish_max=finish_max, may_id=shadow.may_id,
            department_id=shadow.department_id, canh_bao=canh_bao, exclude_id=dong.id,
        )
        self._dien_doi_tuong(van_de, may_id=shadow.may_id, department_id=shadow.department_id)
        return {
            "start": start, "finish": finish, "chiem_may_phut": chiem,
            "chiem_may_phut_min": chiem_min, "chiem_may_phut_max": chiem_max,
            "theo_may": bool(dur.get("theo_may")), "canh_bao": canh_bao, "van_de": van_de,
        }

    def _van_de_dat_lich(self, dong, *, start, finish, may_id, department_id,
                         canh_bao, exclude_id, finish_max=None) -> list[dict]:
        """Gom mọi vấn đề của một cách đặt.

        CHẶN ĐẶT LỊCH: ngoài ca · trước ngày vật tư · sai tiền nhiệm · đè khoá máy · trùng máy ·
        vượt quân số · (khi đã chọn giờ mà) thiếu thời lượng / chưa quy đổi.
        CẢNH BÁO (chỉ nhắc): sát hạn SX · đệm giao ngắn · lấn việc kế (chạy tới max) · máy sắp bảo
        trì · tải máy/tổ cao có mức · máy chưa tốc độ / chưa quy đổi lúc còn nháp.
        """
        vd: list[dict] = []
        ca = self.ctx.ca_windows()
        if start is not None:
            for fn in (
                C.ngoai_ca(start, ca),
                C.chua_tai_nguyen(start, may_id, department_id,
                                  getattr(dong, "nha_cung_cap", None)),
                C.truoc_ngay_vat_tu(start, self.ctx.ngay_vat_tu(dong), ca),
                C.sai_tien_nhiem(start, self.ctx.tien_nhiem_finish(dong)),
            ):
                if fn:
                    vd.append(fn)
        if start is not None and finish is not None:
            # Lấy MỘT lần các khoảng của máy rồi dùng lại cho cả cửa chặn lẫn cửa cảnh báo.
            khoa_may = self.ctx.khoang_chan_may(may_id)
            da_xep = self.ctx.khoang_may_da_xep(may_id, exclude_id)
            for fn in (
                C.de_vung_khoa_may(start, finish, khoa_may),
                C.trung_may(start, finish, da_xep),
                C.lan_viec_ke(finish, finish_max, da_xep),
                C.sap_bao_tri(finish, khoa_may),
                C.tai_may_cao(self._tai_may_ngay(may_id, start, finish, da_xep), C.phut_ca_moi_ngay(ca)),
            ):
                if fn:
                    vd.append(fn)
            vd += self._vuot_quan_so(dong, department_id, start, finish, exclude_id)
            han_sx, han_giao = self.ctx.hai_han(dong)
            for fn in (C.sat_han_sx(finish, han_sx, han_giao),
                       C.dem_giao_ngan(han_sx, han_giao)):
                if fn:
                    vd.append(fn)
        if canh_bao:
            if start is not None and canh_bao in _CANH_BAO_CHAN:
                ma, text, goi_y = _CANH_BAO_CHAN[canh_bao]
                vd.append(C.issue(ma, C.MUC_CHAN_DAT_LICH, text, nguon="buoc", goi_y=goi_y))
            else:
                vd.append(C.issue(canh_bao, C.MUC_CANH_BAO,
                                  _CANH_BAO_TEXT.get(canh_bao, "Cần xem lại dữ liệu bước."),
                                  nguon="buoc"))
        return vd

    def _vuot_quan_so(self, dong, department_id, start, finish, exclude_id) -> list[dict]:
        """Đỉnh quân số tổ: vượt hẳn ⇒ CHẶN (`vuot_quan_so_to`); sắp kịch ⇒ CẢNH BÁO có mức
        (`tai_to_cao`). Đo cùng một đỉnh nên hai cửa không lệch nhau."""
        if not department_id:
            return []
        qs = self.ctx.quan_so(department_id, start.date())
        # Tổ chưa khai nhân sự (0 người, không gõ đè) → KHÔNG kết luận hộ: chưa biết năng lực thật.
        if qs["so_nguoi"] <= 0 and not qs["go_de"]:
            return []
        placements = self.ctx.placements_to(department_id, exclude_id)
        placements.append((start, finish, self.ctx._so_nguoi(dong)))
        dinh = C.dinh_dong_thoi(placements)
        if dinh > qs["so_nguoi"]:
            chan = C.vuot_quan_so_to(placements, qs["so_nguoi"])
            return [chan] if chan else []
        canh = C.tai_to_cao(dinh, qs["so_nguoi"])
        return [canh] if canh else []

    def _tai_may_ngay(self, may_id, start, finish, da_xep) -> float:
        """Tổng phút máy `may_id` bị chiếm trong NGÀY của `start` — gồm chính việc đang đặt (`start`,
        `finish`) + các việc đã xếp (`da_xep`), cắt theo ranh giới ngày. Mẫu số đo tải là quỹ giờ ca.

        Không có máy ⇒ 0 (tải máy vô nghĩa khi chưa chọn máy)."""
        if not may_id or start is None or finish is None:
            return 0.0
        d0 = datetime.combine(start.date(), time.min, tzinfo=timezone.utc)
        d1 = d0 + timedelta(days=1)

        def _giao(s, f) -> float:
            if s is None or f is None:
                return 0.0
            return max(0.0, (min(f, d1) - max(s, d0)).total_seconds() / 60.0)

        tong = _giao(start, finish)
        for s, f in da_xep:
            tong += _giao(s, f)
        return tong

    # ================= THỜI LƯỢNG v2 (thuê ngoài đi theo NGÀY, không chiếm máy) =============
    @staticmethod
    def _la_thue_ngoai(dong) -> bool:
        """Bước gia công ngoài — không chiếm máy/tổ nội bộ, thời lượng đo bằng lead-time gửi→nhận."""
        return getattr(dong, "loai_buoc", None) == LB_THUE_NGOAI

    def _op_cua_dong(self, dong):
        """Bước routing GỐC của dòng (để đọc trường thuê-ngoài không snapshot trên dòng lịch)."""
        if getattr(dong, "nguon", None) == NGUON_LSX:
            return self.core._lcd(getattr(dong, "lsx_cong_doan_id", None))
        bgcd_id = getattr(dong, "bai_ghep_cong_doan_id", None)
        return self.db.get(BaiGhepCongDoan, bgcd_id) if bgcd_id else None

    @staticmethod
    def _lead_time_phut(op) -> int:
        """Thời gian một bước THUÊ NGOÀI chiếm chỗ trên lịch = lead-time gửi→nhận, quy ra PHÚT.

        Ưu tiên MỐC NGÀY dự kiến (`ngay_gui_dk`→`ngay_nhan_dk`): người khai hai mốc là đã tự tính
        cả vận chuyển lẫn gia công. Chưa khai mốc thì suy từ số ngày: gia công + 2×vận chuyển (một
        chiều × 2 lượt đi-về). Không đủ dữ liệu ⇒ 0 (engine phơi cảnh báo `thue_ngoai_chua_lich`).
        """
        if op is None:
            return 0
        gui = getattr(op, "ngay_gui_dk", None)
        nhan = getattr(op, "ngay_nhan_dk", None)
        if gui is not None and nhan is not None:
            days = (nhan - gui).days
            if days > 0:
                return days * 1440
        tong_ngay = _f(getattr(op, "gia_cong_ngay", None)) + 2 * _f(getattr(op, "van_chuyen_ngay", None))
        if tong_ngay > 0:
            return int(round(tong_ngay * 1440))
        return 0

    def _thoi_luong_v2(self, dong) -> dict:
        """Thời lượng v2: bước THUÊ NGOÀI đi theo NGÀY gửi/nhận (máy ≈ 0), còn lại uỷ engine cũ.

        Thuê ngoài trả cả cục vào `phat_sinh_phut` (bóc-tách hiện thanh là "khác", không phải chạy
        máy). `thue_ngoai_chua_lich` bật khi chưa đủ dữ liệu tính lead-time — nháp thì chỉ nhắc, đã
        chọn giờ thì `_van_de_dat_lich` nâng lên chặn đặt lịch.
        """
        if not self._la_thue_ngoai(dong):
            return self.core._thoi_luong(dong)
        phut = self._lead_time_phut(self._op_cua_dong(dong))
        return {
            "chiem_may_phut": phut, "chiem_may_phut_min": phut, "chiem_may_phut_max": phut,
            "tong_phut": phut, "setup_phut": 0, "chay_phut": 0, "phat_sinh_phut": phut,
            "theo_may": False,
            "canh_bao": "thue_ngoai_chua_lich" if phut <= 0 else None,
        }

    # ================= NHÃN ĐỐI TƯỢNG cho vấn đề (trình bày) =================
    def _ten_may(self, may_id) -> str | None:
        if not may_id:
            return None
        if may_id not in self._ten_may_cache:
            m = self.db.get(MayThietBi, may_id)
            self._ten_may_cache[may_id] = m.ten if m else None
        return self._ten_may_cache[may_id]

    def _ten_to(self, department_id) -> str | None:
        if not department_id:
            return None
        if department_id not in self._ten_to_cache:
            d = self.db.get(Department, department_id)
            self._ten_to_cache[department_id] = d.name if d else None
        return self._ten_to_cache[department_id]

    def _dien_doi_tuong(self, van_de, *, may_id=None, department_id=None):
        """Điền `doi_tuong` (đối tượng bị ảnh hưởng) cho mỗi vấn đề theo `nguon` — CHỈ trình bày.

        Idempotent: đã có `doi_tuong` thì bỏ qua (lượt ngoài ở `kiem_phat_hanh` không ghi đè nhãn
        đã kèm tên máy/tổ). `may`/`to` lấy tên thật khi biết id; còn lại dùng nhãn tĩnh.
        """
        for i in van_de:
            if i.get("doi_tuong"):
                continue
            ng = i.get("nguon") or ""
            if ng == "may":
                ten = self._ten_may(may_id)
                i["doi_tuong"] = f"Máy {ten}" if ten else "Máy"
            elif ng == "to":
                ten = self._ten_to(department_id)
                i["doi_tuong"] = f"Tổ {ten}" if ten else "Tổ"
            else:
                tinh = _DOI_TUONG_TINH.get(ng)
                if tinh:
                    i["doi_tuong"] = tinh
        return van_de

    # ================= XEM TRƯỚC (không ghi) =================
    def _anh_huong_ha_nguon(self, dong, finish):
        """Ảnh hưởng HẠ NGUỒN nếu đặt `dong` tới `finish` — xem-trước THUẦN, KHÔNG tự dời gì (đúng
        tinh thần v2 xếp tay). Trả `(cong_doan_anh_huong, han_moi, han_sx, han_giao)`:

        - `cong_doan_anh_huong`: bước SAU (thứ tự lớn hơn) trong cùng lệnh/bài ĐÃ có giờ mà lại BẮT
          ĐẦU trước khi bước này xong ⇒ sai thứ tự, người xếp tự cân nhắc dời.
        - `han_moi`: giờ hoàn thành MUỘN NHẤT của lệnh/bài khi thay finish dòng này bằng xem-trước.
        """
        han_sx, han_giao = self.ctx.hai_han(dong)
        if finish is None:
            return [], None, han_sx, han_giao
        if dong.nguon == NGUON_LSX and dong.lsx_id:
            sib = self.repo.by_lsx(dong.lsx_id)
        elif dong.bai_ghep_id:
            sib = self.repo.by_bai_ghep(dong.bai_ghep_id)
        else:
            sib = []
        nhan = self._nap_nhan(sib)
        thu_tu = int(dong.source_thu_tu or 0)
        anh_huong: list[dict] = []
        fins = [finish]                                    # finish xem-trước thay cho finish đã lưu
        for r in sib:
            if r.id == dong.id:
                continue
            rf = _aware(r.finish_at)
            if rf is not None:
                fins.append(rf)
            rs = _aware(r.start_at)
            if int(r.source_thu_tu or 0) > thu_tu and rs is not None and rs < finish:
                ten = (nhan.lsx_cd.get(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
                       else nhan.bg_cd.get(r.bai_ghep_cong_doan_id))
                anh_huong.append({
                    "dong_id": r.id, "thu_tu": int(r.source_thu_tu or 0),
                    "cong_doan_ten": ten, "start_at": _naive(rs), "finish_at": _naive(rf),
                })
        anh_huong.sort(key=lambda x: (x["thu_tu"], x["dong_id"]))
        return anh_huong, max(fins), han_sx, han_giao

    def xem_truoc(self, *, dong_id: int, patch: dict) -> dict:
        dong = self.core._get_dong(dong_id)
        t = self._tinh(dong, patch)
        anh_huong, han_moi, han_sx, han_giao = self._anh_huong_ha_nguon(dong, t["finish"])
        tre = (han_moi.date() - han_sx).days if (han_moi is not None and han_sx is not None) else None
        return {
            "dong_id": dong_id,
            "start_at": _naive(t["start"]),
            "finish_at": _naive(t["finish"]),
            "chiem_may_phut": t["chiem_may_phut"],
            "chiem_may_phut_min": t["chiem_may_phut_min"],
            "chiem_may_phut_max": t["chiem_may_phut_max"],
            "theo_may": t["theo_may"],
            "van_de": t["van_de"],
            # Ảnh hưởng hạ nguồn (item 14): công đoạn sau bị lấn thứ tự + hạn mới của lệnh/bài.
            "cong_doan_anh_huong": anh_huong,
            "han_moi": _naive(han_moi),
            "han_sx": han_sx,
            "han_giao": han_giao,
            "tre_han_sx": bool(tre is not None and tre > 0),
            "tre_ngay": tre if (tre is not None and tre > 0) else None,
        }

    # ================= LƯU (khóa lạc quan + chặn đặt lịch) =================
    def luu(self, *, dong_id: int, patch: dict, expected_updated_at, actor) -> XepLichCongDoan:
        dong = self.core._get_dong(dong_id)
        # 1) Khóa lạc quan theo `updated_at` — người cầm mốc CŨ thì 409, KHÔNG ghi đè (§12.9).
        if _naive(expected_updated_at) != _naive(dong.updated_at):
            raise XepLich2Conflict(
                "Dòng vừa được người khác sửa — tải lại rồi thao tác tiếp (409)."
            )
        if dong.is_locked:
            raise XepLich2Conflict("Dòng đã khóa — mở khóa trước khi sửa")
        # 2) Tính + chặn theo luật ĐẶT LỊCH (cảnh báo không chặn).
        t = self._tinh(dong, patch)
        chan = [i for i in t["van_de"] if i["muc"] == C.MUC_CHAN_DAT_LICH]
        if chan:
            raise XepLich2Blocked(chan)
        # 3) Ghi quyết định + giờ chạy LIÊN TỤC.
        for f in ("may_id", "department_id", "nha_cung_cap", "work_shift_id"):
            if f in patch:
                setattr(dong, f, patch[f])
        dong.start_at = t["start"]
        dong.finish_at = t["finish"]
        co_tai_nguyen = bool(
            dong.may_id or dong.department_id or (dong.nha_cung_cap or "").strip()
        )
        if t["start"] is not None and co_tai_nguyen:
            dong.trang_thai, dong.blocked_reason = TT_DA_XEP, None
        else:
            dong.trang_thai = TT_CHO_XEP
            dong.blocked_reason = LY_DO_THIEU_MAY if not co_tai_nguyen else LY_DO_CHO_TIEN_DE
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_2_luu",
            target=f"xep_lich:{dong.id}",
            detail=f"Xếp lịch 2: dòng {dong.id} → máy {dong.may_id}, bắt đầu {_naive(t['start'])}",
        )
        self.repo.commit()
        return self.core._get_dong(dong_id)

    # ================= PHÁT HÀNH (cửa dùng chung) =================
    def kiem_phat_hanh(self, *, nguon: str, id: int) -> list[dict]:
        """Danh sách vấn đề CHẶN PHÁT HÀNH: vật tư chưa đủ + dòng chưa xếp giờ + luật đặt còn vướng.

        Rỗng ⇒ phát hành được. Cửa vật tư là DÙNG CHUNG (`release`) nên màn cũ vấp đúng luật này.
        """
        vd: list[dict] = []
        if nguon == NGUON_LSX:
            sv = release.soat_vat_tu(self.db, lsx_id=id)
            rows = self.repo.by_lsx(id)
            han_sx, han_giao = self.ctx.hai_han(SimpleNamespace(lsx_id=id, bai_ghep_id=None))
        else:
            sv = release.soat_vat_tu(self.db, bai_ghep_id=id)
            rows = self.repo.by_bai_ghep(id)
            han_sx, han_giao = self.ctx.hai_han(SimpleNamespace(lsx_id=None, bai_ghep_id=id))
        # Vật tư: rổ CHẶN + rổ CẢNH BÁO (đang về có ngày hứa) — cả hai hiện cho UI, chỉ chan mới khoá.
        vd += sv["chan"] + sv["canh_bao"]
        # Hạn ở cấp lệnh/bài (§7.2): thiếu cả hai hạn ⇒ chặn CỨNG; xong sau hạn SX ⇒ chặn NHƯNG duyệt
        # ngoại lệ được (CHỈ mã này). Ngoại lệ còn hiệu lực thì hạ `tre_han_sx` xuống cảnh báo — không
        # khoá phát hành nữa mà vẫn hiện để xưởng biết mình đang chạy dưới một ngoại lệ có thời hạn.
        if (h2 := C.thieu_ca_hai_han(han_sx, han_giao)):
            vd.append(h2)
        fin = max((_aware(r.finish_at) for r in rows if r.finish_at), default=None)
        tre = C.tre_han_sx(fin, han_sx, han_giao)
        if tre:
            tre["issue_key"] = self._key_tre_han(nguon, id)
            if (nl := self._ngoai_le_tre_han(nguon, id, fin)) is not None:
                moc = _naive(nl.exception_expires_at)
                tre["muc"] = C.MUC_CANH_BAO
                tre["mo_ta"] = (
                    "Trễ hạn hoàn thành SX — ĐÃ DUYỆT NGOẠI LỆ"
                    + (f" (neo mốc xong {moc:%d/%m/%Y %H:%M})" if moc else "") + "."
                )
                tre["da_ngoai_le"] = True
            vd.append(tre)
        for r in rows:
            co_tai_nguyen = bool(r.may_id or r.department_id or (r.nha_cung_cap or "").strip())
            if r.start_at is None or not co_tai_nguyen:
                vd.append(C.issue(
                    "con_buoc_chua_xep", C.MUC_CHAN_PHAT_HANH,
                    "Còn công đoạn chưa gán đủ máy/tổ và giờ bắt đầu.",
                    nguon="buoc",
                    goi_y="Xếp giờ cho mọi công đoạn trước khi phát hành.",
                ))
                continue
            t = self._tinh(r, {})
            vd += [i for i in t["van_de"] if i["muc"] == C.MUC_CHAN_DAT_LICH]
        # Điền nhãn ĐỐI TƯỢNG cho các vấn đề cấp lệnh (vật tư/hạn) — vấn đề dòng đã điền ở `_tinh`,
        # guard idempotent nên không ghi đè nhãn đã có tên máy/tổ.
        self._dien_doi_tuong(vd)
        return vd

    @staticmethod
    def _key_tre_han(nguon: str, id: int) -> str:
        """Vân tay ngoại lệ trễ-hạn của MỘT lệnh/bài — RIÊNG của v2 (màn cũ không đẻ key `tre_han_sx:`
        nên hai màn không giẫm nhau); lưu chung bảng `xep_lich_van_de`, đúng cơ chế `issue_key`."""
        return f"tre_han_sx:{nguon}:{id}"

    def _ngoai_le_tre_han(self, nguon: str, id: int, finish_hien_tai):
        """Dòng ngoại lệ CÒN hiệu lực cho `tre_han_sx` — NEO THEO MỐC ĐÃ DUYỆT (§7.2, lựa chọn của chủ
        dự án). Lúc duyệt, `exception_expires_at` giữ MỐC hoàn thành đang có; ngoại lệ chỉ còn giá trị
        khi lịch làm xong KHÔNG MUỘN HƠN mốc đó. Dời lịch xong trễ hơn mốc ⇒ mất hiệu lực, phải duyệt
        lại — một chữ ký 'tha trễ 1 ngày' không lỡ tha luôn 'trễ 1 tháng'. None nếu chưa duyệt."""
        row = XepLichVanDeRepository(self.db).get_by_key(self._key_tre_han(nguon, id))
        if row is None or row.trang_thai != TT_NGOAI_LE:
            return None
        moc = _aware(row.exception_expires_at)
        fin = _aware(finish_hien_tai)
        if moc is not None and fin is not None and fin > moc:
            return None
        return row

    #: Mã CHẶN PHÁT HÀNH mà v2 tự siết CỨNG ngay trước khi uỷ quyền cho service màn cũ. Lọc kèm `muc`
    #: nên một `tre_han_sx` ĐÃ DUYỆT NGOẠI LỆ (đã bị `kiem_phat_hanh` hạ xuống cảnh báo) KHÔNG còn
    #: chặn. Thiếu cả hai hạn / còn bước trống giờ là ràng buộc toàn vẹn — không có ngoại lệ. Vật tư
    #: thì cửa dùng chung màn cũ lo qua `_chan_thieu_vat_tu`, không nhắc lại ở đây.
    _MA_CHAN_CUNG = frozenset({"thieu_ca_hai_han", "con_buoc_chua_xep", "tre_han_sx"})

    def phat_hanh(self, *, nguon: str, id: int, actor):
        """Phát hành qua cửa dùng chung — uỷ quyền service màn cũ (đã gắn gate vật tư v2 ở §9.3).

        v2 siết thêm cửa riêng TRƯỚC khi uỷ quyền: thiếu cả hai hạn · còn bước chưa xếp giờ · TRỄ HẠN
        SX chưa duyệt ngoại lệ (§7.2). Ngoại lệ còn hiệu lực đã hạ `tre_han_sx` xuống cảnh báo ở
        `kiem_phat_hanh` nên lọt cửa này. Cửa chỉ chạy trên đường v2, không đụng phát hành màn cũ."""
        chan = [i for i in self.kiem_phat_hanh(nguon=nguon, id=id)
                if i["ma"] in self._MA_CHAN_CUNG and i["muc"] == C.MUC_CHAN_PHAT_HANH]
        if chan:
            raise XepLich2Blocked(chan)
        from ..xep_lich_van_de_service import XepLichVanDeService

        svc = XepLichVanDeService(self.db, self.audit)
        if nguon == NGUON_LSX:
            return svc.phat_hanh_lsx(lsx_id=id, actor=actor)
        return svc.phat_hanh_bai_ghep(bai_ghep_id=id, actor=actor)

    def duyet_ngoai_le(self, *, nguon: str, id: int, ly_do: str, actor):
        """Duyệt NGOẠI LỆ cho DUY NHẤT `tre_han_sx` (§7.2): trễ hạn SX vẫn cho phát hành, kèm lý do.
        NEO THEO MỐC ĐÃ DUYỆT — ghi lại MỐC hoàn thành hiện tại vào `exception_expires_at`; sau này dời
        lịch xong muộn hơn mốc thì ngoại lệ tự mất hiệu lực, phải trình duyệt lại. Tái dùng kho ngoại
        lệ `xep_lich_van_de` (chung màn cũ), key riêng của v2.

        Chỉ duyệt khi lệnh ĐANG THỰC SỰ vướng trễ hạn (đã xếp giờ, xong sau hạn, CHƯA có ngoại lệ còn
        hiệu lực) — không mở ngoại lệ cho vấn đề không tồn tại; quyền `approve_exception` gác ở router."""
        ly_do = (ly_do or "").strip()
        if len(ly_do) < 3:
            raise XepLich2Error("Nêu lý do duyệt ngoại lệ (tối thiểu 3 ký tự).")
        rows = self.repo.by_lsx(id) if nguon == NGUON_LSX else self.repo.by_bai_ghep(id)
        moc = max((_aware(r.finish_at) for r in rows if r.finish_at), default=None)
        dang_tre = any(
            i["ma"] == "tre_han_sx" and i["muc"] == C.MUC_CHAN_PHAT_HANH
            for i in self.kiem_phat_hanh(nguon=nguon, id=id)
        )
        if not dang_tre:
            raise XepLich2Error("Lệnh không vướng trễ hạn hoàn thành SX — không cần duyệt ngoại lệ.")
        from ..xep_lich_van_de_service import XepLichVanDeService

        svc = XepLichVanDeService(self.db, self.audit)
        svc.ngoai_le(issue_key=self._key_tre_han(nguon, id), ly_do=ly_do,
                     expires_at=moc, actor=actor)
        return {"ok": True, "nguon": nguon, "id": id,
                "issue_key": self._key_tre_han(nguon, id),
                "moc_da_duyet": _naive(moc).isoformat() if moc else None}

    def thu_hoi(self, *, nguon: str, id: int, actor, ly_do: str | None = None):
        from ..xep_lich_van_de_service import XepLichVanDeService

        svc = XepLichVanDeService(self.db, self.audit)
        if nguon == NGUON_LSX:
            return svc.go_phat_hanh_lsx(lsx_id=id, actor=actor, ly_do=ly_do)
        return svc.go_phat_hanh_bai_ghep(bai_ghep_id=id, actor=actor, ly_do=ly_do)

    # ================= PHÁT HÀNH CẬP NHẬT — phiên bản lịch (§4.3) =================
    def goi_phat_hanh(self, *, nguon: str, id: int) -> dict:
        """Trạng thái gói phát hành của một LSX/bài ghép (phiên bản + số việc đã/chưa bắt đầu) — cho
        UI quyết bày nút 'Phát hành cập nhật' / 'Thu hồi'. Chỉ đọc."""
        from ..san_xuat import release_update

        return release_update.thong_tin_goi(self.db, nguon=nguon, id=id)

    def phat_hanh_cap_nhat(self, *, nguon: str, id: int, ly_do: str, actor) -> dict:
        """Tái chụp việc CHƯA bắt đầu theo lịch hiện tại → phiên bản mới (§4.3).

        Siết đúng cửa CHẶN như phát hành lần đầu (thiếu hạn · còn bước chưa xếp giờ · trễ hạn chưa
        duyệt) — lịch cập nhật phải còn hợp lệ mới cho đóng băng lại. Uỷ nghiệp vụ cho service
        san_xuat; đổi ValueError của nó sang lỗi v2 để router ánh xạ đúng HTTP."""
        chan = [i for i in self.kiem_phat_hanh(nguon=nguon, id=id)
                if i["ma"] in self._MA_CHAN_CUNG and i["muc"] == C.MUC_CHAN_PHAT_HANH]
        if chan:
            raise XepLich2Blocked(chan)
        from ..san_xuat import release_update

        try:
            return release_update.phat_hanh_cap_nhat(self.db, nguon=nguon, id=id, ly_do=ly_do, actor=actor)
        except ValueError as exc:
            raise XepLich2Error(str(exc)) from exc

    # ================= HÀNG CHỜ + BÀN LÀM VIỆC =================
    def queue(self, *, trang: int = 1, moi_trang: int = 50, q: str | None = None, loc: str = "all") -> dict:
        """Hàng chờ chia HAI rổ: `xep_duoc` (đủ giấy) · `bi_chan` (thiếu vật tư). Cờ gấp nổi lên (§12.7).

        Cắt trang + LỌC + ĐẾM đều Ở MÁY CHỦ (cấm cắt-trang ở JS): repo gộp hai nguồn, lọc theo `q` (mã)
        và `loc` (chip all/tre/gap), sắp gấp-trước rồi trả đúng một trang; vật tư chỉ tính trên số dòng
        của trang. Mỗi dòng kèm `han_giao` (hạn giao khách — bài ghép không có) + `so_cong_doan_chua_xep`
        để người xếp ước lượng việc TRƯỚC khi mở lệnh.

        `tong`/`so_trang` tính trên KẾT QUẢ LỌC (để thanh phân trang khớp danh sách đang thấy); `facets`
        đếm TOÀN hàng chờ theo từng chip (gợi ý điều hướng, không đổi theo q/loc); `dem_trang` chỉ đếm rổ
        trong trang hiện tại (chia rổ cần soi vật tư từng dòng nên không đếm được cả kho mà không quét)."""
        trang = max(1, int(trang or 1))
        moi_trang = min(200, max(1, int(moi_trang or 50)))
        loc = loc if loc in ("all", "tre", "gap") else "all"
        refs, tong, facets = self.repo.hang_cho_trang(
            offset=(trang - 1) * moi_trang, limit=moi_trang, q=q, loc=loc
        )
        lsx_by_id = self.repo.lsx_map(i for (n, i) in refs if n == NGUON_LSX)
        bg_by_id = self.repo.bai_ghep_map(i for (n, i) in refs if n == NGUON_IN_GHEP)
        so_cd_lsx = self.repo.lsx_so_cong_doan_map(lsx_by_id.keys())
        so_cd_bg = self.repo.bai_ghep_so_cong_doan_map(bg_by_id.keys())
        xep_duoc: list[dict] = []
        bi_chan: list[dict] = []
        for nguon, id in refs:
            if nguon == NGUON_LSX:
                lsx = lsx_by_id.get(id)
                if lsx is None:
                    continue
                vd = release.van_de_vat_tu(self.db, lsx_id=id)
                row = {
                    "nguon": NGUON_LSX, "id": id, "ma": lsx.ma,
                    "is_rush": bool(getattr(lsx, "is_rush", False)),
                    "han": self.core._han(lsx),
                    "han_giao": lsx.han_giao_khach,
                    "so_cong_doan_chua_xep": int(so_cd_lsx.get(id, 0)),
                    "van_de": vd,
                }
            else:
                bg = bg_by_id.get(id)
                if bg is None:
                    continue
                vd = release.van_de_vat_tu(self.db, bai_ghep_id=id)
                row = {
                    "nguon": NGUON_IN_GHEP, "id": id, "ma": bg.ma,
                    "is_rush": bool(getattr(bg, "is_rush", False)),
                    "han": None,
                    "han_giao": None,
                    "so_cong_doan_chua_xep": int(so_cd_bg.get(id, 0)),
                    "van_de": vd,
                }
            (bi_chan if vd else xep_duoc).append(row)
        return {
            "xep_duoc": xep_duoc,
            "bi_chan": bi_chan,
            "trang": trang,
            "moi_trang": moi_trang,
            "tong": tong,
            "so_trang": max(1, -(-tong // moi_trang)),
            "dem_trang": {"xep_duoc": len(xep_duoc), "bi_chan": len(bi_chan)},
            "facets": facets,
        }

    # ================= BỐI CẢNH MỘT LỆNH/BÀI (dữ liệu Panel phải) =================
    def boi_canh(self, *, nguon: str, id: int) -> dict:
        """Toàn bộ dữ liệu Panel phải cho MỘT lệnh/bài (§8): đầu thực thể · hai hạn + đệm · vật tư ·
        danh sách chặn-cảnh báo cấp lệnh · chuỗi DAG các bước kèm thời lượng/máy/tổ/định biên/quân số.

        Đọc thuần, KHÔNG ghi. Chưa 'Đưa vào kế hoạch' thì `buoc` rỗng (`da_vao_ke_hoach=False`) — Panel
        chỉ hiện đầu thực thể + vật tư + vấn đề, đúng như EntityPanel cũ; đã có nháp thì bày cả chuỗi.
        """
        if nguon == NGUON_LSX:
            ent = self.core.lsx_repo.get(id)
            if ent is None:
                raise XepLichNotFound(f"Không thấy lệnh sản xuất #{id}")
            rows = self.repo.by_lsx(id)
            shadow = SimpleNamespace(lsx_id=id, bai_ghep_id=None)
        elif nguon == NGUON_IN_GHEP:
            ent = self.db.get(BaiGhep, id)
            if ent is None:
                raise XepLichNotFound(f"Không thấy bài ghép #{id}")
            rows = self.repo.by_bai_ghep(id)
            shadow = SimpleNamespace(lsx_id=None, bai_ghep_id=id)
        else:
            raise XepLich2Error(f"Nguồn không hợp lệ: {nguon!r} (cần 'lsx' hoặc 'in_ghep').")

        han_sx, han_giao = self.ctx.hai_han(shadow)
        dem_ngay = (han_giao - han_sx).days if (han_sx and han_giao) else None
        rows = sorted(rows, key=lambda r: (int(r.source_thu_tu or 0), r.id))
        nhan = self._nap_nhan(rows)
        return {
            "nguon": nguon,
            "id": id,
            "ma": ent.ma,
            "ten_san_pham": ent.ten,
            "is_rush": bool(getattr(ent, "is_rush", False)),
            "han_sx": han_sx,
            "han_giao": han_giao,
            "dem_ngay": dem_ngay,
            "da_vao_ke_hoach": bool(rows),
            "vat_tu": self._vat_tu_tom_tat(nguon, id),
            "van_de": self.kiem_phat_hanh(nguon=nguon, id=id),
            "buoc": [self._buoc_view(r, nhan) for r in rows],
        }

    def _vat_tu_tom_tat(self, nguon: str, id: int) -> dict:
        """Tóm tắt vật tư ở mức SCALAR cho Panel: đủ chưa · mấy món còn thiếu · mấy món đang giữ · ngày
        xếp sớm nhất. Chi tiết đỏ/vàng đã nằm trong `van_de` (cửa dùng chung); đây chỉ là thẻ tóm tắt.

        Bảng cân đối hỏng thì NÓI (`loi=True`) chứ không im lặng báo 'đủ' — đồng bộ tinh thần `release`.
        """
        kw = {"lsx_id": id} if nguon == NGUON_LSX else {"bai_ghep_id": id}
        try:
            tt = release.trang_thai_giu_cho(self.db, **kw)
        except Exception:                                             # noqa: BLE001
            return {"bat": False, "du": False, "khong_ro": True, "so_mon_thieu": None,
                    "so_mon_dang_giu": None, "xep_som_nhat": None, "loi": True}
        return {
            "bat": bool(tt.get("bat")),
            "du": bool(tt.get("du")),
            "khong_ro": bool(tt.get("khong_ro")),
            "so_mon_thieu": len(tt.get("thieu") or {}),
            "so_mon_dang_giu": len(tt.get("dang_giu") or {}),
            "xep_som_nhat": tt.get("xep_som_nhat"),
            "loi": False,
        }

    def _buoc_view(self, r: XepLichCongDoan, nhan: "_NhanMaps") -> dict:
        """Một BƯỚC trong chuỗi DAG cho Panel: thời lượng ba mức + nguồn tính · máy/tổ/NCC · số người
        kế hoạch + định biên tham khảo · quân số tổ và phần còn rảnh · vấn đề của bước.

        Thời lượng/vấn đề dùng lại `_tinh` (đúng số như xem-trước); định biên đọc từ bước routing gốc."""
        t = self._tinh(r, {})
        op = self._op_cua_dong(r)
        if self._la_thue_ngoai(r):
            nguon_tl = "thue_ngoai"
        elif t["theo_may"]:
            nguon_tl = "may"
        else:
            nguon_tl = "tay"
        cong_doan_ten = (nhan.lsx_cd.get(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
                         else nhan.bg_cd.get(r.bai_ghep_cong_doan_id))
        return {
            "id": r.id,
            "thu_tu": int(r.source_thu_tu or 0),
            "cong_doan_ten": cong_doan_ten,
            "loai_buoc": r.loai_buoc,
            "trang_thai": r.trang_thai,
            "is_locked": bool(r.is_locked),
            "start_at": _naive(t["start"]),
            "finish_at": _naive(t["finish"]),
            "chiem_may_phut": t["chiem_may_phut"],
            "chiem_may_phut_min": t["chiem_may_phut_min"],
            "chiem_may_phut_max": t["chiem_may_phut_max"],
            "theo_may": t["theo_may"],
            "nguon_thoi_luong": nguon_tl,
            "may_id": r.may_id,
            "may_ten": self._ten_may(r.may_id),
            "department_id": r.department_id,
            "to_ten": self._ten_to(r.department_id),
            "nha_cung_cap": (r.nha_cung_cap or None),
            "so_nhan_cong": int(getattr(op, "so_nhan_cong", 1) or 1) if op is not None else None,
            "dinh_bien": self._dinh_bien(op),
            "quan_so": self._quan_so_buoc(r, r.department_id, t["start"], t["finish"]),
            "van_de": t["van_de"],
        }

    @staticmethod
    def _dinh_bien(op) -> dict:
        """Ba mốc định biên tham khảo của bước (kế thừa từ danh mục, sửa được tại bước). None nếu
        bước routing đã bị xoá — Panel hiện '—' thay vì đoán bừa."""
        if op is None:
            return {"toi_thieu": None, "tieu_chuan": None, "toi_da": None}
        return {
            "toi_thieu": getattr(op, "so_nhan_cong_toi_thieu", None),
            "tieu_chuan": getattr(op, "so_nhan_cong_tieu_chuan", None),
            "toi_da": getattr(op, "so_nhan_cong_toi_da", None),
        }

    def _quan_so_buoc(self, r: XepLichCongDoan, department_id, start, finish) -> dict | None:
        """Quân số tổ NGÀY bước chạy + phần CÒN RẢNH tại đỉnh chồng giờ (gồm chính bước này).

        `con_ranh = quân số - đỉnh đồng thời` (âm ⇒ đang quá tải). Chưa gán tổ / chưa có giờ ⇒ None
        (quân số vô nghĩa khi chưa biết ngày chạy). Đo cùng đỉnh với `_vuot_quan_so` nên hai chỗ khớp."""
        if not department_id or start is None or finish is None:
            return None
        qs = self.ctx.quan_so(department_id, start.date())
        placements = self.ctx.placements_to(department_id, r.id)
        placements.append((start, finish, self.ctx._so_nguoi(r)))
        dinh = C.dinh_dong_thoi(placements)
        return {
            "so_nguoi": qs["so_nguoi"],
            "go_de": qs["go_de"],
            "dinh": dinh,
            "con_ranh": qs["so_nguoi"] - dinh,
        }

    def _dong_view(self, r: XepLichCongDoan, nhan: "_NhanMaps") -> dict:
        # Nhãn dẫn xuất: dòng chỉ neo id nên tra mã lệnh + tên sản phẩm + tên công đoạn từ các map
        # đã nạp theo lô (không join trong vòng lặp). LSX ăn nhánh lsx_*, bài ghép ăn nhánh bg_*.
        if r.nguon == NGUON_LSX:
            lsx = nhan.lsx.get(r.lsx_id)
            lsx_ma = lsx.ma if lsx else None
            bai_ghep_ma = None
            ten_san_pham = lsx.ten if lsx else None
            cong_doan_ten = nhan.lsx_cd.get(r.lsx_cong_doan_id)
        else:
            bg = nhan.bai_ghep.get(r.bai_ghep_id)
            lsx_ma = None
            bai_ghep_ma = bg.ma if bg else None
            ten_san_pham = bg.ten if bg else None
            cong_doan_ten = nhan.bg_cd.get(r.bai_ghep_cong_doan_id)
        return {
            "id": r.id, "nguon": r.nguon, "lsx_id": r.lsx_id, "bai_ghep_id": r.bai_ghep_id,
            "may_id": r.may_id, "department_id": r.department_id,
            # NCC + loại bước để bàn gom lane THUÊ NGOÀI theo từng nhà cung cấp (không còn một khay
            # "chưa rõ NCC" gộp mọi thứ). Cả hai đã nằm sẵn trên dòng, khỏi join thêm.
            "nha_cung_cap": (r.nha_cung_cap or None),
            "loai_buoc": r.loai_buoc,
            "start_at": _naive(_aware(r.start_at)), "finish_at": _naive(_aware(r.finish_at)),
            "trang_thai": r.trang_thai, "is_locked": bool(r.is_locked),
            "updated_at": _naive(r.updated_at),
            # Nhãn cho thanh/cụm: mã lệnh (LSX) hoặc mã bài ghép (GB), tên sản phẩm, tên công đoạn
            # của bước, và thứ tự bước trong chuỗi (snapshot sẵn trên dòng, khỏi join).
            "lsx_ma": lsx_ma,
            "bai_ghep_ma": bai_ghep_ma,
            "ten_san_pham": ten_san_pham,
            "cong_doan_ten": cong_doan_ten,
            "buoc_thu_tu": int(r.source_thu_tu or 0),
            # "Râu" giải thích độ dài thanh: chỉ tính cho dòng ĐÃ có giờ (thanh nằm trên trục thời
            # gian). Nháp chưa-giờ nằm ở cụm "Chưa đặt giờ", không có thanh để bóc tách → None.
            "boc_tach": self._boc_tach(r) if r.start_at is not None else None,
            # Mức NẶNG NHẤT của thanh tại chỗ đang đặt (chan_dat_lich | canh_bao | None) — dùng
            # chung detector `_van_de_dat_lich` với panel/xem-trước nên dải chân bàn khớp từng thanh.
            # Chỉ tính cho dòng đã có giờ (nháp chưa-giờ không có thanh để đếm mức).
            "muc": _muc_worst(self._tinh(r, {})["van_de"]) if r.start_at is not None else None,
        }

    def dong_view(self, r: XepLichCongDoan) -> dict:
        """View MỘT dòng (router `PUT /dong` trả về sau khi lưu) — tự nạp map nhãn cho đúng dòng đó."""
        return self._dong_view(r, self._nap_nhan([r]))

    def _nap_nhan(self, rows: list[XepLichCongDoan]) -> "_NhanMaps":
        """Nạp theo LÔ mã lệnh / mã bài ghép / tên công đoạn cho MỌI dòng trong một lượt (tránh N+1)."""
        return _NhanMaps(
            lsx=self.repo.lsx_map(r.lsx_id for r in rows),
            bai_ghep=self.repo.bai_ghep_map(r.bai_ghep_id for r in rows),
            lsx_cd=self.repo.lsx_cong_doan_ten_map(r.lsx_cong_doan_id for r in rows),
            bg_cd=self.repo.bai_ghep_cong_doan_ten_map(r.bai_ghep_cong_doan_id for r in rows),
        )

    def _boc_tach(self, r: XepLichCongDoan) -> dict:
        """Bóc thời lượng một thanh thành CANH MÁY + CHẠY + KHÁC — để "râu" trên Gantt tự nói vì sao dài.

        Ba cấu phần THẬT engine cộng ra giờ chiếm máy (rửa mực đã bỏ 2026-08-04):
            chiếm máy = canh máy (`setup_phut`, lên khuôn) + chạy (`chay_phut`, sản lượng)
                        + khác (`phat_sinh_phut`, thời gian khai tay).
        Hiển thị số NGUYÊN nên để khỏi lệch làm tròn (canh + chạy + khác ≠ chiếm), giữ nguyên canh máy
        và khác, còn CHẠY suy từ hiệu — phần lẻ rơi vào bucket lớn nhất, ba số luôn khép đúng thanh.
        Min/max đi kèm để hiện dải khi bước có khoảng thời lượng."""
        d = self._thoi_luong_v2(r)
        chiem = int(d.get("chiem_may_phut") or 0)
        canh_may = int(d.get("setup_phut") or 0)
        khac = int(d.get("phat_sinh_phut") or 0)
        chay = max(chiem - canh_may - khac, 0)
        return {
            "chiem_may_phut": chiem,
            "chiem_may_phut_min": int(d.get("chiem_may_phut_min") or 0),
            "chiem_may_phut_max": int(d.get("chiem_may_phut_max") or 0),
            "canh_may_phut": canh_may,
            "chay_phut": chay,
            "khac_phut": khac,
            "theo_may": bool(d.get("theo_may")),
            "canh_bao": d.get("canh_bao"),
        }

    def workspace(self, *, tu: date, den: date) -> dict:
        """Một BÀN làm việc [tu, den] trong MỘT cú gọi (§8, §9.2): ca nền · ngày lễ · vùng khoá máy ·
        lớp phủ tải máy + đỉnh quân số · các dòng trên bàn. Gộp hết để màn khỏi gọi lắt nhắt nhiều lần.

        Dòng gồm HAI nhóm: đã xếp có giờ CHẠM cửa sổ (windowed) + nháp CHƯA đặt giờ (hiện trên mọi
        bàn tới khi được xếp). Lớp phủ chỉ gộp trên nhóm ĐÃ có giờ trong cửa sổ."""
        da_xep = self.repo.da_xep_trong_khoang(tu, den)
        nhap = self.repo.nhap_chua_gio()
        co_gio = [r for r in da_xep if r.start_at is not None]
        nhan = self._nap_nhan(da_xep + nhap)  # gom id CẢ hai nhóm rồi tra map một lượt
        dong = [self._dong_view(r, nhan) for r in da_xep]
        dong += [self._dong_view(r, nhan) for r in nhap]
        pl_may = [(r.may_id, _aware(r.start_at), _aware(r.finish_at)) for r in co_gio if r.may_id]
        pl_to = [(r.department_id, _aware(r.start_at), _aware(r.finish_at), self.ctx._so_nguoi(r))
                 for r in co_gio if r.department_id]
        dinh = overlay.dinh_quan_so(pl_to, tu, den)
        tai_to = [
            {"department_id": dept, "ngay": ngay, "dinh": d, **self._quan_so_kha_dung(dept, ngay)}
            for (dept, ngay), d in sorted(dinh.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        ]
        return {
            "tu": tu, "den": den,
            "ca": self.ctx.ca_windows(),
            "ngay_le": self.ctx.ngay_le(tu, den),
            "khoa_may": self._khoa_may_trong_cua_so({r.may_id for r in co_gio if r.may_id}, tu, den),
            "tai_may": overlay.tai_may(pl_may, tu, den),
            "tai_to": tai_to,
            "dong": dong,
        }

    def _quan_so_kha_dung(self, department_id: int, ngay: date) -> dict:
        """Quân số khả dụng của tổ trong ngày, đủ để UI đặt cạnh ĐỈNH mà biết tổ có quá tải không."""
        qs = self.ctx.quan_so(department_id, ngay)
        return {"so_nguoi": qs["so_nguoi"], "go_de": qs["go_de"]}

    def _khoa_may_trong_cua_so(self, may_ids, tu: date, den: date) -> list[dict]:
        """Vùng KHOÁ máy (bảo trì/hỏng/nghỉ) CẮT vào [tu, den] — nền để Gantt tô mảng máy không dùng
        được, đúng vùng engine né khi dò `de_vung_khoa_may`."""
        d0 = datetime.combine(tu, time.min, tzinfo=timezone.utc)
        d1 = datetime.combine(den, time.min, tzinfo=timezone.utc) + timedelta(days=1)
        out: list[dict] = []
        for may_id in sorted(may_ids):
            for k_start, k_finish in self.ctx.khoang_chan_may(may_id):
                ks, kf = _aware(k_start), _aware(k_finish)
                if ks is None or kf is None or kf <= d0 or ks >= d1:
                    continue
                out.append({"may_id": may_id, "start_at": _naive(max(ks, d0)),
                            "finish_at": _naive(min(kf, d1))})
        return out

    # ================= GỢI Ý MÁY + KHE TRỐNG =================
    def goi_y(self, *, dong_id: int) -> dict:
        return suggestion.goi_y(self, dong_id=dong_id)

    def goi_y_khe(self, *, dong_id: int, tu: date, den: date, toi_da: int = 3) -> dict:
        """Chấm ≤ `toi_da` khe trống sớm nhất để xếp dòng (B8) — người bấm một phát là xong."""
        return suggestion.goi_y_khe(self, dong_id=dong_id, tu=tu, den=den, toi_da=toi_da)
