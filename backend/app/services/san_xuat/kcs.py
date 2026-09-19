"""Thực hiện sản xuất — KCS theo LỆNH (`docs/design-kcs-theo-lenh.md`, mg `0306`).

KCS mở một lệnh → bấm một công đoạn → ghi Số lỗi (18/09/2026: form chỉ còn ô này — số đạt do máy
chủ suy từ phần tổ đã làm mà chưa kiểm, xem `_phan_chua_kiem`). MỘT hành động duy nhất
(`kiem_cong_doan`), làm được trên công đoạn đang chạy / tạm dừng / đã xong, lặp bao nhiêu lần cũng
được. Tuân §18: kiểm quyền tại service → transaction → audit → (SSE do router phát sau commit).

Luật cứng:
  · Người kiểm = thành viên một phòng ban `is_kcs` — kiểm được MỌI tổ, không có quyền KCS theo tổ.
    Đóng thiếu nhóm chỉ trưởng (`head_user_id`) của phòng ban `is_kcs`.
  · Kiểm KHÔNG trừ số, KHÔNG đẻ `san_xuat_batch`, KHÔNG đổi trạng thái công việc — bản ghi chất
    lượng thuần.
  · Lỗi > 0 ⇒ mô tả + ≥1 ảnh. Tổ chịu = tổ của chính công đoạn (tự động); tổ đó nhận thông báo
    tức thì và bấm "Đã xem" (`phan_hoi_luc`).
  · Công đoạn cuối của nhóm (`la_kcs_cuoi`) ⇒ Σ đạt ≤ Σ tốt tổ đã ghi; phần đạt đó là số đề xuất
    nhập kho (`kho.tao_yeu_cau_nhap_kho_cong_doan`).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG
from ...models.san_xuat_kcs import (
    KCS_DAT,
    KCS_DAT_MOT_PHAN,
    KCS_KHONG_DAT,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ..gio_xuong import thuc_te_hien_thi
from ..lenh_sx import boi_canh
from ..quyen_to import MUC_CUA_TOI, VIEC_XAC_NHAN, gate_to_tron, nguoi_co_quyen
from .thuc_thi import _moc

# Dung sai làm tròn (cột Numeric(18,3)) — như san_luong.
_EPS = 0.0005
# Kiểm được công đoạn ĐÃ khởi động (đang chạy / tạm dừng / đã xong).
_TRANG_THAI_KIEM_DUOC = (CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)
_CO_TRANG = 30


def _so_khong_am(x, ten: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{ten} không hợp lệ.")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{ten} không hợp lệ.")
    if v < 0:
        raise ValueError(f"{ten} không được âm.")
    return v


# --- Ai là KCS ------------------------------------------------------------------------------
def la_nguoi_kcs(db: Session, user) -> bool:
    return SanXuatKcsRepository(db).la_thanh_vien_to_kcs(getattr(user, "id", None))


def la_truong_kcs(db: Session, user) -> bool:
    return SanXuatKcsRepository(db).la_truong_to_kcs(getattr(user, "id", None))


def gate_kcs(db: Session, user) -> None:
    if not la_nguoi_kcs(db, user):
        raise PermissionError("Chỉ người thuộc tổ KCS mới kiểm được công đoạn.")


def gate_truong_kcs(db: Session, user) -> None:
    if not la_truong_kcs(db, user):
        raise PermissionError("Chỉ trưởng tổ KCS mới đóng thiếu được nhóm thành phẩm.")


# --- Luật dùng chung ------------------------------------------------------------------------
def _validate_checklist_bat_buoc(cv, checklist_ket_qua: list[dict] | None) -> list[dict] | None:
    """Mọi tiêu chí `bat_buoc=True` trong snapshot `cv.kcs_tieu_chi_json` phải có MỘT kết quả gửi
    kèm — khớp theo `thu_tu` (khoá ổn định kể cả mục bổ sung không có `tieu_chi_id`)."""
    snap = getattr(cv, "kcs_tieu_chi_json", None) or []
    bat_buoc_thu_tu = {it["thu_tu"] for it in snap if it.get("bat_buoc")}
    if not bat_buoc_thu_tu:
        return checklist_ket_qua
    da_co = {
        int(kq["thu_tu"]) for kq in (checklist_ket_qua or [])
        if kq.get("thu_tu") is not None
    }
    if bat_buoc_thu_tu - da_co:
        raise ValueError("Còn tiêu chí kiểm tra bắt buộc chưa ghi kết quả.")
    return checklist_ket_qua


def _ket_luan(dat: float, loi: float) -> str:
    if loi <= _EPS:
        return KCS_DAT
    if dat <= _EPS:
        return KCS_KHONG_DAT
    return KCS_DAT_MOT_PHAN


def _chuan_hoa_anh(raw: dict, uploaded_by: int | None) -> SanXuatKcsLoiAnh:
    file_url = (raw.get("file_url") or "").strip()
    file_name = (raw.get("file_name") or "").strip()
    if not file_url or not file_name:
        raise ValueError("Ảnh bằng chứng thiếu tên file hoặc đường dẫn.")
    return SanXuatKcsLoiAnh(
        file_name=file_name[:255],
        file_url=file_url[:500],
        file_type=(raw.get("file_type") or None),
        uploaded_by=uploaded_by,
    )


def _chan_vuot_tot(db: Session, repo: SanXuatKcsRepository, cv, dat_moi: float,
                   *, tru_batch_id: int | None = None) -> None:
    """Công đoạn cuối nhóm: Σ đạt không vượt Σ tốt tổ đã ghi — phần đạt là số đưa vào kho."""
    if not cv.la_kcs_cuoi:
        return
    tot = SanXuatSanLuongRepository(db).tong_tot(cv.id)
    da_dat = repo.tong_dat(cv.id, tru_batch_id=tru_batch_id)
    if da_dat + dat_moi > tot + _EPS:
        raise ValueError(
            f"Công đoạn cuối: tổng đạt ({da_dat + dat_moi:g}) vượt số tốt tổ đã ghi ({tot:g})."
        )


def _phan_chua_kiem(db: Session, repo: SanXuatKcsRepository, cv) -> float:
    """Phần tổ đã làm mà KCS chưa kiểm = Σ số lượng các mẻ − Σ (đạt + lỗi) các lần kiểm trước."""
    tot = SanXuatSanLuongRepository(db).tong_tot(cv.id)
    da_kiem = sum(
        float(k.so_luong_dat or 0) + float(k.so_luong_khong_dat or 0) for k in repo.cac_kcs_batch(cv.id)
    )
    return max(0.0, tot - da_kiem)


# --- Ghi ------------------------------------------------------------------------------------
def kiem_cong_doan(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    so_dat=None,
    so_loi=0,
    checklist_ket_qua: list[dict] | None = None,
    ghi_chu: str | None = None,
    loi_mo_ta: str | None = None,
    anh: list[dict] | None = None,
) -> dict:
    """Ghi MỘT lần kiểm công đoạn. Người kiểm do server chốt từ tài khoản; tổ chịu lỗi = tổ của
    công đoạn. Trả `notify_user_ids` = người Xác nhận sản lượng trọn tổ đó (router đẩy SSE).

    `so_dat` bỏ trống (form KCS chỉ gõ số lỗi): lần kiểm bao TRỌN phần tổ đã làm mà chưa kiểm, đạt =
    phần đó − số lỗi. Số lỗi không được vượt phần đó — lỗi là hàng tổ đã ghi, tổ chưa ghi mẻ thì chưa
    có gì để kiểm. Gửi `so_dat` tường minh thì giữ luật cũ (chỉ chặn đạt vượt tốt ở bước cuối)."""
    gate_kcs(db, user)
    repo = SanXuatKcsRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công đoạn.")
    if cv.trang_thai not in _TRANG_THAI_KIEM_DUOC:
        raise ValueError("Công đoạn chưa bắt đầu nên chưa kiểm được.")

    loi_sl = _so_khong_am(so_loi if so_loi not in (None, "") else 0, "Số lỗi")
    if so_dat in (None, ""):
        chua_kiem = _phan_chua_kiem(db, repo, cv)
        if chua_kiem <= _EPS:
            raise ValueError("Tổ chưa ghi thêm sản lượng nào từ lần kiểm trước — chưa có gì để kiểm.")
        if loi_sl > chua_kiem + _EPS:
            raise ValueError(
                f"Số lỗi ({loi_sl:g}) vượt phần tổ đã làm mà chưa kiểm ({chua_kiem:g})."
            )
        dat = max(0.0, chua_kiem - loi_sl)
    else:
        dat = _so_khong_am(so_dat, "Số đạt")
    if dat + loi_sl <= _EPS:
        raise ValueError("Nhập số đạt hoặc số lỗi.")
    checklist_ket_qua = _validate_checklist_bat_buoc(cv, checklist_ket_qua)

    mo_ta = (loi_mo_ta or "").strip()
    uid = getattr(user, "id", None)
    cac_anh: list[SanXuatKcsLoiAnh] = []
    if loi_sl > _EPS:
        if not mo_ta:
            raise ValueError("Có lỗi thì phải mô tả lỗi.")
        if not anh:
            raise ValueError("Có lỗi thì phải kèm ít nhất một ảnh.")
        cac_anh = [_chuan_hoa_anh(r, uid) for r in anh]
    _chan_vuot_tot(db, repo, cv, dat)

    luc = _moc()
    don_vi = (cv.don_vi_ra or "").strip()
    kcs = SanXuatKcsBatch(
        cong_viec_id=cv.id,
        nhom_id=cv.nhom_id,
        bat_dau=luc,
        ket_thuc=luc,
        so_luong_nhan=dat + loi_sl,
        so_luong_dat=dat,
        so_luong_khong_dat=loi_sl,
        don_vi=don_vi,
        ket_luan=_ket_luan(dat, loi_sl),
        ghi_chu=(ghi_chu or "").strip() or None,
        checklist_json=checklist_ket_qua,
        created_by=uid,
    )
    repo.add(kcs)
    repo.flush()

    loi_id = None
    if loi_sl > _EPS:
        loi = SanXuatKcsLoi(
            kcs_batch_id=kcs.id,
            mo_ta=mo_ta,
            to_chiu_id=cv.department_id,
            cong_doan_ref_id=cv.id,
            so_luong=loi_sl,
            don_vi=don_vi or None,
            created_by=uid,
        )
        repo.add(loi)
        repo.flush()
        for a in cac_anh:
            a.loi_id = loi.id
            repo.add(a)
        loi_id = loi.id

    AuditLogRepository(db).create(
        actor_user_id=uid,
        action="san_xuat_kcs_kiem",
        target=f"san_xuat_kcs_batch:{kcs.id}",
        detail=f"cong_viec={cv.id} dat={dat:g} loi={loi_sl:g}",
    )
    db.commit()
    lsx = repo.lsx(cv.lsx_id)
    return {
        "kcs_batch_id": kcs.id,
        "loi_id": loi_id,
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "lsx_id": cv.lsx_id,
        "lsx_ma": lsx.ma if lsx else None,
        "nhom_id": cv.nhom_id,
        "ten_cong_doan": cv.ten_cong_doan,
        "so_dat": dat,
        "so_loi": loi_sl,
        "ket_luan": kcs.ket_luan,
        "version": kcs.version,
        "nguoi_kiem": getattr(user, "name", None),
        "notify_user_ids": nguoi_co_quyen(db, cv.department_id, VIEC_XAC_NHAN),
    }


def _so_da_gui_kho(db: Session, cv) -> float:
    """Σ đã đề nghị nhập kho còn hiệu lực của công đoạn (đơn vị KCS) — đọc yêu cầu kho thật."""
    from .kho import dong_nhap_kho_cua_cong_viec, so_da_de_nghi_kcs

    if not cv.la_kcs_cuoi:
        return 0.0
    return so_da_de_nghi_kcs(dong_nhap_kho_cua_cong_viec(db, [cv.id]).get(cv.id, []))


def dieu_chinh_ket_qua(
    db: Session,
    *,
    user,
    kcs_batch_id: int,
    so_luong_dat,
    so_luong_khong_dat,
    checklist_ket_qua: list[dict] | None = None,
    ghi_chu: str | None = None,
    expected_version: int,
) -> dict:
    """Sửa tại chỗ một lần kiểm (không xoá) — tổng số đã kiểm giữ NGUYÊN, chỉ đổi cách chia đạt/lỗi.

    Yêu cầu nhập kho tính theo CÔNG ĐOẠN, không theo lần kiểm: chặn khi Σ đạt sau điều chỉnh thấp
    hơn số đã đề nghị kho còn hiệu lực (muốn hạ thêm thì nhờ kho huỷ yêu cầu trước)."""
    gate_kcs(db, user)
    repo = SanXuatKcsRepository(db)
    kcs = repo.kcs_batch(kcs_batch_id)
    if kcs is None:
        raise ValueError("Không tìm thấy lần kiểm.")
    cv = repo.cong_viec(kcs.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công đoạn của lần kiểm.")
    if expected_version != kcs.version:
        raise ValueError("Phiên bản không khớp — kết quả vừa được cập nhật, hãy tải lại.")
    dat = _so_khong_am(so_luong_dat, "Số đạt")
    loi_sl = _so_khong_am(so_luong_khong_dat, "Số lỗi")
    nhan = float(kcs.so_luong_nhan)
    if abs(nhan - (dat + loi_sl)) > _EPS:
        raise ValueError("Đạt + Lỗi phải bằng đúng số đã kiểm — điều chỉnh không đổi tổng.")
    checklist_ket_qua = _validate_checklist_bat_buoc(cv, checklist_ket_qua)
    cac_loi = repo.cac_loi_nhieu([kcs.id]).get(kcs.id, [])
    if loi_sl > _EPS and not cac_loi:
        raise ValueError("Lần kiểm này chưa có mô tả + ảnh lỗi — hãy kiểm thêm một lần để báo lỗi.")
    _chan_vuot_tot(db, repo, cv, dat, tru_batch_id=kcs.id)
    da_gui = _so_da_gui_kho(db, cv)
    if da_gui > _EPS:
        dat_sau = sum(float(k.so_luong_dat or 0) for k in repo.cac_kcs_batch(cv.id) if k.id != kcs.id) + dat
        if dat_sau + _EPS < da_gui:
            raise ValueError(
                f"Không thể điều chỉnh: công đoạn đã đề nghị nhập kho {da_gui:g} — tổng số đạt sau "
                f"điều chỉnh ({dat_sau:g}) không được thấp hơn. Nhờ kho huỷ yêu cầu trước nếu cần hạ."
            )

    truoc = (float(kcs.so_luong_dat), float(kcs.so_luong_khong_dat), kcs.ket_luan)
    kcs.so_luong_dat = dat
    kcs.so_luong_khong_dat = loi_sl
    kcs.ket_luan = _ket_luan(dat, loi_sl)
    if checklist_ket_qua is not None:
        kcs.checklist_json = checklist_ket_qua
    if ghi_chu is not None:
        kcs.ghi_chu = ghi_chu.strip() or None
    kcs.version += 1
    for l in cac_loi:
        l.so_luong = loi_sl
        l.version += 1

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_dieu_chinh",
        target=f"san_xuat_kcs_batch:{kcs.id}",
        detail=(
            f"truoc(dat={truoc[0]:g}, loi={truoc[1]:g}, ket_luan={truoc[2]}) "
            f"sau(dat={dat:g}, loi={loi_sl:g}, ket_luan={kcs.ket_luan})"
        ),
    )
    db.commit()
    return {
        "kcs_batch_id": kcs.id, "cong_viec_id": cv.id, "department_id": cv.department_id,
        "nhom_id": cv.nhom_id, "so_luong_nhan": nhan, "so_luong_dat": dat,
        "so_luong_khong_dat": loi_sl, "ket_luan": kcs.ket_luan, "version": kcs.version,
    }


def da_xem_loi(db: Session, *, user, loi_id: int) -> dict:
    """Tổ bị báo lỗi bấm "Đã xem" — người Xác nhận sản lượng TRỌN tổ chịu. Bấm lại không đổi gì."""
    repo = SanXuatKcsRepository(db)
    loi = repo.loi(loi_id)
    if loi is None:
        raise ValueError("Không tìm thấy lỗi.")
    gate_to_tron(db, getattr(user, "id", None), loi.to_chiu_id, VIEC_XAC_NHAN)
    kcs = repo.kcs_batch(loi.kcs_batch_id)
    if loi.phan_hoi_luc is None:
        loi.phan_hoi_by_id = getattr(user, "id", None)
        loi.phan_hoi_luc = _moc()
        loi.version += 1
        AuditLogRepository(db).create(
            actor_user_id=getattr(user, "id", None),
            action="san_xuat_kcs_da_xem_loi",
            target=f"san_xuat_kcs_loi:{loi.id}",
            detail=f"to={loi.to_chiu_id}",
        )
        db.commit()
    return {
        "loi_id": loi.id,
        "kcs_batch_id": loi.kcs_batch_id,
        "cong_viec_id": kcs.cong_viec_id if kcs else None,
        "department_id": loi.to_chiu_id,
        "da_xem_luc": thuc_te_hien_thi(loi.phan_hoi_luc),
        "nguoi_xem": repo.ten_nguoi([loi.phan_hoi_by_id]).get(loi.phan_hoi_by_id),
        "nguoi_kiem_id": kcs.created_by if kcs else None,
        "version": loi.version,
    }


# --- Đọc ------------------------------------------------------------------------------------
def _lan_kiem_ra(db: Session, repo: SanXuatKcsRepository,
                 batches: list[SanXuatKcsBatch]) -> dict[int, dict]:
    """{kcs_batch_id: lần kiểm bày ra} — lỗi/ảnh/tên người nạp GỘP một lượt."""
    ids = [b.id for b in batches]
    loi_map = repo.cac_loi_nhieu(ids)
    tat_ca_loi = [l for ds in loi_map.values() for l in ds]
    anh_map = repo.anh_cua_loi_nhieu([l.id for l in tat_ca_loi])
    ten = repo.ten_nguoi(
        {b.created_by for b in batches} | {l.phan_hoi_by_id for l in tat_ca_loi}
    )
    out: dict[int, dict] = {}
    for b in batches:
        out[b.id] = {
            "id": b.id,
            "nguoi_kiem": ten.get(b.created_by),
            "luc": thuc_te_hien_thi(b.ket_thuc or b.created_at),
            "so_dat": float(b.so_luong_dat or 0),
            "so_loi": float(b.so_luong_khong_dat or 0),
            "don_vi": b.don_vi,
            "ket_luan": b.ket_luan,
            "checklist": b.checklist_json or [],
            "ghi_chu": b.ghi_chu,
            "version": b.version,
            "loi": [
                {
                    "id": l.id,
                    "mo_ta": l.mo_ta,
                    "so_luong": float(l.so_luong or 0),
                    "don_vi": l.don_vi,
                    "to_chiu_id": l.to_chiu_id,
                    "da_xem_luc": thuc_te_hien_thi(l.phan_hoi_luc),
                    "nguoi_xem": ten.get(l.phan_hoi_by_id),
                    "anh": [
                        {"id": a.id, "file_name": a.file_name, "file_url": a.file_url,
                         "file_type": a.file_type}
                        for a in anh_map.get(l.id, [])
                    ],
                }
                for l in loi_map.get(b.id, [])
            ],
        }
    return out


def ket_qua_kcs_cong_viec(db: Session, user, cong_viec_id: int) -> dict:
    """Mục "Kết quả KCS" của một công đoạn. Người KCS xem mọi công đoạn; người khác theo phạm vi
    XEM của dòng quyền theo tổ (cùng phạm vi với chi tiết công việc)."""
    repo = SanXuatKcsRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công đoạn.")
    if not la_nguoi_kcs(db, user):
        from .board import _loc_viec_cua_tho, _pham_vi_doc

        _q, muc = _pham_vi_doc(db, user, cv.department_id)
        if muc == MUC_CUA_TOI and not _loc_viec_cua_tho(db, user, [cv]):
            raise PermissionError("Chỉ xem được việc đã giao cho mình.")
    batches = repo.cac_kcs_batch(cong_viec_id)
    ra = _lan_kiem_ra(db, repo, batches)
    return {
        "cong_viec_id": cv.id,
        "la_kcs_cuoi": bool(cv.la_kcs_cuoi),
        "checklist": cv.kcs_tieu_chi_json or [],
        "lan_kiem": [ra[b.id] for b in reversed(batches)],
    }


def _thu_tu_cong_doan(bc, lsx_id: int, thu_tu: dict[int, tuple[int, int]]):
    """Khoá xếp chuỗi công đoạn theo thứ tự routing của lệnh: việc riêng theo bước của nó, việc
    ghép theo bước sớm nhất của lệnh mà nó phủ."""
    def khoa(cv):
        if cv.lsx_id == lsx_id:
            buoc = [cv.lsx_cong_doan_id]
        else:
            buoc = bc.buoc_phu.get(cv.id, [])
        tt = [thu_tu[b][1] for b in buoc if b in thu_tu and thu_tu[b][0] == lsx_id]
        return (min(tt) if tt else 10**9, cv.phan_doan_so or 1, cv.id)
    return khoa


def _dong_kho_cua(bc, cv) -> list:
    """Dòng yêu cầu nhập kho của MỘT công đoạn cuối. `bc.nhap_kho_tp` phát dòng của công đoạn cuối
    cho mọi lệnh cùng nhóm — lọc lại đúng `cong_viec_id` và khử trùng."""
    if not cv.la_kcs_cuoi:
        return []
    thay: dict[int, object] = {}
    for ds in bc.nhap_kho_tp.values():
        for d in ds:
            if d.cong_viec_id == cv.id:
                thay.setdefault(d.line_id, d)
    return sorted(thay.values(), key=lambda d: d.line_id)


def _da_gui_kho(bc, cv) -> float:
    """Σ đã đề nghị kho còn hiệu lực của MỘT công đoạn cuối (đơn vị KCS)."""
    return sum(d.sl_da_de_nghi_kcs for d in _dong_kho_cua(bc, cv))


def _tom_cuoi(bc, cvs) -> dict | None:
    cuoi = [cv for cv in cvs if cv.la_kcs_cuoi]
    if not cuoi:
        return None
    tot = sum(float(b.tot or 0) for cv in cuoi for b in bc.batch[cv.id])
    dat = sum(float(k.so_luong_dat or 0) for cv in cuoi for k in bc.kcs[cv.id])
    da_yc = sum(_da_gui_kho(bc, cv) for cv in cuoi)
    return {
        "tot": tot, "dat": dat, "da_yeu_cau": da_yc,
        "con_gui_kho": max(0.0, min(dat, tot) - da_yc),
    }


def danh_sach_lenh_kcs(
    db: Session, user, *, tim: str | None = None, trang: int = 1, gom_da_dong: bool = False
) -> dict:
    """Danh sách lệnh cho màn KCS — phân trang + tìm ở máy chủ."""
    gate_kcs(db, user)
    repo = SanXuatKcsRepository(db)
    trang = max(1, int(trang or 1))
    ids, tong = repo.trang_lenh(
        tim=tim, gom_da_dong=gom_da_dong, offset=(trang - 1) * _CO_TRANG, limit=_CO_TRANG
    )
    bc = boi_canh.nap(db, ids)
    items = []
    for lid in ids:
        lenh = bc.lenh.get(lid)
        if lenh is None:
            continue
        cvs = bc.cong_viec_du(lid)
        don = bc.don.get(lenh.order_id)
        khach = bc.khach.get(don.customer_id) if don and don.customer_id else None
        nhom = next((bc.nhom[cv.nhom_id] for cv in cvs if cv.nhom_id in bc.nhom), None)
        items.append({
            "lsx_id": lid,
            "ma": lenh.ma,
            "ten": lenh.ten,
            "khach": khach.name if khach else None,
            "nhom_ma": nhom.ma if nhom else None,
            "nhom_trang_thai": nhom.trang_thai if nhom else None,
            "so_cong_doan": len(cvs),
            "so_da_kiem": sum(1 for cv in cvs if bc.kcs[cv.id]),
            "so_loi": sum(float(k.so_luong_khong_dat or 0) for cv in cvs for k in bc.kcs[cv.id]),
            "cuoi": _tom_cuoi(bc, cvs),
        })
    return {"items": items, "tong": tong, "trang": trang, "co_trang": _CO_TRANG}


def chuoi_cong_doan_kcs(db: Session, user, lsx_id: int) -> dict:
    """Chuỗi công đoạn của MỘT lệnh theo thứ tự routing, kèm tổng tốt/hỏng tổ đã ghi và các lần
    kiểm — màn KCS bấm vào một công đoạn để kiểm."""
    gate_kcs(db, user)
    repo = SanXuatKcsRepository(db)
    bc = boi_canh.nap(db, [lsx_id])
    lenh = bc.lenh.get(lsx_id)
    if lenh is None:
        raise ValueError("Không tìm thấy lệnh sản xuất.")
    cvs = bc.cong_viec_du(lsx_id)
    cvs.sort(key=_thu_tu_cong_doan(bc, lsx_id, repo.thu_tu_buoc([lsx_id])))
    ten_to = repo.ten_to({cv.department_id for cv in cvs})
    tat_ca_kcs = [k for cv in cvs for k in bc.kcs[cv.id]]
    ra = _lan_kiem_ra(db, repo, tat_ca_kcs)
    don = bc.don.get(lenh.order_id)
    khach = bc.khach.get(don.customer_id) if don and don.customer_id else None
    nhom = next((bc.nhom[cv.nhom_id] for cv in cvs if cv.nhom_id in bc.nhom), None)

    cong_doan = []
    for cv in cvs:
        ds = bc.kcs[cv.id]
        tot = sum(float(b.tot or 0) for b in bc.batch[cv.id])
        dat = sum(float(k.so_luong_dat or 0) for k in ds)
        da_yc = _da_gui_kho(bc, cv)
        cong_doan.append({
            "cong_viec_id": cv.id,
            "ten": cv.ten_cong_doan,
            "phan_doan_so": cv.phan_doan_so,
            "phan_doan_tong": cv.phan_doan_tong,
            "to_id": cv.department_id,
            "to_ten": ten_to.get(cv.department_id or 0, ""),
            "trang_thai": cv.trang_thai,
            "tot": tot,
            "hong": sum(float(b.hong or 0) for b in bc.batch[cv.id]),
            "don_vi": cv.don_vi_ra,
            "la_kcs_cuoi": bool(cv.la_kcs_cuoi),
            "checklist": cv.kcs_tieu_chi_json or [],
            "so_lan_kiem": len(ds),
            "tong_dat": dat,
            "tong_loi": sum(float(k.so_luong_khong_dat or 0) for k in ds),
            "da_yeu_cau_kho": da_yc,
            "con_gui_kho": max(0.0, min(dat, tot) - da_yc) if cv.la_kcs_cuoi else 0.0,
            "yeu_cau_kho": [
                {"request_id": d.request_id, "ma": d.request_ma, "trang_thai": d.trang_thai,
                 "sl_de_nghi": round(d.sl_hieu_luc, 3), "sl_da_nhan": round(d.sl_da_nhan, 3),
                 "don_vi": d.dvt, "tao_luc": thuc_te_hien_thi(d.created_at)}
                for d in _dong_kho_cua(bc, cv)
            ],
            "lan_kiem": [ra[k.id] for k in reversed(ds)],
        })
    return {
        "lsx": {
            "id": lenh.id, "ma": lenh.ma, "ten": lenh.ten,
            "khach": khach.name if khach else None,
            "nhom_id": nhom.id if nhom else None,
            "nhom_ma": nhom.ma if nhom else None,
            "nhom_trang_thai": nhom.trang_thai if nhom else None,
        },
        "cong_doan": cong_doan,
    }


def loi_cho_xem(db: Session, to_ids) -> list[dict]:
    """Lỗi KCS gửi tới các tổ này mà tổ chưa bấm "Đã xem" — dòng "KCS báo lỗi" ở bàn tổ."""
    repo = SanXuatKcsRepository(db)
    rows = repo.loi_chua_xem_nhieu_to(set(to_ids))
    if not rows:
        return []
    batches = repo.kcs_batch_nhieu({l.kcs_batch_id for l in rows})
    cvs = repo.cong_viec_nhieu({b.cong_viec_id for b in batches.values()})
    ten = repo.ten_nguoi({b.created_by for b in batches.values()})
    anh_map = repo.anh_cua_loi_nhieu([l.id for l in rows])
    lsx_ma = repo.ma_lsx_nhieu({cv.lsx_id for cv in cvs.values()})
    out = []
    for l in rows:
        b = batches.get(l.kcs_batch_id)
        cv = cvs.get(b.cong_viec_id) if b else None
        out.append({
            "loi_id": l.id,
            "kcs_batch_id": l.kcs_batch_id,
            "cong_viec_id": cv.id if cv else None,
            "to_id": l.to_chiu_id,
            "ten_cong_doan": cv.ten_cong_doan if cv else "",
            "lsx_ma": lsx_ma.get(cv.lsx_id) if cv else None,
            "mo_ta": l.mo_ta,
            "so_luong": float(l.so_luong or 0),
            "don_vi": l.don_vi,
            "nguoi_kiem": ten.get(b.created_by) if b else None,
            "luc": thuc_te_hien_thi(l.created_at),
            "so_anh": len(anh_map.get(l.id, [])),
            "version": l.version,
        })
    return out
