"""Vì sao bước này CHƯA tính được giờ / CHƯA tìm được khe — câu trả lời kèm SỐ THẬT.

Trước 21/08/2026 ba mã cảnh báo thời lượng hiện ra bằng đúng một câu cố định, ví dụ *"Đơn vị của
bước chưa quy đổi được về đơn vị tốc độ máy."* Câu đó đúng về mặt kỹ thuật nhưng người xếp lịch đọc
xong vẫn không biết phải đi khai cái gì: đơn vị nào sang đơn vị nào, khai ở màn nào. Tệ hơn, nó nói
"đơn vị tốc độ máy" cho cả bước LÀM TAY THEO TỔ — bước "Đóng gói + nhập kho" chẳng có máy nào để mà
khai tốc độ, nên người đọc đi tìm mãi một ô không tồn tại.

Module này dựng lại mấy câu đó từ chính dữ liệu engine thời lượng vốn đã cầm trong tay — loại bước ·
số lượng vào · đơn vị nguồn · đơn vị đích · tên máy / tên đầu việc khoán — nên KHÔNG tốn thêm truy
vấn nào ngoài một `db.get(MayThietBi)` cho bước máy và bảng TÊN đơn vị (`service.ten_don_vi()`,
nhớ sẵn trên service cho cả lượt dò).

Đơn vị bày ra là TÊN trong danh mục ("tờ"), không phải mã lưu ở cột (`to`) — người xếp lịch không
tra mã.

Nguyên tắc viết câu: *nói cái đang thiếu, ở đâu khai, bằng số của chính bước này*. Không mã lỗi trần,
không "vướng ràng buộc khác".
"""
from __future__ import annotations

from ...models.lsx import LB_MAY, LB_TO
from ...models.may_thiet_bi import MayThietBi
from ...repositories.don_vi_do_repo import nhan_don_vi
from ..lsx_service import _f, ma_don_vi_toc_do

#: Câu chốt hạ khi không dựng nổi câu cụ thể (thiếu cả bước gốc) — vẫn phải nói mã đang vướng.
_MAC_DINH = {
    "may_chua_toc_do": ("Chưa có tốc độ (máy) hoặc năng suất (đầu việc khoán) nên chưa tính được "
                        "giờ chạy của bước.",
                        "Mở Lệnh SX → drawer bước để xem bước đang thiếu tốc độ hay năng suất."),
    "chua_quy_doi": ("Chưa quy đổi được số lượng vào sang đơn vị dùng để tính giờ nên chưa ra được "
                     "thời lượng.",
                     "Khai cầu quy đổi ở Cấu hình danh mục → Đơn vị & quy đổi."),
}


def _txt(v) -> str:
    return str(v).strip() if v not in (None, "") else ""


def _so(v) -> str:
    """Số cho câu tiếng Việt: 12000 → "12.000" · 37.5 → "37,5"."""
    n = _f(v)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")


def _may(service, dong, cd):
    may_id = getattr(dong, "may_id", None) or getattr(cd, "may_id", None)
    return service.db.get(MayThietBi, may_id) if may_id else None


def _dv(service, ma) -> str:
    """MÃ đơn vị (`to`) → TÊN người đọc được ("tờ"). Câu chẩn đoán viết cho NGƯỜI xếp lịch, mà
    mọi cột `don_vi*` của tầng sản xuất giữ mã. Bảng tra nhớ trên service, không tra từng dòng."""
    return nhan_don_vi(service.ten_don_vi(), _txt(ma))


def _khoan(service, cd) -> tuple[str, str]:
    """(tên đầu việc khoán, TÊN đơn vị đơn giá) đã ghim ở bước — rỗng khi bước chưa chọn đầu việc."""
    kh = getattr(cd, "khoan_json", None) or {}
    return _txt(kh.get("ten")), _dv(service, kh.get("don_vi"))


def _nhan_vao(service, cd) -> tuple[str, str]:
    """("Bước nhận 12.000 tờ", "tờ") — vế mở đầu câu + đơn vị nguồn để nhắc lại ở gợi ý."""
    sl = _f(getattr(cd, "so_luong_vao", 0))
    dv = _dv(service, getattr(cd, "don_vi_vao", None))
    if sl > 0 and dv:
        return f"Bước nhận {_so(sl)} {dv}", dv
    if sl > 0:
        return f"Bước nhận {_so(sl)} (chưa khai đơn vị)", ""
    return "Bước", dv


def _cau_quy_doi(nhan: str, dv_nguon: str, dv_dich: str, mo_ta_dich: str) -> tuple[str, str]:
    nguon = dv_nguon or "đơn vị của bước"
    return (
        f"{nhan} nhưng {mo_ta_dich} đếm bằng {dv_dich} — chưa có cách quy {nguon} → {dv_dich}, "
        f"nên phép chia ra giờ không thực hiện được.",
        f"Khai cầu quy đổi {nguon} → {dv_dich} ở Cấu hình danh mục → Đơn vị & quy đổi "
        f"(hoặc khai công thức lượng cho đơn vị {dv_dich}).",
    )


def chi_tiet(service, dong, ma: str) -> tuple[str, str]:
    """`(mô tả, gợi ý)` CỤ THỂ cho một mã cảnh báo thời lượng.

    `dong` là dòng lịch (hoặc bản shadow đang thử) — máy lấy từ nó vì người dùng có thể đang gõ thử
    một máy khác với máy ghim ở routing. Không dựng nổi câu riêng thì rơi về `_MAC_DINH`, tuyệt đối
    không để mã trần lọt ra màn hình.
    """
    from .auto import _buoc_goc

    mac_dinh = _MAC_DINH.get(ma, ("Cần xem lại dữ liệu bước.", ""))
    cd = _buoc_goc(service, dong)
    if cd is None:
        return mac_dinh
    loai = getattr(cd, "loai_buoc", LB_MAY) or LB_MAY

    if ma == "may_chua_toc_do":
        if loai == LB_TO:
            ten, dv = _khoan(service, cd)
            if not ten:
                return ("Bước làm tay chưa chọn đầu việc khoán nên chưa có năng suất để tính giờ "
                        "làm.",
                        "Chọn đầu việc khoán cho bước ở Lệnh SX → drawer bước.")
            don = f"{dv}/người/giờ" if dv else "sản lượng/người/giờ"
            return (f"Đầu việc khoán “{ten}” chưa khai năng suất ({don}) nên chưa tính được giờ "
                    f"làm của bước.",
                    f"Khai năng suất cho “{ten}” ở Danh mục → Công việc khoán.")
        may = _may(service, dong, cd)
        if may is None:
            return ("Bước chưa gán máy nên chưa có tốc độ để tính giờ chạy.",
                    "Chọn máy cho bước ở Lệnh SX → drawer bước (hoặc để Xếp lịch tự chọn máy).")
        return (f"Máy “{may.ten}” chưa khai tốc độ nên chưa tính được giờ chạy của bước.",
                f"Khai ô Tốc độ (và đơn vị tốc độ) cho “{may.ten}” ở Danh mục → Máy & thiết bị.")

    if ma == "chua_quy_doi":
        nhan, dv_nguon = _nhan_vao(service, cd)
        if loai == LB_TO:
            ten, dv_dich = _khoan(service, cd)
            if not dv_dich:
                thieu = ("chưa chọn đầu việc khoán" if not ten
                         else f"đầu việc khoán “{ten}” chưa khai đơn vị")
                return (f"Bước làm tay {thieu} nên chưa biết quy số lượng về đơn vị nào để chia ra "
                        f"giờ làm.",
                        "Chọn đầu việc khoán ở Lệnh SX → drawer bước, hoặc khai đơn vị cho đầu "
                        "việc ở Danh mục → Công việc khoán.")
            return _cau_quy_doi(nhan, dv_nguon, dv_dich, f"năng suất khoán của “{ten}”")
        may = _may(service, dong, cd)
        if may is None:
            return ("Bước chưa gán máy nên chưa biết quy số lượng về đơn vị nào để chia ra giờ "
                    "chạy.",
                    "Chọn máy cho bước ở Lệnh SX → drawer bước (hoặc để Xếp lịch tự chọn máy).")
        dv_dich = _dv(service, ma_don_vi_toc_do(may))
        if not dv_dich:
            cai_gi = dv_nguon or "số lượng của bước"
            return (f"Máy “{may.ten}” chưa khai đơn vị tốc độ nên chưa biết quy {cai_gi} về đâu.",
                    f"Khai Tốc độ + đơn vị tốc độ cho “{may.ten}” ở Danh mục → Máy & thiết bị.")
        return _cau_quy_doi(nhan, dv_nguon, dv_dich, f"tốc độ máy “{may.ten}”")

    return mac_dinh


# ============================ VÌ SAO KHÔNG CÓ KHE NÀO ============================
def _ha(cau: str) -> str:
    """Câu luật (hoa đầu, có chấm) → MỆNH ĐỀ ghép được vào giữa danh sách."""
    cau = cau.strip().rstrip(".")
    return (cau[:1].lower() + cau[1:]) if cau else cau


def vi_sao_khong_co_khe(dem: dict[str, int], mo_ta: dict[str, str], *,
                        so_moc: int, chan_ngay: int) -> str:
    """Mệnh đề cho ca "dò hết mà không mốc nào sạch" — GỌI TÊN luật đã chặn, kèm số mốc.

    Trước đây chỗ này chỉ kể luật chặn tại MỐC ĐẦU TIÊN, mà mốc đầu thường vướng thứ vặt (ngoài ca)
    trong khi thứ thật sự bịt cả cửa sổ là máy kín. Nay đếm trên TOÀN BỘ mốc đã dò rồi kể theo thứ
    tự chặn nhiều nhất trước — người xếp lịch biết ngay phải gỡ cái nào.

    Trả về mệnh đề thường (không hoa đầu, không chấm) vì mọi nơi gọi đều ghép nó sau một vế dẫn.
    """
    if not so_moc:
        return ("không còn mốc bắt đầu nào để thử — lịch xưởng chưa khai ca, hoặc bước phải đợi "
                f"tiền nhiệm xong quá {chan_ngay} ngày dò")
    if not dem:
        return f"dò {so_moc} mốc bắt đầu, không mốc nào đặt được"
    xep = sorted(dem.items(), key=lambda kv: (-kv[1], kv[0]))
    ke = " · ".join(f"{_ha(mo_ta.get(k) or k)} ({v} mốc)" for k, v in xep[:3])
    them = f" · và {len(xep) - 3} vướng khác" if len(xep) > 3 else ""
    return f"cả {so_moc} mốc bắt đầu đều vướng: {ke}{them}"
