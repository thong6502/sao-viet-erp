"""In ma trận quyền của các VAI được seed — nguồn cho `docs/RBAC_VAI_TRO.md`.

Vì sao có script này: tài liệu quyền viết tay thì sớm muộn lệch với code, mà lệch ở đây là người
đọc cấp nhầm quyền. Chạy lệnh này để lấy bản MỚI NHẤT rồi dán lại vào tài liệu.

    python -m scripts.xuat_ma_tran_quyen              # tất cả vai
    python -m scripts.xuat_ma_tran_quyen thu_mua      # lọc theo khoá module

⚠️ Đây là quyền lúc SEED (vai mẫu). Vai đã sửa tay trên DB thật thì khác — muốn xem cái đang chạy
thì đọc bảng `role_permissions`, không đọc file này.
"""
from __future__ import annotations

import pathlib
import re
import sys

from app.catalog_registry import MODULES_SEED
from app.seed import MODULES, ROLES, quyen_mac_dinh

#: `can_*` → nhãn tiếng Việt. Lấy đúng chữ đang hiện trên ma trận phân quyền ở giao diện, để
#: người đọc tài liệu dò được sang màn hình mà không phải đoán.
NHAN_CO: dict[str, str] = {
    "read": "Xem", "create": "Thêm", "update": "Sửa", "delete": "Xoá",
    "reassign": "Điều chuyển", "export": "Xuất file", "view_debt": "Xem công nợ",
    "view_discount": "Xem chiết khấu", "approve": "Duyệt",
    "manage_status": "Đổi trạng thái", "reset_password": "Đặt lại mật khẩu",
    "lock": "Khoá / Chốt kỳ", "revoke_sessions": "Thu hồi phiên",
    "assign_role": "Gán vai trò", "transfer": "Điều chuyển / chuyển phòng",
    "set_head": "Đặt trưởng phòng", "requote": "Tạo bản báo giá mới",
    "manage_price": "Quản giá", "cancel": "Huỷ",
    "manage_permissions": "Sửa ma trận phân quyền", "clone": "Nhân bản",
    "toggle_active": "Bật / ngừng dùng", "reparent": "Đổi cấp trên",
    "view_salary": "Xem lương & BHXH", "edit_salary": "Sửa lương & BHXH",
    "adjust": "Chấm bù / sửa công", "view_log": "Xem nhật ký",
    "approve_exception": "Duyệt trường hợp đặc thù",
    "set_credit_terms": "Đặt chính sách tài chính", "record_deposit": "Ghi phiếu thu cọc",
    "assign_work": "Gán việc", "record_output": "Ghi sản lượng",
    "handover": "Bàn giao / nhận", "request": "Tạo yêu cầu nhập/xuất",
    "view_stock": "Xem tất cả kho", "view_cost": "Xem giá vốn",
    "set_threshold": "Đặt ngưỡng tồn", "post": "Ghi sổ",
    "close_book": "Báo cáo kho + khoá kỳ", "view_timesheet": "Bảng công tháng",
    "approve_late_early": "Duyệt đi muộn / về sớm", "manage_locations": "Điểm chấm công",
    "manage_shifts": "Khai ca", "manage_calendar": "Lịch & Ngày lễ",
    "view_payroll_table": "Bảng lương tháng",
    "manage_salary_profiles": "Lương nhân viên", "manage_piece_rates": "Lương khoán",
    "manage_leave_types": "Danh mục loại nghỉ", "plan": "Lên đơn giao hàng",
    "view_drivers": "Nhân viên giao hàng",
}

NHAN_SCOPE = {"all": "Tất cả", "department": "Phòng ban", "own": "Của tôi"}

#: PHẠM VI TÀI LIỆU — bốn phân hệ đội mình làm. Module của đội khác (Kinh doanh · Sản xuất · Kho ·
#: Danh mục · Hệ thống) KHÔNG in ra: tài liệu quyền mà kể cả phần người khác làm thì người đọc
#: không biết chỗ nào hỏi được ai, và mình cũng không bảo đảm được số liệu bên đó.
PHAM_VI: dict[str, tuple[str, ...]] = {
    "Nhân sự & Lương": ("phong_ban", "nhan_su", "cham_cong", "nghi_phep", "tang_ca",
                        "luong", "noi_quy"),
    "Mua hàng": ("yeu_cau_mua_hang", "thu_mua", "nha_cung_cap"),
    "Kế toán": ("ke_toan", "phieu_chi", "phieu_thu", "cong_no_phai_tra",
                "cong_no_phai_thu", "tk_ngan_hang"),
    "Giao hàng": ("giao_hang",),
}

#: `{module: tên nhóm}` — để in gom theo nhóm thay vì một danh sách phẳng.
NHOM_CUA: dict[str, str] = {m: g for g, ms in PHAM_VI.items() for m in ms}

#: Bảng khai ô quyền của GIAO DIỆN. Đọc thẳng file đó thay vì chép danh sách sang đây — chép là
#: đẻ nguồn sự thật thứ hai, và hai bản sẽ lệch đúng lúc không ai để ý.
_MA_TRAN_FE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "PermissionMatrix.tsx"
)

#: Bốn ô CRUD hiện cho MỌI module.
CO_CHUNG = ("read", "create", "update", "delete")

_KET_KHOI = "\n];"


def co_co_nghia() -> dict[str, set[str]]:
    """`{module: {tên cờ module đó THẬT SỰ đọc}}`, rút từ `FINE_ACTIONS` của giao diện.

    Vì sao phải lọc: hàm `_full()` lúc seed bật CẢ 51 cờ cho một module, kể cả cờ module đó không
    đọc — Giám đốc có "Khai ca" trên module Khách hàng. In tất cả ra tài liệu thì người đọc tưởng
    những cờ đó có tác dụng, mà bật hay tắt đều không đổi gì.
    """
    if not _MA_TRAN_FE.exists():
        return {}
    s = _MA_TRAN_FE.read_text(encoding="utf-8")
    i = s.index("const FINE_ACTIONS")
    blok = s[i:s.index(_KET_KHOI, i)]
    ra: dict[str, set[str]] = {}
    mod: str | None = None
    for ln in blok.splitlines():
        m = re.match(r"^  (\w+):", ln)
        if m:
            mod = m.group(1)
            ra.setdefault(mod, set())
        if mod is None:
            continue
        ra[mod].update(re.findall(r'key:\s*"can_(\w+)"', ln))
        for ks in re.findall(r"keys:\s*\[([^\]]*)\]", ln):
            ra[mod].update(re.findall(r'"can_(\w+)"', ks))
    return ra


def main() -> int:
    loc = sys.argv[1] if len(sys.argv) > 1 else None
    nhan = dict(MODULES)
    nhan.update(dict(MODULES_SEED))
    nghia = co_co_nghia()
    if not nghia:
        print("⚠️  Không đọc được PermissionMatrix.tsx — in TẤT CẢ cờ, kể cả cờ vô nghĩa.\n")

    mac_dinh = quyen_mac_dinh()
    for phong, vai, quyen in ROLES:
        # CỘNG ba ô mặc định `seed_roles` cấp cho MỌI vai (self_service · noi_quy · phần
        # CỦA TÔI của Lương). Trước 26/08/2026 script chỉ đọc preset nên tài liệu bỏ sót
        # chúng ⇒ §2.3 của RBAC_VAI_TRO.md đi kể hai "lỗ hổng" đã vá từ lâu (vai "Nhân viên"
        # không vào được màn Lương · chỉ Giám đốc có Nội quy).
        quyen = {**mac_dinh, **quyen}
        # CHỈ module trong phạm vi tài liệu, xếp đúng thứ tự nhóm ở `PHAM_VI` — thứ tự khai
        # trong seed là ngẫu nhiên với người đọc.
        dong = {
            m: quyen[m] for g in PHAM_VI for m in PHAM_VI[g]
            if m in quyen and (loc is None or loc in m)
        }
        if not dong:
            continue
        print(f"\n### {vai}  ·  phòng {phong}")
        nhom_dang = None
        for mk, p in dong.items():
            g = NHOM_CUA.get(mk)
            if g != nhom_dang:
                nhom_dang = g
                print(f"\n*{g}*")
            dung = (set(CO_CHUNG) | nghia.get(mk, set())) if nghia else None
            co = [
                NHAN_CO.get(k[4:], k[4:]) for k, v in p.items()
                if k.startswith("can_") and v and (dung is None or k[4:] in dung)
            ]
            pv = NHAN_SCOPE.get(p.get("scope", ""), str(p.get("scope", "—")))
            print(f"- **{nhan.get(mk, mk)}** (`{mk}`) — phạm vi *{pv}*  \n"
                  f"  {' · '.join(co) if co else '(không cờ nào)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
