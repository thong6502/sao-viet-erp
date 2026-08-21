"""Đồ thị co của bài ghép: co nút đúng, và hai kiểu vòng đều bị chặn TRƯỚC khi ghi.

Thuần Python, không DB — chạy nhanh nên test được cả các hình đồ thị hiếm (cạnh chéo lệnh,
vòng ba nút) mà dựng bằng fixture DB sẽ rất đắt.
"""
from __future__ import annotations

from app.services.bai_ghep_graph import Buoc, CanhGoc, co_do_thi, kiem_gop, ung_vien_gop

# Hai lệnh, mỗi lệnh: CTP → In → Cán màng → Cắt.
CD_CTP, CD_IN, CD_CAN, CD_CAT, CD_EP = 1, 2, 3, 4, 5
TEN = {CD_CTP: "Ghi kẽm CTP", CD_IN: "In offset", CD_CAN: "Cán màng", CD_CAT: "Cắt xén",
       CD_EP: "Ép kim"}


def _lenh(ma: str, cong_doans: list[int], trong_bai: bool = True):
    """Dựng chuỗi bước tuyến tính của một lệnh + các cạnh nối liên tiếp."""
    buocs = [
        Buoc(key=f"{ma}-{cd}", lsx_id=int(ma), lsx_ma=ma, ten=TEN[cd], cong_doan_id=cd,
             trong_bai=trong_bai)
        for cd in cong_doans
    ]
    canhs = [CanhGoc(truoc=buocs[i].key, sau=buocs[i + 1].key) for i in range(len(buocs) - 1)]
    return buocs, canhs


def _hai_lenh(cd_a: list[int], cd_b: list[int]):
    ba, ca = _lenh("6001", cd_a)
    bb, cb = _lenh("6002", cd_b)
    return ba + bb, ca + cb


def test_khong_gop_gi_thi_moi_buoc_tu_lam_dai_dien():
    buocs, canhs = _hai_lenh([CD_CTP, CD_IN, CD_CAT], [CD_CTP, CD_IN, CD_CAT])
    kq = co_do_thi(buocs, canhs, [])
    assert kq.vong is None
    assert kq.dai_dien == {b.key: b.key for b in buocs}
    assert len(kq.thu_tu) == 6


def test_gop_buoc_in_hai_lenh_thi_tu_va_toa():
    """Gộp xong: hai CTP cùng trỏ vào một nút in, nút in toả ra hai nhánh cắt."""
    buocs, canhs = _hai_lenh([CD_CTP, CD_IN, CD_CAT], [CD_CTP, CD_IN, CD_CAT])
    kq = co_do_thi(buocs, canhs, [["6001-2", "6002-2"]])

    assert kq.vong is None
    chung = kq.dai_dien["6001-2"]
    assert kq.dai_dien["6002-2"] == chung          # hai bước in nhập làm một

    vao = [a for (a, b) in kq.canh if b == chung]
    ra = [b for (a, b) in kq.canh if a == chung]
    assert sorted(vao) == ["6001-1", "6002-1"]     # tụ vào (hai CTP)
    assert sorted(ra) == ["6001-4", "6002-4"]      # toả ra (hai nhánh cắt)
    assert len(kq.thu_tu) == 5                      # 6 bước co còn 5 nút


def test_gop_nhieu_buoc_thi_diem_toa_dich_sang_phai():
    """Gộp thêm cán màng: điểm toả chuyển từ sau in sang sau cán."""
    buocs, canhs = _hai_lenh([CD_IN, CD_CAN, CD_CAT], [CD_IN, CD_CAN, CD_CAT])
    kq = co_do_thi(buocs, canhs, [["6001-2", "6002-2"], ["6001-3", "6002-3"]])

    assert kq.vong is None
    nut_in, nut_can = kq.dai_dien["6001-2"], kq.dai_dien["6001-3"]
    assert [b for (a, b) in kq.canh if a == nut_in] == [nut_can]      # in → cán, một cạnh
    assert sorted(b for (a, b) in kq.canh if a == nut_can) == ["6001-4", "6002-4"]


def test_gop_hai_buoc_phu_thuoc_nhau_trong_cung_lenh_bi_tu_choi():
    """Kiểu hỏng 1 — cạnh tự trỏ chính mình. Một lượt chạy không thể vừa trước vừa sau chính nó."""
    buocs, canhs = _hai_lenh([CD_CAN, CD_EP], [CD_CAN, CD_EP])
    vong = kiem_gop(buocs, canhs, [["6001-3", "6001-5"]])

    assert vong is not None and vong.tu_tro
    assert "6001" in vong.thong_diep
    assert "Cán màng" in vong.thong_diep and "Ép kim" in vong.thong_diep


def test_hai_lenh_xep_nguoc_thu_tu_thi_gop_ca_hai_buoc_bi_tu_choi():
    """Kiểu hỏng 2 — lệnh A `Cán → Ép kim`, lệnh B `Ép kim → Cán`. Gộp cả hai công đoạn là kẹt.

    Đây là ca ở mục 5 phần Verification của plan.
    """
    buocs, canhs = _hai_lenh([CD_CAN, CD_EP], [CD_EP, CD_CAN])

    # Gộp riêng từng công đoạn thì không sao.
    assert kiem_gop(buocs, canhs, [["6001-3", "6002-3"]]) is None
    assert kiem_gop(buocs, canhs, [["6001-5", "6002-5"]]) is None

    vong = kiem_gop(buocs, canhs, [["6001-3", "6002-3"], ["6001-5", "6002-5"]])
    assert vong is not None and not vong.tu_tro
    assert vong.nut[0] == vong.nut[-1]                      # là chu trình thật
    assert {c.truoc for c in vong.nhan_chung} == {"6001-3", "6002-5"}
    assert "6001" in vong.thong_diep and "6002" in vong.thong_diep


def test_canh_cheo_lenh_khong_bi_bo_qua():
    """Sách = bìa + ruột, nối nhau ở "vào bìa". Bộ lọc cùng-một-LSX sẽ mù với cạnh này."""
    b_bia, c_bia = _lenh("6001", [CD_IN, CD_CAN])
    b_ruot, c_ruot = _lenh("6002", [CD_IN, CD_CAT])
    # Ruột cắt xong mới vào bìa (cán) — cạnh chéo lệnh.
    cheo = CanhGoc(truoc="6002-4", sau="6001-3")
    # Nhưng bìa in xong ruột mới in được (giả định để tạo mâu thuẫn khi gộp bước in).
    nguoc = CanhGoc(truoc="6001-3", sau="6002-2")

    buocs = b_bia + b_ruot
    canhs = c_bia + c_ruot + [cheo, nguoc]

    vong = kiem_gop(buocs, canhs, [["6001-2", "6002-2"]])
    assert vong is not None, "cạnh chéo lệnh phải được tính vào đồ thị"


def test_ung_vien_chi_sang_khi_cung_cong_doan_va_khong_sinh_vong():
    buocs, canhs = _hai_lenh([CD_CAN, CD_EP], [CD_EP, CD_CAN])
    b3, c3 = _lenh("6003", [CD_CAN, CD_EP])
    buocs, canhs = buocs + b3, canhs + c3

    ket = ung_vien_gop(buocs, canhs, nhom_hien_co=[], dang_chon=["6001-3"])

    # Chỉ các bước CÙNG công đoạn (cán màng) ở lệnh KHÁC mới có mặt.
    assert set(ket) == {"6002-3", "6003-3"}
    assert ket["6002-3"] is None and ket["6003-3"] is None   # chưa gộp gì thì đều sáng

    # Đã gộp ép kim trước → gộp cán màng với 6002 sẽ sinh vòng, thẻ đó phải tắt.
    ket2 = ung_vien_gop(
        buocs, canhs, nhom_hien_co=[["6001-5", "6002-5"]], dang_chon=["6001-3"]
    )
    assert ket2["6002-3"] is not None
    assert ket2["6003-3"] is None                            # lệnh 6003 xuôi chiều, vẫn gộp được


def test_buoc_ngoai_bai_khong_phai_ung_vien_nhung_van_tinh_vao_do_thi():
    b_in_bai, c_in_bai = _lenh("6001", [CD_IN, CD_CAN])
    b_ngoai, c_ngoai = _lenh("6009", [CD_IN, CD_CAN], trong_bai=False)
    buocs, canhs = b_in_bai + b_ngoai, c_in_bai + c_ngoai

    assert set(ung_vien_gop(buocs, canhs, [], ["6001-2"])) == set()
    assert co_do_thi(buocs, canhs, []).dai_dien.get("6009-2") == "6009-2"


def test_buoc_da_gop_roi_khong_hien_lam_ung_vien_lan_nua():
    buocs, canhs = _hai_lenh([CD_IN, CD_CAT], [CD_IN, CD_CAT])
    b3, c3 = _lenh("6003", [CD_IN, CD_CAT])
    buocs, canhs = buocs + b3, canhs + c3

    ket = ung_vien_gop(buocs, canhs, nhom_hien_co=[["6001-2", "6002-2"]], dang_chon=["6003-2"])
    assert set(ket) == set(), "bước đã nằm trong nhóm gộp khác thì không chọn lại được"
