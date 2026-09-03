"""Báo sự cố tại tổ — KHÔNG đẻ bảng sự cố mới, dùng `ky_thuat_yeu_cau_sua` ("Báo máy hỏng")
cộng hai cột neo về sản xuất. Hai nhánh:

  · "Dừng sản xuất": MỘT giao dịch — ghi yêu cầu + tạm dừng công việc + đóng phiên máy.
  · "Vẫn chạy": chỉ ghi yêu cầu; đồng hồ máy không dừng.

Và luật quan trọng nhất: tạo yêu cầu HỎNG thì công việc KHÔNG được tạm dừng nửa vời.

SỬA SO VỚI BẢN NHÁP TRONG BRIEF (31/08/2026) — bốn chỗ bản nháp giả định sai, đã đọc code thật:

  · `ChoTiepNhanOut` chỉ có khoá `total`, KHÔNG có `so_luong`
    (`app/schemas/ky_thuat_may.py`), đường thật là `GET /api/ky-thuat-may/yeu-cau/cho-xu-ly`.
  · `muc_do` hợp lệ là `nhe|trung_binh|nghiem_trong` (`models.ky_thuat_may.MUC_DO`) — bản nháp
    dùng "cao"/"thap" vốn bị `_validate_yeu_cau` chặn, nên test sẽ đỏ vì lý do KHÔNG phải điều
    nó muốn chứng minh.
  · Test "dừng sản xuất bắt buộc lý do" trong bản nháp gửi `bo_phan_hong=""` nên rơi vào cửa
    "chưa ghi chỗ hỏng" trước, không bao giờ chạm tới cửa lý do. Tách làm hai bài.
  · Admin (vai Giám đốc) KHÔNG có bit `san_xuat:can_assign_work` (`seed._full` không bật cờ đó),
    nên bài API không khẳng định thẳng 200/403 mà so ĐƯỜNG DÂY QUYỀN với `tam-dung` — cùng khuôn
    với `tests/test_san_xuat_doi_may.py::test_api_doi_may_gate_quyen`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.models.department import Department
from app.models.employee import Employee
from app.models.ky_thuat_may import (
    MUC_DO_NGHIEM_TRONG,
    MUC_DO_NHE,
    TT_YC_CHO_TIEP_NHAN,
    YeuCauSuaChua,
)
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat import BUOC_MAY, CV_DANG_CHAY, CV_TAM_DUNG, SanXuatCongViec
from app.models.san_xuat_thuc_thi import PHIEN_TAM_DUNG, SanXuatPhienChay
from app.services.san_xuat import su_co, thuc_thi

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)


# --- Dàn cảnh dùng chung (cùng khuôn tests/test_san_xuat_doi_may.py) -------------------------
def _to_khoan(db, admin, ma="TO-SC") -> Department:
    """Tổ sản xuất bật lương khoán, admin làm tổ trưởng — để qua GATE §6 khi gọi service."""
    d = Department(
        name=f"Tổ Sự Cố {ma}", code=ma, la_san_xuat=True,
        has_piece_work=True, head_user_id=admin.id,
    )
    db.add(d)
    db.flush()
    return d


def _emp(db, dept, ma, ten="Thợ") -> Employee:
    e = Employee(code=ma, full_name=ten, department_id=dept.id)
    db.add(e)
    db.flush()
    return e


def _may(db, ma) -> MayThietBi:
    m = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="press_offset_sheet")
    db.add(m)
    db.flush()
    return m


def _mot_cong_viec(
    db, orders, lsx_svc, admin, customer, *, ma: str, may_id: int | None,
    chay: bool = True, so_nguoi: int = 1,
) -> SanXuatCongViec:
    """Một tổ khoán + một công việc gắn máy THẬT. `chay=False` ⇒ để nguyên trạng thái phát hành."""
    to = _to_khoan(db, admin, ma=ma)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv = (
        db.query(SanXuatCongViec)
        .filter_by(department_id=to.id)
        .order_by(SanXuatCongViec.id)
        .first()
    )
    cv.loai_buoc = BUOC_MAY
    cv.du_kien_bat_dau = None
    cv.du_kien_ket_thuc = None
    cv.may_id = may_id
    db.commit()
    for i in range(so_nguoi):
        e = _emp(db, to, f"NV-{ma}-{i}")
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    if chay:
        thuc_thi.bat_dau(
            db, user=admin, cong_viec_id=cv.id,
            ly_do_so_nguoi="Dàn cảnh test — số người khác định mức chốt lúc phát hành",
        )
    db.refresh(cv)
    return cv


@pytest.fixture
def to_truong(admin):
    """`_to_khoan` gán admin.id làm `head_user_id` của tổ dàn cảnh — admin CHÍNH là tổ trưởng."""
    return admin


@pytest.fixture
def may_sc(db) -> MayThietBi:
    return _may(db, "MAY-SC-1")


@pytest.fixture
def cv_dang_chay(db, orders, lsx_svc, admin, customer, may_sc) -> SanXuatCongViec:
    return _mot_cong_viec(db, orders, lsx_svc, admin, customer, ma="TO-SC", may_id=may_sc.id)


@pytest.fixture
def cv_chua_bat_dau(db, orders, lsx_svc, admin, customer, may_sc) -> SanXuatCongViec:
    return _mot_cong_viec(
        db, orders, lsx_svc, admin, customer, ma="TO-SC-CHUA", may_id=may_sc.id, chay=False,
    )


@pytest.fixture
def cv_khong_may(db, orders, lsx_svc, admin, customer) -> SanXuatCongViec:
    return _mot_cong_viec(db, orders, lsx_svc, admin, customer, ma="TO-SC-NOMAY", may_id=None)


# --- Hai nhánh ------------------------------------------------------------------------------
def test_dung_san_xuat_tam_dung_va_dong_phien(db, cv_dang_chay, to_truong):
    cv = cv_dang_chay
    kq = su_co.bao_su_co(
        db, user=to_truong, cong_viec_id=cv.id, bo_phan_hong="cụm cấp giấy",
        mo_ta="kẹt giấy liên tục", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
    )

    yc = db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv.id).one()
    assert yc.trang_thai == TT_YC_CHO_TIEP_NHAN
    assert yc.may_dung is True
    assert yc.may_id == cv.may_id
    assert yc.lsx_id == cv.lsx_id
    assert yc.nguoi_bao_id == to_truong.id          # người báo = tài khoản đang đăng nhập
    assert cv.trang_thai == CV_TAM_DUNG
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).count() == 0

    # Phiên vừa đóng phải là TẠM DỪNG thật (máy hỏng thì việc dừng thật) — KHÔNG phải `doi_may`;
    # và lý do phải dẫn được về mã yêu cầu để người đọc lịch sử phiên lần ra hồ sơ sửa chữa.
    phien = (
        db.query(SanXuatPhienChay)
        .filter_by(cong_viec_id=cv.id)
        .order_by(SanXuatPhienChay.so_thu_tu.desc())
        .first()
    )
    assert phien.loai_dong == PHIEN_TAM_DUNG
    assert yc.ma in (phien.ly_do or "")

    assert kq["yeu_cau_id"] == yc.id and kq["yeu_cau_ma"] == yc.ma
    assert kq["trang_thai"] == CV_TAM_DUNG


def test_van_chay_khong_dung_dong_ho(db, cv_dang_chay, to_truong):
    cv = cv_dang_chay
    su_co.bao_su_co(
        db, user=to_truong, cong_viec_id=cv.id, bo_phan_hong="đèn báo",
        mo_ta="chập chờn", muc_do=MUC_DO_NHE, dung_san_xuat=False,
    )

    yc = db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv.id).one()
    assert yc.may_dung is False
    assert cv.trang_thai == CV_DANG_CHAY
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).count() == 1


# --- Bốn cửa chặn ---------------------------------------------------------------------------
def test_dung_san_xuat_bat_buoc_ly_do(db, cv_dang_chay, to_truong):
    """Bỏ trống MÔ TẢ khi chọn "Dừng sản xuất" — đây là mốc mất giờ máy của lệnh, không cho trống.
    (Chỗ hỏng vẫn ghi đủ, để không rơi nhầm vào cửa "chưa ghi chỗ hỏng" bên dưới.)"""
    with pytest.raises(ValueError, match="lý do"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="   ", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
        )
    assert db.query(YeuCauSuaChua).count() == 0
    assert cv_dang_chay.trang_thai == CV_DANG_CHAY


def test_thieu_cho_hong_bi_chan(db, cv_dang_chay, to_truong):
    with pytest.raises(ValueError, match="chỗ hỏng"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="  ",
            mo_ta="máy kêu to", muc_do=MUC_DO_NHE, dung_san_xuat=False,
        )
    assert db.query(YeuCauSuaChua).count() == 0


def test_bao_su_co_tren_viec_chua_bat_dau_bi_chan(db, cv_chua_bat_dau, to_truong):
    with pytest.raises(ValueError, match="đang chạy|tạm dừng"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_chua_bat_dau.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
        )
    assert db.query(YeuCauSuaChua).count() == 0


def test_viec_khong_chay_may_bi_chan(db, cv_khong_may, to_truong):
    """Không có máy thì không có gì để báo hỏng — chặn ở service, không tin FE che nút."""
    with pytest.raises(ValueError, match="máy"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_khong_may.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=False,
        )


def test_muc_do_la_bi_chan_bang_valueerror(db, cv_dang_chay, to_truong):
    """Mức độ lạ phải ra `ValueError` — router `_chay` CHỈ dịch `ValueError`/`PermissionError`;
    để `KyThuatMayValidationError` lọt lên là 500 thay vì 400."""
    with pytest.raises(ValueError, match="Mức độ"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do="cao", dung_san_xuat=False,
        )
    assert db.query(YeuCauSuaChua).count() == 0


def test_khong_phai_to_truong_bi_chan(db, cv_dang_chay):
    from types import SimpleNamespace
    with pytest.raises(PermissionError):
        su_co.bao_su_co(
            db, user=SimpleNamespace(id=999_999), cong_viec_id=cv_dang_chay.id,
            bo_phan_hong="cụm cấp giấy", mo_ta="kẹt", muc_do=MUC_DO_NHE, dung_san_xuat=False,
        )
    assert db.query(YeuCauSuaChua).count() == 0


# --- NGUYÊN TỬ: gãy giữa chừng KHÔNG để lại nửa vời ------------------------------------------
def test_gay_khi_tam_dung_thi_khong_de_lai_yeu_cau_lo_lung(db, cv_dang_chay, to_truong, monkeypatch):
    """Bài chứng minh TÍNH NGUYÊN TỬ, không phải chỉ soi trạng thái cuối.

    Trước đây `create_yeu_cau` + `_ghi` + `tam_dung` mỗi cái tự `commit` ⇒ yêu cầu sửa chữa đã
    LƯU rồi mà bước tạm dừng gãy thì công việc vẫn "đang chạy" trên đúng cái máy vừa báo hỏng —
    sản lượng và giờ máy sau đó đều sai. Tiêm lỗi vào ĐÚNG bước tạm dừng và đòi cả hai đầu sạch.
    """
    def _no(*a, **k):
        raise RuntimeError("bể giữa chừng")

    monkeypatch.setattr(thuc_thi, "_tam_dung_lo", _no)
    with pytest.raises(RuntimeError):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt giấy liên tục", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
        )

    assert db.query(YeuCauSuaChua).count() == 0
    assert db.get(SanXuatCongViec, cv_dang_chay.id).trang_thai == CV_DANG_CHAY
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv_dang_chay.id, ket_thuc=None).count() == 1


def test_gay_giua_chung_thi_khong_bao_to_sua_chua(db, cv_dang_chay, to_truong, monkeypatch):
    """SSE chỉ được bắn SAU commit: ghi gãy mà tổ sửa chữa đã nhận "có máy hỏng" là báo động giả
    trỏ vào một yêu cầu không tồn tại."""
    from app.services import ky_thuat_may_service as ktm

    goi: list[str] = []
    monkeypatch.setattr(thuc_thi, "_tam_dung_lo",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bể")))
    monkeypatch.setattr(ktm.KyThuatMayService, "bao_to_sua_chua",
                        lambda self, yc: goi.append("bao_to"))
    monkeypatch.setattr(su_co.hub, "broadcast", lambda *a, **k: goi.append("broadcast"))

    with pytest.raises(RuntimeError):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
        )
    assert goi == []


def test_bao_to_sua_chua_chay_SAU_commit(db, cv_dang_chay, to_truong, monkeypatch):
    """Thứ tự bắt buộc: commit XONG rồi mới đẩy tin. Ghi lại mốc `after_commit` của chính session
    và mốc gọi thông báo rồi so thứ tự — không suy đoán từ trạng thái cuối."""
    from app.services import ky_thuat_may_service as ktm

    moc: list[str] = []

    def _ghi_commit(_session):
        moc.append("commit")

    event.listen(db, "after_commit", _ghi_commit)
    monkeypatch.setattr(ktm.KyThuatMayService, "bao_to_sua_chua",
                        lambda self, yc: moc.append("bao_to"))
    monkeypatch.setattr(su_co.hub, "broadcast", lambda *a, **k: moc.append("broadcast"))
    try:
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
        )
    finally:
        event.remove(db, "after_commit", _ghi_commit)

    assert "commit" in moc and "bao_to" in moc and "broadcast" in moc
    assert moc.index("commit") < moc.index("bao_to")
    assert moc.index("commit") < moc.index("broadcast")
    # ĐÚNG MỘT commit cho cả việc ghi yêu cầu + tạm dừng + audit — nhiều hơn nghĩa là còn chỗ
    # chốt lẻ, tức vẫn còn cửa sổ hỏng dù trạng thái cuối trông vẫn đúng.
    assert moc.count("commit") == 1, moc


# --- Nối vào hộp thư "Báo máy hỏng" -----------------------------------------------------------
def test_yeu_cau_hien_o_hop_thu_sua_chua(client, seed_credentials, db, cv_dang_chay, to_truong):
    """Không đẻ hộp thư thứ hai: yêu cầu báo từ màn Thực hiện SX phải nằm ngay trong hàng chờ
    tiếp nhận của tổ sửa chữa. Khoá thật của `ChoTiepNhanOut` là `total` (không phải `so_luong`)."""
    truoc = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    headers = {"Authorization": f"Bearer {truoc}"}
    goc = client.get("/api/ky-thuat-may/yeu-cau/cho-xu-ly", headers=headers)
    assert goc.status_code == 200, goc.text
    n0 = goc.json()["total"]

    su_co.bao_su_co(
        db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
        mo_ta="kẹt", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
    )

    r = client.get("/api/ky-thuat-may/yeu-cau/cho-xu-ly", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == n0 + 1

    # …và nó mang ĐÚNG neo về lệnh/công việc khi tổ sửa chữa mở danh sách.
    ds = client.get("/api/ky-thuat-may/yeu-cau?trang_thai=cho_xu_ly", headers=headers)
    assert ds.status_code == 200, ds.text
    yc = db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv_dang_chay.id).one()
    assert any(it["ma"] == yc.ma for it in ds.json()["items"])


def test_api_su_co_cung_cua_quyen_voi_tam_dung(client, seed_credentials, db, cv_dang_chay):
    """`su-co` phải đi qua ĐÚNG cùng cổng quyền với `tam-dung` (cùng `assign_work` + `_gate`).
    Không khẳng định thẳng 403: vai của `seed_credentials` có bit `can_assign_work` hay không là
    chuyện của seed, thứ cần chứng minh là hai đường cho CÙNG kết luận về quyền.

    Bắn vào công việc CÓ THẬT (review vòng 1, Minor 3): bản trước gõ thẳng id `1` — trên DB test
    vừa dựng lại thì id đó không tồn tại, nên cả hai đường hoặc chết ở cửa quyền hoặc chết ở 404,
    và phép so "cùng kết luận" đúng một cách tầm thường mà không hề đi qua `_gate`.
    """
    cv_id = cv_dang_chay.id
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r_tam_dung = client.post(
        f"/api/san-xuat/work-items/{cv_id}/tam-dung",
        json={"ly_do": "Soi cửa quyền — dừng thử"}, headers=headers,
    )
    r_su_co = client.post(
        f"/api/san-xuat/work-items/{cv_id}/su-co",
        json={"bo_phan_hong": "cụm cấp giấy", "mo_ta": "kẹt",
              "muc_do": MUC_DO_NGHIEM_TRONG, "dung_san_xuat": True},
        headers=headers,
    )
    assert r_su_co.status_code != 404, (r_su_co.status_code, r_su_co.text)
    assert (r_tam_dung.status_code == 403) == (r_su_co.status_code == 403), (
        r_tam_dung.status_code, r_tam_dung.text, r_su_co.status_code, r_su_co.text,
    )


# --- Chốt cứng phía server (thêm ở vòng sửa 1) -----------------------------------------------
def test_neo_san_xuat_khong_nhan_tu_than_request(db, may_sc):
    """NEO SẢN XUẤT chỉ do SERVER chốt: `cong_viec_id`/`lsx_id` đi bằng THAM SỐ RIÊNG của
    `tao_yeu_cau`/`create_yeu_cau`, KHÔNG đọc từ `data` — vốn là dict đi thẳng từ thân request.

    Vì sao phải khoá bằng test chứ không bằng lời hứa trong comment: nếu hai khoá này đọc được từ
    `data` thì chỉ cần ai đó khai thêm chúng ở `YeuCauIn`, bất kỳ ai gửi được "Báo máy hỏng" cũng
    treo được sự cố giả lên công việc/lệnh của tổ khác — hàng chờ tổ sửa chữa và cả mốc mất giờ
    máy đều trỏ nhầm chỗ. Và `ASSIGNABLE_YEU_CAU` KHÔNG phải cái chặn: vòng gán trực tiếp ngay
    dưới nó đọc cùng cái `data` ấy.
    """
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.ky_thuat_may_repo import KyThuatMayRepository
    from app.services.ky_thuat_may_service import KyThuatMayService

    svc = KyThuatMayService(db, KyThuatMayRepository(db), AuditLogRepository(db))
    ban = {"cong_viec_id": 777_777, "lsx_id": 888_888}          # client khai bậy

    # (1) Server KHÔNG chốt neo (đường "Báo máy hỏng" thường) ⇒ bản ghi phải trống, không nhận.
    yc = svc.tao_yeu_cau(
        {"may_id": may_sc.id, "bo_phan_hong": "cụm cấp giấy", "muc_do": MUC_DO_NHE, **ban},
    )
    db.refresh(yc)
    assert (yc.cong_viec_id, yc.lsx_id) == (None, None)

    # (2) Server CÓ chốt neo (đường báo sự cố tại tổ) ⇒ giá trị server thắng, không phải của client.
    yc2 = svc.tao_yeu_cau(
        {"may_id": may_sc.id, "bo_phan_hong": "đèn báo", "muc_do": MUC_DO_NHE, **ban},
        cong_viec_id=12, lsx_id=34,
    )
    db.refresh(yc2)
    assert (yc2.cong_viec_id, yc2.lsx_id) == (12, 34)


def test_muc_do_rong_khong_am_tham_thanh_trung_binh(db, cv_dang_chay, to_truong):
    """`muc_do=""` phải bị CHẶN, không được lọt.

    Lọt xuống thì `tao_yeu_cau` âm thầm đặt `trung_binh`; hàng chờ tổ sửa chữa xếp theo `uu_tien`
    nên một sự cố KHÔNG AI chọn mức lại chen lên trên những yêu cầu Nhẹ có người chọn thật. Chặn
    hai lớp: schema không cho gửi lên, service không tin FE.
    """
    from pydantic import ValidationError

    from app.schemas.san_xuat import SuCoIn

    with pytest.raises(ValueError, match="Mức độ"):
        su_co.bao_su_co(
            db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
            mo_ta="kẹt", muc_do="", dung_san_xuat=False,
        )
    assert db.query(YeuCauSuaChua).count() == 0
    assert cv_dang_chay.trang_thai == CV_DANG_CHAY

    with pytest.raises(ValidationError):
        SuCoIn(bo_phan_hong="cụm cấp giấy", mo_ta="kẹt", muc_do="", dung_san_xuat=False)


def test_bao_tin_gay_sau_commit_khong_lam_hong_ket_qua(db, cv_dang_chay, to_truong, monkeypatch):
    """Khâu BÁO TIN chạy sau commit thì hỏng cũng KHÔNG được kéo theo thao tác đã chốt.

    `bao_to_sua_chua` không phải broadcast thuần bộ nhớ (còn đọc máy + join vai tổ sửa chữa). Nó
    ném ở đây thì `_chay` không dịch nổi ⇒ tổ trưởng thấy 500 và FE báo "thử lại", TRONG KHI sự cố
    đã ghi và việc đã tạm dừng thật — bấm lại là đẻ yêu cầu thứ hai làm rác hộp thư sửa chữa. Nuốt
    lỗi ở đây chỉ mất cái "ting" tức thì; yêu cầu vẫn nằm sẵn trong hàng chờ khi tổ sửa mở màn.
    """
    from app.services import ky_thuat_may_service as ktm

    def _no(self, yc):
        raise RuntimeError("rớt kết nối ngay sau commit")

    monkeypatch.setattr(ktm.KyThuatMayService, "bao_to_sua_chua", _no)
    kq = su_co.bao_su_co(
        db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
        mo_ta="kẹt giấy liên tục", muc_do=MUC_DO_NGHIEM_TRONG, dung_san_xuat=True,
    )

    yc = db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv_dang_chay.id).one()
    assert kq["yeu_cau_id"] == yc.id and kq["yeu_cau_ma"] == yc.ma
    assert kq["trang_thai"] == CV_TAM_DUNG           # dựng dict TRƯỚC khi báo tin nên không rỗng
    assert db.get(SanXuatCongViec, cv_dang_chay.id).trang_thai == CV_TAM_DUNG
