"""Seed LUỒNG THẬT đầu-cuối: tính giá → báo giá → đơn hàng bán → kế hoạch sản xuất.

Luồng ĐỦ: 1 phiếu tính giá 3 sản phẩm (Ruột sách · Bìa sách · Thẻ nhân viên) → 1 báo giá (ruột +
bìa cùng `nhom` nên bản in gửi khách gộp 1 dòng "quyển sách") → 1 đơn hàng bán đã chốt, đủ cọc,
đã chuyển xuống sản xuất → 3 lệnh sản xuất `san_sang` (chờ xếp lịch).

Luồng CHỜ LẬP LỆNH: phiếu đợt 2 (500 thẻ in bù cho nhân viên mới) → báo giá → đơn đã chuyển
xuống sản xuất mà CHƯA có lệnh → nằm ở tab "hàng chờ" của màn Kế hoạch SX.

Số liệu bám xưởng in offset THẬT: cả 3 sản phẩm chạy tờ 65×86 — ruột A5 bình 16 con/mặt = tay 32
trang (160 trang = 5 tay), bìa 8 con/tờ, thẻ 99 con/tờ; bù hao tra bảng bậc của xưởng; đơn giá
công đoạn theo giá thị trường 2026. Giá vốn do ENGINE tính (`compute_phieu_snapshot`) — không có
số nào gõ tay.

Idempotent: guard theo tên phiếu; danh mục bổ sung guard theo mã. Chỉ chạy trong SEED_DEMO
(gọi cuối `seed_all`).

Công đoạn khâu SÁCH/THẺ được bổ sung TẠI ĐÂY chứ không nhét vào `seed_rebuild.py`: file đó chỉ
seed khi bảng CÒN RỖNG, mà DB dev đã có 6 công đoạn nên thêm vào đó sẽ không bao giờ chạy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.cong_doan import CongDoan, CongDoanDauViec
from .models.customer import Customer
from .models.khuon_be import KhuonBe
from .models.loai_san_pham import LoaiSanPham
from .models.may_thiet_bi import MayThietBi
from .models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia
from .models.vat_lieu_kho import GiayNguyen
from .repositories.audit_repo import AuditLogRepository
from .repositories.document_sequence_repo import DocumentSequenceRepository
from .repositories.lsx_repo import LsxRepository
from .repositories.user_repo import UserRepository
from .services.sequence_service import SequenceService
from .services.tinh_gia_service import compute_phieu_snapshot

# Tên phiếu = khóa idempotent của từng luồng (chạy lại thì bỏ qua đúng luồng đã có).
TEN_PHIEU = "Kỷ yếu 25 năm + thẻ nhân viên An Phát"
TEN_PHIEU_BO_SUNG = "Thẻ nhân viên bổ sung (nhân viên mới) An Phát"
NHOM_SACH = "Kỷ yếu 25 năm An Phát"   # nhãn gộp dòng ruột + bìa khi in báo giá / xác nhận đơn

SL_SACH = 1000       # cuốn
SL_THE = 1000        # thẻ
SL_THE_BO_SUNG = 500  # thẻ — đợt 2 cho nhân viên mới
MARKUP_PCT = 18.0    # markup báo giá (sách ấn phẩm nội bộ, khách quen)
VAT_PCT = 10.0
DEPOSIT_PCT = 30.0

# --- Công đoạn còn THIẾU cho khâu sách + thẻ (danh mục rebuild chỉ có 6 mã chung) -------------
# (ma, ten, nhom, cong_thuc_gia, run_rate, setup_time, nang_suat, may_ma, to_ten, kieu_bu_hao,
#  so_to_bu_hao, requires_tooling, tooling_type, ghi_chu)
# Giá THỊ TRƯỜNG 2026 (đ): gấp máy 120/tờ · vào keo 1.500/cuốn · xén 3 mặt 250/cuốn ·
# cán màng 2.500/m² · bế thành phẩm 250/tờ · đóng gói 100/cái.
# `to_ten` = tổ nhận việc: gắn NGAY lúc tạo vì `seed_san_xuat_org` (gắn công đoạn → tổ) đã chạy
# trước file này, công đoạn sinh sau sẽ không tổ nào nhận → lệnh SX mắc ở "thiếu tổ/máy".
_CONG_DOAN_MOI: list[tuple] = [
    ("CD-0007", "Gấp tay sách", "finishing", "to_dau_vao * 120", 120, 15, 3000, None,
     "Tổ Đóng gói", "khong", 50, False, None,
     "Gấp tay 32 trang (4 nếp) trên máy gấp."),
    ("CD-0008", "Bắt tay + vào keo (đóng cuốn)", "finishing", "so_luong * 1500", 1500, 30, 600, None,
     "Tổ Đóng gói", "khong", 50, False, None, "Keo nhiệt gáy vuông; ruột ≤ 300 trang."),
    ("CD-0009", "Xén 3 mặt thành phẩm", "finishing", "so_luong * 250", 250, 10, 1200, None,
     "Tổ Bế & Xén", "khong", 50, False, None, "Xén 3 mặt sau khi keo đã nguội."),
    ("CD-0010", "Cán màng mờ", "finishing",
     "max(dai_in * rong_in * so_mat * to_dau_vao * 2500, 150000)", 2500, 20, 3000, "CM-03",
     "Tổ Cán màng", "co_dinh", 50, False, None, "2.500đ/m² mỗi mặt, sàn 150.000đ/lượt cán."),
    ("CD-0011", "Bế thành phẩm", "finishing", "to_dau_vao * 250", 250, 60, None, "BE-01",
     "Tổ Bế & Xén", "co_dinh", 30, True, "khuon_be", "Bế con + góc tròn + lỗ dây; cần khuôn bế."),
    ("CD-0012", "Đóng gói + nhập kho", "finishing", "so_luong * 100", 100, 5, 800, None,
     "Tổ Đóng gói", "khong", 50, False, None, "Đếm, bó, dán nhãn, nhập kho thành phẩm."),
    # Ghép màng metalize là công đoạn RIÊNG, không phải "cán màng mờ": màng khác, giá bán khác, và
    # công khoán của thợ cũng khác (250 đ/m² so với 150) — xem bảng CÔNG KHOÁN CÁN·PHỦ của xưởng.
    ("CD-0013", "Ghép màng metalize", "finishing",
     "max(dai_in * rong_in * so_mat * to_dau_vao * 4000, 200000)", 4000, 25, 2500, "CM-03",
     "Tổ Cán màng", "co_dinh", 50, False, None, "4.000đ/m², sàn 200.000đ/lượt ghép."),
]

# Đơn vị VÀO/RA của khâu sách — KHÔNG để mặc định `cai`. Khai sai thành `cai → cai` thì chuỗi bù
# hao ngược mất ranh giới tờ↔cuốn, chạy 1:1 và ra số giấy hụt đúng bằng số tay mỗi cuốn.
#
# Đường sách đủ ba chặng: TỜ NGUYÊN → TỜ IN → TAY → CUỐN. Trước đây hai bước này khai `to → to`
# rồi `to → cai`, tức nhảy cóc qua mức TAY: gấp xong vẫn gọi là tờ in, tới vào keo mới đổi thẳng
# tờ → cuốn. Số giấy vẫn đúng (cầu tắt `to → cai` gánh cả 1/so_tay) nhưng bù hao của bước gấp và
# bước bắt tay bị tra bậc ở SAI ĐƠN VỊ, và người đọc lệnh không thấy tay ở đâu ra.
#
_DON_VI_KHAU_SACH: dict[str, tuple[str, str]] = {
    "CD-0007": ("to", "tay"),    # gấp tay: 1 tờ in gấp nguyên thành 1 tay (hệ số 1)
    "CD-0008": ("tay", "cai"),   # bắt tay + vào keo: gom `so_tay` tay → 1 cuốn
    "CD-0009": ("cai", "cai"),   # xén 3 mặt: đếm cuốn thành phẩm, không đổi mức
    "CD-0010": ("to", "to"),     # cán màng mờ: chạy tờ, ra tờ
    "CD-0011": ("to", "cai"),    # bế thành phẩm: 1 tờ ra `so_tp` con → thành phẩm
    "CD-0012": ("cai", "cai"),   # đóng gói: đếm thành phẩm
    "CD-0013": ("to", "to"),     # ghép màng metalize: chạy tờ, ra tờ
}

# --- Bảng CÔNG KHOÁN của tổ (số hoá đúng tờ Excel xưởng đang dùng) ------------------------------
# (ten_to, ma, ten_dau_viec, [mã công đoạn — CHỈ để suy ra tổ], don_vi, don_gia, ghi_chu)
# Đơn giá chỉ treo vào TỔ. Danh sách công đoạn ở đây KHÔNG được lưu vào bảng: nó chỉ dùng để tìm
# `department_id` đúng của tổ, vì tên tổ trong Excel và tên phòng ban trong hệ có thể lệch nhau.
_DON_GIA_KHOAN: list[tuple] = [
    # Bước IN là bước chính của mọi lệnh — thiếu đơn giá khoán ở đây thì màn bước hiện "chưa có
    # bảng khoán" và tiền công của cả lệnh hụt mất phần lớn nhất. Thêm 12/08/2026 (trước đó dev
    # phải gõ tay `KH-0001`, làm sạch DB một cái là mất).
    ("Tổ In offset", "IN-01K", "In 2 màu", ["CD-0002"], "tờ", 600, None),
    ("Tổ Cán màng", "CP-01", "Cán bóng · cán mờ · phủ UV nước · UV mờ",
     ["CD-0003", "CD-0010"], "m²", 150,
     "Làm theo nhóm; tổ trưởng lấy 5%/tổng doanh thu, phần còn lại nhóm tự chia và báo kế toán."),
    ("Tổ Cán màng", "CP-02", "Ghép màng metalize", ["CD-0013"], "m²", 250, None),
    # Cùng công đoạn Bế nhưng hai cách làm hai giá → bước lệnh BẮT BUỘC người chọn, máy không đoán.
    ("Tổ Bế & Xén", "BE-01", "Bế máy tự động", ["CD-0011"], "tờ", 250, None),
    ("Tổ Bế & Xén", "BE-02", "Bế tay (hàng ăn gian nhíp, SL ít)", ["CD-0011"], "tờ", 400, None),
    ("Tổ Bế & Xén", "XEN-01", "Xén 3 mặt thành phẩm", ["CD-0009"], "cuốn", 120, None),
    ("Tổ Đóng gói", "TP-01", "Gấp tay sách máy", ["CD-0007"], "tờ", 60, None),
    ("Tổ Đóng gói", "TP-02", "Bắt tay + vào keo gáy vuông", ["CD-0008"], "cuốn", 700, None),
    ("Tổ Đóng gói", "TP-03", "Đếm, bó, đóng gói thành phẩm", ["CD-0012"], "cuốn", 40, None),
]

# Canh máy bước IN: danh mục `CD-0002 In offset` để setup_time = 0 nên Gantt vẽ lệnh in "vào máy
# là chạy". Điền 45' (makeready 4-6 màu thực tế) — CHỈ khi đang trống, không đè số đã khai.
_SETUP_IN_MAC_DINH = 45.0

# --- Năng lực máy dùng trong luồng (chỉ điền khi cột còn TRỐNG — không đè số người dùng đã khai).
# (ma, toc_do tờ/giờ, makeready phút). Cột rửa mực đã bỏ khỏi hệ nên seed thôi điền.
_MAY_NANG_LUC: list[tuple[str, float, float]] = [
    ("IN-01", 8000, 30),    # Mitsubishi 2 màu 72×102 — ruột sách đen
    ("IN-02", 9000, 45),    # Mitsubishi 4 màu 79×109
    ("IN-04", 10000, 60),   # Mitsubishi 6 màu 72×102
    ("CM-03", 3000, 20),    # cán màng 800×1080
    ("BE-01", 4000, 60),    # bế tự động Yawa 1050
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_cong_doan(db: Session) -> dict[str, int]:
    """Bổ sung công đoạn khâu sách/thẻ (idempotent theo mã). Trả map mã → id của MỌI công đoạn."""
    from .models.department import Department

    to_ids = {d.name: d.id for d in db.execute(select(Department)).scalars()}
    co_san = {c.ma: c for c in db.execute(select(CongDoan)).scalars()}
    for (ma, ten, nhom, ct, rate, setup, ns, may_ma, to_ten, kieu_bh, so_to_bh,
         tooling, tooling_type, ghi_chu) in _CONG_DOAN_MOI:
        if ma in co_san:
            continue
        db.add(CongDoan(
            ma=ma, ten=ten, nhom=nhom, che_do_tinh="theo_san_luong", pricing_basis="per_other",
            cong_thuc_gia=ct, run_rate=rate, setup_time=setup, nang_suat=ns,
            department_id=to_ids.get(to_ten),
            kieu_bu_hao=kieu_bh, so_to_bu_hao=so_to_bh,
            requires_tooling=tooling, tooling_type=tooling_type, ghi_chu=ghi_chu,
        ))
    cd_in = co_san.get("CD-0002")
    if cd_in is not None and not cd_in.setup_time:
        cd_in.setup_time = _SETUP_IN_MAC_DINH
    db.flush()
    # Sửa cả công đoạn ĐÃ CÓ, không chỉ cái mới tạo: DB demo cũ đang giữ `cai → cai` mặc định.
    for c in db.execute(select(CongDoan)).scalars():
        dv = _DON_VI_KHAU_SACH.get(c.ma)
        if dv and (c.don_vi_vao, c.don_vi_ra) != dv:
            c.don_vi_vao, c.don_vi_ra = dv
    db.flush()
    return {c.ma: c.id for c in db.execute(select(CongDoan)).scalars()}


def _ensure_may_nang_luc(db: Session) -> None:
    """Điền tốc độ / makeready cho các máy của luồng — CHỈ khi cột còn trống."""
    by_ma = {m.ma: m for m in db.execute(select(MayThietBi)).scalars()}
    for ma, toc_do, makeready in _MAY_NANG_LUC:
        m = by_ma.get(ma)
        if m is None:
            continue
        if not m.toc_do:
            m.toc_do = toc_do
            m.don_vi_toc_do = "to_gio"
        if not m.makeready_time_default:
            m.makeready_time_default = makeready
    db.flush()


def _ensure_don_gia_khoan(db: Session) -> None:
    """Số hoá bảng CÔNG KHOÁN của từng tổ (idempotent theo mã). Chạy SAU `seed_san_xuat_org` vì cần
    các tổ đã tồn tại — không có tổ thì bỏ qua dòng đó, KHÔNG tạo tổ mới ở đây."""
    from .models.department import Department
    from .models.piece_work import PieceRate

    to_ids = {d.name: d.id for d in db.execute(select(Department)).scalars()}
    # Tổ của đầu việc SUY TỪ CÔNG ĐOẠN nó áp dụng, không hardcode theo tên tổ: tổ của công đoạn là
    # nguồn sự thật duy nhất (`cong_doan.department_id`), và nó có thể lệch tên tôi đoán ở đây —
    # ĐÃ LỆCH THẬT: "Đóng gói + nhập kho" bị heuristic seed xếp vào Tổ KCS vì có chữ "nhập kho",
    # nên đơn giá khai cho "Tổ Đóng gói" sẽ không bao giờ khớp bước đó.
    cd_rows = {c.ma: c for c in db.execute(select(CongDoan)).scalars()}
    co_san = {r.code for r in db.execute(select(PieceRate)).scalars() if r.code}
    rows = []
    for ten_to, ma, ten, cds, don_vi, don_gia, ghi_chu in _DON_GIA_KHOAN:
        if ma in co_san:
            continue
        dept_id = next(
            (cd_rows[c].department_id for c in cds if c in cd_rows and cd_rows[c].department_id),
            to_ids.get(ten_to),
        )
        if dept_id is None:
            continue   # chưa có tổ nào nhận → khai đơn giá cũng không ai dùng
        rows.append(PieceRate(
            group_name=ten_to, department_id=dept_id, code=ma, name=ten,
            unit=don_vi, unit_price=don_gia,
            note=ghi_chu, is_active=True,
        ))
    if rows:
        db.add_all(rows)
        db.commit()


def _ensure_dinh_muc_to(db: Session) -> None:
    """Gắn đầu việc vào công đoạn theo ĐÚNG bản đồ khai ở `_DON_GIA_KHOAN`.


    Sai này không chỉ xấu mắt: từ khi đầu việc mang theo VẬT TƯ (BOM, mg 0191), gắn nhầm đầu việc là
    bung nhầm vật tư xuống lệnh. Bản đồ phải là nguồn sự thật duy nhất.

    Vẫn idempotent: công đoạn đã có định mức thì không đụng — người dùng khai tay không bị đè.
    """
    from .models.piece_work import PieceRate

    rate_theo_ma = {
        r.code: r for r in db.execute(
            select(PieceRate).where(PieceRate.is_active.is_(True))
        ).scalars() if r.code
    }
    cd_rows = {c.ma: c for c in db.execute(select(CongDoan)).scalars()}
    # Lật bản đồ: công đoạn → các đầu việc THẬT SỰ làm ở đó.
    theo_cd: dict[str, list[str]] = {}
    for _to, ma_rate, _ten, cds, *_ in _DON_GIA_KHOAN:
        for cd_ma in cds:
            theo_cd.setdefault(cd_ma, []).append(ma_rate)
    for cd_ma, ma_rates in theo_cd.items():
        cd = cd_rows.get(cd_ma)
        if cd is None or cd.dau_viec_dinh_muc:
            continue
        for ma_rate in ma_rates:
            rate = rate_theo_ma.get(ma_rate)
            # Đầu việc phải thuộc ĐÚNG tổ của công đoạn — service kiểm luật này, seed cũng phải
            # theo, không thì dữ liệu mồi vào rồi sửa ở form là bị chặn không lưu lại được.
            if rate is None or rate.department_id != cd.department_id:
                continue
            cd.dau_viec_dinh_muc.append(CongDoanDauViec(
                piece_rate_id=rate.id, nang_suat_nguoi_gio=float(cd.nang_suat or 500),
                so_nguoi_tieu_chuan=1, so_nguoi_toi_da=3,
            ))
    db.commit()


def _ensure_loai_the(db: Session) -> int | None:
    """Loại sản phẩm 'Thẻ nhân viên' (idempotent theo mã) — thẻ không phải name card."""
    lsp = db.execute(select(LoaiSanPham).where(LoaiSanPham.ma == "LSP-0008")).scalars().first()
    if lsp is None:
        lsp = LoaiSanPham(ma="LSP-0008", ten="Thẻ nhân viên", structural_type="flat")
        db.add(lsp)
        db.flush()
    return lsp.id


def _ensure_khuon_the(db: Session, khach_ten: str | None) -> int | None:
    """Một dòng mẫu cho KHO KHUÔN — nay chỉ để danh mục có dữ liệu xem, không lệnh nào trỏ tới.

    Trước 16/08/2026 con dao này được gán vào lệnh thẻ để lệnh rời trạng thái 'chờ bổ sung'; cả
    ràng buộc đó lẫn cột `khuon_be_id` đã bỏ (mg `0203`).
    """
    kb = db.execute(select(KhuonBe).where(KhuonBe.ma == "KB-0006")).scalars().first()
    if kb is None:
        kb = KhuonBe(
            ma="KB-0006", ten="Khuôn bế thẻ nhân viên 54×86 (góc R3 + lỗ dây)",
            so_ke="Kệ B2 — kho khuôn", loai="khuon_be",
            ngay_ve_du_kien=date.today() - timedelta(days=20), tinh_trang="dang_dung",
            ghi_chu="Bế 99 con/tờ 65×86.",
        )
        db.add(kb)
        db.flush()
    return kb.id


def _giay(db: Session, ma: str) -> GiayNguyen | None:
    return db.execute(select(GiayNguyen).where(GiayNguyen.ma == ma)).scalars().first()


def _may_id(db: Session, ma: str) -> int | None:
    m = db.execute(select(MayThietBi).where(MayThietBi.ma == ma)).scalars().first()
    return m.id if m else None


def _buoc(cd: dict[str, int], ma: str, ten: str, thu_tu: int, *, so_mat: int = 1) -> PhieuThanhPham:
    """1 dòng công đoạn của sản phẩm. KHÔNG có đơn giá ở dòng (giá nằm ở công thức danh mục)."""
    return PhieuThanhPham(thu_tu=thu_tu, cong_doan_id=cd.get(ma), ten=ten, so_mat=so_mat)


def _tao_phieu_tinh_gia(db: Session, *, cd: dict[str, int], sale_id: int | None,
                        sale_ten: str, lsp_sach_id: int | None,
                        lsp_the_id: int | None, created: datetime) -> PhieuTinhGia:
    """Phiếu tính giá 3 sản phẩm. Khổ ①②③ + chừa + bù hao khai như sale thật khai trên phiếu."""
    ford70 = _giay(db, "FORD-70-65x86")
    couche300 = _giay(db, "COUCHE-300-65x86")
    may_2mau = _may_id(db, "IN-01")   # 2 màu 72×102 — ruột đen 1+1 màu
    may_6mau = _may_id(db, "IN-04")   # 6 màu 72×102 — bìa + thẻ 4 màu

    p = PhieuTinhGia(
        ma=_ma_phieu(db, created),
        ten_san_pham=TEN_PHIEU,
        kho_thanh_pham="Sách 14,5×20,5 cm · thẻ 5,4×8,6 cm",
        loai_san_pham_id=lsp_sach_id,
        so_luong=SL_SACH,
        ktv=sale_ten,
        created_by=sale_id,
        ghi_chu="Khách xin báo giá gộp: 1.000 cuốn kỷ yếu (bìa rời, keo gáy vuông) + "
                "1.000 thẻ nhân viên. Giao 1 lần tại kho khách.",
        created_at=created,
        updated_at=created,
    )

    # ── ① RUỘT SÁCH — 160 trang A5 trên tờ 65×86: 16 con/mặt = tay 32 trang → 5 tay/cuốn ──────
    ruot = PhieuThanhPhan(
        thu_tu=0, loai_thanh_phan="ruot", ten="Ruột sách 160 trang",
        dai_thanh_pham=205, rong_thanh_pham=145,
        so_trang=160, trang_moi_tay=32,
        so_luong=SL_SACH, don_vi_tinh="cuốn", nhom_bao_gia=NHOM_SACH,
        loai_san_pham_id=lsp_sach_id,
        giay_id=(ford70.id if ford70 else None), kho_nguyen="650×860",
        kho_nguyen_dai=860, kho_nguyen_rong=650, nguon_giay="cong_ty",
        # Chừa tờ in KHÔNG khai ở phiếu nữa — engine lấy theo danh mục Máy (nhíp/lề hông/đuôi).
        co_in=True, quy_cach_in="hai_mat", kho_in_dai=860, kho_in_rong=650,
        # 16 con/mặt trên tờ 65×86 (A5 145×205: 4 ngang × 4 dọc) = 32 trang/tay. Với sách, `so_con`
        # KHÔNG vào công thức giấy (tờ gấp nguyên vẹn thành tay) — nó để vẽ sơ đồ bình bài và kiểm
        # khổ có vừa tờ, nên phải là số THẬT chứ đừng để 1.
        so_con=16, con_auto=False,
        may_id=may_2mau, so_mau_a=1, so_mau_b=1,
        ghi_chu_ky_thuat="Bình tay 32 trang (16 con/mặt) trên tờ 65×86 → 5 tay/cuốn. "
                         "In đen 1+1 màu máy 2 màu. Gấp máy, bắt tay, keo gáy vuông.",
    )
    for i, (ma, ten) in enumerate([
        ("CD-0001", "Ghi kẽm CTP"),
        ("CD-0002", "In offset"),
        ("CD-0007", "Gấp tay sách"),
        ("CD-0008", "Bắt tay + vào keo (đóng cuốn)"),
        ("CD-0009", "Xén 3 mặt thành phẩm"),
        ("CD-0012", "Đóng gói + nhập kho"),
    ]):
        ruot.thanh_phams.append(_buoc(cd, ma, ten, i))

    # ── ② BÌA SÁCH — bìa rời, khổ mở 300×205 (2 tay + gáy 10mm), Couché 300 cán màng mờ ───────
    bia = PhieuThanhPhan(
        thu_tu=1, loai_thanh_phan="bia", ten="Bìa sách (bìa rời, cán màng mờ)",
        dai_thanh_pham=300, rong_thanh_pham=205,   # khổ MỞ của bìa (2 tay + gáy 10mm)
        so_to_per_sp=1, so_luong=SL_SACH, don_vi_tinh="cuốn", nhom_bao_gia=NHOM_SACH,
        loai_san_pham_id=lsp_sach_id,
        giay_id=(couche300.id if couche300 else None), kho_nguyen="650×860",
        kho_nguyen_dai=860, kho_nguyen_rong=650, nguon_giay="cong_ty",
        bleed_mm=3,
        co_in=True, quy_cach_in="mot_mat", kho_in_dai=860, kho_in_rong=650,
        con_auto=True, may_id=may_6mau, so_mau_a=4,
        ghi_chu_ky_thuat="In 4 màu mặt ngoài, mặt trong để trắng. Cán màng mờ mặt ngoài. "
                         "Gáy 10mm tính theo ruột 160 trang Ford 70.",
    )
    for i, (ma, ten, so_mat) in enumerate([
        ("CD-0001", "Ghi kẽm CTP", 1),
        ("CD-0002", "In offset", 1),
        ("CD-0010", "Cán màng mờ", 1),
    ]):
        bia.thanh_phams.append(_buoc(cd, ma, ten, i, so_mat=so_mat))

    # ── ③ THẺ NHÂN VIÊN — 54×86mm (khổ CR80), Couché 300, cán mờ 2 mặt, bế góc tròn ───────────
    the = PhieuThanhPhan(
        thu_tu=2, loai_thanh_phan="to_roi", ten="Thẻ nhân viên 54×86mm",
        dai_thanh_pham=86, rong_thanh_pham=54,
        so_to_per_sp=1, so_luong=SL_THE, don_vi_tinh="thẻ",
        loai_san_pham_id=lsp_the_id,
        giay_id=(couche300.id if couche300 else None), kho_nguyen="650×860",
        kho_nguyen_dai=860, kho_nguyen_rong=650, nguon_giay="cong_ty",
        bleed_mm=2,
        co_in=True, quy_cach_in="hai_mat", kho_in_dai=860, kho_in_rong=650,
        con_auto=True, may_id=may_6mau, so_mau_a=4, so_mau_b=1,
        ghi_chu_ky_thuat="Mặt trước 4 màu (ảnh + logo), mặt sau 1 màu đen (nội quy). "
                         "Cán màng mờ 2 mặt, bế con + góc tròn R3 + lỗ dây, khuôn KB-0006.",
    )
    for i, (ma, ten, so_mat) in enumerate([
        ("CD-0001", "Ghi kẽm CTP", 1),
        ("CD-0002", "In offset", 1),
        ("CD-0010", "Cán màng mờ", 2),
        ("CD-0011", "Bế thành phẩm", 1),
        ("CD-0012", "Đóng gói + nhập kho", 1),
    ]):
        the.thanh_phams.append(_buoc(cd, ma, ten, i, so_mat=so_mat))

    p.thanh_phans.extend([ruot, bia, the])
    db.add(p)
    db.flush()
    compute_phieu_snapshot(db, p)   # giá vốn 3 sản phẩm do ENGINE tính
    db.flush()
    return p


def _tao_phieu_the_bo_sung(db: Session, *, cd: dict[str, int], sale_id: int | None,
                           sale_ten: str, lsp_the_id: int | None,
                           created: datetime) -> PhieuTinhGia:
    """Phiếu ĐỢT 2: 500 thẻ in bù cho nhân viên mới — cùng maquette, khác số lượng.

    Đơn nhỏ nên đơn giá/thẻ cao hơn hẳn đợt 1 (kẽm + canh máy chia cho 500 thay vì 1.000) —
    đúng thực tế và cũng là ví dụ để xem engine phản ứng theo quy mô.
    """
    couche300 = _giay(db, "COUCHE-300-65x86")
    p = PhieuTinhGia(
        ma=_ma_phieu(db, created), ten_san_pham=TEN_PHIEU_BO_SUNG,
        kho_thanh_pham="5,4×8,6 cm", loai_san_pham_id=lsp_the_id,
        so_luong=SL_THE_BO_SUNG, ktv=sale_ten, created_by=sale_id,
        ghi_chu="Đợt 2: in bù thẻ cho 500 nhân viên mới + thẻ hỏng. Maquette giữ nguyên đợt 1, "
                "chỉ đổi danh sách tên. Khách hỏi giá gấp.",
        created_at=created, updated_at=created,
    )
    the = PhieuThanhPhan(
        thu_tu=0, loai_thanh_phan="to_roi", ten="Thẻ nhân viên 54×86mm (đợt 2)",
        dai_thanh_pham=86, rong_thanh_pham=54,
        so_to_per_sp=1, so_luong=SL_THE_BO_SUNG, don_vi_tinh="thẻ",
        loai_san_pham_id=lsp_the_id,
        giay_id=(couche300.id if couche300 else None), kho_nguyen="650×860",
        kho_nguyen_dai=860, kho_nguyen_rong=650, nguon_giay="cong_ty",
        bleed_mm=2,
        co_in=True, quy_cach_in="hai_mat", kho_in_dai=860, kho_in_rong=650,
        con_auto=True, may_id=_may_id(db, "IN-04"), so_mau_a=4, so_mau_b=1,
        ghi_chu_ky_thuat="Khuôn bế KB-0006 dùng lại. Cán màng mờ 2 mặt như đợt 1.",
    )
    for i, (ma, ten, so_mat) in enumerate([
        ("CD-0001", "Ghi kẽm CTP", 1),
        ("CD-0002", "In offset", 1),
        ("CD-0010", "Cán màng mờ", 2),
        ("CD-0011", "Bế thành phẩm", 1),
        ("CD-0012", "Đóng gói + nhập kho", 1),
    ]):
        the.thanh_phams.append(_buoc(cd, ma, ten, i, so_mat=so_mat))
    p.thanh_phans.append(the)
    db.add(p)
    db.flush()
    compute_phieu_snapshot(db, p)
    db.flush()
    return p


def _ma_phieu(db: Session, created: datetime) -> str:
    """PTG-{year}-{seq:04d} — cùng luật với router phiếu tính giá."""
    from sqlalchemy import func

    prefix = f"PTG-{created.year}-"
    count = db.scalar(
        select(func.count()).select_from(PhieuTinhGia).where(PhieuTinhGia.ma.like(f"{prefix}%"))
    ) or 0
    return f"{prefix}{count + 1:04d}"


def _tao_bao_gia(db: Session, *, ptg: PhieuTinhGia, khach: Customer, sale_id: int,
                 seq: SequenceService, created: datetime):
    """Báo giá từ PTG — 1 dòng/sản phẩm, giá vốn KHÓA từ `gia_von_tp`, khách ĐÃ ĐỒNG Ý.

    Dựng theo đúng luật `QuotationService._fill_version_from_ptg` (dùng lại `calculate_pricing`
    + `dien_giai_tu_thanh_phan` của service để số và diễn giải khớp màn báo giá thật).
    """
    from .models.quotation import (
        DEFAULT_TERMS, Quote, QuoteActivityLog, QuoteItem, QuoteVersion,
        STATUS_ACCEPTED, VERSION_STATUS_ACCEPTED,
    )
    from .services.quotation_service import QuotationService, _kho_tp, dien_giai_tu_thanh_phan

    sent = created + timedelta(days=1)
    accepted = created + timedelta(days=3)

    q = Quote(
        quote_number=seq.generate_code("quotation", at_date=created.date()),
        customer_id=khach.id, customer_name_snapshot=khach.name,
        phieu_tinh_gia_id=ptg.id, salesperson_id=sale_id, created_by=sale_id,
        status=STATUS_ACCEPTED,
        valid_until=(created + timedelta(days=30)).date(),
        terms_text=DEFAULT_TERMS,
        delivery_address="Lô B4, KCN Tân Bình, Q. Tân Phú, TP.HCM",
        contact_name_snapshot="Nguyễn Thị Hà", contact_phone_snapshot="0901000001",
        contact_title_snapshot="Trưởng phòng Hành chính",
        customer_note="Giao 1 lần cùng thẻ nhân viên. Duyệt maquette trước khi lên kẽm.",
        internal_note="Khách quen, markup 18%. Gáy 10mm đã xác nhận với kỹ thuật.",
        created_at=created, updated_at=accepted,
    )
    db.add(q)
    db.flush()

    v = QuoteVersion(
        quote_id=q.id, version_number=1, status=VERSION_STATUS_ACCEPTED, created_by=sale_id,
        vat_percent=VAT_PCT, created_at=created, sent_at=sent, accepted_at=accepted,
    )
    db.add(v)
    db.flush()
    q.current_version_id = v.id

    subtotal = discount = vat = final = total_cost = 0.0
    tps = sorted(ptg.thanh_phans, key=lambda t: (t.thu_tu or 0, t.id or 0))
    for pos, tp in enumerate(tps):
        qty = int(tp.so_luong) or int(ptg.so_luong) or 1
        cost = float(tp.gia_von_tp or 0)
        pricing = QuotationService.calculate_pricing(
            total_cost=cost, margin_percent=MARKUP_PCT, vat_percent=VAT_PCT, quantity=qty,
        )
        db.add(QuoteItem(
            quote_version_id=v.id, phieu_thanh_phan_id=tp.id, line_no=pos + 1,
            product_type=tp.loai_thanh_phan or "san_pham",
            product_name=tp.ten or ptg.ten_san_pham,
            product_spec_text=_kho_tp(tp),
            dien_giai=dien_giai_tu_thanh_phan(db, tp),
            nhom=tp.nhom_bao_gia,
            quantity=qty, unit=tp.don_vi_tinh or "cái",
            total_cost_snapshot=cost, margin_percent=MARKUP_PCT,
            selling_price=pricing["selling_price"], unit_price=pricing["unit_price"],
            discount_amount=pricing["discount_amount"],
            vat_percent=VAT_PCT, vat_amount=pricing["vat_amount"],
            final_amount=pricing["final_amount"],
            accepted=True,   # khách chốt CẢ 3 dòng
        ))
        subtotal += pricing["selling_price"]
        discount += pricing["discount_amount"]
        vat += pricing["vat_amount"]
        final += pricing["final_amount"]
        total_cost += cost

    v.total_cost_snapshot = total_cost
    v.subtotal_amount = subtotal
    v.discount_amount = discount
    v.vat_amount = vat
    v.final_amount = final

    for act, at, note in (
        ("create_quote", created, f"Tạo báo giá v1 từ phiếu tính giá {ptg.ma} (3 sản phẩm)"),
        ("send", sent, "Gửi khách qua email"),
        ("accept", accepted, "Khách đồng ý toàn bộ 3 dòng"),
    ):
        db.add(QuoteActivityLog(
            quote_id=q.id, quote_version_id=v.id, action=act, actor_id=sale_id,
            new_value_json={"note": note}, created_at=at,
        ))
    db.flush()
    return q, v


def _tao_don_hang(db: Session, *, quote, version, khach: Customer, sale_id: int,
                  created: datetime, han_giao_sau: int, po: str,
                  production_note: str | None = None, is_rush: bool = False):
    """Đơn hàng bán TỪ báo giá: ghim quotation + snapshot giá/giá vốn, đã chốt, đủ cọc 30%,
    đã bấm 'Chuyển xuống sản xuất' → vào hàng chờ kế hoạch. `han_giao_sau` = số ngày từ ngày
    chốt tới hạn giao khách."""
    from .models.accounting import (
        PAYMENT_RECEIPT_RECEIVED, RECEIPT_SOURCE_ORDER, PaymentReceipt,
    )
    from .models.order import (
        COST_BASIS_QUOTE, NATURE_HANG_HOA, ORDER_KIND_MOI, SOURCE_BAO_GIA, STATUS_ORDERED,
        Order, OrderLine,
    )
    from .models.quotation import STATUS_CONVERTED_TO_ORDER
    from .repositories.order_repo import OrderRepository

    ordered_at = created
    coc_at = created + timedelta(days=1)
    ban_giao_at = created + timedelta(days=2)

    o = Order(
        order_no=OrderRepository(db)._next_order_no(),
        customer_id=khach.id,
        quotation_id=quote.id, quotation_version=version.version_number,
        quotation_effective_from=(version.created_at.date() if version.created_at else None),
        source_type=SOURCE_BAO_GIA, order_nature=NATURE_HANG_HOA, order_kind=ORDER_KIND_MOI,
        sale_user_id=sale_id, status=STATUS_ORDERED,
        vat_pct_estimate=int(VAT_PCT), cost_basis=COST_BASIS_QUOTE, deposit_pct=DEPOSIT_PCT,
        customer_po_no=po,
        delivery_committed_date=(created + timedelta(days=han_giao_sau)).date(),
        delivery_address="Lô B4, KCN Tân Bình, Q. Tân Phú, TP.HCM",
        delivery_contact_name="Nguyễn Thị Hà", delivery_contact_phone="0901000001",
        delivery_note="Giao giờ hành chính, gọi trước 30 phút. Xe tải nhỏ vào được cổng B.",
        production_note=production_note,
        is_rush=is_rush,
        ordered_at=ordered_at, ordered_by=sale_id,
        san_xuat_released_at=ban_giao_at,
        created_at=created,
    )

    subtotal = 0
    for it in sorted(version.items, key=lambda x: x.line_no):
        net = int(round(float(it.final_amount) - float(it.vat_amount)))
        unit = int(round(net / it.quantity)) if it.quantity else net
        subtotal += net
        o.lines.append(OrderLine(
            description=it.product_name, qty=it.quantity, don_vi_tinh=it.unit,
            unit_price_snapshot=unit, line_total=net,
            vat_pct_estimate=int(float(it.vat_percent or 0)),
            cost_snapshot=int(round(float(it.total_cost_snapshot or 0))),
            phieu_thanh_phan_id=it.phieu_thanh_phan_id, nhom=it.nhom,
        ))
    db.add(o)
    db.flush()

    coc = int(round(DEPOSIT_PCT * subtotal * (1 + VAT_PCT / 100) / 100))
    db.add(PaymentReceipt(
        code=f"PT-SEED-{o.id}", source_type=RECEIPT_SOURCE_ORDER, order_id=o.id,
        payer_name=khach.name, receipt_method="bank_transfer",
        status=PAYMENT_RECEIPT_RECEIVED, receipt_date=coc_at.date(),
        amount=coc, amount_vnd=coc, currency="VND", exchange_rate=1,
        content=f"Thu cọc {DEPOSIT_PCT:.0f}% đơn {o.order_no}",
        customer_name_snapshot=khach.name, order_no_snapshot=o.order_no,
        created_by_user_id=sale_id, received_by_user_id=sale_id,
        received_at=coc_at, created_at=coc_at,
    ))
    quote.status = STATUS_CONVERTED_TO_ORDER   # báo giá sang tab "Đã lên đơn"
    db.flush()
    return o


def _tao_lenh_san_xuat(db: Session, *, order, actor) -> list:
    """Sinh lệnh sản xuất qua LsxService THẬT (routing + số tờ + đơn vị bước do service tính),
    rồi gán khuôn bế cho lệnh thẻ và xác nhận 'sẵn sàng' như kế hoạch làm trên màn."""
    from .models.lsx import TT_SAN_SANG
    from .services.lsx_service import LsxService

    svc = LsxService(
        db, LsxRepository(db), AuditLogRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
    )
    lenhs = svc.tao(
        order_id=order.id, order_line_ids=[ln.id for ln in order.lines], actor=actor,
    )
    for lsx in lenhs:
        lsx.han_hoan_thanh_sx = (order.delivery_committed_date - timedelta(days=3)
                                 if order.delivery_committed_date else None)
        _sua_don_vi_gap_tay(lsx)
        _sua_so_luong_buoc_be(lsx)
        thieu = svc.thieu_cua(lsx)
        if not thieu:
            lsx.trang_thai = TT_SAN_SANG   # kế hoạch xác nhận đủ dữ liệu → chờ xếp lịch
    db.flush()
    return lenhs


def _sua_don_vi_gap_tay(lsx) -> None:
    """Ghim SỐ LƯỢNG bước 'Gấp tay sách' về số TỜ IN — 10.250 tờ, không phải 1.000 cuốn.

    Gấp TAY SÁCH là gấp cả TỜ in, một tờ ra một tay (hệ số 1) — khác hẳn gấp tờ rơi (xén rời rồi
    mới gấp từng con). Đơn vị nay do DANH MỤC khai (`to → tay`, xem `_DON_VI_KHAU_SACH`) chứ
    không còn dò chữ "gấp" trong tên nữa; hàm này chỉ còn ghim số lượng cho lệnh mô phỏng.
    """
    from .models.lsx import DV_TAY, DV_TO

    to = float(lsx.so_to_ke_hoach or 0)
    if to <= 0:
        return
    for cd in lsx.cong_doans:
        if "gấp tay" not in (cd.ten or "").lower():
            continue
        cd.so_luong_vao = to
        cd.so_luong_ra = to          # 1 tờ = 1 tay nên vào bằng ra, chỉ đổi TÊN đơn vị
        cd.don_vi_vao = DV_TO
        cd.don_vi_ra = DV_TAY
        cd.he_so_quy_doi = 1


def _sua_so_luong_buoc_be(lsx) -> None:
    """Bước BẾ (tờ vào → con ra): chỉ bế số tờ TỐT, không bế cả tờ bù hao canh máy.

    Mặc định service lấy tờ sau in — con số đã gồm CẢ CỤC bù hao của mọi công đoạn — rồi nhân
    con/tờ. Job nhỏ như thẻ (11 tờ cần, 230 tờ bù canh máy 4 màu) vì thế ra 23.859 con cho đơn
    1.000 thẻ. Kế hoạch luôn kéo lại số này ở drawer, nên seed để lệnh ở trạng thái ĐÃ hiệu chỉnh.
    """
    from math import ceil

    from .models.lsx import DV_CAI, DV_TO

    sl = int(lsx.so_luong_dat or 0)
    if sl <= 0:
        return
    for cd in lsx.cong_doans:
        if cd.don_vi_vao != DV_TO or cd.don_vi_ra != DV_CAI:
            continue
        con = max(float(cd.he_so_quy_doi or 1), 1.0)
        if float(cd.so_luong_ra or 0) <= sl * 1.5:   # đã sát SL đặt → để yên
            continue
        to_can = ceil(sl / con)
        cd.so_luong_vao = to_can
        cd.so_luong_ra = to_can * con


def _co_phieu(db: Session, ten: str) -> bool:
    return db.execute(
        select(PhieuTinhGia).where(PhieuTinhGia.ten_san_pham == ten)
    ).first() is not None


def seed_luong_ban_sx(db: Session) -> None:
    """Seed 2 luồng, guard RIÊNG từng phiếu (thêm luồng mới không cần xoá luồng cũ):

    · Luồng ĐỦ: sách + thẻ → báo giá → đơn → 3 lệnh SX `san_sang` (chờ xếp lịch).
    · Luồng CHỜ LẬP LỆNH: đơn thẻ bổ sung đã chuyển xuống SX mà CHƯA có lệnh → nằm ở
      tab "hàng chờ" của màn Kế hoạch SX, để bấm "Tạo lệnh" xem được cả khâu đó.
    """
    # DANH MỤC chạy TRƯỚC guard luồng: mấy thứ này idempotent theo mã và DB đã seed luồng từ trước
    # vẫn cần nhận công đoạn / bảng khoán / đơn vị mới. Để sau guard là DB cũ mãi không có bảng
    # khoán, mà bảng khoán rỗng thì bước lệnh không có đầu việc nào để điền.
    cd = _ensure_cong_doan(db)
    _ensure_may_nang_luc(db)
    _ensure_don_gia_khoan(db)   # bảng khoán của tổ → bước lệnh tự điền được đầu việc lúc bung
    _ensure_dinh_muc_to(db)

    can_luong_du = not _co_phieu(db, TEN_PHIEU)
    can_luong_cho = not _co_phieu(db, TEN_PHIEU_BO_SUNG)
    if not (can_luong_du or can_luong_cho):
        return

    khach = db.execute(
        select(Customer).where(Customer.name.like("%An Phát%"))
    ).scalars().first()
    users = UserRepository(db)
    sale = users.get_by_username("sale1")
    if khach is None or sale is None:
        return   # thiếu nền demo (khách / sale) → không seed nửa vời
    ke_hoach = users.get_by_username("kehoach") or sale
    sale_ten = f"{sale.name or sale.username} (Kinh doanh)"

    now = _utcnow()
    lsp_sach = db.execute(
        select(LoaiSanPham).where(LoaiSanPham.ma == "LSP-0003")
    ).scalars().first()
    lsp_the_id = _ensure_loai_the(db)
    _ensure_khuon_the(db, khach.name)   # chỉ để kho khuôn có dòng mẫu — lệnh không trỏ tới nữa
    seq = SequenceService(DocumentSequenceRepository(db))

    if can_luong_du:
        ptg = _tao_phieu_tinh_gia(
            db, cd=cd, sale_id=sale.id, sale_ten=sale_ten,
            lsp_sach_id=(lsp_sach.id if lsp_sach else None), lsp_the_id=lsp_the_id,
            created=now - timedelta(days=16),
        )
        quote, version = _tao_bao_gia(
            db, ptg=ptg, khach=khach, sale_id=sale.id, seq=seq,
            created=now - timedelta(days=15),
        )
        order = _tao_don_hang(
            db, quote=quote, version=version, khach=khach, sale_id=sale.id,
            created=now - timedelta(days=10), han_giao_sau=23,
            po="PO-ANPHAT-2026-114",
            production_note="Ruột in đen 1+1; bìa cán mờ. Kiểm chính tả trang 3 "
                            "(đã sửa maquette v2).",
        )
        db.commit()   # LsxService.tao tự commit — chốt phần thương mại trước cho sạch transaction
        _tao_lenh_san_xuat(db, order=order, actor=ke_hoach)
        db.commit()

    if can_luong_cho:
        ptg2 = _tao_phieu_the_bo_sung(
            db, cd=cd, sale_id=sale.id, sale_ten=sale_ten, lsp_the_id=lsp_the_id,
            created=now - timedelta(days=5),
        )
        quote2, version2 = _tao_bao_gia(
            db, ptg=ptg2, khach=khach, sale_id=sale.id, seq=seq,
            created=now - timedelta(days=4),
        )
        # KHÔNG tạo lệnh: đây chính là việc đang chờ của kế hoạch sản xuất.
        _tao_don_hang(
            db, quote=quote2, version=version2, khach=khach, sale_id=sale.id,
            created=now - timedelta(days=2), han_giao_sau=9,
            po="PO-ANPHAT-2026-131", is_rush=True,
            production_note="Đợt 2 in bù cho nhân viên mới — khách cần gấp, "
                            "ghép chung ca máy với đơn trước nếu còn kịp.",
        )
        db.commit()
