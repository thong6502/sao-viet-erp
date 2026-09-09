"""Thứ tự xếp & sàn thời gian THEO ROUTING — tầng chung cho `auto` (tự xếp) và `suggestion` (gợi ý).

Vì sao có file này (bệnh cũ, 21/08/2026):

1. `tu_xep` duyệt các bước theo `source_thu_tu`. Nhưng cạnh phụ thuộc được phép NGƯỢC `thu_tu` —
   `replace_routing` chỉ chặn tự-phụ-thuộc · khác đơn hàng · vòng lặp, KHÔNG đòi tiền nhiệm phải
   đứng trước. LSX26-0020 là ví dụ thật: chuỗi là B1 → B6 → B2 → B3 → B4 → B5 trong khi `thu_tu`
   nói B6 chạy cuối. Duyệt theo `thu_tu` thì tới lượt B2, tiền nhiệm B6 của nó chưa có giờ.
2. `ctx.tien_nhiem_finish` CHỈ đếm tiền nhiệm ĐÃ có `finish_at`. Lệnh còn trắng ⇒ trả rỗng ⇒ mọi
   bước cùng rơi về sàn "bây giờ" và chồng lên nhau ở mép trái Gantt, mũi tên chỉ ngược.

Hai chữa: xếp theo THỨ TỰ TÔ-PÔ của DAG (`thu_tu_xep`), và sàn thời gian ƯỚC luôn giờ xong của
tiền nhiệm chưa xếp (`tien_nhiem_finish`) bằng chính engine thời lượng.

RANH GIỚI CỐ Ý — **ước để GỢI Ý, thật để CHẶN**: giờ ước chỉ dùng làm SÀN (đẩy đề xuất xuống cho
đúng routing). Luật chặn `sai_tien_nhiem` vẫn chỉ soi tiền nhiệm ĐÃ có giờ thật — không ai bị chặn
vì một con số máy tự đoán.

Bài ghép (`nguon = in_ghep`) không có bảng phụ thuộc ⇒ mọi hàm ở đây trả rỗng, người gọi tự rơi về
thứ tự `thu_tu` như cũ.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from ...models.lsx import LB_TO, LsxCongDoan, LsxCongDoanPhuThuoc
from ...models.xep_lich import XepLichCongDoan
from ..xep_lich_service import _aware
from . import constraint as C


# ============================ ĐỌC ĐỒ THỊ ============================
def canh_tien_nhiem(db, step_ids) -> dict[int, list[int]]:
    """`{buoc_sau_id: [buoc_truoc_id]}` — MỘT truy vấn cho cả tập, không N+1."""
    ids = [i for i in dict.fromkeys(step_ids) if i]
    if not ids:
        return {}
    ra: dict[int, list[int]] = {}
    for sau, truoc in db.execute(
        select(LsxCongDoanPhuThuoc.buoc_sau_id, LsxCongDoanPhuThuoc.buoc_truoc_id)
        .where(LsxCongDoanPhuThuoc.buoc_sau_id.in_(ids))
    ).all():
        ra.setdefault(sau, []).append(truoc)
    return ra


def _dong_cua_step(db, step_id: int) -> XepLichCongDoan | None:
    """Dòng lịch của một bước routing. Bước chưa được đưa vào kế hoạch ⇒ None (không ước hộ)."""
    return db.execute(
        select(XepLichCongDoan).where(XepLichCongDoan.lsx_cong_doan_id == step_id).limit(1)
    ).scalars().first()


def _ten_buoc(db, step_id: int) -> str:
    b = db.get(LsxCongDoan, step_id)
    if b is None:
        return "bước trước"
    return f"B{int(b.thu_tu or 0) + 1} {b.ten}" if b.ten else f"B{int(b.thu_tu or 0) + 1}"


# ============================ THỨ TỰ TÔ-PÔ ============================
def thu_tu_xep(rows, canh_dong: dict[int, list[int]]) -> list:
    """`rows` sắp theo thứ tự tô-pô của DAG; hoà nhau thì theo `(source_thu_tu, phân đoạn, id)`.

    Kahn + luôn bốc ứng viên "nhỏ" nhất ⇒ DAG trùng với `thu_tu` (đại đa số lệnh) cho ra ĐÚNG thứ
    tự cũ, không đảo lung tung. Còn sót vòng (đáng lẽ `_kiem_chu_trinh_phu_thuoc` đã chặn) thì phần
    kẹt được nối vào cuối theo `thu_tu` thay vì ném lỗi — tự xếp không được phép chết vì dữ liệu cũ.

    Các LẦN CHẠY của cùng một bước đứng ngang hàng trong DAG (chung `source_thu_tu`, không có cạnh
    nối nhau), nên `phan_doan_so` là thứ phá hoà: `trung_lan_chay` đẩy chúng nối đuôi theo ĐÚNG thứ
    tự được xếp, mà lần chạy 2 xếp trước lần chạy 1 thì nhãn "2/3" lại nằm ở khe sớm hơn "1/3".
    """
    def khoa(r):
        return (int(getattr(r, "source_thu_tu", 0) or 0),
                int(getattr(r, "phan_doan_so", 1) or 1), r.id)

    con = {r.id: r for r in rows}
    con_lai = {rid: [p for p in canh_dong.get(rid, []) if p in con] for rid in con}
    ra: list = []
    while con_lai:
        san_sang = sorted((con[rid] for rid, ps in con_lai.items() if not ps), key=khoa)
        if not san_sang:                                   # vòng — nối phần kẹt vào cuối
            ra.extend(sorted((con[rid] for rid in con_lai), key=khoa))
            break
        r = san_sang[0]
        ra.append(r)
        con_lai.pop(r.id)
        for ps in con_lai.values():
            if r.id in ps:
                ps.remove(r.id)
    return ra


def _dong_theo_step(db, step_ids) -> dict[int, list[tuple]]:
    """`{step_id: [(dong_id, phân đoạn, may_id, department_id)]}` — MỘT bước có thể mang NHIỀU dòng
    (đã tách lần chạy), nên map phải là danh sách. Tra một truy vấn cho cả tập.

    Kèm tài nguyên + số phân đoạn vì `_chuoi_lan_chay` cần đúng bấy nhiêu để biết mấy mẻ này là một
    dây nối tiếp hay là mấy dây chạy song song."""
    ids = [i for i in dict.fromkeys(step_ids) if i]
    if not ids:
        return {}
    ra: dict[int, list[tuple]] = {}
    for did, sid, pd, may, dept in db.execute(
        select(XepLichCongDoan.id, XepLichCongDoan.lsx_cong_doan_id,
               XepLichCongDoan.phan_doan_so, XepLichCongDoan.may_id,
               XepLichCongDoan.department_id)
        .where(XepLichCongDoan.lsx_cong_doan_id.in_(ids))
    ).all():
        ra.setdefault(sid, []).append((did, int(pd or 1), may, dept))
    return ra


def _chuoi_lan_chay(dong: list[tuple]) -> list[list[int]]:
    """Các dòng của MỘT bước → những DÂY nối tiếp, mỗi dây sắp theo số lần chạy.

    Các mẻ trên CÙNG tài nguyên buộc phải nối đuôi (`constraint.trung_lan_chay`) nên chúng là MỘT
    dây: mẻ 1 → mẻ 2 → mẻ 3. Chia sang HAI MÁY khác nhau thì hai mẻ chạy song song thật (cách xưởng
    vẫn dùng để về đích sớm) — mỗi máy một dây riêng. Chưa gán tài nguyên thì xếp chung một dây:
    tách lần chạy vốn thừa kế máy/tổ của gốc, nên mặc định là nối tiếp.
    """
    nhom: dict[tuple, list[tuple]] = {}
    for d in dong:
        _, _, may, dept = d
        nhom.setdefault(("may", may) if may else ("to", dept), []).append(d)
    return [[x[0] for x in sorted(v, key=lambda x: (x[1], x[0]))] for v in nhom.values()]


def canh_dong_day_du(db, rows) -> dict[int, list[int]]:
    """`{dong_id: [dong_id tiền nhiệm]}` — tiền nhiệm tra TOÀN BỘ dòng của bước trước, kể cả dòng
    KHÔNG nằm trong `rows` (ngoài cửa sổ Gantt, đã phát hành, đang khoá).

    Dùng cho VIEW: mũi tên trên Gantt phải là cạnh THẬT của DAG routing. Trước đây màn tự nối
    `buoc_thu_tu` liền kề thành một hàng dọc nên hai gốc song song (Ghi kẽm CTP · Cắt tờ cùng chảy
    vào In) bị vẽ thành nối tiếp nhau.

    Bước bị TÁCH lần chạy nối thành MỘT DÂY, không toả nan hoa: cạnh routing chỉ chạm mẻ ĐẦU của
    bên nhận và mẻ CUỐI của bên cho, còn giữa các mẻ là cạnh 1→2→3. Bảng phụ thuộc chỉ khai ở mức
    BƯỚC nên trước đây mọi mẻ của bước sau nhận cạnh từ mọi mẻ của bước trước — Gantt vẽ ra một
    chùm nan hoa (09/09/2026: Dán bắn ba mũi tên sang ba lần chạy Đóng gói) trong khi đường đi thật
    của công việc chỉ là một dây, và các mẻ nay buộc phải nối đuôi nhau (`trung_lan_chay`). Dây
    dựng theo TÀI NGUYÊN nên chia mẻ sang hai máy vẫn ra hai dây song song — xem `_chuoi_lan_chay`.

    Dòng bài ghép (`lsx_cong_doan_id` NULL) không có bảng phụ thuộc ⇒ vắng mặt trong kết quả."""
    theo_step: dict[int, list] = {}
    for r in rows:
        if r.lsx_cong_doan_id:
            theo_step.setdefault(r.lsx_cong_doan_id, []).append(r)
    if not theo_step:
        return {}
    canh = canh_tien_nhiem(db, theo_step.keys())
    dong_truoc = _dong_theo_step(db, (t for truocs in canh.values() for t in truocs))
    ra: dict[int, list[int]] = {}
    for sau_step, rs in theo_step.items():
        # Cửa RA của bước trước = mẻ CUỐI của từng dây: mẻ cuối xong thì cả bước mới xong.
        truoc_ids = sorted({c[-1] for t in canh.get(sau_step, [])
                            for c in _chuoi_lan_chay(dong_truoc.get(t, []))})
        for chuoi in _chuoi_lan_chay(
            [(r.id, int(getattr(r, "phan_doan_so", 1) or 1), r.may_id, r.department_id)
             for r in rs]
        ):
            dau = [i for i in truoc_ids if i != chuoi[0]]
            if dau:
                ra[chuoi[0]] = dau
            for truoc, sau in zip(chuoi, chuoi[1:]):
                ra[sau] = [truoc]
    return ra


def canh_giua_dong(db, rows) -> dict[int, list[int]]:
    """`{dong_id: [dong_id tiền nhiệm]}` — chỉ giữ cạnh mà CẢ HAI đầu nằm trong `rows`.

    Cạnh trỏ ra ngoài tập (bước của LSX khác cùng đơn, hoặc bước đã xếp/đang khoá) không tham gia
    xếp thứ tự — chúng đã có giờ thật nên `tien_nhiem_finish` lo, khỏi ràng buộc thêm.
    """
    trong_tap = {r.id for r in rows}
    ra: dict[int, list[int]] = {}
    for sau, truocs in canh_dong_day_du(db, rows).items():
        con = [i for i in truocs if i in trong_tap]
        if con:
            ra[sau] = con
    return ra


# ============================ SÀN THỜI GIAN ============================
def san_co_ban(service, dong, ca) -> datetime:
    """Sàn KHÔNG kể tiền nhiệm: `max(bây giờ · bàn giao sang SX, ca đầu ngày vật tư hứa về)`."""
    som = service.core._boi_canh_chuoi(dong)[0]
    ngay_ve = service.ctx.ngay_vat_tu(dong)
    if ngay_ve is not None:
        bat_dau_som = min((b for b, _, _ in ca), default=C.GIO_BAT_DAU * 60)
        nguong = datetime(ngay_ve.year, ngay_ve.month, ngay_ve.day,
                          tzinfo=timezone.utc) + timedelta(minutes=int(bat_dau_som))
        if som is None or nguong > som:
            som = nguong
    return som


def tien_nhiem_finish(service, dong, ca) -> tuple[list[datetime], list[str]]:
    """(giờ xong của MỌI tiền nhiệm, tên các bước phải ƯỚC vì chưa xếp).

    Gộp hai nguồn: `ctx.tien_nhiem_finish` (sàn in-ghép + tiền nhiệm ĐÃ có giờ) và phần bù ở đây —
    tiền nhiệm chưa xếp thì chạy tiếp một lượt ước dọc chuỗi. Trả kèm TÊN để UI nói thật là giờ này
    còn đang chờ ai, đừng để người xếp tưởng đó là giờ chắc.
    """
    finishes = [f for f in (_aware(x) for x in service.ctx.tien_nhiem_finish(dong)) if f]
    step_id = getattr(dong, "lsx_cong_doan_id", None)
    if not step_id:
        return finishes, []
    cho: list[str] = []
    memo: dict[int, datetime | None] = {}
    for pid in canh_tien_nhiem(service.db, [step_id]).get(step_id, []):
        prow = _dong_cua_step(service.db, pid)
        if prow is None or prow.finish_at is not None:
            continue                                       # đã có giờ thật ⇒ ctx đếm rồi
        f = _uoc_xong(service, prow, ca, memo, set())
        if f is not None:
            finishes.append(f)
            cho.append(_ten_buoc(service.db, pid))
    return finishes, cho


def _uoc_xong(service, dong, ca, memo: dict, dang_di: set) -> datetime | None:
    """Ước giờ XONG của một bước chưa xếp = sàn của chính nó (đã kể tiền nhiệm) + thời lượng trung
    bình. Chưa tính được thời lượng ⇒ trả về đúng cái sàn (vẫn đẩy được bước sau xuống, không hứa
    thêm gì). Vòng lặp ⇒ None, để `_kiem_chu_trinh_phu_thuoc` lo phần báo lỗi."""
    if dong.finish_at is not None:
        return _aware(dong.finish_at)
    if dong.id in memo:
        return memo[dong.id]
    if dong.id in dang_di:
        return None
    dang_di.add(dong.id)
    san = san_co_ban(service, dong, ca)
    step_id = getattr(dong, "lsx_cong_doan_id", None)
    if step_id:
        for pid in canh_tien_nhiem(service.db, [step_id]).get(step_id, []):
            prow = _dong_cua_step(service.db, pid)
            if prow is None:
                continue
            f = _uoc_xong(service, prow, ca, memo, dang_di)
            if f is not None and (san is None or f > san):
                san = f
    chiem = _chiem_uoc(service, dong)
    ra = (C.finish_lien_tuc(san, chiem, service.ctx.nghi_windows())
          if (san is not None and chiem > 0) else san)
    dang_di.discard(dong.id)
    memo[dong.id] = ra
    return ra


def _chiem_uoc(service, dong) -> int:
    """Thời lượng dùng để ƯỚC. Bước chạy máy mà CHƯA chọn máy vẫn phải ước được — mượn tạm máy đầu
    tiên làm được bước đó, vì bỏ trắng thì bước sau lại rơi về "bây giờ" đúng như bệnh cũ."""
    d = service._thoi_luong_v2(service._shadow(dong, {})) or {}
    chiem = int(d.get("chiem_may_phut") or 0)
    if chiem > 0 or getattr(dong, "may_id", None):
        return chiem
    if getattr(dong, "loai_buoc", None) == LB_TO:
        return 0                                           # không dính máy — thiếu là thiếu thật
    for may in service.core._may_lam_duoc(dong):
        d2 = service._thoi_luong_v2(service._shadow(dong, {"may_id": may.id})) or {}
        c2 = int(d2.get("chiem_may_phut") or 0)
        if c2 > 0:
            return c2
    return 0
