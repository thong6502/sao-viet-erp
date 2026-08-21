"""Lớp phủ Gantt Xếp lịch 2 — hàm THUẦN gộp các thanh đã xếp thành số theo NGÀY.

Không chạm DB / engine cũ: nhận danh sách khoảng (đã tz-aware) rồi trả số để UI tô lớp phủ, để cái
"râu" và nền lane tự giải thích được:
- `tai_may`      : mỗi (máy, ngày) chiếm bao nhiêu PHÚT — nhìn máy nào đang gánh nặng.
- `dinh_quan_so` : mỗi (tổ, ngày) ĐỈNH người cùng lúc — so với quân số khả dụng thì biết tổ nào quá tải.

Tách khỏi service để test §12 soi được ở MỨC HÀM (rẻ + chống hồi quy), y như `constraint.py`. Thanh
kéo qua nhiều ngày (chạy liên tục qua đêm) được CẮT theo ranh giới ngày trước khi cộng — quy đúng
phần việc rơi vào từng ngày, không tính trọn cho ngày bắt đầu.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def _ngay_bounds(d: date) -> tuple[datetime, datetime]:
    """[00:00, 24:00) của một ngày theo đồng hồ tường UTC — cùng gốc với start/finish đã aware."""
    dau = datetime.combine(d, time.min, tzinfo=timezone.utc)
    return dau, dau + timedelta(days=1)


def _cac_ngay(tu: date, den: date):
    d = tu
    while d <= den:
        yield d
        d = d + timedelta(days=1)


def tai_may(placements, tu: date, den: date) -> list[dict]:
    """Phút CHIẾM của mỗi máy theo từng ngày trong [tu, den].

    `placements` = list `(may_id, start, finish)` đã aware. Chỉ trả (máy, ngày) có phút > 0, sắp theo
    (máy, ngày) cho ổn định. Trần giờ máy/ngày là 24h (máy chạy liên tục) nên đây là số để NHÌN tải,
    không phải cửa chặn.
    """
    out: dict[tuple[int, date], float] = {}
    for may_id, start, finish in placements:
        if may_id is None or start is None or finish is None or finish <= start:
            continue
        for d in _cac_ngay(tu, den):
            d0, d1 = _ngay_bounds(d)
            phut = (min(finish, d1) - max(start, d0)).total_seconds() / 60.0
            if phut > 0:
                out[(may_id, d)] = out.get((may_id, d), 0.0) + phut
    return [
        {"may_id": k[0], "ngay": k[1], "phut_ban": round(v, 2)}
        for k, v in sorted(out.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]


def dinh_quan_so(placements, tu: date, den: date) -> dict[tuple[int, date], int]:
    """ĐỈNH số người cùng lúc của mỗi (tổ, ngày) — quét đường TRONG phạm vi từng ngày.

    `placements` = list `(department_id, start, finish, so_nguoi)` đã aware. Cắt theo ranh giới ngày
    rồi tìm đỉnh chồng lấn: tại cùng mốc, việc KẾT THÚC xử lý trước việc BẮT ĐẦU nên nối đuôi (chạm
    mép) KHÔNG cộng dồn — cùng quy ước với `constraint.vuot_quan_so_to`.
    """
    theo_to_ngay: dict[tuple[int, date], list[tuple[datetime, int]]] = {}
    for dept, start, finish, so_nguoi in placements:
        if dept is None or start is None or finish is None or finish <= start:
            continue
        for d in _cac_ngay(tu, den):
            d0, d1 = _ngay_bounds(d)
            s, f = max(start, d0), min(finish, d1)
            if f <= s:
                continue
            ev = theo_to_ngay.setdefault((dept, d), [])
            ev.append((s, int(so_nguoi)))
            ev.append((f, -int(so_nguoi)))
    out: dict[tuple[int, date], int] = {}
    for key, events in theo_to_ngay.items():
        events.sort(key=lambda e: (e[0], e[1]))
        dang_chay = dinh = 0
        for _, delta in events:
            dang_chay += delta
            dinh = max(dinh, dang_chay)
        out[key] = dinh
    return out
