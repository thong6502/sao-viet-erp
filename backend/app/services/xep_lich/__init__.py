"""Gói **Xếp lịch** — bàn xếp lịch cấp LỆNH SẢN XUẤT. Xem `docs/spec-xep-lich-3.md`.

Gộp 18/09/2026 từ hai gói cũ, sau khi chủ dự án chốt *"xoá v2 và đổi tên v3 thành `xep_lich`"*:

- `service` · `moc` · `trai_lich` — bàn cấp lệnh (gói `xep_lich_3` cũ), phần người dùng nhìn thấy.
- `constraint` · `phan_doan` · `release` · `thuc_te` — bốn module LUẬT của gói `xep_lich_2` cũ.
  Chúng **không** thuộc về màn v2 đã gỡ: `services/san_xuat/release.py` (cửa phát hành),
  `xep_lich_van_de_service` (danh sách xung đột) và chính bàn cấp lệnh đều đang ăn chúng. Xoá theo
  màn là gãy phát hành sản xuất, nên chúng chuyển sang đây nguyên vẹn.

Phần còn lại của `xep_lich_2` (bàn kéo-thả theo công đoạn: `service`, `auto`, `context`,
`diem_may`, `overlay`, `routing`, `suggestion`, `chan_doan`) đã xoá hẳn cùng router và màn — không
còn ai gọi sau khi mục menu tắt.
"""
from . import constraint
from .constraint import MUC_CANH_BAO, MUC_CHAN_DAT_LICH, MUC_CHAN_PHAT_HANH
from .moc import lsx_da_xep, moc_theo_buoc
from .service import (
    XepLichLenhConflict,
    XepLichLenhError,
    XepLichLenhNotFound,
    XepLichLenhService,
)
from .trai_lich import BuocVao, DoanChay, KetQuaTrai, MocBuoc, trai_lich

__all__ = [
    "constraint",
    "MUC_CANH_BAO", "MUC_CHAN_DAT_LICH", "MUC_CHAN_PHAT_HANH",
    "lsx_da_xep", "moc_theo_buoc",
    "BuocVao", "DoanChay", "KetQuaTrai", "MocBuoc", "trai_lich",
    "XepLichLenhService", "XepLichLenhError", "XepLichLenhNotFound", "XepLichLenhConflict",
]
