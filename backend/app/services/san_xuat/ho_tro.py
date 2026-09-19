"""Thực hiện sản xuất — HỖ TRỢ CHÉO giữa hai tổ (§9).

Điều phối THỎA THUẬN hỗ trợ: đề xuất → hai bên xác nhận → lưu thành VẾT "người tổ nào sang giúp
tổ nào, ngày nào". Tuân §18: kiểm quyền tại service → transaction → version chống bấm trùng →
ghi audit → (SSE do router phát sau commit). Truy vấn/ghi DB ở `repositories/san_xuat_ho_tro_repo.py`.

⚠️ 18/09/2026 (mg `0322`): ô TỶ LỆ (`ty_le_phan_tram`) và trần "tổng ≤ 100%" gỡ hẳn cùng tầng CHIA
SẢN LƯỢNG. Sản xuất CHỈ GHI NHẬN — không nhân/chia/cộng/trừ ra tiền hay ra phần của ai; kế toán
chia sau. Thỏa thuận hỗ trợ nay không mang con số nào.

LUẬT còn lại (§9.1–§9.2):
  - Phải đủ xác nhận của HAI bên — người có Xác nhận sản lượng trọn tổ gốc của người hỗ trợ và
    trọn tổ đang thực hiện công đoạn (dòng quyền theo tổ, mg 0302).
  - Một người chỉ có MỘT thỏa thuận còn sống trong cùng (công đoạn, ngày).
  - Người không đi làm ngày đó thì không hỗ trợ được.
  - Lịch chưa chạy bị phát hành lại ⇒ huỷ thỏa thuận, buộc xác nhận lại (`huy_ho_tro_phat_hanh_lai`).
"""
from __future__ import annotations

from datetime import date

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
from ...repositories.san_xuat_ho_tro_repo import SanXuatHoTroRepository
from ..quyen_to import VIEC_XAC_NHAN, nguoi_co_quyen, quyen_cua_uid
from .thuc_thi import _moc
from .tinh_trang_nguoi import kiem_di_lam


# --- Trợ giúp ------------------------------------------------------------------------------
def _lay_cong_viec(repo: SanXuatHoTroRepository, cong_viec_id: int):
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    return cv


def _ben_cua(db: Session, user, to_goc_id: int | None, to_thuc_hien_id: int | None) -> tuple[bool, bool]:
    """(đứng được cho bên GỐC?, đứng được cho bên THỰC HIỆN?) — quyền Xác nhận sản lượng trên TRỌN
    tổ đó (thỏa thuận cấp tổ, không gắn việc của riêng ai nên "Của tôi" không đủ)."""
    q = quyen_cua_uid(db, getattr(user, "id", None))
    if q is None:
        return False, False
    return q.co_tron(VIEC_XAC_NHAN, to_goc_id), q.co_tron(VIEC_XAC_NHAN, to_thuc_hien_id)


def _ket_qua(ht: SanXuatHoTro, db: Session, *, user, su_kien: str) -> dict:
    """Dữ liệu router cần để phát SSE (§18) — trừ chính người vừa bấm.

    Còn chờ ⇒ chỉ báo người giữ Xác nhận sản lượng ở BÊN CHƯA XÁC NHẬN (bên kia đã đứng tên rồi,
    báo "chờ tổ bạn xác nhận" cho họ là sai). Đã đủ hai bên / đã huỷ ⇒ báo cả hai tổ."""
    notify: set[int] = set()
    if ht.trang_thai != HT_CHO_HAI_BEN or ht.xac_nhan_goc_by_id is None:
        notify |= set(nguoi_co_quyen(db, ht.to_goc_id, VIEC_XAC_NHAN))
    if ht.trang_thai != HT_CHO_HAI_BEN or ht.xac_nhan_thuc_hien_by_id is None:
        notify |= set(nguoi_co_quyen(db, ht.to_thuc_hien_id, VIEC_XAC_NHAN))
    notify.discard(getattr(user, "id", None))
    emp = db.get(Employee, ht.employee_id)
    cv = SanXuatHoTroRepository(db).cong_viec(ht.cong_viec_id)
    to_goc = db.get(Department, ht.to_goc_id) if ht.to_goc_id else None
    to_th = db.get(Department, ht.to_thuc_hien_id) if ht.to_thuc_hien_id else None
    return {
        "ho_tro_id": ht.id,
        "cong_viec_id": ht.cong_viec_id,
        "to_goc_id": ht.to_goc_id,
        "to_thuc_hien_id": ht.to_thuc_hien_id,
        "trang_thai": ht.trang_thai,
        "notify_user_ids": sorted(notify),
        # Nhãn cho toast của người nhận — họ thường không mở đúng công đoạn này.
        "su_kien": su_kien,
        "ho_ten": emp.full_name if emp else "",
        "ten_cong_doan": cv.ten_cong_doan if cv else "",
        "to_goc_ten": to_goc.name if to_goc else "",
        "to_thuc_hien_ten": to_th.name if to_th else "",
    }


def _audit(db: Session, user, action: str, ht: SanXuatHoTro, detail: str = "") -> None:
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action=action,
        target=f"san_xuat_ho_tro:{ht.id}",
        detail=detail,
    )


# --- Lệnh -----------------------------------------------------------------------------------
def de_xuat_ho_tro(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    employee_id: int,
    ngay_lam_viec: date,
    mo_ta: str | None = None,
) -> dict:
    """Đề xuất một thỏa thuận hỗ trợ. Người có quyền Xác nhận sản lượng ở tổ gốc HOẶC tổ thực hiện
    đều được đề xuất; bên kia xác nhận sau. Snapshot tổ thực hiện = tổ của công đoạn; tổ gốc = tổ của người hỗ trợ."""
    repo = SanXuatHoTroRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)

    emp = db.get(Employee, employee_id)
    if emp is None:
        raise ValueError("Không tìm thấy người hỗ trợ.")
    to_goc_id = emp.department_id
    to_thuc_hien_id = cv.department_id
    if to_goc_id and to_thuc_hien_id and to_goc_id == to_thuc_hien_id:
        raise ValueError("Người hỗ trợ đã thuộc tổ thực hiện — không cần thỏa thuận hỗ trợ chéo.")

    uid = getattr(user, "id", None)
    ben_goc, ben_thuc_hien = _ben_cua(db, user, to_goc_id, to_thuc_hien_id)
    if uid is None or not (ben_goc or ben_thuc_hien):
        raise PermissionError(
            "Cần quyền Xác nhận sản lượng (cả tổ) ở tổ gốc hoặc tổ thực hiện mới được đề xuất hỗ trợ.")

    # Người không đi làm ngày đó thì không hỗ trợ được. Đang chạy việc ở tổ mình thì KHÔNG chặn:
    # thỏa thuận tính theo ngày, không theo giờ — ô chọn chỉ cảnh báo (tinh_trang_nguoi).
    kiem_di_lam(db, emp, ngay_lam_viec, duoi="không đề xuất hỗ trợ được")
    # Một người sang giúp một công đoạn trong một ngày thì chỉ cần MỘT vết; dòng thứ hai là
    # bản trùng, đọc lên không biết tin dòng nào.
    if repo.ho_tro_con_song_cua_nguoi(cong_viec_id, employee_id, ngay_lam_viec) is not None:
        raise ValueError(
            f"{emp.full_name} đã có thỏa thuận hỗ trợ công đoạn này ngày "
            f"{ngay_lam_viec.strftime('%d/%m/%Y')} — huỷ thỏa thuận cũ rồi đề xuất lại nếu cần sửa."
        )

    ht = SanXuatHoTro(
        cong_viec_id=cong_viec_id,
        employee_id=employee_id,
        to_goc_id=to_goc_id,
        to_thuc_hien_id=to_thuc_hien_id,
        ngay_lam_viec=ngay_lam_viec,
        trang_thai=HT_CHO_HAI_BEN,
        mo_ta=(mo_ta or None),
        de_xuat_by_id=uid,
    )
    # Người đề xuất tính là ĐÃ xác nhận cho bên của mình (khỏi bắt bấm hai lần).
    moc = _moc()
    if ben_goc:
        ht.xac_nhan_goc_by_id = uid
        ht.xac_nhan_goc_luc = moc
    if ben_thuc_hien:
        ht.xac_nhan_thuc_hien_by_id = uid
        ht.xac_nhan_thuc_hien_luc = moc
    _cap_nhat_trang_thai(ht)

    repo.add(ht)
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.de_xuat", ht,
           detail=f"nv={employee_id} ngay={ngay_lam_viec}")
    db.commit()
    return _ket_qua(ht, db, user=user, su_kien="de_xuat")


def xac_nhan_ho_tro(
    db: Session, *, user, ho_tro_id: int, expected_version: int | None = None
) -> dict:
    """Xác nhận thỏa thuận cho BÊN của người bấm (tự nhận diện gốc/thực hiện qua quyền tổ). Đủ
    hai bên → `confirmed`."""
    repo = SanXuatHoTroRepository(db)
    ht = repo.ho_tro(ho_tro_id)
    if ht is None:
        raise ValueError("Không tìm thấy thỏa thuận hỗ trợ.")
    if ht.trang_thai == HT_HUY:
        raise ValueError("Thỏa thuận đã huỷ — không xác nhận được.")
    if expected_version is not None and expected_version != ht.version:
        raise ValueError("Phiên bản không khớp — thỏa thuận vừa được cập nhật, hãy tải lại.")

    uid = getattr(user, "id", None)
    la_goc, la_thuc_hien = _ben_cua(db, user, ht.to_goc_id, ht.to_thuc_hien_id)
    if uid is None or not (la_goc or la_thuc_hien):
        raise PermissionError(
            "Cần quyền Xác nhận sản lượng (cả tổ) ở tổ gốc hoặc tổ thực hiện mới được xác nhận.")

    moc = _moc()
    ghi_them = False
    if la_goc and ht.xac_nhan_goc_by_id is None:
        ht.xac_nhan_goc_by_id = uid
        ht.xac_nhan_goc_luc = moc
        ghi_them = True
    if la_thuc_hien and ht.xac_nhan_thuc_hien_by_id is None:
        ht.xac_nhan_thuc_hien_by_id = uid
        ht.xac_nhan_thuc_hien_luc = moc
        ghi_them = True
    if not ghi_them:
        # Bấm lại khi bên mình đã đứng tên: báo thẳng, đừng trả "đã xác nhận" mà không đổi gì.
        raise ValueError("Bên của bạn đã xác nhận thỏa thuận này — đang chờ tổ kia xác nhận.")

    _cap_nhat_trang_thai(ht)
    ht.version += 1
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.xac_nhan", ht, detail=f"-> {ht.trang_thai}")
    db.commit()
    return _ket_qua(ht, db, user=user, su_kien="xac_nhan")


def huy_ho_tro(
    db: Session, *, user, ho_tro_id: int, ly_do: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Huỷ thỏa thuận (người đứng được cho một trong hai bên). Giữ dòng, đổi trạng thái + ghi lý do."""
    repo = SanXuatHoTroRepository(db)
    ht = repo.ho_tro(ho_tro_id)
    if ht is None:
        raise ValueError("Không tìm thấy thỏa thuận hỗ trợ.")
    if expected_version is not None and expected_version != ht.version:
        raise ValueError("Phiên bản không khớp — thỏa thuận vừa được cập nhật, hãy tải lại.")
    if not any(_ben_cua(db, user, ht.to_goc_id, ht.to_thuc_hien_id)):
        raise PermissionError(
            "Cần quyền Xác nhận sản lượng (cả tổ) ở tổ gốc hoặc tổ thực hiện mới được huỷ.")
    if ht.trang_thai == HT_HUY:
        return _ket_qua(ht, db, user=user, su_kien="huy")

    ht.trang_thai = HT_HUY
    ht.huy_by_id = getattr(user, "id", None)
    ht.huy_luc = _moc()
    ht.ly_do_huy = (ly_do or None)
    ht.version += 1
    repo.flush()
    _audit(db, user, "san_xuat.ho_tro.huy", ht, detail=(ly_do or ""))
    db.commit()
    return _ket_qua(ht, db, user=user, su_kien="huy")


def huy_ho_tro_phat_hanh_lai(db: Session, *, cong_viec_id: int, actor_user_id: int | None = None) -> int:
    """Huỷ MỌI thỏa thuận chưa huỷ của một công đoạn khi lịch chưa chạy bị phát hành lại (§9.2).

    KHÔNG commit (nằm trong giao dịch phát hành của caller). Trả số thỏa thuận đã huỷ. Buộc xác
    nhận lại là CÓ CHỦ Ý: bản phát hành mới có thể đổi tổ/ngày nên vết cũ không còn chắc đúng."""
    repo = SanXuatHoTroRepository(db)
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

