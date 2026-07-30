"""Danh mục Đơn vị đo — service CRUD + hai cảnh báo mềm (MÁY CHỈ GHI NHẬN, không chặn).

Hai chỗ dễ sai mà máy phải nhắc chứ không được tự sửa:
  · **Họ chưa có đơn vị gốc** (không dòng nào hệ số = 1) ⇒ cả họ không đổi được.
  · **Hệ số lệch chuẩn vật lý** (khai 1 tấn = 900 kg) ⇒ nhắc đỏ, nhưng vẫn lưu — chủ đã chốt "tất cả
    khai được", và biết đâu xưởng có quy ước riêng.
Sửa hệ số là đổi tiền của mọi phiếu tính về sau → service ghi AuditLog + đặt `hieu_luc_tu`.
"""
from __future__ import annotations

from datetime import date

from ..models.don_vi_do import HO_GOI_Y
from ..repositories.don_vi_do_repo import DonViDoRepository

# Chuẩn vật lý để ĐỐI CHIẾU (không phải để chặn): (ma, ma_goc) → hệ số đúng.
CHUAN_VAT_LY = {
    "m2": 10_000.0,   # 1 m² = 10.000 cm²
    "tan": 1_000.0,   # 1 tấn = 1.000 kg
    "g": 0.001,
    "mm": 0.001,
    "ram": 500.0,     # quy ước ngành in
}


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

    # --- validate ------------------------------------------------------------
    def _validate(self, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise DonViDoValidationError("Mã đơn vị không được trống.")
        if not (data.get("ten") or "").strip():
            raise DonViDoValidationError("Tên đơn vị không được trống.")
        hs = data.get("he_so_goc")
        if hs is not None and float(hs) <= 0:
            raise DonViDoValidationError("Hệ số về đơn vị gốc phải > 0.")

    @staticmethod
    def _chuan_hoa(data: dict) -> dict:
        """Họ về `strip().lower()` — hai lần gõ cùng nghĩa phải ra CÙNG một họ, vì khác họ nghĩa là
        'không đổi được cho nhau'."""
        out = dict(data)
        if out.get("ho"):
            out["ho"] = str(out["ho"]).strip().lower()
        return out

    def canh_bao(self, obj) -> list[str]:
        """Cảnh báo mềm cho 1 dòng — hiện ở màn khai, KHÔNG chặn lưu."""
        out: list[str] = []
        chuan = CHUAN_VAT_LY.get((obj.ma or "").strip().lower())
        hs = float(obj.he_so_goc or 0)
        if chuan is not None and abs(hs - chuan) > 1e-9:
            out.append(
                f"Hệ số {hs:g} lệch chuẩn thông dụng ({chuan:g}) — kiểm lại kẻo lệch tiền."
            )
        cung_ho = [d for d in self.repo.all_active() if (d.ho or "") == (obj.ho or "")]
        if cung_ho and not any(abs(float(d.he_so_goc or 0) - 1.0) < 1e-9 for d in cung_ho):
            out.append(
                f"Họ '{obj.ho}' chưa có đơn vị gốc (hệ số = 1) — cả họ này chưa đổi được."
            )
        return out

    # --- reads ---------------------------------------------------------------
    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise DonViDoNotFound("Không tìm thấy đơn vị.")
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def ho_goi_y(self) -> list[str]:
        """Họ gợi ý = bộ mồi ∪ họ nhà máy đã dùng (giống cách gợi ý đơn vị của Lương khoán)."""
        return sorted({*HO_GOI_Y, *self.repo.distinct_ho()})

    # --- writes --------------------------------------------------------------
    def create(self, data: dict, actor_id: int | None = None):
        data = self._chuan_hoa(data)
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise DonViDoDuplicate("Mã đơn vị đã tồn tại.")
        data.setdefault("hieu_luc_tu", date.today())
        obj = self.repo.create(data)
        self._log(actor_id, "create_don_vi", obj, f"Thêm đơn vị {obj.ma} ({obj.ten})")
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        data = self._chuan_hoa(data)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != obj.id:
            raise DonViDoDuplicate("Mã đơn vị đã tồn tại.")
        hs_cu = float(obj.he_so_goc or 0)
        hs_moi = float(data.get("he_so_goc", hs_cu) or 0)
        if abs(hs_moi - hs_cu) > 1e-9:
            # Đổi hệ số = đổi tiền từ nay về sau → ghim mốc hiệu lực nếu caller không nói rõ.
            data.setdefault("hieu_luc_tu", date.today())
        obj = self.repo.update(obj, data)
        chi_tiet = f"Sửa đơn vị {obj.ma}"
        if abs(hs_moi - hs_cu) > 1e-9:
            chi_tiet += f" — hệ số {hs_cu:g} → {hs_moi:g} (hiệu lực {obj.hieu_luc_tu})"
        self._log(actor_id, "update_don_vi", obj, chi_tiet)
        return obj

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        self._log(actor_id, "delete_don_vi", obj, f"Xoá đơn vị {obj.ma}")
        self.repo.delete(obj)

    def _log(self, actor_id: int | None, action: str, obj, detail: str) -> None:
        if self.audit is None:
            return
        self.audit.create(
            actor_user_id=actor_id, action=action, target=f"don_vi_do:{obj.id}", detail=detail,
        )
