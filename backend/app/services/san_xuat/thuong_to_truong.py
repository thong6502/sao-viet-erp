"""§8 — THƯỞNG/PHẠT TỔ TRƯỞNG theo chất lượng, chạy lúc ĐÓNG NHÓM thành phẩm.

Chủ chốt 04/09/2026: *"xong lệnh nào là biết sản lượng cá nhân và số tiền tương ứng luôn"* +
*"tỉ lệ lỗi lấy từ phiếu KCS"*. Trước hôm nay `PieceWorkService.leader_bonus_pct/_amount` đã có
đủ phép tính nhưng KHÔNG AI GỌI — bảng bậc thưởng khai xong nằm im. Module này là đoạn dây nối:

    đóng nhóm  →  gom sản lượng + tiền khoán từng tổ  →  gom lỗi KCS quy cho tổ đó
               →  tra bảng bậc  →  ghi một dòng ± cho TỔ TRƯỞNG  →  cột lương `thuong_to_truong`

Vì sao neo vào lúc ĐÓNG NHÓM chứ không vào lúc chạy bảng lương: cổng đóng nhóm (§16) đã đòi đúng
những thứ phép thưởng cần đúng — mọi việc hoàn thành · phân bổ đã CHỐT · hết lỗi KCS chờ tổ phản
hồi · kho xong. Tính ở bảng lương thì phải tự dựng lại cả bốn điều kiện đó, và tính vào ngày 5
tháng sau thì tổ trưởng không còn nối được tiền với mẻ hàng nào.

Ghi MỘT LẦN, không tính lại: sửa bậc thưởng hay đổi tổ trưởng về sau không viết lại dòng đã ghi
(cùng nguyên tắc đóng băng của `san_xuat_phan_bo_dong`). Nhóm đã có dòng cho tổ nào thì bỏ qua tổ
đó — `ghi()` gọi lại bao nhiêu lần cũng ra cùng một kết quả.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.payroll import PERIOD_LOCKED, PERIOD_PAID, PayrollPeriod
from ...models.san_xuat_thuong_to_truong import SanXuatThuongToTruong
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.piece_work_repo import PieceWorkRepository
from ...repositories.thuong_to_truong_repo import ThuongToTruongRepository
from ..piece_work_service import PieceWorkService

_EPS = 1e-9


def _r(x) -> float:
    return round(float(x or 0) + 0.0, 2)


def _ky_da_khoa(db: Session, nam: int, thang: int) -> bool:
    """Kỳ lương đã khoá/đã chi ⇒ không nhét thêm tiền vào (§12.3, y hệt `phan_bo._ky_da_khoa`)."""
    return db.scalar(
        select(PayrollPeriod.status).where(
            PayrollPeriod.year == nam, PayrollPeriod.month == thang
        )
    ) in (PERIOD_LOCKED, PERIOD_PAID)


def _ky_nhan_tien(db: Session, ngay: date) -> tuple[int, int, str | None]:
    """Kỳ lương ăn khoản này. Kỳ của ngày đóng đã khoá ⇒ ĐẨY sang kỳ mở kế tiếp, có ghi chú.

    Đúng lối bù trừ mà `phan_bo.bu_tru` đã mở sẵn ("kỳ gốc khoá thì bù ở kỳ đang mở"): nhóm đóng
    muộn sau khi kế toán đã khoá sổ vẫn phải trả tiền, chỉ là trả ở kỳ sau — chứ không im lặng rơi
    vào một kỳ đã chi rồi (tiền bốc hơi) và cũng không chặn việc đóng nhóm (chuyện của sản xuất
    không được kẹt vì sổ lương). Dò tối đa 12 tháng rồi thôi: khoá liền 12 kỳ là hệ đang hỏng,
    ghi vào kỳ cuối cùng dò được còn hơn treo vô hạn."""
    nam, thang = ngay.year, ngay.month
    if not _ky_da_khoa(db, nam, thang):
        return nam, thang, None
    goc = f"{ngay.month:02d}/{ngay.year}"
    for _ in range(12):
        thang += 1
        if thang > 12:
            thang, nam = 1, nam + 1
        if not _ky_da_khoa(db, nam, thang):
            break
    return nam, thang, f"Kỳ {goc} đã khoá — chuyển sang kỳ {thang:02d}/{nam}."


def tinh(db: Session, nhom_id: int) -> list[dict]:
    """XEM TRƯỚC (không ghi): mỗi tổ có sản lượng trong nhóm ⇒ một dòng thưởng/phạt dự kiến.

    Tổ CHƯA khai bảng bậc thì không có dòng và cũng không phải lỗi — nhiều tổ (kho, KCS…) vốn
    không nằm trong chính sách thưởng theo tỷ lệ lỗi. Muốn tổ được xét thì khai bậc cho tổ đó ở
    màn Cấu hình lương → Thưởng/phạt tổ trưởng."""
    repo = ThuongToTruongRepository(db)
    piece = PieceWorkService(PieceWorkRepository(db))
    san_luong = repo.san_luong_theo_to(nhom_id)
    loi = repo.loi_theo_to(nhom_id)

    out: list[dict] = []
    for dept_id in sorted(san_luong):
        sl, tien = san_luong[dept_id]
        if sl <= _EPS:
            continue
        brackets = piece.leader_brackets(dept_id)
        if not brackets:
            continue
        so_loi = float(loi.get(dept_id, 0.0))
        ty_le = so_loi / sl * 100.0
        rate = PieceWorkService.leader_bonus_pct(sl, ty_le, brackets)
        dept = db.get(Department, dept_id)
        out.append({
            "department_id": dept_id,
            "department": getattr(dept, "name", None),
            "head_user_id": getattr(dept, "head_user_id", None),
            "san_luong": round(sl, 3),
            "tien_khoan": _r(tien),
            "so_luong_loi": round(so_loi, 3),
            "ty_le_loi": round(ty_le, 4),
            "rate_pct": float(rate),
            "so_tien": _r(tien * rate / 100.0),
        })
    return out


def ghi(db: Session, *, nhom_id: int, actor=None) -> list[SanXuatThuongToTruong]:
    """Ghi dòng thưởng/phạt cho MỌI tổ chưa có dòng trong nhóm. KHÔNG commit — người gọi commit.

    Không commit là cố ý: hàm này chạy bên trong giao dịch đóng nhóm, phải đóng-và-thưởng cùng
    một lần ghi. Đóng được mà thưởng rớt (hay ngược lại) là trạng thái không sửa lại được bằng
    thao tác người dùng nào cả."""
    repo = ThuongToTruongRepository(db)
    da_co = {r.department_id for r in repo.cua_nhom(nhom_id)}
    ngay = date.today()
    ky_nam, ky_thang, ghi_chu_ky = _ky_nhan_tien(db, ngay)

    them: list[SanXuatThuongToTruong] = []
    for d in tinh(db, nhom_id):
        if d["department_id"] in da_co:
            continue
        head_id = d["head_user_id"]
        emp = repo.employee_cua_user(head_id) if head_id else None
        ghi_chu = ghi_chu_ky
        if head_id is None:
            ghi_chu = _noi(ghi_chu, "Tổ chưa có tổ trưởng — tiền chưa có người nhận.")
        elif emp is None:
            ghi_chu = _noi(ghi_chu, "Tổ trưởng chưa nối hồ sơ nhân sự — bảng lương chưa nhận được.")
        them.append(repo.add(SanXuatThuongToTruong(
            nhom_id=nhom_id,
            department_id=d["department_id"],
            head_user_id=head_id,
            employee_id=getattr(emp, "id", None),
            ngay=ngay,
            ky_nam=ky_nam,
            ky_thang=ky_thang,
            san_luong=d["san_luong"],
            tien_khoan=d["tien_khoan"],
            so_luong_loi=d["so_luong_loi"],
            ty_le_loi=d["ty_le_loi"],
            rate_pct=d["rate_pct"],
            so_tien=d["so_tien"],
            ghi_chu=ghi_chu,
            created_by_id=getattr(actor, "id", None),
        )))

    if them:
        db.flush()
        AuditLogRepository(db).create(
            actor_user_id=getattr(actor, "id", None),
            action="san_xuat.thuong_to_truong.ghi",
            target=f"san_xuat_nhom:{nhom_id}",
            detail="; ".join(
                f"to={r.department_id} sl={float(r.san_luong):g} loi={float(r.ty_le_loi):g}% "
                f"{float(r.rate_pct):+g}% => {float(r.so_tien):+,.0f}đ"
                for r in them
            ),
        )
    return them


def xem(db: Session, nhom_id: int) -> list[dict]:
    """Cho FE: dòng ĐÃ GHI nếu nhóm đã đóng, còn không thì bản XEM TRƯỚC tính-lúc-đọc.

    Một cửa chứ không hai: tổ trưởng nhìn cùng một bảng trước và sau khi đóng, chỉ khác cờ `da_ghi`
    — nếu số nhảy giữa hai lần nhìn thì đó là dữ liệu vào thay đổi (thêm mẻ, KCS ghi thêm lỗi), chứ
    không phải hai phép tính khác nhau."""
    da_ghi = ThuongToTruongRepository(db).cua_nhom(nhom_id)
    if da_ghi:
        ten = {
            d.id: d.name
            for d in db.scalars(select(Department).where(
                Department.id.in_([r.department_id for r in da_ghi])
            ))
        }
        return [{
            "department_id": r.department_id,
            "department": ten.get(r.department_id),
            "san_luong": float(r.san_luong or 0),
            "tien_khoan": float(r.tien_khoan or 0),
            "so_luong_loi": float(r.so_luong_loi or 0),
            "ty_le_loi": float(r.ty_le_loi or 0),
            "rate_pct": float(r.rate_pct or 0),
            "so_tien": float(r.so_tien or 0),
            "ghi_chu": r.ghi_chu,
            "da_ghi": True,
        } for r in da_ghi]
    return [{**d, "ghi_chu": None, "da_ghi": False} for d in tinh(db, nhom_id)]


def _noi(a: str | None, b: str) -> str:
    return f"{a} {b}" if a else b
