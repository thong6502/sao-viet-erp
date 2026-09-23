"""Dải ROUTING của lệnh trên bàn tổ (23/09/2026, `docs/design-dai-routing-tren-ban-to.md`).

Bàn tổ lọc `department_id` nên thẻ lệnh chỉ hiện bước của tổ mình. Module này dựng thêm CHUỖI
đầy đủ: tổ thấy mình đứng thứ mấy, bước trước đã ra bao nhiêu và đã giao sang chưa, làm xong thì
hàng đi đâu.

Tách khỏi `board.py` vì file đó đã hơn 1200 dòng và đây là một mặt đọc độc lập.

CHỈ ĐỌC, và đọc từ SNAPSHOT gói (`san_xuat_cong_viec`) — cùng nguyên tắc với cả `board.py`. Thứ
DUY NHẤT lấy từ routing sống là THỨ TỰ (`lsx_cong_doan.thu_tu`), an toàn vì phát hành đã khoá
routing.

Mức lộ ra cho bước của TỔ KHÁC: tên · tổ · trạng thái · kế hoạch/thực tế · đã giao. KHÔNG người,
KHÔNG khoán, KHÔNG mẻ, KHÔNG vật tư, KHÔNG ảnh KCS — và KHÔNG `cong_viec_id`, để FE không có
đường mở drawer việc của tổ khác.

KHÔNG có TRẦN GHI MẺ ở đây, cố ý. `dau_vao.tran_ghi` lấy MIN qua các nhóm nguồn nên phải gọi
`nhom_truoc` → `cong_viec_chang_truoc` (3-4 truy vấn) cho TỪNG bước của tổ; một trang 20 lệnh là
80-160 truy vấn thêm. Xấp xỉ nó bằng `đã nhận × hệ số` thì sai đúng ở bước ghép (nhiều nguồn) —
mà hai con số khác nhau cho CÙNG một khái niệm là nói dối, đúng bài học đã ghi ở
`board.chi_tiet_cong_viec`. Trần ở lại tab Nhận của drawer, nơi nó được tính đủ.

HIỆU NĂNG: mọi truy vấn ở đây gom theo CẢ TRANG (tối đa 20 lệnh) — 5 truy vấn, không nhân theo
lệnh. Đừng gọi `cong_viec_chang_truoc` / `cong_viec_chang_sau` trong vòng lặp.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat_san_luong import BG_DIEU_CHINH, BG_XAC_NHAN
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository

_DA_CHOT = (BG_XAC_NHAN, BG_DIEU_CHINH)


def _gop_trang_thai(tts: list[str]) -> str:
    """Trạng thái của MỘT BƯỚC gộp từ các lần chạy của nó (mg `0254`).

    Yếu nhất thắng: còn lần nào chờ làm thì cả bước là chờ làm. Có lần đang chạy ⇒ đang chạy
    (tổ cần thấy "bước này đã động vào"), rồi mới tới tạm dừng, cuối cùng hết xong mới là xong.
    """
    if "running" in tts:
        return "running"
    if "released" in tts:
        return "released"
    if "paused" in tts:
        return "paused"
    return "completed" if tts else "released"


def _ten_buoc(cvs: list) -> str:
    """Tên bước: bước chưa tách lấy thẳng; bước tách thì bỏ hậu tố "(lần k/N)" của từng lần chạy
    để ô không mang tên của riêng lần chạy đầu."""
    ten = cvs[0].ten_cong_doan or ""
    if len(cvs) > 1 and " (lần " in ten:
        return ten.split(" (lần ")[0]
    return ten


def _cong(vals) -> float | None:
    so = [float(v) for v in vals if v is not None]
    return sum(so) if so else None


def dung_routing(
    db: Session,
    repo: SanXuatRepository,
    *,
    khoa: list[tuple[str, int | None]],
    cv_cua_toi: list,
) -> dict[tuple[str, int | None], list[dict]]:
    """{("lsx", id): [ô, ô, …]} — dải routing của MỌI lệnh trong trang.

    `cv_cua_toi` là đúng các công việc bàn tổ đã lấy được: nó cho biết gói nào và bước nào là của
    mình. Không nhận `department_id` làm tham số vì bàn cấp gom nhiều tổ con — "của tôi" là
    "nằm trong tập việc bàn này đọc được", không phải "trùng một id tổ".
    """
    lsx_ids = {i for loai, i in khoa if loai == "lsx" and i}
    goi_ids = {cv.goi_id for cv in cv_cua_toi if cv.goi_id}
    if not lsx_ids or not goi_ids:
        return {}

    sl = SanXuatSanLuongRepository(db)
    tat_ca = repo.cong_viec_cua_goi_cho_lenh(goi_ids, lsx_ids)
    if not tat_ca:
        return {}
    thu_tu = repo.thu_tu_theo_step_key(lsx_ids)
    phu = repo.bai_ghep_phu_step_key(lsx_ids)
    tot = sl.tong_tot_nhieu({cv.id for cv in tat_ca})
    to_ten = repo.to_ten_nhan({cv.department_id for cv in tat_ca if cv.department_id})
    cv_toi_ids = {cv.id for cv in cv_cua_toi}
    nhan_map = sl.tong_thuc_nhan_nhieu(cv_toi_ids)

    # "Bước này đã giao sang tổ tôi bao nhiêu" — gom NGƯỢC theo công việc NGUỒN, một truy vấn cho
    # cả trang. Chỉ đếm bàn giao ĐÃ CHỐT: `proposed` là đề xuất chưa ai xác nhận, bày nó ra thành
    # "đã giao" là tổ tưởng hàng đã về tay.
    da_giao: dict[int, float] = {}
    for ds in sl.ban_giao_toi_nhieu_dich(cv_toi_ids).values():
        for b in ds:
            if b.trang_thai in _DA_CHOT and b.nguon_cong_viec_id:
                da_giao[b.nguon_cong_viec_id] = (
                    da_giao.get(b.nguon_cong_viec_id, 0.0) + float(b.so_luong or 0)
                )

    # Gom công việc về từng (lsx_id, step_key của LỆNH). Bước chung của bài ghép đứng tên nhiều
    # bước lệnh một lúc, nên nó góp mặt vào dải của TỪNG lệnh nó phủ.
    gom: dict[tuple[int, str], list] = {}
    for cv in tat_ca:
        if cv.bai_ghep_cong_doan_id is not None:
            for sk in phu.get(cv.bai_ghep_cong_doan_id, []):
                lid = thu_tu.get(sk, (None, 0))[0]
                if lid in lsx_ids:
                    gom.setdefault((lid, sk), []).append(cv)
        elif cv.lsx_id in lsx_ids and cv.step_key:
            gom.setdefault((cv.lsx_id, cv.step_key), []).append(cv)

    ra: dict[tuple[str, int | None], list[dict]] = {}
    for lsx_id in lsx_ids:
        buoc = [(sk, cvs) for (lid, sk), cvs in gom.items() if lid == lsx_id]
        buoc.sort(key=lambda x: (thu_tu.get(x[0], (0, 10**6))[1], x[0]))
        dai: list[dict] = []
        for idx, (sk, cvs) in enumerate(buoc, start=1):
            dau = cvs[0]
            cua_toi = [c for c in cvs if c.id in cv_toi_ids]
            giao = sum(da_giao.get(c.id, 0.0) for c in cvs)
            o = {
                "thu_tu": idx,
                "step_key": sk,
                "ten_cong_doan": _ten_buoc(cvs),
                "to_id": dau.department_id,
                "to_ten": to_ten.get(dau.department_id or 0),
                "la_cua_toi": bool(cua_toi),
                "la_kcs_cuoi": any(c.la_kcs_cuoi for c in cvs),
                "trang_thai": _gop_trang_thai([c.trang_thai for c in cvs]),
                "phan_doan_tong": max(c.phan_doan_tong for c in cvs),
                "chay_chung": dau.bai_ghep_cong_doan_id is not None,
                "ke_hoach": _cong(c.so_luong_ra for c in cvs),
                "thuc_te": sum(tot.get(c.id, 0.0) for c in cvs),
                "don_vi": dau.don_vi_ra,
                # Bước NGUỒN: đã giao sang tổ tôi bao nhiêu. None ở bước của chính tôi và ở bước
                # chưa giao gì — tổ phân biệt "xong rồi" với "xong rồi và hàng đã về tay tôi".
                "da_giao_sang_toi": (giao or None) if not cua_toi else None,
                # Bước CỦA TÔI: đã nhận bao nhiêu, theo ĐÚNG đơn vị đầu vào của bước (cùng luật
                # `board._thuc_nhan` — lấy nhầm đơn vị là ra con số bịa).
                "da_nhan": None,
                "cong_viec_id": cua_toi[0].id if cua_toi else None,
            }
            if cua_toi:
                cv = cua_toi[0]
                theo_dv = nhan_map.get(cv.id)
                if theo_dv and cv.don_vi_vao:
                    o["da_nhan"] = theo_dv.get(cv.don_vi_vao)
            dai.append(o)
        if len(dai) > 1:
            ra[("lsx", lsx_id)] = dai
    return ra
