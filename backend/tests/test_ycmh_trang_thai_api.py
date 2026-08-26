"""Trạng thái yêu cầu mua hàng khi các phiếu con LỆCH NHAU, và tình trạng từng sản phẩm.

Một YCMH tách thành nhiều phiếu (mỗi NCC một phiếu) thì các phiếu chạy lệch nhịp: phiếu giấy được
duyệt trước, phiếu băng keo còn nằm chờ; phiếu này về hàng, phiếu kia bị từ chối. Trước 05/08/2026
chỉ mốc *nhận hàng* biết suy trạng thái, sáu mốc còn lại set thẳng nên "ai bấm sau thì ghi đè".

Luật: trạng thái YCMH = bậc THẤP NHẤT trong các dòng/phiếu. Báo bi quan thì cùng lắm bộ phận đi
hỏi; báo lạc quan thì họ ngồi chờ hàng không bao giờ tới.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _needed_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _supplier(client, headers, *, name: str, item: str, unit: str = "tờ") -> dict:
    dau = f"{abs(hash(name)) % 10**8:08d}"
    r = client.post(
        "/api/suppliers",
        json={
            "name": name,
            "tax_code": f"01{dau}",
            "phone": f"09{dau}",
            "email": f"ncc{dau}@example.com",
            "address": "Hà Nội",
            "contact_name": "Nguyễn Lan",
            "supplier_group": "paper",
            "items": [{"item_name": item, "unit": unit, "unit_price": 2200, "vat_percent": 0}],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _h_duyet() -> dict[str, str]:
    """Người lập không tự duyệt được phiếu của mình ⇒ phải có tài khoản duyệt riêng."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("ycmh-approver")
        if u is None:
            bgd = DepartmentRepository(db).get_by_name("Ban giám đốc")
            roles = RoleRepository(db)
            role = roles.create(name="Duyet PMH cho YCMH", department_id=bgd.id)
            # Duyệt PMH dời sang khoá `ke_toan` (11/08/2026); giữ `thu_mua:read` để đọc phiếu.
            roles.set_permission(
                role_id=role.id, module_key="ke_toan", can_read=True, can_approve=True,
                scope=SCOPE_ALL,
            )
            roles.set_permission(
                role_id=role.id, module_key="thu_mua", can_read=True, scope=SCOPE_ALL,
            )
            u = users.create(username="ycmh-approver", name="GD", password_hash=hash_password("x"))
            users.set_assignment(u, department_id=bgd.id, role_id=role.id, is_active=True)
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def _yeu_cau_hai_dong(client, headers) -> tuple[dict, dict, dict]:
    """YCMH 2 dòng, mỗi dòng một NCC ⇒ tách thành 2 phiếu qua đường tạo cả mẻ."""
    ncc_a = _supplier(client, headers, name="NCC Giay YCMH", item="Giấy Duplex")
    ncc_b = _supplier(client, headers, name="NCC Keo YCMH", item="Băng keo", unit="cuộn")
    src = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy và băng keo",
            "needed_date": _needed_date(),
            "lines": [
                {"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500},
                {"item_name": "Băng keo", "unit": "cuộn", "quantity": 500},
            ],
        },
        headers=headers,
    )
    assert src.status_code == 201, src.text
    source = src.json()
    dong = {line["item_name"]: line["id"] for line in source["lines"]}
    batch = client.post(
        "/api/purchase-requests/batch",
        json={
            "source_request_ids": [source["id"]],
            "purpose": "Mua giấy và băng keo",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500,
                    "expected_unit_price": 2200, "supplier_id": ncc_a["id"],
                    "department_request_line_id": dong["Giấy Duplex"],
                },
                {
                    "item_name": "Băng keo", "unit": "cuộn", "quantity": 500,
                    "expected_unit_price": 2200, "supplier_id": ncc_b["id"],
                    "department_request_line_id": dong["Băng keo"],
                },
            ],
        },
        headers=headers,
    )
    assert batch.status_code == 201, batch.text
    phieu = {p["supplier_id"]: p for p in batch.json()["items"]}
    return source, phieu[ncc_a["id"]], phieu[ncc_b["id"]]


def _trang_thai(client, headers, source_id: int) -> str:
    return client.get(
        f"/api/department-purchase-requests/{source_id}", headers=headers
    ).json()["status"]


def _chi_tiet(client, headers, source_id: int) -> dict:
    r = client.get(f"/api/department-purchase-requests/{source_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _gui(client, headers, pid: int) -> None:
    assert client.post(f"/api/purchase-requests/{pid}/submit", headers=headers).status_code == 200


def _duyet(client, pid: int) -> None:
    assert client.post(
        f"/api/purchase-requests/{pid}/approve", headers=_h_duyet()
    ).status_code == 200


def _ve_hang(client, headers, pid: int) -> None:
    assert client.post(
        f"/api/purchase-requests/{pid}/mark-purchased", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pid}/mark-received", json={"lines": []}, headers=headers
    ).status_code == 200


# --- bốn ca lệch nhịp ------------------------------------------------------


def test_duyet_mot_phieu_thi_yeu_cau_van_la_cho_duyet(client):
    """⭐ Ca chủ hỏi: giấy đã duyệt, băng keo chưa duyệt.

    Trước đây duyệt MỘT phiếu là yêu cầu nhảy sang "Đang mua" ⇒ bộ phận nhìn vào tưởng cả yêu cầu
    đã được duyệt, trong khi băng keo còn nằm trên bàn giám đốc."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    _gui(client, headers, giay["id"])
    _gui(client, headers, keo["id"])
    assert _trang_thai(client, headers, source["id"]) == "pending_approval"

    _duyet(client, giay["id"])
    assert _trang_thai(client, headers, source["id"]) == "pending_approval", (
        "một phiếu được duyệt chưa phải cả yêu cầu được duyệt"
    )

    _duyet(client, keo["id"])
    assert _trang_thai(client, headers, source["id"]) == "in_purchase"


def test_nhan_mot_phieu_thi_chua_xong(client):
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _gui(client, headers, p["id"])
        _duyet(client, p["id"])

    _ve_hang(client, headers, giay["id"])
    assert _trang_thai(client, headers, source["id"]) == "in_purchase"

    _ve_hang(client, headers, keo["id"])
    assert _trang_thai(client, headers, source["id"]) == "done"


def test_tu_choi_mot_phieu_van_giu_yeu_cau_cho_sua_lai(client):
    """⭐ Từ chối phiếu băng keo KHÔNG được xoá sạch tiến độ của phiếu giấy đã về hàng.

    Yêu cầu vẫn được giữ ở "Chờ duyệt" để Thu mua sửa phiếu băng keo cũ và gửi lại; không được
    thả về "Chờ mua" vì như vậy sẽ cho lập thêm phiếu trùng. Phiếu giấy vẫn nguyên trạng thái đã
    nhận, và chi tiết phải nói rõ dòng nào bị từ chối."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _gui(client, headers, p["id"])
    _duyet(client, giay["id"])
    _ve_hang(client, headers, giay["id"])

    tu_choi = client.post(
        f"/api/purchase-requests/{keo['id']}/reject",
        json={"reason": "Giá cao quá"},
        headers=_h_duyet(),
    )
    assert tu_choi.status_code == 200, tu_choi.text

    assert _trang_thai(client, headers, source["id"]) == "pending_approval", (
        "PMH bị từ chối vẫn phải giữ YCMH để sửa và gửi lại chính PMH đó"
    )
    assert client.get(
        f"/api/purchase-requests/{giay['id']}", headers=headers
    ).json()["status"] == "received", "phiếu giấy không được bị đụng tới"

    chi_tiet = _chi_tiet(client, headers, source["id"])
    assert chi_tiet["workflow_status"] == "needs_correction"
    theo_ten = {line["item_name"]: line for line in chi_tiet["lines"]}
    assert theo_ten["Giấy Duplex"]["fulfilment"]["purchase_status"] == "received"
    assert theo_ten["Băng keo"]["fulfilment"]["purchase_status"] == "rejected"

    can_sua = client.get(
        "/api/department-purchase-requests?status=needs_correction",
        headers=headers,
    )
    assert can_sua.status_code == 200, can_sua.text
    assert source["id"] in {row["id"] for row in can_sua.json()["items"]}
    cho_duyet = client.get(
        "/api/department-purchase-requests?status=pending_approval",
        headers=headers,
    )
    assert source["id"] not in {row["id"] for row in cho_duyet.json()["items"]}


def test_phieu_bi_tu_choi_gui_lai_chinh_phieu_cu_va_hoan_tat(client):
    """PMH bị từ chối được gửi lại chính nó; khi hàng về đủ thì YCMH hoàn tất."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _gui(client, headers, p["id"])
    _duyet(client, giay["id"])
    _ve_hang(client, headers, giay["id"])
    assert client.post(
        f"/api/purchase-requests/{keo['id']}/reject",
        json={"reason": "Giá cao"}, headers=_h_duyet(),
    ).status_code == 200

    _gui(client, headers, keo["id"])
    assert _chi_tiet(client, headers, source["id"])["workflow_status"] == "pending_approval"
    _duyet(client, keo["id"])
    _ve_hang(client, headers, keo["id"])

    assert _trang_thai(client, headers, source["id"]) == "done", (
        "hàng đã về đủ sau khi gửi lại PMH cũ thì YCMH phải hoàn tất"
    )


def test_huy_phieu_duy_nhat_thi_yeu_cau_ve_cho_mua(client):
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        huy = client.post(
            f"/api/purchase-requests/{p['id']}/cancel",
            json={"reason": "Không mua nữa"},
            headers=headers,
        )
        assert huy.status_code == 200, huy.text
    assert _trang_thai(client, headers, source["id"]) == "open"


# --- tình trạng từng sản phẩm ----------------------------------------------


def test_chi_tiet_hien_tung_san_pham_va_danh_sach_phieu(client):
    """Bộ phận vào chi tiết phải biết: dòng nào vào phiếu nào, NCC nào, tới đâu, nhận bao nhiêu."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    _gui(client, headers, giay["id"])
    _duyet(client, giay["id"])
    assert client.post(
        f"/api/purchase-requests/{giay['id']}/mark-purchased", headers=headers
    ).status_code == 200
    dong_giay_phieu = giay["lines"][0]["id"]
    assert client.post(
        f"/api/purchase-requests/{giay['id']}/mark-received",
        json={"lines": [{"line_id": dong_giay_phieu, "received_quantity": 400}]},
        headers=headers,
    ).status_code == 200

    chi_tiet = _chi_tiet(client, headers, source["id"])
    theo_ten = {line["item_name"]: line for line in chi_tiet["lines"]}

    f = theo_ten["Giấy Duplex"]["fulfilment"]
    assert f["purchase_code"] == giay["code"]
    assert f["purchase_status"] == "received"
    assert f["supplier_name"] == "NCC Giay YCMH"
    assert f["ordered_quantity"] == 500 and f["received_quantity"] == 400

    # Băng keo mới ở phiếu NHÁP — vẫn nối được, và trạng thái phải nói đúng là còn nháp.
    assert theo_ten["Băng keo"]["fulfilment"]["purchase_status"] == "draft"

    assert {p["code"] for p in chi_tiet["purchase_requests"]} == {giay["code"], keo["code"]}


def test_dong_khong_noi_thi_de_trong_chu_khong_doan_theo_ten(client):
    """Phiếu lập không kèm nối dòng (dữ liệu cũ) ⇒ `fulfilment` để None.

    KHÔNG ghép bù theo tên hàng: thu mua sửa được tên cho khớp danh mục NCC, ghép trượt thì im lặng
    hiện SAI tiến độ. Thà nói "chưa rõ" — giao diện vẫn còn danh sách phiếu để tra."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Khong Noi", item="Giấy Duplex")
    src = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500}],
        },
        headers=headers,
    ).json()
    tao = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": ncc["id"],
            "source_request_ids": [src["id"]],
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500,
                    "expected_unit_price": 2200, "discount_percent": 0, "vat_percent": 0,
                }
            ],
        },
        headers=headers,
    )
    assert tao.status_code == 201, tao.text

    chi_tiet = _chi_tiet(client, headers, src["id"])
    assert chi_tiet["lines"][0]["fulfilment"] is None
    assert len(chi_tiet["purchase_requests"]) == 1, "vẫn phải thấy phiếu nào đã lập"
    # Không nối được dòng nào ⇒ lùi về suy theo PHIẾU. Phiếu còn nháp mà yêu cầu đã "Chờ duyệt" là
    # đúng ý đồ: tạo phiếu là GIỮ CHỖ yêu cầu, không cho người thứ hai lập chồng lên.
    assert chi_tiet["status"] == "pending_approval"
    assert chi_tiet["workflow_status"] == "drafting"


def test_khong_cho_tro_sang_dong_cua_yeu_cau_khac(client):
    """Trỏ nhầm sang dòng của yêu cầu khác thì chi tiết hiện nhầm tiến độ của người khác."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Tro Nham", item="Giấy Duplex")
    lam_yc = lambda: client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500}],
        },
        headers=headers,
    ).json()
    yc1, yc2 = lam_yc(), lam_yc()

    xau = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": ncc["id"],
            "source_request_ids": [yc1["id"]],
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500,
                    "expected_unit_price": 2200, "discount_percent": 0, "vat_percent": 0,
                    # dòng của YÊU CẦU KHÁC
                    "department_request_line_id": yc2["lines"][0]["id"],
                }
            ],
        },
        headers=headers,
    )
    assert xau.status_code == 422, xau.text
    assert "không thuộc yêu cầu nguồn" in xau.json()["detail"]


# --- bỏ TỪNG MÓN khỏi yêu cầu (mg 0233) ------------------------------------
#
# Chủ chốt 24/08/2026: *"phải quản tới từng món hàng, đừng quản tới cấp chứng từ nữa"*. Trước đó
# huỷ là huỷ CẢ yêu cầu, và chỉ huỷ được khi yêu cầu còn `open` — nên yêu cầu 5 dòng mà thu mua đã
# lập đơn cho 3 dòng thì 2 dòng thừa mắc kẹt vĩnh viễn, không ai gỡ được.


def _bo_mon(client, headers, source_id: int, line_id: int, ly_do: str = "Không cần nữa"):
    return client.post(
        f"/api/department-purchase-requests/{source_id}/lines/{line_id}/cancel",
        json={"reason": ly_do},
        headers=headers,
    )


def _huy_phieu(client, headers, pid: int) -> None:
    assert client.post(
        f"/api/purchase-requests/{pid}/cancel",
        json={"reason": "Không mua nữa"},
        headers=headers,
    ).status_code == 200


def test_bo_mot_mon_thi_yeu_cau_la_huy_mot_phan_chu_khong_phai_da_huy(client):
    """⭐ Ca chủ hỏi: bỏ giấy, còn băng keo ⇒ yêu cầu VẪN SỐNG, chỉ là "Hủy một phần"."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    dong = {l["item_name"]: l["id"] for l in source["lines"]}
    for p in (giay, keo):
        _huy_phieu(client, headers, p["id"])

    r = _bo_mon(client, headers, source["id"], dong["Giấy Duplex"], "Kho còn hàng")
    assert r.status_code == 200, r.text
    sau = r.json()

    assert sau["status"] != "cancelled", "còn món chưa mua thì yêu cầu chưa chết"
    assert sau["workflow_status"] == "partially_cancelled"
    assert sau["cancelled_line_count"] == 1 and sau["active_line_count"] == 1
    # Tiến độ THẬT của phần còn lại không bị huy hiệu "Hủy một phần" nuốt mất.
    assert sau["progress_status"] == "open"

    theo_ten = {l["item_name"]: l for l in sau["lines"]}
    bo = theo_ten["Giấy Duplex"]
    assert bo["cancelled_at"] is not None
    assert bo["cancel_reason"] == "Kho còn hàng"
    assert bo["cancelled_by_name"], "phải biết AI bỏ, không thì không ai trả lời được câu hỏi sau"
    assert bo["can_cancel"] is False, "bỏ rồi thì không bỏ lại"
    # Món đã bỏ KHÔNG bị xoá khỏi phiếu — còn nằm đó để tra lại.
    assert set(theo_ten) == {"Giấy Duplex", "Băng keo"}


def test_bo_het_mon_thi_yeu_cau_moi_thanh_da_huy(client):
    """Luật chủ chốt: chỉ khi TẤT CẢ món bị bỏ thì yêu cầu mới là "Đã hủy"."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    # Hai phiếu mua nháp đang giữ hai dòng ⇒ phải huỷ phiếu trước mới bỏ được món.
    for p in (giay, keo):
        _huy_phieu(client, headers, p["id"])

    dong = [l["id"] for l in source["lines"]]
    assert _bo_mon(client, headers, source["id"], dong[0]).json()["status"] != "cancelled"

    cuoi = _bo_mon(client, headers, source["id"], dong[1], "Dự án dừng")
    assert cuoi.status_code == 200, cuoi.text
    sau = cuoi.json()
    assert sau["status"] == "cancelled"
    assert sau["workflow_status"] == "cancelled", (
        "hết món thì hiện thẳng 'Đã hủy', không phải 'Hủy một phần'"
    )
    assert sau["reject_reason"] == "Dự án dừng", "lý do món cuối là lý do của cả phiếu"

    lai = _bo_mon(client, headers, source["id"], dong[0])
    assert lai.status_code == 409, lai.text


def test_mon_dang_nam_trong_don_mua_con_song_thi_khoa_lai_va_noi_ly_do(client):
    """Không ẩn nút — khoá lại và gọi ĐÍCH DANH đơn mua đang giữ món.

    Bỏ món khi thu mua đã đặt hàng là đơn kia mua về một thứ không ai còn cần. Nhưng nếu chỉ im
    lặng giấu nút thì người dùng tưởng phần mềm hỏng."""
    headers = _headers(client)
    source, giay, _keo = _yeu_cau_hai_dong(client, headers)
    _gui(client, headers, giay["id"])
    _duyet(client, giay["id"])

    chi_tiet = _chi_tiet(client, headers, source["id"])
    theo_ten = {l["item_name"]: l for l in chi_tiet["lines"]}
    khoa = theo_ten["Giấy Duplex"]
    assert khoa["can_cancel"] is False
    assert giay["code"] in (khoa["cancel_block_reason"] or ""), (
        "câu chặn phải gọi tên đơn mua để người dùng biết đi xử lý ở đâu"
    )
    # Món còn lại mới ở phiếu NHÁP nhưng phiếu đó vẫn là đơn còn sống ⇒ cũng bị giữ.
    assert theo_ten["Băng keo"]["can_cancel"] is False

    chan = _bo_mon(client, headers, source["id"], khoa["id"])
    assert chan.status_code == 409, chan.text
    assert giay["code"] in chan.json()["detail"]


def test_huy_don_mua_xong_thi_bo_mon_duoc(client):
    """Đơn mua bị huỷ = không còn giữ món nữa ⇒ mở khoá đúng như câu chặn đã hứa."""
    headers = _headers(client)
    source, giay, _keo = _yeu_cau_hai_dong(client, headers)
    dong_giay = next(l["id"] for l in source["lines"] if l["item_name"] == "Giấy Duplex")
    assert _bo_mon(client, headers, source["id"], dong_giay).status_code == 409

    _huy_phieu(client, headers, giay["id"])

    mo = _bo_mon(client, headers, source["id"], dong_giay, "Chuyển sang mua nội bộ")
    assert mo.status_code == 200, mo.text
    assert mo.json()["workflow_status"] == "partially_cancelled"


def test_bo_mon_bat_buoc_co_ly_do(client):
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _huy_phieu(client, headers, p["id"])
    trong = _bo_mon(client, headers, source["id"], source["lines"][0]["id"], "   ")
    assert trong.status_code == 422, trong.text


def test_sua_yeu_cau_khong_lam_mat_mon_da_bo(client):
    """⚠️ BẪY: `purchase_repo.update` dựng lại `request.lines` từ payload.

    Giao diện KHÔNG gửi món đã bỏ lên (không ai sửa được món đã bỏ), nên nếu repo xoá sạch rồi
    dựng lại thì món đã bỏ biến mất — kéo theo `department_request_line_id` của đơn mua bị NULL,
    mất luôn đường nối dòng↔dòng của các món khác."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _huy_phieu(client, headers, p["id"])
    dong_giay = next(l["id"] for l in source["lines"] if l["item_name"] == "Giấy Duplex")
    assert _bo_mon(client, headers, source["id"], dong_giay).status_code == 200

    sua = client.put(
        f"/api/department-purchase-requests/{source['id']}",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy và băng keo",
            "needed_date": _needed_date(),
            # CHỈ gửi món còn sống, đúng như giao diện làm.
            "lines": [{"item_name": "Băng keo", "unit": "cuộn", "quantity": 800}],
        },
        headers=headers,
    )
    assert sua.status_code == 200, sua.text
    sau = sua.json()
    theo_ten = {l["item_name"]: l for l in sau["lines"]}
    assert theo_ten["Giấy Duplex"]["cancelled_at"] is not None, "món đã bỏ phải còn nguyên vết"
    assert theo_ten["Băng keo"]["quantity"] == 800
    assert sau["cancelled_line_count"] == 1 and sau["active_line_count"] == 1


def test_loc_theo_huy_mot_phan(client):
    """Huy hiệu đè lên tiến độ thì BỘ LỌC cũng phải đè theo, không thì bấm lọc ra một đằng, nhìn
    danh sách một nẻo."""
    headers = _headers(client)
    source, giay, keo = _yeu_cau_hai_dong(client, headers)
    for p in (giay, keo):
        _huy_phieu(client, headers, p["id"])
    dong_giay = next(l["id"] for l in source["lines"] if l["item_name"] == "Giấy Duplex")
    assert _bo_mon(client, headers, source["id"], dong_giay).status_code == 200

    r = client.get(
        "/api/department-purchase-requests?status=partially_cancelled", headers=headers
    )
    assert r.status_code == 200, r.text
    assert source["id"] in {row["id"] for row in r.json()["items"]}

    khac = client.get("/api/department-purchase-requests?status=open", headers=headers)
    assert source["id"] not in {row["id"] for row in khac.json()["items"]}, (
        "đang là 'Hủy một phần' thì không được lòi ra ở bộ lọc trạng thái khác"
    )


def test_khong_lap_duoc_don_mua_cho_mon_da_bo(client):
    """Bỏ món xong mà thu mua vẫn lập được đơn cho nó thì việc bỏ chỉ là trang trí."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Bo Mon", item="Giấy Duplex")
    # Vật tư nào cũng phải có NCC đang bán mới khai được vào yêu cầu ⇒ dựng luôn NCC cho món thứ
    # hai, dù test này không mua nó; món thứ hai chỉ để yêu cầu không chết khi bỏ món thứ nhất.
    _supplier(client, headers, name="NCC Bo Mon Keo", item="Băng keo", unit="cuộn")
    src = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy và keo",
            "needed_date": _needed_date(),
            "lines": [
                {"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500},
                {"item_name": "Băng keo", "unit": "cuộn", "quantity": 10},
            ],
        },
        headers=headers,
    )
    assert src.status_code == 201, src.text
    src = src.json()
    dong = {l["item_name"]: l["id"] for l in src["lines"]}
    assert _bo_mon(client, headers, src["id"], dong["Giấy Duplex"]).status_code == 200

    xau = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": ncc["id"],
            "source_request_ids": [src["id"]],
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500,
                    "expected_unit_price": 2200, "discount_percent": 0, "vat_percent": 0,
                    "department_request_line_id": dong["Giấy Duplex"],
                }
            ],
        },
        headers=headers,
    )
    assert xau.status_code == 422, xau.text
    assert "huỷ" in xau.json()["detail"]
