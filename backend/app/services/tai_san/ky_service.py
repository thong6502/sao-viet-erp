"""Kỳ khấu hao: tính · xem bảng · chốt · mở lại.

Tách bạch hai việc mà kế toán hay lẫn:

- **Tính** = dựng lại dòng khấu hao của kỳ. Chạy bao nhiêu lần cũng được, mỗi lần XOÁ dòng cũ
  rồi ghi lại, KHÔNG cộng dồn. Tính KHÔNG đụng `tai_san.hao_mon_luy_ke`.
- **Chốt** = đóng kỳ. Lúc này mới cộng số của kỳ vào `hao_mon_luy_ke` của từng tài sản. Mở lại
  kỳ thì trừ ngược đúng số đó ra.

Nhờ vậy `hao_mon_luy_ke` luôn = tổng các kỳ ĐÃ CHỐT, không bao giờ bị bơm lên vì ai đó bấm Tính
nhiều lần. Muốn xem trước lũy kế của một kỳ khi kỳ trước còn mở thì cộng thêm dòng của các kỳ
chưa chốt nằm trước nó (`_luy_ke_dau_ky`).

Điều chuyển giữa tháng: chi phí kỳ đó về NGUYÊN bộ phận đang giữ lúc tính (không chia đôi theo
ngày) — đã chốt như vậy ở spec §4, vì chia đôi một tháng khấu hao theo ngày công không ai đối
chiếu nổi trên bảng in.

Vì chốt/mở là hai thao tác DUY NHẤT chạm `hao_mon_luy_ke`, mỗi lần đều ghi một dòng
`tai_san_ky_log` (append-only) kèm số tiền đã cộng/trừ. Tính KHÔNG ghi vết: nó không đụng sổ,
mà bấm Tính là chuyện thường ngày — ghi cả vào thì vết chốt chìm nghỉm giữa hàng chục dòng.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.tai_san import (
    BD_GHI_GIAM,
    BD_NANG_CAP,
    KY_DA_CHOT,
    KY_LOG_CHOT,
    KY_LOG_MO,
    KY_MO,
    TT_DANG_DUNG,
    TaiSan,
    TaiSanBienDong,
    TaiSanKhauHao,
    TaiSanKy,
    TaiSanKyLog,
)
from ...models.user import User
from .khau_hao import trich_mot_ky


class KyDaChot(Exception):
    pass


class KyTruocChuaChot(Exception):
    pass


class KyKhongTonTai(Exception):
    pass


class KyCoChungTuSau(Exception):
    pass


def _moc(nam: int, thang: int) -> int:
    """Đổi (năm, tháng) thành một số để so sánh/sắp xếp — dùng cả trong SQL."""
    return nam * 12 + thang


class KyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đọc trạng thái kỳ ------------------------------------------------------------------

    def lay_ky(self, nam: int, thang: int) -> TaiSanKy | None:
        return self.db.execute(
            select(TaiSanKy).where(TaiSanKy.ky_nam == nam, TaiSanKy.ky_thang == thang)
        ).scalar_one_or_none()

    def danh_sach_ky(self) -> list[TaiSanKy]:
        return list(
            self.db.execute(
                select(TaiSanKy).order_by(TaiSanKy.ky_nam.desc(), TaiSanKy.ky_thang.desc())
            ).scalars()
        )

    def _ky_hoac_tao(self, nam: int, thang: int) -> TaiSanKy:
        k = self.lay_ky(nam, thang)
        if k is None:
            k = TaiSanKy(ky_nam=nam, ky_thang=thang, trang_thai=KY_MO)
            self.db.add(k)
            self.db.flush()
        return k

    def _chan_neu_da_chot(self, nam: int, thang: int) -> None:
        k = self.lay_ky(nam, thang)
        if k is not None and k.trang_thai == KY_DA_CHOT:
            raise KyDaChot(f"Kỳ {thang:02d}/{nam} đã chốt — mở lại kỳ trước khi sửa số")

    def _ky_da_chot_set(self) -> set[tuple[int, int]]:
        return {
            (n, t)
            for n, t in self.db.execute(
                select(TaiSanKy.ky_nam, TaiSanKy.ky_thang).where(
                    TaiSanKy.trang_thai == KY_DA_CHOT
                )
            )
        }

    def _luy_ke_dau_ky(self, nam: int, thang: int) -> dict[int, int]:
        """Số đã trích ở các kỳ CHƯA CHỐT nằm TRƯỚC kỳ này, theo tài sản.

        Kỳ đã chốt thì số của nó nằm sẵn trong `tai_san.hao_mon_luy_ke` rồi, cộng lần nữa là
        nhân đôi — nên chỉ gom kỳ chưa chốt.
        """
        da_chot = self._ky_da_chot_set()
        moc = _moc(nam, thang)
        rows = self.db.execute(
            select(
                TaiSanKhauHao.tai_san_id,
                TaiSanKhauHao.ky_nam,
                TaiSanKhauHao.ky_thang,
                TaiSanKhauHao.muc_trich,
            ).where(TaiSanKhauHao.ky_nam * 12 + TaiSanKhauHao.ky_thang < moc)
        )
        ra: dict[int, int] = {}
        for ts_id, n, t, muc in rows:
            if (n, t) in da_chot:
                continue
            ra[ts_id] = ra.get(ts_id, 0) + int(muc or 0)
        return ra

    # --- Tính -------------------------------------------------------------------------------

    def tinh(self, nam: int, thang: int) -> list[TaiSanKhauHao]:
        """Dựng lại dòng khấu hao của kỳ. Ghi đè dòng cũ, KHÔNG đụng hao mòn lũy kế."""
        self._chan_neu_da_chot(nam, thang)
        self._ky_hoac_tao(nam, thang)
        self.db.execute(
            delete(TaiSanKhauHao).where(
                TaiSanKhauHao.ky_nam == nam, TaiSanKhauHao.ky_thang == thang
            )
        )

        them = self._luy_ke_dau_ky(nam, thang)
        # Lấy cả tài sản ĐÃ GIẢM: tháng ghi giảm vẫn trích tới ngày giảm.
        tai_san = list(self.db.execute(select(TaiSan)).scalars())

        ra: list[TaiSanKhauHao] = []
        for t in tai_san:
            luy_ke = int(t.hao_mon_luy_ke or 0) + them.get(t.id, 0)
            muc = trich_mot_ky(
                co_so_trich=int(t.co_so_trich or 0),
                so_thang_con=int(t.so_thang_con or 0),
                moc_tu_ngay=t.moc_tu_ngay,
                nguyen_gia=int(t.nguyen_gia or 0),
                luy_ke=luy_ke,
                nam=nam,
                thang=thang,
                ngay_giam=t.ngay_giam if t.trang_thai != TT_DANG_DUNG else None,
            )
            if muc <= 0:
                continue
            dong = TaiSanKhauHao(
                tai_san_id=t.id,
                ky_nam=nam,
                ky_thang=thang,
                muc_trich=muc,
                luy_ke=luy_ke + muc,
                con_lai=int(t.nguyen_gia or 0) - (luy_ke + muc),
                bo_phan_id=t.bo_phan_id,
            )
            self.db.add(dong)
            ra.append(dong)

        self.db.commit()
        return ra

    def bang(self, nam: int, thang: int) -> list[dict]:
        """Bảng khấu hao kỳ — đúng những cột màn hình và file Excel cần, không hơn."""
        stmt = (
            select(TaiSanKhauHao, TaiSan, Department.name)
            .join(TaiSan, TaiSan.id == TaiSanKhauHao.tai_san_id)
            .outerjoin(Department, Department.id == TaiSanKhauHao.bo_phan_id)
            .where(TaiSanKhauHao.ky_nam == nam, TaiSanKhauHao.ky_thang == thang)
            .order_by(TaiSan.ma)
        )
        return [
            {
                "tai_san_id": t.id,
                "ma": t.ma,
                "ten": t.ten,
                "loai": t.loai,
                "bo_phan_ten": ten_bp,
                "nguyen_gia": int(t.nguyen_gia or 0),
                "muc_trich": int(kh.muc_trich or 0),
                "luy_ke": int(kh.luy_ke or 0),
                "con_lai": int(kh.con_lai or 0),
            }
            for kh, t, ten_bp in self.db.execute(stmt)
        ]

    # --- Vết chốt / mở ----------------------------------------------------------------------

    def _ghi_vet(
        self,
        nam: int,
        thang: int,
        hanh_dong: str,
        so_tien: int,
        so_mon: int,
        user_id: int | None,
    ) -> None:
        """Thêm một dòng vết. KHÔNG commit — đi chung transaction với chính thao tác nó ghi lại,
        nên không bao giờ có vết của một lần chốt đã rollback, cũng không có lần chốt không vết."""
        self.db.add(
            TaiSanKyLog(
                ky_nam=nam,
                ky_thang=thang,
                hanh_dong=hanh_dong,
                so_tien=int(so_tien),
                so_mon=int(so_mon),
                nguoi_id=user_id,
            )
        )

    def lich_su(self, nam: int, thang: int) -> list[dict]:
        """Vết chốt/mở của MỘT kỳ, mới nhất trước."""
        stmt = (
            select(TaiSanKyLog, User.name)
            .outerjoin(User, User.id == TaiSanKyLog.nguoi_id)
            .where(TaiSanKyLog.ky_nam == nam, TaiSanKyLog.ky_thang == thang)
            .order_by(TaiSanKyLog.thoi_diem.desc(), TaiSanKyLog.id.desc())
        )
        return [
            {
                "id": v.id,
                "hanh_dong": v.hanh_dong,
                "so_tien": int(v.so_tien or 0),
                "so_mon": int(v.so_mon or 0),
                "nguoi_ten": ten,
                "thoi_diem": v.thoi_diem,
            }
            for v, ten in self.db.execute(stmt)
        ]

    # --- Chốt / mở --------------------------------------------------------------------------

    def chot(self, nam: int, thang: int, *, user_id: int | None = None) -> TaiSanKy:
        self._chan_neu_da_chot(nam, thang)

        # Không cho nhảy cóc: kỳ trước còn số mà chưa chốt thì lũy kế sẽ lệch nếu sau này kỳ đó
        # bị tính lại.
        da_chot = self._ky_da_chot_set()
        moc = _moc(nam, thang)
        truoc = self.db.execute(
            select(TaiSanKhauHao.ky_nam, TaiSanKhauHao.ky_thang)
            .where(TaiSanKhauHao.ky_nam * 12 + TaiSanKhauHao.ky_thang < moc)
            .distinct()
        )
        con_mo = sorted({(n, t) for n, t in truoc} - da_chot)
        if con_mo:
            n, t = con_mo[0]
            raise KyTruocChuaChot(f"Kỳ {t:02d}/{n} chưa chốt — phải chốt lần lượt từ kỳ cũ nhất")

        dong = list(
            self.db.execute(
                select(TaiSanKhauHao).where(
                    TaiSanKhauHao.ky_nam == nam, TaiSanKhauHao.ky_thang == thang
                )
            ).scalars()
        )
        cong, so_mon = 0, 0
        for d in dong:
            t = self.db.get(TaiSan, d.tai_san_id)
            if t is not None:
                t.hao_mon_luy_ke = int(t.hao_mon_luy_ke or 0) + int(d.muc_trich or 0)
                cong += int(d.muc_trich or 0)
                so_mon += 1

        k = self._ky_hoac_tao(nam, thang)
        k.trang_thai = KY_DA_CHOT
        k.ngay_chot = datetime.now(timezone.utc)
        k.nguoi_chot_id = user_id
        self._ghi_vet(nam, thang, KY_LOG_CHOT, cong, so_mon, user_id)
        self.db.commit()
        return k

    def _chan_chung_tu_sau_ky(self, nam: int, thang: int) -> None:
        """Có chứng từ nâng cấp / ghi giảm nằm SAU kỳ thì không mở lại kỳ được nữa.

        Mở lại kỳ chỉ đơn giản là trừ `muc_trich` đã ghi ra khỏi `hao_mon_luy_ke`. Phép trừ đó
        chỉ đúng chừng nào con số của tài sản còn y như lúc chốt. Hai chứng từ này viết lại chính
        những con số ấy:

          • Ghi giảm MỘT PHẦN lô CCDC rút cả nguyên giá lẫn hao mòn theo tỷ lệ số cái bỏ. Bỏ 2
            trong 4 cái xong mở lại kỳ cũ là đem mức trích của 4 cái trừ khỏi hao mòn của 2 cái —
            lũy kế ÂM, còn lại lớn hơn cả nguyên giá, mà không có lỗi nào bật ra.
          • Nâng cấp và ghi giảm toàn bộ viết lại cơ sở trích / mốc / ngày giảm, nên bấm Tính lại
            cho kỳ vừa mở sẽ ra mức trích theo số SAU chứng từ, gán cho một tháng TRƯỚC nó.

        Không có cửa huỷ chứng từ để lùi số về, nên chặn thẳng và nói rõ vướng món nào — hơn là
        cho mở rồi để kế toán tự phát hiện lũy kế âm.
        """
        cuoi_ky = date(nam + thang // 12, thang % 12 + 1, 1) - timedelta(days=1)
        row = self.db.execute(
            select(TaiSan.ma, TaiSanBienDong.loai, TaiSanBienDong.ngay)
            .join(TaiSan, TaiSan.id == TaiSanBienDong.tai_san_id)
            .where(
                TaiSanBienDong.loai.in_((BD_NANG_CAP, BD_GHI_GIAM)),
                TaiSanBienDong.ngay > cuoi_ky,
            )
            .order_by(TaiSanBienDong.ngay)
        ).first()
        if row is None:
            return
        ma, loai, ngay = row
        ten = "nâng cấp" if loai == BD_NANG_CAP else "ghi giảm"
        raise KyCoChungTuSau(
            f"Đã có chứng từ {ten} {ma} ngày {ngay:%d/%m/%Y} — sau kỳ này. Mở lại kỳ sẽ làm sai "
            f"lũy kế vì chứng từ đó đã viết lại nguyên giá và hao mòn của món."
        )

    def mo(self, nam: int, thang: int, *, user_id: int | None = None) -> TaiSanKy:
        k = self.lay_ky(nam, thang)
        if k is None:
            raise KyKhongTonTai(f"Chưa có kỳ {thang:02d}/{nam}")
        if k.trang_thai != KY_DA_CHOT:
            return k

        # Mở kỳ cũ trong khi kỳ sau đã chốt sẽ làm lũy kế của kỳ sau treo lơ lửng.
        moc = _moc(nam, thang)
        sau = [
            (n, t)
            for n, t in self.db.execute(
                select(TaiSanKy.ky_nam, TaiSanKy.ky_thang).where(
                    TaiSanKy.trang_thai == KY_DA_CHOT, TaiSanKy.ky_nam * 12 + TaiSanKy.ky_thang > moc
                )
            )
        ]
        if sau:
            n, t = sorted(sau)[-1]
            raise KyDaChot(f"Kỳ {t:02d}/{n} đã chốt — mở lần lượt từ kỳ mới nhất trở về trước")

        self._chan_chung_tu_sau_ky(nam, thang)

        tru, so_mon = 0, 0
        for d in self.db.execute(
            select(TaiSanKhauHao).where(
                TaiSanKhauHao.ky_nam == nam, TaiSanKhauHao.ky_thang == thang
            )
        ).scalars():
            t = self.db.get(TaiSan, d.tai_san_id)
            if t is not None:
                t.hao_mon_luy_ke = int(t.hao_mon_luy_ke or 0) - int(d.muc_trich or 0)
                tru += int(d.muc_trich or 0)
                so_mon += 1

        k.trang_thai = KY_MO
        k.ngay_chot = None
        k.nguoi_chot_id = None
        self._ghi_vet(nam, thang, KY_LOG_MO, tru, so_mon, user_id)
        self.db.commit()
        return k
