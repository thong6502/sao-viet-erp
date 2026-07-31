"""Đơn giá khoán (module `luong` nhịp 2): CRUD bảng giá tra khi ghi Phiếu sản lượng.

Tiền khoán vào bảng lương = Phiếu sản lượng theo người (xem test_san_luong_api). Không còn "sổ khoán".
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.piece_work_repo import PieceWorkRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_rate_crud(client):
    token = _admin_token(client)
    r = client.post("/api/luong/khoan/rates", json={
        "group_name": "to_boi", "name": "Bồi 3 lớp", "unit": "m2", "unit_price": 170,
    }, headers=_h(token))
    assert r.status_code == 201
    rid = r.json()["id"]
    assert any(x["id"] == rid for x in client.get("/api/luong/khoan/rates", headers=_h(token)).json()["items"])
    upd = client.put(f"/api/luong/khoan/rates/{rid}", json={
        "group_name": "to_boi", "name": "Bồi 3 lớp", "unit": "m2", "unit_price": 180,
    }, headers=_h(token))
    assert upd.json()["unit_price"] == 180
    assert client.delete(f"/api/luong/khoan/rates/{rid}", headers=_h(token)).status_code == 204


def test_rate_scoped_by_department(client):
    """Đơn giá gắn `department_id` (khai trong Cấu hình lương của tổ) → GET lọc đúng theo tổ."""
    token = _admin_token(client)
    a = client.post("/api/luong/khoan/rates", json={
        "group_name": "Tổ Bế", "department_id": 101, "name": "Dán bìa các tông",
        "unit": "to", "unit_price": 170,
    }, headers=_h(token)).json()
    b = client.post("/api/luong/khoan/rates", json={
        "group_name": "Tổ Bồi", "department_id": 202, "name": "Bồi carton 3 lớp",
        "unit": "m2", "unit_price": 200,
    }, headers=_h(token)).json()
    assert a["department_id"] == 101 and b["department_id"] == 202
    # Lọc theo tổ 101 → chỉ đơn giá của tổ đó.
    only = client.get("/api/luong/khoan/rates?department_id=101", headers=_h(token)).json()["items"]
    ids = {x["id"] for x in only}
    assert a["id"] in ids and b["id"] not in ids
    assert all(x["department_id"] == 101 for x in only)
    # Không lọc → thấy cả hai.
    all_ids = {x["id"] for x in client.get("/api/luong/khoan/rates", headers=_h(token)).json()["items"]}
    assert a["id"] in all_ids and b["id"] in all_ids


# --- Ô "Đơn vị" ---------------------------------------------------------------
# 2026-07-31: màn khai CHỌN từ danh mục `Đơn vị & quy đổi` (lệch một chữ là lệnh không quy đổi ra
# tiền được). Nhưng API vẫn NHẬN chữ bất kỳ — dòng cũ, seed và import đều đang mang đơn vị ngoài
# danh mục; chặn ở API là khoá luôn đường sửa những dòng đó.


def _mk(client, token, **over):
    body = {"group_name": "to_test_unit", "name": "Việc test đơn vị", "unit_price": 100}
    body.update(over)
    return client.post("/api/luong/khoan/rates", json=body, headers=_h(token))


def test_don_vi_go_tu_do_luu_duoc(client):
    """⭐ Đơn vị NGOÀI danh sách gợi ý vẫn lưu bình thường — đây là cả điểm của thay đổi."""
    token = _admin_token(client)
    r = _mk(client, token, unit="mét tới")
    assert r.status_code == 201, r.text
    assert r.json()["unit"] == "mét tới"


def test_don_vi_luu_dung_chu_nhan_duoc(client):
    """⭐ Lưu ĐÚNG chữ nhận được, chỉ cắt khoảng trắng thừa.

    Bản trước còn "chuẩn hoá" ngầm: gõ "KG" khi đã có "kg" thì server âm thầm đổi thành "kg". Có
    lý khi ô đơn vị gõ tự do, nhưng chủ chốt 2026-07-31 — đơn vị CHỌN TỪ danh mục Đơn vị & quy đổi
    và màn khai báo không được sửa chữ của người ta sau lưng."""
    token = _admin_token(client)
    assert _mk(client, token, unit="kg").json()["unit"] == "kg"
    assert _mk(client, token, unit="  KG ").json()["unit"] == "KG"


def test_don_vi_khong_gop_theo_dau(client):
    """CỐ Ý không bỏ dấu để gộp: "to" và "tờ" là hai đơn vị khác nhau."""
    token = _admin_token(client)
    assert _mk(client, token, unit="tờ").json()["unit"] == "tờ"
    assert _mk(client, token, unit="to").json()["unit"] == "to"


def test_don_vi_bo_trong_thanh_khac(client):
    token = _admin_token(client)
    assert _mk(client, token, unit="").json()["unit"] == "khác"
    assert _mk(client, token, unit="   ").json()["unit"] == "khác"


def test_don_vi_dai_24_ky_tu(client):
    """12 ký tự cũ vừa khít "thùng carton" là hỏng ⇒ đã nới 24."""
    token = _admin_token(client)
    assert _mk(client, token, unit="thùng carton loại to").status_code == 201
    assert _mk(client, token, unit="x" * 25).status_code == 422


def test_don_vi_chon_duoc_la_danh_muc_don_vi(client):
    """Danh sách đơn vị = danh mục `Đơn vị & quy đổi`, KHÔNG mọc thêm từ dữ liệu đã dùng.

    Bản trước nối cả hai nguồn nên danh sách đôi nhau từng cặp (`m2`/`m²`, `hop`/`hộp`) — dòng cũ
    lưu MÃ còn danh mục hiện TÊN, nhìn như hai đơn vị khác nhau."""
    token = _admin_token(client)
    truoc = client.get("/api/luong/khoan/units", headers=_h(token)).json()["items"]
    assert "m²" in truoc, "danh mục đơn vị chưa được seed"
    assert len(truoc) == len(set(truoc)), "danh sách đơn vị bị trùng"

    _mk(client, token, unit="ram giấy")
    sau = client.get("/api/luong/khoan/units", headers=_h(token)).json()["items"]
    assert sau == truoc, "đơn vị gõ ngoài danh mục không được chui vào danh sách chọn"


def test_sua_don_gia_giu_nguyen_chu_don_vi(client):
    """Đường SỬA cũng chỉ cắt khoảng trắng, không đổi chữ."""
    token = _admin_token(client)
    rid = _mk(client, token, unit="bộ").json()["id"]
    upd = client.put(f"/api/luong/khoan/rates/{rid}", json={
        "group_name": "to_test_unit", "name": "Việc test đơn vị",
        "unit": " BỘ ", "unit_price": 100,
    }, headers=_h(token))
    assert upd.status_code == 200, upd.text
    assert upd.json()["unit"] == "BỘ"


def test_ma_tu_sinh_khi_bo_trong(client):
    """Chủ chốt: không cho nhập mã, máy sinh KH-####."""
    token = _admin_token(client)
    ma = _mk(client, token, unit="kg").json()["code"]
    assert ma and ma.startswith("KH-")


# --- Bậc thưởng/phạt tổ trưởng theo tỷ lệ hàng lỗi (chủ 29/07/2026) ---------
# "Hàng lỗi khoảng 5% thì thưởng 2% trên tổng, lỗi trên 10% thì bị trừ 10% trên tổng.
#  % này là tiền đó nha."


_DEPT = 4242


def _set_brackets(client, token, items, dept=_DEPT, expect=200, min_output_qty=0):
    r = client.put("/api/luong/khoan/leader-brackets",
                   json={"department_id": dept, "items": items,
                         "min_output_qty": min_output_qty},
                   headers=_h(token))
    assert r.status_code == expect, r.text
    return r


def _get_brackets(client, token, dept=_DEPT):
    r = client.get(f"/api/luong/khoan/leader-brackets?department_id={dept}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _get_nguong(client, token, dept=_DEPT) -> float:
    r = client.get(f"/api/luong/khoan/leader-brackets?department_id={dept}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["min_output_qty"]


def _bo_moc_chuan():
    """Đúng ví dụ chủ nêu: ≤5% thưởng 2% · ≤10% hòa · trên 10% phạt 10%."""
    return [
        {"up_to_defect_pct": 5, "rate_pct": 2},
        {"up_to_defect_pct": 10, "rate_pct": 0},
        {"up_to_defect_pct": None, "rate_pct": -10},
    ]


def test_moc_to_truong_luu_va_doc_lai(client):
    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan())
    got = _get_brackets(client, token)
    assert [b["seq"] for b in got] == [1, 2, 3]
    assert [b["up_to_defect_pct"] for b in got] == [5, 10, None]
    assert [b["rate_pct"] for b in got] == [2, 0, -10]


def test_tra_dung_bac_o_RANH_GIOI(client):
    """⭐ Chỗ dễ sai nhất: `≤` hay `<` lệch một chỗ là trúng bậc khác ⇒ sai tiền.

    Bậc ĐẦU TIÊN có `tỷ lệ lỗi ≤ trần` thắng, nên đúng 5,00% vẫn thuộc bậc "≤5%"."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan())

    db = SessionLocal()
    try:
        bs = PieceWorkRepository(db).list_leader_brackets(_DEPT)
    finally:
        db.close()

    assert S.leader_bonus_pct(0, bs) == 2
    assert S.leader_bonus_pct(5, bs) == 2, "đúng 5% phải còn thuộc bậc ≤5%"
    assert S.leader_bonus_pct(5.01, bs) == 0
    assert S.leader_bonus_pct(10, bs) == 0, "đúng 10% phải còn thuộc bậc ≤10%"
    assert S.leader_bonus_pct(10.01, bs) == -10
    assert S.leader_bonus_pct(99, bs) == -10


def test_ra_tien_dung_dau(client):
    """⭐ Dương = thưởng, âm = PHẠT. Đảo dấu là đảo ngược hoàn toàn ý nghĩa."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan())
    db = SessionLocal()
    try:
        bs = PieceWorkRepository(db).list_leader_brackets(_DEPT)
    finally:
        db.close()

    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=3, brackets=bs) == 2_000_000
    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=20, brackets=bs) == -10_000_000
    # Chưa khai mốc ⇒ không thưởng không phạt (KHÔNG được đoán bừa).
    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=50, brackets=[]) == 0


# --- Ngưỡng tối thiểu để XÉT thưởng/phạt (chủ 30/07/2026) --------------------
# Chủ: *"ở đó mới có Tỷ lệ lỗi tới nhưng không biết nằm trong phạm vi sản lượng là bao nhiêu"*.
# Bảng bậc chỉ có một chiều là tỷ lệ lỗi ⇒ tổ làm rất ít và tổ làm rất nhiều bị đối xử như nhau.



def _bac(client, token, qty):
    """Khai bộ mốc chuẩn + ngưỡng sản lượng, trả về danh sách bậc đã đọc lại từ DB."""
    _set_brackets(client, token, _bo_moc_chuan(), min_output_qty=qty)
    db = SessionLocal()
    try:
        return PieceWorkRepository(db).list_leader_brackets(_DEPT)
    finally:
        db.close()


def test_DUOI_nguong_thi_khong_thuong_khong_phat_du_lo_bao_nhieu(client):
    """⭐ Lý do cửa chặn tồn tại: làm càng ít thì tỷ lệ lỗi càng vô nghĩa.

    Hỏng 2 tờ trên 20 tờ đã là 10% — đủ rơi xuống bậc phạt nặng nhất dù thực tế chẳng làm được gì.
    Phải chặn CẢ HAI đầu: không thưởng oan khi lỗi 0%, không phạt oan khi lỗi 50%."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    bs = _bac(client, token, qty=5_000)

    for loi in (0, 3, 20, 50):
        assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=loi, brackets=bs,
                                     san_luong=4_999, min_output_qty=5_000) == 0, \
            f"dưới ngưỡng mà vẫn ra tiền ở mức lỗi {loi}%"


def test_DUNG_BANG_nguong_thi_VAN_duoc_xet(client):
    """⭐ Ranh giới. Chủ khai "ít nhất X" ⇒ đúng X phải được xét (`>=`, KHÔNG phải `>`).

    Lệch một chỗ ở đây là cắt mất tiền thưởng của người ta, mà nhìn bảng lương không thấy gì bất
    thường — chỉ thấy số 0."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    bs = _bac(client, token, qty=5_000)

    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=3, brackets=bs,
                                 san_luong=4_999, min_output_qty=5_000) == 0
    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=3, brackets=bs,
                                 san_luong=5_000, min_output_qty=5_000) == 2_000_000, \
        "đúng bằng ngưỡng phải ĐƯỢC xét"


def test_CHUA_BIET_san_luong_thi_coi_nhu_duoi_nguong(client):
    """⭐ Fail-closed có chủ ý: chưa xác nhận được tổ đạt ngưỡng thì KHÔNG phát thưởng.

    Đây là trạng thái THẬT hôm nay — chưa có nguồn nhập sản lượng nào."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    bs = _bac(client, token, qty=5_000)

    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=0, brackets=bs,
                                 san_luong=None, min_output_qty=5_000) == 0
    # Nhưng KHÔNG khai ngưỡng thì chưa biết sản lượng vẫn xét bình thường — không gác là không gác.
    assert S.leader_bonus_amount(tong_khoan_to=100_000_000, defect_pct=0, brackets=bs,
                                 san_luong=None, min_output_qty=0) == 2_000_000


def test_khong_khai_nguong_thi_KHONG_GAC(client):
    """Bộ mốc đã khai từ trước (chưa có ngưỡng) phải giữ NGUYÊN hành vi cũ.

    Thêm cửa chặn mà vô tình bật mặc định là cả loạt tổ mất thưởng im lặng."""
    from app.services.piece_work_service import PieceWorkService as S

    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan())
    db = SessionLocal()
    try:
        bs = PieceWorkRepository(db).list_leader_brackets(_DEPT)
    finally:
        db.close()

    assert _get_nguong(client, token) == 0
    assert S.leader_bonus_amount(tong_khoan_to=1_000, defect_pct=3, brackets=bs) == 20


def test_nguong_luu_va_doc_lai_cung_goi_voi_bac(client):
    """Ngưỡng đi CÙNG GÓI với bậc: màn chỉ có một nút Lưu, tách ra là lưu được nửa này mất nửa kia."""
    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan(), min_output_qty=5_000)
    assert _get_nguong(client, token) == 5_000
    assert len(_get_brackets(client, token)) == 3, "lưu ngưỡng không được làm mất bậc"

    # Sửa lại: phải GHI ĐÈ, không đẻ dòng thứ hai (`department_id` là UNIQUE).
    _set_brackets(client, token, _bo_moc_chuan(), min_output_qty=200)
    assert _get_nguong(client, token) == 200


def test_moi_to_mot_nguong_rieng(client):
    """Ngưỡng của tổ này không được rò sang tổ khác — cùng luật với bộ mốc."""
    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan(), min_output_qty=5_000)
    _set_brackets(client, token, _bo_moc_chuan(), dept=_DEPT + 1, min_output_qty=800)

    assert _get_nguong(client, token, _DEPT) == 5_000
    assert _get_nguong(client, token, _DEPT + 1) == 800


def test_nguong_am_bi_chan(client):
    token = _admin_token(client)
    _set_brackets(client, token, _bo_moc_chuan(), min_output_qty=-1, expect=400)
