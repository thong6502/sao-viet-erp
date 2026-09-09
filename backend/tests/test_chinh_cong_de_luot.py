"""CHỈNH CÔNG là ĐÈ lượt cũ, không đẻ thêm lượt thứ ba (chủ chốt 09/09/2026).

*"Tổng của nó chỉ 2 cặp chấm vào ra thôi (cặp vào ra) (cặp tăng ca). Thằng nhân viên bấm ra 15h30
mà nó gửi duyệt chỉnh công hoặc hành chính nhân sự chỉnh công bấm ra 17h thì nó ĐÈ 15h30 luôn —
đừng nhầm lẫn giữa tăng ca."*

Trước đó mọi đường chỉnh công (HCNS chấm bù · duyệt đơn của thợ · xác nhận TC theo phiếu) đều
GHI THÊM một lượt, nên ngày ra `VÀO 15:48 · RA 15:49 · RA 17:00`: `pair_sessions` chỉ ghép được
cặp đầu ⇒ CÔNG = 0 (phiên ca chính dài 1 phút) trong khi ô lịch vẫn in 15:48–17:00. Mất công mà
không ai thấy — mà công là tiền.
"""
from __future__ import annotations

from .test_work_shifts_api import _admin_token, _h, _mk_emp, _mk_shift

NAM, THANG = 2026, 6
NGAY = f"{NAM}-{THANG:02d}-08"      # thứ Hai đã qua


def _nv_co_ca(client, token, ten: str) -> int:
    ca = _mk_shift(client, token, f"HC-{ten}", "08:00", "17:30")["id"]
    emp_id = _mk_emp(client, token, ten)["id"]
    r = client.put(f"/api/employees/{emp_id}/shift",
                   json={"default_shift_id": ca, "effective_from": "2026-01-01"},
                   headers=_h(token))
    assert r.status_code in (200, 201), r.text
    return emp_id


def _bam(client, token, emp_id: int, loai: str, gio: str, *, ok: bool = True):
    r = client.post("/api/attendance/adjust", headers=_h(token), json={
        "employee_id": emp_id, "date": NGAY, "check_type": loai, "time": gio,
        "reason": "chỉnh công", "fault_party": "nv_quen"})
    if not ok:
        assert r.status_code == 400, r.text
        return r.json()
    assert r.status_code == 200, r.text
    return r.json()


def _luot(d: dict) -> list[tuple[str, str]]:
    return [(p["check_type"], p["time"]) for p in d["punches"]]


def test_chinh_luot_RA_thi_de_len_luot_RA_cu(client):
    """⭐ Ca chủ bắt: bấm RA 15:49 rồi chỉnh RA 17:00 ⇒ ngày vẫn 2 lượt, công tính đủ."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "De Luot Ra")
    _bam(client, token, emp_id, "in", "15:48")
    _bam(client, token, emp_id, "out", "15:49")
    d = _bam(client, token, emp_id, "out", "17:00")

    assert _luot(d) == [("in", "15:48"), ("out", "17:00")], "lượt RA cũ phải bị ĐÈ, không thêm"
    assert float(d["cong"] or 0) > 0, "phiên ca chính 15:48–17:00 phải ra công"


def test_chinh_luot_VAO_thi_de_len_luot_VAO_cu(client):
    """Chiều ngược lại: đơn xin sửa giờ VÀO cũng đè, không mở phiên mới."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "De Luot Vao")
    _bam(client, token, emp_id, "in", "08:30")
    _bam(client, token, emp_id, "out", "17:30")
    d = _bam(client, token, emp_id, "in", "08:00")

    assert _luot(d) == [("in", "08:00"), ("out", "17:30")]
    assert float(d["cong"] or 0) == 1.0


def test_bam_bu_luot_RA_con_thieu_thi_van_la_luot_moi(client):
    """Ngày treo (chỉ có VÀO) — chấm bù RA là THÊM lượt để đóng phiên, không đè lượt VÀO."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "Bu Luot Ra")
    _bam(client, token, emp_id, "in", "08:00")
    d = _bam(client, token, emp_id, "out", "17:30")

    assert _luot(d) == [("in", "08:00"), ("out", "17:30")]
    assert float(d["cong"] or 0) == 1.0


def test_cap_TANG_CA_la_cap_thu_hai_chu_khong_phai_de(client):
    """*"Đừng nhầm lẫn giữa tăng ca"*: VÀO sau khi đã RA ca chính là MỞ CẶP THỨ HAI."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "Cap Tang Ca")
    _bam(client, token, emp_id, "in", "08:00")
    _bam(client, token, emp_id, "out", "17:30")
    _bam(client, token, emp_id, "in", "18:00")
    d = _bam(client, token, emp_id, "out", "20:00")

    assert _luot(d) == [("in", "08:00"), ("out", "17:30"),
                        ("in", "18:00"), ("out", "20:00")]
    assert float(d["cong"] or 0) == 1.0, "cặp tăng ca không được cướp công ca chính"


def test_chinh_gio_RA_tang_ca_de_dung_luot_cua_cap_tang_ca(client):
    """Có đủ 2 cặp rồi mà chỉnh RA tăng ca ⇒ đè lượt RA của CẶP TĂNG CA, ca chính đứng yên."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "De Ra Tang Ca")
    for loai, gio in (("in", "08:00"), ("out", "17:30"), ("in", "18:00"), ("out", "20:00")):
        _bam(client, token, emp_id, loai, gio)
    d = _bam(client, token, emp_id, "out", "21:00")

    assert _luot(d) == [("in", "08:00"), ("out", "17:30"),
                        ("in", "18:00"), ("out", "21:00")]


def test_luot_thu_nam_bi_chan(client):
    """Một ngày chỉ có 2 cặp. Lượt thứ 5 chỉ đẻ ra lượt lẻ (bị `pair_sessions` bỏ im) ⇒ chặn."""
    token = _admin_token(client)
    emp_id = _nv_co_ca(client, token, "Luot Thu Nam")
    for loai, gio in (("in", "08:00"), ("out", "17:30"), ("in", "18:00"), ("out", "20:00")):
        _bam(client, token, emp_id, loai, gio)
    loi = _bam(client, token, emp_id, "in", "21:00", ok=False)
    assert "2 cặp bấm" in loi["detail"]


def test_ca_dem_chinh_gio_RA_rang_sang_van_de_dung_luot(client):
    """Ca 22:00–06:00: lượt RA rạng sáng thuộc ngày công hôm trước — chỉnh giờ RA phải đè lượt
    RA cũ, không đẻ lượt lẻ ở ngày hôm sau (công ca đêm là tiền, đừng để rơi)."""
    token = _admin_token(client)
    ca = _mk_shift(client, token, "Dem De Luot", "22:00", "06:00", overnight=True)["id"]
    emp_id = _mk_emp(client, token, "Ca Dem De Luot")["id"]
    r = client.put(f"/api/employees/{emp_id}/shift",
                   json={"default_shift_id": ca, "effective_from": "2026-01-01"},
                   headers=_h(token))
    assert r.status_code in (200, 201), r.text

    _bam(client, token, emp_id, "in", "22:00")
    d = client.post("/api/attendance/adjust", headers=_h(token), json={
        "employee_id": emp_id, "date": NGAY, "check_type": "out", "time": "06:00",
        "reason": "ra ca dem", "fault_party": "nv_quen", "next_day": True}).json()
    assert _luot(d) == [("in", "22:00"), ("out", "06:00")]
    assert float(d["cong"] or 0) == 1.0

    # chỉnh lại giờ RA thành 06:30 sáng hôm sau ⇒ ĐÈ, ngày vẫn đúng 2 lượt
    d2 = client.post("/api/attendance/adjust", headers=_h(token), json={
        "employee_id": emp_id, "date": NGAY, "check_type": "out", "time": "06:30",
        "reason": "sua gio ra", "fault_party": "nv_quen", "next_day": True}).json()
    assert _luot(d2) == [("in", "22:00"), ("out", "06:30")]
    assert float(d2["cong"] or 0) == 1.0
