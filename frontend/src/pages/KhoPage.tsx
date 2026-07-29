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
  // Tab ĐỀ NGHỊ = phía XIN/DUYỆT (tạo đề nghị hoặc duyệt đề nghị). Vai KHO thuần (chỉ cấp phát)
  // KHÔNG thấy tab này — họ xử lý ở "Phiếu từ đề nghị".
  const canDeNghi = can("kho", "request") || can("kho", "approve");
  // Phiếu từ đề nghị = vai TRONG kho (lập phiếu hoặc xem tồn).
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
              Đề nghị
            </button>
          )}
          {canYeuCau && (
            <button
              type="button"
              className={`kho-shell__fn${activeFn === "yeucau" ? " is-active" : ""}`}
              onClick={() => setFn("yeucau")}
            >
              Phiếu từ đề nghị
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
              {k === "NHAP" ? "Nhập" : "Xuất"}
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
