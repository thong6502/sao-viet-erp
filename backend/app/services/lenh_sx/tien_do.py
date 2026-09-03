"""Tầng TÍNH của Lệnh SX & Theo dõi SX (Task 7): tiến độ có trọng số · giờ máy · dự kiến xong · trễ hạn.

Bốn hàm ở đây trả lời đúng ba câu hỏi của điều độ: "lệnh này chạy tới đâu rồi", "bao giờ xong",
"có trễ không". Lỗi ở tầng này KHÔNG làm gãy gì — nó ra CON SỐ SAI mà trông vẫn hợp lý, nên mọi
lựa chọn dưới đây đều ghi rõ lý do.

ĐỌC TỪ `BoiCanh` (Task 6), KHÔNG truy vấn DB. Cả tầng này sinh ra để màn 200 lệnh không đẻ N+1:
nếu một hàm ở đây tự mở query thì công của `boi_canh.nap()` đổ sông. Thiếu dữ liệu thì bổ sung ở
`boi_canh.py`, không lén query tại đây.

--- Bốn luật của `phan_tram` ------------------------------------------------------------------
1. TRỌNG SỐ theo THỜI LƯỢNG kế hoạch (`du_kien_ket_thuc - du_kien_bat_dau` của công việc), KHÔNG
   theo số công đoạn. Lệnh có CTP 15' + In 360' mà xong CTP báo 50% là nói dối điều độ — đúng là
   15/375 ≈ 4%.
2. Công đoạn ĐANG CHẠY ăn phần theo SẢN LƯỢNG TỐT: `Σ batch.tot / so_luong_ra`, KẸP `[0, 1]`. Chạy
   dư (in bù hao) không được đẩy lệnh vượt 100%.
3. Thiếu thời lượng ⇒ CHIA ĐỀU và giương cờ `uoc_tinh=True` để UI nói rõ đây là số ước tính. Chỉ
   cần MỘT bước thiếu là cả lệnh chuyển sang chia đều: trộn nửa trọng-số-thật nửa trọng-số-bịa ra
   một con số không giải thích được cho ai.
4. Công việc `completed` tính 1.0 bất kể sản lượng ghi được bao nhiêu — tổ đã đóng bước thì bước
   xong, sổ sản lượng thiếu là việc của khâu khác.
5. Bước CHƯA xong mà `so_luong_ra` NULL/≤0 (không có mục tiêu để đo) cũng giương `uoc_tinh` — nó
   đóng góp 0% một cách im lặng, không có cờ thì không ai phân biệt được với "chưa ai làm". Bước
   đã `completed` KHÔNG tính vào luật này (xem `_khong_do_duoc`).

--- BƯỚC BỊ BÀI GHÉP PHỦ: đọc `cong_viec_du`, đừng đọc `cong_viec` -----------------------------
Bước gộp vào bài ghép KHÔNG đẻ công việc riêng — nó đẻ MỘT công việc CHUNG `lsx_id = None`. Đọc
`bc.cong_viec[lsx_id]` là mất đúng bước nặng nhất (ca in ghép), IM LẶNG. Ba hàm đọc công việc ở
đây (`phan_tram`, `gio_may`, `du_kien_xong`) đều đi qua `bc.cong_viec_du(lsx_id)`, và
`_duong_gang_phut` nối cạnh qua `bc.buoc_phu` (Task 6 mở rộng ở vòng sửa 1).

--- Đường găng của `du_kien_xong` -------------------------------------------------------------
Cạnh phụ thuộc TRONG một lệnh nằm ở `lsx_cong_doan_phu_thuoc` (`bc.phu_thuoc_buoc[lsx_id]`),
KHÔNG ở `san_xuat_phu_thuoc` — bảng kia chỉ chứa cạnh CHÉO GIỮA HAI LSX (snapshot bước ghép,
`models/san_xuat.py:251-255`; `services/san_xuat/snapshot.py` chỉ chụp cạnh chéo + cạnh toả vào
đó). Duyệt nhầm bảng thì đường găng LUÔN RỖNG, và im lặng.

Cạnh đọc được là cặp `lsx_cong_doan.id`; nối về công việc qua `SanXuatCongViec.lsx_cong_doan_id`
(soft-ref Integer, NULLABLE) VÀ qua `bc.buoc_phu` cho bước bị bài ghép phủ. Đầu nào không nối được
thì BỎ cạnh, không đoán.

Mỗi bước còn có SÀN thời điểm bắt đầu = `max(bay_gio, du_kien_bat_dau)`. Không có sàn thì lệnh
xếp lịch cho tuần sau vẫn báo xong theo giờ hôm nay — sai LUÔN về phía lạc quan, đúng bằng
`du_kien_bat_dau − bay_gio`, và `tre_han` bỏ sót y hệt.

KHÔNG dựng thêm bảng snapshot cho routing: từ `da_lap_ke_hoach` trở đi routing bị khoá
(`models/lsx.py:47-48`) nên cạnh live đã đóng băng trên thực tế.

GIỚI HẠN CÓ Ý THỨC: `du_kien_xong` chỉ tính đường găng TRONG MỘT LỆNH. Lệnh phải chờ bước ghép
của lệnh khác (cạnh chéo `san_xuat_phu_thuoc`) sẽ báo xong SỚM HƠN thực tế. Đã ghi nhận, cố tình
để ngoài phạm vi task này.

--- Hai bẫy kiểu dữ liệu (đều là bẫy tái phát của repo) ---------------------------------------
`Decimal`: `batch.tot`, `cong_viec.so_luong_ra/so_luong_vao` là `Numeric` ⇒ SQLAlchemy trả
`Decimal`; `Decimal / float` nổ TypeError. Ép `float()` ngay tại chỗ ĐỌC.

NAIVE/AWARE: các cột `DateTime(timezone=True)` bị SQLite trả về NAIVE trong khi mốc máy chủ là
AWARE ⇒ trừ thẳng nổ TypeError. Mọi phép tính thời gian ở đây đi qua `_aware()`. ÉP LÊN aware,
tuyệt đối KHÔNG hạ `bay_gio` xuống naive cho hết lỗi: test SQLite sẽ xanh còn Postgres (trả
AWARE) thì lỗi quay lại, lần này im lặng hoặc sai giờ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...models.san_xuat import CV_HOAN_THANH, SanXuatCongViec
from .boi_canh import BoiCanh

# Giờ xưởng (+7). Hạn SX là kiểu `Date` nên "trễ hay không" phải quy về NGÀY THEO GIỜ XƯỞNG:
# ca đêm 2h sáng giờ VN vẫn là ngày HÔM TRƯỚC theo UTC, mà xưởng này CÓ chạy ca đêm. Khai tại chỗ
# đúng khuôn `services/sequence_service.py:45` và `services/ky_thuat_may_service.py:130`.
BUSINESS_TZ = timezone(timedelta(hours=7))

class _TuTinh:
    """Sentinel "bên gọi chưa tính `du_kien_xong`" — KHÔNG dùng `None` được, vì `None` là một kết
    quả HỢP LỆ của `du_kien_xong` ("chưa đủ dữ liệu") mà bên gọi có quyền truyền lại.

    Khai thành LỚP riêng thay vì `object()`: annotation `datetime | None | object` bị `object` nuốt
    trọn (mọi thứ đều là `object`) nên nó không nói được gì cho người đọc lẫn cho type checker.
    """


_TU_TINH = _TuTinh()


def _aware(dt: datetime) -> datetime:
    """SQLite trả datetime NAIVE — ép về aware UTC trước khi so/trừ với mốc máy chủ (bẫy
    naive/aware từng làm 500 ở xếp lịch). Bản gốc: `services/san_xuat/thuc_thi.py:493`; khai lại
    cục bộ ở đây thay vì import tên `_`-riêng tư của module khác (thói quen sẵn có của repo)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _thoi_luong_phut(cv: SanXuatCongViec) -> float | None:
    """Thời lượng KẾ HOẠCH của một công việc, phút. None = chưa xếp lịch / khoảng không hợp lệ.

    Khoảng ≤ 0 coi như KHÔNG có thời lượng: nó không thể làm trọng số (chia cho 0) và cũng không
    nói được gì về công sức của bước.
    """
    if cv.du_kien_bat_dau is None or cv.du_kien_ket_thuc is None:
        return None
    phut = (_aware(cv.du_kien_ket_thuc) - _aware(cv.du_kien_bat_dau)).total_seconds() / 60.0
    return phut if phut > 0 else None


def _phan_hoan_thanh(bc: BoiCanh, cv: SanXuatCongViec) -> float:
    """Phần đã xong của MỘT công việc, trong `[0, 1]`.

    `completed` ⇒ 1.0. Ngược lại `Σ batch.tot / so_luong_ra` (cả hai là `Numeric` ⇒ ép `float`).
    `so_luong_ra` NULL hoặc ≤ 0 ⇒ 0.0: không có mục tiêu thì không có tỷ lệ để nói, và 0 là con số
    KHÔNG khoe khoang (báo thấp hơn thực tế còn chấp nhận được, báo cao hơn thì điều độ ra quyết
    định sai).
    """
    if cv.trang_thai == CV_HOAN_THANH:
        return 1.0
    muc_tieu = float(cv.so_luong_ra) if cv.so_luong_ra is not None else 0.0
    if muc_tieu <= 0:
        return 0.0
    tot = sum(float(b.tot) for b in bc.batch[cv.id])
    return min(1.0, max(0.0, tot / muc_tieu))


def _khong_do_duoc(cv: SanXuatCongViec) -> bool:
    """Bước CHƯA xong mà không có mục tiêu để đo tiến độ (`so_luong_ra` NULL hoặc ≤ 0).

    Bước đã `completed` KHÔNG tính: nó bằng 1.0 theo luật 4, mục tiêu sản lượng hết ý nghĩa — giương
    cờ ở đó thì mọi lệnh ĐÃ XONG đều đeo cờ ước tính và cờ mất nghĩa (tinh chỉnh của reviewer cho
    phán quyết C34, chủ dự án chốt theo).
    """
    if cv.trang_thai == CV_HOAN_THANH:
        return False
    return cv.so_luong_ra is None or float(cv.so_luong_ra) <= 0


def phan_tram(bc: BoiCanh, lsx_id: int) -> tuple[float, bool]:
    """Tiến độ của một lệnh: `(phần trăm 0..100, uoc_tinh)`.

    `uoc_tinh=True` = con số này KHÔNG chắc chắn, UI phải nói rõ. HAI nguồn dựng cờ, đừng lẫn:

      · THIẾU THỜI LƯỢNG ⇒ trọng số chia đều (và cờ bật). Đây là nguồn duy nhất đổi CÁCH TÍNH.
      · KHÔNG ĐO ĐƯỢC (bước chưa xong, `so_luong_ra` NULL/≤0) ⇒ chỉ bật cờ, trọng số giữ nguyên.
        `so_luong_ra` là cột NOT NULL `default=0` (`models/lsx.py:221`, snapshot chép sang) nên ca
        "bằng 0" là ca THƯỜNG chứ không phải dữ liệu hỏng. Không có cờ thì bước đó im lặng đóng
        góp 0% và không ai phân biệt được với "chưa ai làm".

    CỜ NÀY BẬT NHIỀU LÀ ĐÚNG, KHÔNG PHẢI NHIỄU. Bước CHẾ BẢN thường không đo được: nó không khai
    `don_vi_vao/ra`, mà `LsxService.buoc_ngoai_dong` (`lsx_service.py:1733`) chặn ngay ở
    `if not don_vi_ra: return None` — TRƯỚC khi đọc `cong_thuc_san_luong` — nên `_ap_chuoi_nguoc`
    bỏ qua bước đó và `so_luong_ra` nằm lại ở 0. Trong danh mục PROD, cả ba bước chế bản
    (`CD-1001` Phơi kẽm PS · `CD-1002` Bình bài điện tử · `CD-1003` Xuất film) đều như vậy. Nghĩa
    là phần lớn lệnh sẽ đeo cờ `uoc_tinh` ở GIAI ĐOẠN ĐẦU — và đúng lúc đó con số phần trăm thật
    sự mềm. Nhờ luật "chỉ tính bước CHƯA `completed`", cờ TỰ TẮT ngay khi chế bản đóng: nó bật
    đúng cửa sổ số liệu mềm rồi tắt, chứ không phải bật vĩnh viễn.

    Lệnh chưa có công việc nào trả `(0.0, True)`: chưa phát hành thì chưa biết gì, không phải "0%
    chắc chắn".

    Đọc `cong_viec_du` chứ KHÔNG phải `cong_viec`: lệnh mà mọi bước đều bị bài ghép phủ có
    `cong_viec[lsx_id]` RỖNG, và trả 0% cho nó là nói dối một cách tự tin.
    """
    cvs = bc.cong_viec_du(lsx_id)
    if not cvs:
        return 0.0, True

    thoi_luong = [_thoi_luong_phut(cv) for cv in cvs]
    thieu_thoi_luong = any(tl is None for tl in thoi_luong)
    uoc_tinh = thieu_thoi_luong or any(_khong_do_duoc(cv) for cv in cvs)
    # Chia đều TOÀN BỘ khi thiếu, không chỉ bước thiếu: trộn nửa trọng-số-thật nửa trọng-số-bịa ra
    # một con số không giải thích được cho ai.
    trong_so = [1.0] * len(cvs) if thieu_thoi_luong else [float(tl) for tl in thoi_luong]

    # `tong_ts` luôn > 0: nhánh chia đều cho `len(cvs) ≥ 1`, nhánh thời lượng thì mọi phần tử > 0
    # (`_thoi_luong_phut` trả None cho khoảng ≤ 0, mà None đã đẩy sang nhánh chia đều).
    tong_ts = sum(trong_so)
    diem = sum(w * _phan_hoan_thanh(bc, cv) for w, cv in zip(trong_so, cvs))
    return 100.0 * diem / tong_ts, uoc_tinh


def gio_may(bc: BoiCanh, lsx_id: int, bay_gio: datetime | None = None) -> float:
    """Tổng GIỜ CHẠY THỰC TẾ của lệnh, đã loại trừ thời gian dừng.

    Không cần trừ khoảng dừng lần nữa: phiên tạm dừng là phiên ĐÃ ĐÓNG (`ket_thuc` +
    `loai_dong='tam_dung'`), nên cộng thời lượng TỪNG PHIÊN đã tự bỏ mọi khoảng giữa hai phiên.
    Trừ thêm một lần nữa là ra thiếu giờ.

    Phiên còn mở (`ket_thuc IS NULL`) đếm tới `bay_gio`; bỏ trống thì lấy mốc máy chủ — tham số có
    mặt để bài test chốt được con số, phần còn lại của hệ gọi 2 tham số như brief.

    HỆ QUẢ PHẢI BIẾT (phán quyết C36): phiên của BƯỚC GHÉP được đếm ĐỦ cho MỌI lệnh mà bước đó
    phục vụ, KHÔNG chia phần. Đúng cho câu hỏi "lệnh này đã ngốn bao nhiêu giờ máy" (một lượt in
    ghép 3 lệnh thì cả 3 lệnh đều thật sự chờ trọn lượt đó), nhưng nghĩa là **cộng `gio_may` của
    nhiều lệnh sẽ VƯỢT giờ máy thật của xưởng**. Cần tổng giờ máy không trùng lặp thì đọc màn Bài
    ghép, đừng cộng hàm này qua các lệnh.
    """
    moc = _aware(bay_gio) if bay_gio is not None else datetime.now(timezone.utc)
    tong_giay = 0.0
    for cv in bc.cong_viec_du(lsx_id):
        for p in bc.phien[cv.id]:
            bat_dau = _aware(p.bat_dau)
            ket_thuc = _aware(p.ket_thuc) if p.ket_thuc is not None else moc
            giay = (ket_thuc - bat_dau).total_seconds()
            if giay > 0:  # mốc lệch ngược (dữ liệu hỏng) không được ăn bớt giờ của phiên khác
                tong_giay += giay
    return tong_giay / 3600.0


def _duong_gang_phut(
    bc: BoiCanh,
    lsx_id: int,
    cvs: list[SanXuatCongViec],
    con_lai: dict[int, float],
    san: dict[int, float],
) -> float:
    """Số phút TỪ `bay_gio` tới lúc lệnh xong, theo ĐƯỜNG GĂNG của đồ thị phụ thuộc trong lệnh.

    `cvs` là danh sách công việc đã gồm cả bước ghép (`cong_viec_du`); `con_lai` và `san` khoá theo
    `san_xuat_cong_viec.id`. `san[n]` = SÀN thời điểm bắt đầu của n, đo bằng phút từ `bay_gio` —
    bằng 0 khi mốc kế hoạch đã qua hoặc chưa khai. Không có sàn thì lệnh xếp lịch cho TUẦN SAU vẫn
    báo xong theo giờ hôm nay: sai luôn về phía LẠC QUAN, đúng bằng `du_kien_bat_dau − bay_gio`.

    Nhánh CHẠY THẬT là Kahn: `LsxService.tao` sinh sẵn chuỗi cạnh ĐẦY ĐỦ (`lsx_service.py:1526-1528`
    nối `thu_tu` liền kề), nên lệnh bình thường luôn có cạnh. Nhánh `_tuan_tu` là lối thoát cho hai
    ca BẤT THƯỜNG: kế hoạch đã gỡ hết cạnh, hoặc mọi cạnh đều không nối được về công việc (bước bị
    bài ghép phủ làm cạnh tự-nối, dữ liệu routing hỏng). Cả hai nhánh trả cùng một hệ quy chiếu
    "phút từ `bay_gio`".
    """
    cv_theo_buoc = {
        cv.lsx_cong_doan_id: cv.id for cv in cvs if cv.lsx_cong_doan_id is not None
    }
    # Bước bị BÀI GHÉP phủ không có công việc riêng — nó trỏ về công việc CHUNG. Thiếu vòng này thì
    # mọi cạnh chạm bước ghép bị bỏ, chuỗi tuần tự vỡ thành nhánh song song và `max` thay cho `sum`
    # (reviewer đo: 570' thật → báo 210', hụt 63%).
    for cv in cvs:
        for cd_id in bc.buoc_phu.get(cv.id, ()):
            cv_theo_buoc[cd_id] = cv.id

    def _tuan_tu() -> float:
        """Gộp TUẦN TỰ theo SÀN TĂNG DẦN: `t = max(t, san[n]) + con_lai[n]`.

        Cộng dồn từ `min(san)` (bản cũ) luôn ra số NHỎ HƠN HOẶC BẰNG sự thật: hai bước không cạnh,
        A 60' xếp bây giờ và B 30' xếp 7 ngày nữa, cho `0 + 90` thay vì `10080 + 30` — hụt trọn 7
        ngày, và hụt về phía LẠC QUAN, đúng thứ SÀN sinh ra để diệt.

        Duyệt theo sàn tăng dần chứ KHÔNG theo thứ tự `con_lai`: nhánh này chạy đúng lúc không có
        cạnh nào dùng được, nên không suy ra được đâu là đầu chuỗi; mà `con_lai` sinh từ truy vấn
        không `ORDER BY` — SQLite và Postgres có quyền trả khác thứ tự.
        """
        t = 0.0
        for i in sorted(con_lai, key=lambda k: san.get(k, 0.0)):
            t = max(t, san.get(i, 0.0)) + con_lai[i]
        return t

    canh: set[tuple[int, int]] = set()
    for buoc_truoc, buoc_sau in bc.phu_thuoc_buoc[lsx_id]:
        u = cv_theo_buoc.get(buoc_truoc)
        v = cv_theo_buoc.get(buoc_sau)
        # Bỏ cạnh không nối được về công việc, và cạnh TỰ NỐI CHÍNH MÌNH — xảy ra khi một công việc
        # ghép phủ hai bước liền nhau của cùng lệnh.
        if u is None or v is None or u == v or u not in con_lai or v not in con_lai:
            continue
        canh.add((u, v))
    if not canh:
        return _tuan_tu()

    ke: dict[int, list[int]] = {}
    bac_vao: dict[int, int] = {i: 0 for i in con_lai}
    for u, v in canh:
        ke.setdefault(u, []).append(v)
        bac_vao[v] += 1

    # Kahn + longest path: `xong[n]` = mốc kết thúc sớm nhất của n, tính bằng phút từ `bay_gio`.
    xong: dict[int, float] = {i: 0.0 for i in con_lai}
    hang_doi = [i for i, bac in bac_vao.items() if bac == 0]
    da_tham = 0
    while hang_doi:
        u = hang_doi.pop()
        da_tham += 1
        # Bước không bắt đầu trước SÀN của nó, kể cả khi mọi tiền nhiệm đã xong sớm.
        xong[u] = max(xong[u], san.get(u, 0.0)) + con_lai[u]
        for v in ke.get(u, []):
            xong[v] = max(xong[v], xong[u])
            bac_vao[v] -= 1
            if bac_vao[v] == 0:
                hang_doi.append(v)
    if da_tham != len(con_lai):
        # Chu trình (dữ liệu routing hỏng) — trả về ước lượng TUẦN TỰ. Bi quan hơn sự thật còn hơn
        # trả một con số cụt vì bỏ sót nguyên cụm bước nằm trong vòng.
        return _tuan_tu()
    return max(xong.values(), default=0.0)


def _moc_da_xong(bc: BoiCanh, cvs: list) -> datetime | None:
    """Mốc hoàn thành của lệnh ĐÃ ĐÓNG HẾT BƯỚC — thang BA BẬC, không bao giờ lùi về `bay_gio`.

    1. `max(phien.ket_thuc)` của mọi phiên ĐÃ ĐÓNG — sự thật ghi được từ xưởng;
    2. không có phiên đóng nào ⇒ `max(cv.du_kien_ket_thuc)` — mốc kế hoạch, còn hơn không;
    3. cả hai đều không có ⇒ `None` ("chưa đủ dữ liệu").

    CHỈ gọi khi MỌI công việc `completed` — cửa nằm ở `du_kien_xong`, và cửa đó là phần load-bearing
    nhất của hàm này (xem chú thích tại chỗ: cửa `con_lai == 0` đã đẻ ra một regression thật).
    Bậc 1 nhặt phiên của MỌI bước, nên nếu lọt vào đây khi còn một bước đang chạy phiên MỞ, nó sẽ
    trả mốc của bước TRƯỚC — một con số quá khứ trông rất hợp lý.

    VÌ SAO KHÔNG TRẢ `bay_gio` (lỗi thật của bản Task 7, sửa ở Vòng sửa 1): đường găng của lệnh đã
    xong ra 0 phút, `du_kien_xong` = đúng `bay_gio`, và `bay_gio` thì LUÔN muộn hơn một hạn đã qua
    ⇒ `tre_han` bật VĨNH VIỄN cho mọi lệnh đã xong có hạn trong quá khứ, kể cả lệnh về ĐÚNG HẠN từ
    tháng trước. Cứ mỗi ngày trôi qua, mốc "dự kiến xong" của một lệnh đã đóng lại trượt thêm một
    ngày — con số không những sai, nó còn không đứng yên.
    """
    dong = [_aware(p.ket_thuc) for cv in cvs for p in bc.phien[cv.id] if p.ket_thuc is not None]
    if dong:
        return max(dong)
    kh = [_aware(cv.du_kien_ket_thuc) for cv in cvs if cv.du_kien_ket_thuc is not None]
    if kh:
        return max(kh)
    return None


def du_kien_xong(bc: BoiCanh, lsx_id: int, bay_gio: datetime) -> datetime | None:
    """Mốc dự kiến hoàn thành lệnh. `None` = CHƯA ĐỦ DỮ LIỆU (UI hiện "Chưa đủ dữ liệu").

    Phần còn lại của mỗi công việc = `thời lượng × (1 - phần đã xong)`; `completed` ⇒ 0. Chỉ cần
    MỘT công việc chưa xong mà thiếu thời lượng là trả `None` — thà im còn hơn bịa ra một mốc giờ
    mà điều độ sẽ hứa với khách.

    TÔN TRỌNG MỐC BẮT ĐẦU KẾ HOẠCH: mỗi bước có SÀN = `max(bay_gio, du_kien_bat_dau)`. Cộng thẳng
    từ `bay_gio` là coi mọi lệnh như đang bắt đầu ngay bây giờ ⇒ lệnh xếp cho tuần sau báo xong
    theo giờ hôm nay, và `tre_han` bỏ sót đúng bằng `du_kien_bat_dau − bay_gio`.

    LỆNH ĐÃ ĐÓNG HẾT BƯỚC đi đường riêng (`_moc_da_xong`): mốc xong của nó là quá khứ đã ghi được,
    KHÔNG phải `bay_gio` — lỗi thật của bản đầu, sửa ở Vòng sửa 1. Cửa vào đường đó là `trang_thai`
    của mọi công việc, KHÔNG phải `con_lai`: xem chú thích ngay tại cửa, đó là chỗ Vòng sửa 1 đặt
    sai và làm mất cờ `tre_han` của lệnh còn trên máy.

    Giới hạn: chỉ đường găng TRONG một lệnh; lệnh chờ bước ghép của lệnh khác — cạnh CHÉO ở
    `san_xuat_phu_thuoc` — sẽ báo xong sớm hơn thực tế (xem docstring module). Đây là chuyện KHÁC
    với bước ghép phủ bước của chính lệnh này: cái đó đã được `cong_viec_du` + `buoc_phu` nối lại.
    """
    cvs = bc.cong_viec_du(lsx_id)
    if not cvs:
        return None

    # CỬA VÀO THANG là "MỌI bước đã `completed`", KHÔNG phải "mọi `con_lai` = 0" (Vòng sửa 2 —
    # regression của chính Vòng sửa 1). `_phan_hoan_thanh` kẹp `min(1.0, …)`, nên một bước ĐANG
    # CHẠY đã ghi đủ (hoặc dư) sản lượng cũng cho `con_lai = 0`. Lấy `con_lai` làm cửa thì ca
    # "thợ ghi hết sản lượng rồi QUÊN bấm Kết thúc" rơi vào thang: phiên của bước đó còn MỞ nên
    # bậc 1 nhặt mốc của BƯỚC TRƯỚC, `du_kien_xong` lùi về quá khứ, và một lệnh trễ hai ngày CÒN
    # TRÊN MÁY mất cờ `tre_han` — biến khỏi tab Cảnh báo đúng lúc điều độ cần nhìn nhất.
    if all(cv.trang_thai == CV_HOAN_THANH for cv in cvs):
        return _moc_da_xong(bc, cvs)

    moc = _aware(bay_gio)
    con_lai: dict[int, float] = {}
    san: dict[int, float] = {}
    for cv in cvs:
        if cv.trang_thai == CV_HOAN_THANH:
            # Bước ĐÃ XONG không có sàn: nó không còn chờ mốc kế hoạch nào nữa. Để nguyên sàn
            # tương lai ở đây là một bước đã hoàn thành lại đẩy lùi các bước sau nó.
            san[cv.id] = 0.0
            con_lai[cv.id] = 0.0
            continue
        san[cv.id] = (
            max(0.0, (_aware(cv.du_kien_bat_dau) - moc).total_seconds() / 60.0)
            if cv.du_kien_bat_dau is not None else 0.0
        )
        thoi_luong = _thoi_luong_phut(cv)
        if thoi_luong is None:
            return None
        con_lai[cv.id] = thoi_luong * (1.0 - _phan_hoan_thanh(bc, cv))

    # Còn bước CHƯA đóng ⇒ đi đường găng, kể cả khi mọi `con_lai` đã bằng 0 (ca "ghi đủ sản lượng
    # nhưng chưa bấm Kết thúc"): kết quả khi đó là `bay_gio`, tức "đáng lẽ xong rồi" — đúng thứ
    # điều độ cần thấy, và `tre_han` vẫn bật nếu hạn đã qua.
    return moc + timedelta(minutes=_duong_gang_phut(bc, lsx_id, cvs, con_lai, san))


def tre_han(
    bc: BoiCanh, lsx_id: int, bay_gio: datetime, *,
    xong: datetime | None | _TuTinh = _TU_TINH,
) -> bool:
    """Lệnh có nguy cơ trễ HẠN SX hay không.

    `xong` (KEYWORD-ONLY, để không ai lỡ truyền nhầm vào vị trí của `bay_gio`) = kết quả
    `du_kien_xong` mà bên gọi ĐÃ tính. Bỏ trống thì hàm tự tính — tiện cho lời gọi lẻ, nhưng màn
    danh sách 200 lệnh phải TRUYỀN VÀO: cả hai hàm đều duyệt đường găng, để mặc thì trang đó chạy
    400 lượt duyệt thay vì 200. Truyền `None` là hợp lệ và có nghĩa "đã tính, không đủ dữ liệu" —
    nên mặc định phải là sentinel riêng chứ không thể là `None`.

    Mốc so là `han_hoan_thanh_sx` (hạn nội bộ của kế hoạch), KHÔNG phải `han_giao_khach` — trễ
    khâu sản xuất và trễ giao hàng là hai chuyện khác nhau. Hạn NULL ⇒ `False`: không có hạn thì
    không thể trễ. Không suy được mốc xong ⇒ `False`: không kết luận trên dữ liệu thiếu.

    Hạn là kiểu `Date` (`models/lsx.py:120`) nên so bằng NGÀY THEO GIỜ XƯỞNG. `.date()` của mốc
    UTC là sai: ca đêm 2h sáng giờ VN vẫn nằm ở ngày hôm trước theo UTC.
    """
    han = bc.lenh[lsx_id].han_hoan_thanh_sx
    if han is None:
        return False
    if xong is _TU_TINH:
        xong = du_kien_xong(bc, lsx_id, bay_gio)
    if xong is None:
        return False
    return xong.astimezone(BUSINESS_TZ).date() > han
