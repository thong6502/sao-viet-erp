"""Màn Kế hoạch sản xuất: số truy vấn KHÔNG được chạy theo số đơn/số lệnh (rà 18/09/2026).

Màn này mở ra là bắn ba lượt đọc (`KeHoachSXPage.tsx`): `/api/lsx/hang-cho` (tab Hàng chờ),
`/api/lsx` (bảng lệnh + số trên tab) và `/api/lsx/tong-quan` (hàng ba đèn). Cả ba đều nhận cả
TRANG dữ liệu, nên chỗ nào lỡ đọc thêm theo TỪNG dòng sẽ không ai thấy trên màn — chỉ chậm dần
theo đà nhập liệu. Khoá bằng SỐ ĐO, cùng lối `test_danh_muc_so_truy_van.py`.
"""
from __future__ import annotations

from sqlalchemy import event, select

from app.services import lsx_tong_quan

# Fixtures + helper luồng thật (phiếu tính giá → báo giá → đơn → chuyển SX → lệnh).
from tests.test_xep_lich_service import (  # noqa: F401
    _don_da_chuyen_sx,
    _ptg_2_in,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _dem(db, fn):
    """Chạy `fn()` và đếm số câu SQL nó bắn ra trên CHÍNH phiên test."""
    so = {"n": 0}

    def _ghi(conn, cursor, statement, parameters, context, executemany):
        so["n"] += 1

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _ghi)
    try:
        kq = fn()
    finally:
        event.remove(bind, "before_cursor_execute", _ghi)
    return kq, so["n"]


def _them_don(db, orders, lsx_svc, admin, customer, *, so_don: int, len_lenh: bool) -> list[int]:
    """`so_don` đơn đã chuyển xuống SX; `len_lenh=True` thì lên lệnh luôn cho mọi dòng."""
    ids: list[int] = []
    for _ in range(so_don):
        d = _don_da_chuyen_sx(db, orders, admin, customer, _ptg_2_in(db))
        if len_lenh:
            line_ids = [l["order_line_id"] for l in lsx_svc.preview(d.id)["lines"]]
            ids += [x.id for x in lsx_svc.tao(order_id=d.id, order_line_ids=line_ids, actor=admin)]
    db.commit()
    return ids


def _do(db, lsx_svc, ids: list[int]) -> dict[str, int]:
    """Ba lượt đọc của màn, đo riêng từng lượt."""
    # Phiên ORM giữ sẵn đối tượng của lượt dựng dữ liệu ⇒ lazy-load im lặng, số đo đẹp giả.
    db.expire_all()
    _, n_hc = _dem(db, lambda: lsx_svc.hang_cho(page=1, size=50))
    db.expire_all()
    _, n_ds = _dem(db, lambda: lsx_svc.list_rows(page=1, size=50))
    db.expire_all()
    _, n_facet = _dem(db, lambda: lsx_svc.dem_trang_thai())
    db.expire_all()
    _, n_den = _dem(db, lambda: lsx_tong_quan.tong_quan(db, ids))
    return {"hang_cho": n_hc, "bang_lenh": n_ds, "so_tren_tab": n_facet, "ba_den": n_den}


def test_ba_luot_doc_cua_man_khong_chay_theo_so_dong(db, orders, lsx_svc, admin, customer):
    """2 đơn và 6 đơn phải tốn CÙNG một số truy vấn cho cả ba lượt đọc."""
    ids = _them_don(db, orders, lsx_svc, admin, customer, so_don=2, len_lenh=True)
    _them_don(db, orders, lsx_svc, admin, customer, so_don=2, len_lenh=False)
    _do(db, lsx_svc, ids)                       # lượt nháp: cấu hình/seed lười ở lần đọc đầu
    nho = _do(db, lsx_svc, ids)

    ids += _them_don(db, orders, lsx_svc, admin, customer, so_don=4, len_lenh=True)
    _them_don(db, orders, lsx_svc, admin, customer, so_don=4, len_lenh=False)
    lon = _do(db, lsx_svc, ids)

    tang = {k: (nho[k], lon[k]) for k in nho if lon[k] - nho[k] > 1}
    assert not tang, f"số truy vấn nhảy theo số đơn/lệnh (trước, sau): {tang} — N+1 đã quay lại"

def _san_sang(db, ids: list[int]) -> list[int]:
    """Đẩy lệnh sang `san_sang` — cửa vào tập MRP (`ke_hoach_vat_tu_service.TRANG_THAI_TINH`).

    Lệnh vừa tạo còn `nhap`, mà bảng cân đối chỉ tính lệnh đã qua cửa kế hoạch. Không đẩy thì
    phép đo ở dưới so hai lần cùng bằng 0 và bài canh xanh giả.
    """
    from app.models.lsx import TT_SAN_SANG, Lsx

    for r in db.execute(select(Lsx).where(Lsx.id.in_(ids))).scalars():
        r.trang_thai = TT_SAN_SANG
    db.commit()
    return ids


def _dem_lenh_nap(db, fn) -> int:
    """Bao nhiêu DÒNG LỆNH bị nạp về RAM trong một lượt chạy `fn()`.

    Đếm câu SQL không bắt được lỗi này: engine cân đối vật tư kéo cả xưởng về bằng ĐÚNG MỘT câu,
    nên số câu phẳng lì trong khi khối lượng công việc lớn dần theo từng lệnh mới nhập. Thứ phải
    khoá là SỐ DÒNG, và nó phải theo TRANG người dùng đang xem.
    """
    from app.repositories.lsx_repo import LsxRepository

    goc = LsxRepository.cho_mrp
    so = {"n": 0}

    def _rinh(self, **kw):
        rows = goc(self, **kw)
        so["n"] += len(rows)
        return rows

    LsxRepository.cho_mrp = _rinh
    try:
        fn()
    finally:
        LsxRepository.cho_mrp = goc
    return so["n"]


def test_ba_den_cua_mot_trang_khong_chay_theo_ca_xuong(db, orders, lsx_svc, admin, customer):
    """Hàng ba đèn hỏi ĐÚNG các lệnh của trang — khối lượng phải theo TRANG, không theo cả xưởng.

    Khác bài trên: ở đó tập hỏi lớn dần nên số đo được phép nhích theo. Ở đây tập hỏi GIỮ NGUYÊN,
    chỉ có số lệnh khác trong xưởng tăng lên. Người lật trang 1 của 500 nghìn lệnh phải trả đúng
    cái giá của người lật trang 1 của 50 lệnh — không thì phân trang chỉ là trang trí còn máy chủ
    vẫn cày cả bảng.
    """
    trang = _them_don(db, orders, lsx_svc, admin, customer, so_don=3, len_lenh=True)
    _san_sang(db, trang)
    db.expire_all()
    lsx_tong_quan.tong_quan(db, trang)                   # lượt nháp
    db.expire_all()
    nho = _dem_lenh_nap(db, lambda: lsx_tong_quan.tong_quan(db, trang))

    # Xưởng phình ra, TRANG hỏi vẫn y nguyên.
    _san_sang(db, _them_don(db, orders, lsx_svc, admin, customer, so_don=9, len_lenh=True))
    db.expire_all()
    lon = _dem_lenh_nap(db, lambda: lsx_tong_quan.tong_quan(db, trang))

    assert lon <= nho, (
        f"hỏi cùng {len(trang)} lệnh mà phải nạp {nho} → {lon} dòng lệnh khi xưởng đông thêm — "
        "hàng ba đèn đang tính theo TOÀN XƯỞNG chứ không theo trang"
    )
