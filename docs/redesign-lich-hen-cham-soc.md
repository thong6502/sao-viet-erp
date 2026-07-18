# Redesign: Lịch hẹn chăm sóc khách kiểu calendar

> Nâng `CustomerCareTask` từ "1 việc + due_date" → lịch hẹn calendar: **lặp lại được**,
> **xem trên lịch tháng/tuần trong hồ sơ từng khách**, **SSE tự báo khi tới giờ**.
> Giữ triết lý sẵn có: mức nhắc suy live (không lưu, không cron ngoài), báo nội bộ real-time.
> **Gộp vào tab Chăm sóc** của `KhachHangPage` — không dựng màn riêng.

## 1. Model (migration `0077`, cập nhật `docs/DB_SCHEMA.md`)

`customer_care_tasks` thêm 5 cột:

| Cột | Kiểu | Nghĩa |
|---|---|---|
| `repeat_freq` | `String(8)` server_default `'none'` | none/day/week/month — `none` = hẹn đơn lẻ (tương thích ngược) |
| `repeat_interval` | `Integer` default 1 | mỗi N đơn vị |
| `repeat_until` | `DateTime` null | lặp đến hết ngày này |
| `series_id` | `Integer` null, index | nối dòng-ngoại-lệ về hẹn-đầu-chuỗi (head) |
| `occurrence_date` | `DateTime` null | (dòng ngoại lệ) thay cho lần nào của chuỗi |

- Hẹn-đầu-chuỗi (`repeat_freq≠none`) mang **luật**; `due_date` = mốc lần đầu.
- Lần tương lai **không lưu** — bung ảo khi đọc lịch.

## 2. Logic bung occurrence (service)

`expand_occurrences(customer, from, to)`:
1. Lấy hẹn-đầu-chuỗi active của khách.
2. Sinh due-dates theo `(interval, freq)` trong `[from,to] ∩ [.., repeat_until]`, **cap chân trời** (≤1 năm / ≤200 lần).
3. Lấy dòng ngoại-lệ (`series_id`) → map theo `occurrence_date`.
4. Mỗi ngày: có ngoại-lệ → dùng nó (đã xong/dời/hủy); không → occurrence **ảo** (open).

Hành động lên 1 lần = **materialize** 1 dòng ngoại-lệ:
- `complete` (done + tùy chọn ghi `CareEvent`) · `reschedule` (đổi due) · `cancel` (hủy lần này).
- Sửa/hủy **cả chuỗi** = thao tác trên hẹn-đầu-chuỗi.

`remind_level(due_date)` giữ nguyên (chưa tới=0 · đến hạn=1 · quá ≥2 ngày=2 · quá ≥5 ngày=3), áp mỗi occurrence.
`list_due_followups` (panel "Cần chăm sóc") nâng nhẹ để hiểu chuỗi → occurrence open gần nhất đã tới hạn, theo scope RBAC.
`care_stats` chỉ tính dòng đã materialize.

## 3. Endpoint (`routers/customers.py`)

- `GET /api/customers/{id}/care-calendar?from&to` → occurrences trong khoảng (cho lịch).
- `POST /api/customers/{id}/care-tasks` — mở rộng nhận `repeat_freq/interval/until`.
- `POST /api/customers/{id}/care-tasks/{head}/occurrences/{date}` action = `complete|reschedule|cancel`.
- Giữ `PUT …/care-tasks/{id}/status` cho hẹn đơn lẻ.

## 4. SSE real-time

- Tái dùng hạ tầng SSE hiện có (Báo giá dùng `/api/quotations/events`).
- Publish khi: tạo / giao / hoàn thành / dời / **tới hạn**. Kênh theo `assignee_user_id`.
- **Nhịp nền in-process** (asyncio ~60s ở lifespan): quét occurrence vừa tới hạn / nâng mức nhắc → đẩy `care_due`. Không lưu trạng thái nhắc (suy từ `due_date`); nhịp chỉ để **kích đẩy đúng lúc**.
- Scale >1 worker → Postgres LISTEN/NOTIFY (để mở, chưa làm).
- FE: hook nghe stream → badge "Cần chăm sóc" nhảy + toast; đang mở lịch khách đó → refetch.

## 5. UI/UX (tab Chăm sóc, `KhachHangPage`)

- Lịch **tháng** (mặc định) + **tuần**; pill hẹn màu theo mức nhắc + status.
- Click ngày trống → drawer **Hẹn mới** (note + ngày + control lặp: mỗi N ngày/tuần/tháng, đến ngày).
- Click pill → drawer occurrence: **Hoàn thành** (kèm ghi nhật ký) / **Dời** / **Hủy lần này** / **Sửa cả chuỗi**.
- Chip "Lặp: mỗi 2 tuần đến 31/12". Giữ timeline "Đã chăm sóc" (`CareEvent`) cạnh lịch.
- Theo design-system (drawer/pill/badge) → `ui-ux-pro-max` khi dựng, `styleseed` cửa cuối, `dev-browser` verify.

## 6. Tương thích ngược

Hẹn cũ (`repeat_freq='none'`) chạy y hệt hiện tại. `care-followups` / `notify-summary` không vỡ.

## 7. Chia pha (mỗi pha verify `init.ps1` + có test)

- **Pha A — BE nền**: model + migration `0077` + `expand_occurrences` + endpoints + tests.
- **Pha B — SSE**: publish + nhịp nền + FE badge/toast real-time.
- **Pha C — UI lịch**: component lịch + drawer + editor lặp + styleseed + dev-browser.

## 8. Điểm để mở (chốt khi làm)

- Chân trời bung tối đa (1 năm / 200 lần).
- "Dời cả chuỗi từ đây về sau" (split series) — pha sau hoặc bỏ.
- Nhịp SSE 60s hay 30s.
