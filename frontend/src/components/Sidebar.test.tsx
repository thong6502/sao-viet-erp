/** Menu trái: mỗi `id` chỉ được xuất hiện MỘT lần.
 *
 * Ngày 22/08/2026 mục "Khuôn" bị khai hai lần (`khuon-be`, cùng `module`) — React kêu
 * "two children with the same key" ở console và không ai để ý, vì màn hình vẫn vẽ ra.
 *
 * ⭐ Cái đắt hơn cảnh báo của React: `MODULE_BY_NAV_ID` / `MODULES_BY_NAV_ID` dựng bằng
 * `Object.fromEntries`, mà hàm đó **lấy dòng sau đè dòng trước, không báo gì**. Hai mục trùng id
 * nhưng khác `module` ⇒ mục hiện ra lại tra quyền của mục kia: hoặc chặn oan người có quyền,
 * hoặc mở cửa cho người không có. Lần này hai mục cùng `module` nên chỉ hỏng phần hiển thị —
 * lần sau thì chưa chắc.
 */
import { describe, expect, it } from "vitest";

import { MODULES_BY_NAV_ID, NAV } from "./Sidebar";

const trung = (xs: string[]) => [...new Set(xs.filter((x, i) => xs.indexOf(x) !== i))];

describe("Menu trái — id phải là duy nhất", () => {
  it("không mục nào trùng id với mục khác", () => {
    const ids = NAV.flatMap((s) => s.items.map((i) => i.id));
    expect(trung(ids)).toEqual([]);
  });

  it("không nhóm nào trùng id với nhóm khác", () => {
    expect(trung(NAV.map((s) => s.id))).toEqual([]);
  });

  it("menu con không trùng id với mục cha nào, cũng không trùng nhau", () => {
    // Cha và con nằm CHUNG một bảng tra quyền (`MODULES_BY_NAV_ID`), nên trùng ở đây cũng đè
    // nhau y hệt — dù React không kêu vì hai bên vẽ ở hai danh sách khác nhau.
    const ids = NAV.flatMap((s) =>
      s.items.flatMap((i) => [i.id, ...(i.children ?? []).map((c) => c.id)]),
    );
    expect(trung(ids)).toEqual([]);
  });

  it("bảng tra quyền không nuốt mất mục nào", () => {
    // Vế chốt: đếm đầu vào so với đầu ra. `Object.fromEntries` nuốt bao nhiêu dòng thì chênh
    // bấy nhiêu — kiểm thẳng hậu quả, không chỉ kiểm nguyên nhân.
    const soKhai = NAV.reduce(
      (n, s) => n + s.items.reduce((m, i) => m + 1 + (i.children?.length ?? 0), 0),
      0,
    );
    expect(Object.keys(MODULES_BY_NAV_ID)).toHaveLength(soKhai);
  });
});
