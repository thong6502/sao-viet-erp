"""Thực hiện sản xuất — PHÁT HÀNH CẬP NHẬT & THU HỒI GÓI khi lịch đổi sau phát hành (§4.3).

Bối cảnh: sau phát hành, người lập kế hoạch có thể sửa THỜI GIAN / NGUỒN LỰC (máy) của công việc
CHƯA BẮT ĐẦU ở màn Xếp lịch 2. Thay đổi đó nằm ở lịch sống (`xep_lich_cong_doan`) — là "bản nháp";
chỉ có hiệu lực khi bấm **Phát hành cập nhật** ở đây, khi ấy snapshot của các việc chưa bắt đầu được
CHỤP LẠI theo lịch hiện tại và gói lên một phiên bản mới.

Luật §4.3 (chốt bởi chủ dự án):
  · Chỉ việc CHƯA bắt đầu mới được cập nhật. "Đã bắt đầu" = trạng thái ≠ `released` HOẶC đã có ≥1
    phiên chạy — hai tín hiệu này do `bat_dau` đặt cùng lúc, soi cả hai cho chắc.
  · Mỗi lần cập nhật: tăng `goi.version_hien_tai`, đẻ một `san_xuat_phien_ban(loai=cap_nhat)` kèm
    LÝ DO bắt buộc (giữ lịch sử phiên bản đủ) — KHÔNG xoá phiên bản cũ.
  · Việc chưa bắt đầu được tái chụp (máy + giờ dự kiến) theo lịch hiện tại, gắn `phien_ban_so` mới;
    MỌI phân công trước + thỏa thuận hỗ trợ của nó bị HUỶ ⇒ các tổ phải xác nhận lại.
  · Việc ĐÃ bắt đầu: giữ nguyên snapshot (không đổi lịch/tuyến/tỷ lệ ghép/dữ liệu) — không đụng tới.
  · Khi BẤT KỲ việc nào trong gói đã bắt đầu ⇒ KHÔNG được thu hồi toàn bộ gói (chỉ chặn thu-hồi,
    không chặn cập-nhật phần còn chưa bắt đầu).

TÁI CHỤP thời gian + máy (thứ Xếp lịch 2 đổi được sau phát hành) VÀ **hành lý đọc-để-làm** của
thẻ việc (10/09/2026): đơn vị bản địa · cờ + câu diễn giải sản lượng bước ngoài dòng · kíp chuẩn ·
dải phút chạy · dặn dò của kế hoạch · thẻ quy cách rút gọn. Xem
`docs/superpowers/specs/2026-09-10-ban-to-du-thong-tin-design.md` §8: lệnh phát hành TRƯỚC ngày có
mấy khoá ấy lấy đủ thông tin bằng đúng cửa này (migration cố ý không backfill).

Vẫn KHÔNG đụng: số lượng vào/ra · khoán · định mức vật tư · con dao · checklist KCS · tuyến. Đó là
CAM KẾT đã đóng băng (§4.2) — chúng chảy thẳng vào lương, kho và bàn giao, đọc-sống lại là xê dịch
việc thợ đang làm dở. Hành lý ở trên thì ngược lại: nó chỉ để ĐỌC, mà giữ bản cũ nghĩa là thợ đọc
một câu dặn dò đã bị kế hoạch sửa từ lâu.

Hàm ở đây CHỦ GIAO DỊCH cho nhánh cập-nhật (tự commit); còn `thu_hoi_goi` nằm TRONG giao dịch gỡ
phát hành của `xep_lich_van_de_service` nên KHÔNG commit. Router phát SSE sau khi service trả về.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import (
    CV_PHAT_HANH,
    GOI_DA_THU_HOI,
    GOI_DANG_PHAT_HANH,
    PB_CAP_NHAT,
    SanXuatCongViec,
    SanXuatCongViecLichSu,
    SanXuatGoiPhatHanh,
    SanXuatPhienBan,
)
from ...models.san_xuat_thuc_thi import PC_DA_RUT
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository
from ..dong_giay import ban_do_tram
from . import ho_tro
from .snapshot import _dinh_muc, _hanh_ly, _SoPhatHanh

_LY_DO_RUT = "Phát hành cập nhật — phân công cần xác nhận lại."


# --- Trợ giúp ------------------------------------------------------------------------------
def _refs(repo: SanXuatRepository, nguon: str, id: int) -> tuple[set[int], set[int]]:
    """(lsx_ids, bai_ghep_ids) để tìm gói đang hiệu lực. Bài ghép kéo theo các LSX thành viên."""
    if nguon == "lsx":
        return {id}, set()
    if nguon == "in_ghep":
        return set(repo.lsx_ids_cua_bai_ghep({id})), {id}
    raise ValueError(f"Nguồn không hợp lệ: {nguon!r} (cần 'lsx' hoặc 'in_ghep').")


def _da_bat_dau_ids(
    thuc: SanXuatThucThiRepository, all_cv: list[SanXuatCongViec]
) -> set[int]:
    """Id các công việc ĐÃ bắt đầu: có phiên chạy HOẶC trạng thái đã rời `released`."""
    ids = {cv.id for cv in all_cv}
    da = thuc.cong_viec_co_phien(ids)
    da |= {cv.id for cv in all_cv if cv.trang_thai != CV_PHAT_HANH}
    return da


def _lich_nguon(repo: SanXuatRepository, cv: SanXuatCongViec) -> list[tuple]:
    """MỌI phân đoạn đang xếp của công đoạn nguồn, theo `phan_doan_so`.

    Mỗi phần tử `(may_id, start, finish, phan_doan_so, so_luong)` — xem `repo.lich_lsx_step`."""
    if cv.bai_ghep_cong_doan_id is not None:
        return repo.lich_bg_step(cv.bai_ghep_cong_doan_id)
    if cv.lsx_cong_doan_id is not None:
        dong = repo.lich_lsx_step(cv.lsx_cong_doan_id)
        if dong:
            return dong
        # Lệnh xếp ở Xếp lịch 3: không dòng lịch nào, mốc bước là số dẫn xuất. Trả rỗng ở đây thì
        # "Phát hành cập nhật" coi mọi việc là "lịch đã tách/gộp" và bỏ qua sạch — người điều độ
        # dời giờ cả lệnh xong bấm cập nhật mà bàn tổ không đổi một phút nào.
        from ..xep_lich_3.moc import moc_theo_buoc

        moc = moc_theo_buoc(repo.db, [cv.lsx_id]) if cv.lsx_id else {}
        bd_kt = moc.get(cv.lsx_cong_doan_id)
        if bd_kt:
            return [(None, bd_kt[0], bd_kt[1], 1, None)]
    return []


def _thoi_gian_nguon(repo: SanXuatRepository, cv: SanXuatCongViec):
    """(may_id, start, finish) của ĐÚNG lần chạy mà công việc này đại diện — hoặc `None` khi lịch
    không còn phân đoạn đó.

    Một bước tách N lần chạy đẻ N công việc cùng `step_key` (mg `0254`); khớp bằng `phan_doan_so`.
    Bản trước gọi `thoi_gian_*_step` — hàm đó trả DÒNG ĐẦU TIÊN — nên phát hành cập nhật dập giờ
    và máy của lần 1 lên cả N việc: lần 2 mất ca của mình mà không ai báo.

    Trả `None` (thay vì đoán một dòng khác) khi số lần chạy đã đổi sau phát hành — tách thêm hoặc
    gộp lại. Việc đó giữ nguyên snapshot cũ và được ĐẾM RIÊNG để nói ra, vì lúc ấy tập công việc
    không còn ánh xạ 1-1 với lịch: muốn khớp lại phải thu hồi gói rồi phát hành lần đầu.
    """
    lich = _lich_nguon(repo, cv)
    if not lich:
        return (None, None, None)
    for may_id, start, finish, phan_doan_so, _sl in lich:
        if phan_doan_so == cv.phan_doan_so:
            return (may_id, start, finish)
    return None


def _cd_nguon(db: Session, cv: SanXuatCongViec):
    """Bước KẾ HOẠCH đứng sau công việc (`lsx_cong_doan` / `bai_ghep_cong_doan`) — None nếu mất.

    Snapshot ghim cả hai id nên không phải đọc lại nhãn tiếng Việt để dò ngược.
    """
    if cv.bai_ghep_cong_doan_id is not None:
        from ...models.bai_ghep import BaiGhepCongDoan

        return db.get(BaiGhepCongDoan, cv.bai_ghep_cong_doan_id)
    if cv.lsx_cong_doan_id is not None:
        from ...models.lsx import LsxCongDoan

        return db.get(LsxCongDoan, cv.lsx_cong_doan_id)
    return None


def _tai_chup_hanh_ly(db: Session, cv: SanXuatCongViec, so, tram: dict[str, str]) -> bool:
    """Chụp lại HÀNH LÝ đọc-để-làm của một công việc chưa bắt đầu. Trả True nếu có chụp được.

    Đi qua ĐÚNG `snapshot._hanh_ly` / `snapshot._dinh_muc` mà lần phát hành đầu dùng — chép tay
    một bản thứ hai ở đây là mở đường cho hai lần phát hành ra hai hình dữ liệu khác nhau.

    `ty_le` (phần sản lượng của phân đoạn) suy lại từ CHÍNH cặp số đã ghim: bước tách hai mẻ thì
    mỗi thẻ chỉ gánh phần phút chạy của mẻ mình. Số lượng không đụng tới nên tỷ lệ cũ vẫn đúng.
    """
    cd = _cd_nguon(db, cv)
    if cd is None:
        return False
    hanh_ly = _hanh_ly(so, cd, lsx_id=cv.lsx_id, bai_ghep_id=cv.bai_ghep_id, tram=tram)
    vao_buoc = float(cd.so_luong_vao or 0)
    ty_le = (float(cv.so_luong_vao or 0) / vao_buoc
             if vao_buoc > 0 and (cv.phan_doan_tong or 1) > 1 else 1.0)
    cv.don_vi_vao = hanh_ly["don_vi_vao"]
    cv.don_vi_ra = hanh_ly["don_vi_ra"]
    cv.dinh_muc_json = _dinh_muc(cd, hanh_ly, ty_le)
    cv.ghi_chu = hanh_ly["ghi_chu"]
    cv.quy_cach_json = hanh_ly["quy_cach_json"]
    return True


def _huy_phan_cong_ho_tro(
    db: Session, thuc: SanXuatThucThiRepository, cv: SanXuatCongViec, actor_uid: int | None
) -> tuple[int, int]:
    """Huỷ phân công + thỏa thuận hỗ trợ của một việc chưa bắt đầu. Trả (số PC, số HT) đã huỷ.
    Việc chưa bắt đầu không có khoảng tham gia mở, nên chỉ cần rút dòng roster."""
    n_pc = 0
    for pc in thuc.phan_cong_hoat_dong(cv.id):
        pc.trang_thai = PC_DA_RUT
        pc.ly_do_rut = _LY_DO_RUT
        pc.version += 1
        n_pc += 1
    n_ht = ho_tro.huy_ho_tro_phat_hanh_lai(db, cong_viec_id=cv.id, actor_user_id=actor_uid)
    cv.version += 1
    return n_pc, n_ht


# --- Đọc: thông tin gói (cho UI quyết nút Cập nhật / Thu hồi) --------------------------------
def thong_tin_goi(db: Session, *, nguon: str, id: int) -> dict:
    """Trạng thái gói phát hành của một LSX/bài ghép + lịch sử phiên bản + số việc đã/chưa bắt đầu.

    `co_goi=False` khi chưa phát hành (hoặc lệnh phát hành trước khi có lớp thực hiện). Chỉ đọc."""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return {"co_goi": False}
    all_cv = repo.cong_viec_cua_goi(goi.id)
    so_da = len(_da_bat_dau_ids(thuc, all_cv))
    so_chua = len(all_cv) - so_da
    dang = goi.trang_thai == GOI_DANG_PHAT_HANH
    phien_bans = sorted(goi.phien_bans, key=lambda p: p.so)
    return {
        "co_goi": True,
        "goi_id": goi.id,
        "ma": goi.ma,
        "trang_thai": goi.trang_thai,
        "version_hien_tai": goi.version_hien_tai,
        "so_cong_viec": len(all_cv),
        "so_da_bat_dau": so_da,
        "so_chua_bat_dau": so_chua,
        "cho_phep_cap_nhat": dang and so_chua > 0,
        "cho_phep_thu_hoi": dang and so_da == 0,
        "phien_bans": [
            {
                "so": p.so,
                "loai": p.loai,
                "ly_do": p.ly_do,
                "phat_hanh_by_id": p.phat_hanh_by_id,
                "luc": p.created_at.isoformat() if p.created_at else None,
            }
            for p in phien_bans
        ],
    }


# --- Ghi: phát hành cập nhật (chủ giao dịch) ------------------------------------------------
def phat_hanh_cap_nhat(db: Session, *, nguon: str, id: int, ly_do: str, actor) -> dict:
    """Tái chụp các việc CHƯA bắt đầu theo lịch hiện tại → phiên bản mới (§4.3). Tự commit.

    Chặn nếu chưa có gói / gói đã thu hồi / không còn việc nào chưa bắt đầu. Việc đã bắt đầu giữ
    nguyên; các việc cập nhật bị huỷ phân công + hỗ trợ (buộc tổ xác nhận lại).

    "Tái chụp" gồm máy + giờ VÀ hành lý đọc-để-làm (đơn vị · kíp · phút chạy · dặn dò · quy cách) —
    xem docstring module để biết cái gì cố ý KHÔNG chụp lại."""
    ly_do = (ly_do or "").strip()
    if len(ly_do) < 3:
        raise ValueError("Phát hành cập nhật phải ghi lý do (tối thiểu 3 ký tự).")
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        raise ValueError("Chưa phát hành — không có gói để cập nhật.")
    if goi.trang_thai != GOI_DANG_PHAT_HANH:
        raise ValueError("Gói đã thu hồi — không thể cập nhật.")

    all_cv = repo.cong_viec_cua_goi(goi.id)
    da_bat_dau = _da_bat_dau_ids(thuc, all_cv)
    chua = [cv for cv in all_cv if cv.id not in da_bat_dau]
    if not chua:
        raise ValueError("Mọi công việc trong gói đã bắt đầu — không còn gì để cập nhật.")

    actor_uid = getattr(actor, "id", None)
    new_ver = goi.version_hien_tai + 1
    repo.add(SanXuatPhienBan(
        goi_id=goi.id, so=new_ver, loai=PB_CAP_NHAT, ly_do=ly_do[:500],
        phat_hanh_by_id=actor_uid,
    ))
    goi.version_hien_tai = new_ver
    goi.version += 1

    so_huy_pc = so_huy_ht = 0
    so_lech_phan_doan = 0
    # Hộp số dẫn xuất dùng CHUNG cho cả vòng: nó cache quy cách theo lệnh / theo bài, dựng mới mỗi
    # việc là chạy lại `quy_cach_bien` (bài ghép còn phải `tinh_so_to`) cho từng thẻ.
    so = _SoPhatHanh(db)
    tram = ban_do_tram(db)
    for cv in chua:
        moc = _thoi_gian_nguon(repo, cv)
        if moc is None:                 # lịch đã tách thêm/gộp lại — không còn lần chạy này
            so_lech_phan_doan += 1
            continue
        may_id, start, finish = moc
        _tai_chup_hanh_ly(db, cv, so, tram)
        # CHỤP BẢN CŨ TRƯỚC KHI ĐÈ. Ba dòng dưới sửa đè tại chỗ (cố ý — `cv.id` bị phụ thuộc,
        # phân công, hỗ trợ, batch, bàn giao, KCS trỏ tới), nên không chụp ở đây là bản cũ biến
        # mất vĩnh viễn và không ai trả lời được "v3 hứa bước này chạy lúc mấy giờ".
        db.add(SanXuatCongViecLichSu(
            goi_id=goi.id, phien_ban_so=cv.phien_ban_so, cong_viec_id=cv.id,
            may_id=cv.may_id, du_kien_bat_dau=cv.du_kien_bat_dau,
            du_kien_ket_thuc=cv.du_kien_ket_thuc,
        ))
        if may_id is not None:          # giữ máy cũ nếu lịch mới chưa gán (bước tổ/thuê ngoài)
            cv.may_id = may_id
        cv.du_kien_bat_dau = start
        cv.du_kien_ket_thuc = finish
        cv.phien_ban_so = new_ver
        n_pc, n_ht = _huy_phan_cong_ho_tro(db, thuc, cv, actor_uid)
        so_huy_pc += n_pc
        so_huy_ht += n_ht
    so_cap_nhat = len(chua) - so_lech_phan_doan

    AuditLogRepository(db).create(
        actor_user_id=actor_uid,
        action="san_xuat.phat_hanh_cap_nhat",
        target=f"san_xuat_goi:{goi.id}",
        detail=(f"Cập nhật lịch → phiên bản {new_ver}: tái chụp {so_cap_nhat} việc chưa bắt đầu, "
                f"giữ nguyên {len(da_bat_dau)} việc đã bắt đầu; huỷ {so_huy_pc} phân công + "
                f"{so_huy_ht} hỗ trợ"
                + (f"; {so_lech_phan_doan} việc lệch lần chạy (lịch đã tách/gộp lại) giữ nguyên"
                   if so_lech_phan_doan else "")
                + f". Lý do: {ly_do[:200]}"),
    )
    repo.commit()
    return {
        "goi_id": goi.id,
        "ma": goi.ma,
        "version_hien_tai": new_ver,
        "so_cong_viec_cap_nhat": so_cap_nhat,
        "so_giu_nguyen": len(da_bat_dau),
        "so_huy_phan_cong": so_huy_pc,
        "so_huy_ho_tro": so_huy_ht,
        # >0 ⇒ số lần chạy đã đổi sau phát hành; những việc đó KHÔNG được cập nhật, UI phải nói ra.
        "so_lech_phan_doan": so_lech_phan_doan,
    }


# --- Thu hồi gói (nằm trong giao dịch gỡ-phát-hành — KHÔNG commit) ---------------------------
def co_cong_viec_da_bat_dau(db: Session, *, nguon: str, id: int) -> bool:
    """Gói đang hiệu lực của LSX/bài ghép có việc nào đã bắt đầu? (Chặn thu hồi toàn gói — §4.3.)"""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return False
    return bool(_da_bat_dau_ids(thuc, repo.cong_viec_cua_goi(goi.id)))


def thu_hoi_goi(db: Session, *, nguon: str, id: int, actor) -> int:
    """Thu hồi gói phát hành khi CHƯA việc nào bắt đầu: đánh `da_thu_hoi` (biến khỏi bàn tổ) + huỷ
    phân công/hỗ trợ còn treo. KHÔNG commit — nằm trong giao dịch gỡ-phát-hành của caller. Trả số
    công việc trong gói (0 nếu không có gói). Người gọi phải chặn trước bằng `co_cong_viec_da_bat_dau`."""
    repo = SanXuatRepository(db)
    thuc = SanXuatThucThiRepository(db)
    lsx_ids, bg_ids = _refs(repo, nguon, id)
    goi = repo.goi_hien_tai_cua(lsx_ids, bg_ids)
    if goi is None:
        return 0
    all_cv = repo.cong_viec_cua_goi(goi.id)
    actor_uid = getattr(actor, "id", None)
    for cv in all_cv:
        _huy_phan_cong_ho_tro(db, thuc, cv, actor_uid)
    goi.trang_thai = GOI_DA_THU_HOI
    goi.version += 1
    AuditLogRepository(db).create(
        actor_user_id=actor_uid,
        action="san_xuat.thu_hoi_goi",
        target=f"san_xuat_goi:{goi.id}",
        detail=f"Thu hồi gói phát hành {goi.ma} ({len(all_cv)} công việc) — gỡ phát hành khi chưa việc nào bắt đầu.",
    )
    repo.flush()
    return len(all_cv)
