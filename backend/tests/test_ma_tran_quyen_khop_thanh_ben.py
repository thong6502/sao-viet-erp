"""Guard: MA TRẬN PHÂN QUYỀN phải soi đúng cái thanh bên đang bày ra.

Luật của chủ dự án (24/09/2026): *"một module thì nó là một cái bên sidebar, một phân hệ sẽ bao
gồm nhiều module"*. Ba hệ quả kiểm được bằng máy:

  1. Mục menu nào cũng phải có DÒNG trong ma trận — không thì cấp quyền xong người ta vẫn không
     hiểu vì sao màn đó không hiện, vì chẳng có ô nào mang tên nó.
  2. Dòng nào cũng phải nằm trong một PHÂN HỆ — rơi vào nhóm "Khác" ở cuối là coi như tàng hình:
     nhóm đó mặc định thu gọn khi chưa cấp gì.
  3. Tên phân hệ phải TRÙNG chữ với khối tương ứng của thanh bên — hai bộ tên khác nhau cho cùng
     một thứ thì người cấp quyền phải tự dịch trong đầu.

VỠ THẬT (chính là lý do file này ra đời): bốn khoá `lenh_san_xuat` · `theo_doi_san_xuat` ·
`tai_san` · `dm_xe` có mục menu đàng hoàng nhưng không ai khai vào `MODULE_GROUPS`, nên suốt từ
31/08 → 24/09/2026 chúng nằm im trong nhóm "Khác". Không test nào đỏ, không lỗi nào hiện; chỉ có
người mở hộp thoại "Thêm vai trò" ra mới thấy.

Guard đọc THẲNG mã nguồn giao diện (`Sidebar.tsx` · `PermissionMatrix.tsx`) bằng regex — cùng lối
`test_giao_dien_khop_may_chu.py`. Đổi cấu trúc hai file đó thì sửa bộ đọc ở đây, đừng xoá test.
"""

from __future__ import annotations

import re
from pathlib import Path

FE = Path(__file__).resolve().parents[2] / "frontend" / "src"
SIDEBAR = FE / "components" / "Sidebar.tsx"
MA_TRAN = FE / "components" / "PermissionMatrix.tsx"

#: Khoá có mục menu nhưng CỐ Ý không có dòng trong ma trận — kèm lý do.
KHOA_KHONG_BAY_MA_TRAN: dict[str, str] = {
    "bai_ghep_2":
        "Mục 'Bài ghép' đang ẩn theo cờ `BAI_GHEP_ENABLED` (10/09/2026). Khoá vẫn khai trong "
        "`MODULE_GROUPS`, chỉ bị `MODULE_DA_NGUNG` lọc khi cờ tắt — bật cờ là hiện lại cả hai đầu.",
}

#: Khoá có dòng trong ma trận nhưng KHÔNG có mục menu nào — kèm lý do.
#:
#: HIỆN RỖNG, và nên giữ nguyên như vậy. BA khoá từng thuộc diện này đều đã GỠ HẲN trong ngày
#: 24/09/2026 thay vì khai ngoại lệ — đọc kỹ trước khi thêm tên vào đây: ô nào không dẫn tới một
#: mục thanh bên thì hoặc là Ô CHI TIẾT của màn chứa nó, hoặc không nên tồn tại. Cả ba rơi vào
#: vế đầu:
#:   • `vai_tro` (mg `0330`) — chủ chốt bác thẳng *"làm gì có module vai trò đâu"* ⇒ ô
#:     `phong_ban` + ô chi tiết `phong_ban:manage_permissions`.
#:   • `nguoi_dung` (mg `0331`) — *"gộp luôn người dùng vào hồ sơ nhân sự đi"*: màn 'Người dùng'
#:     đã bỏ, tài khoản là tab 'Tài khoản & Quyền' CỦA màn Hồ sơ nhân sự ⇒ ô `nhan_su` + bốn ô
#:     chi tiết `reset_password` · `lock` · `revoke_sessions` · `assign_role`.
#:   • `yeu_cau_sua_chua` (mg `0332`) — *"bên thanh bên có 2 module sao ở quyền lại có 3"*: 'Báo
#:     máy hỏng' là TAB của màn 'Sửa chữa máy' ⇒ ô `ky_thuat_may` + ô chi tiết `can_request`.
#:     Lý do cũ ("cửa thứ hai của cùng một màn") KHÔNG đủ để giữ một dòng ma trận: người đi cấp
#:     quyền nhìn thanh bên đếm 2 mục mà ma trận bày 3 dòng thì họ không nối được với cái gì.
KHOA_KHONG_CO_MUC_MENU: dict[str, str] = {}


#: Khoá mà NHÃN trong ma trận cố ý KHÁC chữ của mục menu — kèm lý do.
NHAN_LECH_CO_LY_DO: dict[str, str] = {
    "kho":
        "Khoá `kho` gác NHIỀU mục cùng lúc: 'Yêu cầu nhập xuất' + mỗi KHO ĐÃ KHAI BÁO (mục động "
        "`kho-item:<id>` do AppShell tiêm, nhãn là TÊN KHO trong DB). Không thể lấy nhãn của một "
        "mục nào làm tên ô, nên giữ tên khối 'Kho hàng'. Đây KHÔNG phải ăn ké: các kho là DỮ "
        "LIỆU của cùng một màn, không phải màn khác — kho nào được xem do khai báo kho + phạm vi "
        "quyết định, không phải một ô quyền mỗi kho.",
    "phieu_chi":
        "Nhãn mục menu là biến `VOUCHER_PAGE_LABEL` (frontend/src/constants/features.ts): 'Phiếu "
        "chi / UNC' khi `UNC_ENABLED`, 'Phiếu chi' khi tắt. Máy chủ không đọc được cờ giao diện "
        "nên nhãn ô giữ tên ngắn 'Phiếu chi'.",
}


def _nguon(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _bo_chu_thich(s: str) -> str:
    """Bỏ chú thích `//` để regex không vớ phải khoá nằm trong lời giải thích."""
    return re.sub(r"^\s*//.*$", "", s, flags=re.M)


def _khoa_cua_thanh_ben() -> set[str]:
    """Mọi khoá module mà một mục menu gác lên: `module:` + danh sách `modules:` của mục đó."""
    s = _bo_chu_thich(_nguon(SIDEBAR))
    # Cắt đúng phần khai `NAV` (phía dưới còn `MODULE_BY_NAV_ID`, `AUTHENTICATED_NAV_IDS`…).
    nav = s.split("export const NAV: NavSection[] = [", 1)[1].split("\n];", 1)[0]
    khoa = set(re.findall(r'\bmodule:\s*"([a-z_0-9]+)"', nav))
    for blob in re.findall(r"\bmodules:\s*\[([^\]]*)\]", nav):
        khoa |= set(re.findall(r'"([a-z_0-9]+)"', blob))
    assert khoa, "không đọc được khoá module nào từ Sidebar.tsx"
    return khoa


def _nhom_cua_ma_tran() -> list[tuple[str, list[str]]]:
    """[(nhãn phân hệ, [khoá module…])] theo đúng thứ tự khai trong `MODULE_GROUPS`."""
    s = _bo_chu_thich(_nguon(MA_TRAN))
    khoi = s.split("const MODULE_GROUPS", 1)[1].split("\n];", 1)[0]
    nhom = []
    for m in re.finditer(r'label:\s*"([^"]+)",\s*modules:\s*\[([^\]]*)\]', khoi, re.S):
        nhom.append((m.group(1), re.findall(r'"([a-z_0-9]+)"', m.group(2))))
    assert nhom, "không đọc được nhóm nào từ MODULE_GROUPS"
    return nhom


def _nhan_muc_menu() -> dict[str, str]:
    """{khoá module: nhãn mục menu} — chỉ những mục có nhãn là CHUỖI viết thẳng.

    Đọc theo mảnh: mỗi mục menu mở đầu bằng `id: "..."`, và `label:` / `module:` gần nhất sau đó
    thuộc về chính nó. Mảnh nào gặp `items:` trước `module:` là một SECTION, không phải mục.
    Nhãn viết bằng BIẾN (`label: VOUCHER_PAGE_LABEL`) thì không đọc được ở đây — khoá đó phải khai
    trong `NHAN_LECH_CO_LY_DO` để không âm thầm lọt qua guard.
    """
    s = _bo_chu_thich(_nguon(SIDEBAR))
    nav = s.split("export const NAV: NavSection[] = [", 1)[1].split("\n];", 1)[0]
    ra: dict[str, str] = {}
    for manh in nav.split('id: "')[1:]:
        m_khoa = re.search(r'module:\s*"([a-z_0-9]+)"', manh)
        if m_khoa is None:
            continue
        m_items = re.search(r"\bitems:\s*\[", manh)
        if m_items is not None and m_items.start() < m_khoa.start():
            continue  # section, không phải mục menu
        m_nhan = re.search(r'label:\s*"([^"]*)"', manh)
        if m_nhan is None or m_nhan.start() > m_khoa.start():
            continue  # nhãn viết bằng biến
        ra[m_khoa.group(1)] = m_nhan.group(1)
    assert ra, "không đọc được cặp (nhãn, khoá) nào từ Sidebar.tsx"
    return ra


def _nhan_may_chu() -> dict[str, str]:
    """{khoá module: nhãn máy chủ trả ra ma trận} — `seed.MODULES` là nguồn duy nhất."""
    from app.seed import MODULES

    return dict(MODULES)


def _nhan_khoi_thanh_ben() -> list[str]:
    s = _bo_chu_thich(_nguon(SIDEBAR))
    nav = s.split("export const NAV: NavSection[] = [", 1)[1].split("\n];", 1)[0]
    # Nhãn của SECTION nằm ở ĐÚNG mức thụt 4 dấu cách trong `NAV` (mục menu thụt sâu hơn) —
    # bám thụt lề là cách rẻ nhất để không phải viết một bộ phân tích TypeScript ở đây.
    return re.findall(r'^ {4}label: "([^"]+)",$', nav, re.M)


def test_moi_muc_menu_deu_co_dong_trong_ma_tran():
    """Mục menu không có dòng ⇒ không ai cấp được màn đó bằng giao diện."""
    trong_nhom = {k for _, ks in _nhom_cua_ma_tran() for k in ks}
    thieu = sorted(
        k for k in _khoa_cua_thanh_ben()
        if k not in trong_nhom and k not in KHOA_KHONG_BAY_MA_TRAN
    )
    assert not thieu, (
        "Thanh bên gác mấy khoá này nhưng MA TRẬN PHÂN QUYỀN không có dòng nào: "
        + ", ".join(thieu)
        + " — quản trị mở 'Thêm vai trò' ra sẽ không thấy ô nào mang tên màn đó. Khai vào "
        "`MODULE_GROUPS` (PermissionMatrix.tsx) ở đúng phân hệ, hoặc vào "
        "`KHOA_KHONG_BAY_MA_TRAN` kèm lý do nếu ẩn là có chủ ý."
    )


def test_moi_dong_ma_tran_deu_co_mot_muc_menu():
    """Dòng không có màn ⇒ cấp cũng như không: tick xong chẳng có gì hiện ra."""
    tren_menu = _khoa_cua_thanh_ben()
    mo_coi = sorted(
        k for _, ks in _nhom_cua_ma_tran() for k in ks
        if k not in tren_menu and k not in KHOA_KHONG_CO_MUC_MENU
    )
    assert not mo_coi, (
        "Ma trận bày mấy dòng này nhưng thanh bên không có mục menu nào gác chúng: "
        + ", ".join(mo_coi)
        + " — cấp ô xong người dùng vẫn không có đường vào bằng chuột. Thêm mục vào Sidebar, "
        "hoặc khai vào `KHOA_KHONG_CO_MUC_MENU` kèm lý do."
    )


def test_khong_con_khoa_nao_roi_vao_nhom_khac():
    """Nhóm 'Khác' là LƯỚI AN TOÀN, không phải chỗ ở.

    Nó dựng ĐỘNG từ ma trận máy chủ trả về nên không đọc tĩnh được; thay vào đó guard soi nguồn
    sinh ra nó: mọi khoá mà máy chủ seed đều phải có nhà trong `MODULE_GROUPS`, trừ những khoá đã
    khai lý do (ô ẩn / ô chết)."""
    from app.seed import MODULES

    trong_nhom = {k for _, ks in _nhom_cua_ma_tran() for k in ks}
    # Ô đã ngừng bày (khai ở `MODULE_DA_NGUNG` bên giao diện) — đọc thẳng cho khỏi chép tay.
    s = _nguon(MA_TRAN)
    da_ngung = set(re.findall(
        r'"([a-z_0-9]+)"',
        s.split("const MODULE_DA_NGUNG = new Set([", 1)[1].split("]);", 1)[0],
    ))
    ngoai = sorted(
        k for k, _ in MODULES
        if k not in trong_nhom and k not in da_ngung and k not in KHOA_KHONG_BAY_MA_TRAN
    )
    assert not ngoai, (
        "Mấy khoá máy chủ seed này không thuộc phân hệ nào nên rơi xuống nhóm 'Khác' ở cuối ma "
        "trận: " + ", ".join(ngoai) + " — nhóm đó mặc định THU GỌN khi chưa cấp gì, nên module "
        "coi như tàng hình. Khai vào `MODULE_GROUPS` ở đúng phân hệ."
    )


def test_nhan_o_quyen_trung_chu_voi_muc_menu():
    """Ô quyền phải mang ĐÚNG TÊN mục menu nó gác.

    Ma trận là thứ quản trị đọc rồi đi tìm màn tương ứng trên thanh bên. Hai bộ tên cho cùng một
    màn thì họ phải tự dịch trong đầu: "Dashboard" ↔ Trang chủ, "Tự phục vụ" ↔ Hồ sơ của tôi,
    "Đơn mua hàng (Kế toán)" ↔ Đơn mua hàng, "Tài sản & Công cụ dụng cụ" ↔ Tài sản & CCDC,
    "Nhật ký hoạt động" ↔ Nhật ký. Cả năm đều lệch thật tới 24/09/2026, chính chủ dự án chỉ ra.
    """
    tren_menu = _nhan_muc_menu()
    may_chu = _nhan_may_chu()
    lech = sorted(
        f"{k}: máy chủ '{may_chu[k]}' ≠ menu '{nhan}'"
        for k, nhan in tren_menu.items()
        if k in may_chu and may_chu[k] != nhan and k not in NHAN_LECH_CO_LY_DO
    )
    assert not lech, (
        "Nhãn ô quyền không trùng chữ với mục menu nó gác:\n  " + "\n  ".join(lech)
        + "\nSửa nhãn ở `seed.MODULES` (seed_modules tự đồng bộ vào DB mỗi lần khởi động), hoặc "
        "khai vào `NHAN_LECH_CO_LY_DO` kèm lý do."
    )


def test_nhom_tong_quan_du_hai_dong():
    """Khối 'Tổng quan' của thanh bên có hai mục ⇒ nhóm 'Tổng quan' phải có hai dòng.

    Chốt cụ thể 24/09/2026 (chủ dự án đối chiếu ảnh chụp hai bên): nhóm này chỉ bày một dòng
    'Dashboard' trong khi thanh bên có Trang chủ + Hồ sơ của tôi. Test này canh đúng cặp đó thay vì
    tin vào `KHOA_KHONG_BAY_MA_TRAN` — ẩn `self_service` lại là đỏ ngay.
    """
    nhom = dict(_nhom_cua_ma_tran())
    assert nhom.get("Tổng quan") == ["dashboard", "self_service"], (
        "Nhóm 'Tổng quan' phải có ĐÚNG hai dòng theo đúng thứ tự menu: `dashboard` (Trang chủ) rồi "
        f"`self_service` (Hồ sơ của tôi). Đang là: {nhom.get('Tổng quan')}"
    )


def test_ten_phan_he_trung_voi_khoi_thanh_ben():
    """Hai bộ tên cho cùng một khối thì người cấp quyền phải tự dịch trong đầu."""
    khoi = set(_nhan_khoi_thanh_ben())
    # "Tổ sản xuất" là nhóm ĐỘNG dựng ở runtime (dòng `to_sx_<id>`), không phải khối thanh bên.
    nhan_nhom = [n for n, _ in _nhom_cua_ma_tran()]
    lech = sorted(n for n in nhan_nhom if n not in khoi)
    assert not lech, (
        "Nhãn phân hệ trong ma trận không khớp khối nào của thanh bên: " + ", ".join(lech)
        + f" — khối thanh bên đang có: {', '.join(sorted(khoi))}. Đặt lại cho trùng chữ."
    )
