"""Hồ sơ LSX chỉ đọc. Bốn thứ dễ làm sai:
  · 403 khi gõ id ngoài phạm vi (không phải 404 mập mờ, không phải trả nội dung).
  · Vật tư có HAI mức: đủ cho bước HIỆN TẠI vs cảnh báo bước SAU — gộp một là mất nghĩa.
  · Timeline gộp đủ nguồn và sắp theo thời gian server.
  · `phien_ban` đọc từ `san_xuat_goi_phat_hanh.version_hien_tai`, KHÔNG cột mới trên `lsx`.

Và BẢY khoảng hụt mà màn hồ sơ (Task 12) cần nhưng danh sách 12 khối của brief không gọi tên —
mỗi cái một bài dưới đây: thông số kỹ thuật · giờ máy · vật tư ĐÃ CẤP · lịch sử đổi tổ-máy-người ·
phiếu sửa dưới sự cố · giao hàng đủ để KHOÁ nút và ĐIỀN SẴN · routing vẽ được nhánh SONG SONG.

FIXTURE dàn cảnh dùng chung nằm ở `tests/lenh_sx_fixtures.py` (RÚT ra từ `test_lenh_sx_api.py`,
không CHÉP — hai bản sao thì bản trôi trước sẽ nói dối mà vẫn xanh). Chỉ năm fixture RIÊNG của
brief này dựng tại chỗ, vì không màn nào khác cần chúng.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.department import Department
from app.models.kho_hang import KhoHang
from app.models.ky_thuat_may import TT_SC_DANG_SUA, TT_YC_DA_TAO_PHIEU, SuaChuaMay
from app.models.lsx import TT_SAN_SANG, Lsx, LsxCongDoan, LsxCongDoanVatTu
from app.models.may_thiet_bi import MayThietBi
from app.models.order import OrderLine
from app.models.san_xuat import SanXuatCongViec, SanXuatNhomLsx
from app.models.san_xuat_ly_do import NHOM_LOI, SanXuatLyDo
from app.models.san_xuat_thuc_thi import SanXuatPhanCong
from app.models.bai_ghep_cong_doan import BaiGhepCongDoanVatTu
from app.models.san_xuat_kho import SanXuatKhoHang, SanXuatKhoLot
from app.models.stock_request import REQ_XUAT, StockRequest, StockRequestLine
from app.models.vat_lieu_kho import VatTuInAn
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.san_xuat import kho as kho_svc
from app.services.san_xuat import san_luong as san_luong_svc
from app.services.san_xuat import nhom as nhom_svc
from app.services.san_xuat import release, release_update, thuc_thi

# Helper (plain function, KHÔNG phải fixture) của file anh em — đi đúng khuôn đường ghi thật.
from tests.test_lenh_sx_trang_thai import _giao_xong, _kcs_batch, _nhap_kho_yc, _su_co

# Fixture + helper dùng chung. `noqa: F401` vì pytest tiêu thụ fixture qua TÊN trong namespace
# module test, không qua lời gọi — bỏ import là mọi bài dưới đây mất fixture.
from tests.lenh_sx_fixtures import (  # noqa: F401
    _chay_that,
    _cvs,
    _dot_dong_don,
    _lenh_ghep_doi,
    _giao_nguoi,
    _lenh_tho,
    _phat_hanh_that,
    admin,
    customer,
    ghep_doi,
    lenh_that,
    lsx_svc,
    orders,
    sale_own,
    sess,
)


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def _ho_so(client, cred, lsx_id: int) -> dict:
    r = client.get(
        f"/api/lenh-san-xuat/{lsx_id}",
        headers={"Authorization": f"Bearer {_tok(client, cred)}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _buoc_cua(sess, lsx_id: int) -> list[LsxCongDoan]:
    return (
        sess.query(LsxCongDoan)
        .filter(LsxCongDoan.lsx_id == lsx_id)
        .order_by(LsxCongDoan.thu_tu)
        .all()
    )


def _vat_tu_moi(sess, *, ma: str, ten: str, don_vi: str = "kg") -> VatTuInAn:
    """Một mặt hàng vật tư KHÔNG có lô tồn nào — nền của mọi bài "thiếu". Seed không có dòng
    `vat_tu_in_an` nào (đã đo), nên món này chắc chắn tồn 0."""
    vt = VatTuInAn(ma=ma, ten=ten, don_vi_gia=don_vi)
    sess.add(vt)
    sess.commit()
    return vt


def _khai_vat_tu_buoc(sess, buoc: LsxCongDoan, vt: VatTuInAn, so_luong: float) -> None:
    """Khai một dòng vật tư ở BƯỚC của lệnh — đúng bảng mà `_gom_nhu_cau` đọc
    (`lsx_cong_doan_vat_tu`, qua `repo.vat_tu_theo_buoc_lenh`)."""
    sess.add(LsxCongDoanVatTu(
        lsx_cong_doan_id=buoc.id, vat_tu_id=vt.id, vat_tu_ma_snapshot=vt.ma,
        vat_tu_ten_snapshot=vt.ten, don_vi_snapshot=vt.don_vi_gia,
        so_luong=so_luong, thu_tu=0,
    ))
    sess.commit()


# --- Năm fixture RIÊNG của brief ---------------------------------------------------------------
@pytest.fixture
def sale_a_credentials(sale_own) -> dict[str, str]:
    """Đăng nhập của một người bán phạm vi `own` (vai seed "NV Sales").

    Mật khẩu khai ở `lenh_sx_fixtures.sale_own` (`hash_password("x")`); fixture này chỉ dịch nó
    sang payload đăng nhập, không đẻ thêm người dùng thứ hai.
    """
    return {"username": sale_own.username, "password": "x"}


@pytest.fixture
def lenh_cua_sale_b(sess, admin, customer) -> int:
    """Lệnh ĐÃ PHÁT HÀNH của một người bán KHÁC (admin) — Sale A không được thấy nội dung."""
    return _lenh_tho(
        sess, ma="LSX-HS-B", sale_user_id=admin.id, customer_id=customer.id,
        han_sx=date(2026, 9, 9), ten="Lệnh của người bán khác",
    )


@pytest.fixture
def lenh_du_buoc_nay_thieu_buoc_sau(sess, lenh_that) -> int:
    """Bước HIỆN TẠI đủ giấy — bước SAU (Đóng gói) khai một vật tư kho KHÔNG có lô nào.

    Giấy của lệnh có tồn từ seed nên dòng giấy ra `xanh`; vật tư vừa tạo tồn 0 nên dòng ở Đóng gói
    ra `do`. Đó đúng là hình dạng "đủ cho việc đang làm, hụt cho việc sắp tới" mà hai mức của khối
    `vat_tu` sinh ra để tách.
    """
    _khai_vat_tu_buoc(
        sess, _buoc_cua(sess, lenh_that)[-1],
        _vat_tu_moi(sess, ma="VT-HS-KEO", ten="Keo dán hộp"), 50,
    )
    return lenh_that


@pytest.fixture
def lenh_nhieu_su_kien(sess, admin, lenh_that) -> int:
    """Lệnh có ít nhất BA loại sự kiện khác nhau: phát hành · chạy xong một bước · báo sự cố.

    Hai cái đầu đi đường ghi thật (`release.phat_hanh` trong fixture nền; `thuc_thi.bat_dau` +
    `ket_thuc` ở đây qua `_chay_that`), sự cố dựng đúng khuôn `su_co.bao_su_co` ghi ra.
    """
    cv = _cvs(sess, lenh_that)[0]
    _chay_that(sess, admin, cv, ma="NV-HS-01", ten="Thợ chế bản")
    _su_co(sess, lenh_that, cv.id, ma="YC-HS-1")
    return lenh_that


@pytest.fixture
def lenh_da_cap_nhat_phat_hanh(sess, admin, lenh_that) -> int:
    """Gói phát hành đã qua MỘT lần "Phát hành cập nhật" ⇒ `version_hien_tai = 2`.

    Đi đúng đường ghi production `release_update.phat_hanh_cap_nhat` (tự commit) chứ không gán tay
    `goi.version_hien_tai`: chỉ như vậy bài `test_phien_ban_doc_tu_goi_phat_hanh` mới chứng minh
    được hồ sơ ĐỌC TỪ GÓI, thay vì đọc một con số fixture vừa bịa ra.
    """
    release_update.phat_hanh_cap_nhat(
        sess, nguon="lsx", id=lenh_that, ly_do="Dời lịch do máy bận", actor=admin,
    )
    sess.expire_all()
    return lenh_that


@pytest.fixture
def lenh_thu_hoi_roi_phat_hanh_lai(sess, admin, lenh_that) -> int:
    """Gói CŨ bị thu hồi, lệnh phát hành lại rồi cập nhật một lần ⇒ gói hiệu lực ở v2.

    Ba bước đều đi đường ghi production (`thu_hoi_goi` → `release.phat_hanh` → `phat_hanh_cap_nhat`).
    Điểm mấu chốt để bài canh có nghĩa: `thu_hoi_goi` KHÔNG xoá `SanXuatCongViec` của gói cũ — nó
    chỉ đổi `goi.trang_thai` — nên sau bước hai, lệnh mang công việc của HAI gói cùng lúc, đúng
    cảnh đang có trên DB dev.
    """
    release_update.thu_hoi_goi(sess, nguon="lsx", id=lenh_that, actor=admin)
    sess.commit()
    release.phat_hanh(sess, lsx_ids={lenh_that}, actor=admin)
    sess.commit()
    release_update.phat_hanh_cap_nhat(
        sess, nguon="lsx", id=lenh_that, ly_do="Xếp lại sau khi thu hồi", actor=admin,
    )
    sess.expire_all()
    return lenh_that


# --- Bốn bài của brief -------------------------------------------------------------------------
def test_ngoai_pham_vi_403(client, sale_a_credentials, lenh_cua_sale_b):
    h = {"Authorization": f"Bearer {_tok(client, sale_a_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_cua_sale_b}", headers=h)
    assert r.status_code == 403
    assert "LSX" not in r.text.upper().replace("LỆNH SẢN XUẤT", "")


def test_vat_tu_hai_muc(client, seed_credentials, lenh_du_buoc_nay_thieu_buoc_sau):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    d = client.get(
        f"/api/lenh-san-xuat/{lenh_du_buoc_nay_thieu_buoc_sau}", headers=h
    ).json()
    assert d["vat_tu"]["hien_tai"]["du"] is True
    assert len(d["vat_tu"]["canh_bao_sau"]) >= 1


def test_timeline_sap_theo_thoi_gian(client, seed_credentials, lenh_nhieu_su_kien):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    tl = client.get(f"/api/lenh-san-xuat/{lenh_nhieu_su_kien}", headers=h).json()["timeline"]
    assert len(tl) >= 3
    assert [e["luc"] for e in tl] == sorted(e["luc"] for e in tl)
    assert {"loai", "luc", "nguoi", "noi_dung"} <= set(tl[0])


def test_timeline_kcs_noi_tieng_viet_khong_ro_khoa_enum(
    client, seed_credentials, sess, lenh_that
):
    """Câu KCS trên dòng thời gian là chuỗi ĐÃ DỰNG SẴN cho người đọc — nó phải nói tiếng Việt.

    `ket_luan` là khoá máy. Ghép thẳng vào câu thì màn xưởng đọc ra
    "KCS Công đoạn: 100 đạt · 20 không đạt (dat_mot_phan)" — đúng thứ đã nhìn thấy trên dev-browser.
    Ngược lại, TRƯỜNG `kcs.batch[].ket_luan` vẫn phải trả khoá THÔ: FE có bảng nhãn riêng và dịch
    lấy, đổi trường đó thành chữ là bắt FE so chuỗi tiếng Việt.
    """
    _kcs_batch(sess, _cvs(sess, lenh_that)[0].id, nhan=120, dat=100, khong_dat=20,
               ket_luan="dat_mot_phan")

    d = _ho_so(client, seed_credentials, lenh_that)
    cau = [e["noi_dung"] for e in d["timeline"] if e["loai"] == "kcs"]
    assert len(cau) == 1, "tiền đề: đúng một sự kiện KCS trên dòng thời gian"
    assert "Đạt một phần" in cau[0], f"nhãn tiếng Việt không ra tới câu timeline: {cau[0]!r}"
    assert "dat_mot_phan" not in cau[0], f"khoá enum thô lọt ra mặt người dùng: {cau[0]!r}"
    assert d["kcs"]["batch"][0]["ket_luan"] == "dat_mot_phan", "trường thô phải giữ nguyên khoá"


def test_phien_ban_doc_tu_goi_phat_hanh(client, seed_credentials, lenh_da_cap_nhat_phat_hanh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    d = client.get(f"/api/lenh-san-xuat/{lenh_da_cap_nhat_phat_hanh}", headers=h).json()
    assert d["phien_ban"] >= 2


def test_phien_ban_lay_goi_dang_hieu_luc_khong_lay_goi_da_thu_hoi(
    client, seed_credentials, lenh_thu_hoi_roi_phat_hanh_lai
):
    """Lệnh mang công việc của HAI gói ⇒ phải đọc gói ĐANG HIỆU LỰC, không phải gói đã thu hồi.

    Bắt được trên DB dev, LSX26-0029: hồ sơ in "Phiên bản 1" trong khi bàn xếp lịch nói
    "phiên bản 2" cho cùng lệnh đó. `thu_hoi_goi` chỉ đổi `goi.trang_thai` và ĐỂ NGUYÊN các dòng
    `SanXuatCongViec` của gói cũ, nên `cong_viec_du()` trả về công việc của cả hai gói và
    `_goi_id` (lấy `goi_id` ĐẦU TIÊN gặp) rơi vào gói đã chết.

    Không phải lỗi cosmetic: QR trên phiếu công nghệ mã hoá `pv=<phien_ban>` lấy từ đúng con số
    này, nên phiếu in ra mang `pv=1` và băng cảnh báo "phiếu giấy này là bản cũ" KHÔNG BAO GIỜ
    bật cho đúng loại lệnh nó sinh ra để phục vụ.
    """
    d = _ho_so(client, seed_credentials, lenh_thu_hoi_roi_phat_hanh_lai)
    assert d["phien_ban"] == 2, (
        "hồ sơ đọc nhầm gói đã thu hồi — phải là 2 (gói đang hiệu lực), không phải "
        f"{d['phien_ban']}"
    )


# --- Cửa: quyền · trạng thái · không lộ tiền ---------------------------------------------------
def test_khong_dang_nhap_401(client, lenh_that):
    assert client.get(f"/api/lenh-san-xuat/{lenh_that}").status_code == 401


def test_lenh_chua_phat_hanh_tra_404(client, seed_credentials, sess, admin):
    """Lệnh còn ở bàn kế hoạch KHÔNG thuộc màn này — 404, không phải 403.

    403 nói "có lệnh đó nhưng không phải phần việc của bạn"; ở đây câu đúng là "màn này không có
    lệnh nào như thế", vì lệnh chưa phát hành thì chưa ai ở xưởng nhìn thấy nó.
    """
    lsx_id = _lenh_tho(
        sess, ma="LSX-HS-NHAP", sale_user_id=admin.id, trang_thai_lsx=TT_SAN_SANG,
    )
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    assert client.get(f"/api/lenh-san-xuat/{lsx_id}", headers=h).status_code == 404


def test_khong_lo_tien(client, seed_credentials, sess, admin, lenh_du_buoc_nay_thieu_buoc_sau):
    """Đọc trên hồ sơ ĐẦY ĐỦ (routing + người + vật tư), không phải trên một body rỗng.

    `quy_cach_json` của lệnh CÓ mang khoá tiền (`phi_giao_hang` — `lsx_service` chép NGUYÊN cụm
    trường vô hướng của phiếu tính giá vào đó, chỉ bỏ 7 khoá trong `_QC_BO_QUA`), nên khối
    `thong_so` bắt buộc phải KHAI TỪNG TRƯỜNG chứ không được đổ nguyên dict ra ngoài. Bài này là
    lưới của luật đó, không phải một phép so hình thức.

    `la_luong_khoan` nằm cùng danh sách cấm: nó là ảnh chụp CHẾ ĐỘ LƯƠNG của một người trên một
    bước — màn của điều độ và tổ trưởng không có việc gì với nó.
    """
    _giao_nguoi(sess, admin, _cvs(sess, lenh_du_buoc_nay_thieu_buoc_sau)[0],
                ma="NV-HS-TIEN", ten="Thợ kiểm tiền")
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_du_buoc_nay_thieu_buoc_sau}", headers=h)
    assert r.status_code == 200, r.text
    body = r.text.lower()
    for cam in ("don_gia", "gia_von", "thanh_tien", "luong_khoan", "chi_phi", "phi_giao_hang"):
        assert cam not in body, f"hồ sơ lộ khoá tiền `{cam}`"


def test_du_cac_khoi(client, seed_credentials, lenh_that):
    """Mười hai khối của brief + `thong_so` phải có mặt ĐỦ — thiếu một khối là màn mất một mảng.

    Bẫy Pydantic của repo: trường không khai trong schema Out bị NUỐT IM LẶNG. Bài này đọc JSON
    THẬT qua HTTP (không đọc dict của service) nên nó bắt được đúng cái nuốt đó.
    """
    d = _ho_so(client, seed_credentials, lenh_that)
    assert set(d) >= {
        "thong_tin", "tien_do", "thong_so", "routing", "vat_tu", "nhan_luc", "san_luong",
        "su_co", "kcs", "kho", "giao_hang", "timeline", "phien_ban",
    }


def test_phien_ban_none_khi_lenh_khong_co_cong_viec(client, seed_credentials, sess, admin):
    """Lệnh đã phát hành mà KHÔNG có công việc nào ⇒ `phien_ban = None`, KHÔNG mặc định 1.

    Gói phát hành không neo `lsx_id`; đường DUY NHẤT tới nó đi qua `cong_viec.goi_id`. Không có
    công việc thì không có gói — trả 1 là bịa ra một phiên bản chưa từng được phát hành.
    """
    lsx_id = _lenh_tho(sess, ma="LSX-HS-TRONG", sale_user_id=admin.id)
    assert _ho_so(client, seed_credentials, lsx_id)["phien_ban"] is None


# --- Khoảng hụt 1: thông số kỹ thuật -----------------------------------------------------------
def test_thong_so_ky_thuat_ra_toi_response(client, seed_credentials, sess, lenh_that):
    """Khổ giấy · khổ tờ in · cách in · số con · số tờ — mở hồ sơ là phải thấy, không phải sang
    màn khác.

    So với CHÍNH `lsx.quy_cach_json` + cột dẫn xuất trên `lsx` chứ không so hằng số: fixture đi qua
    phiếu tính giá thật nên các số này do engine sinh; gõ lại một con số ở đây là bài canh chính nó.
    """
    lsx = sess.get(Lsx, lenh_that)
    qc = lsx.quy_cach_json or {}
    ts = _ho_so(client, seed_credentials, lenh_that)["thong_so"]
    assert qc.get("kho_nguyen_dai"), "tiền đề: lệnh phải có khổ giấy nguyên"
    for k in ("kho_nguyen_dai", "kho_nguyen_rong", "kho_in_dai", "kho_in_rong", "quy_cach_in"):
        assert ts[k] == qc.get(k), f"thông số `{k}` lệch quy cách đã chụp"
    assert ts["so_con"] == lsx.so_con
    assert ts["so_to_nguyen"] == lsx.so_to_nguyen
    assert ts["so_to_ke_hoach"] == lsx.so_to_ke_hoach


# --- Khoảng hụt 2: giờ máy ---------------------------------------------------------------------
def test_gio_may_o_dau_ho_so(client, seed_credentials, sess, admin, lenh_that):
    """Giờ máy phải nằm ngay khối tiến độ, và phải NHÍCH khi một bước thật sự chạy xong.

    Đo DELTA quanh một lượt `bat_dau` → `ket_thuc` thật: so một số tuyệt đối là phụ thuộc vào việc
    fixture nền có sẵn phiên nào hay không.
    """
    truoc = _ho_so(client, seed_credentials, lenh_that)["tien_do"]["gio_may"]
    _chay_that(sess, admin, _cvs(sess, lenh_that)[0], ma="NV-HS-GM", ten="Thợ giờ máy")
    sau = _ho_so(client, seed_credentials, lenh_that)["tien_do"]["gio_may"]
    assert sau > truoc, "một lượt chạy thật không vào được giờ máy của hồ sơ"


# --- Khoảng hụt 3: vật tư ĐÃ CẤP ---------------------------------------------------------------
def _de_nghi_xuat(sess, admin, lsx_id: int, vt: VatTuInAn, *, duyet: float, da_ung: float) -> None:
    """Một đề nghị XUẤT kho đã duyệt + đã ứng một phần — nguồn DUY NHẤT của "đã cấp"/"đang lĩnh".

    `sl_da_ung` = kho đã ghi sổ (tồn đã trừ) ⇒ ĐÃ CẤP; `sl_duyet − sl_da_ung` ⇒ ĐANG LĨNH. Cả hai
    do `KeHoachVatTuService._da_cap_dang_linh` đọc ra rồi đặt lên CHÍNH dòng cân đối — hồ sơ chỉ
    được LẤY con số đó, cấm đi hỏi bảng vật tư lần thứ hai.
    """
    yc = StockRequest(ma=f"YCK-HS-{lsx_id}", loai=REQ_XUAT, nguoi_tao_id=admin.id)
    sess.add(yc)
    sess.flush()
    sess.add(StockRequestLine(
        request_id=yc.id, hang_loai="vat_tu", hang_id=vt.id, lsx_id=lsx_id,
        dvt=vt.don_vi_gia, sl_de_nghi=duyet, sl_duyet=duyet, sl_da_ung=da_ung,
    ))
    sess.commit()


def test_vat_tu_da_cap_lay_tu_dong_can_doi(client, seed_credentials, sess, admin, lenh_that):
    """Ba con số vật tư sống trên CÙNG một dòng cân đối: cần · đã cấp · đang lĩnh.

    Kho xuất cho một LỆNH (dòng đề nghị chỉ mang `lsx_id`, không có bước), nên con số này phải tới
    từ `can_doi()` chứ không từ một truy vấn vật tư thứ hai — hai nguồn thì sớm muộn lệch, mà lệch
    ở đây là tổ đi xin thừa hoặc thiếu.
    """
    vt = _vat_tu_moi(sess, ma="VT-HS-MUC", ten="Mực đen")
    _khai_vat_tu_buoc(sess, _buoc_cua(sess, lenh_that)[-1], vt, 50)
    _de_nghi_xuat(sess, admin, lenh_that, vt, duyet=50, da_ung=30)

    v = _ho_so(client, seed_credentials, lenh_that)["vat_tu"]
    dong = [r for r in v["da_cap"] if r["hang_ma"] == "VT-HS-MUC"]
    assert len(dong) == 1, "dòng đã cấp phải có mặt ở khối vật tư"
    assert dong[0]["da_cap"] == 30.0
    assert dong[0]["dang_linh"] == 20.0


def test_vat_tu_khong_lan_sang_lenh_khac(client, seed_credentials, sess, lenh_that):
    """`can_doi()` trả về dòng của MỌI lệnh còn sống, không riêng lệnh đang mở.

    `_lenh_trong_pham_vi` đi qua `lsx_repo.cho_mrp`, hàm luôn OR thêm `trang_thai IN
    TRANG_THAI_TINH` — nên `include_lsx_ids={id}` KHÔNG phải một bộ lọc (đã đo: gọi với đúng một id
    vẫn ra dòng của lệnh khác). Không chiếu lại về đúng lệnh thì hồ sơ bày vật tư của lệnh hàng
    xóm, và bày một cách rất tự tin.
    """
    ma_lenh = sess.get(Lsx, lenh_that).ma
    v = _ho_so(client, seed_credentials, lenh_that)["vat_tu"]
    moi_dong = v["hien_tai"]["dong"] + v["canh_bao_sau"] + v["da_cap"]
    assert moi_dong, "tiền đề: lệnh phải có ít nhất một dòng vật tư"
    assert {r["ma"] for r in moi_dong} == {ma_lenh}


# --- Khoảng hụt 4: lịch sử đổi tổ · máy · người ------------------------------------------------
def test_nhan_luc_giu_ca_nguoi_da_bi_rut(client, seed_credentials, sess, admin, lenh_that):
    """Bảng điều độ giấu người đã rút; HỒ SƠ thì phải giữ — đây là chỗ trả lời "ai từng làm việc
    này".

    `BoiCanh.phan_cong` chỉ nạp dòng `active` (đúng cho bảng danh sách), nên khối lịch sử BẮT BUỘC
    phải đọc thêm dòng `removed` — và đọc thêm chứ không nới điều kiện của tầng nạp chung.
    """
    cv = _cvs(sess, lenh_that)[0]
    pc = _giao_nguoi(sess, admin, cv, ma="NV-HS-11", ten="Người đã rút")
    _giao_nguoi(sess, admin, cv, ma="NV-HS-12", ten="Người đang làm")
    thuc_thi.go_phan_cong(sess, user=admin, phan_cong_id=pc, ly_do="Chuyển sang tổ khác")
    sess.expire_all()

    nl = _ho_so(client, seed_credentials, lenh_that)["nhan_luc"]
    assert {ten for b in nl["hien_tai"] for ten in b["nguoi"]} == {"Người đang làm"}
    rut = [e for e in nl["lich_su"] if e["loai"] == "rut_nguoi"]
    assert rut and rut[0]["nguoi"] == "Người đã rút"
    assert rut[0]["ly_do"] == "Chuyển sang tổ khác"


def test_nhan_luc_ghi_lai_lan_doi_may(client, seed_credentials, sess, admin, lenh_that):
    """Đổi máy giữa chừng phải để lại VẾT: máy cũ → máy mới, đúng mốc.

    Đường ghi là `thuc_thi.doi_may`: nó đóng phiên đang chạy bằng `loai_dong='doi_may'` rồi mở
    NGAY một phiên mới trên máy mới. Cặp phiên đó LÀ lịch sử máy — không bảng nào khác giữ nó, và
    `cong_viec.may_id` chỉ còn nhớ máy CUỐI CÙNG.
    """
    cv = _cvs(sess, lenh_that)[1]
    may_cu = MayThietBi(ma="MAY-HS-A", ten="Máy in A", loai_may="in")
    may_moi = MayThietBi(ma="MAY-HS-B", ten="Máy in B", loai_may="in")
    sess.add_all([may_cu, may_moi])
    to = sess.get(Department, cv.department_id)
    to.has_piece_work = True
    sess.commit()
    _giao_nguoi(sess, admin, cv, ma="NV-HS-21", ten="Thợ đổi máy")
    cv.may_id = may_cu.id
    sess.commit()
    thuc_thi.bat_dau(
        sess, user=admin, cong_viec_id=cv.id,
        ly_do_tre="Chờ giấy về", ly_do_so_nguoi="Tổ thiếu người",
    )
    thuc_thi.doi_may(sess, user=admin, cong_viec_id=cv.id, may_id_moi=may_moi.id,
                     ly_do="Máy cũ kẹt giấy")
    sess.expire_all()

    doi = [e for e in _ho_so(client, seed_credentials, lenh_that)["nhan_luc"]["lich_su"]
           if e["loai"] == "doi_may"]
    assert doi, "hồ sơ mất vết đổi máy"
    assert doi[0]["may_cu"] == "Máy in A"
    assert doi[0]["may_moi"] == "Máy in B"
    assert doi[0]["ly_do"] == "Máy cũ kẹt giấy"


# --- Khoảng hụt 5: phiếu sửa dưới sự cố --------------------------------------------------------
def test_su_co_keo_theo_phieu_sua(client, seed_credentials, sess, lenh_that):
    """Yêu cầu sửa đã được tiếp nhận thì hồ sơ phải bấm được sang PHIẾU — không thì người báo
    không có đường nào biết thợ đang làm tới đâu.

    `yeu_cau.phieu_id` là soft-ref sang `ky_thuat_sua_chua.id`, KHÔNG có relationship ORM nào —
    phải nối tay, và nối đúng chiều đó.
    """
    phieu = SuaChuaMay(ma="SC-HS-1", may_id=9_001, bo_phan_hong="Cụm cấp giấy",
                       muc_do="trung_binh", trang_thai=TT_SC_DANG_SUA)
    sess.add(phieu)
    sess.flush()
    yc = _su_co(sess, lenh_that, _cvs(sess, lenh_that)[0].id,
                tt=TT_YC_DA_TAO_PHIEU, ma="YC-HS-9")
    yc.phieu_id = phieu.id
    sess.commit()

    sc = _ho_so(client, seed_credentials, lenh_that)["su_co"]
    assert len(sc) == 1
    assert sc[0]["ma"] == "YC-HS-9"
    assert sc[0]["phieu"] is not None, "sự cố mất đường sang phiếu sửa"
    assert sc[0]["phieu"]["ma"] == "SC-HS-1"
    assert sc[0]["phieu"]["trang_thai"] == TT_SC_DANG_SUA


# --- Khoảng hụt 6: giao hàng đủ để KHOÁ nút và ĐIỀN SẴN ----------------------------------------
def _nhap_kho_that(sess, admin, lsx_id: int, cv, *, so_luong: float,
                   kho_ma: str = "KHO-HS-TP", hang_id: int | None = None) -> tuple[KhoHang, int]:
    """KCS chốt một batch ĐẠT → yêu cầu nhập kho → KHO xác nhận nhận, bằng đường ghi thật.

    Hai bước đầu dựng theo đúng khuôn service ghi ra; bước cuối gọi thẳng
    `kho.kho_xac_nhan_nhap` vì chính nó là chỗ đẻ LOT mang `kho_id` — mà kho đích là một trong
    những ô form giao hàng phải điền sẵn. `_nhap_kho_yc` để `nhom_id` trống nên phải nối nhóm ở
    đây: lot thành phẩm neo NHÓM (`lsx_id` của nó luôn NULL, xem `boi_canh.py`).

    ⚠️ FIXTURE GÁN TAY, KHÔNG ĐI ĐƯỜNG GHI THẬT ở khâu gắn nhóm. Đường thật là
    `kho.tao_yeu_cau_nhap_thanh_pham` → `_tao_yc_tu_batch`: nó lấy nhóm từ `kcs_batch.nhom_id` rồi
    truyền xuống `_get_or_create_hang`, và `kho_xac_nhan_nhap` chép `lot.nhom_id = yc.nhom_id`.
    Giá trị gán ở đây bằng đúng giá trị production ghi, nhưng nếu đường thật NGỪNG đặt `nhom_id`
    thì bài này vẫn xanh — nó KHÔNG canh đường ghi, chỉ canh phép tính đọc phía sau. Ai đụng
    `_tao_yc_tu_batch` thì đừng trông vào bài này để biết mình có làm vỡ gì không.

    `hang_id` truyền vào ⇒ dùng LẠI mặt hàng đó thay vì để `_nhap_kho_yc` đẻ mặt hàng mới. Đây mới
    là hình dạng production: `kho._get_or_create_hang` tái dùng ĐÚNG một mặt hàng cho cùng
    (đơn, nhóm, loại, quy cách, đơn vị), nên hai mẻ KCS của cùng một nhóm nhập vào hai kho khác
    nhau là HAI lot chung MỘT `hang_id`. Không có tham số này thì không bài nào dựng nổi ca "một
    mặt hàng nằm hai kho" — ca mà quy ước trừ-dần-theo-`kho_id` sống bằng.

    Trả `(kho, hang_id)` để bài sau chuyền `hang_id` sang lượt nhập kế tiếp.
    """
    tv = sess.query(SanXuatNhomLsx).filter_by(lsx_id=lsx_id).one()
    kb = _kcs_batch(sess, cv.id, nhan=so_luong, dat=so_luong, khong_dat=0, ket_luan="dat")
    yc = _nhap_kho_yc(sess, lsx_id, kb, yeu_cau=so_luong, xac_nhan=0, trang_thai_yc="cho_kho")
    if hang_id is not None:
        thua = sess.get(SanXuatKhoHang, yc.hang_id)
        yc.hang_id = hang_id
        sess.flush()
        sess.delete(thua)          # mặt hàng `_nhap_kho_yc` vừa đẻ ra: production không đẻ nó
    yc.nhom_id = tv.nhom_id
    sess.get(SanXuatKhoHang, yc.hang_id).nhom_id = tv.nhom_id
    # Get-or-create: gọi hàm này HAI lần (hai mặt hàng của cùng nhóm) là ca thật, mà `kho_hang.ma`
    # là unique — tạo mù lần hai thì vỡ ở constraint chứ không phải ở thứ bài test muốn soi.
    k = sess.query(KhoHang).filter_by(ma=kho_ma).one_or_none()
    if k is None:
        k = KhoHang(ma=kho_ma, ten=f"Kho thành phẩm {kho_ma}")
        sess.add(k)
    sess.commit()
    kho_svc.kho_xac_nhan_nhap(sess, user=admin, yc_id=yc.id, so_luong=so_luong, kho_id=k.id)
    ra = int(yc.hang_id)
    sess.expire_all()
    return k, ra


def _nhom_hai_lenh(sess, lsx_id: int, *, nhan: str = "Kỷ yếu") -> int:
    """Dồn lệnh đang mở + lệnh ANH EM cùng đơn vào MỘT nhóm thành phẩm, mỗi lệnh một DÒNG ĐƠN riêng.

    Đây là hình dạng chính thức của hệ, không phải ca dựng cho vui: `SanXuatNhomLsx.lsx_id` là
    UNIQUE nhưng `nhom_id` thì KHÔNG, và nhóm sinh ra từ `OrderLine.nhom` (`nhom._khoa`) — Ruột và
    Bìa là hai dòng đơn khác nhau, cùng nhãn, cùng ra một thành phẩm. Đơn của `lenh_that` sẵn có
    HAI dòng ("Hộp A"/"Hộp B") và hai LSX; fixture chỉ dán nhãn chung rồi gom, không bịa thêm dòng.

    `nhom.dam_bao_nhom` là ĐÚNG hàm mà phát hành gọi: tự tính khoá nhóm, tự dời thành viên cũ sang
    nhóm mới, tự ghi `order_line_id` lên dòng thành viên.

    ⚠️ MỘT chỗ gán tay: `cong_viec.nhom_id`. Sản xuất chỉ gom nhóm LÚC PHÁT HÀNH, và cùng lượt đó
    `snapshot.dung_cong_viec:268` ghi `nhom_id=grp.id` xuống công việc; `dam_bao_nhom` gọi lẻ thì
    không đụng công việc, mà hồ sơ lại suy nhóm qua `cv.nhom_id`. Chép đúng giá trị production ghi
    thay vì tái phát hành cả lệnh (tái phát hành đẻ gói + phiên bản mới, làm nhiễu chính thứ các
    bài khác đang canh). Hệ quả: bài này KHÔNG canh đường gom nhóm lúc phát hành.
    """
    lsx = sess.get(Lsx, lsx_id)
    lsx2 = (
        sess.query(Lsx)
        .filter(Lsx.order_id == lsx.order_id, Lsx.id != lsx_id)
        .order_by(Lsx.id)
        .first()
    )
    assert lsx2 is not None, "đơn của `lenh_that` phải có lệnh anh em — xem `_hai_lsx_san_sang`"
    sess.get(OrderLine, lsx.order_line_id).nhom = nhan
    sess.get(OrderLine, lsx2.order_line_id).nhom = nhan
    lsx2.trang_thai = lsx.trang_thai
    # FLUSH bắt buộc: session test bật `autoflush=False`, mà `dam_bao_nhom` đọc nhãn nhóm bằng
    # `select` thô (`nguon_nhom_cua_lsx`). Không đẩy xuống trước thì lượt LSX đầu đọc nhãn CŨ
    # (None) ⇒ khoá vẫn là `line:<id>` ⇒ lệnh này ở lại nhóm cũ và bài test "2 dòng đơn" hoá
    # thành bài "1 dòng đơn" mà không báo gì.
    sess.flush()
    grp = nhom_svc.dam_bao_nhom(SanXuatRepository(sess), {lsx_id, lsx2.id})[lsx_id]
    sess.query(SanXuatCongViec).filter_by(lsx_id=lsx_id).update({"nhom_id": grp.id})
    sess.commit()
    sess.expire_all()
    return lsx2.id


def test_giao_hang_du_de_khoa_nut_va_dien_san(
    client, seed_credentials, sess, admin, lenh_that
):
    """Ô form giao hàng cần điền sẵn + con số KHOÁ nút, lấy từ MỘT hàm dùng chung ở service kho.

    Trần nằm ở TỪNG dòng `hang[]`: "đã vào kho của chính mặt hàng này − đã giao của đúng dòng đơn
    của nó", KHÔNG phải tổng đã vào kho. Giao lần hai mà vẫn bày trọn số cũ là mời người ta lập
    phiếu vượt số hàng có thật.

    Ca này là ca 1–1–1 (một dòng đơn · một mặt hàng) nên trần tính được: `khong_tinh_duoc=False`.
    """
    k, _hang = _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    _giao_xong(sess, lenh_that, 200, ma="YCGH-HS-1")

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["nhom_id"] is not None
    assert g["order_id"] == sess.get(Lsx, lenh_that).order_id
    assert g["so_lenh_trong_nhom"] == 1
    assert g["da_nhap_kho"] == 500.0
    assert g["da_giao"] == 200.0
    assert "so_toi_da" not in g, "trần cấp nhóm phải BỎ HẲN, không được để cạnh trần từng dòng"
    assert len(g["hang"]) == 1
    dong = g["hang"][0]
    assert dong["kho_id"] == k.id
    assert dong["kho_ten"] == "Kho thành phẩm KHO-HS-TP" == k.ten
    assert dong["ten"] == "Thành phẩm"
    assert dong["don_vi"] == "cái"
    assert dong["so_luong"] == 500.0, "`so_luong` là tồn thật, CHƯA trừ đã giao"
    assert dong["khong_tinh_duoc"] is False
    assert dong["so_toi_da"] == 300.0
    assert g["co_the_giao"] is True


def test_giao_hang_khoa_nut_khi_chua_co_ton(client, seed_credentials, lenh_that):
    """Chưa có gì vào kho ⇒ `hang` rỗng và `co_the_giao=False` — nút phải TẮT.

    Trả "tồn khả dụng = tổng đã nhận" khi chưa nối được số đã giao là mở nút cho một phiếu giao
    không có hàng; ở đây rỗng là câu trả lời đúng, không phải chỗ để đoán.
    """
    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["hang"] == []
    assert g["da_nhap_kho"] == 0.0
    assert g["co_the_giao"] is False


def test_giao_hang_nhom_nhieu_dong_don_khong_bia_tran(
    client, seed_credentials, sess, admin, lenh_that
):
    """Nhóm ôm HAI dòng đơn ⇒ không dựng được ánh xạ mặt hàng ⇄ dòng đơn ⇒ trần để TRỐNG.

    Đây là ca bản đầu tính sai: `Σ lot của nhóm − Σ đã giao của MỌI dòng đơn` = 500 − 400 = 100,
    trong khi kho còn 300 thật. Giao thêm một lượt nữa là `co_the_giao=False` vĩnh viễn trong khi
    hàng vẫn nằm đó. Registry thành phẩm neo NHÓM (`_tao_yc_tu_batch` tạo hàng với `lsx_id=None`)
    nên KHÔNG có cách nào biết lượt giao nào thuộc mặt hàng nào — câu đúng là "chưa biết", không
    phải một con số.

    Nút vẫn phải MỞ: hàng có thật trong kho, chỉ trần là chưa chắc.
    """
    lsx2 = _nhom_hai_lenh(sess, lenh_that)
    _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    _giao_xong(sess, lenh_that, 200, ma="YCGH-HS-2A")
    _giao_xong(sess, lsx2, 200, ma="YCGH-HS-2B")

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["so_lenh_trong_nhom"] == 2
    assert len(g["order_line_ids"]) == 2
    assert g["da_nhap_kho"] == 500.0
    assert g["da_giao"] == 400.0
    assert len(g["hang"]) == 1
    assert g["hang"][0]["khong_tinh_duoc"] is True
    assert g["hang"][0]["so_toi_da"] is None, "thà để trống còn hơn bày ra 100"
    assert g["hang"][0]["so_luong"] == 500.0
    assert g["co_the_giao"] is True, "kho còn hàng thật thì không được khoá nút"


def test_giao_hang_hai_mat_hang_khong_gop_tran(
    client, seed_credentials, sess, admin, lenh_that
):
    """Nhóm có HAI mặt hàng thành phẩm ⇒ mỗi dòng giữ tồn RIÊNG, không có số gộp nào.

    Bản đầu cộng mọi lot của nhóm bất kể `hang_id` rồi trả một trần chung: nhóm 500 + 70 ra trần
    570, tức cho phép lập phiếu 570 cái của món chỉ có 500. `don_vi_lech` không bắt được ca này —
    nó chỉ soi ĐƠN VỊ, còn đây là hai MẶT HÀNG cùng đơn vị.
    """
    cvs = _cvs(sess, lenh_that)
    _nhap_kho_that(sess, admin, lenh_that, cvs[0], so_luong=500)
    _nhap_kho_that(sess, admin, lenh_that, cvs[1], so_luong=70)

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["don_vi_lech"] is False
    theo_sl = sorted(d["so_luong"] for d in g["hang"])
    assert theo_sl == [70.0, 500.0], "hai mặt hàng phải là HAI dòng, không gộp"
    assert all(d["khong_tinh_duoc"] is True for d in g["hang"]), (
        "hai mặt hàng chia nhau một dòng đơn thì không tách được số đã giao"
    )
    assert 570.0 not in [d["so_luong"] for d in g["hang"]]


def test_kho_va_giao_hang_noi_ro_muc_gop(client, seed_credentials, sess, admin, lenh_that):
    """`so_lenh_trong_nhom` phải là SỐ THẬT lúc chạy, không phải cờ hằng.

    Bản đầu trả `kho.cap_nhom=True` cứng: đúng cả khi nhóm một lệnh (cộng thoải mái) lẫn khi nhóm
    ba lệnh (cộng là sai gấp ba), tức không mang thông tin nào. Khối `giao_hang` mang y hệt rủi ro
    gộp mà lại không có cờ nào.
    """
    d = _ho_so(client, seed_credentials, lenh_that)
    assert d["kho"]["so_lenh_trong_nhom"] == 1
    assert "cap_nhom" not in d["kho"]

    _nhom_hai_lenh(sess, lenh_that)
    d2 = _ho_so(client, seed_credentials, lenh_that)
    assert d2["kho"]["so_lenh_trong_nhom"] == 2
    assert d2["giao_hang"]["so_lenh_trong_nhom"] == 2


def test_giao_hang_da_giao_luon_la_so_cap_nhom(client, seed_credentials, sess, lenh_that):
    """Lệnh chưa vào nhóm nào ⇒ `giao_hang.da_giao = 0.0`, KHÔNG phải số của riêng dòng đơn lệnh.

    Bản đầu để hai nhánh của cùng một khoá mang hai nghĩa: có nhóm thì là số CẢ NHÓM, chưa có nhóm
    thì là số của DÒNG ĐƠN lệnh này. FE không có cách nào phân biệt. Số của riêng lệnh vẫn còn ở
    `tien_do.da_giao` nên không mất gì.
    """
    lsx_id = _lenh_tho(sess, ma="LSX-HS-GH0", sale_user_id=None)
    _giao_xong(sess, lsx_id, 120, ma="YCGH-HS-3")
    d = _ho_so(client, seed_credentials, lsx_id)
    assert d["giao_hang"]["nhom_id"] is None
    assert d["giao_hang"]["da_giao"] == 0.0
    assert d["giao_hang"]["so_lenh_trong_nhom"] == 0
    assert d["tien_do"]["da_giao"] == 120


# --- Luật 1–1–1 và quy ước trừ-dần: bốn nhánh KHÔNG bài nào chạm ------------------------------
# Vòng sửa 1 đẻ ra luật này; vòng sửa 2 mới đi canh từng nhánh của nó. Bốn thứ dưới đây đều đã bị
# bắn thủng mà cả bộ vẫn xanh: bộ lọc `nhom_id` của `thanh_vien_nhom`, điều kiện thứ ba
# `thieu_dong_don`, quy ước trừ dần theo `kho_id`, và `so_lenh_trong_nhom` vs số dòng đơn.
def _nhom_rieng_cho_lenh_anh_em(sess, lsx_id: int) -> int:
    """Dựng nhóm THỨ HAI tồn tại song song với nhóm của lệnh đang mở. Trả `nhom_id` mới.

    Lệnh anh em cùng đơn giữ nguyên `OrderLine.nhom = None` nên khoá của nó là `line:<id>` — khác
    khoá của lệnh đang mở ⇒ `dam_bao_nhom` đẻ nhóm mới thay vì gộp. Đây là mặc định của hệ (dòng
    đơn không dán nhãn thì mỗi dòng một nhóm), không phải ca dựng.
    """
    lsx = sess.get(Lsx, lsx_id)
    lsx2 = (
        sess.query(Lsx)
        .filter(Lsx.order_id == lsx.order_id, Lsx.id != lsx_id)
        .order_by(Lsx.id)
        .first()
    )
    lsx2.trang_thai = lsx.trang_thai
    sess.flush()
    grp2 = nhom_svc.dam_bao_nhom(SanXuatRepository(sess), {lsx2.id})[lsx2.id]
    sess.commit()
    sess.expire_all()
    return grp2.id


def _nhom_hai_lenh_chung_dong_don(sess, lsx_id: int) -> int:
    """Nhóm HAI lệnh nhưng CHỈ MỘT dòng đơn — hai lượt sản xuất cho cùng một dòng hàng.

    Khoá nhóm tính từ `(order_line_id, OrderLine.nhom)`, nên hai lệnh chung một dòng đơn rơi vào
    ĐÚNG nhóm sẵn có: không đẻ nhóm mới, không phải dời `cong_viec.nhom_id`. Đây là ca duy nhất
    tách được `so_lenh_trong_nhom` (2) khỏi số dòng đơn (1) — mọi fixture khác cho hai số bằng
    nhau, nên đổi cái này thành cái kia không ai kêu.
    """
    lsx = sess.get(Lsx, lsx_id)
    lsx2 = Lsx(
        ma=f"{lsx.ma}-L2", ten="Lượt sản xuất thứ hai", order_id=lsx.order_id,
        order_line_id=lsx.order_line_id, trang_thai=lsx.trang_thai,
        so_luong_dat=lsx.so_luong_dat,
    )
    sess.add(lsx2)
    sess.flush()
    nhom_svc.dam_bao_nhom(SanXuatRepository(sess), {lsx_id, lsx2.id})
    sess.commit()
    sess.expire_all()
    return lsx2.id


def test_giao_hang_khong_lan_sang_nhom_khac(
    client, seed_credentials, sess, admin, lenh_that
):
    """`thanh_vien_nhom` phải lọc theo `nhom_id`. Bỏ bộ lọc = sai CÂM toàn hệ.

    Không nhóm nào trong bộ bài cũ có hàng xóm, nên gỡ mệnh đề `where nhom_id` vẫn 29 bài xanh —
    trong khi trên DB thật hàm sẽ trả MỌI thành viên của MỌI nhóm: `so_lenh_trong_nhom` phình,
    `dong_don` gom cả đơn của khách khác, `mot_mot_mot` không bao giờ đúng nữa ⇒ hồ sơ nào cũng
    "chưa tính được trần". Đây là cầu DUY NHẤT từ hồ sơ sang giao hàng.

    Dựng hai nhóm cùng tồn tại rồi hỏi nhóm thứ nhất: mọi con số phải y như lúc chỉ có một nhóm.
    """
    nhom2 = _nhom_rieng_cho_lenh_anh_em(sess, lenh_that)
    _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    _giao_xong(sess, lenh_that, 200, ma="YCGH-HS-V3")

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["nhom_id"] != nhom2, "tiền đề: hai nhóm phải khác nhau thật"
    assert g["so_lenh_trong_nhom"] == 1, "thành viên nhóm HÀNG XÓM không được lọt vào"
    assert g["order_line_ids"] == [sess.get(Lsx, lenh_that).order_line_id]
    assert len(g["hang"]) == 1
    assert g["hang"][0]["so_toi_da"] == 300.0, "vẫn là ca 1–1–1, trần phải tính được"
    assert g["hang"][0]["khong_tinh_duoc"] is False


def test_giao_hang_thanh_vien_mat_dong_don_thi_khong_boi_tran(
    client, seed_credentials, sess, admin, lenh_that
):
    """Thành viên nhóm mất `order_line_id` ⇒ trần để TRỐNG, và KHÔNG được hoá thành dòng đơn `0`.

    Điều kiện thứ ba của luật 1–1–1 (`thieu_dong_don`) là nhánh không bài nào chạm: cả hai kiểu phá
    đều từng xanh — ép NULL thành `0` (đúng cái docstring `thanh_vien_nhom` cấm) và bỏ hẳn
    `not thieu_dong_don` (nhóm mất dòng đơn vẫn ra một con số trần).

    `SanXuatNhomLsx.order_line_id` là `nullable` + `ondelete="SET NULL"`, nên ca này đến từ DỮ LIỆU
    THẬT: dòng đơn bị xoá thì DB tự để lại thành viên trống. Fixture đặt NULL thẳng vì đó đúng là
    thứ DB ghi ra ở nhánh ấy.

    Nhóm ở đây có ĐÚNG MỘT dòng đơn còn sống và ĐÚNG MỘT mặt hàng — hai điều kiện kia đều thoả, nên
    chỉ mình `thieu_dong_don` giữ cho con số 300 không ra đời.
    """
    lsx2 = _nhom_hai_lenh(sess, lenh_that)
    sess.query(SanXuatNhomLsx).filter_by(lsx_id=lsx2).one().order_line_id = None
    sess.commit()
    _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    _giao_xong(sess, lenh_that, 200, ma="YCGH-HS-V1")

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["so_lenh_trong_nhom"] == 2
    assert g["order_line_ids"] == [sess.get(Lsx, lenh_that).order_line_id], (
        "thành viên thiếu dòng đơn phải BIẾN MẤT khỏi danh sách, không hoá thành dòng đơn 0"
    )
    assert len(g["hang"]) == 1
    assert g["hang"][0]["so_toi_da"] is None, "một thành viên mất dòng đơn đủ để trần thành ẩn số"
    assert g["hang"][0]["khong_tinh_duoc"] is True
    assert g["hang"][0]["so_luong"] == 500.0, "tồn thật vẫn phải bày ra"
    assert g["co_the_giao"] is True, "hàng còn trong kho thì không được tắt nút"


def test_giao_hang_mot_mat_hang_hai_kho_tru_dan_theo_kho(
    client, seed_credentials, sess, admin, lenh_that
):
    """Một mặt hàng nằm HAI kho: đã giao trừ dần theo `kho_id` tăng dần, ba lời hứa phải giữ.

    Quy ước này do hồ sơ đặt (số đã giao không mang thông tin kho) và docstring hứa ba điều: tổng
    trần đúng bằng trần thật của mặt hàng · không dòng nào vượt tồn của kho nó · không âm. Cả hai
    kiểu phá đều từng xanh: đảo thứ tự trừ, và bỏ `min` (cho ra trần ÂM).

    Bộ bài cũ không có đường nào chạm ca này vì `_nhap_kho_yc` đẻ mặt hàng MỚI mỗi lần gọi — phải
    chuyền `hang_id` để hai lượt nhập dùng chung một mặt hàng, đúng như `_get_or_create_hang` làm.

    Số: kho A 300 + kho B 400 = 700, đã giao 500 ⇒ A cạn (0), B còn 200. Σ = 200 = 700 − 500.
    """
    cvs = _cvs(sess, lenh_that)
    kho_a, hang_id = _nhap_kho_that(
        sess, admin, lenh_that, cvs[0], so_luong=300, kho_ma="KHO-HS-A")
    kho_b, hang_b = _nhap_kho_that(
        sess, admin, lenh_that, cvs[1], so_luong=400, kho_ma="KHO-HS-B", hang_id=hang_id)
    assert hang_b == hang_id, "tiền đề: HAI kho nhưng MỘT mặt hàng"
    assert kho_a.id < kho_b.id, "tiền đề: kho A có id nhỏ hơn nên bị trừ trước"
    _giao_xong(sess, lenh_that, 500, ma="YCGH-HS-2KHO")

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    hang = g["hang"]
    assert len(hang) == 2, "hai kho là hai dòng phiếu riêng, không gộp"
    assert [d["kho_id"] for d in hang] == [kho_a.id, kho_b.id]
    assert [d["so_luong"] for d in hang] == [300.0, 400.0]
    assert [d["so_toi_da"] for d in hang] == [0.0, 200.0], "trừ theo kho_id TĂNG DẦN"
    assert sum(d["so_toi_da"] for d in hang) == 200.0 == g["da_nhap_kho"] - g["da_giao"]
    assert all(d["so_toi_da"] >= 0 for d in hang), "trần âm là số vô nghĩa, `min` giữ chỗ này"
    assert all(d["so_toi_da"] <= d["so_luong"] for d in hang), "không dòng nào vượt tồn kho của nó"
    assert g["da_nhap_kho"] == 700.0
    assert g["da_giao"] == 500.0
    assert g["co_the_giao"] is True


def test_so_lenh_trong_nhom_khong_phai_so_dong_don(
    client, seed_credentials, sess, admin, lenh_that
):
    """`so_lenh_trong_nhom` đếm LỆNH, không đếm dòng đơn — hai số trùng nhau ở mọi fixture khác.

    Trường này sinh ra để FE quyết "có cộng qua các lệnh hay không", nên lấy nhầm số dòng đơn là
    trả lời sai đúng câu hỏi nó được đẻ ra để trả lời. Ca tách được hai số: hai lượt sản xuất cho
    CÙNG một dòng đơn.
    """
    _nhom_hai_lenh_chung_dong_don(sess, lenh_that)
    _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    _giao_xong(sess, lenh_that, 200, ma="YCGH-HS-1DONG")

    d = _ho_so(client, seed_credentials, lenh_that)
    g = d["giao_hang"]
    assert g["order_line_ids"] == [sess.get(Lsx, lenh_that).order_line_id], "đúng MỘT dòng đơn"
    assert g["so_lenh_trong_nhom"] == 2, "nhưng HAI lệnh — không được lấy số dòng đơn thay vào"
    assert d["kho"]["so_lenh_trong_nhom"] == 2
    assert g["hang"][0]["so_toi_da"] == 300.0, "1 dòng đơn + 1 mặt hàng ⇒ trần vẫn tính được"


def test_lot_kho_chua_xac_nhan_khong_vao_ton(
    client, seed_credentials, sess, admin, lenh_that
):
    """Lot thành phẩm CHƯA được thủ kho xác nhận thì KHÔNG phải hàng khả dụng.

    Luật đứng riêng một gạch đầu dòng trong docstring `ton_kha_dung_thanh_pham`: yêu cầu nhập kho
    là lời của KCS, hàng vẫn nằm ở tổ cho tới lúc kho bấm nhận. Gỡ điều kiện `kho_xac_nhan` vẫn 29
    bài xanh, nên luật đó không có lưới nào.

    ⚠️ HÔM NAY production KHÔNG ghi ra hình dạng này: `kho_xac_nhan_nhap:293` đẻ lot thành phẩm
    luôn với `kho_xac_nhan=True`, còn lot chờ xác nhận chỉ có ở BTP (`phan_loai_btp:431`) mà BTP đã
    bị điều kiện `loai_hang` loại từ trước. Tức đây là một CHỐT PHÒNG THỦ, và bài này ghim chốt đó:
    ngày nào có đường ghi lot thành phẩm chờ kho nhận (nhập kho hai bước, chuyển kho…) thì luật đã
    sẵn lưới. Fixture đặt cờ thẳng vì không đường ghi nào đặt nó.
    """
    _kho, hang_id = _nhap_kho_that(sess, admin, lenh_that, _cvs(sess, lenh_that)[0], so_luong=500)
    lots = sess.query(SanXuatKhoLot).filter_by(hang_id=hang_id).all()
    assert len(lots) == 1, "tiền đề: đúng một lot vừa được kho xác nhận"
    assert lots[0].kho_xac_nhan is True
    lots[0].kho_xac_nhan = False
    sess.commit()

    g = _ho_so(client, seed_credentials, lenh_that)["giao_hang"]
    assert g["hang"] == [], "hàng chưa được kho nhận thì không có gì để điền vào phiếu"
    assert g["da_nhap_kho"] == 0.0
    assert g["co_the_giao"] is False


def test_vat_tu_khong_lan_sang_bai_ghep_khac(
    client, seed_credentials, sess, orders, lsx_svc, admin, customer, ghep_doi
):
    """Lệnh của bài A không được ăn dòng vật tư của bài B.

    `_vat_tu` chiếu hai chiều: theo lệnh (`lsx_id`) và theo BÀI của chính lệnh (`bai_ghep_id`).
    Chiều theo lệnh có bài canh từ vòng đầu; chiều theo bài thì không — gỡ nó vẫn 29 bài xanh, vì
    mọi fixture chỉ có ĐÚNG một bài ghép tồn tại. Trên kế hoạch thật lúc nào cũng nhiều bài, và
    giấy của bài người khác hiện trong hồ sơ lệnh mình là con số không ai giải thích nổi.

    Khai vật tư cho CẢ HAI bài: bài A để chứng minh chiều đúng vẫn chạy (không phải bài rỗng vô
    nghĩa), bài B để chứng minh chiều sai bị chặn.
    """
    lsx_a, _lsx_b, cv_chung_a = ghep_doi
    _lsx_c, _lsx_d, cv_chung_b = _lenh_ghep_doi(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 500), ("In", 5000), ("Đóng gói", 5000)], ghep_idx=1,
    )
    assert cv_chung_a.bai_ghep_id != cv_chung_b.bai_ghep_id, "tiền đề: HAI bài ghép khác nhau"

    for cv, ma, ten in (
        (cv_chung_a, "VT-BAI-A", "Mực bài A"), (cv_chung_b, "VT-BAI-B", "Mực bài B"),
    ):
        vt = _vat_tu_moi(sess, ma=ma, ten=ten)
        sess.add(BaiGhepCongDoanVatTu(
            bai_ghep_cong_doan_id=cv.bai_ghep_cong_doan_id, vat_tu_id=vt.id,
            vat_tu_ma_snapshot=vt.ma, vat_tu_ten_snapshot=vt.ten,
            don_vi_snapshot=vt.don_vi_gia, so_luong=12, thu_tu=0,
        ))
    sess.commit()

    vt_khoi = _ho_so(client, seed_credentials, lsx_a)["vat_tu"]
    moi_dong = vt_khoi["hien_tai"]["dong"] + vt_khoi["canh_bao_sau"] + vt_khoi["da_cap"]
    ma_hang = {d["hang_ma"] for d in moi_dong}
    assert "VT-BAI-A" in ma_hang, "vật tư của CHÍNH bài mình phải có — nếu không bài này vô nghĩa"
    assert "VT-BAI-B" not in ma_hang, "vật tư của bài KHÁC không được lọt vào hồ sơ lệnh này"


# --- Bốn khối chỉ được canh "có khoá", chưa canh CON SỐ ------------------------------------------
# Phá thẳng vào code sản xuất ở bốn khối dưới đây mà cả bộ test vẫn XANH: `du` ép True, `ty_le_dat`
# ép 0.0, tổng `san_luong` ép 0, `bo_qua` ép rỗng, `khach_hang` ép None. Nguyên nhân giống nhau:
# `test_du_cac_khoi` chỉ soi TÊN KHOÁ, còn giá trị thì không bài nào nhìn. Sáu bài dưới đây canh
# GIÁ TRỊ, và mỗi bài nói rõ con số sai nào nó chặn.
def _ghi_san_luong(sess, admin, cv, *, tong, tot, hong=0, nhom_loi_id=None, ma="NV-HS-SL") -> None:
    """Ghi MỘT batch sản lượng bằng ĐÚNG đường production (`san_luong.tao_batch`).

    Bước phải ĐANG CHẠY mới ghi được (`_TRANG_THAI_GHI_DUOC`), nên mở ba cửa của `thuc_thi.bat_dau`
    y như `_chay_that` — nhưng KHÔNG kết thúc bước, vì bài cần bước còn mở để ghi tiếp batch sau.
    """
    to = sess.get(Department, cv.department_id)
    to.has_piece_work = True
    sess.commit()
    if not sess.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id).count():
        _giao_nguoi(sess, admin, cv, ma=ma, ten="Thợ sản lượng")
        thuc_thi.bat_dau(
            sess, user=admin, cong_viec_id=cv.id,
            ly_do_tre="Chờ giấy về", ly_do_so_nguoi="Tổ thiếu người",
        )
    san_luong_svc.tao_batch(
        sess, user=admin, cong_viec_id=cv.id,
        bat_dau=datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc),
        ket_thuc=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        tong=tong, tot=tot, hong=hong, nhom_loi_id=nhom_loi_id,
    )
    sess.expire_all()


def test_vat_tu_hien_tai_thieu_thi_du_phai_FALSE(client, seed_credentials, sess, lenh_that):
    """Nhánh FALSE của `vat_tu.hien_tai.du` — nhánh mà cả bộ test trước đó KHÔNG bài nào chạm.

    Bài anh em `test_vat_tu_hai_muc` chỉ canh nhánh True, nên ép `du = True` cứng trong
    `ho_so._vat_tu` vẫn xanh cả bộ. `du` là thứ quyết định tổ trưởng có bấm "Bắt đầu" hay không:
    nói "đủ" khi kho trống là đẩy cả tổ vào ca chạy rồi mới phát hiện thiếu giấy.

    Vật tư khai ở bước ĐẦU (CTP) và lệnh chưa chạy gì nên bước đó chính là bước hiện tại; món vừa
    tạo không có lô nào ⇒ dòng `do` ⇒ `du` phải FALSE.
    """
    _khai_vat_tu_buoc(
        sess, _buoc_cua(sess, lenh_that)[0],
        _vat_tu_moi(sess, ma="VT-HS-BAN", ten="Bản kẽm"), 8,
    )
    vt = _ho_so(client, seed_credentials, lenh_that)["vat_tu"]
    assert vt["hien_tai"]["du"] is False
    # `ma` của dòng cân đối là mã LỆNH/BÀI (nguồn nhu cầu), mã mặt hàng nằm ở `hang_ma`.
    thieu = [d for d in vt["hien_tai"]["dong"] if d["hang_ma"] == "VT-HS-BAN"]
    assert len(thieu) == 1, "dòng thiếu phải nằm ở mức HIỆN TẠI, không bị đẩy xuống cảnh báo sau"
    assert thieu[0]["trang_thai"] == "do"
    assert thieu[0]["nhu_cau"] == 8
    assert thieu[0]["ma"] == _ho_so(client, seed_credentials, lenh_that)["thong_tin"]["ma"]


def test_kcs_ty_le_dat_tinh_theo_so_khong_phai_trung_binh(
    client, seed_credentials, sess, lenh_that
):
    """`ty_le_dat` = Σđạt/Σnhận, và `None` (KHÔNG phải 0.0) khi chưa kiểm cái nào.

    Ép `ty_le_dat = 0.0` trong `_kcs` mà cả bộ vẫn xanh: chưa bài nào đọc con số. Hai lỗi mà bài
    này chặn: (1) "0% đạt" lúc chưa kiểm gì — một lời báo động sai đủ để dừng cả chuyền;
    (2) trung bình cộng các batch — batch 10 cái và batch 10.000 cái không cân nhau, ở đây
    50/100 và 950/1000 cho 90.9% theo số nhưng 72.5% nếu cộng-rồi-chia-đôi.
    """
    assert _ho_so(client, seed_credentials, lenh_that)["kcs"]["ty_le_dat"] is None

    cvs = _cvs(sess, lenh_that)
    _kcs_batch(sess, cvs[0].id, nhan=100, dat=50, khong_dat=50, ket_luan="khong_dat")
    _kcs_batch(sess, cvs[1].id, nhan=1000, dat=950, khong_dat=50, ket_luan="dat")

    k = _ho_so(client, seed_credentials, lenh_that)["kcs"]
    assert k["tong_nhan"] == 1100.0
    assert k["tong_dat"] == 1000.0
    assert k["tong_khong_dat"] == 100.0
    assert round(k["ty_le_dat"], 2) == 90.91, "theo SỐ, không phải trung bình cộng batch (72.5)"
    assert len(k["batch"]) == 2


def test_san_luong_cong_don_moi_batch(client, seed_credentials, sess, admin, lenh_that):
    """Tổng `san_luong` phải CỘNG mọi batch, và `hong` phải ra số thật.

    Ép cả ba tổng về 0 mà bộ test cũ vẫn xanh. Đây là số nuôi phần trăm tiến độ và số vào kho, nên
    trả 0 lúc xưởng đã chạy 500 tờ là hồ sơ nói dối đúng chỗ đau nhất. Hai batch trên CÙNG một bước
    để bắt luôn kiểu "gán = batch cuối" thay vì "+=".
    """
    loi = SanXuatLyDo(ma="LOI-HS-1", nhom=NHOM_LOI, ten="Nhăn giấy")
    sess.add(loi)
    sess.commit()
    cv = _cvs(sess, lenh_that)[0]
    _ghi_san_luong(sess, admin, cv, tong=300, tot=300)
    _ghi_san_luong(sess, admin, cv, tong=200, tot=180, hong=20, nhom_loi_id=loi.id)

    sl = _ho_so(client, seed_credentials, lenh_that)["san_luong"]
    assert sl["tong"] == 500.0, "cộng dồn, không phải lấy batch cuối (200)"
    assert sl["tot"] == 480.0
    assert sl["hong"] == 20.0
    assert len(sl["batch"]) == 2
    assert [b["tong"] for b in sl["batch"]] == [300.0, 200.0], "sắp theo mốc kết thúc"
    assert sl["batch"][1]["mo_ta_loi"] is None
    assert all(b["la_buoc_ghep"] is False for b in sl["batch"])


def test_bo_qua_nhan_dong_bai_ghep(client, seed_credentials, sess, ghep_doi):
    """`bo_qua` phải nhận cả dòng mang mã BÀI GHÉP, không riêng mã lệnh.

    Engine vật tư ghi dòng bỏ qua của bài ghép dưới `bg.ma` (`ke_hoach_vat_tu_service:995`), nên bộ
    lọc `r["ma"] == ma_lenh` làm lệnh nằm trong bài ghép thấy `bo_qua` RỖNG — im lặng bỏ sót đúng
    thứ mà khối này sinh ra để nói. Lệnh ở đây chưa khai giấy nên bài ghép không đối chiếu được,
    engine bỏ qua nó và ghi lý do.
    """
    lsx_a, _lsx_b, _cv_chung = ghep_doi
    vt = _ho_so(client, seed_credentials, lsx_a)["vat_tu"]
    assert vt["bo_qua"], "dòng bỏ qua mang mã bài ghép phải lọt qua bộ lọc"
    assert any("GB" in (r.get("ma") or "") for r in vt["bo_qua"]), (
        "phải là dòng của BÀI GHÉP (mã bắt đầu bằng GB), không phải dòng của lệnh"
    )


def test_thong_tin_ra_dung_ten_khach_va_nguoi_ban(client, seed_credentials, lenh_that):
    """Danh tính lệnh phải ra TÊN THẬT, không phải `None` im lặng.

    Ép `khach_hang = None` mà bộ test cũ vẫn xanh — `test_du_cac_khoi` chỉ soi tên khối. Tên khách
    là thứ đầu tiên người dùng đối chiếu khi mở hồ sơ; để trống thì họ không biết đang xem lệnh của
    ai, mà cũng không có gì báo là đã hỏng.
    """
    t = _ho_so(client, seed_credentials, lenh_that)["thong_tin"]
    assert t["khach_hang"] == "Khách Danh Sách"
    assert t["khach_hang_id"] is not None
    assert t["ma"].startswith("LSX")
    assert t["so_luong_dat"] > 0
    assert t["order_no"]


# --- Khoảng hụt 7: routing vẽ được nhánh SONG SONG ---------------------------------------------
def test_routing_ve_duoc_nhanh_song_song(
    client, seed_credentials, sess, orders, lsx_svc, admin, customer
):
    """Hai bước KHÔNG phụ thuộc nhau phải nằm cùng một LỚP — nếu không màn hồ sơ vẽ chuỗi thẳng.

    Routing nhà in có nhánh thật: bìa và ruột chạy song song rồi gặp nhau ở khâu vào bìa. Chỉ trả
    `nodes` theo `thu_tu` là bày một chuỗi tuần tự KHÔNG tồn tại, và người đọc kết luận sai về việc
    gì đang chặn việc gì. Cạnh phải đủ để dựng lại đồ thị, không chỉ để tô màu.
    """
    _dot_dong_don(sess, 5)
    lsx_id = _phat_hanh_that(
        sess, orders, lsx_svc, admin, customer,
        buoc=[("CTP", 15, 500), ("In bìa", 120, 500), ("In ruột", 120, 500),
              ("Vào bìa", 60, 500)],
        canh=[(0, 1), (0, 2), (1, 3), (2, 3)],
    )
    r = _ho_so(client, seed_credentials, lsx_id)["routing"]
    theo_ten = {n["ten"]: n for n in r["nodes"]}
    assert set(theo_ten) == {"CTP", "In bìa", "In ruột", "Vào bìa"}
    assert theo_ten["CTP"]["lop"] == 0
    assert theo_ten["In bìa"]["lop"] == theo_ten["In ruột"]["lop"] == 1
    assert theo_ten["Vào bìa"]["lop"] == 2
    assert set(theo_ten["Vào bìa"]["phu_thuoc"]) == {
        theo_ten["In bìa"]["id"], theo_ten["In ruột"]["id"]
    }
    canh = {(a, b) for a, b in r["canh"]}
    assert (theo_ten["CTP"]["id"], theo_ten["In ruột"]["id"]) in canh
    assert len(canh) == 4


# --- Bài ghép: bước NẶNG NHẤT của lệnh nằm ở công việc CHUNG ------------------------------------
def test_buoc_ghep_co_mat_trong_routing(client, seed_credentials, ghep_doi):
    """Bước bị bài ghép phủ KHÔNG đẻ công việc riêng — hồ sơ phải lấy nó qua cầu ghép.

    Bỏ sót là hồ sơ hiện "In" ở trạng thái chưa bắt đầu trong khi ca in ghép đang chạy.
    """
    lsx_a, _lsx_b, cv_chung = ghep_doi
    theo_ten = {
        n["ten"]: n for n in _ho_so(client, seed_credentials, lsx_a)["routing"]["nodes"]
    }
    assert theo_ten["In"]["cong_viec_id"] == cv_chung.id
    assert theo_ten["In"]["la_buoc_ghep"] is True
    assert theo_ten["CTP"]["la_buoc_ghep"] is False


# --- `chi_khoi`: xin ít khối hơn, KHÔNG phải đọc bằng đường khác --------------------------------
_KHOI_PHIEU = {"thong_tin", "thong_so", "routing", "phien_ban"}


def _dem_sql(fn):
    """Chạy `fn()` và đếm SỐ CÂU SQL thật đi qua engine — cùng khuôn
    `test_kho_de_nghi.test_api_danh_sach_yeu_cau_sinh_tu_sx_khong_n_plus_1`.

    Đếm câu SQL chứ không đếm lượt gọi hàm: "gọi engine vật tư một lần" và "engine ấy chạy 40 câu"
    là hai chuyện khác nhau, mà cái phải bỏ là chuyện thứ hai.
    """
    from sqlalchemy import event

    from app.db import engine

    cau: list[str] = []

    def ghi(_conn, _cur, sql, *_a):
        cau.append(sql)

    event.listen(engine, "before_cursor_execute", ghi)
    try:
        ket_qua = fn()
    finally:
        event.remove(engine, "before_cursor_execute", ghi)
    return ket_qua, len(cau)


def test_chi_khoi_tra_dung_khoi_duoc_xin_va_giong_het_ban_day_du(sess, lenh_that):
    """Phiếu công nghệ chỉ in 4 khối, nhưng phải đi ĐÚNG cửa quyền của hồ sơ.

    `chi_khoi` là đường giải: hàm dựng ít khối hơn, KHÔNG phải nơi gọi tự viết truy vấn thứ hai
    (đường đọc thứ hai = hai chỗ phải nhớ luật 404/403 và hai chỗ có thể SELECT nhầm cột tiền).

    Bài chốt hai điều: (a) trả ĐÚNG những khoá được xin, không thừa không thiếu; (b) nội dung
    từng khối GIỐNG HỆT bản đầy đủ — "nhanh hơn nhưng khác số" là hỏng chứ không phải tối ưu.
    """
    from app.services.lenh_sx import ho_so as ho_so_svc

    du = ho_so_svc.ho_so(sess, lenh_that, sale_ids=None)
    it = ho_so_svc.ho_so(sess, lenh_that, sale_ids=None, chi_khoi=_KHOI_PHIEU)

    assert set(it) == _KHOI_PHIEU
    assert set(du) == set(ho_so_svc.KHOI)
    for k in _KHOI_PHIEU:
        assert it[k] == du[k], f"khối {k} khác nhau giữa bản đầy đủ và bản `chi_khoi`"


def test_chi_khoi_bot_cau_sql_that(sess, lenh_that):
    """ĐO chứ không đoán: bản 4 khối phải chạm DB ÍT HƠN HẲN bản đầy đủ.

    Đo thật (probe tạm dùng chính `_dem_sql` + chính fixture này):
      · `lenh_that`, DB không có bài ghép : **70 câu** đầy đủ  ->  **25 câu** cho 4 khối
      · `ghep_doi`,  DB có 1 bài ghép     : **101 câu** đầy đủ ->  **25 câu** cho 4 khối
    Con số 4 khối KHÔNG đổi theo bài ghép — đúng chỗ phải bỏ, vì phần phình chính là
    `trang_thai.den_va_bang` → `ke_hoach_vat_tu_service.can_doi()`
    — hàm phình theo số bài ghép trong TOÀN kế hoạch chứ không theo lệnh đang in — cộng
    `_giao_hang` · `_kcs` · `_su_co` · `_timeline` · `_nhan_luc`.

    Vì sao đây không phải bài "chạy nhanh hơn": cái phải bỏ là sự GIÒN. Engine vật tư hoặc khối
    giao hàng ném lỗi vì một trạng thái dữ liệu chẳng liên quan gì tới tờ giấy thì nút In chết
    theo, trong khi tổ trưởng đang đứng chờ.

    Assert theo TỈ LỆ chứ không chốt cứng 70/25: con số tuyệt đối trôi theo mọi thay đổi của
    `boi_canh`, chốt cứng là bài đỏ vì lý do không liên quan. Nhưng "ít hơn một nửa" thì chỉ đỏ
    khi `chi_khoi` thật sự thành vô nghĩa.
    """
    from app.services.lenh_sx import ho_so as ho_so_svc

    _, so_du = _dem_sql(lambda: ho_so_svc.ho_so(sess, lenh_that, sale_ids=None))
    _, so_it = _dem_sql(
        lambda: ho_so_svc.ho_so(sess, lenh_that, sale_ids=None, chi_khoi=_KHOI_PHIEU)
    )
    assert so_it * 2 < so_du, f"đầy đủ {so_du} câu · 4 khối {so_it} câu — `chi_khoi` không bớt gì"


def test_chi_khoi_khoa_la_bao_loi_ngay(sess, lenh_that):
    """Gõ sai tên khối mà im lặng thì nơi gọi nhận dict THIẾU khoá và nổ ở chỗ khác, xa nguyên
    nhân — `KeyError: 'routing'` giữa lúc dựng PDF không nói được gì về cái typo."""
    from app.services.lenh_sx import ho_so as ho_so_svc

    with pytest.raises(ValueError, match="chi_khoi"):
        ho_so_svc.ho_so(sess, lenh_that, sale_ids=None, chi_khoi={"routing", "khoi_khong_co"})
