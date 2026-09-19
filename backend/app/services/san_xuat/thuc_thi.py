"""Thực hiện sản xuất tại TỔ — lệnh GHI (Giai đoạn 2, §7.1–§7.2).

Điều phối phân công · phiên chạy · khoảng tham gia. Mỗi lệnh tuân §18: kiểm quyền tại service →
transaction → version chống bấm trùng → ghi audit → (SSE do router phát sau commit).

QUYỀN (mg 0302): hỏi DÒNG QUYỀN THEO TỔ của tổ thực hiện (`services/quyen_to.py`) — Thực hiện lệnh
cho lệnh ghi ở đây; các file khác truyền việc của mình qua `_gate(..., viec)`. Mức "Của tôi" chỉ qua
khi công việc đang giao cho chính người bấm. Không còn luật cứng "phải đứng tên trưởng tổ".

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
from ...models.may_thiet_bi import MayThietBi
from ...models.san_xuat import (
    BUOC_MAY,
    BUOC_THUE_NGOAI,
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
from ..bai_ghep_service import BaiGhepService
from ..may_trang_thai import NHAN as NHAN_TT_MAY
from ..may_trang_thai import TT_RANH, trang_thai_may
from ..quyen_to import VIEC_THUC_HIEN, gate_to
from .dau_vao import kiem_bat_dau
from .tinh_trang_nguoi import hom_nay, kiem_di_lam, kiem_khong_chay_viec_khac


def _moc() -> datetime:
    """Mốc thời gian máy chủ (aware UTC). Nguồn DUY NHẤT cho mọi mốc — không nhận từ client."""
    return datetime.now(timezone.utc)


# --- Trợ giúp chung -------------------------------------------------------------------------
def _lay_cong_viec(repo: SanXuatThucThiRepository, cong_viec_id: int) -> SanXuatCongViec:
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    return cv


def _gate(db: Session, user, cv: SanXuatCongViec, viec: str = VIEC_THUC_HIEN) -> None:
    """Người bấm phải có quyền `viec` trên tổ của công việc (dòng quyền theo tổ, mg 0302). Mức
    "Của tôi" chỉ qua khi công việc đang giao cho chính họ."""
    gate_to(db, getattr(user, "id", None), cv.department_id, viec, cong_viec_id=cv.id)


def _kiem_version(cv: SanXuatCongViec, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != cv.version:
        raise ValueError("Phiên bản không khớp — công việc vừa được cập nhật, hãy tải lại.")


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
    # Nghỉ dài hạn / đình chỉ / nghỉ phép đã duyệt HÔM NAY ⇒ không giao (tinh_trang_nguoi).
    kiem_di_lam(db, emp, hom_nay(), duoi="không giao việc được")
    la_khoan = _la_luong_khoan(db, emp)
    if cv.loai_buoc == BUOC_TO and not la_khoan:
        # Câu tổ đọc: nói "công nhật" (ngoại lệ) chứ đừng nói "lương khoán" — cùng chữ với bàn tổ.
        raise ValueError(f"{emp.full_name} là người công nhật — bước nội bộ không nhận người công nhật.")
    if repo.phan_cong_hoat_dong_cua(cong_viec_id, employee_id) is not None:
        raise ValueError("Nhân viên này đã được giao vào công việc.")
    # Việc đang chạy thì giao = mở khoảng tham gia ngay ⇒ người đang chạy việc khác bị chặn. Kiểm
    # TRƯỚC khi thêm dòng phân công, khỏi để dòng dở trong session khi báo lỗi.
    phien = repo.phien_dang_mo(cv.id) if cv.trang_thai == CV_DANG_CHAY else None
    if phien is not None:
        kiem_khong_chay_viec_khac(
            db, emp, duoi="việc này đang chạy nên không giao chồng được, dừng hoặc rút người đó ở việc kia trước"
        )

    pc = SanXuatPhanCong(
        cong_viec_id=cv.id,
        employee_id=employee_id,
        la_luong_khoan=la_khoan,
        trang_thai=PC_HOAT_DONG,
        created_by=getattr(user, "id", None),
    )
    repo.add(pc)

    # Thêm người GIỮA CHỪNG khi việc đang chạy → mở khoảng tham gia ngay (§7.2).
    if phien is not None:
        repo.add(
            SanXuatKhoangThamGia(
                cong_viec_id=cv.id,
                phien_chay_id=phien.id,
                employee_id=employee_id,
                bat_dau=_moc(),
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
    expected_version: int | None = None,
) -> dict:
    """Bắt đầu (hoặc Tiếp tục) chạy: mở phiên mới + mở khoảng tham gia cho mọi người đang trong tổ.

    Luật: phải có ≥1 thợ lương khoán đang được giao (§7.1); không ai được có khoảng tham gia chồng
    giờ (§7.1). Sớm hay trễ so với dự kiến KHÔNG hỏi lý do (gỡ 16/09/2026) — lệch giờ đọc thẳng từ
    mốc thực tế của phiên so với `du_kien_*`.

    ⚠️ CỔNG "số người khác dự kiến thì bắt chọn lý do" GỠ 18/09/2026 cùng toàn bộ logic KÍP (mg
    `0321`). Hệ thôi biết một việc *nên* mấy người, nên tổ cử 1 người vào việc 5 người cũng không ai
    cảnh báo — đúng chủ trương "máy chỉ ghi nhận". Luật ≥1 thợ thì Ở LẠI: đó là luật về NGƯỜI
    CÓ MẶT, không phải về cỡ kíp."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_PHAT_HANH, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chờ hoặc tạm dừng mới bắt đầu/tiếp tục được.")

    roster = repo.phan_cong_hoat_dong(cv.id)
    if not any(pc.la_luong_khoan for pc in roster):
        # Luật vẫn là ≥1 người hưởng khoán, nhưng câu báo dùng đúng chữ chân drawer bàn tổ
        # (`ThsxDrawer`): chưa giao ai thì bảo giao thợ; chỉ khi roster toàn công nhật mới nói lý do.
        if not roster:
            raise ValueError("Cần giao ít nhất 1 thợ mới bắt đầu được.")
        raise ValueError(
            "Người đang giao đều là công nhật — cần thêm ít nhất 1 thợ không phải công nhật mới bắt đầu được."
        )

    # Người trong tổ — kiểm TRƯỚC số người dự kiến: người vắng thì phải rút ra, đếm lại rồi mới
    # biết có lệch không. Không ai vắng mặt hôm nay (nghỉ dài hạn / đình chỉ / nghỉ phép đã
    # duyệt — giao từ hôm trước rồi mới có đơn), không ai đang mở khoảng ở việc khác (§7.1). Câu
    # báo gọi TÊN người và việc họ đang giữ; "Nhân viên #57" thì tổ trưởng không biết ai.
    ngay = hom_nay()
    for pc in roster:
        emp = repo.nhan_vien(pc.employee_id)
        if emp is None:
            continue
        kiem_di_lam(db, emp, ngay, duoi="rút người này khỏi tổ rồi mới bắt đầu được")
        kiem_khong_chay_viec_khac(
            db, emp, duoi="dừng hoặc rút người đó ở việc kia trước, không mở được hai việc chồng giờ"
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
    # Cổng ROUTING (19/09/2026): công đoạn sau làm trên đầu ra của công đoạn trước — chưa nhận gì
    # từ công đoạn trước thì chưa có gì để làm. Công đoạn đầu lệnh ⇒ no-op.
    kiem_bat_dau(sl_repo, cv)

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
    phien = SanXuatPhienChay(
        cong_viec_id=cv.id,
        so_thu_tu=repo.so_phien(cv.id) + 1,
        may_id=cv.may_id,          # ẢNH CHỤP máy lúc mở phiên — đổi máy sau này đẻ phiên khác
        bat_dau=now,
        created_by=getattr(user, "id", None),
    )
    repo.add(phien)
    repo.flush()  # cần phien.id để neo khoảng tham gia
    for pc in roster:
        repo.add(
            SanXuatKhoangThamGia(
                cong_viec_id=cv.id,
                phien_chay_id=phien.id,
                employee_id=pc.employee_id,
                bat_dau=now,
            )
        )

    cv.trang_thai = CV_DANG_CHAY
    cv.version += 1
    chi_tiet = f"phien={phien.so_thu_tu}"
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
    expected_version: int | None = None,
) -> dict:
    """Kết thúc: đóng phiên đang mở (nếu có) + khoảng tham gia, đánh dấu hoàn thành. Sớm hay trễ
    so với dự kiến đều không hỏi lý do (gỡ 16/09/2026)."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chạy hoặc tạm dừng mới kết thúc được.")

    now = _moc()
    phien = repo.phien_dang_mo(cv.id)
    if phien is not None:
        phien.ket_thuc = now
        phien.loai_dong = PHIEN_KET_THUC
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


def may_doi_duoc(db: Session, *, user, cong_viec_id: int) -> dict:
    """Ô "Đổi máy" của bàn tổ: máy đổi sang được + TÌNH TRẠNG LÚC NÀY của từng máy.

    Lọc cùng MỘT luật với gợi ý máy ở Xếp lịch (`BaiGhepService.may_ngoai_cong_doan`): công đoạn đã
    chọn máy cụ thể thì chỉ các máy đó, chưa chọn thì lùi về nhóm máy, chưa khai gì thì mọi máy. Bàn
    tổ phán khác bàn xếp lịch là tổ đổi sang một máy mà công đoạn không có công thức giờ để chạy.
    Bỏ sẵn máy đã ngừng dùng và máy đang gán — hai thứ `doi_may` sẽ từ chối.

    Tình trạng lấy ĐÚNG hàm của cột Trạng thái màn Thiết bị (`trang_thai_may`): hai màn tự tính là
    sớm muộn cùng một máy hiện hai chữ khác nhau. Chỉ để NHÌN, không chặn chọn — đúng lối "chỉ cảnh
    báo" chủ chốt cho phiếu sửa chữa; tổ đứng cạnh máy biết rõ hơn lịch.

    Tách endpoint riêng thay vì gắn vào chi tiết công việc: tình trạng phải là của LÚC mở ô chọn, và
    chi tiết nạp lại theo mọi tin SSE thì đừng kéo theo phép tính lịch của cả xưởng.
    """
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    if cv.loai_buoc not in (BUOC_MAY, BUOC_THUE_NGOAI) or cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        return {"items": [], "theo_cong_doan": False}
    cd = repo.cong_doan_cua_viec(cv)
    mays = [m for m in repo.may_con_dung()
            if m.id != cv.may_id and not BaiGhepService.may_ngoai_cong_doan(cd, m)]
    tt = trang_thai_may(db, [m.id for m in mays])
    ranh = {"trang_thai": TT_RANH, "nhan": NHAN_TT_MAY[TT_RANH], "chi_tiet": None}
    return {
        "items": [
            {"id": m.id, "ma": m.ma, "ten": m.ten, "loai_may": m.loai_may,
             **{k: tt.get(m.id, ranh)[k] for k in ("trang_thai", "nhan", "chi_tiet")}}
            for m in mays
        ],
        "theo_cong_doan": cd is not None and bool(cd.may_lam_duoc or cd.nhom_may_cho_phep),
    }


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
    thì không còn máy nào để đổi. Chỉ bước CHẠY MÁY (`BUOC_MAY`, và `BUOC_THUE_NGOAI` — nhà thầu
    khai như một máy trong danh mục) mới có khái niệm
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
    if cv.loai_buoc not in (BUOC_MAY, BUOC_THUE_NGOAI):
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
                nguoi.append(kh.employee_id)
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
        for emp_id in nguoi:
            repo.add(
                SanXuatKhoangThamGia(
                    cong_viec_id=cv.id,
                    phien_chay_id=phien_moi.id,
                    employee_id=emp_id,
                    bat_dau=now,
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

    Cầm được dao trong tay cũng là bằng chứng dao "làm mới" ĐÃ VỀ: danh mục lật `dang_dat_lam` →
    `dang_dung` (16/09/2026). Không lật thì dao mang chữ "đang đặt làm" mãi, lệnh sau dùng lại vẫn
    báo chưa về. Chỉ lật đúng `dang_dat_lam` — hỏng / thanh lý là người phán, cú tích không đè.
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
    _lat_dao_da_ve(db, repo, user, cv)
    _audit(db, user, "san_xuat_nhan_khuon", cv, detail=(cv.khuon_json or {}).get("ma") or "",
           commit=False)
    db.commit()
    return _ket_qua(cv)


def _lat_dao_da_ve(db: Session, repo: SanXuatThucThiRepository, user, cv: SanXuatCongViec) -> None:
    """`dang_dat_lam` → `dang_dung` ở danh mục + mọi ảnh chụp của việc chưa xong trỏ cùng dao.

    Ảnh chụp giữ để tổ thấy đúng CON DAO đã chốt; chữ tình trạng trong đó không phải thứ cần đóng
    băng, để nguyên là chip bàn tổ khác nói sai. Không cần bắn SSE riêng cho tổ khác: sự kiện
    `san_xuat_cong_viec_changed` của router đã làm mọi bàn đang mở tải lại. Nhật ký danh mục ghi
    cùng khuôn với sửa tay ở màn Khuôn."""
    from ...models.khuon_be import KhuonBe
    from ...repositories.khuon_be_repo import KhuonBeRepository
    from .. import nhat_ky_danh_muc as nk

    kid = (cv.khuon_json or {}).get("id")
    dao: KhuonBe | None = KhuonBeRepository(db).get(kid) if kid else None
    if dao is None or dao.tinh_trang != "dang_dat_lam":
        return
    truoc = nk.anh_chup(dao)
    dao.tinh_trang = "dang_dung"
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action=nk.ACTION_SUA,
        target=f"khuon_be:{dao.id}",
        detail=" · ".join(nk.mo_ta_thay_doi(truoc, nk.anh_chup(dao))),
        commit=False,
    )
    for c in {cv, *repo.cong_viec_mo_theo_khuon(dao.id)}:
        anh = c.khuon_json or {}
        if anh.get("tinh_trang") == "dang_dat_lam":
            # Gán dict MỚI: cột JSON không theo dõi sửa tại chỗ, `anh["tinh_trang"] = ...` không ghi.
            c.khuon_json = {**anh, "tinh_trang": "dang_dung"}


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
