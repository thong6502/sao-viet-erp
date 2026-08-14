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
    BIEN, _so, bien_trong, cap_map, cum_tinh, duong_di, he_so_duong,
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

    # 🔴 `_kiem_mot_cong_thuc_moi_dich` ĐÃ GỠ 14/08/2026 (dựng 12/08, sống đúng hai ngày). Nó chặn
    # "hai công thức cùng ra một đơn vị ĐÍCH" — chỉ có nghĩa khi công thức còn có đích. Công thức
    # nay khai trên chính đơn vị và không quy về đâu cả; việc canh trùng chuyển sang
    # `_kiem_mot_cong_thuc_moi_cum` (một CỤM TĨNH một công thức).

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

    def cong_thuc_hieu_luc(self, obj) -> tuple[str, str, str] | None:
        """`(công thức, mã CHỦ, tên CHỦ)` — tự khai trước, không có thì MƯỢN trong cụm tĩnh.

        Cùng luật với `LsxService._cach_do_lan` bên engine: khai ở `kg` thì `tấn`/`g` dùng chung.
        Có ở đây để MÀN cũng nói đúng thứ engine làm — nhìn vào `g` mà thấy trống thì người khai
        tưởng chưa khai gì rồi đi khai lần hai, đúng thứ trùng lặp luật cụm sinh ra để chặn.
        """
        ma = (getattr(obj, "ma", "") or "").strip().lower()
        tu_khai = (getattr(obj, "cong_thuc", None) or "").strip()
        if tu_khai:
            return tu_khai, ma, getattr(obj, "ten", ma)
        chu = self._cum_co_cong_thuc(ma)
        if not chu:
            return None
        d = sorted(chu, key=lambda x: x.ma)[0]
        return (d.cong_thuc or "").strip(), d.ma, d.ten

    def he_so_tu_chu(self, chu_ma: str, ma: str) -> float:
        """Hệ số nhân từ đơn vị CHỦ sang `ma` — đi trên đồ thị cặp TĨNH. 1.0 nếu không cần đổi."""
        if not chu_ma or chu_ma == ma:
            return 1.0
        cap = cap_map(self.repo.cap_rows())
        duong = duong_di(chu_ma, ma, cap)
        return he_so_duong(duong, cap) if duong else 1.0

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

    def _tach_the(self, data: dict, he_so_cu: float = 0.0) -> tuple[dict, float]:
        """Chuẩn hoá một dòng quy đổi — chỉ còn SỐ.

        🔴 14/08/2026: nhánh `cong_thuc` đã gỡ. Cặp quy đổi nay chỉ mang hệ số cố định; công thức
        khai ở CHÍNH đơn vị (`don_vi_do.cong_thuc`) và trả LƯỢNG, không có đích. Ai gửi `cong_thuc`
        lên đây thì CHẶN, đừng nuốt im lặng — client cũ gửi nhầm mà lặng thinh là dữ liệu hỏng.
        """
        if (data.get("cong_thuc") or "").strip():
            raise DonViDoValidationError(
                "Cặp quy đổi chỉ nhận SỐ cố định. Công thức nay khai ở chính đơn vị "
                "(tab “Công thức quy đổi”) và trả ra LƯỢNG, không quy về đơn vị nào. "
                "[E-DV-CAP-CONGTHUC]")
        he_so = float(data.get("he_so", he_so_cu) or 0)
        if he_so <= 0:
            raise DonViDoValidationError("Số quy đổi phải lớn hơn 0.")
        return {k: v for k, v in data.items() if k != "cong_thuc"} | {"he_so": he_so}, he_so

    def create_cap(self, data: dict, actor_id: int | None = None):
        tu_id, den_id = data.get("tu_id"), data.get("den_id")
        if not tu_id or not den_id:
            raise DonViDoValidationError("Phải chọn cả hai đơn vị.")
        if tu_id == den_id:
            raise DonViDoValidationError("Hai đơn vị phải khác nhau.")
        data, he_so = self._tach_the(data)
        tu, den = self.get(tu_id), self.get(den_id)
        if self.repo.find_cap(tu_id, den_id) is not None:
            raise DonViDoDuplicate(f"Đã có quy đổi {tu.ten} → {den.ten}.")
        self._kiem_mau_thuan(tu.ma, den.ma, he_so)
        self._kiem_noi_cum_khong_gop_hai_cong_thuc(tu, den)
        obj = self.repo.create_cap(data)
        self._quen_cache()
        self._log(actor_id, "create_don_vi_cap", obj.id,
                  f"Khai quy đổi 1 {tu.ten} = {_so(he_so)} {den.ten}")
        return obj

    def update_cap(self, cap_id: int, data: dict, actor_id: int | None = None):
        obj = self.repo.get_cap(cap_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy dòng quy đổi.")
        data, he_so = self._tach_the(data, he_so_cu=float(obj.he_so or 0))
        tu, den = self.get(obj.tu_id), self.get(obj.den_id)
        # Bỏ qua CHÍNH cặp đang sửa khi dò đường, không thì nó tự mâu thuẫn với bản cũ của mình.
        self._kiem_mau_thuan(tu.ma, den.ma, he_so, bo_qua_cap_id=obj.id)
        obj = self.repo.update_cap(obj, data)
        self._quen_cache()
        self._log(actor_id, "update_don_vi_cap", obj.id,
                  f"Sửa quy đổi 1 {tu.ten} = {_so(he_so)} {den.ten}")
        return obj

    def delete_cap(self, cap_id: int, actor_id: int | None = None) -> None:
        obj = self.repo.get_cap(cap_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy dòng quy đổi.")
        self._log(actor_id, "delete_don_vi_cap", obj.id, f"Xoá quy đổi #{obj.id}")
        self.repo.delete_cap(obj)
        self._quen_cache()

    # --- mô tả cho màn hình --------------------------------------------------
    def quy_doi_chips(self, obj) -> list[dict]:
        """Từng mảnh của cột "Quy đổi", mỗi mảnh kèm LOẠI để màn danh sách tô màu — khỏi đoán.

        `loai`: `cong_thuc` (câu ĐỊNH NGHĨA, vế phải là TỔNG của lệnh) · `co_dinh` (tỉ số MỘT đơn
        vị). Hai thứ đọc khác nhau nên phải nhìn khác nhau.

        🔴 Vì sao server phải trả loại (14/08/2026): trước đó server chỉ trả một chuỗi gộp
        (`quy_doi_text`), màn danh sách tách bằng " · " rồi đoán loại bằng cách dò tên biến GHI
        CỨNG (`dinh_luong` · `dai` · `rong` · `so_con` · dấu `×`). Đoán trượt ngay: server đã đổi
        mã biến sang nhãn tiếng Việt bằng `cong_thuc_chu` TRƯỚC khi trả, nên không mảnh nào còn
        chứa mã biến — câu "bài in = Tờ vào máy + 2000" rơi hết xuống nhánh cuối, không có dấu `×`
        nên hiện xám y như một hệ số. Phân loại là việc của nơi BIẾT, tức chỗ dựng ra câu.
        """
        caps = [c for c in self._cap_cache() if c.tu_ma == obj.ma or c.den_ma == obj.ma]
        out: list[dict] = []
        # ĐƠN VỊ TỰ TÍNH đứng trước: nó KHÔNG cần cặp nào để dùng được, nên in công thức ra đây thay
        # vì để trống. Trước 13/08/2026 cột này chỉ nhìn bảng cặp ⇒ `kg_giay_to_in` đã khai công
        # thức tử tế vẫn hiện "Chưa khai quy đổi", nhìn như chưa làm gì.
        hl = self.cong_thuc_hieu_luc(obj)
        if hl:
            ct, chu_ma, chu_ten = hl
            # KHÔNG có "1 " ở vế trái: đây là câu ĐỊNH NGHĨA ("kg giấy = định lượng × …"), không
            # phải tỉ số "1 tấn = 1.000 kg". Công thức đã tự nhân số lượng của lệnh nên vế phải là
            # TỔNG, viết "1 kg giấy = …" là đọc thành "mỗi một kg giấy bằng…" — vô nghĩa.
            ma_nay = (obj.ma or "").strip().lower()
            if chu_ma == ma_nay:
                cau_ct = f"{obj.ten} = {cong_thuc_chu(ct)}"
            else:
                # MƯỢN của đơn vị khác trong cụm — phải NHÂN HỆ SỐ vào, không thì `g` hiện y hệt
                # `kg` trong khi 1 kg = 1.000 g. Nói rõ mượn của ai: sửa phải về đúng đơn vị chủ.
                hs_chu = self.he_so_tu_chu(chu_ma, ma_nay)
                ve_phai = (cong_thuc_chu(ct) if hs_chu == 1
                           else f"({cong_thuc_chu(ct)}) × {_so(hs_chu)}")
                cau_ct = f"{obj.ten} = {ve_phai}  (theo {chu_ten})"
            out.append({"text": cau_ct, "loai": "cong_thuc"})
        # KHÔNG dừng ở nhánh công thức: đơn vị vừa có công thức lượng vừa có cặp quy đổi là chuyện
        # thường (`kg` có công thức + `1 kg = 1.000 g` + `1 tấn = 1.000 kg`). Dừng sớm là nuốt mất
        # phần cặp, cột "Quy đổi" chỉ còn công thức — dính 14/08/2026.
        ten = {d.ma: d.ten for d in self._dv_cache()}
        for c in caps:
            kia = ten.get(c.den_ma, c.den_ma) if c.tu_ma == obj.ma else ten.get(c.tu_ma, c.tu_ma)
            hs = float(c.he_so)
            if c.den_ma == obj.ma:          # cặp lưu chiều ngược → quy về chiều của dòng này
                hs = 1.0 / hs if hs else 0.0
            # Vế trái luôn là số NGUYÊN: "1 kg = 1.000 g" chứ không phải "0,001 kg = 1 g", và
            # "10.000 cm² = 1 m²" chứ không phải "1 cm² = 0,0001 m²". Số lẻ đọc mệt hơn hẳn.
            if hs >= 1:
                cau = f"1 {obj.ten} = {_so(hs)} {kia}"
            else:
                cau = f"{_so(1.0 / hs)} {obj.ten} = 1 {kia}" if hs else f"1 {obj.ten} = ? {kia}"
            out.append({"text": cau, "loai": "co_dinh"})
        return out

    def quy_doi_text(self, obj) -> str:
        """Câu quy đổi ĐỌC TỪ CHÍNH DÒNG NÀY, nhiều mảnh thì nối bằng ' · '.

        Luôn mở đầu bằng đơn vị của dòng đang xem — nhìn dòng cm² mà thấy câu "1 m² = 10.000 cm²"
        thì phải tự lật trong đầu mới hiểu, mà hai dòng m² và cm² lại hiện y hệt nhau. Khi đơn vị
        này là vế PHẢI thì viết "10.000 cm² = 1 m²" chứ không đổi thành "1 cm² = 0,0001 m²": số
        thập phân lẻ khó đọc hơn hẳn số nguyên.

        Chuỗi phẳng, GIỮ cho chỗ nào chỉ cần một dòng chữ (nhật ký, tooltip). Màn danh sách dùng
        `quy_doi_chips` để còn biết mảnh nào là công thức.
        """
        chips = self.quy_doi_chips(obj)
        return " · ".join(c["text"] for c in chips) if chips else "Chưa khai quy đổi"

    # 🔴 `_cap_de_cong_thuc` ĐÃ GỠ 14/08/2026 — cảnh báo "cặp SỐ đè lên đường CÔNG THỨC". Nó chỉ có
    # nghĩa khi bảng cặp còn chứa cạnh động để mà đè; nay cặp chỉ còn số nên không còn gì để cảnh.
    #
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
        # 🔴 GỠ 14/08/2026 cùng quy đổi động: cảnh báo "có N công thức động cùng ra <đơn vị>". Luật
        # đó canh việc chọn giữa nhiều công thức CÙNG ĐÍCH — công thức nay không có đích nữa, và
        # "một cụm một công thức" (`_kiem_mot_cong_thuc_moi_cum`) đã CHẶN ngay lúc khai.
        return out

    def _log(self, actor_id: int | None, action: str, target_id: int, detail: str) -> None:
        if self.audit is None:
            return
        self.audit.create(
            actor_user_id=actor_id, action=action, target=f"don_vi_do:{target_id}", detail=detail,
        )
