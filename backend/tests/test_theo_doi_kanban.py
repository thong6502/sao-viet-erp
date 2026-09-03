"""Kanban — cột lấy ĐỘNG từ danh mục nhóm công đoạn, một LSX đúng MỘT card.

Hai luật hay bị vi phạm nhất:
  · Hard-code CTP/In/Cán/Bế/Dán/KCS. Xưởng thêm một nhóm công đoạn là bảng sai ngay, im lặng.
  · Routing song song đẻ nhiều card. Một lệnh nhiều card thì đếm "đang chạy" sai gấp đôi.

Và một luật nghiệp vụ: card tự đổi cột là do dữ liệu đổi, hệ thống KHÔNG tự bắt đầu bước sau.

--- BẢN CHỐT CỦA ĐIỀU PHỐI (Ruling C113, task-15-brief.md) ---------------------------------------
Bản plan gốc viết trục cột lên `SanXuatCongViec.nhom_cong_doan` — cột đó chỉ mang bốn mã HẰNG
TRONG CODE (`prepress|print|finishing|other`), xưởng không thêm được phần tử lúc chạy, nên
`test_cot_lay_tu_danh_muc` không viết nổi trên trục đó. Trục THẬT là danh mục `cong_doan`:

    SanXuatCongViec.step_key → LsxCongDoan.step_key → LsxCongDoan.cong_doan_id → cong_doan.id

Ba bài dưới đây viết theo bản chốt (fixture trả tuple `(lsx_id, cong_doan_id | step_key)` thay vì
so chuỗi `"can"`); hai bài còn lại (`test_song_song_chi_mot_card`, `test_lenh_nhap_khong_len_kanban`)
giữ nguyên như plan gốc.

--- VÒNG SỬA 1 (điều phối, 2026-09-03, `task-15-fix1-brief.md`) -----------------------------------
Sáu việc vá thêm, đánh dấu bằng comment "VÒNG SỬA 1 — mục X" tại đúng chỗ:
  A. Bước đại diện phải theo ĐỘ SÂU đồ thị (`bc.phu_thuoc_buoc`), không theo `thu_tu`.
  B. `meta()`/`cd_con_song` chỉ bày công đoạn CÒN DÙNG (`CongDoan.active`).
  C. `test_hoan_thanh_node_khong_tu_bat_dau_node_sau` thêm vế canh Kanban (bài gốc không chạm
     dòng nào của Task 15 — người rà chứng minh bằng cách cho `kanban()` raise vẫn PASS).
  D. Thêm bài 401/403 cho `/meta` và `/kanban` (gỡ hẳn `require_permission` mà không bài nào đỏ).
  E. Thêm bài khoá số câu SQL (chống N+1) cho `/kanban`.
  F. Thêm bài phủ nhánh "lệnh đã hoàn thành HẾT các bước" (dùng bước CUỐI làm đại diện).
  G. Nhãn cột ưu tiên `ten_hien_thi`, không phải `ten` kỹ thuật.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.db import engine
from app.models.cong_doan import CongDoan
from app.models.customer import Customer
from app.models.department import Department
from app.models.employee import Employee
from app.models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.may_thiet_bi import MayThietBi
from app.models.order import Order
from app.models.san_xuat import CV_HOAN_THANH
from app.models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password
from app.services.lenh_sx import bang_theo_doi
from app.services.san_xuat import thuc_thi

from tests.lenh_sx_fixtures import (  # noqa: F401
    BAY_GIO, _cvs, _dat_xong_luc, _dot_dong_don, _giao_nguoi, _phat_hanh_that, _chay_that,
    admin, customer, ghep_doi, lenh_nhap, lsx_svc, orders, sale_own, sess,
)


def _token_khong_quyen_theo_doi(sess) -> str:
    """Mint một user mà vai chỉ có `dashboard:own` — KHÔNG có `theo_doi_san_xuat` — dùng cho bài
    403 (mục D, vòng sửa 1). Khuôn lấy từ `test_catalog_costing_read._token_for_role`."""
    from app.security import create_access_token

    users = UserRepository(sess)
    existing = users.get_by_username("td-khong-quyen")
    if existing is not None:
        return create_access_token(str(existing.id))
    kd = DepartmentRepository(sess).get_by_name("Kinh doanh")
    roles = RoleRepository(sess)
    role = roles.create(name="R-td-khong-quyen", department_id=kd.id)
    roles.set_permission(role_id=role.id, module_key="dashboard", can_read=True, scope="own")
    u = users.create(
        username="td-khong-quyen", name="U không quyền theo dõi SX",
        password_hash=hash_password("x"),
    )
    users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
    sess.commit()
    return create_access_token(str(u.id))


def _dem_sql(fn):
    """Đếm câu SQL thật sự gửi xuống driver trong lúc chạy `fn` — khuôn `test_lenh_sx_api._dem_sql`
    (mục E, vòng sửa 1)."""
    n = 0

    def _ghi(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        nonlocal n
        n += 1

    event.listen(engine, "before_cursor_execute", _ghi)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _ghi)
    return n


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bat_dau_that(sess, admin, cv, *, ma: str, ten: str) -> None:
    """Bắt đầu một bước qua ĐÚNG đường ghi production, KHÔNG kết thúc — dựng ca "đang chạy" đứng
    yên để test dàn cảnh song song. Rút gọn của `lenh_sx_fixtures._chay_that` (bỏ đoạn `ket_thuc`);
    xem docstring ở đó cho lý do từng bước (`has_piece_work`, `ly_do_tre`, `ly_do_so_nguoi`).
    """
    to = sess.get(Department, cv.department_id)
    to.has_piece_work = True
    sess.commit()
    _giao_nguoi(sess, admin, cv, ma=ma, ten=ten)
    thuc_thi.bat_dau(
        sess, user=admin, cong_viec_id=cv.id,
        ly_do_tre="Chờ giấy về", ly_do_so_nguoi="Tổ thiếu người",
    )
    sess.expire_all()


# --- Fixture MỚI của task này ---------------------------------------------------------------------
@pytest.fixture
def cong_doan_moi(sess) -> tuple[int, str]:
    """Một dòng MỚI trong danh mục `cong_doan` — không đụng LSX/routing nào. Thêm một dòng là mọc
    một cột, đó là toàn bộ ý nghĩa của "cột lấy ĐỘNG" (Ruling C113).

    Khai CẢ `ten` (tên kỹ thuật trong danh mục) LẪN `ten_hien_thi` (tên tổ SX quen gọi) khác nhau
    để bài canh đúng luật ưu tiên của Vòng sửa 1 mục G: nhãn cột PHẢI là `ten_hien_thi` khi đã
    khai, không phải `ten` — dùng `ten` cho cả hai thì một chỗ lỡ đọc nhầm cột vẫn xanh.
    """
    cd = CongDoan(
        ma="CD-KANBAN-MOI", ten="OPP-LAM-SPECIAL-002", ten_hien_thi="Cán màng OPP đặc biệt",
        nhom="finishing",
    )
    sess.add(cd)
    sess.commit()
    return cd.id, cd.ten_hien_thi


@pytest.fixture
def lenh_in_xong_can_dang_cho(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Lệnh ĐÃ PHÁT HÀNH: bước In đã xong, bước Cán còn `released` (chưa ai bấm Bắt đầu) — card
    phải đứng ở cột của Cán, KHÔNG phải cột của In đã xong.

    `cong_doan_id` của bước Cán được LẬT SAU phát hành, đúng khuôn `lenh_thue_ngoai` ở
    `lenh_sx_fixtures.py`: routing bị khoá từ `da_phat_hanh`, nhưng cột này là SOFT-REF
    (`lsx_cong_doan.cong_doan_id`, `models/lsx.py:192`), không phải cột kế hoạch bị khoá — sửa nó
    sau phát hành là hợp lệ, không phải mẹo dựng fixture.
    """
    _dot_dong_don(sess, 5)
    cd_can = CongDoan(ma="CD-KANBAN-CAN", ten="Cán màng bóng", nhom="finishing")
    sess.add(cd_can)
    sess.commit()

    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("In", 360, 5000), ("Cán", 60, 5000)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _dat_xong_luc(sess, cvs["In"], BAY_GIO)

    buoc_can = (
        sess.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id, LsxCongDoan.ten == "Cán")
        .one()
    )
    buoc_can.cong_doan_id = cd_can.id
    sess.commit()
    return lsx_id, cd_can.id


@pytest.fixture
def lenh_hai_nhanh_cung_chay(sess, orders, lsx_svc, admin, customer) -> int:
    """LSX có HAI nhánh SONG SONG cùng chạy: CTP xong → (In ‖ Cán), hai nhánh KHÔNG phụ thuộc lẫn
    nhau và cùng `running` một lúc — Kanban phải gộp về ĐÚNG MỘT card mang ĐỦ hai chip đang chạy.
    """
    _dot_dong_don(sess, 11)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000), ("Cán", 90, 5000)],
        canh=[(0, 1), (0, 2)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _dat_xong_luc(sess, cvs["CTP"], BAY_GIO)
    _bat_dau_that(sess, admin, cvs["In"], ma="TD-HN-IN", ten="Thợ In (song song)")
    _bat_dau_that(sess, admin, cvs["Cán"], ma="TD-HN-CAN", ten="Thợ Cán (song song)")
    return lsx_id


@pytest.fixture
def lenh_in_vua_ket_thuc(sess, orders, lsx_svc, admin, customer) -> tuple[int, str, int]:
    """Lệnh vừa đóng XONG bước In bằng ĐÚNG đường production (`_chay_that` = bắt đầu + kết thúc);
    bước Cán liền sau PHẢI còn `released`. Luật canh: hệ thống KHÔNG tự bắt đầu bước sau khi bước
    trước hoàn thành — card đổi cột là chuyện người bấm nút, không phải hiệu ứng dây chuyền tự động.

    Bước Cán được gán `cong_doan_id` (lật sau phát hành, đúng khuôn `lenh_thue_ngoai`) để bài
    test (mục C, vòng sửa 1) khẳng định được ĐÚNG cột trên Kanban, không chỉ "khác cột của In".
    """
    _dot_dong_don(sess, 3)
    cd_can = CongDoan(ma="CD-KANBAN-VUA-KT", ten="Cán (vừa kết thúc In)", nhom="finishing")
    sess.add(cd_can)
    sess.commit()
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("In", 360, 5000), ("Cán", 90, 5000)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _chay_that(sess, admin, cvs["In"], ma="TD-KT-IN", ten="Thợ In (kết thúc)")
    buoc_can = (
        sess.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id, LsxCongDoan.ten == "Cán")
        .one()
    )
    buoc_can.cong_doan_id = cd_can.id
    sess.commit()
    return lsx_id, buoc_can.step_key, cd_can.id


# --- Fixture của VÒNG SỬA 1, mục A (bước đại diện phải theo ĐỘ SÂU, không theo `thu_tu`) ----------
@pytest.fixture
def lenh_nhanh_lech_do_sau(sess, orders, lsx_svc, admin, customer) -> int:
    """Phản ví dụ dựng lại đúng như brief vòng sửa 1 — mục A: `CTP(0)→In(1)→Bế(2)` và `CTP(0)→Cán(3)`
    (Cán rẽ song song ngay từ CTP). CTP + In đã xong, Bế và Cán đều còn `released`.

    Đại diện ĐÚNG là **Cán** (độ sâu 1 — sẵn sàng chạy từ lúc CTP xong, cùng lúc với In), KHÔNG
    phải **Bế** (độ sâu 2, chỉ vừa mở khoá sau khi In xong) — dù `thu_tu=2` của Bế NHỎ HƠN
    `thu_tu=3` của Cán. Con số `thu_tu` đó chỉ là VỊ TRÍ trong payload lúc lưu routing
    (`lsx_service.py:2775-3002` gán `thu_tu=i` theo thứ tự liệt kê), tách rời khỏi cạnh phụ thuộc.
    """
    _dot_dong_don(sess, 19)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000), ("Bế", 30, 5000), ("Cán", 90, 5000)],
        canh=[(0, 1), (1, 2), (0, 3)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _dat_xong_luc(sess, cvs["CTP"], BAY_GIO)
    _dat_xong_luc(sess, cvs["In"], BAY_GIO)
    return lsx_id


@pytest.fixture
def lenh_canh_cheo_lsx_khac(sess, orders, lsx_svc, admin, customer) -> int:
    """Một cạnh phụ thuộc trỏ SANG BƯỚC CỦA LSX KHÁC — tình huống HỢP LỆ trong nghiệp vụ (Ruột phụ
    thuộc Bìa cùng đơn hàng, `lsx_service.py:2993-2995` cho phép), chèn thẳng bằng ORM vì routing
    đã KHOÁ sau phát hành (không còn đi qua `LsxService.sua_routing` được nữa) — đây là bài PHÒNG
    THỦ cho tầng ĐỌC (mục A, vòng sửa 1), không phải bài canh luồng người dùng thao tác.

    Bẫy phải xử: `bc.phu_thuoc_buoc[lsx_id]` chỉ khoá theo lsx của BƯỚC SAU, nên cạnh này nằm
    trong `phu_thuoc_buoc[lsx_b]` với `buoc_truoc_id` KHÔNG thuộc tập bước của `lsx_b`. Tính độ
    sâu phải coi tiền bối ngoại lai này là độ sâu 0, KHÔNG được `KeyError`.
    """
    _dot_dong_don(sess, 21)
    lsx_a = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("Ruột - In", 200, 3000)],
    )
    lsx_b = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("Bìa - In", 100, 3000), ("Bìa - Cán", 40, 3000)],
    )
    buoc_in_a = sess.query(LsxCongDoan).filter_by(lsx_id=lsx_a, ten="Ruột - In").one()
    buoc_can_b = sess.query(LsxCongDoan).filter_by(lsx_id=lsx_b, ten="Bìa - Cán").one()
    sess.add(LsxCongDoanPhuThuoc(buoc_truoc_id=buoc_in_a.id, buoc_sau_id=buoc_can_b.id))
    sess.commit()
    return lsx_b


# --- Fixture của VÒNG SỬA 1, mục B (`meta()`/`cd_con_song` phải lọc `CongDoan.active`) -------------
@pytest.fixture
def lenh_can_cong_doan_ngung_dung(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Bước Cán trỏ vào một `cong_doan` đã NGỪNG DÙNG (`active=False`, lật đúng đường ghi thật của
    giao diện — `PATCH /api/cong-doan/{id}/active`) — card của lệnh này phải rơi cột `"khac"`, và
    cột của công đoạn ngừng dùng KHÔNG được xuất hiện trong `meta()["cot"]`.
    """
    _dot_dong_don(sess, 23)
    cd_can = CongDoan(ma="CD-KANBAN-NGUNG", ten="Cán màng ngừng dùng", nhom="finishing")
    sess.add(cd_can)
    sess.commit()
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("In", 360, 5000), ("Cán", 60, 5000)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _dat_xong_luc(sess, cvs["In"], BAY_GIO)
    buoc_can = (
        sess.query(LsxCongDoan).filter_by(lsx_id=lsx_id, ten="Cán").one()
    )
    buoc_can.cong_doan_id = cd_can.id
    cd_can.active = False
    sess.commit()
    return lsx_id, cd_can.id


# --- Năm bài test ---------------------------------------------------------------------------------
def test_cot_lay_tu_danh_muc(client, seed_credentials, cong_doan_moi):
    """`cong_doan_moi` thêm MỘT dòng vào danh mục `cong_doan` rồi trả `(id, ten_hien_thi)`.
    Thêm một công đoạn là mọc thêm một cột — đó là toàn bộ ý nghĩa của "cột lấy ĐỘNG". Nhãn phải
    là `ten_hien_thi` (Vòng sửa 1 mục G), không phải `ten` kỹ thuật — hai giá trị fixture khai
    KHÁC NHAU nên bài này đỏ ngay nếu bảng đọc nhầm cột."""
    h = _h(_tok(client, seed_credentials))
    meta = client.get("/api/theo-doi-san-xuat/meta", headers=h).json()
    cd_id, cd_ten_hien_thi = cong_doan_moi
    cot = {c["key"]: c["ten"] for c in meta["cot"]}
    assert str(cd_id) in cot
    assert cot[str(cd_id)] == cd_ten_hien_thi   # ưu tiên ten_hien_thi, không phải id/mã/ten kỹ thuật


def test_kanban_chip_mang_nhan_buoc(client, seed_credentials, sess, lenh_hai_nhanh_cung_chay):
    """Nhãn đi theo BƯỚC tới tận màn theo dõi.

    Trước 04/09/2026 bốn tab Theo dõi SX không có một chữ nào về thuê ngoài hay khuôn: gán nhãn ở
    màn Kế hoạch xong là mất dấu từ đây tới lúc lệnh xong. Bài này canh chính chỗ đứt đó — khối
    `nhan` phải ra tới JSON, không bị `KanbanChipOut` nuốt im lặng.
    """
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lenh_hai_nhanh_cung_chay)}
    cvs["Cán"].loai_buoc = "thue_ngoai"
    cvs["Cán"].nha_cung_cap = "Cơ sở Minh Phát"
    cvs["In"].khuon_json = {"ma": "KB-0001", "so_ke": "Kệ A3", "tinh_trang": "dang_dung",
                            "ngay_ve_du_kien": None}
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    chip = {c["ten"]: c
            for c in next(x for x in cards if x["lsx_id"] == lenh_hai_nhanh_cung_chay)["chip_dang_chay"]}
    assert chip["Cán"]["nhan"]["loai_buoc"] == "thue_ngoai"
    assert chip["Cán"]["nhan"]["nha_cung_cap"] == "Cơ sở Minh Phát"
    assert chip["In"]["nhan"]["khuon_ma"] == "KB-0001"
    assert chip["In"]["nhan"]["khuon_so_ke"] == "Kệ A3"
    assert chip["In"]["nhan"]["khuon_da_nhan"] is False


def test_song_song_chi_mot_card(client, seed_credentials, lenh_hai_nhanh_cung_chay):
    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    cua_lenh = [c for c in cards if c["lsx_id"] == lenh_hai_nhanh_cung_chay]
    assert len(cua_lenh) == 1
    assert len(cua_lenh[0]["chip_dang_chay"]) == 2


def test_card_nam_o_buoc_chan_som_nhat(client, seed_credentials, lenh_in_xong_can_dang_cho):
    """`lenh_in_xong_can_dang_cho` trả `(lsx_id, cong_doan_id_cua_buoc_can)`."""
    h = _h(_tok(client, seed_credentials))
    lsx_id, cd_can_id = lenh_in_xong_can_dang_cho
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    c = next(x for x in cards if x["lsx_id"] == lsx_id)
    assert c["cot"] == str(cd_can_id)


def test_hoan_thanh_node_khong_tu_bat_dau_node_sau(
    client, seed_credentials, sess, lenh_in_vua_ket_thuc
):
    """HAI vế (người rà mục C, vòng sửa 1 — bài gốc chỉ canh vế 1, không chạm dòng nào của Task 15):

    1) TIỀN ĐỀ của `services/san_xuat/thuc_thi` (có TỪ TRƯỚC task này): hoàn thành một bước KHÔNG
       tự đẩy bước sau sang `running` — tra bước SAU bằng `step_key` (neo lỏng thật), KHÔNG bằng
       `nhom_cong_doan="can"`.
    2) HỆ QUẢ trên Kanban (đây mới là phần canh Task 15): card phải đứng ở cột của Cán — đổi cột
       là do DỮ LIỆU đổi (In đã xong), còn Cán vẫn `released` chứ không bị hệ thống tự bật.

    `lenh_in_vua_ket_thuc` trả `(lsx_id, step_key_cua_buoc_can, cong_doan_id_cua_buoc_can)`.
    """
    from app.models.san_xuat import CV_DANG_CHAY, SanXuatCongViec
    lsx_id, step_key_can, cd_can_id = lenh_in_vua_ket_thuc

    # Vế 1 — tiền đề của thuc_thi.
    sau = sess.query(SanXuatCongViec).filter_by(lsx_id=lsx_id, step_key=step_key_can).one()
    assert sau.trang_thai != CV_DANG_CHAY

    # Vế 2 — hệ quả trên Kanban.
    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    c = next(x for x in cards if x["lsx_id"] == lsx_id)
    assert c["cot"] == str(cd_can_id)


def test_lenh_nhap_khong_len_kanban(client, seed_credentials, lenh_nhap):
    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    assert lenh_nhap not in {c["lsx_id"] for c in cards}


# --- VÒNG SỬA 1 — mục A: bước đại diện theo ĐỘ SÂU đồ thị, không theo `thu_tu` ---------------------
def test_card_dai_dien_theo_do_sau_khong_theo_thu_tu(
    client, seed_credentials, lenh_nhanh_lech_do_sau
):
    """Phản ví dụ của brief (`lenh_nhanh_lech_do_sau`): CTP+In xong, Bế (độ sâu 2) và Cán (độ sâu 1)
    đều còn `released`. Đại diện ĐÚNG là Cán — `thu_tu` của nó (3) LỚN hơn `thu_tu` của Bế (2), nên
    bản `thu_tu`-only sẽ chọn NHẦM Bế. Bài này phải ĐỎ trên code cũ trước khi vá."""
    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    c = next(x for x in cards if x["lsx_id"] == lenh_nhanh_lech_do_sau)
    assert c["buoc_hien_tai"] == "Cán", (
        f"đại diện phải là Cán (độ sâu 1), không phải {c['buoc_hien_tai']!r} — "
        "nghi bảng vẫn đang chọn theo `thu_tu` thay vì độ sâu đồ thị"
    )


def test_canh_tro_lsx_khac_khong_no_keyerror(
    client, seed_credentials, lenh_canh_cheo_lsx_khac
):
    """Cạnh phụ thuộc trỏ sang bước của LSX khác (hợp lệ trong nghiệp vụ) không được làm nổ khi
    tính độ sâu — tiền bối ngoại lai phải được coi là độ sâu 0, không `KeyError`."""
    h = _h(_tok(client, seed_credentials))
    resp = client.get("/api/theo-doi-san-xuat/kanban", headers=h)
    assert resp.status_code == 200, resp.text
    assert lenh_canh_cheo_lsx_khac in {c["lsx_id"] for c in resp.json()["cards"]}


# --- VÒNG SỬA 1 — mục B: `meta()`/`cd_con_song` chỉ bày công đoạn CÒN DÙNG -------------------------
def test_meta_khong_bay_cong_doan_ngung_dung(client, seed_credentials, sess):
    """Ngừng dùng một công đoạn (`active=False`) thì `key` của nó phải BIẾN MẤT khỏi
    `meta()["cot"]` — xoá một công đoạn ở giao diện là lật cờ này (`PATCH .../active`), dòng vẫn
    nằm lại trong bảng."""
    cd = CongDoan(ma="CD-KANBAN-AN", ten="Ngừng hẳn", nhom="finishing", active=False)
    sess.add(cd)
    sess.commit()
    h = _h(_tok(client, seed_credentials))
    meta = client.get("/api/theo-doi-san-xuat/meta", headers=h).json()
    assert str(cd.id) not in {c["key"] for c in meta["cot"]}


def test_bat_bien_cot_card_luon_nam_trong_meta(
    client, seed_credentials, lenh_can_cong_doan_ngung_dung
):
    """Bất biến canh thật: mọi `card["cot"]` phải nằm trong tập khoá mà `meta()["cot"]` bày ra —
    `meta()` và bộ lọc soft-ref của `kanban()` PHẢI lọc CÙNG một vị ngữ `CongDoan.active`, lệch
    nhau ở đây là card mang cột không tồn tại. Lệnh trỏ vào công đoạn đã ngừng dùng phải rơi về
    cột `"khac"` — đúng, không phải lỗi."""
    lsx_id, _cd_id_ngung = lenh_can_cong_doan_ngung_dung
    h = _h(_tok(client, seed_credentials))
    meta = client.get("/api/theo-doi-san-xuat/meta", headers=h).json()
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    khoa_meta = {c["key"] for c in meta["cot"]}
    khoa_card = {c["cot"] for c in cards}
    assert khoa_card <= khoa_meta, f"card mang cột không tồn tại trong meta: {khoa_card - khoa_meta}"
    c = next(x for x in cards if x["lsx_id"] == lsx_id)
    assert c["cot"] == "khac"


# --- VÒNG SỬA 1 — mục D: 401/403 cho HAI route mới -------------------------------------------------
def test_meta_khong_dang_nhap_401(client):
    assert client.get("/api/theo-doi-san-xuat/meta").status_code == 401


def test_kanban_khong_dang_nhap_401(client):
    assert client.get("/api/theo-doi-san-xuat/kanban").status_code == 401


def test_meta_thieu_quyen_403(client, sess):
    h = _h(_token_khong_quyen_theo_doi(sess))
    assert client.get("/api/theo-doi-san-xuat/meta", headers=h).status_code == 403


def test_kanban_thieu_quyen_403(client, sess):
    h = _h(_token_khong_quyen_theo_doi(sess))
    assert client.get("/api/theo-doi-san-xuat/kanban", headers=h).status_code == 403


# --- VÒNG SỬA 1 — mục E: khoá số câu SQL của /kanban (chống N+1) -----------------------------------
def test_kanban_khong_n_plus_1(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    """3 lệnh rồi 6 lệnh — số câu SQL của `GET /kanban` KHÔNG được tăng (khuôn
    `test_lenh_sx_api.py:940-950`). Bộ lọc `active` thêm ở mục B là MỘT điều kiện `where` trên câu
    đã có, không phải câu mới — con số phải giữ nguyên."""
    _dot_dong_don(sess, 25)
    h = _h(_tok(client, seed_credentials))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n3 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/kanban", headers=h))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n6 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/kanban", headers=h))
    assert n6 == n3, f"số câu SQL của kanban() nở theo số lệnh: {n3} → {n6}"


# --- VÒNG SỬA 1 — mục F: lệnh đã hoàn thành HẾT các bước vẫn ra ĐÚNG MỘT card ------------------------
@pytest.fixture
def lenh_da_xong_het(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Lệnh đã đóng XONG mọi bước (CTP → In → Cán, cả ba `completed`) — nhánh `elif diem_theo_cv:`
    của `_the` (dùng bước CUỐI làm đại diện) trước vòng sửa này chỉ có người đọc code, không có
    bài canh. Bước CUỐI (Cán) mang `cong_doan_id` THẬT để bài test khẳng định đúng cột, không chỉ
    "không biến mất khỏi board".
    """
    _dot_dong_don(sess, 27)
    cd_can = CongDoan(ma="CD-KANBAN-XONGHET", ten="Cán (lệnh đã xong hết)", nhom="finishing")
    sess.add(cd_can)
    sess.commit()
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000), ("Cán", 60, 5000)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _dat_xong_luc(sess, cvs["CTP"], BAY_GIO)
    _dat_xong_luc(sess, cvs["In"], BAY_GIO)
    _dat_xong_luc(sess, cvs["Cán"], BAY_GIO)
    buoc_can = sess.query(LsxCongDoan).filter_by(lsx_id=lsx_id, ten="Cán").one()
    buoc_can.cong_doan_id = cd_can.id
    sess.commit()
    return lsx_id, cd_can.id


def test_lenh_da_xong_het_van_dung_mot_card_o_buoc_cuoi(
    client, seed_credentials, lenh_da_xong_het
):
    lsx_id, cd_can_id = lenh_da_xong_het
    h = _h(_tok(client, seed_credentials))
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    cua_lenh = [c for c in cards if c["lsx_id"] == lsx_id]
    assert len(cua_lenh) == 1, "lệnh đã xong hết vẫn phải ra ĐÚNG MỘT card, không biến mất"
    assert cua_lenh[0]["cot"] == str(cd_can_id), "đại diện phải là bước CUỐI, không phải bước đầu"


# ==================================================================================================
# TASK 17a — V1 (endpoint facet `/bo-loc`) + V2 (tham số lọc của `/kanban`), Ruling C121
#
# Luật C127 áp cho MỌI bài dưới đây: docstring nói rõ PHÁ CÁI GÌ thì bài đỏ, và fixture LUÔN có ít
# nhất một phần tử KHÔNG thoả điều kiện đang canh. Tập toàn-thoả không phân biệt được "có lọc" với
# "không lọc" — đúng chỗ Task 16 mất hai vòng sửa.
# ==================================================================================================
@pytest.fixture
def hai_lenh_doi_nhau(sess, orders, lsx_svc, admin, customer) -> dict:
    """HAI lệnh đã phát hành ĐỐI NHAU trên TÁM trục lọc, cộng hai máy KHÔNG có việc nào.

    Vì sao phải đối nhau trên MỌI trục: một bộ lọc chỉ chứng minh được là nó lọc khi tập dữ liệu
    có cả phần tử THOẢ lẫn phần tử KHÔNG THOẢ. Dựng hai lệnh giống hệt nhau rồi lọc thì "lọc đúng",
    "lọc sai cột" và "không lọc gì" đều trả về cùng một tập — mọi đột biến đều xanh (C127).

        trục            lệnh A (ALPHA)                 lệnh B (BETA)
        q               ten chứa "ALPHA"               ten chứa "BETA"
        khách hàng      Công ty Bánh kẹo ALPHA         Nhà sách BETA
        máy             MAY-LOC-A (bước CTP)           MAY-LOC-B (bước CTP)
        công đoạn       CD-LOC-A (routing bước CTP)    CD-LOC-B
        nhóm công đoạn  print                          finishing
        công nhân       Thợ ALPHA                      Thợ BETA
        trạng thái việc bước In `completed`            KHÔNG bước nào `completed`
        ưu tiên         is_rush=True (Gấp)             is_rush=False (Bình thường)

    Hai máy thêm — `may_ranh` (còn dùng, KHÔNG việc nào) và `may_ngung` (đã ngừng dùng, KHÔNG việc
    nào) — là phần tử "không thoả" của bài facet Máy: `/bo-loc` phải bày cả ba loại máy, còn một
    facet dựng theo kiểu "chỉ máy nào có việc" (khuôn `danh_sach.bo_loc`) sẽ rụng đúng hai máy này.

    Lật cột sau phát hành là hợp lệ, không phải mẹo: `cong_doan_id` là SOFT-REF (khuôn
    `lenh_in_xong_can_dang_cho` ở trên), `may_id` là cột mà `thuc_thi.doi_may` ghi đè lúc chạy,
    `nhom`/`nhom_cong_doan` là bản chụp danh mục, `orders.customer_id` do màn Đơn hàng ghi.
    """
    _dot_dong_don(sess, 71)
    may_a = MayThietBi(ma="MAY-LOC-A", ten="Máy in ALPHA (lọc)", loai_may="in", active=True)
    may_b = MayThietBi(ma="MAY-LOC-B", ten="Máy in BETA (lọc)", loai_may="in", active=True)
    may_ranh = MayThietBi(ma="MAY-LOC-RANH", ten="Máy bế đang rảnh", loai_may="be", active=True)
    may_ngung = MayThietBi(
        ma="MAY-LOC-NGUNG", ten="Máy dao xén đã thanh lý", loai_may="be", active=False,
    )
    cd_a = CongDoan(ma="CD-LOC-A", ten="In ALPHA (lọc)", nhom="print")
    cd_b = CongDoan(ma="CD-LOC-B", ten="Cán BETA (lọc)", nhom="finishing")
    kh_a = Customer(code="KH-LOC-A", name="Công ty Bánh kẹo ALPHA")
    kh_b = Customer(code="KH-LOC-B", name="Nhà sách BETA")
    sess.add_all([may_a, may_b, may_ranh, may_ngung, cd_a, cd_b, kh_a, kh_b])
    sess.commit()

    ket: dict = {
        "may_a": may_a.id, "may_b": may_b.id,
        "may_ranh": may_ranh.id, "may_ngung": may_ngung.id,
        "cd_a": cd_a.id, "cd_b": cd_b.id,
        "kh_a": kh_a.id, "kh_b": kh_b.id,
    }

    for nhan, ten_lenh, may_id, cd_id, kh_id, nhom, rush in (
        ("a", "Hộp giấy ALPHA", may_a.id, cd_a.id, kh_a.id, "print", True),
        ("b", "Tờ rơi BETA", may_b.id, cd_b.id, kh_b.id, "finishing", False),
    ):
        lsx_id = _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
        lsx = sess.get(Lsx, lsx_id)
        lsx.ten = ten_lenh
        lsx.is_rush = rush
        sess.get(Order, lsx.order_id).customer_id = kh_id
        for cd in sess.query(LsxCongDoan).filter_by(lsx_id=lsx_id).all():
            cd.nhom = nhom
            if cd.ten == "CTP":
                cd.cong_doan_id = cd_id
        cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
        for cv in cvs.values():
            cv.nhom_cong_doan = nhom
        cvs["CTP"].may_id = may_id
        sess.commit()
        _giao_nguoi(
            sess, admin, cvs["CTP"],
            ma=f"THO-LOC-{nhan.upper()}", ten=f"Thợ {nhan.upper()} (lọc)",
        )
        emp = sess.query(Employee).filter_by(code=f"THO-LOC-{nhan.upper()}").one()
        ket[f"tho_{nhan}"] = emp.id
        ket[f"lsx_{nhan}"] = lsx_id
        ket[f"cv_ctp_{nhan}"] = cvs["CTP"].id

    # CHỈ lệnh A có bước `completed` — trục "trạng thái việc". Đặt SAU vòng trên để `_giao_nguoi`
    # (đòi việc chưa đóng) chạy được trên cả hai lệnh.
    cv_in_a = {cv.ten_cong_doan: cv for cv in _cvs(sess, ket["lsx_a"])}["In"]
    _dat_xong_luc(sess, cv_in_a, BAY_GIO)
    return ket


def _ids_kanban(client, h, truy_van: str = "") -> set[int]:
    d = client.get(f"/api/theo-doi-san-xuat/kanban{truy_van}", headers=h).json()
    return {c["lsx_id"] for c in d["cards"]}


# --- V1: endpoint facet riêng ---------------------------------------------------------------------
def test_bo_loc_khong_dang_nhap_401(client):
    """Đỏ nếu route `/bo-loc` quên `require_permission` (hoặc khai `Depends` không gác gì) — khi đó
    một người chưa đăng nhập đọc được danh mục máy/công nhân/khách hàng của cả xưởng."""
    assert client.get("/api/theo-doi-san-xuat/bo-loc").status_code == 401


def test_bo_loc_thieu_quyen_403(client, sess):
    """Đỏ nếu `/bo-loc` gác bằng ô quyền KHÁC `theo_doi_san_xuat` (ví dụ mượn `lenh_san_xuat` như
    `frontend/src/api/client.ts:10755-10758` từng làm): user dưới đây chỉ có `dashboard:own`, có
    quyền nào khác cũng phải bị chặn."""
    r = client.get("/api/theo-doi-san-xuat/bo-loc", headers=_h(_token_khong_quyen_theo_doi(sess)))
    assert r.status_code == 403


def test_bo_loc_may_co_ca_may_ranh_va_may_ngung_dung(
    client, seed_credentials, hai_lenh_doi_nhau,
):
    """Đỏ nếu facet Máy dựng theo kiểu "chỉ máy nào ĐANG có việc" (khuôn `danh_sach.bo_loc`) thay
    vì đọc DANH MỤC: `may_ranh` và `may_ngung` không gánh việc nào nên sẽ rụng — mà chính hai máy
    đó là nguồn LANE RỖNG của `/theo-may` (C126 mục 2). Cũng đỏ nếu cờ `ngung_dung` bị bỏ hoặc
    gán ngược (`may_ranh` còn dùng phải là False, `may_ngung` phải là True)."""
    h = _h(_tok(client, seed_credentials))
    may = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()["may"]
    theo_id = {m["id"]: m for m in may}
    for khoa in ("may_a", "may_ranh", "may_ngung"):
        assert str(hai_lenh_doi_nhau[khoa]) in theo_id, f"facet Máy thiếu {khoa}"
    assert theo_id[str(hai_lenh_doi_nhau["may_a"])]["ngung_dung"] is False
    assert theo_id[str(hai_lenh_doi_nhau["may_ranh"])]["ngung_dung"] is False
    assert theo_id[str(hai_lenh_doi_nhau["may_ngung"])]["ngung_dung"] is True


def test_bo_loc_moi_muc_co_ten_tieng_viet_khong_phai_id(
    client, seed_credentials, hai_lenh_doi_nhau,
):
    """Đỏ nếu một nhóm facet nào đó trả `ten` bằng chính mã máy/mã hằng (`"print"`, `"released"`,
    `"gap"`) — chủ dự án đã phàn nàn hai lần về đúng chuyện id lọt ra chỗ hiện chữ. Bài soi CẢ
    nhóm động (máy/công đoạn/khách/công nhân: `ten` phải khác `id`) LẪN ba nhóm hằng (so ĐÚNG
    chuỗi tiếng Việt có dấu, vì ở đó `ten != id` vẫn đúng với một bản dịch sai)."""
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()
    for nhom, muc in d.items():
        for m in muc:
            assert m["ten"] and m["ten"].strip(), f"{nhom}: mục {m['id']} không có tên"
            assert m["ten"] != m["id"], f"{nhom}: mục {m['id']} lấy chính id làm nhãn"
    assert {m["id"]: m["ten"] for m in d["nhom_cong_doan"]} == {
        "prepress": "Chế bản", "print": "In",
        "finishing": "Gia công sau in", "other": "Dịch vụ khác",
    }
    assert {m["id"]: m["ten"] for m in d["trang_thai_viec"]} == {
        "released": "Chờ làm", "running": "Đang chạy",
        "paused": "Tạm dừng", "completed": "Hoàn thành",
    }
    assert {m["id"]: m["ten"] for m in d["uu_tien"]} == {
        "gap": "Gấp", "binh_thuong": "Bình thường",
    }


def test_bo_loc_cong_nhan_chi_nguoi_dang_duoc_giao(
    client, seed_credentials, sess, admin, hai_lenh_doi_nhau,
):
    """Đỏ nếu facet Công nhân quên điều kiện `trang_thai == PC_HOAT_DONG`: `thuc_thi.go_phan_cong`
    KHÔNG xoá dòng mà lật sang `removed` để giữ lịch sử, nên bỏ điều kiện đó là ô lọc còn bày mãi
    người đã rút khỏi bước. Thợ B bị rút ngay trong bài; thợ A vẫn đang làm — phần tử "không thoả"
    và phần tử "thoả" nằm cạnh nhau."""
    pc_b = (
        sess.query(SanXuatPhanCong)
        .filter_by(
            cong_viec_id=hai_lenh_doi_nhau["cv_ctp_b"],
            employee_id=hai_lenh_doi_nhau["tho_b"],
            trang_thai=PC_HOAT_DONG,
        )
        .one()
    )
    thuc_thi.go_phan_cong(sess, user=admin, phan_cong_id=pc_b.id, ly_do="Đổi tổ")
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()
    ids = {m["id"] for m in d["cong_nhan"]}
    assert str(hai_lenh_doi_nhau["tho_a"]) in ids, "thợ đang được giao phải có trong ô lọc"
    assert str(hai_lenh_doi_nhau["tho_b"]) not in ids, "thợ ĐÃ RÚT khỏi bước vẫn còn trong ô lọc"


def test_bo_loc_khach_hang_chi_khach_co_lenh(client, seed_credentials, sess, hai_lenh_doi_nhau):
    """Đỏ nếu facet Khách hàng đọc cả sổ `customers` thay vì chỉ khách CÓ lệnh trong phạm vi —
    khi đó ô lọc bày cả khách chưa đặt in bao giờ, chọn vào là board trắng mà không ai hiểu vì sao.
    `kh_trong` dựng ngay trong bài là phần tử "không thoả"."""
    kh_trong = Customer(code="KH-LOC-TRONG", name="Khách chưa từng đặt in")
    sess.add(kh_trong)
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()
    ids = {m["id"] for m in d["khach_hang"]}
    assert str(hai_lenh_doi_nhau["kh_a"]) in ids
    assert str(hai_lenh_doi_nhau["kh_b"]) in ids
    assert str(kh_trong.id) not in ids, "ô lọc bày khách không có lệnh nào — dẫn tới ngõ cụt"


def test_bo_loc_cong_doan_trung_khung_cot_cua_meta(client, seed_credentials, sess):
    """Đỏ nếu `/bo-loc` và `/meta` đọc danh mục công đoạn bằng hai câu riêng rồi trôi lệch nhau
    (một bên lọc `active`, bên kia không; hoặc một bên lấy `ten` còn bên kia `ten_hien_thi`) —
    triệu chứng là chọn một công đoạn ở ô lọc mà board không có cột nào tên như thế. Công đoạn
    `CD-LOC-TAT` đã `active=False` là phần tử "không thoả": cả hai cửa đều phải bỏ nó."""
    tat = CongDoan(
        ma="CD-LOC-TAT", ten="Công đoạn đã ngừng dùng", ten_hien_thi="Ngừng dùng (lọc)",
        nhom="other", active=False,
    )
    con = CongDoan(
        ma="CD-LOC-CON", ten="EMBOSS-XYZ-01", ten_hien_thi="Ép nhũ nổi", nhom="finishing",
    )
    sess.add_all([tat, con])
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    cd = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()["cong_doan"]
    cot = client.get("/api/theo-doi-san-xuat/meta", headers=h).json()["cot"]
    assert [(m["id"], m["ten"]) for m in cd] == [
        (c["key"], c["ten"]) for c in cot if c["key"] != "khac"
    ]
    assert (str(con.id), "Ép nhũ nổi") in {(m["id"], m["ten"]) for m in cd}
    assert str(tat.id) not in {m["id"] for m in cd}


# --- V2: tám tham số lọc của `/kanban` ------------------------------------------------------------
def test_kanban_loc_thu_hep_ids_truoc_khi_nap(sess, hai_lenh_doi_nhau, monkeypatch):
    """Ruling C121 "lọc Ở SQL, TRƯỚC `boi_canh.nap()`". Đỏ nếu bộ lọc chuyển sang lọc SAU khi nạp
    (hoặc bỏ hẳn cho FE lọc): `nap()` khi đó vẫn nhận cả hai lệnh. Bài rình thẳng ĐỐI SỐ của
    `nap()` chứ không đo gián tiếp qua số câu SQL — số câu vẫn có thể trùng nhau."""
    ghi: dict = {}
    nap_that = bang_theo_doi.boi_canh.nap

    def rinh(db, lsx_ids):
        ghi["ids"] = list(lsx_ids)
        return nap_that(db, lsx_ids)

    monkeypatch.setattr(bang_theo_doi.boi_canh, "nap", rinh)
    bang_theo_doi.kanban(sess, sale_ids=None, loc=bang_theo_doi.BoLoc(uu_tien="gap"))
    assert hai_lenh_doi_nhau["lsx_a"] in ghi["ids"], "lệnh Gấp phải lọt vào nap()"
    assert hai_lenh_doi_nhau["lsx_b"] not in ghi["ids"], (
        "lệnh KHÔNG gấp vẫn được nạp — bộ lọc chạy SAU nap(), trái C121"
    )


def test_kanban_loc_q(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `q` của `_loc_ban` bị bỏ (trả cả hai lệnh) hoặc soi nhầm cột."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?q=ALPHA")
    assert hai_lenh_doi_nhau["lsx_a"] in ids
    assert hai_lenh_doi_nhau["lsx_b"] not in ids


def test_kanban_loc_khach_hang(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `khach_hang_id` bị bỏ, hoặc join thẳng `orders` lần hai (bảng xuất hiện hai
    lần trong cùng câu, tập trả về sai) thay vì đi qua subquery."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?khach_hang_id=%d" % hai_lenh_doi_nhau["kh_b"])
    assert hai_lenh_doi_nhau["lsx_b"] in ids
    assert hai_lenh_doi_nhau["lsx_a"] not in ids


def test_kanban_loc_may(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `may_id` bị bỏ, hoặc dùng một vị ngữ khác `danh_sach._co_buoc` mà bỏ sót vế
    công việc/ghép/routing (khi đó lệnh A — máy gắn trên CÔNG VIỆC, không trên routing — rụng)."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?may_id=%d" % hai_lenh_doi_nhau["may_a"])
    assert hai_lenh_doi_nhau["lsx_a"] in ids
    assert hai_lenh_doi_nhau["lsx_b"] not in ids


def test_kanban_loc_cong_doan(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `cong_doan_id` bị bỏ, hoặc đi tìm cột `cong_doan_id` trên
    `san_xuat_cong_viec` (bảng đó KHÔNG có cột ấy — nó neo bằng `step_key`)."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?cong_doan_id=%d" % hai_lenh_doi_nhau["cd_b"])
    assert hai_lenh_doi_nhau["lsx_b"] in ids
    assert hai_lenh_doi_nhau["lsx_a"] not in ids


def test_kanban_loc_nhom_cong_doan(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `nhom_cong_doan` bị bỏ. Lọc theo `finishing` (nhóm của lệnh B) chứ không phải
    `print`: `_dung_lenh` khai cứng `nhom="print"` cho mọi bước, nên lọc `print` còn "tình cờ"
    xanh nhờ mọi lệnh khác trong DB cũng là `print` — lọc chiều ngược mới phân biệt được."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?nhom_cong_doan=finishing")
    assert hai_lenh_doi_nhau["lsx_b"] in ids
    assert hai_lenh_doi_nhau["lsx_a"] not in ids


def test_kanban_loc_cong_nhan(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `cong_nhan_id` bị bỏ, hoặc quên `trang_thai == PC_HOAT_DONG` (khi đó người đã
    rút khỏi bước vẫn kéo lệnh về)."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?cong_nhan_id=%d" % hai_lenh_doi_nhau["tho_a"])
    assert hai_lenh_doi_nhau["lsx_a"] in ids
    assert hai_lenh_doi_nhau["lsx_b"] not in ids


def test_kanban_loc_trang_thai_viec(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `trang_thai_viec` bị bỏ. Chỉ lệnh A có bước `completed`; lệnh B thì mọi bước
    còn `released` — đây là phần tử "không thoả" bắt buộc, thiếu nó thì lọc/không lọc ra một tập."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h, "?trang_thai_viec=completed")
    assert hai_lenh_doi_nhau["lsx_a"] in ids
    assert hai_lenh_doi_nhau["lsx_b"] not in ids


def test_kanban_loc_uu_tien(client, seed_credentials, hai_lenh_doi_nhau):
    """Đỏ nếu nhánh `uu_tien` bị bỏ, hoặc hai nhánh `gap`/`binh_thuong` bị đảo. Bài soi CẢ HAI
    chiều nên một bản luôn trả `is_rush=True` cũng đỏ."""
    h = _h(_tok(client, seed_credentials))
    gap = _ids_kanban(client, h, "?uu_tien=gap")
    thuong = _ids_kanban(client, h, "?uu_tien=binh_thuong")
    assert hai_lenh_doi_nhau["lsx_a"] in gap and hai_lenh_doi_nhau["lsx_b"] not in gap
    assert hai_lenh_doi_nhau["lsx_b"] in thuong and hai_lenh_doi_nhau["lsx_a"] not in thuong


def test_kanban_khong_loc_thi_thay_ca_hai(client, seed_credentials, hai_lenh_doi_nhau):
    """TIỀN ĐỀ của tám bài trên: không tham số nào ⇒ KHÔNG lọc gì (brief: "tham số vắng mặt = không
    lọc, đừng bịa mặc định"). Đỏ nếu ai đó gán mặc định cho một ô lọc — khi đó tám bài kia vẫn có
    thể xanh mà board mặc định đã giấu mất một nửa số lệnh."""
    h = _h(_tok(client, seed_credentials))
    ids = _ids_kanban(client, h)
    assert {hai_lenh_doi_nhau["lsx_a"], hai_lenh_doi_nhau["lsx_b"]} <= ids


def test_kanban_gia_tri_la_bi_chan_422(client, seed_credentials):
    """Đỏ nếu tham số hằng khai `str` thay vì `Literal[...]`: giá trị sai chính tả sẽ lọt xuống
    service, không khớp gì và trả về board RỖNG — người dùng đọc thành "hôm nay không có lệnh nào"
    thay vì thấy lỗi. Cùng lý do `routers/lenh_san_xuat.py:45-53` khai `Literal`."""
    h = _h(_tok(client, seed_credentials))
    for tv in ("?uu_tien=khan_cap", "?trang_thai_viec=xong", "?nhom_cong_doan=in"):
        r = client.get("/api/theo-doi-san-xuat/kanban" + tv, headers=h)
        assert r.status_code == 422, f"{tv} phải bị chặn ở cửa, nhận {r.status_code}"


# ==================================================================================================
# VÒNG SỬA 1 — MỤC 3: bốn nhánh lọc đi qua CẦU BÀI GHÉP nhưng trước vòng này không bài nào canh.
#
# `may_id` · `nhom_cong_doan` (cầu ở `danh_sach._co_buoc` vế 2) · `cong_nhan_id` ·
# `trang_thai_viec` (cầu ở `bang_theo_doi._co_viec` vế 2). Fixture `hai_lenh_doi_nhau` dựng hai
# lệnh KHÔNG ghép, nên xoá vế cầu đi thì cả bốn bài vẫn xanh — đúng cái cầu đã làm sập Task 16.
#
# Hình dạng vá lỗ: bước bị bài ghép phủ KHÔNG đẻ công việc riêng (`san_xuat/snapshot.py`), cả cụm
# dùng CHUNG một công việc `lsx_id IS NULL`. Đặt giá trị cần lọc CHỈ lên công việc chung đó ⇒ với
# tới hai lệnh chỉ còn MỘT đường: qua `bai_ghep_cong_doan_map`.
# ==================================================================================================
@pytest.fixture
def ghep_bon_truc(sess, orders, lsx_svc, admin, customer, ghep_doi) -> dict:
    """Hai lệnh CHUNG một ca in ghép (`ghep_doi`: CTP riêng → In GHÉP → Đóng gói riêng), cộng MỘT
    lệnh THƯỜNG không dính bài ghép nào.

    Bốn giá trị đem lọc được đặt CHỈ lên công việc CHUNG (`cv_chung`, `lsx_id IS NULL`):

        trục              giá trị đặt trên `cv_chung`      lệnh thường (phần tử "không thoả")
        may_id            máy MAY-GHEP-C135 (mới tinh)     không máy nào
        nhom_cong_doan    "other"                          "print" (kể cả routing)
        cong_nhan_id      Thợ ca ghép                      không ai
        trang_thai_viec   completed                        released

    Ba việc dọn nền, mỗi việc chặn một đường đi TẮT khiến bài xanh giả:
      · routing (`lsx_cong_doan`) của cả ba lệnh ép `nhom="print"`, `may_id=None` — nếu không,
        vế ROUTING của `_co_buoc` (vế 3) tự bắt được và vế CẦU thành thừa;
      · công việc RIÊNG của A/B ép `nhom_cong_doan="print"`, `may_id=None` — nếu không, vế NEO
        THẲNG (vế 1) bắt được;
      · máy dựng MỚI nên không dòng nào khác trong DB trỏ tới nó.

    Lệnh thường là phần tử "không thoả" bắt buộc của C127: thiếu nó thì "lọc đúng", "lọc sai cột"
    và "không lọc gì" đều trả về cùng một tập hai lệnh.
    """
    a_id, b_id, cv_chung = ghep_doi

    _dot_dong_don(sess, 79)
    c_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500), ("In", 360, 5000)],
    )

    may = MayThietBi(
        ma="MAY-GHEP-C135", ten="Máy in ca ghép (C135)", loai_may="in", active=True,
    )
    sess.add(may)
    sess.commit()

    for lsx_id in (a_id, b_id, c_id):
        for r in sess.query(LsxCongDoan).filter_by(lsx_id=lsx_id).all():
            r.nhom = "print"
            r.may_id = None
        for cv in _cvs(sess, lsx_id):
            cv.nhom_cong_doan = "print"
            cv.may_id = None
    cv_chung.may_id = may.id
    cv_chung.nhom_cong_doan = "other"
    sess.commit()

    tho_id = _giao_nguoi(sess, admin, cv_chung, ma="THO-GHEP-C135", ten="Thợ ca ghép (C135)")
    emp_id = sess.get(SanXuatPhanCong, tho_id).employee_id
    _dat_xong_luc(sess, cv_chung, BAY_GIO)

    # Tiền đề: KHÔNG công việc riêng nào của A/B mang bốn giá trị trên — mất cầu là mất cả hai lệnh.
    for lsx_id in (a_id, b_id, c_id):
        for cv in _cvs(sess, lsx_id):
            assert cv.may_id != may.id
            assert cv.nhom_cong_doan != "other"
            assert cv.trang_thai != CV_HOAN_THANH
    return {
        "a": a_id, "b": b_id, "c": c_id,
        "may": may.id, "tho": emp_id, "cv_chung": cv_chung.id,
    }


def test_kanban_loc_may_qua_cau_bai_ghep(client, seed_credentials, ghep_bon_truc):
    """Đỏ nếu vế 2 (`bai_ghep_cong_doan_map`) bị xoá khỏi `danh_sach._co_buoc`: máy THẬT của ca in
    ghép chỉ nằm trên công việc chung (`bai_ghep_cong_doan.may_id` được chụp vào đó lúc phát hành,
    không chỗ nào ghi ngược về `lsx_cong_doan.may_id`), nên hai lệnh in ghép biến mất khỏi kết quả
    lọc đúng cái máy mà bàn đang bày tên. Lệnh thường là phần tử "không thoả"."""
    g = ghep_bon_truc
    h = _h(_tok(client, seed_credentials))
    assert _ids_kanban(client, h, "?may_id=%d" % g["may"]) == {g["a"], g["b"]}


def test_kanban_loc_nhom_cong_doan_qua_cau_bai_ghep(client, seed_credentials, ghep_bon_truc):
    """Cùng cầu, cùng hàm (`_co_buoc`) nhưng cột KHÁC — đỏ nếu vế 2 bị xoá. Hai bài tách nhau vì
    `may_id` và `nhom_cong_doan` truyền hai cặp cột khác nhau vào `_co_buoc`; một bản chỉ vá cầu
    cho một trong hai cột vẫn phải bị bắt."""
    g = ghep_bon_truc
    h = _h(_tok(client, seed_credentials))
    assert _ids_kanban(client, h, "?nhom_cong_doan=other") == {g["a"], g["b"]}


def test_kanban_loc_cong_nhan_qua_cau_bai_ghep(client, seed_credentials, ghep_bon_truc):
    """Đỏ nếu vế 2 bị xoá khỏi `bang_theo_doi._co_viec`: người đứng ca in ghép được giao vào công
    việc CHUNG, nên câu hỏi "ai đang làm lệnh này" ở khâu nặng nhất của lệnh in ghép chỉ tra được
    qua cầu. Lệnh thường không có ai được giao — phần tử "không thoả"."""
    g = ghep_bon_truc
    h = _h(_tok(client, seed_credentials))
    assert _ids_kanban(client, h, "?cong_nhan_id=%d" % g["tho"]) == {g["a"], g["b"]}


def test_kanban_loc_trang_thai_viec_qua_cau_bai_ghep(client, seed_credentials, ghep_bon_truc):
    """Cùng cầu, cùng hàm (`_co_viec`) nhưng điều kiện KHÁC — đỏ nếu vế 2 bị xoá. `completed` chỉ
    xuất hiện trên công việc chung; mọi công việc riêng của cả ba lệnh còn `released`, nên bài
    phân biệt được "lọc qua cầu" với "lọc bắt hụt rồi trả về mọi lệnh"."""
    g = ghep_bon_truc
    h = _h(_tok(client, seed_credentials))
    assert _ids_kanban(client, h, "?trang_thai_viec=completed") == {g["a"], g["b"]}


# ==================================================================================================
# VÒNG SỬA 1 — MỤC 5 (Ruling C133): cờ `co_viec` cho từng mục MÁY của `/bo-loc`.
#
# Facet `may` lấy từ DANH MỤC nên có cả máy rảnh; ở tab Kanban chọn một máy rảnh sẽ ra bảng TRẮNG,
# mà FE không tự biết máy nào có việc nếu không kéo cả bàn về — đúng thứ C121 cấm. Cờ này là GỢI Ý
# hiển thị, KHÔNG phải bộ lọc: máy rảnh vẫn phải chọn được ở tab Theo máy.
# ==================================================================================================
@pytest.fixture
def ba_may_theo_co_viec(sess, orders, lsx_svc, admin, customer) -> dict:
    """BA máy khác nhau đúng ở chỗ cờ `co_viec` phải đọc ra:

        khoá      việc gán vào máy                cờ `co_viec`
        ban       MỘT bước còn `released`         True
        xong      MỘT bước đã `completed`         False  — cờ phải xét TRẠNG THÁI
        ranh      không việc nào                  False  — cờ không phải bản sao của `ngung_dung`

    Máy `xong` là phần tử "không thoả" quan trọng nhất: một bản chỉ hỏi "có dòng công việc nào trỏ
    tới máy này không" (bỏ vế `!= completed`) vẫn xanh nếu fixture chỉ có `ban` và `ranh`.
    """
    ban = MayThietBi(ma="MAY-C133-BAN", ten="Máy in đang bận (C133)", loai_may="in", active=True)
    xong = MayThietBi(ma="MAY-C133-XONG", ten="Máy in đã xong (C133)", loai_may="in", active=True)
    ranh = MayThietBi(ma="MAY-C133-RANH", ten="Máy in đang rảnh (C133)", loai_may="in", active=True)
    sess.add_all([ban, xong, ranh])
    sess.commit()

    _dot_dong_don(sess, 81)
    ket = {"ban": ban.id, "xong": xong.id, "ranh": ranh.id}
    for nhan, may_id in (("ban", ban.id), ("xong", xong.id)):
        lsx_id = _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
        )
        cv = _cvs(sess, lsx_id)[0]
        cv.may_id = may_id
        sess.commit()
        if nhan == "xong":
            _dat_xong_luc(sess, cv, BAY_GIO)
        ket[f"cv_{nhan}"] = cv.id
    return ket


def _facet_may(client, h) -> dict:
    d = client.get("/api/theo-doi-san-xuat/bo-loc", headers=h).json()
    return {int(m["id"]): m for m in d["may"]}


def test_bo_loc_may_co_viec_theo_dung_dinh_nghia_hop_dong(
    client, seed_credentials, ba_may_theo_co_viec,
):
    """Ruling C133. Đỏ nếu cờ `co_viec` vắng mặt, hoặc tính sai một trong hai vế của định nghĩa đã
    ghi vào hợp đồng API ("ít nhất một công việc CHƯA HOÀN THÀNH thuộc lệnh ĐÃ PHÁT HÀNH trong
    phạm vi"):
      · bỏ vế `!= completed` ⇒ máy `xong` báo nhầm `True`;
      · lấy cờ bằng `not ngung_dung` (hoặc hằng `True`) ⇒ máy `ranh` báo nhầm `True`.

    Ba máy đều `active=True` nên bài không thể xanh nhờ trùng với cờ `ngung_dung`."""
    g = ba_may_theo_co_viec
    h = _h(_tok(client, seed_credentials))
    may = _facet_may(client, h)
    assert may[g["ban"]]["co_viec"] is True, "máy đang gánh việc chưa xong mà cờ báo không có việc"
    assert may[g["xong"]]["co_viec"] is False, "việc đã HOÀN THÀNH vẫn tính là máy đang có việc"
    assert may[g["ranh"]]["co_viec"] is False
    assert all(m["ngung_dung"] is False for m in (may[g[k]] for k in ("ban", "xong", "ranh")))


def test_bo_loc_may_co_viec_van_bay_may_ranh_de_chon(
    client, seed_credentials, ba_may_theo_co_viec,
):
    """C133 chốt `co_viec` là GỢI Ý, KHÔNG phải bộ lọc. Đỏ nếu ai đó "tiện tay" lọc luôn facet
    theo cờ này: máy rảnh biến mất khỏi ô chọn thì tab Theo máy hết cách hỏi "máy nào đang trống
    để nhét việc vào" — toàn bộ lý do C126 mục 2 tồn tại. Máy `ban` là phần tử "không thoả" (nó
    vẫn phải có mặt dù bài này canh chuyện máy RẢNH có mặt)."""
    g = ba_may_theo_co_viec
    h = _h(_tok(client, seed_credentials))
    may = _facet_may(client, h)
    assert g["ranh"] in may, "facet Máy đã bị lọc theo `co_viec` — máy rảnh hết chọn được"
    assert g["xong"] in may
    assert g["ban"] in may


def test_bo_loc_may_co_viec_khop_dung_lane_cua_theo_may(
    client, seed_credentials, ba_may_theo_co_viec, hai_lenh_doi_nhau,
):
    """Bất biến buộc CỜ và BÀN nói cùng một câu: `co_viec=true` ⇔ lane của máy đó trên `/theo-may`
    (KHÔNG lọc, KHÔNG cửa sổ) có ít nhất một block. Đỏ nếu cờ trôi khỏi định nghĩa đã ghi trong
    hợp đồng — ví dụ đổi sang "máy có việc trong hôm nay", hay quên vế phạm vi/trạng thái: khi đó
    FE làm mờ nhầm một máy đang gánh việc, hoặc mời người dùng chọn một máy cho ra bàn trắng.

    `hai_lenh_doi_nhau` kéo thêm bốn máy nữa (hai máy CÓ việc, một máy rảnh, một máy đã thanh lý)
    để bài chạy trên tập có cả hai phía, không chỉ ba máy của fixture chính."""
    h = _h(_tok(client, seed_credentials))
    may = _facet_may(client, h)
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    co_block = {l["may_id"] for l in lanes if l["blocks"] and l["may_id"] is not None}

    assert co_block, "tiền đề: bàn phải có ít nhất một lane CÓ block"
    assert any(not m["co_viec"] for m in may.values()), "tiền đề: phải có máy KHÔNG việc"
    lech = {mid: (m["co_viec"], mid in co_block) for mid, m in may.items()
            if m["co_viec"] != (mid in co_block)}
    assert not lech, f"cờ `co_viec` lệch với lane của /theo-may ở các máy: {lech}"


def test_bo_loc_may_co_viec_bam_pham_vi_nguoi_goi(sess, ba_may_theo_co_viec, sale_own):
    """Vế PHẠM VI của định nghĩa `co_viec` (C133) — đỏ nếu cờ đếm mọi công việc trong DB thay vì
    chỉ công việc thuộc lệnh đã phát hành TRONG PHẠM VI người gọi: một Sale scope `own` sẽ thấy
    máy báo "đang có việc" nhờ việc của người khác, rồi mở tab Kanban ra bàn trắng — đúng cái ngõ
    cụt mà cờ này sinh ra để tránh.

    Gọi thẳng tầng service vì phạm vi đến từ TOKEN, không phải tham số URL. `sale_own` là một Sale
    THẬT không sở hữu lệnh nào của fixture ⇒ phạm vi rỗng; vế `sale_ids=None` (scope `all`) là
    phần tử "không thoả" đứng cạnh, nếu không thì một bản trả cờ `False` cứng cũng xanh."""
    g = ba_may_theo_co_viec
    het = {int(m["id"]): m for m in bang_theo_doi.bo_loc(sess, sale_ids=None)["may"]}
    hep = {int(m["id"]): m for m in bang_theo_doi.bo_loc(sess, sale_ids={sale_own.id})["may"]}

    assert het[g["ban"]]["co_viec"] is True, "tiền đề: scope `all` phải thấy máy đang bận"
    assert hep[g["ban"]]["co_viec"] is False, (
        "cờ `co_viec` đếm cả việc NGOÀI phạm vi người gọi"
    )
    assert set(het) == set(hep), (
        "danh mục máy không được đổi theo phạm vi — chỉ CỜ đổi, còn khung lane/ô chọn giữ nguyên"
    )


# ==================================================================================================
# VÒNG SỬA 2 — MỤC 3: hàng rào đếm SQL cho `/bo-loc`.
#
# `/kanban`, `/theo-may`, `/theo-ca` đều đã có `_dem_sql`; `/bo-loc` thì không, dù nó là endpoint FE
# gọi MỖI LẦN mở màn. Hậu quả đo được: đột biến tính `co_viec` bằng một câu SQL cho MỖI máy vẫn để
# cả 11 bài `/bo-loc` xanh.
# ==================================================================================================
def _them_may(sess, n: int, moc: int) -> list[int]:
    """`n` máy MỚI trong danh mục, mã đánh số từ `moc` — trả về id theo thứ tự tạo."""
    ms = [
        MayThietBi(
            ma=f"MAY-SQL-{moc + i}", ten=f"Máy đếm SQL {moc + i}", loai_may="in", active=True,
        )
        for i in range(n)
    ]
    sess.add_all(ms)
    sess.commit()
    return [m.id for m in ms]


def test_bo_loc_khong_n_plus_1(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    """Số câu SQL của `GET /bo-loc` là HẰNG SỐ — không nở theo số MÁY trong danh mục, cũng không nở
    theo số LỆNH (khuôn `test_kanban_khong_n_plus_1`).

    Đỏ nếu bất kỳ facet nào chuyển sang hỏi từng dòng một: đột biến thật đã dựng là tính cờ
    `co_viec` bằng một câu `EXISTS` cho MỖI máy — trên một xưởng vài chục máy, mỗi lần mở màn là
    vài chục lượt đi DB thừa, và không bài nào trong 11 bài `/bo-loc` cũ bắt được.

    Hai chiều cùng nở giữa hai lượt đo (4 → 16 máy mới, 2 → 8 lệnh) nên bài bắt được cả N+1 theo
    máy lẫn N+1 theo lệnh. Máy phải NHIỀU: với một máy thì "một câu mỗi máy" không phân biệt được
    với hằng số (bẫy C127). Mỗi đợt thêm SONG SONG máy CÓ việc và máy RẢNH — phần tử "không thoả"
    ở đây là máy rảnh: một đột biến chỉ hỏi vòng qua các máy đang bận vẫn phải bị bắt."""
    _dot_dong_don(sess, 88)
    h = _h(_tok(client, seed_credentials))

    def them_dot(so_may: int, moc: int) -> None:
        for may_id in _them_may(sess, so_may, moc):
            lsx_id = _phat_hanh_that(
                sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
            )
            cv = _cvs(sess, lsx_id)[0]
            cv.may_id = may_id
            sess.commit()
        _them_may(sess, so_may, moc + 100)  # máy RẢNH, `co_viec=False`

    them_dot(2, 10)
    n_nho = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/bo-loc", headers=h))
    them_dot(6, 20)
    n_lon = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/bo-loc", headers=h))

    may = _facet_may(client, h)
    assert sum(1 for m in may.values() if m["co_viec"]) >= 8, "tiền đề: phải có nhiều máy CÓ việc"
    assert sum(1 for m in may.values() if not m["co_viec"]) >= 8, "tiền đề: phải có nhiều máy RẢNH"
    assert n_lon == n_nho, f"số câu SQL của bo_loc() nở theo số máy/số lệnh: {n_nho} → {n_lon}"


# --- VÒNG SỬA 2 — hàng rào cho VẾ GHÉP của vị ngữ `_cv_trong_pham_vi` -------------------------------
# Không nằm trong ba mục được giao, thêm vào vì chính lượt đột biến của vòng này lòi ra: xoá vế 2
# (cầu `bai_ghep_cong_doan_map`) khỏi `_cv_trong_pham_vi` mà TOÀN BỘ bài `/bo-loc` vẫn xanh. Bốn bài
# ghép của vòng 1 canh `_co_buoc`/`_co_viec` (đường lọc của `/kanban`), không chạm hàm này.
@pytest.fixture
def ghep_tren_may_rieng(sess, ghep_doi) -> dict:
    """Ca in GHÉP còn `released` đứng trên MỘT máy mới tinh, cạnh một máy mới tinh KHÔNG việc.

    Công việc chung mang `lsx_id IS NULL` nên chỉ với tới hai lệnh qua `bai_ghep_cong_doan_map`.
    Mọi công việc RIÊNG của A/B bị gỡ sạch `may_id` để không đường nào khác trỏ tới máy ghép — mất
    cầu là mất hẳn, không có vế NEO THẲNG đỡ hộ. Máy rảnh là phần tử "không thoả" của C127."""
    a_id, b_id, cv_chung = ghep_doi
    may = MayThietBi(ma="MAY-GHEP-C136", ten="Máy in ca ghép (C136)", loai_may="in", active=True)
    ranh = MayThietBi(ma="MAY-GHEP-C136-R", ten="Máy in rảnh (C136)", loai_may="in", active=True)
    sess.add_all([may, ranh])
    sess.commit()
    for lsx_id in (a_id, b_id):
        for cv in _cvs(sess, lsx_id):
            cv.may_id = None
    cv_chung.may_id = may.id
    sess.commit()
    assert cv_chung.lsx_id is None, "tiền đề: việc ghép phải là việc CHUNG, không neo vào lệnh nào"
    assert cv_chung.trang_thai != CV_HOAN_THANH
    return {"may": may.id, "ranh": ranh.id}


def test_bo_loc_may_co_viec_qua_cau_bai_ghep(client, seed_credentials, ghep_tren_may_rieng):
    """Vế 2 (cầu bài ghép) của `_cv_trong_pham_vi` — đỏ nếu bị xoá: khâu NẶNG nhất của lệnh in
    ghép nằm trên công việc CHUNG (`lsx_id IS NULL`), nên máy đang gánh nguyên ca in ghép sẽ bị
    báo là rảnh, FE làm mờ nó, người dùng đọc thành "máy này không có gì để xem".

    Cũng là bài canh cho `theo_may()`: từ Vòng sửa 2 nó dùng CHUNG vị ngữ này, nên mất cầu ở đây
    là máy đó mất luôn tư cách "còn nợ việc" bên bàn Theo máy."""
    g = ghep_tren_may_rieng
    h = _h(_tok(client, seed_credentials))
    may = _facet_may(client, h)
    assert may[g["may"]]["co_viec"] is True, "máy gánh nguyên ca in ghép mà cờ báo rảnh — mất cầu"
    assert may[g["ranh"]]["co_viec"] is False
