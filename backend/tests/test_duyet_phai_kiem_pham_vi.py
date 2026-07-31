"""Lưới an toàn: MỌI hàm duyệt/từ chối trong `app/services` phải nhận `scope`.

Ngày 29/07/2026 chủ báo *"tổ trưởng duyệt được tăng ca của tổ khác nếu biết mã phiếu"*. Truy ra
**bốn** chỗ cùng một bệnh — tăng ca, nghỉ phép, tạm ứng, YC cập nhật hồ sơ. Cùng một nguyên nhân:

    ô quyền `approve` chỉ trả lời "ĐƯỢC DUYỆT KHÔNG", không trả lời "ĐƯỢC DUYỆT CHO AI".

Đường ĐỌC đã lọc phạm vi nên trên màn không thấy phiếu tổ khác — nhưng đó là **che mắt, không
phải khoá**: gọi thẳng API kèm mã phiếu là duyệt được.

Test này quét toàn bộ `app.services` để bệnh đó không tái phát ở module viết SAU. Ai thêm luồng
duyệt mới mà quên `scope` sẽ thấy test đỏ ngay, kèm tên hàm.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

import app.services

# Hàm mang một trong các tên này = một quyết định GHI lên hồ sơ/phiếu của NGƯỜI KHÁC.
_TEN_HAM_DUYET = re.compile(r"^_?(decide|approve|reject|bulk_approve|bulk_reject)")

# --- MIỄN TRỪ ---------------------------------------------------------------
# Chỉ thêm vào đây khi hàm THẬT SỰ không có trục nhân viên để chặn theo tổ. Mỗi dòng PHẢI kèm lý
# do — để việc miễn trừ là quyết định có ý thức, không phải chỗ giấu lỗi.
MIEN_TRU = {
    # Duyệt YÊU CẦU MUA HÀNG: trục là phòng ban đặt hàng, không phải hồ sơ nhân viên.
    ("PurchaseService", "approve"),
    ("PurchaseService", "reject"),
    # Kế toán: duyệt YC mua rồi sinh phiếu chi — cùng trục với PurchaseService.
    ("AccountingService", "approve_and_create_voucher"),
    # Đơn hàng bán: ĐÃ nhận `scope` nhưng trục là khách hàng/đơn (sale_user_id), không phải NV.
    # Giữ trong danh sách để ai đọc biết là đã soi, không phải sót.
}

# --- LỖ ĐÃ BIẾT, CHƯA VÁ ----------------------------------------------------
# TÁCH RỔ RIÊNG với `MIEN_TRU` là có chủ đích. Hai thứ khác hẳn nhau:
#   MIEN_TRU   = đã soi, KHÔNG có gì để chặn.
#   LO_CHUA_VA = CÓ lỗ thật, biết rồi, cố ý chưa vá.
# Nhét chung một rổ là biến "an toàn" và "đang thủng" thành một — đúng kiểu giấu lỗi mà chính
# test này sinh ra để chống. Tên biến phải nói thật.
#
# Mỗi mục PHẢI ghi: thủng ở đâu, vá thế nào, vì sao chưa vá.
LO_CHUA_VA = {
    # ĐỀ NGHỊ KHO — `routers/kho_request.py::_act` (trình duyệt / duyệt / từ chối / huỷ) lấy phiếu
    # THẲNG theo id, không kiểm phạm vi; trong khi `list` có lọc (`_scoped_filters`). Ai có
    # `kho:approve` là duyệt được đề nghị của bộ phận khác chỉ cần biết mã phiếu — cùng bệnh với
    # tăng ca (mục C-2 trong `docs/RA_SOAT_NHAN_SU_LUONG.md`).
    #
    # CÁCH VÁ: một dòng — gọi `_require_visible(req, user, authz)` trong `_act`. Hàm chặn ĐÃ CÓ
    # SẴN ngay trong file đó, chỉ đang được gọi ở mỗi endpoint xem chi tiết.
    #
    # VÌ SAO CHƯA VÁ: ngoài phạm vi đợt Nhân sự & Lương (chủ 30/07/2026). Chi tiết + cái bẫy
    # 10-test-đỏ khi vá: xem mục C-2c trong `docs/RA_SOAT_NHAN_SU_LUONG.md`.
    ("StockRequestService", "approve"),
    ("StockRequestService", "reject"),
}


def _cac_ham_duyet():
    """(tên class, tên hàm, chữ ký) của mọi hàm duyệt trong app/services."""
    ra = []
    for mod in pkgutil.iter_modules(app.services.__path__):
        m = importlib.import_module(f"app.services.{mod.name}")
        for ten_class, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ != m.__name__:      # class import từ nơi khác — bỏ
                continue
            for ten_ham, fn in inspect.getmembers(cls, inspect.isfunction):
                if _TEN_HAM_DUYET.match(ten_ham):
                    ra.append((ten_class, ten_ham, inspect.signature(fn)))
    return ra


def test_moi_ham_duyet_deu_nhan_scope():
    """⭐ Thiếu `scope` = có đường duyệt vượt tổ. Đỏ ở đây nghĩa là vừa mở lại lỗ C-2."""
    thieu = [
        f"{c}.{h}"
        for c, h, sig in _cac_ham_duyet()
        if (c, h) not in (MIEN_TRU | LO_CHUA_VA) and "scope" not in sig.parameters
    ]
    assert not thieu, (
        "Các hàm duyệt sau KHÔNG nhận `scope` ⇒ người có quyền duyệt sẽ duyệt được cho NGƯỜI "
        "NGOÀI TỔ chỉ cần biết mã phiếu:\n  - " + "\n  - ".join(sorted(thieu))
        + "\n\nCách sửa: nhận `scope` rồi gọi `employees.can_access(...)` trước khi ghi — xem "
          "`late_early_service._guard_scope`. Nếu hàm thật sự không có trục nhân viên thì thêm "
          "vào `MIEN_TRU`. Biết thủng mà chưa vá ngay được ⇒ `LO_CHUA_VA`. Cả hai PHẢI kèm lý do."
    )


def test_ro_no_khong_duoc_phinh_to_lang_le():
    """⭐ `LO_CHUA_VA` là NỢ, không phải chỗ đổ rác.

    Ghim đúng danh sách hiện tại: thêm mục mới vào rổ nợ sẽ làm test đỏ, buộc người thêm phải sửa
    cả test này — tức một hành động CÓ Ý THỨC, có người soi, chứ không lặng lẽ giấu thêm một lỗ
    nữa. Vá xong mục nào thì xoá khỏi rổ, test lại xanh."""
    assert LO_CHUA_VA == {
        ("StockRequestService", "approve"),
        ("StockRequestService", "reject"),
    }, (
        "Rổ LỖ CHƯA VÁ vừa đổi. Thêm mục = đang ghi nhận một lỗ MỚI ⇒ phải ghi lý do ngay tại chỗ "
        "khai VÀ vào `docs/RA_SOAT_NHAN_SU_LUONG.md`. Bớt mục = đã vá ⇒ cập nhật tài liệu."
    )


def test_scope_la_tham_so_BAT_BUOC_o_bon_luong_da_va():
    """⭐ Bốn luồng vừa vá phải để `scope` KHÔNG có giá trị mặc định.

    Cho mặc định (`scope=None` rồi `if scope is None: return`) chính là cơ chế đã để bốn chỗ này
    thủng mà không ai biết: quên truyền thì lặng lẽ bỏ qua kiểm tra. Bắt buộc khai thì quên là
    chương trình báo lỗi ngay lần chạy đầu."""
    can_bat_buoc = {
        ("OvertimeService", "approve"), ("OvertimeService", "reject"),
        ("OvertimeService", "bulk_approve"), ("OvertimeService", "bulk_reject"),
        ("OvertimeService", "_decide"),
        ("LeaveService", "approve"), ("LeaveService", "reject"),
        ("LeaveService", "bulk_approve"), ("LeaveService", "bulk_reject"),
        ("LeaveService", "_decide"),
        ("PayrollService", "decide_advance"),
        ("EmployeeService", "decide_update_request"),
    }
    thay = {(c, h): sig for c, h, sig in _cac_ham_duyet()}
    for khoa in sorted(can_bat_buoc):
        sig = thay.get(khoa)
        assert sig is not None, f"{khoa[0]}.{khoa[1]} biến mất — đổi tên thì cập nhật test này"
        p = sig.parameters.get("scope")
        assert p is not None, f"{khoa[0]}.{khoa[1]} thiếu `scope`"
        assert p.default is inspect.Parameter.empty, (
            f"{khoa[0]}.{khoa[1]} cho `scope` một giá trị mặc định — quên truyền là thủng im lặng"
        )
