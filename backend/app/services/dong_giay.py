"""Dòng giấy — bước nào NẰM TRÊN dòng, bước nào đứng ngoài.

Một routing không phải bước nào cũng chạm giấy: ghi kẽm đếm BẢN, làm khuôn đếm BỘ, đóng thùng đếm
THÙNG. Chỉ những bước trên dòng giấy mới tham gia chuỗi bù hao ngược (`bu_hao_engine.chuoi_nguoc`)
— đó là chuỗi trả lời "cần bao nhiêu tờ để đủ hàng", và nhét bước đếm kẽm vào đó là ra số vô nghĩa.

TRƯỚC 2026-08-11 việc phân loại này nằm rải ba chỗ, mỗi chỗ một luật:
  - `tinh_nguoc_routing`: đơn vị vào/ra khác None  (vì DANH SÁCH đơn vị công đoạn chỉ có 5 mã
    dòng giấy, nên "có khai đơn vị" ⇔ "trên dòng giấy" — đúng nhưng chỉ đúng NHỜ danh sách cứng)
  - `bai_ghep_service`: `nhom != "prepress"`      (theo NHÓM công đoạn)
  - `_canh_bao_don_vi`: lại lọc theo đơn vị None   (hàm đã gỡ 25/08/2026 cùng rổ cảnh báo mềm)
Từ 2026-08-11 câu hỏi đó hỏi CỜ TRẠM trên danh mục (`don_vi_do.tram_dong_giay`): công đoạn khai đơn
vị tự do từ danh mục Đơn vị & quy đổi, nên "có khai đơn vị" không còn đồng nghĩa "trên dòng giấy".

Từ 2026-09-06 CỜ ĐÓ ĐÃ GỠ. Ô "Đơn vị đầu vào / đầu ra" của công đoạn nay là MENU ĐÓNG đúng 5 chặng
(`TRAM_DONG_GIAY`), nên mã đơn vị Ở BƯỚC chính là tên chặng — không cần lớp trung gian nào dịch
giữa hai thứ. Lớp ấy vốn chỉ cho phép ĐỔI TÊN một chặng (khai `to_chay` thay `to`), chứ không thêm
được chặng thứ 6: `CAU_TRAM` và `_he_so_cau` đóng cứng trong code. Đổi lại nó bắt người khai danh
mục đơn vị (việc của kho, mua hàng) phải hiểu dòng giấy để gắn cờ cho đúng — sai một dòng là số
giấy của mọi lệnh lệch theo, mà chẳng màn nào báo.

`ban_do_tram` vì thế không còn truy vấn DB, nhưng GIỮ NGUYÊN chữ ký `(db)` và cái map truyền tay:
5 service (~20 chỗ gọi) đang chuyền `ban_do` xuống các hàm thuần, gỡ tham số ấy là một đợt sửa rộng
không mua thêm gì. Ai đọc tới đây rồi muốn dọn nốt thì dọn cả cụm một lần.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.don_vi_do import TRAM_DONG_GIAY, TRAM_TO, tram_chay_xuoi

__all__ = ["TRAM_MAC_DINH", "ban_do_tram", "tram_cua", "tren_dong_giay", "chieu_hop_le",
           "dich_chuoi", "don_vi_chuoi", "ma_cua_tram"]

# 5 chặng của dòng giấy. Mã đơn vị ở bước = tên chặng, nên map này là ánh xạ đồng nhất — giữ dạng
# dict để mọi hàm bên dưới (và 5 service đang chuyền `ban_do` xuống) không phải đổi.
TRAM_MAC_DINH: dict[str, str] = {ma: ma for ma in TRAM_DONG_GIAY}


def ban_do_tram(db: Session | None = None) -> dict[str, str]:
    """`{mã đơn vị: trạm}` — nay là hằng số, `db` chỉ còn để nơi gọi khỏi phải sửa.

    Trả BẢN SAO: vài chỗ gọi nhét thêm khoá vào map nhận được (test, preview), sửa trúng hằng số
    dùng chung thì lỗi rò sang request sau.
    """
    return dict(TRAM_MAC_DINH)


def tram_cua(don_vi: str | None, ban_do: dict[str, str]) -> str | None:
    """Trạm dòng giấy của một mã đơn vị. None = đơn vị ngoài dòng giấy, hoặc mã không có trong danh mục."""
    return ban_do.get(don_vi) if don_vi else None


def tren_dong_giay(don_vi_vao: str | None, don_vi_ra: str | None, ban_do: dict[str, str],
                   *, nhom: str | None = None) -> bool:
    """Bước này có nằm trên dòng giấy không. MỘT luật: hai đầu đều là chặng.

    Bỏ TRỐNG cả hai = bước ngoài dòng giấy — đó là câu người khai nói thẳng ở ô Đơn vị vào/ra của
    màn Công đoạn (menu đóng 5 chặng, mục trống là "—"), không còn là "dữ liệu cũ chưa khai".

    Vì thế lối LÙI theo `nhom` (chưa khai đơn vị + `nhom != "prepress"` ⇒ coi như trên dòng) đã BỎ
    06/09/2026: giữ nó thì cùng một bước bỏ trống lại được trả lời khác nhau tuỳ nơi gọi có truyền
    `nhom` hay không — `lsx_service` bảo ngoài dòng, `bai_ghep_service` bảo trong dòng. Tham số
    `nhom` giữ lại (bị bỏ qua) để mấy chỗ gọi cũ không gãy; đừng truyền thêm ở chỗ mới.

    Một chân trong một chân ngoài (`cai → thung`, đóng gói) KHÔNG còn khai được — validate của
    công đoạn chặn. Nếu lọt qua từ dữ liệu cũ thì FALSE: cho nó vào chuỗi thì đích của chuỗi hoá
    ra đếm bằng thùng, mà cầu `cái → thùng` là sức chứa của từng đơn chứ không phải cầu quy cách.
    """
    return (tram_cua(don_vi_vao, ban_do) is not None
            and tram_cua(don_vi_ra, ban_do) is not None)


def dich_chuoi(so_luong_dat: float, *, tram_ra_cuoi: str | None, cai_moi_to: float,
               he_so: dict) -> float:
    """ĐÍCH của chuỗi bù hao ngược, quy về ĐƠN VỊ RA của bước cuối. Hàm THUẦN.

    Chuỗi chạy ngược từ "cần bao nhiêu hàng tốt ở cuối". Câu đó phải nói bằng đúng thứ bước cuối
    NHẢ RA: routing kết ở thành phẩm thì đích là số lượng đặt, kết ở con thì là số con, kết ở tờ
    thì là số tờ in.

    Trước 11/08/2026 hai tầng trả lời khác nhau — tính giá xét `dv_cuoi == "cai"` rồi lấy số tờ cho
    mọi ca còn lại, còn lệnh sản xuất luôn lấy số lượng đặt. Routing kết ở `con` là hai màn ra hai
    số giấy lệch nhau đúng `con` lần. Nay một công thức chung:

        đích = (SL đặt ÷ số cái trên 1 tờ) × (số <đơn vị cuối> trên 1 tờ)

    Vế trái là số TỜ IN cần; nhân cầu `tờ → X` ra số X cần. Tự đúng cho mọi trạm: `cai` rút gọn về
    chính SL đặt, `to`/`tay` về số tờ (một tờ gấp thành một tay). Không biết cầu `tờ → X` thì giữ
    mốc TỜ — thà bảo toàn số giấy còn hơn nhân bằng hệ số đoán.
    """
    cmt = float(cai_moi_to or 0)
    to_can = float(so_luong_dat) / cmt if cmt > 0 else 0.0
    if not tram_ra_cuoi or tram_ra_cuoi == TRAM_TO:
        return to_can
    cau = float((he_so or {}).get((TRAM_TO, tram_ra_cuoi)) or 0)
    return to_can * cau if cau > 0 else to_can


def ma_cua_tram(tram: str, ban_do: dict[str, str]) -> str | None:
    """MÃ đơn vị đứng ở một trạm — CHỈ khi danh mục có đúng MỘT. Nhiều hơn ⇒ None.

    Lối lùi cho những chỗ không đọc được đơn vị từ routing (vd lệnh chưa khai công đoạn nào nhưng
    đã có số tờ). Vẫn là hỏi DANH MỤC, không phải viết cứng `"to"` — xưởng đổi tên đơn vị thì chỗ
    gọi đổi theo. Hai đơn vị cùng trạm thì KHÔNG đoán: trả None để nơi gọi nói "chưa đối chiếu
    được", vì hai đơn vị cùng trạm có thể có hai đường quy đổi khác nhau.
    """
    mas = [ma for ma, t in ban_do.items() if t == tram]
    return mas[0] if len(mas) == 1 else None


def _dv(b, ten: str):
    """Đọc field của một bước — nhận cả ORM row lẫn dict (preview dựng dict trong bộ nhớ)."""
    return b.get(ten) if isinstance(b, dict) else getattr(b, ten, None)


def don_vi_chuoi(buocs, ban_do: dict[str, str]) -> dict[str, str | None]:
    """MÃ đơn vị của từng CHẶNG dòng giấy, đọc từ chính routing.

    Vì sao cần: màn DANH SÁCH (nhiều lệnh trên một bảng) không đọc được đơn vị như màn chi tiết —
    một tiêu đề cột không nói được hai đơn vị khi lệnh sách đếm `to_chay` còn lệnh bao bì đếm
    `tam`. Nên server gửi mã đơn vị THEO TỪNG DÒNG, client tra tên trong danh mục.

    Trả MÃ chứ không trả tên: tên nằm ở danh mục Đơn vị, client đã nạp sẵn (`tenDonVi.ts`). Gửi tên
    từ đây là dựng nguồn tên thứ hai — đúng cái vừa dọn xong.

    Chặng nào routing KHÔNG nói tới thì trả None; client tự chọn nhãn mặc định. Đừng mượn mã của
    chặng khác lấp vào: hai cột cùng tên mà hai con số là kiểu sai khó thấy nhất.

    Cùng luật với `donViChuoi` bên frontend (`pages/lsxBuoc.ts`) — hai bản phải đọc ra cùng một
    thứ, khác nhau là màn chi tiết và màn danh sách nói hai đơn vị khác nhau cho cùng một lệnh.
    """
    chuoi = [b for b in sorted(buocs, key=lambda x: _dv(x, "thu_tu") or 0)
             if tren_dong_giay(_dv(b, "don_vi_vao"), _dv(b, "don_vi_ra"), ban_do)]
    buoc_in = next((b for b in chuoi if _dv(b, "nhom") == "print"), None)
    dau = next((b for b in chuoi if _dv(b, "don_vi_vao")), None)
    doi_muc = [b for b in chuoi
               if _dv(b, "don_vi_ra") and _dv(b, "don_vi_ra") != _dv(b, "don_vi_vao")]
    dv_to = _dv(buoc_in, "don_vi_vao") if buoc_in else None
    dv_to = dv_to or (_dv(dau, "don_vi_vao") if dau else None)
    # Bước đầu chuỗi khác bước in ⇒ nó đứng ở chặng TỜ NGUYÊN (bước xả giấy). Không có bước xả thì
    # tờ nguyên chỉ là số suy ra, routing không nói gì ⇒ None.
    dv_to_nguyen = (
        _dv(dau, "don_vi_vao")
        if dau and _dv(dau, "don_vi_vao") != (_dv(buoc_in, "don_vi_vao") if buoc_in else None)
        else None
    )
    # Chặng GIỮA (tay sách) = đầu ra của bước đổi mức ÁP CHÓT. KHÔNG lấy `doi_muc[0]`: bước XẢ GIẤY
    # cũng là một bước đổi mức (`to_lon → to_chay`), nên chuỗi sách CÓ xả có tới ba bước đổi mức và
    # `[0]` rơi đúng vào bước xả — trả về chính chặng tờ in thay vì tay. Áp chót mà vẫn là tờ in
    # nghĩa là chuỗi đi thẳng tờ → thành phẩm, không có chặng giữa nào.
    dv_giua = _dv(doi_muc[-2], "don_vi_ra") if len(doi_muc) >= 2 else None
    return {
        "to": dv_to,
        "to_nguyen": dv_to_nguyen,
        "tp": _dv(doi_muc[-1], "don_vi_ra") if doi_muc else None,
        "tay": dv_giua if dv_giua and dv_giua != dv_to else None,
    }


def chieu_hop_le(don_vi_vao: str | None, don_vi_ra: str | None, ban_do: dict[str, str]) -> bool:
    """Cặp đơn vị của bước có chảy đúng chiều dòng giấy không.

    Bước NGOÀI dòng giấy luôn hợp lệ — `bai → kem` không có chiều nào để mà sai.
    """
    if not tren_dong_giay(don_vi_vao, don_vi_ra, ban_do):
        return True
    return tram_chay_xuoi(tram_cua(don_vi_vao, ban_do), tram_cua(don_vi_ra, ban_do))
