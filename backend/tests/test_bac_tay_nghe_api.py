"""Danh mục bậc tay nghề — API + luật ghi (chủ 29/07/2026).

Hai thứ dễ vỡ nhất và đều được canh ở đây:
  1. **Thứ tự route.** `/api/employees/{employee_id}` khai trước sẽ nuốt `/api/employees/bac-tay-nghe`
     và cố parse "bac-tay-nghe" thành int ⇒ 422. Lỗi này chỉ lộ khi gọi thật.
  2. **Bậc chỉ đổi qua TRANSITION.** Sửa hồ sơ thường KHÔNG được đụng bậc — nếu lọt thì đổi bậc
     không còn để lại dấu trong Quá trình công tác.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.payroll_repo import PayrollRepository
from app.services.payroll_service import PayrollService
from tests.test_luong_api import _admin_token, _h, _make_emp, _sal


def _grades(client, token, **params):
    r = client.get("/api/employees/bac-tay-nghe", params=params, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_route_danh_muc_khong_bi_route_id_nuot(client):
    """⭐ Gọi thật đường dẫn chữ. 422 ở đây = FastAPI đang khớp `/{employee_id}` trước."""
    token = _admin_token(client)
    r = client.get("/api/employees/bac-tay-nghe", headers=_h(token))
    assert r.status_code == 200, f"route bị nuốt: {r.status_code} {r.text}"


def test_seed_5_bac_dung_thu_tu_va_khong_co_truong_tien(client):
    """⭐ Chủ chốt 5 BẬC CHÍNH tên dân dã (Thợ lành nghề…Lính mới), và "khai bậc thôi, không tiền"."""
    token = _admin_token(client)
    items = _grades(client, token)

    assert [g["name"] for g in items] == [
        "Thợ lành nghề", "Thợ vững", "Thợ thường", "Tập việc", "Lính mới"]
    assert [g["code"] for g in items] == ["bac_1", "bac_2", "bac_3", "bac_4", "bac_5"]
    # `output_coefficient` là hệ số SẢN LƯỢNG được thêm CÓ CHỦ Ý (spec-thuc-hien-san-xuat §8) — không
    # phải tiền, và gán bậc vẫn KHÔNG đổi lương cho tới khi có mẻ khoán. Luật "khai bậc thôi, KHÔNG
    # TIỀN" vẫn còn: API tuyệt đối không được phơi trường tiền (đơn giá/mức lương/…).
    assert set(items[0]) == {"id", "code", "name", "seq", "is_active", "note", "output_coefficient"}, \
        "API bậc chỉ được thêm ĐÚNG hệ số sản lượng — KHÔNG được phơi bất kỳ trường tiền nào"
    assert items[0]["output_coefficient"] is None, "seed để trống hệ số (chưa khai = engine coi 1.0)"


def test_them_sua_tat_bac(client):
    token = _admin_token(client)
    created = client.post("/api/employees/bac-tay-nghe", json={"name": "Bậc 6"},
                          headers=_h(token))
    assert created.status_code == 201, created.text
    gid = created.json()["id"]

    assert client.put(f"/api/employees/bac-tay-nghe/{gid}", json={"name": "Bậc 6 (mới)"},
                      headers=_h(token)).json()["name"] == "Bậc 6 (mới)"

    client.put(f"/api/employees/bac-tay-nghe/{gid}", json={"is_active": False},
               headers=_h(token))
    con_bat = [g["name"] for g in _grades(client, token, active_only=True)]
    assert "Bậc 6 (mới)" not in con_bat, "bậc đã tắt không được lọt vào danh sách CHỌN"
    assert "Bậc 6 (mới)" in [g["name"] for g in _grades(client, token)], \
        "màn quản lý vẫn phải thấy để còn bật lại"


def test_he_so_san_luong_dat_va_xoa_duoc(client):
    """Hệ số sản lượng (§8): tạo có hệ số · sửa lên · XOÁ (null) đều round-trip đúng.

    Xoá là ca dễ vỡ: router dùng `exclude_unset` nên gửi `null` phải hiểu là "xoá hệ số", KHÔNG
    phải "giữ nguyên" — nếu service lọc None thì hệ số cũ dính lại, engine chia sai."""
    token = _admin_token(client)
    gid = client.post("/api/employees/bac-tay-nghe",
                      json={"name": "Bậc có hệ số", "output_coefficient": 1.25},
                      headers=_h(token)).json()["id"]
    assert next(g for g in _grades(client, token) if g["id"] == gid)["output_coefficient"] == 1.25

    r = client.put(f"/api/employees/bac-tay-nghe/{gid}",
                   json={"output_coefficient": 0.8}, headers=_h(token))
    assert r.json()["output_coefficient"] == 0.8, r.text

    # Sửa tên KHÔNG kèm hệ số ⇒ hệ số phải giữ nguyên (exclude_unset).
    client.put(f"/api/employees/bac-tay-nghe/{gid}", json={"name": "Bậc có hệ số 2"},
               headers=_h(token))
    assert next(g for g in _grades(client, token) if g["id"] == gid)["output_coefficient"] == 0.8

    # Gửi null ⇒ XOÁ về chưa-khai.
    r = client.put(f"/api/employees/bac-tay-nghe/{gid}",
                   json={"output_coefficient": None}, headers=_h(token))
    assert r.json()["output_coefficient"] is None, r.text


def test_trung_ten_bi_chan_du_viet_hoa_thuong_khac_nhau(client):
    """Khai "thợ lành nghề" khi đã có "Thợ lành nghề" là đẻ hai bậc y hệt trong danh sách chọn."""
    token = _admin_token(client)
    r = client.post("/api/employees/bac-tay-nghe", json={"name": "  thợ lành nghề "},
                    headers=_h(token))
    assert r.status_code == 400, r.text
    assert "đã có" in r.json()["detail"]


def test_chan_xoa_bac_dang_co_nguoi_dung(client):
    """⭐ Xoá bậc còn người mang = hồ sơ trỏ vào bậc không tồn tại, mất luôn bậc của người ta."""
    token = _admin_token(client)
    gid = next(g["id"] for g in _grades(client, token) if g["code"] == "bac_1")
    eid = _make_emp(client, token, name="Thợ Bậc Một")
    client.post(f"/api/employees/{eid}/transitions",
                json={"kind": "promote", "new_job_grade_id": gid}, headers=_h(token))

    r = client.delete(f"/api/employees/bac-tay-nghe/{gid}", headers=_h(token))
    assert r.status_code == 400, r.text
    assert "không xoá được" in r.json()["detail"]
    assert any(g["id"] == gid for g in _grades(client, token)), "bậc phải còn nguyên"


def test_xoa_duoc_bac_chua_ai_dung(client):
    token = _admin_token(client)
    gid = client.post("/api/employees/bac-tay-nghe", json={"name": "Bậc tạm"},
                      headers=_h(token)).json()["id"]
    assert client.delete(f"/api/employees/bac-tay-nghe/{gid}",
                         headers=_h(token)).status_code == 204
    assert not any(g["id"] == gid for g in _grades(client, token))


def test_nang_bac_ghi_qua_trinh_cong_tac(client):
    """Đổi bậc phải để lại dấu — đó là lý do bậc đi qua transition chứ không phải ô sửa tay."""
    token = _admin_token(client)
    gid = next(g["id"] for g in _grades(client, token) if g["code"] == "bac_2")
    eid = _make_emp(client, token, name="NV Được Nâng Bậc")

    out = client.post(f"/api/employees/{eid}/transitions",
                      json={"kind": "promote", "new_job_grade_id": gid},
                      headers=_h(token))
    assert out.status_code == 200, out.text
    assert out.json()["job_grade_id"] == gid
    assert out.json()["job_grade_name"] == "Thợ vững", "phải trả TÊN bậc, khỏi bắt FE tra thêm"

    events = client.get(f"/api/employees/{eid}/events", headers=_h(token)).json()["items"]
    moc = [e for e in events if e["field"] == "job_grade"]
    assert len(moc) == 1 and moc[0]["to_value"] == "Thợ vững", moc


def test_bac_KHONG_doi_duoc_qua_sua_ho_so_thuong(client):
    """⭐ Test GIỮ LUẬT: gửi `job_grade_id` qua PUT hồ sơ thì phải bị bỏ.

    Lọt là có đường đổi bậc không ghi Quá trình công tác — đúng thứ luật hiện hành cấm."""
    token = _admin_token(client)
    g1, g2 = (next(g["id"] for g in _grades(client, token) if g["code"] == c)
              for c in ("bac_1", "bac_3"))
    eid = _make_emp(client, token, name="NV Giữ Luật")
    client.post(f"/api/employees/{eid}/transitions",
                json={"kind": "promote", "new_job_grade_id": g1}, headers=_h(token))

    r = client.put(f"/api/employees/{eid}",
                   json={"full_name": "NV Giữ Luật", "job_grade_id": g2}, headers=_h(token))
    assert r.status_code == 200, r.text

    con = client.get(f"/api/employees/{eid}", headers=_h(token)).json()
    assert con["job_grade_id"] == g1, "sửa hồ sơ thường KHÔNG được đổi bậc"


def test_gan_bac_khong_lam_doi_mot_dong_nao(client):
    """⭐ "Khai bậc thôi, chứ không cần điền tiền đâu" — chốt bằng SỐ THẬT.

    Gọi thẳng `_compute` với đủ 26 công: NV không có chấm công thì lương = 0, so 0 với 0 là
    test rỗng."""
    client
    db = SessionLocal()
    try:
        svc = PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None)
        params = svc.get_params()
        bac_1 = svc.employees.get_job_grade_by_code("bac_1")

        def _v(grade_id):
            emp = SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                                  payroll_group=None, pay_grade_key=None, dependents_count=0,
                                  job_grade_id=grade_id, job_grade=None)
            return svc._compute(employee=emp, params=params, actual_cong=26, standard_cong=26,
                                salary=_sal(luong_vi_tri=12_000_000), on=date(2026, 9, 1))

        khong, co = _v(None), _v(bac_1.id)
        assert khong["gross"] > 0, "test phải có lương thật thì so sánh mới có nghĩa"
        for k in ("gross", "pit", "bhxh", "luong_cong", "allowance", "chuyen_can"):
            assert khong[k] == co[k], f"gán bậc làm đổi {k}: {khong[k]} → {co[k]}"
    finally:
        db.close()


def test_gan_bac_da_tat_bi_chan(client):
    token = _admin_token(client)
    gid = client.post("/api/employees/bac-tay-nghe", json={"name": "Bậc ngừng dùng"},
                      headers=_h(token)).json()["id"]
    client.put(f"/api/employees/bac-tay-nghe/{gid}", json={"is_active": False},
               headers=_h(token))
    eid = _make_emp(client, token, name="NV Bậc Tắt")

    r = client.post(f"/api/employees/{eid}/transitions",
                    json={"kind": "promote", "new_job_grade_id": gid}, headers=_h(token))
    assert r.status_code == 400 and "đang tắt" in r.json()["detail"], r.text


def test_meta_tra_ve_co_san_xuat_hieu_luc(client):
    """⭐ FE ẩn/hiện ô Bậc tay nghề dựa vào cờ này. Thiếu nó thì FE phải tự leo cây `parent_id`,
    mà `parent_id` cũng không có trong meta ⇒ không có cách nào biết phòng nào là sản xuất."""
    token = _admin_token(client)
    meta = client.get("/api/employees/meta", headers=_h(token)).json()

    assert meta["departments"], "meta phải có danh sách phòng ban"
    assert all("la_san_xuat" in d for d in meta["departments"]), \
        "mọi phòng phải kèm cờ khối Sản xuất"

    from app.db import SessionLocal
    from app.repositories.rbac_repo import DepartmentRepository
    db = SessionLocal()
    try:
        # Bật cờ cho một phòng CHA rồi soi lại: tổ CON phải cũng thành sản xuất (cờ hiệu lực).
        repo = DepartmentRepository(db)
        cha = next((d for d in repo.list_all() if any(
            x.parent_id == d.id for x in repo.list_all())), None)
        if cha is None:
            return          # dữ liệu test không có cây cha-con thì thôi
        repo.set_la_san_xuat(cha, True)
        con_ids = {d.id for d in repo.list_all() if d.parent_id == cha.id}
    finally:
        db.close()

    lai = client.get("/api/employees/meta", headers=_h(token)).json()["departments"]
    co = {d["id"]: d["la_san_xuat"] for d in lai}
    assert co[cha.id] is True
    for cid in con_ids:
        assert co[cid] is True, "tổ con của phòng đã tick phải tự động là khối Sản xuất"


def test_khai_hoa_hong_ngay_khi_tao_ho_so(client):
    """Wizard khai lương ban đầu cùng lúc tạo hồ sơ — thiếu field ở `InitialEmployeeSalaryIn`
    thì % gõ vào bị nuốt lặng lẽ, người dùng tưởng đã khai."""
    token = _admin_token(client)
    r = client.post("/api/employees", json={
        "full_name": "NV Khai Hoa Hồng Lúc Tạo",
        "initial_salary": {"luong_vi_tri": 12_000_000, "commission_pct": 0.03},
    }, headers=_h(token))
    assert r.status_code == 201, r.text
    eid = r.json()["employee"]["id"]

    items = client.get(f"/api/luong/salaries/{eid}", headers=_h(token)).json()["items"]
    assert items[0]["commission_pct"] == 0.03, "% khai lúc tạo hồ sơ phải được lưu"
