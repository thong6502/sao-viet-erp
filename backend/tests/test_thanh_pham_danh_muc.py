"""Danh mục THÀNH PHẨM — menu riêng, bảng chung, định danh theo KHÁCH (prd-thanh-pham.md).

Hai nhóm test quan trọng nhất:

* **Đặt lại không đẻ dòng mới** — mg 0203 lấy khoá `order_line_id` nên khách đặt lại là có hai
  dòng cùng tên, và tồn kho bị XÉ ĐÔI. Đây là lỗi chủ dự án bắt được 19/08/2026.
* **Ba chỗ §10 "dễ sai"** — cả ba đều hỏng IM LẶNG: `_mat_hang_row` trả sai `hang_loai` (kho nhập
  được nhưng tra ngược ra rỗng) · quên lọc (hàng hiện ở cả hai màn) · quên thêm vào vòng tìm mặt
  hàng (kho không tìm thấy gì để nhập kho, ô tìm chỉ trả về rỗng).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.customer import Customer
from app.models.order import STATUS_DRAFT, Order, OrderLine
from app.models.vat_lieu_kho import VatTuInAn
from app.services.thanh_pham_khai_bao import chuan_ten, khai_cho_don


def auth_headers(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


TEN_THAT = "Hộp thuốc 10 vỉ — in 2 màu, cán bóng"


def _khach(suffix: str) -> int:
    db = SessionLocal()
    try:
        kh = db.query(Customer).filter(Customer.code == f"KH-TP-{suffix}").one_or_none()
        if kh is None:
            kh = Customer(code=f"KH-TP-{suffix}", name=f"Khach {suffix}")
            db.add(kh)
            db.commit()
        return kh.id
    finally:
        db.close()


def _don(suffix: str, customer_id: int, *, ten: str = TEN_THAT, dvt: str = "hộp",
         so_dong: int = 1) -> int:
    """Một đơn NHÁP + dòng của khách đã cho. Trả `order_id`."""
    db = SessionLocal()
    try:
        o = Order(order_no=f"DH-TP-{suffix}", status=STATUS_DRAFT, customer_id=customer_id)
        db.add(o)
        db.flush()
        for i in range(so_dong):
            db.add(OrderLine(
                order_id=o.id,
                description=ten if i == 0 else f"{ten} (dòng {i + 1})",
                don_vi_tinh=dvt, qty=100,
            ))
        db.commit()
        return o.id
    finally:
        db.close()


def _khai(order_id: int) -> list[int]:
    """Chạy đúng cái mà `OrderService.confirm()` chạy."""
    db = SessionLocal()
    try:
        ra = khai_cho_don(db, db.get(Order, order_id))
        db.commit()
        return [r.id for r in ra]
    finally:
        db.close()


def _cua_khach(customer_id: int) -> list[VatTuInAn]:
    """Thành phẩm ghi nhận khách này là người ĐẦU TIÊN đặt. KHÔNG phải "của khách" nữa —
    từ 21/08/2026 thành phẩm không thuộc về ai, `customer_id` chỉ còn là vết nguồn gốc."""
    db = SessionLocal()
    try:
        return (db.query(VatTuInAn).filter(VatTuInAn.customer_id == customer_id)
                .order_by(VatTuInAn.ma).all())
    finally:
        db.close()


def _thanh_pham() -> list[VatTuInAn]:
    """MỌI thành phẩm — lọc bằng đúng cột mà hai màn danh mục chia nhau."""
    db = SessionLocal()
    try:
        return (db.query(VatTuInAn).filter(VatTuInAn.la_thanh_pham.is_(True))
                .order_by(VatTuInAn.ma).all())
    finally:
        db.close()


# ------------------------------------------------------- ⭐ khách ĐẶT LẠI (lỗi của mg 0203)


def test_KHACH_DAT_LAI_dung_lai_dong_cu_KHONG_de_dong_thu_hai(client):
    """⭐ Đơn tháng 8 và đơn tháng 9 cùng một món ⇒ MỘT dòng danh mục.

    Khoá cũ là `TP-<số đơn>-<id dòng>` nên đặt lại là đẻ dòng thứ hai cùng tên. Nặng nhất không
    phải danh mục phình mà là **TỒN KHO BỊ XÉ ĐÔI** — hàng dư đợt trước nằm ở dòng một, hàng in
    đợt này nằm ở dòng hai, kho không trả lời được "còn bao nhiêu món này".
    """
    kh = _khach("lap")
    id_1 = _khai(_don("lap-t8", kh))[0]
    id_2 = _khai(_don("lap-t9", kh))[0]
    assert id_1 == id_2, "đặt lại đẻ ra dòng danh mục thứ hai"
    assert len(_cua_khach(kh)) == 1


def test_dat_lai_ma_go_LECH_DAU_GACH_van_la_mot_san_pham(client):
    """Chuẩn hoá rồi mới so (chủ chốt 19/08/2026): người lập đơn tháng sau gõ lại bằng tay, lệch
    một kiểu gạch hay một khoảng trắng là bản so-nguyên-văn đẻ thêm dòng."""
    kh = _khach("gach")
    _khai(_don("gach-a", kh, ten="Hộp thuốc 10 vỉ — in 2 màu, cán bóng"))
    _khai(_don("gach-b", kh, ten="hộp thuốc 10 vỉ  -  IN 2 màu, cán bóng"))
    assert len(_cua_khach(kh)) == 1, [h.ten for h in _cua_khach(kh)]


def test_HAI_KHACH_cung_ten_thi_DUNG_CHUNG_mot_dong(client):
    """⭐ ĐẢO LUẬT 21/08/2026 — khoá gộp trùng bỏ KHÁCH, chỉ còn TÊN.

    Chủ: "thành phẩm này là một cái tên hàng, nêu chưa khai để tái sử dụng, tránh phình lên".
    Trước đó khoá là `(khách, tên)` nên hai khách cùng đặt "Tờ hướng dẫn sử dụng — gấp 3" đẻ ra
    hai dòng; nay dùng CHUNG một dòng — đúng như bán cùng một cái quạt cho nhiều khách.

    Test này ĐỎ ngay khi ai đó nhét lại khách vào khoá gộp trùng.
    """
    a, b = _khach("hai-a"), _khach("hai-b")
    ten = "Tờ hướng dẫn sử dụng — gấp 3"
    id_a = _khai(_don("hai-a1", a, ten=ten))[0]
    id_b = _khai(_don("hai-b1", b, ten=ten))[0]
    assert id_a == id_b, "cùng một tên mà đẻ hai dòng danh mục — danh mục sẽ phình lên"
    assert len(_thanh_pham()) == 1


def test_chuan_ten_giu_DAU_tieng_viet(client):
    """"Bìa" và "Bia" là hai thứ khác nhau — chuẩn hoá KHÔNG được bỏ dấu."""
    assert chuan_ten("Bìa lót") != chuan_ten("Bia lót")
    assert chuan_ten("  Hộp   THUỐC – 10 vỉ. ") == chuan_ten("hộp thuốc - 10 vỉ")


def test_ma_sinh_MOT_DAY_CHUNG_va_khong_trung(client):
    """Mã bỏ phần mã khách (21/08/2026) — không còn khách để nhét vào giữa. Mã CŨ giữ nguyên."""
    kh = _khach("ma")
    _khai(_don("ma-1", kh, ten="Món một"))
    _khai(_don("ma-2", kh, ten="Món hai"))
    ma = sorted(h.ma for h in _thanh_pham())
    assert ma == ["TP-00001", "TP-00002"], ma


def test_khai_lay_NGUYEN_VAN_mo_ta_dong_don(client):
    """Tên trong danh mục = mô tả trên đơn. Kho tìm hàng theo tên khách đặt."""
    kh = _khach("ten")
    _khai(_don("ten-1", kh))
    h = _cua_khach(kh)[0]
    assert h.ten == TEN_THAT
    assert h.don_vi_gia == "hộp"


def test_don_hai_dong_khai_du_hai(client):
    kh = _khach("2dong")
    _khai(_don("2dong-1", kh, so_dong=2))
    assert len(_cua_khach(kh)) == 2


# ------------------------------------------------------------------ §10.1 — mắt xích số một


def test_kho_nhin_thay_thanh_pham_la_vat_tu_KHONG_phai_loai_thu_ba(client):
    """⭐ §10.1. `hang_loai` trả về PHẢI là "vat_tu".

    `loai` (màn danh mục nào) và `hang_loai` (bảng nào) là hai không gian tên khác nhau. Trả
    thẳng "thanh_pham" là đẻ ra giá trị thứ ba mà `stock_lots` / `stock_vouchers` /
    `stock_requests` không nhận — kho nhập được nhưng tra ngược ra rỗng, KHÔNG có lỗi nào báo.
    """
    h = auth_headers(client)
    kh = _khach("kho")
    _khai(_don("kho-1", kh))
    ma = _cua_khach(kh)[0].ma

    r = client.get("/api/vat-lieu-kho/mat-hang", params={"q": "Hộp thuốc 10 vỉ"}, headers=h)
    assert r.status_code == 200, r.text
    cua_toi = [m for m in r.json() if m["ma"] == ma]
    assert cua_toi, f"kho KHÔNG tìm thấy thành phẩm để nhập kho: {r.json()}"
    assert cua_toi[0]["hang_loai"] == "vat_tu", cua_toi[0]
    # Nhãn nhóm thì phân biệt được — người gõ thấy đây là thành phẩm chứ không phải mực/kẽm.
    assert cua_toi[0]["nhom"] == "Thành phẩm", cua_toi[0]


# ------------------------------------------------------------------ §10.2 — hai màn rời nhau


def test_hai_man_ROI_HAN_nhau(client):
    """⭐ §10.2 + PRD L4. Không dòng nào hiện ở cả hai màn."""
    h = auth_headers(client)
    kh = _khach("2man")
    _khai(_don("2man-1", kh))
    ma_tp = _cua_khach(kh)[0].ma

    vt = client.get("/api/vat-lieu-kho/vat-tu-in-an", params={"size": 200}, headers=h)
    tp = client.get("/api/vat-lieu-kho/thanh-pham", params={"size": 200}, headers=h)
    assert vt.status_code == 200 and tp.status_code == 200, (vt.text, tp.text)

    ma_vt = {r["ma"] for r in vt.json()["items"]}
    ma_tp_ds = {r["ma"] for r in tp.json()["items"]}
    assert ma_tp in ma_tp_ds, "thành phẩm không hiện ở màn Thành phẩm"
    assert ma_tp not in ma_vt, "thành phẩm LỌT sang màn Vật tư khác"
    assert not (ma_vt & ma_tp_ds), f"hai màn giẫm nhau: {ma_vt & ma_tp_ds}"


def test_man_thanh_pham_hien_TEN_KHACH(client):
    """"Của ai" chính là thứ phân biệt hai thành phẩm cùng tên — chỉ hiện id là vô dụng."""
    h = auth_headers(client)
    kh = _khach("tenkh")
    _khai(_don("tenkh-1", kh))
    r = client.get("/api/vat-lieu-kho/thanh-pham", params={"size": 200}, headers=h)
    dong = next(x for x in r.json()["items"] if x["customer_id"] == kh)
    assert dong["customer_ten"] == "Khach tenkh", dong


def test_khong_tra_CHEO_id_giua_hai_man(client):
    """Chặn cả đường tra theo id, không chỉ đường list.

    ⚠️ Chốt chặn này nằm ở `MotDanhMucVatLieu`, KHÔNG ở repo: kho tra mặt hàng
    `hang_loai="vat_tu"` đi qua đúng `_VatTuRepo.get()`. Chặn ở repo là chặn luôn kho — đã cắn
    đúng vậy 19/08/2026, 14 test đỏ với câu "Không tìm thấy mặt hàng."
    """
    h = auth_headers(client)
    kh = _khach("cheo")
    tp_id = _khai(_don("cheo-1", kh))[0]

    assert client.get(f"/api/vat-lieu-kho/thanh-pham/{tp_id}", headers=h).status_code == 200
    assert client.get(f"/api/vat-lieu-kho/vat-tu-in-an/{tp_id}", headers=h).status_code == 404


# ------------------------------------------------------------------ PRD L5 — khai tay


def test_KHAI_TAY_duoc_va_KHONG_CAN_khach(client):
    """⭐ Khai tay được (PRD L5, nới 19/08/2026) và từ 21/08/2026 KHÔNG cần khách nữa.

    Cổng "phải chọn Khách hàng" đã gỡ cùng lượt bỏ ô đó khỏi form. Nhưng dòng khai từ MÀN Thành
    phẩm vẫn phải Ở LẠI màn Thành phẩm — trước đây chính `customer_id` giữ việc đó, nay là cờ
    `la_thanh_pham` do repo đóng dấu. Quên đóng dấu là dòng vừa khai rơi sang màn Vật tư khác và
    biến mất khỏi màn vừa tạo nó: không lỗi, chỉ mất tích.
    """
    h = auth_headers(client)

    ok = client.post("/api/vat-lieu-kho/thanh-pham", json={
        "ma": "TP-TAY-002", "ten": "Khai tay không khách", "don_vi_gia": "cái",
    }, headers=h)
    assert ok.status_code == 201, ok.text

    ds = client.get("/api/vat-lieu-kho/thanh-pham", headers=h).json()["items"]
    assert [x["ma"] for x in ds] == ["TP-TAY-002"], "khai xong không thấy ở màn Thành phẩm"
    # …và KHÔNG lẫn sang màn Vật tư khác.
    vt = client.get("/api/vat-lieu-kho/vat-tu-in-an", headers=h).json()["items"]
    assert all(x["ma"] != "TP-TAY-002" for x in vt), "lọt sang màn Vật tư khác"


def test_KHAI_TAY_xong_van_MO_RA_SUA_duoc(client):
    """⭐ Lỗi thật 20/08/2026 — test cũ chỉ kiểm lúc TẠO nên bỏ lọt.

    Thành phẩm khai tay có `customer_id` nhưng KHÔNG có `order_line_id`. Chốt chặn hai màn
    (`MotDanhMucVatLieu._dung_man`) bản đầu phân biệt bằng `order_line_id`, trong khi hai repo
    lọc bằng `customer_id` — hai nơi hỏi cùng một câu bằng hai cột khác nhau. Hậu quả: khai xong
    dòng đó hiện ở màn Thành phẩm, nhưng bấm vào là "Không tìm thấy mặt hàng.", không sửa được.
    """
    h = auth_headers(client)
    kh = _khach("mora")
    tao = client.post("/api/vat-lieu-kho/thanh-pham", json={
        "ma": "TP-MORA-001", "ten": "Khai tay roi sua", "don_vi_gia": "cái", "customer_id": kh,
    }, headers=h)
    assert tao.status_code == 201, tao.text
    tp_id = tao.json()["id"]

    # Mở ra xem — đây là bước bị vỡ.
    xem = client.get(f"/api/vat-lieu-kho/thanh-pham/{tp_id}", headers=h)
    assert xem.status_code == 200, xem.text

    sua = client.put(f"/api/vat-lieu-kho/thanh-pham/{tp_id}", json={
        "ma": "TP-MORA-001", "ten": "Khai tay roi sua", "don_vi_gia": "thùng", "customer_id": kh,
    }, headers=h)
    assert sua.status_code == 200, sua.text
    assert sua.json()["don_vi_gia"] == "thùng"


def test_dong_VAT_TU_con_order_line_id_doi_cu_van_mo_duoc(client):
    """Ca lệch chiều ngược: dòng đời cũ còn `order_line_id` mà chưa có `customer_id`.

    Nó nằm ở màn Vật tư khác (repo lọc theo `customer_id`), nên mở ra cũng phải được — nếu không
    thì có dòng hiện trong bảng mà bấm vào là lỗi.
    """
    from app.models.vat_lieu_kho import VatTuInAn

    h = auth_headers(client)
    db = SessionLocal()
    try:
        v = VatTuInAn(ma="VT-CU-001", ten="Vat tu doi cu", don_vi_gia="cái",
                      order_id=1, order_line_id=1)   # có order_line_id, KHÔNG có customer_id
        db.add(v)
        db.commit()
        vid = v.id
    finally:
        db.close()

    assert client.get(f"/api/vat-lieu-kho/vat-tu-in-an/{vid}", headers=h).status_code == 200


def test_KHONG_xoa_thanh_pham_duoc(client):
    """PRD L7 — dòng này có thể đang có lô tồn, xoá là làm mồ côi. Ngừng dùng thì tắt active."""
    h = auth_headers(client)
    kh = _khach("xoa")
    tp_id = _khai(_don("xoa-1", kh))[0]
    r = client.delete(f"/api/vat-lieu-kho/thanh-pham/{tp_id}", headers=h)
    assert r.status_code == 422, r.text
    assert "tồn kho" in r.text


def test_sua_duoc_ten_va_DVT_nhung_KHONG_sua_duoc_ma(client):
    """Tên sửa được (gõ sai chính tả phải sửa, và sửa tên là cách gộp hai dòng lỡ đẻ trùng).
    Mã thì không: nó đã nằm trong lô tồn và phiếu đã ghi sổ."""
    h = auth_headers(client)
    kh = _khach("sua")
    tp_id = _khai(_don("sua-1", kh))[0]
    ma_goc = _cua_khach(kh)[0].ma

    r = client.put(f"/api/vat-lieu-kho/thanh-pham/{tp_id}", json={
        "ma": "TP-DOI-MA", "ten": "Tên đã sửa", "don_vi_gia": "thùng",
        "ghi_chu": "ghi thêm", "customer_id": kh,
    }, headers=h)
    assert r.status_code == 200, r.text
    ra = r.json()
    assert ra["ma"] == ma_goc, "mã bị sửa ⇒ mất dấu với lô tồn và phiếu đã ghi sổ"
    assert ra["ten"] == "Tên đã sửa"
    assert ra["don_vi_gia"] == "thùng"


# ------------------------------------------------------------------ quyền


def test_o_quyen_dm_thanh_pham_co_that_va_RIENG(client):
    """Menu riêng ⇒ ô quyền riêng. Một dòng ở `catalog_registry` phải lan ra đủ: khoá quyền ·
    nhãn · seed module."""
    from app.catalog_registry import MODULE_KEYS, MODULES_SEED, theo_loai

    assert "dm_thanh_pham" in MODULE_KEYS
    assert ("dm_thanh_pham", "Thành phẩm") in MODULES_SEED
    d = theo_loai("thanh_pham")
    assert d is not None and d.path == "thanh-pham"
