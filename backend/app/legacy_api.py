r"""Ba mặt API ĐỜI CŨ còn mount nhưng không ai gọi — `machines` · `operations` ·
`product-types-catalog`.

## Vì sao phải tách ra một ô quyền riêng

Ba router này CHỈ ĐỌC, và cho tới 15/08/2026 chúng dùng CHUNG ô quyền với ba màn danh mục đời
mới: `machines`→`dm_thiet_bi`, `operations`→`dm_cong_doan`, `product-types-catalog`→
`dm_loai_san_pham`. Nghĩa là tick MỘT ô quyền để mở màn Công đoạn thì mở luôn một mặt API thứ hai
đọc bảng khác, mà người cấp quyền không hề biết mình vừa mở cái gì.

## Số đo trước khi đổi (15/08/2026)

* Frontend gọi ba đường này: **0** (`grep -rn "api/machines\|api/operations\|product-types"` trên
  `frontend/src` — hai hit duy nhất là tên trường `applicable_product_types` trong `client.ts`,
  không liên quan).
* Service/engine nào tiêu thụ `MachineService` · `OperationService` ·
  `ProductTypeCatalogService`: **0** ngoài chính ba router (grep chỉ ra `deps.py` nối dây và
  chính file service). Câu "the pricing engine and Báo giá consume machines through the
  list/detail endpoints below" trong docstring `machines.py` là LỖI THỜI.
* Test đụng ba đường: **1 file** (`tests/test_machines_and_operations.py`, 2 test).

Lưu ý: bảng dữ liệu KHÔNG rỗng (`seed.py` còn seed bảng `machines`), nên đây tuyệt đối KHÔNG phải
lệnh xoá bảng. Xoá bảng không nằm trong kế hoạch này.

## Trạng thái hiện tại: NGỪNG DÙNG, chưa xoá

`LEGACY_READONLY` cố ý **KHÔNG** có trong `seed.MODULES`. Vai `Giám đốc` được cấp
`_full(SCOPE_ALL)` cho MỌI khoá trong `MODULES` (`seed.py`), nên thêm khoá này vào đó là tự tay
cấp lại đúng thứ vừa gỡ. Không có dòng quyền nào ⇒ `AuthorizationService.can()` trả `False` cho
mọi vai ⇒ ba đường trả **403 cho tất cả**, kể cả admin. Đó là ý đồ.

**Đảo lại bằng ĐÚNG một dòng**: thêm `("legacy_readonly", "API đời cũ (chỉ đọc)")` vào `MODULES`
trong `seed.py`. Vai Giám đốc nhận quyền ngay ở lần seed kế tiếp.

Bước sau (chờ ≥1 kỳ chạy thật mà không ai kêu thiếu): mới bàn tới gỡ router. Đừng gộp hai bước.
"""
from __future__ import annotations

#: Ô quyền riêng cho ba mặt API đời cũ. KHÔNG seed ⇒ mặc định không vai nào có.
LEGACY_READONLY = "legacy_readonly"
