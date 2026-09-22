import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Guard cú pháp cho MỌI file CSS của frontend: số `{` phải khớp số `}`.
 *
 * Khuôn lỗi thật đã gặp (commit `7917b077`, 18/09/2026): gỡ mấy selector cuối danh sách của §22
 * trong `styles/responsive.css` thì gỡ luôn cả thân khai báo `{ font-size: 12px !important; }` và
 * dấu `}` đóng `@media`. Danh sách selector còn lại kết thúc bằng dấu PHẨY nên trình duyệt nuốt
 * luôn `@media` kế tiếp vào phần selector dở dang ⇒ 4.700 dòng cuối file (từ §22 tới §80) rơi hết
 * vào MỘT khối `@media screen and (max-width: 768px)` tự đóng ở EOF.
 *
 * Hậu quả không ai thấy ngay: Vite build sạch, `tsc` im, không test nào đỏ. Trên màn rộng chỉ lộ
 * đúng một chỗ — `.purchase__line-lb` (nhãn dành riêng cho điện thoại của lưới dòng hàng đơn mua)
 * mất `display: none` nên đổ ra desktop, ngăn kéo "Đơn mua hàng mới" hiện 22 con trong lưới 11
 * cột. Phần còn lại là nợ ẩn ở bản điện thoại/máy tính bảng: §22 + §23 chết hẳn, 9 khối
 * `max-width: 900/1024px` bị ép về ≤768px.
 *
 * Đếm ngoặc là đủ bắt đúng khuôn đó, và rẻ. Phải bỏ phần nằm trong chú thích và trong chuỗi trước khi
 * đếm: chú thích hay `content: "{"` đều có ngoặc mà không tính là khối.
 */

// `import.meta.url` dưới jsdom KHÔNG phải URL scheme `file:` (vitest nạp module qua transform
// riêng), `fileURLToPath` ném ngay lúc nạp file test. Lấy theo thư mục chạy vitest — gốc của nó
// là `frontend/` (xem `vite.config.ts`).
const THU_MUC_GOC = join(process.cwd(), "src");

function timFileCss(thuMuc: string): string[] {
  const ra: string[] = [];
  for (const muc of readdirSync(thuMuc, { withFileTypes: true })) {
    const duongDan = join(thuMuc, muc.name);
    if (muc.isDirectory()) ra.push(...timFileCss(duongDan));
    else if (muc.name.endsWith(".css")) ra.push(duongDan);
  }
  return ra;
}

/** Trả về `null` nếu cân bằng, ngược lại là câu mô tả chỗ lệch (kèm số dòng). */
function soatCanBang(nguon: string): string | null {
  let sau = 0;
  let dong = 1;
  let dongMoCuoi = 0;
  let i = 0;
  while (i < nguon.length) {
    if (nguon.startsWith("/*", i)) {
      const ket = nguon.indexOf("*/", i + 2);
      if (ket < 0) return `chú thích mở ở dòng ${dong} không được đóng`;
      dong += nguon.slice(i, ket + 2).split("\n").length - 1;
      i = ket + 2;
      continue;
    }
    const ky = nguon[i];
    if (ky === '"' || ky === "'") {
      // Chuỗi CSS không được xuống dòng (trừ khi thoát bằng `\`), nên gặp `\n` là coi như hết.
      let j = i + 1;
      while (j < nguon.length && nguon[j] !== ky && nguon[j] !== "\n") {
        j += nguon[j] === "\\" ? 2 : 1;
      }
      i = j + 1;
      continue;
    }
    if (ky === "\n") dong += 1;
    else if (ky === "{") {
      sau += 1;
      if (sau === 1) dongMoCuoi = dong;
    } else if (ky === "}") {
      sau -= 1;
      if (sau < 0) return `thừa một dấu } ở dòng ${dong}`;
    }
    i += 1;
  }
  if (sau > 0) {
    return `thiếu ${sau} dấu } — khối cấp cao nhất mở ở dòng ${dongMoCuoi} không bao giờ đóng`;
  }
  return null;
}

describe("cú pháp CSS", () => {
  const files = timFileCss(THU_MUC_GOC);

  it("quét được toàn bộ file CSS của frontend", () => {
    // Chốt chặn cho chính bài test này: đường dẫn sai thì `files` rỗng và mọi thứ dưới đây xanh
    // một cách vô nghĩa.
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(files.map((f) => relative(THU_MUC_GOC, f)))(
    "%s cân bằng { }",
    (tuongDoi) => {
      const loi = soatCanBang(
        readFileSync(join(THU_MUC_GOC, tuongDoi), "utf-8"),
      );
      expect(loi, `${tuongDoi}: ${loi}`).toBeNull();
    },
  );
});
