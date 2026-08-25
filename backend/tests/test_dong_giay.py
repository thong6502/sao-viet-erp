"""Dòng giấy — bước nào nằm TRÊN dòng giấy, và ai quyết định điều đó.

Trước 11/08/2026 câu trả lời là một danh sách 5 mã CỨNG trong code; nay là CỜ TRẠM trên danh mục
Đơn vị & quy đổi. Bộ test này chốt hai điều dễ vỡ nhất của lần đổi đó:
  1. Danh mục chưa gắn cờ (DB chưa migrate / bảng trắng) thì KHÔNG được im lặng cho ra 0 tờ.
  2. Bước ghi kẽm khai đơn vị THẬT (`bai → kem`) phải đứng ngoài chuỗi bù hao, không bị ghi đè số.
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


def _seed_don_vi(db, *, gan_co: bool = True) -> None:
    db.add_all([
        DonViDo(ma=ma, ten=ma, ho="khac",
                tram_dong_giay=ma if (gan_co and ma in TRAM_DONG_GIAY) else None)
        for ma in (*TRAM_DONG_GIAY, "kem", "bai", "thung")
    ])
    db.commit()


# ---- bản đồ trạm ------------------------------------------------------------
def test_danh_muc_chua_gan_co_thi_lui_ve_bo_tram_mac_dinh():
    """Lưới an toàn: thiếu nó thì không bước nào trên dòng giấy ⇒ chuỗi ngược rỗng ⇒ MỌI lệnh
    về 0 tờ trong im lặng. Hỏng kiểu đó không ai thấy cho tới lúc cấp giấy."""
    db = _db()
    assert ban_do_tram(db) == TRAM_MAC_DINH        # bảng trắng
    _seed_don_vi(db, gan_co=False)
    assert ban_do_tram(db) == TRAM_MAC_DINH        # có đơn vị nhưng chưa ai gắn cờ


def test_gan_co_roi_thi_danh_muc_thang():
    db = _db()
    _seed_don_vi(db)
    ban_do = ban_do_tram(db)
    assert ban_do == {ma: ma for ma in TRAM_DONG_GIAY}
    assert tram_cua("kem", ban_do) is None         # có trong danh mục nhưng ngoài dòng giấy
    assert tram_cua("met", ban_do) is None         # không có trong danh mục


def test_seed_van_hanh_gan_du_5_co_tram():
    """Guard: seed vận hành phải gắn cờ ĐỦ 5 trạm. Sai một dòng là số giấy của mọi lệnh lệch theo,
    mà lệch kiểu này không có test nào khác bắt được."""
    from app.seed_rebuild import seed_don_vi_do

    db = _db()
    seed_don_vi_do(db)
    co = {d.ma: d.tram_dong_giay for d in db.query(DonViDo).all()}
    for ma in TRAM_DONG_GIAY:
        assert co.get(ma) == ma, f"đơn vị {ma} phải mang cờ trạm {ma}"
    assert co.get("kem") is None and co.get("thung") is None


# ---- bước nào trên dòng giấy ------------------------------------------------
def test_tren_dong_giay_va_chieu():
    ban_do = {ma: ma for ma in TRAM_DONG_GIAY}
    assert tren_dong_giay("to", "cai", ban_do)
    assert not tren_dong_giay("bai", "kem", ban_do)          # cả hai đầu ngoài dòng
    assert not tren_dong_giay("cai", "thung", ban_do)        # một trong một ngoài → chưa hỗ trợ
    # Chưa khai đơn vị: có `nhom` thì lùi về luật cũ, không có thì đứng ngoài.
    assert tren_dong_giay(None, None, ban_do, nhom="print")
    assert not tren_dong_giay(None, None, ban_do, nhom="prepress")
    assert not tren_dong_giay(None, None, ban_do)

    assert chieu_hop_le("to_nguyen", "to", ban_do)
    assert chieu_hop_le("to", "to", ban_do)                  # bước không đổi cách đếm (in, KCS)
    assert not chieu_hop_le("cai", "to", ban_do)             # ngược dòng
    assert not chieu_hop_le("to_nguyen", "cai", ban_do)      # nhảy cóc qua khâu in
    assert chieu_hop_le("bai", "kem", ban_do)                # ngoài dòng thì không có chiều nào sai


def test_don_vi_chuoi_doc_tu_routing_khong_tra_ma():
    """Đơn vị từng chặng phải ĐỌC TỪ routing, kể cả khi xưởng đặt mã riêng.

    Màn danh sách không thể suy như màn chi tiết (một tiêu đề cột, nhiều lệnh) nên server chấm sẵn
    theo từng dòng. Mã ở đây cố ý KHÔNG phải `to`/`cai`: dò mã là trượt.
    """
    from app.services.dong_giay import don_vi_chuoi

    ban_do = {"to_lon": "to_nguyen", "to_chay": "to", "sp_xong": "cai", "tay_gap": "tay"}
    b = lambda t, n, v, r: {"thu_tu": t, "nhom": n, "don_vi_vao": v, "don_vi_ra": r}  # noqa: E731

    # Chế bản (`m2 → bai`) đứng NGOÀI dòng giấy — không được chiếm nhãn tờ nguyên.
    dv = don_vi_chuoi([
        b(0, "prepress", "m2", "bai"),
        b(1, "print", "to_chay", "to_chay"),
        b(2, "finishing", "to_chay", "sp_xong"),
    ], ban_do)
    assert dv["to"] == "to_chay" and dv["tp"] == "sp_xong"
    # Không có bước xả giấy ⇒ routing không nói gì về chặng tờ nguyên ⇒ None, KHÔNG mượn mã khác.
    assert dv["to_nguyen"] is None
    # Một lần đổi mức = đi thẳng tờ → thành phẩm, không có chặng giữa.
    assert dv["tay"] is None

    # Có bước xả + có chặng tay (sách): hai bước đổi mức ⇒ tp lấy bước CUỐI.
    dv = don_vi_chuoi([
        b(0, "finishing", "to_lon", "to_chay"),
        b(1, "print", "to_chay", "to_chay"),
        b(2, "finishing", "to_chay", "tay_gap"),
        b(3, "finishing", "tay_gap", "sp_xong"),
    ], ban_do)
    assert dv["to_nguyen"] == "to_lon" and dv["to"] == "to_chay" and dv["tp"] == "sp_xong"
    # Hai lần đổi mức ⇒ lần ĐẦU là chặng giữa (tay sách), lần CUỐI là thành phẩm.
    assert dv["tay"] == "tay_gap"

    # Routing rỗng / toàn bước ngoài dòng giấy ⇒ không bịa gì.
    assert don_vi_chuoi([], ban_do) == {
        "to": None, "to_nguyen": None, "tp": None, "tay": None}
    assert don_vi_chuoi([b(0, "prepress", "m2", "bai")], ban_do)["to"] is None


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
def test_buoc_ghi_kem_khai_don_vi_that_van_dung_ngoai_chuoi():
    """Ca thật của xưởng: ghi kẽm nay khai `bai → kem` thay vì bỏ trống đơn vị.

    Bản cũ lọc chuỗi bằng "có khai đơn vị hay không" nên bước này lọt vào chuỗi, và "Tính ngược"
    ghi đè số kẽm bằng số TỜ. Bản mới hỏi cờ trạm nên nó đứng ngoài, số kẽm giữ nguyên.
    """
    db = _db()
    _seed_don_vi(db)
    db.add_all([
        CongDoan(id=1, ma="CTP", ten="Ghi kẽm", nhom="prepress",
                 don_vi_vao="bai", don_vi_ra="kem"),
        CongDoan(id=2, ma="IN", ten="In offset", nhom="print",
                 don_vi_vao="to", don_vi_ra="to"),
        CongDoan(id=3, ma="BE", ten="Bế", nhom="finishing",
                 don_vi_vao="to", don_vi_ra="cai"),
    ])
    lsx = Lsx(id=1, ma="L1", order_id=1, order_line_id=1, so_luong_dat=1000, so_con=4,
              quy_cach_json={})
    lsx.cong_doans = [
        LsxCongDoan(step_key="s1", thu_tu=1, cong_doan_id=1, ten="Ghi kẽm", nhom="prepress",
                    don_vi_vao="bai", don_vi_ra="kem", so_luong_vao=4, so_luong_ra=4),
        LsxCongDoan(step_key="s2", thu_tu=2, cong_doan_id=2, ten="In offset", nhom="print",
                    don_vi_vao="to", don_vi_ra="to"),
        LsxCongDoan(step_key="s3", thu_tu=3, cong_doan_id=3, ten="Bế", nhom="finishing",
                    don_vi_vao="to", don_vi_ra="cai"),
    ]
    db.add(lsx)
    db.commit()

    rows = {r["ten"]: r for r in _svc(db).tinh_nguoc_routing(lsx)}
    assert "Ghi kẽm" not in rows, "bước ngoài dòng giấy không được vào chuỗi bù hao"
    # 1.000 cái ÷ 4 con/tờ = 250 tờ vào bế, in giao đúng chừng đó.
    assert rows["Bế"]["so_luong_ra"] == 1000
    assert rows["Bế"]["so_luong_vao"] == 250
    assert rows["In offset"]["so_luong_vao"] == 250


def test_engine_tinh_gia_cung_loai_buoc_ngoai_dong_giay():
    """Engine tính giá là hàm THUẦN nên tự nó không tra được danh mục — tầng gọi (`tinh_gia_service`)
    bơm `tram_vao`/`tram_ra` xuống. Thiếu đường này thì bước ghi kẽm khai `bai → kem` lọt vào chuỗi
    giấy của BÁO GIÁ (chỉ lệnh sản xuất được vá), đẻ cảnh báo "đứt đơn vị" giả và nhận hệ số 1.
    """
    from app.services.thanh_phan_engine import compute_phieu

    from .test_thanh_phan_engine import _component   # thành phần đã RESOLVE như service bơm

    ctp = {"ten": "Ghi kẽm", "nhom": "prepress", "don_vi_vao": "bai", "don_vi_ra": "kem"}
    cd_in = {"ten": "In offset", "nhom": "print", "don_vi_vao": "to", "don_vi_ra": "to",
             "tram_vao": "to", "tram_ra": "to"}

    def _canh_bao(cong_doan_ctp: dict) -> list[str]:
        tp = _component()
        tp["thanh_phams"] = [
            {"ten": "Ghi kẽm", "don_gia": 90_000, "cong_doan": cong_doan_ctp},
            {"ten": "In offset", "don_gia": 100, "cong_doan": cd_in},
        ]
        return compute_phieu(so_luong=1000, thanh_phans=[tp]).get("warnings") or []

    co_co = _canh_bao({**ctp, "tram_vao": None, "tram_ra": None})
    khong_co = _canh_bao(ctp)
    assert not any("đứt đơn vị" in w or "chưa biết hệ số" in w for w in co_co), co_co
    assert any("đứt đơn vị" in w or "chưa biết hệ số" in w for w in khong_co), khong_co


# ---- Bốn lỗ vá 11/08/2026: cờ trạm mở cửa cho đơn vị tự khai, nhưng ruột engine còn so bằng MÃ --
def test_don_vi_rieng_cua_xuong_van_gom_du_bu_hao():
    """LỖ 1 — nặng nhất, vì nó SAI TIỀN mà không kêu một tiếng.

    Xưởng khai mã riêng cho chặng tờ in (`to_in`) rồi gắn cờ trạm *tờ in* — đúng thứ ô "Trạm trên
    dòng giấy" mời họ làm. Bản cũ đọc mốc số tờ bằng cách dò đúng chữ `to`, không thấy thì lặng lẽ
    rơi về số tờ trần: mất SẠCH bù hao, không cảnh báo nào.
    """
    from app.services.thanh_phan_engine import compute_phieu

    from .test_thanh_phan_engine import _component

    def to_dau_vao(ma: str) -> int:
        tp = _component()
        tp["thanh_phams"] = [{"ten": "In offset", "don_gia": 100, "cong_doan": {
            "ten": "In", "nhom": "print", "kieu_bu_hao": "co_dinh", "so_to_bu_hao": 500,
            "don_vi_vao": ma, "don_vi_ra": ma, "tram_vao": "to", "tram_ra": "to"}}]
        return compute_phieu(so_luong=5000, thanh_phans=[tp])["meta"]["components"][0]["to_dau_vao"]

    assert to_dau_vao("to_in") == to_dau_vao("to"), "đổi MÃ đơn vị không được đổi số giấy"


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
