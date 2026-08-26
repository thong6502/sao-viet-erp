"""Danh mục "Công việc khoán" (`/api/cong-viec-khoan`) — bảng `piece_rates` sau khi vào Cấu hình
danh mục ngày 17/08/2026.

Kế thừa 13 test cũ của `test_khoan_api.py` (CRUD · đơn vị · mã tự sinh) rồi thêm những thứ chỉ có
sau khi bảng đi vào nền danh mục: NHẬT KÝ từng dòng, luật xoá hai kết cục, `PATCH /{id}/active`,
số trên tab lọc theo tổ.

⚠️ DB test là SQLite in-memory dùng chung cả phiên; `client` wipe schema mỗi test nhưng seed vẫn
chạy. Nên mọi bản ghi đặt tiền tố `ZZ` và mọi khẳng định lọc theo tiền tố đó — KHÔNG assert
`total == N`.
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}
API = "/api/cong-viec-khoan"


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _to_id(client, h) -> int:
    """Id một TỔ sản xuất — lấy từ chính endpoint mà form dùng để đổ ô "Tổ làm việc này"."""
    r = client.get("/api/cong-doan/phong-ban", headers=h)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    if items:
        return int(items[0]["id"])
    # `code` do hệ thống sinh (spec-05) — không nhận từ client. Tổ mới không có con ⇒ là nút LÁ
    # trong khối Sản xuất, đúng thứ `phong_ban_options` mời chọn.
    tao = client.post("/api/departments",
                      json={"name": "ZZ Tổ khoán", "la_san_xuat": True}, headers=h)
    assert tao.status_code == 201, tao.text
    return int(tao.json()["id"])


def _ten_to(client, h, to_id: int) -> str:
    """Tên tổ theo id. Tách hàm để KHÔNG gọi `_to_id` bên trong generator: `_to_id` có thể TẠO tổ
    mới, và tổ mới đó chưa nằm trong danh sách vừa đọc ⇒ `next()` không tìm thấy gì và ném
    StopIteration (pytest báo thành "generator raised StopIteration", rất khó lần)."""
    items = client.get("/api/cong-doan/phong-ban", headers=h).json()["items"]
    ten = next((x["ten"] for x in items if x["id"] == to_id), None)
    assert ten, f"không thấy tổ id={to_id} trong ô chọn"
    return ten


def _mk(client, h, **over):
    body = {"ten": "ZZ Việc test", "department_id": _to_id(client, h), "unit": "to",
            "unit_price": 100}
    body.update(over)
    return client.post(API, json=body, headers=h)


# --- CRUD ---------------------------------------------------------------------


def test_vong_crud(client):
    h = _admin(client)
    tao = _mk(client, h, ten="ZZ Bồi 3 lớp", unit_price=170)
    assert tao.status_code == 201, tao.text
    rid = tao.json()["id"]

    assert any(x["id"] == rid for x in client.get(f"{API}?q=ZZ Bồi", headers=h).json()["items"])

    upd = client.put(f"{API}/{rid}", json={
        "ten": "ZZ Bồi 3 lớp", "department_id": tao.json()["department_id"],
        "unit": "to", "unit_price": 180,
    }, headers=h)
    assert upd.status_code == 200, upd.text
    assert upd.json()["unit_price"] == 180

    assert client.delete(f"{API}/{rid}", headers=h).status_code == 204


def test_ma_tu_sinh_khi_bo_trong(client):
    """Chủ chốt 31/07/2026: không cho nhập mã, máy sinh `KH-####`."""
    h = _admin(client)
    ma = _mk(client, h).json()["ma"]
    assert ma and ma.startswith("KH-"), ma


def test_nhan_to_suy_tu_department_id(client):
    """`group_name` là NHÃN tổ, server suy từ `department_id` — client không gửi.

    Hai chỗ cùng khai một sự thật thì sớm muộn lệch: bảng mang tên tổ của tháng trước trong khi
    con trỏ `department_id` đã sang tổ khác."""
    h = _admin(client)
    to_id = _to_id(client, h)
    ten_to = _ten_to(client, h, to_id)
    row = _mk(client, h, department_id=to_id).json()
    assert row["group_name"] == ten_to[:40], row["group_name"]


def test_thieu_to_bi_chan(client):
    h = _admin(client)
    r = client.post(API, json={"ten": "ZZ Không tổ", "unit": "to", "unit_price": 10}, headers=h)
    assert r.status_code == 422, r.text
    assert "tổ" in r.json()["detail"].lower()


def test_to_khong_ton_tai_bi_chan_bang_CAU_KHAC(client):
    """Hai ca lỗi khác nhau ⇒ hai câu khác nhau: chưa chọn gì, và chọn một id không có thật (form
    còn cầm id của tổ đã xoá). Gộp một câu thì người khai sửa mãi không đúng chỗ."""
    h = _admin(client)
    r = client.post(API, json={"ten": "ZZ Tổ ma", "department_id": 987654,
                               "unit": "to", "unit_price": 10}, headers=h)
    assert r.status_code == 422, r.text
    assert "không tìm thấy tổ" in r.json()["detail"].lower(), r.json()["detail"]


def test_sua_sang_to_khong_ton_tai_bi_chan_nhung_giu_to_cu_thi_qua(client):
    """Đường SỬA chỉ chặn khi ĐỔI SANG một tổ không có thật.

    Gửi lại đúng tổ đang lưu thì phải cho qua — form load ra chính giá trị đó, chặn cả ca này là
    khoá luôn đường sửa tên/đơn giá của dòng ấy."""
    h = _admin(client)
    to_id = _to_id(client, h)
    rid = _mk(client, h, ten="ZZ Sửa tổ").json()["id"]

    doi = client.put(f"{API}/{rid}", json={"ten": "ZZ Sửa tổ", "department_id": 987654,
                                           "unit": "to", "unit_price": 120}, headers=h)
    assert doi.status_code == 422, doi.text

    giu = client.put(f"{API}/{rid}", json={"ten": "ZZ Sửa tổ rồi", "department_id": to_id,
                                           "unit": "to", "unit_price": 120}, headers=h)
    assert giu.status_code == 200, giu.text
    assert giu.json()["ten"] == "ZZ Sửa tổ rồi"


def test_don_gia_am_bi_chan(client):
    h = _admin(client)
    assert _mk(client, h, unit_price=-1).status_code == 422


# --- Ô "Đơn vị" ---------------------------------------------------------------
# Ô này trỏ danh mục `Đơn vị & quy đổi` và lưu MÃ (`to`, `kg`) — cùng lối `giay.don_vi_gia`.
# NHƯNG API vẫn NHẬN chữ bất kỳ: dòng cũ, seed và import đều đang mang đơn vị ngoài danh mục, chặn
# ở API là khoá luôn đường sửa những dòng đó (quyết định 31/07/2026, giữ nguyên).


def test_don_vi_ngoai_danh_muc_van_luu_duoc(client):
    h = _admin(client)
    r = _mk(client, h, unit="mét tới")
    assert r.status_code == 201, r.text
    assert r.json()["unit"] == "mét tới"
    # …nhưng KHÔNG có tên đọc được ⇒ màn hiện nguyên mã kèm dấu hiệu, không im lặng bỏ trắng.
    assert r.json()["don_vi_ten"] is None


def test_don_vi_luu_dung_chu_nhan_duoc(client):
    """Lưu ĐÚNG chữ nhận được, chỉ cắt khoảng trắng — màn khai báo không sửa chữ của người ta."""
    h = _admin(client)
    assert _mk(client, h, unit="kg").json()["unit"] == "kg"
    assert _mk(client, h, unit="  KG ").json()["unit"] == "KG"


def test_don_vi_bo_trong_thanh_khac(client):
    h = _admin(client)
    assert _mk(client, h, unit="").json()["unit"] == "khác"
    assert _mk(client, h, unit="   ").json()["unit"] == "khác"


def test_don_vi_dai_24_ky_tu(client):
    """12 ký tự cũ vừa khít "thùng carton" là hỏng ⇒ đã nới 24."""
    h = _admin(client)
    assert _mk(client, h, unit="thùng carton loại to").status_code == 201
    assert _mk(client, h, unit="x" * 25).status_code == 422


def test_tra_kem_TEN_don_vi(client):
    """⚠️ BẪY Pydantic đã dính 4 lần: service gán thêm field mà schema `Out` không khai thì bị NUỐT
    IM LẶNG. Soi cả ba cửa: tạo · danh sách · chi tiết."""
    h = _admin(client)
    dv = client.post("/api/don-vi", json={"ma": "zzcuon", "ten": "ZZ Cuốn"}, headers=h)
    assert dv.status_code in (201, 409), dv.text

    tao = _mk(client, h, ten="ZZ Vào keo", unit="zzcuon")
    assert tao.status_code == 201, tao.text
    assert tao.json()["don_vi_ten"] == "ZZ Cuốn", f"POST nuốt `don_vi_ten`: {sorted(tao.json())}"

    rid = tao.json()["id"]
    assert client.get(f"{API}/{rid}", headers=h).json()["don_vi_ten"] == "ZZ Cuốn"
    ds = client.get(f"{API}?q=ZZ Vào keo", headers=h).json()["items"]
    assert ds and ds[0]["don_vi_ten"] == "ZZ Cuốn"


# --- Tab lọc theo tổ ----------------------------------------------------------


def test_loc_theo_to_nhan_ca_TEN_va_ID(client):
    """`?to=` nhận hai dạng, cố ý: tab của màn gửi TÊN tổ (nhãn đọc được), panel Cấu hình lương gửi
    ID (nó biết id và không muốn hụt dòng vì nhãn lệch một chữ)."""
    h = _admin(client)
    to_id = _to_id(client, h)
    ten_to = _ten_to(client, h, to_id)
    rid = _mk(client, h, ten="ZZ Lọc theo tổ").json()["id"]

    theo_id = client.get(f"{API}?to={to_id}", headers=h).json()["items"]
    assert any(x["id"] == rid for x in theo_id)
    assert all(x["department_id"] == to_id for x in theo_id)

    theo_ten = client.get(f"{API}?to={ten_to}", headers=h).json()["items"]
    assert any(x["id"] == rid for x in theo_ten)


def test_facets_dem_theo_to(client):
    """Số trên tab do MÁY CHỦ đếm — màn chỉ cầm 20 dòng nên không tự đếm được."""
    h = _admin(client)
    ten_to = _ten_to(client, h, _to_id(client, h))
    _mk(client, h, ten="ZZ Đếm 1")
    body = client.get(API, headers=h).json()
    assert "facets" in body, "thiếu `facets` ⇒ tab lọc mất số"
    assert body["facets"].get(ten_to, 0) >= 1


# --- Luật xoá: một nút, hai kết cục do SỐ LIỆU quyết -------------------------


def test_kiem_xoa_chua_ai_dung_thi_cho_xoa_han(client):
    h = _admin(client)
    rid = _mk(client, h, ten="ZZ Chưa ai dùng").json()["id"]
    r = client.get(f"/api/danh-muc/cong_viec_khoan/{rid}/kiem-xoa", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["xoa_han_duoc"] is True
    assert r.json()["chan"] == []
    # Không có CASCADE nào trỏ vào bảng này (`piece_rate_id` là soft-ref, không FK cứng).
    assert r.json()["keo_theo"] == []


def test_dinh_muc_dau_viec_chan_xoa_han(client):
    """Công đoạn trỏ đơn giá này bằng ID THẬT (`cong_doan_dau_viec.piece_rate_id`) ⇒ chỉ ngừng dùng.

    Xoá cứng ở đây là để lại một id trỏ vào hư không trong bảng định mức — mà định mức là dữ liệu
    khai tay (năng suất người-giờ, số người, BOM vật tư)."""
    h = _admin(client)
    to_id = _to_id(client, h)
    rid = _mk(client, h, ten="ZZ Đang được dùng", department_id=to_id).json()["id"]

    cd = client.post("/api/cong-doan", json={
        "ma": "ZZCDK1", "ten": "ZZ Công đoạn khoán", "nhom": "finishing",
        "pricing_basis": "per_finished_qty", "department_id": to_id,
        "dau_viec_dinh_muc": [{"piece_rate_id": rid, "nang_suat_nguoi_gio": 100,
                               "so_nguoi_tieu_chuan": 1, "so_nguoi_toi_da": 2}],
    }, headers=h)
    assert cd.status_code == 201, cd.text

    kiem = client.get(f"/api/danh-muc/cong_viec_khoan/{rid}/kiem-xoa", headers=h).json()
    assert kiem["xoa_han_duoc"] is False
    assert any("định mức đầu việc" in c for c in kiem["chan"]), kiem["chan"]

    # Cửa chặn THẬT ở service, không chỉ ở hộp thoại: gọi DELETE trực tiếp phải ăn 409 kèm lý do.
    xoa = client.delete(f"{API}/{rid}", headers=h)
    assert xoa.status_code == 409, xoa.text
    assert "định mức đầu việc" in xoa.json()["detail"]


def test_ngung_dung_va_bat_lai_bang_PATCH_active(client):
    """`PATCH /{id}/active` — route RIÊNG chứ không phải `PUT` với mỗi `{active}`.

    `PUT` nhận schema ĐẦY ĐỦ nên gửi một khoá là Pydantic chặn ở cổng bằng 422 "field required":
    đúng lỗi đã làm nút Ngừng dùng/Bật lại bấm-không-ăn ở cả bốn danh mục xoá mềm (15/08/2026)."""
    h = _admin(client)
    rid = _mk(client, h, ten="ZZ Bật tắt").json()["id"]

    tat = client.patch(f"{API}/{rid}/active", json={"active": False}, headers=h)
    assert tat.status_code == 200, tat.text
    assert tat.json()["active"] is False
    # Danh sách mặc định của màn (`?active=true`) không còn thấy nó…
    con = client.get(f"{API}?active=true&q=ZZ Bật tắt", headers=h).json()["items"]
    assert not any(x["id"] == rid for x in con)
    # …nhưng công tắc "Hiện mục đã ngừng" thì thấy.
    ngung = client.get(f"{API}?active=false&q=ZZ Bật tắt", headers=h).json()["items"]
    assert any(x["id"] == rid for x in ngung)

    bat = client.patch(f"{API}/{rid}/active", json={"active": True}, headers=h)
    assert bat.status_code == 200 and bat.json()["active"] is True

    # PUT một khoá vẫn phải 422 — đó là lý do route PATCH tồn tại, không phải đường dự phòng.
    assert client.put(f"{API}/{rid}", json={"active": False}, headers=h).status_code == 422


# --- Nhân bản (POST /{id}/clone) ---------------------------------------------


def test_clone_copy_toan_bo_cot_ma_moi_ten_them_hau_to(client):
    """`MA_TU_SINH=True` ở danh mục này ⇒ bản sao KHÔNG lấy `<mã>-COPY`, mà xin mã mới `KH-####`
    y hệt lúc tạo tay — hai đường sinh mã (tạo mới / nhân bản) không được lệch nhau."""
    h = _admin(client)
    goc = _mk(client, h, ten="ZZ Bồi 3 lớp", unit_price=170).json()
    r = client.post(f"{API}/{goc['id']}/clone", headers=h)
    assert r.status_code == 201, r.text
    ban_sao = r.json()
    assert ban_sao["id"] != goc["id"]
    assert ban_sao["ma"] != goc["ma"] and ban_sao["ma"].startswith("KH-")
    assert ban_sao["ten"] == "ZZ Bồi 3 lớp (bản sao)"
    assert ban_sao["unit_price"] == 170
    assert ban_sao["department_id"] == goc["department_id"]


def test_clone_bao_khong_thay_dong_goc(client):
    h = _admin(client)
    r = client.post(f"{API}/999999/clone", headers=h)
    assert r.status_code == 404, r.text


# --- Tab Nhật ký -------------------------------------------------------------
# Trước 17/08/2026 bảng này KHÔNG ghi dòng nhật ký nào: CRUD của nó nằm ở router Lương, ngoài nền
# danh mục. Ai đổi đơn giá lúc nào là không tra được — mà đó là TIỀN của công nhân.


def _nhat_ky(client, h, rid):
    r = client.get(f"/api/nhat-ky-danh-muc/cong_viec_khoan/{rid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_nhat_ky_ghi_du_tao_sua_ngung_dung(client):
    h = _admin(client)
    rid = _mk(client, h, ten="ZZ Có nhật ký", unit_price=250).json()["id"]
    assert any(i["action"] == "dm_tao" for i in _nhat_ky(client, h, rid)), "thiếu dòng TẠO"

    client.put(f"{API}/{rid}", json={
        "ten": "ZZ Có nhật ký", "department_id": _to_id(client, h), "unit": "to",
        "unit_price": 300,
    }, headers=h)
    dong = _nhat_ky(client, h, rid)
    sua = [i for i in dong if i["action"] == "dm_sua"]
    assert sua, "thiếu dòng SỬA"
    # Nhãn tiếng Việt + hậu tố ĐVT của chính bản ghi ("đ/to"), không phải tên cột `unit_price`.
    assert "Đơn giá" in sua[0]["detail"], sua[0]["detail"]
    assert "đ/to" in sua[0]["detail"], sua[0]["detail"]

    client.patch(f"{API}/{rid}/active", json={"active": False}, headers=h)
    assert len([i for i in _nhat_ky(client, h, rid) if i["action"] == "dm_sua"]) >= 2, \
        "ngừng dùng cũng phải để lại vết — nó ảnh hưởng mọi ô chọn của hệ"


def test_nhat_ky_khong_ghi_khi_khong_doi_gi(client):
    """Bấm Lưu mà giữ nguyên = không phải sự kiện. Ghi vào thì nhật ký loãng, mất ngữ cảnh."""
    h = _admin(client)
    to_id = _to_id(client, h)
    rid = _mk(client, h, ten="ZZ Không đổi", department_id=to_id).json()["id"]
    truoc = len(_nhat_ky(client, h, rid))
    client.put(f"{API}/{rid}", json={"ten": "ZZ Không đổi", "department_id": to_id,
                                     "unit": "to", "unit_price": 100}, headers=h)
    assert len(_nhat_ky(client, h, rid)) == truoc


def test_ghi_nhat_ky_va_ban_ghi_di_chung_MOT_giao_dich(client):
    """Repo chỉ `flush()`, service chốt sau khi audit xong ⇒ audit nổ thì bản ghi cũng không vào.

    Kiểm bằng cách đếm: mỗi dòng tạo ra phải có ĐÚNG một dòng nhật ký tạo — không có cảnh "bản ghi
    nằm đó mà không có vết"."""
    h = _admin(client)
    rid = _mk(client, h, ten="ZZ Một giao dịch").json()["id"]
    tao = [i for i in _nhat_ky(client, h, rid) if i["action"] == "dm_tao"]
    assert len(tao) == 1, tao
