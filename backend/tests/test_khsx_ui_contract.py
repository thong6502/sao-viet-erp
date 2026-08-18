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


def test_may_hien_o_kip_van_hanh_tieu_chuan() -> None:
    config = (
        DRAWER.parents[0] / "rebuildCatalogConfigs.tsx"
    ).read_text(encoding="utf-8")
    section = config.split("export const CFG_MAY", 1)[1].split(
        "export const CFG_CONG_DOAN", 1
    )[0]

    assert 'key: "so_nhan_cong"' in section
    assert "Số người vận hành tiêu chuẩn" in section


def test_drawer_khong_goi_y_may_tu_cong_doan() -> None:
    source = DRAWER.read_text(encoding="utf-8")
    assert "Máy mặc định của công đoạn" not in source
    assert "mayGoiYId" not in source


def test_drawer_hien_nhan_luc_ke_thua_va_ket_qua_thoi_gian_o_cuoi() -> None:
    source = _nhan(DRAWER)
    # Bước MÁY: nhân lực không đổi tốc độ máy — nói rõ kíp tiêu chuẩn kế thừa từ đâu.
    assert "số người vận hành kế hoạch" in source
    assert "kíp vận hành tiêu chuẩn" in source
    # Bước TỔ: người kế hoạch đổi được, kèm định mức và trần tăng năng suất.
    assert "số người kế hoạch" in source
    assert "định mức nhân lực" in source
    assert "trần thời gian" in source
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
    assert "so_nguoi_toi_da" in source
    assert "thoiLuongLive" in source
    assert "export function thoiLuongLive" in model
    assert "Math.min(nguoiKeHoach, nguoiToiDa)" in model


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


def test_thue_ngoai_co_so_giao_nhan_va_chi_mot_cua_ghi() -> None:
    """Sổ giao–nhận nằm trong drawer; badge ở bảng/sơ đồ chỉ để NHÌN và NHẢY vào sổ.

    Hai cửa ghi cho cùng một sự kiện là mầm lệch dữ liệu — badge không được tự ghi.
    """
    drawer = DRAWER.read_text(encoding="utf-8")
    bang = (DRAWER.parent / "LsxRoutingTable.tsx").read_text(encoding="utf-8")
    node = DRAWER.parents[1] / "components" / "DagNodeCard.tsx"
    card = node.read_text(encoding="utf-8")

    # Neo vào ĐỊNH DANH MÁY (`"giao_nhan"`), không vào chữ hiển thị.
    #
    # 16/08/2026: drawer được dựng lại theo tab, khối "Thực tế giao – nhận" (id `sec-giao-nhan`)
    # thành tab `giao_nhan`. Hai assert cũ grep đúng hai chuỗi đó nên đỏ — trong khi MỌI bảo đảm
    # thật vẫn còn (nút xác nhận · `onGiaoNhan(` · `toBody` sạch · badge không ghi; đã kiểm từng
    # cái một trước khi sửa test này).
    #
    # Guard đọc chữ hiển thị thì mỗi lần đổi nhãn là một lần đỏ oan, mà guard kêu oan thì sớm muộn
    # bị tắt — lúc đó mất luôn phần đáng gác. Khoá máy vẫn đỏ khi tính năng bị GỠ THẬT.
    assert '"giao_nhan"' in drawer
    assert "Xác nhận đã giao" in drawer and "Xác nhận đã nhận" in drawer
    # Ghi THẲNG qua cửa thực thi, KHÔNG gom vào payload lưu routing (payload đó bị guard
    # "đã lập kế hoạch" chặn, mà hàng ra cổng đúng lúc lệnh đang chạy).
    assert "onGiaoNhan(" in drawer
    to_body = (DRAWER.parent / "lsxBuoc.ts").read_text(encoding="utf-8").split(
        "export function toBody", 1
    )[1]
    for f in ("giao_luc", "nhan_luc", "sl_giao_thuc", "sl_nhan_thuc", "nguoi_giao", "nguoi_nhan"):
        assert f not in to_body
    # Badge chỉ điều hướng: bấm là mở drawer đúng khối, không có lời gọi ghi nào.
    for src in (bang, card):
        assert "khsx-gn-badge" in src
        assert 'onOpenDrawer(index, "giao_nhan")' in src or '"giao_nhan")' in src
        assert "api.lsx.giaoNhan" not in src


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
