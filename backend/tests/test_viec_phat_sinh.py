"""Việc phát sinh của một công việc khoán (`cong_viec_khoan_phat_sinh`, 14/09/2026).

Chủ xưởng chốt thứ bậc: tổ → công đoạn → công việc khoán → VIỆC PHÁT SINH. Việc phát sinh chỉ khai
ba thứ — tên việc · đơn giá · đơn vị tính — vì tổ và công đoạn đã có ở công việc khoán cha. Đợt này
CHỈ khai báo và hiển thị trong danh mục; sản xuất chưa đọc tới.

Đi chung cửa `/api/cong-viec-khoan` (thân POST/PUT mang thêm `viec_phat_sinh`), nên quyền · nhật ký ·
nhân bản · xoá đều là của công việc khoán cha.

⚠️ DB test dùng chung cả phiên (xem `test_cong_viec_khoan.py`) ⇒ mọi bản ghi tiền tố `ZZ`.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.piece_work import ViecPhatSinh

ADMIN = {"username": "admin", "password": "admin123"}
API = "/api/cong-viec-khoan"


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _to_id(client, h) -> int:
    items = client.get("/api/cong-doan/phong-ban", headers=h).json()["items"]
    if items:
        return int(items[0]["id"])
    tao = client.post("/api/departments",
                      json={"name": "ZZ Tổ in", "la_san_xuat": True}, headers=h)
    assert tao.status_code == 201, tao.text
    return int(tao.json()["id"])


def _don_vi(client, h, ma: str, ten: str) -> str:
    r = client.post("/api/don-vi", json={"ma": ma, "ten": ten}, headers=h)
    assert r.status_code in (201, 409), r.text
    return ma


def _body(client, h, **over) -> dict:
    body = {
        "ten": "ZZ In 4 màu", "department_ids": [_to_id(client, h)], "unit": "to", "unit_price": 30,
        "viec_phat_sinh": [
            {"ten": "ZZ Thay kẽm", "don_gia": 100, "don_vi": _don_vi(client, h, "zzban", "ZZ Bản")},
            {"ten": "ZZ Rửa lô mực", "don_gia": 50, "don_vi": _don_vi(client, h, "zzlan", "ZZ Lần")},
        ],
    }
    body.update(over)
    return body


def _mk(client, h, **over):
    return client.post(API, json=_body(client, h, **over), headers=h)


def _gon(ds: list[dict]) -> list[tuple]:
    return [(v["ten"], v["don_gia"], v["don_vi"]) for v in ds]


# --- Khai + hiển thị -----------------------------------------------------------


def test_tao_kem_viec_phat_sinh_tra_du_o_ca_ba_cua(client):
    """Tạo · chi tiết · danh sách đều phải trả `viec_phat_sinh` — schema Out mà quên khai là Pydantic
    nuốt im lặng (bẫy đã dính nhiều lần ở màn này)."""
    h = _admin(client)
    tao = _mk(client, h)
    assert tao.status_code == 201, tao.text
    mong = [("ZZ Thay kẽm", 100, "zzban"), ("ZZ Rửa lô mực", 50, "zzlan")]
    assert _gon(tao.json()["viec_phat_sinh"]) == mong
    assert all(isinstance(v["id"], int) for v in tao.json()["viec_phat_sinh"])

    rid = tao.json()["id"]
    assert _gon(client.get(f"{API}/{rid}", headers=h).json()["viec_phat_sinh"]) == mong
    ds = client.get(f"{API}?q=ZZ In 4 màu", headers=h).json()["items"]
    assert ds and _gon(ds[0]["viec_phat_sinh"]) == mong


def test_khong_khai_viec_phat_sinh_thi_tra_danh_sach_rong(client):
    h = _admin(client)
    body = _body(client, h, ten="ZZ Bế tay")
    body.pop("viec_phat_sinh")
    tao = client.post(API, json=body, headers=h)
    assert tao.status_code == 201, tao.text
    assert tao.json()["viec_phat_sinh"] == []


def test_sua_giu_nguyen_id_cua_dong_cu(client):
    """Mỗi việc phát sinh có id riêng và GIỮ id qua các lần lưu — sau này sản xuất ghi số lượng trỏ
    vào id đó, đổi tên việc không được làm mồ côi các lần ghi cũ."""
    h = _admin(client)
    goc = _mk(client, h).json()
    thay_kem, rua_lo = goc["viec_phat_sinh"]

    body = _body(client, h, viec_phat_sinh=[
        {"id": thay_kem["id"], "ten": "ZZ Thay bản kẽm", "don_gia": 120, "don_vi": "zzban"},
        {"ten": "ZZ Lau máy", "don_gia": 80, "don_vi": "zzlan"},
    ])
    r = client.put(f"{API}/{goc['id']}", json=body, headers=h)
    assert r.status_code == 200, r.text
    ds = r.json()["viec_phat_sinh"]
    assert _gon(ds) == [("ZZ Thay bản kẽm", 120, "zzban"), ("ZZ Lau máy", 80, "zzlan")]
    assert ds[0]["id"] == thay_kem["id"], "sửa tên/giá phải giữ id cũ"
    assert ds[1]["id"] not in (thay_kem["id"], rua_lo["id"])

    with SessionLocal() as s:
        con = s.scalar(select(func.count()).select_from(ViecPhatSinh)
                       .where(ViecPhatSinh.id == rua_lo["id"]))
    assert con == 0, "dòng bị bỏ khỏi danh sách phải bị xoá thật"


def test_put_khong_gui_viec_phat_sinh_thi_giu_nguyen(client):
    """Cửa ghi không biết tới việc phát sinh (nhập Excel, client cũ) gửi thiếu khoá ⇒ GIỮ NGUYÊN,
    không hiểu nhầm thành "xoá hết"."""
    h = _admin(client)
    goc = _mk(client, h).json()
    body = _body(client, h, unit_price=35)
    body.pop("viec_phat_sinh")
    r = client.put(f"{API}/{goc['id']}", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert _gon(r.json()["viec_phat_sinh"]) == _gon(goc["viec_phat_sinh"])


def test_gui_danh_sach_rong_thi_xoa_het(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    r = client.put(f"{API}/{goc['id']}", json=_body(client, h, viec_phat_sinh=[]), headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["viec_phat_sinh"] == []


def test_giu_dung_thu_tu_da_khai(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    a, b = goc["viec_phat_sinh"]
    r = client.put(f"{API}/{goc['id']}", json=_body(client, h, viec_phat_sinh=[
        {**b}, {**a},
    ]), headers=h)
    assert r.status_code == 200, r.text
    assert [v["id"] for v in r.json()["viec_phat_sinh"]] == [b["id"], a["id"]]


# --- Luật khai ---------------------------------------------------------------


def _loi(client, h, dong: dict) -> str:
    r = _mk(client, h, viec_phat_sinh=[dong])
    assert r.status_code == 422, r.text
    return str(r.json()["detail"])


def test_ten_viec_trong_bi_chan(client):
    h = _admin(client)
    assert "Tên việc phát sinh" in _loi(client, h, {"ten": "  ", "don_gia": 10, "don_vi": "zzlan"})


def test_ten_viec_trung_trong_cung_cong_viec_bi_chan(client):
    """Trùng không phân biệt hoa/thường và khoảng trắng hai đầu — "thay kẽm " và "Thay kẽm" là
    cùng một việc dưới mắt thợ."""
    h = _admin(client)
    r = _mk(client, h, viec_phat_sinh=[
        {"ten": "ZZ Thay kẽm", "don_gia": 100, "don_vi": _don_vi(client, h, "zzban", "ZZ Bản")},
        {"ten": "zz thay kẽm ", "don_gia": 90, "don_vi": "zzban"},
    ])
    assert r.status_code == 422, r.text
    assert "trùng" in str(r.json()["detail"])


def test_don_gia_thieu_hoac_am_bi_chan(client):
    h = _admin(client)
    _don_vi(client, h, "zzlan", "ZZ Lần")
    assert "đơn giá" in _loi(client, h, {"ten": "ZZ Lau máy", "don_vi": "zzlan"}).lower()
    assert "âm" in _loi(client, h, {"ten": "ZZ Lau máy", "don_gia": -1, "don_vi": "zzlan"})


def test_don_gia_bang_0_van_khai_duoc(client):
    h = _admin(client)
    r = _mk(client, h, viec_phat_sinh=[
        {"ten": "ZZ Việc chưa định giá", "don_gia": 0, "don_vi": _don_vi(client, h, "zzlan", "ZZ Lần")},
    ])
    assert r.status_code == 201, r.text


def test_don_vi_trong_hoac_ngoai_danh_muc_bi_chan(client):
    """Khác ô đơn vị của công việc khoán cha (còn nhận chữ ngoài danh mục vì dữ liệu đời cũ): việc
    phát sinh là bảng MỚI, không có dòng cũ nào cần đỡ — chặn ngay từ đầu để không đẻ ra mã lạ."""
    h = _admin(client)
    assert "đơn vị" in _loi(client, h, {"ten": "ZZ Lau máy", "don_gia": 5, "don_vi": ""}).lower()
    loi = _loi(client, h, {"ten": "ZZ Lau máy", "don_gia": 5, "don_vi": "zz-khong-co"})
    assert "Đơn vị & quy đổi" in loi


# --- Nhân bản · xoá · nhật ký ----------------------------------------------------


def test_nhan_ban_chep_luon_viec_phat_sinh(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    r = client.post(f"{API}/{goc['id']}/clone", headers=h)
    assert r.status_code == 201, r.text
    sao = r.json()["viec_phat_sinh"]
    assert _gon(sao) == _gon(goc["viec_phat_sinh"])
    assert {v["id"] for v in sao}.isdisjoint({v["id"] for v in goc["viec_phat_sinh"]}), \
        "bản sao phải có dòng RIÊNG, không dùng chung dòng với bản gốc"


def test_xoa_cong_viec_khoan_xoa_luon_viec_phat_sinh(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    ids = [v["id"] for v in goc["viec_phat_sinh"]]
    assert client.delete(f"{API}/{goc['id']}", headers=h).status_code == 204
    with SessionLocal() as s:
        con = s.scalar(select(func.count()).select_from(ViecPhatSinh).where(ViecPhatSinh.id.in_(ids)))
    assert con == 0


def test_nhat_ky_ghi_thay_doi_viec_phat_sinh(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    thay_kem, rua_lo = goc["viec_phat_sinh"]
    client.put(f"{API}/{goc['id']}", json=_body(client, h, viec_phat_sinh=[
        {**thay_kem, "don_gia": 150}, rua_lo,
    ]), headers=h)
    dong = client.get(f"/api/nhat-ky-danh-muc/cong_viec_khoan/{goc['id']}", headers=h).json()["items"]
    sua = [i["detail"] for i in dong if i["action"] == "dm_sua"]
    assert sua, "đổi đơn giá việc phát sinh phải để lại vết"
    assert "Việc phát sinh" in sua[0] and "ZZ Thay kẽm" in sua[0], sua[0]
    assert "ZZ Rửa lô mực" not in sua[0], "dòng không đổi thì không in"
    # Đơn vị in bằng TÊN danh mục, không in mã: "50 đ/to" đọc thành chữ "to", không ai tra ra "tờ".
    assert "150 đ/ZZ Bản" in sua[0] and "zzban" not in sua[0], sua[0]


def test_luu_lai_y_nguyen_khong_ghi_nhat_ky(client):
    h = _admin(client)
    goc = _mk(client, h).json()
    url = f"/api/nhat-ky-danh-muc/cong_viec_khoan/{goc['id']}"
    truoc = len(client.get(url, headers=h).json()["items"])
    body = _body(client, h, viec_phat_sinh=goc["viec_phat_sinh"])
    assert client.put(f"{API}/{goc['id']}", json=body, headers=h).status_code == 200
    assert len(client.get(url, headers=h).json()["items"]) == truoc
