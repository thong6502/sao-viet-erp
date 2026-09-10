"""Xếp lịch 3 — lớp service, chạy trên LUỒNG THẬT (đơn → chuyển SX → tạo lệnh → sẵn sàng).

Tái dùng nguyên bộ dựng nguồn của `test_xep_lich_service.py` thay vì chép lại: hai màn phải nhìn
CÙNG một hình dạng dữ liệu, chép ra là hai bản trôi nhau. Bám `docs/spec-xep-lich-3.md` §4.1
(ranh giới hiệu năng), §5 (màn), §6 (API).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import event

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_lenh_repo import XepLichLenhRepository
from app.services.gio_xuong import ve_utc_that
from app.services.xep_lich_3 import XepLich3Conflict, XepLich3NotFound, XepLich3Service

# Fixtures + helper dùng lại — import tên vào module này là pytest nhận luôn thành fixture.
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _khai_giay_len_buoc_in,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


@pytest.fixture
def svc3(db):
    return XepLich3Service(db, XepLichLenhRepository(db), AuditLogRepository(db))


@pytest.fixture
def lenh(db, orders, lsx_svc, admin, customer):
    """Một lệnh SẴN SÀNG có routing thật + giấy khai trên bước in (nếu không, giờ chạy = 0)."""
    ds = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _khai_giay_len_buoc_in(db, ds[0].id)
    db.commit()
    return ds[0]


@pytest.fixture
def hai_lenh(db, orders, lsx_svc, admin, customer):
    ds = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for l in ds:
        _khai_giay_len_buoc_in(db, l.id)
    db.commit()
    return ds


# ============================================================== đọc

def test_hang_cho_chua_lenh_san_sang_chua_co_moc(svc3, lenh):
    ds = svc3.hang_cho()
    assert lenh.id in [d["lsx_id"] for d in ds["dong"]]


def test_the_hang_cho_mang_du_so_de_nguoi_quyet(svc3, lenh):
    d = [x for x in svc3.hang_cho()["dong"] if x["lsx_id"] == lenh.id][0]
    for k in ("ma", "ten", "customer_name", "han_hoan_thanh_sx", "is_rush",
              "so_to_ke_hoach", "chay_phut", "so_buoc"):
        assert k in d, f"thieu khoa {k}"
    assert d["chay_phut"] > 0, "routing co buoc may ma gio chay = 0"


def test_dat_moc_xong_thi_roi_hang_cho(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert lenh.id not in [d["lsx_id"] for d in svc3.hang_cho()["dong"]]


def test_hang_cho_phan_trang_o_may_chu(svc3, hai_lenh):
    ds = svc3.hang_cho(trang=1, cd_trang=1)
    assert len(ds["dong"]) == 1
    assert ds["tong"] >= 2                      # tổng là SAU lọc, không phải số dòng trả về


def test_hang_cho_tim_o_may_chu(svc3, lenh):
    ds = svc3.hang_cho(tim=lenh.ma)
    assert [d["lsx_id"] for d in ds["dong"]] == [lenh.id]
    assert svc3.hang_cho(tim="KHONG-CO-MA-NAY")["dong"] == []


def test_lich_chi_tra_lenh_CHAM_cua_so(svc3, lenh):
    """`lich()` bắt buộc cắt theo cửa sổ (§4.1) — không có đường trải cả lịch sử."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    trong = svc3.lich(tu=date(2026, 9, 10), den=date(2026, 9, 16))
    truoc = svc3.lich(tu=date(2026, 8, 1), den=date(2026, 8, 7))
    sau = svc3.lich(tu=date(2026, 12, 1), den=date(2026, 12, 7))
    assert [d["lsx_id"] for d in trong["dong"]] == [lenh.id]
    assert truoc["dong"] == [] and sau["dong"] == []


def test_dong_lich_mang_du_so_cho_thanh_hai_lop(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    d = svc3.lich(tu=date(2026, 9, 10), den=date(2026, 9, 16))["dong"][0]
    assert d["ket_thuc"] >= d["bat_dau_at"]
    assert d["chay_phut"] > 0
    assert d["doan"] and all({"tu", "den", "buoc_index"} <= set(x) for x in d["doan"])
    tong = sum((x["den"] - x["tu"]).total_seconds() / 60 for x in d["doan"])
    assert tong == pytest.approx(d["chay_phut"], abs=0.5)


def test_thanh_dai_bang_gio_chay_cong_nghi_va_ngoai_ca(svc3, lenh):
    """Đây là toàn bộ mục tiêu của module — con số phải cộng đúng, không xấp xỉ."""
    d = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    tong = (d["ket_thuc"] - d["bat_dau_at"]).total_seconds() / 60
    assert tong == pytest.approx(d["chay_phut"] + d["nghi_ngoai_ca_phut"], abs=0.5)


def test_chi_tiet_du_o_cua_panel(svc3, lenh):
    """Panel dưới — thiếu một khoá là FE nhận `undefined` mà không lỗi nào bật ra."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    ct = svc3.chi_tiet(lenh.id)
    for k in ("customer_name", "order_no", "customer_po_no", "sale_name", "so_luong_dat",
              "don_vi_tinh", "so_to_ke_hoach", "so_con", "han_hoan_thanh_sx", "han_giao_khach",
              "nguoi_phu_trach_ten", "luu_y_gui_xuong", "giay", "kho_in", "so_mau", "so_kem",
              "so_nguoi_tong", "is_rush", "bat_dau_at", "ket_thuc", "chay_phut",
              "nghi_ngoai_ca_phut", "cong_doans"):
        assert k in ct, f"thieu khoa {k}"


def test_chi_tiet_lenh_chua_xep_van_mo_duoc(svc3, lenh):
    """Bấm thẻ hàng chờ cũng mở panel — chưa có lịch thì các ô lịch để trống, không nổ."""
    ct = svc3.chi_tiet(lenh.id)
    assert ct["bat_dau_at"] is None and ct["ket_thuc"] is None
    assert ct["cong_doans"]


def test_bang_cong_doan_KHONG_co_moc_tung_buoc(svc3, lenh):
    """§4: mốc từng bước là số THỪA ở màn cấp LỆNH — bốn chỗ khác cần thì lấy đường riêng."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    cd = svc3.chi_tiet(lenh.id)["cong_doans"][0]
    assert "bat_dau" not in cd and "ket_thuc" not in cd
    assert cd["mau_index"] in (0, 1, 2, 3)


def test_moc_tung_buoc_van_lay_duoc_qua_duong_rieng(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    moc = svc3.moc_cong_doan([lenh.id])
    assert lenh.id in moc and moc[lenh.id]
    assert all(b.ket_thuc >= b.bat_dau for b in moc[lenh.id])


def test_lich_khong_N_cong_1_truy_van_routing(db, svc3, hai_lenh):
    """§4.1: routing cả lô nạp MỘT truy vấn, không hỏi từng lệnh."""
    for l in hai_lenh:
        svc3.dat_moc(l.id, datetime(2026, 9, 11, 8, 0))
    dem = {"n": 0}

    def _bat(conn, cur, stmt, params, ctx, many):
        s = stmt.strip().lower()
        if s.startswith("select") and "lsx_cong_doan" in s:
            dem["n"] += 1

    event.listen(db.get_bind(), "before_cursor_execute", _bat)
    try:
        svc3.lich(tu=date(2026, 9, 1), den=date(2026, 9, 30))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _bat)
    assert dem["n"] <= 2, f"N+1: {dem['n']} truy van routing cho {len(hai_lenh)} lenh"


# ============================================================== ghi

def test_dat_moc_lan_dau_tao_dong(svc3, lenh):
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert r["bat_dau_at"] == datetime(2026, 9, 11, 8, 0)
    assert r["ket_thuc"] > r["bat_dau_at"]
    assert r["da_doi"] is False and r["thong_bao"] is None


def test_dat_lai_thi_GHI_DE_khong_de_dong_thu_hai(db, svc3, lenh):
    from app.models.xep_lich_lenh import XepLichLenh

    a = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.dat_moc(lenh.id, datetime(2026, 9, 14, 8, 0), a["updated_at"])
    assert db.query(XepLichLenh).filter_by(lsx_id=lenh.id).count() == 1


def test_moc_ngoai_gio_chay_thi_TU_DOI_va_bao(svc3, lenh):
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 13, 3, 0))   # CN, 03:00
    assert r["da_doi"] is True
    assert r["thong_bao"] and "dời" in r["thong_bao"]


def test_moc_da_doi_duoc_LUU_chu_khong_luu_moc_nguoi_tha(svc3, lenh):
    """Lưu mốc người thả thì mỗi lần đọc lại trượt thêm một nhát, thanh tự đi."""
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 13, 3, 0))
    lai = svc3.chi_tiet(lenh.id)
    assert lai["bat_dau_at"] == r["bat_dau_at"]


def test_nguoi_khac_vua_doi_thi_409(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    with pytest.raises(XepLich3Conflict):
        svc3.dat_moc(lenh.id, datetime(2026, 9, 12, 8, 0), datetime(2020, 1, 1, 0, 0))


def test_khong_gui_chot_thi_van_ghi_duoc(svc3, lenh):
    """Đặt mốc lần đầu (kéo từ hàng chờ) không có gì để so — không được đòi chốt."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert svc3.dat_moc(lenh.id, datetime(2026, 9, 15, 8, 0))["bat_dau_at"].day == 15


def test_KHONG_CHAN_du_tre_han_sx(db, svc3, lenh):
    """§1: "KHÔNG CHẶN GÌ HẾT". Xếp xong sau hạn SX vẫn ghi được, chỉ để UI bày màu."""
    lenh.han_hoan_thanh_sx = date(2026, 9, 1)
    db.commit()
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert r["bat_dau_at"] is not None
    assert r["ket_thuc"].date() > lenh.han_hoan_thanh_sx


def test_xoa_moc_tra_lenh_ve_hang_cho(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.xoa_moc(lenh.id)
    assert lenh.id in [d["lsx_id"] for d in svc3.hang_cho()["dong"]]


def test_xoa_moc_lenh_chua_xep_thi_404(svc3, lenh):
    with pytest.raises(XepLich3NotFound):
        svc3.xoa_moc(lenh.id)


def test_dat_moc_lenh_khong_ton_tai_thi_404(svc3):
    with pytest.raises(XepLich3NotFound):
        svc3.dat_moc(999_999, datetime(2026, 9, 11, 8, 0))


# ================= máy đang giao chạy · MỘT nguồn thời lượng (10/09/2026) =================

def _svc_moi(db):
    """Service MỚI cho mỗi lượt đọc — cache máy/khung giờ sống trong đúng MỘT request."""
    return XepLich3Service(db, XepLichLenhRepository(db), AuditLogRepository(db))


def test_bang_cong_doan_va_thanh_dung_CHUNG_mot_so_gio(svc3, lenh):
    """Tổng giờ các bước trong bảng = giờ chạy của thanh.

    Trước 10/09/2026 hai chỗ tính riêng: bảng truyền `None` chỗ quy cách nên mọi bước rơi về
    "chưa quy đổi" và chỉ còn thời gian chuẩn bị — cùng một lệnh, bảng cộng ra 1 443′ trong khi
    thanh dài 2 362′.
    """
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    ct = svc3.chi_tiet(lenh.id)
    tong = sum(c["chay_phut"] for c in ct["cong_doans"])
    assert tong > 0, "routing co buoc may ma bang cong ra 0 phut"
    assert tong == pytest.approx(ct["chay_phut"], abs=0.5)


def test_lenh_chua_phat_hanh_dung_may_KE_HOACH(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    cds = svc3.chi_tiet(lenh.id)["cong_doans"]
    co_may = [c for c in cds if c["may_id"]]
    assert co_may, "routing khong co buoc nao gan may"
    assert all(c["may_nguon"] == "ke_hoach" for c in co_may)
    assert all(c["may_ke_hoach_ten"] is None for c in cds), "chua doi may thi khong bay doi chieu"


def test_may_lay_tu_CONG_VIEC_dang_giao_chay(db, svc3, lenh, admin):
    """Lệnh đã phát hành thì máy thật nằm ở `san_xuat_cong_viec.may_id`.

    Xưởng đổi máy ở bàn tổ, ô máy kế hoạch trên routing KHÔNG đổi theo — bàn xếp lịch đọc ô kế
    hoạch là bày sai máy, và vì tốc độ treo ở cặp (công đoạn × máy) nên thời lượng cũng tính trên
    một máy không chạy.
    """
    from app.models.may_thiet_bi import MayThietBi
    from app.models.san_xuat import SanXuatCongViec

    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.phat_hanh(lenh.id, actor=admin)

    cv = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.lsx_id == lenh.id,
        SanXuatCongViec.may_id.isnot(None),
        SanXuatCongViec.lsx_cong_doan_id.isnot(None),
    ).order_by(SanXuatCongViec.id).first()
    assert cv is not None, "phat hanh phai de ra cong viec co may"
    # DB test chi seed dung mot may cho moi loai — them mot may THAY THE de co cho ma doi.
    may_moi = db.query(MayThietBi).filter(
        MayThietBi.id != cv.may_id, MayThietBi.active.is_(True)
    ).order_by(MayThietBi.id).first()
    if may_moi is None:
        cu = db.get(MayThietBi, cv.may_id)
        may_moi = MayThietBi(ma=f"{cu.ma}-B", ten=f"{cu.ten} (may 2)",
                             loai_may=cu.loai_may, active=True)
        db.add(may_moi)
        db.commit()
    # Ghi thẳng `cv.may_id` thay vì gọi `thuc_thi.doi_may`: hàm đó đòi công việc đang chạy hoặc
    # tạm dừng (phiên máy, khoảng người…), còn thứ đang kiểm ở đây là ĐƯỜNG ĐỌC của bàn xếp lịch.
    cv.may_id = may_moi.id
    db.commit()

    b = {c["id"]: c for c in _svc_moi(db).chi_tiet(lenh.id)["cong_doans"]}[cv.lsx_cong_doan_id]
    assert b["may_id"] == may_moi.id
    assert b["may_ten"] == may_moi.ten
    assert b["may_nguon"] == "thuc_thi"
    assert b["may_ke_hoach_ten"], "may ke hoach khac may dang chay thi phai bay ca hai de doi chieu"


def test_buoc_chua_gan_may_noi_ro_thieu_gi_va_bao_len_ca_THANH(db, svc3, lenh):
    """Bước máy chưa gán máy chiếm 0 phút ⇒ ngày kết thúc đang TÍNH THIẾU.

    Trước 10/09/2026 bước đó lọt qua im lặng: bảng ghi "Chờ chạy" (câu vô nghĩa với người đang
    tìm xem thiếu gì) và lịch nhảy thẳng sang bước sau, không một dòng cảnh báo nào.
    """
    from app.models.lsx import LsxCongDoan

    b = db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == lenh.id, LsxCongDoan.may_id.isnot(None)
    ).order_by(LsxCongDoan.thu_tu).first()
    assert b is not None
    b.may_id = None
    db.commit()

    _svc_moi(db).dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    ct = _svc_moi(db).chi_tiet(lenh.id)
    buoc = next(c for c in ct["cong_doans"] if c["id"] == b.id)
    assert buoc["chay_phut"] == 0
    assert buoc["canh_bao"] and "chưa gán máy" in buoc["canh_bao"]
    assert any("muộn hơn" in g for g in ct["ghi_chu"]), "thieu du kien ma thanh khong noi gi"


def test_so_luong_vao_chua_khai_ra_None_KHONG_phai_0(db, svc3, lenh):
    """Cot nguon la NOT NULL default 0 nen 0 CHINH LA "chua khai" — doi ve None ngay o mep API.

    "0 to" doc nhu "buoc nay khong nhan gi vao", khac han "ke hoach chua dien".
    """
    from app.models.lsx import LsxCongDoan

    b = db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == lenh.id
    ).order_by(LsxCongDoan.thu_tu).first()
    b.so_luong_vao = 0
    db.commit()
    c = next(x for x in _svc_moi(db).chi_tiet(lenh.id)["cong_doans"] if x["id"] == b.id)
    assert c["so_luong_vao"] is None


def test_don_vi_vao_kem_TEN_hien_thi(db, svc3, lenh):
    """Bảng lưu MÃ (`to`, `con`), người đọc cần chữ — FE trước đó in mã thô và độn mặc định "tờ"."""
    from app.models.don_vi_do import DonViDo
    from app.models.lsx import LsxCongDoan

    dv = db.query(DonViDo).order_by(DonViDo.id).first()
    b = db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == lenh.id
    ).order_by(LsxCongDoan.thu_tu).first()
    b.don_vi_vao = dv.ma
    db.commit()
    c = next(x for x in _svc_moi(db).chi_tiet(lenh.id)["cong_doans"] if x["id"] == b.id)
    assert c["don_vi_vao"] == dv.ma
    assert c["don_vi_vao_ten"] == dv.ten


def test_moi_buoc_mang_LOP_phu_thuoc(svc3, lenh):
    """Bảng bày 1→N theo `thu_tu`; `lop` mới là quan hệ chặn. Có `lop` thì màn nói được "hai bước
    này không chặn nhau" thay vì vẽ ra một chuỗi tuần tự không tồn tại."""
    cds = _svc_moi(svc3.db).chi_tiet(lenh.id)["cong_doans"]
    assert cds
    assert all(isinstance(c["lop"], int) and isinstance(c["song_song"], bool) for c in cds)


def test_lich_khong_N_cong_1_truy_van_may(db, svc3, hai_lenh):
    """§4.1: mọi đường đọc `san_xuat_cong_viec` của bàn phải nạp theo LÔ.

    Đo BẤT BIẾN THEO SỐ LỆNH chứ không chốt một con số: bàn hiện đọc bảng đó ở ba chỗ (lọc cửa
    sổ, máy đang giao chạy, lớp thực tế) và số đó còn đổi khi thêm đường đọc mới. Thứ không được
    phép đổi là: thêm lệnh vào bàn KHÔNG được thêm truy vấn nào.
    """
    for l in hai_lenh:
        svc3.dat_moc(l.id, datetime(2026, 9, 11, 8, 0))
    dem = {"n": 0}

    def _bat(conn, cur, stmt, params, ctx, many):
        s = stmt.strip().lower()
        if s.startswith("select") and "san_xuat_cong_viec" in s:
            dem["n"] += 1

    def _do() -> int:
        dem["n"] = 0
        svc = _svc_moi(db)
        event.listen(db.get_bind(), "before_cursor_execute", _bat)
        try:
            svc.lich(tu=date(2026, 9, 1), den=date(2026, 9, 30))
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", _bat)
        return dem["n"]

    hai = _do()
    svc3.xoa_moc(hai_lenh[1].id)
    mot = _do()
    assert hai == mot, f"N+1: {mot} truy van voi 1 lenh, {hai} voi 2 lenh"


# ============================================================== gói đã thả xuống xưởng
# Chốt 10/09/2026: màn bày nút "Thu hồi phát hành" mà không hỏi gói còn rút về được không, nên
# lệnh có việc đã chạy vẫn mời người dùng gõ lý do rồi mới ném 409 — và câu lỗi chỉ sang "phát
# hành cập nhật" trong khi màn không có nút đó. Ba test dưới khoá cả hai vế.

def _cv_dau(db, lsx_id):
    from app.models.san_xuat import SanXuatCongViec

    return db.query(SanXuatCongViec).filter(
        SanXuatCongViec.lsx_id == lsx_id
    ).order_by(SanXuatCongViec.id).first()


def test_goi_phat_hanh_noi_ro_con_thu_hoi_duoc_khong(db, svc3, lenh, admin):
    """Chưa phát hành thì `co_goi=False`; phát hành xong mà chưa ai bấm bắt đầu thì thu hồi được."""
    assert svc3.goi_phat_hanh(lenh.id)["co_goi"] is False

    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.phat_hanh(lenh.id, actor=admin)

    g = _svc_moi(db).goi_phat_hanh(lenh.id)
    assert g["co_goi"] is True
    assert g["so_da_bat_dau"] == 0
    assert g["cho_phep_thu_hoi"] is True
    # Chưa việc nào chạy ⇒ chưa cần tới đường cập nhật, nhưng vẫn phải mở (còn việc chưa bắt đầu).
    assert g["cho_phep_cap_nhat"] is True


def test_co_viec_da_bat_dau_thi_KHOA_thu_hoi_va_mo_duong_cap_nhat(db, svc3, lenh, admin):
    """Một bước đã rời `released` là cả gói hết rút về được (§4.3) — màn phải biết TRƯỚC khi bày nút."""
    import uuid

    from app.models.lsx import LsxCongDoan
    from app.models.san_xuat import CV_HOAN_THANH
    from app.services.xep_lich_service import XepLichConflict

    # Lệnh của fixture chỉ có MỘT bước; cần bước thứ hai thì mới tách được "đã chạy" với "chưa chạy".
    goc = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == lenh.id).order_by(LsxCongDoan.thu_tu).first()
    db.add(LsxCongDoan(
        step_key=str(uuid.uuid4()), lsx_id=lenh.id, thu_tu=int(goc.thu_tu or 0) + 1,
        cong_doan_id=goc.cong_doan_id, ten=f"{goc.ten} (bước 2)", nhom=goc.nhom,
        department_id=goc.department_id, may_id=goc.may_id,
    ))
    db.commit()

    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.phat_hanh(lenh.id, actor=admin)
    cv = _cv_dau(db, lenh.id)
    assert cv is not None
    cv.trang_thai = CV_HOAN_THANH
    db.commit()

    svc = _svc_moi(db)
    g = svc.goi_phat_hanh(lenh.id)
    assert g["so_da_bat_dau"] == 1
    assert g["cho_phep_thu_hoi"] is False
    assert g["cho_phep_cap_nhat"] is True

    with pytest.raises(XepLichConflict):
        svc.thu_hoi(lenh.id, actor=admin, ly_do="Khách dời hạn")

    # …nhưng lối ra thì mở: đẩy lịch mới cho phần chưa bắt đầu, việc đã xong giữ nguyên.
    kq = _svc_moi(db).phat_hanh_cap_nhat(lenh.id, actor=admin, ly_do="Dời giờ do kẹt máy in")
    assert kq["so_giu_nguyen"] == 1
    assert kq["so_cong_viec_cap_nhat"] >= 1
    assert _svc_moi(db).goi_phat_hanh(lenh.id)["version_hien_tai"] == 2


# ============================================================== thanh của lệnh ĐÃ CHẠY DỞ
# Chốt 10/09/2026 (ảnh người dùng gửi): mốc đổi nghĩa thành "bắt đầu phần còn lại" xong thì thanh
# trên bàn bắt đầu ở mốc — nằm hẳn bên phải chốt "hôm nay" — trong khi panel của chính lệnh đó
# ghi "Lệnh đã bắt đầu 14:15 09/09". Bàn nói lệnh chưa đụng tới, panel nói đã xong một bước.

def _lenh_hai_buoc_da_chay(db, svc3, lenh, admin, *, moc: datetime, vao_viec: datetime):
    """Lệnh đã phát hành, bước ĐẦU chạy xong lúc `vao_viec`, mốc phần còn lại đặt ở `moc`."""
    import uuid

    from app.models.lsx import LsxCongDoan
    from app.models.san_xuat import CV_HOAN_THANH
    from app.models.san_xuat_thuc_thi import SanXuatPhienChay

    goc = db.query(LsxCongDoan).filter(
        LsxCongDoan.lsx_id == lenh.id
    ).order_by(LsxCongDoan.thu_tu).first()
    db.add(LsxCongDoan(
        step_key=str(uuid.uuid4()), lsx_id=lenh.id, thu_tu=int(goc.thu_tu or 0) + 1,
        cong_doan_id=goc.cong_doan_id, ten=f"{goc.ten} (bước 2)", nhom=goc.nhom,
        department_id=goc.department_id, may_id=goc.may_id,
    ))
    db.commit()

    svc3.dat_moc(lenh.id, vao_viec)
    svc3.phat_hanh(lenh.id, actor=admin)
    cv = _cv_dau(db, lenh.id)
    cv.trang_thai = CV_HOAN_THANH
    cv.hoan_thanh_luc = ve_utc_that(vao_viec + timedelta(minutes=30))
    db.add(SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=1, may_id=cv.may_id,
        bat_dau=ve_utc_that(vao_viec), ket_thuc=ve_utc_that(vao_viec + timedelta(minutes=30)),
        loai_dong="ket_thuc",
    ))
    db.commit()
    _svc_moi(db).dat_moc(lenh.id, moc)
    return cv


def test_dong_gantt_bat_dau_o_luc_lenh_VAO_VIEC_chu_khong_o_moc(db, svc3, lenh, admin):
    """Thanh phải bắt đầu ở lúc lệnh thật sự vào việc; `bat_dau_at` vẫn là mốc phần còn lại.

    Hai số ở hai ô khác nhau — trộn làm một thì hoặc bàn nói dối (vẽ từ mốc), hoặc kéo-thả ghi
    nhầm mốc (ghi lúc vào việc, tức là dời cả bước đã xong).
    """
    vao = datetime(2026, 9, 9, 8, 0)
    _lenh_hai_buoc_da_chay(db, svc3, lenh, admin, moc=datetime(2026, 9, 14, 8, 0), vao_viec=vao)

    d = [r for r in _svc_moi(db).lich(tu=date(2026, 9, 7), den=date(2026, 9, 20))["dong"]
         if r["lsx_id"] == lenh.id][0]
    assert d["thuc_bat_dau_lenh"] == vao
    assert d["bat_dau_at"] >= datetime(2026, 9, 14, 8, 0)
    assert d["thuc_bat_dau_lenh"] < d["bat_dau_at"]
    # Mép phải theo thực tế: chỉ còn 1 bước để trải, nên phải sớm hơn mốc kế hoạch (trải cả 2).
    assert d["ket_thuc_thuc_te"] is not None
    assert d["ket_thuc_thuc_te"] <= d["ket_thuc"]


def test_lenh_chay_do_KHONG_bien_mat_khi_moc_bi_day_ra_sau_cua_so(db, svc3, lenh, admin):
    """Đẩy mốc phần còn lại ra sau cửa sổ thì lệnh vẫn phải nằm trên bàn: nó đã chạy TRONG cửa sổ.

    Lọc SQL chỉ theo `bat_dau_at` sẽ đánh rơi đúng những lệnh đang chạy dở — thứ người điều độ
    cần nhìn nhất.
    """
    vao = datetime(2026, 9, 9, 8, 0)
    _lenh_hai_buoc_da_chay(db, svc3, lenh, admin, moc=datetime(2026, 9, 25, 8, 0), vao_viec=vao)

    ds = _svc_moi(db).lich(tu=date(2026, 9, 8), den=date(2026, 9, 10))["dong"]
    assert lenh.id in [r["lsx_id"] for r in ds]


def test_phat_hanh_cap_nhat_thieu_ly_do_thi_LOI_CUA_MAN_khong_phai_ValueError(db, svc3, lenh, admin):
    """Thiếu lý do và "không còn gì để cập nhật" đều là `ValueError` ở tầng dưới — màn phải phân
    biệt được, nên chặn trước bằng lỗi của mình để router ra 400 kèm câu đọc được."""
    from app.services.xep_lich_3 import XepLich3Error

    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.phat_hanh(lenh.id, actor=admin)

    svc = _svc_moi(db)
    with pytest.raises(XepLich3Error) as e:
        svc.phat_hanh_cap_nhat(lenh.id, actor=admin, ly_do="ff")
    assert "lý do" in str(e.value).lower()


def test_doan_thuc_te_chi_om_phan_MAY_CHAY_khong_om_khoang_nam_cho(db, svc3, lenh, admin):
    """Đoạn `thuc_bat_dau_lenh → bat_dau_at` KHÔNG phải là "đã chạy" — phần lớn nó là NẰM CHỜ.

    Lệnh dưới đây chạy đúng 30 phút hôm 09/09 rồi chờ tới 14/09. Trước 10/09/2026 bàn tô cả 5 ngày
    một tông "đã chạy", đọc lên như máy quay suốt tuần. `doan_thuc_te` là lớp đậm vẽ đè lên nền
    chờ, và nó phải bám đúng phiên chạy có thật.
    """
    vao = datetime(2026, 9, 9, 8, 0)
    _lenh_hai_buoc_da_chay(db, svc3, lenh, admin, moc=datetime(2026, 9, 14, 8, 0), vao_viec=vao)

    d = [r for r in _svc_moi(db).lich(tu=date(2026, 9, 7), den=date(2026, 9, 20))["dong"]
         if r["lsx_id"] == lenh.id][0]
    assert d["doan_thuc_te"] == [{"tu": vao, "den": vao + timedelta(minutes=30)}]
    # …và nó ngắn hơn hẳn khoảng chờ tới mốc: đúng cái mà một tông màu đang giấu đi.
    assert d["doan_thuc_te"][0]["den"] < d["bat_dau_at"]


def test_ngay_nghi_theo_LICH_XUONG_chu_khong_phai_T7_va_CN(db, svc3, lenh, admin):
    """`/lich` phải tự trả ngày nghỉ; FE đoán "cuối tuần = T7 + CN" là sai với xưởng này.

    Xưởng khai `works_sat = true`, nên thứ 7 VẪN LÀM — bàn tô nó thành ngày nghỉ trong khi engine
    xếp việc vào đó. Lễ và làm bù thì FE không có đường nào đoán ra.
    """
    from app.models.work_calendar import KIND_OFF, KIND_WORK, SpecialDay

    db.add_all([
        SpecialDay(day=date(2026, 9, 15), kind=KIND_OFF, name="Nghỉ lễ thử"),
        SpecialDay(day=date(2026, 9, 20), kind=KIND_WORK, name="Làm bù chủ nhật"),
    ])
    db.commit()

    nghi = _svc_moi(db).lich(tu=date(2026, 9, 12), den=date(2026, 9, 20))["ngay_nghi"]
    assert date(2026, 9, 12) not in nghi      # thứ 7 — xưởng khai works_sat
    assert date(2026, 9, 13) in nghi          # chủ nhật
    assert date(2026, 9, 15) in nghi          # lễ khai tay
    assert date(2026, 9, 20) not in nghi      # chủ nhật nhưng làm bù
