"""Nạp bối cảnh theo LÔ — luật sống còn là KHÔNG N+1: số câu SQL không được tăng theo số lệnh.

Đo bằng cách đếm câu lệnh qua event `before_cursor_execute`. 1 lệnh và 12 lệnh phải ra CÙNG
một số câu. Đây là thứ duy nhất giữ cho màn danh sách 200 lệnh không sập.

Fixture `mot_lenh`/`muoi_hai_lenh` KHÔNG có sẵn ở đâu trong repo (đã grep `tests/`) — brief gốc
chỉ mô tả Ý ĐỊNH, dựng ở đây theo khuôn `_phat_hanh_vao_to` (đơn thật → PTG 2 thành phần → LSX →
phát hành vào một tổ), tái dùng nguyên luồng test bàn Thực hiện SX.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import event

from app.models.bai_ghep import BaiGhep, BaiGhepThanhVien
from app.models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from app.models.delivery import DeliveryRequest, DeliveryRequestLine
from app.models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.order import Order, OrderLine
from app.models.san_xuat import SanXuatCongViec
from app.models.san_xuat_kcs import SanXuatKcsBatch
from app.models.san_xuat_kho import SanXuatKhoHang, SanXuatNhapKhoYc
from app.models.san_xuat_thuc_thi import SanXuatPhienChay
from app.services.lenh_sx import boi_canh
from app.services.san_xuat import release

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, _to_moi, admin, customer, db, lsx_svc, orders,
)
from tests.test_xep_lich_service import _hai_lsx_san_sang


def _dem_sql(db, fn):
    n = 0

    def _bat(*a, **k):
        nonlocal n
        n += 1

    event.listen(db.get_bind(), "before_cursor_execute", _bat)
    try:
        fn()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _bat)
    return n


# --- Fixtures: lệnh THẬT qua luồng đơn → LSX → phát hành --------------------------------------
@pytest.fixture
def mot_lenh(db, orders, lsx_svc, admin, customer) -> int:
    """Một lệnh ĐÃ PHÁT HÀNH + một phiên chạy đang mở trên công việc đầu tiên của nó — đủ dữ liệu
    để `test_map_dung_khoa` xác nhận map con khớp KHOÁ THẬT, không phải khớp trên bối cảnh rỗng.

    Tiêu một `order_line` mồi TRƯỚC khi dựng lệnh thật: `Lsx` và `OrderLine` là hai bảng riêng,
    id tự tăng ĐỘC LẬP — trong `_hai_lsx_san_sang` mỗi lần luôn sinh ĐÚNG 2 dòng ở cả hai bảng nên
    hai chuỗi id trôi song song, khiến `lsx.id == lsx.order_line_id` LUÔN đúng trên DB test trắng
    (đã xác nhận bằng debug). Nếu để vậy, bài kiểm khoá `giao` (Q3 — theo `order_line_id`, KHÔNG
    theo `lsx_id`) không phân biệt được hai cách khoá — mutation "đổi khoá `giao` sang lsx_id" sẽ
    lọt qua. Tiêu 1 id ở riêng `order_lines` để hai chuỗi lệch nhau từ đây trở đi."""
    mao_don = Order(order_no="DH-BC-MOI")
    db.add(mao_don)
    db.flush()
    db.add(OrderLine(order_id=mao_don.id))
    db.commit()

    to = _to_moi(db, "Tổ BC Một", "TO-BC-1")
    a, _b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)

    cv = db.query(SanXuatCongViec).filter_by(lsx_id=a.id).order_by(SanXuatCongViec.id).first()
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1,
        bat_dau=datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc), ket_thuc=None,
    ))
    db.commit()
    return a.id


@pytest.fixture
def muoi_hai_lenh(db, orders, lsx_svc, admin, customer) -> list[int]:
    """12 lệnh ĐÃ PHÁT HÀNH — 6 lần gọi `_phat_hanh_vao_to` (mỗi lần một đơn PTG-2-thành-phần mới
    → 2 lệnh), KHÔNG tạo tay. Gắn thêm một phiên chạy để `phien` không rỗng khi soi N+1 — nếu
    không, bài N+1 có thể xanh giả trên bối cảnh trống rỗng (mọi map con đều `{}`)."""
    to = _to_moi(db, "Tổ BC Mười Hai", "TO-BC-12")
    ids: list[int] = []
    for _ in range(6):
        a, b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
        ids += [a.id, b.id]

    cv = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.lsx_id.in_(ids)
    ).order_by(SanXuatCongViec.id).first()
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1,
        bat_dau=datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc), ket_thuc=None,
    ))
    db.commit()
    return ids


# --- Ba bài gốc của brief -----------------------------------------------------------------------
def test_khong_n_plus_1(db, mot_lenh, muoi_hai_lenh):
    # Chốt TRƯỚC khi so số câu: bối cảnh 12 lệnh phải nạp ĐỦ 12 lệnh và map con không rỗng — nếu
    # không chốt điều này, bài so `n12 == n1` có thể xanh giả (vd. 12 id không hề tồn tại vẫn ra
    # cùng số câu như 1 id thật, vì `nap()` chạy số câu cố định bất kể kết quả).
    bc12 = boi_canh.nap(db, muoi_hai_lenh)
    assert len(bc12.lenh) == 12
    assert any(bc12.cong_viec.values()), "cong_viec rỗng toàn bộ — bài N+1 đang canh trên rỗng"
    assert any(bc12.phien.values()), "phien rỗng toàn bộ — bài N+1 đang canh trên rỗng"

    n1 = _dem_sql(db, lambda: boi_canh.nap(db, [mot_lenh]))
    n12 = _dem_sql(db, lambda: boi_canh.nap(db, muoi_hai_lenh))
    assert n12 == n1, f"N+1: 1 lệnh {n1} câu, 12 lệnh {n12} câu"
    # Chốt SỐ TUYỆT ĐỐI, không chỉ so hai bên bằng nhau: `n12 == n1` một mình vẫn xanh nếu ai đó
    # bỏ hẳn một câu (cả hai bên cùng tụt). 21 = 15 câu gốc + 3 câu bài ghép (5b/5c/5d)
    # + 5e (thành viên nhóm, cho cầu nhập kho) + 11b (số đã THỰC NHẬN) — hai câu thêm ở Vòng sửa 1
    # của Task 6 — + câu 16 (phân công JOIN nhân viên) thêm ở Vòng sửa 1 của Task 9, cho nửa
    # "người" của cột Máy/người. Đổi số ở đây phải đi kèm sửa danh sách câu trong docstring
    # `boi_canh.py`, nếu không hai chỗ nói hai kiểu.
    assert n1 == 21, f"số câu SQL của nap() đổi: {n1} (kỳ vọng 21)"


def test_map_dung_khoa(db, mot_lenh):
    bc = boi_canh.nap(db, [mot_lenh])
    assert mot_lenh in bc.lenh
    assert mot_lenh in bc.cong_viec
    for cv in bc.cong_viec[mot_lenh]:
        assert cv.id in bc.phien


def test_danh_sach_rong_khong_no(db):
    bc = boi_canh.nap(db, [])
    assert bc.lenh == {}


# --- Bổ sung: khoá của ba map mới/hụt khoá trong brief (Q3, Q4, Q6 — phán quyết ngoài brief) ----
def test_giao_khoa_theo_order_line_id_khong_phai_lsx_id(db, mot_lenh):
    """`giao` PHẢI khoá theo `order_line_id` — bảng `delivery_request_lines` không có cột lsx nào,
    cầu duy nhất là `lsx.order_line_id`."""
    lsx = db.get(Lsx, mot_lenh)
    assert lsx.id != lsx.order_line_id, "fixture trùng id — bài này hết phân biệt được hai cách khoá"
    req = DeliveryRequest(code="YCGH-BC-TEST", order_id=lsx.order_id, ngay_can_giao=date.today())
    db.add(req)
    db.flush()
    line = DeliveryRequestLine(request_id=req.id, order_line_id=lsx.order_line_id, qty=1)
    db.add(line)
    db.commit()

    bc = boi_canh.nap(db, [mot_lenh])
    assert set(bc.giao) == {lsx.order_line_id}
    assert bc.giao[lsx.order_line_id] == [line]


# --- Vòng sửa 1 (review Task 6) — accessor `giao_cua`, bịt lỗ đánh chỉ số `giao` trực tiếp -------
def test_giao_cua_dung_va_bay_danh_chi_so_truc_tiep_co_that(db, orders, lsx_svc, admin, customer):
    """`lsx.id` và `order_line_id` cùng là int tự tăng CÙNG khoảng giá trị nên có thể trùng số
    GIỮA HAI LỆNH KHÁC NHAU: `b.id` trùng `a.order_line_id`. Đọc `giao[b.id]` trực tiếp KHÔNG báo
    lỗi — nó trả nhầm sang giao hàng của `a`. `giao_cua()` không dính bẫy này."""
    # Lệch dãy id NGAY TỪ ĐẦU (như `mot_lenh`) để phép trùng số dưới đây là CHỦ Ý dựng, không phải
    # trùng ngẫu nhiên của DB test trắng (xem docstring fixture `mot_lenh`).
    mao_don = Order(order_no="DH-BC-CUA-MOI")
    db.add(mao_don)
    db.flush()
    db.add(OrderLine(order_id=mao_don.id))
    db.commit()

    to = _to_moi(db, "Tổ BC Giao", "TO-BC-GIAO")
    a, b, _goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    assert b.id == a.order_line_id, "tiền đề trùng khoảng id không còn đúng — sửa lại kịch bản"

    req = DeliveryRequest(code="YCGH-BC-CUA", order_id=a.order_id, ngay_can_giao=date.today())
    db.add(req)
    db.flush()
    line_a = DeliveryRequestLine(request_id=req.id, order_line_id=a.order_line_id, qty=7)
    db.add(line_a)
    db.commit()

    bc = boi_canh.nap(db, [a.id, b.id])

    # Accessor đúng: a có giao hàng, b thì không (b không hề có DeliveryRequestLine nào).
    assert bc.giao_cua(a.id) == [line_a]
    assert bc.giao_cua(b.id) == []

    # Cái bẫy CÓ THẬT: đánh chỉ số `giao` trực tiếp bằng `b.id` (trùng số với `a.order_line_id`)
    # trả NHẦM giao hàng của `a` — không KeyError, không dấu hiệu gì báo sai.
    assert bc.giao[b.id] == [line_a]
    assert bc.giao[b.id] != bc.giao_cua(b.id)


def test_nhap_kho_yc_di_qua_kho_hang(db, mot_lenh):
    """`san_xuat_nhap_kho_yc` không có cột `lsx_id` — về lệnh bằng HAI cầu OR (câu 12).

    KHÔNG phải qua `san_xuat_kho_hang.lsx_id` như bản Task 6 làm (docstring cũ ở đây nói vậy, SAI):
    hàng thành phẩm luôn có `lsx_id IS NULL`. Hai cầu đúng là `kcs_batch → cong_viec.lsx_id` và
    `yc.nhom_id ∈ nhóm của lệnh` — xem docstring `boi_canh.py`.
    """
    lsx = db.get(Lsx, mot_lenh)
    cv = db.query(SanXuatCongViec).filter_by(lsx_id=mot_lenh).first()
    t0 = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 20, 2, 0, tzinfo=timezone.utc)
    kcs_batch = SanXuatKcsBatch(
        cong_viec_id=cv.id, bat_dau=t0, ket_thuc=t1, so_luong_nhan=100, so_luong_dat=100,
        don_vi="cái",
    )
    db.add(kcs_batch)
    db.flush()
    hang = SanXuatKhoHang(ma="KHO-BC-TEST", order_id=lsx.order_id, lsx_id=mot_lenh)
    db.add(hang)
    db.flush()
    yc = SanXuatNhapKhoYc(
        kcs_batch_id=kcs_batch.id, hang_id=hang.id, so_luong_yeu_cau=100, don_vi="cái",
    )
    db.add(yc)
    db.commit()

    bc = boi_canh.nap(db, [mot_lenh])
    assert bc.nhap_kho_yc[mot_lenh] == [yc]


def test_phu_thuoc_buoc_khoa_theo_lsx_cua_buoc_sau(db, mot_lenh):
    """`phu_thuoc_buoc` khoá theo `lsx_id` của BƯỚC SAU (`buoc_sau_id`), lấy từ
    `lsx_cong_doan_phu_thuoc` — không phải bảng `san_xuat_phu_thuoc` (cạnh chéo giữa hai LSX)."""
    buoc_truoc = db.query(LsxCongDoan).filter_by(lsx_id=mot_lenh).first()
    buoc_sau = LsxCongDoan(lsx_id=mot_lenh, thu_tu=99, ten="Bước sau (test BC)")
    db.add(buoc_sau)
    db.flush()
    canh = LsxCongDoanPhuThuoc(buoc_truoc_id=buoc_truoc.id, buoc_sau_id=buoc_sau.id)
    db.add(canh)
    db.commit()

    bc = boi_canh.nap(db, [mot_lenh])
    assert bc.phu_thuoc_buoc[mot_lenh] == [(buoc_truoc.id, buoc_sau.id)]


# --- Vòng sửa 1 (review Task 7) — công việc BÀI GHÉP không được rơi khỏi bối cảnh ---------------
def _phu_buoc_dau_bang_bai_ghep(db, lsxs, *, ma: str):
    """Gộp bước ĐẦU của mỗi lệnh trong `lsxs` vào MỘT công đoạn chung của một bài ghép.

    Đây là hình dạng dữ liệu mà `snapshot.dung_cong_viec` đối xử đặc biệt: bước bị phủ KHÔNG đẻ
    công việc riêng, thay vào đó cả nhóm dùng chung MỘT `SanXuatCongViec` có `lsx_id IS NULL`.
    Trả `(bai_ghep, buoc_chung, {lsx_id: LsxCongDoan bị phủ})`."""
    bg = BaiGhep(ma=ma, ten=f"Bài ghép {ma}")
    db.add(bg)
    db.flush()
    chung = BaiGhepCongDoan(
        bai_ghep_id=bg.id, thu_tu=0, ten="In ghép", nhom="print",
        so_luong_vao=1000, so_luong_ra=1000, don_vi_vao="to", don_vi_ra="to",
    )
    db.add(chung)
    db.flush()

    bi_phu: dict[int, LsxCongDoan] = {}
    for lsx in lsxs:
        cd = (
            db.query(LsxCongDoan).filter_by(lsx_id=lsx.id)
            .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id).first()
        )
        db.add(BaiGhepThanhVien(bai_ghep_id=bg.id, lsx_id=lsx.id, so_con_tren_to=2))
        db.add(BaiGhepCongDoanMap(
            bai_ghep_cong_doan_id=chung.id, lsx_id=lsx.id, lsx_step_key=cd.step_key,
        ))
        bi_phu[lsx.id] = cd
    db.commit()
    return bg, chung, bi_phu


@pytest.fixture
def sau_lenh_chung_bai_ghep(db, orders, lsx_svc, admin, customer):
    """6 lệnh ĐÃ PHÁT HÀNH, bước đầu của CẢ SÁU bị một công đoạn ghép phủ chung.

    Dùng cho hai việc: (1) khoá `cong_viec_ghep`/`buoc_phu`; (2) canh N+1 trên đúng nhánh bài ghép
    — nhánh này thêm 3 câu SQL, nếu ai đó viết thành vòng lặp theo lệnh thì chỉ bài ghép mới lộ."""
    to = _to_moi(db, "Tổ BC Ghép", "TO-BC-GHEP")
    lsxs = []
    for _ in range(3):
        a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
        lsxs += [a, b]
    db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id.in_([l.id for l in lsxs])).update(
        {LsxCongDoan.department_id: to.id}, synchronize_session=False
    )
    db.commit()

    bg, chung, bi_phu = _phu_buoc_dau_bang_bai_ghep(db, lsxs, ma="GB-BC-1")
    release.phat_hanh(db, lsx_ids={l.id for l in lsxs}, bai_ghep_ids={bg.id}, actor=admin)
    db.commit()
    return [l.id for l in lsxs], chung.id, bi_phu


def test_cong_viec_ghep_va_buoc_phu(db, sau_lenh_chung_bai_ghep):
    """Công việc chung của bài ghép có `lsx_id IS NULL` nên câu `WHERE lsx_id IN (...)` KHÔNG với
    tới — không có `cong_viec_ghep` thì tầng tính mất trắng bước in ghép của MỌI lệnh thành viên."""
    ids, bgcd_id, bi_phu = sau_lenh_chung_bai_ghep
    lsx_id = ids[0]

    cv_ghep = db.query(SanXuatCongViec).filter_by(bai_ghep_cong_doan_id=bgcd_id).one()
    assert cv_ghep.lsx_id is None, "tiền đề hỏng: công việc ghép phải KHÔNG thuộc lệnh nào"

    bc = boi_canh.nap(db, [lsx_id])

    # (1) Công việc chung nằm ở `cong_viec_ghep`, KHÔNG nằm ở `cong_viec`.
    assert [cv.id for cv in bc.cong_viec_ghep[lsx_id]] == [cv_ghep.id]
    assert cv_ghep.id not in {cv.id for cv in bc.cong_viec[lsx_id]}
    assert cv_ghep.id in {cv.id for cv in bc.cong_viec_du(lsx_id)}

    # (2) `buoc_phu` nói bằng `lsx_cong_doan.id` — cùng ngôn ngữ với cạnh `phu_thuoc_buoc`, nếu
    #     không thì không nối được công việc chung vào đồ thị bước.
    # Danh sách một phần tử cũng chốt luôn phần "GIỚI HẠN trong ids": 5 lệnh còn lại của cùng bài
    # ghép không lọt vào.
    assert bc.buoc_phu[cv_ghep.id] == [bi_phu[lsx_id].id]

    # (3) Các map con phải TOÀN ÁNH cả trên công việc ghép — thiếu là `bc.phien[cv.id]` ném KeyError
    #     ngay lần đầu tầng tính đọc tới.
    for cv in bc.cong_viec_du(lsx_id):
        assert cv.id in bc.phien
        assert cv.id in bc.batch


def test_khong_n_plus_1_co_bai_ghep(db, sau_lenh_chung_bai_ghep):
    """Ba câu bài ghép phải chạy VÔ ĐIỀU KIỆN và ĐÚNG MỘT LẦN: 1 lệnh và 6 lệnh cùng số câu."""
    ids, _bgcd_id, _bi_phu = sau_lenh_chung_bai_ghep

    bc6 = boi_canh.nap(db, ids)
    assert len(bc6.lenh) == 6
    assert all(bc6.cong_viec_ghep[i] for i in ids), "cong_viec_ghep rỗng — đang canh trên rỗng"

    n1 = _dem_sql(db, lambda: boi_canh.nap(db, ids[:1]))
    n6 = _dem_sql(db, lambda: boi_canh.nap(db, ids))
    assert n6 == n1 == 21, f"N+1 nhánh bài ghép: 1 lệnh {n1} câu, 6 lệnh {n6} câu"
