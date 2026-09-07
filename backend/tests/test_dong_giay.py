"""Dòng giấy — bước nào nằm TRÊN dòng giấy, và ai quyết định điều đó.

Ô Đơn vị vào/ra của công đoạn là MENU ĐÓNG đúng 5 chặng (`TRAM_DONG_GIAY`), bỏ TRỐNG cả hai =
bước ngoài dòng giấy. Giữa 11/08 và 06/09/2026 nó từng trỏ vào danh mục Đơn vị & quy đổi, và câu
"có nằm trên dòng giấy không" hỏi cờ `don_vi_do.tram_dong_giay` — cờ ấy đã gỡ.

Bộ test này chốt hai điều dễ vỡ nhất:
  1. Bước ghi kẽm (đơn vị TRỐNG) phải đứng ngoài chuỗi bù hao, và SL của nó KHÔNG được về rỗng.
  2. Routing kết ở `con`/`tay` vẫn ra đúng số tờ — chỗ hai engine từng ăn hai đích khác nhau.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký metadata
from app.db import Base
from app.models.cong_doan import CongDoan
from app.models.don_vi_do import TRAM_DONG_GIAY, DonViDo, tram_chay_xuoi
from app.models.lsx import Lsx, LsxCongDoan
from app.services.dong_giay import (
    TRAM_MAC_DINH, ban_do_tram, chieu_hop_le, dich_chuoi, tram_cua, tren_dong_giay,
)
from app.services.lsx_service import LsxService


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _svc(db) -> LsxService:
    """Chỉ dùng nhánh tính THUẦN (`tinh_nguoc_routing` · `_he_so_cau`) nên repo/audit/sequence
    không được đụng tới — truyền None để khỏi kéo cả cụm fixture của `test_lsx_service`."""
    return LsxService(db, None, None, None)


def _seed_don_vi(db) -> None:
    """Danh mục đơn vị vẫn phải có 5 mã chặng — kho, mua hàng và nhãn màn lệnh đều tra tên ở đây.
    Nó chỉ KHÔNG còn quyết định bước nào nằm trên dòng giấy nữa."""
    db.add_all([
        DonViDo(ma=ma, ten=ma, ho="khac")
        for ma in (*TRAM_DONG_GIAY, "kem", "bai", "thung")
    ])
    db.commit()


# ---- bản đồ trạm ------------------------------------------------------------
def test_ban_do_tram_la_hang_so_khong_hoi_danh_muc():
    """Bản đồ chặng nay nằm TRONG code, không đọc danh mục nữa.

    Vì sao vẫn còn hàm: 5 service chuyền `ban_do` xuống các hàm thuần; giữ chữ ký là khỏi một đợt
    sửa rộng. Trả BẢN SAO — vài nơi gọi nhét thêm khoá vào map nhận được, sửa trúng hằng số dùng
    chung thì lỗi rò sang request sau.
    """
    db = _db()
    assert ban_do_tram(db) == TRAM_MAC_DINH        # bảng trắng
    _seed_don_vi(db)
    assert ban_do_tram(db) == TRAM_MAC_DINH        # có danh mục cũng không đổi
    assert ban_do_tram() == TRAM_MAC_DINH          # gọi không cần session
    ban_do_tram(db)["moi"] = "to"
    assert "moi" not in TRAM_MAC_DINH, "phải trả bản sao, không phải chính hằng số"


def test_tram_cua_chi_nhan_5_chang():
    ban_do = ban_do_tram()
    assert ban_do == {ma: ma for ma in TRAM_DONG_GIAY}
    assert tram_cua("kem", ban_do) is None         # đơn vị có thật nhưng không phải chặng
    assert tram_cua(None, ban_do) is None


def test_seed_van_hanh_van_giu_5_ma_chang():
    """Guard: seed vận hành phải còn ĐỦ 5 mã chặng trong danh mục đơn vị. Thiếu một mã là màn lệnh
    hiện mã trần thay vì tên, và kho/mua hàng mất đơn vị để nhập."""
    from app.seed_rebuild import seed_don_vi_do

    db = _db()
    seed_don_vi_do(db)
    co = {d.ma for d in db.query(DonViDo).all()}
    for ma in TRAM_DONG_GIAY:
        assert ma in co, f"seed thiếu đơn vị {ma}"


# ---- bước nào trên dòng giấy ------------------------------------------------
def test_tren_dong_giay_va_chieu():
    ban_do = ban_do_tram()
    assert tren_dong_giay("to", "cai", ban_do)
    # BỎ TRỐNG cả hai = bước ngoài dòng giấy. Đây là CÂU TRẢ LỜI, không phải "chưa khai" — nên
    # không còn lối lùi theo `nhom` (bỏ 06/09/2026): giữ nó thì cùng một bước lại được trả lời
    # khác nhau tuỳ nơi gọi có truyền `nhom` hay không.
    assert not tren_dong_giay(None, None, ban_do)
    assert not tren_dong_giay(None, None, ban_do, nhom="print")
    assert not tren_dong_giay(None, None, ban_do, nhom="prepress")
    # Mã ngoài 5 chặng (dữ liệu cũ lọt qua migration `0273`) cũng đứng ngoài, không nhận nhầm.
    assert not tren_dong_giay("bai", "kem", ban_do)
    assert not tren_dong_giay("cai", "thung", ban_do)        # một trong một ngoài → chưa hỗ trợ

    assert chieu_hop_le("to_nguyen", "to", ban_do)
    assert chieu_hop_le("to", "to", ban_do)                  # bước không đổi cách đếm (in, KCS)
    assert not chieu_hop_le("cai", "to", ban_do)             # ngược dòng
    assert not chieu_hop_le("to_nguyen", "cai", ban_do)      # nhảy cóc qua khâu in
    assert chieu_hop_le(None, None, ban_do)                  # ngoài dòng thì không có chiều nào sai


def test_don_vi_chuoi_doc_tu_routing():
    """Đơn vị từng chặng phải ĐỌC TỪ routing, không suy từ vị trí bước.

    Màn danh sách không thể suy như màn chi tiết (một tiêu đề cột, nhiều lệnh) nên server chấm sẵn
    theo từng dòng. Cái phải chốt: chặng nào routing KHÔNG nói tới thì trả None chứ đừng mượn mã
    của chặng khác lấp vào — hai cột cùng tên mà hai con số là kiểu sai khó thấy nhất.
    """
    from app.services.dong_giay import don_vi_chuoi

    ban_do = ban_do_tram()
    b = lambda t, n, v, r: {"thu_tu": t, "nhom": n, "don_vi_vao": v, "don_vi_ra": r}  # noqa: E731

    # Chế bản (đơn vị TRỐNG) đứng NGOÀI dòng giấy — không được chiếm nhãn tờ nguyên.
    dv = don_vi_chuoi([
        b(0, "prepress", None, None),
        b(1, "print", "to", "to"),
        b(2, "finishing", "to", "cai"),
    ], ban_do)
    assert dv["to"] == "to" and dv["tp"] == "cai"
    # Không có bước xả giấy ⇒ routing không nói gì về chặng tờ nguyên ⇒ None, KHÔNG mượn mã khác.
    assert dv["to_nguyen"] is None
    # Một lần đổi mức = đi thẳng tờ → thành phẩm, không có chặng giữa.
    assert dv["tay"] is None

    # Có bước xả + có chặng tay (sách): hai bước đổi mức ⇒ tp lấy bước CUỐI.
    dv = don_vi_chuoi([
        b(0, "finishing", "to_nguyen", "to"),
        b(1, "print", "to", "to"),
        b(2, "finishing", "to", "tay"),
        b(3, "finishing", "tay", "cai"),
    ], ban_do)
    assert dv["to_nguyen"] == "to_nguyen" and dv["to"] == "to" and dv["tp"] == "cai"
    # Hai lần đổi mức ⇒ lần ĐẦU là chặng giữa (tay sách), lần CUỐI là thành phẩm.
    assert dv["tay"] == "tay"

    # Routing rỗng / toàn bước ngoài dòng giấy ⇒ không bịa gì.
    assert don_vi_chuoi([], ban_do) == {
        "to": None, "to_nguyen": None, "tp": None, "tay": None}
    assert don_vi_chuoi([b(0, "prepress", None, None)], ban_do)["to"] is None


def test_cau_tram_khop_he_so_cau_cua_lenh():
    """`CAU_TRAM` (cổng khai báo) và `_he_so_cau` (nơi có hệ số thật) phải khớp nhau: khai được một
    nhịp mà không có hệ số ⇒ engine lấy 1.0 và cấp thiếu giấy trong im lặng."""
    from app.models.don_vi_do import CAU_TRAM

    db = _db()
    lsx = Lsx(ma="L1", order_id=1, order_line_id=1, so_luong_dat=100, so_con=4,
              quy_cach_json={"so_manh_xa": 2})
    cau = _svc(db)._he_so_cau(lsx)
    assert CAU_TRAM == set(cau), "cổng khai báo và bảng hệ số lệch nhau"
    assert all(tram_chay_xuoi(a, b) for a, b in CAU_TRAM)


# ---- chuỗi bù hao ngược -----------------------------------------------------
def test_buoc_ghi_kem_de_trong_don_vi_van_dung_ngoai_chuoi_va_giu_so_kem():
    """Ca thật của xưởng: ghi kẽm BỎ TRỐNG đơn vị (06/09/2026), không khai `bai → kem` nữa.

    Hai thứ phải đúng cùng lúc:
      - bước đứng NGOÀI chuỗi bù hao, "Tính ngược" không ghi đè số kẽm bằng số TỜ;
      - SL của nó vẫn tính được từ `cong_thuc_san_luong` (`so_kem`). Chốt cũ trong
        `buoc_ngoai_dong` (`if not don_vi_ra: return None`) chặn đúng ca này, nên nếu ai đặt lại
        thì kẽm về rỗng trong im lặng — test này là cái phanh.
    """
    db = _db()
    _seed_don_vi(db)
    db.add_all([
        CongDoan(id=1, ma="CTP", ten="Ghi kẽm", nhom="prepress",
                 cong_thuc_san_luong="so_kem"),
        CongDoan(id=2, ma="IN", ten="In offset", nhom="print",
                 don_vi_vao="to", don_vi_ra="to"),
        CongDoan(id=3, ma="BE", ten="Bế", nhom="finishing",
                 don_vi_vao="to", don_vi_ra="cai"),
    ])
    lsx = Lsx(id=1, ma="L1", order_id=1, order_line_id=1, so_luong_dat=1000, so_con=4,
              quy_cach_json={"so_kem": 4})
    lsx.cong_doans = [
        LsxCongDoan(step_key="s1", thu_tu=1, cong_doan_id=1, ten="Ghi kẽm", nhom="prepress",
                    so_luong_vao=4, so_luong_ra=4),
        LsxCongDoan(step_key="s2", thu_tu=2, cong_doan_id=2, ten="In offset", nhom="print",
                    don_vi_vao="to", don_vi_ra="to"),
        LsxCongDoan(step_key="s3", thu_tu=3, cong_doan_id=3, ten="Bế", nhom="finishing",
                    don_vi_vao="to", don_vi_ra="cai"),
    ]
    db.add(lsx)
    db.commit()

    rows = {r["ten"]: r for r in _svc(db).tinh_nguoc_routing(lsx)}
    # 1.000 cái ÷ 4 con/tờ = 250 tờ vào bế, in giao đúng chừng đó.
    assert rows["Bế"]["so_luong_ra"] == 1000
    assert rows["Bế"]["so_luong_vao"] == 250
    assert rows["In offset"]["so_luong_vao"] == 250
    # Ghi kẽm CÓ trong kết quả nhưng đi đường riêng: 4 bản kẽm, không phải 250 tờ.
    assert rows["Ghi kẽm"]["so_luong_ra"] == 4
    assert rows["Ghi kẽm"]["so_luong_vao"] == 4


def test_engine_tinh_gia_cung_loai_buoc_ngoai_dong_giay():
    """Engine tính giá (BÁO GIÁ) phải phân loại bước giống hệt lệnh sản xuất.

    Ghi kẽm bỏ TRỐNG đơn vị ⇒ rơi khỏi dòng giấy, và vì `nhom="prepress"` nên KHÔNG được kêu
    "chưa khai đơn vị" — kêu là kêu oan mỗi phiếu. Ngược lại, một bước không phải chế bản mà bỏ
    trống thì PHẢI kêu: bù hao của nó biến mất khỏi số giấy, im lặng là mất tiền.
    """
    from app.services.thanh_phan_engine import compute_phieu

    from .test_thanh_phan_engine import _component   # thành phần đã RESOLVE như service bơm

    cd_in = {"ten": "In offset", "nhom": "print", "don_vi_vao": "to", "don_vi_ra": "to"}

    def _canh_bao(buoc_them: dict) -> list[str]:
        tp = _component()
        tp["thanh_phams"] = [
            {"ten": buoc_them["ten"], "don_gia": 90_000, "cong_doan": buoc_them},
            {"ten": "In offset", "don_gia": 100, "cong_doan": cd_in},
        ]
        return compute_phieu(so_luong=1000, thanh_phans=[tp]).get("warnings") or []

    def _rot_khoi_dong(ws: list[str], ten: str) -> bool:
        return any(ten in w and "không được tính vào dòng giấy" in w for w in ws)

    ctp = _canh_bao({"ten": "Ghi kẽm", "nhom": "prepress",
                     "don_vi_vao": None, "don_vi_ra": None})
    assert not _rot_khoi_dong(ctp, "Ghi kẽm"), ctp

    quen = _canh_bao({"ten": "Cán màng", "nhom": "finishing",
                      "don_vi_vao": None, "don_vi_ra": None})
    assert _rot_khoi_dong(quen, "Cán màng"), quen


# ---- Ba lỗ vá 11/08/2026 còn giữ nguyên giá trị sau khi gỡ cờ trạm ----------------------------
def test_moc_so_to_doc_ra_khoi_chuoi_nen_gom_du_bu_hao():
    """LỖ 1 — nặng nhất, vì nó SAI TIỀN mà không kêu một tiếng.

    Mốc "số tờ đầu vào" phải ĐỌC RA KHỎI chuỗi bù hao tại chặng tờ in, không tính riêng bên ngoài:
    tính riêng là mất sạch bù hao của bước in, không cảnh báo nào.
    """
    from app.services.thanh_phan_engine import compute_phieu

    from .test_thanh_phan_engine import _component

    def to_dau_vao(so_to_bu_hao: int) -> int:
        tp = _component()
        tp["thanh_phams"] = [{"ten": "In offset", "don_gia": 100, "cong_doan": {
            "ten": "In", "nhom": "print", "kieu_bu_hao": "co_dinh",
            "so_to_bu_hao": so_to_bu_hao, "don_vi_vao": "to", "don_vi_ra": "to"}}]
        return compute_phieu(so_luong=5000, thanh_phans=[tp])["meta"]["components"][0]["to_dau_vao"]

    assert to_dau_vao(500) - to_dau_vao(0) == 500, "bù hao của bước in phải nằm trong số tờ"


def test_don_vi_toc_do_cua_may_doc_tu_ma_gio():
    """LỖ 2 (bản 15/08/2026) — đơn vị của tốc độ đọc từ mã máy, KHÔNG so bảng cứng nào.

    Nguyên bản test này chốt `_nang_suat_buoc`: so mã `<đv>_gio` với đơn vị bước, lệch thì trả
    `(None, None)` — vứt luôn tốc độ của một cái máy có thật, bước tụt về mỗi thời gian chuẩn bị.
    Đó là "khớp hay không khớp", không phải quy đổi.

    Nay chỉ còn một việc: biết tốc độ đếm bằng gì. Lệch đơn vị thì `_sl_theo_don_vi` đi quy đổi
    (cầu quy đổi → công thức của đơn vị); quy đổi không được thì thời gian chạy = 0 KÈM lý do —
    xem `test_chua_quy_doi_duoc_thi_KHONG_bia_gio`.
    """
    from app.services.lsx_service import ma_don_vi_toc_do

    class May:
        def __init__(self, dv): self.don_vi_toc_do = dv

    assert ma_don_vi_toc_do(May("kem_gio")) == "kem"
    assert ma_don_vi_toc_do(May("bai_gio")) == "bai"
    assert ma_don_vi_toc_do(May("m2_gio")) == "m2"
    assert ma_don_vi_toc_do(May(None)) is None


def test_dich_chuoi_theo_tram_ra_cua_buoc_cuoi():
    """LỖ 4 — hai engine ăn hai đích khác nhau khi routing KHÔNG kết ở thành phẩm."""
    he_so = {("to", "cai"): 2.0, ("to", "con"): 8.0, ("to", "tay"): 1.0}
    # 1.000 cái, mỗi tờ ra 2 cái ⇒ 500 tờ in.
    assert dich_chuoi(1000, tram_ra_cuoi="cai", cai_moi_to=2.0, he_so=he_so) == 1000
    assert dich_chuoi(1000, tram_ra_cuoi="con", cai_moi_to=2.0, he_so=he_so) == 4000   # 500 × 8
    assert dich_chuoi(1000, tram_ra_cuoi="to", cai_moi_to=2.0, he_so=he_so) == 500
    assert dich_chuoi(1000, tram_ra_cuoi="tay", cai_moi_to=2.0, he_so=he_so) == 500
    # Không biết cầu `tờ → X` thì giữ mốc TỜ, không nhân bằng số đoán.
    assert dich_chuoi(1000, tram_ra_cuoi="me", cai_moi_to=2.0, he_so=he_so) == 500


def test_routing_ket_o_con_van_ra_dung_so_to():
    """LỖ 4 trên dữ liệu thật: SÁCH (gấp tay) nên `con/tờ` KHÁC `cái/tờ`.

    32 trang, 16 trang/tay ⇒ 2 tay/cuốn ⇒ 1 tờ = 0,5 cuốn; bình 4 con/tờ. Cần 1.000 cuốn = 2.000
    tờ, dù routing kết ở `cai` hay ở `con`. Bản cũ luôn lấy thẳng SL đặt làm đích nên nhánh `con`
    ra 250 tờ — hụt 8 lần, một chiều, không ai báo.
    """
    def so_to_vao(dv_ra_cuoi: str) -> float:
        db = _db()
        _seed_don_vi(db)
        db.add_all([
            CongDoan(id=1, ma="IN", ten="In", nhom="print", don_vi_vao="to", don_vi_ra="to"),
            CongDoan(id=2, ma="BE", ten="Bế", nhom="finishing", don_vi_vao="to",
                     don_vi_ra=dv_ra_cuoi),
        ])
        lsx = Lsx(id=1, ma="L1", order_id=1, order_line_id=1, so_luong_dat=1000, so_con=4,
                  quy_cach_json={"trang_moi_tay": 16, "so_trang": 32})
        lsx.cong_doans = [
            LsxCongDoan(step_key="s1", thu_tu=1, cong_doan_id=1, ten="In", nhom="print",
                        don_vi_vao="to", don_vi_ra="to"),
            LsxCongDoan(step_key="s2", thu_tu=2, cong_doan_id=2, ten="Bế", nhom="finishing",
                        don_vi_vao="to", don_vi_ra=dv_ra_cuoi),
        ]
        db.add(lsx)
        db.commit()
        return {r["ten"]: r for r in _svc(db).tinh_nguoc_routing(lsx)}["In"]["so_luong_vao"]

    assert so_to_vao("cai") == 2000
    assert so_to_vao("con") == 2000, "kết ở `con` phải cần đúng ngần ấy giấy"


def test_may_ctp_chay_theo_so_kem_khi_buoc_dem_kem():
    """LỖ 2 (bản 15/08/2026) — bước ghi kẽm đếm `kem`, máy CTP khai `kem/giờ` ⇒ chạy đúng số kẽm.

    Bản cũ đi bằng "khớp mã": bước khai `bai → kem` cho tử tế thì `bai` không có trong bảng 5 mã,
    máy CTP hết khớp, thời lượng tụt về mỗi thời gian chuẩn bị — im lặng. Nay cùng đơn vị thì tính
    thẳng, khác đơn vị thì QUY ĐỔI, quy đổi không được thì nói ra.
    """
    from app.services.lsx_service import thoi_luong_buoc

    class May:
        def __init__(self, td, dv):
            self.toc_do, self.don_vi_toc_do = td, dv
            self.toc_do_min = self.toc_do_max = None
            self.makeready_time_default, self.fields_theo_loai = 10, None

    buoc = LsxCongDoan(lsx_id=0, thu_tu=0, ten="Ghi kẽm CTP", loai_buoc="may",
                       nhom="prepress", so_luong_vao=40, don_vi_vao="kem")
    t = thoi_luong_buoc(buoc, May(40, "kem_gio"), (40.0, "kẽm", "40 kẽm"))
    assert round(t["chay_phut"]) == 60          # 40 kẽm ÷ 40 kẽm/giờ
    assert round(t["chiem_may_phut"]) == 70     # + 10 phút chuẩn bị

    # Máy đo bằng thứ khác mà chưa khai quy đổi ⇒ KHÔNG bịa giờ, chỉ còn chuẩn bị.
    t2 = thoi_luong_buoc(buoc, May(500, "kg_gio"), None)
    assert t2["chay_phut"] == 0
    assert t2["dien_giai"]["phuong_phap"] == "chua_quy_doi"


def test_dich_chuoi_va_routing_ket_o_con():
    """LỖ 4 — routing kết ở `con` thì hai tầng ăn hai đích khác nhau, lệch đúng số con/cái.

    Sách gấp tay là ca lộ rõ nhất: 1 tờ chỉ ra 0,5 cuốn nhưng bế ra 4 con. Bản cũ ở lệnh sản xuất
    luôn lấy thẳng SL đặt làm đích ⇒ hiểu "cần 1.000 CON" trong khi khách đặt 1.000 CUỐN.
    """
    he_so = {("to", "cai"): 0.5, ("to", "con"): 4.0, ("to", "tay"): 1.0}
    assert dich_chuoi(1000, tram_ra_cuoi="cai", cai_moi_to=0.5, he_so=he_so) == 1000
    assert dich_chuoi(1000, tram_ra_cuoi="con", cai_moi_to=0.5, he_so=he_so) == 8000
    assert dich_chuoi(1000, tram_ra_cuoi="to", cai_moi_to=0.5, he_so=he_so) == 2000
    assert dich_chuoi(1000, tram_ra_cuoi="tay", cai_moi_to=0.5, he_so=he_so) == 2000
    # Không biết cầu → giữ mốc TỜ, thà bảo toàn số giấy còn hơn nhân bằng hệ số đoán.
    assert dich_chuoi(1000, tram_ra_cuoi="la", cai_moi_to=0.5, he_so=he_so) == 2000

    # Và trên lệnh thật: kết ở `con` hay `cai` đều phải ra CÙNG số tờ in.
    def so_to_in(dv_ra_cuoi: str) -> float:
        db = _db()
        _seed_don_vi(db)
        db.add_all([
            CongDoan(id=1, ma="IN", ten="In", nhom="print", don_vi_vao="to", don_vi_ra="to"),
            CongDoan(id=2, ma="BE", ten="Bế", nhom="finishing", don_vi_vao="to",
                     don_vi_ra=dv_ra_cuoi),
        ])
        lsx = Lsx(id=1, ma="L1", order_id=1, order_line_id=1, so_luong_dat=1000, so_con=4,
                  quy_cach_json={"trang_moi_tay": 16, "so_trang": 32})   # sách: 2 tay/cuốn
        lsx.cong_doans = [
            LsxCongDoan(step_key="s1", thu_tu=1, cong_doan_id=1, ten="In", nhom="print",
                        don_vi_vao="to", don_vi_ra="to"),
            LsxCongDoan(step_key="s2", thu_tu=2, cong_doan_id=2, ten="Bế", nhom="finishing",
                        don_vi_vao="to", don_vi_ra=dv_ra_cuoi),
        ]
        db.add(lsx)
        db.commit()
        return {r["ten"]: r for r in _svc(db).tinh_nguoc_routing(lsx)}["In"]["so_luong_vao"]

    assert so_to_in("cai") == 2000            # 1.000 cuốn × 2 tay = 2.000 tờ
    assert so_to_in("con") == so_to_in("cai")
