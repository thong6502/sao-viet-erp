"""Đợt E — ma trận tắt + khoá "công tắc chết" (ô bật cũng không mở thêm gì).

⚠️ BÀI HỌC ĐẮT, ĐỌC TRƯỚC KHI SỬA FILE NÀY.

Bản đầu tiên (11/08/2026) làm kiểu **suy ngược**: registry tự gom mọi cổng `require_permission(...)`
lúc nạp router, rồi ma trận khoá mọi ô KHÔNG có trong registry. Nghe hợp lý, và nó **khoá nhầm hàng
loạt ô đang dùng được**, chủ chốt phát hiện ngay khi mở màn:

    In / xuất phiếu chi · In / xuất phiếu thu · Đặt trưởng phòng · Đổi cấp trên (cây tổ chức) ·
    Xem lương & BHXH · Sửa lương & BHXH · Thao tác vòng đời · Điều chuyển & nâng bậc

Lý do: registry chỉ thấy cổng ở **router**. Rất nhiều ô được thi hành ở **giao diện** (ẩn/hiện nút)
hoặc ở **tầng service**. *Máy chủ không gác* ≠ *ô không có tác dụng*.

Hướng đúng là ngược lại — **danh sách đen đã xác minh**: mặc định coi mọi ô còn sống, chỉ tắt cái
nào đã soi ĐỦ BA NƠI và chắc chắn không nơi nào hỏi. Sai theo hướng này thì tệ nhất là để thừa một
ô vô hại; sai theo hướng kia là **chặn việc thật của người đang làm**.

File này canh cả hai chiều của `deps.O_CHET_DA_XAC_MINH`.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.deps import O_CHET_DA_XAC_MINH, O_QUYEN_GAC_O_SERVICE, o_quyen_co_tac_dung

GOC = Path(__file__).resolve().parents[2]
BE = GOC / "backend" / "app"
FE = GOC / "frontend" / "src"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> str:
    return client.post("/api/auth/login",
                       json={"username": "admin", "password": "admin123"}).json()["access_token"]


def _giao_dien_hoi() -> set[tuple[str, str]]:
    """Mọi cặp (màn, việc) mà GIAO DIỆN hỏi — `can("x","y")` và `caps.get("x")?.can_y`."""
    hoi: set[tuple[str, str]] = set()
    for p in FE.rglob("*.ts*"):
        s = p.read_text(encoding="utf-8")
        hoi.update(re.findall(r'\bcan\(\s*"([a-z_]+)"\s*,\s*"(\w+)"\s*\)', s))
        hoi.update(re.findall(r'caps\.get\("([a-z_]+)"\)\?\.can_(\w+)', s))
    return hoi


def _service_hoi() -> set[tuple[str, str]]:
    """Mọi cặp mà TẦNG SERVICE hỏi (`authz.can(...)`) — không đi qua cổng của router."""
    hoi: set[tuple[str, str]] = set()
    for p in (BE / "services").rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        hoi.update(re.findall(r'\.can\(\s*[\w.]+\s*,\s*"([a-z_]+)"\s*,\s*"(\w+)"', s))
    return hoi


def _sidebar_hoi() -> set[tuple[str, str]]:
    """NƠI THỨ TƯ, thêm 12/08/2026 — và suýt gây lại đúng tai nạn của đợt E.

    Sidebar gác từng mục menu bằng THUỘC TÍNH `module: "x"` / `modules: [...]`, KHÔNG gọi
    `can("x","read")`. Guard cũ chỉ soi ba nơi nên một lượt rà tay đã kết luận nhầm
    `dashboard:read` và `dm_giay_vat_tu:read` là ô chết — tắt hai ô đó là **mất luôn mục
    Dashboard và Hồ sơ của tôi** khỏi menu của mọi vai. Khoá nào có mặt ở sidebar ⇒ `read`
    của nó ĐANG SỐNG.
    """
    s = (FE / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    hoi = {(k, "read") for k in re.findall(r'\bmodules?:\s*"([a-z_0-9]+)"', s)}
    for m in re.finditer(r'\bmodules:\s*\[(.*?)\]', s, re.S):
        hoi |= {(k, "read") for k in re.findall(r'"([a-z_0-9]+)"', m.group(1))}
    return hoi


def test_o_khai_la_chet_thi_phai_chet_o_CA_BON_NOI():
    """Chiều nguy hiểm: khai nhầm một ô đang dùng thành "chết" ⇒ khoá mất việc của người ta.

    Đúng cái đã xảy ra 11/08/2026. Soi đủ bốn nơi: cổng router · `authz.can` ở service ·
    `can(...)` ở giao diện · thuộc tính `module` của sidebar.
    """
    gac = o_quyen_co_tac_dung()
    fe = _giao_dien_hoi()
    svc = _service_hoi()
    sb = _sidebar_hoi()

    sai = []
    for k, a in sorted(O_CHET_DA_XAC_MINH):
        noi = []
        if (k, a) in gac:
            noi.append("cổng máy chủ")
        if (k, a) in svc:
            noi.append("service")
        if (k, a) in fe:
            noi.append("giao diện")
        if (k, a) in sb:
            noi.append("menu sidebar")
        if noi:
            sai.append(f"  {k}:{a}  ← vẫn được hỏi ở: {', '.join(noi)}")
    assert not sai, (
        "Ô khai là CHẾT nhưng vẫn có chỗ hỏi tới — khoá nó là chặn việc thật.\n"
        "Gỡ khỏi `deps.O_CHET_DA_XAC_MINH`.\n" + "\n".join(sai)
    )


def test_o_dang_dung_duoc_khong_bi_khai_nham_la_chet(client):
    """Danh sách cụ thể chủ chốt đã chỉ mặt sau lần khoá nhầm — ghim lại để không tái phạm."""
    tung_bi_khoa_nham = [
        ("phieu_chi", "export"), ("phieu_thu", "export"),
        ("phong_ban", "set_head"), ("phong_ban", "reparent"),
        ("nhan_su", "view_salary"), ("nhan_su", "edit_salary"),
        ("nhan_su", "manage_status"), ("nhan_su", "transfer"),
        ("nhan_su", "export"), ("phieu_thu", "manage_status"),
        ("luong", "view_salary"), ("luong", "export"), ("luong", "manage_status"),
    ]
    khoa_nham = [f"{k}:{a}" for k, a in tung_bi_khoa_nham if (k, a) in O_CHET_DA_XAC_MINH]
    assert not khoa_nham, (
        "Mấy ô này ĐANG DÙNG ĐƯỢC (chủ chốt đã báo một lần rồi) — đừng khai là chết: "
        + ", ".join(khoa_nham)
    )


def test_o_chet_da_biet_van_nam_trong_danh_sach(client):
    """Chiều còn lại: quên khai thì ô chết vẫn bày ra, người cấp quyền tưởng đã cấp."""
    phai_co = [
        ("ke_toan", "create"), ("ke_toan", "update"), ("ke_toan", "delete"),
        ("cong_no_phai_tra", "update"), ("cong_no_phai_thu", "update"),
        ("nghi_phep", "delete"),
        ("di_muon", "read"), ("di_muon", "create"),
        ("tang_ca", "create"),
        # Màn Yêu cầu chỉnh công (chủ chốt hỏi 12/08/2026: "Thao tác tác dụng gì vậy" — không gì
        # cả). Ba cửa của màn chỉ dùng `read` + `approve`; gửi yêu cầu là việc của ô Tự phục vụ.
        ("yeu_cau_chinh_cong", "create"), ("yeu_cau_chinh_cong", "update"),
        ("yeu_cau_chinh_cong", "delete"),
    ]
    thieu = [f"{k}:{a}" for k, a in phai_co if (k, a) not in O_CHET_DA_XAC_MINH]
    assert not thieu, "ô chết chưa khai vào `O_CHET_DA_XAC_MINH`: " + ", ".join(thieu)


def test_api_modules_tra_danh_sach_o_chet(client):
    r = client.get("/api/rbac/modules", headers=_h(_admin(client)))
    assert r.status_code == 200, r.text
    ds = r.json()
    assert ds, "không có module nào"
    for m in ds:
        assert "viec_chet" in m, f'{m["key"]}: thiếu trường viec_chet'

    theo_khoa = {m["key"]: set(m["viec_chet"]) for m in ds}
    assert "update" in theo_khoa.get("cong_no_phai_tra", set())
    assert "create" in theo_khoa.get("ke_toan", set())
    # Ô đang dùng KHÔNG được lọt vào danh sách chết.
    assert "export" not in theo_khoa.get("phieu_chi", set())
    assert "read" not in theo_khoa.get("nhan_su", set())


def test_khai_tay_o_gac_tang_service_van_dung_voi_ma_nguon():
    """`O_QUYEN_GAC_O_SERVICE` khai tay thì phải có người canh — gỡ một `authz.can(...)` ở service
    mà quên xoá dòng khai là registry nói dối."""
    svc = _service_hoi()
    thua = [f"{k}:{a}" for k, a in O_QUYEN_GAC_O_SERVICE if (k, a) not in svc]
    assert not thua, (
        "khai tay nhưng KHÔNG còn chỗ nào ở service hỏi quyền đó — gỡ khỏi "
        "`O_QUYEN_GAC_O_SERVICE`: " + ", ".join(thua)
    )
