"""Thực hiện sản xuất — PHÂN BỔ SẢN LƯỢNG thành lương khoán theo người (Giai đoạn 4, §12).

Biến sản lượng MỘT batch (§12.1: chia theo từng batch, không gộp công đoạn) thành các dòng lương
khoán theo người. Tuân §18: kiểm quyền tại service (đúng tổ trưởng) → transaction → version chống
bấm trùng → ghi audit → (SSE do router phát sau commit).

CÔNG THỨC (§12.2), cho một batch có sản lượng trả lương Q:
  1. Quy đổi bản địa → trả lương bằng ẢNH CHỤP `khoan_json` của công đoạn (đơn giá + đơn vị). Ở đây
     là quy đổi ĐỒNG NHẤT (identity): Q_trả_lương = `batch.tot`, đơn vị = `khoan_json.don_vi` |
     `cv.don_vi_ra`. Luôn GIỮ RIÊNG số bản địa (`q_ban_dia`) và số trả lương (§12.2).
  2. Tổng tỷ lệ hỗ trợ đã xác nhận P (cùng công đoạn + cùng ngày batch).
  3. Mỗi người hỗ trợ nhận Q × tỷ lệ_riêng (ghi cho TỔ GỐC, KHÔNG chia theo phút×hệ số).
  4. Phần tổ thực hiện = Q − Σ(phần hỗ trợ đã làm tròn) = "phần còn lại" thực, đảm bảo tổng = Q.
  5. Trọng số mỗi người tổ thực hiện = phút thực tế hợp lệ (giao khoảng tham gia × cửa sổ batch) ×
     hệ số bậc ẢNH CHỤP (§8).
  6. Chia phần còn lại theo trọng số.
  7. LÀM TRÒN LỚN-NHẤT-DƯ (milli-đơn-vị) để Σ khớp Q chính xác.

CHẶN CHỐT (§8, §11.3, §12.2): thiếu hệ số bậc / thiếu trọng số hợp lệ / bàn giao đi còn không nhất
quán ⇒ KHÔNG cho chốt (nhưng KHÔNG chặn ghi sản xuất). Nháp vẫn tính được phần tính được + phơi
cảnh báo; `chot_phan_bo` tính lại NGHIÊM và ném lỗi nếu vướng.

§12.3: sau hoàn thành phân bổ = draft (công nhân CHƯA xem) → tổ trưởng CHỐT riêng → finalized (feed
lương). Mở lại (trước khi kỳ lương khoá) kèm lý do → reopened → chốt lại. Sau khi kỳ ĐÃ khoá thì
KHÔNG sửa kỳ cũ — đẻ dòng BÙ TRỪ ở kỳ mở tiếp theo (`bu_tru`).
"""
from __future__ import annotations

from datetime import date, datetime
from math import floor

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.payroll import PERIOD_LOCKED, PERIOD_PAID, PayrollPeriod
from ...models.san_xuat import SanXuatCongViec
from ...models.san_xuat_ly_do import NHOM_MO_LAI_PHAN_BO
from ...models.san_xuat_san_luong import SanXuatBatch
from ...models.san_xuat_phan_bo import (
    HT_XAC_NHAN,
    PB_DA_CHOT,
    PB_MO_LAI,
    PB_NHAP,
    SanXuatPhanBo,
    SanXuatPhanBoBuTru,
    SanXuatPhanBoDong,
)
from ...models.san_xuat_phan_bo import SanXuatPhanBoLoaiTru
from ...repositories.attendance_repo import AttendanceRepository
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.employee_repo import EmployeeRepository
from ...repositories.overtime_repo import OvertimeRepository
from ...repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..attendance_service import AttendanceService
from .thuc_thi import _aware, _gate, _moc

_EPS = 0.0005  # dung sai làm tròn Numeric(18,3)


# --- Trợ giúp ------------------------------------------------------------------------------
def _phut_giao(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    """Số phút GIAO giữa hai khoảng [a0,a1] ∩ [b0,b1] (ép aware trước, bẫy naive/aware SQLite)."""
    lo = max(_aware(a0), _aware(b0))
    hi = min(_aware(a1), _aware(b1))
    return max(0.0, (hi - lo).total_seconds() / 60.0)


def _phut_giao_nhieu(a0: datetime, a1: datetime, khoang: list[tuple[datetime, datetime]]) -> float:
    """Tổng phút của [a0,a1] giao với danh sách khoảng KHÔNG chồng lấn `khoang` (§7.3)."""
    return sum(_phut_giao(a0, a1, w0, w1) for w0, w1 in khoang)


def _attendance(db: Session) -> AttendanceService:
    """Dựng AttendanceService để lấy KHOẢNG CHẤM CÔNG HỢP LỆ (§7.3). Truyền `overtime` để cửa sổ
    phiếu tăng ca đã duyệt được tính là 'trong giờ được trả công'."""
    return AttendanceService(
        AttendanceRepository(db),
        EmployeeRepository(db),
        AuditLogRepository(db),
        overtime=OvertimeRepository(db),
    )


def _ten_nguoi(att: AttendanceService, ids: list[int]) -> str:
    """Chuỗi tên NV cho cảnh báo (mã + họ tên), giữ thứ tự truyền vào."""
    ten = []
    for eid in ids:
        emp = att.employees.get_by_id(eid)
        ten.append(f"{emp.full_name} ({emp.code})" if emp is not None else f"NV#{eid}")
    return ", ".join(ten)


def _ky_cua(ngay: date) -> tuple[int, int]:
    return ngay.year, ngay.month


def _don_gia_don_vi(cv: SanXuatCongViec) -> tuple[float, str | None]:
    """Đơn giá + đơn vị trả lương lấy từ ẢNH CHỤP `khoan_json` của công đoạn (đóng băng lúc phát
    hành). Không có khoan_json ⇒ đơn giá 0 (công đoạn không ăn khoán) + đơn vị bản địa `don_vi_ra`."""
    khoan = cv.khoan_json or {}
    don_gia = float(khoan.get("don_gia") or 0)
    don_vi = (khoan.get("don_vi") or cv.don_vi_ra or None)
    return don_gia, don_vi


class _KetQuaTinh:
    """Kết quả engine tính một batch: dòng dự kiến + cờ chặn chốt + cảnh báo."""

    def __init__(self) -> None:
        self.q_pay: float = 0.0
        self.q_native: float = 0.0
        self.p_percent: float = 0.0
        self.don_gia: float = 0.0
        self.don_vi_pay: str | None = None
        self.don_vi_native: str | None = None
        self.ngay: date | None = None
        self.dong: list[dict] = []          # mỗi dict: 1 dòng phân bổ dự kiến
        self.can_chot: bool = True
        self.canh_bao: list[str] = []
        self.thieu_cham_cong: list[int] = []   # employee_id tham gia nhưng 0 phút chấm công hợp lệ (§7.3)
        self.loai_tru: list[int] = []          # employee_id đã bị loại khỏi lương batch (§7.3)


def _tinh_batch(
    db: Session, cv: SanXuatCongViec, batch: SanXuatBatch, pb_repo: SanXuatPhanBoRepository
) -> _KetQuaTinh:
    """Tính DỰ KIẾN các dòng phân bổ của một batch — HÀM THUẦN (không ghi DB). Đặt cờ `can_chot`."""
    kq = _KetQuaTinh()
    kq.q_native = float(batch.tot or 0)
    kq.don_vi_native = batch.don_vi
    kq.don_gia, kq.don_vi_pay = _don_gia_don_vi(cv)
    kq.q_pay = kq.q_native  # quy đổi đồng nhất (identity) — xem docstring module
    ngay = _aware(batch.bat_dau).date()
    kq.ngay = ngay

    # (2) Hỗ trợ đã xác nhận trong phạm vi (công đoạn + ngày batch).
    ho_tro = pb_repo.ho_tro_xac_nhan_trong_pham_vi(cv.id, ngay)
    kq.p_percent = sum(float(h.ty_le_phan_tram or 0) for h in ho_tro)
    nguoi_ho_tro_ids = {h.employee_id for h in ho_tro}

    # Người đã bị tổ trưởng loại khỏi lương batch (§7.3) — bỏ khỏi vòng chia trọng số.
    loai_tru_ids = pb_repo.loai_tru_ids(batch.id)
    kq.loai_tru = sorted(loai_tru_ids)

    if kq.q_pay <= _EPS:
        # Batch không có sản lượng tốt → không có gì để trả (vẫn tạo header q=0).
        return kq

    # (3) Dòng người hỗ trợ = Q × tỷ lệ riêng, làm tròn 3 số lẻ, ghi cho TỔ GỐC.
    tong_ho_tro_pay = 0.0
    for h in ho_tro:
        amt = round(kq.q_pay * float(h.ty_le_phan_tram or 0) / 100.0, 3)
        tong_ho_tro_pay += amt
        kq.dong.append({
            "employee_id": h.employee_id,
            "department_id": h.to_goc_id,
            "la_ho_tro": True,
            "ho_tro_id": h.id,
            "ngay": h.ngay_lam_viec,
            "so_luong_tra_luong": amt,
            "so_luong_ban_dia": amt,  # identity
            "trong_so": None,
            "phut_thuc_te": None,
            "he_so_bac": None,
            "don_gia": kq.don_gia,
        })

    # (4) Phần còn lại THỰC cho tổ thực hiện = Q − Σ(phần hỗ trợ đã làm tròn).
    con_lai = round(kq.q_pay - tong_ho_tro_pay, 3)
    if con_lai < 0:
        con_lai = 0.0

    # (5) Trọng số người tổ thực hiện = Σ(phút HỢP LỆ × hệ số bậc) trên các khoảng của họ.
    #     Phút hợp lệ (§7.3) = giao(khoảng THAM GIA trong batch, khoảng CHẤM CÔNG hợp lệ = cặp
    #     vào/ra thực tế ∩ (trong ca thường ∪ phiếu tăng ca đã duyệt)). Không chấm công hợp lệ ⇒
    #     0 phút ⇒ đánh 'thiếu chấm công' (chặn chốt cho tới khi bổ sung hoặc loại khỏi lương batch).
    b0, b1 = batch.bat_dau, batch.ket_thuc
    att = _attendance(db)
    hople_cache: dict[int, list[tuple[datetime, datetime]]] = {}

    def _khoang_hople(eid: int) -> list[tuple[datetime, datetime]]:
        if eid not in hople_cache:
            emp = att.employees.get_by_id(eid)
            hople_cache[eid] = att.khoang_co_mat_hop_le(emp, b0, b1) if emp is not None else []
        return hople_cache[eid]

    phut_theo_nguoi: dict[int, float] = {}   # phút HỢP LỆ đã cộng dồn (hiển thị + kiểm)
    phut_tham_gia: dict[int, float] = {}     # phút THAM GIA thô (để phát hiện thiếu chấm công)
    ts_theo_nguoi: dict[int, float] = {}
    heso_theo_nguoi: dict[int, float | None] = {}
    thieu_heso = False
    tt_repo = SanXuatThucThiRepository(db)
    for kh in tt_repo.cac_khoang(cv.id):
        eid = kh.employee_id
        if eid in nguoi_ho_tro_ids:
            continue  # người hỗ trợ tính bằng thỏa thuận, không chia lại theo phút (§9.2)
        if eid in loai_tru_ids:
            continue  # đã xác nhận loại khỏi lương batch (§7.3) — phần của họ chia lại cho người khác
        kh_end = kh.ket_thuc if kh.ket_thuc is not None else b1
        phut_tg = _phut_giao(kh.bat_dau, kh_end, b0, b1)
        if phut_tg <= 0:
            continue
        phut_tham_gia[eid] = phut_tham_gia.get(eid, 0.0) + phut_tg
        # Kẹp khoảng tham gia vào cửa sổ batch rồi giao với chấm công hợp lệ.
        a0, a1 = max(_aware(kh.bat_dau), _aware(b0)), min(_aware(kh_end), _aware(b1))
        phut_hl = _phut_giao_nhieu(a0, a1, _khoang_hople(eid))
        if phut_hl <= 0:
            continue  # có mặt trong batch nhưng 0 phút chấm công hợp lệ → gom vào 'thiếu chấm công'
        heso = kh.output_coefficient
        phut_theo_nguoi[eid] = phut_theo_nguoi.get(eid, 0.0) + phut_hl
        if heso is None:
            thieu_heso = True
            # trọng số phần này = 0 (chưa có hệ số) — đánh dấu chặn chốt bên dưới.
            heso_theo_nguoi.setdefault(eid, None)
            continue
        ts_theo_nguoi[eid] = ts_theo_nguoi.get(eid, 0.0) + phut_hl * float(heso)
        heso_theo_nguoi[eid] = float(heso)

    tong_ts = sum(ts_theo_nguoi.values())
    # Thiếu chấm công (§7.3): có tham gia thô nhưng KHÔNG có phút chấm công hợp lệ nào.
    thieu_cham = sorted(
        e for e, p in phut_tham_gia.items()
        if p > _EPS and phut_theo_nguoi.get(e, 0.0) <= _EPS
    )
    kq.thieu_cham_cong = thieu_cham

    if con_lai > _EPS:
        if thieu_cham:
            kq.can_chot = False
            kq.canh_bao.append(
                "Thiếu chấm công hợp lệ: " + _ten_nguoi(att, thieu_cham)
                + " — bổ sung chấm công rồi tính lại, hoặc loại người đó khỏi lương batch kèm lý do."
            )
        if thieu_heso:
            kq.can_chot = False
            kq.canh_bao.append("Có người chưa gán hệ số bậc (§8) — bổ sung bậc trước khi chốt phân bổ.")
        if not phut_theo_nguoi and not thieu_cham:
            kq.can_chot = False
            kq.canh_bao.append("Chưa có ai của tổ thực hiện tham gia trong cửa sổ batch — thiếu trọng số để chia.")
        elif tong_ts <= _EPS and not thieu_heso and not thieu_cham:
            kq.can_chot = False
            kq.canh_bao.append("Tổng trọng số bằng 0 — không chia được phần còn lại.")

    # (6)+(7) Chia phần còn lại theo trọng số + làm tròn lớn-nhất-dư (milli-đơn-vị) để Σ = con_lai.
    if con_lai > _EPS and tong_ts > _EPS and not thieu_heso:
        nguoi = [e for e in ts_theo_nguoi if ts_theo_nguoi[e] > 0]
        pool_milli = int(round(con_lai * 1000))
        raw = {e: pool_milli * ts_theo_nguoi[e] / tong_ts for e in nguoi}
        san = {e: floor(v) for e, v in raw.items()}
        du = pool_milli - sum(san.values())
        # Phân phần dư cho các phần lẻ lớn nhất (ổn định: rồi tới employee_id nhỏ hơn).
        thu_tu = sorted(nguoi, key=lambda e: (-(raw[e] - floor(raw[e])), e))
        for e in thu_tu[:max(0, du)]:
            san[e] += 1
        for e in nguoi:
            amt = san[e] / 1000.0
            kq.dong.append({
                "employee_id": e,
                "department_id": cv.department_id,
                "la_ho_tro": False,
                "ho_tro_id": None,
                "ngay": kq.ngay,
                "so_luong_tra_luong": amt,
                "so_luong_ban_dia": amt,  # identity
                "trong_so": ts_theo_nguoi[e],
                "phut_thuc_te": phut_theo_nguoi.get(e),
                "he_so_bac": heso_theo_nguoi.get(e),
                "don_gia": kq.don_gia,
            })

    return kq


def _ghi_dong(pb_repo: SanXuatPhanBoRepository, header: SanXuatPhanBo, kq: _KetQuaTinh) -> None:
    """Sinh LẠI toàn bộ dòng của header từ kết quả tính (§12.2: dựng lại mỗi lần)."""
    pb_repo.xoa_dong_cua(header.id)
    pb_repo.flush()
    for d in kq.dong:
        pb_repo.add(SanXuatPhanBoDong(phan_bo_id=header.id, **d))


def _ap_header(header: SanXuatPhanBo, kq: _KetQuaTinh) -> None:
    header.ngay = kq.ngay
    header.ky_nam, header.ky_thang = _ky_cua(kq.ngay)
    header.q_tra_luong = kq.q_pay
    header.don_vi_tra_luong = kq.don_vi_pay
    header.don_gia = kq.don_gia
    header.q_ban_dia = kq.q_native
    header.don_vi_ban_dia = kq.don_vi_native
    header.tong_ty_le_ho_tro = kq.p_percent


def _tom_tat(header: SanXuatPhanBo, kq: _KetQuaTinh) -> dict:
    return {
        "phan_bo_id": header.id,
        "batch_id": header.batch_id,
        "cong_viec_id": header.cong_viec_id,
        "department_id": kq_department(kq),
        "trang_thai": header.trang_thai,
        "version": header.version,
        "q_tra_luong": float(header.q_tra_luong or 0),
        "tong_ty_le_ho_tro": float(header.tong_ty_le_ho_tro or 0),
        "so_dong": len(kq.dong),
        "can_chot": kq.can_chot,
        "canh_bao": kq.canh_bao,
        "thieu_cham_cong": kq.thieu_cham_cong,
        "loai_tru": kq.loai_tru,
    }


def kq_department(kq: _KetQuaTinh) -> int | None:
    for d in kq.dong:
        if not d["la_ho_tro"]:
            return d["department_id"]
    return None


# --- Lệnh -----------------------------------------------------------------------------------
def tinh_phan_bo(db: Session, *, user, batch_id: int) -> dict:
    """Tạo/refresh bản NHÁP phân bổ của một batch (§12.3: sau hoàn thành = draft). Đã finalized thì
    phải MỞ LẠI trước. Tính được phần nào ghi phần đó + phơi cảnh báo chặn chốt."""
    pb_repo = SanXuatPhanBoRepository(db)
    sl_repo = SanXuatSanLuongRepository(db)
    batch = sl_repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch sản lượng.")
    cv = pb_repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    header = pb_repo.phan_bo_cua_batch(batch_id)
    if header is not None and header.trang_thai == PB_DA_CHOT:
        raise ValueError("Phân bổ đã chốt — mở lại trước khi tính lại.")

    kq = _tinh_batch(db, cv, batch, pb_repo)
    moi = header is None
    if moi:
        header = SanXuatPhanBo(batch_id=batch_id, cong_viec_id=cv.id, ngay=kq.ngay,
                               ky_nam=kq.ngay.year, ky_thang=kq.ngay.month, trang_thai=PB_NHAP)
        pb_repo.add(header)
        pb_repo.flush()
    _ap_header(header, kq)
    _ghi_dong(pb_repo, header, kq)
    pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.tinh",
        target=f"san_xuat_phan_bo:{header.id}",
        detail=f"batch={batch_id} q={kq.q_pay:g} dong={len(kq.dong)} can_chot={kq.can_chot}",
    )
    db.commit()
    return _tom_tat(header, kq)


def chot_phan_bo(
    db: Session, *, user, phan_bo_id: int, expected_version: int | None = None
) -> dict:
    """CHỐT phân bổ (§12.3): tính LẠI nghiêm, chặn nếu thiếu hệ số/trọng số hoặc bàn giao không nhất
    quán (§8, §11.3, §12.2). Chốt xong công nhân xem được + feed lương."""
    pb_repo = SanXuatPhanBoRepository(db)
    sl_repo = SanXuatSanLuongRepository(db)
    header = pb_repo.phan_bo(phan_bo_id)
    if header is None:
        raise ValueError("Không tìm thấy bản phân bổ.")
    if expected_version is not None and expected_version != header.version:
        raise ValueError("Phiên bản không khớp — phân bổ vừa được cập nhật, hãy tải lại.")
    cv = pb_repo.cong_viec(header.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của phân bổ.")
    _gate(db, user, cv)
    if header.trang_thai == PB_DA_CHOT:
        raise ValueError("Phân bổ đã chốt.")

    if pb_repo.co_ban_giao_khong_nhat_quan(cv.id):
        raise ValueError("Còn bàn giao không nhất quán (§11.3) — xử lý bàn giao trước khi chốt phân bổ.")

    batch = sl_repo.batch(header.batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch của phân bổ.")
    kq = _tinh_batch(db, cv, batch, pb_repo)
    if not kq.can_chot:
        raise ValueError(kq.canh_bao[0] if kq.canh_bao else "Chưa đủ điều kiện chốt phân bổ.")

    _ap_header(header, kq)
    _ghi_dong(pb_repo, header, kq)
    header.trang_thai = PB_DA_CHOT
    header.chot_by_id = getattr(user, "id", None)
    header.chot_luc = _moc()
    header.version += 1
    pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.chot",
        target=f"san_xuat_phan_bo:{header.id}",
        detail=f"q={kq.q_pay:g} dong={len(kq.dong)}",
    )
    db.commit()
    return _tom_tat(header, kq)


def mo_lai_phan_bo(
    db: Session, *, user, phan_bo_id: int, ly_do_id: int, expected_version: int | None = None
) -> dict:
    """Mở lại phân bổ ĐÃ CHỐT để sửa (§12.3) — CHỈ khi kỳ lương của batch CHƯA khoá. Sau khi kỳ đã
    khoá thì không mở kỳ cũ, phải dùng `bu_tru`. Bắt buộc lý do (nhóm `mo_lai_phan_bo`)."""
    pb_repo = SanXuatPhanBoRepository(db)
    header = pb_repo.phan_bo(phan_bo_id)
    if header is None:
        raise ValueError("Không tìm thấy bản phân bổ.")
    if expected_version is not None and expected_version != header.version:
        raise ValueError("Phiên bản không khớp — phân bổ vừa được cập nhật, hãy tải lại.")
    cv = pb_repo.cong_viec(header.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của phân bổ.")
    _gate(db, user, cv)
    if header.trang_thai != PB_DA_CHOT:
        raise ValueError("Chỉ mở lại được bản đã chốt.")
    if _ky_da_khoa(db, header.ky_nam, header.ky_thang):
        raise ValueError("Kỳ lương đã khoá — không mở lại được, hãy dùng bù trừ ở kỳ mở tiếp theo.")

    ly_do = pb_repo.ly_do(ly_do_id)
    if ly_do is None or ly_do.nhom != NHOM_MO_LAI_PHAN_BO:
        raise ValueError("Lý do mở lại không hợp lệ (phải thuộc nhóm 'mo_lai_phan_bo').")

    header.trang_thai = PB_MO_LAI
    header.mo_lai_ly_do_id = ly_do_id
    header.mo_lai_by_id = getattr(user, "id", None)
    header.mo_lai_luc = _moc()
    header.version += 1
    pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.mo_lai",
        target=f"san_xuat_phan_bo:{header.id}",
        detail=f"ly_do={ly_do_id}",
    )
    db.commit()
    return {
        "phan_bo_id": header.id,
        "batch_id": header.batch_id,
        "cong_viec_id": header.cong_viec_id,
        "department_id": cv.department_id,
        "trang_thai": header.trang_thai,
        "version": header.version,
    }


def bu_tru(
    db: Session,
    *,
    user,
    batch_id: int,
    employee_id: int,
    so_luong_tra_luong: float,
    ky_bu_nam: int,
    ky_bu_thang: int,
    ly_do_id: int,
    mo_ta: str | None = None,
) -> dict:
    """Đẻ dòng BÙ TRỪ sau khi kỳ lương ĐÃ khoá (§12.3). Không sửa kỳ cũ — ghi chênh lệch (có thể âm)
    vào kỳ bù (phải là kỳ CHƯA khoá). Tham chiếu batch + kỳ gốc; đơn giá lấy từ phân bổ gốc."""
    pb_repo = SanXuatPhanBoRepository(db)
    sl_repo = SanXuatSanLuongRepository(db)
    batch = sl_repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch sản lượng.")
    cv = pb_repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    header = pb_repo.phan_bo_cua_batch(batch_id)
    if header is None or header.trang_thai != PB_DA_CHOT:
        raise ValueError("Chỉ bù trừ cho batch đã có phân bổ CHỐT.")
    if not _ky_da_khoa(db, header.ky_nam, header.ky_thang):
        raise ValueError("Kỳ gốc chưa khoá — mở lại phân bổ để sửa thay vì bù trừ.")
    if _ky_da_khoa(db, ky_bu_nam, ky_bu_thang):
        raise ValueError("Kỳ bù đã khoá — chọn kỳ lương đang mở.")

    ly_do = pb_repo.ly_do(ly_do_id)
    if ly_do is None or ly_do.nhom != NHOM_MO_LAI_PHAN_BO:
        raise ValueError("Lý do bù trừ không hợp lệ (phải thuộc nhóm 'mo_lai_phan_bo').")

    delta = float(so_luong_tra_luong or 0)
    if abs(delta) <= _EPS:
        raise ValueError("Số lượng bù trừ phải khác 0.")

    bt = SanXuatPhanBoBuTru(
        batch_id=batch_id,
        phan_bo_id=header.id,
        employee_id=employee_id,
        department_id=cv.department_id,
        ky_goc_nam=header.ky_nam,
        ky_goc_thang=header.ky_thang,
        ky_bu_nam=ky_bu_nam,
        ky_bu_thang=ky_bu_thang,
        ngay=date(ky_bu_nam, ky_bu_thang, 1),
        so_luong_tra_luong=delta,
        don_gia=float(header.don_gia or 0),
        ly_do_id=ly_do_id,
        mo_ta=(mo_ta or None),
        created_by_id=getattr(user, "id", None),
    )
    pb_repo.add(bt)
    pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.bu_tru",
        target=f"san_xuat_phan_bo_bu_tru:{bt.id}",
        detail=f"batch={batch_id} nv={employee_id} delta={delta:g} ky_bu={ky_bu_nam}-{ky_bu_thang}",
    )
    db.commit()
    return {
        "bu_tru_id": bt.id,
        "batch_id": batch_id,
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "employee_id": employee_id,
        "so_luong_tra_luong": delta,
        "ky_bu": [ky_bu_nam, ky_bu_thang],
    }


def loai_tru_khoi_phan_bo(
    db: Session, *, user, batch_id: int, employee_id: int, ly_do: str
) -> dict:
    """§7.3 — LOẠI một người khỏi lương của batch kèm LÝ DO. Dùng khi người đó tham gia nhưng thiếu
    chấm công hợp lệ và không thể bổ sung: xác nhận họ không hưởng lương batch, engine bỏ họ khỏi
    vòng chia trọng số (phần của họ chia lại cho người còn lại) và cờ 'thiếu chấm công' của họ tan.
    Chỉ khi phân bổ CHƯA chốt (đã chốt phải mở lại trước). Nếu đã có bản nháp thì tính lại luôn."""
    ly_do = (ly_do or "").strip()
    if not ly_do:
        raise ValueError("Phải nhập lý do loại người khỏi lương batch.")
    pb_repo = SanXuatPhanBoRepository(db)
    sl_repo = SanXuatSanLuongRepository(db)
    batch = sl_repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch sản lượng.")
    cv = pb_repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    header = pb_repo.phan_bo_cua_batch(batch_id)
    if header is not None and header.trang_thai == PB_DA_CHOT:
        raise ValueError("Phân bổ đã chốt — mở lại trước khi loại người khỏi lương batch.")

    if pb_repo.loai_tru_cua(batch_id, employee_id) is None:
        pb_repo.add(SanXuatPhanBoLoaiTru(
            batch_id=batch_id, employee_id=employee_id, ly_do=ly_do,
            created_by_id=getattr(user, "id", None),
        ))
        pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.loai_tru",
        target=f"san_xuat_batch:{batch_id}",
        detail=f"nv={employee_id} ly_do={ly_do[:160]}",
    )
    res = _refresh_neu_nhap(db, pb_repo, cv, batch, header)
    db.commit()
    return res


def go_loai_tru(db: Session, *, user, batch_id: int, employee_id: int) -> dict:
    """Gỡ loại trừ (§7.3): trả người này vào vòng chia lại. Nếu họ vẫn thiếu chấm công hợp lệ thì
    cờ chặn chốt lại nổi lên — tính lại ngay nếu đã có bản nháp."""
    pb_repo = SanXuatPhanBoRepository(db)
    sl_repo = SanXuatSanLuongRepository(db)
    batch = sl_repo.batch(batch_id)
    if batch is None:
        raise ValueError("Không tìm thấy batch sản lượng.")
    cv = pb_repo.cong_viec(batch.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của batch.")
    _gate(db, user, cv)

    header = pb_repo.phan_bo_cua_batch(batch_id)
    if header is not None and header.trang_thai == PB_DA_CHOT:
        raise ValueError("Phân bổ đã chốt — mở lại trước khi gỡ loại trừ.")

    if not pb_repo.go_loai_tru(batch_id, employee_id):
        raise ValueError("Người này chưa bị loại khỏi lương batch.")
    pb_repo.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat.phan_bo.go_loai_tru",
        target=f"san_xuat_batch:{batch_id}",
        detail=f"nv={employee_id}",
    )
    res = _refresh_neu_nhap(db, pb_repo, cv, batch, header)
    db.commit()
    return res


def _refresh_neu_nhap(
    db: Session, pb_repo: SanXuatPhanBoRepository, cv: SanXuatCongViec,
    batch: SanXuatBatch, header: SanXuatPhanBo | None,
) -> dict:
    """Có header NHÁP/MỞ-LẠI thì tính lại + sinh lại dòng (phản ánh loại trừ vừa đổi); chưa có header
    thì trả tóm tắt nhẹ (lần `tinh_phan_bo` sau sẽ honor loại trừ)."""
    if header is not None:
        kq = _tinh_batch(db, cv, batch, pb_repo)
        _ap_header(header, kq)
        _ghi_dong(pb_repo, header, kq)
        pb_repo.flush()
        return _tom_tat(header, kq)
    return {
        "phan_bo_id": None,
        "batch_id": batch.id,
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": None,
        "loai_tru": sorted(pb_repo.loai_tru_ids(batch.id)),
    }


# --- Nội bộ ---------------------------------------------------------------------------------
def _ky_da_khoa(db: Session, nam: int, thang: int) -> bool:
    """Kỳ lương (năm, tháng) đã khoá/đã chi ⇒ không sửa số khoán trong kỳ (§12.3)."""
    row = db.scalar(
        select(PayrollPeriod.status).where(
            PayrollPeriod.year == nam, PayrollPeriod.month == thang
        )
    )
    return row in (PERIOD_LOCKED, PERIOD_PAID)
