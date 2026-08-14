"""Kỹ thuật máy — sửa chữa · bảo trì sinh từ `lich_bao_tri` của máy · cửa ảnh chứng thực.

Phần lõi test ở mức SERVICE với DB in-memory riêng (nhanh, không cần lifespan); riêng cửa ảnh và
RBAC test qua HTTP vì đó là thứ người dùng thật đâm vào.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    GIAI_DOAN_TRUOC,
    LOAI_PHIEU_BAO_TRI,
    LOAI_PHIEU_SUA_CHUA,
    TT_BT_HOAN_THANH,
    TT_SC_DA_SUA_XONG,
    TT_SC_DANG_SUA,
)
from app.models.may_thiet_bi import MayThietBi
from app.repositories.ky_thuat_may_repo import KyThuatMayRepository
from app.services.ky_thuat_may_service import (
    BO_QUA_THIEU_CHU_KY,
    BO_QUA_THIEU_NGAY_BAT_DAU,
    NGUON_NGAY_BAT_DAU,
    NGUON_PHIEU,
    KyThuatMayService,
    KyThuatMayThieuAnh,
    KyThuatMayValidationError,
    cong_chu_ky,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, KyThuatMayService(db, KyThuatMayRepository(db))


def _may(db, *, ma="BOBST-01", goi=None) -> MayThietBi:
    """Máy kèm lịch bảo trì khai sẵn — đúng hình dạng JSON mà form Máy ghi ra."""
    m = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="Bế",
                   fields_theo_loai={"lich_bao_tri": goi} if goi is not None else None)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _goi(**over) -> dict:
    g = {"id": "hm-abc", "viec": "Bảo trì 3 tháng", "so": 3, "don_vi": "thang",
         "hang_muc": [{"id": "hm-1", "ten": "Thay set dao bế (4 dao)"},
                      {"id": "hm-2", "ten": "Kiểm tra hệ thuỷ lực"}]}
    g.update(over)
    return g


def _anh_sau(svc, loai_phieu, phieu_id):
    svc.them_anh(loai_phieu, phieu_id, giai_doan=GIAI_DOAN_SAU,
                 file_name="sau.jpg", file_url="/api/files/x/sau.jpg", file_type="image/jpeg")


# ================= cộng chu kỳ =================


def test_cong_chu_ky_thang_chan_ngay_cuoi_thang():
    """31/01 + 1 tháng = 28/02, KHÔNG phải 03/03 — cộng 30 ngày là trượt sang tháng sau."""
    assert cong_chu_ky(date(2026, 1, 31), 1, "thang") == date(2026, 2, 28)
    assert cong_chu_ky(date(2026, 3, 15), 3, "thang") == date(2026, 6, 15)
    assert cong_chu_ky(date(2026, 5, 20), 1, "nam") == date(2027, 5, 20)
    assert cong_chu_ky(date(2026, 5, 20), 2, "tuan") == date(2026, 6, 3)
    assert cong_chu_ky(date(2026, 5, 20), 10, "ngay") == date(2026, 5, 30)


# ================= 3 nhánh của han_ke_tiep =================


def test_han_lay_tu_NGAY_BAT_DAU_khi_chua_co_phieu_nao():
    """Kỳ 1 rơi đúng vào ngày khai — đây là lý do ô "Bắt đầu từ" tồn tại."""
    db, svc = _svc()
    may = _may(db, goi=[_goi(ngay_bat_dau="2026-09-01")])
    han, nguon = svc.han_ke_tiep(may.id, _goi(ngay_bat_dau="2026-09-01"))
    assert (han, nguon) == (date(2026, 9, 1), NGUON_NGAY_BAT_DAU)


def test_han_khong_khai_ngay_bat_dau_thi_KHONG_doan():
    """Bản đầu coi như "tới hạn hôm nay" ⇒ một cú bấm đẻ 41 phiếu rác cùng ngày (12/08/2026).
    Nay thiếu mốc là KHÔNG tính, và nói ra lý do để người khai đi điền "Bắt đầu từ"."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    han, nguon = svc.han_ke_tiep(may.id, _goi())
    assert han is None and nguon == BO_QUA_THIEU_NGAY_BAT_DAU


def test_han_cua_may_noi_RO_ly_do_khong_tinh_duoc():
    """Hai lý do khác nhau ⇒ hai cách sửa khác nhau (điền "Mỗi … tháng" vs "Bắt đầu từ"),
    nên phải tách chứ không gộp một rọ "không tính được"."""
    db, svc = _svc()
    may = _may(db, ma="BE-01", goi=[
        _goi(id="hm-1", viec="Bảo trì 3 tháng"),                 # có chu kỳ, thiếu ngày bắt đầu
        _goi(id="hm-2", viec="Vệ sinh lớn", so=None),            # thiếu chu kỳ
    ])
    kq = {r["goi_ten"]: r for r in svc.han_cua_may(may.id)}
    assert kq["Bảo trì 3 tháng"]["han"] is None
    assert kq["Bảo trì 3 tháng"]["nguon"] == BO_QUA_THIEU_NGAY_BAT_DAU
    assert kq["Vệ sinh lớn"]["nguon"] == BO_QUA_THIEU_CHU_KY


def test_han_tu_PHIEU_hoan_thanh_gan_nhat_de_len_ngay_bat_dau():
    """Làm xong 03/05 với chu kỳ 3 tháng ⇒ kỳ sau 03/08 — mốc đi ra từ PHIẾU, không phải từ ô khai.

    Ngày hoàn thành phải ở QUÁ KHỨ: service chặn ngày tương lai (không ai xong việc chưa làm)."""
    db, svc = _svc()
    goi = _goi(ngay_bat_dau="2026-05-01")
    may = _may(db, goi=[goi])
    phieu = svc.tao_bao_tri({"may_id": may.id, "goi_id": "hm-abc",
                             "ngay_ke_hoach": date(2026, 5, 1)})
    _anh_sau(svc, LOAI_PHIEU_BAO_TRI, phieu.id)
    svc.doi_trang_thai_bao_tri(phieu.id, TT_BT_HOAN_THANH, ngay_hoan_thanh=date(2026, 5, 3))

    han, nguon = svc.han_ke_tiep(may.id, goi)
    assert (han, nguon) == (date(2026, 8, 3), NGUON_PHIEU)


def test_khong_nhan_ngay_hoan_thanh_o_TUONG_LAI():
    """Nhận ngày mai thì phiếu thành đã-xong khi máy chưa ai đụng, và kỳ kế tiếp bị đẩy lùi theo."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    phieu = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date.today()})
    _anh_sau(svc, LOAI_PHIEU_BAO_TRI, phieu.id)

    with pytest.raises(KyThuatMayValidationError):
        svc.doi_trang_thai_bao_tri(phieu.id, TT_BT_HOAN_THANH,
                                   ngay_hoan_thanh=date.today() + timedelta(days=1))

    # Hôm nay và quá khứ thì nhận bình thường.
    p = svc.doi_trang_thai_bao_tri(phieu.id, TT_BT_HOAN_THANH,
                                   ngay_hoan_thanh=date.today() - timedelta(days=2))
    assert p.ngay_hoan_thanh == date.today() - timedelta(days=2)


def test_goi_thieu_chu_ky_thi_khong_tinh_duoc_han():
    db, svc = _svc()
    may = _may(db, goi=[_goi(so=None)])
    han, nguon = svc.han_ke_tiep(may.id, _goi(so=None))
    assert han is None and nguon == BO_QUA_THIEU_CHU_KY


# ================= tạo phiếu định kỳ TỪ Ô DỰ KIẾN trên lịch =================
# (Nút "Sinh phiếu từ lịch" quét-cả-loạt đã gỡ 12/08/2026 — nó đẻ 41 phiếu rác trong một cú bấm.)


def test_tao_phiếu_theo_goi_thi_CHEP_chu_ky_va_viec_con():
    """Đây là việc xảy ra khi bấm một ô kỳ dự kiến trên lịch."""
    db, svc = _svc()
    may = _may(db, goi=[_goi(ngay_bat_dau=str(date.today()))])

    phieu = svc.tao_bao_tri({"may_id": may.id, "goi_id": "hm-abc",
                             "ngay_ke_hoach": date.today()})
    assert phieu.may_id == may.id and phieu.goi_id == "hm-abc"
    # Snapshot việc con + chu kỳ: người khai sửa gói về sau không làm đổi việc đã giao.
    assert [h["ten"] for h in phieu.hang_muc] == ["Thay set dao bế (4 dao)", "Kiểm tra hệ thuỷ lực"]
    assert all(h["xong"] is False for h in phieu.hang_muc)
    assert (float(phieu.chu_ky_so), phieu.chu_ky_don_vi) == (3.0, "thang")
    # Ngày dự kiến ban đầu chốt ngay lúc tạo — "Đã dời" sau này so với mốc này.
    assert phieu.ngay_ke_hoach_goc == phieu.ngay_ke_hoach


def test_den_ngay_thi_TU_SINH_phieu_va_khong_de_trung():
    """Đến hạn mà không tự sinh thì kỳ đó nằm im dưới dạng chấm mờ, không ai nhắc — người ta chỉ
    biết khi máy đã hỏng (chủ soi ra 14/08/2026). Ticker gọi hàm này mỗi vòng."""
    db, svc = _svc()
    may = _may(db, goi=[_goi(ngay_bat_dau=str(date.today()))])

    ra = svc.sinh_phieu_den_han()
    assert [p.may_id for p in ra] == [may.id]
    assert ra[0].ngay_ke_hoach == date.today()
    assert [h["ten"] for h in ra[0].hang_muc] == ["Thay set dao bế (4 dao)", "Kiểm tra hệ thuỷ lực"]

    # Ticker chạy 10 phút/lần cả ngày ⇒ lần sau KHÔNG được đẻ thêm.
    assert svc.sinh_phieu_den_han() == []


def test_phieu_tu_sinh_co_vet_trong_nhat_ky():
    """Phiếu tự nhiên hiện ra mà nhật ký trống thì không ai biết nó ở đâu ra. Bẫy đã dính: ticker
    dựng service KHÔNG kèm `AuditLogRepository` ⇒ `_ghi` im lặng bỏ qua."""
    from app.repositories.audit_repo import AuditLogRepository

    db, _ = _svc()
    svc = KyThuatMayService(db, KyThuatMayRepository(db), AuditLogRepository(db))
    may = _may(db, goi=[_goi(ngay_bat_dau=str(date.today()))])

    phieu = svc.sinh_phieu_den_han()[0]
    db.commit()
    vet = AuditLogRepository(db).list_by_target(f"ky_thuat_bao_tri:{phieu.id}", limit=10)
    assert any("tự sinh khi tới hạn" in (r.detail or "") for r in vet)
    assert all(r.actor_user_id is None for r in vet)   # hệ thống làm, không phải người


def test_tu_sinh_KHONG_dung_toi_ky_con_xa_hay_goi_khai_thieu():
    """Đây là chỗ nút "Sinh phiếu từ lịch" cũ đã chết: nó quét tuốt và đẻ 41 phiếu rác."""
    db, svc = _svc()
    _may(db, ma="IN-01", goi=[
        _goi(id="hm-1", viec="Tuần sau mới tới", ngay_bat_dau=str(date.today() + timedelta(days=7))),
        _goi(id="hm-2", viec="Thiếu ngày bắt đầu"),                 # có chu kỳ, chưa có mốc
        _goi(id="hm-3", viec="Thiếu chu kỳ", so=None, ngay_bat_dau=str(date.today())),
    ])
    assert svc.sinh_phieu_den_han() == []


def test_may_khong_khai_lich_thi_lich_rong_va_khong_no():
    """Cột JSON tự do: máy chưa khai gì / khai sai kiểu vẫn phải chạy được."""
    db, svc = _svc()
    _may(db, ma="IN-01")
    _may(db, ma="IN-02", goi=[])
    m3 = _may(db, ma="IN-03")
    m3.fields_theo_loai = {"lich_bao_tri": "hỏng kiểu"}
    db.commit()
    kq = svc.lich(date.today(), date.today() + timedelta(days=60))
    assert kq["phieu"] == [] and kq["du_kien"] == []


def test_han_cua_may_tra_ca_goi_va_phieu_dang_mo():
    """Nguồn cho dòng "Kỳ tới" ở tab Lịch bảo trì màn Thiết bị."""
    db, svc = _svc()
    may = _may(db, goi=[_goi(ngay_bat_dau="2026-09-01")])
    kq = svc.han_cua_may(may.id)
    assert kq[0]["han"] == date(2026, 9, 1) and kq[0]["phieu_dang_mo_id"] is None

    phieu = svc.tao_bao_tri({"may_id": may.id, "goi_id": "hm-abc",
                             "ngay_ke_hoach": date(2026, 9, 1)})
    assert svc.han_cua_may(may.id)[0]["phieu_dang_mo_id"] == phieu.id


# ================= lịch (calendar) =================


def test_lich_tra_ky_du_kien_theo_chu_ky_va_khong_chong_len_phieu_that():
    db, svc = _svc()
    may = _may(db, goi=[_goi(so=1, don_vi="thang", ngay_bat_dau="2026-09-01")])

    kq = svc.lich(date(2026, 9, 1), date(2026, 12, 31))
    assert kq["phieu"] == []
    assert [d["ngay"] for d in kq["du_kien"]] == [
        date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1),
    ]

    # Bấm ô dự kiến đầu tiên ⇒ 01/09 thành phiếu THẬT, chuỗi mờ phải bắt đầu từ kỳ sau. Vẽ chồng
    # một chấm dự kiến lên đúng ngày đã có phiếu là nói dối ngay trên lịch.
    svc.tao_bao_tri({"may_id": may.id, "goi_id": "hm-abc", "ngay_ke_hoach": date(2026, 9, 1)})
    kq2 = svc.lich(date(2026, 9, 1), date(2026, 12, 31))
    assert [p.ngay_ke_hoach for p in kq2["phieu"]] == [date(2026, 9, 1)]
    assert [d["ngay"] for d in kq2["du_kien"]] == [
        date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1),
    ]


def test_lich_bo_qua_goi_chua_khai_chu_ky():
    """Không khai chu kỳ thì không đoán được kỳ nào — thà không vẽ còn hơn vẽ một ngày bịa."""
    db, svc = _svc()
    _may(db, goi=[_goi(so=None, ngay_bat_dau="2026-09-01")])
    assert svc.lich(date(2026, 9, 1), date(2026, 12, 31))["du_kien"] == []


def test_api_lich_chan_khoang_qua_dai(client):
    h = _headers(client)
    ok = client.get("/api/ky-thuat-may/bao-tri/lich?tu=2026-08-01&den=2026-08-31", headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"phieu": [], "du_kien": []}

    qua_dai = client.get("/api/ky-thuat-may/bao-tri/lich?tu=2020-01-01&den=2030-01-01", headers=h)
    assert qua_dai.status_code == 422


# ================= cửa ảnh chứng thực =================


def test_khong_dong_duoc_phieu_sua_chua_khi_chua_co_anh_SAU():
    db, svc = _svc()
    may = _may(db, ma="CAN-01")
    phieu = svc.tao_sua_chua({"may_id": may.id, "bo_phan_hong": "Trục cán & bạc đạn"})

    with pytest.raises(KyThuatMayThieuAnh):
        svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DA_SUA_XONG)

    # Ảnh HIỆN TRẠNG không mở được cửa — cái gác cửa là ảnh CHỨNG THỰC sau khi làm.
    svc.them_anh(LOAI_PHIEU_SUA_CHUA, phieu.id, giai_doan=GIAI_DOAN_TRUOC,
                 file_name="truoc.jpg", file_url="/api/files/x/truoc.jpg", file_type="image/jpeg")
    with pytest.raises(KyThuatMayThieuAnh):
        svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DA_SUA_XONG)

    _anh_sau(svc, LOAI_PHIEU_SUA_CHUA, phieu.id)
    phieu = svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DA_SUA_XONG)
    assert phieu.trang_thai == TT_SC_DA_SUA_XONG and phieu.hoan_thanh_at is not None


def test_mo_lai_phieu_da_dong_thi_don_moc_hoan_thanh():
    db, svc = _svc()
    may = _may(db, ma="CAN-01")
    phieu = svc.tao_sua_chua({"may_id": may.id, "bo_phan_hong": "Trục cán"})
    _anh_sau(svc, LOAI_PHIEU_SUA_CHUA, phieu.id)
    svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DA_SUA_XONG)

    phieu = svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DANG_SUA)
    assert phieu.hoan_thanh_at is None and phieu.hoan_thanh_boi is None


def test_khong_go_duoc_anh_chung_thuc_cua_phieu_da_dong():
    db, svc = _svc()
    may = _may(db, ma="CAN-01")
    phieu = svc.tao_sua_chua({"may_id": may.id, "bo_phan_hong": "Trục cán"})
    _anh_sau(svc, LOAI_PHIEU_SUA_CHUA, phieu.id)
    svc.doi_trang_thai_sua_chua(phieu.id, TT_SC_DA_SUA_XONG)
    anh = svc.list_anh(LOAI_PHIEU_SUA_CHUA, phieu.id)[0]

    with pytest.raises(KyThuatMayValidationError):
        svc.xoa_anh(anh.id)


# ================= người nhận việc =================


def _user(db, *, username="tho1", ten="Lê Văn Thợ"):
    from app.models.user import User
    u = User(username=username, name=ten, password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_nguoi_lam_LA_nguoi_bam_xac_nhan_xong():
    """Chủ chốt 12/08/2026: bỏ bước nhận việc — ai bấm "Xác nhận đã bảo trì xong" là người làm."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    tho = _user(db)
    phieu = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 8, 12)})
    assert phieu.nguoi_thuc_hien_id is None      # phiếu còn dở KHÔNG mang tên ai

    _anh_sau(svc, LOAI_PHIEU_BAO_TRI, phieu.id)
    phieu = svc.doi_trang_thai_bao_tri(phieu.id, TT_BT_HOAN_THANH, actor_id=tho.id)
    assert phieu.nguoi_thuc_hien_id == tho.id
    assert phieu.nguoi_thuc_hien == "Lê Văn Thợ"   # tên SNAPSHOT, nghỉ việc vẫn tra được


def test_bao_tri_chi_con_HAI_trang_thai():
    """Nấc "đang thực hiện" đã bỏ — gọi tới nó phải bị chặn, không im lặng ghi giá trị lạ vào DB."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    phieu = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 8, 12)})
    with pytest.raises(KyThuatMayValidationError):
        svc.doi_trang_thai_bao_tri(phieu.id, "dang_thuc_hien")


def test_mo_lai_phieu_da_xong_thi_nha_ten_nguoi_lam():
    """Lối lùi cho phiếu ký nhầm: về hàng chờ thì phiếu không còn mang tên ai."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    tho = _user(db)
    phieu = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 8, 12)})
    _anh_sau(svc, LOAI_PHIEU_BAO_TRI, phieu.id)
    svc.doi_trang_thai_bao_tri(phieu.id, TT_BT_HOAN_THANH, actor_id=tho.id)

    phieu = svc.doi_trang_thai_bao_tri(phieu.id, "cho_thuc_hien", actor_id=tho.id)
    assert phieu.nguoi_thuc_hien_id is None and phieu.nguoi_thuc_hien is None
    assert phieu.ngay_hoan_thanh is None


# ================= KHÔNG xoá được phiếu, chấm hết =================


def test_api_khong_co_duong_nao_xoa_phieu(client):
    """Phiếu là VẾT của việc đã xảy ra ngoài đời (chủ chốt 12/08/2026): máy đã hỏng, có người đã
    báo, ảnh đã chụp. Không có nút, và cũng KHÔNG có endpoint — bịt nút mà để hở API thì vẫn xoá
    được bằng một dòng curl."""
    h = _headers(client)
    may = client.post("/api/may-thiet-bi", json={"ma": "CAN-01", "ten": "Cán 01",
                                                "loai_may": "Cán màng / UV"}, headers=h).json()
    sc = client.post("/api/ky-thuat-may/sua-chua",
                     json={"may_id": may["id"], "bo_phan_hong": "Trục cán"}, headers=h).json()
    bt = client.post("/api/ky-thuat-may/bao-tri",
                     json={"may_id": may["id"], "loai": "dot_xuat",
                           "ngay_ke_hoach": str(date.today())}, headers=h).json()

    assert client.delete(f"/api/ky-thuat-may/sua-chua/{sc['id']}", headers=h).status_code >= 400
    assert client.delete(f"/api/ky-thuat-may/bao-tri/{bt['id']}", headers=h).status_code >= 400
    # Và phiếu vẫn còn nguyên sau khi thử xoá.
    assert client.get(f"/api/ky-thuat-may/sua-chua/{sc['id']}", headers=h).status_code == 200
    assert client.get(f"/api/ky-thuat-may/bao-tri/{bt['id']}", headers=h).status_code == 200


def test_danh_sach_xep_viec_con_do_len_truoc_phieu_da_xong():
    """Phiếu hoàn thành chen giữa việc phải làm = càng chạy lâu càng phải cuộn."""
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    xong = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 1, 5)})
    _anh_sau(svc, LOAI_PHIEU_BAO_TRI, xong.id)
    svc.doi_trang_thai_bao_tri(xong.id, TT_BT_HOAN_THANH, ngay_hoan_thanh=date(2026, 1, 5))
    con_do = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 6, 20)})

    rows, _ = svc.list_bao_tri()
    assert [r.id for r in rows] == [con_do.id, xong.id]   # dù hạn muộn hơn vẫn lên trước

    # Bộ lọc dẫn xuất "can_lam" = mọi phiếu chưa xong, gộp 2 trạng thái cho khỏi bấm hai tab.
    chi_can_lam, tong = svc.list_bao_tri(trang_thai="can_lam")
    assert [r.id for r in chi_can_lam] == [con_do.id] and tong == 1


# ================= dời lịch · checklist =================


def test_api_lich_su_thao_tac_ghi_ai_doi_lich_va_ly_do(client):
    """Cột `ly_do_doi` chỉ giữ lần dời GẦN NHẤT ⇒ lý do lần đầu phải đọc được ở nhật ký, kèm tên
    người dời. Không có nó thì mở phiếu ra không ai biết ai dời và vì sao (chủ soi ra 12/08/2026)."""
    h = _headers(client)
    may = client.post("/api/may-thiet-bi", json={"ma": "BE-01", "ten": "Bế 01",
                                                "loai_may": "Bế"}, headers=h).json()
    p = client.post("/api/ky-thuat-may/bao-tri",
                    json={"may_id": may["id"], "loai": "dot_xuat",
                          "ngay_ke_hoach": str(date.today())}, headers=h).json()

    client.post(f"/api/ky-thuat-may/bao-tri/{p['id']}/doi-lich",
                json={"ngay_moi": str(date.today() + timedelta(days=3)),
                      "ly_do": "Chờ dao bế về"}, headers=h)
    client.post(f"/api/ky-thuat-may/bao-tri/{p['id']}/doi-lich",
                json={"ngay_moi": str(date.today() + timedelta(days=7)),
                      "ly_do": "Máy đang chạy đơn gấp"}, headers=h)

    r = client.get(f"/api/nhat-ky-danh-muc/ky_thuat_bao_tri/{p['id']}", headers=h)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    chi_tiet = " | ".join(i["detail"] for i in items)
    assert "Chờ dao bế về" in chi_tiet          # lý do lần ĐẦU vẫn còn, dù phiếu chỉ giữ lần cuối
    assert "Máy đang chạy đơn gấp" in chi_tiet
    assert all(i["actor_name"] for i in items)  # ai làm — không được để trống


def test_doi_lich_bat_buoc_ly_do_va_giu_moc_ban_dau():
    db, svc = _svc()
    may = _may(db, goi=[_goi()])
    phieu = svc.tao_bao_tri({"may_id": may.id, "ngay_ke_hoach": date(2026, 5, 18)})

    with pytest.raises(KyThuatMayValidationError):
        svc.doi_lich(phieu.id, date(2026, 5, 25), "  ")

    phieu = svc.doi_lich(phieu.id, date(2026, 5, 25), "Chờ dao bế về")
    assert phieu.ngay_ke_hoach == date(2026, 5, 25)
    assert phieu.ngay_ke_hoach_goc == date(2026, 5, 18)   # "Đã dời" dẫn xuất từ chỗ này
    assert phieu.ly_do_doi == "Chờ dao bế về"


def test_tick_hang_muc_ghi_duoc_xuong_db():
    """Cột JSON: sửa tại chỗ thì SQLAlchemy không thấy gì đổi và lặng lẽ không UPDATE."""
    db, svc = _svc()
    may = _may(db, goi=[_goi(ngay_bat_dau=str(date.today()))])
    phieu = svc.tao_bao_tri({"may_id": may.id, "goi_id": "hm-abc",
                             "ngay_ke_hoach": date.today()})

    svc.tick_hang_muc(phieu.id, "hm-1", True)
    db.expire_all()
    lai = svc.get_bao_tri(phieu.id)
    assert [h["xong"] for h in lai.hang_muc] == [True, False]

    with pytest.raises(KyThuatMayValidationError):
        svc.tick_hang_muc(phieu.id, "hm-khong-co", True)


def test_ma_phieu_chay_tang_dan():
    db, svc = _svc()
    may = _may(db, ma="CAN-01")
    a = svc.tao_sua_chua({"may_id": may.id, "bo_phan_hong": "Trục cán"})
    b = svc.tao_sua_chua({"may_id": may.id, "bo_phan_hong": "Cuộn dây gia nhiệt"})
    assert (a.ma, b.ma) == ("SC-0001", "SC-0002")


# ================= HTTP: cửa ảnh + RBAC =================


def _token(client, username="admin", password="admin123") -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(client) -> dict:
    return {"Authorization": f"Bearer {_token(client)}"}


def test_api_dong_phieu_thieu_anh_tra_409(client):
    h = _headers(client)
    may = client.post("/api/may-thiet-bi", json={"ma": "CAN-01", "ten": "Cán 01",
                                                "loai_may": "Cán màng / UV"}, headers=h).json()
    r = client.post("/api/ky-thuat-may/sua-chua",
                    json={"may_id": may["id"], "bo_phan_hong": "Trục cán & bạc đạn",
                          "muc_do": "nghiem_trong"}, headers=h)
    assert r.status_code == 201, r.text
    phieu = r.json()
    assert phieu["ma"].startswith("SC-") and phieu["co_anh_sau"] is False
    assert phieu["may_ma"] == "CAN-01"   # cột Máy đọc field dẫn xuất này

    dong = client.post(f"/api/ky-thuat-may/sua-chua/{phieu['id']}/trang-thai",
                       json={"trang_thai": "da_sua_xong"}, headers=h)
    assert dong.status_code == 409, dong.text


def test_api_khong_dang_nhap_bi_chan(client):
    assert client.get("/api/ky-thuat-may/sua-chua").status_code in (401, 403)
    assert client.get("/api/ky-thuat-may/bao-tri").status_code in (401, 403)


def test_api_phan_trang_va_loc_qua_han_o_SERVER(client):
    """Trước đây FE kéo `size=200` rồi lọc trên mảng ⇒ qua phiếu 201 là bảng âm thầm cắt mất."""
    h = _headers(client)
    may = client.post("/api/may-thiet-bi", json={"ma": "BE-01", "ten": "Bế 01",
                                                "loai_may": "Bế"}, headers=h).json()
    for i in range(5):
        client.post("/api/ky-thuat-may/bao-tri",
                    json={"may_id": may["id"], "loai": "dot_xuat",
                          "ngay_ke_hoach": str(date.today() - timedelta(days=i))}, headers=h)

    trang1 = client.get("/api/ky-thuat-may/bao-tri?page=1&size=2", headers=h).json()
    assert len(trang1["items"]) == 2 and trang1["total"] == 5   # total là TOÀN BỘ, không phải trang

    trang3 = client.get("/api/ky-thuat-may/bao-tri?page=3&size=2", headers=h).json()
    assert len(trang3["items"]) == 1
    assert {p["id"] for p in trang1["items"]} & {p["id"] for p in trang3["items"]} == set()

    # Lọc dẫn xuất chạy Ở SERVER: 4 phiếu hạn hôm qua trở về trước là quá hạn, phiếu hôm nay không.
    qua_han = client.get("/api/ky-thuat-may/bao-tri?trang_thai=qua_han&size=50", headers=h).json()
    assert qua_han["total"] == 4


def test_api_den_han_dem_phieu_toi_han_va_qua_han(client):
    """Nguồn của badge cạnh mục "Phiếu bảo trì" + con số ticker nhắc."""
    h = _headers(client)
    may = client.post("/api/may-thiet-bi", json={"ma": "BE-01", "ten": "Bế 01",
                                                "loai_may": "Bế"}, headers=h).json()
    client.post("/api/ky-thuat-may/bao-tri",
                json={"may_id": may["id"], "loai": "dot_xuat",
                      "ngay_ke_hoach": str(date.today() - timedelta(days=3))}, headers=h)
    client.post("/api/ky-thuat-may/bao-tri",
                json={"may_id": may["id"], "loai": "dot_xuat",
                      "ngay_ke_hoach": str(date.today())}, headers=h)
    # Phiếu tương lai KHÔNG được tính: badge là "việc phải làm bây giờ", không phải tổng số phiếu.
    client.post("/api/ky-thuat-may/bao-tri",
                json={"may_id": may["id"], "loai": "dot_xuat",
                      "ngay_ke_hoach": str(date.today() + timedelta(days=30))}, headers=h)

    r = client.get("/api/ky-thuat-may/bao-tri/den-han", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"total": 2, "qua_han": 1}


def test_api_route_chu_khong_bi_route_int_nuot(client):
    """Mọi path CHỮ dưới `/bao-tri/` phải khai TRƯỚC `/bao-tri/{phieu_id}` — FastAPI khớp theo thứ
    tự, để sau thì rơi vào route int và ăn 422 (bẫy đã dính ở `/may-thiet-bi/trang-thai`)."""
    h = _headers(client)
    assert client.get("/api/ky-thuat-may/bao-tri/den-han", headers=h).status_code == 200
    assert client.get(
        "/api/ky-thuat-may/bao-tri/lich?tu=2026-08-01&den=2026-08-31", headers=h
    ).status_code == 200

    # Hai endpoint đẻ/xoá HÀNG LOẠT đã gỡ ⇒ không để lại cửa hậu gọi thẳng qua API.
    assert client.post("/api/ky-thuat-may/bao-tri/sinh-tu-lich", headers=h).status_code >= 400
    assert client.post("/api/ky-thuat-may/bao-tri/don-phieu-chua-dung", headers=h).status_code >= 400
