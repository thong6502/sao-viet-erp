"""KHOÁ hành vi của `app.catalog_registry` — bảng khai một-nguồn cho 11 màn Cấu hình danh mục.

Đợt B8 gom bốn bản chép tay ở backend (seed quyền · `SCOPELESS_MODULES` · `LOAI_MODULE` của nhật
ký · `model_cua` của luồng xoá) về một chỗ. Rút trừu tượng kiểu này hỏng IM LẶNG: mất một khoá
quyền thì màn vẫn chạy, chỉ có vai không phải Giám đốc là mở ra thấy 403 — không test nào đỏ.

Nên mọi bảng ở đây được chép NGUYÊN VĂN từ bản TRƯỚC refactor và ghi CỨNG. So registry với chính
nó thì test luôn xanh kể cả khi registry sai.
"""
from __future__ import annotations

from app.catalog_registry import DANH_MUC, MODULE_KEYS, MODULE_THEO_LOAI, dang_ky_json
from app.models.bu_hao import BuHao
from app.models.cong_doan import CongDoan
from app.models.don_vi_do import DonViDo
from app.models.khuon_be import KhuonBe
from app.models.loai_san_pham import LoaiSanPham
from app.models.may_thiet_bi import MayThietBi
from app.models.piece_work import PieceRate
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn
from app.routers.nhat_ky_danh_muc import LOAI_MODULE
from app.seed import MODULES
from app.services.danh_muc_tham_chieu import DEM_THEO_LOAI, model_cua
from app.services.role_service import SCOPELESS_MODULES

# ── Bản gốc, chép tay từ code TRƯỚC đợt B8 ──────────────────────────────────────

#: `role_service.SCOPELESS_MODULES` bản cũ — 11 khoá danh mục + Kỹ thuật máy, cộng 4 màn khối
#: Sản xuất tách khoá riêng ngày 17/08/2026 (đã soi: không router nào của chúng đọc scope).
#: `san_xuat` KHÔNG có mặt — `lsx.py` đọc scope thật để thợ chỉ thấy lệnh của mình.
#: `dm_cong_viec_khoan` (17/08/2026): màn danh mục nên scopeless như 10 màn kia — bảng đơn giá là
#: dữ liệu GỐC của cả xưởng, không có khái niệm "đơn giá của tôi".
#: `bai_ghep` (màn cũ) rời danh sách 18/08/2026: mg `0216` chép quyền sang `bai_ghep_2` rồi xoá khoá.
#: `xep_lich` (màn cũ) rời danh sách 19/08/2026: mg `0219` chép quyền sang `xep_lich_2` rồi xoá khoá.
#: `dm_ly_do_san_xuat` (19/08/2026): danh mục Lý do & lỗi SX (§15) — màn thứ 12, scopeless như 11
#: màn kia (danh sách lý do là dữ liệu GỐC của xưởng, không có "lý do của tôi"). mg `0221` chép quyền.
SCOPELESS_CU = frozenset({
    "dm_loai_san_pham", "dm_thiet_bi", "dm_cong_doan", "dm_cong_viec_khoan", "dm_bu_hao",
    "dm_don_vi", "dm_chung_loai_giay", "dm_giay", "dm_vat_tu", "khuon_be", "dm_kho_hang",
    "dm_ly_do_san_xuat",
    "ky_thuat_may",
    "ke_hoach_vat_tu", "bai_ghep_2", "xep_lich_2", "phieu_bao_tri",
})

#: `nhat_ky_danh_muc.LOAI_MODULE` bản cũ — 17 khoá: 11 tên chính, 3 tên đời cũ
#: (`product_type`/`machine`/`operation`), bảng phụ `don_vi_quy_doi`, 2 khoá Kỹ thuật máy.
LOAI_MODULE_CU = {
    "loai_san_pham": "dm_loai_san_pham",
    "product_type": "dm_loai_san_pham",
    "may_thiet_bi": "dm_thiet_bi",
    "machine": "dm_thiet_bi",
    "cong_doan": "dm_cong_doan",
    "operation": "dm_cong_doan",
    # Đơn giá khoán vào Cấu hình danh mục 17/08/2026 — trước đó bảng `piece_rates` KHÔNG ghi nhật ký
    # dòng nào (CRUD của nó nằm ở router Lương, ngoài nền danh mục).
    "cong_viec_khoan": "dm_cong_viec_khoan",
    "bu_hao": "dm_bu_hao",
    "don_vi_do": "dm_don_vi",
    "don_vi_quy_doi": "dm_don_vi",
    "chung_loai_giay": "dm_chung_loai_giay",
    "giay": "dm_giay",
    "vat_tu": "dm_vat_tu",
    "khuon_be": "khuon_be",
    "kho_hang": "dm_kho_hang",
    # Lý do & lỗi SX vào Cấu hình danh mục 19/08/2026 (§15) — màn thứ 12, module riêng.
    "san_xuat_ly_do": "dm_ly_do_san_xuat",
    "ky_thuat_sua_chua": "ky_thuat_may",
    "ky_thuat_bao_tri": "ky_thuat_may",
}

#: `danh_muc_tham_chieu.model_cua` bản cũ — đúng 8 loại có model.
MODEL_CU = {
    "cong_doan": CongDoan, "don_vi_do": DonViDo, "bu_hao": BuHao, "khuon_be": KhuonBe,
    "loai_san_pham": LoaiSanPham, "chung_loai_giay": ChungLoaiGiay,
    "giay": GiayNguyen, "vat_tu": VatTuInAn,
    # Máy vào bản đồ 15/08/2026 cùng cột `active` (mg `0202`): trước đó nó `model=None`
    # nên `kiem-xoa` trả 404 và hộp thoại xoá của màn Máy rơi vào ngõ cụt.
    "may_thiet_bi": MayThietBi,
    # Công việc khoán vào bản đồ 17/08/2026: `kiem-xoa` đếm định mức đầu việc + bước lệnh/bài ghép
    # đang ghim đơn giá này.
    "cong_viec_khoan": PieceRate,
}


# ── Khoá bốn nơi đọc registry ───────────────────────────────────────────────────
def test_scopeless_modules_y_nguyen_ban_cu():
    """Sót một khoá ⇒ danh mục đó lại có dropdown Phạm vi và scope `own` bó âm thầm quyền vừa cấp."""
    assert SCOPELESS_MODULES == SCOPELESS_CU


def test_loai_module_y_nguyen_ban_cu():
    """Sót một khoá ⇒ nhật ký của màn đó trả 404, kể cả khi bản ghi có đủ lịch sử."""
    assert LOAI_MODULE == LOAI_MODULE_CU


def test_model_cua_y_nguyen_ban_cu():
    """Đúng 9 loại có model. Tên đời cũ (`machine`…) và màn chưa có bộ đếm phải trả None —
    trả model theo tên lạ là mở thêm một đường vào luồng xoá bằng khoá không ai khai."""
    for loai, lop in MODEL_CU.items():
        assert model_cua(loai) is lop, f"{loai}: model_cua trả sai lớp"
    for loai in ("kho_hang", "machine", "product_type", "operation",
                 "don_vi_quy_doi", "khong_co_loai_nay"):
        assert model_cua(loai) is None, f"{loai}: phải là None, không được suy ra model"


def test_seed_modules_giu_du_o_quyen_va_khong_trung():
    """Ma trận quyền lấy dòng từ bảng `modules` do seed đẻ ra. Thiếu một dòng = không cấp được
    quyền cho màn đó; trùng một dòng = seed đè nhãn qua lại giữa hai lần chạy."""
    keys = [k for k, _ in MODULES]
    assert len(keys) == len(set(keys)), "MODULES có khoá trùng"
    nhan_theo_key = dict(MODULES)
    for dm in DANH_MUC:
        assert dm.module in nhan_theo_key, f"seed thiếu ô quyền cho màn {dm.nhan}"
        assert nhan_theo_key[dm.module] == dm.nhan


# ── Khoá chính bảng khai ────────────────────────────────────────────────────────
def test_khuon_be_giu_nguyen_chuoi_quyen():
    """`khuon_be` KHÔNG có tiền tố `dm_`. Chuỗi này đang nằm trong `role_permissions` của DB thật:
    đổi cho "nhất quán" là làm mồ côi mọi quyền đã cấp, phải có migration UPDATE đi kèm."""
    assert MODULE_THEO_LOAI["khuon_be"] == "khuon_be"
    assert "dm_khuon_be" not in MODULE_KEYS


def test_khong_trung_loai_khong_trung_module():
    loai = [d.loai for d in DANH_MUC] + [a for d in DANH_MUC for a in d.alias_loai]
    assert len(loai) == len(set(loai)), "trùng `loai` giữa tên chính và tên đời cũ"
    assert len(MODULE_KEYS) == len(set(MODULE_KEYS)) == 12


def test_dem_theo_loai_phu_dung_cac_man_co_model():
    """Hai bảng phải khớp: khai model mà quên hàm đếm ⇒ luồng xoá trả "chưa rà được nơi dùng"
    cho một màn có thật, người dùng không xoá hẳn được gì."""
    assert set(DEM_THEO_LOAI) == {d.loai for d in DANH_MUC if d.model}


# ── Endpoint /api/danh-muc/dang-ky ──────────────────────────────────────────────
def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_dang_ky_tra_du_cac_man(client):
    r = client.get("/api/danh-muc/dang-ky", headers=_admin(client))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 12
    assert [i["module"] for i in items] == list(MODULE_KEYS), "phải giữ đúng thứ tự menu"
    for i in items:
        assert {"loai", "module", "nhan", "path"} == set(i), f"khoá lệch: {sorted(i)}"
        assert i["nhan"] and i["path"]


def test_dang_ky_khong_bi_nuot_vao_route_co_tham_so(client):
    """Route TĨNH `/dang-ky` phải khai TRƯỚC `/{loai}/...`. Nuốt nhầm thì chuỗi "dang-ky" đi vào
    `{loai}` và endpoint trả 404/422 thay vì bảng khai."""
    r = client.get("/api/danh-muc/dang-ky", headers=_admin(client))
    assert r.status_code == 200 and isinstance(r.json().get("items"), list)


def test_dang_ky_bat_dang_nhap(client):
    """Bảng khai tĩnh nên KHÔNG đẻ ô quyền mới, nhưng vẫn phải đăng nhập — nó lộ đúng cấu trúc
    menu của hệ thống."""
    assert client.get("/api/danh-muc/dang-ky").status_code in (401, 403)


def test_moi_man_deu_co_o_quyen_that_trong_db(client):
    """Khoá quyền trong registry phải TỒN TẠI trong bảng `modules` sau khi seed chạy — khai một
    chuỗi không ai seed thì ma trận quyền lặng lẽ bỏ qua dòng đó, không báo gì."""
    r = client.get("/api/rbac/modules", headers=_admin(client))
    assert r.status_code == 200, r.text
    thuc = {m["key"]: m["label"] for m in r.json()}
    thieu = [d.module for d in DANH_MUC if d.module not in thuc]
    assert not thieu, f"seed chưa đẻ ô quyền cho: {thieu}"
    lech = [(d.module, thuc[d.module], d.nhan) for d in DANH_MUC if thuc[d.module] != d.nhan]
    assert not lech, f"nhãn ô quyền lệch registry: {lech}"
