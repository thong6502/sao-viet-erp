"""Khoá chống chạy trùng (app/locks.py).

Điều quan trọng nhất phải giữ: KHÔNG có Redis thì khoá là no-op. Test và máy dev chạy 1 worker,
không có ai để tranh — nếu ở đây mà chặn thì mọi test xếp lịch/phát hành sẽ gãy vô cớ.
"""
from __future__ import annotations

from app.locks import lock


def test_khong_co_redis_thi_khoa_khong_chan_gi():
    with lock("thu-nghiem"):
        # Lấy lại đúng khoá đó ngay bên trong: no-op nên không được raise LockBusy.
        with lock("thu-nghiem"):
            pass


def test_ngoai_le_ben_trong_van_thoat_khoi_khoa():
    """Lỗi nghiệp vụ không được nuốt, và khoá phải nhả (finally) chứ không kẹt."""
    try:
        with lock("thu-nghiem-loi"):
            raise ValueError("lỗi nghiệp vụ")
    except ValueError:
        pass
    with lock("thu-nghiem-loi"):
        pass
