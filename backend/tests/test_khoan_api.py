"""Thưởng/phạt TỔ TRƯỞNG: KHOẢNG SẢN LƯỢNG × tỷ lệ hàng lỗi (module `luong` nhịp 2).

Tiền khoán vào bảng lương = Phiếu sản lượng theo người (xem test_san_luong_api). Không còn "sổ khoán".
Bảng ĐƠN GIÁ khoán nay là danh mục — xem `test_cong_viec_khoan.py`.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.piece_work_repo import PieceWorkRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# --- Đơn giá khoán: TEST CHUYỂN ĐI -------------------------------------------
#
# 13 test CRUD/đơn vị/mã tự sinh của bảng `piece_rates` chuyển sang `test_cong_viec_khoan.py` ngày
# 17/08/2026, cùng lúc 5 route `/api/luong/khoan/rates|units` bị gỡ: bảng đó nay là danh mục "Công
# việc khoán" (`/api/cong-viec-khoan`). Giữ lại ở đây thì test gọi một API không còn tồn tại.
#
# File này còn: THƯỞNG/PHẠT tổ trưởng — lưới hai chiều khoảng sản lượng × tỷ lệ lỗi.


# --- Lưới thưởng/phạt tổ trưởng (chủ 04/09/2026) -----------------------------
# Chủ: *"nó phải sét 2 điều kiện 1 là khoảng sản lượng, 2 là tỷ lệ lỗi"*, và tiền =
# *"tổng sản lượng của lệnh sản xuất tổ đó làm được nhân % sau đó kết hợp với đơn giá khoán"*.


_DEPT = 4242


def _set_brackets(client, token, items, dept=_DEPT, expect=200):
    r = client.put("/api/luong/khoan/leader-brackets",
                   json={"department_id": dept, "items": items},
                   headers=_h(token))
    assert r.status_code == expect, r.text
    return r


def _get_brackets(client, token, dept=_DEPT):
    r = client.get(f"/api/luong/khoan/leader-brackets?department_id={dept}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _o(tu, den, loi, rate):
    return {"sl_tu": tu, "sl_den": den, "up_to_defect_pct": loi, "rate_pct": rate}


def _luoi():
    """Đúng ví dụ chủ nêu: ba khoảng sản lượng, mỗi khoảng vài mốc lỗi."""
    return [
        _o(0, 5000, 5, 5),
        _o(0, 5000, None, -5),
        _o(5000, 10000, 3, 7),
        _o(5000, 10000, 20, -8),
        _o(5000, 10000, None, -15),
        _o(10000, None, 3, 10),
        _o(10000, None, None, -15),
    ]


def _doc_lai(client, token, items=None, dept=_DEPT):
    """Khai lưới rồi đọc lại ĐỐI TƯỢNG ORM — hàm tra nhận model, không nhận dict."""
    _set_brackets(client, token, items if items is not None else _luoi(), dept=dept)
    db = SessionLocal()
    try:
        return PieceWorkRepository(db).list_leader_brackets(dept)
    finally:
        db.close()


def test_luoi_luu_va_doc_lai(client):
    token = _admin_token(client)
    _set_brackets(client, token, _luoi())
    got = _get_brackets(client, token)
    assert [b["seq"] for b in got] == [1, 2, 3, 4, 5, 6, 7]
    assert [b["sl_tu"] for b in got] == [0, 0, 5000, 5000, 5000, 10000, 10000]
    assert [b["sl_den"] for b in got] == [5000, 5000, 10000, 10000, 10000, None, None]
    assert [b["up_to_defect_pct"] for b in got] == [5, None, 3, 20, None, 3, None]
    assert [b["rate_pct"] for b in got] == [5, -5, 7, -8, -15, 10, -15]


def test_tra_dung_RANH_GIOI_san_luong(client):
    """⭐ Khoảng nửa mở `sl_tu < SL ≤ sl_den` — ĐÚNG quy ước bậc số lượng của `bu_hao_engine`.

    Sản lượng đúng 5.000 phải còn thuộc khoảng 0–5.000; lệch một chỗ là nhảy sang khoảng khác,
    ra một mức % khác hẳn mà nhìn bảng lương không thấy gì bất thường."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client))

    assert S.leader_bonus_pct(5_000, 3, bs) == 5, "đúng 5.000 vẫn thuộc khoảng 0–5.000"
    assert S.leader_bonus_pct(5_000.01, 3, bs) == 7, "vượt 5.000 là sang khoảng sau"
    assert S.leader_bonus_pct(10_000, 3, bs) == 7, "đúng 10.000 vẫn thuộc khoảng 5.000–10.000"
    assert S.leader_bonus_pct(10_000.01, 3, bs) == 10


def test_tra_dung_RANH_GIOI_ty_le_loi(client):
    """⭐ Trong một khoảng sản lượng: dòng ĐẦU TIÊN có `lỗi ≤ trần` thắng, nên đúng 3,00% vẫn
    thuộc dòng "≤3%"."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client))

    assert S.leader_bonus_pct(8_000, 0, bs) == 7
    assert S.leader_bonus_pct(8_000, 3, bs) == 7, "đúng 3% phải còn thuộc dòng ≤3%"
    assert S.leader_bonus_pct(8_000, 3.01, bs) == -8
    assert S.leader_bonus_pct(8_000, 20, bs) == -8, "đúng 20% phải còn thuộc dòng ≤20%"
    assert S.leader_bonus_pct(8_000, 20.01, bs) == -15
    assert S.leader_bonus_pct(8_000, 99, bs) == -15


def test_ra_tien_dung_CONG_THUC_va_dung_dau(client):
    """⭐ Tiền = sản lượng × % × đơn giá khoán. Dương = thưởng, âm = PHẠT.

    Đúng hai con số chủ nêu: lệnh 5.000 sản phẩm đơn giá 300đ lỗi 3% ⇒ +75.000đ; lệnh 8.000 lỗi
    20% ⇒ −192.000đ. Nhân trên TỔNG sản lượng, KHÔNG trừ hàng lỗi (*"nhân trên 5000 chứ"*)."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client))

    assert S.leader_bonus_amount(san_luong=5_000, don_gia_khoan=300,
                                 defect_pct=3, brackets=bs) == 75_000
    assert S.leader_bonus_amount(san_luong=8_000, don_gia_khoan=300,
                                 defect_pct=20, brackets=bs) == -192_000
    # Chưa khai lưới ⇒ không thưởng không phạt (KHÔNG được đoán bừa).
    assert S.leader_bonus_amount(san_luong=5_000, don_gia_khoan=300,
                                 defect_pct=50, brackets=[]) == 0


def test_CHUA_BIET_san_luong_thi_khong_thuong_khong_phat(client):
    """⭐ Fail-closed có chủ ý: chưa xác nhận được tổ làm bao nhiêu thì không phát thưởng, cũng
    không phạt. Thừa kế đúng tinh thần cửa ngưỡng cũ (đã gỡ cùng mg `0262`)."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client))

    assert S.leader_bonus_pct(None, 0, bs) == 0
    assert S.leader_bonus_amount(san_luong=None, don_gia_khoan=300,
                                 defect_pct=0, brackets=bs) == 0


def test_san_luong_KHONG_ROI_khoang_nao_thi_ra_0(client):
    """Sản lượng 0 (tổ chưa làm được gì) không rơi vào khoảng nào vì `sl_tu < SL` là NGẶT.

    Đây chính là chỗ cửa chặn `min_output_qty` cũ từng lo: làm quá ít thì tỷ lệ lỗi vô nghĩa —
    hỏng 2 tờ trên 20 tờ đã là 10%. Nay khoảng thấp nhất khai 0% là gánh đúng việc đó."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client))

    assert S.leader_bonus_pct(0, 0, bs) == 0
    assert S.leader_bonus_amount(san_luong=0, don_gia_khoan=300, defect_pct=0, brackets=bs) == 0


def test_khoang_thap_nhat_khai_0_pt_thay_duoc_cua_chan_cu(client):
    """Lệnh nhỏ không thưởng không phạt = khai khoảng 0–5.000 với 0%, ngay trong bảng đang nhìn."""
    from app.services.piece_work_service import PieceWorkService as S

    bs = _doc_lai(client, _admin_token(client), items=[
        _o(0, 5000, None, 0),
        _o(5000, None, 5, 5),
        _o(5000, None, None, -5),
    ])

    for loi in (0, 3, 20, 50):
        assert S.leader_bonus_amount(san_luong=4_999, don_gia_khoan=300,
                                     defect_pct=loi, brackets=bs) == 0, \
            f"lệnh nhỏ mà vẫn ra tiền ở mức lỗi {loi}%"
    assert S.leader_bonus_amount(san_luong=6_000, don_gia_khoan=300,
                                 defect_pct=3, brackets=bs) == 90_000


def test_moi_to_mot_luoi_rieng(client):
    """Lưới của tổ này không được rò sang tổ khác."""
    token = _admin_token(client)
    _set_brackets(client, token, _luoi())
    _set_brackets(client, token, [_o(0, None, None, 1)], dept=_DEPT + 1)

    assert len(_get_brackets(client, token, _DEPT)) == 7
    assert len(_get_brackets(client, token, _DEPT + 1)) == 1


def test_bo_rong_la_hop_le(client):
    """Xoá sạch = "tổ này không áp thưởng/phạt tổ trưởng"."""
    token = _admin_token(client)
    _set_brackets(client, token, _luoi())
    _set_brackets(client, token, [])
    assert _get_brackets(client, token) == []


# --- Validate: bảng hỏng thì hàm tra rơi vào bậc SAI ⇒ sai tiền thật của người ta ---


def test_chan_khoang_dau_khong_bat_dau_tu_0(client):
    token = _admin_token(client)
    _set_brackets(client, token, [_o(100, None, None, 5)], expect=400)


def test_chan_khoang_bi_HO(client):
    """0–5.000 rồi nhảy sang 6.000: lệnh sản lượng 5.500 không rơi vào dòng nào."""
    token = _admin_token(client)
    _set_brackets(client, token, [
        _o(0, 5000, None, 5),
        _o(6000, None, None, -5),
    ], expect=400)


def test_chan_khoang_CUOI_khong_de_trong(client):
    """Thiếu khoảng ∞ thì lệnh lớn hơn mọi khoảng không được thưởng cũng không bị phạt."""
    token = _admin_token(client)
    _set_brackets(client, token, [_o(0, 5000, None, 5)], expect=400)


def test_chan_khoang_vo_cuc_nam_GIUA_bang(client):
    token = _admin_token(client)
    _set_brackets(client, token, [
        _o(0, None, None, 5),
        _o(5000, None, None, -5),
    ], expect=400)


def test_chan_khoang_thieu_dong_TRO_LEN(client):
    """Mỗi khoảng sản lượng phải có đúng MỘT dòng để trống ô tỷ lệ lỗi."""
    token = _admin_token(client)
    _set_brackets(client, token, [
        _o(0, 5000, 5, 5),
        _o(5000, None, None, -5),
    ], expect=400)


def test_chan_ty_le_loi_khong_tang_dan_trong_mot_khoang(client):
    token = _admin_token(client)
    _set_brackets(client, token, [
        _o(0, None, 20, 5),
        _o(0, None, 5, 0),
        _o(0, None, None, -5),
    ], expect=400)


def test_chan_den_SL_nho_hon_tu_SL(client):
    token = _admin_token(client)
    _set_brackets(client, token, [_o(5000, 1000, None, 5)], expect=400)
