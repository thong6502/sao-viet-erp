"""Bàn THỰC HIỆN tại tổ — mặt đọc (§11, §18 `/api/san-xuat/teams` + `/work-items`).

Đây là nền của Giai đoạn 2: mỗi node LÁ trong Khối Sản xuất là một tổ; tổ trưởng mở bàn của tổ
mình thấy các công việc ĐÃ PHÁT HÀNH (đọc từ snapshot gói, không đọc-sống routing). Lát này CHỈ
ĐỌC — phân công / phiên chạy / sản lượng là các lát sau (thêm bảng riêng).

Phạm vi tổ theo DÒNG QUYỀN THEO TỔ (mg 0302, `services/quyen_to.py`): mỗi nút khối Sản xuất một
dòng Xem · Phạm vi · 4 quyền chi tiết; bàn cấp gom gộp các tổ trực thuộc.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.may_thiet_bi import MayThietBi
from ...models.san_xuat import CV_TAM_DUNG
from ...models.san_xuat_phan_bo import HT_CHO_HAI_BEN, HT_HUY
from ...models.san_xuat_thuc_thi import PHIEN_TAM_DUNG
from ...models.user import User
from ...repositories.attendance_repo import AttendanceRepository
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from ...repositories.rbac_repo import DepartmentRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_ho_tro_repo import SanXuatHoTroRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ...repositories.san_xuat_vat_tu_repo import SanXuatVatTuRepository
from ...repositories.stock_request_repo import StockRequestRepository
from ...services.rbac_service import AuthorizationService
from ..quyen_to import (
    MUC_CUA_TOI,
    MUC_TAT_CA,
    VIEC_CHI_TIET,
    VIEC_THUC_HIEN,
    VIEC_XAC_NHAN,
    VIEC_XEM,
    QuyenTo,
    quyen_to_cua,
    quyen_tren_viec,
)
from ..gio_xuong import lich_hien_thi, thuc_te_hien_thi, ve_utc_that
from . import dau_vao, viec_khoan
from .nguoi_trong_me import nguoi_theo_me
from .thuc_thi import _aware
from .tinh_trang_nguoi import hom_nay, tinh_trang_nhieu
from .vat_tu_de_nghi import _hang_service, _kh_service, can_luc_hien_thi, lan_con_mo

MODULE = "san_xuat"


def _pham_vi_doc(db: Session, user: User, team_id: int | None) -> tuple[QuyenTo, str]:
    """(quyền tổ của user, mức XEM trên `team_id`) — chặn nếu tổ nằm ngoài phạm vi xem."""
    q = quyen_to_cua(db, user)
    muc = q.muc(VIEC_XEM, team_id)
    if muc is None:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")
    return q, muc


def _nhan_vien_id(db: Session, user: User) -> int | None:
    """Hồ sơ nhân viên nối với tài khoản. Chưa nối thì phần "Của tôi" rỗng — không rơi về "thấy hết"."""
    nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
    return nv.id if nv is not None else None


def _loc_viec_cua_tho(db: Session, user: User, rows: list) -> list:
    """Giữ lại đúng những việc user đang được giao. Tài khoản chưa nối hồ sơ nhân viên
    (`employee.user_id`) thì không có việc nào — không rơi về "thấy hết"."""
    tt = SanXuatThucThiRepository(db)
    nv = tt.nhan_vien_theo_user(user.id)
    if nv is None:
        return []
    cho_phep = tt.cong_viec_ids_duoc_giao(nv.id, {cv.id for cv in rows})
    return [cv for cv in rows if cv.id in cho_phep]


def teams(db: Session, user: User, authz: AuthorizationService) -> list[dict]:
    """Menu Bàn tổ = các nút khối Sản xuất user XEM được, theo thứ tự cây + cấp thụt lề (mg 0302).

    Bàn của một nút cấp gom phủ cả VÙNG của nó (nút + mọi đơn vị trực thuộc), nên badge của nút là
    tổng badge các tổ trong vùng — mỗi tổ đếm đúng phạm vi user: thấy trọn thì đếm cả tổ, chỉ
    "Của tôi" thì đếm việc đang giao cho mình (navbar báo đúng số dòng mở ra thấy).

    KCS không còn nằm trên menu Bàn tổ (KCS theo lệnh, mg 0306) — người KCS vào màn KCS riêng.
    `la_kcs` ở đây chỉ là `Department.is_kcs` của nút."""
    q = quyen_to_cua(db, user)
    ban = q.ban_thay_duoc()
    if not ban:
        return []
    repo = SanXuatRepository(db)
    tron, rieng = q.tron[VIEC_XEM], q.rieng[VIEC_XEM]
    nv_id = _nhan_vien_id(db, user) if rieng else None
    badge = repo.dem_cho_lam_theo_to(tron, employee_id=nv_id, rieng_ids=rieng)
    ids = {did for did, _, _ in ban}
    dept_map = {d.id: d for d in DepartmentRepository(db).list_all() if d.id in ids}
    bang = q.bang()
    cho_xn = _to_cho_xac_nhan(db, q.tron[VIEC_XAC_NHAN])
    ra = []
    for did, cap, muc in ban:
        d = dept_map.get(did)
        vung = q.cay.vung(did)
        ra.append({
            "id": did,
            "ten": d.name if d else q.cay.ten.get(did, ""),
            "ma": (d.code if d else None) or "",
            "cap": cap,
            "la_kcs": bool(getattr(d, "is_kcs", False)),
            # FE cần biết "tôi vào bàn này chỉ với phần CỦA TÔI" để bật băng *Sản lượng của tôi*
            # (§6). Trả con số đã tính sẵn, đừng để FE tự suy từ phạm vi.
            "la_tho": muc == MUC_CUA_TOI,
            "so_viec_cho": sum(badge.get(x, 0) for x in vung),
            "so_cho_xac_nhan": sum(1 for cac_to in cho_xn if cac_to & vung),
            # Mức từng việc trên CHÍNH nút này — thao tác cấp tổ (xác nhận vật tư, đóng thiếu nhóm,
            # hỗ trợ chéo) đòi `all`; nút trên từng công việc đọc `quyen` của drawer.
            "quyen": bang.get(did, {}),
        })
    return ra


def _num(x) -> float | None:
    return None if x is None else float(x)


def _may_thiet_bi_nhan(db: Session, may_ids: set[int]) -> dict[int, str]:
    """{may_id: tên máy} tra ĐÚNG danh mục `may_thiet_bi` — KHÁC bảng `machines` cũ mà
    `SanXuatRepository.may_nhan` dùng (đó là danh mục máy của Tính giá). `san_xuat_cong_viec.may_id`
    / `san_xuat_phien_chay.may_id` đều neo theo `MayThietBi.id` (xem `snapshot.py`), nên đọc TÊN máy cho phiên chạy phải tra đúng bảng này chứ không phải bảng cũ."""
    if not may_ids:
        return {}
    rows = db.execute(
        select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(may_ids))
    ).all()
    return {mid: ten for mid, ten in rows}


def _con_thieu(
    cv, tong_tot: float, thuc_nhan: float | None = None
) -> tuple[float | None, float | None]:
    """(mục tiêu, còn thiếu) của MỘT bước — dẫn xuất, KHÔNG lưu cột (spec-thuc-te-vs-ke-hoach §2.3).

    Mốc chấm là `so_luong_ra` (snapshot lúc phát hành, đã đúng `don_vi_ra`), so thẳng với
    `tong_tot` không cần quy đổi. NHƯNG khi tổ trước giao thiếu, chấm tổ này theo kế hoạch là đổ
    oan: hụt đó là của tổ trước. Nhận được bao nhiêu thì mốc rút theo bấy nhiêu — quy theo TỈ LỆ
    vì đầu vào và đầu ra khác đơn vị (nhận "tờ", ra "cái"): kế hoạch 12 tờ → 1.188 cái, thực nhận
    11 tờ ⇒ mốc còn 1.188 × 11 / 12 = 1.089 cái.

    Kế hoạch KHÔNG bị đè — `cv.so_luong_ra` vẫn nguyên, FE hiện cả hai số cạnh nhau.

    Mốc chỉ RÚT XUỐNG, không bao giờ đẩy lên: nhà in cố ý giao dư để bù hao (1.050 tờ cho 1.000
    cái), nhận dư không có nghĩa tổ phải làm nhiều hơn cam kết. Bỏ cái kẹp này là mốc phình theo
    lượng bù hao và tổ nào cũng "còn thiếu".

    Không nhận từ ai (`thuc_nhan is None` — bước ĐẦU chuỗi lấy vật tư từ kho) hoặc bước không khai
    `so_luong_vao` ⇒ giữ nguyên mốc kế hoạch. Bước không khai mục tiêu ⇒ trả None, đừng bịa 0:
    "còn thiếu 0" và "không biết thiếu bao nhiêu" là hai câu khác hẳn nhau.

    Chạy DƯ thì kẹp về 0 — số âm ở ô "còn thiếu" chỉ làm người đọc dừng lại đoán nghĩa.
    """
    if cv.so_luong_ra is None:
        return None, None
    muc_tieu = float(cv.so_luong_ra)
    vao = None if cv.so_luong_vao is None else float(cv.so_luong_vao)
    if thuc_nhan is not None and vao is not None and vao > 0:
        muc_tieu = min(muc_tieu, muc_tieu * float(thuc_nhan) / vao)
    return muc_tieu, max(muc_tieu - float(tong_tot), 0.0)


def _thuc_nhan(cv, nhan_map: dict[int, dict[str, float]]) -> float | None:
    """Lượng bước này nhận được, tính THEO ĐÚNG đơn vị đầu vào của nó.

    Bàn giao ghi đơn vị riêng; lấy nhầm đơn vị rồi đem chia cho `so_luong_vao` là ra con số bịa
    (nhận 26.888 "con" chia cho 68 "tờ"). Bước không khai `don_vi_vao`, hoặc không có bàn giao nào
    đúng đơn vị đó ⇒ None = coi như không rút mốc, giữ kế hoạch."""
    theo_dv = nhan_map.get(cv.id)
    if not theo_dv or not cv.don_vi_vao:
        return None
    return theo_dv.get(cv.don_vi_vao)


def _so_lieu_map(
    rows, tot_map: dict[int, float], nhan_map: dict[int, dict[str, float]]
) -> dict[int, dict]:
    """{cong_viec_id: ba số thực tế + còn thiếu} cho cả bàn tổ — nạp GỘP một lần, không hỏi
    `tong_tot`/bàn giao theo từng dòng."""
    ket = {}
    for cv in rows:
        tot = tot_map.get(cv.id, 0.0)
        nhan = _thuc_nhan(cv, nhan_map)
        muc_tieu, thieu = _con_thieu(cv, tot, nhan)
        ket[cv.id] = {
            "thuc_nhan": nhan, "da_lam": tot, "muc_tieu": muc_tieu, "con_thieu": thieu,
        }
    return ket


def _dm(cv, khoa: str):
    """Một khoá của `dinh_muc_json` — ảnh chụp CŨ thiếu khoá thêm sau thì trả None, không nổ.

    Không ép kiểu và không lấp 0: khoá vắng nghĩa là "lệnh phát hành trước ngày có khoá này", mà
    0 phút chạy / kíp 0 người là câu khác hẳn và FE sẽ bày ra như số thật.
    """
    return cv.dinh_muc_json.get(khoa) if isinstance(cv.dinh_muc_json, dict) else None


def _item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map=None, so_map=None,
               chay_ids: set[int] | None = None, kcs_map=None, khach_map=None) -> dict:
    """Một dòng công việc trên timeline — nhãn nguồn/nhóm/máy đã resolve theo lô (§18)."""
    if cv.bai_ghep_id and cv.bai_ghep_id in bg_map:
        nguon_ma, nguon_ten = bg_map[cv.bai_ghep_id]
        nguon_loai = "bai_ghep"
        khach = (khach_map or {}).get(("bai_ghep", cv.bai_ghep_id))
    elif cv.lsx_id and cv.lsx_id in lsx_map:
        nguon_ma, nguon_ten = lsx_map[cv.lsx_id]
        nguon_loai = "lsx"
        khach = (khach_map or {}).get(("lsx", cv.lsx_id))
    else:
        nguon_ma, nguon_ten, nguon_loai, khach = "", "", "", None
    return {
        "id": cv.id,
        # Tổ THẬT của việc — bàn nút cha gộp việc nhiều tổ con, nên thao tác theo tổ (danh chọn
        # người, xác nhận nhận vật tư) phải lấy tổ ở đây chứ không lấy nút đang mở.
        "department_id": cv.department_id,
        "goi_id": cv.goi_id,
        "phien_ban_so": cv.phien_ban_so,
        "nguon_loai": nguon_loai,
        "nguon_ma": nguon_ma,
        "nguon_ten": nguon_ten,
        # Tên khách của lệnh (bài ghép: khách mọi lệnh thành viên) — tổ nhìn biết hàng của ai.
        "khach_hang": khach,
        "nhom_id": cv.nhom_id,
        "nhom": nhom_map.get(cv.nhom_id or 0, ""),
        "ten_cong_doan": cv.ten_cong_doan,
        "nhom_cong_doan": cv.nhom_cong_doan,
        "loai_buoc": cv.loai_buoc,
        "la_kcs_cuoi": cv.la_kcs_cuoi,
        # Dấu KCS trên thẻ việc (KCS theo lệnh): số lần kiểm + Σ đạt/lỗi. Chỗ gọi không nạp
        # `kcs_map` thì để 0 — drawer đọc chi tiết qua mục "Kết quả KCS".
        "kcs_so_lan": (kcs_map or {}).get(cv.id, (0, 0.0, 0.0))[0],
        "kcs_dat": (kcs_map or {}).get(cv.id, (0, 0.0, 0.0))[1],
        "kcs_loi": (kcs_map or {}).get(cv.id, (0, 0.0, 0.0))[2],
        "may": may_map.get(cv.may_id or 0, ""),
        "may_id": cv.may_id,      # máy HIỆN TẠI — FE cần để dựng ô chọn "Đổi máy" (§7.2 mở rộng)
        # Hai thang giờ khác nhau gặp nhau ở ĐÂY (xem `services/gio_xuong.py`): mốc kế hoạch là
        # giờ tường dán nhãn UTC, mốc phiên chạy là UTC THẬT. Cùng quy về wall-clock giờ xưởng
        # rồi mới trả — không thì cùng một thanh Gantt đo bằng hai cây thước lệch nhau 7 tiếng.
        "du_kien_bat_dau": lich_hien_thi(cv.du_kien_bat_dau),
        "du_kien_ket_thuc": lich_hien_thi(cv.du_kien_ket_thuc),
        # Lúc việc tới tay tổ = lúc phát hành tạo thẻ việc (`created_at`, UTC THẬT → giờ xưởng).
        # "Phát hành cập nhật" sửa đè tại chỗ nên mốc này giữ nguyên lần nhận đầu.
        "nhan_luc": thuc_te_hien_thi(cv.created_at),
        # Số người dự kiến chốt lúc phát hành (§7.1) — FE so với roster để đòi lý do khi lệch.
        # Bước NGOÀI dòng giấy: đo bằng đơn vị của CHÍNH nó (ghi kẽm đếm bản, đóng thùng đếm
        # thùng) nên `so_luong_vao == so_luong_ra` và cột "SL vào → ra" phải hiện MỘT số. Cờ này
        # là ảnh chụp lúc phát hành — FE không suy lại được từ mã đơn vị, xem `dinh_muc_json`.
        "ngoai_dong": bool(_dm(cv, "ngoai_dong")),
        # Dải thời lượng chạy: ba số cùng thang, bằng nhau khi máy chưa khai tốc độ min/max.
        "chay_phut": _dm(cv, "chay_phut"),
        "chay_phut_min": _dm(cv, "chay_phut_min"),
        "chay_phut_max": _dm(cv, "chay_phut_max"),
        # Dặn dò của kế hoạch + thẻ quy cách rút gọn — hai thứ tổ trưởng không có cửa nào tra
        # ngược (không có quyền `lsx`), nên chúng đi theo thẻ việc từ lúc phát hành.
        "ghi_chu": cv.ghi_chu,
        "quy_cach": cv.quy_cach_json or None,
        "so_luong_vao": _num(cv.so_luong_vao),
        "so_luong_ra": _num(cv.so_luong_ra),
        "don_vi_vao": cv.don_vi_vao,
        "don_vi_ra": cv.don_vi_ra,
        "trang_thai": cv.trang_thai,
        # Ba số thực tế + còn thiếu — dẫn xuất, chỉ để BÀY (§2.3). `muc_tieu` đã rút theo lượng
        # THỰC NHẬN (xem `_con_thieu`), còn `so_luong_ra` ở trên vẫn là kế hoạch nguyên vẹn. Chỗ
        # gọi không nạp `so_map` (vd. khối "cong_viec" của drawer) thì cứ None, không bịa số.
        "thuc_nhan": (so_map or {}).get(cv.id, {}).get("thuc_nhan"),
        "da_lam": (so_map or {}).get(cv.id, {}).get("da_lam"),
        "muc_tieu": (so_map or {}).get(cv.id, {}).get("muc_tieu"),
        "con_thieu": (so_map or {}).get(cv.id, {}).get("con_thieu"),
        # Định mức vật tư đóng băng lúc phát hành (§4.2) — đã đúng hình `VatTuDinhMucOut`, không cần dựng lại.
        "dinh_muc_vat_tu": cv.vat_tu_json or [],
        # Nhà gia công + khuôn — ảnh chụp lúc phát hành, thẻ việc tự đứng được không tra ngược lệnh.
        "nha_cung_cap": cv.nha_cung_cap,
        "khuon": cv.khuon_json or None,
        "khuon_da_nhan": cv.khuon_nhan_luc is not None,
        "khuon_da_tra": cv.khuon_tra_luc is not None,
        # Lớp thực-tế (§5.1): các phiên chạy đã ghi; phiên còn mở giữ ket_thuc=None (FE kéo tới "bây giờ").
        "thuc_te": [
            {"bat_dau": thuc_te_hien_thi(p.bat_dau), "ket_thuc": thuc_te_hien_thi(p.ket_thuc)}
            for p in (phien_map or {}).get(cv.id, [])
        ],
        # Người xem bấm được Bắt đầu / Tạm dừng / Kết thúc ngay trên dòng? Chỗ gọi không truyền
        # `chay_ids` (vd. khối "cong_viec" của drawer — drawer đọc `quyen`) thì cứ False.
        "chay_duoc": cv.id in (chay_ids or ()),
    }


def _viec_chay_duoc(db: Session, user: User, q: QuyenTo, rows: list) -> set[int]:
    """Việc nào người xem giữ Thực hiện lệnh — cùng luật `quyen_tren_viec`, nhưng gộp MỘT truy vấn
    phân công cho mọi việc mức "Của tôi" thay vì hỏi từng dòng."""
    ra: set[int] = set()
    cho_rieng: set[int] = set()
    for cv in rows:
        muc = q.muc(VIEC_THUC_HIEN, cv.department_id)
        if muc == MUC_TAT_CA:
            ra.add(cv.id)
        elif muc == MUC_CUA_TOI:
            cho_rieng.add(cv.id)
    if cho_rieng:
        emp_id = _nhan_vien_id(db, user)
        if emp_id is not None:
            ra |= SanXuatThucThiRepository(db).cong_viec_ids_duoc_giao(emp_id, cho_rieng)
    return ra


def _dung_items(db: Session, repo: SanXuatRepository, rows: list,
                chay_ids: set[int] | None = None) -> list[dict]:
    """Dựng payload thẻ việc cho một tập bước — GỘP mọi truy vấn phụ, không N+1 theo dòng."""
    if not rows:
        return []
    lsx_map = repo.lsx_nhan({cv.lsx_id for cv in rows if cv.lsx_id})
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id for cv in rows if cv.bai_ghep_id})
    khach_map = repo.khach_nhan({cv.lsx_id for cv in rows if cv.lsx_id},
                                {cv.bai_ghep_id for cv in rows if cv.bai_ghep_id})
    may_map = repo.may_nhan({cv.may_id for cv in rows if cv.may_id})
    nhom_map = repo.nhom_nhan({cv.nhom_id for cv in rows if cv.nhom_id})
    # Lớp thực-tế: phiên chạy của cả gói trong MỘT truy vấn (§5.1), tránh N+1 theo từng việc.
    phien_map = SanXuatThucThiRepository(db).phien_theo_cong_viec({cv.id for cv in rows})
    # Còn thiếu (§2.3): nạp tổng TỐT gộp cho cả bàn tổ rồi tính tại chỗ — không gọi `tong_tot`
    # (một truy vấn/việc) theo từng dòng, bàn tổ có thể có hàng chục công việc.
    sl_repo = SanXuatSanLuongRepository(db)
    cv_ids = {cv.id for cv in rows}
    so_map = _so_lieu_map(rows, sl_repo.tong_tot_nhieu(cv_ids),
                          sl_repo.tong_thuc_nhan_nhieu(cv_ids))
    kcs_map = SanXuatKcsRepository(db).tong_kiem_nhieu(cv_ids)
    return [
        _item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map, so_map, chay_ids, kcs_map,
                   khach_map)
        for cv in rows
    ]


def _trong_cua_so(cv, tu_ngay: date | None, den_ngay: date | None) -> bool:
    """Bước có GIAO với cửa sổ ngày? Bước chưa xếp giờ LUÔN giữ lại — nó nằm ở khúc "chưa định
    giờ" của cột trái, cắt nó theo cửa sổ là làm nó mất hẳn khỏi mọi trang."""
    if cv.du_kien_bat_dau is None or cv.du_kien_ket_thuc is None:
        return True
    if den_ngay is not None and cv.du_kien_bat_dau.date() > den_ngay:
        return False
    if tu_ngay is not None and cv.du_kien_ket_thuc.date() < tu_ngay:
        return False
    return True


def _dau_ngay_xuong(d: date | None) -> datetime | None:
    """0 giờ của một NGÀY XƯỞNG → UTC THẬT, để so với `created_at` (thang thực thi)."""
    if d is None:
        return None
    return ve_utc_that(datetime.combine(d, time.min, tzinfo=timezone.utc))


def _digest(rows) -> dict[str, int]:
    """Đếm bước theo trạng thái cho nhãn của một lệnh — cùng bốn khoá mà FE `sxDigest` dùng."""
    d = {"released": 0, "running": 0, "paused": 0, "completed": 0}
    for cv in rows:
        d[cv.trang_thai if cv.trang_thai in d else "released"] += 1
    return d


def work_items(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int,
    nhom: str = "lenh",
    tim: str | None = None,
    trang: int = 1,
    co_trang: int = 20,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    cho_xac_nhan: bool = False,
    trang_thai: set[str] | None = None,
    nhan_tu: date | None = None,
    nhan_den: date | None = None,
    sap_xep: str = "moi_nhan",
) -> dict:
    """Việc đã phát hành của MỘT tổ. Hai hình, chọn bằng `nhom`:

    · `"lenh"` (mặc định) — **đầu mục là LỆNH SX / BÀI GHÉP**, mỗi lệnh một dòng, bên trong là các
      CÔNG ĐOẠN của chính tổ này (thẻ việc giữ nguyên hình cũ — đơn vị việc vẫn là công đoạn).
      Chủ xưởng chốt 11/09/2026: *"lệnh hoặc bài ghép thôi, chứ không làm sao tôi biết được công
      đoạn đó cho lệnh nào"*. Gom nhóm + CẮT TRANG ở máy chủ, đơn vị trang là LỆNH.
    · `"phang"` — mảng bước phẳng như trước, cho view **Gantt** (trục thời gian không có tầng
      lệnh). Nhận thêm cửa sổ `tu_ngay`/`den_ngay` để Gantt chỉ kéo đúng khoảng đang xem thay vì
      cả bàn.

    `tim` (ô tìm kiếm của bàn) lọc Ở SQL, trước khi cắt trang — chỉ có nghĩa với `nhom="lenh"`;
    chế độ phẳng kéo trọn bàn nên màn tự lọc lấy.

    Bàn của nút cấp gom phủ cả VÙNG của nút (mg 0302). Trong vùng, tổ nào user thấy trọn thì lấy
    cả tổ; tổ nào chỉ "Của tôi" thì chỉ việc đang giao cho mình — lọc ĐẨY XUỐNG SQL, trước cả lúc
    gom lệnh và cắt trang (§6 spec). Router ép kiểu `nhom` bằng `Literal` trước khi gọi
    xuống đây — service nhận `str` thô là đủ.

    `cho_xac_nhan` (ô "chờ xác nhận" của bàn, §11.5): chỉ giữ lệnh có ÍT NHẤT MỘT công đoạn đang
    chờ tổ bấm (bàn giao đến · hỗ trợ chéo · lỗi KCS chưa xem) — lọc trước khi cắt trang, cả lệnh
    vẫn hiện đủ công đoạn của tổ.

    Lọc nâng cao (chỉ `nhom="lenh"`, lọc trước khi cắt trang): `trang_thai` giữ lệnh có bước ở
    trạng thái ấy VÀ trong lệnh chỉ bày các bước khớp; `nhan_tu`/`nhan_den` là NGÀY XƯỞNG (gồm cả
    hai đầu) của lúc tổ nhận lệnh; `sap_xep` mặc định lệnh nhận SAU nằm trên — xem repo."""
    repo = SanXuatRepository(db)
    q, _muc = _pham_vi_doc(db, user, team_id)
    tron, rieng = q.pham_vi_ban(team_id)
    emp_id = _nhan_vien_id(db, user) if rieng else None
    chi_ids = _cv_cho_xac_nhan(db, q, team_id) if cho_xac_nhan else None

    if nhom == "phang":
        rows = repo.cong_viec_cua_to(tron, employee_id=emp_id, rieng_ids=rieng)
        if tu_ngay is not None or den_ngay is not None:
            rows = [cv for cv in rows if _trong_cua_so(cv, tu_ngay, den_ngay)]
        if chi_ids is not None:
            rows = [cv for cv in rows if cv.id in chi_ids]
        return {"team_id": team_id, "nhom": "phang",
                "cong_viec": _dung_items(db, repo, rows, _viec_chay_duoc(db, user, q, rows))}

    khoa_trang, tong = repo.lenh_cua_to_phan_trang(
        tron, employee_id=emp_id, rieng_ids=rieng, tim=tim, trang=trang,
        co_trang=co_trang, chi_cong_viec_ids=chi_ids, trang_thai=trang_thai,
        nhan_tu=_dau_ngay_xuong(nhan_tu),
        nhan_den=_dau_ngay_xuong(nhan_den + timedelta(days=1) if nhan_den else None),
        sap_xep=sap_xep)
    khoa = [k for k, _, _ in khoa_trang]
    rows = repo.cong_viec_cua_lenh(tron, khoa, employee_id=emp_id, rieng_ids=rieng)
    # "Nhận" của lệnh tính trên MỌI bước của tổ (cùng khoá sắp của repo), trước khi lọc trạng thái.
    nhan_lenh: dict[tuple[str, int | None], datetime] = {}
    for cv in rows:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        if cv.created_at and (k not in nhan_lenh or cv.created_at < nhan_lenh[k]):
            nhan_lenh[k] = cv.created_at
    if trang_thai:
        rows = [cv for cv in rows if cv.trang_thai in trang_thai]
    item_theo_id = {it["id"]: it for it in _dung_items(db, repo, rows, _viec_chay_duoc(db, user, q, rows))}
    cv_theo_khoa: dict[tuple[str, int | None], list] = {}
    for cv in rows:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id else ("lsx", cv.lsx_id)
        cv_theo_khoa.setdefault(k, []).append(cv)

    lsx_map = repo.lsx_nhan({i for loai, i in khoa if loai == "lsx" and i})
    bg_map = repo.bai_ghep_nhan({i for loai, i in khoa if loai == "bai_ghep" and i})
    ra: list[dict] = []
    for (loai, nid), som, muon in khoa_trang:
        cvs = cv_theo_khoa.get((loai, nid), [])
        ma, ten = (bg_map if loai == "bai_ghep" else lsx_map).get(nid or 0, ("", ""))
        ma, ten = ma or "", ten or ""
        # Khách lấy lại từ thẻ việc đã dựng (cùng lệnh ⇒ cùng khách), khỏi tra DB thêm lượt nữa.
        khach = next((item_theo_id[cv.id]["khach_hang"] for cv in cvs if cv.id in item_theo_id), None)
        ra.append({
            "nguon_loai": loai,
            "nguon_ma": ma,
            "nguon_ten": ten,
            "khach_hang": khach,
            "lsx_id": nid if loai == "lsx" else None,
            "bai_ghep_id": nid if loai == "bai_ghep" else None,
            "som_nhat": lich_hien_thi(som),
            "muon_nhat": lich_hien_thi(muon),
            "nhan_luc": thuc_te_hien_thi(nhan_lenh.get((loai, nid))),
            "so_viec": len(cvs),
            "digest": _digest(cvs),
            "cong_viec": [item_theo_id[cv.id] for cv in cvs if cv.id in item_theo_id],
        })
    return {"team_id": team_id, "nhom": "lenh",
            "trang": {"trang": trang, "co_trang": co_trang, "tong": tong},
            "lenh": ra}


def nhan_vien_chon(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int
) -> dict:
    """Nhân viên chọn được để GIAO vào việc của một tổ (ô "Giao người" ở drawer, §7.1).

    Cùng phạm vi ĐỌC như `work_items` (tổ phải trong quyền user, nếu không → chặn). Endpoint riêng
    của module `san_xuat` để tổ trưởng KHÔNG cần quyền `nhan_su` mới đổ được danh chọn. `la_luong_khoan`
    suy từ `has_piece_work` của chính tổ (mọi người trong tổ cùng chế độ) — FE lọc/cảnh báo cho bước
    nội bộ (`loai_buoc=="to"` chỉ nhận thợ khoán). `co_tai_khoan` để biết ai nhận được thông báo đẩy.
    """
    _pham_vi_doc(db, user, team_id)
    dept = db.get(Department, team_id)
    la_khoan = bool(dept and dept.has_piece_work)
    ds = SanXuatThucThiRepository(db).nhan_vien_cua_to(team_id)
    # Đang chạy việc nào / chờ mấy việc / nghỉ gì — xem `tinh_trang_nguoi`. Ngày là ngày XƯỞNG.
    ngay = hom_nay()
    tt = tinh_trang_nhieu(db, ds, ngay=ngay)
    return {
        "team_id": team_id,
        "hom_nay": ngay,
        "nhan_vien": [
            {
                "id": e.id,
                "code": e.code,
                "full_name": e.full_name,
                "la_luong_khoan": la_khoan,
                "co_tai_khoan": e.user_id is not None,
                **tt[e.id],
            }
            for e in ds
        ],
    }


def _to_cho_xac_nhan(db: Session, xn_ids: set[int]) -> list[set[int]]:
    """Mỗi việc đang chờ xác nhận → tập tổ (trong `xn_ids`) đang phải đứng tên cho nó. Badge menu
    đếm một việc cho một nút khi tập đó chạm vùng của nút — một thỏa thuận chờ cả hai tổ trong
    cùng vùng chỉ đếm một lần."""
    if not xn_ids:
        return []
    ra: list[set[int]] = [
        {dept} for _bg, dept in SanXuatSanLuongRepository(db).ban_giao_cho_nhan_cua_to(xn_ids)
    ]
    for h in SanXuatHoTroRepository(db).ho_tro_cho_cua_to(xn_ids):
        ra.append(_ben_cho(h, xn_ids))
    # Lỗi KCS tổ chưa bấm "Đã xem" — cũng là việc tổ phải bấm, badge đếm chung.
    ra.extend({l.to_chiu_id} for l in SanXuatKcsRepository(db).loi_chua_xem_nhieu_to(xn_ids))
    return ra


def _ben_cho(h, xn_ids: set[int]) -> set[int]:
    """Tổ trong `xn_ids` còn chưa đứng tên xác nhận thỏa thuận hỗ trợ `h`."""
    ben: set[int] = set()
    if h.xac_nhan_goc_by_id is None and h.to_goc_id in xn_ids:
        ben.add(h.to_goc_id)
    if h.xac_nhan_thuc_hien_by_id is None and h.to_thuc_hien_id in xn_ids:
        ben.add(h.to_thuc_hien_id)
    return ben


def _cv_cho_xac_nhan(db: Session, q, team_id: int) -> set[int]:
    """Công đoạn đang có việc chờ tổ bấm trên bàn `team_id` — cùng ba nguồn, cùng luật tổ với
    `cho_xac_nhan`, nhưng chỉ lấy id để lọc bảng việc (không dựng nhãn)."""
    xn_ids = set(q.cay.vung(team_id)) & q.tron[VIEC_XAC_NHAN]
    if not xn_ids:
        return set()
    ids = {bg.dich_cong_viec_id for bg, _dept in SanXuatSanLuongRepository(db).ban_giao_cho_nhan_cua_to(xn_ids)}
    ids |= {h.cong_viec_id for h in SanXuatHoTroRepository(db).ho_tro_cho_cua_to(xn_ids)}
    kcs = SanXuatKcsRepository(db)
    loi = kcs.loi_chua_xem_nhieu_to(xn_ids)
    # Lỗi quy về công đoạn đứng trước nằm ở công đoạn CHỊU lỗi, không phải công đoạn của lần kiểm —
    # cùng luật với `kcs.loi_cho_xem`, không thì bàn tổ chịu lỗi lọc ra trắng.
    batch = kcs.kcs_batch_nhieu({l.kcs_batch_id for l in loi if not l.cong_doan_ref_id})
    ids |= {l.cong_doan_ref_id or (batch[l.kcs_batch_id].cong_viec_id if l.kcs_batch_id in batch else None)
            for l in loi}
    return {i for i in ids if i}


def cho_xac_nhan(db: Session, user: User, *, team_id: int) -> dict:
    """Việc chờ tổ bấm trên bàn `team_id` (§9.1, §11.2, §11.5, §18).

    Ba loại việc tổ mình phải bấm: bàn giao đến chờ nhận, thỏa thuận hỗ trợ chéo chờ bên mình — kể
    cả khi tổ mình chỉ CHO MƯỢN người nên không có công đoạn đó trên bàn — và lỗi KCS báo về tổ
    chưa bấm "Đã xem" (KCS theo lệnh, mg 0306).
    Chỉ tính tổ trong vùng của bàn mà user giữ Xác nhận sản lượng trọn tổ (cùng luật với nút ghi).

    `tren_ban`: công đoạn của dòng nằm trong tổ user thấy TRỌN trên bàn này ⇒ bàn đã vẽ nó (chấm đỏ
    trên dòng, xác nhận trong ngăn chi tiết). `False` (thường là tổ cho mượn người) ⇒ không có dòng
    nào để gắn, bàn liệt kê riêng khi bật ô "chờ xác nhận"."""
    q, _muc = _pham_vi_doc(db, user, team_id)
    xn_ids = set(q.cay.vung(team_id)) & q.tron[VIEC_XAC_NHAN]
    if not xn_ids:
        return {"team_id": team_id, "ban_giao": [], "ho_tro": [], "kcs_loi": []}
    tron, _rieng = q.pham_vi_ban(team_id)
    repo = SanXuatRepository(db)
    sl = SanXuatSanLuongRepository(db)
    bgs = [bg for bg, _dept in sl.ban_giao_cho_nhan_cua_to(xn_ids)]
    hts = SanXuatHoTroRepository(db).ho_tro_cho_cua_to(xn_ids)
    from .kcs import loi_cho_xem  # import muộn: kcs.py đọc ngược board lúc gác phạm vi

    kcs_loi = loi_cho_xem(db, xn_ids)
    cvs = sl.cong_viec_nhieu(
        {b.nguon_cong_viec_id for b in bgs} | {b.dich_cong_viec_id for b in bgs}
        | {h.cong_viec_id for h in hts} | {l["cong_viec_id"] for l in kcs_loi}
    )

    def _tren_ban(cid) -> bool:
        cv = cvs.get(cid)
        return cv is not None and cv.department_id in tron
    to_ten = repo.to_ten_nhan(
        {c.department_id for c in cvs.values() if c.department_id}
        | {h.to_goc_id for h in hts if h.to_goc_id}
    )
    lsx_map = repo.lsx_nhan({c.lsx_id for c in cvs.values() if c.lsx_id})
    ten_map = repo.nhan_vien_nhan({h.employee_id for h in hts})

    def _cv(cid):
        return cvs.get(cid)

    def _lsx_ma(cv):
        return lsx_map.get(cv.lsx_id, (None, None))[0] if cv is not None and cv.lsx_id else None

    ban_giao = []
    for b in bgs:
        nguon, dich = _cv(b.nguon_cong_viec_id), _cv(b.dich_cong_viec_id)
        ban_giao.append({
            "id": b.id,
            "nguon_cong_viec_id": b.nguon_cong_viec_id,
            "nguon_ten": nguon.ten_cong_doan if nguon else "",
            "nguon_to_ten": to_ten.get(nguon.department_id) if nguon and nguon.department_id else None,
            "dich_cong_viec_id": b.dich_cong_viec_id,
            "dich_ten": dich.ten_cong_doan if dich else "",
            "dich_to_ten": to_ten.get(dich.department_id) if dich and dich.department_id else None,
            "lsx_ma": _lsx_ma(dich),
            "so_luong": float(b.so_luong),
            "don_vi": b.don_vi,
            "de_xuat_luc": thuc_te_hien_thi(b.de_xuat_luc),
            "version": b.version,
            "tren_ban": _tren_ban(b.dich_cong_viec_id),
        })
    ho_tro = []
    for h in hts:
        cv = _cv(h.cong_viec_id)
        ben = _ben_cho(h, xn_ids)
        ho_tro.append({
            "id": h.id,
            "cong_viec_id": h.cong_viec_id,
            "ten_cong_doan": cv.ten_cong_doan if cv else "",
            "lsx_ma": _lsx_ma(cv),
            "ho_ten": ten_map.get(h.employee_id, ("", None))[0],
            "to_goc_ten": to_ten.get(h.to_goc_id) if h.to_goc_id else None,
            "to_thuc_hien_ten": to_ten.get(h.to_thuc_hien_id) if h.to_thuc_hien_id else None,
            "ngay_lam_viec": h.ngay_lam_viec,
            "mo_ta": h.mo_ta,
            "cho_ben_goc": h.to_goc_id in ben,
            "cho_ben_thuc_hien": h.to_thuc_hien_id in ben,
            "version": h.version,
            "tren_ban": _tren_ban(h.cong_viec_id),
        })
    for l in kcs_loi:
        l["tren_ban"] = _tren_ban(l["cong_viec_id"])

    return {"team_id": team_id, "ban_giao": ban_giao, "ho_tro": ho_tro, "kcs_loi": kcs_loi}


def ho_tro_ung_vien(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int
) -> dict:
    """Ứng viên đề xuất HỖ TRỢ CHÉO cho một tổ (§9): thợ ở các tổ SX KHÁC. Cùng phạm vi ĐỌC như
    `work_items` (tổ phải trong quyền user). Mỗi ứng viên kèm nhãn tổ gốc để tổ trưởng biết đang
    mời ai từ đâu."""
    _pham_vi_doc(db, user, team_id)
    # Ứng viên = thợ mọi tổ SX (kể cả tổ user không quản), trừ tổ đang thực hiện.
    moi_to = DepartmentRepository(db).to_san_xuat()
    to_ten = {d.id: d.name for d in moi_to}
    ds = SanXuatThucThiRepository(db).nhan_vien_ho_tro_ung_vien(
        {d.id for d in moi_to}, team_id
    )
    ngay = hom_nay()
    tt = tinh_trang_nhieu(db, ds, ngay=ngay)
    return {
        "team_id": team_id,
        "hom_nay": ngay,
        "nhan_vien": [
            {
                "id": e.id,
                "code": e.code,
                "full_name": e.full_name,
                "to_id": e.department_id,
                "to_ten": to_ten.get(e.department_id) if e.department_id else None,
                **tt[e.id],
            }
            for e in ds
        ],
    }


def _lan_dung_may(phien_rows, cv) -> list[tuple[datetime, datetime | None, str]]:
    """Các lần DỪNG MÁY của công việc (§5.2): `(tu, den, ly_do)`, mốc UTC thật.

    Bấm Tạm dừng là ĐÓNG phiên đang chạy (`loai_dong='tam_dung'` + lý do), nên máy dừng TỪ
    `ket_thuc` của phiên đó TỚI lúc phiên kế tiếp mở. Không có phiên kế: việc còn tạm dừng thì chưa
    hết dừng (`den` None); đã Kết thúc thẳng từ lúc dừng thì hết ở `hoan_thanh_luc`.

    Khoảng [bat_dau, ket_thuc] của chính phiên tạm dừng là lúc máy CHẠY. Lấy nó làm giờ dừng là mẻ
    09:09–09:11 hiện "Dừng máy 09:09–00:21" cho lần hết giấy lúc nửa đêm (DB dev 17/09/2026)."""
    ra = []
    for i, p in enumerate(phien_rows):
        if p.loai_dong != PHIEN_TAM_DUNG or not p.ly_do or p.ket_thuc is None:
            continue
        tu = _aware(p.ket_thuc)
        if i + 1 < len(phien_rows):
            den = _aware(phien_rows[i + 1].bat_dau)
        elif cv.trang_thai == CV_TAM_DUNG:
            den = None
        else:
            den = _aware(cv.hoan_thanh_luc) if cv.hoan_thanh_luc is not None else tu
        ra.append((tu, den, p.ly_do))
    return ra


def _dung_giao_me(lan_dung, b) -> list[tuple[datetime, datetime | None, str]]:
    """Các lần dừng máy GIAO với cửa sổ mẻ. Chạm đúng mép (dừng lúc mẻ vừa xong, chạy lại lúc mẻ
    sau vừa bắt đầu) không tính — không thì một lần dừng hiện ở cả hai mẻ kề nhau. Dừng chưa hết
    coi như kéo tới hiện tại."""
    bd, kt = _aware(b.bat_dau), _aware(b.ket_thuc)
    return [d for d in lan_dung if d[0] < kt and (d[1] is None or d[1] > bd)]


def _phien_giao_me(phien_rows, b) -> list:
    """Các phiên chạy GIAO với cửa sổ mẻ — nền của "máy nào chạy mẻ này" (§5.2). Máy đứng trên
    PHIÊN chứ không trên công việc, nên đọc `cv.may_id` chỉ ra máy HIỆN TẠI, sai cho mẻ chạy trước
    lúc đổi máy. Lần dừng máy của mẻ KHÔNG đọc ở đây, xem `_lan_dung_may`.

    Ép `_aware` vì SQLite trả naive (bẫy naive/aware của module). Phiên đang mở (`ket_thuc` NULL)
    coi như kéo dài tới hiện tại nên vẫn tính là giao."""
    bd, kt = _aware(b.bat_dau), _aware(b.ket_thuc)
    ra = []
    for p in phien_rows:
        pbd = _aware(p.bat_dau)
        pkt = _aware(p.ket_thuc) if p.ket_thuc is not None else None
        if pbd <= kt and (pkt is None or pkt >= bd):
            ra.append(p)
    return ra


def _ca_cua(cas, dt) -> str | None:
    """Tên CA chứa mốc THỰC THI `dt` (UTC thật), hoặc None khi mốc rơi ngoài mọi ca đã khai.

    Dùng lại đúng `_ca_cua_moc` của Theo dõi sản xuất thay vì viết bản so giờ thứ hai: luật ca qua
    nửa đêm (Ruling C120) chỉ nên có MỘT chỗ, hai bản chép nhau là sớm muộn lệch nhau. "Ngoài ca"
    là một câu trả lời thật và tổ trưởng cần thấy đúng nó — đừng đoán ca gần nhất.

    Phút ca (`start_minute`) là phút-trong-ngày theo GIỜ TƯỜNG, nên phải đưa mốc về giờ xưởng
    trước khi so — trả UTC thật vào đây là mẻ 20:00 rơi vào Ca 1 (13:00)."""
    if dt is None:
        return None
    from ..lenh_sx.bang_theo_doi import _ca_cua_moc

    kq = _ca_cua_moc(list(cas), thuc_te_hien_thi(dt))
    return kq[0].name if kq else None


def _bg_dict(b, doi_tac_id, doi_tac_map, me_map, dc_map, ten) -> dict:
    """Một dòng bàn giao — hai bên thấy như nhau ai đề xuất, ai xác nhận, lúc nào và từng lần điều
    chỉnh; tên đọc từ tài khoản đã thao tác (`ten` = `{user_id: tên}` gom sẵn một lần)."""
    return {
        "id": b.id,
        "doi_tac_cong_viec_id": doi_tac_id,
        "doi_tac_ten": doi_tac_map.get(doi_tac_id or 0, ""),
        "cung_to": b.cung_to,
        "so_luong": float(b.so_luong),
        "don_vi": b.don_vi,
        "trang_thai": b.trang_thai,
        "khong_nhat_quan": b.khong_nhat_quan,
        "version": b.version,
        "batch_ids": me_map.get(b.id, []),
        "nguoi_de_xuat": ten.get(b.de_xuat_by_id),
        "de_xuat_luc": thuc_te_hien_thi(b.de_xuat_luc),
        "nguoi_xac_nhan": ten.get(b.xac_nhan_by_id),
        "xac_nhan_luc": thuc_te_hien_thi(b.xac_nhan_luc),
        "dieu_chinh": [
            {
                "so_luong_truoc": float(dc.so_luong_truoc),
                "so_luong_sau": float(dc.so_luong_sau),
                "mo_ta": dc.mo_ta,
                "khong_nhat_quan": dc.khong_nhat_quan,
                "nguoi": ten.get(dc.created_by),
                "luc": thuc_te_hien_thi(dc.created_at),
            }
            for dc in dc_map.get(b.id, [])
        ],
    }


def _vat_tu_cap(db: Session, sl, kh_svc, cv, cac_dn, du_lieu_cu: bool) -> dict:
    """Khối vật tư cấp của drawer công đoạn (spec-de-nghi-cap-vat-tu-cong-doan §6).

    Ba con số của mỗi mặt hàng cộng dồn qua MỌI lần đề nghị — lần bổ sung là CỘNG THÊM, không ghi
    đè lần trước. `sl_thuc_xuat` lấy từ dòng phiếu `posted` HIỆN TẠI (ưu tiên `sl_goc`), tức là số
    SAU điều chỉnh: đọc `sl_da_ung` cũng ra số đó, nhưng đọc thẳng chứng từ thì không phụ thuộc
    thứ tự các bước cập nhật.

    Ruling task-7 25 (brief gốc tự mâu thuẫn — dặn "không truy vấn trong vòng lặp" rồi chính nó
    viết N+1): hai hàm repo GỘP (`yeu_cau_tom_tat`, `ten_hang_nhieu`) gọi ĐÚNG MỘT LẦN trước hai
    vòng lặp bên dưới; thân vòng lặp chỉ tra dict, không chạm DB lần nào nữa.
    """
    ke_hoach = kh_svc.nhu_cau_cua_cong_viec(cv)
    req_ids = [d.stock_request_id for d in cac_dn if d.stock_request_id]
    thuc_xuat = sl.thuc_xuat_theo_hang(req_ids)
    tom_tat = sl.yeu_cau_tom_tat(req_ids)

    tat_ca_khoa = {(k["hang_loai"], k["hang_id"]) for k in ke_hoach} | {
        (d.hang_loai, d.hang_id) for dn in cac_dn for d in dn.dongs
    }
    ten_map = sl.ten_hang_nhieu(tat_ca_khoa)

    gom: dict[tuple, dict] = {}
    for k in ke_hoach:
        gom[(k["hang_loai"], k["hang_id"])] = {
            "hang_loai": k["hang_loai"], "hang_id": k["hang_id"], "ten": k["ten"],
            "dvt": k["dvt"], "dvt_goc": k["dvt_goc"],
            "sl_ke_hoach": k["sl"], "sl_ke_hoach_goc": k["sl_goc"],
            "sl_yeu_cau": 0.0, "sl_yeu_cau_goc": 0.0,
            "sl_thuc_xuat": 0.0, "cac_ly_do": [], "_cac_dvt": {k["dvt"]},
        }
    # Ruling task-7 47: `doi_chieu[].sl_yeu_cau` cộng dồn qua MỌI lần (đúng cho khối đối chiếu),
    # nhưng form "Sửa đề nghị" cần đúng dòng CỦA RIÊNG lần đang sửa — `sua()` THAY THẾ toàn bộ dòng
    # của một lần, điền số cộng dồn vào sẽ âm thầm thổi phồng. Gom `dongs_theo_lan` NGAY trong vòng
    # lặp này (không truy vấn thêm) để `cac_de_nghi` bên dưới đính đúng dòng riêng từng lần.
    dongs_theo_lan: dict[int, list[dict]] = {}
    for dn in cac_dn:
        dongs_theo_lan[dn.id] = []
        for d in dn.dongs:
            key = (d.hang_loai, d.hang_id)
            row = gom.setdefault(key, {
                "hang_loai": d.hang_loai, "hang_id": d.hang_id,
                "ten": ten_map.get(key) or f"#{d.hang_id}", "dvt": d.dvt, "dvt_goc": d.dvt_goc,
                "sl_ke_hoach": float(d.sl_ke_hoach), "sl_ke_hoach_goc": float(d.sl_ke_hoach_goc),
                "sl_yeu_cau": 0.0, "sl_yeu_cau_goc": 0.0,
                "sl_thuc_xuat": 0.0, "cac_ly_do": [], "_cac_dvt": set(),
            })
            row["sl_yeu_cau"] += float(d.sl_yeu_cau)
            row["sl_yeu_cau_goc"] += float(d.sl_yeu_cau_goc)
            row["_cac_dvt"].add(d.dvt)
            if d.ly_do_chenh_lech:
                row["cac_ly_do"].append({"lan_so": dn.lan_so, "ly_do": d.ly_do_chenh_lech})
            dongs_theo_lan[dn.id].append({
                "hang_loai": d.hang_loai, "hang_id": d.hang_id,
                "ten": ten_map.get(key) or f"#{d.hang_id}", "dvt": d.dvt, "dvt_goc": d.dvt_goc,
                "sl_ke_hoach": float(d.sl_ke_hoach), "sl_ke_hoach_goc": float(d.sl_ke_hoach_goc),
                "sl_yeu_cau": float(d.sl_yeu_cau), "sl_yeu_cau_goc": float(d.sl_yeu_cau_goc),
                "ly_do_chenh_lech": d.ly_do_chenh_lech,
            })
    for key, sl_ra in thuc_xuat.items():
        if key in gom:
            gom[key]["sl_thuc_xuat"] = sl_ra

    doi_chieu = []
    for row in gom.values():
        # MÁY so bằng thang GỐC (models/san_xuat_vat_tu.py:85-87); `sl_thuc_xuat` (từ
        # `StockVoucherLine.sl_goc`) vốn đã là thang gốc — so nó với `sl_yeu_cau` (thang tổ khai)
        # là so 100 tờ với 12 kg (vòng sửa 1, Important 2+3).
        row["lech_ke_hoach"] = row["sl_yeu_cau_goc"] - row["sl_ke_hoach_goc"]
        row["lech_thuc_te"] = row["sl_thuc_xuat"] - row["sl_yeu_cau_goc"]
        # Khoá gom là (hang_loai, hang_id) — KHÔNG có đơn vị, nên một hàng có thể ôm dòng kế hoạch
        # khai "ram" và dòng tổ khai "tờ". Cộng hai số đó lại rồi in ra là nói dối. Thang gốc là
        # thứ DUY NHẤT chắc chắn chung, nên hàng lẫn đơn vị thì hiện bằng nó (vòng sửa 1, 2c).
        if len(row.pop("_cac_dvt")) > 1:
            row["dvt"] = row["dvt_goc"]
            row["sl_ke_hoach"] = row["sl_ke_hoach_goc"]
            row["sl_yeu_cau"] = row["sl_yeu_cau_goc"]
        doi_chieu.append(row)

    lan_cuoi = cac_dn[-1] if cac_dn else None
    req_repo = StockRequestRepository(db)
    tt = tom_tat.get(lan_cuoi.stock_request_id, {}).get("trang_thai") if lan_cuoi else None
    # `lan_con_mo` là vị ngữ DÙNG CHUNG với cổng thật của `tao()` (vòng sửa 1, Important 1) — hai
    # bên tính TỪ CÙNG một hàm nên không lệch nhau được nữa: `co_the_tao_bo_sung` giờ là phủ định
    # ĐÚNG BẰNG điều kiện ném của `tao()`, theo cấu trúc chứ không theo trí nhớ.
    con_mo = lan_con_mo(
        lan_cuoi,
        co_voucher=req_repo.co_voucher(lan_cuoi.stock_request_id) if lan_cuoi else False,
        trang_thai_kho=tt,
    )
    return {
        "ke_hoach": ke_hoach,
        "cac_de_nghi": [{
            # `can_luc_hien_thi` gỡ nhãn UTC: Postgres trả AWARE, để nguyên là FE dịch thêm +7h.
            "id": d.id, "lan_so": d.lan_so, "loai": d.loai,
            "can_luc": can_luc_hien_thi(d.can_luc),
            "stock_request_id": d.stock_request_id,
            "stock_request_ma": tom_tat.get(d.stock_request_id, {}).get("ma"),
            "stock_request_trang_thai": tom_tat.get(d.stock_request_id, {}).get("trang_thai"),
            "created_by_id": d.created_by_id, "updated_by_id": d.updated_by_id,
            "created_at": thuc_te_hien_thi(d.created_at),
            "updated_at": thuc_te_hien_thi(d.updated_at),
            "dongs": dongs_theo_lan[d.id],
        } for d in cac_dn],
        "doi_chieu": doi_chieu,
        "de_nghi_co_the_sua_id": lan_cuoi.id if con_mo else None,
        "co_the_tao_bo_sung": not con_mo,
        "du_lieu_cu": du_lieu_cu,
    }


def chi_tiet_cong_viec(
    db: Session, user: User, authz: AuthorizationService, *, cong_viec_id: int
) -> dict:
    """Drawer một công việc: thanh kế hoạch + roster + phiên chạy + khoảng tham gia + sản lượng /
    bàn giao / vật tư (§5.1, §10–§11, §18).

    Cùng phạm vi ĐỌC như `work_items`: công việc phải thuộc một tổ user được thấy, nếu không → chặn.
    """
    repo = SanXuatRepository(db)
    tt = SanXuatThucThiRepository(db)
    cv = tt.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    q, muc = _pham_vi_doc(db, user, cv.department_id)
    la_tho = muc == MUC_CUA_TOI
    if la_tho and not _loc_viec_cua_tho(db, user, [cv]):
        raise PermissionError("Chỉ xem được việc đã giao cho mình.")

    lsx_map = repo.lsx_nhan({cv.lsx_id} if cv.lsx_id else set())
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id} if cv.bai_ghep_id else set())
    may_map = repo.may_nhan({cv.may_id} if cv.may_id else set())
    nhom_map = repo.nhom_nhan({cv.nhom_id} if cv.nhom_id else set())

    roster = tt.phan_cong_hoat_dong(cv.id)
    khoang = tt.cac_khoang(cv.id)
    phien_rows = tt.cac_phien(cv.id)
    # Tên máy cho TỪNG phiên (có thể khác nhau nếu đã đổi máy giữa chừng, §7.2 mở rộng) — tra
    # theo đúng bảng `may_thiet_bi`, không dùng `may_map` (đó là bảng `machines` cũ, xem
    # `_may_thiet_bi_nhan`).
    phien_may_ten = _may_thiet_bi_nhan(db, {p.may_id for p in phien_rows if p.may_id})
    lan_dung = _lan_dung_may(phien_rows, cv)

    # --- Hỗ trợ chéo (§9) — vết "người tổ nào sang giúp tổ nào", KHÔNG chia gì
    # --------------
    pb = SanXuatHoTroRepository(db)
    ho_tro_rows = pb.ho_tro_cua_cong_viec(cv.id)

    emp_ids = (
        {pc.employee_id for pc in roster}
        | {k.employee_id for k in khoang}
        | {h.employee_id for h in ho_tro_rows}
    )
    ten_map = repo.nhan_vien_nhan(emp_ids) if emp_ids else {}
    # Ảnh đại diện cho roster + khoảng tham gia — đọc sống từ tài khoản, người đổi ảnh là drawer mở
    # lần sau thấy ngay. Không có = FE vẽ chữ cái đầu.
    anh_map = repo.anh_dai_dien({pc.employee_id for pc in roster} | {k.employee_id for k in khoang})
    to_ids = {h.to_goc_id for h in ho_tro_rows if h.to_goc_id} | {
        h.to_thuc_hien_id for h in ho_tro_rows if h.to_thuc_hien_id
    }
    to_ten = repo.to_ten_nhan(to_ids) if to_ids else {}

    def _emp_ten(eid: int) -> str:
        return ten_map.get(eid, ("", None))[0]

    # --- Sản lượng · bàn giao · vật tư (Giai đoạn 3) -----------------------------------------
    sl = SanXuatSanLuongRepository(db)
    batches = sl.cac_batch(cv.id)
    _tong_tot_cv = sl.tong_tot(cv.id)
    # Lượng tổ này THẬT SỰ nhận được (bàn giao đã xác nhận về đây) — mốc chấm rút theo nó, xem
    # `_con_thieu`. None = không ai giao cho (bước đầu chuỗi) ⇒ giữ mốc kế hoạch.
    _thuc_nhan_cv = _thuc_nhan(cv, sl.tong_thuc_nhan_nhieu({cv.id}))
    _muc_tieu_cv, _con_thieu_cv = _con_thieu(cv, _tong_tot_cv, _thuc_nhan_cv)

    # Máy + ca + sự cố + đầu việc của TỪNG mẻ (§5.2) — mọi số đã có sẵn trong DB, chỉ là chưa ai
    # nối ra mặt đọc. Tập ca lấy đúng nguồn dùng chung của xưởng (`ca_lich_xuong`, cùng tập mà Xếp
    # lịch và Theo dõi sản xuất dùng) để mẻ không bị gán một ca mà hai màn kia không biết tới.
    ca_list = AttendanceRepository(db).ca_lich_xuong()

    lot_map = sl.lot_vao_cua_nhieu([b.id for b in batches])
    # VIỆC PHÁT SINH của từng mẻ (mg `0318`) — một truy vấn cho cả tab, xem `phat_sinh_cua_nhieu`.
    # KHÔNG cộng vào `tong_tot`/`muc_tieu`/`con_thieu`: nó là con số đứng CẠNH sản lượng.
    ps_map = sl.phat_sinh_cua_nhieu([b.id for b in batches])
    # Băng "Danh mục đã đổi" của từng mẻ đọc chung một bản nạp (việc khoán của tổ + phát sinh sống).
    nap_dmd = viec_khoan.nap_doi_chieu(
        db, department_id=cv.department_id,
        ps_rows=[r for rows in ps_map.values() for r in rows],
    ) if any(b.piece_rate_id for b in batches) else ({}, {})
    # Tên đơn vị cho ảnh chụp của mẻ + của việc phát sinh — cột giữ MÃ (`kem`), tổ đọc TÊN.
    dv_me_ten = DonViDoRepository(db).ten_theo_ma()
    # AI CÓ MẶT trong từng mẻ — CÙNG một hàm với tab Sản lượng và màn thợ (khoảng tham gia + hỗ trợ
    # chéo đã xác nhận), để drawer và hai màn kia không bao giờ lệch nhau. Không số phút (chốt ý 13).
    # Người không thuộc tổ CHỦ mẻ (tổ của bước) kèm nhãn tổ gốc — tổ trưởng biết ngay ai sang giúp.
    theo_me = nguoi_theo_me(db, [b.id for b in batches])
    to_goc_ten = repo.to_ten_nhan({
        n["department_id"] for ds in theo_me.values() for n in ds
        if n["department_id"] and n["department_id"] != cv.department_id
    })

    def _nguoi_me(batch_id: int) -> list[dict]:
        return [
            {
                "employee_id": n["employee_id"],
                "ho_ten": n["ho_ten"],
                "to_ten": (to_goc_ten.get(n["department_id"])
                           if n["department_id"] and n["department_id"] != cv.department_id
                           else None),
            }
            for n in theo_me.get(batch_id, [])
        ]
    bg_di = sl.ban_giao_tu_nguon(cv.id)
    bg_den = sl.ban_giao_toi_dich(cv.id)
    doi_tac_ids = {b.dich_cong_viec_id for b in bg_di if b.dich_cong_viec_id} | {
        b.nguon_cong_viec_id for b in bg_den
    }
    # Vòng sửa 1, Minor 4: gộp một truy vấn cho cả tập đối tác thay vì `db.get` từng cái (N+1 về
    # HÌNH DẠNG — `doi_tac_ids` thường 0-5 phần tử, không phải chỗ nghẽn, nhưng rẻ để sửa đúng
    # khuôn `*_nhieu` Task 7 vừa dựng).
    doi_tac_map = {i: cv.ten_cong_doan for i, cv in sl.cong_viec_nhieu(doi_tac_ids).items()}
    vt_repo = SanXuatVatTuRepository(db)
    cac_dn = vt_repo.cac_de_nghi(cv.id)
    req_ids = [d.stock_request_id for d in cac_dn if d.stock_request_id]
    vouchers, du_lieu_cu = sl.voucher_xuat_cua_cong_viec(cv, req_ids)
    nhan_map = sl.nhan_theo_voucher_ids([v.id for v in vouchers])

    kh_svc = _kh_service(db, _hang_service(db))
    vat_tu_cap = _vat_tu_cap(db, sl, kh_svc, cv, cac_dn, du_lieu_cu)

    # ĐÍCH bàn giao = chặng sau theo routing lệnh (§11.2) — FE bày cố định, chỉ cho chọn khi bước
    # sau tách lần chạy/rẽ nhánh. Rỗng = bước cuối lệnh — không bàn giao, thành phẩm qua KCS.
    chang_sau = sl.cong_viec_chang_sau(cv)
    chang_sau_to_ten = repo.to_ten_nhan({c.department_id for c in chang_sau if c.department_id})
    # Mẻ nào đã đi theo lần giao nào — form bàn giao chỉ tick sẵn mẻ chưa giao.
    me_map = sl.me_cua_ban_giao_nhieu([b.id for b in bg_di] + [b.id for b in bg_den])
    me_da_giao = sl.batch_da_giao_ids(cv.id)
    dc_map = sl.dieu_chinh_nhieu([b.id for b in bg_di] + [b.id for b in bg_den])
    ten_bg = SanXuatKcsRepository(db).ten_nguoi(
        {u for b in (*bg_di, *bg_den) for u in (b.de_xuat_by_id, b.xac_nhan_by_id)}
        | {dc.created_by for ds in dc_map.values() for dc in ds}
    )

    return {
        # Vòng sửa 1, mục 2: truyền đúng bộ số đã tính ở trên — nếu không, "cong_viec.con_thieu"
        # trả null trong khi "san_luong.con_thieu" ngay bên dưới có số, hai giá trị khác nhau cho
        # CÙNG một khái niệm trong CÙNG một response là nói dối.
        "cong_viec": _item_dict(
            cv, lsx_map, bg_map, may_map, nhom_map,
            khach_map=repo.khach_nhan({cv.lsx_id} if cv.lsx_id else set(),
                                      {cv.bai_ghep_id} if cv.bai_ghep_id else set()),
            so_map={cv.id: {
                "thuc_nhan": _thuc_nhan_cv, "da_lam": _tong_tot_cv,
                "muc_tieu": _muc_tieu_cv, "con_thieu": _con_thieu_cv,
            }},
        ),
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        # Bốn quyền chi tiết của người đang xem trên CHÍNH việc này — drawer bật/tắt nút theo đây.
        "quyen": quyen_tren_viec(db, user.id, cv, q=q),
        # MỨC của từng quyền ở tổ này ("all" | "own"; không có khoá = không được cấp). `quyen` tắt
        # vì hai lý do khác nhau — không được cấp, hoặc chỉ "Của tôi" mà việc chưa giao cho mình —
        # và drawer phải nói đúng lý do nào, không thì người đã bật quyền đọc thấy "cần quyền".
        "quyen_muc": {v: m for v in VIEC_CHI_TIET if (m := q.muc(v, cv.department_id))},
        "phan_cong": [
            {
                "id": pc.id,
                "employee_id": pc.employee_id,
                "ho_ten": ten_map.get(pc.employee_id, ("", None))[0],
                "la_luong_khoan": pc.la_luong_khoan,
                "co_tai_khoan": ten_map.get(pc.employee_id, ("", None))[1] is not None,
                "avatar_url": anh_map.get(pc.employee_id),
                "trang_thai": pc.trang_thai,
            }
            for pc in roster
        ],
        "phien_chay": [
            {
                "id": p.id,
                "so_thu_tu": p.so_thu_tu,
                "may_id": p.may_id,
                "may_ten": phien_may_ten.get(p.may_id or 0),
                "bat_dau": thuc_te_hien_thi(p.bat_dau),
                "ket_thuc": thuc_te_hien_thi(p.ket_thuc),
                "loai_dong": p.loai_dong,
                "ly_do_bat_dau_tre": p.ly_do_bat_dau_tre,
                "ly_do": p.ly_do,
            }
            for p in phien_rows
        ],
        "khoang_tham_gia": [
            {
                "id": k.id,
                "phien_chay_id": k.phien_chay_id,
                "employee_id": k.employee_id,
                "ho_ten": ten_map.get(k.employee_id, ("", None))[0],
                "avatar_url": anh_map.get(k.employee_id),
                "bat_dau": thuc_te_hien_thi(k.bat_dau),
                "ket_thuc": thuc_te_hien_thi(k.ket_thuc),
            }
            for k in khoang
        ],
        "san_luong": {
            "tong_tot": _tong_tot_cv,
            "da_giao": sl.tong_da_giao(cv.id),
            # Mục tiêu bước + thực nhận + còn thiếu (§2.3) — dẫn xuất, chỉ để BÀY, không đổi
            # cổng đóng nhóm.
            "muc_tieu": _muc_tieu_cv,
            "thuc_nhan": _thuc_nhan_cv,
            "con_thieu": _con_thieu_cv,
            "don_vi": cv.don_vi_ra,
            "batches": [
                {
                    "id": b.id,
                    # Cửa sổ mẻ là mốc THỰC THI (UTC thật từ mg 0298 — trước đó tổ gõ giờ tường
                    # rồi bị dán nhãn UTC, lệch đúng 7 tiếng so với phiên chạy/chấm công).
                    "bat_dau": thuc_te_hien_thi(b.bat_dau),
                    "ket_thuc": thuc_te_hien_thi(b.ket_thuc),
                    "tong": float(b.tong),
                    "tot": float(b.tot),
                    "hong": float(b.hong),
                    "don_vi": b.don_vi,
                    "mo_ta_loi": b.mo_ta_loi,
                    "ghi_chu": b.ghi_chu,
                    "version": b.version,
                    "may_ten": next(
                        (phien_may_ten.get(p.may_id or 0) for p in _phien_giao_me(phien_rows, b)
                         if p.may_id), None),
                    "ca_ten": _ca_cua(ca_list, b.bat_dau),
                    "su_co": [
                        {"bat_dau": thuc_te_hien_thi(tu), "ket_thuc": thuc_te_hien_thi(den),
                         "ly_do": ly_do}
                        for tu, den, ly_do in _dung_giao_me(lan_dung, b)
                    ],
                    "nguoi_tham_gia": (nguoi_me := _nguoi_me(b.id)),
                    "so_nguoi": len(nguoi_me),
                    "da_ban_giao": b.id in me_da_giao,
                    # Việc khoán của mẻ = ẢNH CHỤP lúc ghi, KHÔNG tra danh mục sống: mẻ là chứng
                    # từ, phải đọc lại đúng bối cảnh của nó. Danh mục đổi thì băng dưới nói, và
                    # chỉ đổi khi NGƯỜI bấm (§7.2b).
                    "viec_khoan_id": b.piece_rate_id,
                    "viec_khoan_ten": b.ten_khoan_snapshot,
                    "viec_khoan_don_vi": b.don_vi_khoan_snapshot,
                    "viec_khoan_don_vi_ten": nhan_don_vi(dv_me_ten, b.don_vi_khoan_snapshot)
                    if b.don_vi_khoan_snapshot else None,
                    "viec_khoan_don_gia": (float(b.don_gia_khoan_snapshot)
                                           if b.don_gia_khoan_snapshot is not None else None),
                    "phat_sinh": [
                        {
                            "id": r.id,
                            "phat_sinh_id": r.phat_sinh_id,
                            "so_luong": float(r.so_luong),
                            "ten": r.ten_snapshot,
                            "don_vi": r.don_vi_snapshot,
                            "don_vi_ten": nhan_don_vi(dv_me_ten, r.don_vi_snapshot)
                            if r.don_vi_snapshot else None,
                            "don_gia": (float(r.don_gia_snapshot)
                                        if r.don_gia_snapshot is not None else None),
                        }
                        for r in ps_map.get(b.id, [])
                    ],
                    "danh_muc_doi": viec_khoan.danh_muc_doi(
                        db, b, ps_map.get(b.id, []), department_id=cv.department_id,
                        nap=nap_dmd),
                    "lot_vao": [
                        {
                            "id": lot.id,
                            "nguon_batch_id": lot.nguon_batch_id,
                            "so_luong": float(lot.so_luong),
                            "don_vi": lot.don_vi,
                        }
                        for lot in lot_map.get(b.id, [])
                    ],
                }
                for b in batches
            ],
        },
        "ban_giao_di": [
            _bg_dict(b, b.dich_cong_viec_id, doi_tac_map, me_map, dc_map, ten_bg) for b in bg_di
        ],
        "ban_giao_den": [
            _bg_dict(b, b.nguon_cong_viec_id, doi_tac_map, me_map, dc_map, ten_bg) for b in bg_den
        ],
        # Đầu vào theo routing (19/09/2026, `dau_vao`): công đoạn trước + trần ghi mẻ + còn thiếu
        # nguồn nào thì chưa bắt đầu được — cùng hàm máy chủ dùng để CHẶN, drawer chỉ bày lại.
        "cong_doan_truoc": dau_vao.cong_doan_truoc(db, sl, cv),
        "tran_ghi": (
            {**t, "da_ghi": _tong_tot_cv, "con_ghi_duoc": max(0.0, t["toi_da"] - _tong_tot_cv)}
            if (t := dau_vao.tran_ghi(db, cv, repo=sl)) else None
        ),
        "thieu_dau_vao": dau_vao.thieu_dau_vao(sl, cv),
        "ban_giao_chang_sau": [
            {
                "cong_viec_id": c.id,
                "ten_cong_doan": c.ten_cong_doan,
                "to_id": c.department_id,
                "to_ten": chang_sau_to_ten.get(c.department_id) if c.department_id else None,
                "du_kien_bat_dau": lich_hien_thi(c.du_kien_bat_dau),
                "phan_doan_so": c.phan_doan_so,
                "phan_doan_tong": c.phan_doan_tong,
                "loai_buoc": c.loai_buoc,
                "nha_cung_cap": c.nha_cung_cap,
                "trang_thai": c.trang_thai,
            }
            for c in chang_sau
        ],
        "vat_tu": [
            {
                "voucher_id": v.id,
                "ma": v.ma,
                "da_nhan": v.id in nhan_map,
                "xac_nhan_luc": (
                    thuc_te_hien_thi(nhan_map[v.id].xac_nhan_luc) if v.id in nhan_map else None
                ),
            }
            for v in vouchers
        ],
        "vat_tu_cap": vat_tu_cap,
        "ho_tro": [
            {
                "id": h.id,
                "employee_id": h.employee_id,
                "ho_ten": _emp_ten(h.employee_id),
                "to_goc_id": h.to_goc_id,
                "to_goc_ten": to_ten.get(h.to_goc_id) if h.to_goc_id else None,
                "to_thuc_hien_id": h.to_thuc_hien_id,
                "to_thuc_hien_ten": to_ten.get(h.to_thuc_hien_id) if h.to_thuc_hien_id else None,
                "ngay_lam_viec": h.ngay_lam_viec,
                "trang_thai": h.trang_thai,
                "mo_ta": h.mo_ta,
                "da_xac_nhan_goc": h.xac_nhan_goc_luc is not None,
                "da_xac_nhan_thuc_hien": h.xac_nhan_thuc_hien_luc is not None,
                # Cùng luật `ho_tro._ben_cua`: đứng được cho bên nào thì xác nhận bên đó (khi bên
                # đó còn trống), huỷ được khi đứng được cho một trong hai bên.
                "co_the_xac_nhan": h.trang_thai == HT_CHO_HAI_BEN and bool(
                    _ben_cho(h, q.tron[VIEC_XAC_NHAN])),
                "co_the_huy": h.trang_thai != HT_HUY and (
                    q.co_tron(VIEC_XAC_NHAN, h.to_goc_id)
                    or q.co_tron(VIEC_XAC_NHAN, h.to_thuc_hien_id)),
                "version": h.version,
            }
            for h in ho_tro_rows
        ],
    }
