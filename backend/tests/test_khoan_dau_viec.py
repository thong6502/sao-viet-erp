"""Khoán theo ĐẦU VIỆC — luật khớp đầu việc với bước lệnh + snapshot khi chọn.

Bảng đơn giá khoán là bảng KHAI BÁO thuần (chủ chốt 2026-07-31): nó chỉ nói *tổ này có những đầu
việc nào, mỗi việc bao nhiêu tiền một đơn vị*. Việc nào của tổ dùng dòng nào là do bên SẢN XUẤT
chọn ở bước lệnh — bảng giá không khai, không đoán. Bản trước cho khai "áp cho công đoạn nào" ngay
trên dòng giá, đẻ ra một luật khớp ngầm (dòng khai riêng thắng dòng khai chung) mà mở form ra
không ai đoán được.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.piece_work_service import dau_viec_khop, khoan_snapshot


def _rate(**kw):
    base = dict(id=1, department_id=10, is_active=True, name="Việc", unit="m²", unit_price=150)
    base.update(kw)
    return SimpleNamespace(**base)


CAN_PHU = _rate(id=1, name="Cán bóng · cán mờ · phủ UV")
METALIZE = _rate(id=2, name="Ghép màng metalize", unit_price=250)
BE_MAY = _rate(id=3, department_id=11, name="Bế máy", unit="tờ", unit_price=250)
BE_TAY = _rate(id=4, department_id=11, name="Bế tay", unit="tờ", unit_price=400)
RATES = [CAN_PHU, METALIZE, BE_MAY, BE_TAY]


def test_thay_moi_dau_viec_cua_to():
    """Tổ Cán màng có 2 đơn giá → bước nào của tổ đó cũng thấy cả 2, người lập lệnh chọn."""
    khop = dau_viec_khop(RATES, department_id=10)
    assert {r.id for r in khop} == {CAN_PHU.id, METALIZE.id}


def test_to_mot_dau_viec_thi_tu_dien_duoc():
    """Khớp đúng 1 thì `lsx_service` điền sẵn cho bước — đó là lý do hàm trả LIST chứ không bool."""
    khop = dau_viec_khop([CAN_PHU, BE_MAY], department_id=10)
    assert [r.id for r in khop] == [CAN_PHU.id]


def test_khong_lay_dau_viec_cua_to_khac():
    """Bước của tổ Bế không được ăn đơn giá của tổ Cán — tiền khoán sẽ chảy sang tổ sai."""
    khop = dau_viec_khop(RATES, department_id=11)
    assert {r.id for r in khop} == {BE_MAY.id, BE_TAY.id}


def test_bo_qua_dong_ngung_dung():
    ngung = _rate(id=9, name="Giá cũ", is_active=False)
    khop = dau_viec_khop([*RATES, ngung], department_id=10)
    assert 9 not in {r.id for r in khop}


def test_to_chua_khai_gia_thi_rong():
    """Tổ không ăn khoán → danh sách rỗng → bước để trống ô Công việc khoán, không bịa."""
    assert dau_viec_khop(RATES, department_id=99) == []


def test_khong_con_luat_khop_theo_cong_doan():
    """Canh cho luật ngầm khỏi mọc lại: hàm KHÔNG nhận mã công đoạn nữa."""
    import inspect

    assert "cong_doan_ma" not in inspect.signature(dau_viec_khop).parameters


def test_snapshot_ghim_du_so_de_khong_doc_song():
    """Ghim tên + đơn vị + đơn giá: xưởng lên giá về sau không được xê dịch lệnh đã phát. KHÔNG
    ghim trục tính — không còn hệ số ngầm nào để ghim."""
    snap = khoan_snapshot(BE_MAY)
    assert snap == {"rate_id": 3, "ten": "Bế máy", "don_vi": "tờ", "don_gia": 250.0}
