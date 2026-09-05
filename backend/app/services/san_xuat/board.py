"""Bàn THỰC HIỆN tại tổ — mặt đọc (§11, §18 `/api/san-xuat/teams` + `/work-items`).

Đây là nền của Giai đoạn 2: mỗi node LÁ trong Khối Sản xuất là một tổ; tổ trưởng mở bàn của tổ
mình thấy các công việc ĐÃ PHÁT HÀNH (đọc từ snapshot gói, không đọc-sống routing). Lát này CHỈ
ĐỌC — phân công / phiên chạy / sản lượng là các lát sau (thêm bảng riêng).

Phạm vi tổ theo QUYỀN người đăng nhập, tái dùng đúng cơ chế scope của module `san_xuat` (giống
`routers/lsx.py`): `all` thấy mọi tổ; `department` thấy cả cây con phòng mình; `own` chỉ tổ mình.
Không có "quyền ghi đè cho quản lý cấp cao" (§10) — cấp trên phạm vi rộng vẫn chỉ để xem.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.may_thiet_bi import MayThietBi
from ...models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ...models.san_xuat_phan_bo import PB_DA_CHOT
from ...models.user import User
from ...repositories.org_scope import dept_subtree_ids
from ...repositories.rbac_repo import DepartmentRepository
from ...repositories.san_xuat_phan_bo_repo import SanXuatPhanBoRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ...repositories.san_xuat_vat_tu_repo import SanXuatVatTuRepository
from ...repositories.stock_request_repo import StockRequestRepository
from ...services.rbac_service import AuthorizationService
from ..gio_xuong import lich_hien_thi, thuc_te_hien_thi
from .phan_bo import _tinh_batch
from .thuc_thi import _aware
from .vat_tu_de_nghi import _hang_service, _kh_service, can_luc_hien_thi, lan_con_mo

MODULE = "san_xuat"


def _to_thay_duoc(
    db: Session, user: User, authz: AuthorizationService
) -> tuple[list, set[int]]:
    """(danh sách tổ = node lá Khối SX mà user được thấy, tập id của chúng) theo scope `san_xuat`.

    `to_san_xuat()` là ĐỊNH NGHĨA CHUNG của "tổ" (node lá khối SX). Lọc thêm theo scope: cấp
    xưởng (`all`) thấy hết; tổ trưởng (`department`/`own`) chỉ cây con phòng mình — CỘNG THÊM mọi
    tổ mà user đứng `head_user_id` (kiêm nhiệm tổ trưởng một tổ ngoài phòng mình): nếu không, tổ
    trưởng kiêm nhiệm được `_gate` (thuc_thi.py) cho GHI việc của tổ đó nhưng sidebar lại không có
    lối vào để XEM — user bị khoá ngoài bàn tổ chính mình đứng đầu.
    """
    tos = DepartmentRepository(db).to_san_xuat()
    scope = authz.scope_for(user, MODULE) or SCOPE_ALL
    if scope == SCOPE_ALL:
        pass
    elif scope == SCOPE_DEPARTMENT:
        cho_phep = dept_subtree_ids(db, user.department_id) or set()
        tos = [d for d in tos if d.id in cho_phep or d.head_user_id == user.id]
    else:  # own
        tos = [d for d in tos if d.id == user.department_id or d.head_user_id == user.id]
    return tos, {d.id for d in tos}


def _la_tho(user: User, authz: AuthorizationService, team) -> bool:
    """Người đang mở bàn là THỢ của tổ này (không phải tổ trưởng, không có phạm vi rộng hơn)?

    Thợ chỉ thấy việc CHÍNH MÌNH đang được giao (§7.1) — bàn tổ không phải bảng điều hành cả tổ.
    Tổ trưởng (kể cả kiêm nhiệm tổ ngoài phòng mình) và cấp trên phạm vi `department`/`all` vẫn
    thấy trọn bàn."""
    if (authz.scope_for(user, MODULE) or SCOPE_ALL) != SCOPE_OWN:
        return False
    return team is None or team.head_user_id != user.id


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
    """Danh sách tổ sản xuất hiệu lực + badge sản xuất + badge/cổng KCS (§18 `/teams`, §2.1 navbar).

    `la_kcs` ở đây là `Department.is_kcs` ("tổ KCS chuyên trách") — KHÁC `la_kcs` của công việc
    (`SanXuatCongViec.la_kcs`, cấp TỪNG bước, do tổ bất kỳ đảm nhiệm — KCS kiêm nhiệm). Field mới
    Task 4 (`so_viec_kcs_cho`, `co_viec_kcs`) đọc theo cờ công việc, KHÔNG theo `is_kcs`."""
    repo = SanXuatRepository(db)
    tos, ids = _to_thay_duoc(db, user, authz)
    # Tổ nào user vào với tư cách THỢ thì badge phải đếm theo việc được giao, không đếm cả tổ —
    # nếu không navbar báo 12 mà mở bàn ra chỉ có 2 dòng.
    to_tho = {d.id for d in tos if _la_tho(user, authz, d)}
    to_thuong = ids - to_tho
    badge = repo.dem_cho_lam_theo_to(to_thuong)
    kcs_badge = repo.dem_kcs_cho_kiem_theo_to(to_thuong)
    co_kcs = repo.to_co_viec_kcs(to_thuong)
    if to_tho:
        nv = SanXuatThucThiRepository(db).nhan_vien_theo_user(user.id)
        nv_id = nv.id if nv is not None else None
        if nv_id is not None:
            badge.update(repo.dem_cho_lam_theo_to(to_tho, employee_id=nv_id))
            kcs_badge.update(repo.dem_kcs_cho_kiem_theo_to(to_tho, employee_id=nv_id))
            co_kcs |= repo.to_co_viec_kcs(to_tho, employee_id=nv_id)
    return [
        {
            "id": d.id,
            "ten": d.name,
            "ma": d.code,
            "la_kcs": bool(getattr(d, "is_kcs", False)),
            "so_viec_cho": badge.get(d.id, 0),
            "so_viec_kcs_cho": kcs_badge.get(d.id, 0),
            "co_viec_kcs": d.id in co_kcs,
        }
        for d in tos
    ]


def _num(x) -> float | None:
    return None if x is None else float(x)


def _may_thiet_bi_nhan(db: Session, may_ids: set[int]) -> dict[int, str]:
    """{may_id: tên máy} tra ĐÚNG danh mục `may_thiet_bi` — KHÁC bảng `machines` cũ mà
    `SanXuatRepository.may_nhan` dùng (đó là danh mục máy của Tính giá). `san_xuat_cong_viec.may_id`
    / `san_xuat_phien_chay.may_id` đều neo theo `MayThietBi.id` (xem `xep_lich_2/service.py`,
    `snapshot.py`), nên đọc TÊN máy cho phiên chạy phải tra đúng bảng này chứ không phải bảng cũ."""
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


def _item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map=None, so_map=None) -> dict:
    """Một dòng công việc trên timeline — nhãn nguồn/nhóm/máy đã resolve theo lô (§18)."""
    if cv.bai_ghep_id and cv.bai_ghep_id in bg_map:
        nguon_ma, nguon_ten = bg_map[cv.bai_ghep_id]
        nguon_loai = "bai_ghep"
    elif cv.lsx_id and cv.lsx_id in lsx_map:
        nguon_ma, nguon_ten = lsx_map[cv.lsx_id]
        nguon_loai = "lsx"
    else:
        nguon_ma, nguon_ten, nguon_loai = "", "", ""
    return {
        "id": cv.id,
        "goi_id": cv.goi_id,
        "phien_ban_so": cv.phien_ban_so,
        "nguon_loai": nguon_loai,
        "nguon_ma": nguon_ma,
        "nguon_ten": nguon_ten,
        "nhom_id": cv.nhom_id,
        "nhom": nhom_map.get(cv.nhom_id or 0, ""),
        "ten_cong_doan": cv.ten_cong_doan,
        "nhom_cong_doan": cv.nhom_cong_doan,
        "loai_buoc": cv.loai_buoc,
        "la_kcs": cv.la_kcs,
        "la_kcs_cuoi": cv.la_kcs_cuoi,
        "may": may_map.get(cv.may_id or 0, ""),
        "may_id": cv.may_id,      # máy HIỆN TẠI — FE cần để dựng ô chọn "Đổi máy" (§7.2 mở rộng)
        # Hai thang giờ khác nhau gặp nhau ở ĐÂY (xem `services/gio_xuong.py`): mốc kế hoạch là
        # giờ tường dán nhãn UTC, mốc phiên chạy là UTC THẬT. Cùng quy về wall-clock giờ xưởng
        # rồi mới trả — không thì cùng một thanh Gantt đo bằng hai cây thước lệch nhau 7 tiếng.
        "du_kien_bat_dau": lich_hien_thi(cv.du_kien_bat_dau),
        "du_kien_ket_thuc": lich_hien_thi(cv.du_kien_ket_thuc),
        # Số người dự kiến chốt lúc phát hành (§7.1) — FE so với roster để đòi lý do khi lệch.
        "du_kien_so_nguoi": (
            cv.dinh_muc_json.get("so_nhan_cong_tieu_chuan")
            if isinstance(cv.dinh_muc_json, dict) else None
        ),
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
    }


def work_items(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int,
    mode: str = "production",
) -> dict:
    """Công việc đã phát hành của MỘT tổ (timeline), lọc theo `mode` (Task 4, §18 mục 6):
    - "production" (mặc định) → chỉ việc SẢN XUẤT (`la_kcs=false`).
    - "kcs" → chỉ việc KCS (`la_kcs=true`).
    Chặn nếu tổ ngoài phạm vi quyền của user. Router ép kiểu `mode` bằng `Literal` trước khi gọi
    xuống đây — service nhận `str` thô là đủ."""
    repo = SanXuatRepository(db)
    _tos, ids = _to_thay_duoc(db, user, authz)
    if team_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")

    rows = repo.cong_viec_cua_to({team_id}, la_kcs=(mode == "kcs"))
    if _la_tho(user, authz, next((d for d in _tos if d.id == team_id), None)):
        rows = _loc_viec_cua_tho(db, user, rows)
    lsx_map = repo.lsx_nhan({cv.lsx_id for cv in rows if cv.lsx_id})
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id for cv in rows if cv.bai_ghep_id})
    may_map = repo.may_nhan({cv.may_id for cv in rows if cv.may_id})
    nhom_map = repo.nhom_nhan({cv.nhom_id for cv in rows if cv.nhom_id})
    # Lớp thực-tế: phiên chạy của cả gói trong MỘT truy vấn (§5.1), tránh N+1 theo từng việc.
    phien_map = SanXuatThucThiRepository(db).phien_theo_cong_viec({cv.id for cv in rows})
    # Còn thiếu (§2.3): nạp tổng TỐT gộp cho cả bàn tổ rồi tính tại chỗ — không gọi `tong_tot`
    # (một truy vấn/việc) theo từng dòng, bàn tổ có thể có hàng chục công việc.
    sl_repo = SanXuatSanLuongRepository(db)
    cv_ids = {cv.id for cv in rows}
    tot_map = sl_repo.tong_tot_nhieu(cv_ids)
    nhan_map = sl_repo.tong_thuc_nhan_nhieu(cv_ids)
    so_map = _so_lieu_map(rows, tot_map, nhan_map)
    items = [
        _item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map, so_map)
        for cv in rows
    ]
    return {"team_id": team_id, "cong_viec": items}


def nhan_vien_chon(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int
) -> dict:
    """Nhân viên chọn được để GIAO vào việc của một tổ (ô "Giao người" ở drawer, §7.1).

    Cùng phạm vi ĐỌC như `work_items` (tổ phải trong quyền user, nếu không → chặn). Endpoint riêng
    của module `san_xuat` để tổ trưởng KHÔNG cần quyền `nhan_su` mới đổ được danh chọn. `la_luong_khoan`
    suy từ `has_piece_work` của chính tổ (mọi người trong tổ cùng chế độ) — FE lọc/cảnh báo cho bước
    nội bộ (`loai_buoc=="to"` chỉ nhận thợ khoán). `co_tai_khoan` để biết ai nhận được thông báo đẩy.
    """
    _tos, ids = _to_thay_duoc(db, user, authz)
    if team_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")
    dept = db.get(Department, team_id)
    la_khoan = bool(dept and dept.has_piece_work)
    ds = SanXuatThucThiRepository(db).nhan_vien_cua_to(team_id)
    return {
        "team_id": team_id,
        "nhan_vien": [
            {
                "id": e.id,
                "code": e.code,
                "full_name": e.full_name,
                "la_luong_khoan": la_khoan,
                "co_tai_khoan": e.user_id is not None,
            }
            for e in ds
        ],
    }


def ho_tro_ung_vien(
    db: Session, user: User, authz: AuthorizationService, *, team_id: int
) -> dict:
    """Ứng viên đề xuất HỖ TRỢ CHÉO cho một tổ (§9): thợ ở các tổ SX KHÁC. Cùng phạm vi ĐỌC như
    `work_items` (tổ phải trong quyền user). Mỗi ứng viên kèm nhãn tổ gốc để tổ trưởng biết đang
    mời ai từ đâu."""
    tos, ids = _to_thay_duoc(db, user, authz)
    if team_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")
    # Ứng viên = thợ mọi tổ SX (kể cả tổ user không quản), trừ tổ đang thực hiện.
    moi_to = DepartmentRepository(db).to_san_xuat()
    to_ten = {d.id: d.name for d in moi_to}
    ds = SanXuatThucThiRepository(db).nhan_vien_ho_tro_ung_vien(
        {d.id for d in moi_to}, team_id
    )
    return {
        "team_id": team_id,
        "nhan_vien": [
            {
                "id": e.id,
                "code": e.code,
                "full_name": e.full_name,
                "to_id": e.department_id,
                "to_ten": to_ten.get(e.department_id) if e.department_id else None,
            }
            for e in ds
        ],
    }


def _nguoi_trong_batch(khoang, ten_map, b) -> list[dict]:
    """§12.1: người có khoảng tham gia GIAO với cửa sổ batch — nền chia phần lương (tính LÚC ĐỌC,
    không lưu thành viên batch). Ép `_aware` vì SQLite trả naive (bẫy naive/aware)."""
    bd, kt = _aware(b.bat_dau), _aware(b.ket_thuc)
    seen: dict[int, str] = {}
    for k in khoang:
        kbd = _aware(k.bat_dau)
        kkt = _aware(k.ket_thuc) if k.ket_thuc is not None else None
        if kbd <= kt and (kkt is None or kkt >= bd) and k.employee_id not in seen:
            seen[k.employee_id] = ten_map.get(k.employee_id, ("", None))[0]
    return [{"employee_id": eid, "ho_ten": ten} for eid, ten in seen.items()]


def _bg_dict(b, doi_tac_id, doi_tac_map) -> dict:
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
    _tos, ids = _to_thay_duoc(db, user, authz)
    if cv.department_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")
    if _la_tho(user, authz, next((d for d in _tos if d.id == cv.department_id), None))             and not _loc_viec_cua_tho(db, user, [cv]):
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

    # --- Hỗ trợ chéo · phân bổ (Giai đoạn 4, §9 · §12) --------------------------------------
    pb = SanXuatPhanBoRepository(db)
    ho_tro_rows = pb.ho_tro_cua_cong_viec(cv.id)
    pb_headers = pb.phan_bo_cua_cong_viec(cv.id)
    dong_map = {h.id: pb.cac_dong(h.id) for h in pb_headers}
    bu_tru_map = {h.id: pb.bu_tru_cua_batch(h.batch_id) for h in pb_headers}
    loai_tru_map = {h.id: pb.loai_tru_cua_batch(h.batch_id) for h in pb_headers}

    emp_ids = (
        {pc.employee_id for pc in roster}
        | {k.employee_id for k in khoang}
        | {h.employee_id for h in ho_tro_rows}
        | {d.employee_id for dl in dong_map.values() for d in dl}
        | {b.employee_id for bl in bu_tru_map.values() for b in bl}
        | {lt.employee_id for ll in loai_tru_map.values() for lt in ll}
    )
    ten_map = repo.nhan_vien_nhan(emp_ids) if emp_ids else {}
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
    # Tính LẠI cờ chặn chốt + cảnh báo cho từng phân bổ CHƯA chốt (§7.3/§12): chấm công có thể vừa
    # được bổ sung / loại trừ vừa đổi ⇒ trạng thái can_chot phải phản ánh hiện tại, không đóng băng.
    batch_by_id = {b.id: b for b in batches}
    pb_flags: dict[int, dict] = {}
    for h in pb_headers:
        b = batch_by_id.get(h.batch_id)
        if h.trang_thai == PB_DA_CHOT or b is None:
            pb_flags[h.id] = {"can_chot": True, "canh_bao": [], "thieu_cham_cong": []}
            continue
        kq = _tinh_batch(db, cv, b, pb)
        pb_flags[h.id] = {
            "can_chot": kq.can_chot,
            "canh_bao": kq.canh_bao,
            "thieu_cham_cong": kq.thieu_cham_cong,
        }
    lot_map = sl.lot_vao_cua_nhieu([b.id for b in batches])
    ld_ten = sl.nhan_ly_do({b.nhom_loi_id for b in batches if b.nhom_loi_id})
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

    # Gợi ý ĐÍCH bàn giao = chặng sau của cùng gói/LSX (§11.2); tổ trưởng chọn hoặc "giao ra ngoài".
    goi_y = sl.cong_viec_sau_goi_y(cv)
    goi_y_to_ten = repo.to_ten_nhan({c.department_id for c in goi_y if c.department_id})

    return {
        # Vòng sửa 1, mục 2: truyền đúng bộ số đã tính ở trên — nếu không, "cong_viec.con_thieu"
        # trả null trong khi "san_luong.con_thieu" ngay bên dưới có số, hai giá trị khác nhau cho
        # CÙNG một khái niệm trong CÙNG một response là nói dối.
        "cong_viec": _item_dict(
            cv, lsx_map, bg_map, may_map, nhom_map,
            so_map={cv.id: {
                "thuc_nhan": _thuc_nhan_cv, "da_lam": _tong_tot_cv,
                "muc_tieu": _muc_tieu_cv, "con_thieu": _con_thieu_cv,
            }},
        ),
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "phan_cong": [
            {
                "id": pc.id,
                "employee_id": pc.employee_id,
                "ho_ten": ten_map.get(pc.employee_id, ("", None))[0],
                "la_luong_khoan": pc.la_luong_khoan,
                "co_tai_khoan": ten_map.get(pc.employee_id, ("", None))[1] is not None,
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
                    # Batch do TỔ GÕ ở ô `datetime-local` → `_aware()` gắn nhãn UTC lên giờ
                    # tường: thang LỊCH, không phải mốc máy chủ. Gỡ nhãn là xong.
                    "bat_dau": lich_hien_thi(b.bat_dau),
                    "ket_thuc": lich_hien_thi(b.ket_thuc),
                    "tong": float(b.tong),
                    "tot": float(b.tot),
                    "hong": float(b.hong),
                    "don_vi": b.don_vi,
                    "nhom_loi_id": b.nhom_loi_id,
                    "nhom_loi_ten": ld_ten.get(b.nhom_loi_id) if b.nhom_loi_id else None,
                    "mo_ta_loi": b.mo_ta_loi,
                    "ghi_chu": b.ghi_chu,
                    "version": b.version,
                    "nguoi_tham_gia": _nguoi_trong_batch(khoang, ten_map, b),
                    "lot_vao": [
                        {
                            "id": lot.id,
                            "nguon_loai": lot.nguon_loai,
                            "nguon_batch_id": lot.nguon_batch_id,
                            "nguon_lot_id": lot.nguon_lot_id,
                            "so_luong": float(lot.so_luong),
                            "don_vi": lot.don_vi,
                        }
                        for lot in lot_map.get(b.id, [])
                    ],
                }
                for b in batches
            ],
        },
        "ban_giao_di": [_bg_dict(b, b.dich_cong_viec_id, doi_tac_map) for b in bg_di],
        "ban_giao_den": [_bg_dict(b, b.nguon_cong_viec_id, doi_tac_map) for b in bg_den],
        "ban_giao_goi_y": [
            {
                "cong_viec_id": c.id,
                "ten_cong_doan": c.ten_cong_doan,
                "to_id": c.department_id,
                "to_ten": goi_y_to_ten.get(c.department_id) if c.department_id else None,
                "du_kien_bat_dau": lich_hien_thi(c.du_kien_bat_dau),
            }
            for c in goi_y
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
                "ty_le_phan_tram": float(h.ty_le_phan_tram),
                "trang_thai": h.trang_thai,
                "mo_ta": h.mo_ta,
                "da_xac_nhan_goc": h.xac_nhan_goc_luc is not None,
                "da_xac_nhan_thuc_hien": h.xac_nhan_thuc_hien_luc is not None,
                "version": h.version,
            }
            for h in ho_tro_rows
        ],
        "phan_bo": [
            {
                "phan_bo_id": h.id,
                "batch_id": h.batch_id,
                "trang_thai": h.trang_thai,
                "version": h.version,
                "ngay": h.ngay,
                "ky_nam": h.ky_nam,
                "ky_thang": h.ky_thang,
                "q_tra_luong": float(h.q_tra_luong or 0),
                "don_vi_tra_luong": h.don_vi_tra_luong,
                "don_gia": float(h.don_gia or 0),
                "q_ban_dia": float(h.q_ban_dia) if h.q_ban_dia is not None else None,
                "don_vi_ban_dia": h.don_vi_ban_dia,
                "tong_ty_le_ho_tro": float(h.tong_ty_le_ho_tro or 0),
                "can_chot": pb_flags[h.id]["can_chot"],
                "canh_bao": pb_flags[h.id]["canh_bao"],
                "thieu_cham_cong": pb_flags[h.id]["thieu_cham_cong"],
                "loai_tru": [
                    {
                        "employee_id": lt.employee_id,
                        "ho_ten": _emp_ten(lt.employee_id),
                        "ly_do": lt.ly_do,
                    }
                    for lt in loai_tru_map.get(h.id, [])
                ],
                "dong": [
                    {
                        "employee_id": d.employee_id,
                        "ho_ten": _emp_ten(d.employee_id),
                        "department_id": d.department_id,
                        "la_ho_tro": d.la_ho_tro,
                        "ngay": d.ngay,
                        "so_luong_tra_luong": float(d.so_luong_tra_luong or 0),
                        "so_luong_ban_dia": float(d.so_luong_ban_dia) if d.so_luong_ban_dia is not None else None,
                        "trong_so": float(d.trong_so) if d.trong_so is not None else None,
                        "phut_thuc_te": float(d.phut_thuc_te) if d.phut_thuc_te is not None else None,
                        "he_so_bac": float(d.he_so_bac) if d.he_so_bac is not None else None,
                        "don_gia": float(d.don_gia or 0),
                    }
                    for d in dong_map.get(h.id, [])
                ],
                "bu_tru": [
                    {
                        "id": bt.id,
                        "employee_id": bt.employee_id,
                        "ho_ten": _emp_ten(bt.employee_id),
                        "so_luong_tra_luong": float(bt.so_luong_tra_luong or 0),
                        "don_gia": float(bt.don_gia or 0),
                        "ky_bu_nam": bt.ky_bu_nam,
                        "ky_bu_thang": bt.ky_bu_thang,
                        "mo_ta": bt.mo_ta,
                    }
                    for bt in bu_tru_map.get(h.id, [])
                ],
            }
            for h in pb_headers
        ],
    }
