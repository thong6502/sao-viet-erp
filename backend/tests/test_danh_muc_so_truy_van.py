"""Các màn danh mục: số truy vấn KHÔNG được chạy theo số dòng (rà 14/09/2026).

Khuôn & khung · Thành phẩm · Vật tư khác · Giấy (+ chủng loại) · Công đoạn ·
Thiết bị & Máy móc. Đo thật lúc rà: mọi đường đọc của màn và drawer (danh sách, chi tiết, tab Nhật
ký, kiểm-tra-trước-khi-xoá, lịch sử công thức, cột Trạng thái máy, các ô chọn tham chiếu) đều ra số
truy vấn KHÔNG ĐỔI khi dữ liệu tăng gấp bốn — không có N+1.

Đa số chỗ đó không-N+1 là nhờ ĐÚNG MỘT dòng code dễ bị gỡ nhầm khi dọn dẹp: `selectinload` ở
`CongDoanRepository._base_select`, `lazy="joined"` của `KhuonBe.khach_hang`, các hook `dung_rows`
nạp tên đơn vị/khách một lượt cho cả trang. Gỡ một dòng thì không bài nào đỏ, không số nào sai trên
màn — chỉ chậm dần theo đà khai danh mục. Vì vậy khoá bằng SỐ ĐO (cùng lối
`test_bang_cong_so_truy_van.py`).
"""
from __future__ import annotations

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models.audit import AuditLog
from app.models.cong_doan import CongDoan, CongDoanMay, CongDoanVatTu
from app.models.customer import Customer
from app.models.department import Department
from app.models.khuon_be import KhuonBe
from app.models.may_thiet_bi import MayThietBi
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn

from .test_work_shifts_api import _admin_token

# Mỗi lượt dựng một tiền tố mã riêng — bài dựng dữ liệu hai đợt, mà `ma`/`code` là DUY NHẤT.
_dot = iter(range(1, 100))

DANH_SACH = [
    "/api/khuon-be?size=200",
    "/api/vat-lieu-kho/thanh-pham?size=200",
    "/api/vat-lieu-kho/vat-tu-in-an?size=200",
    "/api/vat-lieu-kho/giay?size=200",
    "/api/vat-lieu-kho/chung-loai-giay?size=200",
    "/api/cong-doan?size=200",
    "/api/may-thiet-bi?size=200",
    "/api/may-thiet-bi/trang-thai",
    "/api/cong-doan/phong-ban",
    "/api/nhom-may",
]


def _dem_truy_van(fn):
    """Chạy `fn()` và đếm số câu SQL nó bắn ra."""
    dem = {"n": 0}

    def _ghi(conn, cursor, statement, parameters, context, executemany):
        dem["n"] += 1

    event.listen(engine, "before_cursor_execute", _ghi)
    try:
        kq = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _ghi)
    return kq, dem["n"]


def _dung_danh_muc(n: int) -> dict[str, int]:
    """`n` dòng cho MỖI danh mục; mỗi công đoạn kèm 2 vật tư (tab Vật tư) + 2 máy.

    Ghi thẳng qua ORM chứ không qua API: bài này đo TẢI, dựng vài trăm dòng bằng POST chỉ tốn thời
    gian mà không khoá thêm điều gì.
    """
    d = next(_dot)
    db = SessionLocal()
    try:
        to = Department(name=f"ST To {d}", code=f"STT{d}", la_san_xuat=True)
        cl = ChungLoaiGiay(ma=f"STCL{d}", ten=f"ST CL {d}")
        khs = [Customer(code=f"STKH{d}-{i}", name=f"ST Khach {d}-{i}") for i in range(n)]
        db.add_all([to, cl, *khs])
        db.flush()
        vts = [VatTuInAn(ma=f"STVT{d}-{i}", ten=f"ST vt {d}-{i}", don_vi_gia="kg") for i in range(n)]
        mays = [MayThietBi(ma=f"STM{d}-{i}", ten=f"ST may {d}-{i}", loai_may="press_offset_sheet")
                for i in range(n)]
        db.add_all([*vts, *mays])
        for i in range(n):
            db.add(VatTuInAn(ma=f"STTP{d}-{i}", ten=f"ST tp {d}-{i}", don_vi_gia="kg",
                             la_thanh_pham=True, customer_id=khs[i].id))
            db.add(KhuonBe(ma=f"STKB{d}-{i}", ten=f"ST khuon {d}-{i}", khach_hang_id=khs[i].id))
            db.add(GiayNguyen(ma=f"STG{d}-{i}", ten=f"ST giay {d}-{i}", chung_loai_giay_id=cl.id,
                              gsm=100, don_vi_gia="kg"))
            db.add(ChungLoaiGiay(ma=f"STCL{d}-{i}", ten=f"ST CL {d}-{i}"))
        db.flush()
        cd_dau = None
        for i in range(n):
            cd = CongDoan(ma=f"STCD{d}-{i}", ten=f"ST cd {d}-{i}", nhom="finishing",
                          pricing_basis="per_finished_qty", department_ids=[to.id])
            db.add(cd)
            db.flush()
            cd_dau = cd_dau or cd
            for j in range(2):
                db.add(CongDoanVatTu(cong_doan_id=cd.id, vat_tu_id=vts[(i + j) % n].id, thu_tu=j,
                                     cong_thuc_luong="sl_vao / 1000"))
                db.add(CongDoanMay(cong_doan_id=cd.id, may_id=mays[(i + j) % n].id, thu_tu=j))
        db.commit()
        return {"cong_doan": cd_dau.id, "may_thiet_bi": mays[0].id}
    finally:
        db.close()


def _ghi_nhat_ky(target: str, so_dong: int) -> None:
    db = SessionLocal()
    try:
        db.add_all([AuditLog(actor_user_id=1, action="update", target=target, detail="đo tải")
                    for _ in range(so_dong)])
        db.commit()
    finally:
        db.close()


def _do(client, h, urls) -> dict[str, int]:
    so = {}
    for u in urls:
        r, n = _dem_truy_van(lambda: client.get(u, headers=h))
        assert r.status_code == 200, (u, r.status_code, r.text[:300])
        so[u] = n
    return so


def test_danh_sach_khong_chay_theo_so_dong(client):
    """10 dòng và 40 dòng mỗi danh mục phải tốn CÙNG một số truy vấn."""
    h = {"Authorization": f"Bearer {_admin_token(client)}"}
    _dung_danh_muc(10)
    _do(client, h, DANH_SACH)                    # lượt nháp: cấu hình/seed lười ở lần đọc đầu
    nho = _do(client, h, DANH_SACH)
    _dung_danh_muc(30)
    lon = _do(client, h, DANH_SACH)

    tang = {u: (nho[u], lon[u]) for u in DANH_SACH if lon[u] - nho[u] > 1}
    assert not tang, (
        f"thêm 30 dòng mỗi danh mục mà số truy vấn nhảy (trước, sau): {tang} — N+1 đã quay lại "
        f"(soi `selectinload` ở `CongDoanRepository._base_select`, `lazy=\"joined\"` của "
        f"`KhuonBe.khach_hang`, hook `dung_rows` của router danh mục)")


def test_drawer_khong_chay_theo_nhat_ky_va_con(client):
    """Chi tiết · tab Nhật ký · kiểm-xoá: số truy vấn không theo số dòng nhật ký.

    Lịch sử công thức của Công đoạn GỠ 18/09/2026 (mg `0324`) cùng ô công thức sản lượng ra.
    """
    h = {"Authorization": f"Bearer {_admin_token(client)}"}
    ids = _dung_danh_muc(12)
    urls = [
        f"/api/cong-doan/{ids['cong_doan']}",
        f"/api/may-thiet-bi/{ids['may_thiet_bi']}",
        f"/api/nhat-ky-danh-muc/cong_doan/{ids['cong_doan']}",
        *(f"/api/danh-muc/{loai}/{i}/kiem-xoa" for loai, i in ids.items()),
    ]
    _ghi_nhat_ky(f"cong_doan:{ids['cong_doan']}", 3)
    _do(client, h, urls)                         # lượt nháp
    nho = _do(client, h, urls)
    _ghi_nhat_ky(f"cong_doan:{ids['cong_doan']}", 40)
    lon = _do(client, h, urls)

    tang = {u: (nho[u], lon[u]) for u in urls if lon[u] - nho[u] > 1}
    assert not tang, f"số truy vấn chạy theo số dòng nhật ký (trước, sau): {tang}"
