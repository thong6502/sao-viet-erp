"""Thực hiện sản xuất — VIỆC KHOÁN của mẻ (§7.1 · §7.2 · §7.2b, 18/09/2026).

Thợ ghi mẻ theo CÔNG VIỆC KHOÁN, không theo công đoạn nữa. Chủ xưởng 18/09/2026: *"dưới sản xuất
sẽ xuất hiện tất cả các công việc khoán ở tổ đó, chỉ chọn được một trong đó… nhớ là phải hiển thị
cả đơn giá, đơn vị tính, ghi chú và danh sách việc phát sinh của việc đó"*.

Ba việc ở đây:
  1. `danh_sach_cua_to` — rổ việc cho form ghi mẻ, kèm việc phát sinh của từng việc. Ô tìm TƯƠNG
     ĐỐI (bỏ dấu, khớp một phần) và HIỆN CHO MỌI TỔ, kể cả tổ chỉ có một việc.
  2. `chuan_hoa_khi_ghi` — kiểm + CHỤP ảnh (tên · đơn vị · đơn giá) của việc khoán và của từng
     việc phát sinh, lúc thợ bấm Ghi mẻ.
  3. `danh_muc_doi` + `cap_nhat_theo_danh_muc` — băng "Danh mục đã đổi so với lúc ghi mẻ": so NỘI
     DUNG với danh mục sống, và chỉ đổi ảnh chụp KHI NGƯỜI BẤM.

**KHÔNG có phép nhân nào ở đây.** Ảnh chụp đơn giá chỉ trả lời "lúc ghi mẻ việc này treo giá bao
nhiêu"; tiền tính ở màn Khoán theo kỳ của kế toán. Việc phát sinh KHÔNG BAO GIỜ cộng vào sản
lượng — không tiến độ, không KCS, không bàn giao, không nhập kho (*"chỗ việc phát sinh như lên
khuôn không cộng vào sản lượng"*).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat_san_luong import SanXuatBatchPhatSinh
from ...repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from ...repositories.tim_khong_dau import bo_dau
from ..lsx_danh_muc_doi import o_lech

#: Ba ô đem so của VIỆC KHOÁN và của MỖI việc phát sinh (§7.2b). Nhãn là câu người đọc trên băng.
_O_SO = (("ten", "tên việc"), ("don_vi", "đơn vị"), ("don_gia", "đơn giá"))


def _anh_chup(ten, don_vi, don_gia) -> dict:
    """Ảnh chụp chuẩn hoá của một dòng — CÙNG hình dạng cho việc khoán và việc phát sinh, để `o_lech`
    so được cả hai bằng một bộ ô."""
    return {
        "ten": (ten or "").strip() or None,
        "don_vi": (don_vi or "").strip() or None,
        "don_gia": None if don_gia is None else float(don_gia),
    }


def _anh_khoan_song(rate) -> dict:
    """Ảnh "nếu ghi bây giờ" của một công việc khoán — đọc danh mục SỐNG."""
    return _anh_chup(rate.ten, rate.unit, rate.unit_price)


def _anh_ps_song(ps) -> dict:
    return _anh_chup(ps.ten, ps.don_vi, ps.don_gia)


def _dong_phat_sinh(ps, dv_ten: dict[str, str]) -> dict:
    """Một dòng việc phát sinh cho form: TÊN · ĐƠN GIÁ · ĐVT — đúng ba thứ chủ xưởng dặn phải hiện."""
    return {
        "id": ps.id,
        "ten": ps.ten,
        "don_gia": float(ps.don_gia),
        "don_vi": ps.don_vi,
        "don_vi_ten": nhan_don_vi(dv_ten, ps.don_vi),
    }


def danh_sach_cua_to(db: Session, *, department_id: int | None, tim: str | None = None) -> list[dict]:
    """Việc khoán của một tổ cho form Ghi mẻ — mỗi dòng kèm việc phát sinh của chính nó.

    Ô tìm lọc TRONG BỘ NHỚ bằng `bo_dau`: danh sách một tổ đo trên DB dev là 1–17 dòng, đi thêm một
    vòng SQL chỉ để lọc 17 dòng thì đắt hơn phép lọc. Khớp cả MÃ và TÊN — xưởng gọi việc bằng mã
    (`KH-0013`) nhiều như gọi bằng tên.

    Đường này chỉ giữ để đọc dữ liệu mẻ cũ; form ghi mẻ mới dùng cấu hình Khoán của Công đoạn.
    """
    rates = CongViecKhoanRepository(db).theo_to(department_id)
    if not rates:
        return []
    dv_ten = DonViDoRepository(db).ten_theo_ma()
    kim = bo_dau(tim)
    ra: list[dict] = []
    for r in rates:
        if kim and kim not in bo_dau(f"{r.ma or ''} {r.ten}"):
            continue
        ra.append({
            "id": r.id,
            "ma": r.ma,
            "ten": r.ten,
            "don_gia": float(r.unit_price),
            "don_vi": r.unit,
            # Cột giữ MÃ đơn vị (`to`, `kem`); tổ đọc câu này nên bày TÊN ("tờ", "bản kẽm").
            "don_vi_ten": nhan_don_vi(dv_ten, r.unit),
            "ghi_chu": r.note,
            "phat_sinh": [_dong_phat_sinh(ps, dv_ten) for ps in r.viec_phat_sinh],
        })
    return ra


def chuan_hoa_khi_ghi(
    db: Session, *, khoan, ten_cong_doan: str | None, phat_sinh: list[dict] | None,
) -> tuple[dict, list[SanXuatBatchPhatSinh]]:
    """Chụp cấu hình Khoán của công đoạn vào mẻ đang ghi.

    Không có cấu hình vẫn ghi sản lượng bình thường. Chỉ khi gửi việc phát sinh mà công đoạn chưa
    cấu hình Khoán mới từ chối, vì không có danh mục nguồn để kiểm và chụp giá.
    """
    if khoan is None:
        if any(r.get("phat_sinh_id") for r in (phat_sinh or [])):
            raise ValueError("Công đoạn chưa cấu hình Khoán nên không thể ghi việc phát sinh.")
        return ({
            "piece_rate_id": None,
            "khoan_cong_doan_id": None,
            "ten_khoan_snapshot": None,
            "don_vi_khoan_snapshot": None,
            "don_gia_khoan_snapshot": None,
        }, [])

    o_snapshot = {
        "piece_rate_id": None,
        "khoan_cong_doan_id": khoan.id,
        "ten_khoan_snapshot": (ten_cong_doan or "").strip() or None,
        "don_vi_khoan_snapshot": khoan.unit,
        "don_gia_khoan_snapshot": float(khoan.unit_price),
    }

    hop_le = {ps.id: ps for ps in khoan.viec_phat_sinh}
    rows: list[SanXuatBatchPhatSinh] = []
    da_co: set[int] = set()
    for r in (phat_sinh or []):
        psid = r.get("phat_sinh_id")
        if not psid:
            continue
        ps = hop_le.get(int(psid))
        if ps is None:
            raise ValueError("Việc phát sinh không thuộc cấu hình Khoán của công đoạn này.")
        if int(psid) in da_co:
            raise ValueError(f'Việc phát sinh "{ps.ten}" bị chọn hai lần.')
        try:
            sl = float(r.get("so_luong"))
        except (TypeError, ValueError):
            raise ValueError(f'Số lượng của "{ps.ten}" không hợp lệ.')
        if sl <= 0:
            raise ValueError(f'Số lượng của "{ps.ten}" phải lớn hơn 0.')
        da_co.add(int(psid))
        anh_ps = _anh_ps_song(ps)
        rows.append(SanXuatBatchPhatSinh(
            phat_sinh_id=ps.id, so_luong=sl,
            ten_snapshot=anh_ps["ten"], don_vi_snapshot=anh_ps["don_vi"],
            don_gia_snapshot=anh_ps["don_gia"],
        ))
    return o_snapshot, rows


def _anh_khoan_cua_me(b) -> dict:
    return _anh_chup(b.ten_khoan_snapshot, b.don_vi_khoan_snapshot, b.don_gia_khoan_snapshot)


def _anh_ps_cua_me(r) -> dict:
    return _anh_chup(r.ten_snapshot, r.don_vi_snapshot, r.don_gia_snapshot)


def nap_doi_chieu(
    db: Session, *, department_id: int | None, ps_rows: list[SanXuatBatchPhatSinh],
) -> tuple[dict, dict]:
    """Nạp MỘT lần cho cả drawer: việc khoán của tổ (kể cả đã ngừng) + việc phát sinh sống mà các
    mẻ trỏ tới. Không nạp sẵn thì `danh_muc_doi` hỏi DB hai lần cho MỖI mẻ — việc chạy vài chục mẻ
    là vài chục truy vấn chỉ để vẽ một băng thường rỗng."""
    repo = CongViecKhoanRepository(db)
    return (
        {int(r.id): r for r in repo.theo_to(department_id, chi_active=False)},
        repo.phat_sinh_theo_id([r.phat_sinh_id for r in ps_rows]),
    )


def danh_muc_doi(
    db: Session, b, ps_rows: list[SanXuatBatchPhatSinh], *, department_id: int | None,
    nap: tuple[dict, dict] | None = None,
) -> list[dict]:
    """Băng "Danh mục đã đổi so với lúc ghi mẻ" (§7.2b) — `[]` = ảnh chụp còn khớp danh mục.

    So NỘI DUNG (`o_lech` → `_chuan` + sai số `1e-9`), KHÔNG so `updated_at`: cùng lý do đã ghi ở
    `lsx_danh_muc_doi` — `piece_rates` có `updated_at` nhưng `cong_viec_khoan_phat_sinh` thì không,
    nên so mốc là im lặng đúng lúc cần nói nhất.

    Đọc việc khoán bằng `chi_active=False`: việc đã NGỪNG DÙNG vẫn phải đọc được tên/giá mới của
    nó, không thì mẻ cũ báo "đã xoá" oan. Việc phát sinh vắng hẳn trong danh mục thì báo *"đã xoá
    khỏi danh mục"* — KHÔNG tự gỡ khỏi mẻ. `nap` = kết quả `nap_doi_chieu` khi gọi cho nhiều mẻ.
    """
    if b.khoan_cong_doan_id:
        from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository

        khoan = SanXuatSanLuongRepository(db).khoan_cong_doan(b.khoan_cong_doan_id)
        if khoan is None:
            return [{
                "nhan": f'{b.ten_khoan_snapshot or "Cấu hình Khoán"} — đã xoá khỏi công đoạn',
                "truong": "khoan_cong_doan", "cu": None, "moi": None, "mat": True,
            }]
        ra: list[dict] = []
        anh_song = _anh_chup(khoan.cong_doan.ten, khoan.unit, khoan.unit_price)
        for o in o_lech(_anh_khoan_cua_me(b), anh_song, _O_SO):
            ra.append({**o, "nhan": f'{khoan.cong_doan.ten} · {o["nhan"]}', "mat": False})
        song = {int(ps.id): ps for ps in khoan.viec_phat_sinh}
        for r in ps_rows:
            ps = song.get(int(r.phat_sinh_id))
            if ps is None:
                ra.append({
                    "nhan": f'{r.ten_snapshot or "Việc phát sinh"} — đã xoá khỏi cấu hình Khoán',
                    "truong": "phat_sinh", "cu": None, "moi": None, "mat": True,
                })
                continue
            for o in o_lech(_anh_ps_cua_me(r), _anh_ps_song(ps), _O_SO):
                ra.append({**o, "nhan": f'{ps.ten} · {o["nhan"]}', "mat": False})
        return ra
    if not b.piece_rate_id:
        return []
    rates, song = nap or nap_doi_chieu(db, department_id=department_id, ps_rows=ps_rows)
    rate = rates.get(int(b.piece_rate_id))
    ra: list[dict] = []
    if rate is None:
        ra.append({"nhan": f'{b.ten_khoan_snapshot or "Công việc khoán"} — đã xoá khỏi danh mục',
                   "truong": "piece_rate", "cu": None, "moi": None, "mat": True})
    else:
        for o in o_lech(_anh_khoan_cua_me(b), _anh_khoan_song(rate), _O_SO):
            ra.append({**o, "nhan": f'{rate.ten} · {o["nhan"]}', "mat": False})

    for r in ps_rows:
        ps = song.get(int(r.phat_sinh_id))
        if ps is None:
            ra.append({"nhan": f'{r.ten_snapshot or "Việc phát sinh"} — đã xoá khỏi danh mục',
                       "truong": "phat_sinh", "cu": None, "moi": None, "mat": True})
            continue
        for o in o_lech(_anh_ps_cua_me(r), _anh_ps_song(ps), _O_SO):
            ra.append({**o, "nhan": f'{ps.ten} · {o["nhan"]}', "mat": False})
    return ra


def cap_nhat_theo_danh_muc(db: Session, *, user, batch_id: int) -> dict:
    """Bấm "Cập nhật theo danh mục": ảnh chụp của mẻ lấy số MỚI, ghi vết vào nhật ký.

    Không bấm thì mẻ giữ số cũ VÔ HẠN và băng treo đó — *hệ không bao giờ tự đổi số dưới chân mẻ
    đã ghi*. Dòng đã bị xoá khỏi danh mục thì giữ nguyên ảnh chụp (không có số mới để lấy) — nó
    vẫn là vết của việc thợ đã làm thật.
    """
    from ...repositories.audit_repo import AuditLogRepository
    from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
    from .thuc_thi import _gate

    sl = SanXuatSanLuongRepository(db)
    b = sl.batch(batch_id)
    if b is None:
        raise ValueError("Không tìm thấy mẻ.")
    cv = sl.cong_viec(b.cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc của mẻ.")
    _gate(db, user, cv)
    if b.khoan_cong_doan_id:
        khoan = sl.khoan_cong_doan(b.khoan_cong_doan_id)
        if khoan is None:
            raise ValueError("Cấu hình Khoán của công đoạn không còn tồn tại.")
        doi: list[str] = []
        moi = _anh_chup(khoan.cong_doan.ten, khoan.unit, khoan.unit_price)
        if o_lech(_anh_khoan_cua_me(b), moi, _O_SO):
            b.ten_khoan_snapshot = moi["ten"]
            b.don_vi_khoan_snapshot = moi["don_vi"]
            b.don_gia_khoan_snapshot = moi["don_gia"]
            doi.append(f"khoan_cong_doan={khoan.id}")
        ps_rows = sl.phat_sinh_cua_batch(b.id)
        song = {int(ps.id): ps for ps in khoan.viec_phat_sinh}
        for r in ps_rows:
            ps = song.get(int(r.phat_sinh_id))
            if ps is None:
                continue
            anh_ps = _anh_ps_song(ps)
            if o_lech(_anh_ps_cua_me(r), anh_ps, _O_SO):
                r.ten_snapshot = anh_ps["ten"]
                r.don_vi_snapshot = anh_ps["don_vi"]
                r.don_gia_snapshot = anh_ps["don_gia"]
                doi.append(f"phat_sinh={ps.id}")
        AuditLogRepository(db).create(
            actor_user_id=getattr(user, "id", None),
            action="san_xuat_me_cap_nhat_danh_muc",
            target=f"san_xuat_batch:{b.id}",
            detail=f"cong_viec={cv.id} " + (" ".join(doi) if doi else "khong_co_gi_lech"),
        )
        db.commit()
        return {
            "cong_viec_id": cv.id, "department_id": cv.department_id,
            "trang_thai": cv.trang_thai, "version": cv.version,
            "batch_id": b.id, "ket_qua_lsx": [],
        }
    if not b.piece_rate_id:
        raise ValueError("Mẻ này chưa khai công việc khoán — không có gì để cập nhật.")

    repo = CongViecKhoanRepository(db)
    rate = next(
        (r for r in repo.theo_to(cv.department_id, chi_active=False)
         if r.id == int(b.piece_rate_id)), None,
    )
    doi: list[str] = []
    if rate is not None:
        moi = _anh_khoan_song(rate)
        if o_lech(_anh_khoan_cua_me(b), moi, _O_SO):
            b.ten_khoan_snapshot = moi["ten"]
            b.don_vi_khoan_snapshot = moi["don_vi"]
            b.don_gia_khoan_snapshot = moi["don_gia"]
            doi.append(f"khoan={rate.id}")

    ps_rows = sl.phat_sinh_cua_batch(b.id)
    song = repo.phat_sinh_theo_id([r.phat_sinh_id for r in ps_rows])
    for r in ps_rows:
        ps = song.get(int(r.phat_sinh_id))
        if ps is None:
            continue
        moi = _anh_ps_song(ps)
        if o_lech(_anh_ps_cua_me(r), moi, _O_SO):
            r.ten_snapshot = moi["ten"]
            r.don_vi_snapshot = moi["don_vi"]
            r.don_gia_snapshot = moi["don_gia"]
            doi.append(f"phat_sinh={ps.id}")

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_me_cap_nhat_danh_muc",
        target=f"san_xuat_batch:{b.id}",
        detail=f"cong_viec={cv.id} " + (" ".join(doi) if doi else "khong_co_gi_lech"),
    )
    db.commit()
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "batch_id": b.id,
        "ket_qua_lsx": [],
    }
