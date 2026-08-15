"""Phân hệ Kế toán — mỗi MÀN một ô quyền riêng (tách 10/08/2026).

Trước bản này cả phân hệ treo trên một khoá `ke_toan`: bật `can_read` là mở luôn 6 màn, còn
`can_approve` là cờ vạn năng cho "lập phiếu chi", "lập phiếu thu" và "gán chứng từ" — bật một ô là
tiền ra được. Đó là bệnh #5 tester ghi: *"bật Xem là hiện hết mọi chức năng kế toán"*.

Test ở đây giữ hai chiều của hàng rào: cấp đúng màn thì VÀO được, không cấp thì 403.
"""

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

# Màn → (khoá quyền, một đường GET chỉ màn đó mở được).
MAN_KE_TOAN = (
    ("Đơn mua hàng", "ke_toan", "/api/accounting/inbox"),
    ("Phiếu chi", "phieu_chi", "/api/accounting/payment-vouchers"),
    ("Phiếu thu", "phieu_thu", "/api/accounting/payment-receipts"),
    ("Công nợ phải trả", "cong_no_phai_tra", "/api/accounting/payables"),
    ("Công nợ phải thu", "cong_no_phai_thu", "/api/accounting/receivables"),
    ("Tài khoản ngân hàng", "tk_ngan_hang", "/api/accounting/company-bank-accounts"),
)


def _token_mot_man(khoa: str, hau_to: str = "", **co) -> str:
    """Tài khoản được cấp ĐÚNG MỘT khoá của phân hệ Kế toán.

    `hau_to` để dựng HAI người khác nhau trên cùng một khoá (vd chỉ-Xem và Xem+Lập). Thiếu nó thì
    lần gọi thứ hai đụng đúng tài khoản đã tạo ở lần đầu và trả về bộ quyền cũ — test sẽ nói dối.
    """
    db = SessionLocal()
    try:
        users = UserRepository(db)
        uname = f"chi-man-{khoa.replace('_', '-')}{hau_to}"
        existing = users.get_by_username(uname)
        if existing is not None:
            return create_access_token(str(existing.id))
        dept = DepartmentRepository(db).get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(name=f"Chi man {khoa}{hau_to}", department_id=dept.id)
        roles.set_permission(role_id=role.id, module_key=khoa, scope=SCOPE_ALL, **co)
        u = users.create(username=uname, name=uname, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_moi_man_ke_toan_gac_bang_khoa_rieng(client):
    """Cấp Xem của một màn ⇒ đúng màn đó mở, năm màn còn lại 403."""
    for ten, khoa, duong in MAN_KE_TOAN:
        h = _h(_token_mot_man(khoa, can_read=True))

        mo = client.get(duong, headers=h)
        assert mo.status_code == 200, f"cấp {khoa} mà không mở được {ten}: {mo.text}"

        for ten_khac, khoa_khac, duong_khac in MAN_KE_TOAN:
            if khoa_khac == khoa:
                continue
            r = client.get(duong_khac, headers=h)
            assert r.status_code == 403, (
                f"chỉ cấp {khoa} mà vẫn vào được {ten_khac} ({duong_khac}) — {r.status_code}"
            )


def test_xem_phieu_chi_khong_keo_theo_quyen_lap_phieu(client):
    """XEM và LẬP là hai ô khác nhau — đây là chỗ tiền rời két nên phải tách thật.

    Cũng ghim luôn tên động từ mới: LẬP phiếu là `can_create`, không phải `can_approve` như tên cũ.
    """
    chi_xem = _h(_token_mot_man("phieu_chi", can_read=True))
    assert client.get("/api/accounting/payment-vouchers", headers=chi_xem).status_code == 200
    lap = client.post(
        "/api/accounting/payment-vouchers",
        json={"voucher_type": "cash", "amount_vnd": 500_000, "purchase_request_id": 1},
        headers=chi_xem,
    )
    assert lap.status_code == 403, f"chỉ có Xem mà vẫn lập được phiếu chi: {lap.text}"

    # Có ô LẬP thì qua được hàng rào quyền (còn hợp lệ nghiệp vụ hay không là chuyện khác — đơn số
    # 1 có thể không tồn tại; điều cần chứng minh ở đây là KHÔNG còn bị 403).
    co_lap = _h(_token_mot_man("phieu_chi", "-co-lap", can_read=True, can_create=True))
    r = client.post(
        "/api/accounting/payment-vouchers",
        json={"voucher_type": "cash", "amount_vnd": 500_000, "purchase_request_id": 1},
        headers=co_lap,
    )
    assert r.status_code != 403, "có ô Lập phiếu mà vẫn bị chặn quyền"


def test_xem_phieu_thu_khong_keo_theo_quyen_ghi_nhan_tien_ve(client):
    chi_xem = _h(_token_mot_man("phieu_thu", can_read=True))
    assert client.get("/api/accounting/payment-receipts", headers=chi_xem).status_code == 200
    for duong, than in (
        ("/api/accounting/payment-receipts", {"amount_vnd": 100_000}),
        ("/api/accounting/payment-receipts/1/mark-received", {}),
        ("/api/accounting/payment-receipts/1/cancel", {"reason": "x"}),
    ):
        r = client.post(duong, json=than, headers=chi_xem)
        assert r.status_code == 403, f"chỉ có Xem mà vẫn gọi được {duong}: {r.status_code}"


def test_xem_tai_khoan_ngan_hang_khong_keo_theo_quyen_sua(client):
    chi_xem = _h(_token_mot_man("tk_ngan_hang", can_read=True))
    assert client.get("/api/accounting/company-bank-accounts", headers=chi_xem).status_code == 200
    r = client.post(
        "/api/accounting/company-bank-accounts",
        json={"bank_name": "VCB", "account_number": "123", "account_holder": "SVN"},
        headers=chi_xem,
    )
    assert r.status_code == 403, f"chỉ có Xem mà vẫn thêm được tài khoản: {r.text}"


# ══════════════════════════════════════════════ Duyệt PMH — dời từ Mua hàng xuống đây (11/08/2026)


def test_duyet_pmh_doi_o_cua_man_don_mua_hang_ke_toan(client):
    """Ô "Duyệt / từ chối PMH" nay là `ke_toan:approve`, KHÔNG còn là `thu_mua:approve`.

    Vì sao dời: nút Duyệt / Từ chối chỉ có ở màn **Đơn mua hàng (Kế toán)** (chốt 04/08/2026
    "phải duyệt ở phần kế toán chứ"). Để ô dưới phân hệ Mua hàng thì nhìn ma trận không đoán ra nó
    tác dụng ở đâu — mà bên Mua hàng cùng cờ đó lại nuôi 3 việc khác hẳn (sửa số nhận · mở lại đơn
    · đóng đơn), nên một ô mang hai nghĩa.
    """
    chi_thu_mua = _token_mot_man("thu_mua", "-duyet-cu",
                                 can_read=True, can_create=True, can_approve=True)
    r = client.post("/api/purchase-requests/1/approve", headers=_h(chi_thu_mua))
    assert r.status_code == 403, f"`thu_mua:approve` vẫn duyệt được PMH: {r.status_code}"

    co_o = _token_mot_man("ke_toan", "-duyet-moi", can_read=True, can_approve=True)
    r2 = client.post("/api/purchase-requests/1/approve", headers=_h(co_o))
    assert r2.status_code != 403, "có ô Duyệt của màn Đơn mua hàng mà vẫn bị chặn quyền"


def test_xem_don_mua_hang_khong_keo_theo_quyen_duyet(client):
    """Xem hộp thư đơn mua ≠ được ký duyệt cho tiền đi tiếp."""
    chi_xem = _token_mot_man("ke_toan", "-chi-xem-duyet", can_read=True)
    assert client.get("/api/accounting/inbox", headers=_h(chi_xem)).status_code == 200
    assert client.post("/api/purchase-requests/1/approve",
                       headers=_h(chi_xem)).status_code == 403
    assert client.post("/api/purchase-requests/1/reject", json={"reason": "x"},
                       headers=_h(chi_xem)).status_code == 403
