"""TỪ ĐIỂN BIẾN của mọi công thức trong hệ — MỘT nguồn duy nhất.

Hệ có bốn ô cho người dùng gõ công thức: **giấy · vật tư · công đoạn** (công thức TIỀN, engine
`thanh_phan_engine` thế số) và **quy đổi đơn vị** (công thức HỆ SỐ, engine `quy_doi_service`).
Mỗi ô cho dùng một bộ biến khác nhau, và tên biến phải khớp giữa hai tầng thì công thức mới chạy.

VÌ SAO GOM VỀ ĐÂY (11/08/2026): trước đó danh sách nằm ở HAI nơi rời nhau — frontend giữ mảng
`PHIEU_VARS`/`EXTRA_VALID_VARS` (quyết định chip nào hiện + validator chấp nhận biến nào), backend
giữ `ctx_vars` (quyết định biến nào có GIÁ TRỊ thật). Không có gì ép hai bên khớp, và chúng đã lệch:

  · `so_mau_pha` — backend có giá trị, frontend không cho gõ (validator báo đỏ).
  · `so_vi_tri` · `dien_tich` — frontend cho gõ ở MỌI loại, backend chỉ bơm cho công đoạn ⇒ gõ vào
    công thức giấy/vật tư là thiếu biến, ra 0đ không kèn không trống.
  · `don_gia_luot` · `don_gia_kem` — frontend nhận, backend KHÔNG hề có. Không công thức nào đang
    dùng (đã soi DB), nên bỏ hẳn thay vì bịa giá trị cho chúng.

BA NƠI CÙNG ĐỌC FILE NÀY: engine tính giá (`ngu_canh_phieu` dưới đây), quy đổi động
(`quy_doi_service.BIEN`), và API `/api/bien-cong-thuc` cho màn khai vẽ chip. Thêm biến mới (vd
`sl_buoc` cho vật tư theo bước) thì sửa ĐÚNG file này — quên bơm giá trị là `ngu_canh_phieu` ném
TypeError ngay, không im lặng ra 0 như dict rời trước kia.
"""
from __future__ import annotations

# Bốn ô gõ công thức. Ba ô đầu là công thức TIỀN (thế số ra đồng), ô cuối là công thức HỆ SỐ.
LOAI_GIAY = "giay"
LOAI_VAT_TU = "vat_tu"
LOAI_CONG_DOAN = "cong_doan"
LOAI_QUY_DOI = "quy_doi"
LOAI = (LOAI_GIAY, LOAI_VAT_TU, LOAI_CONG_DOAN, LOAI_QUY_DOI)

_TIEN = (LOAI_GIAY, LOAI_VAT_TU, LOAI_CONG_DOAN)   # ba ô công thức tiền
_MOI_O = (*_TIEN, LOAI_QUY_DOI)                    # bộ CHUNG — có mặt ở cả bốn ô

# (mã, nhãn ngắn, mô tả hover, đơn vị, NGUỒN số, dùng được ở ô nào)
#
# BỘ CHUNG 17 BIẾN (15 + hai chip quy cách sách, 03/09/2026) + đúng MỘT biến đơn giá cho ô nào có
# mục để lấy giá, + năm chip TẦNG BƯỚC cho hai ô đứng ở một bước:
#     Giấy 19 · Vật tư 18 · Công đoạn 22 · Quy đổi 23
# Con số này bị khoá bằng test (`test_bon_o_dung_chung_bo_bien_va_hai_chip_rieng_cua_buoc`).
# Công đoạn KHÔNG có biến tiền — không có ô nhập đơn giá ở cả phiếu lẫn danh mục, và 13/13 công
# thức đang gõ đơn giá thẳng vào công thức. Quy đổi dùng chung bộ 16: nó chỉ chạy ở TẦNG LỆNH
# (kế hoạch vật tư · tiền khoán · màn thử), nơi quy cách lệnh có sẵn đủ số — kho và mua hàng
# KHÔNG gọi quy đổi động.
#
# `nguon` là câu trả lời cho "số này ở đâu ra", hiện thẳng trên màn khai. Thiếu nó thì người ta gõ
# `to_dau_vao` mà không biết số đó ĐÃ gồm bù hao, rồi nhân thêm hệ số hao lần nữa.
_BANG: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    # --- Kích thước: engine chia 1000 TRƯỚC khi bơm, nên trong công thức luôn là MÉT ------------
    ("dai_tp", "Dài sản phẩm", "Dài sản phẩm (vd 0,21)", "m",
     "khổ thành phẩm của lệnh ÷ 1.000", _MOI_O),
    ("rong_tp", "Rộng sản phẩm", "Rộng sản phẩm", "m",
     "khổ thành phẩm của lệnh ÷ 1.000", _MOI_O),
    ("dai_nguyen", "Dài tờ nguyên", "Dài tờ giấy nguyên (khổ to, chưa cắt)", "m",
     "khổ giấy nguyên của lệnh ÷ 1.000", _MOI_O),
    ("rong_nguyen", "Rộng tờ nguyên", "Rộng tờ giấy nguyên", "m",
     "khổ giấy nguyên của lệnh ÷ 1.000", _MOI_O),
    ("dai_in", "Dài tờ in", "Dài tờ chạy máy in (vd 0,64)", "m",
     "khổ tờ in của lệnh ÷ 1.000", _MOI_O),
    ("rong_in", "Rộng tờ in", "Rộng tờ chạy máy in", "m",
     "khổ tờ in của lệnh ÷ 1.000", _MOI_O),
    # --- Sản lượng ------------------------------------------------------------------------------
    ("so_luong", "Số lượng đặt", "Số cái cần làm (số lượng đặt)", "cái",
     "SL của dòng ĐƠN — lệnh ép theo đơn, không lấy SL của phiếu tính giá", _MOI_O),
    ("so_tp", "Số con/tờ in", "Số con/tờ — 1 tờ in ra mấy cái", "con",
     "bình bài của lệnh", _MOI_O),
    # --- Quy cách SÁCH (03/09/2026) --------------------------------------------------------------
    # Hai số này là thứ phân biệt sách với tờ rời, và trước nay KHÔNG có tên biến nào trỏ tới:
    # engine đọc chúng để dựng cầu `to → tay → cai` (`cau_to_sang_cai`) nhưng người khai công thức
    # thì không, nên mọi công thức phải đi vòng qua `so_tp`/`sl_ra` — không tính được thứ tính theo
    # TRANG (bình file, ghi kẽm theo tay, gấp, bắt tay) mà chỉ tính theo tờ.
    #
    # Tờ rời và hộp: cả hai = 1 (mặc định cột, và mg 0147 backfill dữ liệu cũ về 1), nên
    # `x * so_trang` trên bài tờ rời ra đúng `x` — thêm chip này KHÔNG đổi số của công thức cũ.
    # `trang_moi_tay > 1` là dấu hiệu DUY NHẤT của "làm kiểu sách" (xem `la_sach` ở lsx_service),
    # nên `if(trang_moi_tay > 1, ..., ...)` là cách khai một công thức chạy cả hai kiểu bài.
    ("so_trang", "Số trang sách", "Số trang nội dung của 1 sản phẩm (tờ rời/hộp = 1)", "trang",
     "ô Số trang của sản phẩm ở phiếu tính giá — tờ rời/hộp là 1", _MOI_O),
    ("trang_moi_tay", "Trang mỗi tay", "Số trang trên 1 tay gấp (8 · 16 · 32); 1 = không gấp tay",
     "trang", "ô Trang mỗi tay của sản phẩm — 1 nghĩa là không gấp tay (tờ rời, hộp)", _MOI_O),
    # Ba biến tờ dưới đây ĐÃ GỒM BÙ HAO — kết quả của chuỗi bù hao ngược, không phải số thô.
    ("to_dau_vao", "Tờ vào máy", "Số tờ vào máy = tờ cần in + bù hao", "tờ",
     "CHUỖI BÙ HAO NGƯỢC — đã gồm bù hao, đừng nhân hao thêm lần nữa", _MOI_O),
    ("to_sau_in", "Tờ tốt sau in", "Số tờ tốt sau in (dùng cho gia công)", "tờ",
     "CHUỖI BÙ HAO NGƯỢC — số ra khỏi bước in", _MOI_O),
    ("to_nguyen", "Tờ giấy nguyên", "Số tờ giấy nguyên tiêu hao (giấy to chưa cắt)", "tờ",
     "CHUỖI BÙ HAO NGƯỢC — đọc tại bước xả giấy; không có bước xả thì chia số mảnh xả", _MOI_O),
    # --- Quy cách in ----------------------------------------------------------------------------
    ("so_mau", "Số màu in", "Tổng số màu in (mặt A + mặt B)", "màu",
     "dẫn xuất từ TẬP MỰC mỗi mặt, không phải số gõ tay", _MOI_O),
    ("so_mau_pha", "Số màu pha", "Số màu pha riêng (Pantone) trong tổng số màu", "màu",
     "dẫn xuất từ tập mực — phần màu pha riêng", _MOI_O),
    ("so_mat", "Số mặt in", "Số mặt qua máy (1 mặt = 1 · 2 mặt/tự trở = 2)", "mặt",
     "quy cách in của lệnh — CÔNG ĐOẠN gõ số riêng vào ô của bước thì ăn số đó, để trống mới theo quy cách", _MOI_O),
    ("so_kem", "Số bản kẽm", "Số bản kẽm = số bản mỗi tay × số tay", "bản",
     "số bản mỗi tay × số tay", _MOI_O),
    # Định lượng là thuộc tính CỦA GIẤY — chỉ ô Giấy khai được. Ô Quy đổi vẫn phải có: dòng
    # `1 tờ = dinh_luong × dai_in × rong_in` kg là thứ DUY NHẤT biến tờ thành cân, bỏ là gãy phép
    # đổi tờ→kg và kéo theo gãy bảng so tồn giấy.
    ("dinh_luong", "Định lượng giấy", "Định lượng giấy, kg/m² (= gsm ÷ 1.000)", "kg/m²",
     "gsm của giấy ÷ 1.000", (LOAI_GIAY, LOAI_QUY_DOI)),
    # --- Đơn giá: MỖI Ô MỘT BIẾN, tên nói rõ của ai -------------------------------------------
    # Trước 11/08/2026 cả ba ô dùng chung một chữ `don_gia`, nhìn chip không biết giá của cái gì.
    # Nay ô nào có mục để lấy giá thì có biến của riêng nó; ô Công đoạn KHÔNG có, vì không có chỗ
    # nào nhập đơn giá công đoạn cả (kiểm 11/08: hết ô ở phiếu, hết ô ở danh mục).
    ("don_gia_giay", "Đơn giá giấy",
     "Đơn giá của CHÍNH dòng giấy đang mở — đã quy về đơn vị công thức đang đếm", "đ",
     "ô Đơn giá của dòng giấy, quy về đơn vị cơ sở (khai đ/tấn thì máy ÷ 1.000)", (LOAI_GIAY,)),
    # --- SỐ CỦA CHÍNH BƯỚC (14/08/2026) ---------------------------------------------------------
    # Mọi biến trên đây là số của CẢ LỆNH. Hai biến này là số của MỘT BƯỚC — keo dán ở bước Bắt tay
    # phải tính theo số cuốn chạy qua ĐÚNG bước đó, bước sau hao bớt thì lượng keo ít đi theo.
    #
    # Hai biến này thuộc TẦNG BƯỚC (`_TANG_BUOC` dưới đây), không phải tầng phiếu — engine bơm
    # chúng trong vòng lặp từng bước, nên chúng nằm NGOÀI `MA_NGU_CANH_PHIEU`.
    #
    # MỞ CHO Ô CÔNG ĐOẠN 15/08/2026: không có chúng thì công thức tiền của một công đoạn KHÔNG CÓ
    # tên biến nào trỏ tới số tờ đi qua chính nó. Bảng chip chỉ có `to_dau_vao` (tờ vào máy, đã gồm
    # bù hao của CẢ chuỗi), `to_sau_in` (một con số chung, không phân biệt được hai bước sau in) và
    # `so_luong` (SL đặt). Hệ quả đo được: bước "Gấp tay sách" chạm 5.000 tờ nhưng khai
    # `to_dau_vao * 120` nên tính tiền trên 5.200 — dư đúng 200 tờ mà máy in đã đốt.
    #
    # Ô "Công thức tính lượng" của Vật tư/Giấy vẫn với tới hai biến này qua bộ chip `quy_doi`
    # (xem `rebuildCatalogConfigs`). Giấy/Vật tư KHÔNG mở: hai ô đó tính tiền cho một MẶT HÀNG, nó
    # không đứng ở bước nào cả.
    #
    # Nơi bơm: `thanh_phan_engine` (vòng lặp công đoạn) · `LsxService._vat_tu_bung` +
    # `_goi_y_luong_vat_tu`. Ngữ cảnh nào không có (công thức của cặp · công thức đơn vị RA lúc
    # đang tính chính SL bước) thì `_thieu_bien` coi là THIẾU ⇒ để trống + báo lý do, không đoán.
    ("sl_vao", "SL vào của công đoạn", "Số lượng VÀO của chính bước đang tính",
     "đơn vị của bước", "chuỗi bù hao ngược — có sau khi engine chạy xong",
     (LOAI_CONG_DOAN, LOAI_QUY_DOI)),
    ("sl_ra", "SL ra của công đoạn", "Số lượng RA của chính bước đang tính",
     "đơn vị của bước", "chuỗi bù hao ngược — có sau khi engine chạy xong",
     (LOAI_CONG_DOAN, LOAI_QUY_DOI)),
    # Ba biến khung lụa — TẦNG BƯỚC như `sl_vao`/`sl_ra`. Nguồn thật: 3 ô nhập ở phiếu tính giá
    # (`PhieuThanhPham.dai_khung_lua/rong_khung_lua/so_khung_lua`), TÁCH BIỆT với `phi_khuon` —
    # không dùng để tự tính phí, chỉ để công thức của công đoạn tự quy ra tiền.
    #
    # MỞ CHO CẢ Ô QUY ĐỔI 29/08/2026 (yêu cầu người dùng): ô Quy đổi (Công thức sản lượng ra ·
    # Cách đo lượng khoán/tốc độ máy · Công thức tính lượng của Giấy/Vật tư) chạy ở TẦNG LỆNH, nơi
    # không có khái niệm "khung lụa của bước" (dữ liệu chỉ khai per-phiếu-tính-giá) — nên MỌI nơi
    # bơm `ngu_canh_lenh` phải bơm thêm `KHUNG_LUA_MAC_DINH` (mặc định 0.0) ngay sau, giống hệt cách
    # `sl_vao`/`sl_ra` được bơm thêm ở từng nơi gọi. Gõ chip này vào công thức quy đổi thì luôn ra 0
    # — đúng như đã hứa "không fill được thì coi như 0", KHÔNG NameError.
    ("dai_khung_lua", "Dài khung lụa", "Chiều dài khung lụa dùng ở bước này", "mm",
     "ô Dài khung lụa của bước, khai ở phiếu tính giá — 0 ở công thức quy đổi (không có ở tầng lệnh)",
     (LOAI_CONG_DOAN, LOAI_QUY_DOI)),
    ("rong_khung_lua", "Rộng khung lụa", "Chiều rộng khung lụa dùng ở bước này", "mm",
     "ô Rộng khung lụa của bước, khai ở phiếu tính giá — 0 ở công thức quy đổi (không có ở tầng lệnh)",
     (LOAI_CONG_DOAN, LOAI_QUY_DOI)),
    ("so_khung_lua", "Số khung lụa", "Số khung lụa sử dụng ở bước này", "khung",
     "ô Số khung lụa của bước, khai ở phiếu tính giá — 0 ở công thức quy đổi (không có ở tầng lệnh)",
     (LOAI_CONG_DOAN, LOAI_QUY_DOI)),
    ("don_gia_vat_tu", "Đơn giá vật tư",
     "Đơn giá của CHÍNH vật tư đang mở — đã quy về đơn vị công thức đang đếm", "đ",
     "ô Đơn giá của dòng vật tư, quy về đơn vị cơ sở (khai đ/tấn thì máy ÷ 1.000)",
     (LOAI_VAT_TU,)),
)

BIEN: tuple[dict, ...] = tuple(
    {"ma": ma, "nhan": nhan, "mo_ta": mo_ta, "don_vi": don_vi, "nguon": nguon, "loai": list(loai)}
    for ma, nhan, mo_ta, don_vi, nguon, loai in _BANG
)

_THEO_MA = {b["ma"]: b for b in BIEN}

# Biến engine bơm sẵn cho BA ô công thức tiền (`ngu_canh_phieu`). Biến đơn giá KHÔNG nằm đây —
# chúng lấy từ chính mục đang khai nên nơi gọi bơm thêm sau.
#
# `dinh_luong` có trong ngữ cảnh dù chỉ ô Giấy KHAI được: ba ô dùng chung một ngữ cảnh, và bơm dư
# một biến thì vô hại (validator vẫn chặn ai gõ nó vào công thức vật tư/công đoạn). Chiều NGUY HIỂM
# là ngược lại — khai mà không bơm, công thức ra 0đ im lặng; đó mới là thứ test guard canh.
# Biến của TẦNG BƯỚC: giá trị chỉ có khi engine đã biết đang tính bước nào, nên KHÔNG bơm ở tầng
# phiếu (`ngu_canh_phieu` chạy một lần cho cả thành phần, trước vòng lặp bước). Trừ chúng ra khỏi
# `MA_NGU_CANH_PHIEU` để cái chốt "khai mà quên bơm ⇒ nổ ngay" vẫn canh được đúng tầng của nó:
# tầng phiếu vẫn assert khít, tầng bước có chốt riêng ở nơi bơm.
_TANG_BUOC: frozenset[str] = frozenset(
    {"sl_vao", "sl_ra", "dai_khung_lua", "rong_khung_lua", "so_khung_lua"}
)

MA_NGU_CANH_PHIEU: tuple[str, ...] = tuple(
    b["ma"] for b in BIEN
    if set(b["loai"]) & set(_TIEN)
    and not b["ma"].startswith("don_gia")
    and b["ma"] not in _TANG_BUOC
)

# Biến tầng bước dùng được ở ô công thức TIỀN — `thanh_phan_engine` bơm đủ bộ này trong vòng lặp.
MA_TANG_BUOC_TIEN: tuple[str, ...] = tuple(
    b["ma"] for b in BIEN if set(b["loai"]) & set(_TIEN) and b["ma"] in _TANG_BUOC
)

# Ba biến khung lụa mặc định 0 ở TẦNG LỆNH (`ngu_canh_lenh`) — tầng này không có nguồn tương đương
# phiếu tính giá, nên MỌI nơi gọi `ngu_canh_lenh` rồi `safe_eval` một công thức quy_doi phải bơm
# thêm bộ này (`{**ngu_canh_lenh(...), **KHUNG_LUA_MAC_DINH}`), y hệt cách `sl_vao`/`sl_ra` được bơm
# — thiếu thì công thức lỡ gọi tới các chip này vỡ NameError thay vì ra 0 như đã hứa.
KHUNG_LUA_MAC_DINH: dict[str, float] = {
    "dai_khung_lua": 0.0, "rong_khung_lua": 0.0, "so_khung_lua": 0.0,
}


def bien_cho(loai: str) -> list[dict]:
    """Danh sách biến dùng được trong MỘT ô công thức, giữ thứ tự khai (nhóm theo chủ đề)."""
    return [b for b in BIEN if loai in b["loai"]]


def ma_hop_le(loai: str) -> frozenset[str]:
    """Tập mã hợp lệ của một ô — validator hai tầng dùng chung tập này."""
    return frozenset(b["ma"] for b in BIEN if loai in b["loai"])


def nhan(ma: str) -> str:
    """Nhãn tiếng Việt của một mã; mã lạ trả về chính nó (đừng nuốt, để người đọc thấy)."""
    b = _THEO_MA.get(ma)
    return b["nhan"] if b else ma


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def ngu_canh_phieu(
    *,
    dai_tp: float, rong_tp: float,
    dai_nguyen: float, rong_nguyen: float,
    dai_in: float, rong_in: float,
    so_luong: float, so_tp: float,
    so_trang: float, trang_moi_tay: float,
    to_dau_vao: float, to_sau_in: float, to_nguyen: float,
    so_mau: float, so_mau_pha: float, so_mat: float, so_kem: float,
    dinh_luong: float,
) -> dict[str, float]:
    """Ngữ cảnh biến cho ba ô công thức TIỀN — engine `thanh_phan_engine` gọi hàm này.

    KEYWORD-ONLY và không có mặc định là CỐ Ý: thêm một dòng vào `_BANG` mà quên bơm giá trị thì
    engine ném `TypeError` ngay lần chạy đầu, thay vì lặng lẽ thiếu biến rồi công thức ra 0đ —
    đúng kiểu hỏng đã dính với `so_mau_pha`.

    Kích thước vào đây phải đã ở MÉT (engine chia 1.000 trước khi gọi), xem cột `nguon` của bảng.
    """
    ctx = {
        "dai_tp": dai_tp, "rong_tp": rong_tp,
        "dai_nguyen": dai_nguyen, "rong_nguyen": rong_nguyen,
        "dai_in": dai_in, "rong_in": rong_in,
        "so_luong": so_luong, "so_tp": so_tp,
        "so_trang": so_trang, "trang_moi_tay": trang_moi_tay,
        "to_dau_vao": to_dau_vao, "to_sau_in": to_sau_in, "to_nguyen": to_nguyen,
        "so_mau": so_mau, "so_mau_pha": so_mau_pha, "so_mat": so_mat, "so_kem": so_kem,
        "dinh_luong": dinh_luong,
    }
    # Chốt tại chỗ: bảng khai và ngữ cảnh phải trùng khít. Test guard cũng soi, nhưng bắt ngay ở
    # đây thì lỗi hiện đúng lúc chạy chứ không đợi tới lúc ai đó nhớ chạy test.
    assert set(ctx) == set(MA_NGU_CANH_PHIEU), (
        f"bảng khai và ngữ cảnh lệch: {set(ctx) ^ set(MA_NGU_CANH_PHIEU)}")
    return ctx


def ngu_canh_lenh(quy_cach: dict | None) -> dict[str, float]:
    """Ngữ cảnh biến khi công thức chạy ở TẦNG LỆNH — quy đổi động gọi hàm này.

    CÙNG bộ biến, CÙNG tên, CÙNG đơn vị với `ngu_canh_phieu` ở trên; khác mỗi chỗ lấy số:

        `ngu_canh_phieu`  ← thành phần PHIẾU TÍNH GIÁ, tính tươi mỗi lần bấm tính.
        `ngu_canh_lenh`   ← quy cách LỆNH SẢN XUẤT (ảnh chụp lúc tạo, người kế hoạch sửa được).

    Hai hàm để CẠNH NHAU là cố ý: cùng một công thức chạy ở hai nơi phải ra một số khi lệnh chưa
    ai sửa, mà cách duy nhất giữ được điều đó là nhìn thấy cả hai cùng lúc. Tách hai file là mời
    nhau lệch, rồi báo giá 236 tờ mà lệnh đi mua 210 tờ, không ai biết bên nào đúng.

    Nơi gọi phải bơm ĐỦ — `lsx_service.quy_cach_bien(lsx)` gộp `quy_cach_json` với năm số dẫn xuất
    nằm ở CỘT của lệnh (SL đặt · con/tờ · tờ in · tờ nguyên · tờ sau in). Trước 11/08/2026 không có
    bước gộp đó, nên năm biến này trả 0 ở mọi công thức quy đổi dù màn Quy cách của lệnh đang hiện
    đủ số ngay trên đầu.

    Thiếu số thì trả 0, và `_thieu_bien` coi 0 là THIẾU ⇒ cạnh động đó bị loại khỏi đồ thị kèm câu
    "chưa biết <tên biến>". Thà không đổi được còn hơn đổi bằng số đoán.

    Nhận cả khoá MÉT (nơi gọi đã tự quy) lẫn khoá mm thô của `lsx.quy_cach_json`, và hai khoá CŨ
    `dai`/`rong` (hiểu là khổ tờ IN) để `ke_hoach_vat_tu` khỏi phải sửa cùng lúc.
    """
    qc = quy_cach or {}
    # Khoá đã ở MÉT (nơi gọi tự quy) thì lấy nguyên; khoá mm thô của lệnh thì ÷ 1.000.
    _da_met = ("dai", "rong", "dai_tp", "rong_tp", "dai_in", "rong_in",
               "dai_nguyen", "rong_nguyen")

    def _met(*khoa: str) -> float:
        """Khoá đầu tiên có số > 0 thắng."""
        for k in khoa:
            v = _f(qc.get(k))
            if v > 0:
                return v if k in _da_met else v / 1000.0
        return 0.0

    def _so(*khoa: str) -> float:
        for k in khoa:
            v = _f(qc.get(k))
            if v > 0:
                return v
        return 0.0

    so_mau = _so("so_mau") or (_f(qc.get("so_mau_a")) + _f(qc.get("so_mau_b"))
                               + _f(qc.get("so_mau_pha")))
    ctx = {
        "dai_tp": _met("dai_tp", "dai_thanh_pham"),
        "rong_tp": _met("rong_tp", "rong_thanh_pham"),
        "dai_nguyen": _met("dai_nguyen", "kho_nguyen_dai", "kho_dai"),
        "rong_nguyen": _met("rong_nguyen", "kho_nguyen_rong", "kho_rong"),
        # `dai`/`rong` (khoá cũ) hiểu là khổ tờ IN — đúng thứ `ke_hoach_vat_tu` đang bơm.
        "dai_in": _met("dai_in", "dai", "kho_in_dai"),
        "rong_in": _met("rong_in", "rong", "kho_in_rong"),
        # Năm số dưới nằm ở CỘT của `lsx` chứ không trong `quy_cach_json`; `quy_cach_bien` ghi
        # chúng vào dict dưới ĐÚNG tên biến (khoá đầu) nên số sống của lệnh luôn thắng khoá cũ
        # còn sót trong ảnh chụp — `so_con` chép từ phiếu lúc tạo lệnh là loại hay lệch nhất.
        "so_luong": _so("so_luong"),
        "so_tp": _so("so_tp", "so_con"),
        # Hai số quy cách sách MẶC ĐỊNH 1, không phải 0 như các biến khác: 1 là phần tử trung hoà
        # (`x * so_trang` giữ nguyên `x`) và đúng nghĩa thật — tờ rời/hộp là 1 trang, 1 trang/tay,
        # y như default của cột. Để 0 thì mọi công thức nhân với chúng ra 0 trên bài tờ rời, và
        # `_thieu_bien` coi 0 là THIẾU nên cạnh quy đổi rơi khỏi đồ thị dù chẳng thiếu gì.
        # Bài GHÉP cũng nhận 1: gộp nhiều sản phẩm khác nhau thì "bài này bao nhiêu trang" là câu
        # hỏi sai, và 1 là số duy nhất không bịa thêm gì (xem `quy_cach_bien_bai`).
        "so_trang": _so("so_trang") or 1.0,
        "trang_moi_tay": _so("trang_moi_tay") or 1.0,
        "to_dau_vao": _so("to_dau_vao", "so_to_ke_hoach"),
        "to_nguyen": _so("to_nguyen", "so_to_nguyen"),
        # Tờ TỐT sau in: lệnh không có cột riêng — đọc `so_luong_ra` của bước nhóm `print`.
        "to_sau_in": _so("to_sau_in"),
        "so_mau": so_mau,
        "so_mau_pha": _so("so_mau_pha"),
        "so_mat": _so("so_mat") or (2.0 if qc.get("quy_cach_in") == "hai_mat" else 1.0),
        "so_kem": _so("so_kem"),
        # kg/m² — cùng đơn vị với `dinh_luong` của công thức tiền, khỏi hai nghĩa cho một chữ.
        "dinh_luong": _f(qc.get("dinh_luong")) or _f(qc.get("gsm")) / 1000.0,
    }
    assert set(ctx) == set(MA_NGU_CANH_PHIEU), (
        f"hai hàm bơm lệch bộ biến: {set(ctx) ^ set(MA_NGU_CANH_PHIEU)}")
    return ctx


def quy_cach_bien(lsx) -> dict:
    """Quy cách của lệnh + NĂM số dẫn xuất nằm ở CỘT → dict đem đi quy đổi.

    Mười ba trong mười tám biến nằm sẵn trong `lsx.quy_cach_json` (`so_trang`/`trang_moi_tay` có
    trong đó — xem danh sách khoá `ap_quy_cach` chép sang). Năm biến còn lại thì không —
    chúng là số DẪN XUẤT, để ở cột riêng của `lsx` vì cả UI lẫn xếp lịch đọc tới:

        so_luong   ← `so_luong_dat`     (SL của ĐƠN — lệnh ép theo đơn, không theo phiếu)
        so_tp      ← `so_con`           (bình bài; `ap_quy_cach` tính lại khi đổi khổ)
        to_dau_vao ← `so_to_ke_hoach`   ─┐ hai mốc `_ap_chuoi_nguoc` đọc ra khỏi chuỗi
        to_nguyen  ← `so_to_nguyen`     ─┘ bù hao ngược
        to_sau_in  ← `so_luong_ra` của bước nhóm `print` (lệnh không có cột riêng)

    Không có bước gộp này thì năm biến đó trả 0 ở MỌI công thức quy đổi — mà `_thieu_bien` coi 0
    là THIẾU, nên cạnh động im lặng biến mất khỏi đồ thị trong khi màn Quy cách của lệnh đang hiện
    đủ số ngay trên đầu. Đó là trạng thái của hệ tới 11/08/2026.

    Ghi bằng ĐÚNG TÊN BIẾN (`so_tp`, không phải `so_con`): `ngu_canh_lenh` tra tên biến TRƯỚC, tên
    cột sau — nên số sống của lệnh luôn thắng khoá cũ còn sót trong ảnh chụp chép từ phiếu.

    Nhận `lsx` theo kiểu VỊT (chỉ đọc thuộc tính) để `bien_cong_thuc` không phải kéo theo model —
    file này là từ điển, phải nhẹ và không phụ thuộc tầng nào.
    """
    qc = dict(getattr(lsx, "quy_cach_json", None) or {})
    qc["so_luong"] = _f(getattr(lsx, "so_luong_dat", None))
    qc["so_tp"] = _f(getattr(lsx, "so_con", None))
    qc["to_dau_vao"] = _f(getattr(lsx, "so_to_ke_hoach", None))
    qc["to_nguyen"] = _f(getattr(lsx, "so_to_nguyen", None))
    # Tờ sau in: mặc định = tờ vào máy, rồi bước in CUỐI ghi đè (lệnh in hai lượt thì lượt sau mới
    # ra tờ tốt thật sự). Mặc định này BẮT BUỘC phải có — bên phiếu cũng làm y hệt
    # (`thanh_phan_engine`: `to_sau_in = float(to_dau_vao)` rồi mới dò bước in). Bỏ nó thì routing
    # không có bước in (gia công thuần, chế bản thuần) cho ra 0 ở lệnh nhưng ra `to_dau_vao` ở
    # phiếu — đúng kiểu lệch âm thầm mà cả cặp hàm này sinh ra để chặn.
    qc["to_sau_in"] = qc["to_dau_vao"]
    for cd in sorted(getattr(lsx, "cong_doans", None) or [], key=lambda c: c.thu_tu or 0):
        if getattr(cd, "nhom", None) == "print" and _f(getattr(cd, "so_luong_ra", None)) > 0:
            qc["to_sau_in"] = _f(cd.so_luong_ra)
    return qc


# Biến KHÔNG có nghĩa ở tầng BÀI GHÉP — mỗi thành viên một giá trị, gộp lại là bịa số.
# Bài ghép gộp nhiều sản phẩm KHÁC nhau lên một tờ: thẻ 500 cái 99 con/tờ nằm cạnh bìa 2.000 cuốn
# 8 con/tờ. Hỏi "bài này số lượng đặt bao nhiêu" là câu hỏi sai — không có đáp án đúng để điền.
BIEN_KHONG_CO_O_BAI: tuple[str, ...] = ("so_luong", "so_tp", "dai_tp", "rong_tp")

def quy_cach_bien_bai(bai, *, thanh_vien=(), so_to=None, muc=None) -> dict:
    """Như `quy_cach_bien` nhưng cho BÀI GHÉP — nguồn số thứ ba của cùng bộ biến.

    Bài ghép in NHIỀU lệnh chung một tờ, nên số của nó không nằm ở lệnh nào cả:

        dai_in · rong_in  ← khổ tờ in CỦA BÀI (cột riêng trên `bai_ghep`)
        dai_nguyen · rong_nguyen · dinh_luong · so_mat
                          ← quy cách CHUNG, đọc từ thành viên đầu tiên có khai. An toàn vì ghép
                            được nghĩa là cùng giấy, cùng khổ nguyên, cùng lượt in.
        to_dau_vao        ← `tong_to`        (tờ in phải cấp, đã gồm hao canh máy)
        to_nguyen         ← `to_nguyen_can`  (tờ nguyên đi lĩnh kho)
        to_sau_in         ← `so_to_tot`      (tờ tốt chung sau lượt in)
        so_mau · so_mau_pha · so_kem
                          ← `bai_ghep_service.muc_gop` — HỢP tập mực các thành viên, vì bài in một
                            lượt trên một bộ bản. Đếm ở bên đó (nơi import được engine tính giá),
                            truyền vào đây qua `muc`; file này cố ý không phụ thuộc tầng nào.

    Ba số tờ lấy từ `bai_ghep_service.tinh_so_to` — KHÔNG cộng lại ở đây. Hàm đó còn phải đi qua
    đúng cầu `to_nguyen → to` và cộng hao TRƯỚC khi chia mảnh xả; viết lại là đòi giấy sai mấy lần.

    Bốn biến còn lại để 0 CÓ CHỦ Ý, xem `BIEN_KHONG_CO_O_BAI`. Trước 11/08/2026 hàm này chưa có:
    dòng bài ghép chỉ mang ba khoá (khổ in + gsm) nên 13/16 biến bằng 0 trong im lặng, y hệt tình
    trạng của lệnh.
    """
    tv = [x for x in (thanh_vien or []) if x is not None]

    def _tu_thanh_vien(*khoa: str):
        """Giá trị đầu tiên khai được trong các thành viên — quy cách chung nên lấy cái nào cũng thế."""
        for lenh in tv:
            q = getattr(lenh, "quy_cach_json", None) or {}
            for k in khoa:
                if q.get(k):
                    return q[k]
        return None

    qc: dict = {
        "kho_in_dai": getattr(bai, "kho_in_dai", None),
        "kho_in_rong": getattr(bai, "kho_in_rong", None),
        "kho_nguyen_dai": _tu_thanh_vien("kho_nguyen_dai", "kho_dai"),
        "kho_nguyen_rong": _tu_thanh_vien("kho_nguyen_rong", "kho_rong"),
        "gsm": _tu_thanh_vien("gsm"),
        "quy_cach_in": _tu_thanh_vien("quy_cach_in"),
    }
    st = so_to or {}
    if _f(st.get("tong_to")) > 0:
        qc["to_dau_vao"] = _f(st["tong_to"])
    if _f(st.get("to_nguyen_can")) > 0:
        qc["to_nguyen"] = _f(st["to_nguyen_can"])
    if _f(st.get("so_to_tot")) > 0:
        qc["to_sau_in"] = _f(st["so_to_tot"])
    qc.update({k: v for k, v in (muc or {}).items() if _f(v) > 0})
    return {k: v for k, v in qc.items() if v is not None}
