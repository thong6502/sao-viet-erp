"""Data-access cho module Thực hiện sản xuất (Giai đoạn 1: nhóm & phát hành).

Giữ đúng tầng: mọi truy vấn/ghi DB của module gom ở đây; service chỉ điều phối. Gồm HAI nhóm:

  · ĐỒ THỊ LIÊN THÔNG — đọc quan hệ có sẵn (bài ghép ↔ thành viên, phụ thuộc chéo giữa LSX,
    cùng nhóm đơn hàng, routing, thời gian đã xếp) để tính thành phần liên thông + dựng snapshot.
  · GHI SNAPSHOT — upsert nhóm/thành viên + tạo gói/phiên bản/công việc/phụ thuộc.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep, BaiGhepThanhVien
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.customer import Customer
from ..models.department import Department
from ..models.employee import Employee
from ..models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ..models.may_thiet_bi import MayThietBi
from ..models.order import Order, OrderLine
from ..models.san_xuat import (
    CV_HOAN_THANH,
    GOI_DANG_PHAT_HANH,
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatNhomLsx,
    SanXuatPhienBan,
    SanXuatPhuThuoc,
)
from ..models.san_xuat_kcs import SanXuatKcsTieuChi
from ..models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from ..models.user import User
from ..models.xep_lich import XepLichCongDoan


class SanXuatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ================= ĐỒ THỊ LIÊN THÔNG =================

    def bai_ghep_ids_cua_lsx(self, lsx_ids: set[int]) -> set[int]:
        """Bài ghép nào có thành viên nằm trong tập LSX này."""
        if not lsx_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.bai_ghep_id).where(
                BaiGhepThanhVien.lsx_id.in_(lsx_ids)
            )
        ).scalars()
        return set(rows)

    def thanh_vien_so_con(self, bg_ids: set[int]) -> dict[int, int]:
        """`lsx_id → so_con_tren_to` của thành viên trong tập bài ghép — tỷ lệ toả sản lượng khi
        điểm toả tách batch chung thành sản lượng riêng từng LSX (§ điểm toả)."""
        if not bg_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id, BaiGhepThanhVien.so_con_tren_to).where(
                BaiGhepThanhVien.bai_ghep_id.in_(bg_ids)
            )
        ).all()
        return {lsx_id: int(con or 0) for lsx_id, con in rows}

    def lsx_ids_cua_bai_ghep(self, bg_ids: set[int]) -> set[int]:
        """Toàn bộ LSX thành viên của các bài ghép này."""
        if not bg_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id).where(
                BaiGhepThanhVien.bai_ghep_id.in_(bg_ids)
            )
        ).scalars()
        return set(rows)

    def cross_lsx_dep_neighbors(self, lsx_ids: set[int]) -> set[int]:
        """LSX nối với tập này qua cạnh phụ thuộc CHÉO (hai bước thuộc hai LSX khác nhau)."""
        edges = self._cross_lsx_edges_all()
        out: set[int] = set()
        for a, b in edges:
            if a in lsx_ids:
                out.add(b)
            if b in lsx_ids:
                out.add(a)
        return out

    def _cross_lsx_edges_all(self) -> list[tuple[int, int]]:
        """Mọi cạnh phụ thuộc chéo dưới dạng (lsx_truoc_id, lsx_sau_id), chỉ giữ cạnh KHÁC LSX."""
        Truoc = LsxCongDoan.__table__.alias("bt")
        Sau = LsxCongDoan.__table__.alias("bs")
        rows = self.db.execute(
            select(Truoc.c.lsx_id, Sau.c.lsx_id)
            .select_from(
                LsxCongDoanPhuThuoc.__table__
                .join(Truoc, LsxCongDoanPhuThuoc.buoc_truoc_id == Truoc.c.id)
                .join(Sau, LsxCongDoanPhuThuoc.buoc_sau_id == Sau.c.id)
            )
        ).all()
        return [(a, b) for (a, b) in rows if a != b]

    def cross_lsx_edges_chi_tiet(self, lsx_ids: set[int]) -> list[tuple[LsxCongDoan, LsxCongDoan]]:
        """Cạnh phụ thuộc chéo (buoc_truoc, buoc_sau) mà CẢ HAI bước thuộc LSX trong tập — dùng
        dựng snapshot bước ghép. Chỉ giữ cạnh nối hai LSX khác nhau (§3.2)."""
        if not lsx_ids:
            return []
        from sqlalchemy.orm import aliased

        Truoc = aliased(LsxCongDoan)
        Sau = aliased(LsxCongDoan)
        # MỘT truy vấn lọc sẵn theo lệnh — trước đây quét cả bảng cạnh rồi `db.get` từng đầu mút.
        rows = self.db.execute(
            select(Truoc, Sau)
            .select_from(LsxCongDoanPhuThuoc)
            .join(Truoc, LsxCongDoanPhuThuoc.buoc_truoc_id == Truoc.id)
            .join(Sau, LsxCongDoanPhuThuoc.buoc_sau_id == Sau.id)
            .where(
                Truoc.lsx_id.in_(lsx_ids), Sau.lsx_id.in_(lsx_ids), Truoc.lsx_id != Sau.lsx_id,
            )
            .order_by(LsxCongDoanPhuThuoc.buoc_truoc_id, LsxCongDoanPhuThuoc.buoc_sau_id)
        ).all()
        return [(truoc, sau) for truoc, sau in rows]

    def same_group_lsx(self, lsx_ids: set[int]) -> set[int]:
        """LSX cùng (order_id, nhom) với bất kỳ LSX nào trong tập — nhóm thành phẩm nối chúng
        thành một khối phát hành (§3.1). Dòng không có `nhom` KHÔNG kéo theo LSX khác."""
        if not lsx_ids:
            return set()
        keys = self._group_keys_of(lsx_ids)
        labelled = {(oid, nhom) for (oid, nhom) in keys if nhom is not None}
        if not labelled:
            return set()
        out: set[int] = set()
        rows = self.db.execute(
            select(Lsx.id, Lsx.order_id, OrderLine.nhom)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(OrderLine.nhom.is_not(None))
        ).all()
        for lid, oid, nhom in rows:
            if (oid, nhom) in labelled:
                out.add(lid)
        return out

    def _group_keys_of(self, lsx_ids: set[int]) -> set[tuple[int, str | None]]:
        rows = self.db.execute(
            select(Lsx.order_id, OrderLine.nhom)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(Lsx.id.in_(lsx_ids))
        ).all()
        return {(oid, nhom) for (oid, nhom) in rows}

    def nguon_nhom_cua_lsx(self, lsx_id: int) -> tuple[int, int, str | None, str] | None:
        """(order_id, order_line_id, nhom, description) của một LSX; None nếu thiếu dòng đơn."""
        row = self.db.execute(
            select(Lsx.order_id, Lsx.order_line_id, OrderLine.nhom, OrderLine.description)
            .join(OrderLine, Lsx.order_line_id == OrderLine.id)
            .where(Lsx.id == lsx_id)
        ).first()
        return tuple(row) if row is not None else None

    def routing_steps(self, lsx_id: int) -> list[LsxCongDoan]:
        return list(
            self.db.execute(
                select(LsxCongDoan)
                .where(LsxCongDoan.lsx_id == lsx_id)
                .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
            ).scalars()
        )

    def bai_ghep_cong_doans(self, bg_id: int) -> list[BaiGhepCongDoan]:
        return list(
            self.db.execute(
                select(BaiGhepCongDoan)
                .where(BaiGhepCongDoan.bai_ghep_id == bg_id)
                .order_by(BaiGhepCongDoan.thu_tu, BaiGhepCongDoan.id)
            ).scalars()
        )

    def step_keys_da_ghep(self, bg_id: int) -> set[str]:
        """`lsx_step_key` của các bước LSX đã bị gộp vào bước dùng chung của bài ghép — để KHỎI
        đẻ công việc trùng cho bước đó ở tầng LSX (§3.3: một bài ghép = một bản ghi thực hiện)."""
        cd_ids = [
            cd.id for cd in self.bai_ghep_cong_doans(bg_id)
        ]
        if not cd_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_(cd_ids)
            )
        ).scalars()
        return set(rows)

    def covered_step_keys_of_cd(self, bai_ghep_cong_doan_id: int) -> set[str]:
        """`lsx_step_key` mà MỘT bước dùng chung của bài ghép gộp lại (để nối phụ thuộc về đúng
        công việc dùng chung)."""
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id
            )
        ).scalars()
        return set(rows)

    def lsx_ids_covered_by_cd(self, bai_ghep_cong_doan_id: int) -> set[int]:
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.lsx_id).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id
            )
        ).scalars()
        return set(rows)

    def lich_lsx_step(
        self, lsx_cong_doan_id: int
    ) -> list[tuple[int | None, object, object, int, object]]:
        """MỌI phân đoạn đã xếp của một bước lệnh, sắp theo `phan_doan_so`.

        Trước đây một bước = một dòng lịch nên `thoi_gian_lsx_step` trả đúng một bộ. Từ khi tách
        được lần chạy (spec-thuc-te-vs-ke-hoach §2.4), một bước có N dòng — phát hành phải đẻ N
        công việc, không thì phân đoạn 2 trở đi biến mất khỏi bàn tổ mà không ai báo.

        Mỗi phần tử: `(may_id, start_at, finish_at, phan_doan_so, so_luong)`. `so_luong` là Decimal
        hoặc None; None = dòng chưa tách, mang TRỌN số lượng của bước — KHÁC 0, chỗ gọi phải phân
        biệt chứ đừng ép về 0.
        """
        return [
            (r.may_id, r.start_at, r.finish_at, r.phan_doan_so, r.so_luong)
            for r in self.db.execute(
                select(
                    XepLichCongDoan.may_id,
                    XepLichCongDoan.start_at,
                    XepLichCongDoan.finish_at,
                    XepLichCongDoan.phan_doan_so,
                    XepLichCongDoan.so_luong,
                )
                .where(XepLichCongDoan.lsx_cong_doan_id == lsx_cong_doan_id)
                .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
            )
        ]

    def lich_bg_step(
        self, bai_ghep_cong_doan_id: int
    ) -> list[tuple[int | None, object, object, int, object]]:
        """Như `lich_lsx_step` nhưng cho bước chạy chung của bài ghép."""
        return [
            (r.may_id, r.start_at, r.finish_at, r.phan_doan_so, r.so_luong)
            for r in self.db.execute(
                select(
                    XepLichCongDoan.may_id,
                    XepLichCongDoan.start_at,
                    XepLichCongDoan.finish_at,
                    XepLichCongDoan.phan_doan_so,
                    XepLichCongDoan.so_luong,
                )
                .where(XepLichCongDoan.bai_ghep_cong_doan_id == bai_ghep_cong_doan_id)
                .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
            )
        ]

    def checklist_theo_cong_doan(self, cong_doan_ids: set[int]) -> dict[int, list[SanXuatKcsTieuChi]]:
        """{cong_doan_id: [hạng mục kiểm active, sort thu_tu rồi id]} — MỘT truy vấn cho cả gói."""
        if not cong_doan_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatKcsTieuChi)
            .where(
                SanXuatKcsTieuChi.cong_doan_id.in_(cong_doan_ids),
                SanXuatKcsTieuChi.active.is_(True),
            )
            .order_by(SanXuatKcsTieuChi.thu_tu, SanXuatKcsTieuChi.id)
        ).scalars()
        out: dict[int, list[SanXuatKcsTieuChi]] = {}
        for tc in rows:
            out.setdefault(tc.cong_doan_id, []).append(tc)
        return out

    # ================= GHI SNAPSHOT =================

    def get_nhom(self, order_id: int, khoa: str) -> SanXuatNhom | None:
        return self.db.execute(
            select(SanXuatNhom).where(
                SanXuatNhom.order_id == order_id, SanXuatNhom.khoa == khoa
            )
        ).scalar_one_or_none()

    def add(self, obj):
        self.db.add(obj)
        return obj

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def lenh_cua_nhom(self, nhom_id: int) -> list[tuple[Lsx, SanXuatNhomLsx]]:
        """`[(lệnh, dòng thành viên)]` của MỌI lệnh trong nhóm, theo id lệnh. Dòng đơn của thành viên
        đọc `SanXuatNhomLsx.order_line_id`, rỗng thì `Lsx.order_line_id` (cột nullable phía nhóm)."""
        return [
            (lsx, tv)
            for lsx, tv in self.db.execute(
                select(Lsx, SanXuatNhomLsx)
                .join(SanXuatNhomLsx, SanXuatNhomLsx.lsx_id == Lsx.id)
                .where(SanXuatNhomLsx.nhom_id == nhom_id)
                .order_by(Lsx.id)
            ).all()
        ]

    def member_of_lsx(self, lsx_id: int) -> SanXuatNhomLsx | None:
        return self.db.execute(
            select(SanXuatNhomLsx).where(SanXuatNhomLsx.lsx_id == lsx_id)
        ).scalar_one_or_none()

    def goi_hien_tai_cua(
        self, lsx_ids: set[int], bai_ghep_ids: set[int]
    ) -> SanXuatGoiPhatHanh | None:
        """Gói phát hành đang hiệu lực có công việc trỏ tới bất kỳ LSX/bài ghép nào trong tập —
        để KHỎI đẻ gói trùng khi tái phát hành (versioning cập nhật §4.3 làm ở lát sau)."""
        conds = []
        if lsx_ids:
            conds.append(SanXuatCongViec.lsx_id.in_(lsx_ids))
        if bai_ghep_ids:
            conds.append(SanXuatCongViec.bai_ghep_id.in_(bai_ghep_ids))
        if not conds:
            return None
        from sqlalchemy import or_

        return self.db.execute(
            select(SanXuatGoiPhatHanh)
            .join(SanXuatCongViec, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH, or_(*conds))
            .limit(1)
        ).scalar_one_or_none()

    def goi_dang_phat_hanh(self, goi_id: int) -> bool:
        """Gói còn hiệu lực? Thu hồi rồi thì công việc vẫn nằm đó nhưng tổ không còn thấy."""
        return self.db.execute(
            select(SanXuatGoiPhatHanh.id).where(
                SanXuatGoiPhatHanh.id == goi_id,
                SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            )
        ).first() is not None

    def cong_viec_cua_goi(self, goi_id: int) -> list[SanXuatCongViec]:
        """Mọi công việc của một gói (không lọc phiên bản) — §4.3 chia đã/chưa bắt đầu để cập nhật."""
        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .where(SanXuatCongViec.goi_id == goi_id)
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )

    def cong_viec_cua_goi_cho_lenh(
        self, goi_ids: set[int], lsx_ids: set[int]
    ) -> list[SanXuatCongViec]:
        """Bước của MỌI TỔ trong các gói đã cho — nguồn của dải routing trên bàn tổ.

        Khác `cong_viec_cua_lenh` ở đúng một chỗ, nhưng là chỗ cốt lõi: KHÔNG lọc
        `department_id`. Bàn tổ lọc theo tổ để ra danh sách VIỆC; dải thì cần cả chuỗi, kể cả
        bước của tổ khác.

        Lấy hai nhánh: bước RIÊNG của các lệnh trong trang, và MỌI bước chạy chung của bài ghép
        trong cùng gói (bước chung neo `bai_ghep_id`, `lsx_id` để trống nên không lọc theo lệnh
        được — bên gọi nối lại qua `bai_ghep_phu_step_key`).
        """
        if not goi_ids or not lsx_ids:
            return []
        from sqlalchemy import or_

        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .where(
                    SanXuatCongViec.goi_id.in_(goi_ids),
                    or_(
                        SanXuatCongViec.lsx_id.in_(lsx_ids),
                        SanXuatCongViec.bai_ghep_cong_doan_id.is_not(None),
                    ),
                )
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )

    def thu_tu_theo_step_key(self, lsx_ids: set[int]) -> dict[str, tuple[int, int]]:
        """{step_key: (lsx_id, thu_tu)} cho cả một trang bàn tổ — MỘT truy vấn.

        `san_xuat_cong_viec` KHÔNG có cột thứ tự, nên thứ tự dải phải tra ngược về
        `lsx_cong_doan.thu_tu`. Đọc routing SỐNG ở đây là an toàn: phát hành đã khoá routing
        (`da_phat_hanh`) nên `thu_tu` không đổi dưới chân snapshot.

        ĐỪNG sắp dải theo `du_kien_bat_dau` như `cong_viec_cua_lenh` làm cho danh sách việc —
        lệnh chưa đặt giờ thì mốc trống và dải nhảy lung tung.
        """
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(LsxCongDoan.step_key, LsxCongDoan.lsx_id, LsxCongDoan.thu_tu)
            .where(LsxCongDoan.lsx_id.in_(lsx_ids), LsxCongDoan.step_key.is_not(None))
        ).all()
        return {sk: (lid, tt) for sk, lid, tt in rows}

    def bai_ghep_phu_step_key(self, lsx_ids: set[int]) -> dict[int, list[str]]:
        """{bai_ghep_cong_doan_id: [lsx_step_key, …]} — bước chạy chung PHỦ lên bước nào của lệnh.

        Bước chung của bài ghép mang `step_key` của CHÍNH bài ghép, không phải của lệnh, nên nối
        vào dải của một lệnh phải đi qua bảng map này.
        """
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhepCongDoanMap.bai_ghep_cong_doan_id, BaiGhepCongDoanMap.lsx_step_key)
            .where(BaiGhepCongDoanMap.lsx_id.in_(lsx_ids))
        ).all()
        ra: dict[int, list[str]] = {}
        for bgcd_id, sk in rows:
            if sk:
                ra.setdefault(bgcd_id, []).append(sk)
        return ra

    # ================= ĐÓNG NHÓM THÀNH PHẨM (§16) =================

    def nhom(self, nhom_id: int) -> SanXuatNhom | None:
        return self.db.get(SanXuatNhom, nhom_id)

    def lsx(self, lsx_id: int) -> Lsx | None:
        return self.db.get(Lsx, lsx_id)

    def don_vi_ra_cua(self, cong_viec_ids) -> dict[int, str | None]:
        """`{cong_viec_id: đơn vị ra}` — một câu cho cả tập."""
        ids = {int(i) for i in cong_viec_ids if i}
        if not ids:
            return {}
        return {int(i): dv for i, dv in self.db.execute(
            select(SanXuatCongViec.id, SanXuatCongViec.don_vi_ra)
            .where(SanXuatCongViec.id.in_(ids))).all()}

    def cong_viec(self, cong_viec_id: int) -> SanXuatCongViec | None:
        """Một công việc theo id — router dùng để lần ra `nhom_id` khi bắn chốt-chặn đóng nhóm."""
        return self.db.get(SanXuatCongViec, cong_viec_id)

    def khoa_cong_viec(self, cong_viec_id: int) -> None:
        """Khoá DÒNG công việc (SELECT … FOR UPDATE) để hai lượt ghi lên CÙNG công đoạn phải xếp
        hàng. Cùng khuôn `StockRequestRepository.lock_for_update`: Postgres cho lượt sau CHỜ rồi
        đọc lại trạng thái mới; SQLite coi `FOR UPDATE` là no-op nhưng tự khoá ghi cả DB nên vẫn
        tuần tự.

        Người gọi đầu tiên là `vat_tu_de_nghi.tao()`: tổ trưởng bấm "Gửi đề nghị" hai lần thì hai
        lượt cùng đọc `lan_ke_tiep = 1`, cả hai đẻ yêu cầu kho (repo kho tự COMMIT), rồi một lượt
        vỡ `UniqueConstraint("cong_viec_id", "lan_so")` — để lại một yêu cầu kho MỒ CÔI không có
        `SanXuatVatTuDeNghi` nào trỏ tới, tức thủ kho thấy một yêu cầu không rõ công đoạn/giờ cần
        và vẫn soạn hàng lần thứ hai. Vì thế phải gọi TRƯỚC khi đọc `lan_ke_tiep`, không phải
        trước khi ghi.
        """
        self.db.execute(
            select(SanXuatCongViec.id)
            .where(SanXuatCongViec.id == cong_viec_id)
            .with_for_update()
        ).first()

    def cong_viec_hien_tai_cua_nhom(self, nhom_id: int) -> list[SanXuatCongViec]:
        """Công việc SỐNG của nhóm — bỏ gói đã thu hồi. Đây là tập việc mà cổng đóng nhóm §16 soi.

        KHÔNG lọc thêm `phien_ban_so == version_hien_tai`: "Phát hành cập nhật" (§4.3) SỬA TRỰC
        TIẾP dòng `SanXuatCongViec` đã có (không đẻ dòng mới), chỉ bump `phien_ban_so` cho việc
        CHƯA bắt đầu; việc đã bắt đầu giữ nguyên dòng với `phien_ban_so` cũ. Lọc bằng nhau ở đây
        từng khiến việc đã chạy trước lần cập nhật bị rớt khỏi xét đóng nhóm — cùng một dòng, cùng
        đang sống, không phải bản "cũ bị thay thế"."""
        return list(
            self.db.execute(
                select(SanXuatCongViec)
                .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
                .where(
                    SanXuatCongViec.nhom_id == nhom_id,
                    SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
                )
                .order_by(SanXuatCongViec.id)
            ).scalars()
        )

    # ================= ĐỌC BÀN THỰC HIỆN TẠI TỔ (§11, §18 /work-items) =================

    def cong_viec_cua_to(
        self,
        department_ids: set[int],
        *,
        chi_chua_xong: bool = False,
        employee_id: int | None = None,
        rieng_ids: set[int] | None = None,
    ) -> list[SanXuatCongViec]:
        """Công việc ĐÃ PHÁT HÀNH mà tổ (`department_id`) phải làm — timeline bàn tổ. Chỉ đọc gói
        đang hiệu lực (bỏ gói đã thu hồi). Sắp theo giờ dự kiến (chưa xếp giờ dồn cuối), rồi id.

        `employee_id` / `rieng_ids`: phạm vi tổ, xem `_pham_vi_to`."""
        pham_vi = self._pham_vi_to(department_ids, employee_id, rieng_ids)
        if pham_vi is None:
            return []
        q = (
            select(SanXuatCongViec)
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(
                pham_vi,
                SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            )
        )
        if chi_chua_xong:
            q = q.where(SanXuatCongViec.trang_thai != CV_HOAN_THANH)
        rows = list(self.db.execute(q).scalars())
        rows.sort(key=lambda cv: (cv.du_kien_bat_dau is None, cv.du_kien_bat_dau, cv.id))
        return rows

    # ---- Bàn tổ trục LỆNH (spec 2026-09-11) --------------------------------------------------
    #
    # Đơn vị VIỆC vẫn là CÔNG ĐOẠN — `SanXuatCongViec` là một bước của lệnh, và đó vẫn là thứ tổ
    # bấm Bắt đầu / Ghi sản lượng. Hai hàm dưới chỉ đổi CÁCH BÀY: bọc các bước ấy dưới đầu mục
    # LỆNH / BÀI GHÉP, và cắt trang theo LỆNH. Cắt theo BƯỚC thì một lệnh bị xé qua hai trang, tổ
    # trưởng mở trang 2 thấy một công đoạn trơ trọi không biết của lệnh nào.

    @staticmethod
    def _khoa_lenh_cols():
        """(cột LOẠI nguồn, cột ID nguồn) suy ngay trong SQL — cùng luật với `board._item_dict`.

        Bài ghép THẮNG lệnh khi bước đeo cả hai: bài ghép chạy MỘT lần trên MỘT tờ, tổ nhìn nó là
        một việc. Xẻ nó theo từng lệnh thành viên là đẻ ra mấy dòng cho một lần chạy máy.
        """
        from sqlalchemy import case, literal

        co_bg = SanXuatCongViec.bai_ghep_id.is_not(None)
        loai = case((co_bg, literal("bai_ghep")), else_=literal("lsx"))
        nid = case((co_bg, SanXuatCongViec.bai_ghep_id), else_=SanXuatCongViec.lsx_id)
        return loai, nid

    def lenh_cua_to_phan_trang(
        self,
        department_ids: set[int],
        *,
        employee_id: int | None = None,
        rieng_ids: set[int] | None = None,
        tim: str | None = None,
        trang: int = 1,
        co_trang: int = 20,
        chi_cong_viec_ids: set[int] | None = None,
        trang_thai: set[str] | None = None,
        nhan_tu: datetime | None = None,
        nhan_den: datetime | None = None,
        sap_xep: str = "moi_nhan",
    ) -> tuple[list[tuple[tuple[str, int | None], datetime | None, datetime | None]], int]:
        """Một TRANG các LỆNH/BÀI GHÉP mà tổ phải làm + tổng số lệnh.

        Mỗi phần tử: `((loai, id), sớm_nhất, muộn_nhất)` — hai mốc là giờ dự kiến của bước SỚM/MUỘN
        NHẤT **của chính tổ này** trong lệnh đó, không phải mốc của cả lệnh: bàn tổ sắp theo thứ tự
        việc đến tay TỔ.

        Cắt trang theo LỆNH (không theo bước) và cắt ở SQL. `employee_id` (thợ mở bàn) lọc NGAY
        trong câu gom — lọc sau khi cắt trang thì trang 1 có thể rỗng trong khi trang 3 đầy việc.

        Lệnh chưa xếp giờ dồn CUỐI (`NULLS LAST` viết tay bằng CASE cho chạy cả PG lẫn SQLite).

        `tim` cũng lọc Ở ĐÂY chứ không lọc bằng JS sau khi kéo trang về — lọc sau khi cắt trang
        thì ô tìm kiếm chỉ soi được đúng 20 lệnh đang hiện. Từ khoá soi mã/tên LỆNH, mã/tên BÀI
        GHÉP, tên KHÁCH (của lệnh, hoặc của lệnh thành viên bài ghép) và tên CÔNG ĐOẠN; khớp một
        bước là cả lệnh hiện ra (bàn tổ đi tìm LỆNH, không đi tìm
        bước rời).

        `chi_cong_viec_ids` (ô "chờ xác nhận"): chỉ giữ lệnh chứa ít nhất một bước trong tập. Lọc
        bằng HAVING chứ không WHERE — WHERE bỏ các bước khác của lệnh nên mốc sớm/muộn (thứ tự
        trang) lệch khỏi bàn không lọc. Tập rỗng ⇒ trang rỗng.

        Lọc nâng cao của bàn (19/09/2026) — cũng HAVING, cũng trước khi cắt trang:
        · `trang_thai`: giữ lệnh có ÍT NHẤT MỘT bước của tổ ở một trong các trạng thái ấy.
        · `nhan_tu`/`nhan_den` (UTC THẬT, nửa mở `[tu, den)`): lúc tổ NHẬN lệnh — `created_at`
          sớm nhất của các bước của tổ, cùng mốc bàn hiện "Nhận …" ở đầu lệnh.
        `sap_xep`: `moi_nhan` (mặc định — lệnh phát hành xuống tổ SAU nằm TRÊN), `cu_nhan`, hoặc
        `du_kien` (giờ dự kiến bước sớm nhất của tổ, lệnh chưa xếp giờ dồn cuối).
        """
        pham_vi = self._pham_vi_to(department_ids, employee_id, rieng_ids)
        if pham_vi is None or (chi_cong_viec_ids is not None and not chi_cong_viec_ids):
            return [], 0
        from sqlalchemy import case as sa_case, func, select as sa_select

        loai, nid = self._khoa_lenh_cols()
        som = func.min(SanXuatCongViec.du_kien_bat_dau)
        muon = func.max(SanXuatCongViec.du_kien_ket_thuc)
        nhan = func.min(SanXuatCongViec.created_at)
        dieu_kien = [
            pham_vi,
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
        ]

        nhom = (
            sa_select(loai.label("loai"), nid.label("nid"),
                      som.label("som"), muon.label("muon"))
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
        )
        kw = (tim or "").strip()
        if kw:
            from sqlalchemy import or_

            from sqlalchemy.orm import aliased

            mau = f"%{kw}%"
            nhom = (
                nhom.outerjoin(Lsx, SanXuatCongViec.lsx_id == Lsx.id)
                .outerjoin(Order, Lsx.order_id == Order.id)
                .outerjoin(Customer, Order.customer_id == Customer.id)
                .outerjoin(BaiGhep, SanXuatCongViec.bai_ghep_id == BaiGhep.id)
            )
            # Khách của BÀI GHÉP là khách các lệnh thành viên — EXISTS chứ không JOIN, join thì mỗi
            # bước nhân lên theo số thành viên.
            lsx_tv, don_tv, khach_tv = aliased(Lsx), aliased(Order), aliased(Customer)
            khach_bai_ghep = (
                sa_select(BaiGhepThanhVien.id)
                .join(lsx_tv, BaiGhepThanhVien.lsx_id == lsx_tv.id)
                .join(don_tv, lsx_tv.order_id == don_tv.id)
                .join(khach_tv, don_tv.customer_id == khach_tv.id)
                .where(BaiGhepThanhVien.bai_ghep_id == SanXuatCongViec.bai_ghep_id,
                       khach_tv.name.ilike(mau))
                .exists()
            )
            dieu_kien.append(or_(
                Lsx.ma.ilike(mau), Lsx.ten.ilike(mau), Customer.name.ilike(mau),
                BaiGhep.ma.ilike(mau), BaiGhep.ten.ilike(mau), khach_bai_ghep,
                SanXuatCongViec.ten_cong_doan.ilike(mau),
            ))
        nhom = nhom.where(*dieu_kien).group_by(loai, nid)
        if chi_cong_viec_ids is not None:
            nhom = nhom.having(func.sum(sa_case(
                (SanXuatCongViec.id.in_(chi_cong_viec_ids), 1), else_=0)) > 0)
        if trang_thai:
            nhom = nhom.having(func.sum(sa_case(
                (SanXuatCongViec.trang_thai.in_(trang_thai), 1), else_=0)) > 0)
        if nhan_tu is not None:
            nhom = nhom.having(nhan >= nhan_tu)
        if nhan_den is not None:
            nhom = nhom.having(nhan < nhan_den)
        tong = self.db.scalar(sa_select(func.count()).select_from(nhom.subquery())) or 0

        co_trang = max(1, min(int(co_trang or 20), 100))
        trang = max(1, int(trang or 1))
        if sap_xep == "du_kien":
            thu_tu = (sa_case((som.is_(None), 1), else_=0), som, nid)
        elif sap_xep == "cu_nhan":
            thu_tu = (nhan, nid)
        else:
            thu_tu = (nhan.desc(), nid.desc())
        rows = self.db.execute(
            nhom.order_by(*thu_tu)
            .limit(co_trang)
            .offset((trang - 1) * co_trang)
        ).all()
        return [((r.loai, r.nid), r.som, r.muon) for r in rows], int(tong)

    def cong_viec_cua_lenh(
        self,
        department_ids: set[int],
        khoa: list[tuple[str, int | None]],
        *,
        employee_id: int | None = None,
        rieng_ids: set[int] | None = None,
    ) -> list[SanXuatCongViec]:
        """Mọi bước CỦA TỔ thuộc các lệnh/bài ghép trong danh sách khoá — một truy vấn cho cả trang.

        Ghép điều kiện bằng ba nhánh OR đích danh thay vì `IN` trên tuple: `IN ((a,b),…)` không
        portable giữa Postgres và SQLite, mà phân trang thì bắt buộc chạy đúng trên cả hai.
        """
        pham_vi = self._pham_vi_to(department_ids, employee_id, rieng_ids)
        if pham_vi is None or not khoa:
            return []
        from sqlalchemy import false, or_

        bg_ids = {i for loai, i in khoa if loai == "bai_ghep" and i is not None}
        lsx_ids = {i for loai, i in khoa if loai == "lsx" and i is not None}
        co_mo_coi = any(loai == "lsx" and i is None for loai, i in khoa)

        nhanh = []
        if bg_ids:
            nhanh.append(SanXuatCongViec.bai_ghep_id.in_(bg_ids))
        if lsx_ids:
            nhanh.append(
                (SanXuatCongViec.bai_ghep_id.is_(None))
                & (SanXuatCongViec.lsx_id.in_(lsx_ids))
            )
        if co_mo_coi:
            nhanh.append(
                (SanXuatCongViec.bai_ghep_id.is_(None))
                & (SanXuatCongViec.lsx_id.is_(None))
            )

        dieu_kien = [
            pham_vi,
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
            or_(*nhanh) if nhanh else false(),
        ]

        rows = list(
            self.db.execute(
                select(SanXuatCongViec)
                .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
                .where(*dieu_kien)
            ).scalars()
        )
        rows.sort(key=lambda cv: (cv.du_kien_bat_dau is None, cv.du_kien_bat_dau, cv.id))
        return rows

    def _pham_vi_to(
        self,
        department_ids: set[int],
        employee_id: int | None,
        rieng_ids: set[int] | None,
    ):
        """Điều kiện PHẠM VI TỔ của một câu đọc bàn tổ; None = không có gì để thấy.

        Hình cũ (`rieng_ids is None`): mọi tổ trong `department_ids`, và nếu có `employee_id` thì chỉ
        việc đang giao cho người đó. Hình theo quyền tổ (mg 0302): `department_ids` thấy TRỌN,
        `rieng_ids` chỉ việc đang giao cho `employee_id` — một bàn cấp gom có thể trộn cả hai (vd
        Tất cả ở Nhóm 2 màu nhưng chỉ Của tôi ở phần còn lại của Tổ in)."""
        from sqlalchemy import or_

        giao = self._duoc_giao_cho(employee_id)
        if rieng_ids is None:
            if not department_ids:
                return None
            dk = SanXuatCongViec.department_id.in_(department_ids)
            return dk if giao is None else (dk & giao)
        nhanh = []
        if department_ids:
            nhanh.append(SanXuatCongViec.department_id.in_(department_ids))
        if rieng_ids and giao is not None:
            nhanh.append(SanXuatCongViec.department_id.in_(rieng_ids) & giao)
        if not nhanh:
            return None
        return nhanh[0] if len(nhanh) == 1 else or_(*nhanh)

    @staticmethod
    def _duoc_giao_cho(employee_id: int | None):
        """Điều kiện "việc này đang giao cho người đó" — dùng khi THỢ mở bàn tổ (§7.1). None ⇒
        không lọc (tổ trưởng / cấp trên thấy trọn tổ)."""
        from sqlalchemy import exists

        if employee_id is None:
            return None
        return exists().where(
            SanXuatPhanCong.cong_viec_id == SanXuatCongViec.id,
            SanXuatPhanCong.employee_id == employee_id,
            SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
        )

    def dem_cho_lam_theo_to(
        self,
        department_ids: set[int],
        *,
        employee_id: int | None = None,
        rieng_ids: set[int] | None = None,
    ) -> dict[int, int]:
        """Số việc CHƯA XONG mỗi tổ (badge navbar §2.1) — chỉ đếm gói đang hiệu lực.

        `employee_id`: chỉ đếm việc đang giao cho người đó — badge của THỢ phải khớp đúng số dòng
        họ mở ra thấy, nếu không navbar báo 12 mà bàn chỉ có 2."""
        pham_vi = self._pham_vi_to(department_ids, employee_id, rieng_ids)
        if pham_vi is None:
            return {}
        from sqlalchemy import func

        dieu_kien = [
            pham_vi,
            SanXuatCongViec.trang_thai != CV_HOAN_THANH,
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
        ]
        rows = self.db.execute(
            select(SanXuatCongViec.department_id, func.count(SanXuatCongViec.id))
            .join(SanXuatGoiPhatHanh, SanXuatCongViec.goi_id == SanXuatGoiPhatHanh.id)
            .where(*dieu_kien)
            .group_by(SanXuatCongViec.department_id)
        ).all()
        return {dept_id: n for dept_id, n in rows if dept_id is not None}

    def lsx_nhan(self, lsx_ids: set[int]) -> dict[int, tuple[str, str]]:
        """{lsx_id: (mã, tên)} để gắn nhãn công việc — không có thì bỏ khỏi map."""
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(Lsx.id, Lsx.ma, Lsx.ten).where(Lsx.id.in_(lsx_ids))
        ).all()
        return {lid: (ma, ten) for lid, ma, ten in rows}

    def bai_ghep_nhan(self, bg_ids: set[int]) -> dict[int, tuple[str, str]]:
        if not bg_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhep.id, BaiGhep.ma, BaiGhep.ten).where(BaiGhep.id.in_(bg_ids))
        ).all()
        return {bid: (ma, ten) for bid, ma, ten in rows}

    def khach_nhan(self, lsx_ids: set[int], bg_ids: set[int]) -> dict[tuple[str, int], str]:
        """{("lsx", id) | ("bai_ghep", id): tên khách} — lệnh → đơn hàng → khách. Bài ghép chạy
        chung nhiều lệnh nên gộp tên khách của mọi thành viên (khác nhau, theo thứ tự thêm vào bài).
        Lệnh không có đơn/khách thì vắng khỏi map."""
        ra: dict[tuple[str, int], str] = {}
        if lsx_ids:
            rows = self.db.execute(
                select(Lsx.id, Customer.name)
                .join(Order, Lsx.order_id == Order.id)
                .join(Customer, Order.customer_id == Customer.id)
                .where(Lsx.id.in_(lsx_ids))
            ).all()
            ra.update({("lsx", lid): ten for lid, ten in rows if ten})
        if bg_ids:
            rows = self.db.execute(
                select(BaiGhepThanhVien.bai_ghep_id, Customer.name)
                .join(Lsx, BaiGhepThanhVien.lsx_id == Lsx.id)
                .join(Order, Lsx.order_id == Order.id)
                .join(Customer, Order.customer_id == Customer.id)
                .where(BaiGhepThanhVien.bai_ghep_id.in_(bg_ids))
                .order_by(BaiGhepThanhVien.id)
            ).all()
            gom: dict[int, list[str]] = {}
            for bid, ten in rows:
                if ten and ten not in gom.setdefault(bid, []):
                    gom[bid].append(ten)
            ra.update({("bai_ghep", bid): " · ".join(ds) for bid, ds in gom.items() if ds})
        return ra

    def may_nhan(self, may_ids: set[int]) -> dict[int, str]:
        """{may_id: tên máy} cho bàn tổ.

        Tra trong `may_thiet_bi` — ĐÚNG danh mục mà `san_xuat_cong_viec.may_id` trỏ tới kể từ mg
        `0237` (trước đó là FK cứng sang `machines`, danh mục đời tính giá). Bản cũ còn tra
        `machines` nên cột "Máy" của bàn tổ luôn rỗng: id là của bảng này, tên đi tìm ở bảng kia.
        """
        if not may_ids:
            return {}
        rows = self.db.execute(
            select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(may_ids))
        ).all()
        return {mid: ten for mid, ten in rows}

    def nhom_nhan(self, nhom_ids: set[int]) -> dict[int, str]:
        """{nhom_id: nhãn nhóm thành phẩm} — ưu tiên `nhom_label`, rồi `ten`, rồi `khoa`."""
        if not nhom_ids:
            return {}
        rows = self.db.execute(
            select(SanXuatNhom.id, SanXuatNhom.nhom_label, SanXuatNhom.ten, SanXuatNhom.khoa)
            .where(SanXuatNhom.id.in_(nhom_ids))
        ).all()
        return {nid: (lbl or ten or khoa) for nid, lbl, ten, khoa in rows}

    def nhan_vien_nhan(self, emp_ids: set[int]) -> dict[int, tuple[str, int | None]]:
        """{employee_id: (họ tên, user_id)} — nhãn cho roster/khoảng tham gia của drawer thực thi.
        `user_id is None` = nhân viên không có tài khoản (vẫn giao + tính lương, §6)."""
        if not emp_ids:
            return {}
        rows = self.db.execute(
            select(Employee.id, Employee.full_name, Employee.user_id).where(
                Employee.id.in_(emp_ids)
            )
        ).all()
        return {eid: (ten, uid) for eid, ten, uid in rows}

    def anh_dai_dien(self, emp_ids: set[int]) -> dict[int, str]:
        """{employee_id: users.avatar_url} — chỉ người CÓ tài khoản và đã đặt ảnh. Lấy ảnh tài khoản
        (thư mục `avatars/`, ai đăng nhập cũng xem được), không lấy `employees.photo_url`: ảnh hồ sơ có
        thể nằm dưới `hr/` đòi quyền nhân sự, tổ trưởng mở drawer sẽ nhận ảnh vỡ."""
        if not emp_ids:
            return {}
        rows = self.db.execute(
            select(Employee.id, User.avatar_url)
            .join(User, User.id == Employee.user_id)
            .where(Employee.id.in_(emp_ids), User.avatar_url.is_not(None))
        ).all()
        return {eid: url for eid, url in rows}

    def to_ten_nhan(self, dept_ids: set[int]) -> dict[int, str]:
        """{department_id: tên tổ/phòng} — nhãn cho tổ gốc/tổ thực hiện của thỏa thuận hỗ trợ (§9)."""
        if not dept_ids:
            return {}
        rows = self.db.execute(
            select(Department.id, Department.name).where(Department.id.in_(dept_ids))
        ).all()
        return {did: name for did, name in rows}
