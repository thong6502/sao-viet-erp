"""Gác: MỌI cột danh mục phải có nhãn tiếng Việt trong `NHAN`.

Vì sao cần gác. Nhật ký danh mục dựng câu bằng `NHAN.get(truong, truong)` — không có nhãn thì nó
**rơi về tên cột** và người dùng đọc được nguyên văn `he_so_ngoai_dong 1 → 8`. Hỏng trong im lặng:
không lỗi, không test nào đỏ, chỉ là một dòng nhật ký không ai hiểu.

Đo ngày 15/08/2026 trước khi vá: **59 cột** trên 8 danh mục không có nhãn. Frontend từng cố chữa
cháy bằng một bảng nhãn riêng (`NK_FIELD_LABELS`), nhưng bảng đó khai theo TÊN CỘT TIẾNG ANH của
mấy bảng đời cũ (`machine_group`, `max_width_cm`) trong khi cột thật là `loai_may`, `kho_max_rong`
— khớp **0/8** khi thử. Chữa ở frontend là chữa sai tầng: nhãn phải nằm cùng chỗ với chỗ dựng câu.

Thêm cột mới vào một bảng danh mục ⇒ test này đỏ ⇒ thêm một dòng vào `NHAN`. Đó là toàn bộ chi phí.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from app.catalog_registry import DANH_MUC, lop_model_cua
from app.models.kho_hang import KhoHang
from app.models.may_thiet_bi import MayThietBi
from app.services.nhat_ky_danh_muc import BO_QUA, NHAN, anh_chup, mo_ta_thay_doi


def _models():
    """Model của mọi màn danh mục.

    Registry chỉ mang `model` cho màn CÓ bộ đếm "còn ai dùng không"; Máy và Kho hàng chưa có nên
    `lop_model_cua` trả None — nhưng chúng vẫn là danh mục và vẫn ghi nhật ký, nên nạp thẳng.
    """
    ra = [(d.loai, lop_model_cua(d.loai)) for d in DANH_MUC]
    ra = [(loai, m) for loai, m in ra if m is not None]
    return [*ra, ("may_thiet_bi", MayThietBi), ("kho_hang", KhoHang)]


@pytest.mark.parametrize("loai,model", _models(), ids=[t[0] for t in _models()])
def test_moi_cot_danh_muc_deu_co_nhan(loai, model):
    cols = sa_inspect(model).columns.keys()
    thieu = sorted(c for c in cols if c not in BO_QUA and c not in NHAN)
    assert not thieu, (
        f"Danh mục `{loai}` có cột chưa đặt nhãn: {thieu}.\n"
        f"Nhật ký sẽ in ra TÊN CỘT cho người dùng đọc. Thêm nhãn vào `NHAN` trong "
        f"`app/services/nhat_ky_danh_muc.py` (lấy đúng chữ đang hiện trên màn)."
    )


def test_cau_nhat_ky_khong_con_lo_ten_cot():
    """Ca thật: đổi hai cột của Máy — câu phải là chữ người đọc được, kèm đơn vị."""
    truoc = {"loai_may": "Máy in", "nhip_giay_mm": 10, "kho_max_rong": 720}
    sau = {"loai_may": "Máy bế", "nhip_giay_mm": 12, "kho_max_rong": 720}
    dong = mo_ta_thay_doi(truoc, sau)

    assert "Nhóm máy Máy in → Máy bế" in dong
    assert "Nhíp giấy 10 → 12 mm" in dong
    # Cột KHÔNG đổi thì không được đẻ ra dòng nào.
    assert not any("Khổ giấy max" in d for d in dong)


def test_anh_chup_bo_qua_cot_ky_thuat():
    """`anh_chup` đọc cột từ chính model — thêm cột là nhật ký theo dõi luôn, nhưng cột kỹ thuật
    (`id`, `created_at`…) phải nằm ngoài, không thì mỗi lần lưu đẻ một dòng 'updated_at đổi'."""
    may = MayThietBi(ma="TB-9001", ten="Máy thử")
    chup = anh_chup(may)
    assert "ma" in chup and "ten" in chup
    for kt in ("id", "created_at", "updated_at"):
        assert kt not in chup


def test_o_chon_in_nhan_khong_in_ma():
    """Ô chọn lưu MÃ (`dang_dat_lam`, `khuon_ep`, `theo_bac`). In thẳng thì nhật ký ra
    "Tình trạng dang_dat_lam → dang_dung" — đúng dòng người ta đọc được sau khi tổ bế tích nhận
    khuôn. Chữ phải khớp ô chọn trên màn; mã lạ (giá trị cũ còn sót) thì giữ nguyên, không đoán."""
    assert mo_ta_thay_doi({"tinh_trang": "dang_dat_lam"}, {"tinh_trang": "dang_dung"}) == [
        "Tình trạng Đang đặt làm → Đang dùng"]
    assert mo_ta_thay_doi({"loai": None}, {"loai": "khung_lua"}) == ["Loại — → Khung lụa"]
    assert mo_ta_thay_doi(
        {"nhom": "print", "tooling_type": "khuon_be", "kieu_bu_hao": "khong"},
        {"nhom": "finishing", "tooling_type": "khuon_ep", "kieu_bu_hao": "theo_bac"},
    ) == ["Nhóm In → Gia công sau in", "Loại dụng cụ Khuôn bế → Khuôn ép kim",
          "Bù hao Không bù hao → Theo bậc số lượng"]
    assert mo_ta_thay_doi({"tinh_trang": "dang_dung"}, {"tinh_trang": "zz_la"}) == [
        "Tình trạng Đang dùng → zz_la"]


def test_moi_ma_cua_o_chon_deu_co_nhan():
    """Thêm mã mới vào bộ hằng của model (vd `khung_lua` 04/09/2026) ⇒ test này đỏ ⇒ thêm nhãn.
    Không gác thì mã mới lọt ra nhật ký nguyên dạng, hỏng trong im lặng như chuyện 59 cột."""
    from app.models import cong_doan, khuon_be
    from app.services.nhat_ky_danh_muc import GIA_TRI_NHAN

    bo = {
        "tinh_trang": khuon_be.TINH_TRANG, "loai": khuon_be.LOAI_KHUON,
        "nhom": cong_doan.NHOM, "tooling_type": cong_doan.TOOLING_TYPE,
        "kieu_bu_hao": cong_doan.KIEU_BU_HAO,
    }
    thieu = {truong: sorted(set(ma) - set(GIA_TRI_NHAN.get(truong, {})))
             for truong, ma in bo.items()}
    assert not any(thieu.values()), f"Mã chưa có nhãn trong `GIA_TRI_NHAN`: {thieu}"
