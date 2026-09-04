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
        ("cong_no_phai_tra", "create"), ("cong_no_phai_thu", "update"),
        ("nghi_phep", "delete"),
        ("di_muon", "read"), ("di_muon", "create"),
        # `tang_ca:create` SỐNG LẠI 15/08/2026 — bỏ ô Tự phục vụ nên "gửi phiếu cho chính mình"
        # đi bằng ô Thao tác của chính màn Tăng ca. Đừng khai lại là chết.
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
    assert "create" in theo_khoa.get("cong_no_phai_tra", set())
    assert "create" in theo_khoa.get("ke_toan", set())
    # Ô đang dùng KHÔNG được lọt vào danh sách chết.
    assert "export" not in theo_khoa.get("phieu_chi", set())
    # `cong_no_phai_tra:update` CHẾT LẠI 04/09/2026: nút KHÓA SỔ dọn sang gác bằng
    # `bao_cao_cong_no:update` riêng (module "Báo cáo" tách khỏi hai khoá công nợ). Còn nằm trong
    # danh sách chết là ĐÚNG, không phải quay lại lỗi cũ.
    assert "update" in theo_khoa.get("cong_no_phai_tra", set())
    # `bao_cao_cong_no`: Xem + Thao tác (khoá/mở kỳ) đều sống, Thêm/Xoá chết.
    assert "read" not in theo_khoa.get("bao_cao_cong_no", set())
    assert "update" not in theo_khoa.get("bao_cao_cong_no", set())
    assert "create" in theo_khoa.get("bao_cao_cong_no", set())
    assert "delete" in theo_khoa.get("bao_cao_cong_no", set())
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


def test_moi_cot_co_quyen_deu_di_xuong_duoc_trinh_duyet():
    """⭐ TẦNG THỨ SÁU — chỗ vừa lọt 15/08/2026.

    Chuỗi nối một ô quyền có SÁU tầng: model → repo `set_permission` → bản đồ động từ ở
    `rbac_service` → schema API → ma trận ở giao diện → **`capabilities()`**. Tầng cuối liệt kê
    TỪNG CỜ MỘT bằng tay; thiếu một dòng là ô lưu được, ma trận hiện đúng, mà trình duyệt không
    biết ô đó tồn tại ⇒ **tab không bao giờ hiện, không một lời báo lỗi**.

    Năm tầng kia đều có test rồi; tầng này thì không, và nó vừa nuốt mất 5 ô mới."""
    from app.models.role import RolePermission
    from app.services.rbac_service import AuthorizationService

    cot = {c.name for c in RolePermission.__table__.columns if c.name.startswith("can_")}
    nguon = (BE / "services" / "rbac_service.py").read_text(encoding="utf-8")
    than = nguon.split("def capabilities(", 1)[1].split("\n    def ", 1)[0]
    gui_xuong = set(re.findall(r'"(can_\w+)": p\.', than))

    thieu = sorted(cot - gui_xuong)
    assert not thieu, (
        "Mấy cột quyền này KHÔNG được gửi xuống trình duyệt trong `capabilities()` — quản trị tick "
        "được, ma trận hiện đúng, nhưng màn hình không bao giờ thấy ô đó nên tab/nút không hiện:\n"
        "  " + ", ".join(thieu)
    )
    assert AuthorizationService is not None


def test_schema_tra_ve_khong_cat_mat_cot_quyen_nao():
    """⭐ TẦNG 6b — `response_model` của FastAPI CẮT BỎ field không khai trong schema.

    Ngày 15/08/2026 chuyện này lọt HAI LẦN liên tiếp: cờ đã có trong `capabilities()` nhưng
    `ModuleCapability` không khai ⇒ FastAPI lọc sạch, trình duyệt không nhận. Triệu chứng y hệt
    tầng 6: mọi thứ đúng, chỉ tab không hiện, không một lời báo lỗi.

    Guard `test_moi_cot_co_quyen_deu_di_xuong_duoc_trinh_duyet` KHÔNG bắt được ca này — nó chỉ soi
    `capabilities()`, không soi schema."""
    from app.models.role import RolePermission
    from app.schemas.auth import ModuleCapability

    cot = {c.name for c in RolePermission.__table__.columns if c.name.startswith("can_")}
    khai = set(ModuleCapability.model_fields)
    thieu = sorted(cot - khai)
    assert not thieu, (
        "Mấy cột quyền này KHÔNG khai trong `ModuleCapability` ⇒ FastAPI cắt khỏi JSON trả về, "
        "trình duyệt không bao giờ nhận được:\n  " + ", ".join(thieu)
    )


def test_o_chi_tiet_khong_dung_chung_cot_voi_nut_thao_tac():
    """⭐ Ô chi tiết KHÔNG được mượn cột mà nút "Thao tác" bật.

    Nút "Thao tác" trên ma trận bật CÙNG LÚC ba cột `can_create` / `can_update` / `can_delete`.
    Ô chi tiết nào lấy một trong ba cột đó làm khoá thì bật Thao tác là nó TỰ SÁNG THEO — người
    cấp quyền mở thêm một quyền mà không hề bấm vào đó, và không có gì báo cho họ biết.

    Đã cắn thật 15/08/2026: ô "Quản danh mục loại nghỉ" dùng `can_update`, nên bật Thao tác (để
    thợ gửi / huỷ đơn của chính mình) là mở luôn quyền sửa chính sách nghỉ của cả nhà máy.
    """
    s = (FE / "components" / "PermissionMatrix.tsx").read_text(encoding="utf-8")

    m = re.search(r"const WRITE_ACTIONS: ActionKey\[\] = \[(.*?)\]", s, re.S)
    assert m, "không đọc được `WRITE_ACTIONS` — đổi tên hằng thì sửa guard này luôn"
    ghi = {x.strip().strip('"') for x in m.group(1).split(",") if x.strip()}
    assert ghi, "WRITE_ACTIONS rỗng — guard sẽ xanh giả"

    than = s[s.index("const FINE_ACTIONS"):]
    than = than[: than.index("\n};")]

    dung_chung, mod = [], None
    for dong in than.split("\n"):
        khop = re.match(r"\s{2}([a-z_]+): \[", dong)
        if khop:
            mod = khop.group(1)
        for k in re.findall(r'key: "(can_\w+)"', dong):
            if k in ghi:
                dung_chung.append(f"{mod}.{k}")

    assert not dung_chung, (
        "Ô chi tiết mượn cột của nút Thao tác — bật Thao tác là ô đó TỰ SÁNG THEO, tức mở thêm "
        "quyền mà người cấp không hề bấm:\n  " + ", ".join(dung_chung)
    )


def test_khong_co_hai_o_chi_tiet_dung_chung_mot_cot():
    """⭐ Trong CÙNG một module, hai ô chi tiết không được dùng chung một cột.

    Dùng chung thì tick ô này ô kia sáng theo — người cấp quyền tưởng đó là hai việc khác nhau,
    thật ra chỉ là một dòng khai thừa. Đã cắn thật 15/08/2026: màn Lương có cả "Chốt bảng lương /
    Mở lại kỳ" lẫn "Chốt kỳ lương", hai nhãn khác nhau nhưng cùng cột `can_lock`.

    Ô dùng `keys` (một công tắc set NHIỀU cột) vẫn hợp lệ — chỗ đó `key` chỉ là cột đại diện.
    """
    s = (FE / "components" / "PermissionMatrix.tsx").read_text(encoding="utf-8")
    than = s[s.index("const FINE_ACTIONS"):]
    than = than[: than.index("\n};")]

    trung, mod = [], None
    da_thay: dict[str, set[str]] = {}
    for dong in than.split("\n"):
        khop = re.match(r"\s{2}([a-z_]+): \[", dong)
        if khop:
            mod = khop.group(1)
            da_thay[mod] = set()
        for k in re.findall(r'key: "(can_\w+)"', dong):
            if mod is None:
                continue
            if k in da_thay[mod]:
                trung.append(f"{mod}.{k}")
            da_thay[mod].add(k)

    assert not trung, (
        "Hai ô chi tiết dùng chung một cột — tick ô này ô kia sáng theo, mà nhãn lại khác nhau "
        "nên người cấp quyền tưởng là hai việc:\n  " + ", ".join(trung)
    )
