"""Router màn "Lệnh sản xuất" — bàn của điều độ / kế hoạch SX (Task 9).

Prefix `/api/lenh-san-xuat`. RBAC MODULE = `lenh_san_xuat` (module RIÊNG, không dùng chung
`san_xuat` của `routers/lsx.py`: bên kia là bàn TẠO lệnh, bên này là bàn THEO DÕI lệnh đã phát
hành — cùng dữ liệu nhưng khác người, khác quyền).

--- PHẠM VI LẤY TỪ TOKEN, KHÔNG BAO GIỜ TỪ URL --------------------------------------------------
Router KHÔNG nhận bất kỳ tham số nào cho phép người gọi tự nới phạm vi. `sale_ids` luôn do
`pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)` sinh ra từ scope của chính token đang
dùng. Gửi thêm `?sale_user_id=...` vào đây thì FastAPI bỏ qua — không có tham số nào tên như thế,
và cũng đừng ai thêm vào. Bài canh: `test_client_khong_tu_noi_pham_vi`.

Cùng lý do đó, `summary` KHÔNG có cửa "xem toàn nhà máy": KPI phải hẹp đúng bằng bảng bên dưới,
nếu không người đọc thấy một con số mà không có cách nào lần ra nó gồm những lệnh nào.

Đường TĨNH (`/summary`) khai TRƯỚC đường gốc, và phải giữ thói quen đó: FastAPI khớp route theo
THỨ TỰ KHAI, nên khi Task sau thêm `/{lsx_id}` (màn chi tiết) vào file này, `/summary` đã nằm sẵn
ở trên — thêm vào dưới là xong. Khai ngược lại thì `/summary` bị `/{lsx_id}` nuốt và người dùng
nhận 422 "lsx_id không phải số".

Router CHỈ điều phối: đọc scope, chuyển tham số, trả schema. Toàn bộ nghiệp vụ (lọc hai tầng, tính
trạng thái, KPI) nằm ở `services/lenh_sx/danh_sach.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.user import User
from ..schemas.lenh_san_xuat import LenhSxListOut, LenhSxSummaryOut
from ..services.lenh_sx import danh_sach, pham_vi
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/lenh-san-xuat", tags=["lenh-san-xuat"])
MODULE = "lenh_san_xuat"
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]

# Khai kiểu `Literal` để giá trị lạ bị chặn ở CỬA bằng 422, thay vì lọt xuống service rồi lặng lẽ
# trả về danh sách rỗng — "không có lệnh nào" và "bạn gõ sai tên tab" là hai câu trả lời khác nhau.
#
# Dựng từ chính hằng của service chứ không gõ lại chuỗi: `Literal[X]` với `X` là TUPLE tương đương
# `Literal[*X]` ở runtime (đúng cách Python vẫn nhận `Literal["a","b"]`). Gõ lại danh sách ở đây là
# tự đặt bẫy — thêm tab thứ bảy vào `trang_thai.TAB_CHINH` mà quên router thì tab mới trả 422 mà
# không ai hiểu vì sao.
Tab = Literal[danh_sach.TAB_CHO_PHEP]
UuTien = Literal[danh_sach.UU_TIEN_CHO_PHEP]


@router.get("/summary", response_model=LenhSxSummaryOut)
def summary(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    """Bốn thẻ KPI đầu màn, tính theo NGÀY GIỜ XƯỞNG (+7). Xem `danh_sach.summary`."""
    sale_ids = pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)
    return danh_sach.summary(db, sale_ids=sale_ids)


@router.get("", response_model=LenhSxListOut)
def danh_sach_lenh(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    tab: Tab | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=danh_sach.PAGE_SIZE_TOI_DA)
    ] = danh_sach.PAGE_SIZE_MAC_DINH,
    nhom_cong_doan: Annotated[str | None, Query(max_length=24)] = None,
    may_id: int | None = None,
    uu_tien: UuTien | None = None,
    tre: bool | None = None,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
):
    """Bảng lệnh đã phát hành, đã lọc, đã đếm theo tab và đã CẮT TRANG ở máy chủ.

    `tab` và `tre` là bộ lọc DẪN XUẤT (không có cột nào để `WHERE`) — chúng được áp ở tầng 2, sau
    một lượt nạp bối cảnh cho cả tập. Chi tiết và chi phí: docstring `services/lenh_sx/danh_sach`.
    """
    sale_ids = pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)
    return danh_sach.danh_sach(
        db,
        sale_ids=sale_ids,
        tab=tab,
        q=q,
        page=page,
        page_size=page_size,
        nhom_cong_doan=nhom_cong_doan,
        may_id=may_id,
        uu_tien=uu_tien,
        tre=tre,
        tu_ngay=tu_ngay,
        den_ngay=den_ngay,
    )
