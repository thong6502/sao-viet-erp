"""ĐỢT 1 vá luồng Chấm công ⇄ Lương (chủ chốt 12/08/2026) — L1 · L2 · L5.

BỆNH CHUNG của cả ba: **một đường ghi vào tháng đã chốt mà không ai hỏi "chốt chưa"**.

`AttendanceService._require_period_open` viết đúng luật đó từ trước, nhưng chỉ gắn vào 4 đường —
chấm bù · xóa punch bù · sửa ca · gửi yêu cầu chỉnh công. Toàn đường của HCNS. Còn **duyệt đơn
nghỉ · duyệt phiếu tăng ca · duyệt phiếu đi muộn** thì không ai hỏi, mà đó mới là đường đi HẰNG
NGÀY: thợ nộp giấy nghỉ ốm tuần sau, tổ trưởng duyệt bù.

Đo được 12/08/2026: duyệt một đơn nghỉ CÓ LƯƠNG cho tháng đã chốt ⇒ Bảng công tháng cộng thêm công
(nó tính LIVE), Bảng lương giữ số cũ (nó đọc ẢNH CHỤP). Hai màn nói hai con số, không chỗ nào báo,
người lao động là bên mất tiền.

BA LỖ ĐƯỢC VÁ Ở ĐỢT NÀY
-----------------------
* **L1** — chốt lương không đòi chốt công ⇒ chi tiền trên số công còn sửa được.
* **L2** — duyệt / hủy đơn nghỉ · tăng ca · đi muộn vẫn lọt vào tháng đã chốt.
* **L5** — còn NGÀY TREO (bấm VÀO thiếu bấm RA) vẫn chốt công được ⇒ đóng băng luôn cái sai.

CHỖ DỄ VÁ HỤT (đã có test riêng ở dưới)
---------------------------------------
Tăng ca và đi muộn có đường **tổ trưởng tạo HỘ = duyệt luôn**, KHÔNG đi qua `_decide`. Chỉ gác
`_decide` là "tạo hộ" thành đường vòng ghi thẳng vào tháng đã chốt.
"""

from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository

ADMIN = {"username": "admin", "password": "admin123"}

#: Tháng để thử L2/L5 — QUÁ KHỨ so với "hôm nay" của bộ test, vì chấm công chặn ghi ngày chưa tới.
NAM, THANG = 2026, 7
NGAY = f"{NAM}-{THANG:02d}-06"

#: L1 chỉ áp từ `payroll_service.AP_DUNG_CHOT_CONG_TRUOC_TU` trở đi — tháng thử phải ≥ mốc đó.
L1_NAM, L1_THANG = 2026, 8


def _h(client) -> dict[str, str]:
    tok = client.post("/api/auth/login", json=ADMIN).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _nhan_vien(client, h, ten="NV Chot Cong") -> dict:
    r = client.post("/api/employees",
                    json={"full_name": ten, "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": "2020-01-01"}, headers=h)
    assert r.status_code in (200, 201), r.text
    emp = r.json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": _uid("admin")}, headers=h)
    return emp


def _gan_ca(client, h, employee_id: int) -> int:
    """Chấm bù đòi NV có CA hiệu lực trong ngày — không gán thì API trả 400 và ca đo hỏng
    trước cả khi chạm tới luật đang thử."""
    items = client.get("/api/attendance/shifts", headers=h).json()["items"]
    ca = next((s for s in items if s["name"] == "Ca thử chốt công"), None)
    if ca is None:
        ca = client.post("/api/attendance/shifts",
                         json={"name": "Ca thử chốt công", "start_time": "08:00",
                               "end_time": "17:00"}, headers=h).json()
    # `effective_from` BẮT BUỘC lùi về trước ngày thử: gán ca tạo một dòng LỊCH SỬ, và ngày nằm
    # trước dòng đầu tiên cố ý nghĩa là "chưa có ca" (xem `base_shift_id_on`). Bỏ trống ⇒ hiệu lực
    # từ hôm nay ⇒ chấm bù cho ngày trong quá khứ trả 400 và ca đo hỏng trước khi chạm luật đang thử.
    r = client.put(f"/api/employees/{employee_id}/shift",
                   json={"default_shift_id": ca["id"], "effective_from": "2020-01-01"}, headers=h)
    assert r.status_code == 200, r.text
    return ca["id"]


def _chot_cong(client, h, *, nam=NAM, thang=THANG, expect=200):
    r = client.post("/api/attendance/period/lock", json={"year": nam, "month": thang}, headers=h)
    assert r.status_code == expect, r.text
    return r


def _loai_nghi(client, h, ten="Nghỉ ốm chốt công") -> int:
    r = client.post("/api/leaves/types", json={"name": ten, "is_paid": True}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ══════════════════════════════════════════════ L1 — chốt lương đòi chốt công


def test_L1_chua_chot_cong_thi_khong_chot_duoc_luong(client):
    """⭐ Mắt xích còn thiếu của vòng khoá. Trước bản vá: tính lương → chốt → chi tiền, mà kỳ công
    chưa từng chốt ⇒ lương chạy trên số LIVE, và số live vẫn sửa được SAU KHI TIỀN ĐÃ RA."""
    h = _h(client)
    _nhan_vien(client, h)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200

    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code in (400, 409, 422), f"chốt được lương khi kỳ công chưa chốt: {r.text}"
    chi_tiet = r.json()["detail"]
    assert "Chấm công" in chi_tiet, f"câu báo phải CHỈ ĐƯỜNG sang màn Chấm công: {chi_tiet}"


def test_L1_chot_cong_xong_thi_chot_luong_duoc(client):
    """Đối chứng — chặn phải MỞ RA được, nếu không là ngõ cụt."""
    h = _h(client)
    _nhan_vien(client, h)
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200
    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "locked"


def test_L1_thang_truoc_moc_van_chot_duoc_nhu_cu(client):
    """MIỄN TRỪ CÓ CHỦ Ý, đừng "sửa" thành chặt hơn mà không hỏi.

    Hệ thống đang chạy có tháng ĐÃ CHỐT / ĐÃ CHI lương mà chưa hề tồn tại dòng kỳ công. Áp luật
    ngược về quá khứ thì ai mở lại một kỳ lương cũ để sửa sẽ KHÔNG CHỐT LẠI ĐƯỢC — muốn chốt công
    tháng đó phải đi duyệt sạch đơn treo từ đời nào, có khi của người đã nghỉ việc."""
    from app.services.payroll_service import AP_DUNG_CHOT_CONG_TRUOC_TU

    truoc = (2026, 5)
    assert truoc < AP_DUNG_CHOT_CONG_TRUOC_TU, "chọn lại tháng thử cho nằm TRƯỚC mốc"

    h = _h(client)
    _nhan_vien(client, h)
    assert client.post("/api/luong/generate", json={"year": truoc[0], "month": truoc[1]},
                       headers=h).status_code == 200
    r = client.post("/api/luong/lock", json={"year": truoc[0], "month": truoc[1]}, headers=h)
    assert r.status_code == 200, f"tháng trước mốc phải chốt được như cũ: {r.text}"


# ══════════════════════════════════════════════ L2 — duyệt/hủy đơn vào tháng đã chốt


def test_L2_khong_duyet_duoc_don_nghi_cua_thang_da_chot(client):
    """Đường đi HẰNG NGÀY: thợ nộp giấy nghỉ muộn, tổ trưởng duyệt bù. Duyệt xong ngày đó thành
    công có lương ⇒ Bảng công đổi số, Bảng lương giữ ảnh chụp cũ."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _chot_cong(client, h)
    tid = _loai_nghi(client, h)

    # Tạo đơn SAU khi chốt: `lock_period` chỉ chặn đơn ĐANG TREO tại thời điểm chốt.
    rid = client.post("/api/leaves",
                      json={"leave_type_id": tid, "employee_id": emp["id"],
                            "start_date": NGAY, "end_date": NGAY},
                      headers=h).json()["id"]

    r = client.post(f"/api/leaves/{rid}/approve", json={}, headers=h)
    assert r.status_code in (400, 409, 422), f"duyệt lọt vào tháng đã chốt: {r.text}"
    assert "đã chốt" in r.json()["detail"]


def test_L2_van_TU_CHOI_duoc_don_cua_thang_da_chot(client):
    """Đừng chặn quá tay: đơn ĐANG CHỜ không hề tính vào bảng công, từ chối nó không đổi số nào.
    Chặn luôn cả từ chối là để đơn treo vĩnh viễn trong hộp việc của tổ trưởng."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _chot_cong(client, h)
    tid = _loai_nghi(client, h)
    rid = client.post("/api/leaves",
                      json={"leave_type_id": tid, "employee_id": emp["id"],
                            "start_date": NGAY, "end_date": NGAY},
                      headers=h).json()["id"]

    r = client.post(f"/api/leaves/{rid}/reject", json={"note": "không đủ căn cứ"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"


def test_L2_don_nghi_bac_cau_hai_thang_cung_bi_chan(client):
    """Đơn 30/7 → 02/8: tháng 7 đã chốt, tháng 8 chưa. Chỉ cần MỘT đầu rơi vào tháng đã chốt là đủ
    làm lệch số — soi mỗi ngày bắt đầu là lọt."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _chot_cong(client, h)
    tid = _loai_nghi(client, h)
    rid = client.post("/api/leaves",
                      json={"leave_type_id": tid, "employee_id": emp["id"],
                            "start_date": f"{NAM}-{THANG:02d}-30", "end_date": f"{NAM}-08-02"},
                      headers=h).json()["id"]

    r = client.post(f"/api/leaves/{rid}/approve", json={}, headers=h)
    assert r.status_code in (400, 409, 422), f"đơn bắc cầu lọt: {r.text}"
    assert f"{THANG}/{NAM}" in r.json()["detail"], "phải gọi đúng tên tháng đang vướng"


def test_L2_khong_huy_duoc_don_nghi_DA_DUYET_cua_thang_da_chot(client):
    """Chiều ngược: hủy đơn đã duyệt = GỠ công đã đóng băng, lệch y hệt chiều duyệt."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    tid = _loai_nghi(client, h)
    rid = client.post("/api/leaves",
                      json={"leave_type_id": tid, "employee_id": emp["id"],
                            "start_date": NGAY, "end_date": NGAY},
                      headers=h).json()["id"]
    assert client.post(f"/api/leaves/{rid}/approve", json={}, headers=h).status_code == 200
    _chot_cong(client, h)          # chốt SAU khi đơn đã duyệt ⇒ công đó đã vào ảnh chụp

    r = client.post(f"/api/leaves/{rid}/cancel", headers=h)
    assert r.status_code in (400, 409, 422), f"hủy lọt: {r.text}"
    assert "đã chốt" in r.json()["detail"]


def test_L2_to_truong_TAO_HO_phieu_tang_ca_cung_bi_chan(client):
    """⚠️ CHỖ DỄ VÁ HỤT. Tạo hộ = DUYỆT LUÔN, không đi qua `_decide`. Chỉ gác `_decide` thì
    "tạo hộ" thành đường vòng ghi thẳng phút tăng ca vào tháng đã chốt."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _chot_cong(client, h)

    r = client.post("/api/overtime",
                    json={"employee_id": emp["id"], "work_date": NGAY,
                          "from_minute": 1020, "to_minute": 1140, "reason": "chạy đơn gấp"},
                    headers=h)
    assert r.status_code in (400, 409, 422), f"tạo hộ lọt vào tháng đã chốt: {r.text}"
    assert "đã chốt" in r.json()["detail"]


def test_L2_to_truong_KHAI_HO_phieu_di_muon_cung_bi_chan(client):
    """Cùng đường vòng như tăng ca — phiếu đi muộn duyệt xong là MIỄN PHẠT (+ có thể trừ phép)."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _chot_cong(client, h)

    r = client.post("/api/late-early",
                    json={"employee_id": emp["id"], "work_date": NGAY,
                          "from_minute": 480, "to_minute": 540, "reason": "kẹt xe"},
                    headers=h)
    assert r.status_code in (400, 409, 422), f"khai hộ lọt vào tháng đã chốt: {r.text}"
    assert "đã chốt" in r.json()["detail"]


def test_L2_thang_CHUA_chot_thi_moi_duong_van_chay_binh_thuong(client):
    """Đối chứng cho cả cụm L2 — vá xong mà chặn nhầm tháng đang mở thì cả xưởng đứng."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    tid = _loai_nghi(client, h)

    rid = client.post("/api/leaves",
                      json={"leave_type_id": tid, "employee_id": emp["id"],
                            "start_date": NGAY, "end_date": NGAY},
                      headers=h).json()["id"]
    assert client.post(f"/api/leaves/{rid}/approve", json={}, headers=h).status_code == 200

    assert client.post("/api/overtime",
                       json={"employee_id": emp["id"], "work_date": NGAY,
                             "from_minute": 1020, "to_minute": 1140, "reason": "x"},
                       headers=h).status_code == 201
    assert client.post("/api/late-early",
                       json={"employee_id": emp["id"], "work_date": NGAY,
                             "from_minute": 480, "to_minute": 540, "reason": "y"},
                       headers=h).status_code == 201


# ══════════════════════════════════════════════ L5 — ngày treo chặn chốt công


def test_L5_con_ngay_treo_thi_khong_chot_cong_duoc(client):
    """`period_status` đếm `hanging_days` và trả về cho giao diện từ lâu, nhưng chỗ QUYẾT ĐỊNH
    (`lock_period`) lại không dùng — đếm để hiển thị rồi bỏ qua lúc chốt là bẫy khó thấy nhất.

    Chốt khi còn ngày treo = ĐÓNG BĂNG LUÔN CÁI SAI: ngày đó vào ảnh chụp với 0 giờ, lương trả
    thiếu, mà sau đó không sửa được nữa (`_require_period_open` đã khoá đường chấm bù)."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _gan_ca(client, h, emp["id"])
    # Chỉ bấm VÀO, không có bấm RA ⇒ 1 ngày treo.
    r_bu = client.post("/api/attendance/adjust",
                       json={"employee_id": emp["id"], "date": NGAY, "check_type": "in",
                             "time": "08:00", "reason": "NV quên chấm vào"},
                       headers=h)
    assert r_bu.status_code == 200, r_bu.text

    st = client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                    headers=h).json()
    assert st["hanging_days"] >= 1, "ca đo hỏng: chưa dựng được ngày treo nào"

    r = _chot_cong(client, h, expect=400)
    assert "treo" in r.json()["detail"]


def test_L5_cham_bu_du_roi_thi_chot_cong_duoc(client):
    """Đối chứng: chặn phải mở ra được sau khi sửa đúng cái nó phàn nàn."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _gan_ca(client, h, emp["id"])
    for kieu, gio in (("in", "08:00"), ("out", "17:00")):
        r_bu = client.post("/api/attendance/adjust",
                           json={"employee_id": emp["id"], "date": NGAY, "check_type": kieu,
                                 "time": gio, "reason": "NV quên chấm"},
                           headers=h)
        assert r_bu.status_code == 200, r_bu.text

    st = client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                    headers=h).json()
    assert st["hanging_days"] == 0
    _chot_cong(client, h)


# ══════════════════════════════════════════════ B — giao diện Lương phải BIẾT


def test_B_table_tra_ly_do_chua_chot_duoc(client):
    """Cờ này nuôi hai thứ trên màn Lương: băng cảnh báo + nút "Chốt" xám.

    Thiếu nó thì người tính lương bấm Chốt rồi mới ăn lỗi đỏ — đúng kiểu UX mà đợt 5 dọn đi
    (khoá nút kèm lý do, đừng để bấm rồi báo)."""
    h = _h(client)
    _nhan_vien(client, h)

    t = client.get("/api/luong/table", params={"year": L1_NAM, "month": L1_THANG},
                   headers=h).json()
    assert t["chan_chot_ly_do"], "phải nói được VÌ SAO chưa chốt được"
    assert "chưa chốt" in t["chan_chot_ly_do"]
    assert t["period"] is None, "ca đo này cố ý chưa khởi tạo kỳ lương"

    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    t2 = client.get("/api/luong/table", params={"year": L1_NAM, "month": L1_THANG},
                    headers=h).json()
    assert t2["chan_chot_ly_do"] is None


def test_B_thang_truoc_moc_khong_bi_bao_dong_gia(client):
    """Miễn trừ phải NHẤT QUÁN hai bên: máy chủ cho chốt mà màn vẫn hiện băng vàng + nút xám thì
    người dùng kẹt trước một cái chặn không có thật."""
    h = _h(client)
    _nhan_vien(client, h)
    t = client.get("/api/luong/table", params={"year": 2026, "month": 5}, headers=h).json()
    assert t["chan_chot_ly_do"] is None


def test_B_generate_cung_tra_ly_do(client):
    """`POST /generate` trả thẳng bảng mới. Sót cờ ở đây thì vừa bấm Tính lại là băng cảnh báo
    BIẾN MẤT dù công vẫn chưa chốt."""
    h = _h(client)
    _nhan_vien(client, h)
    t = client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                    headers=h).json()
    assert t["chan_chot_ly_do"]


def test_B_giao_dien_that_su_doc_ly_do_nay():
    """Hàng rào chống đúng khuôn sai đã lặp 4 lần vòng này: máy chủ đổi, giao diện quên.

    Cờ có mà màn không đọc thì nút "Chốt" vẫn sáng như cũ — bấm vào ăn 400, không ai biết vì sao."""
    from pathlib import Path

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src"
    client_ts = (fe / "api" / "client.ts").read_text(encoding="utf-8")
    luong = (fe / "pages" / "LuongPage.tsx").read_text(encoding="utf-8")

    assert "chan_chot_ly_do" in client_ts, "kiểu PayrollTable chưa khai trường lý do"
    assert "chan_chot_ly_do" in luong, "màn Lương không đọc lý do từ máy chủ"
    assert "chanChotLyDo" in luong, "màn Lương không giữ lý do vào state"
    assert "busy || Boolean(chanChotLyDo)" in luong, (
        'nút "Chốt" phải bị khoá khi có lý do — không thì bấm vào mới ăn lỗi'
    )


# ══════════════════════════════════════════════ ĐỢT 2 — L3 · L4/L6 · L7


def test_L4_bang_luong_tinh_TRUOC_luc_chot_cong_thi_khong_chot_duoc(client):
    """⭐ Kẽ hở còn lại của L1::

        9h tính lương → 10h chấm bù → 11h chốt công → 12h chốt lương

    Dòng lương lúc 12h VẪN là số của 9h. Chỉ bắt "đã chốt công" là chưa đủ."""
    h = _h(client)
    _nhan_vien(client, h)
    # 1) Tính lương TRƯỚC (kỳ công chưa chốt) — vẫn cho tính, chỉ không cho chốt.
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200
    # 2) Chốt công SAU đó ⇒ ảnh chụp mới hơn bảng lương.
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)

    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code in (400, 409, 422), f"chốt lương trên số đã lạc hậu: {r.text}"
    assert "Tính lại" in r.json()["detail"], "câu báo phải nói rõ phải bấm gì"


def test_L4_tinh_lai_roi_thi_chot_duoc(client):
    """Đối chứng: chặn phải mở ra được đúng bằng hành động nó yêu cầu."""
    h = _h(client)
    _nhan_vien(client, h)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200      # ← Tính lại

    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code == 200, r.text


def test_L6_mo_lai_ky_cong_roi_chot_lai_thi_bat_tinh_lai(client):
    """L6 đi chung đường với L4: mở lại kỳ công XOÁ ảnh chụp, chốt lại sinh ảnh MỚI ⇒ bảng lương
    cũ lại thành lạc hậu. Không có test này thì dễ tưởng L4 chỉ đúng cho lần chốt đầu."""
    h = _h(client)
    _nhan_vien(client, h)
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200
    assert client.post("/api/attendance/period/reopen",
                       json={"year": L1_NAM, "month": L1_THANG}, headers=h).status_code == 200
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)      # chốt lại ⇒ ảnh chụp mới

    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code in (400, 409, 422), f"lọt sau khi chốt lại kỳ công: {r.text}"
    assert "Tính lại" in r.json()["detail"]


def test_L7_nguoi_vao_so_sau_khi_chot_cong_thi_chan_chot_luong(client):
    """Ảnh chụp lấy danh sách NV tại THỜI ĐIỂM chốt. Hồ sơ nhập sau đó không có dòng nào ⇒ 0 công
    ⇒ tháng đó họ mất trắng. Tính lại bao nhiêu lần cũng không sinh thêm dòng vào ảnh chụp —
    đường sửa duy nhất là mở lại rồi chốt lại kỳ công."""
    h = _h(client)
    _nhan_vien(client, h)
    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    # Vào sổ MUỘN cho người đã đi làm cả tháng.
    _nhan_vien(client, h, ten="NV Vao So Muon")
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200

    r = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert r.status_code in (400, 409, 422), f"trả 0 công cho người mới mà vẫn chốt: {r.text}"
    chi_tiet = r.json()["detail"]
    assert "NV Vao So Muon" in chi_tiet, f"phải gọi ĐÍCH DANH ai đang bị 0 công: {chi_tiet}"


def test_L7_khong_bao_dong_gia_voi_nguoi_thang_sau_moi_vao(client):
    """⚠️ Bộ lọc `hire_date` là thứ giữ luật này DÙNG ĐƯỢC.

    HCNS hay nhập trước hồ sơ người sắp vào làm. Họ vắng mặt trong ảnh chụp tháng này là ĐÚNG,
    không phải lỗi — chặn nhầm ở đây là mỗi lần tuyển người mới lại không chốt được lương."""
    h = _h(client)
    _nhan_vien(client, h)
    r = client.post("/api/employees",
                    json={"full_name": "NV Thang Sau Moi Vao",
                          "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": f"{L1_NAM}-{L1_THANG + 1:02d}-01"}, headers=h)
    assert r.status_code in (200, 201), r.text

    _chot_cong(client, h, nam=L1_NAM, thang=L1_THANG)
    assert client.post("/api/luong/generate", json={"year": L1_NAM, "month": L1_THANG},
                       headers=h).status_code == 200
    ok = client.post("/api/luong/lock", json={"year": L1_NAM, "month": L1_THANG}, headers=h)
    assert ok.status_code == 200, f"chặn nhầm vì người THÁNG SAU mới vào: {ok.text}"


def test_L3_cham_cong_sau_khi_chot_thi_bi_danh_dau(client):
    """Chấm công GPS cố ý KHÔNG bị chặn — chặn thợ bấm giờ là họ đứng ở cổng bấm mãi không xong
    (ca đêm qua nửa đêm dính ngay). Bù lại phải ĐÁNH DẤU, nếu không lượt bấm rơi vào khoảng trống:
    ảnh chụp không có, Bảng lương không tính, mà không màn nào nói gì."""
    h = _h(client)
    emp = _nhan_vien(client, h)
    _gan_ca(client, h, emp["id"])
    _chot_cong(client, h)

    st = client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                    headers=h).json()
    assert st["phat_sinh_sau_chot"] == 0, "chưa phát sinh gì mà đã báo"

    # Ghi thẳng một lượt bấm vào tháng ĐÃ CHỐT (mô phỏng đường GPS — đường này KHÔNG bị chặn).
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.repositories.attendance_repo import AttendanceRepository
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=emp["id"], work_location_id=None, check_type="in",
            latitude=None, longitude=None, distance_m=None, within_range=True,
            checked_at=datetime(NAM, THANG, 8, 1, 0, tzinfo=timezone.utc),
        )
    finally:
        db.close()

    st2 = client.get("/api/attendance/period", params={"year": NAM, "month": THANG},
                     headers=h).json()
    assert st2["phat_sinh_sau_chot"] == 1, "lượt bấm sau khi chốt lọt qua không dấu vết"


def test_L3_giao_dien_cham_cong_that_su_doc_co_nay():
    """Cùng hàng rào với bên Lương: máy chủ đổi, giao diện quên — khuôn sai đã lặp 4 lần vòng này."""
    from pathlib import Path

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src"
    assert "phat_sinh_sau_chot" in (fe / "api" / "client.ts").read_text(encoding="utf-8")
    cc = (fe / "pages" / "ChamCongPage.tsx").read_text(encoding="utf-8")
    assert "phat_sinh_sau_chot" in cc, "màn Chấm công không đọc cờ phát sinh sau chốt"
    assert "chốt lại" in cc, "băng cảnh báo phải nói rõ phải làm gì"


def test_migration_0186_chay_lai_khong_vo(client):
    """Migration phải CHẠY LẠI ĐƯỢC: `run_migrations` bỏ qua theo `schema_migrations`, nhưng test
    và các đường vá tay vẫn gọi thẳng. Thêm cột hai lần mà không guard là nổ trên DB thật."""
    from app.db import SessionLocal
    from app.db_migrations import MIGRATIONS

    ten, ham = next(m for m in MIGRATIONS if m[0].startswith("0186_"))
    assert ten == "0186_them_generated_at_cho_ky_luong"
    db = SessionLocal()
    try:
        ham(db)
        ham(db)                      # lần hai: phải im lặng, không nổ
        from sqlalchemy import inspect
        cols = {c["name"] for c in inspect(db.get_bind()).get_columns("payroll_periods")}
        assert "generated_at" in cols
    finally:
        db.close()
