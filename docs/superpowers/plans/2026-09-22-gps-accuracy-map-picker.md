# GPS Accuracy And Map Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve GPS acquisition by waiting for the best fresh reading and let administrators place a work-location geofence accurately on a map inside the existing modal.

**Architecture:** Keep browser positioning in the existing shared helper, but replace the one-shot acquisition with a bounded `watchPosition` collector that resolves early on a good fix and otherwise returns the best acceptable sample. Add a focused map-picker component used only by the existing location form; the form remains the single create/edit flow and the server payload is unchanged.

**Tech Stack:** React 18, TypeScript, Vitest, browser Geolocation API, MapLibre GL JS.

---

### Task 1: Collect the best GPS sample

> **ĐÃ THAY THẾ 23/09/2026.** Cách thu nhiều mẫu trong 20 giây bị gỡ: máy bàn định vị bằng
> Wi-Fi nên sai số không hội tụ, lần nào cũng chờ hết cửa sổ rồi báo đỏ. `getPosition` nay
> dùng ngay mẫu đầu tiên và không còn ngưỡng 30/50 m.

**Files:**
- Modify: `frontend/src/pages/nhan-su-luong/cham-cong/shared/helpers.ts`
- Test: `frontend/src/pages/nhan-su-luong/cham-cong/shared/helpers.gps.test.ts`

- [ ] Add failing tests proving that several `watchPosition` samples are observed, a fix at or below 30 m resolves early, and the best sample at or below 50 m is used when the collection window expires.
- [ ] Run `npm test -- --run src/pages/nhan-su-luong/cham-cong/shared/helpers.gps.test.ts` from `frontend` and confirm the tests fail because the current helper calls `getCurrentPosition`.
- [ ] Implement a bounded watcher with `enableHighAccuracy: true`, `maximumAge: 0`, cleanup through `clearWatch`, best-sample selection, early success at 30 m, and rejection when no sample reaches 50 m.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Add the map picker to the current modal

**Files:**
- Create: `frontend/src/pages/nhan-su-luong/cham-cong/components/LocationMapPicker.tsx`
- Modify: `frontend/src/pages/nhan-su-luong/cham-cong/modals/LocationForm.tsx`
- Modify: `frontend/src/pages/cham-cong.css`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Test: `frontend/src/pages/nhan-su-luong/cham-cong/modals/LocationForm.test.tsx`

- [ ] Scan the MapLibre package source with `skillspector scan <package-path> --no-llm` before adding it to the project, and inspect every finding.
- [ ] Add a failing form test proving map coordinate changes update the existing latitude/longitude fields without creating a second workflow.
- [ ] Install MapLibre GL JS and scan the installed package again.
- [ ] Implement a reusable map picker with a draggable marker, click-to-place behavior, a radius circle, loading/error states, and cleanup on unmount.
- [ ] Mount the picker inside `LocationForm`, synchronize it with GPS/manual input/radius presets, and retain the current API payload.
- [ ] Add scoped styles using the existing design tokens and responsive rules.
- [ ] Run the focused form tests and confirm they pass.

### Task 3: Verify behavior and presentation

**Files:**
- Review: all files changed above

- [ ] Run the complete frontend test suite with `npm test`.
- [ ] Run the production build with `npm run build`.
- [ ] Start the application using the project workflow, inspect the modal with browser automation, and verify GPS progress, map dragging/clicking, radius synchronization, error state, and mobile layout.
- [ ] Run the StyleSeed design review, apply fixes until the changed UI scores at least 80, and re-run the relevant tests/build.
- [ ] Run the repository verification command `./init.ps1` and report the actual result.

