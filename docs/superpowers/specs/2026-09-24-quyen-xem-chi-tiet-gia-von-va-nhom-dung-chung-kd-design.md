# Thiết kế: quyền xem chi tiết giá vốn (Tính giá) + nhóm dùng chung khối Kinh doanh

Ngày: 24/09/2026
Trạng thái: Chờ duyệt thiết kế

## 1. Mục tiêu

Hai việc rời nhau, cùng phục vụ khối Kinh doanh, không việc nào thay được việc nào.

**Việc 1 — giấu ruột giá.** Phiếu tính giá đang bày trọn cách ra giá vốn: giấy gì, bao nhiêu
tờ, đơn giá kg, mỗi công đoạn ăn bao nhiêu. Nhìn vào là biết nhà máy mua giấy giá nào và còn
lãi mấy phần. Nhân viên đi chào khách chỉ cần biết giá vốn tổng, không cần biết vì sao ra nó.
Cần một ô quyền để tách hai mức đó.

**Việc 2 — hai người dùng chung dữ liệu mà không mở cả phòng.** Phạm vi hiện có ba nấc
(*Của tôi* · *Cả phòng* · *Tất cả*). Có nhu cầu: anh A và anh B đều để *Của tôi*, nhưng hai
người làm chung nên phải thấy và sửa được phiếu của nhau — mà không kéo cả phòng vào. Đổi
sang *Cả phòng* là mở quá tay; thêm người vào từng phiếu, từng báo giá, từng đơn là bắt làm
đi làm lại.

## 2. Phạm vi

Trong phạm vi:

- Một quyền chi tiết mới trên dòng **Tính giá** của ma trận phân quyền.
- Gỡ hẳn nút "In phiếu" khỏi màn Tính giá.
- Khái niệm **nhóm dùng chung — Kinh doanh**, khai ở màn Phòng ban.
- Nhóm chỉ áp cho bốn màn: **Tính giá · Báo giá · Đơn hàng · Khách hàng**.

Ngoài phạm vi:

- Không đổi ngữ nghĩa ba nấc phạm vi hiện có.
- Không áp nhóm dùng chung cho bất kỳ màn nào ngoài bốn màn trên (đặc biệt: Lương, Hồ sơ
  nhân sự, Chấm công vẫn hiểu *Của tôi* = chỉ chính mình).
- Không đụng công thức tính giá, không đụng luồng nghiệp vụ báo giá/đơn hàng.
- Không đẻ mục sidebar mới.

---

## 3. Việc 1 — quyền "Xem chi tiết giá vốn"

### 3.1. Ô quyền

Dòng **Tính giá** trong ma trận phân quyền (tab "Vai trò & Quyền" của màn Phòng ban) có thêm
một chip quyền chi tiết, giống cách Báo giá in ấn và Đơn hàng bán đang có:

- Nhãn: **Xem chi tiết giá vốn**
- Mặc định: **tắt**

### 3.2. Ô đó gác những gì

Bật thì thấy đủ như hiện nay. Tắt thì ba thứ sau biến mất:

1. Bảng **Chi tiết dòng giá vốn** — toàn bộ phần diễn giải từng dòng nguyên vật liệu và
   công đoạn (`0,20 kg/m² × 1,09 m × 0,79 m × 1.955 tờ × 22.000 đ ÷ 3.000 = 2.469,06đ/sp`).
2. **Thẻ sản phẩm** — bấm vào dòng hàng trong bảng "Sản phẩm trong phiếu" không mở ra nữa.
   Đây là chỗ khai giấy, khổ, số con, công đoạn, gia công.

Hai thứ này đi chung một ô, không tách: cả hai đều bày đúng một nội dung.

### 3.2b. Gỡ hẳn nút "In phiếu"

Nút **In phiếu** trên màn Tính giá bị **gỡ bỏ hoàn toàn**, cho mọi vai, kể cả vai có đủ
quyền. Phiếu tính giá là giấy tờ nội bộ chứa ruột giá — không có nhu cầu in ra giấy, mà in ra
thì tờ giấy đó đi đâu hệ thống không biết. Bản in cho khách nằm ở màn Báo giá, không đổi.

### 3.3. Tắt rồi thì còn thấy gì

Người thiếu quyền vẫn mở được phiếu và vẫn thấy — đủ để đi chào khách:

- Mã phiếu, tên sản phẩm, loại, số lượng, trạng thái, người lập, ngày lập.
- **Giá vốn tổng** và **đơn giá bình quân** của từng sản phẩm và của cả phiếu.
- Thẻ tổng bên phải với ba cục tiền: Nguyên vật liệu · Công đoạn · Giao hàng.

Ba cục tiền ở thẻ tổng **giữ nguyên** — chúng không lộ định mức hay giá mua vào, chỉ nói tiền
chia về ba nhóm.

### 3.4. Chặn ở máy chủ

Ẩn nút ở giao diện là chưa đủ. Máy chủ **không gửi** phần diễn giải về máy người dùng khi
người gọi thiếu quyền: dữ liệu kết quả chi tiết của phiếu bị cắt khỏi phản hồi, y như cách
`kho:view_cost` đang cắt đơn giá và thành tiền.

Mọi đường sửa phiếu (lưu thành phần, tính lại giá) cũng đòi quyền này ở máy chủ, không chỉ
dựa vào việc giao diện không mở thẻ ra.

### 3.5. Ràng buộc với cột Thao tác

Lập hoặc sửa phiếu nghĩa là phải mở thẻ sản phẩm ra khai. Nên trong ma trận:

> Bật **Thao tác** ở dòng Tính giá ⇒ ô "Xem chi tiết giá vốn" **tự bật** và khoá, không tắt
> được. Tắt Thao tác thì ô trở lại cấp tự do.

Cách này đã có tiền lệ trong ma trận (vài ô chỉ bật được khi Phạm vi là "Tất cả"), giao diện
hiện ô mờ kèm dòng giải thích vì sao không tắt được.

Vai chỉ **Xem** thì cấp hay không tuỳ người quản trị — đây mới là trường hợp dùng chính.

---

## 4. Việc 2 — nhóm dùng chung (Kinh doanh)

### 4.1. Khái niệm

**Nhóm dùng chung** là một danh sách người. Hai người cùng một nhóm thì, ở bốn màn khối Kinh
doanh, phạm vi *Của tôi* của mỗi người được hiểu rộng ra:

> *Của tôi* = dữ liệu của tôi **và** dữ liệu của mọi người cùng nhóm với tôi.

Nhóm **mở rộng dữ liệu nhìn thấy, không nâng quyền**. Anh B không có ô "Duyệt báo giá đặc
thù" thì vào báo giá của anh A vẫn không duyệt được. Mọi ô quyền vẫn tính theo vai của người
đang thao tác.

### 4.2. Bốn màn áp dụng

| Màn | Dữ liệu "của tôi" hiện đang tính theo |
|---|---|
| Tính giá | người lập phiếu |
| Báo giá in ấn | người lập báo giá |
| Đơn hàng bán | người lập đơn |
| Khách hàng | Sale phụ trách khách |

Ngoài bốn màn này, nhóm **không có tác dụng gì**. Lương, Hồ sơ nhân sự, Chấm công, Sản xuất,
Kho… giữ nguyên *Của tôi* = chỉ chính mình.

### 4.3. Khai ở đâu

Màn **Phòng ban** → tab **Nhân sự**. Mỗi người trong danh sách đã có sẵn ô tick.

- Tick vài người → bấm nút **"Gộp nhóm dùng chung — Kinh doanh"**.
- Hộp thoại hiện ra: đặt tên nhóm mới (vd "Cặp KD 1"), hoặc chọn thêm vào một nhóm đã có.
- Trong danh sách nhân sự, người đang thuộc nhóm nào hiện chip tên nhóm đó; bấm vào chip mở
  hộp thoại để đổi tên, thêm/bớt người, hoặc xoá nhóm.

Không đẻ màn mới, không thêm mục sidebar.

### 4.4. Quy tắc của nhóm

- Một người ở được **nhiều nhóm**. Tập người dùng chung = hợp của mọi nhóm người đó thuộc.
- Nhóm **vắt qua phòng ban được** — hai người khác phòng vẫn gộp chung được.
- Người **không thuộc nhóm nào** thì mọi thứ y như hiện nay, không có gì đổi.
- Nhóm chỉ tác động khi phạm vi của vai là ***Của tôi***. Vai đang ở *Cả phòng* hoặc *Tất cả*
  thì đã rộng hơn rồi, nhóm không làm hẹp lại và cũng không cộng thêm gì đáng kể (lấy hợp).
- Gỡ một người khỏi nhóm thì ngay lượt gọi sau người đó hết thấy dữ liệu của nhóm.
- Nhóm **không đổi người sở hữu**: phiếu A lập vẫn ghi người lập là A dù B sửa; B sửa thì để
  lại vết B đã sửa trong nhật ký của phiếu.

### 4.5. Ai được gộp nhóm

Gộp nhóm là quyết định "cho người này thấy dữ liệu của người kia" — cùng loại với việc cấp
quyền. Nên dùng lại ô đã có: **Phòng ban → "Sửa ma trận phân quyền"** (`phong_ban:manage_permissions`).
Ai sửa được ma trận thì gộp được nhóm; không đẻ ô quyền mới.

Mọi thao tác tạo nhóm, thêm người, bớt người, xoá nhóm đều ghi vết: ai làm, lúc nào, với ai.

---

## 5. Dữ liệu và kỹ thuật

### 5.1. Việc 1 — không cần cột mới

Bảng phân quyền đã có sẵn cột `can_view_cost` (module Kho đang dùng cho "Xem giá vốn & giá trị
tồn"). Mỗi vai có một dòng quyền cho **từng module**, nên khai thêm cờ này cho module
`tinh_gia_thanh` là xong — **không migration, không đụng DB**.

Việc phải làm:

- Khai `can_view_cost` vào danh sách quyền chi tiết của `tinh_gia_thanh` ở cả hai phía (ma
  trận giao diện và bản đồ hành động phía máy chủ) — hai phía này có test guard so khớp.
- Router `phieu_tinh_gia` cắt phần kết quả chi tiết khỏi phản hồi khi người gọi thiếu quyền,
  và chặn các đường ghi thành phần/tính lại giá.
- Vai mẫu trong seed: vai có Thao tác ở Tính giá thì bật sẵn; vai chỉ Xem thì tắt.
- Gỡ nút "In phiếu" và phần định kiểu dành riêng cho bản in của màn Tính giá (nếu có) —
  không để lại nút mờ hay nút ẩn theo quyền.

### 5.2. Việc 2 — hai bảng mới, một migration

- Bảng **nhóm**: id, tên, người tạo, thời điểm tạo.
- Bảng **thành viên**: nhóm ↔ người dùng, người thêm, thời điểm thêm.

Viết vào `db_migrations.py` (dự án không có Alembic, `create_all` không ALTER được), cập nhật
`docs/DB_SCHEMA.md` cùng lúc vì có test guard.

Cột Boolean nếu có thì `server_default` phải là `false`/`true` kiểu Python, không phải `"0"`/`"1"`.

### 5.3. Điểm sửa của bốn màn

Mỗi màn trong bốn màn đó hiện đã có **đúng một chỗ** quyết định "được thấy dữ liệu của ai" —
nhánh *own* trong hàm lọc của repository tương ứng (`phieu_tinh_gia` lọc theo `created_by`,
`quotation_repo` / `order_repo` theo người lập, `customer_repo` theo `sale_user_id`). Cả bốn
chỗ đổi từ "bằng chính tôi" sang "nằm trong tập người dùng chung của tôi", gọi **một hàm
chung** đặt cạnh `org_scope.py`.

Hàm đó trả về tập user-id = {chính mình} ∪ {mọi người cùng nhóm}. Người không thuộc nhóm nào
trả về đúng {chính mình} — hành vi cũ giữ nguyên nguyên vẹn.

Nhánh *department* và *all* không đụng tới.

### 5.4. Hiệu năng

Tập người dùng chung đọc một lần cho mỗi lượt gọi, không đọc lại theo từng dòng. Bốn màn đều
là màn có phân trang ở máy chủ nên tập này vào thẳng điều kiện lọc SQL, không lọc sau ở tầng
Python.

---

## 6. Trường hợp cần kiểm

**Việc 1:**

1. Vai có Thao tác ở Tính giá → ô tự bật, khoá, mở phiếu thấy đủ.
2. Vai chỉ Xem + tắt ô → mở phiếu: không có bảng chi tiết, bấm dòng sản phẩm không mở thẻ;
   vẫn thấy giá vốn tổng, đơn giá bình quân và ba cục tiền.
2b. Vai **có đủ quyền** mở phiếu → không còn nút "In phiếu" trên màn Tính giá.
3. Vai chỉ Xem + tắt ô, gọi thẳng đường lấy phiếu → phản hồi không chứa phần diễn giải.
4. Vai chỉ Xem + tắt ô, gọi thẳng đường ghi thành phần → bị từ chối.
5. Vai chỉ Xem + bật ô → thấy đủ nhưng vẫn không sửa được.

**Việc 2:**

6. A và B cùng nhóm, cả hai phạm vi *Của tôi*: A thấy và sửa được phiếu/báo giá/đơn/khách của
   B, và ngược lại.
7. C cùng phòng nhưng không cùng nhóm: C không thấy gì của A và B.
8. B không có ô duyệt báo giá đặc thù: vào báo giá của A vẫn không duyệt được.
9. B không có "Xem chi tiết giá vốn": vào phiếu của A vẫn không thấy bảng diễn giải — hai
   việc độc lập, nhóm không cấp hộ quyền.
10. Gỡ B khỏi nhóm: B hết thấy dữ liệu của A ngay lượt sau.
11. A và B cùng nhóm nhưng nhóm **không** đụng tới Lương/Hồ sơ nhân sự/Chấm công: A không
    thấy phiếu lương hay hồ sơ của B.
12. A ở phạm vi *Cả phòng*: nhóm không làm hẹp lại tập A đang thấy.
13. Người không thuộc nhóm nào: kết quả mọi màn y hệt trước khi có tính năng.

**Guard sẵn có phải còn xanh:** ma trận giao diện khớp máy chủ, ma trận quyền khớp thanh bên,
`docs/DB_SCHEMA.md` khớp model.

**Xác minh bằng giao diện thật** (bắt buộc theo CLAUDE.md): đăng nhập bằng hai tài khoản
khác nhau trên dev-browser, thao tác đủ luồng phiếu → báo giá → đơn, không dùng API thay bất
kỳ bước nào.

---

## 7. Điểm đã chốt trong lúc bàn

- Ô quyền là **một ô duy nhất**, gác bảng diễn giải và thẻ sản phẩm.
- Nút "In phiếu" **gỡ hẳn**, không gác bằng quyền — phiếu tính giá không in ra giấy.
- Ba cục tiền ở thẻ tổng **không** giấu.
- Nhóm dùng chung **chỉ** bốn màn khối Kinh doanh, cứng, không cho tick chọn màn lúc tạo
  nhóm. Khối khác cần thì sau này đẻ loại nhóm riêng, không mở rộng lén cái này.
- Tên nút nói thẳng phạm vi: "Gộp nhóm dùng chung — Kinh doanh". Không hiện dòng phụ liệt kê
  bốn màn.
- Phạm vi *Của tôi* / *Cả phòng* / *Tất cả* giữ nguyên ngữ nghĩa, không thêm nấc thứ tư.
