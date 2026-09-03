"""Router màn "Hồ sơ lệnh sản xuất" — bàn của điều độ / kế hoạch SX (Task 9).

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

Mọi đường TĨNH (`/summary`, `/bo-loc`) khai TRƯỚC `/{lsx_id}`, và phải giữ thói quen đó: FastAPI
khớp route theo THỨ TỰ KHAI. Khai ngược lại thì đường tĩnh bị `/{lsx_id}` nuốt và người dùng nhận
422 "lsx_id không phải số" cho một URL hoàn toàn đúng. Bài canh:
`test_bo_loc_khong_bi_route_dong_nuot`.

Router CHỈ điều phối: đọc scope, chuyển tham số, trả schema. Toàn bộ nghiệp vụ (lọc hai tầng, tính
trạng thái, KPI) nằm ở `services/lenh_sx/danh_sach.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_authorization_service, require_permission
from ..models.user import User
from ..schemas.lenh_san_xuat import (
    LenhSxBoLocOut, LenhSxHoSoOut, LenhSxListOut, LenhSxSummaryOut,
)
from ..services.lenh_sx import danh_sach, ho_so, pham_vi, phieu_cong_nghe
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


@router.get("/bo-loc", response_model=LenhSxBoLocOut)
def bo_loc(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    """Nguồn cho ô lọc **Máy** — chỉ máy CÓ THẬT trong tập lệnh của người gọi.

    Đường TĨNH, nên phải nằm TRÊN `/{lsx_id}` (xem docstring đầu file): khai xuống dưới thì route
    động nuốt mất và người dùng nhận 422 "lsx_id không phải số" cho một URL hoàn toàn đúng.

    Gác bằng chính `lenh_san_xuat:read` chứ KHÔNG mượn `/api/may-thiet-bi`: endpoint danh mục máy
    đòi `dm_thiet_bi:read` hoặc `tinh_gia_thanh:read`, mà vai QC — vai đứng ở màn này nhiều nhất —
    không có ô nào trong hai ô ấy. Lý do đầy đủ ở `danh_sach.bo_loc`.
    """
    sale_ids = pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)
    return danh_sach.bo_loc(db, sale_ids=sale_ids)


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


@router.get("/{lsx_id}", response_model=LenhSxHoSoOut)
def ho_so_lenh(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    lsx_id: int,
):
    """Hồ sơ đầy đủ MỘT lệnh: 13 khối cho màn chi tiết, thuần đọc, không ghi gì.

    Khai SAU `/summary` là bắt buộc (xem docstring đầu file). `lsx_id` chỉ là ĐỊA CHỈ, không phải
    quyền: `sale_ids` vẫn sinh từ token, và `ho_so` sẽ trả 404 nếu lệnh không tồn tại / chưa phát
    hành, 403 nếu lệnh có thật nhưng nằm ngoài phạm vi người gọi — thân lỗi không kèm nội dung
    lệnh, để người ngoài phạm vi không dò được thông tin qua thông báo lỗi.
    """
    sale_ids = pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)
    return ho_so.ho_so(db, lsx_id, sale_ids=sale_ids)


@router.get(
    "/{lsx_id}/phieu-cong-nghe.pdf",
    response_class=Response,
    # KHAI CHO ĐÚNG SỰ THẬT: không có `response_model` thì OpenAPI mặc định ghi 200 là
    # `application/json` — mọi client sinh từ schema (kể cả Swagger UI) sẽ đọc sai kiểu trả về của
    # một endpoint chỉ trả bytes PDF.
    responses={200: {"content": {"application/pdf": {}}, "description": "Phiếu công nghệ A4"}},
)
def phieu_cong_nghe_pdf(
    db: Annotated[Session, Depends(get_db)],
    authz: Authz,
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    lsx_id: int,
):
    """Phiếu công nghệ A4 (Task 13) — bản in cho TỔ SẢN XUẤT, không một số tiền nào.

    ĐÚNG một cửa quyền với `ho_so_lenh` ở trên: `sale_ids` sinh từ token y hệt, và
    `phieu_cong_nghe.render_pdf` gọi thẳng `ho_so.ho_so()` bên trong nên 404/403 nổ ra từ CHÍNH
    phép kiểm đó — router không tự viết lại lượt kiểm quyền thứ hai. Route có thêm một đoạn
    đường dẫn (`/phieu-cong-nghe.pdf`) so với `/{lsx_id}` nên không tranh chấp thứ tự khai với
    hai đường tĩnh `/summary`/`/bo-loc` phía trên.

    `Content-Disposition` mang MÃ LỆNH: không có nó thì mọi phiếu tải về đều tên
    `phieu-cong-nghe.pdf`, và thư mục Downloads của người điều độ thành `(1)`, `(2)`, `(3)` không
    biết tờ nào của lệnh nào. `inline` chứ không `attachment` — bấm In là muốn XEM trước rồi mới
    in, không phải tải file về.
    """
    sale_ids = pham_vi.sale_ids_theo_pham_vi(db, user, authz, MODULE)
    phieu = phieu_cong_nghe.render_pdf(
        db, lsx_id, sale_ids=sale_ids, nguoi_in=user.name or user.username
    )
    return Response(
        content=phieu.noi_dung,
        media_type="application/pdf",
        # Tên file do SERVICE đặt (nó mới có mã lệnh trong tay): router đọc lại `lsx.ma` là mở
        # đường đọc DB thứ hai cho đúng một chuỗi, và là đường KHÔNG đi qua cửa phạm vi.
        headers={"Content-Disposition": f'inline; filename="{phieu.ten_file}"'},
    )
