"""Ảnh minh họa của dòng báo giá — /api/quotations/{id}/items/{item_id}/anh-minh-hoa.

Bản in gửi khách bỏ cột "Thành tiền", thay bằng cột **Hình ảnh minh họa**. Vì bản in gộp các
dòng CÙNG TÊN thành một dòng (ruột + bìa → 1 "quyển sách"; nhiều mức SL của cùng một món → 1
dòng nhiều mức), ảnh cũng phải theo đúng đơn vị đó: **một ảnh cho cả cụm cùng tên**, upload một
lần là mọi dòng trong cụm nhận chung — chứ không phải mỗi dòng dữ liệu một ảnh.

Khóa cụm = `nhom` nếu dòng có nhãn nhóm, không thì `product_name` (đúng khóa mà bản in dùng ở
`utils/gop-nhom.ts`: gopTheoNhom theo nhãn `nhom`, rồi gopTrungTen theo tên hiển thị).

Bao phủ: upload lan cả cụm · dòng khác tên không dính · xóa gỡ cả cụm + dọn storage ·
ảnh theo sang phiên bản mới khi re-quote · guard (không phải ảnh / rỗng / quá lớn / đã hủy /
lẫn phiếu khác).
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mk_ptg_hai_cum() -> int:
    """PTG 3 thành phần: Ruột + Bìa cùng nhãn nhóm "Sách ABC" (bản in gộp 1 dòng) + 1 tờ rơi rời."""
    db = SessionLocal()
    try:
        n = db.query(PhieuTinhGia).count() + 1
        ptg = PhieuTinhGia(
            ma=f"PTG-ANH-{n:04d}", ten_san_pham="Sách ABC", so_luong=1000,
            tong_gia_von=3_000_000, gia_von_don=0, ktv="KTV Test",
        )
        db.add(ptg)
        db.flush()
        db.add(PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=0, ten="Ruột sách", so_luong=1000,
            gia_von_tp=1_000_000, loai_thanh_phan="to_roi", nhom_bao_gia="Sách ABC",
        ))
        db.add(PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=1, ten="Bìa sách", so_luong=1000,
            gia_von_tp=1_000_000, loai_thanh_phan="to_roi", nhom_bao_gia="Sách ABC",
        ))
        db.add(PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=2, ten="Tờ rơi A5", so_luong=5000,
            gia_von_tp=1_000_000, loai_thanh_phan="to_roi",
        ))
        db.commit()
        return ptg.id
    finally:
        db.close()


def _create_quote(client, token) -> dict:
    r = client.post(
        "/api/quotations",
        json={"customer_id": None, "phieu_tinh_gia_id": _mk_ptg_hai_cum(), "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _dat_anh(client, token, qid, item_id, name="minh-hoa.png", data=b"PNGDATA", ctype="image/png"):
    return client.post(
        f"/api/quotations/{qid}/items/{item_id}/anh-minh-hoa",
        files={"file": (name, data, ctype)},
        headers=_h(token),
    )


def _items(client, token, qid) -> list[dict]:
    r = client.get(f"/api/quotations/{qid}", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _theo_ten(items: list[dict]) -> dict[str, dict]:
    return {it["product_name"]: it for it in items}


# --- upload: một ảnh cho cả cụm cùng tên ---------------------------------------

def test_upload_gan_anh_cho_moi_dong_cung_cum(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    ruot = _theo_ten(_items(client, token, qid))["Ruột sách"]

    r = _dat_anh(client, token, qid, ruot["id"])
    assert r.status_code == 200, r.text
    url = r.json()["anh_minh_hoa"]
    assert url.startswith("/api/files/bao-gia/")

    sau = _theo_ten(_items(client, token, qid))
    # Ruột + Bìa cùng nhãn "Sách ABC" ⇒ bản in ra 1 dòng ⇒ dùng CHUNG một ảnh.
    assert sau["Ruột sách"]["anh_minh_hoa"] == url
    assert sau["Bìa sách"]["anh_minh_hoa"] == url
    # Tờ rơi là cụm khác ⇒ không dính ảnh của cụm sách.
    assert sau["Tờ rơi A5"]["anh_minh_hoa"] is None


def test_upload_tai_ve_duoc_va_ghi_vet_hoat_dong(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    to_roi = _theo_ten(_items(client, token, qid))["Tờ rơi A5"]

    url = _dat_anh(client, token, qid, to_roi["id"], data=b"anh-that").json()["anh_minh_hoa"]

    got = client.get(url)
    assert got.status_code == 200 and got.content == b"anh-that"

    acts = client.get(f"/api/quotations/{qid}/activity", headers=_h(token)).json()["items"]
    assert any(a["action"] == "quote_item_image_set" for a in acts)


def test_thay_anh_moi_don_anh_cu_khoi_storage(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    ruot = _theo_ten(_items(client, token, qid))["Ruột sách"]

    cu = _dat_anh(client, token, qid, ruot["id"], data=b"anh-cu").json()["anh_minh_hoa"]
    moi = _dat_anh(client, token, qid, ruot["id"], name="khac.png", data=b"anh-moi").json()["anh_minh_hoa"]

    assert moi != cu
    assert client.get(cu).status_code == 404          # ảnh cũ đã dọn, không để file rác
    assert client.get(moi).content == b"anh-moi"
    assert _theo_ten(_items(client, token, qid))["Bìa sách"]["anh_minh_hoa"] == moi


# --- xóa ------------------------------------------------------------------------

def test_xoa_anh_go_khoi_ca_cum_va_don_storage(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    bia = _theo_ten(_items(client, token, qid))["Bìa sách"]
    url = _dat_anh(client, token, qid, bia["id"]).json()["anh_minh_hoa"]

    d = client.delete(f"/api/quotations/{qid}/items/{bia['id']}/anh-minh-hoa", headers=_h(token))
    assert d.status_code == 204, d.text

    sau = _theo_ten(_items(client, token, qid))
    assert sau["Ruột sách"]["anh_minh_hoa"] is None
    assert sau["Bìa sách"]["anh_minh_hoa"] is None
    assert client.get(url).status_code == 404


# --- phiên bản mới --------------------------------------------------------------

def test_anh_theo_sang_phien_ban_moi(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    ruot = _theo_ten(_items(client, token, qid))["Ruột sách"]
    url = _dat_anh(client, token, qid, ruot["id"]).json()["anh_minh_hoa"]

    # Chỉ báo giá BỊ TỪ CHỐI mới tạo được phiên bản mới → đi đúng đường nghiệp vụ trước.
    for to in ("sent", "rejected"):
        t = client.post(
            f"/api/quotations/{qid}/transition", json={"to_status": to}, headers=_h(token),
        )
        assert t.status_code == 200, t.text

    r = client.post(
        f"/api/quotations/{qid}/requote",
        json={"change_reason": "Khách đổi giấy"},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text

    sau = _theo_ten(_items(client, token, qid))
    assert sau["Ruột sách"]["anh_minh_hoa"] == url
    assert sau["Bìa sách"]["anh_minh_hoa"] == url


# --- guards ---------------------------------------------------------------------

def test_chan_tep_khong_phai_anh(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    it = _theo_ten(_items(client, token, qid))["Tờ rơi A5"]
    r = _dat_anh(client, token, qid, it["id"], name="bang-gia.pdf",
                 data=b"%PDF-1.4", ctype="application/pdf")
    assert r.status_code == 400, r.text


def test_chan_tep_rong(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    it = _theo_ten(_items(client, token, qid))["Tờ rơi A5"]
    assert _dat_anh(client, token, qid, it["id"], data=b"").status_code == 400


def test_chan_anh_qua_lon(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    it = _theo_ten(_items(client, token, qid))["Tờ rơi A5"]
    big = b"\0" * (5 * 1024 * 1024 + 1)
    r = _dat_anh(client, token, qid, it["id"], name="to.png", data=big)
    assert r.status_code == 413, r.text


def test_bao_gia_da_huy_chan_dat_anh(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    it = _theo_ten(_items(client, token, qid))["Tờ rơi A5"]
    c = client.post(
        f"/api/quotations/{qid}/transition",
        json={"to_status": "cancelled", "cancel_reason": "Khách đổi ý"},
        headers=_h(token),
    )
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert _dat_anh(client, token, qid, it["id"]).status_code == 409


def test_khong_dat_anh_cho_dong_cua_bao_gia_khac(client):
    token = _admin_token(client)
    qa = _create_quote(client, token)["id"]
    qb = _create_quote(client, token)["id"]
    it_a = _theo_ten(_items(client, token, qa))["Tờ rơi A5"]
    r = _dat_anh(client, token, qb, it_a["id"])
    assert r.status_code == 404, r.text
