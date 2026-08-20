"""Gợi ý cho một dòng — LỚP MỎNG trên engine cũ + luật thời gian thuần.

Hai việc:
- `goi_y`     : mượn danh sách máy cùng nhóm công đoạn engine cũ đã dựng, để người xếp có chỗ bấm
  chọn. v2 KHÔNG xếp hạng/loại máy theo khổ · số màu · định lượng (spec §6): máy hợp hay không do
  con người tự cân.
- `goi_y_khe` : chấm tối đa ba KHE TRỐNG sớm nhất để xếp (B8) — người bấm một phát là xong thay vì
  tự dò tay. Chỉ dò theo GIỜ (trùng máy · đè khoá · vượt quân số · trong ca · tiền nhiệm · ngày vật
  tư), đúng bộ luật `constraint`, không thêm bất kỳ phán đoán năng-lực máy nào.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from ...models.bai_ghep_cong_doan import BaiGhepCongDoan
from ...models.lsx import LB_THUE_NGOAI
from ...models.xep_lich import NGUON_LSX
from ..lsx_service import thoi_luong_buoc
from ..xep_lich_service import _aware, _naive
from . import constraint as C


def goi_y(service, *, dong_id: int) -> dict:
    """Gợi ý MÁY cho dòng `dong_id` — TỰ tính trên luật v2, KHÔNG mượn `_top_may` engine cũ.

    Khác engine cũ ở hai điểm cốt lõi (spec §6, §12.8):
    - GIỜ XONG tính LIÊN TỤC (`finish = khe + chiếm-máy`), không đi bộ qua ca.
    - KHÔNG cờ `khong_hop_kho`: v2 không kết luận máy hợp khổ/màu/định lượng — "máy đề xuất, người quyết".

    Thuê ngoài đi theo ngày gửi/nhận, không chiếm máy ⇒ không gợi ý máy (danh sách rỗng). Giữ nguyên
    hình dạng `{may_id, khe_trong, finish_neu_xep, han_lui, goi_y_may}`; ba mốc bám-máy để None (UI v2
    chỉ đọc `goi_y_may`).
    """
    core = service.core
    dong = core._get_dong(dong_id)
    if service._la_thue_ngoai(dong):
        return {"may_id": dong.may_id, "khe_trong": None, "finish_neu_xep": None,
                "han_lui": None, "goi_y_may": []}
    som = core._boi_canh_chuoi(dong)[0]          # sàn thời gian (now / bàn giao)
    for f in service.ctx.tien_nhiem_finish(dong):  # + mọi bước tiền nhiệm đã xếp phải xong trước
        fa = _aware(f)
        if fa is not None and (som is None or fa > som):
            som = fa
    return {
        "may_id": dong.may_id,
        "khe_trong": None,
        "finish_neu_xep": None,
        "han_lui": None,
        "goi_y_may": _top_may_v2(service, dong, som=som, exclude_id=dong_id),
    }


def _top_may_v2(service, dong, *, som: datetime, exclude_id: int, top: int = 3) -> list[dict]:
    """Top máy làm được công đoạn, sắp theo GIỜ XONG (liên tục) tăng dần.

    Thời lượng tính LẠI theo TỪNG máy (`thoi_luong_buoc`): tốc độ/chuẩn bị là thuộc tính của MÁY nên
    cùng bước trên hai máy ra hai con số. Khe trống mượn `core._khe_trong` (né việc đã xếp + vùng khoá),
    còn giờ xong theo mô hình v2 chạy liên tục. Tiêu chí PHỤ `cung_gom` (việc liền trước cùng giấy/khổ/
    bộ mực) chỉ phá hoà khi giờ xong bằng nhau.
    """
    core = service.core
    lcd = (
        core._lcd(dong.lsx_cong_doan_id) if dong.nguon == NGUON_LSX
        else service.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
        if dong.bai_ghep_cong_doan_id else None
    )
    if lcd is None:
        return []
    lsx = core.lsx_repo.get(dong.lsx_id) if dong.lsx_id else None
    gom = core._gom_key(lsx)
    ra: list[dict] = []
    for may in core._may_lam_duoc(dong):
        chiem = thoi_luong_buoc(lcd, may, core._sl_tinh(lcd, may))["chiem_may_phut"]
        if chiem <= 0:
            continue                          # máy chưa khai tốc độ → không hứa được giờ xong nào
        khe = core._khe_trong(may.id, som, chiem, exclude_id=exclude_id)
        if khe is None:
            continue
        ra.append({
            "may_id": may.id,
            "may_ten": may.ten,
            "khe_trong": _naive(khe),
            "finish": _naive(C.finish_lien_tuc(khe, chiem)),
            "chiem_may_phut": round(chiem, 2),
            "cung_gom": core._lien_ke_cung_gom(may.id, khe, gom, exclude_id=exclude_id),
        })
    ra.sort(key=lambda d: (d["finish"], not d["cung_gom"]))
    return ra[:top]


def goi_y_khe(service, *, dong_id: int, tu, den, toi_da: int = 3) -> dict:
    """Chấm tối đa `toi_da` khe trống SỚM NHẤT để xếp dòng `dong_id` trong cửa sổ [tu, den] (B8).

    Đã bắt đầu là chạy LIÊN TỤC trên máy cố định (`finish = start + chiếm-máy`) nên khe bắt đầu sớm
    nhất cũng là khe KẾT THÚC sớm nhất — chỉ cần rà các mốc "mở" (đầu ca + ngay sau việc/khoá đã
    chiếm máy + tiền nhiệm vừa xong + ngày vật tư về) theo thứ tự tăng dần, nhận khe đầu tiên không
    vướng luật CHẶN ĐẶT LỊCH, tới khi đủ `toi_da`.

    Chưa chọn máy / chưa tính được thời lượng ⇒ trả rỗng kèm ghi chú (không đoán bừa một khe).
    """
    dong = service.core._get_dong(dong_id)
    if service._la_thue_ngoai(dong):
        return {"khe": [], "ghi_chu": "Bước thuê ngoài đi theo ngày gửi/nhận, không xếp khe máy."}
    if not dong.may_id:
        return {"khe": [], "ghi_chu": "Chọn máy trước rồi hệ mới gợi ý được khe trống."}
    shadow = service._shadow(dong, {})
    dur = service._thoi_luong_v2(shadow)
    chiem = int(dur.get("chiem_may_phut") or 0)
    if dur.get("canh_bao") or chiem <= 0:
        return {"khe": [], "ghi_chu": "Máy chưa khai tốc độ hoặc đơn vị bước chưa quy đổi — "
                                      "bổ sung rồi hệ mới gợi ý được khe."}
    ca = service.ctx.ca_windows()
    khe: list[dict] = []
    for start in _moc_ung_vien(service, dong, shadow, tu, den, ca):
        finish = C.finish_lien_tuc(start, chiem)
        vd = service._van_de_dat_lich(
            shadow, start=start, finish=finish, may_id=shadow.may_id,
            department_id=shadow.department_id, canh_bao=None, exclude_id=dong.id,
        )
        if any(i["muc"] == C.MUC_CHAN_DAT_LICH for i in vd):
            continue
        khe.append({
            "start_at": _naive(start),
            "finish_at": _naive(finish),
            "chiem_may_phut": chiem,
            "canh_bao": [i for i in vd if i["muc"] == C.MUC_CANH_BAO],
        })
        if len(khe) >= toi_da:
            break
    return {"khe": khe, "ghi_chu": None if khe else
            "Không thấy khe trống trong khoảng đang xem — mở rộng cửa sổ hoặc đổi máy."}


def _moc_ung_vien(service, dong, shadow, tu, den, ca) -> list[datetime]:
    """Các mốc bắt đầu ứng viên trong [tu, den], TĂNG DẦN + đã khử trùng.

    Gom mọi thời điểm một khe có thể "mở": đầu mỗi ca từng ngày · ngay sau mỗi việc/vùng-khoá đã
    chiếm máy · lúc tổ vừa rảnh · tiền nhiệm vừa xong · ca đầu ngày vật tư về. Ứng viên ngoài ca /
    còn vướng sẽ bị `_van_de_dat_lich` loại ở vòng chấm — ở đây chỉ cần phủ đủ mốc, không lọc sẵn.
    """
    d0 = datetime.combine(tu, time.min, tzinfo=timezone.utc)
    d1 = datetime.combine(den, time.min, tzinfo=timezone.utc) + timedelta(days=1)
    moc: set[datetime] = set()
    ngay = tu
    while ngay <= den:
        base = datetime.combine(ngay, time.min, tzinfo=timezone.utc)
        for bat_dau, _, _ in ca:
            moc.add(base + timedelta(minutes=int(bat_dau)))
        ngay = ngay + timedelta(days=1)
    for _, f in service.ctx.khoang_may_da_xep(shadow.may_id, dong.id):
        if f is not None:
            moc.add(_aware(f))
    for _, f in service.ctx.khoang_chan_may(shadow.may_id):
        if f is not None:
            moc.add(_aware(f))
    if shadow.department_id:
        for _, f, _n in service.ctx.placements_to(shadow.department_id, dong.id):
            if f is not None:
                moc.add(_aware(f))
    for f in service.ctx.tien_nhiem_finish(shadow):
        if f is not None:
            moc.add(_aware(f))
    ngay_ve = service.ctx.ngay_vat_tu(dong)
    if ngay_ve is not None:
        bat_dau_som = min((b for b, _, _ in ca), default=0)
        moc.add(datetime.combine(ngay_ve, time.min, tzinfo=timezone.utc)
                + timedelta(minutes=int(bat_dau_som)))
    trong = sorted(m for m in moc if d0 <= m < d1)
    # Trần an toàn: cửa sổ hữu hạn nên hiếm khi chạm, chỉ để chặn vòng chấm thoái hoá.
    return trong[:400]
