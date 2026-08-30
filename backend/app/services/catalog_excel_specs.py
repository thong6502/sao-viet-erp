"""Hợp đồng workbook Excel của ĐỦ 13 màn Cấu hình danh mục.

Cơ chế nằm ở `services/catalog_excel.py`; file này chỉ KHAI: sheet nào, cột nào, kiểu gì, dịch mã
bằng resolver nào, và field nào cố ý KHÔNG đi qua Excel (`loai_tru`, kèm lý do ngay tại chỗ).

⚠️ THÊM CỘT CẤU HÌNH MỚI LÀ PHẢI GHÉ QUA ĐÂY. `tests/test_import_excel.py::test_guard_*` đối chiếu
`repo.fields` của từng màn với tập field Excel + `loai_tru` — quên khai một cột (nhất là một ô công
thức mới) thì test ĐỎ, không lặng lẽ rơi khỏi file xuất.

⚠️ NHÃN CỘT LÀ HỢP ĐỒNG VỚI NGƯỜI DÙNG. Đổi `nhan` = file họ đang giữ mất cột đó (nhập vào sẽ "giữ
nguyên giá trị cũ" chứ không báo lỗi). Muốn đổi thì thêm nhãn cũ vào `nhan_cu`, đừng thay thẳng.

KHÔNG có ở đây, cố ý: nhật ký sửa đổi, phiên bản giá giấy, lịch sử công thức (`<field>_truoc` /
`<field>_sua_luc`), id nội bộ, `created_at`/`updated_at`, ảnh, và trạng thái vận hành tức thời
(máy đang chạy / đang bảo trì). Chúng là LỊCH SỬ và DẪN XUẤT — nhập ngược vào là ghi đè sự thật.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan, NHOM
from ..models.customer import Customer
from ..models.department import Department
from ..models.piece_work import PieceRate
from ..models.vat_lieu_kho import ChungLoaiGiay, VatTuInAn
from ..repositories.bu_hao_repo import BuHaoRepository
from ..repositories.cong_doan_repo import CongDoanRepository
from ..repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.khuon_be_repo import KhuonBeRepository
from ..repositories.loai_san_pham_repo import LoaiSanPhamRepository
from ..repositories.may_thiet_bi_repo import MayThietBiRepository
from ..repositories.san_xuat_ly_do_repo import SanXuatLyDoRepository
from ..repositories.vat_lieu_kho_repo import (
    _ChungLoaiGiayRepo, _GiayRepo, _ThanhPhamRepo, _VatTuRepo,
)
from .catalog_excel import NHAN_TRANG_THAI, CatalogExcelSpec, Cot, NguCanh, SheetCon

# ======================================================================================
# Resolver dùng chung — dịch MÃ NGHIỆP VỤ ↔ id
# ======================================================================================
#
# Vì sao mọi FK đều đi qua mã chứ không id: file Excel là thứ NGƯỜI khai gõ. Số id chỉ có nghĩa
# trong DB của đúng một môi trường — copy file từ máy này sang máy kia là id trỏ nhầm bản ghi mà
# không có gì báo. Phòng ban và khách hàng dùng MÃ HỆ THỐNG (`PB003`, `KH012`) kèm một cột tên
# `chi_doc` để đối chiếu bằng mắt.


class _Tra:
    """Bảng tra hai chiều `mã ↔ id` cho một bảng danh mục, nạp MỘT lần cho cả lượt xuất/nhập.

    Nạp cả bảng chứ không tra từng ô: một lần xuất Công đoạn có ~30 dòng × 3 cột FK, tra lẻ là
    ~90 round-trip cho ba bảng vài chục dòng.
    """

    def __init__(self, model, cot_ma: str, nhan: str, *, cot_ten: str | None = None,
                 man: str | None = None) -> None:
        self.model, self.cot_ma, self.nhan, self.cot_ten = model, cot_ma, nhan, cot_ten
        #: Tên MÀN phải khai xong trước — ghép vào câu lỗi để người nhập biết đi đâu, thay vì chỉ
        #: biết "không tìm thấy" rồi ngồi đoán. Thứ tự nhập giữa các màn là ràng buộc thật.
        self.man = man
        self.khoa = f"tra:{model.__tablename__}:{cot_ma}"

    def _map(self, ctx: NguCanh) -> tuple[dict[str, int], dict[int, str], dict[int, str]]:
        def dung():
            cols = [self.model.id, getattr(self.model, self.cot_ma)]
            if self.cot_ten:
                cols.append(getattr(self.model, self.cot_ten))
            theo_ma: dict[str, int] = {}
            ma_theo_id: dict[int, str] = {}
            ten_theo_id: dict[int, str] = {}
            for hang in ctx.db.execute(select(*cols)).all():
                i, ma = hang[0], hang[1]
                if ma:
                    theo_ma.setdefault(str(ma).strip().lower(), i)
                    ma_theo_id[i] = str(ma)
                if self.cot_ten and hang[2]:
                    ten_theo_id[i] = str(hang[2])
                    # Nhận CẢ TÊN khi nhập: file đời cũ của Công đoạn / Công việc khoán ghi tên tổ,
                    # và người khai quen gõ tên hơn mã. Mã thắng khi trùng nhau.
                    theo_ma.setdefault(str(hang[2]).strip().lower(), i)
            return theo_ma, ma_theo_id, ten_theo_id

        return ctx.nho(self.khoa, dung)

    def doc(self, gt: Any, ctx: NguCanh) -> int | None:
        if gt in (None, ""):
            return None
        theo_ma, _, _ = self._map(ctx)
        khoa = str(gt).strip().lower()
        if khoa not in theo_ma:
            them = f' Khai xong màn "{self.man}" rồi nhập lại màn này.' if self.man else ""
            raise ValueError(f'Không tìm thấy {self.nhan} "{gt}".{them}')
        return theo_ma[khoa]

    def ghi(self, gt: Any, ctx: NguCanh) -> str | None:
        if not gt:
            return None
        _, ma_theo_id, _ = self._map(ctx)
        return ma_theo_id.get(int(gt))

    def ghi_ten(self, gt: Any, ctx: NguCanh) -> str | None:
        if not gt:
            return None
        _, _, ten_theo_id = self._map(ctx)
        return ten_theo_id.get(int(gt))


TRA_TO = _Tra(Department, "code", "tổ/phòng ban", cot_ten="name", man="Phòng ban")
TRA_KHACH = _Tra(Customer, "code", "khách hàng", cot_ten="name", man="Khách hàng")
TRA_BU_HAO = _Tra(BuHao, "ma", "mã bù hao", cot_ten="ten", man="Bù hao")
TRA_CONG_DOAN = _Tra(CongDoan, "ma", "mã công đoạn", cot_ten="ten", man="Công đoạn")
TRA_DAU_VIEC = _Tra(PieceRate, "ma", "mã công việc khoán", cot_ten="ten", man="Công việc khoán")
TRA_VAT_TU = _Tra(VatTuInAn, "ma", "mã vật tư", cot_ten="ten", man="Vật tư khác")
TRA_CHUNG_LOAI = _Tra(ChungLoaiGiay, "ma", "chủng loại giấy", cot_ten="ten",
                      man="Chủng loại giấy")


def _cot_to(field: str = "department_id", nhan: str = "Mã tổ", nhan_ten: str = "Tên tổ",
            nhan_cu: tuple[str, ...] = ()) -> tuple[Cot, Cot]:
    """Cặp cột PHÒNG BAN: một cột mã (ghi được) + một cột tên (`chi_doc`, chỉ để đối chiếu)."""
    return (
        Cot(nhan, field, doc=TRA_TO.doc, ghi=TRA_TO.ghi, nhan_cu=nhan_cu),
        Cot(nhan_ten, field, ghi=TRA_TO.ghi_ten, chi_doc=True, rong=26),
    )


def _tach_danh_sach(gt: Any, _ctx: NguCanh) -> list[str]:
    """Ô "a, b, c" đời cũ → danh sách. Chỉ dùng cho cột `chi_nhap` (nay đã tách thành sheet con)."""
    return [t.strip() for t in str(gt or "").split(",") if t.strip()]


CO_ACTIVE = Cot(NHAN_TRANG_THAI, "active", kieu="bool", rong=12)
"""Cột bật/ngừng dùng. File XUẤT có CẢ dòng đã ngừng (`FALSE`) — xem `_moi_dong` để biết vì sao —
nên đổi ô này rồi nhập lại là ngừng dùng hoặc bật lại được cả hai chiều."""


# ======================================================================================
# 1 · Kho hàng
# ======================================================================================

KHO_HANG = CatalogExcelSpec(
    loai="kho_hang", tieu_de="Kho hàng", repo_cls=KhoHangRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Vị trí", "vi_tri", rong=28),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
)


# ======================================================================================
# 2 · Bù hao — bảng tra số tờ theo bậc số lượng
# ======================================================================================

BU_HAO = CatalogExcelSpec(
    loai="bu_hao", tieu_de="Bù hao", repo_cls=BuHaoRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
    sheets_con=(
        # Bậc bù hao là TOÀN BỘ nội dung nghiệp vụ của màn này — nén vào một ô JSON thì không ai
        # sửa nổi, mà đó chính là thứ người ta mở file Excel ra để sửa.
        SheetCon(
            "Bậc bù hao", field="bac",
            cot=(
                Cot("SL từ", "sl_tu", kieu="nguyen", rong=14),
                Cot("SL đến", "sl_den", kieu="nguyen", rong=14),
                Cot("Giá trị", "gia_tri", kieu="so", rong=14),
                Cot("Đơn vị", "don_vi", rong=12),
            ),
        ),
    ),
)


# ======================================================================================
# 3 · Khuôn bế
# ======================================================================================

KHUON_BE = CatalogExcelSpec(
    loai="khuon_be", tieu_de="Khuôn bế", repo_cls=KhuonBeRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Mã khách hàng", "khach_hang_id", doc=TRA_KHACH.doc, ghi=TRA_KHACH.ghi),
        Cot("Tên khách hàng", "khach_hang_id", ghi=TRA_KHACH.ghi_ten, chi_doc=True, rong=30),
        Cot("Loại dao", "loai"),
        Cot("Số kệ", "so_ke", rong=14),
        Cot("Tình trạng", "tinh_trang", rong=16),
        Cot("Ngày về dự kiến", "ngay_ve_du_kien", kieu="ngay", rong=18),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
)


# ======================================================================================
# 4 · Loại sản phẩm
# ======================================================================================

LOAI_SAN_PHAM = CatalogExcelSpec(
    loai="loai_san_pham", tieu_de="Loại sản phẩm", repo_cls=LoaiSanPhamRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Kiểu cấu trúc", "structural_type", rong=18),
        Cot("Kiểu hộp", "box_sub_type", rong=18),
        Cot("Có bìa", "has_cover", kieu="bool", rong=12),
        Cot("Loại bìa", "cover_type", rong=18),
        Cot("Kiểu đóng mặc định", "default_binding", rong=20),
        Cot("Nhóm giấy mặc định", "default_stock_class", rong=20),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
    sheets_con=(
        SheetCon(
            "Chuỗi công đoạn mặc định", field="routing_template", rut_gon="cong_doan_id",
            cot=(Cot("Mã công đoạn", "cong_doan_id",
                     doc=TRA_CONG_DOAN.doc, ghi=TRA_CONG_DOAN.ghi),),
        ),
    ),
    # `imposition_rule_id` trỏ tới `quy_tac_binh_bai` — bảng đó KHÔNG tồn tại trong hệ (không model,
    # không màn khai). Đưa vào Excel là bắt người ta gõ một id không tra được ở đâu.
    loai_tru=frozenset({"imposition_rule_id"}),
)


# ======================================================================================
# 5 · Lý do & lỗi sản xuất
# ======================================================================================

SAN_XUAT_LY_DO = CatalogExcelSpec(
    loai="san_xuat_ly_do", tieu_de="Lý do & lỗi SX", repo_cls=SanXuatLyDoRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Nhóm", "nhom", rong=16),
        Cot("Tên", "ten", rong=32),
        Cot("Mô tả", "mo_ta", rong=40),
        Cot("Thứ tự hiện", "thu_tu", kieu="nguyen", rong=14),
        CO_ACTIVE,
    ),
)


# ======================================================================================
# 6 · Công việc khoán (`piece_rates`)
# ======================================================================================

CONG_VIEC_KHOAN = CatalogExcelSpec(
    loai="cong_viec_khoan", tieu_de="Công việc khoán", repo_cls=CongViecKhoanRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        # `nhan_cu="Tổ"`: file đời cũ ghi TÊN tổ trong cột "Tổ" — `_Tra` nhận cả tên lẫn mã.
        *_cot_to(nhan_cu=("Tổ",)),
        Cot("Đơn vị", "unit", rong=14),
        Cot("Đơn giá", "unit_price", kieu="so", rong=16),
        Cot("Công thức lượng", "cong_thuc_luong", rong=36),
        Cot("Ghi chú", "note", rong=32),
        CO_ACTIVE,
    ),
    # `group_name` là NHÃN TỔ do service tự đặt theo `department_id` (`CongViecKhoanIn` cố ý không
    # có nó). Cho nhập là mở đường để hai cột cùng khai một sự thật rồi lệch nhau.
    loai_tru=frozenset({"group_name"}),
)


# ======================================================================================
# 7 · Đơn vị & quy đổi
# ======================================================================================


def _doc_cap(obj, ctx: NguCanh) -> list[dict]:
    """Các cặp quy đổi mà đơn vị này là VẾ TRÁI.

    Chỉ chiều đã LƯU (`tu → den`), không bày cặp ngược: `repo.find_cap` khớp hai chiều nên một cặp
    hiện ở cả hai đơn vị là mời người ta sửa hai nơi rồi hai nơi nói khác nhau.
    """
    if obj is None:
        return []
    caps = ctx.nho("don_vi:cap", lambda: ctx.svc.repo.cap_rows())
    return [{"den_ma": c.den_ma, "he_so": float(c.he_so), "ghi_chu": c.ghi_chu}
            for c in caps if c.tu_id == obj.id]


def _ap_cap(ctx: NguCanh, obj, rows: list[dict], actor_id: int | None) -> None:
    """Thay TRỌN tập cặp có vế trái là `obj` — thêm cặp mới, sửa hệ số, xoá cặp đã bỏ khỏi file."""
    svc = ctx.svc
    hien_co = {c.den_id: c for c in svc.repo.cap_rows() if c.tu_id == obj.id}
    muon: dict[int, dict] = {}
    for r in rows:
        den_ma = (r.get("den_ma") or "").strip()
        if not den_ma:
            raise ValueError("Cặp quy đổi thiếu mã đơn vị đích.")
        den = svc.repo.find_by_ma(den_ma)
        if den is None:
            raise ValueError(f'Không tìm thấy mã đơn vị "{den_ma}" (cặp quy đổi).')
        muon[den.id] = {"tu_id": obj.id, "den_id": den.id,
                        "he_so": float(r.get("he_so") or 0), "ghi_chu": r.get("ghi_chu")}

    for den_id, cu in hien_co.items():
        if den_id not in muon:
            svc.delete_cap(cu.id, actor_id=actor_id)
    for den_id, data in muon.items():
        cu = hien_co.get(den_id)
        if cu is None:
            svc.create_cap(data, actor_id=actor_id)
        elif abs(float(cu.he_so) - data["he_so"]) > 1e-9 or (cu.ghi_chu or None) != data["ghi_chu"]:
            svc.update_cap(cu.id, data, actor_id=actor_id)


DON_VI_DO = CatalogExcelSpec(
    loai="don_vi_do", tieu_de="Đơn vị đo", repo_cls=DonViDoRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=28),
        Cot("Loại đo", "ho", rong=16),
        Cot("Hiệu lực từ", "hieu_luc_tu", kieu="ngay", rong=16),
        Cot("Dùng làm đơn vị tốc độ", "dung_lam_toc_do", kieu="bool", rong=22),
        Cot("Trạm dòng giấy", "tram_dong_giay", rong=18),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
    sheets_con=(
        # Cặp quy đổi là bảng RIÊNG (`don_vi_quy_doi`), không phải field của `DonViDoIn` — nên đi
        # đường `ap_dung` thay vì `_gan_con`.
        SheetCon(
            "Các cặp quy đổi", thu_tu=False,
            cot=(
                Cot("Mã đơn vị đích", "den_ma", rong=18),
                Cot("Hệ số", "he_so", kieu="so", rong=16),
                Cot("Ghi chú", "ghi_chu", rong=32),
            ),
            doc_hien_co=_doc_cap, ap_dung=_ap_cap,
        ),
    ),
)


# ======================================================================================
# 8-11 · Vật liệu kho: Chủng loại giấy · Giấy · Vật tư khác · Thành phẩm
# ======================================================================================


def _doc_thay_the(gt: Any, ctx: NguCanh) -> int:
    """Mã NVL thay thế → id, TRONG CÙNG danh mục đang nhập (`svc.kind`)."""
    ma = str(gt or "").strip()
    o = ctx.svc.find_by_ma(ma)
    if o is None:
        raise ValueError(f'Không tìm thấy mã "{ma}" (NVL thay thế).')
    return o.id


def _ghi_thay_the(gt: Any, ctx: NguCanh) -> str | None:
    if not gt:
        return None
    objs = ctx.nho(f"tt:{ctx.svc.kind}:{int(gt)}",
                   lambda: ctx.svc.goc.repo.by_ids(ctx.svc.kind, [int(gt)]))
    return objs[0].ma if objs else None


def _sheet_thay_the(ten: str, nhan: str) -> SheetCon:
    return SheetCon(
        ten, field="thay_the_ids", rut_gon="thay_the_id",
        cot=(Cot(nhan, "thay_the_id", doc=_doc_thay_the, ghi=_ghi_thay_the),),
    )


CHUNG_LOAI_GIAY = CatalogExcelSpec(
    loai="chung_loai_giay", tieu_de="Chủng loại giấy", repo_cls=_ChungLoaiGiayRepo,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Mô tả", "mo_ta", rong=40),
        CO_ACTIVE,
    ),
)

GIAY = CatalogExcelSpec(
    loai="giay", tieu_de="Giấy", repo_cls=_GiayRepo,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Chủng loại giấy", "chung_loai_giay_id",
            doc=TRA_CHUNG_LOAI.doc, ghi=TRA_CHUNG_LOAI.ghi),
        Cot("Định lượng (gsm)", "gsm", kieu="nguyen", rong=16),
        Cot("Độ dày (micron)", "caliper_micron", kieu="nguyen", rong=16),
        Cot("Thớ giấy", "tho", rong=12),
        Cot("Đơn vị giá", "don_vi_gia", rong=14),
        Cot("Đơn giá", "don_gia", kieu="so", rong=16),
        Cot("Giá thị trường", "gia_thi_truong", kieu="so", rong=16),
        Cot("Dùng tính giá", "kho_tinh_gia", kieu="bool", rong=14),
        Cot("Ghi chú", "ghi_chu", rong=32),
        Cot("Công thức giá", "cong_thuc_gia", rong=36),
        Cot("Công thức lượng", "cong_thuc_luong", rong=36),
        CO_ACTIVE,
        # Cột đời cũ: một ô "MÃ1, MÃ2". Nay là sheet con — sheet con áp SAU nên nó thắng nếu file
        # có cả hai.
        Cot("NVL thay thế", "thay_the_ids", chi_nhap=True,
            doc=lambda gt, ctx: [_doc_thay_the(m, ctx) for m in _tach_danh_sach(gt, ctx)]),
    ),
    sheets_con=(_sheet_thay_the("Giấy thay thế", "Mã giấy"),),
)

VAT_TU = CatalogExcelSpec(
    loai="vat_tu", tieu_de="Vật tư khác", repo_cls=_VatTuRepo,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Đơn vị giá", "don_vi_gia", rong=14),
        Cot("Đơn giá", "don_gia", kieu="so", rong=16),
        Cot("Ghi chú", "ghi_chu", rong=32),
        Cot("Công thức giá", "cong_thuc_gia", rong=36),
        Cot("Công thức lượng", "cong_thuc_luong", rong=36),
        CO_ACTIVE,
        Cot("NVL thay thế", "thay_the_ids", chi_nhap=True,
            doc=lambda gt, ctx: [_doc_thay_the(m, ctx) for m in _tach_danh_sach(gt, ctx)]),
    ),
    sheets_con=(_sheet_thay_the("Vật tư thay thế", "Mã vật tư"),),
)

THANH_PHAM = CatalogExcelSpec(
    loai="thanh_pham", tieu_de="Thành phẩm", repo_cls=_ThanhPhamRepo,
    cot=(
        Cot("Mã", "ma"),
        # `ma` KHÔNG sửa được (repo gỡ khỏi payload update: mã đã nằm trong lô tồn và phiếu ghi
        # sổ) — nhưng vẫn phải có cột, vì nó là KHOÁ khớp dòng. `customer_id` cố ý vắng mặt: từ
        # mg 0228 thành phẩm không còn thuộc về khách, cột chỉ còn để tra lịch sử.
        Cot("Tên", "ten", rong=32),
        Cot("Đơn vị giá", "don_vi_gia", rong=14),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
    ),
)


# ======================================================================================
# 12 · Công đoạn
# ======================================================================================

_NHOM_NHAN = {
    "che ban": "prepress", "in": "print",
    "gia cong sau in": "finishing", "dich vu khac": "other",
}


def _bo_dau(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _doc_nhom(gt: Any, _ctx: NguCanh) -> str:
    """Nhận CẢ nhãn tiếng Việt của màn LẪN mã gốc — dropdown hiện "Chế bản", DB lưu `prepress`."""
    goc = str(gt or "").strip()
    if goc in NHOM:
        return goc
    ma = _NHOM_NHAN.get(_bo_dau(goc).lower())
    if not ma:
        raise ValueError(
            f'Nhóm "{goc}" không hợp lệ — chọn: Chế bản, In, Gia công sau in, Dịch vụ khác.')
    return ma


def _doc_dau_viec_hien_co(obj, ctx: NguCanh) -> list[dict]:
    return [
        {
            "piece_rate_id": dv.piece_rate_id,
            "nang_suat_nguoi_gio": float(dv.nang_suat_nguoi_gio),
            "nang_suat_nguoi_gio_min": (None if dv.nang_suat_nguoi_gio_min is None
                                        else float(dv.nang_suat_nguoi_gio_min)),
            "nang_suat_nguoi_gio_max": (None if dv.nang_suat_nguoi_gio_max is None
                                        else float(dv.nang_suat_nguoi_gio_max)),
            "don_vi_nang_suat": dv.don_vi_nang_suat,
            "so_nguoi_toi_thieu": dv.so_nguoi_toi_thieu,
            "so_nguoi_tieu_chuan": dv.so_nguoi_tieu_chuan,
            "so_nguoi_toi_da": dv.so_nguoi_toi_da,
        }
        for dv in (getattr(obj, "dau_viec_dinh_muc", None) or [])
    ]


def _giu_dau_viec(obj, ctx: NguCanh) -> list[dict]:
    """Định mức đầu việc ĐANG CÓ, đủ cả `vat_tu_ids` — gán lại khi file KHÔNG có sheet đó.

    `CongDoanRepository._sau_gan` thay TRỌN bảng con mỗi lần ghi, kể cả khi khoá vắng mặt trong
    `data`; không gán lại là nhập một file thiếu sheet cũng xoá sạch định mức của mọi công đoạn.
    """
    ra = _doc_dau_viec_hien_co(obj, ctx)
    for dong, dv in zip(ra, getattr(obj, "dau_viec_dinh_muc", None) or [], strict=False):
        dong["vat_tu_ids"] = list(dv.vat_tu_ids)
    return ra


def _doc_vat_tu_dau_viec(obj, ctx: NguCanh) -> list[dict]:
    return [
        {"piece_rate_id": dv.piece_rate_id, "vat_tu_id": vt}
        for dv in (getattr(obj, "dau_viec_dinh_muc", None) or [])
        for vt in dv.vat_tu_ids
    ]


def _gop_vat_tu_dau_viec(du_lieu: dict, rieng: dict, _ctx: NguCanh) -> None:
    """Nối sheet "Vật tư đầu việc" vào đúng dòng đầu việc (khoá: mã công việc khoán)."""
    dong = rieng.get("Vật tư đầu việc")
    if dong is None:
        return
    theo_dv: dict[Any, list[int]] = {}
    for r in dong:
        if r.get("vat_tu_id"):
            theo_dv.setdefault(r.get("piece_rate_id"), []).append(int(r["vat_tu_id"]))
    for dv in du_lieu.get("dau_viec_dinh_muc") or []:
        dv["vat_tu_ids"] = theo_dv.get(dv.get("piece_rate_id"), [])


def _cong_doan_truoc_khi_ghi(du_lieu: dict, _ctx: NguCanh, cu) -> dict:
    """Giữ `che_do_tinh` / `pricing_basis` — hai ô KHÔNG có trên màn nhưng `_validate` bắt buộc.

    Màn hiện tại luôn ép `theo_san_luong` + `per_other` ("CHỈ TÍNH THEO CÔNG THỨC"). Ở đây chỉ điền
    khi bản ghi CHƯA có giá trị: ép cứng là lặng lẽ đổi cấu hình của những dòng khai đường khác,
    và mỗi lần nhập lại một file không sửa gì cũng thành "cập nhật".
    """
    du_lieu.setdefault("che_do_tinh", getattr(cu, "che_do_tinh", None) or "theo_san_luong")
    du_lieu.setdefault("pricing_basis", getattr(cu, "pricing_basis", None) or "per_other")
    return du_lieu


CONG_DOAN = CatalogExcelSpec(
    loai="cong_doan", tieu_de="Công đoạn", repo_cls=CongDoanRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Tên hiển thị", "ten_hien_thi", rong=28),
        Cot("Nhóm", "nhom", doc=_doc_nhom, rong=18),
        Cot("Đơn vị vào", "don_vi_vao", rong=14),
        Cot("Đơn vị ra", "don_vi_ra", rong=14),
        Cot("Công thức sản lượng", "cong_thuc_san_luong", rong=36),
        Cot("Công thức giá", "cong_thuc_gia", rong=36),
        Cot("Kiểu bù hao", "kieu_bu_hao", rong=16),
        Cot("Mã bù hao", "bu_hao_id", doc=TRA_BU_HAO.doc, ghi=TRA_BU_HAO.ghi),
        Cot("Số tờ bù hao", "so_to_bu_hao", kieu="nguyen", rong=16),
        *_cot_to(nhan="Mã tổ phụ trách", nhan_ten="Tên tổ phụ trách", nhan_cu=("Tổ phụ trách",)),
        Cot("Khoán ghi theo", "khoan_ghi_theo", rong=18),
        Cot("% hao cho phép", "allowed_defect_pct", kieu="so", rong=16),
        Cot("Số hao cho phép", "allowed_defect_abs", kieu="so", rong=16),
        Cot("Chi phí chuẩn bị", "setup_cost", kieu="so", rong=18),
        Cot("Thời gian chuẩn bị", "setup_time", kieu="so", rong=18),
        Cot("Năng suất mặc định", "nang_suat", kieu="so", rong=18),
        Cot("Đơn giá theo cơ sở", "run_rate", kieu="so", rong=18),
        Cot("Sàn bậc đầu", "first_unit_floor", kieu="so", rong=16),
        Cot("Sàn cả công đoạn", "min_charge", kieu="so", rong=18),
        Cot("Cần dụng cụ", "requires_tooling", kieu="bool", rong=14),
        Cot("Loại dụng cụ", "tooling_type", rong=16),
        Cot("% phế", "spoilage_pct", kieu="so", rong=12),
        Cot("Chạy inline", "inline_flag", kieu="bool", rong=14),
        Cot("Ghi chú", "ghi_chu", rong=32),
        CO_ACTIVE,
        # Cột đời cũ (một ô "Máy in, Bế") — nay là sheet con "Nhóm máy cho phép".
        Cot("Nhóm máy cho phép", "nhom_may_cho_phep", chi_nhap=True, doc=_tach_danh_sach),
    ),
    sheets_con=(
        SheetCon(
            "Nhóm máy cho phép", field="nhom_may_cho_phep", rut_gon="ten",
            cot=(Cot("Nhóm máy", "ten", rong=24),),
        ),
        SheetCon(
            "Bậc đơn giá", field="rate_tiers",
            cot=(
                Cot("Từ sản lượng", "from_qty", kieu="so", rong=16),
                Cot("Đơn giá", "rate", kieu="so", rong=16),
                Cot("Kiểu", "kieu", rong=14),
                Cot("Theo biến", "driver", rong=18),
            ),
        ),
        SheetCon(
            "Bậc theo khổ", field="size_tiers",
            cot=(
                Cot("Đến (cm)", "den_cm", kieu="so", rong=14),
                Cot("Đơn giá", "don_gia", kieu="so", rong=16),
            ),
        ),
        SheetCon(
            "Đầu việc định mức", field="dau_viec_dinh_muc",
            cot=(
                Cot("Mã công việc khoán", "piece_rate_id",
                    doc=TRA_DAU_VIEC.doc, ghi=TRA_DAU_VIEC.ghi, rong=22),
                Cot("Năng suất người/giờ", "nang_suat_nguoi_gio", kieu="so", rong=20),
                Cot("Năng suất tối thiểu", "nang_suat_nguoi_gio_min", kieu="so", rong=20),
                Cot("Năng suất tối đa", "nang_suat_nguoi_gio_max", kieu="so", rong=20),
                Cot("Đơn vị năng suất", "don_vi_nang_suat", rong=18),
                Cot("Số người tối thiểu", "so_nguoi_toi_thieu", kieu="nguyen", rong=18),
                Cot("Số người tiêu chuẩn", "so_nguoi_tieu_chuan", kieu="nguyen", rong=18),
                Cot("Số người tối đa", "so_nguoi_toi_da", kieu="nguyen", rong=18),
            ),
            doc_hien_co=_doc_dau_viec_hien_co, giu_khi_vang=_giu_dau_viec,
        ),
        SheetCon(
            "Vật tư đầu việc", rieng=True,
            khoa_phu=(Cot("Mã công việc khoán", "piece_rate_id",
                          doc=TRA_DAU_VIEC.doc, ghi=TRA_DAU_VIEC.ghi, rong=22),),
            cot=(Cot("Mã vật tư", "vat_tu_id", doc=TRA_VAT_TU.doc, ghi=TRA_VAT_TU.ghi),),
            doc_hien_co=_doc_vat_tu_dau_viec,
        ),
    ),
    gop_con=_gop_vat_tu_dau_viec,
    truoc_khi_ghi=_cong_doan_truoc_khi_ghi,
    # Hai ô này KHÔNG có trên màn: `rebuildCatalogConfigs.tsx` luôn ép `theo_san_luong`+`per_other`
    # ("CHỈ TÍNH THEO CÔNG THỨC"). Bày ra Excel là mở lại một cách tính mà UI đã bỏ.
    loai_tru=frozenset({"che_do_tinh", "pricing_basis"}),
)


# ======================================================================================
# 13 · Máy & thiết bị
# ======================================================================================

_KHOA_JSON_BIET = ("chuan_bi_khoan", "lich_bao_tri")


def _doc_nhom_may(_obj, ctx: NguCanh) -> list[dict]:
    from ..repositories.may_thiet_bi_repo import NhomMayRepository

    rows = ctx.nho("nhom_may", lambda: NhomMayRepository(ctx.db).list_active())
    return [{"ten": r.ten} for r in rows]


def _ap_nhom_may(ctx: NguCanh, _obj, rows: list[dict], _actor_id: int | None) -> None:
    """THÊM nhóm máy còn thiếu. CỐ Ý không xoá nhóm vắng mặt trong file.

    Nhóm máy là mỏ neo của bình bài + tính giá (`NhomMayService.delete` chặn nhóm hệ thống và nhóm
    còn máy/công đoạn dùng). Một file Excel thiếu vài dòng không phải là ý định xoá cấu hình mà
    hai màn khác đang bám vào — muốn bỏ thì bỏ ngay tại ô Nhóm máy, nơi có câu chặn giải thích.
    """
    from ..repositories.may_thiet_bi_repo import NhomMayRepository
    from .may_thiet_bi_service import MayThietBiDuplicate, NhomMayService

    svc = NhomMayService(NhomMayRepository(ctx.db))
    dang_co = {(r.ten or "").strip().lower() for r in svc.list()}
    for r in rows:
        ten = (r.get("ten") or "").strip()
        if not ten or ten.lower() in dang_co:
            continue
        try:
            svc.create(ten)
        except MayThietBiDuplicate:
            pass          # nhóm đã có (khác hoa/thường) — không phải lỗi của người nhập
        dang_co.add(ten.lower())


def _doc_hang_muc(obj, _ctx: NguCanh) -> list[dict]:
    goi = ((getattr(obj, "fields_theo_loai", None) or {}).get("lich_bao_tri")) or []
    return [
        {"goi_id": g.get("id"), "id": hm.get("id"), "ten": hm.get("ten")}
        for g in goi if isinstance(g, dict)
        for hm in (g.get("hang_muc") or []) if isinstance(hm, dict)
    ]


def _gop_hang_muc(du_lieu: dict, rieng: dict, _ctx: NguCanh) -> None:
    """Nối sheet "Hạng mục bảo trì" vào đúng gói bảo trì (khoá: Mã gói)."""
    dong = rieng.get("Hạng mục bảo trì")
    if dong is None:
        return
    theo_goi: dict[Any, list[dict]] = {}
    for r in dong:
        theo_goi.setdefault(r.get("goi_id"), []).append(
            {"id": r.get("id"), "ten": r.get("ten")})
    tui = du_lieu.get("fields_theo_loai") or {}
    for g in tui.get("lich_bao_tri") or []:
        g["hang_muc"] = theo_goi.get(g.get("id"), [])


def _may_truoc_khi_ghi(du_lieu: dict, _ctx: NguCanh, _cu) -> dict:
    """Cấp mã cho gói bảo trì / hạng mục mới khai trong Excel.

    Mã gói (`hm-...`) là NEO của phiếu bảo trì (`ky_thuat_bao_tri.goi_id`): gói cũ giữ NGUYÊN mã đã
    có, chỉ dòng để trống mới được cấp mã. Bỏ trống rồi tự sinh là đúng ý người khai — họ thêm một
    gói mới, chứ không phải đổi tên gói cũ.
    """
    tui = du_lieu.get("fields_theo_loai")
    if not isinstance(tui, dict):
        return du_lieu
    n = 0
    for g in tui.get("lich_bao_tri") or []:
        if not isinstance(g, dict):
            continue
        if not g.get("id"):
            n += 1
            g["id"] = f"hm-x{n}-{(du_lieu.get('ma') or '').lower()}"
        for i, hm in enumerate(g.get("hang_muc") or [], start=1):
            if isinstance(hm, dict) and not hm.get("id"):
                hm["id"] = f"{g['id']}-{i}"
    return du_lieu


def _khoa_la(obj, _ctx: NguCanh) -> dict:
    """Khoá trong `fields_theo_loai` mà workbook KHÔNG diễn giải — giữ để round-trip không mất."""
    tui = getattr(obj, "fields_theo_loai", None) or {}
    return {k: v for k, v in tui.items() if k not in _KHOA_JSON_BIET}


def _gop_khoa_la(du_lieu: dict, giu: dict, _ctx: NguCanh) -> None:
    tui = du_lieu.get("fields_theo_loai")
    tui = dict(tui) if isinstance(tui, dict) else {}
    for k, v in giu.items():
        if k not in _KHOA_JSON_BIET:
            tui[k] = v
    du_lieu["fields_theo_loai"] = tui


MAY_THIET_BI = CatalogExcelSpec(
    loai="may_thiet_bi", tieu_de="Máy thiết bị", repo_cls=MayThietBiRepository,
    cot=(
        Cot("Mã", "ma"),
        Cot("Tên", "ten", rong=32),
        Cot("Loại máy", "loai_may", rong=18),
        Cot("Hãng sản xuất", "hang_san_xuat", rong=20),
        Cot("Model", "model", rong=18),
        Cot("Số seri", "so_seri", rong=18),
        Cot("Ghi chú", "ghi_chu", rong=32),
        Cot("Tốc độ (trung bình)", "toc_do", kieu="so", rong=20),
        Cot("Tốc độ tối thiểu", "toc_do_min", kieu="so", rong=18),
        Cot("Tốc độ tối đa", "toc_do_max", kieu="so", rong=18),
        Cot("Đơn vị tốc độ", "don_vi_toc_do", rong=16),
        Cot("Công thức lượng", "cong_thuc_luong", rong=36),
        Cot("Thời gian canh máy mặc định", "makeready_time_default", kieu="so", rong=26),
        Cot("Số nhân công", "so_nhan_cong", kieu="so", rong=16),
        Cot("Khổ tối đa - dài (mm)", "kho_max_dai", kieu="nguyen", rong=20),
        Cot("Khổ tối đa - rộng (mm)", "kho_max_rong", kieu="nguyen", rong=20),
        Cot("Khổ tối thiểu - dài (mm)", "kho_min_dai", kieu="nguyen", rong=22),
        Cot("Khổ tối thiểu - rộng (mm)", "kho_min_rong", kieu="nguyen", rong=22),
        Cot("Khổ kèm - dài (mm)", "kho_kem_dai", kieu="nguyen", rong=20),
        Cot("Khổ kèm - rộng (mm)", "kho_kem_rong", kieu="nguyen", rong=20),
        Cot("Vùng in - dài (mm)", "vung_in_dai", kieu="nguyen", rong=20),
        Cot("Vùng in - rộng (mm)", "vung_in_rong", kieu="nguyen", rong=20),
        Cot("Nhịp giấy (mm)", "nhip_giay_mm", kieu="nguyen", rong=16),
        Cot("Lề hông (mm)", "le_hong_mm", kieu="nguyen", rong=16),
        Cot("Đuôi thẳng màu (mm)", "duoi_thang_mau_mm", kieu="nguyen", rong=20),
        CO_ACTIVE,
        # Cột đời cũ: cả túi JSON trong MỘT ô. Nay tách thành ba sheet đọc được; sheet con áp SAU
        # nên file mới thắng, file cũ vẫn nhập được nguyên trạng.
        Cot("Field theo loại (JSON)", "fields_theo_loai", kieu="json", chi_nhap=True),
    ),
    sheets_con=(
        SheetCon("Nhóm máy", toan_cuc=True, thu_tu=False,
                 cot=(Cot("Tên nhóm", "ten", rong=24),),
                 doc_hien_co=_doc_nhom_may, ap_dung=_ap_nhom_may),
        SheetCon(
            "Khoản chuẩn bị", trong_json=("fields_theo_loai", "chuan_bi_khoan"),
            cot=(
                Cot("Tên khoản", "ten", rong=30),
                Cot("Số phút", "phut", kieu="so", rong=14),
            ),
        ),
        SheetCon(
            "Gói bảo trì", trong_json=("fields_theo_loai", "lich_bao_tri"),
            cot=(
                # GIỮ NGUYÊN mã gói khi sửa — phiếu bảo trì neo vào nó (`ky_thuat_bao_tri.goi_id`).
                # Thêm gói MỚI thì tự gõ một mã bất kỳ (để trống hệ cũng cấp, nhưng khi đó sheet
                # "Hạng mục bảo trì" không biết móc vào gói nào).
                Cot("Mã gói", "id", rong=22),
                Cot("Việc", "viec", rong=30),
                Cot("Chu kỳ số", "so", kieu="nguyen", rong=14),
                Cot("Chu kỳ đơn vị", "don_vi", rong=16),
                Cot("Ngày bắt đầu", "ngay_bat_dau", rong=16),
                Cot("Dừng máy (phút)", "dung_phut", kieu="so", rong=18),
                Cot("Lần cuối", "lan_cuoi", rong=16),
            ),
        ),
        SheetCon(
            "Hạng mục bảo trì", rieng=True,
            khoa_phu=(Cot("Mã gói", "goi_id", rong=22),),
            cot=(
                Cot("Mã hạng mục", "id", rong=22),
                Cot("Tên hạng mục", "ten", rong=32),
            ),
            doc_hien_co=_doc_hang_muc,
        ),
    ),
    gop_con=_gop_hang_muc,
    truoc_khi_ghi=_may_truoc_khi_ghi,
    sheet_an=_khoa_la,
    gop_an=_gop_khoa_la,
)


# ======================================================================================
# Sổ đăng ký — router tra spec theo `ten` của màn
# ======================================================================================

SPECS: dict[str, CatalogExcelSpec] = {
    s.loai: s for s in (
        KHO_HANG, BU_HAO, KHUON_BE, LOAI_SAN_PHAM, SAN_XUAT_LY_DO, CONG_VIEC_KHOAN,
        DON_VI_DO, CHUNG_LOAI_GIAY, GIAY, VAT_TU, THANH_PHAM, CONG_DOAN, MAY_THIET_BI,
    )
}
