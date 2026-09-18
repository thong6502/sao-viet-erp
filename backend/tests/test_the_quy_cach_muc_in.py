"""Thẻ quy cách ở bàn tổ mang khổ giấy nguyên · cách in · mực TỪNG MẶT (18/09/2026).

Trước đó thẻ chỉ có số đếm: LSX in 2 mặt AB (mặt A C-M-Y, mặt B K) xuống tổ thành "Số mặt: 2 ·
Số màu: 4" — thợ in không biết mặt nào chạy mực nào, khổ tờ in 0 × 0 thì mất luôn dòng khổ.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import _migrate_the_quy_cach_muc_in
from app.services.bai_ghep_service import BaiGhepService
from app.services.san_xuat.snapshot import the_quy_cach

_LENH_AB = {
    "giay_ten": "Giấy C300", "gsm": 300,
    "kho_nguyen_dai": 860, "kho_nguyen_rong": 650,
    "kho_in_dai": 0, "kho_in_rong": 0,
    "dai_thanh_pham": 86, "rong_thanh_pham": 54,
    "quy_cach_in": "hai_mat", "muc_a": ["c", "M ", "y"], "muc_b": ["K"],
}


def test_the_mang_kho_nguyen_cach_in_va_muc_tung_mat():
    the = the_quy_cach(_LENH_AB)
    assert the["kho_nguyen"] == "860 × 650"
    # 0 × 0 = in thẳng khổ giấy nguyên — khoá bỏ hẳn, câu chữ do UI nói (giống màn lệnh).
    assert "kho_in" not in the
    assert the["kho_tp"] == "86 × 54"
    assert the["cach_in"] == "hai_mat"
    assert the["muc_a"] == ["C", "M", "Y"] and the["muc_b"] == ["K"]


def test_lenh_cu_chi_co_so_mau_dung_luat_tap_muc_tu_so():
    the = the_quy_cach({"so_mau_a": 4, "so_mau_b": 1, "quy_cach_in": "hai_mat"})
    assert the["muc_a"] == ["K", "C", "M", "Y"] and the["muc_b"] == ["K"]


def test_khong_khai_muc_thi_khong_co_khoa_muc():
    the = the_quy_cach({"giay_ten": "Giấy C300", "quy_cach_in": "mot_mat"})
    assert "muc_a" not in the and "muc_b" not in the


def test_bai_ghep_mang_hop_tap_muc_cac_thanh_vien(monkeypatch):
    """Biến công thức của bài chỉ có số đếm; `quy_cach_bien_cua_bai` phải gắn thêm HỢP tập mực.

    Dựng bằng đối tượng giả: phần số tờ/khổ (`_qc_bien_bai`) không phải thứ đang soi."""
    a = SimpleNamespace(id=1, quy_cach_json={"muc_a": ["C", "M", "Y", "K"], "muc_b": []})
    b = SimpleNamespace(id=2, quy_cach_json={"muc_a": ["K", "185c"], "muc_b": ["K"]})
    bg = SimpleNamespace(kho_in_dai=640, kho_in_rong=450,
                         thanh_viens=[SimpleNamespace(lsx_id=1), SimpleNamespace(lsx_id=2)])
    svc = BaiGhepService(None, None, None, None)
    monkeypatch.setattr(svc, "_lsx_map", lambda _bg: {1: a, 2: b})
    monkeypatch.setattr(svc, "_qc_bien_bai", lambda _bg, _m: {"quy_cach_in": "hai_mat",
                                                              "kho_in_dai": 640, "kho_in_rong": 450})

    the = the_quy_cach(svc.quy_cach_bien_cua_bai(bg))
    assert the["muc_a"] == ["185C", "C", "K", "M", "Y"]
    assert the["muc_b"] == ["K"]
    assert the["kho_in"] == "640 × 450" and the["cach_in"] == "hai_mat"


# --- migration 0313 ---------------------------------------------------------------------------
def _fixture(cvs, lsxs, tvs=()):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE lsx (id INTEGER PRIMARY KEY, quy_cach_json JSON)"))
        cn.execute(text(
            "CREATE TABLE bai_ghep_thanh_vien (id INTEGER PRIMARY KEY, bai_ghep_id INTEGER, "
            "lsx_id INTEGER)"))
        cn.execute(text(
            "CREATE TABLE san_xuat_cong_viec (id INTEGER PRIMARY KEY, lsx_id INTEGER, "
            "bai_ghep_id INTEGER, quy_cach_json JSON)"))
        for i, qc in lsxs:
            cn.execute(text("INSERT INTO lsx VALUES (:i, :q)"),
                       {"i": i, "q": json.dumps(qc, ensure_ascii=False)})
        for i, bg_id, lsx_id in tvs:
            cn.execute(text("INSERT INTO bai_ghep_thanh_vien VALUES (:i, :b, :l)"),
                       {"i": i, "b": bg_id, "l": lsx_id})
        for i, lsx_id, bg_id, the in cvs:
            cn.execute(text("INSERT INTO san_xuat_cong_viec VALUES (:i, :l, :b, :q)"),
                       {"i": i, "l": lsx_id, "b": bg_id,
                        "q": None if the is None else json.dumps(the, ensure_ascii=False)})
    return engine


def _the(engine) -> dict[int, dict | None]:
    with engine.begin() as cn:
        return {r[0]: (json.loads(r[1]) if r[1] else None) for r in cn.execute(text(
            "SELECT id, quy_cach_json FROM san_xuat_cong_viec")).all()}


def _run(engine) -> None:
    with Session(engine) as s:
        _migrate_the_quy_cach_muc_in(s)


def test_migration_them_khoa_moi_khong_dung_khoa_cu_va_bo_qua_the_null():
    cu = {"giay": "Giấy C300", "so_mat": 2.0, "so_mau": 4.0, "so_kem": 4.0}
    engine = _fixture(
        cvs=[
            (1, 10, None, cu),                   # lệnh thường
            (2, 10, None, None),                 # thẻ NULL (trước mg 0290) — để nguyên
            (3, None, 7, {"kho_in": "640 × 450"}),  # bài ghép
        ],
        lsxs=[
            (10, _LENH_AB),
            (11, {"kho_nguyen_dai": 790, "kho_nguyen_rong": 1090, "quy_cach_in": "tu_tro",
                  "muc_a": ["C", "M"], "muc_b": []}),
            (12, {"quy_cach_in": "hai_mat", "muc_a": ["Y", "K"], "muc_b": ["K"]}),
        ],
        tvs=[(1, 7, 11), (2, 7, 12)],
    )
    _run(engine)
    t = _the(engine)

    assert t[1] == {**cu, "kho_nguyen": "860 × 650", "cach_in": "hai_mat",
                    "muc_a": ["C", "M", "Y"], "muc_b": ["K"]}
    assert t[2] is None
    # Bài: khổ nguyên + cách in lấy thành viên ĐẦU có khai, mực là HỢP.
    assert t[3] == {"kho_in": "640 × 450", "kho_nguyen": "790 × 1090", "cach_in": "tu_tro",
                    "muc_a": ["C", "K", "M", "Y"], "muc_b": ["K"]}

    _run(engine)  # idempotent
    assert _the(engine) == t
