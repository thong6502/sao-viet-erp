"""Thực hiện sản xuất — KHO SẢN XUẤT: yêu cầu nhập kho thành phẩm · xác nhận kho · phân loại BTP dư
(Giai đoạn 5, §14).

Điều phối lệnh GHI của khâu kho. Tuân §18: kiểm quyền tại service → transaction → ghi audit →
(SSE do router phát sau commit). Truy vấn/ghi DB nằm ở `repositories/san_xuat_kho_repo`; ở đây chỉ luật.

Luật cứng:
  · §14.1 KCS tạo nhiều yêu cầu nhập kho MỘT PHẦN từ một batch ĐẠT; TỔNG yêu cầu của một batch ≤
    `batch.so_luong_dat`. Kho xác nhận từng phần (`so_luong_xac_nhan` cộng dồn) → mỗi lần đẻ một lot
    thành phẩm; phần đã xác nhận BỊ KHÓA. KCS huỷ phần chưa nhận để phân loại lại.
  · §14.2 BTP dư trước khi đóng nhóm phải phân loại thành `nhập kho BTP` / `mẫu lưu` / `phế`; riêng
    `nhập kho BTP` chờ kho xác nhận nhận (chặn đóng nhóm §16).

GATE hai phía: bên KCS/tổ (tạo yêu cầu, phân loại BTP) gate TỔ TRƯỞNG đúng tổ của công việc
(`_gate`); bên KHO (xác nhận nhận) gate quyền `kho` — kiểm ở ROUTER (nhân viên kho không phải tổ
trưởng), service chỉ ghi ai xác nhận.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat_kho import (
    HANG_BTP,
    HANG_THANH_PHAM,
    PL_NHAP_BTP,
    PHAN_LOAI_BTP_DU,
    YC_CHO_KHO,
    YC_DA_NHAP,
    YC_HUY,
    YC_MOT_PHAN,
    SanXuatKhoHang,
    SanXuatKhoLot,
    SanXuatNhapKhoYc,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.document_sequence_repo import DocumentSequenceRepository
from ...repositories.san_xuat_kho_repo import SanXuatKhoRepository
from ..sequence_service import SequenceService
from .kcs import _EPS, _so_khong_am
from .thuc_thi import _gate, _moc


# --- Registry hàng sản xuất (§14.2) ---------------------------------------------------------
def _get_or_create_hang(
    repo: SanXuatKhoRepository,
    *,
    user,
    order_id: int,
    loai_hang: str,
    nhom_id: int | None,
    lsx_id: int | None,
    cong_doan_ref_id: int | None,
    quy_cach: str | None,
    ten: str,
    don_vi: str,
) -> SanXuatKhoHang:
    """Tìm registry theo khóa danh tính; chưa có thì tạo (sinh mã HSX). Danh tính hàng ỔN ĐỊNH trong
    một đơn → không đẻ trùng."""
    hang = repo.tim_hang(
        order_id=order_id,
        loai_hang=loai_hang,
        nhom_id=nhom_id,
        lsx_id=lsx_id,
        cong_doan_ref_id=cong_doan_ref_id,
        quy_cach=quy_cach,
    )
    if hang is not None:
        return hang
    seq = SequenceService(DocumentSequenceRepository(repo.db))
    hang = SanXuatKhoHang(
        ma=seq.generate_code("san_xuat_kho_hang"),
        loai_hang=loai_hang,
        order_id=order_id,
        nhom_id=nhom_id,
        lsx_id=lsx_id,
        cong_doan_ref_id=cong_doan_ref_id,
        ten=(ten or "")[:255],
        quy_cach=quy_cach,
        don_vi=(don_vi or "")[:24],
        created_by=getattr(user, "id", None),
    )
    repo.add(hang)
    repo.flush()
    return hang


# --- Yêu cầu nhập kho thành phẩm (§14.1) ----------------------------------------------------
def tao_yeu_cau_nhap_thanh_pham(
    db: Session,
    *,
    user,
    kcs_batch_id: int,
    so_luong,
    quy_cach: str | None = None,
    ghi_chu: str | None = None,
) -> dict:
    """KCS tạo MỘT yêu cầu nhập kho thành phẩm từ một batch ĐẠT (§14.1).

    Gate tổ trưởng KCS (theo công việc của batch). Trần: tổng yêu cầu chưa-huỷ của batch + số mới
    ≤ `batch.so_luong_dat`. Danh tính thành phẩm = registry (đơn + nhóm)."""
    repo = SanXuatKhoRepository(db)
    kcs = repo.kcs_batch(kcs_batch_id)
    if kcs is None:
        raise ValueError("Không tìm thấy batch kiểm tra.")
    cv = repo.cong_viec(kcs.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch kiểm tra.")
    _gate(db, user, cv)

    so = _so_khong_am(so_luong, "Số lượng nhập kho")
    if so <= 0:
        raise ValueError("Số lượng nhập kho phải lớn hơn 0.")
    dat = float(kcs.so_luong_dat or 0)
    if dat <= 0:
        raise ValueError("Batch này không có số lượng đạt để nhập kho.")
    da_yeu_cau = repo.tong_yeu_cau_cua_batch(kcs_batch_id)
    if da_yeu_cau + so > dat + _EPS:
        raise ValueError(
            f"Tổng yêu cầu nhập kho ({da_yeu_cau + so:g}) vượt số lượng KCS đã chấp nhận ({dat:g})."
        )

    nhom = repo.nhom(kcs.nhom_id) if kcs.nhom_id else None
    if nhom is None:
        raise ValueError("Batch kiểm tra chưa gắn nhóm thành phẩm nên chưa thể nhập kho.")
    don_vi = (kcs.don_vi or cv.don_vi_ra or "").strip()

    hang = _get_or_create_hang(
        repo, user=user,
        order_id=nhom.order_id,
        loai_hang=HANG_THANH_PHAM,
        nhom_id=nhom.id,
        lsx_id=None,
        cong_doan_ref_id=None,
        quy_cach=(quy_cach or "").strip() or None,
        ten=nhom.ten or nhom.nhom_label or "",
        don_vi=don_vi,
    )

    yc = SanXuatNhapKhoYc(
        kcs_batch_id=kcs.id,
        hang_id=hang.id,
        order_id=nhom.order_id,
        nhom_id=nhom.id,
        so_luong_yeu_cau=so,
        so_luong_xac_nhan=0,
        don_vi=don_vi,
        quy_cach=(quy_cach or "").strip() or None,
        trang_thai=YC_CHO_KHO,
        ghi_chu=(ghi_chu or "").strip() or None,
        created_by=getattr(user, "id", None),
    )
    repo.add(yc)
    repo.flush()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_yeu_cau_nhap",
        target=f"san_xuat_nhap_kho_yc:{yc.id}",
        detail=f"kcs_batch={kcs.id} hang={hang.id} so_luong={so:g}",
    )
    db.commit()
    return {
        "yc_id": yc.id,
        "kcs_batch_id": kcs.id,
        "hang_id": hang.id,
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": yc.trang_thai,
        "version": yc.version,
    }


def _trang_thai_yc(yeu_cau: float, xac_nhan: float) -> str:
    if xac_nhan <= _EPS:
        return YC_CHO_KHO
    if xac_nhan + _EPS >= yeu_cau:
        return YC_DA_NHAP
    return YC_MOT_PHAN


def kho_xac_nhan_nhap(
    db: Session,
    *,
    user,
    yc_id: int,
    so_luong,
    kho_id: int,
    expected_version: int | None = None,
) -> dict:
    """KHO xác nhận nhận MỘT phần của yêu cầu nhập kho thành phẩm (§14.1). Gate quyền `kho` ở router.

    Cộng dồn `so_luong_xac_nhan` (≤ số yêu cầu), đẻ một lot thành phẩm cho phần vừa nhận (khoá), cập
    nhật trạng thái theo số. Phần đã ghi nhận không sửa ngược batch KCS (§14.1).

    `kho_id` BẮT BUỘC (31/08/2026) — không có kho đích thì lot thành phẩm là con số lơ lửng: không
    tra được tồn theo kho, không lập được phiếu xuất giao. Cố ý KHÔNG có giá trị mặc định: đoán kho
    hộ thủ kho là ghi sai chỗ cất mà không ai hay. Kho phải CÒN DÙNG (`active`) — xem
    `kho_nhan_duoc`."""
    repo = SanXuatKhoRepository(db)
    yc = repo.yc(yc_id)
    if yc is None:
        raise ValueError("Không tìm thấy yêu cầu nhập kho.")
    if yc.trang_thai in (YC_DA_NHAP, YC_HUY):
        raise ValueError("Yêu cầu nhập kho đã kết thúc, không thể xác nhận thêm.")
    if expected_version is not None and expected_version != yc.version:
        raise ValueError("Phiên bản không khớp — yêu cầu vừa được cập nhật, hãy tải lại.")
    if kho_id is None or not repo.kho_nhan_duoc(kho_id):
        raise ValueError("Kho đích không tồn tại hoặc đã ngừng dùng.")

    so = _so_khong_am(so_luong, "Số lượng nhận")
    if so <= 0:
        raise ValueError("Số lượng nhận phải lớn hơn 0.")
    da_nhan = float(yc.so_luong_xac_nhan or 0)
    yeu_cau = float(yc.so_luong_yeu_cau or 0)
    con_lai = yeu_cau - da_nhan
    if so > con_lai + _EPS:
        raise ValueError(f"Số nhận ({so:g}) vượt phần còn lại chưa nhận ({con_lai:g}).")

    lot = SanXuatKhoLot(
        hang_id=yc.hang_id,
        loai_hang=HANG_THANH_PHAM,
        order_id=yc.order_id,
        nhom_id=yc.nhom_id,
        kcs_batch_id=yc.kcs_batch_id,
        nhap_kho_yc_id=yc.id,
        so_luong=so,
        don_vi=yc.don_vi,
        phan_loai=None,
        kho_id=kho_id,
        kho_xac_nhan=True,
        xac_nhan_by_id=getattr(user, "id", None),
        xac_nhan_luc=_moc(),
        created_by=getattr(user, "id", None),
    )
    repo.add(lot)

    yc.so_luong_xac_nhan = da_nhan + so
    yc.trang_thai = _trang_thai_yc(float(yc.so_luong_yeu_cau or 0), float(yc.so_luong_xac_nhan or 0))
    yc.xac_nhan_last_by_id = getattr(user, "id", None)
    yc.xac_nhan_last_luc = _moc()
    yc.version += 1
    repo.flush()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_xac_nhan_nhap",
        target=f"san_xuat_nhap_kho_yc:{yc.id}",
        detail=(f"nhan={so:g} kho={kho_id} luy_ke={float(yc.so_luong_xac_nhan):g} "
                f"trang_thai={yc.trang_thai}"),
    )
    db.commit()
    return {
        "yc_id": yc.id,
        "lot_id": lot.id,
        "kcs_batch_id": yc.kcs_batch_id,
        "nhom_id": yc.nhom_id,
        "kho_id": kho_id,
        "trang_thai": yc.trang_thai,
        "so_luong_xac_nhan": float(yc.so_luong_xac_nhan or 0),
        "nguoi_tao_id": yc.created_by,
        "version": yc.version,
    }


def huy_phan_chua_nhan(
    db: Session,
    *,
    user,
    yc_id: int,
    expected_version: int | None = None,
) -> dict:
    """KCS huỷ PHẦN CHƯA NHẬN của yêu cầu để phân loại lại (§14.1). Gate tổ trưởng KCS. Phần đã kho
    xác nhận GIỮ nguyên (đã khoá); yêu cầu chốt về số đã nhận."""
    repo = SanXuatKhoRepository(db)
    yc = repo.yc(yc_id)
    if yc is None:
        raise ValueError("Không tìm thấy yêu cầu nhập kho.")
    if yc.trang_thai in (YC_DA_NHAP, YC_HUY):
        raise ValueError("Yêu cầu nhập kho đã kết thúc.")
    kcs = repo.kcs_batch(yc.kcs_batch_id)
    cv = repo.cong_viec(kcs.cong_viec_id) if kcs else None
    if cv is None:
        raise ValueError("Không tìm thấy công việc của yêu cầu.")
    _gate(db, user, cv)
    if expected_version is not None and expected_version != yc.version:
        raise ValueError("Phiên bản không khớp — yêu cầu vừa được cập nhật, hãy tải lại.")

    da_nhan = float(yc.so_luong_xac_nhan or 0)
    yc.so_luong_yeu_cau = da_nhan            # chốt trần về phần đã nhận
    yc.trang_thai = YC_DA_NHAP if da_nhan > _EPS else YC_HUY
    yc.version += 1
    repo.flush()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_huy_phan_chua_nhan",
        target=f"san_xuat_nhap_kho_yc:{yc.id}",
        detail=f"da_nhan={da_nhan:g} trang_thai={yc.trang_thai}",
    )
    db.commit()
    return {
        "yc_id": yc.id,
        "kcs_batch_id": yc.kcs_batch_id,
        "nhom_id": yc.nhom_id,
        "trang_thai": yc.trang_thai,
        "version": yc.version,
    }


# --- Phân loại BTP dư + kho xác nhận (§14.2) -------------------------------------------------
def phan_loai_btp_du(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    so_luong,
    phan_loai: str,
    quy_cach: str | None = None,
    nguon_batch_id: int | None = None,
    ghi_chu: str | None = None,
) -> dict:
    """Phân loại BTP DƯ của một công việc trước khi đóng nhóm (§14.2): `nhập kho BTP` / `mẫu lưu` /
    `phế`. Gate tổ trưởng tổ giữ BTP. `nhập kho BTP` chờ kho xác nhận (`kho_xac_nhan=false`); `mẫu
    lưu`/`phế` là chung cục ngay."""
    repo = SanXuatKhoRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate(db, user, cv)

    if phan_loai not in PHAN_LOAI_BTP_DU:
        raise ValueError("Phân loại BTP dư không hợp lệ.")
    so = _so_khong_am(so_luong, "Số lượng BTP dư")
    if so <= 0:
        raise ValueError("Số lượng BTP dư phải lớn hơn 0.")

    nhom = repo.nhom(cv.nhom_id) if cv.nhom_id else None
    if nhom is None:
        raise ValueError("Công việc chưa gắn nhóm thành phẩm.")
    don_vi = (cv.don_vi_ra or "").strip()
    quy_cach_n = (quy_cach or "").strip() or None

    hang = _get_or_create_hang(
        repo, user=user,
        order_id=nhom.order_id,
        loai_hang=HANG_BTP,
        nhom_id=nhom.id,
        lsx_id=cv.lsx_id,
        cong_doan_ref_id=cv.id,
        quy_cach=quy_cach_n,
        ten=cv.ten_cong_doan or nhom.ten or "",
        don_vi=don_vi,
    )

    cho_kho = phan_loai == PL_NHAP_BTP
    lot = SanXuatKhoLot(
        hang_id=hang.id,
        loai_hang=HANG_BTP,
        order_id=nhom.order_id,
        nhom_id=nhom.id,
        lsx_id=cv.lsx_id,
        cong_doan_ref_id=cv.id,
        nguon_batch_id=nguon_batch_id,
        quy_cach=quy_cach_n,
        so_luong=so,
        don_vi=don_vi,
        phan_loai=phan_loai,
        kho_xac_nhan=not cho_kho,     # mẫu lưu / phế: chung cục ngay; nhập kho BTP: chờ kho
        created_by=getattr(user, "id", None),
        ghi_chu=(ghi_chu or "").strip() or None,
    )
    repo.add(lot)
    repo.flush()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_phan_loai_btp",
        target=f"san_xuat_kho_lot:{lot.id}",
        detail=f"cong_viec={cv.id} phan_loai={phan_loai} so_luong={so:g}",
    )
    db.commit()
    return {
        "lot_id": lot.id,
        "hang_id": hang.id,
        "cong_viec_id": cv.id,
        "nhom_id": nhom.id,
        "phan_loai": phan_loai,
        "cho_kho": cho_kho,
    }


def kho_xac_nhan_btp(db: Session, *, user, lot_id: int) -> dict:
    """KHO xác nhận đã NHẬN BTP trả vào kho (§14.2). Gate quyền `kho` ở router. Chỉ lot BTP phân loại
    `nhập kho BTP` còn chờ."""
    repo = SanXuatKhoRepository(db)
    lot = repo.lot(lot_id)
    if lot is None:
        raise ValueError("Không tìm thấy lot BTP.")
    if lot.loai_hang != HANG_BTP or lot.phan_loai != PL_NHAP_BTP:
        raise ValueError("Chỉ BTP phân loại 'nhập kho BTP' mới cần kho xác nhận.")
    if lot.kho_xac_nhan:
        raise ValueError("Lot BTP này kho đã xác nhận nhận.")

    lot.kho_xac_nhan = True
    lot.xac_nhan_by_id = getattr(user, "id", None)
    lot.xac_nhan_luc = _moc()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_xac_nhan_btp",
        target=f"san_xuat_kho_lot:{lot.id}",
        detail=f"nhom={lot.nhom_id} so_luong={float(lot.so_luong or 0):g}",
    )
    db.commit()
    return {
        "lot_id": lot.id,
        "nhom_id": lot.nhom_id,
        "cong_viec_id": lot.cong_doan_ref_id,
        "nguoi_phan_loai_id": lot.created_by,
    }


# --- Đọc ------------------------------------------------------------------------------------
# `ten_kho` = bản đồ `{kho_id: tên}` dựng MỘT lần cho cả lượt đọc (xem `ten_kho_theo_ids`) — phơi
# tên kho chứ không phơi số id trần, và không N+1.
def _yc_ra(yc: SanXuatNhapKhoYc, ten_kho: dict[int, str] | None = None) -> dict:
    yeu_cau = float(yc.so_luong_yeu_cau or 0)
    xac_nhan = float(yc.so_luong_xac_nhan or 0)
    return {
        "id": yc.id,
        "kcs_batch_id": yc.kcs_batch_id,
        "hang_id": yc.hang_id,
        "nhom_id": yc.nhom_id,
        "order_id": yc.order_id,
        "so_luong_yeu_cau": yeu_cau,
        "so_luong_xac_nhan": xac_nhan,
        "con_lai": max(0.0, yeu_cau - xac_nhan),
        "don_vi": yc.don_vi,
        "quy_cach": yc.quy_cach,
        # Kho ĐỀ NGHỊ của KCS (có thể trống) — kho THẬT nằm trên từng lot.
        "kho_id": yc.kho_id,
        "kho_ten": (ten_kho or {}).get(yc.kho_id) if yc.kho_id else None,
        "trang_thai": yc.trang_thai,
        "ghi_chu": yc.ghi_chu,
        "version": yc.version,
    }


def _lot_ra(lot: SanXuatKhoLot, ten_kho: dict[int, str] | None = None) -> dict:
    return {
        "id": lot.id,
        "hang_id": lot.hang_id,
        "loai_hang": lot.loai_hang,
        "nhom_id": lot.nhom_id,
        "lsx_id": lot.lsx_id,
        "cong_doan_ref_id": lot.cong_doan_ref_id,
        "kcs_batch_id": lot.kcs_batch_id,
        "so_luong": float(lot.so_luong or 0),
        "don_vi": lot.don_vi,
        "phan_loai": lot.phan_loai,
        # Kho ĐÃ NHẬN lot này (BTP `mau_luu`/`phe` và lot cũ trước mg 0249 để trống).
        "kho_id": lot.kho_id,
        "kho_ten": (ten_kho or {}).get(lot.kho_id) if lot.kho_id else None,
        "kho_xac_nhan": bool(lot.kho_xac_nhan),
        "quy_cach": lot.quy_cach,
        "ghi_chu": lot.ghi_chu,
    }


def chi_tiet_kho_nhom(db: Session, nhom_id: int) -> dict:
    """Toàn cảnh kho của MỘT nhóm thành phẩm: yêu cầu nhập kho + lot + BTP đã phân loại (mặt đọc cho
    panel §14). Gate `read` ở router."""
    repo = SanXuatKhoRepository(db)
    yeu_cau = repo.cac_yc_cua_nhom(nhom_id)
    lots = repo.cac_lot_cua_nhom(nhom_id)
    btp = repo.btp_tra_cho_kho(nhom_id)
    ten_kho = repo.ten_kho_theo_ids(
        [y.kho_id for y in yeu_cau] + [l.kho_id for l in lots] + [l.kho_id for l in btp])
    return {
        "nhom_id": nhom_id,
        "yeu_cau": [_yc_ra(y, ten_kho) for y in yeu_cau],
        "lot": [_lot_ra(l, ten_kho) for l in lots],
        "btp_tra_cho_kho": [_lot_ra(l, ten_kho) for l in btp],
    }


def hop_thu_kho(db: Session) -> dict:
    """Hộp thư nhân viên KHO (§14, §17): mọi việc còn chờ kho hành động — yêu cầu nhập kho thành phẩm
    (chờ/một phần) + BTP `nhập kho BTP` chờ nhận. Gate quyền `kho` ở router."""
    repo = SanXuatKhoRepository(db)
    yeu_cau = repo.cac_yc_cho_kho()
    btp = repo.cac_btp_cho_kho()
    ten_kho = repo.ten_kho_theo_ids([y.kho_id for y in yeu_cau] + [l.kho_id for l in btp])
    return {
        "yeu_cau_nhap": [_yc_ra(y, ten_kho) for y in yeu_cau],
        "btp_cho_nhan": [_lot_ra(l, ten_kho) for l in btp],
    }
