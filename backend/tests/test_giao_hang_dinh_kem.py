"""File minh chứng của chuyến giao — ảnh/PDF (chủ chốt 22/08/2026).

Việc thật: hàng đi kèm hoá đơn. Trước lúc đi thì đính hoá đơn để tài xế cầm theo; giao xong thì
chụp lại tờ khách đã ký. Cả hai đều là file của CHUYẾN đó.

Bytes nằm ở kho file dùng chung, bảng chỉ giữ metadata — mirror `payment_receipt_attachments`.
"""
from __future__ import annotations

import io

from tests.test_giao_hang_api import (
    _admin,
    _don_da_chot,
    _len_kh,
    _tai_xe,
    _tao_yc,
)

ANH = ("hoa-don.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 64), "image/png")


def _chuyen(client, h, *, suffix: str) -> int:
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh(client, h, yc["id"], _tai_xe(f"TX-{suffix}"))
    assert r.status_code == 201, r.text
    return r.json()["trip"]["id"]


def _tai_len(client, h, trip, *, ten="hoa-don.png", noi_dung=b"PNGDATA", mime="image/png"):
    return client.post(f"/api/giao-hang/trips/{trip}/dinh-kem",
                       files={"file": (ten, io.BytesIO(noi_dung), mime)}, headers=h)


def _ds(client, h, trip) -> list[dict]:
    r = client.get(f"/api/giao-hang/trips/{trip}/dinh-kem", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# =============================================================================================
# Đính kèm được, và đính ở BẤT KỲ lúc nào trong đời chuyến
# =============================================================================================
def test_DINH_KEM_ANH_va_doc_lai_duoc(client):
    """⭐ Lý do cả tính năng: có chỗ giữ minh chứng đã giao, không phải tin miệng."""
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk1")
    assert _ds(client, h, trip) == []

    r = _tai_len(client, h, trip)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trip_id"] == trip
    assert body["file_name"].endswith(".png")
    assert body["file_url"].startswith("/api/files/"), body["file_url"]

    ds = _ds(client, h, trip)
    assert [x["id"] for x in ds] == [body["id"]]


def test_dinh_duoc_TU_LUC_LEN_KE_HOACH_khong_phai_doi_giao_xong(client):
    """Trước lúc đi là hoá đơn tài xế cầm theo — chặn theo trạng thái là bắt đoán đúng thời điểm.

    Chuyến ở `da_len_ke_hoach` (chưa lấy hàng) vẫn phải đính được.
    """
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk2")
    assert _tai_len(client, h, trip).status_code == 201


def test_dinh_duoc_NHIEU_FILE(client):
    """Một chuyến thường có hoá đơn + biên nhận + ảnh hàng — không ép một file."""
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk3")
    _tai_len(client, h, trip, ten="hoa-don.pdf", noi_dung=b"%PDF-1.4", mime="application/pdf")
    _tai_len(client, h, trip, ten="bien-nhan.jpg", noi_dung=b"JPG", mime="image/jpeg")
    assert len(_ds(client, h, trip)) == 2


# =============================================================================================
# Những thứ KHÔNG nhận
# =============================================================================================
def test_CHI_NHAN_anh_hoac_PDF(client):
    """⭐ Nhận mọi loại file là biến kho chứng từ thành ổ đĩa chung — và mở đường cho file thực thi."""
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk4")
    r = _tai_len(client, h, trip, ten="script.exe", noi_dung=b"MZ", mime="application/x-msdownload")
    assert r.status_code == 400, r.text
    assert _ds(client, h, trip) == []


def test_TEP_RONG_bi_chan(client):
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk5")
    assert _tai_len(client, h, trip, noi_dung=b"").status_code == 400


def test_TEP_QUA_LON_bi_chan(client):
    """Trần 10 MB — cùng ngưỡng với đính kèm chứng từ kế toán, một luật cho cả hệ."""
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk6")
    r = _tai_len(client, h, trip, noi_dung=b"x" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 400, r.text
    assert "10 MB" in r.json()["detail"]


# =============================================================================================
# Xoá
# =============================================================================================
def test_XOA_duoc_ke_ca_khi_chuyen_DA_CO_KET_QUA(client):
    """⭐ Tài xế chụp mờ, chụp nhầm là chuyện thường. Khoá xoá sau khi ghi kết quả là buộc người ta
    để rác lại trong hồ sơ — mà rác trong hồ sơ chứng từ còn tệ hơn thiếu."""
    from tests.test_giao_hang_api import _di_toi_dang_giao

    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk7")
    fid = _tai_len(client, h, trip).json()["id"]
    _di_toi_dang_giao(client, h, trip)
    assert client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": 8, "nguoi_nhan_thuc_te": "Chi Lan"}, headers=h
    ).status_code == 200

    r = client.delete(f"/api/giao-hang/trips/{trip}/dinh-kem/{fid}", headers=h)
    assert r.status_code == 204, r.text
    assert _ds(client, h, trip) == []


def test_KHONG_xoa_duoc_file_cua_CHUYEN_KHAC(client):
    """⭐ Truyền id file của chuyến khác vào đường xoá ⇒ 404, không phải xoá hộ.

    Lọc theo danh sách mà quên gác đường id là hàng rào vẽ trên màn hình.
    """
    h = _admin(client)
    a = _chuyen(client, h, suffix="dk8a")
    b = _chuyen(client, h, suffix="dk8b")
    fid_a = _tai_len(client, h, a).json()["id"]

    r = client.delete(f"/api/giao-hang/trips/{b}/dinh-kem/{fid_a}", headers=h)
    assert r.status_code == 404, r.text
    assert len(_ds(client, h, a)) == 1, "file của chuyến A bị xoá qua đường chuyến B"


# =============================================================================================
# Đọc lại file — hai lỗ đã vá ngày 22/08/2026
# =============================================================================================
def test_DOC_LAI_DUOC_file_vua_tai_len(client):
    """⭐ Tải lên xong mà bấm vào không mở được thì tính năng coi như không có.

    `file_url` là đường TƯƠNG ĐỐI; giao diện phải ghép gốc API (`assetUrl`) vì nó chạy khác cổng.
    Ở đây kiểm vế máy chủ: đúng đường đó phải trả về đúng bytes đã tải lên.
    """
    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk9")
    noi_dung = bytes.fromhex("89504e470d0a1a0a") + b"anh-hoa-don"
    url = _tai_len(client, h, trip, noi_dung=noi_dung).json()["file_url"]

    r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    assert r.content == noi_dung, "đọc lại ra bytes khác lúc tải lên"


def test_FILE_GIAO_HANG_bi_GAC_QUYEN_khong_phai_ai_dang_nhap_cung_xem(client):
    """⭐ Lỗ bảo mật đã vá: thư mục `giao-hang` chưa khai trong bảng gác quyền của `/api/files`
    thì rơi vào nhánh "không có khoá" ⇒ BẤT KỲ ai đăng nhập cũng đọc được.

    Trên tờ hoá đơn có tên khách, mặt hàng và ĐƠN GIÁ — không phải thứ ai cũng nên xem.

    ⚠️ `/api/files` xác thực bằng COOKIE, không đọc header Bearer (`deps.get_file_user`) — vì
    `<img src>` không gắn được header. Nên muốn thử "người ngoài" thì phải ĐĂNG NHẬP THẬT để lấy
    cookie của họ; phát token rồi gắn header là vẫn chạy dưới cookie của người đăng nhập trước đó,
    và test sẽ xanh giả.
    """
    from tests.test_giao_hang_api import _vai

    h = _admin(client)
    trip = _chuyen(client, h, suffix="dk10")
    url = _tai_len(client, h, trip).json()["file_url"]

    _vai("nguoi-ngoai-dk", can_read=False)          # tài khoản KHÔNG có quyền đọc giao hàng
    client.cookies.clear()
    dn = client.post("/api/auth/login", json={"username": "nguoi-ngoai-dk", "password": "x"})
    assert dn.status_code == 200, dn.text

    r = client.get(url)
    assert r.status_code == 403, f"người không có quyền giao hàng vẫn đọc được file: {r.status_code}"
