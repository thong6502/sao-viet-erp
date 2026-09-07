"""So ẢNH CHỤP mà lệnh sản xuất đang giữ với DANH MỤC hiện tại — phần THUẦN, không đụng DB.

Vì sao có việc này: bước lệnh GHIM `khoan_json` lúc bung lệnh (`piece_work_service.khoan_snapshot`)
và ghim luôn các dòng vật tư đã bung. Xưởng sửa công thức ở danh mục Công đoạn về sau thì lệnh đã
tạo KHÔNG hay biết — đúng thiết kế (lệnh đã phát xuống xưởng không được tự đổi tiền dưới chân thợ),
nhưng người lập kế hoạch cũng chẳng có gì để mà BIẾT mà bấm lấy số mới. Băng "Danh mục đã đổi" của
phiếu tính giá (`tinh_gia_service.danh_muc_doi_sau_khi_tinh`) trả lời đúng câu hỏi đó, nhưng ở
tầng báo giá.

KHÔNG chép cách làm của băng ấy. Nó so `updated_at` của bảng CHA, mà công thức khoán · định mức
vật tư · công thức máy đều nằm ở bảng CON (`cong_doan_dau_viec`, `cong_doan_dau_viec_vat_tu`,
`cong_doan_may`) — ba bảng đó không có lấy một cột thời gian, và sửa con KHÔNG chạm
`cong_doan.updated_at` (đo trên DB dev 07/09/2026: thêm hai dòng vật tư cho CD-0012 xong
`updated_at` vẫn đứng ở 20/08). So mốc thì im lặng đúng lúc cần nói nhất.

Ở đây so THẲNG NỘI DUNG: dựng lại ảnh chụp "nếu bung bây giờ" rồi đối chiếu với ảnh đang lưu.
Không thêm cột nào, và nói được đích danh bước nào lệch ô nào.

Phần đọc DB (dựng ảnh mới, bung lại vật tư) nằm ở `LsxService._soi_danh_muc` — ở đây chỉ có phép
SO, để test được mà không phải dựng cả lệnh.
"""
from __future__ import annotations

from .don_vi_do_service import cong_thuc_chu

# Ô của ảnh chụp khoán đem ra so, kèm nhãn người đọc. KHÔNG so `rate_id` (số nội bộ — đổi id là
# đổi hẳn đầu việc, đã có nhánh "mồ côi" lo) và không so các khoá min/max của năng suất (chúng chỉ
# vẽ râu nhanh–chậm trên Gantt, không vào tiền cũng không vào thời lượng).
KHOAN_TRUONG: tuple[tuple[str, str], ...] = (
    ("ten", "Tên đầu việc"),
    ("don_vi", "Đơn vị đơn giá"),
    ("don_gia", "Đơn giá khoán"),
    ("cong_thuc", "Cách tính tiền công"),
    ("cong_thuc_gio", "Cách đo giờ chạy"),
    ("nang_suat_nguoi_gio", "Năng suất người-giờ"),
    ("don_vi_nang_suat", "Đơn vị năng suất"),
    ("so_nguoi_tieu_chuan", "Kíp chuẩn"),
)

# Ô nào là CÔNG THỨC — hiện ra thì dịch sang chữ đọc được ("Dài tờ in × Rộng tờ in") thay vì bày
# mã biến. Người lập kế hoạch đọc băng này để QUYẾT, không phải để debug.
CONG_THUC_TRUONG = frozenset({"cong_thuc", "cong_thuc_gio"})

# So số thực: hai đường tính khác nhau (float của DB vs float vừa dựng) lệch nhau ở chữ số cuối là
# chuyện thường, mà báo "đơn giá 600 → 600" thì băng mất uy tín ngay lần đầu.
SAI_SO = 1e-9


def _chuan(v):
    """"Chưa có gì" quy về MỘT dạng: `None`, chuỗi rỗng và chuỗi toàn khoảng trắng là như nhau.

    Cần vì `khoan_snapshot` VẮNG hẳn khoá `cong_thuc` khi công thức rỗng, còn ảnh chụp cũ lại có
    khoá ấy mang chuỗi rỗng — không quy về một dạng thì mọi bước cũ đều báo lệch giả.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    return v


def _khac(cu, moi) -> bool:
    """Hai giá trị có khác nhau DƯỚI MẮT người dùng không."""
    if cu is None and moi is None:
        return False
    if cu is None or moi is None:
        return True
    if isinstance(cu, bool) or isinstance(moi, bool):
        return bool(cu) != bool(moi)
    if isinstance(cu, (int, float)) and isinstance(moi, (int, float)):
        return abs(float(cu) - float(moi)) > SAI_SO
    return str(cu).strip() != str(moi).strip()


def _hien(truong: str, v) -> str | None:
    """Giá trị → chuỗi bày trên băng. `None` = ô đang bỏ trống, FE tự vẽ dấu —."""
    if v is None:
        return None
    if truong in CONG_THUC_TRUONG:
        return cong_thuc_chu(str(v))
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def khoan_lech(cu: dict | None, moi: dict | None) -> list[dict]:
    """Ảnh chụp khoán CŨ vs MỚI → `[{truong, nhan, cu, moi}]`. Rỗng = còn khớp danh mục."""
    cu, moi = cu or {}, moi or {}
    ra: list[dict] = []
    for truong, nhan in KHOAN_TRUONG:
        a, b = _chuan(cu.get(truong)), _chuan(moi.get(truong))
        if _khac(a, b):
            ra.append({"truong": truong, "nhan": nhan,
                       "cu": _hien(truong, a), "moi": _hien(truong, b)})
    return ra


def vat_tu_lech(hien_co: list[dict], theo_danh_muc: list[dict]) -> dict:
    """Dòng vật tư ĐANG nằm trên bước vs dòng danh mục bung ra bây giờ.

    Trả `{"them", "bo", "lech"}` — ba rổ vì ba việc khác nhau:
      * `them` — danh mục có mà bước chưa có ⇒ bấm cập nhật là thêm vào, an toàn;
      * `lech` — cùng món, số khác ⇒ ghi đè được;
      * `bo`   — bước có mà danh mục không còn bung (thường vì ô "Công thức định mức" bị bỏ trống)
        ⇒ CHỈ BÁO, không tự xoá. Dòng ấy vẫn giữ số cũ và vẫn tính vào nhu cầu vật tư; bỏ hay giữ
        là quyết định của người lập kế hoạch, máy đoán sai thì mất một dòng vật tư thật.

    Dòng NGƯỜI KHAI (`tu_dong=False`) đứng ngoài cả `bo` lẫn `lech`: người ta đã cố ý gõ đè số đó,
    lấy số danh mục ghi lên là xoá việc họ vừa làm — cùng luật với cột "Đã sửa" trong drawer vật tư.
    """
    # Khoá là CẶP `(hang_loai, id)` (08/09/2026): bước nay ăn cả giấy lẫn vật tư, mà Giấy #7 và
    # Vật tư #7 là hai món khác nhau. Khoá bằng id trần thì "Cập nhật theo danh mục" đè số của một
    # dòng giấy bằng số của một món mực trùng id.
    cu_theo_id = {_cap(v): v for v in hien_co if v.get("vat_tu_id")}
    moi_theo_id = {_cap(v): v for v in theo_danh_muc if v.get("vat_tu_id")}
    them, bo, lech = [], [], []
    for vid, moi in moi_theo_id.items():
        cu = cu_theo_id.get(vid)
        if cu is None:
            them.append({**_mon(moi), "so_luong_cu": None,
                         "so_luong_moi": float(moi.get("so_luong") or 0)})
        elif cu.get("tu_dong") and _khac(_chuan(cu.get("so_luong")), _chuan(moi.get("so_luong"))):
            lech.append({**_mon(moi), "so_luong_cu": float(cu.get("so_luong") or 0),
                         "so_luong_moi": float(moi.get("so_luong") or 0)})
    for vid, cu in cu_theo_id.items():
        if vid not in moi_theo_id and cu.get("tu_dong"):
            bo.append({**_mon(cu), "so_luong_cu": float(cu.get("so_luong") or 0),
                       "so_luong_moi": None})
    return {"them": them, "bo": bo, "lech": lech}


def _cap(v: dict) -> tuple[str, int]:
    """Khoá nhận dạng một món trên bước. Dòng cũ / client cũ không mang `hang_loai` ⇒ là vật tư."""
    return (str(v.get("hang_loai") or "vat_tu"), int(v["vat_tu_id"]))


def _mon(v: dict) -> dict:
    """Bốn ô nhận dạng một món — `_vat_tu_bung` và dòng đã lưu đặt tên khoá khác nhau nên gom ở đây."""
    return {
        "hang_loai": str(v.get("hang_loai") or "vat_tu"),
        "vat_tu_id": int(v["vat_tu_id"]),
        "ma": v.get("ma") or v.get("vat_tu_ma"),
        "ten": v.get("ten") or v.get("vat_tu_ten"),
        "don_vi": v.get("don_vi"),
    }
