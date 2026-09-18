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


def test_snapshot_chi_ghim_TEN_VIEC_khong_ghim_gia():
    """Ảnh chụp giữ CÁI TÊN + ĐƠN VỊ của việc, không giữ giá.

    Từ 11/09/2026 kế hoạch và sản xuất không ôm tiền khoán nữa (chủ xưởng: *"bên sản xuất chỉ ghi
    nhận số lượng thôi"*). Ghim giá lúc phát hành là ghim một con số mà máy nào chạy, kíp mấy
    người, mấy màu mực, khuôn cũ hay mới đều làm nó đổi — những chiều engine không suy được. Kế
    toán lương đọc `rate_id`/`ten` rồi tra bảng giá TẠI THỜI ĐIỂM TÍNH LƯƠNG.

    `don_vi` ở lại vì phép đo GIỜ cần nó làm ĐÍCH quy đổi mặc định (xem
    `test_snapshot_giu_don_vi_lam_DICH_do_gio`), không vì tiền.
    """
    snap = khoan_snapshot(BE_MAY)
    assert snap == {"rate_id": 3, "ten": "Bế máy", "don_vi": "tờ"}


def test_snapshot_khong_ghim_don_gia_cong_thuc_ra_tien():
    class _Dm:
        cong_thuc_khoan = "50000 + don_gia_khoan * sl_ra"
        cong_thuc_gio = "sl_vao"

    snap = khoan_snapshot(BE_MAY, _Dm())

    assert snap["rate_id"] == 3 and snap["ten"] == "Bế máy"
    for khoa in ("don_gia", "cong_thuc"):
        assert khoa not in snap, khoa
    # Dấu "ảnh chụp MỚI, biết ô đo giờ riêng" phải còn — `dich_gio_cua_khoan` gác luật theo nó.
    assert snap["cong_thuc_gio"] == "sl_vao"


def test_snapshot_giu_don_vi_lam_DICH_do_gio():
    """⭐ Bỏ `don_vi` khỏi ảnh chụp là mọi bước Tổ chưa khai đơn vị năng suất về 0 phút.

    `dich_gio_cua_khoan` lùi về `don_vi` khi đầu việc để trống `don_vi_nang_suat`; tịt đích thì
    `sl_tinh_cua_buoc` trả None, bước hiện 0 phút và Xếp lịch chặn đặt lịch mà không nói vì sao.
    Đây là lý do DUY NHẤT khoá ấy còn trong ảnh chụp — nó là ĐƠN VỊ, đi một mình, không kèm giá.
    """
    from app.services.lsx_service import dich_gio_cua_khoan

    class _Dm:
        cong_thuc_gio = ""
        don_vi_nang_suat = None

    snap = khoan_snapshot(BE_MAY, _Dm())
    assert dich_gio_cua_khoan(snap) == ("tờ", "")


def test_snapshot_phat_hanh_khong_gan_don_gia_hd():
    """Lúc PHÁT HÀNH cũng không gắn `don_gia_hd` (đơn giá hiệu dụng) vào ảnh chụp nữa.

    Ảnh chụp cũ trong DB còn khoá tiền (không migrate JSON) nên bài này đưa vào một ảnh chụp KIỂU
    CŨ: hàm phải trả lại đúng nó, không thêm khoá nào.
    """
    from app.services.san_xuat.snapshot import _SoPhatHanh

    cu = {"rate_id": 3, "ten": "Bế máy", "don_vi": "tờ", "don_gia": 250.0,
          "cong_thuc": "50000 + don_gia_khoan * sl_ra"}
    cd = SimpleNamespace(khoan_json=dict(cu), cong_doan_id=None, department_id=11)

    ra = _SoPhatHanh(None).khoan_json(cd, lsx_id=None)

    assert ra == cu
    assert "don_gia_hd" not in ra
