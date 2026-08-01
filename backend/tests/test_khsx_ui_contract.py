from pathlib import Path


DRAWER = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "pages"
    / "LsxBuocDrawer.tsx"
)


def test_drawer_chi_co_mot_o_nhap_so_luot_chay() -> None:
    source = DRAWER.read_text(encoding="utf-8")

    assert source.count('set("so_luot_chay", e.target.value)') == 1
    assert "Số lượt chạy qua máy" in source


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
