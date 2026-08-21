/** Gác hai bệnh CSS đã dính thật, cả hai đều HỎNG TRONG IM LẶNG.
 *
 *  1. CƯỚP SELECTOR. CSS ở repo này là global và `AppShell` import tĩnh mọi trang, nên file nạp
 *     sau thắng file nạp trước trên MỌI màn. `kho-request.css` khai lại một loạt selector `rc-*`
 *     của `rebuild-catalog.css` và thắng suốt nhiều tháng — màn vẫn "chạy", chỉ là chạy bằng
 *     style của màn khác. Không ai thấy vì không có gì báo.
 *
 *  2. KHAI HAI LẦN TRONG CÙNG MỘT FILE. Bản sau chỉ đè những thuộc tính nó có; phần còn lại của
 *     bản trước vẫn ăn. Kết quả là một style lai mà không dòng nào trong file mô tả đúng — đúng
 *     cái bẫy đã làm mất cả buổi khi sửa CSS "không ăn".
 *
 *  Đọc file bằng `node:fs`, không render gì — nhanh và không phụ thuộc jsdom.
 */
import { describe, expect, it } from "vitest";

// Đọc bằng `import.meta.glob` của Vite chứ không `node:fs`: app frontend không khai `@types/node`
// nên `tsc --noEmit` đỏ ngay, mà thêm cả bộ type Node chỉ để một test đọc file là đắt hơn thứ nó
// mua. `?raw` trả nguyên văn nội dung, `eager` để có sẵn lúc chạy test.
const CSS = import.meta.glob("./*.css", { query: "?raw", import: "default", eager: true }) as
  Record<string, string>;
const CHU = "./rebuild-catalog.css";

/** Số selector mở đầu bằng `.rc-` / `.rc__` mà mỗi file KHÁC đang khai.
 *  Đây là NỢ ĐÃ BIẾT: con số chỉ được CO LẠI, không được phình ra. */
/* ⚠️ BA CON SỐ NÀY LÀ SỐ ĐO THẬT, đo lại 16/08/2026 — trước đó chúng SAI CẢ BA.
 *
 * Lý do: `import.meta.glob(..., "?raw")` dưới Vitest trả về CHUỖI RỖNG cho mọi file CSS, vì mặc
 * định `test.css = false` khiến CSS không được xử lý. Cả lưới gác này đọc rỗng ⇒ mọi khẳng định
 * đúng một cách vô nghĩa, và nó xanh suốt từ lúc viết. Đã bật `css: true` trong `vite.config.ts`.
 *
 * Bài học đắt hơn con số: một guard XANH chưa chứng minh gì nếu chưa có lần nào thấy nó ĐỎ. */
const NO_DA_BIET: Record<string, number> = {
  // 28→31 khi GỘP hai nhánh (20/08/2026): nhánh SX có nhóm scrim · drawer · sec__title · code-badge …
  // (đã giành lại bằng .rc--dm), nhánh HR/kho thêm bảng Báo cáo kho tái dùng .rc__table (.rc__table--fixed,
  // .rc__filler, .rc__muted, .rc__link-btn, .rc__tabn …). Không có selector nào TRÙNG — là hợp nhất thật của
  // hai bộ nợ đã-được-ghi-nhận riêng, không phải rò mới. Vẫn chỉ được CO LẠI từ đây.
  // 31→37 khi dựng lại màn Kho tồn/Phiếu (21/08/2026). Đã TRỪ trước hai chỗ KHAI TRÙNG trong
  // chính kho-request.css (`.rc-sec__title` và `.kho-lines .rc-input` mỗi cái hai bản, đang chạy
  // bằng style lai) — gộp xong mới đếm. Sáu cái còn lại:
  //   · 5 cái nằm trong khung riêng của màn kho, KHÔNG chạm tới màn Cấu hình danh mục được:
  //     .kho-lines .rc-input{:hover,:focus,[type=date]} · .kho-info-item .rc-input[type=date] ·
  //     .kho-table-card .rc__table  (+3 .kho-voucher-info-grid > .rc-field* chỉ là đổi tên của
  //     3 .kho-info-grid > .rc-field* cũ, và .rc-drawer--wide bị bỏ ⇒ phần này bù trừ nhau).
  //   · 1 cái là NỢ THẬT: `.rc-drawer__kicker` khai toàn cục, tô thẳng đầu drawer của danh mục.
  //     Nó nhập vào đúng khối .rc-drawer / .rc-drawer__head / .rc-drawer__scrim đã nằm trong nợ
  //     từ trước, nên chưa gỡ riêng được — gỡ thì gỡ cả khối, ghi lại đây để không quên.
  // Vẫn chỉ được CO LẠI từ đây.
  "./kho-request.css": 37,
  // .rc-drawer__kicker trong .khvt-drawer__head (màn Kế hoạch vật tư tái dùng đầu drawer của rc, có chủ đích).
  "./ke-hoach-sx.css": 1,
  "./ky-thuat-may.css": 1,  // .rc__tab.is-qua-han — hex cứng thay token
  "./tinh-gia.css": 19,     // .rc-drawer--wide + bộ .rc-modal__* của màn Tính giá
};

function docCss(ten: string): string {
  return CSS[ten] ?? "";
}

/** Selector đang tô MỘT PHẦN TỬ `rc-*`.
 *
 *  Đếm theo phần tử BỊ TÔ (token cuối), không theo token đầu. `.rc-modal__right-col .tg-sheetrow`
 *  tô một phần tử `tg-*` nằm trong khung của chính màn đó — nó không thể chạm tới màn Cấu hình
 *  danh mục, nên tính vào nợ là kêu oan. Còn `.kho-request .rc-drawer__scrim` thì tô THẲNG một
 *  phần tử của danh mục ⇒ đúng thứ guard này sinh ra để bắt. */
function selectorRc(css: string): string[] {
  return css
    .split("\n")
    .map((d) => d.trim())
    .filter((d) => d.endsWith("{") && !d.startsWith("@") && !d.startsWith("/"))
    .map((d) => d.replace(/\s*\{$/, ""))
    .filter((sel) =>
      sel.split(",").some((phan) => {
        const cuoi = phan.trim().split(/\s+|>/).filter(Boolean).pop() ?? "";
        return /^\.rc[-_]/.test(cuoi);
      }),
    );
}

describe("CSS danh mục không bị file khác cướp selector", () => {
  const files = Object.keys(CSS).filter((f) => f !== CHU);

  it.each(files)("%s không thêm selector rc-* mới", (ten: string) => {
    const n = selectorRc(docCss(ten)).length;
    const tran = NO_DA_BIET[ten] ?? 0;
    expect(
      n,
      `${ten} khai ${n} selector "rc-*" (nợ đã biết: ${tran}).\n` +
        `CSS là global — thêm một cái nữa là đè lên màn Cấu hình danh mục trên MỌI màn hình.\n` +
        `Muốn style riêng thì dùng tiền tố của chính màn đó, đừng mượn họ "rc".`,
    ).toBeLessThanOrEqual(tran);
  });
});

/** Các luật trong mọi khối `@media print` của một file: `{ sel, khai }`.
 *
 *  Cắt thô bằng regex chứ không dựng parser CSS: đủ cho việc soi một mẫu selector, và không kéo
 *  thêm phụ thuộc chỉ để chạy một test. */
function luatTrongMediaPrint(css: string): { sel: string; khai: string }[] {
  const ra: { sel: string; khai: string }[] = [];
  const khoi = css.matchAll(/@media[^{]*\bprint\b[^{]*\{/g);
  for (const m of khoi) {
    // Cắt đúng thân khối bằng cách đếm ngoặc từ vị trí mở.
    let i = (m.index ?? 0) + m[0].length;
    let sau = 1;
    const dau = i;
    while (i < css.length && sau > 0) {
      if (css[i] === "{") sau++;
      else if (css[i] === "}") sau--;
      i++;
    }
    const than = css.slice(dau, i - 1).replace(/\/\*[\s\S]*?\*\//g, "");
    for (const r of than.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      ra.push({ sel: r[1].trim().replace(/\s+/g, " "), khai: r[2] });
    }
  }
  return ra;
}

/** Luật này có ẨN thứ gì đi không (chứ không phải chỉ nới overflow/height)? */
function laLuatAn(khai: string): boolean {
  return /(^|;)\s*(display\s*:\s*none|visibility\s*:\s*hidden)/i.test(khai);
}

describe("@media print không được ẩn toàn cục", () => {
  /** Đã dính HAI LẦN, cả hai đều làm bản in của MÀN KHÁC ra trắng tinh:
   *
   *   · `luong.css` — `body * { visibility: hidden }` trần. Comment tại chỗ ghi rõ hậu quả:
   *     "ẩn sạch bản in của MỌI màn khác (vd Phiếu tính giá bị trắng)". Đã sửa bằng `body:has(…)`.
   *   · `ky-thuat-may.css` — viết lại y hệt cái bẫy đó, phát hiện 16/08/2026 khi Phiếu tính giá
   *     in ra 2 trang trắng.
   *
   *  CSS ở repo này là global và `AppShell` import tĩnh mọi trang, nên một dòng `body *` trong
   *  `@media print` của MỘT màn sẽ ăn vào bản in của TẤT CẢ màn. Hỏng câm: không lỗi, không cảnh
   *  báo, chỉ là giấy trắng — mà thường tới tay khách rồi mới có người kêu.
   *
   *  Luật: mọi selector nhắm `body`/`html`/`*` trong `@media print` phải khoá phạm vi bằng
   *  `:has(...)` của chính màn đó. Bốn màn in hiện có đều làm vậy: `.qpdf` · `.tg-page` ·
   *  `.lg-payslip-print` · `.ktm-drawer`.
   */
  const files = Object.keys(CSS);

  it.each(files)("%s: luật print ẩn-toàn-cục phải khoá màn", (ten: string) => {
    // CHỈ soi luật có ẩn thật (`display:none` / `visibility:hidden`). Luật chỉ nới `overflow` hay
    // `height` cho `html, body` là VÔ HẠI và cần cho mọi màn in — `tinh-gia.css` cố ý làm thế, kèm
    // ghi chú "không dùng :has vì vài trình duyệt bỏ qua :has trong media print". Bắt cả nhóm đó
    // là guard kêu oan, mà guard kêu oan thì sớm muộn bị tắt.
    const xau = luatTrongMediaPrint(docCss(ten))
      .filter(({ sel, khai }) => laLuatAn(khai) && !sel.includes(":has("))
      .map(({ sel }) => sel)
      .filter((sel) => sel.split(",").some((s) => /^\s*(html|body|\*)(\s|\*|$)/.test(s)));
    expect(
      xau,
      `${ten} có luật print ẨN toàn cục mà không khoá màn: ${JSON.stringify(xau)}\n` +
        "CSS là global ⇒ nó ăn vào bản in của MỌI màn khác, và hậu quả là GIẤY TRẮNG.\n" +
        "Khoá lại bằng `body:has(<class riêng của màn>) …`, xem 4 màn in hiện có.",
    ).toEqual([]);
  });

  it("bản in Kỹ thuật máy vẫn còn luật hiện drawer của nó", () => {
    // Khoá phạm vi mà lỡ tay khoá luôn cả phần hiện drawer thì màn KTM in ra trắng — đổi bệnh
    // chứ không chữa bệnh. Giữ một mốc để chắc phần "cho hiện" còn nguyên.
    const luat = luatTrongMediaPrint(docCss("./ky-thuat-may.css"));
    expect(luat.length, "khối @media print của KTM biến mất").toBeGreaterThan(0);
    expect(
      luat.some((l) => l.sel.includes(".ktm-drawer") && l.sel.includes(":has(")),
      "KTM phải khoá phạm vi bằng :has(.ktm-drawer)",
    ).toBe(true);
    expect(
      luat.some((l) => l.sel.includes(".rc-drawer__scrim") && /visibility\s*:\s*visible/i.test(l.khai)),
      "KTM phải còn luật CHO HIỆN drawer, không thì chính nó in ra trắng",
    ).toBe(true);
  });
});

describe("rebuild-catalog.css không khai trùng selector", () => {
  it("mỗi selector chỉ xuất hiện một lần", () => {
    const dem = new Map<string, number>();
    let sau = 0;                       // độ sâu ngoặc — chỉ xét selector ở CẤP NGOÀI CÙNG
    for (const d of docCss(CHU).split("\n")) {
      const s = d.trim();
      const mo = (s.match(/\{/g) ?? []).length;
      const dong = (s.match(/\}/g) ?? []).length;
      // Selector lặp lại BÊN TRONG `@media` là override responsive HỢP LỆ, không phải khai trùng
      // — đếm cả chúng là guard kêu oan, mà guard kêu oan thì sớm muộn bị tắt.
      if (sau === 0 && s.endsWith("{") && !s.startsWith("@") && !s.startsWith("/")) {
        const sel = s.replace(/\s*\{$/, "");
        if (sel && !sel.includes(":root")) dem.set(sel, (dem.get(sel) ?? 0) + 1);
      }
      sau += mo - dong;
      if (sau < 0) sau = 0;
    }
    const trung = [...dem].filter(([, n]) => n > 1).map(([s]) => s);
    expect(
      trung,
      "Selector khai hai lần: bản sau chỉ đè thuộc tính nó có, phần còn lại của bản trước VẪN ăn.\n" +
        "Sửa bằng cách GỘP thành một khối, đừng thêm khối thứ ba.",
    ).toEqual([]);
  });
});
