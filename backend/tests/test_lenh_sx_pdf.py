"""Phiếu công nghệ A4 (Task 13). Dùng ReportLab đang có ở `routers/quotations.py` — KHÔNG thêm
thư viện QR mới, widget QR của chính ReportLab (`graphics.barcode.qr`) đủ dùng.

Bốn luật: đúng PDF · nội dung dài thì TỰ chia trang (không cắt bảng giữa dòng) · mọi trang lặp
mã LSX + phiên bản + QR · tải PDF KHÔNG làm tăng phiên bản phát hành.

Bản nháp brief (`task-13-brief.md`, Bước 1) gọi bốn fixture KHÔNG tồn tại trong repo — nó viết
trước khi Task 10-12 dựng `tests/lenh_sx_fixtures.py`. Ánh xạ đã chốt ở phần "Điều chỉnh của điều
phối" của brief đó:
  · `mot_lenh`           -> `lenh_that`  (lệnh ĐÃ PHÁT HÀNH, routing thật, chủ `admin`)
  · `lenh_40_cong_doan`  -> `lenh_dai`   (fixture MỚI, 40 công đoạn, dựng ở `lenh_sx_fixtures.py`)
  · `sale_a_credentials` -> user `sale_own_ds`/`x` của fixture `sale_own`
  · `lenh_cua_sale_b`    -> `lenh_that`  (thuộc `admin`, ngoài phạm vi `own` của `sale_own`)

Nội dung QR chốt SAU khi điều phối đọc trước Task 14 (task kế tiếp, sửa tiếp `phieu_cong_nghe.py`):
hash fragment `{base}/#lsx=<id>&pv=<phien_ban>`, không phải query string `?ho-so=...` như bản
nháp đầu của brief.

--- ĐỌC ĐƯỢC CHỮ TRÊN GIẤY: BỌC CHỖ VẼ ----------------------------------------------------------
Vòng đầu của task này khai "không có cách rẻ để đọc ngược text từ PDF nếu không thêm thư viện phân
tích PDF" rồi bỏ luôn phần canh nội dung — KẾT LUẬN ĐÓ SAI, và hậu quả là hai luật nóng nhất của
phiếu (mọi trang lặp mã LSX; ĐVT in TÊN chứ không in MÃ) nằm đó không bài nào bắt được: sửa code
cho sai cả hai chỗ mà bộ test vẫn xanh.

Cách rẻ nằm sẵn trong repo — `tests/test_quotations_api.py::test_pdf_giu_dau_tieng_viet` (cùng đợt
sửa font 02/09): thay vì đọc ngược file đã nén, BẮT CHUỖI LÚC NÓ ĐƯỢC VẼ bằng cách bọc
`Canvas.drawString`. Phiếu công nghệ dựng bằng `platypus` nên phải bọc THÊM `Paragraph` (chữ trong
bảng không đi qua `drawString`) và `renderPDF.draw` (đếm lượt vẽ QR). Không thêm thư viện nào.
`_bat_chu()` bên dưới gói đúng ba lượt bọc đó.

Điều đúng-mà-không-đủ của lời khai cũ: bytes PDF thật sự KHÔNG chứa chữ gốc (nội dung trang nén
`FlateDecode`, ký tự tiếng Việt đi qua font TTF nhúng thành mã CID). Nên `b"DejaVuSans" in
r.content` vẫn là cách duy nhất khẳng định font đã NHÚNG, và mọi phép soi NỘI DUNG đi qua
`_bat_chu` chứ không qua `r.content`.

ĐƠN VỊ: `DonViDoRepository.ten_theo_ma()` + `nhan_don_vi()` đổi MÃ (`to`, `kem`…) sang TÊN (`tờ`,
`kẽm`…) trước khi in — `to` được seed sẵn NGOÀI cổng `SEED_DEMO` (`seed_rebuild.seed_don_vi_do`)
nên bài dưới không cần tự tạo dữ liệu danh mục.
"""
from __future__ import annotations

import re
from datetime import date

from app.models.khuon_be import KhuonBe
from app.services.lenh_sx import phieu_cong_nghe

from tests.lenh_sx_fixtures import (  # noqa: F401
    KHUON_KE,
    KHUON_MA,
    NHA_GIA_CONG,
    admin,
    customer,
    lenh_co_khuon,
    lenh_dai,
    lenh_that,
    lenh_thue_ngoai,
    lsx_svc,
    orders,
    sale_own,
    sess,
)


def _tok(client, cred) -> str:
    return client.post("/api/auth/login", json=cred).json()["access_token"]


class _Giay:
    """Những gì THẬT SỰ đi vào mặt giấy của một lượt dựng PDF.

    `canvas` — chuỗi vẽ thẳng lên canvas (đầu trang, chân trang).
    `o` — nội dung từng Ô của ba bảng (mỗi `Paragraph` là một ô), so được BẰNG NHAU chứ không chỉ
    "có chứa": ô ĐVT phải ĐÚNG là `"tờ"`, và không ô nào được ĐÚNG là `"to"`.
    `qr_trang` — số trang tại mỗi lượt vẽ QR.
    """

    def __init__(self) -> None:
        self.canvas: list[str] = []
        self.o: list[str] = []
        self.qr_trang: list[int] = []

    @property
    def chu(self) -> str:
        return "\n".join(self.canvas + self.o)


def _bat_chu(monkeypatch) -> _Giay:
    """Bọc ba chỗ VẼ của ReportLab để soi mọi chữ đi vào bản in — xem docstring module.

    Bọc CHỖ VẼ chứ không mock service: bài vẫn đi trọn đường thật (HTTP → router → quyền →
    `ho_so` → dựng PDF), chỉ nghe lỏm dọc đường. Mock `render_pdf` là canh chính bản mock.
    """
    from reportlab.graphics import renderPDF
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Paragraph

    giay = _Giay()

    ve_trai = Canvas.drawString
    ve_giua = Canvas.drawCentredString
    khoi_tao_o = Paragraph.__init__
    ve_hinh = renderPDF.draw

    def bat_trai(self, x, y, text, *a, **k):
        giay.canvas.append(text)
        return ve_trai(self, x, y, text, *a, **k)

    def bat_giua(self, x, y, text, *a, **k):
        giay.canvas.append(text)
        return ve_giua(self, x, y, text, *a, **k)

    def bat_o(self, text, *a, **k):
        giay.o.append(text)
        return khoi_tao_o(self, text, *a, **k)

    def bat_hinh(drawing, canvas_obj, x, y, *a, **k):
        giay.qr_trang.append(canvas_obj.getPageNumber())
        return ve_hinh(drawing, canvas_obj, x, y, *a, **k)

    monkeypatch.setattr(Canvas, "drawString", bat_trai)
    monkeypatch.setattr(Canvas, "drawCentredString", bat_giua)
    monkeypatch.setattr(Paragraph, "__init__", bat_o)
    monkeypatch.setattr(renderPDF, "draw", bat_hinh)
    return giay


#: Tiêu đề bảng routing, đúng thứ tự cột trên giấy (`phieu_cong_nghe.routing_rows`).
_COT_ROUTING = (
    "STT", "Lớp", "Công đoạn", "Nhóm", "Loại bước",
    "SL vào", "SL ra", "ĐVT", "Tổ", "Bắt buộc",
)


def _bang_routing(giay: _Giay, so_buoc: int) -> list[dict[str, str]]:
    """Dựng lại BẢNG routing theo DÒNG từ danh sách ô phẳng mà `_bat_chu` bắt được.

    `giay.o` là các ô theo đúng thứ tự `Paragraph` được tạo, nên bảng routing là một khối liên
    tục bắt đầu ở ô tiêu đề `"STT"`. So cả hàng tiêu đề trước khi cắt: đổi tên/đổi thứ tự/bỏ một
    cột là bài đỏ ngay tại đây với thông báo đọc được, chứ không lệch âm thầm sang cột bên cạnh.

    Cần soi theo DÒNG chứ không "có chứa": cột `Lớp` và cột `STT` dùng chung kho ký tự số, một
    phép `"1" in giay.o` không phân biệt nổi hai cột — mà phân biệt đúng hai cột ấy chính là việc
    của Q-02.
    """
    n = len(_COT_ROUTING)
    dau = giay.o.index(_COT_ROUTING[0])
    assert giay.o[dau:dau + n] == list(_COT_ROUTING), f"hàng tiêu đề lạ: {giay.o[dau:dau + n]}"
    o = giay.o[dau + n:dau + n * (1 + so_buoc)]
    assert len(o) == n * so_buoc, f"thiếu ô: cần {n * so_buoc}, có {len(o)}"
    return [dict(zip(_COT_ROUTING, o[i * n:(i + 1) * n])) for i in range(so_buoc)]


def _so_trang(noi_dung: bytes) -> int:
    """Đếm TRANG thật trong bytes PDF.

    `count(b"/Type /Page")` KHÔNG đếm được trang: `/Type /Pages` (nút gốc cây trang, mọi PDF đều
    có đúng một cái) chứa chuỗi đó nên phép đếm cũ không bao giờ xuống dưới 1, và với `>= 2` nó
    chỉ cần thêm MỘT trang là đủ — bài không phân biệt được 1 trang với 2. Chặn `s` phía sau.
    """
    return len(re.findall(rb"/Type\s*/Page(?!s)", noi_dung))


def test_tra_ve_pdf(client, seed_credentials, lenh_that):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"


def test_ten_file_tai_ve_mang_ma_lenh(client, seed_credentials, lenh_that):
    """Không có `Content-Disposition` thì mọi phiếu tải về đều tên `phieu-cong-nghe.pdf` trần, và
    thư mục Downloads của người điều độ thành `(1)` `(2)` `(3)` không biết tờ nào của lệnh nào."""
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    ma = client.get(f"/api/lenh-san-xuat/{lenh_that}", headers=h).json()["thong_tin"]["ma"]
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    cd = r.headers["content-disposition"]
    assert ma in cd, cd
    assert cd.endswith('.pdf"'), cd


def test_lenh_dai_tu_chia_trang(client, seed_credentials, lenh_dai):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_dai}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text
    so_trang = _so_trang(r.content)
    assert so_trang >= 2, f"phiếu 40 công đoạn chỉ ra {so_trang} trang"


def test_moi_trang_deu_co_ma_va_phien_ban(client, seed_credentials, lenh_dai, monkeypatch):
    """LUẬT 3 của brief: MỌI trang lặp mã LSX + phiên bản + QR.

    Tờ phiếu đi khắp xưởng và bị tách rời — trang 2 rơi ra khỏi tập mà không mang mã lệnh thì
    không ai biết nó của lệnh nào. Cài đặt là `doc.build(..., onFirstPage=, onLaterPages=)`; bỏ
    `onLaterPages` KHÔNG làm PDF hỏng, không đổi status, không đổi số trang — im lặng hoàn toàn,
    nên phải có bài canh (đột biến ấy đã từng qua được cả bộ test).

    So BẰNG số trang thật, không `>= 1`: đủ mã ở trang đầu mà thiếu ở trang sau là đúng ca phải
    bắt.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_dai}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    so_trang = _so_trang(r.content)
    assert so_trang >= 2, f"tiền đề của bài: phiếu 40 công đoạn phải ra >1 trang, đang ra {so_trang}"

    ma = [s for s in giay.canvas if s.startswith("Mã LSX:")]
    pb = [s for s in giay.canvas if s.startswith("Phiên bản phát hành:")]
    assert len(ma) == so_trang, f"{so_trang} trang nhưng chỉ {len(ma)} trang có mã LSX: {ma}"
    assert len(pb) == so_trang, f"{so_trang} trang nhưng chỉ {len(pb)} trang có phiên bản: {pb}"
    assert giay.qr_trang == list(range(1, so_trang + 1)), giay.qr_trang
    # Mã trên mọi trang phải là CÙNG một mã (không phải mỗi trang một chuỗi khác nhau).
    assert len(set(ma)) == 1 and len(set(pb)) == 1


def test_giay_in_ten_don_vi_khong_in_ma(client, seed_credentials, lenh_that, monkeypatch):
    """Sửa gấp của chủ dự án giữa Task 13: cột ĐVT in TÊN đơn vị, không in MÃ.

    Tổ trưởng đọc "480 tờ", không phải "480 to". Bài cũ (`test_nhan_don_vi_ten_khong_phai_ma`) chỉ
    gọi hàm tra tên nên nó canh CÔNG CỤ chứ không canh chỗ CẮM công cụ vào giấy — bỏ hàm tra ra
    khỏi đúng chỗ nối, in mã trần lên phiếu, mà bài đó vẫn xanh. Bài này soi MẶT GIẤY.

    `lenh_that` khai `don_vi_vao/ra="to"` cho cả ba bước (`test_lenh_sx_tien_do._dung_lenh`), và
    `to` là dòng seed nền (ngoài cổng `SEED_DEMO`) có `ten="tờ"`.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    assert "tờ" in giay.o, f"không ô nào trên giấy là 'tờ' — các ô: {giay.o}"
    assert "to" not in giay.o, "MÃ đơn vị 'to' lọt lên giấy thay vì tên 'tờ'"


def test_giay_khong_in_khoa_may_cua_ba_cot(client, seed_credentials, lenh_that, monkeypatch):
    """Quy cách in / Nhóm / Loại bước phải ra tiếng Việt, không phải khoá máy.

    CÙNG loại lỗi với "480 to", trên cùng tờ giấy: phiếu từng in `mot_mat` / `print` / `may` trong
    khi màn hồ sơ cùng dữ liệu hiện `1 mặt` / `In` / `Máy`. Khoá là thứ chỉ máy đọc được.

    Bài cũng canh luôn luật "khoá lạ ⇒ in NGUYÊN khoá" không bị đổi thành "nuốt mất": ô Nhóm và ô
    Loại bước phải CÓ chữ, không được rỗng.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    # `lenh_that` dựng bước `nhom="print"`, `loai_buoc="may"` (`_dung_lenh`).
    assert "In" in giay.o, f"nhóm `print` chưa được dịch — các ô: {giay.o}"
    assert "Máy" in giay.o, "loại bước `may` chưa được dịch"

    khoa_may = {
        "prepress", "print", "finishing", "other",      # cong_doan.NHOM
        "may", "to", "thue_ngoai",                      # lsx.LOAI_BUOC
        "mot_mat", "hai_mat", "tu_tro", "tro_nhip",     # phieu_tinh_gia.quy_cach_in
    }
    lot = sorted(khoa_may & set(giay.o))
    assert not lot, f"khoá máy lọt lên giấy phát cho tổ: {lot}"


# Khoá dữ liệu mang tiền (tên cột / khoá JSON) và nhãn tiền người đọc. KHÔNG dùng chuỗi trần
# `"gia"`: nhãn hợp lệ "Gia công sau in" chứa nó, và một bài đỏ vì lý do sai thì lần sau người ta
# nới assertion chứ không sửa code.
_KHOA_TIEN = (
    "don_gia", "gia_von", "gia_ban", "thanh_tien", "chi_phi", "phi_giao_hang",
    "luong_khoan", "la_luong_khoan", "tien_khoan", "tong_tien", "don_gia_ban",
)
_NHAN_TIEN = ("đơn giá", "thành tiền", "chi phí", "phí giao", "tiền", "lương", "vnd", "vnđ", "₫")


def test_khong_mot_so_tien_nao_len_giay(client, seed_credentials, lenh_that, monkeypatch):
    """Ràng buộc toàn cục của plan, canh trên ĐƯỜNG PDF — chỗ KHÔNG có lưới schema.

    `test_khong_lo_tien` (đọc JSON qua HTTP) dựa vào `response_model`: `ThongSoOut` lặng lẽ vứt mọi
    khoá không khai, nên `ho_so.py:50-56` CỐ Ý cấp phép cho người sau đổ nguyên `quy_cach_json`
    (có `phi_giao_hang`) vào `_thong_so`. Đường PDF gọi thẳng service, không qua `response_model`
    ⇒ lưới ấy không có ở đây. Bài này là lưới thay thế: nó soi CHUỖI THẬT đi vào bản in.

    Ai thêm một ô vào phiếu mà ô đó mang tiền thì đây là chỗ đỏ lên.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert giay.o, "không bắt được ô nào — bài mất tiền đề, đừng đọc nó là 'không có tiền'"

    chu = giay.chu.lower()
    lot_khoa = [k for k in _KHOA_TIEN if k in chu]
    assert not lot_khoa, f"khoá dữ liệu mang tiền lọt lên giấy: {lot_khoa}"
    lot_nhan = [n for n in _NHAN_TIEN if n in chu]
    assert not lot_nhan, f"nhãn tiền lọt lên giấy: {lot_nhan}"
    # Số kèm ký hiệu tiền tệ ("20.000 đ") — dạng lọt mà không cần nhãn nào. Chỉ nhận DẤU CÁCH
    # giữa số và ký hiệu, không nhận xuống dòng: `giay.chu` nối các ô bằng "\n" nên `\s` sẽ khớp
    # bừa qua ranh giới hai ô ("3" của cột STT + ô kế bắt đầu bằng "đ").
    co_tien = re.search(r"\d[\d.,]*[ ]?(?:đ|₫)(?!\w)", giay.chu)
    assert co_tien is None, f"số tiền lọt lên giấy: {co_tien.group(0) if co_tien else ''}"


def test_giay_in_cot_lop_khong_phai_chi_stt(client, seed_credentials, lenh_that, monkeypatch):
    """Q-02: bảng routing phải mang cột `Lớp`, và `Lớp` KHÁC `STT`.

    `ho_so.py:209-219` giải thích vì sao: bìa và ruột chạy SONG SONG nhưng `thu_tu` của chúng vẫn
    là 1 và 2. Một tờ giấy chỉ đánh số 1→N nói với tổ trưởng rằng bước 12 xong mới tới 13 — sai
    với routing có nhánh. Hai bước cùng `lop` = làm song song được; `lop` lớn hơn = phải đợi.

    Bài này lấp đúng lỗ mà mũi đột biến R5 của lượt rà lại chui qua: rút ruột cột `Lớp`
    (`gia_tri(node.get("lop"))` → `gia_tri("")`) mà cả bộ test vẫn `11 passed`.

    `lenh_that` là chuỗi tuyến tính CTP → In → Đóng gói, nên `lop` = 0/1/2 trong khi STT = 1/2/3
    — hai cột lệch nhau ở MỌI dòng, không dòng nào trùng để lọt.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    dong = _bang_routing(giay, 3)
    assert [d["Công đoạn"] for d in dong] == ["CTP", "In", "Đóng gói"], dong
    assert [d["Lớp"] for d in dong] == ["0", "1", "2"], f"cột Lớp sai: {[d['Lớp'] for d in dong]}"
    assert [d["STT"] for d in dong] == ["1", "2", "3"], "STT phải vẫn còn để người ta gọi 'dòng 2'"


def test_giay_in_nha_gia_cong_cua_buoc_thue_ngoai(
    client, seed_credentials, lenh_thue_ngoai, monkeypatch
):
    """n-04: bước `thue_ngoai` phải mang TÊN nhà gia công lên giấy.

    Bước thuê ngoài mà không ghi giao cho ai thì tổ cầm tờ giấy không biết gọi ai. Trước fixture
    `lenh_thue_ngoai`, nhánh này chưa từng chạy trong bộ test — code đọc thì đúng nhưng "đúng khi
    đọc" là mức bảo đảm mà task này đã hai lần bị bác.

    Canh luôn quyết định "đi CHUNG ô Loại bước, không thành cột riêng": bước không thuê ngoài chỉ
    có `"Máy"` trần, không dính dấu hai chấm hay ô rỗng thừa.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_thue_ngoai}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    theo_ten = {d["Công đoạn"]: d for d in _bang_routing(giay, 3)}
    assert theo_ten["Cán màng"]["Loại bước"] == f"Thuê ngoài: {NHA_GIA_CONG}"
    assert theo_ten["In"]["Loại bước"] == "Máy", "bước nội bộ không được dính tên nhà gia công"


def test_giay_in_ma_dao_va_so_ke(client, seed_credentials, lenh_co_khuon, monkeypatch):
    """Thợ cầm TỜ GIẤY đi lấy dao chứ không mở màn hình — thiếu số kệ ở đây là đứt chuỗi khuôn dù
    phần mềm giữ đủ dữ liệu.

    Đi chung ô "Loại bước" với nhà gia công, cùng lý do (xem `phieu_cong_nghe.routing_rows`): chỉ
    một phần nhỏ số dòng có dao, thêm hẳn một cột là bỏ trống gần hết bảng và ăn mất bề ngang của
    cột Công đoạn.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_co_khuon}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    theo_ten = {d["Công đoạn"]: d for d in _bang_routing(giay, 3)}
    assert theo_ten["Bế"]["Loại bước"] == f"Máy · {KHUON_MA} — {KHUON_KE}"
    assert theo_ten["In"]["Loại bước"] == "Máy", "bước không dùng dao không được dính mã dao"


def test_giay_noi_thang_dao_chua_ve(client, seed_credentials, lenh_co_khuon, sess, monkeypatch):
    """Dao đang đặt làm thì giấy phải nói "chưa về" + ngày dự kiến.

    Im lặng ở ca này là để thợ đi tìm một con dao không tồn tại trong kho — tệ hơn hẳn việc không
    in gì cả, vì tờ giấy trông vẫn đầy đủ.
    """
    dao = sess.query(KhuonBe).filter(KhuonBe.ma == KHUON_MA).one()
    dao.tinh_trang = "dang_dat_lam"
    dao.ngay_ve_du_kien = date(2026, 9, 20)
    sess.commit()

    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_co_khuon}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    theo_ten = {d["Công đoạn"]: d for d in _bang_routing(giay, 3)}
    assert theo_ten["Bế"]["Loại bước"] == f"Máy · {KHUON_MA} — chưa về, dự kiến 20/09/2026"


def test_chan_trang_co_moc_in_va_nguoi_in(client, seed_credentials, lenh_that, monkeypatch):
    """n-03: chân trang mang MỐC IN + NGƯỜI IN, cạnh số trang.

    `pv` trong QR chỉ so được "tờ giấy này là bản cũ" nếu người cầm biết nó in lúc nào; tên người
    in để còn biết hỏi ai khi giấy và màn nói khác nhau. Trước bài này không assert nào chạm chân
    trang — grep `In lúc` / `Người in` trong `backend/tests` ra 0 dòng.
    """
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text

    chan = [s for s in giay.canvas if s.startswith("In lúc ")]
    assert len(chan) == _so_trang(r.content), f"số chân trang ≠ số trang: {chan}"
    # Mốc in là NGÀY GIỜ thật, không phải chuỗi mẫu bỏ quên.
    assert re.fullmatch(r"In lúc \d{2}/\d{2}/\d{4} \d{2}:\d{2} · Người in: .+", chan[0]), chan[0]
    assert f"Trang {len(chan)}" in giay.canvas, giay.canvas


def test_chan_trang_khong_de_len_o_so_trang(
    client, seed_credentials, lenh_that, sess, admin, monkeypatch
):
    """Chân trang phải CẮT THEO BỀ RỘNG THẬT, không theo số ký tự.

    Bản trước cắt cứng 28 ký tự: đo bằng `stringWidth` của chính font đang vẽ thì một tên 28 ký
    tự chạy tới 108,4 mm trong khi ô "Trang 1" bắt đầu ở 99,6 mm — ĐÈ 8,8 mm. Ngưỡng an toàn
    thật là ~21 ký tự, mà tên đầy đủ tiếng Việt 22 ký tự là chuyện thường.

    Bài đi ba mức tên qua ĐÚNG đường thật (đổi `users.name` rồi gọi HTTP), vì `nguoi_in` do router
    lấy từ user đang đăng nhập — không gọi thẳng `render_pdf` để khỏi bỏ qua chính khâu đó.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from app.services.lenh_sx.phieu_cong_nghe import _CO_CHAN_TRANG, _LE_MM
    from app.services.pdf_font import THUONG, dang_ky_font

    dang_ky_font()
    giay = _bat_chu(monkeypatch)
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    ten_thu = ("Admin", "Nguyễn Thị Thanh Hương", "Nguyễn Thị Thanh Hương Trần Quốc Khánh Anh")
    for ten in ten_thu:
        admin.name = ten
        sess.commit()
        r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
        assert r.status_code == 200, r.text

    chan = [s for s in giay.canvas if s.startswith("In lúc ")]
    assert len(chan) == len(ten_thu), chan

    bat_dau_so_trang = A4[0] / 2 - stringWidth("Trang 1", THUONG, _CO_CHAN_TRANG) / 2
    for s in chan:
        het = _LE_MM * mm + stringWidth(s, THUONG, _CO_CHAN_TRANG)
        assert het <= bat_dau_so_trang, (
            f"chân trang chạy tới {het / mm:.1f}mm, đè ô Trang N bắt đầu ở "
            f"{bat_dau_so_trang / mm:.1f}mm: {s!r}"
        )
    # Tên ngắn KHÔNG được cắt oan — nếu không thì "luôn cắt" cũng qua được bài này.
    assert chan[0].endswith("· Người in: Admin"), chan[0]
    assert chan[-1].endswith("…"), f"tên dài phải bị cắt và có dấu …: {chan[-1]!r}"


def test_ngoai_pham_vi_403(client, sale_own, lenh_that):  # noqa: ARG001 (sale_own tạo user)
    h = {"Authorization": f"Bearer {_tok(client, {'username': 'sale_own_ds', 'password': 'x'})}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 403


def test_tai_pdf_khong_tang_phien_ban(client, seed_credentials, lenh_that):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    truoc = client.get(f"/api/lenh-san-xuat/{lenh_that}", headers=h).json()["phien_ban"]
    client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    sau = client.get(f"/api/lenh-san-xuat/{lenh_that}", headers=h).json()["phien_ban"]
    assert sau == truoc


def test_noi_dung_qr_la_hash_url():
    """Sửa gấp của điều phối (đọc trước Task 14): hash fragment, không query string, không token.

    ĐI CÙNG bốn bài `frontend_origin` ở `tests/test_config_guard.py` — xoá một nửa là mất phủ, và
    hai nửa canh hai thứ KHÁC nhau:
      · bài này canh HÌNH DẠNG chuỗi QR (nó tính `base` bằng chính `settings.frontend_origin` nên
        `base` sai thế nào nó cũng không biết);
      · bốn bài kia canh property `frontend_origin` TÍNH đúng (lấy CORS đầu tiên · bỏ `/` cuối ·
        override thắng · rỗng khi không có CORS).
    Đã kiểm hai chiều bằng đột biến: đổi hình dạng chuỗi ⇒ chỉ bài này đỏ; bỏ `.rstrip("/")` trong
    `config.py` ⇒ chỉ bốn bài kia đỏ.
    """
    base = phieu_cong_nghe.settings.frontend_origin
    assert phieu_cong_nghe.noi_dung_qr(123, 2) == f"{base}/#lsx=123&pv=2"
    # `phien_ban=None` vẫn phải ra một chuỗi hợp lệ, không ném lỗi.
    assert phieu_cong_nghe.noi_dung_qr(5, None) == f"{base}/#lsx=5&pv="


def test_font_nhung_co_dau(client, seed_credentials, lenh_that):
    """`lenh_that` có bước "Đóng gói" (dấu tiếng Việt) — PDF phải NHÚNG DejaVuSans, không được
    câm bằng cách bỏ dấu (quyết định bỏ dấu đã bị chủ dự án bác giữa chừng Task 13)."""
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_that}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert b"DejaVuSans" in r.content
