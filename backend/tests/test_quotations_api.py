"""Báo giá H-V-I API (Quote → QuoteVersion → QuoteItem).

Covers: list + status filter + stats; create từ 1 Phiếu tính giá (dòng = mỗi sản phẩm
PhieuThanhPhan, giá vốn khóa per dòng + gói biên áp chung); validation (thiếu phiếu → 422,
phiếu không tồn tại → 422, hạn quá khứ → 422); khóa sửa sau khi gửi (409); lifecycle
draft→sent (freeze snapshot) → accepted/rejected, transition sai → 409/422, hủy cần lý do;
requote sinh phiên bản mới.

Đợt 5 (2026-08-08): đường Estimate cũ (`estimate_id`/`picks`) đã gỡ hẳn — mọi test dựng qua
`phieu_tinh_gia_id`, và picker SEAM-13 `/api/quotations/costings/{id}` không còn tồn tại.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuTinhGia

ADMIN = {"username": "admin", "password": "admin123"}
TOMORROW = (date.today() + timedelta(days=30)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mk_ptg(*, products=(("Catalogue A4", 1000, 1_000_000),)) -> int:
    """Dựng 1 Phiếu tính giá thẳng vào DB (engine không tham gia): mỗi phần tử
    `products` = (tên, số lượng, giá vốn) → 1 `PhieuThanhPhan` = 1 dòng báo giá. Trả id."""
    db = SessionLocal()
    try:
        n = db.query(PhieuTinhGia).count() + 1
        ptg = PhieuTinhGia(
            ma=f"PTG-TEST-{n:04d}",
            ten_san_pham=products[0][0],
            so_luong=products[0][1],
            tong_gia_von=sum(p[2] for p in products),
            gia_von_don=0,
            ktv="KTV Test",
        )
        db.add(ptg)
        db.flush()
        for i, (ten, sl, von) in enumerate(products):
            db.add(PhieuThanhPhan(
                phieu_id=ptg.id, thu_tu=i, ten=ten, so_luong=sl, gia_von_tp=von,
                loai_thanh_phan="to_roi",
            ))
        db.commit()
        return ptg.id
    finally:
        db.close()


def _create(client, token, ptg_id, **over) -> dict:
    body = {"customer_id": None, "phieu_tinh_gia_id": ptg_id, "valid_until": TOMORROW}
    body.update(over)
    r = client.post("/api/quotations", json=body, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


# --- list + stats ---------------------------------------------------------------

def test_list_empty_then_shows_created(client):
    token = _admin_token(client)
    r = client.get("/api/quotations", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0

    q = _create(client, token, _mk_ptg())

    body = client.get("/api/quotations?page=1&size=10", headers=_h(token)).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["code"].startswith("BG")
    assert row["version"] == 1
    assert row["status"] == "draft"
    assert row["total"] == q["total"]
    assert row["product_summary"] == "Catalogue A4"


def test_list_status_filter_and_stats(client):
    token = _admin_token(client)
    _create(client, token, _mk_ptg())

    r = client.get("/api/quotations?status=accepted", headers=_h(token))
    assert r.status_code == 200 and r.json()["total"] == 0

    stats = client.get("/api/quotations/stats", headers=_h(token)).json()
    assert stats["total"] == 1 and stats["draft"] == 1 and stats["need_action"] == 1


# --- create: từ phiếu tính giá ---------------------------------------------------

def test_create_one_line_per_product_with_shared_margin(client):
    """1 PTG nhiều sản phẩm → mỗi sản phẩm 1 dòng, giá vốn khóa riêng, gói biên áp chung."""
    token = _admin_token(client)
    pid = _mk_ptg(products=(
        ("Catalogue A4", 1000, 1_000_000),
        ("Tờ rơi A5", 5000, 400_000),
    ))
    q = _create(client, token, pid, margin_percent=25)

    assert len(q["items"]) == 2
    for it in q["items"]:
        assert it["margin_percent"] == 25.0        # gói biên áp chung
        assert it["total_cost_snapshot"] > 0       # giá vốn khóa per dòng

    # Giá bán mỗi dòng = giá vốn × (1 + 25%) rồi + VAT 10%
    it1 = next(it for it in q["items"] if it["product_name"] == "Catalogue A4")
    assert abs(it1["selling_price"] - 1_000_000 * 1.25) < 1
    assert abs(it1["final_amount"] - it1["selling_price"] * 1.10) < 1

    # Tổng version = cộng các dòng
    assert abs(q["total"] - sum(it["final_amount"] for it in q["items"])) < 1


def test_create_requires_a_phieu_tinh_gia(client):
    """Báo giá phải xuất phát từ 1 phiếu tính giá — thiếu / không tồn tại đều 422."""
    token = _admin_token(client)
    r = client.post("/api/quotations", json={"valid_until": TOMORROW}, headers=_h(token))
    assert r.status_code == 422
    assert "Phiếu tính giá" in r.json()["detail"]

    r = client.post(
        "/api/quotations",
        json={"phieu_tinh_gia_id": 99999, "valid_until": TOMORROW},
        headers=_h(token),
    )
    assert r.status_code == 422


def test_create_past_valid_until_422(client):
    token = _admin_token(client)
    r = client.post(
        "/api/quotations",
        json={"phieu_tinh_gia_id": _mk_ptg(), "valid_until": YESTERDAY},
        headers=_h(token),
    )
    assert r.status_code == 422


# --- update draft only -----------------------------------------------------------

def test_update_locked_after_send(client):
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())

    # sửa được khi draft (đổi % biên dòng đầu)
    item_id = q["items"][0]["id"]
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"items": [{"id": item_id, "margin_percent": 30, "vat_percent": 10}]},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["margin_percent"] == 30.0

    # gửi khách → khóa
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 200
    r = client.put(
        f"/api/quotations/{q['id']}",
        json={"items": [{"id": item_id, "margin_percent": 5}]},
        headers=_h(token),
    )
    assert r.status_code == 409


# --- lifecycle --------------------------------------------------------------------

def test_send_freezes_snapshot_then_accept(client):
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())

    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert "accepted" in body["allowed_transitions"]

    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "accepted"}, headers=_h(token))
    assert r.status_code == 200 and r.json()["status"] == "accepted"


def test_illegal_transition_conflict(client):
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    # draft → rejected là bất hợp lệ
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))
    assert r.status_code == 409
    # trạng thái lạ → 422
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "banana"}, headers=_h(token))
    assert r.status_code == 422


def test_cancel_requires_reason(client):
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    r = client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "cancelled"}, headers=_h(token))
    assert r.status_code == 422
    r = client.post(
        f"/api/quotations/{q['id']}/transition",
        json={"to_status": "cancelled", "cancel_reason": "Khách đổi ý"},
        headers=_h(token),
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_requote_new_version(client):
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    # Đưa về "Bị từ chối" (khách từ chối) — trạng thái DUY NHẤT tạo được phiên bản mới.
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))

    # Tạo phiên bản mới BẮT BUỘC ghi chú — thiếu → 422.
    r0 = client.post(f"/api/quotations/{q['id']}/requote", json={"change_reason": "  "}, headers=_h(token))
    assert r0.status_code == 422, r0.text

    r = client.post(f"/api/quotations/{q['id']}/requote",
                    json={"change_reason": "KH đổi số lượng"}, headers=_h(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 2
    assert len(body["versions"]) == 2
    # phiên bản cũ giữ nguyên trong lịch sử
    assert {v["version"] for v in body["versions"]} == {1, 2}
    # ghi chú in vào phiên bản mới (Lịch sử phiên bản); phiên bản mới về nháp để sửa
    v2 = next(v for v in body["versions"] if v["version"] == 2)
    assert v2["change_reason"] == "KH đổi số lượng"
    assert body["status"] == "draft"


def test_requote_carries_source_product_ref(client):
    """Phiên bản mới chép dòng cũ KÈM neo sản phẩm nguồn (`phieu_thanh_phan_id`) — mất neo là
    mất đường lần ngược về bài tính giá."""
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))
    r = client.post(f"/api/quotations/{q['id']}/requote",
                    json={"change_reason": "báo lại"}, headers=_h(token))
    assert r.status_code == 201, r.text

    from app.models.quotation import Quote, QuoteVersion
    db = SessionLocal()
    try:
        quote = db.get(Quote, q["id"])
        v2 = db.get(QuoteVersion, quote.current_version_id)
        assert v2.version_number == 2
        assert [it.phieu_thanh_phan_id for it in v2.items] and all(
            it.phieu_thanh_phan_id is not None for it in v2.items
        )
    finally:
        db.close()


def test_requote_blocked_unless_rejected(client):
    """Tạo phiên bản mới CHỈ khi báo giá BỊ TỪ CHỐI — nháp / đã gửi → 409."""
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    # Nháp → chặn 409.
    r = client.post(f"/api/quotations/{q['id']}/requote", json={"change_reason": "thử"}, headers=_h(token))
    assert r.status_code == 409, r.text
    # Đã gửi khách → vẫn chặn.
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    r2 = client.post(f"/api/quotations/{q['id']}/requote", json={"change_reason": "thử"}, headers=_h(token))
    assert r2.status_code == 409, r2.text
    # Khách từ chối → CHO tạo phiên bản mới.
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))
    r3 = client.post(f"/api/quotations/{q['id']}/requote",
                     json={"change_reason": "báo lại giá"}, headers=_h(token))
    assert r3.status_code == 201, r3.text
    assert r3.json()["version"] == 2


def test_valid_until_defaults_30_days(client):
    """Hạn hiệu lực mặc định = 30 ngày kể từ hôm nay khi KHÔNG truyền valid_until."""
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg(), valid_until=None)
    assert q["valid_until"] == (date.today() + timedelta(days=30)).isoformat()
    # Tạo phiên bản mới cũng reset hạn = +30 ngày (từ phiên bản mới nhất).
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "rejected"}, headers=_h(token))
    r = client.post(f"/api/quotations/{q['id']}/requote",
                    json={"change_reason": "báo lại"}, headers=_h(token))
    assert r.json()["valid_until"] == (date.today() + timedelta(days=30)).isoformat()


def test_activity_feed_records_who_did_what(client):
    """Feed Hoạt động = nhật ký THẬT (ai làm gì): mọi thao tác để lại dấu vết + tên người."""
    token = _admin_token(client)
    q = _create(client, token, _mk_ptg())
    client.post(f"/api/quotations/{q['id']}/transition", json={"to_status": "sent"}, headers=_h(token))

    r = client.get(f"/api/quotations/{q['id']}/activity", headers=_h(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    actions = [it["action"] for it in items]
    assert "create_quote" in actions
    assert "transition_sent" in actions
    # có TÊN người thao tác (biết ai làm) — không rỗng
    assert any(it["actor_name"] for it in items)
    # mới nhất trước: gửi khách đứng trước tạo báo giá
    assert actions.index("transition_sent") < actions.index("create_quote")


# --- PDF đối ngoại: TIẾNG VIỆT CÓ DẤU ------------------------------------------

def test_pdf_giu_dau_tieng_viet(client, monkeypatch):
    """Bản in gửi khách phải giữ dấu — trước 02/09/2026 nó bỏ dấu sạch (`_ascii`, đã gỡ).

    Không đọc ngược được TEXT từ trong PDF (nội dung trang bị nén, chữ đi qua font TTF nhúng
    thành mã CID — cùng lý do đã ghi ở `test_lenh_sx_pdf.py`), nên bài này bắt ngay chuỗi lúc
    nó được VẼ: bọc `Canvas.drawString`/`drawRightString` rồi soi những gì đi qua. Cách này
    khẳng định được đúng thứ cần khẳng định — chữ đưa vào bản in còn nguyên dấu.
    """
    from reportlab.pdfgen.canvas import Canvas

    da_ve: list[str] = []
    ve_trai, ve_phai = Canvas.drawString, Canvas.drawRightString

    def bat_trai(self, x, y, text, *a, **k):
        da_ve.append(text)
        return ve_trai(self, x, y, text, *a, **k)

    def bat_phai(self, x, y, text, *a, **k):
        da_ve.append(text)
        return ve_phai(self, x, y, text, *a, **k)

    monkeypatch.setattr(Canvas, "drawString", bat_trai)
    monkeypatch.setattr(Canvas, "drawRightString", bat_phai)

    token = _admin_token(client)
    q = _create(client, token, _mk_ptg(products=(("Hộp thuốc 10 vỉ", 1000, 1_000_000),)))
    r = client.get(f"/api/quotations/{q['id']}/pdf", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"

    chu = "\n".join(da_ve)
    # Tiêu đề + nhãn cột: bản cũ in "BANG BAO GIA" / "Thanh tien".
    assert "BẢNG BÁO GIÁ" in chu
    assert "Số báo giá:" in chu
    assert "Thành tiền" in chu
    assert "Điều khoản:" in chu
    # Tên sản phẩm KHÁCH đọc — chỗ bỏ dấu là sai chính tả tên riêng, không phải viết tắt.
    assert "Hộp thuốc 10 vỉ" in chu
    # Ký hiệu tiền: Helvetica không có glyph "đ" nên cột tiền trước đây in ra ô vuông.
    assert any("đ" in s for s in da_ve)
    # Font Unicode phải NHÚNG THẬT vào file, không chỉ khai tên trong code.
    assert b"DejaVuSans" in r.content


def test_cat_ten_dai_khong_de_len_cot_so():
    """Tên sản phẩm dài phải bị CẮT theo bề rộng thật của font, không được chạy đè cột Số lượng.

    Đo bằng `stringWidth` chứ không đếm ký tự: "Ơ" và "l" cùng là một ký tự nhưng rộng khác nhau,
    đếm ký tự thì tên toàn chữ hoa vẫn tràn sang cột bên phải.

    Nhập hàm từ `app.routers.quotations` chứ KHÔNG từ `services.pdf_font` (nơi hàm nay định
    nghĩa): bài này canh bản in báo giá, và điều nó phải bắt là *bản in báo giá mất phép cắt* —
    kể cả khi ai đó gỡ `cat_vua` khỏi router mà `pdf_font` vẫn còn nguyên. `test_lenh_sx_pdf`
    canh đầu kia của cùng hàm.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from app.routers.quotations import THUONG, cat_vua, dang_ky_font

    dang_ky_font()
    rong = 60 * 72 / 25.4  # 60mm quy ra point

    ngan = "Hộp thuốc"
    assert cat_vua(ngan, rong, THUONG, 10) == ngan  # vừa thì trả nguyên, không thêm "…"

    dai = "Hộp thuốc 10 vỉ — giấy Ivory 350gsm, cán màng bóng, ép kim nhũ vàng, bế hộp âm dương"
    cat = cat_vua(dai, rong, THUONG, 10)
    assert cat.endswith("…")
    assert len(cat) < len(dai)
    assert stringWidth(cat, THUONG, 10) <= rong
    assert dai.startswith(cat[:-1])  # cắt từ đuôi, không xáo chữ
