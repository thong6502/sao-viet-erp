"""Tab Ghi chú — customer_notes CRUD + ghim + tách khỏi Nhật ký.

Ghi chú TỰ DO của team về khách: xem cần quyền `read`, thêm/sửa/xóa/ghim cần `update`.
Ghim KHÔNG tính là "đã sửa" (updated_at chỉ bump khi đổi nội dung). KHÔNG ghi audit →
không hiện trong Nhật ký. Chạy trên in-memory DB nên không đụng dữ liệu thật.
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _create(client, token, name: str = "KH Ghi chú") -> int:
    r = client.post("/api/customers", json={"name": name}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["customer"]["id"]


def test_note_crud_roundtrip(client):
    token = _admin_token(client)
    cid = _create(client, token)

    # thêm
    r = client.post(
        f"/api/customers/{cid}/notes",
        json={"body": "Thích giao buổi sáng"},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["body"] == "Thích giao buổi sáng"
    assert n["pinned"] is False and n["edited"] is False and n["updated_at"] is None
    assert n["author_name"]  # tên người ghi được nạp
    nid = n["id"]

    # list thấy đúng 1 ghi chú
    items = client.get(f"/api/customers/{cid}/notes", headers=_h(token)).json()["items"]
    assert [x["id"] for x in items] == [nid]

    # sửa nội dung → edited=True + updated_at set
    r = client.put(
        f"/api/customers/{cid}/notes/{nid}",
        json={"body": "Thích giao SÁNG sớm"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    n2 = r.json()
    assert n2["body"] == "Thích giao SÁNG sớm"
    assert n2["edited"] is True and n2["updated_at"] is not None

    # xóa
    assert client.delete(f"/api/customers/{cid}/notes/{nid}", headers=_h(token)).status_code == 204
    assert client.get(f"/api/customers/{cid}/notes", headers=_h(token)).json()["items"] == []


def test_pin_does_not_count_as_edit_and_sorts_first(client):
    token = _admin_token(client)
    cid = _create(client, token, name="KH Ghim")
    a = client.post(f"/api/customers/{cid}/notes", json={"body": "Ghi chú A"}, headers=_h(token)).json()
    b = client.post(f"/api/customers/{cid}/notes", json={"body": "Ghi chú B"}, headers=_h(token)).json()

    # mặc định mới-nhất-trước: B rồi A
    ids = [x["id"] for x in client.get(f"/api/customers/{cid}/notes", headers=_h(token)).json()["items"]]
    assert ids == [b["id"], a["id"]]

    # ghim A: lên đầu, và edited vẫn False (ghim KHÔNG phải sửa nội dung)
    r = client.put(f"/api/customers/{cid}/notes/{a['id']}", json={"pinned": True}, headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["pinned"] is True and r.json()["edited"] is False
    ids = [x["id"] for x in client.get(f"/api/customers/{cid}/notes", headers=_h(token)).json()["items"]]
    assert ids == [a["id"], b["id"]]


def test_empty_body_rejected(client):
    token = _admin_token(client)
    cid = _create(client, token, name="KH Rỗng")
    # rỗng/toàn khoảng trắng khi tạo → 422
    assert client.post(f"/api/customers/{cid}/notes", json={"body": "   "}, headers=_h(token)).status_code == 422
    # rỗng khi sửa → 422
    nid = client.post(f"/api/customers/{cid}/notes", json={"body": "x"}, headers=_h(token)).json()["id"]
    assert client.put(f"/api/customers/{cid}/notes/{nid}", json={"body": "  "}, headers=_h(token)).status_code == 422


def test_note_of_other_customer_is_404(client):
    token = _admin_token(client)
    c1 = _create(client, token, name="KH1")
    c2 = _create(client, token, name="KH2")
    nid = client.post(f"/api/customers/{c1}/notes", json={"body": "của c1"}, headers=_h(token)).json()["id"]
    # sửa/xóa note của c1 qua đường c2 → 404 (không rò rỉ giữa khách)
    assert client.put(f"/api/customers/{c2}/notes/{nid}", json={"body": "hack"}, headers=_h(token)).status_code == 404
    assert client.delete(f"/api/customers/{c2}/notes/{nid}", headers=_h(token)).status_code == 404


def test_notes_not_in_audit_timeline(client):
    """Ghi chú KHÔNG ghi audit → KHÔNG hiện trong Nhật ký (giữ tách)."""
    token = _admin_token(client)
    cid = _create(client, token, name="KH Tách Nhật ký")
    before = client.get(f"/api/customers/{cid}/audit", headers=_h(token)).json()["items"]
    client.post(f"/api/customers/{cid}/notes", json={"body": "note ẩn khỏi nhật ký"}, headers=_h(token))
    after = client.get(f"/api/customers/{cid}/audit", headers=_h(token)).json()["items"]
    assert len(after) == len(before)
    assert all("note ẩn khỏi nhật ký" not in (x.get("detail") or "") for x in after)
