"""Duyệt nhiều phiếu tạm ứng + lập phiếu chi một lượt (chủ chốt 25/09/2026).

Chủ: *"chọn nhiều nhân viên để lập phiếu thì … bắt tôi chọn từng người duyệt với lập từng phiếu chi
à"*. Giữ bước duyệt, gộp THAO TÁC:

* `POST /api/luong/advances/bulk-decision` — duyệt / từ chối nhiều phiếu; kiểm hết trước, một phiếu
  vướng là không phiếu nào đổi trạng thái.
* `POST /api/accounting/payment-vouchers/from-advances` — chi MỘT LƯỢT ⇒ MỘT phiếu chi cho cả lô
  (chủ đổi ý 25/09/2026: "một hay 1000 nhân viên cùng lúc cũng chỉ 1 phiếu chi"). Số tiền = tổng
  lô, người nhận "Theo bảng kê đính kèm (N người)"; lô một người thì như lập lẻ. Huỷ phiếu chi ⇒
  cả lô về "chờ chi" (không gỡ lẻ từng người).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.employee import Employee
from app.models.payroll import SalaryAdvance

from .test_accounting_api import _headers, _nv_tam_ung, _tam_ung


def _loi(r) -> str:
    """Thao tác hàng loạt bị chặn trả `detail = {message, vuong_ids}`; lỗi thường là chuỗi."""
    d = r.json()["detail"]
    return d["message"] if isinstance(d, dict) else d


def _trang_thai(aid: int) -> str:
    db = SessionLocal()
    try:
        return db.get(SalaryAdvance, aid).status
    finally:
        db.close()


def _khai_ngan_hang(eid: int, so: str, ngan_hang: str) -> None:
    db = SessionLocal()
    try:
        e = db.get(Employee, eid)
        e.bank_account, e.bank_name = so, ngan_hang
        db.commit()
    finally:
        db.close()


def _tai_khoan_cong_ty(client, headers) -> int:
    r = client.post("/api/accounting/company-bank-accounts", json={
        "account_holder": "CÔNG TY SAO VIỆT NHẬT", "account_number": "123456789",
        "bank_name": "Vietcombank", "bank_branch": "Hà Nội", "currency": "VND", "is_default": True,
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_duyet_nhieu_phieu_mot_luot(client):
    h = _headers(client)
    ids = [_tam_ung(client, h, _nv_tam_ung(client, h, ten=f"NV Duyệt {i}"), duyet=False)
           for i in range(3)]

    r = client.post("/api/luong/advances/bulk-decision",
                    json={"ids": ids[:2], "approve": True}, headers=h)
    assert r.status_code == 200, r.text
    assert [a["status"] for a in r.json()["items"]] == ["approved", "approved"]
    assert _trang_thai(ids[2]) == "pending"

    # Một phiếu đã duyệt lẫn vào ⇒ KHÔNG phiếu nào đổi, báo đúng phiếu vướng.
    r = client.post("/api/luong/advances/bulk-decision",
                    json={"ids": [ids[2], ids[0]], "approve": False}, headers=h)
    assert r.status_code == 400, r.text
    assert "Chưa từ chối phiếu nào" in _loi(r)
    assert "đã được xử lý" in _loi(r)
    assert r.json()["detail"]["vuong_ids"] == [ids[0]]      # chỉ đúng phiếu vướng
    assert _trang_thai(ids[2]) == "pending"

    r = client.post("/api/luong/advances/bulk-decision",
                    json={"ids": [ids[2]], "approve": False, "note": "chưa đủ hồ sơ"}, headers=h)
    assert r.status_code == 200, r.text
    assert _trang_thai(ids[2]) == "rejected"


def test_phieu_chi_mot_luot_tien_mat(client):
    h = _headers(client)
    a = _tam_ung(client, h, _nv_tam_ung(client, h, ten="NV Chi Một"), amount=2_000_000)
    b = _tam_ung(client, h, _nv_tam_ung(client, h, ten="NV Chi Hai"), amount=5_000_000,
                 kind="luong_dot_1")
    cho = _tam_ung(client, h, _nv_tam_ung(client, h, ten="NV Chưa Duyệt"), duyet=False)

    # Lẫn một phiếu CHƯA duyệt ⇒ không phiếu chi nào được ghi.
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": [a, b, cho], "voucher_type": "cash", "voucher_date": "2026-08-20",
    }, headers=h)
    assert r.status_code in (400, 422), r.text
    assert "NV Chưa Duyệt" in _loi(r) and "Chưa lập phiếu chi nào" in _loi(r)
    assert r.json()["detail"]["vuong_ids"] == [cho]
    assert _trang_thai(a) == "approved" and _trang_thai(b) == "approved"

    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": [a, b], "voucher_type": "cash", "voucher_date": "2026-08-20",
    }, headers=h)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["total_amount"] == 7_000_000
    [pc] = out["vouchers"]                              # MỘT phiếu chi cho cả lô
    assert pc["amount"] == 7_000_000 and pc["salary_advance_id"] is None
    assert pc["cash_recipient_name"] == "Theo bảng kê đính kèm (2 người)"
    assert pc["content"] == "Chi tạm ứng + lương đợt 1 tháng 08/2026 — 2 người (theo bảng kê)"
    assert _trang_thai(a) == "paid" and _trang_thai(b) == "paid"
    # Cả hai dòng tạm ứng mang CÙNG mã phiếu chi.
    ds = {x["id"]: x for x in client.get("/api/luong/advances", params={"year": 2026, "month": 8},
                                           headers=h).json()["items"]}
    assert ds[a]["phieu_chi_code"] == ds[b]["phieu_chi_code"] == pc["code"]

    # Lập lần hai ⇒ vướng "đã có phiếu chi".
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": [a], "voucher_type": "cash", "voucher_date": "2026-08-20",
    }, headers=h)
    assert r.status_code in (400, 409, 422) and "đã có phiếu chi" in _loi(r)


def test_phieu_chi_mot_luot_chuyen_khoan_lay_tai_khoan_tu_ho_so(client):
    h = _headers(client)
    tk = _tai_khoan_cong_ty(client, h)
    e1 = _nv_tam_ung(client, h, ten="NV CK Có TK")
    e2 = _nv_tam_ung(client, h, ten="NV CK Thiếu TK")
    _khai_ngan_hang(e1, "0011223344", "Techcombank")
    a1, a2 = _tam_ung(client, h, e1), _tam_ung(client, h, e2)
    body = {"salary_advance_ids": [a1, a2], "voucher_type": "bank_transfer",
            "voucher_date": "2026-08-20", "company_bank_account_id": tk}

    r = client.post("/api/accounting/payment-vouchers/from-advances", json=body, headers=h)
    assert r.status_code in (400, 422), r.text
    loi = _loi(r)
    assert "Chưa khai số tài khoản" in loi and "NV CK Thiếu TK" in loi and "NV CK Có TK" not in loi
    assert _trang_thai(a1) == "approved"

    _khai_ngan_hang(e2, "5566778899", "BIDV")
    r = client.post("/api/accounting/payment-vouchers/from-advances", json=body, headers=h)
    assert r.status_code == 201, r.text
    [pc] = r.json()["vouchers"]
    # UNC một lô: thụ hưởng là DANH SÁCH — từng tài khoản nằm ở bảng kê (lấy từ hồ sơ).
    assert pc["voucher_type"] == "bank_transfer"
    assert pc["beneficiary_account_holder"] == "Theo bảng kê đính kèm (2 người)"
    bk = client.get(f"/api/accounting/payment-vouchers/{pc['id']}/bang-ke-tam-ung", headers=h)
    assert bk.status_code == 200, bk.text
    theo = {x["salary_advance_id"]: x for x in bk.json()["rows"]}
    assert theo[a1]["so_tai_khoan"] == "0011223344" and theo[a1]["ngan_hang"] == "Techcombank"
    assert theo[a2]["so_tai_khoan"] == "5566778899"
    assert bk.json()["tong"] == pc["amount"] and bk.json()["so_nguoi"] == 2


def test_chuyen_khoan_thieu_tai_khoan_cong_ty_bao_mot_lan(client):
    """20 phiếu cùng một lỗi chung thì báo MỘT câu, không lặp 20 lần."""
    h = _headers(client)
    ids = []
    for i in range(3):
        e = _nv_tam_ung(client, h, ten=f"NV Gom Lỗi {i}")
        _khai_ngan_hang(e, f"99{i}", "ACB")
        ids.append(_tam_ung(client, h, e))
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": ids, "voucher_type": "bank_transfer", "voucher_date": "2026-08-20",
    }, headers=h)
    assert r.status_code in (400, 422), r.text
    assert _loi(r).count("tài khoản công ty") == 1


def test_lo_mot_nguoi_nhu_lap_le(client):
    """Lô chỉ một người ⇒ phiếu chi ghi TÊN + tài khoản của chính người đó, như lập lẻ."""
    h = _headers(client)
    tk = _tai_khoan_cong_ty(client, h)
    e = _nv_tam_ung(client, h, ten="NV Lô Một")
    _khai_ngan_hang(e, "7788990011", "VCB")
    a = _tam_ung(client, h, e, amount=1_500_000)
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": [a], "voucher_type": "bank_transfer", "voucher_date": "2026-08-20",
        "company_bank_account_id": tk}, headers=h)
    assert r.status_code == 201, r.text
    [pc] = r.json()["vouchers"]
    assert pc["salary_advance_id"] == a and pc["cash_recipient_name"] == "NV Lô Một"
    assert pc["beneficiary_account_number"] == "7788990011"
    assert pc["content"] == "Tạm ứng lương tháng 08/2026 — NV Lô Một"


def test_huy_phieu_chi_lo_ca_lo_ve_cho_chi_va_khong_huy_le(client):
    h = _headers(client)
    ids = [_tam_ung(client, h, _nv_tam_ung(client, h, ten=f"NV Huỷ Lô {i}"), amount=100_000)
           for i in range(3)]
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": ids, "voucher_type": "cash", "voucher_date": "2026-08-20"}, headers=h)
    assert r.status_code == 201, r.text
    [pc] = r.json()["vouchers"]

    # Huỷ LẺ một phiếu tạm ứng trong lô ⇒ chặn, nói rõ mã phiếu chi phải huỷ trước.
    huy = client.post(f"/api/luong/advances/{ids[0]}/cancel", headers=h)
    assert huy.status_code == 400 and pc["code"] in huy.json()["detail"]

    r = client.post(f"/api/accounting/payment-vouchers/{pc['id']}/cancel",
                    json={"reason": "ngân hàng báo lỗi, lập lại"}, headers=h)
    assert r.status_code == 200, r.text
    assert all(_trang_thai(i) == "approved" for i in ids)       # CẢ LÔ về chờ chi
    ds = {x["id"]: x for x in client.get("/api/luong/advances", params={"year": 2026, "month": 8},
                                           headers=h).json()["items"]}
    assert all(ds[i]["phieu_chi_code"] is None for i in ids)

    # Lập lại cho những người đã nhận được tiền (bỏ người cuối) ⇒ phiếu chi MỚI chỉ gồm 2 người.
    r = client.post("/api/accounting/payment-vouchers/from-advances", json={
        "salary_advance_ids": ids[:2], "voucher_type": "cash", "voucher_date": "2026-08-20"},
        headers=h)
    assert r.status_code == 201, r.text
    [pc2] = r.json()["vouchers"]
    assert pc2["amount"] == 200_000 and pc2["code"] != pc["code"]
    assert _trang_thai(ids[2]) == "approved"
