"""Schema ra của màn "Theo dõi sản xuất" — Kanban (Task 15).

Cột Kanban KHÔNG phải hằng trong code: `meta().cot` là chính danh mục `cong_doan` + một cột "Khác"
cố định (Ruling C113, xem docstring `services/lenh_sx/bang_theo_doi.py`). FE dựng khung bảng từ
`/meta` rồi rải `card.cot` (= `str(cong_doan.id)`, hoặc `"khac"`) vào đúng cột — hai cửa PHẢI đọc
cùng một chuỗi khoá, sai lệch kiểu chuỗi/số ở một trong hai bên là board vỡ âm thầm (cột không khớp
card nào, hoặc card không khớp cột nào).

KHÔNG MỘT SỐ TIỀN NÀO — cùng ràng buộc của cả gói `services/lenh_sx/` (xem `LenhSxItem` ở
`schemas/lenh_san_xuat.py`).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class KanbanCotOut(BaseModel):
    """MỘT cột của board. `key` là chuỗi vì nó phải khớp thẳng `KanbanCardOut.cot` (cũng là chuỗi)
    — so sánh trên FE không cần ép kiểu."""

    key: str
    ten: str


class KanbanMetaOut(BaseModel):
    cot: list[KanbanCotOut] = []


class KanbanChipOut(BaseModel):
    """MỘT công việc ĐANG `running`/`paused` của lệnh. Card hiện ĐỦ danh sách này (không chỉ một
    cái): routing song song có thể chạy nhiều nhánh cùng lúc, và đếm 1 khi có 2 là bỏ sót đúng
    nhánh nặng nhất của lệnh (xem docstring `bang_theo_doi._the`).

    `may` (Vòng sửa 2 mục 5, task-16-fix2-brief.md, GN-5) — siết về `str` (không `| None`): dựng
    qua `_ten_may` (Vòng sửa 1 mục G), hàm đó KHÔNG BAO GIỜ trả `None` (máy chưa gán/đã xoá đều có
    nhãn tiếng Việt riêng). `CaViecOut.may` (dưới, mục G) đã siết trước — hai schema tả CÙNG một
    giá trị bằng hai kiểu là đúng lớp lệch mà mục G sinh ra để khử."""

    cong_viec_id: int
    ten: str | None = None
    trang_thai: str
    may: str
    nguoi: list[str] = []


class KanbanCardOut(BaseModel):
    """MỘT lệnh = MỘT card, bất kể routing của nó rẽ bao nhiêu nhánh (Ruling C113).

    `cot` là bước CHÂN SỚM NHẤT còn dang dở (hoặc bước CUỐI nếu lệnh đã xong hết) — đại diện cho
    VỊ TRÍ của card trên board; `chip_dang_chay` mới là nơi thấy ĐỦ mọi việc đang chạy."""

    lsx_id: int
    ma: str
    ten: str | None = None
    khach_hang: str | None = None
    so_luong_dat: int
    is_rush: bool = False
    han_hoan_thanh_sx: date | None = None

    cot: str
    buoc_hien_tai: str | None = None
    chip_dang_chay: list[KanbanChipOut] = []


class KanbanOut(BaseModel):
    cards: list[KanbanCardOut] = []


# --- Theo máy (Task 16) --------------------------------------------------------------------------
class LsxThamChieuOut(BaseModel):
    """MỘT lệnh mà một block đang gánh — CẶP `(lsx_id, ma)` (Task 17, Ruling C123).

    Trước Task 17 đây là `str` (chỉ mã) nên FE không có gì để bấm mở hồ sơ: nó phải đi dò ngược mã
    → id qua một lượt gọi khác, hoặc đoán. Mang cả id lẫn mã thì `ma` là mặt ĐỌC (in trên block),
    `lsx_id` là KHOÁ để mở hồ sơ — đúng luật "id không lọt ra chỗ hiện chữ".

    Một block có thể mang NHIỀU phần tử (ca in ghép phục vụ nhiều lệnh): C123 chốt là từ hai lệnh
    trở lên thì FE bày danh sách cho người dùng chọn, CẤM đoán lấy cái đầu tiên.
    """

    lsx_id: int
    ma: str


class MayLaneBlockOut(BaseModel):
    """MỘT công việc trong lane của MỘT máy. Công việc GHÉP phục vụ nhiều lệnh vẫn ra ĐÚNG MỘT
    block (khoá theo `cong_viec_id`) — `lsx` liệt kê MỌI lệnh nó phục vụ, để người điều độ biết
    block đó gánh những đơn nào (xem docstring `bang_theo_doi.theo_may`).

    `lsx` sắp theo MÃ (thứ tự ổn định giữa hai lần tải) — Task 17 đổi kiểu phần tử từ `str` sang
    `LsxThamChieuOut` nhưng GIỮ NGUYÊN tiêu chí sắp đó."""

    cong_viec_id: int
    ten: str | None = None
    trang_thai: str
    lsx: list[LsxThamChieuOut] = []
    du_kien_bat_dau: datetime | None = None
    du_kien_ket_thuc: datetime | None = None
    nguoi: list[str] = []


class MayLaneOut(BaseModel):
    """MỘT lane. `may_id=None` là lane "Chưa xếp máy" — LUÔN có mặt kể cả rỗng (khuôn `COT_KHAC`
    của Kanban): việc chưa gán máy là đúng thứ điều độ phải xử lý, không phải thứ để giấu đi.

    `ngung_dung` (Vòng sửa 1 mục H, task-16-fix1-brief.md) — máy đã `active=False` (mg 0202,
    "còn dùng hay đã thanh lý") mà CÒN ôm việc vẫn giữ NGUYÊN lane/tên, chỉ đánh dấu cho FE: giấu
    lane đi mới là mất dấu, đúng nguyên tắc của `may_id=None` ở trên.

    `blocks` RỖNG là một câu trả lời, không phải thiếu dữ liệu (Task 17, C126 mục 2): máy CÒN DÙNG
    mà không có việc nào vẫn ra lane — đó chính là câu "máy nào đang trống để nhét việc vào" mà bàn
    điều độ hỏi. Ngoại lệ (Ruling C132, vòng sửa 1 mục 4): trong bộ lane MẶC ĐỊNH, máy đã NGỪNG
    DÙNG *và* KHÔNG CÒN NỢ VIỆC thì không ra lane — nguyên tắc "đừng ẩn" bảo vệ VIỆC, không bảo vệ
    chỗ trống của máy đã thanh lý. "Còn nợ việc" ở đây xét ĐỘC LẬP với cửa sổ `tu`/`den` đang hỏi
    (Ruling C136, vòng sửa 2), cùng một vị ngữ với cờ `co_viec` của `/bo-loc` — nên một máy ngừng
    dùng có thể ra lane `blocks: []`, nghĩa là "còn nợ, nhưng không nợ trong khoảng anh đang xem".

    Ngoại lệ của ngoại lệ (Ruling C137, vòng sửa 2): `?may_id=` tường minh KHÔNG chịu C132 — luôn
    đúng MỘT lane, kể cả máy rảnh đã thanh lý, kể cả `may_id` không còn trong danh mục (nhãn "Máy
    đã xoá"). Xem `bang_theo_doi.theo_may` cho ranh giới giữa lane sinh-từ-dữ-liệu và lane
    sinh-từ-danh-mục."""

    may_id: int | None = None
    ten: str
    ngung_dung: bool = False
    blocks: list[MayLaneBlockOut] = []


class TheoMayOut(BaseModel):
    lanes: list[MayLaneOut] = []


# --- Theo ca (Task 16) ---------------------------------------------------------------------------
class CaViecOut(BaseModel):
    """`may`/`may_id` (Vòng sửa 1 mục G, task-16-fix1-brief.md) — trước `may` là `None` cho CẢ
    "chưa xếp máy" lẫn "máy đã xoá", trong khi `/theo-may` phân biệt hai thứ đó bằng hai nhãn tiếng
    Việt riêng. Nay `may` LUÔN là một chuỗi (qua `_ten_may`, không bao giờ `None`), `may_id` giữ id
    thô để so khớp (khớp hình dạng `MayLaneOut` — `may_id` để so, `ten`/`may` để bày)."""

    cong_viec_id: int
    ten: str | None = None
    trang_thai: str
    may_id: int | None = None
    may: str
    du_kien_bat_dau: datetime | None = None
    nguoi: list[str] = []


class CaOut(BaseModel):
    """MỘT ca của danh mục `work_shifts`, với việc rơi vào ĐÚNG ngày xưởng đang xem. `qua_nua_dem`
    là CỜ để FE (và bài test) nhận ra ca đêm — KHÔNG được dò theo tên (Ruling C116: xưởng khác gọi
    ca đêm là "Ca tối"/"Ca C" thì dò theo tên là bắt oan).

    `id=None` (Vòng sửa 1 mục A, CHẶN-1) là rổ "Ngoài ca" — LUÔN có mặt, đứng CUỐI danh sách `ca`:
    mọi việc mà không ca nào trong danh mục nhận (bước chạy trên MÁY không bị ràng buộc bởi tập ca;
    hoặc `work_shifts` rỗng) rơi vào đây thay vì biến mất khỏi mọi cột. `bat_dau_phut`/
    `ket_thuc_phut` là `None` cho rổ này (không phải một ca thật, không có khung giờ)."""

    id: int | None
    ten: str
    bat_dau_phut: int | None
    ket_thuc_phut: int | None
    qua_nua_dem: bool
    viec: list[CaViecOut] = []


class TheoCaOut(BaseModel):
    ca: list[CaOut] = []


# --- Gantt (Task 16) ------------------------------------------------------------------------------
class GanttRowOut(BaseModel):
    """MỘT dòng = MỘT LỆNH (Ruling C118), KHÔNG phải một công việc. Dải thời gian rút từ MIN/MAX
    mốc của mọi công việc thuộc lệnh; lệnh chưa có công việc/chưa xếp giờ (vd fixture
    `hai_muoi_lenh`) ra `None` — "chưa đủ dữ liệu thì nói chưa đủ dữ liệu", không bịa mốc."""

    lsx_id: int
    ma: str
    ten: str | None = None
    khach_hang: str | None = None
    han_hoan_thanh_sx: date | None = None
    du_kien_bat_dau: datetime | None = None
    du_kien_ket_thuc: datetime | None = None


class GanttOut(BaseModel):
    rows: list[GanttRowOut] = []
    total: int
    page: int
    page_size: int


# --- Bộ lọc chung của màn (Task 17, Ruling C121) --------------------------------------------------
class BoLocMucOut(BaseModel):
    """MỘT ô chọn trong thanh lọc. `ten` là mặt ĐỌC (tiếng Việt CÓ DẤU), `id` chỉ để SO KHỚP —
    đem gán thẳng vào tham số lọc cùng tên trên `/kanban` và `/theo-may`.

    `id` là CHUỖI cho MỌI nhóm facet, kể cả nhóm mà cột dưới DB là số (máy, công đoạn, khách,
    công nhân) — cùng lý do `KanbanCotOut.key` là chuỗi: FE so khớp một kiểu duy nhất, không phải
    nhớ nhóm nào số nhóm nào chữ. FastAPI tự ép về `int` ở những tham số khai kiểu số."""

    id: str
    ten: str


class BoLocMayMucOut(BoLocMucOut):
    """Ô chọn MÁY — thêm cờ `ngung_dung` (`may_thiet_bi.active=False`, mg 0202) và cờ `co_viec`.

    Danh sách này là DANH MỤC máy, KHÔNG phải "máy có việc": nó vừa là nguồn của ô lọc vừa là
    KHUNG LANE của `/theo-may` (C126 mục 2 — máy đang rảnh phải có lane). Nên khác
    `/api/lenh-san-xuat/bo-loc`, ở đây một mục CÓ THỂ lọc ra rỗng — và rỗng là câu trả lời đúng
    ("máy này đang trống").

    `co_viec` (Vòng sửa 1 mục 5, Ruling C133) — máy có ÍT NHẤT MỘT công việc CHƯA HOÀN THÀNH
    thuộc lệnh ĐÃ PHÁT HÀNH trong phạm vi người gọi, tức ĐÚNG phạm vi mà `/theo-may` vẽ khi KHÔNG
    truyền `tu`/`den`. Nói khác đi: `co_viec=true` ⇔ lane của máy đó trên `/theo-may` (không lọc,
    không cửa sổ) có ít nhất một block. Cờ KHÔNG xét cửa sổ thời gian — truyền `?tu`/`?den` hẹp
    lại thì một máy `co_viec=true` vẫn có thể ra lane rỗng.

    Đây là GỢI Ý hiển thị, KHÔNG phải bộ lọc: FE dùng nó để làm mờ/cảnh báo những máy sẽ cho bảng
    TRẮNG ở tab Kanban, nhưng máy rảnh vẫn PHẢI chọn được ở tab Theo máy — "máy nào đang trống để
    nhét việc vào" là câu hỏi chính của tab đó."""

    ngung_dung: bool = False
    co_viec: bool = False


class BoLocOut(BaseModel):
    """Nguồn của thanh lọc — endpoint RIÊNG của màn này, gác `theo_doi_san_xuat:read`.

    CẤM mượn `/api/lenh-san-xuat/bo-loc` (Ruling C121): endpoint kia gác ô quyền `lenh_san_xuat`,
    và repo đã có sẵn vết thương đúng kiểu đó ghi ở `frontend/src/api/client.ts:10755-10758`.

    `ca` có mặt để FE dựng ô chọn CA cho tab "Theo ca" (Task 18) — nhưng `/kanban` và `/theo-may`
    KHÔNG nhận tham số `ca_id`: xếp một công việc vào ca là phép tính Python trên mốc giờ tường
    (`bang_theo_doi._ca_cua_moc`, có nhánh qua nửa đêm), không có mệnh đề `WHERE` nào diễn đạt
    được nó trong MỘT lượt truy vấn. Xem `bang_theo_doi.bo_loc` cho danh sách những gì đã BỎ."""

    may: list[BoLocMayMucOut] = []
    cong_nhan: list[BoLocMucOut] = []
    cong_doan: list[BoLocMucOut] = []
    nhom_cong_doan: list[BoLocMucOut] = []
    ca: list[BoLocMucOut] = []
    trang_thai_viec: list[BoLocMucOut] = []
    uu_tien: list[BoLocMucOut] = []
    khach_hang: list[BoLocMucOut] = []
