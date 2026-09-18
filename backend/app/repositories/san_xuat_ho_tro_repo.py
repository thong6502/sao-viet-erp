"""Data-access cho lát HỖ TRỢ CHÉO (Giai đoạn 4, §9).

Giữ đúng tầng: mọi truy vấn/ghi DB của thoả thuận hỗ trợ gom ở đây; service
`services/san_xuat/ho_tro.py` chỉ điều phối + kiểm luật. Đọc mẻ / khoảng tham gia thì dùng
`SanXuatSanLuongRepository` / `SanXuatThucThiRepository` (không lặp lại).

⚠️ Tách ra từ `san_xuat_phan_bo_repo.py` ngày 18/09/2026 (mg `0322`) khi tầng CHIA SẢN LƯỢNG gỡ
hẳn — header/dòng phân bổ, bù trừ, loại trừ đi cùng bốn bảng bị xoá. Còn lại đúng hai việc: thoả
thuận hỗ trợ chéo và cổng "bàn giao không nhất quán".

Hàm `ho_tro_xac_nhan_trong_pham_vi` gỡ theo: nó sinh ra để cộng TỔNG TỶ LỆ ≤ 100% cho engine chia,
mà ô tỷ lệ đã bỏ (`ty_le_phan_tram`). Phiếu hỗ trợ nay thuần là vết "ai sang giúp ai, ngày nào".
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models.san_xuat import SanXuatCongViec
from ..models.san_xuat_phan_bo import HT_CHO_HAI_BEN, HT_HUY, SanXuatHoTro
from ..models.san_xuat_san_luong import SanXuatBanGiao


class SanXuatHoTroRepository:
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

    # --- Thỏa thuận hỗ trợ (§9) --------------------------------------------------------------
    def ho_tro(self, ho_tro_id: int) -> SanXuatHoTro | None:
        return self.db.get(SanXuatHoTro, ho_tro_id)

    def ho_tro_cua_cong_viec(self, cong_viec_id: int) -> list[SanXuatHoTro]:
        """Mọi thỏa thuận hỗ trợ của một công đoạn (mọi trạng thái) — để hiển thị + huỷ khi lịch
        chưa chạy bị phát hành lại (§9.2)."""
        return list(
            self.db.scalars(
                select(SanXuatHoTro)
                .where(SanXuatHoTro.cong_viec_id == cong_viec_id)
                .order_by(SanXuatHoTro.ngay_lam_viec, SanXuatHoTro.id)
            )
        )

    def ho_tro_con_song_cua_nguoi(
        self, cong_viec_id: int, employee_id: int, ngay: date
    ) -> SanXuatHoTro | None:
        """Thỏa thuận CHƯA HUỶ của đúng một người trong (công đoạn, ngày) — chặn ghi hai vết
        trùng nhau cho cùng một người cùng một ngày (một người sang giúp thì chỉ một vết)."""
        return self.db.scalar(
            select(SanXuatHoTro)
            .where(
                SanXuatHoTro.cong_viec_id == cong_viec_id,
                SanXuatHoTro.employee_id == employee_id,
                SanXuatHoTro.ngay_lam_viec == ngay,
                SanXuatHoTro.trang_thai != HT_HUY,
            )
            .order_by(SanXuatHoTro.id)
            .limit(1)
        )

    def ho_tro_cho_cua_to(self, to_ids: set[int]) -> list[SanXuatHoTro]:
        """Thỏa thuận CÒN CHỜ mà bên thuộc `to_ids` chưa xác nhận — bên gốc hoặc bên thực hiện.
        Nguồn của hộp "Chờ tổ bạn xác nhận" trên Bàn tổ và badge menu."""
        if not to_ids:
            return []
        return list(
            self.db.scalars(
                select(SanXuatHoTro)
                .where(
                    SanXuatHoTro.trang_thai == HT_CHO_HAI_BEN,
                    or_(
                        and_(SanXuatHoTro.to_goc_id.in_(to_ids),
                             SanXuatHoTro.xac_nhan_goc_by_id.is_(None)),
                        and_(SanXuatHoTro.to_thuc_hien_id.in_(to_ids),
                             SanXuatHoTro.xac_nhan_thuc_hien_by_id.is_(None)),
                    ),
                )
                .order_by(SanXuatHoTro.ngay_lam_viec, SanXuatHoTro.id)
            )
        )

    # --- Gate không-nhất-quán bàn giao (§11.3) -----------------------------------------------
    def co_ban_giao_khong_nhat_quan(self, cong_viec_id: int) -> bool:
        """Công đoạn còn bàn giao ĐI bị đánh dấu không nhất quán (giảm dưới lượng công đoạn sau đã
        dùng) → §11.3 chặn CHỐT phân bổ cho tới khi gỡ."""
        row = self.db.scalar(
            select(SanXuatBanGiao.id).where(
                SanXuatBanGiao.nguon_cong_viec_id == cong_viec_id,
                SanXuatBanGiao.khong_nhat_quan.is_(True),
            ).limit(1)
        )
        return row is not None
