// CHUẨN BỊ THEO KHOẢN (thay giấy 15p · thay mực 18p → tổng 33p).
//
// Tổng là ô CHỈ ĐỌC, tự cộng. Cho sửa tay ô tổng là đẻ nguồn chân lý thứ hai: sửa một khoản rồi
// tổng không khớp thì không ai biết bên nào đúng. Tổng này chính là số ghi vào
// `makeready_time_default` — cột Xếp lịch đang đọc (xem `transformSubmit` của CFG_MAY).
import { RowEditor } from "./RowEditor";
import type { ChuanBiKhoanRow } from "../types";

export function tongChuanBi(rows: ChuanBiKhoanRow[] | undefined): number {
  return (rows ?? []).reduce((s, r) => s + (Number(r.phut) || 0), 0);
}

export function ChuanBiKhoanField({
  value,
  onChange,
}: { value: ChuanBiKhoanRow[]; onChange: (v: ChuanBiKhoanRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<ChuanBiKhoanRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => onChange([...rows, { ten: "", phut: 0 }]);
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const tong = tongChuanBi(rows);

  return (
    <RowEditor
      rows={rows}
      cot={["Việc chuẩn bị", "Số phút"]}
      trong="Chưa có khoản — bấm “＋ Thêm khoản”."
      themNhan="＋ Thêm khoản"
      onThem={add}
      onXoa={del}
      xoaTitle="Xóa khoản"
      chan={
        <tfoot>
          <tr>
            <td style={{ textAlign: "right", fontWeight: 600 }}>Tổng (tự cộng)</td>
            <td style={{ fontWeight: 700 }}>{tong.toLocaleString("vi-VN")} phút</td>
            <td />
          </tr>
        </tfoot>
      }
      veHang={(r, i) => (
        <>
          <td>
            <input
              className="rc-input"
              value={r.ten ?? ""}
              placeholder="vd: Thay giấy"
              onChange={(e) => setRow(i, { ten: e.target.value })}
            />
          </td>
          <td>
            <input
              className="rc-input rc-input--num"
              type="number"
              step="any"
              inputMode="decimal"
              value={r.phut === undefined || r.phut === null ? "" : String(r.phut)}
              onChange={(e) => setRow(i, { phut: e.target.value === "" ? undefined : Number(e.target.value) })}
            />
          </td>
        </>
      )}
    />
  );
}
