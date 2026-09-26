"""Repository — Bảng cân đối vật tư (kế hoạch SX).

CHỈ truy vấn DB. Mọi luật cân đối (con trỏ tồn, màu dòng, mốc tạm, gom mặt hàng) nằm ở
`services/ke_hoach_vat_tu_service.py`.

Vì sao có repo RIÊNG thay vì rải method sang 5 repo sẵn có: sáu truy vấn dưới đây phục vụ ĐÚNG một
màn (bảng cân đối), gom vào một chỗ thì đọc được toàn bộ "màn này chạm những bảng nào" trong một
lần mở file. Rải ra `lsx_repo` / `bai_ghep_repo` / `khuon_be_repo`… là thêm method cho những repo
chẳng liên quan gì tới cân đối, rồi lần sau muốn biết màn này đọc gì phải đi tìm khắp nơi.
"""
from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.bai_ghep_cong_doan import (
    BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu,
)
from ..models.lsx import LsxCongDoanVatTu
from ..models.may_thiet_bi import MayThietBi
from ..models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from ..models.xep_lich import XepLichCongDoan


class KeHoachVatTuRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def dong_lich_da_xep(self) -> list[XepLichCongDoan]:
        """Mọi dòng lịch ĐÃ có giờ bắt đầu — nền để suy "ngày cần" của từng dòng vật tư."""
        return list(self.db.execute(
            select(XepLichCongDoan).where(XepLichCongDoan.start_at.is_not(None))
        ).scalars())

    def vat_tu_theo_buoc_lenh(self, buoc_ids: list[int]) -> list[LsxCongDoanVatTu]:
        """Vật tư khai tay ở các bước lệnh."""
        if not buoc_ids:
            return []
        return list(self.db.execute(
            select(LsxCongDoanVatTu).where(LsxCongDoanVatTu.lsx_cong_doan_id.in_(buoc_ids))
        ).scalars())

    def vat_tu_theo_buoc_chung(self, buoc_ids: list[int]) -> list[BaiGhepCongDoanVatTu]:
        """Vật tư của các lượt chạy chung (bài ghép)."""
        if not buoc_ids:
            return []
        return list(self.db.execute(
            select(BaiGhepCongDoanVatTu).where(
                BaiGhepCongDoanVatTu.bai_ghep_cong_doan_id.in_(buoc_ids)
            )
        ).scalars())

    def buoc_chung(self, bai_ghep_id: int) -> list[BaiGhepCongDoan]:
        return list(self.db.execute(
            select(BaiGhepCongDoan)
            .where(BaiGhepCongDoan.bai_ghep_id == bai_ghep_id)
            .order_by(BaiGhepCongDoan.thu_tu)
        ).scalars())

    def step_keys_bi_buoc_chung_de(self, bai_ghep_ids: set[int]) -> set[str]:
        """Tập bước nguồn đã mất hiệu lực vì đang được một bước chung của các bài này đè."""
        ids = {int(i) for i in bai_ghep_ids if i}
        if not ids:
            return set()
        return set(self.db.execute(
            select(BaiGhepCongDoanMap.lsx_step_key)
            .join(
                BaiGhepCongDoan,
                BaiGhepCongDoan.id == BaiGhepCongDoanMap.bai_ghep_cong_doan_id,
            )
            .where(BaiGhepCongDoan.bai_ghep_id.in_(ids))
        ).scalars())

    def may_theo_ids(self, ids: set[int]) -> dict[int, MayThietBi]:
        """Máy của các bước — nạp LÔ để suy thời lượng, tra từng cái là N+1 theo số bước."""
        ids = {int(i) for i in ids if i}
        if not ids:
            return {}
        return {
            m.id: m
            for m in self.db.execute(select(MayThietBi).where(MayThietBi.id.in_(ids))).scalars()
        }

    def buoc_da_chay_xong(
        self, *, lsx_buoc_ids: set[int], bai_buoc_ids: set[int]
    ) -> tuple[set[int], set[int]]:
        """Bước mà MỌI công việc sản xuất của nó đã `completed` — trả `(bước lệnh, bước chung)`.

        "Mọi", không phải "có một": một bước tách nhiều lần chạy (`phan_doan_so`, mg `0254`) đẻ N
        công việc cùng `lsx_cong_doan_id`. Xong lần 1 mà lần 2 còn chạy thì vật tư vẫn phải lo.

        Bước KHÔNG có công việc nào (chưa phát hành, hoặc gói đã thu hồi và xoá việc) rơi ra ngoài
        cả hai tập ⇒ tầng trên coi là CHƯA xong. Đó là chiều an toàn: thà giữ một dòng thừa trên
        bảng còn hơn giấu mất một món chưa ai mua.

        Neo bước ở `san_xuat_cong_viec` là id LỎNG (không FK — `replace_routing` tái sinh id). Vô
        hại ở đây: routing khoá từ lúc lập kế hoạch, mà chưa lập kế hoạch thì cũng chưa có việc.
        """
        lsx_ids = {int(i) for i in lsx_buoc_ids if i}
        bai_ids = {int(i) for i in bai_buoc_ids if i}
        if not lsx_ids and not bai_ids:
            return set(), set()
        dk = []
        if lsx_ids:
            dk.append(SanXuatCongViec.lsx_cong_doan_id.in_(lsx_ids))
        if bai_ids:
            dk.append(SanXuatCongViec.bai_ghep_cong_doan_id.in_(bai_ids))
        rows = self.db.execute(
            select(
                SanXuatCongViec.lsx_cong_doan_id,
                SanXuatCongViec.bai_ghep_cong_doan_id,
                func.count().label("tong"),
                func.sum(
                    case((SanXuatCongViec.trang_thai == CV_HOAN_THANH, 1), else_=0)
                ).label("xong"),
            )
            .where(or_(*dk))
            .group_by(
                SanXuatCongViec.lsx_cong_doan_id, SanXuatCongViec.bai_ghep_cong_doan_id
            )
        ).all()
        xong_lsx: set[int] = set()
        xong_bai: set[int] = set()
        for lsx_cd, bai_cd, tong, xong in rows:
            if not tong or int(xong or 0) < int(tong):
                continue
            if bai_cd is not None:
                xong_bai.add(int(bai_cd))
            elif lsx_cd is not None:
                xong_lsx.add(int(lsx_cd))
        return xong_lsx, xong_bai

    # (`khuon_theo_ids` + `cong_doan_can_dung_cu` đã gỡ 16/08/2026 cùng nhóm "Công cụ" — mg `0203`.)
