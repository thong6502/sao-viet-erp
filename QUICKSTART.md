# QUICKSTART — Bắt đầu từ đâu

> File này dành cho **con người** đọc nhanh để hiểu luồng. Agent thì đọc `AGENTS.md`.
> Việc nối dây phần an toàn (hook/trust) nằm ở `SETUP.md`.

Harness này = **một vòng lặp làm việc** + **6 module lan can** bao quanh.
Ngày thường bạn chỉ cần nhớ vòng lặp. Các module phần lớn tự chạy hoặc chỉ dùng khi cần.

---

## TL;DR — chạy thử ngay

```bash
./init.sh        # Unix / macOS / CI
# hoặc trên Windows:
./init.ps1       # PowerShell
```

Lệnh này = "đèn xanh môi trường": chạy test (`pytest`) + biên dịch (`compileall`).
Hiện tại nó **PASS** sẵn (3 test của hook bảo vệ). Nếu nó đỏ → sửa nó TRƯỚC khi làm gì khác.

---

## Vòng lặp cốt lõi (mọi phiên làm việc đều theo đây)

```
BẮT ĐẦU  →  CHỌN VIỆC  →  LÀM  →  XÁC MINH  →  KẾT THÚC
```

1. **BẮT ĐẦU** — đọc `AGENTS.md`, đọc `memory/MEMORY.md`, chạy `./init.sh` (hoặc `./init.ps1`),
   đọc `feature_list.json` xem đang ở đâu.
2. **CHỌN VIỆC** — chọn **đúng MỘT** feature chưa xong trong `feature_list.json`
   (`status` khác `done`). Không ôm nhiều việc cùng lúc.
3. **LÀM** — code feature đó, không đụng file ngoài phạm vi.
4. **XÁC MINH** — chạy lại `./init.sh`, phải PASS. Ghi bằng chứng (lệnh + kết quả)
   vào ô `evidence` của feature trong `feature_list.json`.
5. **KẾT THÚC** — cập nhật `progress.md` + `feature_list.json` (đổi `status`),
   ghi `memory/` nếu có quyết định lâu dài, điền `session-handoff.md`, rồi `git commit`.

**3 quy tắc bất biến:** một feature một lúc · luôn xác minh trước khi nói "xong" ·
để repo sạch để phiên sau chạy `./init.sh` được ngay.

---

## Bản đồ file — cái nào để làm gì

| File / thư mục | Dùng để |
|---|---|
| `AGENTS.md` | **Nguồn chỉ dẫn chính** cho agent (luồng, quy tắc, định nghĩa "xong") |
| `CLAUDE.md` | Chỉ trỏ về `AGENTS.md` (để Claude Code tự tìm thấy) |
| `feature_list.json` | **Sổ trạng thái**: danh sách feature + `status` + `evidence` |
| `progress.md` | Nhật ký phiên: đang làm gì, kẹt ở đâu, làm gì tiếp |
| `session-handoff.md` | Bàn giao cho phiên sau (khi việc lớn, kéo dài nhiều phiên) |
| `init.sh` / `init.ps1` | Lệnh xác minh chuẩn (bash / PowerShell) |
| `pytest.ini` | Cấu hình để `pytest` tìm thấy test (kể cả test trong `.claude/`) |
| `memory/` | Ghi nhớ lâu dài: `MEMORY.md` (chỉ mục) + `topics/<slug>.md` (chi tiết) |
| `docs/` | Giao thức từng module: `CONTEXT*`, `TOOL_SAFETY`, `LIFECYCLE`, `COORDINATION` |
| `.claude/settings.json` | Quyền (allow/ask/deny) + đăng ký hook |
| `.claude/hooks/` | Hook: `guard_bash.py` (chặn lệnh nguy hiểm), `dispatch.py` (mở/đóng phiên) |
| `.claude/skills/` | Skill tái dùng — gõ `/run-feature` để chạy đúng vòng lặp trên |
| `coordination/` | Khi giao việc cho agent con: sổ task + chống đệ quy fork |
| `tools/` | Tiện ích bảo trì (vd quét file memory mồ côi) |
| `SETUP.md` | **Danh sách việc cần nối dây** trước khi dùng thật |

---

## Quan trọng: cái gì ĐANG chạy vs cái gì mới là KHUNG

- ✅ **Dùng được ngay:** `AGENTS.md`/`CLAUDE.md`, `init.*` (đã xanh), `feature_list.json`,
  `progress.md`. Đây là vòng lặp cốt lõi.
- ⚠️ **Mới là khung, CHƯA tự chạy:** các hook bảo vệ (`guard_bash.py`, `fork_guard.py`,
  `dispatch.py`) chỉ kích hoạt khi workspace "được tin cậy", mà hàm
  `workspace_is_trusted()` còn là `<PLACEHOLDER>`. Xem `SETUP.md` mục 1 để bật.
- 📝 Còn nhiều `<PLACEHOLDER>` trong `memory/`, `docs/`, `guard_bash.py`… cần điền theo
  dự án thật của bạn.

---

## Việc đầu tiên nên làm (theo thứ tự)

1. Mở `feature_list.json`, thay `feat-002 … feat-005` (đang là placeholder) bằng
   feature thật đầu tiên của bạn.
2. Khi đã có code Python thật + test → `./init.sh` sẽ kiểm chứng dự án của bạn, không chỉ test hook.
3. Đọc `SETUP.md` và nối dây trust signal nếu muốn các lan can an toàn hoạt động.
4. Bắt đầu vòng lặp ở trên (hoặc gõ `/run-feature`).
