"""Thực hiện sản xuất tại TỔ — lệnh GHI (Giai đoạn 2, §7.1–§7.2).

Điều phối phân công · phiên chạy · khoảng tham gia. Mỗi lệnh tuân §18: kiểm quyền tại service →
transaction → version chống bấm trùng → ghi audit → (SSE do router phát sau commit).

QUYỀN (§6): chỉ người ĐANG là `department.head_user_id` của CHÍNH tổ thực hiện mới được ghi. Quản
lý cấp trên (scope rộng) chỉ XEM — KHÔNG ghi đè. Router đã gác bit RBAC `san_xuat:assign_work`;
tầng này siết thêm đúng-tổ-trưởng, nên admin/GĐ (không có bit, và không phải tổ trưởng) đều bị chặn.

LƯƠNG KHOÁN (§6): chỉ nhân viên thuộc chế độ lương khoán (suy từ `departments.has_piece_work` của
tổ nhân viên) mới được giao vào bước NỘI BỘ (`loai_buoc == 'to'`). Người không có tài khoản vẫn
giao + tính lương được (chỉ neo `employee_id`).

MỐC THỜI GIAN lấy từ máy chủ, không backdate, không sửa mốc đã phát sinh (§7.2). Phút thực tế cho
lương (§7.3) tính LÚC ĐỌC ở lát sau — bảng chỉ giữ khoảng thô.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.employee import Employee, JobGrade
from ...models.may_thiet_bi import MayThietBi
from ...models.san_xuat import (
    BUOC_MAY,
    BUOC_TO,
    CV_DANG_CHAY,
    CV_HOAN_THANH,
    CV_PHAT_HANH,
    CV_TAM_DUNG,
    SanXuatCongViec,
)
from ...models.san_xuat_thuc_thi import (
    PC_DA_RUT,
    PC_HOAT_DONG,
    PHIEN_DOI_MAY,
    PHIEN_KET_THUC,
    PHIEN_TAM_DUNG,
    SanXuatKhoangThamGia,
    SanXuatPhanCong,
    SanXuatPhienChay,
)
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..gio_xuong import ve_gio_xuong


def _moc() -> datetime:
    """Mốc thời gian máy chủ (aware UTC). Nguồn DUY NHẤT cho mọi mốc — không nhận từ client."""
    return datetime.now(timezone.utc)


# --- Trợ giúp chung -------------------------------------------------------------------------
def _lay_cong_viec(repo: SanXuatThucThiRepository, cong_viec_id: int) -> SanXuatCongViec:
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    return cv


def _gate(db: Session, user, cv: SanXuatCongViec) -> None:
    """Chỉ tổ trưởng ĐÚNG tổ của công việc mới được ghi (§6). Không có ghi đè cho cấp trên."""
    dept = db.get(Department, cv.department_id) if cv.department_id else None
    uid = getattr(user, "id", None)
    if dept is None or dept.head_user_id is None or dept.head_user_id != uid:
        raise PermissionError("Chỉ tổ trưởng của tổ thực hiện mới được thao tác công việc này.")


def _kiem_version(cv: SanXuatCongViec, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != cv.version:
        raise ValueError("Phiên bản không khớp — công việc vừa được cập nhật, hãy tải lại.")


def _snapshot_bac(db: Session, employee_id: int) -> tuple[int | None, float | None]:
    """Ảnh chụp bậc tay nghề + hệ số sản lượng của một người tại lúc mở khoảng tham gia (§8).

    Đóng băng để danh mục bậc đổi về sau KHÔNG viết lại khoảng đang chạy/đã xong. Người chưa gán bậc
    → (None, None); bậc chưa khai hệ số → (grade_id, None) ⇒ §8 chặn CHỐT phân bổ chứ không chặn ghi
    sản xuất (engine đọc snapshot này để chia trọng số §12.2)."""
    emp = db.get(Employee, employee_id)
    grade_id = getattr(emp, "job_grade_id", None) if emp else None
    heso = None
    if grade_id:
        grade = db.get(JobGrade, grade_id)
        heso = getattr(grade, "output_coefficient", None) if grade else None
    return grade_id, heso


def _la_luong_khoan(db: Session, emp) -> bool:
    """Nhân viên thuộc chế độ lương khoán ⇔ tổ của họ bật `has_piece_work` (cùng cờ mà thành phần
    lương `luong_khoan` soi). Không có tổ → không phải thợ khoán."""
    if emp is None or emp.department_id is None:
        return False
    dept = db.get(Department, emp.department_id)
    return bool(dept and dept.has_piece_work)


def _audit(db: Session, user, action: str, cv: SanXuatCongViec, detail: str = "",
           *, commit: bool = True) -> None:
    """`commit=False` khi lệnh đang là MỘT MẢNH của giao dịch lớn hơn (vd `su_co.bao_su_co` gom
    ghi yêu cầu sửa chữa + tạm dừng + đóng phiên). Mặc định giữ nguyên hành vi cũ cho mọi lệnh
    đang chạy — chúng đều `db.commit()` ngay sau đó nên thêm một commit ở đây chỉ là dư."""
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action=action,
        target=f"san_xuat_cong_viec:{cv.id}",
        detail=detail,
        commit=commit,
    )


def _ket_qua(cv: SanXuatCongViec, *, notify_user_id: int | None = None) -> dict:
    """Dữ liệu tối thiểu router cần để phát SSE sau commit."""
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "notify_user_id": notify_user_id,
    }


# --- Phân công (§7.1) -----------------------------------------------------------------------
def phan_cong(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    employee_id: int,
    expected_version: int | None = None,
) -> dict:
    """Giao MỘT người vào công việc. Lần giao đầu = tổ tiếp nhận (§5.2, không nút Nhận lệnh riêng).

    Bước nội bộ chỉ nhận thợ lương khoán (§6). Nếu công việc ĐANG chạy, mở luôn khoảng tham gia
    cho người mới (§7.2 "thêm người"), nhưng chặn nếu người đó còn khoảng mở ở việc khác (§7.1)."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai == CV_HOAN_THANH:
        raise ValueError("Công việc đã hoàn thành, không thể phân công thêm.")

    emp = repo.nhan_vien(employee_id)
    if emp is None:
        raise ValueError("Không tìm thấy nhân viên.")
    la_khoan = _la_luong_khoan(db, emp)
    if cv.loai_buoc == BUOC_TO and not la_khoan:
        raise ValueError("Bước nội bộ chỉ được giao cho nhân viên thuộc chế độ lương khoán.")
    if repo.phan_cong_hoat_dong_cua(cong_viec_id, employee_id) is not None:
        raise ValueError("Nhân viên này đã được giao vào công việc.")

    pc = SanXuatPhanCong(
        cong_viec_id=cv.id,
        employee_id=employee_id,
        la_luong_khoan=la_khoan,
        trang_thai=PC_HOAT_DONG,
        created_by=getattr(user, "id", None),
    )
    repo.add(pc)

    # Thêm người GIỮA CHỪNG khi việc đang chạy → mở khoảng tham gia ngay (§7.2).
    if cv.trang_thai == CV_DANG_CHAY:
        phien = repo.phien_dang_mo(cv.id)
        if phien is not None:
            if repo.khoang_mo_cua_nguoi(employee_id) is not None:
                raise ValueError(
                    "Người này đang tham gia một công việc khác (khoảng tham gia chồng giờ)."
                )
            bac_id, heso = _snapshot_bac(db, employee_id)
            repo.add(
                SanXuatKhoangThamGia(
                    cong_viec_id=cv.id,
                    phien_chay_id=phien.id,
                    employee_id=employee_id,
                    bat_dau=_moc(),
                    job_grade_id=bac_id,
                    output_coefficient=heso,
                )
            )

    cv.version += 1
    _audit(db, user, "san_xuat_phan_cong", cv, detail=f"employee_id={employee_id}")
    db.commit()
    return _ket_qua(cv, notify_user_id=emp.user_id)


def go_phan_cong(
    db: Session,
    *,
    user,
    phan_cong_id: int,
    ly_do: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Rút một người khỏi công việc (§7.2 "rút người"): đóng khoảng tham gia đang mở của họ."""
    repo = SanXuatThucThiRepository(db)
    pc = repo.phan_cong(phan_cong_id)
    if pc is None or pc.trang_thai != PC_HOAT_DONG:
        raise ValueError("Không tìm thấy phân công đang hoạt động.")
    cv = _lay_cong_viec(repo, pc.cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)

    khoang = repo.khoang_mo_cua_nguoi_o_cong_viec(cv.id, pc.employee_id)
    if khoang is not None:
        repo.dong_khoang(khoang, _moc())

    pc.trang_thai = PC_DA_RUT
    pc.ly_do_rut = ly_do
    pc.version += 1
    cv.version += 1
    _audit(db, user, "san_xuat_go_phan_cong", cv, detail=f"employee_id={pc.employee_id}")
    db.commit()
    return _ket_qua(cv)


# --- Phiên chạy (§7.2) ----------------------------------------------------------------------
def bat_dau(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    ly_do_tre: str | None = None,
    ly_do_so_nguoi: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Bắt đầu (hoặc Tiếp tục) chạy: mở phiên mới + mở khoảng tham gia cho mọi người đang trong tổ.

    Luật: phải có ≥1 thợ lương khoán đang được giao (§7.1); bắt đầu SỚM không cần lý do, bắt đầu
    TRỄ bắt buộc `ly_do_tre` (§7.2); số người THỰC TẾ khác số dự kiến (chốt lúc phát hành) bắt buộc
    `ly_do_so_nguoi` (§7.1); không ai được có khoảng tham gia chồng giờ (§7.1)."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_PHAT_HANH, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chờ hoặc tạm dừng mới bắt đầu/tiếp tục được.")

    roster = repo.phan_cong_hoat_dong(cv.id)
    if not any(pc.la_luong_khoan for pc in roster):
        raise ValueError("Phải có ít nhất một thợ lương khoán được phân công mới bắt đầu được.")

    # §7.1: số người THỰC TẾ bắt đầu khác số dự kiến (chốt lúc phát hành trong dinh_muc_json) ⇒
    # vẫn cho bắt đầu nhưng BẮT BUỘC chọn lý do. Không khai định mức người (None) → miễn kiểm.
    du_kien_so_nguoi = (
        cv.dinh_muc_json.get("so_nhan_cong_tieu_chuan")
        if isinstance(cv.dinh_muc_json, dict) else None
    )
    lech_so_nguoi = du_kien_so_nguoi is not None and len(roster) != du_kien_so_nguoi
    if lech_so_nguoi and not (ly_do_so_nguoi or "").strip():
        raise ValueError(
            f"Số người thực tế ({len(roster)}) khác dự kiến ({du_kien_so_nguoi}) — bắt buộc chọn lý do."
        )

    # Cổng BƯỚC GHÉP (§10.2): công việc có cạnh phụ thuộc đổ vào (bài ghép gộp nhiều nhánh) chỉ
    # chạy được khi MỌI nhánh nguồn đã có bàn giao XÁC NHẬN số dương vào đây. Công việc một nhánh
    # (không cạnh phụ thuộc) → vòng lặp rỗng → no-op, giữ G2 nguyên vẹn.
    sl_repo = SanXuatSanLuongRepository(db)
    for canh in sl_repo.canh_phu_thuoc_toi(cv.id):
        if not sl_repo.co_ban_giao_xac_nhan_duong(canh.nguon_cong_viec_id, cv.id):
            raise ValueError(
                "Bước ghép chưa đủ đầu vào — cần bàn giao đã xác nhận từ mọi nhánh trước khi chạy."
            )

    # Cổng KHUÔN/KHUNG: bước có dụng cụ lưu kho thì phải có người xác nhận dao đang nằm trên bàn.
    # Đây là ĐIỂM CHẶN DUY NHẤT của luật "bế phải có khuôn mới làm được" — ngày dự kiến có khuôn
    # KHÔNG chặn xếp lịch (chốt 04/09/2026), vì ngày đó thợ tự sửa trong danh mục nên không đủ tin
    # để chặn ai. Ở đây thì khác: người tích là người đang cầm con dao trong tay.
    if cv.khuon_json and cv.khuon_nhan_luc is None:
        ma_dao = (cv.khuon_json or {}).get("ma") or "khuôn"
        raise ValueError(
            f"Chưa nhận khuôn/khung ({ma_dao}) — tích “Đã nhận” trước khi bắt đầu."
        )

    now = _moc()
    # `du_kien_*` là GIỜ XƯỞNG còn `_moc()` là UTC THẬT — so thẳng thì cổng "trễ" khoan dung đúng
    # bằng offset máy chủ (VN: 7 tiếng). Quy về cùng thang trước khi so (`services/gio_xuong.py`).
    if (cv.du_kien_bat_dau is not None and ve_gio_xuong(now) > _aware(cv.du_kien_bat_dau)
            and not (ly_do_tre or "").strip()):
        raise ValueError("Bắt đầu trễ so với dự kiến — bắt buộc chọn lý do.")

    # Không ai được đang mở khoảng ở việc khác (§7.1) — kiểm TRƯỚC khi mở loạt.
    for pc in roster:
        if repo.khoang_mo_cua_nguoi(pc.employee_id) is not None:
            raise ValueError(
                f"Nhân viên #{pc.employee_id} đang tham gia công việc khác — không thể mở khoảng chồng giờ."
            )

    phien = SanXuatPhienChay(
        cong_viec_id=cv.id,
        so_thu_tu=repo.so_phien(cv.id) + 1,
        may_id=cv.may_id,          # ẢNH CHỤP máy lúc mở phiên — đổi máy sau này đẻ phiên khác
        bat_dau=now,
        ly_do_bat_dau_tre=(ly_do_tre or "").strip() or None,
        ly_do_so_nguoi=((ly_do_so_nguoi or "").strip() or None) if lech_so_nguoi else None,
        created_by=getattr(user, "id", None),
    )
    repo.add(phien)
    repo.flush()  # cần phien.id để neo khoảng tham gia
    for pc in roster:
        bac_id, heso = _snapshot_bac(db, pc.employee_id)
        repo.add(
            SanXuatKhoangThamGia(
                cong_viec_id=cv.id,
                phien_chay_id=phien.id,
                employee_id=pc.employee_id,
                bat_dau=now,
                job_grade_id=bac_id,
                output_coefficient=heso,
            )
        )

    cv.trang_thai = CV_DANG_CHAY
    cv.version += 1
    chi_tiet = f"phien={phien.so_thu_tu}"
    if lech_so_nguoi:
        chi_tiet += f"; so_nguoi {len(roster)}≠{du_kien_so_nguoi}: {phien.ly_do_so_nguoi}"
    _audit(db, user, "san_xuat_bat_dau", cv, detail=chi_tiet)
    db.commit()
    return _ket_qua(cv)


def _tam_dung_lo(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    ly_do: str,
    expected_version: int | None = None,
) -> dict:
    """LÕI của Tạm dừng — làm đủ mọi việc NHƯNG KHÔNG commit (31/08/2026).

    Tách ra vì báo sự cố "dừng sản xuất" (`services/san_xuat/su_co.py`) phải gộp ghi yêu cầu sửa
    chữa + tạm dừng + đóng phiên máy vào MỘT giao dịch: rơi giữa chừng là để lại một công việc
    "đang chạy" trên cái máy đã hỏng, và mọi sản lượng/giờ máy sau đó đều sai. Đi qua CHÍNH lõi
    này chứ không tự set cờ ở nơi khác — mọi luật đóng phiên + đóng khoảng tham gia + audit nằm
    ở đây, viết đường thứ hai là ngày nào đó hai đường lệch nhau.
    """
    if not (ly_do or "").strip():
        raise ValueError("Tạm dừng bắt buộc có lý do.")
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai != CV_DANG_CHAY:
        raise ValueError("Chỉ công việc đang chạy mới tạm dừng được.")

    now = _moc()
    phien = repo.phien_dang_mo(cv.id)
    if phien is not None:
        phien.ket_thuc = now
        phien.loai_dong = PHIEN_TAM_DUNG
        phien.ly_do = ly_do.strip()
        for kh in repo.khoang_mo_cua_phien(phien.id):
            repo.dong_khoang(kh, now)

    cv.trang_thai = CV_TAM_DUNG
    cv.version += 1
    _audit(db, user, "san_xuat_tam_dung", cv, detail=ly_do.strip()[:200], commit=False)
    return _ket_qua(cv)


def tam_dung(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    ly_do: str,
    expected_version: int | None = None,
) -> dict:
    """Tạm dừng: đóng phiên đang mở + đóng mọi khoảng tham gia của phiên. Bắt buộc lý do (§7.2)."""
    res = _tam_dung_lo(
        db, user=user, cong_viec_id=cong_viec_id, ly_do=ly_do,
        expected_version=expected_version,
    )
    db.commit()
    return res


def ket_thuc(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    ly_do_tre: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Kết thúc: đóng phiên đang mở (nếu có) + khoảng tham gia, đánh dấu hoàn thành.

    Kết thúc TRỄ chỉ cần thêm lý do khi CHƯA có lý do tạm dừng nào giải thích phần chậm (§7.2)."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chạy hoặc tạm dừng mới kết thúc được.")

    now = _moc()
    # Cùng lý do như ở `bat_dau`: quy `now` (UTC thật) về giờ xưởng trước khi so với `du_kien_*`.
    tre = cv.du_kien_ket_thuc is not None and ve_gio_xuong(now) > _aware(cv.du_kien_ket_thuc)
    da_giai_thich = any(
        p.loai_dong == PHIEN_TAM_DUNG and (p.ly_do or "").strip()
        for p in repo.cac_phien(cv.id)
    )
    if tre and not da_giai_thich and not (ly_do_tre or "").strip():
        raise ValueError("Kết thúc trễ — bắt buộc thêm lý do (chưa có lý do tạm dừng giải thích).")

    phien = repo.phien_dang_mo(cv.id)
    if phien is not None:
        phien.ket_thuc = now
        phien.loai_dong = PHIEN_KET_THUC
        if (ly_do_tre or "").strip():
            phien.ly_do = ly_do_tre.strip()
        for kh in repo.khoang_mo_cua_phien(phien.id):
            repo.dong_khoang(kh, now)

    cv.trang_thai = CV_HOAN_THANH
    # Đóng dấu MỐC NGHIỆP VỤ. Đây là chỗ DUY NHẤT trong hệ đặt `trang_thai='completed'` (grep
    # `CV_HOAN_THANH` — mọi chỗ khác chỉ ĐỌC), nên một dấu ở đây là đủ. KHÔNG để KPI đọc
    # `updated_at`: cột đó dời theo mọi `version += 1` về sau (rút người khỏi bước đã xong là ca
    # thật đã đo được), và bịt từng đường ghi thì đường ghi thêm sau lại phá lại.
    #
    # DẤU KHÔNG BAO GIỜ BỊ GHI ĐÈ: cửa `trang_thai not in (running, paused)` ở đầu hàm chặn mọi
    # lần gọi thứ hai, nên `hoan_thanh_luc` chỉ được ghi ĐÚNG MỘT LẦN, ở lần đóng đầu tiên. Muốn
    # mở lại một bước đã xong thì phải viết đường ghi mới — và đường ấy PHẢI tự quyết định làm gì
    # với cột này.
    #
    # DÒNG NÀY CÓ LƯỚI: `test_ket_thuc_that_dong_dau_hoan_thanh_luc`. Xoá nó mà mọi bài KPI vẫn
    # xanh là chuyện ĐÃ XẢY RA — các bài kia đi qua fixture `_dat_xong_luc`, mà fixture tự ghi cột
    # này nên nó che mất đường ghi thật. Kiến trúc cột riêng đổi một lỗi đếm THỪA ồn ào lấy một lỗi
    # đếm THIẾU lặng lẽ; đổi vậy chỉ có lãi khi ĐƯỜNG GHI được canh.
    cv.hoan_thanh_luc = now
    cv.version += 1
    _audit(db, user, "san_xuat_ket_thuc", cv)
    db.commit()
    return _ket_qua(cv)


def doi_may(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    may_id_moi: int,
    ly_do: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Đổi máy của một công việc, giữ nguyên lịch sử giờ máy (§7.2 mở rộng 31/08/2026).

    Đang CHẠY: đóng phiên hiện tại (`loai_dong=doi_may` — KHÁC `tam_dung`, xem hằng số
    `PHIEN_DOI_MAY`) rồi mở NGAY một phiên mới trên máy mới với CÙNG mốc `now` — không hở giây
    nào, vì công việc không thực sự dừng. Khoảng tham gia của người cũng đóng-mở theo phiên để
    phút công không bị đếm hai lần.

    Đang TẠM DỪNG: chỉ đổi máy được phân công. KHÔNG mở phiên — phiên mở khi bấm Tiếp tục, và
    lúc đó `bat_dau()` tự chụp `cv.may_id` mới.

    Chỉ hai trạng thái đó đổi được: việc chưa bắt đầu thì sửa ở bàn xếp lịch, việc đã kết thúc
    thì không còn máy nào để đổi. Chỉ bước CHẠY MÁY (`loai_buoc == BUOC_MAY`) mới có khái niệm
    đổi máy — bước nội bộ/thuê ngoài không gắn máy nào để đổi (review vòng 1, Important 2).

    Máy mới phải tồn tại và còn dùng (`active=True`) trong danh mục `may_thiet_bi` — FE chỉ CHE
    nút chứ không phải cổng thật (tab để lâu, máy vừa bị ngừng dùng ở màn khác vẫn gọi được API
    này nếu không kiểm ở đây); router dùng `_chay()` nên `ValueError` ở đây dịch thẳng ra 400.
    """
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chạy hoặc tạm dừng mới đổi máy được.")
    if cv.loai_buoc != BUOC_MAY:
        raise ValueError("Bước này không chạy máy — không có gì để đổi.")
    if cv.may_id == may_id_moi:
        raise ValueError("Máy mới trùng máy đang chạy — không có gì để đổi.")
    may_moi = db.get(MayThietBi, may_id_moi)
    if may_moi is None or not may_moi.active:
        raise ValueError("Máy mới không tồn tại hoặc đã ngừng dùng trong danh mục.")

    now = _moc()
    may_cu = cv.may_id
    if cv.trang_thai == CV_DANG_CHAY:
        phien_cu = repo.phien_dang_mo(cv.id)
        nguoi = []
        if phien_cu is not None:
            phien_cu.ket_thuc = now
            phien_cu.loai_dong = PHIEN_DOI_MAY
            phien_cu.ly_do = (ly_do or "Đổi máy").strip()[:255]
            for kh in repo.khoang_mo_cua_phien(phien_cu.id):
                nguoi.append((kh.employee_id, kh.job_grade_id, kh.output_coefficient))
                repo.dong_khoang(kh, now)
        phien_moi = SanXuatPhienChay(
            cong_viec_id=cv.id,
            so_thu_tu=repo.so_phien(cv.id) + 1,
            may_id=may_id_moi,
            bat_dau=now,
            created_by=getattr(user, "id", None),
        )
        repo.add(phien_moi)
        repo.flush()
        for emp_id, bac_id, heso in nguoi:
            repo.add(
                SanXuatKhoangThamGia(
                    cong_viec_id=cv.id,
                    phien_chay_id=phien_moi.id,
                    employee_id=emp_id,
                    bat_dau=now,
                    job_grade_id=bac_id,
                    output_coefficient=heso,
                )
            )

    cv.may_id = may_id_moi
    cv.version += 1
    _audit(db, user, "san_xuat_doi_may", cv, detail=f"may {may_cu} -> {may_id_moi}")
    db.commit()
    return _ket_qua(cv)


# --- Khuôn/khung của bước (chốt 04/09/2026) -------------------------------------------------
def nhan_khuon(db: Session, *, user, cong_viec_id: int) -> dict:
    """Tổ xác nhận đã cầm con dao trong tay.

    Tích MỘT LẦN, không gỡ được — gỡ ra thì cái mốc "ai nói dao đã ở đây, lúc mấy giờ" mất nghĩa,
    mà đó đúng là thứ duy nhất mở được cổng Bắt đầu ở trên.
    """
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    if not cv.khuon_json:
        raise ValueError("Bước này không dùng khuôn/khung.")
    if cv.khuon_nhan_luc is not None:
        raise ValueError("Khuôn của bước này đã được xác nhận nhận.")
    cv.khuon_nhan_luc = _moc()
    cv.khuon_nhan_by_id = getattr(user, "id", None)
    cv.version += 1
    _audit(db, user, "san_xuat_nhan_khuon", cv, detail=(cv.khuon_json or {}).get("ma") or "")
    db.commit()
    return _ket_qua(cv)


def tra_khuon(db: Session, *, user, cong_viec_id: int) -> dict:
    """Trả dao về kệ. KHÔNG chặn gì — chỉ để hệ thống khỏi mất dấu con dao sau khi nó rời kệ, đúng
    việc mà kho dao sinh ra để khỏi phải đi hỏi từng tổ."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    if not cv.khuon_json:
        raise ValueError("Bước này không dùng khuôn/khung.")
    cv.khuon_tra_luc = _moc()
    cv.version += 1
    _audit(db, user, "san_xuat_tra_khuon", cv, detail=(cv.khuon_json or {}).get("ma") or "")
    db.commit()
    return _ket_qua(cv)


def _aware(dt: datetime) -> datetime:
    """SQLite trả datetime NAIVE — ép về aware UTC trước khi so với mốc máy chủ (bẫy naive/aware
    từng làm 500 ở xếp lịch). Postgres đã aware thì giữ nguyên."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
