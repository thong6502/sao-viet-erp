"""Repository khóa sổ kỳ kế toán công nợ (chốt công nợ) — đồng nhất với kho_khoa_so_repo."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.cong_no_khoa_so import CongNoKhoaSo, CongNoKyChot


class CongNoKhoaSoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _thuoc_phan_he(row, phan_he: str | None) -> bool:
        """Bản ghi này có áp cho phân hệ đang hỏi không?

        `row.phan_he IS NULL` = bản ghi CŨ, sinh trước khi tách phân hệ (04/09/2026) ⇒ nó khoá CẢ
        HAI sổ, nên áp cho mọi phân hệ. Hỏi mà không nêu phân hệ (`phan_he=None`) thì lấy tất —
        dùng cho màn lịch sử.
        """
        return phan_he is None or row.phan_he is None or row.phan_he == phan_he

    def is_locked(self, ngay: date, phan_he: str | None = None) -> bool:
        """Ngày `ngay` có đang khóa cho phân hệ đó? Bản ghi mới nhất phủ ngày đó quyết định."""
        rows = self.db.execute(
            select(CongNoKhoaSo)
            .where(CongNoKhoaSo.tu_ngay <= ngay, CongNoKhoaSo.den_ngay >= ngay)
            .order_by(CongNoKhoaSo.id.desc())
        ).scalars().all()
        for r in rows:
            if self._thuoc_phan_he(r, phan_he):
                return r.hanh_dong == "khoa"
        return False

    def ngay_bi_khoa(
        self, tu_ngay: date, den_ngay: date, phan_he: str | None = None
    ) -> set[date]:
        """Tập NGÀY đang bị khóa trong khoảng — nền của mọi câu hỏi về trạng thái kỳ.

        `is_locked` chỉ trả lời cho MỘT ngày. Hỏi nó bằng ngày cuối kỳ rồi kết luận cho cả kỳ là
        sai theo CẢ HAI chiều, và bug 04/09/2026 dính đúng cả hai:

          • Khóa 01/09–03/09 rồi hỏi `is_locked(30/09)` ⇒ False ⇒ màn hình báo "chưa khóa", người
            dùng bấm khóa lại bốn lần mà không hiểu vì sao (log #2 #3 #4 #6 trên DB dev).
          • Ngược lại, bản ghi khóa 03/07–03/09 làm `is_locked(31/07)` = True ⇒ tháng 7 hiện "đã
            khóa" trong khi 01/07 và 02/07 vẫn mở toang. Cái này NGUY HIỂM HƠN: nó nói dối rằng sổ
            đã chốt.

        Nạp toàn bộ log MỘT LẦN rồi duyệt trong Python: bảng này chỉ vài chục dòng, còn khoảng hỏi
        nhiều nhất là một năm — rẻ hơn hẳn 365 lượt đi DB.
        """
        rows = list(
            self.db.execute(
                select(CongNoKhoaSo).order_by(CongNoKhoaSo.id.desc())
            ).scalars()
        )
        ra: set[date] = set()
        ngay = tu_ngay
        while ngay <= den_ngay:
            # Bản ghi MỚI NHẤT phủ ngày này quyết định — 'mo' ghi sau đè 'khoa' ghi trước.
            for r in rows:
                if r.tu_ngay <= ngay <= r.den_ngay and self._thuoc_phan_he(r, phan_he):
                    if r.hanh_dong == "khoa":
                        ra.add(ngay)
                    break
            ngay += timedelta(days=1)
        return ra

    def khoa_ca_khoang(
        self, tu_ngay: date, den_ngay: date, phan_he: str | None = None
    ) -> tuple[bool, bool]:
        """`(khóa trọn, khóa một phần)` cho khoảng `[tu_ngay, den_ngay]`.

        Ba trạng thái, không phải hai: chưa khóa · khóa MỘT PHẦN · khóa trọn. Gộp "một phần" vào
        "chưa khóa" là giấu mất chuyện nửa kỳ đã chốt — mà đó đúng là lúc kế toán cần biết nhất.
        """
        if den_ngay < tu_ngay:
            return (False, False)
        bi_khoa = self.ngay_bi_khoa(tu_ngay, den_ngay, phan_he)
        tong = (den_ngay - tu_ngay).days + 1
        return (len(bi_khoa) == tong, 0 < len(bi_khoa) < tong)

    def add_log(
        self,
        *,
        phan_he: str | None = None,
        tu_ngay: date,
        den_ngay: date,
        hanh_dong: str,
        nguoi_khoa_id: int | None,
        ten: str | None = None,
    ) -> CongNoKhoaSo:
        row = CongNoKhoaSo(
            phan_he=phan_he,
            tu_ngay=tu_ngay,
            den_ngay=den_ngay,
            hanh_dong=hanh_dong,
            nguoi_khoa_id=nguoi_khoa_id,
            ten=ten,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def history(
        self, limit: int = 100, phan_he: str | None = None
    ) -> Sequence[CongNoKhoaSo]:
        rows = self.db.execute(
            select(CongNoKhoaSo).order_by(CongNoKhoaSo.id.desc())
        ).scalars().all()
        giu = [r for r in rows if self._thuoc_phan_he(r, phan_he)]
        return giu[:limit]

    def delete_snapshots(
        self, tu_ngay: date, den_ngay: date, phan_he: str | None = None
    ) -> None:
        """Khi mở khóa kỳ -> xóa các snapshot của kỳ đó để tính lại khi chốt.

        Có `phan_he` thì chỉ xoá snapshot của phân hệ đó — mở sổ phải trả không được thổi bay
        snapshot của sổ phải thu (lỗi 04/09/2026).
        """
        dk = [CongNoKyChot.tu_ngay == tu_ngay, CongNoKyChot.den_ngay == den_ngay]
        if phan_he is not None:
            dk.append(CongNoKyChot.phan_he == phan_he)
        stmt = delete(CongNoKyChot).where(*dk)
        self.db.execute(stmt)
        self.db.commit()

    def save_snapshots(self, items: list[CongNoKyChot]) -> None:
        """Lưu snapshot công nợ chi tiết các đơn/đợt giao khi chốt kỳ."""
        self.db.add_all(items)
        self.db.commit()

    def get_snapshots(
        self,
        phan_he: str,
        den_ngay: date,
        doi_tuong_id: int | None = None,
    ) -> Sequence[CongNoKyChot]:
        stmt = select(CongNoKyChot).where(
            CongNoKyChot.phan_he == phan_he,
            CongNoKyChot.den_ngay == den_ngay,
        )
        if doi_tuong_id is not None:
            stmt = stmt.where(CongNoKyChot.doi_tuong_id == doi_tuong_id)
        return self.db.execute(stmt).scalars().all()
