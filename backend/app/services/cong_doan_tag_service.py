"""Service nhãn công đoạn — bản sao NGUYÊN LỐI của phần nhãn trong `customer_service`.

Khác biệt duy nhất: "khách" → "một bước" (cặp `buoc_loai`, `buoc_id`). Mọi luật mềm giữ y hệt:
  · thêm/gán nhãn trùng (case-insensitive) → trả nhãn cũ, KHÔNG lỗi, KHÔNG đẻ đúp;
  · nhãn gõ tay tại chỗ cũng VÀO KHO, không thì sớm muộn ra hai biến thể;
  · xoá nhãn khỏi kho KHÔNG bị chặn — nhãn là ghi chú mềm; màn hình hỏi kèm SỐ BƯỚC thật.
"""
from __future__ import annotations

from ..models.cong_doan_tag import BUOC_LOAI_HOP_LE
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.cong_doan_tag_repo import CongDoanTagRepository


class CongDoanTagValidationError(Exception):
    """Dữ liệu nhãn không hợp lệ (rỗng / quá dài / loại bước sai)."""


class CongDoanTagNotFound(Exception):
    """Không tìm thấy nhãn / dòng kho."""


class CongDoanTagService:
    def __init__(self, db, repo: CongDoanTagRepository, audit: AuditLogRepository) -> None:
        self.db = db
        self.tags = repo
        self.audit = audit

    @staticmethod
    def _check_loai(buoc_loai: str) -> None:
        if buoc_loai not in BUOC_LOAI_HOP_LE:
            raise CongDoanTagValidationError("Loại bước không hợp lệ.")

    # --- kho nhãn dùng chung -----------------------------------------------------

    def list_kho_nhan(self) -> list[dict]:
        """Kho nhãn + số bước đang mang từng nhãn (để cảnh báo trước khi xoá)."""
        dem = self.tags.dem_buoc_theo_nhan()
        return [
            {"id": r.id, "label": r.label, "so_buoc": dem.get(r.label.strip().lower(), 0)}
            for r in self.tags.list_kho_nhan()
        ]

    def them_nhan_kho(self, *, label: str, actor):
        """Thêm nhãn vào kho. Nhãn đã có (không phân biệt hoa-thường) → trả nhãn cũ, không lỗi."""
        label = (label or "").strip()
        if not label:
            raise CongDoanTagValidationError("Nhãn không được để trống.")
        if len(label) > 50:
            raise CongDoanTagValidationError("Nhãn tối đa 50 ký tự.")
        san_co = self.tags.tim_nhan_kho(label)
        if san_co is not None:
            return san_co
        row = self.tags.them_nhan_kho(label=label, created_by=actor.id)
        self.audit.create(
            actor_user_id=actor.id, action="update_cong_doan_tag",
            target="cong_doan:kho_nhan", detail=f"Thêm nhãn vào kho: {label}",
        )
        return row

    def xoa_nhan_kho(self, *, nhan_id: int, actor) -> int:
        """Xoá nhãn khỏi kho + gỡ khỏi mọi bước đang mang. Trả số bước bị gỡ. KHÔNG chặn."""
        row = self.tags.get_nhan_kho(nhan_id)
        if row is None:
            raise CongDoanTagNotFound("Không tìm thấy nhãn.")
        label = row.label
        so_buoc = self.tags.xoa_nhan_kho(row)
        self.audit.create(
            actor_user_id=actor.id, action="update_cong_doan_tag",
            target="cong_doan:kho_nhan",
            detail=f"Xoá nhãn khỏi kho: {label} (gỡ khỏi {so_buoc} bước)",
        )
        return so_buoc

    # --- nhãn đã gán cho bước -----------------------------------------------------

    def list_tags(self, *, buoc_loai: str, buoc_id: int):
        self._check_loai(buoc_loai)
        return self.tags.list_tags(buoc_loai, buoc_id)

    def add_tag(self, *, buoc_loai: str, buoc_id: int, actor, label: str):
        """Gán nhãn. Nhãn trùng (case-insensitive) trên cùng bước → trả nhãn có sẵn, không lỗi."""
        self._check_loai(buoc_loai)
        label = " ".join((label or "").strip().split())
        if not label:
            raise CongDoanTagValidationError("Nhãn không được để trống.")
        if len(label) > 50:
            raise CongDoanTagValidationError("Nhãn tối đa 50 ký tự.")
        existing = self.tags.find_tag_by_label(buoc_loai, buoc_id, label)
        if existing is not None:
            return existing
        # Nhãn gõ tay tại chỗ cũng phải VÀO KHO (cùng lối `customer_service.add_tag`).
        if self.tags.tim_nhan_kho(label) is None:
            self.tags.them_nhan_kho(label=label, created_by=actor.id)
        tag = self.tags.add_tag(buoc_loai, buoc_id, label=label, created_by=actor.id)
        self.audit.create(
            actor_user_id=actor.id, action="update_cong_doan_tag",
            target=f"cong_doan:{buoc_loai}:{buoc_id}", detail=f"Gán nhãn: {label}",
        )
        return tag

    def remove_tag(self, *, buoc_loai: str, buoc_id: int, tag_id: int, actor) -> None:
        self._check_loai(buoc_loai)
        tag = self.tags.get_tag(tag_id)
        if tag is None or tag.buoc_loai != buoc_loai or tag.buoc_id != buoc_id:
            raise CongDoanTagNotFound("Không tìm thấy nhãn.")
        self.tags.delete_tag(tag)
        self.audit.create(
            actor_user_id=actor.id, action="update_cong_doan_tag",
            target=f"cong_doan:{buoc_loai}:{buoc_id}", detail=f"Gỡ nhãn: {tag.label}",
        )
