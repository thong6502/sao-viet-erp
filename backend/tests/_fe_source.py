"""Đọc mã nguồn GIAO DIỆN cho các guard "máy chủ đổi, giao diện quên".

VÌ SAO CÓ FILE NÀY — vỡ THẬT 25/08/2026:

Một loạt guard bên backend đọc thẳng MỘT file `.tsx` của frontend để hỏi "màn này có thật sự
dùng cờ máy chủ vừa thêm không". Cách hỏi thì đúng, nhưng cách ĐỌC thì mong manh: đợt refactor
dời + chẻ các màn thành thư mục (`pages/ChamCongPage.tsx` → `pages/nhan-su-luong/cham-cong/`
gồm shell + `tabs/` + `modals/` + `components/` + `shared/`), thế là 6 guard đỏ cùng lúc bằng
`FileNotFoundError` — không phải vì tính năng mất, mà vì file đổi chỗ.

Tệ hơn: kể cả vá lại đường dẫn cho trỏ đúng file shell mới thì vẫn sai, vì nội dung guard đi tìm
(`"day.restday"`, `"heSo.le"`, `"Công đặc biệt"`…) nay nằm ở FILE CON (`tabs/MyTimesheetTab.tsx`),
không còn trong shell. Vá kiểu đó là hẹn giờ đỏ lại lần sau, hoặc tệ hơn là hẹn giờ XANH GIẢ.

⇒ Guard đọc CẢ THƯ MỤC MÀN, không một file. Như vậy nó canh đúng Ý NGHĨA ("giao diện có dùng cờ
này không") và không gãy nữa khi ai đó chẻ tiếp.
"""

from __future__ import annotations

from pathlib import Path

#: `frontend/src` — gốc mã nguồn giao diện.
FE_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _la_module_rieng(thu_muc: Path) -> bool:
    """Thư mục con có `index.ts(x)` của riêng nó = MÀN KHÁC, đừng nuốt vào.

    Ví dụ sống: `nhan-su-luong/luong/cau-hinh/` nằm bên trong `nhan-su-luong/luong/` nhưng là màn
    Cấu hình lương riêng. Nuốt nó vào màn Lương thì guard mất răng — `test_com_tang_ca` hỏi HAI
    câu khác nhau ("phiếu lương có dòng Cơm tăng ca" vs "màn Cấu hình khai được hai ô"), gộp lại
    thì một câu trả lời thay được cả hai.
    """
    return (thu_muc / "index.ts").exists() or (thu_muc / "index.tsx").exists()


def _thu_thap(thu_muc: Path) -> list[Path]:
    ra: list[Path] = []
    for p in sorted(thu_muc.iterdir()):
        if p.is_dir():
            if not _la_module_rieng(p):
                ra.extend(_thu_thap(p))
        # BỎ `*.test.ts(x)`: file vitest TRÍCH DẪN chính chuỗi đang được canh, tính vào là guard
        # tự trả lời mình — màn gỡ mất tính năng mà test bên FE còn nhắc tên là vẫn xanh.
        elif p.suffix in (".ts", ".tsx") and ".test." not in p.name:
            ra.append(p)
    return ra


def doc_module_fe(*phan: str) -> str:
    """Gộp nội dung mọi file `.ts`/`.tsx` của MỘT thư mục màn giao diện, đệ quy.

    Đọc CẢ THƯ MỤC chứ không một file: các màn đã tách thành shell + `tabs/` + `modals/` +
    `components/` + `shared/`, nội dung có thể nằm ở bất kỳ file con nào. Đọc cả thư mục thì
    guard canh đúng Ý NGHĨA và không gãy khi ai đó chẻ tiếp.

    Loại trừ hai thứ để guard không mất răng: thư mục con là màn riêng (có `index.ts` của nó) và
    file `*.test.ts(x)` của vitest.

    Dùng: ``doc_module_fe("pages", "nhan-su-luong", "cham-cong")``.
    """
    thu_muc = FE_SRC.joinpath(*phan)
    assert thu_muc.is_dir(), (
        f"Không thấy thư mục màn giao diện: {thu_muc}\n"
        "Màn vừa bị dời/đổi tên? Sửa đường dẫn ở đây, ĐỪNG bỏ assert bên dưới."
    )
    tep = _thu_thap(thu_muc)
    assert tep, f"Thư mục màn giao diện rỗng (không có .ts/.tsx nào): {thu_muc}"
    return "\n".join(p.read_text(encoding="utf-8") for p in tep)


def doc_file_fe(*phan: str) -> str:
    """Đọc MỘT file giao diện — cho thứ vốn là một file thật (vd `api/client.ts`)."""
    tep = FE_SRC.joinpath(*phan)
    assert tep.is_file(), f"Không thấy file giao diện: {tep}"
    return tep.read_text(encoding="utf-8")


# ── Neo tên thư mục của các màn hay bị guard soi ─────────────────────────────────────────────
# Để một chỗ: lần sau màn dời nữa thì sửa ĐÚNG MỘT DÒNG ở đây, không phải đi lùng 6 file test.

MAN_CHAM_CONG = ("pages", "nhan-su-luong", "cham-cong")
MAN_LUONG = ("pages", "nhan-su-luong", "luong")
MAN_CAU_HINH_LUONG = ("pages", "nhan-su-luong", "luong", "cau-hinh")
MAN_HO_SO_CUA_TOI = ("pages", "nhan-su-luong", "ho-so-cua-toi")
MAN_KE_TOAN_DON_MUA_HANG = ("pages", "ke-toan", "don-mua-hang")
MAN_MUA_HANG_PHIEU = ("pages", "mua-hang", "phieu-mua-hang")
