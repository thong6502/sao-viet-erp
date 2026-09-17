"""File Excel bảng lương theo ĐÚNG khuôn `BL CT` của công ty (chủ chốt 17/09/2026).

Chủ đặt thứ tự: Số TT · MNV · Họ và tên · Chức vụ · NCT · CN/Lễ · Tổng NC · Tăng ca · Lương BHXH · Lương
cơ bản · Lương trách nhiệm · các khoản phụ cấp · Chuyên cần · Lương thời gian · Tổng lương · (các khoản
trừ, mình tự xếp) · Thực nhận. Bộ test khoá ba điều:

1. Thứ tự cột đó.
2. File TỰ CỘNG RA: Tổng lương = Σ khối thu; Thực nhận = Tổng lương − Σ khối trừ (bài học 09/09/2026: thiếu
   cột đoàn phí / khoản trừ / lương đợt 1 là kế toán không dò được chênh ở đâu).
3. Nghĩa từng cột y file công ty: mức lương tháng chỉ tham chiếu; "Lương thời gian" gồm phụ cấp theo công +
   phần thêm CN / lễ (`X = (vị trí + trách nhiệm + phụ cấp) ÷ 26 × Tổng NC`); "Ngoài giờ/Tăng ca" chỉ là
   tiền GIỜ tăng ca (`payroll_lines.tien_gio_tang_ca`, mg 0305).

Số viết tay: mức nền 10.400.000 (cơ bản 7.800.000 + trách nhiệm 2.600.000) ⇒ 400.000 đ/công; phụ cấp khác
520.000 ⇒ 20.000 đ/công; công chuẩn 26.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.db import SessionLocal
from app.services.luong_excel import KHONG_TRU, NEN_THU_VIEC, cot_bang_luong, dong_so, xuat_bang_luong


def _khoan(name: str, amount: float, *, kind: str = "thu", source: str = "employee",
           da_de_tay: bool = False):
    return SimpleNamespace(code=name, name=name, kind=kind, amount=amount, source=source,
                           is_taxable=True, note=None, da_de_tay=da_de_tay)


def _dong(**kw):
    """Người công nhật đủ 26 ngày thường + đi làm 1 Chủ nhật + 8 giờ tăng ca ngày thường — khớp engine:

    - Lương theo công 27 công × 400.000 = 10.800.000 · phần thêm CN 400.000 · tiền giờ 50.000 × 8 × 1,5 =
      600.000 ⇒ `ot_pay` 1.000.000.
    - Phụ cấp theo công 28 công (27 + phần thêm 1) × 20.000 = 560.000.
    - Thu 10.800.000 + 560.000 + 1.000.000 + chuyên cần 500.000 + cơm 330.000 = 13.190.000.
    - Trừ BH 819.000 + thuế 100.000 ⇒ thực nhận 12.271.000.
    """
    d = dict(
        employee_id=1, employee_code="NV001", employee_name="Nguyễn Văn A", department_name="Tổ Bế",
        is_probation=False, standard_cong=26.0, actual_cong=27.0, special_cong=1.0, paid_leave_cong=0.0,
        monthly_salary=10_400_000, insurance_base=7_800_000, phu_cap_thang=520_000, cong_phu_cap=28.0,
        luong_cong=10_800_000, luong_ngay_le=0, allowance=560_000, chuyen_can=500_000,
        ot_minutes=480, ot_pay=1_000_000, tien_gio_tang_ca=600_000, off1x_pay=0,
        che_do_khoan=False, la_giao_hang=False, bu_lo_theo_cong=None, lay_bu_lo=False,
        khoan=0, khoan_km=0, hoa_hong=0, dieu_chinh_luong=0, phep_nam=0,
        meal_allowance_pay=300_000, com_tang_ca_pay=30_000, shift_allowance_pay=0, night_premium_pay=0,
        night_pay=0, night_days=0, other_bonus=0, thuong_5s=0, thuong_doanh_so=0, thuong_thanh_tich=0,
        tra_dong_phuc=0, components=[],
        vi_pham=0, di_tre=0, phat_bien_ban=0, dt_vuot_troi=0, phat_5s_dong_phuc=0,
        gross=13_190_000, bhxh=819_000, cong_doan=0, pit=100_000,
        advance_total=0, luong_dot_1_total=0, no_ung_ky_truoc=0, no_ung_chuyen_ky_sau=0,
        net_pay=12_271_000, note=None,
    )
    d.update(kw)
    return SimpleNamespace(**d)


NV = {1: {"chuc_vu": "Thợ bế", "ngay_vao_lam": date(2020, 1, 1), "nguoi_phu_thuoc": 0,
          "luong_vi_tri": 7_800_000, "luong_trach_nhiem": 2_600_000, "phu_cap_khac": 520_000,
          "khoan_ho_so": {}}}


def BH3(ln):
    """Tách tổng BH 10,5% thành 8 / 1,5 / 1 — phần dư dồn BHTN như `_insurance_lines` của router."""
    tong = round(float(ln.bhxh or 0))
    bhxh, bhyt = round(tong * 8 / 10.5), round(tong * 1.5 / 10.5)
    return bhxh, bhyt, tong - bhxh - bhyt


def _so(*lines, nhan_vien=None, ty_le: float = 1.0):
    """Dựng cột + giá trị như file, KIỂM hai đẳng thức, trả {tên cột: số} theo từng dòng."""
    nhan_vien = NV if nhan_vien is None else nhan_vien
    cot = cot_bang_luong(lines, nhan_vien, bh_tach=BH3, ty_le_thu_viec=ty_le)
    ket_qua = []
    for ln in lines:
        g = dong_so(cot, ln, nhan_vien.get(ln.employee_id, {}), BH3(ln), ty_le_thu_viec=ty_le)
        thu = sum(float(g[i] or 0) for i, c in enumerate(cot) if c.nhom == "thu")
        tru = sum(float(g[i] or 0) for i, c in enumerate(cot) if c.nhom == "tru")
        so = {c.ten: g[i] for i, c in enumerate(cot)}
        assert so["Tổng lương"] == round(thu), (so["Tổng lương"], thu)
        assert round(so["Tổng lương"] - tru) == so["Thực nhận"], (so["Tổng lương"] - tru, so["Thực nhận"])
        ket_qua.append(so)
    return ket_qua[0] if len(ket_qua) == 1 else ket_qua


# =============================================================================================
# Thứ tự cột
# =============================================================================================
def test_thu_tu_cot_dung_nhu_chu_dat():
    ten = [c.ten for c in cot_bang_luong([_dong()], NV, bh_tach=BH3)]
    assert ten[:11] == ["Số TT", "MNV", "Họ và tên", "Chức vụ", "NCT", "CN/Lễ", "Tổng NC", "Tăng ca",
                        "Lương BHXH", "Lương cơ bản", "Lương trách nhiệm"]
    i = ten.index
    assert i("Lương trách nhiệm") < i("Phụ cấp khác") < i("Chuyên cần") < i("Lương thời gian") \
        < i("Tổng lương") < i("Thực nhận")
    for tru in ("BHXH", "BHYT", "BHTN", "Công đoàn", "Tạm ứng/Lương đợt 1", "Đi trễ/về sớm", "Thuế TNCN",
                "Phạt biên bản vi phạm", "ĐT vượt trội", "Đồng phục, phạt 5S", "Khoản trừ khác"):
        assert i("Tổng lương") < i(tru) < i("Thực nhận"), tru
    # Thu nhập nằm giữa phụ cấp và Chuyên cần, như file công ty (O → V).
    for thu in ("Phép năm", "Ngoài giờ/Tăng ca", "Lương kinh doanh/Sản lượng", "Cơm/Phụ cấp ca đêm",
                "Thưởng/khoản phát sinh", "Điều chỉnh lương"):
        assert i("Phụ cấp khác") < i(thu) < i("Chuyên cần"), thu
    # Không ai bị phạt vượt trần / nợ ứng ⇒ không đẻ cột thừa.
    assert KHONG_TRU not in ten and "Nợ ứng chuyển kỳ sau" not in ten


# =============================================================================================
# Số của từng cột
# =============================================================================================
def test_dong_cong_nhat_so_viet_tay_va_luong_thoi_gian_nhu_cong_thuc_file():
    so = _so(_dong())
    assert (so["NCT"], so["CN/Lễ"], so["Tổng NC"], so["Tăng ca"]) == (26, 1, 28, 8)
    assert (so["Lương BHXH"], so["Lương cơ bản"], so["Lương trách nhiệm"], so["Phụ cấp khác"]) == \
        (7_800_000, 7_800_000, 2_600_000, 520_000)
    assert so["Ngoài giờ/Tăng ca"] == 600_000, "cột tăng ca chỉ là tiền GIỜ"
    assert so["Cơm/Phụ cấp ca đêm"] == 330_000 and so["Chuyên cần"] == 500_000
    # ⭐ Lương thời gian gồm phụ cấp theo công + phần thêm Chủ nhật — đúng `X = SUM(K:N) ÷ 26 × Tổng NC`.
    assert so["Lương thời gian"] == 11_760_000
    assert so["Lương thời gian"] == (7_800_000 + 2_600_000 + 520_000) / 26 * so["Tổng NC"]
    assert so["Tổng lương"] == 13_190_000 and so["Thực nhận"] == 12_271_000
    assert (so["BHXH"], so["BHYT"], so["BHTN"], so["Thuế TNCN"]) == (624_000, 117_000, 78_000, 100_000)


def test_ky_tinh_truoc_mg_0305_chua_tach_tien_gio_van_cong_dung():
    """Dòng cũ `tien_gio_tang_ca` NULL: công nhật dồn trọn `ot_pay` (trừ off1x) vào cột tăng ca; người
    chế độ khoán thì giờ tăng ca vốn 0đ nên `ot_pay` toàn là phần thêm CN — về Lương thời gian. Kỳ trước
    15/09 chưa chụp `cong_phu_cap` ⇒ Tổng NC = tổng công."""
    cu = _so(_dong(tien_gio_tang_ca=None, cong_phu_cap=None))
    assert cu["Ngoài giờ/Tăng ca"] == 1_000_000 and cu["Lương thời gian"] == 11_360_000
    assert cu["Tổng lương"] == 13_190_000 and cu["Tổng NC"] == 27

    khoan = _so(_dong(tien_gio_tang_ca=None, che_do_khoan=True, ot_pay=400_000, gross=12_590_000,
                      net_pay=11_671_000))
    assert khoan["Ngoài giờ/Tăng ca"] == 0 and khoan["Lương thời gian"] == 11_760_000


def test_LAY_BU_LO_tien_khoan_nam_trong_luong_thoi_gian_tong_nc_gom_cong_bu_lo():
    """⭐ Thợ khoán tháng lấy bù lỗ (chủ 16/09/2026: đã lấy bù lỗ thì không hiện khoán nữa).

    Mức nền 7.200.000 + phụ cấp 520.000 ⇒ 296.923,08 đ/công. Đi làm 26,5 công (3 Chủ nhật) ⇒ bù lỗ
    7.868.462; khoán 5.000.000 ⇒ phần bù thêm 2.868.462. Phần thêm 3 CN 830.769 + phụ cấp 3 công 60.000.
    Lương thời gian = 7.868.462 + 60.000 + 830.769 = 8.759.231 · Tổng NC = 3 + 26,5 = 29,5."""
    tho = _dong(monthly_salary=7_200_000, insurance_base=0, phu_cap_thang=520_000, cong_phu_cap=3,
                actual_cong=26.5, special_cong=3, luong_cong=2_868_462, khoan=5_000_000, allowance=60_000,
                bu_lo_theo_cong=7_868_462, lay_bu_lo=True, che_do_khoan=True, ot_minutes=0,
                ot_pay=830_769, tien_gio_tang_ca=0, chuyen_can=0, meal_allowance_pay=0, com_tang_ca_pay=0,
                gross=8_759_231, bhxh=0, pit=0, net_pay=8_759_231)
    nv = {1: {**NV[1], "luong_vi_tri": 4_800_000, "luong_trach_nhiem": 2_400_000}}
    so = _so(tho, nhan_vien=nv)
    assert so["Lương kinh doanh/Sản lượng"] == 0, "lấy bù lỗ mà vẫn in tiền khoán = kế toán đọc cộng dồn"
    assert so["Lương thời gian"] == 8_759_231
    assert so["Tổng NC"] == 29.5

    # Thử việc (luôn lấy bù lỗ, nền × 80%): (5.760.000 + 520.000) ÷ 26 × 26 công = 6.280.000.
    tv = _dong(is_probation=True, monthly_salary=7_200_000, insurance_base=0, phu_cap_thang=520_000,
               cong_phu_cap=0, actual_cong=26, special_cong=0, luong_cong=6_280_000, allowance=0,
               bu_lo_theo_cong=6_280_000, lay_bu_lo=True, che_do_khoan=True, ot_minutes=0, ot_pay=0,
               tien_gio_tang_ca=0, chuyen_can=0, meal_allowance_pay=0, com_tang_ca_pay=0,
               gross=6_280_000, bhxh=0, pit=0, net_pay=6_280_000)
    assert _so(tv, nhan_vien=nv, ty_le=0.8)["Tổng NC"] == 26


def test_LAY_KHOAN_san_luong_cot_rieng_luong_thoi_gian_chi_con_le_va_chu_nhat():
    """Tháng tiền khoán cao hơn: sản lượng ở cột riêng (gộp hoa hồng như cột Q của file); Lương thời gian chỉ
    còn 2 công lễ nghỉ + phần thêm 3 Chủ nhật — đúng `Tổng NC = CN × 1 + lễ` của người sản lượng."""
    tho = _dong(monthly_salary=7_200_000, insurance_base=0, phu_cap_thang=520_000, cong_phu_cap=5,
                actual_cong=26, special_cong=3, luong_cong=0, khoan=20_000_000, hoa_hong=150_000,
                luong_ngay_le=553_846, allowance=100_000, bu_lo_theo_cong=6_646_154, lay_bu_lo=False,
                che_do_khoan=True, ot_minutes=0, ot_pay=830_769, tien_gio_tang_ca=0, chuyen_can=0,
                meal_allowance_pay=0, com_tang_ca_pay=0,
                gross=21_634_615, bhxh=0, pit=0, net_pay=21_634_615)
    so = _so(tho)
    assert so["Lương kinh doanh/Sản lượng"] == 20_150_000
    assert so["Lương thời gian"] == 1_484_615 and so["Tổng NC"] == 5


def test_phat_vuot_tran_30_phan_tram_hien_cot_khong_tru_duoc():
    """Phạt ghi nhận 5.000.000 nhưng trần Điều 102 chỉ cho trừ 1.000.000: cột phạt in số GHI NHẬN, cột
    "Không trừ được kỳ này" −4.000.000 để file vẫn cộng ra đúng thực nhận. Người không bị phạt: 0."""
    phat = _dong(employee_id=2, vi_pham=5_000_000, gross=12_190_000, net_pay=11_271_000)
    thuong, bi_phat = _so(_dong(), phat, nhan_vien={**NV, 2: NV[1]})
    assert bi_phat["Phạt biên bản vi phạm"] == 5_000_000
    assert bi_phat[KHONG_TRU] == -4_000_000 and thuong[KHONG_TRU] == 0
    assert bi_phat["Tổng lương"] == 13_190_000, "Tổng lương là tổng thu TRƯỚC phạt, như file công ty"


def test_khau_tru_lon_hon_luong_con_lai_khong_tru_duoc():
    """Tháng ít công: BH 819.000 + khoản trừ 500.000 > tổng lương 1.000.000 ⇒ engine để thực nhận 0."""
    so = _so(_dong(luong_cong=1_000_000, allowance=0, ot_pay=0, tien_gio_tang_ca=0, chuyen_can=0,
                   meal_allowance_pay=0, com_tang_ca_pay=0, gross=1_000_000, pit=0,
                   components=[_khoan("Mua đồng phục", 500_000, kind="tru")], net_pay=0))
    assert so["Khoản trừ khác"] == 500_000 and so[KHONG_TRU] == -319_000


def test_tam_ung_luong_dot_1_no_ky_truoc_tru_ky_nay():
    so = _so(_dong(advance_total=2_000_000, luong_dot_1_total=3_000_000, no_ung_ky_truoc=1_000_000,
                   net_pay=6_271_000))
    assert so["Tạm ứng/Lương đợt 1"] == 6_000_000

    # Ứng vượt lương: trừ được 12.271.000, phần dư 7.729.000 chuyển kỳ sau — cột phụ, KHÔNG trừ.
    vuot = _so(_dong(advance_total=20_000_000, no_ung_chuyen_ky_sau=7_729_000, net_pay=0))
    assert vuot["Tạm ứng/Lương đợt 1"] == 12_271_000 and vuot["Nợ ứng chuyển kỳ sau"] == 7_729_000


def test_phu_cap_tung_khoan_la_muc_thang():
    """Khoản hồ sơ chụp SỐ TRẢ theo công ⇒ chia ngược ra mức tháng: 280.000 × 26 ÷ 28 = 260.000. Tháng
    lấy bù lỗ không có công hưởng ⇒ đọc mức đang gán ở hồ sơ. Khoản phát sinh kỳ này KHÔNG thành cột phụ cấp
    (nó là tiền thật, nằm ở cột thưởng)."""
    ln = _dong(phu_cap_thang=780_000, allowance=840_000, gross=13_470_000, net_pay=12_551_000,
               components=[_khoan("Phụ cấp xăng xe", 280_000),
                           _khoan("Thưởng nóng", 0, source="line"),
                           _khoan("Trang phục", 0)])
    so = _so(ln)
    assert so["Phụ cấp khác"] == 520_000 and so["Phụ cấp xăng xe"] == 260_000
    assert "Thưởng nóng" not in so and "Trang phục" not in so, "khoản 0đ / phát sinh không đẻ cột phụ cấp"

    bu_lo = _dong(employee_id=3, cong_phu_cap=0, phu_cap_thang=780_000,
                  components=[_khoan("Phụ cấp xăng xe", 0)])
    nv = {3: {**NV[1], "khoan_ho_so": {"Phụ cấp xăng xe": 260_000}}}
    cot = cot_bang_luong([bu_lo], nv, bh_tach=BH3)
    g = dong_so(cot, bu_lo, nv[3], BH3(bu_lo))
    assert g[[c.ten for c in cot].index("Phụ cấp xăng xe")] == 260_000


def test_chia_nguoc_sat_muc_ho_so_thi_lay_dung_muc_ho_so():
    """Bắt được trên DB dev kỳ 09/2026 (NV002): `cong_phu_cap` lưu 7,38 công, số trả 56.769 ⇒ chia ngược ra
    199.999 và "Phụ cấp khác" hiện 3đ. Sát mức hồ sơ trong sai số làm tròn thì lấy đúng mức hồ sơ; hồ sơ đã
    đổi hẳn thì giữ số chia ngược."""
    ln = _dong(cong_phu_cap=7.38, phu_cap_thang=600_000,
               components=[_khoan("Hỗ trợ đi lại", 56_769), _khoan("Phụ cấp xăng xe", 56_769),
                           _khoan("Thu nhập khác", 56_769)])
    nv = {1: {**NV[1], "phu_cap_khac": 0,
              "khoan_ho_so": {"Hỗ trợ đi lại": 200_000, "Phụ cấp xăng xe": 200_000, "Thu nhập khác": 150_000}}}
    cot = cot_bang_luong([ln], nv, bh_tach=BH3)
    so = dict(zip([c.ten for c in cot], dong_so(cot, ln, nv[1], BH3(ln))))
    assert so["Hỗ trợ đi lại"] == 200_000 and so["Phụ cấp xăng xe"] == 200_000
    assert so["Thu nhập khác"] == 199_999, "hồ sơ đã đổi sang 150.000 ⇒ kỳ này vẫn là mức cũ chia ngược"
    assert so["Phụ cấp khác"] == 0, "lệch 1đ làm tròn không được hiện thành phụ cấp khác"


def test_lech_lam_tron_vai_dong_don_vao_luong_thoi_gian():
    """Mỗi khoản làm tròn riêng, `gross` làm tròn một lần ⇒ các cột thu cộng lệch 1đ. Dồn vào Lương thời gian
    để Tổng lương bằng đúng gross, và KHÔNG đẻ cột "Không trừ được kỳ này" chỉ vì 1đ."""
    so = _so(_dong(luong_cong=10_800_001))
    assert so["Tổng lương"] == 13_190_000 and so["Lương thời gian"] == 11_760_000
    assert KHONG_TRU not in so


def test_muc_luong_lech_so_da_chup_thi_theo_so_da_chup():
    """Mốc lương sửa SAU khi tính (hoặc dữ liệu cũ khai một số tổng): cơ bản + trách nhiệm phải bằng mức nền
    đã chụp trên dòng lương, không thì cột mức tháng nói một đằng tiền một nẻo."""
    nv = {1: {**NV[1], "luong_vi_tri": 5_000_000, "luong_trach_nhiem": 2_000_000}}
    so = _so(_dong(), nhan_vien=nv)
    assert (so["Lương cơ bản"], so["Lương trách nhiệm"]) == (10_400_000, 0)


# =============================================================================================
# Khuôn file
# =============================================================================================
def test_file_ba_sheet_tieu_de_dong_4_to_vang_thu_viec_dong_tong():
    tv = _dong(employee_id=2, employee_code="NV002", employee_name="Trần Thị B", is_probation=True)
    wb = load_workbook(BytesIO(xuat_bang_luong(
        [_dong(), tv], nam=2026, thang=5, nhan_vien={**NV, 2: NV[1]}, bh_tach=BH3, ty_le_thu_viec=0.8,
        tam_ung=[{"employee_id": 1, "ngay": date(2026, 5, 20), "so_tien": 2_000_000, "loai": "tam_ung"}])))
    assert wb.sheetnames == ["Bang luong 05-2026", "Ky nhan", "Tam ung"]

    ws = wb["Bang luong 05-2026"]
    assert ws["A1"].value == "BẢNG THANH TOÁN LƯƠNG NHÂN VIÊN"
    head = [c.value for c in ws[4]]
    assert head[:4] == ["Số TT", "MNV", "Họ và tên", "Chức vụ"] and "Ngày ca đêm" in head
    assert ws.cell(row=5, column=1).value == 1 and ws.cell(row=5, column=4).value == "Thợ bế"
    assert ws.cell(row=5, column=head.index("Lương thời gian") + 1).value == 11_760_000
    # Dòng thử việc tô vàng như bảng công ty; dòng chính thức không.
    assert ws.cell(row=6, column=2).fill.fgColor.rgb == NEN_THU_VIEC
    assert ws.cell(row=5, column=2).fill.fgColor.rgb != NEN_THU_VIEC
    assert ws.cell(row=7, column=3).value == "Tổng cộng"
    chu = head.index("Tổng lương") + 1
    assert ws.cell(row=7, column=chu).value.startswith("=SUM(")
    assert any("Nền vàng" in str(c.value) for c in ws["C"] if c.value)
    assert ws.freeze_panes == "E5"

    ky = wb["Ky nhan"]
    assert [c.value for c in ky[3]][:6] == ["STT", "Mã NV", "Họ và tên", "Chức vụ", "Bộ phận", "Thực nhận"]
    assert "20/05" in [c.value for c in wb["Tam ung"][3]]


def test_bang_rong_van_xuat_duoc():
    wb = load_workbook(BytesIO(xuat_bang_luong([], nam=2026, thang=5, nhan_vien={}, bh_tach=BH3,
                                               tam_ung=[])))
    assert len(wb.sheetnames) == 3


def test_api_phoi_du_moi_cot_file_xuat_can():
    """⭐ Bẫy đã cắn 09/09/2026: cột có trong DB nhưng `LineOut` KHÔNG phơi ⇒ bộ xuất đọc `getattr(…, 0)`
    ra 0 mà không báo. Kiểu hỏng này IM LẶNG nên khoá bằng test."""
    from app.schemas.payroll import LineOut

    can = {"actual_cong", "standard_cong", "special_cong", "monthly_salary", "insurance_base", "luong_cong",
           "luong_ngay_le", "phu_cap_thang", "cong_phu_cap", "bu_lo_theo_cong", "lay_bu_lo", "che_do_khoan",
           "la_giao_hang", "is_probation", "tien_gio_tang_ca", "off1x_pay", "dieu_chinh_luong", "chuyen_can",
           "allowance", "ot_minutes", "ot_pay", "night_pay", "night_premium_pay", "night_days",
           "meal_allowance_pay", "com_tang_ca_pay", "shift_allowance_pay", "khoan", "khoan_km", "hoa_hong",
           "thuong_thanh_tich", "thuong_doanh_so", "thuong_5s", "tra_dong_phuc", "phep_nam", "other_bonus",
           "vi_pham", "di_tre", "phat_bien_ban", "dt_vuot_troi", "phat_5s_dong_phuc", "gross", "bhxh",
           "cong_doan", "pit", "advance_total", "luong_dot_1_total", "no_ung_ky_truoc",
           "no_ung_chuyen_ky_sau", "net_pay", "components", "note"}
    thieu = sorted(can - set(LineOut.model_fields))
    assert not thieu, f"LineOut thiếu {thieu} ⇒ cột tương ứng trong file xuất sẽ ra 0 mà không báo"


# =============================================================================================
# Engine chụp tiền giờ tăng ca · luồng thật qua API
# =============================================================================================
def test_ENGINE_chup_tien_gio_tang_ca_tach_khoi_phan_them_chu_nhat(client):
    """Lương 26tr ⇒ 1.000.000 đ/công · 125.000 đ/giờ. Đi làm 1 Chủ nhật + 4 giờ tăng ca ngày thường:

    - Tổ thường: tiền giờ 125.000 × 4 × 1,5 = 750.000; `ot_pay` = 750.000 + phần thêm CN 1.000.000.
    - Chế độ khoán: tiền giờ 0, `ot_pay` chỉ còn phần thêm CN.
    - Tài xế tháng lấy vế thời gian: trả đủ tiền giờ (PRD bù lỗ §00.10)."""
    client
    from tests.test_khoan_khong_tien_tang_ca import _svc, _tinh

    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        cn = dict(actual_cong=27, restday_cong=1, ot_minutes=240)
        thuong = _tinh(svc, params, **cn, che_do_khoan=False)
        assert thuong["tien_gio_tang_ca"] == 750_000
        assert thuong["ot_pay"] - thuong["tien_gio_tang_ca"] == 1_000_000

        khoan = _tinh(svc, params, **cn, che_do_khoan=True)
        assert khoan["tien_gio_tang_ca"] == 0 and khoan["ot_pay"] == 1_000_000

        tai_xe = _tinh(svc, params, **cn, che_do_khoan=True, chi_an_km=True, khoan_km=0)
        assert tai_xe["lay_bu_lo"] is True and tai_xe["tien_gio_tang_ca"] == 750_000
    finally:
        db.close()


def test_XUAT_EXCEL_qua_API_theo_khuon_cong_ty(client):
    """⭐ Luồng thật: khai mốc lương tách cơ bản / trách nhiệm / phụ cấp + một khoản hồ sơ, chấm 1 ngày
    thường có 2 giờ tăng ca + 1 Chủ nhật, Tính lại, tải file. Cột mức tháng ra đúng mốc; cột tiền khớp dòng
    lương; file tự cộng ra Tổng lương và Thực nhận."""
    from tests.test_com_tang_ca import (
        NAM, THANG, _ca_hanh_chinh, _h, _lam_ngay, _ngay_lam_viec, _ngay_nghi, _nv, _phieu_tang_ca,
    )
    from tests.test_khoan_khong_tien_tang_ca import (
        _chinh_thuc, _dong as _dong_bang, _khai_com_tc_va_tat_khop_ca, _tinh_lai,
    )

    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    eid = _nv(client, h, ten="NV Excel khuôn công ty")
    _chinh_thuc(client, h, eid)
    r = client.post(f"/api/luong/salaries/{eid}",
                    json={"effective_from": "2026-02-01", "luong_vi_tri": 7_800_000,
                          "luong_trach_nhiem": 2_600_000, "allowance": 520_000,
                          "insurance_base": 7_800_000}, headers=h)
    assert r.status_code in (200, 201), r.text
    r = client.post("/api/luong/components", json={"name": "Phụ cấp xăng thử Excel", "kind": "thu",
                                                   "is_taxable": True}, headers=h)
    assert r.status_code == 201, r.text
    r = client.put(f"/api/luong/components/employee/{eid}",
                   json={"items": [{"component_id": r.json()["id"], "amount": 260_000}]}, headers=h)
    assert r.status_code == 200, r.text
    _ca_hanh_chinh(client, h, eid)
    ngay = _ngay_lam_viec(client, h)[2]
    _lam_ngay(client, h, eid, ngay, ot_gio=2)
    _phieu_tang_ca(client, h, eid, ngay)
    _lam_ngay(client, h, eid, _ngay_nghi(client, h)[1])
    d = _dong_bang(_tinh_lai(client, h), eid)
    assert d["tien_gio_tang_ca"] > 0 and d["special_cong"] >= 1, d

    r = client.get(f"/api/luong/export.xlsx?year={NAM}&month={THANG}", headers=h)
    assert r.status_code == 200, r.text
    ws = load_workbook(BytesIO(r.content))[f"Bang luong {THANG:02d}-{NAM}"]
    head = [c.value for c in ws[4]]
    row = next(x for x in ws.iter_rows(min_row=5, values_only=True) if x[2] == "NV Excel khuôn công ty")
    lay = lambda ten: float(row[head.index(ten)] or 0)      # noqa: E731

    assert (lay("Lương cơ bản"), lay("Lương trách nhiệm"), lay("Phụ cấp khác")) == \
        (7_800_000, 2_600_000, 520_000)
    assert lay("Phụ cấp xăng thử Excel") == 260_000
    assert lay("CN/Lễ") == d["special_cong"] and lay("Tổng NC") == d["cong_phu_cap"]
    assert lay("Ngoài giờ/Tăng ca") == d["tien_gio_tang_ca"]
    # Lệch làm tròn (≤ 10đ) được dồn vào cột này — xem `LECH_LAM_TRON`.
    assert abs(lay("Lương thời gian") - (d["luong_cong"] + d["luong_ngay_le"] + d["allowance"]
                                         + d["ot_pay"] - d["tien_gio_tang_ca"])) <= 10
    assert lay("Tổng lương") == d["gross"], "không phạt ⇒ Tổng lương bằng gross"
    assert lay("Thực nhận") == d["net_pay"]
    tru = sum(lay(t) for t in ("BHXH", "BHYT", "BHTN", "Công đoàn", "Tạm ứng/Lương đợt 1", "Đi trễ/về sớm",
                               "Thuế TNCN", "Phạt biên bản vi phạm", "ĐT vượt trội", "Đồng phục, phạt 5S",
                               "Khoản trừ khác"))
    assert lay("Tổng lương") - tru == lay("Thực nhận")
