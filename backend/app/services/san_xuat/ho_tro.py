"""Thực hiện sản xuất — HỖ TRỢ CHÉO giữa hai tổ (Giai đoạn 4, §9).

Điều phối THỎA THUẬN hỗ trợ: đề xuất → hai tổ trưởng xác nhận → áp vào phân bổ. Tuân §18: kiểm
quyền tại service → transaction → version chống bấm trùng → ghi audit → (SSE do router phát sau
commit). Truy vấn/ghi DB ở `repositories/san_xuat_phan_bo_repo.py`.

LUẬT (§9.1–§9.2):
  - Tỷ lệ do người NHẬP theo từng thỏa thuận (7%, 12,5%…) — KHÔNG hard-code / mặc định / giới hạn 7%.
  - Tổng tỷ lệ ĐÃ XÁC NHẬN trong cùng phạm vi (cùng công đoạn + cùng ngày) không vượt 100%.
  - Phải đủ xác nhận của HAI tổ trưởng (tổ gốc của người hỗ trợ + tổ đang thực hiện công đoạn).
  - Phần hỗ trợ thuộc NGÀY LÀM VIỆC thỏa thuận, ghi cho TỔ GỐC; engine phân bổ trừ trước phần này
    rồi mới chia phần còn lại cho tổ thực hiện (xử ở `phan_bo.py`).
  - Lịch chưa chạy bị phát hành lại ⇒ huỷ thỏa thuận, buộc xác nhận lại (`huy_ho_tro_phat_hanh_lai`).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.employee import Employee
from ...models.san_xuat_phan_bo import (
    HT_CHO_HAI_BEN,
    HT_HUY,
    HT_XAC_NHAN,
    SanXuatHoTro,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from .thuc_thi import _moc

_EPS = 0.0005  # dung sai làm tròn cho trần tổng tỷ lệ (Numeric(7,4))


# --- Trợ giúp ------------------------------------------------------------------------------
def _lay_cong_viec(repo: SanXuatPhanBoRepository, cong_viec_id: int):
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    return cv


def _head(db: Session, dept_id: int | None) -> int | None:
    dept = db.get(Department, dept_id) if dept_id else None
    return dept.head_user_id if dept else None


def _la_to_truong_mot_ben(db: Session, user, ht: SanXuatHoTro) -> bool:
    """User là tổ trưởng của MỘT trong hai bên (gốc / thực hiện)?"""
    uid = getattr(user, "id", None)
    if uid is None:
        return False
    return uid in {_head(db, ht.to_goc_id), _head(db, ht.to_thuc_hien_id)}


def _ket_qua(ht: SanXuatHoTro, db: Session) -> dict:
    """Dữ liệu router cần để phát SSE — đẩy tới CẢ HAI tổ trưởng liên quan."""
    notify = {
        u
        for u in (_head(db, ht.to_goc_id), _head(db, ht.to_thuc_hien_id))
        if u is not None
    }
    return {
        "ho_tro_id": ht.id,
        "cong_viec_id": ht.cong_viec_id,
        "to_goc_id": ht.to_goc_id,
        "to_thuc_hien_id": ht.to_thuc_hien_id,
        "trang_thai": ht.trang_thai,
        "notify_user_ids": sorted(notify),
    }


def _audit(db: Session, user, action: str, ht: SanXuatHoTro, detail: str = "") -> None:
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action=action,
        target=f"san_xuat_ho_tro:{ht.id}",
        detail=detail,
    )


def _tong_ty_le_da_xac_nhan(
    repo: SanXuatPhanBoRepository, cong_viec_id: int, ngay: date, tru_id: int | None = None
) -> float:
    """Tổng % đã xác nhận trong phạm vi (công đoạn + ngày), bỏ qua thỏa thuận `tru_id`."""
    return sum(
        float(h.ty_le_phan_tram or 0)
        for h in repo.ho_tro_xac_nhan_trong_pham_vi(cong_viec_id, ngay)
        if h.id != tru_id
    )


# --- Lệnh -----------------------------------------------------------------------------------
def de_xuat_ho_tro(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    employee_id: int,
    ngay_lam_viec: date,
    ty_le_phan_tram: float,
    mo_ta: str | None = None,
) -> dict:
    """Đề xuất một thỏa thuận hỗ trợ. Tổ trưởng của tổ gốc HOẶC tổ thực hiện đều được đề xuất; bên
    kia xác nhận sau. Snapshot tổ thực hiện = tổ của công đoạn; tổ gốc = tổ của người hỗ trợ."""
    repo = SanXuatPhanBoRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)

    emp = db.get(Employee, employee_id)
    if emp is None:
        raise ValueError("Không tìm thấy người hỗ trợ.")
    to_goc_id = emp.department_id
    to_thuc_hien_id = cv.department_id
    if to_goc_id and to_thuc_hien_id and to_goc_id == to_thuc_hien_id:
        raise ValueError("Người hỗ trợ đã thuộc tổ thực hiện — không cần thỏa thuận hỗ trợ chéo.")

    uid = getattr(user, "id", None)
    if uid is None or uid not in {_head(db, to_goc_id), _head(db, to_thuc_hien_id)}:
        raise PermissionError("Chỉ tổ trưởng tổ gốc hoặc tổ thực hiện mới được đề xuất hỗ trợ.")

    ty_le = float(ty_le_phan_tram or 0)
    if ty_le <= 0 or ty_le > 100:
        raise ValueError("Tỷ lệ hỗ trợ phải trong khoảng lớn hơn 0 và không quá 100%.")

    ht = SanXuatHoTro(
        cong_viec_id=cong_viec_id,
        employee_id=employee_id,
        to_goc_id=to_goc_id,
        to_thuc_hien_id=to_thuc_hien_id,
        ngay_lam_viec=ngay_lam_viec,
        ty_le_phan_tram=ty_le,
        trang_thai=HT_CHO_HAI_BEN,
        mo_ta=(mo_ta or None),
        de_xuat_by_id=uid,
    )
    # Người đề xuất tính là ĐÃ xác nhận cho bên của mình (khỏi bắt bấm hai lần).
    moc = _moc()
    if uid == _head(db, to_goc_id):
        ht.xac_nhan_goc_by_id = uid
        ht.xac_nhan_goc_luc = moc
    if uid == _head(db, to_thuc_hien_id):
        ht.xac_nhan_thuc_hien_by_id = uid
        ht.xac_nhan_thuc_hien_luc = moc
    _cap_nhat_trang_thai(ht)
    if ht.trang_thai == HT_XAC_NHAN:
        _kiem_tran(repo, cong_viec_id, ngay_lam_viec, ty_le, tru_id=None)

    repo.add(ht)
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.de_xuat", ht,
           detail=f"nv={employee_id} ty_le={ty_le:g}% ngay={ngay_lam_viec}")
    db.commit()
    return _ket_qua(ht, db)


def xac_nhan_ho_tro(
    db: Session, *, user, ho_tro_id: int, expected_version: int | None = None
) -> dict:
    """Xác nhận thỏa thuận cho BÊN của người bấm (tự nhận diện gốc/thực hiện qua head_user_id). Đủ
    hai bên → `confirmed`, và lúc đó mới kiểm trần tổng tỷ lệ ≤ 100% cho phạm vi."""
    repo = SanXuatPhanBoRepository(db)
    ht = repo.ho_tro(ho_tro_id)
    if ht is None:
        raise ValueError("Không tìm thấy thỏa thuận hỗ trợ.")
    if ht.trang_thai == HT_HUY:
        raise ValueError("Thỏa thuận đã huỷ — không xác nhận được.")
    if expected_version is not None and expected_version != ht.version:
        raise ValueError("Phiên bản không khớp — thỏa thuận vừa được cập nhật, hãy tải lại.")

    uid = getattr(user, "id", None)
    la_goc = uid is not None and uid == _head(db, ht.to_goc_id)
    la_thuc_hien = uid is not None and uid == _head(db, ht.to_thuc_hien_id)
    if not (la_goc or la_thuc_hien):
        raise PermissionError("Chỉ tổ trưởng tổ gốc hoặc tổ thực hiện mới được xác nhận.")

    moc = _moc()
    if la_goc and ht.xac_nhan_goc_by_id is None:
        ht.xac_nhan_goc_by_id = uid
        ht.xac_nhan_goc_luc = moc
    if la_thuc_hien and ht.xac_nhan_thuc_hien_by_id is None:
        ht.xac_nhan_thuc_hien_by_id = uid
        ht.xac_nhan_thuc_hien_luc = moc

    truoc = ht.trang_thai
    _cap_nhat_trang_thai(ht)
    if ht.trang_thai == HT_XAC_NHAN and truoc != HT_XAC_NHAN:
        _kiem_tran(repo, ht.cong_viec_id, ht.ngay_lam_viec, float(ht.ty_le_phan_tram or 0),
                   tru_id=ht.id)
    ht.version += 1
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.xac_nhan", ht, detail=f"-> {ht.trang_thai}")
    db.commit()
    return _ket_qua(ht, db)


def huy_ho_tro(
    db: Session, *, user, ho_tro_id: int, ly_do: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Huỷ thỏa thuận (tổ trưởng một trong hai bên). Giữ dòng, đổi trạng thái + ghi lý do."""
    repo = SanXuatPhanBoRepository(db)
    ht = repo.ho_tro(ho_tro_id)
    if ht is None:
        raise ValueError("Không tìm thấy thỏa thuận hỗ trợ.")
    if expected_version is not None and expected_version != ht.version:
        raise ValueError("Phiên bản không khớp — thỏa thuận vừa được cập nhật, hãy tải lại.")
    if not _la_to_truong_mot_ben(db, user, ht):
        raise PermissionError("Chỉ tổ trưởng tổ gốc hoặc tổ thực hiện mới được huỷ.")
    if ht.trang_thai == HT_HUY:
        return _ket_qua(ht, db)

    ht.trang_thai = HT_HUY
    ht.huy_by_id = getattr(user, "id", None)
    ht.huy_luc = _moc()
    ht.ly_do_huy = (ly_do or None)
    ht.version += 1
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.huy", ht, detail=(ly_do or ""))
    db.commit()
    return _ket_qua(ht, db)


def huy_ho_tro_phat_hanh_lai(db: Session, *, cong_viec_id: int, actor_user_id: int | None = None) -> int:
    """Huỷ MỌI thỏa thuận chưa huỷ của một công đoạn khi lịch chưa chạy bị phát hành lại (§9.2).

    KHÔNG commit (nằm trong giao dịch phát hành của caller). Trả số thỏa thuận đã huỷ. Buộc xác
    nhận lại là CÓ CHỦ Ý: bản phát hành mới có thể đổi tổ/ngày nên tỷ lệ cũ không còn chắc đúng."""
    repo = SanXuatPhanBoRepository(db)
    n = 0
    for ht in repo.ho_tro_cua_cong_viec(cong_viec_id):
        if ht.trang_thai == HT_HUY:
            continue
        ht.trang_thai = HT_HUY
        ht.huy_by_id = actor_user_id
        ht.huy_luc = _moc()
        ht.ly_do_huy = "Lịch phát hành lại — thỏa thuận hỗ trợ cần xác nhận lại."
        ht.version += 1
        AuditLogRepository(db).create(
            actor_user_id=actor_user_id,
            action="san_xuat.ho_tro.huy_phat_hanh_lai",
            target=f"san_xuat_ho_tro:{ht.id}",
            detail="",
        )
        n += 1
    return n


# --- Nội bộ ---------------------------------------------------------------------------------
def _cap_nhat_trang_thai(ht: SanXuatHoTro) -> None:
    if ht.trang_thai == HT_HUY:
        return
    if ht.xac_nhan_goc_by_id is not None and ht.xac_nhan_thuc_hien_by_id is not None:
        ht.trang_thai = HT_XAC_NHAN
    else:
        ht.trang_thai = HT_CHO_HAI_BEN


def _kiem_tran(
    repo: SanXuatPhanBoRepository, cong_viec_id: int, ngay: date, ty_le_moi: float,
    *, tru_id: int | None
) -> None:
    da_co = _tong_ty_le_da_xac_nhan(repo, cong_viec_id, ngay, tru_id=tru_id)
    if da_co + ty_le_moi > 100.0 + _EPS:
        raise ValueError(
            f"Tổng tỷ lệ hỗ trợ đã xác nhận trong ngày {ngay} sẽ vượt 100% "
            f"({da_co:g}% + {ty_le_moi:g}%)."
        )
