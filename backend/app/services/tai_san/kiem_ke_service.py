"""Đợt kiểm kê tài sản — mức TỐI GIẢN.

Ba bước, hết: bung danh sách phải có → đi đối chiếu rồi tick từng dòng Có / Không thấy → kết
thúc đợt để ra hai danh sách thiếu và thừa.

Cố ý KHÔNG có: dán QR lên máy, quét bằng điện thoại, ký duyệt nhiều cấp, đối chiếu tự động với
sổ kho. Xưởng in này kiểm kê một hai lần một năm; mấy thứ đó thêm màn để sai chứ không thêm việc
làm được.

Đợt ĐÃ KẾT là đóng: kết quả kiểm kê là chứng từ, sửa lại sau khi đã ký biên bản thì biên bản
thành vô nghĩa. Muốn sửa thì lập đợt mới.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...models.tai_san import (
    KK_DA_KET,
    KK_DANG_KIEM,
    TT_DANG_DUNG,
    TaiSan,
    TaiSanKiemKe,
    TaiSanKiemKeDong,
)

KQ_CO = "co"
KQ_KHONG_THAY = "khong_thay"


class KiemKeNotFound(Exception):
    pass


class KiemKeDaKet(Exception):
    pass


class KiemKeValidationError(Exception):
    pass


class KiemKeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đọc ------------------------------------------------------------------------------

    def lay(self, dot_id: int) -> TaiSanKiemKe:
        dot = self.db.execute(
            select(TaiSanKiemKe)
            .options(selectinload(TaiSanKiemKe.dong))
            .where(TaiSanKiemKe.id == dot_id)
        ).scalar_one_or_none()
        if dot is None:
            raise KiemKeNotFound(f"Không tìm thấy đợt kiểm kê #{dot_id}")
        return dot

    def danh_sach(self, *, offset: int = 0, limit: int = 50) -> tuple[list[TaiSanKiemKe], int]:
        tong = int(self.db.execute(select(func.count()).select_from(TaiSanKiemKe)).scalar_one())
        rows = list(
            self.db.execute(
                select(TaiSanKiemKe)
                .order_by(TaiSanKiemKe.ngay.desc(), TaiSanKiemKe.id.desc())
                .offset(max(int(offset), 0))
                .limit(max(int(limit), 1))
            ).scalars()
        )
        return rows, tong

    def dong_kem_ten(self, dot_id: int) -> list[dict]:
        """Dòng đợt kèm mã/tên tài sản — bảng đối chiếu đọc thẳng, không tra từng dòng."""
        dot = self.lay(dot_id)
        stmt = (
            select(TaiSanKiemKeDong, TaiSan.ma, TaiSan.ten)
            .outerjoin(TaiSan, TaiSan.id == TaiSanKiemKeDong.tai_san_id)
            .where(TaiSanKiemKeDong.dot_id == dot.id)
            .order_by(TaiSanKiemKeDong.id)
        )
        return [
            {
                "id": d.id,
                "tai_san_id": d.tai_san_id,
                "ma": ma,
                "ten": ten or d.ten_phat_hien,
                "ket_qua": d.ket_qua,
                "ten_phat_hien": d.ten_phat_hien,
                "tinh_trang": d.tinh_trang,
                "ghi_chu": d.ghi_chu,
            }
            for d, ma, ten in self.db.execute(stmt)
        ]

    # --- Ghi ------------------------------------------------------------------------------

    def _sinh_ma(self) -> str:
        lon_nhat = self.db.execute(
            select(func.max(TaiSanKiemKe.ma)).where(TaiSanKiemKe.ma.like("KK-%"))
        ).scalar_one_or_none()
        so = int(lon_nhat[3:]) if lon_nhat and lon_nhat[3:].isdigit() else 0
        return f"KK-{so + 1:04d}"

    def _dang_mo(self, dot_id: int) -> TaiSanKiemKe:
        dot = self.lay(dot_id)
        if dot.trang_thai == KK_DA_KET:
            raise KiemKeDaKet(f"Đợt {dot.ma} đã kết thúc — lập đợt mới nếu cần kiểm lại")
        return dot

    def tao_dot(
        self,
        *,
        ngay: date,
        bo_phan_id: int | None = None,
        ghi_chu: str | None = None,
        user_id: int | None = None,
    ) -> TaiSanKiemKe:
        """Bung sẵn một dòng cho MỖI tài sản đang dùng thuộc phạm vi — người kiểm chỉ việc tick.

        Tài sản đã ghi giảm KHÔNG bung: nó không còn ở xưởng, hỏi "có thấy không" là vô nghĩa.
        """
        dot = TaiSanKiemKe(
            ma=self._sinh_ma(), ngay=ngay, bo_phan_id=bo_phan_id,
            trang_thai=KK_DANG_KIEM, ghi_chu=ghi_chu, nguoi_tao_id=user_id,
        )
        conds = [TaiSan.trang_thai == TT_DANG_DUNG]
        if bo_phan_id:
            conds.append(TaiSan.bo_phan_id == bo_phan_id)
        for t in self.db.execute(select(TaiSan).where(*conds).order_by(TaiSan.ma)).scalars():
            dot.dong.append(TaiSanKiemKeDong(tai_san_id=t.id))
        self.db.add(dot)
        self.db.commit()
        return dot

    def ghi_ket_qua(
        self,
        dot_id: int,
        dong_id: int,
        *,
        ket_qua: str | None = None,
        tinh_trang: str | None = None,
        ghi_chu: str | None = None,
    ) -> TaiSanKiemKeDong:
        dot = self._dang_mo(dot_id)
        dong = next((d for d in dot.dong if d.id == dong_id), None)
        if dong is None:
            raise KiemKeNotFound(f"Đợt {dot.ma} không có dòng #{dong_id}")
        if ket_qua is not None and ket_qua not in (KQ_CO, KQ_KHONG_THAY):
            raise KiemKeValidationError(f"Kết quả không hợp lệ: {ket_qua}")
        if ket_qua is not None:
            dong.ket_qua = ket_qua
        if tinh_trang is not None:
            dong.tinh_trang = tinh_trang
        if ghi_chu is not None:
            dong.ghi_chu = ghi_chu
        self.db.commit()
        return dong

    def them_phat_hien(
        self,
        dot_id: int,
        *,
        ten_phat_hien: str,
        tinh_trang: str | None = None,
        ghi_chu: str | None = None,
    ) -> TaiSanKiemKeDong:
        """Món có ở xưởng mà KHÔNG có trong sổ. Chỉ ghi nhận — vào sổ hay không là việc ghi tăng."""
        dot = self._dang_mo(dot_id)
        if not (ten_phat_hien or "").strip():
            raise KiemKeValidationError("Phải nhập tên món phát hiện")
        dong = TaiSanKiemKeDong(
            dot_id=dot.id, tai_san_id=None, ten_phat_hien=ten_phat_hien.strip(),
            tinh_trang=tinh_trang, ghi_chu=ghi_chu,
        )
        self.db.add(dong)
        self.db.commit()
        return dong

    def ket_thuc(self, dot_id: int) -> dict:
        """Đóng đợt và trả về hai danh sách: THIẾU (có sổ không thấy) và THỪA (thấy không sổ)."""
        dot = self._dang_mo(dot_id)
        dot.trang_thai = KK_DA_KET
        self.db.commit()
        return self.ket_qua(dot_id)

    def ket_qua(self, dot_id: int) -> dict:
        dong = self.dong_kem_ten(dot_id)
        return {
            "thieu": [d for d in dong if d["tai_san_id"] and d["ket_qua"] == KQ_KHONG_THAY],
            "thua": [d for d in dong if not d["tai_san_id"]],
        }
