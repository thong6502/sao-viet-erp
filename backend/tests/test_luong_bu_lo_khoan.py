"""LƯƠNG BÙ LỖ cho tổ khoán sản xuất (+ tài xế chỉ ăn km) — `docs/prd-luong-bu-lo-khoan-san-xuat.md` (14–15/09/2026).

Khách xác nhận: *"lương cơ bản + lương vị trí cũng được gọi là lương bù lỗ. Nếu lương khoán sản lượng
mà lớn hơn lương bù lỗ thì lấy lương khoán làm chính, còn bé hơn thì lấy lương bù lỗ. Nhưng đóng bảo
hiểm thì vẫn theo mức lương bù lỗ."* Các câu chủ chốt được test ở đây:

1. Bù lỗ = Lương cơ bản + trách nhiệm + PHỤ CẤP, chia theo công đi làm (khách chốt 15/09/2026 chiều —
   ĐẢO câu 1 "chỉ cơ bản + trách nhiệm"; công lễ nghỉ, công phép có lương KHÔNG đếm).
2–3. Cuối tháng lấy MAX(tiền khoán, bù lỗ theo công) theo từng người — THAY NHAU, không cộng dồn.
4. Làm CN: 1 công nằm trong phần so, phần thêm theo ĐƠN GIÁ BÙ LỖ (cơ bản + trách nhiệm).
5. Bảo hiểm luôn trên cơ bản + trách nhiệm — khoán cao bao nhiêu cũng không đổi.
9. Nghỉ không phép: chỉ bù lỗ bị chia theo công.
10. Phụ cấp khoán hay bù lỗ đều ăn.
Chốt họp khách 15/09/2026 chiều (PRD §00): lễ đi làm 300% (không phải 400%) · lễ rơi đúng Chủ nhật 500% ·
tài xế + phụ xe CÓ bù lỗ như thợ khoán · tổ in không có công gốc ngày CN / lễ · người khoán không dùng
nghỉ phép có lương.

Cách ghi lên dòng lương: `luong_cong` = PHẦN BÙ THÊM cho đủ bù lỗ (0 khi khoán cao hơn), nên
`luong_cong + khoan` = MAX và "Sửa 1 ô" / file xuất / tổng bảng không phải biết luật này.
Số viết tay theo Nguyễn Tuấn Kiệt (bế) bảng lương T05/2026: cơ bản 4,8tr + trách nhiệm 2,4tr.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.db import SessionLocal
from app.services.piece_work_service import PieceWorkService
from tests.test_com_tang_ca import _ca_hanh_chinh, _h, _lam_ngay, _ngay_lam_viec, _nv
from tests.test_khoan_khong_tien_tang_ca import (
    _chinh_thuc, _chuyen_to, _dong, _khai_com_tc_va_tat_khop_ca, _svc, _tinh_lai, _to,
)
from tests.test_luong_api import _sal

CO_BAN, TRACH_NHIEM = 4_800_000, 2_400_000     # bù lỗ 7.200.000 · 276.923,08 đ/công (26 công)


def _emp():
    return SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                           payroll_group=None, pay_grade_key=None, dependents_count=0)


def _tinh(svc, params, *, bu_lo=True, chi_an_km=None, allowance=0, la_to_in=None,
          thu_viec=False, **kw) -> dict:
    """Kiệt tháng 5: 21,5 ngày thường + 2 ngày lễ có lương + 3 Chủ nhật ⇒ 26,5 công, 3 công CN."""
    goc = dict(actual_cong=26.5, restday_cong=3)
    goc.update(kw)
    nv = _emp()
    if thu_viec:
        nv.status = "probation"
    return svc._compute(employee=nv,
                        salary=_sal(luong_vi_tri=CO_BAN, luong_trach_nhiem=TRACH_NHIEM,
                                    allowance=allowance),
                        params=params, standard_cong=26, on=date(2026, 5, 1), bu_lo=bu_lo,
                        chi_an_km=chi_an_km, la_to_in=la_to_in, **goc)


# =============================================================================================
# Engine — số viết tay
# =============================================================================================
def test_KHOAN_CAO_hon_bu_lo_chi_lay_khoan_khong_cong_luong_cong(client):
    """⭐ Kiệt T05: khoán 20.157.390 > bù lỗ theo công 7.200.000 ÷ 26 × 26,5 = 7.338.462 ⇒ chỉ khoán.

    Phần thêm 3 Chủ nhật theo ĐƠN GIÁ BÙ LỖ: 276.923 × 3 = 830.769 (không phải lương cơ bản 553.846).
    """
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), khoan=20_157_390)
        assert v["bu_lo_theo_cong"] == 7_338_462
        assert v["lay_bu_lo"] is False
        assert v["luong_cong"] == 0, "khoán cao hơn mà vẫn cộng lương theo công = trả cả hai"
        assert v["khoan"] == 20_157_390
        assert v["ot_pay"] == 830_769
        assert v["chuyen_can"] == 0 and v["allowance"] == 0     # nghỉ 2,5 ngày ⇒ mất chuyên cần
        assert v["gross"] == 20_157_390 + 830_769
    finally:
        db.close()


def test_KHOAN_THAP_hon_bu_lo_duoc_bu_cho_du_bu_lo(client):
    """Khoán 6.000.000 < bù lỗ 7.338.462 ⇒ nhận đúng 7.338.462 (phần bù thêm 1.338.462), không cộng dồn."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), khoan=6_000_000)
        assert v["lay_bu_lo"] is True
        assert v["luong_cong"] == 1_338_462
        assert v["luong_cong"] + v["khoan"] == v["bu_lo_theo_cong"] == 7_338_462
        assert v["gross"] == 7_338_462 + 830_769
    finally:
        db.close()


def test_CHUA_CO_TIEN_KHOAN_thi_nhan_tron_bu_lo(client):
    """Tháng chưa chốt phân bổ sản xuất (khoán = 0) ⇒ tự rơi về bù lỗ theo công."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), khoan=0)
        assert v["lay_bu_lo"] is True and v["luong_cong"] == 7_338_462
    finally:
        db.close()


def test_TAI_XE_co_BU_LO_nhu_tho_khoan_lay_MAX_voi_tien_km(client):
    """⭐ Khách chốt 15/09/2026 chiều: *"tài xế vẫn có lương bù lỗ như khoán sản lượng luôn"* — ĐẢO chốt
    sáng cùng ngày ("tài xế không có lương bù lỗ"). Đem so tiền km với bù lỗ 4 cột theo công:
    (7.200.000 + 5.400.000) ÷ 26 × 26 = 12.600.000.

    - km 21.075.180 > bù lỗ ⇒ lấy km, lương theo công 0, phụ cấp ngày thường nằm trong km.
    - km 1.000.000 / 0 ⇒ bù cho đủ 12.600.000.
    """
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        cao = _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=26, restday_cong=0,
                    khoan_km=21_075_180, allowance=5_400_000)
        assert cao["bu_lo_theo_cong"] == 12_600_000 and cao["lay_bu_lo"] is False
        assert cao["luong_cong"] == 0
        assert cao["allowance"] == 0 and cao["phu_cap_thang"] == 5_400_000
        assert cao["gross"] == 21_075_180 + cao["chuyen_can"]

        for km, bu_them in ((1_000_000, 11_600_000), (0, 12_600_000)):
            v = _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=26, restday_cong=0,
                      khoan_km=km, allowance=5_400_000)
            assert v["lay_bu_lo"] is True and v["luong_cong"] == bu_them, km
            assert v["gross"] == 12_600_000 + v["chuyen_can"], km

        # Công lễ nghỉ vẫn trả RIÊNG, ngoài phép so; bù lỗ chỉ còn 24 công đi làm.
        le = _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=26, restday_cong=0,
                   le_nghi_cong=2, khoan_km=21_075_180, allowance=5_400_000)
        assert le["bu_lo_theo_cong"] == round(12_600_000 / 26 * 24)
        assert le["luong_ngay_le"] == 553_846 and le["allowance"] == round(5_400_000 / 26 * 2)

        cn = _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=27, restday_cong=1,
                   khoan_km=5_000_000)
        assert cn["ot_pay"] == 276_923
        assert cn["lay_bu_lo"] is True and cn["luong_cong"] == round(7_200_000 / 26 * 27) - 5_000_000
    finally:
        db.close()


def test_NGAY_LE_nghi_cua_tho_khoan_tra_RIENG_ngoai_phan_so(client):
    """⭐ Chủ đọc bảng lương thật 15/09/2026: "+2" của Tổng NC là 2 ngày lễ nằm sẵn trong NCT, "họ trả
    công, nếu là khoán hoặc hành chính". 26 công gồm 24 ngày làm + 2 ngày lễ nghỉ:

    - Bù lỗ theo công chỉ còn đếm ngày đi làm: 276.923,08 × 24 = 6.646.154.
    - Công lễ trả riêng: 276.923,08 × 2 = 553.846 — khoán cao hơn bù lỗ vẫn có (trước bản vá: mất).
    - Khoán thấp (1.000.000): bù thêm 5.646.154 ⇒ bù thêm + khoán + công lễ = 7.200.000, y như chưa tách.
    """
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        cao = _tinh(svc, params, actual_cong=26, restday_cong=0, le_nghi_cong=2, khoan=20_157_390)
        assert cao["luong_ngay_le"] == 553_846 and cao["le_nghi_cong"] == 2
        assert cao["bu_lo_theo_cong"] == 6_646_154 and cao["lay_bu_lo"] is False
        assert cao["luong_cong"] == 0
        assert cao["gross"] == 20_157_390 + 553_846 + cao["chuyen_can"]

        thap = _tinh(svc, params, actual_cong=26, restday_cong=0, le_nghi_cong=2, khoan=1_000_000)
        assert thap["lay_bu_lo"] is True and thap["luong_cong"] == 5_646_154
        assert thap["luong_cong"] + thap["khoan"] + thap["luong_ngay_le"] == 7_200_000

        khong_le = _tinh(svc, params, actual_cong=26, restday_cong=0, khoan=1_000_000)
        assert khong_le["luong_ngay_le"] == 0 and khong_le["bu_lo_theo_cong"] == 7_200_000
        assert thap["gross"] == khong_le["gross"], "tháng lấy bù lỗ: tách công lễ không được đổi tổng"
    finally:
        db.close()


def test_NGAY_LE_nghi_cua_tai_xe_tra_rieng_cong_nhat_giu_trong_luong_cong(client):
    """Tài xế (chỉ ăn km) nghỉ 2 ngày lễ: km + 553.846 công lễ, lương theo công vẫn 0.
    Người công nhật: công lễ nằm sẵn trong lương theo công (26 công = 7.200.000), không tách dòng."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        tx = _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=26, restday_cong=0,
                   le_nghi_cong=2, khoan_km=21_075_180)
        assert tx["luong_cong"] == 0 and tx["bu_lo_theo_cong"] == 6_646_154
        assert tx["luong_ngay_le"] == 553_846
        assert tx["gross"] == 21_075_180 + 553_846 + tx["chuyen_can"]

        cn = _tinh(svc, params, bu_lo=False, chi_an_km=False, actual_cong=26, restday_cong=0,
                   le_nghi_cong=2)
        assert cn["luong_ngay_le"] == 0 and cn["luong_cong"] == 7_200_000
    finally:
        db.close()


def test_TO_THUONG_giu_nguyen_luong_cong_cong_khoan_phan_them_CN_theo_muc_nen(client):
    """Ngoài luật bù lỗ (tổ thường): lương công + khoán cộng thêm, không chụp số bù lỗ. Phần thêm 3 CN
    theo mức nền 7.200.000 ÷ 26 × 3 = 830.769 — từ 15/09/2026 cùng đơn giá với tổ khoán (chủ đảo chốt
    12/08 "theo lương cơ bản": trước đó ra 553.846)."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), khoan=6_000_000, bu_lo=False)
        assert v["bu_lo_theo_cong"] is None and v["lay_bu_lo"] is False
        assert v["luong_cong"] == 7_338_462 and v["khoan"] == 6_000_000
        assert v["ot_pay"] == 830_769
    finally:
        db.close()


def test_BAO_HIEM_khong_doi_du_khoan_cao_bao_nhieu(client):
    """Câu 5: "cho dù khoán cao bao nhiêu thì mức đóng bảo hiểm vẫn là trách nhiệm + vị trí"."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        cac_thang = [_tinh(svc, params, khoan=k) for k in (0, 6_000_000, 20_157_390, 90_000_000)]
        assert {v["insurance_base"] for v in cac_thang} == {CO_BAN + TRACH_NHIEM}
        assert len({v["bhxh"] for v in cac_thang}) == 1
    finally:
        db.close()


def test_NGHI_KHONG_PHEP_chi_bu_lo_bi_chia_theo_cong(client):
    """Câu 9: 20 công ngày thường, không CN ⇒ bù lỗ 7.200.000 × 20/26 = 5.538.462; khoán 5.000.000
    thấp hơn ⇒ bù thêm 538.462. Tiền khoán để nguyên."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), actual_cong=20, restday_cong=0, khoan=5_000_000)
        assert v["bu_lo_theo_cong"] == 5_538_462
        assert v["khoan"] == 5_000_000 and v["luong_cong"] == 538_462
    finally:
        db.close()


def test_PHU_CAP_di_theo_cong_ca_voi_tho_khoan(client):
    """Chủ chốt 15/09/2026 — ĐẢO câu 10 ("khoán hay bù lỗ đều ăn đủ phụ cấp"): phụ cấp đi theo công cho
    TẤT CẢ, y như bảng lương T05 (`X = SUM(K:N) ÷ 26 × Tổng NC`, người sản lượng Tổng NC = CN × 1 + lễ).

    Kiệt (phụ cấp 4.800.000, 3 Chủ nhật):
    - Khoán cao: ngày thường ăn trong tiền khoán ⇒ phụ cấp chỉ theo 3 công thêm CN = 4.800.000 ÷ 26 × 3.
    - Bù lỗ theo công GỒM phụ cấp (khách chốt 15/09/2026 chiều): (7.200.000 + 4.800.000) ÷ 26 × 26,5 =
      12.230.769 — nên tháng lấy bù lỗ KHÔNG cộng thêm dòng phụ cấp ngày thường nữa (cộng nữa = hai lần).
    """
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        cao = _tinh(svc, params, khoan=20_157_390, allowance=4_800_000)
        cao_khong = _tinh(svc, params, khoan=20_157_390)
        assert cao["phu_cap_thang"] == 4_800_000 and cao["cong_phu_cap"] == 3
        assert cao["allowance"] == 553_846
        assert cao["gross"] - cao_khong["gross"] == 553_846
        assert cao["bu_lo_theo_cong"] == 12_230_769 and cao_khong["bu_lo_theo_cong"] == 7_338_462

        thap = _tinh(svc, params, khoan=6_000_000, allowance=4_800_000)
        assert thap["lay_bu_lo"] is True
        assert thap["luong_cong"] + thap["khoan"] == thap["bu_lo_theo_cong"] == 12_230_769
        assert thap["cong_phu_cap"] == 3 and thap["allowance"] == 553_846, "phụ cấp đã nằm trong bù lỗ"
    finally:
        db.close()


def test_PHU_CAP_trong_BU_LO_ranh_gioi_KHONG_con_nhay_tien(client):
    """⭐ Khách chốt 15/09/2026 chiều — bù lỗ GỒM phụ cấp nên ranh giới khoán / bù lỗ đi LIỀN MẠCH.
    26 công, bù lỗ 4 cột = 12.000.000: khoán 11,9tr ⇒ 12.000.000 · khoán 12,1tr ⇒ 12.100.000.
    (Luật cũ nhảy 4,8tr ở ranh giới vì phụ cấp chỉ được cộng khi LẤY bù lỗ — đã gỡ.)"""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        duoi = _tinh(svc, params, actual_cong=26, restday_cong=0, khoan=11_900_000, allowance=4_800_000)
        tren = _tinh(svc, params, actual_cong=26, restday_cong=0, khoan=12_100_000, allowance=4_800_000)
        assert duoi["lay_bu_lo"] is True and tren["lay_bu_lo"] is False
        assert duoi["bu_lo_theo_cong"] == tren["bu_lo_theo_cong"] == 12_000_000
        assert duoi["gross"] - duoi["chuyen_can"] == 12_000_000
        assert tren["gross"] - tren["chuyen_can"] == 12_100_000
        assert tren["gross"] - duoi["gross"] == 100_000, "chênh khoán 200k mà tiền nhảy = luật hỏng"
    finally:
        db.close()


def test_NGAY_LE_di_lam_300_phan_tram_khong_con_400(client):
    """⭐ Khách chốt 15/09/2026 chiều: *"ngày lễ … chỉ 300% thôi"* — phần THÊM = hệ số − 1, y như Chủ nhật.
    Người công nhật 26 công (đã gồm 1 công lễ Đ112): phần thêm 276.923 × 2 = 553.846 ⇒ ngày lễ 3 công.
    Trước bản này phần thêm ăn TRỌN 3× ⇒ 830.769 (tổng 4 công)."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), bu_lo=False, actual_cong=26, restday_cong=0, holiday_cong=1)
        assert v["ot_pay"] == 553_846
        assert v["luong_cong"] == 7_200_000
    finally:
        db.close()


def test_LE_TRUNG_CHU_NHAT_500_phan_tram(client):
    """⭐ Khách chốt 15/09/2026 chiều: lễ rơi đúng Chủ nhật = 200% (CN) + 300% (lễ) = 500%.
    Chấm công ghi công ngày đó vào CẢ `holiday_cong` LẪN `restday_cong`, nên 2 công gốc nằm trong lương
    theo công và phần thêm = (3 − 1) + (2 − 1) = 3 công ⇒ 276.923 × 3 = 830.769."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), bu_lo=False, actual_cong=26, restday_cong=1, holiday_cong=1)
        assert v["ot_pay"] == 830_769
        assert v["luong_cong"] == 7_200_000, "2 công gốc của ngày đó nằm trong lương theo công"
    finally:
        db.close()


def test_TO_IN_ngay_CN_le_KHONG_co_cong_goc_tra_het_o_phan_them(client):
    """⭐ Khách chốt 15/09/2026 chiều: *"riêng khoán mà thuộc tổ in … chủ nhật đi làm được 2 công là công
    dôi ra luôn chứ không phải 1 công sản lượng và 1 công dôi ra"*.

    Kiệt 26,5 công (3 Chủ nhật), khoán 0 ⇒ nhận trọn bù lỗ:
    - Tổ khoán thường: bù lỗ 26,5 công + phần thêm 3 công = 7.338.462 + 830.769.
    - TỔ IN: bù lỗ chỉ 23,5 công đi làm ngày thường + phần thêm 3 × 2 công = 6.507.692 + 1.661.538.
    TỔNG TIỀN HAI BÊN BẰNG NHAU — chỉ khác chỗ số nào nằm trong phép so với tiền khoán."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        thuong = _tinh(svc, params, khoan=0)
        to_in = _tinh(svc, params, khoan=0, la_to_in=True)
        assert thuong["bu_lo_theo_cong"] == 7_338_462 and thuong["ot_pay"] == 830_769
        assert to_in["bu_lo_theo_cong"] == 6_507_692 and to_in["ot_pay"] == 1_661_538
        assert abs((to_in["luong_cong"] + to_in["ot_pay"])
                   - (thuong["luong_cong"] + thuong["ot_pay"])) <= 2
        # Khoán cao hơn bù lỗ: tổ in vẫn ăn trọn 2 công/ngày CN ở phần thêm.
        cao = _tinh(svc, params, khoan=20_157_390, la_to_in=True)
        assert cao["lay_bu_lo"] is False and cao["ot_pay"] == 1_661_538
        # Cờ tổ in của tổ KHÔNG khoán không đổi tiền (công gốc vẫn nằm trong lương theo công).
        assert _tinh(svc, params, bu_lo=False, khoan=0, la_to_in=True)["ot_pay"] == 830_769
    finally:
        db.close()


def test_PHEP_CO_LUONG_khong_tinh_cong_cho_nguoi_khoan(client):
    """⭐ Khách chốt 15/09/2026 chiều: *"nghỉ phép có lương ấy bên khoán mình sẽ không cho dùng"*.
    Đơn cũ đã duyệt vẫn còn thì Lương KHÔNG đếm công phép đó vào bù lỗ theo công: 26 công gồm 2 công
    phép ⇒ bù lỗ chỉ 24 công. Người công nhật vẫn được trả đủ 26 công như cũ."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        v = _tinh(svc, params, actual_cong=26, restday_cong=0, paid_leave_cong=2, khoan=0)
        assert v["bu_lo_theo_cong"] == 6_646_154 and v["luong_ngay_phep"] == 0
        cn = _tinh(svc, params, bu_lo=False, actual_cong=26, restday_cong=0, paid_leave_cong=2)
        assert cn["luong_cong"] == 7_200_000
    finally:
        db.close()


# =============================================================================================
# Qua "Tính lại" thật — tổ bật Lương khoán, chấm công thật, tiền khoán giả lập ở nguồn khoán
# =============================================================================================
def test_TINH_LAI_to_khoan_lay_MAX_chup_len_dong_luong_va_sua_1_o_khong_cong_doi(client, monkeypatch):
    """⭐ Hai thợ cùng tổ khoán, cùng 3 ngày công, lương cơ bản 10tr:
    thợ làm ra 50tr ăn khoán; thợ làm ra 100.000 được bù cho đủ bù lỗ theo công. Tổ thường giữ cách cũ.
    "Sửa 1 ô" sau đó phải ra đúng tổng cũ — nó cộng `luong_cong + khoan` từ dòng lương đã ghi."""
    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán bù lỗ", khoan=True)
    ngay = _ngay_lam_viec(client, h)[2:5]

    nguoi = {}
    for vai, to in (("cao", to_khoan), ("thap", to_khoan), ("thuong", None)):
        eid = _nv(client, h, ten=f"Thợ bù lỗ {vai}")
        _chinh_thuc(client, h, eid)
        if to is not None:
            _chuyen_to(eid, to)
        _ca_hanh_chinh(client, h, eid)
        for d in ngay:
            _lam_ngay(client, h, eid, d)
        nguoi[vai] = eid

    tien_khoan = {nguoi["cao"]: 50_000_000, nguoi["thap"]: 100_000, nguoi["thuong"]: 100_000}
    monkeypatch.setattr(PieceWorkService, "khoan_map", lambda self, y, m: dict(tien_khoan))

    bang = _tinh_lai(client, h)
    cao, thap, thuong = (_dong(bang, nguoi[k]) for k in ("cao", "thap", "thuong"))

    assert cao["bu_lo_theo_cong"] > 0 and cao["lay_bu_lo"] is False
    assert cao["luong_cong"] == 0 and cao["khoan"] == 50_000_000

    assert thap["lay_bu_lo"] is True and thap["khoan"] == 100_000
    assert abs(thap["luong_cong"] + thap["khoan"] - thap["bu_lo_theo_cong"]) <= 1
    assert thap["bu_lo_theo_cong"] == cao["bu_lo_theo_cong"], "cùng công, cùng mức ⇒ cùng bù lỗ"

    # Tổ thường: lương công vẫn trả, khoán vẫn cộng thêm.
    assert thuong["bu_lo_theo_cong"] is None
    assert thuong["luong_cong"] == thap["bu_lo_theo_cong"] and thuong["khoan"] == 100_000

    # Bảo hiểm cùng một gốc dù người kia làm ra 50 triệu (số tuyệt đối của gốc đóng đã có test
    # engine `test_BAO_HIEM_khong_doi_du_khoan_cao_bao_nhieu`).
    assert cao["insurance_base"] == thap["insurance_base"]
    assert cao["bhxh"] == thap["bhxh"]

    # "Sửa 1 ô" (ghi chú) KHÔNG được cộng lại lương theo công lên trên tiền khoán.
    for d in (cao, thap):
        r = client.put(f"/api/luong/lines/{d['id']}", json={"note": "soát bù lỗ"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["gross"] == d["gross"], (d["employee_id"], r.json()["gross"], d["gross"])
        assert r.json()["net_pay"] == d["net_pay"]


def test_TINH_LAI_to_GIAO_HANG_tai_xe_lay_MAX_km_voi_bu_lo(client, monkeypatch):
    """Tổ bật cờ Giao hàng qua "Tính lại" thật: tài xế chạy ra 20 triệu tiền km (cao hơn bù lỗ 3 công)
    ⇒ lương theo công 0; tài xế tháng không có chuyến nào ⇒ nhận trọn bù lỗ theo công và vẫn bị nhắc
    trước khi chốt (khách chốt 15/09/2026 chiều: tài xế có bù lỗ như thợ khoán)."""
    from app.services.khoan_km_service import KhoanKmService

    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_gh = _to("Tổ giao hàng bù lỗ", giao_hang=True)
    ngay = _ngay_lam_viec(client, h)[2:5]

    nguoi = {}
    for vai in ("chay", "nghi_xe"):
        eid = _nv(client, h, ten=f"Tài xế bù lỗ {vai}")
        _chinh_thuc(client, h, eid)
        _chuyen_to(eid, to_gh)
        _ca_hanh_chinh(client, h, eid)
        for d in ngay:
            _lam_ngay(client, h, eid, d)
        nguoi[vai] = eid

    monkeypatch.setattr(KhoanKmService, "theo_ky", lambda self, y, m: {nguoi["chay"]: 20_000_000})

    bang = _tinh_lai(client, h)
    chay, nghi_xe = _dong(bang, nguoi["chay"]), _dong(bang, nguoi["nghi_xe"])

    assert chay["khoan_km"] == 20_000_000 and chay["luong_cong"] == 0
    assert chay["bu_lo_theo_cong"] > 0 and chay["lay_bu_lo"] is False

    assert nghi_xe["khoan_km"] == 0 and nghi_xe["lay_bu_lo"] is True
    assert nghi_xe["luong_cong"] == nghi_xe["bu_lo_theo_cong"] == chay["bu_lo_theo_cong"]
    canh_bao = bang["canh_bao_chot"] or ""
    assert "1 tài xế / phụ xe có công nhưng tiền km kỳ này = 0 (Tài xế bù lỗ nghi_xe)" in canh_bao, canh_bao
    assert "tổ khoán" not in canh_bao, "tài xế bị gom nhầm vào câu của thợ khoán: " + canh_bao
    assert "Tài xế bù lỗ chay" not in canh_bao


def test_TINH_LAI_NGAY_LE_nghi_nguoi_khoan_va_tai_xe_duoc_tra_rieng_chot_cong_khong_nhay(client, monkeypatch):
    """⭐ Lịch chung có 1 ngày lễ hưởng lương (không ai đi làm) + mỗi người 3 ngày công:

    - Thợ khoán làm ra 50tr: khoán + 1 công lễ riêng (trước 15/09/2026 mất công lễ).
    - Thợ khoán làm ra 100.000: bù thêm + khoán + công lễ = đúng 4 công như người công nhật.
    - Tài xế chạy 20tr km: km + 1 công lễ, lương theo công vẫn 0 (km cao hơn bù lỗ 3 công).
    - Tổ thường: công lễ nằm sẵn trong lương công (4 công), không tách dòng.
    "Sửa 1 ô" giữ nguyên gross; chốt công xong Tính lại số không nhảy (nhánh ảnh chụp đọc `holiday_days`)."""
    from app.services.khoan_km_service import KhoanKmService

    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán ngày lễ", khoan=True)
    to_gh = _to("Tổ giao hàng ngày lễ", giao_hang=True)
    ngay_lam = _ngay_lam_viec(client, h)
    ngay, le = ngay_lam[2:5], ngay_lam[10]
    r = client.post("/api/calendar/special-days",
                    json={"day": f"2026-06-{le:02d}", "kind": "off", "name": "Lễ thử", "is_paid": True},
                    headers=h)
    assert r.status_code in (200, 201), r.text

    nguoi = {}
    for vai, to in (("cao", to_khoan), ("thap", to_khoan), ("tai_xe", to_gh), ("thuong", None)):
        eid = _nv(client, h, ten=f"Ngày lễ {vai}")
        _chinh_thuc(client, h, eid)
        if to is not None:
            _chuyen_to(eid, to)
        _ca_hanh_chinh(client, h, eid)
        for d in ngay:
            _lam_ngay(client, h, eid, d)
        nguoi[vai] = eid
    monkeypatch.setattr(PieceWorkService, "khoan_map",
                        lambda self, y, m: {nguoi["cao"]: 50_000_000, nguoi["thap"]: 100_000})
    monkeypatch.setattr(KhoanKmService, "theo_ky", lambda self, y, m: {nguoi["tai_xe"]: 20_000_000})

    bang = _tinh_lai(client, h)
    cao, thap, tx, thuong = (_dong(bang, nguoi[k]) for k in ("cao", "thap", "tai_xe", "thuong"))

    assert thuong["actual_cong"] == 4, "đo hỏng: ngày lễ chưa vào công"
    assert thuong["luong_ngay_le"] == 0 and thuong["bu_lo_theo_cong"] is None
    # Số công lễ vẫn chụp cho mọi người — phiếu / bảng lương ghi "1 ngày" cạnh tiền lễ.
    assert thuong["le_nghi_cong"] == cao["le_nghi_cong"] == tx["le_nghi_cong"] == 1
    mot_cong = thuong["luong_cong"] / 4

    assert abs(cao["luong_ngay_le"] - mot_cong) <= 1, (cao["luong_ngay_le"], mot_cong)
    assert abs(cao["bu_lo_theo_cong"] - 3 * mot_cong) <= 1
    assert cao["luong_cong"] == 0 and cao["khoan"] == 50_000_000

    assert thap["lay_bu_lo"] is True
    assert abs(thap["luong_cong"] + thap["khoan"] + thap["luong_ngay_le"] - thuong["luong_cong"]) <= 1

    assert tx["luong_cong"] == 0 and tx["khoan_km"] == 20_000_000 and tx["lay_bu_lo"] is False
    assert abs(tx["luong_ngay_le"] - mot_cong) <= 1

    for d in (cao, tx):
        r = client.put(f"/api/luong/lines/{d['id']}", json={"note": "soát công lễ"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["gross"] == d["gross"], (d["employee_id"], r.json()["gross"], d["gross"])

    r = client.post("/api/attendance/period/lock", json={"year": 2026, "month": 6}, headers=h)
    assert r.status_code == 200, r.text
    sau = _tinh_lai(client, h)
    for k in ("cao", "thap", "tai_xe"):
        truoc_d, sau_d = _dong(bang, nguoi[k]), _dong(sau, nguoi[k])
        assert sau_d["luong_ngay_le"] == truoc_d["luong_ngay_le"], (
            f"{k}: chốt công xong công lễ nhảy {truoc_d['luong_ngay_le']} → {sau_d['luong_ngay_le']}")
        assert sau_d["gross"] == truoc_d["gross"], k


# =============================================================================================
# TỔ GIAO HÀNG — vế thời gian GỒM tiền giờ tăng ca rồi mới so khoán km (chủ chốt 16/09/2026, §00.10)
#
# Chủ: *"lương thời gian ấy gọi là lương bù lỗ ấy nó cộng cả tiền tăng ca vào rồi so sánh lương khoán
# rồi mới xem bên này cao hơn thì lấy — chỉ áp dụng cho phòng ban giao hàng"* · *"tăng ca thì nhân hệ
# số bình thường thôi"*. ĐẢO chốt 14/09/2026 cho RIÊNG tổ Giao hàng.
#
# Số viết tay: nền 7.200.000 + phụ cấp 5.400.000, 26 công ⇒ bù lỗ 4 cột 12.600.000.
# 10h tăng ca ngày thường: (7.200.000 ÷ 26 ÷ 8) × 10 × 1,5 = 519.231 ⇒ vế thời gian 13.119.231.
# =============================================================================================
BU_LO_GH, TC_GH = 12_600_000, 519_231


def _tai_xe_tc(svc, params, *, khoan_km):
    return _tinh(svc, params, bu_lo=False, chi_an_km=True, actual_cong=26, restday_cong=0,
                 allowance=5_400_000, ot_minutes=600, khoan_km=khoan_km)


def test_GIAO_HANG_tien_km_THAP_hon_thi_an_bu_lo_CONG_tang_ca(client):
    """⭐ km 5tr < vế thời gian 13.119.231 ⇒ trả bù lỗ + tăng ca, tăng ca trả ĐỦ."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tai_xe_tc(svc, svc.get_params(), khoan_km=5_000_000)
        assert v["bu_lo_theo_cong"] == BU_LO_GH
        assert v["lay_bu_lo"] is True
        assert v["ot_pay"] == TC_GH, "tài xế phải có tiền giờ tăng ca (đảo chốt 14/09 cho tổ GH)"
        assert v["luong_cong"] == BU_LO_GH - 5_000_000
        assert v["luong_cong"] + v["khoan_km"] + v["ot_pay"] == BU_LO_GH + TC_GH
    finally:
        db.close()


def test_GIAO_HANG_km_NHINH_hon_bu_lo_nhung_van_THUA_ve_thoi_gian(client):
    """⭐ Ca ở GIỮA: km 13.000.000 > bù lỗ 12.600.000 nhưng < vế thời gian 13.119.231.

    Vẫn lấy vế thời gian. Đã ăn km rồi nên chỉ bù đúng phần còn thiếu 119.231 — KHÔNG trả cả km lẫn
    trọn tăng ca (sẽ thành 13.519.231, tức cộng dồn hai vế)."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tai_xe_tc(svc, svc.get_params(), khoan_km=13_000_000)
        assert v["lay_bu_lo"] is True
        assert v["luong_cong"] == 0
        assert v["ot_pay"] == BU_LO_GH + TC_GH - 13_000_000
        assert v["khoan_km"] + v["ot_pay"] == BU_LO_GH + TC_GH
    finally:
        db.close()


def test_GIAO_HANG_km_CAO_hon_ve_thoi_gian_thi_KHONG_co_tien_tang_ca(client):
    """km 20tr > vế thời gian ⇒ lấy km, không lương theo công, KHÔNG tiền tăng ca (hai vế thay nhau)."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tai_xe_tc(svc, svc.get_params(), khoan_km=20_000_000)
        assert v["lay_bu_lo"] is False
        assert v["luong_cong"] == 0 and v["ot_pay"] == 0
        assert v["khoan_km"] == 20_000_000
    finally:
        db.close()


def test_TO_KHOAN_san_luong_KHONG_dinh_luat_moi_van_0d_tang_ca(client):
    """Luật mới CHỈ cho tổ Giao hàng: thợ khoán sản lượng vẫn 0đ tiền giờ tăng ca (chốt 14/09/2026)."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), actual_cong=26, restday_cong=0, allowance=5_400_000,
                  ot_minutes=600, khoan=5_000_000)
        assert v["ot_pay"] == 0, "tổ khoán sản lượng bỗng dưng có tiền giờ tăng ca"
        assert v["lay_bu_lo"] is True and v["luong_cong"] == BU_LO_GH - 5_000_000
    finally:
        db.close()


# =============================================================================================
# THỬ VIỆC ở tổ khoán — LUÔN ăn bù lỗ, không đem so sản lượng (chủ chốt 16/09/2026, PRD §00.9)
#
# Chủ: *"nhân viên thử việc bên khoán ấy nó sẽ ăn theo lương bù lỗ, và mức tiền mình đã làm như phần
# hành chính ấy là số % của lương ấy"*. Hai vế: (1) không so với khoán nữa; (2) % thử việc chỉ nhân
# vào MỨC NỀN, phụ cấp giữ 100% — y hệt khối hành chính.
# Số viết tay: nền 7.200.000 × 0,80 = 5.760.000 ⇒ 221.538,46 đ/công × 26,5 công = 5.870.769.
# =============================================================================================
BU_LO_TV = 5_870_769


def test_THU_VIEC_to_khoan_LUON_an_bu_lo_du_san_luong_CAO_hon(client):
    """⭐ Cùng số của Kiệt nhưng là người thử việc: khoán 20.157.390 vẫn KHÔNG được lấy.

    Người chính thức tháng này lấy khoán 20.157.390 (test đầu file). Thử việc: 5.870.769.
    Không zero tiền khoán thì `max(0, bù lỗ − khoán)` ra 0 ⇒ thành "lấy khoán", ăn trọn 100% tiền
    sản lượng và % thử việc mất tác dụng đúng vào tháng làm ra nhiều tiền nhất."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), thu_viec=True, khoan=20_157_390)
        assert v["is_probation"] is True
        assert v["bu_lo_theo_cong"] == BU_LO_TV
        assert v["lay_bu_lo"] is True
        assert v["luong_cong"] == BU_LO_TV, "thử việc phải nhận trọn bù lỗ, không phải phần bù thêm"
        assert v["khoan"] == 0, "tiền sản lượng vẫn cộng cho thử việc = không so nữa mà vẫn trả khoán"
    finally:
        db.close()


def test_THU_VIEC_khoan_THAP_hon_cung_chi_an_bu_lo_khong_cong_don(client):
    """Khoán 3tr < bù lỗ: vẫn đúng 5.870.769, KHÔNG phải bù lỗ + khoán."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), thu_viec=True, khoan=3_000_000)
        assert v["khoan"] == 0 and v["luong_cong"] == BU_LO_TV and v["lay_bu_lo"] is True
    finally:
        db.close()


def test_THU_VIEC_tai_xe_km_CAO_hon_cung_an_bu_lo(client):
    """Tài xế / phụ xe thử việc: chạy ra 20tr tiền km vẫn ăn bù lỗ theo công."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), thu_viec=True, chi_an_km=True, khoan_km=20_000_000)
        assert v["khoan_km"] == 0 and v["luong_cong"] == BU_LO_TV and v["lay_bu_lo"] is True
    finally:
        db.close()


def test_THU_VIEC_he_so_chi_nhan_vao_NEN_phu_cap_van_du_100(client):
    """⭐ Vế 2 của câu chốt: phụ cấp 2,6tr KHÔNG bị nhân 0,80 — y như khối hành chính.

    (5.760.000 + 2.600.000) ÷ 26 × 26,5 = 8.520.769. Nhân cả phụ cấp thì ra 7.990.769."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        v = _tinh(svc, svc.get_params(), thu_viec=True, allowance=2_600_000, khoan=50_000_000)
        assert v["bu_lo_theo_cong"] == 8_520_769
        assert v["bu_lo_theo_cong"] != 7_990_769, "phụ cấp bị nhân hệ số thử việc"
    finally:
        db.close()


def test_THU_VIEC_khong_ganh_TRU_LOI_khoan_vi_da_khong_an_khoan(client):
    """Bỏ tiền khoán thì cũng bỏ trừ lỗi khoán: `khoan_map` đã trừ lỗi vào số vừa bị bỏ, để lại
    `khoan_defect` là bóp trần khấu trừ 30% (Đ102) vì một khoản họ không hề chịu."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        p = svc.get_params()
        co_loi = _tinh(svc, p, thu_viec=True, khoan=20_000_000, khoan_defect=1_000_000,
                       vi_pham=1_000_000)
        khong_loi = _tinh(svc, p, thu_viec=True, khoan=20_000_000, vi_pham=1_000_000)
        assert co_loi["gross"] == khong_loi["gross"], "trừ lỗi khoán vẫn bóp trần 30% của thử việc"
    finally:
        db.close()


def test_TINH_LAI_THU_VIEC_va_CHINH_THUC_cung_to_khoan_an_hai_kieu(client, monkeypatch):
    """⭐ Qua API thật: hai thợ cùng tổ khoán, cùng 3 ngày công, cùng làm ra 50 triệu sản lượng.

    Chính thức ⇒ lấy khoán 50tr. Thử việc ⇒ bù lỗ theo công, hai cột khoán = 0, và bù lỗ của họ
    đúng bằng 0,80 bù lỗ của người chính thức (hệ số chỉ nhân vào nền). "Sửa 1 ô" không đổi tổng."""
    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán thử việc", khoan=True)
    ngay = _ngay_lam_viec(client, h)[2:5]

    nguoi = {}
    for vai in ("chinh_thuc", "thu_viec"):
        eid = _nv(client, h, ten=f"Khoán {vai}")
        if vai == "chinh_thuc":
            _chinh_thuc(client, h, eid)
        _chuyen_to(eid, to_khoan)
        _ca_hanh_chinh(client, h, eid)
        for d in ngay:
            _lam_ngay(client, h, eid, d)
        nguoi[vai] = eid
    monkeypatch.setattr(PieceWorkService, "khoan_map",
                        lambda self, y, m: {e: 50_000_000 for e in nguoi.values()})

    bang = _tinh_lai(client, h)
    ct, tv = _dong(bang, nguoi["chinh_thuc"]), _dong(bang, nguoi["thu_viec"])

    assert ct["is_probation"] is False and ct["lay_bu_lo"] is False
    assert ct["khoan"] == 50_000_000 and ct["luong_cong"] == 0

    assert tv["is_probation"] is True and tv["lay_bu_lo"] is True
    assert tv["khoan"] == 0, "thử việc vẫn ăn sản lượng"
    assert tv["luong_cong"] == tv["bu_lo_theo_cong"] > 0
    assert abs(tv["bu_lo_theo_cong"] - 0.80 * ct["bu_lo_theo_cong"]) <= 1, (
        tv["bu_lo_theo_cong"], ct["bu_lo_theo_cong"])

    r = client.put(f"/api/luong/lines/{tv['id']}", json={"note": "soát thử việc"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["gross"] == tv["gross"] and r.json()["net_pay"] == tv["net_pay"]


def test_CANH_BAO_truoc_chot_KHONG_reo_ten_nguoi_thu_viec(client):
    """Tiền khoán của thử việc = 0 vì LUẬT, không phải vì phân bổ sản xuất chưa chốt.

    Câu nhắc *"có công nhưng tiền khoán kỳ này = 0 — kiểm lại phân bổ sản xuất đã chốt chưa"* mà réo
    tên họ là bắt HCNS đi tìm một phiếu không bao giờ có, và tháng nào cũng réo."""
    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán cảnh báo", khoan=True)
    ngay = _ngay_lam_viec(client, h)[2:5]

    nguoi = {}
    for vai in ("chinh_thuc", "thu_viec"):
        eid = _nv(client, h, ten=f"Cảnh báo {vai}")
        if vai == "chinh_thuc":
            _chinh_thuc(client, h, eid)
        _chuyen_to(eid, to_khoan)
        _ca_hanh_chinh(client, h, eid)
        for d in ngay:
            _lam_ngay(client, h, eid, d)
        nguoi[vai] = eid

    bang = _tinh_lai(client, h)      # chưa chốt phân bổ nào ⇒ tiền khoán = 0 cho cả hai
    cb = bang["canh_bao_chot"] or ""
    assert "Cảnh báo chinh_thuc" in cb, cb
    assert "Cảnh báo thu_viec" not in cb, cb


def test_CHAN_nghi_phep_CO_LUONG_cua_nguoi_khoan_va_tai_xe(client):
    """⭐ Khách chốt 15/09/2026 chiều: *"nghỉ phép có lương ấy bên khoán mình sẽ không cho dùng"*.

    Chặn ngay ở CỬA GỬI ĐƠN cho người tổ Lương khoán và tổ Giao hàng; loại nghỉ KHÔNG lương vẫn
    dùng bình thường; người tổ thường không bị đụng."""
    h = _h(client)
    co_luong = client.post("/api/leaves/types",
                           json={"name": "Phép năm khoán", "is_paid": True, "annual_quota": 12},
                           headers=h).json()["id"]
    khong_luong = client.post("/api/leaves/types",
                              json={"name": "Nghỉ không lương khoán", "is_paid": False,
                                    "annual_quota": 0}, headers=h).json()["id"]
    # Đơn gửi cho CHÍNH người đăng nhập ⇒ chuyển hồ sơ của admin qua từng tổ để đo từng chế độ.
    me = client.get("/api/leaves/me", headers=h).json()
    assert me["has_employee"] is True
    eid = client.get("/api/employees?q=Admin", headers=h).json()["items"][0]["id"]

    def xin(tid, ngay):
        return client.post("/api/leaves", json={"leave_type_id": tid,
                                                "start_date": ngay, "end_date": ngay}, headers=h)

    ngay = iter(["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16", "2026-06-17"])
    for ten, kw in (("Tổ khoán chặn phép", dict(khoan=True)),
                    ("Tổ giao hàng chặn phép", dict(giao_hang=True))):
        _chuyen_to(eid, _to(ten, **kw))
        r = xin(co_luong, next(ngay))
        assert r.status_code == 400, (ten, r.status_code, r.text)
        assert "không dùng nghỉ phép có lương" in r.text, r.text
        assert xin(khong_luong, next(ngay)).status_code == 201, ten

    _chuyen_to(eid, _to("Tổ thường chặn phép"))
    assert xin(co_luong, next(ngay)).status_code == 201


def test_CHAN_to_GIAO_HANG_bat_LUONG_KHOAN_va_nguoc_lai(client):
    """⭐ Một tổ không vừa có cờ Giao hàng vừa ăn Lương khoán / sản lượng (chủ chốt 16/09/2026).

    Hai cờ là hai NGUỒN TIỀN đem so với bù lỗ (tiền km ⟷ tiền sản lượng). Bật cả hai thì phép so
    cộng chung hai khoản thành một vế: ai gán nhầm một phiếu sản lượng cho tài xế là tháng đó anh ta
    mất trắng tiền tăng ca. Chặn cả HAI CHIỀU + cả cửa tạo phòng ban."""
    h = _h(client)

    # (1) tổ Giao hàng ⇒ Cấu hình lương không bật được Lương khoán
    gh = client.post("/api/departments", json={"name": "Tổ giao hàng chặn khoán",
                                               "la_giao_hang": True}, headers=h)
    assert gh.status_code == 201, gh.text
    pb = gh.json()["id"]
    r = client.put(f"/api/luong/dept-components/{pb}",
                   json={"items": [{"component_key": "luong_khoan", "is_enabled": True}]},
                   headers=h)
    assert r.status_code == 400, r.text
    assert "Giao hàng" in r.text and "Lương khoán" in r.text, r.text
    # Tắt thì vẫn ghi được (không khoá cứng cả ô).
    r = client.put(f"/api/luong/dept-components/{pb}",
                   json={"items": [{"component_key": "luong_khoan", "is_enabled": False}]},
                   headers=h)
    assert r.status_code == 200, r.text

    # (2) chiều ngược lại: tổ đang ăn khoán sản lượng ⇒ không bật được cờ Giao hàng
    kh = client.post("/api/departments", json={"name": "Tổ khoán chặn giao hàng",
                                               "has_piece_work": True}, headers=h)
    assert kh.status_code == 201, kh.text
    r = client.put(f"/api/departments/{kh.json()['id']}",
                   json={"name": "Tổ khoán chặn giao hàng", "la_giao_hang": True}, headers=h)
    assert r.status_code == 400, r.text
    assert "Giao hàng" in r.text, r.text

    # (3) cửa TẠO phòng ban cũng chặn, không để lọt trạng thái sai ngay từ đầu
    r = client.post("/api/departments", json={"name": "Tổ vừa km vừa sản lượng",
                                              "la_giao_hang": True, "has_piece_work": True},
                    headers=h)
    assert r.status_code == 400, r.text


def test_CO_TO_IN_khai_o_phong_ban_qua_API(client):
    """Cờ "Tổ in" khai ở màn Phòng ban (mg 0304): tạo có cờ, PUT không gửi thì GIỮ NGUYÊN (cùng luật
    với cờ Giao hàng — luồng sửa chỉ đụng tên phòng không được âm thầm gỡ cờ)."""
    h = _h(client)
    r = client.post("/api/departments", json={"name": "Tổ in offset", "la_to_in": True,
                                              "has_piece_work": True}, headers=h)
    assert r.status_code == 201, r.text
    pb = r.json()
    assert pb["la_to_in"] is True and pb["has_piece_work"] is True

    doi_ten = client.put(f"/api/departments/{pb['id']}",
                         json={"name": "Tổ in offset 2", "head_user_id": None}, headers=h)
    assert doi_ten.status_code == 200, doi_ten.text
    assert doi_ten.json()["la_to_in"] is True, "sửa tên phòng mà mất cờ Tổ in"

    tat = client.put(f"/api/departments/{pb['id']}",
                     json={"name": "Tổ in offset 2", "la_to_in": False}, headers=h)
    assert tat.status_code == 200 and tat.json()["la_to_in"] is False
