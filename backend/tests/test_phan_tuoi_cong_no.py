"""PHÂN TUỔI CÔNG NỢ PHẢI TRẢ — xé cục "Quá hạn" thành 6 rổ tuổi.

Trước 26/08/2026 màn Công nợ phải trả chỉ có MỘT con số `overdue_amount`: 20 triệu quá hạn có thể
là một đợt trễ 2 ngày, cũng có thể là ba đợt trễ nửa năm — hai ca đó xử lý khác hẳn nhau mà nhìn
vào không phân biệt được. Rổ tuổi xé con số đó ra theo `overdue_days` (đã tính sẵn từ hạn trả của
từng ĐỢT GIAO), KHÔNG tính lại đồng nào.

Ba luật được canh ở đây:

1. **Biên rổ lệch một ngày là sang rổ khác.** 0 · 1 · 7 · 8 · 15 · 16 · 30 · 31 · 60 · 61 phải rơi
   đúng rổ. Mốc chỉ có MỘT nguồn: `AGING_BUCKETS` trong accounting_service.
2. ⭐ **`overdue_amount` cũ == TỔNG 5 rổ trễ.** Đây là test quan trọng nhất cả file. Rổ tuổi là
   phép NHÓM, không phải phép tính mới — hai chỗ nói hai kiểu tiền trên màn công nợ là lỗi nặng
   nhất có thể có, vì không ai phát hiện cho tới lúc ngồi đối chiếu với NCC.
3. **Đợt KHÔNG CÓ HẠN không được rơi vào rổ trễ nào**, và badge "Chưa đặt hạn" phải còn nguyên.
   `credit_days` NULL ⇒ `han_tra_dot` trả None ⇒ đợt đó không bao giờ vào cột Quá hạn; giữ đúng
   hành vi `_no_theo_han` vẫn chạy từ 06/08/2026 (nó nằm ở "chưa tới hạn"), rổ tuổi chỉ thêm rổ
   chứ không đổi chỗ của nó.

Mọi test ở đây chọc SEAM `accounting_service._business_today` để dời "hôm nay", KHÔNG cắm ngày
cứng — cắm cứng là hẹn giờ cho test tự đỏ vài tháng sau.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.services import accounting_service
from app.services.accounting_service import (
    AGING_CHUA_TOI_HAN,
    AGING_KEYS,
    AGING_KEYS_TRE,
    ro_tuoi,
)
from tests.test_payables_api import (
    _cong_no,
    _cong_no_ncc,
    _da_mua,
    _dong_dau_tien,
    _don,
    _ghi_dot,
    _headers,
    _hom_nay,
    _phieu_chi,
    _supplier,
    _ve_hang,
)

# Một đợt 100 tờ × 2.200đ. `_don` mặc định đặt 1000 tờ ⇒ chia vừa đủ 10 đợt.
MOT_DOT = 220_000

# Biên của từng rổ + rổ nó PHẢI rơi vào. Lệch một ngày là sang rổ khác — đó là toàn bộ giá trị của
# việc phân tuổi, nên biên phải được canh chứ không chỉ canh giữa rổ.
RO_THEO_SO_NGAY = {
    0: AGING_CHUA_TOI_HAN,
    1: "d1_7",
    7: "d1_7",
    8: "d8_15",
    15: "d8_15",
    16: "d16_30",
    30: "d16_30",
    31: "d31_60",
    60: "d31_60",
    61: "d60_plus",
}


def _cong_no_loc(client, headers, **params) -> dict:
    r = client.get("/api/accounting/payables", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _muc_ncc(tong: dict, supplier_id: int) -> dict:
    return next(m for m in tong["items"] if m["supplier_id"] == supplier_id)


def _ten_ncc(tong: dict) -> set[str]:
    return {m["supplier_name"] for m in tong["items"]}


def _ro(danh_sach: list[dict], khoa: str) -> dict:
    """Một rổ trong dải `aging` (danh sách CÓ NHÃN mà API trả cho giao diện)."""
    return next(b for b in danh_sach if b["key"] == khoa)


def _don_du_bien(client, headers, supplier_id: int, ngay_soi):
    """Một PMH 10 đợt giao, mỗi đợt đáo hạn đúng một BIÊN rổ tính từ `ngay_soi`.

    Hạn trả đặt tay (`due_date`) vì NCC chưa khai `credit_days`; `han_tra_dot` khi đó lấy đúng
    ngày mình gõ. Ngày giao vẫn là HÔM NAY thật (không được ở tương lai), còn hạn thì nằm sau —
    lúc dời "hôm nay" tới `ngay_soi` mới lần lượt quá hạn.
    """
    don = _don(client, headers, supplier_id)
    _da_mua(client, headers, don["id"])
    for so_ngay in RO_THEO_SO_NGAY:
        _ghi_dot(
            client,
            headers,
            don["id"],
            lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 100}],
            han=(ngay_soi - timedelta(days=so_ngay)).isoformat(),
        )
    return don


# --- 1. biên từng rổ --------------------------------------------------------


@pytest.mark.parametrize("so_ngay,khoa", sorted(RO_THEO_SO_NGAY.items()))
def test_bien_tung_ro_lech_mot_ngay_la_sang_ro_khac(so_ngay: int, khoa: str):
    """Phép gom rổ là hàm THUẦN trên `overdue_days` — canh thẳng ở đây, khỏi dựng 10 đơn hàng."""
    assert ro_tuoi(so_ngay) == khoa


def test_ro_tuoi_khong_de_lot_so_ngay_nao():
    """Không có khe hở giữa hai rổ: mọi số ngày từ -5 tới 400 đều có nhà."""
    for n in range(-5, 401):
        assert ro_tuoi(n) in AGING_KEYS


def test_dot_giao_roi_dung_ro_theo_so_ngay_tre(client, monkeypatch):
    """Vòng đủ: 10 đợt thật, mỗi đợt đáo hạn đúng một biên ⇒ đúng số tiền vào đúng rổ."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Bien Ro")
    ngay_soi = _hom_nay() + timedelta(days=100)
    _don_du_bien(client, headers, supplier["id"], ngay_soi)

    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)
    tong = _cong_no(client, headers)
    muc = _muc_ncc(tong, supplier["id"])

    # 10 đợt: 1 chưa tới hạn · 2 ở mỗi rổ 1–7 / 8–15 / 16–30 / 31–60 · 1 ở rổ > 60.
    assert {k: v["count"] for k, v in muc["aging"].items()} == {
        AGING_CHUA_TOI_HAN: 1,
        "d1_7": 2,
        "d8_15": 2,
        "d16_30": 2,
        "d31_60": 2,
        "d60_plus": 1,
    }
    assert {k: v["amount"] for k, v in muc["aging"].items()} == {
        AGING_CHUA_TOI_HAN: MOT_DOT,
        "d1_7": 2 * MOT_DOT,
        "d8_15": 2 * MOT_DOT,
        "d16_30": 2 * MOT_DOT,
        "d31_60": 2 * MOT_DOT,
        "d60_plus": MOT_DOT,
    }
    # Dải rổ toàn màn có NHÃN đi kèm — giao diện in thẳng nhãn của server, không tự đặt tên rổ
    # (gõ "1–7" ở hai nơi là hai nơi lệch nhau ngay lần đầu chủ đổi mốc).
    assert [b["key"] for b in tong["aging"]] == list(AGING_KEYS)
    assert _ro(tong["aging"], "d60_plus")["label"] == "Trễ > 60 ngày"
    assert _ro(tong["aging"], "d8_15")["min_days"] == 8
    assert _ro(tong["aging"], "d8_15")["max_days"] == 15
    assert _ro(tong["aging"], AGING_CHUA_TOI_HAN)["min_days"] is None
    assert _ro(tong["aging"], "d60_plus")["max_days"] is None


# --- 2. ⭐ bất biến: tiền không được nói hai kiểu ----------------------------


def test_overdue_amount_cu_bang_dung_tong_nam_ro_tre(client, monkeypatch):
    """TEST QUAN TRỌNG NHẤT: `overdue_amount` (nhiều chỗ đang ăn) == tổng 5 rổ trễ.

    Rổ tuổi chỉ XÉ con số cũ ra. Ngày nào hai vế này lệch nhau là ngày màn công nợ bắt đầu nói
    dối, và không ai phát hiện cho tới lúc đối chiếu với NCC."""
    headers = _headers(client)
    a = _supplier(client, headers, name="NCC Bat Bien A")
    b = _supplier(client, headers, name="NCC Bat Bien B")
    ngay_soi = _hom_nay() + timedelta(days=100)
    _don_du_bien(client, headers, a["id"], ngay_soi)
    # NCC thứ hai: một đợt CHƯA tới hạn — để tổng màn không chỉ toàn nợ trễ.
    don_b = _don(client, headers, b["id"], quantity=500)
    _da_mua(client, headers, don_b["id"])
    _ghi_dot(
        client,
        headers,
        don_b["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don_b), "quantity": 500}],
        han=(ngay_soi + timedelta(days=10)).isoformat(),
    )

    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)
    tong = _cong_no(client, headers)

    tre = sum(_ro(tong["aging"], k)["amount"] for k in AGING_KEYS_TRE)
    assert tre == tong["overdue_amount"], "tổng 5 rổ trễ phải khớp con số Quá hạn cũ"
    ca_sau_ro = sum(b["amount"] for b in tong["aging"])
    assert ca_sau_ro == tong["total_due"], "gộp 6 rổ lại phải ra đúng Tổng phải trả"

    for muc in (_muc_ncc(tong, a["id"]), _muc_ncc(tong, b["id"])):
        tre_ncc = sum(muc["aging"][k]["amount"] for k in AGING_KEYS_TRE)
        assert tre_ncc == muc["overdue_amount"]
        assert muc["aging"][AGING_CHUA_TOI_HAN]["amount"] == muc["no_han_amount"]
        assert sum(v["amount"] for v in muc["aging"].values()) == muc["total_due"]

    # Drawer một NCC cũng phải khớp với chính nó — pill và bảng dưới nó cùng một phép đếm.
    chi_tiet = _cong_no_ncc(client, headers, a["id"])
    tre_drawer = sum(_ro(chi_tiet["aging"], k)["amount"] for k in AGING_KEYS_TRE)
    assert tre_drawer == chi_tiet["overdue_amount"]
    assert sum(b["amount"] for b in chi_tiet["aging"]) == chi_tiet["total_due"]
    assert sum(b["count"] for b in chi_tiet["aging"]) == len(chi_tiet["items"])


# --- 3. đợt không có hạn: không rổ trễ nào được nuốt nó ---------------------


def test_dot_khong_co_han_khong_vao_ro_tre_nao_va_van_deo_badge(client, monkeypatch):
    """`credit_days` NULL + không gõ hạn tay ⇒ đợt KHÔNG CÓ HẠN.

    Nó ở lại rổ "chưa tới hạn" (đúng chỗ `_no_theo_han` vẫn xếp nó từ 06/08/2026) và tuyệt đối
    không được rơi vào rổ trễ nào — dù có dời "hôm nay" đi bao xa. Badge "Chưa đặt hạn" ở danh
    sách chi tiết phải còn nguyên: mất badge là món nợ đó lặng lẽ nằm ngoài mọi cảnh báo."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Khong Han")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client,
        headers,
        don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
    )

    # Dời hôm nay đi cả năm: đợt có hạn thì đã trễ 365 ngày, đợt không hạn vẫn phải đứng yên.
    # Chốt mốc TRƯỚC khi vá seam — `_hom_nay()` đọc chính seam đó, gọi trong lambda là đệ quy.
    ngay_soi = _hom_nay() + timedelta(days=365)
    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)
    tong = _cong_no(client, headers)
    muc = _muc_ncc(tong, supplier["id"])
    assert muc["overdue_amount"] == 0
    assert all(muc["aging"][k]["amount"] == 0 for k in AGING_KEYS_TRE)
    assert all(muc["aging"][k]["count"] == 0 for k in AGING_KEYS_TRE)
    assert muc["aging"][AGING_CHUA_TOI_HAN]["amount"] == 2_200_000
    assert muc["aging"][AGING_CHUA_TOI_HAN]["count"] == 1

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    dong = chi_tiet["items"][0]
    assert dong["due_date"] is None
    assert dong["chua_dat_han"] is True, "badge 'Chưa đặt hạn' phải còn nguyên"
    assert dong["overdue_days"] == 0
    assert _ro(chi_tiet["aging"], AGING_CHUA_TOI_HAN)["amount"] == 2_200_000
    assert all(_ro(chi_tiet["aging"], k)["amount"] == 0 for k in AGING_KEYS_TRE)


def test_don_cu_khong_theo_dot_van_nam_o_ro_chua_toi_han(client, monkeypatch):
    """Phiếu CŨ không theo dõi theo đợt: nợ chỉ quy được về mức PHIẾU, không có hạn ⇒ y hệt ca
    trên. Đây đúng là nhánh `return 0, con_no` của `_no_theo_han` — giữ nguyên, chỉ thêm rổ."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Don Cu")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    ngay_soi = _hom_nay() + timedelta(days=90)  # chốt mốc TRƯỚC khi vá seam, xem ghi chú trên
    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)
    muc = _muc_ncc(_cong_no(client, headers), supplier["id"])
    assert muc["total_due"] == 2_200_000
    assert muc["aging"][AGING_CHUA_TOI_HAN]["amount"] == 2_200_000
    assert muc["aging"][AGING_CHUA_TOI_HAN]["count"] == 1
    assert all(muc["aging"][k]["amount"] == 0 for k in AGING_KEYS_TRE)


# --- 4. lọc theo rổ ---------------------------------------------------------


def test_loc_theo_ro_tra_dung_tap_ncc(client, monkeypatch):
    """Bấm một rổ ⇒ bảng chỉ còn NCC có tiền trong rổ đó. Thẻ tổng ở đầu màn KHÔNG đổi theo —
    dải mà nhảy theo bộ lọc thì nó đang đo cái bộ lọc, không đo món nợ."""
    headers = _headers(client)
    gia = _supplier(client, headers, name="NCC No Gia")
    moi = _supplier(client, headers, name="NCC No Moi")
    ngay_soi = _hom_nay() + timedelta(days=100)
    _don_du_bien(client, headers, gia["id"], ngay_soi)
    don_moi = _don(client, headers, moi["id"], quantity=500)
    _da_mua(client, headers, don_moi["id"])
    _ghi_dot(
        client,
        headers,
        don_moi["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don_moi), "quantity": 500}],
        han=(ngay_soi + timedelta(days=10)).isoformat(),
    )

    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)

    chi_gia = _cong_no_loc(client, headers, aging_bucket="d60_plus")
    assert _ten_ncc(chi_gia) == {"NCC No Gia"}
    ca_hai = _cong_no_loc(client, headers, aging_bucket=AGING_CHUA_TOI_HAN)
    assert _ten_ncc(ca_hai) == {"NCC No Gia", "NCC No Moi"}
    assert _ten_ncc(_cong_no_loc(client, headers, aging_bucket="d8_15")) == {"NCC No Gia"}

    # Thẻ tổng + dải rổ tính trên TOÀN BỘ NCC, không đổi theo bộ lọc đang bấm.
    khong_loc = _cong_no(client, headers)
    assert chi_gia["total_due"] == khong_loc["total_due"]
    assert chi_gia["aging"] == khong_loc["aging"]

    # Khoá lạ ⇒ BỎ QUA, y như `filter` lạ. Cửa lọc không phải chỗ ném lỗi vào mặt kế toán.
    assert _ten_ncc(_cong_no_loc(client, headers, aging_bucket="d999")) == _ten_ncc(khong_loc)


def test_loc_ro_di_chung_duoc_voi_o_tim(client, monkeypatch):
    headers = _headers(client)
    gia = _supplier(client, headers, name="NCC Tim Gia")
    khac = _supplier(client, headers, name="NCC Tim Khac")
    ngay_soi = _hom_nay() + timedelta(days=100)
    _don_du_bien(client, headers, gia["id"], ngay_soi)
    _don_du_bien(client, headers, khac["id"], ngay_soi)

    monkeypatch.setattr(accounting_service, "_business_today", lambda: ngay_soi)
    ra = _cong_no_loc(client, headers, aging_bucket="d31_60", q="Tim Gia")
    assert _ten_ncc(ra) == {"NCC Tim Gia"}


# --- 5. NCC không nợ gì -----------------------------------------------------


def test_ncc_da_tra_het_thi_moi_ro_bang_khong_va_khong_no(client):
    """Trả hết ⇒ 6 rổ đều 0 mà KHÔNG lỗi, và dòng NCC vẫn còn (nhờ tiền đã trả trong kỳ).

    Thiếu khoá rổ nào là giao diện đọc ra `undefined` rồi in "NaN đ" — đủ 6 rổ = 0 mới đúng."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tra Het")
    don = _don(client, headers, supplier["id"], coc=2_200_000)
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 2_200_000)

    muc = _muc_ncc(_cong_no(client, headers), supplier["id"])
    assert muc["total_due"] == 0
    assert muc["paid_in_period"] == 2_200_000
    assert set(muc["aging"]) == set(AGING_KEYS)
    assert all(v == {"amount": 0, "count": 0} for v in muc["aging"].values())

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert [b["key"] for b in chi_tiet["aging"]] == list(AGING_KEYS)
    assert all(b["amount"] == 0 and b["count"] == 0 for b in chi_tiet["aging"])
