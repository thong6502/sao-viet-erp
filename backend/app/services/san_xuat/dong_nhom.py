"""§16 — Đóng nhóm thành phẩm: tự động đóng ĐỦ + trưởng KCS đóng THIẾU (§13.3).

Trạng thái đóng là DẪN XUẤT, không đẻ thêm cột phụ: cổng soi các tín hiệu tính-lúc-đọc của
nhóm rồi chuyển `san_xuat_nhom.trang_thai`.

  · Đóng ĐỦ (auto) — khi HỘI ĐỦ mọi điều kiện thì nhảy sang `closed_full`. Gọi như CHỐT CHẶN
    sau mỗi thao tác có thể hoàn tất điều kiện cuối (hoàn thành việc · xác nhận bàn giao · chốt
    phân bổ · KCS kiểm công đoạn). Không đủ ⇒ no-op, để lần sau.
  · Đóng THIẾU (§13.3) — trưởng tổ KCS (`head_user_id` của phòng ban `is_kcs`) chủ động đóng nhóm
    còn dở HOẶC hụt mục tiêu, KHÔNG cần Kế hoạch duyệt, nhưng vẫn phải sạch các điều kiện TOÀN VẸN
    (không lệch bàn giao · công đoạn cuối đã kiểm hết · phân bổ đã chốt). ⇒ `closed_short`.

"ĐỦ" nghĩa là ĐỦ HÀNG, không chỉ "làm xong": Σ số KCS ĐẠT ở công đoạn cuối phải ≥ mục tiêu
(Σ `so_luong_ra` của công đoạn cuối, chốt lúc phát hành — gồm mọi phân đoạn khi bước bị tách lần
chạy). Đổi 17/09/2026: trước đó cổng chỉ đòi "KCS đã kiểm hết số tốt tổ ghi" (chốt 20/08), nên nhóm
làm xong mà hụt hàng vẫn tự đóng ĐỦ và báo Sale "đơn có thể giao".
Điều kiện 3 vẫn giữ: Σ(đạt + lỗi) KCS đã kiểm ở công đoạn cuối ≥ Σ tốt tổ đã ghi. Lỗi KCS chỉ cần
tổ bấm "Đã xem", không chặn đóng nhóm. BTP dư (điều kiện 6–7) ĐÃ GỠ hẳn 17/09/2026.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import (
    CV_HOAN_THANH,
    NHOM_DONG_DU,
    NHOM_DONG_THIEU,
    SanXuatNhom,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from .kcs import _EPS, gate_truong_kcs

# Hai điều kiện "đã ĐỦ" — đóng thiếu chính là đóng khi hụt một trong hai; mọi điều kiện còn lại là
# TOÀN VẸN, đóng thiếu vẫn phải thoả (§13.3).
_MA_HOAN_THANH = "moi_viec_xong"
_MA_DAT_MUC_TIEU = "dat_muc_tieu"
_MA_DU = (_MA_HOAN_THANH, _MA_DAT_MUC_TIEU)


def _so(v: float) -> str:
    """Số kiểu Việt cho dòng chi tiết: 10000 → "10.000", 12.5 → "12,5". `:g` in 1e+06 từ một triệu."""
    t = f"{v:,.3f}".rstrip("0").rstrip(".")
    return t.translate(str.maketrans(",.", ".,"))


def _danh_gia(db: Session, nhom_id: int) -> tuple[SanXuatNhom, list[dict], dict]:
    """Chấm từng điều kiện đóng nhóm (tính-lúc-đọc). Trả (nhom, list điều kiện, số mục tiêu/đã đạt)."""
    repo = SanXuatRepository(db)
    nhom = repo.nhom(nhom_id)
    if nhom is None:
        raise ValueError("Không tìm thấy nhóm thành phẩm.")
    cvs = repo.cong_viec_hien_tai_cua_nhom(nhom_id)
    kcs_repo = SanXuatKcsRepository(db)
    pb_repo = SanXuatPhanBoRepository(db)

    # (1) mọi công việc phiên hiện tại đã hoàn thành.
    chua_xong = [cv for cv in cvs if cv.trang_thai != CV_HOAN_THANH]

    # (2 + 8) không còn bàn giao ĐI bị đánh dấu không nhất quán.
    lech = [cv for cv in cvs if pb_repo.co_ban_giao_khong_nhat_quan(cv.id)]

    # (3) công đoạn cuối: KCS đã kiểm hết số tốt tổ ghi. `la_kcs_cuoi` do release gán
    #     (`snapshot.danh_dau_kcs_cuoi`); nhóm không có cờ đó thì không có gì để đưa vào kho.
    cuoi = [cv for cv in cvs if cv.la_kcs_cuoi]
    tot_map = SanXuatSanLuongRepository(db).tong_tot_nhieu([cv.id for cv in cuoi])
    kiem_map = kcs_repo.tong_kiem_nhieu([cv.id for cv in cuoi])
    tot = sum(tot_map.get(cv.id, 0.0) for cv in cuoi)
    da_kiem = sum(sum(kiem_map.get(cv.id, (0, 0.0, 0.0))[1:]) for cv in cuoi)
    kcs_du = bool(cuoi) and tot > _EPS and da_kiem + _EPS >= tot

    # (3b) KCS ĐẠT đủ mục tiêu. "Đạt" = số KCS đạt, KHÔNG phải số tốt tổ tự ghi (KCS theo lệnh §6:
    #     hàng chưa qua KCS không vào kho). Bước không có `so_luong_ra` thì không có gì để so ⇒ chưa
    #     đạt: nhóm như vậy chỉ đóng thiếu được, không tự nhận là đủ.
    co_muc_tieu = [cv for cv in cuoi if cv.so_luong_ra is not None]
    muc_tieu = sum(float(cv.so_luong_ra) for cv in co_muc_tieu) if co_muc_tieu else None
    da_dat = sum(kiem_map.get(cv.id, (0, 0.0, 0.0))[1] for cv in co_muc_tieu) if co_muc_tieu else None
    dat_muc_tieu = muc_tieu is not None and da_dat + _EPS >= muc_tieu

    # (4) mọi phân bổ lương khoán đã chốt (không còn draft/mở lại).
    chua_chot = [cv for cv in cvs if pb_repo.con_phan_bo_chua_chot(cv.id)]

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
            "ma": "kcs_cuoi_kiem_het",
            "ten": "KCS đã kiểm hết công đoạn cuối",
            "dat": kcs_du,
            "chi_tiet": (
                "" if kcs_du else
                "nhóm chưa xác định công đoạn cuối" if not cuoi else
                "công đoạn cuối chưa ghi số tốt" if tot <= _EPS else
                f"mới kiểm {_so(da_kiem)}/{_so(tot)}"
            ),
        },
        {
            "ma": _MA_DAT_MUC_TIEU,
            "ten": "KCS đạt đủ mục tiêu",
            "dat": dat_muc_tieu,
            "chi_tiet": (
                "" if dat_muc_tieu else
                "công đoạn cuối chưa có số mục tiêu" if muc_tieu is None else
                f"mới đạt {_so(da_dat)}/{_so(muc_tieu)}"
            ),
        },
        {
            "ma": "phan_bo_da_chot",
            "ten": "Phân bổ lương đã chốt",
            "dat": not chua_chot,
            "chi_tiet": f"{len(chua_chot)} công đoạn còn phân bổ chưa chốt" if chua_chot else "",
        },
    ]
    return nhom, dieu_kien, {"muc_tieu": muc_tieu, "da_dat": da_dat}


def dieu_kien_dong_nhom(db: Session, nhom_id: int) -> dict:
    """Đọc tình trạng cổng đóng nhóm — FE hiện checklist "vì sao chưa đóng" + bật nút đóng thiếu."""
    nhom, dk, so = _danh_gia(db, nhom_id)
    muc_tieu, da_dat = so["muc_tieu"], so["da_dat"]
    return {
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": nhom.trang_thai,
        "version": nhom.version,
        "du_dong_du": all(d["dat"] for d in dk),
        "du_dong_thieu": all(d["dat"] for d in dk if d["ma"] not in _MA_DU),
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
    _n, dk, _so_lieu = _danh_gia(db, nhom_id)
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


def dong_thieu(
    db: Session,
    *,
    user,
    nhom_id: int,
    expected_version: int | None = None,
) -> dict:
    """Trưởng tổ KCS đóng THIẾU nhóm còn dở hoặc hụt mục tiêu (§13.3). Vẫn phải sạch điều kiện toàn
    vẹn (mọi điều kiện TRỪ "mọi việc xong" và "đạt đủ mục tiêu"). Chuyển sang `closed_short`, ghi
    audit sự kiện."""
    gate_truong_kcs(db, user)
    repo = SanXuatRepository(db)
    nhom = repo.nhom(nhom_id)
    if nhom is None:
        raise ValueError("Không tìm thấy nhóm thành phẩm.")
    if nhom.trang_thai in (NHOM_DONG_DU, NHOM_DONG_THIEU):
        raise ValueError("Nhóm đã đóng, không thể đóng thiếu lần nữa.")
    if expected_version is not None and expected_version != nhom.version:
        raise ValueError("Nhóm vừa được cập nhật, hãy tải lại rồi thao tác.")

    _n, dk, _so_lieu = _danh_gia(db, nhom_id)
    thieu = [d for d in dk if d["ma"] not in _MA_DU and not d["dat"]]
    if thieu:
        raise ValueError("Chưa thể đóng thiếu — " + "; ".join(d["ten"] for d in thieu) + ".")

    nhom.trang_thai = NHOM_DONG_THIEU
    nhom.version += 1
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_dong_nhom_thieu",
        target=f"san_xuat_nhom:{nhom.id}",
        detail=f"order={nhom.order_id}",
    )
    db.commit()
    return {
        "nhom_id": nhom.id,
        "order_id": nhom.order_id,
        "trang_thai": nhom.trang_thai,
        "kieu": "thieu",
        "version": nhom.version,
    }
