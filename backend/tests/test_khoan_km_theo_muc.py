"""Khoán km theo MỨC — nghiệm thu `docs/prd-khoan-km-giao-hang.md` §11 (12/09/2026).

Mô hình chủ chốt:

    Mức khoán km  ──1──┬──n──  Xe  ──1──n──  Chuyến giao
    (bảng bậc giá)     │        (biển số)     (tra bậc theo mức của xe)

Tạo MỨC (kèm bảng bậc), rồi khi khai xe thì gán xe đó ăn mức nào. Cần một giá khác thì tạo MỨC
MỚI — không sửa mức đang có, vì mức đang có là của những xe khác.

Vì sao có đợt này: đo `SAN LUONG T08.2026.xls` thì công thức KHÔNG sai — 292 chuyến của ba xe
2,5T/3,5T khớp từng đồng. Sai ở chỗ hệ thống chỉ giữ MỘT thang cho cả phòng, trong khi xưởng dùng
HAI: thang xe 5 tấn = thang thường **× 1,1 ở cả 8 bậc**. Xe 5 tấn vì thế bị tính thiếu đúng 10% —
2.696.650đ riêng tháng 8. Kiểu hỏng này không làm đỏ bài nào và không báo lỗi gì: vẫn ra tiền, chỉ
ra thiếu. Nên nghiệm thu phải bằng SỐ THẬT lấy từ file gốc.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.delivery import DeliveryTrip
from tests.test_giao_hang_api import _admin, _di_toi_dang_giao, _don_da_chot, _len_kh, _tao_yc
from tests.test_khoan_km_giao_hang import PHONG_GH, _bat_khoi_giao_hang, _tai_xe

# Thang THƯỜNG — nguyên văn sheet `xe tải a Giang` (2,5T) / `a sang` · `a Tùng` (3,5T).
THANG_THUONG = [
    {"up_to_km": 5, "don_gia": 18000}, {"up_to_km": 20, "don_gia": 11200},
    {"up_to_km": 40, "don_gia": 8200}, {"up_to_km": 60, "don_gia": 7200},
    {"up_to_km": 80, "don_gia": 6300}, {"up_to_km": 100, "don_gia": 5400},
    {"up_to_km": 150, "don_gia": 4500}, {"up_to_km": None, "don_gia": 3600},
]
# Thang XE 5 TẤN — sheet `xe tải a Việt`. Đúng bằng thang thường × 1,1, không làm tròn chỗ nào.
THANG_5T = [
    {"up_to_km": 5, "don_gia": 19800}, {"up_to_km": 20, "don_gia": 12320},
    {"up_to_km": 40, "don_gia": 9020}, {"up_to_km": 60, "don_gia": 7920},
    {"up_to_km": 80, "don_gia": 6930}, {"up_to_km": 100, "don_gia": 5940},
    {"up_to_km": 150, "don_gia": 4950}, {"up_to_km": None, "don_gia": 3960},
]
GOC = "/api/giao-hang/muc-khoan-km"


# --- dựng cảnh -------------------------------------------------------------------------------
def _tao_muc(client, h, ten: str, _bo_qua=None, *, cho=201):
    r = client.post(GOC, json={"ten": ten}, headers=h)
    assert r.status_code == cho, r.text
    if r.status_code != 201:
        return None
    return next(m for m in r.json()["items"] if m["ten"] == ten)["id"]


def _bac_muc(client, h, muc_id: int, items, *, cho=200):
    """Ghi bảng bậc của một mức. Hết tham số phòng ban từ 14/09/2026 — bậc thuộc về MỨC."""
    r = client.put(f"{GOC}/{muc_id}/bac", json={"items": items}, headers=h)
    assert r.status_code == cho, r.text
    return r


def _muc_co_gia(client, h, ten: str = "Mức có giá") -> int:
    """Một mức ĐÃ khai bậc (thang thường) — cho bài cần xe thật mà không soi giá.

    Từ 14/09/2026 xe bắt buộc có mức, và lên đơn bằng xe có mức chưa khai bậc bị chặn.
    """
    muc = _tao_muc(client, h, ten)
    _bac_muc(client, h, muc, THANG_THUONG)
    return muc


def _tao_xe(client, h, ma: str, ten: str, tai_trong=None, muc_id=None, *, cho=201):
    r = client.post("/api/xe", json={"ma": ma, "ten": ten, "tai_trong": tai_trong,
                                     "muc_khoan_km_id": muc_id}, headers=h)
    assert r.status_code == cho, r.text
    return r.json()["id"] if r.status_code == 201 else None


def _len_kh_kem_xe(client, h, request_id, tai_xe, xe_id):
    """POST kế hoạch KÈM xe. Từ 12/09/2026 xe là BẮT BUỘC ngay ở bước lên đơn, nên không dùng
    được `_len_kh` (nó không gửi xe) cho những bài đã khai xe trong danh mục."""
    from tests.test_giao_hang_api import _gio

    body = {"request_id": request_id, "employee_id": tai_xe,
            "gio_lay_hang": _gio(8), "gio_du_kien_giao": _gio(11)}
    if xe_id is not None:
        body["vehicle_id"] = xe_id
    return client.post("/api/giao-hang/plans", json=body, headers=h)


def _chuyen(client, h, *, suffix, tai_xe, km, xe_id=None, cho=200, cho_ke_hoach=201):
    """Đơn → yêu cầu → kế hoạch (kèm xe) → giao thành công. Trả `trip_id` (None nếu bị chặn)."""
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh_kem_xe(client, h, yc["id"], tai_xe, xe_id)
    assert r.status_code == cho_ke_hoach, r.text
    if r.status_code != 201:
        return None
    trip = r.json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": km, "nguoi_nhan_thuc_te": "Chi Lan"}, headers=h)
    assert r.status_code == cho, r.text
    return trip if r.status_code == 200 else None


def _da_chup(trip_id: int) -> float | None:
    db = SessionLocal()
    try:
        dg = db.get(DeliveryTrip, trip_id).don_gia_km
        return float(dg) if dg is not None else None
    finally:
        db.close()


# =============================================================================================
# Bài chính — đúng cảnh chủ mô tả: 2 mức, 4 xe
# =============================================================================================
def test_hai_muc_bon_xe_ra_dung_hai_gia(client):
    """⭐ Cảnh THẬT của xưởng: 2 mức, 4 xe, ba xe dùng chung một mức.

    Đây là điều mà gắn bảng giá thẳng vào từng xe KHÔNG làm được gọn: ba xe chung thang chỉ khai
    MỘT lần, nên không có đường nào để chúng lệch nhau.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)

    m_thuong = _tao_muc(client, h, "Xe 2,5–3,5 tấn", 3.5)
    m_5t = _tao_muc(client, h, "Xe 5 tấn", 5)
    _bac_muc(client, h, m_thuong, THANG_THUONG)
    _bac_muc(client, h, m_5t, THANG_5T)

    giang = _tao_xe(client, h, "61C-53270", "Xe a Giang", 2.5, m_thuong)
    sang = _tao_xe(client, h, "61C-52386", "Xe a Sang", 3.5, m_thuong)
    tung = _tao_xe(client, h, "51D-85366", "Xe a Tùng", 3.5, m_thuong)
    viet = _tao_xe(client, h, "51K-77404", "Xe a Việt", 5, m_5t)

    tx = _tai_xe("TX bon xe", phong=PHONG_GH)
    # 113 km rơi bậc "100–150": thang thường 4.500, thang 5 tấn 4.950.
    for i, xe in enumerate((giang, sang, tung)):
        t = _chuyen(client, h, suffix=f"m{i}", tai_xe=tx, km=113, xe_id=xe)
        assert _da_chup(t) == 4500.0, "ba xe chung mức phải ra CÙNG một giá"
    t5 = _chuyen(client, h, suffix="m5", tai_xe=tx, km=113, xe_id=viet)
    assert _da_chup(t5) == 4950.0, "xe 5 tấn phải ăn mức riêng của nó"
    assert _da_chup(t5) == 4500.0 * 1.1   # đúng 10% — chỗ đang bị trả thiếu


def test_sua_mot_muc_la_ca_nhom_xe_theo(client):
    """Giá trị lớn nhất của mô hình mức: tăng giá MỘT lần, cả nhóm xe theo.

    Gắn bảng giá thẳng vào từng xe thì đây là ba lần sửa, và quên một lần là một xe tụt lại ở giá
    cũ — im lặng, vẫn ra tiền, không ai thấy.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Xe thường", 3.5)
    _bac_muc(client, h, muc, THANG_THUONG)
    xe_a = _tao_xe(client, h, "51A-00001", "Xe A", 3.5, muc)
    xe_b = _tao_xe(client, h, "51A-00002", "Xe B", 3.5, muc)

    tx = _tai_xe("TX tang gia", phong=PHONG_GH)
    assert _da_chup(_chuyen(client, h, suffix="tg1", tai_xe=tx, km=113, xe_id=xe_a)) == 4500.0

    # Tăng bậc 100–150 từ 4.500 lên 5.000 — CHỈ sửa mức, không đụng xe nào.
    moi = [dict(b) for b in THANG_THUONG]
    moi[6]["don_gia"] = 5000
    _bac_muc(client, h, muc, moi)

    assert _da_chup(_chuyen(client, h, suffix="tg2", tai_xe=tx, km=113, xe_id=xe_a)) == 5000.0
    assert _da_chup(_chuyen(client, h, suffix="tg3", tai_xe=tx, km=113, xe_id=xe_b)) == 5000.0


def test_ca_tam_bac_khop_tung_dong_voi_sheet_goc(client):
    """Cả 8 bậc × 2 mức — không chỉ một điểm may mắn.

    Km chọn rơi GIỮA mỗi bậc, trừ hai mốc biên (5 và 150) cố tình lấy đúng trần: biên là chỗ
    `km ≤ trần` dễ lệch một đơn vị nhất.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    m_thuong = _tao_muc(client, h, "Thường", 3.5)
    m_5t = _tao_muc(client, h, "Năm tấn", 5)
    _bac_muc(client, h, m_thuong, THANG_THUONG)
    _bac_muc(client, h, m_5t, THANG_5T)
    xe_t = _tao_xe(client, h, "51B-00001", "Xe thường", 3.5, m_thuong)
    xe_5 = _tao_xe(client, h, "51B-00005", "Xe 5 tấn", 5, m_5t)

    tx = _tai_xe("TX tam bac", phong=PHONG_GH)
    for i, (km, thuong, nam) in enumerate([
        (5, 18000, 19800), (13, 11200, 12320), (30, 8200, 9020), (50, 7200, 7920),
        (70, 6300, 6930), (91, 5400, 5940), (150, 4500, 4950), (196, 3600, 3960),
    ]):
        assert _da_chup(_chuyen(client, h, suffix=f"b{i}a", tai_xe=tx, km=km,
                                xe_id=xe_t)) == float(thuong), f"{km} km · mức thường"
        assert _da_chup(_chuyen(client, h, suffix=f"b{i}b", tai_xe=tx, km=km,
                                xe_id=xe_5)) == float(nam), f"{km} km · mức 5 tấn"


# Hai bài "nấc lùi" cũ — xe chưa gán mức / mức chưa khai bậc thì rơi về đơn giá phẳng — đã ĐẢO
# NGƯỢC ngày 14/09/2026 (PRD §12, quyết định 4): cả hai ca nay bị CHẶN. Bài mới nằm ở
# `test_khoan_km_siet_chat.py`.


# =============================================================================================
# Luật giữ cho dữ liệu không nói dối
# =============================================================================================
def test_khong_xoa_duoc_muc_con_xe_dang_an(client):
    """Xoá mức còn xe dùng = để lại xe trỏ vào một mức không còn. Phải chặn."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Mức có xe", 5)
    _bac_muc(client, h, muc, THANG_5T)
    _tao_xe(client, h, "51D-00001", "Xe giữ mức", 5, muc)

    r = client.delete(f"{GOC}/{muc}", headers=h)
    assert r.status_code == 400, r.text
    assert "1 xe" in r.json()["detail"], r.text


def test_xoa_duoc_muc_khong_con_xe(client):
    _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Mức bỏ đi", 2)
    _bac_muc(client, h, muc, THANG_THUONG)
    r = client.delete(f"{GOC}/{muc}", headers=h)
    assert r.status_code == 200, r.text
    assert all(m["id"] != muc for m in r.json()["items"])


def test_ten_muc_khong_duoc_trung(client):
    """Tên là thứ người dùng đọc khi gán xe — hai mức cùng tên là gán mù."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    _tao_muc(client, h, "Xe 2 tấn", 2)
    _tao_muc(client, h, "xe 2 TẤN", 2, cho=400)   # khác hoa/thường vẫn là trùng


def test_danh_sach_muc_dem_dung_so_xe(client):
    """Màn cấu hình phải nói "sửa mức này là đổi giá của mấy xe" TRƯỚC khi người ta gõ."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Mức đếm xe", 3.5)
    _bac_muc(client, h, muc, THANG_THUONG)
    for i in range(3):
        _tao_xe(client, h, f"51E-0000{i}", f"Xe {i}", 3.5, muc)

    ds = client.get(GOC, headers=h).json()["items"]
    m = next(x for x in ds if x["id"] == muc)
    assert m["so_xe"] == 3
    assert [b["don_gia"] for b in m["items"]] == [b["don_gia"] for b in THANG_THUONG]


def test_ghi_bac_cho_mot_muc_khong_dung_muc_khac(client):
    """Vế xoá của `MucKhoanKmRepository.ghi_lai_bac` phải khoá theo ĐÚNG `muc_id`.

    Sai một chữ ở WHERE là lưu bậc cho một mức thì quét sạch bậc của mọi mức còn lại — rồi đám xe
    đó hết giá, lên đơn là vấp.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    m1 = _tao_muc(client, h, "Mức một", 3.5)
    m2 = _tao_muc(client, h, "Mức hai", 5)
    _bac_muc(client, h, m1, THANG_THUONG)
    _bac_muc(client, h, m2, [{"up_to_km": None, "don_gia": 1234}])

    ds = {m["id"]: m for m in client.get(GOC, headers=h).json()["items"]}
    assert len(ds[m1]["items"]) == 8
    assert len(ds[m2]["items"]) == 1 and ds[m2]["items"][0]["don_gia"] == 1234


def test_luat_cau_truc_bac_ap_cho_ca_duong_muc(client):
    """Bậc ∞ phải ở cuối, trần phải tăng dần, không hai bậc ∞."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Mức sai bậc", 5)

    _bac_muc(client, h, muc, [
        {"up_to_km": None, "don_gia": 3960}, {"up_to_km": 5, "don_gia": 19800}], cho=400)
    _bac_muc(client, h, muc, [
        {"up_to_km": 40, "don_gia": 9020}, {"up_to_km": 20, "don_gia": 12320}], cho=400)
    _bac_muc(client, h, muc, [
        {"up_to_km": None, "don_gia": 1}, {"up_to_km": None, "don_gia": 2}], cho=400)


# =============================================================================================
# Ô Xe lúc đóng chuyến
# =============================================================================================
def test_khai_xe_roi_thi_LEN_DON_da_bat_buoc_chon_xe(client):
    """⭐ Chặn NGAY Ở BƯỚC LÊN ĐƠN (chủ chốt 12/09/2026), không đợi tới lúc ghi kết quả.

    Bản đầu chỉ chặn lúc ghi kết quả với lý do "đổi xe phút chót là chuyện thường". Nhưng như thế
    người phân chuyến bỏ trống được, và cái giá dồn hết sang người đóng chuyến — lúc đó mới biết
    chuyến nào thiếu xe, mà hàng thì đã đi rồi.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    _tao_xe(client, h, "51F-00001", "Xe có thật", 5, _muc_co_gia(client, h))

    tx = _tai_xe("TX thieu xe", phong=PHONG_GH)
    _chuyen(client, h, suffix="tx1", tai_xe=tx, km=50, xe_id=None, cho_ke_hoach=400)


def test_khong_go_duoc_xe_khi_DOI_KE_HOACH(client):
    """Gỡ xe ở màn Đổi kế hoạch cũng bị chặn — không thì đó là cửa sau của luật trên."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    xe = _tao_xe(client, h, "51F-00002", "Xe đổi", 5, _muc_co_gia(client, h))
    tx = _tai_xe("TX doi kh", phong=PHONG_GH)

    oid, lid = _don_da_chot(suffix="dkh")
    yc = _tao_yc(client, h, oid, lid)
    trip = _len_kh_kem_xe(client, h, yc["id"], tx, xe).json()["trip"]["id"]
    r = client.put(f"/api/giao-hang/plans/{trip}", json={"vehicle_id": None}, headers=h)
    assert r.status_code == 400, r.text
    assert "chọn xe" in r.json()["detail"], r.text


def test_danh_muc_con_trong_thi_KHONG_doi_xe(client):
    """⭐ Luật chỉ BẬT khi đã có xe.

    Bật vô điều kiện thì ngày triển khai — lúc chưa ai kịp khai chiếc nào — mọi chuyến đang chạy
    đều không đóng được. Chặn cả phân hệ vì một ô vừa mới sinh ra là cái giá quá đắt.
    """
    _bat_khoi_giao_hang(don_gia=4330)
    h = _admin(client)

    tx = _tai_xe("TX chua co xe", phong=PHONG_GH)
    t = _chuyen(client, h, suffix="tx2", tai_xe=tx, km=113, xe_id=None)
    assert _da_chup(t) == 4330.0, "không có xe thì vẫn ăn đơn giá phẳng như cũ"
    assert t is not None, "danh mục trống mà đã chặn lên đơn thì ngày triển khai không ai đi giao được"


def test_gan_xe_vao_muc_khong_ton_tai_thi_bao_loi(client):
    _bat_khoi_giao_hang()
    h = _admin(client)
    r = client.post("/api/xe", json={"ma": "51G-00001", "ten": "Xe mức lạ",
                                     "muc_khoan_km_id": 999999}, headers=h)
    # 422 chứ không 400: nền danh mục dùng chung ánh xạ lỗi validate sang 422 (`catalog_base`).
    assert r.status_code == 422, r.text
    assert "Mức khoán km không tồn tại" in r.text


def test_hai_muc_so_bac_KHAC_NHAU(client, capsys):
    """⭐ Đúng ví dụ chủ nêu (12/09/2026): mức 1 có 8 bậc, mức 2 có 9 bậc.

    Số bậc là chuyện RIÊNG của từng mức — không có ràng buộc nào bắt hai mức phải cùng số bậc,
    cùng mốc km, hay cùng thứ gì. Mỗi mức tự mang bảng bậc của nó; xe gán mức nào thì tra bảng ấy.

    Bài này cố ý cho mức 5 tấn một bậc TĂNG THÊM (150–200) mà mức 2 tấn không có, rồi bắn hai
    chuyến 180 km để thấy hai mức rẽ hai giá khác nhau ở đúng đoạn đó.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)

    # MỨC 1 — xe 2 tấn, 8 bậc
    m2t = _tao_muc(client, h, "Xe 2 tấn", 2)
    bac_2t = [
        {"up_to_km": 5, "don_gia": 18000}, {"up_to_km": 20, "don_gia": 11200},
        {"up_to_km": 40, "don_gia": 8200}, {"up_to_km": 60, "don_gia": 7200},
        {"up_to_km": 80, "don_gia": 6300}, {"up_to_km": 100, "don_gia": 5400},
        {"up_to_km": 150, "don_gia": 4500}, {"up_to_km": None, "don_gia": 3600},
    ]
    _bac_muc(client, h, m2t, bac_2t)

    # MỨC 2 — xe 5 tấn, 9 bậc (thêm một bậc 150–200 mà mức 2 tấn không có)
    m5t = _tao_muc(client, h, "Xe 5 tấn", 5)
    bac_5t = [
        {"up_to_km": 5, "don_gia": 19800}, {"up_to_km": 20, "don_gia": 12320},
        {"up_to_km": 40, "don_gia": 9020}, {"up_to_km": 60, "don_gia": 7920},
        {"up_to_km": 80, "don_gia": 6930}, {"up_to_km": 100, "don_gia": 5940},
        {"up_to_km": 150, "don_gia": 4950}, {"up_to_km": 200, "don_gia": 4200},
        {"up_to_km": None, "don_gia": 3960},
    ]
    _bac_muc(client, h, m5t, bac_5t)

    ds = {m["ten"]: m for m in client.get(GOC, headers=h).json()["items"]}
    assert len(ds["Xe 2 tấn"]["items"]) == 8
    assert len(ds["Xe 5 tấn"]["items"]) == 9

    xe_nho = _tao_xe(client, h, "51H-00002", "Xe hai tấn", 2, m2t)
    xe_lon = _tao_xe(client, h, "51H-00005", "Xe năm tấn", 5, m5t)

    tx = _tai_xe("TX hai muc", phong=PHONG_GH)
    # 180 km: mức 2 tấn hết bậc ở 150 nên rơi bậc "trở lên" = 3.600;
    #          mức 5 tấn còn bậc 150–200 = 4.200.
    t_nho = _chuyen(client, h, suffix="k1", tai_xe=tx, km=180, xe_id=xe_nho)
    t_lon = _chuyen(client, h, suffix="k2", tai_xe=tx, km=180, xe_id=xe_lon)
    assert _da_chup(t_nho) == 3600.0
    assert _da_chup(t_lon) == 4200.0

    with capsys.disabled():
        print("\n  MỨC 1 · Xe 2 tấn  —", len(ds["Xe 2 tấn"]["items"]), "bậc,",
              ds["Xe 2 tấn"]["so_xe"], "xe gán")
        print("  MỨC 2 · Xe 5 tấn  —", len(ds["Xe 5 tấn"]["items"]), "bậc,",
              ds["Xe 5 tấn"]["so_xe"], "xe gán")
        print("  Chuyến 180 km:  xe 2 tấn = 3.600 đ/km   |   xe 5 tấn = 4.200 đ/km")
