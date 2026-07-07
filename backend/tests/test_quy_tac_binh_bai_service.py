"""Test service Quy tắc bình bài — version-chain, integrity §12, preview (nối engine §6).

DB in-memory chỉ bind các bảng cần (header+version+folding + users/audit làm FK target).
Không phụ thuộc registry toàn cục (chạy độc lập ở pha xây, chưa wiring)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
# Import models để đăng ký bảng lên Base.metadata cho create_all.
from app.models.quy_tac_binh_bai import QuyTacBinhBai, QuyTacBinhBaiVersion, FoldingScheme  # noqa: F401
from app.models.user import User  # noqa: F401  (FK created_by)
from app.models.audit import AuditLog  # noqa: F401  (audit.create)
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.quy_tac_binh_bai_repo import QuyTacBinhBaiRepository
from app.services.quy_tac_binh_bai_service import (
    DuplicateError,
    QuyTacBinhBaiService,
    ValidationError,
)


class _Actor:
    id = None  # created_by nullable; SQLite test không ép FK


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return QuyTacBinhBaiService(QuyTacBinhBaiRepository(db), AuditLogRepository(db)), db


def _payload(ma="PHANG-NUP", ten="Ấn phẩm phẳng", **cfg):
    base = {"layout_mode": "step_repeat", "gutter_mm": 4, "side_margin_mm": 5, "tail_colorbar_mm": 8}
    base.update(cfg)
    return {"ma": ma, "ten": ten, "mo_ta": None, "config": base}


# ---------- version-chain ----------
def test_create_spawns_v1_current():
    svc, _ = _svc()
    h = svc.create_item(_payload(), actor=_Actor())
    assert h.ma == "PHANG-NUP"
    cur = svc.current_version(h.id)
    assert cur is not None and cur.version_no == 1 and cur.is_current is True
    assert svc.version_count(h.id) == 1


def test_edit_config_spawns_new_version_old_frozen():
    svc, _ = _svc()
    h = svc.create_item(_payload(), actor=_Actor())
    v1 = svc.current_version(h.id)
    assert float(v1.gutter_mm) == 4
    # sửa cấu hình → v2 is_current, v1 khoá
    svc.create_version(h.id, {"config": {**_payload()["config"], "gutter_mm": 8},
                              "ghi_chu_version": "giãn gutter"}, actor=_Actor())
    cur = svc.current_version(h.id)
    assert cur.version_no == 2 and cur.is_current is True
    assert float(cur.gutter_mm) == 8
    versions = svc.versions_of(h.id)
    assert len(versions) == 2
    old = next(v for v in versions if v.version_no == 1)
    assert old.is_current is False        # v1 hết hiện hành
    assert float(old.gutter_mm) == 4      # v1 giữ nguyên số cũ (immutable)


def test_exactly_one_current_per_rule():
    svc, _ = _svc()
    h = svc.create_item(_payload(), actor=_Actor())
    for i in range(3):
        svc.create_version(h.id, {"config": _payload()["config"]}, actor=_Actor())
    currents = [v for v in svc.versions_of(h.id) if v.is_current]
    assert len(currents) == 1
    assert currents[0].version_no == 4     # v1 + 3 lần sửa


# ---------- integrity ----------
def test_ma_uppercased_and_unique():
    svc, _ = _svc()
    svc.create_item(_payload(ma="phang-nup"), actor=_Actor())
    h = svc.list_items()[0][0]
    assert h.ma == "PHANG-NUP"
    with pytest.raises(DuplicateError):
        svc.create_item(_payload(ma="PHANG-NUP"), actor=_Actor())


def test_invalid_layout_mode_rejected():
    svc, _ = _svc()
    with pytest.raises(ValidationError):
        svc.create_item(_payload(layout_mode="bogus"), actor=_Actor())


def test_pages_per_sig_must_be_valid():
    svc, _ = _svc()
    with pytest.raises(ValidationError):
        svc.create_item(_payload(ma="S1", layout_mode="signature", pages_per_sig=7), actor=_Actor())


def test_update_header_keeps_ma_immutable():
    svc, _ = _svc()
    h = svc.create_item(_payload(), actor=_Actor())
    svc.update_header(h.id, {"ten": "Tên mới", "mo_ta": "x", "trang_thai": "inactive"}, actor=_Actor())
    h2 = svc.get_header(h.id)
    assert h2.ten == "Tên mới" and h2.trang_thai == "inactive"
    assert h2.ma == "PHANG-NUP"   # ma không đổi (schema update không có field ma)


def test_delete_removes_header_and_versions():
    svc, db = _svc()
    h = svc.create_item(_payload(), actor=_Actor())
    svc.create_version(h.id, {"config": _payload()["config"]}, actor=_Actor())
    rid = h.id
    svc.delete_item(rule_id=rid, actor=_Actor())
    assert svc.repo.get_header(rid) is None
    assert svc.versions_of(rid) == []


# ---------- preview (nối engine) ----------
def test_preview_step_repeat_golden():
    svc, _ = _svc()
    bench = {
        "rong_tp": 90, "dai_tp": 53, "bleed_mm": 2,
        "rong_ng": 430, "dai_ng": 650, "gsm": 150, "gia_kg": 30000,
        "gripper_mm": 12, "max_w": 0, "max_h": 0,
        "so_luong": 10000, "so_mau_truoc": 4, "so_mau_sau": 4,
    }
    config = {"layout_mode": "step_repeat", "side_margin_mm": 5, "tail_colorbar_mm": 8,
              "gutter_mm": 4, "allow_rotate": True, "bleed_default_mm": 3}
    out = svc.preview(config, bench)
    assert out["don_vi_per_to_in"] == 40
    assert out["so_to_in"] == 250       # ceil(10000/40)
    assert out["so_kem"] == 8           # 4 trước + 4 sau
    assert not any(w["severity"] == "error" for w in out["warnings"])


def test_preview_efit0_surfaces_error():
    svc, _ = _svc()
    bench = {"rong_tp": 500, "dai_tp": 700, "rong_ng": 430, "dai_ng": 650, "gripper_mm": 12}
    out = svc.preview({"layout_mode": "step_repeat"}, bench)
    assert out["don_vi_per_to_in"] == 0
    assert any(w["code"] == "E-FIT-0" for w in out["warnings"])
