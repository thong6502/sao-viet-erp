"""Repo khóa sổ kỳ kế toán kho (chốt sổ) — docs/spec-bao-cao-kho.md §6.

LOG APPEND-ONLY: mỗi lần khóa/mở ghi 1 bản ghi cho KHOẢNG [tu_ngay, den_ngay] và một phạm vi
(kho_id NULL = toàn kho). Phiếu tại (kho, ngày) bị KHÓA nếu bản ghi MỚI NHẤT (theo id) trong các
bản ghi phủ ngày đó (toàn kho HOẶC kho này) có hanh_dong='khoa'. → 'mo' ghi sau đè 'khoa'; kho
riêng đè toàn kho khi ghi sau. Bảng vừa là HIỆU LỰC vừa là LỊCH SỬ thao tác.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models.kho_khoa_so import KhoKhoaSo


class KhoKhoaSoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_locked(self, kho_id: int | None, ngay: date) -> bool:
        """Ngày `ngay` ở kho `kho_id` có đang khóa? Bản ghi mới nhất phủ ngày đó quyết định."""
        stmt = (
            select(KhoKhoaSo)
            .where(
                KhoKhoaSo.tu_ngay <= ngay,
                KhoKhoaSo.den_ngay >= ngay,
                or_(KhoKhoaSo.kho_id.is_(None), KhoKhoaSo.kho_id == kho_id),
            )
            .order_by(KhoKhoaSo.id.desc())
            .limit(1)
        )
        row = self.db.execute(stmt).scalars().first()
        return row is not None and row.hanh_dong == "khoa"

    def add(self, *, kho_id: int | None, tu_ngay: date, den_ngay: date,
            hanh_dong: str, nguoi_khoa_id: int | None, ten: str | None = None) -> KhoKhoaSo:
        row = KhoKhoaSo(
            kho_id=kho_id, tu_ngay=tu_ngay, den_ngay=den_ngay,
            hanh_dong=hanh_dong, nguoi_khoa_id=nguoi_khoa_id, ten=ten,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def locked_cutoff(self, kho_id: int | None) -> date | None:
        """NGÀY KHÓA XA NHẤT còn hiệu lực (cutoff) cho phạm vi — MÉP CUỐI vùng đang khóa. None nếu
        không có gì đang khóa. Dùng cho luật MỞ SỔ TUẦN TỰ (đặt 'Đến ngày' = cutoff).

        KHÔNG được dựa vào `den_ngay` của bản ghi 'khoa': khi MỞ MỘT PHẦN (bản 'mo' phủ đuôi một kỳ
        'khoa') thì mép khóa lùi sang ngày KHÔNG trùng mốc bản ghi nào (vd khóa tới 30/08 rồi mở
        12/08–30/08 → cutoff = 11/08). Phải QUÉT LÙI từ den lớn nhất của các bản 'khoa' tới ngày
        `is_locked` đầu tiên. Tính trong bộ nhớ (1 query) cho phạm vi này, tránh N query."""
        recs = list(
            self.db.execute(
                select(KhoKhoaSo).where(
                    or_(KhoKhoaSo.kho_id.is_(None), KhoKhoaSo.kho_id == kho_id),
                )
            ).scalars()
        )
        khoa_den = [r.den_ngay for r in recs if r.hanh_dong == "khoa"]
        if not khoa_den:
            return None

        def locked_at(day: date) -> bool:
            # Bản ghi MỚI NHẤT (id lớn nhất) phủ `day` quyết định — giống `is_locked`, làm in-memory.
            cov = [r for r in recs if r.tu_ngay <= day <= r.den_ngay]
            return bool(cov) and max(cov, key=lambda r: r.id).hanh_dong == "khoa"

        lo = min(r.tu_ngay for r in recs)
        day = max(khoa_den)
        one = timedelta(days=1)
        while day >= lo:
            if locked_at(day):
                return day
            day -= one
        return None

    def locked_run_start(self, kho_id: int | None, cutoff: date) -> date:
        """Ngày ĐẦU của vùng khóa LIỀN MẠCH kết thúc tại `cutoff` — mọi ngày trong [start, cutoff]
        đều đang khóa. Dùng cho luật MỞ: chỉ được mở phần đuôi LIỀN MẠCH, KHÔNG vắt qua kẽ hở hay
        ôm luôn kỳ cũ hơn phía trước. (Muốn mở kỳ cũ thì phải mở kỳ mới hơn TRƯỚC — cutoff lùi dần.)"""
        day = cutoff
        while self.is_locked(kho_id, day - timedelta(days=1)):
            day -= timedelta(days=1)
        return day

    def overlaps_locked(self, kho_id: int | None, tu: date, den: date) -> bool:
        """Khoảng [tu, den] có CHỒNG LẤN ngày nào ĐANG KHÓA không (cho phạm vi)? Dùng để CẤM khóa
        đè: kỳ mới phải bắt đầu sau ngày đã khóa gần nhất, không giẫm lên kỳ cũ."""
        stmt = select(KhoKhoaSo).where(
            KhoKhoaSo.hanh_dong == "khoa",
            KhoKhoaSo.tu_ngay <= den,
            KhoKhoaSo.den_ngay >= tu,
            or_(KhoKhoaSo.kho_id.is_(None), KhoKhoaSo.kho_id == kho_id),
        )
        for rec in self.db.execute(stmt).scalars():
            # Điểm đầu vùng chồng lấn — kiểm còn khóa thật (chưa bị 'mo' đè).
            if self.is_locked(kho_id, max(tu, rec.tu_ngay)):
                return True
        return False

    def locked_periods(self) -> list[tuple]:
        """Các KỲ CÒN ĐANG KHÓA, theo phạm vi — cho tab 'Kỳ đã khóa'. Trả list
        (kho_id, tu_ngay, den_ngay, khoa_luc), MỚI NHẤT (den lớn) trước.

        MỖI LẦN KHÓA = 1 KỲ RIÊNG: kỳ bị CẮT mỗi khi ĐỔI bản ghi 'khoa' thắng (kể cả 2 kỳ liền
        ngày nhau) → khớp đúng cách BÁO CÁO tô màu (mỗi `rec.id` một màu).
        - Phạm vi TOÀN KHO (kho_id None): ngày khóa xét theo bản ghi toàn-kho.
        - Kho RIÊNG: chỉ tính ngày khóa riêng cho kho đó (đang khóa cho kho mà KHÔNG bị lệnh
          toàn-kho khóa) → không trùng với kỳ toàn kho. `khoa_luc` lấy từ bản ghi 'khoa' quyết
          định tại NGÀY ĐẦU của kỳ."""
        records = list(self.db.execute(select(KhoKhoaSo).order_by(KhoKhoaSo.id)).scalars())
        if not records:
            return []

        def winner_at(kho_id: int | None, day: date) -> KhoKhoaSo | None:
            w = None
            for r in records:  # id tăng dần → bản ghi ghi sau đè bản trước
                if r.tu_ngay <= day <= r.den_ngay and (r.kho_id is None or r.kho_id == kho_id):
                    w = r
            return w

        span_start = min(r.tu_ngay for r in records)
        span_end = max(r.den_ngay for r in records)
        scopes: list[int | None] = [None] + sorted(
            {r.kho_id for r in records if r.kho_id is not None}
        )

        out: list[tuple] = []
        one = timedelta(days=1)
        for scope in scopes:
            run_start: date | None = None
            run_rep: KhoKhoaSo | None = None
            prev_id: int | None = None       # id bản ghi 'khoa' thắng NGÀY TRƯỚC (None = không khóa)
            prev_day: date | None = None
            day = span_start
            while day <= span_end:
                w = winner_at(scope, day)
                locked = w is not None and w.hanh_dong == "khoa"
                if scope is not None and locked:
                    # Kho riêng: bỏ ngày đã bị lệnh TOÀN KHO khóa (đã thuộc kỳ toàn kho).
                    wn = winner_at(None, day)
                    if wn is not None and wn.hanh_dong == "khoa":
                        locked = False
                cur_id = w.id if locked else None
                # ĐỔI bản ghi khóa (hoặc chuyển khóa↔không) → chốt kỳ trước, mở kỳ mới.
                if cur_id != prev_id:
                    if prev_id is not None:
                        out.append((scope, run_start, prev_day, run_rep.khoa_luc if run_rep else None, run_rep.ten if run_rep else None))
                    run_start = day if cur_id is not None else None
                    run_rep = w if cur_id is not None else None
                prev_id = cur_id
                prev_day = day
                day += one
            if prev_id is not None:
                out.append((scope, run_start, prev_day, run_rep.khoa_luc if run_rep else None, run_rep.ten if run_rep else None))

        out.sort(key=lambda t: (t[2], t[1]), reverse=True)  # den (rồi tu) giảm dần
        return out

    def exempted_khos(self, tu_ngay: date, den_ngay: date) -> list[int]:
        """Trong kỳ TOÀN KHO [tu_ngay, den_ngay]: các kho được MỞ RIÊNG (miễn trừ) — có lệnh mở riêng
        kho ĐÈ lên khóa toàn kho ở ít nhất 1 ngày. Trả kho_id đang MỞ. Tính in-memory (1 query)."""
        records = list(self.db.execute(select(KhoKhoaSo).order_by(KhoKhoaSo.id)).scalars())

        def winner_at(kho_id: int, day: date) -> KhoKhoaSo | None:
            w = None
            for r in records:  # id tăng dần → bản ghi ghi sau đè bản trước
                if r.tu_ngay <= day <= r.den_ngay and (r.kho_id is None or r.kho_id == kho_id):
                    w = r
            return w

        one = timedelta(days=1)
        out: list[int] = []
        for kid in sorted({r.kho_id for r in records if r.kho_id is not None}):
            day = tu_ngay
            while day <= den_ngay:
                w = winner_at(kid, day)
                if w is not None and w.hanh_dong == "mo":  # kho này đang MỞ (bị lệnh mở riêng đè)
                    out.append(kid)
                    break
                day += one
        return out

    def history(self, limit: int = 300) -> list[KhoKhoaSo]:
        """Toàn bộ thao tác khóa/mở, mới nhất trước — = lịch sử thao tác."""
        return list(
            self.db.execute(
                select(KhoKhoaSo).order_by(KhoKhoaSo.id.desc()).limit(limit)
            ).scalars().all()
        )
