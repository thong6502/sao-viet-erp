"""Nhóm thành phẩm — tự sinh từ `OrderLine.nhom` (§3.1).

KHÔNG bắt người dùng nhập lại tên thành phẩm; dòng đơn không có `nhom` thành nhóm đơn lẻ. Kế
hoạch KHÔNG tự ghép/tách nhóm — sai thì sửa từ Sale/đơn hàng trước phát hành. Idempotent: gọi lại
(tái phát hành) chỉ upsert, không nhân bản.
"""
from __future__ import annotations

from ...repositories.document_sequence_repo import DocumentSequenceRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...models.san_xuat import SanXuatNhom, SanXuatNhomLsx
from ..sequence_service import SequenceService


def _khoa(order_line_id: int, nhom: str | None) -> str:
    return nhom if nhom else f"line:{order_line_id}"


def dam_bao_nhom(repo: SanXuatRepository, lsx_ids: set[int]) -> dict[int, SanXuatNhom]:
    """Upsert nhóm + dòng thành viên cho tập LSX; trả map lsx_id → nhóm.

    Bỏ qua LSX thiếu dòng đơn (không truy được nguồn nhóm) — nó không nên lọt tới đây vì lệnh
    luôn neo `order_line_id` NOT NULL, nhưng phòng dữ liệu cũ."""
    seq = SequenceService(DocumentSequenceRepository(repo.db))
    ket_qua: dict[int, SanXuatNhom] = {}

    for lsx_id in sorted(lsx_ids):
        nguon = repo.nguon_nhom_cua_lsx(lsx_id)
        if nguon is None:
            continue
        order_id, order_line_id, nhom, mo_ta = nguon
        khoa = _khoa(order_line_id, nhom)
        ten = (nhom or (mo_ta or "").strip() or f"Dòng {order_line_id}")[:255]

        grp = repo.get_nhom(order_id, khoa)
        if grp is None:
            grp = SanXuatNhom(
                ma=seq.generate_code("san_xuat_nhom"),
                order_id=order_id, khoa=khoa, nhom_label=nhom, ten=ten,
            )
            repo.add(grp)
            repo.flush()
        else:
            # Giữ nhóm cũ; chỉ cập nhật nhãn hiển thị nếu nguồn đổi.
            grp.nhom_label = nhom
            grp.ten = ten

        member = repo.member_of_lsx(lsx_id)
        if member is None:
            repo.add(SanXuatNhomLsx(
                nhom_id=grp.id, lsx_id=lsx_id, order_line_id=order_line_id,
            ))
        elif member.nhom_id != grp.id:
            member.nhom_id = grp.id
            member.order_line_id = order_line_id
        repo.flush()
        ket_qua[lsx_id] = grp

    return ket_qua
