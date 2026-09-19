"""So ẢNH CHỤP mà lệnh sản xuất đang giữ với DANH MỤC hiện tại — phần THUẦN, không đụng DB.

Vì sao có việc này: bước lệnh GHIM các dòng vật tư đã bung lúc tạo lệnh. Xưởng sửa công thức định
mức ở danh mục Công đoạn về sau thì lệnh đã tạo KHÔNG hay biết — đúng thiết kế (lệnh đã phát xuống
xưởng không được tự đổi số dưới chân thợ), nhưng người lập kế hoạch cũng chẳng có gì để mà BIẾT mà
bấm lấy số mới. Băng "Danh mục đã đổi" của phiếu tính giá
(`tinh_gia_service.danh_muc_doi_sau_khi_tinh`) trả lời đúng câu hỏi đó, nhưng ở tầng báo giá.

KHÔNG chép cách làm của băng ấy. Nó so `updated_at` của bảng CHA, mà định mức vật tư và công thức
máy đều nằm ở bảng CON (`cong_doan_vat_tu`, `cong_doan_may`) — hai bảng đó không có lấy một cột
thời gian, và sửa con KHÔNG chạm `cong_doan.updated_at` (đo trên DB dev 07/09/2026: thêm hai dòng
vật tư cho CD-0012 xong `updated_at` vẫn đứng ở 20/08). So mốc thì im lặng đúng lúc cần nói nhất.

Ở đây so THẲNG NỘI DUNG: dựng lại ảnh chụp "nếu bung bây giờ" rồi đối chiếu với ảnh đang lưu.
Không thêm cột nào, và nói được đích danh bước nào lệch ô nào.

Phần đọc DB (bung lại vật tư) nằm ở `LsxService._soi_danh_muc` — ở đây chỉ có phép SO, để test
được mà không phải dựng cả lệnh.

⚠️ 18/09/2026 (mg `0320`): nửa KHOÁN (`KHOAN_TRUONG` · `khoan_lech`) GỠ HẲN cùng ô đầu việc của
bước lệnh. Ba phép THUẦN còn lại (`_chuan` · `khac` · `hien`) thì GIỮ và mở ra public: băng
"Danh mục đã đổi" của MẺ sản xuất (§7.2b — so ảnh chụp tên/đơn vị/đơn giá của mẻ với danh mục
Công việc khoán) dùng lại đúng ba phép này, để hai băng cùng một định nghĩa "khác nhau".
"""
from __future__ import annotations

# So số thực: hai đường tính khác nhau (float của DB vs float vừa dựng) lệch nhau ở chữ số cuối là
# chuyện thường, mà báo "đơn giá 600 → 600" thì băng mất uy tín ngay lần đầu.
SAI_SO = 1e-9


def _chuan(v):
    """"Chưa có gì" quy về MỘT dạng: `None`, chuỗi rỗng và chuỗi toàn khoảng trắng là như nhau.

    Cần vì ảnh chụp dựng ở hai thời điểm khác nhau hay VẮNG hẳn một khoá ở bản này mà mang chuỗi
    rỗng ở bản kia — không quy về một dạng thì mọi bản ghi cũ đều báo lệch giả.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    return v


def khac(cu, moi) -> bool:
    """Hai giá trị có khác nhau DƯỚI MẮT người dùng không. Public: băng mẻ dùng chung."""
    if cu is None and moi is None:
        return False
    if cu is None or moi is None:
        return True
    if isinstance(cu, bool) or isinstance(moi, bool):
        return bool(cu) != bool(moi)
    if isinstance(cu, (int, float)) and isinstance(moi, (int, float)):
        return abs(float(cu) - float(moi)) > SAI_SO
    return str(cu).strip() != str(moi).strip()


def hien(v) -> str | None:
    """Giá trị → chuỗi bày trên băng. `None` = ô đang bỏ trống, FE tự vẽ dấu —.

    Số nguyên-ở-dạng-float về dạng nguyên: đơn giá `250.0` bày thành `250`, không thì băng khoe
    "250.0 → 260.0" trông như một thứ máy sinh chứ không phải con số người vừa gõ.
    """
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def o_lech(cu: dict | None, moi: dict | None,
           truong_nhan: tuple[tuple[str, str], ...]) -> list[dict]:
    """Hai ảnh chụp CŨ vs MỚI → `[{truong, nhan, cu, moi}]`. Rỗng = còn khớp danh mục.

    Bộ ô đem so do NƠI GỌI truyền vào (`truong_nhan`), không ghi cứng ở đây: mẻ sản xuất so
    tên · đơn vị · đơn giá, mà bản sau này có thêm băng khác thì cũng chỉ là một tuple nữa.
    Thay `khoan_lech` (bộ ô ghi cứng của ảnh chụp đầu việc) gỡ 18/09/2026.
    """
    cu, moi = cu or {}, moi or {}
    ra: list[dict] = []
    for truong, nhan in truong_nhan:
        a, b = _chuan(cu.get(truong)), _chuan(moi.get(truong))
        if khac(a, b):
            ra.append({"truong": truong, "nhan": nhan, "cu": hien(a), "moi": hien(b)})
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
        elif cu.get("tu_dong") and khac(_chuan(cu.get("so_luong")), _chuan(moi.get("so_luong"))):
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
