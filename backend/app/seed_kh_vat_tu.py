"""Seed DEMO cho màn KẾ HOẠCH VẬT TƯ: mỗi trạng thái của bảng cân đối có ÍT NHẤT một dòng thật.

Bảng cân đối là số DẪN XUẤT — không bảng nào lưu "màu" cả. Muốn nhìn đủ các màu thì phải dựng
đúng cái NỀN sinh ra chúng: lệnh trong phạm vi tính, tồn kho, hàng đang về, phiếu xuất kho và đơn
vị khai ở bước lệnh. File này dựng nền đó bằng LUỒNG THẬT (phiếu tính giá → báo giá → đơn hàng →
`LsxService.tao`), không chèn tay số tờ hay giá vốn nào.

Bản đồ ca (1 đơn hàng, 5 lệnh mới):

  ① Tờ hướng dẫn A4 · Ford 70 (tồn 1.000 kg)      → giấy XANH
     + mực CMYK đã xuất kho đủ                     → XÁM (đã cấp đủ, hết phải lo)
     + mực Pantone khai đơn vị "hộp"               → KHÔNG RÕ (không có cầu hộp→kg)
     ⇒ giữ chỗ BẬT: giấy giữ đủ 100% mà VẪN chưa mở khoá xếp lịch vì còn dòng không rõ.
     ⇒ `created_at` dòng giữ chỗ lùi 10 ngày       → chip "giữ lâu chưa chạy" (ngưỡng 7 ngày).

  ② Tờ rơi A4 · Couché 150 (tồn 0, KHÔNG mua)     → ĐỎ + đèn ĐẶT MUỘN (ngày cần = hôm nay)
     ⇒ giữ chỗ bật mà giữ được 0%                  → nút "Nhặt thêm ngay".

  ③ Thực đơn A4 · Ivory 350 (tồn 0, phiếu mua về TRƯỚC ngày cần 4 ngày) → VÀNG
     ⇒ phần giữ bám nguồn `dang_ve`                → "xếp sớm nhất từ" = ngày hàng về.

  ④ Bảng giá A3 · Duplex 300 (tồn 0, phiếu mua về SAU ngày cần 7 ngày)  → VỀ MUỘN
     + mực CMYK duyệt 8 kg / kho mới giao 5 kg     → "đã cấp 5 · đang lĩnh 3".

  ⑤ Tem decal · gỡ giấy khỏi quy cách             → khối "BỎ QUA" (lệnh chưa chọn giấy).

  + Đẩy LSX26-0005 / LSX26-0006 từ `nhap` lên `san_sang` để bài ghép GB26-0004 quay lại bảng (bài
    vào phạm vi khi CÓ thành viên trong phạm vi) — chuỗi Couché 300 chạy lại 500 → 460,42 →
    405,92. Bước In offset của hai lệnh đó đang bị bước chung của bài đè, nên dòng vật tư khai ở
    đó KHÔNG sinh nhu cầu riêng; Couché 300 không bị đụng thêm gì.

Hai pha, cố ý:
  · Pha A dựng lệnh rồi ĐỌC LẠI `can_doi()` để lấy ngày cần + lượng cần THẬT do engine tính.
  · Pha B mới nắn hạn sản xuất và cân số lô tồn / phiếu mua theo đúng số vừa đọc.
Làm ngược lại (đoán trước số kg rồi chèn lô) là gán số chết: engine đổi công thức một cái là màu
đổi hết mà không ai biết.

Idempotent: guard theo tên phiếu tính giá. KHÔNG đụng schema, không migration.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.customer import Customer
from .models.kho_hang import KhoHang
from .models.loai_san_pham import LoaiSanPham
from .models.lsx import TT_NHAP, TT_SAN_SANG, Lsx, LsxCongDoanVatTu
from .models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia
from .models.purchase import PR_APPROVED, PurchaseRequest, PurchaseRequestLine, Supplier
from .models.stock_lot import LOT_AVAILABLE, StockLot
from .models.stock_request import (
    REQ_DONE,
    REQ_PARTIAL,
    REQ_XUAT,
    StockRequest,
    StockRequestLine,
)
from .models.vat_lieu_kho import HANG_GIAY, HANG_VAT_TU, GiayNguyen, VatTuInAn
from .models.vat_tu_giu_cho import VatTuGiuCho
from .repositories.document_sequence_repo import DocumentSequenceRepository
from .repositories.user_repo import UserRepository
from .seed_luong_ban_sx import (
    _buoc,
    _co_phieu,
    _ensure_cong_doan,
    _giay,
    _ma_phieu,
    _may_id,
    _tao_bao_gia,
    _tao_don_hang,
    _utcnow,
)
from .services.sequence_service import SequenceService
from .services.tinh_gia_service import compute_phieu_snapshot

TEN_PHIEU_VT = "Bộ ấn phẩm khai trương chi nhánh Bình Dương"

# Mỗi sản phẩm = 1 ca của bảng cân đối. `ngay_can_sau` = số ngày kể từ HÔM NAY mà pha B sẽ nắn
# ngày cần về đúng đó — nắn bằng HẠN SẢN XUẤT, không chèn dòng lịch giả.
#  (khoá, tên, mã giấy, dài TP, rộng TP, khổ nguyên (dài, rộng), mã máy,
#   (màu mặt A, màu mặt B), số lượng, đvt, ngày cần sau ... ngày)
_SAN_PHAM: list[tuple] = [
    ("xanh", "Tờ hướng dẫn sử dụng A4 (1 màu 2 mặt)", "FORD-70-65x86",
     297, 210, (860, 650), "IN-01", (1, 1), 20000, "tờ", 6),
    ("do", "Tờ rơi A4 4 màu 2 mặt", "COUCHE-150-79x109",
     297, 210, (1090, 790), "IN-02", (4, 4), 30000, "tờ", 0),
    ("vang", "Thực đơn A4 (cán màng mờ 2 mặt)", "IVORY-350-79x109",
     297, 210, (1090, 790), "IN-02", (4, 4), 3000, "cái", 10),
    ("ve_muon", "Bảng giá treo A3 (cán màng mờ)", "DUPLEX-300",
     420, 297, (1090, 790), "IN-02", (4, 0), 2000, "cái", 8),
    ("bo_qua", "Tem decal cuộn 40×25mm", "COUCHE-300-65x86",
     40, 25, (860, 650), "IN-04", (4, 0), 5000, "cái", 12),
]
_NGAY_CAN_SAU = {s[0]: s[-1] for s in _SAN_PHAM}

# Routing từng sản phẩm. Bước XÉN RỜI (`CD-0014`, `to → cai`) là BẮT BUỘC với hàng tờ rời: chuỗi
# tính ngược đổi đơn vị NGAY TRONG một bước, nên thiếu bước bắc cầu tờ↔cái thì bước in nhận thẳng
# số thành phẩm làm số tờ — 20.000 tờ rơi bình 6 con/tờ vẫn đòi 20.000 tờ giấy thay vì ~3.400.
# Không dùng CD-0011 "Bế thành phẩm" cho hàng vuông vắn: bế đòi khuôn (`requires_tooling`), lệnh
# sẽ mắc ở checklist khuôn mà khuôn không phải thứ màn này đang trưng bày.
_ROUTING: dict[str, list[tuple[str, str, int]]] = {
    "xanh": [("CD-0001", "Ghi kẽm CTP", 1), ("CD-0002", "In offset", 2),
             ("CD-0014", "Xén rời thành phẩm", 1), ("CD-0012", "Đóng gói + nhập kho", 1)],
    "do": [("CD-0001", "Ghi kẽm CTP", 1), ("CD-0002", "In offset", 2),
           ("CD-0014", "Xén rời thành phẩm", 1), ("CD-0012", "Đóng gói + nhập kho", 1)],
    "vang": [("CD-0001", "Ghi kẽm CTP", 1), ("CD-0002", "In offset", 2),
             ("CD-0010", "Cán màng mờ", 2), ("CD-0014", "Xén rời thành phẩm", 1),
             ("CD-0012", "Đóng gói + nhập kho", 1)],
    "ve_muon": [("CD-0001", "Ghi kẽm CTP", 1), ("CD-0002", "In offset", 1),
                ("CD-0010", "Cán màng mờ", 1), ("CD-0014", "Xén rời thành phẩm", 1),
                ("CD-0012", "Đóng gói + nhập kho", 1)],
    "bo_qua": [("CD-0001", "Ghi kẽm CTP", 1), ("CD-0002", "In offset", 1),
               ("CD-0014", "Xén rời thành phẩm", 1), ("CD-0012", "Đóng gói + nhập kho", 1)],
}

# Bảng `suppliers` đang RỖNG — không có gì cho phiếu mua trỏ tới.
_NCC: list[tuple] = [
    ("Giấy Vĩnh Tiến", "0301234567", "giay", "Lô 12 KCN Vĩnh Lộc, TP.HCM", 30),
    ("Vật tư ngành in Sài Gòn", "0309876543", "vat_tu", "45 Lý Thường Kiệt, Q.10, TP.HCM", 15),
]


def _kho(db: Session) -> KhoHang:
    """Kho để treo lô tồn + phiếu xuất. Có kho rồi thì DÙNG LẠI (DB dev đang có "vsd"), chưa có
    mới khai một kho demo — bảng cân đối không nói được gì nếu hệ thống chưa có kho nào."""
    co = db.execute(select(KhoHang).order_by(KhoHang.id)).scalars().first()
    if co is not None:
        return co
    k = KhoHang(ma="KHO-0001", ten="Kho vật tư", vi_tri="Xưởng A — tầng trệt",
                ghi_chu="Kho chính chứa giấy + mực + màng.")
    db.add(k)
    db.flush()
    return k


def _ncc(db: Session) -> dict[str, Supplier]:
    co = {s.name: s for s in db.execute(select(Supplier)).scalars()}
    for ten, mst, nhom, dia_chi, ngay_no in _NCC:
        if ten in co:
            continue
        s = Supplier(name=ten, tax_code=mst, supplier_group=nhom, address=dia_chi,
                     credit_days=ngay_no, payment_terms=f"Công nợ {ngay_no} ngày")
        db.add(s)
        co[ten] = s
    db.flush()
    return co


def _tao_phieu(db: Session, *, cd: dict[str, int], sale_id: int | None, sale_ten: str,
               lsp_id: int | None, created) -> PhieuTinhGia:
    """1 phiếu 5 sản phẩm — mỗi sản phẩm sẽ thành 1 lệnh, mỗi lệnh là 1 ca của bảng cân đối."""
    p = PhieuTinhGia(
        ma=_ma_phieu(db, created), ten_san_pham=TEN_PHIEU_VT,
        kho_thanh_pham="A4 · A3 · tem 40×25mm", loai_san_pham_id=lsp_id,
        so_luong=20000, ktv=sale_ten, created_by=sale_id,
        ghi_chu="Gói khai trương chi nhánh Bình Dương: tờ hướng dẫn, tờ rơi phát tay, thực đơn, "
                "bảng giá treo và tem dán quà tặng. Giao 2 đợt theo lịch khai trương.",
        created_at=created, updated_at=created,
    )
    for thu_tu, (khoa, ten, ma_giay, dai, rong, (kn_dai, kn_rong),
                 ma_may, (mau_a, mau_b), sl, dvt, _ngay) in enumerate(_SAN_PHAM):
        g = _giay(db, ma_giay)
        tp = PhieuThanhPhan(
            thu_tu=thu_tu, loai_thanh_phan="to_roi", ten=ten,
            dai_thanh_pham=dai, rong_thanh_pham=rong,
            so_to_per_sp=1, so_luong=sl, don_vi_tinh=dvt, loai_san_pham_id=lsp_id,
            giay_id=(g.id if g else None), kho_nguyen=f"{kn_rong}×{kn_dai}",
            kho_nguyen_dai=kn_dai, kho_nguyen_rong=kn_rong, nguon_giay="cong_ty",
            bleed_mm=3, co_in=True,
            quy_cach_in=("hai_mat" if mau_b else "mot_mat"),
            kho_in_dai=kn_dai, kho_in_rong=kn_rong,
            con_auto=True, may_id=_may_id(db, ma_may),
            so_mau_a=mau_a, so_mau_b=mau_b,
        )
        for i, (ma_cd, ten_buoc, so_mat) in enumerate(_ROUTING[khoa]):
            tp.thanh_phams.append(_buoc(cd, ma_cd, ten_buoc, i, so_mat=so_mat))
        p.thanh_phans.append(tp)
    db.add(p)
    db.flush()
    compute_phieu_snapshot(db, p)   # giá vốn do ENGINE tính
    db.flush()
    return p


def _khai_vat_tu(db: Session, lsx: Lsx, cong_doan_id: int, vt: VatTuInAn,
                 sl: float, dvt: str) -> None:
    """Khai tay 1 dòng vật tư ở bước của lệnh — đúng đường người dùng khai trên màn bước lệnh."""
    buoc = next((c for c in lsx.cong_doans if c.cong_doan_id == cong_doan_id), None)
    if buoc is None:
        return
    db.add(LsxCongDoanVatTu(
        lsx_cong_doan_id=buoc.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
        vat_tu_ten_snapshot=vt.ten, don_vi_snapshot=dvt, so_luong=sl,
        thu_tu=len(buoc.vat_tus or []), tu_dong=False,
    ))


def _ton(db: Session, hang_loai: str, hang_id: int) -> float:
    """Tồn kho hiện có của một mặt hàng — cộng phần CÒN LẠI của mọi lô còn hiệu lực."""
    return float(sum(
        float(l.sl_con_lai or 0)
        for l in db.execute(
            select(StockLot).where(StockLot.hang_loai == hang_loai,
                                   StockLot.hang_id == hang_id,
                                   StockLot.trang_thai == LOT_AVAILABLE)
        ).scalars()
    ))


def _lo(db: Session, *, ma: str, kho_id: int, hang_loai: str, hang_id: int,
        sl: float, don_gia: int, ngay: date) -> None:
    db.add(StockLot(ma_lo=ma, hang_loai=hang_loai, hang_id=hang_id, kho_id=kho_id,
                    ngay_nhap=ngay, don_gia_nhap=don_gia, sl_ban_dau=sl, sl_con_lai=sl,
                    trang_thai=LOT_AVAILABLE))


def _phieu_mua(db: Session, *, code: str, ncc: Supplier, ngay_ve: date, hang_loai: str,
               hang_id: int, ten: str, dvt: str, sl: float, don_gia: int,
               nguoi_id: int, ghi_chu: str) -> None:
    """Phiếu mua ĐÃ DUYỆT + CÓ ngày về ⇒ engine đếm là "hàng đang về". Thiếu ngày về là không đếm."""
    now = _utcnow()
    pr = PurchaseRequest(
        code=code, status=PR_APPROVED, supplier_id=ncc.id, content=ghi_chu,
        needed_date=ngay_ve - timedelta(days=1), expected_receipt_date=ngay_ve,
        created_by_user_id=nguoi_id, approved_by_user_id=nguoi_id,
        submitted_at=now, approved_at=now, note=ghi_chu,
    )
    pr.lines.append(PurchaseRequestLine(
        hang_loai=hang_loai, hang_id=hang_id, item_name=ten, unit=dvt, quantity=sl,
        expected_unit_price=don_gia, discount_percent=0, vat_percent=8,
    ))
    db.add(pr)


def _phieu_xuat(db: Session, *, ma: str, kho_id: int, nguoi_id: int, lsx_id: int,
                hang_loai: str, hang_id: int, dvt: str, de_nghi: float, duyet: float,
                da_ung: float, ngay_can: date, ghi_chu: str) -> None:
    """Phiếu XUẤT kho cho lệnh. `sl_da_ung` = kho đã ghi sổ ⇒ "đã cấp"; `sl_duyet − sl_da_ung` =
    "đang lĩnh" (chỉ là nhãn nhắc việc, KHÔNG trừ thêm lần nữa vào tồn)."""
    r = StockRequest(
        ma=ma, loai=REQ_XUAT, nguoi_tao_id=nguoi_id, kho_id=kho_id, ngay_can=ngay_can,
        ghi_chu=ghi_chu, trang_thai=(REQ_DONE if da_ung >= duyet else REQ_PARTIAL),
        nguoi_duyet_id=nguoi_id, duyet_luc=_utcnow(),
    )
    r.lines.append(StockRequestLine(
        hang_loai=hang_loai, hang_id=hang_id, lsx_id=lsx_id, dvt=dvt,
        sl_de_nghi=de_nghi, sl_duyet=duyet, sl_da_ung=da_ung,
    ))
    db.add(r)


def _kh_service(db: Session):
    """Dựng `KeHoachVatTuService` y hệt router — một engine, một kết quả."""
    from .repositories.bai_ghep_repo import BaiGhepRepository
    from .repositories.don_vi_do_repo import DonViDoRepository
    from .repositories.lsx_repo import LsxRepository
    from .repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from .repositories.stock_lot_repo import StockLotRepository
    from .repositories.stock_request_repo import StockRequestRepository
    from .repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from .services.ke_hoach_vat_tu_service import KeHoachVatTuService
    from .services.vat_lieu_kho_service import VatLieuKhoService

    return KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db), bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db), suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


def _dong_giay(bang: dict, lsx_id: int) -> dict | None:
    """Dòng GIẤY của riêng lệnh trong bảng cân đối (bỏ dòng của bài ghép)."""
    for nhom in bang.get("items", []):
        if nhom.get("hang_loai") != HANG_GIAY:
            continue
        for d in nhom.get("dong", []):
            if d.get("lsx_id") == lsx_id and not d.get("bai_ghep_id"):
                return d
    return None


def seed_kh_vat_tu(db: Session) -> None:
    if _co_phieu(db, TEN_PHIEU_VT):
        return
    khach = db.execute(
        select(Customer).where(Customer.name.like("%An Phát%"))
    ).scalars().first()
    users = UserRepository(db)
    sale = users.get_by_username("sale1")
    if khach is None or sale is None:
        return   # thiếu nền demo (khách / sale) → không seed nửa vời
    kho = _kho(db)

    ke_hoach = users.get_by_username("kehoach") or sale
    thu_kho = users.get_by_username("thukho") or sale
    mua_hang = users.get_by_username("muahang") or sale
    cd = _ensure_cong_doan(db)
    ncc = _ncc(db)
    now = _utcnow()
    hom_nay = now.date()
    lsp = db.execute(
        select(LoaiSanPham).where(LoaiSanPham.ma == "LSP-0002")
    ).scalars().first()

    # ══ PHA A — luồng thương mại thật → 5 lệnh sản xuất ═══════════════════════════════════════
    ptg = _tao_phieu(
        db, cd=cd, sale_id=sale.id, sale_ten=f"{sale.name or sale.username} (Kinh doanh)",
        lsp_id=(lsp.id if lsp else None), created=now - timedelta(days=8),
    )
    tp_theo_khoa = {sp[0]: tp.id for sp, tp in zip(_SAN_PHAM, ptg.thanh_phans)}
    quote, version = _tao_bao_gia(
        db, ptg=ptg, khach=khach, sale_id=sale.id,
        seq=SequenceService(DocumentSequenceRepository(db)),
        created=now - timedelta(days=7),
    )
    order = _tao_don_hang(
        db, quote=quote, version=version, khach=khach, sale_id=sale.id,
        created=now - timedelta(days=5), han_giao_sau=20, po="PO-ANPHAT-2026-142",
        production_note="Gói khai trương — tem dán quà chưa chốt được giấy decal, "
                        "kế hoạch bổ sung khi mua được.",
    )
    db.commit()   # LsxService.tao tự commit — chốt phần thương mại trước cho sạch transaction

    from .repositories.audit_repo import AuditLogRepository
    from .repositories.lsx_repo import LsxRepository
    from .services.lsx_service import LsxService

    svc = LsxService(db, LsxRepository(db), AuditLogRepository(db),
                     SequenceService(DocumentSequenceRepository(db)))
    lenhs = svc.tao(order_id=order.id, order_line_ids=[ln.id for ln in order.lines],
                    actor=ke_hoach)
    theo_ptp = {l.phieu_thanh_phan_id: l for l in lenhs}
    lenh = {khoa: theo_ptp[tp_id] for khoa, tp_id in tp_theo_khoa.items() if tp_id in theo_ptp}
    if len(lenh) != len(_SAN_PHAM):
        return   # engine không sinh đủ lệnh → dừng, đừng để lại nửa bộ ca

    for khoa, lsx in lenh.items():
        # Hạn SX tạm đặt bằng ngày cần mong muốn; pha B nắn lại theo thời gian dẫn engine tính.
        lsx.han_hoan_thanh_sx = hom_nay + timedelta(days=_NGAY_CAN_SAU[khoa])
        # Ép `san_sang` để lệnh vào PHẠM VI TÍNH của bảng cân đối. Bước hoàn thiện còn chưa gán
        # máy (giống mọi lệnh demo đang có) — đó chính là cảnh báo "chưa suy được mốc" mà màn này
        # cần trưng bày, không phải lỗi phải chữa ở đây.
        lsx.trang_thai = TT_SAN_SANG

    # ⑤ Tem decal: GỠ giấy khỏi quy cách → rơi vào khối "bỏ qua" của bảng cân đối.
    tem = lenh["bo_qua"]
    qc = dict(tem.quy_cach_json or {})
    qc.pop("giay_id", None)
    tem.quy_cach_json = qc
    # GIỮ `san_sang`: khối "bỏ qua" chỉ gom lệnh ĐANG TRONG PHẠM VI TÍNH mà thiếu giấy. Hạ về
    # `nhap` là lệnh rơi khỏi phạm vi, khối kia rỗng — mất đúng cái ca muốn cho thấy.

    vts = {v.ma: v for v in db.execute(select(VatTuInAn)).scalars()}
    cd_in = cd["CD-0002"]
    _khai_vat_tu(db, lenh["xanh"], cd_in, vts["MUC-CMYK"], 12, "kg")
    # KHÔNG RÕ: mực pha Pantone xưởng mua theo HỘP, mà danh mục để đơn vị gốc là kg và bảng
    # `don_vi_quy_doi` không có cầu hộp→kg ⇒ engine từ chối đoán, dán nhãn "không đối chiếu được".
    _khai_vat_tu(db, lenh["xanh"], cd_in, vts["MUC-PANTONE"], 2, "hop")
    _khai_vat_tu(db, lenh["ve_muon"], cd_in, vts["MUC-CMYK"], 8, "kg")

    # Bài ghép GB26-0004 quay lại bảng: bài vào phạm vi khi CÓ thành viên trong phạm vi.
    for ma in ("LSX26-0005", "LSX26-0006"):
        l = db.execute(select(Lsx).where(Lsx.ma == ma)).scalars().first()
        if l is not None and l.trang_thai == TT_NHAP:
            l.trang_thai = TT_SAN_SANG
    db.commit()

    # ══ PHA B — đọc số THẬT engine tính rồi mới nắn ngày + cân lô tồn / phiếu mua ═════════════
    bang = _kh_service(db).can_doi()
    can: dict[str, tuple[date, float]] = {}
    for khoa in ("xanh", "do", "vang", "ve_muon"):
        d = _dong_giay(bang, lenh[khoa].id)
        if d and d.get("ngay_can"):
            can[khoa] = (d["ngay_can"], float(d.get("nhu_cau") or 0))

    for khoa, (ngay_can, _sl) in can.items():
        lech = ((hom_nay + timedelta(days=_NGAY_CAN_SAU[khoa])) - ngay_can).days
        if lech:
            lenh[khoa].han_hoan_thanh_sx += timedelta(days=lech)

    giay = {g.ma: g for g in db.execute(select(GiayNguyen)).scalars()}

    # XANH — kho phải CÓ ĐỦ giấy thì dòng mới xanh. Cỡ lô lấy từ NHU CẦU engine vừa tính (dư 25%
    # như xưởng vẫn nhập nguyên kiện) TRỪ tồn sẵn có, nên bộ ca tự đúng trên mọi DB: DB dev đã có
    # lô Ford khai tay thì lô này chỉ bù phần thiếu, DB trắng thì nó gánh cả.
    if "xanh" in can:
        con_thieu = can["xanh"][1] * 1.25 - _ton(db, HANG_GIAY, giay["FORD-70-65x86"].id)
        if con_thieu > 0:
            _lo(db, ma="LO-FORD70-VT01", kho_id=kho.id, hang_loai=HANG_GIAY,
                hang_id=giay["FORD-70-65x86"].id, sl=round(con_thieu, 2), don_gia=28000,
                ngay=hom_nay - timedelta(days=12))
    # VÀNG — hàng về TRƯỚC ngày cần 4 ngày; mua dư 15% như xưởng vẫn mua.
    if "vang" in can:
        ngay_can, sl = can["vang"]
        _phieu_mua(
            db, code="PMH-VT-01", ncc=ncc["Giấy Vĩnh Tiến"],
            ngay_ve=hom_nay + timedelta(days=max(1, (ngay_can - hom_nay).days - 4)),
            hang_loai=HANG_GIAY, hang_id=giay["IVORY-350-79x109"].id,
            ten="Giấy Ivory 350 79×109", dvt="kg", sl=round(sl * 1.15, 2), don_gia=32000,
            nguoi_id=mua_hang.id,
            ghi_chu="Mua cho thực đơn khai trương — NCC hẹn giao trước ngày lên máy.",
        )
    # VỀ MUỘN — cùng cách mua nhưng NCC hẹn giao SAU ngày cần 7 ngày.
    if "ve_muon" in can:
        ngay_can, sl = can["ve_muon"]
        _phieu_mua(
            db, code="PMH-VT-02", ncc=ncc["Giấy Vĩnh Tiến"],
            ngay_ve=ngay_can + timedelta(days=7),
            hang_loai=HANG_GIAY, hang_id=giay["DUPLEX-300"].id,
            ten="Giấy Duplex 300 79×109", dvt="kg", sl=round(sl * 1.15, 2), don_gia=24000,
            nguoi_id=mua_hang.id,
            ghi_chu="NCC hết khổ 79×109, hẹn lô kế tiếp — đã báo kế hoạch dời bước in.",
        )

    # XÁM + "đang lĩnh": kho phải CÓ mực thì phiếu xuất mới hợp lý. Lô 52 kg, đã xuất 17 kg
    # (12 cho lệnh ①, 5 cho lệnh ④) ⇒ còn lại 35 kg.
    muc = vts["MUC-CMYK"]
    _lo(db, ma="LO-MUC-CMYK-01", kho_id=kho.id, hang_loai=HANG_VAT_TU, hang_id=muc.id,
        sl=35, don_gia=185000, ngay=hom_nay - timedelta(days=6))
    _phieu_xuat(
        db, ma="DNX-VT01", kho_id=kho.id, nguoi_id=thu_kho.id, lsx_id=lenh["xanh"].id,
        hang_loai=HANG_VAT_TU, hang_id=muc.id, dvt="kg",
        de_nghi=12, duyet=12, da_ung=12, ngay_can=hom_nay - timedelta(days=1),
        ghi_chu="Cấp đủ mực CMYK cho tờ hướng dẫn — đã ký nhận tại kho.",
    )
    _phieu_xuat(
        db, ma="DNX-VT02", kho_id=kho.id, nguoi_id=thu_kho.id, lsx_id=lenh["ve_muon"].id,
        hang_loai=HANG_VAT_TU, hang_id=muc.id, dvt="kg",
        de_nghi=8, duyet=8, da_ung=5, ngay_can=hom_nay + timedelta(days=2),
        ghi_chu="Duyệt 8 kg, kho mới giao 5 kg — còn 3 kg chờ lĩnh nốt.",
    )
    db.commit()

    # ══ PHA C — giữ chỗ ══════════════════════════════════════════════════════════════════════
    from .services.giu_cho_service import GiuChoService

    for khoa in ("xanh", "do", "vang", "ve_muon"):
        GiuChoService(db, _kh_service(db)).bat(lsx_id=lenh[khoa].id)
    db.commit()

    # Chip "giữ lâu chưa chạy": ngưỡng 7 ngày, tính từ dòng giữ chỗ CŨ NHẤT của chủ thể.
    cu = now - timedelta(days=10)
    for r in db.execute(
        select(VatTuGiuCho).where(VatTuGiuCho.lsx_id == lenh["xanh"].id)
    ).scalars():
        r.created_at = cu
    db.commit()
