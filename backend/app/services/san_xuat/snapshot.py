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


def _khuon(db, cd) -> dict | None:
    """Ảnh chụp con dao của bước. `None` khi bước không trỏ dao nào (kể cả bước không cần dụng cụ).

    Đọc ĐÍCH DANH cột thay vì trả cả object: ảnh chụp phải là dữ liệu chết, không phải một hàng ORM
    còn sống mà lần đọc sau lại ra giá trị khác. Cùng lý do với `_vat_tu` ngay dưới.
    """
    kid = getattr(cd, "khuon_be_id", None)
    if not kid:
        return None
    from ...models.khuon_be import KhuonBe

    k = db.get(KhuonBe, kid)
    if k is None:
        return None
    return {
        "id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
        "tinh_trang": k.tinh_trang,
        # ISO chứ không phải object date: JSON column phải serialize được, và FE đọc `yyyy-mm-dd`.
        "ngay_ve_du_kien": k.ngay_ve_du_kien.isoformat() if k.ngay_ve_du_kien else None,
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


def _chia(tong, ty_les: list[float]) -> list[float | None]:
    """Chia `tong` theo `ty_les`; phần CUỐI gánh phần lẻ làm tròn ⇒ Σ khép ĐÚNG `tong`.

    Cùng cách khép tổng với `phan_doan.tach`: cột là NUMERIC(18,3), làm tròn từng phần rồi cộng
    lại là tổng trôi một tờ — mà lệch một tờ là lệch cả bảng cân đối vật tư lẫn định mức khoán.
    """
    if tong is None:
        return [None] * len(ty_les)
    t = float(tong)
    ra = [round(t * r, 3) for r in ty_les]
    ra[-1] = round(t - sum(ra[:-1]), 3)
    return ra


def _chia_theo_phan_doan(lich: list[tuple], cd) -> list[tuple]:
    """Số `(vào, ra)` của TỪNG phân đoạn lịch, Σ khép đúng số của bước.

    Tỉ lệ lấy từ CHÍNH CỤM (Σ `so_luong` của các dòng) — cùng MỘT đường với
    `phan_doan.ty_le_trong_cum` mà engine thời lượng đang dùng, đừng đẻ đường thứ hai:

      · suy từ `phan_doan_tong` kiểu 1/N là sai ngay khi ai đó chia 6.000 + 4.000;
      · lấy `so_luong_vao` của bước làm mẫu số thì bước chưa khai số (0) sẽ cho MỖI phân đoạn ăn
        TRỌN số của bước — nhân bản sản lượng, im lặng.

    Chia CẢ hai cột theo cùng tỉ lệ, không gán thẳng `so_luong` của dòng vào `so_luong_vao`: bước
    có hệ số quy đổi (in: vào tờ, ra con) mà chỉ chia một cột là hai cột nói hai thang khác nhau.
    """
    if len(lich) == 1 and lich[0][4] is None:
        # Bước CHƯA tách — giữ NGUYÊN số của bước (Decimal), không đi vòng qua float. Đây là
        # đường của mọi lệnh đang chạy, đừng để nó lệch một phần nghìn so với trước.
        return [(cd.so_luong_vao, cd.so_luong_ra)]
    n = len(lich)
    tong_cum = sum(float(r[4] or 0) for r in lich)
    ty_les = (
        [float(r[4] or 0) / tong_cum for r in lich] if tong_cum > 0 else [1.0 / n] * n
    )
    return list(zip(_chia(cd.so_luong_vao, ty_les), _chia(cd.so_luong_ra, ty_les)))


def _ten_phan_doan(ten: str | None, phan_doan_so: int, phan_doan_tong: int) -> str:
    """Tên công việc của một phân đoạn — bước chưa tách giữ nguyên tên bước.

    Tổ nhìn hai thẻ cùng công đoạn mà không có hậu tố thì không biết thẻ nào là mẻ nào. Cột
    `ten_cong_doan` là String(255) nên cắt phần TÊN chứ đừng cắt hậu tố: mất "lần 2/2" là mất
    đúng thứ dùng để phân biệt.
    """
    goc = ten or ""
    if phan_doan_tong <= 1:
        return goc
    hau_to = f" (lần {phan_doan_so}/{phan_doan_tong})"
    return goc[: 255 - len(hau_to)] + hau_to


def _checklist(cd, tieu_chi_theo_cd: dict[int, list], la_kcs: bool) -> list[dict] | None:
    """Ghép checklist danh mục (theo cong_doan_id của bước) + bổ sung riêng của bước, đúng thứ tự.
    None nếu bước không phải KCS — `la_kcs` đã được tính sẵn ở `dung_cong_viec` (suy tự động, xem
    đó), không đọc cột nào ở đây."""
    if not la_kcs:
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


def _cong_viec_theo_phan_doan(
    repo: SanXuatRepository,
    *,
    lich: list[tuple],
    cd,
    tieu_chi_theo_cd: dict[int, list],
    la_kcs: bool,
    chung: dict,
) -> list[SanXuatCongViec]:
    """Đẻ MỘT công việc cho MỖI phân đoạn lịch của một bước; trả danh sách theo `phan_doan_so`.

    Dùng chung cho cả hai nhánh (bước riêng của lệnh + bước chạy chung của bài ghép) vì hai bên
    chỉ khác ở mấy khoá neo — gom vào `chung`. `lich` là kết quả `repo.lich_lsx_step` /
    `lich_bg_step`: mỗi phần tử `(may_id, start, finish, phan_doan_so, so_luong)`.

    Bước CHƯA vào kế hoạch (không dòng lịch nào) vẫn phải ra đúng một công việc — trước đây
    `thoi_gian_*_step` trả `(None, None, None)` và snapshot vẫn ghi; giữ nguyên hành vi đó bằng
    một phần tử giả, không thì lệnh phát hành khi chưa xếp giờ sẽ RỖNG bàn tổ.

    `la_kcs` tính MỘT LẦN cho cả bước rồi áp cho mọi phân đoạn: KCS là tính chất của BƯỚC (vị trí
    trong routing + tổ), không phải của lần chạy.
    """
    if not lich:
        lich = [(None, None, None, 1, None)]
    tong = len(lich)
    so_luongs = _chia_theo_phan_doan(lich, cd)
    ra: list[SanXuatCongViec] = []
    for (may_id, start, finish, phan_doan_so, _sl), (sl_vao, sl_ra) in zip(lich, so_luongs):
        cv = SanXuatCongViec(
            **chung,
            step_key=cd.step_key,
            # Cặp số phân đoạn ghi THÀNH CỘT chứ không chỉ nằm trong tên: "Phát hành cập nhật"
            # phải khớp công việc ↔ dòng lịch bằng số, không bằng cách đọc lại nhãn tiếng Việt.
            phan_doan_so=phan_doan_so, phan_doan_tong=tong,
            ten_cong_doan=_ten_phan_doan(cd.ten, phan_doan_so, tong),
            nhom_cong_doan=cd.nhom, loai_buoc=cd.loai_buoc or BUOC_MAY,
            department_id=cd.department_id, la_kcs=la_kcs,
            may_id=may_id or cd.may_id,
            du_kien_bat_dau=start, du_kien_ket_thuc=finish,
            so_luong_vao=sl_vao, so_luong_ra=sl_ra,
            don_vi_vao=cd.don_vi_vao, don_vi_ra=cd.don_vi_ra, he_so_quy_doi=cd.he_so_quy_doi,
            # Định mức/khoán/vật tư KHÔNG chia theo phân đoạn: chúng là ĐỊNH MỨC (trên một đơn vị
            # / trên một lượt), chia nữa là chia hai lần. Sản lượng đã mang phần của phân đoạn.
            dinh_muc_json=_dinh_muc(cd), khoan_json=cd.khoan_json, vat_tu_json=_vat_tu(cd),
            # Nhà gia công + con dao: chụp CÙNG LÚC với vật tư, cùng một lý do — bàn tổ và các màn
            # theo dõi phải tự đứng được, không tra ngược lệnh (lệnh còn sửa được sau khi phát).
            nha_cung_cap=getattr(cd, "nha_cung_cap", None),
            khuon_json=_khuon(repo.db, cd),
            # Gọi lại `_checklist` cho TỪNG phân đoạn: mỗi dòng phải giữ bản JSON riêng, dùng
            # chung một list Python là sửa checklist của mẻ này lan sang mẻ kia.
            kcs_tieu_chi_json=_checklist(cd, tieu_chi_theo_cd, la_kcs),
            trang_thai=CV_PHAT_HANH,
        )
        repo.add(cv)
        repo.flush()
        ra.append(cv)
    return ra


def dung_cong_viec(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    tieu_chi_theo_cd: dict[int, list] | None = None,
) -> dict[str, list[SanXuatCongViec]]:
    """Đẻ công việc cho gói phát hành; trả map `step_key` → DANH SÁCH công việc theo phân đoạn.

    Trước 31/08/2026 map này là `step_key` → MỘT công việc, vì một bước chỉ có một dòng lịch. Từ
    khi tách được LẦN CHẠY (spec-thuc-te-vs-ke-hoach §2.4), một bước có N dòng lịch ⇒ N công việc,
    xếp theo `phan_doan_so`. Bước chưa tách vẫn ra danh sách MỘT phần tử — bên gọi không cần phân
    biệt hai trường hợp.

    Với bước LSX bị bài ghép phủ, `step_key` của nó cũng trỏ về danh sách công việc CHUNG — cạnh
    phụ thuộc chéo neo vào đúng bản ghi thực hiện chung.
    """
    cv_by_step: dict[str, list[SanXuatCongViec]] = {}
    tieu_chi_theo_cd = tieu_chi_theo_cd or {}

    # KCS kiêm nhiệm — suy TỰ ĐỘNG (không còn khai tay ở danh mục Công đoạn): một bước là KCS khi
    # nó là bước CUỐI CÙNG trong routing của một LSX VÀ tổ thực hiện có `Department.is_kcs=true`
    # (xem docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem-suy-tu-dong.md). Nạp trước "bước cuối
    # của mỗi LSX" một lần để tra O(1) ở cả hai nhánh dưới (LSX riêng + bước dùng chung bài ghép).
    kcs_dept_ids = repo.kcs_department_ids()
    steps_by_lsx = {lsx_id: repo.routing_steps(lsx_id) for lsx_id in lsx_ids}
    buoc_cuoi_key_by_lsx = {
        lid: steps[-1].step_key for lid, steps in steps_by_lsx.items() if steps
    }

    # (1) Bước dùng chung của bài ghép — MỘT công việc mỗi bước, phủ nhiều bước LSX.
    covered_step_keys: set[str] = set()
    for bg_id in sorted(bai_ghep_ids):
        for cd in repo.bai_ghep_cong_doans(bg_id):
            covered = repo.covered_step_keys_of_cd(cd.id)
            covered_step_keys |= covered
            covered_lsx_ids = repo.lsx_ids_covered_by_cd(cd.id)
            # Nhóm của công việc chung: nếu mọi LSX được phủ cùng một nhóm thì gán nhóm đó, khác
            # nhau (bài ghép nối nhiều nhóm) thì để trống — phân bổ sản lượng theo nhóm ở pha sau.
            nhom_ids = {
                nhom_by_lsx[lid].id
                for lid in covered_lsx_ids
                if lid in nhom_by_lsx
            }
            nhom_id = next(iter(nhom_ids)) if len(nhom_ids) == 1 else None
            # KCS: bước chung này có phải bước cuối của ÍT NHẤT MỘT LSX nó phủ, VÀ tổ thực hiện
            # (của chính lượt chạy chung — gán lúc lập kế hoạch gộp) có `is_kcs=true`.
            la_kcs = cd.department_id in kcs_dept_ids and any(
                buoc_cuoi_key_by_lsx.get(lid) in covered for lid in covered_lsx_ids
            )
            cvs = _cong_viec_theo_phan_doan(
                repo, lich=repo.lich_bg_step(cd.id), cd=cd,
                tieu_chi_theo_cd=tieu_chi_theo_cd, la_kcs=la_kcs,
                chung=dict(
                    goi_id=goi.id, phien_ban_so=phien_ban_so,
                    nhom_id=nhom_id, lsx_id=None, bai_ghep_id=bg_id,
                    bai_ghep_cong_doan_id=cd.id,
                ),
            )
            cv_by_step[cd.step_key] = cvs
            for sk in covered:
                cv_by_step[sk] = cvs

    # (2) Bước RIÊNG của từng LSX — bỏ bước đã bị bài ghép phủ.
    for lsx_id in sorted(lsx_ids):
        grp = nhom_by_lsx.get(lsx_id)
        buoc_cuoi_key = buoc_cuoi_key_by_lsx.get(lsx_id)
        for cd in steps_by_lsx.get(lsx_id) or []:
            if cd.step_key in covered_step_keys:
                continue
            la_kcs = cd.step_key == buoc_cuoi_key and cd.department_id in kcs_dept_ids
            cv_by_step[cd.step_key] = _cong_viec_theo_phan_doan(
                repo, lich=repo.lich_lsx_step(cd.id), cd=cd,
                tieu_chi_theo_cd=tieu_chi_theo_cd, la_kcs=la_kcs,
                chung=dict(
                    goi_id=goi.id, phien_ban_so=phien_ban_so,
                    nhom_id=grp.id if grp else None, lsx_id=lsx_id, bai_ghep_id=None,
                    lsx_cong_doan_id=cd.id,
                ),
            )

    return cv_by_step


def danh_dau_kcs_cuoi(
    repo: SanXuatRepository,
    *,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> dict[int, int]:
    """Suy KCS-cuối của MỖI nhóm (spec §3.2/§4.4): bước KCS nằm ở CUỐI routing của một LSX thành
    viên. Đúng một ứng viên/nhóm → đánh `la_kcs_cuoi` + chốt LSX thân chính. Không có / nhiều hơn
    một → để engine kiểm-phát-hành báo (không tự đoán).

    Bước KCS-cuối bị TÁCH lần chạy: đánh dấu MỌI phân đoạn, không riêng phân đoạn cuối. `la_kcs_cuoi`
    là tính chất của BƯỚC, và ba chỗ đọc nó đều đọc theo TẬP: `kho.tao_yeu_cau_kho_mot_nut` chặn
    thẳng công việc thiếu cờ (bỏ cờ ở lần chạy 1 ⇒ số ĐẠT của mẻ đầu không có đường vào kho), còn
    `dong_nhom` cộng `so_luong_ra` + gom batch KCS trên đúng tập ấy (thiếu một phân đoạn ⇒ mục tiêu
    nhóm tụt đúng phần của nó). "Nhóm chỉ đóng khi mẻ cuối xong" vẫn giữ, do điều kiện "mọi công
    việc đã hoàn thành" của `dong_nhom._danh_gia` lo.

    Trả map nhom_id → lsx_id thân chính (chỉ nhóm xác định được).
    """
    kcs_dept_ids = repo.kcs_department_ids()
    ung_vien: dict[int, list[tuple[int, str]]] = {}  # nhom_id → [(lsx_id, step_key)]
    for lsx_id in lsx_ids:
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        steps = repo.routing_steps(lsx_id)
        if not steps:
            continue
        cuoi = steps[-1]  # đã sort theo thu_tu, id
        if cuoi.department_id in kcs_dept_ids and cuoi.step_key in cv_by_step:
            ung_vien.setdefault(grp.id, []).append((lsx_id, cuoi.step_key))

    than_chinh: dict[int, int] = {}
    for nhom_id, ds in ung_vien.items():
        if len(ds) != 1:
            continue
        lsx_id, step_key = ds[0]
        for cv in cv_by_step[step_key]:
            cv.la_kcs_cuoi = True
        than_chinh[nhom_id] = lsx_id
    return than_chinh


def dung_phu_thuoc(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> int:
    """Chụp cạnh phụ thuộc CHÉO giữa các LSX trong gói thành `san_xuat_phu_thuoc` (bước ghép §3.2).

    Chỉ nối cạnh mà CẢ hai đầu đều có công việc trong gói này; neo về công việc chung nếu đầu đó đã
    bị bài ghép phủ (nhờ `cv_by_step` đã map cả step_key bị phủ). Nhóm lấy từ LSX ĐÍCH (luôn có
    trong gói) — `cong_viec.nhom_id` có thể trống nếu đầu đó là bước dùng chung nối nhiều nhóm, mà
    cột `san_xuat_phu_thuoc.nhom_id` NOT NULL. Tỷ lệ ghép để trống — kế hoạch tinh chỉnh ở pha sau.

    Bước đã TÁCH lần chạy: nguồn là phân đoạn CUỐI, đích là phân đoạn ĐẦU. Nối vào phân đoạn đầu
    của nguồn là cho bước sau chạy khi mới xong 60% — đúng thứ mà tách lần chạy sinh ra để tránh."""
    dem = 0
    for truoc, sau in repo.cross_lsx_edges_chi_tiet(lsx_ids):
        nguon_ds = cv_by_step.get(truoc.step_key) or []
        dich_ds = cv_by_step.get(sau.step_key) or []
        if not nguon_ds or not dich_ds:
            continue
        nguon, dich = nguon_ds[-1], dich_ds[0]
        if nguon.id == dich.id:
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
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> int:
    """Chụp cạnh TOẢ từ điểm-toả bài ghép sang từng nhánh LSX riêng thành `san_xuat_phu_thuoc`.

    Điểm toả = bước dùng chung CUỐI CÙNG trên dòng giấy của một LSX thành viên (theo `thu_tu`
    routing); đích = bước RIÊNG đầu tiên ngay sau đó của chính LSX đó. Chỉ nhận bước dùng chung
    nằm TRÊN DÒNG GIẤY (`tren_dong_giay`) — bước như ghi kẽm/CTP không đếm, tránh lấy nhầm điểm
    toả. LSX không còn bước riêng nào sau bước chung cuối (mọi bước đều dùng chung, hoặc bài ghép
    chưa có bước chung nào trên dòng giấy) thì không có gì để toả — bỏ qua, không phải lỗi.

    Điểm toả bị TÁCH lần chạy: MỖI phân đoạn một cạnh. Cạnh này không phải cổng chặn mà là đường
    tự chia sản lượng (`san_luong._toa_san_luong` chạy theo từng batch của CÔNG VIỆC NGUỒN) — chỉ
    nối phân đoạn cuối thì số của mẻ đầu không bao giờ toả xuống nhánh, mất im lặng. Đích thì
    ngược lại, chỉ MỘT: phân đoạn đầu của bước riêng."""
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
            cvs = cv_by_step.get(cd.step_key)
            if not cvs or cvs[0].bai_ghep_id is None:
                continue
            if not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram, nhom=cd.nhom):
                continue
            diem_toa_idx = i
        if diem_toa_idx is None:
            continue
        nguon_cvs = cv_by_step[steps[diem_toa_idx].step_key]
        dich_cd = next(
            (
                cd for cd in steps[diem_toa_idx + 1:]
                if (cv_by_step.get(cd.step_key)
                    and cv_by_step[cd.step_key][0].bai_ghep_id is None)
            ),
            None,
        )
        if dich_cd is None:
            continue
        dich_cv = cv_by_step[dich_cd.step_key][0]
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        don_vi_ra = steps[diem_toa_idx].don_vi_ra
        don_vi_vao = dich_cd.don_vi_vao
        for nguon_cv in nguon_cvs:
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
