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
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MODULES_BY_NAV_ID, NAV, Sidebar, type NavItem } from "./Sidebar";

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

/** Gập nhánh cây tổ: 11 tổ + 5 nhóm in đẩy menu dài quá màn hình, nên hàng CHA phải đóng/mở được
 *  con — mà bấm vào TÊN tổ cha thì vẫn mở bàn của chính tổ đó (nó là tổ thật, có việc, có badge). */
describe("Menu trái — gập nhánh tổ", () => {
  const TO: NavItem[] = [
    { id: "thuc-hien-sx:1", label: "Tổ in", icon: "users", module: "to_sx", indent: 0 },
    {
      id: "thuc-hien-sx:2", label: "Nhóm in máy 5 màu", icon: "users", module: "to_sx",
      indent: 1, parentId: "thuc-hien-sx:1",
    },
    {
      id: "thuc-hien-sx:3", label: "Ca đêm máy 5 màu", icon: "users", module: "to_sx",
      indent: 2, parentId: "thuc-hien-sx:2",
    },
    { id: "thuc-hien-sx:4", label: "Tổ bế", icon: "users", module: "to_sx", indent: 0 },
  ];

  function ve(activeId = "thuc-hien-sx:4", onSelect = () => {}) {
    return render(
      <Sidebar
        activeId={activeId}
        onSelect={onSelect}
        readable={new Set(["to_sx"])}
        dynamicItems={{ "san-xuat": TO }}
      />,
    );
  }

  beforeEach(() => localStorage.clear());

  it("gập cha là giấu cả nhánh cháu, mở lại thì hiện đủ", async () => {
    ve();
    expect(screen.getByRole("button", { name: "Nhóm in máy 5 màu" })).toBeInTheDocument();
    const nut = screen.getByRole("button", { name: "Thu gọn các tổ trong Tổ in" });

    await userEvent.click(nut);
    expect(screen.queryByRole("button", { name: "Nhóm in máy 5 màu" })).not.toBeInTheDocument();
    // Cháu (cấp 2) cũng phải biến mất, không chỉ con trực tiếp.
    expect(screen.queryByRole("button", { name: "Ca đêm máy 5 màu" })).not.toBeInTheDocument();
    // Tổ cha và tổ NGANG HÀNG vẫn còn — chỉ cắt đúng nhánh của nó.
    expect(screen.getByRole("button", { name: "Tổ in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tổ bế" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mở các tổ trong Tổ in" }));
    expect(screen.getByRole("button", { name: "Ca đêm máy 5 màu" })).toBeInTheDocument();
  });

  it("bấm TÊN tổ cha vẫn mở bàn của tổ đó, không phải gập nhánh", async () => {
    const chon = vi.fn();
    ve("thuc-hien-sx:4", chon);

    await userEvent.click(screen.getByRole("button", { name: "Tổ in" }));
    expect(chon).toHaveBeenCalledWith("thuc-hien-sx:1");
    expect(screen.getByRole("button", { name: "Nhóm in máy 5 màu" })).toBeInTheDocument();
  });

  it("nhớ nhánh đã gập qua lần vào sau", async () => {
    const man = ve();
    await userEvent.click(screen.getByRole("button", { name: "Thu gọn các tổ trong Tổ in" }));
    man.unmount();

    ve();
    expect(screen.queryByRole("button", { name: "Nhóm in máy 5 màu" })).not.toBeInTheDocument();
  });

  it("đi thẳng tới tổ nằm trong nhánh đang gập thì nhánh tự bung", async () => {
    const man = ve();
    await userEvent.click(screen.getByRole("button", { name: "Thu gọn các tổ trong Tổ in" }));
    man.unmount();

    ve("thuc-hien-sx:3");
    expect(screen.getByRole("button", { name: "Ca đêm máy 5 màu" })).toBeInTheDocument();
  });
});
