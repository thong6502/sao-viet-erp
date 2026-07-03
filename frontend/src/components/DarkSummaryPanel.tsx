import type { ReactNode } from "react";
import "./ui-blocks.css";

export interface DarkPanelRow {
  label: string;
  value: string;
  /** true = dòng tổng (kẻ trên, giá trị màu nhấn to) */
  total?: boolean;
}

/** Panel tổng tiền nền tối (kiểu "TỔNG GIÁ VỐN (NỘI BỘ)" / "GIÁ BÁN ĐỀ XUẤT"). */
export function DarkSummaryPanel({
  label,
  labelExtra,
  amount,
  unit = "đ",
  sub,
  note,
  rows,
  children,
}: {
  label: string;
  /** Chữ nhỏ màu nhấn cạnh label (VD "V3") */
  labelExtra?: string;
  /** Số tiền đã format ("20.609.331") — null hiện "—" */
  amount: string | null;
  unit?: string;
  /** Dòng phụ dưới số to: "≈ 2.061đ/cái giá vốn" */
  sub?: string;
  /** Ghi chú đóng khung (VD "chưa cộng lợi nhuận...") */
  note?: ReactNode;
  /** Các dòng con (subtotal theo nhóm, dẫn tiền) */
  rows?: DarkPanelRow[];
  /** Nội dung tùy biến chèn giữa (gói biên, slider...) */
  children?: ReactNode;
}) {
  return (
    <div className="dpanel">
      <div className="dpanel__label">
        <span>{label}</span>
        {labelExtra && <span className="dpanel__label-extra">{labelExtra}</span>}
      </div>
      <div className="dpanel__amount">
        {amount ?? "—"}
        {amount !== null && <small>{unit}</small>}
      </div>
      {sub && <div className="dpanel__sub">{sub}</div>}
      {note && <div className="dpanel__note">{note}</div>}
      {children && <div className="dpanel__body">{children}</div>}
      {rows && rows.length > 0 && (
        <div className="dpanel__rows">
          {rows.map((r, i) => (
            <div key={i} className={`dpanel__row ${r.total ? "dpanel__row--total" : ""}`}>
              <span>{r.label}</span>
              <span className="dpanel__row-value">{r.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
