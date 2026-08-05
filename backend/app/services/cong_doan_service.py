"""Công đoạn — service: CRUD + validate (§8)."""
from __future__ import annotations

from ..models.cong_doan import (
    CAP_DON_VI_HOP_LE, CHE_DO_TINH, DON_VI_DONG_GIAY, KIEU_BU_HAO, NHOM, PRICING_BASIS,
    TOOLING_TYPE, CongDoan,
)
from ..repositories.cong_doan_repo import CongDoanRepository


class CongDoanError(Exception):
    pass


class CongDoanValidationError(CongDoanError):
    pass


class CongDoanDuplicate(CongDoanError):
    pass


class CongDoanNotFound(CongDoanError):
    pass


class CongDoanService:
    def __init__(self, repo: CongDoanRepository) -> None:
        self.repo = repo

    def _validate(self, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise CongDoanValidationError("Mã công đoạn không được trống.")
        if not (data.get("ten") or "").strip():
            raise CongDoanValidationError("Tên công đoạn không được trống.")
        if data.get("nhom") not in NHOM:
            raise CongDoanValidationError("Nhóm công đoạn không hợp lệ.")
        dinh_muc = data.get("dau_viec_dinh_muc") or []
        if dinh_muc:
            if data.get("department_id") is None:
                raise CongDoanValidationError("Muốn khai định mức đầu việc phải chọn tổ phụ trách.")
            ids = [int(r.get("piece_rate_id") or 0) for r in dinh_muc]
            if len(ids) != len(set(ids)):
                raise CongDoanValidationError("Một đầu việc không được chọn trùng.")
            if sum(bool(r.get("is_default")) for r in dinh_muc) > 1:
                raise CongDoanValidationError("Mỗi công đoạn chỉ có một đầu việc mặc định.")
            rates = self.repo.piece_rates(set(ids))
            for r in dinh_muc:
                rid = int(r.get("piece_rate_id") or 0)
                rate = rates.get(rid)
                if rate is None or not rate.is_active:
                    raise CongDoanValidationError("Đầu việc không tồn tại hoặc đã ngừng dùng.")
                if rate.department_id != data.get("department_id"):
                    raise CongDoanValidationError("Đầu việc phải thuộc đúng tổ phụ trách.")
                ns = float(r.get("nang_suat_nguoi_gio") or 0)
                tt = int(r.get("so_nguoi_toi_thieu") or 1)
                tc = int(r.get("so_nguoi_tieu_chuan") or 0)
                td = int(r.get("so_nguoi_toi_da") or 0)
                if ns <= 0:
                    raise CongDoanValidationError("Năng suất một người phải lớn hơn 0.")
                if tt < 1 or tc < tt or td < tc:
                    raise CongDoanValidationError(
                        "Số người phải thỏa 1 ≤ tối thiểu ≤ tiêu chuẩn ≤ tối đa.")
                # Dải năng suất: khai mức nào thì mức đó phải đứng đúng phía của trung bình, không
                # thì "nhanh nhất" ra dài hơn "chậm nhất" và râu Gantt vẽ ngược.
                ns_min = r.get("nang_suat_nguoi_gio_min")
                ns_max = r.get("nang_suat_nguoi_gio_max")
                if ns_min is not None and float(ns_min) > ns:
                    raise CongDoanValidationError(
                        "Năng suất tối thiểu không được lớn hơn năng suất trung bình.")
                if ns_max is not None and float(ns_max) < ns:
                    raise CongDoanValidationError(
                        "Năng suất tối đa không được nhỏ hơn năng suất trung bình.")
        che_do = data.get("che_do_tinh", "theo_san_luong")
        if che_do not in CHE_DO_TINH:
            raise CongDoanValidationError("Chế độ tính không hợp lệ.")
        if data.get("pricing_basis") not in PRICING_BASIS:
            raise CongDoanValidationError("Tính theo sản lượng cần pricing_basis hợp lệ. [E-CD-BASIS]")
        if data.get("tooling_type") not in (None, "") and data["tooling_type"] not in TOOLING_TYPE:
            raise CongDoanValidationError("Loại khuôn/kẽm không hợp lệ.")
        if data.get("kieu_bu_hao", "khong") not in KIEU_BU_HAO:
            raise CongDoanValidationError("Kiểu bù hao không hợp lệ. [E-CD-BUHAO]")
        # Đơn vị vào/ra: TRỐNG = bước không chạm giấy (chế bản) → engine loại khỏi dòng giấy.
        # Khai thì phải khai CẢ HAI, và đúng chiều — dòng giấy chảy một chiều tờ nguyên → tờ in →
        # tờ thành phẩm, nên `cai → to` hay nhảy cóc là vô nghĩa.
        dv_vao = (data.get("don_vi_vao") or "").strip() or None
        dv_ra = (data.get("don_vi_ra") or "").strip() or None
        data["don_vi_vao"], data["don_vi_ra"] = dv_vao, dv_ra
        if (dv_vao is None) != (dv_ra is None):
            raise CongDoanValidationError(
                "Đơn vị đầu vào và đầu ra phải cùng khai, hoặc cùng để trống. [E-CD-DONVI]")
        if dv_vao is not None:
            if dv_vao not in DON_VI_DONG_GIAY or dv_ra not in DON_VI_DONG_GIAY:
                raise CongDoanValidationError("Đơn vị vào/ra không hợp lệ. [E-CD-DONVI]")
            if (dv_vao, dv_ra) not in CAP_DON_VI_HOP_LE:
                raise CongDoanValidationError(
                    f"Không quy đổi được {dv_vao} → {dv_ra}. Dòng giấy chỉ chảy một chiều: "
                    f"tờ nguyên → tờ in → tờ thành phẩm. [E-CD-DONVI]"
                )
        # W-CD-PRINT-SPOIL: bước in không nên có spoilage (bù hao lấy từ máy) — ép 0.
        if data.get("nhom") == "print" and data.get("spoilage_pct"):
            data["spoilage_pct"] = 0

    def get(self, cd_id: int) -> CongDoan:
        cd = self.repo.get(cd_id)
        if cd is None:
            raise CongDoanNotFound("Không tìm thấy công đoạn.")
        return cd

    def list(self, **kw):
        return self.repo.list(**kw)

    def dau_viec_options(self, department_id: int | None = None) -> list[dict]:
        return [{"id": r.id, "ma": r.code or f"DV-{r.id}", "ten": r.name,
                 "department_id": r.department_id, "don_vi": r.unit,
                 "don_gia": float(r.unit_price)}
                for r in self.repo.piece_rates_active(department_id)]

    def create(self, data: dict) -> CongDoan:
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise CongDoanDuplicate("Mã công đoạn đã tồn tại.")
        return self.repo.create(data)

    def update(self, cd_id: int, data: dict) -> CongDoan:
        cd = self.get(cd_id)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != cd.id:
            raise CongDoanDuplicate("Mã công đoạn đã tồn tại.")
        return self.repo.update(cd, data)

    def delete(self, cd_id: int) -> None:
        self.repo.delete(self.get(cd_id))
