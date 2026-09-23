"""Bù hao engine — tra bậc số lượng khai NGAY TRÊN công đoạn.

Mô hình từ 22/09/2026: module Bù hao độc lập đã gỡ. Công đoạn tự mang bảng bậc (`bac_bu_hao`),
mỗi bậc chỉ khai MỐC TRÊN (`sl_den`) — cận dưới là mốc của bậc liền trước, bậc cuối `sl_den=None`
là vô hạn. Không còn `rows=` (cả danh mục) lẫn `bu_hao_id`.
"""
from app.services import bu_hao_engine as be


def _bac(vals, pct):
    """Bảng bậc kiểu xưởng: 6 mốc tờ + bậc vô hạn tính %."""
    moc = [3000, 7000, 10000, 15000, 20000, 30000]
    b = [{"sl_den": d, "gia_tri": v, "don_vi": "to"} for d, v in zip(moc, vals)]
    b.append({"sl_den": None, "gia_tri": pct, "don_vi": "pct"})
    return b


IN_1_2 = _bac([120, 150, 200, 250, 300, 350], 1.5)
IN_3_4 = _bac([150, 200, 250, 300, 350, 400], 1.7)
IN_5 = _bac([200, 250, 300, 350, 400, 450], 2)
SONG_1CON = _bac([70, 100, 150, 170, 200, 250], 1)


def _cd(bac):
    return {"kieu_bu_hao": "theo_bac", "bac_bu_hao": bac}


def test_tra_bac_theo_sl():
    # In 5 màu, 12.000 → bậc 10.000-15.000 → 350 tờ
    assert be.tra_bac(IN_5, 12000) == 350
    # In 3-4 màu, 12.000 → bậc 10.000-15.000 → 300
    assert be.tra_bac(IN_3_4, 12000) == 300
    # In 3-4 màu, 5.000 → bậc 3.000-7.000 → 200
    assert be.tra_bac(IN_3_4, 5000) == 200
    # In 1-2 màu, 40.000 → bậc >30.000 = 1,5% × 40.000 = 600 tờ
    assert be.tra_bac(IN_1_2, 40000) == 600
    # Sóng 1 con, 8.000 → bậc 7.000-10.000 → 150
    assert be.tra_bac(SONG_1CON, 8000) == 150


def test_bien_bac_chan_tren_bao_gom():
    # SL đúng biên 3.000 → "Đến 3.000" (bậc đầu) → 150
    assert be.tra_bac(IN_3_4, 3000) == 150
    # 3.001 → bậc kế → 200
    assert be.tra_bac(IN_3_4, 3001) == 200


def test_can_duoi_lay_tu_moc_cua_bac_lien_truoc():
    """Bậc mới KHÔNG khai `sl_tu`; cận dưới là mốc của bậc trước, không phải 0."""
    bac = [{"sl_den": 3000, "gia_tri": 150, "don_vi": "to"},
           {"sl_den": 10000, "gia_tri": 3, "don_vi": "pct"},
           {"sl_den": None, "gia_tri": 2, "don_vi": "pct"}]
    assert be.tra_bac_raw(bac, 3000)["gia_tri"] == 150      # đúng biên bậc đầu
    assert be.tra_bac_raw(bac, 3001)["gia_tri"] == 3        # rơi bậc giữa
    assert be.tra_bac_raw(bac, 10000)["gia_tri"] == 3       # đúng biên bậc giữa
    assert be.tra_bac_raw(bac, 10001)["gia_tri"] == 2       # vượt mốc cuối → bậc vô hạn


def test_khong_khop_tra_0():
    assert be.tra_bac(SONG_1CON, 0) == 0.0   # SL 0: không bậc
    assert be.tra_bac([], 5000) == 0.0       # chưa khai bậc


def test_bu_hao_cong_doan_theo_kieu():
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "khong"}, sl=12000) == 0.0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}, sl=12000) == 50
    # theo_bac → tra bảng của CHÍNH công đoạn, 12.000 → 300
    assert be.bu_hao_cong_doan(_cd(IN_3_4), sl=12000) == 300
    # theo_bac nhưng chưa khai bậc → 0 (migration để bảng rỗng khi mất mã nguồn)
    assert be.bu_hao_cong_doan(_cd([]), sl=12000) == 0.0
    assert be.bu_hao_cong_doan({"kieu_bu_hao": "theo_bac"}, sl=12000) == 0.0


def test_tong_bu_hao_don():
    # Đơn 12.000: In (bảng → 300) + Ép kim (cố định 50) + Bồi (cố định 50) = 400
    cds = [
        _cd(IN_3_4),
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},
        {"kieu_bu_hao": "khong"},                         # ghi kẽm → 0
    ]
    assert be.tong_bu_hao(cds, sl=12000) == 400
    # + đơn yêu cầu 2% → +240 tờ
    assert be.tong_bu_hao(cds, sl=12000, pct_yeu_cau=2) == 400 + 240


# ============================ Bù hao NGƯỢC theo chuỗi công đoạn ============================

def test_hao_buoc_tach_to_va_pct():
    """Đi ngược cần tờ-cố-định và % TÁCH RIÊNG: tờ cộng thẳng, % nhân trên số RA của bước."""
    assert be.hao_buoc({"kieu_bu_hao": "khong"}, sl=12000) == (0.0, 0.0)
    assert be.hao_buoc({"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}, sl=12000) == (50, 0.0)
    # bậc đơn vị "to" → về vế TỜ
    assert be.hao_buoc(_cd(IN_3_4), sl=12000) == (300, 0.0)
    # bậc đơn vị "pct" (>30.000) → về vế %, KHÔNG quy sẵn ra tờ như `bu_hao_cong_doan`
    assert be.hao_buoc(_cd(IN_3_4), sl=40000) == (0.0, 1.7)
    assert be.hao_buoc(_cd([]), sl=12000) == (0.0, 0.0)


def test_chuoi_nguoc_rong_thi_khong_hao():
    assert be.chuoi_nguoc([], to_can=500) == []


def test_chuoi_nguoc_buoc_dau_roi_bac_cao_hon():
    """Bằng chứng "ngược" đã chạy: bước IN ở ĐẦU chuỗi tra bậc theo số tờ nó thật sự chạy."""
    chain = [
        _cd(IN_3_4),                                      # In 3-4 màu
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},   # Bế
        {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50},   # Xén
    ]
    b = be.chuoi_nguoc(chain, to_can=2950)
    # Xén 2.950→3.000 · Bế 3.000→3.050 · In tra bậc theo 3.050 → bậc 3.000-7.000 = 200 tờ
    assert [x["ra"] for x in b] == [3050, 3000, 2950]
    assert [x["vao"] for x in b] == [3250, 3050, 3000]
    # Cộng xuôi phẳng tra bậc In theo to_net=2.950 → bậc "Đến 3.000" = 150 → chỉ 3.200 tờ.
    assert be.tong_bu_hao(chain, sl=2950) + 2950 == 3200


def _b(ten, dv_vao, dv_ra, cd=None):
    return {"ten": ten, "cd": cd or {}, "dv_vao": dv_vao, "dv_ra": dv_ra}


def test_chuoi_nguoc_dv_tra_bac_theo_DUNG_don_vi_cua_buoc():
    """Ca chứng minh bug gốc: bước đếm CON phải tra bậc theo số CON, không theo số tờ.

    Đóng gói xử lý 5.000 con → bậc "3.000–7.000". Bản phẳng cũ truyền số TỜ (24) nên rơi bậc
    "Đến 3.000" — sai bậc, sai lượng, sai đơn vị.
    """
    chain = [
        _b("In offset", "to", "to", _cd(IN_3_4)),
        _b("Bế", "to", "cai", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 50}),
        _b("Đóng gói", "cai", "cai", _cd(IN_3_4)),
    ]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, to_can=5000, he_so={("to", "cai"): 210})
    assert canh_bao == []
    b_in, b_be, b_dg = kq
    # Đóng gói: 5.000 con → bậc 3.000-7.000 = 200 (con) → vào 5.200 con
    assert b_dg["ra"] == 5000 and b_dg["vao"] == 5200
    # Bế: quy 5.200 con ÷ 210 con/tờ = 24,76 tờ, + 50 tờ canh khuôn
    assert round(b_be["vao"], 2) == round(5200 / 210 + 50, 2)
    assert b_be["dv_vao"] == "to" and b_be["dv_ra"] == "cai"
    # In: ra ~74,8 tờ → bậc "Đến 3.000" = 150 tờ
    assert round(b_in["vao"], 2) == round(5200 / 210 + 50 + 150, 2)


def test_chuoi_nguoc_dv_cau_to_nguyen_sang_to_in():
    """Bước xả giấy là ranh giới tờ NGUYÊN → tờ IN; hao của nó khai bằng tờ nguyên."""
    chain = [
        _b("Xả giấy", "to_nguyen", "to", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 5}),
        _b("In offset", "to", "to", {"kieu_bu_hao": "co_dinh", "so_to_bu_hao": 150}),
    ]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, to_can=100, he_so={("to_nguyen", "to"): 2})
    assert canh_bao == []
    assert kq[1]["vao"] == 250            # in: 100 tờ in ra + 150 canh máy
    assert kq[0]["vao"] == 130            # xả: 250 ÷ 2 mảnh = 125 tờ nguyên + 5 tờ hao xả


def test_chuoi_nguoc_dv_bao_dut_don_vi():
    """Bế nhả CON mà bước sau lại ăn TỜ → chuỗi đứt. Engine KHÔNG tự bắc cầu, chỉ nói ra."""
    chain = [_b("Bế", "to", "cai"), _b("Cán màng", "to", "to")]
    _kq, canh_bao = be.chuoi_nguoc_dv(chain, to_can=100, he_so={("to", "cai"): 210})
    assert len(canh_bao) == 1 and "đứt đơn vị" in canh_bao[0]


def test_chuoi_nguoc_dv_thieu_he_so_thi_keu_chu_khong_doan():
    chain = [_b("Bế", "to", "cai")]
    kq, canh_bao = be.chuoi_nguoc_dv(chain, to_can=5000, he_so={})
    assert len(canh_bao) == 1 and "hệ số" in canh_bao[0]
    assert kq[0]["vao"] == 5000            # tạm hệ số 1, KHÔNG đoán bừa một con số


def test_chuoi_nguoc_pct_do_tren_so_RA():
    """Bậc % đo trên số RA của bước: `vào = ra × (1 + %)`, KHÔNG phải `ra / (1 − %)`.

    Chốt nghiệp vụ 06/09/2026: "hao 10%" nghĩa là cứ 100 tờ tốt phải chạy thêm 10 tờ — 110, chứ
    không phải 111,11. Bậc 1,5% ở dải trên 30.000: 40.000 tờ tốt ⇒ 40.600 tờ vào, hao đúng 600.
    """
    b = be.chuoi_nguoc([_cd(IN_1_2)], to_can=40000)
    assert round(b[0]["vao"], 2) == 40600.0
    assert round(b[0]["hao"], 2) == 600.0
    # Trùng khít đường CỘNG XUÔI: cùng một nghĩa của "%" thì hai lối phải ra một số.
    assert round(b[0]["vao"], 2) == 40000 + be.tong_bu_hao([_cd(IN_1_2)], sl=40000)


def test_chuoi_nguoc_pct_10_phan_tram_ra_100_thi_vao_110():
    """Ca mẫu người dùng chốt bằng miệng — giữ nguyên văn để khỏi trôi lại về phép chia."""
    cd = _cd([{"sl_den": None, "gia_tri": 10, "don_vi": "pct"}])
    b = be.chuoi_nguoc([cd], to_can=100)
    assert round(b[0]["vao"], 2) == 110.0
