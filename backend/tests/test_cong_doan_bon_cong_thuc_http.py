"""Bốn ô công thức của màn Công đoạn — đi TRỌN vòng POST → GET qua API thật.

Vì sao kiểm ở tầng router chứ không tầng service: bốn ô này nằm ở BA schema lồng nhau
(`CongDoanMayIn`, `CongDoanDauViecIn`, `CongDoanDauViecVatTuIn`). Bẫy "Pydantic nuốt field im
lặng" ăn đúng khuôn đó — service trả đủ mà schema `Out` quên khai một khoá thì nó rơi KHÔNG lỗi,
form nhận `undefined` và người dùng thấy ô mình vừa gõ tự trống lại sau khi lưu.

Kiểm thêm luật "công thức GIÁ chỉ thuộc công đoạn nhóm In": màn danh mục ẩn ô ngoài nhóm In,
nhưng bảng Excel gửi thẳng payload nên luật phải nằm ở server.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def nen(client) -> dict:
    """Máy · tổ · đầu việc khoán · vật tư — dựng thẳng vào DB.

    `SEED_DEMO=false` trong test nên bốn danh mục này rỗng; dựng qua ORM chứ không qua bốn lượt
    POST vì thứ đang kiểm là vòng lưu–đọc của CÔNG ĐOẠN, không phải form của bốn màn kia.
    """
    from app.db import engine
    from app.models.department import Department
    from app.models.may_thiet_bi import MayThietBi
    from app.models.piece_work import PieceRate
    from app.models.vat_lieu_kho import VatTuInAn

    with Session(engine) as db:
        to = Department(name="Tổ In offset", code="PB901")
        may = MayThietBi(ma="IN-TEST", ten="Máy 4 màu", loai_may="Máy in", active=True)
        vat_tu = VatTuInAn(ma="MUC-TEST", ten="Mực đen", don_vi_gia="kg", don_gia=180_000,
                           active=True)
        db.add_all([to, may, vat_tu])
        db.flush()
        rate = PieceRate(group_name="to_in", ten="In tờ rời", unit="to", unit_price=35,
                         department_id=to.id, active=True)
        db.add(rate)
        db.commit()
        ids = {"may_id": may.id, "vat_tu_id": vat_tu.id, "rate_id": rate.id, "to_id": to.id}
    return {"headers": _headers(client), **ids}


def _payload(nen: dict, *, nhom: str = "print", ct_gia: str | None = "sl_vao * so_mat * 420",
             ct_gio: str | None = "sl_vao * so_mat") -> dict:
    return dict(
        ma="CD-4CT", ten="In offset 4 công thức", nhom=nhom,
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty",
        department_id=nen["to_id"],
        may_lam_duoc=[{"may_id": nen["may_id"], "cong_thuc_gio": ct_gio,
                       "cong_thuc_gia": ct_gia}],
        dau_viec_dinh_muc=[{
            "piece_rate_id": nen["rate_id"],
            "nang_suat_nguoi_gio": 3000, "so_nguoi_tieu_chuan": 2,
            "cong_thuc_khoan": "sl_vao * so_luot_chay",
            "vat_tus": [{"vat_tu_id": nen["vat_tu_id"], "cong_thuc_luong": "sl_vao / 8000"}],
        }],
    )


def _tao(client, nen: dict, **kw) -> dict:
    r = client.post("/api/cong-doan", json=_payload(nen, **kw), headers=nen["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def test_bon_o_cong_thuc_song_sot_ca_luc_luu_lan_luc_doc_lai(client, nen):
    tao = _tao(client, nen)

    doc = client.get(f"/api/cong-doan/{tao['id']}", headers=nen["headers"])
    assert doc.status_code == 200, doc.text
    cd = doc.json()

    may = cd["may_lam_duoc"][0]
    assert (may["cong_thuc_gio"], may["cong_thuc_gia"]) == (
        "sl_vao * so_mat", "sl_vao * so_mat * 420")
    dv = cd["dau_viec_dinh_muc"][0]
    assert dv["cong_thuc_khoan"] == "sl_vao * so_luot_chay"
    assert dv["vat_tus"][0]["cong_thuc_luong"] == "sl_vao / 8000"
    # Trả lời ngay ở POST cũng phải đủ bốn ô: form dựng lại state từ response này.
    assert tao["may_lam_duoc"][0]["cong_thuc_gia"] == "sl_vao * so_mat * 420"
    assert tao["dau_viec_dinh_muc"][0]["vat_tus"][0]["cong_thuc_luong"] == "sl_vao / 8000"


def test_cong_doan_ngoai_nhom_in_khong_giu_duoc_cong_thuc_gia(client, nen):
    """Ngoài nhóm In không có đường nào chảy tới công thức giá — giữ lại là bày giá ma."""
    cd = _tao(client, nen, nhom="finishing")

    may = cd["may_lam_duoc"][0]
    assert may["cong_thuc_gia"] is None, "công thức giá phải bị dọn ngoài nhóm In"
    assert may["cong_thuc_gio"] == "sl_vao * so_mat", "công thức giờ thì mọi nhóm đều dùng"


def test_cau_toan_khoang_trang_ve_trong_chu_khong_thanh_cong_thuc_rong(client, nen):
    """`"   "` mà lọt xuống engine thì `if cong_thuc:` tưởng có khai rồi `safe_eval` nổ."""
    cd = _tao(client, nen, ct_gio="   ", ct_gia="")

    may = cd["may_lam_duoc"][0]
    assert (may["cong_thuc_gio"], may["cong_thuc_gia"]) == (None, None)
