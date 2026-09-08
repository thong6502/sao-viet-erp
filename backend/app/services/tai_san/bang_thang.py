"""Bảng khấu hao / phân bổ của MỘT THÁNG — tính tại chỗ từ sổ, không lưu, không chốt.

Thay cho `ky_service.py` (tính · chốt · mở kỳ) từ 08/09/2026. Kế toán chọn tháng, nhìn bảng, xuất
Excel rồi gõ sang phần mềm kế toán; hỏi lại tháng đó lúc nào cũng ra đúng một số vì số đến từ
lịch của từng tài sản (`khau_hao.py`), không từ dòng đã ghi.

Mỗi dòng kèm `so_luong` (lô mấy cái), `su_kien` (chip ngắn + câu đầy đủ khi tháng đó có chuyện:
nâng cấp, điều chuyển, tháng đầu lẻ ngày, tháng cuối…) và `dien_giai` (các câu nối lại — cột
Excel). Chủ chốt 08/09/2026: hai tab phải liên quan đến nhau, đổi số thì phải nói số trước → sau.
Dòng cũ đã ghi giảm (nghiệp vụ đã bỏ) thì tháng giảm `con_lai` = 0 — món đã ra khỏi sổ.

Bộ phận chịu chi phí = bộ phận ĐANG giữ tài sản lúc xem bảng (điều chuyển không giữ lịch sử
theo tháng — chủ chốt phạm vi hẹp, đủ cho bảng in cuối tháng).
"""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...models.department import Department
from ...models.tai_san import TaiSan
from ...repositories.tai_san_repo import TaiSanRepository
from .khau_hao import DongThang
from .service import TaiSanService, mocs_cua, muc_thang, ngay_giam_cua


def bang_thang(db: Session, nam: int, thang: int) -> list[dict]:
    """Đúng những cột màn hình và file Excel cần, không hơn. Tài sản không trích tháng đó (chưa
    tới mốc, đã hết giá trị, đã giảm từ tháng trước) thì không có dòng."""
    if not (1 <= int(thang) <= 12):
        raise ValueError("Tháng phải trong 1–12")
    svc = TaiSanService(TaiSanRepository(db))
    rows = list(
        db.execute(
            select(TaiSan, Department.name)
            .outerjoin(Department, Department.id == TaiSan.bo_phan_id)
            .options(selectinload(TaiSan.moc), selectinload(TaiSan.bien_dong))
            .order_by(TaiSan.ma)
        )
    )
    ra: list[dict] = []
    for t, ten_bp in rows:
        muc, luy_ke = muc_thang(mocs_cua(t), nam, thang, ngay_giam=ngay_giam_cua(t))
        if muc <= 0:
            continue
        dong = svc.dong_hien_thi(
            t, DongThang(nam, thang, int(muc), int(luy_ke), int(t.nguyen_gia or 0) - int(luy_ke))
        )
        theo_thang = svc.su_kien_theo_thang(t)
        ra.append({
            "tai_san_id": t.id,
            "ma": t.ma,
            "ten": t.ten,
            "loai": t.loai,
            "so_luong": int(t.so_luong or 0),
            "bo_phan_ten": ten_bp,
            "nguyen_gia": int(t.nguyen_gia or 0),
            "muc_trich": dong.muc_trich,
            "luy_ke": dong.luy_ke,
            "con_lai": dong.con_lai,
            "su_kien": [asdict(s) for s in svc.su_kien_dong(dong, theo_thang)],
            "dien_giai": svc.dien_giai_dong(dong, theo_thang),
        })
    return ra
