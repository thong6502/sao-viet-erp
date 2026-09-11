"""Truy vấn bảng `xep_lich_lenh` + nạp routing THEO LÔ cho Xếp lịch 3.

Mọi đường đọc CẮT theo cửa sổ thời gian hoặc theo tập `lsx_id` — không có đường nào trải toàn bộ
lịch sử. Routing của cả lô nạp bằng MỘT truy vấn `IN (...)`, không N+1: một lần vẽ bảng có thể
duyệt vài chục lệnh, hỏi routing từng lệnh là đúng bài N+1 đã dính một lần ở màn đơn hàng.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.don_vi_do import DonViDo
from ..models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.san_xuat import (
    GOI_DANG_PHAT_HANH, SanXuatCongViec, SanXuatCongViecLichSu, SanXuatGoiPhatHanh,
)
from ..models.san_xuat_thuc_thi import SanXuatPhienChay
from ..models.xep_lich_lenh import XepLichLenh


class XepLichLenhRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- mốc

    def theo_lsx(self, lsx_id: int) -> XepLichLenh | None:
        return self.db.execute(
            select(XepLichLenh).where(XepLichLenh.lsx_id == lsx_id)
        ).scalar_one_or_none()

    def theo_nhieu_lsx(self, lsx_ids: list[int]) -> dict[int, XepLichLenh]:
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(XepLichLenh).where(XepLichLenh.lsx_id.in_(lsx_ids))
        ).scalars()
        return {r.lsx_id: r for r in rows}

    def truoc_moc(self, den: datetime) -> list[XepLichLenh]:
        """Lệnh CHẠM cửa sổ: mốc bắt đầu trước mép phải, HOẶC đã có phiên chạy trước mép phải.

        Vế thứ hai không thừa. Từ lúc mốc của lệnh chạy dở đổi nghĩa thành "bắt đầu phần CÒN LẠI",
        người điều độ đẩy mốc ra sau cửa sổ là chuyện thường — nhưng lệnh đã chạy từ trước đó và
        thanh của nó vẫn cắt ngang cửa sổ. Lọc mỗi `bat_dau_at` thì nó biến mất khỏi bàn.

        `san_xuat_phien_chay.bat_dau` là UTC THẬT còn `den` là giờ tường dán nhãn UTC, nên vế này
        LỎNG hơn thực tế đúng một offset máy chủ. Cố ý: lọt thừa vài lệnh thì service cắt lại
        chính xác sau khi trải, còn lọt thiếu là mất dòng.
        """
        da_chay = (
            select(SanXuatCongViec.lsx_id)
            .join(SanXuatPhienChay, SanXuatPhienChay.cong_viec_id == SanXuatCongViec.id)
            .where(SanXuatPhienChay.bat_dau <= den, SanXuatCongViec.lsx_id.is_not(None))
            .scalar_subquery()
        )
        return list(self.db.execute(
            select(XepLichLenh)
            .where(or_(XepLichLenh.bat_dau_at <= den, XepLichLenh.lsx_id.in_(da_chay)))
            .order_by(XepLichLenh.bat_dau_at)
        ).scalars())

    def them(self, row: XepLichLenh) -> XepLichLenh:
        self.db.add(row)
        self.db.flush()
        return row

    def xoa(self, row: XepLichLenh) -> None:
        self.db.delete(row)
        self.db.flush()

    # ---------------------------------------------------------------- lệnh

    def lsx_theo_ids(self, lsx_ids: list[int]) -> dict[int, Lsx]:
        if not lsx_ids:
            return {}
        rows = self.db.execute(select(Lsx).where(Lsx.id.in_(lsx_ids))).scalars()
        return {r.id: r for r in rows}

    def hang_cho(self, *, trang_thai: tuple[str, ...], tim: str | None,
                 trang: int, cd_trang: int) -> tuple[list[Lsx], int]:
        """Lệnh đủ điều kiện xếp mà CHƯA có mốc. Lọc + phân trang Ở MÁY CHỦ, luôn.

        Cắt trang trong JS sau khi kéo cả bảng về là đường đã bị bác một lần — thẻ hàng chờ có thể
        lên vài trăm khi xưởng dồn việc cuối tháng.
        """
        dieu_kien = [
            Lsx.trang_thai.in_(trang_thai),
            ~select(XepLichLenh.id).where(XepLichLenh.lsx_id == Lsx.id).exists(),
        ]
        if tim:
            mau = f"%{tim.strip()}%"
            dieu_kien.append(or_(Lsx.ma.ilike(mau), Lsx.ten.ilike(mau)))
        tong = self.db.execute(
            select(func.count()).select_from(Lsx).where(*dieu_kien)
        ).scalar_one()
        rows = list(self.db.execute(
            select(Lsx).where(*dieu_kien)
            # Gấp lên đầu, rồi tới hạn SX sớm nhất — đúng thứ tự người điều độ nhặt việc.
            .order_by(Lsx.is_rush.desc(), Lsx.han_hoan_thanh_sx.asc().nullslast(), Lsx.id)
            .offset(max(0, (trang - 1)) * cd_trang).limit(cd_trang)
        ).scalars())
        return rows, int(tong)

    # ---------------------------------------------------------------- routing

    def routing_theo_lo(self, lsx_ids: list[int]) -> dict[int, list[LsxCongDoan]]:
        """MỘT truy vấn cho cả lô. Gom theo `lsx_id`, sắp theo `thu_tu`."""
        if not lsx_ids:
            return {}
        rows = list(self.db.execute(
            select(LsxCongDoan)
            .where(LsxCongDoan.lsx_id.in_(lsx_ids))
            .order_by(LsxCongDoan.lsx_id, LsxCongDoan.thu_tu)
        ).scalars())
        out: dict[int, list[LsxCongDoan]] = {}
        for r in rows:
            out.setdefault(r.lsx_id, []).append(r)
        return out

    def phu_thuoc_theo_lo(self, cd_ids: list[int]) -> list[tuple[int, int]]:
        """Cạnh `(bước trước, bước sau)` giữa các bước TRONG tập đã cho. MỘT truy vấn."""
        if not cd_ids:
            return []
        trong = set(cd_ids)
        return [(a, b) for a, b in self.db.execute(
            select(LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoanPhuThuoc.buoc_sau_id)
            .where(LsxCongDoanPhuThuoc.buoc_sau_id.in_(cd_ids))
        ).all() if a in trong]

    # ---------------------------------------------------------------- máy đang giao chạy

    def may_dang_chay(self, lsx_ids: list[int]) -> dict[int, list[tuple[int | None, str | None, int]]]:
        """`{lsx_id: [(lsx_cong_doan_id, step_key, may_id)]}` — máy trên CÔNG VIỆC THỰC THI.

        Sau khi phát hành, máy thật của một bước nằm ở `san_xuat_cong_viec.may_id`: đó là ô mà
        `thuc_thi.doi_may` ghi vào, còn `lsx_cong_doan.may_id` giữ nguyên máy KẾ HOẠCH. Bàn xếp
        lịch phải nói máy nào đang cầm việc, không thì nó vẽ tiến độ trên một máy không chạy.

        Neo công đoạn của công việc là LỎNG (`lsx_cong_doan_id` + `step_key`, không FK — sửa
        routing là replace-all nên id tái sinh) nên trả CẢ HAI khoá, service ghép id trước rồi mới
        lùi về `step_key`. Không lọc `phien_ban_so` — cùng lối với `boi_canh` câu 5; sắp giảm dần
        để dòng của phiên bản mới nhất tới trước, service lấy dòng đầu tiên gặp.

        Bước bị BÀI GHÉP phủ dùng chung một công việc mang `lsx_id IS NULL` nên không lọt vào đây:
        bước đó lùi về máy kế hoạch, đúng như trước. Nối cả đường ghép cần `boi_canh` (năm truy vấn
        nữa) trong khi module bài ghép đang tắt — chưa đáng.
        """
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(
                SanXuatCongViec.lsx_id, SanXuatCongViec.lsx_cong_doan_id,
                SanXuatCongViec.step_key, SanXuatCongViec.may_id,
            )
            .where(
                SanXuatCongViec.lsx_id.in_(lsx_ids),
                SanXuatCongViec.may_id.isnot(None),
            )
            .order_by(
                SanXuatCongViec.lsx_id,
                SanXuatCongViec.phien_ban_so.desc(),
                SanXuatCongViec.phan_doan_so,
                SanXuatCongViec.id,
            )
        ).all()
        out: dict[int, list[tuple[int | None, str | None, int]]] = {}
        for lsx_id, cd_id, key, may_id in rows:
            out.setdefault(lsx_id, []).append((cd_id, key, may_id))
        return out

    def thuc_te_buoc(self, lsx_ids: list[int]) -> dict[int, list[tuple]]:
        """`{lsx_id: [(lsx_cong_doan_id, step_key, trang_thai, kh_bd, kh_kt, xong_luc, thuc_bd)]}`.

        Lớp THỰC TẾ của từng bước, cho panel bày cạnh lớp kế hoạch. Hai truy vấn, cắt theo tập
        `lsx_id` — cùng ranh giới hiệu năng với `may_dang_chay` (spec §4.1).

        LỌC THEO GÓI ĐANG PHÁT HÀNH, không lọc `phien_ban_so`: "Phát hành cập nhật" chỉ tái chụp
        các việc CHƯA bắt đầu, nên việc ĐÃ bắt đầu ở lại `phien_ban_so` cũ. Lọc theo phiên bản
        hiện tại là làm biến mất đúng những bước có thực tế để bày — thứ duy nhất panel này sinh
        ra để nói. Lệnh đã THU HỒI rồi phát hành lại có hai gói; chỉ gói `dang_phat_hanh` lọt.

        `thuc_bd` là mốc phiên chạy ĐẦU TIÊN (`min(bat_dau)`), UTC THẬT — khác thang với `kh_*`
        (giờ tường dán nhãn UTC). Service bọc bằng `gio_xuong` trước khi trả ra, xem
        `services/gio_xuong.py`.

        Bước bị BÀI GHÉP phủ mang `lsx_id IS NULL` nên không lọt vào đây — cùng giới hạn đã ghi ở
        `may_dang_chay`, bước đó chỉ có lớp kế hoạch.
        """
        if not lsx_ids:
            return {}
        goi_dang = (
            select(SanXuatGoiPhatHanh.id)
            .where(SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH)
            .scalar_subquery()
        )
        rows = self.db.execute(
            select(
                SanXuatCongViec.id, SanXuatCongViec.lsx_id, SanXuatCongViec.lsx_cong_doan_id,
                SanXuatCongViec.step_key, SanXuatCongViec.trang_thai,
                SanXuatCongViec.du_kien_bat_dau, SanXuatCongViec.du_kien_ket_thuc,
                SanXuatCongViec.hoan_thanh_luc,
            )
            .where(
                SanXuatCongViec.lsx_id.in_(lsx_ids),
                SanXuatCongViec.goi_id.in_(goi_dang),
            )
            .order_by(
                SanXuatCongViec.lsx_id,
                SanXuatCongViec.phien_ban_so.desc(),
                SanXuatCongViec.phan_doan_so,
                SanXuatCongViec.id,
            )
        ).all()
        if not rows:
            return {}
        moc = dict(self.db.execute(
            select(SanXuatPhienChay.cong_viec_id, func.min(SanXuatPhienChay.bat_dau))
            .where(SanXuatPhienChay.cong_viec_id.in_([r[0] for r in rows]))
            .group_by(SanXuatPhienChay.cong_viec_id)
        ).all())
        ra: dict[int, list[tuple]] = {}
        for cv_id, lsx_id, cd_id, key, tt, kh_bd, kh_kt, xong in rows:
            ra.setdefault(lsx_id, []).append(
                (cd_id, key, tt, kh_bd, kh_kt, xong, moc.get(cv_id))
            )
        return ra

    def lich_su_lich(self, lsx_id: int) -> tuple[list, list]:
        """`(công việc SỐNG, dòng lịch sử)` của gói đang phát hành cho MỘT lệnh — hai truy vấn.

        Dòng sống mang trạng thái của MỌI phiên bản kể từ `cv.phien_ban_so` trở đi; dòng lịch sử
        mang trạng thái đã bị đè, khoá bằng số phiên bản CŨ. Hai tập này ghép lại mới đủ để dựng
        "bước X ở phiên bản N trông thế nào" — xem `XepLich3Service.so_sanh_phien_ban`.

        Bước bị BÀI GHÉP phủ (`lsx_id IS NULL`) không lọt vào đây, cùng giới hạn `may_dang_chay`.
        """
        goi_dang = (
            select(SanXuatGoiPhatHanh.id)
            .where(SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH)
            .scalar_subquery()
        )
        cvs = list(self.db.execute(
            select(SanXuatCongViec)
            .where(
                SanXuatCongViec.lsx_id == lsx_id,
                SanXuatCongViec.goi_id.in_(goi_dang),
            )
            .order_by(SanXuatCongViec.phan_doan_so, SanXuatCongViec.id)
        ).scalars())
        if not cvs:
            return [], []
        ls = list(self.db.execute(
            select(SanXuatCongViecLichSu)
            .where(SanXuatCongViecLichSu.cong_viec_id.in_([c.id for c in cvs]))
            .order_by(SanXuatCongViecLichSu.cong_viec_id,
                      SanXuatCongViecLichSu.phien_ban_so)
        ).scalars())
        return cvs, ls

    # ---------------------------------------------------------------- đơn vị đo

    def ten_don_vi(self, ma: list[str]) -> dict[str, str]:
        """`{mã: tên hiển thị}`. Bảng lưu MÃ (`to`, `con`), người đọc cần chữ (`tờ in`, `con`)."""
        if not ma:
            return {}
        return {
            r.ma: r.ten for r in self.db.execute(
                select(DonViDo).where(DonViDo.ma.in_(ma))
            ).scalars()
        }
