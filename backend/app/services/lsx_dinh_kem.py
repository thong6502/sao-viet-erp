"""Tệp đính kèm của lệnh sản xuất — maket, file in, mẫu khách duyệt, ảnh tham khảo.

Luật (chốt 15/09/2026):
  - Thêm/xoá được ở MỌI trạng thái lệnh, kể cả sau phát hành: xưởng nhận thêm maket giữa chừng là
    chuyện thường. Chỉ khoá khi ĐƠN đã huỷ — khi đó danh sách vẫn xem được.
  - Mỗi tệp tối đa `MAX_BYTES`. Không giới hạn số tệp trên một lệnh.
  - Chặn tệp CHẠY ĐƯỢC. Tệp đi xuống xưởng qua máy tính dùng chung; nhận `.exe` ở đây là mở đường
    cho ai đó bấm nhầm. Nội dung có thể chứa script (`.html`, `.svg`) KHÔNG chặn — thiết kế hay gửi
    `.svg` — mà để `/api/files` ép tải về thay vì mở trong trình duyệt.
  - Người tải lấy từ tài khoản đang đăng nhập. Mỗi lần thêm/xoá ghi audit `lsx:{id}` ⇒ tab Nhật ký.

Thứ tự ghi: kho file TRƯỚC, DB SAU. DB gãy thì xoá object vừa ghi — ngược lại (DB trước) thì một lần
kho file lỗi để lại dòng trỏ vào tệp không tồn tại, người xem bấm vào chỉ thấy 404.
"""
from __future__ import annotations

from pathlib import PurePath

from sqlalchemy.orm import Session

from ..models.lsx import Lsx, LsxDinhKem
from ..models.order import STATUS_CANCELLED, Order
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.lsx_dinh_kem_repo import LsxDinhKemRepository
from ..storage import get_storage, key_from_url, make_key, url_from_key
from .lsx_service import LsxConflict, LsxNotFound, LsxValidationError

MAX_BYTES = 50 * 1024 * 1024
THU_MUC = "san-xuat/lsx"

# Đuôi tệp chạy được trên Windows/máy xưởng. Danh sách CHẶN chứ không phải danh sách CHO: định dạng
# thiết kế của nghề in quá nhiều (.ai .cdr .psd .indd .eps .tif .zip .rar…) để liệt kê hết.
DUOI_BI_CHAN = frozenset({
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif", ".cpl", ".dll",
    ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".jar", ".sh", ".lnk",
})


class TepQuaLon(Exception):
    """Vượt `MAX_BYTES` — router trả 413."""


class TepBiChan(Exception):
    """Đuôi tệp chạy được — router trả 415."""


def _khoa_neu_don_huy(db: Session, lsx: Lsx, viec: str) -> None:
    order = db.get(Order, lsx.order_id)
    if order is not None and order.status == STATUS_CANCELLED:
        raise LsxConflict(f"Đơn đã hủy — không {viec} tệp đính kèm được")


def kiem_tep(ten: str | None, kich_thuoc: int) -> None:
    """Chặn trước khi chạm kho file. `kich_thuoc` là số byte đã đọc (router đọc tối đa MAX+1)."""
    if kich_thuoc == 0:
        raise LsxValidationError("Tệp rỗng")
    if kich_thuoc > MAX_BYTES:
        raise TepQuaLon(f"Tệp vượt quá {MAX_BYTES // (1024 * 1024)}MB")
    if PurePath((ten or "").replace("\\", "/")).suffix.lower() in DUOI_BI_CHAN:
        raise TepBiChan("Không nhận tệp chạy được (.exe, .bat, .ps1…)")


class LsxDinhKemService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = LsxDinhKemRepository(db)
        self.audit = AuditLogRepository(db)

    def danh_sach(self, lsx: Lsx) -> list[dict]:
        rows = self.repo.list_by_lsx(lsx.id)
        ten = self.repo.ten_nguoi({r.nguoi_tai_id for r in rows if r.nguoi_tai_id})
        return [self._dict(r, ten.get(r.nguoi_tai_id)) for r in rows]

    def them(self, lsx: Lsx, *, actor, ten_goc: str | None, data: bytes,
             content_type: str | None) -> dict:
        _khoa_neu_don_huy(self.db, lsx, "thêm")
        kiem_tep(ten_goc, len(data))
        key, ten = make_key(THU_MUC, lsx.id, ten_goc)
        kho = get_storage()
        kho.save(key, data, content_type)
        try:
            row = self.repo.add(LsxDinhKem(
                lsx_id=lsx.id, ten_tep=ten, file_url=url_from_key(key),
                content_type=(content_type or None), kich_thuoc=len(data), nguoi_tai_id=actor.id,
            ))
            self.audit.create(
                actor_user_id=actor.id, action="lsx_dinh_kem_them", target=f"lsx:{lsx.id}",
                detail=f"Lệnh {lsx.ma}: đính kèm tệp “{ten}”", commit=False,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            kho.delete(key)
            raise
        return self._dict(row, actor.name)

    def xoa(self, lsx: Lsx, *, dinh_kem_id: int, actor) -> None:
        _khoa_neu_don_huy(self.db, lsx, "xoá")
        row = self.repo.get(dinh_kem_id)
        if row is None or row.lsx_id != lsx.id:
            raise LsxNotFound("Không tìm thấy tệp đính kèm")
        url, ten = row.file_url, row.ten_tep
        self.repo.delete(row)
        self.audit.create(
            actor_user_id=actor.id, action="lsx_dinh_kem_xoa", target=f"lsx:{lsx.id}",
            detail=f"Lệnh {lsx.ma}: xoá tệp đính kèm “{ten}”", commit=False,
        )
        self.db.commit()
        # Dọn SAU commit: xoá object trước mà commit gãy thì dòng còn đó trỏ vào tệp đã mất.
        don_kho([url])

    def urls_cua_lenh(self, lsx_id: int) -> list[str]:
        return self.repo.urls_by_lsx(lsx_id)

    @staticmethod
    def _dict(r: LsxDinhKem, nguoi_tai_ten: str | None) -> dict:
        return {
            "id": r.id, "ten_tep": r.ten_tep, "file_url": r.file_url, "content_type": r.content_type,
            "kich_thuoc": r.kich_thuoc, "nguoi_tai_ten": nguoi_tai_ten, "tai_luc": r.tai_luc,
        }


def don_kho(urls: list[str]) -> None:
    """Xoá object trong kho file — best-effort, `Storage.delete` không raise."""
    kho = get_storage()
    for url in urls:
        key = key_from_url(url)
        if key:
            kho.delete(key)
