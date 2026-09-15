"""Tệp đính kèm của lệnh, đọc từ Bàn tổ.

Kế hoạch SX đính kèm tệp vào LỆNH (`LsxDinhKemService`, gác module `san_xuat`). Tổ dưới xưởng vào
bằng quyền theo tổ (mg 0302), không có module đó, nên đọc qua CÔNG VIỆC họ đang thấy — cùng cổng
với drawer (`board.chi_tiet_cong_viec`), thêm điều kiện gói còn phát hành. Chỉ đọc.

Tải/xem tệp đi `/api/files`, nhánh `san-xuat/` đã mở cho người có quyền Xem ở một tổ.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.user import User
from ...repositories.lsx_dinh_kem_repo import LsxDinhKemRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..lsx_dinh_kem import LsxDinhKemService
from ..quyen_to import MUC_CUA_TOI
from .board import _loc_viec_cua_tho, _pham_vi_doc


def tep_cua_cong_viec(db: Session, user: User, *, cong_viec_id: int) -> list[dict]:
    """Tệp của (các) lệnh mà công việc thuộc về, gom theo lệnh, sắp theo mã lệnh.

    Công việc bài ghép trả MỌI lệnh thành viên — tờ in chung thì maket của lệnh nào cũng cần.
    Lệnh không có tệp vẫn có nhóm (`items` rỗng) để màn nói rõ "chưa có tệp"."""
    repo = SanXuatRepository(db)
    cv = SanXuatThucThiRepository(db).cong_viec(cong_viec_id)
    if cv is None or not repo.goi_dang_phat_hanh(cv.goi_id):
        raise ValueError("Không tìm thấy công việc.")
    _q, muc = _pham_vi_doc(db, user, cv.department_id)
    if muc == MUC_CUA_TOI and not _loc_viec_cua_tho(db, user, [cv]):
        raise PermissionError("Chỉ xem được việc đã giao cho mình.")

    lsx_ids = repo.lsx_ids_cua_bai_ghep({cv.bai_ghep_id}) if cv.bai_ghep_id else {cv.lsx_id}
    nhan = repo.lsx_nhan({i for i in lsx_ids if i})
    dk = LsxDinhKemRepository(db)
    rows = dk.list_by_lsx_ids(set(nhan))
    ten = dk.ten_nguoi({r.nguoi_tai_id for r in rows if r.nguoi_tai_id})

    nhom = {
        lsx_id: {"lsx_id": lsx_id, "lsx_ma": ma, "lsx_ten": ten_lenh, "items": []}
        for lsx_id, (ma, ten_lenh) in nhan.items()
    }
    for r in rows:
        nhom[r.lsx_id]["items"].append(LsxDinhKemService._dict(r, ten.get(r.nguoi_tai_id)))
    return sorted(nhom.values(), key=lambda n: n["lsx_ma"])
