# Thiết kế — KCS theo LỆNH (LSX → Công đoạn → Kết quả kiểm)

Trạng thái: **ĐÃ CHỐT** (17/09/2026) — toàn bộ mục 1–7. Plan triển khai:
`docs/superpowers/plans/2026-09-17-kcs-theo-lenh.md`.
Thay thế cách tổ chức "KCS theo TỔ" của `design-kcs-kiem-nhiem-ui.md` và ba loại mẻ KCS của
`design-kcs-theo-cong-doan.md` (tiêu chí theo công đoạn ở tài liệu đó GIỮ NGUYÊN).

---

## 0. Vì sao đổi

Màn KCS hiện đi vào theo TỔ ("KCS · {tổ}"), và mọi thứ lệch theo từ đó:

- Ba loại mẻ KCS (`routing` · `diem_kiem` · `dot_xuat`) cho cùng một việc là kiểm một công đoạn,
  mỗi loại một cửa, một luật trạng thái, một luật số lượng.
- Bước KCS phải **đoán** từ routing (bước cuối + tổ `is_kcs`) → LSX kết thúc ở tổ không cờ KCS bị
  chặn phát hành (`release.py:158`, `kcs_cuoi_thieu`), bước "Đóng gói" bị coi là bước KCS.
- Tổ KCS ghi vào kết quả = tổ của trang đang mở, không phải người kiểm (DB dev đã có mẻ ghi
  "Sản xuất" là bên kiểm).
- Hộp "Kiểm đột xuất" liệt kê tổ theo quyền **xem bàn tổ** (`KcsResultDrawer.tsx:100` →
  `board.teams`) → `tt_kcs` chỉ kiểm đột xuất được chính tổ mình. Gốc rễ: quyền kiểm bị cấp theo
  từng tổ (ô `can_qc`), trong khi KCS vốn kiểm mọi tổ.
- Phía tổ bị kiểm không có chỗ thấy kết quả: cột lỗi KCS trên bàn tổ truyền cứng rỗng
  (`ThucHienSxPage.tsx:785`), drawer công việc không có mục KCS, thông báo chỉ bắn khi người KCS tự
  chọn "Tổ liên đới" (`kcs.py:567`); điểm kiểm và kiểm đột xuất không đẩy cho ai.

## 1. Luồng nghiệp vụ (ĐÃ CHỐT)

Một LSX = một chuỗi công đoạn, mỗi công đoạn thuộc một tổ. KCS đi theo lệnh:

1. Mở màn **KCS** → danh sách LSX đang sản xuất.
2. Bấm một LSX → chuỗi công đoạn theo thứ tự. Mỗi dòng: tổ phụ trách, trạng thái chạy, số tốt/hỏng
   tổ đã ghi, tình trạng kiểm (chưa kiểm · đạt · có lỗi, số lần kiểm).
3. Bấm một công đoạn → hệ thống tự điền tổ, máy, thợ, số lượng các mẻ, bộ tiêu chí của công đoạn
   (`kcs_tieu_chi_json` chụp lúc phát hành). Không chọn tổ, không chọn loại.
4. KCS tick tiêu chí (nếu công đoạn có), nhập **Số đạt** / **Số lỗi**; có lỗi thì mô tả + ≥1 ảnh.
   Kết quả mỗi lần kiểm (màn KCS và tab KCS của bàn tổ) liệt kê TỪNG tiêu chí một dòng: ✓/✗, tên,
   Đạt/Không đạt, ghi chú của tiêu chí; không đạt lên đầu (17/09/2026). Tên tiêu chí có thể chứa dấu
   phẩy nên không nối chung một câu.
5. Lưu → kết quả gắn vào công đoạn đó. **Tổ chịu = tổ của công đoạn** (tự điền, bỏ ô "Tổ liên
   đới"). **Người kiểm = tài khoản đang đăng nhập.** Đẩy ngay tới tổ bị kiểm (mục 3).

Kiểm được công đoạn đã bắt đầu: đang chạy, tạm dừng hoặc đã xong. Kiểm nhiều lần được.

Hệ quả: chỉ còn MỘT hành động "kiểm công đoạn". Không còn ba loại, không còn bước chọn tổ, không còn
nút "Kiểm đột xuất" và "Ghi điểm kiểm" tách nhau.

## 2. Ai là KCS (ĐÃ CHỐT 17/09/2026 — BỎ ô quyền KCS)

Bản chất KCS là kiểm được **mọi bàn tổ**, kể cả khi tổ KCS nằm ở node lá của cây. Nên KHÔNG cấp
quyền kiểm theo từng tổ nữa:

- **Gỡ ô "KCS" (`can_qc`)** khỏi ma trận quyền theo tổ (`quyen_to.py` `VIEC_KCS`,
  `PermissionMatrix.tsx`, cột `role_permissions.can_qc`).
- **KCS = người thuộc tổ có cờ "Tổ KCS"** (`Department.is_kcs`, cờ đặt đích danh trên danh mục phòng
  ban — không kế thừa). Người đó kiểm được công đoạn của **mọi** tổ, không phụ thuộc vị trí tổ mình
  trên cây và không phụ thuộc quyền xem bàn tổ.
- Menu: MỘT mục **"KCS"** (thay các node "KCS · {tổ}"), hiện cho người thuộc tổ KCS.
- Danh sách LSX: mọi LSX đang sản xuất, đủ chuỗi công đoạn.

**Đóng thiếu nhóm chỉ tổ trưởng** (chốt 17/09/2026): người đứng đầu một tổ KCS
(`Department.head_user_id` của tổ `is_kcs`, đặt ở màn Phòng ban). Không suy theo tên vai — tên vai
là danh mục động. Thành viên khác của tổ KCS kiểm và sửa kết quả được, không đóng thiếu được.

Dữ liệu dev cần biết: "Tổ thành phẩm / KCS" (32 người) gộp cả thợ Đóng gói (`tho_donggoi*`) lẫn
người kiểm → theo luật này thợ Đóng gói cũng thành người KCS; muốn khác thì tách tổ Đóng gói ra ở
màn Phòng ban (sửa dữ liệu, không sửa code). Người đứng đầu tổ hiện là `tt_thanhpham`; `tt_kcs` và
`tt_donggoi` mang vai "Tổ trưởng SX" nhưng không đứng đầu tổ nên không đóng thiếu được.

Cờ `is_kcs` đổi nghĩa: trước là "bước cuối ở tổ này là bước KCS" (dùng để đoán `la_kcs`), nay là
"thành viên tổ này là người kiểm". Nghĩa cũ bỏ theo mục 6. DB dev đang bật cờ ở cả "Ban giám đốc" —
phải rà lại khi làm.

## 3. Phía tổ bị kiểm (ĐÃ CHỐT — dựng lại chỗ đã gỡ)

1. **Đẩy tức thì** tới người có quyền Xác nhận sản lượng trọn tổ của công đoạn (cùng tập người đang
   nhận hộp "Chờ tổ bạn xác nhận") — toast + badge, không phải refresh.
2. **Bàn tổ, từng công việc:** dấu "KCS: đạt" / "KCS: N lỗi". Drawer công việc có mục **"Kết quả
   KCS"**: từng lần kiểm — ai kiểm, lúc nào, đạt/lỗi, checklist, mô tả, ảnh.
3. **Hộp "Chờ tổ bạn xác nhận"** (đã có, `ThsxChoXacNhanBar`) thêm dòng **"KCS báo lỗi"** cho lỗi
   mới, nút **"Đã xem"**. Lưu ai xem, lúc nào. Không có Nhận/Từ chối trách nhiệm, không chặn gì.
   *(17/09/2026: hộp này đã gỡ — lỗi chưa xem thành chấm đỏ trên dòng công đoạn + tab KCS của ngăn
   chi tiết, "Đã xem" bấm ở đó. Xem `spec-thuc-hien-san-xuat.md` §11.5.)*

Giả định: tổ chỉ cần xác nhận đã biết, không tranh chấp trách nhiệm (thông báo một chiều như
quyết định hiện hành, thêm vết đã xem).

## 4. Số lượng (ĐÃ CHỐT)

Kiểm **không trừ** số lượng giữa các công đoạn. Số chảy sang công đoạn sau vẫn là số **tốt** tổ tự
ghi trong mẻ (`san_xuat_batch.tot` / `hong`). Kết quả KCS là bản ghi chất lượng thuần: không đẻ
`san_xuat_batch`, không đổi trạng thái công việc, không chặn bước sau.

## 5. Dữ liệu — KHÔNG thêm bảng

| Cần | Dùng lại |
|---|---|
| Một lần kiểm | `san_xuat_kcs_batch` (bỏ phân biệt `loai`; người kiểm = `created_by`) |
| Lỗi + ảnh | `san_xuat_kcs_loi` + `san_xuat_kcs_loi_anh`; `to_chiu_id` = tổ của công đoạn |
| "Đã xem" | `san_xuat_kcs_loi.phan_hoi_by_id` / `phan_hoi_luc` (cột đang có, luồng phản hồi cũ bỏ) |
| Tiêu chí | `san_xuat_cong_viec.kcs_tieu_chi_json` (giữ nguyên) |

`kcs_department_id` thôi là "tổ KCS của trang" — bỏ khỏi luồng ghi. Dự án chưa có dữ liệu thật: dữ
liệu KCS cũ trên DB dev chuyển về một loại, không giữ tương thích ngược.

## 6. Công đoạn cuối → nhập kho (ĐÃ CHỐT 17/09/2026)

Hàng chưa qua KCS không vào kho:

- `la_kcs_cuoi` = **công đoạn cuối của nhóm thành phẩm**, bất kể tổ nào làm — bỏ điều kiện tổ
  `is_kcs`, bỏ cờ `la_kcs` từng bước. Hết lỗi chặn phát hành `kcs_cuoi_thieu` vì nhóm nào cũng có
  công đoạn cuối.
- KCS kiểm công đoạn cuối như mọi công đoạn; **số đạt cộng dồn** là số được đề nghị nhập kho, trần =
  số tốt tổ đã ghi ở công đoạn đó.
- Nút "Tạo yêu cầu nhập kho" nằm trên dòng công đoạn cuối của LSX (không chỉ hiện một lần sau khi
  lưu như hiện nay).
- Phần lỗi ở công đoạn cuối không vào kho; tổ làm lại rồi KCS kiểm lại, hoặc đóng thiếu nhóm.
- Đóng nhóm giữ điều kiện đếm theo số đạt của công đoạn cuối (từ 17/09/2026 số đạt còn phải ≥ mục
  tiêu `so_luong_ra` mới tự đóng đủ); bỏ điều kiện "hết lỗi chờ" (đang chết
  vì lỗi ghi thẳng `recorded`).

Một công đoạn tên "KCS" nếu có trong routing thì là công đoạn thường của tổ làm nó (ghi mẻ tốt/hỏng,
khoán như mọi công đoạn), không còn nghĩa đặc biệt.

Từ 17/09/2026 nút "Tạo yêu cầu nhập kho" tạo thẳng yêu cầu NHẬP của Kho (không còn sổ kho riêng của
xưởng, không còn bước kho xác nhận ở bàn tổ). Màn KCS liệt kê từng yêu cầu DNN kèm "đề nghị / kho đã
nhận" và trạng thái. Xem `docs/design-nhap-kho-thanh-pham-qua-yeu-cau-nhap-xuat.md`.

## 7. Gỡ

- Ba loại mẻ và ba đường ghi (`tao_batch_kcs`, `tao_kiem_dot_xuat`, `ghi_loi` tách riêng) → một đường.
- Bắt đầu / Tạm dừng / Kết thúc **bước KCS** (`KcsChayDialog`) và mẻ sản lượng đẻ kèm.
- Node "KCS · {tổ}", `so_viec_kcs_cho`, `co_viec_kcs`, `_nut_nhan_kcs` trong `board.teams`.
  ⚠ Session khác đang vá đúng chỗ này (17/09/2026) — thiết kế này làm bản vá đó thừa.
- Nút "Kiểm đột xuất", bảng "Điểm kiểm theo công đoạn", bảng "Chờ KCS" của trang tổ.
- Ô "Tổ liên đới", bộ lọc "Loại" trên dashboard.
- Ô quyền "KCS" (`can_qc`) theo tổ — mọi chỗ đang gate bằng nó chuyển sang "người thuộc tổ KCS"
  (kiểm, sửa kết quả, Xuất Excel), riêng đóng thiếu nhóm chuyển sang "người đứng đầu tổ KCS".
- Luồng phản hồi Nhận/Từ chối (`phan_hoi_loi`, `hop_thu_loi`, cột KCS rỗng của `ThsxHopThuBar`).

Giữ: dashboard (KPI, biểu đồ), Xuất Excel, khối Chốt nhóm (BTP dư đã gỡ 17/09/2026), danh mục tiêu chí theo công đoạn.

## 8. Thứ tự làm

1. BE: một hàm ghi kết quả kiểm theo `cong_viec_id` + gate "người thuộc tổ `is_kcs`"; đẩy SSE tới
   tổ bị kiểm. Gỡ `can_qc` (migration bỏ cột + `docs/DB_SCHEMA.md`).
2. BE: `la_kcs_cuoi` theo công đoạn cuối của nhóm; kho + đóng nhóm đọc theo đó; bỏ chặn phát hành.
3. BE: API danh sách LSX cho KCS + chi tiết chuỗi công đoạn kèm tình trạng kiểm; "Đã xem".
4. FE màn KCS: danh sách LSX → chuỗi công đoạn → form kiểm (dùng lại khối form của
   `KcsResultDrawer`).
5. FE bàn tổ: dấu KCS trên công việc, mục "Kết quả KCS" trong drawer, dòng "KCS báo lỗi" trong hộp
   "Chờ tổ bạn xác nhận".
6. Gỡ mục 7, migration dữ liệu KCS dev, cập nhật `docs/DB_SCHEMA.md` nếu đổi cột.
7. Xác minh bằng dev-browser: tài khoản KCS kiểm một công đoạn tổ khác có lỗi → tổ trưởng tổ đó thấy
   toast + dòng trong hộp + mục trong drawer → bấm "Đã xem"; kiểm công đoạn cuối → tạo yêu cầu nhập
   kho → kho nhận → nhóm đóng.
