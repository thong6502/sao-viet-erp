"""GIỮ CHỖ vật tư — bật · tắt · tự nhặt thêm · tồn tự do. Chủ dự án chốt 17/08/2026.

Một câu: **lệnh phải giữ được vật tư thì mới được xếp lịch.**

Trước đó bảng cân đối chỉ đọc, tồn không thuộc về ai. Lệnh A xếp lịch 22/8 dựa trên 60 kg giấy
đang có; chiều hôm sau lệnh B lĩnh mất 50 kg; lịch của A thành lịch ma mà không ai báo.

## Nguồn NHU CẦU: tái dùng, KHÔNG tính lại

Mọi con số "chủ thể này cần bao nhiêu" đọc thẳng từ `KeHoachVatTuService.can_doi()` — cùng một
engine quy đổi, cùng luật chủ thể (lệnh đã ghép thì bài đại diện), cùng thứ tự con trỏ theo ngày
cần. Viết đường tính nhu cầu thứ hai ở đây là đẻ ra hai con số sẽ lệch nhau, và lúc lệch thì không
biết tin bên nào.

Cụ thể lấy `con_phai_co` (= nhu cầu − đã cấp) chứ không lấy `nhu_cau`: phần kho đã xuất rồi thì
không cần giữ chỗ nữa, nó đã nằm ở xưởng.

## Bật = ĐĂNG KÝ, không phải chụp một lần

Giữ được bao nhiêu hay bấy nhiêu; công tắc vẫn BẬT dù chưa đủ. Hàng về sau thì `nhat_them()` tự bù
— không bắt người dùng nhớ quay lại bấm đúng lúc hàng nhập kho, vì chẳng ai nhớ.

**Mở khoá xếp lịch chỉ khi giữ ĐỦ 100%** (`du_chua`).

## Ai nhặt trước

Theo **NGÀY CẦN**, không theo ai bật trước, cũng không theo ai đề nghị mua. `can_doi()` đã sắp dòng
theo ngày cần sẵn nên chỉ việc duyệt theo đúng thứ tự nó trả về — một luật, không đẻ luật thứ hai
cho hàng đang về.

## Ba thứ CỐ Ý KHÔNG làm

* **Không giữ đích danh lô** — phá nhập-trước-xuất-trước của kho. Chỉ giữ cặp (mặt hàng, số lượng).
* **Không tự hết hạn** — thứ chạy ngầm mà nhả nhầm đúng hôm gấp thì không ai truy ra được. Thay
  bằng danh sách "giữ lâu chưa chạy" để người nhìn rồi tự quyết.
* **Không xử lý ưu tiên hộ** — lệnh gấp tranh chỗ với lệnh đang giữ thì máy chỉ BÀY cờ gấp, người
  lập kế hoạch tự vào nhả. Chọn hy sinh lệnh nào là quyết định kinh doanh, máy không có dữ kiện.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep
from ..models.lsx import Lsx
from ..models.vat_tu_giu_cho import NGUON_DANG_VE, NGUON_KHO, VatTuGiuCho
from ..repositories.giu_cho_repo import GiuChoRepository

Hang = tuple[str, int]

#: Giữ quá ngần này ngày mà chưa đưa vào kế hoạch ⇒ vào danh sách "giữ lâu chưa chạy".
#:
#: Đây là NGƯỠNG NHÌN, không phải hạn tự nhả (xem luật ③ ở docstring model): quá ngưỡng thì chỗ giữ
#: vẫn nguyên, chỉ nổi lên cho người lập kế hoạch thấy rồi tự quyết. Một tuần vì kế hoạch xưởng in
#: chạy theo tuần — ngắn hơn thì mọi lệnh vừa bật đều kêu, dài hơn thì giấy nằm chết cả nửa tháng
#: mới có ai biết.
NGUONG_GIU_LAU_NGAY = 7

#: Nặng → nhẹ. Một chủ thể cần một mặt hàng ở NHIỀU bước; thẻ tóm tắt chỉ hiện được MỘT màu, và
#: màu đó phải là màu tệ nhất. Lấy màu của bước đầu (hoặc bước cuối) là giấu đúng thứ phải lo.
_NANG = {"khong_ro": 5, "do": 4, "ve_muon": 3, "vang": 2, "xanh": 1, "xam": 0}


class GiuChoError(Exception):
    pass


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _aware(dt: datetime) -> datetime:
    """Dán UTC lên giờ đọc từ DB trước khi đem trừ.

    SQLite trả datetime NAIVE dù cột khai `timezone=True`, còn `datetime.now(timezone.utc)` thì
    aware — trừ thẳng hai cái là `TypeError`, và nó nổ ở giữa vòng lặp nên chỉ hiện thành 500 trắng
    trơn. Đúng cái bẫy đã dính ở `xep_lich_service` (25/07/2026); dán nhãn ngay tại biên đọc.
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class GiuChoService:
    """Nhận sẵn `KeHoachVatTuService` từ nơi gọi — KHÔNG tự dựng, để test bơm bản giả được."""

    def __init__(self, db: Session, kh_vt, repo: GiuChoRepository | None = None) -> None:
        self.db = db
        self.kh = kh_vt
        self.repo = repo or GiuChoRepository(db)

    # ================== ĐỌC ==================

    def ton_tu_do(self, hangs: list[Hang]) -> dict[Hang, float]:
        """`tồn thật − Σ đang giữ` — con số DUY NHẤT kho được phép cho người khác lĩnh.

        Kẹp sàn 0: giữ nhiều hơn tồn là chuyện có thật (giữ hứa bám lô đang về, hàng chưa nhập),
        nhưng "tồn tự do âm" thì không có nghĩa gì với người đi lĩnh.
        """
        if not hangs:
            return {}
        ton = self.kh.lots.on_hand_map(hangs)
        giu = self.repo.da_giu_map(hangs)
        return {h: max(0.0, _f(ton.get(h)) - _f(giu.get(h))) for h in hangs}

    def _nhu_cau_theo_chu_the(self, bang: dict) -> dict[tuple, dict]:
        """`{(lsx_id, bai_ghep_id): {hang: {"can": float, "khong_ro": bool}}}` từ bảng cân đối.

        Gộp mọi BƯỚC của cùng chủ thể + cùng mặt hàng: giữ chỗ hỏi "lệnh này chạy được chưa", mà
        lệnh chỉ chạy được khi đủ cho CẢ chuỗi — một lệnh ăn màng ở hai công đoạn thì phải giữ tổng
        của hai bước.

        `khong_ro` = dòng KHÔNG quy đổi được đơn vị. `nhu_cau` của nó là 0 vì máy chưa tính nổi,
        KHÔNG phải vì không cần — nên không giữ được gì, và chủ thể đó KHÔNG bao giờ được tính là
        "đủ". Coi nó là 0 rồi mở khoá xếp lịch là mở cho một lệnh chưa ai biết cần bao nhiêu.
        """
        ra: dict[tuple, dict] = {}
        for nhom in bang.get("items", []):
            if nhom.get("loai_nhom") != "vat_tu":
                continue
            hang = (nhom["hang_loai"], nhom["hang_id"])
            for d in nhom.get("dong", []):
                khoa = (d.get("lsx_id"), d.get("bai_ghep_id"))
                if khoa == (None, None):
                    continue
                o = ra.setdefault(khoa, {}).setdefault(hang, {"can": 0.0, "khong_ro": False})
                o["can"] += _f(d.get("con_phai_co"))
                if d.get("trang_thai") == "khong_ro":
                    o["khong_ro"] = True
        return ra

    def trang_thai(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None,
                   bang: dict | None = None) -> dict:
        """Kết quả sau khi bấm — ba trạng thái người dùng thấy.

        `du` = giữ đủ 100% ⇒ xếp lịch mở khoá. `xep_som_nhat` = ngày sớm nhất được xếp bước tiêu
        thụ: `None` khi mọi phần đều giữ CHẮC (hàng trong kho ⇒ ngày tháng vô nghĩa), là ngày về
        MUỘN NHẤT trong các phần giữ HỨA khi có — phải chờ đủ MỌI món mới chạy được, không phải
        món đầu tiên.

        `bang` = bảng cân đối DÙNG LẠI. Nơi gọi nào cũng hỏi nhiều chủ thể một lượt (`nhat_them`,
        `theo_chu_the`), mà `can_doi()` chạy cả engine quy đổi + con trỏ tồn cho TOÀN BỘ kế hoạch —
        để mặc mỗi chủ thể tự gọi là bình phương số lần chạy theo số lệnh. Bảng KHÔNG phụ thuộc vào
        bảng giữ chỗ (nó đọc tồn thật, không đọc tồn tự do) nên dùng lại là số y hệt, không phải
        bản chụp cũ.
        """
        chu = (lsx_id, bai_ghep_id)
        if bang is None:
            bang = self.kh.can_doi()
        can = self._nhu_cau_theo_chu_the(bang).get(chu, {})
        dang = self.repo.cua_chu_the(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)

        giu_theo_hang: dict[Hang, float] = {}
        for r in dang:
            h = (r.hang_loai, r.hang_id)
            giu_theo_hang[h] = giu_theo_hang.get(h, 0.0) + _f(r.so_luong)

        thieu: dict[Hang, float] = {}
        khong_ro = False
        for h, o in can.items():
            if o["khong_ro"]:
                khong_ro = True
            con = round(o["can"] - giu_theo_hang.get(h, 0.0), 4)
            if con > 0:
                thieu[h] = con

        ngay_ve = [r.ngay_ve for r in dang if r.nguon == NGUON_DANG_VE and r.ngay_ve]
        return {
            "bat": self._co_bat(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id),
            "du": not thieu and not khong_ro and bool(can),
            "khong_ro": khong_ro,
            "thieu": thieu,
            "dang_giu": giu_theo_hang,
            "xep_som_nhat": max(ngay_ve) if ngay_ve else None,
            # Dòng giữ chỗ CŨ NHẤT — mốc đếm "giữ bao lâu rồi". Lấy min chứ không lấy max: nhặt
            # thêm khi hàng về đẻ dòng mới, lấy max là mỗi lần bù hàng lại reset đồng hồ về 0 và
            # chỗ giữ lâu nhất thì không bao giờ nổi lên danh sách.
            "giu_tu": min((r.created_at for r in dang), default=None),
        }

    def du_chua(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> bool:
        return bool(self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)["du"])

    # ================== CÁCH NHÌN THỨ HAI: THEO LỆNH ==================

    def theo_chu_the(self, *, q: str | None = None, chi_can_lo: bool = False,
                     chi_giu_lau: bool = False) -> dict:
        """Cùng một bảng cân đối, XOAY 90°: mỗi thẻ = MỘT lệnh/bài, bên trong là các mặt hàng nó cần.

        Vì sao phải có cách nhìn thứ hai chứ không thêm cột vào bảng cũ: hai câu hỏi khác nhau và
        không câu nào trả lời hộ câu kia.
          · Gom theo MẶT HÀNG trả lời *"còn thiếu gì, mua bao nhiêu"* — gộp mọi lệnh vào một đơn mua.
          · Gom theo LỆNH trả lời *"lệnh này chạy được chưa"* — mà giữ chỗ và cửa xếp lịch đều
            phán theo CHỦ THỂ. Muốn biết một lệnh đủ chưa trên bảng cũ thì phải mở hết mọi mặt hàng
            rồi tự dò xem lệnh đó có mặt ở đâu.

        ⚠️ `q` KHÔNG truyền xuống `can_doi()`. Ở đó `q` lọc theo MẶT HÀNG, mà lọc mặt hàng rồi gom
        theo lệnh là cắt mất chính món đang thiếu của lệnh — thẻ sẽ hiện "đủ" cho một lệnh còn
        thiếu giấy. Lấy bảng đầy đủ rồi lọc theo CHỦ THỂ ở đây.
        """
        bang = self.kh.can_doi()
        gom = self._gom_theo_chu_the(bang)

        da_xep_lsx, da_xep_bai = self.repo.chu_the_da_xep_lich()
        gio = datetime.now(timezone.utc)

        self._them_mo_coi(gom)
        dang_thieu = self._chu_the_dang_thieu(gom)

        rows: list[dict] = []
        for chu, o in gom.items():
            lsx_id, bg_id = chu
            tt = self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bg_id, bang=bang)
            hangs = list(o["hang"].values())
            for h in hangs:
                k = (h["hang_loai"], h["hang_id"])
                h["dang_giu"] = round(_f(tt["dang_giu"].get(k)), 4)
                h["can"] = round(h["can"], 4)
                h["thieu"] = round(h["thieu"], 4)
                h["so_lenh_khac_thieu"] = len(dang_thieu.get(k, frozenset()) - {chu})

            da_xep = (lsx_id in da_xep_lsx) if lsx_id is not None else (bg_id in da_xep_bai)
            giu_tu = tt["giu_tu"]
            so_ngay_giu = (gio - _aware(giu_tu)).days if giu_tu else None
            rows.append({
                "lsx_id": lsx_id,
                "bai_ghep_id": bg_id,
                "ma": o["ma"],
                "is_rush": bool(o["is_rush"]),
                "ngay_can": o["ngay_can"],
                "moc_tam": bool(o["moc_tam"]),
                "ngoai_pham_vi": bool(o.get("ngoai_pham_vi")),
                "bat": tt["bat"],
                "du": tt["du"],
                "khong_ro": tt["khong_ro"],
                "xep_som_nhat": tt["xep_som_nhat"],
                "da_xep_lich": da_xep,
                "giu_tu": giu_tu,
                "so_ngay_giu": so_ngay_giu,
                # Đã bật, đã giữ lâu, mà chưa hề đưa vào kế hoạch ⇒ chỗ giữ đang nằm không. Cố ý
                # KHÔNG tự nhả (luật ③): thứ chạy ngầm nhả nhầm đúng hôm gấp thì không ai truy ra.
                "giu_lau_chua_chay": bool(
                    tt["bat"] and not da_xep and so_ngay_giu is not None
                    and so_ngay_giu >= NGUONG_GIU_LAU_NGAY
                ),
                "so_mat_hang": len(hangs),
                "so_thieu": sum(1 for h in hangs if h["trang_thai"] == "do"),
                "so_ve_muon": sum(1 for h in hangs if h["trang_thai"] == "ve_muon"),
                "so_khong_ro": sum(1 for h in hangs if h["trang_thai"] == "khong_ro"),
                "hang": sorted(hangs, key=lambda h: (-_NANG.get(h["trang_thai"], 0),
                                                     h["hang_ma"] or "")),
            })

        return {"items": self._loc_chu_the(rows, q=q, chi_can_lo=chi_can_lo,
                                           chi_giu_lau=chi_giu_lau),
                "so_giu_lau": sum(1 for r in rows if r["giu_lau_chua_chay"])}

    @staticmethod
    def _chu_the_dang_thieu(gom: dict[tuple, dict]) -> dict[Hang, frozenset]:
        """`{mặt hàng: {chủ thể đang thiếu nó}}` — để hộp xác nhận nhả chỗ nói được *"nhả ra thì
        ai đỡ"*.

        ⚠️ Tính trên `gom` ĐẦY ĐỦ, TRƯỚC khi lọc. Đếm sau bộ lọc thì màn đang lọc "chỉ lệnh giữ
        lâu" sẽ báo *"0 lệnh khác đang thiếu"* trong khi thật ra có ba — và người dùng nhả (hoặc
        không nhả) dựa trên một con số do bộ lọc của chính họ tạo ra.

        Dựa vào `thieu` chứ không vào tồn tự do: `thieu` là phần bảng cân đối nói *"không đủ hàng
        THẬT"*, tức lệnh đó bí thật. Lệnh chỉ bí vì bị người khác giữ mất thì không tính vào đây —
        con số phải nói về hàng, không nói về hàng đợi.
        """
        ra: dict[Hang, set] = {}
        for chu, o in gom.items():
            for hang, h in o["hang"].items():
                if _f(h.get("thieu")) > 0:
                    ra.setdefault(hang, set()).add(chu)
        return {k: frozenset(v) for k, v in ra.items()}

    def _them_mo_coi(self, gom: dict[tuple, dict]) -> None:
        """Chủ thể còn giữ chỗ mà KHÔNG còn trên bảng cân đối (lệnh bị kéo về `nhap`, bài bị phá…).

        Không bày ra thì chỗ giữ đó VÔ HÌNH: vẫn trừ tồn tự do của mọi người mà chẳng màn nào hiện
        để có nút nhả. Và phải kèm cả DANH SÁCH MẶT HÀNG đang giữ — thẻ chỉ nói "lệnh này giữ gì đó"
        thì người dùng không có căn cứ nào để quyết nhả hay không.
        """
        mo_coi: dict[tuple, list] = {}
        for r in self.repo.tat_ca():
            chu = (r.lsx_id, r.bai_ghep_id)
            if chu not in gom:
                mo_coi.setdefault(chu, []).append(r)
        if not mo_coi:
            return
        objs = self.kh.hang.map_theo_cap(
            sorted({(r.hang_loai, r.hang_id) for rs in mo_coi.values() for r in rs}))
        for chu, rs in mo_coi.items():
            hang: dict[Hang, dict] = {}
            for r in rs:
                k = (r.hang_loai, r.hang_id)
                obj = objs.get(k)
                hang.setdefault(k, {
                    "hang_loai": k[0], "hang_id": k[1],
                    "hang_ma": getattr(obj, "ma", None), "hang_ten": getattr(obj, "ten", None),
                    "don_vi_goc": getattr(obj, "don_vi_gia", None),
                    # `can = 0` là ĐÚNG, không phải thiếu dữ liệu: lệnh đã rơi khỏi kế hoạch nên
                    # hệ không còn biết nó cần bao nhiêu. Chỉ `dang_giu` là có thật.
                    "can": 0.0, "thieu": 0.0, "dang_giu": 0.0, "so_buoc": 0,
                    "trang_thai": "xam", "ngay_can": None, "ngay_du_hang": None,
                    # Lệnh đã rơi khỏi kế hoạch thì không hỏi "đang mua gì cho nó" nữa — chỗ giữ
                    # còn lại là việc NHẢ, không phải việc mua.
                    "phieu_ve": None, "phieu_mua": [], "khoa_do": [],
                })
            gom[chu] = {"ma": self._ma_chu_the(chu), "is_rush": False, "ngay_can": None,
                        "moc_tam": False, "ngoai_pham_vi": True, "hang": hang}

    def mot_dong(self, *, lsx_id: int | None = None,
                 bai_ghep_id: int | None = None) -> dict | None:
        """Đúng MỘT thẻ, cùng hình dạng với thẻ trong danh sách — trả về sau khi bật/tắt.

        Trả nguyên thẻ chứ không trả `{ok: true}`: bật giữ chỗ đổi luôn cả phần thiếu, ngày xếp
        sớm nhất và cờ mở khoá xếp lịch. Không trả thì màn phải gọi lại cả danh sách, và trong
        khoảng giữa hai lời gọi người dùng nhìn thấy một thẻ nói dối.
        """
        chu = (lsx_id, bai_ghep_id)
        for r in self.theo_chu_the()["items"]:
            if (r["lsx_id"], r["bai_ghep_id"]) == chu:
                return r
        return None

    @staticmethod
    def _gom_theo_chu_the(bang: dict) -> dict[tuple, dict]:
        """Xoay bảng: `{(lsx_id, bai_ghep_id): {…, "hang": {hang: {…}}}}`.

        `khoa_do` mang ĐÚNG khoá 5 phần của từng dòng đỏ để nút "Đề nghị mua" trên thẻ lệnh đi lại
        cửa `/de-nghi-mua` có sẵn. Không gộp về một khoá cho mỗi mặt hàng: một lệnh ăn cùng món ở
        hai công đoạn là HAI dòng, gộp lại thì yêu cầu mua ra đúng một nửa (đúng lỗi đã sửa 17/08).
        """
        gom: dict[tuple, dict] = {}
        for nhom in bang.get("items", []):
            if nhom.get("loai_nhom") != "vat_tu":
                continue
            hang = (nhom["hang_loai"], nhom["hang_id"])
            for d in nhom.get("dong", []):
                chu = (d.get("lsx_id"), d.get("bai_ghep_id"))
                if chu == (None, None):
                    continue
                o = gom.setdefault(chu, {"ma": d.get("ma") or "", "is_rush": False,
                                         "ngay_can": None, "moc_tam": False, "hang": {}})
                o["is_rush"] = o["is_rush"] or bool(d.get("is_rush"))
                o["moc_tam"] = o["moc_tam"] or bool(d.get("moc_tam"))
                ngay = d.get("ngay_can")
                if ngay and (o["ngay_can"] is None or ngay < o["ngay_can"]):
                    o["ngay_can"] = ngay
                h = o["hang"].setdefault(hang, {
                    "hang_loai": hang[0], "hang_id": hang[1],
                    "hang_ma": nhom.get("hang_ma"), "hang_ten": nhom.get("hang_ten"),
                    "don_vi_goc": nhom.get("don_vi_goc"),
                    "can": 0.0, "thieu": 0.0, "dang_giu": 0.0, "so_buoc": 0,
                    "trang_thai": "xam", "ngay_can": None, "ngay_du_hang": None,
                    "phieu_ve": None,
                    # Vết mua là thuộc tính của MẶT HÀNG — giống hệt nhau ở mọi lệnh cần món đó.
                    # Chép thẳng từ nhóm, không gộp, không cộng dồn.
                    "phieu_mua": list(nhom.get("phieu_mua") or []),
                    "khoa_do": [],
                })
                h["can"] += _f(d.get("con_phai_co"))
                h["thieu"] += _f(d.get("thieu"))
                h["so_buoc"] += 1
                if _NANG.get(d.get("trang_thai"), 0) > _NANG.get(h["trang_thai"], 0):
                    h["trang_thai"] = d.get("trang_thai") or "xam"
                nc = d.get("ngay_can")
                if nc and (h["ngay_can"] is None or nc < h["ngay_can"]):
                    h["ngay_can"] = nc
                # Ngày đủ hàng lấy MUỘN NHẤT trong các bước `ve_muon`: hai bước ăn cùng món, bước
                # sau chờ lô về 01/09 thì món đó chỉ xong ngày 01/09 — lấy ngày sớm là hứa một mốc
                # mà tới nơi vẫn thiếu. Mã phiếu đi theo đúng ngày được chọn, không lấy rời.
                dh = d.get("ngay_du_hang")
                if d.get("trang_thai") == "ve_muon" and dh:
                    if h["ngay_du_hang"] is None or dh > h["ngay_du_hang"]:
                        h["ngay_du_hang"] = dh
                        h["phieu_ve"] = d.get("phieu_ve")
                if d.get("trang_thai") == "do":
                    h["khoa_do"].append({
                        "hang_loai": hang[0], "hang_id": hang[1],
                        "lsx_id": d.get("lsx_id"), "bai_ghep_id": d.get("bai_ghep_id"),
                        "buoc_id": d.get("buoc_id"),
                    })
        return gom

    @staticmethod
    def _loc_chu_the(rows: list[dict], *, q: str | None, chi_can_lo: bool,
                     chi_giu_lau: bool) -> list[dict]:
        """Lọc + sắp. Tìm theo mã lệnh HOẶC tên/mã mặt hàng nó cần — người dùng gõ cả hai kiểu."""
        ra = rows
        if chi_giu_lau:
            ra = [r for r in ra if r["giu_lau_chua_chay"]]
        if chi_can_lo:
            ra = [r for r in ra if r["so_thieu"] or r["so_khong_ro"] or r["so_ve_muon"]
                  or r["giu_lau_chua_chay"] or r["ngoai_pham_vi"]]
        k = (q or "").strip().lower()
        if k:
            ra = [r for r in ra if k in (r["ma"] or "").lower()
                  or any(k in ((h["hang_ma"] or "") + " " + (h["hang_ten"] or "")).lower()
                         for h in r["hang"])]
        # Việc phải lo lên đầu, rồi tới ngày cần sớm nhất. Lệnh chưa có ngày cần xuống cuối chứ
        # KHÔNG lên đầu: chưa có ngày là chưa xếp được, không phải là gấp.
        ra.sort(key=lambda r: (
            0 if (r["so_thieu"] or r["so_khong_ro"] or r["giu_lau_chua_chay"]
                  or r["ngoai_pham_vi"]) else 1,
            r["ngay_can"] or date.max,
            r["ma"] or "",
        ))
        return ra

    def _ma_chu_the(self, chu: tuple) -> str:
        obj = (self.db.get(Lsx, chu[0]) if chu[0] is not None
               else self.db.get(BaiGhep, chu[1]))
        return getattr(obj, "ma", None) or f"#{chu[0] or chu[1]}"

    # ================== GHI ==================

    def bat(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> dict:
        """Bật công tắc rồi nhặt được bao nhiêu hay bấy nhiêu.

        Nhặt TỒN TỰ DO trước, thiếu thì bám lô đang về theo ngày tăng dần — hàng có thật bao giờ
        cũng hơn hàng mới hứa, và lô về sớm hơn thì ràng buộc lịch nhẹ hơn.
        """
        self._doi_co(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bat=True)
        # MỘT lượt dựng bảng cho cả ba việc (nhặt · soi lại · trả kết quả). Bảng không phụ thuộc
        # bảng giữ chỗ nên các dòng vừa nhặt không làm nó cũ đi.
        bang = self.kh.can_doi()
        self.nhat_them(chi_chu_the=(lsx_id, bai_ghep_id), bang=bang)
        return self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bang=bang)

    def tat(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> dict:
        """Nhả HẾT. Không phải hoàn tác — bật lại có thể chẳng còn gì, nơi gọi phải hỏi trước."""
        self.repo.xoa_cua_chu_the(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
        self._doi_co(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id, bat=False)
        return self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)

    def nhat_them(self, *, chi_chu_the: tuple | None = None, bang: dict | None = None) -> int:
        """Bù thêm cho MỌI chủ thể đang bật công tắc mà chưa giữ đủ. Trả số dòng giữ chỗ đẻ ra.

        Gọi khi HÀNG VỀ NHẬP KHO — đó là toàn bộ lý do "bật = đăng ký" chứ không phải chụp một lần.

        Thứ tự nhặt = thứ tự dòng của `can_doi()`, tức **theo ngày cần**: lệnh cần sớm ăn trước.
        Không sắp lại ở đây — sắp lại là đẻ luật ưu tiên thứ hai, và hai luật sẽ lệch nhau.
        """
        if bang is None:
            bang = self.kh.can_doi()
        nhu_cau = self._nhu_cau_theo_chu_the(bang)
        if not nhu_cau:
            return 0
        bat_lsx, bat_bai = self.repo.dang_bat()

        hangs = sorted({h for m in nhu_cau.values() for h in m})
        tu_do = self.ton_tu_do(hangs)
        ve = self._lo_dang_ve(bang, hangs)

        moi: list[VatTuGiuCho] = []
        for chu in self._thu_tu_chu_the(bang):
            if chi_chu_the is not None and chu != chi_chu_the:
                continue
            lsx_id, bg_id = chu
            if not ((lsx_id in bat_lsx) if lsx_id is not None else (bg_id in bat_bai)):
                continue
            tt = self.trang_thai(lsx_id=lsx_id, bai_ghep_id=bg_id, bang=bang)
            for hang, con in tt["thieu"].items():
                # 1) Hàng CÓ THẬT trong kho.
                lay = min(con, _f(tu_do.get(hang)))
                if lay > 0:
                    tu_do[hang] = _f(tu_do.get(hang)) - lay
                    con -= lay
                    moi.append(self._dong(chu, hang, lay, NGUON_KHO, None))
                # 2) Còn thiếu thì bám lô ĐANG VỀ, sớm trước.
                i = 0
                while con > 0 and i < len(ve.get(hang, [])):
                    ngay, sl = ve[hang][i]
                    lay = min(con, sl)
                    if lay > 0:
                        ve[hang][i] = (ngay, sl - lay)
                        con -= lay
                        moi.append(self._dong(chu, hang, lay, NGUON_DANG_VE, ngay))
                    if ve[hang][i][1] <= 0:
                        i += 1
                    else:
                        break
        self.repo.them(moi)
        return len(moi)

    # ================== KHO GỌI VÀO ==================

    def kiem_xuat(self, *, hang: Hang, so_luong: float,
                  lsx_id: int | None = None, bai_ghep_id: int | None = None) -> str | None:
        """Kho sắp xuất `so_luong` của `hang` cho ai đó — có lấn vào chỗ người khác giữ không?

        Trả câu từ chối, hoặc `None` nếu xuất được.

        Được phép lấy: **tồn tự do + phần CHÍNH chủ thể này đang giữ**. Vế sau là mấu chốt — xuất
        cho lệnh A thì chính chỗ A giữ phải dùng được, không thì giữ chỗ tự khoá chân người giữ.

        Xuất KHÔNG gắn lệnh nào (`lsx_id`/`bai_ghep_id` đều trống — lĩnh chung, bù hao, mẫu) thì
        chỉ được ăn phần tự do.
        """
        tu_do = _f(self.ton_tu_do([hang]).get(hang))
        cua_minh = 0.0
        if lsx_id is not None or bai_ghep_id is not None:
            cua_minh = sum(
                _f(r.so_luong) for r in self.repo.cua_chu_the(
                    lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
                if (r.hang_loai, r.hang_id) == hang
            )
        if so_luong <= tu_do + cua_minh + 1e-9:
            return None
        return (
            f"Chỉ còn {tu_do:g} chưa ai giữ"
            + (f" (cộng {cua_minh:g} của chính lệnh này)" if cua_minh else "")
            + f", không đủ để xuất {so_luong:g}. Phần còn lại đang được lệnh khác giữ chỗ — "
            "vào Kế hoạch vật tư nhả bớt nếu muốn ưu tiên phiếu này."
        )

    def tieu_thu(self, *, hang: Hang, so_luong: float,
                 lsx_id: int | None = None, bai_ghep_id: int | None = None) -> float:
        """Kho ĐÃ ghi sổ xuất — phần giữ chỗ tương ứng HOÁ THÀNH phần đã cấp, nhả khỏi bảng này.

        Không nhả thì đếm hai lần: tồn đã giảm khi kho ghi sổ, mà chỗ giữ vẫn còn trừ tiếp vào tồn
        tự do ⇒ mọi lệnh khác báo thiếu oan.

        Nhả phần `kho` TRƯỚC, `dang_ve` sau: hàng vừa xuất là hàng có thật trong kho, đúng loại
        đang nhả. Trả về phần đã nhả được.
        """
        con = float(so_luong)
        rows = [r for r in self.repo.cua_chu_the(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
                if (r.hang_loai, r.hang_id) == hang]
        rows.sort(key=lambda r: 0 if r.nguon == NGUON_KHO else 1)
        for r in rows:
            if con <= 0:
                break
            bot = min(con, _f(r.so_luong))
            con -= bot
            if _f(r.so_luong) - bot <= 0.004:      # nhả sạch dòng (Numeric(14,2))
                self.db.delete(r)
            else:
                r.so_luong = round(_f(r.so_luong) - bot, 2)
        self.db.commit()
        return float(so_luong) - con

    # ================== phụ ==================

    def _lo_dang_ve(self, bang: dict, hangs: list[Hang]) -> dict[Hang, list[tuple[date, float]]]:
        """Lô đang về CÒN TRỐNG chỗ = số đang về − phần đã có chủ (`nguon='dang_ve'`).

        Trừ phần đã giữ hứa, không thì hai lệnh cùng bám một lô và cả hai đều tưởng mình có hàng.
        Đơn giản hoá có chủ ý: trừ theo TỔNG rồi cắt dần từ lô sớm nhất, không truy từng lô ai giữ
        — bảng giữ chỗ cố ý không neo lô nào (xem docstring model).
        """
        ra: dict[Hang, list[tuple[date, float]]] = {}
        da_hua = {h: 0.0 for h in hangs}
        for r in self.db.query(VatTuGiuCho).filter(VatTuGiuCho.nguon == NGUON_DANG_VE).all():
            h = (r.hang_loai, r.hang_id)
            if h in da_hua:
                da_hua[h] += _f(r.so_luong)
        for hang, ds in self.kh._hang_dang_ve().items():
            if hang not in set(hangs):
                continue
            con_hua = da_hua.get(hang, 0.0)
            con_lai: list[tuple[date, float]] = []
            # `_hang_dang_ve` trả kèm mã phiếu; ở đây chỉ cần (ngày, số) — chỗ giữ hứa cố ý
            # KHÔNG neo vào lô nào (xem docstring model), nên mã phiếu không có việc gì.
            for ngay, sl, *_ in ds:
                bot = min(con_hua, sl)
                con_hua -= bot
                if sl - bot > 0:
                    con_lai.append((ngay, sl - bot))
            ra[hang] = con_lai
        return ra

    @staticmethod
    def _thu_tu_chu_the(bang: dict) -> list[tuple]:
        """Chủ thể theo THỨ TỰ XUẤT HIỆN trong bảng cân đối = theo ngày cần. Không sắp lại."""
        ra: list[tuple] = []
        for nhom in bang.get("items", []):
            if nhom.get("loai_nhom") != "vat_tu":
                continue
            for d in nhom.get("dong", []):
                chu = (d.get("lsx_id"), d.get("bai_ghep_id"))
                if chu != (None, None) and chu not in ra:
                    ra.append(chu)
        return ra

    @staticmethod
    def _dong(chu: tuple, hang: Hang, sl: float, nguon: str, ngay: date | None) -> VatTuGiuCho:
        return VatTuGiuCho(
            hang_loai=hang[0], hang_id=hang[1], lsx_id=chu[0], bai_ghep_id=chu[1],
            so_luong=round(sl, 2), nguon=nguon, ngay_ve=ngay,
        )

    def _co_bat(self, *, lsx_id: int | None, bai_ghep_id: int | None) -> bool:
        obj = (self.db.get(Lsx, lsx_id) if lsx_id is not None
               else self.db.get(BaiGhep, bai_ghep_id))
        return bool(getattr(obj, "giu_cho_bat", False))

    def _doi_co(self, *, lsx_id: int | None, bai_ghep_id: int | None, bat: bool) -> None:
        obj = (self.db.get(Lsx, lsx_id) if lsx_id is not None
               else self.db.get(BaiGhep, bai_ghep_id))
        if obj is None:
            raise GiuChoError("Không tìm thấy lệnh / bài ghép.")
        obj.giu_cho_bat = bat
        self.db.commit()
