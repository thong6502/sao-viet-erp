"""Bước NGOÀI dòng giấy: ĐƠN VỊ + SỐ do kế hoạch khai thẳng tại lệnh (10/09/2026).

Ghi kẽm CTP không chạm tờ giấy nào nên nó đứng ngoài chuỗi bù hao — số của nó không suy được từ
số hàng khách đặt. Trước hôm nay chỉ có MỘT nguồn: `cong_doan.cong_thuc_san_luong` ở danh mục, tức
một con số dùng chung cho mọi lệnh chạy công đoạn đó. Nhưng số bản kẽm đổi theo số màu / số mặt /
số bài của TỪNG đơn, lại còn ca cá biệt (kẽm hỏng ghi lại 2 bản, khách sửa 1 màu, ghép chung bài
nên chỉ gánh một nửa) — không công thức chung nào nói hộ, mà sửa danh mục là đè lên mọi lệnh khác.

Nên drawer mở hai ô đơn vị + hai ô số cho đúng những bước ấy. Bài này soi CÁI GIÁ của việc mở:

  ① khai đủ cặp đơn vị ⇒ số của người khai THẮNG công thức danh mục, và bước hết đòi cầu quy đổi;
  ② xoá một ô đơn vị ⇒ bước trả ngay về cho danh mục (không cần cột cờ nào để gỡ);
  ③ số khai tay đi tới THẺ VIỆC của tổ, đúng cả đơn vị;
  ④ nửa cặp KHÔNG phải lời khai — bước tự thêm vẫn nối chuỗi giấy như cũ (hồi quy);
  ⑤ bước TRÊN dòng giấy gửi số lên vẫn bị chuỗi ngược ghi đè — mở cửa này không được thủng dòng giấy.
"""
from __future__ import annotations

from app.models.lsx import LB_MAY, LsxCongDoan
from app.models.san_xuat import SanXuatCongViec
from app.schemas.lsx import LsxCongDoanIn
from app.services.san_xuat import release

# Fixtures + helper luồng thật (đơn → lệnh → sẵn sàng → công đoạn ghi kẽm).
from tests.test_san_xuat_buoc_ngoai_dong import (  # noqa: F401
    _cd_ghi_kem,
    _to_ky_thuat,
)
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _in_step,
    _nha_cho,
    admin,
    bg_svc,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)


def _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, *, to_id):
    """Lệnh 4 bản kẽm theo công thức danh mục, có bước Ghi kẽm CTP đứng ĐẦU routing.

    Cố ý để danh mục CÓ `cong_thuc_san_luong` — nếu không thì "khai tay thắng công thức" không có
    gì để thắng, bài sẽ xanh cả khi luật chưa chạy.
    """
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    # Fixture chung giữ chỗ vật tư sẵn, mà giữ chỗ thì `replace_routing` chặn cứng (đúng luật).
    # Bài này soi ô số của bước chứ không soi cửa chặn ấy nên nhả chỗ ra — tương đương thao tác
    # "nhả chỗ ở màn Kế hoạch vật tư" mà chính câu báo lỗi chỉ đường tới.
    a.giu_cho_bat = False
    a.quy_cach_json = {**(a.quy_cach_json or {}), "so_kem": 4}
    cd = _cd_ghi_kem(db)
    dau = min(c.thu_tu or 0 for c in a.cong_doans)
    buoc = LsxCongDoan(
        lsx_id=a.id, thu_tu=dau - 1, ten="Ghi kẽm CTP", nhom="prepress", loai_buoc=LB_MAY,
        department_id=to_id, cong_doan_id=cd.id,
    )
    db.add(buoc)
    db.flush()
    db.expire(a, ["cong_doans"])
    lsx_svc._ap_chuoi_nguoc(a)
    db.commit()
    return a, buoc.step_key


def _rows(lsx, **doi_theo_key) -> list[LsxCongDoanIn]:
    """Payload REPLACE-ALL y như bảng routing gửi lên: mọi bước đang có, sửa vài ô theo `step_key`."""
    out = []
    for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu):
        d = dict(
            step_key=cd.step_key, cong_doan_id=cd.cong_doan_id, ten=cd.ten, nhom=cd.nhom,
            loai_buoc=cd.loai_buoc, department_id=cd.department_id, may_id=cd.may_id,
            so_luong_vao=float(cd.so_luong_vao or 0), so_luong_ra=float(cd.so_luong_ra or 0),
            don_vi_vao=cd.don_vi_vao or "", don_vi_ra=cd.don_vi_ra or "",
        )
        d.update(doi_theo_key.get(cd.step_key, {}))
        out.append(LsxCongDoanIn(**d))
    return out


def _buoc(lsx, step_key) -> LsxCongDoan:
    return next(c for c in lsx.cong_doans if c.step_key == step_key)


# --- ① Khai đủ cặp: số của người khai thắng công thức danh mục -------------------------------
def test_khai_du_cap_don_vi_thi_so_go_tay_thang_cong_thuc(
    db, orders, lsx_svc, admin, customer
):
    to = _to_ky_thuat(db, admin)
    a, key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    # Trước khi khai: công thức danh mục cầm trịch (`so_kem` = 4).
    assert float(_buoc(a, key).so_luong_ra) == 4

    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{key: dict(don_vi_vao="bai", don_vi_ra="kem", so_luong_vao=1, so_luong_ra=6)}))
    b = _buoc(lsx_svc.get(a.id), key)
    assert (b.don_vi_vao, b.don_vi_ra) == ("bai", "kem")
    assert (float(b.so_luong_vao), float(b.so_luong_ra)) == (1.0, 6.0)

    # Lưu LẦN NỮA (không đổi gì) — đây đúng chỗ bản cũ nuốt số: `_ap_chuoi_nguoc` chạy ở MỌI cửa
    # làm số đổi, nên "giữ được lúc lưu" chưa chứng minh được gì nếu lần lưu sau kéo lại danh mục.
    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(lsx_svc.get(a.id)))
    b = _buoc(lsx_svc.get(a.id), key)
    assert (float(b.so_luong_vao), float(b.so_luong_ra)) == (1.0, 6.0)


def test_khai_tay_thi_thoi_doi_cau_quy_doi_va_thoi_bay_dien_giai(
    db, orders, lsx_svc, admin, customer
):
    """Hai đầu đều là số người ta gõ ⇒ chẳng có phép đổi nào phải bắc cầu, cũng chẳng có công thức
    nào để diễn giải. Bản đầu bày cả hai: banner đỏ "chưa khai cầu bài→kẽm" chặn phát hành cho một
    việc máy không hề cần làm, và câu "Số bản kẽm = 4 bản kẽm" nằm ngay dưới cái pill ghi 6."""
    to = _to_ky_thuat(db, admin)
    a, key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{key: dict(don_vi_vao="bai", don_vi_ra="kem", so_luong_vao=1, so_luong_ra=6)}))

    chi_tiet = lsx_svc.detail_dict(lsx_svc.get(a.id))
    hang = next(c for c in chi_tiet["cong_doans"] if c["step_key"] == key)
    assert hang["tren_dong_giay"] is False
    assert hang["loi_quy_doi"] is None
    assert hang["san_luong_dien_giai"] is None
    assert hang["so_luong_ra"] == 6


# --- ② Gỡ khai tay: xoá một ô đơn vị là xong --------------------------------------------------
def test_xoa_mot_o_don_vi_tra_buoc_ve_cho_danh_muc(db, orders, lsx_svc, admin, customer):
    to = _to_ky_thuat(db, admin)
    a, key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{key: dict(don_vi_vao="bai", don_vi_ra="kem", so_luong_vao=1, so_luong_ra=6)}))

    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        lsx_svc.get(a.id), **{key: dict(don_vi_ra="")}))
    b = _buoc(lsx_svc.get(a.id), key)
    assert (b.don_vi_vao, b.don_vi_ra) == (None, None)
    assert float(b.so_luong_ra) == 4        # công thức `so_kem` cầm trịch trở lại


# --- ③ Số khai tay đi tới thẻ việc của tổ ------------------------------------------------------
def test_so_khai_tay_xuong_the_viec_cua_to(db, orders, lsx_svc, admin, customer):
    to = _to_ky_thuat(db, admin)
    a, key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{key: dict(don_vi_vao="bai", don_vi_ra="kem", so_luong_vao=1, so_luong_ra=6)}))

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()
    cv = db.query(SanXuatCongViec).filter_by(goi_id=goi.id, step_key=key).one()
    assert (cv.don_vi_vao, cv.don_vi_ra) == ("bai", "kem")
    assert (float(cv.so_luong_vao), float(cv.so_luong_ra)) == (1.0, 6.0)
    assert cv.dinh_muc_json["ngoai_dong"] is True


# --- ④⑤ Hai chỗ KHÔNG được xê dịch ------------------------------------------------------------
def test_nua_cap_don_vi_khong_phai_loi_khai(db, orders, lsx_svc, admin, customer):
    """Bước tự thêm giữa chuỗi vốn chỉ mang `don_vi_vao` rồi để lượt kế thừa nối vế RA. Nhận nửa
    cặp là bước ấy đứng lại ngoài dòng giấy và hao của nó biến mất khỏi số giấy phải mua, im lặng."""
    to = _to_ky_thuat(db, admin)
    a, key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{key: dict(don_vi_vao="bai", don_vi_ra="", so_luong_ra=6)}))
    b = _buoc(lsx_svc.get(a.id), key)
    assert (b.don_vi_vao, b.don_vi_ra) == (None, None)     # kế thừa danh mục: ngoài dòng, để trống
    assert float(b.so_luong_ra) == 4


def test_buoc_tren_dong_giay_van_bi_chuoi_nguoc_ghi_de(db, orders, lsx_svc, admin, customer):
    to = _to_ky_thuat(db, admin)
    a, _key = _lenh_co_ghi_kem(db, orders, lsx_svc, admin, customer, to_id=to.id)
    in_key = _in_step(db, a.id).step_key
    vao_that = float(_buoc(a, in_key).so_luong_vao)

    lsx_svc.replace_routing(lsx_id=a.id, actor=admin, rows_in=_rows(
        a, **{in_key: dict(so_luong_vao=99, so_luong_ra=99, don_vi_vao="kem", don_vi_ra="kem")}))
    b = _buoc(lsx_svc.get(a.id), in_key)
    assert (b.don_vi_vao, b.don_vi_ra) == ("to", "to")
    assert float(b.so_luong_vao) == vao_that
