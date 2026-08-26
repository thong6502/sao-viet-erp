"""Import Excel (mục 1 "Bảng định mức") — `GET .../mau-excel` + `POST .../import-excel`.

Cơ chế DÙNG CHUNG cho cả 5 danh mục, sống ở `routers/catalog_base.make_catalog_router`
(tham số `enable_import`/`import_columns`/`import_resolve`) — không có unit test service nào
phủ được vì logic nằm ở ROUTER (đọc file, dịch cột, gọi `svc.create` từng dòng). Test qua
`TestClient` thật, dựng file `.xlsx` bằng `openpyxl` trong bộ nhớ, giống hệt cách route build
file mẫu.

Phủ luôn BA lỗi "field bắt buộc-ở-service-nhưng-ẩn-ở-schema" tự soi ra khi dựng cơ chế này:
Công đoạn (`nhom` dịch từ nhãn tiếng Việt + `pricing_basis`/`che_do_tinh` ép cứng), Giấy
(`chung_loai_giay_id` dịch từ tên chủng loại), Công việc khoán (`department_id` dịch từ tên tổ).
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository


def _login(client, username="admin", password="admin123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _wb_bytes(headers: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, headers, url: str, content: bytes):
    return client.post(
        url,
        files={"file": ("import.xlsx", content,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )


def test_mau_excel_tra_dung_tieu_de_cong_doan(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    resp = client.get("/api/cong-doan/mau-excel", headers=headers)
    assert resp.status_code == 200, resp.text
    wb = load_workbook(BytesIO(resp.content))
    tieu_de = [c.value for c in wb.active[1]]
    assert tieu_de == [
        "Mã", "Tên", "Tên hiển thị", "Nhóm", "Đơn vị vào", "Đơn vị ra", "Công thức sản lượng",
    ]


def test_import_cong_doan_thanh_cong_va_bao_loi_dong_sai(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    content = _wb_bytes(
        ["Mã", "Tên", "Tên hiển thị", "Nhóm", "Đơn vị vào", "Đơn vị ra", "Công thức sản lượng"],
        [
            # Nhãn tiếng Việt "In" — phải dịch qua `_resolve_nhom` thành mã gốc "print", đồng thời
            # `pricing_basis`/`che_do_tinh` phải được TỰ ép (không khai ở đây) mới qua được service.
            ["CD-IMP-01", "In offset nhập Excel", "In offset", "In", None, None, None],
            # Nhóm không có trong 4 nhãn hợp lệ → lỗi resolve, KHÔNG được chặn dòng sau.
            ["CD-IMP-02", "Nhóm sai", "Sai nhóm", "Không tồn tại", None, None, None],
            # Thiếu "Mã" (bắt buộc) → lỗi Pydantic.
            [None, "Thiếu mã", "x", "In", None, None, None],
        ],
    )
    resp = _upload(client, headers, "/api/cong-doan/import-excel", content)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tong_dong"] == 3
    assert data["thanh_cong"] == 1
    assert len(data["loi"]) == 2
    assert data["loi"][0]["dong"] == 3
    assert "Nhóm" in data["loi"][0]["ly_do"]
    assert data["loi"][1]["dong"] == 4

    list_resp = client.get("/api/cong-doan", params={"q": "CD-IMP-01"}, headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    dong = next(i for i in items if i["ma"] == "CD-IMP-01")
    assert dong["nhom"] == "print"
    assert dong["che_do_tinh"] == "theo_san_luong"
    assert dong["pricing_basis"] == "per_other"


def test_import_cong_doan_ma_trung_bao_loi_dong_khac_khong_bi_chan(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    create_resp = client.post(
        "/api/cong-doan",
        json={
            "ma": "CD-DUP", "ten": "Đã có sẵn", "nhom": "print",
            "che_do_tinh": "theo_san_luong", "pricing_basis": "per_other",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text

    content = _wb_bytes(
        ["Mã", "Tên", "Tên hiển thị", "Nhóm", "Đơn vị vào", "Đơn vị ra", "Công thức sản lượng"],
        [
            ["CD-DUP", "Trùng mã", "Trùng", "In", None, None, None],
            ["CD-IMP-03", "Dòng sau vẫn chạy", "OK", "In", None, None, None],
        ],
    )
    resp = _upload(client, headers, "/api/cong-doan/import-excel", content)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tong_dong"] == 2
    assert data["thanh_cong"] == 1
    assert len(data["loi"]) == 1
    assert data["loi"][0]["dong"] == 2


def test_import_giay_dich_chung_loai_bang_ten_va_bao_loi_ten_khong_ton_tai(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    cl_resp = client.post(
        "/api/vat-lieu-kho/chung-loai-giay",
        json={"ma": "CL-IMP", "ten": "Giấy couche nhập"},
        headers=headers,
    )
    assert cl_resp.status_code == 201, cl_resp.text

    content = _wb_bytes(
        [
            "Mã", "Tên", "Chủng loại giấy", "Định lượng (gsm)", "Độ dày (micron)", "Thớ giấy",
            "Đơn vị giá", "Đơn giá", "Giá thị trường", "Ghi chú", "Công thức giá", "Công thức lượng",
        ],
        [
            ["GIAY-IMP-01", "Giấy nhập Excel", "Giấy couche nhập", 150, None, None,
             None, None, None, None, None, None],
            ["GIAY-IMP-02", "Chủng loại không có", "Không tồn tại trong danh mục", 100, None, None,
             None, None, None, None, None, None],
        ],
    )
    resp = _upload(client, headers, "/api/vat-lieu-kho/giay/import-excel", content)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tong_dong"] == 2
    assert data["thanh_cong"] == 1
    assert len(data["loi"]) == 1
    assert data["loi"][0]["dong"] == 3
    assert "chủng loại giấy" in data["loi"][0]["ly_do"].lower()

    list_resp = client.get("/api/vat-lieu-kho/giay", params={"q": "GIAY-IMP-01"}, headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    dong = next(i for i in list_resp.json()["items"] if i["ma"] == "GIAY-IMP-01")
    assert dong["chung_loai_giay_id"] == cl_resp.json()["id"]


def test_import_cong_viec_khoan_dich_to_bang_ten(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    db = SessionLocal()
    try:
        to_id = DepartmentRepository(db).get_by_name("Hành chính nhân sự").id
    finally:
        db.close()

    content = _wb_bytes(
        ["Mã", "Tên", "Tổ", "Đơn vị", "Đơn giá", "Công thức lượng", "Ghi chú"],
        [
            ["KH-IMP-01", "Đầu việc nhập Excel", "Hành chính nhân sự", "tờ", 5000, None, None],
            ["KH-IMP-02", "Tổ không tồn tại", "Tổ ma không có thật", "tờ", 5000, None, None],
        ],
    )
    resp = _upload(client, headers, "/api/cong-viec-khoan/import-excel", content)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tong_dong"] == 2
    assert data["thanh_cong"] == 1
    assert len(data["loi"]) == 1
    assert data["loi"][0]["dong"] == 3

    list_resp = client.get("/api/cong-viec-khoan", params={"q": "KH-IMP-01"}, headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    dong = next(i for i in list_resp.json()["items"] if i["ma"] == "KH-IMP-01")
    assert dong["department_id"] == to_id


def test_import_may_thiet_bi_khong_can_resolver(client, seed_credentials):
    headers = _login(client, **seed_credentials)
    content = _wb_bytes(
        ["Mã", "Tên", "Loại máy", "Hãng sản xuất", "Model", "Số seri"],
        [["MAY-IMP-01", "Máy in nhập Excel", "In offset", "Heidelberg", "SM-52", "SN-001"]],
    )
    resp = _upload(client, headers, "/api/may-thiet-bi/import-excel", content)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tong_dong"] == 1
    assert data["thanh_cong"] == 1
    assert data["loi"] == []
