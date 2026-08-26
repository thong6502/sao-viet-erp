"""SAO NHÀ CUNG CẤP — máy tự tính từ phiếu mua hàng (không ai chấm tay).

Luật đầy đủ: `app/services/danh_gia_ncc.py`. Bộ test này canh ba thứ dễ vỡ nhất:

1. **`None` KHÁC `0`.** NCC chưa có đơn nào đủ điều kiện phải ra "Chưa đánh giá" (`rating=None`).
   Trả 0 là nói NCC đó TỆ NHẤT — vu oan cho nhà cung cấp vừa khai hồ sơ hôm qua.
2. **Hai đường tính không được lệch.** Thang sao có bản Python (`sao_tu_so_ngay_tre`) và bản SQL
   (CASE trong `SupplierRepository._bang_danh_gia`). Cả hai đọc chung `NGUONG_SAO_NCC`, nhưng
   dịch sang SQL vẫn có thể sai — nhất là phép TRỪ NGÀY, thứ mà SQLite và Postgres làm khác nhau.
3. **Mốc hẹn là `needed_date`, KHÔNG fallback.** Chốt 26/08/2026. Đơn thiếu `needed_date` bị BỎ
   khỏi trung bình, không phải cho 5 sao.

Dữ liệu dựng THẲNG vào DB thay vì đi qua luồng lập → duyệt → mua → giao: tính năng này CHỈ ĐỌC,
mà mỗi ca test cần một cặp ngày rất cụ thể (trễ đúng 3 ngày, đúng 8 ngày…). Bắt nó chui qua 5 cú
POST thì cái vỡ khi test đỏ sẽ là luồng duyệt, không phải công thức sao.
"""
from __future__ import annotations

from datetime import date, timedelta
from itertools import count

from app.db import SessionLocal
from app.models.purchase import (
    PR_PARTIALLY_RECEIVED,
    PR_PURCHASED,
    PR_RECEIVED,
    PurchaseDelivery,
    PurchaseRequest,
    Supplier,
)
from app.repositories.purchase_repo import SupplierRepository
from app.services.danh_gia_ncc import sao_tu_so_ngay_tre, tu_tong_hop

ADMIN = {"username": "admin", "password": "admin123"}

_dem = count(1)
HOM_NAY = date.today()


def _h(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ncc(db, ten: str) -> Supplier:
    """NCC trắng tinh — chưa một phiếu mua nào."""
    n = next(_dem)
    row = Supplier(
        name=ten,
        tax_code=f"09{n:08d}",
        phone="0900000000",
        email=f"ncc{n}@x.vn",
        address="HN",
        contact_name="A",
        supplier_group="giay",
        status="active",
    )
    db.add(row)
    db.flush()
    return row


def _don(
    db,
    ncc: Supplier,
    *,
    can_hang: date | None,
    giao: date | None = None,
    trang_thai: str = PR_RECEIVED,
) -> PurchaseRequest:
    """Một phiếu mua + (tuỳ chọn) MỘT đợt giao.

    `can_hang` = `needed_date` = MỐC HẸN. `giao` = ngày của đợt giao duy nhất.
    """
    n = next(_dem)
    pr = PurchaseRequest(
        code=f"PMH-TEST-{n:05d}",
        status=trang_thai,
        supplier_id=ncc.id,
        needed_date=can_hang,
    )
    db.add(pr)
    db.flush()
    if giao is not None:
        db.add(PurchaseDelivery(purchase_request_id=pr.id, seq_no=1, delivery_date=giao))
        db.flush()
    return pr


def _sao(db, ncc: Supplier):
    """Sổ điểm của một NCC, đi qua ĐÚNG đường mà API đi (truy vấn con gộp theo supplier_id)."""
    return tu_tong_hop(SupplierRepository(db).danh_gia_mot(ncc.id))


# --- thang sao: bản Python ---------------------------------------------------------------

def test_thang_sao_python_dung_tung_nac():
    """≤0 → 5 · 1–3 → 4 · 4–7 → 3 · 8–14 → 2 · >14 → 1. Không có nấc 0 sao."""
    assert sao_tu_so_ngay_tre(-30) == 5
    assert sao_tu_so_ngay_tre(0) == 5
    assert sao_tu_so_ngay_tre(1) == 4
    assert sao_tu_so_ngay_tre(3) == 4
    assert sao_tu_so_ngay_tre(4) == 3
    assert sao_tu_so_ngay_tre(7) == 3
    assert sao_tu_so_ngay_tre(8) == 2
    assert sao_tu_so_ngay_tre(14) == 2
    assert sao_tu_so_ngay_tre(15) == 1
    assert sao_tu_so_ngay_tre(999) == 1
    assert min(sao_tu_so_ngay_tre(n) for n in range(-5, 400)) == 1, "thấp nhất là 1 SAO, không phải 0"


# --- thang sao: bản SQL phải khớp bản Python ----------------------------------------------

def test_giao_dung_hen_va_giao_som_deu_5_sao(client):
    db = SessionLocal()
    try:
        dung_hen = _ncc(db, "NCC dung hen")
        _don(db, dung_hen, can_hang=HOM_NAY - timedelta(days=20),
             giao=HOM_NAY - timedelta(days=20))
        som = _ncc(db, "NCC giao som")
        _don(db, som, can_hang=HOM_NAY - timedelta(days=20), giao=HOM_NAY - timedelta(days=27))
        db.commit()

        assert _sao(db, dung_hen).rating == 5.0
        assert _sao(db, som).rating == 5.0
        assert _sao(db, som).on_time_count == 1
        assert _sao(db, som).late_count == 0
        assert _sao(db, som).avg_late_days is None, "chưa trễ đơn nào thì đừng bịa ra số ngày trễ"
    finally:
        db.close()


def test_sql_va_python_ra_cung_mot_so_o_moi_nac(client):
    """Quét TỪNG nấc: 0,1,3,4,7,8,14,15,40 ngày trễ — SQL phải nói y hệt `sao_tu_so_ngay_tre`.

    Đây là ca canh phép TRỪ NGÀY: Postgres cho `date - date` ra số nguyên, SQLite lưu DATE thành
    chuỗi nên phải đi qua `julianday()`. Rẽ nhánh sai thì KHÔNG có lỗi nào bắn ra, chỉ là mọi đơn
    bỗng thành "đúng hẹn" — đúng kiểu bug im lặng.
    """
    db = SessionLocal()
    try:
        for tre in (0, 1, 3, 4, 7, 8, 14, 15, 40):
            ncc = _ncc(db, f"NCC tre {tre} ngay")
            moc = HOM_NAY - timedelta(days=60)
            _don(db, ncc, can_hang=moc, giao=moc + timedelta(days=tre))
            db.commit()
            mong_doi = float(sao_tu_so_ngay_tre(tre))
            thuc_te = _sao(db, ncc)
            assert thuc_te.rating == mong_doi, f"trễ {tre} ngày: SQL ra {thuc_te.rating}, Python ra {mong_doi}"
            assert thuc_te.rating_count == 1
            if tre > 0:
                assert thuc_te.late_count == 1
                assert thuc_te.avg_late_days == float(tre)
            else:
                assert thuc_te.on_time_count == 1
    finally:
        db.close()


# --- đơn chưa giao đủ: đồng hồ vẫn chạy ----------------------------------------------------

def test_dang_tre_chua_giao_du_van_bi_tru_sao(client):
    """NCC ôm hàng không giao KHÔNG được sạch sổ — trễ tính tới HÔM NAY.

    Hai đơn: một đơn `purchased` chưa giao gì, một đơn `partially_received` mới giao được một đợt.
    Cả hai đều quá hẹn 10 ngày ⇒ 2 sao, chứ không phải "chưa có ngày giao nên chưa chấm".
    """
    db = SessionLocal()
    try:
        chua_giao = _ncc(db, "NCC om hang")
        _don(db, chua_giao, can_hang=HOM_NAY - timedelta(days=10), giao=None,
             trang_thai=PR_PURCHASED)
        giao_do = _ncc(db, "NCC giao do dang")
        _don(db, giao_do, can_hang=HOM_NAY - timedelta(days=10),
             giao=HOM_NAY - timedelta(days=12), trang_thai=PR_PARTIALLY_RECEIVED)
        db.commit()

        assert _sao(db, chua_giao).rating == 2.0, "quá hẹn 10 ngày mà chưa giao gì ⇒ 2 sao"
        assert _sao(db, chua_giao).late_count == 1
        # Đã giao một đợt SỚM nhưng đơn CHƯA đủ ⇒ vẫn chốt tới hôm nay, không được ăn 5 sao nhờ
        # đợt giao lẻ.
        assert _sao(db, giao_do).rating == 2.0
    finally:
        db.close()


def test_chua_giao_du_nhung_CHUA_qua_han_thi_chua_cham(client):
    """Đơn còn trong hạn thì chưa có gì để chấm — bỏ ra, không phải cho 5 sao sẵn."""
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC don con trong han")
        _don(db, ncc, can_hang=HOM_NAY + timedelta(days=7), giao=None, trang_thai=PR_PURCHASED)
        db.commit()

        dg = _sao(db, ncc)
        assert dg.rating is None
        assert dg.rating_count == 0
    finally:
        db.close()


# --- ⭐ ca quan trọng nhất: chưa có dữ liệu ≠ 0 sao ----------------------------------------

def test_ncc_chua_co_don_nao_tra_None_KHONG_phai_0(client):
    """NCC vừa khai hồ sơ ⇒ "Chưa đánh giá" (`None`). 0 nghĩa là TỆ NHẤT — đừng vu oan.

    Ca này bảo vệ đúng cái ranh giới mà màn Công nợ đã phải học một lần ("im lặng ≠ 0đ").
    """
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC moi tinh")
        db.commit()

        dg = _sao(db, ncc)
        assert dg.rating is None, "PHẢI là None"
        assert dg.rating != 0, "0 sao = TỆ NHẤT; chưa có dữ liệu thì phải là None"
        assert dg.rating_count == 0
        assert dg.on_time_count == 0
        assert dg.late_count == 0
        assert dg.avg_late_days is None
    finally:
        db.close()


def test_ncc_chi_co_don_khong_du_dieu_kien_van_la_chua_danh_gia(client):
    """Đơn nháp / chờ duyệt / đã duyệt-chưa-mua KHÔNG vào sổ điểm ⇒ vẫn "Chưa đánh giá".

    Trước khi mình bấm "đã mua", NCC còn chưa nhận đơn — chậm ở khâu duyệt là lỗi nội bộ.
    """
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC chi co don nhap")
        for tt in ("draft", "pending_approval", "approved", "rejected", "cancelled"):
            _don(db, ncc, can_hang=HOM_NAY - timedelta(days=30),
                 giao=HOM_NAY - timedelta(days=1), trang_thai=tt)
        db.commit()

        assert _sao(db, ncc).rating is None
        assert _sao(db, ncc).rating_count == 0
    finally:
        db.close()


# --- mốc hẹn: CHỈ `needed_date`, không fallback --------------------------------------------

def test_don_thieu_needed_date_bi_BO_khoi_trung_binh(client):
    """Chốt 26/08/2026: mốc hẹn CHỈ là `needed_date`, bỏ hẳn `expected_receipt_date`.

    Đơn không có `needed_date` thì không có gì để so ⇒ BỎ. Không cho 5 sao (thưởng oan), không
    cho 1 sao (phạt oan). Ở đây đơn thiếu mốc còn được gắn `expected_receipt_date` hẳn hoi — nếu
    ai đó lén thêm fallback lại thì trung bình sẽ tụt và ca này đỏ.
    """
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC co don thieu moc")
        # Đơn tính được: trễ 2 ngày ⇒ 4 sao.
        moc = HOM_NAY - timedelta(days=30)
        _don(db, ncc, can_hang=moc, giao=moc + timedelta(days=2))
        # Đơn THIẾU `needed_date` nhưng CÓ `expected_receipt_date` trễ tận 20 ngày (1 sao).
        pr = _don(db, ncc, can_hang=None, giao=moc + timedelta(days=20))
        pr.expected_receipt_date = moc
        db.commit()

        dg = _sao(db, ncc)
        assert dg.rating_count == 1, "chỉ MỘT đơn đủ điều kiện"
        assert dg.rating == 4.0, "nếu tụt xuống 2.5 nghĩa là fallback expected_receipt_date đã quay lại"
    finally:
        db.close()


# --- trung bình nhiều đơn -------------------------------------------------------------------

def test_trung_binh_nhieu_don_ra_dung_so(client):
    """Trung bình lấy trên SAO TỪNG ĐƠN, không phải sao của số ngày trễ trung bình.

    Khác nhau thật: đơn 0 ngày (5 sao) + đơn 20 ngày (1 sao) ⇒ trung bình sao = 3,0; còn nếu lấy
    trung bình ngày trễ (10 ngày) rồi mới quy sao thì ra 2. Bucket phải làm TRƯỚC khi cộng.
    """
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC nhieu don")
        moc = HOM_NAY - timedelta(days=90)
        for tre in (0, 20):
            _don(db, ncc, can_hang=moc, giao=moc + timedelta(days=tre))
        db.commit()

        dg = _sao(db, ncc)
        assert dg.rating_count == 2
        assert dg.rating == 3.0
        assert dg.on_time_count == 1
        assert dg.late_count == 1
        assert dg.avg_late_days == 20.0

        # Thêm đơn trễ 1 ngày (4 sao) ⇒ (5 + 1 + 4)/3 = 3,333… làm tròn 1 chữ số = 3,3.
        _don(db, ncc, can_hang=moc, giao=moc + timedelta(days=1))
        db.commit()
        dg = _sao(db, ncc)
        assert dg.rating_count == 3
        assert dg.rating == 3.3
        # Trễ TB tính TRÊN CÁC ĐƠN TRỄ: (20 + 1)/2 = 10,5 — không chia cho cả đơn đúng hẹn.
        assert dg.avg_late_days == 10.5
    finally:
        db.close()


def test_nhieu_dot_giao_lay_dot_CUOI_va_khong_nhan_dong(client):
    """Đơn giao 3 đợt: chấm theo đợt CUỐI, và vẫn chỉ đếm là MỘT đơn."""
    db = SessionLocal()
    try:
        ncc = _ncc(db, "NCC giao nhieu dot")
        moc = HOM_NAY - timedelta(days=40)
        pr = _don(db, ncc, can_hang=moc, giao=moc - timedelta(days=3))
        for i, lech in enumerate((1, 5), start=2):
            db.add(PurchaseDelivery(
                purchase_request_id=pr.id, seq_no=i, delivery_date=moc + timedelta(days=lech)
            ))
        db.commit()

        dg = _sao(db, ncc)
        assert dg.rating_count == 1, "3 đợt giao vẫn là 1 đơn — đừng để join nhân dòng"
        assert dg.rating == 3.0, "đợt cuối trễ 5 ngày ⇒ 3 sao"
    finally:
        db.close()


# --- API: danh sách · sắp xếp · lọc ---------------------------------------------------------

def test_api_danh_sach_ncc_phoi_sao_va_ra_so_dung(client):
    db = SessionLocal()
    try:
        tot = _ncc(db, "AAA NCC tot")
        _don(db, tot, can_hang=HOM_NAY - timedelta(days=30), giao=HOM_NAY - timedelta(days=31))
        te = _ncc(db, "BBB NCC te")
        _don(db, te, can_hang=HOM_NAY - timedelta(days=60), giao=HOM_NAY - timedelta(days=20))
        moi = _ncc(db, "CCC NCC moi")
        db.commit()
        id_tot, id_te, id_moi = tot.id, te.id, moi.id
    finally:
        db.close()

    r = client.get("/api/suppliers?size=200", headers=_h(client))
    assert r.status_code == 200, r.text
    theo_id = {row["id"]: row for row in r.json()["items"]}

    assert theo_id[id_tot]["rating"] == 5.0
    assert theo_id[id_tot]["rating_count"] == 1
    assert theo_id[id_tot]["on_time_count"] == 1

    assert theo_id[id_te]["rating"] == 1.0, "trễ 40 ngày ⇒ 1 sao (thấp nhất), không phải 0"
    assert theo_id[id_te]["late_count"] == 1
    assert theo_id[id_te]["avg_late_days"] == 40.0

    assert theo_id[id_moi]["rating"] is None, "Chưa đánh giá — API phải trả null, KHÔNG phải 0"
    assert theo_id[id_moi]["rating_count"] == 0


def test_api_sap_xep_theo_sao_chua_danh_gia_luon_xuong_cuoi(client):
    db = SessionLocal()
    try:
        cao = _ncc(db, "ZZZ NCC 5 sao")
        _don(db, cao, can_hang=HOM_NAY - timedelta(days=30), giao=HOM_NAY - timedelta(days=31))
        thap = _ncc(db, "YYY NCC 1 sao")
        _don(db, thap, can_hang=HOM_NAY - timedelta(days=60), giao=HOM_NAY - timedelta(days=20))
        trang = _ncc(db, "XXX NCC chua danh gia")
        db.commit()
        id_cao, id_thap, id_trang = cao.id, thap.id, trang.id
    finally:
        db.close()

    h = _h(client)

    giam = [r["id"] for r in client.get("/api/suppliers?sort=-rating&size=200", headers=h).json()["items"]]
    assert giam.index(id_cao) < giam.index(id_thap)
    assert giam.index(id_thap) < giam.index(id_trang), "chưa đánh giá phải nằm CUỐI"

    tang = [r["id"] for r in client.get("/api/suppliers?sort=rating&size=200", headers=h).json()["items"]]
    assert tang.index(id_thap) < tang.index(id_cao)
    # Ở CHIỀU TĂNG cũng vẫn cuối: "chưa có dữ liệu" không phải là "tệ nhất".
    assert tang.index(id_cao) < tang.index(id_trang)


def test_api_loc_theo_sao_toi_thieu(client):
    db = SessionLocal()
    try:
        cao = _ncc(db, "NCC loc 5 sao")
        _don(db, cao, can_hang=HOM_NAY - timedelta(days=30), giao=HOM_NAY - timedelta(days=31))
        thap = _ncc(db, "NCC loc 1 sao")
        _don(db, thap, can_hang=HOM_NAY - timedelta(days=60), giao=HOM_NAY - timedelta(days=20))
        trang = _ncc(db, "NCC loc chua danh gia")
        db.commit()
        id_cao, id_thap, id_trang = cao.id, thap.id, trang.id
    finally:
        db.close()

    body = client.get("/api/suppliers?rating_min=4&size=200", headers=_h(client)).json()
    ids = {r["id"] for r in body["items"]}
    assert id_cao in ids
    assert id_thap not in ids
    assert id_trang not in ids, "lọc '≥4 sao' hỏi ai ĐÃ chứng minh được, không kèm NCC chưa có dữ liệu"
    # `total` phải đếm theo ĐÚNG bộ lọc, không phải tổng toàn bảng — nếu không, chân trang bịa ra
    # những trang rỗng.
    assert body["total"] == len(body["items"])


def test_api_tao_ncc_moi_tra_ve_chua_danh_gia(client):
    """Cửa POST cũng phải nói `null`, không được để mặc định rơi về 0."""
    r = client.post("/api/suppliers", headers=_h(client), json={
        "name": "NCC vua khai hom nay",
        "tax_code": "0977777777",
        "phone": "0900000001",
        "email": "vuakhai@x.vn",
        "address": "HN",
        "contact_name": "B",
        "supplier_group": "giay",
        "items": [],
    })
    assert r.status_code == 201, r.text
    assert r.json()["rating"] is None
    assert r.json()["rating_count"] == 0
