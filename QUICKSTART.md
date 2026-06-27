# QUICKSTART — Bắt đầu từ đâu

> File này dành cho **con người** đọc nhanh để hiểu luồng GAN. Agent thì đọc `AGENTS.md`.

Template này = **vòng lặp GAN 3 vai** để dựng một app **React + Vite (frontend) · FastAPI (backend) · SQLite/Postgres (DB)** theo từng feature một, có người làm Planner.

```text
Spec  →  🧠 plan  →  feature_list.json  →  🔨 generate  ⇄  🔍 browser-validate  →  review
   (người)      (skill)        (sổ feature)         (build)        (chấm điểm, lặp lại)    (người)
```

---

## Bước 0 — App skeleton CHƯA có sẵn, dựng nó trước

⚠️ Đây là **TEMPLATE**, không phải app. Source của app (React + Vite + FastAPI + DB) **chưa được ship**. Trước khi chạy vòng lặp, hãy dựng khung tối thiểu để app chạy được và `init` xác minh được:

- Khung frontend React + Vite, backend FastAPI, kết nối DB SQLite/Postgres — theo `docs/ARCHITECTURE.md`.
- Mọi chỗ đặc thù dự án còn để `<PLACEHOLDER>` thì điền theo dự án thật của bạn.
- Chạy `./init.sh` (Unix/macOS/CI) hoặc `./init.ps1` (Windows/PowerShell) — phải **PASS** (`pytest` smoke `tests/test_template_smoke.py` + `compileall`). Đỏ thì sửa TRƯỚC.

---

## Bước 1 — Viết spec (người)

Tạo `docs/product-specs/<spec>.md` từ `docs/product-specs/_TEMPLATE.md`, ghi danh mục vào `docs/product-specs/index.md`.
Mô tả mục tiêu spec, phạm vi, và acceptance criteria mong muốn. Tham khảo `docs/PRODUCT_SENSE.md` để biết "tốt" nghĩa là gì.

## Bước 2 — Chạy skill 🧠 plan

Gọi skill `plan` (`.claude/skills/plan/SKILL.md`). Skill này:

1. Đọc spec của bạn.
2. **DỪNG để hỏi** — trình một **menu lựa chọn** mức độ chi tiết (kèm tùy chọn "Other" để tự nhập). Nó không bao giờ tự chạy tiếp.
3. Tinh chỉnh theo lựa chọn của bạn rồi điền `feature_list.json` (`feat-001..N` + acceptance criteria).

## Bước 3 — Chạy workflow gan-loop

Chạy orchestrator `.claude/workflows/gan-loop.js`. Nó tự lái bước 3–5 của vòng lặp, mỗi lần **MỘT feature**:

- 🔨 **generate** (`.claude/skills/generate/SKILL.md`) — build feature từ spec + `docs/UI_DESIGN.md`, rồi tự xác minh bằng `init`.
- 🔍 **browser-validate** (`.claude/skills/browser-validate/SKILL.md`) — Playwright click app đang chạy, chấm 4 tiêu chí (design quality, originality, craft, functionality) theo `docs/EVALUATION.md`.
- Điểm dưới ngưỡng → tiêu chí yếu nhất được feed ngược về 🔨 để build lại, **lặp** tới khi đạt hoặc hết budget.

## Bước 4 — Review (người)

Xem điểm đã ghi trong `docs/EVALUATION.md`, tiến độ trong `progress.md`, và trạng thái trong `feature_list.json`. Duyệt feature, rồi quay lại Bước 1 cho spec kế tiếp.

---

## Bản đồ file — theo vai

| Vai | File / thư mục | Dùng để |
|---|---|---|
| Router | `AGENTS.md` | **Chỉ dẫn chính** cho agent (luồng, quy tắc, "xong" là gì) |
| Router | `CLAUDE.md` | Chỉ trỏ về `AGENTS.md` |
| Người | `QUICKSTART.md` | File này — đường nhanh nhất chạy vòng lặp |
| Người | `docs/product-specs/_TEMPLATE.md` · `index.md` | Mẫu spec + danh mục |
| Người | `docs/PRODUCT_SENSE.md` | Thước đo "tốt" cho feature |
| 🧠 plan | `.claude/skills/plan/SKILL.md` | Spec → `feature_list.json` (hỏi menu, dừng lại) |
| Sổ | `feature_list.json` | Danh sách feature + `status` + `evidence` |
| 🔨 generate | `.claude/skills/generate/SKILL.md` | Build + xác minh một feature |
| 🔨 generate | `docs/ARCHITECTURE.md` · `docs/UI_DESIGN.md` (assets: `docs/design-assets/`) | Layout/quy ước stack + design system |
| 🔍 validate | `.claude/skills/browser-validate/SKILL.md` · `docs/sops/browser-validation-loop.md` | Playwright chấm app đang chạy |
| 🔍 validate | `docs/EVALUATION.md` | 4 tiêu chí, ngưỡng, và điểm đã ghi |
| Orchestrator | `.claude/workflows/gan-loop.js` | Lái generate → validate → feedback |
| Tham chiếu | `docs/ORCHESTRATION.md` | 3 vai + `gan-loop.js` ráp với nhau ra sao |
| Tham chiếu | `docs/SECURITY.md` | Secrets, dữ liệu không tin cậy, hành động ngoài |
| Xác minh | `init.sh` / `init.ps1` · `pytest.ini` · `tests/test_template_smoke.py` | Lệnh xác minh chuẩn (smoke + compileall) |
| Nhật ký | `progress.md` | Đang làm gì, kẹt ở đâu, làm gì tiếp |
| Skill meta | `.claude/skills/README.md` · `.claude/skills/scripts/validate-skills.{sh,ps1}` | Viết & kiểm tra skill |

---

## Khôi phục bản đầy đủ

Template này là bản **rút gọn**. Nhiều module nặng (memory, hooks, coordination, các SOP/docs mở rộng…) đã được lược bỏ. Để lấy lại bản đầy đủ:

```bash
git checkout full-pack    # checkout tag bản đầy đủ
```

Xem các tag có sẵn bằng `git tag`.
