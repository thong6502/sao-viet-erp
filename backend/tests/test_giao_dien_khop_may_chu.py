"""Guard chặng 5: giao diện hỏi ô quyền nào thì máy chủ phải thật sự gác ô đó.

VÌ SAO CÓ FILE NÀY — vỡ THẬT hai chỗ cùng một lượt (11/08/2026):

  • Nút *Duyệt* / *Từ chối* ở màn Đơn mua hàng (Kế toán): máy chủ đã dời sang `ke_toan:approve`,
    giao diện vẫn hỏi `thu_mua:approve`.
  • Ba nút *Sửa số nhận* · *Mở lại đơn* · *Đóng đơn* ở màn Mua hàng: máy chủ đổi sang
    `thu_mua:manage_status`, giao diện vẫn hỏi `thu_mua:approve`.

Hậu quả giống nhau và rất khó đoán từ phía người dùng: **cấp quyền rồi mà nút không hiện**. Không
lỗi, không cảnh báo — chỉ là một nút không bao giờ xuất hiện. Bộ test API không bắt được vì máy chủ
hoàn toàn đúng; chỉ có người ngồi test tay mới thấy.

Guard này quét mọi lời gọi `can("<màn>", "<việc>")` trong mã giao diện rồi đối chiếu với tập cặp
(màn, việc) mà máy chủ THẬT SỰ hỏi. Lệch một đầu là đỏ ngay, không đợi test tay.
"""

from __future__ import annotations

import re
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
BE = GOC / "backend" / "app"
FE = GOC / "frontend" / "src"

#: Cặp (màn, việc) giao diện được phép hỏi dù máy chủ KHÔNG gác — phải nêu lý do từng cái.
#: Danh sách này chỉ nên co lại, đừng phình ra: mỗi dòng ở đây là một ô "bật thì hiện nút, nhưng
#: gọi thẳng API vẫn làm được" — tức hàng rào chỉ nằm ở giao diện.
CHO_PHEP: dict[tuple[str, str], str] = {
    ("phieu_chi", "export"):
        "In / xuất phiếu chi chạy hoàn toàn ở trình duyệt (window.print) — không có endpoint để gác. "
        "Người bấm vốn đã có quyền XEM chứng từ nên không rò thêm gì.",
    ("phieu_thu", "export"):
        "Như trên, cho màn Phiếu thu.",
    ("kho", "post"):
        "TÀN DƯ, nên dọn — nằm NGOÀI 3 phân hệ của đợt phân quyền nên chưa đụng. `can_post` từng là "
        "tách vai 'thủ kho lập / kế toán ghi sổ'; tách vai đó đã BỎ (xem chú thích ở seed.py), máy "
        "chủ nay cho ai lập phiếu thì ghi sổ luôn. Nhưng KhoYeuCauPage vẫn ẩn nút 'Tạo & Ghi sổ' "
        "sau cờ này ⇒ người có quyền lập mà chưa tick `can_post` phải bấm hai bước, dù máy chủ cho "
        "làm một bước. Hàng rào giả, chỉ gây khó.",
    ("dashboard", "read"):
        "Gác việc HIỆN MENU/thẻ trên trang chủ, không phải một endpoint. Dữ liệu từng thẻ vẫn do "
        "endpoint của phân hệ tương ứng gác.",
}


def _khoa_theo_hang(nguon: str) -> dict[str, str]:
    """Bản đồ tên hằng → khoá module, để giải `require_permission(MODULE_X, ...)`."""
    return dict(re.findall(r'^(MODULE\w*) = "([a-z_]+)"', nguon, re.M))


def _may_chu_gac() -> set[tuple[str, str]]:
    """Mọi cặp (module, action) máy chủ thật sự hỏi — gom từ cả 3 kiểu khai."""
    dung: set[tuple[str, str]] = set()
    for p in BE.rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        hang = _khoa_theo_hang(s)
        # Hằng danh sách khoá: TEN = ("a", "b", ...) — dùng cho kiểu `for m in TEN`.
        ds: dict[str, list[str]] = {}
        for m in re.finditer(r'^([A-Z_]+) = \(\s*([\s\S]*?)\)\n', s, re.M):
            khoa_ds = re.findall(r'"([a-z_]+)"', m.group(2))
            if khoa_ds:
                ds[m.group(1)] = khoa_ds

        def giai(x: str) -> str | None:
            x = x.strip()
            return x.strip('"') if x.startswith('"') else hang.get(x)

        for m, a in re.findall(r'require_permission\(\s*([\w".]+)\s*,\s*"(\w+)"', s):
            if (k := giai(m)):
                dung.add((k, a))
        for blob in re.findall(r'require_any_permission\(([\s\S]{0,400}?)\)\s*\)', s):
            for m, a in re.findall(r'\(\s*([\w".]+)\s*,\s*"(\w+)"\s*\)', blob):
                if (k := giai(m)):
                    dung.add((k, a))
            for a, ten_ds in re.findall(r'\(\s*\w+\s*,\s*"(\w+)"\s*\)\s*for\s+\w+\s+in\s+(\w+)', blob):
                for k in ds.get(ten_ds, []):
                    dung.add((k, a))
        for k, a in re.findall(r'\.can\(\s*[\w.]+\s*,\s*"([a-z_]+)"\s*,\s*"(\w+)"', s):
            dung.add((k, a))
        for m, a in re.findall(r'\.can\(\s*[\w.]+\s*,\s*(MODULE\w*)\s*,\s*"(\w+)"', s):
            if (k := giai(m)):
                dung.add((k, a))

    # Hằng danh sách khai ở service nhưng dùng bởi router khác (vd 6 nhóm đọc được YCMH).
    ps = (BE / "services" / "purchase_service.py").read_text(encoding="utf-8")
    for m in re.finditer(r'^([A-Z_]+) = \(([\s\S]*?)\)\n', ps, re.M):
        if "READER" in m.group(1):
            for k in re.findall(r'"([a-z_]+)"', m.group(2)):
                dung.add((k, "read"))
    return dung


def _giao_dien_hoi() -> dict[tuple[str, str], list[str]]:
    """Mọi cặp (module, action) giao diện hỏi, kèm tên file để báo lỗi cho dễ tìm."""
    hoi: dict[tuple[str, str], list[str]] = {}
    for p in FE.rglob("*.ts*"):
        s = p.read_text(encoding="utf-8")
        for k, a in re.findall(r'\bcan\(\s*"([a-z_]+)"\s*,\s*"(\w+)"\s*\)', s):
            hoi.setdefault((k, a), []).append(p.name)
    return hoi


def test_giao_dien_va_may_chu_hoi_cung_mot_o_quyen():
    gac = _may_chu_gac()
    hoi = _giao_dien_hoi()

    lech = [
        f'  {k}:{a}  ← {", ".join(sorted(set(files)))}'
        for (k, a), files in sorted(hoi.items())
        if (k, a) not in gac and (k, a) not in CHO_PHEP
    ]
    assert not lech, (
        "Giao diện hỏi ô quyền mà MÁY CHỦ KHÔNG gác ô đó.\n"
        "Triệu chứng ngoài đời: quản trị cấp quyền rồi mà NÚT KHÔNG HIỆN (hoặc ngược lại, nút hiện "
        "mà bấm vào ăn 403). Thường do dời khoá ở máy chủ mà quên sửa giao diện.\n"
        "Sửa cho khớp, hoặc nếu đúng là hàng rào chỉ ở giao diện thì khai vào `CHO_PHEP` kèm lý do.\n"
        + "\n".join(lech)
    )


#: Khoá module máy chủ có gác nhưng GIAO DIỆN không cần hỏi — kèm lý do.
KHONG_CAN_O_GIAO_DIEN: dict[str, str] = {
    "activity_log": "Màn Nhật ký hiện/ẩn qua thanh bên (`module:` ở Sidebar), không có nút nào hỏi thêm.",
    "vai_tro": "Màn Vai trò & Quyền hiện qua thanh bên; sửa ma trận gác bằng ô chi tiết riêng.",
}


def test_moi_khoa_module_may_chu_gac_deu_co_cho_dung_o_giao_dien():
    """Máy chủ gác một khoá mà GIAO DIỆN không hỏi tới bao giờ ⇒ ô đó cấp cũng như không: người
    dùng vẫn không thấy màn/nút nào đổi.

    ⚠️ ĐÃ VỠ THẬT 11/08/2026 (lần thứ ba của cùng một khuôn sai): tách khoá `yeu_cau_chinh_cong` ở
    máy chủ nhưng tab "Yêu cầu chỉnh công" vẫn hỏi `cham_cong:read` — cấp ô Chấm công là tab hiện
    ra, tách coi như không.

    Guard kia (`test_giao_dien_va_may_chu_hoi_cung_mot_o_quyen`) KHÔNG bắt được ca này: nó chỉ hỏi
    "cặp giao diện hỏi có được gác không", mà `cham_cong:read` thì được gác thật — chỉ là SAI CẶP
    cho nút đó. Guard này soi ở mức KHOÁ MÀN: khoá mới mà giao diện chưa hỏi lần nào là đỏ.
    """
    khoa_may_chu = {k for k, _ in _may_chu_gac()}
    # BỎ QUA `PermissionMatrix.tsx`: nó LIỆT KÊ mọi khoá module theo bản chất (nhãn, nhóm, ô chi
    # tiết) nên khoá nào cũng xuất hiện ở đó — tính vào là guard mất răng. Đã đo: không loại file
    # này thì đột biến "trả tab về hỏi khoá cũ" vẫn xanh.
    fe_nguon = "\n".join(
        p.read_text(encoding="utf-8")
        for p in FE.rglob("*.ts*")
        if p.name != "PermissionMatrix.tsx"
    )

    mo_coi = sorted(
        k for k in khoa_may_chu
        if k not in KHONG_CAN_O_GIAO_DIEN and f'"{k}"' not in fe_nguon
    )
    assert not mo_coi, (
        "Máy chủ gác mấy khoá này nhưng giao diện KHÔNG hỏi tới bao giờ — cấp quyền xong người "
        "dùng vẫn không thấy gì đổi. Thường do tách khoá ở máy chủ mà quên đổi màn tương ứng.\n"
        "  " + ", ".join(mo_coi)
    )


#: Nút NGUY HIỂM → (ô quyền phải hỏi, file giao diện phải hỏi nó).
#:
#: Vì sao cần bảng ghim này dù đã có hai guard ở trên: cả hai đều mù trước ca "hỏi một cặp HỢP LỆ
#: nhưng SAI NÚT". Ví dụ nút *Chốt kỳ công* từng gác bằng `cham_cong:adjust` — cặp đó có thật, có
#: được máy chủ gác, khoá `cham_cong` cũng được giao diện dùng — nên không guard nào kêu. Chỉ có
#: người ngồi bấm mới thấy: có ô Chấm bù là thấy nút Chốt kỳ, mà bấm thì 403.
#:
#: KHUÔN SAI NÀY ĐÃ LẶP BỐN LẦN trong đợt 11/08/2026 — mỗi lần đều là "đổi khoá ở máy chủ, quên
#: màn". Bảng này chỉ ghim những nút mà bấm nhầm là đau: chốt kỳ, duyệt chi tiền, đảo số công nợ.
NUT_NGUY_HIEM: list[tuple[str, str, str, str]] = [
    # (mô tả, module, action, file giao diện)
    ("Chốt kỳ công / Mở lại kỳ", "cham_cong", "lock", "ChamCongPage.tsx"),
    ("Duyệt / từ chối PMH", "ke_toan", "approve", "AccountingPurchaseInboxPage.tsx"),
    ("Sửa số nhận · Mở lại đơn · Đóng đơn", "thu_mua", "manage_status", "PurchaseRequestsPage.tsx"),
    ("Duyệt yêu cầu chỉnh công", "yeu_cau_chinh_cong", "approve", "ChamCongPage.tsx"),
    ("Xem tab Yêu cầu chỉnh công", "yeu_cau_chinh_cong", "read", "ChamCongPage.tsx"),
    ("Chốt bảng lương", "luong", "lock", "LuongPage.tsx"),
    ("Đánh dấu đã chi lương", "luong", "manage_status", "LuongPage.tsx"),
    ("Lập phiếu chi", "phieu_chi", "create", "AccountingPurchaseInboxPage.tsx"),
    ("Duyệt phiếu đi muộn / về sớm", "di_muon", "approve", "ChamCongPage.tsx"),
]


def test_nut_nguy_hiem_hoi_dung_o_quyen_cua_no():
    """Mỗi nút nguy hiểm phải được gác bằng ĐÚNG ô của nó, ở ĐÚNG màn có nút."""
    thieu = []
    for mo_ta, khoa, viec, ten_file in NUT_NGUY_HIEM:
        ds = list(FE.rglob(ten_file))
        if not ds:
            thieu.append(f"  {mo_ta}: không tìm thấy file {ten_file}")
            continue
        nguon = ds[0].read_text(encoding="utf-8")
        mau = rf'can\(\s*"{khoa}"\s*,\s*"{viec}"\s*\)'
        if not re.search(mau, nguon):
            thieu.append(f'  {mo_ta}: {ten_file} không hỏi can("{khoa}", "{viec}")')
    assert not thieu, (
        "Nút nguy hiểm không gác bằng ô của chính nó — nhiều khả năng đổi khoá ở máy chủ mà quên "
        "màn. Hậu quả: cấp quyền rồi mà nút không hiện, hoặc thấy nút mà bấm ăn 403.\n"
        + "\n".join(thieu)
    )


def test_danh_sach_cho_phep_khong_con_thua():
    """`CHO_PHEP` phải co lại theo thời gian. Cặp nào máy chủ ĐÃ gác rồi thì gỡ khỏi đây —
    để lại chỉ khiến lần sau tưởng chỗ đó vẫn hở."""
    gac = _may_chu_gac()
    thua = sorted(f"{k}:{a}" for (k, a) in CHO_PHEP if (k, a) in gac)
    assert not thua, (
        "Cặp này máy chủ đã gác rồi, gỡ khỏi `CHO_PHEP` đi: " + ", ".join(thua)
    )
