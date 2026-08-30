"""Dựng SNAPSHOT phát hành — chụp routing/tổ/máy/định mức/khoán/vật tư tại thời điểm phát hành.

Nguyên tắc (spec §4.2):

  · CHỤP MỘT LẦN. Sau phát hành, xưởng sửa danh mục (đổi tổ, đổi định mức khoán) KHÔNG được làm
    xê dịch việc đã thả xuống — mọi số của công việc nằm ở đây, không đọc-sống lên routing.
  · MỘT BÀI GHÉP = MỘT CÔNG VIỆC (spec §3.3). Bước đã gộp vào bài ghép chỉ đẻ ĐÚNG MỘT công việc
    chung; các bước LSX bị nó phủ (`bai_ghep_cong_doan_map.lsx_step_key`) KHÔNG đẻ công việc riêng.
  · Số dẫn xuất (tiền khoán, sản lượng thực) KHÔNG chụp — tính lúc đọc ở pha thực thi.

Hàm ở đây THUẦN dựng-bản-ghi: nhận gói + phiên bản đã tạo, ghi công việc/phụ thuộc vào session,
KHÔNG commit (người gọi — `release.py` — chủ giao dịch).
"""
from __future__ import annotations

from ...models.san_xuat import (
    BUOC_MAY,
    CV_PHAT_HANH,
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatPhuThuoc,
)
from ...repositories.san_xuat_repo import SanXuatRepository
from ..dong_giay import ban_do_tram, tren_dong_giay


def _num(x) -> float | None:
    """Numeric (Decimal) → float cho JSON; None giữ None."""
    return None if x is None else float(x)


def _dinh_muc(cd) -> dict:
    """Ảnh định mức nhân lực + thời gian của một bước (LSX hoặc bài ghép — cùng hình dạng)."""
    return {
        "so_nhan_cong_tieu_chuan": getattr(cd, "so_nhan_cong_tieu_chuan", None),
        "so_nhan_cong_toi_da": getattr(cd, "so_nhan_cong_toi_da", None),
        "so_nhan_cong_toi_thieu": getattr(cd, "so_nhan_cong_toi_thieu", None),
        "setup_phut": _num(getattr(cd, "setup_phut", None)),
        "nang_suat": _num(getattr(cd, "nang_suat", None)),
        "don_vi_nang_suat": getattr(cd, "don_vi_nang_suat", None),
        "chay_phut": _num(getattr(cd, "chay_phut", None)),
        "phat_sinh_phut": _num(getattr(cd, "phat_sinh_phut", None)),
    }


def _vat_tu(cd) -> list[dict]:
    """Ảnh danh sách vật tư của bước (đọc quan hệ `.vat_tus` — đã snapshot mã/tên/đơn vị từ trước)."""
    out: list[dict] = []
    for vt in getattr(cd, "vat_tus", []) or []:
        out.append({
            "vat_tu_id": vt.vat_tu_id,
            "ma": vt.vat_tu_ma_snapshot,
            "ten": vt.vat_tu_ten_snapshot,
            "don_vi": vt.don_vi_snapshot,
            "so_luong": _num(vt.so_luong),
        })
    return out


def _checklist(cd, tieu_chi_theo_cd: dict[int, list]) -> list[dict] | None:
    """Ghép checklist danh mục (theo cong_doan_id của bước) + bổ sung riêng của bước, đúng thứ tự.
    None nếu bước không phải KCS — cột chỉ có ý nghĩa với `la_kcs=True`."""
    if not cd.la_kcs:
        return None
    out: list[dict] = []
    for tc in tieu_chi_theo_cd.get(cd.cong_doan_id, []) if cd.cong_doan_id else []:
        out.append({
            "tieu_chi_id": tc.id, "ma": tc.ma, "ten": tc.ten, "huong_dan": tc.huong_dan,
            "bat_buoc": bool(tc.bat_buoc), "nguon": "danh_muc", "thu_tu": tc.thu_tu,
        })
    for i, bs in enumerate(getattr(cd, "kcs_tieu_chi_bo_sung_json", None) or []):
        out.append({
            "tieu_chi_id": None, "ma": None, "ten": bs.get("ten"), "huong_dan": bs.get("huong_dan"),
            "bat_buoc": bool(bs.get("bat_buoc", True)), "nguon": "bo_sung_lsx", "thu_tu": 1000 + i,
        })
    return out


def dung_cong_viec(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    tieu_chi_theo_cd: dict[int, list] | None = None,
) -> dict[str, SanXuatCongViec]:
    """Đẻ công việc cho gói phát hành; trả map `step_key` → công việc (để nối phụ thuộc).

    Với bước LSX bị bài ghép phủ, `step_key` của nó cũng trỏ về công việc CHUNG — cạnh phụ thuộc
    chéo neo vào đúng bản ghi thực hiện chung.
    """
    cv_by_step: dict[str, SanXuatCongViec] = {}
    tieu_chi_theo_cd = tieu_chi_theo_cd or {}

    # (1) Bước dùng chung của bài ghép — MỘT công việc mỗi bước, phủ nhiều bước LSX.
    covered_step_keys: set[str] = set()
    for bg_id in sorted(bai_ghep_ids):
        for cd in repo.bai_ghep_cong_doans(bg_id):
            may_id, start, finish = repo.thoi_gian_bg_step(cd.id)
            covered = repo.covered_step_keys_of_cd(cd.id)
            covered_step_keys |= covered
            # Nhóm của công việc chung: nếu mọi LSX được phủ cùng một nhóm thì gán nhóm đó, khác
            # nhau (bài ghép nối nhiều nhóm) thì để trống — phân bổ sản lượng theo nhóm ở pha sau.
            nhom_ids = {
                nhom_by_lsx[lid].id
                for lid in repo.lsx_ids_covered_by_cd(cd.id)
                if lid in nhom_by_lsx
            }
            nhom_id = next(iter(nhom_ids)) if len(nhom_ids) == 1 else None
            cv = SanXuatCongViec(
                goi_id=goi.id, phien_ban_so=phien_ban_so,
                nhom_id=nhom_id, lsx_id=None, bai_ghep_id=bg_id,
                bai_ghep_cong_doan_id=cd.id, step_key=cd.step_key,
                ten_cong_doan=cd.ten, nhom_cong_doan=cd.nhom, loai_buoc=cd.loai_buoc or BUOC_MAY,
                department_id=cd.department_id, la_kcs=bool(cd.la_kcs),
                may_id=may_id or cd.may_id,
                du_kien_bat_dau=start, du_kien_ket_thuc=finish,
                so_luong_vao=cd.so_luong_vao, so_luong_ra=cd.so_luong_ra,
                don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra, he_so_quy_doi=cd.he_so_quy_doi,
                dinh_muc_json=_dinh_muc(cd), khoan_json=cd.khoan_json, vat_tu_json=_vat_tu(cd),
                kcs_tieu_chi_json=_checklist(cd, tieu_chi_theo_cd),
                trang_thai=CV_PHAT_HANH,
            )
            repo.add(cv)
            repo.flush()
            cv_by_step[cd.step_key] = cv
            for sk in covered:
                cv_by_step[sk] = cv

    # (2) Bước RIÊNG của từng LSX — bỏ bước đã bị bài ghép phủ.
    for lsx_id in sorted(lsx_ids):
        grp = nhom_by_lsx.get(lsx_id)
        for cd in repo.routing_steps(lsx_id):
            if cd.step_key in covered_step_keys:
                continue
            may_id, start, finish = repo.thoi_gian_lsx_step(cd.id)
            cv = SanXuatCongViec(
                goi_id=goi.id, phien_ban_so=phien_ban_so,
                nhom_id=grp.id if grp else None, lsx_id=lsx_id, bai_ghep_id=None,
                lsx_cong_doan_id=cd.id, step_key=cd.step_key,
                ten_cong_doan=cd.ten, nhom_cong_doan=cd.nhom, loai_buoc=cd.loai_buoc or BUOC_MAY,
                department_id=cd.department_id, la_kcs=bool(cd.la_kcs),
                may_id=may_id or cd.may_id,
                du_kien_bat_dau=start, du_kien_ket_thuc=finish,
                so_luong_vao=cd.so_luong_vao, so_luong_ra=cd.so_luong_ra,
                don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra, he_so_quy_doi=cd.he_so_quy_doi,
                dinh_muc_json=_dinh_muc(cd), khoan_json=cd.khoan_json, vat_tu_json=_vat_tu(cd),
                kcs_tieu_chi_json=_checklist(cd, tieu_chi_theo_cd),
                trang_thai=CV_PHAT_HANH,
            )
            repo.add(cv)
            repo.flush()
            cv_by_step[cd.step_key] = cv

    return cv_by_step


def danh_dau_kcs_cuoi(
    repo: SanXuatRepository,
    *,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, SanXuatCongViec],
) -> dict[int, int]:
    """Suy KCS-cuối của MỖI nhóm (spec §3.2/§4.4): bước KCS nằm ở CUỐI routing của một LSX thành
    viên. Đúng một ứng viên/nhóm → đánh `la_kcs_cuoi` + chốt LSX thân chính. Không có / nhiều hơn
    một → để engine kiểm-phát-hành báo (không tự đoán).

    Trả map nhom_id → lsx_id thân chính (chỉ nhóm xác định được).
    """
    ung_vien: dict[int, list[tuple[int, str]]] = {}  # nhom_id → [(lsx_id, step_key)]
    for lsx_id in lsx_ids:
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        steps = repo.routing_steps(lsx_id)
        if not steps:
            continue
        cuoi = steps[-1]  # đã sort theo thu_tu, id
        if cuoi.la_kcs and cuoi.step_key in cv_by_step:
            ung_vien.setdefault(grp.id, []).append((lsx_id, cuoi.step_key))

    than_chinh: dict[int, int] = {}
    for nhom_id, ds in ung_vien.items():
        if len(ds) != 1:
            continue
        lsx_id, step_key = ds[0]
        cv_by_step[step_key].la_kcs_cuoi = True
        than_chinh[nhom_id] = lsx_id
    return than_chinh


def dung_phu_thuoc(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, SanXuatCongViec],
) -> int:
    """Chụp cạnh phụ thuộc CHÉO giữa các LSX trong gói thành `san_xuat_phu_thuoc` (bước ghép §3.2).

    Chỉ nối cạnh mà CẢ hai đầu đều có công việc trong gói này; neo về công việc chung nếu đầu đó đã
    bị bài ghép phủ (nhờ `cv_by_step` đã map cả step_key bị phủ). Nhóm lấy từ LSX ĐÍCH (luôn có
    trong gói) — `cong_viec.nhom_id` có thể trống nếu đầu đó là bước dùng chung nối nhiều nhóm, mà
    cột `san_xuat_phu_thuoc.nhom_id` NOT NULL. Tỷ lệ ghép để trống — kế hoạch tinh chỉnh ở pha sau."""
    dem = 0
    for truoc, sau in repo.cross_lsx_edges_chi_tiet(lsx_ids):
        nguon = cv_by_step.get(truoc.step_key)
        dich = cv_by_step.get(sau.step_key)
        if nguon is None or dich is None or nguon.id == dich.id:
            continue
        grp = nhom_by_lsx.get(sau.lsx_id) or nhom_by_lsx.get(truoc.lsx_id)
        if grp is None:
            continue  # không truy được nhóm (dữ liệu cũ) — bỏ cạnh còn hơn vỡ NOT NULL
        repo.add(SanXuatPhuThuoc(
            goi_id=goi.id, phien_ban_so=phien_ban_so,
            nhom_id=grp.id,
            nguon_cong_viec_id=nguon.id, dich_cong_viec_id=dich.id,
            don_vi_nguon=truoc.don_vi_ra, don_vi_dich=sau.don_vi_vao,
        ))
        dem += 1
    repo.flush()
    return dem


def dung_diem_toa(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, SanXuatCongViec],
) -> int:
    """Chụp cạnh TOẢ từ điểm-toả bài ghép sang từng nhánh LSX riêng thành `san_xuat_phu_thuoc`.

    Điểm toả = bước dùng chung CUỐI CÙNG trên dòng giấy của một LSX thành viên (theo `thu_tu`
    routing); đích = bước RIÊNG đầu tiên ngay sau đó của chính LSX đó. Chỉ nhận bước dùng chung
    nằm TRÊN DÒNG GIẤY (`tren_dong_giay`) — bước như ghi kẽm/CTP không đếm, tránh lấy nhầm điểm
    toả. LSX không còn bước riêng nào sau bước chung cuối (mọi bước đều dùng chung, hoặc bài ghép
    chưa có bước chung nào trên dòng giấy) thì không có gì để toả — bỏ qua, không phải lỗi."""
    if not bai_ghep_ids:
        return 0
    so_con = repo.thanh_vien_so_con(bai_ghep_ids)
    tram = ban_do_tram(repo.db)
    dem = 0
    for lsx_id in sorted(lsx_ids):
        con = so_con.get(lsx_id)
        if not con or con <= 0:
            continue
        steps = repo.routing_steps(lsx_id)
        diem_toa_idx = None
        for i, cd in enumerate(steps):
            cv = cv_by_step.get(cd.step_key)
            if cv is None or cv.bai_ghep_id is None:
                continue
            if not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram, nhom=cd.nhom):
                continue
            diem_toa_idx = i
        if diem_toa_idx is None:
            continue
        nguon_cv = cv_by_step[steps[diem_toa_idx].step_key]
        dich_cd = next(
            (
                cd for cd in steps[diem_toa_idx + 1:]
                if cv_by_step.get(cd.step_key) and cv_by_step[cd.step_key].bai_ghep_id is None
            ),
            None,
        )
        if dich_cd is None:
            continue
        dich_cv = cv_by_step[dich_cd.step_key]
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        don_vi_ra = steps[diem_toa_idx].don_vi_ra
        don_vi_vao = dich_cd.don_vi_vao
        repo.add(SanXuatPhuThuoc(
            goi_id=goi.id, phien_ban_so=phien_ban_so,
            nhom_id=grp.id,
            nguon_cong_viec_id=nguon_cv.id, dich_cong_viec_id=dich_cv.id,
            ty_le_ghep=float(con),
            don_vi_nguon=don_vi_ra, don_vi_dich=don_vi_vao,
            quy_tac_quy_doi=(
                f"Điểm toả bài ghép: 1 {don_vi_ra or '?'} chung → {con} {don_vi_vao or '?'} riêng của lệnh"
            ),
        ))
        dem += 1
    repo.flush()
    return dem
