"""Thực hiện sản xuất — SẢN LƯỢNG: ghi batch + lot đầu vào (Giai đoạn 3, §10.3 · §11.1).

Điều phối lệnh GHI batch sản lượng. Tuân §18 như lát phiên-chạy: kiểm quyền tại service (đúng
tổ trưởng) → transaction → ghi audit → (SSE do router phát sau commit). Truy vấn/ghi DB nằm ở
`repositories/san_xuat_san_luong_repo.py`; ở đây chỉ luật.

Luật cứng (§11.1): `tong = tot + hong` (dung sai làm tròn 3 số lẻ); hỏng ghi kèm mô tả tự do
(`mo_ta_loi`, tuỳ chọn) — danh mục lý do/lỗi ĐÃ GỠ. Chọn lot đầu vào (§10.3) dựng quan hệ truy vết
mẻ công đoạn trước → batch đầu ra.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG
from ...models.san_xuat_san_luong import (
    BG_XAC_NHAN,
    SanXuatBanGiao,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
)
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ..gio_xuong import moc_tu_client
from .thuc_thi import _gate, _moc

# Dung sai làm tròn cho ràng buộc tong = tot + hong: cột Numeric(18,3) nên nửa bậc số lẻ cuối là
# 0.0005 — quá ngưỡng này coi như nhập lệch chứ không phải sai số làm tròn.
_EPS = 0.0005
# Chỉ ghi sản lượng cho công việc ĐÃ khởi động (đang chạy / tạm dừng / đã xong) — chưa bắt đầu thì
# chưa có gì để ghi.
_TRANG_THAI_GHI_DUOC = (CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)
# Độ lệch đồng hồ chấp nhận giữa máy tổ gõ giờ và máy chủ khi chặn mẻ ở tương lai.
_LECH_DONG_HO = timedelta(minutes=5)


def _so_khong_am(x, ten: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{ten} không hợp lệ.")
    if v != v or v in (float("inf"), float("-inf")):  # NaN/inf
        raise ValueError(f"{ten} không hợp lệ.")
    if v < 0:
        raise ValueError(f"{ten} không được âm.")
    return v


def _ket_qua_batch(cv, batch: SanXuatBatch | None, ket_qua_lsx: list[dict] | None = None) -> dict:
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "batch_id": batch.id if batch is not None else None,
        "ket_qua_lsx": ket_qua_lsx or [],
    }


def _toa_san_luong(
    db: Session, repo: SanXuatSanLuongRepository, *, cv, batch: SanXuatBatch, tot: float, actor,
) -> list[dict]:
    """Tự TOẢ sản lượng TỐT của một batch điểm-toả sang các nhánh LSX riêng (§ điểm toả bài ghép).

    Mỗi cạnh `SanXuatPhuThuoc` xuất phát từ `cv` (điểm toả, do `dung_diem_toa` sinh lúc phát hành)
    mang `ty_le_ghep` = số con/tờ của lệnh đích — nhân thẳng với `tot` ra sản lượng nhánh, rồi bàn
    giao THẲNG dạng đã xác nhận (không qua đề xuất/xác nhận hai bên): số này suy MỘT CHIỀU từ
    `tot`, không thể vượt, nên không cần vòng thương lượng như bàn giao người khai tay (§11.2)."""
    if tot <= 0:
        return []
    canh = repo.canh_toa_di_tu(cv.id)
    if not canh:
        return []
    ket_qua: list[dict] = []
    now = _moc()
    for c in canh:
        dich_cv = repo.cong_viec(c.dich_cong_viec_id)
        if dich_cv is None or dich_cv.lsx_id is None or not c.ty_le_ghep:
            continue
        sl_nhanh = round(tot * float(c.ty_le_ghep), 3)
        if sl_nhanh <= 0:
            continue
        don_vi_nhanh = c.don_vi_dich or dich_cv.don_vi_vao or batch.don_vi
        kq = SanXuatKetQuaNhanh(
            batch_id=batch.id, lsx_id=dich_cv.lsx_id, so_luong=sl_nhanh, don_vi=don_vi_nhanh,
        )
        repo.add(kq)
        bg = SanXuatBanGiao(
            nguon_cong_viec_id=cv.id,
            dich_cong_viec_id=dich_cv.id,
            cung_to=False,
            so_luong=sl_nhanh,
            don_vi=don_vi_nhanh,
            trang_thai=BG_XAC_NHAN,
            de_xuat_by_id=getattr(actor, "id", None),
            de_xuat_luc=now,
            xac_nhan_by_id=getattr(actor, "id", None),
            xac_nhan_luc=now,
        )
        repo.add(bg)
        repo.flush()
        kq.ban_giao_id = bg.id
        ket_qua.append({
            "lsx_id": dich_cv.lsx_id, "so_luong": sl_nhanh, "don_vi": don_vi_nhanh,
            "ban_giao_id": bg.id,
        })
    return ket_qua


def _chuan_hoa_lot(
    repo: SanXuatSanLuongRepository, dich_cv, don_vi_mac_dinh: str, raw: dict,
    dv_ten: dict[str, str],
) -> SanXuatBatchLotVao:
    """Dựng một dòng lot đầu vào từ payload thô, kiểm §10.3. KHÔNG add vào session (caller làm).
    Nguồn duy nhất là mẻ đầu ra của công đoạn trước (lot BTP trong kho đã gỡ 17/09/2026)."""
    so_luong = _so_khong_am(raw.get("so_luong"), "Số lượng lot")
    if so_luong <= 0:
        raise ValueError("Số lượng lot phải lớn hơn 0.")
    don_vi = (raw.get("don_vi") or don_vi_mac_dinh or "").strip()
    if not don_vi:
        raise ValueError("Lot đầu vào chưa có đơn vị.")

    nguon_batch_id = raw.get("nguon_batch_id")
    if not nguon_batch_id:
        raise ValueError("Lot từ công đoạn trước phải chọn batch nguồn.")
    nguon = repo.batch(int(nguon_batch_id))
    if nguon is None:
        raise ValueError("Không tìm thấy batch nguồn của lot đầu vào.")
    if nguon.cong_viec_id == dich_cv.id:
        raise ValueError("Batch nguồn không được trùng chính công việc đang ghi.")
    # Batch nguồn là điểm toả bài ghép (đã tách theo LSX) — công việc đang ghi phải THUỘC một
    # LSX có phần trong đó, và không được dùng vượt phần đã toả cho LSX của chính nó.
    if dich_cv.lsx_id is not None and repo.co_ket_qua_nhanh(nguon.id):
        kq = repo.ket_qua_nhanh_cua(nguon.id, dich_cv.lsx_id)
        if kq is None:
            raise ValueError(
                "Batch nguồn đã toả theo từng lệnh sản xuất — lệnh này không có phần trong đó."
            )
        da_dung = repo.da_dung_nhanh(nguon.id, dich_cv.lsx_id)
        if da_dung + so_luong > float(kq.so_luong) + _EPS:
            raise ValueError(
                f"Vượt phần đã toả cho lệnh sản xuất này "
                f"({float(kq.so_luong):g} {nhan_don_vi(dv_ten, kq.don_vi)})."
            )

    return SanXuatBatchLotVao(
        nguon_batch_id=int(nguon_batch_id),
        so_luong=so_luong,
        don_vi=don_vi,
    )


def tao_batch(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    bat_dau: datetime,
    ket_thuc: datetime,
    tong,
    tot,
    hong=0,
    don_vi: str | None = None,
    mo_ta_loi: str | None = None,
    ghi_chu: str | None = None,
    lot_vao: list[dict] | None = None,
) -> dict:
    """Ghi MỘT batch sản lượng (§11.1) + các lot đầu vào (§10.3). Cho nhiều batch một phần / công đoạn.

    Ràng buộc: `tong = tot + hong`. Đơn vị bỏ trống ⇒ lấy `don_vi_ra` của công việc (đơn vị bản
    địa công đoạn)."""
    repo = SanXuatSanLuongRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate(db, user, cv)
    if cv.trang_thai not in _TRANG_THAI_GHI_DUOC:
        raise ValueError("Chỉ ghi sản lượng cho công việc đã bắt đầu.")

    tong_f = _so_khong_am(tong, "Tổng số lượng")
    tot_f = _so_khong_am(tot, "Số lượng tốt")
    hong_f = _so_khong_am(hong, "Số lượng hỏng")
    if tong_f <= 0:
        raise ValueError("Tổng số lượng phải lớn hơn 0.")
    if abs(tong_f - (tot_f + hong_f)) > _EPS:
        raise ValueError("Tổng số lượng phải bằng Tốt + Hỏng.")

    if bat_dau is None or ket_thuc is None:
        raise ValueError("Batch phải có khoảng thời gian bắt đầu và kết thúc.")
    # Ô `datetime-local` gửi chuỗi KHÔNG offset ⇒ naive = GIỜ TƯỜNG xưởng. Quy về UTC THẬT ngay ở
    # cửa vào để cửa sổ mẻ đo cùng thước với khoảng tham gia và chấm công (§7.3/§12.1), xem
    # `services/gio_xuong.moc_tu_client`.
    bat_dau = moc_tu_client(bat_dau)
    ket_thuc = moc_tu_client(ket_thuc)
    if ket_thuc < bat_dau:
        raise ValueError("Kết thúc batch không được trước khi bắt đầu.")
    # Mẻ ghi SAU khi làm xong. Cửa sổ ở tương lai là gõ nhầm hoặc để nguyên giờ kế hoạch (16/09/2026:
    # ba mẻ Dán mang 17/09 20:00→22:50 khi bước mới chạy từ 16/09 15:24) — không dấu chấm công nào
    # rơi vào đó nên cổng §7.3 chặn chốt phân bổ mãi. Nới vài phút cho đồng hồ máy tổ lệch máy chủ.
    if ket_thuc > _moc() + _LECH_DONG_HO:
        raise ValueError("Giờ kết thúc mẻ đang ở sau thời điểm hiện tại — chỉ ghi mẻ đã làm xong.")

    don_vi_batch = (don_vi or cv.don_vi_ra or "").strip()
    if not don_vi_batch:
        raise ValueError("Batch chưa có đơn vị.")
    # Sản lượng được CỘNG THẲNG rồi đem trừ `so_luong_ra` (mục tiêu bước) — không có tầng quy đổi ở
    # đây. Nhận đơn vị khác `don_vi_ra` là cộng táo với cam: 20 ram ghi vào bước khai 10.000 tờ ra
    # "còn thiếu 9.980" dù việc đã xong. Từ chối rõ ràng đúng hơn là cộng nhầm im lặng.
    don_vi_cv = (cv.don_vi_ra or "").strip()
    # Câu này TỔ đọc, nên nói tên đơn vị ("tờ") chứ đừng nói mã ("to") — cột giữ mã, xem
    # `DonViDoRepository.ten_theo_ma`.
    dv_ten = DonViDoRepository(db).ten_theo_ma()
    if don_vi_cv and don_vi_batch != don_vi_cv:
        raise ValueError(
            f"Đơn vị sản lượng phải là “{nhan_don_vi(dv_ten, don_vi_cv)}” — "
            f"đúng đơn vị đầu ra của bước này."
        )

    # Dựng lot TRƯỚC khi add batch để bắt lỗi sớm (chưa chạm session cho tới khi hợp lệ hết).
    don_vi_lot_mac_dinh = (cv.don_vi_vao or don_vi_batch or "").strip()
    cac_lot = [
        _chuan_hoa_lot(repo, cv, don_vi_lot_mac_dinh, r, dv_ten)
        for r in (lot_vao or [])
    ]

    batch = SanXuatBatch(
        cong_viec_id=cv.id,
        bat_dau=bat_dau,
        ket_thuc=ket_thuc,
        tong=tong_f,
        tot=tot_f,
        hong=hong_f,
        don_vi=don_vi_batch,
        mo_ta_loi=(mo_ta_loi or "").strip() or None,
        ghi_chu=(ghi_chu or "").strip() or None,
        created_by=getattr(user, "id", None),
    )
    repo.add(batch)
    repo.flush()  # cần batch.id để neo lot
    for lot in cac_lot:
        lot.batch_id = batch.id
        repo.add(lot)

    from ...repositories.audit_repo import AuditLogRepository
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_tao_batch",
        target=f"san_xuat_batch:{batch.id}",
        detail=f"cong_viec={cv.id} tot={tot_f} hong={hong_f}",
    )
    ket_qua_lsx = _toa_san_luong(db, repo, cv=cv, batch=batch, tot=tot_f, actor=user)
    db.commit()
    return _ket_qua_batch(cv, batch, ket_qua_lsx)


def them_lot(
    db: Session,
    *,
    user,
    batch_id: int,
    nguon_batch_id: int | None = None,
    so_luong=0,
    don_vi: str | None = None,
) -> dict:
    """Bổ sung MỘT lot đầu vào cho batch đã tạo (§10.3) — khi tổ trưởng nhập truy vết sau."""
    repo = SanXuatSanLuongRepository(db)
    batch = repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch.")
    cv = repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    don_vi_lot_mac_dinh = (cv.don_vi_vao or batch.don_vi or "").strip()
    lot = _chuan_hoa_lot(
        repo,
        cv,
        don_vi_lot_mac_dinh,
        {
            "nguon_batch_id": nguon_batch_id,
            "so_luong": so_luong,
            "don_vi": don_vi,
        },
        DonViDoRepository(db).ten_theo_ma(),
    )
    lot.batch_id = batch.id
    repo.add(lot)
    db.commit()
    return _ket_qua_batch(cv, batch)
