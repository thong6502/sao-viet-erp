"""Ba tab còn lại của màn "Theo dõi sản xuất" (Task 16) — Theo máy · Theo ca · Gantt.

  · Theo máy: mỗi máy MỘT lane, việc CHƯA gán máy vào lane riêng "Chưa xếp máy" — bỏ chúng đi là
    giấu mất đúng thứ điều độ phải xử lý.
  · Theo ca: ca lấy từ DANH MỤC `work_shifts` đang hiệu lực, không hard-code ba ca. Ca qua nửa
    đêm tính theo mốc BẮT ĐẦU ca.
  · Gantt: MỘT dòng = MỘT LỆNH (không phải một công việc), có phân trang Ở SQL, không trả toàn
    bộ lịch sử một lần.

--- BẢN CHỐT CỦA ĐIỀU PHỐI (task-16-brief.md, Ruling C115-C120) --------------------------------
Bốn bài của plan gốc đã SỬA theo bản chốt, KHÔNG chép nguyên si:

  C115 — đường dẫn: `/theo-may`, `/theo-ca` (tiếng Việt kebab, khớp router hiện có), giữ `/gantt`.
  C116 — bài ca qua nửa đêm KHÔNG được dò theo TÊN ca (`"ca 3"`) — chọn bằng CỜ `qua_nua_dem`, và
         fixture `viec_ca_dem_qua_ngay` TỰ TẠO ca qua đêm của nó, không dựa vào "Ca 3" của seed
         (seed CÓ sẵn Ca 3 qua đêm — dò theo tên vẫn "tình cờ" xanh nếu không tách bạch).
  C117 — tập ca của `/theo-ca` PHẢI TRÙNG tập ca mà Xếp lịch dùng (`XepLichService._ca_lich_may`),
         qua MỘT hàm dùng chung ở tầng repository (`AttendanceRepository.ca_lich_xuong`). Bài
         `test_tap_ca_trung_voi_xep_lich` canh đúng bất biến này.
  C118 — dòng Gantt là MỘT LỆNH. Fixture `hai_muoi_lenh` dựng 20 lệnh KHÔNG công việc/routing nào
         — hiểu "dòng = công việc" thì `total` luôn 0 và bài phân trang đỏ vĩnh viễn.
  C119 — phân trang Ở SQL (LIMIT/OFFSET ngay trên `select(Lsx.id)`), và phải canh được TRẬT TỰ:
         trang 1 và trang 2 phải RỜI NHAU, gộp lại đủ 10 mã khác nhau — đếm số dòng thôi thì một
         bản trả cùng 5 dòng cho mọi trang vẫn xanh.
  C120 — giờ chuẩn hoá qua `services/gio_xuong.py` (`lich_hien_thi`), `?ngay=` là NGÀY XƯỞNG (+7).

Cộng các bài brief bắt thêm: 401/403 cho cả BA route mới, chống N+1 cho `/theo-may` và `/gantt`
(và thêm cho `/theo-ca` dù brief không nêu tên — cùng khuôn "nạp theo LÔ" áp cho cả ba endpoint).
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.db import engine
from app.models.attendance import WorkShift
from app.models.department import Department
from app.models.lsx import Lsx
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.repositories.audit_repo import AuditLogRepository
from app.security import hash_password
from app.services.gio_xuong import lich_hien_thi
from app.services.lenh_sx import bang_theo_doi
from app.services.san_xuat import thuc_thi
from app.services.xep_lich_service import XepLichService

from tests.lenh_sx_fixtures import (  # noqa: F401
    _cvs, _dot_dong_don, _giao_nguoi, _lenh_tho, _phat_hanh_that,
    admin, customer, ghep_doi, hai_muoi_lenh, lsx_svc, orders, sess,
)


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_khong_quyen_theo_doi(sess) -> str:
    """Mint một user mà vai chỉ có `dashboard:own` — KHÔNG có `theo_doi_san_xuat` — dùng cho bài
    403. Khuôn lấy từ `test_theo_doi_kanban.py::_token_khong_quyen_theo_doi` (Task 15); bản sao
    riêng ở đây vì hai file test độc lập nhau, mỗi file tự dựng nền trên DB SQLite riêng của nó."""
    from app.security import create_access_token

    users = UserRepository(sess)
    existing = users.get_by_username("td-khong-quyen-16")
    if existing is not None:
        return create_access_token(str(existing.id))
    kd = DepartmentRepository(sess).get_by_name("Kinh doanh")
    roles = RoleRepository(sess)
    role = roles.create(name="R-td-khong-quyen-16", department_id=kd.id)
    roles.set_permission(role_id=role.id, module_key="dashboard", can_read=True, scope="own")
    u = users.create(
        username="td-khong-quyen-16", name="U không quyền theo dõi SX (16)",
        password_hash=hash_password("x"),
    )
    users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
    sess.commit()
    return create_access_token(str(u.id))


def _dem_sql(fn):
    """Đếm câu SQL thật sự gửi xuống driver trong lúc chạy `fn` — khuôn
    `test_theo_doi_kanban.py::_dem_sql` / `test_lenh_sx_api.py::_dem_sql`."""
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


def _bat_sql(fn) -> list[tuple[str, tuple]]:
    """Như `_dem_sql` nhưng GIỮ LẠI văn bản + tham số của từng câu — Vòng sửa 2 mục 4 cần soi
    CÂU LỆNH THẬT SỰ CHẠY (không phải chuỗi trong mã nguồn Python)."""
    cau: list[tuple[str, tuple]] = []

    def _ghi(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        cau.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _ghi)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _ghi)
    return cau


# --- Fixture MỚI của task này --------------------------------------------------------------------
@pytest.fixture
def viec_chua_xep_may(sess, orders, lsx_svc, admin, customer) -> int:
    """Lệnh THẬT với MỘT bước, chưa ai xếp máy (`may_id` mặc định NULL — không đường ghi nào của
    `_phat_hanh_that` chạm cột này). Trả `cong_viec_id` để canh lane "Chưa xếp máy" của
    `/theo-may`."""
    _dot_dong_don(sess, 31)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    return _cvs(sess, lsx_id)[0].id


@pytest.fixture
def ca_thu_tu(sess) -> int:
    """MỘT ca MỚI trong danh mục `work_shifts`, không đụng LSX nào — canh `/theo-ca` đọc ĐỘNG từ
    danh mục (không hard-code ba ca "Ca 1/2/3" của seed, Ruling C116's chị em)."""
    ca = WorkShift(
        name="Ca thử nghiệm C115", start_minute=9 * 60, end_minute=17 * 60,
        is_overnight=False, is_active=True, ca_san_xuat=True,
    )
    sess.add(ca)
    sess.commit()
    return ca.id


@pytest.fixture
def viec_ca_dem_qua_ngay(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Ca qua nửa đêm TỰ TẠO (Ruling C116 — KHÔNG dựa vào "Ca 3" có sẵn trong seed, dù seed cũng
    có một ca qua đêm cùng hình dạng) + một công việc đặt giờ RẠNG SÁNG NGÀY SAU (01:00, sau 0h).

    Đặt việc SAU nửa đêm (Ruling C120) mới phân biệt được "tính theo mốc BẮT ĐẦU ca" (phải thuộc
    ngày HÔM TRƯỚC, 31/08) với "tính theo ngày lịch của mốc chạy" (sẽ rơi nhầm sang 01/09 nếu cài
    đặt tính sai) — đặt việc TRƯỚC nửa đêm thì hai cách tính trùng nhau, bài không canh được gì.

    Trả `(ca_id, cong_viec_id)` — test tra ĐÚNG ca này bằng `id`, không suy đoán qua tên/vị trí.
    """
    ca = WorkShift(
        name="Ca đêm test C116", start_minute=23 * 60, end_minute=7 * 60,
        is_overnight=True, is_active=True, ca_san_xuat=True,
    )
    sess.add(ca)
    sess.commit()

    _dot_dong_don(sess, 33)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    cv = _cvs(sess, lsx_id)[0]
    # Giờ TƯỜNG dán nhãn UTC (đúng quy ước `gio_xuong.py`) — 01:00 rạng sáng 01/09/2026.
    cv.du_kien_bat_dau = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)
    # Vòng sửa 1 mục D "kèm" — set luôn mốc kết thúc (15' khớp CTP) để fixture này không vô tình
    # là ca duy nhất thiếu `du_kien_ket_thuc`, gây nhiễu bài đo dải Gantt.
    cv.du_kien_ket_thuc = datetime(2026, 9, 1, 1, 15, tzinfo=timezone.utc)
    sess.commit()
    return ca.id, cv.id


# --- Fixture của Vòng sửa 1 (task-16-fix1-brief.md) ------------------------------------------------
def _khai_ca_bo_ba(sess) -> dict[str, int]:
    """Bộ BỐN ca tối thiểu để bài canh C117 CÓ RĂNG (Vòng sửa 1 mục B) — MỘT ca sản xuất
    (`ca_san_xuat=True`), MỘT ca văn phòng (`ca_san_xuat=False`), MỘT ca ĐÃ TẮT (`is_active=False`),
    cộng MỘT ca ĐÊM (Vòng sửa 2 mục 3 / NS-2). `ca_thu_tu` cũ (một phần tử duy nhất, qua được MỌI
    cách viết lọc/không lọc) không phân biệt nổi "có lọc `ca_san_xuat`" với "không lọc", cũng không
    phân biệt "có đường lùi `or cas`" với "không có". Bản BA-ca gốc lại mù trước kiểu trôi "hậu
    lọc": một `_ca_lich_may()` vẫn gọi đúng `ca_lich_xuong()` rồi LỌC BỎ ca đêm SAU khi gọi — không
    ca đêm nào trong bộ ba thì phép lọc đó không đổi tập, cả bài hành vi lẫn bài `inspect.getsource`
    (không có `select(` mới, vẫn gọi đúng nguồn) đều mù. Ca đêm thứ tư khiến hậu lọc kiểu đó hiện
    thành hiệu tập ngay ở Pha 1. Bản sao ĐỘC LẬP của `_khai_ca_xuong` (`test_xep_lich_service.py:
    1048-1066`) — không import chéo giữa hai file test, mỗi file đứng trên DB SQLite riêng theo
    hàm."""
    sx = WorkShift(
        name="Ca SX (mục B)", start_minute=6 * 60, end_minute=14 * 60,
        is_active=True, ca_san_xuat=True,
    )
    vp = WorkShift(
        name="Ca văn phòng (mục B)", start_minute=8 * 60, end_minute=17 * 60,
        is_active=True, ca_san_xuat=False,
    )
    tat = WorkShift(
        name="Ca đã tắt (mục B)", start_minute=14 * 60, end_minute=22 * 60,
        is_active=False, ca_san_xuat=True,
    )
    dem = WorkShift(
        name="Ca đêm (Vòng sửa 2 mục 3)", start_minute=22 * 60, end_minute=6 * 60,
        is_overnight=True, is_active=True, ca_san_xuat=True,
    )
    sess.add_all([sx, vp, tat, dem])
    sess.commit()
    return {"sx": sx.id, "vp": vp.id, "tat": tat.id, "dem": dem.id}


@pytest.fixture
def viec_23h_khong_ca_nao_phu(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """Xưởng khai ĐỦ Ca 1 (06–14) + Ca 2 (14–22), KHÔNG có ca đêm — hợp lệ, xưởng chỉ chạy hai ca
    ngày là chuyện bình thường. Một việc xếp 23:00 TRÊN MÁY — Xếp lịch không hề bị ràng buộc bởi
    tập ca khi bước chạy trên máy (`xep_lich_service.py:470-487` dựng `LichXuong(..., lien_tuc=True)`
    = khung phẳng [00:00,24:00)) — canh CHẶN-1 kịch bản A / Ruling C117 (Vòng sửa 1 mục A): việc
    này KHÔNG được biến mất khỏi `/theo-ca` dù không ca nào trong danh mục phủ 23:00."""
    ca1 = WorkShift(
        name="Ca 1 (mục A)", start_minute=6 * 60, end_minute=14 * 60,
        is_active=True, ca_san_xuat=True,
    )
    ca2 = WorkShift(
        name="Ca 2 (mục A)", start_minute=14 * 60, end_minute=22 * 60,
        is_active=True, ca_san_xuat=True,
    )
    sess.add_all([ca1, ca2])
    sess.commit()

    _dot_dong_don(sess, 51)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    cv = _cvs(sess, lsx_id)[0]
    cv.du_kien_bat_dau = datetime(2026, 8, 31, 23, 0, tzinfo=timezone.utc)
    cv.du_kien_ket_thuc = datetime(2026, 8, 31, 23, 15, tzinfo=timezone.utc)
    sess.commit()
    return ca1.id, cv.id


@pytest.fixture
def lenh_gantt_thu_tu_xao_tron(sess, admin, customer) -> None:
    """6 lệnh — hạn rải xa nhau, mã KHÔNG cùng thứ tự bảng chữ cái với hạn, CHÈN vào DB theo thứ tự
    XÁO TRỘN (không theo hạn, không theo mã) + một lệnh KHÔNG hạn chen giữa. Canh Ruling C119
    (Vòng sửa 1 mục C.1): `hai_muoi_lenh` cũ chèn ĐÚNG theo thứ tự hạn tăng dần nên rowid/thứ tự
    chèn vô tình trùng thứ tự đúng — bỏ `order_by` hay đảo chiều đều không đỏ được trên fixture đó.
    Xáo trộn thứ tự chèn mới phân biệt được "có ORDER BY đúng" với "trùng hợp rowid"."""
    _dot_dong_don(sess, 53)
    thu_tu_chen = [
        ("LSX-XT-D", date(2026, 9, 5)),
        ("LSX-XT-KHONG-HAN", None),
        ("LSX-XT-B", date(2026, 9, 2)),
        ("LSX-XT-E", date(2026, 9, 6)),
        ("LSX-XT-A", date(2026, 9, 1)),
        ("LSX-XT-C", date(2026, 9, 3)),
    ]
    for ma, han in thu_tu_chen:
        _lenh_tho(sess, ma=ma, sale_user_id=admin.id, customer_id=customer.id, han_sx=han)


@pytest.fixture
def lenh_buoc_cuoi_thieu_moc_ket_thuc(sess, orders, lsx_svc, admin, customer) -> tuple[int, str]:
    """Lệnh 2 bước — bước 2 (In) CHỈ có `du_kien_bat_dau`, THIẾU `du_kien_ket_thuc` (hình dạng THẬT:
    bước 1 đã xếp xong lịch, bước 2 mới xếp được mốc bắt đầu — `tien_do.py:99` và
    `danh_sach.py:246-250` đều rẽ nhánh cho ca này). `lech_buoc={1: 6h}` đẩy mốc bắt đầu bước 2 ra
    XA HẲN mốc kết thúc bước 1 (không chỉ liền kề) — thiếu khoảng CÁCH THẬT thì bug cũ (`max()` trên
    tập mốc kết thúc, bỏ sót bước chưa có kết thúc) TÌNH CỜ ra đúng giá trị đúng (mốc bắt đầu bước 2
    == mốc kết thúc bước 1 khi không lệch), bài sẽ không đỏ được (Vòng sửa 1 mục D / NS-1)."""
    _dot_dong_don(sess, 59)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        lech_buoc={1: timedelta(hours=6)},
    )
    cv_cuoi = _cvs(sess, lsx_id)[1]
    moc_bat_dau_buoc_cuoi = lich_hien_thi(cv_cuoi.du_kien_bat_dau).isoformat()
    cv_cuoi.du_kien_ket_thuc = None
    sess.commit()
    return lsx_id, moc_bat_dau_buoc_cuoi


@pytest.fixture
def viec_tren_may_ngung_dung(sess, orders, lsx_svc, admin, customer) -> tuple[int, int]:
    """MỘT máy `active=False` (đã ngừng dùng/thanh lý, mg 0202) đang còn gánh MỘT việc chưa xong —
    canh Vòng sửa 1 mục H: lane của máy này KHÔNG được biến mất khỏi `/theo-may`, chỉ đánh dấu
    `ngung_dung=True` — máy đã tắt vẫn còn nợ điều độ, giấu lane đi mới là mất dấu việc đó."""
    may = MayThietBi(
        ma="MAY-H-NGUNG-DUNG", ten="Máy đã thanh lý (test mục H)", loai_may="in", active=False,
    )
    sess.add(may)
    sess.flush()

    _dot_dong_don(sess, 61)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    cv = _cvs(sess, lsx_id)[0]
    cv.may_id = may.id
    sess.commit()
    return may.id, cv.id


# --- Bốn bài của plan, viết theo bản chốt ---------------------------------------------------------
def test_viec_chua_gan_may_co_lane_rieng(client, seed_credentials, viec_chua_xep_may):
    h = _h(_tok(client, seed_credentials))
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    chua = next(l for l in lanes if l["may_id"] is None)
    assert viec_chua_xep_may in {b["cong_viec_id"] for b in chua["blocks"]}


def test_ca_lay_tu_danh_muc(client, seed_credentials, ca_thu_tu):
    h = _h(_tok(client, seed_credentials))
    cas = client.get("/api/theo-doi-san-xuat/theo-ca", headers=h).json()["ca"]
    assert ca_thu_tu in {c["id"] for c in cas}


def test_ca_qua_nua_dem_tinh_theo_moc_bat_dau(client, seed_credentials, viec_ca_dem_qua_ngay):
    ca_id, cv_id = viec_ca_dem_qua_ngay
    h = _h(_tok(client, seed_credentials))
    cas = client.get(
        "/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h
    ).json()["ca"]
    dem = next(c for c in cas if c["id"] == ca_id)
    assert dem["qua_nua_dem"] is True, "tiền đề: ca dựng trong fixture phải mang cờ qua_nua_dem"
    assert cv_id in {v["cong_viec_id"] for v in dem["viec"]}, (
        "việc chạy 01:00 (01/09) phải thuộc ca BẮT ĐẦU tối 31/08, không phải rơi ra ngoài / "
        "nhảy sang ca của ngày 01/09"
    )


def test_theo_ca_viec_khong_ca_nao_phu_roi_vao_rong_ngoai_ca(
    client, seed_credentials, viec_23h_khong_ca_nao_phu,
):
    """CHẶN-1 kịch bản A (Vòng sửa 1 mục A) — hai ca ngày (06-14, 14-22) không phủ 23:00, việc chạy
    trên máy vẫn được Xếp lịch xếp giờ đó (không bị ràng buộc bởi tập ca). Bản vá phải hứng việc này
    vào rổ "Ngoài ca" (`id=None`) thay vì để nó biến mất khỏi mọi cột."""
    ca1_id, cv_id = viec_23h_khong_ca_nao_phu
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h).json()

    ngoai = next(c for c in d["ca"] if c["id"] is None)
    assert ngoai["ten"] == "Ngoài ca"
    assert cv_id in {v["cong_viec_id"] for v in ngoai["viec"]}
    ca1 = next(c for c in d["ca"] if c["id"] == ca1_id)
    assert cv_id not in {v["cong_viec_id"] for v in ca1["viec"]}, (
        "việc 23:00 không thuộc Ca 1 (06-14) — không được lẫn vào ca thật nào"
    )

    # Bất biến brief đòi thêm cho bài 1 — tập cong_viec_id /theo-ca thấy PHẢI ⊇ tập /theo-may thấy.
    # Vòng sửa 2 mục 7 (GN-2): sau mục I, đây KHÔNG còn là bất biến TOÀN CỤC — /theo-ca chỉ thấy
    # việc của MỘT ngày (`?ngay=`), còn /theo-may thấy MỌI việc chưa xong bất kể ngày (một lệnh xếp
    # 05/09 nằm trong /theo-may nhưng không thể nằm trong /theo-ca?ngay=31/08). Khẳng định dưới đây
    # chỉ ĐÚNG vì tiền đề của bài này: fixture `viec_23h_khong_ca_nao_phu` chỉ dựng ĐÚNG MỘT việc,
    # và việc đó rơi vào ĐÚNG ngày đang hỏi (31/08) — nên toàn bộ những gì /theo-may thấy ở đây cũng
    # thuộc ngày 31/08, và phải thấy lại được ở /theo-ca. Đừng đọc đây thành "⊇ với MỌI bối cảnh".
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    tu_theo_may = {b["cong_viec_id"] for l in lanes for b in l["blocks"]}
    tu_theo_ca = {v["cong_viec_id"] for c in d["ca"] for v in c["viec"]}
    assert tu_theo_may <= tu_theo_ca, (
        f"/theo-may thấy {tu_theo_may - tu_theo_ca} mà /theo-ca không thấy — CHẶN-1 vẫn còn"
    )


def test_theo_ca_work_shifts_rong_van_co_rong_ngoai_ca(client, seed_credentials, viec_chua_xep_may):
    """CHẶN-1 kịch bản B (Vòng sửa 1 mục A) — danh mục `work_shifts` RỖNG hoàn toàn (tiền đề mặc
    định của test env, `SEED_DEMO=false`). Xếp lịch vẫn dựng lịch được nhờ fallback "8h phẳng
    [08:00,16:00)" (`xep_lich_service.py:153`); `/theo-ca` (trước vá) trả `ca=[]` tuyệt đối vì
    không có ca nào để dò `_ca_cua_moc` — bản vá phải còn rổ "Ngoài ca"."""
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h).json()
    assert d["ca"] != [], "work_shifts rỗng không được làm /theo-ca trả về rỗng tuyệt đối"
    ngoai = next(c for c in d["ca"] if c["id"] is None)
    assert viec_chua_xep_may in {v["cong_viec_id"] for v in ngoai["viec"]}


def test_theo_ca_thay_viec_ghep_qua_cau_bai_ghep(client, seed_credentials, sess, ghep_doi):
    """Vòng sửa 2 mục 1 (CHẶN) — nhánh UNION `qua_ghep` của mục I (`bang_theo_doi.py:607-620`,
    docstring "VÒNG SỬA 1 MỤC I") trước vòng này KHÔNG có bài canh riêng. Người rà soát đo được nó
    LOAD-BEARING: bỏ nhánh đó thì một lệnh mà việc DUY NHẤT trong cửa sổ ngày là việc GHÉP
    (`SanXuatCongViec.lsx_id IS NULL`, phủ lệnh qua `BaiGhepCongDoanMap`) rớt khỏi `ids` và biến
    mất khỏi `/theo-ca` — mà 25/25 bài cũ vẫn xanh, vì không bài nào trước đây dựng đúng hình dạng
    "lệnh không còn việc RIÊNG nào trong ngày, chỉ còn việc ghép".

    Xoá mốc của MỌI công việc RIÊNG (CTP/Đóng gói, `lsx_id` là chính lệnh) của CẢ HAI lệnh trong
    `ghep_doi` — chỉ còn `cv_chung` (bước In ghép, `lsx_id IS NULL`) mang mốc trong cửa sổ ngày."""
    a_id, b_id, cv_chung = ghep_doi
    for lsx_id in (a_id, b_id):
        for cv in _cvs(sess, lsx_id):
            cv.du_kien_bat_dau = None
            cv.du_kien_ket_thuc = None
    cv_chung.du_kien_bat_dau = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
    cv_chung.du_kien_ket_thuc = datetime(2026, 8, 31, 11, 0, tzinfo=timezone.utc)
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h).json()
    thay = {v["cong_viec_id"] for c in d["ca"] for v in c["viec"]}
    assert cv_chung.id in thay, (
        "việc ghép (lsx_id IS NULL, phủ qua BaiGhepCongDoanMap) biến mất khỏi /theo-ca — "
        "nhánh UNION qua_ghep mất tác dụng"
    )


def test_theo_ca_va_theo_may_dung_chung_mot_nhan_chua_xep_may(
    client, seed_credentials, viec_ca_dem_qua_ngay,
):
    """Vòng sửa 1 mục G — trước bản vá, `/theo-ca` luôn trả `may=None` cho CẢ "chưa xếp máy" lẫn
    "máy đã xoá", trong khi `/theo-may` phân biệt hai thứ bằng hai nhãn tiếng Việt riêng. Việc
    chưa gán máy phải hiện CÙNG một nhãn ở cả hai tab, không được để hai tab nói hai chuyện."""
    ca_id, cv_id = viec_ca_dem_qua_ngay
    h = _h(_tok(client, seed_credentials))
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    nhan_chua_xep_may = next(l for l in lanes if l["may_id"] is None)["ten"]

    cas = client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h).json()["ca"]
    dem = next(c for c in cas if c["id"] == ca_id)
    viec = next(v for v in dem["viec"] if v["cong_viec_id"] == cv_id)
    assert viec["may_id"] is None
    assert viec["may"] == nhan_chua_xep_may, (
        f"/theo-ca nói {viec['may']!r}, /theo-may nói {nhan_chua_xep_may!r} — hai tab trôi nhau"
    )


def test_theo_may_ngung_dung_van_co_lane_nhung_danh_dau(
    client, seed_credentials, viec_tren_may_ngung_dung,
):
    """Vòng sửa 1 mục H — máy `active=False` không được biến mất khỏi `/theo-may`; lane vẫn hiện,
    chỉ thêm cờ `ngung_dung=True` để FE biết mà cảnh báo điều độ viên."""
    may_id, cv_id = viec_tren_may_ngung_dung
    h = _h(_tok(client, seed_credentials))
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    lane = next((l for l in lanes if l["may_id"] == may_id), None)
    assert lane is not None, "máy ngừng dùng không được biến mất khỏi /theo-may"
    assert lane["ngung_dung"] is True
    assert cv_id in {b["cong_viec_id"] for b in lane["blocks"]}


def test_gantt_ket_thuc_khong_som_hon_buoc_cuoi_moi_bat_dau(
    client, seed_credentials, lenh_buoc_cuoi_thieu_moc_ket_thuc,
):
    """Vòng sửa 1 mục D / NS-1 — bước CUỐI của routing có `du_kien_bat_dau` nhưng THIẾU
    `du_kien_ket_thuc` (đã xếp giờ bắt đầu, chưa xếp xong khoảng chạy). Dải Gantt của lệnh không
    được kết thúc SỚM HƠN mốc bắt đầu của chính bước cuối đó — nếu không, thanh Gantt giấu mất phần
    việc đã biết chắc chắn còn đang chạy."""
    lsx_id, moc_bat_dau_buoc_cuoi = lenh_buoc_cuoi_thieu_moc_ket_thuc
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=50", headers=h).json()
    dong = next(r for r in d["rows"] if r["lsx_id"] == lsx_id)
    assert dong["du_kien_ket_thuc"] is not None, (
        "bước cuối thiếu mốc kết thúc không được làm cả dòng mất luôn dải thời gian"
    )
    assert dong["du_kien_ket_thuc"] >= moc_bat_dau_buoc_cuoi, (
        f"Gantt kết thúc {dong['du_kien_ket_thuc']} trong khi bước cuối mới bắt đầu "
        f"{moc_bat_dau_buoc_cuoi} — giấu mất phần việc đã xếp"
    )


def test_gantt_thu_tu_dung_han_khong_phai_thu_tu_chen(
    client, seed_credentials, lenh_gantt_thu_tu_xao_tron,
):
    """Ruling C119 / Vòng sửa 1 mục C.1 — sắp theo HẠN thật (lệnh không hạn xếp CUỐI), không phải
    trùng hợp theo thứ tự chèn DB. Fixture chèn xáo trộn (D, không-hạn, B, E, A, C) nên chỉ có
    ORDER BY đúng mới ra được thứ tự trang dưới đây."""
    h = _h(_tok(client, seed_credentials))
    trang1 = client.get(
        "/api/theo-doi-san-xuat/gantt?page=1&page_size=3", headers=h
    ).json()
    trang2 = client.get(
        "/api/theo-doi-san-xuat/gantt?page=2&page_size=3", headers=h
    ).json()
    assert [r["ma"] for r in trang1["rows"]] == ["LSX-XT-A", "LSX-XT-B", "LSX-XT-C"]
    assert [r["ma"] for r in trang2["rows"]] == ["LSX-XT-D", "LSX-XT-E", "LSX-XT-KHONG-HAN"]


def test_gantt_cat_trang_o_sql_khong_phai_python():
    """Canh HÌNH DẠNG MÃ NGUỒN — CHỈ chặn đúng hình dạng `ids[a:b]` (Vòng sửa 1 mục C.2, siết chú
    thích ở Vòng sửa 2 mục 4). Người rà soát vòng 2 đo được bài này qua mặt được bằng hai mẹo tầm
    thường ngay trong SOURCE: giữ một `.offset(0).limit(10_000)` TRANG TRÍ (không thật sự gắn vào
    câu cắt trang) để qua vế `.limit(`/`.offset(`, và đổi tên biến `ids` thành thứ khác (vd `tat_ca`)
    để qua vế `"ids["` — bản SAI (kéo cả phạm vi về Python rồi cắt lát) vẫn xanh. Bài này KHÔNG
    chặn được kiểu né đó — khoá THẬT nằm ở `test_gantt_cat_trang_bang_sql_that_su_chay` bên dưới
    (soi SQL thật sự chạy, không soi chuỗi mã nguồn). Giữ bài này lại vì nó vẫn rẻ và vẫn chặn được
    hình dạng ngây thơ nhất; đừng đọc tên bài mà tưởng nó chặn được mọi cách cắt ở Python."""
    src = inspect.getsource(bang_theo_doi.gantt)
    assert ".limit(" in src and ".offset(" in src, "phải cắt trang bằng LIMIT/OFFSET của SQL"
    assert "ids[" not in src, "không được cắt trang bằng slice Python trên danh sách id"


def test_gantt_cat_trang_bang_sql_that_su_chay(client, seed_credentials, hai_muoi_lenh):
    """Vòng sửa 2 mục 4 — khoá C119 bằng SQL THẬT SỰ GỬI XUỐNG DRIVER, không quét chuỗi mã nguồn.
    `page=3&page_size=2` ⇒ `limit=2`, `offset=(3-1)*2=4` — cố ý chọn hai giá trị KHÁC NHAU để không
    thể lẫn lộn thứ tự bind. Tìm ĐÚNG câu SELECT chỉ chọn cột `lsx.id` (phân biệt với câu tải đủ cột
    `lsx` bên trong `boi_canh.nap()`, câu đó lọc bằng `WHERE lsx.id IN (...)`, không có LIMIT/OFFSET)
    — đây là câu QUYẾT ĐỊNH trang nào được trả, khẳng định nó mang `LIMIT`/`OFFSET` và tham số bind
    ĐÚNG BẰNG `page_size`/`offset`, không chỉ đếm số câu hay quét xem chữ "LIMIT" có xuất hiện đâu đó
    trong câu (một `.limit(10_000)` trang trí gắn lên đúng câu này vẫn chứa chữ "LIMIT" — chỉ giá
    trị bind mới vạch trần nó không phải `page_size` thật)."""
    h = _h(_tok(client, seed_credentials))
    cau = _bat_sql(
        lambda: client.get("/api/theo-doi-san-xuat/gantt?page=3&page_size=2", headers=h)
    )
    cau_id = [
        (s, p) for s, p in cau
        if s.split("FROM", 1)[0].strip() == "SELECT lsx.id"
    ]
    assert cau_id, "không thấy câu SELECT lsx.id nào — không xác định được câu quyết định trang"
    s, p = cau_id[0]
    assert "LIMIT" in s and "OFFSET" in s, f"câu chọn lsx.id thiếu LIMIT/OFFSET thật sự: {s!r}"
    assert p[-2:] == (2, 4), (
        f"LIMIT/OFFSET bind sai giá trị (phải là page_size=2, offset=4) — bind thật: {p[-2:]!r}. "
        "Một bản kéo cả phạm vi rồi cắt ở Python, hoặc giữ .limit(10_000) trang trí, sẽ lộ ở đây."
    )


def test_gantt_co_phan_trang(client, seed_credentials, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=5", headers=h).json()
    assert len(d["rows"]) == 5
    assert d["total"] >= 20

    # Ruling C119 — không chỉ đếm số dòng: trang 1/2 phải RỜI NHAU và gộp đủ 10 mã khác nhau.
    # Một bản cài đặt trả cùng 5 dòng cho mọi trang vẫn qua được hai khẳng định phía trên.
    ma_trang_1 = {r["ma"] for r in d["rows"]}
    d2 = client.get("/api/theo-doi-san-xuat/gantt?page=2&page_size=5", headers=h).json()
    ma_trang_2 = {r["ma"] for r in d2["rows"]}
    assert ma_trang_1.isdisjoint(ma_trang_2), "trang 1 và trang 2 trùng dòng — phân trang sai"
    assert len(ma_trang_1 | ma_trang_2) == 10

    # Vòng sửa 2 mục 6 (GN-1) — `hai_muoi_lenh` dựng 20 lệnh KHÔNG công việc/routing nào (Ruling
    # C118). Tập mốc rỗng ⇒ dải thời gian phải để None ("chưa đủ dữ liệu thì nói chưa đủ dữ liệu"),
    # KHÔNG được bịa mốc — hành vi này đã ĐÚNG từ trước, chỉ chưa ai canh.
    for r in d["rows"]:
        assert r["du_kien_bat_dau"] is None, f"lệnh {r['ma']} không có việc nào nhưng lại có mốc bắt đầu"
        assert r["du_kien_ket_thuc"] is None, f"lệnh {r['ma']} không có việc nào nhưng lại có mốc kết thúc"


# --- C117 — tập ca của /theo-ca PHẢI TRÙNG tập ca mà Xếp lịch dùng --------------------------------
def test_tap_ca_trung_voi_xep_lich(sess):
    """`AttendanceRepository.ca_lich_xuong()` phải là NGUỒN DUY NHẤT cho cả hai bàn (Ruling C117).

    Vòng sửa 1 mục B — `ca_thu_tu` cũ (MỘT ca duy nhất, qua được MỌI cách viết lọc/không lọc) không
    phân biệt được ba cách viết khác nhau đều "trông đúng". Bộ BỐN ca (`_khai_ca_bo_ba`) có răng cho
    CẢ hai đột biến brief nêu tên, chạy qua HAI PHA trên cùng một bộ ca:

      · Pha 1 — HAI ca tick `ca_san_xuat=True` (`sx` + `dem`): phải lấy ĐÚNG hai ca đó, không lẫn
        ca văn phòng `vp` (bắt được đột biến "bỏ lọc `ca_san_xuat`" — thiếu lọc sẽ trả cả ba ca
        đang dùng). Ca `dem` (Vòng sửa 2 mục 3 / NS-2) là ca ĐÊM DUY NHẤT trong bộ — thiếu nó thì
        một `_ca_lich_may()` gọi đúng `ca_lich_xuong()` nhưng LỌC BỎ ca đêm SAU khi gọi vẫn qua được
        pha này (không có ca đêm nào để lọc mất), đúng kiểu trôi "hậu lọc" mà mục 3 sinh ra để chặn.
      · Pha 2 — tắt nốt `ca_san_xuat` của CẢ `sx` LẪN `dem`: KHÔNG còn ca nào tick ⇒ đường lùi
        `or cas` phải trả HẾT ca ĐANG DÙNG (`sx` + `vp` + `dem`, không có `tat` vì đã
        `is_active=False`), không phải rỗng (bắt được đột biến "bỏ đường lùi `or cas`" — thiếu
        đường lùi sẽ trả tập rỗng).
    """
    bo_ba = _khai_ca_bo_ba(sess)
    xl = XepLichService(sess, XepLichRepository(sess), AuditLogRepository(sess))

    tu_repo = {s.id for s in AttendanceRepository(sess).ca_lich_xuong()}
    tu_xep_lich = {s.id for s in xl._ca_lich_may()}
    assert tu_repo, "tiền đề: bộ ca phải tạo được ít nhất một ca ca_san_xuat=True + active"
    assert tu_repo == {bo_ba["sx"], bo_ba["dem"]}, f"lọc ca_san_xuat sai (pha 1) — repo trả {tu_repo}"
    assert tu_repo == tu_xep_lich, f"tập ca lệch nhau (pha 1) — repo={tu_repo}, xep_lich={tu_xep_lich}"

    sx_obj = sess.get(WorkShift, bo_ba["sx"])
    sx_obj.ca_san_xuat = False
    dem_obj = sess.get(WorkShift, bo_ba["dem"])
    dem_obj.ca_san_xuat = False
    sess.commit()

    tu_repo2 = {s.id for s in AttendanceRepository(sess).ca_lich_xuong()}
    tu_xep_lich2 = {s.id for s in xl._ca_lich_may()}
    assert tu_repo2 == {bo_ba["sx"], bo_ba["vp"], bo_ba["dem"]}, (
        f"đường lùi 'or cas' sai (pha 2) — repo trả {tu_repo2}"
    )
    assert tu_repo2 == tu_xep_lich2, (
        f"tập ca lệch nhau (pha 2) — repo={tu_repo2}, xep_lich={tu_xep_lich2}"
    )


def test_ca_lich_may_mot_nguon_duy_nhat():
    """Khoá bất biến "MỘT nguồn" bằng MÃ NGUỒN (Vòng sửa 1 mục B.2) — bài hành vi ở trên không canh
    nổi việc mai sau ai đó chép một bản TƯƠNG ĐƯƠNG hành vi vào `_ca_lich_may()` thay vì gọi lại
    `ca_lich_xuong()`: lúc đó mọi bài hành vi đều xanh, nhưng hai nơi bắt đầu trôi ra hai hướng độc
    lập — đúng kịch bản C117 sinh ra để chặn. Khuôn đã dùng trong repo:
    `test_xep_lich_service.py:1036-1043`."""
    src = inspect.getsource(XepLichService._ca_lich_may)
    # Chỉ soi THÂN hàm thật thi hành — chữ ký (`-> list[WorkShift]`) và docstring (kể chuyện "trước
    # đây tự `select(WorkShift)...`") đều nhắc hai chữ này TRONG VĂN XUÔI, soi cả `src` sẽ bắt oan.
    than_ham = src.split('"""', 2)[-1]
    assert "ca_lich_xuong" in than_ham, "_ca_lich_may() phải GỌI LẠI AttendanceRepository.ca_lich_xuong()"
    assert "select(" not in than_ham, "_ca_lich_may() không được tự SELECT — phải đi qua ca_lich_xuong()"


# --- 401/403 cho CẢ BA route mới -------------------------------------------------------------------
def test_theo_may_khong_dang_nhap_401(client):
    assert client.get("/api/theo-doi-san-xuat/theo-may").status_code == 401


def test_theo_ca_khong_dang_nhap_401(client):
    assert client.get("/api/theo-doi-san-xuat/theo-ca").status_code == 401


def test_gantt_khong_dang_nhap_401(client):
    assert client.get("/api/theo-doi-san-xuat/gantt").status_code == 401


def test_theo_may_thieu_quyen_403(client, sess):
    h = _h(_token_khong_quyen_theo_doi(sess))
    assert client.get("/api/theo-doi-san-xuat/theo-may", headers=h).status_code == 403


def test_theo_ca_thieu_quyen_403(client, sess):
    h = _h(_token_khong_quyen_theo_doi(sess))
    assert client.get("/api/theo-doi-san-xuat/theo-ca", headers=h).status_code == 403


def test_gantt_thieu_quyen_403(client, sess):
    h = _h(_token_khong_quyen_theo_doi(sess))
    assert client.get("/api/theo-doi-san-xuat/gantt", headers=h).status_code == 403


# --- Chống N+1: nạp theo LÔ, không lặp theo lệnh ----------------------------------------------------
def test_theo_may_khong_n_plus_1(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    _dot_dong_don(sess, 35)
    h = _h(_tok(client, seed_credentials))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n3 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/theo-may", headers=h))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n6 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/theo-may", headers=h))
    assert n6 == n3, f"số câu SQL của /theo-may nở theo số lệnh: {n3} → {n6}"


def test_theo_ca_khong_n_plus_1(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    _dot_dong_don(sess, 37)
    h = _h(_tok(client, seed_credentials))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n3 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h))
    for _ in range(3):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n6 = _dem_sql(lambda: client.get("/api/theo-doi-san-xuat/theo-ca?ngay=2026-08-31", headers=h))
    assert n6 == n3, f"số câu SQL của /theo-ca nở theo số lệnh: {n3} → {n6}"


def test_gantt_khong_n_plus_1_truc_tong(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    """Trục TỔNG (Vòng sửa 1 mục C.3) — TĂNG số LỆNH ngoài trang, `page_size` CỐ ĐỊNH và LUÔN nhỏ
    hơn tổng số lệnh ở cả hai pha (số DÒNG trả về không đổi, luôn 5) — cô lập đúng MỘT trục: có
    vòng lặp nào chạy trên TOÀN TẬP thay vì trên đúng trang không. Bài `test_gantt_khong_n_plus_1`
    cũ (3→8 lệnh, cùng lúc page_size=5 vượt tổng ở pha 1 rồi không vượt ở pha 2) lẫn cả trục TRANG
    vào phép đo — số DÒNG trả về đổi 3→5 mới là thứ thật sự phơi ra đột biến, không phải tổng lệnh
    tăng. Tách riêng để mỗi bài canh ĐÚNG MỘT bất biến."""
    _dot_dong_don(sess, 55)
    h = _h(_tok(client, seed_credentials))
    for _ in range(6):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n6 = _dem_sql(
        lambda: client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=5", headers=h)
    )
    for _ in range(4):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n10 = _dem_sql(
        lambda: client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=5", headers=h)
    )
    assert n10 == n6, f"số câu SQL của /gantt nở theo TỔNG số lệnh dù cùng page_size: {n6} → {n10}"


def test_gantt_khong_n_plus_1_truc_trang(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    """Trục TRANG (Vòng sửa 1 mục C.3) — CÙNG một tập lệnh (dựng đủ MỘT lần), TĂNG `page_size` (số
    DÒNG trả về, 3 → 8): đây mới là N+1 THẬT của một endpoint đã phân trang — một câu SQL nhét
    trong vòng lặp dựng `rows` nở đúng theo số DÒNG trả về, không theo tổng số lệnh (trục TỔNG ở
    trên không bắt được ca này khi số dòng trên trang không đổi giữa hai lần đo)."""
    _dot_dong_don(sess, 57)
    h = _h(_tok(client, seed_credentials))
    for _ in range(8):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n_it = _dem_sql(
        lambda: client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=3", headers=h)
    )
    n_nhieu = _dem_sql(
        lambda: client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=8", headers=h)
    )
    assert n_nhieu == n_it, f"số câu SQL của /gantt nở theo số DÒNG trả về: {n_it} → {n_nhieu}"


# --- Vòng sửa 1 mục J — page/page_size vô lý phải 422, không được âm thầm kẹp về biên -------------
def test_gantt_page_0_422(client, seed_credentials):
    h = _h(_tok(client, seed_credentials))
    assert client.get("/api/theo-doi-san-xuat/gantt?page=0", headers=h).status_code == 422


def test_gantt_page_size_qua_han_422(client, seed_credentials):
    h = _h(_tok(client, seed_credentials))
    assert client.get("/api/theo-doi-san-xuat/gantt?page_size=999", headers=h).status_code == 422


# ==================================================================================================
# TASK 17a — V3 (cửa sổ thời gian + lane cho máy rảnh, C126) và V4 (block mang cặp `(lsx_id, ma)`,
# C123) của `/theo-may`.
#
# Luật C127: mỗi bài nói rõ PHÁ CÁI GÌ thì nó đỏ, và fixture LUÔN có phần tử KHÔNG thoả điều kiện
# đang canh. Riêng cửa sổ thời gian còn thêm một ràng buộc của brief: "cửa sổ SQL chỉ được NỚI,
# KHÔNG được THU HẸP" — nên `viec_quanh_cua_so` đặt việc ĐÚNG BIÊN (23:00 của ngày `den`), đúng chỗ
# Task 16 từng cắt mất ở `/theo-ca`.
# ==================================================================================================
NGAY_CUA_SO = date(2026, 9, 10)


@pytest.fixture
def viec_quanh_cua_so(sess, orders, lsx_svc, admin, customer) -> dict:
    """MỘT lệnh với SÁU công việc rải quanh cửa sổ một ngày (10/09/2026), cộng MỘT lệnh nằm TRỌN
    ngoài cửa sổ.

        khoá           mốc kế hoạch                      trong cửa sổ 10/09?
        bien_dau       10/09 00:00 → 00:30               CÓ (biên trái)
        bien_cuoi      10/09 23:00 → 23:30               CÓ (biên phải — chỗ Task 16 cắt mất)
        vat_qua        05/09 08:00 → 15/09 17:00         CÓ (chồng lấn, không "bắt đầu trong")
        chua_xep       NULL → NULL                       CÓ (chưa xếp giờ thì luôn phải hiện)
        hom_truoc      09/09 08:00 → 09:00               KHÔNG
        hom_sau        11/09 00:30 → 01:00               KHÔNG

    Bốn phần tử "có" và hai phần tử "không" nằm trong CÙNG một lệnh là cố ý: câu SQL chọn LỆNH
    (lệnh này thoả nên lọt qua), còn phép chọn BLOCK mới phân biệt sáu việc — bài test vì thế đo
    được đúng tầng Python mà không bị tầng SQL che. Lệnh thứ hai (`lsx_ngoai`, mọi việc 20/09) là
    phần tử "không thoả" ở tầng SQL.
    """
    _dot_dong_don(sess, 73)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[(ten, 30, 500) for ten in
              ("Biên đầu", "Biên cuối", "Vắt qua", "Chưa xếp", "Hôm trước", "Hôm sau")],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    moc = {
        "Biên đầu": (datetime(2026, 9, 10, 0, 0), datetime(2026, 9, 10, 0, 30)),
        "Biên cuối": (datetime(2026, 9, 10, 23, 0), datetime(2026, 9, 10, 23, 30)),
        "Vắt qua": (datetime(2026, 9, 5, 8, 0), datetime(2026, 9, 15, 17, 0)),
        "Chưa xếp": (None, None),
        "Hôm trước": (datetime(2026, 9, 9, 8, 0), datetime(2026, 9, 9, 9, 0)),
        "Hôm sau": (datetime(2026, 9, 11, 0, 30), datetime(2026, 9, 11, 1, 0)),
    }
    for ten, (bd, kt) in moc.items():
        cvs[ten].du_kien_bat_dau = bd.replace(tzinfo=timezone.utc) if bd else None
        cvs[ten].du_kien_ket_thuc = kt.replace(tzinfo=timezone.utc) if kt else None
    sess.commit()

    lsx_ngoai = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("Ngoài cửa sổ", 60, 500)],
    )
    cv_ngoai = _cvs(sess, lsx_ngoai)[0]
    cv_ngoai.du_kien_bat_dau = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    cv_ngoai.du_kien_ket_thuc = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    sess.commit()

    ket = {ten: cvs[ten].id for ten in moc}
    ket["lsx"] = lsx_id
    ket["lsx_ngoai"] = lsx_ngoai
    ket["cv_ngoai"] = cv_ngoai.id
    return ket


@pytest.fixture
def hai_may_khong_viec(sess) -> tuple[int, int]:
    """MỘT máy CÒN DÙNG và MỘT máy ĐÃ NGỪNG DÙNG, cả hai KHÔNG gánh việc nào.

    Máy CÒN DÙNG là nguồn của lane RỖNG (C126 mục 2). Máy NGỪNG DÙNG ở đây là phần tử "không
    thoả" của chính luật đó sau Vòng sửa 1 mục 4 (Ruling C132): ngừng dùng + không việc ⇒ THÔI đẻ
    lane. Cặp máy ngừng dùng CÓ việc / KHÔNG việc nằm ở `hai_may_ngung_dung` bên dưới.

    Phần tử "không thoả" còn lại là các máy CÓ việc do fixture khác dựng: bài chỉ xanh khi lane
    mọc ra từ DANH MỤC chứ không mọc ra từ dữ liệu công việc."""
    ranh = MayThietBi(
        ma="MAY-C126-RANH", ten="Máy bế đang rảnh (C126)", loai_may="be", active=True,
    )
    ngung = MayThietBi(
        ma="MAY-C126-NGUNG", ten="Máy xén đã thanh lý (C126)", loai_may="be", active=False,
    )
    sess.add_all([ranh, ngung])
    sess.commit()
    return ranh.id, ngung.id


def _blocks_theo_may(client, h, truy_van: str = "") -> set[int]:
    d = client.get("/api/theo-doi-san-xuat/theo-may" + truy_van, headers=h).json()
    return {b["cong_viec_id"] for l in d["lanes"] for b in l["blocks"]}


# --- V3: cửa sổ thời gian -------------------------------------------------------------------------
def test_theo_may_cua_so_khong_cat_viec_bien_cuoi_ngay(
    client, seed_credentials, viec_quanh_cua_so,
):
    """BÀI BIÊN mà brief C126 bắt buộc phải có. Đỏ nếu biên phải của cửa sổ lấy thẳng `den 00:00`
    thay vì `den + 1 ngày` (`_cua_so_ban_may`): việc 23:00 của CHÍNH NGÀY người dùng chọn bị cắt —
    đúng lỗi Task 16 đã dính ở `/theo-ca` và tốn một vòng sửa vì không fixture nào đặt dữ liệu ở
    biên. Cũng đỏ nếu biên trái bị lệch (`Biên đầu` 00:00 rơi ra ngoài).

    Hai phần tử "không thoả" (`Hôm trước` 09/09, `Hôm sau` 11/09) khẳng định bài vẫn phân biệt
    được: một bản BỎ HẲN cửa sổ (trả mọi việc) cũng phải đỏ, không chỉ bản cắt quá tay."""
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h, "?tu=2026-09-10&den=2026-09-10")
    assert viec_quanh_cua_so["Biên cuối"] in thay, (
        "việc 23:00 ngày 10/09 bị cắt khỏi cửa sổ 10/09 — biên phải thu hẹp thay vì nới"
    )
    assert viec_quanh_cua_so["Biên đầu"] in thay
    assert viec_quanh_cua_so["Hôm trước"] not in thay
    assert viec_quanh_cua_so["Hôm sau"] not in thay


def test_theo_may_viec_vat_qua_cua_so_van_hien(client, seed_credentials, viec_quanh_cua_so):
    """Đỏ nếu cửa sổ hỏi kiểu "bắt đầu TRONG khoảng" (`du_kien_bat_dau BETWEEN tu AND den`) thay
    vì CHỒNG LẤN: ca in dài 05/09 → 15/09 đang chiếm máy suốt ngày 10/09 sẽ biến mất khỏi bàn điều
    độ đúng lúc nó bận nhất. `Hôm trước`/`Hôm sau` là phần tử "không thoả" của bài."""
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h, "?tu=2026-09-10&den=2026-09-10")
    assert viec_quanh_cua_so["Vắt qua"] in thay, "việc vắt qua cửa sổ bị bỏ — cửa sổ không chồng lấn"
    assert viec_quanh_cua_so["Hôm sau"] not in thay


def test_theo_may_viec_chua_xep_gio_luon_hien_trong_moi_cua_so(
    client, seed_credentials, viec_quanh_cua_so,
):
    """Đỏ nếu nhánh `du_kien_bat_dau IS NULL` bị bỏ khỏi `_cham_cua_so`/`_cham_cua_so_sql`: việc
    CHƯA xếp giờ chính là thứ người điều độ mở bàn này ra để nhét vào, lọc nó đi vì "không thuộc
    cửa sổ" là giấu mất đúng phần việc cần làm. Cửa sổ chọn hẹp (một ngày) và `Hôm sau` vẫn phải
    vắng — nếu không, một bản "cửa sổ vô hiệu" cũng xanh."""
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h, "?tu=2026-09-10&den=2026-09-10")
    assert viec_quanh_cua_so["Chưa xếp"] in thay, "việc chưa xếp giờ biến mất khi có cửa sổ"
    assert viec_quanh_cua_so["Hôm sau"] not in thay


def test_theo_may_khong_cua_so_thi_thay_het(client, seed_credentials, viec_quanh_cua_so):
    """TIỀN ĐỀ của ba bài trên, và là luật "tham số vắng mặt = không lọc": không `tu`/`den` thì
    `/theo-may` giữ nguyên hành vi Task 16 (backlog trọn đời). Đỏ nếu ai đó gán mặc định "hôm nay"
    cho cửa sổ — khi đó bàn im lặng giấu mọi việc xếp cho tuần sau."""
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h)
    assert {viec_quanh_cua_so[k] for k in ("Hôm trước", "Hôm sau", "Vắt qua", "Chưa xếp")} <= thay
    assert viec_quanh_cua_so["cv_ngoai"] in thay


def test_theo_may_mot_dau_cua_so_chi_chan_dau_do(client, seed_credentials, viec_quanh_cua_so):
    """Đỏ nếu `_cua_so_ban_may` đòi CẢ HAI đầu mới lọc (hoặc tự bịa đầu còn thiếu): `?tu=` một
    mình phải chặn quá khứ mà để ngỏ tương lai, `?den=` một mình thì ngược lại. Mỗi vế đều có
    phần tử "không thoả" riêng nên một bản bỏ qua cửa sổ nửa hở cũng đỏ."""
    h = _h(_tok(client, seed_credentials))
    tu_thoi = _blocks_theo_may(client, h, "?tu=2026-09-10")
    assert viec_quanh_cua_so["Hôm sau"] in tu_thoi
    assert viec_quanh_cua_so["Hôm trước"] not in tu_thoi

    den_thoi = _blocks_theo_may(client, h, "?den=2026-09-10")
    assert viec_quanh_cua_so["Hôm trước"] in den_thoi
    assert viec_quanh_cua_so["Hôm sau"] not in den_thoi


def test_theo_may_cua_so_loc_ids_truoc_khi_nap(sess, viec_quanh_cua_so, monkeypatch):
    """Ruling C121 áp cho cả cửa sổ: lọc Ở SQL, TRƯỚC `boi_canh.nap()`. Đỏ nếu cửa sổ chỉ được áp
    ở tầng Python (lọc block sau khi nạp) — khi đó `nap()` vẫn kéo về lệnh `lsx_ngoai` dù mọi việc
    của nó nằm ngoài cửa sổ mười ngày, và một xưởng chạy lâu năm trả cả kho lịch sử mỗi lần tải.
    Bài rình thẳng đối số của `nap()`, không đo gián tiếp qua số câu SQL."""
    ghi: dict = {}
    nap_that = bang_theo_doi.boi_canh.nap

    def rinh(db, lsx_ids):
        ghi["ids"] = list(lsx_ids)
        return nap_that(db, lsx_ids)

    monkeypatch.setattr(bang_theo_doi.boi_canh, "nap", rinh)
    bang_theo_doi.theo_may(sess, sale_ids=None, tu=NGAY_CUA_SO, den=NGAY_CUA_SO)
    assert viec_quanh_cua_so["lsx"] in ghi["ids"], "lệnh CÓ việc trong cửa sổ phải lọt vào nap()"
    assert viec_quanh_cua_so["lsx_ngoai"] not in ghi["ids"], (
        "lệnh không có việc nào trong cửa sổ vẫn được nạp — cửa sổ chỉ chạy ở Python"
    )


def test_theo_may_cua_so_nguoc_422(client, seed_credentials):
    """Đỏ nếu router nhận `tu > den` không kêu: cửa sổ ngược cho ra tập rỗng, mà người dùng đọc
    một bàn trắng thành "hôm nay xưởng không có việc" chứ không thành "mình gõ ngược ngày"."""
    h = _h(_tok(client, seed_credentials))
    r = client.get(
        "/api/theo-doi-san-xuat/theo-may?tu=2026-09-20&den=2026-09-10", headers=h
    )
    assert r.status_code == 422


# --- V3: lane cho máy KHÔNG có việc ---------------------------------------------------------------
def test_theo_may_lane_rong_cho_may_khong_co_viec(
    client, seed_credentials, hai_may_khong_viec, viec_chua_xep_may,
):
    """C126 mục 2. Đỏ nếu khung lane vẫn dựng TỪ DỮ LIỆU công việc (`theo_lane` chỉ gom theo
    `cv.may_id` như Task 16) thay vì từ DANH MỤC máy: hai máy dưới đây không gánh việc nào nên sẽ
    không có lane, và câu hỏi "máy nào đang trống để nhét việc vào" không trả lời được.

    Máy CÒN DÙNG là vế khẳng định; máy ĐÃ NGỪNG DÙNG và không việc nào là vế phủ định — sau Vòng
    sửa 1 mục 4 (Ruling C132) nó KHÔNG được đẻ lane nữa, nên bài này cũng đỏ với bản "cứ máy nào
    trong danh mục cũng đẻ lane rỗng". Máy ngừng dùng CÒN ôm việc thì vẫn phải có lane — vế đó ở
    `test_theo_may_may_ngung_dung_giu_lane_khi_con_viec_bo_lane_khi_rong`.

    `viec_chua_xep_may` giữ trong fixture để bàn vẫn có ít nhất một lane CÓ block, tức bài không
    xanh nhờ một bàn trống trơn."""
    ranh_id, ngung_id = hai_may_khong_viec
    h = _h(_tok(client, seed_credentials))
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    theo_id = {l["may_id"]: l for l in lanes}

    assert ranh_id in theo_id, "máy còn dùng, không có việc — thiếu lane rỗng"
    assert theo_id[ranh_id]["blocks"] == []
    assert theo_id[ranh_id]["ngung_dung"] is False
    assert theo_id[ranh_id]["ten"] == "Máy bế đang rảnh (C126)", (
        "lane của máy rảnh mang nhãn sai — máy rảnh không nằm trong bc.may nên rất dễ bị gán "
        "nhầm nhãn 'Máy đã xoá'"
    )

    assert ngung_id not in theo_id, (
        "máy đã ngừng dùng và KHÔNG có việc vẫn đẻ lane rỗng (C132, vòng sửa 1 mục 4)"
    )

    co_block = [l for l in lanes if l["blocks"]]
    assert co_block, "tiền đề: bàn phải có ít nhất một lane CÓ việc"


def test_theo_may_loc_may_chi_bay_lane_may_do(
    client, seed_credentials, hai_may_khong_viec, viec_chua_xep_may,
):
    """Đỏ nếu `?may_id=` chỉ thu hẹp TẬP LỆNH mà vẫn bày nguyên khung lane của cả danh mục: chọn
    một máy rồi nhận về hai chục lane (kèm lane "Chưa xếp máy") là câu trả lời sai cho câu hỏi đã
    đặt. Phần tử "không thoả": máy ngừng dùng và lane "Chưa xếp máy" — cả hai đều tồn tại trong
    cùng lượt gọi KHÔNG lọc (đã canh ở bài trên) nên bài này phân biệt được hai hành vi."""
    ranh_id, ngung_id = hai_may_khong_viec
    h = _h(_tok(client, seed_credentials))
    lanes = client.get(
        "/api/theo-doi-san-xuat/theo-may?may_id=%d" % ranh_id, headers=h
    ).json()["lanes"]
    assert [l["may_id"] for l in lanes] == [ranh_id], (
        "lọc theo một máy vẫn trả về lane của máy khác / lane Chưa xếp máy"
    )


# --- V4: block mang cặp `(lsx_id, ma)` (Ruling C123) ----------------------------------------------
def test_theo_may_block_mang_ca_lsx_id_lan_ma(client, seed_credentials, sess, ghep_doi):
    """Đỏ nếu `MayLaneBlockOut.lsx` quay lại `list[str]` (chỉ mã): FE không có gì để bấm mở hồ sơ,
    phải dò ngược mã → id hoặc đoán. Dùng ca in GHÉP vì đó là hình dạng duy nhất mà một block gánh
    NHIỀU lệnh — C123 chốt là từ hai lệnh trở lên thì FE bày danh sách cho người chọn, nên cả hai
    cặp phải có mặt và `lsx_id` phải là id THẬT của đúng lệnh mang mã đó (một bản trả `lsx_id` của
    lệnh đầu cho cả hai phần tử cũng đỏ). Thứ tự vẫn sắp theo MÃ như Task 16."""
    a_id, b_id, cv_chung = ghep_doi
    ma_theo_id = {l: sess.get(Lsx, l).ma for l in (a_id, b_id)}
    assert len(set(ma_theo_id.values())) == 2, "tiền đề: hai lệnh phải khác mã"

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()
    block = next(
        b for l in d["lanes"] for b in l["blocks"] if b["cong_viec_id"] == cv_chung.id
    )
    assert block["lsx"] == sorted(
        [{"lsx_id": a_id, "ma": ma_theo_id[a_id]}, {"lsx_id": b_id, "ma": ma_theo_id[b_id]}],
        key=lambda x: x["ma"],
    )


def test_theo_may_block_lsx_giu_thu_tu_theo_ma(client, seed_credentials, sess, ghep_doi):
    """Đỏ nếu thứ tự `lsx` trong block đổi tiêu chí (sắp theo `lsx_id`, hay bỏ hẳn `sorted`, để
    thứ tự chạy theo dict/set): Task 17 đổi KIỂU phần tử nhưng brief bắt GIỮ tiêu chí sắp theo MÃ,
    vì đó là thứ người dùng đọc trên block. Bài đổi mã của một lệnh cho THỨ TỰ MÃ NGƯỢC với thứ tự
    id — không đổi thì hai tiêu chí trùng nhau và bài không phân biệt được gì."""
    a_id, b_id, cv_chung = ghep_doi
    sess.get(Lsx, a_id).ma = "LSX-ZZZ-SAU"
    sess.get(Lsx, b_id).ma = "LSX-AAA-TRUOC"
    sess.commit()

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()
    block = next(
        b for l in d["lanes"] for b in l["blocks"] if b["cong_viec_id"] == cv_chung.id
    )
    assert [x["ma"] for x in block["lsx"]] == ["LSX-AAA-TRUOC", "LSX-ZZZ-SAU"]
    assert [x["lsx_id"] for x in block["lsx"]] == [b_id, a_id]


# ==================================================================================================
# VÒNG SỬA 1 — MỤC 1 (Ruling C135): `du_kien_ket_thuc IS NULL` nghĩa là MỞ ĐẦU KIA (+∞), KHÔNG
# phải "kết thúc ngay lúc bắt đầu".
#
# Bug thật đang chạy trước vòng này: cả hai tầng đều `COALESCE(ket_thuc, bat_dau)` / `... or bd`,
# nên một ca đang chạy từ tuần trước mà chưa ai đóng giờ dự kiến kết thúc bị suy thành khoảng
# `[bat_dau, bat_dau]` — nằm trọn TRƯỚC `tu` ⇒ rớt khỏi bàn điều độ ĐÚNG LÚC NÓ ĐANG CHẠY. Vi phạm
# thẳng luật "cửa sổ chỉ NỚI, không THU HẸP" của C126.
#
# Chỉ đầu `tu` mở. Vế `den` vẫn chặn: việc xếp bắt đầu SAU `den` thì không thuộc cửa sổ dù chưa
# biết giờ xong — nếu không, mọi việc chưa khai giờ kết thúc sẽ tràn vào mọi cửa sổ.
# ==================================================================================================
def _bat_dau_that(sess, admin, cv, *, ma: str, ten: str) -> None:
    """Bắt đầu một bước qua ĐÚNG đường ghi production, KHÔNG kết thúc — dựng một ca "đang chạy"
    đứng yên. Bản sao của `test_theo_doi_kanban._bat_dau_that` (hai file test độc lập nhau, mỗi
    file tự dựng nền trên DB SQLite riêng); xem `lenh_sx_fixtures._chay_that` cho lý do từng cửa
    (`has_piece_work`, `ly_do_tre`, `ly_do_so_nguoi`)."""
    to = sess.get(Department, cv.department_id)
    to.has_piece_work = True
    sess.commit()
    _giao_nguoi(sess, admin, cv, ma=ma, ten=ten)
    thuc_thi.bat_dau(
        sess, user=admin, cong_viec_id=cv.id,
        ly_do_tre="Chờ giấy về", ly_do_so_nguoi="Tổ thiếu người",
    )
    sess.expire_all()


@pytest.fixture
def viec_dang_chay_chua_biet_gio_xong(sess, orders, lsx_svc, admin, customer) -> dict:
    """MỘT lệnh, BA công việc — hình dạng mà C135 chốt lại. Cửa sổ đem canh là 10/09/2026.

        khoá         trạng thái  mốc kế hoạch                trong cửa sổ 10/09?
        dang_chay    running     01/09 08:00 → NULL          CÓ    (NULL = mở tới +∞)
        xong_som     released    01/09 08:00 → 01/09 09:00   KHÔNG (kết thúc hẳn trước `tu`)
        xep_sau      released    20/09 08:00 → NULL          KHÔNG (bắt đầu sau `den`)

    Hai phần tử "không thoả" là cố ý và mỗi cái chặn một bản vá sai khác nhau:
      · `xong_som` chặn bản "bỏ hẳn vế `tu`" (cửa sổ mất nửa trái thì việc này cũng lọt);
      · `xep_sau` chặn bản "NULL thì LUÔN lọt như việc chưa xếp giờ" — nới quá tay sang cả đầu
        `den`, khi đó mọi việc chưa khai giờ kết thúc tràn vào mọi cửa sổ.

    Ba việc nằm trong CÙNG một lệnh: tầng SQL chọn LỆNH nên lệnh này lọt/rớt trọn gói, còn phép
    chọn BLOCK mới phân biệt ba việc — bài vì thế đỏ ở CẢ hai tầng khi chỉ vá một tầng.
    """
    _dot_dong_don(sess, 77)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("Đang chạy", 30, 500), ("Xong sớm", 30, 500), ("Xếp sau", 30, 500)],
    )
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}
    _bat_dau_that(sess, admin, cvs["Đang chạy"], ma="THO-C135", ten="Thợ ca dài (C135)")
    cvs = {cv.ten_cong_doan: cv for cv in _cvs(sess, lsx_id)}

    moc = {
        "Đang chạy": (datetime(2026, 9, 1, 8, 0), None),
        "Xong sớm": (datetime(2026, 9, 1, 8, 0), datetime(2026, 9, 1, 9, 0)),
        "Xếp sau": (datetime(2026, 9, 20, 8, 0), None),
    }
    for ten, (bd, kt) in moc.items():
        cvs[ten].du_kien_bat_dau = bd.replace(tzinfo=timezone.utc)
        cvs[ten].du_kien_ket_thuc = kt.replace(tzinfo=timezone.utc) if kt else None
    sess.commit()
    sess.expire_all()

    assert cvs["Đang chạy"].trang_thai == CV_DANG_CHAY, (
        "tiền đề: bước phải ĐANG CHẠY — bug này chỉ có nghĩa với việc chưa hoàn thành"
    )
    ket = {ten: cvs[ten].id for ten in moc}
    ket["lsx"] = lsx_id
    return ket


def test_theo_may_viec_dang_chay_chua_biet_gio_xong_van_trong_cua_so(
    client, seed_credentials, viec_dang_chay_chua_biet_gio_xong,
):
    """Đỏ nếu `du_kien_ket_thuc IS NULL` bị suy thành "kết thúc NGAY LÚC BẮT ĐẦU"
    (`COALESCE(ket_thuc, bat_dau)` ở `_cham_cua_so_sql`, `... or bd` ở `_cham_cua_so`): ca đang
    chạy từ 01/09 mà chưa ai khai giờ xong biến mất khỏi cửa sổ 10/09 — đúng lúc nó vẫn chiếm máy.
    Ruling C135: NULL = MỞ tới +∞, chỉ ở đầu `tu`.

    Hai vế còn lại giữ bài khỏi xanh nhờ một bản nới quá tay: `xong_som` (đã xong hẳn trước cửa sổ)
    và `xep_sau` (bắt đầu sau `den`, cũng NULL giờ kết thúc) đều phải VẮNG."""
    v = viec_dang_chay_chua_biet_gio_xong
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h, "?tu=2026-09-10&den=2026-09-10")
    assert v["Đang chạy"] in thay, (
        "việc ĐANG CHẠY chưa biết giờ xong bị cửa sổ nuốt mất — NULL bị coi là kết thúc tức thời"
    )
    assert v["Xong sớm"] not in thay
    assert v["Xếp sau"] not in thay, (
        "việc bắt đầu SAU `den` vẫn lọt — NULL bị nới sang cả đầu `den`, không chỉ đầu `tu`"
    )


def test_theo_may_viec_chua_biet_gio_xong_loc_ids_truoc_khi_nap(
    sess, viec_dang_chay_chua_biet_gio_xong, monkeypatch,
):
    """Cùng luật C135 nhưng canh TẦNG SQL: đỏ nếu chỉ tầng Python được vá còn `_cham_cua_so_sql`
    vẫn `COALESCE` — khi đó câu SQL loại LUÔN CẢ LỆNH và tầng Python không bao giờ được nhìn thấy
    việc đang chạy. Đây đúng chiều trôi lệch NGUY HIỂM mà docstring `_cham_cua_so` từng nói quá là
    "không mất dữ liệu" (mục 6).

    Phần tử "không thoả": chính lệnh này khi hỏi một cửa sổ nằm hẳn TRƯỚC mọi mốc của nó (20/08) —
    lúc đó nó PHẢI rớt, nếu không thì một bản "bỏ hẳn cửa sổ ở SQL" cũng xanh. (Cửa sổ nằm SAU thì
    KHÔNG dùng được làm phần tử phủ định: việc `Xếp sau` mở tới +∞ nên nó chạm mọi cửa sổ về sau —
    đúng theo C135, không phải lỗi.)"""
    ghi: dict = {}
    nap_that = bang_theo_doi.boi_canh.nap

    def rinh(db, lsx_ids):
        ghi.setdefault("ids", []).append(list(lsx_ids))
        return nap_that(db, lsx_ids)

    monkeypatch.setattr(bang_theo_doi.boi_canh, "nap", rinh)
    bang_theo_doi.theo_may(sess, sale_ids=None, tu=NGAY_CUA_SO, den=NGAY_CUA_SO)
    bang_theo_doi.theo_may(
        sess, sale_ids=None, tu=date(2026, 8, 20), den=date(2026, 8, 20),
    )
    trong_cua_so, truoc_moi_moc = ghi["ids"]
    assert viec_dang_chay_chua_biet_gio_xong["lsx"] in trong_cua_so, (
        "câu SQL loại cả lệnh vì việc đang chạy chưa khai giờ xong — tầng Python không được nhìn"
    )
    assert viec_dang_chay_chua_biet_gio_xong["lsx"] not in truoc_moi_moc, (
        "cửa sổ 20/08 (trước MỌI mốc của lệnh) vẫn nạp lệnh — vế `den` của câu SQL mất tác dụng"
    )


# ==================================================================================================
# VÒNG SỬA 1 — MỤC 2: HÀNG RÀO RIÊNG cho TẦNG SQL của cửa sổ.
#
# Lỗ hổng người rà soát tìm ra: `viec_quanh_cua_so` dồn mọi ca biên vào MỘT lệnh, nên câu SQL
# ("lệnh có ít nhất một việc chạm cửa sổ") LUÔN cho lệnh đó qua và chỉ tầng Python quyết định.
# Đột biến `_cham_cua_so_sql` từ CHỒNG LẤN sang "bắt đầu trong khoảng" ⇒ 71/71 bài vẫn XANH.
#
# Hình dạng vá lỗ: một lệnh CÔ LẬP (việc của nó không lệnh nào khác dùng chung) mà việc DUY NHẤT
# của nó KHÔNG "bắt đầu trong khoảng" nhưng CÓ chồng lấn — SQL sai là lệnh biến mất, không còn tầng
# nào cứu.
# ==================================================================================================
@pytest.fixture
def hai_lenh_co_lap_quanh_cua_so(sess, orders, lsx_svc, admin, customer) -> dict:
    """HAI lệnh MỘT-BƯỚC, mỗi lệnh giữ riêng công việc của nó (không bài ghép, không dùng chung).

        khoá      mốc kế hoạch                  cửa sổ 10/09?
        vat_qua   05/09 08:00 → 15/09 17:00     CÓ    — chồng lấn, nhưng KHÔNG "bắt đầu trong"
        ngoai     20/09 08:00 → 20/09 09:00     KHÔNG — phần tử "không thoả"

    Khác `viec_quanh_cua_so` ở đúng một điểm, và điểm đó là toàn bộ lý do fixture này tồn tại:
    ở kia sáu việc nằm trong CÙNG một lệnh nên câu SQL cho cả lệnh qua bất kể nó hỏi gì, còn ở đây
    lệnh `vat_qua` chỉ có MỘT việc — SQL hỏi sai là mất trắng cả lệnh.
    """
    _dot_dong_don(sess, 78)
    lsx_vat = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("Ca in dài", 60, 500)],
    )
    cv_vat = _cvs(sess, lsx_vat)[0]
    cv_vat.du_kien_bat_dau = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
    cv_vat.du_kien_ket_thuc = datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc)

    lsx_ngoai = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("Ca in sau", 60, 500)],
    )
    cv_ngoai = _cvs(sess, lsx_ngoai)[0]
    cv_ngoai.du_kien_bat_dau = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    cv_ngoai.du_kien_ket_thuc = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    sess.commit()

    assert len(_cvs(sess, lsx_vat)) == 1, "tiền đề: lệnh `vat_qua` phải CHỈ có một việc"
    return {
        "lsx_vat": lsx_vat, "cv_vat": cv_vat.id,
        "lsx_ngoai": lsx_ngoai, "cv_ngoai": cv_ngoai.id,
    }


def test_theo_may_cua_so_sql_chan_o_tang_lenh_khong_phai_tang_block(
    sess, hai_lenh_co_lap_quanh_cua_so, monkeypatch,
):
    """HÀNG RÀO của TẦNG SQL (`_cham_cua_so_sql`), tách hẳn khỏi tầng Python (`_cham_cua_so`).
    Đỏ nếu câu SQL hỏi "bắt đầu TRONG khoảng" thay vì CHỒNG LẤN: lệnh `vat_qua` (một việc duy
    nhất, bắt đầu 05/09) rớt ngay ở `WHERE` và `boi_canh.nap()` không bao giờ nhận được nó — tầng
    Python không có gì để cứu, khác hẳn `viec_quanh_cua_so` nơi lệnh luôn lọt nhờ năm việc còn lại.

    Bài rình thẳng đối số của `nap()` chứ không đọc kết quả API: nếu chỉ đọc block thì một bản
    "SQL hẹp + Python rộng" vẫn có thể xanh nhờ lệnh khác kéo theo.

    Phần tử "không thoả": `lsx_ngoai` (20/09) phải VẮNG — không có nó thì một bản bỏ hẳn cửa sổ ở
    SQL cũng xanh."""
    ghi: dict = {}
    nap_that = bang_theo_doi.boi_canh.nap

    def rinh(db, lsx_ids):
        ghi["ids"] = list(lsx_ids)
        return nap_that(db, lsx_ids)

    monkeypatch.setattr(bang_theo_doi.boi_canh, "nap", rinh)
    bang_theo_doi.theo_may(sess, sale_ids=None, tu=NGAY_CUA_SO, den=NGAY_CUA_SO)
    assert hai_lenh_co_lap_quanh_cua_so["lsx_vat"] in ghi["ids"], (
        "lệnh CÔ LẬP chỉ chạm cửa sổ theo phép CHỒNG LẤN đã bị câu SQL loại — cửa sổ SQL THU HẸP"
    )
    assert hai_lenh_co_lap_quanh_cua_so["lsx_ngoai"] not in ghi["ids"]


def test_theo_may_cua_so_sql_giu_lai_block_cua_lenh_co_lap(
    client, seed_credentials, hai_lenh_co_lap_quanh_cua_so,
):
    """Vế NGƯỜI DÙNG THẤY của bài trên: block của lệnh cô lập phải thật sự lên bàn, không chỉ lọt
    vào `nap()`. Đỏ với cùng một đột biến `_cham_cua_so_sql`, và cũng đỏ nếu ai đó "vá" bằng cách
    nới SQL rồi lại siết ở tầng Python. `cv_ngoai` là phần tử "không thoả"."""
    h = _h(_tok(client, seed_credentials))
    thay = _blocks_theo_may(client, h, "?tu=2026-09-10&den=2026-09-10")
    assert hai_lenh_co_lap_quanh_cua_so["cv_vat"] in thay
    assert hai_lenh_co_lap_quanh_cua_so["cv_ngoai"] not in thay


# ==================================================================================================
# VÒNG SỬA 1 — MỤC 4 (Ruling C132): máy NGỪNG DÙNG mà KHÔNG có block thì THÔI đẻ lane.
#
# C126 viết "ĐỪNG ẩn lane" là để chặn việc BIẾN MẤT, không phải để giữ lane rỗng cho máy đã thanh
# lý — xưởng chạy lâu năm sẽ có hàng chục lane chết. Máy ngừng dùng mà CÒN ôm việc thì lane vẫn
# phải hiện (kèm cờ `ngung_dung`): đó đúng là thứ điều độ phải xử lý.
# ==================================================================================================
@pytest.fixture
def hai_may_ngung_dung(sess, orders, lsx_svc, admin, customer) -> dict:
    """HAI máy đã NGỪNG DÙNG (`active=False`), khác nhau ĐÚNG MỘT điểm — có việc hay không.

        khoá         active  việc chưa xong        lane trên `/theo-may`?
        co_viec      False   MỘT (bước CTP)        CÒN, kèm `ngung_dung=True`
        khong_viec   False   không                 KHÔNG (C132)

    Hai phần tử ngược nhau trong CÙNG một bài là điều kiện C127: một bản "ẩn mọi máy ngừng dùng"
    và một bản "giữ mọi máy ngừng dùng" đều phải bị bắt, không bản nào lọt.
    """
    co_viec = MayThietBi(
        ma="MAY-C132-CO-VIEC", ten="Máy bế cũ còn việc (C132)", loai_may="be", active=False,
    )
    khong_viec = MayThietBi(
        ma="MAY-C132-RONG", ten="Máy xén đã thanh lý (C132)", loai_may="be", active=False,
    )
    sess.add_all([co_viec, khong_viec])
    sess.commit()

    _dot_dong_don(sess, 80)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    cv = _cvs(sess, lsx_id)[0]
    cv.may_id = co_viec.id
    sess.commit()
    return {"co_viec": co_viec.id, "khong_viec": khong_viec.id, "cv": cv.id}


def test_theo_may_may_ngung_dung_giu_lane_khi_con_viec_bo_lane_khi_rong(
    client, seed_credentials, hai_may_ngung_dung,
):
    """Ruling C132. Đỏ theo HAI chiều ngược nhau:
      · bỏ luật ⇒ máy đã thanh lý KHÔNG việc vẫn đẻ lane rỗng, bàn điều độ mọc hàng chục lane chết;
      · làm quá tay (ẩn MỌI máy `active=False`) ⇒ việc còn nằm trên máy đã thanh lý biến mất khỏi
        bàn, đúng thứ C126 cấm.

    Hai máy trong fixture khác nhau ĐÚNG cột `blocks`, nên không bản nào đi qua được cả hai vế."""
    g = hai_may_ngung_dung
    h = _h(_tok(client, seed_credentials))
    lanes = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    theo_id = {l["may_id"]: l for l in lanes}

    assert g["co_viec"] in theo_id, "máy ngừng dùng CÒN ôm việc bị ẩn lane — việc biến mất"
    assert theo_id[g["co_viec"]]["ngung_dung"] is True
    assert g["cv"] in {b["cong_viec_id"] for b in theo_id[g["co_viec"]]["blocks"]}

    assert g["khong_viec"] not in theo_id, (
        "máy đã thanh lý và KHÔNG có việc nào vẫn đẻ lane rỗng (C132)"
    )


# ==================================================================================================
# VÒNG SỬA 2 — MỤC 1 (Ruling C136) và MỤC 2 (Ruling C137).
#
# Gốc chung: `theo_may()` từng quyết định "máy này có lane không" bằng cách nhìn `cvs` — tập công
# việc ĐÃ LỌC THEO CỬA SỔ. Nhưng "máy này còn nợ việc không" là câu hỏi ĐỘC LẬP với cửa sổ đang
# xem. Trộn hai câu vào một phép thử đẻ ra hai lỗi dưới đây.
#
# C136 — "còn nợ việc" là MỘT vị ngữ duy nhất (`_may_con_no_viec`), độc lập cửa sổ, dùng chung cho
#        cờ `co_viec` của `/bo-loc` lẫn quyết định có-lane của `/theo-may`.
# C137 — C132 chỉ chi phối bộ lane MẶC ĐỊNH. `?may_id=` tường minh luôn trả ĐÚNG MỘT lane.
# ==================================================================================================
@pytest.fixture
def may_ngung_dung_no_viec_ngoai_cua_so(sess, orders, lsx_svc, admin, customer) -> dict:
    """HAI máy đã NGỪNG DÙNG, khác nhau đúng ở chỗ CÒN NỢ VIỆC hay không — và việc đang nợ nằm
    NGOÀI cửa sổ đem hỏi.

        khoá        active  việc                              lane khi hỏi cửa sổ 10/09?
        no_viec     False   MỘT bước `released` 20/09 08:00    CÒN (C132 hứa vô điều kiện)
        sach_no     False   không việc nào                    KHÔNG (C132 khử lane chết)

    Cửa sổ đem hỏi (10/09) cố ý KHÔNG chứa việc kia: đó chính là ca biên. Máy `sach_no` là phần tử
    "không thoả" — thiếu nó thì một bản "cứ máy ngừng dùng là đẻ lane" cũng xanh.
    """
    no_viec = MayThietBi(
        ma="MAY-C136-NO", ten="Máy bế cũ còn nợ việc (C136)", loai_may="be", active=False,
    )
    sach_no = MayThietBi(
        ma="MAY-C136-SACH", ten="Máy xén cũ hết việc (C136)", loai_may="be", active=False,
    )
    sess.add_all([no_viec, sach_no])
    sess.commit()

    _dot_dong_don(sess, 82)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("CTP", 15, 500)],
    )
    cv = _cvs(sess, lsx_id)[0]
    cv.may_id = no_viec.id
    cv.du_kien_bat_dau = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    cv.du_kien_ket_thuc = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    sess.commit()

    assert cv.trang_thai != CV_HOAN_THANH, "tiền đề: việc đang nợ phải CHƯA hoàn thành"
    return {"no_viec": no_viec.id, "sach_no": sach_no.id, "cv": cv.id}


def test_theo_may_may_ngung_dung_con_no_viec_ngoai_cua_so_van_co_lane(
    client, seed_credentials, may_ngung_dung_no_viec_ngoai_cua_so,
):
    """Ruling C136. Đỏ nếu quyết định có-lane đọc tập công việc ĐÃ LỌC THEO CỬA SỔ (`cvs`) thay vì
    vị ngữ "còn nợ việc" độc lập cửa sổ: máy đã thanh lý còn nợ một bước `released` xếp cho ngày
    20/09 sẽ BIẾN MẤT khỏi bàn ngay khi người điều độ thu cửa sổ về ngày 10/09 — trái thẳng lời hứa
    vô điều kiện của C132, và là lần thứ ba của họ lỗi "cửa sổ thu hẹp làm dữ liệu biến mất im
    lặng" trên nhánh này.

    Máy `sach_no` (ngừng dùng, KHÔNG nợ gì) phải VẮNG trong cùng lượt gọi — nếu không thì một bản
    bỏ hẳn C132 cũng xanh. Lane của `no_viec` mang `blocks: []` là ĐÚNG: việc kia thật sự nằm ngoài
    cửa sổ, cái phải giữ là LANE (chỗ để thấy máy còn nợ), không phải block."""
    g = may_ngung_dung_no_viec_ngoai_cua_so
    h = _h(_tok(client, seed_credentials))
    lanes = client.get(
        "/api/theo-doi-san-xuat/theo-may?tu=2026-09-10&den=2026-09-10", headers=h
    ).json()["lanes"]
    theo_id = {l["may_id"]: l for l in lanes}

    assert g["no_viec"] in theo_id, (
        "máy ngừng dùng CÒN NỢ việc mất lane chỉ vì việc đó nằm ngoài cửa sổ đang xem"
    )
    assert theo_id[g["no_viec"]]["ngung_dung"] is True
    assert theo_id[g["no_viec"]]["blocks"] == []
    assert g["sach_no"] not in theo_id, "máy ngừng dùng KHÔNG nợ gì vẫn đẻ lane (C132)"


def test_theo_may_lane_may_ngung_dung_khong_doi_theo_cua_so(
    client, seed_credentials, may_ngung_dung_no_viec_ngoai_cua_so,
):
    """Bất biến gọn của C136, phát biểu thành một phép so trực tiếp: bộ máy NGỪNG DÙNG có lane
    phải GIỐNG NHAU dù hỏi cửa sổ nào — kể cả cửa sổ không chứa việc nào. Đỏ nếu quyết định có-lane
    còn dính vào cửa sổ ở bất kỳ đường nào (kể cả một bản chỉ vá riêng ca biên của bài trên).

    Phần tử "không thoả" nằm ngay trong phép so: `sach_no` vắng ở CẢ HAI vế, nên hai vế bằng nhau
    không phải vì cả hai cùng rỗng."""
    g = may_ngung_dung_no_viec_ngoai_cua_so
    h = _h(_tok(client, seed_credentials))

    def ngung_dung_co_lane(truy_van: str) -> set[int]:
        d = client.get("/api/theo-doi-san-xuat/theo-may" + truy_van, headers=h).json()
        return {l["may_id"] for l in d["lanes"] if l["ngung_dung"]}

    rong = ngung_dung_co_lane("")
    hep = ngung_dung_co_lane("?tu=2026-09-10&den=2026-09-10")
    assert hep == rong, f"bộ lane máy ngừng dùng đổi theo cửa sổ: {rong} → {hep}"
    assert g["no_viec"] in rong
    assert g["sach_no"] not in rong


def test_theo_may_hoi_dich_danh_may_ngung_dung_dang_ranh_van_ra_mot_lane(
    client, seed_credentials, hai_may_ngung_dung,
):
    """Ruling C137. Đỏ nếu C132 bị áp cho cả nhánh `?may_id=` tường minh: người dùng hỏi đích danh
    "cho tôi xem máy X" mà nhận `{"lanes": []}` sẽ đọc thành "máy này không tồn tại" — cùng họ
    nói-dối-im-lặng. C132 sinh ra để khử NHIỄU trong bộ lane MẶC ĐỊNH, mà một câu hỏi trực tiếp
    thì không phải nhiễu.

    Bài canh CẢ HAI nhánh trên cùng một máy: không tham số ⇒ KHÔNG lane (C132 vẫn nguyên), hỏi
    đích danh ⇒ ĐÚNG MỘT lane. Một bản bỏ hẳn C132 sẽ đỏ ở vế đầu, một bản áp C132 khắp nơi đỏ ở
    vế sau."""
    ngung_ranh = hai_may_ngung_dung["khong_viec"]
    h = _h(_tok(client, seed_credentials))

    mac_dinh = client.get("/api/theo-doi-san-xuat/theo-may", headers=h).json()["lanes"]
    assert ngung_ranh not in {l["may_id"] for l in mac_dinh}, (
        "tiền đề C132: bộ lane MẶC ĐỊNH vẫn không đẻ lane cho máy đã thanh lý đang rảnh"
    )

    lanes = client.get(
        "/api/theo-doi-san-xuat/theo-may?may_id=%d" % ngung_ranh, headers=h
    ).json()["lanes"]
    assert [l["may_id"] for l in lanes] == [ngung_ranh], (
        "hỏi đích danh một máy có THẬT mà trả về danh sách rỗng"
    )
    assert lanes[0]["ngung_dung"] is True
    assert lanes[0]["blocks"] == []
    assert lanes[0]["ten"] == "Máy xén đã thanh lý (C132)"


def test_theo_may_hoi_may_id_khong_ton_tai_van_ra_mot_lane_may_da_xoa(
    client, seed_credentials, sess, hai_may_ngung_dung,
):
    """Hợp đồng cho `?may_id=` trỏ vào một id KHÔNG có trong `may_thiet_bi`: trả `200` với ĐÚNG MỘT
    lane rỗng mang nhãn "Máy đã xoá", KHÔNG phải 404 và cũng không phải `{"lanes": []}`.

    Chọn thế vì `may_id` là tham số lọc DÙNG CHUNG với `/kanban`, mà `/kanban?may_id=<id lạ>` trả
    `200` với bảng rỗng — hai tab của cùng một thanh lọc mà một tab `200` một tab `404` thì một
    chip lọc cũ (máy vừa bị xoá khỏi danh mục) làm gãy nguyên màn thay vì hiện một lane giải thích
    được. Nhãn "Máy đã xoá" là đúng từ vựng repo đã dùng cho soft-ref trỏ hụt (`NHAN_MAY_DA_XOA`).

    Đỏ nếu ai đó đổi sang 404/422, hoặc trả danh sách rỗng. Phần tử "không thoả": chính lượt hỏi
    máy CÓ THẬT ở bài trên, nhãn khác hẳn — nên bài không xanh nhờ mọi lane đều mang một nhãn."""
    lon_nhat = max(m.id for m in sess.query(MayThietBi).all())
    la = lon_nhat + 1000
    h = _h(_tok(client, seed_credentials))

    r = client.get("/api/theo-doi-san-xuat/theo-may?may_id=%d" % la, headers=h)
    assert r.status_code == 200
    lanes = r.json()["lanes"]
    assert [l["may_id"] for l in lanes] == [la], (
        "hỏi một `may_id` không có trong danh mục mà trả danh sách rỗng — im lặng"
    )
    assert lanes[0]["ten"] == "Máy đã xoá"
    assert lanes[0]["ngung_dung"] is False
    assert lanes[0]["blocks"] == []
