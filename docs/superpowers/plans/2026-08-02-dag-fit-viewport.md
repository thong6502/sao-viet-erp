# DAG Fit Viewport Implementation Plan

> **For agentic workers:** Execute inline in the current session; do not use subagents.

**Goal:** Thêm thanh kéo ngang thật và để người dùng chủ động zoom routing DAG.

**Architecture:** Tách phép tính chiều rộng nội dung thành hàm thuần. Canvas có width theo node ngoài
cùng, viewport dùng overflow-x; auto-layout đưa về 100% và không có observer ghi đè zoom.

**Tech Stack:** React 18, TypeScript, CSS, pytest UI contract.

---

### Task 1: Khóa hợp đồng fit

**Files:**
- Modify: `backend/tests/test_khsx_ui_contract.py`
- Modify: `frontend/src/components/DagRoutingCanvas.tsx`

- [ ] Viết test thất bại yêu cầu hàm fit, ResizeObserver và nút auto-layout gọi fit.
- [ ] Chạy test, xác nhận fail vì chưa có hành vi.

### Task 2: Cài phép tính vừa khung

**Files:**
- Modify: `frontend/src/components/DagRoutingCanvas.tsx`
- Modify: `frontend/src/pages/dag-routing.css`

- [ ] Thêm hàm bounds/fit có giới hạn zoom và padding.
- [ ] Tính chiều cao động theo số node lớn nhất trong tầng.
- [ ] Gọi fit khi mở, resize và auto-layout.
- [ ] Chạy test contract và TypeScript.

### Task 3: Rà giao diện

**Files:**
- Review: `frontend/src/components/DagRoutingCanvas.tsx`
- Review: `frontend/src/pages/dag-routing.css`

- [ ] Chạy StyleSeed review theo source/CSS, bảo đảm giữ cùng token và hierarchy hiện tại.
- [ ] Không commit hoặc push nếu người dùng chưa yêu cầu.
