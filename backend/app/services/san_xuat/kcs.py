"""Thực hiện sản xuất — KCS: batch kiểm tra + lỗi + phản hồi trách nhiệm (Giai đoạn 5, §13).

Điều phối lệnh GHI của KCS. Tuân §18 như các lát trước: kiểm quyền tại service → transaction →
ghi audit → (SSE do router phát sau commit). Truy vấn/ghi DB nằm ở `repositories/san_xuat_kcs_repo`;
ở đây chỉ luật.

Luật cứng:
  · §13.1 `so_luong_nhan = so_luong_dat + so_luong_khong_dat` (dung sai làm tròn). NĂNG SUẤT KCS
    lấy nền theo `so_luong_nhan` (số nhận-và-kết-luận, KHÔNG theo số đạt) — nên khi ghi batch KCS,
    service ĐẺ KÈM một `san_xuat_batch` sản lượng (`tot = so_luong_nhan`, `hong = 0`) để tái dùng
    NGUYÊN pipeline phân bổ (§12). Batch KCS neo về nó qua `batch_id`.
  · §13.2 mỗi lỗi bắt buộc ≥1 ảnh; nhóm lỗi phải thuộc danh mục nhóm `loi`. Tổ trưởng phụ trách
    (tổ `to_chiu_id`) CHẤP NHẬN hoặc TỪ CHỐI-kèm-lý-do — chung thẩm, không phân xử tiếp.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG
from ...models.san_xuat_ly_do import NHOM_LOI
from ...models.san_xuat_kcs import (
    KCS_DAT,
    KCS_DAT_MOT_PHAN,
    KCS_KHONG_DAT,
    KCS_LOAI_DOT_XUAT,
    KCS_LOAI_ROUTING,
    TN_CHAP_NHAN,
    TN_CHO,
    TN_TU_CHOI,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from ...models.san_xuat_kho import YC_CHO_KHO, YC_HUY, YC_MOT_PHAN, SanXuatNhapKhoYc
from ...models.san_xuat_san_luong import SanXuatBatch
from ...models.user import User
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_kho_repo import SanXuatKhoRepository
from .thuc_thi import _aware, _gate, _moc

# Dung sai làm tròn (cột Numeric(18,3)) — như san_luong.
_EPS = 0.0005
# Chỉ ghi KCS cho công việc ĐÃ khởi động (đang chạy / tạm dừng / đã xong).
_TRANG_THAI_GHI_DUOC = (CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)
# KCS kiêm nhiệm đột xuất (mg 0250): CHỈ đang chạy / tạm dừng — KHÔNG gồm HOAN_THANH (mục 10).
_TRANG_THAI_DOT_XUAT = (CV_DANG_CHAY, CV_TAM_DUNG)


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


def _gate_to(db: Session, user, department_id: int | None) -> None:
    """Chỉ tổ trưởng ĐÚNG tổ `department_id` mới được thao tác (dùng cho phản hồi trách nhiệm lỗi:
    người phản hồi là tổ trưởng tổ BỊ yêu cầu, KHÁC tổ KCS ghi lỗi §13.2)."""
    dept = db.get(Department, department_id) if department_id else None
    uid = getattr(user, "id", None)
    if dept is None or dept.head_user_id is None or dept.head_user_id != uid:
        raise PermissionError("Chỉ tổ trưởng của tổ được yêu cầu mới được phản hồi lỗi này.")


def _gate_member(db: Session, user, department_id: int | None) -> None:
    """Chỉ THÀNH VIÊN của tổ `department_id` (không cần là trưởng) mới thao tác được — dùng RIÊNG
    cho kiểm đột xuất KCS kiêm nhiệm: bất kỳ ai trong tổ được giao kiểm cũng ghi được. KHÁC
    `_gate`/`_gate_to` (chỉ tổ trưởng) đang gác routing/phản hồi lỗi — hai gate đó GIỮ NGUYÊN."""
    if department_id is None or getattr(user, "department_id", None) != department_id:
        raise PermissionError("Chỉ thành viên của tổ được giao kiểm đột xuất mới được thao tác.")


def _gate_dieu_chinh(db: Session, user, kcs: SanXuatKcsBatch, cv) -> None:
    """Trưởng tổ KCS mới sửa được kết quả (§4.3) — với routing là tổ đang chạy việc (`cv.department_id`,
    `_gate`), với đột xuất là tổ đi kiểm (`kcs.kcs_department_id`, `_gate_to`) — KHÁC tổ bị kiểm."""
    if kcs.loai == KCS_LOAI_DOT_XUAT:
        _gate_to(db, user, kcs.kcs_department_id)
    else:
        _gate(db, user, cv)


def _validate_so_luong(nhan, dat, khong_dat, co_mau) -> tuple[float, float, float, float | None]:
    """Luật số DÙNG CHUNG cho cả hai luồng batch KCS (mục 9): không âm, nhan>0, nhan=dat+khong_dat,
    cỡ mẫu ≤ nhận. Tách khỏi `tao_batch_kcs` để `tao_kiem_dot_xuat` không LẶP nguyên khối luật."""
    nhan_f = _so_khong_am(nhan, "Số lượng nhận")
    dat_f = _so_khong_am(dat, "Số lượng đạt")
    khong_dat_f = _so_khong_am(khong_dat, "Số lượng không đạt")
    if nhan_f <= 0:
        raise ValueError("Số lượng nhận phải lớn hơn 0.")
    if abs(nhan_f - (dat_f + khong_dat_f)) > _EPS:
        raise ValueError("Số lượng nhận phải bằng Đạt + Không đạt.")
    co_mau_f = None
    if co_mau is not None and str(co_mau) != "":
        co_mau_f = _so_khong_am(co_mau, "Cỡ mẫu")
        if co_mau_f > nhan_f + _EPS:
            raise ValueError("Cỡ mẫu không được vượt số lượng nhận.")
    return nhan_f, dat_f, khong_dat_f, co_mau_f


def _validate_checklist_bat_buoc(cv, checklist_ket_qua: list[dict] | None) -> list[dict] | None:
    """Mọi tiêu chí `bat_buoc=True` trong snapshot `cv.kcs_tieu_chi_json` phải có MỘT kết quả gửi
    kèm — khớp theo `thu_tu` (khoá ổn định kể cả mục bổ sung không có `tieu_chi_id`). Không có
    checklist (None/rỗng, hoặc bước không phải KCS) ⇒ không có gì bắt buộc, no-op. Dùng CHUNG cho
    routing lẫn đột xuất (mục 7) — batch cũ trước module này gọi hàm với `checklist_ket_qua=None`
    và KHÔNG có `kcs_tieu_chi_json` nên luôn no-op, không phá test cũ."""
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


def _ket_luan(dat: float, khong_dat: float) -> str:
    if khong_dat <= _EPS:
        return KCS_DAT
    if dat <= _EPS:
        return KCS_KHONG_DAT
    return KCS_DAT_MOT_PHAN


def _kq_batch(cv, kcs: SanXuatKcsBatch) -> dict:
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "nhom_id": kcs.nhom_id,
        "kcs_batch_id": kcs.id,
        "batch_id": kcs.batch_id,
        "version": kcs.version,
    }


# --- Batch kiểm tra (§13.1) -----------------------------------------------------------------
def tao_batch_kcs(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    bat_dau: datetime,
    ket_thuc: datetime,
    so_luong_nhan,
    so_luong_dat,
    so_luong_khong_dat=0,
    co_mau=None,
    don_vi: str | None = None,
    ghi_chu: str | None = None,
    checklist_ket_qua: list[dict] | None = None,
) -> dict:
    """Ghi MỘT batch kiểm tra KCS (§13.1) + đẻ kèm batch sản lượng nền cho phân bổ năng suất KCS.

    Chỉ cho công việc KCS (`la_kcs`) đã khởi động. Ràng buộc số: `so_luong_nhan = dat + khong_dat`.
    Kết luận suy từ số (đạt / đạt một phần / không đạt)."""
    repo = SanXuatKcsRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate(db, user, cv)
    if not cv.la_kcs:
        raise ValueError("Chỉ công việc KCS mới ghi được batch kiểm tra.")
    if cv.trang_thai not in _TRANG_THAI_GHI_DUOC:
        raise ValueError("Chỉ ghi kiểm tra cho công việc KCS đã bắt đầu.")

    nhan, dat, khong_dat, co_mau_f = _validate_so_luong(
        so_luong_nhan, so_luong_dat, so_luong_khong_dat, co_mau
    )

    if bat_dau is None or ket_thuc is None:
        raise ValueError("Batch kiểm tra phải có khoảng thời gian bắt đầu và kết thúc.")
    if _aware(ket_thuc) < _aware(bat_dau):
        raise ValueError("Kết thúc kiểm tra không được trước khi bắt đầu.")

    don_vi_kcs = (don_vi or cv.don_vi_ra or "").strip()
    if not don_vi_kcs:
        raise ValueError("Batch kiểm tra chưa có đơn vị.")

    checklist_ket_qua = _validate_checklist_bat_buoc(cv, checklist_ket_qua)

    # Chặn TỔNG các đợt vượt số đã bàn giao xác nhận (mục 2-4). Chỉ áp khi công việc này CÓ ít
    # nhất một dòng bàn giao — công việc chưa nối bàn giao (vd fixture test cũ, hoặc KCS nhận thẳng
    # từ kho không qua bàn giao nội bộ) thì chưa có gì để chặn theo, giữ nguyên hành vi cũ.
    da_ban_giao = repo.tong_ban_giao_xac_nhan(cv.id)
    if da_ban_giao > _EPS:
        da_ghi_truoc = repo.tong_kcs_routing_da_ghi(cv.id)
        if da_ghi_truoc + nhan > da_ban_giao + _EPS:
            raise ValueError(
                f"Tổng số đã kiểm ({da_ghi_truoc + nhan:.3f}) vượt số đã bàn giao xác nhận "
                f"({da_ban_giao:.3f})."
            )

    # Batch sản lượng nền: tot = so_luong_nhan (nền năng suất KCS §13.1), hong = 0 (số không đạt là
    # LỖI SẢN PHẨM ghi ở lỗi KCS, KHÔNG phải hỏng do KCS). Pipeline phân bổ đọc batch.tot → chia đúng.
    batch = SanXuatBatch(
        cong_viec_id=cv.id,
        bat_dau=_aware(bat_dau),
        ket_thuc=_aware(ket_thuc),
        tong=nhan,
        tot=nhan,
        hong=0,
        don_vi=don_vi_kcs,
        ghi_chu="KCS",
        created_by=getattr(user, "id", None),
    )
    repo.add(batch)
    repo.flush()  # cần batch.id để neo

    kcs = SanXuatKcsBatch(
        cong_viec_id=cv.id,
        batch_id=batch.id,
        nhom_id=cv.nhom_id,
        bat_dau=_aware(bat_dau),
        ket_thuc=_aware(ket_thuc),
        so_luong_nhan=nhan,
        co_mau=co_mau_f,
        so_luong_dat=dat,
        so_luong_khong_dat=khong_dat,
        don_vi=don_vi_kcs,
        ket_luan=_ket_luan(dat, khong_dat),
        ghi_chu=(ghi_chu or "").strip() or None,
        checklist_json=checklist_ket_qua,
        created_by=getattr(user, "id", None),
    )
    repo.add(kcs)
    repo.flush()

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_tao_batch",
        target=f"san_xuat_kcs_batch:{kcs.id}",
        detail=f"cong_viec={cv.id} nhan={nhan} dat={dat} khong_dat={khong_dat}",
    )
    db.commit()
    return _kq_batch(cv, kcs)


def tao_kiem_dot_xuat(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    kcs_department_id: int,
    bat_dau: datetime,
    ket_thuc: datetime,
    so_luong_nhan,
    so_luong_dat,
    so_luong_khong_dat=0,
    co_mau=None,
    don_vi: str | None = None,
    ghi_chu: str | None = None,
    checklist_ket_qua: list[dict] | None = None,
    nhom_loi_id: int | None = None,
    loi_mo_ta: str | None = None,
    to_chiu_id: int | None = None,
    cong_doan_ref_id: int | None = None,
    anh: list[dict] | None = None,
) -> dict:
    """KCS KIÊM NHIỆM (mg 0250) — một tổ SX KHÁC kiểm ĐỘT XUẤT một công việc đang chạy/tạm dừng,
    KHÔNG đứng sẵn trong routing (khác `tao_batch_kcs` — cách cũ, cố định trong routing/bài ghép).

    Khác routing ở BA điểm CỐ Ý:
      · không đòi `la_kcs`/"đã bắt đầu" kiểu routing — chỉ đòi running/tạm dừng (mục 5, 10).
      · KHÔNG đẻ kèm `san_xuat_batch` sản lượng, KHÔNG đụng `trang_thai`/kho (mục 6, 11) — đây là
        bản ghi CHẤT LƯỢNG thuần, không phải nền năng suất/tồn kho.
      · `so_luong_khong_dat > 0` bắt buộc ghi lỗi (nhóm lỗi + ≥1 ảnh) NGAY trong CÙNG lệnh gọi —
        routing tách hai bước (`tao_batch_kcs` rồi `ghi_loi` riêng); đột xuất gộp một (mục 8)."""
    repo = SanXuatKcsRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_member(db, user, kcs_department_id)
    if cv.trang_thai not in _TRANG_THAI_DOT_XUAT:
        raise ValueError("Chỉ kiểm đột xuất cho công việc đang chạy hoặc tạm dừng.")

    nhan, dat, khong_dat, co_mau_f = _validate_so_luong(
        so_luong_nhan, so_luong_dat, so_luong_khong_dat, co_mau
    )
    if bat_dau is None or ket_thuc is None:
        raise ValueError("Batch kiểm tra phải có khoảng thời gian bắt đầu và kết thúc.")
    if _aware(ket_thuc) < _aware(bat_dau):
        raise ValueError("Kết thúc kiểm tra không được trước khi bắt đầu.")
    don_vi_kcs = (don_vi or cv.don_vi_ra or "").strip()
    if not don_vi_kcs:
        raise ValueError("Batch kiểm tra chưa có đơn vị.")
    checklist_ket_qua = _validate_checklist_bat_buoc(cv, checklist_ket_qua)

    if khong_dat > _EPS:
        if not nhom_loi_id:
            raise ValueError("Không đạt lớn hơn 0 bắt buộc chọn nhóm lỗi.")
        if not anh:
            raise ValueError("Không đạt lớn hơn 0 bắt buộc kèm ít nhất một ảnh bằng chứng.")
        ld = repo.ly_do(int(nhom_loi_id))
        if ld is None or ld.nhom != NHOM_LOI:
            raise ValueError("Nhóm lỗi không hợp lệ (phải là một lỗi trong danh mục).")
        if to_chiu_id and db.get(Department, int(to_chiu_id)) is None:
            raise ValueError("Không tìm thấy tổ bị yêu cầu nhận trách nhiệm.")
        if cong_doan_ref_id and repo.cong_viec(int(cong_doan_ref_id)) is None:
            raise ValueError("Không tìm thấy công đoạn liên đới.")

    # KHÔNG đẻ san_xuat_batch, KHÔNG đụng cv.trang_thai/kho (mục 6, 11) — batch_id giữ NULL.
    kcs = SanXuatKcsBatch(
        cong_viec_id=cv.id,
        batch_id=None,
        nhom_id=cv.nhom_id,
        bat_dau=_aware(bat_dau),
        ket_thuc=_aware(ket_thuc),
        so_luong_nhan=nhan,
        co_mau=co_mau_f,
        so_luong_dat=dat,
        so_luong_khong_dat=khong_dat,
        don_vi=don_vi_kcs,
        ket_luan=_ket_luan(dat, khong_dat),
        ghi_chu=(ghi_chu or "").strip() or None,
        loai=KCS_LOAI_DOT_XUAT,
        kcs_department_id=int(kcs_department_id),
        checklist_json=checklist_ket_qua,
        created_by=getattr(user, "id", None),
    )
    repo.add(kcs)
    repo.flush()

    loi_id = None
    if khong_dat > _EPS:
        cac_anh = [_chuan_hoa_anh(r, getattr(user, "id", None)) for r in (anh or [])]
        loi = SanXuatKcsLoi(
            kcs_batch_id=kcs.id,
            nhom_loi_id=int(nhom_loi_id),
            mo_ta=(loi_mo_ta or "").strip() or None,
            to_chiu_id=int(to_chiu_id) if to_chiu_id else None,
            cong_doan_ref_id=int(cong_doan_ref_id) if cong_doan_ref_id else None,
            so_luong=khong_dat,
            don_vi=don_vi_kcs,
            trang_thai=TN_CHO,
            created_by=getattr(user, "id", None),
        )
        repo.add(loi)
        repo.flush()
        for a in cac_anh:
            a.loi_id = loi.id
            repo.add(a)
        loi_id = loi.id

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_dot_xuat",
        target=f"san_xuat_kcs_batch:{kcs.id}",
        detail=(
            f"cong_viec={cv.id} kcs_to={kcs_department_id} nhan={nhan} dat={dat} "
            f"khong_dat={khong_dat}"
        ),
    )
    db.commit()
    res = _kq_batch(cv, kcs)
    res["loi_id"] = loi_id
    return res


def _con_yeu_cau_kho_chan(db: Session, kcs_batch_id: int) -> bool:
    """Còn dòng `SanXuatNhapKhoYc` nào KHÁC `YC_HUY` của batch này (§4.3): gộp CẢ HAI điều kiện chặn
    (đã xác nhận dù một phần / chưa nhận nhưng chưa huỷ) về MỘT check — `YC_CHO_KHO`/`YC_MOT_PHAN`/
    `YC_DA_NHAP` đều chặn, chỉ `YC_HUY` (huỷ khi CHƯA nhận gì) mở khoá."""
    rows = SanXuatKhoRepository(db).cac_yc_cua_batch(kcs_batch_id)
    return any(r.trang_thai != YC_HUY for r in rows)


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
    """Điều chỉnh kết quả một batch KCS đã ghi (§4.3, §5.5) — KHÔNG xoá, sửa tại chỗ + audit
    trước/sau + kiểm `expected_version`. Số NHẬN giữ NGUYÊN — chỉ đổi cách phân loại đạt/không đạt
    trong CÙNG số đã kiểm. Chặn TUYỆT ĐỐI nếu kho đã đụng vào (xác nhận dù một phần) hoặc còn yêu
    cầu chưa hủy — sửa sai phải hủy yêu cầu chưa nhận trước (§4.3 trình tự sửa sai bước 1), hàm này
    KHÔNG tự hủy giúp."""
    repo = SanXuatKcsRepository(db)
    kcs = repo.kcs_batch(kcs_batch_id)
    if kcs is None:
        raise ValueError("Không tìm thấy batch kiểm tra.")
    cv = repo.cong_viec(kcs.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch kiểm tra.")

    _gate_dieu_chinh(db, user, kcs, cv)

    if expected_version != kcs.version:
        raise ValueError("Phiên bản không khớp — kết quả vừa được cập nhật, hãy tải lại.")

    if _con_yeu_cau_kho_chan(db, kcs.id):
        raise ValueError(
            "Không thể điều chỉnh: còn yêu cầu nhập kho chưa hủy hoặc đã được kho xác nhận (dù một "
            "phần). Hủy phần chưa nhận rồi điều chỉnh, sau đó tạo lại yêu cầu nếu cần."
        )

    dat_f = _so_khong_am(so_luong_dat, "Số lượng đạt")
    khong_dat_f = _so_khong_am(so_luong_khong_dat, "Số lượng không đạt")
    nhan = float(kcs.so_luong_nhan)
    if abs(nhan - (dat_f + khong_dat_f)) > _EPS:
        raise ValueError(
            "Đạt + Không đạt phải bằng đúng số đã nhận — điều chỉnh không đổi số nhận."
        )
    checklist_ket_qua = _validate_checklist_bat_buoc(cv, checklist_ket_qua)

    truoc_dat, truoc_khong_dat, truoc_ket_luan = (
        float(kcs.so_luong_dat), float(kcs.so_luong_khong_dat), kcs.ket_luan
    )
    kcs.so_luong_dat = dat_f
    kcs.so_luong_khong_dat = khong_dat_f
    kcs.ket_luan = _ket_luan(dat_f, khong_dat_f)
    if checklist_ket_qua is not None:
        kcs.checklist_json = checklist_ket_qua
    if ghi_chu is not None:
        kcs.ghi_chu = ghi_chu.strip() or None
    kcs.version += 1

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_dieu_chinh",
        target=f"san_xuat_kcs_batch:{kcs.id}",
        detail=(
            f"truoc(dat={truoc_dat}, khong_dat={truoc_khong_dat}, ket_luan={truoc_ket_luan}) "
            f"sau(dat={dat_f}, khong_dat={khong_dat_f}, ket_luan={kcs.ket_luan})"
        ),
    )
    db.commit()
    return {
        "kcs_batch_id": kcs.id, "cong_viec_id": cv.id, "so_luong_nhan": nhan,
        "so_luong_dat": dat_f, "so_luong_khong_dat": khong_dat_f, "ket_luan": kcs.ket_luan,
        "version": kcs.version,
    }


# --- Lỗi + ảnh (§13.2) ----------------------------------------------------------------------
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


def ghi_loi(
    db: Session,
    *,
    user,
    kcs_batch_id: int,
    nhom_loi_id: int | None,
    mo_ta: str | None = None,
    to_chiu_id: int | None = None,
    cong_doan_ref_id: int | None = None,
    so_luong=0,
    don_vi: str | None = None,
    anh: list[dict] | None = None,
) -> dict:
    """Ghi MỘT lỗi phát hiện trong batch KCS (§13.2) + ≥1 ảnh bằng chứng (bắt buộc).

    Người ghi = tổ trưởng tổ KCS (gate theo công việc KCS). `nhom_loi_id` phải là lý do nhóm `loi`.
    `to_chiu_id` (tổ bị yêu cầu nhận trách nhiệm) mặc định `pending` chờ tổ đó phản hồi."""
    repo = SanXuatKcsRepository(db)
    kcs = repo.kcs_batch(kcs_batch_id)
    if kcs is None:
        raise ValueError("Không tìm thấy batch kiểm tra.")
    cv = repo.cong_viec(kcs.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch kiểm tra.")
    _gate(db, user, cv)

    anh = anh or []
    if not anh:
        raise ValueError("Mỗi lỗi phải kèm ít nhất một ảnh bằng chứng.")

    if not nhom_loi_id:
        raise ValueError("Phải chọn nhóm lỗi.")
    ld = repo.ly_do(int(nhom_loi_id))
    if ld is None or ld.nhom != NHOM_LOI:
        raise ValueError("Nhóm lỗi không hợp lệ (phải là một lỗi trong danh mục).")

    to_chiu = None
    if to_chiu_id:
        to_chiu = db.get(Department, int(to_chiu_id))
        if to_chiu is None:
            raise ValueError("Không tìm thấy tổ bị yêu cầu nhận trách nhiệm.")

    cd_ref = None
    if cong_doan_ref_id:
        cd_ref = repo.cong_viec(int(cong_doan_ref_id))
        if cd_ref is None:
            raise ValueError("Không tìm thấy công đoạn liên đới.")

    so_luong_f = _so_khong_am(so_luong, "Số lượng lỗi")
    cac_anh = [_chuan_hoa_anh(r, getattr(user, "id", None)) for r in anh]

    loi = SanXuatKcsLoi(
        kcs_batch_id=kcs.id,
        nhom_loi_id=int(nhom_loi_id),
        mo_ta=(mo_ta or "").strip() or None,
        to_chiu_id=int(to_chiu_id) if to_chiu_id else None,
        cong_doan_ref_id=int(cong_doan_ref_id) if cong_doan_ref_id else None,
        so_luong=so_luong_f,
        don_vi=(don_vi or kcs.don_vi or "").strip() or None,
        trang_thai=TN_CHO,
        created_by=getattr(user, "id", None),
    )
    repo.add(loi)
    repo.flush()  # cần loi.id để neo ảnh
    for a in cac_anh:
        a.loi_id = loi.id
        repo.add(a)

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_ghi_loi",
        target=f"san_xuat_kcs_loi:{loi.id}",
        detail=f"kcs_batch={kcs.id} nhom_loi={nhom_loi_id} to_chiu={to_chiu_id or '-'}",
    )
    db.commit()
    return {
        "loi_id": loi.id,
        "kcs_batch_id": kcs.id,
        "cong_viec_id": cv.id,
        "to_chiu_id": loi.to_chiu_id,
        "to_chiu_head_user_id": to_chiu.head_user_id if to_chiu else None,
        "trang_thai": loi.trang_thai,
        "version": loi.version,
    }


def them_anh_loi(db: Session, *, user, loi_id: int, anh: list[dict]) -> dict:
    """Bổ sung ảnh bằng chứng cho một lỗi đã ghi (§13.2)."""
    repo = SanXuatKcsRepository(db)
    loi = repo.loi(loi_id)
    if loi is None:
        raise ValueError("Không tìm thấy lỗi.")
    kcs = repo.kcs_batch(loi.kcs_batch_id)
    cv = repo.cong_viec(kcs.cong_viec_id) if kcs else None
    if cv is None:
        raise ValueError("Không tìm thấy công việc của lỗi.")
    _gate(db, user, cv)
    if not anh:
        raise ValueError("Chưa có ảnh để thêm.")
    for r in anh:
        a = _chuan_hoa_anh(r, getattr(user, "id", None))
        a.loi_id = loi.id
        repo.add(a)
    db.commit()
    return {"loi_id": loi.id, "so_anh": repo.dem_anh(loi.id)}


def xoa_anh_loi(db: Session, *, user, anh_id: int) -> dict:
    """Xoá MỘT ảnh bằng chứng — nhưng GIỮ ≥1 ảnh/lỗi (§13.2). Trả `file_url` để router xoá storage."""
    repo = SanXuatKcsRepository(db)
    a = repo.anh(anh_id)
    if a is None:
        raise ValueError("Không tìm thấy ảnh.")
    loi = repo.loi(a.loi_id)
    kcs = repo.kcs_batch(loi.kcs_batch_id) if loi else None
    cv = repo.cong_viec(kcs.cong_viec_id) if kcs else None
    if cv is None:
        raise ValueError("Không tìm thấy công việc của ảnh.")
    _gate(db, user, cv)
    if repo.dem_anh(a.loi_id) <= 1:
        raise ValueError("Mỗi lỗi phải giữ ít nhất một ảnh bằng chứng — không thể xoá ảnh cuối.")
    file_url = a.file_url
    repo.delete(a)
    db.commit()
    return {"loi_id": loi.id, "file_url": file_url}


def phan_hoi_loi(
    db: Session,
    *,
    user,
    loi_id: int,
    chap_nhan: bool,
    ly_do_tu_choi: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Tổ trưởng tổ BỊ yêu cầu CHẤP NHẬN hoặc TỪ CHỐI trách nhiệm lỗi (§13.2). Chung thẩm — chỉ
    trả lời khi còn `pending`. Từ chối bắt buộc lý do; chấp nhận thì tính vào chất lượng tổ."""
    repo = SanXuatKcsRepository(db)
    loi = repo.loi(loi_id)
    if loi is None:
        raise ValueError("Không tìm thấy lỗi.")
    if loi.trang_thai != TN_CHO:
        raise ValueError("Lỗi này đã được phản hồi — quyết định là chung thẩm.")
    if not loi.to_chiu_id:
        raise ValueError("Lỗi chưa gán tổ nhận trách nhiệm nên không thể phản hồi.")
    _gate_to(db, user, loi.to_chiu_id)
    if expected_version is not None and expected_version != loi.version:
        raise ValueError("Phiên bản không khớp — lỗi vừa được cập nhật, hãy tải lại.")

    if not chap_nhan and not (ly_do_tu_choi or "").strip():
        raise ValueError("Từ chối trách nhiệm bắt buộc nêu lý do.")

    loi.trang_thai = TN_CHAP_NHAN if chap_nhan else TN_TU_CHOI
    loi.ly_do_tu_choi = None if chap_nhan else ly_do_tu_choi.strip()
    loi.phan_hoi_by_id = getattr(user, "id", None)
    loi.phan_hoi_luc = _moc()
    loi.version += 1

    kcs = repo.kcs_batch(loi.kcs_batch_id)
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kcs_phan_hoi_loi",
        target=f"san_xuat_kcs_loi:{loi.id}",
        detail=f"{'chap_nhan' if chap_nhan else 'tu_choi'} to={loi.to_chiu_id}",
    )
    db.commit()
    return {
        "loi_id": loi.id,
        "trang_thai": loi.trang_thai,
        "kcs_batch_id": loi.kcs_batch_id,
        "cong_viec_id": kcs.cong_viec_id if kcs else None,
        "nguoi_ghi_id": loi.created_by,
        "version": loi.version,
    }


# --- Đọc ------------------------------------------------------------------------------------
def _anh_ra(a: SanXuatKcsLoiAnh) -> dict:
    return {"id": a.id, "file_name": a.file_name, "file_url": a.file_url, "file_type": a.file_type}


def _loi_ra(loi: SanXuatKcsLoi, anh: list[SanXuatKcsLoiAnh], ten_loi: str | None) -> dict:
    return {
        "id": loi.id,
        "kcs_batch_id": loi.kcs_batch_id,
        "nhom_loi_id": loi.nhom_loi_id,
        "nhom_loi_ten": ten_loi,
        "mo_ta": loi.mo_ta,
        "to_chiu_id": loi.to_chiu_id,
        "cong_doan_ref_id": loi.cong_doan_ref_id,
        "so_luong": float(loi.so_luong or 0),
        "don_vi": loi.don_vi,
        "trang_thai": loi.trang_thai,
        "ly_do_tu_choi": loi.ly_do_tu_choi,
        "phan_hoi_luc": loi.phan_hoi_luc,
        "version": loi.version,
        "anh": [_anh_ra(a) for a in anh],
    }


def _trang_thai_gui_kho(loai: str, requests: list[SanXuatNhapKhoYc]) -> str:
    """Suy trạng thái gửi kho của MỘT batch từ các yêu cầu nhập kho neo vào nó (§14.1, §6.2). Batch
    `dot_xuat` không bao giờ gửi được (`kho.py:212` chặn) → luôn "khong_ap_dung"."""
    if loai != KCS_LOAI_ROUTING:
        return "khong_ap_dung"
    active = [r for r in requests if r.trang_thai != YC_HUY]
    if not active:
        return "chua_gui"
    if any(r.trang_thai in (YC_CHO_KHO, YC_MOT_PHAN) for r in active):
        return "dang_cho"
    return "da_nhap"


def chi_tiet_kcs(db: Session, user, cong_viec_id: int) -> dict:
    """Danh sách batch kiểm tra + lỗi + ảnh của MỘT công việc KCS (mặt đọc cho panel drawer §13)."""
    repo = SanXuatKcsRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate(db, user, cv)

    batches = repo.cac_kcs_batch(cong_viec_id)
    batch_ids = [b.id for b in batches]
    loi_map = repo.cac_loi_nhieu(batch_ids)
    all_loi = [l for ls in loi_map.values() for l in ls]
    anh_map = repo.anh_cua_loi_nhieu([l.id for l in all_loi])
    ten_loi = repo.nhan_ly_do({l.nhom_loi_id for l in all_loi})

    kho_repo = SanXuatKhoRepository(db)
    yc_map = kho_repo.cac_yc_cua_nhieu_batch(batch_ids)
    nguoi_ids = {b.created_by for b in batches if b.created_by}
    nguoi_ten = (
        {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(nguoi_ids)))}
        if nguoi_ids else {}
    )

    out = []
    for b in batches:
        loi_list = loi_map.get(b.id, [])
        out.append({
            "id": b.id,
            "batch_id": b.batch_id,
            "nhom_id": b.nhom_id,
            "bat_dau": b.bat_dau,
            "ket_thuc": b.ket_thuc,
            "so_luong_nhan": float(b.so_luong_nhan or 0),
            "co_mau": float(b.co_mau) if b.co_mau is not None else None,
            "so_luong_dat": float(b.so_luong_dat or 0),
            "so_luong_khong_dat": float(b.so_luong_khong_dat or 0),
            "don_vi": b.don_vi,
            "ket_luan": b.ket_luan,
            "ghi_chu": b.ghi_chu,
            "version": b.version,
            "loi": [_loi_ra(l, anh_map.get(l.id, []), ten_loi.get(l.nhom_loi_id)) for l in loi_list],
            "loai": b.loai,
            "nguoi_ghi": nguoi_ten.get(b.created_by),
            "trang_thai_gui_kho": _trang_thai_gui_kho(b.loai, yc_map.get(b.id, [])),
        })
    return {
        "cong_viec_id": cong_viec_id,
        "la_kcs": cv.la_kcs,
        "checklist": cv.kcs_tieu_chi_json or [],
        "da_ban_giao_xac_nhan": repo.tong_ban_giao_xac_nhan(cong_viec_id),
        "batch": out,
    }


def hop_thu_loi(db: Session, user) -> list[dict]:
    """Hộp thư lỗi CHỜ phản hồi gửi tới các tổ mà `user` làm tổ trưởng (§13.2). Người dùng có thể
    làm tổ trưởng nhiều tổ → gộp lỗi của mọi tổ đó."""
    uid = getattr(user, "id", None)
    if uid is None:
        return []
    to_ids = [
        d.id for d in db.query(Department).filter(Department.head_user_id == uid).all()
    ]
    if not to_ids:
        return []
    repo = SanXuatKcsRepository(db)
    rows: list[SanXuatKcsLoi] = []
    for tid in to_ids:
        rows.extend(repo.loi_cho_to(tid))
    anh_map = repo.anh_cua_loi_nhieu([l.id for l in rows])
    ten_loi = repo.nhan_ly_do({l.nhom_loi_id for l in rows})
    return [_loi_ra(l, anh_map.get(l.id, []), ten_loi.get(l.nhom_loi_id)) for l in rows]
