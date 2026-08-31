"""§16 — Đóng nhóm thành phẩm: tự động đóng ĐỦ + trưởng KCS đóng THIẾU (§13.3).

Trạng thái đóng là DẪN XUẤT, không đẻ thêm cột phụ: cổng soi các tín hiệu tính-lúc-đọc của
nhóm rồi chuyển `san_xuat_nhom.trang_thai`.

  · Đóng ĐỦ (auto) — khi HỘI ĐỦ mọi điều kiện thì nhảy sang `closed_full`. Gọi như CHỐT CHẶN
    sau mỗi thao tác có thể hoàn tất điều kiện cuối (hoàn thành việc · xác nhận bàn giao · chốt
    phân bổ · trả lời lỗi KCS · kho xác nhận nhập/BTP). Không đủ ⇒ no-op, để lần sau.
  · Đóng THIẾU (§13.3) — trưởng KCS chủ động đóng nhóm còn dở, KHÔNG cần Kế hoạch duyệt, nhưng
    BẮT BUỘC lý do (danh mục nhóm `dong_thieu`) và vẫn phải sạch các điều kiện TOÀN VẸN khác
    (không lệch bàn giao · phân bổ đã chốt · hết lỗi KCS chờ · hết BTP chờ kho). ⇒ `closed_short`.

ĐO ĐIỀU KIỆN 3 (KCS cuối) bằng tỷ lệ ĐÃ PHÂN LOẠI trên SỐ ĐÃ XÁC NHẬN NHẬN, KHÔNG đo bằng đã
đạt mục tiêu đơn hàng hay chưa (chủ dự án chốt 20/08). Điều kiện 7 (BTP dư) ĐÃ BỎ khỏi cổng.
Phần "vật tư trả kho" của điều kiện 6 chưa có tầng dữ liệu (§10 mới có nhận, chưa có trả) nên
cổng chỉ soi BTP; bổ sung khi module vật tư-trả-kho ra đời.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.san_xuat import (
    CV_HOAN_THANH,
    NHOM_DONG_DU,
    NHOM_DONG_THIEU,
    SanXuatNhom,
)
from ...models.san_xuat_ly_do import NHOM_DONG_THIEU as LY_DO_NHOM_DONG_THIEU
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_kho_repo import SanXuatKhoRepository
from ...repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from .kcs import _EPS

# Điều kiện KHÔNG thuộc "hoàn thành" — đóng thiếu vẫn phải thoả (§13.3).
_MA_HOAN_THANH = "moi_viec_xong"


def _danh_gia(db: Session, nhom_id: int) -> tuple[SanXuatNhom, list, list[dict]]:
    """Chấm từng điều kiện đóng nhóm (tính-lúc-đọc). Trả (nhom, công-việc-hiện-tại, list điều kiện)."""
    repo = SanXuatRepository(db)
    nhom = repo.nhom(nhom_id)
    if nhom is None:
        raise ValueError("Không tìm thấy nhóm thành phẩm.")
    cvs = repo.cong_viec_hien_tai_cua_nhom(nhom_id)
    kcs_repo = SanXuatKcsRepository(db)
    kho_repo = SanXuatKhoRepository(db)
    pb_repo = SanXuatPhanBoRepository(db)

    # (1) mọi công việc phiên hiện tại đã hoàn thành.
    chua_xong = [cv for cv in cvs if cv.trang_thai != CV_HOAN_THANH]

    # (2 + 8) không còn bàn giao ĐI bị đánh dấu không nhất quán.
    lech = [cv for cv in cvs if pb_repo.co_ban_giao_khong_nhat_quan(cv.id)]

    # (3) KCS cuối đã phân loại HẾT số đã xác nhận nhận (tỷ lệ classified/received ≥ 1), KHÔNG so
    #     với mục tiêu đơn. Bất biến batch `nhan = dat + khong_dat` nên chỉ vỡ nếu có batch dở.
    #     "Chưa nhận gì" KHÔNG được ngầm hiểu là "đạt" — release.van_de_phat_hanh (§4.4) đã chặn
    #     phát hành thiếu KCS cuối nên `co_kcs_cuoi=False` ở đây là dữ liệu tồn từ trước khi có
    #     gate đó, không phải quy tắc "không cần KCS" (quy tắc đó phải chốt riêng, không suy từ 0).
    #     `la_kcs_cuoi` chỉ được gán thật khi qua release.phat_hanh (snapshot.danh_dau_kcs_cuoi);
    #     dữ liệu/test dựng tay chỉ có `la_kcs` (rộng hơn) — dùng lại đúng cách rơi-về đã có ở
    #     dong_thieu (bên dưới) để không vỡ khi thiếu cờ hẹp.
    kcs_final_cvs = [cv for cv in cvs if cv.la_kcs_cuoi] or [cv for cv in cvs if cv.la_kcs]
    co_kcs_cuoi = bool(kcs_final_cvs)
    da_nhan = 0.0
    da_phan_loai = 0.0
    for cv in kcs_final_cvs:
        for b in kcs_repo.cac_kcs_batch(cv.id):
            da_nhan += float(b.so_luong_nhan or 0)
            da_phan_loai += float(b.so_luong_dat or 0) + float(b.so_luong_khong_dat or 0)
    kcs_du = co_kcs_cuoi and da_nhan > _EPS and da_phan_loai + _EPS >= da_nhan

    # (4) mọi phân bổ lương khoán đã chốt (không còn draft/mở lại).
    chua_chot = [cv for cv in cvs if pb_repo.con_phan_bo_chua_chot(cv.id)]

    # (5) hết lỗi KCS chờ trả lời; (6) hết BTP chờ kho xác nhận.
    con_loi = kcs_repo.co_loi_chua_tra_loi(nhom_id)
    con_btp = kho_repo.co_btp_tra_cho_kho(nhom_id)

    dieu_kien = [
        {
            "ma": _MA_HOAN_THANH,
            "ten": "Mọi công việc đã hoàn thành",
            "dat": not chua_xong,
            "chi_tiet": f"còn {len(chua_xong)} việc chưa xong" if chua_xong else "",
        },
        {
            "ma": "khong_lech_ban_giao",
            "ten": "Không còn bàn giao lệch",
            "dat": not lech,
            "chi_tiet": f"{len(lech)} công đoạn bàn giao chưa nhất quán" if lech else "",
        },
        {
            "ma": "kcs_cuoi_phan_loai_du",
            "ten": "KCS cuối đã phân loại hết số nhận",
            "dat": kcs_du,
            "chi_tiet": (
                "" if kcs_du else
                "nhóm chưa xác định bước KCS cuối" if not co_kcs_cuoi else
                "KCS cuối chưa nhận sản phẩm nào" if da_nhan <= _EPS else
                f"mới phân loại {da_phan_loai:g}/{da_nhan:g}"
            ),
        },
        {
            "ma": "phan_bo_da_chot",
            "ten": "Phân bổ lương đã chốt",
            "dat": not chua_chot,
            "chi_tiet": f"{len(chua_chot)} công đoạn còn phân bổ chưa chốt" if chua_chot else "",
        },
        {
            "ma": "het_loi_kcs_cho",
            "ten": "Hết lỗi KCS chờ trả lời",
            "dat": not con_loi,
            "chi_tiet": "còn lỗi KCS chờ trả lời" if con_loi else "",
        },
        {
            "ma": "het_btp_cho_kho",
            "ten": "Hết BTP chờ kho nhận",
            "dat": not con_btp,
            "chi_tiet": "còn BTP chờ kho xác nhận" if con_btp else "",
        },
    ]
    return nhom, cvs, dieu_kien


def dieu_kien_dong_nhom(db: Session, nhom_id: int) -> dict:
    """Đọc tình trạng cổng đóng nhóm — FE hiện checklist "vì sao chưa đóng" + bật nút đóng thiếu."""
    nhom, cvs, dk = _danh_gia(db, nhom_id)
    # Con số CÒN THIẾU của cả nhóm — CHỈ ĐỂ BÀY (spec-thuc-te-vs-ke-hoach §2.3).
    # `_danh_gia` vẫn giữ nguyên 6 điều kiện: nó đo "đã phân loại / đã nhận", CỐ Ý không so mục
    # tiêu đơn (chú thích dòng 63). Người bấm "đóng thiếu" trước đây bấm mù — nay thấy thiếu bao
    # nhiêu, nhưng quyền đóng không đổi.
    # Tập KCS cuối dùng ĐÚNG biểu thức rơi-về đã có ở `_danh_gia` (dòng ~67) và `dong_thieu` (dòng
    # ~217) trong chính module này: `la_kcs_cuoi` chỉ được gán thật khi qua release.phat_hanh
    # (snapshot.danh_dau_kcs_cuoi); dữ liệu/test dựng tay chỉ có `la_kcs` (rộng hơn). Lọc theo
    # `so_luong_ra is not None` PHẢI làm SAU khi đã chọn xong tập bằng `or`, không nhét vào vế
    # trái — nhét vào sẽ rơi-về sai khi nhóm có `la_kcs_cuoi` nhưng chưa khai số. Đổi luật rơi-về
    # thì phải sửa cả BA chỗ (đây + hai chỗ trên), không chỉ chỗ này.
    kcs_final_cvs = [c for c in cvs if c.la_kcs_cuoi] or [c for c in cvs if c.la_kcs]
    kcs_cuoi = [c for c in kcs_final_cvs if c.so_luong_ra is not None]
    tot_map = SanXuatSanLuongRepository(db).tong_tot_nhieu([c.id for c in kcs_cuoi])
    muc_tieu = sum(float(c.so_luong_ra) for c in kcs_cuoi) if kcs_cuoi else None
    da_dat = (
        sum(tot_map.get(c.id, 0.0) for c in kcs_cuoi) if muc_tieu is not None else None
    )
    return {
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": nhom.trang_thai,
        "version": nhom.version,
        "du_dong_du": all(d["dat"] for d in dk),
        "du_dong_thieu": all(d["dat"] for d in dk if d["ma"] != _MA_HOAN_THANH),
        "dieu_kien": dk,
        "muc_tieu": muc_tieu,
        "da_dat": da_dat,
        "con_thieu": max(muc_tieu - da_dat, 0.0) if muc_tieu is not None else None,
    }


def tu_dong_dong_neu_du(
    db: Session, *, nhom_id: int, actor=None, su_kien: str = ""
) -> dict | None:
    """CHỐT CHẶN §16: nếu nhóm còn mở và hội đủ MỌI điều kiện thì đóng ĐỦ. Không đủ ⇒ None (no-op).

    Gọi sau các thao tác có thể hoàn tất điều kiện cuối. Trả dict để router bắn SSE (Sale + Kế
    hoạch SX) khi có đóng; None khi chưa đóng."""
    repo = SanXuatRepository(db)
    nhom = repo.nhom(nhom_id)
    if nhom is None or nhom.trang_thai in (NHOM_DONG_DU, NHOM_DONG_THIEU):
        return None
    _n, _cvs, dk = _danh_gia(db, nhom_id)
    if not all(d["dat"] for d in dk):
        return None
    nhom.trang_thai = NHOM_DONG_DU
    nhom.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(actor, "id", None),
        action="san_xuat_dong_nhom_du",
        target=f"san_xuat_nhom:{nhom.id}",
        detail=f"su_kien={su_kien or 'auto'} order={nhom.order_id}",
    )
    db.commit()
    return {
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": nhom.trang_thai,
        "kieu": "du",
        "version": nhom.version,
    }


def _gate_truong_kcs(db: Session, user, kcs_cvs: list) -> None:
    """Chỉ trưởng KCS (head_user_id của MỘT tổ KCS cuối trong nhóm) mới được đóng thiếu (§13.3)."""
    uid = getattr(user, "id", None)
    for cv in kcs_cvs:
        dept = db.get(Department, cv.department_id) if cv.department_id else None
        if dept is not None and dept.head_user_id is not None and dept.head_user_id == uid:
            return
    raise PermissionError("Chỉ trưởng KCS của nhóm mới được đóng thiếu nhóm này.")


def dong_thieu(
    db: Session,
    *,
    user,
    nhom_id: int,
    ly_do_id: int,
    expected_version: int | None = None,
) -> dict:
    """Trưởng KCS đóng THIẾU nhóm còn dở (§13.3). Bắt buộc lý do; vẫn phải sạch điều kiện toàn vẹn
    (mọi điều kiện TRỪ "mọi việc xong"). Chuyển sang `closed_short`, ghi audit sự kiện + lý do."""
    repo = SanXuatRepository(db)
    nhom = repo.nhom(nhom_id)
    if nhom is None:
        raise ValueError("Không tìm thấy nhóm thành phẩm.")
    if nhom.trang_thai in (NHOM_DONG_DU, NHOM_DONG_THIEU):
        raise ValueError("Nhóm đã đóng, không thể đóng thiếu lần nữa.")
    if expected_version is not None and expected_version != nhom.version:
        raise ValueError("Nhóm vừa được cập nhật, hãy tải lại rồi thao tác.")

    cvs = repo.cong_viec_hien_tai_cua_nhom(nhom_id)
    kcs_cvs = [cv for cv in cvs if cv.la_kcs_cuoi] or [cv for cv in cvs if cv.la_kcs]
    if not kcs_cvs:
        raise PermissionError("Nhóm không có bước KCS nên không có ai đóng thiếu.")
    _gate_truong_kcs(db, user, kcs_cvs)

    ly_do = SanXuatPhanBoRepository(db).ly_do(ly_do_id)
    if ly_do is None or ly_do.nhom != LY_DO_NHOM_DONG_THIEU:
        raise ValueError("Lý do đóng thiếu không hợp lệ.")

    _n, _c, dk = _danh_gia(db, nhom_id)
    thieu = [d for d in dk if d["ma"] != _MA_HOAN_THANH and not d["dat"]]
    if thieu:
        raise ValueError("Chưa thể đóng thiếu — " + "; ".join(d["ten"] for d in thieu) + ".")

    nhom.trang_thai = NHOM_DONG_THIEU
    nhom.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_dong_nhom_thieu",
        target=f"san_xuat_nhom:{nhom.id}",
        detail=f"ly_do={ly_do_id} order={nhom.order_id}",
    )
    db.commit()
    return {
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": nhom.trang_thai,
        "kieu": "thieu",
        "ly_do_id": ly_do_id,
        "version": nhom.version,
    }
