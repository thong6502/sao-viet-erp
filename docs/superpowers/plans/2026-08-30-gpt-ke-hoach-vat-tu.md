# Siết logic Kế hoạch vật tư trên giữ chỗ hiện có — Implementation Plan

> **Nguồn kế hoạch:** GPT/Codex lập ngày 30/08/2026. Từ `gpt` trong tên file là dấu nhận biết kế hoạch do GPT tạo.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dùng một engine backend để kết luận nhu cầu, đã cấp, đã giữ, có thể giữ, hàng về muộn và thiếu; giữ nguyên sổ `vat_tu_giu_cho`, đồng thời nối chắc nguồn PMH với phiếu nhập Kho.

**Architecture:** `KeHoachVatTuService` thu thập nhu cầu và nguồn cung rồi gọi một engine phân bổ thuần, không ghi DB. `GiuChoService` là nơi duy nhất thay đổi cam kết giữ chỗ; `StockVoucherService` là nơi duy nhất làm thay đổi tồn thật. Hai cách nhìn FE, gợi ý mua, cửa phát hành lịch và đèn tổng quan đều chiếu từ cùng snapshot backend.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite/PostgreSQL, React/TypeScript, SSE.

**Quy tắc dự án:** Không commit/push nếu chủ dự án chưa yêu cầu. Mọi thay đổi schema phải có `backend/app/db_migrations.py` và `docs/DB_SCHEMA.md`. Lệnh xác minh chuẩn duy nhất là `./init.ps1`.

---

## Kết luận nghiệp vụ đã khóa

1. Không tạo chức năng giữ chỗ mới; `vat_tu_giu_cho` là sổ cam kết duy nhất.
2. Kho đã ghi sổ là nguồn sự thật của tồn và `đã cấp`.
3. Giữ nguồn `kho` và giữ nguồn `dang_ve` là hai pool độc lập:
   - Chỉ giữ nguồn `kho` làm giảm tồn tự do hiện tại.
   - Giữ nguồn `dang_ve` làm giảm phần còn tự do của đúng dòng PMH.
4. Hàng đang về chỉ được dùng khi PMH đã đặt với NCC, có ngày dự kiến và dòng hàng nối được danh mục gốc.
5. Ghi nhận đợt giao chưa làm tăng tồn. Chỉ ghi sổ phiếu nhập Kho mới làm tăng tồn thật.
6. Sửa nhu cầu khi đang giữ bị chặn; người dùng phải nhả trước.
7. Không tự hết hạn, không tự cướp chỗ vì cờ gấp. Khi nguồn giảm, cam kết cũ được giữ; chỗ mới hơn bị nhả trước.
8. Giấy/vật tư bước chung thuộc bài ghép; vật tư bước riêng thuộc LSX thành viên.

## Hợp đồng tính toán chung

Tạo module thuần `backend/app/services/vat_tu_allocation.py` với các kiểu nội bộ sau:

```python
TrangThaiVatTu = Literal[
    "da_cap", "da_giu", "co_the_giu", "ve_muon", "thieu", "chua_ro"
]

@dataclass(frozen=True)
class NhuCauVatTu:
    hang: tuple[str, int]
    lsx_id: int | None
    bai_ghep_id: int | None
    buoc_id: int | None
    ngay_can: date | None
    so_luong: float
    khong_ro: bool
    is_rush: bool

@dataclass(frozen=True)
class NguonDangVe:
    purchase_request_line_id: int
    hang: tuple[str, int]
    ngay_ve: date
    so_luong_con_lai: float
    ma_phieu: str

@dataclass
class KetQuaDongVatTu:
    da_cap: float = 0
    dang_linh: float = 0
    da_giu_kho: float = 0
    da_giu_dang_ve: float = 0
    co_the_giu_kho: float = 0
    co_the_giu_dang_ve: float = 0
    thieu: float = 0
    trang_thai: TrangThaiVatTu = "chua_ro"
```

Thứ tự phân bổ cho từng mặt hàng:

1. Sắp nhu cầu theo `(ngay_can hoặc date.max, loại chủ thể, id chủ thể, buoc_id)`; cờ gấp không đổi thứ tự.
2. Phân bổ `đã cấp` theo `(chủ thể, mặt hàng)` đúng một lần vào các bước theo ngày cần.
3. Áp giữ chỗ hiện có của đúng chủ thể, nguồn `kho` trước rồi `dang_ve`; không vượt phần nhu cầu còn lại.
4. Pool kho tự do bằng `tồn thật - tổng giữ nguồn kho`.
5. Pool PMH tự do của từng dòng bằng `số nguồn còn hiệu lực - tổng giữ dang_ve của dòng đó`.
6. Phân bổ thử kho tự do, sau đó PMH theo ngày về tăng dần.
7. PMH đủ số nhưng về sau ngày cần cho trạng thái `ve_muon`, không sinh lượng mua trùng.
8. Phần không có bất kỳ nguồn nào mới là `thieu`.

Trạng thái tổng lấy nhánh xấu nhất theo thứ tự:

```text
chua_ro > thieu > ve_muon > co_the_giu > da_giu > da_cap
```

Mọi lượng dùng đơn vị gốc của mặt hàng và được làm tròn theo biên `Numeric(14,2)` tại điểm ghi giữ chỗ, không làm tròn giữa các phép phân bổ đọc-only.

---

### Task 1: Dựng engine phân bổ thuần và khóa contract API

**Files:**
- Create: `backend/app/services/vat_tu_allocation.py`
- Modify: `backend/app/schemas/ke_hoach_vat_tu.py`
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py`
- Modify: `frontend/src/api/client.ts`
- Test: `backend/tests/test_ke_hoach_vat_tu.py`

- [ ] **Step 1: Viết test thất bại cho thứ tự phân bổ và sáu trạng thái**

  Bổ sung ca độc lập cho: đã cấp đủ, đã giữ đủ, có thể giữ từ kho, có thể giữ từ PMH, về muộn, thiếu và chưa rõ. Ca hỗn hợp phải giữ đủ các lượng thành phần nhưng trạng thái tổng là nhánh xấu nhất.

- [ ] **Step 2: Chạy `./init.ps1` và xác nhận test mới thất bại vì chưa có engine/field mới**

- [ ] **Step 3: Tạo engine thuần**

  Hàm công khai nội bộ duy nhất:

  ```python
  def phan_bo_vat_tu(
      *,
      nhu_cau: Sequence[NhuCauVatTu],
      da_cap: Mapping[ChuTheHang, float],
      dang_linh: Mapping[ChuTheHang, float],
      giu_cho: Sequence[GiuChoSnapshot],
      ton_kho: Mapping[Hang, float],
      dang_ve: Sequence[NguonDangVe],
  ) -> VatTuSnapshot:
      ...
  ```

  Engine không query DB, không commit và không phụ thuộc FastAPI/Pydantic.

- [ ] **Step 4: Mở rộng response model**

  `CanDoiDong` và `TheoLenhHang` phải trả ít nhất:

  ```text
  da_cap
  dang_linh
  da_giu_kho
  da_giu_dang_ve
  co_the_giu_kho
  co_the_giu_dang_ve
  thieu
  trang_thai
  ngay_du_hang
  phieu_ve
  nguon_giu[]
  ```

  Giữ nguyên route và payload hiện tại của `/can-doi`, `/theo-lenh`, `/giu-cho/bat`, `/giu-cho/tat`.

- [ ] **Step 5: Cho `KeHoachVatTuService` dựng một snapshot rồi chiếu ra hai cách gom**

  `can_doi()`, `vat_tu_hieu_luc()` và dữ liệu cho `GiuChoService` không được tự chạy lại phép phân bổ riêng.

- [ ] **Step 6: Chạy `./init.ps1`; mong đợi toàn bộ pytest và compileall PASS**

---

### Task 2: Sửa ngày cần từng công đoạn và chủ thể LSX/bài ghép

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py`
- Modify: `backend/app/services/xep_lich_2/context.py` hoặc helper lịch làm việc hiện được `xep_lich_2` dùng
- Test: `backend/tests/test_ke_hoach_vat_tu.py`
- Test: `backend/tests/test_xep_lich_2.py`

- [ ] **Step 1: Viết test ngày cần cho hai công đoạn chưa xếp lịch**

  Công đoạn sớm và công đoạn muộn của cùng LSX phải có hai ngày cần khác nhau. Nếu thiếu máy/thời lượng/hạn, kết quả phải `chua_ro`, không gắn nhãn đủ.

- [ ] **Step 2: Viết test chủ thể bài ghép**

  Giấy chung và vật tư bước chung thuộc `bai_ghep_id`; vật tư bước riêng vẫn thuộc `lsx_id` thành viên.

- [ ] **Step 3: Chạy `./init.ps1` và xác nhận các test mới thất bại**

- [ ] **Step 4: Thay `_moc_tam` bằng phép tính lùi theo từng bước**

  - Có lịch thật: `start_at - CAP_PHAT_TRUOC_PHUT`.
  - Chưa có lịch: lấy latest-start của bước bằng cách tính lùi trên DAG công đoạn từ hạn sản xuất, dùng đúng duration và lịch làm việc mà xếp lịch đang dùng.
  - Bài ghép dùng routing bước chung và hạn sớm nhất của thành viên liên quan.

- [ ] **Step 5: Sửa quy phiếu xuất về đúng chủ thể**

  Với phiếu gắn LSX thành viên:

  1. Nếu snapshot có nhu cầu `(LSX, mặt hàng)`, giữ nguyên LSX.
  2. Nếu không có nhu cầu LSX và có đúng một nhu cầu chung của bài ghép khớp mặt hàng, quy về bài.
  3. Nếu không có hoặc có nhiều ứng viên, không trừ số; trả cảnh báo dữ liệu mơ hồ.

- [ ] **Step 6: Phân bổ `đã cấp`/`đang lĩnh` cấp chủ thể xuống các bước một lần theo ngày cần**

- [ ] **Step 7: Chạy `./init.ps1`; mong đợi PASS**

---

### Task 3: Nối giữ chỗ và yêu cầu nhập với đúng dòng PMH

**Files:**
- Modify: `backend/app/models/vat_tu_giu_cho.py`
- Modify: `backend/app/models/stock_request.py`
- Modify: `backend/app/db_migrations.py`
- Modify: `docs/DB_SCHEMA.md`
- Modify: `backend/app/repositories/giu_cho_repo.py`
- Modify: `backend/app/repositories/stock_request_repo.py`
- Test: `backend/tests/test_giu_cho_vat_tu.py`
- Test: `backend/tests/test_kho_de_nghi.py`

- [ ] **Step 1: Viết test migration/backfill trước**

  Bao phủ:

  - Dòng `dang_ve` cũ khớp duy nhất một PMH.
  - Một dòng giữ phải tách qua hai dòng PMH.
  - Tổng giữ lớn hơn nguồn còn hiệu lực: nhả dòng mới nhất trước.
  - Dòng nguồn `kho` không được mang `purchase_request_line_id`.

- [ ] **Step 2: Chạy `./init.ps1` và xác nhận test thất bại**

- [ ] **Step 3: Thêm hai cột nullable**

  ```text
  vat_tu_giu_cho.purchase_request_line_id
  stock_request_lines.purchase_request_line_id
  ```

  Cả hai có index; dòng giữ `dang_ve` trỏ FK tới `purchase_request_lines.id`. Dòng yêu cầu nhập dùng liên kết này để đi từ phiếu nhập → đợt giao → dòng PMH.

- [ ] **Step 4: Thêm migration tương thích SQLite và PostgreSQL**

  Backfill nguồn theo thứ tự:

  ```text
  nguồn PMH: expected_receipt_date, purchase_request_id, line_id
  giữ chỗ: created_at, id
  ```

  Nếu một dòng giữ trải qua nhiều nguồn thì tách dòng. Nếu nguồn không đủ, xóa phần giữ mới nhất trước và giữ nguyên cờ đăng ký để màn hiện thiếu. Ghi audit hệ thống cho phần bị nhả; migration chạy trước app nên không phát SSE trong chính migration.

- [ ] **Step 5: Siết invariant ở model/service**

  ```text
  nguon=kho     => purchase_request_line_id=NULL, ngay_ve=NULL
  nguon=dang_ve => purchase_request_line_id!=NULL, ngay_ve!=NULL
  ```

- [ ] **Step 6: Cập nhật đầy đủ bảng/cột/mô tả trong `docs/DB_SCHEMA.md`**

- [ ] **Step 7: Chạy `./init.ps1`; mong đợi migration guard và toàn bộ test PASS**

---

### Task 4: Cho giữ chỗ dùng đúng hai pool và bảo đảm transaction

**Files:**
- Modify: `backend/app/services/giu_cho_service.py`
- Modify: `backend/app/repositories/giu_cho_repo.py`
- Modify: `backend/app/routers/ke_hoach_vat_tu.py`
- Test: `backend/tests/test_giu_cho_vat_tu.py`

- [ ] **Step 1: Viết test nguồn kho và nguồn đang về không ăn lẫn nhau**

  - Giữ `dang_ve` không làm giảm `ton_tu_do` hiện tại.
  - Hai LSX không giữ vượt một dòng PMH.
  - LSX chỉ có giữ `dang_ve` không được dùng con số đó để xuất phần kho LSX khác đang giữ.

- [ ] **Step 2: Viết test hai thao tác bật giữ đồng thời**

  Tổng giữ nguồn kho không vượt tồn; tổng giữ từng PMH không vượt phần còn hiệu lực.

- [ ] **Step 3: Chạy `./init.ps1` và xác nhận test thất bại với logic cũ**

- [ ] **Step 4: Sửa `ton_tu_do`**

  Repository phải có hai phép tổng riêng:

  ```python
  da_giu_kho_map(hangs)
  da_giu_dang_ve_map(purchase_request_line_ids)
  ```

  Không dùng tổng mọi nguồn để trừ tồn kho.

- [ ] **Step 5: Cho `bat()` materialize đúng phần `co_the_giu_*` từ snapshot**

  Giữ kho trước, sau đó PMH theo ngày về. Dòng PMH phải ghi `purchase_request_line_id` và `ngay_ve`.

- [ ] **Step 6: Tách mutation trong transaction khỏi wrapper commit**

  Repository không tự commit. Cung cấp các hàm nội bộ:

  ```python
  nhat_them_in_tx(...)
  tieu_thu_in_tx(...)
  chuyen_nguon_nhap_in_tx(...)
  doi_soat_nguon_in_tx(...)
  ```

  Route bật/tắt commit một lần sau toàn bộ thao tác. `StockVoucherService` gọi bản `_in_tx` và sở hữu commit cuối.

- [ ] **Step 7: Khóa nguồn theo thứ tự ổn định**

  Khóa các dòng lot, PMH và giữ chỗ theo `(hang_loai, hang_id, source_id)`. PostgreSQL dùng `SELECT ... FOR UPDATE`; SQLite dựa trên write transaction nhưng phải giữ cùng thứ tự gọi.

- [ ] **Step 8: Chạy `./init.ps1`; mong đợi PASS**

---

### Task 5: Đồng bộ nhập/xuất Kho với giữ chỗ trong một giao dịch

**Files:**
- Modify: `backend/app/services/stock_voucher_service.py`
- Modify: `backend/app/services/stock_request_service.py`
- Modify: `backend/app/schemas/stock.py`
- Modify: `frontend/src/pages/KhoDeNghiPage.tsx`
- Test: `backend/tests/test_kho_de_nghi.py`
- Test: `backend/tests/test_giu_cho_vat_tu.py`

- [ ] **Step 1: Viết test xuất kho không lấn cam kết**

  `kiem_xuat` chỉ cho dùng `tồn tự do + giữ nguồn kho của chính chủ thể`; không cộng giữ `dang_ve` vào khả năng xuất.

- [ ] **Step 2: Viết test nhập kho từ đúng dòng PMH**

  - Tạo yêu cầu nhập chưa tăng tồn.
  - Ghi sổ nhập tăng tồn.
  - Số nhập chuyển các giữ `dang_ve` cùng `purchase_request_line_id` sang `kho`, cũ trước.
  - Nhập dư trở thành tồn tự do.

- [ ] **Step 3: Viết test rollback**

  Gây lỗi sau khi lot đã mutate nhưng trước khi cập nhật giữ chỗ; sau rollback, lot, `sl_da_ung`, voucher và giữ chỗ phải đều giữ nguyên.

- [ ] **Step 4: Chạy `./init.ps1` và xác nhận test thất bại**

- [ ] **Step 5: Mang `purchase_request_line_id` qua seed yêu cầu nhập**

  Backend phải xác nhận dòng PMH thuộc đúng `purchase_delivery_id` của header và đúng mặt hàng; không tin id do FE gửi trần.

- [ ] **Step 6: Sửa `_apply_post`**

  - XUẤT: kiểm toàn bộ trước, mutate lot/đã ứng, gọi `tieu_thu_in_tx`, commit một lần.
  - NHẬP: tạo lot, cập nhật đã ứng, gọi `chuyen_nguon_nhap_in_tx`, rồi `nhat_them_in_tx`, commit một lần.
  - Không có `commit()` bên trong `GiuChoService` khi đi từ phiếu Kho.

- [ ] **Step 7: Chạy `./init.ps1`; mong đợi PASS**

---

### Task 6: Đối soát vòng đời PMH và trạng thái nhập Kho

**Files:**
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py`
- Modify: `backend/app/services/purchase_service.py`
- Modify: `backend/app/repositories/purchase_repo.py`
- Modify: `backend/app/schemas/purchase.py`
- Modify: `frontend/src/pages/mua-hang/phieu-mua-hang/PurchaseRequestsPage.tsx`
- Modify: `frontend/src/pages/mua-hang/phieu-mua-hang/components/DeliveriesBlock.tsx`
- Test: `backend/tests/test_purchases_api.py`
- Test: `backend/tests/test_ke_hoach_vat_tu.py`

- [ ] **Step 1: Viết test điều kiện nguồn PMH**

  - `approved`: chỉ hiện dấu vết mua, không thành nguồn giữ.
  - `purchased`/`partially_received` có ngày: thành nguồn giữ.
  - Không ngày: báo đang mua nhưng chưa hứa được, không mở khóa lịch.

- [ ] **Step 2: Viết test đợt giao chờ Kho**

  Số đã ghi đợt giao nhưng phiếu Kho chưa posted vẫn là `cho_nhap_kho`, không biến mất khỏi nguồn và không tăng tồn.

- [ ] **Step 3: Viết test PMH đổi nguồn**

  - Lùi ngày cập nhật `xep_som_nhat`.
  - Giảm/hủy nhả phần vượt nguồn, reservation mới nhất trước.
  - Không tự đổi ngay sang PMH khác.
  - Giao một phần và giao vượt không làm âm nguồn.

- [ ] **Step 4: Chạy `./init.ps1` và xác nhận test thất bại**

- [ ] **Step 5: Dựng nguồn PMH theo hai segment**

  ```text
  cho_nhap_kho = lượng delivery đã ghi - lượng Kho đã posted
  dang_ve      = lượng đã đặt - tổng delivery đã ghi
  ```

  `cho_nhap_kho` dùng ngày giao thực tế; `dang_ve` dùng ngày dự kiến của PMH. Cả hai vẫn bám cùng `purchase_request_line_id`.

- [ ] **Step 6: Gọi đối soát giữ chỗ sau mọi thay đổi PMH ảnh hưởng số lượng/ngày/trạng thái**

  Runtime phải tạo audit hệ thống và phát SSE cho các LSX/bài ghép bị đổi kết luận.

- [ ] **Step 7: Sửa contract đợt giao**

  Trả rõ:

  ```text
  stock_request_id
  stock_request_ma
  stock_request_status
  da_tao_yeu_cau_kho
  da_ghi_so_kho
  ```

  FE hiển thị `Đã gửi Kho · DNN...` khi mới có yêu cầu và chỉ dùng chữ `Đã nhập kho` sau khi phiếu đã ghi sổ.

- [ ] **Step 8: Chạy `./init.ps1`; mong đợi PASS**

---

### Task 7: Cập nhật màn Kế hoạch vật tư, không tạo màn mới

**Files:**
- Modify: `frontend/src/pages/VatTuKeHoachView.tsx`
- Modify: `frontend/src/pages/GiuChoTheoLenhView.tsx`
- Modify: `frontend/src/pages/KeHoachVatTuPage.tsx`
- Modify: `frontend/src/pages/ke-hoach-sx.css`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Đổi type trạng thái FE đồng bộ backend**

  ```ts
  export type TrangThaiVatTu =
    | "da_cap"
    | "da_giu"
    | "co_the_giu"
    | "ve_muon"
    | "thieu"
    | "chua_ro";
  ```

- [ ] **Step 2: Xóa mọi phép kết luận ở FE**

  Không dùng `ton / tong_can`, không tự đổi trạng thái theo phần trăm và không tự cộng lại nguồn. FE chỉ format số backend trả.

- [ ] **Step 3: Cập nhật cách nhìn theo mặt hàng**

  Mỗi dòng hiện gọn các lượng có giá trị: đã cấp, đã giữ, có thể giữ, về muộn, thiếu. Nút đề nghị mua chỉ hiện khi `thieu > 0`; dòng `ve_muon` gọi tên PMH và gợi ý hối NCC/dời lịch.

- [ ] **Step 4: Cập nhật cách nhìn theo LSX**

  Giữ nguyên nút bật/tắt và drawer hiện có. Hiện nguồn giữ kho/PMH, ngày về và trạng thái đủ để phát hành. `dang_linh` là badge phụ, không thay trạng thái vật tư.

- [ ] **Step 5: Giữ nguyên một màn và segmented switch hiện có**

  Không thêm menu, route, tab hay form mua mới.

- [ ] **Step 6: Chạy `./init.ps1`; mong đợi backend contract/compileall PASS**

- [ ] **Step 7: Kiểm UI chạy thật**

  Dùng `dev-browser` hoặc Playwright kiểm hai cách gom, bật/nhả, dòng hỗn hợp, về muộn, thiếu, chưa rõ và realtime. Sau đó chạy `styleseed-design-review`; chỉ sửa các điểm làm sai phân cấp/trạng thái, không redesign ngoài phạm vi.

---

### Task 8: Cho lịch, tổng quan và gợi ý mua dùng cùng snapshot

**Files:**
- Modify: `backend/app/services/xep_lich_2/release.py`
- Modify: `backend/app/services/xep_lich_service.py`
- Modify: `backend/app/services/lsx_tong_quan.py`
- Modify: `backend/app/services/ke_hoach_vat_tu_service.py`
- Test: `backend/tests/test_xep_lich_2.py`
- Test: `backend/tests/test_ke_hoach_vat_tu.py`

- [ ] **Step 1: Viết test cửa phát hành**

  - Giữ đủ kho: phát hành được, không có chặn ngày.
  - Giữ đủ PMH: phát hành được nhưng bước tiêu thụ không được trước ngày đủ hàng.
  - Có thể giữ nhưng chưa giữ: vẫn chặn phát hành.
  - Thiếu/chưa rõ: chặn và nói đúng hành động.

- [ ] **Step 2: Viết test gợi ý mua tái tính server-side**

  Client chỉ gửi khóa dòng; server dựng snapshot mới. Tồn/giữ/PMH thay đổi sau khi mở màn phải làm số mua thay đổi đúng. `ve_muon` không được đưa vào lượng mua trùng.

- [ ] **Step 3: Chạy `./init.ps1` và xác nhận test thất bại nếu consumer còn dùng logic cũ**

- [ ] **Step 4: Thay các consumer bằng kết luận snapshot**

  Không consumer nào tự diễn giải màu cũ `xam/xanh/vang/do` hoặc tự gọi lại phép phân bổ riêng.

- [ ] **Step 5: Phát SSE sau thay đổi có ảnh hưởng**

  Bao gồm bật/nhả, PMH đổi nguồn, Kho nhập/xuất/điều chỉnh và auto-top-up. Payload tối thiểu mang loại sự kiện và danh sách chủ thể/mặt hàng ảnh hưởng; FE dùng event hiện có để refetch.

- [ ] **Step 6: Chạy `./init.ps1`; mong đợi PASS**

---

### Task 9: Nghiệm thu tích hợp và bàn giao

**Files:**
- Test: `backend/tests/test_ke_hoach_vat_tu.py`
- Test: `backend/tests/test_giu_cho_vat_tu.py`
- Test: `backend/tests/test_kho_de_nghi.py`
- Test: `backend/tests/test_purchases_api.py`
- Test: `backend/tests/test_xep_lich_2.py`

- [ ] **Step 1: Chạy `./init.ps1` trên toàn repository**

  Kết quả bắt buộc: pytest PASS và compileall PASS. Nếu fail, lưu log thật và không báo hoàn tất.

- [ ] **Step 2: Restart backend bằng `./restart-be.ps1`**

  Route/schema backend không được nghiệm thu trên tiến trình uvicorn cũ.

- [ ] **Step 3: Kiểm luồng vận hành đầu-cuối bằng browser**

  ```text
  LSX phát sinh nhu cầu
  → Kế hoạch hiện Có thể giữ/Thiếu
  → bật giữ
  → lập PMH và đặt NCC
  → ghi đợt giao
  → tạo yêu cầu nhập từ nút hiện có
  → Kho ghi sổ
  → giữ dang_ve chuyển kho
  → Kho xuất cho đúng LSX
  → giữ chuyển đã cấp
  → cửa phát hành lịch cập nhật realtime
  ```

- [ ] **Step 4: Kiểm các ca phá nguồn**

  Giảm/hủy/lùi ngày PMH; xuất một phần; nhập nhiều đợt; giữ lâu; LSX rơi khỏi phạm vi; sửa LSX/bài ghép đang giữ; hai người bật giữ đồng thời.

- [ ] **Step 5: Soi UI cuối bằng StyleSeed và ghi lại bằng chứng kiểm tra**

- [ ] **Step 6: Không commit/push cho tới khi chủ dự án yêu cầu rõ**

## Tiêu chí hoàn tất

- Một con số ở “Theo mặt hàng” và “Theo LSX” truy được về cùng snapshot.
- Không có trường hợp giữ hàng đang về làm giảm tồn hiện tại.
- Không có trường hợp LSX chỉ giữ hàng đang về mà xuất được vào hàng kho người khác giữ.
- Không đếm lặp `đã cấp` khi một mặt hàng xuất hiện ở nhiều bước.
- PMH, yêu cầu nhập, phiếu nhập và giữ chỗ truy vết được tới đúng dòng nguồn.
- Chỉ phiếu Kho đã ghi sổ mới tăng tồn.
- Gợi ý mua không mua trùng hàng đang về và luôn tái tính tại server.
- Phát hành lịch chỉ dựa trên giữ chỗ thật; hàng đang về tạo đúng chặn dưới ngày chạy.
- Mọi thay đổi liên phân hệ atomic, có audit và cập nhật realtime.
- `./init.ps1` PASS; backend đã restart; UI đã được browser và StyleSeed xác nhận.
