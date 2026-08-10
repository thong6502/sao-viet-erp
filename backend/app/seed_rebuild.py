"""Seed data cho các module rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP).

Theo seed §7 của từng spec. Idempotent (bỏ qua nếu bảng đã có dòng). Gọi 1 lần từ seed_all.
Direct model instantiation — đơn giản, đủ để UI có dữ liệu + engine (Phase D) có nền.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.bu_hao import BuHao
from .models.cong_doan import CongDoan
from .models.don_vi_do import DonViDo, DonViQuyDoi
from .models.khuon_be import KhuonBe
from .models.loai_san_pham import LoaiSanPham
from .models.may_thiet_bi import MayThietBi
from .models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn


def _empty(db: Session, model) -> bool:
    return db.execute(select(model).limit(1)).first() is None


# --- Đơn vị đo & quy đổi (nền cho khoán · kho · mua hàng) ---------------------------------------
# (mã, tên, họ, GIẢI NGHĨA). `ho` = LOẠI ĐO, chỉ để gom nhóm khi hiển thị — "đổi được cho nhau hay
# không" nằm ở `_QUY_DOI_SEED` bên dưới, không ở loại đo.
# Giải nghĩa hiện ở cột Ghi chú của màn Đơn vị: người ngoài nhà in mở
# danh sách ra thấy "con", "bài in", "lượt" thì không đoán nổi đang đếm cái gì. Đơn vị ai cũng biết
# (kg · m · cm²) để trống — viết thừa cũng là một kiểu ồn.
_DON_VI_SEED: list[tuple[str, str, str, str]] = [
    ("cm2", "cm²", "dien_tich", ""),
    ("m2", "m²", "dien_tich", ""),
    ("kg", "kg", "khoi_luong", ""),
    ("tan", "tấn", "khoi_luong", ""),
    ("g", "g", "khoi_luong", ""),
    ("m", "mét", "do_dai", ""),
    ("mm", "mm", "do_dai", ""),
    ("to", "tờ", "to", "Tờ giấy chạy qua máy in."),
    ("ram", "ram", "to", "Cách nhà cung cấp đóng gói giấy: 1 ram = 500 tờ."),
    # Loại THÀNH PHẨM — mọi cách đếm "một sản phẩm xong": bước lệnh gọi `cai`, bảng khoán của tổ gọi
    # "cuốn" (sách) / "hộp" (gỡ hàng) / "con" (tem). Chúng đếm như nhau nên có cặp quy đổi 1-1 bên
    # dưới; thiếu cặp đó thì bước "vào keo" (đơn vị `cai`, 1.000 cuốn) không khớp đơn giá 700 đ/cuốn.
    ("cai", "cái", "thanh_pham", "Một sản phẩm hoàn chỉnh. Cuốn · con · bộ · hộp đều quy về cái."),
    ("con", "con", "thanh_pham", "Sản phẩm rời bế/xén ra từ tờ in — 1 tờ ra nhiều con (tem, thẻ, nhãn)."),
    ("cuon", "cuốn", "thanh_pham", "Một cuốn sách thành phẩm (= 1 cái)."),
    ("bo", "bộ", "thanh_pham", "Một bộ thành phẩm (= 1 cái)."),
    ("hop", "hộp", "thanh_pham", "Một hộp thành phẩm (= 1 cái)."),
    ("kem", "bản kẽm", "kem", "Bản kẽm phơi cho MỘT màu của một bài in."),
    # mã `bai` khớp đơn vị bước lệnh (DV_BAI), không phải "bai_in"
    ("bai", "bài in", "bai", "Một bài đã bình, chạy ra nhiều tờ in giống nhau."),
    ("luot", "lượt", "luot", "Một lần đưa giấy qua máy (cắt demi tính theo lượt)."),
    ("thung", "thùng", "thung", "Thùng đóng hàng lúc giao."),
]

# CẶP quy đổi: (tu, den, he_so) đọc là "1 <tu> = <he_so> <den>". Máy tự đi chiều ngược, nên KHÔNG
# khai dòng đối xứng. Cặp nào chưa khai thì máy dò đường qua trung gian (tấn → g đi qua kg).
_QUY_DOI_SEED: list[tuple[str, str, float, str]] = [
    ("m2", "cm2", 10_000, ""),     # 1 m² = 10.000 cm²
    ("tan", "kg", 1_000, ""),      # 1 tấn = 1.000 kg
    ("kg", "g", 1_000, ""),        # 1 kg = 1.000 g
    ("m", "mm", 1_000, ""),        # 1 mét = 1.000 mm
    ("ram", "to", 500, ""),        # quy ước ngành in: 1 ram = 500 tờ
    # Các cách đếm thành phẩm là MỘT: nối hết về `cai` để bước lệnh (đếm `cai`) khớp mọi đơn giá
    # khoán dù xưởng ghi "cuốn", "con", "hộp" hay "bộ".
    ("con", "cai", 1, ""),
    ("cuon", "cai", 1, ""),
    ("bo", "cai", 1, ""),
    ("hop", "cai", 1, ""),
    # --- Quy đổi ĐỘNG: hệ số là công thức, số ra tuỳ giấy/khổ của chính việc đang làm ---------
    # Ba dòng này trước nằm CỨNG trong code (`quy_doi_service.CAU`) nên xưởng không sửa được.
    # Biến do nơi gọi bơm: `dai`/`rong` là khổ của TỜ ĐANG ĐẾM (m), `dinh_luong` kg/m².
    # tờ → cm² KHÔNG cần dòng riêng: đi tiếp bằng cặp m² → cm² đã khai ở trên.
    ("to", "m2", 0, "dai * rong"),
    ("to", "kg", 0, "dinh_luong * dai * rong"),
    ("to", "cai", 0, "so_con"),
]


def seed_don_vi_do(db: Session) -> None:
    """Đơn vị đo + cặp quy đổi — DỮ LIỆU VẬN HÀNH THẬT, không phải demo.

    Gọi NGOÀI khối `SEED_DEMO` (như biểu thuế TNCN / ngày lễ): thiếu bảng này thì mọi phép quy đổi
    trả "chưa khai quy đổi" và tiền khoán không tính được — tê liệt trên chính DB thật, nơi không ai
    bật seed demo.

    Bổ sung theo MÃ / CẶP CÒN THIẾU (không dùng `_empty`): thêm dòng mới vào hai danh sách trên là
    DB đang chạy cũng nhận, khỏi phải drop bảng. Cặp người dùng tự sửa thì KHÔNG bị ghi đè.
    """
    from .db_migrations import DON_VI_TOC_DO_MAC_DINH   # một nguồn duy nhất, đừng chép danh sách

    co = {d.ma for d in db.execute(select(DonViDo)).scalars()}
    moi = [
        DonViDo(ma=ma, ten=ten, ho=ho, ghi_chu=gc or None,
                dung_lam_toc_do=ma in DON_VI_TOC_DO_MAC_DINH)
        for ma, ten, ho, gc in _DON_VI_SEED if ma not in co
    ]
    if moi:
        db.add_all(moi)
        db.commit()

    # Giải nghĩa cho đơn vị nghề: điền vào dòng đang TRỐNG ghi chú, không đè chữ người dùng đã ghi.
    # Làm riêng vì DB đang chạy đã có sẵn các dòng này từ trước khi có cột giải nghĩa.
    nghia = {ma: gc for ma, _t, _h, gc in _DON_VI_SEED if gc}
    them = 0
    for d in db.execute(select(DonViDo)).scalars():
        if nghia.get(d.ma) and not (d.ghi_chu or "").strip():
            d.ghi_chu = nghia[d.ma]
            them += 1
    if them:
        db.commit()

    by_ma = {d.ma: d.id for d in db.execute(select(DonViDo)).scalars()}
    da_co = {
        (c.tu_id, c.den_id) for c in db.execute(select(DonViQuyDoi)).scalars()
    }
    caps = []
    for tu, den, hs, ct in _QUY_DOI_SEED:
        tu_id, den_id = by_ma.get(tu), by_ma.get(den)
        if not tu_id or not den_id:
            continue
        # Kiểm CẢ HAI CHIỀU: người dùng có thể đã khai "1 tờ = 0,002 ram" — cùng một chuyện.
        if (tu_id, den_id) in da_co or (den_id, tu_id) in da_co:
            continue
        caps.append(DonViQuyDoi(tu_id=tu_id, den_id=den_id, he_so=hs, cong_thuc=ct or None))
    if caps:
        db.add_all(caps)
        db.commit()


def seed_nhom_may(db: Session) -> None:
    """Danh mục Nhóm máy — DỮ LIỆU VẬN HÀNH THẬT, không gated demo.

    Gọi NGOÀI khối `SEED_DEMO`: thiếu bảng này thì ô "Nhóm máy" trống trơn và không khai được máy
    nào. Nạp theo TÊN CÒN THIẾU (không `_empty`) nên DB đang chạy cũng nhận, khỏi drop bảng.

    Vì sao seed ĐÔI (ở đây + migration 0155): `schema_migrations` sống qua `drop_all` nên test
    KHÔNG chạy lại migration — chỉ seed mới dựng được DB test."""
    from .models.may_thiet_bi import MayThietBi, NHOM_MAY_MAC_DINH, NhomMay

    da_co = {r for r in db.execute(select(NhomMay.ten)).scalars()}
    # Gộp cả nhóm ĐANG có máy dùng: xưởng tự đặt tên nào thì tên đó phải có trong danh mục,
    # không thì máy trỏ vào nhóm "không tồn tại".
    dang_dung = {
        (t or "").strip()
        for t in db.execute(select(MayThietBi.loai_may).distinct()).scalars()
        if (t or "").strip()
    }
    moi: list[NhomMay] = []
    for ten in (*NHOM_MAY_MAC_DINH, *sorted(dang_dung)):
        if ten not in da_co:
            da_co.add(ten)          # chặn trùng NGAY trong lượt này (tên mặc định có thể trùng
            moi.append(NhomMay(ten=ten))   # với tên máy đang dùng)
    if moi:
        db.add_all(moi)
        db.commit()


def seed_rebuild_catalog(db: Session) -> None:
    # --- Máy (spec-may-thiet-bi §7) ---
    if _empty(db, MayThietBi):
        # Dữ liệu THẬT của xưởng. Dim mm, rộng = số đầu, dài = số sau (vd "800*1030" = rộng 800, dài 1030).
        # Nhóm máy = chữ tự do (form MỞ). Chủ xưởng tự đặt tên nhóm để nhóm/lọc.
        _IN = "Máy in"              # máy in nội bộ
        _INX = "In ngoài"          # xưởng in ngoài
        _CM = "Cán màng / UV"      # cán màng / UV
        _BOI = "Bồi"               # bồi sóng / duplex
        _BE = "Bế"                 # bế / ép kim
        # Chừa TỜ GIẤY của máy in — engine bình bài trừ theo chiều (dài ← nhíp + đuôi, rộng ←
        # lề hông ×2). Đây là NGUỒN DUY NHẤT của chừa: phiếu chỉ còn ô đè `chua_nhip`. Số nghề
        # thường gặp; xưởng đo lại máy mình thì sửa trong danh mục Máy.
        _CHUA_IN = {"nhip_giay_mm": 10, "le_hong_mm": 5, "duoi_thang_mau_mm": 5}
        db.add_all([
            # ── MÁY IN nội bộ — kẽm / nhíp / khổ giấy / vùng in ───────────────────────
            MayThietBi(ma="IN-01", ten="Máy 2 màu Mitsubishi 72×102", loai_may=_IN,
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44, **_CHUA_IN,
                       kho_min_rong=390, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010,
                       ghi_chu="Có in UV được. Hàng bồi sóng phải chạy in tay kề nghịch, "
                               "đặt tay kề sẵn trên bài in"),
            MayThietBi(ma="IN-02", ten="Máy 4 màu Mitsubishi 79×109", loai_may=_IN,
                       kho_kem_rong=930, kho_kem_dai=1130, gripper_mm=60, **_CHUA_IN,
                       kho_min_rong=540, kho_min_dai=750, kho_max_rong=800, kho_max_dai=1090,
                       vung_in_rong=780, vung_in_dai=1080),
            MayThietBi(ma="IN-03", ten="Máy 5 màu Mitsubishi 54×79", loai_may=_IN,
                       kho_kem_rong=645, kho_kem_dai=830, gripper_mm=50, **_CHUA_IN,
                       kho_min_rong=320, kho_min_dai=420, kho_max_rong=540, kho_max_dai=790,
                       vung_in_rong=535, vung_in_dai=780),
            MayThietBi(ma="IN-04", ten="Máy 6 màu Mitsubishi 72×102", loai_may=_IN,
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Có in UV được"),
            MayThietBi(ma="IN-05", ten="Máy 6 màu Heidelberg 72×102", loai_may=_IN,
                       kho_kem_rong=765, kho_kem_dai=1030, gripper_mm=44, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=560, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=690, vung_in_dai=1000,
                       ghi_chu="Có in UV được. Vùng in lớn hơn 69cm thì nhíp kẽm 38mm; "
                               "chỉ in được giấy từ 150g trở lên"),
            MayThietBi(ma="IN-06", ten="Máy 7 màu Heidelberg 72×102", loai_may=_IN,
                       kho_kem_rong=765, kho_kem_dai=1030, gripper_mm=44, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=560, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=690, vung_in_dai=1000),
            # ── IN ngoài (xưởng in ngoài) ────────────────────────────────────────────
            MayThietBi(ma="IN-07", ten="Minh Tiến 72×102 - 5 màu", loai_may=_INX,
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=48, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Xưởng in ngoài"),
            MayThietBi(ma="IN-08", ten="Hoàng Anh 1020×1420 - 6 màu", loai_may=_INX,
                       kho_min_rong=575, kho_min_dai=810, kho_max_rong=1020, kho_max_dai=1420,
                       vung_in_rong=1000, vung_in_dai=1400, ghi_chu="Xưởng in ngoài", **_CHUA_IN),
            MayThietBi(ma="IN-09", ten="Bảo Tiến 72×102 - 6 màu", loai_may=_INX,
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=50, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Xưởng in ngoài. Có in UV"),
            MayThietBi(ma="IN-10", ten="Đỉnh Việt 72×102 - 5 màu", loai_may=_INX,
                       kho_kem_rong=800, kho_kem_dai=1030, gripper_mm=44, **_CHUA_IN,
                       kho_min_rong=395, kho_min_dai=545, kho_max_rong=720, kho_max_dai=1020,
                       vung_in_rong=710, vung_in_dai=1010, ghi_chu="Xưởng in ngoài"),
            # ── MÁY CÁN MÀNG + UV ĐỊNH HÌNH — chỉ khổ giấy min/max ────────────────────
            MayThietBi(ma="CM-01", ten="Máy UV toàn phần 790×1090", loai_may=_CM,
                       kho_min_rong=280, kho_min_dai=380, kho_max_rong=790, kho_max_dai=1090,
                       ghi_chu="Lớn hơn nửa thì thả tay dọc được"),
            MayThietBi(ma="CM-02", ten="Máy UV định hình 720×1020", loai_may=_CM,
                       kho_min_rong=360, kho_min_dai=440, kho_max_rong=720, kho_max_dai=1020,
                       ghi_chu="Xuất film để chụp lụa kéo. Phim đế 100k để chụp nét nội dung"),
            MayThietBi(ma="CM-03", ten="Máy cán màng 800×1080", loai_may=_CM,
                       kho_min_rong=300, kho_min_dai=300, kho_max_rong=800, kho_max_dai=1080),
            MayThietBi(ma="CM-04", ten="Máy cán màng 1250×1500", loai_may=_CM,
                       kho_min_rong=300, kho_min_dai=300, kho_max_rong=1250, kho_max_dai=1500),
            # ── MÁY BỒI SÓNG + BỒI DUPLEX ────────────────────────────────────────────
            MayThietBi(ma="BOI-01", ten="Bồi sóng 1450×1450", loai_may=_BOI,
                       kho_min_rong=395, kho_min_dai=395, kho_max_rong=1450, kho_max_dai=1450,
                       ghi_chu="Sóng luôn ghi chiều khổ trước. Tem luôn lớn hơn sóng mỗi chiều 5mm; "
                               "trừ khi ăn gian giấy thì bằng ĐC nhưng phải báo"),
            MayThietBi(ma="BOI-02", ten="Bồi sóng 1700×1700", loai_may=_BOI,
                       kho_min_rong=395, kho_min_dai=395, kho_max_rong=1700, kho_max_dai=1700),
            MayThietBi(ma="BOI-03", ten="Bồi duplex với duplex 1100", loai_may=_BOI,
                       kho_min_rong=280, kho_min_dai=380, kho_max_rong=700, kho_max_dai=1000),
            MayThietBi(ma="BOI-04", ten="Bồi thủ công 1100", loai_may=_BOI,
                       kho_min_rong=200, kho_min_dai=200, kho_max_rong=700, kho_max_dai=1000),
            # ── MÁY BẾ TỰ ĐỘNG + BẾ TAY ──────────────────────────────────────────────
            MayThietBi(ma="BE-01", ten="Máy bế tự động Yawa 1050", loai_may=_BE,
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1050,
                       ghi_chu="Tự động trừ nhíp bế 8mm; chỉ ăn gian được tại dán ở nhíp thì phải tháo "
                               "dao lạng hoặc tháo bớt nhíp gấp, phải hỏi thợ trước. "
                               "Ván min 450×650, ván thực lỗ min 450×450"),
            MayThietBi(ma="BE-02", ten="Máy ép kim bế tự động Aoer 1050", loai_may=_BE,
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1050),
            MayThietBi(ma="BE-03", ten="Máy bế tự động Aoer 1500", loai_may=_BE,
                       kho_min_rong=400, kho_min_dai=420, kho_max_rong=1100, kho_max_dai=1500),
            MayThietBi(ma="BE-04", ten="Máy bế tự động Brouse 145", loai_may=_BE,
                       kho_min_rong=400, kho_min_dai=420, kho_max_rong=1050, kho_max_dai=1450),
            MayThietBi(ma="BE-05", ten="Máy ép kim bế tự động Diamon 1020", loai_may=_BE,
                       kho_min_rong=380, kho_min_dai=380, kho_max_rong=720, kho_max_dai=1020),
            MayThietBi(ma="BE-06", ten="Máy bế tay 720/930/1100/1500", loai_may=_BE,
                       kho_min_rong=150, kho_min_dai=150, kho_max_rong=1050, kho_max_dai=1450,
                       ghi_chu="Bế tay bế SL ít, bế hàng ăn gian nhíp"),
        ])
        db.commit()

    # --- Danh mục Giấy & Vật tư (Cấu hình danh mục) ---
    if _empty(db, ChungLoaiGiay):
        db.add_all([
            ChungLoaiGiay(ma="COUCHE", ten="Couché", be_mat="bong", mo_ta="Giấy tráng phủ 2 mặt, bóng."),
            ChungLoaiGiay(ma="FORD", ten="Ford (giấy in thường)", be_mat="nham"),
            ChungLoaiGiay(ma="IVORY", ten="Ivory (bìa 1 mặt)", be_mat="bong"),
            ChungLoaiGiay(ma="DUPLEX", ten="Duplex (bồi 2 lớp)", be_mat="nham"),
            ChungLoaiGiay(ma="BRISTOL", ten="Bristol", be_mat="mo"),
            ChungLoaiGiay(ma="KRAFT", ten="Kraft (giấy nâu)", be_mat="nham"),
        ])
        db.commit()
    _cl = {c.ma: c.id for c in db.execute(select(ChungLoaiGiay)).scalars()}
    if _empty(db, GiayNguyen):
        db.add_all([
            GiayNguyen(ma="COUCHE-300-65x86", ten="Couché 300 65×86", chung_loai_giay_id=_cl.get("COUCHE"),
                       kho_dai=860, kho_rong=650, gsm=300, caliper_micron=310, tho="canh_dai",
                       don_vi_gia="kg", don_gia=30000),
            GiayNguyen(ma="COUCHE-150-79x109", ten="Couché 150 79×109", chung_loai_giay_id=_cl.get("COUCHE"),
                       kho_dai=1090, kho_rong=790, gsm=150, caliper_micron=150, tho="canh_dai",
                       don_vi_gia="kg", don_gia=28000),
            GiayNguyen(ma="FORD-70-65x86", ten="Ford 70 65×86", chung_loai_giay_id=_cl.get("FORD"),
                       kho_dai=860, kho_rong=650, gsm=70, caliper_micron=95, tho="canh_ngan",
                       don_vi_gia="kg", don_gia=26000),
            GiayNguyen(ma="IVORY-350-79x109", ten="Ivory 350 79×109", chung_loai_giay_id=_cl.get("IVORY"),
                       kho_dai=1090, kho_rong=790, gsm=350, caliper_micron=430, tho="canh_dai",
                       don_vi_gia="kg", don_gia=32000),
            GiayNguyen(ma="DUPLEX-300", ten="Duplex 300", chung_loai_giay_id=_cl.get("DUPLEX"),
                       kho_dai=1090, kho_rong=790, gsm=300, caliper_micron=380,
                       don_vi_gia="kg", don_gia=18000),
        ])
        db.commit()
    # Backfill chủng loại cho giấy chưa gắn (dev data / sau migration) theo tiền tố mã.
    _unlinked = list(db.execute(select(GiayNguyen).where(GiayNguyen.chung_loai_giay_id.is_(None))).scalars())
    if _unlinked:
        for g in _unlinked:
            for pfx, clid in _cl.items():
                if g.ma.upper().startswith(pfx):
                    g.chung_loai_giay_id = clid
                    break
        db.commit()

    if _empty(db, VatTuInAn):
        db.add_all([
            # ⚠️ CÔNG THỨC NÀY SAI THANG 10⁶ — biết và CỐ Ý để nguyên (chủ chốt 2026-08-09).
            # Hệ số 0,0003 viết cho diện tích tính bằng MÉT ("0,3 g mực / m² / màu"), nhưng
            # `dai_in`/`rong_in` engine đưa vào là MILIMÉT ⇒ diện tích to gấp 1.000.000 lần.
            #   1.000 tờ 650×900, in 4 màu → ra 702.000 kg mực = 175,5 TỶ đồng.
            #   Đúng ra:                     0,702 kg          = 175.500 đồng.
            # Không sửa vì xưởng tính giá KHOÁN THEO CÔNG ĐOẠN, không thêm dòng vật tư rời — công
            # thức này hiện không chảy vào phiếu nào. Ai thêm một dòng mực vào phiếu tính giá thì
            # PHẢI sửa hệ số (÷ 1.000.000) trước, không thì ra báo giá 175 tỷ.
            VatTuInAn(ma="MUC-CMYK", ten="Mực process CMYK", don_vi_gia="kg", don_gia=250000,
                      cong_thuc_gia="so_mau * dai_in * rong_in * don_gia_kg * to_dau_vao * 0.0003"),
            VatTuInAn(ma="MUC-PANTONE", ten="Mực pha Pantone", don_vi_gia="kg", don_gia=15000),
            # `kem` chứ không phải `ban`: đơn vị PHẢI là mã có thật trong `don_vi_do` (xem
            # `_DON_VI_SEED`) — mã lạ thì mọi quy đổi của món đó tắt lặng lẽ.
            VatTuInAn(ma="KEM-74", ten="Bản kẽm khổ 74", don_vi_gia="kem", don_gia=100000),
            VatTuInAn(ma="KEM-102", ten="Bản kẽm khổ 102", don_vi_gia="kem", don_gia=180000),
            VatTuInAn(ma="KEM-52", ten="Bản kẽm khổ 52", don_vi_gia="kem", don_gia=70000),
            # ⚠️ SAI THANG 10⁶ y như MUC-CMYK ở trên — `dai_in`/`rong_in` là MILIMÉT, mà đơn giá
            # khai đ/m². 1.000 tờ 650×900 → 585.000.000 m² = 1.755 TỶ đồng; đúng ra 585 m² =
            # 1.755.000 đồng. Cố ý để nguyên, cùng lý do: xưởng khoán theo công đoạn.
            VatTuInAn(ma="MANG-BONG", ten="Màng cán bóng", don_vi_gia="m2", don_gia=3000,
                      cong_thuc_gia="dai_in * rong_in * don_gia_m2 * to_sau_in"),
            VatTuInAn(ma="KEO-GAY", ten="Keo vào gáy", don_vi_gia="kg", don_gia=45000),
        ])
        db.commit()

    # --- Công đoạn: seed ÍT (6 mẫu) đủ minh hoạ 3 kiểu bù hao (khong/tra_bang/cố định) ---
    if _empty(db, CongDoan):
        db.add_all([
            # Giá CHỈ theo CÔNG THỨC (đơn giá nhét sẵn trong công thức, nhân biến số lượng tương ứng).
            # pricing_basis=per_other để hợp validate; run_rate giữ làm tham chiếu (engine ưu tiên công thức).
            # `nhom_may_cho_phep`: nhóm máy (danh mục `nhom_may`) làm được công đoạn — chặn gán máy
            # sai loại ở bước bài ghép. Chế bản chưa có máy seed nên để ["Chế bản"] (mọi máy in/sau-in
            # đều bị coi là sai → khớp vụ CTP gán máy bế).
            CongDoan(ma="CD-0001", ten="Ghi kẽm CTP", nhom="prepress", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=95000, nhom_may_cho_phep=["Chế bản"],
                     cong_thuc_gia="so_kem * 95000", setup_time=10, kieu_bu_hao="khong"),
            CongDoan(ma="CD-0002", ten="In offset", nhom="print", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=350, kieu_bu_hao="tra_bang",  # → BH nối bên dưới
                     nhom_may_cho_phep=["Máy in", "In ngoài"],
                     cong_thuc_gia="to_dau_vao * so_mat * 350"),
            CongDoan(ma="CD-0003", ten="Cán màng bóng", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=2.2, min_charge=110000,
                     kieu_bu_hao="co_dinh", so_to_bu_hao=50, nhom_may_cho_phep=["Cán màng / UV"],
                     cong_thuc_gia="max(dai_in * rong_in * 10000 * so_mat * to_dau_vao * 2.2, 110000)"),
            CongDoan(ma="CD-0004", ten="Bồi sóng", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=200, kieu_bu_hao="tra_bang",  # → BH nối bên dưới
                     nhom_may_cho_phep=["Bồi"],
                     cong_thuc_gia="to_dau_vao * 200"),
            CongDoan(ma="CD-0005", ten="Ép kim", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=400, requires_tooling=True,
                     tooling_type="khuon_ep", kieu_bu_hao="co_dinh", so_to_bu_hao=50,
                     nhom_may_cho_phep=["Bế"],
                     cong_thuc_gia="so_vi_tri * so_luong * 400"),
            CongDoan(ma="CD-0006", ten="Bế nổi", nhom="finishing", che_do_tinh="theo_san_luong",
                     pricing_basis="per_other", run_rate=20, requires_tooling=True,
                     tooling_type="khuon_be", kieu_bu_hao="co_dinh", so_to_bu_hao=30,
                     nhom_may_cho_phep=["Bế"],
                     cong_thuc_gia="so_luong * 20"),
        ])
        db.commit()

    # --- Bù hao (mã bù hao × bậc SL động) — số THẬT của xưởng ---
    if _empty(db, BuHao):
        _SL = [(0, 3000), (3000, 7000), (7000, 10000), (10000, 15000), (15000, 20000), (20000, 30000)]

        def _bac(sau_to, pct):  # 6 bậc đầu = số tờ, bậc >30.000 = %
            b = [{"sl_tu": t, "sl_den": d, "gia_tri": v, "don_vi": "to"} for (t, d), v in zip(_SL, sau_to)]
            b.append({"sl_tu": 30000, "sl_den": None, "gia_tri": pct, "don_vi": "pct"})
            return b

        db.add_all([
            BuHao(ma="BH-KHONG-IN", ten="Hàng không in", bac=_bac([50, 70, 100, 130, 150, 200], 1)),
            BuHao(ma="BH-IN-1-2", ten="In 1-2 màu", bac=_bac([120, 150, 200, 250, 300, 350], 1.5)),
            BuHao(ma="BH-IN-3-4", ten="In 3-4 màu", bac=_bac([150, 200, 250, 300, 350, 400], 1.7)),
            BuHao(ma="BH-IN-5", ten="In 5 màu", bac=_bac([200, 250, 300, 350, 400, 450], 2)),
            BuHao(ma="BH-IN-6", ten="In 6 màu", bac=_bac([250, 300, 350, 450, 500, 600], 2.5)),
            BuHao(ma="BH-SONG-1CON", ten="Sóng — 1 con",
                  bac=_bac([70, 100, 150, 170, 200, 250], 1), ghi_chu="Sóng E, B, BC, BE — lưu ý chiều sóng trước"),
            BuHao(ma="BH-SONG-NHIEU", ten="Sóng — nhiều con", bac=_bac([50, 70, 120, 150, 170, 200], 0.7)),
        ])
        db.commit()

    # --- Nối công đoạn 'tra_bang' → 1 mã bù hao mặc định (mô hình MỚI: công đoạn trỏ thẳng mã) ---
    for cd_ma, bh_ma in (("CD-0002", "BH-IN-3-4"), ("CD-0004", "BH-SONG-1CON")):
        cd = db.execute(select(CongDoan).where(CongDoan.ma == cd_ma)).scalars().first()
        bh = db.execute(select(BuHao).where(BuHao.ma == bh_ma)).scalars().first()
        if cd is not None and bh is not None and cd.kieu_bu_hao == "tra_bang" and cd.bu_hao_id is None:
            cd.bu_hao_id = bh.id
    db.commit()

    # --- Loại sản phẩm (spec-san-pham §7) ---
    if _empty(db, LoaiSanPham):
        cd = {c.ma: c.id for c in db.execute(select(CongDoan)).scalars()}
        rt_flat = [cd.get("CD-0001"), cd.get("CD-0002"), cd.get("CD-0005"), cd.get("CD-0003")]
        rt_book = [cd.get("CD-0001"), cd.get("CD-0002"), cd.get("CD-0004"), cd.get("CD-0007"), cd.get("CD-0003")]
        db.add_all([
            LoaiSanPham(ma="LSP-0001", ten="Name card", structural_type="flat",
                        routing_template=[x for x in rt_flat if x]),
            LoaiSanPham(ma="LSP-0002", ten="Tờ phơi / brochure gấp", structural_type="flat"),
            LoaiSanPham(ma="LSP-0003", ten="Catalogue đóng keo", structural_type="multipage",
                        has_cover=True, cover_type="bia_roi", default_binding="keo",
                        routing_template=[x for x in rt_book if x]),
            LoaiSanPham(ma="LSP-0004", ten="Sách đóng ghim", structural_type="multipage",
                        has_cover=True, cover_type="tu_bia", default_binding="ghim"),
            LoaiSanPham(ma="LSP-0005", ten="Hộp giấy Ivory", structural_type="box",
                        box_sub_type="folding_carton"),
            LoaiSanPham(ma="LSP-0006", ten="Thùng carton sóng", structural_type="box",
                        box_sub_type="corrugated"),
            LoaiSanPham(ma="LSP-0007", ten="Tem decal cuộn", structural_type="label"),
        ])
        db.commit()

    # --- Khuôn bế (khai báo lưu trữ) — khai TAY: tên ấn phẩm · khách · số kệ · ngày làm · tình trạng ---
    if _empty(db, KhuonBe):
        db.add_all([
            KhuonBe(ma="KB-0001", ten="Khuôn bế hộp bánh Trung thu", khach_hang="Cty Kinh Đô",
                    so_ke="Kệ A1 — xưởng sau in", ngay_lam_khuon=date(2025, 8, 12), tinh_trang="dang_dung"),
            KhuonBe(ma="KB-0002", ten="Khuôn bế hộp Ivory 12×8×5", khach_hang="Cty Minh Long",
                    so_ke="Kệ A2 — xưởng sau in", ngay_lam_khuon=date(2026, 1, 15), tinh_trang="dang_dung"),
            KhuonBe(ma="KB-0003", ten="Khuôn bế tem decal tròn Ø40", khach_hang="Dược Hậu Giang",
                    so_ke="Kệ B1 — kho khuôn", ngay_lam_khuon=date(2025, 11, 3), tinh_trang="dang_dung"),
            KhuonBe(ma="KB-0004", ten="Khuôn bế thùng carton sóng B 40×30×25", khach_hang="Cty Vinamilk",
                    so_ke="Kệ C3 — kho khuôn", ngay_lam_khuon=date(2024, 6, 20), tinh_trang="hong",
                    ghi_chu="Dao mòn góc, cần mài lại trước khi tái dùng"),
            KhuonBe(ma="KB-0005", ten="Khuôn bế túi giấy quai xách", khach_hang="Shop An Nhiên",
                    so_ke="Kệ B4 — kho khuôn", ngay_lam_khuon=date(2025, 3, 10), tinh_trang="thanh_ly",
                    ghi_chu="Mẫu cũ, khách đã đổi thiết kế"),
        ])
        db.commit()
