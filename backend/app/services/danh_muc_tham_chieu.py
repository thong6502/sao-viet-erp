"""Đếm NƠI ĐANG DÙNG một mục danh mục — một nguồn cho luồng xoá của cả phân hệ.

Vì sao cần: danh mục là dữ liệu GỐC, mọi module khác chỉ ăn theo. Nhưng ở DB gần như không có
ràng buộc thật — 12 bảng danh mục chỉ có 7 khoá ngoại, chạm đúng 3 bảng. Nghĩa là xoá cứng một
công đoạn / một loại giấy KHÔNG sinh lỗi: nó trả 204 êm ru rồi để lại id trỏ vào hư không ở 9 chỗ
khác. Muốn hỏi "cái này còn ai dùng không" thì phải TỰ ĐẾM, và đếm ở MỘT chỗ chứ không phải mỗi
service chép một kiểu.

Luật của luồng xoá (xem `docs` phần Mô hình xoá):
  * còn nơi dùng  → chỉ cho NGỪNG DÙNG (`active=false`), giữ nguyên mọi chứng từ cũ;
  * chưa ai dùng  → cho XOÁ HẲN, vì đó là khai nhầm rồi xoá ngay, giữ lại chỉ tổ làm rác danh mục.

Hai loại con số, đừng lẫn:
  * `chan`   — nơi đang dùng thật. Có cái này thì KHÔNG cho xoá hẳn.
  * `keo_theo` — bản ghi sẽ BAY THEO nếu xoá hẳn, do `ON DELETE CASCADE` ở DB. Không chặn, nhưng
    phải nói bằng SỐ trước khi người dùng bấm: xoá 1 công đoạn là mất luôn toàn bộ định mức đầu
    việc + BOM vật tư của nó, mà những thứ đó khai tay hàng giờ.

Tham chiếu bằng CHUỖI (mã đơn vị nằm trong `cong_doan.don_vi_vao`, `giay_nguyen.don_vi_gia`…)
cũng phải đếm: đếm theo id sẽ ra 0 và "xoá hẳn" tưởng an toàn trong khi thực tế cắt đứt thật.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session


@dataclass
class ThamChieu:
    """Kết quả đếm cho MỘT bản ghi danh mục."""

    chan: list[str] = field(default_factory=list)      # "3 lệnh sản xuất" — chặn xoá hẳn
    keo_theo: list[str] = field(default_factory=list)  # "12 định mức đầu việc" — cảnh báo bằng số

    @property
    def xoa_han_duoc(self) -> bool:
        return not self.chan

    def as_dict(self) -> dict:
        return {
            "xoa_han_duoc": self.xoa_han_duoc,
            "chan": self.chan,
            "keo_theo": self.keo_theo,
        }


def _dem(db: Session, model, *dieu_kien) -> int:
    """Đếm dòng của `model` thoả mọi điều kiện. Truyền THẲNG lớp model chứ không suy từ cột —
    suy ngầm là chỗ sai im lặng khi điều kiện đụng hai bảng."""
    stmt = select(func.count()).select_from(model)
    for c in dieu_kien:
        stmt = stmt.where(c)
    return int(db.execute(stmt).scalar_one() or 0)


def _cau(n: int, nhan: str) -> str | None:
    """`3` + `"lệnh sản xuất"` → `"3 lệnh sản xuất"`. `0` → None (không thêm dòng rỗng)."""
    return f"{n} {nhan}" if n else None


def _gom(*cau: str | None) -> list[str]:
    return [c for c in cau if c]


# ── từng danh mục ────────────────────────────────────────────────────────────────
def _cong_doan(db: Session, obj) -> ThamChieu:
    from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
    from ..models.cong_doan import CongDoan, CongDoanDauViec
    from ..models.loai_san_pham import LoaiSanPham
    from ..models.lsx import LsxCongDoan
    from ..models.phieu_tinh_gia import PhieuThanhPham

    chan = _gom(
        _cau(_dem(db, LsxCongDoan, LsxCongDoan.cong_doan_id == obj.id),
             "bước trong lệnh sản xuất"),
        _cau(_dem(db, PhieuThanhPham, PhieuThanhPham.cong_doan_id == obj.id),
             "dòng phiếu tính giá"),
        _cau(_dem(db, BaiGhepCongDoan, BaiGhepCongDoan.cong_doan_id == obj.id),
             "bước trong bài ghép"),
    )
    # `routing_template` là JSON list id — không query được bằng SQL cho mọi phương ngữ, đọc trong
    # Python. Bảng loại sản phẩm nhỏ (chục dòng), không đáng lo về hiệu năng.
    n_tpl = sum(
        1 for sp in db.execute(select(LoaiSanPham)).scalars()
        if isinstance(sp.routing_template, list) and obj.id in sp.routing_template
    )
    if (c := _cau(n_tpl, "loại sản phẩm có bước này trong chuỗi mặc định")):
        chan.append(c)

    # CASCADE thật ở DB (`cong_doan.py:163` → nối tầng `:232`): xoá công đoạn là bay sạch định mức
    # đầu việc VÀ BOM vật tư của chúng. Khai tay hàng giờ, không hoàn tác được.
    n_dv = _dem(db, CongDoanDauViec, CongDoanDauViec.cong_doan_id == obj.id)
    n_bom = 0
    if n_dv:
        ids = [r.id for r in db.execute(
            select(CongDoanDauViec).where(CongDoanDauViec.cong_doan_id == obj.id)).scalars()]
        from ..models.cong_doan import CongDoanDauViecVatTu
        n_bom = _dem(db, CongDoanDauViecVatTu,
                     CongDoanDauViecVatTu.cong_doan_dau_viec_id.in_(ids)) if ids else 0
    _ = CongDoan  # giữ import cho rõ ràng bảng đang nói tới
    return ThamChieu(chan=chan, keo_theo=_gom(
        _cau(n_dv, "định mức đầu việc"), _cau(n_bom, "dòng vật tư trong định mức")))


def _don_vi_do(db: Session, obj) -> ThamChieu:
    from ..models.cong_doan import CongDoan
    from ..models.don_vi_do import DonViQuyDoi
    from ..models.lsx import LsxCongDoan
    from ..models.stock_request import StockRequestLine
    from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn

    ma = (obj.ma or "").strip().lower()
    # Tham chiếu bằng CHUỖI MÃ — đếm theo id sẽ ra 0 và "xoá hẳn" tưởng an toàn.
    chan = _gom(
        _cau(_dem(db, CongDoan,
                  or_(func.lower(CongDoan.don_vi_vao) == ma, func.lower(CongDoan.don_vi_ra) == ma)),
             "công đoạn dùng làm đơn vị vào/ra"),
        _cau(_dem(db, GiayNguyen, func.lower(GiayNguyen.don_vi_gia) == ma),
             "loại giấy lấy làm đơn vị gốc"),
        _cau(_dem(db, VatTuInAn, func.lower(VatTuInAn.don_vi_gia) == ma),
             "vật tư lấy làm đơn vị gốc"),
        _cau(_dem(db, StockRequestLine, func.lower(StockRequestLine.dvt) == ma),
             "dòng đề nghị kho"),
        _cau(_dem(db, LsxCongDoan,
                  or_(func.lower(LsxCongDoan.don_vi_vao) == ma,
                      func.lower(LsxCongDoan.don_vi_ra) == ma)),
             "bước lệnh sản xuất"),
    )
    # CASCADE: `don_vi_quy_doi.tu_id`/`den_id` (`don_vi_do.py:205,208`). Xoá 1 đơn vị là bay mọi
    # cạnh quy đổi có nó ⇒ đồ thị mất đường ⇒ tiền khoán và quy đổi kho sai IM LẶNG.
    n_cap = _dem(db, DonViQuyDoi,
                 or_(DonViQuyDoi.tu_id == obj.id, DonViQuyDoi.den_id == obj.id))
    return ThamChieu(chan=chan, keo_theo=_gom(_cau(n_cap, "cặp quy đổi")))


def _dem_ghim_khoan(db: Session, model, rate_id: int) -> int:
    """Số bước đang GHIM đơn giá này trong `khoan_json` (`{rate_id, ten, don_vi, don_gia}`).

    Đọc trong Python: `khoan_json` là cột JSON, mà Postgres và SQLite không có cùng một toán tử
    "lấy khoá" nào chạy được cả hai (`->>` vs `json_extract`). Lọc `IS NOT NULL` NGAY Ở SQL nên chỉ
    tải về đúng các bước THẬT SỰ có đầu việc khoán, không phải cả bảng bước lệnh.
    """
    rows = db.execute(
        select(model.khoan_json).where(model.khoan_json.is_not(None))
    ).scalars()
    return sum(1 for j in rows if isinstance(j, dict) and int(j.get("rate_id") or 0) == rate_id)


def _cong_viec_khoan(db: Session, obj) -> ThamChieu:
    """Ai đang dùng một dòng đơn giá khoán.

    Hai kiểu tham chiếu, đếm thiếu kiểu nào là "xoá hẳn" tưởng an toàn:
      · bằng ID   — `cong_doan_dau_viec.piece_rate_id` (định mức đầu việc của công đoạn, khai tay
        hàng giờ: năng suất người-giờ, số người, BOM vật tư);
      · bằng ẢNH CHỤP — bước lệnh SX và bước bài ghép ghim `khoan_json.rate_id`. Số tiền của chúng
        KHÔNG xê dịch khi danh mục đổi (đó là lý do có ảnh chụp), nhưng vẫn phải CHẶN xoá hẳn: mất
        dòng gốc là lệnh không còn chọn lại được đúng đầu việc đó, và người đọc lệnh hết đường tra
        ngược "đơn giá này ở đâu ra".

    Không có CASCADE nào trỏ vào bảng này (`piece_rate_id` là soft-ref, không FK cứng) ⇒ `keo_theo`
    luôn rỗng: xoá một dòng đơn giá không làm bay theo bản ghi nào.
    """
    from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
    from ..models.cong_doan import CongDoanDauViec
    from ..models.lsx import LsxCongDoan

    return ThamChieu(chan=_gom(
        _cau(_dem(db, CongDoanDauViec, CongDoanDauViec.piece_rate_id == obj.id),
             "định mức đầu việc của công đoạn"),
        _cau(_dem_ghim_khoan(db, LsxCongDoan, obj.id), "bước trong lệnh sản xuất"),
        _cau(_dem_ghim_khoan(db, BaiGhepCongDoan, obj.id), "bước trong bài ghép"),
    ))


def _bu_hao(db: Session, obj) -> ThamChieu:
    from ..models.cong_doan import CongDoan

    return ThamChieu(chan=_gom(_cau(
        _dem(db, CongDoan, CongDoan.bu_hao_id == obj.id), "công đoạn tra mã này")))


def _san_xuat_kcs_tieu_chi(db: Session, obj) -> ThamChieu:
    from ..models.san_xuat_kcs import SanXuatKcsTieuChiCongDoan

    return ThamChieu(chan=_gom(_cau(
        _dem(db, SanXuatKcsTieuChiCongDoan, SanXuatKcsTieuChiCongDoan.tieu_chi_id == obj.id),
        "công đoạn đang gắn tiêu chí này")))


def _khuon_be(db: Session, obj) -> ThamChieu:
    """Kho khuôn nay KHÔNG có ai tham chiếu ⇒ xoá không bị chặn.

    Từ 16/08/2026 (mg `0203`) khuôn đã ra khỏi lệnh sản xuất hoàn toàn — cả `lsx_cong_doan
    .khuon_be_id` lẫn `lsx.khuon_be_id` đều xoá, cùng hai detector xếp lịch và nhóm "Công cụ" của
    bảng cân đối. Danh mục này giờ là sổ tài sản đứng riêng.

    Giữ hàm (thay vì gỡ khỏi registry) để màn danh mục vẫn đi đúng luồng `kiem-xoa` chung như 9 màn
    kia — trả rỗng nghĩa là "hỏi rồi, không vướng gì", khác hẳn với 404 vì thiếu hàm.
    """
    return ThamChieu()


def _loai_san_pham(db: Session, obj) -> ThamChieu:
    from ..models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia

    return ThamChieu(chan=_gom(
        _cau(_dem(db, PhieuTinhGia, PhieuTinhGia.loai_san_pham_id == obj.id),
             "phiếu tính giá"),
        _cau(_dem(db, PhieuThanhPhan, PhieuThanhPhan.loai_san_pham_id == obj.id),
             "thành phần phiếu tính giá"),
    ))


def _chung_loai_giay(db: Session, obj) -> ThamChieu:
    from ..models.vat_lieu_kho import GiayNguyen

    return ThamChieu(chan=_gom(_cau(
        _dem(db, GiayNguyen, GiayNguyen.chung_loai_giay_id == obj.id),
        "loại giấy thuộc chủng loại này")))


def _mat_hang(db: Session, obj, hang_loai: str) -> ThamChieu:
    """Giấy / Vật tư — kho trỏ về bằng CẶP (`hang_loai`, `hang_id`), không phải id trần."""
    from ..models.stock_lot import StockLot
    from ..models.stock_request import StockRequestLine
    from ..models.stock_voucher import StockVoucherLine

    cap = (StockLot.hang_loai == hang_loai, StockLot.hang_id == obj.id)
    chan = _gom(
        _cau(_dem(db, StockLot, *cap, StockLot.sl_con_lai > 0), "lô còn tồn trong kho"),
        _cau(_dem(db, StockRequestLine,
                  StockRequestLine.hang_loai == hang_loai, StockRequestLine.hang_id == obj.id),
             "dòng đề nghị kho"),
        _cau(_dem(db, StockVoucherLine,
                  StockVoucherLine.hang_loai == hang_loai, StockVoucherLine.hang_id == obj.id),
             "dòng phiếu kho"),
    )
    if hang_loai == "giay":
        from ..models.bai_ghep import BaiGhep
        from ..models.phieu_tinh_gia import PhieuThanhPhan
        chan += _gom(
            _cau(_dem(db, PhieuThanhPhan, PhieuThanhPhan.giay_id == obj.id),
                 "thành phần phiếu tính giá"),
            _cau(_dem(db, BaiGhep, BaiGhep.giay_id == obj.id), "bài ghép"),
        )
    else:
        from ..models.bai_ghep_cong_doan import BaiGhepCongDoanVatTu
        from ..models.cong_doan import CongDoanDauViecVatTu
        from ..models.lsx import LsxCongDoanVatTu
        from ..models.phieu_tinh_gia import PhieuVatTu
        chan += _gom(
            _cau(_dem(db, CongDoanDauViecVatTu,
                      CongDoanDauViecVatTu.vat_tu_id == obj.id), "định mức đầu việc"),
            _cau(_dem(db, LsxCongDoanVatTu, LsxCongDoanVatTu.vat_tu_id == obj.id),
                 "dòng vật tư của bước lệnh"),
            _cau(_dem(db, BaiGhepCongDoanVatTu,
                      BaiGhepCongDoanVatTu.vat_tu_id == obj.id), "dòng vật tư của bài ghép"),
            _cau(_dem(db, PhieuVatTu, PhieuVatTu.vat_tu_id == obj.id),
                 "dòng vật tư phiếu tính giá"),
        )
    return ThamChieu(chan=chan)


def _may_thiet_bi(db: Session, obj) -> ThamChieu:
    """Ai đang dùng một cái máy.

    Ba đường tham chiếu, hai kiểu khác nhau — đếm thiếu kiểu nào là "xoá hẳn" tưởng an toàn:
      · bằng ID   — bước lệnh SX, thành phần phiếu tính giá, bài ghép, vùng khoá lịch;
      · bằng CHUỖI TÊN NHÓM — `cong_doan.nhom_may_cho_phep` là danh sách JSON tên nhóm, mà máy
        thì mang tên nhóm ở `loai_may`. Xoá cái máy CUỐI CÙNG của một nhóm là công đoạn khai
        nhóm đó hết máy khả dụng, xếp lịch không xếp được mà chẳng ai báo.
    """
    from ..models.bai_ghep import BaiGhep
    from ..models.lsx import Lsx, LsxCongDoan
    from ..models.may_thiet_bi import MayThietBi
    from ..models.phieu_tinh_gia import PhieuThanhPhan
    from ..models.machine_unavailable import MachineUnavailablePeriod

    chan = _gom(
        _cau(_dem(db, LsxCongDoan, LsxCongDoan.may_id == obj.id), "bước trong lệnh sản xuất"),
        _cau(_dem(db, Lsx, Lsx.may_id == obj.id), "lệnh sản xuất"),
        _cau(_dem(db, PhieuThanhPhan, PhieuThanhPhan.may_id == obj.id), "dòng phiếu tính giá"),
        _cau(_dem(db, BaiGhep, BaiGhep.may_id == obj.id), "bài ghép"),
    )
    # Nhóm máy: chỉ CHẶN khi đây là máy cuối cùng còn lại của nhóm — còn máy khác thì công đoạn
    # vẫn chạy được, không có lý do gì bắt giữ lại.
    ten_nhom = (obj.loai_may or "").strip()
    if ten_nhom:
        con_lai = _dem(db, MayThietBi, and_(
            MayThietBi.loai_may == ten_nhom, MayThietBi.id != obj.id, MayThietBi.active.is_(True)))
        if con_lai == 0:
            n_cd = _dem_cong_doan_theo_nhom(db, ten_nhom)
            chan += _gom(_cau(n_cd, f"công đoạn chỉ cho phép nhóm “{ten_nhom}” (đây là máy cuối)"))
    # CASCADE: vùng khoá máy (`machine_unavailable_periods.may_id`) bay theo — đó là lịch nghỉ/bảo
    # trì đã khai, mất là xếp lịch xếp đè vào ngày máy nghỉ.
    n_khoa = _dem(db, MachineUnavailablePeriod, MachineUnavailablePeriod.may_id == obj.id)
    return ThamChieu(chan=chan, keo_theo=_gom(_cau(n_khoa, "khoảng khoá máy đã khai")))


def _dem_cong_doan_theo_nhom(db: Session, ten_nhom: str) -> int:
    """Số công đoạn khai `nhom_may_cho_phep` CÓ CHỨA tên nhóm này.

    `nhom_may_cho_phep` là cột JSON danh sách chuỗi — Postgres và SQLite không có cùng một toán tử
    "chứa" nào chạy được cả hai, nên đọc về rồi lọc trong Python. Danh mục công đoạn có 13 dòng,
    không phải chỗ cần tối ưu truy vấn.
    """
    from ..models.cong_doan import CongDoan

    n = 0
    for ds in db.execute(select(CongDoan.nhom_may_cho_phep)).scalars():
        if isinstance(ds, list) and any((str(x) or "").strip() == ten_nhom for x in ds):
            n += 1
    return n


# `loai` ở đây là tên chính trong `catalog_registry` (cũng là key nhật ký) — không đẻ bộ tên thứ hai.
DEM_THEO_LOAI = {
    "cong_doan": _cong_doan,
    "cong_viec_khoan": _cong_viec_khoan,
    "may_thiet_bi": _may_thiet_bi,
    "don_vi_do": _don_vi_do,
    "bu_hao": _bu_hao,
    "khuon_be": _khuon_be,
    "loai_san_pham": _loai_san_pham,
    "chung_loai_giay": _chung_loai_giay,
    "giay": lambda db, obj: _mat_hang(db, obj, "giay"),
    "vat_tu": lambda db, obj: _mat_hang(db, obj, "vat_tu"),
    "san_xuat_kcs_tieu_chi": _san_xuat_kcs_tieu_chi,
}


def model_cua(loai: str):
    """`loai` → lớp model, đọc từ `catalog_registry` (một nguồn với menu · quyền · nhật ký).

    Registry giữ tên lớp ở dạng CHUỖI và chỉ import lúc gọi — vẫn đúng mẹo cũ: không kéo cả cây
    model vào lúc import module này. Màn chưa khai model (Máy, Khai báo kho) → None, y như trước.
    """
    from ..catalog_registry import lop_model_cua

    return lop_model_cua(loai)


def tham_chieu(db: Session, loai: str, obj) -> ThamChieu:
    """Đếm nơi đang dùng `obj`. Loại chưa khai → coi như KHÔNG BIẾT, và không biết thì không cho
    xoá hẳn: thà bắt người dùng ngừng-dùng còn hơn xoá nhầm thứ đang chạy."""
    fn = DEM_THEO_LOAI.get(loai)
    if fn is None:
        return ThamChieu(chan=["chưa rà được nơi dùng của danh mục này"])
    return fn(db, obj)
