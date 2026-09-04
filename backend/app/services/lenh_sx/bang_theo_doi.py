"""Bảng Kanban của màn "Theo dõi sản xuất" (Task 15) — cửa HTTP đầu tiên của cả bốn góc nhìn
(Kanban · Theo máy · Theo ca · Gantt); ba góc sau là task riêng, dùng lại đúng `boi_canh.nap()`.

--- RULING C113 (điều phối, 2026-08-31) — TRỤC CỘT LÀ DANH MỤC CÔNG ĐOẠN --------------------------
Cột Kanban = bảng danh mục `cong_doan`. `key` của cột = `str(cong_doan.id)`, nhãn ưu tiên
`ten_hien_thi` (Vòng sửa 1 mục G bên dưới — bản đầu dùng thẳng `cong_doan.ten`, đã sửa)
(tiếng Việt CÓ DẤU — khoá là chuyện của máy, id/mã không được lọt ra chỗ hiện chữ cho người dùng).

KHÔNG dùng `SanXuatCongViec.nhom_cong_doan`: cột đó chỉ mang bốn mã HẰNG TRONG CODE
(`prepress|print|finishing|other`, `models/cong_doan.py:25`), xưởng không thêm được phần tử lúc
chạy — trục "cột lấy ĐỘNG từ danh mục" chỉ đứng vững trên `cong_doan`.

Đường nối card → cột (đã có sẵn, KHÔNG thêm cột DB nào):

    SanXuatCongViec.step_key → LsxCongDoan.step_key (unique) → LsxCongDoan.cong_doan_id → cong_doan.id

`cong_doan_id` là SOFT-REF (không FK, `models/lsx.py:192`) — bước không tra được về danh mục (chưa
khai, hoặc trỏ vào một dòng đã bị xoá khỏi danh mục) rơi vào cột `COT_KHAC` tường minh, KHÔNG biến
mất khỏi board và KHÔNG bịa ra một cột mang tên bước.

--- MỘT LSX ĐÚNG MỘT CARD -------------------------------------------------------------------------
Routing song song (hai nhánh không phụ thuộc nhau, cùng chạy) KHÔNG được đẻ hai card: card đại diện
CẢ lệnh, cột của nó là cột của "bước chân sớm nhất" còn dang dở (bước có `thu_tu` nhỏ nhất trong số
những bước CHƯA `completed`), còn danh sách `chip_dang_chay` liệt kê ĐỦ mọi công việc đang
`running`/`paused` — đếm 1 khi có 2 là bỏ sót đúng nhánh nặng nhất của lệnh.

Lệnh đã xong HẾT các bước vẫn cần một cột để không biến mất khỏi board: dùng bước CUỐI (thu_tu lớn
nhất), không phải bước đầu — "đã ra khỏi cột nào rồi" không phải câu Kanban trả lời được, board chỉ
biết dừng ở đâu.

--- VÒNG SỬA 1, MỤC A (điều phối, 2026-09-03) — BƯỚC ĐẠI DIỆN THEO ĐỘ SÂU ĐỒ THỊ, KHÔNG THEO `thu_tu`
Bản đầu dùng `thu_tu` làm thước đo "sớm/muộn": SAI. `thu_tu` chỉ là VỊ TRÍ trong payload client gửi
lên lúc lưu routing (`lsx_service.py:2775-3002` gán `thu_tu=i` theo đúng thứ tự liệt kê), hoàn toàn
tách rời khỏi cạnh phụ thuộc thật — server KHÔNG ép `thu_tu` đơn điệu theo độ sâu.

Phản ví dụ (canh bởi `lenh_nhanh_lech_do_sau`): routing `CTP(thu_tu=0)→In(1)→Bế(2)` và
`CTP(0)→Cán(3)` (Cán rẽ song song từ CTP). CTP + In xong, Bế và Cán đều còn `released`. Đại diện
ĐÚNG là **Cán** (độ sâu 1 — sẵn sàng chạy từ lúc CTP xong, cùng lúc với In, mà chưa ai đụng), KHÔNG
phải **Bế** (độ sâu 2, chỉ vừa mở khoá sau khi In xong) — dù `thu_tu` của Bế NHỎ hơn. Rủi ro áp cho
MỌI routing có một nhánh song song bị LIỆT KÊ SAU trong danh sách — không cần "DAG rẽ nhánh sâu"
mới dính, một nhánh rẽ nông cũng đủ sai.

Độ sâu = đường DÀI NHẤT từ gốc, suy từ cạnh có sẵn `bc.phu_thuoc_buoc[lsx_id]`
(`boi_canh.py:515-525`, câu 13 của `nap()`) — xem `_do_sau_tat_ca`, KHÔNG thêm câu SQL nào. `thu_tu`
hạ xuống làm nấc SO SÁNH PHỤ (hai bước cùng độ sâu vẫn có thứ tự ổn định, đúng thứ tự cột trên
phiếu công nghệ), `cv.id` làm nấc cuối.

Hai cái bẫy PHẢI xử (xem docstring `_do_sau_tat_ca`): cạnh trỏ sang một bước thuộc LỆNH KHÁC (hợp
lệ trong nghiệp vụ — Ruột phụ thuộc Bìa cùng đơn hàng), và chu trình (dữ liệu hỏng, DB không cấm dù
đường ghi thật có chặn) — cả hai không được làm nổ `KeyError` hay đệ quy vô tận.

`RoutingNodeOut.lop` (`schemas/lenh_san_xuat.py`) tính đúng con số này nhưng cho MỘT lệnh tại một
thời điểm (phiếu công nghệ); ở đây cần cho CẢ LÔ mỗi lần tải Kanban nên viết lại thuật toán riêng
trên đúng cạnh mà `boi_canh` đã nạp, không gọi lại hàm đó (nó tự đi truy vấn routing của MỘT lsx).

--- VÒNG SỬA 1, MỤC B (điều phối, 2026-09-03) — CHỈ BÀY CÔNG ĐOẠN CÒN DÙNG ---------------------------
`CongDoan.active` có thật (`models/cong_doan.py:157`, `server_default=true()`) — XOÁ một công đoạn ở
giao diện Danh mục Công đoạn là LẬT `active=False` (`PATCH /api/cong-doan/{id}/active`,
`routers/catalog_base.py:342-367`), dòng vẫn NẰM LẠI trong bảng. `meta()` và `cd_con_song` (bộ lọc
soft-ref trỏ hụt ở `_the`, xem đoạn "SOFT-REF" của Ruling C113) PHẢI lọc CÙNG MỘT vị ngữ — dùng
chung hằng `_DANG_DUNG` — lệch nhau ở đây là đẻ ra card mang `cot` không tồn tại trong
`meta()["cot"]`, vì `cd_con_song` quyết định card rơi cột nào còn `meta()` là thứ dựng khung cột.
Card đang trỏ vào công đoạn đã ngừng dùng thì rơi về `COT_KHAC` — đúng, không phải lỗi.

--- VÒNG SỬA 1, MỤC G (điều phối, 2026-09-03) — NHÃN CỘT ƯU TIÊN `ten_hien_thi` ----------------------
Bản đầu dùng thẳng `cong_doan.ten`. Sửa: **`ten_hien_thi` nếu đã khai, không thì `ten`** — đúng
khuôn `services/thanh_phan_engine.py:421-424` (`_ten_buoc`) và đúng định nghĩa cột
(`models/cong_doan.py:62`, "tên in cho thợ sản xuất"). Kanban là bàn theo dõi XƯỞNG, phải gọi bước
bằng đúng cái tên tổ sản xuất quen nghe. Vẫn giữ luật cũ: nhãn là tiếng Việt CÓ DẤU, cấm `id`/`ma`
lọt ra chỗ hiện chữ.

--- KHÔNG N+1: batch đúng MỘT câu SQL routing + MỘT câu danh mục, cộng với `boi_canh.nap()` --------
`boi_canh.nap()` đã lo 21 câu cho cả lô. Task này cần thêm ít dữ liệu nó KHÔNG nạp (`thu_tu` +
`cong_doan_id` của từng bước routing) — nạp bằng MỘT câu `LsxCongDoan.lsx_id IN ids`, không lặp
theo lsx. Danh mục `cong_doan` (cho `meta()` VÀ để lọc soft-ref trỏ hụt ở `kanban()`) đọc trọn bảng
một lần — danh mục công đoạn của một xưởng in offset nằm ở hàng chục dòng, không phải hàng nghìn.
Tính độ sâu (`_do_sau_tat_ca`) chạy THUẦN TRONG PYTHON trên cạnh đã nạp sẵn, không đụng DB câu nào —
số câu SQL của `kanban()` không đổi theo vòng sửa này (khoá bởi `test_khong_n_plus_1`).

--- KHÔNG MỘT SỐ TIỀN NÀO ---------------------------------------------------------------------------
Cùng ràng buộc của cả gói `services/lenh_sx/`: không `don_gia`/`gia_von`/`thanh_tien`/`luong_khoan`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ...models.attendance import WorkShift
from ...models.bai_ghep_cong_doan import BaiGhepCongDoanMap
from ...models.cong_doan import NHOM as NHOM_CONG_DOAN, CongDoan
from ...models.customer import Customer
from ...models.employee import Employee
from ...models.lsx import Lsx, LsxCongDoan
from ...models.may_thiet_bi import MayThietBi
from ...models.order import Order
from ...models.san_xuat import (
    CV_DANG_CHAY, CV_HOAN_THANH, CV_PHAT_HANH, CV_TAM_DUNG, SanXuatCongViec,
)
from ...models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong
from ...repositories.attendance_repo import AttendanceRepository
from ..gio_xuong import gio_xuong, lich_hien_thi
from . import boi_canh, danh_sach, pham_vi
from .boi_canh import BoiCanh

# Cột "Khác" — cố định, LUÔN có mặt trong `meta()` dù hôm nay chưa lệnh nào rơi vào đó. Đây là
# đường thoát tường minh cho bước không tra được về danh mục (Ruling C113), không phải một facet
# dẫn xuất từ dữ liệu như `dem_theo_tab` của `danh_sach.py`.
COT_KHAC = "khac"
NHAN_KHAC = "Khác"

# Hai trạng thái công việc coi là "đang có người làm" — hiện thành chip trên card. Không gồm
# `CV_PHAT_HANH` (đang chờ tới lượt): chip là để thấy NGAY máy nào/tổ nào đang bận, không phải
# liệt kê cả hàng đợi.
_DANG_LAM = (CV_DANG_CHAY, CV_TAM_DUNG)

# MỘT vị ngữ dùng CHUNG cho `meta()` (khung cột) và `cd_con_song` trong `kanban()` (lọc soft-ref
# trỏ hụt ở `_the`) — Vòng sửa 1 mục B. Rút ra hằng thay vì viết `where` hai lần: lệch nhau ở đây
# là đẻ ra card mang `cot` không tồn tại trong `meta()["cot"]`.
_DANG_DUNG = CongDoan.active.is_(True)

# --- Nhãn "đường thoát tường minh" DÙNG CHUNG cho cả BA góc nhìn (Vòng sửa 1 mục A/G,
# task-16-fix1-brief.md) — RÚT LÊN ĐÂY (trước đây `NHAN_CHUA_XEP_MAY`/`NHAN_MAY_DA_XOA` nằm ngay
# trước `theo_may()`): `_ten_may` bên dưới được `_the()` của Kanban gọi, mà `_the()` đứng TRƯỚC
# `theo_may()` trong file — hằng neo phải lên trước điểm dùng đầu tiên.
NHAN_CHUA_XEP_MAY = "Chưa xếp máy"
# `may_id` không NULL nhưng không tra được trong `bc.may` (soft-ref trỏ hụt — máy đã bị xoá khỏi
# `may_thiet_bi`, xem docstring `boi_canh`) — vẫn phải có nhãn tiếng Việt, cấm để id lọt ra.
NHAN_MAY_DA_XOA = "Máy đã xoá"
# Rổ "không tra được ca nào" của `/theo-ca` (Vòng sửa 1 mục A, CHẶN-1) — LUÔN có mặt, `CaOut.id`
# mang `None` để phân biệt với ca thật.
NHAN_NGOAI_CA = "Ngoài ca"
# Giá trị SENTINEL của `?ca_id=` để CHỌN rổ "Ngoài ca" (Task 18a, Ruling C134) — `ca_id` thật là
# `int` (khoá `work_shifts.id`), rổ "Ngoài ca" mang `id=None` trong `CaOut` nên không có số nào để
# gõ vào URL cho nó; cần một hằng CHUỖI tách biệt hẳn khỏi mọi giá trị `int` hợp lệ. Dùng làm
# `Literal[...]` ở router (`CaId = int | Literal[CA_ID_NGOAI_CA] | None`) — KHÔNG được im lặng bỏ
# qua khả năng lọc đúng rổ này, đó là bài học Task 16 đã trả giá một vòng sửa.
CA_ID_NGOAI_CA = "ngoai_ca"


def _ten_may(may: dict[int, MayThietBi], may_id: int | None) -> str:
    """Nhãn máy MỘT NƠI DUY NHẤT (Vòng sửa 1 mục G/GN-3/NS-4) — trước đó idiom
    `may.ten if (may := bc.may.get(may_id)) is not None else None` lặp lại dưới BA hình dạng khác
    nhau (`_khoa_lane_may`, closure `ten_lane` của `theo_may`, biểu thức inline của `_the`/
    `theo_ca`): Kanban trả `None` cho máy chưa gán, `/theo-may` trả `"Chưa xếp máy"`, `/theo-ca`
    lại trả `None` — CÙNG một sự thật (chưa gán máy) mà ba cửa nói ba câu khác nhau. Một hàm thì ba
    cửa không thể trôi ra ba hướng.

    LUÔN trả một CHUỖI (không bao giờ `None`) — tiếng Việt CÓ DẤU cho cả hai nhánh rỗng: chưa gán
    (`may_id is None`) và soft-ref trỏ hụt (máy đã xoá khỏi `may_thiet_bi`).

    Task 17 (C126 mục 2) đổi tham số đầu từ `BoiCanh` sang chính DICT máy: `/theo-may` nay dựng
    lane cho cả máy KHÔNG có việc nào, mà máy như thế không nằm trong `bc.may` (`boi_canh` chỉ nạp
    máy được công việc/phiên/sự cố nhắc tới). Truyền `bc` vào thì lane của máy rảnh mang nhãn
    "Máy đã xoá" — một câu nói dối im lặng. Hai bàn còn lại vẫn truyền `bc.may`.
    """
    if may_id is None:
        return NHAN_CHUA_XEP_MAY
    m = may.get(may_id)
    return m.ten if m is not None else NHAN_MAY_DA_XOA


def _may_danh_muc(db: Session) -> dict[int, MayThietBi]:
    """DANH MỤC máy (`may_thiet_bi`) — TOÀN BỘ, kể cả `active=False`. MỘT câu SQL.

    Hai nơi dùng, và phải dùng CHUNG một nguồn (Task 17):
      · `bo_loc()` — ô lọc Máy, kèm cờ `ngung_dung`;
      · `theo_may()` — KHUNG LANE, để máy đang rảnh vẫn có lane (C126 mục 2).
    Tách hai nguồn ra là ô lọc bày một máy mà bàn không có lane cho nó (hoặc ngược lại) — đúng lớp
    lệch mà `_DANG_DUNG` sinh ra để chặn giữa `meta()` và `cd_con_song`.

    Sắp theo TÊN rồi MÃ — thứ người dùng đọc trước, mã làm nấc phân giải cuối cho thứ tự toàn phần
    (hai máy trùng tên vẫn có thứ tự ổn định giữa hai lần gọi). Khuôn `danh_sach.bo_loc`.
    """
    return {
        m.id: m
        for m in db.execute(
            select(MayThietBi).order_by(MayThietBi.ten.asc(), MayThietBi.ma.asc())
        ).scalars()
    }


def _cv_trong_pham_vi(trong_pham_vi):
    """Subquery `id` của MỌI công việc thuộc các lệnh trong `trong_pham_vi` — HAI vế gộp bằng
    `UNION` trong CÙNG một câu (khuôn nhánh `qua_ghep` của `theo_ca`).

    Vế 1 — công việc NEO THẲNG (`san_xuat_cong_viec.lsx_id IN (...)`).
    Vế 2 — công việc CHUNG của bài ghép (`lsx_id IS NULL`), với tới lệnh qua `bai_ghep_cong_doan_map`.
    Bỏ vế 2 là bỏ đúng khâu nặng nhất của lệnh in ghép, cùng luận cứ `_co_viec` vế 2.

    Là SUBQUERY (không phải một lượt đi DB): mọi chỗ dùng đều nhúng nó vào câu của mình, nên rút
    hàm này ra KHÔNG làm tăng số câu SQL.
    """
    return (
        select(SanXuatCongViec.id.label("id"))
        .where(SanXuatCongViec.lsx_id.in_(trong_pham_vi))
        .union(
            select(SanXuatCongViec.id.label("id"))
            .join(
                BaiGhepCongDoanMap,
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id
                == SanXuatCongViec.bai_ghep_cong_doan_id,
            )
            .where(BaiGhepCongDoanMap.lsx_id.in_(trong_pham_vi))
        )
        .subquery()
    )


def _may_con_no_viec(db: Session, sale_ids: set[int] | None) -> set[int]:
    """VỊ NGỮ DUY NHẤT của câu hỏi "máy này còn nợ việc không" (Ruling C136) — MỘT câu SQL, trả
    tập `may_id`.

    Định nghĩa, và nó phải khớp TỪNG CHỮ với hợp đồng API của cờ `co_viec`: máy có ÍT NHẤT MỘT
    công việc CHƯA HOÀN THÀNH (`trang_thai != CV_HOAN_THANH`) thuộc lệnh ĐÃ PHÁT HÀNH trong PHẠM
    VI người gọi. Ba vế đều load-bearing: bỏ `!= CV_HOAN_THANH` là máy xong việc từ tháng trước
    vẫn báo "đang nợ"; bỏ `_cv_trong_pham_vi` là một Sale scope `own` đọc được phần việc của người
    khác; bỏ vế ghép bên trong subquery là mất đúng ca in ghép.

    --- VÌ SAO PHẢI LÀ MỘT HÀM, VÀ VÌ SAO ĐỘC LẬP CỬA SỔ (Vòng sửa 2, C136) ------------------------
    HAI nơi hỏi cùng câu này:
      · `bo_loc()` — cờ `co_viec` của từng mục máy (gợi ý cho FE, C133);
      · `theo_may()` — máy NGỪNG DÙNG có được đẻ lane không (C132).
    Trước vòng sửa 2, `theo_may()` trả lời bằng cách nhìn `cvs` — tập công việc ĐÃ LỌC THEO CỬA SỔ.
    Nhưng "còn nợ việc" là thuộc tính của MÁY, không phải của khoảng thời gian đang xem: một máy đã
    thanh lý còn nợ một bước xếp cho tuần sau thì thu cửa sổ về hôm nay là lane BIẾN MẤT, trái lời
    hứa vô điều kiện của C132 (và là lần thứ ba của họ lỗi "cửa sổ thu hẹp làm dữ liệu biến mất im
    lặng" trên nhánh này). Một nguồn sự thật thì không trôi lệch được; hai bản chép tay thì có.

    Cửa sổ `?tu`/`?den` KHÔNG được truyền vào đây, và đó là điểm mấu chốt — chứ không phải thiếu
    sót. Cửa sổ quyết định BLOCK nào vẽ ra; hàm này quyết định LANE nào tồn tại.
    """
    cv = _cv_trong_pham_vi(pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids))
    return set(
        db.execute(
            select(SanXuatCongViec.may_id)
            .where(
                SanXuatCongViec.may_id.is_not(None),
                SanXuatCongViec.trang_thai != CV_HOAN_THANH,
                SanXuatCongViec.id.in_(select(cv.c.id)),
            )
            .distinct()
        ).scalars()
    )


def _cong_doan_dang_dung(db: Session) -> list[tuple[int, str]]:
    """`[(cong_doan.id, nhãn)]` của công đoạn CÒN DÙNG — MỘT câu SQL, nguồn CHUNG của `meta()`
    (khung cột Kanban) và `bo_loc()` (ô lọc Công đoạn).

    Nhãn ưu tiên `ten_hien_thi` khi đã khai (Vòng sửa 1 mục G) — tên tổ SX quen gọi, không phải tên
    kỹ thuật trong danh mục. Sắp theo `id` = thứ tự KHAI, ổn định giữa hai lần tải và không phụ
    thuộc bảng chữ cái (hai công đoạn trùng tên vẫn tách được).

    Rút thành hàm chung ở Task 17 vì cùng lý do đã rút `_DANG_DUNG`: hai nơi bày CÙNG một danh mục
    mà đọc bằng hai câu riêng thì sớm muộn một bên đổi nhãn/đổi vị ngữ lọc, và triệu chứng là ô lọc
    hiện một tên còn cột board hiện tên khác cho cùng một công đoạn.
    """
    rows = db.execute(
        select(CongDoan.id, CongDoan.ten, CongDoan.ten_hien_thi)
        .where(_DANG_DUNG)
        .order_by(CongDoan.id)
    ).all()
    return [(cd_id, ten_hien_thi or ten) for cd_id, ten, ten_hien_thi in rows]


def _ids_trong_pham_vi(
    db: Session, sale_ids: set[int] | None, *, loc: "BoLoc | None" = None, them=None,
) -> list[int]:
    """Toàn bộ id LSX đã phát hành trong phạm vi người gọi, ĐÃ ÁP bộ lọc — câu lặp nguyên văn ở
    `kanban()` và `theo_may()` (Vòng sửa 1 mục J/GN-3). `theo_ca()` KHÔNG dùng hàm này: từ Vòng sửa
    1 mục I nó cần một cửa sổ ngày dựng theo tập ca, nên không còn là bản sao nguyên văn — xem
    `_cua_so_ngay_xuong`.

    `them` là một vị ngữ SQL phụ (Task 17: cửa sổ thời gian của `/theo-may`) gắn thêm vào cùng câu
    — LỌC Ở SQL, TRƯỚC `boi_canh.nap()`, không phải lọc trên tập đã nạp (Ruling C121).
    """
    stmt = _loc_ban(pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids), loc)
    if them is not None:
        stmt = stmt.where(them)
    return list(db.execute(stmt).scalars())


def meta(db: Session) -> dict:
    """`{cot: [{key, ten}]}` — khung cột của board. Xem Ruling C113 ở docstring module.

    `key` = `str(cong_doan.id)` (JSON/URL đều muốn chuỗi, và để khớp thẳng với `card["cot"]` —
    cả hai đều là chuỗi, so sánh không phải ép kiểu). Danh mục + nhãn lấy qua
    `_cong_doan_dang_dung()` — CHUNG với ô lọc Công đoạn của `bo_loc()`.
    """
    cot = [{"key": str(cd_id), "ten": ten} for cd_id, ten in _cong_doan_dang_dung(db)]
    cot.append({"key": COT_KHAC, "ten": NHAN_KHAC})
    return {"cot": cot}


# --- Bộ lọc chung của màn (Task 17, Ruling C121) --------------------------------------------------
# Nhãn TIẾNG VIỆT CÓ DẤU cho ba nhóm facet mà giá trị là MÃ HẰNG TRONG CODE (không phải danh mục
# người dùng khai được). Ba dict này là chỗ DUY NHẤT dịch mã → chữ cho màn này.
#
# `NHAN_NHOM_CONG_DOAN` bám đúng bốn chữ mà cửa nhập Excel danh mục Công đoạn đang dạy người dùng
# (`services/catalog_excel_specs.py:451,471`) — hai cửa nói hai bộ từ vựng cho cùng bốn mã là bắt
# người dùng học hai lần. Dựng theo `models/cong_doan.NHOM` để thêm/bớt mã bên đó là lộ ra ở đây
# (thiếu nhãn ⇒ rơi về chính mã, không im lặng mất mục).
NHAN_NHOM_CONG_DOAN = {
    "prepress": "Trước In", "print": "In",
    "finishing": "Gia công sau in", "other": "Dịch vụ khác",
}
# Trạng thái CÔNG VIỆC — dùng ĐÚNG bốn chữ mà hai màn đang chạy đã bày cho người dùng
# (`frontend/src/pages/thsxShared.tsx:26-29` và `LenhSxHoSoView.tsx:78-81`).
NHAN_TRANG_THAI_VIEC = {
    CV_PHAT_HANH: "Chờ làm", CV_DANG_CHAY: "Đang chạy",
    CV_TAM_DUNG: "Tạm dừng", CV_HOAN_THANH: "Hoàn thành",
}
# Mức ưu tiên — hai giá trị của `danh_sach.UU_TIEN_CHO_PHEP` (cột thật là `lsx.is_rush`, Boolean).
NHAN_UU_TIEN = {danh_sach.UU_TIEN_GAP: "Gấp", danh_sach.UU_TIEN_THUONG: "Bình thường"}

TRANG_THAI_VIEC_CHO_PHEP = (CV_PHAT_HANH, CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)


@dataclass(frozen=True)
class BoLoc:
    """Thanh lọc CHUNG của cả bốn góc nhìn — `/kanban`, `/theo-may` (Ruling C121, Task 17a), và từ
    Task 18a cũng chính `/theo-ca` + `/gantt`. Trường `None` = KHÔNG lọc — không có mặc định nào
    được bịa ra ở tầng này.

    --- BỘ LỌC CHỌN *LỆNH*, KHÔNG CHỌN CARD/BLOCK/CA -----------------------------------------------
    Mọi trường ở đây thu hẹp TẬP LỆNH ở SQL (`_loc_ban`), trước `boi_canh.nap()` (và trước cắt trang
    ở `gantt()`). Hệ quả phải nói thẳng ra cho FE viết microcopy đúng: lọc `may_id=X` trên
    `/theo-may` cho ra những LỆNH có bước trên máy X — và lane của các lệnh đó vẫn bày cả bước chạy
    trên máy KHÁC; `/theo-ca?may_id=X` cũng vậy, ca vẫn hiện ĐỦ mọi việc-trong-ngày của lệnh đó chứ
    không chỉ việc chạy trên máy X. Đổi lại, cùng một bộ lọc cho cùng một tập lệnh trên CẢ BỐN tab;
    một tab hiểu bộ lọc theo nghĩa khác tab kia mới là thứ làm người điều độ đọc sai số.

    --- VÌ SAO KHÔNG CÓ `ca_id` / `tre` ------------------------------------------------------------
    Xem `bo_loc()` — hai thứ đó không diễn đạt được bằng `WHERE` trong MỘT lượt nạp, và brief C121
    chốt rõ: lọc nào không lấy được thì BỎ, cấm bù bằng lọc ở client.
    """

    q: str | None = None
    khach_hang_id: int | None = None
    may_id: int | None = None
    cong_doan_id: int | None = None
    nhom_cong_doan: str | None = None
    cong_nhan_id: int | None = None
    trang_thai_viec: str | None = None
    uu_tien: str | None = None


def _co_viec(*dieu_kien):
    """"Lệnh này có CÔNG VIỆC nào thoả `dieu_kien` không" — HAI vế `EXISTS` trong CÙNG một `WHERE`
    (vẫn một câu SQL), tương quan với `Lsx.id` của câu bao ngoài.

    Vế 1 — công việc NEO THẲNG (`san_xuat_cong_viec.lsx_id = Lsx.id`).
    Vế 2 — công việc CHUNG của bài ghép (`lsx_id IS NULL`), với tới lệnh qua `bai_ghep_cong_doan_map`.
    Bỏ vế 2 là bỏ đúng khâu NẶNG NHẤT của lệnh in ghép: bước bị bài ghép phủ KHÔNG đẻ công việc
    riêng (`services/san_xuat/snapshot.py`), nên "lệnh đang chạy" hay "ai đang làm lệnh này" ở ca in
    ghép chỉ tra được ở đây. Cùng luận cứ với `danh_sach._co_buoc` vế 2 và với nhánh UNION
    `qua_ghep` của `theo_ca` (Vòng sửa 1 mục I).

    KHÁC `danh_sach._co_buoc` ở chỗ KHÔNG có vế ROUTING (`lsx_cong_doan`): hàm này soi những cột
    chỉ tồn tại trên CÔNG VIỆC (trạng thái thực thi, người được giao, mốc giờ đã xếp) — routing
    không có bản sao nào của chúng để mà soi.
    """
    return or_(
        select(SanXuatCongViec.id)
        .where(SanXuatCongViec.lsx_id == Lsx.id, *dieu_kien)
        .exists(),
        select(SanXuatCongViec.id)
        .join(
            BaiGhepCongDoanMap,
            BaiGhepCongDoanMap.bai_ghep_cong_doan_id == SanXuatCongViec.bai_ghep_cong_doan_id,
        )
        .where(BaiGhepCongDoanMap.lsx_id == Lsx.id, *dieu_kien)
        .exists(),
    )


def _loc_ban(stmt, loc: BoLoc | None):
    """Gắn HẾT bộ lọc của thanh lọc vào một `select(Lsx.id)` đã mang sẵn phạm vi + `da_phat_hanh`.

    TẤT CẢ ở SQL, TRƯỚC `boi_canh.nap()` (Ruling C121) — trái luật của repo là kéo cả tập về rồi
    lọc ở Python/JS. Tham số vắng mặt (`None`) không sinh mệnh đề nào.

    Ba trường đi qua `danh_sach._co_buoc` (BA vế `EXISTS`: công việc riêng · công việc ghép ·
    routing) chứ KHÔNG chép lại: `may_id` và `nhom_cong_doan` phải cho CÙNG một tập lệnh với bảng
    "Hồ sơ lệnh sản xuất" (`/api/lenh-san-xuat?may_id=`) — hai bàn cùng một xưởng mà chọn cùng một
    máy lại ra hai tập lệnh khác nhau là lỗi không ai truy được. Chép hàm ra làm bản thứ hai thì
    bản trôi trước là bản nói dối (xem docstring `tests/lenh_sx_fixtures.py`).

      · `may_id`         — `_co_buoc(SanXuatCongViec.may_id, LsxCongDoan.may_id, v)`.
      · `nhom_cong_doan` — `_co_buoc(SanXuatCongViec.nhom_cong_doan, LsxCongDoan.nhom, v)`.
      · `cong_doan_id`   — MỘT vế `EXISTS` trên routing, vì `san_xuat_cong_viec` KHÔNG có cột
                           `cong_doan_id` (`models/san_xuat.py`: nó neo lỏng bằng `step_key` +
                           `lsx_cong_doan_id`). Đây đúng là con đường mà `card["cot"]` đi
                           (`step_key → lsx_cong_doan.cong_doan_id`, Ruling C113), nên lọc theo
                           một cột Kanban ra đúng những card đứng ở cột đó. Bước bị bài ghép phủ
                           vẫn có dòng `lsx_cong_doan` của riêng lệnh ⇒ một vế là ĐỦ, không hụt.
      · `cong_nhan_id`   — `_co_viec(...)`, chỉ dòng phân công ĐANG HOẠT ĐỘNG (`PC_HOAT_DONG`):
                           người đã bị rút khỏi bước còn dòng `removed` để giữ lịch sử
                           (`thuc_thi.go_phan_cong`), lọc trúng nó là chỉ sai người đang làm.
      · `trang_thai_viec`— `_co_viec(...)`; "lệnh CÓ ÍT NHẤT MỘT bước ở trạng thái đó", không phải
                           "trạng thái của cả lệnh" (lệnh không có trạng thái thực thi nào cả).
      · `uu_tien`        — cột phẳng `lsx.is_rush`.
      · `khach_hang_id`  — qua SUBQUERY trên `orders`, KHÔNG `join(Order)`: phạm vi hẹp đã có thể
                           join `orders` rồi (`pham_vi.loc_lsx_da_phat_hanh`), join lần hai là một
                           bảng xuất hiện hai lần trong cùng câu. Cùng lý do `danh_sach._loc_sql`
                           dựng `q` bằng subquery.
      · `q`              — mã/tên lệnh · số đơn · tên khách, khuôn nguyên văn `danh_sach._loc_sql`.
    """
    if loc is None:
        return stmt

    if loc.q and loc.q.strip():
        mau = f"%{loc.q.strip()}%"
        don_khop = (
            select(Order.id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(or_(Order.order_no.ilike(mau), Customer.name.ilike(mau)))
        )
        stmt = stmt.where(
            or_(Lsx.ma.ilike(mau), Lsx.ten.ilike(mau), Lsx.order_id.in_(don_khop))
        )

    if loc.khach_hang_id is not None:
        stmt = stmt.where(
            Lsx.order_id.in_(
                select(Order.id).where(Order.customer_id == loc.khach_hang_id)
            )
        )

    if loc.may_id is not None:
        stmt = stmt.where(
            danh_sach._co_buoc(SanXuatCongViec.may_id, LsxCongDoan.may_id, loc.may_id)
        )

    if loc.nhom_cong_doan:
        stmt = stmt.where(
            danh_sach._co_buoc(
                SanXuatCongViec.nhom_cong_doan, LsxCongDoan.nhom, loc.nhom_cong_doan
            )
        )

    if loc.cong_doan_id is not None:
        stmt = stmt.where(
            select(LsxCongDoan.id)
            .where(
                LsxCongDoan.lsx_id == Lsx.id,
                LsxCongDoan.cong_doan_id == loc.cong_doan_id,
            )
            .exists()
        )

    if loc.cong_nhan_id is not None:
        stmt = stmt.where(
            _co_viec(
                SanXuatCongViec.id.in_(
                    select(SanXuatPhanCong.cong_viec_id).where(
                        SanXuatPhanCong.employee_id == loc.cong_nhan_id,
                        SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
                    )
                )
            )
        )

    if loc.trang_thai_viec:
        stmt = stmt.where(_co_viec(SanXuatCongViec.trang_thai == loc.trang_thai_viec))

    if loc.uu_tien == danh_sach.UU_TIEN_GAP:
        stmt = stmt.where(Lsx.is_rush.is_(True))
    elif loc.uu_tien == danh_sach.UU_TIEN_THUONG:
        stmt = stmt.where(Lsx.is_rush.is_(False))

    return stmt


def bo_loc(db: Session, *, sale_ids: set[int] | None) -> dict:
    """Nguồn của thanh lọc màn "Theo dõi sản xuất" — endpoint RIÊNG (Ruling C121).

    --- VÌ SAO KHÔNG MƯỢN `/api/lenh-san-xuat/bo-loc` -----------------------------------------------
    Endpoint kia gác ô quyền `lenh_san_xuat`, màn này gác `theo_doi_san_xuat`. Repo đã có sẵn đúng
    vết thương ấy ghi lại ở `frontend/src/api/client.ts:10755-10758` (mượn nhầm endpoint gác ô
    khác, vai QC ăn 403 giữa luồng). Nó còn trả đúng MỘT nhóm (`may`) và trả theo luật "mục nào
    cũng phải lọc ra ít nhất một lệnh" — luật ngược hẳn với thứ bàn này cần (xem dưới).

    --- BẢY NHÓM TRẢ VỀ, và nguồn của từng nhóm ----------------------------------------------------
      `may`             DANH MỤC máy, kể cả `active=False` (cờ `ngung_dung`). CỐ Ý KHÔNG lọc theo
                        "máy có việc": nhóm này còn là KHUNG LANE của `/theo-may` (C126 mục 2 —
                        máy đang rảnh phải có lane để điều độ biết chỗ nhét việc). Nên KHÁC
                        `danh_sach.bo_loc`, ở đây một mục CÓ THỂ lọc ra rỗng, và rỗng là câu trả
                        lời đúng chứ không phải ngõ cụt. Kèm cờ `co_viec` (Vòng sửa 1 mục 5,
                        Ruling C133) để FE biết mục nào sẽ ra bảng trắng ở tab Kanban mà tự làm mờ
                        — GỢI Ý, KHÔNG phải bộ lọc: máy rảnh vẫn phải chọn được ở tab Theo máy,
                        đó là toàn bộ lý do C126 mục 2 tồn tại. Định nghĩa cờ ở ngay chỗ tính.
      `cong_nhan`       Người ĐANG được giao (`PC_HOAT_DONG`) ở công việc của lệnh trong phạm vi —
                        HAI vế (công việc riêng ∪ công việc ghép), cùng lý do `_co_viec` vế 2.
      `cong_doan`       Danh mục công đoạn CÒN DÙNG, chung nguồn với `meta()` (`_cong_doan_dang_dung`).
      `nhom_cong_doan`  Bốn mã hằng của `models/cong_doan.NHOM`, dịch qua `NHAN_NHOM_CONG_DOAN`.
      `ca`              `AttendanceRepository.ca_lich_xuong()` — CHỈ để FE dựng ô chọn cho tab
                        "Theo ca" (Task 18). `/kanban` và `/theo-may` KHÔNG nhận `ca_id`, xem dưới.
      `trang_thai_viec` Bốn trạng thái của `SanXuatCongViec`.
      `uu_tien`         Hai mức của `danh_sach.UU_TIEN_CHO_PHEP`.
      `khach_hang`      Khách của chính các lệnh trong phạm vi (không phải cả sổ khách hàng — chọn
                        một khách không có lệnh nào là một lựa chọn dẫn tới ngõ cụt).

    --- NHỮNG THỨ ĐÃ BỎ, và vì sao (C121: "lọc nào không lấy được thì BỎ và BÁO") -------------------
      · **Lọc theo CA** — xếp một công việc vào ca là phép tính Python trên mốc giờ tường, có nhánh
        ca qua nửa đêm phải LÙI ngày (`_ca_cua_moc`, Ruling C120). Diễn đạt nó bằng `WHERE` đòi hàm
        ngày-giờ của DB, mà SQLite (test) với Postgres (prod) không nói cùng cú pháp — đúng nỗi lo
        `NULLS LAST` mà `danh_sach._khoa_sap` đã né. Facet `ca` vẫn trả về vì tab "Theo ca" cần.
      · **Lọc theo CẢNH BÁO TRỄ** — `trang_thai.co_canh_bao`/`tien_do.tre_han` là DẪN XUẤT tính từ
        20 map của `boi_canh`, không có cột nào để `WHERE` (chính lý do `danh_sach` phải lọc hai
        tầng). Áp được nó ở đây nghĩa là nạp TOÀN BỘ phạm vi rồi mới lọc — ngược hẳn C121.
      · **Facet SẢN PHẨM** — `lsx.ten` là chữ tự do, một xưởng chạy lâu năm có hàng nghìn giá trị
        khác nhau; bày thành ô chọn là bày một danh sách không ai cuộn hết. Phủ bằng `?q=` (đã soi
        `lsx.ma`, `lsx.ten`, số đơn, tên khách).

    Số câu SQL HẰNG SỐ, không phụ thuộc số lệnh và cũng KHÔNG phụ thuộc số máy: máy (1) + cờ
    `co_viec` (1, `_may_con_no_viec`) + công đoạn (1) + khách (1) + công nhân (1) + ca (1, qua
    repo). Ba nhóm còn lại là hằng trong code, 0 câu. Con số này có hàng rào từ vòng sửa 2
    (`test_bo_loc_khong_n_plus_1`) — trước đó một bản tính `co_viec` bằng một câu cho MỖI máy vẫn
    để cả 11 bài `/bo-loc` xanh, dù đây là endpoint FE gọi mỗi lần mở màn.
    """
    trong_pham_vi = pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids)

    # Công việc thuộc phạm vi (subquery, không phải một lượt đi DB) — facet `cong_nhan` đứng trên nó.
    cv_trong_pham_vi = _cv_trong_pham_vi(trong_pham_vi)

    # Cờ `co_viec` (Vòng sửa 1 mục 5, Ruling C133) — GỢI Ý cho FE, KHÔNG phải bộ lọc. Định nghĩa
    # nằm ở `_may_con_no_viec`, và từ Vòng sửa 2 (Ruling C136) NƠI ĐÓ là chỗ DUY NHẤT định nghĩa
    # nó: `theo_may()` gọi CÙNG hàm này để quyết định máy ngừng dùng có đẻ lane không. Trước đây
    # hai nơi tự trả lời theo hai cách — `/bo-loc` xét độc lập cửa sổ (đúng), `/theo-may` xét trên
    # tập đã lọc theo cửa sổ (sai) — nên cùng một máy được trả lời hai kiểu trong cùng một màn.
    may_co_viec = _may_con_no_viec(db, sale_ids)
    may = [
        {
            "id": str(m.id),
            "ten": m.ten,
            "ngung_dung": not bool(m.active),
            "co_viec": m.id in may_co_viec,
        }
        for m in _may_danh_muc(db).values()
    ]

    cong_doan = [{"id": str(cd_id), "ten": ten} for cd_id, ten in _cong_doan_dang_dung(db)]

    khach_rows = db.execute(
        select(Customer.id, Customer.name)
        .join(Order, Order.customer_id == Customer.id)
        .join(Lsx, Lsx.order_id == Order.id)
        .where(Lsx.id.in_(trong_pham_vi))
        .distinct()
    ).all()
    khach = sorted(
        ({"id": str(cid), "ten": ten} for cid, ten in khach_rows),
        key=lambda x: (x["ten"] or "", x["id"]),
    )

    nguoi_rows = db.execute(
        select(Employee.id, Employee.full_name)
        .join(SanXuatPhanCong, SanXuatPhanCong.employee_id == Employee.id)
        .where(
            SanXuatPhanCong.cong_viec_id.in_(select(cv_trong_pham_vi.c.id)),
            SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
        )
        .distinct()
    ).all()
    cong_nhan = sorted(
        ({"id": str(eid), "ten": ten} for eid, ten in nguoi_rows),
        key=lambda x: (x["ten"] or "", x["id"]),
    )

    cas = AttendanceRepository(db).ca_lich_xuong()
    return {
        "may": may,
        "cong_nhan": cong_nhan,
        "cong_doan": cong_doan,
        "nhom_cong_doan": [
            {"id": ma, "ten": NHAN_NHOM_CONG_DOAN.get(ma, ma)} for ma in NHOM_CONG_DOAN
        ],
        "ca": [{"id": str(ca.id), "ten": ca.name} for ca in cas],
        "trang_thai_viec": [
            {"id": tt, "ten": NHAN_TRANG_THAI_VIEC[tt]} for tt in TRANG_THAI_VIEC_CHO_PHEP
        ],
        "uu_tien": [
            {"id": ma, "ten": NHAN_UU_TIEN[ma]} for ma in danh_sach.UU_TIEN_CHO_PHEP
        ],
        "khach_hang": khach,
    }


def _routing_index(
    db: Session, ids: list[int]
) -> tuple[
    dict[tuple[int, str], tuple[int, int, int | None]], dict[int, tuple[int, int, int | None]]
]:
    """MỘT câu SQL cho cả lô, dựng hai chỉ mục từ `lsx_cong_doan`:

      `theo_khoa[(lsx_id, step_key)] = (id, thu_tu, cong_doan_id)` — tra bước RIÊNG của lệnh.
      `theo_id[lsx_cong_doan.id]     = (lsx_id, thu_tu, cong_doan_id)` — tra qua cầu bài ghép
                                       (`BoiCanh.buoc_phu` trả về đúng những id này).

    `id` có mặt ở cả hai để `_do_sau_tat_ca` (Vòng sửa 1 mục A) tính độ sâu theo đúng
    `lsx_cong_doan.id` — khoá mà cạnh phụ thuộc (`bc.phu_thuoc_buoc`) dùng.

    Không đi qua `boi_canh.nap()` vì nó không nạp `thu_tu`/`cong_doan_id` — hai cột này chỉ Task
    15 cần, gộp vào tầng nạp chung là bắt 14 nơi dùng khác cõng thêm dữ liệu chúng không đọc.
    """
    rows = db.execute(
        select(
            LsxCongDoan.id, LsxCongDoan.lsx_id, LsxCongDoan.step_key,
            LsxCongDoan.thu_tu, LsxCongDoan.cong_doan_id,
        ).where(LsxCongDoan.lsx_id.in_(ids))
    ).all()
    theo_khoa: dict[tuple[int, str], tuple[int, int, int | None]] = {}
    theo_id: dict[int, tuple[int, int, int | None]] = {}
    for rid, lsx_id, step_key, thu_tu, cd_id in rows:
        theo_khoa[(lsx_id, step_key)] = (rid, thu_tu, cd_id)
        theo_id[rid] = (lsx_id, thu_tu, cd_id)
    return theo_khoa, theo_id


def _buoc_cua(
    bc: BoiCanh, lsx_id: int, cv: SanXuatCongViec,
    theo_khoa: dict[tuple[int, str], tuple[int, int, int | None]],
    theo_id: dict[int, tuple[int, int, int | None]],
) -> tuple[int, int, int | None] | None:
    """`(lsx_cong_doan.id, thu_tu, cong_doan_id)` của MỘT công việc, dưới góc nhìn của `lsx_id`.
    `None` khi không tra được (dữ liệu cũ / soft-ref trỏ hụt / cầu bài ghép đã đứt — xem
    `boi_canh.buoc_phu`).

    Bước RIÊNG của lệnh (`cv.lsx_id == lsx_id`) tra thẳng `(lsx_id, cv.step_key)`. Bước GHÉP
    (`cv.lsx_id IS None`) mang `step_key` của CHÍNH dòng bài ghép (`snapshot.dung_cong_viec:251`),
    KHÔNG phải `step_key` của lệnh — nên phải với qua `bc.buoc_phu[cv.id]` (danh sách
    `lsx_cong_doan.id` mà công việc chung này phủ, gộp cả những lệnh KHÁC cùng nằm trên ca ghép),
    rồi lọc đúng dòng thuộc `lsx_id` đang xét. Một công việc ghép phủ NHIỀU bước của CÙNG một lệnh
    (hiếm, nhưng không cấm) thì lấy dòng `thu_tu` nhỏ nhất — đây là chọn VỊ TRÍ đại diện của MỘT
    công việc, khác việc chọn đại diện của CẢ LỆNH ở `_the` (đó dùng độ sâu, xem `_do_sau_tat_ca`).
    """
    if cv.lsx_id == lsx_id:
        return theo_khoa.get((lsx_id, cv.step_key))
    ung_vien = [
        (lcd_id, thu_tu, cd_id)
        for lcd_id in bc.buoc_phu.get(cv.id, [])
        if (info := theo_id.get(lcd_id)) is not None and info[0] == lsx_id
        for thu_tu, cd_id in [info[1:]]
    ]
    return min(ung_vien, key=lambda t: t[1]) if ung_vien else None


def _do_sau_tat_ca(bc: BoiCanh, lsx_id: int) -> dict[int, int]:
    """Độ sâu (đường DÀI NHẤT từ gốc) của mọi `lsx_cong_doan.id` thuộc lệnh `lsx_id`, suy từ cạnh
    có sẵn `bc.phu_thuoc_buoc[lsx_id]` — KHÔNG thêm câu SQL nào (Vòng sửa 1, mục A).

    BẪY 1 — cạnh trỏ sang LỆNH KHÁC: `lsx_service.py:2976,2993-2995` cho phép `buoc_truoc` thuộc
    một LSX khác cùng đơn hàng (vd Bìa phụ thuộc Ruột). `phu_thuoc_buoc[lsx_id]` chỉ lọc theo lsx
    của BƯỚC SAU, nên trong danh sách cạnh của lệnh này có thể có `buoc_truoc_id` KHÔNG thuộc tập
    bước của lệnh này. Cách xử: `preds` (dict target→sources) dựng ĐÚNG BẰNG danh sách cạnh này,
    mà mọi "target" trong đó chắc chắn là bước của `lsx_id` (điều kiện JOIN ở `boi_canh.nap()` câu
    13 đảm bảo) — một tiền bối ngoại lai KHÔNG BAO GIỜ tự nó là "target" của lệnh này nên KHÔNG có
    mặt trong `preds`, và tự nhiên rơi vào nhánh "không có cạnh vào" = độ sâu 0. Không cần lọc tay
    "id có thuộc lệnh này không", không `KeyError`.

    BẪY 2 — chu trình: dữ liệu lẽ ra không có (`LsxService._kiem_chu_trinh_phu_thuoc` chặn ở đường
    ghi THẬT), nhưng không có ràng buộc DB nào cấm dữ liệu cũ/hỏng. Tập `dang_tham` ghi nhận các id
    đang đứng trong ngăn xếp đệ quy; gặp lại một id đang ở đó nghĩa là đụng chu trình — cắt ngay,
    trả độ sâu 0 cho nhánh đó thay vì đệ quy vô tận, không được để cả bàn theo dõi treo vì một dòng
    dữ liệu hỏng.
    """
    preds: dict[int, list[int]] = {}
    for truoc_id, sau_id in bc.phu_thuoc_buoc[lsx_id]:
        preds.setdefault(sau_id, []).append(truoc_id)

    memo: dict[int, int] = {}
    dang_tham: set[int] = set()

    def sau(id_: int) -> int:
        if id_ in memo:
            return memo[id_]
        tien_boi = preds.get(id_)
        if not tien_boi:
            memo[id_] = 0
            return 0
        if id_ in dang_tham:  # BẪY 2: chu trình — cắt, không đệ quy tiếp
            return 0
        dang_tham.add(id_)
        d = 1 + max(sau(p) for p in tien_boi)
        dang_tham.discard(id_)
        memo[id_] = d
        return d

    for id_ in preds:
        sau(id_)
    return memo


def _nhan(cv: SanXuatCongViec) -> dict:
    """Khối NHÃN của MỘT công việc — dùng chung cho Kanban / Theo máy / Theo ca (và KCS / Kho).

    Một hàm chứ không ba: ba chỗ tự dựng lấy là ba cơ hội để một chỗ quên field, rồi nhãn lại đứt
    ở đúng một tab mà không ai để ý — đúng lớp lỗi mà cả chuỗi 04/09/2026 sinh ra để khử.

    Đọc SNAPSHOT trên chính công việc, không tra ngược danh mục: bàn theo dõi phải nói đúng thứ tổ
    đang cầm trong tay, kể cả khi ai đó sửa danh mục sau lúc phát hành.
    """
    k = cv.khuon_json or {}
    return {
        "loai_buoc": cv.loai_buoc,
        "nha_cung_cap": cv.nha_cung_cap,
        "khuon_ma": k.get("ma"),
        "khuon_so_ke": k.get("so_ke"),
        "khuon_tinh_trang": k.get("tinh_trang"),
        "khuon_ngay_ve": k.get("ngay_ve_du_kien"),
        "khuon_da_nhan": cv.khuon_nhan_luc is not None,
    }


def _the(
    bc: BoiCanh, lsx_id: int,
    theo_khoa: dict[tuple[int, str], tuple[int, int, int | None]],
    theo_id: dict[int, tuple[int, int, int | None]],
    cd_con_song: set[int],
) -> dict:
    """MỘT card. `cot`/`buoc_hien_tai` từ bước đại diện — chân sớm nhất theo ĐỘ SÂU đồ thị (Vòng
    sửa 1 mục A, không phải `thu_tu`), hoặc bước CUỐI nếu lệnh đã xong hết; `chip_dang_chay` liệt
    kê ĐỦ mọi công việc `running`/`paused`, không chỉ bước đại diện — xem docstring module vì sao
    hai thứ này phải tách nhau ở lệnh routing song song.
    """
    cvs = bc.cong_viec_du(lsx_id)
    do_sau_map = _do_sau_tat_ca(bc, lsx_id)

    def diem(cv: SanXuatCongViec) -> tuple[int, int, int | None] | None:
        """`(do_sau, thu_tu, cong_doan_id)` — `do_sau` là nấc so sánh CHÍNH, `thu_tu` chỉ còn là
        nấc PHỤ để hai bước cùng độ sâu vẫn có thứ tự ổn định (Vòng sửa 1 mục A)."""
        info = _buoc_cua(bc, lsx_id, cv, theo_khoa, theo_id)
        if info is None:
            return None
        id_, thu_tu, cd_id = info
        return (do_sau_map.get(id_, 0), thu_tu, cd_id)

    def khoa_som_nhat(item: tuple[tuple[int, int, int | None] | None, SanXuatCongViec]) -> tuple:
        """Khoá sắp cho "bước CHƯA xong sớm nhất": biết điểm còn hơn không biết, `cv.id` làm nấc
        cuối cho thứ tự toàn phần."""
        d, cv = item
        if d is None:
            return (1, 0, 0, cv.id)
        do_sau, thu_tu, _cd_id = d
        return (0, do_sau, thu_tu, cv.id)

    def khoa_buoc_cuoi(item: tuple[tuple[int, int, int | None] | None, SanXuatCongViec]) -> tuple:
        """Khoá sắp cho "bước CUỐI" (mọi bước đã xong) — độ sâu LỚN nhất thắng, ngược `khoa_som_nhat`."""
        d, cv = item
        if d is None:
            return (-1, -1, cv.id)
        do_sau, thu_tu, _cd_id = d
        return (do_sau, thu_tu, cv.id)

    diem_theo_cv = [(diem(cv), cv) for cv in cvs]
    con_lai = [t for t in diem_theo_cv if t[1].trang_thai != CV_HOAN_THANH]

    if con_lai:
        d, dai_dien = min(con_lai, key=khoa_som_nhat)
    elif diem_theo_cv:
        d, dai_dien = max(diem_theo_cv, key=khoa_buoc_cuoi)
    else:
        d, dai_dien = None, None

    cd_id = d[2] if d is not None else None
    cot = str(cd_id) if cd_id is not None and cd_id in cd_con_song else COT_KHAC

    chip_dang_chay = [
        {
            "cong_viec_id": cv.id,
            "ten": cv.ten_cong_doan,
            "trang_thai": cv.trang_thai,
            "may": _ten_may(bc.may, cv.may_id),  # Vòng sửa 1 mục G — trước trả None cho máy chưa gán
            "nguoi": bc.nguoi_cua(cv.id),
            "nhan": _nhan(cv),
        }
        for cv in cvs
        if cv.trang_thai in _DANG_LAM
    ]
    return {
        "cot": cot,
        "buoc_hien_tai": dai_dien.ten_cong_doan if dai_dien is not None else None,
        "chip_dang_chay": chip_dang_chay,
    }


def kanban(db: Session, *, sale_ids: set[int] | None, loc: BoLoc | None = None) -> dict:
    """`{cards: [...]}` — MỘT card mỗi lệnh ĐÃ PHÁT HÀNH trong phạm vi người gọi.

    `sale_ids` sinh từ token (`pham_vi.sale_ids_theo_pham_vi`), y hệt `danh_sach.danh_sach`; lệnh
    chưa phát hành (`san_sang`) không thuộc phạm vi của bất kỳ ai — `pham_vi.loc_lsx_da_phat_hanh`
    tự loại, KHÔNG cần lọc tay thêm ở đây.

    `loc` (Task 17, Ruling C121) ép HẾT vào `WHERE` của câu chọn `ids`, tức TRƯỚC `boi_canh.nap()`
    — xem `_loc_ban`. Lọc sau khi nạp thì `nap()` vẫn phải kéo cả phạm vi về, đúng thứ C121 cấm;
    còn để FE lọc thì con số trên card ("đang chạy mấy việc") tính trên tập chưa lọc, sai lặng.
    `loc=None` (hoặc mọi trường `None`) = KHÔNG lọc — cùng tập với trước Task 17.

    Ba lượt nạp cho CẢ lô, không phụ thuộc số lệnh: `boi_canh.nap()` (21 câu) + `_routing_index()`
    (1 câu) + danh mục `cong_doan` (1 câu, dùng để lọc soft-ref trỏ hụt — xem `_the`).
    """
    ids = _ids_trong_pham_vi(db, sale_ids, loc=loc)
    bc = boi_canh.nap(db, ids)
    theo_khoa, theo_id = _routing_index(db, ids)
    cd_con_song = set(db.execute(select(CongDoan.id).where(_DANG_DUNG)).scalars())

    cards = []
    for lsx_id in ids:
        lsx = bc.lenh[lsx_id]
        don = bc.don.get(lsx.order_id)
        khach = bc.khach.get(don.customer_id) if don is not None and don.customer_id else None
        cards.append({
            "lsx_id": lsx.id,
            "ma": lsx.ma,
            "ten": lsx.ten,
            "khach_hang": khach.name if khach is not None else None,
            "so_luong_dat": lsx.so_luong_dat,
            "is_rush": bool(lsx.is_rush),
            "han_hoan_thanh_sx": lsx.han_hoan_thanh_sx,
            **_the(bc, lsx_id, theo_khoa, theo_id, cd_con_song),
        })
    return {"cards": cards}


# --- Theo máy (Task 16) ------------------------------------------------------------------------
# "Chưa xếp máy" LUÔN có mặt trong `theo_may()`, kể cả rỗng — đúng khuôn `COT_KHAC` của Kanban (xem
# đầu file): việc chưa gán máy là đúng thứ điều độ phải xử lý, giấu nó đi (không lane, hoặc lane
# biến mất khi rỗng) là mất dấu. Hai nhãn `NHAN_CHUA_XEP_MAY`/`NHAN_MAY_DA_XOA` đã CHUYỂN lên đầu
# file cạnh `_ten_may` (Vòng sửa 1 mục G) — dùng chung với Kanban/Theo ca, không còn riêng ở đây.
# Mốc "vô cùng" để xếp việc CHƯA xếp giờ xuống cuối mỗi lane — cùng khuôn `_NGAY_XA` của
# `danh_sach.py`, ở đây NAIVE vì `lich_hien_thi()` trả naive (bỏ tzinfo hiển thị).
_MOC_XA_NAIVE = datetime(9999, 12, 31)


def _khoa_lane_may(may_id: int | None, may: dict[int, MayThietBi]) -> tuple:
    """Thứ tự lane: máy CÒN TỒN TẠI (theo tên) trước, máy đã XOÁ sau, "Chưa xếp máy" LUÔN cuối —
    để không lẫn với lane máy thật nào khi FE/test tìm theo `may_id is None`.

    Nhãn dùng để so (nhánh còn tồn tại) rút qua `_ten_may` (Vòng sửa 1 mục G) — nhưng RANK vẫn tự
    phân theo "còn/mất trong `may`", KHÔNG suy ngược từ chuỗi nhãn: một máy thật trùng tên với
    hằng `NHAN_MAY_DA_XOA` (hiếm nhưng không cấm khai) sẽ làm suy-ngược-từ-chuỗi nhận nhầm rank.

    Tham số là DICT máy chứ không còn là `BoiCanh` (Task 17, C126 mục 2): khung lane nay gồm cả
    máy KHÔNG có việc, mà `bc.may` chỉ chứa máy được việc/phiên/sự cố nhắc tới — truyền `bc` vào
    đây thì mọi lane rỗng đều bị xếp rank "máy đã xoá" và bày nhãn "Máy đã xoá". Xem `_ten_may`.
    """
    if may_id is None:
        return (2, "", 0)
    m = may.get(may_id)
    return (0, _ten_may(may, may_id), may_id) if m is not None else (1, "", may_id)


def _cua_so_ban_may(
    tu: date | None, den: date | None
) -> tuple[datetime | None, datetime | None]:
    """`[tu_dt, den_dt)` AWARE cho cửa sổ `?tu`/`?den` của `/theo-may` (Task 17, C126 mục 1).

    Hai đầu ĐỘC LẬP: thiếu đầu nào thì đầu đó KHÔNG chặn (`None`), thiếu cả hai thì không có cửa
    sổ nào — `/theo-may` trở về đúng hành vi Task 16 ("backlog trọn đời", Vòng sửa 1 mục E). Đây
    là luật "tham số vắng mặt = không lọc" của brief, không phải một mặc định bịa ra.

    `den` là NGÀY, và người dùng hỏi TRỌN ngày đó ⇒ biên phải là `den + 1 ngày` lúc 00:00, chặn
    HỞ. Lấy thẳng `den 00:00` là cắt mất mọi việc từ 00:01 tới 23:59 của chính ngày người dùng
    chọn — ĐÚNG lỗi mà Task 16 đã dính ở `/theo-ca` (`_cua_so_ngay_xuong`: "việc 23:00 bị SQL cắt
    TRƯỚC CẢ KHI tới rổ đúng"), lần đó tốn một vòng sửa vì không bài canh nào đặt dữ liệu ở BIÊN.
    Bài canh biên của lần này: `test_theo_may_cua_so_khong_cat_viec_cuoi_ngay_den`.

    Bind AWARE là cố ý: trên Postgres cột là `timestamptz` nên naive sẽ bị hiểu theo múi phiên
    (lệch 7 tiếng — đúng cái bẫy mà `services/gio_xuong.py` mô tả); trên SQLite bộ nạp DATETIME
    bỏ qua tzinfo nên hai đường ra cùng một chuỗi. Cùng khuôn `_cua_so_ngay_xuong`.
    """
    tu_dt = datetime(tu.year, tu.month, tu.day, tzinfo=timezone.utc) if tu is not None else None
    den_dt = (
        datetime(den.year, den.month, den.day, tzinfo=timezone.utc) + timedelta(days=1)
        if den is not None
        else None
    )
    return tu_dt, den_dt


def _cham_cua_so_sql(tu_dt: datetime | None, den_dt: datetime | None):
    """Mệnh đề "công việc này CHẠM cửa sổ" — CHỒNG LẤN, không phải "bắt đầu trong cửa sổ".

    Một ca in dài chạy từ hôm kia tới hôm kìa vẫn ĐANG chiếm máy trong cửa sổ hôm nay; hỏi
    `du_kien_bat_dau BETWEEN tu AND den` là nó biến mất khỏi bàn điều độ đúng lúc nó bận nhất.
    Nên: `bat_dau < den` VÀ `(ket_thuc IS NULL OR ket_thuc >= tu)`.

    `du_kien_bat_dau IS NULL` (chưa xếp giờ) LUÔN LỌT, ở MỌI cửa sổ. Việc chưa xếp giờ chính là
    thứ người điều độ mở bàn này ra để nhét vào — lọc nó đi vì "không thuộc cửa sổ" là giấu mất
    đúng phần việc cần làm, cùng lỗi họ nhà `NHAN_CHUA_XEP_MAY`/`COT_KHAC`/"Ngoài ca".

    --- VÒNG SỬA 1 MỤC 1 (Ruling C135) — `du_kien_ket_thuc IS NULL` là MỞ, không phải TỨC THỜI ---
    Bản trước dùng `COALESCE(ket_thuc, bat_dau)`, tức suy khoảng của một việc chưa khai giờ xong
    thành `[bat_dau, bat_dau]`. Hệ quả THẬT (không cần đột biến nào): một ca `running` mở từ tuần
    trước, chưa ai đóng giờ dự kiến kết thúc, có khoảng nằm TRỌN trước `tu` ⇒ câu này loại nó, và
    vì đây là câu chọn LỆNH nên loại luôn CẢ LỆNH — bàn điều độ mất đúng thứ đang chiếm máy. Vi
    phạm thẳng luật "cửa sổ chỉ NỚI, không THU HẸP" của C126, cùng họ với lỗi Task 16.

    Nay NULL = MỞ TỚI +∞, và CHỈ ở đầu `tu`. Đầu `den` vẫn chặn bằng `bat_dau` (cột luôn có mặt
    khi đã xếp giờ): một việc xếp bắt đầu SAU `den` thì không thuộc cửa sổ dù chưa biết giờ xong —
    mở cả hai đầu là mọi việc chưa khai giờ kết thúc tràn vào mọi cửa sổ, hết còn là cửa sổ.

    Trả `None` khi không có đầu chặn nào — chỗ gọi tự hiểu là "không thêm `WHERE`".
    """
    dieu = []
    if den_dt is not None:
        dieu.append(SanXuatCongViec.du_kien_bat_dau < den_dt)
    if tu_dt is not None:
        dieu.append(
            or_(
                SanXuatCongViec.du_kien_ket_thuc.is_(None),
                SanXuatCongViec.du_kien_ket_thuc >= tu_dt,
            )
        )
    if not dieu:
        return None
    return or_(SanXuatCongViec.du_kien_bat_dau.is_(None), and_(*dieu))


def _cham_cua_so(
    cv: SanXuatCongViec, tu_dt: datetime | None, den_dt: datetime | None
) -> bool:
    """Bản PYTHON của `_cham_cua_so_sql`, dùng để chọn BLOCK sau khi đã nạp. Cùng một vị ngữ, viết
    hai lần vì hai tầng — nên phải đọc song song hai hàm mỗi lần sửa một trong hai.

    Quan hệ giữa hai tầng: câu SQL chọn LỆNH ("lệnh có ÍT NHẤT MỘT công việc chạm cửa sổ", không
    kèm điều kiện trạng thái), còn hàm này chọn BLOCK trong số công việc CHƯA hoàn thành của những
    lệnh đó.

    --- VÒNG SỬA 1 MỤC 6 — trôi lệch chỉ AN TOÀN MỘT CHIỀU -----------------------------------------
    Bản trước ghi ở đây rằng trôi lệch giữa hai tầng "KHÔNG mất dữ liệu vì tập block luôn là tập
    con". Câu đó NÓI QUÁ, và đúng chỗ nói quá ấy là chỗ bug mục 1 sống sót:
      · SQL RỘNG hơn hàm này ⇒ an toàn thật: lệnh thừa được nạp, hàm này gạt block thừa đi.
      · SQL HẸP hơn ⇒ MẤT DỮ LIỆU: lệnh bị loại ngay ở `WHERE`, hàm này KHÔNG BAO GIỜ được nhìn
        thấy công việc đó, nên không có cơ hội "gạt lại". Không tầng nào tự phát hiện được.
    Chiều nguy hiểm ấy nay do hai bài canh gác, không do lập luận: `test_theo_may_cua_so_sql_chan_o
    _tang_lenh_khong_phai_tang_block` (lệnh CÔ LẬP chỉ chạm cửa sổ theo phép chồng lấn) và
    `test_theo_may_viec_chua_biet_gio_xong_loc_ids_truoc_khi_nap`. Sửa MỘT trong hai hàm thì phải
    đọc và sửa hàm kia cùng lượt.

    `du_kien_ket_thuc is None` = MỞ tới +∞ ở đầu `tu` (Ruling C135, mục 1) — giữ `kt` là `None`
    thay vì lùi về `bd`, và chỉ loại khi thực sự biết giờ kết thúc mà giờ đó nằm trước `tu`.

    So sánh phải NAIVE cả hai vế: `du_kien_*` đọc từ SQLite ra naive còn từ Postgres ra aware, hai
    mốc biên thì luôn aware ⇒ so thẳng là `TypeError` trên một trong hai DB. `lich_hien_thi()` bỏ
    tzinfo ở CẢ HAI vế đưa về cùng thang giờ tường (xem `services/gio_xuong.py`).
    """
    bd = lich_hien_thi(cv.du_kien_bat_dau)
    if bd is None:
        return True
    kt = lich_hien_thi(cv.du_kien_ket_thuc)
    if den_dt is not None and bd >= lich_hien_thi(den_dt):
        return False
    if tu_dt is not None and kt is not None and kt < lich_hien_thi(tu_dt):
        return False
    return True


def theo_may(
    db: Session,
    *,
    sale_ids: set[int] | None,
    loc: BoLoc | None = None,
    tu: date | None = None,
    den: date | None = None,
) -> dict:
    """`{lanes: [{may_id, ten, ngung_dung, blocks: [...]}]}` — MỘT lane mỗi máy, cộng lane
    "Chưa xếp máy".

    Chỉ hiện công việc CHƯA hoàn thành (`trang_thai != CV_HOAN_THANH`, quyết định tự chốt — brief
    gốc không nêu rõ, cùng tinh thần `_DANG_LAM` mà Kanban dùng cho `chip_dang_chay`).

    --- VÒNG SỬA 1 MỤC E (task-16-fix1-brief.md) → TASK 17 C126 MỤC 1 — nay ĐÃ có cửa sổ ----------
    Task 16 cố ý KHÔNG nhận cửa sổ: lấy MỌI công việc chưa hoàn thành của MỌI lệnh đã phát hành,
    kể cả việc xếp ba tháng nữa — một backlog trọn đời. Task 17 thêm `tu`/`den` (NGÀY, cùng khuôn
    `?ngay` của `/theo-ca`), và VẮNG MẶT vẫn là hành vi cũ y nguyên: không tham số ⇒ không cửa sổ.
    Hai tab `/theo-may` và `/theo-ca` vẫn trả lời hai câu khác nhau ("việc CÒN PHẢI xếp máy" khác
    "ai đã làm gì trong ca ngày X"), số liệu lệch nhau là ĐÚNG.

    Cửa sổ là phép CHỒNG LẤN (`_cham_cua_so_sql`), lọc ở SQL trước `boi_canh.nap()`, và việc chưa
    xếp giờ LUÔN lọt. Đọc `_cua_so_ban_may` cho ranh giới `den` (trọn ngày) — chỗ Task 16 từng cắt
    mất việc 23:00 ở `/theo-ca`.

    --- TASK 17 C126 MỤC 2 — LANE cho máy KHÔNG có việc -----------------------------------------
    Khung lane = DANH MỤC `may_thiet_bi` (`_may_danh_muc`, cùng nguồn với facet `may` của
    `bo_loc()`), hợp với những `may_id` thực sự có block. Nên một máy CÒN DÙNG mà rảnh ra lane
    `blocks: []` — đó chính là câu "máy nào đang trống để nhét việc vào".

    Một ngoại lệ, Vòng sửa 1 mục 4 (Ruling C132): máy `active=False` mà KHÔNG CÒN NỢ VIỆC thì THÔI
    đẻ lane. "ĐỪNG ẩn lane" của C126 là để chặn VIỆC biến mất, không phải để giữ chỗ cho máy đã
    thanh lý — xưởng chạy lâu năm sẽ có hàng chục lane chết đẩy lane thật xuống dưới màn hình. Máy
    ngừng dùng mà CÒN ôm việc thì lane vẫn hiện nguyên, chỉ đánh dấu `ngung_dung` (mục H).

    --- VÒNG SỬA 2 (Ruling C136) — "còn nợ việc" KHÔNG được nhìn qua cửa sổ ----------------------
    Phép thử của C132 hỏi `_may_con_no_viec` (vị ngữ DÙNG CHUNG với cờ `co_viec` của `bo_loc`),
    KHÔNG hỏi tập công việc đã lọc theo `tu`/`den`. Vòng sửa 1 đặt phép thử ở cuối, đọc `cvs`, nên
    máy đã thanh lý còn nợ một bước xếp cho ngày 20/09 BIẾN MẤT khỏi bàn ngay khi người điều độ thu
    cửa sổ về ngày 10/09 — trái lời hứa vô điều kiện của C132, và là lần thứ ba lỗi "cửa sổ thu hẹp
    làm dữ liệu biến mất im lặng" trên nhánh này. Cửa sổ quyết định BLOCK nào vẽ; nó không có thẩm
    quyền quyết định LANE nào tồn tại. Lane giữ lại có thể `blocks: []` — đó là ĐÚNG, chỗ trống ấy
    chính là câu "máy này vẫn còn nợ, chỉ là không nợ trong khoảng anh đang xem".

    --- Ngoại lệ DUY NHẤT: `may_id=X` (Ruling C131 + C137) -------------------------------------
    Lọc `may_id=X` thì bàn chỉ dựng lane của CHÍNH máy X (kể cả rỗng), không bày lane máy khác cũng
    không bày "Chưa xếp máy" — chọn một máy mà board trả về hai chục lane là câu trả lời sai cho
    câu hỏi đã đặt. Không mất dữ liệu: câu SQL đã giữ lại đúng những lệnh CÓ bước trên máy X, mà
    mọi block nằm trên máy X đều thuộc một lệnh như thế ⇒ lane X đầy đủ.

    Nhánh này KHÔNG chịu C132 (Ruling C137, vòng sửa 2): khung `{mot_may: []}` chốt cứng một lane
    và không có phép khử nào chạy sau đó, nên `?may_id=<máy ngừng dùng đang rảnh>` ra đúng một lane
    rỗng có cờ, `?may_id=<id không có trong danh mục>` ra đúng một lane nhãn "Máy đã xoá". C132 sinh
    ra để khử NHIỄU trong bộ lane MẶC ĐỊNH; một câu hỏi đích danh không phải nhiễu, và trả
    `{"lanes": []}` cho một máy có thật là nói với người dùng rằng máy đó không tồn tại.

    --- VÒNG SỬA 1 MỤC F — gom theo máy HIỆN TẠI là CỐ Ý, không phải thiếu sót -----------------
    Gom theo `cv.may_id` (máy ĐANG gán, KHÔNG phải lịch sử đổi máy): câu hỏi của bàn điều độ là
    "từ giờ trở đi máy nào gánh việc gì", không phải "lúc trước việc này chạy ở đâu" — chuyện đó là
    của báo cáo giờ-máy/hồ sơ lệnh (`ho_so.py:422-467` đã dựng vết đổi máy từ cặp phiên
    `loai_dong='doi_may'`, đọc `san_xuat_phien_chay` — `models/san_xuat_thuc_thi.py:100-106`).
    Khuôn đã có sẵn ở `danh_sach.py:276`: "máy của bước đang xét: `cong_viec.may_id` — máy HIỆN
    TẠI, `thuc_thi.doi_may` ghi vào đây." Mỗi block vẽ dải THỜI GIAN KẾ HOẠCH của CẢ công việc
    (`du_kien_bat_dau/ket_thuc`), không phải khoảng máy hiện tại thật sự đã bận — muốn có thanh
    chiếm dụng THẬT cần lớp mốc thực tế chồng lên (`gio_xuong.thuc_te_hien_thi` đã dọn đường, chưa
    phơi ở đây vì brief không đòi).

    --- VÒNG SỬA 1 MỤC H — máy NGỪNG DÙNG (`MayThietBi.active=False`, mg 0202) CÒN VIỆC thì CÓ lane
    KHÔNG ẩn: việc còn nằm trên máy đã ngừng dùng chính là thứ điều độ phải xử lý, giấu đi là mất
    dấu — đúng nguyên tắc `NHAN_CHUA_XEP_MAY`. `ngung_dung=True` chỉ ĐÁNH DẤU cho FE, không đổi
    tên/vị trí lane (soft-ref còn tra được nên vẫn đi nhánh "máy còn tồn tại" của `_khoa_lane_may`).
    Ranh giới với C132 ở trên: nguyên tắc này bảo vệ VIỆC, không bảo vệ cái lane rỗng.

    Một công việc GHÉP phục vụ nhiều lệnh vẫn ra ĐÚNG MỘT block (khoá theo `cv.id`, giống
    `_DANG_LAM`/`chip_dang_chay` của Kanban không được đếm hai lần); trường `lsx` liệt kê MỌI lệnh
    nó phục vụ, mỗi lệnh là CẶP `{lsx_id, ma}` (Task 17, Ruling C123 — trước chỉ có mã nên FE
    không bấm mở hồ sơ được, phải dò ngược mã → id hoặc đoán). Vẫn sắp theo MÃ như cũ.

    Không N+1: MỘT lượt `boi_canh.nap()` (21 câu, không phụ thuộc số lệnh) + MỘT câu danh mục máy
    (`_may_danh_muc`, cả bảng, hàng chục dòng) + MỘT câu `_may_con_no_viec` (vòng sửa 2, chỉ chạy ở
    nhánh lane mặc định) — không cần `_routing_index()` vì lane chỉ cần `may_id`/`ten_cong_doan`,
    đã có sẵn trên `SanXuatCongViec`.
    """
    tu_dt, den_dt = _cua_so_ban_may(tu, den)
    cham = _cham_cua_so_sql(tu_dt, den_dt)
    them = None if cham is None else _co_viec(cham)
    ids = _ids_trong_pham_vi(db, sale_ids, loc=loc, them=them)
    bc = boi_canh.nap(db, ids)
    danh_muc_may = _may_danh_muc(db)
    # Danh mục THẮNG khi trùng khoá (cùng một dòng DB), nhưng `bc.may` vẫn phải có mặt để một máy
    # bị xoá khỏi danh mục GIỮA hai lượt đọc không tụt xuống nhãn "Máy đã xoá" ngay trong lượt này.
    may_tra_cuu: dict[int, MayThietBi] = {**bc.may, **danh_muc_may}

    cv_theo_id: dict[int, SanXuatCongViec] = {}
    lsx_cua_cv: dict[int, dict[int, str]] = {}
    for lsx_id in ids:
        lsx = bc.lenh[lsx_id]
        for cv in bc.cong_viec_du(lsx_id):
            if cv.trang_thai == CV_HOAN_THANH or not _cham_cua_so(cv, tu_dt, den_dt):
                continue
            cv_theo_id[cv.id] = cv
            lsx_cua_cv.setdefault(cv.id, {})[lsx.id] = lsx.ma

    mot_may = loc.may_id if loc is not None else None
    theo_lane: dict[int | None, list[SanXuatCongViec]] = (
        {mot_may: []} if mot_may is not None else {None: []}
    )
    for cv in cv_theo_id.values():
        if mot_may is not None and cv.may_id != mot_may:
            continue
        theo_lane.setdefault(cv.may_id, []).append(cv)
    if mot_may is None:
        # C126 mục 2 — khung lane MẶC ĐỊNH lấy từ DANH MỤC, máy CÒN DÙNG mà rảnh vẫn có chỗ.
        # C132 — máy NGỪNG DÙNG chỉ được chỗ khi CÒN NỢ VIỆC; máy đã thanh lý và sạch nợ thì thôi,
        # kẻo hàng chục lane chết đẩy lane thật xuống dưới màn hình.
        # C136 — "còn nợ việc" hỏi `_may_con_no_viec` (ĐỘC LẬP cửa sổ), KHÔNG hỏi `theo_lane` (đã
        # lọc theo cửa sổ). Trước Vòng sửa 2 phép thử nằm dưới vòng dựng lane và đọc `cvs`, nên máy
        # đã thanh lý còn nợ một bước xếp cho tuần sau BIẾN MẤT ngay khi thu cửa sổ về hôm nay —
        # cửa sổ quyết định BLOCK nào vẽ, không được quyết định LANE nào tồn tại.
        con_no = _may_con_no_viec(db, sale_ids)
        for may_id, m in danh_muc_may.items():
            if m.active or may_id in con_no:
                theo_lane.setdefault(may_id, [])

    lanes = []
    for may_id in sorted(theo_lane, key=lambda m: _khoa_lane_may(m, may_tra_cuu)):
        may = may_tra_cuu.get(may_id) if may_id is not None else None
        cvs = sorted(
            theo_lane[may_id],
            key=lambda cv: (lich_hien_thi(cv.du_kien_bat_dau) or _MOC_XA_NAIVE, cv.id),
        )
        # KHÔNG có phép khử lane nào ở đây. C132 đã được thi hành ĐÚNG MỘT CHỖ — lúc dựng khung
        # lane mặc định ở trên — nên nhánh `?may_id=` (khung đã chốt cứng `{mot_may: []}`) không
        # bị nó chạm tới. Đó là Ruling C137: C132 sinh ra để khử NHIỄU trong bộ lane MẶC ĐỊNH; một
        # `?may_id=` tường minh không phải nhiễu mà là câu hỏi trực tiếp, phải trả ĐÚNG MỘT lane —
        # rỗng thì rỗng, ngừng dùng thì gắn cờ. Vòng sửa 1 đặt phép khử ở đây nên nó cắt luôn cả
        # nhánh tường minh, biến "cho tôi xem máy X" thành `{"lanes": []}` — người dùng đọc ra
        # "máy này không tồn tại".
        lanes.append({
            "may_id": may_id,
            "ten": _ten_may(may_tra_cuu, may_id),
            "ngung_dung": bool(may is not None and not may.active),  # Vòng sửa 1 mục H
            "blocks": [
                {
                    "cong_viec_id": cv.id,
                    "ten": cv.ten_cong_doan,
                    "trang_thai": cv.trang_thai,
                    "lsx": [
                        {"lsx_id": lid, "ma": ma}
                        for lid, ma in sorted(
                            lsx_cua_cv.get(cv.id, {}).items(), key=lambda kv: (kv[1], kv[0])
                        )
                    ],
                    "du_kien_bat_dau": lich_hien_thi(cv.du_kien_bat_dau),
                    "du_kien_ket_thuc": lich_hien_thi(cv.du_kien_ket_thuc),
                    "nguoi": bc.nguoi_cua(cv.id),
                    "nhan": _nhan(cv),
                }
                for cv in cvs
            ],
        })
    return {"lanes": lanes}


# --- Theo ca (Task 16) -------------------------------------------------------------------------
def _ca_cua_moc(cas: list[WorkShift], moc_tuong: datetime) -> tuple[WorkShift, date] | None:
    """Ca (và NGÀY của ca đó) mà `moc_tuong` (giờ TƯỜNG, đã qua `lich_hien_thi` — NAIVE) rơi vào.

    Ca qua nửa đêm tính theo mốc BẮT ĐẦU ca (Ruling C120, đúng plan gốc): việc chạy 01:00 nằm
    trong cửa sổ `[0, end_minute)` của HÔM NAY là phần ĐUÔI của ca đã bắt đầu TỐI HÔM QUA —
    `ngay_ca` phải lùi lại một ngày để khớp với ngày người dùng bấm xem (mốc bắt đầu ca), không
    phải ngày lịch của chính mốc chạy.

    `cas` phải đã sort theo `start_minute` (đúng thứ tự `AttendanceRepository.ca_lich_xuong()`
    trả về) — hai ca chồng giờ (dữ liệu khai lỗi) thì ca có `start_minute` nhỏ hơn thắng, không
    quan trọng bằng việc hàm này không bao giờ `IndexError`/chọn sai kiểu.
    """
    phut = moc_tuong.hour * 60 + moc_tuong.minute
    ngay = moc_tuong.date()
    for ca in cas:
        if not ca.is_overnight:
            if ca.start_minute <= phut < ca.end_minute:
                return ca, ngay
        elif phut >= ca.start_minute:
            return ca, ngay
        elif phut < ca.end_minute:
            return ca, ngay - timedelta(days=1)
    return None


def _cua_so_ngay_xuong(ngay: date, cas: list[WorkShift]) -> tuple[datetime, datetime]:
    """`[tu, den)` — cửa sổ SQL để lọc `ids` TRƯỚC `boi_canh.nap()` (Vòng sửa 1 mục I,
    task-16-fix1-brief.md, canh NS-6 cho `/theo-ca`).

    Base LUÔN là trọn ngày lịch `ngay` — `[ngay 00:00, ngay+1 00:00)` — KHÔNG phụ thuộc `cas` một
    chút nào. Đây là điều BẮT BUỘC: nếu cửa sổ co hẹp theo "vùng ca đã khai" thì việc 23:00 của
    kịch bản CHẶN-1 (xưởng chỉ khai Ca 1 06–14 + Ca 2 14–22, không phủ 22h–6h) bị SQL cắt mất
    TRƯỚC CẢ KHI tới rổ "Ngoài ca" — tự vá mục A ở tầng trên rồi tự phá nó ở tầng dưới.

    Phần NỚI THÊM sau `ngay+1 00:00` chỉ để bắt phần TRÀN của ca qua nửa đêm (`_ca_cua_moc` gán
    việc rạng sáng `ngay+1` về `ngay_ca = ngay` — xem C120/`viec_ca_dem_qua_ngay`): rộng bằng
    `end_minute` LỚN NHẤT trong số các ca `is_overnight=True` đang có (0 nếu không ca nào qua đêm).
    Dùng `cas` ở đây chỉ để NỚI, không bao giờ để THU HẸP base — nới sai (quá rộng) chỉ tốn một
    chút hiệu năng, thu hẹp sai mới là mất dữ liệu.
    """
    tu = datetime(ngay.year, ngay.month, ngay.day, tzinfo=timezone.utc)
    tran_qua_ngay = max((ca.end_minute for ca in cas if ca.is_overnight), default=0)
    den = tu + timedelta(days=1) + timedelta(minutes=tran_qua_ngay)
    return tu, den


def _viec_theo_ca_dict(bc: BoiCanh, cv: SanXuatCongViec, lsx_cua_cv: dict[int, dict[int, str]]) -> dict:
    """MỘT công việc trong `viec: [...]` — dùng CHUNG cho ca thật lẫn rổ "Ngoài ca" (Vòng sửa 1
    mục A). `may`/`may_id` qua `_ten_may` (mục G) — trước đó trả `None` cho máy chưa gán, khác
    hẳn nhãn `"Chưa xếp máy"` mà `/theo-may` đã dùng cho đúng một sự thật.

    `lsx` (vòng rà UI 2026-09-04) dựng y hệt block của `/theo-may`: map `{lsx_id: ma}` gom sẵn ở
    hàm gọi (công việc GHÉP xuất hiện dưới NHIỀU lệnh nên phải gom, không đọc `cv.lsx_id` — thứ đó
    là `None` với đúng loại việc ấy), sắp theo MÃ để hai lượt tải không đảo thứ tự."""
    return {
        "cong_viec_id": cv.id,
        "ten": cv.ten_cong_doan,
        "trang_thai": cv.trang_thai,
        "may_id": cv.may_id,
        "may": _ten_may(bc.may, cv.may_id),
        "lsx": [
            {"lsx_id": lid, "ma": ma}
            for lid, ma in sorted(lsx_cua_cv.get(cv.id, {}).items(), key=lambda kv: (kv[1], kv[0]))
        ],
        "du_kien_bat_dau": lich_hien_thi(cv.du_kien_bat_dau),
        "nguoi": bc.nguoi_cua(cv.id),
        "nhan": _nhan(cv),
    }


def theo_ca(
    db: Session, *, sale_ids: set[int] | None, ngay: date | None,
    loc: BoLoc | None = None, ca_id: int | Literal[CA_ID_NGOAI_CA] | None = None,
) -> dict:
    """`{ca: [{id, ten, bat_dau_phut, ket_thuc_phut, qua_nua_dem, viec: [...]}]}` — công việc rơi
    vào TỪNG CA của một NGÀY XƯỞNG, cộng MỘT rổ cuối `id=None` ("Ngoài ca").

    Tập ca lấy từ `AttendanceRepository.ca_lich_xuong()` — ĐÚNG hàm mà Xếp lịch dùng
    (`XepLichService._ca_lich_may()` nay gọi lại chính nó, Ruling C117): tập ca của hai bàn phải
    TRÙNG NHAU. Bài canh: `test_tap_ca_trung_voi_xep_lich` + `test_ca_lich_may_mot_nguon_duy_nhat`
    (khoá bằng `inspect.getsource`, Vòng sửa 1 mục B).

    --- VÒNG SỬA 1 MỤC A (điều phối, 2026-09-03) — CHẶN-1: rổ "Ngoài ca" LUÔN có mặt --------------
    C117 gom được MỘT trong BA đường lùi (`or cas` khi không ca nào tick `ca_san_xuat`) nhưng bỏ sót
    hai đường: (a) bước chạy trên MÁY không hề bị ràng buộc bởi tập ca — `XepLichService._lich_may`
    dựng khung `lien_tuc=True` [00:00, 24:00) (`xep_lich_service.py:485`), nên việc 23:00 là bình
    thường dù không ca nào khai phủ giờ đó; (b) `work_shifts` RỖNG (mặc định vì seed sau cổng
    `SEED_DEMO`, và là trạng thái prod trắng) thì Xếp lịch vẫn đặt được việc bằng fallback 08:00–
    16:00 của `LichXuong` (`:153`). Cả hai khiến bản trước `continue` bỏ việc — biến mất khỏi MỌI
    cột mà không ai biết, đúng triệu chứng C117 sinh ra để chặn. Mọi việc mà `_ca_cua_moc` trả
    `None` (kể cả khi `cas` rỗng) rơi vào rổ `id=None`, nhãn `NHAN_NGOAI_CA` — đúng khuôn `COT_KHAC`
    của Kanban / `NHAN_CHUA_XEP_MAY` của `/theo-may` ("giấu nó đi là mất dấu"). Rổ này lọc theo
    NGÀY LỊCH của chính mốc chạy (`moc.date() == ngay`) — không có ca neo mốc BẮT ĐẦU nào để lùi
    ngày như nhánh qua-nửa-đêm của `_ca_cua_moc`.

    `ngay` mặc định "hôm nay" theo ĐỒNG HỒ XƯỞNG (`gio_xuong()`), KHÔNG phải ngày UTC (Ruling
    C120). KHÔNG lọc theo trạng thái công việc — khác `/theo-may` (xem Vòng sửa 1 mục E ở đó): đây
    là bàn xem lịch của MỘT ngày cụ thể (có thể là hôm qua hoặc mai), việc ĐÃ xong trong ca đó vẫn
    phải hiện, không thì xem lại một ngày đã qua sẽ thấy ca trống trơn.

    --- VÒNG SỬA 1 MỤC I — lọc Ở SQL trước `boi_canh.nap()` (NS-6) --------------------------------
    Trước đây `nap()` chạy trên TOÀN TẬP lệnh đã phát hành trong phạm vi — cùng cảnh báo mà chính
    docstring `gantt()` nêu ("một xưởng chạy lâu năm có hàng nghìn lệnh"), mà `/theo-ca` ĐÃ có
    `?ngay` nên lọc được. Cửa sổ `_cua_so_ngay_xuong()` (xem đó) không bao giờ cắt mất việc thuộc
    `ngay` — bài mục A bài 1 phải vẫn xanh sau khi thêm bộ lọc này, đó là điều kiện BẮT BUỘC brief
    đặt ra cho mục I.

    HAI nhánh ứng viên vì công việc GHÉP (`lsx_id IS NULL`) không tự mang `lsx_id` — nó phủ NHIỀU
    lệnh qua `BaiGhepCongDoanMap.lsx_id` (không qua `boi_canh.buoc_phu`, thứ đó chỉ dựng được SAU
    khi đã có `bc`, tức SAU khi đã biết `ids` — vòng luẩn quẩn nếu dùng nó để LỌC `ids`). Bỏ nhánh
    ghép ở bộ lọc SQL sẽ lặp lại ĐÚNG kiểu lỗi mục A vừa vá (một lệnh có việc ghép trong `ngay`
    nhưng không có cv riêng nào trong `ngay` sẽ rớt khỏi `ids`, và mọi việc của lệnh đó biến mất
    khỏi CẢ HAI bàn) — nên bắt buộc UNION cả hai nhánh, không phải một tối ưu tuỳ chọn.

    Không N+1: `boi_canh.nap()` chỉ nạp cho các lệnh CÓ việc trong cửa sổ ngày (thường là một phần
    nhỏ của phạm vi), không phải cả tập.

    --- TASK 18a MỤC W1 — thanh lọc CHUNG (`loc: BoLoc`) --------------------------------------------
    ĐÚNG `_loc_ban` mà `/kanban`/`/theo-may` dùng (Ruling C121), gắn thêm vào SAU cửa sổ ngày ở
    TRÊN, trước khi câu SELECT chạy — vẫn một lượt lọc SQL DUY NHẤT, TRƯỚC `boi_canh.nap()`, không
    một mệnh đề nào chép lại. Hệ quả cần nói rõ cho FE: `loc` thu hẹp Ở CẤP LỆNH, không phải cấp
    công việc — `?may_id=X` cho ra MỌI việc-trong-ngày của những lệnh có bước trên máy X, kể cả
    việc khác của lệnh đó chạy trên máy KHÁC (đúng nghĩa "lệnh này có dính máy X", giống hệt cách
    `/kanban?may_id=` đọc).

    --- TASK 18a MỤC W2 — `ca_id` (đã chốt Ruling C134, KHÔNG đẩy xuống SQL) -------------------------
    Lọc SAU khi đã dựng xong `ca_that`/`ngoai` — thuần Python trên CỘT CA trả về, không thêm vị từ
    SQL, không N+1 (không đọc gì thêm từ DB), không mất dữ liệu (cửa sổ `[tu, den)` ở trên đã chặn
    đúng tập việc của `ngay`, đây chỉ đang CHỌN xem rổ nào trong số các rổ ĐÃ có).

      · `ca_id` vắng mặt (`None`) — không đổi gì, trả `ca_that + [ngoai]` như cũ.
      · `ca_id=<int>` khớp một `WorkShift.id` đang có mặt trong `ca_that` — trả DUY NHẤT ca đó
        (danh sách một phần tử).
      · `ca_id=<int>` KHÔNG khớp ca nào (id lạ/ca đã xoá khỏi danh mục) — trả `{"ca": []}`. KHÔNG
        bịa một ca rỗng mang nhãn giả: khác `/theo-may?may_id=` (Ruling C137) vì DANH MỤC ca không
        có khái niệm "tôi hỏi đích danh một máy đã thanh lý vẫn còn nợ việc" — `work_shifts` không
        phải đối tượng nghiệp vụ có vòng đời "thanh lý mà còn nợ", một id lạ ở đây chỉ có thể là
        gõ sai/copy nhầm, `[]` là câu trả lời trung thực.
      · `ca_id=CA_ID_NGOAI_CA` (chuỗi sentinel `"ngoai_ca"`, KHÔNG phải số) — chọn ĐÚNG rổ "Ngoài
        ca", trả `{"ca": [ngoai]}`. Đây là điểm brief C127/Task 18a nhấn: rổ `id=None` không có số
        nào để gõ vào URL, phải có một giá trị tường minh riêng cho nó — im lặng bỏ sót khả năng
        này là đúng lỗi Task 16 đã tốn một vòng sửa.
    """
    ngay = ngay if ngay is not None else gio_xuong().date()
    cas = AttendanceRepository(db).ca_lich_xuong()
    tu, den = _cua_so_ngay_xuong(ngay, cas)

    truc_tiep = (
        select(SanXuatCongViec.lsx_id)
        .where(SanXuatCongViec.lsx_id.isnot(None))
        .where(SanXuatCongViec.du_kien_bat_dau >= tu, SanXuatCongViec.du_kien_bat_dau < den)
    )
    qua_ghep = (
        select(BaiGhepCongDoanMap.lsx_id)
        .join(
            SanXuatCongViec,
            SanXuatCongViec.bai_ghep_cong_doan_id == BaiGhepCongDoanMap.bai_ghep_cong_doan_id,
        )
        .where(SanXuatCongViec.lsx_id.is_(None))
        .where(SanXuatCongViec.du_kien_bat_dau >= tu, SanXuatCongViec.du_kien_bat_dau < den)
    )
    ung_vien = truc_tiep.union(qua_ghep).subquery()
    ids = list(db.execute(
        _loc_ban(
            pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids)
            .where(Lsx.id.in_(select(ung_vien.c.lsx_id))),
            loc,
        )
    ).scalars())
    bc = boi_canh.nap(db, ids)

    cv_theo_id: dict[int, SanXuatCongViec] = {}
    lsx_cua_cv: dict[int, dict[int, str]] = {}
    for lsx_id in ids:
        lsx = bc.lenh[lsx_id]
        for cv in bc.cong_viec_du(lsx_id):
            cv_theo_id[cv.id] = cv
            lsx_cua_cv.setdefault(cv.id, {})[lsx.id] = lsx.ma

    viec_theo_ca: dict[int, list[SanXuatCongViec]] = {ca.id: [] for ca in cas}
    ngoai_ca: list[SanXuatCongViec] = []
    for cv in cv_theo_id.values():
        moc = lich_hien_thi(cv.du_kien_bat_dau)
        if moc is None:
            continue
        tim = _ca_cua_moc(cas, moc)
        if tim is None:
            if moc.date() == ngay:  # Vòng sửa 1 mục A — "Ngoài ca", KHÔNG bỏ đi nữa
                ngoai_ca.append(cv)
            continue
        ca, ngay_ca = tim
        if ngay_ca == ngay:
            viec_theo_ca[ca.id].append(cv)

    ca_that = [
        {
            "id": ca.id,
            "ten": ca.name,
            "bat_dau_phut": ca.start_minute,
            "ket_thuc_phut": ca.end_minute,
            "qua_nua_dem": bool(ca.is_overnight),
            "viec": [
                _viec_theo_ca_dict(bc, cv, lsx_cua_cv)
                for cv in sorted(
                    viec_theo_ca[ca.id],
                    key=lambda cv: (lich_hien_thi(cv.du_kien_bat_dau), cv.id),
                )
            ],
        }
        for ca in cas
    ]
    ngoai = {
        "id": None,
        "ten": NHAN_NGOAI_CA,
        "bat_dau_phut": None,
        "ket_thuc_phut": None,
        "qua_nua_dem": False,
        "viec": [
            _viec_theo_ca_dict(bc, cv, lsx_cua_cv)
            for cv in sorted(ngoai_ca, key=lambda cv: (lich_hien_thi(cv.du_kien_bat_dau), cv.id))
        ],
    }

    # Task 18a mục W2 (Ruling C134) — lọc `ca_id` SAU khi đã dựng xong cả hai rổ, thuần Python,
    # không câu SQL nào thêm. Xem đoạn "TASK 18a MỤC W2" ở docstring trên cho từng nhánh.
    if ca_id == CA_ID_NGOAI_CA:
        return {"ca": [ngoai]}
    if ca_id is not None:
        return {"ca": [c for c in ca_that if c["id"] == ca_id]}
    return {"ca": ca_that + [ngoai]}


# --- Gantt (Task 16) ---------------------------------------------------------------------------
PAGE_SIZE_GANTT_MAC_DINH = 50
PAGE_SIZE_GANTT_TOI_DA = 200


def gantt(
    db: Session, *, sale_ids: set[int] | None,
    loc: BoLoc | None = None,
    page: int = 1, page_size: int = PAGE_SIZE_GANTT_MAC_DINH,
) -> dict:
    """`{rows, total, page, page_size}` — MỘT dòng mỗi LỆNH (Ruling C118: KHÔNG phải mỗi công
    việc — fixture `hai_muoi_lenh` dựng 20 lệnh KHÔNG công việc/routing nào để canh đúng nhánh
    đếm/phân trang; hiểu nhầm thành "mỗi công việc" thì `total` luôn 0 trên fixture đó và bài
    phân trang đỏ vĩnh viễn).

    Cắt trang Ở SQL (Ruling C119) — `ORDER BY`/`LIMIT`/`OFFSET` ngay trên `select(Lsx.id)`, KHÔNG
    kéo hết lệnh về Python rồi cắt như `danh_sach.danh_sach` (bàn đó BẮT BUỘC sort ở Python vì
    `tab`/`tre` là dẫn xuất không có cột nào `WHERE`/`ORDER BY` được; bàn Gantt không có tầng dẫn
    xuất đó — thứ tự chỉ dựa cột SẴN CÓ trên `lsx` — nên đẩy hết xuống SQL đúng như cảnh báo chi
    phí ở docstring `danh_sach`: "một xưởng chạy lâu năm có hàng nghìn lệnh đã phát hành", kéo cả
    tập về Python mỗi lần vẽ Gantt mới đúng là N+1 mà việc này phải né.

    Thứ tự TẤT ĐỊNH: hạn SX gần nhất trước (NULL — chưa có hạn — xuống CUỐI), mã lệnh làm nấc
    phân giải cuối. Dùng `case()` thay vì `.nulls_last()` để không phụ thuộc SQLite đang chạy có
    hỗ trợ cú pháp `NULLS LAST` hay không — cùng nỗi lo mà `danh_sach._khoa_sap` đã né bằng cách
    sort hẳn ở Python; ở đây né bằng `case()` để vẫn cắt trang được Ở SQL.

    Lệnh CHƯA có công việc/chưa xếp giờ vẫn ra dòng, dải thời gian để `None` — "chưa đủ dữ liệu
    thì nói chưa đủ dữ liệu", không bịa mốc giờ (đúng luật đã dùng ở `ho_so`).

    Không N+1: `boi_canh.nap()` chỉ nạp cho ĐÚNG các id của TRANG đang xem (`page_size` phần tử),
    không phải cả tập — thêm lệnh Ở NGOÀI trang hiện tại không đổi số câu SQL.

    --- TASK 18a MỤC W1 — thanh lọc CHUNG (`loc: BoLoc`), ÁP TRƯỚC CẢ ĐẾM LẪN CẮT TRANG --------------
    ĐÂY LÀ CHỖ DỄ SAI NHẤT của cả task (brief nhắc thẳng): `_loc_ban(pham_vi_stmt, loc)` phải chạy
    TRƯỚC khi `pham_vi_stmt` được dùng để (a) đếm `total` và (b) cắt trang — nếu đảo thứ tự, lọc sẽ
    chỉ còn tác dụng trên MỘT TRANG đã cắt sẵn (dữ liệu đúng ngẫu nhiên ở trang 1, sai hẳn từ trang 2
    trở đi), và `total` sẽ đếm nhầm cả những lệnh KHÔNG khớp lọc. Cả `total` lẫn câu `ORDER BY/
    LIMIT/OFFSET` bên dưới đều tái sử dụng CÙNG MỘT `pham_vi_stmt` đã lọc — không phải hai bản chép
    tay dễ lệch nhau. `/gantt` KHÔNG nhận `ca_id` (Ruling C134): một dòng Gantt là một LỆNH trải
    nhiều ca (Ruling C118), lọc ở thang "ca" trên một hàng đã gộp nhiều ca là vô nghĩa.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, PAGE_SIZE_GANTT_TOI_DA))

    pham_vi_stmt = _loc_ban(pham_vi.loc_lsx_da_phat_hanh(select(Lsx.id), sale_ids), loc)
    total = db.execute(select(func.count()).select_from(pham_vi_stmt.subquery())).scalar_one()

    han_rong = case((Lsx.han_hoan_thanh_sx.is_(None), 1), else_=0)
    ids = list(
        db.execute(
            pham_vi_stmt.order_by(han_rong, Lsx.han_hoan_thanh_sx.asc(), Lsx.ma.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    bc = boi_canh.nap(db, ids)

    rows = []
    for lsx_id in ids:
        lsx = bc.lenh[lsx_id]
        don = bc.don.get(lsx.order_id)
        khach = bc.khach.get(don.customer_id) if don is not None and don.customer_id else None
        cvs = bc.cong_viec_du(lsx_id)
        moc_bat_dau = [m for cv in cvs if (m := lich_hien_thi(cv.du_kien_bat_dau)) is not None]
        moc_ket_thuc = [m for cv in cvs if (m := lich_hien_thi(cv.du_kien_ket_thuc)) is not None]
        # Vòng sửa 1 mục D (NS-1) — `du_kien_ket_thuc` LÀ max trên HAI tập gộp lại (kết thúc ∪ bắt
        # đầu), KHÔNG chỉ tập kết thúc: lệnh xếp dở (bước cuối mới có `du_kien_bat_dau`, chưa có
        # `du_kien_ket_thuc` — hình dạng THẬT, `tien_do.py:99`/`danh_sach.py:246-250` đều rẽ nhánh
        # cho ca này) trước đây làm thanh Gantt kết thúc TRƯỚC lúc bước cuối mới bắt đầu, giấu mất
        # phần việc đã xếp. Hai tập ĐỘC LẬP trước đó là đúng NGUỒN của lỗi.
        moc_ket_thuc_hoac_bat_dau = moc_ket_thuc + moc_bat_dau
        rows.append({
            "lsx_id": lsx.id,
            "ma": lsx.ma,
            "ten": lsx.ten,
            "khach_hang": khach.name if khach is not None else None,
            "han_hoan_thanh_sx": lsx.han_hoan_thanh_sx,
            "du_kien_bat_dau": min(moc_bat_dau) if moc_bat_dau else None,
            "du_kien_ket_thuc": max(moc_ket_thuc_hoac_bat_dau) if moc_ket_thuc_hoac_bat_dau else None,
        })
    return {"rows": rows, "total": int(total), "page": page, "page_size": page_size}
