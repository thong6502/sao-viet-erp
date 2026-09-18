"""Tab SẢN LƯỢNG của Bàn tổ (spec 2026-09-14 §6).

Trả lời *"từ ngày này tới ngày kia, tổ (và các tổ trực thuộc) làm ra bao nhiêu, cho lệnh nào, ai
được bao nhiêu"*. Bảng mở ba tầng: LỆNH/BÀI GHÉP → CÔNG ĐOẠN (tốt · hỏng theo đơn vị của mẻ) →
NGƯỜI (đã chốt · tạm tính · nhãn hỗ trợ chéo).

Phạm vi theo dòng quyền tổ của người xem, trong VÙNG của nút đang mở (`QuyenTo.pham_vi_ban`):
  · tổ thấy TRỌN → số của mẻ + mọi dòng chia;
  · tổ chỉ thấy CỦA TÔI → không có tầng người, số là phần ĐÃ CHỐT của chính mình (bản nháp công nhân
    chưa được xem, §12.3).

Ngày = ngày BẮT ĐẦU mẻ theo giờ xưởng. Không bao giờ cộng lẫn đơn vị: mọi tổng là danh sách theo
đơn vị. Lọc · phân trang · cộng tổng ở máy chủ.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...models.san_xuat_phan_bo import PB_DA_CHOT
from ...models.user import User
from ...repositories.san_xuat_san_luong_to_repo import SanXuatSanLuongToRepository
from ..gio_xuong import thuc_te_hien_thi, ve_gio_xuong, ve_utc_that
from .board import _nhan_vien_id, _pham_vi_doc

CO_TRANG_MAC_DINH = 20
KHOANG_TOI_DA = 366  # ngày — chặn một cú lọc cả chục năm kéo sập bảng mẻ


def _moc_utc(ngay: date) -> datetime:
    """Nửa đêm đầu `ngay` theo giờ xưởng → UTC thật (thang của `san_xuat_batch.bat_dau`)."""
    return ve_utc_that(datetime(ngay.year, ngay.month, ngay.day, tzinfo=timezone.utc))


def _ngay_xuong(dt: datetime | None) -> date | None:
    d = ve_gio_xuong(dt)
    return d.date() if d is not None else None


def _cong(bang: dict, don_vi: str | None, **so: float) -> None:
    dong = bang.setdefault(don_vi, {k: 0.0 for k in so})
    for k, v in so.items():
        dong[k] = dong.get(k, 0.0) + float(v or 0)


def _ra_ds(bang: dict) -> list[dict]:
    return [{"don_vi": dv, **{k: round(v, 3) for k, v in so.items()}} for dv, so in bang.items()]


def san_luong(
    db: Session, user: User, *, team_id: int, tu: date | None = None, den: date | None = None,
    to_id: int | None = None, tim: str | None = None, trang: int = 1,
    co_trang: int = CO_TRANG_MAC_DINH,
) -> dict:
    q, _ = _pham_vi_doc(db, user, team_id)
    hom_nay = ve_gio_xuong(datetime.now(timezone.utc)).date()
    den = den or hom_nay
    tu = tu or den.replace(day=1)
    if tu > den:
        raise ValueError("Từ ngày phải trước hoặc bằng đến ngày.")
    if (den - tu).days >= KHOANG_TOI_DA:
        raise ValueError(f"Khoảng lọc tối đa {KHOANG_TOI_DA} ngày.")
    co_trang = max(1, min(int(co_trang or CO_TRANG_MAC_DINH), 100))
    trang = max(1, int(trang or 1))

    tron, rieng = q.pham_vi_ban(team_id)
    # Ô "Đơn vị": các nút trong vùng người này thấy được, theo thứ tự cây — lọc thu về cây con của nút chọn.
    thay = tron | rieng
    cac_to = [
        {"id": did, "ten": q.cay.ten.get(did, ""), "cap": cap}
        for did, cap in q.cay.thu_tu() if did in thay
    ]
    if to_id is not None:
        if to_id not in thay:
            raise PermissionError("Ngoài phạm vi tổ được phép xem.")
        vung = q.cay.vung(to_id)
        tron, rieng = tron & vung, rieng & vung
    nv_id = _nhan_vien_id(db, user) if rieng else None

    repo = SanXuatSanLuongToRepository(db)
    moc_tu, moc_den = _moc_utc(tu), _moc_utc(den + timedelta(days=1))
    loc = {"tu": moc_tu, "den": moc_den}

    khoa, tong_nguon = repo.trang_nguon(
        tron=tron, rieng=rieng, employee_id=nv_id, tim=tim, trang=trang, co_trang=co_trang, **loc,
    )
    me = repo.me_cua_nguon(khoa, tron=tron, rieng=rieng, employee_id=nv_id, **loc)
    batch_ids = {b.id for b, _ in me}
    dong_chia = repo.dong_chia(batch_ids)
    co_chia = repo.batch_co_ban_chia(batch_ids)
    nhan = repo.nhan_nguon(khoa)
    ten_nv = repo.ten_nhan_vien({d.employee_id for *_, d in dong_chia})

    dong_theo_me: dict[int, list] = {}
    for bid, tt, dv, d in dong_chia:
        dong_theo_me.setdefault(bid, []).append((tt, dv, d))

    # Gom: nguồn → công việc. Công việc của tổ thấy trọn lấy số mẻ; tổ "của tôi" lấy phần mình.
    nguon: dict[tuple, dict] = {k: {"cd": {}, "me": 0, "dau": None, "cuoi": None} for k in khoa}
    for b, cv in me:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id is not None else ("lsx", cv.lsx_id)
        n = nguon.get(k)
        if n is None:
            continue
        ngay = _ngay_xuong(b.bat_dau)
        n["dau"] = ngay if n["dau"] is None or (ngay and ngay < n["dau"]) else n["dau"]
        n["cuoi"] = ngay if n["cuoi"] is None or (ngay and ngay > n["cuoi"]) else n["cuoi"]
        la_tron = cv.department_id in tron
        c = n["cd"].setdefault(cv.id, {
            "cong_viec_id": cv.id, "ten_cong_doan": cv.ten_cong_doan, "to_id": cv.department_id,
            "to_ten": q.cay.ten.get(cv.department_id, ""), "cua_toi": not la_tron,
            "so_me": 0, "chua_chia": 0, "_sl": {}, "_toi": {}, "_nguoi": {},
            "_dau": b.bat_dau,
        })
        c["so_me"] += 1
        n["me"] += 1
        if la_tron:
            _cong(c["_sl"], b.don_vi, tot=b.tot, hong=b.hong)
            if b.id not in co_chia:
                c["chua_chia"] += 1
            for tt, dv, d in dong_theo_me.get(b.id, []):
                khoa_ng = (d.employee_id, dv, bool(d.la_ho_tro))
                chot = tt == PB_DA_CHOT
                _cong(c["_nguoi"], khoa_ng,
                      da_chot=d.so_luong_tra_luong if chot else 0,
                      tam_tinh=0 if chot else d.so_luong_tra_luong)
        else:
            for tt, dv, d in dong_theo_me.get(b.id, []):
                if tt == PB_DA_CHOT and d.employee_id == nv_id:
                    _cong(c["_toi"], dv, da_chot=d.so_luong_tra_luong)

    lenh = []
    for k in khoa:
        n = nguon[k]
        ma, ten = nhan.get(k, ("", ""))
        sl_nguon: dict = {}
        toi_nguon: dict = {}
        cds = []
        for c in sorted(n["cd"].values(), key=lambda x: (x["_dau"], x["cong_viec_id"])):
            for dv, so in c["_sl"].items():
                _cong(sl_nguon, dv, **so)
            for dv, so in c["_toi"].items():
                _cong(toi_nguon, dv, **so)
            nguoi = [
                {"employee_id": eid, "ho_ten": ten_nv.get(eid, f"#{eid}"), "don_vi": dv,
                 "la_ho_tro": ht, "da_chot": round(so["da_chot"], 3),
                 "tam_tinh": round(so["tam_tinh"], 3)}
                for (eid, dv, ht), so in c["_nguoi"].items()
            ]
            nguoi.sort(key=lambda x: (x["la_ho_tro"], -(x["da_chot"] + x["tam_tinh"]), x["ho_ten"]))
            cds.append({
                "cong_viec_id": c["cong_viec_id"], "ten_cong_doan": c["ten_cong_doan"],
                "to_id": c["to_id"], "to_ten": c["to_ten"], "cua_toi": c["cua_toi"],
                "so_me": c["so_me"], "chua_chia": c["chua_chia"],
                "san_luong": _ra_ds(c["_sl"]), "phan_cua_toi": _ra_ds(c["_toi"]),
                "nguoi": [] if c["cua_toi"] else nguoi,
            })
        lenh.append({
            "nguon_loai": k[0], "nguon_id": k[1], "ma": ma, "ten": ten,
            "so_me": n["me"], "ngay_dau": n["dau"], "ngay_cuoi": n["cuoi"],
            "san_luong": _ra_ds(sl_nguon), "phan_cua_toi": _ra_ds(toi_nguon),
            "cong_doan": cds,
        })

    tong_tron = repo.tong_tron(tron=tron, tim=tim, **loc)
    tong_toi = repo.tong_cua_toi(tron=tron, rieng=rieng, employee_id=nv_id, tim=tim, **loc)
    return {
        "team_id": team_id, "tu": tu, "den": den, "to_id": to_id,
        "trang": trang, "co_trang": co_trang, "tong_lenh": tong_nguon,
        "co_pham_vi_tron": bool(tron), "co_pham_vi_rieng": bool(rieng),
        "cac_to": cac_to,
        "tong": [{"don_vi": dv, "tot": round(t, 3), "hong": round(h, 3), "so_me": n}
                 for dv, t, h, n in tong_tron],
        "tong_cua_toi": [{"don_vi": dv, "da_chot": round(t, 3)} for dv, t in tong_toi],
        "lenh": lenh,
        "cap_nhat_luc": thuc_te_hien_thi(datetime.now(timezone.utc)),
    }
