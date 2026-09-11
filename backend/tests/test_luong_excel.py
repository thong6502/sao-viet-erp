"""File xuất bảng lương phải TỰ CỘNG RA ĐƯỢC Thực nhận (chủ chốt 09/09/2026).

Bản cũ chỉ có Tổng · BHXH · TNCN · Tạm ứng nên thiếu **đoàn phí công đoàn**, **khoản trừ danh mục**
và **lương đợt 1**: kế toán lấy các cột trong file cộng trừ thì không ra Thực nhận, và không dò
được chênh ở đâu. Bộ test này khoá đúng hai đẳng thức đó, cộng danh sách cột theo khuôn bảng lương
công ty đang dùng (đối chiếu file `BẢNG LƯƠNG T05.2026 (duyệt).xlsx`).
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.luong_excel import COT, dong_so, xuat_bang_luong


def _khoan(code: str, amount: float, *, kind: str = "thu", source: str = "employee"):
    return SimpleNamespace(code=code, name=code, kind=kind, amount=amount, source=source,
                           is_taxable=True, note=None)


def _dong(**kw):
    """Một dòng lương đủ trường, mặc định KHỚP: cộng thu − phạt = gross; gross − trừ = net."""
    d = dict(
        employee_id=1, employee_code="NV001", employee_name="Nguyễn Văn A",
        department_name="Tổ In", is_probation=False,
        actual_cong=26.0, standard_cong=26.0, special_cong=2.0, paid_leave_cong=1.0,
        monthly_salary=10_000_000, insurance_base=10_000_000,
        luong_cong=10_000_000, luong_ngay_phep=384_615, dieu_chinh_luong=0, chuyen_can=500_000,
        allowance=1_000_000, phu_cap_tham_nien=0,
        ot_pay=1_200_000, night_pay=0, night_premium_pay=0, meal_allowance_pay=300_000,
        com_tang_ca_pay=0, shift_allowance_pay=0, khoan=0, khoan_km=0, thuong_to_truong=0,
        hoa_hong=0, thuong_thanh_tich=0, thuong_doanh_so=0, thuong_5s=0, tra_dong_phuc=0,
        phep_nam=0, other_bonus=0, components=[],
        vi_pham=0, di_tre=0, phat_bien_ban=0, dt_vuot_troi=0, phat_5s_dong_phuc=0,
        ot_minutes=600, night_days=0,
        gross=13_000_000, bhxh=1_050_000, cong_doan=50_000, pit=200_000,
        pit_taxable=0, thu_nhap_chiu_thue=0,
        advance_total=0, luong_dot_1_total=0, no_ung_ky_truoc=0, no_ung_chuyen_ky_sau=0,
        net_pay=11_700_000, note=None,
    )
    d.update(kw)
    return SimpleNamespace(**d)


NV = {1: {"chuc_vu": "Thợ in", "ngay_vao_lam": date(2020, 1, 1), "nguoi_phu_thuoc": 2}}
BH3 = lambda ln: (800_000, 150_000, 100_000)   # noqa: E731 — cộng đúng 1.050.000


def _cot(ten: str) -> int:
    return next(i for i, c in enumerate(COT) if c[0] == ten)


def _so(gia_tri, ten: str) -> float:
    return float(gia_tri[_cot(ten)] or 0)


# --- hai đẳng thức phải luôn đúng -------------------------------------------


def _kiem_dang_thuc(ln, nv=None):
    gia_tri = dong_so(ln, nv or NV[1], BH3(ln))
    assert _so(gia_tri, "CỘNG THU") - _so(gia_tri, "Phạt/trừ thực tế") == _so(gia_tri, "TỔNG LƯƠNG")
    con_lai = (_so(gia_tri, "TỔNG LƯƠNG")
               - _so(gia_tri, "BHXH") - _so(gia_tri, "BHYT") - _so(gia_tri, "BHTN")
               - _so(gia_tri, "Đoàn phí công đoàn") - _so(gia_tri, "Thuế TNCN")
               - _so(gia_tri, "Khoản trừ danh mục") - _so(gia_tri, "Tạm ứng trừ kỳ này"))
    assert con_lai == _so(gia_tri, "THỰC NHẬN"), (con_lai, _so(gia_tri, "THỰC NHẬN"))
    return gia_tri


def test_dong_thuong_cong_ra_dung_thuc_nhan():
    _kiem_dang_thuc(_dong())


def test_co_doan_phi_van_cong_dung():
    """⭐ Ca làm vỡ bản cũ: đoàn viên công đoàn — file cũ không có cột đoàn phí nên lệch đúng
    bằng số đó."""
    gia_tri = _kiem_dang_thuc(_dong(cong_doan=52_480, net_pay=11_697_520))
    assert _so(gia_tri, "Đoàn phí công đoàn") == 52_480


def test_co_khoan_tru_danh_muc_van_cong_dung():
    """Khoản danh mục loại TRỪ (mua đồng phục…) trừ thẳng vào thực nhận, file cũ cũng không có."""
    gia_tri = _kiem_dang_thuc(_dong(
        components=[_khoan("dong_phuc", 200_000, kind="tru")], net_pay=11_500_000))
    assert _so(gia_tri, "Khoản trừ danh mục") == 200_000


def test_luong_dot_1_va_no_ky_truoc_van_cong_dung():
    """Trừ tạm ứng + đợt 1 + nợ kỳ trước; phần chưa trừ hết chuyển kỳ sau, KHÔNG được đếm vào."""
    gia_tri = _kiem_dang_thuc(_dong(
        advance_total=2_000_000, luong_dot_1_total=3_000_000, no_ung_ky_truoc=1_000_000,
        no_ung_chuyen_ky_sau=0, net_pay=5_700_000))
    assert _so(gia_tri, "Tạm ứng trừ kỳ này") == 6_000_000

    # Ứng vượt lương: thực nhận 0, phần dư chuyển kỳ sau và KHÔNG nằm trong "đã trừ kỳ này".
    gia_tri = _kiem_dang_thuc(_dong(
        advance_total=20_000_000, no_ung_chuyen_ky_sau=8_300_000, net_pay=0))
    assert _so(gia_tri, "Tạm ứng trừ kỳ này") == 11_700_000


def test_thuong_gop_ba_khoan_da_bo_cot(client=None):
    """Ba cột đã bỏ vẫn phải nằm TRONG cột "Thưởng" — bỏ cột mà quên cộng là mất tiền của NV."""
    ln = _dong(other_bonus=100_000, thuong_5s=200_000, tra_dong_phuc=300_000, phep_nam=400_000,
               gross=14_000_000, net_pay=12_700_000)
    gia_tri = _kiem_dang_thuc(ln)
    assert _so(gia_tri, "Thưởng") == 1_000_000


def test_khoan_phat_sinh_nam_trong_cong_thu():
    """Khoản phát sinh (thưởng nóng, nguồn `line`) cộng vào gross ⇒ phải có cột riêng, còn khoản
    gán ở hồ sơ thì KHÔNG (đã nằm trong Phụ cấp) — cộng cả hai là đếm đôi."""
    ln = _dong(components=[_khoan("thuong_nong", 500_000, source="line"),
                           _khoan("com", 300_000, source="employee")],
               gross=13_500_000, net_pay=12_200_000)
    gia_tri = _kiem_dang_thuc(ln)
    assert _so(gia_tri, "Khoản phát sinh") == 500_000


def test_phat_bi_tran_30_phan_tram_van_cong_dung():
    """Phạt ghi nhận 5.000.000 nhưng trần Điều 102 chỉ cho trừ 1.000.000 ⇒ cột "Phạt/trừ thực tế"
    phải là số THỰC TRỪ, không phải tổng ghi nhận."""
    gia_tri = _kiem_dang_thuc(_dong(vi_pham=5_000_000, gross=12_000_000, net_pay=10_700_000))
    assert _so(gia_tri, "Vi phạm") == 5_000_000
    assert _so(gia_tri, "Phạt/trừ thực tế") == 1_000_000


def test_cong_tach_ba_loai_va_cong_lai_dung_tong():
    gia_tri = dong_so(_dong(actual_cong=26, special_cong=2, paid_leave_cong=1), NV[1], BH3(None))
    assert _so(gia_tri, "Công ngày thường") == 23
    assert (_so(gia_tri, "Công ngày thường") + _so(gia_tri, "Công lễ/CN")
            + _so(gia_tri, "Công phép")) == _so(gia_tri, "Tổng công")


# --- khuôn file -------------------------------------------------------------


def test_file_du_ba_sheet_va_cac_cot_ke_toan_can():
    wb = load_workbook(BytesIO(xuat_bang_luong(
        [_dong(), _dong(employee_id=1, employee_code="NV002", employee_name="Trần Thị B")],
        nam=2026, thang=5, nhan_vien=NV, bh_tach=BH3,
        tam_ung=[{"employee_id": 1, "ngay": date(2026, 5, 20), "so_tien": 2_000_000,
                  "loai": "tam_ung"}])))
    assert wb.sheetnames == ["Bang luong 05-2026", "Ky nhan", "Tam ung"]

    ws = wb["Bang luong 05-2026"]
    tieu_de = [c.value for c in ws[4]]
    for ten in ("Chức vụ", "Ngày vào làm", "Mức lương tháng", "Lương đóng BHXH",
                "Công ngày thường", "Công lễ/CN", "BHXH", "BHYT", "BHTN",
                "Đoàn phí công đoàn", "Khoản trừ danh mục", "Lương đợt 1",
                "Thưởng thành tích", "Thưởng doanh số", "Thưởng",
                "Đi trễ/về sớm", "Phạt biên bản", "ĐT vượt trội", "Đồng phục/5S",
                "THỰC NHẬN", "Người phụ thuộc"):
        assert ten in tieu_de, ten
    assert ws.cell(row=5, column=1).value == 1                       # STT
    assert ws.cell(row=5, column=_cot("Chức vụ") + 1).value == "Thợ in"
    assert ws.cell(row=7, column=1).value == "TỔNG"                  # 2 dòng + dòng tổng

    ky = wb["Ky nhan"]
    assert [c.value for c in ky[3]][:6] == ["STT", "Mã NV", "Họ và tên", "Chức vụ", "Bộ phận",
                                            "Thực nhận"]
    # Chủ bỏ 3 cột này 09/09/2026 — gộp vào "Thưởng", đừng dựng lại.
    for ten in ("Thưởng 5S", "Trả đồng phục", "Phép năm"):
        assert ten not in tieu_de, ten

    tu = wb["Tam ung"]
    assert "20/05" in [c.value for c in tu[3]]


def test_api_phoi_du_moi_cot_file_xuat_can():
    """⭐ Bẫy đã cắn 09/09/2026: cột `special_cong` có trong DB nhưng `LineOut` KHÔNG phơi ⇒ bộ
    xuất đọc `getattr(ln, "special_cong", 0)` ra 0, file in "Công lễ/CN = 0" trong khi dòng lương
    có 1,94 công. Kiểu hỏng này IM LẶNG (không lỗi, chỉ sai số), nên khoá bằng test."""
    from app.schemas.payroll import LineOut

    can = {"actual_cong", "standard_cong", "special_cong", "paid_leave_cong", "monthly_salary",
           "insurance_base", "luong_cong", "dieu_chinh_luong", "chuyen_can", "allowance",
           "ot_pay", "night_pay", "night_premium_pay", "meal_allowance_pay", "com_tang_ca_pay",
           "shift_allowance_pay", "khoan", "khoan_km", "thuong_to_truong", "hoa_hong",
           "thuong_thanh_tich", "thuong_doanh_so", "thuong_5s", "tra_dong_phuc", "phep_nam",
           "other_bonus", "vi_pham", "di_tre", "phat_bien_ban", "dt_vuot_troi",
           "phat_5s_dong_phuc", "gross", "bhxh", "cong_doan", "pit", "advance_total",
           "luong_dot_1_total", "no_ung_ky_truoc", "no_ung_chuyen_ky_sau", "net_pay",
           "luong_ngay_phep", "phu_cap_tham_nien", "thu_nhap_chiu_thue", "pit_taxable",
           "ot_minutes", "night_days", "components"}
    thieu = sorted(can - set(LineOut.model_fields))
    assert not thieu, f"LineOut thiếu {thieu} ⇒ cột tương ứng trong file xuất sẽ ra 0 mà không báo"


def test_bang_rong_van_xuat_duoc():
    wb = load_workbook(BytesIO(xuat_bang_luong([], nam=2026, thang=5, nhan_vien={},
                                               bh_tach=BH3, tam_ung=[])))
    assert len(wb.sheetnames) == 3
