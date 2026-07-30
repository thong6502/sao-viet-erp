"""Khoán theo ĐẦU VIỆC — luật khớp đầu việc với bước lệnh + snapshot khi chọn.

Bối cảnh nghiệp vụ: bảng CÔNG KHOÁN của xưởng gom NHIỀU công đoạn vào MỘT dòng đơn giá (cán bóng ·
cán mờ · phủ UV nước · UV mờ = 150 đ/m²), nhưng cũng có trường hợp CÙNG một công đoạn mà hai giá
(bế máy 250 đ/tờ ≠ bế tay 400 đ/tờ). Hai tình huống đó quyết định máy có được điền hộ hay không.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.piece_work_service import dau_viec_khop, khoan_snapshot


def _rate(**kw):
    base = dict(id=1, department_id=10, is_active=True, cong_doan_mas=[], cong_doan=None,
                name="Việc", unit="m²", unit_price=150, tinh_theo="per_sheet_area")
    base.update(kw)
    return SimpleNamespace(**base)


CAN_PHU = _rate(id=1, name="Cán bóng · cán mờ · phủ UV", cong_doan_mas=["CD-0003", "CD-0010"])
METALIZE = _rate(id=2, name="Ghép màng metalize", cong_doan_mas=["CD-0013"], unit_price=250)
CHUNG_TO = _rate(id=3, name="Việc chung của tổ", cong_doan_mas=[])
BE_MAY = _rate(id=4, department_id=11, name="Bế máy", cong_doan_mas=["CD-0011"],
               unit="tờ", unit_price=250, tinh_theo="per_sheet")
BE_TAY = _rate(id=5, department_id=11, name="Bế tay", cong_doan_mas=["CD-0011"],
               unit="tờ", unit_price=400, tinh_theo="per_sheet")
RATES = [CAN_PHU, METALIZE, CHUNG_TO, BE_MAY, BE_TAY]


def test_mot_dau_viec_phu_nhieu_cong_doan():
    """Cán bóng và cán mờ là hai công đoạn khác nhau (khác giá BÁN) nhưng cùng một công khoán."""
    for ma in ("CD-0003", "CD-0010"):
        khop = dau_viec_khop(RATES, department_id=10, cong_doan_ma=ma)
        assert [r.id for r in khop] == [CAN_PHU.id]


def test_dong_khai_rieng_thang_dong_chung():
    """Tổ có 1 dòng chung + 1 dòng khai riêng cho công đoạn → phải lấy dòng RIÊNG. Trộn cả hai thì
    bước nào cũng ra 2 kết quả và người dùng phải chọn tay dù xưởng đã khai rõ."""
    khop = dau_viec_khop(RATES, department_id=10, cong_doan_ma="CD-0013")
    assert [r.id for r in khop] == [METALIZE.id]


def test_cong_doan_khong_khai_rieng_thi_dung_dong_chung():
    khop = dau_viec_khop(RATES, department_id=10, cong_doan_ma="CD-9999")
    assert [r.id for r in khop] == [CHUNG_TO.id]


def test_cung_cong_doan_hai_gia_thi_de_nguoi_chon():
    """Bế máy / bế tay cùng CD-0011 → trả 2 dòng; `lsx_service` thấy ≠1 nên KHÔNG điền hộ."""
    khop = dau_viec_khop(RATES, department_id=11, cong_doan_ma="CD-0011")
    assert {r.id for r in khop} == {BE_MAY.id, BE_TAY.id}


def test_khong_lay_dau_viec_cua_to_khac():
    """Bước của tổ Bế không được ăn đơn giá của tổ Cán — tiền khoán sẽ chảy sang tổ sai."""
    khop = dau_viec_khop(RATES, department_id=11, cong_doan_ma="CD-0010")
    assert khop == []


def test_bo_qua_dong_ngung_dung():
    ngung = _rate(id=6, name="Giá cũ", cong_doan_mas=["CD-0010"], is_active=False)
    khop = dau_viec_khop([*RATES, ngung], department_id=10, cong_doan_ma="CD-0010")
    assert [r.id for r in khop] == [CAN_PHU.id]


def test_doc_duoc_cot_cong_doan_cu():
    """Dòng cũ khai 1 mã ở cột `cong_doan` (trước khi có `cong_doan_mas`) vẫn phải khớp."""
    cu = _rate(id=7, name="Dòng cũ", cong_doan_mas=[], cong_doan="CD-0010")
    khop = dau_viec_khop([cu], department_id=10, cong_doan_ma="CD-0010")
    assert [r.id for r in khop] == [cu.id]


def test_khong_co_to_thi_khong_khop_gi():
    """Bước chưa gán tổ (department_id=None) — `dau_viec_khop` bỏ lọc tổ, nhưng vẫn theo công đoạn."""
    khop = dau_viec_khop(RATES, department_id=None, cong_doan_ma="CD-0011")
    assert {r.id for r in khop} == {BE_MAY.id, BE_TAY.id}


def test_snapshot_ghim_du_so_de_khong_doc_song():
    """Ghim đủ tên + đơn vị + đơn giá + trục: xưởng lên giá về sau không được xê dịch lệnh đã phát."""
    snap = khoan_snapshot(BE_MAY)
    assert snap == {"rate_id": 4, "ten": "Bế máy", "don_vi": "tờ", "don_gia": 250.0,
                    "tinh_theo": "per_sheet"}
