"""Từ điển BIẾN công thức — canh hai tầng còn khớp nhau.

Danh sách biến từng nằm ở HAI nơi rời nhau: frontend giữ mảng cứng (quyết định chip nào hiện +
validator chấp nhận gì), backend giữ `ctx_vars` (quyết định biến nào có GIÁ TRỊ). Không gì ép chúng
khớp, và chúng ĐÃ lệch — `so_mau_pha` có giá trị mà không gõ được, `so_vi_tri`/`dien_tich` gõ được
ở mọi ô mà chỉ công đoạn mới có giá trị.

Nay một từ điển (`services/bien_cong_thuc`) và frontend hỏi qua API. Hai test dưới khoá cả hai
chiều lệch — thiếu chúng thì mỗi lần thêm biến là một cặp lệch mới, và lệch kiểu này KHÔNG có test
nào khác bắt được vì công thức sai vẫn "chạy", chỉ ra 0đ.
"""
import app.services.thanh_phan_engine as tpe
from app.services.bien_cong_thuc import (
    BIEN, LOAI, LOAI_CONG_DOAN, LOAI_GIAY, LOAI_QUY_DOI, LOAI_VAT_TU, bien_cho, ma_hop_le,
)
from app.services.thanh_phan_engine import compute_phieu

from .test_thanh_phan_engine import _component

# Khoá trong ngữ cảnh eval KHÔNG phải biến người dùng gõ — hàm toán học engine phơi sẵn.
_KHONG_PHAI_BIEN = set(tpe.MATH_FUNCS)


def _phieu(*, giay: str = "", vat_tu: str = "", cong_doan: str = "") -> dict:
    tp = _component()
    tp["cong_thuc_gia"] = giay
    tp["vat_tus"] = [{"ten": "Mực", "don_gia": 100, "don_vi_gia": "kg",
                      "cong_thuc_gia": vat_tu}] if vat_tu else []
    tp["thanh_phams"] = [{"ten": "Bế", "don_gia": 0, "cong_doan": {
        "ten": "Bế", "nhom": "finishing", "don_vi_vao": "to", "don_vi_ra": "cai",
        "tram_vao": "to", "tram_ra": "cai", "cong_thuc_gia": cong_doan}}] if cong_doan else []
    return tp


def test_moi_bien_khai_trong_tu_dien_deu_co_gia_tri_that():
    """Chiều 1: khai mà engine không bơm ⇒ người dùng gõ chip vào là công thức nổ, ra 0đ.

    Dựng công thức CỘNG HẾT biến của từng ô rồi chạy thật: thiếu biến nào là `safe_eval` ném lỗi
    và engine đẻ cảnh báo "lỗi công thức" — bắt được ngay, không cần soi tay.
    """
    for loai in (LOAI_GIAY, LOAI_VAT_TU, LOAI_CONG_DOAN):
        ct = " + ".join(sorted(ma_hop_le(loai)))
        res = compute_phieu(so_luong=1000, thanh_phans=[_phieu(**{loai: ct})])
        loi = [w for w in res.get("warnings") or [] if "lỗi công thức" in w]
        assert not loi, f"ô {loai}: {loi}"


def test_khong_co_bien_nao_chay_duoc_ma_khong_ai_khai():
    """Chiều 2: engine bơm mà từ điển không khai ⇒ biến CHẠY ĐƯỢC nhưng không ai biết để gõ.

    Đây đúng là ca `so_mau_pha` đã dính. Rình `safe_eval` để lấy tập khoá engine thật sự bơm vào.
    """
    thay = []
    that = tpe.safe_eval

    def rinh(cong_thuc, ctx):
        thay.append(set(ctx))
        return that(cong_thuc, ctx)

    tpe.safe_eval = rinh
    try:
        compute_phieu(so_luong=1000, thanh_phans=[
            _phieu(giay="dai_tp", vat_tu="so_mau", cong_doan="so_luong")])
    finally:
        tpe.safe_eval = that

    assert thay, "không câu được lần gọi safe_eval nào — test đã mất tác dụng"
    khai = {b["ma"] for b in BIEN}
    thua = set().union(*thay) - khai - _KHONG_PHAI_BIEN
    assert not thua, f"engine bơm biến chưa khai trong từ điển: {sorted(thua)}"


def test_bon_o_dung_chung_bo_bien_va_hai_chip_rieng_cua_buoc():
    """Giấy 19 · Vật tư 18 · Công đoạn 22 · Quy đổi 23 (18 + `sl_vao`/`sl_ra` + 3 khung lụa).

    Năm điều dễ trượt lại nếu không khoá:
      · Công đoạn KHÔNG có biến tiền — không có ô nhập đơn giá ở cả phiếu lẫn danh mục.
      · Quy đổi dùng chung bộ biến với công thức tiền, cộng `dinh_luong` (tờ→kg cần nó).
      · Ba biến VAI TRÒ cũ (`dai` · `rong` · `so_con`) đã bỏ — thay bằng tên khổ cụ thể.
      · `so_trang`/`trang_moi_tay` (03/09/2026) có ở CẢ BỐN ô — cả công thức tiền lẫn công thức
        lượng đều phải tính được theo trang, không chỉ theo tờ.
      · `sl_vao`/`sl_ra` CHỈ Công đoạn + Quy đổi có, và chỉ TẦNG BƯỚC bơm được (`lsx_service`):
        công thức lượng cần số của CHÍNH bước, mà quy cách lệnh không biết bước nào đang hỏi.
      · `dai_khung_lua`/`rong_khung_lua`/`so_khung_lua` CÙNG hai ô đó — 29/08/2026 mở thêm cho Quy
        đổi (trước chỉ Công đoạn); tầng lệnh không có nguồn nên `ngu_canh_lenh` không bơm, luôn 0
        (`KHUNG_LUA_MAC_DINH`), y hệt cách `sl_vao`/`sl_ra` bơm ngoài.
    """
    KHUNG_LUA = {"dai_khung_lua", "rong_khung_lua", "so_khung_lua"}
    CUA_BUOC = {"sl_vao", "sl_ra"} | KHUNG_LUA
    dem = {loai: len(bien_cho(loai)) for loai in LOAI}
    assert dem == {LOAI_GIAY: 19, LOAI_VAT_TU: 18, LOAI_CONG_DOAN: 22, LOAI_QUY_DOI: 23}, dem

    chung = ma_hop_le(LOAI_CONG_DOAN) - CUA_BUOC    # 17 biến ai cũng có
    assert {"so_trang", "trang_moi_tay"} <= chung, "hai chip quy cách sách phải có ở MỌI ô"
    assert ma_hop_le(LOAI_GIAY) - chung == {"dinh_luong", "don_gia_giay"}
    assert ma_hop_le(LOAI_VAT_TU) - chung == {"don_gia_vat_tu"}
    # Định lượng là thuộc tính CỦA GIẤY — chỉ ô Giấy khai được; Quy đổi giữ vì cần cho tờ→kg.
    assert ma_hop_le(LOAI_QUY_DOI) - chung == {"dinh_luong"} | CUA_BUOC
    # Năm chip tầng BƯỚC (`sl_*` + khung lụa). Công đoạn có (15/08/2026, mở rộng 29/08/2026) vì
    # công thức tiền của nó phải đếm được đúng lượng/dụng cụ đi qua chính nó; Quy đổi có vì chạy ở
    # tầng lệnh cần cùng bộ chip đó cho "Công thức sản lượng ra"/"Cách đo lượng khoán". Giấy/Vật tư
    # KHÔNG — hai ô đó tính tiền/lượng cho một MẶT HÀNG, không đứng ở bước nào cả.
    for loai in (LOAI_GIAY, LOAI_VAT_TU):
        assert not (CUA_BUOC & ma_hop_le(loai)), f"{loai} không được có chip của bước"
    assert CUA_BUOC <= ma_hop_le(LOAI_CONG_DOAN)
    assert CUA_BUOC <= ma_hop_le(LOAI_QUY_DOI)
    assert not any(m.startswith("don_gia") for m in chung), "Công đoạn không có biến tiền"
    assert not ({"dai", "rong", "so_con"} & chung), "biến vai trò cũ phải hết"


def test_ngu_canh_quy_doi_bom_du_tru_hai_chip_cua_buoc():
    """`ngu_canh` dựng từ QUY CÁCH nên trả đủ bộ chung, TRỪ 5 chip tầng bước.

    `sl_vao`/`sl_ra` do `lsx_service` bơm thêm ở tầng bước (`{**ngu_canh_lenh(qc), "sl_vao": …}`) —
    quy cách của lệnh không biết đang hỏi bước nào. Ba chip khung lụa cũng vậy nhưng KHÔNG có nguồn
    ở tầng lệnh, nên `lsx_service` bơm cố định 0 (`KHUNG_LUA_MAC_DINH`), không phải số thật. Thiếu
    một chip KHÁC là dòng quy đổi dùng nó rơi khỏi đồ thị, mà chỉ lộ ra ở màn kế hoạch vật tư.
    """
    from app.services.quy_doi_service import ngu_canh

    CUA_BUOC = {"sl_vao", "sl_ra", "dai_khung_lua", "rong_khung_lua", "so_khung_lua"}
    ctx = ngu_canh({"kho_in_dai": 860, "kho_in_rong": 650, "kho_nguyen_dai": 860,
                    "kho_nguyen_rong": 650, "gsm": 300, "so_con": 99})
    assert set(ctx) >= ma_hop_le(LOAI_QUY_DOI) - CUA_BUOC
    assert not (set(ctx) & CUA_BUOC), "chip của bước không được lọt vào ngữ cảnh quy cách"
    assert ctx["dai_in"] == 0.86 and ctx["dinh_luong"] == 0.3 and ctx["so_tp"] == 99
    # Quy cách KHÔNG khai trang (thẻ nhân viên) ⇒ hai chip sách về 1, KHÔNG về 0: `x * so_trang`
    # phải giữ nguyên `x`, và `_thieu_bien` coi 0 là THIẾU nên 0 sẽ đánh rơi cạnh quy đổi.
    assert ctx["so_trang"] == 1 and ctx["trang_moi_tay"] == 1
    # Có khai thì lấy số thật — ca sách 160 trang, tay 16 (kỷ yếu 10 bài in).
    sach = ngu_canh({"so_trang": 160, "trang_moi_tay": 16})
    assert sach["so_trang"] == 160 and sach["trang_moi_tay"] == 16
    # Khoá CŨ `dai`/`rong` (mét) vẫn hiểu là khổ tờ IN — `ke_hoach_vat_tu` đang bơm kiểu đó.
    cu = ngu_canh({"dai": 0.86, "rong": 0.65, "gsm": 300})
    assert cu["dai_in"] == 0.86 and cu["rong_in"] == 0.65


def test_quy_doi_service_doc_tu_dien_chung():
    """`quy_doi_service.BIEN` phải là DẪN XUẤT của từ điển, không phải bản khai thứ hai."""
    from app.services.quy_doi_service import BIEN as BIEN_QD

    assert set(BIEN_QD) == ma_hop_le(LOAI_QUY_DOI)


def test_tu_dien_khong_co_ma_trung_va_loai_hop_le():
    ma = [b["ma"] for b in BIEN]
    assert len(ma) == len(set(ma)), "mã biến bị khai trùng"
    for b in BIEN:
        assert b["loai"], f"biến {b['ma']} không thuộc ô nào — khai ra để làm gì"
        assert set(b["loai"]) <= set(LOAI), f"biến {b['ma']} có loại lạ: {b['loai']}"
        assert b["nhan"] and b["mo_ta"] and b["don_vi"], f"biến {b['ma']} thiếu nhãn/mô tả/đơn vị"


def test_api_tra_dung_bo_loc():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        tok = c.post("/api/auth/login",
                     json={"username": "admin", "password": "admin123"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        het = c.get("/api/bien-cong-thuc", headers=h).json()["items"]
        assert len(het) == len(BIEN)
        cd = c.get("/api/bien-cong-thuc?loai=cong_doan", headers=h).json()["items"]
        assert {b["ma"] for b in cd} == ma_hop_le(LOAI_CONG_DOAN)
        assert {b["ma"] for b in cd} == {b["ma"] for b in bien_cho(LOAI_CONG_DOAN)}
        assert c.get("/api/bien-cong-thuc?loai=bay_ba", headers=h).status_code == 422


def test_moi_bien_deu_noi_duoc_SO_NAY_O_DAU_RA():
    """Cột `nguon` là bắt buộc — nó trả lời câu người khai công thức luôn hỏi.

    Ca thật: `to_dau_vao` ĐÃ gồm bù hao. Không nói ra thì người khai nhân thêm hệ số hao lần nữa,
    ra số giấy phồng mà nhìn công thức vẫn thấy hợp lý.
    """
    for b in BIEN:
        assert b["nguon"], f"biến {b['ma']} chưa nói số ở đâu ra"
    # Ba biến tờ phải nói rõ đã gồm bù hao, không thì lời cảnh báo nằm trong đầu người viết code.
    for ma in ("to_dau_vao", "to_sau_in", "to_nguyen"):
        nguon = next(b["nguon"] for b in BIEN if b["ma"] == ma)
        assert "BÙ HAO" in nguon.upper(), f"{ma}: nguồn phải nói rõ nó ra từ chuỗi bù hao"


class _Buoc:
    def __init__(self, thu_tu, nhom, so_luong_ra):
        self.thu_tu, self.nhom, self.so_luong_ra = thu_tu, nhom, so_luong_ra


class _Lenh:
    """Đủ thuộc tính mà `quy_cach_bien` đọc — hàm nhận theo kiểu VỊT nên khỏi dựng cả ORM."""

    def __init__(self, **kw):
        self.quy_cach_json = kw.get("quy_cach_json") or {}
        self.so_luong_dat = kw.get("so_luong_dat")
        self.so_con = kw.get("so_con")
        self.so_to_ke_hoach = kw.get("so_to_ke_hoach")
        self.so_to_nguyen = kw.get("so_to_nguyen")
        self.cong_doans = kw.get("cong_doans") or []


# Quy cách kiểu LSX26-0024: thẻ nhân viên 86×54 trên Couché 300, khổ 860×650, in 2 mặt 4+1.
_QC_THE = {
    "kho_nguyen_dai": 860, "kho_nguyen_rong": 650, "kho_in_dai": 860, "kho_in_rong": 650,
    "dai_thanh_pham": 86, "rong_thanh_pham": 54, "gsm": 300,
    "quy_cach_in": "hai_mat", "so_mau_a": 4, "so_mau_b": 1, "so_mau_pha": 0, "so_kem": 5,
}


def test_quy_cach_bien_bom_nam_so_nam_o_cot_cua_lenh():
    """Năm biến này KHÔNG nằm trong `quy_cach_json` — chúng ở cột riêng của `lsx`.

    Thiếu bước gộp thì cả năm trả 0, mà `_thieu_bien` coi 0 là THIẾU ⇒ mọi cạnh quy đổi dùng chúng
    im lặng rơi khỏi đồ thị, trong khi màn Quy cách của lệnh đang hiện đủ số ngay trên đầu. Đây là
    bug thật của hệ tới 11/08/2026, không phải ca giả định.
    """
    from app.services.bien_cong_thuc import ngu_canh_lenh, quy_cach_bien

    lenh = _Lenh(quy_cach_json=_QC_THE, so_luong_dat=500, so_con=99,
                 so_to_ke_hoach=236, so_to_nguyen=236,
                 cong_doans=[_Buoc(0, "prepress", 0), _Buoc(1, "print", 232),
                             _Buoc(2, "finishing", 23_364)])

    tran = ngu_canh_lenh(_QC_THE)          # đường CŨ: quy cách trần
    assert [tran[k] for k in ("so_luong", "so_tp", "to_dau_vao", "to_nguyen", "to_sau_in")] \
        == [0.0] * 5, "ca hỏng phải còn hỏng — không thì test này không canh gì cả"

    ctx = ngu_canh_lenh(quy_cach_bien(lenh))
    assert ctx["so_luong"] == 500 and ctx["so_tp"] == 99
    assert ctx["to_dau_vao"] == 236 and ctx["to_nguyen"] == 236
    assert ctx["to_sau_in"] == 232, "tờ tốt sau in đọc `so_luong_ra` của bước nhóm print"
    # Mười một biến còn lại không được đổi nghĩa khi thêm bước gộp.
    assert ctx["dai_in"] == 0.86 and ctx["dinh_luong"] == 0.3
    assert ctx["so_mau"] == 5 and ctx["so_mat"] == 2 and ctx["so_kem"] == 5


def test_routing_khong_co_buoc_in_thi_to_sau_in_nga_ve_to_vao_may():
    """Lệnh gia công thuần (cán/bế/đóng gói, không in) — `to_sau_in` phải = tờ vào máy.

    Bên phiếu làm đúng thế: `thanh_phan_engine` đặt `to_sau_in = to_dau_vao` rồi mới để bước in ghi
    đè. Bản đầu của `quy_cach_bien` chỉ ghi khoá khi CÓ bước in, nên ca này ra 0 ở lệnh mà ra 236 ở
    phiếu — cùng một công thức, hai số. Test ca sách không bắt được vì sách có bước in.
    """
    from app.services.bien_cong_thuc import ngu_canh_lenh, quy_cach_bien

    khong_in = _Lenh(quy_cach_json=_QC_THE, so_luong_dat=500, so_con=99,
                     so_to_ke_hoach=236, so_to_nguyen=236,
                     cong_doans=[_Buoc(0, "finishing", 500)])
    ctx = ngu_canh_lenh(quy_cach_bien(khong_in))
    assert ctx["to_sau_in"] == ctx["to_dau_vao"] == 236

    # Có bước in thì bước in vẫn thắng, và bước in CUỐI mới là số chốt.
    hai_luot = _Lenh(quy_cach_json=_QC_THE, so_to_ke_hoach=236,
                     cong_doans=[_Buoc(0, "print", 200), _Buoc(1, "print", 180),
                                 _Buoc(2, "finishing", 150)])
    assert ngu_canh_lenh(quy_cach_bien(hai_luot))["to_sau_in"] == 180


def test_so_song_cua_lenh_thang_anh_chup_chep_tu_phieu():
    """`so_con` chép từ phiếu lúc tạo lệnh vẫn nằm trong ảnh chụp; sửa khổ ở lệnh là nó THIU.

    `ap_quy_cach` bình bài lại rồi ghi vào CỘT `lsx.so_con`, không sửa khoá cũ trong JSON. Nên
    `quy_cach_bien` phải ghi bằng đúng TÊN BIẾN (`so_tp`) để thắng — ghi bằng tên cột thì
    `_so("so_tp", "so_con")` vớ phải số thiu và cả bảng vật tư lệch.
    """
    from app.services.bien_cong_thuc import ngu_canh_lenh, quy_cach_bien

    lenh = _Lenh(quy_cach_json={**_QC_THE, "so_con": 48}, so_con=99, so_luong_dat=500)
    assert ngu_canh_lenh(quy_cach_bien(lenh))["so_tp"] == 99


def test_bai_ghep_bom_du_moi_bien_co_nghia_o_tang_bai():
    """Bài ghép là nguồn số THỨ BA của cùng bộ biến — trước 11/08/2026 nó chỉ mang 3 khoá.

    Dòng bài ghép trong bảng cân đối vật tư dựng tay `{kho_in_dai, kho_in_rong, gsm}`, nên 13/16
    biến bằng 0: công thức quy đổi nào chạm `to_dau_vao` là cạnh tắt, dòng nhận "chưa đánh giá
    được" mà không ai truy ra vì sao.
    """
    from app.services.bien_cong_thuc import (
        BIEN_KHONG_CO_O_BAI, MA_NGU_CANH_PHIEU, ngu_canh_lenh, quy_cach_bien_bai,
    )

    bai = _Lenh(quy_cach_json={})          # chỉ cần hai thuộc tính khổ in
    bai.kho_in_dai, bai.kho_in_rong = 860, 650
    tv = [_Lenh(quy_cach_json={"kho_nguyen_dai": 1090, "kho_nguyen_rong": 790, "gsm": 300,
                               "quy_cach_in": "hai_mat"})]
    so_to = {"so_to_tot": 5_000, "tong_to": 5_150, "to_nguyen_can": 1_288}
    # Hợp tập mực do `bai_ghep_service.muc_gop` đếm: thẻ CMYK ghép bìa CMYK+185C ⇒ 5 bản.
    muc = {"so_mau_a": 4, "so_mau_b": 0, "so_mau_pha": 1, "so_kem": 5}

    ctx = ngu_canh_lenh(quy_cach_bien_bai(bai, thanh_vien=tv, so_to=so_to, muc=muc))
    assert ctx["dai_in"] == 0.86 and ctx["rong_in"] == 0.65        # khổ CỦA BÀI
    assert ctx["dai_nguyen"] == 1.09 and ctx["rong_nguyen"] == 0.79  # giấy chung, từ thành viên
    assert ctx["dinh_luong"] == 0.3 and ctx["so_mat"] == 2
    # Ba số tờ lấy nguyên từ `tinh_so_to`, KHÔNG cộng lại ở đây.
    assert ctx["to_dau_vao"] == 5_150 and ctx["to_nguyen"] == 1_288
    assert ctx["to_sau_in"] == 5_000
    assert ctx["so_mau"] == 5 and ctx["so_mau_pha"] == 1 and ctx["so_kem"] == 5

    # ĐÚNG BỐN biến để 0, và là bốn cái không có nghĩa ở tầng bài — mọi cái khác phải có số.
    assert {k for k in MA_NGU_CANH_PHIEU if not ctx[k]} == set(BIEN_KHONG_CO_O_BAI)
    # Bài chưa tính được số tờ (chưa gộp bước nào) → ba biến tờ trả 0, không dựng số ảo.
    assert ngu_canh_lenh(quy_cach_bien_bai(bai, thanh_vien=tv, muc=muc))["to_dau_vao"] == 0


def test_hai_ham_bom_cung_mot_bo_bien():
    """Hai nguồn số (phiếu · lệnh) phải trả CÙNG bộ khoá — lệch một cái là công thức chạy được ở
    màn này, ra 0 ở màn kia mà không ai báo."""
    import inspect

    from app.services.bien_cong_thuc import MA_NGU_CANH_PHIEU, ngu_canh_lenh, ngu_canh_phieu

    assert set(ngu_canh_lenh({})) == set(MA_NGU_CANH_PHIEU)
    assert set(ngu_canh_lenh({})) == set(inspect.signature(ngu_canh_phieu).parameters)


def test_engine_dung_dung_ngu_canh_khai_trong_tu_dien():
    """`ngu_canh_phieu` là CỬA DUY NHẤT dựng ngữ cảnh — khai thừa/thiếu một biến là nổ ngay.

    Trước đây engine giữ dict rời: thêm dòng vào bảng mà quên bơm giá trị thì công thức lặng lẽ
    ra 0đ. Nay hàm keyword-only không mặc định ⇒ TypeError ngay lần chạy đầu.
    """
    import inspect

    from app.services.bien_cong_thuc import MA_NGU_CANH_PHIEU, ngu_canh_phieu

    tham_so = inspect.signature(ngu_canh_phieu).parameters
    assert set(tham_so) == set(MA_NGU_CANH_PHIEU), "tham số hàm lệch bảng khai"
    assert all(p.kind is p.KEYWORD_ONLY and p.default is p.empty for p in tham_so.values()), \
        "phải keyword-only và KHÔNG mặc định — có mặc định là thiếu biến vẫn chạy, ra 0đ im lặng"
    # Ngữ cảnh phiếu = 17 biến chung + `dinh_luong`. Biến đơn giá do nơi gọi bơm riêng cho ô của nó.
    # Năm chip tầng BƯỚC nằm ngoài (`sl_vao`/`sl_ra` + ba chip khung lụa): `ngu_canh_phieu` chạy một
    # lần cho cả thành phần, chưa biết bước nào — engine bơm chúng trong vòng lặp (`MA_TANG_BUOC_TIEN`).
    CUA_BUOC = {"sl_vao", "sl_ra", "dai_khung_lua", "rong_khung_lua", "so_khung_lua"}
    assert set(MA_NGU_CANH_PHIEU) == (ma_hop_le(LOAI_CONG_DOAN) - CUA_BUOC) | {"dinh_luong"}
    assert not (set(MA_NGU_CANH_PHIEU) & CUA_BUOC)
