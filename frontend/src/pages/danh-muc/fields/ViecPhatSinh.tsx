// VIỆC PHÁT SINH của một công việc khoán (In 4 màu → Thay kẽm · 100 đ · bản kẽm).
//
// Thứ bậc chủ xưởng chốt: tổ → công đoạn → công việc khoán → việc phát sinh. Tổ và công đoạn đã có
// ở công việc khoán cha, nên mỗi dòng chỉ ba ô, theo ĐÚNG thứ tự chủ xưởng đọc: Tên việc · Đơn giá ·
// Đơn vị tính. Đợt đầu chỉ khai báo — sản xuất chưa đọc bảng này.
//
// `id` của dòng đã lưu đi theo dòng (sửa tên/giá không làm mất nó) — server dựa vào đó để sửa đúng
// hàng cũ thay vì đẻ hàng mới. Luật khai (trống · trùng tên · đơn vị ngoài danh mục) nằm ở server,
// câu lỗi gọi đúng tên việc; ở đây không lặp lại để khỏi thành hai bộ luật lệch nhau.
//
// Ví dụ khai nằm ở dòng "chưa có gì" + chữ mờ trong ô, KHÔNG nằm ở gợi ý dưới bảng: gợi ý dưới bảng
// bị menu đơn vị của dòng cuối trùm lên đúng lúc người ta đang khai.
import { useState } from "react";

import type { Row, ViecPhatSinhRow } from "../types";
import { RefSearchField } from "./RefFields";
import { RowEditor } from "./RowEditor";

export function ViecPhatSinhField({
  value,
  donViOptions,
  onChange,
}: {
  value: ViecPhatSinhRow[];
  /** Danh mục Đơn vị & quy đổi (đã bỏ mục ngừng dùng, trừ mục đang chọn). */
  donViOptions: Row[];
  onChange: (v: ViecPhatSinhRow[]) => void;
}) {
  const rows = value ?? [];
  // Dòng vừa bấm "＋ Thêm" — con trỏ nhảy thẳng vào ô Tên việc của nó, khỏi phải với chuột lần nữa.
  const [dongMoi, setDongMoi] = useState<number | null>(null);
  const setRow = (i: number, patch: Partial<ViecPhatSinhRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <RowEditor
      khoa="rc-bands--vps"
      rows={rows}
      cot={["Tên việc", "Đơn giá", "Đơn vị tính"]}
      trong="Chưa có việc phát sinh"
      themNhan="＋ Thêm việc phát sinh"
      onThem={() => {
        setDongMoi(rows.length);
        onChange([...rows, { ten: "", don_gia: null, don_vi: "" }]);
      }}
      onXoa={(i) => { setDongMoi(null); onChange(rows.filter((_, j) => j !== i)); }}
      xoaTitle="Xóa việc phát sinh"
      veHang={(r, i) => (
        <>
          <td>
            <input
              className="rc-input"
              aria-label={`Tên việc dòng ${i + 1}`}
              value={r.ten ?? ""}
              placeholder="vd: Thay kẽm"
              maxLength={255}
              autoFocus={i === dongMoi}
              onChange={(e) => setRow(i, { ten: e.target.value })}
            />
          </td>
          <td>
            <div className="rc-input-wrapper">
              <input
                className="rc-input rc-input--num"
                aria-label={`Đơn giá dòng ${i + 1}`}
                type="number"
                min={0}
                step="any"
                inputMode="decimal"
                placeholder="vd: 100"
                value={r.don_gia === undefined || r.don_gia === null ? "" : String(r.don_gia)}
                onChange={(e) => setRow(i, { don_gia: e.target.value === "" ? null : Number(e.target.value) })}
              />
              <span className="rc-input-suffix">đ</span>
            </div>
          </td>
          <td>
            <RefSearchField
              value={r.don_vi ? r.don_vi : null}
              options={donViOptions}
              placeholder="Gõ để tìm đơn vị…"
              byMa
              onChange={(v) => setRow(i, { don_vi: v == null ? "" : String(v) })}
            />
          </td>
        </>
      )}
    />
  );
}
