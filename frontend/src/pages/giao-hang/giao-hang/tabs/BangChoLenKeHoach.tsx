// Tab "Yêu cầu giao" — danh sách yêu cầu chờ lên kế hoạch (tách từ pages/GiaoHangPage.tsx).
//
// Tick NHIỀU yêu cầu ⇒ "Lên lượt xe (N)" (chủ chốt 18/09/2026 — "gom nhiều phiếu lại chạy 1
// lượt"): mỗi yêu cầu vẫn một đơn giao hàng + một phiếu xuất kho, chung một vòng xe.
import { useEffect, useState } from "react";
import type { DeliveryRequest } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDate } from "../../../../utils/format";
import { KhoangTrong } from "../components/giaoHangCells";

// =============================================================================
// Tab · Yêu cầu giao
// =============================================================================
export function BangChoLenKeHoach({
  rows,
  loading,
  onMo,
  onLenKeHoach,
  onLenLuot,
}: {
  rows: DeliveryRequest[];
  loading: boolean;
  onMo: (id: number) => void;
  onLenKeHoach: (r: DeliveryRequest) => void;
  /** Lên CHUNG một lượt xe cho các yêu cầu đã tick. */
  onLenLuot?: (rs: DeliveryRequest[]) => void;
}) {
  // Chọn theo TRANG đang xem. Bảng tải lại (SSE, lên đơn xong) thì bỏ những dòng không còn — yêu
  // cầu đã lên đơn biến khỏi tab, giữ id của nó là gửi lại một yêu cầu đã có chuyến.
  const [chon, setChon] = useState<Set<number>>(new Set());
  useEffect(() => {
    setChon((cu) => {
      const con = new Set([...cu].filter((id) => rows.some((r) => r.id === id)));
      return con.size === cu.size ? cu : con;
    });
  }, [rows]);

  if (!loading && rows.length === 0)
    return (
      <KhoangTrong
        title="Không có yêu cầu giao nào đang chờ"
        desc="Mọi yêu cầu Bán hàng gửi sang đều đã lên đơn giao hàng. Yêu cầu mới sẽ hiện ở đây ngay, không cần tải lại trang."
      />
    );

  const doi = (id: number) =>
    setChon((cu) => {
      const moi = new Set(cu);
      if (moi.has(id)) moi.delete(id);
      else moi.add(id);
      return moi;
    });
  const tatCa = rows.length > 0 && rows.every((r) => chon.has(r.id));

  return (
    <>
      {onLenLuot && (
        <div className="gh-chon-bar">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span>Tick nhiều yêu cầu để chở chung một lượt xe.</span>
            {chon.size > 0 && (
              <span className="gh-badge" style={{ background: "#e2e8f0", color: "#0f172a", fontWeight: 600 }}>
                Đã chọn {chon.size}
              </span>
            )}
          </div>
          <Button variant="accent" disabled={chon.size === 0}
            onClick={() => onLenLuot(rows.filter((r) => chon.has(r.id)))}>
            Lên lượt xe{chon.size ? ` (${chon.size})` : ""}
          </Button>
        </div>
      )}
      <div className="rc__tablewrap">
        <table className="rc__table rc__table--fixed">
          <thead>
            <tr>
              {onLenLuot && (
                <th style={{ width: 38 }}>
                  <input type="checkbox" checked={tatCa} aria-label="Chọn tất cả yêu cầu trên trang"
                    onChange={() => setChon(tatCa ? new Set() : new Set(rows.map((r) => r.id)))} />
                </th>
              )}
              <th style={{ width: "13%" }}>Mã yêu cầu</th>
              <th style={{ width: "11%" }}>Đơn hàng</th>
              <th>Khách hàng</th>
              <th style={{ width: "13%" }}>Ngày cần giao</th>
              <th style={{ width: "18%" }}>Hàng hoá</th>
              <th style={{ width: "13%" }}>Người yêu cầu</th>
              <th style={{ width: "14%", textAlign: "right" }} />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={onLenLuot ? 8 : 7} style={{ textAlign: "center", padding: "24px", color: "#64748b" }}>
                  Đang tải…
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} style={chon.has(r.id) ? { background: "#f8fafc" } : undefined}>
                {onLenLuot && (
                  <td>
                    <input type="checkbox" checked={chon.has(r.id)} aria-label={`Chọn ${r.code}`}
                      onChange={() => doi(r.id)} />
                  </td>
                )}
                <td>
                  <button type="button" className="gh-link" onClick={() => onMo(r.id)}>
                    {r.code}
                  </button>
                </td>
                <td style={{ fontWeight: 500, color: "#334155" }}>{r.order_code}</td>
                <td style={{ fontWeight: 600, color: "#0f172a" }}>{r.customer_name}</td>
                <td style={{ color: "#334155" }}>{fmtDate(r.ngay_can_giao)}</td>
                <td className="gh-nowrap" title={r.lines
                  .map((l) => `${l.mo_ta ?? ""} × ${l.qty}${l.don_vi_tinh ? ` ${l.don_vi_tinh}` : ""}`)
                  .join(" · ")}>
                  <span className="gh-badge">{r.lines.length} mặt hàng</span>
                </td>
                <td style={{ color: "#475569" }}>{r.created_by_name}</td>
                <td style={{ textAlign: "right" }}>
                  <Button variant="accent" onClick={() => onLenKeHoach(r)}>
                    Lên đơn giao hàng
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
