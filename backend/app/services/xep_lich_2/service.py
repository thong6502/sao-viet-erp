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
from ...repositories.don_vi_do_repo import DonViDoRepository
from ...repositories.xep_lich_van_de_repo import XepLichVanDeRepository
from ..lsx_service import _f
from ..xep_lich_service import XepLichNotFound, XepLichService, _aware, _naive
from . import constraint as C
from . import auto, chan_doan, overlay, release, suggestion
from .context import XepLich2Context
from .thuc_te import nap_thuc_te

# Mã CHẶN tương ứng khi ĐÃ chọn giờ mà engine không tính nổi thời lượng: thiếu dữ liệu này biến
# lịch thành vô nghĩa ⇒ nâng từ cảnh báo lên CHẶN ĐẶT LỊCH (spec §7.1). Lúc mới tạo nháp (chưa có
# giờ) thì vẫn chỉ nhắc, không cản người đưa lệnh vào kế hoạch.
# CÂU CHỮ không nằm ở đây: `chan_doan.chi_tiet` dựng câu từ chính dữ liệu bước đang đứng (loại bước ·
# số lượng vào · đơn vị nguồn/đích · tên máy hay đầu việc khoán), nên bước tổ không bị đọc câu của
# bước máy và người xếp thấy luôn con số đang vướng.
_MA_CHAN = {
    "may_chua_toc_do": "thieu_thoi_luong",
    "chua_quy_doi": "thieu_quy_doi",
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


def _goi_ten(ten: str, loai: str) -> str:
    """Gọi tên tài nguyên trong câu văn — KHÔNG lặp loại khi tên đã tự mang loại.

    Danh mục máy/tổ do người dùng khai, tên thường đã có sẵn chữ "Máy …" / "Tổ …" (dữ liệu thật:
    "Máy bế tự động Yawa 1050", "Tổ Đóng gói"); ghép cứng tiền tố sẽ ra "máy Máy bế tự động".
    """
    t = (ten or "").strip()
    return t if t.lower().startswith(loai.lower() + " ") else f"{loai} {t}"


def _muc_worst(van_de: list[dict]) -> str | None:
    """Mức nặng nhất trong danh sách vấn đề (None nếu sạch) — để dải chân bàn đếm theo mức."""
    best, br = None, 0
    for i in van_de:
        r = _XL2_MUC_RANK.get(i.get("muc"), 0)
        if r > br:
            br, best = r, i.get("muc")
    return best


#: Không có khuôn để nói — dòng bài ghép, dòng chưa neo bước, bước không cần dụng cụ. Phải là một
#: khối ĐỦ KHOÁ (không phải `{}`) để thanh Gantt luôn đọc được `requires_tooling`/`khuon_ma`.
KHUON_TRONG = {
    "requires_tooling": False, "khuon_ma": None, "khuon_so_ke": None,
    "khuon_tinh_trang": None, "khuon_ngay_ve": None,
}


@dataclass
class _NhanMaps:
    """Bốn map nhãn nạp theo lô cho một lượt `workspace` — mã lệnh · mã bài · hai loại công đoạn.

    Hai map công đoạn mang CẶP `(tên, SL vào)`: dòng lịch chỉ neo id bước, mà bàn cần cả nhãn để vẽ
    thanh lẫn tổng của bước để biết chia lần chạy được hay không. Tra qua `ten_cd` / `sl_vao_cd`
    thay vì đọc thẳng map — dòng LSX và dòng bài ghép ăn hai map khác nhau, viết tay chỗ nào cũng
    lặp đúng câu điều kiện ấy."""

    lsx: dict[int, Lsx] = field(default_factory=dict)
    bai_ghep: dict[int, BaiGhep] = field(default_factory=dict)
    lsx_cd: dict[int, tuple[str, float]] = field(default_factory=dict)
    bg_cd: dict[int, tuple[str, float]] = field(default_factory=dict)
    #: Khuôn/khung theo bước LSX — chỉ dòng LSX có; dòng bài ghép luôn rơi về `KHUON_TRONG`.
    khuon: dict[int, dict] = field(default_factory=dict)

    def _cd(self, r) -> tuple[str, float] | None:
        return (self.lsx_cd.get(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
                else self.bg_cd.get(r.bai_ghep_cong_doan_id))

    def ten_cd(self, r) -> str | None:
        """Tên công đoạn của bước dòng đang neo (None khi dòng chưa neo bước / bước đã xoá)."""
        cd = self._cd(r)
        return cd[0] if cd else None

    def sl_vao_cd(self, r) -> float | None:
        """SL VÀO của bước — None khi chưa neo bước, 0 khi bước có nhưng chưa khai số lượng."""
        cd = self._cd(r)
        return cd[1] if cd else None

    def khuon_cua(self, r) -> dict:
        """Khối khuôn của dòng — rỗng cho dòng bài ghép và dòng chưa neo bước LSX."""
        if r.nguon != NGUON_LSX:
            return KHUON_TRONG
        return self.khuon.get(r.lsx_cong_doan_id or 0, KHUON_TRONG)


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
        self._ten_dv_cache: dict[str, str] | None = None

    def ten_don_vi(self) -> dict[str, str]:
        """Bảng MÃ đơn vị → TÊN hiển thị, cho câu chẩn đoán của `chan_doan` bày ra người đọc.

        Một lượt dò gọi `chan_doan.chi_tiet` cho TỪNG dòng, nên tra thẳng danh mục trong đó là
        N+1 truy vấn. Nhớ trên service — service sống trong đúng một request, cùng lối
        `_ten_may_cache`.
        """
        if self._ten_dv_cache is None:
            self._ten_dv_cache = DonViDoRepository(self.db).ten_theo_ma()
        return self._ten_dv_cache

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
            # Chiều PHÂN ĐOẠN phải đi theo bản sao: engine thời lượng tra cụm bằng `id`/
            # `goc_dong_id` rồi nhân tỉ lệ. Bỏ sót là dòng đã tách 6.000 vẫn được xem-trước và
            # LƯU theo thời lượng của trọn 10.000 — đúng cái thanh dài sai mà tách sinh ra để tránh.
            id=dong.id,
            so_luong=getattr(dong, "so_luong", None),
            phan_doan_so=getattr(dong, "phan_doan_so", 1),
            phan_doan_tong=getattr(dong, "phan_doan_tong", 1),
            goc_dong_id=getattr(dong, "goc_dong_id", None),
        )

    def _tinh(self, dong: XepLichCongDoan, patch: dict) -> dict:
        shadow = self._shadow(dong, patch)
        # TRÒN PHÚT ngay từ đây: `luu` ghi thẳng `t["start"]`/`t["finish"]` nên chuẩn hoá một chỗ
        # là cả xem-trước lẫn bản ghi đều sạch giây (xem `C.tron_phut`).
        start = C.tron_phut(
            _aware(patch["start_at"]) if "start_at" in patch else _aware(dong.start_at))
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

        CHẶN ĐẶT LỊCH: ngoài ca · trước ngày vật tư · sai tiền nhiệm · trùng máy · (khi đã chọn
        giờ mà) thiếu thời lượng / chưa quy đổi.
        CẢNH BÁO (chỉ nhắc): đè khoá máy · vượt quân số tổ (cả hai HẠ từ chặn xuống nhắc ngày
        21/08/2026 — xưởng vẫn chạy đè được, máy chỉ là kế hoạch) · sát hạn SX · đệm giao ngắn ·
        lấn việc kế (chạy tới max) · máy sắp bảo trì · tải máy/tổ cao có mức · máy chưa tốc độ /
        chưa quy đổi lúc còn nháp.
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
                # CỐ Ý khác `trung_may` ở nền soi: bước sau của chính lệnh này không phải "việc
                # kế phải giữ chỗ" (xem `ctx.khoang_may_lenh_khac`).
                C.lan_viec_ke(finish, finish_max,
                              self.ctx.khoang_may_lenh_khac(may_id, exclude_id, dong)),
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
            mo_ta, goi_y = chan_doan.chi_tiet(self, dong, canh_bao)
            if start is not None and canh_bao in _MA_CHAN:
                vd.append(C.issue(_MA_CHAN[canh_bao], C.MUC_CHAN_DAT_LICH, mo_ta,
                                  nguon="buoc", goi_y=goi_y))
            else:
                vd.append(C.issue(canh_bao, C.MUC_CANH_BAO, mo_ta, nguon="buoc", goi_y=goi_y))
        return vd

    def _vuot_quan_so(self, dong, department_id, start, finish, exclude_id) -> list[dict]:
        """Đỉnh quân số tổ: vượt hẳn ⇒ CẢNH BÁO (`vuot_quan_so_to`); sắp kịch ⇒ CẢNH BÁO có mức
        (`tai_to_cao`). Đo cùng một đỉnh nên hai cửa không lệch nhau.

        Cả hai đều chỉ CẢNH BÁO (21/08/2026) — quân số không còn chặn đặt lịch lẫn phát hành."""
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

    # ================= THỜI LƯỢNG v2 =================
    def _op_cua_dong(self, dong):
        """Bước routing GỐC của dòng (để đọc trường không snapshot trên dòng lịch)."""
        if getattr(dong, "nguon", None) == NGUON_LSX:
            return self.core._lcd(getattr(dong, "lsx_cong_doan_id", None))
        bgcd_id = getattr(dong, "bai_ghep_cong_doan_id", None)
        return self.db.get(BaiGhepCongDoan, bgcd_id) if bgcd_id else None

    def _thoi_luong_v2(self, dong) -> dict:
        """Thời lượng v2 — uỷ hết cho engine cũ.

        THUÊ NGOÀI không còn đường riêng (04/09/2026): nhà thầu là một MÁY khai trong danh mục
        (tên kèm hậu tố "thuê ngoài – …"), nên bước chạy đúng bộ máy tốc-độ/kíp như bước máy nhà.
        """
        return self.core._thoi_luong(dong)

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

    def _nhan_buoc(self, r, nhan: "_NhanMaps") -> str:
        """Nhãn NGƯỜI ĐỌC của một bước: `B3 · Cán màng bóng` — đúng số bàn/panel đang hiện (B = thứ
        tự + 1). Không có tên công đoạn thì còn mỗi số bước, vẫn hơn nhãn chung "Công đoạn"."""
        ten = nhan.ten_cd(r)
        so = f"B{int(r.source_thu_tu or 0) + 1}"
        return f"{so} · {ten}" if ten else so

    def _chu_buoc(self, r) -> str | None:
        """AI đang nhận bước — nhà thầu ngoài / máy / tổ, gọi bằng TÊN THẬT. None = còn vô chủ.

        Dòng theo máy trong dữ liệu thật thường mang KÈM `department_id` (tổ vận hành máy), nên thứ
        tự ưu tiên là thầu ngoài → máy → tổ, khớp thứ tự engine đọc tài nguyên."""
        if (ncc := (getattr(r, "nha_cung_cap", None) or "").strip()):
            return f"nhà thầu ngoài {ncc}"
        if r.may_id:
            ten = self._ten_may(r.may_id)
            return _goi_ten(ten, "máy") if ten else "máy đã chọn"
        if r.department_id:
            ten = self._ten_to(r.department_id)
            return _goi_ten(ten, "tổ") if ten else "tổ đã chọn"
        return None

    def _ly_do_chua_tinh_duoc(self, r) -> tuple[str, str] | None:
        """`(mô tả, gợi ý)` vì sao engine CHƯA tính nổi thời lượng của MỘT dòng đã lưu, hay None khi
        tính được bình thường. Câu do `chan_doan` dựng nên nó gọi tên đúng thứ đang thiếu."""
        ma = (self._thoi_luong_v2(r) or {}).get("canh_bao")
        return chan_doan.chi_tiet(self, r, ma) if ma else None

    def _van_de_chua_xep(self, r, nhan: "_NhanMaps") -> dict:
        """Vấn đề CHẶN PHÁT HÀNH của MỘT bước chưa xếp xong — gọi ĐÍCH DANH bước nào, thiếu THỨ GÌ.

        Trước 21/08/2026 mọi bước dùng chung một câu "Còn công đoạn chưa gán đủ máy/tổ và giờ bắt
        đầu": lệnh 6 bước đẻ 6 thẻ y hệt nhau, và bước ĐÃ có máy vẫn bị nói là thiếu máy (LSX26-0020:
        cả 6 dòng có `may_id`/`department_id`, chỉ thiếu `start_at`). Nay tách đúng ba tình huống —
        thiếu giờ · thiếu chủ · thiếu cả hai — và ghép thêm lý do engine chưa tính nổi thời lượng khi
        có, vì đó mới là thứ chặn Tự xếp.
        """
        chu = self._chu_buoc(r)
        gio = _naive(r.start_at)
        if chu and gio is None:
            mo_ta = f"Đã giao cho {chu} nhưng CHƯA có giờ bắt đầu."
            goi_y = "Bấm Tự xếp cho bước này, hoặc kéo thanh vào bàn để chốt giờ bắt đầu."
        elif chu is None and gio is not None:
            mo_ta = f"Đã có giờ bắt đầu {gio:%H:%M %d/%m} nhưng CHƯA chọn ai chạy bước."
            goi_y = "Chọn máy, tổ hoặc nhà thầu ngoài cho bước này."
        else:
            mo_ta = "CHƯA chọn máy/tổ, cũng CHƯA có giờ bắt đầu."
            goi_y = "Bấm Tự xếp cho bước này, hoặc chọn máy/tổ rồi kéo vào bàn."
        if (ly_do := self._ly_do_chua_tinh_duoc(r)):
            mo_ta += f" {ly_do[0]}"
            goi_y = ly_do[1] or goi_y
        return C.issue("con_buoc_chua_xep", C.MUC_CHAN_PHAT_HANH, mo_ta, nguon="buoc",
                       goi_y=goi_y, doi_tuong=self._nhan_buoc(r, nhan))

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
                i["doi_tuong"] = _goi_ten(ten, "Máy") if ten else "Máy"
            elif ng == "to":
                ten = self._ten_to(department_id)
                i["doi_tuong"] = _goi_ten(ten, "Tổ") if ten else "Tổ"
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
                ten = nhan.ten_cd(r)
                anh_huong.append({
                    "dong_id": r.id, "thu_tu": int(r.source_thu_tu or 0),
                    "cong_doan_ten": ten, "start_at": _naive(rs), "finish_at": _naive(rf),
                })
        anh_huong.sort(key=lambda x: (x["thu_tu"], x["dong_id"]))
        return anh_huong, max(fins), han_sx, han_giao

    def xem_truoc(self, *, dong_id: int, patch: dict) -> dict:
        dong = self.core._get_dong(dong_id)
        t = self._tinh(dong, patch)
        # Nhân lực của bước đi kèm xem-trước. Hộp xác nhận vốn chỉ in NGUYÊN VĂN câu vấn đề
        # ("Đỉnh 5 người cùng lúc vượt quân số 3 của tổ") — người xếp đọc xong không biết số 5 ở
        # đâu ra và định biên của bước là bao nhiêu, phải mở màn Lệnh sản xuất mới tra được.
        # Trả kèm số bố trí + ba mốc để hộp thoại tự nói hết.
        op = self._op_cua_dong(dong)
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
            "so_nhan_cong": int(getattr(op, "so_nhan_cong", 1) or 1) if op is not None else None,
            "dinh_bien": self._dinh_bien(op),
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

    # ================= TÁCH / GỘP LẦN CHẠY =================
    def _viet_lai_finish(self, dong: XepLichCongDoan) -> None:
        """Viết lại `finish_at` theo số lượng HIỆN TẠI của dòng.

        `finish_at` là cột PERSIST và là nguồn duy nhất cho bộ dò `trung_may`. Tách/gộp đổi số
        lượng ⇒ đổi thời lượng, để nguyên giờ kết thúc cũ là đọc sai khoảng máy theo cả hai chiều:
        tách xong thanh vẫn dài như trọn bước (khoá máy DƯ ~40%), gộp lại thì thanh ngắn hơn việc
        thật nên `trung_may` không la trong khi ngoài xưởng hai lệnh chồng nhau — hướng nguy hiểm.

        Đi đúng đường `luu` đang ghi (`finish_lien_tuc`, §3.3) chứ không đường cộng-theo-ca của
        engine cũ: cùng một dòng trên cùng một bàn không được có hai kiểu giờ kết thúc.
        """
        start = C.tron_phut(_aware(dong.start_at))
        if start is None:
            dong.finish_at = None
            return
        chiem = int(self._thoi_luong_v2(self._shadow(dong, {})).get("chiem_may_phut") or 0)
        dong.finish_at = C.finish_lien_tuc(start, chiem) if chiem > 0 else None

    def tach_dong(self, *, dong_id: int, cac_phan: list[float], actor) -> list[dict]:
        """Tách một công đoạn thành nhiều LẦN CHẠY, trả view của CẢ CỤM (spec §2.4).

        Trả cả cụm chứ không chỉ dòng vừa bấm: tách đẻ thêm thanh trên bàn, FE cần đủ cụm để vẽ
        lại một lượt thay vì đoán rồi đi tải lại workspace.
        """
        from .phan_doan import tach

        cum = tach(self.db, dong_id=dong_id, cac_phan=cac_phan, actor=actor)
        for d in cum:
            self._viet_lai_finish(d)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_2_tach_dong",
            target=f"xep_lich:{dong_id}",
            detail="Tách lần chạy: " + "; ".join(
                f"{d.phan_doan_so}/{d.phan_doan_tong}={float(d.so_luong or 0):g}" for d in cum),
        )
        self.repo.commit()
        nhan = self._nap_nhan(cum)
        return [self._dong_view(d, nhan) for d in cum]

    def gop_dong(self, *, dong_id: int, actor) -> dict:
        """Gộp cả cụm phân đoạn về lại MỘT dòng (giữ id gốc) — trả view của dòng còn lại."""
        from .phan_doan import gop

        goc = gop(self.db, dong_id=dong_id)
        self._viet_lai_finish(goc)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xep_lich_2_gop_dong",
            target=f"xep_lich:{goc.id}", detail=f"Gộp lần chạy về một dòng {goc.id}",
        )
        self.repo.commit()
        return self.dong_view(goc)

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
        nhan = self._nap_nhan(rows)
        for r in rows:
            co_tai_nguyen = bool(r.may_id or r.department_id or (r.nha_cung_cap or "").strip())
            if r.start_at is None or not co_tai_nguyen:
                vd.append(self._van_de_chua_xep(r, nhan))
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

    #: MỨC chặn phát hành — MỘT CỬA DUY NHẤT (25/08/2026). Trước đây v2 chỉ siết ba mã rồi để
    #: service màn cũ chặn tiếp bằng 12 detector đời cũ: dải chân báo "đủ điều kiện phát hành" (đọc
    #: `kiem_phat_hanh`) trong khi nút Phát hành trả "còn N xung đột CHẶN" (đọc detector cũ) — hai
    #: người gác, hai danh sách, người dùng không biết phải gỡ cái gì (LSX26-0029). Nay CHỈ
    #: `kiem_phat_hanh` quyết, đúng bằng danh sách UI đang bày; phát hành từ màn cũ giữ gác cũ.
    _MUC_CHAN = (C.MUC_CHAN_PHAT_HANH, C.MUC_CHAN_DAT_LICH)

    def _chan_phat_hanh(self, *, nguon: str, id: int) -> list[dict]:
        """Vấn đề đang CHẶN phát hành của một lệnh/bài — rỗng nghĩa là phát hành được.

        Cùng NGUỒN với dải chân UI (`kiem_phat_hanh`) nên nút bấm và cái đèn không bao giờ nói khác
        nhau; FE cũng gate đúng hai mức này. `chan_dat_lich` chặn luôn: một bước còn đè khoá máy hay
        trùng máy mà thả xuống xưởng thì thợ nhận một lịch không chạy được. `tre_han_sx` đã duyệt
        ngoại lệ được `kiem_phat_hanh` hạ xuống cảnh báo nên tự lọt qua đây."""
        return [i for i in self.kiem_phat_hanh(nguon=nguon, id=id) if i["muc"] in self._MUC_CHAN]

    def phat_hanh(self, *, nguon: str, id: int, actor):
        """Phát hành: v2 gác TOÀN BỘ, service màn cũ chỉ còn lo đổi trạng thái + snapshot + audit.

        Cửa gồm: vật tư chưa giữ đủ · thiếu cả hai hạn · còn bước chưa xếp giờ · trễ hạn SX chưa
        duyệt ngoại lệ (§7.2) · mọi luật CHẶN ĐẶT LỊCH còn vướng trên từng dòng (trùng máy · sai
        tiền nhiệm · ngoài ca · chưa có chủ · trước ngày vật tư · thiếu thời lượng/quy đổi/lead thuê
        ngoài). Gác đời cũ tắt bằng `bo_qua_xung_dot` — xem `XepLichVanDeService._chan_xung_dot`."""
        chan = self._chan_phat_hanh(nguon=nguon, id=id)
        if chan:
            raise XepLich2Blocked(chan)
        from ..xep_lich_van_de_service import XepLichVanDeService

        svc = XepLichVanDeService(self.db, self.audit)
        if nguon == NGUON_LSX:
            return svc.phat_hanh_lsx(lsx_id=id, actor=actor, bo_qua_xung_dot=True)
        return svc.phat_hanh_bai_ghep(bai_ghep_id=id, actor=actor, bo_qua_xung_dot=True)

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

        Siết ĐÚNG MỘT CỬA với phát hành lần đầu (`_chan_phat_hanh`) — lịch cập nhật phải còn hợp lệ
        mới cho đóng băng lại. Uỷ nghiệp vụ cho service san_xuat; đổi ValueError của nó sang lỗi v2
        để router ánh xạ đúng HTTP."""
        chan = self._chan_phat_hanh(nguon=nguon, id=id)
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
        tags_lsx = self.repo.customer_tags_for_lsx(lsx_by_id.keys())
        tags_bg = self.repo.customer_tags_for_bai_ghep(bg_by_id.keys())
        ten_kh_lsx = self.repo.customer_ten_for_lsx(lsx_by_id.keys())
        ten_kh_bg = self.repo.customer_ten_for_bai_ghep(bg_by_id.keys())
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
                    "ten_san_pham": lsx.ten,
                    "so_luong_dat": lsx.so_luong_dat,
                    "don_vi_tinh": lsx.don_vi_tinh,
                    "is_rush": bool(getattr(lsx, "is_rush", False)),
                    "han": self.core._han(lsx),
                    "han_giao": lsx.han_giao_khach,
                    "so_cong_doan_chua_xep": int(so_cd_lsx.get(id, 0)),
                    "ten_khach_hang": ten_kh_lsx.get(id),
                    "nhan_khach_hang": tags_lsx.get(id, []),
                    "van_de": vd,
                }
            else:
                bg = bg_by_id.get(id)
                if bg is None:
                    continue
                vd = release.van_de_vat_tu(self.db, bai_ghep_id=id)
                row = {
                    "nguon": NGUON_IN_GHEP, "id": id, "ma": bg.ma,
                    "ten_san_pham": bg.ten or "Bài in ghép",
                    "so_luong_dat": None,
                    "don_vi_tinh": None,
                    "is_rush": bool(getattr(bg, "is_rush", False)),
                    "han": bg.han_hoan_thanh_sx,
                    "han_giao": None,
                    "so_cong_doan_chua_xep": int(so_cd_bg.get(id, 0)),
                    "ten_khach_hang": ten_kh_bg.get(id),
                    "nhan_khach_hang": tags_bg.get(id, []),
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
        if t["theo_may"]:
            nguon_tl = "may"
        else:
            nguon_tl = "tay"
        cong_doan_ten = nhan.ten_cd(r)
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

    def _dong_view(self, r: XepLichCongDoan, nhan: "_NhanMaps", tt: dict[int, dict] | None = None) -> dict:
        # Nhãn dẫn xuất: dòng chỉ neo id nên tra mã lệnh + tên sản phẩm + tên công đoạn từ các map
        # đã nạp theo lô (không join trong vòng lặp). LSX ăn nhánh lsx_*, bài ghép ăn nhánh bg_*.
        if r.nguon == NGUON_LSX:
            lsx = nhan.lsx.get(r.lsx_id)
            lsx_ma = lsx.ma if lsx else None
            bai_ghep_ma = None
            ten_san_pham = lsx.ten if lsx else None
        else:
            bg = nhan.bai_ghep.get(r.bai_ghep_id)
            lsx_ma = None
            bai_ghep_ma = bg.ma if bg else None
            ten_san_pham = bg.ten if bg else None
        cong_doan_ten = nhan.ten_cd(r)
        return {
            "id": r.id, "nguon": r.nguon, "lsx_id": r.lsx_id, "bai_ghep_id": r.bai_ghep_id,
            "may_id": r.may_id, "department_id": r.department_id,
            # NCC + loại bước để bàn gom lane THUÊ NGOÀI theo từng nhà cung cấp (không còn một khay
            # "chưa rõ NCC" gộp mọi thứ). Cả hai đã nằm sẵn trên dòng, khỏi join thêm.
            "nha_cung_cap": (r.nha_cung_cap or None),
            "loai_buoc": r.loai_buoc,
            # Khuôn/khung của bước: thanh Gantt tự nói "cần dao mà chưa chốt" / "dao đang đặt làm"
            # mà không phải mở lệnh ra tra. Ngày dự kiến KHÔNG chặn kéo thả (chốt 04/09/2026).
            **nhan.khuon_cua(r),
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
            # Chiều LẦN CHẠY: thanh phải tự nói "2/3" và phần việc của nó, không thì người xếp
            # nhìn ba thanh giống hệt nhau mà không biết cái nào làm bao nhiêu.
            # `so_luong` NULL = trọn bước (dòng chưa tách) — KHÁC hẳn 0.
            "so_luong": float(r.so_luong) if r.so_luong is not None else None,
            "phan_doan_so": int(r.phan_doan_so or 1),
            "phan_doan_tong": int(r.phan_doan_tong or 1),
            # SL VÀO của cả bước — cái mà `phan_doan.tach` đem đi chia khi dòng chưa mang `so_luong`
            # (gần như luôn thế). Không phơi thì màn không có cách nào biết bấm Tách có ra gì không:
            # `so_luong` NULL đọc như "chưa biết số" trong khi bước vẫn khai đủ. 0 = bước thật sự
            # chưa khai số lượng ⇒ tách sẽ bị chặn, nút phải xám từ đầu.
            "so_luong_buoc": nhan.sl_vao_cd(r),
            # "Râu" giải thích độ dài thanh: chỉ tính cho dòng ĐÃ có giờ (thanh nằm trên trục thời
            # gian). Nháp chưa-giờ nằm ở cụm "Chưa đặt giờ", không có thanh để bóc tách → None.
            "boc_tach": self._boc_tach(r) if r.start_at is not None else None,
            # Mức NẶNG NHẤT của thanh tại chỗ đang đặt (chan_dat_lich | canh_bao | None) — dùng
            # chung detector `_van_de_dat_lich` với panel/xem-trước nên dải chân bàn khớp từng thanh.
            # Chỉ tính cho dòng đã có giờ (nháp chưa-giờ không có thanh để đếm mức).
            "muc": _muc_worst(self._tinh(r, {})["van_de"]) if r.start_at is not None else None,
            # Lớp THỰC TẾ — CHỈ ĐỌC, không bao giờ dời thanh (spec-thuc-te-vs-ke-hoach §2.1).
            # None = chưa phát hành / phát hành phiên bản khác ⇒ FE vẽ thanh trơn như trước.
            "thuc_te": (tt or {}).get(r.id),
        }

    def dong_view(self, r: XepLichCongDoan) -> dict:
        """View MỘT dòng (router `PUT /dong` trả về sau khi lưu) — tự nạp map nhãn cho đúng dòng đó."""
        return self._dong_view(r, self._nap_nhan([r]))

    def _nap_nhan(self, rows: list[XepLichCongDoan]) -> "_NhanMaps":
        """Nạp theo LÔ mã lệnh / mã bài ghép / tên công đoạn cho MỌI dòng trong một lượt (tránh N+1)."""
        return _NhanMaps(
            lsx=self.repo.lsx_map(r.lsx_id for r in rows),
            bai_ghep=self.repo.bai_ghep_map(r.bai_ghep_id for r in rows),
            lsx_cd=self.repo.lsx_cong_doan_nhan_map(r.lsx_cong_doan_id for r in rows),
            bg_cd=self.repo.bai_ghep_cong_doan_nhan_map(r.bai_ghep_cong_doan_id for r in rows),
            khuon=self.repo.khuon_buoc_map(r.lsx_cong_doan_id for r in rows),
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
        # Nạp GỘP một lượt cho cả bàn — cùng lý do `_nap_nhan` tồn tại: bàn vài trăm thanh.
        tt = nap_thuc_te(self.db, da_xep + nhap)
        dong = [self._dong_view(r, nhan, tt) for r in da_xep]
        dong += [self._dong_view(r, nhan, tt) for r in nhap]
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
            "ca_nhan": self._ca_nhan(),
            "ngay_le": self.ctx.ngay_le(tu, den),
            "khoa_may": self._khoa_may_trong_cua_so({r.may_id for r in co_gio if r.may_id}, tu, den),
            "tai_may": overlay.tai_may(pl_may, tu, den),
            "tai_to": tai_to,
            "dong": dong,
        }

    def _ca_nhan(self) -> list[dict]:
        """Ca nền KÈM TÊN, để Gantt gọi được "Ca 2" chứ không chỉ tô một dải xám vô danh.

        `ca_windows()` cố ý chỉ trả bộ ba số (nó là cửa của ENGINE, tên ca không tham gia luật nào).
        Nhưng màn thì cần tên: xưởng khai 4 ca chồng nhau phủ gần trọn 24h, không có tên thì người
        xem chỉ thấy một mảng liền và không biết mình đang xếp vào ca nào (§7.1 chỉ soi GIỜ BẮT ĐẦU).
        Chưa khai ca nào → trả đúng một dải fallback, nói thẳng là mặc định chứ đừng giả vờ có ca.
        """
        cas = self.core._ca_lich_may()
        if not cas:
            b = C.GIO_BAT_DAU * 60
            return [{"id": None, "ten": "Giờ mặc định (chưa khai ca)", "bat_dau_phut": b,
                     "ket_thuc_phut": b + C.PHUT_LAM_NGAY, "qua_dem": False}]
        return [{
            "id": int(s.id), "ten": s.name,
            "bat_dau_phut": int(s.start_minute), "ket_thuc_phut": int(s.end_minute),
            "qua_dem": bool(s.is_overnight) or int(s.end_minute) <= int(s.start_minute),
        } for s in cas]

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

    # ================= TỰ XẾP CẢ CHUỖI =================
    def tu_xep(self, *, nguon: str, id: int, actor, ghi_de: bool = False,
               chan_ngay: int = auto.CHAN_NGAY_MAC_DINH) -> dict:
        """Tự xếp toàn bộ bước chưa có giờ của một lệnh/bài (§6) — thuật toán ở `auto`.

        `ghi_de=True` thì xếp lại CẢ những bước đã có giờ (trừ bước đang khoá). Mọi cách đặt đều đi
        qua `_van_de_dat_lich` nên không đẻ ra được lịch mà bấm tay sẽ bị chặn."""
        return auto.tu_xep(self, nguon=nguon, id=id, actor=actor, ghi_de=ghi_de,
                           chan_ngay=chan_ngay)
