"""Xếp lịch công đoạn 2 — TEST THẤT BẠI TRƯỚC (TDD) cho từng nhóm luật của spec.

Đọc kèm `docs/spec-xep-lich-2.md` §7 (ba mức kiểm soát) và §12 (11 kịch bản bắt buộc). File này
KHÔNG dựng lại engine cũ: nó chốt HỢP ĐỒNG của lớp v2 (`app.services.xep_lich_2`) — lưu vẫn vào
`xep_lich_cong_doan`, nhưng luật xếp/phát hành do v2 quyết.

Chiến thuật kiểm (theo đúng lối `test_xep_lich_dot2.py`):
- Luật THỜI GIAN thuần (chạy liên tục · trong ca · qua nửa đêm · đè khoá máy · trùng máy · vượt
  quân số · trước ngày vật tư) kiểm ở MỨC HÀM trong `constraint.py` — dựng cả luồng đơn→lệnh chỉ để
  so một phép là phí. Đây cũng là chỗ chống hồi quy rẻ nhất.
- Luật phụ thuộc DỮ LIỆU SỐNG (vật tư giữ chỗ · 409 · gate phát hành dùng chung · ngày lễ · hàng
  chờ) đi qua fixture luồng thật của `test_xep_lich_service`.
- Hai kịch bản CẤU TRÚC (§12.8 không còn khổ/màu/gsm · §12.11 mọi mutation đẩy SSE) kiểm bằng cách
  soi MÃ NGUỒN — không token cấm trong service, mọi route ghi đều `hub.broadcast`.
"""
from __future__ import annotations

import ast
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.cong_doan import CongDoan
from app.models.department import Department
from app.models.khuon_be import KhuonBe
from app.models.lsx import (
    LB_MAY, LB_TO, TT_DA_PHAT_HANH, TT_SAN_SANG, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from app.models.purchase import PR_PURCHASED, PurchaseRequest, PurchaseRequestLine
from app.models.vat_tu_giu_cho import NGUON_DANG_VE, VatTuGiuCho
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.giu_cho_repo import GiuChoRepository
from app.repositories.xep_lich_repo import XepLichRepository

from app.services.xep_lich_2 import (
    MUC_CANH_BAO, MUC_CHAN_DAT_LICH, MUC_CHAN_PHAT_HANH,
    XepLich2Blocked, XepLich2Conflict, XepLich2Error, XepLich2Service,
)
from app.services.xep_lich_2 import auto as A
from app.services.xep_lich_2 import constraint as C
from app.models.xep_lich import TT_DA_XEP, XepLichCongDoan
from app.services.xep_lich_service import XepLichConflict, XepLichNotFound, _naive
from app.repositories.xep_lich_2_repo import XepLich2Repository

from tests.test_xep_lich_service import (  # noqa: F401 — fixture dùng chung
    _giu_cho_du, _gop_in_va_san_sang, _hai_lsx_san_sang, _in_step, _khai_ca_xuong, _nha_cho,
    admin, bg_svc, customer, db, lsx_svc, orders, xl_svc,
)


def test_dong_xep_lich_mang_theo_khuon(db, orders, lsx_svc, xl_svc, admin, customer):
    """Xếp lịch KHÔNG chặn theo ngày dao về (chốt 04/09/2026) — nhưng phải HIỆN.

    Người điều độ cần biết TRƯỚC lúc kéo thanh, chứ không phải phát hiện ở khâu cuối khi tổ bấm
    Bắt đầu mà không có dao trong tay. Dòng mang sẵn mã · số kệ · tình trạng · ngày về, để màn
    Gantt và bảng dòng không phải tra lẻ từng dòng.
    """
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    buoc = _in_step(db, lsx.id)
    cd = db.get(CongDoan, buoc.cong_doan_id)
    cd.requires_tooling = True
    cd.tooling_type = "khuon_be"
    dao = KhuonBe(ma="KB-0001", ten="Dao thu", loai="khuon_be", so_ke="Kệ A3",
                  tinh_trang="dang_dung")
    db.add(dao)
    db.flush()
    buoc.khuon_be_id = dao.id
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)

    dong = [d for d in xl_svc.danh_sach()["items"] if d["lsx_cong_doan_id"] == buoc.id][0]
    assert dong["requires_tooling"] is True
    assert dong["khuon_ma"] == "KB-0001"
    assert dong["khuon_so_ke"] == "Kệ A3"
    assert dong["khuon_tinh_trang"] == "dang_dung"


def test_ban_lam_viec_mang_theo_khuon(db, orders, lsx_svc, xl_svc, admin, customer):
    """BÀN v2 (`workspace`) mới là thứ Gantt đọc — `danh_sach()` của lớp cũ chỉ nuôi màn Xung đột.

    Thiếu khối khuôn ở đây thì thanh trên bàn im lặng đúng lúc cần nói nhất, dù dữ liệu đã có đủ
    ở lệnh: đúng lỗi phát hiện khi nghiệm thu 04/09/2026.
    """
    lsx, lsx_khac = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    buoc = _in_step(db, lsx.id)
    cd = db.get(CongDoan, buoc.cong_doan_id)
    cd.requires_tooling = True
    cd.tooling_type = "khuon_be"
    dao = KhuonBe(ma="KB-0042", ten="Dao ban", loai="khuon_be",
                  tinh_trang="dang_dat_lam", ngay_ve_du_kien=date(2026, 9, 12))
    db.add(dao)
    db.flush()
    buoc.khuon_be_id = dao.id
    db.commit()
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=lsx_khac.id, actor=admin)  # lệnh không cần dao — để đối chứng

    # Dòng v2 KHÔNG phơi `lsx_cong_doan_id` ra view, nên bám theo id dòng xếp lịch của bước.
    row_id = db.query(XepLichCongDoan.id).filter_by(lsx_cong_doan_id=buoc.id).scalar()
    v2 = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    ban = v2.workspace(tu=date(2026, 9, 1), den=date(2026, 9, 30))
    dong = [d for d in ban["dong"] if d["id"] == row_id][0]
    assert dong["requires_tooling"] is True
    assert dong["khuon_ma"] == "KB-0042"
    assert dong["khuon_tinh_trang"] == "dang_dat_lam"
    assert dong["khuon_ngay_ve"] == "2026-09-12"

    # Lệnh đối chứng dùng CÙNG công đoạn nhưng chưa trỏ dao ⇒ đúng thế "cần dao mà chưa chốt":
    # khoá vẫn phải đủ (thanh đọc thẳng, không được vấp KeyError), chỉ mã dao là rỗng.
    khac = [d for d in ban["dong"] if d["id"] != row_id]
    assert khac and all(d["requires_tooling"] is True and d["khuon_ma"] is None
                        and d["khuon_ngay_ve"] is None for d in khac)


# ---------------------------------------------------------------------------
@pytest.fixture
def v2(db):
    return XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))


def _utc(y, mo, d, h, m=0) -> datetime:
    return datetime(y, mo, d, h, m, tzinfo=timezone.utc)


def _ma(van_de) -> set[str]:
    return {i["ma"] for i in van_de}


def _kcs_hoa(db, lsx_id: int) -> None:
    """Gắn tổ KCS lên bước CUỐI của lệnh, để qua cửa gate §4.4 (chặn thiếu KCS cuối khi phát hành).

    KCS-cuối suy TỰ ĐỘNG (2026-08-31, mg `0252`): bước CUỐI routing + tổ thực hiện có
    `is_kcs=true` — không còn cờ `la_kcs` khai tay để set song song.
    """
    d = Department(name="KCS Xưởng", code="KCS-XL", is_kcs=True)
    db.add(d)
    db.flush()
    buoc = db.query(LsxCongDoan).filter(LsxCongDoan.lsx_id == lsx_id).order_by(
        LsxCongDoan.thu_tu, LsxCongDoan.id
    ).all()
    buoc[-1].department_id = d.id
    db.commit()


def _in_theo_may(db, lsx_id: int) -> LsxCongDoan:
    """Bước in, ép về đường TÍNH THEO MÁY sạch: 5000 tờ / 5000 tờ-giờ = 60' chạy + 30' makeready."""
    step = _in_step(db, lsx_id)
    step.setup_phut, step.nang_suat, step.so_luong_vao = 0, 5000, 5000
    step.chay_phut, step.ve_sinh_phut, step.so_luot_chay = None, 0, 1
    db.commit()
    return step


# ======================================================================
# §12.1 + §12.5 — CHẠY LIÊN TỤC: đã bắt đầu thì `finish = start + chiếm máy`,
# không cắt theo ca, kéo qua cuối ca / nửa đêm là bình thường.
# ======================================================================
def test_chay_lien_tuc_khong_cat_theo_ca():
    start = _utc(2026, 7, 27, 20, 0)          # 20:00 trong ca 2 (14:00–22:00)
    finish = C.finish_lien_tuc(start, 700)     # 11h40 > phần còn lại của ca
    assert finish == start + timedelta(minutes=700)
    assert finish.date() > start.date(), "kéo qua cuối ca sang hôm sau, KHÔNG tách đoạn"


def test_cong_doan_qua_nua_dem():
    start = _utc(2026, 7, 27, 23, 0)
    assert C.finish_lien_tuc(start, 180) == _utc(2026, 7, 28, 2, 0)  # 23:00 + 3h = 02:00


# ======================================================================
# §7.1 `ngoai_ca` — giờ bắt đầu phải nằm trong một ca đã cấu hình (cửa chặn DUY NHẤT của ca).
# ======================================================================
def test_ngoai_ca_chan_khi_bat_dau_ngoai_khung():
    ca = [(840, 1320, False)]                   # 14:00–22:00
    assert C.ngoai_ca(_utc(2026, 7, 27, 20, 0), ca) is None            # trong ca
    vd = C.ngoai_ca(_utc(2026, 7, 27, 12, 0), ca)                      # trước ca
    assert vd is not None and vd["ma"] == "ngoai_ca" and vd["muc"] == MUC_CHAN_DAT_LICH


def test_ngoai_ca_hieu_ca_dem():
    ca = [(1320, 360, True)]                     # ca đêm 22:00 → 06:00 hôm sau
    assert C.ngoai_ca(_utc(2026, 7, 27, 23, 0), ca) is None            # 23:00 trong ca
    assert C.ngoai_ca(_utc(2026, 7, 27, 2, 0), ca) is None             # 02:00 (đuôi ca) trong ca
    assert C.ngoai_ca(_utc(2026, 7, 27, 12, 0), ca) is not None        # trưa: ngoài ca đêm


# ======================================================================
# §12.3 — máy hỏng/bảo trì nằm GIỮA khoảng chạy ⇒ CẢNH BÁO, không chặn (hạ mức 21/08/2026).
# ======================================================================
def test_de_vung_khoa_may_chi_canh_bao():
    start, finish = _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 12, 0)
    khoa = [(_utc(2026, 7, 27, 10, 0), _utc(2026, 7, 27, 11, 0))]      # bảo trì 10–11 GIỮA khoảng
    vd = C.de_vung_khoa_may(start, finish, khoa)
    # Vẫn PHẢI nói ra — hạ mức là nới một nấc, không phải xoá luật.
    assert vd is not None and vd["ma"] == "de_vung_khoa_may" and vd["muc"] == C.MUC_CANH_BAO
    # Khoá NẰM NGOÀI khoảng chạy thì không sao.
    assert C.de_vung_khoa_may(start, finish, [(_utc(2026, 7, 27, 13, 0),
                                               _utc(2026, 7, 27, 14, 0))]) is None


# ======================================================================
# §7.1 `trung_may` — trùng việc khác trên cùng máy.
# ======================================================================
def test_trung_may_khi_chong_gio():
    start, finish = _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 10, 0)
    da_xep = [(_utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 11, 0))]     # chồng 09–10
    assert C.trung_may(start, finish, da_xep)["ma"] == "trung_may"
    # Nối đuôi (10–12) không phải trùng.
    assert C.trung_may(start, finish, [(_utc(2026, 7, 27, 10, 0),
                                        _utc(2026, 7, 27, 12, 0))]) is None


# Mốc trong DB lẻ giây (auto-xếp lấy từ `now()`) còn ô nhập giờ chỉ tới PHÚT ⇒ việc nối đuôi bị
# hô trùng oan. Dung sai 1 phút phải nuốt lệch dưới phút, nhưng KHÔNG được nuốt trùng thật.
def test_trung_may_bo_qua_chong_lan_le_giay():
    start, finish = _utc(2026, 7, 27, 10, 54), _utc(2026, 7, 27, 12, 11)
    truoc = (_utc(2026, 7, 27, 10, 22),
             _utc(2026, 7, 27, 10, 54).replace(second=29, microsecond=870360))
    assert C.trung_may(start, finish, [truoc]) is None          # chồng 29,87 giây ⇒ bỏ qua
    # Chồng 2 phút vẫn là trùng.
    that = (_utc(2026, 7, 27, 10, 22), _utc(2026, 7, 27, 10, 56))
    assert C.trung_may(start, finish, [that])["ma"] == "trung_may"


# Mọi mốc GHI XUỐNG phải tròn phút — `service._tinh` và `auto._ap` đều đi qua đây.
def test_tron_phut_cat_giay():
    moc = _utc(2026, 7, 27, 10, 54).replace(second=29, microsecond=870360)
    assert C.tron_phut(moc) == _utc(2026, 7, 27, 10, 54)
    assert C.tron_phut(None) is None


# ======================================================================
# §12.4 — ba việc CÙNG TỔ chồng nhau làm vượt quân số ⇒ chặn (`vuot_quan_so_to`).
# Kiểm ĐỈNH đồng thời, không phải tổng ngày.
# ======================================================================
def test_vuot_quan_so_to_theo_dinh_chong_gio():
    # A 08–10 (2 người), B 09–11 (2), C 12–13 (2). Đỉnh 09–10 = 4 người.
    xep = [
        (_utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 10, 0), 2),
        (_utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 11, 0), 2),
        (_utc(2026, 7, 27, 12, 0), _utc(2026, 7, 27, 13, 0), 2),
    ]
    assert C.vuot_quan_so_to(xep, quan_so=3)["ma"] == "vuot_quan_so_to"   # đỉnh 4 > 3
    assert C.vuot_quan_so_to(xep, quan_so=4) is None                       # đỉnh 4 = 4: vừa đủ
    # Xếp NỐI TIẾP (không chồng) thì đỉnh chỉ là 2, quân số 3 vẫn ổn.
    tuan_tu = [
        (_utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 9, 0), 2),
        (_utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 10, 0), 2),
    ]
    assert C.vuot_quan_so_to(tuan_tu, quan_so=3) is None


# ======================================================================
# ĐỢT 2 — Tầng CẢNH BÁO còn thiếu (§7.3): lấn việc kế (chạy tới max) · máy sắp bảo trì ·
# tải máy/tổ cao CHIA MỨC. Tất cả chỉ NHẮC (MUC_CANH_BAO), không chặn. Soi ở mức hàm.
# ======================================================================
def test_lan_viec_ke_canh_bao_khi_max_lan_sang_viec_ke():
    finish = _utc(2026, 7, 27, 9, 30)            # chuẩn xong 09:30 (đã qua cửa trùng máy)
    da_xep = [(_utc(2026, 7, 27, 10, 0), _utc(2026, 7, 27, 12, 0))]   # việc kế bắt đầu 10:00
    # max xong 10:30 > việc kế 10:00 ⇒ cảnh báo lấn.
    vd = C.lan_viec_ke(finish, _utc(2026, 7, 27, 10, 30), da_xep)
    assert vd is not None and vd["ma"] == "lan_viec_ke" and vd["muc"] == MUC_CANH_BAO
    # max xong 09:50 < việc kế 10:00 ⇒ không lấn.
    assert C.lan_viec_ke(finish, _utc(2026, 7, 27, 9, 50), da_xep) is None
    # Không có dải max (finish_max == finish) ⇒ không thể lấn.
    assert C.lan_viec_ke(finish, finish, da_xep) is None
    # Không có việc kế nào sau finish ⇒ không lấn.
    assert C.lan_viec_ke(finish, _utc(2026, 7, 27, 11, 0), []) is None


def test_sap_bao_tri_canh_bao_khi_khoa_toi_gan():
    finish = _utc(2026, 7, 27, 9, 30)
    # Kỳ khoá 11:00 (cách 1.5h sau finish, trong ngưỡng 2 ngày) ⇒ cảnh báo.
    gan = [(_utc(2026, 7, 27, 11, 0), _utc(2026, 7, 27, 12, 0))]
    vd = C.sap_bao_tri(finish, gan)
    assert vd is not None and vd["ma"] == "sap_bao_tri" and vd["muc"] == MUC_CANH_BAO
    # Kỳ khoá tận 5 ngày sau ⇒ ngoài ngưỡng, không nhắc.
    assert C.sap_bao_tri(finish, [(_utc(2026, 8, 1, 8, 0), _utc(2026, 8, 1, 9, 0))]) is None
    # Kỳ khoá đã QUA (trước finish) ⇒ không nhắc.
    assert C.sap_bao_tri(finish, [(_utc(2026, 7, 27, 6, 0), _utc(2026, 7, 27, 7, 0))]) is None
    assert C.sap_bao_tri(None, gan) is None


def test_tai_to_cao_chia_muc():
    assert C.tai_to_cao(6, 8)["mo_ta"].startswith("Tổ tải cao")        # 75% → cao
    assert C.tai_to_cao(7, 8)["mo_ta"].startswith("Tổ tải cao")        # 87.5% → cao
    assert "rất cao" in C.tai_to_cao(8, 8)["mo_ta"]                    # 100% (vừa kịch) → rất cao
    assert C.tai_to_cao(8, 8)["muc"] == MUC_CANH_BAO
    assert C.tai_to_cao(5, 8) is None                                  # 62.5% < 75% → không nhắc
    assert C.tai_to_cao(9, 8) is None                                  # đã vượt → vuot_quan_so_to lo
    assert C.tai_to_cao(1, 0) is None                                  # chưa khai quân số


# Ca THẬT của xưởng (bản khai đang chạy trên Postgres dev) — BỐN ca GỐI NHAU phủ trọn 24h.
CA_XUONG_GOI_NHAU = [
    (360, 840, False),        # Ca 1        06:00–14:00 = 480'
    (480, 1020, False),       # Hành chính 08:00–17:00 = 540'  (nằm GỌN trong Ca 1 + Ca 2)
    (840, 1320, False),       # Ca 2        14:00–22:00 = 480'
    (1320, 360, True),        # Ca 3        22:00–06:00 = 480'  (qua đêm)
]


def test_quy_ca_phut_ca_GOI_NHAU_chi_dem_MOT_lan():
    """⭐ Mẫu số của MọI con số tải máy. Cộng thẳng độ dài từng ca ra 1980' cho một ngày chỉ có
    1440' — Hành chính bị đếm hai lần vì nằm gọn trong Ca 1 + Ca 2 ⇒ tất cả % tải thấp giả ~27%
    (màn hiện 7% trong khi thực là 9%). Lỗi này Ủ từ 21/08/2026 (mg 0226 cho engine đọc ca thật),
    trước đó hàm rơi về fallback 480' nên không ai thấy.
    """
    cong_thang = sum((1440 - b + e) if qd else (e - b) for b, e, qd in CA_XUONG_GOI_NHAU)
    assert cong_thang == 1980                                         # phép CŨ — vượt quá 24h
    assert C.phut_ca_moi_ngay(CA_XUONG_GOI_NHAU) == 1440              # phép MỚI — hợp các khoảng

    # Hành chính không góp thêm giờ nào: bỏ nó đi mẫu số phải Y NGUYÊN.
    assert C.phut_ca_moi_ngay([c for c in CA_XUONG_GOI_NHAU if c != (480, 1020, False)]) == 1440

    # Tải thật của một máy bận 105' trong ngày: 105/1440 = 7.3% (cũ: 105/1980 = 5.3%).
    assert round(105 / C.phut_ca_moi_ngay(CA_XUONG_GOI_NHAU) * 100) == 7

    # Ca RỜI NHAU vẫn cộng bình thường — sửa chồng lấn không được ăn bớt của xưởng khai rời.
    assert C.phut_ca_moi_ngay([(0, 240, False), (720, 960, False)]) == 480
    # Chồng MỘT PHẦN (08–16 + 14–22): 480 + 480 − 120 gối = 840.
    assert C.phut_ca_moi_ngay([(480, 960, False), (840, 1320, False)]) == 840
    # Ca đêm chồng chính đuôi nó (06:00–06:00 = trọn ngày) không được vượt 1440.
    assert C.phut_ca_moi_ngay([(360, 360, True)]) == 1440
    assert C.phut_ca_moi_ngay([]) == 0                                # chưa khai ca nào


def test_tai_may_cao_chia_muc_va_quy_gio_ca():
    ca = [(480, 960, False)]                                           # 08:00–16:00 = 480'
    assert C.phut_ca_moi_ngay(ca) == 480
    assert C.phut_ca_moi_ngay([(1320, 360, True)]) == 480             # ca đêm 22:00→06:00 = 480'
    assert C.tai_may_cao(410, 480)["mo_ta"].startswith("Máy tải cao") # 85% → cao
    assert "rất cao" in C.tai_may_cao(480, 480)["mo_ta"]             # 100% → rất cao
    assert C.tai_may_cao(300, 480) is None                            # 62.5% < 85% → không nhắc
    assert C.tai_may_cao(400, 0) is None                              # chưa khai ca


def test_dinh_dong_thoi_dung_chung_voi_vuot_quan_so():
    xep = [
        (_utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 10, 0), 2),
        (_utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 11, 0), 2),
    ]
    assert C.dinh_dong_thoi(xep) == 4                                  # chồng 09–10 → đỉnh 4
    assert C.dinh_dong_thoi([]) == 0


def test_van_de_dat_lich_gan_du_ba_canh_bao_moi_qua_wiring(v2, monkeypatch):
    """Wiring: `_van_de_dat_lich` gọi đúng ba luật mới với `finish_max` + khoảng máy đã bóc.

    Ép `ctx` trả bối cảnh tối giản (không vật tư/tiền nhiệm/hạn) để chỉ còn ba cảnh báo mới nổi lên,
    và cả bốn phải là MỨC CẢNH BÁO — không được biến thành chặn đặt lịch."""
    ca = [(480, 960, False)]                                          # 08:00–16:00
    monkeypatch.setattr(v2.ctx, "ca_windows", lambda: ca)
    monkeypatch.setattr(v2.ctx, "ngay_vat_tu", lambda dong: None)
    monkeypatch.setattr(v2.ctx, "tien_nhiem_finish", lambda dong: [])
    monkeypatch.setattr(v2.ctx, "hai_han", lambda dong: (None, None))
    monkeypatch.setattr(v2.ctx, "khoang_chan_may",
                        lambda may_id: [(_utc(2026, 7, 27, 11, 0), _utc(2026, 7, 27, 12, 0))])
    # Việc kế đã xếp 10:00–16:00 (không đè việc đang đặt 08:00–09:30) — vừa là mốc lấn, vừa nạp tải máy.
    ke = [(_utc(2026, 7, 27, 10, 0), _utc(2026, 7, 27, 16, 0))]
    monkeypatch.setattr(v2.ctx, "khoang_may_da_xep", lambda may_id, exclude_id: ke)
    # `lan_viec_ke` ăn nền HẸP HƠN (việc của LỆNH KHÁC) — ở đây việc kế là của lệnh khác nên vẫn kêu.
    monkeypatch.setattr(v2.ctx, "khoang_may_lenh_khac", lambda may_id, exclude_id, dong: ke)
    monkeypatch.setattr(v2.ctx, "quan_so", lambda dept, ngay: {"so_nguoi": 8, "go_de": False})
    monkeypatch.setattr(v2.ctx, "placements_to", lambda dept, exclude_id: [])
    monkeypatch.setattr(v2.ctx, "_so_nguoi", lambda dong: 7)          # đỉnh 7/8 → tải tổ cao

    shadow = SimpleNamespace(nguon="lsx", loai_buoc=LB_MAY, lsx_id=1, lsx_cong_doan_id=1,
                             bai_ghep_id=None, bai_ghep_cong_doan_id=None, may_id=9,
                             department_id=3, nha_cung_cap=None)
    vd = v2._van_de_dat_lich(
        shadow, start=_utc(2026, 7, 27, 8, 0), finish=_utc(2026, 7, 27, 9, 30),
        finish_max=_utc(2026, 7, 27, 10, 30), may_id=9, department_id=3,
        canh_bao=None, exclude_id=999,
    )
    codes = {i["ma"] for i in vd}
    assert {"lan_viec_ke", "sap_bao_tri", "tai_to_cao", "tai_may_cao"} <= codes
    assert "trung_may" not in codes and "de_vung_khoa_may" not in codes   # không đè → không chặn
    assert all(i["muc"] == MUC_CANH_BAO for i in vd), "cả bốn chỉ nhắc, không chặn đặt lịch"


def test_lan_viec_ke_im_khi_viec_ke_la_buoc_sau_cua_chinh_lenh(v2, monkeypatch):
    """Việc kế trên máy là bước sau của CHÍNH lệnh này ⇒ KHÔNG cảnh báo lấn (25/08/2026).

    Bước sau vốn phải đợi bước trước xong: bước trước chạy chậm thì cả dây trượt theo, không ai mất
    máy. Nhưng nó vẫn là việc thật trên máy — TẢI MÁY vẫn phải đếm nó, và `trung_may` vẫn soi nó."""
    ca = [(480, 960, False)]
    monkeypatch.setattr(v2.ctx, "ca_windows", lambda: ca)
    monkeypatch.setattr(v2.ctx, "ngay_vat_tu", lambda dong: None)
    monkeypatch.setattr(v2.ctx, "tien_nhiem_finish", lambda dong: [])
    monkeypatch.setattr(v2.ctx, "hai_han", lambda dong: (None, None))
    monkeypatch.setattr(v2.ctx, "khoang_chan_may", lambda may_id: [])
    ke = [(_utc(2026, 7, 27, 10, 0), _utc(2026, 7, 27, 16, 0))]
    monkeypatch.setattr(v2.ctx, "khoang_may_da_xep", lambda may_id, exclude_id: ke)
    monkeypatch.setattr(v2.ctx, "khoang_may_lenh_khac", lambda may_id, exclude_id, dong: [])
    monkeypatch.setattr(v2.ctx, "quan_so", lambda dept, ngay: {"so_nguoi": 8, "go_de": False})
    monkeypatch.setattr(v2.ctx, "placements_to", lambda dept, exclude_id: [])
    monkeypatch.setattr(v2.ctx, "_so_nguoi", lambda dong: 1)

    shadow = SimpleNamespace(nguon="lsx", loai_buoc=LB_MAY, lsx_id=1, lsx_cong_doan_id=1,
                             bai_ghep_id=None, bai_ghep_cong_doan_id=None, may_id=9,
                             department_id=3, nha_cung_cap=None)
    vd = v2._van_de_dat_lich(
        shadow, start=_utc(2026, 7, 27, 8, 0), finish=_utc(2026, 7, 27, 9, 30),
        finish_max=_utc(2026, 7, 27, 10, 30), may_id=9, department_id=3,
        canh_bao=None, exclude_id=999,
    )
    codes = {i["ma"] for i in vd}
    assert "lan_viec_ke" not in codes, "bước sau của chính lệnh mình không phải việc bị lấn"
    assert "tai_may_cao" in codes, "việc kế vẫn là việc thật trên máy — tải máy phải đếm nó"


def test_ctx_khoang_may_lenh_khac_chi_bo_viec_cung_lenh(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Nền hẹp của `lan_viec_ke`: bỏ việc CÙNG lệnh, giữ nguyên việc của lệnh khác."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    l0, l1 = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    inb, xa = _chuoi_in_xa(db, l0.id)
    in1 = _in_theo_may(db, l1.id)
    in1.may_id = inb.may_id                                   # ép cả ba bước về CÙNG một máy
    db.commit()
    v2.tao_nhap(nguon="lsx", id=l0.id, actor=admin)
    v2.tao_nhap(nguon="lsx", id=l1.id, actor=admin)

    rep = XepLichRepository(db)
    d_in = next(d for d in rep.by_lsx(l0.id) if d.lsx_cong_doan_id == inb.id)
    d_xa = next(d for d in rep.by_lsx(l0.id) if d.lsx_cong_doan_id == xa.id)
    d_l1 = next(d for d in rep.by_lsx(l1.id) if d.lsx_cong_doan_id == in1.id)
    v2.luu(dong_id=d_in.id, patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=d_in.updated_at, actor=admin)

    may = inb.may_id
    assert len(v2.ctx.khoang_may_da_xep(may, d_xa.id)) == 1     # nền của `trung_may`: thấy đủ
    assert v2.ctx.khoang_may_lenh_khac(may, d_xa.id, d_xa) == []          # cùng lệnh → bỏ
    assert len(v2.ctx.khoang_may_lenh_khac(may, d_l1.id, d_l1)) == 1      # lệnh khác → giữ


# ======================================================================
# §7.2 — đã chọn GIỜ mà chưa gán máy/tổ/NCC ⇒ CHẶN ĐẶT LỊCH (không âm thầm hạ trạng thái).
# ======================================================================
def test_chua_tai_nguyen_la_chan_dat_lich():
    t = _utc(2026, 7, 27, 8, 0)
    vd = C.chua_tai_nguyen(t, None, None, None)
    assert vd["ma"] == "chua_tai_nguyen" and vd["muc"] == MUC_CHAN_DAT_LICH
    assert C.chua_tai_nguyen(t, 9, None, None) is None                 # có máy → ok
    assert C.chua_tai_nguyen(t, None, 3, None) is None                 # có tổ → ok
    assert C.chua_tai_nguyen(t, None, None, "Xưởng ngoài A") is None   # có NCC → ok
    assert C.chua_tai_nguyen(t, None, None, "   ")["ma"] == "chua_tai_nguyen"  # NCC rỗng vẫn chặn
    assert C.chua_tai_nguyen(None, None, None, None) is None           # chưa chọn giờ → không xét ở đây


def test_chua_tai_nguyen_wiring_qua_van_de_dat_lich(v2, monkeypatch):
    """WIRING: `_van_de_dat_lich` phải gọi `chua_tai_nguyen` — chọn giờ mà trống cả máy/tổ/NCC thì
    nổi đúng vấn đề chặn đặt lịch (thay cho việc âm thầm hạ trạng thái ở `luu`)."""
    monkeypatch.setattr(v2.ctx, "ca_windows", lambda: [(480, 960, False)])   # 08:00–16:00
    monkeypatch.setattr(v2.ctx, "ngay_vat_tu", lambda dong: None)
    monkeypatch.setattr(v2.ctx, "tien_nhiem_finish", lambda dong: [])
    shadow = SimpleNamespace(nguon="lsx", loai_buoc=LB_MAY, lsx_id=1, lsx_cong_doan_id=1,
                             bai_ghep_id=None, bai_ghep_cong_doan_id=None, may_id=None,
                             department_id=None, nha_cung_cap=None)
    vd = v2._van_de_dat_lich(shadow, start=_utc(2026, 7, 27, 8, 0), finish=None,
                             may_id=None, department_id=None, canh_bao=None, exclude_id=999)
    chan = [i for i in vd if i["ma"] == "chua_tai_nguyen"]
    assert chan and chan[0]["muc"] == MUC_CHAN_DAT_LICH


# ======================================================================
# §12.6 — vật tư có NGÀY HỨA VỀ ⇒ không được bắt đầu trước ca đầu tiên của ngày đó.
# ======================================================================
def test_truoc_ngay_vat_tu_la_chan():
    ca = [(480, 960, False)]                     # 08:00–16:00
    ngay_ve = date(2026, 7, 28)
    assert C.truoc_ngay_vat_tu(_utc(2026, 7, 28, 7, 0), ngay_ve, ca)["ma"] == "truoc_ngay_vat_tu"
    assert C.truoc_ngay_vat_tu(_utc(2026, 7, 28, 8, 0), ngay_ve, ca) is None   # đúng ca đầu ngày về
    assert C.truoc_ngay_vat_tu(_utc(2026, 7, 28, 8, 0), None, ca) is None      # chưa có ngày ⇒ không chặn ở đây


# ======================================================================
# §12.9 — hai người sửa cùng một dòng ⇒ 409, KHÔNG ghi đè.
# ======================================================================
def test_luu_dong_thoi_bao_409(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]
    moc_cu = dong.updated_at

    v2.luu(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=moc_cu, actor=admin)                     # người 1: OK

    with pytest.raises(XepLich2Conflict):                              # người 2 cầm mốc CŨ → 409
        v2.luu(dong_id=dong.id, patch={"may_id": step.may_id, "start_at": _utc(2026, 7, 27, 9, 0)},
               expected_updated_at=moc_cu, actor=admin)


# ======================================================================
# §12.2 — ngày lễ vẫn xếp được như ngày thường (chỉ tô nền + ghi chú).
# ======================================================================
def test_ngay_le_van_xep_duoc_chi_to_nen(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    from app.models.work_calendar import KIND_OFF, SpecialDay
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    ngay = date(2026, 7, 27)
    db.add(SpecialDay(day=ngay, kind=KIND_OFF, name="Ngày lễ thử"))
    db.commit()
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = XepLichRepository(db).by_lsx(lsx.id)[0]

    pv = v2.xem_truoc(dong_id=dong.id,
                      patch={"may_id": step.may_id, "start_at": _utc(2026, 7, 27, 8, 0)})
    assert pv["finish_at"] is not None, "ngày lễ vẫn xếp được"
    assert "ngoai_ca" not in _ma(pv["van_de"])

    ws = v2.workspace(tu=ngay, den=ngay)
    assert any(h["ngay"] == ngay and h["ten"] == "Ngày lễ thử" for h in ws["ngay_le"])


# ======================================================================
# §8 — vừa 'Đưa vào kế hoạch' xong, dòng nháp CHƯA đặt giờ vẫn phải nằm trên bàn
# (bất kể cửa sổ), nếu không lệnh vừa xếp sẽ bốc hơi khỏi board.
# ======================================================================
def test_nhap_chua_gio_hien_tren_ban(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)          # sinh dòng nháp, CHƯA có giờ

    rows = XepLichRepository(db).by_lsx(lsx.id)
    assert rows and all(r.start_at is None for r in rows), "nháp chưa đặt giờ"

    ids_nhap = {r.id for r in rows}
    # Cửa sổ nào cũng thấy — việc chưa xếp không thuộc tuần nào.
    for tu in (date(2026, 7, 20), date(2027, 1, 1)):
        ws = v2.workspace(tu=tu, den=tu + timedelta(days=13))
        tren_ban = {d["id"] for d in ws["dong"]}
        assert ids_nhap <= tren_ban, f"dòng nháp phải hiện trên bàn {tu}"
        assert all(d["start_at"] is None for d in ws["dong"] if d["id"] in ids_nhap)


# ======================================================================
# item 15 — mỗi thanh trên bàn kèm MỨC nặng nhất tại chỗ đang đặt (dùng CHUNG detector
# `_van_de_dat_lich` với panel/xem-trước) để dải chân bàn đếm theo mức, số bấm được nổi thanh.
# ======================================================================
def test_workspace_dong_kem_muc_nang_nhat(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    ls = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx = ls[0]
    inb = _in_theo_may(db, lsx.id)
    ngay = date(2026, 7, 27)
    lsx.han_hoan_thanh_sx = ngay                       # xong cùng ngày ⇒ đệm 0 ⇒ sat_han_sx (canh_bao)
    db.commit()
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    v2.luu(dong_id=dong.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)
    # LSX thứ hai: nháp CHƯA đặt giờ ⇒ không có thanh ⇒ muc None.
    _in_theo_may(db, ls[1].id)
    v2.tao_nhap(nguon="lsx", id=ls[1].id, actor=admin)

    ws = v2.workspace(tu=ngay, den=ngay)
    d = next(x for x in ws["dong"] if x["id"] == dong.id)
    assert "muc" in d, "mỗi dòng phải kèm khoá muc"
    assert d["muc"] == "canh_bao", "xếp sát hạn ⇒ cảnh báo, không chặn đặt lịch"
    # Dòng ĐÃ có giờ chỉ mang None hoặc canh_bao — chan_dat_lich đã bị `luu` chặn từ đầu.
    assert all(x["muc"] in (None, "canh_bao") for x in ws["dong"] if x["start_at"] is not None)
    # Nháp chưa-giờ ⇒ muc None (không có thanh để đếm mức).
    assert any(x["start_at"] is None and x["muc"] is None for x in ws["dong"])


# ======================================================================
# §12.6 + §12.10 — vật tư chưa giữ đủ ⇒ chặn PHÁT HÀNH (nháp vẫn tạo được).
# Gate là DÙNG CHUNG: màn cũ phát hành cũng vấp đúng luật này (§9.3).
# ======================================================================
def test_nhap_cho_phep_thieu_vat_tu(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    _nha_cho(db, [lsx.id])                              # bỏ giữ chỗ → vật tư CHƯA đủ
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)   # KHÔNG raise: nháp cho phép thiếu vật tư
    assert XepLichRepository(db).by_lsx(lsx.id), "vẫn tạo được lịch nháp"


def test_vat_tu_chua_du_chan_phat_hanh(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    assert "vat_tu_chua_du" not in _ma(v2.kiem_phat_hanh(nguon="lsx", id=lsx.id))  # đã giữ đủ

    _nha_cho(db, [lsx.id])                             # nhả giữ chỗ
    vd = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    assert "vat_tu_chua_du" in _ma(vd)
    assert all(i["muc"] == MUC_CHAN_PHAT_HANH for i in vd if i["ma"] == "vat_tu_chua_du")


def test_phat_hanh_man_cu_khong_vuot_gate_v2(db, orders, lsx_svc, xl_svc, admin, customer):
    """§9.3 — router màn cũ gọi vào cùng gate v2. Thiếu vật tư thì phát hành từ màn cũ CŨNG chặn."""
    from app.services.xep_lich_van_de_service import XepLichVanDeService
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    xl_svc.dua_vao_lsx(lsx_id=lsx.id, actor=admin)     # lập kế hoạch qua màn cũ
    _nha_cho(db, [lsx.id])                             # rồi vật tư mất giữ chỗ
    vd_svc = XepLichVanDeService(db, AuditLogRepository(db))
    with pytest.raises(Exception):                     # gate chung chặn (vat_tu_chua_du)
        vd_svc.phat_hanh_lsx(lsx_id=lsx.id, actor=admin)


# ======================================================================
# §12.7 — hàng chờ chia hai rổ; lệnh gấp nổi cờ.
# ======================================================================
def test_queue_chia_hai_ro_va_co_co_gap(v2, db, orders, lsx_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    created[0].is_rush = True
    db.commit()
    q = v2.queue()
    assert "xep_duoc" in q and "bi_chan" in q
    all_items = {r["id"]: r for r in q["xep_duoc"] + q["bi_chan"] if r["nguon"] == "lsx"}
    assert created[0].id in all_items and all_items[created[0].id]["is_rush"] is True


# ======================================================================
# Đợt 4 · item 12 — hàng chờ kèm hạn giao + số công đoạn chưa xếp.
# ======================================================================
def test_queue_kem_han_giao_va_so_cong_doan(v2, db, orders, lsx_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    lsx = created[0]
    lsx.han_giao_khach = date(2026, 8, 30)
    db.commit()
    q = v2.queue()
    rows = {r["id"]: r for r in q["xep_duoc"] + q["bi_chan"] if r["nguon"] == "lsx"}
    r = rows[lsx.id]
    assert r["han_giao"] == date(2026, 8, 30)
    assert r["so_cong_doan_chua_xep"] == len(lsx.cong_doans) > 0
    for k in ("trang", "moi_trang", "tong", "so_trang", "dem_trang"):
        assert k in q
    assert q["tong"] >= 2 and q["so_trang"] >= 1


# ======================================================================
# Đợt 4 · item 16 — cắt trang Ở MÁY CHỦ (cấm cắt-trang ở JS).
# ======================================================================
def test_queue_phan_trang_may_chu(v2, db, orders, lsx_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    assert len(created) >= 2
    t1 = v2.queue(trang=1, moi_trang=1)
    t2 = v2.queue(trang=2, moi_trang=1)
    n1 = len(t1["xep_duoc"]) + len(t1["bi_chan"])
    n2 = len(t2["xep_duoc"]) + len(t2["bi_chan"])
    assert n1 == 1 and n2 == 1
    assert t1["tong"] == t2["tong"] >= 2
    assert t1["so_trang"] == t1["tong"]                       # mỗi trang 1 dòng ⇒ số trang = tổng
    ids1 = {r["id"] for r in t1["xep_duoc"] + t1["bi_chan"]}
    ids2 = {r["id"] for r in t2["xep_duoc"] + t2["bi_chan"]}
    assert ids1.isdisjoint(ids2)                              # trang khác nhau, không trùng dòng


def test_queue_gap_noi_len_trang_dau(v2, db, orders, lsx_svc, admin, customer):
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    gap = created[0]
    gap.is_rush = True
    db.commit()
    t1 = v2.queue(trang=1, moi_trang=1)                       # is_rush DESC ⇒ lệnh gấp phải ở trang đầu
    dong = (t1["xep_duoc"] + t1["bi_chan"])[0]
    assert dong["id"] == gap.id and dong["is_rush"] is True


def test_queue_facets_va_loc_o_may_chu(v2, db, orders, lsx_svc, admin, customer):
    """Lọc (q/loc) + đếm chip (facets) đều Ở MÁY CHỦ: facets đếm CẢ hàng chờ (bất kể q/loc),
    còn `tong` khớp KẾT QUẢ LỌC — bằng chứng không cắt/đếm-trang ở JS."""
    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    gap, tre = created[0], created[1]
    gap.is_rush = True
    tre.han_hoan_thanh_sx = date(2026, 1, 1)                  # quá hôm nay (2026-08-19) ⇒ trễ
    db.commit()

    base = v2.queue()
    assert base["facets"]["all"] == base["tong"] >= 2         # không lọc ⇒ tong = facets.all
    assert base["facets"]["gap"] >= 1 and base["facets"]["tre"] >= 1

    # loc lọc kết quả (tong đổi) nhưng facets GIỮ NGUYÊN (số gợi ý điều hướng).
    chi_gap = v2.queue(loc="gap")
    ids_gap = {r["id"] for r in chi_gap["xep_duoc"] + chi_gap["bi_chan"] if r["nguon"] == "lsx"}
    assert gap.id in ids_gap and tre.id not in ids_gap
    assert chi_gap["tong"] == chi_gap["facets"]["gap"]
    assert chi_gap["facets"]["all"] == base["facets"]["all"]  # facets không đổi theo loc

    chi_tre = v2.queue(loc="tre")
    ids_tre = {r["id"] for r in chi_tre["xep_duoc"] + chi_tre["bi_chan"] if r["nguon"] == "lsx"}
    assert tre.id in ids_tre and gap.id not in ids_tre

    # q lọc theo MÃ của chính bảng đó — chỉ ra đúng lệnh khớp.
    theo_ma = v2.queue(q=gap.ma)
    ids_ma = {r["id"] for r in theo_ma["xep_duoc"] + theo_ma["bi_chan"] if r["nguon"] == "lsx"}
    assert ids_ma == {gap.id} and theo_ma["tong"] == 1


# ======================================================================
# §7.1 `sai_tien_nhiem` — bước sau KHÔNG được bắt đầu trước khi bước tiền nhiệm KẾT THÚC.
# Kiểm ở mức hàm: chỉ so với tiền nhiệm ĐÃ có giờ; nối đuôi (chạm mép) không tính là sai.
# ======================================================================
def test_sai_tien_nhiem_chan_khi_bat_dau_truoc_tien_nhiem():
    pred = [_utc(2026, 7, 28, 10, 0)]
    vd = C.sai_tien_nhiem(_utc(2026, 7, 28, 9, 0), pred)          # bắt đầu 09:00 < tiền nhiệm xong 10:00
    assert vd is not None and vd["ma"] == "sai_tien_nhiem" and vd["muc"] == MUC_CHAN_DAT_LICH
    assert C.sai_tien_nhiem(_utc(2026, 7, 28, 10, 0), pred) is None       # nối đuôi đúng lúc xong: OK
    assert C.sai_tien_nhiem(_utc(2026, 7, 28, 9, 0), []) is None          # chưa có tiền nhiệm xếp: không chặn
    # Nhiều tiền nhiệm → phải chờ MUỘN NHẤT.
    hai = [_utc(2026, 7, 28, 9, 0), _utc(2026, 7, 28, 11, 0)]
    assert C.sai_tien_nhiem(_utc(2026, 7, 28, 10, 0), hai)["ma"] == "sai_tien_nhiem"
    assert C.sai_tien_nhiem(_utc(2026, 7, 28, 11, 0), hai) is None


# ======================================================================
# §7.2 `thieu_ca_hai_han` / `tre_han_sx` — CHẶN PHÁT HÀNH; §7.3 `sat_han_sx` / `dem_giao_ngan` — CẢNH BÁO.
# ======================================================================
def test_thieu_ca_hai_han_la_chan_phat_hanh():
    vd = C.thieu_ca_hai_han(None, None)
    assert vd["ma"] == "thieu_ca_hai_han" and vd["muc"] == MUC_CHAN_PHAT_HANH
    assert C.thieu_ca_hai_han(date(2026, 8, 1), None) is None
    assert C.thieu_ca_hai_han(None, date(2026, 8, 1)) is None


def test_tre_han_sx_la_chan_phat_hanh():
    han = date(2026, 7, 28)
    vd = C.tre_han_sx(_utc(2026, 7, 29, 9, 0), han)              # xong 29/7 > hạn 28/7
    assert vd["ma"] == "tre_han_sx" and vd["muc"] == MUC_CHAN_PHAT_HANH
    assert C.tre_han_sx(_utc(2026, 7, 28, 23, 0), han) is None    # xong trong ngày hạn: OK
    assert C.tre_han_sx(None, han) is None
    assert C.tre_han_sx(_utc(2026, 7, 29, 9, 0), None) is None    # chưa có hạn: để `thieu_ca_hai_han` lo


def test_sat_han_sx_va_dem_giao_ngan_la_canh_bao():
    han = date(2026, 7, 30)
    vd = C.sat_han_sx(_utc(2026, 7, 29, 9, 0), han)             # còn 1 ngày đệm ≤ 2
    assert vd["ma"] == "sat_han_sx" and vd["muc"] == MUC_CANH_BAO
    assert C.sat_han_sx(_utc(2026, 7, 20, 9, 0), han) is None     # còn nhiều đệm
    assert C.sat_han_sx(_utc(2026, 8, 1, 9, 0), han) is None      # đã trễ → `tre_han_sx` lo, không cảnh báo trùng

    dg = C.dem_giao_ngan(date(2026, 7, 28), date(2026, 7, 28))  # đệm 0 ngày giữa xong SX và giao
    assert dg["ma"] == "dem_giao_ngan" and dg["muc"] == MUC_CANH_BAO
    assert C.dem_giao_ngan(date(2026, 7, 28), date(2026, 7, 31)) is None   # đệm 3 ngày
    assert C.dem_giao_ngan(None, date(2026, 7, 31)) is None


# ======================================================================
# §5 + §7.1 — tiền nhiệm ĐI QUA LUỒNG THẬT: xếp bước sau chạy trước bước trước ⇒ chặn `luu`.
# ======================================================================
def test_sai_tien_nhiem_chan_luu_qua_luong_that(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)                               # In = 90' chiếm máy (60' chạy + 30' makeready)
    xa = LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                     may_id=inb.may_id, so_luong_vao=5000, nang_suat=6000, don_vi_nang_suat="to_gio",
                     don_vi_vao="to", don_vi_ra="to")
    db.add(xa); db.flush()
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=inb.id, buoc_sau_id=xa.id))
    db.commit()
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_dong = next(d for d in dongs if d.lsx_cong_doan_id == inb.id)
    xa_dong = next(d for d in dongs if d.lsx_cong_doan_id == xa.id)
    # Xếp In 28/7 08:00 → xong 09:30.
    v2.luu(dong_id=in_dong.id, patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 28, 8, 0)},
           expected_updated_at=in_dong.updated_at, actor=admin)
    # Xả tờ bắt đầu 08:30 (trước khi In xong 09:30) ⇒ chặn sai_tien_nhiem.
    xa_dong = v2.core._get_dong(xa_dong.id)
    with pytest.raises(XepLich2Blocked) as e:
        v2.luu(dong_id=xa_dong.id, patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 28, 8, 30)},
               expected_updated_at=xa_dong.updated_at, actor=admin)
    assert "sai_tien_nhiem" in {i["ma"] for i in e.value.van_de}
    # Xả tờ 10:00 (sau khi In xong) ⇒ hết vướng tiền nhiệm.
    xa_dong = v2.core._get_dong(xa_dong.id)
    pv = v2.xem_truoc(dong_id=xa_dong.id,
                      patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 28, 10, 0)})
    assert "sai_tien_nhiem" not in _ma(pv["van_de"])


# ======================================================================
# §7.2 — hạn ĐI QUA LUỒNG THẬT: thiếu cả hai hạn ⇒ chặn phát hành; xong sau hạn ⇒ `tre_han_sx`.
# ======================================================================
def test_thieu_ca_hai_han_chan_phat_hanh_qua_luong(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    lsx.han_hoan_thanh_sx, lsx.han_giao_khach = None, None
    db.commit()
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    assert "thieu_ca_hai_han" in _ma(v2.kiem_phat_hanh(nguon="lsx", id=lsx.id))
    with pytest.raises(XepLich2Blocked):                        # phát hành cũng chặn
        v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)


def test_phat_hanh_chan_khi_con_buoc_chua_xep(v2, db, orders, lsx_svc, admin, customer):
    # Có hạn (thieu_ca_hai_han không nổ) nhưng lệnh còn NHÁP, bước chưa xếp giờ: gọi thẳng API
    # phát hành v2 vẫn phải CHẶN — không được lọt xuống màn cũ mà phát hành lệnh còn bước trống giờ.
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    lsx.han_hoan_thanh_sx = date(2026, 12, 31)
    db.commit()
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)            # nháp: bước CHƯA xếp giờ
    codes = _ma(v2.kiem_phat_hanh(nguon="lsx", id=lsx.id))
    assert "con_buoc_chua_xep" in codes and "thieu_ca_hai_han" not in codes
    with pytest.raises(XepLich2Blocked) as e:
        v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)
    assert "con_buoc_chua_xep" in _ma(e.value.van_de)


def test_tre_han_sx_hien_o_kiem_phat_hanh(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    lsx.han_hoan_thanh_sx = date(2026, 7, 27)                    # hạn 27/7
    db.commit()
    inb = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    in_dong = next(d for d in XepLichRepository(db).by_lsx(lsx.id) if d.lsx_cong_doan_id == inb.id)
    v2.luu(dong_id=in_dong.id, patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 28, 8, 0)},
           expected_updated_at=in_dong.updated_at, actor=admin)   # xong 28/7 > hạn 27/7
    vd = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    assert "tre_han_sx" in _ma(vd)
    tre = next(i for i in vd if i["ma"] == "tre_han_sx")
    assert tre["muc"] == MUC_CHAN_PHAT_HANH
    # §1.3 — vấn đề mang NGUỒN phân loại + nhãn ĐỐI TƯỢNG đã điền sẵn để UI khỏi tự đoán.
    assert tre["nguon"] == "han"
    assert tre["doi_tuong"] == "Hạn lệnh"


# ======================================================================
# §7.2 (B3) — TRỄ HẠN SX siết CỨNG lúc phát hành, NHƯNG duyệt ngoại lệ (chỉ mã này) mở lại cửa.
# Tái dùng kho ngoại lệ `xep_lich_van_de` (chung màn cũ), key riêng `tre_han_sx:{nguon}:{id}`.
# Ngoại lệ NEO THEO MỐC ĐÃ DUYỆT: `exception_expires_at` giữ mốc hoàn thành lúc duyệt — dời lịch
# xong muộn hơn mốc thì tự mất hiệu lực, phải duyệt lại (§7.2, lựa chọn của chủ dự án).
# ======================================================================
def _lsx_tre_han_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """LSX 1 bước IN, đã xếp giờ ở TƯƠNG LAI nhưng xong SAU hạn SX ⇒ chỉ còn `tre_han_sx` chặn.

    Dùng ngày tương-đối-với-hiện-tại (không hardcode quá khứ): màn cũ tính `som_nhat` ≈ bây giờ, xếp
    ở quá khứ sẽ bị nó gắn `sai_tien_nhiem` (sai thứ tự routing) làm nhiễu — nên xếp ở tương lai để
    gate màn cũ trong sạch, đúng kịch bản trễ-hạn-nhưng-sạch mà chỉ ngoại lệ mới mở được cửa."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    hom_nay = datetime.now(timezone.utc).date()
    ngay_chay = hom_nay + timedelta(days=14)                        # xếp tuần sau nữa (> som_nhat)
    lsx.han_hoan_thanh_sx = hom_nay + timedelta(days=10)            # hạn TRƯỚC ngày chạy ⇒ chắc trễ
    lsx.han_giao_khach = hom_nay + timedelta(days=12)
    db.commit()
    inb = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    in_dong = next(d for d in XepLichRepository(db).by_lsx(lsx.id) if d.lsx_cong_doan_id == inb.id)
    v2.luu(dong_id=in_dong.id,
           patch={"may_id": inb.may_id,
                  "start_at": _utc(ngay_chay.year, ngay_chay.month, ngay_chay.day, 8, 0)},
           expected_updated_at=in_dong.updated_at, actor=admin)     # xong cùng ngày > hạn SX
    return lsx


def test_tre_han_sx_siet_cung_phat_hanh(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    lsx = _lsx_tre_han_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)
    truoc = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    assert any(i["ma"] == "tre_han_sx" and i["muc"] == MUC_CHAN_PHAT_HANH for i in truoc)
    assert "con_buoc_chua_xep" not in _ma(truoc)                    # đúng 1 bước, đã xếp
    with pytest.raises(XepLich2Blocked) as e:
        v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)
    assert "tre_han_sx" in _ma(e.value.van_de)


def test_duyet_ngoai_le_mo_cua_phat_hanh(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    lsx = _lsx_tre_han_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)
    _kcs_hoa(db, lsx.id)
    kq = v2.duyet_ngoai_le(nguon="lsx", id=lsx.id, ly_do="khách đồng ý nhận trễ một ngày", actor=admin)
    assert kq["moc_da_duyet"] is not None                          # mốc đã duyệt được ghi lại
    sau = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    tre = [i for i in sau if i["ma"] == "tre_han_sx"]
    assert tre and tre[0]["muc"] == MUC_CANH_BAO and tre[0].get("da_ngoai_le") is True
    lsx_ph = v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)      # nay QUA cửa
    assert lsx_ph.trang_thai == TT_DA_PHAT_HANH


def _dong_da_xep(db, lsx_id):
    return next(d for d in XepLichRepository(db).by_lsx(lsx_id) if d.start_at is not None)


def test_ngoai_le_het_hieu_luc_khi_doi_muon_hon(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """NEO THEO MỐC: duyệt xong mà DỜI lịch làm xong MUỘN HƠN mốc đã duyệt ⇒ ngoại lệ tự mất hiệu
    lực, chặn phát hành lại — một chữ ký 'tha trễ 1 ngày' KHÔNG lỡ tha luôn 'trễ 1 tháng'."""
    lsx = _lsx_tre_han_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)   # xếp ~day+14
    v2.duyet_ngoai_le(nguon="lsx", id=lsx.id, ly_do="khách đồng ý mốc hiện tại", actor=admin)
    dong = _dong_da_xep(db, lsx.id)
    xa = datetime.now(timezone.utc).date() + timedelta(days=28)     # muộn hơn mốc rõ rệt
    v2.luu(dong_id=dong.id, patch={"start_at": _utc(xa.year, xa.month, xa.day, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)
    sau = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    tre = [i for i in sau if i["ma"] == "tre_han_sx"]
    assert tre and tre[0]["muc"] == MUC_CHAN_PHAT_HANH              # vượt mốc → chặn lại
    with pytest.raises(XepLich2Blocked):
        v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)


def test_ngoai_le_giu_hieu_luc_khi_doi_som_hon_moc(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """NEO THEO MỐC: dời lịch làm xong SỚM HƠN mốc (dù vẫn trễ hạn SX) KHÔNG bắt duyệt lại — ngoại
    lệ còn hiệu lực vì không vượt mốc đã duyệt."""
    lsx = _lsx_tre_han_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)   # xếp ~day+14
    _kcs_hoa(db, lsx.id)
    v2.duyet_ngoai_le(nguon="lsx", id=lsx.id, ly_do="khách đồng ý mốc hiện tại", actor=admin)
    dong = _dong_da_xep(db, lsx.id)
    som = datetime.now(timezone.utc).date() + timedelta(days=12)    # sớm hơn mốc, vẫn > hạn SX (day+10)
    v2.luu(dong_id=dong.id, patch={"start_at": _utc(som.year, som.month, som.day, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)
    sau = v2.kiem_phat_hanh(nguon="lsx", id=lsx.id)
    tre = [i for i in sau if i["ma"] == "tre_han_sx"]
    assert tre and tre[0]["muc"] == MUC_CANH_BAO and tre[0].get("da_ngoai_le") is True
    assert v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin).trang_thai == TT_DA_PHAT_HANH


def test_duyet_ngoai_le_tu_choi_khi_khong_tre(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    lsx.han_hoan_thanh_sx = date(2026, 12, 31)                       # hạn xa → không trễ
    db.commit()
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    with pytest.raises(XepLich2Error):                              # lý do quá ngắn
        v2.duyet_ngoai_le(nguon="lsx", id=lsx.id, ly_do="x", actor=admin)
    with pytest.raises(XepLich2Error):                              # không có trễ hạn để duyệt
        v2.duyet_ngoai_le(nguon="lsx", id=lsx.id, ly_do="không có gì để duyệt", actor=admin)


# ======================================================================
# MỘT CỬA PHÁT HÀNH (25/08/2026) — v2 chỉ nghe `kiem_phat_hanh`, gác đời cũ không xen vào.
#
# Trước đây có HAI người gác: dải chân UI đọc `kiem_phat_hanh` báo "đủ điều kiện phát hành", còn
# nút Phát hành lại đi qua 12 detector của màn Xếp lịch 1 và trả "còn 2 xung đột CHẶN chưa xử
# lý/ngoại lệ" (LSX26-0029) — người dùng không có cách nào biết phải gỡ cái gì.
# ======================================================================
def _lsx_hai_buoc_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Lệnh 2 bước (In → Xả tờ) đã tự-xếp xong, hạn xa để KHÔNG lẫn `tre_han_sx` vào phép thử.

    `_chuoi_in_xa` khai ở mục Tự xếp phía dưới — Python tra tên lúc CHẠY nên gọi ngược lên được."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    hom_nay = datetime.now(timezone.utc).date()
    lsx.han_hoan_thanh_sx = hom_nay + timedelta(days=120)
    lsx.han_giao_khach = hom_nay + timedelta(days=130)
    db.commit()
    inb, xa = _chuoi_in_xa(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    return lsx, inb, xa


def test_phat_hanh_v2_khong_goi_gac_doi_cu(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Đường phát hành v2 KHÔNG được chạm `_build()` của service màn cũ — một cửa là một cửa."""
    from app.services.xep_lich_van_de_service import XepLichVanDeService
    lsx, _, _ = _lsx_hai_buoc_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)
    _kcs_hoa(db, lsx.id)
    assert v2._chan_phat_hanh(nguon="lsx", id=lsx.id) == [], "lệnh phải sạch trước khi thử"

    def _cam(self):
        raise AssertionError("gác đời cũ KHÔNG được chạy trên đường phát hành v2")

    monkeypatch.setattr(XepLichVanDeService, "_build", _cam)
    assert v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin).trang_thai == TT_DA_PHAT_HANH


def test_man_cu_van_giu_gac_cua_no(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Bỏ gác chỉ áp cho đường v2: phát hành TỪ MÀN CŨ vẫn qua `_build()` như trước."""
    from app.services.xep_lich_van_de_service import XepLichVanDeService
    lsx, _, _ = _lsx_hai_buoc_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)
    _kcs_hoa(db, lsx.id)
    da_goi = []
    monkeypatch.setattr(XepLichVanDeService, "_build", lambda self: da_goi.append(1) or [])
    XepLichVanDeService(db, AuditLogRepository(db)).phat_hanh_lsx(lsx_id=lsx.id, actor=admin)
    assert da_goi, "màn cũ phải còn gác xung đột đời cũ"


def test_chan_dat_lich_con_vuong_thi_chan_phat_hanh(v2, db, orders, lsx_svc, admin, customer,
                                                    monkeypatch):
    """Luật CHẶN ĐẶT LỊCH còn vướng ⇒ chặn luôn phát hành (trước 25/08 chỉ ba mã cứng mới chặn).

    Kịch bản thật: xếp xong cả chuỗi rồi ĐẨY bước IN sang hôm sau — `luu` chỉ soi chính dòng bị sửa
    nên bước XẢ TỜ ở lại phía trước, hoá ra chạy TRƯỚC bước in (`sai_tien_nhiem`)."""
    lsx, inb, _ = _lsx_hai_buoc_da_xep(v2, db, orders, lsx_svc, admin, customer, monkeypatch)
    d_in = next(d for d in XepLichRepository(db).by_lsx(lsx.id) if d.lsx_cong_doan_id == inb.id)
    s = d_in.start_at
    moi = _utc(s.year, s.month, s.day, s.hour, s.minute) + timedelta(days=1)
    v2.luu(dong_id=d_in.id, patch={"start_at": moi},
           expected_updated_at=d_in.updated_at, actor=admin)

    sai = [i for i in v2.kiem_phat_hanh(nguon="lsx", id=lsx.id) if i["ma"] == "sai_tien_nhiem"]
    assert sai and sai[0]["muc"] == MUC_CHAN_DAT_LICH
    with pytest.raises(XepLich2Blocked) as e:
        v2.phat_hanh(nguon="lsx", id=lsx.id, actor=admin)
    assert "sai_tien_nhiem" in _ma(e.value.van_de)


# ======================================================================
# §12.8 — không còn kết luận nào dựa trên khổ / số màu / định lượng (soi MÃ NGUỒN).
# ======================================================================
def test_khong_con_luat_theo_kho_mau_gsm():
    pkg = Path(__file__).resolve().parents[1] / "app" / "services" / "xep_lich_2"
    cam = re.compile(r"kiem_kha_nang|_may_fit|kho_max|so_mau|gsm|dinh_luong")
    dinh = []
    for f in pkg.glob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]                # bỏ chú thích: nói VỀ luật cũ thì được
            if cam.search(code):
                dinh.append(f"{f.name}:{i}: {line.strip()}")
    assert not dinh, "v2 không được kết luận theo khổ/màu/gsm:\n" + "\n".join(dinh)


# ======================================================================
# §12.6 (WIRING) — thời lượng min/max chảy tới xem-trước; ngày vật tư ĐỌC TỪ GIỮ CHỖ.
# ======================================================================
def _dong_in(db, lsx_id) -> LsxCongDoan:
    return next(d for d in XepLichRepository(db).by_lsx(lsx_id)
                if d.lsx_cong_doan_id is not None)


def _giu_dang_ve(db, lsx_id: int, ngay_ve: date) -> None:
    """Gắn MỘT dòng giữ chỗ nguồn ĐANG VỀ (mượn đúng mặt hàng đã giữ trong kho) với ngày hứa."""
    kho = GiuChoRepository(db).cua_chu_the(lsx_id=lsx_id, bai_ghep_id=None)
    assert kho, "cần có sẵn giữ chỗ kho để mượn mặt hàng"
    h0 = kho[0]
    db.add(VatTuGiuCho(hang_loai=h0.hang_loai, hang_id=h0.hang_id, lsx_id=lsx_id,
                       so_luong=1.0, nguon=NGUON_DANG_VE, ngay_ve=ngay_ve))
    db.commit()


def test_xem_truoc_tra_chiem_may_phut_min_max(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    pv = v2.xem_truoc(dong_id=dong.id,
                      patch={"may_id": step.may_id, "start_at": _utc(2026, 7, 27, 8, 0)})
    assert "chiem_may_phut_min" in pv and "chiem_may_phut_max" in pv
    assert pv["chiem_may_phut_min"] <= pv["chiem_may_phut"] <= pv["chiem_may_phut_max"]


# ======================================================================
# item 14 — xem-trước kèm ẢNH HƯỞNG HẠ NGUỒN: bước SAU (thứ tự lớn hơn) đã có giờ mà bắt đầu
# TRƯỚC khi bước này xong ⇒ hiện ở `cong_doan_anh_huong`; kèm `han_moi` = giờ xong muộn nhất lệnh.
# Xem-trước THUẦN — KHÔNG tự dời bước nào (đúng tinh thần v2 xếp tay).
# ======================================================================
def test_xem_truoc_kem_anh_huong_ha_nguon(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)                               # In = 90' chiếm máy → 08:00 xong 09:30
    xa = LsxCongDoan(lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                     may_id=inb.may_id, so_luong_vao=5000, nang_suat=6000, don_vi_nang_suat="to_gio",
                     don_vi_vao="to", don_vi_ra="to")
    db.add(xa); db.flush()
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=inb.id, buoc_sau_id=xa.id))
    db.commit()
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dongs = XepLichRepository(db).by_lsx(lsx.id)
    in_dong = next(d for d in dongs if d.lsx_cong_doan_id == inb.id)
    xa_dong = next(d for d in dongs if d.lsx_cong_doan_id == xa.id)
    # Xếp bước SAU (xả, thứ tự 1) bắt đầu 08:30 — trước khi bước IN xem-trước (08:00→09:30) xong.
    v2.luu(dong_id=xa_dong.id, patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 30)},
           expected_updated_at=xa_dong.updated_at, actor=admin)

    pv = v2.xem_truoc(dong_id=in_dong.id,
                      patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)})
    ah = pv["cong_doan_anh_huong"]
    assert any(a["thu_tu"] == 1 and a["dong_id"] == xa_dong.id for a in ah), \
        "bước xả (sau) bị lấn thứ tự phải hiện ở công đoạn ảnh hưởng"
    assert pv["han_moi"] is not None, "phải suy ra hạn mới của lệnh khi đặt như xem-trước"


def test_ngay_vat_tu_chua_giu_dang_ve_thi_khong_chan(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    pv = v2.xem_truoc(dong_id=dong.id,
                      patch={"may_id": step.may_id, "start_at": _utc(2026, 8, 19, 8, 0)})
    assert "truoc_ngay_vat_tu" not in _ma(pv["van_de"])          # chưa có giữ chỗ đang về ⇒ không chặn


def test_ngay_vat_tu_doc_tu_giu_cho_dang_ve(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    _giu_dang_ve(db, lsx.id, date(2026, 9, 1))                   # vật tư hứa về 01/9
    dong = _dong_in(db, lsx.id)
    pv = v2.xem_truoc(dong_id=dong.id,
                      patch={"may_id": step.may_id, "start_at": _utc(2026, 8, 19, 8, 0)})
    assert "truoc_ngay_vat_tu" in _ma(pv["van_de"])              # 19/8 trước ngày hứa 01/9 ⇒ chặn


# ======================================================================
# §7.2 + §12.6 — soi vật tư TÁCH hai rổ: chặn-phát-hành vs cảnh-báo (release.soat_vat_tu).
# ======================================================================
def test_vat_tu_dang_ve_la_canh_bao_khong_chan(db, orders, lsx_svc, admin, customer):
    from app.services.xep_lich_2 import release
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _giu_dang_ve(db, lsx.id, date(2026, 9, 1))                   # đã đủ + có phần đang về
    sv = release.soat_vat_tu(db, lsx_id=lsx.id)
    assert "vat_tu_dang_ve" in {i["ma"] for i in sv["canh_bao"]}
    assert all(i["muc"] == MUC_CANH_BAO for i in sv["canh_bao"] if i["ma"] == "vat_tu_dang_ve")
    assert "vat_tu_dang_ve" not in {i["ma"] for i in sv["chan"]}         # KHÔNG lọt vào rổ chặn
    assert "vat_tu_chua_du" not in {i["ma"] for i in sv["chan"]}         # vẫn đủ


def test_van_de_vat_tu_chi_tra_ro_chan(db, orders, lsx_svc, admin, customer):
    """Màn CŨ chỉ hỏi rổ chặn — cảnh báo đang-về không được lọt sang đường phát hành màn cũ."""
    from app.services.xep_lich_2 import release
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _giu_dang_ve(db, lsx.id, date(2026, 9, 1))
    assert release.van_de_vat_tu(db, lsx_id=lsx.id) == []        # đủ giấy ⇒ màn cũ phát hành được


def test_vat_tu_dang_mua_khong_ngay_chan_rieng(v2, db, orders, lsx_svc, admin, customer):
    from app.services.xep_lich_2 import release
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    _nha_cho(db, [lsx.id])                                       # nhả giữ chỗ ⇒ thiếu
    thieu = release.trang_thai_giu_cho(db, lsx_id=lsx.id)["thieu"]
    assert thieu, "sau khi nhả phải có hàng thiếu"
    for (loai, hid) in thieu.keys():                             # đặt mua NHƯNG chưa hẹn ngày
        p = PurchaseRequest(code=f"PMH-KO-NGAY-{loai}-{hid}", status=PR_PURCHASED,
                            expected_receipt_date=None)
        db.add(p); db.flush()
        db.add(PurchaseRequestLine(purchase_request_id=p.id, item_name="Giấy mua",
                                   hang_loai=loai, hang_id=hid, unit="kg",
                                   quantity=100000, expected_unit_price=1))
    db.commit()
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    codes = _ma(v2.kiem_phat_hanh(nguon="lsx", id=lsx.id))
    assert "vat_tu_chua_co_ngay" in codes                        # tách riêng "đã mua, chưa có ngày"
    assert "vat_tu_chua_du" not in codes                         # mọi món thiếu đều đã có phiếu mua


# ======================================================================
# §7.2 — đổi tên `chua_xep_gio` → `con_buoc_chua_xep` (cùng mức chặn phát hành).
# ======================================================================
def test_con_buoc_chua_xep_thay_ten_cu(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)            # nháp: chưa gán giờ
    codes = _ma(v2.kiem_phat_hanh(nguon="lsx", id=lsx.id))
    assert "con_buoc_chua_xep" in codes
    assert "chua_xep_gio" not in codes


# ======================================================================
# §12.11 — mọi mutation đẩy SSE (soi router: mỗi handler POST/PUT/DELETE có `hub.broadcast`).
# ======================================================================
def test_moi_route_ghi_deu_day_sse():
    src = Path(__file__).resolve().parents[1] / "app" / "routers" / "xep_lich_2.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    thieu = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods = {
            d.func.attr
            for d in node.decorator_list
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
        }
        if not (methods & {"post", "put", "delete", "patch"}):
            continue
        body = ast.dump(node)
        if "broadcast" not in body:
            thieu.append(node.name)
    assert not thieu, f"route ghi thiếu hub.broadcast: {thieu}"


# ======================================================================
# PHASE 3 (B9) — LỚP PHỦ GANTT ở MỨC HÀM: gộp thanh đã xếp thành số theo NGÀY.
# Cắt theo ranh giới ngày (chạy liên tục qua đêm), nối đuôi không cộng dồn.
# ======================================================================
def test_overlay_tai_may_cat_theo_ngay():
    from app.services.xep_lich_2 import overlay
    pl = [
        (7, _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 10, 0)),      # 120' trong ngày 27
        (7, _utc(2026, 7, 27, 23, 0), _utc(2026, 7, 28, 1, 0)),      # qua đêm: 60' ngày 27 + 60' ngày 28
        (9, _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 8, 30)),      # máy khác, 30' ngày 27
    ]
    out = {(x["may_id"], x["ngay"]): x["phut_ban"]
           for x in overlay.tai_may(pl, date(2026, 7, 27), date(2026, 7, 28))}
    assert out[(7, date(2026, 7, 27))] == 180        # 120 + 60 (phần qua đêm rơi vào ngày 27)
    assert out[(7, date(2026, 7, 28))] == 60         # phần còn lại rơi sang ngày 28
    assert out[(9, date(2026, 7, 27))] == 30
    assert (9, date(2026, 7, 28)) not in out         # máy 9 không chạm ngày 28


def test_overlay_dinh_quan_so_theo_dinh_chong_gio():
    from app.services.xep_lich_2 import overlay
    pl = [
        (3, _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 10, 0), 2),
        (3, _utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 11, 0), 2),  # chồng 09–10 → đỉnh 4
        (3, _utc(2026, 7, 28, 8, 0), _utc(2026, 7, 28, 9, 0), 1),   # ngày khác
    ]
    out = overlay.dinh_quan_so(pl, date(2026, 7, 27), date(2026, 7, 28))
    assert out[(3, date(2026, 7, 27))] == 4
    assert out[(3, date(2026, 7, 28))] == 1
    # Nối đuôi (chạm mép) KHÔNG cộng dồn — cùng quy ước với constraint.vuot_quan_so_to.
    tuan_tu = [
        (5, _utc(2026, 7, 27, 8, 0), _utc(2026, 7, 27, 9, 0), 2),
        (5, _utc(2026, 7, 27, 9, 0), _utc(2026, 7, 27, 10, 0), 2),
    ]
    assert overlay.dinh_quan_so(tuan_tu, date(2026, 7, 27), date(2026, 7, 27))[(5, date(2026, 7, 27))] == 2


# ======================================================================
# PHASE 3 (B9) — MỘT CÚ GỌI lấy hết bối cảnh: workspace trả ca · ngày lễ · vùng khoá máy ·
# lớp phủ tải máy + đỉnh quân số, và mỗi thanh đã xếp có "râu" bóc tách CANH MÁY + CHẠY.
# ======================================================================
def test_workspace_mot_cu_goi_du_boi_canh_va_boc_tach(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)                              # In = 90' chiếm máy (60' chạy + 30' canh máy)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    v2.luu(dong_id=dong.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)     # xong 09:30

    ws = v2.workspace(tu=date(2026, 7, 27), den=date(2026, 7, 27))
    for k in ("ca", "ngay_le", "khoa_may", "tai_may", "tai_to", "dong"):
        assert k in ws, f"workspace thiếu khối {k} — màn phải gọi một cú là đủ"

    # "Râu" trên thanh đã xếp: canh máy 30' + chạy 60' = chiếm máy 90'.
    d = next(x for x in ws["dong"] if x["id"] == dong.id)
    bt = d["boc_tach"]
    assert bt is not None
    assert bt["canh_may_phut"] == 30 and bt["chay_phut"] == 60 and bt["khac_phut"] == 0
    assert bt["chiem_may_phut"] == 90
    assert bt["canh_may_phut"] + bt["chay_phut"] + bt["khac_phut"] == bt["chiem_may_phut"]

    # Lớp phủ tải máy: máy này gánh đúng 90' trong ngày 27/7.
    tm = {(x["may_id"], x["ngay"]): x["phut_ban"] for x in ws["tai_may"]}
    assert tm[(inb.may_id, date(2026, 7, 27))] == 90


def test_boc_tach_co_thoi_gian_khac_van_khep_bang_thanh(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Bước có 'thời gian khác' (`phat_sinh_phut`>0): "râu" phải phơi đủ ba cấu phần và CỘNG LẠI
    đúng bằng giờ chiếm máy — không được nuốt mất phần khác như bản đầu chỉ có canh máy + chạy."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)          # 30' canh + 60' chạy
    inb.phat_sinh_phut = 15                  # + 15' thời gian khác ⇒ chiếm máy = 105'
    db.commit()
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    v2.luu(dong_id=dong.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)

    ws = v2.workspace(tu=date(2026, 7, 27), den=date(2026, 7, 27))
    bt = next(x for x in ws["dong"] if x["id"] == dong.id)["boc_tach"]
    assert bt["chiem_may_phut"] == 105
    assert bt["canh_may_phut"] == 30 and bt["khac_phut"] == 15 and bt["chay_phut"] == 60
    assert bt["canh_may_phut"] + bt["chay_phut"] + bt["khac_phut"] == bt["chiem_may_phut"]


def test_workspace_nhap_chua_gio_khong_co_boc_tach(v2, db, orders, lsx_svc, admin, customer):
    """Nháp chưa đặt giờ nằm ở cụm 'Chưa đặt giờ' — không có thanh nên `boc_tach` = None."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    ws = v2.workspace(tu=date(2026, 7, 20), den=date(2026, 8, 2))
    nhap = [d for d in ws["dong"] if d["start_at"] is None]
    assert nhap and all(d["boc_tach"] is None for d in nhap)


def test_workspace_nhan_dan_xuat_ma_ten_ca_hai_nguon(
    v2, db, orders, lsx_svc, bg_svc, admin, customer,
):
    """Mỗi dòng mang SẴN nhãn dẫn xuất để thanh Gantt đọc được mà KHÔNG phải join lại ở FE:
    - nguồn LSX      → `lsx_ma` + tên sản phẩm (lệnh); `bai_ghep_ma` rỗng;
    - nguồn bài ghép → `bai_ghep_ma` + tên bài; `lsx_ma` rỗng;
    - cả hai         → tên công đoạn của bước (`cong_doan_ten`) + thứ tự bước (`buoc_thu_tu`).

    Nạp theo LÔ ở `workspace` nên một cú gọi phải đủ nhãn cho CẢ dòng in chung (bài ghép) lẫn dòng
    riêng còn lại của lệnh (LSX)."""
    from app.models.bai_ghep_cong_doan import BaiGhepCongDoan

    created = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Mỗi lệnh thêm bước "Xả tờ" (sau in) → in CHUNG ở bài, mỗi lệnh vẫn còn MỘT bước riêng (nguồn LSX).
    for lsx in created:
        db.add(LsxCongDoan(
            lsx_id=lsx.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
            may_id=_in_step(db, lsx.id).may_id, so_luong_vao=5000, nang_suat=3000,
            don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
        ))
    db.commit()
    _nha_cho(db, [l.id for l in created])
    bg = bg_svc.tao(lsx_ids=[l.id for l in created], actor=admin)
    bg = _gop_in_va_san_sang(db, bg_svc, bg, admin)
    v2.tao_nhap(nguon="in_ghep", id=bg.id, actor=admin)

    repo = XepLichRepository(db)
    gang = repo.by_bai_ghep(bg.id)[0]            # dòng in CHUNG — nguồn bài ghép
    member = repo.by_lsx(created[0].id)[0]       # dòng "Xả tờ" — nguồn LSX
    gang_cd_ten = db.get(BaiGhepCongDoan, gang.bai_ghep_cong_doan_id).ten
    member_cd_ten = db.get(LsxCongDoan, member.lsx_cong_doan_id).ten

    ws = v2.workspace(tu=date(2026, 7, 27), den=date(2026, 7, 27))
    by_id = {d["id"]: d for d in ws["dong"]}
    KHOA = {"lsx_ma", "bai_ghep_ma", "ten_san_pham", "cong_doan_ten", "buoc_thu_tu"}

    dg = by_id[gang.id]
    assert KHOA <= set(dg), "dòng bài ghép thiếu nhãn dẫn xuất"
    assert dg["bai_ghep_ma"] == bg.ma and dg["lsx_ma"] is None
    assert dg["ten_san_pham"] == bg.ten
    assert dg["cong_doan_ten"] == gang_cd_ten
    assert dg["buoc_thu_tu"] == gang.source_thu_tu

    dl = by_id[member.id]
    assert KHOA <= set(dl), "dòng LSX thiếu nhãn dẫn xuất"
    assert dl["lsx_ma"] == created[0].ma and dl["bai_ghep_ma"] is None
    assert dl["ten_san_pham"] == created[0].ten
    assert dl["cong_doan_ten"] == member_cd_ten == "Xả tờ"
    assert dl["buoc_thu_tu"] == member.source_thu_tu


# ======================================================================
# PHASE 3 (B9) — XOÁ NHÁP: bỏ một lệnh ra khỏi kế hoạch nháp (tái dùng go_lsx engine cũ).
# ======================================================================
def test_xoa_nhap_go_lenh_khoi_ke_hoach(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    assert XepLichRepository(db).by_lsx(lsx.id), "đã có dòng nháp"

    v2.xoa_nhap(nguon="lsx", id=lsx.id, actor=admin)
    assert XepLichRepository(db).by_lsx(lsx.id) == [], "xoá nháp → không còn dòng"
    assert lsx.trang_thai == TT_SAN_SANG, "lệnh về lại SẴN SÀNG, đưa vào kế hoạch lại được"


def test_xoa_nhap_chan_khi_da_phat_hanh(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    lsx.trang_thai = TT_DA_PHAT_HANH                            # giả lập đã phát hành
    db.commit()
    with pytest.raises(XepLichConflict):                        # engine cũ chặn, không gỡ nửa vời (router map 409)
        v2.xoa_nhap(nguon="lsx", id=lsx.id, actor=admin)


# ======================================================================
# PHASE 3 (B8) — GỢI Ý ≤3 KHE TRỐNG: hệ tự chấm chỗ hợp lý sớm nhất, người bấm một phát là xong.
# ======================================================================
def test_goi_y_khe_ne_khoang_da_chiem_may(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Khe đề xuất phải NÉ đúng đoạn máy đã bị chiếm, và bám sát đuôi nó.

    Giờ dùng ở đây là TƯƠNG ĐỐI (lấy từ chính khe hệ chấm ra) chứ không neo cứng một ngày
    lịch: từ khi `goi_y_khe` dùng sàn thật (`max(bây giờ · bàn giao · tiền nhiệm · ngày vật tư)`),
    mọi mốc viết chết trong quá khứ sẽ hết hạn theo thời gian thực — test sẽ tự mục nát.

    Nhưng "tương đối" thôi CHƯA đủ: phải khai ca thật nữa. DB test không có ca nào thì engine rơi
    về một ca mặc định 08:00–16:00, mà cửa chặn `ngoai_ca` (§7.1) chỉ soi GIỜ BẮT ĐẦU. Chạy trong
    khung 14:30–16:00 giờ xưởng thì `som` còn trong ca nhưng cái đuôi `som + 90'` đã rơi ra ngoài,
    hệ đẩy khe sang 08:00 hôm sau và bài đỏ (CI 03/09/2026: chờ 16:10, nhận 04/09 08:00). Ngoài
    khung đó `som` tự trượt sang 08:00 hôm sau nên bài lại xanh — đỏ ngắt quãng theo GIỜ CHẠY,
    không theo lỗi. Bốn ca xưởng phủ trọn 24h nên biến duy nhất còn lại đúng là thứ đang đo.
    """
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    _khai_ca_xuong(db)                                          # phủ 24h ⇒ `ngoai_ca` không xen vào
    l0, l1 = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    in0 = _in_theo_may(db, l0.id)
    in1 = _in_theo_may(db, l1.id)
    in1.may_id = in0.may_id                                     # ép HAI lệnh cùng một máy
    db.commit()
    v2.tao_nhap(nguon="lsx", id=l0.id, actor=admin)
    v2.tao_nhap(nguon="lsx", id=l1.id, actor=admin)

    hom_nay = datetime.now(timezone.utc).date()
    cua_so = {"tu": hom_nay, "den": hom_nay + timedelta(days=3)}

    d1 = _dong_in(db, l1.id)
    truoc = v2.goi_y_khe(dong_id=d1.id, **cua_so)["khe"]
    assert truoc, "máy còn trống thì phải chấm được khe"
    som = truoc[0]["start_at"]
    chiem = truoc[0]["chiem_may_phut"]

    # Lệnh 0 chiếm đúng cái khe sớm nhất đó ⇒ lệnh 1 phải bị đẩy ra sau đuôi.
    d0 = _dong_in(db, l0.id)
    v2.luu(dong_id=d0.id,
           patch={"may_id": in0.may_id, "start_at": som.replace(tzinfo=timezone.utc)},
           expected_updated_at=d0.updated_at, actor=admin)

    res = v2.goi_y_khe(dong_id=d1.id, **cua_so)
    khe = res["khe"]
    assert khe, "phải chấm được ít nhất một khe"
    assert len(khe) <= 3
    assert khe[0]["start_at"] == som + timedelta(minutes=chiem), "khe đầu bám đuôi việc đang chạy"
    assert khe[0]["finish_at"] == khe[0]["start_at"] + timedelta(minutes=chiem)
    starts = [k["start_at"] for k in khe]
    assert starts == sorted(starts), "khe sắp xếp tăng dần theo giờ bắt đầu"
    # Mỗi khe mang NHÃN NGÀY thật (thứ · cuối tuần · ngày lễ · ca đêm) để UI không phải gắn đại
    # chữ "lý tưởng" cho một chỗ rơi vào chủ nhật.
    nhan = khe[0]["nhan_ngay"]
    assert {"thu", "cuoi_tuan", "ngay_le", "ca_dem"} <= set(nhan)
    assert nhan["thu"] and isinstance(nhan["cuoi_tuan"], bool)


def test_goi_y_khe_chua_chon_may_thi_bao_thieu(v2, db, orders, lsx_svc, admin, customer):
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    dong.may_id = None                                          # gỡ máy khỏi dòng nháp
    db.commit()
    res = v2.goi_y_khe(dong_id=dong.id, tu=date(2026, 7, 27), den=date(2026, 7, 27))
    assert res["khe"] == []
    assert res["ghi_chu"] and "máy" in res["ghi_chu"].lower()


# ======================================================================
# ĐỢT 0 (0.1) — REGRESSION 500: PUT /dong lưu XONG rồi DỰNG view phải chạy trọn.
# Bug đã sửa: router gọi `svc._dong_view(saved)` (thiếu tham số `nhan`) ⇒ TypeError ⇒ 500 SAU KHI
# đã commit + đẩy SSE (mất-đồng-bộ tệ nhất). Chốt bằng đúng hai bước router làm ở dòng 233.
# ======================================================================
def test_luu_xong_dung_view_khong_500(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    step = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)

    saved = v2.luu(dong_id=dong.id,
                   patch={"may_id": step.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
                   expected_updated_at=dong.updated_at, actor=admin)
    view = v2.dong_view(saved)                                   # đúng `return svc.dong_view(saved)` của router
    assert view["id"] == dong.id
    assert view["may_id"] == step.may_id
    assert view["start_at"] == datetime(2026, 7, 27, 8, 0)
    assert view["finish_at"] is not None, "đã có máy + giờ bắt đầu ⇒ tính được giờ xong"


def test_router_put_dong_tra_qua_view_cong_khai():
    """Guard cấu trúc: PUT /dong trả qua `dong_view` (1 tham số), KHÔNG `_dong_view(saved)` (cần 2)."""
    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "xep_lich_2.py").read_text(
        encoding="utf-8")
    assert "return svc.dong_view(saved)" in src
    assert "svc._dong_view(saved)" not in src, "regression 500: gọi hàm 2 tham số bằng 1 tham số"


# ======================================================================
# ĐỢT 1 (1.1) — THUÊ NGOÀI đo bằng LEAD-TIME gửi→nhận, KHÔNG phải phút máy (≈0).
# ======================================================================
# ======================================================================
# ĐỢT 1 (1.4) — THIẾU hạn SX thì ĐO TRỄ theo HẠN GIAO KHÁCH (chưa khai hạn SX ≠ muốn trễ).
# ======================================================================
def test_tre_va_sat_han_lui_ve_han_giao_khi_thieu_han_sx():
    # tre_han_sx: không có hạn SX, xong 29/7 > hạn giao 28/7 ⇒ vẫn CHẶN PHÁT HÀNH, đo theo hạn giao.
    vd = C.tre_han_sx(_utc(2026, 7, 29, 9, 0), None, date(2026, 7, 28))
    assert vd["ma"] == "tre_han_sx" and vd["muc"] == MUC_CHAN_PHAT_HANH
    assert "giao khách" in vd["mo_ta"]
    assert C.tre_han_sx(_utc(2026, 7, 27, 9, 0), None, date(2026, 7, 28)) is None   # xong trước hạn giao
    assert C.tre_han_sx(_utc(2026, 7, 29, 9, 0), None, None) is None                # trống cả hai: không kết luận

    # Có hạn SX thì hạn SX THẮNG (đo theo 30/7, bỏ qua hạn giao 28/7).
    assert C.tre_han_sx(_utc(2026, 7, 29, 9, 0), date(2026, 7, 30), date(2026, 7, 28)) is None

    # sat_han_sx: thiếu hạn SX ⇒ cảnh báo đệm mỏng theo hạn giao (còn 1 ngày ≤ 2).
    sv = C.sat_han_sx(_utc(2026, 7, 29, 9, 0), None, date(2026, 7, 30))
    assert sv["ma"] == "sat_han_sx" and sv["muc"] == MUC_CANH_BAO
    assert "giao khách" in sv["mo_ta"]


# ======================================================================
# ĐỢT 3 (B9) — BỐI CẢNH MỘT LỆNH/BÀI: dữ liệu Panel phải gom trong MỘT cú gọi.
# `GET /boi-canh/{nguon}/{id}` → header + hạn + đệm · tóm tắt vật tư · vấn đề phát hành ·
# danh sách bước (thời lượng ba mức · máy/tổ/NCC · định biên · quân số · vấn đề của bước).
# ======================================================================
_KHOA_BUOC = {
    "id", "thu_tu", "cong_doan_ten", "loai_buoc", "trang_thai", "is_locked",
    "start_at", "finish_at", "chiem_may_phut", "chiem_may_phut_min", "chiem_may_phut_max",
    "theo_may", "nguon_thoi_luong", "may_id", "may_ten", "department_id", "to_ten",
    "nha_cung_cap", "so_nhan_cong", "dinh_bien", "quan_so", "van_de",
}


def test_boi_canh_lenh_chua_vao_ke_hoach(v2, db, orders, lsx_svc, admin, customer):
    """Lệnh CHƯA 'Đưa vào kế hoạch' vẫn mở Panel được: header + tóm tắt vật tư + cửa phát hành có
    mặt, còn chuỗi bước rỗng (`da_vao_ke_hoach=False`) — Panel nói 'chưa vào kế hoạch' thay vì 404."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    bc = v2.boi_canh(nguon="lsx", id=lsx.id)
    assert bc["nguon"] == "lsx" and bc["id"] == lsx.id
    assert bc["ma"] == lsx.ma and bc["ten_san_pham"] == lsx.ten
    assert bc["da_vao_ke_hoach"] is False and bc["buoc"] == []
    assert "is_rush" in bc
    assert isinstance(bc["vat_tu"], dict) and "du" in bc["vat_tu"]
    assert isinstance(bc["van_de"], list)                          # cửa phát hành dùng chung


def test_boi_canh_han_va_dem_giao(v2, db, orders, lsx_svc, admin, customer):
    """Hạn SX + hạn giao khách + số ngày đệm giữa hai mốc lộ đúng cho Panel (đọc từ `ctx.hai_han`)."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    lsx.han_hoan_thanh_sx = date(2026, 7, 27)
    lsx.han_giao_khach = date(2026, 7, 30)
    db.commit()
    bc = v2.boi_canh(nguon="lsx", id=lsx.id)
    assert bc["han_sx"] == date(2026, 7, 27)
    assert bc["han_giao"] == date(2026, 7, 30)
    assert bc["dem_ngay"] == 3                                     # 30/7 − 27/7 = 3 ngày đệm


def test_boi_canh_buoc_du_khoa_va_sap_theo_thu_tu(v2, db, orders, lsx_svc, admin, customer):
    """Đã vào kế hoạch (nháp): mỗi bước mang ĐỦ khoá Panel, chuỗi SẮP theo thứ tự routing tăng dần,
    định biên là dict ba mốc, `van_de` là list — Panel render thẳng không phải join lại."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)

    bc = v2.boi_canh(nguon="lsx", id=lsx.id)
    assert bc["da_vao_ke_hoach"] is True and bc["buoc"], "có bước nháp"
    thu_tu = [b["thu_tu"] for b in bc["buoc"]]
    assert thu_tu == sorted(thu_tu), "chuỗi bước sắp theo thứ tự routing"
    for b in bc["buoc"]:
        assert _KHOA_BUOC <= set(b), f"bước thiếu khoá Panel: {_KHOA_BUOC - set(b)}"
        assert set(b["dinh_bien"]) == {"toi_thieu", "tieu_chuan", "toi_da"}
        assert isinstance(b["van_de"], list)
        assert b["nguon_thoi_luong"] in ("may", "tay", "thue_ngoai")


def test_boi_canh_buoc_da_xep_theo_may_co_gio_va_ten_may(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Bước IN đã xếp giờ trên máy: Panel phơi giờ bắt đầu/xong + TÊN máy + nguồn thời lượng 'may',
    và quân số tổ tính được (có giờ chạy) — đúng số như xem-trước (`_tinh`)."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    v2.luu(dong_id=dong.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 7, 27, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)

    bc = v2.boi_canh(nguon="lsx", id=lsx.id)
    b = next(x for x in bc["buoc"] if x["id"] == dong.id)
    assert b["start_at"] == datetime(2026, 7, 27, 8, 0)
    assert b["finish_at"] == datetime(2026, 7, 27, 9, 30)          # 90' chiếm máy, chạy liên tục
    assert b["may_id"] == inb.may_id and b["may_ten"]
    assert b["nguon_thoi_luong"] == "may" and b["theo_may"] is True
    assert b["chiem_may_phut"] == 90
    assert b["quan_so"] is not None and "con_ranh" in b["quan_so"]


def test_boi_canh_khong_thay_va_nguon_sai(v2, db, orders, lsx_svc, admin, customer):
    """Không thấy lệnh ⇒ `XepLichNotFound` (router map 404); nguồn lạ ⇒ `XepLich2Error` (map 400)."""
    with pytest.raises(XepLichNotFound):
        v2.boi_canh(nguon="lsx", id=999999)
    with pytest.raises(XepLichNotFound):
        v2.boi_canh(nguon="in_ghep", id=999999)
    with pytest.raises(XepLich2Error):
        v2.boi_canh(nguon="ban_be", id=1)


# ======================================================================
# TỰ XẾP CẢ CHUỖI (`auto.tu_xep`) — thuật toán tự xếp lịch công đoạn.
# Bốn thứ phải đúng, thiếu cái nào là "tự xếp" thành "nhét bừa":
#   1. Chuỗi nối đuôi nhau (bước sau ≥ bước trước xong), không phải N quyết định mù nhau.
#   2. Hai lệnh cùng máy KHÔNG đè giờ nhau — bước vừa đặt phải làm bước sau nhìn thấy máy bận.
#   3. Mọi cách đặt nó ghi ra đều PHẢI qua được chính cửa `luu` (không tự cho mình luật riêng).
#   4. Dòng đã khoá / đã có giờ thì không đụng (trừ khi người bấm "xếp lại").
# ======================================================================
def _chuoi_in_xa(db, lsx_id: int) -> tuple[LsxCongDoan, LsxCongDoan]:
    """Routing 2 bước có phụ thuộc thật: In (90') → Xả tờ (50'), cùng nhóm máy."""
    inb = _in_theo_may(db, lsx_id)
    xa = LsxCongDoan(lsx_id=lsx_id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
                     may_id=inb.may_id, so_luong_vao=5000, nang_suat=6000,
                     don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to")
    db.add(xa)
    db.flush()
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=inb.id, buoc_sau_id=xa.id))
    db.commit()
    return inb, xa


def test_tu_xep_noi_duoi_ca_chuoi(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Xếp một phát cả lệnh: mọi bước có giờ, bước sau bắt đầu SAU khi bước trước xong."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb, xa = _chuoi_in_xa(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)

    kq = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    assert kq["bo_qua"] == [], "không bước nào được phép rơi lại: %r" % kq["bo_qua"]
    assert len(kq["da_xep"]) == 2
    theo_thu_tu = sorted(kq["da_xep"], key=lambda k: k["thu_tu"])
    a, b = theo_thu_tu
    assert b["start_at"] >= a["finish_at"], "bước sau phải đợi bước trước xong"
    for k in theo_thu_tu:
        assert k["start_at"] and k["finish_at"] and k["may_id"]
        assert k["ly_do"], "mỗi bước phải nói được VÌ SAO chọn máy/giờ đó"
        # Đặt lịch luôn dùng mức TRUNG BÌNH; min/max chỉ để Gantt vẽ râu (§3.3).
        assert k["chiem_may_phut_min"] <= k["chiem_may_phut"] <= k["chiem_may_phut_max"]
        assert k["finish_at"] == k["start_at"] + timedelta(minutes=k["chiem_may_phut"])

    # Ghi thật xuống dòng, không phải chỉ trả về cho vui.
    dongs = {d.lsx_cong_doan_id: d for d in XepLichRepository(db).by_lsx(lsx.id)}
    for step in (inb, xa):
        d = dongs[step.id]
        assert d.start_at is not None and d.finish_at is not None and d.trang_thai == TT_DA_XEP
    assert kq["tom_tat"] and "Xếp được 2 bước" in kq["tom_tat"]


def test_tu_xep_khong_de_hai_lenh_trung_may(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Hai lệnh cùng một máy: tự xếp lệnh 2 phải NHÌN THẤY máy vừa bị lệnh 1 chiếm."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    l0, l1 = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    in0 = _in_theo_may(db, l0.id)
    in1 = _in_theo_may(db, l1.id)
    in1.may_id = in0.may_id
    db.commit()
    v2.tao_nhap(nguon="lsx", id=l0.id, actor=admin)
    v2.tao_nhap(nguon="lsx", id=l1.id, actor=admin)

    k0 = v2.tu_xep(nguon="lsx", id=l0.id, actor=admin)
    k1 = v2.tu_xep(nguon="lsx", id=l1.id, actor=admin)
    assert len(k0["da_xep"]) == 1 and len(k1["da_xep"]) == 1
    a, b = k0["da_xep"][0], k1["da_xep"][0]
    if a["may_id"] == b["may_id"]:
        assert a["finish_at"] <= b["start_at"] or b["finish_at"] <= a["start_at"], \
            "hai việc cùng máy mà chồng giờ nhau"


def test_khe_dau_tien_ne_cach_dat_de_ra_canh_bao(monkeypatch):
    """C — tự-xếp không được giao ra bản kế hoạch mà CHÍNH NÓ chấm là có vấn đề.

    Khe sớm nhất dính `MA_NE` (cảnh báo do chỗ đặt chật) thì dò thêm tìm khe sạch; hết trần mà
    không có thì quay về đúng khe sớm nhất — né KHÔNG BAO GIỜ được đắt hơn thứ nó né."""
    t0 = _utc(2026, 7, 27, 8, 0)
    moc = [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2)]
    monkeypatch.setattr(A, "_moc_ung_vien",
                        lambda service, dong, shadow, *, san, chan_ngay, ca: moc)

    def dung(theo_moc: dict):
        """`service` giả: mỗi mốc trả sẵn danh sách vấn đề đã dựng."""
        return SimpleNamespace(_van_de_dat_lich=lambda shadow, *, start, **kw: theo_moc[start])

    lan = [C.issue("lan_viec_ke", MUC_CANH_BAO, "lấn việc kế")]
    chan = [C.issue("trung_may", MUC_CHAN_DAT_LICH, "trùng máy")]
    tai = [C.issue("tai_may_cao", MUC_CANH_BAO, "máy tải cao")]
    dong = SimpleNamespace(id=1)
    shadow = SimpleNamespace(may_id=9, department_id=3)

    def khe(service, **kw):
        return A._khe_dau_tien(service, dong, shadow, chiem=30, chiem_max=60, san=t0,
                               chan_ngay=7, ca=[(480, 960, False)], **kw)

    # Mốc 1 lấn việc kế · mốc 2 bị chặn · mốc 3 sạch ⇒ lấy mốc 3, và KHÔNG mang cảnh báo nào về.
    sv = dung({moc[0]: lan, moc[1]: chan, moc[2]: []})
    assert khe(sv) == (moc[2], [], None)
    # Lượt CỨU HẠN (`ne_canh_bao=False`) vẫn ăn khe sớm nhất, kèm cảnh báo của nó.
    start, cb, _ = khe(sv, ne_canh_bao=False)
    assert start == moc[0] and [i["ma"] for i in cb] == ["lan_viec_ke"]
    # Cảnh báo NGOÀI diện né (`tai_may_cao`) không đáng để dời việc — nhận ngay khe sớm nhất.
    assert khe(dung({moc[0]: tai, moc[1]: [], moc[2]: []}))[0] == moc[0]
    # Mốc nào cũng lấn ⇒ quay về khe sớm nhất chứ không bỏ trống máy, và vẫn nói ra cảnh báo.
    start, cb, vi_sao = khe(dung({moc[0]: lan, moc[1]: lan, moc[2]: lan}))
    assert start == moc[0] and [i["ma"] for i in cb] == ["lan_viec_ke"] and vi_sao is None


def test_khe_dau_tien_khong_ne_qua_tran_gio(monkeypatch):
    """Khe sạch nằm quá `TRAN_NE_GIO` giờ ⇒ thà mang cảnh báo còn hơn bỏ máy trống nửa ngày."""
    t0 = _utc(2026, 7, 27, 8, 0)
    moc = [t0, t0 + timedelta(hours=A.TRAN_NE_GIO + 1)]
    monkeypatch.setattr(A, "_moc_ung_vien",
                        lambda service, dong, shadow, *, san, chan_ngay, ca: moc)
    lan = [C.issue("lan_viec_ke", MUC_CANH_BAO, "lấn việc kế")]
    theo_moc = {moc[0]: lan, moc[1]: []}
    sv = SimpleNamespace(_van_de_dat_lich=lambda shadow, *, start, **kw: theo_moc[start])
    start, cb, _ = A._khe_dau_tien(sv, SimpleNamespace(id=1), SimpleNamespace(may_id=9,
                                   department_id=3), chiem=30, chiem_max=60, san=t0,
                                   chan_ngay=7, ca=[(480, 960, False)])
    assert start == moc[0] and [i["ma"] for i in cb] == ["lan_viec_ke"]


def test_tu_xep_khong_tu_de_ra_canh_bao_lan_viec_ke(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """A+C hợp lại: xếp cả chuỗi In → Xả trên cùng một máy không được đẻ ra `lan_viec_ke`.

    Đây đúng cảnh người xếp gặp trên màn: tự-xếp nối đuôi hai bước của CÙNG lệnh rồi tự chấm kế
    hoạch mình vừa đẻ là có vấn đề (25/08/2026)."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _chuoi_in_xa(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)

    kq = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    assert len(kq["da_xep"]) == 2
    ma = [i["ma"] for k in kq["da_xep"] for i in (k.get("canh_bao") or [])]
    assert "lan_viec_ke" not in ma, "tự-xếp tự tố kế hoạch của chính mình: %r" % ma


def test_tu_xep_moi_cach_dat_deu_qua_duoc_cua_luu(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Bất biến quan trọng nhất: cách đặt tự-xếp ghi ra phải KHÔNG vướng luật CHẶN của `_van_de_dat_lich`.

    Nếu hỏng, người dùng gặp cảnh "hệ tự xếp xong, mở ra sửa một tí là bị chính hệ chặn".
    """
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _chuoi_in_xa(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    kq = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)

    for k in kq["da_xep"]:
        dong = v2.core._get_dong(k["dong_id"])
        pv = v2.xem_truoc(dong_id=dong.id, patch={
            "may_id": k["may_id"], "start_at": k["start_at"].replace(tzinfo=timezone.utc),
        })
        chan = [i for i in pv["van_de"] if i["muc"] == MUC_CHAN_DAT_LICH]
        assert chan == [], "tự xếp đẻ ra cách đặt mà chính hệ chặn: %r" % chan


def test_tu_xep_khong_dung_dong_da_khoa(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """Khoá là có ý; đã có giờ là người ta đã quyết. Tự xếp chỉ lấp chỗ TRỐNG — trừ khi bấm xếp lại."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb, xa = _chuoi_in_xa(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dongs = {d.lsx_cong_doan_id: d for d in XepLichRepository(db).by_lsx(lsx.id)}
    d_in, d_xa = dongs[inb.id], dongs[xa.id]

    # In: xếp tay rồi KHOÁ. Xả tờ: để trống.
    v2.luu(dong_id=d_in.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 9, 28, 8, 0)},
           expected_updated_at=d_in.updated_at, actor=admin)
    d_in = v2.core._get_dong(d_in.id)
    d_in.is_locked = True
    db.commit()
    moc_in = (d_in.may_id, d_in.start_at, d_in.finish_at)

    kq = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    assert kq["so_giu_nguyen"] == 1
    assert [k["dong_id"] for k in kq["da_xep"]] == [d_xa.id]
    d_in = v2.core._get_dong(d_in.id)
    assert (d_in.may_id, d_in.start_at, d_in.finish_at) == moc_in, "dòng khoá bị đụng"

    # Ngay cả khi bấm "xếp lại toàn bộ", dòng KHOÁ vẫn không bị đụng.
    kq2 = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin, ghi_de=True)
    assert kq2["so_giu_nguyen"] == 1
    d_in = v2.core._get_dong(d_in.id)
    assert (d_in.may_id, d_in.start_at, d_in.finish_at) == moc_in


def test_tu_xep_ghi_de_xep_lai_dong_da_co_gio(v2, db, orders, lsx_svc, admin, customer, monkeypatch):
    """`ghi_de=True` = "xếp lại toàn bộ": dòng đã có giờ (không khoá) được tính lại, không bị giữ."""
    monkeypatch.setattr(v2.core.cal, "is_working_day", lambda d: True)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    inb = _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)
    v2.luu(dong_id=dong.id,
           patch={"may_id": inb.may_id, "start_at": _utc(2026, 12, 25, 8, 0)},
           expected_updated_at=dong.updated_at, actor=admin)

    giu = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    assert giu["da_xep"] == [] and giu["so_giu_nguyen"] == 1
    assert "Không có bước nào cần xếp" in giu["tom_tat"]

    lai = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin, ghi_de=True)
    assert len(lai["da_xep"]) == 1 and lai["so_giu_nguyen"] == 0
    dong = v2.core._get_dong(dong.id)
    assert dong.start_at is not None
    assert _naive(dong.start_at) < datetime(2026, 12, 25, 8, 0), "xếp lại phải kéo sớm hơn chỗ cũ"


def test_tu_xep_lenh_chua_vao_ke_hoach(v2, db, orders, lsx_svc, admin, customer):
    """Lệnh chưa đưa vào kế hoạch (0 dòng) ⇒ nói rõ "không có bước nào cần xếp", không nổ."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    kq = v2.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    assert kq["da_xep"] == [] and kq["bo_qua"] == [] and kq["luot"] == 0
    assert "Không có bước nào cần xếp" in kq["tom_tat"]


# ============================================================================
# THỨ TỰ XẾP THEO ROUTING (routing.thu_tu_xep) — hàm thuần, kiểm ở mức hàm
# ============================================================================
def _r(id: int, thu_tu: int):
    return SimpleNamespace(id=id, source_thu_tu=thu_tu)


def test_thu_tu_xep_theo_dag_khi_canh_nguoc_thu_tu():
    """Cạnh routing được phép NGƯỢC `thu_tu` (LSX26-0020 thật: B1→B6→B2→B3→B4→B5).

    Duyệt theo `thu_tu` thì tới lượt B2, tiền nhiệm B6 của nó chưa có giờ ⇒ sàn thiếu mất tiền nhiệm
    ⇒ cả chuỗi rơi về "bây giờ" và chồng lên nhau. Phải xếp theo thứ tự TÔ-PÔ.
    """
    from app.services.xep_lich_2.routing import thu_tu_xep
    rows = [_r(1, 0), _r(2, 1), _r(3, 2), _r(4, 3), _r(5, 4), _r(6, 5)]
    canh = {2: [6], 3: [2], 4: [3], 5: [4], 6: [1]}          # B2←B6, B3←B2, …, B6←B1
    assert [r.id for r in thu_tu_xep(rows, canh)] == [1, 6, 2, 3, 4, 5]


def test_thu_tu_xep_giu_nguyen_thu_tu_khi_dag_thuan():
    """DAG trùng `thu_tu` (đại đa số lệnh) hoặc không có cạnh nào ⇒ ra ĐÚNG thứ tự cũ, không đảo."""
    from app.services.xep_lich_2.routing import thu_tu_xep
    rows = [_r(30, 2), _r(10, 0), _r(20, 1)]
    assert [r.id for r in thu_tu_xep(rows, {20: [10], 30: [20]})] == [10, 20, 30]
    assert [r.id for r in thu_tu_xep(rows, {})] == [10, 20, 30]


def test_thu_tu_xep_con_vong_thi_khong_chet():
    """Dữ liệu cũ còn vòng (đáng lẽ `_kiem_chu_trinh_phu_thuoc` đã chặn) ⇒ nối phần kẹt vào cuối
    theo `thu_tu`, KHÔNG ném lỗi: tự xếp không được phép chết vì một cạnh hỏng."""
    from app.services.xep_lich_2.routing import thu_tu_xep
    rows = [_r(1, 0), _r(2, 1), _r(3, 2)]
    ra = thu_tu_xep(rows, {2: [3], 3: [2]})                  # B2 ⇄ B3
    assert [r.id for r in ra] == [1, 2, 3]
    assert len(ra) == 3, "không được đánh rơi bước nào"


# ======================================================================
# §6.1 — CHẤM ĐIỂM MÁY (`diem_may`): kịp hạn trước, gate theo dữ liệu, không đụng khổ.
# ======================================================================
def _uv(may_id: int, finish: datetime, **kw) -> dict:
    """Một ứng viên máy tối giản — đúng những khoá mà `diem_may` đọc."""
    return {"may_id": may_id, "may_ten": f"M{may_id}", "finish": finish,
            "co_gom": kw.get("co_gom", False), "cung_gom": kw.get("cung_gom", False),
            "tai_ngay": kw.get("tai_ngay", 0)}


_CA_8H = [(480, 960, False)]                                     # 8h–16h = 480 phút/ngày


def test_diem_may_quy_ca_phut_cong_ca_qua_dem():
    from app.services.xep_lich_2 import diem_may as DM
    assert DM.quy_ca_phut(_CA_8H) == 480
    assert DM.quy_ca_phut([(1320, 360, True)]) == 480            # 22h→6h vắt qua nửa đêm


def test_diem_may_va_canh_bao_tai_dung_CHUNG_mot_thuoc():
    """⭐ Trục `san_tai` (chấm khe gợi ý) và cảnh báo "máy ken đặc" phải đo cùng một mẫu số.
    Trước 22/08/2026 đây là hai bản sao độc lập của cùng phép cộng ⇒ sửa một nơi thì nơi kia lệch
    âm thầm: máy bị trừ điểm san tải theo một thước, còn đèn cảnh báo bật theo thước khác.
    """
    from app.services.xep_lich_2 import diem_may as DM
    for ca in (_CA_8H, CA_XUONG_GOI_NHAU, [(1320, 360, True)], []):
        assert DM.quy_ca_phut(ca) == C.phut_ca_moi_ngay(ca)
    assert DM.quy_ca_phut(CA_XUONG_GOI_NHAU) == 1440
    assert DM.quy_ca_phut(None) == 0                             # chưa khai ca — trục tự tắt, không nổ


def test_diem_may_tre_han_bi_danh_dau_va_ve_khong_diem_kip_han():
    """Xong sau 24h ngày hạn = TRỄ. Cờ `tre_han` là cái mà `chon_may` lọc, không phải điểm thấp."""
    from app.services.xep_lich_2 import diem_may as DM
    han = date(2026, 8, 20)
    kip = _uv(1, datetime(2026, 8, 20, 15, tzinfo=timezone.utc))
    tre = _uv(2, datetime(2026, 8, 21, 9, tzinfo=timezone.utc))  # đã sang ngày sau hạn
    DM.cham_tat_ca([kip, tre], han=han, ca=_CA_8H)
    assert kip["diem"]["tre_han"] is False
    assert tre["diem"]["tre_han"] is True
    assert tre["diem"]["diem"] < kip["diem"]["diem"]
    assert next(t for t in tre["diem"]["truc"] if t["ma"] == "kip_han")["dat"] == 0


def test_diem_may_xong_23h_ngay_han_van_la_kip():
    """Hạn là NGÀY: xong 23h ngày hạn vẫn kịp. Nếu so với 0h ngày hạn thì cả xưởng trễ oan."""
    from app.services.xep_lich_2 import diem_may as DM
    u = _uv(1, datetime(2026, 8, 20, 23, tzinfo=timezone.utc))
    DM.cham_tat_ca([u], han=date(2026, 8, 20), ca=_CA_8H)
    assert u["diem"]["tre_han"] is False


def test_diem_may_gom_giay_thang_khi_hai_may_cung_kip_han():
    """Hai máy cùng kịp thoải mái ⇒ trục kịp hạn hoà, quyền quyết về trục ĐỔI BÀI."""
    from app.services.xep_lich_2 import diem_may as DM
    xa = datetime(2026, 8, 10, 10, tzinfo=timezone.utc)
    noi = _uv(1, xa, co_gom=True, cung_gom=True)
    roi = _uv(2, xa, co_gom=True, cung_gom=False)
    DM.cham_tat_ca([noi, roi], han=date(2026, 12, 31), ca=_CA_8H)
    assert noi["diem"]["diem"] > roi["diem"]["diem"]
    assert "giấy" in " ".join(noi["diem"]["manh"])


def test_diem_may_truc_khong_do_duoc_bi_bo_khoi_ca_tu_lan_mau():
    """Lệnh chưa đủ quy cách ⇒ KHÔNG có trục `doi_bai`, và điểm KHÔNG bị kéo tụt vì thiếu nó.

    Chấm 0 cho thứ chưa khai là phạt oan mọi máy như nhau — vô nghĩa, mà còn làm người đọc tưởng
    cả xưởng đều tệ.
    """
    from app.services.xep_lich_2 import diem_may as DM
    xa = datetime(2026, 8, 10, 10, tzinfo=timezone.utc)
    khong_do = _uv(1, xa, co_gom=False)
    do_duoc = _uv(2, xa, co_gom=True, cung_gom=True)
    DM.cham_tat_ca([khong_do], han=date(2026, 12, 31), ca=_CA_8H)
    DM.cham_tat_ca([do_duoc], han=date(2026, 12, 31), ca=_CA_8H)
    assert [t["ma"] for t in khong_do["diem"]["truc"]] == ["kip_han", "san_tai"]
    assert khong_do["diem"]["diem"] == do_duoc["diem"]["diem"], "thiếu dữ liệu ≠ máy dở"


def test_diem_may_chua_khai_ca_thi_bo_truc_san_tai():
    from app.services.xep_lich_2 import diem_may as DM
    u = _uv(1, datetime(2026, 8, 10, 10, tzinfo=timezone.utc))
    DM.cham_tat_ca([u], han=date(2026, 12, 31), ca=[])
    assert [t["ma"] for t in u["diem"]["truc"]] == ["kip_han"]


def test_diem_may_may_kin_ca_bi_tru_diem_san_tai():
    from app.services.xep_lich_2 import diem_may as DM
    xa = datetime(2026, 8, 10, 10, tzinfo=timezone.utc)
    ranh = _uv(1, xa, tai_ngay=0)
    kin = _uv(2, xa, tai_ngay=470)                               # gần kín 480 phút quỹ ca
    DM.cham_tat_ca([ranh, kin], han=date(2026, 12, 31), ca=_CA_8H)
    assert ranh["diem"]["diem"] > kin["diem"]["diem"]
    assert kin["diem"]["tru"] and "kín" in kin["diem"]["tru"]


def test_diem_may_khong_co_han_thi_do_tuong_doi_chu_khong_bo_truc():
    """Thiếu cả hai hạn ⇒ vẫn phải còn yếu tố thời gian, không thì hệ chọn máy xong muộn 10 ngày."""
    from app.services.xep_lich_2 import diem_may as DM
    som = _uv(1, datetime(2026, 8, 10, 10, tzinfo=timezone.utc))
    muon = _uv(2, datetime(2026, 8, 13, 10, tzinfo=timezone.utc))
    DM.cham_tat_ca([som, muon], han=None, ca=_CA_8H)
    assert som["diem"]["diem"] > muon["diem"]["diem"]
    assert som["diem"]["tre_han"] is False and muon["diem"]["tre_han"] is False


def test_diem_may_la_so_tuyet_doi_khong_doi_khi_bot_ung_vien():
    """Gợi ý bốc dần từng máy ra khỏi danh sách ⇒ điểm máy còn lại KHÔNG được nhảy."""
    from app.services.xep_lich_2 import diem_may as DM
    a = _uv(1, datetime(2026, 8, 10, 10, tzinfo=timezone.utc), co_gom=True, cung_gom=True)
    b = _uv(2, datetime(2026, 8, 11, 10, tzinfo=timezone.utc), co_gom=True)
    DM.cham_tat_ca([a, b], han=date(2026, 12, 31), ca=_CA_8H)
    truoc = b["diem"]["diem"]
    b2 = _uv(2, b["finish"], co_gom=True)
    DM.cham_tat_ca([b2], han=date(2026, 12, 31), ca=_CA_8H)
    assert b2["diem"]["diem"] == truoc


def test_chon_may_uu_tien_kip_han_hon_diem_cao():
    """Máy điểm cao mà TRỄ hạn không được thắng máy kịp hạn — hạn là điều kiện, không phải điểm."""
    from app.services.xep_lich_2 import auto, diem_may as DM
    kip = _uv(1, datetime(2026, 8, 20, 10, tzinfo=timezone.utc), tai_ngay=470)
    tre = _uv(2, datetime(2026, 8, 25, 10, tzinfo=timezone.utc), co_gom=True, cung_gom=True)
    for u in (kip, tre):
        u.update(chiem_may_phut=60)
    DM.cham_tat_ca([kip, tre], han=date(2026, 8, 20), ca=_CA_8H)
    assert auto.chon_may([kip, tre], nhanh_nhat=False)["may_id"] == 1
    # Lượt CỨU HẠN thì chỉ còn một câu hỏi là xong sớm nhất — ở đây vẫn là chính máy đó.
    assert auto.chon_may([kip, tre], nhanh_nhat=True)["may_id"] == 1


def test_chon_may_ca_hai_deu_tre_thi_lay_xong_som_nhat():
    from app.services.xep_lich_2 import auto, diem_may as DM
    a = _uv(1, datetime(2026, 8, 25, 10, tzinfo=timezone.utc), co_gom=True, cung_gom=True)
    b = _uv(2, datetime(2026, 8, 23, 10, tzinfo=timezone.utc))
    for u in (a, b):
        u.update(chiem_may_phut=60)
    DM.cham_tat_ca([a, b], han=date(2026, 8, 20), ca=_CA_8H)
    assert auto.chon_may([a, b], nhanh_nhat=False)["may_id"] == 2


def test_goi_y_may_kem_diem_va_bang_truc(v2, db, orders, lsx_svc, admin, customer):
    """Hợp đồng của `/goi-y`: mỗi máy kèm ĐIỂM 0–100 · cờ trễ hạn · bảng trục có câu giải thích."""
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    res = v2.goi_y(dong_id=_dong_in(db, lsx.id).id)
    assert {"goi_y_may", "bi_loai", "vi_sao_trong"} <= set(res)
    assert res["goi_y_may"], "máy làm được bước in thì phải có gợi ý"
    assert len(res["goi_y_may"]) <= 3
    g = res["goi_y_may"][0]
    assert 0 <= g["diem"] <= 100 and isinstance(g["tre_han"], bool)
    assert g["truc"] and all(
        {"ma", "ten", "dat", "toi_da", "ty_le", "cau"} <= set(t) and t["cau"] for t in g["truc"])
    assert all(t["ma"] in ("kip_han", "doi_bai", "san_tai") for t in g["truc"])
    assert g["ly_do"], "phải có MỘT câu vì-sao do chính thuật toán sinh"
    # Điểm giảm dần theo đúng thứ tự hiện ra (trong cùng nhóm kịp hạn).
    kip = [x["diem"] for x in res["goi_y_may"] if not x["tre_han"]]
    assert kip == sorted(kip, reverse=True)


def test_goi_y_may_loai_may_khong_tinh_duoc_thoi_luong_va_noi_ly_do(
    v2, db, orders, lsx_svc, admin, customer, monkeypatch,
):
    """Máy KHÔNG làm được bước thì phải bị loại — và phải nói ra vì sao, đừng vắng mặt im lặng.

    Bẫy thật đã gặp: máy chưa khai tốc độ vẫn ra thời lượng > 0 nhờ makeready + phát sinh, nên
    "Ghi kẽm CTP" từng được gợi ý ba máy in offset ở đúng 45 phút — xếp nhất chính vì chúng
    không làm được việc.
    """
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    _in_theo_may(db, lsx.id)
    v2.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    dong = _dong_in(db, lsx.id)

    from app.services.xep_lich_2 import auto
    that = auto.thoi_luong_buoc

    def gia(*a, **kw):                                           # ép mọi máy về đường KHÔNG-theo-máy
        d = dict(that(*a, **kw))
        d["dien_giai"] = {**(d.get("dien_giai") or {}), "phuong_phap": "to"}
        return d

    monkeypatch.setattr(auto, "thoi_luong_buoc", gia)
    res = v2.goi_y(dong_id=dong.id)
    assert res["goi_y_may"] == []
    assert res["bi_loai"], "loại hết máy thì phải liệt kê ra"
    assert res["vi_sao_trong"], "và phải có một câu tổng nói vì sao danh sách trống"


def test_ruy_bang_ca_tren_gantt_bo_ca_van_phong(v2, db):
    """Ruy-băng "CA LÀM VIỆC" trên bàn Xếp lịch 2 chỉ vẽ ca dưới xưởng (mg 0227).

    Trước cờ: Hành chính 08:00–17:00 chồng lên Ca 1 + Ca 2 nên FE phải đẩy nó xuống DÒNG THỨ HAI
    — ruy-băng cao gấp đôi mà không nói thêm điều gì về giờ chạy máy. FE không tự lọc: `caLayout`
    dựng thẳng từ `ca_nhan` máy chủ gửi, và mẫu số % tải cũng đọc chính mảng đó — lọc ở đây là
    lọc cả hai.
    """
    _khai_ca_xuong(db)
    ten = [c["ten"] for c in v2._ca_nhan()]
    assert ten == ["Ca 1", "Ca 2", "Ca 3"], ten
    assert all(0 <= c["bat_dau_phut"] < 1440 for c in v2._ca_nhan())


def test_khong_ca_nao_tick_thi_khung_gio_KHONG_roi_ve_8h(v2, db):
    """Cửa §7.1 (khung giờ hợp lệ để đặt việc) không được rơi về fallback 08:00–16:00.

    Đó là cách cờ đời trước hỏng trong im lặng: 4/4 ca FALSE ⇒ tập ca rỗng ⇒ engine tưởng xưởng
    chỉ làm 8 tiếng ngày, chặn mọi việc đặt ngoài khung đó.
    """
    from app.models.attendance import WorkShift

    _khai_ca_xuong(db)
    for c in db.query(WorkShift).all():
        c.ca_san_xuat = False
    db.commit()
    assert len(v2._ca_nhan()) == 4          # KHÔNG phải 1 dải "Giờ mặc định (chưa khai ca)"
