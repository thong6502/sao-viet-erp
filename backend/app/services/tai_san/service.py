"""Nghiệp vụ sổ tài sản — ghi tăng, nạp số dư đầu kỳ, sửa, xoá, hai chứng từ biến động.

Từ 08/09/2026 sổ KHÔNG còn kỳ chốt (chủ: "nó chỉ theo dõi khấu hao thôi"). Hao mòn lũy kế là số
TÍNH RA từ lịch (`khau_hao.py`) tới hết tháng trước, không lưu, không cộng dồn, không có gì để
chốt hay mở lại. Mỗi lần cơ sở trích đổi (ghi tăng, nạp đầu kỳ, nâng cấp) là một dòng
`tai_san_moc`; mốc cũ giữ nguyên nên tháng trước mốc mới vẫn tính theo cơ sở cũ.

KHÔNG còn nghiệp vụ ghi giảm (chủ 08/09/2026: "cái ghi giảm bỏ đi"): món bán / hỏng / không dùng
nữa thì XOÁ khỏi sổ — xoá được cả khi đã có điều chuyển / nâng cấp. Dòng cũ còn mang `da_giam` +
`ngay_giam` thì engine vẫn ngừng trích từ ngày đó (đọc được, không tạo mới).

Luật khoá còn lại: tài sản ĐÃ CÓ CHỨNG TỪ biến động thì không sửa ô ảnh hưởng số — lịch sử chứng
từ và mốc phải khớp nhau. Ô mô tả sửa thoải mái.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date

from ...models.tai_san import (
    BD_DIEU_CHUYEN,
    BD_NANG_CAP,
    LOAI_CCDC,
    LOAI_TSCD,
    MOC_DAU_KY,
    MOC_GHI_TANG,
    MOC_NANG_CAP,
    MOC_SUA,
    NGUON_DAU_KY,
    NGUON_GHI_TANG,
    TT_DA_GIAM,
    TT_DANG_DUNG,
    TaiSan,
    TaiSanBienDong,
    TaiSanChiPhi,
    TaiSanMoc,
)
from ...repositories.tai_san_repo import TaiSanRepository
from ..bien_che import TRANG_THAI_DANG_LAM
from .khau_hao import DongThang, Moc, lich_khau_hao, luy_ke_den, muc_thang, thang_truoc


class TaiSanNotFound(Exception):
    pass


class TaiSanTrung(Exception):
    pass


class TaiSanValidationError(Exception):
    pass


class TaiSanDaCoChungTu(Exception):
    """Đụng vào số của tài sản đã có chứng từ biến động."""


#: Ô làm ĐỔI SỐ trên sổ — khoá hết khi tài sản đã có chứng từ biến động.
O_ANH_HUONG_SO = {
    "nguyen_gia", "so_thang", "ngay_su_dung", "co_so_trich", "so_thang_con", "moc_tu_ngay",
    "so_luong", "don_gia", "hao_mon_dau_ky", "thang_da_trich_dau_ky", "chi_phi", "loai",
    "nguon_vao",
}

#: Ô mô tả — sửa lúc nào cũng được. `nguoi_quan_ly_id` đi qua `_gan_nguoi_quan_ly` (phải là
#: nhân viên của bộ phận đang giữ), không setattr thẳng.
O_MO_TA = {
    "ten", "bo_phan_id", "nguoi_quan_ly_id", "nguoi_quan_ly", "vi_tri", "so_hoa_don",
    "nha_cung_cap", "ghi_chu",
}

TIEN_TO_MA = {LOAI_TSCD: "TS-", LOAI_CCDC: "CC-"}


def mocs_cua(t: TaiSan) -> list[Moc]:
    """Danh sách mốc của tài sản cho engine (theo thứ tự ngày).

    Dòng cũ chưa có mốc nào (trước mg 0281) chỉ có bộ ba trên `tai_san` ⇒ coi là một mốc duy
    nhất, lũy kế đầu = nguyên giá − còn phải trích: đúng cho cả bốn đường (mua mới 0; đầu kỳ =
    hao mòn mang sang; đã nâng cấp / giảm lô = lũy kế tại lúc đó). Cùng công thức với mg 0281.
    """
    if t.moc:
        return [
            Moc(tu_ngay=m.tu_ngay, nguyen_gia=int(m.nguyen_gia or 0),
                co_so_trich=int(m.co_so_trich or 0), so_thang_con=int(m.so_thang_con or 0),
                luy_ke_dau=int(m.luy_ke_dau or 0))
            for m in sorted(t.moc, key=lambda m: m.tu_ngay)
        ]
    return [Moc(tu_ngay=t.moc_tu_ngay, nguyen_gia=int(t.nguyen_gia or 0),
                co_so_trich=int(t.co_so_trich or 0), so_thang_con=int(t.so_thang_con or 0),
                luy_ke_dau=int(t.nguyen_gia or 0) - int(t.co_so_trich or 0))]


def ngay_giam_cua(t: TaiSan) -> date | None:
    return t.ngay_giam if t.trang_thai == TT_DA_GIAM else None


def thang_da_tinh(hom_nay: date | None = None) -> tuple[int, int]:
    """Tháng gần nhất đã KHÉP: hao mòn lũy kế "tới nay" là tới hết tháng trước — tháng đang chạy
    chưa hết thì chưa trích (kế toán ghi khấu hao vào cuối tháng)."""
    h = hom_nay or date.today()
    return thang_truoc(h.year, h.month)


def _dau_thang(d: date) -> date:
    return date(d.year, d.month, 1)


def _thang_sau(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _tien(x) -> str:
    """28800000 → "28.800.000" — cùng kiểu với màn hình, để câu diễn giải đọc là khớp ngay."""
    return f"{int(x or 0):,}".replace(",", ".")


@dataclass(frozen=True)
class SuKien:
    """Một chuyện xảy ra với tài sản trong một tháng — nhãn ngắn để đeo chip trên bảng, câu đầy
    đủ để rê chuột / ngăn chi tiết / Excel."""

    #: `dau` | `dau_ky` | `nang_cap` | `chuyen` | `cuoi` — FE tô màu theo đây.
    loai: str
    nhan: str
    chi_tiet: str


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

    # --- Đọc số từ lịch (không lưu) --------------------------------------------------------

    def hao_mon_den(self, t: TaiSan, nam: int, thang: int) -> int:
        """Hao mòn lũy kế tính đến HẾT tháng (năm, tháng)."""
        return luy_ke_den(mocs_cua(t), nam, thang, ngay_giam=ngay_giam_cua(t))

    def hao_mon_hien_tai(self, t: TaiSan, hom_nay: date | None = None) -> int:
        """Hao mòn lũy kế tới nay = tới hết tháng trước."""
        return self.hao_mon_den(t, *thang_da_tinh(hom_nay))

    def muc_thang(self, t: TaiSan, nam: int, thang: int) -> tuple[int, int]:
        """(số trích của tháng, lũy kế sau tháng đó)."""
        return muc_thang(mocs_cua(t), nam, thang, ngay_giam=ngay_giam_cua(t))

    def lich(self, t: TaiSan) -> list[DongThang]:
        """Lịch khấu hao trọn đời (đã qua lẫn sắp tới) — mỗi tháng một dòng."""
        return lich_khau_hao(mocs_cua(t), ngay_giam=ngay_giam_cua(t))

    def lich_da_tinh(self, t: TaiSan, hom_nay: date | None = None) -> list[DongThang]:
        """Phần lịch đã vào lũy kế (tới hết tháng trước)."""
        moc = thang_da_tinh(hom_nay)
        return [d for d in self.lich(t) if (d.nam, d.thang) <= moc]

    def du_kien(self, tai_san_id: int) -> list[DongThang]:
        """Lịch khấu hao của tài sản — hiện ngay sau khi lưu phiếu ghi tăng."""
        return self.lich(self._bat_buoc(tai_san_id))

    # --- Sự kiện theo tháng (bảng tháng · ngăn xem chi tiết · Excel) ----------------------
    #
    # Chủ (08/09/2026): "nâng cấp / đổi số mà bảng tháng chỉ điền nguyên giá mới thì khó hiểu, hai
    # tab phải liên quan đến nhau". Tháng nào "có chuyện" (dùng từ giữa tháng, số dư mang sang,
    # nâng cấp, điều chuyển, tháng cuối) thì có một `SuKien`: nhãn ngắn đeo chip trên bảng, câu
    # đầy đủ nói số TRƯỚC → SAU cho ngăn chi tiết / tooltip / Excel.

    def su_kien_theo_thang(self, t: TaiSan) -> dict[tuple[int, int], list[SuKien]]:
        """Khoá (năm, tháng) → sự kiện của tháng đó. Cần `t.moc` và `t.bien_dong`."""
        ghi: dict[tuple[int, int], list[SuKien]] = {}

        def them(d: date, loai: str, nhan: str, chi_tiet: str) -> None:
            ghi.setdefault((d.year, d.month), []).append(SuKien(loai, nhan, chi_tiet))

        mocs = sorted(t.moc, key=lambda m: (m.tu_ngay, m.id or 0))
        if mocs:
            dau = mocs[0]
            if t.nguon_vao == NGUON_DAU_KY:
                them(dau.tu_ngay, "dau_ky", "Số dư mang sang",
                     f"Bắt đầu tính trên phần mềm, hao mòn mang sang {_tien(dau.luy_ke_dau)}")
            elif dau.tu_ngay.day != 1:
                so_ngay = calendar.monthrange(dau.tu_ngay.year, dau.tu_ngay.month)[1]
                dung = so_ngay - dau.tu_ngay.day + 1
                them(dau.tu_ngay, "dau", f"Tháng đầu {dung}/{so_ngay} ngày",
                     f"Dùng từ {dau.tu_ngay:%d/%m}: tháng đầu trích {dung}/{so_ngay} ngày")

        def muc(m) -> int:
            return int(m.co_so_trich) // int(m.so_thang_con) if m.so_thang_con else 0

        def truoc_sau(m) -> str:
            i = mocs.index(m)
            if i == 0:
                return f"nguyên giá {_tien(m.nguyen_gia)}, mức tháng {_tien(muc(m))}"
            tr = mocs[i - 1]
            return (f"nguyên giá {_tien(tr.nguyen_gia)} → {_tien(m.nguyen_gia)}, "
                    f"mức tháng {_tien(muc(tr))} → {_tien(muc(m))}")

        # Chứng từ ↔ mốc nó đẻ ra, cùng thứ tự: nâng cấp ↔ mốc `nang_cap`, bớt cái ↔ mốc `giam_lo`.
        bd_nc = [b for b in t.bien_dong if b.loai == BD_NANG_CAP]
        for b, m in zip(bd_nc, [m for m in mocs if m.nguon == MOC_NANG_CAP]):
            them(m.tu_ngay, "nang_cap", f"Sửa chữa lớn +{_tien(b.so_tien)}",
                 f"Sửa chữa lớn +{_tien(b.so_tien)} ngày {b.ngay:%d/%m}: {truoc_sau(m)}")

        for b in t.bien_dong:
            if b.loai == BD_DIEU_CHUYEN:
                ten = self.repo.ten_bo_phan(b.bo_phan_moi_id) if b.bo_phan_moi_id else None
                them(b.ngay, "chuyen", f"Chuyển sang {ten or 'bộ phận khác'} {b.ngay:%d/%m}",
                     f"Điều chuyển sang {ten or 'bộ phận khác'} ngày {b.ngay:%d/%m}")

        return ghi

    @staticmethod
    def su_kien_dong(d: DongThang, theo_thang: dict[tuple[int, int], list[SuKien]]) -> list[SuKien]:
        """Sự kiện của một dòng lịch: tháng có chuyện thì lấy, không thì tháng cuối mới có."""
        ds = theo_thang.get((d.nam, d.thang))
        if ds:
            return list(ds)
        if d.con_lai == 0:
            return [SuKien("cuoi", "Tháng cuối", "Hết khấu hao: tháng cuối trích nốt phần còn lại")]
        return []

    @staticmethod
    def dien_giai_dong(d: DongThang, theo_thang: dict[tuple[int, int], list[SuKien]]) -> str | None:
        """Câu đầy đủ của dòng (Excel, tooltip) — nối các sự kiện bằng "; "."""
        ds = TaiSanService.su_kien_dong(d, theo_thang)
        return "; ".join(s.chi_tiet for s in ds) if ds else None

    @staticmethod
    def dong_hien_thi(t: TaiSan, d: DongThang) -> DongThang:
        """Dòng CŨ đã ghi giảm (nghiệp vụ đã bỏ): tháng giảm "còn lại" hiện 0 — món đã ra khỏi
        sổ, không để cột số bảo còn 23.906.667 trong khi món đã bán."""
        if t.trang_thai == TT_DA_GIAM and t.ngay_giam is not None \
                and (d.nam, d.thang) == (t.ngay_giam.year, t.ngay_giam.month):
            return replace(d, con_lai=0)
        return d

    # --- Mốc cơ sở -------------------------------------------------------------------------

    def _dat_moc(self, t: TaiSan, *, tu_ngay: date, nguyen_gia: int, co_so_trich: int,
                 so_thang_con: int, luy_ke_dau: int, nguon: str) -> None:
        """Thêm một mốc và chép nó lên bộ ba `co_so_trich/so_thang_con/moc_tu_ngay` của `tai_san`
        (gương của mốc HIỆN TẠI để bảng và form đọc thẳng; engine đọc bảng mốc)."""
        t.moc.append(TaiSanMoc(
            tu_ngay=tu_ngay, nguyen_gia=int(nguyen_gia), co_so_trich=int(co_so_trich),
            so_thang_con=int(so_thang_con), luy_ke_dau=int(luy_ke_dau), nguon=nguon,
        ))
        t.co_so_trich = int(co_so_trich)
        t.so_thang_con = int(so_thang_con)
        t.moc_tu_ngay = tu_ngay

    def _moc_hien_tai(self, t: TaiSan) -> Moc:
        return mocs_cua(t)[-1]

    # --- Người quản lý ---------------------------------------------------------------------
    #
    # Chủ chốt 08/09/2026: chọn bộ phận sử dụng rồi thì người quản lý phải là NHÂN VIÊN của bộ
    # phận đó, không gõ tay. Tên chụp sang `nguoi_quan_ly` để bảng đọc thẳng.

    def nhan_vien_bo_phan(self, bo_phan_id: int):
        """Nhân viên ĐANG LÀM của bộ phận — nguồn của ô chọn người quản lý."""
        return self.repo.nhan_vien_bo_phan(bo_phan_id, TRANG_THAI_DANG_LAM)

    def _gan_nguoi_quan_ly(self, t: TaiSan, nhan_vien_id: int | None) -> None:
        """None = bỏ trống. Có id thì người đó phải thuộc `t.bo_phan_id` (đã gán trước đó)."""
        if not nhan_vien_id:
            t.nguoi_quan_ly_id = None
            t.nguoi_quan_ly = None
            return
        nv = self.repo.nhan_vien(int(nhan_vien_id))
        if nv is None:
            raise TaiSanValidationError(f"Không tìm thấy nhân viên #{nhan_vien_id}")
        if not t.bo_phan_id:
            raise TaiSanValidationError("Chọn bộ phận sử dụng trước rồi mới chọn người quản lý")
        if nv.department_id != t.bo_phan_id:
            raise TaiSanValidationError(
                f"{nv.full_name} không thuộc bộ phận đang giữ tài sản — người quản lý phải là "
                "nhân viên của bộ phận đó"
            )
        t.nguoi_quan_ly_id = nv.id
        t.nguoi_quan_ly = nv.full_name

    def _nguoi_quan_ly_lech_bo_phan(self, t: TaiSan) -> bool:
        if not t.nguoi_quan_ly_id:
            return False
        nv = self.repo.nhan_vien(t.nguoi_quan_ly_id)
        return nv is None or nv.department_id != t.bo_phan_id

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
            nguon_vao=nguon_vao,
            bo_phan_id=payload.get("bo_phan_id"),
            nguoi_quan_ly=payload.get("nguoi_quan_ly"),
            vi_tri=payload.get("vi_tri"),
            so_hoa_don=payload.get("so_hoa_don"),
            nha_cung_cap=payload.get("nha_cung_cap"),
            ghi_chu=payload.get("ghi_chu"),
            trang_thai=TT_DANG_DUNG,
            created_by_user_id=user_id,
        )
        if not t.ten:
            raise TaiSanValidationError("Phải nhập tên tài sản")
        if payload.get("nguoi_quan_ly_id"):
            self._gan_nguoi_quan_ly(t, payload["nguoi_quan_ly_id"])
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
        self._dat_moc(t, tu_ngay=t.ngay_su_dung, nguyen_gia=t.nguyen_gia,
                      co_so_trich=t.nguyen_gia, so_thang_con=t.so_thang, luy_ke_dau=0,
                      nguon=MOC_GHI_TANG)
        self.repo.them(t)
        self.repo.commit()
        return t

    def nap_dau_ky(self, payload: dict, *, user_id: int | None = None) -> TaiSan:
        """Tài sản đã dùng TRƯỚC khi lên phần mềm: mang sang phần còn phải trích.

        `moc_tu_ngay` là tháng đầu tiên phần mềm chịu trách nhiệm tính (thường là tháng bắt đầu
        dùng hệ), KHÁC `ngay_su_dung` (ngày mua về từ mấy năm trước). Luôn ép về NGÀY 1 của tháng
        đó: số mang sang là số tròn tháng, không có chuyện "từ 15/01 chia lẻ ngày".
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
        self._dat_moc(t, tu_ngay=_dau_thang(moc), nguyen_gia=t.nguyen_gia,
                      co_so_trich=t.nguyen_gia - hao_mon, so_thang_con=t.so_thang - thang_da_trich,
                      luy_ke_dau=hao_mon, nguon=MOC_DAU_KY)
        self.repo.them(t)
        self.repo.commit()
        return t

    # --- Sửa / xoá ------------------------------------------------------------------------

    def sua(self, tai_san_id: int, payload: dict) -> TaiSan:
        t = self._bat_buoc(tai_san_id)
        dung_o_so = {k for k in payload if k in O_ANH_HUONG_SO}
        if dung_o_so and t.bien_dong:
            raise TaiSanDaCoChungTu(
                "Tài sản đã có chứng từ biến động — chỉ sửa được các ô mô tả "
                f"(đang sửa: {', '.join(sorted(dung_o_so))})"
            )
        for k in payload:
            if k in O_MO_TA and k != "nguoi_quan_ly_id":
                setattr(t, k, payload[k])
        if "nguoi_quan_ly_id" in payload:
            self._gan_nguoi_quan_ly(t, payload["nguoi_quan_ly_id"])
        elif "bo_phan_id" in payload and self._nguoi_quan_ly_lech_bo_phan(t):
            self._gan_nguoi_quan_ly(t, None)     # đổi bộ phận mà không chọn người mới ⇒ bỏ trống
        if dung_o_so:
            self._ap_lai_o_so(t, payload)
        self.repo.commit()
        return t

    def _ap_lai_o_so(self, t: TaiSan, payload: dict) -> None:
        """Sửa ô ảnh hưởng số khi CHƯA có chứng từ ⇒ dựng lại mốc duy nhất từ đầu."""
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
        so_thang_con = int(t.so_thang) - int(t.thang_da_trich_dau_ky or 0)
        if so_thang_con <= 0:
            raise TaiSanValidationError("Số tháng đã trích phải nhỏ hơn số tháng khấu hao")
        hao_mon_dau = int(t.hao_mon_dau_ky or 0) if t.nguon_vao == NGUON_DAU_KY else 0
        if hao_mon_dau >= nguyen_gia:
            raise TaiSanValidationError("Hao mòn lũy kế phải từ 0 đến nhỏ hơn nguyên giá")

        if payload.get("moc_tu_ngay"):
            moc = payload["moc_tu_ngay"]
        elif t.nguon_vao == NGUON_GHI_TANG:
            moc = t.ngay_su_dung
        else:
            moc = t.moc_tu_ngay
        if t.nguon_vao == NGUON_DAU_KY:
            moc = _dau_thang(moc)

        t.nguyen_gia = nguyen_gia
        t.moc.clear()
        self._dat_moc(t, tu_ngay=moc, nguyen_gia=nguyen_gia, co_so_trich=nguyen_gia - hao_mon_dau,
                      so_thang_con=so_thang_con, luy_ke_dau=hao_mon_dau, nguon=MOC_SUA)

    def xoa(self, tai_san_id: int) -> None:
        """Gỡ hẳn khỏi sổ — cả chứng từ điều chuyển / nâng cấp lẫn mọi tháng đã trích.

        Không có nghiệp vụ ghi giảm (chủ bỏ 08/09/2026) nên đây là lối ra DUY NHẤT cho món đã
        bán / hỏng / không dùng nữa; FE hỏi xác nhận trước. `tai_san_bien_dong` là FK RESTRICT
        nên phải xoá chứng từ trước khi xoá tài sản; mốc và dòng chi phí cascade theo.
        """
        t = self._bat_buoc(tai_san_id)
        for bd in list(t.bien_dong):
            self.repo.xoa(bd)
        self.repo.xoa(t)
        self.repo.commit()

    # --- Hai chứng từ biến động -------------------------------------------------------------
    #
    # Mỗi chứng từ để lại đúng một hàng `tai_san_bien_dong` — tab lịch sử của tài sản đọc thẳng
    # bảng đó. Nâng cấp thêm một mốc cơ sở; điều chuyển không đụng mốc. (Ghi giảm đã bỏ 08/09/2026.)

    def _ky_ap_dung(self, ngay: date) -> date:
        """Nâng cấp áp từ ĐẦU THÁNG SAU, trừ khi chứng từ đúng ngày 1 thì áp ngay tháng đó.

        Nửa tháng đầu tính theo giá cũ, nửa sau theo giá mới là kiểu số không ai đối chiếu nổi;
        kế toán vẫn quen "tháng sau mới đổi mức". Tháng chứng từ vẫn trích theo mốc CŨ (mốc cũ còn
        nguyên trong bảng mốc), không mất tháng nào.
        """
        return ngay if ngay.day == 1 else _thang_sau(ngay)

    def _chan_truoc_khi_dung(self, t: TaiSan, ngay: date) -> None:
        if ngay < t.ngay_su_dung:
            raise TaiSanValidationError(
                f"Ngày chứng từ ({ngay:%d/%m/%Y}) trước ngày đưa vào sử dụng "
                f"({t.ngay_su_dung:%d/%m/%Y})"
            )

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
        nguoi_quan_ly_id: int | None = None,
        ly_do: str | None = None,
        user_id: int | None = None,
    ) -> TaiSanBienDong:
        """Đổi bộ phận đang giữ. KHÔNG đụng một đồng nào trên sổ — chỉ đổi nơi chịu chi phí.

        Người quản lý: chọn một người của bộ phận NHẬN; không chọn thì bỏ trống — người cũ thuộc
        bộ phận cũ, để lại là sai.
        """
        t = self._bat_buoc(tai_san_id)
        if not bo_phan_moi_id:
            raise TaiSanValidationError("Phải chọn bộ phận nhận")
        bd = self._ghi_bien_dong(
            t, loai=BD_DIEU_CHUYEN, ngay=ngay, bo_phan_moi_id=bo_phan_moi_id,
            ly_do=ly_do, nguoi_tao_id=user_id,
        )
        t.bo_phan_id = bo_phan_moi_id
        self._gan_nguoi_quan_ly(t, nguoi_quan_ly_id)
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
        user_id: int | None = None,
    ) -> TaiSanBienDong:
        """Cộng chi phí SỬA CHỮA LỚN (kế toán gọi là nâng cấp — TT45/2013 Điều 7: sửa chữa làm tăng
        năng lực / kéo dài tuổi thọ thì ghi tăng nguyên giá; sửa chữa bảo dưỡng thường xuyên thì
        vào chi phí tháng đó, KHÔNG nhập ở đây) vào nguyên giá rồi chia lại phần còn phải trích.
        Màn hình gọi là "Sửa chữa lớn" (chủ 08/09/2026: "nâng cấp thực chất là sửa chữa").

        Hao mòn đã trích GIỮ NGUYÊN — sửa chữa lớn không xoá quá khứ. Mức trích mới =
        (nguyên giá mới − hao mòn lũy kế tới trước kỳ áp dụng) ÷ số tháng còn dùng, áp từ kỳ áp
        dụng; các tháng trước đó vẫn theo mốc cũ.
        """
        t = self._bat_buoc(tai_san_id)
        if t.trang_thai == TT_DA_GIAM:
            raise TaiSanValidationError("Tài sản đã ghi giảm — không sửa chữa lớn được nữa")
        self._chan_truoc_khi_dung(t, ngay)
        if int(so_tien or 0) <= 0:
            raise TaiSanValidationError("Chi phí sửa chữa phải lớn hơn 0")
        if int(so_thang_con_lai or 0) <= 0:
            raise TaiSanValidationError("Số tháng còn dùng phải lớn hơn 0")
        ky = self._ky_ap_dung(ngay)
        if ky < self._moc_hien_tai(t).tu_ngay:
            raise TaiSanValidationError("Tháng áp dụng sửa chữa lớn phải sau mốc cơ sở hiện tại")

        bd = self._ghi_bien_dong(
            t, loai=BD_NANG_CAP, ngay=ngay, so_tien=int(so_tien),
            so_thang_con_lai=int(so_thang_con_lai), ly_do=ly_do, nguoi_tao_id=user_id,
        )
        t.chi_phi.append(
            TaiSanChiPhi(dien_giai=ly_do or f"Sửa chữa lớn {ngay:%d/%m/%Y}", so_tien=int(so_tien))
        )
        luy_ke_truoc = self.hao_mon_den(t, *thang_truoc(ky.year, ky.month))
        nguyen_gia_moi = int(t.nguyen_gia or 0) + int(so_tien)
        t.nguyen_gia = nguyen_gia_moi
        self._dat_moc(t, tu_ngay=ky, nguyen_gia=nguyen_gia_moi,
                      co_so_trich=nguyen_gia_moi - luy_ke_truoc,
                      so_thang_con=int(so_thang_con_lai), luy_ke_dau=luy_ke_truoc,
                      nguon=MOC_NANG_CAP)
        self.repo.commit()
        return bd
