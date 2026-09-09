"""mg `0286`: đổi tên biến công thức `so_tp` → `so_con` trong DỮ LIỆU đã lưu.

Đổi tên biến ở `bien_cong_thuc._BANG` là việc một dòng; cái đáng canh là công thức người ta ĐÃ GÕ
và lệnh ĐÃ PHÁT. Bỏ sót một cột thì công thức đó mất biến, mà `_thieu_bien` coi biến vắng như 0 —
tiền/giờ tụt về 0 IM LẶNG, không lỗi nào nổ.

Hai loại chỗ, test theo đúng hai loại: 11 cột CHỮ của danh mục, và 3 bảng ôm `khoan_json` (ảnh
chụp đầu việc ghim vào bước — lệnh đã phát cố ý không đọc-sống danh mục nữa).

Khuôn lấy từ `test_migration_0282_thanh_pham_don_vi_ma.py`.
"""
from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_migrations import MIGRATIONS, _migrate_doi_bien_so_tp_ve_so_con

#: (bảng, cột) — đúng bộ mà migration đi qua. Khai lại ở đây CỐ Ý: đây là bản kê độc lập, sửa
#: migration mà quên bảng nào thì test dưới đỏ chứ không im theo.
COT_CHU = [
    ("cong_doan", "cong_thuc_san_luong"),
    ("cong_doan", "cong_thuc_gia"),
    ("cong_doan_dau_viec", "cong_thuc_khoan"),
    ("cong_doan_dau_viec", "cong_thuc_gio"),
    ("cong_doan_dau_viec_vat_tu", "cong_thuc_luong"),
    ("cong_doan_may", "cong_thuc_gio"),
    ("cong_doan_may", "cong_thuc_gia"),
    ("giay_nguyen", "cong_thuc_gia"),
    ("giay_nguyen", "cong_thuc_luong"),
    ("vat_tu_in_an", "cong_thuc_gia"),
    ("don_vi_quy_doi", "cong_thuc"),
]

BANG_SNAP = ["lsx_cong_doan", "bai_ghep_cong_doan", "san_xuat_cong_viec"]


def _engine(*, cot_chu=COT_CHU, bang_snap=BANG_SNAP):
    """DB tí hon: mỗi bảng đúng những cột migration đụng tới, không hơn."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    theo_bang: dict[str, list[str]] = {}
    for bang, cot in cot_chu:
        theo_bang.setdefault(bang, []).append(cot)
    with engine.begin() as cn:
        for bang, cots in theo_bang.items():
            cn.execute(text(
                f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, "
                + ", ".join(f"{c} TEXT" for c in cots) + ")"
            ))
        for bang in bang_snap:
            cn.execute(text(f"CREATE TABLE {bang} (id INTEGER PRIMARY KEY, khoan_json TEXT)"))
    return engine


def _chay(engine) -> None:
    with Session(engine) as db:
        _migrate_doi_bien_so_tp_ve_so_con(db)


def _doc(engine, bang: str, cot: str, rid: int = 1):
    with engine.begin() as cn:
        return cn.execute(text(f"SELECT {cot} FROM {bang} WHERE id = :i"), {"i": rid}).scalar()


def _ghi(engine, bang: str, cot: str, gia_tri, rid: int = 1) -> None:
    with engine.begin() as cn:
        cn.execute(text(f"INSERT INTO {bang} (id, {cot}) VALUES (:i, :v)"),
                   {"i": rid, "v": gia_tri})


def test_moi_cot_chu_deu_duoc_viet_lai():
    """⭐ Bỏ sót một cột là công thức đó ra 0đ mà không báo gì — nên soi CẢ MƯỜI MỘT."""
    engine = _engine()
    for i, (bang, cot) in enumerate(COT_CHU, start=1):
        _ghi(engine, bang, cot, "sl_vao * so_tp * don_gia_khoan", rid=i)
    _chay(engine)
    for i, (bang, cot) in enumerate(COT_CHU, start=1):
        assert _doc(engine, bang, cot, rid=i) == "sl_vao * so_con * don_gia_khoan", \
            f"{bang}.{cot} chưa được viết lại"


def test_KHONG_dung_toi_so_tp_ra():
    """`so_tp_ra` là số thành phẩm ra ở CUỐI chuỗi — khái niệm khác, vẫn giữ tên. Thay bằng
    `str.replace` thẳng là nó thành `so_con_ra`, một biến không tồn tại."""
    engine = _engine()
    _ghi(engine, "cong_doan", "cong_thuc_gia", "so_tp_ra + so_tp + so_tp_ra")
    _chay(engine)
    assert _doc(engine, "cong_doan", "cong_thuc_gia") == "so_tp_ra + so_con + so_tp_ra"


def test_giu_nguyen_cong_thuc_khong_dinh_bien():
    engine = _engine()
    _ghi(engine, "don_vi_quy_doi", "cong_thuc", "sl_vao / so_trang")
    _ghi(engine, "cong_doan", "cong_thuc_gia", None, rid=2)
    _chay(engine)
    assert _doc(engine, "don_vi_quy_doi", "cong_thuc") == "sl_vao / so_trang"
    assert _doc(engine, "cong_doan", "cong_thuc_gia", rid=2) is None


def test_anh_chup_khoan_json_cua_ca_ba_bang():
    """Lệnh đã phát ghim công thức vào `khoan_json` và KHÔNG đọc-sống danh mục nữa — không viết
    lại ảnh chụp thì đúng những lệnh đang chạy mới là thứ hỏng."""
    engine = _engine()
    snap = {"rate_id": 7, "ten": "Bế tay", "don_gia": 250,
            "cong_thuc": "sl_vao * so_tp", "cong_thuc_gio": "sl_vao * so_tp / 2"}
    for bang in BANG_SNAP:
        _ghi(engine, bang, "khoan_json", json.dumps(snap, ensure_ascii=False))
    _chay(engine)
    for bang in BANG_SNAP:
        moi = json.loads(_doc(engine, bang, "khoan_json"))
        assert moi["cong_thuc"] == "sl_vao * so_con"
        assert moi["cong_thuc_gio"] == "sl_vao * so_con / 2"
        # Các khoá khác của ảnh chụp phải nguyên vẹn — nó là chứng từ, không phải bản nháp.
        assert moi["rate_id"] == 7 and moi["ten"] == "Bế tay" and moi["don_gia"] == 250


def test_khoan_json_khong_co_cong_thuc_thi_de_yen():
    """Khoá `cong_thuc` VẮNG khi đầu việc không khai công thức riêng (xem `khoan_snapshot`) —
    migration không được tự đẻ khoá."""
    engine = _engine()
    _ghi(engine, "lsx_cong_doan", "khoan_json", json.dumps({"rate_id": 1, "don_gia": 100}))
    _chay(engine)
    assert json.loads(_doc(engine, "lsx_cong_doan", "khoan_json")) == {"rate_id": 1, "don_gia": 100}


def test_thieu_bang_thi_bo_qua():
    """DB cũ chưa có `bai_ghep_cong_doan`/`san_xuat_cong_viec` vẫn phải chạy trót lọt."""
    engine = _engine(cot_chu=[("cong_doan", "cong_thuc_gia")], bang_snap=[])
    _ghi(engine, "cong_doan", "cong_thuc_gia", "so_tp * 2")
    _chay(engine)
    assert _doc(engine, "cong_doan", "cong_thuc_gia") == "so_con * 2"


def test_chay_lai_khong_doi_them():
    engine = _engine()
    _ghi(engine, "cong_doan", "cong_thuc_gia", "so_tp * 2")
    _ghi(engine, "lsx_cong_doan", "khoan_json", json.dumps({"cong_thuc": "so_tp"}))
    _chay(engine)
    _chay(engine)                      # idempotent
    assert _doc(engine, "cong_doan", "cong_thuc_gia") == "so_con * 2"
    assert json.loads(_doc(engine, "lsx_cong_doan", "khoan_json"))["cong_thuc"] == "so_con"


def test_dang_ky_dung_mot_lan_dung_thu_tu():
    """Chạy SAU `0285`. Không neo vào "phần tử cuối" vì phiên khác có thể nối mg mới lên sau."""
    ten = [m[0] for m in MIGRATIONS]
    assert ten.count("0286_doi_bien_so_tp_ve_so_con") == 1
    assert ten.index("0286_doi_bien_so_tp_ve_so_con") > ten.index(
        "0285_kcs_tieu_chi_thuoc_mot_cong_doan")
