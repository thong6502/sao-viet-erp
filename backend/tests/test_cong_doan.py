"""Công đoạn — danh mục CRUD/validate + routing_engine (cascade/basis/step-cost/kẽm §4–5)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.cong_doan import CongDoan  # noqa: F401 — đăng ký metadata
from app.models.department import Department
from app.models.piece_work import PieceRate
from app.repositories.cong_doan_repo import CongDoanRepository
from app.schemas.cong_doan import CongDoanIn, CongDoanRow
from app.services.cong_doan_service import (
    CongDoanDuplicate,
    CongDoanService,
    CongDoanValidationError,
)
from app.services import routing_engine as re


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    _seed_don_vi(db)
    return db, CongDoanService(CongDoanRepository(db))


def _seed_don_vi(db) -> None:
    """Danh mục Đơn vị tối thiểu — kho / mua hàng / khoán vẫn tra tên ở đây.

    Ô đơn vị vào/ra của CÔNG ĐOẠN thì từ 06/09/2026 KHÔNG đọc bảng này nữa: nó là menu đóng đúng
    5 chặng dòng giấy trong code. Vẫn seed để test nào cần đơn vị (vật tư, khoán) có mà dùng.
    """
    from app.models.don_vi_do import TRAM_DONG_GIAY, DonViDo

    db.add_all([
        DonViDo(ma=ma, ten=ma, ho="khac")
        for ma in (*TRAM_DONG_GIAY, "kem", "bai", "thung")
    ])
    db.commit()


# ---- danh mục ----
def test_crud_and_duplicate():
    db, svc = _svc()
    cd = svc.create(dict(ma="IN", ten="In offset", nhom="print",
                         che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty",
                         first_unit_floor=350000))
    assert cd.id and cd.nhom == "print"
    with pytest.raises(CongDoanDuplicate):
        svc.create(dict(ma="IN", ten="khác", nhom="print", pricing_basis="per_sheet"))


def test_clone_khong_MA_TU_SINH_dung_hau_to_COPY():
    """`CongDoanService` không đặt `MA_TU_SINH` ⇒ nhánh `ma_ban_sao()` chạy, không phải nhánh
    xin mã tự sinh (khác `test_cong_viec_khoan.test_clone_...` — hai danh mục đi hai nhánh)."""
    db, svc = _svc()
    cd = svc.create(dict(ma="IN", ten="In offset", nhom="print",
                         che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty",
                         first_unit_floor=350000))
    ban_sao = svc.clone(cd.id)
    assert ban_sao.id != cd.id
    assert ban_sao.ma == "IN-COPY"
    assert ban_sao.ten == "In offset (bản sao)"
    assert ban_sao.nhom == "print" and ban_sao.pricing_basis == "per_finished_qty"

    # Nhân bản LẦN NỮA từ chính dòng gốc: "-COPY" đã bị chiếm, phải lệch sang "-COPY2".
    ban_sao_2 = svc.clone(cd.id)
    assert ban_sao_2.ma == "IN-COPY2"


def test_validate_basis():
    db, svc = _svc()
    with pytest.raises(CongDoanValidationError):          # E-CD-BASIS
        svc.create(dict(ma="X1", ten="x", nhom="finishing", che_do_tinh="theo_san_luong"))
    with pytest.raises(CongDoanValidationError):          # theo_gio đã gỡ → chế độ không hợp lệ
        svc.create(dict(ma="X2", ten="x", nhom="prepress", che_do_tinh="theo_gio"))


def test_nhom_other_hop_le_nhom_la_thi_khong():
    """Giai đoạn 'Dịch vụ khác' (`other`) phải KHỚP FE (rebuildCatalogConfigs NHOM_CD) — tạo được;
    nhóm ngoài danh sách vẫn bị loại."""
    db, svc = _svc()
    cd = svc.create(dict(ma="DV-KHAC", ten="Giao hàng", nhom="other",
                         pricing_basis="per_finished_qty"))
    assert cd.id and cd.nhom == "other"
    with pytest.raises(CongDoanValidationError):          # nhóm không có trong NHOM
        svc.create(dict(ma="ZZZ", ten="x", nhom="linh_tinh", pricing_basis="per_sheet"))


def test_nang_suat_luu_va_sua_duoc():
    """`nang_suat` phải nằm trong whitelist `ASSIGNABLE` — thiếu là field bị NUỐT IM LẶNG:
    form gửi lên, API trả 200, mà giá trị không vào DB và không ai biết."""
    db, svc = _svc()
    cd = svc.create(dict(ma="DAN", ten="Dán hộp", nhom="finishing",
                         pricing_basis="per_finished_qty", nang_suat=4000))
    assert float(cd.nang_suat) == 4000
    # `update` chạy full validation nên phải gửi cả bản ghi, không phải patch lẻ 1 field.
    sua = svc.update(cd.id, dict(ma="DAN", ten="Dán hộp", nhom="finishing",
                                 pricing_basis="per_finished_qty", nang_suat=5200))
    assert float(sua.nang_suat) == 5200
    # Không khai vẫn hợp lệ → NULL (routing để trống, không bịa 0).
    assert svc.create(dict(ma="GOI", ten="Đóng gói", nhom="finishing",
                           pricing_basis="per_finished_qty")).nang_suat is None


def test_cong_doan_khong_con_tang_dau_viec_dinh_muc():
    """Bảng "Đầu việc và định mức của tổ" GỠ 18/09/2026 (mg `0320`) — đúng bảng chủ xưởng khoanh
    đỏ. Công đoạn còn Phòng ban/Tổ phụ trách + Máy + tab VẬT TƯ; client cũ còn gửi khoá cũ thì
    schema bỏ qua im lặng, không nổ 422."""
    assert "dau_viec_dinh_muc" not in CongDoanIn.model_fields
    assert "dau_viec_dinh_muc" not in CongDoanRow.model_fields
    assert {"vat_tus", "department_ids", "may_lam_duoc"} <= set(CongDoanIn.model_fields)
    body = CongDoanIn(ma="BOI", ten="Bồi sóng", nhom="finishing",
                      pricing_basis="per_finished_qty",
                      dau_viec_dinh_muc=[{"piece_rate_id": 1, "so_nguoi_tieu_chuan": 3}])
    assert "dau_viec_dinh_muc" not in body.model_dump()


def test_go_to_khoi_viec_khong_con_bi_cong_doan_giu():
    """Công đoạn thôi giữ đầu việc (mg `0320`) nên gỡ tổ khỏi một công việc khoán KHÔNG còn bị
    công đoạn nào chặn. Mẻ đã ghi việc ấy giữ ảnh chụp riêng (băng "Danh mục đã đổi", `mat`)."""
    from app.repositories.cong_viec_khoan_repo import CongViecKhoanRepository
    from app.services.cong_viec_khoan_service import CongViecKhoanService

    db, svc = _svc()
    to_a = Department(name="Tổ A", code="PB921", la_san_xuat=True)
    to_b = Department(name="Tổ B", code="PB922", la_san_xuat=True)
    db.add_all([to_a, to_b])
    db.flush()
    chung = PieceRate(department_ids=[to_a.id, to_b.id], ten="Bế nổi", unit="tờ", unit_price=5)
    db.add(chung)
    db.commit()
    svc.create(dict(ma="BE-B", ten="Bế tổ B", nhom="finishing", department_ids=[to_b.id],
                    pricing_basis="per_finished_qty"))
    khoan = CongViecKhoanService(CongViecKhoanRepository(db))

    khoan.update(chung.id, dict(ten="Bế nổi", unit_price=5, department_ids=[to_a.id]))
    db.commit()
    assert db.get(PieceRate, chung.id).department_ids == [to_a.id]


def test_cong_doan_NHIEU_to_giu_thu_tu():
    """Công đoạn do tổ B + tổ A phụ trách (mg `0312`): lưu ĐÚNG thứ tự chọn (tổ đầu là mặc định
    của bước lệnh). `department_ids=None` giữ nguyên, `[]` gỡ hết, id lạ thì chặn."""
    db, svc = _svc()
    to_a = Department(name="Tổ A", code="PB931", la_san_xuat=True)
    to_b = Department(name="Tổ B", code="PB932", la_san_xuat=True)
    to_c = Department(name="Tổ C", code="PB933", la_san_xuat=True)
    db.add_all([to_a, to_b, to_c])
    db.commit()
    base = dict(ma="CD-NT", ten="Cán màng mờ", nhom="finishing", pricing_basis="per_finished_qty")

    cd = svc.create({**base, "department_ids": [to_b.id, to_a.id, to_b.id]})
    assert cd.department_ids == [to_b.id, to_a.id]
    assert cd.to_mac_dinh_id == to_b.id
    assert CongDoanRow.model_validate(cd).department_ids == [to_b.id, to_a.id]

    cd = svc.update(cd.id, {**base, "department_ids": None})
    assert cd.department_ids == [to_b.id, to_a.id], "vắng danh sách tổ = giữ nguyên"

    cd = svc.update(cd.id, {**base, "department_ids": [to_a.id, to_c.id]})
    db.expire_all()
    assert svc.get(cd.id).department_ids == [to_a.id, to_c.id]

    with pytest.raises(CongDoanValidationError, match="Không tìm thấy tổ"):
        svc.update(cd.id, {**base, "department_ids": [to_a.id, 987654]})
    db.rollback()

    cd = svc.update(cd.id, {**base, "department_ids": []})
    assert cd.department_ids == [] and cd.to_mac_dinh_id is None


def _to_va_rate(svc, db, *, ma_to: str, ma_rate: str):
    to = Department(name=f"Tổ {ma_to}", code=ma_to, la_san_xuat=True)
    db.add(to)
    db.flush()
    rate = PieceRate(department_ids=[to.id], ma=ma_rate,
                     ten=f"Việc {ma_rate}", unit="tờ", unit_price=100)
    db.add(rate)
    db.commit()
    return to, rate


def test_cong_doan_mang_nhieu_vat_tu_moi_mon_mot_cong_thuc():
    """Tab VẬT TƯ (spec 18/09/2026 §3.1, mg `0316`): công đoạn khai nhiều món, mỗi món một công
    thức định mức ra LƯỢNG theo ĐVT của món — mực theo số tờ, cồn theo cách khác, dù cùng kg."""
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, _rate = _to_va_rate(svc, db, ma_to="PB910", ma_rate="IN-01")
    muc = VatTuInAn(ma="MUC-X", ten="Mực X", don_vi_gia="kg", don_gia=180_000)
    con = VatTuInAn(ma="CON-X", ten="Cồn X", don_vi_gia="kg", don_gia=42_000)
    db.add_all([muc, con])
    db.commit()
    base = dict(ma="IN-X", ten="In offset X", nhom="print",
                department_ids=[to.id], pricing_basis="per_finished_qty")

    cd = svc.create({**base, "vat_tus": [
        {"vat_tu_id": muc.id, "cong_thuc_luong": "  sl_vao / 1000 "},
        {"vat_tu_id": con.id, "cong_thuc_luong": "sl_vao * 0.002"},
    ]})
    assert [v.vat_tu_id for v in cd.vat_tus] == [muc.id, con.id], "giữ đúng thứ tự người khai"
    assert [v.thu_tu for v in cd.vat_tus] == [0, 1]
    assert [v.cong_thuc_luong for v in cd.vat_tus] == ["sl_vao / 1000", "sl_vao * 0.002"]
    row = CongDoanRow.model_validate(cd)
    assert [(v.vat_tu_id, v.cong_thuc_luong) for v in row.vat_tus] == [
        (muc.id, "sl_vao / 1000"), (con.id, "sl_vao * 0.002")]

    # Sửa lại danh sách: thay trọn, không cộng dồn; ô trắng về None.
    cd = svc.update(cd.id, {**base, "vat_tus": [{"vat_tu_id": con.id, "cong_thuc_luong": "  "}]})
    assert [(v.vat_tu_id, v.cong_thuc_luong) for v in cd.vat_tus] == [(con.id, None)]


def test_chan_vat_tu_ngung_dung_va_vat_tu_chua_co_don_vi():
    """Hai ca im lặng nếu không chặn: vật tư tắt thì lúc bung nó rơi mất, vật tư chưa có ĐVT thì
    không có đích để quy đổi — cả hai đều khiến người khai không hiểu vì sao dòng không hiện."""
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, _rate = _to_va_rate(svc, db, ma_to="PB911", ma_rate="GC-01")
    tat = VatTuInAn(ma="VT-TAT", ten="Đã ngừng", don_vi_gia="kg", don_gia=1, active=False)
    trong = VatTuInAn(ma="VT-TRONG", ten="Chưa có ĐVT", don_vi_gia=None, don_gia=1)
    db.add_all([tat, trong])
    db.commit()
    base = dict(ma="GC-X", ten="Gia công X", nhom="finishing",
                department_ids=[to.id], pricing_basis="per_finished_qty")

    with pytest.raises(CongDoanValidationError, match="đã ngừng dùng"):
        svc.create({**base, "vat_tus": [{"vat_tu_id": tat.id}]})
    with pytest.raises(CongDoanValidationError, match="đơn vị tính"):
        svc.create({**base, "ma": "GC-X2", "vat_tus": [{"vat_tu_id": trong.id}]})
    with pytest.raises(CongDoanValidationError, match="trùng"):
        svc.create({**base, "ma": "GC-X3",
                    "vat_tus": [{"vat_tu_id": trong.id}, {"vat_tu_id": trong.id}]})


def test_vat_tu_ngung_dung_van_sua_duoc_cong_doan_dang_giu_no():
    """Chặn GÁN MỚI, không chặn GIỮ NGUYÊN (luật đã chốt cho lương 27/07).

    Công đoạn khai vật tư X, sau đó kho tắt X ⇒ công đoạn vẫn phải sửa được (đổi cái tên), không thì
    không có đường nào gỡ ngoài vào DB bật lại X."""
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, _rate = _to_va_rate(svc, db, ma_to="PB912", ma_rate="GC-02")
    vt = VatTuInAn(ma="VT-SONG", ten="Keo", don_vi_gia="kg", don_gia=1)
    db.add(vt)
    db.commit()
    base = dict(ma="GC-Y", ten="Gia công Y", nhom="finishing", department_ids=[to.id],
                pricing_basis="per_finished_qty")
    cd = svc.create({**base, "vat_tus": [{"vat_tu_id": vt.id}]})

    vt.active = False                      # kho ngừng dùng vật tư SAU khi công đoạn đã khai nó
    db.commit()

    sua = svc.update(cd.id, {**base, "ten": "Gia công Y (đổi tên)",
                             "vat_tus": [{"vat_tu_id": vt.id}]})
    assert sua.ten == "Gia công Y (đổi tên)"
    assert [v.vat_tu_id for v in sua.vat_tus] == [vt.id]

    # Nhưng GÁN THÊM một vật tư đã ngừng thì vẫn phải chặn.
    khac = VatTuInAn(ma="VT-TAT2", ten="Mực cũ", don_vi_gia="kg", don_gia=1, active=False)
    db.add(khac)
    db.commit()
    with pytest.raises(CongDoanValidationError, match="đã ngừng dùng"):
        svc.update(cd.id, {**base, "vat_tus": [{"vat_tu_id": vt.id}, {"vat_tu_id": khac.id}]})


def test_cong_doan_trung_tinh_khong_mang_loai_thuc_hien_hoac_may_mac_dinh():
    """Máy/Tổ là quyết định của bước LSX, không phải thuộc tính danh mục Công đoạn."""
    assert "loai_thuc_hien" not in CongDoanIn.model_fields
    assert "may_id" not in CongDoanIn.model_fields
    assert "loai_thuc_hien" not in CongDoanRow.model_fields
    assert "may_id" not in CongDoanRow.model_fields
    assert not hasattr(CongDoan, "loai_thuc_hien")
    assert not hasattr(CongDoan, "may_id")


def test_don_vi_vao_ra_chi_chay_MOT_CHIEU():
    """Dòng giấy: tờ nguyên → tờ in → tờ thành phẩm. Cặp đi ngược/nhảy cóc phải bị chặn."""
    db, svc = _svc()
    base = dict(nhom="finishing", pricing_basis="per_finished_qty")
    # Không khai → TRỐNG = bước không nằm trên dòng giấy (KHÔNG còn đoán theo tên).
    assert svc.create(dict(ma="X1", ten="Bế thành phẩm", **base)).don_vi_vao is None
    # Khai đúng chiều thì nhận.
    cd = svc.create(dict(ma="X2", ten="Bế", don_vi_vao="to", don_vi_ra="cai", **base))
    assert (cd.don_vi_vao, cd.don_vi_ra) == ("to", "cai")
    assert svc.create(dict(ma="X3", ten="Xả giấy", don_vi_vao="to_nguyen", don_vi_ra="to",
                           **base)).don_vi_ra == "to"
    # Ngược dòng: con không quay lại thành tờ.
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X4", ten="Sai", don_vi_vao="cai", don_vi_ra="to", **base))
    # Nhảy cóc: tờ nguyên không thành con một phát (thiếu bước xả + bế ở giữa).
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X5", ten="Sai", don_vi_vao="to_nguyen", don_vi_ra="cai", **base))
    # Mã NGOÀI 5 chặng → chặn, dù có thật trong danh mục Đơn vị (kho vẫn đếm bằng `kem`).
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X6kem", ten="Sai", don_vi_vao="kem", don_vi_ra="kem", **base))
    # Khai một nửa thì chặn — trống là trống cả hai.
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X7", ten="Sai", don_vi_vao="to", don_vi_ra="", **base))
    # Chế bản: để TRỐNG vì không chạm giấy. Cả engine tính giá lẫn lệnh sản xuất loại nó khỏi dòng
    # giấy; SL của nó do người lập lệnh tự khai ở bước (`lsx_service.tu_khai_don_vi`).
    cb = svc.create(dict(ma="X8", ten="Ghi kẽm CTP", nhom="prepress", pricing_basis="per_other"))
    assert (cb.don_vi_vao, cb.don_vi_ra) == (None, None)


def test_don_vi_ngoai_dong_giay_de_trong_ca_hai():
    """Bước KHÔNG chạm giấy BỎ TRỐNG cả hai ô đơn vị (06/09/2026).

    Giữa 11/08 và 06/09 nó khai đơn vị THẬT (`bai → kem`) và cờ `don_vi_do.tram_dong_giay` trả lời
    hộ câu "có nằm trên dòng giấy không". Cờ ấy gỡ rồi: ô đơn vị của công đoạn là menu đóng 5
    chặng, nên khai `kem` là chặn — đơn vị + số của bước do người lập lệnh tự khai ở bước.
    """
    db, svc = _svc()
    base = dict(nhom="prepress", pricing_basis="per_other")
    cd = svc.create(dict(ma="CTP", ten="Ghi kẽm CTP", **base))
    assert (cd.don_vi_vao, cd.don_vi_ra) == (None, None)
    # Mã ngoài 5 chặng: chặn cả hai chiều, dù `kem`/`bai` có thật trong danh mục Đơn vị.
    for vao, ra in (("bai", "kem"), ("kem", "bai")):
        with pytest.raises(CongDoanValidationError, match="E-CD-DONVI"):
            svc.create(dict(ma=f"X-{vao}-{ra}", ten="x", don_vi_vao=vao, don_vi_ra=ra, **base))
    # Một chân trong dòng giấy một chân ngoài (`cai → thung`, đóng gói) cũng chặn: hệ số của cặp đó
    # là sức chứa từng đơn, chưa có chỗ khai → cho qua là engine ăn hệ số 1 trong im lặng.
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="DG", ten="Đóng thùng", don_vi_vao="cai", don_vi_ra="thung",
                        nhom="finishing", pricing_basis="per_carton"))


def test_print_spoilage_forced_zero():
    db, svc = _svc()
    cd = svc.create(dict(ma="IN2", ten="In", nhom="print", pricing_basis="per_sheet", spoilage_pct=5))
    assert float(cd.spoilage_pct) == 0        # W-CD-PRINT-SPOIL → ép 0


# ---- routing_engine ----
def test_basis_qty_table():
    ctx = dict(so_to_in_gross=1000, so_mat=2, dt_to_in_cm2=5000, dt_thanh_pham_cm2=100,
               so_luong_thanh_pham=44000, so_trang=200, so_cuon=500, so_vi_tri=2,
               so_bao=88, so_thung=12)
    assert re.basis_qty("per_sheet", ctx) == 1000
    assert re.basis_qty("per_finished_qty", ctx) == 44000
    assert re.basis_qty("per_finished_area", ctx) == 100 * 44000
    assert re.basis_qty("per_book_page", ctx) == 200 * 500
    assert re.basis_qty("per_book_page_q4", ctx) == 200 * 500 / 4
    assert re.basis_qty("per_position", ctx) == 2 * 44000
    assert re.basis_qty("per_bag", ctx) == 88
    assert re.basis_qty("per_carton", ctx) == 12
    assert re.basis_qty("per_area_sides", ctx) == 5000 * 2 * 1000
    assert re.basis_qty("per_sheet_area", ctx) == 5000 * 1000
    assert re.basis_qty("per_other", ctx) == 1.0


def test_step_cost_floor_and_pass():
    # Sàn 350.000 khi lượng nhỏ (per_finished_qty × run_rate < sàn)
    cd_in = dict(che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty",
                 run_rate=200000, first_unit_floor=350000)
    r = re.compute_step_cost(cd_in, dict(so_luong_thanh_pham=1))
    assert r["total"] == 350000
    # BẾ per_sheet: 333 tờ × 180 + khuôn 200k
    cd_be = dict(che_do_tinh="theo_san_luong", pricing_basis="per_sheet", run_rate=180)
    r2 = re.compute_step_cost(cd_be, dict(so_to_in_gross=333), tooling_one_time=200000)
    assert r2["run_cost"] == round(333 * 180, 2)
    assert r2["tooling_cost"] == 200000
    # tái bản → bỏ tiền khuôn
    r3 = re.compute_step_cost(cd_be, dict(so_to_in_gross=333), reuse_tooling=True, tooling_one_time=200000)
    assert r3["tooling_cost"] == 0


def test_cascade_waste_backward():
    steps = [dict(nhom="print", spoilage_pct=5), dict(nhom="finishing", spoilage_pct=2),
             dict(nhom="finishing", spoilage_pct=3)]
    out = re.cascade_waste_backward(steps, 1000)
    assert out[-1]["output_qty"] == 1000
    # bước cuối 3%: hao đo trên số RA ⇒ input = 1000 × 1,03 = 1030 (KHÔNG phải 1000/0,97 = 1030,93)
    assert abs(out[-1]["input_qty"] - 1030.0) < 0.01
    # bước giữa 2% ăn tiếp trên số ra của nó = 1030 ⇒ 1050,6
    assert abs(out[1]["input_qty"] - 1050.6) < 0.01
    # bước in: spoilage ép 0 → input == output
    assert out[0]["input_qty"] == out[0]["output_qty"]


def test_kem_line():
    # sheetwise 4/4, 1 form → 8 kẽm
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000)["so_kem"] == 8
    # tự trở → max(4,4)=4 kẽm
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=True,
                               don_gia_kem=100000)["so_kem"] == 4
    # digital → 0 kẽm
    assert re.compute_kem_line(so_forms=2, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000, is_digital=True)["so_kem"] == 0
    # tiền kẽm = 8 × 100k
    assert re.compute_kem_line(so_forms=1, so_kem_truoc=4, so_kem_sau=4, tu_tro=False,
                               don_gia_kem=100000)["tien_kem"] == 800000


def test_so_to_in_gross():
    # net 228 + canh máy 100/màu × ... (ở đây 1 lần) + 2% → ceil
    g = re.so_to_in_gross(228, so_mau=1, bu_hao_canh_may_per_mau=100, bu_hao_chay_pct=2)
    assert g == pytest.approx(335, abs=1)   # (228+100)*1.02 = 334.56 → 335


def test_dem_theo_nhom_nuoi_tab_loc():
    """Số trên tab lọc màn Công đoạn do MÁY CHỦ đếm — không lọc theo `nhom` (tab nào cũng
    phải có số của nó), nhưng CÓ đi theo ô tìm và cờ `active`."""
    db, svc = _svc()
    svc.create(dict(ma="IN1", ten="In offset", nhom="print", pricing_basis="per_sheet"))
    svc.create(dict(ma="IN2", ten="In lụa", nhom="print", pricing_basis="per_sheet"))
    svc.create(dict(ma="BE1", ten="Bế hộp", nhom="finishing", pricing_basis="per_sheet"))
    ngung = svc.create(dict(ma="CU1", ten="In cũ", nhom="print", pricing_basis="per_sheet"))
    svc.update(ngung.id, dict(ma="CU1", ten="In cũ", nhom="print",
                              pricing_basis="per_sheet", active=False))

    assert svc.dem_theo_nhom() == {"print": 3, "finishing": 1}
    assert svc.dem_theo_nhom(active=True) == {"print": 2, "finishing": 1}
    assert svc.dem_theo_nhom(q="bế") == {"finishing": 1}


def test_cong_thuc_san_luong_da_go():
    """GỠ 18/09/2026 (mg `0324`): công đoạn thôi khai công thức + đơn vị sản lượng ra.

    Số của bước ngoài dòng giấy (ghi kẽm) nay do người lập lệnh tự khai ở bước. Payload cũ còn
    gửi hai khoá đó (file Excel cũ, client chưa tải lại) thì bị bỏ qua, không lỗi, không ghi.
    """
    from app.models.cong_doan import CongDoan
    from app.schemas.cong_doan import CongDoanIn, CongDoanRow

    for cot in ("cong_thuc_san_luong", "don_vi_san_luong", "he_so_ngoai_dong"):
        assert cot not in CongDoan.__table__.c
        assert cot not in CongDoanIn.model_fields
        assert cot not in CongDoanRow.model_fields
    db, svc = _svc()
    cd = svc.create(dict(ma="CTP2", ten="Ghi kẽm CTP", nhom="prepress", pricing_basis="per_sheet",
                         cong_thuc_san_luong="so_kem", don_vi_san_luong="kem"))
    assert (cd.don_vi_vao, cd.don_vi_ra) == (None, None)


def test_cong_thuc_vat_tu_sai_cu_phap_bi_chan_goi_ten_mon():
    """Câu lỗi phải GỌI TÊN món vật tư — tab nhiều dòng, không nói tên thì người khai phải dò."""
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, _rate = _to_va_rate(svc, db, ma_to="CTG2", ma_rate="XENG2")
    muc = VatTuInAn(ma="MUC-SAI", ten="Mực sai", don_vi_gia="kg", don_gia=1)
    db.add(muc)
    db.commit()
    with pytest.raises(CongDoanValidationError, match="Mực sai"):
        svc.create(dict(ma="CD-CTG2", ten="Xén 2", nhom="finishing", department_ids=[to.id],
                        pricing_basis="per_finished_qty",
                        vat_tus=[{"vat_tu_id": muc.id, "cong_thuc_luong": "sl_vao * *"}]))
