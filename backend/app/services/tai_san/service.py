"""Nghiệp vụ sổ tài sản — ghi tăng, nạp số dư đầu kỳ, sửa, xoá.

Luật xuyên suốt: KỲ ĐÃ CHỐT LÀ ĐÓNG. Tài sản đã có số ở một kỳ đã chốt thì không sửa được ô nào
ảnh hưởng tới số đã trích, không xoá được. Các ô mô tả (vị trí, người quản lý, ghi chú hạch
toán…) vẫn sửa thoải mái — chúng không làm đổi một đồng nào trên sổ.
"""
from __future__ import annotations

from datetime import date

from ...models.tai_san import (
    LOAI_CCDC,
    LOAI_TSCD,
    NGUON_DAU_KY,
    NGUON_GHI_TANG,
    TT_DANG_DUNG,
    TaiSan,
    TaiSanChiPhi,
)
from ...repositories.tai_san_repo import TaiSanRepository
from .khau_hao import DongDuKien, lich_du_kien


class TaiSanNotFound(Exception):
    pass


class TaiSanTrung(Exception):
    pass


class TaiSanValidationError(Exception):
    pass


class TaiSanDaChotKy(Exception):
    """Đụng vào số của một kỳ đã chốt."""


#: Ô làm ĐỔI SỐ trên sổ — khoá hết khi tài sản đã có số ở kỳ đã chốt.
O_ANH_HUONG_SO = {
    "nguyen_gia", "so_thang", "ngay_su_dung", "co_so_trich", "so_thang_con", "moc_tu_ngay",
    "so_luong", "don_gia", "hao_mon_dau_ky", "thang_da_trich_dau_ky", "hao_mon_luy_ke",
    "chi_phi", "loai", "nguon_vao",
}

#: Ô mô tả — sửa lúc nào cũng được.
O_MO_TA = {
    "ten", "bo_phan_id", "nguoi_quan_ly", "vi_tri", "so_hoa_don", "nha_cung_cap",
    "ghi_chu_hach_toan", "ghi_chu",
}

TIEN_TO_MA = {LOAI_TSCD: "TS-", LOAI_CCDC: "CC-"}


class TaiSanService:
    def __init__(self, repo: TaiSanRepository) -> None:
        self.repo = repo

    # --- Tiện ích -------------------------------------------------------------------------

    def sinh_ma(self, loai: str) -> str:
        """`TS-0001` cho TSCĐ, `CC-0001` cho CCDC. Đánh số riêng từng loại."""
        tien_to = TIEN_TO_MA.get(loai, TIEN_TO_MA[LOAI_TSCD])
        lon_nhat = self.repo.ma_lon_nhat(tien_to)
        so = 0
        if lon_nhat:
            duoi = lon_nhat[len(tien_to):]
            if duoi.isdigit():
                so = int(duoi)
        return f"{tien_to}{so + 1:04d}"

    def _bat_buoc(self, tai_san_id: int) -> TaiSan:
        t = self.repo.lay(tai_san_id)
        if t is None:
            raise TaiSanNotFound(f"Không tìm thấy tài sản #{tai_san_id}")
        return t

    def _chan_ky_da_chot(self, ngay: date) -> None:
        """Chứng từ rơi vào kỳ đã chốt thì không được lập — số kỳ đó đã khoá."""
        if self.repo.ky_da_chot(ngay.year, ngay.month):
            raise TaiSanDaChotKy(f"Kỳ {ngay.month:02d}/{ngay.year} đã chốt, không sửa được nữa")

    # --- Ghi tăng / nạp đầu kỳ ------------------------------------------------------------

    def _nguyen_gia(self, payload: dict) -> int:
        """Nguyên giá = tổng dòng chi phí; lô CCDC không khai dòng thì lấy số lượng × đơn giá."""
        dong = payload.get("chi_phi") or []
        if dong:
            return sum(int(d.get("so_tien") or 0) for d in dong)
        return int(payload.get("so_luong") or 1) * int(payload.get("don_gia") or 0)

    def _dung(self, payload: dict, *, nguon_vao: str, user_id: int | None) -> TaiSan:
        loai = payload.get("loai") or LOAI_TSCD
        so_thang = int(payload.get("so_thang") or 0)
        if so_thang <= 0:
            raise TaiSanValidationError("Số tháng khấu hao phải lớn hơn 0")
        ngay_su_dung = payload.get("ngay_su_dung")
        if not ngay_su_dung:
            raise TaiSanValidationError("Phải nhập ngày đưa vào sử dụng")
        nguyen_gia = self._nguyen_gia(payload)
        if nguyen_gia <= 0:
            raise TaiSanValidationError("Nguyên giá phải lớn hơn 0")

        ma = (payload.get("ma") or "").strip() or self.sinh_ma(loai)
        if self.repo.tim_theo_ma(ma) is not None:
            raise TaiSanTrung(f"Mã {ma} đã có trong sổ")

        t = TaiSan(
            ma=ma,
            ten=(payload.get("ten") or "").strip(),
            loai=loai,
            so_luong=int(payload.get("so_luong") or 1),
            don_gia=payload.get("don_gia"),
            nguyen_gia=nguyen_gia,
            so_thang=so_thang,
            ngay_su_dung=ngay_su_dung,
            hao_mon_luy_ke=0,
            nguon_vao=nguon_vao,
            bo_phan_id=payload.get("bo_phan_id"),
            nguoi_quan_ly=payload.get("nguoi_quan_ly"),
            vi_tri=payload.get("vi_tri"),
            so_hoa_don=payload.get("so_hoa_don"),
            nha_cung_cap=payload.get("nha_cung_cap"),
            ghi_chu_hach_toan=payload.get("ghi_chu_hach_toan"),
            ghi_chu=payload.get("ghi_chu"),
            trang_thai=TT_DANG_DUNG,
            created_by_user_id=user_id,
        )
        if not t.ten:
            raise TaiSanValidationError("Phải nhập tên tài sản")
        for d in payload.get("chi_phi") or []:
            t.chi_phi.append(
                TaiSanChiPhi(
                    dien_giai=(d.get("dien_giai") or "").strip() or "Nguyên giá",
                    so_tien=int(d.get("so_tien") or 0),
                )
            )
        return t

    def ghi_tang(self, payload: dict, *, user_id: int | None = None) -> TaiSan:
        """Tài sản mua mới: trích từ chính ngày đưa vào sử dụng, chưa hao mòn đồng nào."""
        t = self._dung(payload, nguon_vao=NGUON_GHI_TANG, user_id=user_id)
        t.co_so_trich = t.nguyen_gia
        t.so_thang_con = t.so_thang
        t.moc_tu_ngay = t.ngay_su_dung
        self.repo.them(t)
        self.repo.commit()
        return t

    def nap_dau_ky(self, payload: dict, *, user_id: int | None = None) -> TaiSan:
        """Tài sản đã dùng TRƯỚC khi lên phần mềm: mang sang phần còn phải trích.

        `moc_tu_ngay` là tháng đầu tiên phần mềm chịu trách nhiệm tính (thường là tháng bắt đầu
        dùng hệ), KHÁC `ngay_su_dung` (ngày mua về từ mấy năm trước).
        """
        t = self._dung(payload, nguon_vao=NGUON_DAU_KY, user_id=user_id)
        hao_mon = int(payload.get("hao_mon_dau_ky") or 0)
        thang_da_trich = int(payload.get("thang_da_trich_dau_ky") or 0)
        moc = payload.get("moc_tu_ngay")
        if not moc:
            raise TaiSanValidationError("Phải nhập tháng bắt đầu tính trên phần mềm")
        if hao_mon < 0 or hao_mon >= t.nguyen_gia:
            raise TaiSanValidationError("Hao mòn lũy kế phải từ 0 đến nhỏ hơn nguyên giá")
        if thang_da_trich < 0 or thang_da_trich >= t.so_thang:
            raise TaiSanValidationError("Số tháng đã trích phải nhỏ hơn số tháng khấu hao")

        t.hao_mon_dau_ky = hao_mon
        t.thang_da_trich_dau_ky = thang_da_trich
        t.hao_mon_luy_ke = hao_mon
        t.co_so_trich = t.nguyen_gia - hao_mon
        t.so_thang_con = t.so_thang - thang_da_trich
        t.moc_tu_ngay = moc
        self.repo.them(t)
        self.repo.commit()
        return t

    # --- Sửa / xoá ------------------------------------------------------------------------

    def sua(self, tai_san_id: int, payload: dict) -> TaiSan:
        t = self._bat_buoc(tai_san_id)
        dung_o_so = {k for k in payload if k in O_ANH_HUONG_SO}
        if dung_o_so and self.repo.co_ky_chot_lien_quan(tai_san_id):
            raise TaiSanDaChotKy(
                "Tài sản đã có số ở kỳ đã chốt — chỉ sửa được các ô mô tả "
                f"(đang sửa: {', '.join(sorted(dung_o_so))})"
            )
        for k in payload:
            if k in O_MO_TA:
                setattr(t, k, payload[k])
        if dung_o_so:
            self._ap_lai_o_so(t, payload)
        self.repo.commit()
        return t

    def _ap_lai_o_so(self, t: TaiSan, payload: dict) -> None:
        """Sửa ô ảnh hưởng số khi CHƯA có kỳ chốt ⇒ dựng lại bộ ba từ đầu."""
        if "chi_phi" in payload:
            t.chi_phi.clear()
            for d in payload["chi_phi"] or []:
                t.chi_phi.append(
                    TaiSanChiPhi(
                        dien_giai=(d.get("dien_giai") or "").strip() or "Nguyên giá",
                        so_tien=int(d.get("so_tien") or 0),
                    )
                )
        for k in ("loai", "so_luong", "don_gia", "so_thang", "ngay_su_dung",
                  "hao_mon_dau_ky", "thang_da_trich_dau_ky"):
            if k in payload and payload[k] is not None:
                setattr(t, k, payload[k])

        nguyen_gia = sum(int(c.so_tien or 0) for c in t.chi_phi)
        if not nguyen_gia:
            nguyen_gia = int(t.so_luong or 1) * int(t.don_gia or 0)
        if nguyen_gia <= 0:
            raise TaiSanValidationError("Nguyên giá phải lớn hơn 0")
        if int(t.so_thang or 0) <= 0:
            raise TaiSanValidationError("Số tháng khấu hao phải lớn hơn 0")

        t.nguyen_gia = nguyen_gia
        t.hao_mon_luy_ke = int(t.hao_mon_dau_ky or 0)
        t.co_so_trich = nguyen_gia - t.hao_mon_luy_ke
        t.so_thang_con = int(t.so_thang) - int(t.thang_da_trich_dau_ky or 0)
        if t.so_thang_con <= 0:
            raise TaiSanValidationError("Số tháng đã trích phải nhỏ hơn số tháng khấu hao")
        if "moc_tu_ngay" in payload and payload["moc_tu_ngay"]:
            t.moc_tu_ngay = payload["moc_tu_ngay"]
        elif t.nguon_vao == NGUON_GHI_TANG:
            t.moc_tu_ngay = t.ngay_su_dung

    def xoa(self, tai_san_id: int) -> None:
        t = self._bat_buoc(tai_san_id)
        if self.repo.co_ky_chot_lien_quan(tai_san_id):
            raise TaiSanDaChotKy("Tài sản đã có số ở kỳ đã chốt — không xoá được, hãy ghi giảm")
        if t.bien_dong:
            raise TaiSanValidationError(
                "Tài sản đã có chứng từ biến động — không xoá được, hãy ghi giảm"
            )
        self.repo.xoa(t)
        self.repo.commit()

    # --- Xem trước ------------------------------------------------------------------------

    def du_kien(self, tai_san_id: int) -> list[DongDuKien]:
        """Bảng khấu hao dự kiến từ mốc hiện tại — hiện ngay sau khi lưu phiếu ghi tăng."""
        t = self._bat_buoc(tai_san_id)
        return lich_du_kien(
            co_so_trich=t.co_so_trich,
            so_thang_con=t.so_thang_con,
            moc_tu_ngay=t.moc_tu_ngay,
            nguyen_gia=t.nguyen_gia,
            luy_ke=t.hao_mon_luy_ke,
        )
