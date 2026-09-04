"""Unit tests cho khóa sổ kỳ công nợ (chốt công nợ) và báo cáo công nợ chi tiết."""
from __future__ import annotations

from datetime import date, timedelta


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_get_cong_no_ky_list(client):
    """Danh sách kỳ = các LẦN CHỐT + kỳ hiện tại. KHÔNG còn 12 tháng lịch tự sinh (04/09/2026).

    Chưa chốt kỳ nào thì chỉ có đúng một mục: kỳ hiện tại, chưa chốt.
    """
    from datetime import date

    headers = _headers(client)
    r = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1, f"chưa chốt kỳ nào thì chỉ có kỳ hiện tại: {data}"
    assert data[0]["dang_dien_ra"] is True
    assert data[0]["da_khoa"] is False
    assert data[0]["den_ngay"] == date.today().isoformat()


def test_chot_ky_va_mo_ky(client):
    """Chốt rồi mở lại một kỳ ĐÃ KẾT THÚC.

    Đổi từ tháng ĐANG CHẠY sang THÁNG TRƯỚC (04/09/2026): từ khi chặn chốt sổ cho tương lai, khóa
    cả tháng hiện tại là 422 — mà đó đúng là hành vi cần chặn, không phải test sai. Kỳ để chốt sổ
    thì cũng phải là kỳ đã qua mới có nghĩa.
    """
    headers = _headers(client)
    today = date.today()
    # Ngày 0 của tháng này = ngày cuối tháng trước; khỏi phải nhớ tháng nào 30 hay 31.
    den = date(today.year, today.month, 1) - timedelta(days=1)
    tu = den.replace(day=1)

    # 1. Khóa kỳ
    r_lock = client.post(
        "/api/accounting/khoa-so",
        json={
            "phan_he": "phai_tra",
            "tu_ngay": tu.isoformat(),
            "den_ngay": den.isoformat(),
            "hanh_dong": "khoa",
            "ten": f"Kỳ test {today.month}/{today.year}",
        },
        headers=headers,
    )
    assert r_lock.status_code == 201, r_lock.text
    res_lock = r_lock.json()
    assert res_lock["hanh_dong"] == "khoa"

    # 2. Lấy lịch sử
    r_hist = client.get("/api/accounting/khoa-so", headers=headers)
    assert r_hist.status_code == 200
    hist = r_hist.json()
    assert any(h["id"] == res_lock["id"] for h in hist)

    # 3. Mở khóa kỳ
    r_unlock = client.post(
        "/api/accounting/khoa-so",
        json={
            "phan_he": "phai_tra",
            "tu_ngay": tu.isoformat(),
            "den_ngay": den.isoformat(),
            "hanh_dong": "mo",
        },
        headers=headers,
    )
    assert r_unlock.status_code == 201, r_unlock.text
    assert r_unlock.json()["hanh_dong"] == "mo"


def test_cong_no_chi_tiet_phai_thu(client):
    headers = _headers(client)
    r = client.get("/api/accounting/cong-no-chi-tiet/phai-thu", headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_cong_no_chi_tiet_phai_tra(client):
    headers = _headers(client)
    r = client.get("/api/accounting/cong-no-chi-tiet/phai-tra", headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ══ BA LỖI CỦA 04/09/2026 ═══════════════════════════════════════════════════════════════════
#
# Chủ báo: *"chọn khóa kỳ từ 01/09 đến 03/09 không được, mà nay mới 04/09 lại chọn được ngày
# tương lai vì đến ngày nó hiện 30/09"*. Soi DB dev thấy log khóa 01/09–03/09 ghi thành công tới
# BỐN lần (#2 #3 #4 #6) mà màn hình vẫn báo chưa khóa — bấm rồi không thấy gì nên bấm lại.


def _khoa(client, headers, tu: str, den: str, *, hanh_dong: str = "khoa",
          phan_he: str = "phai_tra", expect: int = 201):
    r = client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": phan_he, "tu_ngay": tu, "den_ngay": den,
              "hanh_dong": hanh_dong, "ten": "Kỳ thử"},
        headers=headers,
    )
    assert r.status_code == expect, r.text
    return r


def _trang_thai(client, headers, tu: str, den: str, phan_he: str = "phai_tra") -> dict:
    r = client.get(
        "/api/accounting/khoa-so/trang-thai",
        params={"tu_ngay": tu, "den_ngay": den, "phan_he": phan_he},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_khoa_mot_phan_khong_duoc_bao_la_da_khoa(client):
    """⭐ Lỗi chính. Khóa 01–03 rồi hỏi trạng thái CẢ THÁNG phải ra "một phần", KHÔNG phải "đã khóa".

    Bản cũ hỏi `is_locked(ngày cuối kỳ)` nên sai theo cả hai chiều: khóa đầu kỳ thì báo chưa khóa,
    mà khóa lọt ngày cuối thì báo đã khóa trọn dù giữa kỳ còn hở.
    """
    from datetime import date, timedelta

    headers = _headers(client)
    hom_qua = date.today() - timedelta(days=1)
    dau_thang = hom_qua.replace(day=1)
    if dau_thang == hom_qua:                      # mùng 1: lùi sang tháng trước cho có khoảng
        hom_qua = dau_thang - timedelta(days=1)
        dau_thang = hom_qua.replace(day=1)

    _khoa(client, headers, dau_thang.isoformat(), dau_thang.isoformat())

    tt = _trang_thai(client, headers, dau_thang.isoformat(), hom_qua.isoformat())
    assert tt["khoa_mot_phan"] is True, "khóa đúng 1 ngày trong kỳ ⇒ MỘT PHẦN"
    assert tt["da_khoa"] is False, "chưa khóa trọn thì không được báo đã khóa"

    # Chốt NỐT phần còn lại — bắt đầu từ ngày kế tiếp, không đè lên ngày đã chốt (nếu đè thì
    # server chặn 422, xem `test_khong_chot_chong_lan_ky_da_chot`).
    _khoa(client, headers, (dau_thang + timedelta(days=1)).isoformat(), hom_qua.isoformat())
    tt = _trang_thai(client, headers, dau_thang.isoformat(), hom_qua.isoformat())
    assert tt["da_khoa"] is True and tt["khoa_mot_phan"] is False


def test_khoa_dung_ngay_cuoi_khong_lam_ca_ky_thanh_da_khoa(client):
    """Chiều ngược lại — NGUY HIỂM HƠN: sổ nói "đã chốt" trong khi đầu kỳ còn mở toang."""
    from datetime import date, timedelta

    headers = _headers(client)
    hom_qua = date.today() - timedelta(days=1)
    dau_thang = hom_qua.replace(day=1)
    if dau_thang == hom_qua:
        hom_qua = dau_thang - timedelta(days=1)
        dau_thang = hom_qua.replace(day=1)

    _khoa(client, headers, hom_qua.isoformat(), hom_qua.isoformat())
    tt = _trang_thai(client, headers, dau_thang.isoformat(), hom_qua.isoformat())
    assert tt["da_khoa"] is False, "khóa mỗi ngày cuối mà báo cả kỳ đã chốt là NÓI DỐI"
    assert tt["khoa_mot_phan"] is True


def test_khong_chot_so_cho_tuong_lai(client):
    """Chốt sổ = "kỳ này xong, số đã chốt". Chốt cho ngày chưa xảy ra thì chốt cái gì?"""
    from datetime import date, timedelta

    headers = _headers(client)
    mai = date.today() + timedelta(days=1)
    r = _khoa(client, headers, date.today().isoformat(), mai.isoformat(), expect=422)
    assert "tương lai" in r.json()["detail"].lower()

    # MỞ khóa thì vẫn cho, kể cả khoảng trót phủ sang tương lai — gỡ bản ghi lỡ tay phải luôn làm được.
    _khoa(client, headers, date.today().isoformat(), mai.isoformat(), hanh_dong="mo", expect=201)


def test_ky_dang_chay_dung_o_hom_nay_khong_chay_toi_cuoi_thang(client):
    """Kỳ tháng ĐANG CHẠY phải kết ở hôm nay. Trước đó luôn hiện tới cuối tháng, nên hộp khóa kỳ
    mặc định đề nghị chốt sổ cho những ngày chưa tới."""
    from datetime import date

    headers = _headers(client)
    r = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"}, headers=headers)
    assert r.status_code == 200, r.text
    ky = r.json()[0]                                   # kỳ đầu danh sách = kỳ chưa chốt
    hom_nay = date.today()
    assert ky["dang_dien_ra"] is True
    assert ky["den_ngay"] == hom_nay.isoformat(), "kỳ đang chạy không được vượt hôm nay"
    # Chưa chốt kỳ nào ⇒ tính từ đầu năm. (Đã chốt rồi thì nối sau mốc chốt cuối — canh riêng ở
    # `test_ky_hien_tai_noi_ngay_sau_ky_da_chot`.)
    assert ky["tu_ngay"] == date(hom_nay.year, 1, 1).isoformat()


# ══ KỲ = LẦN CHỐT, KHÔNG PHẢI THÁNG LỊCH (chủ chốt 04/09/2026) ══════════════════════════════
#
# *"những kì mà mình bấm chốt"* + *"đừng cho chọn ngày tương lai với trùng ngày đã chốt của kì
# trước"*. Kế toán ở đây chốt sổ theo kỳ TỰ ĐẶT, có tên riêng ("Chốt kì 1 2026", 03/07–03/09) —
# không phải tháng lịch. Trộn hai lối đánh kỳ vào một màn chính là thứ đẻ ra mớ "Chốt một phần".


def test_danh_sach_ky_la_cac_lan_da_chot(client):
    """Kỳ chốt xong phải hiện trong danh sách kỳ, kèm ĐÚNG tên kế toán đặt."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=3)
    tu = den - timedelta(days=5)
    r = client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": "phai_tra", "tu_ngay": tu.isoformat(), "den_ngay": den.isoformat(),
              "hanh_dong": "khoa", "ten": "Chốt kì thử nghiệm"},
        headers=headers,
    )
    assert r.status_code == 201, r.text

    ky = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"},
                    headers=headers).json()
    khop = [k for k in ky if k["tu_ngay"] == tu.isoformat() and k["den_ngay"] == den.isoformat()]
    assert len(khop) == 1, f"kỳ vừa chốt phải có trong danh sách: {ky}"
    assert khop[0]["ten"] == "Chốt kì thử nghiệm", "phải giữ tên kế toán đặt, không đổi thành 'Tháng 09/2026'"
    assert khop[0]["da_khoa"] is True


def test_ky_hien_tai_noi_ngay_sau_ky_da_chot(client):
    """Kỳ hiện tại (chưa chốt) bắt đầu ĐÚNG ngày sau mốc chốt cuối — không hở, không đè."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=3)
    tu = den - timedelta(days=5)
    client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": "phai_tra", "tu_ngay": tu.isoformat(), "den_ngay": den.isoformat(),
              "hanh_dong": "khoa", "ten": "K"},
        headers=headers,
    )
    ky = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"},
                    headers=headers).json()
    hien_tai = ky[0]
    assert hien_tai["dang_dien_ra"] is True, "kỳ chưa chốt phải đứng ĐẦU danh sách"
    assert hien_tai["tu_ngay"] == (den + timedelta(days=1)).isoformat()
    assert hien_tai["den_ngay"] == date.today().isoformat()


def test_khong_chot_chong_lan_ky_da_chot(client):
    """⭐ Hai kỳ cùng nhận một ngày ⇒ dư cuối kỳ này và đầu kỳ kia đếm trùng chứng từ."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=3)
    tu = den - timedelta(days=5)
    client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": "phai_tra", "tu_ngay": tu.isoformat(), "den_ngay": den.isoformat(),
              "hanh_dong": "khoa", "ten": "K1"},
        headers=headers,
    )
    # Đè lên đúng một ngày của kỳ trên.
    r = client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": "phai_tra", "tu_ngay": den.isoformat(),
              "den_ngay": date.today().isoformat(), "hanh_dong": "khoa", "ten": "K2"},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "chồng lấn" in r.json()["detail"].lower()

    # Nối SAU kỳ cũ thì phải cho.
    r2 = client.post(
        "/api/accounting/khoa-so",
        json={"phan_he": "phai_tra", "tu_ngay": (den + timedelta(days=1)).isoformat(),
              "den_ngay": date.today().isoformat(), "hanh_dong": "khoa", "ten": "K2"},
        headers=headers,
    )
    assert r2.status_code == 201, r2.text


def test_mo_lai_ky_thi_no_bien_khoi_danh_sach(client):
    """Mở lại toàn phần ⇒ không còn là kỳ đã chốt nữa, phải rời danh sách."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=3)
    tu = den - timedelta(days=5)
    for hd in ("khoa", "mo"):
        client.post(
            "/api/accounting/khoa-so",
            json={"phan_he": "phai_tra", "tu_ngay": tu.isoformat(),
                  "den_ngay": den.isoformat(), "hanh_dong": hd, "ten": "K"},
            headers=headers,
        )
    ky = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"},
                    headers=headers).json()
    assert not [k for k in ky if k["tu_ngay"] == tu.isoformat() and k["den_ngay"] == den.isoformat()]


def test_ba_cot_tien_cua_dot_phai_tru_ra_nhau(client):
    """⭐ `Giá trị đợt − Đã trả = Còn nợ`, từng dòng một.

    Chủ hỏi 04/09/2026: *"Giá trị đợt với Còn nợ khác gì nhau không"* — hỏi vì màn hình hiện
    "Giá trị đợt 0đ · Đã trả 0đ · Còn nợ 1.305.000.000đ". Ba cột cạnh nhau mà không trừ ra nhau.

    Gốc: chỗ dựng bảng đọc `dot["delivery_value"]` / `dot["paid_amount"]`, trong khi
    `_no_tung_dot` trả `amount` / `paid` / `coc_bu`. Hai tên không tồn tại, `.get(..., 0)` nuốt
    gọn thành 0 — không lỗi, không cảnh báo, chỉ có số sai. Đây là lý do bài này so ĐẲNG THỨC chứ
    không so từng con số: đẳng thức bắt được cả lỗi đọc nhầm khoá lẫn lỗi tính.
    """
    from tests.test_payables_api import (
        _da_mua, _dong_dau_tien, _don, _ghi_dot, _phieu_chi, _supplier,
    )

    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Ba Cot")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )                                                     # 400 × 2.200 = 880.000
    _phieu_chi(
        client, headers, don["id"], 300_000,
        stage="final", delivery_id=dot["deliveries"][0]["id"],
    )

    r = client.get("/api/accounting/cong-no-chi-tiet/phai-tra", headers=headers)
    assert r.status_code == 200, r.text
    muc = next(x for x in r.json() if x["supplier_id"] == ncc["id"])
    assert muc["items"], "NCC có đợt giao thì phải có dòng chi tiết"
    for it in muc["items"]:
        assert it["delivery_value"] - it["paid_amount"] == it["con_no"], (
            f"ba cột không trừ ra nhau: {it}"
        )
    d = muc["items"][0]
    assert d["delivery_value"] == 880_000, "giá trị đợt KHÔNG được là 0"
    assert d["paid_amount"] == 300_000
    assert d["con_no"] == 580_000
    assert d["seq_no"] == 1, "số đợt là thứ tự TRONG ĐƠN, không phải id bản ghi"


# ══ ĐÃ CÓ KỲ CHỐT SAU ⇒ KỲ TRƯỚC NIÊM VĨNH VIỄN (chủ chốt 04/09/2026) ═══════════════════════
#
# *"Không cho luôn, đã tạo ra kì mới rồi thì không cho mở nữa"*.
#
# Số dư ĐẦU kỳ tháng 9 lấy từ số dư CUỐI kỳ tháng 8 — mở tháng 8 ra sửa là rút gốc của kỳ đã đóng.
# KHÔNG phải tháo ngược từng nấc: mở kỳ 9 ra rồi thì kỳ 8 VẪN niêm. Xét trên LỊCH SỬ chốt, không
# phải trạng thái khóa hiện tại.
#
# Van an toàn duy nhất là kỳ MỚI NHẤT — chưa có kỳ nào chốt sau nó thì mở thoải mái.


def _hai_ky_lien_tiep():
    """Hai kỳ nối nhau, đều đã kết thúc: (kỳ trước, kỳ sau)."""
    from datetime import date, timedelta

    sau_den = date.today() - timedelta(days=1)
    sau_tu = sau_den - timedelta(days=4)
    truoc_den = sau_tu - timedelta(days=1)
    truoc_tu = truoc_den - timedelta(days=4)
    return (truoc_tu, truoc_den), (sau_tu, sau_den)


def test_chot_ky_sau_roi_thi_ky_truoc_khong_mo_duoc(client):
    """⭐ Chốt kỳ trước → chốt kỳ sau → mở kỳ trước phải bị CHẶN, kèm chỉ rõ kỳ nào đang chặn."""
    headers = _headers(client)
    (t_tu, t_den), (s_tu, s_den) = _hai_ky_lien_tiep()

    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat())
    # Mở lại lúc CHƯA có kỳ sau ⇒ phải được.
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat(), hanh_dong="mo")
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat())

    _khoa(client, headers, s_tu.isoformat(), s_den.isoformat())

    r = _khoa(client, headers, t_tu.isoformat(), t_den.isoformat(), hanh_dong="mo", expect=422)
    chi_tiet = r.json()["detail"]
    assert "niêm" in chi_tiet.lower(), chi_tiet
    assert s_tu.strftime("%d/%m/%Y") in chi_tiet, "phải chỉ rõ kỳ nào niêm nó lại"


def test_mo_ky_sau_van_khong_cuu_duoc_ky_truoc(client):
    """⭐ Bài ĐẢO 04/09/2026. Trước đó luật là "tháo ngược từng nấc" — mở kỳ sau xong thì kỳ trước
    mở được. Chủ bác: *"không cho luôn"*.

    Niêm là niêm: kỳ sau dù đã mở ra, kỳ trước VẪN không mở được. Luật xét trên LỊCH SỬ chốt, nên
    một khi kỳ sau đã từng ra đời thì kỳ trước hết đường lùi.
    """
    headers = _headers(client)
    (t_tu, t_den), (s_tu, s_den) = _hai_ky_lien_tiep()
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat())
    _khoa(client, headers, s_tu.isoformat(), s_den.isoformat())

    _khoa(client, headers, s_tu.isoformat(), s_den.isoformat(), hanh_dong="mo")
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat(), hanh_dong="mo", expect=422)

    tt = _trang_thai(client, headers, t_tu.isoformat(), t_den.isoformat())
    assert tt["da_khoa"] is True, "kỳ trước phải còn nguyên trạng thái đã chốt"


def test_ky_moi_nhat_van_la_van_an_toan(client):
    """Chốt nhầm mà phát hiện NGAY thì vẫn cứu được — chưa có kỳ nào sau nó."""
    headers = _headers(client)
    (t_tu, t_den), _ = _hai_ky_lien_tiep()
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat())
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat(), hanh_dong="mo", expect=201)
    tt = _trang_thai(client, headers, t_tu.isoformat(), t_den.isoformat())
    assert tt["da_khoa"] is False


def test_danh_sach_ky_noi_ro_ky_nao_mo_duoc(client):
    """Giao diện MỜ nút thay vì cho bấm rồi ăn 422 ⇒ server phải nói trước `co_the_mo`."""
    headers = _headers(client)
    (t_tu, t_den), (s_tu, s_den) = _hai_ky_lien_tiep()
    _khoa(client, headers, t_tu.isoformat(), t_den.isoformat())
    _khoa(client, headers, s_tu.isoformat(), s_den.isoformat())

    ky = client.get("/api/accounting/khoa-so/ky", params={"phan_he": "phai_tra"},
                    headers=headers).json()
    truoc = next(k for k in ky if k["tu_ngay"] == t_tu.isoformat())
    sau = next(k for k in ky if k["tu_ngay"] == s_tu.isoformat())
    assert sau["co_the_mo"] is True, "kỳ mới nhất luôn mở được (van an toàn)"
    assert truoc["co_the_mo"] is False, "kỳ đã có kỳ chốt sau thì niêm vĩnh viễn"


# ══ HAI SỔ ĐỘC LẬP — 131 và 331 KHÔNG khoá lây nhau (chủ báo 04/09/2026) ═════════════════════
#
# *"Tôi mới chốt công nợ phải trả sao nó tự động chốt công nợ phải thu, 2 cái này nó khác nhau
# mà"*. Đúng. Bảng `cong_no_khoa_so` dựng ra KHÔNG có cột nào phân biệt 131 với 331, nên một bản
# ghi khoá là khoá cả hai sổ. Đã thêm cột `phan_he` (migration 0259).


def test_chot_phai_tra_khong_lam_phai_thu_bi_khoa_theo(client):
    """⭐ Bài quan trọng nhất của cụm: khoá 331 xong thì 131 phải còn nguyên đang mở."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=1)
    tu = den - timedelta(days=4)

    _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he="phai_tra")

    tra = _trang_thai(client, headers, tu.isoformat(), den.isoformat(), "phai_tra")
    thu = _trang_thai(client, headers, tu.isoformat(), den.isoformat(), "phai_thu")
    assert tra["da_khoa"] is True, "sổ vừa chốt phải khoá"
    assert thu["da_khoa"] is False, "sổ BÊN KIA phải còn mở — hai sổ độc lập"
    assert thu["khoa_mot_phan"] is False


def test_hai_so_chot_cung_khoang_ngay_khong_bao_chong_lan(client):
    """Cùng một khoảng ngày, chốt được CẢ HAI sổ — chúng không đè lên nhau.

    Luật chống chồng lấn chỉ áp TRONG cùng một phân hệ; nếu xét chung thì chốt 331 xong là 131
    báo 422 "chồng lấn" cho đúng cái khoảng mà nó chưa hề chốt.
    """
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=1)
    tu = den - timedelta(days=4)

    _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he="phai_tra")
    _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he="phai_thu", expect=201)

    for ph in ("phai_tra", "phai_thu"):
        assert _trang_thai(client, headers, tu.isoformat(), den.isoformat(), ph)["da_khoa"] is True


def test_danh_sach_ky_tach_theo_phan_he(client):
    """Ô "Kỳ kế toán" của tab phải trả không được hiện kỳ của tab phải thu."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=1)
    tu = den - timedelta(days=4)
    _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he="phai_tra")

    def _ky(ph):
        return client.get("/api/accounting/khoa-so/ky", params={"phan_he": ph},
                          headers=headers).json()

    da_chot = [k for k in _ky("phai_tra") if not k["dang_dien_ra"]]
    ben_kia = [k for k in _ky("phai_thu") if not k["dang_dien_ra"]]
    assert len(da_chot) == 1 and da_chot[0]["tu_ngay"] == tu.isoformat()
    assert ben_kia == [], "sổ chưa chốt gì thì danh sách kỳ đã chốt phải rỗng"


def test_mo_ky_ben_nay_khong_mo_ben_kia(client):
    """Mở 331 ra thì 131 vẫn khoá — và ngược lại."""
    from datetime import date, timedelta

    headers = _headers(client)
    den = date.today() - timedelta(days=1)
    tu = den - timedelta(days=4)
    for ph in ("phai_tra", "phai_thu"):
        _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he=ph)

    _khoa(client, headers, tu.isoformat(), den.isoformat(), phan_he="phai_tra", hanh_dong="mo")

    assert _trang_thai(client, headers, tu.isoformat(), den.isoformat(), "phai_tra")["da_khoa"] is False
    assert _trang_thai(client, headers, tu.isoformat(), den.isoformat(), "phai_thu")["da_khoa"] is True
