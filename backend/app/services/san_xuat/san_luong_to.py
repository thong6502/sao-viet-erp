"""Tab SẢN LƯỢNG của Bàn tổ (spec 2026-09-14 §6, sửa 18/09/2026 §7.3b).

Trả lời *"từ ngày này tới ngày kia, tổ (và các tổ trực thuộc) làm ra bao nhiêu, cho lệnh nào, ai
có mặt"*. Bảng mở ba tầng: LỆNH/BÀI GHÉP → CÔNG ĐOẠN → MẺ (kèm danh sách người tham gia).

**Mẻ có đúng MỘT chủ** — tổ của bước. Chuỗi khai là *tổ → công đoạn → việc khoán → mẻ*, nên mẻ
không bao giờ thuộc hai tổ. Tổ khác có người trong mẻ thì là KHÁCH, và bảng chia hai mục:

  · **MẺ CỦA TỔ** — vào dòng tổng;
  · **NGƯỜI CỦA TỔ ĐI LÀM Ở TỔ KHÁC** — hiện ĐỦ con số của mẻ (cùng một số với tổ chủ, không
    400/600) nhưng KHÔNG cộng vào tổng.

Nhờ chỉ cộng mục đầu mà dòng tổng của cả 8 tổ ghép lại ra đúng sản lượng xưởng, không mẻ nào bị
đếm hai lượt.

⚠️ 18/09/2026 (mg `0322`): tầng NGƯỜI kiểu "ai được bao nhiêu" (đã chốt / tạm tính / chưa chia) gỡ
hẳn cùng engine chia sản lượng — chủ xưởng: *"ghi nhận thế thôi, đừng có chia bất cứ gì"*. Còn lại
là DANH SÁCH người tham gia, không số phút của ai (chốt ý 13).

Ngày = ngày BẮT ĐẦU mẻ theo giờ xưởng. Không bao giờ cộng lẫn đơn vị: mọi tổng là danh sách theo
đơn vị. Lọc · phân trang · cộng tổng ở máy chủ.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...models.user import User
from ...repositories.san_xuat_san_luong_to_repo import CuaSoGiup, SanXuatSanLuongToRepository
from ..gio_xuong import thuc_te_hien_thi, ve_gio_xuong, ve_utc_that
from .board import _nhan_vien_id, _pham_vi_doc
from .nguoi_trong_me import nguoi_theo_me

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
    # Tập tổ "của mình" để phân mục chủ/khách — mẻ thuộc tổ ngoài tập này là mẻ khách.
    cua_minh = tron | rieng

    repo = SanXuatSanLuongToRepository(db)
    moc_tu, moc_den = _moc_utc(tu), _moc_utc(den + timedelta(days=1))
    loc = {"tu": moc_tu, "den": moc_den}
    # Người của tổ sang giúp tổ khác qua HỖ TRỢ CHÉO không có khoảng tham gia (xem `nguoi_trong_me`)
    # — mẻ khách của họ lọc theo NGÀY xưởng của thỏa thuận, quy ra hai mốc UTC ở đây.
    giup = [
        CuaSoGiup(cv_id, eid, dep, _moc_utc(ngay), _moc_utc(ngay + timedelta(days=1)))
        for cv_id, eid, dep, ngay in repo.ho_tro_trong_khoang(tron | rieng, tu, den)
    ]

    khoa, tong_nguon = repo.trang_nguon(
        tron=tron, rieng=rieng, employee_id=nv_id, tim=tim, trang=trang, co_trang=co_trang,
        giup=giup, **loc,
    )
    me = repo.me_cua_nguon(khoa, tron=tron, rieng=rieng, employee_id=nv_id, giup=giup, **loc)
    nhan = repo.nhan_nguon(khoa)
    # AI CÓ MẶT — suy lúc đọc (khoảng tham gia + hỗ trợ chéo), gộp truy vấn cho cả trang (§7.3b luật 2).
    theo_me = nguoi_theo_me(db, [b.id for b, _ in me])
    to_nguoi = {n["department_id"] for ds in theo_me.values() for n in ds if n["department_id"]}
    ten_to = repo.ten_to(to_nguoi | {cv.department_id for _, cv in me if cv.department_id})

    def _nguoi_cua(batch_id: int, chu_to: int | None, la_khach: bool) -> list[dict]:
        # Nhãn tổ gốc cho "người ngoài" — tổ trưởng cần biết ngay ai là người mình, ai sang giúp
        # (§7.3b luật 2); người nhà thì khỏi dán nhãn cho đỡ rối. "Người ngoài" tính theo mục:
        #   · MẺ CỦA TỔ: không thuộc tổ CHỦ mẻ (xem cả xưởng vẫn biết ai từ tổ nào sang);
        #   · mục KHÁCH: không thuộc vùng ĐANG XEM — tab tổ cán thấy "a, b (Tổ bế) · c", đúng ví dụ
        #     của chủ xưởng; theo tổ chủ thì nhãn lại dán lên chính người của mình.
        def _ngoai(d: int | None) -> bool:
            if not d:
                return False
            return d not in cua_minh if la_khach else d != chu_to
        return [
            {
                "employee_id": n["employee_id"],
                "ho_ten": n["ho_ten"],
                "to_ten": ten_to.get(n["department_id"]) if _ngoai(n["department_id"]) else None,
            }
            for n in theo_me.get(batch_id, [])
        ]

    # Gom: nguồn → công việc → mẻ.
    nguon: dict[tuple, dict] = {k: {"cd": {}, "me": 0, "dau": None, "cuoi": None} for k in khoa}
    for b, cv in me:
        k = ("bai_ghep", cv.bai_ghep_id) if cv.bai_ghep_id is not None else ("lsx", cv.lsx_id)
        n = nguon.get(k)
        if n is None:
            continue
        ngay = _ngay_xuong(b.bat_dau)
        n["dau"] = ngay if n["dau"] is None or (ngay and ngay < n["dau"]) else n["dau"]
        n["cuoi"] = ngay if n["cuoi"] is None or (ngay and ngay > n["cuoi"]) else n["cuoi"]
        la_khach = cv.department_id not in cua_minh
        c = n["cd"].setdefault(cv.id, {
            "cong_viec_id": cv.id, "ten_cong_doan": cv.ten_cong_doan, "to_id": cv.department_id,
            "to_ten": (q.cay.ten.get(cv.department_id) or ten_to.get(cv.department_id) or ""),
            "la_khach": la_khach, "so_me": 0, "_sl": {}, "_me": [], "_dau": b.bat_dau,
        })
        c["so_me"] += 1
        n["me"] += 1
        _cong(c["_sl"], b.don_vi, tot=b.tot, hong=b.hong)
        c["_me"].append({
            "batch_id": b.id,
            "ngay": ngay,
            "bat_dau": thuc_te_hien_thi(b.bat_dau),
            "ket_thuc": thuc_te_hien_thi(b.ket_thuc),
            # Mẻ ghi trước 18/09/2026 không có việc khoán để backfill ⇒ None, FE hiện
            # "— chưa khai việc khoán". KHÔNG đoán, không tự gán.
            "viec_khoan_ten": b.ten_khoan_snapshot,
            "tot": float(b.tot),
            "hong": float(b.hong),
            "don_vi": b.don_vi,
            "nguoi": _nguoi_cua(b.id, cv.department_id, la_khach),
        })

    lenh = []
    for k in khoa:
        n = nguon[k]
        ma, ten = nhan.get(k, ("", ""))
        sl_nguon: dict = {}
        cds = []
        for c in sorted(n["cd"].values(),
                        key=lambda x: (x["la_khach"], x["_dau"], x["cong_viec_id"])):
            # Dòng tổng của nguồn chỉ gom MẺ CỦA TỔ — mục khách bày số nhưng không cộng.
            if not c["la_khach"]:
                for dv, so in c["_sl"].items():
                    _cong(sl_nguon, dv, **so)
            cds.append({
                "cong_viec_id": c["cong_viec_id"], "ten_cong_doan": c["ten_cong_doan"],
                "to_id": c["to_id"], "to_ten": c["to_ten"], "la_khach": c["la_khach"],
                "so_me": c["so_me"], "san_luong": _ra_ds(c["_sl"]),
                "me": sorted(c["_me"], key=lambda x: (x["bat_dau"] or "", x["batch_id"])),
            })
        lenh.append({
            "nguon_loai": k[0], "nguon_id": k[1], "ma": ma, "ten": ten,
            "so_me": n["me"], "ngay_dau": n["dau"], "ngay_cuoi": n["cuoi"],
            "san_luong": _ra_ds(sl_nguon),
            "cong_doan": cds,
        })

    # Dòng tổng chỉ cho phạm vi thấy TRỌN. Quyền chỉ "Của tôi" thì không có tổng của tổ —
    # thợ đọc "Các mẻ tôi tham gia", không đọc tổng của người khác (§12.3).
    tong_to = repo.tong_cua_to(tron=tron, tim=tim, **loc)
    return {
        "team_id": team_id, "tu": tu, "den": den, "to_id": to_id,
        "trang": trang, "co_trang": co_trang, "tong_lenh": tong_nguon,
        "co_pham_vi_tron": bool(tron), "co_pham_vi_rieng": bool(rieng),
        "cac_to": cac_to,
        "tong": [{"don_vi": dv, "tot": round(t, 3), "hong": round(h, 3), "so_me": n}
                 for dv, t, h, n in tong_to],
        "lenh": lenh,
        "cap_nhat_luc": thuc_te_hien_thi(datetime.now(timezone.utc)),
    }
