"""Hàng 3 đèn tổng quan của bảng Lệnh sản xuất (Đợt 1 redesign 18/08/2026).

Hai lớp kiểm, cố ý tách:

* **Luật đèn** — hàm thuần, không DB. Đây là chỗ dễ trôi nhất: đổi một nhánh `if` là đèn đổi màu
  mà không test nào đỏ, trong khi người điều độ đọc bảng bằng đúng mấy cái chấm đó.
* **Đấu dây thật** — đèn Vật tư phải nói CÙNG MỘT CÂU với cửa chặn `_chan_chua_giu_du`, và route
  `/tong-quan` phải đứng trước `/{lsx_id}`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.lsx import LB_MAY, LB_TO
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.lsx_tong_quan import (
    MUC_DO, MUC_OK, MUC_VANG, _den_may, _den_nguoi, _den_vat_tu, _slack, tong_quan,
)

# Fixtures + helper dùng chung với test xếp lịch (đơn → lệnh → sẵn sàng → giữ chỗ đủ).
from tests.test_xep_lich_service import (  # noqa: F401
    _giu_cho_du,
    _hai_lsx_san_sang,
    _in_step,
    _nha_cho,
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)


# --- Luật đèn (hàm thuần) ----------------------------------------------------
def test_den_vat_tu_soi_dung_thu_tu_cua_cua_chan():
    """Bốn nhánh của `_chan_chua_giu_du`, đúng thứ tự — đèn đỏ phải đoán trúng việc bấm sẽ bị chặn."""
    assert _den_vat_tu({"du": True, "xep_som_nhat": None}, 1)["muc"] == MUC_OK
    ve = _den_vat_tu({"du": True, "xep_som_nhat": datetime(2026, 8, 25)}, 1)
    assert ve["muc"] == MUC_VANG and "25/08" in ve["chu"]      # đủ, nhưng đừng xếp trước ngày hàng về
    assert _den_vat_tu({"du": False, "bat": False}, 1)["muc"] == MUC_DO
    assert "quy đổi" in _den_vat_tu({"du": False, "bat": True, "khong_ro": True}, 1)["chu"]
    thieu = _den_vat_tu({"du": False, "bat": True, "khong_ro": False, "thieu": {("vt", 3): 5.0}}, 1)
    assert thieu["muc"] == MUC_DO and "1 mặt hàng" in thieu["chu"]
    # `du` đòi `bool(can)`: không ra nhu cầu nào thì cửa vẫn chặn, nhưng đừng in "còn thiếu 0".
    assert "0" not in _den_vat_tu({"du": False, "bat": True, "khong_ro": False, "thieu": {}}, 1)["chu"]


def test_den_vat_tu_do_thi_bam_duoc_sang_man_ke_hoach_vat_tu():
    """Chấm đỏ mà không nhảy được đi đâu thì người dùng lại phải tự đi tìm màn — đúng cái đang sửa."""
    den = _den_vat_tu({"du": False, "bat": False}, 42)
    assert den["nhay"] == {"man": "ke-hoach-vat-tu", "id": 42}
    assert _den_vat_tu({"du": True, "xep_som_nhat": None}, 42)["nhay"] is None  # `ok` không vẽ chấm


def test_den_may_gio_chua_co_gio_la_VANG_chu_khong_phai_ok():
    """Dòng vừa sinh KHÔNG có `start_at` (`_dong_moi`). Để nó là `ok` thì đưa 12 lệnh vào kế hoạch
    xong bảng vẫn xanh mướt trong khi chưa việc nào có giờ — đèn nói dối đúng lúc cần nói thật."""
    cho = [{"start_at": None, "loai_buoc": LB_MAY}, {"start_at": datetime(2026, 8, 20),
                                                     "loai_buoc": LB_MAY}]
    den = _den_may(set(), cho, 7)
    assert den["muc"] == MUC_VANG and "1 bước" in den["chu"]
    assert den["nhay"] == {"man": "xep-lich-cong-doan", "id": 7}
    # Chưa vào kế hoạch (không có dòng nào) → im, cột Trạng thái đã nói rồi.
    assert _den_may(set(), [], 7)["muc"] == MUC_OK


def test_den_may_gio_do_thang_vang_va_uu_tien_trung_may():
    da_xep = [{"start_at": datetime(2026, 8, 20), "loai_buoc": LB_MAY}]
    assert _den_may({"trung_may"}, da_xep, 1)["muc"] == MUC_DO
    assert _den_may({"de_khoa_may"}, da_xep, 1)["muc"] == MUC_DO
    assert _den_may({"sai_tien_nhiem"}, da_xep, 1)["muc"] == MUC_DO
    assert _den_may({"thieu_du_lieu"}, da_xep, 1)["muc"] == MUC_DO
    # Đỏ thắng vàng: còn bước chưa có giờ mà cũng đang trùng máy thì phải báo cái chặn được trước.
    assert _den_may({"trung_may"}, [{"start_at": None, "loai_buoc": LB_MAY}], 1)["muc"] == MUC_DO
    # Khổ vượt máy: CẢNH BÁO thôi (chốt 18/08/2026) — thợ còn cách xử lý, máy không quyết thay.
    assert _den_may({"may_khong_kham"}, da_xep, 1)["muc"] == MUC_VANG


def test_den_nguoi_do_khi_qua_tai_vang_khi_buoc_to_chua_co_to():
    assert _den_nguoi({"qua_tai_to"}, [], 1)["muc"] == MUC_DO
    assert _den_nguoi({"thieu_nguoi"}, [], 1)["muc"] == MUC_DO
    chua_to = [{"loai_buoc": LB_TO, "department_id": None},
               {"loai_buoc": LB_MAY, "department_id": None}]   # bước máy không cần tổ
    den = _den_nguoi(set(), chua_to, 1)
    assert den["muc"] == MUC_VANG and "1 bước tổ" in den["chu"]
    assert _den_nguoi(set(), [{"loai_buoc": LB_TO, "department_id": 3}], 1)["muc"] == MUC_OK


# --- Đấu dây thật ------------------------------------------------------------
def test_den_vat_tu_doi_mau_theo_dung_giu_cho_that(db, orders, lsx_svc, admin, customer):
    """Giữ đủ → im; nhả chỗ → đỏ. Và chỉ đúng lệnh bị nhả mới đỏ, lệnh bên cạnh không lây."""
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    res = {r["lsx_id"]: r["den"] for r in tong_quan(db, [a.id, b.id])}
    assert res[a.id]["vat_tu"]["muc"] == MUC_OK and res[b.id]["vat_tu"]["muc"] == MUC_OK

    _nha_cho(db, [a.id])
    res = {r["lsx_id"]: r["den"] for r in tong_quan(db, [a.id, b.id])}
    assert res[a.id]["vat_tu"]["muc"] == MUC_DO
    assert res[b.id]["vat_tu"]["muc"] == MUC_OK


def test_den_may_gio_len_tieng_khi_vao_ke_hoach_va_do_khi_trung_may(
    db, orders, lsx_svc, xl_svc, admin, customer, monkeypatch
):
    monkeypatch.setattr(xl_svc.cal, "is_working_day", lambda d: True)
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for lsx in (a, b):
        s = _in_step(db, lsx.id)
        s.setup_phut, s.nang_suat, s.so_luong_vao, s.chay_phut = 0, 5000, 5000, None
    db.commit()

    # Chưa vào kế hoạch: chưa có gì để nói.
    assert tong_quan(db, [a.id])[0]["den"]["may_gio"]["muc"] == MUC_OK

    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    xl_svc.dua_vao_lsx(lsx_id=b.id, actor=admin)
    # Có dòng mà chưa dòng nào có giờ ⇒ đèn KHÔNG được im (vàng "chưa có giờ", hoặc đỏ nếu bước
    # còn thiếu máy/năng suất). Cái phải chặn ở đây là trạng thái `ok`.
    assert tong_quan(db, [a.id])[0]["den"]["may_gio"]["muc"] != MUC_OK

    repo = XepLichRepository(db)
    bat_dau = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    may_id = _in_step(db, a.id).may_id          # 2 lệnh cùng công đoạn in → cùng máy
    for lsx in (a, b):
        xl_svc.gan(dong_id=repo.by_lsx(lsx.id)[0].id,
                   patch={"may_id": may_id, "start_at": bat_dau}, actor=admin)

    res = {r["lsx_id"]: r["den"] for r in tong_quan(db, [a.id, b.id])}
    assert res[a.id]["may_gio"]["muc"] == MUC_DO
    assert "Trùng giờ" in res[a.id]["may_gio"]["chu"]
    assert res[b.id]["may_gio"]["muc"] == MUC_DO


def test_tong_quan_khong_hoi_thi_khong_tinh(db):
    """Không id nào thì thoát ngay — đừng chạy engine cân đối cho một câu trả lời rỗng."""
    assert tong_quan(db, []) == []
    assert tong_quan(db, [0, None]) == []        # type: ignore[list-item]


# --- Hợp đồng HTTP -----------------------------------------------------------
def _headers(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_route_tong_quan_phai_dung_truoc_lsx_id(client):
    """FastAPI khớp route theo THỨ TỰ khai. `/tong-quan` mà nằm sau `/{lsx_id}` thì bị nuốt thành
    path param và trả 422 — hỏng câm, chỉ lộ khi bấm thật."""
    from app.main import app

    duong = [getattr(r, "path", "") for r in app.routes]
    assert duong.index("/api/lsx/tong-quan") < duong.index("/api/lsx/{lsx_id}")

    r = client.get("/api/lsx/tong-quan", headers=_headers(client))
    assert r.status_code == 200 and r.json() == {"items": []}


def test_tong_quan_bo_id_khong_co_that(client):
    """Id rác không được nhận đèn: `GiuChoService` trả `bat=False` cho lệnh không tồn tại, tức là
    đèn sẽ bịa ra một chấm đỏ 'chưa giữ chỗ vật tư' cho lệnh không hề có."""
    r = client.get("/api/lsx/tong-quan?ids=999999,abc,", headers=_headers(client))
    assert r.status_code == 200 and r.json()["items"] == []


# --- `slack_ngay` cho cột Hạn -------------------------------------------------
def test_slack_lay_buoc_cang_nhat_va_bo_qua_buoc_chua_co_gio():
    """Lệnh trễ ở MỘT bước là lệnh trễ. Lấy `min` chứ không lấy bước cuối, và bước chưa có giờ
    (`slack_ngay=None`) không được kéo cả lệnh về `None`."""
    assert _slack([]) is None
    assert _slack([{"slack_ngay": None}]) is None
    assert _slack([{"slack_ngay": 5}, {"slack_ngay": -1}, {"slack_ngay": None}]) == -1


def test_slack_ngay_di_het_duong_dict_den_schema(db, orders, lsx_svc, admin, customer):
    """Pydantic nuốt field IM LẶNG: có trong dict mà không khai ở schema thì FE nhận `undefined`,
    cột `Hạn` lặng lẽ lùi về đếm ngày lịch — hỏng câm đúng chỗ vừa sửa."""
    from app.schemas.lsx import LsxTongQuanItem

    a, _ = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    item = tong_quan(db, [a.id])[0]
    assert "slack_ngay" in item, "service phải trả field"
    assert "slack_ngay" in LsxTongQuanItem.model_fields, "schema phải khai field"
    ra = LsxTongQuanItem.model_validate({**item, "slack_ngay": -2})
    assert ra.slack_ngay == -2 and ra.model_dump()["slack_ngay"] == -2


def test_moi_loai_den_van_con_bo_do_phat_ra():
    """Đèn gom theo TIỀN TỐ `issue_key` (= từng bộ dò). Xoá/đổi một bộ dò bên
    `xep_lich_van_de_service` mà quên ở đây thì đèn tắt IM LẶNG — không lỗi, chỉ là không khớp cái
    nào nữa. Test này soi thẳng mã nguồn bộ dò.

    Soi tiền tố chứ không soi `category`: 18/08/2026 loại gom còn 6, `may` nay trùm cả bốn thứ
    trùng-giờ · đè-khoá · quá-tải · không-kham-khổ, mà ba cái đầu ĐỎ còn cái cuối VÀNG.
    """
    import pathlib

    from app.services import lsx_tong_quan as tq

    src = pathlib.Path(
        tq.__file__).with_name("xep_lich_van_de_service.py").read_text(encoding="utf-8")
    for pre in tq.CAT_MAY_DO + tq.CAT_NGUOI_DO + tq.CAT_MAY_VANG:
        ten = [k for k, v in vars(tq).items() if k.startswith("K_") and v == pre]
        assert ten, f"tiền tố {pre!r} phải NHẬP từ hằng K_* của bộ dò, không gõ lại chuỗi"
        assert any(
            f'"issue_key": f"{{{n}}}' in src for n in ten
        ), f"tiền tố {pre!r} không còn bộ dò nào phát ra"
