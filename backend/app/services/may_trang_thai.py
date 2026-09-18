"""Trạng thái LÚC NÀY của từng máy — DẪN XUẤT hoàn toàn, không cột nào lưu.

Vì sao không đẻ cột `may_thiet_bi.trang_thai`: cột đó ĐÃ TỪNG có và bị gỡ 11/08/2026 vì là ô khai
tay — không ai nhớ vào sửa, nên mọi máy vĩnh viễn "active" kể cả lúc đang nằm. Ba nguồn dưới đây
thì luôn đúng vì chính người làm việc sinh ra chúng trong lúc làm:

  · **Vùng khoá máy** — `machine_unavailable_periods` phủ giờ này. Lý do quyết nhãn:
    `bao_tri` → Đang bảo trì · `hong_hoc` → Hỏng — chờ sửa · còn lại → Chặn xếp lệnh.
  · **Lệnh đang chạy** — có dòng phủ giờ này trên bàn Xếp lịch.
  · **Phiếu sửa chữa đang mở** — CẢNH BÁO, không phải vùng khoá (chủ chốt 11/09/2026). Xem dưới.

Thứ tự ưu tiên: máy nằm THẮNG máy chạy. Bàn lịch vẫn giữ lệnh trên lane của máy vừa bị khoá (lệnh
chưa được dời đi đâu cả) — hiện "Đang chạy" cho một cái máy đang tháo ra sửa là nói dối đúng lúc
người ta cần tin nhất.

Riêng nguồn thứ ba đứng NGOÀI chuỗi ưu tiên đó, và cố ý:

  · Phiếu sửa chữa là **lời khai của tổ kỹ thuật**, không phải khoảng giờ điều độ đặt ra — nó KHÔNG
    chặn xếp lệnh, chỉ nói ra một sự thật để điều độ tự cân nhắc.
  · Nên nó chỉ điền cho máy **không có chuyện gì khác** (lẽ ra hiện "Xếp được"). Máy đang chạy hay
    đã bị khoá thì đó là sự thật cụ thể hơn một tờ phiếu — giữ nguyên, không đè.
  · Nhờ vậy hai nhánh trên KHÔNG đổi một dòng nào; thêm cảnh báo không làm lệch được thứ tự sẵn có.

Ghi chú lịch sử: bản đầu đọc phiếu sự cố của module Bảo trì cũ (gỡ 12/08/2026) để ra trạng thái máy
hỏng kèm "đứng 3 giờ 20". Từ 11/09/2026 module Kỹ thuật máy quay lại nguồn này, nhưng **chỉ ở mức
cảnh báo** — chủ xưởng chốt "chỉ cảnh báo thôi, không động vào logic xếp lịch".
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ..models.machine_unavailable import (
    KIEU_CHAN,
    LY_DO_BAO_TRI,
    LY_DO_HONG_HOC,
    MachineUnavailablePeriod,
)

TT_MAY_DUNG = "may_dung"
TT_BAO_TRI = "bao_tri"
TT_KHOA = "khoa"
TT_DANG_CHAY = "dang_chay"
TT_RANH = "ranh"
# CẢNH BÁO, không phải vùng khoá (chủ chốt 11/09/2026 — "chỉ cảnh báo thôi").
# Máy có phiếu sửa chữa CHƯA đóng thì vẫn xếp lệnh được: phiếu là lời khai của tổ kỹ thuật, không
# phải khoảng giờ điều độ đặt ra. Nhưng để nguyên chữ "Xếp được" cho một cái máy đang tháo ra sửa
# là nói dối đúng lúc người ta cần tin nhất — nên nói ra sự thật, và để điều độ tự quyết.
TT_CO_PHIEU_SUA = "co_phieu_sua"

# Nhãn tiếng Việt — dựng ở ĐÂY, không ở FE: hai màn tự đặt tên là sớm muộn cùng một máy hiện hai
# chữ khác nhau. Bộ chữ chốt 12/08/2026 (chủ chốt): nói thẳng việc điều độ phải làm, không tả tình
# trạng máy. Bỏ "Máy đứng" vì "đứng máy" trong xưởng là NGHỀ của người thợ, đọc lướt trượt nghĩa;
# bỏ "Tạm khoá" vì màn này còn một chữ "khoá" khác (ghim dòng lịch, `POST /dong/{id}/khoa`).
NHAN = {
    TT_MAY_DUNG: "Hỏng — chờ sửa",
    TT_BAO_TRI: "Đang bảo trì",
    TT_KHOA: "Chặn xếp lệnh",
    TT_DANG_CHAY: "Đang chạy",
    TT_RANH: "Xếp được",
    # Cố ý KHÔNG phrasing kiểu ra lệnh như bốn nhãn trên: chúng nói việc điều độ PHẢI làm, còn đây
    # chỉ nêu một sự thật để họ cân nhắc. Máy vẫn xếp được.
    TT_CO_PHIEU_SUA: "Có phiếu sửa chữa",
}


def _aware(dt: datetime | None) -> datetime | None:
    """Giờ đọc từ SQLite là NAIVE — đem so với `now()` aware là nổ 500 (bẫy cũ ở Xếp lịch)."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _naive(dt: datetime | None) -> datetime | None:
    """Bỏ tzinfo cho ĐẦU RA — FE `new Date(iso)` không dịch múi (tránh lệch +7h)."""
    return dt.replace(tzinfo=None) if dt is not None else None


def _gio_xuong() -> datetime:
    """Bây giờ theo ĐỒNG HỒ XƯỞNG, gắn nhãn UTC cho khớp `_aware()` ở trên.

    Mọi mốc đem ra so ở đây (`start_at`/`finish_at` bàn lịch, vùng khoá máy) đều là GIỜ TƯỜNG dán
    nhãn UTC. Lấy `datetime.now(timezone.utc)` là UTC thật ⇒ ở VN lùi 7 tiếng: lúc 09:00 xưởng, hàm
    hỏi "máy nào đang chạy lúc 02:00" và trả về lệnh của ca đêm. Sửa cùng lượt với mốc sàn xếp lịch
    22/08/2026 (`xep_lich_service._gio_xuong`).
    """
    return datetime.now().replace(tzinfo=timezone.utc)


def _gio(dt: datetime | None) -> str:
    return f"{dt:%H:%M}" if dt else "?"


def _dong_gia_xep_lich_3(db, may_ids: list[int], bay_gio: datetime) -> list:
    """Dòng GIẢ (không lưu) dựng từ mốc dẫn xuất của Xếp lịch 3, cho vừa vòng lặp bên dưới.

    Màn 3 không đẻ dòng `xep_lich_cong_doan`, nên nếu chỉ đọc bảng lịch cũ thì mọi máy đang chạy
    lệnh xếp ở màn mới đều hiện "rảnh" — sai theo hướng nguy hiểm nhất: người ta đẩy thêm việc vào
    máy đang bận. Chỉ dựng đúng ba thuộc tính vòng lặp dùng tới (`may_id`/`finish_at`/`lsx_id`).
    """
    from types import SimpleNamespace

    from ..models.lsx import LsxCongDoan
    from .xep_lich_3.moc import lsx_da_xep, moc_theo_buoc

    da_xep = lsx_da_xep(db)
    if not da_xep:
        return []
    moc = moc_theo_buoc(db, sorted(da_xep))
    if not moc:
        return []
    buoc = db.execute(
        select(LsxCongDoan.id, LsxCongDoan.may_id, LsxCongDoan.lsx_id).where(
            LsxCongDoan.id.in_(sorted(moc)), LsxCongDoan.may_id.in_(may_ids),
        )
    ).all()
    moc_now = _naive(_aware(bay_gio))
    ra = []
    for bid, may_id, lsx_id in buoc:
        bat_dau, ket_thuc = moc[bid]
        if bat_dau <= moc_now < ket_thuc:
            ra.append(SimpleNamespace(may_id=may_id, lsx_id=lsx_id, bai_ghep_id=None,
                                      finish_at=ket_thuc))
    return ra


def lenh_dang_chay(db, may_ids: list[int], bay_gio: datetime) -> dict[int, dict]:
    """{may_id: {ma, finish_at}} — lệnh ĐANG chạy trên máy, đọc từ bàn Xếp lịch.

    Import cục bộ để màn Thiết bị không phụ thuộc cứng vào Xếp lịch: thiếu bảng thì trả rỗng,
    cột Trạng thái vẫn hiện được phần còn lại thay vì cả màn chết.
    """
    if not may_ids:
        return {}
    from ..models.bai_ghep import BaiGhep
    from ..models.lsx import Lsx
    from ..models.xep_lich import XepLichCongDoan

    rows = list(db.execute(
        select(XepLichCongDoan).where(
            XepLichCongDoan.may_id.in_(may_ids),
            XepLichCongDoan.start_at <= bay_gio,
            XepLichCongDoan.finish_at > bay_gio,
        )
    ).scalars())
    rows.extend(_dong_gia_xep_lich_3(db, may_ids, bay_gio))
    if not rows:
        return {}
    lsx_ma = dict(db.execute(
        select(Lsx.id, Lsx.ma).where(Lsx.id.in_({r.lsx_id for r in rows if r.lsx_id}))
    ).all()) if any(r.lsx_id for r in rows) else {}
    bg_ma = dict(db.execute(
        select(BaiGhep.id, BaiGhep.ma).where(BaiGhep.id.in_({r.bai_ghep_id for r in rows if r.bai_ghep_id}))
    ).all()) if any(r.bai_ghep_id for r in rows) else {}

    out: dict[int, dict] = {}
    for r in rows:
        ma = bg_ma.get(r.bai_ghep_id) or lsx_ma.get(r.lsx_id)
        if not ma or r.may_id is None:
            continue
        # Nhiều dòng chồng nhau trên cùng máy (không nên có, nhưng bàn lịch cho phép) ⇒ giữ dòng
        # KẾT THÚC SỚM NHẤT: đó là cái sắp giải phóng máy.
        cu = out.get(r.may_id)
        if cu is None or _aware(r.finish_at) < cu["_f"]:
            out[r.may_id] = {"ma": ma, "finish_at": _naive(_aware(r.finish_at)),
                             "_f": _aware(r.finish_at)}
    for v in out.values():
        v.pop("_f", None)
    return out


def phieu_sua_dang_mo(db, may_ids: list[int]) -> dict[int, dict]:
    """{may_id: {ma, phieu_id, bo_phan_hong, so}} — phiếu sửa chữa CHƯA đóng của từng máy.

    Import cục bộ, cùng lý do với `lenh_dang_chay`: màn Thiết bị không được chết theo module Kỹ
    thuật máy. Thiếu bảng ⇒ trả rỗng, cột Trạng thái vẫn hiện được phần còn lại.

    Nặng trước, mới sau — giống thứ tự hàng chờ của tổ sửa chữa: một máy có ba phiếu mở thì cái
    điều độ cần biết là cái nặng nhất, không phải cái tình cờ có id nhỏ nhất.
    """
    if not may_ids:
        return {}
    try:
        from ..models.ky_thuat_may import MUC_DO, TT_SC_DANG_MO, SuaChuaMay
    except Exception:  # noqa: BLE001
        return {}

    nang = {m: i for i, m in enumerate(MUC_DO)}
    rows = list(db.execute(
        select(SuaChuaMay).where(
            SuaChuaMay.may_id.in_(may_ids),
            SuaChuaMay.trang_thai.in_(TT_SC_DANG_MO),
        )
    ).scalars())

    out: dict[int, dict] = {}
    for p in rows:
        cu = out.get(p.may_id)
        if cu is None:
            out[p.may_id] = {"ma": p.ma, "phieu_id": p.id, "bo_phan_hong": p.bo_phan_hong,
                             "so": 1, "_nang": nang.get(p.muc_do, -1), "_khi": p.thoi_diem}
            continue
        cu["so"] += 1
        mm, khi = nang.get(p.muc_do, -1), p.thoi_diem
        if (mm, khi) > (cu["_nang"], cu["_khi"]):
            cu.update(ma=p.ma, phieu_id=p.id, bo_phan_hong=p.bo_phan_hong, _nang=mm, _khi=khi)
    for v in out.values():
        v.pop("_nang", None)
        v.pop("_khi", None)
    return out


def trang_thai_may(db, may_ids: list[int], *, bay_gio: datetime | None = None) -> dict[int, dict]:
    """{may_id: {trang_thai, nhan, chi_tiet, phieu_id, den}} — chỉ máy CÓ CHUYỆN mới có mặt.

    Máy không xuất hiện trong map = `ranh`. Cố ý không nhồi cả danh sách máy vào đây: bên gọi đã
    có danh sách rồi, trả về thêm một bản sao chỉ để nói "không có gì" là tốn công vô ích.
    """
    if not may_ids:
        return {}
    bay_gio = bay_gio or _gio_xuong()
    out: dict[int, dict] = {}

    # 1. Đang chạy (yếu nhất — bị vùng khoá đè)
    for may_id, lenh in lenh_dang_chay(db, may_ids, bay_gio).items():
        finish = lenh.get("finish_at")
        out[may_id] = {
            "trang_thai": TT_DANG_CHAY, "nhan": NHAN[TT_DANG_CHAY],
            "chi_tiet": f"{lenh['ma']} · xong {_gio(finish)}",
            "phieu_id": None, "den": finish,
        }

    # 2. Vùng khoá đang phủ giờ này — máy nằm, đè lên "đang chạy".
    rows = db.execute(
        select(MachineUnavailablePeriod).where(
            MachineUnavailablePeriod.may_id.in_(may_ids),
            MachineUnavailablePeriod.kieu == KIEU_CHAN,
            MachineUnavailablePeriod.unavailable_from <= bay_gio,
            MachineUnavailablePeriod.unavailable_to > bay_gio,
        )
    ).scalars()
    for k in rows:
        if k.reason == LY_DO_BAO_TRI:
            tt = TT_BAO_TRI
        elif k.reason == LY_DO_HONG_HOC:
            tt = TT_MAY_DUNG
        else:
            tt = TT_KHOA          # nghỉ riêng của máy / khoá tay lý do khác
        den = _naive(_aware(k.unavailable_to))
        cu = out.get(k.may_id)
        # Nhiều khoảng chồng nhau: giữ cái MỞ KHOÁ MUỘN NHẤT — đó mới là lúc máy thật sự chạy lại.
        if cu is not None and cu["trang_thai"] != TT_DANG_CHAY and (cu.get("den") or den) >= den:
            continue
        out[k.may_id] = {
            "trang_thai": tt, "nhan": NHAN[tt],
            "chi_tiet": (k.note or "").strip()[:80] or f"tới {_gio(den)}",
            "phieu_id": None, "den": den,
        }

    # 3. CẢNH BÁO phiếu sửa chữa — YẾU NHẤT, và cố ý đặt sau cùng với điều kiện `not in out`.
    #
    # Chỉ điền cho máy KHÔNG có chuyện gì khác, tức máy lẽ ra hiện "Xếp được" — đúng cái trường hợp
    # nói dối: máy đang tháo ra sửa mà bảng ghi xếp được. Máy đang chạy hay đã bị khoá thì đó là sự
    # thật cụ thể hơn một tờ phiếu, giữ nguyên.
    #
    # Viết kiểu "chỉ điền chỗ trống" thay vì chen vào chuỗi ưu tiên ở trên là có chủ ý: hai nhánh
    # trên KHÔNG đổi một dòng nào, nên không có đường nào cảnh báo này làm lệch thứ tự sẵn có.
    for may_id, p in phieu_sua_dang_mo(db, may_ids).items():
        if may_id in out:
            continue
        them = f" · +{p['so'] - 1} phiếu" if p["so"] > 1 else ""
        out[may_id] = {
            "trang_thai": TT_CO_PHIEU_SUA, "nhan": NHAN[TT_CO_PHIEU_SUA],
            "chi_tiet": f"{p['ma']} · {(p['bo_phan_hong'] or '').strip()[:40]}{them}",
            "phieu_id": p["phieu_id"], "den": None,
        }
    return out
