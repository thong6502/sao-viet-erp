"""Nội quy công ty — Giám đốc soạn NHIỀU TÀI LIỆU, MỌI nhân viên đọc (chủ 30/07/2026).

Bộ nội quy một nhà máy là nhiều văn bản (Nội quy lao động, Quy chế lương thưởng, An toàn lao
động…). Mỗi tài liệu có TIÊU ĐỀ riêng và CHUỖI VERSION riêng — ban hành từng cái độc lập.

Bốn thứ hỏng thì đau, mỗi thứ có test riêng canh:

1. **Nhân viên thường phải ĐỌC được** `/documents` và `/documents/{id}/current`. Đó là chính yêu
   cầu. Gác nhầm ô quyền vào hai đường đó là cả công ty mở màn nội quy ra thấy cột phải TRỐNG —
   không còn đường nào tới nội dung, và không ai phát hiện cho tới khi có người hỏi.
2. **Hai tài liệu không được lẫn vào nhau.** Nháp riêng, bản hiệu lực riêng, lịch sử riêng, ngày
   ban hành riêng. Lẫn thì hỏng theo kiểu IM LẶNG nhất: nội dung văn bản này hiện ra dưới tên văn
   bản kia, không một dòng cảnh báo.
3. **Bản nháp KHÔNG được lọt ra ngoài.** Giám đốc viết dở mà cả công ty đọc thấy thì tệ hơn là
   chưa có tính năng.
4. **File đính kèm + ảnh trang phải tải được bởi nhân viên thường.** Cổng `/api/files` gác theo
   THƯ MỤC; thêm `noi-quy` vào `_PREFIX_PERMISSION` là chỉ Giám đốc mở được PDF. Việc đó trông rất
   "đúng bài" nên rất dễ có người thêm vào sau — test này là thứ chặn.
"""
from __future__ import annotations

import io
import sys
from unittest import mock

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from tests.test_luong_api import _admin_token, _h


def _nv_thuong_token() -> str:
    """Tài khoản vai 'NV Sales' — KHÔNG có ô quyền `noi_quy` nào. Đúng vai công nhân/nhân viên
    thường: chỉ đăng nhập được, không quản trị gì."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("nv-thuong-nq")
        if u is None:
            kd = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
            u = users.create(username="nv-thuong-nq", name="NV thường",
                             password_hash=hash_password("x"))
            users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _tao_tai_lieu(client, token, title: str) -> int:
    """Tạo một tài liệu trong bộ nội quy, trả về id. Mọi thao tác soạn thảo giờ đều đi qua id này —
    không còn "bản nội quy" toàn cục nào nữa."""
    r = client.post("/api/noi-quy/documents", json={"title": title}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _soan_va_ban_hanh(client, token, doc_id: int, *, noi_dung: str, ghi_chu: str | None = None):
    r = client.put(f"/api/noi-quy/documents/{doc_id}/draft",
                   json={"noi_dung": noi_dung, "ghi_chu": ghi_chu}, headers=_h(token))
    assert r.status_code == 200, r.text
    p = client.post(f"/api/noi-quy/documents/{doc_id}/publish", headers=_h(token))
    assert p.status_code == 200, p.text
    return p.json()


def _ngay_ban_hanh(client, token) -> dict[int, str | None]:
    """`{id tài liệu: ngày ban hành}` đọc từ đúng danh sách nhân viên nhìn thấy."""
    items = client.get("/api/noi-quy/documents", headers=_h(token)).json()["items"]
    return {i["id"]: i["published_at"] for i in items}


def _current(client, token, doc_id: int) -> dict:
    return client.get(f"/api/noi-quy/documents/{doc_id}/current", headers=_h(token)).json()


def _dinh_kem(client, token, doc_id: int, *, ten="noi-quy-ky.pdf"):
    """Đính một file CHỨNG TỪ vào nháp của tài liệu (không phải file gốc do hệ thống tự đính)."""
    return client.post(
        f"/api/noi-quy/documents/{doc_id}/draft/attachments",
        files={"file": (ten, io.BytesIO(b"%PDF-1.4 noi quy da ky"), "application/pdf")},
        headers=_h(token),
    )


# --- Yêu cầu cốt lõi: ai cũng đọc được --------------------------------------

def test_nhan_vien_thuong_DOC_DUOC_noi_quy(client):
    """⭐ Chính yêu cầu của chủ: "tất cả nhân viên có thể thấy".

    Canh CẢ HAI đường đọc, vì màn nội quy cần đủ hai mới ra được nội dung: `/documents` dựng cột
    phải, `/documents/{id}/current` dựng nội dung bên trái. Thêm `require_permission` vào một trong
    hai là nhân viên thấy màn rỗng — mà cả hai đều trông rất "đáng gác", nên rất dễ bị siết nhầm."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Điều 1. Đi làm đúng giờ.")

    nv = _nv_thuong_token()
    ds = client.get("/api/noi-quy/documents", headers=_h(nv))
    assert ds.status_code == 200, ds.text
    items = ds.json()["items"]
    assert [i["title"] for i in items] == ["Nội quy lao động"]
    assert items[0]["published_at"], "thiếu ngày ban hành thì cột phải không nói được bản nào mới"

    noi_dung = client.get(f"/api/noi-quy/documents/{doc}/current", headers=_h(nv))
    assert noi_dung.status_code == 200, noi_dung.text
    assert noi_dung.json()["has_content"] is True
    assert "Điều 1" in noi_dung.json()["noi_dung"]
    assert noi_dung.json()["document_id"] == doc


def test_endpoint_current_cu_van_song_them_mot_nhip(client):
    """Lúc deploy, trình duyệt nhân viên vẫn đang mở bản giao diện CŨ — nó chỉ biết gọi `/current`.
    Bỏ hẳn endpoint này là những người đó thấy màn gãy cho tới khi họ tự tải lại trang."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Điều 1. Đi làm đúng giờ.")

    r = client.get("/api/noi-quy/current", headers=_h(_nv_thuong_token()))
    assert r.status_code == 200, r.text
    assert r.json()["has_content"] is True and "Điều 1" in r.json()["noi_dung"]


def test_chua_ban_hanh_lan_nao_thi_bao_ro_chu_khong_no(client):
    """Công ty chưa khai nội quy ⇒ danh sách rỗng + `has_content=false` để màn hiện trạng thái
    rỗng, KHÔNG phải 404 (404 làm FE tưởng hỏng API) và không phải màn trắng."""
    nv = _nv_thuong_token()
    ds = client.get("/api/noi-quy/documents", headers=_h(nv))
    assert ds.status_code == 200 and ds.json()["items"] == []

    r = client.get("/api/noi-quy/current", headers=_h(nv))
    assert r.status_code == 200
    assert r.json()["has_content"] is False and r.json()["noi_dung"] == ""


def test_nhan_vien_thuong_KHONG_sua_duoc(client):
    """Đọc thì ai cũng được, GHI thì chỉ vai có quyền. Kể cả danh sách `/documents/tat-ca` — nó
    phơi cả tài liệu chưa ban hành, tức là bản Giám đốc đang viết dở."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    nv = _nv_thuong_token()

    assert client.post("/api/noi-quy/documents", json={"title": "Tự tạo"},
                       headers=_h(nv)).status_code == 403
    assert client.patch(f"/api/noi-quy/documents/{doc}", json={"title": "Tự đổi"},
                        headers=_h(nv)).status_code == 403
    assert client.put(f"/api/noi-quy/documents/{doc}/draft", json={"noi_dung": "tự sửa"},
                      headers=_h(nv)).status_code == 403
    assert client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(nv)).status_code == 403
    assert client.get(f"/api/noi-quy/documents/{doc}/draft", headers=_h(nv)).status_code == 403
    assert client.get(f"/api/noi-quy/documents/{doc}/versions", headers=_h(nv)).status_code == 403
    assert client.get("/api/noi-quy/documents/tat-ca", headers=_h(nv)).status_code == 403


# --- Nhiều tài liệu: không được lẫn vào nhau --------------------------------

def test_hai_tai_lieu_co_hai_NHAP_DOC_LAP(client):
    """⭐ Chỗ vừa suýt hỏng, và hỏng thì KHÔNG có dấu hiệu nào.

    `get_draft()` từng truy vấn toàn cục (không lọc `document_id`). Khi đó mở nháp "Nội quy lao
    động" rồi mở nháp "Quy chế lương thưởng" sẽ trả về CÙNG một nháp: gõ cho văn bản này là đè lên
    văn bản kia, và bấm Ban hành thì nội dung vừa gõ trở thành bản hiệu lực của văn bản kia. Đảo
    nội dung giữa hai văn bản, không một dòng cảnh báo — người soạn chỉ phát hiện khi có nhân viên
    đọc nhầm luật."""
    gd = _admin_token(client)
    a = _tao_tai_lieu(client, gd, "Nội quy lao động")
    b = _tao_tai_lieu(client, gd, "Quy chế lương thưởng")

    nhap_a = client.get(f"/api/noi-quy/documents/{a}/draft", headers=_h(gd)).json()
    nhap_b = client.get(f"/api/noi-quy/documents/{b}/draft", headers=_h(gd)).json()
    assert nhap_a["id"] != nhap_b["id"], "hai tài liệu đang dùng CHUNG một bản nháp"
    assert nhap_a["document_id"] == a and nhap_b["document_id"] == b

    # Ghi cho B không được chạm tới A.
    client.put(f"/api/noi-quy/documents/{b}/draft",
               json={"noi_dung": "<p>Thưởng tháng 13 — bản của B</p>"}, headers=_h(gd))
    lai_a = client.get(f"/api/noi-quy/documents/{a}/draft", headers=_h(gd)).json()
    assert lai_a["id"] == nhap_a["id"], "mở lại nháp A phải ra đúng nháp cũ, không phải nháp mới"
    assert "bản của B" not in lai_a["noi_dung"], "nội dung của B tràn sang nháp của A"

    # Và ban hành B không được biến nội dung B thành bản hiệu lực của A.
    assert client.post(f"/api/noi-quy/documents/{b}/publish",
                       headers=_h(gd)).status_code == 200
    assert "bản của B" in _current(client, gd, b)["noi_dung"]
    assert _current(client, gd, a)["has_content"] is False, \
        "A chưa ban hành lần nào mà đã có nội dung — nội dung của B đã bị gán nhầm sang A"


def test_tai_lieu_MOI_thi_TRONG_khong_chep_cua_tai_lieu_khac(client):
    """⭐ Cùng gốc bệnh với test trên, nhưng ở `current()`.

    Không lọc `document_id` thì tài liệu vừa tạo ra đời là BẢN SAO NGUYÊN VĂN của tài liệu khác —
    kèm cả file PDF đã ký. Chủ gõ tiêu đề "An toàn lao động", bấm vào, thấy nguyên nội quy lao động
    nằm sẵn trong đó; sửa vài dòng rồi ban hành là công ty có hai văn bản gần giống nhau mà không
    ai biết cái nào là thật."""
    gd = _admin_token(client)
    a = _tao_tai_lieu(client, gd, "Nội quy lao động")
    assert _dinh_kem(client, gd, a, ten="noi-quy-da-ky.pdf").status_code == 201
    _soan_va_ban_hanh(client, gd, a, noi_dung="<p>Điều 1. Đi làm đúng giờ.</p>")

    b = _tao_tai_lieu(client, gd, "An toàn lao động")
    assert _current(client, gd, b)["has_content"] is False, "tài liệu mới mà đã có bản hiệu lực"

    nhap_b = client.get(f"/api/noi-quy/documents/{b}/draft", headers=_h(gd)).json()
    assert nhap_b["noi_dung"] == "", f"nháp tài liệu mới chép nội dung của tài liệu khác: {nhap_b}"
    assert nhap_b["attachments"] == [], "file đã ký của tài liệu khác bị chép sang"
    assert nhap_b["pages"] == []
    assert nhap_b["source_kind"] == "html"


def test_ban_hanh_tai_lieu_A_KHONG_doi_ngay_cua_tai_lieu_B(client):
    """⭐ Chính điều chủ yêu cầu khi chốt tách nhiều tài liệu: sửa "Các lỗi thường gặp" thì "Nội quy
    lao động" phải GIỮ NGUYÊN ngày ban hành cũ.

    Ngày ban hành là thứ nhân viên nhìn để biết "luật có đổi không". Đẩy ngày của mọi văn bản mỗi
    lần sửa một văn bản là cả danh sách nhấp nháy "mới" — vài lần thì không ai còn tin cột đó, và
    lần thật sự có thay đổi cũng trôi qua không ai để ý."""
    gd = _admin_token(client)
    a = _tao_tai_lieu(client, gd, "Các lỗi thường gặp")
    b = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, a, noi_dung="A — bản 1")
    _soan_va_ban_hanh(client, gd, b, noi_dung="B — bản 1")

    truoc = _ngay_ban_hanh(client, gd)
    ban_b_truoc = _current(client, gd, b)["id"]

    _soan_va_ban_hanh(client, gd, a, noi_dung="A — bản 2, sửa giờ làm")

    sau = _ngay_ban_hanh(client, gd)
    assert sau[b] == truoc[b], f"ban hành A mà B bị đổi ngày: {truoc[b]} → {sau[b]}"
    ban_b_sau = _current(client, gd, b)
    assert ban_b_sau["id"] == ban_b_truoc, "bản hiệu lực của B bị thay khi ban hành A"
    assert ban_b_sau["noi_dung"] == "B — bản 1", "nội dung của B bị A ghi đè"

    # Còn A thì PHẢI đổi — nếu không thì test trên xanh chỉ vì chẳng có gì được ban hành cả.
    assert _current(client, gd, a)["noi_dung"] == "A — bản 2, sửa giờ làm"
    assert sau[a] >= truoc[a]


def test_doi_ten_tai_lieu_KHONG_viet_lai_tieu_de_ban_DA_BAN_HANH(client):
    """Tiêu đề của bản đã ban hành là BẢN CHỤP (`noi_quy_versions.title`), không phải con trỏ tới
    tên hiện hành.

    Đọc thẳng tên từ `noi_quy_documents` thì đổi tên hôm nay là viết lại lịch sử của hôm qua — đúng
    thứ mà cả kiến trúc append-only này dựng ra để chống. Nội quy là căn cứ kỷ luật: "bản tháng 5"
    phải còn nguyên cái tên nó mang hồi tháng 5."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 1")

    r = client.patch(f"/api/noi-quy/documents/{doc}",
                     json={"title": "Nội quy lao động 2026"}, headers=_h(gd))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Nội quy lao động 2026"

    assert _current(client, gd, doc)["title"] == "Nội quy lao động", \
        "đổi tên hôm nay đã viết lại tiêu đề của bản ban hành hôm qua"
    # Danh sách thì dùng tên HIỆN HÀNH — đó mới là chỗ đổi tên phải hiện ra.
    ds = client.get("/api/noi-quy/documents", headers=_h(gd)).json()["items"]
    assert [i["title"] for i in ds] == ["Nội quy lao động 2026"]

    # Bản ban hành SAU khi đổi tên mới mang tên mới.
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 2")
    assert _current(client, gd, doc)["title"] == "Nội quy lao động 2026"


def test_tai_lieu_chua_ban_hanh_KHONG_hien_voi_nhan_vien_nhung_con_o_tat_ca(client):
    """Tiêu đề đã có mà nội dung chưa ⇒ nhân viên bấm vào ra TRANG TRẮNG, trông y như hệ thống hỏng.
    Nên danh sách của nhân viên phải lọc bỏ.

    Nhưng người soạn thì BẮT BUỘC vẫn thấy, nếu không thì tài liệu vừa tạo biến mất khỏi màn hình
    và không còn đường nào quay lại làm tiếp."""
    gd = _admin_token(client)
    xong = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, xong, noi_dung="Điều 1.")
    dang_lam = _tao_tai_lieu(client, gd, "An toàn lao động")

    ds_nv = client.get("/api/noi-quy/documents", headers=_h(_nv_thuong_token())).json()["items"]
    assert [i["id"] for i in ds_nv] == [xong], "tài liệu chưa ban hành lọt ra danh sách nhân viên"

    ds_gd = client.get("/api/noi-quy/documents/tat-ca", headers=_h(gd)).json()["items"]
    assert [i["id"] for i in ds_gd] == [xong, dang_lam], \
        "người soạn mất dấu tài liệu mình vừa tạo"
    chua = next(i for i in ds_gd if i["id"] == dang_lam)
    assert chua["published_at"] is None
    assert chua["co_nhap"] is False

    # Mở nháp rồi thì danh sách của người soạn phải đánh dấu — để biết chỗ nào còn dở dang.
    client.get(f"/api/noi-quy/documents/{dang_lam}/draft", headers=_h(gd))
    ds_gd = client.get("/api/noi-quy/documents/tat-ca", headers=_h(gd)).json()["items"]
    assert next(i for i in ds_gd if i["id"] == dang_lam)["co_nhap"] is True


def test_tai_lieu_ngung_dung_bien_khoi_danh_sach_nhan_vien(client):
    """Thôi áp dụng một văn bản = nhân viên không được thấy nó nữa (đọc nhầm luật đã bỏ là căn cứ
    kỷ luật sai). Nhưng KHÔNG xoá: người soạn vẫn thấy để bật lại, và lịch sử vẫn tra được."""
    gd = _admin_token(client)
    con = _tao_tai_lieu(client, gd, "Nội quy lao động")
    thoi = _tao_tai_lieu(client, gd, "Quy chế cũ 2019")
    _soan_va_ban_hanh(client, gd, con, noi_dung="Điều 1.")
    _soan_va_ban_hanh(client, gd, thoi, noi_dung="Quy định cũ.")

    r = client.patch(f"/api/noi-quy/documents/{thoi}", json={"is_active": False}, headers=_h(gd))
    assert r.status_code == 200 and r.json()["is_active"] is False

    ds_nv = client.get("/api/noi-quy/documents", headers=_h(_nv_thuong_token())).json()["items"]
    assert [i["id"] for i in ds_nv] == [con]

    ds_gd = client.get("/api/noi-quy/documents/tat-ca", headers=_h(gd)).json()["items"]
    assert {i["id"] for i in ds_gd} == {con, thoi}
    assert next(i for i in ds_gd if i["id"] == thoi)["is_active"] is False


def test_chan_TRUNG_tieu_de_ke_ca_khac_hoa_thuong_va_thua_khoang_trang(client):
    """Hai dòng "Nội quy lao động" nằm cạnh nhau trong cột phải thì chủ sẽ sửa nhầm cái — và KHÔNG
    có cách nào nhìn ra mình đang sửa cái nào. So sánh phải chuẩn hoá hoa/thường + khoảng trắng,
    vì tên gõ tay hai lần gần như không bao giờ giống nhau từng ký tự."""
    gd = _admin_token(client)
    _tao_tai_lieu(client, gd, "Nội quy lao động")

    trung = client.post("/api/noi-quy/documents",
                        json={"title": "  nội quy   LAO động "}, headers=_h(gd))
    assert trung.status_code == 400, trung.text
    assert "Đã có tài liệu tên" in trung.json()["detail"]

    # Và chốt phải giữ cả ở đường ĐỔI TÊN — không thì né được chỉ bằng cách tạo tên khác rồi sửa lại.
    khac = _tao_tai_lieu(client, gd, "An toàn lao động")
    doi = client.patch(f"/api/noi-quy/documents/{khac}",
                       json={"title": "NỘI QUY LAO ĐỘNG"}, headers=_h(gd))
    assert doi.status_code == 400, doi.text
    assert "Đã có tài liệu tên" in doi.json()["detail"]

    # Nhưng đổi tên CHÍNH NÓ về đúng tên nó đang mang thì không được coi là trùng.
    assert client.patch(f"/api/noi-quy/documents/{khac}",
                        json={"title": "An toàn lao động", "seq": 2},
                        headers=_h(gd)).status_code == 200


def test_lich_su_chi_co_ban_cua_DUNG_tai_lieu_do(client):
    """`list_versions` không lọc `document_id` thì lịch sử trộn chung mọi văn bản — mở lịch sử "Các
    lỗi thường gặp" ra thấy cả các bản của "Nội quy lao động", và không cột nào nói cho biết dòng
    nào thuộc văn bản nào."""
    gd = _admin_token(client)
    a = _tao_tai_lieu(client, gd, "Nội quy lao động")
    b = _tao_tai_lieu(client, gd, "Các lỗi thường gặp")
    _soan_va_ban_hanh(client, gd, a, noi_dung="A1", ghi_chu="A — ban hành lần đầu")
    _soan_va_ban_hanh(client, gd, b, noi_dung="B1", ghi_chu="B — ban hành lần đầu")
    _soan_va_ban_hanh(client, gd, a, noi_dung="A2", ghi_chu="A — sửa giờ làm")

    ls_a = client.get(f"/api/noi-quy/documents/{a}/versions", headers=_h(gd)).json()["items"]
    assert [i["ghi_chu"] for i in ls_a] == ["A — sửa giờ làm", "A — ban hành lần đầu"]

    ls_b = client.get(f"/api/noi-quy/documents/{b}/versions", headers=_h(gd)).json()["items"]
    assert [i["ghi_chu"] for i in ls_b] == ["B — ban hành lần đầu"]


# --- Nháp không được lọt ----------------------------------------------------

def test_NHAP_khong_lot_ra_ngoai(client):
    """⭐ Chỗ hỏng thì đau nhất: cả công ty đọc nội quy Giám đốc đang viết dở.

    Lưu nháp xong, nhân viên phải vẫn thấy BẢN CŨ — không phải nội dung nháp, cũng không phải
    màn trống."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="BẢN CŨ — đang hiệu lực.")

    r = client.put(f"/api/noi-quy/documents/{doc}/draft",
                   json={"noi_dung": "BẢN NHÁP — viết dở, chưa xong."}, headers=_h(gd))
    assert r.status_code == 200

    nv = _current(client, _nv_thuong_token(), doc)
    assert nv["noi_dung"] == "BẢN CŨ — đang hiệu lực."
    assert "NHÁP" not in nv["noi_dung"]

    # Ban hành xong thì mới thấy.
    client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    nv2 = _current(client, _nv_thuong_token(), doc)
    assert nv2["noi_dung"] == "BẢN NHÁP — viết dở, chưa xong."


def test_ban_hanh_giu_lai_ban_cu_lam_lich_su(client):
    """Nội quy là căn cứ kỷ luật — phải trả lời được "hồi tháng trước luật là gì"."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 1", ghi_chu="Ban hành lần đầu")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 2", ghi_chu="Sửa giờ làm")

    assert _current(client, gd, doc)["noi_dung"] == "Bản 2"
    items = client.get(f"/api/noi-quy/documents/{doc}/versions", headers=_h(gd)).json()["items"]
    assert [i["ghi_chu"] for i in items] == ["Sửa giờ làm", "Ban hành lần đầu"]
    assert items[0]["published_by_name"], "phải biết AI ban hành"


def test_khong_ban_hanh_noi_dung_rong(client):
    """Bấm nhầm nút Ban hành khi ô trống = xoá trắng nội quy cả công ty."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    client.put(f"/api/noi-quy/documents/{doc}/draft", json={"noi_dung": "   "}, headers=_h(gd))
    r = client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    assert r.status_code == 400 and "trống" in r.json()["detail"]


def test_mo_nhap_thi_chep_san_ban_dang_hieu_luc(client):
    """Sửa nội quy hầu như là sửa vài chỗ trên bản đang có — mở ra trang trắng là mời gõ thiếu."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Điều 1. Đi làm đúng giờ.")
    nhap = client.get(f"/api/noi-quy/documents/{doc}/draft", headers=_h(gd)).json()
    assert nhap["noi_dung"] == "Điều 1. Đi làm đúng giờ."


# --- File đính kèm ----------------------------------------------------------

def test_nhan_vien_thuong_TAI_DUOC_file_dinh_kem(client):
    """⭐ Canh đúng cái bẫy: `/api/files` gác theo THƯ MỤC (`_PREFIX_PERMISSION`), thư mục nào
    KHÔNG khai trong bảng đó thì chỉ cần đăng nhập — giống `avatars/`.

    Thêm `"noi-quy"` vào bảng đó là chỉ Giám đốc mở được PDF, phá đúng yêu cầu "tất cả nhân viên
    thấy". Việc đó trông rất hợp lý nên rất dễ bị thêm vào — test này là thứ chặn."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    up = _dinh_kem(client, gd, doc)
    assert up.status_code == 201, up.text
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Có file kèm")

    nv = _nv_thuong_token()
    cur = _current(client, nv, doc)
    assert len(cur["attachments"]) == 1, "file phải theo sang bản đã ban hành"

    tai = client.get(cur["attachments"][0]["file_url"], headers=_h(nv))
    assert tai.status_code == 200, f"nhân viên thường KHÔNG tải được file: {tai.status_code}"


def test_ban_hanh_ban_moi_thi_file_da_ky_KHONG_bi_mat(client):
    """⭐ Sửa một lỗi chính tả rồi ban hành mà mất bản PDF đã ký thì im lặng chết người.

    Nháp phải chép sẵn file của bản đang hiệu lực."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _dinh_kem(client, gd, doc)
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 1 có file")

    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản 2 sửa chính tả")
    cur = _current(client, gd, doc)
    assert cur["noi_dung"] == "Bản 2 sửa chính tả"
    assert len(cur["attachments"]) == 1, "file đã ký phải theo sang bản mới, không tự biến mất"


def test_ban_DA_BAN_HANH_thi_khong_them_bot_file_duoc(client):
    """Bản đã ban hành là ảnh chụp tại thời điểm đó. Đổi file sau lưng người đã đọc thì "bản
    tháng 5" không còn là bản tháng 5."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _soan_va_ban_hanh(client, gd, doc, noi_dung="Bản đã chốt")
    ban = _current(client, gd, doc)

    from app.repositories.noi_quy_repo import NoiQuyRepository
    db = SessionLocal()
    try:
        svc_repo = NoiQuyRepository(db)
        a = svc_repo.add_attachment(version_id=ban["id"], file_name="x.pdf",
                                    file_url="/api/files/noi-quy/x.pdf", file_type=None,
                                    uploaded_by=None)
        aid = a.id
    finally:
        db.close()
    r = client.delete(f"/api/noi-quy/draft/attachments/{aid}", headers=_h(gd))
    assert r.status_code == 400 and "đã ban hành" in r.json()["detail"]


def test_chi_Giam_doc_co_module_noi_quy_sau_seed(client):
    """Chủ chốt: CHỈ Giám đốc soạn được. Vai khác vô tình được cấp là lệch chính sách."""
    client
    db = SessionLocal()
    try:
        depts, roles = DepartmentRepository(db), RoleRepository(db)
        co_quyen = sorted({
            r.name
            for d in depts.list_all()
            for r in roles.list_by_department(d.id)
            if any(p.module_key == "noi_quy" and (p.can_update or p.can_create)
                   for p in roles.permissions_for(r.id))
        })
    finally:
        db.close()
    assert co_quyen == ["Giám đốc"], f"ngoài Giám đốc còn vai khác soạn được nội quy: {co_quyen}"


def test_chan_loai_va_dung_luong_file_o_SERVER(client):
    """⭐ Chặn ở FE chỉ là phép lịch sự — ai gọi thẳng API là đi vòng qua nó.

    Endpoint này ban đầu tôi viết KHÔNG kiểm gì (agent soi UI bắt ra 30/07). Không chặn thì một
    cú kéo nhầm cả thư mục ảnh vào đây là phình kho file."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    url = f"/api/noi-quy/documents/{doc}/draft/attachments"

    sai_loai = client.post(
        url,
        files={"file": ("virus.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")},
        headers=_h(gd))
    assert sai_loai.status_code == 400 and "PDF" in sai_loai.json()["detail"]

    qua_to = client.post(
        url,
        files={"file": ("to.pdf", io.BytesIO(b"x" * (20 * 1024 * 1024 + 1)), "application/pdf")},
        headers=_h(gd))
    assert qua_to.status_code == 400 and "20 MB" in qua_to.json()["detail"]

    rong = client.post(
        url,
        files={"file": ("rong.pdf", io.BytesIO(b""), "application/pdf")},
        headers=_h(gd))
    assert rong.status_code == 400 and "rỗng" in rong.json()["detail"]

    # PDF hợp lệ vẫn phải qua — chặn không được chặn nhầm việc thật.
    assert _dinh_kem(client, gd, doc).status_code == 201


# --- Lọc HTML (nội quy nay là HTML, không còn văn bản thuần) ------------------

def _luu(client, token, doc_id: int, html: str) -> str:
    r = client.put(f"/api/noi-quy/documents/{doc_id}/draft",
                   json={"noi_dung": html}, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["noi_dung"]


def test_HTML_doc_bi_loc_o_SERVER(client):
    """⭐ Test đáng giá nhất của màn này.

    Nội quy do MỘT người ghi nhưng MỌI nhân viên render ⇒ một lần ghi độc là cả công ty chạy.
    DOMPurify phía trình duyệt KHÔNG tính — ai gọi thẳng API là đi vòng qua nó. Chốt phải nằm ở
    server, và đây là thứ canh nó."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")

    ra = _luu(client, gd, doc, '<p>Điều 1</p><script>alert(1)</script>')
    assert "<script" not in ra and "alert" not in ra
    assert "Điều 1" in ra, "lọc mà mất luôn nội dung thật thì hỏng kiểu khác"

    ra = _luu(client, gd, doc, '<p onclick="alert(1)">Điều 2</p><img src=x onerror=alert(1)>')
    assert "onclick" not in ra and "onerror" not in ra
    assert "Điều 2" in ra

    ra = _luu(client, gd, doc, '<a href="javascript:alert(1)">bấm đây</a>')
    assert "javascript:" not in ra

    ra = _luu(client, gd, doc, '<iframe src="https://xau.com"></iframe><p>Điều 3</p>')
    assert "<iframe" not in ra and "Điều 3" in ra


def test_the_HOP_LE_khong_bi_loc_oan(client):
    """⭐ Hỏng theo chiều ngược lại: lọc quá tay là MẤT NỘI DUNG nội quy.

    Bảng "hành vi vi phạm → hình thức xử lý" gần như nội quy nào cũng có — lọc mất bảng là mất
    đúng phần quan trọng nhất."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    ra = _luu(client, gd, doc, (
        '<h2>CHƯƠNG I</h2><p><strong>Điều 1.</strong> Đi làm <em>đúng giờ</em>.</p>'
        '<ul><li>Ca sáng 7h00</li><li>Ca chiều 13h00</li></ul>'
        '<ol><li>Nhắc nhở</li><li>Khiển trách</li></ol>'
        '<table><thead><tr><th>Vi phạm</th><th>Xử lý</th></tr></thead>'
        '<tbody><tr><td colspan="2">Đi trễ 3 lần</td></tr></tbody></table>'
        '<blockquote>Trích Điều 118 BLLĐ</blockquote>'
    ))
    for the in ("<h2>", "<strong>", "<em>", "<ul>", "<li>", "<ol>",
                "<table>", "<th>", "<td", "<blockquote>"):
        assert the in ra, f"thẻ hợp lệ {the} bị lọc oan — mất nội dung nội quy"
    assert 'colspan="2"' in ra, "gộp ô của bảng bị mất thì bảng vỡ"


def test_anh_NGOAI_bi_chan_anh_NOI_BO_duoc_giu(client):
    """Ảnh ngoài = mỗi lần nhân viên mở nội quy là máy chủ lạ biết ⇒ vô tình điểm danh cả công ty."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    ra = _luu(client, gd, doc, '<img src="https://theo-doi.com/x.gif"><p>Điều 1</p>')
    assert "theo-doi.com" not in ra

    ra = _luu(client, gd, doc, '<img src="/api/files/noi-quy/1/chu-ky.png" alt="chữ ký">')
    assert "/api/files/noi-quy/1/chu-ky.png" in ra and 'alt="chữ ký"' in ra


def test_noi_dung_chi_con_the_rong_van_bi_coi_la_TRONG(client):
    """Trình soạn thảo luôn để lại `<p></p>` khi xoá hết chữ. Đếm theo độ dài chuỗi thì nó "có
    nội dung" ⇒ bấm Ban hành là xoá trắng nội quy cả công ty mà hệ thống không cản."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    client.put(f"/api/noi-quy/documents/{doc}/draft",
               json={"noi_dung": "<p></p><p><br></p>"}, headers=_h(gd))
    r = client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    assert r.status_code == 400 and "trống" in r.json()["detail"]


def test_endpoint_anh_chan_dung_va_nhan_vien_thuong_khong_goi_duoc(client):
    """Ảnh trong THÂN nội quy — endpoint này CỐ Ý không gắn với tài liệu nào (ảnh chỉ là bytes,
    tài liệu nào dùng là do thẻ `<img>` trong nội dung quyết định)."""
    gd = _admin_token(client)

    ok = client.post("/api/noi-quy/draft/images",
                     files={"file": ("ky.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")},
                     headers=_h(gd))
    assert ok.status_code == 201, ok.text
    assert ok.json()["url"].startswith("/api/files/noi-quy/"), \
        "URL phải nằm trong kho file nội bộ, không thì bộ lọc HTML sẽ vứt thẻ img"

    sai = client.post("/api/noi-quy/draft/images",
                      files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
                      headers=_h(gd))
    assert sai.status_code == 400 and "JPG" in sai.json()["detail"]

    assert client.post("/api/noi-quy/draft/images",
                       files={"file": ("x.png", io.BytesIO(b"\x89PNG"), "image/png")},
                       headers=_h(_nv_thuong_token())).status_code == 403


# --- Lọc CSS trong `style` --------------------------------------------------

def test_style_giu_dinh_dang_that_su_can(client):
    """Đây là nửa "đừng lọc quá tay" — hỏng chiều này thì bản Word tải lên mất hết canh lề, cỡ chữ.

    Văn bản hành chính VN canh GIỮA khối tiêu đề; mất `text-align: center` là nhìn ra sai ngay."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    html = _luu(client, gd, doc, (
        '<p style="text-align: center; font-size: 14pt">NỘI QUY LAO ĐỘNG</p>'
        '<p style="text-indent: 28px; line-height: 1.5">Điều 1. <span style="color: #b00">Quan '
        'trọng</span></p>'
        '<table><tr><td style="width: 40%; vertical-align: top">Vi phạm</td>'
        '<td style="text-align: right">Xử lý</td></tr></table>'
    ))
    for phai_co in ("text-align: center", "font-size: 14pt", "text-indent: 28px",
                    "line-height: 1.5", "color: #b00", "width: 40%",
                    "vertical-align: top", "text-align: right"):
        assert phai_co in html, f"mất định dạng cần giữ ({phai_co}): {html}"
    assert "<span" in html and "<td" in html


def test_style_chan_thuoc_tinh_nguy_hiem_nhung_GIU_khai_bao_lanh(client):
    """⭐ Lọc theo TỪNG khai báo, không phải cả chuỗi.

    `url(...)` trong CSS kéo tài nguyên từ máy chủ lạ ⇒ mỗi nhân viên mở nội quy là bên đó biết,
    vô tình điểm danh cả công ty (cùng lý do đã siết `<img src>`). `position: fixed` thì phủ kín
    màn hình. Nhưng vứt cả chuỗi vì một khai báo xấu là mất luôn `text-align` lành — nên phải lọc
    lẻ từng cái."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    html = _luu(client, gd, doc, (
        '<p style="text-align: center; background-image: url(https://theo-doi.com/x.png); '
        'position: fixed; top: 0; z-index: 99999; width: 30%">Tiêu đề</p>'
    ))
    assert "text-align: center" in html, f"khai báo lành phải sống: {html}"
    assert "width: 30%" in html
    for phai_mat in ("url(", "theo-doi.com", "position", "z-index", "background-image"):
        assert phai_mat not in html, f"còn sót thứ nguy hiểm ({phai_mat}): {html}"


def test_style_chan_expression_va_ky_tu_thoat(client):
    """`expression()` chạy script trên IE cũ; `\\` và `/*` là cách kinh điển để đi vòng qua chính
    bộ lọc này. Chặn ở tầng giá trị, không tin vào việc "chắc không ai dùng IE"."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    html = _luu(client, gd, doc, (
        '<p style="color: expression(alert(1)); font-size: 12\\70 t; '
        'text-align: cen/*x*/ter">Thử</p>'
    ))
    for phai_mat in ("expression", "\\", "/*"):
        assert phai_mat not in html, f"còn sót ({phai_mat}): {html}"
    assert "Thử" in html, "chữ vẫn phải còn"


def test_style_tren_the_LA_bi_bo_han(client):
    """`style` chỉ được phép trên tập thẻ văn bản. Trên `<a>`/`<img>` thì không cần, mà mở ra là
    thêm bề mặt cho không việc gì."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    html = _luu(client, gd, doc,
                '<p><a href="https://x.vn" style="width: 9999px">link</a></p>')
    assert "<a" in html and 'href="https://x.vn"' in html
    assert "style" not in html, f"style trên <a> phải bị bỏ: {html}"


def test_tieu_de_cap_5_6_bi_HA_THANH_h4_chu_khong_mat_the(client):
    """⭐ Word soạn được tới Heading 6, allowlist chỉ tới `h4`.

    Nếu để nh3 xử lý thì nó BỎ THẺ và giữ chữ trơn ⇒ tiêu đề tụt thành đoạn văn thường, **không
    báo gì**. Chủ nhìn editor thấy đúng, lưu xong tải lại thì cấp tiêu đề biến mất — loại lỗi chỉ
    phát hiện sau khi đã ban hành cho cả công ty.

    Chốt phải nằm ở SERVER: FE cũng hạ cấp (`capHeadings`) nhưng ai gọi thẳng API là đi vòng qua
    nó."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    html = _luu(client, gd, doc, "<h2>Chương I</h2><h5>Mục nhỏ</h5><h6>Mục nhỏ hơn</h6>")

    assert "<h2>Chương I</h2>" in html, "cấp hợp lệ phải giữ nguyên"
    assert "<h5" not in html and "<h6" not in html, f"cấp quá sâu phải được đổi: {html}"
    assert html.count("<h4>") == 2, f"cả hai phải thành h4, không phải chữ trơn: {html}"
    assert "<h4>Mục nhỏ</h4>" in html and "<h4>Mục nhỏ hơn</h4>" in html


def test_noi_dung_qua_dai_bi_chan(client):
    """`noi_dung` được MỌI nhân viên tải lại mỗi lần mở màn. Không có trần thì một lần dán nhầm là
    cả công ty gánh khối đó mãi."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    r = client.put(f"/api/noi-quy/documents/{doc}/draft",
                   json={"noi_dung": "<p>" + ("x" * (2 * 1024 * 1024 + 10)) + "</p>"},
                   headers=_h(gd))
    assert r.status_code == 422, r.status_code


# --- Đường "giữ nguyên dáng chữ": hiện đúng bản gốc PDF ---------------------
# Màn này giờ CHỈ tải file lên (chủ chốt 30/07/2026 — bỏ trình soạn thảo, bỏ luôn đường tách chữ
# từ PDF). Nên nhóm test dưới đây là đường sống chính của tính năng, không phải nhánh phụ.

def _pdf_nhieu_trang(so_trang: int = 3) -> io.BytesIO:
    from reportlab.pdfgen import canvas

    data = io.BytesIO()
    pdf = canvas.Canvas(data)
    for i in range(1, so_trang + 1):
        pdf.drawString(72, 780, f"NOI QUY - trang {i}")
        pdf.showPage()
    pdf.save()
    data.seek(0)
    return data


def _tai_ban_goc(client, token, doc_id: int, *, so_trang: int = 3, ten="noi-quy.pdf"):
    return client.post(
        f"/api/noi-quy/documents/{doc_id}/draft/ban-goc-pdf",
        files={"file": (ten, _pdf_nhieu_trang(so_trang), "application/pdf")},
        headers=_h(token),
    )


def test_tai_PDF_len_thi_dung_anh_tung_trang_va_nhan_vien_XEM_DUOC(client):
    """⭐ Yêu cầu gốc của chủ: *"đưa pdf hoặc word lên thì… dáng chữ vẫn giữ nguyên"*.

    Cách duy nhất giữ nguyên dáng PDF là hiện chính trang đó ⇒ dựng ảnh từng trang. Test canh cả
    chuỗi: dựng đủ trang, đúng thứ tự, `source_kind` đổi sang `file`, và **nhân viên thường tải
    được ảnh** (ảnh nằm trong `noi-quy/` — thư mục cố ý không gác quyền)."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    r = _tai_ban_goc(client, gd, doc, so_trang=3)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["source_kind"] == "file"
    assert [p["page_no"] for p in body["pages"]] == [1, 2, 3], "phải đủ trang và đúng thứ tự"
    assert all(p["width"] > 0 and p["height"] > 0 for p in body["pages"]), \
        "phải có kích thước thật, nếu không trang sẽ nhảy khi ảnh tải lười xong"
    # File gốc tự đính kèm để đối chiếu về sau.
    assert len(body["attachments"]) == 1

    p = client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    assert p.status_code == 200, p.text

    nv = _nv_thuong_token()
    cur = _current(client, nv, doc)
    assert cur["source_kind"] == "file"
    assert len(cur["pages"]) == 3
    tai = client.get(cur["pages"][0]["file_url"], headers=_h(nv))
    assert tai.status_code == 200, f"nhân viên thường KHÔNG xem được trang nội quy: {tai.status_code}"


def test_ban_hanh_PDF_khong_bi_chan_vi_noi_dung_chu_TRONG(client):
    """⭐ Bản PDF có `noi_dung` trống là BÌNH THƯỜNG — nội dung của nó là ảnh trang.

    Chốt "không ban hành nội dung rỗng" nếu chỉ đếm chữ sẽ chặn luôn nội quy PDF, và chủ không có
    đường nào ban hành được bản mình vừa tải lên. Từ khi bỏ trình soạn thảo thì đây là đường DUY
    NHẤT để có nội quy — chặn nhầm ở đây là tính năng chết hẳn."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    assert _tai_ban_goc(client, gd, doc, so_trang=1).status_code == 200
    nhap = client.get(f"/api/noi-quy/documents/{doc}/draft", headers=_h(gd)).json()
    assert nhap["noi_dung"] == ""

    r = client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    assert r.status_code == 200, f"phải ban hành được dù không có chữ: {r.text}"


def test_mo_lai_nhap_cua_ban_PDF_thi_KHONG_mat_anh_trang(client):
    """⭐ Chỗ hỏng thì cả công ty thấy nội quy TRỐNG TRƠN.

    `get_or_create_draft` chép nội dung + file đính kèm sang nháp. Với bản `file` thì ẢNH TRANG
    chính là nội dung — không chép thì chỉ cần mở nháp rồi ban hành lại (kể cả không sửa gì) là
    nội quy rỗng, mà hệ thống không báo một câu nào."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _tai_ban_goc(client, gd, doc, so_trang=2)
    client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))

    nhap = client.get(f"/api/noi-quy/documents/{doc}/draft", headers=_h(gd)).json()
    assert len(nhap["pages"]) == 2, f"nháp phải chép cả ảnh trang: {nhap['pages']}"
    assert nhap["source_kind"] == "file"

    client.post(f"/api/noi-quy/documents/{doc}/publish", headers=_h(gd))
    cur = _current(client, _nv_thuong_token(), doc)
    assert len(cur["pages"]) == 2, "ban hành lại mà mất ảnh trang = cả công ty thấy trống"


def test_tai_lai_PDF_khac_thi_THAY_het_trang_va_THAY_file_goc(client):
    """Tải lại tài liệu khác mà giữ ảnh cũ thì nội quy thành hai tài liệu dán vào nhau — sai mà
    nhìn vẫn "có nội dung", nên rất dễ lọt tới lúc ban hành.

    Và chủ đã chốt: nhập lại thì THAY file gốc cũ, không cộng dồn — 3 file gần giống nhau thì lúc
    tranh chấp không ai biết bản nào là thật."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _tai_ban_goc(client, gd, doc, so_trang=4, ten="ban-cu.pdf")
    r = _tai_ban_goc(client, gd, doc, so_trang=2, ten="ban-moi.pdf")
    assert r.status_code == 200, r.text
    body = r.json()

    assert [p["page_no"] for p in body["pages"]] == [1, 2], "phải THAY hết trang, không cộng dồn"
    assert len(body["attachments"]) == 1, "chỉ còn MỘT file gốc"
    assert "ban-moi" in body["attachments"][0]["file_name"]


def test_file_chung_tu_chu_TU_dinh_kem_KHONG_bi_xoa_khi_tai_lai(client):
    """⭐ Chỗ này mất là mất bản có giá trị pháp lý nhất.

    "Thay file gốc cũ" chỉ được áp cho file do hệ thống tự đính khi nhập (`is_import_source`). Bản
    PDF đã ký/đóng dấu mà chủ tự bấm "Đính kèm file…" thì phải sống qua mọi lần tải lại."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    assert _dinh_kem(client, gd, doc, ten="da-ky-va-dong-dau.pdf").status_code == 201
    _tai_ban_goc(client, gd, doc, so_trang=1, ten="ban-goc.pdf")
    r = _tai_ban_goc(client, gd, doc, so_trang=1, ten="ban-goc-sua.pdf")

    files = r.json()["attachments"]
    ten_file = {a["file_name"] for a in files}
    assert any("da-ky-va-dong-dau" in t for t in ten_file), \
        f"file đã ký của chủ bị xoá oan: {ten_file}"
    assert len(ten_file) == 2, f"đúng 1 chứng từ + 1 file gốc mới: {ten_file}"

    # Cờ phải PHƠI RA API: FE dùng nó để biết nút "Tải bản PDF gốc" trỏ vào file nào. Thiếu field
    # này thì FE phải suy từ đường dẫn kho file — đoán sai ngay khi có 2 file cùng lúc như đây.
    goc = [a for a in files if a["is_import_source"]]
    chung_tu = [a for a in files if not a["is_import_source"]]
    assert len(goc) == 1 and "ban-goc-sua" in goc[0]["file_name"], f"cờ file gốc sai: {files}"
    assert len(chung_tu) == 1 and "da-ky-va-dong-dau" in chung_tu[0]["file_name"]


def test_chuyen_ve_go_tay_thi_xoa_anh_trang(client):
    """Một bản KHÔNG được mang cả ảnh trang lẫn HTML: hai nội dung cùng lúc thì hiện ra cái nào là
    tuỳ nhánh code nào chạy trước — kiểu lỗi không ai lần ra được."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    _tai_ban_goc(client, gd, doc, so_trang=2)

    r = client.put(f"/api/noi-quy/documents/{doc}/draft",
                   json={"noi_dung": "<p>Gõ tay lại từ đầu</p>", "source_kind": "html"},
                   headers=_h(gd))
    assert r.status_code == 200, r.text
    assert r.json()["source_kind"] == "html"
    assert r.json()["pages"] == [], "chuyển về gõ tay thì ảnh trang phải bị xoá"


def test_nhan_vien_thuong_KHONG_tai_duoc_ban_goc(client):
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    assert _tai_ban_goc(client, _nv_thuong_token(), doc).status_code == 403


def test_PDF_qua_day_bi_chan_va_bao_ro(client):
    """Quá 60 trang gần như chắc chắn là tải nhầm tài liệu khác; dựng ảnh 200 trang thì API treo
    vài phút và kho file phình vô ích."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    r = _tai_ban_goc(client, gd, doc, so_trang=61)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "61" in detail and "60" in detail, f"phải nói rõ bao nhiêu/quá mức nào: {detail}"


def test_thieu_thu_vien_dung_anh_PDF_thi_bao_loi_SERVER_chu_khong_vu_cho_file(client):
    """⭐ Server thiếu thư viện dựng ảnh PDF ⇒ phải nói là lỗi hệ thống.

    Chuyện thật đã xảy ra một lần với `pypdf`: khai trong `requirements.txt` nhưng chưa cài, và vì
    `import` nằm trong `try ... except` nên mọi file PDF đều bị báo **"PDF không hợp lệ hoặc đã bị
    hỏng"**. Người dùng tải một file hoàn toàn lành lên và được bảo là file của mình hỏng — họ sẽ đi
    xuất lại file, đổi máy, nhờ người khác kiểm tra, mất cả buổi cho một lỗi cài đặt. Nay đường tách
    chữ đã bỏ nhưng cái bẫy chuyển nguyên vẹn sang `pypdfium2`, và giờ nó nằm trên đường DUY NHẤT
    để có nội quy. Thông báo phải chỉ về SERVER, và mã lỗi phải là 5xx (4xx nghĩa là "bạn gửi sai"
    ⇒ người ta đi chữa sai chỗ)."""
    gd = _admin_token(client)
    doc = _tao_tai_lieu(client, gd, "Nội quy lao động")
    # `None` trong `sys.modules` làm `import pypdfium2` nổ ImportError — đúng cảnh chưa cài.
    with mock.patch.dict(sys.modules, {"pypdfium2": None}):
        r = _tai_ban_goc(client, gd, doc, so_trang=1)

    assert r.status_code == 503, f"lỗi server phải là 5xx, không phải {r.status_code}: {r.text}"
    detail = r.json()["detail"].lower()
    assert "kỹ thuật" in detail or "hệ thống" in detail, f"phải chỉ về server: {detail}"
    # Canh đúng câu VU CHO FILE, không canh chữ "file của bạn" — thông báo hiện tại có nói cụm đó
    # nhưng ở dạng phủ định ("KHÔNG phải do file của bạn"), tức đang làm đúng.
    assert "hỏng" not in detail, f"KHÔNG được nói file người dùng hỏng: {detail}"
    assert "không hợp lệ" not in detail, f"KHÔNG được nói file người dùng sai: {detail}"

    # Cài đủ thư viện thì đường tải bản gốc vẫn chạy bình thường — không để lại tác dụng phụ.
    assert _tai_ban_goc(client, gd, doc, so_trang=1).status_code == 200
