"""Nạp bối cảnh theo LÔ cho Lệnh SX & Theo dõi SX (Task 6 của loạt).

Hai màn đọc sắp dựng (Lệnh SX, Theo dõi SX) phải hiện được ~200 lệnh MỘT TRANG. Nếu mỗi lệnh tự
đi vấn thêm đơn/khách/công việc/phiên chạy... thì 200 lệnh ra 200×N câu SQL — trang danh sách sập.
`nap()` là TẦNG NẠP DỮ LIỆU DUY NHẤT mọi thứ phía sau (tiến độ, trạng thái, API, UI) phải đi qua:
MỘT câu `select(...).where(<cột>.in_(ids))` cho MỖI bảng nguồn, gom kết quả vào dict bằng Python —
KHÔNG vòng lặp gọi DB. Số câu SQL của `nap()` KHÔNG phụ thuộc `len(lsx_ids)` (đo bằng
`tests/test_lenh_sx_boi_canh.py::test_khong_n_plus_1`).

21 câu, mỗi câu một dòng (bảng — cột lọc — khoá dict kết quả):
  1.  Lsx                       id IN ids                                   -> lenh[lsx_id]
  2.  Order                     id IN {lenh.order_id}                       -> don[order_id]
  3.  Customer                  id IN {don.customer_id}                     -> khach[customer_id]
  4.  User                      id IN {don.sale_user_id}                    -> sale[user_id]
  5.  SanXuatCongViec           lsx_id IN ids                               -> cong_viec[lsx_id] (list)
  5b. BaiGhepCongDoanMap        lsx_id IN ids                               -> (cầu bước ↔ bước chung)
  5c. LsxCongDoan               lsx_id IN ids                               -> (cầu (lsx,step_key) → id)
  5d. SanXuatCongViec           bai_ghep_cong_doan_id IN {5b}               -> cong_viec_ghep[lsx_id] (list)
                                                                            + buoc_phu[cong_viec_id] (list)
  5e. SanXuatNhomLsx            lsx_id IN ids                               -> (cầu lệnh ↔ nhóm)
  6.  SanXuatPhienChay          cong_viec_id IN {cong_viec.id ∪ ghép}       -> phien[cong_viec_id] (list)
  7.  SanXuatBatch              cong_viec_id IN {cong_viec.id ∪ ghép}       -> batch[cong_viec_id] (list)
  8.  SanXuatKcsBatch           cong_viec_id IN {cong_viec.id ∪ ghép}       -> kcs[cong_viec_id] (list)
  9.  SanXuatKhoLot             lsx_id IN ids                               -> lot[lsx_id] (list)
  10. YeuCauSuaChua             lsx_id IN ids OR cong_viec_id IN {5+5d}     -> su_co[lsx_id] (list)
  11. DeliveryRequestLine       order_line_id IN {lenh.order_line_id}       -> giao[order_line_id] (list)
  11b.DeliveryTripLine JOIN DeliveryTrip, lọc order_line_id IN {lenh.order_line_id}
                                + trip.trang_thai IN LAN_GIAO_CO_HANG_DEN_TAY
                                                                            -> da_giao[order_line_id] (int)
  12. SanXuatNhapKhoYc OUTER JOIN SanXuatKcsBatch ON kcs_batch_id OUTER JOIN SanXuatCongViec ON
                                cong_viec_id, lọc cong_viec.lsx_id IN ids OR yc.nhom_id IN {5e}
                                                                            -> nhap_kho_yc[lsx_id] (list)
  13. LsxCongDoanPhuThuoc JOIN LsxCongDoan (buoc_sau) ON buoc_sau_id, lọc LsxCongDoan.lsx_id IN ids
                                                                             -> phu_thuoc_buoc[lsx_id] (list cạnh)
  14. SanXuatNhom               id IN {cong_viec.nhom_id ∪ ghép}            -> nhom[nhom_id]
  15. MayThietBi                id IN {cong_viec.may_id} ∪ {phien.may_id}
                                     ∪ {su_co.may_id}                        -> may[may_id]
  16. SanXuatPhanCong JOIN Employee, cong_viec_id IN {cong_viec.id ∪ ghép}
                                + trang_thai = 'active'                     -> phan_cong[cong_viec_id] (list)
                                                                            + nhan_su[employee_id]

VÌ SAO `cong_viec` MỘT MÌNH LÀ KHÔNG ĐỦ (ba câu 5b/5c/5d): bước bị BÀI GHÉP phủ KHÔNG đẻ công việc
riêng — nó đẻ MỘT công việc CHUNG mang `lsx_id = None` + `bai_ghep_cong_doan_id`
(`services/san_xuat/snapshot.py:78-110`). Lọc `SanXuatCongViec.lsx_id IN ids` bỏ sót đúng bước
NẶNG NHẤT của lệnh (ca in ghép). Hậu quả đo được ở tầng tính: chuỗi tuần tự vỡ thành nhánh song
song (mọi cạnh chạm bước ghép bị bỏ) nên đường găng lấy `max` thay vì `sum`; lệnh mà MỌI bước đều
bị phủ thì `cong_viec[lsx_id]` RỖNG và tiến độ trả 0% một cách TỰ TIN. Đây là lỗi ra SỐ SAI mà
không gãy gì — không thể vá ở tầng trên vì thời lượng bước ghép nằm ở công việc chung, không có
bản sao nào bên lệnh.

Cầu nối phải đi ba chặng vì hai đầu neo bằng hai thứ khác nhau: công việc chung neo
`bai_ghep_cong_doan_id`, còn bảng phủ `bai_ghep_cong_doan_map` neo bước của lệnh bằng
`lsx_step_key` (KHÔNG bằng `lsx_cong_doan.id` — `models/bai_ghep_cong_doan.py:146-151`: sửa
routing là replace-all nên id tái sinh). Mà cạnh phụ thuộc (câu 13) lại là cặp `lsx_cong_doan.id`.
Nên: 5b lấy bộ ba `(bai_ghep_cong_doan_id, lsx_id, lsx_step_key)`, 5c dựng
`(lsx_id, step_key) → lsx_cong_doan.id`, 5d lấy công việc chung. Ghép ba thứ lại ra `buoc_phu`.

Vì sao gộp `nhom`/`may`/`nhan_su` vào ĐÂY: `cong_viec.may_id`/`phien.may_id`/`su_co.may_id` là
SOFT-REF (Integer, không FK — máy có thể đã bị xoá khỏi danh mục), `cong_viec.nhom_id` và
`phan_cong.employee_id` chỉ là id. Nếu để service/UI phía sau tự lấy tên máy/tên nhóm/tên người
theo từng id đọc được, đó đúng là kiểu N+1 mà file này sinh ra để chặn — nên nạp một lần ở đây,
kèm luôn 3 câu 14-16. Vòng sửa 1 của Task 9 đã phải gỡ một hàm tra tên máy bù ở tầng danh sách
đúng vì lý do này: một đường tra, không hai.

Khoá theo FK THẬT của từng bảng — không đoán, không suy diễn:
  - `cong_viec.lsx_id` NULLABLE (`ondelete=SET NULL`, `models/san_xuat.py:205`) — có cong việc
    thuộc BÀI GHÉP chứ không thuộc lsx nào. KHÔNG cần lọc tay: `WHERE lsx_id IN (ids)` tự loại
    NULL (NULL không khớp bất kỳ giá trị nào trong mệnh đề IN), nên không có đường nổ ở đây.
  - `giao` KHÔNG khoá được theo `lsx_id` — `delivery_request_lines` (`models/delivery.py:163`)
    chỉ có `request_id` + `order_line_id`, không có cột nào trỏ lsx. Cầu duy nhất là
    `lsx.order_line_id == delivery_request_lines.order_line_id`.
    `order_line_id` KHÔNG unique trên `lsx` — một dòng đơn có thể sinh lệnh bổ sung/bù/làm lại
    trỏ `lsx_goc_id` về lệnh gốc (pha sau, xem docstring `Lsx.lsx_goc_id`). Hôm nay 1 dòng đơn = 1
    lsx nên gộp theo `order_line_id` vẫn đúng; ngày lệnh-bù ra đời, hai lệnh cùng một dòng đơn sẽ
    CÙNG đọc trọn số đã giao của dòng đó qua map này — bên dùng map (task tiến độ) phải tự chia,
    KHÔNG phải việc của tầng nạp này.
    `giao` là map DUY NHẤT trong 9 map danh sách toàn ánh trên `order_line_id` thay vì `lsx_id` —
    mà cả hai đều là int tự tăng CÙNG khoảng giá trị, nên `giao[lsx_id]` không nổ `KeyError`, nó
    ÂM THẦM trả nhầm dòng của lệnh khác trùng số (Vòng sửa 1, review Task 6). Dùng
    `BoiCanh.giao_cua(lsx_id)` thay vì đánh chỉ số `giao` trực tiếp trừ khi thật sự cần khoá theo
    dòng đơn (vd. gộp giao hàng của nhiều lsx cùng dòng).
  - `nhap_kho_yc` (`SanXuatNhapKhoYc`, `models/san_xuat_kho.py:160`) không có cột `lsx_id` — đi
    bằng HAI cầu OR trong cùng một câu, vì "đã nhập kho" là sự thật cấp NHÓM chứ không cấp lệnh:
      · cầu BATCH: `kcs_batch_id` → `san_xuat_kcs_batch.cong_viec_id` → `san_xuat_cong_viec.lsx_id`;
      · cầu NHÓM: `SanXuatNhapKhoYc.nhom_id` ∈ nhóm mà lệnh là thành viên (câu 5e).
    ĐỪNG bắc cầu qua registry `san_xuat_kho_hang.lsx_id` (bản Task 6 làm vậy, SỬA ở Task 8): hàng
    THÀNH PHẨM luôn có `lsx_id IS NULL` vì `kho._get_or_create_hang` được gọi với `lsx_id=None`
    cứng (`services/san_xuat/kho.py:132`) — thành phẩm thuộc NHÓM ("Ruột + Bìa → Kỷ yếu"), không
    thuộc một lệnh. Cầu cũ nối được ĐÚNG 0 dòng trên dữ liệu thật, và im lặng: map luôn rỗng, không
    lỗi, không dấu hiệu. Bài canh của Task 6 xanh vì fixture tự tay đặt `hang.lsx_id = lsx_id` —
    một giá trị production không bao giờ ghi.
    VÌ SAO PHẢI CÓ CẦU NHÓM (Vòng sửa 1): một nhóm có thể gồm NHIỀU lệnh (Ruột + Bìa), mà
    `snapshot.danh_dau_kcs_cuoi:137-171` chỉ đánh `la_kcs_cuoi` cho ĐÚNG MỘT ứng viên mỗi nhóm ⇒
    yêu cầu nhập kho chỉ sinh được từ batch của THÂN CHÍNH. Đi mình cầu batch thì lệnh thành viên
    còn lại có `nhap_kho_yc` rỗng VĨNH VIỄN và kẹt ở tab Đang SX dù hàng đã nằm trong kho.
    CẦU NHÓM CHE ĐỦ 100% (chốt ở Vòng sửa 2, không còn là suy đoán): `SanXuatNhapKhoYc` chỉ được
    dựng ở MỘT chỗ (`kho.py:139`), và chỗ đó raise khi `kcs.nhom_id` NULL ⇒ MỌI dòng yc đều có
    `nhom_id`. Ghép trong cùng một nhóm thì cầu nhóm với tới; ghép bắc qua nhiều nhóm thì công việc
    chung có `nhom_id` NULL nên KHÔNG có yc nào ra đời để mà hụt. Hệ quả: cầu BATCH nay là TẬP CON
    của cầu nhóm, giữ lại chỉ để dự phòng dữ liệu trôi (yc có `nhom_id` trỏ vào nhóm mà lệnh không
    còn là thành viên). Không cần vá gì thêm ở đây, kể cả nếu bộ lọc `NHOM_PRINT` ở
    `app/services/bai_ghep_service.py:109` được nới ra.
    Nạp NGUYÊN TRẠNG, không lọc theo `trang_thai` — đây là tầng nạp, luật đọc thuộc về bên dùng.
    ⚠️ ĐỪNG CỘNG QUA CÁC LỆNH: nhiều lệnh cùng nhóm cùng đọc CHUNG một tập yc (cùng object, cùng
    id). Cộng `so_luong_xac_nhan` qua các lệnh của một trang là nhân số thật lên đúng bằng số thành
    viên nhóm. Map này trả lời "nhóm của lệnh đã có hàng vào kho chưa", KHÔNG trả lời "lệnh này
    đóng góp bao nhiêu" — muốn con số per-lệnh thì phải chia ở tầng khác, cùng kiểu cảnh báo mà
    `tien_do.gio_may` đã ghi cho phiên của bước ghép.
  - `su_co` cũng đi HAI đường OR: `lsx_id IN ids` và `cong_viec_id IN {cv_ids}`.
    `su_co.bao_su_co` (`services/san_xuat/su_co.py:118-120`) ghi `lsx_id = cv.lsx_id` — NULL khi
    sự cố báo trên một bước bị bài ghép phủ — nhưng luôn ghi `cong_viec_id`. Đi mình đường `lsx_id`
    thì sự cố của ca in ghép không về được lệnh nào và im lặng biến mất.
    QUYẾT ĐỊNH (không phải hệ quả hiển nhiên): sự cố trên công việc GHÉP giương cờ cho MỌI lệnh
    trong ca. Ca in ghép hỏng máy thì mọi lệnh nằm trên tờ in ấy đều đứng — báo cho một lệnh và
    giấu với các lệnh còn lại mới là sai. Đổi lại, cùng một sự cố xuất hiện ở nhiều dòng bảng.
  - `da_giao` là map SỐ (không phải danh sách): số khách ĐÃ THỰC NHẬN của dòng đơn. Đọc từ
    `delivery_trip_lines.qty_giao` (`models/delivery.py:294`) qua chuyến có trạng thái trong
    `LAN_GIAO_CO_HANG_DEN_TAY` (`:79-80`), bám khuôn `delivery_repo.da_giao_theo_dong:123-138`.
    KHÁC `giao[...]` — `qty` ở đó (`:163`) là số YÊU CẦU giao, lập phiếu xong là có ngay dù xe
    chưa chạy. Dùng hằng có sẵn thay vì liệt kê trạng thái loại trừ: danh sách tay sót `hen_lai`
    (ngưng dùng nhưng dòng cũ còn đọc được) và lệch ngay lần bên giao hàng thêm trạng thái.
  - `lot` khoá theo `SanXuatKhoLot.lsx_id`, mà cột đó CHỈ được ghi cho lot BTP
    (`kho.phan_loai_btp_du`); lot THÀNH PHẨM (`kho.kho_xac_nhan_nhap`) để trống nó. Nên
    `lot[lsx_id]` là "lot BTP của lệnh", KHÔNG phải "tồn thành phẩm của lệnh" — muốn tồn thành
    phẩm thì đọc `nhap_kho_yc[...].so_luong_xac_nhan`.
  - `phu_thuoc_buoc` lấy từ `lsx_cong_doan_phu_thuoc` (`models/lsx.py:349`), khoá theo `lsx_id`
    CỦA BƯỚC SAU (`buoc_sau_id`) — cạnh (`buoc_truoc_id`, `buoc_sau_id`) dùng để tính đường găng ở
    task tiến độ (phía sau). ĐỪNG nhầm với bảng `san_xuat_phu_thuoc` — đó là cạnh phụ thuộc CHÉO
    giữa HAI LSX cùng nhóm (snapshot bước ghép, `models/san_xuat.py:251-255`), khác hoàn toàn.
  - `cong_viec.may_id` / `phien.may_id` / `su_co.may_id` là SOFT-REF Integer (không FK) — máy có
    thể đã bị xoá khỏi danh mục; `may` map chỉ chứa những id CÒN TỒN TẠI trong `may_thiet_bi`, id
    trỏ hụt đơn giản vắng mặt trong dict, không có đường nổ.
  - `phan_cong` CHỈ gồm dòng `trang_thai='active'`. Rút người giữ lại dòng `removed` để có lịch sử
    (`thuc_thi.go_phan_cong:211`); ai cần lịch sử thì đọc bảng, đừng nới điều kiện ở đây — bảng
    điều độ hiện tên người đã bị rút là chỉ sai người, mà không gãy gì để ai biết.

Hai HẠNG map:
  - Map DANH SÁCH (`cong_viec`, `cong_viec_ghep`, `phien`, `batch`, `kcs`, `lot`, `su_co`, `giao`,
    `nhap_kho_yc`, `phu_thuoc_buoc`, `buoc_phu`) đều TOÀN ÁNH trên miền khoá tự nhiên của chúng:
    mọi khoá thuộc miền đó LUÔN có mặt trong dict, trỏ tới `[]` khi không có dòng nào — để bên
    dùng đọc thẳng `bc.cong_viec[lsx_id]` mà KHÔNG phải viết `.get(id, [])` ở khắp nơi.
    (`buoc_phu` toàn ánh trên id của CÔNG VIỆC GHÉP, không phải trên mọi công việc: đọc nó bằng id
    công việc riêng là lỗi lập trình, để `KeyError` bật lên.)
  - Map ĐỐI TƯỢNG ĐƠN (`lenh`, `don`, `khach`, `sale`, `nhom`, `may`, `nhan_su`) thì THƯA: vắng
    mặt nghĩa là không tìm thấy (FK NULL, hoặc bản ghi đã bị xoá/soft-ref trỏ hụt).
    (`phan_cong` thuộc hạng DANH SÁCH, toàn ánh trên id công việc như `phien`/`batch`/`kcs`.)
  (`da_giao` là map SỐ, toàn ánh trên `order_line_id` như `giao`, thiếu dòng ⇒ `0`.)
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...models.bai_ghep_cong_doan import BaiGhepCongDoanMap
from ...models.customer import Customer
from ...models.delivery import (
    LAN_GIAO_CO_HANG_DEN_TAY, DeliveryRequestLine, DeliveryTrip, DeliveryTripLine,
)
from ...models.employee import Employee
from ...models.ky_thuat_may import YeuCauSuaChua
from ...models.lsx import Lsx, LsxCongDoan, LsxCongDoanPhuThuoc
from ...models.may_thiet_bi import MayThietBi
from ...models.order import Order
from ...models.san_xuat import SanXuatCongViec, SanXuatNhom, SanXuatNhomLsx
from ...models.san_xuat_kcs import SanXuatKcsBatch
from ...models.san_xuat_kho import SanXuatKhoLot, SanXuatNhapKhoYc
from ...models.san_xuat_san_luong import SanXuatBatch
from ...models.san_xuat_thuc_thi import PC_HOAT_DONG, SanXuatPhanCong, SanXuatPhienChay
from ...models.user import User


@dataclass
class BoiCanh:
    """Kết quả một lần `nap()`. Xem docstring module cho đầy đủ 21 câu SQL + lý do từng khoá."""

    lenh: dict[int, Lsx]
    don: dict[int, Order]
    khach: dict[int, Customer]
    sale: dict[int, User]
    cong_viec: dict[int, list[SanXuatCongViec]]
    cong_viec_ghep: dict[int, list[SanXuatCongViec]]
    buoc_phu: dict[int, list[int]]
    phien: dict[int, list[SanXuatPhienChay]]
    batch: dict[int, list[SanXuatBatch]]
    kcs: dict[int, list[SanXuatKcsBatch]]
    lot: dict[int, list[SanXuatKhoLot]]
    su_co: dict[int, list[YeuCauSuaChua]]
    giao: dict[int, list[DeliveryRequestLine]]
    da_giao: dict[int, int]
    nhom: dict[int, SanXuatNhom]
    may: dict[int, MayThietBi]
    phan_cong: dict[int, list[SanXuatPhanCong]]
    nhan_su: dict[int, Employee]
    phu_thuoc_buoc: dict[int, list[tuple[int, int]]]
    nhap_kho_yc: dict[int, list[SanXuatNhapKhoYc]]

    def giao_cua(self, lsx_id: int) -> list[DeliveryRequestLine]:
        """Dòng giao hàng của MỘT lệnh. Dùng cái này, đừng đánh chỉ số `giao` trực tiếp —
        `giao` khoá theo `order_line_id`, mà `lsx.id` trùng khoảng giá trị với nó (cả hai đều
        int tự tăng cùng khoảng) nên `giao[lsx_id]` sẽ ÂM THẦM trả nhầm dòng đơn khác thay vì
        báo `KeyError` — sai dữ liệu hiển thị, không dấu hiệu nào (Vòng sửa 1, review Task 6).

        Lệnh không có trong bối cảnh (id ngoài tập đã `nap()`) để `KeyError` bật lên tự nhiên từ
        `self.lenh[lsx_id]` — đó là lỗi lập trình thật, không nuốt thành `[]`.
        """
        return self.giao[self.lenh[lsx_id].order_line_id]

    def da_giao_cua(self, lsx_id: int) -> int:
        """Số khách ĐÃ THỰC NHẬN của dòng đơn mà lệnh này thuộc về.

        KHÁC `giao_cua()`: `delivery_request_lines.qty` là số YÊU CẦU giao (`models/delivery.py:163`),
        còn số thực nhận nằm ở `delivery_trip_lines.qty_giao` (`:294`) và chỉ tính qua các chuyến
        trong `LAN_GIAO_CO_HANG_DEN_TAY`. Lập yêu cầu giao xong mà xe chưa chạy — hoặc chạy mà
        thất bại — thì con số này vẫn là 0.

        Cùng cảnh báo với `giao_cua`: nhiều lệnh cùng một dòng đơn (lệnh bù, pha sau) sẽ CÙNG đọc
        trọn số của dòng đó; bên dùng phải tự chia.
        """
        return self.da_giao[self.lenh[lsx_id].order_line_id]

    def cong_viec_du(self, lsx_id: int) -> list[SanXuatCongViec]:
        """Công việc RIÊNG của lệnh + công việc BÀI GHÉP phủ bước của lệnh.

        Dùng cái này, đừng đọc thẳng `cong_viec[...]` trừ khi thật sự chỉ cần phần riêng: bước bị
        bài ghép phủ nằm ở công việc CHUNG (`lsx_id = None`) nên `cong_viec[lsx_id]` thiếu đúng
        bước nặng nhất của lệnh, và thiếu một cách IM LẶNG — không `KeyError`, không dấu hiệu gì.

        Một công việc chung có thể phủ NHIỀU bước của cùng lệnh; `cong_viec_ghep` đã khử trùng nên
        danh sách trả về không có bản ghi lặp.
        """
        return self.cong_viec[lsx_id] + self.cong_viec_ghep[lsx_id]

    def nguoi_cua(self, cong_viec_id: int) -> list[str]:
        """TÊN những người ĐANG được giao ở một công việc, theo thứ tự giao.

        Trả tên chứ không trả id vì mọi nơi tiêu thụ (cột "Máy/người", hồ sơ chi tiết) đều cần tên;
        ai cần id thì đọc thẳng `phan_cong[...]`. KHÔNG đụng `la_luong_khoan` — đó là ảnh chụp chế
        độ lương, và cả loạt màn này cấm mọi thứ dính lương/tiền.

        Không ai được giao ⇒ `[]`. Đừng bịa "chưa phân công" ở tầng này: đó là việc của UI.

        Tra THẲNG `phan_cong[...]`, không `.get(..., [])`: map này TOÀN ÁNH trên `cv_ids` đúng như
        `phien`/`batch`/`kcs`, nên `KeyError` ở đây nghĩa là người gọi đưa một công việc KHÔNG
        thuộc lô vừa nạp — đó là lỗi lập trình, phải nổ chứ không được lặng lẽ trả "không ai làm".
        Ngược lại `nhan_su` là map THƯA (chỉ có nhân viên thật sự xuất hiện) nên chỗ đó `.get` là
        đúng — hai hạng map, hai cách tra, xem docstring module.
        """
        return [
            emp.full_name
            for pc in self.phan_cong[cong_viec_id]
            if (emp := self.nhan_su.get(pc.employee_id)) is not None
        ]


def _rong() -> BoiCanh:
    return BoiCanh(
        lenh={}, don={}, khach={}, sale={}, cong_viec={}, cong_viec_ghep={}, buoc_phu={},
        phien={}, batch={}, kcs={}, lot={}, su_co={}, giao={}, da_giao={}, nhom={}, may={},
        phan_cong={}, nhan_su={}, phu_thuoc_buoc={}, nhap_kho_yc={},
    )


def nap(db: Session, lsx_ids: list[int]) -> BoiCanh:
    """Nạp bối cảnh của TẬP `lsx_ids` bằng đúng 21 câu SQL, bất kể tập có 1 hay 200 phần tử, và bất
    kể các lệnh có bài ghép hay không (ba câu bài ghép chạy VÔ ĐIỀU KIỆN — `IN ()` rỗng vẫn là một
    câu; rẽ nhánh theo dữ liệu thì số câu đổi theo nội dung và bài canh N+1 mất nghĩa).

    Danh sách bảng + lý do gom từng khoá: xem docstring module. Đầu vào rỗng trả bối cảnh rỗng
    ngay, KHÔNG đụng DB câu nào (khỏi tốn round-trip cho trang không có gì để hiện).
    """
    ids = set(lsx_ids)
    if not ids:
        return _rong()

    # 1) lenh — Lsx.id IN ids.
    lenh: dict[int, Lsx] = {
        l.id: l for l in db.execute(select(Lsx).where(Lsx.id.in_(ids))).scalars()
    }
    order_ids = {l.order_id for l in lenh.values()}
    order_line_ids = {l.order_line_id for l in lenh.values()}

    # 2) don — Order.id IN {lenh.order_id}.
    don: dict[int, Order] = {
        o.id: o for o in db.execute(select(Order).where(Order.id.in_(order_ids))).scalars()
    }
    customer_ids = {o.customer_id for o in don.values() if o.customer_id is not None}
    sale_user_ids = {o.sale_user_id for o in don.values() if o.sale_user_id is not None}

    # 3) khach — Customer.id IN {don.customer_id}.
    khach: dict[int, Customer] = {
        c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(customer_ids))).scalars()
    }

    # 4) sale — User.id IN {don.sale_user_id}.
    sale: dict[int, User] = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(sale_user_ids))).scalars()
    }

    # 5) cong_viec — SanXuatCongViec.lsx_id IN ids. Toàn ánh trên `ids` (xem docstring: NULL tự bị
    # `IN` loại, không cần lọc tay).
    cv_rows = list(
        db.execute(select(SanXuatCongViec).where(SanXuatCongViec.lsx_id.in_(ids))).scalars()
    )
    cong_viec: dict[int, list[SanXuatCongViec]] = {i: [] for i in ids}
    for cv in cv_rows:
        cong_viec[cv.lsx_id].append(cv)

    # 5b) Bảng PHỦ của bài ghép — bước nào của lệnh nào bị dòng chung nào đè. Neo bằng
    # `lsx_step_key`, nên còn phải bắc cầu qua câu 5c mới ra `lsx_cong_doan.id`.
    map_rows = list(
        db.execute(
            select(BaiGhepCongDoanMap).where(BaiGhepCongDoanMap.lsx_id.in_(ids))
        ).scalars()
    )
    bgcd_ids = {m.bai_ghep_cong_doan_id for m in map_rows}

    # 5c) Cầu `(lsx_id, step_key) → lsx_cong_doan.id` — để `buoc_phu` nói cùng ngôn ngữ với cạnh
    # phụ thuộc ở câu 13 (vốn là cặp `lsx_cong_doan.id`).
    buoc_theo_khoa: dict[tuple[int, str], int] = {
        (lsx_id, step_key): cd_id
        for cd_id, lsx_id, step_key in db.execute(
            select(LsxCongDoan.id, LsxCongDoan.lsx_id, LsxCongDoan.step_key)
            .where(LsxCongDoan.lsx_id.in_(ids))
        ).all()
    }

    # 5d) Công việc CHUNG của bài ghép (`lsx_id IS NULL`) — câu 5 không với tới được.
    # KHÔNG lọc `phien_ban_so` — CÓ Ý THỨC, chủ dự án đã phán giữ nguyên. Câu 5 (công việc riêng
    # của lệnh) cũng không lọc; lọc một câu mà bỏ câu kia mới là chỗ đẻ lệch, vì cùng một lệnh sẽ
    # thấy bước riêng của mọi phiên bản nhưng bước ghép chỉ của một phiên. Khi nào phát-hành-cập-
    # nhật đẻ phiên bản mới (spec §4.3, hiện CHƯA làm — `release.py` gặp gói hiệu lực thì trả lại
    # gói cũ) thì lọc CẢ HAI câu cùng lúc.
    cv_ghep_rows = list(
        db.execute(
            select(SanXuatCongViec).where(SanXuatCongViec.bai_ghep_cong_doan_id.in_(bgcd_ids))
        ).scalars()
    )
    cv_ghep_theo_bgcd: dict[int, list[SanXuatCongViec]] = {}
    for cv in cv_ghep_rows:
        cv_ghep_theo_bgcd.setdefault(cv.bai_ghep_cong_doan_id, []).append(cv)

    cong_viec_ghep: dict[int, list[SanXuatCongViec]] = {i: [] for i in ids}
    buoc_phu: dict[int, list[int]] = {cv.id: [] for cv in cv_ghep_rows}
    for m in map_rows:
        for cv in cv_ghep_theo_bgcd.get(m.bai_ghep_cong_doan_id, []):
            # Một dòng chung phủ nhiều bước của CÙNG một lệnh ⇒ khử trùng (`cong_viec_du` hứa
            # danh sách không lặp). Dùng so-sánh-theo-id chứ không `in` trên list ORM cho rẻ.
            if all(x.id != cv.id for x in cong_viec_ghep[m.lsx_id]):
                cong_viec_ghep[m.lsx_id].append(cv)
            cd_id = buoc_theo_khoa.get((m.lsx_id, m.lsx_step_key))
            # Bước đã bị xoá/tái sinh id (routing sửa sau khi gộp bài) ⇒ không bắc được cầu; bỏ
            # qua, KHÔNG đoán. Công việc chung vẫn nằm trong `cong_viec_ghep` nên thời lượng của
            # nó không mất, chỉ mất phần nối cạnh của riêng bước đó.
            if cd_id is not None and cd_id not in buoc_phu[cv.id]:
                buoc_phu[cv.id].append(cd_id)

    # `cv_ids` PHẢI gồm cả công việc ghép: `phien`/`batch`/`kcs` là map TOÀN ÁNH trên tập này, thiếu
    # là `bc.phien[cv.id]` nổ `KeyError` ngay khi tầng tính chạm bước ghép.
    cv_ids = [cv.id for cv in cv_rows] + [cv.id for cv in cv_ghep_rows]
    nhom_ids = {
        cv.nhom_id for cv in (cv_rows + cv_ghep_rows) if cv.nhom_id is not None
    }
    # Máy của CÔNG VIỆC — hạt giống của câu 15. Phải có mặt ở đây chứ không chỉ `phien.may_id`:
    # bước đã xếp máy mà CHƯA ai bấm chạy không có phiên nào, mà đó lại là trạng thái phổ biến
    # nhất của một lệnh vừa phát hành. Thiếu nó thì cột "Máy" của bảng lệnh trống đúng lúc điều độ
    # cần nó nhất. Bài canh: `test_may_lay_duoc_khi_chua_co_phien_nao`.
    may_ids = {cv.may_id for cv in (cv_rows + cv_ghep_rows) if cv.may_id is not None}
    # `lenh_theo_cv` = cầu NGƯỢC công việc → những lệnh dùng nó. Một công việc GHÉP phục vụ nhiều
    # lệnh, nên đây là quan hệ nhiều-nhiều, không phải `cv.lsx_id`.
    lenh_theo_cv: dict[int, list[int]] = {}
    for i in ids:
        for cv in cong_viec[i] + cong_viec_ghep[i]:
            lenh_theo_cv.setdefault(cv.id, []).append(i)

    # 5e) Thành viên NHÓM thành phẩm — `san_xuat_nhom_lsx.lsx_id` IN ids. Cần cho câu 12: "đã nhập
    # kho" là sự thật cấp NHÓM, không cấp lệnh (xem docstring).
    # CÂU NÀY GỘP ĐƯỢC vào câu 12 bằng một subquery (ra 19 câu) — giữ tách là LỰA CHỌN: một SELECT
    # phẳng đọc và sửa dễ hơn một câu 12 đã có sẵn hai OUTER JOIN cộng thêm subquery lồng. Cái
    # phải giữ là bất biến "số câu không đổi theo `len(lsx_ids)`", không phải con số 20.
    thanh_vien_rows = list(
        db.execute(select(SanXuatNhomLsx).where(SanXuatNhomLsx.lsx_id.in_(ids))).scalars()
    )
    lsx_theo_nhom: dict[int, list[int]] = {}
    for tv in thanh_vien_rows:
        lsx_theo_nhom.setdefault(tv.nhom_id, []).append(tv.lsx_id)

    # 6) phien — SanXuatPhienChay.cong_viec_id IN {cong_viec.id}. Toàn ánh trên `cv_ids`.
    phien_rows = list(
        db.execute(
            select(SanXuatPhienChay).where(SanXuatPhienChay.cong_viec_id.in_(cv_ids))
        ).scalars()
    )
    phien: dict[int, list[SanXuatPhienChay]] = {i: [] for i in cv_ids}
    for p in phien_rows:
        phien[p.cong_viec_id].append(p)
    may_ids |= {p.may_id for p in phien_rows if p.may_id is not None}

    # 7) batch — SanXuatBatch.cong_viec_id IN {cong_viec.id}.
    batch_rows = list(
        db.execute(select(SanXuatBatch).where(SanXuatBatch.cong_viec_id.in_(cv_ids))).scalars()
    )
    batch: dict[int, list[SanXuatBatch]] = {i: [] for i in cv_ids}
    for b in batch_rows:
        batch[b.cong_viec_id].append(b)

    # 8) kcs — SanXuatKcsBatch.cong_viec_id IN {cong_viec.id}.
    kcs_rows = list(
        db.execute(select(SanXuatKcsBatch).where(SanXuatKcsBatch.cong_viec_id.in_(cv_ids))).scalars()
    )
    kcs: dict[int, list[SanXuatKcsBatch]] = {i: [] for i in cv_ids}
    for k in kcs_rows:
        kcs[k.cong_viec_id].append(k)

    # 9) lot — SanXuatKhoLot.lsx_id IN ids.
    lot_rows = list(
        db.execute(select(SanXuatKhoLot).where(SanXuatKhoLot.lsx_id.in_(ids))).scalars()
    )
    lot: dict[int, list[SanXuatKhoLot]] = {i: [] for i in ids}
    for lo in lot_rows:
        lot[lo.lsx_id].append(lo)

    # 10) su_co — HAI đường về lệnh, OR trong CÙNG một câu: `lsx_id IN ids` (sự cố trên bước riêng)
    # và `cong_viec_id IN cv_ids` (sự cố trên bước bị BÀI GHÉP phủ — `cv.lsx_id` NULL nên đường đầu
    # hụt). `cv_ids` đã có sẵn từ câu 5d, không đẻ câu mới. Xem docstring cho quyết định "sự cố của
    # ca ghép giương cờ cho MỌI lệnh trong ca".
    su_co_rows = list(
        db.execute(
            select(YeuCauSuaChua).where(
                or_(YeuCauSuaChua.lsx_id.in_(ids), YeuCauSuaChua.cong_viec_id.in_(cv_ids))
            )
        ).scalars()
    )
    su_co: dict[int, list[YeuCauSuaChua]] = {i: [] for i in ids}
    for sc in su_co_rows:
        # Sự cố KHÔNG ghép khớp CẢ HAI vế ⇒ gom đích vào set trước rồi mới phát, không thì mỗi
        # lệnh nhận bản ghi hai lần.
        dich = set(lenh_theo_cv.get(sc.cong_viec_id, ())) if sc.cong_viec_id else set()
        if sc.lsx_id in su_co:
            dich.add(sc.lsx_id)
        for i in dich:
            su_co[i].append(sc)
    may_ids |= {sc.may_id for sc in su_co_rows if sc.may_id is not None}

    # 11) giao — DeliveryRequestLine.order_line_id IN {lenh.order_line_id}. KHÔNG khoá theo
    # lsx_id (xem docstring — bảng này không có cột đó).
    giao_rows = list(
        db.execute(
            select(DeliveryRequestLine).where(DeliveryRequestLine.order_line_id.in_(order_line_ids))
        ).scalars()
    )
    giao: dict[int, list[DeliveryRequestLine]] = {i: [] for i in order_line_ids}
    for g in giao_rows:
        giao[g.order_line_id].append(g)

    # 11b) da_giao — SỐ THỰC NHẬN, cộng từ `delivery_trip_lines` qua các chuyến CÓ HÀNG ĐẾN TAY.
    # Bám khuôn `delivery_repo.da_giao_theo_dong:123-138`; bỏ join `delivery_requests` vì đã lọc
    # thẳng theo `order_line_id`. KHÔNG liệt kê trạng thái loại trừ — dùng hằng `LAN_GIAO_CO_HANG_
    # DEN_TAY` để danh sách này không lệch khi bên giao hàng thêm/bỏ trạng thái.
    # ⚠️ BỘ LỌC NÀY HÔM NAY KHÔNG LOẠI ĐƯỢC DÒNG NÀO, và đó là chuyện bình thường — nó PHÒNG THỦ,
    # không phải đang gánh việc. Đã rà hết đường ghi (Vòng sửa 3): `delivery_trip_lines` chỉ sinh
    # ở `delivery_repo.add_trip_line:169`, gọi từ `_ghi_dong_thuc_nhan:883`, gọi từ
    # `ghi_ket_qua:833` — hàm này đòi chuyến đang ở `dang_giao`, chỉ ghi dòng ở nhánh
    # `thanh_cong`/`giao_thieu`, rồi đóng trạng thái sang đúng hai giá trị ấy trong cùng lượt.
    # Các bước chuyển đều MỘT CHIỀU tiến (`da_lay_hang:812` ← `dang_chuan_bi`, `dang_giao:822` ←
    # `da_lay_hang`), `huy_ke_hoach:783` chỉ huỷ được khi chuyến còn trong `LAN_GIAO_SUA_DUOC`
    # (chưa có dòng nào), và `cho_giao_lai` đã gỡ khỏi `HUONG_XU_LY` nên không có đường quay lui.
    # ⇒ Mọi chuyến CÓ dòng hàng đều nằm sẵn trong tập. Vì thế KHÔNG có bài test nào canh riêng bộ
    # lọc này: dựng được ca đỏ thì phải phá đường ghi, mà fixture phá đường ghi là fixture nói dối.
    # Giữ bộ lọc vì bên giao hàng có thể thêm trạng thái mang hàng-chưa-tới-tay bất cứ lúc nào.
    trip_rows = db.execute(
        select(
            DeliveryTripLine.order_line_id,
            func.coalesce(func.sum(DeliveryTripLine.qty_giao), 0),
        )
        .join(DeliveryTrip, DeliveryTrip.id == DeliveryTripLine.trip_id)
        .where(
            DeliveryTripLine.order_line_id.in_(order_line_ids),
            DeliveryTrip.trang_thai.in_(LAN_GIAO_CO_HANG_DEN_TAY),
        )
        .group_by(DeliveryTripLine.order_line_id)
    ).all()
    da_giao: dict[int, int] = {i: 0 for i in order_line_ids}
    for order_line_id, tong in trip_rows:
        da_giao[int(order_line_id)] = int(tong or 0)

    # 12) nhap_kho_yc — HAI cầu, OR trong CÙNG một câu:
    #   · `kcs_batch → cong_viec.lsx_id` (yêu cầu sinh từ batch của chính lệnh);
    #   · `SanXuatNhapKhoYc.nhom_id` ∈ nhóm của lệnh (kho nhận hàng của NHÓM — xem docstring).
    # OUTER JOIN vì vế nhóm phải sống cả khi batch/công việc trỏ hụt.
    nhom_thanh_vien_ids = set(lsx_theo_nhom)
    nhap_rows = list(
        db.execute(
            select(SanXuatNhapKhoYc, SanXuatCongViec.lsx_id)
            .outerjoin(SanXuatKcsBatch, SanXuatNhapKhoYc.kcs_batch_id == SanXuatKcsBatch.id)
            .outerjoin(SanXuatCongViec, SanXuatKcsBatch.cong_viec_id == SanXuatCongViec.id)
            .where(
                or_(
                    SanXuatCongViec.lsx_id.in_(ids),
                    SanXuatNhapKhoYc.nhom_id.in_(nhom_thanh_vien_ids),
                )
            )
        ).all()
    )
    nhap_kho_yc: dict[int, list[SanXuatNhapKhoYc]] = {i: [] for i in ids}
    for yc, lsx_id in nhap_rows:
        # Thân chính khớp CẢ HAI vế ⇒ gom đích vào set trước rồi mới phát (khử trùng).
        dich = set(lsx_theo_nhom.get(yc.nhom_id, ())) if yc.nhom_id else set()
        if lsx_id in nhap_kho_yc:
            dich.add(lsx_id)
        for i in dich:
            nhap_kho_yc[i].append(yc)

    # 13) phu_thuoc_buoc — JOIN lsx_cong_doan (bước SAU) để có lsx_id; cạnh (buoc_truoc, buoc_sau).
    edge_rows = list(
        db.execute(
            select(LsxCongDoanPhuThuoc, LsxCongDoan.lsx_id)
            .join(LsxCongDoan, LsxCongDoanPhuThuoc.buoc_sau_id == LsxCongDoan.id)
            .where(LsxCongDoan.lsx_id.in_(ids))
        ).all()
    )
    phu_thuoc_buoc: dict[int, list[tuple[int, int]]] = {i: [] for i in ids}
    for canh, lsx_id in edge_rows:
        phu_thuoc_buoc[lsx_id].append((canh.buoc_truoc_id, canh.buoc_sau_id))

    # 14) nhom — SanXuatNhom.id IN {cong_viec.nhom_id}.
    nhom: dict[int, SanXuatNhom] = {
        n.id: n for n in db.execute(select(SanXuatNhom).where(SanXuatNhom.id.in_(nhom_ids))).scalars()
    }

    # 15) may — MayThietBi.id IN {cong_viec.may_id} ∪ {phien.may_id} ∪ {su_co.may_id}.
    may: dict[int, MayThietBi] = {
        m.id: m for m in db.execute(select(MayThietBi).where(MayThietBi.id.in_(may_ids))).scalars()
    }

    # 16) phan_cong + nhan_su — MỘT câu JOIN, ra HAI map (khuôn `nhom`/`may`: map dòng + map danh mục).
    #
    # CHỈ dòng ĐANG HOẠT ĐỘNG. Rút người ghi `trang_thai='removed'` để giữ lịch sử
    # (`thuc_thi.go_phan_cong:211`); hiện tên người đã bị rút lên bảng điều độ là nói sai ai đang
    # làm — mà nói sai kiểu này KHÔNG gãy gì, nó chỉ khiến người ta đi tìm nhầm người.
    #
    # INNER JOIN là ĐÚNG chứ không phải cẩu thả: `employee_id` NOT NULL + `ondelete=CASCADE`
    # (`models/san_xuat_thuc_thi.py:66`) ⇒ không có dòng phân công nào mồ côi nhân viên.
    #
    # Sắp theo `SanXuatPhanCong.id` = THỨ TỰ GIAO. Người được giao đầu là người nhận việc; UI cắt
    # bớt khi cột hẹp thì phải cắt từ cuối, không phải cắt ngẫu nhiên theo thứ tự DB trả về.
    pc_rows = list(
        db.execute(
            select(SanXuatPhanCong, Employee)
            .join(Employee, Employee.id == SanXuatPhanCong.employee_id)
            .where(
                SanXuatPhanCong.cong_viec_id.in_(cv_ids),
                SanXuatPhanCong.trang_thai == PC_HOAT_DONG,
            )
            .order_by(SanXuatPhanCong.id.asc())
        ).all()
    )
    phan_cong: dict[int, list[SanXuatPhanCong]] = {i: [] for i in cv_ids}
    nhan_su: dict[int, Employee] = {}
    for pc, emp in pc_rows:
        phan_cong[pc.cong_viec_id].append(pc)
        nhan_su[emp.id] = emp

    return BoiCanh(
        lenh=lenh, don=don, khach=khach, sale=sale, cong_viec=cong_viec,
        cong_viec_ghep=cong_viec_ghep, buoc_phu=buoc_phu,
        phien=phien, batch=batch, kcs=kcs, lot=lot, su_co=su_co, giao=giao, da_giao=da_giao,
        nhom=nhom, may=may, phan_cong=phan_cong, nhan_su=nhan_su,
        phu_thuoc_buoc=phu_thuoc_buoc, nhap_kho_yc=nhap_kho_yc,
    )
