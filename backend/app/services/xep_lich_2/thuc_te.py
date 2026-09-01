"""Lớp THỰC TẾ đè lên bàn Gantt — CHỈ ĐỌC (docs/spec-thuc-te-vs-ke-hoach.md §2.1).

Bàn xếp lịch dựng từ `xep_lich_cong_doan`; sản xuất ghi vào `san_xuat_*`. Hai tầng nối nhau bằng
cặp neo có sẵn: `lsx_cong_doan_id` và `bai_ghep_cong_doan_id`. Module này chỉ ĐỌC — máy KHÔNG tự
dời thanh (xem docstring `XepLichCongDoan`: "record-only, máy đề xuất, người quyết").

Nạp GỘP một lượt cho cả bàn, đúng tinh thần `context.py`/`routing.py` cùng cụm — bàn có vài trăm
thanh, N+1 ở đây là chết.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...models.san_xuat import (
    CV_HOAN_THANH, GOI_DANG_PHAT_HANH, SanXuatCongViec, SanXuatGoiPhatHanh,
)
from ...models.san_xuat_thuc_thi import SanXuatPhienChay
from ...models.san_xuat_san_luong import SanXuatBatch
from ..gio_xuong import gio_xuong, ve_gio_xuong


def _aware(dt: datetime | None) -> datetime | None:
    """Giờ đọc từ SQLite về naive; so hai mốc lệch tz là ném TypeError giữa lúc dựng bàn."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _phut(sau: datetime | None, truoc: datetime | None) -> int | None:
    """Số phút `sau` muộn hơn `truoc`; None nếu thiếu mốc, 0 nếu không muộn."""
    a, b = _aware(sau), _aware(truoc)
    if a is None or b is None:
        return None
    return max(int((a - b).total_seconds() // 60), 0)


def _neo(r) -> tuple[str, int] | None:
    """Khoá neo của một dòng lịch: ('lsx', lsx_cong_doan_id) hoặc ('bg', bai_ghep_cong_doan_id)."""
    lsx_cd = r["lsx_cong_doan_id"] if isinstance(r, dict) else r.lsx_cong_doan_id
    bg_cd = r["bai_ghep_cong_doan_id"] if isinstance(r, dict) else r.bai_ghep_cong_doan_id
    if bg_cd:
        return ("bg", int(bg_cd))
    if lsx_cd:
        return ("lsx", int(lsx_cd))
    return None


def nap_thuc_te(db: Session, rows: list, *, bay_gio: datetime | None = None) -> dict[int, dict]:
    """`{xep_lich_cong_doan.id: tiến-độ-thật}` cho danh sách dòng lịch đã cho.

    Dòng không có công việc tương ứng (chưa phát hành, hoặc phát hành phiên bản khác) KHÔNG có
    khoá trong map — bên gọi cứ `.get()`, không cần biết vì sao vắng.

    Khi một công đoạn có nhiều công việc (phát hành nhiều phiên bản), lấy bản `phien_ban_so` LỚN
    NHẤT: đó là phiên bản đang hiệu lực, đúng thứ tổ đang chạy. CHỈ trong phạm vi gói ĐANG PHÁT
    HÀNH — thu-hồi-rồi-phát-hành-lại đẻ gói mới bắt đầu lại từ `phien_ban_so=1` trong khi gói cũ
    (đã thu hồi) có thể từng qua vài lượt "phát hành cập nhật" nên `phien_ban_so` CAO HƠN; không
    lọc gói sẽ bám nhầm dòng đã thu hồi (tiền lệ lọc gói hiệu lực: `san_xuat_repo.py:goi_hien_tai_cua`).
    """
    if not rows:
        return {}
    neo_map: dict[tuple[str, int], list[int]] = {}
    for r in rows:
        k = _neo(r)
        if k is None:
            continue
        neo_map.setdefault(k, []).append(r["id"] if isinstance(r, dict) else r.id)
    if not neo_map:
        return {}

    lsx_cds = [i for (loai, i) in neo_map if loai == "lsx"]
    bg_cds = [i for (loai, i) in neo_map if loai == "bg"]
    dieu_kien = []
    if lsx_cds:
        dieu_kien.append(SanXuatCongViec.lsx_cong_doan_id.in_(lsx_cds))
    if bg_cds:
        dieu_kien.append(SanXuatCongViec.bai_ghep_cong_doan_id.in_(bg_cds))

    cvs = list(db.scalars(
        select(SanXuatCongViec)
        .join(SanXuatGoiPhatHanh, SanXuatGoiPhatHanh.id == SanXuatCongViec.goi_id)
        .where(SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH, or_(*dieu_kien))
        .order_by(SanXuatCongViec.phien_ban_so)
    ))
    if not cvs:
        return {}

    # Bản SAU đè bản trước ⇒ còn lại đúng phiên bản lớn nhất cho mỗi neo.
    cv_theo_neo: dict[tuple[str, int], SanXuatCongViec] = {}
    for cv in cvs:
        if cv.bai_ghep_cong_doan_id:
            cv_theo_neo[("bg", int(cv.bai_ghep_cong_doan_id))] = cv
        elif cv.lsx_cong_doan_id:
            cv_theo_neo[("lsx", int(cv.lsx_cong_doan_id))] = cv

    cv_ids = [cv.id for cv in cv_theo_neo.values()]
    sl_map = {
        cid: (float(tot or 0), float(hong or 0))
        for cid, tot, hong in db.execute(
            select(SanXuatBatch.cong_viec_id,
                   func.coalesce(func.sum(SanXuatBatch.tot), 0),
                   func.coalesce(func.sum(SanXuatBatch.hong), 0))
            .where(SanXuatBatch.cong_viec_id.in_(cv_ids))
            .group_by(SanXuatBatch.cong_viec_id)
        ).all()
    }
    moc_map = {
        cid: (bd, kt, int(con_mo or 0))
        for cid, bd, kt, con_mo in db.execute(
            select(SanXuatPhienChay.cong_viec_id,
                   func.min(SanXuatPhienChay.bat_dau),
                   func.max(SanXuatPhienChay.ket_thuc),
                   func.count().filter(SanXuatPhienChay.ket_thuc.is_(None)))
            .where(SanXuatPhienChay.cong_viec_id.in_(cv_ids))
            .group_by(SanXuatPhienChay.cong_viec_id)
        ).all()
    }

    # `du_kien_*` là GIỜ XƯỞNG (snapshot chép từ `xep_lich_cong_doan`), còn `san_xuat_phien_chay`
    # là UTC THẬT — phải quy về CÙNG một thang trước khi trừ, nếu không lệch đúng offset máy chủ
    # (VN: 7 tiếng) theo chiều khoan dung rồi bị `_phut()` kẹp thành 0. Xem `services/gio_xuong.py`.
    now = _aware(bay_gio) or gio_xuong()
    ra: dict[int, dict] = {}
    for khoa, cv in cv_theo_neo.items():
        tot, hong = sl_map.get(cv.id, (0.0, 0.0))
        bd, kt, con_mo = moc_map.get(cv.id, (None, None, 0))
        bd, kt = ve_gio_xuong(bd), ve_gio_xuong(kt)
        # XONG là do TRẠNG THÁI công việc nói, không phải do "hết phiên mở": `tam_dung()` cũng đóng
        # phiên đang mở, nên chỉ soi `con_mo` thì việc đang tạm dừng bị đọc thành đã kết thúc — thanh
        # Gantt hết đỏ đúng lúc hết ca, và `tre_ket_thuc_phut` ngừng tăng trong suốt lúc việc nằm im.
        xong = cv.trang_thai == CV_HOAN_THANH and not con_mo
        ket_thuc = kt if xong else None
        muc_tieu = float(cv.so_luong_ra) if cv.so_luong_ra is not None else None
        con_thieu = max(muc_tieu - tot, 0.0) if muc_tieu is not None else None
        phan_tram = round(tot / muc_tieu * 100, 1) if muc_tieu else None
        # Quá giờ dự kiến mà chưa đóng ⇒ đo tới BÂY GIỜ; đã đóng ⇒ đo tới mốc đóng thật.
        tre_kt = _phut(ket_thuc or now, cv.du_kien_ket_thuc) if cv.du_kien_ket_thuc else None
        thong_tin = {
            "cong_viec_id": cv.id,
            "trang_thai": cv.trang_thai,
            "bat_dau_thuc": bd,
            "ket_thuc_thuc": ket_thuc,
            "tong_tot": tot,
            "tong_hong": hong,
            "muc_tieu": muc_tieu,
            "don_vi": cv.don_vi_ra,
            "con_thieu": con_thieu,
            "phan_tram": phan_tram,
            "tre_bat_dau_phut": _phut(bd, cv.du_kien_bat_dau) if cv.du_kien_bat_dau else None,
            "tre_ket_thuc_phut": tre_kt,
        }
        for dong_id in neo_map.get(khoa, []):
            ra[dong_id] = dict(thong_tin)
    return ra
