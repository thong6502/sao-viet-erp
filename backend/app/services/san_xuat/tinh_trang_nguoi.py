"""Thực hiện sản xuất — TÌNH TRẠNG NGƯỜI lúc chọn người giao việc / mời hỗ trợ chéo.

Một nguồn cho ô "Giao người" (§7.1), ô "Thợ hỗ trợ" (§9) và các luật chặn ở mặt ghi. Tổ trưởng cần
thấy ba thứ TRƯỚC khi chọn:
  · đang CHẠY việc nào — khoảng tham gia còn mở, cùng nguồn với hàng rào "không hai khoảng chồng
    giờ" (§7.1);
  · đang CÓ TÊN ở việc nào chưa xong — việc chưa chạy / đang tạm dừng. Giao trước để xếp người,
    chưa phải bận nên KHÔNG chặn, nhưng phải nói rõ việc nào (chỉ một con số thì tổ trưởng không
    biết người đó sắp phải quay về đâu);
  · có đi làm không — hồ sơ nghỉ dài hạn / đình chỉ, hoặc đơn nghỉ phép ĐÃ DUYỆT phủ đúng ngày.
    Đơn còn chờ duyệt không tính: chưa ai chốt người đó nghỉ.

Luật chặn:
  · nghỉ dài hạn, đình chỉ, nghỉ phép đã duyệt đúng ngày ⇒ CHẶN giao, chặn Bắt đầu khi người đó còn
    trong tổ, chặn đề xuất hỗ trợ cho ngày đó;
  · đang chạy việc khác ⇒ chỉ chặn lúc sắp MỞ khoảng tham gia (giao vào việc đang chạy, bấm Bắt
    đầu/Tiếp tục). Giao trước vào việc chưa chạy vẫn được — ô chọn hiện cảnh báo.
Hỗ trợ chéo KHÔNG chặn người đang chạy việc ở tổ mình: thỏa thuận tính theo NGÀY chứ không theo
giờ, sáng đứng máy tổ mình chiều sang giúp tổ khác là chuyện thường — ô chọn chỉ cảnh báo.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ...models.employee import STATUS_ON_LEAVE, STATUS_SUSPENDED, Employee
from ...models.san_xuat import SanXuatCongViec
from ...repositories.leave_repo import LeaveRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..gio_xuong import gio_xuong

# Nhãn ô chọn (danh từ) và vị ngữ câu báo lỗi — cùng một trạng thái hồ sơ.
LY_DO_NGHI = {STATUS_ON_LEAVE: "Nghỉ dài hạn", STATUS_SUSPENDED: "Đang đình chỉ"}
_CAU_NGHI = {STATUS_ON_LEAVE: "đang nghỉ dài hạn", STATUS_SUSPENDED: "đang bị đình chỉ"}

# Đơn nghỉ đã hết trước hôm nay quá cửa sổ này thì ô chọn không cần biết: đề xuất hỗ trợ lùi ngày
# thường chỉ vài hôm. Lùi xa hơn vẫn bị chặn ở máy chủ, chỉ thiếu dòng báo trước trên ô chọn.
_CUA_SO_NGHI_PHEP_NGAY = 31


def hom_nay() -> date:
    """Ngày theo ĐỒNG HỒ XƯỞNG — cùng thang với ngày của mẻ trong phân bổ (`ve_gio_xuong`)."""
    return gio_xuong().date()


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def nhan_viec(db: Session, cvs: list[SanXuatCongViec]) -> dict[int, dict]:
    """{cong_viec_id: {cong_viec_id, ma, ten_cong_doan, to_ten}} — mã lệnh (hoặc bài ghép) + công
    đoạn + tổ, đủ để tổ trưởng biết người đó đang đứng ở đâu."""
    if not cvs:
        return {}
    repo = SanXuatRepository(db)
    lsx = repo.lsx_nhan({c.lsx_id for c in cvs if c.lsx_id})
    bg = repo.bai_ghep_nhan({c.bai_ghep_id for c in cvs if c.bai_ghep_id})
    to = repo.to_ten_nhan({c.department_id for c in cvs if c.department_id})
    ra: dict[int, dict] = {}
    for c in cvs:
        ma = (lsx.get(c.lsx_id, (None, None))[0] if c.lsx_id
              else bg.get(c.bai_ghep_id, (None, None))[0] if c.bai_ghep_id else None)
        ra[c.id] = {
            "cong_viec_id": c.id,
            "ma": ma,
            "ten_cong_doan": c.ten_cong_doan or "",
            "to_ten": to.get(c.department_id) if c.department_id else None,
            "trang_thai": c.trang_thai,
        }
    return ra


def mo_ta_viec(v: dict) -> str:
    """"LSX26-0005 · In offset (Tổ In)" — câu báo lỗi dùng chung một cách gọi tên việc."""
    than = " · ".join(x for x in (v.get("ma"), v.get("ten_cong_doan")) if x) or "một công việc khác"
    return f"{than} ({v['to_ten']})" if v.get("to_ten") else than


def tinh_trang_nhieu(db: Session, emps: list[Employee], *, ngay: date) -> dict[int, dict]:
    """{employee_id: {ly_do_nghi, nghi_phep, dang_chay, viec_cho}} cho ô chọn người.

    `nghi_phep` trả KHOẢNG ngày (không trả cờ "nghỉ hôm nay") vì ô hỗ trợ đổi được ngày làm việc
    ngay trên form — FE tự so với ngày đang chọn, khỏi gọi lại máy chủ mỗi lần đổi ngày."""
    ids = {e.id for e in emps}
    if not ids:
        return {}
    repo = SanXuatThucThiRepository(db)
    chay = repo.viec_dang_chay_cua_nhieu(ids)
    cho = repo.viec_cho_cua_nhieu(ids)
    cvs = {c.id: c for c in chay.values()}
    for ds in cho.values():
        cvs.update((c.id, c) for c in ds)
    nhan = nhan_viec(db, list(cvs.values()))
    phep: dict[int, list[dict]] = {}
    for d in LeaveRepository(db).approved_for_employees(
        ids, tu=ngay - timedelta(days=_CUA_SO_NGHI_PHEP_NGAY)
    ):
        phep.setdefault(d.employee_id, []).append({"tu": d.start_date, "den": d.end_date})
    return {
        e.id: {
            "ly_do_nghi": LY_DO_NGHI.get(e.status),
            "nghi_phep": phep.get(e.id, []),
            "dang_chay": nhan.get(chay[e.id].id) if e.id in chay else None,
            "viec_cho": [nhan[c.id] for c in cho.get(e.id, [])],
        }
        for e in emps
    }


def kiem_di_lam(db: Session, emp: Employee, ngay: date, *, duoi: str) -> None:
    """Chặn người không đi làm ngày `ngay`: hồ sơ nghỉ dài hạn / đình chỉ, hoặc đơn nghỉ phép đã
    duyệt phủ ngày đó. `duoi` là nửa sau câu báo, theo việc đang làm ("không giao việc được"…)."""
    cau = _CAU_NGHI.get(emp.status)
    if cau:
        raise ValueError(f"{emp.full_name} {cau} — {duoi}.")
    if LeaveRepository(db).approved_for_employees({emp.id}, tu=ngay, den=ngay):
        khi = "hôm nay" if ngay == hom_nay() else f"ngày {_dmy(ngay)}"
        raise ValueError(f"{emp.full_name} nghỉ phép {khi} (đơn đã duyệt) — {duoi}.")


def kiem_khong_chay_viec_khac(db: Session, emp: Employee, *, duoi: str) -> None:
    """Chặn mở khoảng tham gia thứ hai cho người đang chạy việc khác (§7.1) — câu báo nói rõ việc
    nào để tổ trưởng biết phải sang dừng/rút ở đâu."""
    chay = SanXuatThucThiRepository(db).viec_dang_chay_cua_nhieu({emp.id})
    if emp.id not in chay:
        return
    v = nhan_viec(db, [chay[emp.id]])[chay[emp.id].id]
    raise ValueError(f"{emp.full_name} đang chạy {mo_ta_viec(v)} — {duoi}.")
