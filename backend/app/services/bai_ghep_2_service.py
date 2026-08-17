"""Bài ghép 2 dùng chung engine/bảng, chỉ nới điều kiện ứng viên và thêm metadata quản trị."""
from __future__ import annotations

from ..models.lsx import TT_CHO_BO_SUNG, TT_NHAP, TT_SAN_SANG, Lsx
from .bai_ghep_service import (
    BaiGhepConflict,
    BaiGhepService,
    BaiGhepValidationError,
)
from .thanh_phan_engine import la_gap_tay, so_tay_moi_cuon


class BaiGhep2Service(BaiGhepService):
    _SUA_DUOC_BAI = BaiGhepService._SUA_DUOC_BAI + (
        "ten", "han_hoan_thanh_sx", "is_rush", "nguoi_phu_trach_id",
    )
    _TRANG_THAI_HANG_CHO = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)

    def hang_cho_ghep(self, *, giay_id: int | None = None, q: str | None = None) -> dict:
        # BG2 cố ý không dùng giấy làm điều kiện/bộ lọc; giữ tham số để HTTP contract tương đương.
        return super().hang_cho_ghep(giay_id=None, q=q)

    def _la_sach_khong_ghep_duoc(self, quy_cach: dict | None) -> bool:
        if not la_gap_tay(quy_cach):
            return False
        qc = quy_cach or {}
        return so_tay_moi_cuon(
            trang_moi_tay=qc.get("trang_moi_tay"), so_trang=qc.get("so_trang"),
        ) > 1

    def _validate_them(self, lsx_ids: list[int], lsx_map: dict[int, Lsx]) -> None:
        for lsx_id in lsx_ids:
            lsx = lsx_map.get(lsx_id)
            if lsx is None:
                raise BaiGhepValidationError(f"LSX #{lsx_id} không tồn tại")
            if lsx.trang_thai not in self._TRANG_THAI_HANG_CHO:
                raise BaiGhepValidationError(f"LSX {lsx.ma} đã lập kế hoạch hoặc phát hành")
            if self._la_sach_khong_ghep_duoc(lsx.quy_cach_json):
                tay = so_tay_moi_cuon(
                    trang_moi_tay=(lsx.quy_cach_json or {}).get("trang_moi_tay"),
                    so_trang=(lsx.quy_cach_json or {}).get("so_trang"),
                )
                raise BaiGhepValidationError(
                    f"LSX {lsx.ma} là sách gấp tay ({tay} tay/cuốn) nên không vào Bài ghép 2"
                )
        if self.repo.lsx_da_ghep(lsx_ids):
            raise BaiGhepConflict("Có LSX đã thuộc bài ghép khác - gỡ khỏi bài đó trước")

    def tao(self, *, lsx_ids: list[int], actor):
        ids = list(dict.fromkeys(int(i) for i in lsx_ids if i))
        if len(ids) < 2:
            raise BaiGhepValidationError("Chọn ít nhất 2 LSX để tạo Bài ghép 2")
        return super().tao(lsx_ids=ids, actor=actor)

    def nguoi_phu_trach_options(self) -> list[dict]:
        return [{"id": user.id, "ten": user.name} for user in self.repo.nguoi_phu_trach_options()]

    def list_rows(self) -> list[dict]:
        rows = super().list_rows()
        names = self.repo.user_names({r["nguoi_phu_trach_id"] for r in rows if r["nguoi_phu_trach_id"]})
        for row in rows:
            row["nguoi_phu_trach_ten"] = names.get(row["nguoi_phu_trach_id"])
        return rows

    def detail_dict(self, bg) -> dict:
        row = super().detail_dict(bg)
        names = self.repo.user_names({bg.nguoi_phu_trach_id} if bg.nguoi_phu_trach_id else set())
        row["nguoi_phu_trach_ten"] = names.get(bg.nguoi_phu_trach_id)
        return row
