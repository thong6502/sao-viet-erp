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
    """Danh mục Đơn vị tối thiểu — đơn vị vào/ra của công đoạn nay TRỎ vào bảng này (không còn
    danh sách cứng trong code), nên DB trắng là không khai được đơn vị nào.

    5 mã đầu mang CỜ TRẠM (dòng giấy), 3 mã sau không — đủ để thử cả hai nhánh validate.
    """
    from app.models.don_vi_do import TRAM_DONG_GIAY, DonViDo

    db.add_all([
        DonViDo(ma=ma, ten=ma, ho="khac", tram_dong_giay=ma if ma in TRAM_DONG_GIAY else None)
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


def test_cong_doan_to_luu_dinh_muc_theo_dau_viec():
    db, svc = _svc()
    to = Department(name="Tổ Bồi", code="PB900", la_san_xuat=True)
    db.add(to)
    db.flush()
    rate = PieceRate(group_name="Tổ Bồi", department_id=to.id, code="BOI-01",
                     name="Bồi sóng", unit="tờ", unit_price=200)
    db.add(rate)
    db.commit()

    cd = svc.create(dict(
        ma="BOI", ten="Bồi sóng", nhom="finishing",
        department_id=to.id, pricing_basis="per_finished_qty",
        dau_viec_dinh_muc=[dict(
            piece_rate_id=rate.id, nang_suat_nguoi_gio=500,
            so_nguoi_tieu_chuan=3, so_nguoi_toi_da=5,
        )],
    ))

    assert len(cd.dau_viec_dinh_muc) == 1
    dm = cd.dau_viec_dinh_muc[0]
    assert dm.piece_rate_id == rate.id
    assert float(dm.nang_suat_nguoi_gio) == 500
    assert (dm.so_nguoi_tieu_chuan, dm.so_nguoi_toi_da) == (3, 5)


def test_dinh_muc_luu_dai_nang_suat_don_vi_va_ba_moc_nhan_luc():
    """Dải năng suất + đơn vị khai báo + ba mốc nhân lực lưu đúng, và khai ngược thì bị chặn."""
    db, svc = _svc()
    to = Department(name="Tổ Dán", code="PB903", la_san_xuat=True)
    db.add(to)
    db.flush()
    rate = PieceRate(group_name="Tổ Dán", department_id=to.id, name="Dán hộp",
                     unit="hộp", unit_price=80)
    db.add(rate)
    db.commit()
    base = dict(ma="DAN", ten="Dán hộp", nhom="finishing",
                department_id=to.id, pricing_basis="per_finished_qty")

    cd = svc.create({**base, "dau_viec_dinh_muc": [dict(
        piece_rate_id=rate.id, nang_suat_nguoi_gio=250,
        nang_suat_nguoi_gio_min=200, nang_suat_nguoi_gio_max=320,
        don_vi_nang_suat="hop_gio",
        so_nguoi_toi_thieu=2, so_nguoi_tieu_chuan=4, so_nguoi_toi_da=8,
    )]})
    dm = cd.dau_viec_dinh_muc[0]
    assert (float(dm.nang_suat_nguoi_gio_min), float(dm.nang_suat_nguoi_gio_max)) == (200, 320)
    assert dm.don_vi_nang_suat == "hop_gio"
    assert (dm.so_nguoi_toi_thieu, dm.so_nguoi_tieu_chuan, dm.so_nguoi_toi_da) == (2, 4, 8)

    # Tối thiểu > trung bình ⇒ "nhanh nhất" hoá ra chậm hơn "chậm nhất" — chặn ngay ở service.
    with pytest.raises(CongDoanValidationError, match="tối thiểu"):
        svc.create({**base, "ma": "DAN2", "dau_viec_dinh_muc": [dict(
            piece_rate_id=rate.id, nang_suat_nguoi_gio=250, nang_suat_nguoi_gio_min=400,
            so_nguoi_tieu_chuan=4, so_nguoi_toi_da=8,
        )]})
    # Ba mốc nhân lực phải xếp đúng thứ tự.
    with pytest.raises(CongDoanValidationError, match="1 ≤ tối thiểu"):
        svc.create({**base, "ma": "DAN3", "dau_viec_dinh_muc": [dict(
            piece_rate_id=rate.id, nang_suat_nguoi_gio=250,
            so_nguoi_toi_thieu=5, so_nguoi_tieu_chuan=4, so_nguoi_toi_da=8,
        )]})


def test_luu_lai_dinh_muc_cung_dau_viec_khong_dung_unique():
    """Sửa số rồi lưu lại ĐÚNG đầu việc cũ — trước đây 500 `duplicate key uq_cd_dau_viec_rate`.

    Bẫy SQLAlchemy: trong một flush, INSERT bay trước DELETE cho cùng bảng, nên xoá-rồi-thêm
    dòng có cùng `(cong_doan_id, piece_rate_id)` là đụng UNIQUE. Repo phải flush ở giữa.
    """
    db, svc = _svc()
    to = Department(name="Tổ Cán màng", code="PB904", la_san_xuat=True)
    db.add(to)
    db.flush()
    rate = PieceRate(group_name="Tổ Cán màng", department_id=to.id, name="Cán mờ",
                     unit="m²", unit_price=150)
    db.add(rate)
    db.commit()
    base = dict(ma="CAN-M", ten="Cán màng mờ", nhom="finishing",
                department_id=to.id, pricing_basis="per_finished_qty")
    cd = svc.create({**base, "dau_viec_dinh_muc": [dict(
        piece_rate_id=rate.id, nang_suat_nguoi_gio=3000,
        so_nguoi_tieu_chuan=1, so_nguoi_toi_da=3,
    )]})

    cd = svc.update(cd.id, {**base, "dau_viec_dinh_muc": [dict(
        piece_rate_id=rate.id, nang_suat_nguoi_gio=3000,
        nang_suat_nguoi_gio_min=2000, nang_suat_nguoi_gio_max=5000,
        so_nguoi_tieu_chuan=1, so_nguoi_toi_da=3,
    )]})
    assert len(cd.dau_viec_dinh_muc) == 1
    dm = cd.dau_viec_dinh_muc[0]
    assert (float(dm.nang_suat_nguoi_gio_min), float(dm.nang_suat_nguoi_gio_max)) == (2000, 5000)


def test_dinh_muc_to_chan_dau_viec_khac_to_va_cho_nhieu_dau_viec_khong_can_mac_dinh():
    db, svc = _svc()
    to_a = Department(name="Tổ A", code="PB901", la_san_xuat=True)
    to_b = Department(name="Tổ B", code="PB902", la_san_xuat=True)
    db.add_all([to_a, to_b])
    db.flush()
    rates = [
        PieceRate(group_name="A", department_id=to_a.id, name="A1", unit="tờ", unit_price=1),
        PieceRate(group_name="A", department_id=to_a.id, name="A2", unit="tờ", unit_price=1),
        PieceRate(group_name="B", department_id=to_b.id, name="B1", unit="tờ", unit_price=1),
    ]
    db.add_all(rates)
    db.commit()
    base = dict(ma="TO-A", ten="Việc A", nhom="finishing",
                department_id=to_a.id, pricing_basis="per_finished_qty")

    with pytest.raises(CongDoanValidationError, match="đúng tổ"):
        svc.create({**base, "dau_viec_dinh_muc": [dict(
            piece_rate_id=rates[2].id, nang_suat_nguoi_gio=100,
            so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2,
        )]})

    # Hai đầu việc cùng tổ: KHÔNG còn phải chỉ định cái nào "mặc định" (cột đó gỡ 12/08/2026,
    # mg 0190). Lưu được trọn vẹn; việc chọn dùng cái nào để dành cho lúc lập lệnh.
    cd = svc.create({**base, "ma": "TO-A2", "dau_viec_dinh_muc": [
        dict(piece_rate_id=rates[0].id, nang_suat_nguoi_gio=100,
             so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2),
        dict(piece_rate_id=rates[1].id, nang_suat_nguoi_gio=120,
             so_nguoi_tieu_chuan=1, so_nguoi_toi_da=3),
    ]})
    assert len(cd.dau_viec_dinh_muc) == 2
    assert not hasattr(cd.dau_viec_dinh_muc[0], "is_default"), "cờ mặc định phải hết hẳn"


def _to_va_rate(svc, db, *, ma_to: str, ma_rate: str):
    to = Department(name=f"Tổ {ma_to}", code=ma_to, la_san_xuat=True)
    db.add(to)
    db.flush()
    rate = PieceRate(group_name=ma_to, department_id=to.id, code=ma_rate,
                     name=f"Việc {ma_rate}", unit="tờ", unit_price=100)
    db.add(rate)
    db.commit()
    return to, rate


def test_dau_viec_mang_danh_sach_vat_tu():
    """Nền BOM (mg 0191): đầu việc khai sẵn nó tiêu thụ vật tư nào — DANH SÁCH, không có số lượng.

    Số lượng suy lúc bung ở bước lệnh theo quy cách; một con số khai ở danh mục là số chết.
    """
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, rate = _to_va_rate(svc, db, ma_to="PB910", ma_rate="IN-01")
    muc = VatTuInAn(ma="MUC-X", ten="Mực X", don_vi_gia="kg", don_gia=180_000)
    con = VatTuInAn(ma="CON-X", ten="Cồn X", don_vi_gia="kg", don_gia=42_000)
    db.add_all([muc, con])
    db.commit()

    cd = svc.create(dict(
        ma="IN-X", ten="In offset X", nhom="print",
        department_id=to.id, pricing_basis="per_finished_qty",
        dau_viec_dinh_muc=[dict(
            piece_rate_id=rate.id, nang_suat_nguoi_gio=5000,
            so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2,
            vat_tu_ids=[muc.id, con.id],
        )],
    ))
    dv = cd.dau_viec_dinh_muc[0]
    assert dv.vat_tu_ids == [muc.id, con.id], "giữ đúng thứ tự người khai"
    assert [v.thu_tu for v in dv.vat_tus] == [0, 1]

    # Sửa lại danh sách: thay trọn, không cộng dồn.
    cd = svc.update(cd.id, dict(
        ma="IN-X", ten="In offset X", nhom="print",
        department_id=to.id, pricing_basis="per_finished_qty",
        dau_viec_dinh_muc=[dict(
            piece_rate_id=rate.id, nang_suat_nguoi_gio=5000,
            so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2, vat_tu_ids=[con.id],
        )],
    ))
    assert cd.dau_viec_dinh_muc[0].vat_tu_ids == [con.id]


def test_chan_vat_tu_ngung_dung_va_vat_tu_chua_co_don_vi():
    """Hai ca im lặng nếu không chặn: vật tư tắt thì lúc bung nó rơi mất, vật tư chưa có ĐVT thì
    không có đích để quy đổi — cả hai đều khiến người khai không hiểu vì sao dòng không hiện."""
    from app.models.vat_lieu_kho import VatTuInAn

    db, svc = _svc()
    to, rate = _to_va_rate(svc, db, ma_to="PB911", ma_rate="GC-01")
    tat = VatTuInAn(ma="VT-TAT", ten="Đã ngừng", don_vi_gia="kg", don_gia=1, active=False)
    trong = VatTuInAn(ma="VT-TRONG", ten="Chưa có ĐVT", don_vi_gia=None, don_gia=1)
    db.add_all([tat, trong])
    db.commit()
    base = dict(ma="GC-X", ten="Gia công X", nhom="finishing",
                department_id=to.id, pricing_basis="per_finished_qty")
    dm = dict(piece_rate_id=rate.id, nang_suat_nguoi_gio=100,
              so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2)

    with pytest.raises(CongDoanValidationError, match="ngừng sử dụng"):
        svc.create({**base, "dau_viec_dinh_muc": [{**dm, "vat_tu_ids": [tat.id]}]})
    with pytest.raises(CongDoanValidationError, match="đơn vị tính"):
        svc.create({**base, "ma": "GC-X2", "dau_viec_dinh_muc": [{**dm, "vat_tu_ids": [trong.id]}]})
    with pytest.raises(CongDoanValidationError, match="trùng"):
        svc.create({**base, "ma": "GC-X3",
                    "dau_viec_dinh_muc": [{**dm, "vat_tu_ids": [trong.id, trong.id]}]})


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
    # Mã KHÔNG có trong danh mục Đơn vị → chặn, dù trông giống mã thật.
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X6met", ten="Sai", don_vi_vao="met", don_vi_ra="met", **base))
    # Khai một nửa thì chặn — trống là trống cả hai.
    with pytest.raises(CongDoanValidationError):
        svc.create(dict(ma="X7", ten="Sai", don_vi_vao="to", don_vi_ra="", **base))
    # Chế bản: để TRỐNG vì không chạm giấy. Engine tính giá loại nó khỏi dòng giấy; lệnh sản xuất
    # tự suy ra kẽm từ `nhom` (xem `lsx_service._don_vi_theo_buoc`).
    cb = svc.create(dict(ma="X8", ten="Ghi kẽm CTP", nhom="prepress", pricing_basis="per_other"))
    assert (cb.don_vi_vao, cb.don_vi_ra) == (None, None)


def test_don_vi_ngoai_dong_giay_khai_duoc():
    """Bước KHÔNG chạm giấy nay khai được đơn vị THẬT (`bai → kem`) thay vì phải để trống.

    Đây là điểm mở của 11/08/2026: trước đó service chỉ nhận 5 mã dòng giấy nên ghi kẽm buộc phải
    bỏ trống đơn vị, kéo theo không khớp được tốc độ máy CTP (kẽm/giờ) lẫn định mức vật tư.
    """
    db, svc = _svc()
    base = dict(nhom="prepress", pricing_basis="per_other")
    cd = svc.create(dict(ma="CTP", ten="Ghi kẽm CTP", don_vi_vao="bai", don_vi_ra="kem", **base))
    assert (cd.don_vi_vao, cd.don_vi_ra) == ("bai", "kem")
    # Ngoài dòng giấy thì KHÔNG có chiều nào để mà sai — cặp ngược cũng nhận.
    assert svc.create(dict(ma="CTP2", ten="x", don_vi_vao="kem", don_vi_ra="bai",
                           **base)).don_vi_ra == "bai"
    # Nhưng một chân trong dòng giấy một chân ngoài (`cai → thung`, đóng gói) thì CHẶN: hệ số của
    # cặp đó là sức chứa từng đơn, chưa có chỗ khai → cho qua là engine ăn hệ số 1 trong im lặng.
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
    # bước cuối 3%: input = 1000/0.97 ≈ 1030.93
    assert abs(out[-1]["input_qty"] - 1030.928) < 0.01
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
