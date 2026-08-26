"""Trạng thái LÚC NÀY của từng máy — DẪN XUẤT hoàn toàn, không cột nào lưu.

Vì sao không đẻ cột `may_thiet_bi.trang_thai`: cột đó ĐÃ TỪNG có và bị gỡ 11/08/2026 vì là ô khai
tay — không ai nhớ vào sửa, nên mọi máy vĩnh viễn "active" kể cả lúc đang nằm. Hai nguồn dưới đây
thì luôn đúng vì chính người làm việc sinh ra chúng trong lúc làm:

  · **Vùng khoá máy** — `machine_unavailable_periods` phủ giờ này. Lý do quyết nhãn:
    `bao_tri` → Đang bảo trì · `hong_hoc` → Hỏng — chờ sửa · còn lại → Chặn xếp lệnh.
  · **Lệnh đang chạy** — có dòng phủ giờ này trên bàn Xếp lịch.

Thứ tự ưu tiên: máy nằm THẮNG máy chạy. Bàn lịch vẫn giữ lệnh trên lane của máy vừa bị khoá (lệnh
chưa được dời đi đâu cả) — hiện "Đang chạy" cho một cái máy đang tháo ra sửa là nói dối đúng lúc
người ta cần tin nhất.

Ghi chú lịch sử: bản đầu còn đọc phiếu sự cố của module Bảo trì để ra trạng thái máy hỏng kèm
"đứng 3 giờ 20". Module đó đã bị gỡ 12/08/2026 theo yêu cầu chủ xưởng, nên nguồn duy nhất còn lại
cho trạng thái máy nằm là vùng khoá do điều độ đặt trên Gantt.
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
    return out
