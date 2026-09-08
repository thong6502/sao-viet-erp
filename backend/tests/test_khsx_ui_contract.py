"""Hợp đồng UI của KHSX — soi TRÊN MÃ NGUỒN FE.

Đây là kiểm CẤU TRÚC, không phải kiểm hành vi: nó chứng minh ký tự tồn tại, không chứng minh
render. Đổi `n.buoc.map(...)` thành `n.buoc.filter(...).map(...)` là đỏ dù đúng; để nguyên chuỗi
đó trong một comment thì xanh dù đã xoá sạch UI.

Vẫn giữ vì nó rẻ và bắt được đúng một loại lỗi: ai đó gỡ mất một cửa ghi / một khoá dữ liệu mà
không ai để ý. Nhưng nó KHÔNG còn là bằng chứng duy nhất cho FE — hành vi thật (bấm chọn, gộp,
chip số) nay có test render bằng vitest + jsdom, xem `frontend/src/components/*.test.tsx` và
`test_bang_chung_fe_that_su_ton_tai` ở cuối file này.
"""
import re
from pathlib import Path


DRAWER = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "pages"
    / "LsxBuocDrawer.tsx"
)
DAG_CANVAS = DRAWER.parents[1] / "components" / "DagRoutingCanvas.tsx"
DAG_CSS = DRAWER.parent / "dag-routing.css"
ROUTING = DRAWER.parent / "LsxRoutingTable.tsx"
DETAIL = DRAWER.parent / "LsxDetailView.tsx"


def _nhan(path: Path) -> str:
    """Nguồn JSX đã GỘP KHOẢNG TRẮNG + hạ chữ thường — để so nhãn người dùng đọc được.

    Nhãn trong JSX bị prettier ngắt dòng bất kỳ lúc nào ("Tối đa tăng\\n  năng suất"), và nhãn ô
    nhập ở drawer này viết IN HOA. Bám nguyên văn thì test đỏ vì lý do trình bày chứ không phải
    vì UI mất chữ — đúng cái đã xảy ra sau lần redesign trước.
    """
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).casefold()


def test_drawer_chi_co_mot_o_nhap_so_luot_chay() -> None:
    source = DRAWER.read_text(encoding="utf-8")

    assert source.count('set("so_luot_chay", e.target.value)') == 1
    assert "số lượt chạy qua máy" in _nhan(DRAWER)


def test_cong_doan_khong_khai_loai_thuc_hien_hoac_may_mac_dinh() -> None:
    config = (
        DRAWER.parents[0] / "rebuildCatalogConfigs.tsx"
    ).read_text(encoding="utf-8")
    section = config.split("export const CFG_CONG_DOAN", 1)[1].split(
        "export const CFG_BU_HAO", 1
    )[0]

    assert 'key: "loai_thuc_hien"' not in section
    assert 'key: "may_id"' not in section
    assert "Máy mặc định" not in section


def test_may_khong_con_o_kip_van_hanh() -> None:
    """Máy hết ô người (06/09/2026, mg `0270`): kíp khai MỘT chỗ — định mức đầu việc của công đoạn.

    Trước đây cùng câu hỏi "việc này mấy người làm" có tới bốn ô khai ở bốn màn khác nhau; hễ ai
    khai lệch là hệ điền sai kíp mà không màn nào bày hai số cạnh nhau để phát hiện.
    """
    config = (
        DRAWER.parents[0] / "rebuildCatalogConfigs.tsx"
    ).read_text(encoding="utf-8")
    section = config.split("export const CFG_MAY", 1)[1].split(
        "export const CFG_CONG_DOAN", 1
    )[0]

    assert 'key: "so_nhan_cong"' not in section
    assert "Số người vận hành tiêu chuẩn *" not in section


def test_drawer_khong_goi_y_may_tu_cong_doan() -> None:
    source = DRAWER.read_text(encoding="utf-8")
    assert "Máy mặc định của công đoạn" not in source
    assert "mayGoiYId" not in source


def test_drawer_hien_nhan_luc_ke_thua_va_ket_qua_thoi_gian_o_cuoi() -> None:
    source = _nhan(DRAWER)
    # 21/08/2026: MỘT khối nhân lực dùng chung cho cả bước máy lẫn bước tổ. Trước đó mỗi loại hở
    # một nửa — bước máy có ô kế hoạch mà ba mốc để trống, bước tổ ngược lại — nên nhãn cũ "số
    # người vận hành kế hoạch" không còn.
    # 08/09/2026 (mg `0281`): ô "số người bố trí (kế hoạch)" GỠ HẲN — nó luôn là bản sao của kíp
    # chuẩn (cùng rót từ `cong_doan_dau_viec.so_nguoi_tieu_chuan`) nên hiện hai ô chỉ gây rối.
    # Bám NGUYÊN VĂN NHÃN chứ không bám hai chữ "bố trí": comment lịch sử ngay trên khối nhân lực
    # còn nhắc tên ô cũ, mà file này soi cả comment (xem docstring đầu file).
    assert "số người bố trí (kế hoạch)" not in source
    # 06/09/2026 (mg `0270`): khối ba mốc "biên nhân lực" thu về MỘT ô kíp chuẩn, dùng chung cho
    # cả ba loại bước — nguồn là định mức đầu việc của công đoạn, không còn ô riêng trên máy.
    assert "kíp chuẩn (định mức công đoạn)" in source
    # Kíp chuẩn nay gánh CẢ vai cũ của ô bố trí: bàn xếp lịch cân quân số tổ theo đúng số này.
    assert "cân quân số tổ" in source
    # Bước MÁY: nhân lực không đổi tốc độ máy — nói rõ kíp kế thừa từ đâu (định mức công đoạn).
    # Câu cũ "nhân lực không thay đổi tốc độ máy" nằm ở hint của ô bố trí, gỡ cùng ô đó ở mg `0281`;
    # hint của kíp chuẩn vẫn nói đúng ý ấy, kèm tên máy đang chọn.
    assert "không ảnh hưởng tốc độ máy" in source
    assert "điền sẵn từ định mức đầu việc của công đoạn" in source
    # Bước TỔ: kíp chuẩn RÚT NGẮN thời gian (nhân năng suất/đầu người).
    assert "kíp chuẩn" in source
    assert "rút ngắn thời gian" in source
    # Nguồn tính đứng TRƯỚC kết quả — đọc từ "vì sao ra số này" rồi mới tới con số.
    assert "nguồn tính" in source
    assert "thời gian chiếm máy" in source
    assert "tổng thời gian hoàn thành" in source
    assert source.index("nguồn tính") < source.index("thời gian chiếm máy")


def test_drawer_doi_dau_viec_cap_nhat_dinh_muc_va_thoi_gian_live() -> None:
    source = DRAWER.read_text(encoding="utf-8")
    model = (DRAWER.parent / "lsxBuoc.ts").read_text(encoding="utf-8")

    assert "chonDauViec" in source
    assert "nang_suat_nguoi_gio" in source
    assert "so_nguoi_tieu_chuan" in source
    assert "thoiLuongLive" in source
    assert "export function thoiLuongLive" in model
    # Bước TỔ nhân năng suất với SỐ NGƯỜI TIÊU CHUẨN (chốt 20/08/2026): mirror FE phải đọc đúng cột
    # đó và nhân vào công thức — KHÔNG còn trần `min(kế hoạch, tối đa)` của thiết kế cũ.
    assert "so_nhan_cong_tieu_chuan" in model
    assert "ns * nguoiTC" in model
    assert "Math.min(nguoiKeHoach, nguoiToiDa)" not in model


def test_so_do_bai_ghep_ve_routing_day_du_va_mot_cua_ghi() -> None:
    """Sơ đồ bài ghép: routing ĐẦY ĐỦ từng lệnh, bước chung do NGƯỜI khai, mọi cửa ghi đẩy lên cha.

    Máy/giấy/khổ mà đặt thêm form trong sơ đồ là hai form cùng một dữ liệu, mỗi form một dirty
    state — mầm lệch. Gộp/tách cũng vậy: sơ đồ chỉ gọi callback, cha mới gọi API và `apply()` kết
    quả, nhờ đó bảng thành viên và sơ đồ cùng nhận số mới trong một nhịp.
    """
    # Màn Bài ghép cũ (`BaiGhepPage`/`BaiGhepDetailView`/`BaiGhepSoDo`) gỡ 18/08/2026 — hợp đồng
    # chuyển sang cặp `BaiGhep2Page` (cha, giữ mọi cửa ghi) + `BaiGhepDagCanvas` (sơ đồ, chỉ vẽ).
    sd = (DRAWER.parents[1] / "components" / "BaiGhepDagCanvas.tsx").read_text(encoding="utf-8")
    page = (DRAWER.parent / "BaiGhep2Page.tsx").read_text(encoding="utf-8")

    # KHÔNG tự đúc node in chung: ghép bài chung cả CTP/cán/bế, chọn bước nào là việc của người.
    assert "IN CHUNG TỜ" not in sd
    assert "n.buoc.map" in sd                        # vẽ routing đầy đủ của từng lệnh
    assert "gop_duoc" in sd                          # bước bị đè vẫn còn, chỉ mang thêm dấu
    assert "toa_step_key" in sd                      # điểm toả suy từ bước gộp cuối cùng
    assert "bgsd-node--ngoai" in sd                  # tiền nhiệm ngoài bài → node bóng mờ
    assert "onMoLenh" in sd                          # nhánh chỉ đọc, bấm là điều hướng
    # Chọn → gộp → tách, và kiểm vòng hỏi TRƯỚC khi cho bấm.
    assert "onGop" in sd and "onTach" in sd
    assert "onHoiUngVien" in sd
    # Sơ đồ KHÔNG tự gọi API ghi — chỉ đẩy lên cha, để bảng thành viên và sơ đồ nhận số mới cùng nhịp.
    for cua_ghi in ("api.baiGhep2.update", "api.baiGhep2.gop", "api.baiGhep2.tach",
                    "api.baiGhep2.luuBuocChung"):
        assert cua_ghi not in sd, f"{cua_ghi} phải gọi ở cha, không gọi trong sơ đồ"
        assert cua_ghi in page, f"{cua_ghi} biến mất khỏi màn cha — cửa ghi bị gỡ mất"
    assert "BaiGhepDagCanvas" in page


def test_thue_ngoai_khong_co_o_nao_rieng_ngoai_buoc_may() -> None:
    """Bước THUÊ NGOÀI nhập liệu Y HỆT bước máy — không được có ô/tab nào của riêng nó.

    Nhà thầu khai như một MÁY trong danh mục (tên kèm hậu tố "thuê ngoài – <nhà in>"), nên mọi
    khối "gia công ngoài" cũ (đối tác · số gửi · ngày gửi/nhận · đơn giá gia công · sổ giao–nhận)
    đã GỠ khỏi màn kế hoạch. Guard neo vào ĐỊNH DANH MÁY, không vào chữ hiển thị.

    Cột `nha_cung_cap` và cửa ghi `POST …/giao-nhan` ở server VẪN CÒN (dữ liệu cũ + ảnh chụp cho
    kho) — guard này chỉ gác phần MÀN KẾ HOẠCH.
    """
    drawer = DRAWER.read_text(encoding="utf-8")
    bang = (DRAWER.parent / "LsxRoutingTable.tsx").read_text(encoding="utf-8")
    card = (DRAWER.parents[1] / "components" / "DagNodeCard.tsx").read_text(encoding="utf-8")

    for src in (drawer, bang, card):
        assert '"giao_nhan"' not in src
        assert "khsx-gn-badge" not in src
        assert "onGiaoNhan(" not in src
    # Nút chọn loại bước phải BÀY LẠI "Thuê ngoài" (trước đó bị ẩn khỏi danh sách).
    assert 'LOAI_BUOC_ORDER: LsxLoaiBuoc[] = ["may", "to", "thue_ngoai"]' in drawer
    # Và nó đi CHUNG đường với bước máy khi đổi loại (kíp lấy theo máy, không theo bảng khoán tổ).
    assert 'if (k === "may" || k === "thue_ngoai") {' in drawer



def test_dag_noi_duoc_phu_thuoc_xuyen_lsx_ngay_tren_so_do() -> None:
    """Bước LSX khác cùng đơn phải NHÌN THẤY + NỐI ĐƯỢC ngay trên canvas, không bắt mở drawer."""
    source = DAG_CANVAS.read_text(encoding="utf-8")
    css = DAG_CSS.read_text(encoding="utf-8")

    # Ngăn trái liệt kê bước của lệnh khác và kéo được thẳng vào canvas
    assert "railGroups" in source
    assert "handleRailMouseDown" in source
    assert "Bước LSX khác" in source
    # Tiền nhiệm ngoài lệnh hiện thành node bóng mờ chỉ-đọc (chỉ có cổng Ra)
    assert "ghostKeysCua" in source
    assert "DagGhostNodeCard" in source
    assert 'dag-node--ngoai' in source
    assert 'dag-port--in' not in source.split("function DagGhostNodeCard", 1)[1].split(
        "export function DagRoutingCanvas", 1
    )[0]
    # Kéo bắt đầu ngoài viewport nên phải có mouseup ở cấp window để không treo dây nháp
    assert 'window.addEventListener("mouseup"' in source
    assert ".dag-rail" in css
    assert ".dag-node--ngoai" in css


def test_drawer_van_giu_duong_chon_phu_thuoc_bang_ban_phim() -> None:
    """Canvas kéo-thả là chuột; drawer vẫn là đường a11y để chọn tiền nhiệm."""
    source = DRAWER.read_text(encoding="utf-8")
    # Cùng lý do như test giao–nhận ở trên: tiêu đề đổi "Phụ thuộc ĐỂ xếp lịch" → "Phụ thuộc xếp
    # lịch" khi dựng lại drawer 16/08/2026. Neo vào `phu_thuoc_step_keys` — mất khoá đó thì đường
    # chọn tiền nhiệm bằng bàn phím mới thật sự biến mất.
    assert "phu_thuoc_step_keys" in source
    assert "phuThuocRefs" in source


def test_dag_co_thanh_keo_ngang_va_van_giu_sap_xep_tu_dong() -> None:
    source = DAG_CANVAS.read_text(encoding="utf-8")
    css = DAG_CSS.read_text(encoding="utf-8")

    assert "computeCanvasWidth" in source
    assert "computeCanvasHeight" in source
    assert "computeViewportHeight" in source
    assert "handleAutoLayout" in source
    # Xếp lại là trả tầm nhìn về mặc định. Mặc định nay là THU VỪA KHUNG chứ không phải 100%:
    # chuỗi 5 bước đã rộng hơn khung nên để 100% là xếp gọn xong vẫn phải cuộn mới thấy bước cuối.
    assert "thuVuaKhung(auto)" in source
    assert "tinhZoomVua" in source
    assert "scrollLeft = 0" in source
    assert "overflow: auto" in css
    assert "height: 580px" not in css


def test_bang_chung_fe_that_su_ton_tai() -> None:
    """Bộ test render của FE phải còn sống và phải được CI chạy.

    Không kiểm nội dung test FE ở đây (vô nghĩa — lại grep chuỗi). Chỉ chốt đúng hai điều mà xoá
    đi thì cả module mất bằng chứng hành vi mà pytest vẫn xanh: file test còn đó, và cổng kiểm
    còn gọi nó. Thư mục có test nhưng CI không chạy còn tệ hơn không có test: nhìn vào tưởng
    phần đó đã được khoá.
    """
    goc = DRAWER.parents[3]          # …/frontend/src/pages/X.tsx → gốc repo
    canvas_test = goc / "frontend" / "src" / "components" / "BaiGhepDagCanvas.test.tsx"
    assert canvas_test.exists(), "mất test render của canvas bài ghép"

    pkg = (goc / "frontend" / "package.json").read_text(encoding="utf-8")
    assert '"test"' in pkg and "vitest" in pkg

    ci = (goc / ".github" / "workflows" / "build-test.yml").read_text(encoding="utf-8")
    assert "npm test" in ci, "cổng kiểm không chạy test FE thì test FE sẽ mục"


def test_lenh_giu_cho_vat_tu_thi_bang_routing_khoa_va_noi_ra() -> None:
    """Giữ chỗ vật tư khoá routing ở SERVER — màn phải khoá theo và nói đường lùi.

    `LsxService._chan_dang_giu_cho` chặn `PUT /routing` VÀ `POST /xem-truoc-routing`. Để bảng sửa
    được lúc đó là mời người ta làm không công: mỗi lần đổi công đoạn ăn một 409, mà `xemTruocChuoi`
    từng nuốt im lặng nên số vào–ra đứng im không ai giải thích, tới lúc bấm Lưu mới hiện băng đỏ.
    """
    source = ROUTING.read_text(encoding="utf-8")

    assert "const suaDuoc = canUpdate && !giuCho;" in source
    # Mọi CỬA GHI phải đi qua `suaDuoc`. Còn sót `canUpdate` trần trong JSX là còn một đường sửa
    # mở ra trong lúc server đang khoá — đúng cái lỗ này.
    assert "{canUpdate && (" not in source
    assert "canUpdate={canUpdate}" not in source
    assert "draggable={suaDuoc}" in source
    # Băng nói lý do + đường lùi, và nó phải là băng RIÊNG (điều kiện `canUpdate && giuCho`), không
    # dựa vào `suaDuoc` — `suaDuoc` đã false nên dùng nó là băng không bao giờ hiện.
    assert "{canUpdate && giuCho && (" in source
    assert "khsx-ghep-bang--khoa" in source
    assert "Nhả chỗ" in source

    # Cha phải THẬT SỰ truyền cờ xuống, không thì bảng luôn nghĩ là không giữ chỗ.
    assert "giuCho={d.giu_cho_bat}" in DETAIL.read_text(encoding="utf-8")


def test_xem_truoc_chuoi_hong_thi_phai_noi_ra_chu_khong_nuot() -> None:
    """Số vào–ra là do SERVER tính. Xem trước hỏng mà im lặng = bảng hiện số CŨ như thể vừa tính."""
    source = ROUTING.read_text(encoding="utf-8")

    assert "khsx-ghep-bang--loi" in source
    # CẢ HAI chặng của "đổi công đoạn" phải báo ra: lấy mặc định công đoạn (`mac-dinh-buoc`, từng
    # 500 câm) và tính lại số cả chuỗi (`xem-truoc-routing`, từng 409 câm). Một chỗ đặt là đủ để
    # test xanh mà chỗ kia vẫn nuốt, nên đếm.
    assert source.count("setLoiDoiCd(") >= 3
    # Nhánh catch RỖNG là cách lỗi cũ sống được lâu đến thế: bắt lỗi xong không nói gì. Câu trấn an
    # trong đó ("bấm Lưu server vẫn tính đúng") còn SAI — lưu cũng 409 y hệt khi lệnh đang giữ chỗ.
    assert "server v" + "ẫn tính đúng" not in source


def test_giu_cho_vat_tu_khong_con_gi_de_khoa_o_cum_thong_so() -> None:
    """Giữ chỗ vật tư chặn ba đường ở server: `so_luong_dat`, `quy_cach`, xoá lệnh.

    Từ 07/09/2026 cụm quy cách ở lệnh CHỈ XEM — ô Giấy, ngoại lệ cuối cùng, đã gỡ — nên `luu()`
    không bao giờ gửi `quy_cach` nữa: giữ chỗ không còn gì để khoá trong cụm này, và băng "ô Giấy
    khoá luôn" phải đi theo, không thì màn đi báo khoá một ô không còn trên màn. Hai chỗ giữ chỗ
    VẪN khoá là bảng công đoạn (băng riêng, xem test ở trên) và nút Xoá (chip riêng).
    """
    source = DETAIL.read_text(encoding="utf-8")

    assert "const giuCho = !!d?.giu_cho_bat;" in source
    # Không còn cờ "được sửa quy cách" nào — còn sót một cái là còn một ô quy cách gõ được ở lệnh.
    assert "suaQc" not in source
    assert "suaGiay" not in source
    # `luu()` không gửi cụm thông số ⇒ không có đường nào ăn 409 vì giữ chỗ.
    assert "body.quy_cach" not in source
    # Băng khoá của cụm thông số đã gỡ khỏi màn lệnh; chip khoá nút Xoá thì còn nguyên.
    assert "khsx-ghep-bang--khoa" not in source
    assert "giuCho ? (" in source
    assert "khsx-khoa-chip" in source


def test_quy_cach_o_lenh_chi_xem_khong_con_o_nao_sua_duoc() -> None:
    """Quy cách là thứ đã CHỐT với khách ở phiếu tính giá — lệnh không gõ lại, KỂ CẢ giấy.

    Khổ giấy nguyên / khổ tờ / khổ thành phẩm / cách in / số trang / bleed / khe cắt / mực / bình
    bài đều chỉ xem, và từ 07/09/2026 ô Giấy cũng vậy. Phiếu tính ra sao thì lệnh chạy y như vậy;
    muốn đổi thì sửa ở phiếu rồi tạo lại lệnh. Không còn ai sửa `form.qc` ⇒ đường xem-trước-số-máy-
    tự-tính cũng không còn việc gì để làm.
    """
    source = DETAIL.read_text(encoding="utf-8")

    # Không còn ô gõ số nào trong cụm: `KVNum` (ô nhập) đã thay bằng `KVSo` (chỉ hiện).
    assert "function KVNum(" not in source
    assert "function KVSo(" in source
    assert "<KVNum" not in source
    # `setQc` GỠ HẲN, không phải "chỉ còn một chỗ gọi" như bản 05/09/2026.
    assert "setQc" not in source
    # Bình bài (`so_con`) cũng là số kế hoạch giấy — Task 23 đã chặn ở server, màn không mở lại.
    assert 'set("so_con"' not in source
    # Xem trước chỉ phục vụ việc SỬA. Sửa gỡ rồi mà còn gọi là mỗi lần mở lệnh đi hỏi server một
    # con số không ai dùng. (`xemTruocMay` / `xemTruocRouting` của bảng công đoạn thì vẫn còn.)
    assert "api.lsx.xemTruocQuyCach(" not in source
    assert "setXemTruoc" not in source
    # Ô số dẫn xuất không còn cặp cũ/mới để so — chip "tính lại" đi cùng.
    assert "function KVDeriv(" not in source
    assert "tính lại</span>" not in source
    # Nhãn khối phải nói đúng cái đang cho phép, không thì màn tự cãi nhau.
    assert "thông số — chỉ xem" in _nhan(DETAIL)
    assert "đổi được giấy khi thiếu hàng" not in _nhan(DETAIL)
    # Và nói ra đường đi tiếp: sửa quy cách là việc của phiếu tính giá, không phải của lệnh.
    assert "muốn đổi thì sửa ở phiếu tính giá" in _nhan(DETAIL)


def test_lenh_giu_cho_vat_tu_thi_khong_con_nut_xoa() -> None:
    """`LsxService.xoa` cũng gọi `_chan_dang_giu_cho` — để nút Xoá sáng là mời bấm vào 409."""
    source = DETAIL.read_text(encoding="utf-8")

    assert "giuCho ? (" in source
    assert "khsx-khoa-chip" in source
    assert "chưa xoá được" in source
    # Chip phải NÓI lý do trên mặt, không phải nút mờ chỉ có tooltip.
    assert 'className="khsx-khoa-chip"' in source
    assert ".khsx-khoa-chip {" in (DRAWER.parent / "ke-hoach-sx.css").read_text(encoding="utf-8")


def test_o_giay_o_lenh_da_go_han_khong_con_cua_doi() -> None:
    """Đổi giấy Ở KHỐI QUY CÁCH là đổi bài toán giá — phải quay về phiếu tính giá rồi TẠO LẠI lệnh.

    Ô chọn giấy ở lệnh (mở 13/08/2026, bó vào `thay_the_ids` của danh mục 05/09/2026) GỠ HẲN
    07/09/2026. Còn sót một mảnh nào của đường đó là còn một cửa đổi giấy ngay tại lệnh.

    [08/09/2026] Danh mục Giấy được nạp LẠI ở màn này, nhưng cho việc KHÁC HẲN: đổ vào ô "Thêm vật
    tư" của từng BƯỚC để người lập lệnh chọn NVL chính. Đó không phải cửa đổi quy cách — quy cách
    vẫn chỉ-xem, và dòng giấy ở bước là một dòng vật tư như mọi dòng khác. Nên guard đổi từ "cấm
    nạp danh mục giấy" sang "nạp thì chỉ được chảy vào bảng routing".
    """
    source = DETAIL.read_text(encoding="utf-8")

    assert '<KV k="Giấy" v={s("giay_ten")} />' in source
    assert "giayChonDuoc" not in source
    assert "giayNeoId" not in source
    assert "thay_the_ids" not in source
    assert "chưa chọn giấy" not in source
    # Danh mục giấy chỉ có ĐÚNG một cửa ra: prop `giayRefs` của bảng routing (→ drawer bước).
    assert "vat-lieu-kho/giay" in source and "setGiayRefs" in source
    assert "giayRefs={giayRefs}" in source
    assert source.count("giayRefs") == 3, (
        "`giayRefs` chỉ được xuất hiện ĐÚNG ba lần: khai state, tên prop, giá trị prop "
        "(`giayRefs={giayRefs}`) — thêm chỗ đọc nào nữa là đang mở lại cửa đổi giấy ở lệnh"
    )
