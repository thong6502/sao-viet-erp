"""Repository — Danh mục Tiêu chí KCS. CRUD + thay trọn bộ công đoạn áp dụng."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.cong_doan import CongDoan
from ..models.san_xuat_kcs import SanXuatKcsTieuChi, SanXuatKcsTieuChiCongDoan
from .catalog_base import CatalogRepo


class SanXuatKcsTieuChiRepository(CatalogRepo):
    model = SanXuatKcsTieuChi
    fields = ("ten", "huong_dan", "bat_buoc", "thu_tu", "active")
    ma_case = "upper"       # đúng quy ước bu_hao/kho_hang/khuon_be
    ma_prefix = None        # mã khai tay, giống bu_hao — không tự sinh

    def _base_select(self):
        return select(SanXuatKcsTieuChi).options(selectinload(SanXuatKcsTieuChi.cong_doan_links))

    def cong_doan_ids_ton_tai(self, ids: set[int]) -> set[int]:
        """Tập id công đoạn CÓ THẬT trong `ids` — service dùng để chặn gắn tiêu chí vào id ma."""
        if not ids:
            return set()
        return {i for (i,) in self.db.execute(
            select(CongDoan.id).where(CongDoan.id.in_(ids))
        ).all()}

    def _sau_gan(self, obj, data: dict) -> None:
        # BẮT BUỘC canh khoá CÓ MẶT trong `data`, không phải giá trị của nó: `CatalogRepo.update()`
        # gọi `_sau_gan` VÔ ĐIỀU KIỆN trên mọi update — kể cả PATCH .../active (bật/tắt "Ngừng
        # dùng") chỉ gửi `{"active": bool}` một khoá duy nhất. Trước bản vá này, thiếu khoá bị đọc
        # thành "người dùng muốn xoá trọn hết công đoạn" (`data.get(...) or []` ⇒ `[]`) nên bấm
        # Ngừng dùng/Bật lại xoá sạch `cong_doan_ids` đang gắn — phát hiện khi xác minh UI thật
        # (Fix round 1, Task 3, xem task-3-report.md). Form tạo/sửa qua CatalogDrawer luôn gửi
        # khoá này (kể cả rỗng `[]`, xem CatalogDrawer.tsx submit() dòng ~333) nên guard này không
        # ảnh hưởng nhánh tạo/sửa bình thường.
        if "cong_doan_ids" in data:
            self._replace_cong_doan_links(obj, data.get("cong_doan_ids") or [])

    def _replace_cong_doan_links(self, obj, cong_doan_ids: list[int]) -> None:
        # BẮT BUỘC clear() + flush() TRƯỚC khi thêm lại — giống hệt lý do ở
        # CongDoanRepository._replace_dinh_muc (cong_doan_repo.py:134-141): trong MỘT flush,
        # SQLAlchemy phát INSERT trước DELETE cho cùng bảng → giữ nguyên một cặp cũ là đụng
        # UniqueConstraint("tieu_chi_id", "cong_doan_id") → 500.
        if obj.cong_doan_links:
            obj.cong_doan_links.clear()
            if obj.id is not None:
                self.db.flush()
        seen = set()
        for cid in cong_doan_ids:
            cid = int(cid)
            if cid in seen:
                continue
            seen.add(cid)
            obj.cong_doan_links.append(SanXuatKcsTieuChiCongDoan(cong_doan_id=cid))
