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

from ..models.don_vi_do import HO_GOI_Y
from ..repositories.don_vi_do_repo import DonViDoRepository
from .quy_doi_service import BIEN, _so, bien_trong, cap_map, duong_di, he_so_duong
from .thanh_phan_engine import safe_eval

# Biến → chữ người đọc, dùng khi in công thức ra bảng ("1 tờ = định lượng × dài × rộng kg").
BIEN_CHU = {"dinh_luong": "định lượng", "dai": "dài", "rong": "rộng", "so_con": "số con"}

# Sai số tương đối cho phép khi so hai đường quy đổi. Không so tuyệt đối vì hệ số trải từ 0,001
# tới 1.000.000 — tuyệt đối thì hoặc quá chặt với số nhỏ, hoặc quá lỏng với số lớn.
SAI_SO = 1e-6


def cong_thuc_chu(cong_thuc: str) -> str:
    """Công thức → chữ đọc được: `dinh_luong * dai * rong` → "định lượng × dài × rộng"."""
    ra = cong_thuc or ""
    for bien, chu in BIEN_CHU.items():
        ra = re.sub(rf"\b{bien}\b", chu, ra)
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
        self._log(actor_id, "update_don_vi", obj.id, f"Sửa đơn vị {obj.ma}")
        return obj

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        self._log(actor_id, "delete_don_vi", obj.id, f"Xoá đơn vị {obj.ma}")
        self.repo.delete(obj)

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
        if not ct:
            # Dòng ĐỘNG không so được với đường hằng lúc khai (chưa có giấy nào để thay biến) —
            # kiểm nó là lúc dùng, kèm diễn giải. Chỉ chặn được cái so được.
            self._kiem_mau_thuan(tu.ma, den.ma, he_so)
        obj = self.repo.create_cap(data)
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
        if not ct:
            # Bỏ qua CHÍNH cặp đang sửa khi dò đường, không thì nó tự mâu thuẫn với bản cũ của mình.
            self._kiem_mau_thuan(tu.ma, den.ma, he_so, bo_qua_cap_id=obj.id)
        obj = self.repo.update_cap(obj, data)
        self._log(actor_id, "update_don_vi_cap", obj.id,
                  f"Sửa quy đổi 1 {tu.ten} = {ct or _so(he_so)} {den.ten}")
        return obj

    def delete_cap(self, cap_id: int, actor_id: int | None = None) -> None:
        obj = self.repo.get_cap(cap_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy dòng quy đổi.")
        self._log(actor_id, "delete_don_vi_cap", obj.id, f"Xoá quy đổi #{obj.id}")
        self.repo.delete_cap(obj)

    # --- mô tả cho màn hình --------------------------------------------------
    def quy_doi_text(self, obj) -> str:
        """Câu quy đổi ĐỌC TỪ CHÍNH DÒNG NÀY, nhiều cặp thì nối bằng ' · '.

        Luôn mở đầu bằng đơn vị của dòng đang xem — nhìn dòng cm² mà thấy câu "1 m² = 10.000 cm²"
        thì phải tự lật trong đầu mới hiểu, mà hai dòng m² và cm² lại hiện y hệt nhau. Khi đơn vị
        này là vế PHẢI thì viết "10.000 cm² = 1 m²" chứ không đổi thành "1 cm² = 0,0001 m²": số
        thập phân lẻ khó đọc hơn hẳn số nguyên.
        """
        caps = [c for c in self.repo.cap_rows() if c.tu_ma == obj.ma or c.den_ma == obj.ma]
        if not caps:
            return "Chưa khai quy đổi"
        cau: list[str] = []
        ten = {d.ma: d.ten for d in self.repo.all_active()}
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

    def canh_bao(self, obj) -> list[str]:
        """Cảnh báo mềm — hiện ở màn khai, KHÔNG chặn lưu."""
        out: list[str] = []
        if not any(c.tu_ma == obj.ma or c.den_ma == obj.ma for c in self.repo.cap_rows()):
            out.append(
                f"Chưa khai quy đổi — {obj.ten} chưa đổi qua lại được với đơn vị nào."
            )
        return out

    def _log(self, actor_id: int | None, action: str, target_id: int, detail: str) -> None:
        if self.audit is None:
            return
        self.audit.create(
            actor_user_id=actor_id, action=action, target=f"don_vi_do:{target_id}", detail=detail,
        )
