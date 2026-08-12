"""Phân hệ Nhân sự & Lương — mỗi màn một ô, và TỰ PHỤC VỤ là ô thật (tách 10/08/2026).

Ba thứ đổi ở lát này, mỗi thứ vá một bệnh tester ghi:

1. **Tự phục vụ thành một ô** (`self_service`). Trước đó 34 endpoint `/me` của 6 router chỉ đòi
   ĐĂNG NHẬP — luật ngầm, không có ô nào để tắt. Đúng chỗ tester bắt ở Tăng ca: *"phân quyền xem
   nhưng user vẫn gửi, sửa, huỷ phiếu được"*.
2. **Màn Chấm công tách khoá riêng** (`cham_cong`). Trước đó dùng chung `nhan_su` nên cấp quyền
   xem hồ sơ là mở luôn bảng công cả công ty.
3. **Chốt kỳ công tách khỏi Chấm bù** (`can_lock` ≠ `can_adjust`), và ba tab cấu hình khoá cả
   ĐƯỜNG ĐỌC — trước đây vai chỉ-xem không thấy tab nhưng gọi thẳng API vẫn đọc được toạ độ +
   bán kính mọi điểm chấm công và lưới phân ca cả tháng.
"""

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _tai_khoan(ten: str, quyen: dict[str, dict] | None = None) -> str:
    """Tạo tài khoản với ĐÚNG bộ quyền được nêu (ngoài hai ô mặc định của vai mới)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(ten)
        if existing is not None:
            return create_access_token(str(existing.id))
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        roles = RoleRepository(db)
        role = roles.create(name=f"Vai {ten}", department_id=dept.id)
        for khoa, co in (quyen or {}).items():
            roles.set_permission(role_id=role.id, module_key=khoa, **co)
        u = users.create(username=ten, name=ten, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        db.commit()
        return create_access_token(str(u.id))
    finally:
        db.close()


def _go_o(ten_vai: str, khoa: str) -> None:
    """Gỡ một ô của vai (đặt can_read=False) — dùng để dựng ca 'không được cấp'."""
    db = SessionLocal()
    try:
        roles = RoleRepository(db)
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        role = roles.get_by_name_and_department(ten_vai, dept.id)
        roles.set_permission(role_id=role.id, module_key=khoa, can_read=False, scope="own")
        db.commit()
    finally:
        db.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════ 1) Tự phục vụ là ô THẬT

# Vài đường tự phục vụ tiêu biểu, mỗi router một cái.
DUONG_TU_PHUC_VU = (
    "/api/attendance/me/status",
    "/api/attendance/me/logs",
    "/api/overtime/me",
    "/api/late-early/me",
    "/api/employees/me",
    "/api/luong/advances/me",
)


def test_vai_moi_co_san_o_tu_phuc_vu(client):
    """Vai mới sinh ra đã bật sẵn Tự phục vụ — nếu không thì gán vai xong thợ vẫn không chấm công được."""
    tok = _tai_khoan("tpv-mac-dinh")
    for duong in DUONG_TU_PHUC_VU:
        r = client.get(duong, headers=_h(tok))
        assert r.status_code != 403, f"vai mới mà bị chặn ở {duong}"


def test_go_o_tu_phuc_vu_thi_chan_het_duong_me(client):
    """Gỡ ô ⇒ chặn. Đây là chiều mà trước 10/08/2026 KHÔNG THỂ có: không có ô nào để gỡ."""
    tok = _tai_khoan("tpv-bi-go")
    _go_o("Vai tpv-bi-go", "self_service")

    for duong in DUONG_TU_PHUC_VU:
        r = client.get(duong, headers=_h(tok))
        assert r.status_code == 403, f"đã gỡ ô Tự phục vụ mà vẫn vào được {duong} ({r.status_code})"

    # Cả đường GHI — đúng chỗ tester bắt: "xem thôi mà vẫn gửi/sửa/huỷ phiếu được".
    assert client.post("/api/overtime/me", json={
        "work_date": "2026-08-20", "from_minute": 1020, "to_minute": 1080, "reason": "x",
    }, headers=_h(tok)).status_code == 403
    assert client.post("/api/attendance/check", json={
        "latitude": 10.0, "longitude": 106.0,
    }, headers=_h(tok)).status_code == 403


def test_xem_tang_ca_khong_keo_theo_quyen_gui_phieu(client):
    """Ô `tang_ca:read` chỉ cho THẤY màn — không phải giấy phép gửi phiếu.

    Tester ghi: *"phân quyền xem nhưng user vẫn gửi, sửa, huỷ phiếu được"*. Gốc không nằm ở
    `tang_ca` mà ở chỗ đường tự phục vụ không gác gì.
    """
    tok = _tai_khoan("chi-xem-tang-ca", {"tang_ca": dict(can_read=True, scope=SCOPE_ALL)})
    _go_o("Vai chi-xem-tang-ca", "self_service")

    assert client.get("/api/overtime", headers=_h(tok)).status_code == 200
    assert client.post("/api/overtime/me", json={
        "work_date": "2026-08-20", "from_minute": 1020, "to_minute": 1080, "reason": "x",
    }, headers=_h(tok)).status_code == 403


# ══════════════════════════════════════════════ 2) Chấm công tách khỏi Hồ sơ nhân sự


def test_ho_so_nhan_su_khong_con_mo_duoc_bang_cong(client):
    """Cấp `nhan_su` KHÔNG kéo theo màn Chấm công nữa, và ngược lại."""
    hs = _tai_khoan("chi-ho-so", {"nhan_su": dict(can_read=True, scope=SCOPE_ALL)})
    cc = _tai_khoan("chi-cham-cong", {"cham_cong": dict(can_read=True, scope=SCOPE_ALL)})

    assert client.get("/api/employees", headers=_h(hs)).status_code == 200
    assert client.get("/api/attendance/timesheet?year=2026&month=8",
                      headers=_h(hs)).status_code == 403

    assert client.get("/api/attendance/timesheet?year=2026&month=8",
                      headers=_h(cc)).status_code == 200
    assert client.get("/api/employees", headers=_h(cc)).status_code == 403


def test_xem_cham_cong_khong_doc_duoc_cau_hinh(client):
    """Ba tab cấu hình khoá cả ĐƯỜNG ĐỌC.

    Lỗ hổng cũ: giao diện ẩn tab nhưng máy chủ chỉ đòi `read`, nên vai chỉ-xem gọi thẳng API là
    đọc được toạ độ + bán kính mọi điểm chấm công và lưới phân ca cả tháng.
    """
    tok = _tai_khoan("cc-chi-xem", {"cham_cong": dict(can_read=True, scope=SCOPE_ALL)})

    for duong in ("/api/attendance/locations",
                  "/api/attendance/shift-plan?year=2026&month=8",
                  "/api/calendar/config",
                  "/api/calendar/special-days?year=2026"):
        r = client.get(duong, headers=_h(tok))
        assert r.status_code == 403, f"vai chỉ-xem vẫn đọc được cấu hình: {duong} ({r.status_code})"

    # Có ô Cấu hình thì đọc được.
    quan = _tai_khoan("cc-cau-hinh",
                      {"cham_cong": dict(can_read=True, can_update=True, scope=SCOPE_ALL)})
    assert client.get("/api/attendance/locations", headers=_h(quan)).status_code == 200
    assert client.get("/api/calendar/config", headers=_h(quan)).status_code == 200


def test_cham_bu_khong_keo_theo_quyen_chot_ky(client):
    """CHỐT KỲ tách khỏi CHẤM BÙ — một cú bấm đóng băng đầu vào lương toàn nhà máy."""
    ky = {"year": 2026, "month": 7}
    cham_bu = _tai_khoan("cc-cham-bu",
                         {"cham_cong": dict(can_read=True, can_adjust=True, scope=SCOPE_ALL)})

    r = client.post("/api/attendance/period/lock", json=ky, headers=_h(cham_bu))
    assert r.status_code == 403, f"có mỗi ô Chấm bù mà vẫn chốt được kỳ: {r.text}"
    assert client.post("/api/attendance/period/reopen", json=ky,
                       headers=_h(cham_bu)).status_code == 403

    # Có ô Chốt kỳ + phạm vi cả công ty ⇒ chốt được (hàng rào phạm vi đã vá ở đợt 1).
    chot = _tai_khoan("cc-chot-ky",
                      {"cham_cong": dict(can_read=True, can_lock=True, scope=SCOPE_ALL)})
    assert client.post("/api/attendance/period/lock", json=ky, headers=_h(chot)).status_code == 200


# ══════════════════════════════════════════════ 3) Lương có phạm vi RIÊNG


def test_luong_khong_con_muon_pham_vi_cua_nhan_su(client):
    """Lương đọc phạm vi của CHÍNH nó.

    Trước đây `payroll._scope_for` đọc `scope_for(user, "nhan_su")`: cấp quyền Lương phạm vi cả
    công ty mà quên cấp Nhân sự thì người đó tụt về *chỉ mình* — không ai đoán ra được.
    """
    tok = _tai_khoan("luong-pham-vi-rieng", {"luong": dict(can_read=True, scope=SCOPE_ALL)})
    r = client.get("/api/luong/periods", headers=_h(tok))
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════ 4) Nội quy


def test_noi_quy_la_o_that_chu_khong_phai_ai_dang_nhap_cung_doc(client):
    tok = _tai_khoan("nq-co-o")
    assert client.get("/api/noi-quy", headers=_h(tok)).status_code == 200

    _go_o("Vai nq-co-o", "noi_quy")
    assert client.get("/api/noi-quy", headers=_h(tok)).status_code == 403


# ══════════════════════════════════════════════ 5) Đợt 4 — bốn việc nguy hiểm, mỗi việc một ô


def _co_bang_luong(client, nam: int, thang: int) -> None:
    """Admin sinh bảng lương tháng đó (điều kiện cần để chốt / đánh dấu đã chi)."""
    admin = client.post("/api/auth/login",
                        json={"username": "admin", "password": "admin123"}).json()["access_token"]
    client.post("/api/luong/generate", json={"year": nam, "month": thang}, headers=_h(admin))


def test_chot_bang_luong_doi_pham_vi_toan_cong_ty(client):
    """LỖ HỔNG ĐÃ ĐO 10/08/2026 — cùng khuôn sai với Chốt kỳ công đã vá ở đợt 1.

    Kỳ lương là MỘT bản ghi cho cả công ty (`payroll_periods` khoá theo năm+tháng). Trước bản vá,
    endpoint chỉ hỏi "có ô Chốt không", KHÔNG hỏi người bấm quản ai: vai phạm vi `own` bấm chốt ⇒
    kỳ chuyển `locked`, bấm tiếp ⇒ chuyển `paid` (tuyên bố ĐÃ TRẢ TIỀN cho toàn bộ người lao động).
    """
    _co_bang_luong(client, 2026, 7)
    ky = {"year": 2026, "month": 7}

    for pham_vi in ("own", "department"):
        tok = _tai_khoan(f"luong-chot-{pham_vi}", {
            "luong": dict(can_read=True, can_lock=True, can_manage_status=True, scope=pham_vi),
        })
        r = client.post("/api/luong/lock", json=ky, headers=_h(tok))
        assert r.status_code == 403, f"phạm vi {pham_vi} vẫn chốt được bảng lương: {r.text}"
        assert "cả công ty" in r.json()["detail"]

        assert client.post("/api/luong/reopen", json=ky, headers=_h(tok)).status_code == 403
        assert client.post("/api/luong/pay", json=ky, headers=_h(tok)).status_code == 403
        assert client.post("/api/luong/unpay", json=ky, headers=_h(tok)).status_code == 403


def test_chot_bang_luong_khong_keo_theo_quyen_danh_dau_da_chi(client):
    """CHỐT (số đã tính xong) ≠ ĐÃ CHI (tiền đã ra tới tay người lao động).

    Gộp một ô thì ai chốt được là tự tuyên bố đã trả — không còn ai đối chiếu. Ngoài đời hai người:
    người tính lương chốt số, kế toán mới xác nhận đã trả.
    """
    _co_bang_luong(client, 2026, 6)
    ky = {"year": 2026, "month": 6}

    chi_chot = _tai_khoan("luong-chi-chot",
                          {"luong": dict(can_read=True, can_lock=True, scope=SCOPE_ALL)})
    assert client.post("/api/luong/lock", json=ky, headers=_h(chi_chot)).status_code == 200
    r = client.post("/api/luong/pay", json=ky, headers=_h(chi_chot))
    assert r.status_code == 403, f"có mỗi ô Chốt mà vẫn đánh dấu được đã chi: {r.text}"

    # Người có ô Đánh dấu đã chi thì làm được — và KHÔNG cần ô Chốt.
    ke_toan = _tai_khoan("luong-danh-dau-da-chi",
                         {"luong": dict(can_read=True, can_manage_status=True, scope=SCOPE_ALL)})
    ok = client.post("/api/luong/pay", json=ky, headers=_h(ke_toan))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "paid"


def test_danh_dau_da_chi_khong_keo_theo_quyen_chot(client):
    """Chiều ngược lại — kế toán xác nhận đã trả thì không tự chốt / mở lại kỳ được."""
    _co_bang_luong(client, 2026, 5)
    ky = {"year": 2026, "month": 5}
    ke_toan = _tai_khoan("luong-chi-da-chi",
                         {"luong": dict(can_read=True, can_manage_status=True, scope=SCOPE_ALL)})

    assert client.post("/api/luong/lock", json=ky, headers=_h(ke_toan)).status_code == 403
    assert client.post("/api/luong/reopen", json=ky, headers=_h(ke_toan)).status_code == 403


def test_xem_bang_cong_khong_keo_theo_quyen_doc_nhat_ky(client):
    """Ô RIÊNG cho tab "Nhật ký chấm công" (11/08/2026).

    Bảng công tháng là số công đã TỔNG HỢP; nhật ký là TỪNG LƯỢT BẤM kèm giờ và toạ độ của từng
    người, cả xưởng — ai đi sớm về muộn hôm nào, đọc là biết. Người cần xem công để tính lương
    không đương nhiên cần đọc dấu chân từng người."""
    chi_bang_cong = _tai_khoan("cc-bang-cong",
                               {"cham_cong": dict(can_read=True, scope=SCOPE_ALL)})
    assert client.get("/api/attendance/timesheet?year=2026&month=8",
                      headers=_h(chi_bang_cong)).status_code == 200
    r = client.get("/api/attendance/logs", headers=_h(chi_bang_cong))
    assert r.status_code == 403, f"chỉ có ô Xem mà vẫn đọc được nhật ký: {r.status_code}"

    co_nhat_ky = _tai_khoan("cc-nhat-ky",
                            {"cham_cong": dict(can_read=True, can_view_log=True, scope=SCOPE_ALL)})
    assert client.get("/api/attendance/logs", headers=_h(co_nhat_ky)).status_code == 200


# ══════════════════════════════════ 6) Vòng 2 — Tự phục vụ tách XEM / THAO TÁC (11/08/2026)


def test_o_xem_tu_phuc_vu_khong_cho_ghi_gi(client):
    """Chủ chốt báo ba lần, ba màn, cùng một gốc: *"chưa bật thao tác nó vẫn hiện nút gửi sửa
    công, xin đi muộn về sớm vẫn thao tác được"* · *"Tăng ca: vẫn tạo được phiếu của mình"* ·
    *"Nghỉ phép: vẫn xin nghỉ phép"*.

    Gốc: khoá `self_service` từ đợt 3 tới nay CHỈ dùng động từ `read` — cột "Thao tác" là ô chết.
    Nay `create` mới là thứ cho GHI."""
    chi_xem = _tai_khoan("tpv-chi-xem", {
        "self_service": dict(can_read=True, can_create=False, scope="own"),
    })

    # ĐỌC vẫn được — người ta phải xem được công / phiếu của chính mình.
    assert client.get("/api/attendance/me/status", headers=_h(chi_xem)).status_code == 200
    assert client.get("/api/overtime/me", headers=_h(chi_xem)).status_code == 200

    # GHI thì không.
    assert client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0},
                       headers=_h(chi_xem)).status_code == 403, "chấm công được dù chỉ có ô Xem"
    assert client.post("/api/overtime/me", json={
        "work_date": "2026-08-20", "from_minute": 1020, "to_minute": 1080, "reason": "x",
    }, headers=_h(chi_xem)).status_code == 403, "gửi phiếu tăng ca được dù chỉ có ô Xem"
    assert client.post("/api/late-early/me", json={
        "work_date": "2026-08-20", "kind": "late", "minutes": 30, "reason": "x",
    }, headers=_h(chi_xem)).status_code == 403, "xin đi muộn được dù chỉ có ô Xem"
    assert client.post("/api/luong/advances/me", json={"amount": 100000, "reason": "x"},
                       headers=_h(chi_xem)).status_code == 403, "xin tạm ứng được dù chỉ có ô Xem"
    assert client.post("/api/leaves", json={
        "leave_type_id": 1, "start_date": "2026-08-20", "end_date": "2026-08-20", "reason": "x",
    }, headers=_h(chi_xem)).status_code == 403, "xin nghỉ được dù chỉ có ô Xem"


def test_co_o_thao_tac_thi_ghi_duoc(client):
    """Chiều ngược lại — bật ô Thao tác là qua được hàng rào quyền (còn hợp lệ nghiệp vụ hay không
    là chuyện khác)."""
    co_ghi = _tai_khoan("tpv-co-ghi", {
        "self_service": dict(can_read=True, can_create=True, scope="own"),
    })
    for duong, than in (
        ("/api/overtime/me", {"work_date": "2026-08-20", "from_minute": 1020,
                              "to_minute": 1080, "reason": "x"}),
        ("/api/luong/advances/me", {"amount": 100000, "reason": "x"}),
    ):
        r = client.post(duong, json=than, headers=_h(co_ghi))
        assert r.status_code != 403, f"có ô Thao tác mà vẫn bị chặn quyền ở {duong}"


def test_xuat_excel_nhan_su_doi_o_rieng(client):
    """Ô "Xuất Excel danh sách" trước 11/08/2026 chưa bao giờ có tác dụng: endpoint chỉ đòi `read`,
    giao diện thì render nút trần. Xuất file là mang dữ liệu RA KHỎI hệ thống — phải cấp riêng."""
    chi_xem = _tai_khoan("ns-chi-xem", {"nhan_su": dict(can_read=True, scope=SCOPE_ALL)})
    assert client.get("/api/employees", headers=_h(chi_xem)).status_code == 200
    assert client.get("/api/employees/export.xlsx",
                      headers=_h(chi_xem)).status_code == 403, "chỉ có Xem mà vẫn tải được file"

    co_xuat = _tai_khoan("ns-co-xuat",
                         {"nhan_su": dict(can_read=True, can_export=True, scope=SCOPE_ALL)})
    assert client.get("/api/employees/export.xlsx", headers=_h(co_xuat)).status_code == 200


# ══════════════════════════════ 7) Đợt D — tách ô Yêu cầu chỉnh công · Đi muộn chỉ còn Duyệt


def test_duyet_yeu_cau_chinh_cong_doi_o_rieng(client):
    """Tách khỏi ô "Chấm bù" của màn Chấm công (11/08/2026).

    Duyệt yêu cầu chỉnh công là việc của người QUẢN tổ/phòng; còn `cham_cong:read` thì ai xem bảng
    công cũng có. Trước đây xem thì dùng chung `read`, duyệt thì dùng chung `adjust`."""
    cham_bu = _tai_khoan("ycch-cham-bu", {
        "cham_cong": dict(can_read=True, can_adjust=True, scope=SCOPE_ALL),
    })
    assert client.get("/api/attendance/adjust-requests",
                      headers=_h(cham_bu)).status_code == 403, "ô Chấm bù vẫn mở được màn này"
    assert client.post("/api/attendance/adjust-requests/1/approve", json={},
                       headers=_h(cham_bu)).status_code == 403

    co_o = _tai_khoan("ycch-co-o", {
        "yeu_cau_chinh_cong": dict(can_read=True, can_approve=True, scope=SCOPE_ALL),
    })
    assert client.get("/api/attendance/adjust-requests", headers=_h(co_o)).status_code == 200
    assert client.post("/api/attendance/adjust-requests/1/approve", json={},
                       headers=_h(co_o)).status_code != 403


def test_xem_yeu_cau_chinh_cong_khong_keo_theo_quyen_duyet(client):
    chi_xem = _tai_khoan("ycch-chi-xem",
                         {"yeu_cau_chinh_cong": dict(can_read=True, scope=SCOPE_ALL)})
    assert client.get("/api/attendance/adjust-requests", headers=_h(chi_xem)).status_code == 200
    for duong in ("/api/attendance/adjust-requests/1/approve",
                  "/api/attendance/adjust-requests/1/reject"):
        assert client.post(duong, json={"reason": "x"},
                           headers=_h(chi_xem)).status_code == 403, f"chỉ Xem mà duyệt được: {duong}"


def test_di_muon_chi_con_o_duyet(client):
    """Chủ chốt: *"Nút Xem với Thao tác có bị thừa không, tôi chỉ thấy Duyệt phiếu đi muộn/về sớm
    là dùng được thôi"*. Danh sách nay đi theo ô Duyệt; xem phiếu của mình thì qua Tự phục vụ."""
    chi_xem = _tai_khoan("dm-chi-xem", {"di_muon": dict(can_read=True, scope=SCOPE_ALL)})
    assert client.get("/api/late-early", headers=_h(chi_xem)).status_code == 403

    co_duyet = _tai_khoan("dm-co-duyet",
                          {"di_muon": dict(can_read=True, can_approve=True, scope=SCOPE_ALL)})
    assert client.get("/api/late-early", headers=_h(co_duyet)).status_code == 200
