"""Data-access cho lát SẢN LƯỢNG · BÀN GIAO · XÁC NHẬN VẬT TƯ (Giai đoạn 3, §10–§12.1).

Giữ đúng tầng: mọi truy vấn/ghi DB của batch · lot đầu vào · bàn giao · xác nhận vật tư gom ở
đây; các service `services/san_xuat/san_luong.py` · `ban_giao.py` · `vat_tu_nhan.py` chỉ điều phối
+ kiểm luật. Tách khỏi `san_xuat_thuc_thi_repo.py` (phân công/phiên chạy) để mỗi file một mối bận tâm.

Số DẪN XUẤT (sản lượng tốt còn lại, lượng đã bàn giao, lượng công đoạn sau đã dùng) TÍNH LÚC ĐỌC
bằng các hàm tổng ở đây — không cache cột (precedent `lsx_service`/`san_xuat_repo`).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.san_xuat import CV_HOAN_THANH, SanXuatCongViec, SanXuatPhuThuoc
from ..models.san_xuat_ly_do import SanXuatLyDo
from ..models.san_xuat_san_luong import (
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    LOT_TU_BATCH,
    SanXuatBanGiao,
    SanXuatBanGiaoDieuChinh,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
    SanXuatVatTuNhan,
)
from ..models.stock_request import StockRequestLine
from ..models.stock_voucher import (
    VOUCHER_POSTED,
    VOUCHER_XUAT,
    StockVoucher,
    StockVoucherLine,
)


class SanXuatSanLuongRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Ghi ---------------------------------------------------------------------------------
    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    # --- Công việc (đọc lại để gate/nối) -----------------------------------------------------
    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def cong_viec_sau_goi_y(self, cv: SanXuatCongViec) -> list[SanXuatCongViec]:
        """Công việc KHÁC cùng gói phát hành + cùng LSX/bài ghép — GỢI Ý đích bàn giao (§11.2).

        Loại chính nó và các việc đã hoàn thành; nếu công việc hiện tại có giờ dự kiến thì chỉ giữ
        các chặng bắt đầu SAU nó (giao xuôi). Sắp theo giờ dự kiến (chưa có giờ xuống cuối). Tổ
        trưởng chọn đích trong danh sách này — không tự đoán "chặng kế tiếp" duy nhất."""
        stmt = select(SanXuatCongViec).where(
            SanXuatCongViec.goi_id == cv.goi_id,
            SanXuatCongViec.id != cv.id,
            SanXuatCongViec.trang_thai != CV_HOAN_THANH,
        )
        if cv.lsx_id is not None:
            stmt = stmt.where(SanXuatCongViec.lsx_id == cv.lsx_id)
        elif cv.bai_ghep_id is not None:
            stmt = stmt.where(SanXuatCongViec.bai_ghep_id == cv.bai_ghep_id)
        else:
            return []
        rows = list(self.db.scalars(stmt))
        moc = cv.du_kien_bat_dau.timestamp() if cv.du_kien_bat_dau else None
        if moc is not None:
            rows = [
                r for r in rows
                if r.du_kien_bat_dau is None or r.du_kien_bat_dau.timestamp() >= moc
            ]
        rows.sort(key=lambda c: (
            c.du_kien_bat_dau is None,
            c.du_kien_bat_dau.timestamp() if c.du_kien_bat_dau else 0.0,
            c.ten_cong_doan,
        ))
        return rows

    # --- Lý do/lỗi (§15) ---------------------------------------------------------------------
    def ly_do(self, ly_do_id: int) -> SanXuatLyDo | None:
        return self.db.get(SanXuatLyDo, ly_do_id)

    def nhan_ly_do(self, ids: set[int]) -> dict[int, str]:
        """{id: tên} cho nhãn nhóm lỗi/lý do trên drawer (batch hỏng, điều chỉnh bàn giao)."""
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.scalars(select(SanXuatLyDo).where(SanXuatLyDo.id.in_(ids)))
        return {r.id: r.ten for r in rows}

    # --- Batch sản lượng (§11.1) -------------------------------------------------------------
    def batch(self, batch_id: int) -> SanXuatBatch | None:
        return self.db.get(SanXuatBatch, batch_id)

    def cac_batch(self, cong_viec_id: int) -> list[SanXuatBatch]:
        return list(
            self.db.scalars(
                select(SanXuatBatch)
                .where(SanXuatBatch.cong_viec_id == cong_viec_id)
                .order_by(SanXuatBatch.bat_dau, SanXuatBatch.id)
            )
        )

    def tong_tot(self, cong_viec_id: int) -> float:
        """Tổng sản lượng TỐT đã ghi của một công việc (nền cho trần bàn giao §11.2)."""
        return float(
            self.db.scalar(
                select(func.coalesce(func.sum(SanXuatBatch.tot), 0)).where(
                    SanXuatBatch.cong_viec_id == cong_viec_id
                )
            )
            or 0
        )

    def batch_ids_cua(self, cong_viec_id: int) -> list[int]:
        return list(
            self.db.scalars(
                select(SanXuatBatch.id).where(SanXuatBatch.cong_viec_id == cong_viec_id)
            )
        )

    # --- Lot đầu vào (§10.3) -----------------------------------------------------------------
    def lot_vao_cua(self, batch_id: int) -> list[SanXuatBatchLotVao]:
        return list(
            self.db.scalars(
                select(SanXuatBatchLotVao)
                .where(SanXuatBatchLotVao.batch_id == batch_id)
                .order_by(SanXuatBatchLotVao.id)
            )
        )

    def lot_vao_cua_nhieu(self, batch_ids: list[int]) -> dict[int, list[SanXuatBatchLotVao]]:
        if not batch_ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatBatchLotVao)
            .where(SanXuatBatchLotVao.batch_id.in_(batch_ids))
            .order_by(SanXuatBatchLotVao.id)
        )
        out: dict[int, list[SanXuatBatchLotVao]] = {}
        for lot in rows:
            out.setdefault(lot.batch_id, []).append(lot)
        return out

    def da_dung_tu_nguon(self, nguon_cong_viec_id: int, dich_cong_viec_id: int) -> float:
        """Lượng đầu vào mà công đoạn SAU (`dich`) đã tiêu thụ từ đầu ra công đoạn TRƯỚC (`nguon`).

        Đo bằng truy vết lot (§10.3): tổng `so_luong` của các lot đầu vào thuộc batch của `dich`
        mà `nguon_batch_id` trỏ về một batch của `nguon`. Đây là "số lượng công đoạn sau đã sử
        dụng" trong luật không-nhất-quán §11.3.
        """
        nguon_batches = self.batch_ids_cua(nguon_cong_viec_id)
        if not nguon_batches:
            return 0.0
        stmt = (
            select(func.coalesce(func.sum(SanXuatBatchLotVao.so_luong), 0))
            .select_from(SanXuatBatchLotVao)
            .join(SanXuatBatch, SanXuatBatchLotVao.batch_id == SanXuatBatch.id)
            .where(
                SanXuatBatch.cong_viec_id == dich_cong_viec_id,
                SanXuatBatchLotVao.nguon_loai == LOT_TU_BATCH,
                SanXuatBatchLotVao.nguon_batch_id.in_(nguon_batches),
            )
        )
        return float(self.db.scalar(stmt) or 0)

    # --- Bàn giao (§11.2–§11.3) --------------------------------------------------------------
    def ban_giao(self, ban_giao_id: int) -> SanXuatBanGiao | None:
        return self.db.get(SanXuatBanGiao, ban_giao_id)

    def ban_giao_tu_nguon(self, cong_viec_id: int) -> list[SanXuatBanGiao]:
        """Các bàn giao mà công việc này là NGUỒN (giao đi)."""
        return list(
            self.db.scalars(
                select(SanXuatBanGiao)
                .where(SanXuatBanGiao.nguon_cong_viec_id == cong_viec_id)
                .order_by(SanXuatBanGiao.id)
            )
        )

    def ban_giao_toi_dich(self, cong_viec_id: int) -> list[SanXuatBanGiao]:
        """Các bàn giao mà công việc này là ĐÍCH (nhận về)."""
        return list(
            self.db.scalars(
                select(SanXuatBanGiao)
                .where(SanXuatBanGiao.dich_cong_viec_id == cong_viec_id)
                .order_by(SanXuatBanGiao.id)
            )
        )

    def tong_da_giao(self, nguon_cong_viec_id: int) -> float:
        """Tổng số lượng ĐÃ ghi bàn giao từ một nguồn (mọi trạng thái — không có huỷ cứng). Dùng
        để chặn giao vượt sản lượng tốt (§11.2)."""
        return float(
            self.db.scalar(
                select(func.coalesce(func.sum(SanXuatBanGiao.so_luong), 0)).where(
                    SanXuatBanGiao.nguon_cong_viec_id == nguon_cong_viec_id
                )
            )
            or 0
        )

    def co_ban_giao_xac_nhan_duong(self, nguon_cong_viec_id: int, dich_cong_viec_id: int) -> bool:
        """Có bàn giao ĐÃ XÁC NHẬN với số lượng dương từ `nguon` sang `dich` — điều kiện chạy bước
        ghép (§10.2)."""
        row = self.db.scalar(
            select(SanXuatBanGiao.id).where(
                SanXuatBanGiao.nguon_cong_viec_id == nguon_cong_viec_id,
                SanXuatBanGiao.dich_cong_viec_id == dich_cong_viec_id,
                SanXuatBanGiao.trang_thai.in_((BG_XAC_NHAN, BG_DIEU_CHINH)),
                SanXuatBanGiao.so_luong > 0,
            ).limit(1)
        )
        return row is not None

    def dieu_chinh_cua(self, ban_giao_id: int) -> list[SanXuatBanGiaoDieuChinh]:
        return list(
            self.db.scalars(
                select(SanXuatBanGiaoDieuChinh)
                .where(SanXuatBanGiaoDieuChinh.ban_giao_id == ban_giao_id)
                .order_by(SanXuatBanGiaoDieuChinh.id)
            )
        )

    # --- Phụ thuộc chéo (bước ghép) ----------------------------------------------------------
    def canh_phu_thuoc_toi(self, dich_cong_viec_id: int) -> list[SanXuatPhuThuoc]:
        """Các cạnh phụ thuộc chéo ĐỔ VÀO một công việc (nó là đích = bước ghép). Rỗng với công
        việc thường → cổng bước-ghép ở §10.2 là no-op, an toàn cho công việc một nhánh."""
        return list(
            self.db.scalars(
                select(SanXuatPhuThuoc).where(
                    SanXuatPhuThuoc.dich_cong_viec_id == dich_cong_viec_id
                )
            )
        )

    def canh_toa_di_tu(self, nguon_cong_viec_id: int) -> list[SanXuatPhuThuoc]:
        """Cạnh TOẢ xuất phát từ một công việc (nó là điểm toả bài ghép). Rỗng với công việc
        thường → `_toa_san_luong` là no-op, an toàn cho mọi batch không phải điểm toả."""
        return list(
            self.db.scalars(
                select(SanXuatPhuThuoc).where(
                    SanXuatPhuThuoc.nguon_cong_viec_id == nguon_cong_viec_id
                )
            )
        )

    def co_ket_qua_nhanh(self, batch_id: int) -> bool:
        """Batch này có phải điểm toả (đã tách ra ≥1 nhánh LSX) hay không."""
        return self.db.scalar(
            select(SanXuatKetQuaNhanh.id).where(SanXuatKetQuaNhanh.batch_id == batch_id).limit(1)
        ) is not None

    def ket_qua_nhanh_cua(self, batch_id: int, lsx_id: int) -> SanXuatKetQuaNhanh | None:
        """Phần đã toả cho MỘT lsx cụ thể của một batch điểm toả — None nghĩa là lsx đó KHÔNG có
        phần trong batch này (không phải nhánh hợp lệ của điểm toả)."""
        return self.db.scalars(
            select(SanXuatKetQuaNhanh).where(
                SanXuatKetQuaNhanh.batch_id == batch_id, SanXuatKetQuaNhanh.lsx_id == lsx_id
            )
        ).first()

    def ket_qua_nhanh_cua_batch(self, batch_id: int) -> list[SanXuatKetQuaNhanh]:
        return list(
            self.db.scalars(
                select(SanXuatKetQuaNhanh).where(SanXuatKetQuaNhanh.batch_id == batch_id)
            )
        )

    def da_dung_nhanh(self, batch_id: int, lsx_id: int) -> float:
        """Tổng số lượng LSX này đã LẤY từ batch điểm-toả `batch_id` qua các lot đầu vào (§10.3) —
        cộng dồn mọi batch của LSX đó có lot trỏ về `batch_id`."""
        tong = self.db.scalar(
            select(func.coalesce(func.sum(SanXuatBatchLotVao.so_luong), 0))
            .select_from(SanXuatBatchLotVao)
            .join(SanXuatBatch, SanXuatBatch.id == SanXuatBatchLotVao.batch_id)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatBatch.cong_viec_id)
            .where(
                SanXuatBatchLotVao.nguon_batch_id == batch_id,
                SanXuatCongViec.lsx_id == lsx_id,
            )
        )
        return float(tong or 0)

    # --- Xác nhận vật tư (§10.1) -------------------------------------------------------------
    def voucher(self, voucher_id: int) -> StockVoucher | None:
        return self.db.get(StockVoucher, voucher_id)

    def vat_tu_nhan_cua_voucher(self, voucher_id: int) -> SanXuatVatTuNhan | None:
        return self.db.scalars(
            select(SanXuatVatTuNhan).where(SanXuatVatTuNhan.voucher_id == voucher_id)
        ).first()

    def voucher_xuat_cua_lsx(self, lsx_id: int) -> list[StockVoucher]:
        """Phiếu XUẤT ĐÃ GHI SỔ cấp cho một LSX (join phiếu → dòng phiếu → dòng yêu cầu.lsx_id).

        Đây là danh sách tổ trưởng thấy để XÁC NHẬN đã nhận (§10.1). DISTINCT vì một phiếu nhiều
        dòng cùng trỏ một LSX."""
        if not lsx_id:
            return []
        return list(
            self.db.scalars(
                select(StockVoucher)
                .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
                .join(
                    StockRequestLine,
                    StockVoucherLine.request_line_id == StockRequestLine.id,
                )
                .where(
                    StockVoucher.loai == VOUCHER_XUAT,
                    StockVoucher.trang_thai == VOUCHER_POSTED,
                    StockRequestLine.lsx_id == lsx_id,
                )
                .distinct()
                .order_by(StockVoucher.id)
            )
        )

    def nhan_theo_voucher_ids(self, voucher_ids: list[int]) -> dict[int, SanXuatVatTuNhan]:
        """{voucher_id: bản xác nhận} cho một tập phiếu — để đánh dấu phiếu nào tổ đã nhận."""
        if not voucher_ids:
            return {}
        rows = self.db.scalars(
            select(SanXuatVatTuNhan).where(SanXuatVatTuNhan.voucher_id.in_(voucher_ids))
        )
        return {r.voucher_id: r for r in rows}
