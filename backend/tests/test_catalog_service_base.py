"""Nền SERVICE danh mục (`services/catalog_base.CatalogService`) — khuôn CRUD + GIAO DỊCH.

Vì sao phải có file riêng, không ké `conftest`: `conftest` dùng SQLite in-memory + `StaticPool`,
tức MỌI session dùng CHUNG một connection — dữ liệu mới `flush()` mà chưa `commit()` vẫn thấy
được từ session khác. Nghĩa là bộ test hiện có KHÔNG chứng minh được là service có commit thật;
nó sẽ xanh y hệt kể cả khi bản ghi tan biến trên Postgres.

Ở đây dùng SQLite ghi RA FILE, mỗi session một connection riêng → chỉ thấy nhau qua dữ liệu ĐÃ
CHỐT. Đó là điều kiện đúng như Postgres dev/prod.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.bu_hao_repo import BuHaoRepository
from app.repositories.kho_hang_repo import KhoHangRepository
from app.repositories.khuon_be_repo import KhuonBeRepository
from app.services.bu_hao_service import BuHaoDuplicate, BuHaoNotFound, BuHaoService
from app.services.kho_hang_service import KhoHangInUse, KhoHangNotFound, KhoHangService
from app.services.khuon_be_service import KhuonBeNotFound, KhuonBeService


@pytest.fixture
def hai_session(tmp_path):
    """Trả `(mo_session, engine)` — mỗi lần gọi `mo_session()` là MỘT connection mới tới cùng file.

    Session thứ hai chỉ đọc được thứ session thứ nhất đã CHỐT.
    """
    eng = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}")
    Base.metadata.create_all(eng)
    Maker = sessionmaker(bind=eng)
    yield Maker
    eng.dispose()


# --- GIAO DỊCH: ghi bản ghi + ghi nhật ký đi CHUNG một lần chốt ---------------------------


def test_tao_xong_la_da_chot_that_du_khong_co_nhat_ky(hai_session):
    """Service dựng trần (`Service(repo)`, `audit=None`) vẫn phải CHỐT.

    Đây là ca dễ vỡ nhất khi tắt `commit_on_write` của repo: repo chỉ `flush()`, còn `audit`
    None thì nhật ký không ghi ⇒ không ai commit ⇒ session đóng là bản ghi bay mất. 10 test
    tầng service đang dựng service kiểu này.
    """
    ghi = hai_session()
    KhoHangService(KhoHangRepository(ghi)).create({"ten": "Kho giấy"})
    ghi.close()

    doc = hai_session()
    rows, total = KhoHangRepository(doc).list()
    assert total == 1 and rows[0].ten == "Kho giấy", "bản ghi không được chốt xuống DB"


def test_sua_va_xoa_cung_duoc_chot(hai_session):
    ghi = hai_session()
    svc = KhuonBeService(KhuonBeRepository(ghi))
    a = svc.create({"ten": "Khuôn hộp"})
    b = svc.create({"ten": "Khuôn túi"})
    svc.update(a.id, {"ten": "Khuôn hộp A4"})
    svc.delete(b.id)
    ghi.close()

    doc = hai_session()
    rows, total = KhuonBeRepository(doc).list()
    assert total == 1 and rows[0].ten == "Khuôn hộp A4"


def test_ban_ghi_va_nhat_ky_vao_cung_mot_luot(hai_session):
    """Có `audit` thì dòng nhật ký và bản ghi phải CÙNG có mặt sau khi chốt — không được cảnh
    "bản ghi nằm đó mà không có vết ai tạo"."""
    ghi = hai_session()
    KhoHangService(KhoHangRepository(ghi), AuditLogRepository(ghi)).create(
        {"ten": "Kho mực"}, actor_id=None)
    ghi.close()

    doc = hai_session()
    rows, _ = KhoHangRepository(doc).list()
    assert len(rows) == 1
    assert AuditLogRepository(doc).list_by_target(f"kho_hang:{rows[0].id}"), \
        "bản ghi đã chốt nhưng KHÔNG có dòng nhật ký nào"


def test_nhat_ky_no_thi_ban_ghi_KHONG_lot_vao_DB(hai_session):
    """⭐ Chốt của cả đợt gom giao dịch. Trước 15/08/2026 repo commit TRƯỚC rồi service mới ghi
    audit — audit nổ là **mất vết mà bản ghi vẫn nằm đó**. Nay hai việc đi chung một giao dịch.

    Test này CHỈ có nghĩa khi repo đã tắt `commit_on_write`; còn bật thì bỏ qua chứ không giả vờ
    xanh (repo commit trước nên bản ghi vào DB là ĐÚNG với chế độ đó).
    """
    if KhoHangRepository.commit_on_write:
        pytest.skip("repo còn tự commit — giao dịch chưa gom về service")

    class AuditNo(AuditLogRepository):
        def create(self, **kw):
            raise RuntimeError("ổ đĩa nhật ký hỏng")

    ghi = hai_session()
    svc = KhoHangService(KhoHangRepository(ghi), AuditNo(ghi))
    with pytest.raises(RuntimeError):
        svc.create({"ten": "Kho hỏng"})
    ghi.rollback()
    ghi.close()

    doc = hai_session()
    _, total = KhoHangRepository(doc).list()
    assert total == 0, "nhật ký nổ mà bản ghi vẫn lọt vào DB"


# --- KHUÔN CRUD: lớp exception PHẢI là của chính danh mục ---------------------------------


def test_moi_danh_muc_nem_dung_lop_exception_cua_no(hai_session):
    """⚠️ Bẫy chính của đợt B6. Nền mà ném lớp CƠ SỞ dùng chung thì router đang viết
    `except KhoHangNotFound` không bắt được, 404 rơi thành 500 trong im lặng."""
    db = hai_session()
    with pytest.raises(KhoHangNotFound):
        KhoHangService(KhoHangRepository(db)).get(9999)
    with pytest.raises(KhuonBeNotFound):
        KhuonBeService(KhuonBeRepository(db)).get(9999)
    with pytest.raises(BuHaoNotFound):
        BuHaoService(BuHaoRepository(db)).get(9999)


def test_cau_bao_loi_giu_nguyen_chu_cua_tung_man(hai_session):
    """"Không tìm thấy kho." KHÁC "Không tìm thấy khuôn bế." — người dùng đọc câu này, không đọc
    tên lớp."""
    db = hai_session()
    with pytest.raises(KhoHangNotFound) as e_kho:
        KhoHangService(KhoHangRepository(db)).get(1)
    with pytest.raises(KhuonBeNotFound) as e_kb:
        KhuonBeService(KhuonBeRepository(db)).get(1)
    assert "kho" in str(e_kho.value).lower()
    assert "khuôn" in str(e_kb.value).lower()


def test_trung_ma_nem_lop_duplicate_cua_danh_muc(hai_session):
    db = hai_session()
    svc = BuHaoService(BuHaoRepository(db))
    svc.create({"ma": "BH-GIAY", "ten": "Bù hao giấy"})
    with pytest.raises(BuHaoDuplicate):
        svc.create({"ma": "bh-giay", "ten": "Trùng, khác hoa thường"})


# --- Hai nét riêng mà nền phải giữ: mã tự sinh + xoá mềm ----------------------------------


def test_ma_tu_sinh_va_tai_dung_hang_da_xoa_mem(hai_session):
    """Kho xoá mềm rồi khai lại ĐÚNG mã đó (đường API, không phải UI) → tái dùng chính hàng cũ +
    bật lại `active`, không đẻ hàng rác mang mã trùng."""
    db = hai_session()
    svc = KhoHangService(KhoHangRepository(db))
    a = svc.create({"ten": "Kho A"})
    assert a.ma.startswith("KHO-"), f"mã tự sinh sai tiền tố: {a.ma}"

    svc.delete(a.id)
    assert svc.get(a.id).active is False, "xoá kho phải là XOÁ MỀM"

    lai = svc.create({"ma": a.ma, "ten": "Kho A dùng lại"})
    assert lai.id == a.id and lai.active is True
    _, total = KhoHangRepository(db).list()
    assert total == 1, "tái dùng mà vẫn đẻ thêm hàng"


def test_chan_xoa_khi_con_rang_buoc(hai_session, monkeypatch):
    """`_blockers` chặn xoá và câu báo phải kể ĐỦ lý do — hộp thoại xoá đọc chính chuỗi này."""
    db = hai_session()
    repo = KhoHangRepository(db)
    svc = KhoHangService(repo)
    kho = svc.create({"ten": "Kho còn tồn"})
    monkeypatch.setattr(repo, "dem_rang_buoc", lambda _id: {
        "lo_con_ton": 3, "phieu_cho_ghi_so": 0, "de_nghi_dang_xu_ly": 2})

    assert svc.delete_blockers(kho.id) == ["3 lô còn tồn", "2 đề nghị đang xử lý"]
    with pytest.raises(KhoHangInUse) as e:
        svc.delete(kho.id)
    assert "3 lô còn tồn" in str(e.value) and "2 đề nghị đang xử lý" in str(e.value)


def test_danh_muc_khai_ma_tay_khong_tu_cap_ma(hai_session):
    """Bù hao KHÔNG có `ma_prefix` — gửi thiếu mã thì phải báo lỗi khai thiếu, chứ không im lặng
    cấp một mã bịa."""
    db = hai_session()
    with pytest.raises(Exception) as e:
        BuHaoService(BuHaoRepository(db)).create({"ten": "Thiếu mã"})
    assert "Mã" in str(e.value)
