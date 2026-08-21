// Tính giá — CONTROLLER master↔detail. Không có react-router: điều hướng bằng state nội bộ.
// mode "list" → danh sách phiếu (PhieuTinhGiaListView); mode "detail" → 1 phiếu (PhieuTinhGiaDetailView,
// chính là form giá vốn bản redesign đã duyệt, nay gắn với phiếu đã lưu).
import { useState } from "react";
import { PhieuTinhGiaListView } from "./PhieuTinhGiaListView";
import { PhieuTinhGiaDetailView } from "./PhieuTinhGiaDetailView";
import "./tinh-gia.css";

// id = null ⇒ phiếu NHÁP chưa ghi DB (bấm "Lập phiếu" chỉ mở form, chưa gọi API). Phiếu chỉ
// được tạo thật khi có ≥1 sản phẩm và bấm Tính giá — bỏ ngang thì không để lại phiếu rỗng.
type View = { mode: "list" } | { mode: "detail"; id: number | null };

export function TinhGiaPage({ navigate, openPhieuId }: {
  // BG-3: điều hướng sang Báo giá (nút "Báo giá →" trên phiếu). Không truyền → ẩn nút.
  navigate?: (pageId: string, params?: { openQuoteId?: number }) => void;
  // P3 (redesign-bao-gia §6): mở thẳng 1 phiếu tính giá (link "↳ PTG" từ Báo giá).
  openPhieuId?: number;
} = {}) {
  const [view, setView] = useState<View>(
    openPhieuId ? { mode: "detail", id: openPhieuId } : { mode: "list" },
  );

  if (view.mode === "detail") {
    return (
      <PhieuTinhGiaDetailView
        id={view.id}
        onBack={() => setView({ mode: "list" })}
        navigate={navigate}
      />
    );
  }
  return (
    <PhieuTinhGiaListView
      onOpen={(id) => setView({ mode: "detail", id })}
      onNew={() => setView({ mode: "detail", id: null })}
    />
  );
}
