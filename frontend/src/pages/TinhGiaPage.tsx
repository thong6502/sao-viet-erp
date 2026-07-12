// Tính giá — CONTROLLER master↔detail. Không có react-router: điều hướng bằng state nội bộ.
// mode "list" → danh sách phiếu (PhieuTinhGiaListView); mode "detail" → 1 phiếu (PhieuTinhGiaDetailView,
// chính là form giá vốn bản redesign đã duyệt, nay gắn với phiếu đã lưu).
import { useState } from "react";
import { PhieuTinhGiaListView } from "./PhieuTinhGiaListView";
import { PhieuTinhGiaDetailView } from "./PhieuTinhGiaDetailView";
import "./tinh-gia.css";

type View = { mode: "list" } | { mode: "detail"; id: number };

export function TinhGiaPage() {
  const [view, setView] = useState<View>({ mode: "list" });

  if (view.mode === "detail") {
    return (
      <PhieuTinhGiaDetailView id={view.id} onBack={() => setView({ mode: "list" })} />
    );
  }
  return (
    <PhieuTinhGiaListView
      onOpen={(id) => setView({ mode: "detail", id })}
      onNew={(id) => setView({ mode: "detail", id })}
    />
  );
}
