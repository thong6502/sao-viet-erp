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

from ..models.bai_ghep_cong_doan import BaiGhepCongDoanMap
from ..models.lsx import LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.san_xuat import SanXuatCongViec, SanXuatPhuThuoc
from ..models.san_xuat_san_luong import (
    BG_DE_XUAT,
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    SanXuatBanGiao,
    SanXuatBanGiaoBatch,
    SanXuatBanGiaoDieuChinh,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
    SanXuatVatTuNhan,
)
from ..models.san_xuat_vat_tu import SanXuatVatTuDeNghi
from ..models.stock_request import StockRequest, StockRequestLine
from ..models.stock_voucher import (
    VOUCHER_POSTED,
    VOUCHER_XUAT,
    StockVoucher,
    StockVoucherLine,
)
from ..models.vat_lieu_kho import HANG_GIAY, HANG_VAT_TU, GiayNguyen, VatTuInAn


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

    def cong_viec_nhieu(self, ids) -> dict[int, SanXuatCongViec]:
        """`{id: công việc}` — MỘT truy vấn cho cả tập (vòng sửa 1, Minor 4: N+1 hình dạng ở
        `board.chi_tiet_cong_viec`'s `doi_tac_map`, quy mô nhỏ — 0-5 đối tác bàn giao mỗi công
        đoạn — nhưng rẻ để gộp theo đúng khuôn `*_nhieu` Task 7 đã dựng). Rỗng ⇒ `{}` mà không
        chạm DB."""
        ids = [i for i in set(ids) if i]
        if not ids:
            return {}
        rows = self.db.scalars(select(SanXuatCongViec).where(SanXuatCongViec.id.in_(ids)))
        return {r.id: r for r in rows}

    def cong_viec_chang_sau(self, cv: SanXuatCongViec) -> list[SanXuatCongViec]:
        """Công việc của CHẶNG SAU theo routing lệnh — đích bàn giao DUY NHẤT hợp lệ (§11.2).

        Lệnh nào cũng đã khai chuỗi công đoạn, nên đích không phải thứ để tổ trưởng chọn trong mọi
        việc cùng lệnh (bản cũ liệt kê hết, chọn nhầm là nhảy cóc chặng). Cách suy:

          1. Các bước LỆNH mà công việc này đại diện: bước riêng ⇒ chính `step_key`; bước chạy
             chung của bài ghép ⇒ mọi bước lệnh nó gộp (`bai_ghep_cong_doan_map`).
          2. Bước sau của từng bước = cạnh `lsx_cong_doan_phu_thuoc` đi ra (có thể sang lệnh khác
             — bước ghép). Bước KHÔNG khai cạnh đi ra thì lấy bước có `thu_tu` kế tiếp trong
             lệnh — cùng luật số lượng bám thứ tự bảng.
          3. Bước sau ⇒ công việc CÙNG GÓI: khớp `step_key` (bước riêng) hoặc bước chung bài
             ghép đã gộp nó.

        Nhiều phần tử khi bước sau bị TÁCH lần chạy ("lần k/N") hoặc routing rẽ nhánh — lúc đó
        tổ mới phải chọn. Rỗng ⇔ bước cuối của lệnh (không bàn giao — thành phẩm qua KCS nhập kho). Giữ cả việc đã hoàn thành: đó
        vẫn là chặng sau thật, bên gọi tự quyết mặc định."""
        if cv.bai_ghep_cong_doan_id is not None:
            keys = set(self.db.scalars(
                select(BaiGhepCongDoanMap.lsx_step_key).where(
                    BaiGhepCongDoanMap.bai_ghep_cong_doan_id == cv.bai_ghep_cong_doan_id
                )
            ))
        else:
            keys = {cv.step_key} if cv.step_key else set()
        if not keys:
            return []
        buoc = list(self.db.scalars(select(LsxCongDoan).where(LsxCongDoan.step_key.in_(keys))))
        if not buoc:
            return []

        canh: dict[int, list[str]] = {}
        for truoc_id, sau_key in self.db.execute(
            select(LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoan.step_key)
            .join(LsxCongDoan, LsxCongDoan.id == LsxCongDoanPhuThuoc.buoc_sau_id)
            .where(LsxCongDoanPhuThuoc.buoc_truoc_id.in_([b.id for b in buoc]))
        ):
            canh.setdefault(truoc_id, []).append(sau_key)

        sau_keys: set[str] = set()
        thu_tu_lenh: dict[int, list[LsxCongDoan]] = {}
        for b in buoc:
            if canh.get(b.id):
                sau_keys.update(canh[b.id])
                continue
            if b.lsx_id not in thu_tu_lenh:
                thu_tu_lenh[b.lsx_id] = list(self.db.scalars(
                    select(LsxCongDoan)
                    .where(LsxCongDoan.lsx_id == b.lsx_id)
                    .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
                ))
            ds = thu_tu_lenh[b.lsx_id]
            i = next(i for i, x in enumerate(ds) if x.id == b.id)
            if i + 1 < len(ds):
                sau_keys.add(ds[i + 1].step_key)
        sau_keys -= keys
        if not sau_keys:
            return []

        bg_cd_ids = set(self.db.scalars(
            select(BaiGhepCongDoanMap.bai_ghep_cong_doan_id).where(
                BaiGhepCongDoanMap.lsx_step_key.in_(sau_keys)
            )
        ))
        dieu_kien = SanXuatCongViec.step_key.in_(sau_keys)
        if bg_cd_ids:
            dieu_kien = dieu_kien | SanXuatCongViec.bai_ghep_cong_doan_id.in_(bg_cd_ids)
        rows = [
            r for r in self.db.scalars(
                select(SanXuatCongViec).where(SanXuatCongViec.goi_id == cv.goi_id, dieu_kien)
            )
            if r.id != cv.id
        ]
        rows.sort(key=lambda c: (
            c.du_kien_bat_dau is None,
            c.du_kien_bat_dau.timestamp() if c.du_kien_bat_dau else 0.0,
            c.step_key or "", c.phan_doan_so, c.id,
        ))
        return rows

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

    def tong_tot_nhieu(self, cong_viec_ids) -> dict[int, float]:
        """{cong_viec_id: tổng TỐT} cho một TẬP công việc — MỘT truy vấn GỘP, khác `tong_tot` ở
        trên vốn chỉ phục vụ MỘT công việc (drawer). Bàn tổ liệt kê hàng chục công việc và cổng
        đóng nhóm duyệt nhiều bước KCS cuối cùng lúc — gọi `tong_tot` theo từng dòng ở đó là N+1.

        Id không có batch nào thì KHÔNG có mặt trong dict (bên gọi tự `.get(id, 0.0)`). Rỗng đầu
        vào ⇒ trả `{}` mà không đụng DB."""
        ids = [i for i in set(cong_viec_ids) if i]
        if not ids:
            return {}
        rows = self.db.execute(
            select(SanXuatBatch.cong_viec_id, func.coalesce(func.sum(SanXuatBatch.tot), 0))
            .where(SanXuatBatch.cong_viec_id.in_(ids))
            .group_by(SanXuatBatch.cong_viec_id)
        )
        return {cvid: float(tong or 0) for cvid, tong in rows}

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

    def ban_giao_cho_nhan_cua_to(self, to_ids: set[int]) -> list[tuple[SanXuatBanGiao, int]]:
        """Bàn giao ĐANG CHỜ bên nhận xác nhận mà công việc đích thuộc `to_ids` — kèm tổ đích.
        Nguồn của hộp "Chờ tổ bạn xác nhận" trên Bàn tổ và badge menu."""
        if not to_ids:
            return []
        rows = self.db.execute(
            select(SanXuatBanGiao, SanXuatCongViec.department_id)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatBanGiao.dich_cong_viec_id)
            .where(
                SanXuatBanGiao.trang_thai == BG_DE_XUAT,
                SanXuatCongViec.department_id.in_(to_ids),
            )
            .order_by(SanXuatBanGiao.de_xuat_luc, SanXuatBanGiao.id)
        ).all()
        return [(bg, dept) for bg, dept in rows]

    def batch_da_giao_ids(self, cong_viec_id: int) -> set[int]:
        """Id các mẻ của công việc này ĐÃ đi theo một lần bàn giao (bảng `san_xuat_ban_giao_batch`).
        Mẻ không có trong tập = mẻ chưa giao, form bàn giao tick sẵn."""
        return set(self.db.scalars(
            select(SanXuatBanGiaoBatch.batch_id)
            .join(SanXuatBatch, SanXuatBatch.id == SanXuatBanGiaoBatch.batch_id)
            .where(SanXuatBatch.cong_viec_id == cong_viec_id)
        ))

    def lien_ket_me(self, ban_giao_id: int) -> list[SanXuatBanGiaoBatch]:
        """Các dòng mẻ↔bàn giao của MỘT lần giao — để sửa lại danh sách mẻ khi còn `proposed`."""
        return list(self.db.scalars(
            select(SanXuatBanGiaoBatch).where(SanXuatBanGiaoBatch.ban_giao_id == ban_giao_id)
        ))

    def delete(self, obj) -> None:
        self.db.delete(obj)

    def me_cua_ban_giao_nhieu(self, ban_giao_ids) -> dict[int, list[int]]:
        """`{ban_giao_id: [batch_id…]}` — các mẻ đi theo từng lần giao, MỘT truy vấn cho cả tập."""
        ids = [i for i in set(ban_giao_ids) if i]
        if not ids:
            return {}
        out: dict[int, list[int]] = {}
        for bg_id, batch_id in self.db.execute(
            select(SanXuatBanGiaoBatch.ban_giao_id, SanXuatBanGiaoBatch.batch_id)
            .where(SanXuatBanGiaoBatch.ban_giao_id.in_(ids))
            .order_by(SanXuatBanGiaoBatch.batch_id)
        ):
            out.setdefault(bg_id, []).append(batch_id)
        return out

    def tong_thuc_nhan_nhieu(self, cong_viec_ids) -> dict[int, dict[str, float]]:
        """{cong_viec_id: {đơn vị: tổng ĐÃ NHẬN về}} cho một TẬP công việc — MỘT truy vấn GỘP.

        "Thực nhận" = bàn giao ĐẾN việc này ở trạng thái confirmed/adjusted; `proposed` chưa chốt
        nên không tính (cùng luật với `san_xuat_kcs_repo.tong_ban_giao_xac_nhan`).

        Tách theo ĐƠN VỊ, không cộng gộp một cục: một bước ghép nhận "tờ" từ chỗ này và "cuốn" từ
        chỗ khác — cộng chung ra một con số vô nghĩa. Bên gọi tự lấy đúng đơn vị đầu vào của bước.
        Việc chưa nhận gì thì KHÔNG có mặt trong dict — phân biệt "nhận 0" với "không ai giao tới"
        (bước ĐẦU chuỗi lấy vật tư từ kho)."""
        ids = [i for i in set(cong_viec_ids) if i]
        if not ids:
            return {}
        rows = self.db.execute(
            select(
                SanXuatBanGiao.dich_cong_viec_id,
                SanXuatBanGiao.don_vi,
                func.coalesce(func.sum(SanXuatBanGiao.so_luong), 0),
            )
            .where(
                SanXuatBanGiao.dich_cong_viec_id.in_(ids),
                SanXuatBanGiao.trang_thai.in_((BG_XAC_NHAN, BG_DIEU_CHINH)),
            )
            .group_by(SanXuatBanGiao.dich_cong_viec_id, SanXuatBanGiao.don_vi)
        )
        ket: dict[int, dict[str, float]] = {}
        for cvid, don_vi, tong in rows:
            ket.setdefault(cvid, {})[don_vi or ""] = float(tong or 0)
        return ket

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

    def dieu_chinh_nhieu(self, ban_giao_ids) -> dict[int, list[SanXuatBanGiaoDieuChinh]]:
        """`{ban_giao_id: [điều chỉnh cũ → mới]}` — lịch sử của cả tập bàn giao, MỘT truy vấn."""
        ids = [i for i in set(ban_giao_ids) if i]
        if not ids:
            return {}
        out: dict[int, list[SanXuatBanGiaoDieuChinh]] = {}
        for dc in self.db.scalars(
            select(SanXuatBanGiaoDieuChinh)
            .where(SanXuatBanGiaoDieuChinh.ban_giao_id.in_(ids))
            .order_by(SanXuatBanGiaoDieuChinh.id)
        ):
            out.setdefault(dc.ban_giao_id, []).append(dc)
        return out

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

    def voucher_xuat_cua_lsx(self, lsx_id: int, *, tru_yeu_cau=None) -> list[StockVoucher]:
        """Phiếu XUẤT ĐÃ GHI SỔ cấp cho một LSX (join phiếu → dòng phiếu → dòng yêu cầu.lsx_id).

        Đây là danh sách tổ trưởng thấy để XÁC NHẬN đã nhận (§10.1). DISTINCT vì một phiếu nhiều
        dòng cùng trỏ một LSX. `tru_yeu_cau` — truy vấn con trả `stock_request_id` cần loại (không
        chứa NULL, nếu không `NOT IN` loại sạch mọi dòng)."""
        if not lsx_id:
            return []
        dieu_kien = [
            StockVoucher.loai == VOUCHER_XUAT,
            StockVoucher.trang_thai == VOUCHER_POSTED,
            StockRequestLine.lsx_id == lsx_id,
        ]
        if tru_yeu_cau is not None:
            dieu_kien.append(StockRequestLine.request_id.not_in(tru_yeu_cau))
        return list(
            self.db.scalars(
                select(StockVoucher)
                .join(StockVoucherLine, StockVoucherLine.voucher_id == StockVoucher.id)
                .join(
                    StockRequestLine,
                    StockVoucherLine.request_line_id == StockRequestLine.id,
                )
                .where(*dieu_kien)
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

    # --- Task 7: khối đối chiếu `vat_tu_cap` (spec-de-nghi-cap-vat-tu-cong-doan §6) -----------
    def voucher_xuat_cua_cong_viec(
        self, cv: SanXuatCongViec, stock_request_ids: list[int]
    ) -> tuple[list[StockVoucher], bool]:
        """Phiếu XUẤT đã ghi sổ mà tổ của CÔNG ĐOẠN này cần xác nhận.

        Công đoạn đã có đề nghị ⇒ CHỈ lấy phiếu của các yêu cầu liên kết. Đường lùi theo `lsx_id`
        chỉ dành cho công đoạn CHƯA TỪNG có đề nghị (dữ liệu trước 31/08/2026) — trộn hai đường là
        cho tổ in thấy cả phiếu của tổ cán màng chỉ vì chung một LSX.

        Bài ghép KHÔNG có đường lùi: dòng yêu cầu cũ khai `lsx_id`, mà bước chung của bài không
        thuộc LSX nào — lùi ở đây là trả về danh sách sai chứ không phải danh sách thiếu.

        "Chưa từng có đề nghị" KHÔNG đủ để gọi là dữ liệu cũ: bước MỚI chưa xin gì cũng rơi vào đó
        (16/09/2026: LSX26-0004 hiện băng "Dữ liệu lịch sử (trước 31/08/2026)"). Đường lùi chỉ nhặt
        phiếu mà yêu cầu của nó KHÔNG thuộc đề nghị công đoạn nào — phiếu đi đường mới của tổ khác
        cùng lệnh không phải của bước này — và cờ chỉ bật khi thật sự nhặt được phiếu như thế.

        Trả `(phiếu, la_du_lieu_cu)`.
        """
        if stock_request_ids:
            return list(self.db.scalars(
                select(StockVoucher)
                .where(StockVoucher.loai == VOUCHER_XUAT,
                       StockVoucher.trang_thai == VOUCHER_POSTED,
                       StockVoucher.request_id.in_(stock_request_ids))
                .order_by(StockVoucher.id)
            )), False
        if cv.bai_ghep_id or not cv.lsx_id:
            return [], False
        yc_cua_de_nghi = (
            select(SanXuatVatTuDeNghi.stock_request_id)
            .where(SanXuatVatTuDeNghi.stock_request_id.is_not(None))
        )
        cu = self.voucher_xuat_cua_lsx(cv.lsx_id, tru_yeu_cau=yc_cua_de_nghi)
        return cu, bool(cu)

    def thuc_xuat_theo_hang(self, stock_request_ids: list[int]) -> dict[tuple[str, int], float]:
        """{(hang_loai, hang_id): tổng `sl_goc`} của DÒNG phiếu XUẤT `posted` thuộc các yêu cầu
        này — MỘT truy vấn GỘP cho cả danh sách, không theo từng yêu cầu (ruling task-7 25).
        Danh sách rỗng trả `{}` mà KHÔNG chạm DB."""
        if not stock_request_ids:
            return {}
        rows = self.db.execute(
            select(StockVoucherLine.hang_loai, StockVoucherLine.hang_id,
                   func.sum(StockVoucherLine.sl_goc))
            .select_from(StockVoucherLine)
            .join(StockVoucher, StockVoucher.id == StockVoucherLine.voucher_id)
            .where(StockVoucher.loai == VOUCHER_XUAT,
                   StockVoucher.trang_thai == VOUCHER_POSTED,
                   StockVoucher.request_id.in_(stock_request_ids))
            .group_by(StockVoucherLine.hang_loai, StockVoucherLine.hang_id)
        )
        return {(loai, int(hid)): float(tong or 0) for loai, hid, tong in rows}

    def yeu_cau_tom_tat(self, request_ids: list[int]) -> dict[int, dict]:
        """`{request_id: {"ma", "trang_thai"}}` — MỘT truy vấn cho cả danh sách. Drawer công đoạn
        cần mã + trạng thái của mọi lần đề nghị; hỏi từng cái là N+1 ngay trên đường mở drawer
        (ruling task-7 25). Danh sách rỗng trả `{}` mà KHÔNG chạm DB."""
        ids = [i for i in set(request_ids) if i]
        if not ids:
            return {}
        rows = self.db.execute(
            select(StockRequest.id, StockRequest.ma, StockRequest.trang_thai)
            .where(StockRequest.id.in_(ids))
        )
        return {rid: {"ma": ma, "trang_thai": tt} for rid, ma, tt in rows}

    def ten_hang_nhieu(self, keys: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
        """`{(hang_loai, hang_id): tên}` — MỘT truy vấn MỖI `hang_loai`, không phải mỗi mặt hàng
        (ruling task-7 25). Danh sách rỗng trả `{}` mà KHÔNG chạm DB."""
        theo_loai: dict[str, set[int]] = {}
        for loai, hid in keys:
            theo_loai.setdefault(loai, set()).add(int(hid))
        out: dict[tuple[str, int], str] = {}
        for loai, ids in theo_loai.items():
            if not ids:
                continue
            model = GiayNguyen if loai == HANG_GIAY else VatTuInAn if loai == HANG_VAT_TU else None
            if model is None:
                continue
            rows = self.db.execute(select(model.id, model.ten).where(model.id.in_(ids)))
            for hid, ten in rows:
                out[(loai, hid)] = ten
        return out
