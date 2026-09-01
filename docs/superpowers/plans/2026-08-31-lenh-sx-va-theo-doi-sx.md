# Lệnh sản xuất & Theo dõi sản xuất — Kế hoạch cài đặt

> **Cho người/agent thi công:** BẮT BUỘC dùng `superpowers:executing-plans` (hoặc
> `superpowers:subagent-driven-development`) để chạy plan này theo từng task. Các bước
> dùng checkbox `- [ ]` để đánh dấu.

**Goal:** Dựng hai màn CHỈ ĐỌC — "Lệnh sản xuất" (hồ sơ lệnh xuyên suốt từ phát hành tới
giao hàng) và "Theo dõi sản xuất" (Kanban · Theo máy · Theo ca · Gantt) — tổng hợp trên
dữ liệu vận hành đã có, cộng ba lỗ hổng dữ liệu nguồn phải vá ở màn Thực hiện SX.

**Architecture:** Không đẻ luồng sản xuất thứ hai. Một tầng đọc `services/lenh_sx/` nạp
theo LÔ từ các bảng đang chạy (`lsx`, `san_xuat_cong_viec`, `san_xuat_phien_chay`,
`san_xuat_batch`, `san_xuat_kcs_*`, `san_xuat_kho_*`, `ky_thuat_yeu_cau_sua`,
`delivery_*`) rồi tính dẫn xuất lúc đọc — theo đúng precedent `lsx_tong_quan.py`. Router
chỉ điều phối; mọi luật nằm ở service. Hai ô quyền mới, phạm vi bám `orders.sale_user_id`.

**Tech Stack:** FastAPI · SQLAlchemy 2 (Mapped/mapped_column) · Pydantic v2 · pytest ·
React 18 + TypeScript + Vite · SSE (`app/realtime.py`) · ReportLab (PDF).

**Spec nguồn:** `docs/spec-thuc-hien-san-xuat.md` (lớp thực thi đang chạy) ·
`docs/spec-xep-lich-2.md` (lịch/phát hành) · `docs/prd-giao-hang.md` · bản chốt hội thoại
31/08/2026 (ghi lại nguyên văn ở §"Chốt thiết kế" bên dưới).

---

## Global Constraints

- Ngôn ngữ code/comment: tiếng Việt cho nghiệp vụ, thuật ngữ kỹ thuật giữ tiếng Anh.
- **KHÔNG chạy `./init.ps1`.** Verify bằng `python -m pytest <file cụ thể> -q` trong
  `backend/` và `npx tsc --noEmit` trong `frontend/`.
- **KHÔNG `python -c` trần trong `backend/`** — nó trỏ vào Postgres DEV thật. Muốn thăm dò
  thì viết test tạm rồi chạy pytest.
- **KHÔNG commit / push** cho tới khi chủ dự án yêu cầu. Mỗi task kết thúc bằng bước
  "Dừng — báo cáo", không phải `git commit`.
- Bảng MỚI → `create_all` tự dựng, KHÔNG migration. Cột thêm vào bảng CŨ → BẮT BUỘC viết
  migration idempotent trong `backend/app/db_migrations.py` + cập nhật `docs/DB_SCHEMA.md`
  cùng lúc (`backend/tests/test_schema_documented.py` sẽ đỏ nếu quên).
- Boolean: `server_default` dùng `false()`/`true()` của SQLAlchemy, **không** `"0"`/`"1"`.
- Migration chỉ dùng SQL thuần đích danh cột. KHÔNG ORM full-select trong migration.
- Hai màn mới **không có một nút ghi nào**: không tạo LSX, không bắt đầu/tạm dừng/tiếp
  tục/huỷ, không sửa routing. Mọi thao tác sản xuất vẫn ở màn Thực hiện SX.
- Response của hai màn mới **không được chứa** giá thành, đơn giá máy, lương khoán, đơn giá
  vật tư.
- Sửa route/schema backend → RESTART uvicorn (không hot-reload đáng tin ở đây).
- Số dẫn xuất TÍNH LÚC ĐỌC, không cache cột.
- Verify UI: **đúng một** instance dev-browser, đúng một named page. Xem §"Nghi thức soi
  màn" — bắt buộc cho mọi task có FE.

---

## Chốt thiết kế (khác bản plan trước — đọc trước khi làm)

Bản plan trước đề xuất dựng lại nhiều thứ đã có trong repo. Sáu điểm dưới đây là bản đã
đối chiếu code ngày 31/08/2026 và là bản có hiệu lực.

**1. Ranh giới với màn "Kế hoạch sản xuất" đang chạy.**
`KeHoachSXPage.tsx` (module `san_xuat`) là bàn của người **LẬP**: mọi trạng thái lệnh, có
nút ghi, sửa routing, chuyển trạng thái. Màn "Lệnh sản xuất" mới là bàn của người **HỎI**:
chỉ lệnh `trang_thai = 'da_phat_hanh'`, không nút ghi, và kéo dài tới KCS · nhập kho ·
giao hàng — quãng mà màn Kế hoạch SX không nói gì.

**2. Hai ô quyền mới, phạm vi KHÁC `san_xuat`.**
`routers/lsx.py:88 _owner_ids_for_scope` hiện lọc theo `lsx.nguoi_phu_trach_id` /
`lsx.created_by` — phạm vi của người **làm** lệnh. Sale cần phạm vi theo
`orders.sale_user_id` — phạm vi của người **bán**. Hai nghĩa khác nhau, nên tách khoá
`lenh_san_xuat` + `theo_doi_san_xuat`; sửa đè nghĩa `san_xuat` sẽ làm tổ trưởng/thợ (scope
`own`) mất sạch lệnh ở màn Kế hoạch SX.

**3. Phiên máy ĐÃ CÓ — chỉ thiếu đổi máy.**
`san_xuat_phien_chay` (`models/san_xuat_thuc_thi.py:9`) đã mở/đóng đúng theo bắt đầu ·
tạm dừng · kết thúc, kèm khoảng tham gia từng người. Thiếu đúng hai thứ: cột `may_id` trên
phiên, và đường đổi máy khi đang chạy.

**4. Sự cố KHÔNG đẻ bảng mới.**
`ky_thuat_yeu_cau_sua` (`models/ky_thuat_may.py:148`, ô quyền `yeu_cau_sua_chua` "Báo máy
hỏng") đã có: máy · bộ phận hỏng · mô tả · mức độ · `may_dung` · người báo · thời điểm ·
ảnh (`KyThuatMayAnh`) · `tao_phieu_tu_yeu_cau()` sinh phiếu sửa chữa · báo tổ sửa chữa.
Thiếu đúng: neo về công việc/LSX, và nhánh "Dừng sản xuất" tạm dừng work item trong CÙNG
transaction.

**5. KHÔNG đẻ khái niệm `production_group`.**
`san_xuat_nhom` + `san_xuat_nhom_lsx` đã là nhóm thành phẩm (Ruột + Bìa → Kỷ yếu). Dùng
`nhom_id`. Kho thành phẩm (`san_xuat_kho_hang` · `san_xuat_kho_lot` · `san_xuat_nhap_kho_yc`)
đã có registry, lot, yêu cầu nhập, xác nhận từng phần, đóng nhóm thiếu. Thiếu đúng một
thứ: **kho đích** (`kho_id`).

**6. KHÔNG thêm cột `release_version` lên `lsx`.**
Phiên bản phát hành đã có: `san_xuat_goi_phat_hanh.version_hien_tai` +
`san_xuat_phien_ban`, và `san_xuat_cong_viec.phien_ban_so` bump ở
`services/san_xuat/release_update.py:172`. QR chỉ cần đọc lại con số đó.

**Hệ quả:** khối lượng thật gom vào ba việc vá dữ liệu nguồn (Đợt B), một tầng đọc (Đợt C),
và hai màn FE (Đợt D, F).

---

## Bản đồ file

**Tạo mới — backend**

| File | Trách nhiệm |
|---|---|
| `backend/app/services/lenh_sx/__init__.py` | Gói tầng đọc |
| `backend/app/services/lenh_sx/pham_vi.py` | Phạm vi theo `orders.sale_user_id` cho 2 ô quyền mới |
| `backend/app/services/lenh_sx/boi_canh.py` | Nạp theo LÔ mọi bảng nguồn cho một tập `lsx_id` |
| `backend/app/services/lenh_sx/tien_do.py` | Tiến độ có trọng số + dự kiến hoàn thành |
| `backend/app/services/lenh_sx/trang_thai.py` | Trạng thái tổng hợp + cờ cảnh báo |
| `backend/app/services/lenh_sx/danh_sach.py` | Danh sách + KPI |
| `backend/app/services/lenh_sx/ho_so.py` | Hồ sơ chi tiết + timeline |
| `backend/app/services/lenh_sx/bang_theo_doi.py` | Kanban · máy · ca · gantt |
| `backend/app/services/lenh_sx/phieu_cong_nghe.py` | PDF A4 + QR |
| `backend/app/routers/lenh_san_xuat.py` | API `/api/lenh-san-xuat` |
| `backend/app/routers/theo_doi_san_xuat.py` | API `/api/theo-doi-san-xuat` |
| `backend/app/schemas/lenh_san_xuat.py` | DTO danh sách + hồ sơ |
| `backend/app/schemas/theo_doi_san_xuat.py` | DTO 4 tab |

**Sửa — backend**

| File | Sửa gì |
|---|---|
| `backend/app/seed.py` | 2 dòng `MODULES` + cấp quyền trong `ROLES` |
| `backend/app/db_migrations.py` | mg 0246 → 0249 |
| `backend/app/models/san_xuat_thuc_thi.py` | `SanXuatPhienChay.may_id` |
| `backend/app/models/ky_thuat_may.py` | `YeuCauSuaChua.cong_viec_id` + `.lsx_id` |
| `backend/app/models/san_xuat_kho.py` | `SanXuatNhapKhoYc.kho_id` + `SanXuatKhoLot.kho_id` |
| `backend/app/services/san_xuat/thuc_thi.py` | `doi_may()`; `bat_dau()` ghi `may_id` vào phiên |
| `backend/app/services/san_xuat/kho.py` | `kho_xac_nhan_nhap(..., kho_id)` |
| `backend/app/services/ky_thuat_may_service.py` | `tao_yeu_cau()` nhận neo sản xuất |
| `backend/app/routers/san_xuat.py` | 2 endpoint mới (`doi-may`, `su-co`) |
| `backend/app/main.py` | Mount 2 router mới |
| `docs/DB_SCHEMA.md` | 5 cột mới |
| `docs/RBAC_QUYEN_THEO_MODULE.md` | 2 ô quyền mới |

**Tạo mới — frontend**

| File | Trách nhiệm |
|---|---|
| `frontend/src/pages/LenhSanXuatPage.tsx` | Danh sách + KPI + tab trạng thái |
| `frontend/src/pages/LenhSxHoSoView.tsx` | Hồ sơ LSX chỉ đọc |
| `frontend/src/pages/lenh-san-xuat.css` | Style hai màn hồ sơ |
| `frontend/src/pages/TheoDoiSanXuatPage.tsx` | Khung 4 tab + bộ lọc chung |
| `frontend/src/pages/TdsxKanban.tsx` | Tab Kanban |
| `frontend/src/pages/TdsxTheoMay.tsx` | Tab Theo máy |
| `frontend/src/pages/TdsxTheoCa.tsx` | Tab Theo ca |
| `frontend/src/pages/theo-doi-san-xuat.css` | Style 4 tab |

**Sửa — frontend**

| File | Sửa gì |
|---|---|
| `frontend/src/components/Sidebar.tsx` | 2 mục menu dưới section `san-xuat` |
| `frontend/src/components/AppShell.tsx` | 2 nhánh render + deep link QR |
| `frontend/src/components/appShellRealtime.ts` | 2 khoá vào `REALTIME_MODULES` |
| `frontend/src/api/client.ts` | Hàm gọi + type cho 2 nhóm endpoint |

---

## Nghi thức soi màn (BẮT BUỘC cho mọi task có FE)

Không được báo "xong" một màn khi chưa chạy hết nghi thức này trên chính màn đó và dán
được output. Đây là chỗ hay gian lận nhất: nhìn ảnh chụp rồi kết luận.

### Luật cứng

- **ĐÚNG MỘT trình duyệt.** Mọi script chạy với `dev-browser --browser svn`, và **đúng một**
  named page tên `"svn"`. Cấm `browser.newPage()`, cấm tên page thứ hai. Nếu daemon đang
  giữ browser khác: `dev-browser browsers` để xem, `dev-browser stop` trước khi mở lại.
- **Soi hết MỘT màn rồi mới sang màn khác.** Không nhảy qua lại.
- **Không dùng API/curl thay cho bất kỳ bước thao tác nào**, kể cả để dựng dữ liệu nhanh.
  Nếu buộc phải, phải nói rõ ngay trong báo cáo, không đợi bị hỏi.
- Báo cáo phải liệt kê **cụ thể**: bấm nút nào, gõ gì, thấy gì. Không viết "đã test UI".

### Bước 0 — Dựng máy chủ (một lần cho cả đợt)

BE `127.0.0.1:8000`, FE `localhost:5173`. Đẻ tiến trình tách rời bằng WMI (Bash nền và
`Start-Process` đều chết khi hết phiên):

```powershell
$be = 'cmd /c "cd /d D:\jobs\SVN\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"'
([wmiclass]'Win32_Process').Create($be) | Out-Null
$fe = 'cmd /c "cd /d D:\jobs\SVN\frontend && npm run dev"'
([wmiclass]'Win32_Process').Create($fe) | Out-Null
```

### Bước 1 — Mở đúng một trang + đăng nhập

```bash
dev-browser --browser svn <<'EOF'
const page = await browser.getPage("svn");
await page.setViewportSize({ width: 1440, height: 900 });
await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
if (await page.locator('input[name="username"], input[type="text"]').first().isVisible().catch(() => false)) {
  await page.fill('input[name="username"], input[type="text"]', "admin");
  await page.fill('input[type="password"]', "admin123");
  await page.click('button[type="submit"]');
  await page.waitForLoadState("networkidle");
}
console.log(JSON.stringify({ url: page.url(), title: await page.title() }));
EOF
```

Mật khẩu là `admin123` (`SEED_ADMIN_PASSWORD`), không phải `123456`. Nếu `page.fill` không
ăn vì React giữ state, dùng native setter:

```js
await page.evaluate(() => {
  const set = (el, v) => {
    const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    s.call(el, v);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  };
  set(document.querySelector('input[type="text"]'), "admin");
  set(document.querySelector('input[type="password"]'), "admin123");
});
```

### Bước 2 — Kiểm kê mọi thứ bấm được trên màn

```bash
dev-browser --browser svn <<'EOF'
const page = await browser.getPage("svn");
const els = await page.evaluate(() => {
  const sel = 'button,a[href],[role="button"],[role="tab"],[role="switch"],input,select,textarea,summary,[tabindex]:not([tabindex="-1"])';
  return [...document.querySelectorAll(sel)].map((e, i) => ({
    i,
    tag: e.tagName.toLowerCase(),
    type: e.getAttribute("type"),
    text: (e.innerText || e.value || e.getAttribute("aria-label") || e.getAttribute("placeholder") || "").trim().slice(0, 70),
    disabled: !!e.disabled || e.getAttribute("aria-disabled") === "true",
    an: e.offsetParent === null,
  }));
});
console.log(JSON.stringify(els, null, 2));
console.log("TONG=" + els.length + " HIEN=" + els.filter(e => !e.an).length);
EOF
```

Danh sách này là **checklist bấm**. Mọi phần tử `an: false` phải được bấm/gõ ít nhất một
lần trước khi báo xong màn. Phần tử `disabled: true` phải giải thích được vì sao khoá.

### Bước 3 — Cuộn hết bốn hướng, bắt tràn ngang

```bash
dev-browser --browser svn <<'EOF'
const page = await browser.getPage("svn");
const o = await page.evaluate(() => {
  const d = document.documentElement;
  const cuon = [...document.querySelectorAll("*")]
    .filter(e => e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2)
    .map(e => ({
      cls: String(e.className || "").slice(0, 70),
      sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight,
      ox: getComputedStyle(e).overflowX, oy: getComputedStyle(e).overflowY,
    }));
  return { docW: d.scrollWidth, viewW: d.clientWidth, tran_ngang_body: d.scrollWidth > d.clientWidth, cuon: cuon.slice(0, 25) };
});
console.log(JSON.stringify(o, null, 2));
EOF
```

Luật: `tran_ngang_body` phải là `false`. Bảng/Gantt rộng phải cuộn **trong khung riêng**
(`overflowX: auto`), không đẩy cả trang. Sau đó cuộn thật để lộ nội dung cuối:

```bash
dev-browser --browser svn <<'EOF'
const page = await browser.getPage("svn");
for (const [dx, dy, ten] of [[0, 4000, "xuong"], [0, -4000, "len"], [4000, 0, "phai"], [-4000, 0, "trai"]]) {
  await page.mouse.move(700, 500);
  await page.mouse.wheel(dx, dy);
  await page.waitForTimeout(400);
  await saveScreenshot(await page.screenshot(), `cuon-${ten}.png`);
}
console.log("da cuon 4 huong");
EOF
```

### Bước 4 — Quét bấm, bắt lỗi ngầm

Handler phải đăng ký trong CÙNG script với vòng bấm (script thoát là handler mất).

```bash
dev-browser --browser svn --timeout 180 <<'EOF'
const page = await browser.getPage("svn");
const loi = [];
page.on("console", m => { if (m.type() === "error") loi.push("console: " + m.text().slice(0, 200)); });
page.on("pageerror", e => loi.push("pageerror: " + String(e).slice(0, 200)));
page.on("response", r => { if (r.status() >= 400) loi.push(`http ${r.status()} ${r.url().slice(0, 140)}`); });

const nut = page.locator('button:visible, [role="tab"]:visible').filter({ hasNotText: /Đăng xuất/ });
const n = await nut.count();
for (let i = 0; i < n; i++) {
  const t = (await nut.nth(i).innerText().catch(() => "")).trim().slice(0, 40);
  await nut.nth(i).click({ timeout: 3000 }).catch(e => loi.push(`click#${i} "${t}": ${String(e).slice(0, 90)}`));
  await page.waitForTimeout(500);
  await saveScreenshot(await page.screenshot(), `bam-${i}-${t.replace(/[^\w]/g, "_").slice(0, 20)}.png`);
  await page.keyboard.press("Escape").catch(() => {});
}
console.log("da bam " + n + " nut");
console.log(loi.length ? JSON.stringify(loi, null, 2) : "KHONG CO LOI");
EOF
```

Luật: khối cuối phải in `KHONG CO LOI`. Mỗi dòng lỗi phải được vá hoặc giải thích tại sao
vô hại (kèm bằng chứng), không được bỏ qua.

### Bước 5 — Bề rộng điện thoại

```bash
dev-browser --browser svn <<'EOF'
const page = await browser.getPage("svn");
await page.setViewportSize({ width: 390, height: 844 });
await page.reload({ waitUntil: "networkidle" });
const o = await page.evaluate(() => ({
  tran_ngang: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  docW: document.documentElement.scrollWidth,
  viewW: document.documentElement.clientWidth,
}));
await saveScreenshot(await page.screenshot({ fullPage: true }), "dienthoai.png");
console.log(JSON.stringify(o));
await page.setViewportSize({ width: 1440, height: 900 });
EOF
```

### Bước 6 — Chạy `styleseed-design-review` trên các file vừa dựng, xử lý phát hiện có nghĩa.

### Bước 7 — Kết luận

Chỉ được viết "màn X xong" khi dán được: số phần tử kiểm kê, số nút đã bấm, dòng
`KHONG CO LOI`, `tran_ngang_body: false` ở cả 1440 và 390, và danh sách ảnh chụp. Thiếu
một thứ thì trạng thái là "chưa xong".

---

# ĐỢT A — Hai ô quyền + phạm vi theo Sale

### Task 1: Hai ô quyền `lenh_san_xuat` và `theo_doi_san_xuat`

**Files:**
- Modify: `backend/app/seed.py` (khối `MODULES` quanh dòng 62; các map trong `ROLES`)
- Modify: `backend/app/db_migrations.py` (cuối file, sau mg 0245)
- Modify: `frontend/src/components/Sidebar.tsx:93-108`
- Modify: `docs/RBAC_QUYEN_THEO_MODULE.md`
- Test: `backend/tests/test_lenh_sx_quyen.py`

**Interfaces:**
- Produces: khoá module `"lenh_san_xuat"`, `"theo_doi_san_xuat"`; nav id `"lenh-san-xuat"`,
  `"theo-doi-san-xuat"`.

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_quyen.py
"""Hai ô quyền mới của khối Sản xuất: có mặt trong danh mục module, và vai Kinh doanh
được cấp theo ĐÚNG phạm vi của `don_hang_ban` (phạm vi đơn hàng họ đang thấy)."""
from __future__ import annotations


def _dang_nhap(client, seed_credentials) -> str:
    r = client.post("/api/auth/login", json=seed_credentials)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_hai_module_moi_co_trong_danh_muc(client, seed_credentials):
    token = _dang_nhap(client, seed_credentials)
    r = client.get("/api/rbac/modules", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    keys = {m["key"] for m in r.json()}
    assert "lenh_san_xuat" in keys
    assert "theo_doi_san_xuat" in keys


def test_vai_kinh_doanh_duoc_cap_theo_pham_vi_don_hang(client, seed_credentials):
    token = _dang_nhap(client, seed_credentials)
    r = client.get("/api/rbac/roles", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    for vai in r.json():
        quyen = {p["module_key"]: p for p in vai.get("permissions", [])}
        dhb = quyen.get("don_hang_ban")
        if not dhb or not dhb.get("can_read"):
            continue
        for khoa in ("lenh_san_xuat", "theo_doi_san_xuat"):
            assert khoa in quyen, f"vai {vai['name']} thiếu {khoa}"
            assert quyen[khoa]["can_read"] is True
            assert quyen[khoa]["scope"] == dhb["scope"]
```

- [ ] **Bước 2: Chạy để thấy đỏ**

Chạy: `cd backend && python -m pytest tests/test_lenh_sx_quyen.py -q`
Kỳ vọng: FAIL — `"lenh_san_xuat" in keys` sai.

Nếu tên endpoint RBAC khác (`/api/rbac/modules`, `/api/rbac/roles`), mở
`backend/app/routers/rbac.py` đọc đúng đường rồi sửa test — **không** đổi mục tiêu test.

- [ ] **Bước 3: Thêm 2 dòng module vào seed**

Trong `backend/app/seed.py`, ngay sau `("xep_lich_2", "Xếp lịch công đoạn"),`:

```python
    # HAI MÀN CHỈ ĐỌC (31/08/2026). Phạm vi của chúng bám `orders.sale_user_id` — phạm vi của
    # người BÁN — khác hẳn `san_xuat` vốn bám `lsx.nguoi_phu_trach_id` (người LÀM). Đó là lý do
    # phải là hai khoá riêng chứ không tick thêm bit vào `san_xuat`: sửa nghĩa scope của
    # `san_xuat` là tổ trưởng/thợ (scope `own`) mất sạch lệnh ở màn Kế hoạch SX.
    ("lenh_san_xuat", "Lệnh sản xuất"),
    ("theo_doi_san_xuat", "Theo dõi sản xuất"),
```

- [ ] **Bước 4: Cấp quyền trong `ROLES`**

Với mỗi vai đang có `"don_hang_ban": _read(<scope>)` hoặc `_full(<scope>)`, thêm hai dòng
cùng scope đó. Với vai đang có `"san_xuat": _read(SCOPE_ALL)` / `_full(SCOPE_ALL)` /
`_rcu(SCOPE_ALL)` (Kế hoạch SX, Giám đốc, Admin), thêm hai dòng `_read(SCOPE_ALL)`.

Ví dụ khối vai Kinh doanh:

```python
            "don_hang_ban": _full(SCOPE_OWN),
            # Xem lệnh SX của ĐƠN mình phụ trách: cùng phạm vi với đơn hàng, không rộng hơn.
            "lenh_san_xuat": _read(SCOPE_OWN),
            "theo_doi_san_xuat": _read(SCOPE_OWN),
```

Không cấp cho vai Thợ/Tổ trưởng: họ vào bằng màn Thực hiện SX.

- [ ] **Bước 5: Migration 0246 — chép quyền cho vai TỰ TẠO**

`seed_roles` upsert lại vai seed mỗi lần khởi động, nhưng vai do người dùng tự tạo thì
không. Thêm vào cuối `backend/app/db_migrations.py`:

```python
_HAI_MAN_CHI_DOC = (
    ("lenh_san_xuat", "Lệnh sản xuất"),
    ("theo_doi_san_xuat", "Theo dõi sản xuất"),
)


def _migrate_hai_man_chi_doc(db) -> None:
    """Hai ô quyền chỉ-đọc của khối Sản xuất (31/08/2026): Lệnh sản xuất · Theo dõi sản xuất.

    Vai SEED do `seed_roles` upsert lại mỗi lần khởi động nên không cần backfill. Migration này
    lo vai NGƯỜI DÙNG TỰ TẠO: chép nguyên dòng `don_hang_ban` sang hai khoá mới, giữ nguyên
    `scope` — phạm vi lệnh SX phải bằng đúng phạm vi đơn hàng người đó đang thấy, không rộng hơn.
    Chỉ chép quyền ĐỌC: hai màn này không có thao tác ghi nào.

    Idempotent: chạy lại không đẻ hàng trùng.
    """
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    if "modules" not in tables or "role_permissions" not in tables:
        return
    for key, label in _HAI_MAN_CHI_DOC:
        db.execute(
            text("INSERT INTO modules (key, label, created_at) "
                 "SELECT :k, :l, CURRENT_TIMESTAMP "
                 "WHERE NOT EXISTS (SELECT 1 FROM modules WHERE key = :k)"),
            {"k": key, "l": label},
        )
    cols = sorted(_existing_columns(insp, "role_permissions"))
    # Chỉ giữ bit ĐỌC; mọi bit ghi ép về FALSE. `scope` chép nguyên.
    doc_bits = {"can_read", "can_view_stock"}
    chep = [c for c in cols if c not in ("id", "module_key")]
    for key, _label in _HAI_MAN_CHI_DOC:
        chon = []
        for c in chep:
            if c == "scope":
                chon.append("rp.scope")
            elif c.startswith("can_") and c not in doc_bits:
                chon.append("FALSE")
            else:
                chon.append(f"rp.{c}")
        db.execute(
            text(
                f"INSERT INTO role_permissions (module_key, {', '.join(chep)}) "
                f"SELECT :k, {', '.join(chon)} FROM role_permissions rp "
                "WHERE rp.module_key = 'don_hang_ban' AND rp.can_read = TRUE "
                "AND NOT EXISTS (SELECT 1 FROM role_permissions x "
                "                WHERE x.role_id = rp.role_id AND x.module_key = :k)"
            ),
            {"k": key},
        )
    db.commit()


MIGRATIONS.append(("0246_hai_man_chi_doc_san_xuat", _migrate_hai_man_chi_doc))
```

- [ ] **Bước 6: Hai mục menu**

Trong `frontend/src/components/Sidebar.tsx`, thêm ngay sau mục `xep-lich-cong-doan-2`:

```tsx
      // HAI MÀN CHỈ ĐỌC (31/08/2026) — bàn của người HỎI, không phải người LẬP. Đứng sau Xếp lịch
      // vì chúng chỉ nói về lệnh ĐÃ phát hành: từ đây trở đi là chuyện của xưởng, không sửa được
      // ở đây nữa. Ai muốn sửa lệnh vẫn quay lên "Kế hoạch sản xuất".
      { id: "lenh-san-xuat", label: "Lệnh sản xuất", icon: "clipboard", module: "lenh_san_xuat" },
      { id: "theo-doi-san-xuat", label: "Theo dõi sản xuất", icon: "activity", module: "theo_doi_san_xuat" },
```

Nếu `"clipboard"` / `"activity"` chưa có trong bộ icon, mở `frontend/src/components/Icon.tsx`
chọn tên đã có — đừng thêm icon mới ở task này.

- [ ] **Bước 7: Chạy test xanh**

Chạy: `cd backend && python -m pytest tests/test_lenh_sx_quyen.py tests/test_rbac_seed.py -q`
Kỳ vọng: PASS toàn bộ.

Chạy: `cd frontend && npx vitest run src/components/Sidebar.test.tsx`
Kỳ vọng: PASS (test này canh `MODULES_BY_NAV_ID` không trùng id).

- [ ] **Bước 8: Cập nhật `docs/RBAC_QUYEN_THEO_MODULE.md`** — thêm mục cho hai ô quyền: bật
  ô này thì thấy được gì, không làm được gì.

- [ ] **Bước 9: Dừng — báo cáo.** Dán output pytest + vitest. KHÔNG commit.

---

### Task 2: Phạm vi theo `orders.sale_user_id`

**Files:**
- Create: `backend/app/services/lenh_sx/__init__.py`
- Create: `backend/app/services/lenh_sx/pham_vi.py`
- Test: `backend/tests/test_lenh_sx_pham_vi.py`

**Interfaces:**
- Consumes: `AuthorizationService.scope_for` · `dept_subtree_ids` (`repositories/org_scope.py`)
- Produces:
  - `sale_ids_theo_pham_vi(db, user, authz, module_key) -> set[int] | None`
    (`None` = thấy tất cả)
  - `loc_lsx_da_phat_hanh(stmt, sale_ids)` — gắn điều kiện vào một `select(Lsx)`
  - `chan_ngoai_pham_vi(db, lsx, sale_ids)` — ném `HTTPException(403)`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_pham_vi.py
"""Phạm vi hai màn chỉ-đọc bám `orders.sale_user_id` — KHÁC `routers/lsx.py` (bám
`lsx.nguoi_phu_trach_id`). Ba mức: own · department (cả cây con) · all. Lệnh của đơn KHÔNG
có sale phụ trách chỉ hiện với `all`. Lệnh CHƯA phát hành không bao giờ hiện."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.lsx import TT_DA_PHAT_HANH, TT_SAN_SANG, Lsx
from app.models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from app.services.lenh_sx import pham_vi

MODULE = "lenh_san_xuat"


class _Authz:
    def __init__(self, scope: str) -> None:
        self._scope = scope

    def scope_for(self, user, module_key: str):  # noqa: ARG002
        return self._scope


def test_own_chi_thay_lenh_cua_don_minh_phu_trach(db, sale_a, sale_b, lenh_cua):
    ids = pham_vi.sale_ids_theo_pham_vi(db, sale_a, _Authz(SCOPE_OWN), MODULE)
    assert ids == {sale_a.id}
    stmt = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), ids)
    thay = {r.id for r in db.execute(stmt).scalars()}
    assert lenh_cua(sale_a) in thay
    assert lenh_cua(sale_b) not in thay


def test_department_thay_ca_cay_con(db, tp_kinh_doanh, sale_a, sale_phong_khac, lenh_cua):
    ids = pham_vi.sale_ids_theo_pham_vi(db, tp_kinh_doanh, _Authz(SCOPE_DEPARTMENT), MODULE)
    assert sale_a.id in ids
    assert sale_phong_khac.id not in ids


def test_all_tra_none(db, admin):
    assert pham_vi.sale_ids_theo_pham_vi(db, admin, _Authz(SCOPE_ALL), MODULE) is None


def test_lenh_chua_phat_hanh_khong_bao_gio_hien(db, admin, lenh_nhap):
    stmt = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), None)
    thay = {r.id for r in db.execute(stmt).scalars()}
    assert lenh_nhap not in thay


def test_don_khong_co_sale_chi_hien_voi_all(db, sale_a, lenh_khong_sale):
    stmt_all = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), None)
    assert lenh_khong_sale in {r.id for r in db.execute(stmt_all).scalars()}
    stmt_own = pham_vi.loc_lsx_da_phat_hanh(select(Lsx), {sale_a.id})
    assert lenh_khong_sale not in {r.id for r in db.execute(stmt_own).scalars()}


def test_ngoai_pham_vi_nem_403(db, sale_a, sale_b, lenh_cua):
    from fastapi import HTTPException
    lsx = db.get(Lsx, lenh_cua(sale_b))
    with pytest.raises(HTTPException) as e:
        pham_vi.chan_ngoai_pham_vi(db, lsx, {sale_a.id})
    assert e.value.status_code == 403
```

Fixture `db` / `admin` / `orders` tái dùng từ `tests/test_san_xuat_board.py` (đã có sẵn,
xem `tests/test_san_xuat_thuc_thi.py:43-51` cho cách import). Bốn fixture còn lại
(`sale_a`, `sale_b`, `sale_phong_khac`, `tp_kinh_doanh`, `lenh_cua`, `lenh_nhap`,
`lenh_khong_sale`) viết mới trong chính file test: tạo `Department` cha-con, `User` gắn
`department_id`, `Order` gắn `sale_user_id`, `Lsx` gắn `order_id` + `trang_thai`.

- [ ] **Bước 2: Chạy để thấy đỏ**

Chạy: `cd backend && python -m pytest tests/test_lenh_sx_pham_vi.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: app.services.lenh_sx`.

- [ ] **Bước 3: Cài đặt**

```python
# backend/app/services/lenh_sx/__init__.py
"""Tầng ĐỌC của hai màn chỉ-đọc "Lệnh sản xuất" và "Theo dõi sản xuất".

KHÔNG có một đường ghi nào trong gói này. Mọi thao tác sản xuất vẫn nằm ở
`services/san_xuat/` (bàn của tổ trưởng) và `services/lsx_service.py` (bàn của kế hoạch).
"""
```

```python
# backend/app/services/lenh_sx/pham_vi.py
"""Phạm vi dữ liệu của hai màn chỉ-đọc — bám `orders.sale_user_id`.

KHÁC `routers/lsx.py::_owner_ids_for_scope`, và khác một cách CỐ Ý. Ở đó phạm vi tính theo
`lsx.nguoi_phu_trach_id` / `lsx.created_by` — "lệnh này ai LÀM". Ở đây là "lệnh này bán cho
ai, ai bán" — câu hỏi của Sale, Trưởng phòng KD, Giám đốc. Dùng chung một hàm cho cả hai
nghĩa thì một trong hai bên sai âm thầm.

Lệnh CHƯA phát hành không thuộc phạm vi của bất kỳ ai ở đây: hai màn này nói về việc đã thả
xuống xưởng. Lệnh nháp/đang lập vẫn xem ở màn Kế hoạch sản xuất.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.lsx import TT_DA_PHAT_HANH, Lsx
from ...models.order import Order
from ...models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ...models.user import User
from ...repositories.org_scope import dept_subtree_ids


def sale_ids_theo_pham_vi(db: Session, user: User, authz, module_key: str) -> set[int] | None:
    """Tập `users.id` của người BÁN mà `user` được nhìn lệnh. `None` = thấy tất cả.

    Thiếu khai scope ⇒ hẹp nhất (`own`), không phải rộng nhất — mở nhầm còn tệ hơn khoá nhầm.
    """
    scope = authz.scope_for(user, module_key) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        dept_ids = dept_subtree_ids(db, user.department_id)
        if dept_ids:
            ids = db.execute(select(User.id).where(User.department_id.in_(dept_ids))).scalars().all()
            return set(ids) | {user.id}
    return {user.id}


def loc_lsx_da_phat_hanh(stmt, sale_ids: set[int] | None):
    """Gắn hai điều kiện vào một `select(Lsx)`: đã phát hành + trong phạm vi người bán.

    `sale_ids is None` ⇒ chỉ lọc trạng thái. Đơn KHÔNG có người bán (`sale_user_id IS NULL`)
    rơi ra ngoài mọi phạm vi hẹp — chỉ `all` thấy, đúng chủ ý: không gán bừa cho ai.
    """
    stmt = stmt.where(Lsx.trang_thai == TT_DA_PHAT_HANH)
    if sale_ids is None:
        return stmt
    return stmt.join(Order, Order.id == Lsx.order_id).where(Order.sale_user_id.in_(sale_ids))


def chan_ngoai_pham_vi(db: Session, lsx: Lsx | None, sale_ids: set[int] | None) -> None:
    """403 khi người dùng gõ thẳng id ngoài phạm vi (hoặc lệnh chưa phát hành).

    Dùng 403 chứ không 404: hai màn này là bàn tra cứu, người dùng CẦN biết "có lệnh đó nhưng
    không thuộc phần việc của bạn" để đi hỏi đúng người, thay vì tưởng gõ nhầm mã.
    """
    if lsx is None or lsx.trang_thai != TT_DA_PHAT_HANH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy lệnh sản xuất đã phát hành")
    if sale_ids is None:
        return
    order = db.get(Order, lsx.order_id)
    if order is not None and order.sale_user_id in sale_ids:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Lệnh sản xuất ngoài phạm vi của bạn")
```

- [ ] **Bước 4: Chạy test xanh**

Chạy: `cd backend && python -m pytest tests/test_lenh_sx_pham_vi.py -q`
Kỳ vọng: 6 passed.

- [ ] **Bước 5: Dừng — báo cáo.** Dán output pytest. KHÔNG commit.

---

# ĐỢT B — Ba lỗ hổng dữ liệu nguồn

Ba task độc lập nhau, làm được theo thứ tự nào cũng được. Cả ba đều đụng màn **Thực hiện
sản xuất** (`ThucHienSxPage.tsx`) — màn có UI, nên mỗi task kết thúc bằng nghi thức soi màn.

### Task 3: Phiên máy mang `may_id` + đường đổi máy

**Files:**
- Modify: `backend/app/models/san_xuat_thuc_thi.py` (class `SanXuatPhienChay`)
- Modify: `backend/app/services/san_xuat/thuc_thi.py` (`bat_dau`; thêm `doi_may`)
- Modify: `backend/app/routers/san_xuat.py` (sau route `bat-dau`)
- Modify: `backend/app/schemas/san_xuat.py`
- Modify: `backend/app/db_migrations.py` (mg 0247)
- Modify: `docs/DB_SCHEMA.md` (mục `san_xuat_phien_chay`, dòng ~4466)
- Modify: `frontend/src/pages/ThsxExecPanels.tsx` + `frontend/src/api/client.ts`
- Test: `backend/tests/test_san_xuat_doi_may.py`

**Interfaces:**
- Consumes: `thuc_thi.bat_dau/tam_dung/ket_thuc`, `SanXuatThucThiRepository.phien_dang_mo`
- Produces: `thuc_thi.doi_may(db, *, user, cong_viec_id, may_id_moi, expected_version=None) -> dict`
  và `POST /api/san-xuat/work-items/{id}/doi-may`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_san_xuat_doi_may.py
"""Đổi máy giữa chừng — bốn luật (§7.2 mở rộng 31/08/2026):

  · Đang CHẠY: đóng phiên máy cũ + mở phiên mới trên máy mới, CÙNG một mốc thời gian.
  · Đang TẠM DỪNG: chỉ đổi máy được phân công, KHÔNG mở phiên (mở khi bấm Tiếp tục).
  · Không bao giờ có hai phiên mở trên cùng một công việc.
  · Giờ máy = tổng khoảng phiên ĐÃ ĐÓNG + phần phiên đang chạy — đổi máy không làm mất giờ cũ.
"""
from __future__ import annotations

import pytest

from app.models.san_xuat import CV_DANG_CHAY, CV_TAM_DUNG
from app.models.san_xuat_thuc_thi import PHIEN_TAM_DUNG, SanXuatPhienChay
from app.services.san_xuat import thuc_thi

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)


def test_doi_may_khi_dang_chay_dong_phien_cu_mo_phien_moi(db, cv_dang_chay, to_truong):
    cv = cv_dang_chay
    may_cu = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).one().may_id
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=may_cu + 1)

    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).order_by(SanXuatPhienChay.so_thu_tu).all()
    assert len(phien) == 2
    assert phien[0].ket_thuc is not None and phien[0].may_id == may_cu
    assert phien[1].ket_thuc is None and phien[1].may_id == may_cu + 1
    assert phien[0].ket_thuc == phien[1].bat_dau       # không hở, không chồng
    assert cv.trang_thai == CV_DANG_CHAY
    assert cv.may_id == may_cu + 1


def test_doi_may_khi_tam_dung_khong_mo_phien(db, cv_tam_dung, to_truong):
    cv = cv_tam_dung
    truoc = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).count()
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv.id, may_id_moi=999)
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).count() == truoc
    assert cv.trang_thai == CV_TAM_DUNG
    assert cv.may_id == 999


def test_khong_bao_gio_hai_phien_mo(db, cv_dang_chay, to_truong):
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=777)
    thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=778)
    mo = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv_dang_chay.id, ket_thuc=None).count()
    assert mo == 1


def test_doi_sang_chinh_may_dang_chay_bi_chan(db, cv_dang_chay, to_truong):
    with pytest.raises(ValueError, match="đang chạy"):
        thuc_thi.doi_may(db, user=to_truong, cong_viec_id=cv_dang_chay.id, may_id_moi=cv_dang_chay.may_id)


def test_api_doi_may_gate_quyen(client, seed_credentials):
    r = client.post("/api/auth/login", json=seed_credentials)
    token = r.json()["access_token"]
    r = client.post("/api/san-xuat/work-items/1/doi-may", json={"may_id": 2},
                    headers={"Authorization": f"Bearer {token}"})
    # Admin là Giám đốc, KHÔNG có bit `can_assign_work` → 403 (cùng đường dây với `bat-dau`).
    assert r.status_code == 403, r.text
```

Fixture `cv_dang_chay`, `cv_tam_dung`, `to_truong` dựng theo mẫu ở
`tests/test_san_xuat_thuc_thi.py` (phần "Dàn cảnh dùng chung", từ dòng 55).

- [ ] **Bước 2: Chạy để thấy đỏ**

Chạy: `cd backend && python -m pytest tests/test_san_xuat_doi_may.py -q`
Kỳ vọng: FAIL — `SanXuatPhienChay` chưa có `may_id`.

- [ ] **Bước 3: Thêm cột `may_id` vào model**

Trong `backend/app/models/san_xuat_thuc_thi.py`, class `SanXuatPhienChay`, ngay sau
`so_thu_tu`:

```python
    # Máy CHẠY TRONG PHIÊN NÀY. Đứng trên phiên chứ không phải trên công việc: đổi máy giữa
    # chừng đóng phiên cũ + mở phiên mới, nên `san_xuat_cong_viec.may_id` chỉ nói máy HIỆN TẠI,
    # còn giờ máy của từng máy phải đọc từ đây. Soft ref → `may_thiet_bi.id` (convention repo).
    # Nullable: bước chiếm TỔ (`loai_buoc='to'`) không có máy.
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
```

- [ ] **Bước 4: `bat_dau` ghi máy vào phiên**

Trong `backend/app/services/san_xuat/thuc_thi.py`, hàm `bat_dau`, sửa chỗ dựng
`SanXuatPhienChay` (thêm một dòng):

```python
    phien = SanXuatPhienChay(
        cong_viec_id=cv.id,
        so_thu_tu=repo.so_phien(cv.id) + 1,
        may_id=cv.may_id,          # ẢNH CHỤP máy lúc mở phiên — đổi máy sau này đẻ phiên khác
        bat_dau=now,
```

- [ ] **Bước 5: Thêm `doi_may`**

Cuối `backend/app/services/san_xuat/thuc_thi.py`:

```python
def doi_may(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    may_id_moi: int,
    ly_do: str | None = None,
    expected_version: int | None = None,
) -> dict:
    """Đổi máy của một công việc, giữ nguyên lịch sử giờ máy (§7.2 mở rộng 31/08/2026).

    Đang CHẠY: đóng phiên hiện tại (`loai_dong=tam_dung`, ghi lý do "đổi máy") rồi mở NGAY một
    phiên mới trên máy mới với CÙNG mốc `now` — không hở giây nào, vì công việc không thực sự
    dừng. Khoảng tham gia của người cũng đóng-mở theo phiên để phút công không bị đếm hai lần.

    Đang TẠM DỪNG: chỉ đổi máy được phân công. KHÔNG mở phiên — phiên mở khi bấm Tiếp tục, và
    lúc đó `bat_dau()` tự chụp `cv.may_id` mới.

    Chỉ hai trạng thái đó đổi được: việc chưa bắt đầu thì sửa ở bàn xếp lịch, việc đã kết thúc
    thì không còn máy nào để đổi.
    """
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    _kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ công việc đang chạy hoặc tạm dừng mới đổi máy được.")
    if cv.may_id == may_id_moi:
        raise ValueError("Máy mới trùng máy đang chạy — không có gì để đổi.")

    now = _moc()
    may_cu = cv.may_id
    if cv.trang_thai == CV_DANG_CHAY:
        phien_cu = repo.phien_dang_mo(cv.id)
        nguoi = []
        if phien_cu is not None:
            phien_cu.ket_thuc = now
            phien_cu.loai_dong = PHIEN_TAM_DUNG
            phien_cu.ly_do = (ly_do or "Đổi máy").strip()[:255]
            for kh in repo.khoang_mo_cua_phien(phien_cu.id):
                nguoi.append((kh.employee_id, kh.job_grade_id, kh.output_coefficient))
                repo.dong_khoang(kh, now)
        phien_moi = SanXuatPhienChay(
            cong_viec_id=cv.id,
            so_thu_tu=repo.so_phien(cv.id) + 1,
            may_id=may_id_moi,
            bat_dau=now,
            created_by=getattr(user, "id", None),
        )
        repo.add(phien_moi)
        repo.flush()
        for emp_id, bac_id, heso in nguoi:
            repo.add(
                SanXuatKhoangThamGia(
                    cong_viec_id=cv.id,
                    phien_chay_id=phien_moi.id,
                    employee_id=emp_id,
                    bat_dau=now,
                    job_grade_id=bac_id,
                    output_coefficient=heso,
                )
            )

    cv.may_id = may_id_moi
    cv.version += 1
    _audit(db, user, "san_xuat_doi_may", cv, detail=f"may {may_cu} -> {may_id_moi}")
    db.commit()
    return _ket_qua(cv)
```

- [ ] **Bước 6: Endpoint**

Trong `backend/app/schemas/san_xuat.py`:

```python
class DoiMayIn(BaseModel):
    may_id: int
    ly_do: str | None = None
    expected_version: int | None = None
```

Trong `backend/app/routers/san_xuat.py`, ngay sau route `bat-dau` (dòng ~428), sao chép
nguyên bộ decorator/dependency của route đó rồi đổi thân:

```python
@router.post("/work-items/{cong_viec_id}/doi-may", response_model=LenhKetQuaOut)
def doi_may(cong_viec_id: int, body: DoiMayIn, db: DbDep, user: GhiDep) -> LenhKetQuaOut:
    """Đổi máy giữa chừng. CÙNG cửa quyền với Bắt đầu (`can_assign_work` + tổ trưởng của
    CHÍNH tổ) — đổi máy là quyết định điều hành, không phải ghi nhận."""
    try:
        return LenhKetQuaOut(**thuc_thi.doi_may(
            db, user=user, cong_viec_id=cong_viec_id,
            may_id_moi=body.may_id, ly_do=body.ly_do,
            expected_version=body.expected_version,
        ))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
```

Tên `DbDep` / `GhiDep` phải khớp alias thật trong file — đọc route `bat-dau` rồi dùng
đúng tên đó.

- [ ] **Bước 7: Migration 0247**

```python
def _migrate_phien_chay_may_id(db: Session) -> None:
    """`san_xuat_phien_chay.may_id` — máy CHẠY TRONG PHIÊN (31/08/2026).

    Trước đây máy chỉ nằm trên `san_xuat_cong_viec`, nên đổi máy giữa chừng là mất dấu: giờ máy
    của máy cũ bị gán hết sang máy mới. Cột này neo máy lên PHIÊN, phiên đóng là số giờ chốt.

    Backfill: mọi phiên cũ lấy máy hiện tại của công việc — phiên cũ chưa từng đổi máy (chưa có
    đường đổi), nên đó chính là máy nó đã chạy. Raw SQL đích danh cột, KHÔNG ORM full-select.
    No-op khi bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "san_xuat_phien_chay" not in set(insp.get_table_names()):
        return
    if "may_id" in _existing_columns(insp, "san_xuat_phien_chay"):
        return
    db.execute(text("ALTER TABLE san_xuat_phien_chay ADD COLUMN may_id INTEGER"))
    db.execute(text(
        "UPDATE san_xuat_phien_chay SET may_id = ("
        "  SELECT cv.may_id FROM san_xuat_cong_viec cv WHERE cv.id = san_xuat_phien_chay.cong_viec_id)"
    ))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_san_xuat_phien_chay_may_id "
                    "ON san_xuat_phien_chay (may_id)"))
    db.commit()


MIGRATIONS.append(("0247_phien_chay_may_id", _migrate_phien_chay_may_id))
```

- [ ] **Bước 8: `docs/DB_SCHEMA.md`** — thêm dòng `may_id` vào bảng `san_xuat_phien_chay`
  (mục ở dòng ~4466), đúng định dạng cột của các dòng bên cạnh.

- [ ] **Bước 9: Chạy test xanh**

Chạy: `cd backend && python -m pytest tests/test_san_xuat_doi_may.py tests/test_san_xuat_thuc_thi.py tests/test_schema_documented.py -q`
Kỳ vọng: PASS toàn bộ. `test_san_xuat_thuc_thi.py` phải vẫn xanh — nó canh `bat_dau` cũ.

- [ ] **Bước 10: Nút "Đổi máy" trên màn Thực hiện SX**

Trong `frontend/src/pages/ThsxExecPanels.tsx`, thêm nút cạnh nhóm Bắt đầu/Tạm dừng, chỉ
hiện khi `trang_thai` là `dang_chay` hoặc `tam_dung` và bước là `loai_buoc === "may"`. Mở
select máy từ endpoint máy đang có; gọi `api.sanXuat.doiMay(...)` mới thêm vào
`frontend/src/api/client.ts`.

- [ ] **Bước 11: Chạy `npx tsc --noEmit` trong `frontend/`.** Kỳ vọng: 0 lỗi.

- [ ] **Bước 12: NGHI THỨC SOI MÀN trên "Thực hiện sản xuất"** — chạy trọn §Nghi thức, bước
  0→7. Riêng task này phải thao tác thật đủ chuỗi: chọn tổ → mở một công việc → Phân công →
  Bắt đầu → **Đổi máy** → Báo sản lượng → Tạm dừng → **Đổi máy lần hai** → Tiếp tục → Kết
  thúc, và đọc lại panel giờ máy sau mỗi bước để xác nhận giờ cũ không mất.

- [ ] **Bước 13: Dừng — báo cáo.** Dán: output pytest, output tsc, số phần tử kiểm kê, số nút
  đã bấm, dòng `KHONG CO LOI`, tên các ảnh chụp. KHÔNG commit.

---

### Task 4: Sự cố sản xuất nối vào "Báo máy hỏng"

**Files:**
- Modify: `backend/app/models/ky_thuat_may.py` (class `YeuCauSuaChua`)
- Modify: `backend/app/services/ky_thuat_may_service.py` (`tao_yeu_cau`)
- Create: `backend/app/services/san_xuat/su_co.py`
- Modify: `backend/app/routers/san_xuat.py`
- Modify: `backend/app/schemas/san_xuat.py`
- Modify: `backend/app/db_migrations.py` (mg 0248)
- Modify: `docs/DB_SCHEMA.md` (mục `ky_thuat_yeu_cau_sua`, dòng ~3568)
- Modify: `frontend/src/pages/ThsxExecPanels.tsx`
- Test: `backend/tests/test_san_xuat_su_co.py`

**Interfaces:**
- Consumes: `KyThuatMayService.tao_yeu_cau`, `thuc_thi.tam_dung`, `hub.broadcast`
- Produces: `su_co.bao_su_co(db, *, user, cong_viec_id, bo_phan_hong, mo_ta, muc_do, dung_san_xuat, ly_do_dung=None, expected_version=None) -> dict`
  và `POST /api/san-xuat/work-items/{id}/su-co`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_san_xuat_su_co.py
"""Báo sự cố tại tổ — KHÔNG đẻ bảng sự cố mới, dùng `ky_thuat_yeu_cau_sua` ("Báo máy hỏng")
cộng hai cột neo về sản xuất. Hai nhánh:

  · "Dừng sản xuất": MỘT giao dịch — ghi yêu cầu + tạm dừng công việc + đóng phiên máy.
  · "Vẫn chạy": chỉ ghi yêu cầu; đồng hồ máy không dừng.

Và luật quan trọng nhất: tạo yêu cầu HỎNG thì công việc KHÔNG được tạm dừng nửa vời.
"""
from __future__ import annotations

import pytest

from app.models.ky_thuat_may import TT_YC_CHO_TIEP_NHAN, YeuCauSuaChua
from app.models.san_xuat import CV_DANG_CHAY, CV_TAM_DUNG
from app.models.san_xuat_thuc_thi import SanXuatPhienChay
from app.services.san_xuat import su_co

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)


def test_dung_san_xuat_tam_dung_va_dong_phien(db, cv_dang_chay, to_truong):
    cv = cv_dang_chay
    su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv.id, bo_phan_hong="cụm cấp giấy",
                    mo_ta="kẹt giấy liên tục", muc_do="cao", dung_san_xuat=True)

    yc = db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv.id).one()
    assert yc.trang_thai == TT_YC_CHO_TIEP_NHAN
    assert yc.may_dung is True
    assert yc.lsx_id == cv.lsx_id
    assert cv.trang_thai == CV_TAM_DUNG
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).count() == 0


def test_van_chay_khong_dung_dong_ho(db, cv_dang_chay, to_truong):
    cv = cv_dang_chay
    su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv.id, bo_phan_hong="đèn báo",
                    mo_ta="chập chờn", muc_do="thap", dung_san_xuat=False)

    assert db.query(YeuCauSuaChua).filter_by(cong_viec_id=cv.id).count() == 1
    assert cv.trang_thai == CV_DANG_CHAY
    assert db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id, ket_thuc=None).count() == 1


def test_dung_san_xuat_bat_buoc_ly_do(db, cv_dang_chay, to_truong):
    with pytest.raises(ValueError, match="lý do"):
        su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="",
                        mo_ta="x", muc_do="cao", dung_san_xuat=True)


def test_bao_su_co_tren_viec_chua_bat_dau_bi_chan(db, cv_chua_bat_dau, to_truong):
    with pytest.raises(ValueError):
        su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv_chua_bat_dau.id,
                        bo_phan_hong="cụm cấp giấy", mo_ta="x", muc_do="cao", dung_san_xuat=True)


def test_yeu_cau_hien_o_hop_thu_sua_chua(client, seed_credentials, db, cv_dang_chay, to_truong):
    su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv_dang_chay.id, bo_phan_hong="cụm cấp giấy",
                    mo_ta="kẹt", muc_do="cao", dung_san_xuat=True)
    token = client.post("/api/auth/login", json=seed_credentials).json()["access_token"]
    r = client.get("/api/ky-thuat-may/yeu-cau/cho-xu-ly", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["so_luong"] >= 1
```

Khoá `"so_luong"` phải khớp schema thật của `ChoTiepNhanOut` — mở
`backend/app/schemas/ky_thuat_may.py` đọc rồi sửa test cho khớp.

- [ ] **Bước 2: Chạy để thấy đỏ**

Chạy: `cd backend && python -m pytest tests/test_san_xuat_su_co.py -q`
Kỳ vọng: FAIL — `app.services.san_xuat.su_co` chưa tồn tại.

- [ ] **Bước 3: Hai cột neo trên `YeuCauSuaChua`**

Trong `backend/app/models/ky_thuat_may.py`, class `YeuCauSuaChua`, sau `may_id`:

```python
    # NEO SẢN XUẤT (31/08/2026). Yêu cầu báo từ màn Thực hiện SX mang theo công việc đang chạy
    # lúc máy hỏng — nhờ đó hồ sơ lệnh kể được "sự cố này ăn mất bao lâu của lệnh nào", còn tổ
    # sửa chữa biết máy đang cắm vào việc gì mà xếp ưu tiên. Yêu cầu báo từ màn Sửa chữa máy
    # (người ngoài xưởng) để trống hai cột này — nullable, không phải FK cứng, theo convention
    # soft-ref của repo.
    cong_viec_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    lsx_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
```

- [ ] **Bước 4: `tao_yeu_cau` nhận neo**

Trong `backend/app/services/ky_thuat_may_service.py::tao_yeu_cau`, cho phép `data` mang
`cong_viec_id` / `lsx_id` và gán vào bản ghi. Không đổi chữ ký hàm — nó đã nhận `data: dict`.

- [ ] **Bước 5: Service sự cố**

```python
# backend/app/services/san_xuat/su_co.py
"""Báo sự cố tại tổ — MỘT giao dịch, hai nhánh (31/08/2026).

KHÔNG có bảng sự cố riêng. `ky_thuat_yeu_cau_sua` ("Báo máy hỏng") đã là đúng cái cần: máy,
bộ phận hỏng, mô tả, mức độ tự thấy, cờ máy dừng, người báo là tài khoản đang đăng nhập, ảnh
bằng chứng, và một đường tiếp nhận → sinh phiếu sửa chữa đã chạy. Đẻ bảng thứ hai chỉ để có
chữ "sự cố" nghĩa là tổ sửa chữa phải nhìn hai hộp thư.

Nhánh DỪNG SẢN XUẤT phải nguyên tử: ghi yêu cầu · tạm dừng công việc · đóng phiên máy. Rơi
giữa chừng là để lại một công việc "đang chạy" trên cái máy đã hỏng — sản lượng và giờ máy
sau đó đều sai. Nên toàn bộ nằm trong một transaction, và SSE chỉ bắn SAU khi commit.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.san_xuat import CV_DANG_CHAY, CV_TAM_DUNG
from ...realtime import hub
from ..ky_thuat_may_service import KyThuatMayService
from ...repositories.ky_thuat_may_repo import KyThuatMayRepository
from . import thuc_thi


def bao_su_co(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    bo_phan_hong: str,
    mo_ta: str | None,
    muc_do: str,
    dung_san_xuat: bool,
    expected_version: int | None = None,
) -> dict:
    """Ghi một sự cố lên công việc đang chạy/tạm dừng, kèm tuỳ chọn dừng sản xuất."""
    repo = thuc_thi.SanXuatThucThiRepository(db)
    cv = thuc_thi._lay_cong_viec(repo, cong_viec_id)
    thuc_thi._gate(db, user, cv)
    thuc_thi._kiem_version(cv, expected_version)
    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ báo sự cố trên công việc đang chạy hoặc tạm dừng.")
    if not (bo_phan_hong or "").strip():
        raise ValueError("Phải nêu chỗ hỏng — một yêu cầu chỉ có tên máy thì thợ sửa phải đi hỏi lại.")
    if dung_san_xuat and not (mo_ta or "").strip():
        raise ValueError("Dừng sản xuất bắt buộc có lý do — đây là mốc mất giờ máy của lệnh.")
    if cv.may_id is None:
        raise ValueError("Công việc này không chạy máy — không có máy để báo hỏng.")

    svc = KyThuatMayService(db, KyThuatMayRepository(db))
    yc = svc.tao_yeu_cau(
        {
            "may_id": cv.may_id,
            "bo_phan_hong": bo_phan_hong.strip(),
            "mo_ta": (mo_ta or "").strip() or None,
            "muc_do": muc_do,
            "may_dung": bool(dung_san_xuat),
            "cong_viec_id": cv.id,
            "lsx_id": cv.lsx_id,
        },
        actor_id=getattr(user, "id", None),
    )

    if dung_san_xuat and cv.trang_thai == CV_DANG_CHAY:
        # Đi qua CHÍNH `tam_dung` chứ không tự set cờ: mọi luật đóng phiên + đóng khoảng tham gia
        # + audit nằm ở đó. Tự viết một đường thứ hai là ngày nào đó hai đường lệch nhau.
        thuc_thi.tam_dung(db, user=user, cong_viec_id=cv.id,
                          ly_do=f"Sự cố {yc.ma}: {bo_phan_hong.strip()}"[:255])

    db.commit()
    hub.broadcast({"type": "san_xuat_changed", "lsx_id": cv.lsx_id})
    return {"yeu_cau_id": yc.id, "yeu_cau_ma": yc.ma,
            "cong_viec_trang_thai": cv.trang_thai, "version": cv.version}
```

`tam_dung` tự commit — kiểm lại: nếu nó commit ở giữa thì tính nguyên tử vỡ. Nếu đúng vậy,
tách phần lõi của `tam_dung` ra hàm `_tam_dung_khong_commit(db, ...)` và cho cả `tam_dung`
lẫn `bao_su_co` gọi nó, commit ở ngoài. **Đây là bước bắt buộc kiểm, không được bỏ qua** —
viết thêm một test khẳng định rollback:

```python
def test_that_bai_tao_phieu_thi_khong_de_lai_cong_viec_tam_dung(db, cv_dang_chay, to_truong, monkeypatch):
    from app.services import ky_thuat_may_service
    monkeypatch.setattr(ky_thuat_may_service.KyThuatMayService, "tao_yeu_cau",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bể")))
    with pytest.raises(RuntimeError):
        su_co.bao_su_co(db, user=to_truong, cong_viec_id=cv_dang_chay.id,
                        bo_phan_hong="x", mo_ta="y", muc_do="cao", dung_san_xuat=True)
    db.rollback()
    assert db.get(type(cv_dang_chay), cv_dang_chay.id).trang_thai == CV_DANG_CHAY
```

- [ ] **Bước 6: Endpoint + schema** — cùng khuôn với Task 3 bước 6, đường
  `POST /api/san-xuat/work-items/{cong_viec_id}/su-co`, cùng cửa quyền với `tam-dung`.

- [ ] **Bước 7: Migration 0248**

```python
def _migrate_yeu_cau_sua_neo_san_xuat(db: Session) -> None:
    """`ky_thuat_yeu_cau_sua`: thêm `cong_viec_id` + `lsx_id` (31/08/2026).

    Sự cố báo từ màn Thực hiện SX mang theo công việc đang chạy. Yêu cầu cũ (báo từ màn Sửa chữa
    máy) để NULL — không backfill đoán mò: gán nhầm lệnh còn tệ hơn để trống.
    No-op khi bảng chưa có / cột đã có.
    """
    insp = inspect(db.get_bind())
    if "ky_thuat_yeu_cau_sua" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "ky_thuat_yeu_cau_sua")
    for ten in ("cong_viec_id", "lsx_id"):
        if ten not in cols:
            db.execute(text(f"ALTER TABLE ky_thuat_yeu_cau_sua ADD COLUMN {ten} INTEGER"))
            db.execute(text(f"CREATE INDEX IF NOT EXISTS ix_ky_thuat_yeu_cau_sua_{ten} "
                            f"ON ky_thuat_yeu_cau_sua ({ten})"))
    db.commit()


MIGRATIONS.append(("0248_yeu_cau_sua_neo_san_xuat", _migrate_yeu_cau_sua_neo_san_xuat))
```

- [ ] **Bước 8: `docs/DB_SCHEMA.md`** — hai dòng vào mục `ky_thuat_yeu_cau_sua`.

- [ ] **Bước 9: Chạy test xanh**

Chạy: `cd backend && python -m pytest tests/test_san_xuat_su_co.py tests/test_ky_thuat_may.py tests/test_schema_documented.py -q`
Kỳ vọng: PASS toàn bộ (tên file test kỹ thuật máy: kiểm bằng `ls backend/tests | grep ky_thuat`).

- [ ] **Bước 10: Nút "Báo sự cố" trên màn Thực hiện SX** — form: chỗ hỏng · mô tả · mức độ ·
  hai lựa chọn `Dừng sản xuất` / `Vẫn chạy`. Đổ mức độ từ hằng đang dùng ở màn Sửa chữa máy,
  KHÔNG hard-code chuỗi mới.

- [ ] **Bước 11: `npx tsc --noEmit`.** Kỳ vọng 0 lỗi.

- [ ] **Bước 12: NGHI THỨC SOI MÀN trên "Thực hiện sản xuất"**, thao tác đủ chuỗi: Bắt đầu →
  **Báo sự cố / Vẫn chạy** (xác nhận đồng hồ máy vẫn chạy) → **Báo sự cố / Dừng sản xuất**
  (xác nhận công việc chuyển Tạm dừng) → mở màn **Sửa chữa máy** thấy hai yêu cầu ở hộp chờ
  tiếp nhận → tiếp nhận một yêu cầu, thấy phiếu sửa sinh ra.

- [ ] **Bước 13: Dừng — báo cáo.** KHÔNG commit.

---

### Task 5: Kho đích khi xác nhận nhập kho thành phẩm

**Files:**
- Modify: `backend/app/models/san_xuat_kho.py` (`SanXuatNhapKhoYc`, `SanXuatKhoLot`)
- Modify: `backend/app/services/san_xuat/kho.py` (`kho_xac_nhan_nhap`, `_lot_ra`, `_yc_ra`)
- Modify: `backend/app/routers/san_xuat.py` (route `/kho/yeu-cau/{yc_id}/xac-nhan`)
- Modify: `backend/app/schemas/san_xuat.py`
- Modify: `backend/app/db_migrations.py` (mg 0249)
- Modify: `docs/DB_SCHEMA.md`
- Modify: `frontend/src/pages/ThsxG5.tsx`
- Test: `backend/tests/test_san_xuat_kho_dich.py`

**Interfaces:**
- Produces: `kho_xac_nhan_nhap(db, *, user, yc_id, so_luong, kho_id, expected_version=None)`
  — `kho_id` **bắt buộc**; `SanXuatKhoLot.kho_id` để tồn thành phẩm biết nằm ở kho nào.

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_san_xuat_kho_dich.py
"""Nhập kho thành phẩm phải chọn KHO ĐÍCH (31/08/2026).

Không có kho đích thì lot thành phẩm là một con số lơ lửng: không tra được tồn theo kho,
không lập được phiếu xuất giao. Ba luật: bắt buộc chọn, kho phải có thật, và lot ghi lại kho
đã nhận — nhập nhiều lần vào nhiều kho thì mỗi lot mang kho của nó.
"""
from __future__ import annotations

import pytest

from app.models.san_xuat_kho import SanXuatKhoLot
from app.services.san_xuat import kho

from tests.test_san_xuat_kho import (  # noqa: F401
    db, yc_nhap_kho, nhan_vien_kho, kho_a, kho_b,
)


def test_thieu_kho_dich_bi_chan(db, yc_nhap_kho, nhan_vien_kho):
    with pytest.raises((ValueError, TypeError)):
        kho.kho_xac_nhan_nhap(db, user=nhan_vien_kho, yc_id=yc_nhap_kho.id, so_luong=10)


def test_kho_khong_ton_tai_bi_chan(db, yc_nhap_kho, nhan_vien_kho):
    with pytest.raises(ValueError, match="[Kk]ho"):
        kho.kho_xac_nhan_nhap(db, user=nhan_vien_kho, yc_id=yc_nhap_kho.id, so_luong=10, kho_id=999999)


def test_lot_mang_kho_da_nhan(db, yc_nhap_kho, nhan_vien_kho, kho_a, kho_b):
    kho.kho_xac_nhan_nhap(db, user=nhan_vien_kho, yc_id=yc_nhap_kho.id, so_luong=6, kho_id=kho_a.id)
    kho.kho_xac_nhan_nhap(db, user=nhan_vien_kho, yc_id=yc_nhap_kho.id, so_luong=4, kho_id=kho_b.id)
    lots = db.query(SanXuatKhoLot).filter_by(nhap_kho_yc_id=yc_nhap_kho.id).order_by(SanXuatKhoLot.id).all()
    assert [l.kho_id for l in lots] == [kho_a.id, kho_b.id]
    assert [float(l.so_luong) for l in lots] == [6.0, 4.0]
```

Fixture `yc_nhap_kho` / `nhan_vien_kho` tái dùng từ `tests/test_san_xuat_kho.py`; `kho_a` /
`kho_b` tạo mới bằng `models/kho_hang.py`.

- [ ] **Bước 2: Chạy để thấy đỏ.** `cd backend && python -m pytest tests/test_san_xuat_kho_dich.py -q`

- [ ] **Bước 3: Hai cột `kho_id`**

`SanXuatNhapKhoYc` (kho ĐỀ NGHỊ, KCS gợi ý — nullable) và `SanXuatKhoLot` (kho ĐÃ NHẬN —
nullable vì lot BTP `mau_luu`/`phe` không vào kho nào):

```python
    # KHO ĐÍCH (31/08/2026). Trên YÊU CẦU là kho KCS ĐỀ NGHỊ (có thể để trống); trên LOT là kho
    # ĐÃ THỰC SỰ NHẬN — nhập nhiều lần vào nhiều kho thì mỗi lot mang kho của nó. Không có cột
    # này thì tồn thành phẩm không tra được theo kho, và phiếu xuất giao không biết lấy hàng ở đâu.
    kho_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
```

- [ ] **Bước 4: `kho_xac_nhan_nhap` bắt buộc `kho_id`**

Thêm tham số **keyword bắt buộc** `kho_id: int` (đặt trước `expected_version`), kiểm tồn tại
bằng `KhoHangRepository`, gán vào lot vừa đẻ. Ném `ValueError("Không tìm thấy kho đích.")`
khi id sai.

- [ ] **Bước 5: Router + schema** — thêm `kho_id: int` vào body `KhoXacNhanNhapIn`, truyền
  xuống service.

- [ ] **Bước 6: Migration 0249** — cùng khuôn mg 0248, hai bảng `san_xuat_nhap_kho_yc` và
  `san_xuat_kho_lot`, thêm `kho_id INTEGER` + index. Không backfill (lot cũ không biết kho nào).

- [ ] **Bước 7: `docs/DB_SCHEMA.md`** — hai dòng.

- [ ] **Bước 8: Chạy test xanh**

Chạy: `cd backend && python -m pytest tests/test_san_xuat_kho_dich.py tests/test_san_xuat_kho.py tests/test_san_xuat_g5_tich_hop.py tests/test_schema_documented.py -q`
Kỳ vọng: PASS. Test cũ gọi `kho_xac_nhan_nhap` sẽ đỏ vì thiếu `kho_id` — sửa chúng để
truyền kho, **không** làm `kho_id` optional để né.

- [ ] **Bước 9: Ô chọn kho trên `ThsxG5.tsx`** — bắt buộc, không mặc định ngầm; nút Xác nhận
  khoá khi chưa chọn.

- [ ] **Bước 10: `npx tsc --noEmit`.**

- [ ] **Bước 11: NGHI THỨC SOI MÀN**, thao tác: KCS kết luận đạt → tạo yêu cầu nhập kho →
  vào vai kho, thử bấm Xác nhận khi **chưa** chọn kho (phải bị chặn) → chọn kho A xác nhận
  một phần → chọn kho B xác nhận phần còn lại → mở màn Tồn kho của A và B thấy đúng số.

- [ ] **Bước 12: Dừng — báo cáo.** KHÔNG commit.

---

# ĐỢT C — Tầng đọc + API Lệnh sản xuất

### Task 6: Nạp bối cảnh theo LÔ

**Files:**
- Create: `backend/app/services/lenh_sx/boi_canh.py`
- Test: `backend/tests/test_lenh_sx_boi_canh.py`

**Interfaces:**
- Produces: `@dataclass BoiCanh` + `nap(db, lsx_ids: list[int]) -> BoiCanh` với các map:
  `lenh: dict[int, Lsx]` · `don: dict[int, Order]` · `khach: dict[int, Customer]` ·
  `sale: dict[int, User]` · `cong_viec: dict[int, list[SanXuatCongViec]]` (khoá `lsx_id`) ·
  `phien: dict[int, list[SanXuatPhienChay]]` (khoá `cong_viec_id`) ·
  `batch: dict[int, list[SanXuatBatch]]` · `kcs: dict[int, list]` · `lot: dict[int, list]` ·
  `su_co: dict[int, list[YeuCauSuaChua]]` · `giao: dict[int, list[DeliveryRequestLine]]` ·
  `nhom: dict[int, SanXuatNhom]` · `may: dict[int, MayThietBi]`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_boi_canh.py
"""Nạp bối cảnh theo LÔ — luật sống còn là KHÔNG N+1: số câu SQL không được tăng theo số lệnh.

Đo bằng cách đếm câu lệnh qua event `before_cursor_execute`. 1 lệnh và 12 lệnh phải ra CÙNG
một số câu. Đây là thứ duy nhất giữ cho màn danh sách 200 lệnh không sập.
"""
from __future__ import annotations

from sqlalchemy import event

from app.services.lenh_sx import boi_canh

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)


def _dem_sql(db, fn):
    n = 0

    def _bat(*a, **k):
        nonlocal n
        n += 1

    event.listen(db.get_bind(), "before_cursor_execute", _bat)
    try:
        fn()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _bat)
    return n


def test_khong_n_plus_1(db, mot_lenh, muoi_hai_lenh):
    n1 = _dem_sql(db, lambda: boi_canh.nap(db, [mot_lenh]))
    n12 = _dem_sql(db, lambda: boi_canh.nap(db, muoi_hai_lenh))
    assert n12 == n1, f"N+1: 1 lệnh {n1} câu, 12 lệnh {n12} câu"


def test_map_dung_khoa(db, mot_lenh):
    bc = boi_canh.nap(db, [mot_lenh])
    assert mot_lenh in bc.lenh
    assert mot_lenh in bc.cong_viec
    for cv in bc.cong_viec[mot_lenh]:
        assert cv.id in bc.phien


def test_danh_sach_rong_khong_no(db):
    bc = boi_canh.nap(db, [])
    assert bc.lenh == {}
```

- [ ] **Bước 2: Chạy để thấy đỏ.**

- [ ] **Bước 3: Cài đặt** — một truy vấn `select(...).where(<cot>.in_(ids))` cho mỗi bảng
  nguồn, gom vào dict. Không vòng lặp gọi DB. Docstring nêu rõ danh sách bảng và lý do gom.

- [ ] **Bước 4: Chạy test xanh.** `python -m pytest tests/test_lenh_sx_boi_canh.py -q`

- [ ] **Bước 5: Dừng — báo cáo.**

---

### Task 7: Tiến độ có trọng số + dự kiến hoàn thành

**Files:**
- Create: `backend/app/services/lenh_sx/tien_do.py`
- Test: `backend/tests/test_lenh_sx_tien_do.py`

**Interfaces:**
- Consumes: `BoiCanh` (Task 6)
- Produces:
  - `phan_tram(bc, lsx_id) -> tuple[float, bool]` — (%, `uoc_tinh`)
  - `gio_may(bc, lsx_id) -> float` — giờ, loại trừ thời gian dừng
  - `du_kien_xong(bc, lsx_id, bay_gio) -> datetime | None` — `None` = chưa đủ dữ liệu
  - `tre_han(bc, lsx_id, bay_gio) -> bool`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_tien_do.py
"""Tiến độ KHÔNG đếm số công đoạn — nó là trung bình có TRỌNG SỐ theo thời lượng kế hoạch.

Vì sao: một lệnh có CTP 15 phút và In 6 tiếng; xong CTP mà báo 50% là nói dối điều độ. Bốn
luật: trọng số theo thời lượng · công đoạn đang chạy ăn phần theo sản lượng tốt · thiếu thời
lượng thì chia đều VÀ giương cờ `uoc_tinh` · routing song song đi theo ĐƯỜNG GĂNG.

Và một luật thà im còn hơn đoán: thiếu lịch/mục tiêu/thời lượng ⇒ `du_kien_xong` trả None để
UI hiện "Chưa đủ dữ liệu", KHÔNG bịa ra một mốc giờ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.lenh_sx import boi_canh, tien_do

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)

BAY_GIO = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)


def test_trong_so_theo_thoi_luong_khong_theo_so_cong_doan(db, lenh_ctp_15p_in_6h):
    """Xong CTP (15') trong tổng 6h15' ⇒ ~4%, KHÔNG phải 50%."""
    bc = boi_canh.nap(db, [lenh_ctp_15p_in_6h])
    pct, uoc = tien_do.phan_tram(bc, lenh_ctp_15p_in_6h)
    assert 3.0 <= pct <= 5.0, pct
    assert uoc is False


def test_cong_doan_dang_chay_an_phan_theo_san_luong(db, lenh_in_dang_chay_nua_muc_tieu):
    bc = boi_canh.nap(db, [lenh_in_dang_chay_nua_muc_tieu])
    pct, _ = tien_do.phan_tram(bc, lenh_in_dang_chay_nua_muc_tieu)
    assert 48.0 <= pct <= 52.0, pct


def test_vuot_muc_tieu_khong_qua_100(db, lenh_in_vuot_muc_tieu):
    bc = boi_canh.nap(db, [lenh_in_vuot_muc_tieu])
    pct, _ = tien_do.phan_tram(bc, lenh_in_vuot_muc_tieu)
    assert pct <= 100.0


def test_thieu_thoi_luong_thi_chia_deu_va_giuong_co(db, lenh_khong_thoi_luong):
    bc = boi_canh.nap(db, [lenh_khong_thoi_luong])
    pct, uoc = tien_do.phan_tram(bc, lenh_khong_thoi_luong)
    assert uoc is True


def test_gio_may_loai_tru_thoi_gian_dung(db, lenh_chay_2h_dung_1h):
    bc = boi_canh.nap(db, [lenh_chay_2h_dung_1h])
    assert 1.9 <= tien_do.gio_may(bc, lenh_chay_2h_dung_1h) <= 2.1


def test_song_song_lay_duong_gang(db, lenh_hai_nhanh_2h_va_5h):
    """Hai nhánh chạy song song 2h và 5h ⇒ dự kiến xong theo nhánh 5h."""
    bc = boi_canh.nap(db, [lenh_hai_nhanh_2h_va_5h])
    xong = tien_do.du_kien_xong(bc, lenh_hai_nhanh_2h_va_5h, BAY_GIO)
    assert xong is not None
    assert xong >= BAY_GIO + timedelta(hours=4.5)


def test_thieu_du_lieu_tra_none(db, lenh_khong_lich):
    bc = boi_canh.nap(db, [lenh_khong_lich])
    assert tien_do.du_kien_xong(bc, lenh_khong_lich, BAY_GIO) is None


def test_tre_han_khi_du_kien_vuot_han_sx(db, lenh_du_kien_vuot_han):
    bc = boi_canh.nap(db, [lenh_du_kien_vuot_han])
    assert tien_do.tre_han(bc, lenh_du_kien_vuot_han, BAY_GIO) is True
```

- [ ] **Bước 2: Chạy để thấy đỏ.**

- [ ] **Bước 3: Cài đặt.** Trọng số = `(du_kien_ket_thuc - du_kien_bat_dau)` phút của
  `san_xuat_cong_viec`; thiếu ⇒ chia đều + `uoc_tinh=True`. Phần công đoạn đang chạy =
  `sum(batch.tot) / so_luong_ra`, kẹp `[0, 1]`. Giờ máy = tổng `(ket_thuc - bat_dau)` của
  phiên đã đóng + `(bay_gio - bat_dau)` của phiên đang mở. Đường găng: duyệt
  `san_xuat_phu_thuoc` bằng topo sort; không có cạnh ⇒ chuỗi tuần tự theo `du_kien_bat_dau`.

- [ ] **Bước 4: Chạy test xanh.**

- [ ] **Bước 5: Dừng — báo cáo.**

---

### Task 8: Trạng thái tổng hợp + cờ cảnh báo

**Files:**
- Create: `backend/app/services/lenh_sx/trang_thai.py`
- Test: `backend/tests/test_lenh_sx_trang_thai.py`

**Interfaces:**
- Consumes: `BoiCanh`, `tien_do`, `services/lsx_tong_quan.py`
- Produces: hằng `TAB_DANG_SX`, `TAB_CANH_BAO`, `TAB_KCS`, `TAB_CHO_NHAP_KHO`,
  `TAB_SAN_SANG_GIAO`, `TAB_HOAN_THANH`; `trang_thai_chinh(bc, lsx_id, bay_gio) -> str`;
  `co_canh_bao(bc, lsx_id, bay_gio) -> list[str]`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_trang_thai.py
"""Trạng thái tổng hợp — MỘT trạng thái chính cho bảng, nhiều cờ phụ cho badge.

Thứ tự ưu tiên khi một lệnh dính nhiều thứ cùng lúc (chốt 31/08/2026): Cảnh báo ăn trước Đang
SX. Điều độ quét bảng để TÌM chỗ tắc — lệnh vừa chạy vừa có sự cố mà xếp vào "Đang SX" thì nó
biến mất khỏi tầm mắt đúng lúc cần nhìn nhất.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.lenh_sx import boi_canh, trang_thai

from tests.test_san_xuat_board import (  # noqa: F401
    _authz, _phat_hanh_vao_to, admin, customer, db, lsx_svc, orders,
)

BAY_GIO = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)


def _tt(db, lsx_id):
    return trang_thai.trang_thai_chinh(boi_canh.nap(db, [lsx_id]), lsx_id, BAY_GIO)


def test_dang_chay_ra_dang_sx(db, lenh_dang_chay):
    assert _tt(db, lenh_dang_chay) == trang_thai.TAB_DANG_SX


def test_su_co_chua_dong_an_truoc_dang_sx(db, lenh_dang_chay_co_su_co):
    assert _tt(db, lenh_dang_chay_co_su_co) == trang_thai.TAB_CANH_BAO


def test_tam_dung_ra_canh_bao(db, lenh_tam_dung):
    assert _tt(db, lenh_tam_dung) == trang_thai.TAB_CANH_BAO


def test_toi_kcs_ra_kcs(db, lenh_dang_kcs):
    assert _tt(db, lenh_dang_kcs) == trang_thai.TAB_KCS


def test_kcs_dat_chua_nhap_kho_ra_cho_nhap_kho(db, lenh_kcs_dat_chua_nhap):
    assert _tt(db, lenh_kcs_dat_chua_nhap) == trang_thai.TAB_CHO_NHAP_KHO


def test_co_ton_chua_giao_ra_san_sang_giao(db, lenh_da_nhap_kho):
    assert _tt(db, lenh_da_nhap_kho) == trang_thai.TAB_SAN_SANG_GIAO


def test_giao_het_ra_hoan_thanh(db, lenh_giao_het):
    assert _tt(db, lenh_giao_het) == trang_thai.TAB_HOAN_THANH


def test_kcs_khong_dat_khong_tao_ton_giao_duoc(db, lenh_kcs_khong_dat):
    assert _tt(db, lenh_kcs_khong_dat) != trang_thai.TAB_SAN_SANG_GIAO


def test_co_phu_van_hien_du(db, lenh_dang_chay_co_su_co):
    co = trang_thai.co_canh_bao(boi_canh.nap(db, [lenh_dang_chay_co_su_co]),
                                lenh_dang_chay_co_su_co, BAY_GIO)
    assert "su_co" in co
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo.

Cờ vật tư lấy lại từ `services/lsx_tong_quan.py` (đèn `vat_tu`) chứ không tính lại — nó đã
soi đúng cửa `XepLichService._chan_chua_giu_du`.

---

### Task 9: API danh sách + KPI

**Files:**
- Create: `backend/app/services/lenh_sx/danh_sach.py`
- Create: `backend/app/schemas/lenh_san_xuat.py`
- Create: `backend/app/routers/lenh_san_xuat.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_lenh_sx_api.py`

**Interfaces:**
- Produces:
  - `GET /api/lenh-san-xuat/summary` → `{dang_sx, cong_doan_xong_hom_nay, du_kien_tre, ty_le_kcs_dat_hom_nay}`
  - `GET /api/lenh-san-xuat?tab&q&page&page_size&nhom_cong_doan&may_id&uu_tien&tre&tu_ngay&den_ngay`
    → `{items, total, page, page_size, dem_theo_tab}`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_api.py
"""API danh sách Lệnh sản xuất — phân trang + lọc Ở MÁY CHỦ, phạm vi gắn từ QUYỀN.

Ba thứ phải đúng ngay từ đầu, sửa sau rất đắt:
  · `page_size` cắt ở SQL, không kéo cả bảng về rồi slice trong Python.
  · Client KHÔNG được tự truyền `sale_user_id` để nới phạm vi — backend tự gắn từ token.
  · Response không mang một con số tiền nào.
"""
from __future__ import annotations


def _tok(client, seed_credentials):
    return client.post("/api/auth/login", json=seed_credentials).json()["access_token"]


def test_khong_dang_nhap_401(client):
    assert client.get("/api/lenh-san-xuat").status_code == 401


def test_summary_du_4_kpi(client, seed_credentials):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get("/api/lenh-san-xuat/summary", headers=h)
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"dang_sx", "cong_doan_xong_hom_nay", "du_kien_tre", "ty_le_kcs_dat_hom_nay"}


def test_phan_trang_o_may_chu(client, seed_credentials, hai_muoi_lenh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get("/api/lenh-san-xuat?page=1&page_size=5", headers=h)
    d = r.json()
    assert len(d["items"]) == 5
    assert d["total"] >= 20


def test_client_khong_tu_noi_pham_vi(client, seed_credentials, sale_khac):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    a = client.get("/api/lenh-san-xuat", headers=h).json()["total"]
    b = client.get(f"/api/lenh-san-xuat?sale_user_id={sale_khac.id}", headers=h).json()["total"]
    assert a == b, "tham số lạ trên URL không được đổi phạm vi"


def test_khong_lo_tien(client, seed_credentials):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    body = client.get("/api/lenh-san-xuat", headers=h).text.lower()
    for cam in ("don_gia", "gia_von", "thanh_tien", "luong_khoan", "chi_phi"):
        assert cam not in body, f"lộ {cam}"


def test_lenh_nhap_khong_hien(client, seed_credentials, lenh_nhap):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    ids = {i["id"] for i in client.get("/api/lenh-san-xuat?page_size=200", headers=h).json()["items"]}
    assert lenh_nhap not in ids
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo.

Lưu ý Pydantic: service trả `dict` + `response_model` ⇒ field không khai trong schema Out bị
**nuốt im lặng**, FE nhận `undefined`. Thêm field phải đi hết chuỗi
dict → hàm trung gian → schema → type TS.

---

### Task 10: API hồ sơ chi tiết + timeline

**Files:**
- Create: `backend/app/services/lenh_sx/ho_so.py`
- Modify: `backend/app/schemas/lenh_san_xuat.py`, `backend/app/routers/lenh_san_xuat.py`
- Test: `backend/tests/test_lenh_sx_ho_so.py`

**Interfaces:**
- Produces: `GET /api/lenh-san-xuat/{lsx_id}` → DTO gồm `thong_tin` · `tien_do` ·
  `routing` (node + cạnh) · `vat_tu` (`hien_tai`, `canh_bao_sau`) · `nhan_luc` ·
  `san_luong` · `su_co` · `kcs` · `kho` · `giao_hang` · `timeline` · `phien_ban`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_ho_so.py
"""Hồ sơ LSX chỉ đọc. Bốn thứ dễ làm sai:
  · 403 khi gõ id ngoài phạm vi (không phải 404 mập mờ, không phải trả nội dung).
  · Vật tư có HAI mức: đủ cho bước HIỆN TẠI vs cảnh báo bước SAU — gộp một là mất nghĩa.
  · Timeline gộp đủ nguồn và sắp theo thời gian server.
  · `phien_ban` đọc từ `san_xuat_goi_phat_hanh.version_hien_tai`, KHÔNG cột mới trên `lsx`.
"""
from __future__ import annotations


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def test_ngoai_pham_vi_403(client, sale_a_credentials, lenh_cua_sale_b):
    h = {"Authorization": f"Bearer {_tok(client, sale_a_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_cua_sale_b}", headers=h)
    assert r.status_code == 403
    assert "LSX" not in r.text.upper().replace("LỆNH SẢN XUẤT", "")


def test_vat_tu_hai_muc(client, seed_credentials, lenh_du_buoc_nay_thieu_buoc_sau):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    d = client.get(f"/api/lenh-san-xuat/{lenh_du_buoc_nay_thieu_buoc_sau}", headers=h).json()
    assert d["vat_tu"]["hien_tai"]["du"] is True
    assert len(d["vat_tu"]["canh_bao_sau"]) >= 1


def test_timeline_sap_theo_thoi_gian(client, seed_credentials, lenh_nhieu_su_kien):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    tl = client.get(f"/api/lenh-san-xuat/{lenh_nhieu_su_kien}", headers=h).json()["timeline"]
    assert len(tl) >= 3
    assert [e["luc"] for e in tl] == sorted(e["luc"] for e in tl)
    assert {"loai", "luc", "nguoi", "noi_dung"} <= set(tl[0])


def test_phien_ban_doc_tu_goi_phat_hanh(client, seed_credentials, lenh_da_cap_nhat_phat_hanh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    d = client.get(f"/api/lenh-san-xuat/{lenh_da_cap_nhat_phat_hanh}", headers=h).json()
    assert d["phien_ban"] >= 2
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo.

---

# ĐỢT D — Màn Lệnh sản xuất (frontend)

### Task 11: Danh sách + KPI + tab

**Files:**
- Create: `frontend/src/pages/LenhSanXuatPage.tsx`, `frontend/src/pages/lenh-san-xuat.css`
- Modify: `frontend/src/api/client.ts`, `frontend/src/components/AppShell.tsx`,
  `frontend/src/components/appShellRealtime.ts`

- [ ] **Bước 1: Chốt thiết kế bằng skill `ui-ux-pro-max`**

Gọi skill với bối cảnh: bám pattern list/badge/pill/drawer của `RebuildCatalogPage.tsx`; hệ
màu và spacing lấy từ `frontend/src/pages/ke-hoach-sx.css` để hai màn Sản xuất đứng cạnh
nhau không lệch. Chốt trước khi gõ dòng JSX nào: hierarchy (KPI → lọc → tab → bảng), trạng
thái loading/empty/error, focus ring + `aria-*` cho tab, breakpoint hẹp.

- [ ] **Bước 2: Trình bản thiết kế + diff dự kiến trong chat, chờ chốt.** Không sửa
  `AppShell.tsx` / `Sidebar.tsx` trước khi được đồng ý.

- [ ] **Bước 3: Dựng `LenhSanXuatPage.tsx`** — 4 KPI, ô tìm kiếm, bộ lọc, 7 tab, bảng có cột
  Mã · Sản phẩm/SL · Khách · Máy/người · Công đoạn + tiến độ · Hạn/Dự kiến · Trạng thái ·
  mũi tên mở hồ sơ. Phân trang gọi server. **Không** nút Tạo LSX, **không** Xuất Excel,
  **không** nút điều hành.

- [ ] **Bước 4: Mount vào `AppShell.tsx`** trong `switch (baseId)`, nhánh `"lenh-san-xuat"`.
  Thêm `"lenh_san_xuat"` và `"theo_doi_san_xuat"` vào `REALTIME_MODULES`.

- [ ] **Bước 5: `npx tsc --noEmit`.** Kỳ vọng 0 lỗi.

- [ ] **Bước 6: NGHI THỨC SOI MÀN trên "Lệnh sản xuất"** — trọn §Nghi thức bước 0→7. Bắt
  buộc thao tác thêm: bấm **từng** tab trong 7 tab và đọc số đếm; gõ vào ô tìm kiếm mã LSX
  có thật rồi mã không có thật; đổi từng bộ lọc; sang trang 2 rồi quay lại trang 1; cuộn bảng
  hết sang phải để thấy cột cuối; thu cửa sổ còn 390px xem bảng có tràn không.

- [ ] **Bước 7: `styleseed-design-review`** trên hai file mới, xử lý phát hiện có nghĩa.

- [ ] **Bước 8: Dừng — báo cáo** theo §Nghi thức bước 7. KHÔNG commit.

---

### Task 12: Hồ sơ LSX chỉ đọc

**Files:**
- Create: `frontend/src/pages/LenhSxHoSoView.tsx`
- Modify: `frontend/src/pages/LenhSanXuatPage.tsx`, `frontend/src/api/client.ts`

- [ ] **Bước 1: Dựng hồ sơ** — header tổng quan (tiến độ · sản lượng · giờ máy) · sản phẩm ·
  routing + trạng thái từng công đoạn (hiện nhánh song song) · timeline · thông số kỹ thuật ·
  BOM/vật tư đã cấp/thiếu hụt · tổ-máy-người + lịch sử đổi · sự cố & phiếu sửa · KCS · nhập
  kho · giao hàng · nút In phiếu công nghệ (Task 13 nối) · liên kết sang form giao hàng.

  **Không** tái dùng chế độ sửa của `LsxDetailView.tsx` — dựng từ DTO chỉ đọc, để không vô
  tình lộ CTA hay đụng logic lập kế hoạch.

- [ ] **Bước 2: Liên kết "Tạo yêu cầu giao hàng"** — chỉ hiện khi có tồn khả dụng **và**
  người dùng có `giao_hang:create`. Điều hướng sang form giao hàng hiện có, điền sẵn nhóm
  sản xuất · đơn · thành phẩm · kho · số tối đa. **Không** nhúng form ghi vào màn này.

- [ ] **Bước 3: `npx tsc --noEmit`.**

- [ ] **Bước 4: NGHI THỨC SOI MÀN trên hồ sơ LSX** — mở hồ sơ từ bảng; bấm mở/đóng **mọi**
  khối gập; cuộn timeline tới sự kiện cũ nhất; cuộn bảng routing sang phải hết; bấm nút In;
  bấm liên kết giao hàng và xác nhận form được điền sẵn đúng; bấm nút Quay lại và xác nhận
  bảng giữ nguyên tab + bộ lọc + vị trí cuộn.

- [ ] **Bước 5: `styleseed-design-review`.**

- [ ] **Bước 6: Dừng — báo cáo.** KHÔNG commit.

---

# ĐỢT E — Phiếu công nghệ A4 + QR

### Task 13: PDF phiếu công nghệ

**Files:**
- Create: `backend/app/services/lenh_sx/phieu_cong_nghe.py`
- Modify: `backend/app/routers/lenh_san_xuat.py`
- Test: `backend/tests/test_lenh_sx_pdf.py`

**Interfaces:**
- Produces: `GET /api/lenh-san-xuat/{lsx_id}/phieu-cong-nghe.pdf` → `application/pdf`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_lenh_sx_pdf.py
"""Phiếu công nghệ A4. Dùng ReportLab đang có ở `routers/quotations.py` — KHÔNG thêm thư viện
QR mới nếu widget QR của ReportLab đủ dùng.

Bốn luật: đúng PDF · nội dung dài thì TỰ chia trang (không cắt bảng giữa dòng) · mọi trang
lặp mã LSX + phiên bản + QR · tải PDF KHÔNG làm tăng phiên bản phát hành.
"""
from __future__ import annotations


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def test_tra_ve_pdf(client, seed_credentials, mot_lenh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{mot_lenh}/phieu-cong-nghe.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"


def test_lenh_dai_tu_chia_trang(client, seed_credentials, lenh_40_cong_doan):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    r = client.get(f"/api/lenh-san-xuat/{lenh_40_cong_doan}/phieu-cong-nghe.pdf", headers=h)
    assert r.content.count(b"/Type /Page") >= 2


def test_ngoai_pham_vi_403(client, sale_a_credentials, lenh_cua_sale_b):
    h = {"Authorization": f"Bearer {_tok(client, sale_a_credentials)}"}
    assert client.get(f"/api/lenh-san-xuat/{lenh_cua_sale_b}/phieu-cong-nghe.pdf",
                      headers=h).status_code == 403


def test_tai_pdf_khong_tang_phien_ban(client, seed_credentials, mot_lenh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    truoc = client.get(f"/api/lenh-san-xuat/{mot_lenh}", headers=h).json()["phien_ban"]
    client.get(f"/api/lenh-san-xuat/{mot_lenh}/phieu-cong-nghe.pdf", headers=h)
    client.get(f"/api/lenh-san-xuat/{mot_lenh}/phieu-cong-nghe.pdf", headers=h)
    sau = client.get(f"/api/lenh-san-xuat/{mot_lenh}", headers=h).json()["phien_ban"]
    assert sau == truoc
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo. Không có xuất Excel ở v1.

---

### Task 14: QR deep link qua đăng nhập

**Files:**
- Modify: `backend/app/services/lenh_sx/phieu_cong_nghe.py`
- Modify: `frontend/src/components/AppShell.tsx`, `frontend/src/pages/LoginPage.tsx`
- Test: `backend/tests/test_lenh_sx_qr.py` + kiểm UI

- [ ] **Bước 1: Nội dung QR** — `#lsx=<id>&pv=<phien_ban_in>`. MỘT QR cho mỗi LSX, không QR
  riêng từng công đoạn. Không nhúng token vào QR: đây là trang **cần đăng nhập**, khác
  `routers/public_scan.py` (kho, HMAC, công khai) — đừng nhầm hai đường.

- [ ] **Bước 2: FE** — chưa đăng nhập thì giữ deep link, đăng nhập xong quay lại đúng LSX;
  `pv < phien_ban_hien_tai` ⇒ băng cảnh báo "Phiếu giấy v{pv}, lệnh hiện tại đã là v{n}".
  Nội dung trên màn luôn là dữ liệu HIỆN TẠI, không dựng lại snapshot cũ.

- [ ] **Bước 3: `npx tsc --noEmit`.**

- [ ] **Bước 4: Kiểm UI thật** — trong CÙNG một trang dev-browser: đăng xuất → `goto`
  `http://localhost:5173/#lsx=<id>&pv=1` → thấy màn đăng nhập → đăng nhập → xác nhận nhảy
  đúng hồ sơ LSX đó. Rồi thử `#lsx=<id ngoài phạm vi>` với tài khoản hẹp → thấy chặn.
  Rồi `pv=1` khi lệnh đã v2 → thấy băng cảnh báo. Chụp ảnh cả ba.

- [ ] **Bước 5: Dừng — báo cáo.** KHÔNG commit.

---

# ĐỢT F — Màn Theo dõi sản xuất

### Task 15: API meta + Kanban

**Files:**
- Create: `backend/app/services/lenh_sx/bang_theo_doi.py`,
  `backend/app/schemas/theo_doi_san_xuat.py`, `backend/app/routers/theo_doi_san_xuat.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_theo_doi_kanban.py`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_theo_doi_kanban.py
"""Kanban — cột lấy ĐỘNG từ danh mục nhóm công đoạn, một LSX đúng MỘT card.

Hai luật hay bị vi phạm nhất:
  · Hard-code CTP/In/Cán/Bế/Dán/KCS. Xưởng thêm một nhóm công đoạn là bảng sai ngay, im lặng.
  · Routing song song đẻ nhiều card. Một lệnh nhiều card thì đếm "đang chạy" sai gấp đôi.

Và một luật nghiệp vụ: card tự đổi cột là do dữ liệu đổi, hệ thống KHÔNG tự bắt đầu bước sau.
"""
from __future__ import annotations


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def test_cot_lay_tu_danh_muc(client, seed_credentials, nhom_cong_doan_moi):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cot = [c["key"] for c in client.get("/api/theo-doi-san-xuat/meta", headers=h).json()["cot"]]
    assert nhom_cong_doan_moi in cot


def test_song_song_chi_mot_card(client, seed_credentials, lenh_hai_nhanh_cung_chay):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    cua_lenh = [c for c in cards if c["lsx_id"] == lenh_hai_nhanh_cung_chay]
    assert len(cua_lenh) == 1
    assert len(cua_lenh[0]["chip_dang_chay"]) == 2


def test_card_nam_o_buoc_chan_som_nhat(client, seed_credentials, lenh_in_xong_can_dang_cho):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    c = next(x for x in cards if x["lsx_id"] == lenh_in_xong_can_dang_cho)
    assert c["cot"] == "can"


def test_hoan_thanh_node_khong_tu_bat_dau_node_sau(db, lenh_in_vua_ket_thuc):
    from app.models.san_xuat import CV_DANG_CHAY, SanXuatCongViec
    sau = db.query(SanXuatCongViec).filter_by(lsx_id=lenh_in_vua_ket_thuc, nhom_cong_doan="can").one()
    assert sau.trang_thai != CV_DANG_CHAY


def test_lenh_nhap_khong_len_kanban(client, seed_credentials, lenh_nhap):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cards = client.get("/api/theo-doi-san-xuat/kanban", headers=h).json()["cards"]
    assert lenh_nhap not in {c["lsx_id"] for c in cards}
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo.

---

### Task 16: API theo máy · theo ca · gantt

**Files:**
- Modify: `backend/app/services/lenh_sx/bang_theo_doi.py`, schemas, router
- Test: `backend/tests/test_theo_doi_may_ca_gantt.py`

- [ ] **Bước 1: Viết test thất bại**

```python
# backend/tests/test_theo_doi_may_ca_gantt.py
"""Ba tab còn lại.

  · Theo máy: mỗi máy một lane, việc CHƯA gán máy vào nhóm riêng "Chưa xếp máy" — bỏ chúng đi
    là giấu mất đúng thứ điều độ phải xử lý.
  · Theo ca: ca lấy từ DANH MỤC ca đang hiệu lực, không hard-code ba ca. Ca qua nửa đêm tính
    theo mốc BẮT ĐẦU ca.
  · Gantt: có phân trang/windowing, không trả toàn bộ lịch sử một lần.
"""
from __future__ import annotations


def _tok(client, cred):
    return client.post("/api/auth/login", json=cred).json()["access_token"]


def test_viec_chua_gan_may_co_lane_rieng(client, seed_credentials, viec_chua_xep_may):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    lanes = client.get("/api/theo-doi-san-xuat/machines", headers=h).json()["lanes"]
    chua = next(l for l in lanes if l["may_id"] is None)
    assert viec_chua_xep_may in {b["cong_viec_id"] for b in chua["blocks"]}


def test_ca_lay_tu_danh_muc(client, seed_credentials, ca_thu_tu):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cas = client.get("/api/theo-doi-san-xuat/shifts", headers=h).json()["ca"]
    assert ca_thu_tu in {c["id"] for c in cas}


def test_ca_qua_nua_dem_tinh_theo_moc_bat_dau(client, seed_credentials, viec_ca_dem_qua_ngay):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    cas = client.get("/api/theo-doi-san-xuat/shifts?ngay=2026-08-31", headers=h).json()["ca"]
    dem = next(c for c in cas if c["ten"].lower().startswith("ca 3") or c["qua_nua_dem"])
    assert viec_ca_dem_qua_ngay in {v["cong_viec_id"] for v in dem["viec"]}


def test_gantt_co_phan_trang(client, seed_credentials, hai_muoi_lenh):
    h = {"Authorization": f"Bearer {_tok(client, seed_credentials)}"}
    d = client.get("/api/theo-doi-san-xuat/gantt?page=1&page_size=5", headers=h).json()
    assert len(d["rows"]) == 5
    assert d["total"] >= 20
```

- [ ] **Bước 2→5:** đỏ → cài đặt → xanh → dừng, báo cáo.

---

### Task 17: FE Theo dõi sản xuất — khung + Kanban + Theo máy

**Files:**
- Create: `frontend/src/pages/TheoDoiSanXuatPage.tsx`, `TdsxKanban.tsx`, `TdsxTheoMay.tsx`,
  `theo-doi-san-xuat.css`
- Modify: `frontend/src/components/AppShell.tsx`, `frontend/src/api/client.ts`

- [ ] **Bước 1: Chốt thiết kế bằng `ui-ux-pro-max`**, trình bản thiết kế trong chat, chờ chốt.

- [ ] **Bước 2: Khung 4 tab + bộ lọc chung** (công nhân · máy · nhóm công đoạn · ca · ưu tiên ·
  trạng thái · cảnh báo trễ · khách/sản phẩm/mã LSX). Bộ lọc và tab giữ trong URL hash để
  quay lại khôi phục đúng.

- [ ] **Bước 3: Tab Kanban** — cột động, card một-lệnh-một-card, chip nhánh song song.

- [ ] **Bước 4: Tab Theo máy** — mini-Gantt kế hoạch vs thực tế, lane "Chưa xếp máy", click
  block mở hồ sơ LSX.

- [ ] **Bước 5: `npx tsc --noEmit`.**

- [ ] **Bước 6: NGHI THỨC SOI MÀN**, thao tác thêm: cuộn Kanban **ngang** hết các cột và
  **dọc** hết trong một cột; kéo/cuộn mini-Gantt sang trái và phải hết dải thời gian; bấm
  một block mở hồ sơ rồi Quay lại, xác nhận về đúng tab + bộ lọc + vị trí cuộn; bật/tắt
  **từng** bộ lọc và đọc số card đổi theo.

- [ ] **Bước 7: `styleseed-design-review`.** — [ ] **Bước 8: Dừng — báo cáo.**

---

### Task 18: FE — Theo ca + Gantt tổng thể + realtime

**Files:**
- Create: `frontend/src/pages/TdsxTheoCa.tsx`
- Modify: `frontend/src/pages/TheoDoiSanXuatPage.tsx`

- [ ] **Bước 1: Tab Theo ca** — mỗi ca: việc dự kiến · đã thực hiện · chuyển tiếp từ ca trước ·
  vượt ca; hiện tổ, máy, công nhân, sản lượng tốt.

- [ ] **Bước 2: Tab Gantt tổng thể** — **tái dùng `frontend/src/pages/Xl2Gantt.tsx`** (đã có,
  `export function Xl2Gantt`, `Xl2ClusterKey = "may" | "to" | "ncc" | "cho" | "lenh"`). Dựng
  Gantt thứ hai từ đầu là hai bộ code vẽ trục thời gian lệch nhau. Nếu props không đủ, mở
  rộng props của `Xl2Gantt` chứ không fork file.

- [ ] **Bước 3: Realtime** — nghe SSE có sẵn ở AppShell. Backend `broadcast` sự kiện gọn
  (`{"type": "san_xuat_changed", "lsx_id": ...}`) **sau** khi commit; **không** đẩy nội dung
  card qua SSE (event đi tới mọi kết nối, đẩy tên khách là rò phạm vi). Client nhận rồi gọi
  lại API đã áp phạm vi. Gộp các event sát nhau (debounce ~400ms).

- [ ] **Bước 4: `npx tsc --noEmit`.**

- [ ] **Bước 5: NGHI THỨC SOI MÀN + kiểm realtime hai màn**

Vẫn **một** trình duyệt. Mở màn Theo dõi sản xuất, cuộn xuống giữa danh sách, đặt một bộ lọc.
Ở tab khác của **chính trình duyệt đó** (dùng `browser.getPage("svn")` rồi
`page.goto` qua lại — không mở page thứ hai) vào màn Thực hiện SX, bấm Bắt đầu một công việc.
Quay lại màn Theo dõi: card phải tự đổi cột **mà không refresh**, và tab + bộ lọc + vị trí
cuộn phải giữ nguyên. Chụp ảnh trước/sau.

- [ ] **Bước 6: `styleseed-design-review`.** — [ ] **Bước 7: Dừng — báo cáo.**

---

## Kịch bản nghiệm thu (chạy sau Task 18, trước khi xin commit)

Mỗi dòng phải có bằng chứng: output test **hoặc** mô tả cụ thể thao tác + ảnh chụp.

**Phạm vi & quyền**
- [ ] Sale chỉ thấy LSX thuộc đơn mình phụ trách.
- [ ] Trưởng phòng thấy đúng cây phòng ban con, không thấy phòng khác.
- [ ] Admin và Kế hoạch SX thấy toàn bộ LSX đã phát hành.
- [ ] LSX nháp không xuất hiện ở bất kỳ view hay KPI nào.
- [ ] Gõ URL/ID ngoài phạm vi nhận 403, không lộ nội dung.
- [ ] Response không chứa giá thành, đơn giá máy, lương khoán.

**Chỉ đọc**
- [ ] Hai màn mới không có nút bắt đầu/dừng/huỷ/sửa nào (kiểm bằng kiểm kê §Nghi thức bước 2).
- [ ] Tổ trưởng bắt đầu công đoạn ở màn Thực hiện SX → Kanban tự cập nhật, không refresh.
- [ ] Hoàn thành một node không tự bắt đầu node kế tiếp.

**Tổng hợp**
- [ ] Routing song song chỉ sinh một card, hiện chip các nhánh đang chạy.
- [ ] Cột Kanban đổi đúng khi danh mục nhóm công đoạn đổi.
- [ ] Ca lấy từ danh mục; ca qua nửa đêm tính theo mốc bắt đầu.
- [ ] LSX thiếu dữ liệu ETA hiện "Chưa đủ dữ liệu", không bịa mốc giờ.
- [ ] Vật tư đủ bước hiện tại nhưng thiếu bước sau hiện đúng hai mức.

**Vận hành**
- [ ] Giờ máy loại trừ thời gian tạm dừng và giữ đúng lịch sử sau đổi máy.
- [ ] Sự cố "Dừng sản xuất" đồng thời tạm dừng công đoạn và tạo yêu cầu sửa chữa.
- [ ] Sự cố "Vẫn chạy" không làm dừng đồng hồ máy.
- [ ] Nhập kho bắt buộc chọn kho; KCS không đạt không tạo tồn giao được.
- [ ] Nhóm Ruột/Bìa chỉ tạo tồn cho một thành phẩm cuối.

**QR / PDF**
- [ ] Quét QR khi chưa đăng nhập quay lại đúng LSX sau đăng nhập.
- [ ] QR ngoài phạm vi bị chặn.
- [ ] Phiếu giấy phiên bản cũ mở dữ liệu hiện tại + hiện băng cảnh báo version.
- [ ] PDF dài tự chia trang, lặp header/version/QR mỗi trang.

**Không hỏng cái cũ**
- [ ] Màn Kế hoạch SX, Xếp lịch 2, Thực hiện SX, Giao hàng cũ (`order_line_id`) chạy như trước.
- [ ] `python -m pytest tests/ -q` xanh — chạy MỘT lần ở cuối, sau khi mọi task xong.
- [ ] `npx tsc --noEmit` 0 lỗi.
- [ ] `docs/DB_SCHEMA.md` khớp model (`tests/test_schema_documented.py` xanh).
- [ ] Migration 0246→0249 chạy được **hai lần liên tiếp** không lỗi, trên cả SQLite và Postgres.

---

## Tự rà (đã chạy khi viết plan)

**Phủ spec.** Mọi mục trong bản chốt 31/08/2026 đều có task: quyền+phạm vi (T1,T2) · phiên
máy+đổi máy (T3) · sự cố+sửa chữa (T4) · kho thành phẩm+kho đích (T5) · read model (T6-T8) ·
API danh sách/chi tiết (T9,T10) · FE Lệnh SX (T11,T12) · PDF+QR (T13,T14) · Theo dõi SX
(T15-T18) · audit timeline (T10) · realtime (T18).

**Ba mục trong plan cũ CỐ Ý bỏ**, vì code đã có và làm lại là hỏng cái đang chạy:
- Bảng sự cố riêng → dùng `ky_thuat_yeu_cau_sua` (§Chốt 4).
- `production_group` mới → dùng `san_xuat_nhom` (§Chốt 5).
- Cột `release_version` trên `lsx` → dùng `san_xuat_goi_phat_hanh.version_hien_tai` (§Chốt 6).

**Một mục HOÃN có chủ ý:** chuyển `DeliveryRequestLine` sang giao theo nhóm sản xuất. Cột
`order_line_id` đang `NOT NULL` và nằm trong unique `(request_id, order_line_id)`
(`models/delivery.py:172,195`) — nới nó là ALTER + đổi constraint trên bảng có dữ liệu thật,
đủ rủi ro để đứng thành plan riêng. Trong plan này, Task 12 chỉ **liên kết** sang form giao
hàng hiện có với dữ liệu điền sẵn; luồng giao vẫn chạy đường `order_line_id` cũ. Nếu chủ dự
án muốn làm luôn, đó là đợt G và cần bản plan riêng.

**Nhất quán tên.** `sale_ids_theo_pham_vi` / `loc_lsx_da_phat_hanh` / `chan_ngoai_pham_vi`
(T2) dùng nguyên tên đó ở T9, T10, T13. `BoiCanh` + `nap()` (T6) dùng nguyên ở T7, T8, T15,
T16. `phan_tram` trả `tuple[float, bool]` ở T7 và được đọc đúng dạng tuple ở T8, T9.
`doi_may` (T3) và `bao_su_co` (T4) đều trả `dict` để router bọc `response_model`.
