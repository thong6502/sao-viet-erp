// Sản xuất — CONTROLLER master↔detail cho "Kế hoạch SX" (không react-router: state nội bộ,
// bám TinhGiaPage). mode "list" → danh sách lệnh; mode "detail" → 1 lệnh (theo dõi end-to-end).
// Các item nav anh em (Theo dõi SX · Nhập liệu xưởng · QC/KCS) thuộc chunk sau → placeholder.
import { useState } from "react";
import { LenhSanXuatListView } from "./LenhSanXuatListView";
import { LenhSanXuatDetailView } from "./LenhSanXuatDetailView";
import "./lenh-san-xuat.css";

type View = { mode: "list" } | { mode: "detail"; id: number };

export function SanXuatPage() {
  const [view, setView] = useState<View>({ mode: "list" });

  if (view.mode === "detail") {
    return <LenhSanXuatDetailView id={view.id} onBack={() => setView({ mode: "list" })} />;
  }
  return <LenhSanXuatListView onOpen={(id) => setView({ mode: "detail", id })} />;
}

// Placeholder cho các màn Sản xuất thuộc chunk kế (theo dõi / nhập liệu xưởng / QC-KCS) — route tạm
// để nav không dẫn về Dashboard. Màn thợ (textless) sẽ thay ở chunk sau.
const SOON: Record<string, { title: string; sub: string }> = {
  "theo-doi-sx": {
    title: "Theo dõi sản xuất",
    sub: "Bảng điều độ tờ in theo máy & tiến độ lệnh theo thời gian thực — đang phát triển ở chunk kế.",
  },
  "nhap-lieu-xuong": {
    title: "Nhập liệu xưởng",
    sub: "Màn cho tổ trưởng ghi sản lượng / bàn giao ngay tại xưởng (tối giản, ít chạm) — chunk kế.",
  },
  "qc-kcs": {
    title: "QC / KCS",
    sub: "Màn KCS nêu lỗi kèm ảnh & tổ trưởng xác nhận — chunk kế.",
  },
};

export function SanXuatComingSoon({ featureId }: { featureId: string }) {
  const f = SOON[featureId] ?? { title: "Sản xuất", sub: "Màn này đang được phát triển." };
  return (
    <main className="lsx">
      <div className="lsx-soon">
        <span className="lsx-soon__ic">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 8.6 12 4l9 4.6" />
            <path d="M5 10.4V20h14v-9.6" />
            <rect x="9" y="13.5" width="6" height="6.5" />
          </svg>
        </span>
        <h1 className="lsx-soon__title">{f.title}</h1>
        <p className="lsx-soon__sub">{f.sub}</p>
      </div>
    </main>
  );
}
