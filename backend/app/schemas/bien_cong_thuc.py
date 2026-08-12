"""Pydantic schemas — từ điển biến của các ô gõ công thức."""
from __future__ import annotations

from pydantic import BaseModel


class BienCongThucRow(BaseModel):
    ma: str            # tên gõ trong công thức
    nhan: str          # nhãn ngắn trên chip
    mo_ta: str         # câu giải thích khi hover
    don_vi: str        # đơn vị của GIÁ TRỊ (m · tờ · kg/m² …) — người khai phải biết để nhân đúng
    # "Số này ở đâu ra" — hiện trên màn khai. Thiếu nó thì người ta gõ `to_dau_vao` mà không biết
    # nó ĐÃ gồm bù hao, rồi nhân thêm hệ số hao lần nữa.
    nguon: str
    # Ô công thức nào dùng được biến này (giay · vat_tu · cong_doan · quy_doi). Frontend lọc theo
    # đây để vẽ chip, và validate biến gõ tay — cùng một tập với backend, không còn hai danh sách.
    loai: list[str]


class BienCongThucListOut(BaseModel):
    items: list[BienCongThucRow]
