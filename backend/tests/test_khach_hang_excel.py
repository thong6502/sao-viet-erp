"""Nhập Excel — Khách hàng (11/09/2026). Thay hẳn đường nhập CSV cũ.

Test đi qua HTTP vì đây là thứ người dùng thật đâm vào: tải mẫu → điền → xem trước → ghi, và cửa
quyền `set_credit_terms` chỉ có nghĩa ở tầng router.

File dùng trong test dựng từ CHÍNH file mẫu hệ xuất ra (`/mau-excel`) rồi điền vào — nếu mẫu đổi
cột mà bộ đọc quên theo thì test đỏ ngay, đúng cái "file mẫu luôn khớp hệ thống" mà chủ yêu cầu.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from app.services.customer_excel import TIEU_DE

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mau(client, token) -> bytes:
    r = client.get("/api/customers/mau-excel", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.content


def _dien(mau: bytes, dong: list[list]) -> bytes:
    """Điền các dòng vào ĐÚNG file mẫu hệ vừa xuất ra — giữ nguyên sheet `_meta`."""
    wb = load_workbook(BytesIO(mau))
    ws = wb[TIEU_DE]
    for hang in dong:
        ws.append(hang)
    ra = BytesIO()
    wb.save(ra)
    return ra.getvalue()


def _nhap(client, token, du_lieu: bytes, mode: str):
    return client.post(
        f"/api/customers/import-excel?mode={mode}",
        files={"file": ("kh.xlsx", du_lieu,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_h(token),
    )


def _tong(client, token) -> int:
    return client.get("/api/customers", headers=_h(token)).json()["total"]


# ================= file mẫu =================


def test_mau_excel_RONG_va_du_cot(client):
    """Mẫu rỗng (chốt 11/09/2026) — chỉ dòng tiêu đề, không kèm khách đang có. Và KHÔNG có cột Mã:
    mã là mã hệ tự cấp, người dùng không gõ."""
    wb = load_workbook(BytesIO(_mau(client, _token(client))))
    ws = wb[TIEU_DE]
    tieu_de = [o.value for o in ws[1]]

    assert ws.max_row == 1                       # rỗng: đúng một dòng tiêu đề
    assert "Mã" not in tieu_de and "Mã KH" not in tieu_de
    assert tieu_de[0] == "Tên khách hàng"
    # Admin có `set_credit_terms` ⇒ mẫu kèm cả khối tài chính.
    assert "Hạn mức công nợ (đ)" in tieu_de and "Markup tối đa (%)" in tieu_de
    assert "_meta" in wb.sheetnames               # dấu nhận diện màn


def test_file_cua_man_khac_bi_chan(client):
    """Sheet `_meta` là cửa chặn nhập nhầm — dùng lại đúng cơ chế của mọi màn danh mục."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "_meta"
    wb.active.append(["khoa", "gia_tri"])
    wb.active.append(["loai", "may_thiet_bi"])
    ra = BytesIO()
    wb.save(ra)

    r = _nhap(client, _token(client), ra.getvalue(), "preview")
    assert r.status_code == 422
    assert "không phải Khách hàng" in r.json()["detail"]


def test_file_khong_phai_xlsx_bi_chan(client):
    r = _nhap(client, _token(client), b"kh,mst\nabc,123\n", "preview")
    assert r.status_code == 422


# ================= luồng chính =================


def test_them_nhieu_khach_ma_TU_SINH_noi_tiep(client):
    token = _token(client)
    truoc = _tong(client, token)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Excel Một", "Công ty", "0101234567", "0911", "e1@x.vn", "HN", "Anh A"],
        ["Cty Excel Hai", "Cá nhân", None, "0912", None, "HCM", None],
    ])

    r = _nhap(client, token, du_lieu, "commit")
    assert r.status_code == 200, r.text
    kq = r.json()
    assert kq["hop_le"] and kq["da_ghi"] and kq["tong_dong"] == 2 and kq["tao_moi"] == 2
    assert _tong(client, token) == truoc + 2

    ds = client.get("/api/customers?size=200", headers=_h(token)).json()["items"]
    hai = next(c for c in ds if c["name"] == "Cty Excel Hai")
    assert hai["customer_kind"] == "ca_nhan"      # nhãn tiếng Việt map đúng
    assert hai["code"].startswith("KH")           # mã do hệ cấp


def test_XEM_TRUOC_khong_ghi_gi_xuong_db(client):
    """`preview` chạy y hệt `commit` rồi rollback — con số là con số THẬT, nhưng không còn dấu vết."""
    token = _token(client)
    truoc = _tong(client, token)
    du_lieu = _dien(_mau(client, token), [["Cty Chỉ Xem Trước", "Công ty", None, None, None, None, None]])

    kq = _nhap(client, token, du_lieu, "preview").json()
    assert kq["hop_le"] and kq["tao_moi"] == 1
    assert kq["da_ghi"] is False
    assert _tong(client, token) == truoc          # KHÔNG một bản ghi nào lọt xuống


def test_dong_TRANG_cuoi_file_khong_tinh_la_loi(client):
    """Ai cũng để thừa vài dòng trắng cuối file — bắt lỗi ở đó là bắt lỗi một việc không có."""
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Có Thật", "Công ty", None, None, None, None, None],
        [None, None, None, None, None, None, None],
        ["", "", "", "", "", "", ""],
    ])
    kq = _nhap(client, token, du_lieu, "preview").json()
    assert kq["hop_le"] and kq["tong_dong"] == 1 and kq["tao_moi"] == 1


# ================= lỗi: cả file cùng sống hoặc cùng chết =================


def test_thieu_ten_thi_CA_FILE_khong_ghi_gi(client):
    token = _token(client)
    truoc = _tong(client, token)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Hợp Lệ Nhưng Vẫn Không Được Ghi", "Công ty", None, None, None, None, None],
        [None, "Công ty", "0100000000", None, None, None, None],        # thiếu tên
    ])

    kq = _nhap(client, token, du_lieu, "commit").json()
    assert kq["hop_le"] is False and kq["da_ghi"] is False
    assert kq["tao_moi"] == 0
    assert [x["dong"] for x in kq["loi"]] == [3]      # dòng THẬT trên sheet (tính cả tiêu đề)
    assert kq["loi"][0]["cot"] == "Tên khách hàng"
    assert _tong(client, token) == truoc              # dòng hợp lệ cũng KHÔNG được ghi


def test_sale_sai_ten_bao_dung_dong(client):
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Sale Lạ", "Công ty", None, None, None, None, None, "Nguyễn Không Có Thật"],
    ])
    kq = _nhap(client, token, du_lieu, "preview").json()
    assert kq["hop_le"] is False
    assert kq["loi"][0]["dong"] == 2 and kq["loi"][0]["cot"] == "Sale phụ trách"
    assert "Nguyễn Không Có Thật" in kq["loi"][0]["ly_do"]


def test_sale_NGOAI_KHOI_KINH_DOANH_bi_chan_va_noi_dung_ly_do(client):
    """Ô "NV phụ trách" trên màn chỉ cho chọn người thuộc khối Kinh doanh — để không lỡ tay gán
    khách cho Thủ kho. Đường Excel phải chặt y hệt, nếu không nó thành cửa sau.

    Và phải nói ĐÚNG lý do: "không thuộc khối Kinh doanh", chứ không phải "không tìm thấy người
    nào tên đó" — hai câu dẫn người dùng đi hai hướng khác hẳn nhau.
    """
    from app.db import SessionLocal
    from app.models.department import Department
    from app.models.user import User
    from app.repositories.user_repo import UserRepository
    from app.security import hash_password

    db = SessionLocal()
    try:
        kho = db.query(Department).filter(Department.name == "Kho").first()
        if kho is None:
            kho = Department(name="Kho")
            db.add(kho)
            db.commit()
            db.refresh(kho)
        u = db.query(User).filter(User.username == "thukho_excel").first()
        if u is None:
            u = UserRepository(db).create(username="thukho_excel", name="Thủ Kho Excel",
                                          password_hash=hash_password("x"))
            UserRepository(db).set_assignment(u, department_id=kho.id, role_id=None,
                                              is_active=True)
        ten_thu_kho = u.name
    finally:
        db.close()

    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Gán Nhầm Thủ Kho", "Công ty", None, None, None, None, None, ten_thu_kho],
    ])
    kq = _nhap(client, token, du_lieu, "preview").json()

    assert kq["hop_le"] is False
    assert kq["loi"][0]["cot"] == "Sale phụ trách"
    assert "không thuộc khối Kinh doanh" in kq["loi"][0]["ly_do"]


def test_o_chon_sale_trong_mau_CHI_liet_ke_nguoi_du_tu_cach(client):
    """Sheet ẩn `_sale` là nguồn ô chọn xổ xuống — nó phải khớp đúng danh sách màn hình cho chọn."""
    from io import BytesIO

    from openpyxl import load_workbook

    from app.db import SessionLocal
    from app.models.user import User
    from app.services.customer_service import nguoi_du_tu_cach_nhan_khach

    wb = load_workbook(BytesIO(_mau(client, _token(client))))
    trong_mau = set()
    if "_sale" in wb.sheetnames:
        trong_mau = {r[0] for r in wb["_sale"].iter_rows(values_only=True) if r and r[0]}

    db = SessionLocal()
    try:
        du = nguoi_du_tu_cach_nhan_khach(db)
        mong_doi = {
            (u.name or u.username)
            for u in db.query(User).all() if u.id in du
        }
    finally:
        db.close()
    assert trong_mau == mong_doi


def test_loai_khach_la_bi_chan(client):
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [["Cty Loại Lạ", "Doanh nghiệp", None, None, None, None, None]])
    kq = _nhap(client, token, du_lieu, "preview").json()
    assert kq["hop_le"] is False and kq["loi"][0]["cot"] == "Loại khách"


def test_rao_min_lon_hon_max_bi_chan(client):
    """Luật nằm ở service (`_validate_bounds`) — bộ nhập không chép lại luật, chỉ dịch lỗi ra dòng."""
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Rào Ngược", "Công ty", None, None, None, None, None, None, None, None, 50, 10],
    ])
    kq = _nhap(client, token, du_lieu, "commit").json()
    assert kq["hop_le"] is False and kq["da_ghi"] is False


# ================= trùng = cảnh báo, KHÔNG chặn =================


def test_trung_MST_chi_CANH_BAO_va_VAN_GHI(client):
    """Model ghi rõ MST không unique, trùng là cảnh báo mềm (§34, §41) — form nhập tay cũng chỉ
    cảnh báo. Chặn ở Excel là chặt hơn cả form, tức là sai."""
    token = _token(client)
    client.post("/api/customers", json={"name": "Cty Gốc MST", "tax_code": "0107654321"},
                headers=_h(token))
    truoc = _tong(client, token)

    du_lieu = _dien(_mau(client, token), [
        ["Cty Trùng MST", "Công ty", "0107654321", None, None, None, None],
    ])
    kq = _nhap(client, token, du_lieu, "commit").json()

    assert kq["hop_le"] and kq["da_ghi"] and kq["tao_moi"] == 1
    assert _tong(client, token) == truoc + 1
    assert len(kq["canh_bao"]) == 1
    assert kq["canh_bao"][0]["dong"] == 2 and "MST" in kq["canh_bao"][0]["ly_do"]


def test_trung_NGAY_TRONG_MOT_FILE_cung_canh_bao(client):
    """Hai dòng cùng MST trong CÙNG một file: dòng sau phải thấy dòng trước — nhờ `flush()` trong
    cùng giao dịch, không phải đợi commit."""
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Nội Bộ A", "Công ty", "0109999999", None, None, None, None],
        ["Cty Nội Bộ B", "Công ty", "0109999999", None, None, None, None],
    ])
    kq = _nhap(client, token, du_lieu, "commit").json()
    assert kq["hop_le"] and kq["tao_moi"] == 2
    assert [c["dong"] for c in kq["canh_bao"]] == [3]     # dòng 2 trùng với dòng 1


# ================= khối tài chính theo quyền =================


def test_co_quyen_thi_GHI_duoc_chinh_sach_tai_chinh(client):
    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Có Hạn Mức", "Công ty", None, None, None, None, None, None,
         5000000, 30, 0, 10, 5, 20],
    ])
    assert _nhap(client, token, du_lieu, "commit").json()["da_ghi"] is True

    ds = client.get("/api/customers?size=200", headers=_h(token)).json()["items"]
    kh = next(c for c in ds if c["name"] == "Cty Có Hạn Mức")
    chi_tiet = client.get(f"/api/customers/{kh['id']}", headers=_h(token)).json()["customer"]
    assert chi_tiet["credit_limit"] == 5000000
    assert chi_tiet["payment_term_days"] == 30
    assert chi_tiet["markup_max_pct"] == 20


def test_khong_quyen_thi_BO_QUA_cot_tai_chinh_va_NOI_RA(client):
    """Nhánh dễ làm ẩu nhất: ghi lén là vượt quyền, chặn cả file là mượn mẫu của đồng nghiệp rồi
    không nhập nổi gì. Bỏ qua ĐÚNG mấy cột đó, ghi phần còn lại, và nói thành lời.

    Gọi thẳng tầng service với `co_tai_chinh=False` — đúng giá trị router truyền xuống khi người
    dùng thiếu `set_credit_terms`.
    """
    from app.db import SessionLocal
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.customer_repo import CustomerRepository
    from app.repositories.user_repo import UserRepository
    from app.services import customer_excel
    from app.services.customer_service import CustomerService

    token = _token(client)
    du_lieu = _dien(_mau(client, token), [
        ["Cty Không Được Đặt Hạn Mức", "Công ty", None, None, None, None, None, None,
         9000000, 45, None, None, None, None],
    ])

    db = SessionLocal()
    try:
        admin = UserRepository(db).get_by_username("admin")
        svc = CustomerService(CustomerRepository(db), AuditLogRepository(db))
        kq = customer_excel.nhap(db, svc, du_lieu, actor=admin, scope="all",
                                 co_tai_chinh=False, ghi=True)
        assert kq.hop_le and kq.da_ghi and kq.tao_moi == 1
        assert kq.bo_qua_tai_chinh is True          # có nói ra, không im lặng
        kh = CustomerRepository(db).find_by_name_exact("Cty Không Được Đặt Hạn Mức") \
            if hasattr(CustomerRepository(db), "find_by_name_exact") else None
        if kh is None:
            from app.models.customer import Customer
            from sqlalchemy import select
            kh = db.execute(
                select(Customer).where(Customer.name == "Cty Không Được Đặt Hạn Mức")
            ).scalars().first()
        assert kh is not None
        assert kh.credit_limit == 0                 # KHÔNG ghi lén
        assert kh.payment_term_days is None
    finally:
        db.close()
