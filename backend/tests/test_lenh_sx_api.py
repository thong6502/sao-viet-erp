"""API danh sách Lệnh sản xuất — phân trang + lọc Ở MÁY CHỦ, phạm vi gắn từ QUYỀN.

Ba thứ phải đúng ngay từ đầu, sửa sau rất đắt:
  · `page_size` cắt ở MÁY CHỦ, không kéo cả bảng về rồi slice ở trình duyệt.
  · Client KHÔNG được tự truyền `sale_user_id` để nới phạm vi — backend tự gắn từ token.
  · Response không mang một con số tiền nào.

BA FIXTURE của brief KHÔNG có sẵn ở đâu trong repo (`hai_muoi_lenh`, `sale_khac`, `lenh_nhap` —
đã grep) nên dựng hết ở đây. Hai fixture CÓ thật giữ nguyên: `client` + `seed_credentials`
(`tests/conftest.py:38,51`).

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
from sqlalchemy import event, update

from app.db import SessionLocal, engine
from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from app.models.customer import Customer
from app.models.department import Department
from app.models.employee import Employee
from app.models.lsx import (
    LB_MAY, TT_DA_PHAT_HANH, TT_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from app.models.order import Order, OrderLine
from app.models.san_xuat import CV_DANG_CHAY, CV_HOAN_THANH, CV_TAM_DUNG, SanXuatCongViec
from app.models.san_xuat_kcs import SanXuatKcsBatch
from app.models.san_xuat_thuc_thi import (
    PC_HOAT_DONG, PHIEN_KET_THUC, SanXuatPhanCong, SanXuatPhienChay,
)
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.lsx_repo import LsxRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.accounting_service import AccountingService
from app.services.lenh_sx import danh_sach, trang_thai
from app.services.lsx_service import LsxService
from app.services.order_service import OrderService
from app.services.san_xuat import release, thuc_thi
from app.services.sequence_service import SequenceService

# Plain function (KHÔNG phải fixture) — xem docstring module. `_giao_xong` dựng yêu cầu giao +
# chuyến ĐÃ CÓ KẾT QUẢ, tức số THỰC NHẬN (`delivery_trip_lines.qty_giao`) — đường DUY NHẤT làm một
# lệnh rơi vào tab Hoàn thành; docstring của nó giải thích vì sao không được đếm `qty` yêu cầu.
from tests.test_lenh_sx_tien_do import _cv_ghep, _dung_lenh
from tests.test_lenh_sx_trang_thai import _giao_xong
from tests.test_san_xuat_board import _to_moi
from tests.test_xep_lich_service import _hai_lsx_san_sang

# 02:00 giờ VN ngày 01/09 = 19:00 UTC ngày 31/08. Mọi bài "hôm nay" đo bằng mốc này để cài đặt
# tính theo UTC bị bắt ngay (xem `test_summary_cong_doan_xong_theo_gio_xuong`).
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
    in ghép (vế `EXISTS` qua cầu ghép, `cong_viec_du` trong `_buoc_hien_tai`, khử trùng `cv`/`kcs`
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


# --- Bài của brief -------------------------------------------------------------------------------
def test_khong_dang_nhap_401(client):
    assert client.get("/api/lenh-san-xuat").status_code == 401


def test_summary_du_4_kpi(client, seed_credentials):
    h = _h(_tok(client, seed_credentials))
    r = client.get("/api/lenh-san-xuat/summary", headers=h)
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {
        "dang_sx", "cong_doan_xong_hom_nay", "du_kien_tre", "ty_le_kcs_dat_hom_nay"
    }


def test_phan_trang_o_may_chu(client, seed_credentials, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page=1&page_size=5", headers=h).json()
    assert len(d["items"]) == 5
    assert d["total"] >= 20


def test_client_khong_tu_noi_pham_vi(client, seed_credentials, sale_khac):
    h = _h(_tok(client, seed_credentials))
    a = client.get("/api/lenh-san-xuat", headers=h).json()["total"]
    b = client.get(f"/api/lenh-san-xuat?sale_user_id={sale_khac.id}", headers=h).json()["total"]
    assert a == b, "tham số lạ trên URL không được đổi phạm vi"


def test_khong_lo_tien(client, seed_credentials, lenh_that):
    """Đọc trên lệnh THẬT (có routing + snapshot), không phải trên danh sách rỗng — bài "không lộ
    tiền" chạy trên body rỗng thì xanh vĩnh viễn."""
    h = _h(_tok(client, seed_credentials))
    r = client.get("/api/lenh-san-xuat", headers=h)
    assert r.json()["total"] >= 1
    body = r.text.lower()
    for cam in ("don_gia", "gia_von", "thanh_tien", "luong_khoan", "chi_phi"):
        assert cam not in body, f"lộ {cam}"


def test_lenh_nhap_khong_hien(client, seed_credentials, lenh_nhap):
    h = _h(_tok(client, seed_credentials))
    ids = {i["id"] for i in client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()["items"]}
    assert lenh_nhap not in ids


# --- Phân trang: cắt Ở MÁY CHỦ, không phải slice ở client -----------------------------------------
def test_hai_trang_roi_nhau_va_gop_lai_du(client, seed_credentials, hai_muoi_lenh):
    """Trang 1 và trang 2 không được lặp dòng, và gộp lại phải phủ đúng 20 lệnh của fixture.

    Cắt trang mà quên sắp thứ tự ổn định thì bài này đỏ ngẫu nhiên — đó chính là điều cần bắt.
    """
    h = _h(_tok(client, seed_credentials))
    t1 = client.get("/api/lenh-san-xuat?page=1&page_size=10", headers=h).json()
    t2 = client.get("/api/lenh-san-xuat?page=2&page_size=10", headers=h).json()
    a = [i["id"] for i in t1["items"]]
    b = [i["id"] for i in t2["items"]]
    assert len(a) == 10 and len(b) == 10
    assert not (set(a) & set(b)), "hai trang lặp dòng"
    assert set(hai_muoi_lenh) <= set(a) | set(b)
    assert t1["total"] == t2["total"]


def test_total_khong_doi_theo_page_size(client, seed_credentials, hai_muoi_lenh):
    """`total` là số dòng KHỚP BỘ LỌC, không phải số dòng của trang đang xem."""
    h = _h(_tok(client, seed_credentials))
    nho = client.get("/api/lenh-san-xuat?page=1&page_size=3", headers=h).json()
    to = client.get("/api/lenh-san-xuat?page=1&page_size=200", headers=h).json()
    assert nho["total"] == to["total"] == len(to["items"])
    assert len(nho["items"]) == 3


def test_trang_vuot_qua_tra_rong_khong_no(client, seed_credentials, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page=99&page_size=10", headers=h).json()
    assert d["items"] == [] and d["total"] >= 20


# --- `dem_theo_tab`: đếm CẢ TẬP đã lọc, không phải trang đang xem ---------------------------------
def test_dem_theo_tab_dem_ca_tap_khong_chi_trang(client, seed_credentials, hai_muoi_lenh):
    """Số trên tab phải là số của cả tập lọc. Đếm trên `items` của trang là lỗi kinh điển và nó
    IM LẶNG: trang 1 vẫn hiện đủ dòng, chỉ con số trên tab bé đi."""
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page=1&page_size=5", headers=h).json()
    dem = d["dem_theo_tab"]
    assert set(dem) >= set(trang_thai.TAB_CHINH) | {"tat_ca"}
    assert dem["tat_ca"] == d["total"] >= 20
    assert sum(dem[t] for t in trang_thai.TAB_CHINH) == dem["tat_ca"]
    assert len(d["items"]) == 5


def test_dem_theo_tab_theo_bo_loc_khac(client, seed_credentials, hai_muoi_lenh, lenh_that):
    """Đổi bộ lọc (không phải tab) thì số trên tab phải đổi theo — tab là FACET của tập đã lọc."""
    h = _h(_tok(client, seed_credentials))
    het = client.get("/api/lenh-san-xuat", headers=h).json()["dem_theo_tab"]["tat_ca"]
    loc = client.get("/api/lenh-san-xuat?q=LSX-DS-0", headers=h).json()["dem_theo_tab"]["tat_ca"]
    assert loc < het


def test_loc_tab_o_may_chu(client, seed_credentials, sess, hai_muoi_lenh, lenh_that):
    """Chọn một tab thì `items` chỉ còn lệnh của tab đó, và `total` co lại theo — nhưng
    `dem_theo_tab` GIỮ NGUYÊN (tab không tự lọc chính số đếm của mình).

    Tập fixture phải KHÔNG ĐỒNG NHẤT, và bài phải tự kiểm điều đó. Mọi lệnh chưa giao ở đây đều
    rơi vào MỘT tab (`canh_bao` — chúng chưa giữ đủ vật tư); nếu chỉ có chúng thì lọc tab là phép
    rỗng và bài vẫn xanh kể cả khi cài đặt bỏ hẳn mệnh đề lọc — nghi thức đột biến đã bắt đúng lỗ
    đó ở bản đầu. `lenh_that` được giao ĐỦ cho khách để rơi sang `hoan_thanh`: nhánh ấy đứng TRƯỚC
    mọi cờ cảnh báo trong `trang_thai_chinh:346`, nên nó tách khỏi tập kia một cách chắc chắn.
    """
    h = _h(_tok(client, seed_credentials))
    _giao_xong(sess, lenh_that, sess.get(Lsx, lenh_that).so_luong_dat, ma="YCGH-DS-TAB")

    het = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    assert len({i["trang_thai"] for i in het["items"]}) >= 2, "tập đồng nhất — bài mất tiền đề"
    tab = trang_thai.TAB_HOAN_THANH
    assert 0 < het["dem_theo_tab"][tab] < het["total"], "tab đang xét phải là tập CON thật sự"

    d = client.get(f"/api/lenh-san-xuat?tab={tab}&page_size=200", headers=h).json()
    assert d["total"] == het["dem_theo_tab"][tab] < het["total"]
    assert {i["trang_thai"] for i in d["items"]} == {tab}
    assert [i["id"] for i in d["items"]] == [lenh_that]
    assert d["dem_theo_tab"] == het["dem_theo_tab"]


def test_tab_la_gia_tri_khong_hop_le_bi_chan(client, seed_credentials):
    h = _h(_tok(client, seed_credentials))
    assert client.get("/api/lenh-san-xuat?tab=lung_tung", headers=h).status_code == 422


# --- Bộ lọc ở TẦNG SQL ---------------------------------------------------------------------------
def test_q_tim_theo_ma(client, seed_credentials, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?q=LSX-DS-07", headers=h).json()
    assert [i["ma"] for i in d["items"]] == ["LSX-DS-07"]
    assert d["total"] == 1
    assert client.get("/api/lenh-san-xuat?q=KHONG-CO-MA-NAY", headers=h).json()["total"] == 0


def test_q_tim_theo_ten_khach(client, seed_credentials, hai_muoi_lenh):
    """Sale gõ tên khách chứ không nhớ mã lệnh — `q` phải với tới `customers.name`."""
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?q=Danh Sách&page_size=200", headers=h).json()
    assert d["total"] >= 20
    assert all(i["khach_hang"] == "Khách Danh Sách" for i in d["items"])


def test_loc_uu_tien_gap(client, seed_credentials, sess, admin, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    gap = _lenh_tho(sess, ma="LSX-DS-GAP", sale_user_id=admin.id, is_rush=True)
    d = client.get("/api/lenh-san-xuat?uu_tien=gap&page_size=200", headers=h).json()
    assert [i["id"] for i in d["items"]] == [gap]
    thuong = client.get("/api/lenh-san-xuat?uu_tien=binh_thuong&page_size=200", headers=h).json()
    assert gap not in {i["id"] for i in thuong["items"]}
    assert thuong["total"] >= 20


def test_lenh_gap_dung_dau_bang(client, seed_credentials, sess, admin, hai_muoi_lenh):
    """Thứ tự mặc định: GẤP trước, rồi tới hạn SX gần nhất. Lệnh gấp nằm cuối bảng thì điều độ
    không thấy nó ở trang 1 — đúng thứ cột `uu_tien` sinh ra để tránh."""
    h = _h(_tok(client, seed_credentials))
    gap = _lenh_tho(
        sess, ma="LSX-DS-GAP2", sale_user_id=admin.id, is_rush=True, han_sx=date(2027, 1, 1)
    )
    d = client.get("/api/lenh-san-xuat?page=1&page_size=5", headers=h).json()
    assert d["items"][0]["id"] == gap


def test_loc_khoang_ngay_theo_han_sx(client, seed_credentials, hai_muoi_lenh):
    """`tu_ngay`/`den_ngay` soi `han_hoan_thanh_sx` — cùng cột mà `tre_han` dùng làm mốc."""
    h = _h(_tok(client, seed_credentials))
    d = client.get(
        "/api/lenh-san-xuat?tu_ngay=2026-09-03&den_ngay=2026-09-05&page_size=200", headers=h
    ).json()
    assert d["total"] == 3
    assert {i["han_hoan_thanh_sx"] for i in d["items"]} == {
        "2026-09-03", "2026-09-04", "2026-09-05"
    }


def test_loc_may_id_theo_snapshot(client, seed_credentials, sess, lenh_that, hai_muoi_lenh):
    """Lọc theo máy phải soi `san_xuat_cong_viec.may_id` — cột mà `thuc_thi.doi_may:486` ghi và
    `snapshot.dung_cong_viec` chép sang lúc phát hành."""
    h = _h(_tok(client, seed_credentials))
    cv = _cvs(sess, lenh_that)[1]
    cv.may_id = 4242
    sess.commit()

    d = client.get("/api/lenh-san-xuat?may_id=4242&page_size=200", headers=h).json()
    assert [i["id"] for i in d["items"]] == [lenh_that]
    assert client.get("/api/lenh-san-xuat?may_id=999999", headers=h).json()["total"] == 0


def test_loc_may_id_bat_ca_buoc_chi_co_o_routing(
    client, seed_credentials, sess, admin, hai_muoi_lenh
):
    """Vế ROUTING của bộ lọc máy: `lsx_cong_doan.may_id`, khi snapshot chưa mang máy ấy.

    ĐỌC KỸ PHẠM VI: bài này KHÔNG canh ca in ghép — docstring cũ khai như vậy nhưng nó không dựng
    bài ghép nào, nên lời khai ấy là sai (rà soát vòng 2 bắt đúng chỗ này). Ca ghép do
    `test_loc_may_id_bat_ca_buoc_ghep` canh, bằng bài ghép thật.

    Cái nó canh THẬT vẫn đáng canh: routing khai máy mà công việc snapshot chưa mang máy đó —
    routing sửa sau phát hành, hoặc lệnh chưa có snapshot nào cho bước ấy. Vế `EXISTS` trên
    `san_xuat_cong_viec` một mình sẽ hụt.
    """
    h = _h(_tok(client, seed_credentials))
    lsx_id = _lenh_tho(sess, ma="LSX-DS-ROUTING-MAY", sale_user_id=admin.id)
    sess.add(LsxCongDoan(lsx_id=lsx_id, thu_tu=0, ten="In", nhom="print", may_id=5151))
    sess.commit()

    d = client.get("/api/lenh-san-xuat?may_id=5151&page_size=200", headers=h).json()
    assert [i["id"] for i in d["items"]] == [lsx_id]


def test_loc_nhom_cong_doan(client, seed_credentials, lenh_that, hai_muoi_lenh):
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?nhom_cong_doan=print&page_size=200", headers=h).json()
    assert [i["id"] for i in d["items"]] == [lenh_that]
    assert client.get("/api/lenh-san-xuat?nhom_cong_doan=khong-co", headers=h).json()["total"] == 0


def test_loc_tre(client, seed_credentials, sess, orders, lsx_svc, admin, customer):
    """`tre` là bộ lọc DẪN XUẤT (tính lúc đọc) — không có cột nào để `WHERE`.

    Hai lệnh THẬT giống hệt nhau trừ hạn SX: một hạn đã qua từ lâu, một hạn còn xa. Cùng routing,
    cùng thời lượng ⇒ chỉ hạn quyết định, không có biến nào khác lẫn vào.
    """
    h = _h(_tok(client, seed_credentials))
    _dot_dong_don(sess, 5)
    som = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)],
    )
    muon = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)],
    )
    sess.get(Lsx, som).han_hoan_thanh_sx = date(2020, 1, 1)     # đã quá hạn
    sess.get(Lsx, muon).han_hoan_thanh_sx = date(2099, 1, 1)    # còn rất xa
    sess.commit()

    tre = client.get("/api/lenh-san-xuat?tre=true&page_size=200", headers=h).json()
    assert som in {i["id"] for i in tre["items"]}
    assert muon not in {i["id"] for i in tre["items"]}
    khong = client.get("/api/lenh-san-xuat?tre=false&page_size=200", headers=h).json()
    assert muon in {i["id"] for i in khong["items"]}
    assert som not in {i["id"] for i in khong["items"]}
    assert tre["total"] + khong["total"] == client.get(
        "/api/lenh-san-xuat", headers=h
    ).json()["total"]


# --- Phạm vi bám QUYỀN, không bám URL ------------------------------------------------------------
def test_pham_vi_own_chi_thay_lenh_cua_minh(
    client, sale_own, lenh_cua_sale_own, hai_muoi_lenh
):
    """Vai "NV Sales" (scope `own`) chỉ thấy lệnh của ĐƠN MÌNH BÁN.

    Đây là bài canh THẬT của phạm vi; bài `test_client_khong_tu_noi_pham_vi` của brief chỉ chứng
    minh một tham số lạ bị bỏ qua (FastAPI vốn bỏ qua query param không khai), nó KHÔNG chứng minh
    phạm vi có được gắn hay không.
    """
    h = _h(create_access_token(str(sale_own.id)))
    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    assert [i["id"] for i in d["items"]] == [lenh_cua_sale_own]
    assert d["total"] == 1


def test_summary_cung_theo_pham_vi(client, sale_own, lenh_cua_sale_own, hai_muoi_lenh):
    """KPI phải hẹp theo cùng phạm vi với bảng — nếu không, Sale nhìn thấy con số của cả nhà máy
    bên trên một cái bảng chỉ có một dòng."""
    h = _h(create_access_token(str(sale_own.id)))
    r = client.get("/api/lenh-san-xuat/summary", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dang_sx"] == 1


# --- KPI -----------------------------------------------------------------------------------------
def test_summary_dang_sx_va_du_kien_tre(sess, orders, lsx_svc, admin, customer):
    """`dang_sx` = lệnh CHƯA ra khỏi nhà máy; `du_kien_tre` là tập con của nó.

    BA lệnh, và lệnh thứ ba là phần LOAD-BEARING: nó đã giao đủ cho khách ⇒ `hoan_thanh` ⇒ KHÔNG
    được tính vào `dang_sx`. Thiếu nó thì mọi lệnh trong bài đều dở dang, và cài đặt đếm HẾT (bỏ
    hẳn phép loại lệnh xong) vẫn ra đúng số — nghi thức đột biến đã bắt đúng lỗ đó ở bản đầu.

    Lệnh xong cũng KHÔNG được tính vào `du_kien_tre` dù hạn đã qua từ 2020: hàng đã tới tay khách
    thì không còn "dự kiến" nào để trễ nữa.

    Gọi thẳng service để chốt được `bay_gio` — cùng lý do `tien_do.gio_may` nhận tham số ấy.
    """
    _dot_dong_don(sess, 4)
    som = _phat_hanh_that(sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)])
    muon = _phat_hanh_that(sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)])
    xong = _phat_hanh_that(sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)])
    sess.get(Lsx, som).han_hoan_thanh_sx = date(2020, 1, 1)
    sess.get(Lsx, muon).han_hoan_thanh_sx = date(2099, 1, 1)
    sess.get(Lsx, xong).han_hoan_thanh_sx = date(2020, 1, 1)     # quá hạn, nhưng đã giao xong
    sess.commit()
    _giao_xong(sess, xong, sess.get(Lsx, xong).so_luong_dat, ma="YCGH-DS-KPI")

    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["dang_sx"] == 2, "lệnh đã giao đủ không còn 'đang sản xuất'"
    assert kq["du_kien_tre"] == 1


def test_summary_cong_doan_xong_theo_gio_xuong(sess, orders, lsx_svc, admin, customer):
    """"Hôm nay" của KPI là NGÀY GIỜ XƯỞNG (+7), không phải ngày UTC.

    `BAY_GIO` = 31/08 19:00 UTC = 01/09 02:00 giờ VN (ca đêm). Bước đóng lúc 31/08 20:00 UTC
    = 01/09 03:00 giờ VN ⇒ CÙNG ngày xưởng, nhưng ngày UTC thì là HÔM QUA. Cài đặt tính theo UTC
    sẽ trả 0. Bước đóng lúc 31/08 15:00 UTC (= 31/08 22:00 giờ VN) là ngày xưởng TRƯỚC ⇒ không đếm.
    """
    _dot_dong_don(sess, 6)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000)],
    )
    cvs = _cvs(sess, lsx_id)
    _dat_xong_luc(sess, cvs[0], datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc))   # hôm qua
    _dat_xong_luc(sess, cvs[1], datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc))   # hôm nay

    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["cong_doan_xong_hom_nay"] == 1


def test_summary_ty_le_kcs_hom_nay(sess, orders, lsx_svc, admin, customer):
    """Tỷ lệ = Σ đạt / Σ nhận của các batch KẾT THÚC trong ngày xưởng, tính theo SỐ chứ không phải
    trung bình cộng các batch — batch 10 cái và batch 10.000 cái không cân nhau."""
    _dot_dong_don(sess, 2)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer, buoc=[("In", 60, 1000)],
    )
    cv = _cvs(sess, lsx_id)[0]
    trong = datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc)      # ngày xưởng 01/09
    ngoai = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)      # ngày xưởng 31/08
    for luc, nhan, dat in ((trong, 900, 800), (trong, 100, 100), (ngoai, 500, 0)):
        sess.add(SanXuatKcsBatch(
            cong_viec_id=cv.id, bat_dau=luc - timedelta(hours=1), ket_thuc=luc,
            so_luong_nhan=nhan, so_luong_dat=dat, so_luong_khong_dat=nhan - dat, don_vi="to",
        ))
    sess.commit()

    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["ty_le_kcs_dat_hom_nay"] == pytest.approx(90.0)


def test_summary_kcs_khong_kiem_gi_tra_none(sess):
    """Không kiểm cái nào thì trả `None` (UI hiện "—"). Trả 0.0 là nói "0% đạt" — một lời báo
    động sai, và nó xuất hiện đúng vào mỗi sáng sớm."""
    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["ty_le_kcs_dat_hom_nay"] is None


# --- Nội dung một dòng ----------------------------------------------------------------------------
def test_item_du_truong_nghiep_vu(client, seed_credentials, sess, lenh_that):
    """Dòng bảng phải đủ cho các cột đã chốt: Mã · Sản phẩm/SL · Khách · Máy · Công đoạn + tiến độ
    · Hạn/Dự kiến · Trạng thái."""
    h = _h(_tok(client, seed_credentials))
    cvs = _cvs(sess, lenh_that)
    cvs[0].trang_thai = CV_HOAN_THANH
    cvs[1].trang_thai = CV_DANG_CHAY
    cvs[1].may_id = 4242
    sess.commit()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert {
        "id", "ma", "ten", "khach_hang", "sale", "so_luong_dat", "don_vi_tinh", "da_giao",
        "is_rush", "buoc_hien_tai", "nhom_cong_doan", "may", "tien_do_pct", "tien_do_uoc_tinh",
        "gio_may", "han_hoan_thanh_sx", "han_giao_khach", "du_kien_xong", "trang_thai",
        "canh_bao",
    } <= set(row)
    assert row["ma"]
    assert row["buoc_hien_tai"] == "In", "phải là bước ĐANG CHẠY, không phải bước đầu routing"
    assert row["nhom_cong_doan"] == "print"
    assert row["trang_thai"] in trang_thai.TAB_CHINH
    assert set(row["canh_bao"]) <= set(trang_thai.CO_CANH_BAO)
    # CTP 15' xong / (15+360+60)' ⇒ ~3,4%. Chia đều 3 bước sẽ ra 33% — con số nói dối điều độ.
    assert row["tien_do_pct"] == pytest.approx(100 * 15 / 435, abs=0.01)


def test_khach_hang_id_ra_toi_response_va_dung_khach(
    client, seed_credentials, sess, admin, customer
):
    """Mỗi dòng mang `khach_hang_id` CỦA CHÍNH ĐƠN mình — khoá để FE bấm sang hồ sơ khách.

    Đi qua HTTP chứ không gọi thẳng service, và đó là phần LOAD-BEARING: `LenhSxItem` là
    `response_model`, mà Pydantic BỎ IM LẶNG mọi khoá service trả nhưng schema không khai. Bài gọi
    thẳng service vẫn xanh cả khi trường rơi mất đúng trên đường ra.

    Ba lệnh, ba cảnh (khách A, khách B, chưa có khách) để bài không xanh nhờ “trả đại một id nào
    đó”: id phải khớp đúng khách của từng đơn, và đơn chưa gắn khách phải ra `None` chứ không
    phải một id gần đúng.
    """
    kh2 = Customer(code="KH-DS-2", name="Khách Danh Sách Hai")
    sess.add(kh2)
    sess.commit()
    _dot_dong_don(sess, 4)
    a = _lenh_tho(sess, ma="LSX-DS-KH1", sale_user_id=admin.id, customer_id=customer.id)
    b = _lenh_tho(sess, ma="LSX-DS-KH2", sale_user_id=admin.id, customer_id=kh2.id)
    khong = _lenh_tho(sess, ma="LSX-DS-KH0", sale_user_id=admin.id, customer_id=None)

    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    dong = {i["id"]: i for i in d["items"]}
    assert dong[a]["khach_hang_id"] == customer.id
    assert dong[a]["khach_hang"] == customer.name
    assert dong[b]["khach_hang_id"] == kh2.id
    assert dong[b]["khach_hang"] == kh2.name
    assert dong[khong]["khach_hang_id"] is None, "đơn chưa gắn khách ⇒ None, không phải id bịa"


def test_buoc_hien_tai_uu_tien_buoc_dang_chay(client, seed_credentials, sess, lenh_that):
    """Cột Công đoạn hiện bước ĐANG CHẠY, kể cả khi một bước TRƯỚC nó còn chưa bắt đầu.

    Ca này có thật ở xưởng: máy in chạy trước trong khi chế bản còn đang chờ bản mới cho tay kê
    thứ hai. Chọn "bước chờ sớm nhất" ở đây là hiện "CTP" trong lúc máy in đang gầm — điều độ đọc
    bảng sẽ đi tìm nhầm chỗ. Không có bài này thì phép ưu tiên ĐANG CHẠY không có lưới: mọi ca
    khác đều để bước đang chạy trùng luôn với bước chờ sớm nhất.
    """
    h = _h(_tok(client, seed_credentials))
    cvs = _cvs(sess, lenh_that)                       # CTP · In · Đóng gói
    cvs[1].trang_thai = CV_DANG_CHAY                  # CTP vẫn 'released', chưa ai bấm
    sess.commit()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["buoc_hien_tai"] == "In", "phải là bước ĐANG CHẠY, không phải bước chờ sớm nhất"


def test_buoc_hien_tai_uu_tien_buoc_tam_dung(client, seed_credentials, sess, lenh_that):
    """Không có bước nào chạy thì bước TẠM DỪNG mới là nơi lệnh đang mắc — vẫn hơn bước chờ."""
    h = _h(_tok(client, seed_credentials))
    cvs = _cvs(sess, lenh_that)
    cvs[1].trang_thai = CV_TAM_DUNG
    sess.commit()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["buoc_hien_tai"] == "In"


def test_item_may_lay_ten_tu_danh_muc(client, seed_credentials, sess, lenh_that):
    """Cột Máy hiện TÊN máy, không phải id — và id trỏ hụt danh mục thì để trống chứ không nổ."""
    from app.models.may_thiet_bi import MayThietBi

    h = _h(_tok(client, seed_credentials))
    may = MayThietBi(ma="MAY-DS-01", ten="Máy in Komori 5 màu", loai_may="press_offset_sheet")
    sess.add(may)
    sess.flush()
    cv = _cvs(sess, lenh_that)[1]
    cv.trang_thai = CV_DANG_CHAY
    cv.may_id = may.id
    sess.commit()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["may"] == "Máy in Komori 5 màu"


def test_may_lay_duoc_khi_chua_co_phien_nao(client, seed_credentials, sess, lenh_that):
    """Bước ĐÃ XẾP MÁY mà CHƯA ai bấm chạy vẫn phải hiện tên máy.

    Đây là trạng thái phổ biến NHẤT của một lệnh vừa phát hành: lịch đã chỉ định máy, còn phiên
    chạy thì chưa có dòng nào. Nếu câu gom máy của `boi_canh` chỉ nhặt `phien.may_id` /
    `su_co.may_id` thì đúng lúc điều độ cần biết "việc này nằm ở máy nào" cột Máy lại trống — và
    trống một cách IM LẶNG: không lỗi, không cảnh báo, chỉ là một ô rỗng trông y hệt "chưa xếp
    máy". Bài này khoá `cong_viec.may_id` vào câu gom ấy.

    Khác `test_item_may_lay_ten_tu_danh_muc` ở chỗ bước KHÔNG được đặt 'đang chạy' và bài tự
    khẳng định không có phiên nào — nếu không, ca "chưa có phiên" không được canh thật.
    """
    from app.models.may_thiet_bi import MayThietBi

    h = _h(_tok(client, seed_credentials))
    may = MayThietBi(ma="MAY-DS-02", ten="Máy bế Bobst 102", loai_may="press_offset_sheet")
    sess.add(may)
    sess.flush()
    cv = _cvs(sess, lenh_that)[0]          # CTP — bước chờ sớm nhất, giữ nguyên 'released'
    cv.may_id = may.id
    sess.commit()
    assert sess.query(SanXuatPhienChay).filter(
        SanXuatPhienChay.cong_viec_id == cv.id
    ).count() == 0, "bài chỉ có nghĩa khi bước CHƯA có phiên chạy nào"

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["may"] == "Máy bế Bobst 102", "bước đã xếp máy mà chưa chạy phải hiện tên máy"


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


def test_nguoi_rong_khi_chua_giao_ai(client, seed_credentials, lenh_that):
    """Chưa giao ai ⇒ `nguoi` là danh sách RỖNG, không phải `None`, không phải chữ bịa."""
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["nguoi"] == []


def test_nguoi_hien_ca_to_theo_thu_tu_giao(client, seed_credentials, sess, admin, lenh_that):
    """Nhiều người trên một bước là chuyện thường (roster) ⇒ trả ĐỦ tên, theo THỨ TỰ GIAO.

    Trả danh sách chứ không phải chuỗi "A +1" dựng sẵn: cột hẹp thì UI tự cắt (cắt từ cuối được vì
    thứ tự là thứ tự giao), còn tooltip/hồ sơ vẫn có đủ tên mà không phải gọi thêm API.
    """
    h = _h(_tok(client, seed_credentials))
    cv = _cvs(sess, lenh_that)[0]
    _giao_nguoi(sess, admin, cv, ma="NV-DS-01", ten="Nguyễn Văn A")
    _giao_nguoi(sess, admin, cv, ma="NV-DS-02", ten="Trần Thị B")

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["nguoi"] == ["Nguyễn Văn A", "Trần Thị B"]


def test_nguoi_khong_hien_nguoi_da_bi_rut(client, seed_credentials, sess, admin, lenh_that):
    """Người đã bị RÚT khỏi việc không được hiện trên bảng điều độ.

    Rút người ghi `trang_thai='removed'` và GIỮ dòng lại để có lịch sử (`thuc_thi.go_phan_cong`).
    Nếu câu nạp phân công quên điều kiện trạng thái, bảng sẽ khai tên một người KHÔNG còn làm việc
    đó — sai kiểu không gãy gì, chỉ khiến điều độ đi tìm nhầm người. Bước vẫn còn đúng MỘT người
    đang hoạt động nên ô không rỗng: bỏ điều kiện là ra hai tên, thấy ngay.
    """
    h = _h(_tok(client, seed_credentials))
    cv = _cvs(sess, lenh_that)[0]
    pc_a = _giao_nguoi(sess, admin, cv, ma="NV-DS-11", ten="Người đã rút")
    _giao_nguoi(sess, admin, cv, ma="NV-DS-12", ten="Người đang làm")
    thuc_thi.go_phan_cong(sess, user=admin, phan_cong_id=pc_a, ly_do="Chuyển sang tổ khác")
    sess.expire_all()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    row = next(i for i in d["items"] if i["id"] == lenh_that)
    assert row["nguoi"] == ["Người đang làm"], "người đã `removed` không được lên bảng"


# --- Bài ghép: ba luận cứ của `danh_sach.py` mà trước vòng này không lời nào có lưới ------------
def test_loc_may_id_bat_ca_buoc_ghep(client, seed_credentials, sess, ghep_doi):
    """`?may_id=` phải bắt được lệnh mà MÁY nằm ở bước GHÉP — đây là lỗi thật, đã đo.

    Máy của ca in ghép chỉ sống ở công việc CHUNG (`lsx_id IS NULL`): `snapshot` chụp
    `bai_ghep_cong_doan.may_id` vào đó, và KHÔNG chỗ nào ghi ngược về `lsx_cong_doan.may_id`. Vế
    `EXISTS` neo thẳng `cong_viec.lsx_id = lsx.id` không với tới nó, vế routing cũng không — nên
    trước khi có vế thứ ba, bảng HIỆN tên máy mà lọc theo chính máy đó lại trả rỗng. Hai khẳng
    định dưới đây cố ý đi liền nhau vì chính cặp mâu thuẫn ấy là lỗi.
    """
    from app.models.may_thiet_bi import MayThietBi

    h = _h(_tok(client, seed_credentials))
    a, b, cv_chung = ghep_doi
    may = MayThietBi(ma="MAY-GHEP-01", ten="Máy in ghép 9", loai_may="press_offset_sheet")
    sess.add(may)
    sess.flush()
    cv_chung.may_id = may.id            # cột `snapshot` ghi lúc phát hành, `doi_may` ghi lúc chạy
    cv_chung.trang_thai = CV_DANG_CHAY
    sess.commit()

    ca = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    dong = {i["id"]: i for i in ca["items"]}
    assert dong[a]["may"] == "Máy in ghép 9", "bảng phải khai máy của ca ghép"

    loc = client.get(f"/api/lenh-san-xuat?may_id={may.id}&page_size=200", headers=h).json()
    assert {i["id"] for i in loc["items"]} == {a, b}, (
        "bảng khai máy này thì lọc theo chính nó phải ra CẢ HAI lệnh trên tờ ghép"
    )


def test_loc_nhom_cong_doan_bat_ca_buoc_ghep(client, seed_credentials, sess, ghep_doi):
    """PHÒNG THỦ TƯƠNG LAI, không phải ca đang chạy: nhóm ca ghép LỆCH nhóm routing.

    Hình dạng này hôm nay production KHÔNG ghi được, và bài phải đặt tay `cv_chung.nhom_cong_doan`
    chính vì thế. Hai chốt chặn (đã đọc mã, không suy đoán): `bai_ghep_service.gop` từ chối gộp
    các bước khác `cong_doan_id` rồi chép thẳng `chung.nhom = mau.nhom`; và `_SUA_DUOC_BUOC_CHUNG`
    — danh sách trường sửa được của bước chung — KHÔNG có `nhom`. Nên nhóm của công việc chung
    luôn TRÙNG nhóm routing của thành viên, và trong mọi ca thật vế routing bắt hộ.

    Vì sao vẫn giữ: thứ nó canh là LUẬT “lọc theo nhóm phải với tới công việc chung”, chứ không
    phải sự trùng hợp đang đỡ hộ. Ngày nào bước chung cho sửa `nhom` (hoặc phép gộp nới ra khác
    công đoạn), trùng hợp mất mà bài này vẫn đứng. Đừng đọc nó như bằng chứng ca ấy đang xảy ra.
    """
    h = _h(_tok(client, seed_credentials))
    a, b, cv_chung = ghep_doi
    cv_chung.nhom_cong_doan = "finishing"
    sess.commit()
    assert not sess.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id.in_([a, b]), LsxCongDoan.nhom == "finishing"
    ).count(), "routing không được mang nhóm này, nếu không vế routing bắt hộ và bài mất nghĩa"

    d = client.get("/api/lenh-san-xuat?nhom_cong_doan=finishing&page_size=200", headers=h).json()
    assert {i["id"] for i in d["items"]} == {a, b}


def test_buoc_hien_tai_lay_ca_buoc_ghep(client, seed_credentials, sess, ghep_doi):
    """Bước ĐANG CHẠY là ca in GHÉP ⇒ cột Công đoạn phải hiện nó, không phải một bước riêng.

    `_buoc_hien_tai` đọc `bc.cong_viec_du()` chứ không `bc.cong_viec[]` chính vì ca này: công việc
    chung mang `lsx_id IS NULL` nên map neo theo lệnh KHÔNG có nó, và bảng sẽ hiện "CTP" trong lúc
    máy in đang gầm. Cột Máy/người đi theo cùng một `cv`, nên mất bước ghép là mất cả ba cột.
    """
    h = _h(_tok(client, seed_credentials))
    a, b, cv_chung = ghep_doi
    cv_chung.trang_thai = CV_DANG_CHAY
    sess.commit()

    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    dong = {i["id"]: i for i in d["items"]}
    assert dong[a]["buoc_hien_tai"] == "Ca chạy ghép"
    assert dong[b]["buoc_hien_tai"] == "Ca chạy ghép", "cả hai lệnh cùng đứng ở ca ghép ấy"


def test_kpi_cong_doan_xong_dem_ca_buoc_ghep_dung_mot_lan(sess, ghep_doi):
    """Ca in ghép đóng hôm nay PHẢI vào KPI, và chỉ đếm MỘT dù phục vụ hai lệnh.

    Hai luật trong một con số: `summary` duyệt `cong_viec_du()` (không thì bước ghép rơi khỏi KPI
    ⇒ 0) và gom vào `set` theo id công việc (không thì một ca đếm thành hai ⇒ 2). Chỉ đáp số 1 mới
    thoả cả hai.
    """
    a, b, cv_chung = ghep_doi
    _dat_xong_luc(sess, cv_chung, datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc))

    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["cong_doan_xong_hom_nay"] == 1


def test_kpi_kcs_khong_dem_lap_batch_cua_buoc_ghep(sess, ghep_doi):
    """Một batch KCS của ca GHÉP là MỘT lần kiểm, không phải một lần cho mỗi lệnh thành viên.

    Bài phải có thêm MỘT batch riêng mang tỷ lệ KHÁC, nếu không nó xanh cả khi khử trùng bị gỡ:
    nhân đôi cả tử lẫn mẫu không đổi thương. Đếm đúng: (0+100) đạt / (100+100) nhận = 50%. Đếm
    lặp batch ghép: 100/300 = 33,3%.
    """
    a, b, cv_chung = ghep_doi
    trong = datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc)
    rieng = _cvs(sess, a)[0]                       # CTP của lệnh a — công việc RIÊNG
    for cv, nhan, dat in ((cv_chung, 100, 0), (rieng, 100, 100)):
        sess.add(SanXuatKcsBatch(
            cong_viec_id=cv.id, bat_dau=trong - timedelta(hours=1), ket_thuc=trong,
            so_luong_nhan=nhan, so_luong_dat=dat, so_luong_khong_dat=nhan - dat, don_vi="to",
        ))
    sess.commit()

    kq = danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO)
    assert kq["ty_le_kcs_dat_hom_nay"] == pytest.approx(50.0), (
        "batch của ca ghép đang được đếm một lần cho MỖI lệnh thành viên"
    )


# --- Ba luật khác mà đột biến từng đi qua không ai cản ------------------------------------------
def test_dem_theo_tab_phan_anh_bo_loc_tre(
    client, seed_credentials, sess, orders, lsx_svc, admin, customer
):
    """`dem_theo_tab` phải tính SAU bộ lọc `tre` — nó là facet của tập ĐANG xem.

    `tre` không phải một tab, nên nếu đếm trước nó thì con số nói về một tập RỘNG HƠN cái bảng
    đang hiện: người dùng bật "chỉ lệnh trễ", thấy 1 dòng, mà tab "Tất cả" vẫn ghi 2. `tab` thì
    ngược lại — phải đếm TRƯỚC nó, nếu không bấm một tab là mọi tab khác về 0.
    """
    h = _h(_tok(client, seed_credentials))
    _dot_dong_don(sess, 5)
    som = _phat_hanh_that(sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)])
    muon = _phat_hanh_that(sess, orders, lsx_svc, admin, customer, buoc=[("In", 120, 5000)])
    sess.get(Lsx, som).han_hoan_thanh_sx = date(2020, 1, 1)
    sess.get(Lsx, muon).han_hoan_thanh_sx = date(2099, 1, 1)
    sess.commit()

    het = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    assert het["dem_theo_tab"][danh_sach.TAB_TAT_CA] == 2, "tiền đề: không lọc thì thấy cả hai"

    tre = client.get("/api/lenh-san-xuat?tre=true&page_size=200", headers=h).json()
    assert tre["total"] == 1
    assert tre["dem_theo_tab"][danh_sach.TAB_TAT_CA] == 1, (
        "facet vẫn đếm cả lệnh không trễ — tức đang đếm TRƯỚC bộ lọc `tre`"
    )
    assert sum(tre["dem_theo_tab"][t] for t in trang_thai.TAB_CHINH) == 1


def test_sap_xep_toan_phan_khi_trung_khoa_chinh(client, seed_credentials, sess, admin, customer):
    """Hai lệnh TRÙNG cả độ gấp lẫn hạn SX ⇒ `lsx.ma` là nấc phân giải cuối của thứ tự.

    Không có nấc đó thì thứ tự chỉ còn là thứ tự DB tình cờ trả về, và cắt trang trên một thứ tự
    KHÔNG TOÀN PHẦN cho phép trang 1 với trang 2 chồng nhau hoặc bỏ sót dòng. SQLite hay "đúng một
    cách tình cờ", nên bài ép hai thứ tự ấy LỆCH nhau: lệnh mã Z tạo TRƯỚC (id nhỏ hơn), lệnh mã A
    tạo SAU. Sắp theo mã ⇒ A trước; rơi về thứ tự id ⇒ Z trước.
    """
    h = _h(_tok(client, seed_credentials))
    hom = date(2026, 9, 9)
    z = _lenh_tho(sess, ma="LSX-SAP-Z", sale_user_id=admin.id, customer_id=customer.id, han_sx=hom)
    a = _lenh_tho(sess, ma="LSX-SAP-A", sale_user_id=admin.id, customer_id=customer.id, han_sx=hom)
    assert z < a, "tiền đề: id tăng theo thứ tự tạo, tức NGƯỢC thứ tự mã"

    t1 = client.get("/api/lenh-san-xuat?page=1&page_size=1", headers=h).json()
    t2 = client.get("/api/lenh-san-xuat?page=2&page_size=1", headers=h).json()
    assert [i["id"] for i in t1["items"]] == [a], "trang 1 phải là lệnh có MÃ nhỏ hơn"
    assert [i["id"] for i in t2["items"]] == [z]
    assert t1["total"] == t2["total"] == 2


def test_canh_bao_thieu_vat_tu_ra_toi_dong(client, seed_credentials, hai_muoi_lenh):
    """Cờ `thieu_vat_tu` phải ra tới dòng bảng — nó là cờ DUY NHẤT phải bơm từ ngoài vào.

    `co_canh_bao` bỏ trống `den_vat_tu` thì im lặng KHÔNG xét cờ này (đúng như docstring của nó
    nói), nên đây cũng là cờ duy nhất mất được mà không gãy gì: tab Cảnh báo hụt người, không lỗi,
    không dấu hiệu. Bốn cờ còn lại tính từ `boi_canh` nên chúng tự có mặt.
    """
    h = _h(_tok(client, seed_credentials))
    d = client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()
    thieu = [i for i in d["items"] if trang_thai.CO_THIEU_VAT_TU in i["canh_bao"]]
    assert thieu, "không dòng nào giương cờ thiếu vật tư — bài đang canh trên rỗng"
    assert d["dem_theo_tab"][trang_thai.TAB_CANH_BAO] >= 1


def test_kpi_khong_bi_go_phan_cong_keo_vao_hom_nay(sess, admin, lenh_that):
    """Rút người khỏi một bước ĐÃ XONG TỪ LÂU không được kéo bước ấy vào KPI hôm nay.

    `go_phan_cong` chỉ kiểm trạng thái DÒNG PHÂN CÔNG, không kiểm trạng thái công việc, rồi
    `cv.version += 1` ⇒ `onupdate` dời `updated_at`. Khi KPI đọc `updated_at`, một bước đóng năm
    2020 nhảy thẳng vào "công đoạn xong hôm nay". Cột `hoan_thanh_luc` (mig `0256`) có mặt để mốc
    NGHIỆP VỤ không lệ thuộc cột BẢO TRÌ — bịt riêng `go_phan_cong` thì đường ghi thêm sau lại phá
    lại đúng chỗ này, âm thầm.

    ĐO Ở MỐC "BÂY GIỜ" THẬT, không phải `BAY_GIO` cố định của file: thứ mà `go_phan_cong` dời
    `updated_at` tới là ĐỒNG HỒ MÁY CHỦ, nên chỉ ngày xưởng chứa đồng hồ ấy mới bắt được lỗi. Đo
    bằng mốc cố định thì bài xanh hay đỏ tuỳ giờ chạy test — tức là không canh gì cả (đã đo: mũi
    đột biến "KPI đọc lại `updated_at`" đi qua sạch khi bài dùng `BAY_GIO`).
    """
    cv = _cvs(sess, lenh_that)[0]
    pc_id = _giao_nguoi(sess, admin, cv, ma="NV-DS-21", ten="Thợ ca cũ")
    xua = datetime(2020, 1, 1, 3, 0, tzinfo=timezone.utc)
    _dat_xong_luc(sess, cv, xua)
    gio = datetime.now(timezone.utc)
    assert danh_sach.summary(sess, sale_ids=None, bay_gio=gio)["cong_doan_xong_hom_nay"] == 0

    thuc_thi.go_phan_cong(sess, user=admin, phan_cong_id=pc_id, ly_do="Nghỉ việc")
    sess.expire_all()
    cv = sess.get(SanXuatCongViec, cv.id)
    assert cv.updated_at.year >= 2026, "tiền đề: `go_phan_cong` CÓ dời `updated_at` về hiện tại"
    assert cv.hoan_thanh_luc.year == 2020, "mốc NGHIỆP VỤ phải đứng yên"
    assert danh_sach.summary(sess, sale_ids=None, bay_gio=gio)["cong_doan_xong_hom_nay"] == 0, (
        "một bước đóng năm 2020 vừa bị kéo vào KPI hôm nay — KPI đang đọc cột BẢO TRÌ"
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


def test_ket_thuc_that_dong_dau_hoan_thanh_luc(sess, admin, lenh_that):
    """ĐƯỜNG GHI THẬT có đóng dấu `hoan_thanh_luc`, và KPI hôm nay nhích lên nhờ chính dấu đó.

    Bài DUY NHẤT của file đi qua `thuc_thi.ket_thuc` thay vì fixture `_dat_xong_luc`. Vì sao cần:
    xoá hẳn dòng `cv.hoan_thanh_luc = now` khỏi `thuc_thi.ket_thuc` mà cả file vẫn XANH (đã đo).
    Fixture không nói dối — nó ghi đúng giá trị production ghi — nhưng vì ghi THẲNG vào cột nên
    không bài nào còn chứng minh production CÒN ghi. Cột KPI mà hỏng đường ghi thì hỏng im lặng:
    con số tụt về 0 vĩnh viễn, không lỗi nào nổ.

    Đo ở mốc “bây giờ” THẬT chứ không `BAY_GIO`: `thuc_thi._moc()` đóng dấu bằng đồng hồ máy chủ
    và không nhận mốc từ ngoài. So DELTA chứ không so số tuyệt đối, để bài không phụ thuộc việc
    nền seed có sẵn bước nào xong trong ngày hay không.
    """
    cv = _cvs(sess, lenh_that)[0]
    gio = datetime.now(timezone.utc)
    truoc = danh_sach.summary(sess, sale_ids=None, bay_gio=gio)["cong_doan_xong_hom_nay"]

    _chay_that(sess, admin, cv, ma="NV-DS-31", ten="Thợ đóng dấu")

    cv = sess.get(SanXuatCongViec, cv.id)
    assert cv.trang_thai == CV_HOAN_THANH, "tiền đề: đường ghi thật có đóng bước"
    assert cv.hoan_thanh_luc is not None, "`ket_thuc` KHÔNG đóng dấu mốc nghiệp vụ"
    sau = danh_sach.summary(sess, sale_ids=None, bay_gio=gio)["cong_doan_xong_hom_nay"]
    assert sau == truoc + 1, (
        "bước vừa đóng bằng đường ghi thật không vào được KPI hôm nay — dấu nghiệp vụ hụt"
    )


def test_ket_thuc_lan_hai_bi_chan_nen_dau_khong_bi_ghi_de(sess, admin, lenh_that):
    """Bước đã `completed` gọi `ket_thuc` lần nữa ⇒ BỊ CHẶN, dấu đứng yên. Hành vi chốt ở đây.

    Câu trả lời không nằm ở dòng đóng dấu mà ở cửa `trang_thai not in (running, paused)` ngay đầu
    hàm: lần gọi thứ hai chết ở cửa, chưa chạm tới phép gán. Nên `hoan_thanh_luc` ghi ĐÚNG MỘT
    LẦN theo cấu trúc chứ không nhờ may — và không có đường nào để một cú bấm lặp kéo bước cũ vào
    KPI hôm nay. Ai sau này viết đường “mở lại bước đã xong” buộc phải mở chính cửa ấy, và bài
    này bắt họ tự quyết định làm gì với cột.
    """
    cv = _cvs(sess, lenh_that)[0]
    _chay_that(sess, admin, cv, ma="NV-DS-32", ten="Thợ đóng dấu hai")
    dau = sess.get(SanXuatCongViec, cv.id).hoan_thanh_luc
    assert dau is not None, "tiền đề: lần đóng đầu tiên đã đóng dấu"

    with pytest.raises(ValueError, match="đang chạy hoặc tạm dừng"):
        thuc_thi.ket_thuc(sess, user=admin, cong_viec_id=cv.id)
    sess.expire_all()
    assert sess.get(SanXuatCongViec, cv.id).hoan_thanh_luc == dau, "dấu nghiệp vụ bị ghi đè"


# --- N+1: số câu SQL hằng TRÊN TRỤC LỆNH (trục BÀI GHÉP thì nở — xem docstring dưới) -------------
def _dem_sql(fn):
    """Đếm câu SQL thật sự gửi xuống driver trong lúc chạy `fn`."""
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


def _nen_hinh_dang_that(sess, orders, lsx_svc, admin, customer) -> tuple[int, int, int]:
    """Tập nền cho hai bài đếm SQL: một tờ in GHÉP (2 lệnh) + một lệnh riêng, có máy và có người.

    Nở tập bằng `_lenh_tho` (lệnh TRẦN — không routing, không công việc) là bài tự vô hiệu hoá
    mình: `_buoc_hien_tai` trả `None` nên `_may_id` / `nguoi_cua` / `bc.may` KHÔNG BAO GIỜ được
    gọi, và bất biến "số câu không nở" chỉ được chứng minh trên phần RỖNG của hàm. Vòng rà soát 2
    chỉ đúng lỗ đó. Ở đây mọi nhánh có thể sinh câu SQL đều được chạm, và bài tự chốt điều ấy
    trước khi đo.
    """
    from app.models.may_thiet_bi import MayThietBi

    a, b, cv_chung = _lenh_ghep_doi(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 500), ("In", 5000), ("Đóng gói", 5000)], ghep_idx=1,
    )
    rieng = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In", 360, 5000)],
    )
    may = MayThietBi(ma="MAY-SQL-01", ten="Máy đo SQL", loai_may="press_offset_sheet")
    sess.add(may)
    sess.flush()
    cv_chung.may_id = may.id
    cv_chung.trang_thai = CV_DANG_CHAY
    sess.commit()
    _giao_nguoi(sess, admin, _cvs(sess, rieng)[0], ma="NV-SQL-01", ten="Thợ đo SQL")
    return a, b, rieng


def test_so_cau_sql_hang_tren_truc_lenh(sess, orders, lsx_svc, admin, customer):
    """Một request tốn SỐ CÂU SQL CỐ ĐỊNH khi thêm LỆNH — và CHỈ trên trục lệnh.

    Đây là lý do cả tầng `lenh_sx` tồn tại (`boi_canh.nap` = 21 câu bất kể số lệnh). Ai lỡ gọi
    `nap()` / `den_vat_tu_theo_lo()` trong vòng lặp từng lệnh sẽ bị bắt tại đây, chứ không phải ở
    màn hình sáu tháng sau. Tập nở bằng lệnh có ROUTING + SNAPSHOT (xem `_nen_hinh_dang_that`), vì
    trên lệnh trần bài không chạm được nhánh nào có thể nở.

    TÊN BÀI NÓI ĐÚNG THỨ NÓ CANH — không hơn. Trục còn lại, số BÀI GHÉP, thì số câu CÓ nở: +28
    câu mỗi bài ghép (đo được 90 → 98 khi thêm hai lệnh thường rồi phẳng, → 126 → 154 khi thêm
    bài ghép). Nguồn nằm NGOÀI tầng này — hai vòng `for bg in bais` trong
    `ke_hoach_vat_tu_service._gom_nhu_cau` — và phán quyết C68 để nó lại cho một task riêng. Bài
    này KHÔNG canh trục đó; tên cũ `..._khong_no_theo_so_lenh` hứa rộng hơn nội dung nó có.
    """
    _dot_dong_don(sess, 8)
    a, _b, rieng = _nen_hinh_dang_that(sess, orders, lsx_svc, admin, customer)

    # Chốt TIỀN ĐỀ: ba nhánh đắt tiền đều được đi qua trong lần đo dưới đây.
    dong = {
        i["id"]: i
        for i in danh_sach.danh_sach(sess, sale_ids=None, bay_gio=BAY_GIO)["items"]
    }
    assert dong[a]["buoc_hien_tai"] == "Ca chạy ghép", "nhánh công việc GHÉP chưa được chạm"
    assert dong[a]["may"] == "Máy đo SQL", "nhánh tra danh mục MÁY chưa được chạm"
    assert dong[rieng]["nguoi"] == ["Thợ đo SQL"], "nhánh tra NHÂN SỰ chưa được chạm"

    n3 = _dem_sql(lambda: danh_sach.danh_sach(sess, sale_ids=None, bay_gio=BAY_GIO))
    for _ in range(2):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n5 = _dem_sql(lambda: danh_sach.danh_sach(sess, sale_ids=None, bay_gio=BAY_GIO))
    assert len(danh_sach.danh_sach(sess, sale_ids=None, bay_gio=BAY_GIO)["items"]) == 5
    assert n3 == n5, f"số câu SQL nở theo số lệnh: {n3} → {n5}"


def test_summary_so_cau_sql_hang_tren_truc_lenh(sess, orders, lsx_svc, admin, customer):
    """Cùng bất biến cho `summary`, đo trên hình dạng thật — và cũng CHỈ trên trục LỆNH."""
    _dot_dong_don(sess, 8)
    _nen_hinh_dang_that(sess, orders, lsx_svc, admin, customer)

    n3 = _dem_sql(lambda: danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO))
    for _ in range(2):
        _phat_hanh_that(
            sess, orders, lsx_svc, admin, customer,
            buoc=[("CTP", 15, 500), ("In", 360, 5000)],
        )
    n5 = _dem_sql(lambda: danh_sach.summary(sess, sale_ids=None, bay_gio=BAY_GIO))
    assert n5 == n3, f"số câu SQL của summary nở theo số lệnh: {n3} → {n5}"
