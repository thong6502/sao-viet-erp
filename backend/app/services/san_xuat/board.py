"""Bàn THỰC HIỆN tại tổ — mặt đọc (§11, §18 `/api/san-xuat/teams` + `/work-items`).

Đây là nền của Giai đoạn 2: mỗi node LÁ trong Khối Sản xuất là một tổ; tổ trưởng mở bàn của tổ
mình thấy các công việc ĐÃ PHÁT HÀNH (đọc từ snapshot gói, không đọc-sống routing). Lát này CHỈ
ĐỌC — phân công / phiên chạy / sản lượng là các lát sau (thêm bảng riêng).

Phạm vi tổ theo QUYỀN người đăng nhập, tái dùng đúng cơ chế scope của module `san_xuat` (giống
`routers/lsx.py`): `all` thấy mọi tổ; `department` thấy cả cây con phòng mình; `own` chỉ tổ mình.
Không có "quyền ghi đè cho quản lý cấp cao" (§10) — cấp trên phạm vi rộng vẫn chỉ để xem.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ...models.san_xuat_phan_bo import PB_DA_CHOT
from ...models.stock_request import REQ_CANCELLED
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
from .phan_bo import _tinh_batch
from .thuc_thi import _aware
from .vat_tu_de_nghi import _hang_service, _kh_service, moi_dong_deu_0

MODULE = "san_xuat"


def _to_thay_duoc(
    db: Session, user: User, authz: AuthorizationService
) -> tuple[list, set[int]]:
    """(danh sách tổ = node lá Khối SX mà user được thấy, tập id của chúng) theo scope `san_xuat`.

    `to_san_xuat()` là ĐỊNH NGHĨA CHUNG của "tổ" (node lá khối SX). Lọc thêm theo scope: cấp
    xưởng (`all`) thấy hết; tổ trưởng (`department`/`own`) chỉ cây con phòng mình.
    """
    tos = DepartmentRepository(db).to_san_xuat()
    scope = authz.scope_for(user, MODULE) or SCOPE_ALL
    if scope == SCOPE_ALL:
        pass
    elif scope == SCOPE_DEPARTMENT:
        cho_phep = dept_subtree_ids(db, user.department_id) or set()
        tos = [d for d in tos if d.id in cho_phep]
    else:  # own
        tos = [d for d in tos if d.id == user.department_id]
    return tos, {d.id for d in tos}


def teams(db: Session, user: User, authz: AuthorizationService) -> list[dict]:
    """Danh sách tổ sản xuất hiệu lực + badge số việc chưa xong (§18 `/teams`, §2.1 navbar)."""
    repo = SanXuatRepository(db)
    tos, ids = _to_thay_duoc(db, user, authz)
    badge = repo.dem_cho_lam_theo_to(ids)
    return [
        {
            "id": d.id,
            "ten": d.name,
            "ma": d.code,
            "la_kcs": bool(getattr(d, "is_kcs", False)),
            "so_viec_cho": badge.get(d.id, 0),
        }
        for d in tos
    ]


def _num(x) -> float | None:
    return None if x is None else float(x)


def _item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map=None) -> dict:
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
        "du_kien_bat_dau": cv.du_kien_bat_dau,
        "du_kien_ket_thuc": cv.du_kien_ket_thuc,
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
        # Định mức vật tư đóng băng lúc phát hành (§4.2) — đã đúng hình `VatTuDinhMucOut`, không cần dựng lại.
        "dinh_muc_vat_tu": cv.vat_tu_json or [],
        # Lớp thực-tế (§5.1): các phiên chạy đã ghi; phiên còn mở giữ ket_thuc=None (FE kéo tới "bây giờ").
        "thuc_te": [
            {"bat_dau": p.bat_dau, "ket_thuc": p.ket_thuc}
            for p in (phien_map or {}).get(cv.id, [])
        ],
    }


def work_items(db: Session, user: User, authz: AuthorizationService, *, team_id: int) -> dict:
    """Công việc đã phát hành của MỘT tổ (timeline). Chặn nếu tổ ngoài phạm vi quyền của user."""
    repo = SanXuatRepository(db)
    _tos, ids = _to_thay_duoc(db, user, authz)
    if team_id not in ids:
        raise PermissionError("Ngoài phạm vi tổ được phép xem.")

    rows = repo.cong_viec_cua_to({team_id})
    lsx_map = repo.lsx_nhan({cv.lsx_id for cv in rows if cv.lsx_id})
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id for cv in rows if cv.bai_ghep_id})
    may_map = repo.may_nhan({cv.may_id for cv in rows if cv.may_id})
    nhom_map = repo.nhom_nhan({cv.nhom_id for cv in rows if cv.nhom_id})
    # Lớp thực-tế: phiên chạy của cả gói trong MỘT truy vấn (§5.1), tránh N+1 theo từng việc.
    phien_map = SanXuatThucThiRepository(db).phien_theo_cong_viec({cv.id for cv in rows})
    items = [_item_dict(cv, lsx_map, bg_map, may_map, nhom_map, phien_map) for cv in rows]
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
            "dvt": k["dvt"], "sl_ke_hoach": k["sl"], "sl_yeu_cau": 0.0,
            "sl_thuc_xuat": 0.0, "cac_ly_do": [],
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
                "ten": ten_map.get(key) or f"#{d.hang_id}", "dvt": d.dvt,
                "sl_ke_hoach": float(d.sl_ke_hoach), "sl_yeu_cau": 0.0,
                "sl_thuc_xuat": 0.0, "cac_ly_do": [],
            })
            row["sl_yeu_cau"] += float(d.sl_yeu_cau)
            if d.ly_do_chenh_lech:
                row["cac_ly_do"].append({"lan_so": dn.lan_so, "ly_do": d.ly_do_chenh_lech})
            dongs_theo_lan[dn.id].append({
                "hang_loai": d.hang_loai, "hang_id": d.hang_id,
                "ten": ten_map.get(key) or f"#{d.hang_id}", "dvt": d.dvt,
                "sl_ke_hoach": float(d.sl_ke_hoach), "sl_yeu_cau": float(d.sl_yeu_cau),
                "ly_do_chenh_lech": d.ly_do_chenh_lech,
            })
    for key, sl_ra in thuc_xuat.items():
        if key in gom:
            gom[key]["sl_thuc_xuat"] = sl_ra

    doi_chieu = []
    for row in gom.values():
        row["lech_ke_hoach"] = row["sl_yeu_cau"] - row["sl_ke_hoach"]
        row["lech_thuc_te"] = row["sl_thuc_xuat"] - row["sl_yeu_cau"]
        doi_chieu.append(row)

    lan_cuoi = cac_dn[-1] if cac_dn else None
    req_repo = StockRequestRepository(db)
    tt = tom_tat.get(lan_cuoi.stock_request_id, {}).get("trang_thai") if lan_cuoi else None
    # Kho hủy yêu cầu rồi thì `sua()` sẽ ném — đừng mời tổ bấm sửa để rồi ăn 400 (ruling task-7
    # 27). Còn `cancelled` do CHÍNH tổ đưa mọi dòng về 0 thì vẫn sửa lại được (nhập số dương là
    # khôi phục) — `moi_dong_deu_0` là ĐÚNG vị ngữ `sua()` dùng, không viết lại lần hai.
    kho_da_huy = tt == REQ_CANCELLED and not moi_dong_deu_0(lan_cuoi)
    con_sua_duoc = (
        bool(lan_cuoi)
        and not req_repo.co_voucher(lan_cuoi.stock_request_id)
        and not kho_da_huy
    )
    return {
        "ke_hoach": ke_hoach,
        "cac_de_nghi": [{
            "id": d.id, "lan_so": d.lan_so, "loai": d.loai, "can_luc": d.can_luc,
            "stock_request_id": d.stock_request_id,
            "stock_request_ma": tom_tat.get(d.stock_request_id, {}).get("ma"),
            "stock_request_trang_thai": tom_tat.get(d.stock_request_id, {}).get("trang_thai"),
            "created_by_id": d.created_by_id, "updated_by_id": d.updated_by_id,
            "created_at": d.created_at, "updated_at": d.updated_at,
            "dongs": dongs_theo_lan[d.id],
        } for d in cac_dn],
        "doi_chieu": doi_chieu,
        "de_nghi_co_the_sua_id": lan_cuoi.id if con_sua_duoc else None,
        "co_the_tao_bo_sung": (not cac_dn) or (not con_sua_duoc),
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

    lsx_map = repo.lsx_nhan({cv.lsx_id} if cv.lsx_id else set())
    bg_map = repo.bai_ghep_nhan({cv.bai_ghep_id} if cv.bai_ghep_id else set())
    may_map = repo.may_nhan({cv.may_id} if cv.may_id else set())
    nhom_map = repo.nhom_nhan({cv.nhom_id} if cv.nhom_id else set())

    roster = tt.phan_cong_hoat_dong(cv.id)
    khoang = tt.cac_khoang(cv.id)

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
    doi_tac_map: dict[int, str] = {}
    for did in doi_tac_ids:
        dcv = sl.cong_viec(did)
        if dcv is not None:
            doi_tac_map[did] = dcv.ten_cong_doan
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
        "cong_viec": _item_dict(cv, lsx_map, bg_map, may_map, nhom_map),
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
                "bat_dau": p.bat_dau,
                "ket_thuc": p.ket_thuc,
                "loai_dong": p.loai_dong,
                "ly_do_bat_dau_tre": p.ly_do_bat_dau_tre,
                "ly_do": p.ly_do,
            }
            for p in tt.cac_phien(cv.id)
        ],
        "khoang_tham_gia": [
            {
                "id": k.id,
                "phien_chay_id": k.phien_chay_id,
                "employee_id": k.employee_id,
                "ho_ten": ten_map.get(k.employee_id, ("", None))[0],
                "bat_dau": k.bat_dau,
                "ket_thuc": k.ket_thuc,
            }
            for k in khoang
        ],
        "san_luong": {
            "tong_tot": sl.tong_tot(cv.id),
            "da_giao": sl.tong_da_giao(cv.id),
            "batches": [
                {
                    "id": b.id,
                    "bat_dau": b.bat_dau,
                    "ket_thuc": b.ket_thuc,
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
                "du_kien_bat_dau": c.du_kien_bat_dau,
            }
            for c in goi_y
        ],
        "vat_tu": [
            {
                "voucher_id": v.id,
                "ma": v.ma,
                "da_nhan": v.id in nhan_map,
                "xac_nhan_luc": nhan_map[v.id].xac_nhan_luc if v.id in nhan_map else None,
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
