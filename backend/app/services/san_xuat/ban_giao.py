"""Thực hiện sản xuất — BÀN GIAO công đoạn (Giai đoạn 3, §11.2 · §11.3).

Một số lượng THỐNG NHẤT mỗi lần giao — không lưu hai con số cạnh tranh. Cùng tổ + cùng LSX thì
tự `confirmed`; khác tổ/khác LSX thì `proposed` → bên NHẬN xác nhận đúng con số cuối. Điều chỉnh
KHÔNG xoá cứng: đẻ dòng lịch sử trước/sau; giảm dưới lượng công đoạn sau đã dùng ⇒ cờ không nhất quán.

Quyền (dòng quyền theo tổ, mg 0302): ĐỀ XUẤT/SỬA đòi Xác nhận sản lượng ở tổ NGUỒN; XÁC NHẬN đòi
Xác nhận sản lượng trọn tổ ĐÍCH; ĐIỀU CHỈNH cho phép người có quyền ở một trong hai bên (người nhập
sai sửa lại). Tất cả siết ở service, router chỉ gác coarse.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat_san_luong import (
    BG_DE_XUAT,
    BG_DIEU_CHINH,
    BG_XAC_NHAN,
    SanXuatBanGiao,
    SanXuatBanGiaoBatch,
    SanXuatBanGiaoDieuChinh,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ..quyen_to import VIEC_XAC_NHAN, nguoi_co_quyen
from .thuc_thi import _gate, _kiem_version, _moc
from .san_luong import _EPS, _so_khong_am


def _nguoi_nhan(db: Session, user, *department_ids: int | None) -> list[int]:
    """Người giữ quyền Xác nhận sản lượng (cả tổ) ở các tổ này — trừ chính người vừa bấm."""
    uid = getattr(user, "id", None)
    ket: set[int] = set()
    for d in department_ids:
        ket.update(nguoi_co_quyen(db, d, VIEC_XAC_NHAN))
    ket.discard(uid)
    return sorted(ket)


def _gate_hai_ben(db: Session, user, nguon_cv, dich_cv) -> None:
    """Điều chỉnh: người có quyền Xác nhận sản lượng ở tổ NGUỒN hoặc ĐÍCH đều được (người nhập sai
    sửa lại, §11.3)."""
    for cv in (nguon_cv, dich_cv):
        if cv is None:
            continue
        try:
            _gate(db, user, cv, VIEC_XAC_NHAN)
            return
        except PermissionError:
            pass
    raise PermissionError("Bạn không có quyền Xác nhận sản lượng ở tổ nguồn hoặc tổ đích.")


def _la_cung_to(nguon_cv, dich_cv) -> bool:
    """Tự xác nhận ⇔ cùng tổ VÀ cùng LSX (§11.2). Bước ghép gộp nhiều LSX ⇒ luôn khác LSX ⇒ cần
    xác nhận hai bên (khớp cổng §10.2)."""
    if dich_cv is None:
        return False
    return (
        nguon_cv.department_id is not None
        and nguon_cv.department_id == dich_cv.department_id
        and nguon_cv.lsx_id is not None
        and nguon_cv.lsx_id == dich_cv.lsx_id
    )


def _ket_qua(
    bg: SanXuatBanGiao, nguon_cv, dich_cv, *,
    notify_user_ids: list[int] | None = None, su_kien: str = "",
) -> dict:
    return {
        "ban_giao_id": bg.id,
        "trang_thai_ban_giao": bg.trang_thai,
        "so_luong": float(bg.so_luong),
        "khong_nhat_quan": bg.khong_nhat_quan,
        "version": bg.version,
        "nguon_cong_viec_id": bg.nguon_cong_viec_id,
        "dich_cong_viec_id": bg.dich_cong_viec_id,
        "nguon_department_id": nguon_cv.department_id if nguon_cv else None,
        "dich_department_id": dich_cv.department_id if dich_cv else None,
        "notify_user_ids": list(notify_user_ids or []),
        # Nhãn cho toast của người nhận (§18) — họ thường không mở đúng công đoạn này.
        "su_kien": su_kien,
        "nguon_ten": nguon_cv.ten_cong_doan if nguon_cv else "",
        "dich_ten": dich_cv.ten_cong_doan if dich_cv else "",
        "don_vi": bg.don_vi,
    }


def _so_theo_me(
    repo: SanXuatSanLuongRepository,
    nguon_cv,
    batch_ids: list[int] | None,
    *,
    ban_giao: SanXuatBanGiao | None = None,
) -> tuple[list[int], float]:
    """Chọn mẻ ⇒ ra số lượng giao (14/09/2026). Tổ KHÔNG gõ số: số = tổng TỐT của các mẻ chọn.

    Còn mẻ chưa giao thì phải chọn ít nhất một; mẻ đã đi theo lần giao KHÁC thì không chọn lại được.
    Hết mẻ chưa giao mà vẫn còn lẻ (điều chỉnh giảm sau xác nhận) thì giao nốt phần lẻ, không mẻ.
    Số không vượt phần còn chưa giao: bàn giao tạo trước khi có giao-theo-mẻ không gắn mẻ nào, nên
    mẻ cũ vẫn hiện "chưa giao" dù số đã đi rồi.

    `ban_giao` = lần giao đang SỬA: mẻ của chính nó chọn lại được, số của nó không tính là đã giao."""
    cua_no: set[int] = set()
    con_lai = repo.tong_tot(nguon_cv.id) - repo.tong_da_giao(nguon_cv.id)
    if ban_giao is not None:
        cua_no = set(repo.me_cua_ban_giao_nhieu([ban_giao.id]).get(ban_giao.id, []))
        con_lai += float(ban_giao.so_luong)
    da_giao = repo.batch_da_giao_ids(nguon_cv.id) - cua_no
    chua_giao = {
        b.id: b for b in repo.cac_batch(nguon_cv.id)
        if b.id not in da_giao and float(b.tot) > _EPS
    }
    chon = list(dict.fromkeys(batch_ids or []))
    if chon:
        if any(i not in chua_giao for i in chon):
            raise ValueError("Có mẻ không thuộc bước này, không có sản lượng tốt hoặc đã giao rồi.")
        sl = min(sum(float(chua_giao[i].tot) for i in chon), con_lai)
    elif chua_giao:
        raise ValueError("Chọn mẻ cần giao.")
    else:
        sl = con_lai
    if sl <= _EPS:
        raise ValueError("Không còn sản lượng tốt để giao.")
    return chon, sl


def de_xuat(
    db: Session,
    *,
    user,
    nguon_cong_viec_id: int,
    dich_cong_viec_id: int | None,
    don_vi: str | None = None,
    batch_ids: list[int] | None = None,
) -> dict:
    """Bên NGUỒN đề xuất giao sản lượng tốt sang công đoạn sau (§11.2).

    Cùng tổ + cùng LSX → `confirmed` ngay. Khác → `proposed`, chờ bên đích xác nhận.

    ĐÍCH phải là chặng sau theo routing lệnh (`cong_viec_chang_sau`) — không còn chọn tự do trong
    mọi việc cùng lệnh. Bước cuối lệnh (không có chặng sau) KHÔNG bàn giao: thành phẩm rời tổ qua
    KCS kiểm rồi đề nghị nhập kho. "Giao ra kho" (`dich=None`) ĐÃ GỠ 17/09/2026 — nó đẻ một bàn giao
    không ai xác nhận được, treo mãi ở `proposed`.

    GIAO THEO MẺ: số lượng suy ra từ mẻ chọn (`_so_theo_me`), không nhận số gõ tay. Đếm thực tế lệch
    thì bên nhận xác nhận xong rồi ĐIỀU CHỈNH (§11.3)."""
    repo = SanXuatSanLuongRepository(db)
    nguon_cv = repo.cong_viec(nguon_cong_viec_id)
    if nguon_cv is None:
        raise ValueError("Không tìm thấy công việc nguồn.")
    _gate(db, user, nguon_cv, VIEC_XAC_NHAN)

    chang_sau = {c.id: c for c in repo.cong_viec_chang_sau(nguon_cv)}
    if not chang_sau:
        raise ValueError(
            "Bước cuối của lệnh không bàn giao — thành phẩm vào kho qua KCS kiểm và đề nghị nhập kho."
        )
    if not dich_cong_viec_id:
        raise ValueError("Bước này còn chặng sau theo routing — phải giao cho chặng sau.")
    if dich_cong_viec_id not in chang_sau:
        raise ValueError("Đích bàn giao không phải chặng sau của bước này theo routing.")
    dich_cv = chang_sau[dich_cong_viec_id]

    chon, sl = _so_theo_me(repo, nguon_cv, batch_ids)

    don_vi_bg = (don_vi or nguon_cv.don_vi_ra or "").strip()
    if not don_vi_bg:
        raise ValueError("Bàn giao chưa có đơn vị.")

    cung_to = _la_cung_to(nguon_cv, dich_cv)
    now = _moc()
    bg = SanXuatBanGiao(
        nguon_cong_viec_id=nguon_cv.id,
        dich_cong_viec_id=dich_cv.id,
        cung_to=cung_to,
        so_luong=sl,
        don_vi=don_vi_bg,
        trang_thai=BG_XAC_NHAN if cung_to else BG_DE_XUAT,
        de_xuat_by_id=getattr(user, "id", None),
        de_xuat_luc=now,
        xac_nhan_by_id=getattr(user, "id", None) if cung_to else None,
        xac_nhan_luc=now if cung_to else None,
    )
    repo.add(bg)
    repo.flush()
    for batch_id in chon:
        repo.add(SanXuatBanGiaoBatch(ban_giao_id=bg.id, batch_id=batch_id))
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_de_xuat",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=(
            f"nguon={nguon_cv.id} dich={dich_cv.id} sl={sl} "
            f"me={','.join(map(str, chon)) or '-'} {'cung_to' if cung_to else 'de_xuat'}"
        ),
    )
    db.commit()
    # Chờ xác nhận → báo người xác nhận được ở tổ ĐÍCH; tự xác nhận → không cần báo ai đợi.
    notify = [] if cung_to else _nguoi_nhan(db, user, dich_cv.department_id)
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_ids=notify, su_kien="de_xuat")


def sua_de_xuat(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    batch_ids: list[int] | None,
    expected_version: int | None = None,
) -> dict:
    """Bên NGUỒN sửa lại MẺ đi theo lần giao khi còn `proposed` (§11.2) — tick nhầm thì gỡ ra, sót
    thì thêm vào; số lượng tính lại theo mẻ. Đã xác nhận thì không sửa mẻ nữa, chỉ điều chỉnh số."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai != BG_DE_XUAT:
        raise ValueError("Chỉ sửa được đề xuất chưa xác nhận.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id) if bg.dich_cong_viec_id else None
    _gate(db, user, nguon_cv, VIEC_XAC_NHAN)
    _kiem_version(bg, expected_version)

    chon, sl = _so_theo_me(repo, nguon_cv, batch_ids, ban_giao=bg)
    sl_truoc = float(bg.so_luong)

    # Gỡ dòng cũ TRƯỚC rồi mới thêm: `batch_id` UNIQUE, mà trong một lần flush SQLAlchemy chèn
    # trước xoá sau. Mẻ giữ nguyên thì giữ nguyên dòng.
    cu = {lk.batch_id: lk for lk in repo.lien_ket_me(bg.id)}
    for batch_id, lk in cu.items():
        if batch_id not in chon:
            repo.delete(lk)
    repo.flush()
    for batch_id in chon:
        if batch_id not in cu:
            repo.add(SanXuatBanGiaoBatch(ban_giao_id=bg.id, batch_id=batch_id))

    bg.so_luong = sl
    bg.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_sua",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"sl={sl_truoc:g}->{sl:g} me={','.join(map(str, chon)) or '-'}",
    )
    db.commit()
    return _ket_qua(bg, nguon_cv, dich_cv, su_kien="sua", notify_user_ids=_nguoi_nhan(
        db, user, dich_cv.department_id if dich_cv else None))


def xac_nhan(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    expected_version: int | None = None,
) -> dict:
    """Bên ĐÍCH xác nhận đúng con số cuối (§11.2). Số này thành đầu ra được chấp nhận + đầu vào khả dụng."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai != BG_DE_XUAT:
        raise ValueError("Bàn giao này không ở trạng thái chờ xác nhận.")
    if bg.dich_cong_viec_id is None:
        raise ValueError("Công đoạn nhận của bàn giao này không còn — không xác nhận được.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id)
    _gate(db, user, dich_cv, VIEC_XAC_NHAN)
    _kiem_version(bg, expected_version)

    bg.trang_thai = BG_XAC_NHAN
    bg.xac_nhan_by_id = getattr(user, "id", None)
    bg.xac_nhan_luc = _moc()
    bg.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_xac_nhan",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"sl={float(bg.so_luong)}",
    )
    db.commit()
    return _ket_qua(bg, nguon_cv, dich_cv, su_kien="xac_nhan", notify_user_ids=_nguoi_nhan(
        db, user, nguon_cv.department_id if nguon_cv else None))


def dieu_chinh(
    db: Session,
    *,
    user,
    ban_giao_id: int,
    so_luong_sau,
    mo_ta: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Điều chỉnh số lượng đã xác nhận (§11.3): đẻ dòng lịch sử trước/sau, cập nhật bàn giao.

    Giảm dưới lượng công đoạn sau ĐÃ DÙNG ⇒ đánh dấu không nhất quán (chặn chốt phân bổ/đóng nhóm).
    Ghi chú tự do (`mo_ta`) tuỳ chọn — danh mục lý do/lỗi ĐÃ GỠ."""
    repo = SanXuatSanLuongRepository(db)
    bg = repo.ban_giao(ban_giao_id)
    if bg is None:
        raise ValueError("Không tìm thấy bàn giao.")
    if bg.trang_thai not in (BG_XAC_NHAN, BG_DIEU_CHINH):
        raise ValueError("Chỉ điều chỉnh bàn giao đã xác nhận.")
    nguon_cv = repo.cong_viec(bg.nguon_cong_viec_id)
    dich_cv = repo.cong_viec(bg.dich_cong_viec_id) if bg.dich_cong_viec_id else None
    _gate_hai_ben(db, user, nguon_cv, dich_cv)
    _kiem_version(bg, expected_version)

    sl_sau = _so_khong_am(so_luong_sau, "Số lượng sau điều chỉnh")
    sl_truoc = float(bg.so_luong)

    # Không nhất quán nếu giảm dưới lượng công đoạn sau đã tiêu thụ (truy vết qua lot đầu vào).
    da_dung = 0.0
    if dich_cv is not None:
        da_dung = repo.da_dung_tu_nguon(bg.nguon_cong_viec_id, bg.dich_cong_viec_id)
    khong_nhat_quan = sl_sau < da_dung - _EPS

    repo.add(
        SanXuatBanGiaoDieuChinh(
            ban_giao_id=bg.id,
            so_luong_truoc=sl_truoc,
            so_luong_sau=sl_sau,
            mo_ta=(mo_ta or "").strip() or None,
            khong_nhat_quan=khong_nhat_quan,
            created_by=getattr(user, "id", None),
        )
    )
    bg.so_luong = sl_sau
    bg.trang_thai = BG_DIEU_CHINH
    bg.khong_nhat_quan = khong_nhat_quan
    bg.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_ban_giao_dieu_chinh",
        target=f"san_xuat_ban_giao:{bg.id}",
        detail=f"{sl_truoc} -> {sl_sau}{' KHONG_NHAT_QUAN' if khong_nhat_quan else ''}",
    )
    db.commit()
    # Báo cả hai bên (trừ chính người vừa điều chỉnh).
    notify = _nguoi_nhan(db, user, nguon_cv.department_id if nguon_cv else None,
                         dich_cv.department_id if dich_cv else None)
    return _ket_qua(bg, nguon_cv, dich_cv, notify_user_ids=notify, su_kien="dieu_chinh")
