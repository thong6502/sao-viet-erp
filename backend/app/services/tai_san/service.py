"""Nghiệp vụ sổ tài sản — ghi tăng, nạp số dư đầu kỳ, sửa, xoá.

Luật xuyên suốt: KỲ ĐÃ CHỐT LÀ ĐÓNG. Tài sản đã có số ở một kỳ đã chốt thì không sửa được ô nào
ảnh hưởng tới số đã trích, không xoá được. Các ô mô tả (vị trí, người quản lý, ghi chú hạch
toán…) vẫn sửa thoải mái — chúng không làm đổi một đồng nào trên sổ.
"""
from __future__ import annotations

from datetime import date

from ...models.tai_san import (
    BD_DIEU_CHUYEN,
    BD_GHI_GIAM,
    BD_NANG_CAP,
    LOAI_CCDC,
    LOAI_TSCD,
    NGUON_DAU_KY,
    NGUON_GHI_TANG,
    TT_DA_GIAM,
    TT_DANG_DUNG,
    TaiSan,
    TaiSanBienDong,
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

    # --- Ba chứng từ biến động --------------------------------------------------------------
    #
    # Chung một luật vào cửa: ngày chứng từ rơi vào kỳ ĐÃ CHỐT thì không lập được, và mỗi chứng
    # từ để lại đúng một hàng `tai_san_bien_dong` — tab lịch sử của tài sản đọc thẳng bảng đó.

    def _ky_ap_dung(self, ngay: date) -> date:
        """Nâng cấp áp từ ĐẦU KỲ SAU, trừ khi chứng từ đúng ngày 1 thì áp ngay kỳ đó.

        Nửa tháng đầu tính theo giá cũ, nửa sau theo giá mới là kiểu số không ai đối chiếu nổi;
        kế toán vẫn quen "tháng sau mới đổi mức".
        """
        if ngay.day == 1:
            return ngay
        return date(ngay.year + 1, 1, 1) if ngay.month == 12 else date(ngay.year, ngay.month + 1, 1)

    def _ghi_bien_dong(self, t: TaiSan, **truong) -> TaiSanBienDong:
        bd = TaiSanBienDong(tai_san_id=t.id, **truong)
        self.repo.them(bd)
        return bd

    def dieu_chuyen(
        self,
        tai_san_id: int,
        *,
        ngay: date,
        bo_phan_moi_id: int,
        ly_do: str | None = None,
        ghi_chu_hach_toan: str | None = None,
        user_id: int | None = None,
    ) -> TaiSanBienDong:
        """Đổi bộ phận đang giữ. KHÔNG đụng một đồng nào trên sổ — chỉ đổi nơi chịu chi phí."""
        t = self._bat_buoc(tai_san_id)
        self._chan_ky_da_chot(ngay)
        if not bo_phan_moi_id:
            raise TaiSanValidationError("Phải chọn bộ phận nhận")
        bd = self._ghi_bien_dong(
            t, loai=BD_DIEU_CHUYEN, ngay=ngay, bo_phan_moi_id=bo_phan_moi_id,
            ly_do=ly_do, ghi_chu_hach_toan=ghi_chu_hach_toan, nguoi_tao_id=user_id,
        )
        t.bo_phan_id = bo_phan_moi_id
        self.repo.commit()
        return bd

    def nang_cap(
        self,
        tai_san_id: int,
        *,
        ngay: date,
        so_tien: int,
        so_thang_con_lai: int,
        ly_do: str | None = None,
        ghi_chu_hach_toan: str | None = None,
        user_id: int | None = None,
    ) -> TaiSanBienDong:
        """Cộng chi phí nâng cấp vào nguyên giá rồi chia lại phần còn phải trích.

        Hao mòn đã trích GIỮ NGUYÊN — nâng cấp không xoá quá khứ. Mức trích mới =
        (nguyên giá mới − hao mòn lũy kế) ÷ số tháng còn dùng, áp từ kỳ áp dụng.
        """
        t = self._bat_buoc(tai_san_id)
        self._chan_ky_da_chot(ngay)
        if t.trang_thai == TT_DA_GIAM:
            raise TaiSanValidationError("Tài sản đã ghi giảm — không nâng cấp được nữa")
        if int(so_tien or 0) <= 0:
            raise TaiSanValidationError("Chi phí nâng cấp phải lớn hơn 0")
        if int(so_thang_con_lai or 0) <= 0:
            raise TaiSanValidationError("Số tháng còn dùng phải lớn hơn 0")

        bd = self._ghi_bien_dong(
            t, loai=BD_NANG_CAP, ngay=ngay, so_tien=int(so_tien),
            so_thang_con_lai=int(so_thang_con_lai), ly_do=ly_do,
            ghi_chu_hach_toan=ghi_chu_hach_toan, nguoi_tao_id=user_id,
        )
        t.chi_phi.append(
            TaiSanChiPhi(dien_giai=ly_do or f"Nâng cấp {ngay:%d/%m/%Y}", so_tien=int(so_tien))
        )
        t.nguyen_gia = int(t.nguyen_gia or 0) + int(so_tien)
        t.so_thang_con = int(so_thang_con_lai)
        t.co_so_trich = t.nguyen_gia - int(t.hao_mon_luy_ke or 0)
        t.moc_tu_ngay = self._ky_ap_dung(ngay)
        self.repo.commit()
        return bd

    def ghi_giam(
        self,
        tai_san_id: int,
        *,
        ngay: date,
        ly_do: str,
        gia_ban: int | None = None,
        so_luong_giam: int | None = None,
        ghi_chu_hach_toan: str | None = None,
        user_id: int | None = None,
    ) -> TaiSanBienDong:
        """Thanh lý / nhượng bán / mất / hỏng.

        Bỏ MỘT PHẦN lô CCDC (`so_luong_giam` < số lượng) thì lô vẫn sống: nguyên giá và hao mòn
        cùng rút theo tỷ lệ số cái bỏ, phần còn phải trích chia đều cho số tháng còn lại. Bỏ hết
        lô, hoặc TSCĐ (một cái), thì tài sản chuyển `da_giam` và ngừng trích từ `ngay`.
        """
        t = self._bat_buoc(tai_san_id)
        self._chan_ky_da_chot(ngay)
        if t.trang_thai == TT_DA_GIAM:
            raise TaiSanValidationError("Tài sản đã ghi giảm rồi")
        if not (ly_do or "").strip():
            raise TaiSanValidationError("Phải nhập lý do ghi giảm")

        mot_phan = so_luong_giam is not None and int(so_luong_giam) < int(t.so_luong or 1)
        if so_luong_giam is not None:
            n = int(so_luong_giam)
            if n <= 0 or n > int(t.so_luong or 1):
                raise TaiSanValidationError(
                    f"Số lượng giảm phải từ 1 đến {int(t.so_luong or 1)}"
                )

        bd = self._ghi_bien_dong(
            t, loai=BD_GHI_GIAM, ngay=ngay,
            so_tien=int(gia_ban) if gia_ban is not None else None,
            so_luong_giam=int(so_luong_giam) if so_luong_giam is not None else None,
            ly_do=ly_do, ghi_chu_hach_toan=ghi_chu_hach_toan, nguoi_tao_id=user_id,
        )

        if mot_phan:
            n = int(so_luong_giam)
            tong = int(t.so_luong)
            ng_bo = int(t.nguyen_gia or 0) * n // tong
            hm_bo = int(t.hao_mon_luy_ke or 0) * n // tong
            t.so_luong = tong - n
            t.nguyen_gia = int(t.nguyen_gia or 0) - ng_bo
            t.hao_mon_luy_ke = int(t.hao_mon_luy_ke or 0) - hm_bo
            t.co_so_trich = t.nguyen_gia - t.hao_mon_luy_ke
            da_trich = self.repo.so_ky_da_trich(t.id)
            t.so_thang_con = max(int(t.so_thang) - da_trich, 1)
            t.moc_tu_ngay = date(ngay.year, ngay.month, 1)
        else:
            if so_luong_giam is not None:
                t.so_luong = 0
            t.trang_thai = TT_DA_GIAM
            t.ngay_giam = ngay

        self.repo.commit()
        return bd

    def chenh_lech_thanh_ly(self, tai_san_id: int) -> int | None:
        """Giá bán − giá trị còn lại của PHẦN ĐÃ BỎ, theo chứng từ ghi giảm mới nhất.

        Dương = lãi thanh lý, âm = lỗ. Module chỉ BÁO SỐ; hạch toán vào đâu là việc của kế toán,
        ghi ở ô ghi chú hạch toán của chứng từ.

        Bỏ MỘT PHẦN lô CCDC thì `nguyen_gia`/`hao_mon_luy_ke` trên bản ghi ĐÃ rút theo tỷ lệ, tức
        chúng mô tả mấy cái CÒN nằm trong xưởng. Trừ thẳng chúng là đem giá bán 1 cái so với giá
        trị của 3 cái còn lại — số ra sai hẳn một bậc. Hao mòn rút CÙNG tỷ lệ với nguyên giá nên
        giá trị còn lại chia đều cho mỗi cái: phần đã bỏ = giá trị còn lại × số cái bỏ ÷ số cái
        còn (lệch tối đa vài đồng do làm tròn xuống, không đáng kể với con số thanh lý).
        """
        t = self._bat_buoc(tai_san_id)
        gan_nhat = None
        for bd in t.bien_dong:
            if bd.loai == BD_GHI_GIAM:
                gan_nhat = bd
        if gan_nhat is None or gan_nhat.so_tien is None:
            return None
        con_lai = int(t.nguyen_gia or 0) - int(t.hao_mon_luy_ke or 0)
        con = int(t.so_luong or 0)
        bo = int(gan_nhat.so_luong_giam or 0)
        if t.trang_thai != TT_DA_GIAM and bo > 0 and con > 0:
            con_lai = con_lai * bo // con
        return int(gan_nhat.so_tien) - con_lai

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
