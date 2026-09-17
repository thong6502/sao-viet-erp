"""Siết chặt khoán km giao hàng — nghiệm thu `docs/prd-khoan-km-giao-hang.md` §12 (14/09/2026).

Chủ hỏi: *"nếu có một xe ăn Mức khoán km mà mình tắt phòng ban giao hàng, hoặc mình xoá mức đó đi
nhưng trong khi đó vẫn có xe dùng tới thì sao"*. Đo thực nghiệm: xoá mức đã chặn; còn TẮT CỜ giữa
lúc chuyến đang giao thì đóng chuyến vẫn 200 với `don_gia_km = NULL` — tài xế mất trắng tiền chuyến
đó, không lỗi, không cảnh báo. Soát thêm ra ba lỗ cùng gốc. Bốn quyết định chủ chốt:

1. Mức khoán km là cấu hình CHUNG — bảng bậc không còn dính phòng ban.
2. Tắt cờ Giao hàng khi tài xế của phòng còn chuyến chưa ghi kết quả ⇒ CHẶN cứng.
3. Khối Giao hàng = cờ RIÊNG của từng phòng, KHÔNG kế thừa theo cây — *"nếu mà phòng con thì nó
   cũng phải bật cái phòng đó là giao hàng lên thôi"*.
4. Xe BẮT BUỘC có mức (kèm: lên đơn bằng xe có mức chưa khai bậc cũng chặn).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.delivery import LG_DANG_TRA_HANG, DeliveryTrip
from app.models.xe import MucKhoanKmBac, Xe
from app.repositories.rbac_repo import DepartmentRepository
from tests.test_giao_hang_api import _admin, _di_toi_dang_giao, _don_da_chot, _tai_xe, _tao_yc
from tests.test_khoan_km_giao_hang import PHONG_GH, _bat_khoi_giao_hang
from tests.test_khoan_km_theo_muc import (
    GOC, THANG_THUONG, _bac_muc, _chuyen, _da_chup, _len_kh_kem_xe, _muc_co_gia, _tao_muc,
    _tao_xe,
)


# --- dựng cảnh -------------------------------------------------------------------------------
def _sua_phong(client, h, dept_id: int, **o):
    """PUT đúng endpoint màn Phòng ban dùng. `o` = các ô gửi kèm (không gửi = giữ nguyên)."""
    return client.put(f"/api/departments/{dept_id}", json={"name": PHONG_GH, **o}, headers=h)


def _co_giao_hang(dept_id: int) -> bool:
    db = SessionLocal()
    try:
        return bool(DepartmentRepository(db).get_by_id(dept_id).la_giao_hang)
    finally:
        db.close()


def _chuyen_dang_giao(client, h, *, suffix, tai_xe, xe_id) -> int:
    """Đơn → yêu cầu → kế hoạch (kèm xe) → đang giao. CHƯA ghi kết quả."""
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh_kem_xe(client, h, yc["id"], tai_xe, xe_id)
    assert r.status_code == 201, r.text
    trip = r.json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    return trip


def _chuyen_moi_len_ke_hoach(client, h, *, suffix, tai_xe, xe_id) -> int:
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh_kem_xe(client, h, yc["id"], tai_xe, xe_id)
    assert r.status_code == 201, r.text
    return r.json()["trip"]["id"]


def _to_con(ten: str, *, bat_co: bool) -> int:
    """Một tổ CON nằm dưới phòng Giao hàng, tự bật hoặc không bật cờ của chính nó."""
    db = SessionLocal()
    try:
        repo = DepartmentRepository(db)
        con = repo.create(name=ten, parent_id=repo.get_by_name(PHONG_GH).id)
        con.la_giao_hang = bat_co
        db.commit()
        return con.id
    finally:
        db.close()


def _o_chon_tai_xe(client, h) -> set[int]:
    r = client.get("/api/giao-hang/tai-xe-chon", headers=h)
    assert r.status_code == 200, r.text
    return {x["id"] for x in r.json()["items"]}


# =============================================================================================
# Quyết định 2 — tắt cờ Giao hàng khi còn chuyến đang chạy
# =============================================================================================
def test_TAT_CO_giao_hang_khi_con_chuyen_dang_chay_bi_chan_va_noi_dung_so_chuyen(client):
    """⭐ Đúng cảnh chủ hỏi. Hai chuyến ở hai trạng thái khác nhau — cả hai đều chưa chụp giá."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    xe = _tao_xe(client, h, "51S-00001", "Xe siết", 3.5, _muc_co_gia(client, h))
    # Hai TÀI XẾ: một người không được xếp hai chuyến trùng giờ (luật lịch kíp xe).
    tx = _tai_xe("TX tat co", phong=PHONG_GH)
    tx2 = _tai_xe("TX tat co hai", phong=PHONG_GH)
    dang_giao = _chuyen_dang_giao(client, h, suffix="tc1", tai_xe=tx, xe_id=xe)
    _chuyen_moi_len_ke_hoach(client, h, suffix="tc2", tai_xe=tx2, xe_id=xe)

    r = _sua_phong(client, h, pb, la_giao_hang=False)
    assert r.status_code == 400, r.text
    assert "Còn 2 chuyến" in r.json()["detail"], r.text
    assert _co_giao_hang(pb) is True, "báo chặn mà cờ vẫn bị tắt"

    # Sửa phòng mà KHÔNG đụng cờ (đổi tên, trưởng phòng…) thì không được chặn oan.
    assert _sua_phong(client, h, pb).status_code == 200

    # Chuyến đang giao đóng xong thì CÓ TIỀN — đây là thứ luật chặn bảo vệ.
    r = client.post(f"/api/giao-hang/trips/{dang_giao}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": 113, "nguoi_nhan_thuc_te": "Chi Lan"}, headers=h)
    assert r.status_code == 200, r.text
    assert _da_chup(dang_giao) == 4500.0

    r = _sua_phong(client, h, pb, la_giao_hang=False)
    assert r.status_code == 400 and "Còn 1 chuyến" in r.json()["detail"], r.text


def test_TAT_CO_khi_chi_con_chuyen_DA_DONG_hoac_DANG_TRA_HANG_thi_cho_tat(client):
    """Không chặn oan. `dang_tra_hang` là chuyến đã GHI KẾT QUẢ (giao thất bại, trả hàng về) —
    đơn giá đã chụp từ lúc ghi, tắt cờ lúc này không làm mất gì."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    xe = _tao_xe(client, h, "51S-00002", "Xe trả hàng", 3.5, _muc_co_gia(client, h))
    tx = _tai_xe("TX tra hang", phong=PHONG_GH)
    _chuyen(client, h, suffix="tc3", tai_xe=tx, km=50, xe_id=xe)          # đã đóng
    trip = _chuyen_dang_giao(client, h, suffix="tc4", tai_xe=tx, xe_id=xe)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "that_bai", "km": 20, "ly_do_that_bai": "Khách đi vắng",
        "huong_xu_ly": "tra_ve"}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.get(DeliveryTrip, trip).trang_thai == LG_DANG_TRA_HANG
    finally:
        db.close()

    r = _sua_phong(client, h, pb, la_giao_hang=False)
    assert r.status_code == 200, r.text
    assert _co_giao_hang(pb) is False


# =============================================================================================
# Quyết định 3 — một định nghĩa khối Giao hàng: cờ RIÊNG, không kế thừa
# =============================================================================================
def test_TO_CON_khong_tu_bat_co_thi_tai_xe_KHONG_hien_o_o_chon(client):
    """Trước 14/09 ô chọn đi kế thừa theo cây còn tính tiền đọc cờ riêng: tài xế tổ con được phân
    chuyến bình thường mà không có tiền khoán km, không ai báo."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    _to_con("Tổ xe con chưa bật", bat_co=False)
    tx_cha = _tai_xe("TX phong cha", phong=PHONG_GH)
    tx_con = _tai_xe("TX to con chua bat", phong="Tổ xe con chưa bật")

    ds = _o_chon_tai_xe(client, h)
    assert tx_cha in ds
    assert tx_con not in ds, "tổ con chưa tự bật cờ mà vẫn chọn được ⇒ chạy chuyến không có tiền"


def test_TO_CON_tu_bat_co_thi_HIEN_o_o_chon_VA_co_tien(client):
    """Hai vế phải cùng một câu trả lời — chọn được thì phải ra tiền."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    _to_con("Tổ xe con đã bật", bat_co=True)
    xe = _tao_xe(client, h, "51S-00003", "Xe tổ con", 3.5, _muc_co_gia(client, h))
    tx = _tai_xe("TX to con da bat", phong="Tổ xe con đã bật")

    assert tx in _o_chon_tai_xe(client, h)
    t = _chuyen(client, h, suffix="tcon", tai_xe=tx, km=113, xe_id=xe)
    assert _da_chup(t) == 4500.0


# =============================================================================================
# Quyết định 4 — xe bắt buộc có mức, và mức phải có giá
# =============================================================================================
def test_TAO_XE_thieu_muc_bi_chan(client):
    h = _admin(client)
    r = client.post("/api/xe", json={"ma": "51S-00010", "ten": "Xe thiếu mức"}, headers=h)
    # 422: nền danh mục dùng chung ánh xạ lỗi validate sang 422 (`catalog_base`).
    assert r.status_code == 422, r.text
    assert "Phải chọn mức khoán km" in r.text


def test_SUA_XE_go_muc_bi_chan_nhung_khong_gui_o_muc_thi_giu_nguyen(client):
    h = _admin(client)
    muc = _muc_co_gia(client, h)
    xe = _tao_xe(client, h, "51S-00011", "Xe gỡ mức", 3.5, muc)

    r = client.put(f"/api/xe/{xe}", json={"ma": "51S-00011", "ten": "Xe gỡ mức",
                                          "muc_khoan_km_id": None}, headers=h)
    assert r.status_code == 422, r.text

    r = client.put(f"/api/xe/{xe}", json={"ma": "51S-00011", "ten": "Xe đổi tên"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["muc_khoan_km_id"] == muc


def test_LEN_DON_bang_xe_co_muc_CHUA_KHAI_BAC_bi_chan(client):
    """Không chặn thì mức rỗng lại âm thầm ăn đơn giá phẳng (4.330) y như xe không mức."""
    _bat_khoi_giao_hang(don_gia=4330)
    h = _admin(client)
    muc = _tao_muc(client, h, "Xe 5 tấn")                     # chưa khai bậc
    xe = _tao_xe(client, h, "51S-00020", "Xe mức rỗng", 5, muc)
    tx = _tai_xe("TX muc rong", phong=PHONG_GH)

    oid, lid = _don_da_chot(suffix="mr1")
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh_kem_xe(client, h, yc["id"], tx, xe)
    assert r.status_code == 400, r.text
    assert "Mức “Xe 5 tấn”" in r.json()["detail"], r.text
    assert "chưa có bảng giá" in r.json()["detail"], r.text

    # Khai bậc xong thì lên đơn được — và ra giá của MỨC, không phải 4.330 phẳng.
    _bac_muc(client, h, muc, THANG_THUONG)
    assert _da_chup(_chuyen(client, h, suffix="mr2", tai_xe=tx, km=113, xe_id=xe)) == 4500.0


def test_xe_DOI_CU_chua_gan_muc_thi_LEN_DON_bi_chan(client):
    """Xe khai trước 14/09 có thể còn NULL mức — cột nullable, luật nằm ở service."""
    _bat_khoi_giao_hang(don_gia=4330)
    h = _admin(client)
    db = SessionLocal()
    try:
        x = Xe(ma="51S-00030", ten="Xe đời cũ", muc_khoan_km_id=None)
        db.add(x)
        db.commit()
        xe = x.id
    finally:
        db.close()
    tx = _tai_xe("TX xe doi cu", phong=PHONG_GH)

    oid, lid = _don_da_chot(suffix="xc1")
    yc = _tao_yc(client, h, oid, lid)
    r = _len_kh_kem_xe(client, h, yc["id"], tx, xe)
    assert r.status_code == 400, r.text
    assert "chưa gán mức" in r.json()["detail"], r.text


def test_KHONG_de_trong_bang_gia_cua_muc_CON_XE_dang_an(client):
    """Xoá trắng giá của mức đang dùng = âm thầm khoá lên đơn của mọi xe đó."""
    h = _admin(client)
    muc = _muc_co_gia(client, h, "Mức đang dùng")
    _tao_xe(client, h, "51S-00040", "Xe giữ giá", 3.5, muc)

    r = _bac_muc(client, h, muc, [], cho=400)
    assert "Còn 1 xe" in r.json()["detail"], r.text
    ds = {m["id"]: m for m in client.get(GOC, headers=h).json()["items"]}
    assert len(ds[muc]["items"]) == 8, "báo chặn mà bảng giá vẫn mất"

    # Mức chưa xe nào dùng thì xoá trắng được.
    _bac_muc(client, h, _muc_co_gia(client, h, "Mức chưa ai dùng"), [], cho=200)


# =============================================================================================
# Quyết định 1 — mức là cấu hình chung
# =============================================================================================
def test_XOA_PHONG_BAN_khong_cuon_bang_gia_cua_muc(client):
    """Trước 14/09 mỗi dòng bậc mang `department_id` với FK xoá dây chuyền: xoá phòng là mức còn
    tên mà hết giá."""
    h = _admin(client)
    db = SessionLocal()
    try:
        tam = DepartmentRepository(db).create(name="Phòng tạm từng lưu giá")
        db.commit()
        tam_id = tam.id
    finally:
        db.close()
    muc = _muc_co_gia(client, h, "Mức sống lâu hơn phòng")

    r = client.delete(f"/api/departments/{tam_id}", headers=h)
    assert r.status_code == 204, r.text
    ds = {m["id"]: m for m in client.get(GOC, headers=h).json()["items"]}
    assert len(ds[muc]["items"]) == 8
    assert "department_id" not in MucKhoanKmBac.__table__.c, "bậc lại dính vào phòng ban"


def test_duong_ghi_bac_cu_theo_phong_da_go(client):
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    muc = _tao_muc(client, h, "Mức đường cũ")
    r = client.put(f"/api/giao-hang/departments/{pb}/muc-khoan-km/{muc}/km-brackets",
                   json={"items": THANG_THUONG}, headers=h)
    assert r.status_code in (404, 405), r.text


# =============================================================================================
# Lỗi d — đổi tên mức làm mất ghi chú, tự bật lại mức đang tắt
# =============================================================================================
def test_DOI_TEN_muc_giu_nguyen_ghi_chu_va_trang_thai(client):
    h = _admin(client)
    r = client.post(GOC, json={"ten": "Mức có ghi chú", "ghi_chu": "Thang xe 5 tấn"}, headers=h)
    assert r.status_code == 201, r.text
    muc = next(m for m in r.json()["items"] if m["ten"] == "Mức có ghi chú")["id"]
    assert client.put(f"{GOC}/{muc}", json={"active": False}, headers=h).status_code == 200

    r = client.put(f"{GOC}/{muc}", json={"ten": "Mức đổi tên"}, headers=h)   # đúng thứ màn gửi
    assert r.status_code == 200, r.text
    m = next(x for x in r.json()["items"] if x["id"] == muc)
    assert m["ten"] == "Mức đổi tên"
    assert m["ghi_chu"] == "Thang xe 5 tấn", "đổi tên mà mất ghi chú"
    assert m["active"] is False, "đổi tên mà mức đang tắt tự bật lại"
