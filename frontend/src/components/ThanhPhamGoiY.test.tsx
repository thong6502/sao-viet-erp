// Ô TÊN SẢN PHẨM có gợi ý — mắt xích khép vòng chống trùng thành phẩm.
//
// Vì sao ô này quan trọng hơn vẻ ngoài của nó: tên gõ ở đây đi thẳng tới đích không biến dạng —
//
//     phiếu tính giá `.ten` → quote_items.product_name → order_lines.description
//
// …và `order_lines.description` là nửa sau của khoá gộp trùng `(khách, tên đã chuẩn hoá)`. Chọn
// lại đúng tên cũ ⇒ lúc chốt đơn dùng lại đúng dòng danh mục cũ, không đẻ dòng mới.
//
// Hai hàng rào phải giữ, và chúng KÉO NGƯỢC nhau:
//   · gõ tự do PHẢI được — sản phẩm mới thì chưa có gì để chọn (khác `MaterialCombobox`, ô đó ép
//     phải chọn theo luật kho 08/08/2026);
//   · chọn xong phải chép NGUYÊN VĂN — lệch một dấu là hết khớp khoá gộp.
import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThanhPhamGoiY } from "./ThanhPhamGoiY";

const TEN_CU = "Hộp thuốc 10 vỉ — in 2 màu, cán bóng";

function stub(items: unknown[] = []) {
  const goi: string[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    goi.push(String(url));
    return Promise.resolve({
      ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ items, total: items.length }),
      text: async () => JSON.stringify({ items, total: items.length }),
    } as Response);
  }));
  return goi;
}

const DONG = [
  { id: 7, ma: "TP-KH001-001", ten: TEN_CU, customer_ten: "Dược phẩm Sao Mai" },
];

/** Bọc component với state thật để soi được giá trị sau khi chọn.
 *  Nội dung gợi ý do `stub()` quyết định, không phải prop — nên component này không nhận gì. */
function Ve() {
  const [v, setV] = useState("");
  return <ThanhPhamGoiY token="t" value={v} onChange={setV} placeholder="VD Thân hộp / Ruột / Bìa" />;
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("Ô tên sản phẩm · gợi ý thành phẩm", () => {
  it("⭐ GÕ TỰ DO được — không ép chọn trong danh mục", async () => {
    // Sản phẩm lần đầu làm thì chưa có gì để chọn. Ép chọn ở đây là bắt chọn một thứ chưa tồn
    // tại — đúng cái sai đã phải gỡ ở màn Giao hàng (19/08/2026).
    stub([]);
    render(<Ve />);
    const o = screen.getByLabelText("Tên sản phẩm");
    await userEvent.type(o, "Món hoàn toàn mới");
    expect(o).toHaveValue("Món hoàn toàn mới");
  });

  it("⭐ chọn gợi ý ⇒ chép NGUYÊN VĂN tên trong danh mục", async () => {
    // Lệch một dấu gạch là lúc chốt đơn không khớp khoá gộp nữa ⇒ đẻ dòng thành phẩm thứ hai.
    stub(DONG);
    render(<Ve />);
    const o = screen.getByLabelText("Tên sản phẩm");
    await userEvent.type(o, "hộp thuốc");
    await userEvent.click(await screen.findByRole("option", { name: /Hộp thuốc 10 vỉ/ }));
    expect(o).toHaveValue(TEN_CU);
  });

  it("gợi ý KHÔNG hiện tên khách — chỉ là chọn lại một cái TÊN", async () => {
    // Đảo luật ngày 21/08/2026. Trước đó cố ý hiện tên khách để "nhận ra món này mình làm rồi";
    // chủ bỏ: "cái đó chỉ là có sản phẩm thôi, mình chỉ sử dụng lại tên đó thôi mà nên bỏ".
    // Giống bán cùng một cái quạt cho nhiều khách — tên khách không giúp gì cho việc chọn tên,
    // mà lại dính liền tên sản phẩm thành "Sản phẩm BCông ty Bánh…".
    stub(DONG);
    render(<Ve />);
    await userEvent.type(screen.getByLabelText("Tên sản phẩm"), "hộp");
    expect(await screen.findByText(TEN_CU)).toBeInTheDocument();
    expect(screen.queryByText("Dược phẩm Sao Mai")).not.toBeInTheDocument();
  });

  it("không có gợi ý nào ⇒ nói rõ CỨ GÕ TIẾP, không doạ người dùng", async () => {
    stub([]);
    render(<Ve />);
    await userEvent.type(screen.getByLabelText("Tên sản phẩm"), "abc");
    expect(await screen.findByText(/cứ gõ tên mới/i)).toBeInTheDocument();
  });

  it("chỉ mời dòng ĐANG DÙNG", async () => {
    // Mời dòng đã ngừng dùng là dẫn người ta gõ lại một cái tên vừa bị khai tử.
    const goi = stub(DONG);
    render(<Ve />);
    await userEvent.type(screen.getByLabelText("Tên sản phẩm"), "hộp");
    await waitFor(() => expect(goi.length).toBeGreaterThan(0));
    expect(goi.some((u) => u.includes("active=true"))).toBe(true);
    expect(goi.some((u) => u.includes("/api/vat-lieu-kho/thanh-pham"))).toBe(true);
  });
});
