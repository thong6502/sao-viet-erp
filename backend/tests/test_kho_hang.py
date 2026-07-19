"""Danh mục Kho hàng (khai báo kho) — CRUD nhẹ + xử lý TRÙNG MÃ do xóa mềm.

Xóa mềm giữ `ma` (unique) trong DB → mã kẹt. create() phải tái dùng đúng hàng đã
xóa mềm khi mã trùng, thay vì 409. Self-contained in-memory DB.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.repositories.kho_hang_repo import KhoHangRepository
from app.services.kho_hang_service import (
    KhoHangDuplicate,
    KhoHangService,
    KhoHangValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, KhoHangService(KhoHangRepository(db))


def test_create_and_validate():
    db, svc = _svc()
    k = svc.create(dict(ma="KHO-0001", ten="Kho thành phẩm", vi_tri="Tầng 1"))
    assert k.id and k.ma == "KHO-0001" and k.active is True
    with pytest.raises(KhoHangValidationError):            # thiếu tên
        svc.create(dict(ma="KHO-0002", ten=""))


def test_ma_auto_generated_when_blank():
    db, svc = _svc()
    a = svc.create(dict(ten="Kho 1"))                      # không truyền mã → tự sinh
    b = svc.create(dict(ma="", ten="Kho 2"))              # mã rỗng cũng tự sinh
    assert a.ma == "KHO-0001" and b.ma == "KHO-0002"


def test_ma_auto_skips_soft_deleted_gap():
    db, svc = _svc()
    a = svc.create(dict(ten="Kho 1"))                      # KHO-0001
    b = svc.create(dict(ten="Kho 2"))                      # KHO-0002
    svc.update(b.id, dict(ten="Kho 2", active=False))     # xóa mềm KHO-0002
    c = svc.create(dict(ten="Kho 3"))                     # phải là KHO-0003, KHÔNG tái dùng 0002
    assert a.ma == "KHO-0001" and c.ma == "KHO-0003"


def test_duplicate_active_blocks():
    db, svc = _svc()
    svc.create(dict(ma="KHO-0001", ten="Kho A"))
    with pytest.raises(KhoHangDuplicate):                  # trùng kho đang hoạt động → chặn
        svc.create(dict(ma="kho-0001", ten="Kho khác"))   # (không phân biệt hoa/thường)


def test_soft_deleted_ma_reused_not_duplicate():
    db, svc = _svc()
    a = svc.create(dict(ma="KHO-0001", ten="Kho cũ", vi_tri="Tầng 1", ghi_chu="cũ"))
    svc.update(a.id, dict(ma="KHO-0001", ten="Kho cũ", active=False))  # xóa mềm (như UI)

    # Tạo lại đúng mã đã xóa mềm → KHÔNG 409, tái dùng chính hàng đó (cùng id).
    b = svc.create(dict(ma="KHO-0001", ten="Kho mới", vi_tri="Tầng 2", ghi_chu="mới"))
    assert b.id == a.id                                    # cùng 1 hàng, không đẻ hàng rác
    assert b.active is True
    assert b.ten == "Kho mới" and b.vi_tri == "Tầng 2" and b.ghi_chu == "mới"

    rows, total = svc.list(active=True)                   # chỉ 1 kho active, không nhân đôi
    assert total == 1 and rows[0].id == a.id
