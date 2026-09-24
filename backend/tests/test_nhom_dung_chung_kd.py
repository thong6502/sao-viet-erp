"""Nhóm DÙNG CHUNG (khối Kinh doanh) — hai người ở phạm vi "Của tôi" dùng chung dữ liệu.

Phạm vi có ba nấc: Của tôi · Cả phòng · Tất cả. Nhu cầu ở giữa nấc 1 và nấc 2: anh A và anh B
làm chung nên phải thấy + sửa được phiếu của nhau, mà KHÔNG kéo cả phòng vào. Nhóm dùng chung
mở rộng đúng nghĩa "Của tôi" cho bốn màn `tinh_gia_thanh` · `bao_gia` · `don_hang_ban` ·
`khach_hang`, và CHỈ bốn màn đó — Lương/Hồ sơ/Chấm công vẫn là "chỉ mình tôi".

Nhóm MỞ RỘNG DỮ LIỆU, KHÔNG nâng quyền: ô quyền vẫn tính theo vai người đang thao tác.
"""
from __future__ import annotations

import pytest

from app.models.nhom_dung_chung import NhomDungChung, NhomDungChungThanhVien
from tests.conftest import phien_da_seed


@pytest.fixture
def db():
    yield from phien_da_seed()


def test_hai_bang_ton_tai_va_ghi_duoc(db):
    nhom = NhomDungChung(ten="Cặp KD 1", created_by=None)
    db.add(nhom)
    db.flush()
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=1, added_by=None))
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=2, added_by=None))
    db.flush()
    assert db.query(NhomDungChungThanhVien).filter_by(nhom_id=nhom.id).count() == 2
