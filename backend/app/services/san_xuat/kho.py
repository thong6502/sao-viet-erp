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

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.san_xuat import SanXuatCongViec
from ...models.san_xuat_kcs import KCS_LOAI_ROUTING, SanXuatKcsBatch
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
from ...repositories.delivery_repo import DeliveryRepository
from ...repositories.document_sequence_repo import DocumentSequenceRepository
from ...repositories.san_xuat_kho_repo import SanXuatKhoRepository
from ..sequence_service import SequenceService
from .kcs import _EPS, _so_khong_am
from .thuc_thi import _gate, _moc


class KhongConSoDuGuiKho(ValueError):
    """Không còn số đạt chưa gửi kho cho batch này — router dịch thành 409 (khác ValueError thường
    dịch 400). Kế thừa ValueError để nếu lỡ không được bắt riêng, `_chay` vẫn dịch 400, không bao
    giờ rơi thành 500 không rõ nguyên nhân."""


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
def _tao_yc_tu_batch(
    repo: SanXuatKhoRepository,
    *,
    user,
    kcs,
    cv,
    so: float,
    quy_cach: str | None = None,
    ghi_chu: str | None = None,
) -> dict:
    """Tạo MỘT `SanXuatNhapKhoYc` cho `so` đơn vị của một batch KCS đã qua đủ kiểm tra ở caller
    (gate/số lượng/loai/la_kcs_cuoi đã validate trước khi gọi hàm này) — dùng chung cho cả luồng
    thủ công (`tao_yeu_cau_nhap_thanh_pham`) lẫn luồng một nút (`tao_yeu_cau_kho_mot_nut`, §5.6)."""
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
    return {
        "yc_id": yc.id,
        "kcs_batch_id": kcs.id,
        "hang_id": hang.id,
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": yc.trang_thai,
        "version": yc.version,
    }


def tao_yeu_cau_nhap_thanh_pham(
    db: Session,
    *,
    user,
    kcs_batch_id: int,
    so_luong,
    quy_cach: str | None = None,
    ghi_chu: str | None = None,
) -> dict:
    """KCS tạo MỘT yêu cầu nhập kho thành phẩm THỦ CÔNG từ một batch ĐẠT (§14.1, không đổi hành vi
    — chỉ tái cấu trúc phần tạo dòng ra `_tao_yc_tu_batch` dùng chung với luồng một nút §5.6).

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

    ket = _tao_yc_tu_batch(repo, user=user, kcs=kcs, cv=cv, so=so, quy_cach=quy_cach, ghi_chu=ghi_chu)

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_yeu_cau_nhap",
        target=f"san_xuat_nhap_kho_yc:{ket['yc_id']}",
        detail=f"kcs_batch={kcs.id} hang={ket['hang_id']} so_luong={so:g}",
    )
    db.commit()
    return ket


def tao_yeu_cau_kho_mot_nut(db: Session, *, user, kcs_batch_id: int) -> dict:
    """Gửi kho MỘT NÚT (§5.6) — server tự tính 'số đạt chưa gửi' của batch KCS routing CUỐI, KHÔNG
    nhận số từ client. Khóa dòng batch (`with_for_update`) TRƯỚC khi đọc số để double-click không
    tạo 2 yêu cầu song song. Chỉ `loai=routing` + công việc `la_kcs_cuoi=true`."""
    repo = SanXuatKhoRepository(db)
    repo.khoa_batch_kcs(kcs_batch_id)          # khóa TRƯỚC khi đọc — chặn race double-click
    kcs = repo.kcs_batch(kcs_batch_id)
    if kcs is None:
        raise ValueError("Không tìm thấy batch kiểm tra.")
    cv = repo.cong_viec(kcs.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch kiểm tra.")
    _gate(db, user, cv)

    if kcs.loai != KCS_LOAI_ROUTING:
        raise ValueError("Chỉ batch kiểm theo routing mới gửi kho theo lối một nút.")
    if not cv.la_kcs_cuoi:
        raise ValueError("Chỉ công việc KCS cuối mới được gửi kho.")

    dat = float(kcs.so_luong_dat or 0)
    da_yeu_cau = repo.tong_yeu_cau_cua_batch(kcs_batch_id)
    con_lai = dat - da_yeu_cau
    if con_lai <= _EPS:
        raise KhongConSoDuGuiKho("Không còn số đạt chưa gửi kho cho batch này.")

    ket = _tao_yc_tu_batch(repo, user=user, kcs=kcs, cv=cv, so=con_lai)

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_yeu_cau_nhap_mot_nut",
        target=f"san_xuat_nhap_kho_yc:{ket['yc_id']}",
        detail=f"kcs_batch={kcs.id} hang={ket['hang_id']} so_luong={con_lai:g} (tu_dong)",
    )
    db.commit()
    return ket


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
def _nhan_theo_yc(db: Session, yeu_cau: list[SanXuatNhapKhoYc]) -> dict[int, dict]:
    """`{kcs_batch_id: {loai_buoc, nha_cung_cap}}` — nạp MỘT lô cho cả hộp thư.

    Chỉ hai field: nhân viên kho nhận THÀNH PHẨM, không nhận dao, nên khuôn không có nghĩa ở đây.
    Nhưng "lô này vừa từ nhà gia công về hay tổ trong nhà làm" thì có: kiểm nhập hai đường đó
    khác nhau, mà trước 04/09/2026 dòng chờ kho không nói được một chữ nào.
    """
    ids = {y.kcs_batch_id for y in yeu_cau if y.kcs_batch_id}
    if not ids:
        return {}
    rows = db.execute(
        select(
            SanXuatKcsBatch.id, SanXuatCongViec.loai_buoc, SanXuatCongViec.nha_cung_cap
        )
        .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatKcsBatch.cong_viec_id)
        .where(SanXuatKcsBatch.id.in_(ids))
    ).all()
    return {int(r[0]): {"loai_buoc": r[1], "nha_cung_cap": r[2]} for r in rows}


def _yc_ra(yc: SanXuatNhapKhoYc, ten_kho: dict[int, str] | None = None,
           nhan: dict[int, dict] | None = None) -> dict:
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
        "nhan": (nhan or {}).get(yc.kcs_batch_id),
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
        # Kho ĐÃ NHẬN lot này (BTP `mau_luu`/`phe` và lot cũ trước mg 0255 để trống).
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
    nhan = _nhan_theo_yc(db, yeu_cau)
    return {
        "yeu_cau_nhap": [_yc_ra(y, ten_kho, nhan) for y in yeu_cau],
        "btp_cho_nhan": [_lot_ra(l, ten_kho) for l in btp],
    }


def ton_kha_dung_thanh_pham(db: Session, nhom_id: int) -> dict:
    """Thành phẩm của MỘT nhóm còn giao được bao nhiêu, và giao từ kho nào.

    HÔM NAY CHỈ CÓ MỘT NGƯỜI GỌI: `lenh_sx/ho_so._giao_hang`. `delivery_service` CHƯA dùng hàm này
    — `grep` cả `backend/` lẫn `frontend/` không ra chỗ nào khác.

    Ý ĐỊNH (chưa thành, đừng đọc câu dưới như việc đã rà): hàm này sẽ là nguồn DUY NHẤT cho cả hai
    bên — nút "Lập phiếu giao" ở màn Hồ sơ lệnh sản xuất (Task 12) đọc `hang[].so_toi_da` để KHOÁ ô
    số lượng, còn form giao hàng đọc chính `hang[]` để ĐIỀN SẴN (thành phẩm · kho · đơn vị · số
    lượng). Lý do đáng làm: hai bên tự tính thì sớm muộn một bên cho bấm cái bên kia từ chối, và
    người dùng không có cách nào biết bên nào đúng. Ngày nối bên giao hàng vào, sửa lại đoạn này.

    --- TRẦN NẰM Ở TỪNG DÒNG `hang[]`, KHÔNG CÓ SCALAR CẤP NHÓM ---------------------------------
    Bản đầu trả một `so_toi_da` cho cả nhóm, tính bằng `Σ lot của nhóm − Σ đã giao của MỌI dòng
    đơn trong nhóm`. Hai vế đó ở hai không gian gộp khác nhau và ra SỐ SAI ở đúng ca mà nhóm sinh
    ra để phục vụ: reviewer dựng nhóm 2 dòng đơn, kho còn 300 thật mà hàm trả 100 — giao thêm một
    lượt nữa là nút tắt vĩnh viễn trong khi hàng vẫn nằm đó. Nhóm nhiều dòng đơn là hình dạng
    CHÍNH THỨC của hệ (`SanXuatNhomLsx.lsx_id` unique, `nhom_id` thì không), không phải ca dựng.

    Nên trần chuyển xuống MỖI mặt hàng, và scalar cấp nhóm bị BỎ HẲN — giữ cả hai là để hai con số
    cạnh nhau mà một cái sai, rồi mặt đọc nhặt cái tiện tay hơn.

    --- KHI NÀO TÍNH ĐƯỢC TRẦN -----------------------------------------------------------------
    Trần của một mặt hàng = lot của chính nó − đã giao của ĐÚNG dòng đơn của nó. Ánh xạ đó chỉ
    dựng được khi nhóm là 1–1–1: đúng MỘT dòng đơn (không thành viên nào thiếu `order_line_id`) và
    đúng MỘT mặt hàng thành phẩm. Lý do: registry thành phẩm neo NHÓM chứ không neo dòng đơn
    (`_tao_yc_tu_batch` tạo hàng với `lsx_id=None`), nên nhóm 2 dòng đơn thì không có cách nào
    biết lượt giao nào thuộc mặt hàng nào; nhóm 2 mặt hàng (khác quy cách) chia nhau CÙNG một dòng
    đơn cũng thế.

    Không dựng được ⇒ `so_toi_da = None` + `khong_tinh_duoc = True` cho riêng mặt hàng đó. Một con
    số sai mà trông chắc chắn tệ hơn hẳn một ô trống có lý do. `so_luong` vẫn có (tồn thật của
    dòng), nên nút KHÔNG bị tắt oan — mặt đọc mở form và bắt người lập phiếu tự kiểm.

    --- CHIA PHẦN ĐÃ GIAO KHI MỘT MẶT HÀNG NẰM Ở NHIỀU KHO ---------------------------------------
    `hang[]` gom theo cặp (mặt hàng × kho) vì phiếu xuất đi từ MỘT kho. Số đã giao thì không mang
    thông tin kho, nên nó được TRỪ DẦN theo `kho_id` tăng dần: kho đầu hết mới trừ sang kho sau.
    Cách chia là quy ước, nhưng nhờ nó `Σ so_toi_da của một mặt hàng` ĐÚNG bằng trần thật của mặt
    hàng đó và mỗi dòng không bao giờ vượt tồn của chính kho nó. Cộng thẳng cột là ra số đúng.

    --- HAI VẾ CỦA PHÉP TRỪ --------------------------------------------------------------------
      · ĐÃ VÀO KHO đọc từ LOT thành phẩm có `kho_xac_nhan` — tức thủ kho đã bấm nhận. KHÔNG đọc
        `nhap_kho_yc.so_luong_yeu_cau`: yêu cầu là lời của KCS, hàng vẫn nằm ở tổ cho tới lúc kho
        nhận. Lot là bảng CHỈ-THÊM nên tổng này không bao giờ bị sửa lùi.
      · ĐÃ THỰC NHẬN đọc `delivery_trip_lines.qty_giao` qua các chuyến trong
        `LAN_GIAO_CO_HANG_DEN_TAY` (`delivery_repo.da_giao_theo_dong`), KHÔNG phải
        `delivery_request_lines.qty` — số đó là số YÊU CẦU giao, có ngay lúc lập phiếu dù xe chưa
        chạy, và vẫn còn đó khi chuyến thất bại.

    --- CÒN LẠI MỘT GIỚI HẠN, NÓI THẲNG --------------------------------------------------------
    ĐƠN VỊ: `lot.don_vi` (đơn vị kho ghi nhận) và `qty_giao` (đơn vị dòng đơn) được coi là CÙNG
    một thang. Đúng với dữ liệu hôm nay (thành phẩm nhập kho theo đúng đơn vị bán) nhưng KHÔNG có
    ràng buộc nào bắt buộc thế — trừ hai thang khác nhau là ra một con số vô nghĩa. Nhóm gom nhiều
    đơn vị khác nhau ⇒ `don_vi_lech = True` để mặt đọc biết đường im con số tổng đi.

    `da_nhap_kho` và `da_giao` là số CẤP NHÓM (mọi mặt hàng, mọi dòng đơn) — để đối chiếu, không
    phải để lập phiếu. `so_lenh_trong_nhom` nói mức gộp: `1` thì số của nhóm chính là số của lệnh.
    Nhóm chưa có lot nào ⇒ `hang` rỗng và `co_the_giao=False`.
    """
    repo = SanXuatKhoRepository(db)
    lots = [
        l for l in repo.cac_lot_cua_nhom(nhom_id)
        if l.loai_hang == HANG_THANH_PHAM and l.kho_xac_nhan
    ]
    ten_kho = repo.ten_kho_theo_ids([l.kho_id for l in lots])

    thanh_vien = repo.thanh_vien_nhom(nhom_id)
    dong_don = sorted({ol for _, ol in thanh_vien if ol is not None})
    thieu_dong_don = any(ol is None for _, ol in thanh_vien)

    # Gộp theo (mặt hàng, kho): form giao hàng lập phiếu XUẤT từ MỘT kho, nên hai lot cùng món ở
    # hai kho khác nhau là hai dòng phải điền riêng, không phải một con số cộng lại.
    gom: dict[tuple[int, int | None], dict] = {}
    for l in lots:
        khoa = (int(l.hang_id), l.kho_id)
        dong = gom.get(khoa)
        if dong is None:
            hang = repo.hang(l.hang_id)
            dong = gom[khoa] = {
                "hang_id": int(l.hang_id),
                "ma": getattr(hang, "ma", None),
                "ten": getattr(hang, "ten", None),
                "quy_cach": l.quy_cach or getattr(hang, "quy_cach", None),
                "don_vi": l.don_vi,
                "kho_id": l.kho_id,
                "kho_ten": ten_kho.get(l.kho_id) if l.kho_id else None,
                # Tồn THẬT của cặp (mặt hàng × kho) này, CHƯA trừ đã giao. Trần để lập phiếu là
                # `so_toi_da` bên dưới — hai số khác nhau và tên phải nói ra điều đó.
                "so_luong": 0.0,
                "so_toi_da": None,
                "khong_tinh_duoc": True,
            }
        dong["so_luong"] += float(l.so_luong or 0)

    da_nhap = sum(float(l.so_luong or 0) for l in lots)
    order_id = next((l.order_id for l in lots if l.order_id is not None), None)
    if order_id is None:
        nhom = repo.nhom(nhom_id)
        order_id = getattr(nhom, "order_id", None)

    theo_dong: dict[int, int] = {}
    if order_id is not None and dong_don:
        theo_dong = DeliveryRepository(db).da_giao_theo_dong(order_id)
    da_giao = float(sum(theo_dong.get(i, 0) for i in dong_don))

    hang_ids = {d["hang_id"] for d in gom.values()}
    mot_mot_mot = len(dong_don) == 1 and not thieu_dong_don and len(hang_ids) == 1
    if mot_mot_mot:
        for hid in hang_ids:
            con = float(theo_dong.get(dong_don[0], 0))
            for dong in sorted(
                (d for d in gom.values() if d["hang_id"] == hid),
                key=lambda d: (d["kho_id"] or 0),
            ):
                tru = min(dong["so_luong"], con)
                dong["so_toi_da"] = round(dong["so_luong"] - tru, 3)
                dong["khong_tinh_duoc"] = False
                con -= tru

    hang = sorted(gom.values(), key=lambda d: (d["hang_id"], d["kho_id"] or 0))
    co_the_giao = any(
        (d["so_luong"] if d["khong_tinh_duoc"] else (d["so_toi_da"] or 0.0)) > _EPS
        for d in hang
    )
    for d in hang:
        d["so_luong"] = round(d["so_luong"], 3)
    return {
        "nhom_id": nhom_id,
        "order_id": order_id,
        "order_line_ids": dong_don,
        "so_lenh_trong_nhom": len(thanh_vien),
        "hang": hang,
        "da_nhap_kho": round(da_nhap, 3),
        "da_giao": round(da_giao, 3),
        "co_the_giao": co_the_giao,
        "don_vi_lech": len({l.don_vi for l in lots}) > 1,
    }
