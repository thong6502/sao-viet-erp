"""Danh mục Đơn vị đo + CẶP quy đổi — service CRUD.

Mô hình: người dùng khai theo CẶP như cách nói ngoài đời ("1 tấn = 1.000 kg"), lưu vào
`don_vi_quy_doi`. Cặp chưa khai trực tiếp thì `quy_doi_service` dò đường qua trung gian.

Đổi lại sự thoải mái đó, hai cặp có thể MÂU THUẪN nhau (1 tấn = 1.000 kg nhưng 1 tấn = 999.000 g
trong khi 1 kg = 1.000 g). Chủ chốt 2026-07-30: **CHẶN, không cho lưu** — số quy đổi chảy thẳng
vào tiền khoán và tồn kho, lệch mà im lặng thì phát hiện ra đã trả lương sai mấy tháng.
"""
from __future__ import annotations

import re
from datetime import date

from ..models.don_vi_do import HO_GOI_Y, TRAM_DONG_GIAY
from .bien_cong_thuc import LOAI_QUY_DOI, bien_cho
from ..repositories.don_vi_do_repo import DonViDoRepository
from .quy_doi_service import (
    BIEN, _dong_tren_duong, _so, bien_trong, cap_map, cum_tinh, duong_di, he_so_duong,
)
from .thanh_phan_engine import safe_eval

# 🔴 `BIEN_CHU` (bảng nhãn riêng thứ ba) ĐÃ GỠ 11/08/2026 — nhãn nay lấy từ TỪ ĐIỂN CHUNG
# `bien_cong_thuc.nhan()`. Giữ bảng riêng ở đây là đúng cái bệnh đang chữa: thêm biến mới thì bảng
# này không biết, công thức in ra hiện mã trần (`dai_in`) giữa những chữ tiếng Việt.

# Sai số tương đối cho phép khi so hai đường quy đổi. Không so tuyệt đối vì hệ số trải từ 0,001
# tới 1.000.000 — tuyệt đối thì hoặc quá chặt với số nhỏ, hoặc quá lỏng với số lớn.
SAI_SO = 1e-6


def cong_thuc_chu(cong_thuc: str) -> str:
    """Công thức → chữ đọc được: `dinh_luong * dai_in * rong_in` → "Định lượng giấy × Dài tờ in ×
    Rộng tờ in". Nhãn lấy từ TỪ ĐIỂN CHUNG nên thêm biến mới là câu này tự đọc được."""
    ra = cong_thuc or ""
    for b in bien_cho(LOAI_QUY_DOI):
        ra = re.sub(rf"\b{b['ma']}\b", b["nhan"], ra)
    return ra.replace("*", "×").replace("/", "÷")


class DonViDoError(Exception):
    pass


class DonViDoValidationError(DonViDoError):
    pass


class DonViDoDuplicate(DonViDoError):
    pass


class DonViDoNotFound(DonViDoError):
    pass


class DonViDoService:
    def __init__(self, repo: DonViDoRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    # --- đơn vị --------------------------------------------------------------
    def _validate(self, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise DonViDoValidationError("Mã đơn vị không được trống.")
        if not (data.get("ten") or "").strip():
            raise DonViDoValidationError("Tên đơn vị không được trống.")
        # Trạm dòng giấy là MENU đóng: engine chạy chuỗi bù hao theo đúng 5 mức này, gõ mức lạ thì
        # `TRAM_THU_TU` không có bậc và bước rơi khỏi chuỗi trong im lặng.
        tram = (data.get("tram_dong_giay") or "").strip() or None
        data["tram_dong_giay"] = tram
        if tram is not None and tram not in TRAM_DONG_GIAY:
            raise DonViDoValidationError(
                f"Trạm dòng giấy phải là một trong: {' · '.join(TRAM_DONG_GIAY)}.")
        # CÁCH ĐO (mg 0192): công thức định nghĩa chính đơn vị này, ra LƯỢNG. Kiểm bằng đúng bộ luật
        # của công thức quy đổi — biến lạ thì cách đo nằm chết, mọi vật tư dùng đơn vị này im lặng
        # không ra số. Để trống = đơn vị thường, không đo bằng công thức.
        if "cong_thuc" in data:
            ct = (data.get("cong_thuc") or "").strip()
            data["cong_thuc"] = ct or None
            if ct:
                self._kiem_cong_thuc(ct)
                self._kiem_mot_cong_thuc_moi_cum(ct, str(data.get("ma") or ""))
                self._kiem_khong_vong_tron(ct, str(data.get("ma") or ""))

    @staticmethod
    def _chuan_hoa(data: dict) -> dict:
        """Loại đo về `strip().lower()` — hai lần gõ cùng nghĩa phải ra CÙNG một nhóm khi hiển thị.
        Loại đo KHÔNG quyết định đổi được hay không; việc đó là của cặp đã khai."""
        out = dict(data)
        if out.get("ho"):
            out["ho"] = str(out["ho"]).strip().lower()
        return out

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy đơn vị.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def ho_goi_y(self) -> list[str]:
        """Loại đo gợi ý = bộ mồi ∪ loại nhà máy đã dùng (giống cách gợi ý đơn vị của Lương khoán)."""
        return sorted({*HO_GOI_Y, *self.repo.distinct_ho()})

    def create(self, data: dict, actor_id: int | None = None):
        data = self._chuan_hoa(data)
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise DonViDoDuplicate("Mã đơn vị đã tồn tại.")
        data.setdefault("hieu_luc_tu", date.today())
        obj = self.repo.create(data)
        self._quen_cache()
        self._log(actor_id, "create_don_vi", obj.id, f"Thêm đơn vị {obj.ma} ({obj.ten})")
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        data = self._chuan_hoa(data)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != obj.id:
            raise DonViDoDuplicate("Mã đơn vị đã tồn tại.")
        obj = self.repo.update(obj, data)
        self._quen_cache()
        self._log(actor_id, "update_don_vi", obj.id, f"Sửa đơn vị {obj.ma}")
        return obj

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        self._log(actor_id, "delete_don_vi", obj.id, f"Xoá đơn vị {obj.ma}")
        self.repo.delete(obj)
        self._quen_cache()

    # --- cặp quy đổi ---------------------------------------------------------
    def list_cap(self, **kw):
        return self.repo.list_cap(**kw)

    def _kiem_mau_thuan(self, tu_ma: str, den_ma: str, he_so: float,
                        bo_qua_cap_id: int | None = None) -> None:
        """Chặn cặp làm LỆCH đường quy đổi đã có.

        Ví dụ thật: đã có `1 tấn = 1.000 kg` và `1 kg = 1.000 g`; giờ khai `1 tấn = 999.000 g` →
        đường qua kg ra 1.000.000 g. Hai số cùng trả lời một câu hỏi mà khác nhau ⇒ từ chối, nói rõ
        đường nào đang mâu thuẫn để người khai biết sửa cái nào.
        """
        cap = cap_map(self.repo.cap_rows(bo_qua_id=bo_qua_cap_id))
        duong = duong_di(tu_ma, den_ma, cap)
        if duong is None:
            return
        hs_cu = he_so_duong(duong, cap)
        if abs(hs_cu - he_so) <= SAI_SO * max(abs(hs_cu), abs(he_so), 1.0):
            return
        qua = " → ".join(duong)
        raise DonViDoValidationError(
            f"Lệch với quy đổi đã khai: theo đường {qua} thì 1 {tu_ma} = {_so(hs_cu)} {den_ma}, "
            f"còn bạn đang khai {_so(he_so)}. Sửa lại cho khớp, hoặc sửa cặp cũ trước."
        )

    def _kiem_cong_thuc(self, cong_thuc: str) -> None:
        """Công thức phải chạy được và chỉ dùng biến hệ thống bơm được — biến lạ thì vĩnh viễn
        thiếu số, dòng quy đổi đó nằm chết trong bảng mà không ai biết vì sao."""
        la = [b for b in bien_trong(cong_thuc) if b not in BIEN]
        if la:
            raise DonViDoValidationError(
                f"Công thức dùng biến không có: {', '.join(la)}. "
                f"Biến dùng được: {', '.join(BIEN)}."
            )
        try:
            safe_eval(cong_thuc, {b: 1.0 for b in BIEN})
        except (ValueError, ZeroDivisionError) as e:
            raise DonViDoValidationError(f"Công thức không chạy được: {e}") from None

    def _kiem_mot_cong_thuc_moi_dich(
        self, ct: str, den_id: int, den, *, bo_qua_cap_id: int | None = None
    ) -> None:
        """MỖI ĐƠN VỊ CHỈ ĐƯỢC TÍNH RA BẰNG MỘT CÔNG THỨC (12/08/2026).

        Luật sinh ra cho BOM. Vật tư khai ĐVT là kg thì lúc bung ở bước lệnh máy phải đổi số lượng
        của bước sang kg — có hai công thức cùng ra kg thì không có cách nào chọn, và chọn bừa nghĩa
        là số vật tư sai mà nhìn vẫn hợp lý.

        CHỈ chặn theo đơn vị ĐÍCH. Một đơn vị vẫn được khai nhiều công thức ĐI RA
        (`tờ → cái` · `tờ → kg` · `tờ → m²`) — ba đích là ba câu hỏi khác nhau, không tranh nhau.

        Không đụng dữ liệu cũ: dòng đã lưu trước luật này vẫn nằm nguyên, `canh_bao` nhắc để người
        dùng tự dọn. Chặn ở đây chỉ ngăn khai thêm cái thứ hai.
        """
        if not ct:
            return
        cu = self.repo.dong_ve(den_id, bo_qua_id=bo_qua_cap_id)
        if cu is None:
            return
        raise DonViDoValidationError(
            f"{den.ten} đã có công thức động: 1 {cu.tu_ten} = "
            f"{cong_thuc_chu(cu.cong_thuc)} {den.ten}. "
            f"Mỗi đơn vị chỉ tính ra bằng MỘT công thức — sửa dòng đó thay vì khai thêm."
        )

    def _kiem_khong_vong_tron(self, ct: str, ma: str) -> None:
        """Chiều NGƯỢC của luật vòng tròn (14/08/2026).

        Chiều xuôi ở `cong_doan_service`: chọn đơn vị RA có công thức dùng `sl_vao` thì chặn. Không
        có chiều này thì chỉ cần khai ngược thứ tự là lọt — khai công đoạn trước, rồi mới vào sửa
        công thức của đơn vị thêm chip.
        """
        lap = [b for b in bien_trong(ct) if b in ("sl_vao", "sl_ra")]
        if not lap:
            return
        ten_cd = self.repo.cong_doan_lay_lam_don_vi_ra((ma or "").strip().lower())
        if not ten_cd:
            return
        raise DonViDoValidationError(
            f"Đơn vị này đang là ĐẦU RA của công đoạn {' · '.join(ten_cd)} (bước ngoài dòng giấy). "
            f"Công thức dùng {' · '.join(lap)} — số của chính bước — sẽ thành vòng tròn: SL ra cần "
            f"SL vào, mà SL vào lại suy từ SL ra. Bỏ chip đó, hoặc đổi đơn vị đầu ra của công đoạn "
            f"đó trước. [E-DV-VONG-TRON]"
        )

    def _cum_co_cong_thuc(self, ma: str, *, tru_ma: str = "") -> list:
        """Đơn vị trong CỤM TĨNH của `ma` đang mang công thức lượng. Bỏ qua chính `tru_ma`."""
        goc = (ma or "").strip().lower()
        if not goc:
            return []
        cum = cum_tinh(goc, self.repo.cap_rows())
        bo = {goc, (tru_ma or "").strip().lower()}
        return [d for d in self._dv_cache()
                if d.ma in cum and d.ma not in bo and (d.cong_thuc or "").strip()]

    def _kiem_mot_cong_thuc_moi_cum(self, ct: str, ma: str) -> None:
        """MỘT CỤM TĨNH CHỈ MỘT CÔNG THỨC LƯỢNG (14/08/2026).

        `kg · tấn · g` nối nhau bằng hằng số nên chúng là MỘT phép đo. Khai công thức ở cả `kg` lẫn
        `tấn` là hai số cho cùng một câu hỏi, và `_cach_do_lan` bên lệnh sẽ phải chọn bừa.

        Chỉ đi qua cạnh TĨNH: `tờ` với `kg` nối bằng cạnh ĐỘNG (`1 tờ = f(quy cách) kg`) — hai thứ
        khác loại, cả hai được có công thức riêng. Gộp chúng là chặn oan.
        """
        if not ct:
            return
        kia = self._cum_co_cong_thuc(ma)
        if not kia:
            return
        chu = kia[0]
        ten_cum = " · ".join(sorted({chu.ten, *(d.ten for d in kia)}))
        raise DonViDoValidationError(
            f"“{chu.ten}” đã có công thức tính lượng: {cong_thuc_chu(chu.cong_thuc)}. "
            f"Cả cụm {ten_cum} quy đổi cho nhau bằng số cố định nên chỉ được MỘT công thức — "
            f"sửa ở “{chu.ten}”, hoặc xoá công thức đó trước. [E-DV-BOM-TRUNG]"
        )

    def _kiem_noi_cum_khong_gop_hai_cong_thuc(self, tu, den) -> None:
        """Nối hai cụm mà MỖI BÊN đã có công thức lượng ⇒ cụm mới có hai. CHẶN.

        Chiều ngược của `_kiem_mot_cong_thuc_moi_cum`. Không có nó thì luật thủng, chỉ cần khai
        ngược thứ tự: khai công thức ở `kg`, khai công thức ở `tạ`, RỒI mới nối "1 tạ = 100 kg".

        Chỉ áp cho cặp TĨNH — nơi gọi đã lọc (`if not ct`).
        """
        ben_tu = [d for d in self._dv_cache()
                  if d.ma in cum_tinh(tu.ma, self.repo.cap_rows()) and (d.cong_thuc or "").strip()]
        ben_den = [d for d in self._dv_cache()
                   if d.ma in cum_tinh(den.ma, self.repo.cap_rows()) and (d.cong_thuc or "").strip()]
        if not ben_tu or not ben_den:
            return
        raise DonViDoValidationError(
            f"Nối “{tu.ten}” với “{den.ten}” là gộp hai cụm đang CÙNG có công thức tính lượng "
            f"(“{ben_tu[0].ten}” và “{ben_den[0].ten}”). Một cụm chỉ được MỘT — xoá bớt một công "
            f"thức trước khi khai quy đổi này. [E-DV-BOM-TRUNG]"
        )

    def _tach_the(self, data: dict, he_so_cu: float = 0.0) -> tuple[dict, float, str]:
        """Chuẩn hoá dữ liệu một dòng quy đổi: số HAY công thức, không phải cả hai.

        Dòng động lưu `he_so = 0` (xem model): để 1 thì chỗ nào lỡ đọc cột số sẽ ra con số y như
        thật mà sai, để 0 thì hỏng lộ ra ngay.
        """
        ct = (data.get("cong_thuc") or "").strip()
        if ct:
            self._kiem_cong_thuc(ct)
            return {**data, "cong_thuc": ct, "he_so": 0}, 0.0, ct
        he_so = float(data.get("he_so", he_so_cu) or 0)
        if he_so <= 0:
            raise DonViDoValidationError("Số quy đổi phải lớn hơn 0, hoặc khai bằng công thức.")
        return {**data, "cong_thuc": None, "he_so": he_so}, he_so, ""

    def create_cap(self, data: dict, actor_id: int | None = None):
        tu_id, den_id = data.get("tu_id"), data.get("den_id")
        if not tu_id or not den_id:
            raise DonViDoValidationError("Phải chọn cả hai đơn vị.")
        if tu_id == den_id:
            raise DonViDoValidationError("Hai đơn vị phải khác nhau.")
        data, he_so, ct = self._tach_the(data)
        tu, den = self.get(tu_id), self.get(den_id)
        if self.repo.find_cap(tu_id, den_id) is not None:
            raise DonViDoDuplicate(f"Đã có quy đổi {tu.ten} → {den.ten}.")
        self._kiem_mot_cong_thuc_moi_dich(ct, den_id, den)
        if not ct:
            # Dòng ĐỘNG không so được với đường hằng lúc khai (chưa có giấy nào để thay biến) —
            # kiểm nó là lúc dùng, kèm diễn giải. Chỉ chặn được cái so được.
            self._kiem_mau_thuan(tu.ma, den.ma, he_so)
            self._kiem_noi_cum_khong_gop_hai_cong_thuc(tu, den)
        obj = self.repo.create_cap(data)
        self._quen_cache()
        self._log(actor_id, "create_don_vi_cap", obj.id,
                  f"Khai quy đổi 1 {tu.ten} = {ct or _so(he_so)} {den.ten}")
        return obj

    def update_cap(self, cap_id: int, data: dict, actor_id: int | None = None):
        obj = self.repo.get_cap(cap_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy dòng quy đổi.")
        if "cong_thuc" not in data and obj.cong_thuc:
            data = {**data, "cong_thuc": obj.cong_thuc}
        data, he_so, ct = self._tach_the(data, he_so_cu=float(obj.he_so or 0))
        tu, den = self.get(obj.tu_id), self.get(obj.den_id)
        self._kiem_mot_cong_thuc_moi_dich(ct, obj.den_id, den, bo_qua_cap_id=obj.id)
        if not ct:
            # Bỏ qua CHÍNH cặp đang sửa khi dò đường, không thì nó tự mâu thuẫn với bản cũ của mình.
            self._kiem_mau_thuan(tu.ma, den.ma, he_so, bo_qua_cap_id=obj.id)
        obj = self.repo.update_cap(obj, data)
        self._quen_cache()
        self._log(actor_id, "update_don_vi_cap", obj.id,
                  f"Sửa quy đổi 1 {tu.ten} = {ct or _so(he_so)} {den.ten}")
        return obj

    def delete_cap(self, cap_id: int, actor_id: int | None = None) -> None:
        obj = self.repo.get_cap(cap_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy dòng quy đổi.")
        self._log(actor_id, "delete_don_vi_cap", obj.id, f"Xoá quy đổi #{obj.id}")
        self.repo.delete_cap(obj)
        self._quen_cache()

    # --- mô tả cho màn hình --------------------------------------------------
    def quy_doi_text(self, obj) -> str:
        """Câu quy đổi ĐỌC TỪ CHÍNH DÒNG NÀY, nhiều cặp thì nối bằng ' · '.

        Luôn mở đầu bằng đơn vị của dòng đang xem — nhìn dòng cm² mà thấy câu "1 m² = 10.000 cm²"
        thì phải tự lật trong đầu mới hiểu, mà hai dòng m² và cm² lại hiện y hệt nhau. Khi đơn vị
        này là vế PHẢI thì viết "10.000 cm² = 1 m²" chứ không đổi thành "1 cm² = 0,0001 m²": số
        thập phân lẻ khó đọc hơn hẳn số nguyên.
        """
        caps = [c for c in self._cap_cache() if c.tu_ma == obj.ma or c.den_ma == obj.ma]
        # ĐƠN VỊ TỰ TÍNH đứng trước: nó KHÔNG cần cặp nào để dùng được, nên in công thức ra đây thay
        # vì để trống. Trước 13/08/2026 cột này chỉ nhìn bảng cặp ⇒ `kg_giay_to_in` đã khai công
        # thức tử tế vẫn hiện "Chưa khai quy đổi", nhìn như chưa làm gì.
        ct = (getattr(obj, "cong_thuc", None) or "").strip()
        if ct:
            # KHÔNG có "1 " ở vế trái: đây là câu ĐỊNH NGHĨA ("kg giấy = định lượng × …"), không
            # phải tỉ số "1 tấn = 1.000 kg". Công thức đã tự nhân số lượng của lệnh nên vế phải là
            # TỔNG, viết "1 kg giấy = …" là đọc thành "mỗi một kg giấy bằng…" — vô nghĩa.
            return f"{obj.ten} = {cong_thuc_chu(ct)}"
        if not caps:
            return "Chưa khai quy đổi"
        cau: list[str] = []
        ten = {d.ma: d.ten for d in self._dv_cache()}
        for c in caps:
            kia = ten.get(c.den_ma, c.den_ma) if c.tu_ma == obj.ma else ten.get(c.tu_ma, c.tu_ma)
            if c.cong_thuc:
                # Dòng ĐỘNG: in nguyên chiều đã khai cho cả hai đơn vị (lật một công thức ra chữ
                # thì đọc còn khó hơn), thay tên biến bằng chữ thường ngày.
                cau.append(f"1 {ten.get(c.tu_ma, c.tu_ma)} = {cong_thuc_chu(c.cong_thuc)} "
                           f"{ten.get(c.den_ma, c.den_ma)}")
                continue
            hs = float(c.he_so)
            if c.den_ma == obj.ma:          # cặp lưu chiều ngược → quy về chiều của dòng này
                hs = 1.0 / hs if hs else 0.0
            # Vế trái luôn là số NGUYÊN: "1 kg = 1.000 g" chứ không phải "0,001 kg = 1 g", và
            # "10.000 cm² = 1 m²" chứ không phải "1 cm² = 0,0001 m²". Số lẻ đọc mệt hơn hẳn.
            if hs >= 1:
                cau.append(f"1 {obj.ten} = {_so(hs)} {kia}")
            else:
                cau.append(f"{_so(1.0 / hs)} {obj.ten} = 1 {kia}" if hs else f"1 {obj.ten} = ? {kia}")
        return " · ".join(cau)

    def _cap_de_cong_thuc(self, obj, rows) -> list[str]:
        """Cặp SỐ CỐ ĐỊNH nối hai LOẠI ĐO khác nhau, trong khi hai loại đó vốn đã nối được bằng
        đường CÔNG THỨC.

        Vì sao đáng ngờ: đổi ngang loại đo (tờ → kg, tờ → m²) phụ thuộc khổ + định lượng của TỪNG
        mặt hàng — đó chính là lý do nó được khai bằng công thức. Chốt thêm một con số cố định cho
        cùng cặp ấy là ghi đè công thức bằng con số chỉ đúng với đúng một mặt hàng.

        Đây là cách `1 tờ = 1.000 g` (⇒ mọi tờ giấy nặng 1 kg) lọt được vào DB: `_kiem_mau_thuan`
        chỉ so với đường HẰNG, mà tờ → kg lại là đường ĐỘNG nên nó không có gì để so.

        Chỉ CẢNH BÁO chứ không chặn: cạnh động có thể thiếu biến, và xưởng có thể có cặp ngang loại
        hợp lệ thật (1 lượt = 1 tờ). Cùng loại đo thì không bao giờ báo — "1 tấn = 1.000 kg" đúng
        với mọi mặt hàng.
        """
        ho = {d.ma: (d.ho or "khac") for d in self._dv_cache()}
        out: list[str] = []
        for r in rows:
            if r.cong_thuc or obj.ma not in (r.tu_ma, r.den_ma):
                continue
            if ho.get(r.tu_ma) == ho.get(r.den_ma):
                continue
            con_lai = [x for x in rows if x is not r]
            # `gia_dinh_du_bien` để cạnh động vào được đồ thị dù chưa có mặt hàng nào thay biến —
            # ở đây chỉ hỏi "có đường không", không lấy số.
            duong = duong_di(r.tu_ma, r.den_ma, cap_map(con_lai, {}, gia_dinh_du_bien=True))
            if duong and _dong_tren_duong(con_lai, duong):
                out.append(
                    f"“1 {r.tu_ten} = {_so(float(r.he_so))} {r.den_ten}” là số cố định, nhưng "
                    f"{r.tu_ten} → {r.den_ten} vốn đổi bằng công thức (tuỳ khổ · định lượng của "
                    f"từng mặt hàng). Số cố định này chỉ đúng với một mặt hàng — nên xoá."
                )
        return out

    # Màn Đơn vị gọi `canh_bao` + `quy_doi_text` cho TỪNG dòng (18 đơn vị → 18 lượt). Không cache
    # thì mỗi dòng lại quét cả bảng đơn vị và bảng cặp — service sống đúng một request nên cache ở
    # đây an toàn, và dữ liệu không đổi giữa chừng.
    def _dv_cache(self):
        if getattr(self, "_dv_rows", None) is None:
            self._dv_rows = list(self.repo.all_active())
        return self._dv_rows

    def _cap_cache(self):
        if getattr(self, "_cap_rows_c", None) is None:
            self._cap_rows_c = list(self.repo.cap_rows())
        return self._cap_rows_c

    def _quen_cache(self) -> None:
        """Gọi sau MỌI thao tác ghi — cùng một request có thể ghi rồi đọc lại (tạo đơn vị xong
        router dựng ngay dòng trả về), đọc trúng cache cũ là hiện sai ngay màn vừa bấm."""
        self._dv_rows = None
        self._cap_rows_c = None

    def canh_bao(self, obj) -> list[str]:
        """Cảnh báo mềm — hiện ở màn khai, KHÔNG chặn lưu."""
        rows = self._cap_cache()
        out: list[str] = []
        # Đơn vị TỰ TÍNH bằng công thức thì không cần cặp nào — báo "chưa khai quy đổi" là báo oan,
        # và người khai sẽ đi khai thêm một cặp không ai dùng để cho hết cảnh báo.
        co_ct = bool((getattr(obj, "cong_thuc", None) or "").strip())
        if not co_ct and not any(c.tu_ma == obj.ma or c.den_ma == obj.ma for c in rows):
            out.append(
                f"Chưa khai quy đổi — {obj.ten} chưa đổi qua lại được với đơn vị nào."
            )
        # Dữ liệu khai TRƯỚC luật "một công thức mỗi đích" (12/08/2026) vẫn nằm nguyên — chặn chỉ áp
        # cho lần khai mới. Nhắc ở đây để người dùng tự dọn: còn hai công thức cùng ra một đơn vị thì
        # BOM bung vật tư sẽ vớ phải cái nào không ai đoán được.
        nhieu = [c for c in rows if (c.cong_thuc or "").strip() and c.den_ma == obj.ma]
        if len(nhieu) > 1:
            out.append(
                f"Có {len(nhieu)} công thức động cùng ra {obj.ten} "
                f"({' · '.join(c.tu_ten for c in nhieu)}) — BOM sẽ không biết chọn cái nào. "
                f"Giữ lại một."
            )
        out.extend(self._cap_de_cong_thuc(obj, rows))
        return out

    def _log(self, actor_id: int | None, action: str, target_id: int, detail: str) -> None:
        if self.audit is None:
            return
        self.audit.create(
            actor_user_id=actor_id, action=action, target=f"don_vi_do:{target_id}", detail=detail,
        )
