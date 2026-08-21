# Thiết kế UI — Thực hiện sản xuất tại tổ ("một bàn làm việc")

> Trạng thái: **ĐÃ CHỐT THIẾT KẾ** — tài liệu cho agent BUILD dựng FE.
> Phạm vi tài liệu này: **CHỈ FRONTEND**. Backend mặt đọc + mặt ghi (§7.1–§7.2) đã có sẵn và
> KHÔNG đụng tới. Mọi field/luật dưới đây **bám đúng** `routers/san_xuat.py` +
> `schemas/san_xuat.py` + `services/san_xuat/*` (không bịa field).
>
> Hai mảnh phải dựng, **gộp vào luồng đang có, KHÔNG đẻ màn/loại mới**:
> 1. **Node lá tổ** trong Khối "Sản xuất" của navbar (badge = số việc chờ, bấm mở bàn lọc theo tổ).
> 2. **Bàn làm việc** (một khung dùng chung mọi tổ): timeline theo thời gian + drawer một công việc.

---

## 1. Bối cảnh — cái gì đã có, cái gì phải dựng

Module này là **pha THỰC HIỆN** đứng sau "Xếp lịch công đoạn 2" (`xep_lich_2`): khi một gói
đã **phát hành**, các công việc của nó rơi xuống bàn của TỔ. Tổ trưởng mở bàn tổ mình, thấy
timeline việc đã phát hành, giao người vào việc, rồi bấm Bắt đầu/Tạm dừng/Kết thúc.

Backend đã sẵn (đọc kỹ trước khi dựng):

| Tầng | File | Nội dung |
|---|---|---|
| Router | `backend/app/routers/san_xuat.py` | prefix `/api/san-xuat`, 3 GET đọc + 5 POST ghi |
| Schema | `backend/app/schemas/san_xuat.py` | `TeamsOut`/`WorkItemsOut`/`WorkItemChiTietOut` + các `*In`/`LenhKetQuaOut` |
| Service | `backend/app/services/san_xuat/board.py` (đọc) · `thuc_thi.py` (ghi) | luật nghiệp vụ |
| Enum trạng thái | `backend/app/models/san_xuat.py` | `released`/`running`/`paused`/`completed` |

**FE hiện KHÔNG có gì cho module này**: `client.ts` chưa có `api.sanXuat`; `AppShell` chưa có
state tổ, chưa đổ item động, chưa nhánh SSE, chưa case render bàn tổ; Sidebar section
`san-xuat` mới chỉ có 6 màn công cụ. Tất cả wiring là việc của agent BUILD.

---

## 2. Soi precedent — bê cái gì, TRÁNH cái gì

### 2.1. `XepLich2Page.tsx` + `Xl2Gantt.tsx` — precedent GẦN NHẤT ("một bàn làm việc")
Đây là bàn 3 cột đã được duyệt (styleseed 95/A). **Bê nguyên khung, bỏ bớt cho đúng vai.**

**Bê lại:**
- Khung `.xl2` 3 cột: top (tiêu đề + cửa sổ ngày + seg zoom) → subbar → grid (trái/giữa/phải) → foot.
  Chỉ cột GIỮA cuộn ngang, thân trang không bao giờ cuộn ngang (`overflow:hidden` ở gốc).
- Trục **tuyến tính** `buildLinearScale` + `XL2_PX_PER_MIN` (px/phút theo zoom) trong `xl2Shared.tsx`.
  Việc thực hiện chạy theo đồng hồ tường như v2 nên **KHÔNG** dùng `buildScale` nén-ngoài-ca.
- Cluster → lane → bar; `LABEL_W`/`BAR_H`/`LANE_H`; dải ngày + băng ca + đường "bây giờ" (nowline).
- Panel phải trượt thành **drawer** trên màn hẹp (`--open` + scrim), như `xl2-panel`.
- Zoom Giờ/Ca/Ngày/Tuần bằng seg pill (`XL2_PX_PER_MIN` đã có đủ 4 nấc), mặc định **Ca**.
- Helper format: `ngay`/`ngayGio`/`thoiLuong`/`num` trong `keHoachSxShared.tsx` (dùng lại, đừng chép).

**DỨT KHOÁT BỎ (dở/không hợp vai tổ trưởng):**
- **Toàn bộ kéo–thả** (Pointer Events, ghost, `snapToWork`, `PreviewImpactDialog`, Undo, `xem-truoc`).
  Tổ trưởng **KHÔNG** được dời lịch (§5.2). Bỏ hết cơ chế drag của `Xl2Gantt` — timeline chỉ ĐỌC + bấm mở drawer.
- Cột trái "hàng chờ chia 2 rổ" và cột "gợi ý máy/khe" — không có khái niệm đó ở pha thực hiện.
  → Thay cột trái bằng **danh sách việc gọn của tổ** (cùng nguồn dữ liệu timeline, khỏi gọi thêm API).
- `Xl2MucPill` 3 mức chặn-đặt/chặn-phát-hành/cảnh-báo — đó là ngôn ngữ của bàn xếp lịch, không dùng ở đây.

### 2.2. `keHoachSxShared.tsx` — kho mảnh dùng lại
- `TrangThaiPill`/`.khsx-pill` (bo tròn, có chấm + CHỮ, không chỉ dựa màu) là khuôn để làm **pill
  trạng thái công việc** (released/running/paused/completed).
- `ChuoiCongDoan` + `LSX_LOAI_BUOC_META` (client.ts) đã biết tô `loai_buoc` (may/to/thue_ngoai) —
  dùng cho nhãn công đoạn + icon thuê-ngoài, đừng tự chế màu mới.
- `EmptyState`/`BangLoi`/`Skeleton` cho rỗng/lỗi/đang tải.

### 2.3. Kho (`AppShell` + Sidebar) — precedent node lá ĐỘNG + badge + SSE
Cơ chế "kho đã khai báo → item động dưới section, bấm mở màn tạm lọc theo id" là **đúng khuôn**
cho node lá tổ. Sao đúng khuôn này (chi tiết ở §6), đừng nghĩ ra cách khác.

**Precedent dở đã tránh:** `AppShell.renderContent` là chuỗi `if (baseId === ...)` dài — chấp nhận
được vì đó là điểm mắc dây chung; chỉ **thêm 1 case** cho bàn tổ, không refactor.

---

## 3. Bố cục màn (một khung dùng chung mọi tổ)

Bấm node lá "Tổ Bế" → mở `ThucHienSxPage` với `teamId` lấy từ id nav. Tiêu đề mang **tên tổ**.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ THSX-TOP  [icon] Bàn tổ · «Tên tổ»      [◀ cửa sổ ngày ▶]   [Giờ|Ca|Ngày|Tuần]  ⟳  │
├───────────────────────────────────────────────────────────────────────────────────┤
│ THSX-SUBBAR  🔎 tìm mã/công đoạn   ·  digest: N việc · ⦿đang chạy k · ⏸tạm dừng j   │
├──────────────┬────────────────────────────────────────────────┬─────────────────────┤
│ THSX-LIST    │ THSX-TIMELINE (chỉ đây cuộn ngang)             │ THSX-PANEL (drawer) │
│ (cột trái)   │                                                │                     │
│ việc của tổ  │  ── cluster: MÁY In 4 màu ──────────────────   │  «đóng khi chưa chọn│
│ dạng dòng    │   lane máy  ▐████ plan ▌   ▐██ plan ▌           │   → hiện digest»    │
│ gọn, bấm =   │  ── cluster: MÁY Bế ────────────────────────   │                     │
│ mở drawer +  │   lane máy  ▐███ running ▌                      │  ► khi chọn 1 việc: │
│ scroll-to    │  ── cluster: NĂNG LỰC TỔ (bước nội bộ) ─────    │   plan + roster +   │
│ thanh        │   lane tổ   ▐████ paused ▌  ▐███ ▌              │   phiên chạy +      │
│              │  ── cluster: THUÊ NGOÀI ────────────────────   │   nút hành động     │
│              │   lane      ▐██ ▌                               │                     │
├──────────────┴────────────────────────────────────────────────┴─────────────────────┤
│ THSX-FOOT   chú giải: ▐plan  ⦿running  ⏸paused  ✓completed  ·  ↕ zoom  ·  cửa sổ ngày │
└───────────────────────────────────────────────────────────────────────────────────┘
```

**Nhóm lane (cluster) — quy tắc gom:**
- `loai_buoc == "may"` → **cluster theo tên máy** (`may`), mỗi máy một lane. Nhãn lane = tên máy.
- `loai_buoc == "to"` (bước nội bộ) → **một cluster "Năng lực tổ"**, các việc xếp vào 1–vài lane
  theo công đoạn (`ten_cong_doan`). Đây là "lane theo NĂNG LỰC TỔ" spec nói tới (thủ công, không neo máy).
- `loai_buoc == "thue_ngoai"` → cluster "Thuê ngoài", một lane.

**Thanh (bar):** cửa sổ **kế hoạch** `du_kien_bat_dau → du_kien_ket_thuc`. Tô theo `trang_thai`
(xem §7). Nhãn thanh: serial nguồn + `ten_cong_doan` (dùng lại kiểu `dongSerial`/`dongNhanParts`
nhưng nguồn field khác — xem §5). Bấm thanh → mở drawer + cuộn danh sách trái tới đúng dòng.

> **Lớp "thực tế" ở đâu?** Endpoint `/work-items` (mức bàn) **KHÔNG** trả mốc chạy thật — chỉ có
> `trang_thai`. Vì vậy ở TIMELINE, "lớp thực tế" thể hiện bằng **trạng thái thanh** (đang chạy có
> nhịp đập / tạm dừng gạch chéo / hoàn thành mờ + tick), **không vẽ thanh-thật riêng** (không có
> field để vẽ → không bịa). So khớp **kế hoạch ↔ thực tế theo mốc** nằm trong **DRAWER**, nơi có
> `phien_chay` (bat_dau/ket_thuc) + `khoang_tham_gia`. Nếu sau này muốn overlay mốc-thật ngay trên
> bàn thì cần BE thêm field vào `WorkItemOut` (ghi ở §9, KHÔNG tự chế ở FE).

**Drawer một công việc** (`/work-items/{id}` — detail):
```
┌ Drawer: «serial» · «ten_cong_doan» ────────────────── [pill trạng thái] [✕] ┐
│ THANH KẾ HOẠCH:  dự kiến  09:00 → 12:30  ·  máy «…»  ·  SL vào/ra + đơn vị    │
│                                                                              │
│ TỔ THỰC HIỆN (roster)                                    [＋ Giao người ▾]   │
│   • Nguyễn Văn A   (lương khoán)  [đang làm]              [－ Rút]           │
│   • Trần B         (công nhật)    [đang làm]              [－ Rút]           │
│   → chỉ thợ LƯƠNG KHOÁN mới được giao vào bước nội bộ (loai_buoc="to")       │
│                                                                              │
│ PHIÊN CHẠY                             [▶ Bắt đầu] / [⏸ Tạm dừng] [■ Kết thúc]│
│   #1  09:12 → 10:40  tạm dừng · "hết giấy"                                    │
│   #2  10:55 → (đang chạy)                                                     │
│   ▸ khoảng tham gia (ai có mặt phiên nào) — bảng phụ gấp/mở                   │
│                                                                              │
│ ── PHA SAU (khung xám, chưa có API) ────────────────────────────────────────│
│   Nhập/Xuất sản lượng · Bàn giao chặng sau · KCS   →  "sắp có", disabled     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component + trách nhiệm + tên file dự kiến

Đặt tên bám nếp `xl2` (Page/Timeline/Shared/css). Bọc CSS trong `.thsx` để không rò.

| File dự kiến | Vai trò |
|---|---|
| `frontend/src/pages/ThucHienSxPage.tsx` | Controller bàn tổ: nhận `teamId`, giữ state (cửa sổ ngày, zoom, việc, việc-đang-chọn, version lạc quan), gọi `api.sanXuat.*`, dựng top/subbar/grid/foot, điều phối drawer + dialog lý do + toast. |
| `frontend/src/pages/ThsxTimeline.tsx` | Timeline thuần trình bày: nhận danh sách việc + scale + zoom → gom cluster/lane/bar, vẽ dải ngày/băng ca/nowline, phát `onChonViec(id)` khi bấm thanh. **Không** kéo–thả. |
| `frontend/src/pages/ThsxDrawer.tsx` | Drawer một công việc: thanh kế hoạch + roster (Giao/Rút) + phiên chạy (Bắt đầu/Tạm dừng/Kết thúc) + khoảng tham gia + khung "pha sau". Nhận `chiTiet` + callback ghi. |
| `frontend/src/pages/thsxShared.tsx` | Mảnh dùng chung: `THSX_TT_META` (pill trạng thái công việc), map cluster theo `loai_buoc`, nhãn serial/nguồn từ `WorkItemOut`, digest đếm theo trạng thái. (Trục thời gian **tái dùng** `xl2Shared.tsx` — import `buildLinearScale`/`XL2_PX_PER_MIN`/`LABEL_W`/`BAR_H`, đừng chép.) |
| `frontend/src/pages/thuc-hien-sx.css` | Style bọc `.thsx`, token từ `styles/tokens.css` (§7). Có thể copy khung layout của `xep-lich-2.css` rồi đổi tiền tố. |

Dialog lý do dùng lại `ConfirmDialog` (đã dùng ở `XepLich2Page`) — thêm ô nhập lý do khi cần.

---

## 5. Ánh xạ API → UI (bám đúng schema, không bịa field)

Tất cả gọi qua helper `authed<T>(path, token, init?)` sẵn có; thêm nhánh `sanXuat` vào `api` trong
`client.ts`. Kèm type TS mirror **đúng** schema (Pydantic nuốt field lạ im lặng — thêm/bớt phải đi cả hai đầu).

| Hành động UI | Endpoint (đã có ở BE) | Method client dự kiến | Body / trả về (đúng schema) |
|---|---|---|---|
| Nạp danh sách tổ + badge | `GET /api/san-xuat/teams` | `api.sanXuat.teams(token)` | `TeamsOut{ teams: TeamOut[] }`, `TeamOut{id,ten,ma,la_kcs,so_viec_cho}` |
| Nạp timeline 1 tổ | `GET /api/san-xuat/work-items?team_id=` | `api.sanXuat.workItems(token, teamId)` | `WorkItemsOut{team_id, cong_viec: WorkItemOut[]}`; 403 nếu ngoài phạm vi |
| Mở drawer 1 việc | `GET /api/san-xuat/work-items/{id}` | `api.sanXuat.chiTiet(token, id)` | `WorkItemChiTietOut{cong_viec, trang_thai, version, phan_cong[], phien_chay[], khoang_tham_gia[]}` |
| Danh nhân viên để "Giao người" | `GET /api/san-xuat/teams/{team_id}/nhan-vien` | `api.sanXuat.nhanVienChon(token, teamId)` | `NhanVienChonListOut{team_id, nhan_vien: NhanVienChonOut[]}`, `NhanVienChonOut{id, code, full_name, la_luong_khoan, co_tai_khoan}`; 403 nếu ngoài phạm vi |
| Giao 1 người | `POST /work-items/{id}/phan-cong` | `api.sanXuat.phanCong(token,id,body)` | `PhanCongIn{employee_id, expected_version?}` → `LenhKetQuaOut{cong_viec_id,department_id,trang_thai,version}` |
| Rút 1 người | `POST /phan-cong/{pcId}/rut` | `api.sanXuat.rut(token,pcId,body)` | `GoPhanCongIn{ly_do?, expected_version?}` → `LenhKetQuaOut` |
| Bắt đầu / Tiếp tục | `POST /work-items/{id}/bat-dau` | `api.sanXuat.batDau(token,id,body)` | `BatDauIn{ly_do_tre?, expected_version?}` → `LenhKetQuaOut` |
| Tạm dừng | `POST /work-items/{id}/tam-dung` | `api.sanXuat.tamDung(token,id,body)` | `TamDungIn{ly_do(BẮT BUỘC), expected_version?}` → `LenhKetQuaOut` |
| Kết thúc | `POST /work-items/{id}/ket-thuc` | `api.sanXuat.ketThuc(token,id,body)` | `KetThucIn{ly_do_tre?, expected_version?}` → `LenhKetQuaOut` |

**`WorkItemOut` (mọi field cho thanh + drawer):** `id, goi_id, phien_ban_so, nguon_loai("lsx"|"bai_ghep"|""),
nguon_ma, nguon_ten, nhom, ten_cong_doan, nhom_cong_doan, loai_buoc, la_kcs, la_kcs_cuoi, may,
du_kien_bat_dau, du_kien_ket_thuc, so_luong_vao, so_luong_ra, don_vi_vao, don_vi_ra, trang_thai`.
→ Nhãn thanh: `nguon_ma` (hoặc rút serial sau dấu "-") + `ten_cong_doan`; icon nguồn theo `nguon_loai`;
chip thuê-ngoài khi `loai_buoc=="thue_ngoai"`; chip KCS khi `la_kcs`. **KHÔNG có** mốc chạy thật ở đây.

**`PhanCongItemOut`:** `id, employee_id, ho_ten, la_luong_khoan, co_tai_khoan, trang_thai("active"|"removed")`.
→ Roster chỉ hiện người `active`. `la_luong_khoan=true` mới đủ điều kiện làm việc bắt đầu được (§7).
`co_tai_khoan=false` = thợ không có tài khoản (vẫn giao được, chỉ không nhận thông báo đẩy).

**`PhienChayOut`:** `id, so_thu_tu, bat_dau, ket_thuc?, loai_dong?("tam_dung"|"ket_thuc"), ly_do_bat_dau_tre?, ly_do?`.
→ Phiên `ket_thuc==null` = đang chạy. `loai_dong` cho biết phiên đóng vì tạm dừng hay kết thúc.

**`KhoangThamGiaOut`:** `id, phien_chay_id, employee_id, ho_ten, bat_dau, ket_thuc?`.
→ Ai có mặt ở phiên nào; `ket_thuc==null` = đang tham gia.

**Nguồn danh cho ô "Giao người":** dùng endpoint RIÊNG của module — `GET /api/san-xuat/teams/{team_id}/nhan-vien`
(`api.sanXuat.nhanVienChon`). **KHÔNG** dùng `api.employees` — nó gác quyền `nhan_su` nên tổ trưởng
(chỉ có `san_xuat`) sẽ **403**. Endpoint này gác bằng `san_xuat:read` + đúng phạm vi tổ, trả nhân
viên CÒN LÀM của tổ kèm `la_luong_khoan` (để **lọc/cảnh báo** cho bước nội bộ `loai_buoc=="to"` chỉ
nhận thợ khoán) và `co_tai_khoan`. Ô "Giao người" = ô chọn (combobox/tìm) trên danh này, loại sẵn
người đã có trong roster `active` (đối chiếu `phan_cong[]` của drawer). Bấm chọn → gọi `phanCong`.

---

## 6. Cơ chế navbar node lá tổ (đúng khuôn Kho)

Ba khoá dữ liệu (grep để chỉnh đúng chỗ):

**a) Sidebar** (`components/Sidebar.tsx`)
- Node lá tổ được đổ ĐỘNG qua prop `dynamicItems` theo **section id** — section "Sản xuất" có
  `id: "san-xuat"` (dòng 82). `Sidebar` gộp `merged = [...s.items, ...(dynamicItems?.[s.id] ?? [])]`
  (dòng 339) rồi lọc theo quyền `readable.has(module)`. → Không sửa gì trong Sidebar; chỉ **cấp
  `dynamicItems["san-xuat"]`** từ AppShell.
- Badge: `Sidebar` render `badges?.[item.id]` (dòng 410). → Đặt `badges["<id nav tổ>"] = so_viec_cho`.
- Mỗi `NavItem` tổ: `{ id: "thuc-hien-sx:<teamId>", label: ten, icon: "users", module: "san_xuat" }`.
  Chọn id dạng `baseId:param` để `activeId.split(":")[0] === "thuc-hien-sx"`, teamId ở `[1]`
  (giống Kho `"kho-item:<id>"`). Icon "users" đã có trong `Icons.tsx`.

**b) AppShell** (`components/AppShell.tsx`) — thêm, không refactor:
1. State + nạp (khuôn `khoList`/`reloadKho`, dòng 141 & 497):
   `const [teamList, setTeamList] = useState<TeamOut[]>([])`.
   `reloadTeams()`: nếu `readable.has("san_xuat")` → `api.sanXuat.teams(token).then(setTeamList)`.
   Gọi trong `useEffect([reloadTeams])`. **Một cú gọi cho cả list lẫn badge** (teams đã kèm `so_viec_cho`).
2. Đổ item động (khuôn dòng 902):
   `dynamicItems["san-xuat"] = teamList.map(t => ({ id: `thuc-hien-sx:${t.id}`, label: t.ten, icon: "users", module: "san_xuat" }))`.
3. Badge (khuôn `setBadges` trong `reloadBadges`, dòng 278): với mỗi tổ
   `setBadges(prev => ({ ...prev, [`thuc-hien-sx:${t.id}`]: t.so_viec_cho }))`. Vì `teams` đã có
   badge, chỉ cần đổ từ `teamList` — **không** gọi API riêng cho badge.
4. Cổng quyền route (khuôn `moduleKeys` dòng 891): `MODULES_BY_NAV_ID` chỉ tính từ `NAV.items`
   TĨNH nên `baseId="thuc-hien-sx"` sẽ `undefined`. Thêm nhánh giống Kho:
   `const moduleKeys = MODULES_BY_NAV_ID[baseId] ?? (baseId === "thuc-hien-sx" ? ["san_xuat"] : (isKhoView ? ["kho"] : undefined));`
5. Case render (khuôn `kho-item` dòng 954): 
   `if (baseId === "thuc-hien-sx") { const teamId = Number(activeId.split(":")[1]); const t = teamList.find(x=>x.id===teamId); return <ThucHienSxPage key={`thsx-${teamId}`} teamId={teamId} tenTo={t?.ten} eventTick={quoteTick} onBadgeStale={reloadTeams} .../>; }`
6. SSE (khuôn nhánh trong `connectQuoteEvents`, dòng 512+): thêm nhánh
   `else if (readable.has("san_xuat") && e.type === "san_xuat_cong_viec_changed") { reloadTeams(); setQuoteTick(n=>n+1); }`
   → badge tổ nhảy + bàn đang mở tự refetch tức thì (không refresh). Kênh SSE cho `san_xuat` **đã mở
   sẵn** — `appShellRealtime.ts::REALTIME_MODULES` đã liệt kê `"san_xuat"`.
   Nhánh `"san_xuat_duoc_giao_viec"` (đẩy riêng cho người vừa được giao) → toast cá nhân "Bạn được
   giao việc mới" (tuỳ chọn, nếu người dùng có tài khoản).

> **Vị trí node lá:** theo `merged`, các tổ xếp **SAU** 6 màn công cụ trong section "Sản xuất".
> Đây là "gộp vào section đang có" đúng ý spec §2.1 (không đẻ section mới). Nếu về sau muốn tách
> nhóm trực quan thì bàn riêng — lát này giữ đơn giản như Kho.

---

## 7. Token / màu / spacing (bám `styles/tokens.css`, cấm hex thô)

Bọc `.thsx`, đặt biến cục bộ giống `.xl2` (label-w, bar-h, lane-h). Không thêm `:root`.

| Vai trò | Token |
|---|---|
| Nền trang / nền thẻ | `--paper` / `--canvas` |
| Chữ chính / mờ / rất mờ | `--ink` / `--ash` / `--ash-2` |
| Đường kẻ | `--rule` / `--rule-soft` / `--rule-hair` |
| Accent / bề mặt tô (đang chọn, hover hàng, header) | `--rust` / `--rust-deep` / `--rust-soft` |
| Font chữ / font SỐ-MÃ (giờ, SL, mã) | `--ff-sans` / `--ff-num` + `font-variant-numeric: tabular-nums` |
| Cỡ chữ | `--fs-2xs`…`--fs-xl` · Đậm `--fw-medium`/`--fw-bold` |
| Giãn cách (4px scale) | `--sp-1`…`--sp-8` |
| Bo góc | `--r-2`/`--r-3`/`--r-6` · pill `--r-pill` |
| Bóng drawer/overlay | `--shadow-4` / `--shadow-lg` |

**Pill trạng thái công việc** (`THSX_TT_META`, khuôn `.khsx-pill` — LUÔN có icon + CHỮ, a11y):

| `trang_thai` | Nhãn | Họ màu | Ý |
|---|---|---|---|
| `released` | Chờ làm | `--steel` / `--steel-soft` | đã phát hành, chưa chạy |
| `running` | Đang chạy | `--moss` / `--moss-soft` | có phiên mở (nhịp đập nhẹ trên thanh) |
| `paused` | Tạm dừng | `--amber` / `--amber-soft` | gạch chéo mảnh trên thanh |
| `completed` | Hoàn thành | `--ash` trên nền `--rule-hair` | thanh mờ + tick ✓ |

Thanh **kế hoạch** dùng nền trung tính (`--steel-soft` viền `--rule`); trạng thái chỉ đổi **viền/vân/độ
mờ + pill**, KHÔNG chỉ dựa màu nền (người mù màu vẫn phân biệt). Băng ca / nowline lấy lại token
`.xl2` band (`--rule-soft`, `--rust` cho nowline).

---

## 8. State & tương tác

- **Cửa sổ ngày**: `[tu, den]` mặc định quanh hôm nay (vd tuần chứa hôm nay); nút ◀▶ dời cửa sổ.
  Timeline chỉ vẽ việc có `du_kien_*` giao với cửa sổ; việc thiếu `du_kien_*` gom vào lane "chưa
  định giờ" ở cột trái (không có mốc thì không đặt lên trục).
- **Zoom** Giờ/Ca/Ngày/Tuần, **mặc định Ca**, **nhớ lần cuối** bằng `localStorage`
  (key `thsx.zoom`). Không có "Vừa khít" (đó là nhu cầu của bàn xếp lịch).
- **Khoá lạc quan**: mọi POST gửi `expected_version` = `version` mới nhất từ `chiTiet`/`LenhKetQuaOut`.
  Nhận `LenhKetQuaOut.version` → cập nhật state + đóng dialog. Nếu BE trả **400** (lệch version/ràng
  buộc) → toast cảnh báo + refetch `chiTiet` (không mất chỗ). **403** → toast "ngoài phạm vi".
- **Dialog lý do (bắt buộc theo luật BE, bind đúng):**
  - **Tạm dừng** → `ly_do` **BẮT BUỘC** (BE chặn rỗng). Dialog có ô lý do, nút xác nhận disabled khi trống.
  - **Bắt đầu TRỄ** → nếu `now > du_kien_bat_dau` thì `ly_do_tre` bắt buộc (BE chặn). FE tự so
    `du_kien_bat_dau` với hiện tại để **hiện sẵn** ô lý do; bắt đầu sớm thì bấm thẳng, không hỏi.
  - **Kết thúc TRỄ** → `ly_do_tre` chỉ bắt buộc khi trễ **và chưa** có phiên tạm-dừng nào kèm lý do
    (BE: `ket_thuc` §7.2). FE nên hỏi lý do khi trễ; nếu đã có lý do tạm dừng thì BE cho qua.
- **Điều kiện bật nút** (khớp tiền điều kiện service — chặn sớm ở FE cho đỡ round-trip, nhưng BE vẫn là trọng tài):
  - **Bắt đầu**: bật khi `trang_thai ∈ {released, paused}` **và** roster có ≥1 người `la_luong_khoan`
    (BE: `bat_dau` cần ≥1 lương khoán). Thiếu → nút mờ + gợi ý "cần ≥1 thợ lương khoán".
  - **Tạm dừng**: bật khi `running`. **Kết thúc**: bật khi `running` hoặc `paused`.
  - **Giao người**: chặn khi `completed`. Bước `loai_buoc=="to"` chỉ nhận người `la_luong_khoan`
    (BE chặn công nhật) → nếu FE có cờ chế độ lương thì lọc/cảnh báo trước.
  - **Rút**: chỉ với phân công `active`.
- **Realtime**: `eventTick` (từ SSE) đổi → bàn refetch `workItems`; drawer đang mở refetch `chiTiet`.
  Sau mỗi POST của chính mình cũng refetch để đồng bộ (BE là nguồn mốc thời gian, FE không tự đặt giờ).
- **Rỗng/lỗi/tải**: `EmptyState`("Chưa có việc phát hành cho tổ này") · `BangLoi`+Tải lại · `Skeleton`.
- **A11y & thợ ít chữ**: nút hành động TO, có icon + chữ; pill luôn kèm chữ; bàn phím mở/đóng drawer.

---

## 9. Khung "PHA SAU" — chừa chỗ, KHÔNG dựng (chưa có API)

Vẽ khối xám mờ, nhãn "Sắp có", control `disabled`. Đừng gọi/bịa endpoint.

| Mảnh | Vì sao hoãn |
|---|---|
| **Nhập / Xuất sản lượng** (§8 spec) | Chưa có bảng/endpoint sản lượng. `so_luong_vao/ra` hiện chỉ là số **kế hoạch** đọc ra, không phải nhập-liệu. |
| **Bàn giao chặng sau** (§8/§11) | Chưa có API handover. |
| **KCS / nghiệm thu** (§ KCS) | `la_kcs`/`la_kcs_cuoi` mới là CỜ đánh dấu, chưa có luồng chấm KCS. |
| **Chấm công – OT theo khoảng tham gia** (§7.3) | BE ghi `khoang_tham_gia` nhưng chưa nối chấm công/OT. |
| **"Số người thực tế ≠ dự kiến → bắt buộc lý do"** | BE **chưa** có field/luật này (không có trong `phan_cong`/`bat_dau`). **KHÔNG** thêm ràng buộc FE — sẽ chặn oan. |
| **Overlay mốc-thật ngay trên timeline bàn** | `/work-items` không trả mốc chạy thật; muốn có phải BE thêm field vào `WorkItemOut`. Lát này so kế-hoạch↔thực-tế nằm trong DRAWER. |

> **Đã bổ sung (không còn pha sau):** endpoint danh nhân viên cho ô "Giao người" —
> `GET /api/san-xuat/teams/{team_id}/nhan-vien`. Ô "Giao người" DỰNG THẬT lát này (không để khung xám).

---

## 10. Rủi ro / ràng buộc cho agent BUILD

1. **KHÔNG kéo–thả, KHÔNG sửa lịch.** Tổ trưởng chỉ đọc timeline + ghi phân công/phiên chạy. Bỏ sạch
   cơ chế drag của `Xl2Gantt` (dễ bê nhầm vì copy từ đó).
2. **Không bịa field.** Mọi field bám §5. Pydantic nuốt field lạ im lặng — type TS phải mirror đúng
   schema, thêm field phải sửa cả BE (ngoài phạm vi lát này).
3. **Trục thời gian: dùng lại `xl2Shared.tsx`** (`buildLinearScale`/`XL2_PX_PER_MIN`/`LABEL_W`/`BAR_H`),
   đừng chép — nhưng **đừng** import `xep-lich-2.css` (đổi tiền tố sang `.thsx`).
4. **Version lạc quan**: luôn gửi `expected_version`; xử lý 400/403 bằng refetch + toast, không nuốt lỗi.
5. **Lý do bắt buộc** đúng 3 chỗ (tạm dừng luôn; bắt đầu/kết thúc chỉ khi trễ) — bind đúng luật BE,
   đừng bắt lý do ở nơi BE không đòi (gây khó chịu) cũng đừng bỏ nơi BE đòi (gây 400).
6. **Node lá + badge + SSE**: sao đúng khuôn Kho (§6). `teams` một cú gọi ra cả list lẫn badge —
   đừng thêm API badge riêng. Nhớ nhánh cổng quyền `moduleKeys` cho `baseId="thuc-hien-sx"`.
7. **Sửa route/schema BE → phải restart uvicorn** (dự án không hot-reload BE) — nhưng lát này FE
   thuần, BE đã sẵn, không cần đụng BE.
8. **Verify sau khi dựng**: `npx tsc` cho FE + xem thật trên dev-browser (styleseed review) — theo
   quy trình 2 bước của dự án (agent BUILD tự chạy, không phải agent này).
9. **CSS token**: chỉ dùng biến `styles/tokens.css`; nền phụ dùng `--paper`/`--canvas`, đừng
   hardcode kem/cam (bẫy "tự nhiên có sắc cam" đã dính nhiều lần).
