"""HỢP ĐỒNG HTTP của mọi màn Cấu hình danh mục — lưới an toàn TRƯỚC khi rút trừu tượng.

Không kiểm nghiệp vụ (10 file test tầng service đã lo). Chỉ kiểm thứ mà refactor router/repo dễ
làm gãy IM LẶNG, và hiện KHÔNG file nào phủ: mã HTTP, khoá trong JSON trả về, phân trang qua
query string, và ai đọc/ghi được gì.

Vì sao cần: 9/11 file test danh mục đang gọi thẳng `Service(Repo(db))`, tức là đi vòng qua tầng
HTTP. Đổi một `response_model` hay gỡ nhầm một dependency quyền thì test vẫn xanh, chỉ có người
dùng thấy hỏng.

⚠️ DB test là SQLite in-memory DÙNG CHUNG cả phiên (StaticPool), `client` fixture wipe schema mỗi
test nhưng seed lại chạy — nên mọi bản ghi test đặt tiền tố `ZZ` và mọi khẳng định lọc theo tiền
tố đó. KHÔNG assert `total == N`.
"""
from __future__ import annotations

import pytest

from tests.test_catalog_costing_read import _h


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _doan_tim(ten: str) -> str:
    """Đoạn chuỗi dùng để thử ô tìm kiếm, cắt bỏ phần có chữ HOA ngoài ASCII.

    KHÔNG phải để né lỗi code: `lower()` của SQLite chỉ hạ được A–Z, nên `"Đơn vị"` không bao giờ
    khớp `q="đơn vị"` — trong khi Postgres (dev + prod) hạ đủ Unicode và tìm ra bình thường. Ép
    test đỏ vì khác biệt của engine test là đánh lạc hướng người đọc kết quả.
    """
    idx = max((i for i, ch in enumerate(ten) if ch.isupper() and not ch.isascii()), default=-1)
    return ten[idx + 1:].strip() or ten


def _to_sx_id(client, h) -> int:
    """Id một TỔ sản xuất — `department_id` bắt buộc của Công việc khoán.

    Lấy từ chính endpoint mà form dùng (`/api/cong-doan/phong-ban`), không tự tạo tổ: tổ đó phải là
    nút LÁ trong khối Sản xuất mới hiện ở ô chọn, mà luật đó nằm ở service — test tự dựng một
    `Department` là dựng một tổ mà form thật không mời chọn.
    """
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


def _chung_loai_id(client, h) -> int:
    r = client.post("/api/vat-lieu-kho/chung-loai-giay",
                    json={"ma": "ZZCLG", "ten": "ZZ Chủng loại"}, headers=h)
    return r.json()["id"] if r.status_code == 201 else \
        client.get("/api/vat-lieu-kho/chung-loai-giay?q=ZZCLG", headers=h).json()["items"][0]["id"]


# (path, module quyền, dựng payload, mã tự sinh?, DELETE là xoá mềm?)
DANH_MUC = [
    ("/api/cong-doan", "dm_cong_doan",
     lambda c, h, i: {"ma": f"ZZCD{i}", "ten": f"ZZ Công đoạn {i}", "nhom": "finishing",
                      "pricing_basis": "per_finished_qty"}, False, False),
    ("/api/loai-san-pham", "dm_loai_san_pham",
     lambda c, h, i: {"ma": f"ZZSP{i}", "ten": f"ZZ SP {i}", "structural_type": "flat"},
     False, False),
    ("/api/bu-hao", "dm_bu_hao",
     lambda c, h, i: {"ma": f"ZZBH{i}", "ten": f"ZZ Bù hao {i}"}, False, False),
    # Công việc khoán (17/08/2026): mã tự sinh `KH-####`, DELETE xoá HẲN khi chưa ai dùng (dòng test
    # chưa có định mức đầu việc nào trỏ tới) — cùng luật với Công đoạn · Bù hao, khác Kho.
    ("/api/cong-viec-khoan", "dm_cong_viec_khoan",
     lambda c, h, i: {"ten": f"ZZ Việc khoán {i}", "department_id": _to_sx_id(c, h),
                      "unit": "to", "unit_price": 100 + i}, True, False),
    ("/api/don-vi", "dm_don_vi",
     lambda c, h, i: {"ma": f"zzdv{i}", "ten": f"ZZ Đơn vị {i}"}, False, False),
    ("/api/khuon-be", "khuon_be",
     lambda c, h, i: {"ten": f"ZZ Khuôn {i}"}, True, False),
    ("/api/kho", "dm_kho_hang",
     lambda c, h, i: {"ten": f"ZZ Kho {i}"}, True, True),
    ("/api/vat-lieu-kho/chung-loai-giay", "dm_chung_loai_giay",
     lambda c, h, i: {"ma": f"ZZCL{i}", "ten": f"ZZ Chủng loại {i}"}, False, False),
    ("/api/vat-lieu-kho/giay", "dm_giay",
     lambda c, h, i: {"ma": f"ZZG{i}", "ten": f"ZZ Giấy {i}", "gsm": 100,
                      "chung_loai_giay_id": _chung_loai_id(c, h)}, False, False),
    ("/api/vat-lieu-kho/vat-tu-in-an", "dm_vat_tu",
     lambda c, h, i: {"ma": f"ZZVT{i}", "ten": f"ZZ Vật tư {i}"}, False, False),
    ("/api/may-thiet-bi", "dm_thiet_bi",
     lambda c, h, i: {"ma": f"ZZM{i}", "ten": f"ZZ Máy {i}", "loai_may": "Máy in",
                      "so_nhan_cong": 1}, False, False),
]
IDS = [d[0] for d in DANH_MUC]


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_list_tra_dung_phong_bi(client, path, module, payload, auto_ma, xoa_mem):
    """`{items,total,page,size}` — FE đọc cả bốn khoá; thiếu một cái là phân trang câm."""
    r = client.get(path, headers=_admin(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"items", "total", "page", "size"} <= set(body), f"{path} thiếu khoá: {sorted(body)}"
    assert isinstance(body["items"], list)


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_phan_trang_va_tim_kiem_qua_query_string(client, path, module, payload, auto_ma, xoa_mem):
    """Cắt trang + lọc phải Ở MÁY CHỦ. Test đi qua query string đúng như FE gửi."""
    h = _admin(client)
    tao = [client.post(path, json=payload(client, h, i), headers=h) for i in (1, 2, 3)]
    assert all(t.status_code == 201 for t in tao), [t.text for t in tao]

    mot = client.get(f"{path}?page=1&size=1", headers=h).json()
    assert len(mot["items"]) == 1 and mot["size"] == 1 and mot["page"] == 1
    assert mot["total"] >= 3

    ten = tao[0].json()["ten"]
    tim = client.get(f"{path}?q={_doan_tim(ten)}", headers=h).json()
    assert any(x["ten"] == ten for x in tim["items"]), f"{path}: tìm theo tên không ra"

    ma = tao[0].json()["ma"]
    assert any(x["ma"] == ma for x in client.get(f"{path}?q={ma}", headers=h).json()["items"]), \
        f"{path}: tìm theo mã không ra"

    # `size` vượt trần: hoặc bị kẹp, hoặc 422 — nhưng KHÔNG được đổ cả bảng về.
    qua = client.get(f"{path}?size=9999", headers=h)
    assert qua.status_code in (200, 422)
    if qua.status_code == 200:
        assert qua.json()["size"] <= 200


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_vong_crud_qua_http(client, path, module, payload, auto_ma, xoa_mem):
    """POST 201 → GET 200 → PUT 200 → DELETE 204. Đây là test DELETE đầu tiên đi qua HTTP:
    `test_khuon_be.py` mô phỏng xoá bằng `svc.update(active=False)`, tức là NÉ chính endpoint."""
    h = _admin(client)
    body = payload(client, h, 7)
    tao = client.post(path, json=body, headers=h)
    assert tao.status_code == 201, tao.text
    item_id = tao.json()["id"]
    if auto_ma:
        assert tao.json()["ma"], f"{path}: mã tự sinh mà trả về rỗng"

    assert client.get(f"{path}/{item_id}", headers=h).status_code == 200

    sua = client.put(f"{path}/{item_id}", json={**body, "ma": tao.json()["ma"],
                                                "ten": "ZZ Đã sửa"}, headers=h)
    assert sua.status_code == 200, sua.text
    assert sua.json()["ten"] == "ZZ Đã sửa"

    assert client.delete(f"{path}/{item_id}", headers=h).status_code == 204
    con = client.get(f"{path}/{item_id}", headers=h)
    if xoa_mem:
        # Xoá mềm: bản ghi CÒN (lịch sử phiếu vẫn trỏ tới), chỉ tắt cờ.
        assert con.status_code == 200 and con.json()["active"] is False
    else:
        assert con.status_code == 404


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_trung_ma_tra_409(client, path, module, payload, auto_ma, xoa_mem):
    """409 = XUNG ĐỘT TRẠNG THÁI, không phải 422 (dữ liệu gửi lên chẳng sai gì cả)."""
    if auto_ma:
        pytest.skip("mã do server cấp — không có đường gửi trùng")
    h = _admin(client)
    body = payload(client, h, 5)
    assert client.post(path, json=body, headers=h).status_code == 201
    lai = client.post(path, json=body, headers=h)
    assert lai.status_code == 409, f"{path}: trùng mã trả {lai.status_code}, mong 409"


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_khong_dang_nhap_thi_khong_vao_duoc(client, path, module, payload, auto_ma, xoa_mem):
    assert client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("path,module,payload,auto_ma,xoa_mem", DANH_MUC, ids=IDS)
def test_row_khong_nuot_field(client, path, module, payload, auto_ma, xoa_mem):
    """BẪY Pydantic: service trả dict + `response_model` ⇒ field chưa khai ở schema Out bị NUỐT
    IM LẶNG và FE nhận `undefined`. Khoá FE đang đọc phải CÓ MẶT, kể cả khi giá trị là None."""
    h = _admin(client)
    tao = client.post(path, json=payload(client, h, 9), headers=h)
    assert tao.status_code == 201, tao.text
    row = tao.json()
    assert {"id", "ma", "ten"} <= set(row), f"{path}: thiếu khoá cơ bản — {sorted(row)}"
    # `may_thiet_bi` CỐ Ý không có cờ `active` (gỡ 11/08/2026, máy dừng khai theo khoảng thời
    # gian ở `machine_unavailable_periods`) — 9 danh mục còn lại thì phải có.
    if path != "/api/may-thiet-bi":
        assert "active" in row, f"{path}: thiếu `active` ⇒ FE không vẽ được badge Đã ngừng"


def test_openapi_dung_duoc(client):
    """Sinh được OpenAPI = không có route nào trùng tên/`operation_id`. Đây là cái gãy đầu tiên
    khi một factory sinh router chạy nhiều lần mà quên tham số hoá tên."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["paths"]


def test_items_khong_con_list_tran_trong_openapi(client):
    """`items: list` TRẦN làm OpenAPI mất type ⇒ client sinh code ra `any[]`.

    Bốn schema từng phạm: `khuon_be.py:39` · `kho_hang.py:29` · `bu_hao.py:41` ·
    `vat_lieu_kho.py:136`. Cả bốn đã khai kiểu dòng ở đợt B5 (15/08/2026) nên test này ASSERT
    thật, không còn xfail.

    ⚠️ BỘ DÒ CŨ KHÔNG BẮT ĐƯỢC GÌ — nó tìm schema THIẾU HẲN khoá `items`, trong khi Pydantic
    sinh cho `list` trần ra `{"type": "array", "items": {}}`: khoá CÓ mặt nhưng RỖNG. Vì thế
    test vẫn xanh suốt trong lúc bốn schema kia đang hỏng. Nay bắt đúng ca `items` rỗng.
    """
    spec = client.get("/openapi.json").json()
    xau = []
    for ten, sch in spec["components"]["schemas"].items():
        it = (sch.get("properties") or {}).get("items")
        if it is not None and it.get("type") == "array" and not it.get("items"):
            xau.append(ten)
    assert not xau, f"còn schema khai `items: list` trần (OpenAPI mất type): {sorted(xau)}"


# --- `GET {prefix}/ma-goi-y` — mã kế tiếp do MÁY CHỦ cấp (đợt B7) -------------------------
#
# Trước 15/08/2026 frontend tự ĐOÁN tiền tố bằng cách dò chuỗi trong URL
# (`frontend/src/pages/danh-muc/maGoiY.ts`, bảng `tienToMa` viết cứng 8 nhánh) rồi bắn HAI request
# để mò mã lớn nhất. Luật đánh mã vốn thuộc về danh mục, không thuộc màn.

# (đường dẫn, tiền tố mã) — CHỈ danh mục thật sự đánh số theo một dãy duy nhất.
CO_MA_GOI_Y = [
    ("/api/kho", "KHO-"),
    ("/api/khuon-be", "KB-"),
    ("/api/cong-doan", "CD-"),
    ("/api/loai-san-pham", "LSP-"),
    # Công việc khoán: mã do MÁY cấp hẳn (không có ô Mã trên form) — xưởng gọi việc khoán bằng tên.
    ("/api/cong-viec-khoan", "KH-"),
]
# Danh mục KHÔNG có "mã kế tiếp": mã là chữ có nghĩa (`kg`, `COUCHE`, `MUC-CMYK`) hoặc đánh theo
# LOẠI (`IN-01`, `CM-03`) ⇒ cố ý không mở route, chứ không phải quên.
KHONG_MA_GOI_Y = ["/api/don-vi", "/api/bu-hao", "/api/may-thiet-bi",
                  "/api/vat-lieu-kho/giay", "/api/vat-lieu-kho/vat-tu-in-an"]


@pytest.mark.parametrize("path,tien_to", CO_MA_GOI_Y, ids=[p for p, _ in CO_MA_GOI_Y])
def test_ma_goi_y_tra_ma_ke_tiep(client, path, tien_to):
    """`{"ma": "<tiền tố>####"}` — và mã đó phải CHƯA có ai dùng (dùng luôn được để tạo mới)."""
    h = _admin(client)
    r = client.get(f"{path}/ma-goi-y", headers=h)
    assert r.status_code == 200, r.text
    ma = r.json()["ma"]
    assert ma.startswith(tien_to) and ma[len(tien_to):].isdigit(), \
        f"{path}: mã gợi ý sai khuôn — {ma}"
    trung = client.get(f"{path}?q={ma}", headers=h).json()["items"]
    assert not any(x["ma"] == ma for x in trung), f"{path}: mã gợi ý {ma} ĐÃ có người dùng"


def test_ma_goi_y_nhay_len_sau_khi_tao(client):
    """Tạo xong thì lần hỏi sau phải ra mã KHÁC — không thì hai người khai liên tiếp đụng nhau."""
    h = _admin(client)
    truoc = client.get("/api/kho/ma-goi-y", headers=h).json()["ma"]
    tao = client.post("/api/kho", json={"ten": "ZZ Kho gợi ý"}, headers=h)
    assert tao.status_code == 201, tao.text
    assert tao.json()["ma"] == truoc, "mã tự sinh lúc tạo phải khớp mã vừa gợi ý"
    assert client.get("/api/kho/ma-goi-y", headers=h).json()["ma"] != truoc


@pytest.mark.parametrize("path", KHONG_MA_GOI_Y, ids=KHONG_MA_GOI_Y)
def test_danh_muc_khai_ma_tay_khong_mo_ma_goi_y(client, path):
    """Không mở route thì "ma-goi-y" rơi vào `/{item_id}` → 422 (không ép được sang int), hoặc
    404. Cái KHÔNG được phép là 200 kèm một mã bịa."""
    r = client.get(f"{path}/ma-goi-y", headers=_admin(client))
    assert r.status_code != 200, f"{path}: không có quy ước đánh số mà vẫn gợi ý mã — {r.text}"


def test_ma_goi_y_van_can_dang_nhap(client):
    assert client.get("/api/kho/ma-goi-y").status_code in (401, 403)


# --- Hàng MÁY trả kèm TÊN đơn vị tốc độ (đợt B7) -----------------------------------------


def test_hang_may_tra_kem_ten_don_vi_toc_do(client):
    """⚠️ BẪY Pydantic đã dính 4 lần: service trả thêm field mà schema `Out` không khai thì bị
    NUỐT IM LẶNG, FE nhận `undefined` và không có lỗi nào. Vì thế test này đi qua HTTP THẬT
    (không phải tầng service) và soi cả ba cửa: tạo · danh sách · chi tiết.
    """
    h = _admin(client)
    dv = client.post("/api/don-vi",
                     json={"ma": "zzto_gio", "ten": "ZZ Tờ mỗi giờ", "dung_lam_toc_do": True},
                     headers=h)
    assert dv.status_code in (201, 409), dv.text

    tao = client.post("/api/may-thiet-bi", headers=h, json={
        "ma": "ZZMTD1", "ten": "ZZ Máy có đơn vị tốc độ", "loai_may": "Máy in",
        "so_nhan_cong": 1, "toc_do": 8000, "don_vi_toc_do": "zzto_gio"})
    assert tao.status_code == 201, tao.text
    assert tao.json().get("don_vi_toc_do_ten") == "ZZ Tờ mỗi giờ", \
        f"POST nuốt mất `don_vi_toc_do_ten`: {sorted(tao.json())}"

    may_id = tao.json()["id"]
    chi_tiet = client.get(f"/api/may-thiet-bi/{may_id}", headers=h).json()
    assert chi_tiet["don_vi_toc_do_ten"] == "ZZ Tờ mỗi giờ"

    dong = next(x for x in client.get("/api/may-thiet-bi?q=ZZMTD1", headers=h).json()["items"]
                if x["id"] == may_id)
    assert dong["don_vi_toc_do_ten"] == "ZZ Tờ mỗi giờ"


def test_may_chua_khai_don_vi_toc_do_thi_ten_la_None_chu_khong_vang_khoa(client):
    """Khoá phải CÓ MẶT kể cả khi rỗng — FE đọc `row.don_vi_toc_do_ten`, vắng khoá là undefined
    và cột hiện trống mà không phân biệt được "chưa khai" với "lỗi tải"."""
    h = _admin(client)
    tao = client.post("/api/may-thiet-bi", headers=h, json={
        "ma": "ZZMTD2", "ten": "ZZ Máy không đơn vị", "loai_may": "Máy in", "so_nhan_cong": 1})
    assert tao.status_code == 201, tao.text
    assert "don_vi_toc_do_ten" in tao.json()
    assert tao.json()["don_vi_toc_do_ten"] is None


def test_nhom_may_tra_du_phong_bi_phan_trang(client):
    """`/api/nhom-may` dùng chung `crud()` của frontend nên phải đủ `{items,total,page,size}` —
    trước 15/08/2026 thiếu `page`/`size` nên phân trang câm (undefined)."""
    h = _admin(client)
    r = client.get("/api/nhom-may", headers=h)
    assert r.status_code == 200, r.text
    assert {"items", "total", "page", "size"} <= set(r.json()), sorted(r.json())
    assert r.json()["size"] == len(r.json()["items"])


def test_gan_go_anh_mat_hang_khong_co_that_tra_404(client):
    """Ảnh minh hoạ của mặt hàng đã bị xoá ⇒ 404 kèm câu tiếng Việt, KHÔNG phải 500.

    Hai handler ảnh (`POST|DELETE /{loai}/{id}/anh`) từng gọi `_err(e)` — một tên không tồn tại
    trong module — nên nhánh "không tìm thấy mặt hàng" nổ `NameError` thành 500 trắng thay vì
    404. Người dùng gặp đúng lúc hai người cùng mở một mặt hàng, một người xoá xong người kia
    mới bấm gắn ảnh.
    """
    h = _admin(client)
    anh = ("anh.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")
    r = client.post("/api/vat-lieu-kho/giay/99999999/anh", headers=h, files={"file": anh})
    assert r.status_code == 404, r.text
    assert r.json()["detail"], "404 phải kèm câu giải thích"

    r = client.delete("/api/vat-lieu-kho/vat_tu/99999999/anh", headers=h)
    assert r.status_code == 404, r.text
    assert r.json()["detail"]
