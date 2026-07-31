// Khung "Kho" — gộp Đề nghị + Hộp yêu cầu vào MỘT module, chia tab.
//
// Hai trục tab:
//   • VIỆC:   Đề nghị · Hộp yêu cầu  (Hộp yêu cầu chỉ hiện cho vai trong kho)
//   • CHIỀU:  Nhập · Xuất            (khoá chiều cho màn con qua prop `loai`)
//
// Không tách bảng DB — vẫn 1 bảng `stock_requests`/`stock_vouchers` cột `loai`, chỉ lọc theo
// chiều. `key={loai}` để đổi chiều là remount màn con với state sạch (khỏi lẫn dữ liệu 2 chiều).
import { useState } from "react";
import type { StockRequestKind } from "../api/client";
import { useCan } from "../auth/permissions";
import { KhoDeNghiPage } from "./KhoDeNghiPage";
import { KhoYeuCauPage } from "./KhoYeuCauPage";
import "./rebuild-catalog.css";
import "./kho-request.css";

type FnTab = "denghi" | "yeucau";

export function KhoPage({ eventTick = 0 }: { eventTick?: number }) {
  const can = useCan();
  const canDeNghi = can("kho", "request") || can("kho", "approve");
  const canYeuCau = can("kho", "create") || can("kho", "view_stock");
  const [fn, setFn] = useState<FnTab>(canDeNghi ? "denghi" : "yeucau");
  const [loai, setLoai] = useState<StockRequestKind>("NHAP");
  const activeFn: FnTab =
    fn === "denghi" && !canDeNghi
      ? "yeucau"
      : fn === "yeucau" && !canYeuCau
        ? "denghi"
        : fn;

  return (
    <main className="rc">
      <div className="kho-shell">
        <div className="kho-shell__fns">
          {canDeNghi && (
            <button
              type="button"
              className={`kho-shell__fn${activeFn === "denghi" ? " is-active" : ""}`}
              onClick={() => setFn("denghi")}
            >
              <FileTextIcon />
              <span>Đề nghị</span>
            </button>
          )}
          {canYeuCau && (
            <button
              type="button"
              className={`kho-shell__fn${activeFn === "yeucau" ? " is-active" : ""}`}
              onClick={() => setFn("yeucau")}
            >
              <InboxIcon />
              <span>Phiếu từ đề nghị</span>
            </button>
          )}
        </div>
        <div className="kho-shell__dirs">
          {(["NHAP", "XUAT"] as StockRequestKind[]).map((k) => (
            <button
              key={k}
              type="button"
              className={`seg${loai === k ? " is-active" : ""}`}
              onClick={() => setLoai(k)}
            >
              {k === "NHAP" ? <ArrowDownIcon /> : <ArrowUpIcon />}
              <span>{k === "NHAP" ? "Nhập" : "Xuất"}</span>
            </button>
          ))}
        </div>
      </div>

      {activeFn === "denghi" ? (
        <KhoDeNghiPage key={`dn-${loai}`} loai={loai} eventTick={eventTick} />
      ) : (
        <KhoYeuCauPage key={`yc-${loai}`} loai={loai} eventTick={eventTick} />
      )}
    </main>
  );
}

function FileTextIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </svg>
  );
}

function InboxIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

function ArrowDownIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <polyline points="19 12 12 19 5 12" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  );
}

