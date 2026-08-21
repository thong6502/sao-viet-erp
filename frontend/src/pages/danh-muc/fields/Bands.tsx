// Ô "bậc số lượng": Từ SL · Đến SL · Giá trị · Đơn vị (tờ hay %).
import { RowEditor } from "./RowEditor";
import type { BacRow } from "../types";

export function BandsField({ value, onChange }: { value: BacRow[]; onChange: (v: BacRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<BacRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => {
    const lastRow = rows[rows.length - 1];
    const nextTu = lastRow && lastRow.sl_den != null ? lastRow.sl_den : 0;
    onChange([...rows, { sl_tu: nextTu, sl_den: null, gia_tri: 0, don_vi: lastRow?.don_vi ?? "to" }]);
  };
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  const sai = (r: BacRow) =>
    r.sl_den !== null && r.sl_den !== undefined && (r.sl_tu ?? 0) >= r.sl_den;

  return (
    <RowEditor
      rows={rows}
      cot={["Từ SL", "Đến SL", "Giá trị", "Đơn vị"]}
      trong="Chưa có bậc — bấm “＋ Thêm bậc”."
      themNhan="＋ Thêm bậc"
      onThem={add}
      onXoa={del}
      xoaTitle="Xóa bậc"
      lopHang={(r) => (sai(r) ? "rc-bands__row--invalid" : undefined)}
      veHang={(r, i) => {
        const isRangeInvalid = sai(r);
        return (
          <>
            <td>
              <input
                className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                type="number"
                value={num(r.sl_tu)}
                title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                onChange={(e) => setRow(i, { sl_tu: e.target.value === "" ? 0 : Number(e.target.value) })}
              />
            </td>
            <td>
              <input
                className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                type="number"
                placeholder="∞"
                value={num(r.sl_den)}
                title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                onChange={(e) => setRow(i, { sl_den: e.target.value === "" ? null : Number(e.target.value) })}
              />
            </td>
            <td>
              <input
                className="rc-input rc-input--num"
                type="number"
                step="any"
                value={num(r.gia_tri)}
                onChange={(e) => setRow(i, { gia_tri: e.target.value === "" ? 0 : Number(e.target.value) })}
              />
            </td>
            <td style={{ textAlign: "center" }}>
              <div className="rc-bands__unit-toggle">
                <button
                  type="button"
                  className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "to" ? " is-active" : ""}`}
                  onClick={() => setRow(i, { don_vi: "to" })}
                >
                  Tờ
                </button>
                <button
                  type="button"
                  className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "pct" ? " is-active" : ""}`}
                  onClick={() => setRow(i, { don_vi: "pct" })}
                >
                  %
                </button>
              </div>
            </td>
          </>
        );
      }}
    />
  );
}
