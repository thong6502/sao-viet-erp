"""AI CÓ MẶT trong một mẻ — suy lúc đọc, không lưu (spec 18/09/2026 §7.3b).

Thay đúng một việc mà engine chia sản lượng (`phan_bo.py`, gỡ 18/09/2026) từng làm kèm: trả lời
*"mẻ này những ai làm"*. Khác ở chỗ **không có số phút và không có phép chia nào** — chốt của chủ
dự án: *"phải có danh sách người tham gia, không cần ghi tôi có mặt bao nhiêu phút đâu"* và
*"ghi nhận thế thôi, đừng có chia bất cứ gì"*.

HAI nguồn, cùng y như engine cũ đã đọc:

1. **Khoảng tham gia** giao với cửa sổ `[bat_dau, ket_thuc]` của mẻ — người được GIAO vào việc
   (§12.1). Khoảng còn mở (`ket_thuc IS NULL`) coi như kéo tới hết mẻ — thợ đang làm vẫn phải hiện
   tên. Chạm nhau đúng một mốc thì KHÔNG tính (giao rỗng), nếu không thì người vừa rời lúc mẻ bắt
   đầu cũng bị đếm vào.
2. **Thỏa thuận HỖ TRỢ CHÉO đã đủ hai bên xác nhận** cho cùng công việc, `ngay_lam_viec` = ngày
   XƯỞNG của giờ bắt đầu mẻ — người TỔ KHÁC sang giúp. Ô "Giao người" chỉ bày người trong tổ nên
   người sang giúp không bao giờ có khoảng tham gia; engine chia cũ đọc họ từ đúng thỏa thuận này
   (cùng công đoạn + cùng ngày). Bỏ nguồn này thì người đi giúp biến mất khỏi mẻ và tổ của họ không
   thấy mẻ ở mục khách (§7.3b).

Giờ ở đây là UTC THẬT (xem `gio_xuong.ve_utc_that` và mg `0298`) — cả hai phía cùng thang nên so
trực tiếp; đừng trộn giờ tường vào. Riêng NGÀY của mẻ thì theo giờ xưởng (mẻ 01:30 sáng là ngày
đó, không phải hôm trước theo UTC).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.employee import Employee
from ...models.san_xuat_phan_bo import HT_XAC_NHAN, SanXuatHoTro
from ...models.san_xuat_san_luong import SanXuatBatch
from ...models.san_xuat_thuc_thi import SanXuatKhoangThamGia
from ..gio_xuong import ve_gio_xuong

_XA = datetime(2999, 1, 1, tzinfo=timezone.utc)  # mốc thay cho khoảng còn mở


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite trả naive; so naive với aware là TypeError. Xem memory `me-gio-naive-lech-7-tieng`."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _giao(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    """Hai khoảng có phần chung THỰC SỰ (chạm một mốc không tính)."""
    return max(a0, b0) < min(a1, b1)


def ngay_cua_me(bat_dau: datetime | None) -> date | None:
    """Ngày của mẻ = ngày theo GIỜ XƯỞNG của giờ bắt đầu — khoá để khớp `ngay_lam_viec` hỗ trợ."""
    d = ve_gio_xuong(_aware(bat_dau))
    return d.date() if d is not None else None


def nguoi_theo_me(db: Session, batch_ids: set[int] | list[int]) -> dict[int, list[dict]]:
    """{batch_id → [{employee_id, ho_ten, department_id}]} — ai có mặt trong từng mẻ.

    Một query khoảng tham gia + một query hỗ trợ cho TẤT CẢ mẻ truyền vào (không N+1): tab Sản
    lượng mở một trang là hai ba chục mẻ, hỏi lẻ từng mẻ là mỗi lần mở tab bắn mấy chục query.
    """
    ids = {int(i) for i in batch_ids}
    if not ids:
        return {}
    me = list(db.scalars(select(SanXuatBatch).where(SanXuatBatch.id.in_(ids))))
    if not me:
        return {}
    cv_ids = {b.cong_viec_id for b in me}
    ngay_me = {b.id: ngay_cua_me(b.bat_dau) for b in me}
    khoang = list(db.scalars(
        select(SanXuatKhoangThamGia).where(SanXuatKhoangThamGia.cong_viec_id.in_(cv_ids))
    ))
    ho_tro = list(db.scalars(
        select(SanXuatHoTro).where(
            SanXuatHoTro.cong_viec_id.in_(cv_ids),
            SanXuatHoTro.ngay_lam_viec.in_({n for n in ngay_me.values() if n is not None}),
            SanXuatHoTro.trang_thai == HT_XAC_NHAN,
        )
    ))
    if not khoang and not ho_tro:
        return {b.id: [] for b in me}

    nv = {
        e.id: e for e in db.scalars(
            select(Employee).where(Employee.id.in_(
                {k.employee_id for k in khoang} | {h.employee_id for h in ho_tro}
            ))
        )
    }
    theo_cv: dict[int, list[SanXuatKhoangThamGia]] = {}
    for k in khoang:
        theo_cv.setdefault(k.cong_viec_id, []).append(k)
    giup: dict[tuple[int, date], list[int]] = {}
    for h in ho_tro:
        giup.setdefault((h.cong_viec_id, h.ngay_lam_viec), []).append(h.employee_id)

    def _dong(eid: int) -> dict:
        e = nv.get(eid)
        return {
            "employee_id": eid,
            "ho_ten": (getattr(e, "full_name", None) or f"#{eid}"),
            # Tổ GỐC của người — tab Sản lượng dùng để dán nhãn "(tổ bế)" cho người đi giúp.
            "department_id": getattr(e, "department_id", None),
        }

    ra: dict[int, list[dict]] = {}
    for b in me:
        b0, b1 = _aware(b.bat_dau), _aware(b.ket_thuc)
        thay: dict[int, dict] = {}
        for k in theo_cv.get(b.cong_viec_id, []):
            k0 = _aware(k.bat_dau)
            k1 = _aware(k.ket_thuc) or _XA
            if b0 is None or b1 is None or k0 is None or not _giao(k0, k1, b0, b1):
                continue
            thay.setdefault(k.employee_id, _dong(k.employee_id))
        for eid in giup.get((b.cong_viec_id, ngay_me[b.id]), []):
            thay.setdefault(eid, _dong(eid))
        ra[b.id] = sorted(thay.values(), key=lambda x: (x["ho_ten"], x["employee_id"]))
    return ra


def me_co_nguoi_cua_to(db: Session, batch_ids: set[int], to_ids: set[int]) -> set[int]:
    """Mẻ nào có ít nhất một người thuộc `to_ids` — dùng cho mục "người của tổ đi làm ở tổ khác"."""
    if not batch_ids or not to_ids:
        return set()
    theo_me = nguoi_theo_me(db, batch_ids)
    return {
        bid for bid, ds in theo_me.items()
        if any(n["department_id"] in to_ids for n in ds)
    }
