// Ô "bậc số lượng" của bù hao — nay nằm TRÊN công đoạn (22/09/2026), không còn danh mục riêng.
//
// Người khai chỉ nhập MỐC TRÊN. Cận dưới là mốc của bậc liền trước, nhãn tự nối: "Đến 3.000" ·
// "Trên 3.000 đến 10.000" · "Trên 10.000". Bỏ ô "Từ SL" là chốt của thiết kế: còn hai đầu tự gõ
// thì khai được khoảng HỞ (3.000→7.000 rồi 8.000→…) lẫn khoảng CHỒNG, mà cả hai đều không báo lỗi
// lúc lưu — chỉ ra số sai lúc tính giá. Bậc cuối luôn vô hạn nên không có ô mốc và không xoá được.
import { RowEditor } from "./RowEditor";
import type { BacRow } from "../types";

const voHan = (r: BacRow) => r.sl_den === null || r.sl_den === undefined;
const so = (v: number) => Number(v).toLocaleString("vi-VN");

export function BandsField({ value, onChange }: { value: BacRow[]; onChange: (v: BacRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<BacRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  /** Mốc của bậc LIỀN TRƯỚC — cận dưới của bậc `i`. Bậc đầu bắt từ 0. */
  const canDuoi = (i: number) => {
    const truoc = rows[i - 1];
    return truoc && !voHan(truoc) ? Number(truoc.sl_den) : 0;
  };

  // "Thêm bậc" CHÈN TRƯỚC bậc vô hạn — nó phải ở cuối, không thì chuỗi tra bậc đứt ở giữa. Bậc mới
  // mượn mốc của bậc vô hạn liền trước (bằng cận dưới của nó) để hàng hiện lên đã có số, người khai
  // chỉ việc sửa; chưa có bậc nào thì bậc đầu tiên mở ra chính là bậc vô hạn.
  const add = () => {
    const iVo = rows.findIndex(voHan);
    const donVi = rows[rows.length - 1]?.don_vi ?? "to";
    if (iVo < 0) {
      onChange([...rows, { sl_den: null, gia_tri: 0, don_vi: donVi }]);
      return;
    }
    const moi: BacRow = { sl_den: canDuoi(iVo), gia_tri: 0, don_vi: donVi };
    onChange([...rows.slice(0, iVo), moi, ...rows.slice(iVo)]);
  };

  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  /** Mốc phải TĂNG DẦN — hàng nào phá thứ tự thì tô đỏ ngay tại chỗ, không đợi lưu. */
  const sai = (r: BacRow, i: number) => !voHan(r) && canDuoi(i) >= Number(r.sl_den);

  return (
    <RowEditor
      rows={rows}
      cot={["Khoảng số lượng", "Giá trị", "Đơn vị"]}
      khoa="rc-bands--bac"
      trong="Chưa có bậc — bấm “＋ Thêm bậc”."
      themNhan="＋ Thêm bậc"
      onThem={add}
      onXoa={del}
      xoaTitle="Xóa bậc"
      khoaXoa={voHan}
      lopHang={(r, i) => (sai(r, i) ? "rc-bands__row--invalid" : undefined)}
      veHang={(r, i) => {
        const lech = sai(r, i);
        const duoi = canDuoi(i);
        const nhan = voHan(r)
          ? (i === 0 ? "Mọi số lượng" : `Trên ${so(duoi)}`)
          : (i === 0 ? "Đến" : `Trên ${so(duoi)} đến`);
        return (
          <>
            <td>
              <div className="rc-bands__range">
                <span className="rc-bands__range-lbl">{nhan}</span>
                {!voHan(r) && (
                  <input
                    className={`rc-input rc-input--num${lech ? " rc-input--invalid" : ""}`}
                    type="number"
                    title={lech ? "Mốc phải lớn hơn mốc của bậc trên nó" : "Mốc trên của bậc"}
                    value={num(r.sl_den)}
                    onChange={(e) =>
                      setRow(i, { sl_den: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                )}
              </div>
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
