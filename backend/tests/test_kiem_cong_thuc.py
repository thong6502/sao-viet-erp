"""CÔNG THỨC KHAI SAI THÌ KHÔNG LƯU ĐƯỢC — cổng ở server (07/09/2026).

Bệnh đã đo được trên dev: `PUT /api/vat-lieu-kho/giay/6` với `dinh_luong * dai_nguyen *
rong_nguyen *` (thừa dấu nhân cuối) trả về **200 OK**. Câu hỏng nằm im trong DB tới lúc bảng cân
đối vật tư gọi mới nổ — nổ ở màn khác, cách chỗ gõ sai nhiều ngày.

Tầng trình duyệt (`fields/FormulaField.tsx`) chỉ đếm ngoặc và soi tên chip nên câu trên qua lọt,
và nó không đứng ở hai đường KHÔNG đi qua màn khai: nhập Excel và gọi thẳng API. Vì vậy cổng phải
ở service — file này khoá cả hai tầng: hàm kiểm (`kiem_cong_thuc`) và đường HTTP thật.
"""
from __future__ import annotations

import pytest

from app.services.bien_cong_thuc import LOAI_GIAY, LOAI_QUY_DOI
from app.services.thanh_phan_engine import kiem_cong_thuc
from tests.test_danh_muc_http_contract import _admin, _chung_loai_id

CT_TOT = "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen"
CT_HONG = "dinh_luong * dai_nguyen * rong_nguyen *"   # ĐÚNG câu đã lọt vào DB dev


@pytest.mark.parametrize("ct", [
    CT_TOT,
    "so_kem * 95000",
    "if(trang_moi_tay > 1, so_trang * so_luong, so_luong)",
    "max(sl_vao, 1) / 40000",
    "dinh_luong × dai_nguyen ÷ 1000",   # ký hiệu người gõ, `_chuan_hoa` dịch trước khi parse
    "",                                  # chưa khai — hợp lệ, đừng ép ai phải gõ
    "   ",
    None,
])
def test_cau_chay_duoc_thi_nhan(ct):
    kiem_cong_thuc(ct, nhan="Ô thử", loai=LOAI_QUY_DOI)


@pytest.mark.parametrize("ct,dau_hieu", [
    (CT_HONG, "sai cú pháp"),
    ("dinh_luong * (dai_nguyen", "sai cú pháp"),
    ("* dinh_luong", "sai cú pháp"),
    ("dinh_luongg * 2", "Biến không xác định"),
    ("sqrt(dinh_luong)", "Hàm không được hỗ trợ"),
    ("sl_vao > 100", "ĐÚNG/SAI"),
])
def test_cau_hong_thi_chan_va_goi_ten_o(ct, dau_hieu):
    with pytest.raises(ValueError) as e:
        kiem_cong_thuc(ct, nhan="Công thức tính định mức", loai=LOAI_QUY_DOI)
    assert dau_hieu in str(e.value)
    # Câu lỗi hiện thẳng cho người đang gõ — không gọi tên ô thì họ không biết sửa ở đâu.
    assert "Công thức tính định mức" in str(e.value)


def test_o_ra_luong_khong_duoc_nhac_toi_tien():
    """Cùng một câu: hợp lệ ở ô ra TIỀN, sai ở ô ra LƯỢNG. Tập biến của từng ô là `ma_hop_le`,
    dùng chung với bảng chip của màn khai — hai tầng một nguồn."""
    kiem_cong_thuc("dinh_luong * don_gia_giay", nhan="Công thức tính giá", loai=LOAI_GIAY)
    with pytest.raises(ValueError, match="don_gia_giay"):
        kiem_cong_thuc("dinh_luong * don_gia_giay", nhan="Công thức tính định mức",
                       loai=LOAI_QUY_DOI)


def test_chia_cho_hieu_hai_bien_van_luu_duoc():
    """Bộ số giả cho MỌI biến = 1 nên `dai_nguyen - rong_nguyen` ra 0 — chia cho nó là lỗi của
    chính bộ số giả, không phải của câu khai. Chặn ở đây là chặn oan."""
    kiem_cong_thuc("so_luong / (dai_nguyen - rong_nguyen)", nhan="Ô thử", loai=LOAI_QUY_DOI)


def test_khong_khai_loai_thi_chi_soi_cu_phap():
    kiem_cong_thuc("bien_la_hoac * 2", nhan="Ô thử")
    with pytest.raises(ValueError):
        kiem_cong_thuc(CT_HONG, nhan="Ô thử")


# --- đường HTTP thật ---------------------------------------------------------------------------

def _giay(client, h, **them) -> dict:
    return {"ma": "ZZCTG", "ten": "ZZ Giấy công thức", "gsm": 100,
            "chung_loai_giay_id": _chung_loai_id(client, h), **them}


def test_api_giay_khong_nhan_cau_hong_o_ca_tao_lan_sua(client):
    h = _admin(client)
    hong = client.post("/api/vat-lieu-kho/giay", json=_giay(client, h, cong_thuc_luong=CT_HONG),
                       headers=h)
    assert hong.status_code == 422, hong.text
    assert "Công thức tính định mức" in hong.json()["detail"]

    tao = client.post("/api/vat-lieu-kho/giay", json=_giay(client, h, cong_thuc_luong=CT_TOT),
                      headers=h)
    assert tao.status_code == 201, tao.text
    gid = tao.json()["id"]

    sua = client.put(f"/api/vat-lieu-kho/giay/{gid}",
                     json=_giay(client, h, cong_thuc_luong=CT_HONG), headers=h)
    assert sua.status_code == 422, sua.text
    # Bị chặn thì DB phải giữ nguyên câu cũ, không lưu một nửa.
    assert client.get(f"/api/vat-lieu-kho/giay/{gid}",
                      headers=h).json()["cong_thuc_luong"] == CT_TOT

    lai = client.put(f"/api/vat-lieu-kho/giay/{gid}",
                     json=_giay(client, h, cong_thuc_luong=CT_TOT, ten="ZZ Giấy đã sửa"),
                     headers=h)
    assert lai.status_code == 200, lai.text


def test_api_giay_sua_khong_dinh_toi_o_cong_thuc_thi_khong_bi_chan(client):
    """Dòng đang mang câu hỏng từ trước vẫn phải đổi được TÊN — payload không có ô công thức thì
    không soi. (Có gửi ô đó lên thì mới chặn, xem test trên.)"""
    h = _admin(client)
    tao = client.post("/api/vat-lieu-kho/giay", json=_giay(client, h, ma="ZZCTG2"), headers=h)
    assert tao.status_code == 201, tao.text
    gid = tao.json()["id"]
    sua = client.put(f"/api/vat-lieu-kho/giay/{gid}",
                     json=_giay(client, h, ma="ZZCTG2", ten="ZZ Giấy đổi tên"), headers=h)
    assert sua.status_code == 200, sua.text


def test_api_cong_doan_khong_nhan_cau_hong(client):
    h = _admin(client)
    than = {"ma": "ZZCDCT", "ten": "ZZ Công đoạn công thức", "nhom": "finishing",
            "pricing_basis": "per_finished_qty"}
    hong = client.post("/api/cong-doan", json={**than, "cong_thuc_gia": "so_kem * "}, headers=h)
    assert hong.status_code == 422, hong.text
    assert "Công thức tính giá" in hong.json()["detail"]

    tao = client.post("/api/cong-doan", json={**than, "cong_thuc_gia": "so_kem * 95000"},
                      headers=h)
    assert tao.status_code == 201, tao.text
