"""Tài liệu đính kèm NỘI BỘ của báo giá — /api/quotations/{id}/attachments.

Bám mẫu đính kèm dùng chung (customers/employees): lưu qua storage, đọc lại qua
/api/files/bao-gia/... có kiểm quyền `bao_gia`. Bao phủ:
  - vòng đời upload → list → tải về (cookie file) → xóa (dọn luôn object storage);
  - vết ai-gì-lúc-nào hiện ở feed Hoạt động (audit target quote:{id});
  - guard: báo giá đã HỦY chặn thêm/xóa (409); tệp rỗng (400); tệp > 25MB (413);
  - không xóa được đính kèm của báo giá khác (404).
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


def _mk_ptg() -> int:
    db = SessionLocal()
    try:
        n = db.query(PhieuTinhGia).count() + 1
        ptg = PhieuTinhGia(
            ma=f"PTG-ATT-{n:04d}", ten_san_pham="Catalogue A4", so_luong=1000,
            tong_gia_von=1_000_000, gia_von_don=0, ktv="KTV Test",
        )
        db.add(ptg)
        db.flush()
        db.add(PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=0, ten="Catalogue A4", so_luong=1000,
            gia_von_tp=1_000_000, loai_thanh_phan="to_roi",
        ))
        db.commit()
        return ptg.id
    finally:
        db.close()


def _create_quote(client, token) -> dict:
    r = client.post(
        "/api/quotations",
        json={"customer_id": None, "phieu_tinh_gia_id": _mk_ptg(), "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, token, quote_id, name="thiet-ke.png", data=b"PNGDATA", ctype="image/png"):
    return client.post(
        f"/api/quotations/{quote_id}/attachments",
        files={"file": (name, data, ctype)},
        headers=_h(token),
    )


# --- vòng đời đầy đủ ------------------------------------------------------------

def test_upload_list_download_delete_flow(client):
    token = _admin_token(client)
    q = _create_quote(client, token)
    qid = q["id"]

    # rỗng lúc đầu
    r = client.get(f"/api/quotations/{qid}/attachments", headers=_h(token))
    assert r.status_code == 200 and r.json()["items"] == []

    # upload
    up = _upload(client, token, qid, data=b"noi-dung-file-in")
    assert up.status_code == 201, up.text
    att = up.json()
    assert att["file_name"] == "thiet-ke.png"
    assert att["file_type"] == "image/png"
    assert att["file_url"].startswith("/api/files/bao-gia/")

    # list thấy 1
    items = client.get(f"/api/quotations/{qid}/attachments", headers=_h(token)).json()["items"]
    assert len(items) == 1 and items[0]["id"] == att["id"]

    # tải về đúng bytes (TestClient giữ cookie file_access sau login)
    got = client.get(att["file_url"])
    assert got.status_code == 200 and got.content == b"noi-dung-file-in"

    # vết hiện ở feed Hoạt động
    acts = client.get(f"/api/quotations/{qid}/activity", headers=_h(token)).json()["items"]
    assert any(a["action"] == "quote_attach_add" for a in acts)

    # xóa → dọn luôn file trong storage
    d = client.delete(f"/api/quotations/{qid}/attachments/{att['id']}", headers=_h(token))
    assert d.status_code == 204, d.text
    assert client.get(f"/api/quotations/{qid}/attachments", headers=_h(token)).json()["items"] == []
    assert client.get(att["file_url"]).status_code == 404  # object đã bị xóa khỏi storage


# --- guards --------------------------------------------------------------------

def test_empty_file_rejected(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    r = _upload(client, token, qid, data=b"")
    assert r.status_code == 400, r.text


def test_too_big_file_rejected(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    big = b"\0" * (25 * 1024 * 1024 + 1)
    r = _upload(client, token, qid, name="qua-to.psd", data=big, ctype="application/octet-stream")
    assert r.status_code == 413, r.text


def test_cancelled_quote_blocks_upload_but_still_lists(client):
    token = _admin_token(client)
    qid = _create_quote(client, token)["id"]
    # đính 1 tệp khi còn nháp
    assert _upload(client, token, qid).status_code == 201
    # hủy báo giá
    c = client.post(
        f"/api/quotations/{qid}/transition",
        json={"to_status": "cancelled", "cancel_reason": "Khách đổi ý"},
        headers=_h(token),
    )
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    # vẫn xem được danh sách…
    assert client.get(f"/api/quotations/{qid}/attachments", headers=_h(token)).status_code == 200
    # …nhưng KHÔNG thêm nữa (409)
    assert _upload(client, token, qid).status_code == 409


def test_cannot_delete_attachment_of_another_quote(client):
    token = _admin_token(client)
    qa = _create_quote(client, token)["id"]
    qb = _create_quote(client, token)["id"]
    att = _upload(client, token, qa).json()
    # xóa đính kèm của A qua đường B → 404 (không lẫn phiếu)
    r = client.delete(f"/api/quotations/{qb}/attachments/{att['id']}", headers=_h(token))
    assert r.status_code == 404
    # A vẫn còn tệp
    assert len(client.get(f"/api/quotations/{qa}/attachments", headers=_h(token)).json()["items"]) == 1
