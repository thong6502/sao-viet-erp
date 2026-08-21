"""Luật THỜI GIAN thuần của Xếp lịch 2 — HÀM LÁ, không chạm DB, không chạm engine cũ.

Mỗi hàm nhận đúng dữ liệu đã bóc sẵn (giờ, ca, khoảng khoá…) và trả về MỘT `issue` hoặc `None`.
Nhờ vậy test §12 soi được từng luật ở mức hàm mà khỏi dựng cả luồng đơn→lệnh (rẻ + chống hồi quy).

Ba MỨC kiểm soát (spec §7):
- `MUC_CANH_BAO`     — chỉ nhắc, không chặn.
- `MUC_CHAN_DAT_LICH`— chặn ngay lúc đặt/sửa lịch (ngoài ca · trùng máy · thiếu chủ · sai tiền
  nhiệm). Quân số tổ và vùng khoá máy KHÔNG còn trong nhóm này từ 21/08/2026 — xem
  `vuot_quan_so_to` và `de_vung_khoa_may`. Cả hai bị hạ vì cùng một bệnh: luật cứng dựng trên một
  bản khai TAY còn thưa thì chặn nhầm nhiều hơn chặn đúng. Còn lại trong nhóm này là những thứ máy
  tự biết chắc — hai việc không thể cùng nằm trên một máy, giờ không thuộc ca nào đã khai.
- `MUC_CHAN_PHAT_HANH`— cho đặt nháp, nhưng chặn lúc phát hành (vật tư chưa đủ).

CỐ Ý không có bất kỳ luật nào theo khổ giấy / số màu / định lượng (spec §6, §12.8): máy khớp hay
không là việc con người tự cân, v2 không kết luận hộ.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

MUC_CANH_BAO = "canh_bao"
MUC_CHAN_DAT_LICH = "chan_dat_lich"
MUC_CHAN_PHAT_HANH = "chan_phat_hanh"

GIO_BAT_DAU = 8            # giờ mặc định của ca đầu ngày khi chưa khai ca nào
PHUT_LAM_NGAY = 480        # 8 tiếng — độ dài ca mặc định


def issue(ma: str, muc: str, mo_ta: str, *, nguon: str = "", goi_y: str = "",
          doi_tuong: str = "") -> dict:
    """Gói một vấn đề về đúng một hình dạng để router/UI đọc được đều tay.

    `nguon` = LOẠI đối tượng vấn đề chạm tới (may · to · han · tien_nhiem · vat_tu · ca · buoc),
    để lớp service điền `doi_tuong` (tên máy/tổ cụ thể hoặc nhãn tĩnh) lúc trình bày.
    """
    return {"ma": ma, "muc": muc, "mo_ta": mo_ta, "nguon": nguon, "goi_y": goi_y,
            "doi_tuong": doi_tuong}


def _phut_trong_ngay(mth: datetime) -> int:
    return mth.hour * 60 + mth.minute


def finish_lien_tuc(start: datetime, chiem_may_phut: int) -> datetime:
    """Đã bắt đầu thì CHẠY LIÊN TỤC tới xong (§3.3): finish = start + chiếm-máy, theo đồng hồ tường.

    KHÔNG cắt theo ca, KHÔNG đi bộ qua từng khung giờ làm — kéo qua cuối ca / nửa đêm là bình thường.
    """
    return start + timedelta(minutes=int(chiem_may_phut))


def ngoai_ca(start: datetime, ca: list[tuple[int, int, bool]]) -> dict | None:
    """Cửa chặn DUY NHẤT của ca (§7.1): GIỜ BẮT ĐẦU phải rơi vào một ca đã cấu hình.

    `ca` = danh sách `(bat_dau_phut, ket_thuc_phut, qua_dem)` tính từ nửa đêm. Ca đêm (`qua_dem`)
    ôm nửa đêm nên đuôi ca thuộc phần đầu ngày hôm sau.
    """
    m = _phut_trong_ngay(start)
    for bat_dau, ket_thuc, qua_dem in ca:
        if qua_dem:
            if m >= bat_dau or m < ket_thuc:
                return None
        elif bat_dau <= m < ket_thuc:
            return None
    return issue(
        "ngoai_ca", MUC_CHAN_DAT_LICH,
        "Giờ bắt đầu không nằm trong ca làm nào.",
        nguon="ca",
        goi_y="Chọn giờ bắt đầu trong một ca đã khai.",
    )


def chua_tai_nguyen(
    start: datetime | None, may_id, department_id, nha_cung_cap,
) -> dict | None:
    """Đã chọn GIỜ mà chưa có ai làm ⇒ chặn ĐẶT LỊCH (§7.2).

    Một thanh nằm trên trục thời gian phải có chủ: máy, tổ, hoặc nhà cung cấp (thuê ngoài). Thiếu
    cả ba thì cái giờ ấy vô nghĩa — trước đây service âm thầm hạ trạng thái về "chờ xếp", giấu mất
    vấn đề; nay phơi thành vấn đề chặn ngay tại chỗ. Chưa chọn giờ (nháp trong khay) thì KHÔNG xét.
    """
    if start is None:
        return None
    if may_id or department_id or (nha_cung_cap or "").strip():
        return None
    return issue(
        "chua_tai_nguyen", MUC_CHAN_DAT_LICH,
        "Đã chọn giờ nhưng chưa gán máy · tổ · nhà cung cấp nào.",
        nguon="buoc",
        goi_y="Gán máy, tổ, hoặc nhà cung cấp (thuê ngoài) cho bước rồi mới đặt giờ.",
    )


def de_vung_khoa_may(
    start: datetime, finish: datetime, khoa: list[tuple[datetime, datetime]],
) -> dict | None:
    """Máy hỏng/bảo trì nằm CHẠM khoảng chạy ⇒ CẢNH BÁO (§7.3). Khoá ngoài khoảng thì không sao.

    HẠ TỪ CHẶN XUỐNG CẢNH BÁO 21/08/2026 theo yêu cầu chủ, cùng lý lẽ với `vuot_quan_so_to`: vùng
    khoá máy là thứ người ta khai TAY và khai thưa (dev đang có 0 dòng), nên nó mô tả dự định chứ
    không mô tả sự thật của xưởng. Lấy một bản khai thưa đi chặn cứng thì hai đằng đều sai: máy hỏng
    thật mà chưa ai kịp khai vẫn xếp được như thường, còn khoá khai dư lại bịt mất khe của một máy
    đang chạy tốt — mà người xếp không có đường đi tiếp ngoài việc xoá bản khai.

    Hạ mức là nới ĐÚNG một nấc, không phải xoá luật: vấn đề vẫn hiện nguyên câu trên thanh và trong
    danh sách vấn đề, chỉ khác là nó không còn tự bác nút Lưu (và theo `kiem_phat_hanh` thì cũng
    không còn chặn Phát hành). Muốn bật lại thành chặn thì đổi đúng một hằng ở dòng dưới.
    """
    for k_start, k_finish in khoa:
        if k_start < finish and start < k_finish:
            return issue(
                "de_vung_khoa_may", MUC_CANH_BAO,
                "Khoảng chạy đè lên thời gian máy hỏng/bảo trì.",
                nguon="may",
                goi_y="Cân nhắc dời sang khe khác hoặc đổi máy.",
            )
    return None


def trung_may(
    start: datetime, finish: datetime, da_xep: list[tuple[datetime, datetime]],
) -> dict | None:
    """Trùng việc khác trên CÙNG máy (§7.1). Nối đuôi (chạm mép) KHÔNG tính là trùng."""
    for o_start, o_finish in da_xep:
        if o_start < finish and start < o_finish:
            return issue(
                "trung_may", MUC_CHAN_DAT_LICH,
                "Trùng giờ với một việc khác trên cùng máy.",
                nguon="may",
                goi_y="Dời sang khe trống hoặc đổi máy.",
            )
    return None


def dinh_dong_thoi_chi_tiet(
    placements: list[tuple[datetime, datetime, int]],
) -> tuple[int, int]:
    """(ĐỈNH số người cùng lúc, SỐ VIỆC chồng giờ tại đúng đỉnh đó) — quét đường (sweep line).

    Tại cùng mốc, việc KẾT THÚC xử lý trước việc BẮT ĐẦU nên xếp nối tiếp (chạm mép) không bị cộng
    dồn. Đếm luôn số việc vì câu cảnh báo "đỉnh 5 người" một mình thì người xếp không biết 5 đó là
    MỘT bước khai 5 người hay năm việc chồng nhau — hai chuyện sửa khác hẳn nhau.
    """
    events: list[tuple[datetime, int, int]] = []
    for p_start, p_finish, so_nguoi in placements:
        events.append((p_start, int(so_nguoi), 1))
        events.append((p_finish, -int(so_nguoi), -1))
    events.sort(key=lambda e: (e[0], e[1]))
    dang_chay = dinh = viec_dang_chay = viec_tai_dinh = 0
    for _, delta, delta_viec in events:
        dang_chay += delta
        viec_dang_chay += delta_viec
        if dang_chay > dinh:
            dinh, viec_tai_dinh = dang_chay, viec_dang_chay
    return dinh, viec_tai_dinh


def dinh_dong_thoi(placements: list[tuple[datetime, datetime, int]]) -> int:
    """ĐỈNH số người cùng lúc của một loạt việc. Tách riêng để hai cửa cảnh báo
    (`vuot_quan_so_to`, `tai_to_cao`) đo cùng một số."""
    return dinh_dong_thoi_chi_tiet(placements)[0]


def lan_viec_ke(
    finish: datetime | None, finish_max: datetime | None,
    da_xep: list[tuple[datetime, datetime]],
) -> dict | None:
    """Chạy hết thời lượng TỐI ĐA sẽ lấn sang việc kế trên cùng máy ⇒ CẢNH BÁO (§7.3).

    Giờ CHUẨN (`finish`) đã qua cửa `trung_may` (không đè việc nào). Nhưng bước có DẢI thời lượng
    (min↔max): rơi vào nhánh chậm thì đuôi `finish_max` có thể chồm sang việc kế đã xếp. Chỉ nhắc,
    không chặn — chưa chắc chạy tới max, và người xếp có thể chủ động chừa đệm. Không có dải max
    (`finish_max <= finish`) thì không thể lấn thêm.
    """
    if finish is None or finish_max is None or finish_max <= finish:
        return None
    ke = min((o_start for o_start, _ in da_xep if o_start >= finish), default=None)
    if ke is None or finish_max <= ke:
        return None
    return issue(
        "lan_viec_ke", MUC_CANH_BAO,
        "Nếu chạy hết thời lượng tối đa, việc này lấn sang việc kế trên cùng máy.",
        nguon="may",
        goi_y="Chừa đệm hoặc dời việc kế để phòng bước chạy chậm.",
    )


def sap_bao_tri(
    finish: datetime | None, khoa: list[tuple[datetime, datetime]], *, nguong_ngay: int = 2,
) -> dict | None:
    """Máy có kỳ KHOÁ (bảo trì/hỏng/nghỉ) tới GẦN ngay sau khi việc xong ⇒ CẢNH BÁO (§7.3).

    `khoa` = list `(k_start, k_finish)` đã aware — cùng nguồn `de_vung_khoa_may` (luật báo khi ĐÈ
    lên). Ở đây việc KHÔNG đè, nhưng kỳ khoá tới sát đuôi việc: nhắc để người xếp biết máy sắp nghỉ,
    tránh dồn thêm việc vào sát đó. Chỉ soi kỳ khoá bắt đầu SAU khi việc xong.
    """
    if finish is None:
        return None
    nguong = finish + timedelta(days=nguong_ngay)
    ke = min((k_start for k_start, _ in khoa if k_start >= finish), default=None)
    if ke is None or ke > nguong:
        return None
    con_gio = (ke - finish).total_seconds() / 3600.0
    return issue(
        "sap_bao_tri", MUC_CANH_BAO,
        f"Máy sắp tới kỳ khoá/bảo trì, chỉ cách {con_gio:.0f} giờ sau khi việc xong.",
        nguon="may",
        goi_y="Cân nhắc dời việc hoặc chốt xong trước kỳ khoá.",
    )


def phut_ca_moi_ngay(ca: list[tuple[int, int, bool]]) -> int:
    """Tổng quỹ giờ (PHÚT) một ngày làm việc theo các ca đã khai — mẫu số để đo tải máy/ngày.

    Ca đêm (`qua_dem`, `ket_thuc <= bat_dau`) ôm nửa đêm nên độ dài = `(1440 - bat_dau) + ket_thuc`.
    Giả định các ca không chồng nhau (ca xưởng khai rời) nên cộng thẳng.
    """
    tong = 0
    for bat_dau, ket_thuc, qua_dem in ca:
        tong += (1440 - bat_dau + ket_thuc) if qua_dem else (ket_thuc - bat_dau)
    return tong


def tai_may_cao(
    phut_may_ngay: float, phut_ca_ngay: float, *,
    nguong_cao: float = 0.85, nguong_rat_cao: float = 1.0,
) -> dict | None:
    """Máy đã đặt gần KÍN quỹ giờ ca trong ngày ⇒ CẢNH BÁO CÓ MỨC (§7.3).

    `phut_may_ngay` = tổng phút máy bị chiếm trong ngày (gồm việc đang đặt); `phut_ca_ngay` = quỹ giờ
    ca/ngày. Máy chạy liên tục nên KHÔNG có trần cứng — đây chỉ là số để nhìn "máy này ken đặc", chia
    mức cao / rất cao (đã quá quỹ ca), không chỉ ném ra một con số thô.
    """
    if phut_ca_ngay <= 0 or phut_may_ngay <= 0:
        return None
    ty = phut_may_ngay / phut_ca_ngay
    if ty < nguong_cao:
        return None
    muc_chu = "rất cao" if ty >= nguong_rat_cao else "cao"
    return issue(
        "tai_may_cao", MUC_CANH_BAO,
        f"Máy tải {muc_chu}: đã đặt {int(round(phut_may_ngay))}/{int(round(phut_ca_ngay))} "
        "phút quỹ ca trong ngày.",
        nguon="may",
        goi_y="Giãn bớt việc trong ngày hoặc chuyển sang máy khác.",
    )


def vuot_quan_so_to(
    placements: list[tuple[datetime, datetime, int]], quan_so: int,
) -> dict | None:
    """ĐỈNH đồng thời của một tổ vượt quân số khả dụng ⇒ CẢNH BÁO (§4, §12.4).

    21/08/2026 hạ từ CHẶN xuống CẢNH BÁO theo yêu cầu chủ dự án: quân số khai trên routing là số
    ƯỚC (bước "Đóng gói + nhập kho" của LSX26-0020 khai 5 người trong khi tổ có 3), trong khi thực
    tế xưởng vẫn điều người qua lại giữa các tổ. Chặn cứng làm bước không tìm được khe nào trong cả
    60 ngày dò — máy nói "không xếp được" mà việc thì vẫn làm được. Vẫn nêu đúng con số để người xếp
    tự cân, KHÔNG giấu.
    """
    dinh, so_viec = dinh_dong_thoi_chi_tiet(placements)
    if dinh > quan_so:
        # MỘT việc ở đỉnh ⇒ con số đến thẳng từ ô "số người bố trí" của chính bước này; nói đúng
        # như vậy để người xếp biết mở đâu mà sửa, thay vì đoán xem "đỉnh 5" là mấy việc cộng lại.
        mo_ta = (
            f"Bước này bố trí {dinh} người, vượt quân số {quan_so} của tổ."
            if so_viec <= 1
            else f"Đỉnh {dinh} người cùng lúc ({so_viec} việc chồng giờ) vượt quân số "
                 f"{quan_so} của tổ."
        )
        return issue(
            "vuot_quan_so_to", MUC_CANH_BAO, mo_ta,
            nguon="to",
            goi_y=("Sửa số người bố trí ở bước, giãn giờ hoặc bổ sung người."
                   if so_viec <= 1 else "Giãn giờ các việc hoặc bổ sung người."),
        )
    return None


def tai_to_cao(
    dinh: int, quan_so: int, *, nguong_cao: float = 0.75, nguong_rat_cao: float = 0.9,
) -> dict | None:
    """Đỉnh quân số tổ CHƯA vượt (không chặn) nhưng đã chạm ngưỡng cao ⇒ CẢNH BÁO CÓ MỨC (§7.3).

    `dinh` = số người cùng lúc ở đỉnh (đã gồm việc đang đặt); `quan_so` = quân số khả dụng. Vượt hẳn
    thì `vuot_quan_so_to` lo — ở đây chỉ lo vùng "sắp kịch". Chia hai mức (cao / rất cao) để
    người xếp phân biệt "đông" với "gần hết người", không chỉ ném ra một con số thô.
    """
    if quan_so <= 0 or dinh <= 0 or dinh > quan_so:
        return None
    ty = dinh / quan_so
    if ty < nguong_cao:
        return None
    muc_chu = "rất cao" if ty >= nguong_rat_cao else "cao"
    return issue(
        "tai_to_cao", MUC_CANH_BAO,
        f"Tổ tải {muc_chu}: đỉnh {dinh}/{quan_so} người cùng lúc.",
        nguon="to",
        goi_y="Cân nhắc giãn việc hoặc bổ sung người để chừa dự phòng.",
    )


def sai_tien_nhiem(
    start: datetime, pred_finishes: list[datetime], *, dung_sai_phut: int = 1,
) -> dict | None:
    """Bước sau KHÔNG được bắt đầu trước khi mọi bước tiền nhiệm KẾT THÚC (§5, §7.1).

    `pred_finishes` = giờ kết thúc của các tiền nhiệm ĐÃ có giờ (tiền nhiệm chưa xếp thì chưa có mốc
    để so — không chặn ở đây). Nối đuôi (bắt đầu đúng lúc tiền nhiệm xong) KHÔNG tính là sai; chừa
    `dung_sai_phut` phút để tránh chặn oan vì lệch giây.
    """
    if start is None or not pred_finishes:
        return None
    muon_nhat = max(pred_finishes)
    if start < muon_nhat - timedelta(minutes=dung_sai_phut):
        return issue(
            "sai_tien_nhiem", MUC_CHAN_DAT_LICH,
            "Bắt đầu trước khi bước tiền nhiệm kết thúc.",
            nguon="tien_nhiem",
            goi_y="Dời giờ bắt đầu sang sau khi bước trước xong.",
        )
    return None


def thieu_ca_hai_han(han_sx: date | None, han_giao: date | None) -> dict | None:
    """Thiếu CẢ HAI hạn (hoàn thành SX lẫn giao khách) ⇒ chặn phát hành (§7.2).

    Có ít nhất một hạn là đủ để đo trễ; trống cả hai thì không có mốc nào để cam kết với xưởng.
    """
    if han_sx is None and han_giao is None:
        return issue(
            "thieu_ca_hai_han", MUC_CHAN_PHAT_HANH,
            "Lệnh chưa có hạn hoàn thành SX lẫn hạn giao khách.",
            nguon="han",
            goi_y="Khai ít nhất một hạn trước khi phát hành.",
        )
    return None


def tre_han_sx(
    finish: datetime | None, han_sx: date | None, han_giao: date | None = None,
) -> dict | None:
    """Kết thúc dự kiến TRỄ hơn hạn hoàn thành SX ⇒ chặn phát hành (§7.2, duyệt ngoại lệ được).

    Thiếu hạn SX thì đo theo HẠN GIAO KHÁCH (chưa khai hạn SX không có nghĩa muốn trễ giao) — mốc
    dùng để so là `han_sx` nếu có, không thì `han_giao`. Chưa có `finish` / thiếu cả hai hạn ⇒ không
    kết luận ở đây.
    """
    han = han_sx if han_sx is not None else han_giao
    if finish is None or han is None:
        return None
    if finish.date() > han:
        mo_ta = ("Kết thúc dự kiến trễ hơn hạn hoàn thành SX." if han_sx is not None
                 else "Kết thúc dự kiến trễ hơn hạn giao khách (chưa khai hạn SX).")
        return issue(
            "tre_han_sx", MUC_CHAN_PHAT_HANH, mo_ta,
            nguon="han",
            goi_y="Dời sớm hơn / đổi máy nhanh hơn, hoặc xin duyệt ngoại lệ.",
        )
    return None


def sat_han_sx(finish: datetime | None, han_sx: date | None, han_giao: date | None = None,
               *, nguong_ngay: int = 2) -> dict | None:
    """Đệm tới hạn hoàn thành SX quá mỏng (0..`nguong_ngay` ngày) ⇒ CẢNH BÁO, không chặn (§7.3).

    Thiếu hạn SX thì đo theo HẠN GIAO KHÁCH. Đã trễ (đệm âm) thì để `tre_han_sx` lo — không phát
    cảnh báo chồng lên.
    """
    han = han_sx if han_sx is not None else han_giao
    if finish is None or han is None:
        return None
    con = (han - finish.date()).days
    if 0 <= con <= nguong_ngay:
        nhan_han = "hạn hoàn thành SX" if han_sx is not None else "hạn giao khách"
        return issue(
            "sat_han_sx", MUC_CANH_BAO,
            f"Chỉ còn {con} ngày đệm tới {nhan_han}.",
            nguon="han",
            goi_y="Ưu tiên chạy sớm để phòng phát sinh.",
        )
    return None


def dem_giao_ngan(
    han_sx: date | None, han_giao: date | None, *, nguong_ngay: int = 1,
) -> dict | None:
    """Đệm giữa xong SX và giao khách quá ngắn (< `nguong_ngay` ngày) ⇒ CẢNH BÁO (§7.3)."""
    if han_sx is None or han_giao is None:
        return None
    dem = (han_giao - han_sx).days
    if dem < nguong_ngay:
        return issue(
            "dem_giao_ngan", MUC_CANH_BAO,
            f"Đệm giữa xong SX và giao khách chỉ {dem} ngày.",
            nguon="han",
            goi_y="Cân nhắc kéo hạn hoàn thành SX sớm hơn để kịp giao.",
        )
    return None


def truoc_ngay_vat_tu(
    start: datetime, ngay_ve: date | None, ca: list[tuple[int, int, bool]],
) -> dict | None:
    """Vật tư có NGÀY HỨA VỀ ⇒ không được bắt đầu trước ca đầu tiên của ngày đó (§5, §12.6).

    Chưa có ngày hứa ⇒ không chặn ở đây (thiếu vật tư chỉ chặn lúc phát hành, không cấm đặt nháp).
    """
    if ngay_ve is None:
        return None
    bat_dau_som_nhat = min((b for b, _, _ in ca), default=GIO_BAT_DAU * 60)
    nguong = datetime(
        ngay_ve.year, ngay_ve.month, ngay_ve.day, tzinfo=start.tzinfo,
    ) + timedelta(minutes=int(bat_dau_som_nhat))
    if start < nguong:
        return issue(
            "truoc_ngay_vat_tu", MUC_CHAN_DAT_LICH,
            "Bắt đầu trước ngày vật tư hứa về.",
            nguon="vat_tu",
            goi_y="Dời giờ bắt đầu sang ca đầu của ngày vật tư về.",
        )
    return None
