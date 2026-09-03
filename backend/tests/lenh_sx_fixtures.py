"""Fixture + helper DÙNG CHUNG cho các file test của tầng đọc "Hồ sơ lệnh sản xuất".

RÚT RA từ `tests/test_lenh_sx_api.py` (Task 9) khi Task 10 cần đúng những thứ này — RÚT chứ không
CHÉP. Hai bản sao của cùng một fixture thì trôi mỗi bản một hướng, và cái trôi trước là cái đang
"nói dối": nó vẫn dựng ra dữ liệu, chỉ là không còn giống dữ liệu production nữa, nên bài test dựa
vào nó xanh trên một hình dạng không tồn tại. Loạt task này đã dính đúng lỗi ấy nhiều lần.

Đây là MODULE THƯỜNG, không phải `conftest.py`: `conftest.py` áp fixture cho MỌI file test trong
thư mục, mà `sess`/`admin`/`customer`/`orders`/`lsx_svc` ở đây trùng tên với fixture của vài file
anh em (`test_xep_lich_service`, `test_san_xuat_board`). Đặt vào `conftest` là ghi đè lẫn nhau theo
thứ tự thu thập — hỏng im lặng. File nào cần thì `from tests.lenh_sx_fixtures import ...` cho
tường minh; pytest nhận fixture qua tên đã import vào namespace của module test.

--- VÌ SAO KHÔNG DÙNG FIXTURE `db` CỦA CÁC FILE ANH EM -------------------------------------------
`tests/test_xep_lich_service.py::db` (mà `test_san_xuat_board` / `test_lenh_sx_tien_do` re-export)
mở đầu bằng `drop_all` + `create_all` + `seed_all` — Y HỆT `conftest.client`. Kéo cả hai vào một
test là hai lượt xoá bảng đá nhau: cái chạy sau xoá sạch dữ liệu cái chạy trước, và triệu chứng là
một danh sách RỖNG chứ không phải một lỗi. Nên ở đây chỉ mượn HÀM (`_dung_lenh`, `_hai_lsx_san_sang`
là plain function, không phải fixture), còn session thì tự mở bằng `SessionLocal()` SAU khi `client`
đã dựng xong nền — đúng khuôn `test_lenh_sx_quyen.py::test_migration_0246_chep_quyen_cho_vai_tu_tao`.
DB test là SQLite in-memory + StaticPool ⇒ session này và session của request DÙNG CHUNG một
connection, nên mọi fixture PHẢI `commit()` trước khi trả về, không thì request đọc phải nửa vời.

--- HAI CHỖ CỐ Ý LÀM LỆCH (bài học Task 6 & 7) --------------------------------------------------
  · `lsx.id` vs `order_line_id` — hai bảng id tự tăng ĐỘC LẬP, trên DB test trắng chúng trôi song
    song và bằng nhau. `_dot_dong_don()` đốt trước một loạt `order_lines.id`: không có nó thì
    `bc.giao_cua(lsx_id)` và `bc.giao[lsx_id]` cho cùng kết quả và mọi bài chạm giao hàng hết canh.
  · `BAY_GIO` của các bài KPI đặt ở 02:00 GIỜ VN (19:00 UTC hôm trước) — ngày theo giờ xưởng KHÁC
    hẳn ngày theo UTC. Đặt mốc ban ngày thì bài "hôm nay" xanh cả khi cài đặt tính theo UTC.

--- LỆNH "PHÁT HÀNH" TRONG FIXTURE --------------------------------------------------------------
`san_xuat/release.phat_hanh` KHÔNG đụng `lsx.trang_thai` (đã đọc: nó chỉ đóng băng gói + công
việc). Đường ghi production của cột đó là `xep_lich_van_de_service.py:716`
(`lsx.trang_thai = LSX_DA_PHAT_HANH` — một phép gán cột phẳng, sau khi cụm liên thông qua hết cửa
vật tư/KCS-cuối). Fixture ở đây gán ĐÚNG giá trị đó bằng tay và bỏ qua các cửa — cửa là chuyện của
bàn xếp lịch, không phải của tầng đọc; giá trị ghi vào cột thì y hệt production.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.db import SessionLocal
from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from app.models.customer import Customer
from app.models.department import Department
from app.models.employee import Employee
from app.models.lsx import (
    LB_MAY, LB_THUE_NGOAI, TT_DA_PHAT_HANH, TT_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from app.models.order import Order, OrderLine
from app.models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from app.models.san_xuat_thuc_thi import (
    PC_HOAT_DONG, PHIEN_KET_THUC, SanXuatPhanCong, SanXuatPhienChay,
)
from app.models.user import User
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.lsx_repo import LsxRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password
from app.services.accounting_service import AccountingService
from app.services.lsx_service import LsxService
from app.services.order_service import OrderService
from app.services.san_xuat import release, thuc_thi
from app.services.sequence_service import SequenceService
from tests.test_lenh_sx_tien_do import _dung_lenh
from tests.test_san_xuat_board import _to_moi
from tests.test_xep_lich_service import _hai_lsx_san_sang

BAY_GIO = datetime(2026, 8, 31, 19, 0, tzinfo=timezone.utc)


# --- Hạ tầng phiên làm việc ---------------------------------------------------------------------
@pytest.fixture
def sess(client):
    """Session RIÊNG trên CÙNG nền mà `client` vừa dựng (drop/create + lifespan seed).

    Phụ thuộc `client` là phần LOAD-BEARING: nó ép thứ tự "dựng nền xong mới ghi dữ liệu". Đảo lại
    thì `client` xoá sạch những gì fixture vừa ghi.
    """
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def admin(sess) -> User:
    return sess.query(User).filter(User.username == "admin").first()


@pytest.fixture
def customer(sess) -> Customer:
    c = Customer(code="KH-DS", name="Khách Danh Sách")
    sess.add(c)
    sess.commit()
    return c


@pytest.fixture
def orders(sess) -> OrderService:
    audit = AuditLogRepository(sess)
    acc_repo = AccountingRepository(sess)
    accounting = AccountingService(
        acc_repo, PurchaseRequestRepository(sess), SupplierRepository(sess),
        UserRepository(sess), audit, SequenceService(DocumentSequenceRepository(sess)),
    )
    return OrderService(
        OrderRepository(sess), audit, QuotationRepository(sess), sess, acc_repo, accounting
    )


@pytest.fixture
def lsx_svc(sess) -> LsxService:
    return LsxService(
        sess, LsxRepository(sess), AuditLogRepository(sess),
        SequenceService(DocumentSequenceRepository(sess)),
    )


def _tok(client, seed_credentials) -> str:
    return client.post("/api/auth/login", json=seed_credentials).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Dàn cảnh -----------------------------------------------------------------------------------
_dem_ten_to = 0


def _nhuong_ten_to(sess) -> None:
    """`_dung_lenh` tạo tổ với tên CỨNG "Tổ Tiến độ", mà `departments.name`/`.code` là UNIQUE —
    gọi lần thứ hai trong cùng một test là `IntegrityError`. Đổi tên tổ CŨ (không xoá: công việc đã
    phát hành neo `department_id`, không neo tên). Khuôn lấy từ `test_lenh_sx_trang_thai._don_nen`.
    """
    global _dem_ten_to
    _dem_ten_to += 1
    for d in sess.query(Department).filter(Department.name == "Tổ Tiến độ").all():
        d.name = f"Tổ Tiến độ {_dem_ten_to}"
        d.code = f"TO-TIEN-DO-DS-{_dem_ten_to}"
    sess.commit()


def _dot_dong_don(sess, so_dong: int = 7) -> None:
    """Đốt vài `order_lines.id` để dãy đó KHÔNG còn trôi song song với dãy `lsx.id`.

    `Lsx` và `OrderLine` là hai bảng tự tăng độc lập; trên DB test trắng mà mỗi lệnh sinh đúng một
    dòng đơn thì `lsx.id == order_line_id` LUÔN đúng — và khi đó `bc.giao_cua(lsx_id)` (tra đúng)
    với `bc.giao[lsx_id]` (tra sai) trả CÙNG một thứ, bài test hết phân biệt được (Task 6 đã đo).
    """
    don = Order(order_no=f"DH-DS-DOT-{so_dong}")
    sess.add(don)
    sess.flush()
    for _ in range(so_dong):
        sess.add(OrderLine(order_id=don.id, description="Dòng mồi", qty=1))
    sess.commit()


def _lenh_tho(
    sess, *, ma: str, sale_user_id: int | None, customer_id: int | None = None,
    trang_thai_lsx: str = TT_DA_PHAT_HANH, han_sx: date | None = None,
    is_rush: bool = False, so_luong: int = 1000, ten: str = "Hộp giấy",
) -> int:
    """MỘT lệnh + đơn + dòng đơn của nó, đặt cột bằng tay.

    Mọi cột đặt ở đây đều là cột mà đường ghi production ghi đúng giá trị đó:
      · `orders.sale_user_id` — `OrderService` gán người bán khi lập đơn;
      · `lsx.trang_thai='da_phat_hanh'` — `xep_lich_van_de_service.py:716` (xem docstring module);
      · `lsx.is_rush` / `han_hoan_thanh_sx` / `so_luong_dat` — `LsxService.tao` + màn Kế hoạch SX.
    KHÔNG có công việc/phiên nào: đây là lệnh dùng cho các bài ĐẾM và PHÂN TRANG, nơi nội dung
    routing không tham gia phép so. Bài nào cần lệnh THẬT (routing + snapshot + phiên) thì dùng
    `lenh_that`, dựng qua `_dung_lenh` (đơn → PTG → LSX → `release.phat_hanh`).
    """
    don = Order(order_no=f"DH-{ma}", sale_user_id=sale_user_id, customer_id=customer_id)
    don.lines.append(OrderLine(description=ten, qty=so_luong))
    sess.add(don)
    sess.flush()
    lsx = Lsx(
        ma=ma, ten=ten, order_id=don.id, order_line_id=don.lines[0].id,
        trang_thai=trang_thai_lsx, so_luong_dat=so_luong, han_hoan_thanh_sx=han_sx,
        is_rush=is_rush,
    )
    sess.add(lsx)
    sess.commit()
    return lsx.id


@pytest.fixture
def hai_muoi_lenh(sess, admin, customer) -> list[int]:
    """20 lệnh ĐÃ PHÁT HÀNH thuộc phạm vi của admin (scope `all` ⇒ thấy hết).

    Hạn SX rải đều 20 ngày và mã đánh số để bài phân trang kiểm được TRẬT TỰ ổn định, không chỉ
    đếm số dòng: hai trang liền nhau phải rời nhau, gộp lại vẫn đủ 20.
    """
    _dot_dong_don(sess)
    ids = []
    for i in range(20):
        ids.append(_lenh_tho(
            sess, ma=f"LSX-DS-{i:02d}", sale_user_id=admin.id, customer_id=customer.id,
            han_sx=date(2026, 9, 1) + timedelta(days=i), so_luong=100 + i,
        ))
    return ids


@pytest.fixture
def lenh_nhap(sess, admin) -> int:
    """Lệnh CHƯA phát hành (`san_sang`). Hai màn chỉ-đọc không bao giờ được hiện nó."""
    return _lenh_tho(
        sess, ma="LSX-DS-NHAP", sale_user_id=admin.id, trang_thai_lsx=TT_SAN_SANG,
        ten="Lệnh còn ở bàn kế hoạch",
    )


@pytest.fixture
def sale_khac(sess) -> User:
    """Một người bán KHÁC admin, KHÔNG có lệnh nào — dùng làm giá trị lạ nhét lên URL."""
    u = User(username="sale_khac_ds", name="Sale khác (DS)", password_hash=hash_password("x"))
    sess.add(u)
    sess.commit()
    return u


@pytest.fixture
def sale_own(sess) -> User:
    """Người bán THẬT mang vai "NV Sales" (seed) — `lenh_san_xuat` ở scope `own`.

    Dùng vai SEED chứ không tự chế quyền: phạm vi `own` của hai màn mới là thứ `seed.ROLES` khai
    (`seed.py:615`), tự dựng một vai riêng ở đây thì bài test canh cấu hình của chính nó.
    """
    roles = RoleRepository(sess)
    depts = DepartmentRepository(sess)
    kd = depts.get_by_name("Kinh doanh")
    vai = roles.get_by_name_and_department("NV Sales", kd.id)
    assert vai is not None, "seed thiếu vai 'NV Sales' — bài phạm vi mất tiền đề"
    users = UserRepository(sess)
    u = users.create(
        username="sale_own_ds", name="Sale Own (DS)", password_hash=hash_password("x")
    )
    users.set_assignment(u, department_id=kd.id, role_id=vai.id, is_active=True)
    sess.commit()
    return u


@pytest.fixture
def lenh_cua_sale_own(sess, sale_own, customer) -> int:
    return _lenh_tho(
        sess, ma="LSX-DS-OWN", sale_user_id=sale_own.id, customer_id=customer.id,
        han_sx=date(2026, 9, 5), ten="Lệnh của Sale Own",
    )


def _phat_hanh_that(sess, orders, lsx_svc, admin, customer, **kw) -> int:
    """Một lệnh THẬT (routing + gói phát hành + công việc snapshot) rồi bật `da_phat_hanh`.

    `_dung_lenh` đi luồng đơn → PTG → LSX → sửa routing → `release.phat_hanh`, nhưng
    `release.phat_hanh` KHÔNG đụng `lsx.trang_thai` — cột đó do
    `xep_lich_van_de_service._phat_hanh_ca_cum` gán. Không bật thì lệnh nằm ở `san_sang` và
    `pham_vi.loc_lsx_da_phat_hanh` loại nó ra, mọi bài dưới đây rỗng mà không ai biết vì sao.
    """
    _nhuong_ten_to(sess)
    lsx_id = _dung_lenh(sess, orders, lsx_svc, admin, customer, **kw)
    lsx = sess.get(Lsx, lsx_id)
    lsx.trang_thai = TT_DA_PHAT_HANH
    sess.commit()
    return lsx_id


@pytest.fixture
def lenh_that(sess, orders, lsx_svc, admin, customer) -> int:
    """Lệnh ĐÃ PHÁT HÀNH có routing thật: CTP 15' → In 360' → Đóng gói 60'."""
    _dot_dong_don(sess, 3)
    return _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000), ("Đóng gói", 60, 5000)],
    )


#: Tên nhà gia công của `lenh_thue_ngoai` — bài test so ĐÚNG chuỗi này trên mặt giấy.
NHA_GIA_CONG = "Cơ sở cán màng Minh Long"


@pytest.fixture
def lenh_thue_ngoai(sess, orders, lsx_svc, admin, customer) -> int:
    """Lệnh ĐÃ PHÁT HÀNH có MỘT bước THUÊ NGOÀI mang tên nhà gia công.

    Vì sao phải có fixture riêng: `_dung_lenh` khai cứng `loai_buoc=LB_MAY` cho mọi bước và không
    đụng `nha_cung_cap`, nên trước fixture này KHÔNG bài nào chạy qua nhánh in tên nhà gia công
    của phiếu công nghệ (`phieu_cong_nghe.py`, ô "Loại bước") — một `AttributeError` ở đó cũng
    không ai thấy. Sửa `_dung_lenh` thì đụng 8 fixture của Task 7-12 đang dựa vào nó, nên chỉ
    LẬT một bước sau khi lệnh đã phát hành.

    Lật sau phát hành là hợp lệ, không phải mẹo: `ho_so._routing` đọc thẳng `lsx_cong_doan`
    (`ho_so.py:286-288` lấy `b.loai_buoc` / `b.nha_cung_cap`), không đọc snapshot công việc.

    Cán màng là khâu xưởng in offset hay thuê ngoài thật, nên bước cuối mang đúng nghĩa.
    """
    _dot_dong_don(sess, 5)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000), ("Cán màng", 90, 5000)],
    )
    buoc_cuoi = (
        sess.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id, LsxCongDoan.ten == "Cán màng")
        .one()
    )
    buoc_cuoi.loai_buoc = LB_THUE_NGOAI
    buoc_cuoi.nha_cung_cap = NHA_GIA_CONG
    sess.commit()
    return lsx_id


@pytest.fixture
def lenh_dai(sess, orders, lsx_svc, admin, customer) -> int:
    """Lệnh ĐÃ PHÁT HÀNH với 40 công đoạn tuyến tính — riêng cho bài PDF chia trang
    (`test_lenh_sx_pdf.py::test_lenh_dai_tu_chia_trang`).

    Task 13 map từ `lenh_40_cong_doan` của bản nháp brief: bốn fixture đó KHÔNG tồn tại trong repo
    (viết trước khi Task 10-12 dựng file này) — xem phần "Điều chỉnh của điều phối" ở
    `task-13-brief.md`. Bốn mươi bước tuyến tính là đủ để bảng routing của phiếu công nghệ tràn
    quá một trang A4, không cần hình dạng routing phức tạp (song song/bài ghép) — bài PDF không
    canh điều đó.
    """
    _dot_dong_don(sess, 41)
    return _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[(f"CĐ {i:02d}", 10, 1000) for i in range(1, 41)],
    )


def _cvs(sess, lsx_id: int) -> list[SanXuatCongViec]:
    return (
        sess.query(SanXuatCongViec)
        .filter(SanXuatCongViec.lsx_id == lsx_id)
        .order_by(SanXuatCongViec.id)
        .all()
    )


def _dat_xong_luc(sess, cv: SanXuatCongViec, luc: datetime) -> None:
    """Đóng một bước ĐÚNG HÌNH DẠNG production, nhưng ở một MỐC do bài test chọn.

    `thuc_thi.ket_thuc` đóng phiên đang mở (`loai_dong='ket_thuc'`), đặt `trang_thai='completed'`
    VÀ đóng dấu `hoan_thanh_luc = now` (mig `0256`); `updated_at` mang `onupdate=_utcnow` nên nó
    cũng ghi khoảnh khắc ấy. Fixture chép lại cả bốn thứ đó và chỉ DỜI mốc — không bịa ra hình dạng
    nào production không ghi.

    `hoan_thanh_luc` là cột KPI đọc; `updated_at` vẫn đặt bằng đúng mốc ấy để bài test nào so hai
    cột cũng bắt đầu từ chỗ production để lại chúng (bằng nhau), rồi mới tách ra khi có đường ghi
    khác chạm vào. Cả hai phải ghi bằng Core `update()` nêu đích danh cột, vì `onupdate` chỉ tự
    điền cho cột KHÔNG có trong mệnh đề SET.
    """
    sess.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, bat_dau=luc - timedelta(hours=1), ket_thuc=luc,
        loai_dong=PHIEN_KET_THUC,
    ))
    sess.execute(
        update(SanXuatCongViec)
        .where(SanXuatCongViec.id == cv.id)
        .values(trang_thai=CV_HOAN_THANH, hoan_thanh_luc=luc, updated_at=luc)
    )
    sess.commit()
    sess.expire_all()


_dem_bai_ghep = 0


def _lenh_ghep_doi(sess, orders, lsx_svc, admin, customer, *, buoc, ghep_idx: int):
    """HAI lệnh ĐÃ PHÁT HÀNH cùng nằm trên MỘT bài ghép. Trả `(lsx_a, lsx_b, cv_chung)`.

    Vì sao file này phải có fixture bài ghép THẬT: `danh_sach.py` đặt luận cứ của ba đoạn mã lên ca
    in ghép (vế `EXISTS` qua cầu ghép, `cong_viec_du` trong `buoc_hien_tai`, khử trùng `cv`/`kcs`
    trong `summary`). Bước bị ghép phủ KHÔNG đẻ công việc riêng — cả cụm dùng CHUNG một
    `SanXuatCongViec` mang `lsx_id IS NULL` + `bai_ghep_cong_doan_id`
    (`services/san_xuat/snapshot.py`) — nên mọi bài dựng bằng lệnh thường đều chạy trên hình dạng
    KHÔNG có cái mà đoạn mã ấy nói nó xử lý.

    Khác `_dung_lenh(ghep=[...])` của Task 7 ở đúng một điểm: bài ghép ở đó chỉ có MỘT thành viên,
    nên phép khử trùng "một ca ghép phục vụ nhiều lệnh chỉ đếm MỘT" không bao giờ bị thử. Ở đây cả
    hai lệnh cùng vào bài, và cùng được phát hành trong MỘT gói (`release.phat_hanh` nhận cả tập)
    — đúng cách bàn xếp lịch thả một tờ in ghép xuống xưởng.

    Đi đường thật: đơn → PTG → LSX → sửa routing lúc `san_sang` → dựng bài ghép → `phat_hanh`.
    Thứ duy nhất đặt tay sau phát hành là `lsx.trang_thai` (xem `_phat_hanh_that`).
    """
    global _dem_bai_ghep
    _dem_bai_ghep += 1
    a, b = _hai_lsx_san_sang(sess, orders, lsx_svc, admin, customer)
    to = _to_moi(sess, f"Tổ Ghép API {_dem_bai_ghep}", f"TO-GHEP-API-{_dem_bai_ghep}")

    buocs: dict[int, list[LsxCongDoan]] = {}
    for l in (a, b):
        for cd in sess.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == l.id).all():
            sess.delete(cd)
    sess.flush()
    for l in (a, b):
        ds = []
        for i, (ten, sl) in enumerate(buoc):
            cd = LsxCongDoan(
                lsx_id=l.id, thu_tu=i, ten=ten, nhom="print", department_id=to.id,
                loai_buoc=LB_MAY, so_luong_vao=sl, so_luong_ra=sl,
                don_vi_vao="to", don_vi_ra="to",
            )
            sess.add(cd)
            ds.append(cd)
        buocs[l.id] = ds
    sess.flush()
    for ds in buocs.values():
        for i in range(len(ds) - 1):
            sess.add(LsxCongDoanPhuThuoc(buoc_truoc_id=ds[i].id, buoc_sau_id=ds[i + 1].id))
    sess.commit()

    # Bài ghép phải tồn tại TRƯỚC phát hành: `snapshot.dung_cong_viec` đọc bảng phủ để biết bước
    # nào KHÔNG được đẻ công việc riêng. Dựng sau là snapshot đã sai từ gốc.
    sl_ghep = buoc[ghep_idx][1]
    bg = BaiGhep(ma=f"GB-API-{_dem_bai_ghep}", ten="Bài ghép API")
    sess.add(bg)
    sess.flush()
    chung = BaiGhepCongDoan(
        bai_ghep_id=bg.id, thu_tu=0, ten="Ca chạy ghép", nhom="print", department_id=to.id,
        loai_buoc=LB_MAY, so_luong_vao=sl_ghep, so_luong_ra=sl_ghep,
        don_vi_vao="to", don_vi_ra="to",
    )
    sess.add(chung)
    sess.flush()
    for l in (a, b):
        sess.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=l.id, so_con_tren_to=2))
        sess.add(BaiGhepCongDoanMap(
            bai_ghep_cong_doan_id=chung.id, lsx_id=l.id,
            lsx_step_key=buocs[l.id][ghep_idx].step_key,
        ))
    sess.commit()

    release.phat_hanh(sess, lsx_ids={a.id, b.id}, bai_ghep_ids={bg.id}, actor=admin)
    sess.commit()
    for l in (a, b):
        l.trang_thai = TT_DA_PHAT_HANH
    sess.commit()

    cv_chung = (
        sess.query(SanXuatCongViec).filter_by(bai_ghep_cong_doan_id=chung.id).one()
    )
    # Chốt TIỀN ĐỀ của mọi bài dùng fixture này: nếu bước ghép vẫn đẻ công việc riêng thì
    # `cong_viec[lsx_id]` đã đủ và các bài dưới đây canh trên hình dạng sai.
    assert cv_chung.lsx_id is None
    assert not sess.query(SanXuatCongViec).filter(
        SanXuatCongViec.lsx_id == a.id, SanXuatCongViec.ten_cong_doan == buoc[ghep_idx][0]
    ).count(), "bước bị ghép phủ KHÔNG được đẻ công việc riêng"
    return a.id, b.id, cv_chung


@pytest.fixture
def ghep_doi(sess, orders, lsx_svc, admin, customer):
    """Hai lệnh chung một ca in ghép: CTP riêng → In GHÉP → Đóng gói riêng."""
    _dot_dong_don(sess, 9)
    return _lenh_ghep_doi(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 500), ("In", 5000), ("Đóng gói", 5000)], ghep_idx=1,
    )


def _giao_nguoi(sess, admin, cv, *, ma: str, ten: str) -> int:
    """Giao MỘT người vào công việc bằng ĐÚNG đường ghi production. Trả `san_xuat_phan_cong.id`.

    Gọi `thuc_thi.phan_cong` chứ không `db.add(SanXuatPhanCong(...))`: service còn chụp
    `la_luong_khoan`, mở khoảng tham gia khi việc đang chạy và soi luật bước nội bộ. Dựng tay một
    dòng mà production không bao giờ ghi như thế là bài test canh một hình dạng không tồn tại.

    `_gate` (`thuc_thi.py:63`) chỉ cho TỔ TRƯỞNG đúng tổ ghi, mà `_to_moi` của fixture tạo tổ
    KHÔNG có `head_user_id` — nên phải trao quyền tổ trưởng cho `admin` trước, đúng như dữ liệu
    thật (mọi tổ sản xuất đều có tổ trưởng).
    """
    to = sess.get(Department, cv.department_id)
    if to.head_user_id != admin.id:
        to.head_user_id = admin.id
        sess.commit()
    emp = Employee(code=ma, full_name=ten, department_id=to.id)
    sess.add(emp)
    sess.commit()
    thuc_thi.phan_cong(sess, user=admin, cong_viec_id=cv.id, employee_id=emp.id)
    sess.expire_all()
    return (
        sess.query(SanXuatPhanCong)
        .filter(
            SanXuatPhanCong.cong_viec_id == cv.id,
            SanXuatPhanCong.employee_id == emp.id,
            SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
        )
        .one()
        .id
    )


def _chay_that(sess, admin, cv, *, ma: str, ten: str) -> None:
    """Cho một bước chạy rồi kết thúc bằng ĐÚNG hai lệnh production, không đặt cột nào bằng tay.

    Ba cửa của `thuc_thi.bat_dau` phải mở đúng thứ tự, không cửa nào đi vòng được:
      · `has_piece_work` của TỔ — `_la_luong_khoan` soi cờ này lúc `phan_cong` chụp roster, không
        bật thì `bat_dau` chặn “phải có ít nhất một thợ lương khoán”. Bật TRƯỚC khi giao người,
        vì cờ được CHỤP vào dòng phân công chứ không tra lại lúc bắt đầu.
      · `ly_do_so_nguoi` — roster một người thường lệch `so_nhan_cong_tieu_chuan` của snapshot.
      · `ly_do_tre` — `du_kien_bat_dau` của lệnh dựng sẵn nằm ở quá khứ.
    Truyền cả hai lý do vô điều kiện là an toàn: không lệch/không trễ thì service tự bỏ qua.
    """
    to = sess.get(Department, cv.department_id)
    to.has_piece_work = True
    sess.commit()
    _giao_nguoi(sess, admin, cv, ma=ma, ten=ten)
    thuc_thi.bat_dau(
        sess, user=admin, cong_viec_id=cv.id,
        ly_do_tre="Chờ giấy về", ly_do_so_nguoi="Tổ thiếu người",
    )
    thuc_thi.ket_thuc(sess, user=admin, cong_viec_id=cv.id, ly_do_tre="Máy kẹt giữa ca")
    sess.expire_all()
