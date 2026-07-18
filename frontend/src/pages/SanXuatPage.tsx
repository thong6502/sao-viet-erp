// Sản xuất — CONTROLLER master↔detail cho "Kế hoạch SX" (không react-router: state nội bộ,
// bám TinhGiaPage). mode "list" → danh sách lệnh; mode "detail" → 1 lệnh (theo dõi end-to-end).
// Các item nav anh em (Theo dõi SX · Nhập liệu xưởng · QC/KCS) thuộc chunk sau → placeholder.
import { useState } from "react";
import { LenhSanXuatListView } from "./LenhSanXuatListView";
import { LenhSanXuatDetailView } from "./LenhSanXuatDetailView";
import { GhepBaiView } from "./GhepBaiView";
import "./lenh-san-xuat.css";

// Controller nội bộ (không react-router): list ↔ detail 1 lệnh ↔ ghép bài (dựng tờ in).
type View = { mode: "list" } | { mode: "detail"; id: number } | { mode: "ghep"; preselect?: number };

export function SanXuatPage() {
  const [view, setView] = useState<View>({ mode: "list" });

  if (view.mode === "ghep") {
    return (
      <GhepBaiView
        preselectLenhId={view.preselect}
        onBack={() => setView({ mode: "list" })}
        onOpenLenh={(id) => setView({ mode: "detail", id })}
      />
    );
  }
  if (view.mode === "detail") {
    return (
      <LenhSanXuatDetailView
        id={view.id}
        onBack={() => setView({ mode: "list" })}
        onGhep={(lenhId) => setView({ mode: "ghep", preselect: lenhId })}
      />
    );
  }
  return (
    <LenhSanXuatListView
      onOpen={(id) => setView({ mode: "detail", id })}
      onGhep={() => setView({ mode: "ghep" })}
    />
  );
}
