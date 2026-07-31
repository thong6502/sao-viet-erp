// Chuyển tài liệu Word (.docx) sang HTML **giàu định dạng** cho màn Nội quy.
//
// ⚠️ FILE NÀY CỐ Ý ĐỨNG RIÊNG ĐỂ NẠP MUỘN — đừng gộp ngược vào `NoiQuyPage.tsx`.
// Màn nội quy là màn CẢ CÔNG TY mở, nhưng chỉ Giám đốc tải tài liệu lên. Để `docx-preview` nằm
// trong gói chính là mỗi công nhân tải thêm một thư viện dựng file Word họ không bao giờ chạm
// tới — trên điện thoại mạng yếu ngoài xưởng thì đó là thêm giây trắng màn.
// `NoiQuyPage` gọi hàm dưới đây bằng `await import()` ngay tại chỗ dùng, và bản thân
// `docx-preview` lại được `import()` lần nữa bên trong `docxToRichHtml` ⇒ hai tầng nạp muộn.
//
// ⇒ ĐỪNG import gì từ file này bằng `import` TĨNH ở bất kỳ đâu: một chỗ thôi là chunk bị kéo
// thẳng vào gói chính và toàn bộ lợi ích ở trên biến mất mà không ai thấy.
//
// (Trình soạn thảo TipTap + đường "tách chữ" bằng mammoth đã GỠ HẲN — chủ chốt 30/07/2026:
// màn này CHỈ tải file lên. Đừng dựng lại.)

export interface ConvertResult {
  html: string;
  /** Chỉ CẢNH BÁO KỸ THUẬT của riêng lần chuyển đổi này (ảnh bị bỏ…). Lời khuyên chung về độ
   *  trung thực do `NoiQuyPage` viết — nó mới biết người dùng vừa chọn đường nào. */
  warnings: string[];
  /** `true` = tài liệu CÓ dùng số thứ tự tự động của Word và số đó KHÔNG mang theo được.
   *  Tách khỏi `warnings` vì chỗ gọi phải nâng nó lên banner cảnh báo không tự tắt, chứ không
   *  trộn vào một câu thông báo chung rồi trôi qua. */
  matSoTuDong: boolean;
}

// Phải khớp ĐÚNG bộ lọc của server (`_STYLE_TAGS` + `_CSS_CHO_PHEP` trong
// `services/noi_quy_service.py`). Sinh ra thứ server sẽ vứt là tệ hơn cả không sinh: chủ thấy bản
// xem trước đẹp, lưu xong mới phát hiện mất một nửa định dạng, và không hiểu tại sao.
const STYLE_TAGS = new Set([
  "P", "DIV", "SPAN", "TD", "TH", "TABLE", "TR",
  "H1", "H2", "H3", "H4", "LI", "UL", "OL", "BLOCKQUOTE",
]);

/** CSS **thừa hưởng**: chỉ ghi ra khi KHÁC cha. Bằng cha thì bỏ — nó tự thừa hưởng, ghi lại chỉ
 *  phình HTML (tài liệu 40 trang có hàng nghìn thẻ). */
const CSS_INHERITED = [
  "color", "font-family", "font-size", "font-style", "font-weight",
  "line-height", "text-align", "text-indent", "text-transform",
];

/** CSS **không thừa hưởng**: so với cha là vô nghĩa (con luôn về mặc định của nó), nên so với
 *  GIÁ TRỊ MẶC ĐỊNH. Bằng mặc định thì bỏ — bỏ đi vẫn ra đúng kết quả đó. */
const CSS_OWN: { prop: string; skip: string[] }[] = [
  { prop: "background-color", skip: ["rgba(0, 0, 0, 0)", "transparent"] },
  { prop: "margin-left", skip: ["0px"] },
  { prop: "padding-left", skip: ["0px"] },
  { prop: "vertical-align", skip: ["baseline"] },
];

/** Ép định dạng của docx-preview thành `style` NỘI TUYẾN trên từng thẻ.
 *
 *  Vì sao bắt buộc phải làm: docx-preview đặt phần lớn định dạng qua **LỚP CSS** trong một
 *  `<style>` nó tự chèn. Lấy `innerHTML` rồi làm sạch là bảng CSS đó biến mất ⇒ tiêu đề, canh
 *  giữa, thụt lề, cỡ chữ mất sạch, chỉ còn chữ trơn. Mà `<style>` thì không tầng nào cho qua
 *  (đúng: một bảng CSS lạ chạy trên màn CẢ CÔNG TY mở là chuyện khác hẳn).
 *  ⇒ Đọc giá trị đã TÍNH XONG của trình duyệt rồi viết thẳng vào từng thẻ. Đây là lý do cây phải
 *  được gắn thật vào trang trước khi gọi: `getComputedStyle` không chạy trên cây rời.
 *
 *  `parent` = style đã tính của thẻ cha, dùng để bỏ những khai báo trùng (xem `CSS_INHERITED`).
 *  An toàn khi vừa đọc vừa ghi: giá trị ghi vào bằng ĐÚNG giá trị đang tính, nên con cháu tính ra
 *  vẫn y như cũ. */
function flattenStyles(el: Element, parent: CSSStyleDeclaration): void {
  const cs = getComputedStyle(el);
  const html = el as HTMLElement;

  if (STYLE_TAGS.has(el.tagName)) {
    const decls: string[] = [];
    for (const prop of CSS_INHERITED) {
      const v = cs.getPropertyValue(prop);
      if (v && v !== parent.getPropertyValue(prop)) decls.push(`${prop}: ${v}`);
    }
    for (const { prop, skip } of CSS_OWN) {
      const v = cs.getPropertyValue(prop);
      if (v && !skip.includes(v)) decls.push(`${prop}: ${v}`);
    }
    // `text-decoration` đã tính trả về cả 3 phần ("none solid rgb(0,0,0)") — chỉ lấy phần gạch.
    const line = cs.getPropertyValue("text-decoration-line");
    if (line && line !== "none") decls.push(`text-decoration: ${line}`);
    // `width` CHỈ lấy cho bảng: giá trị đã tính của mọi thẻ khác luôn là một số px cụ thể, ghi ra
    // là khoá cứng bề rộng từng đoạn văn theo màn hình của người TẢI LÊN. Với bảng thì ngược lại,
    // bề rộng cột là phần dáng người ta thật sự muốn giữ.
    if (el.tagName === "TABLE" || el.tagName === "TD" || el.tagName === "TH") {
      const w = cs.getPropertyValue("width");
      if (w && w !== "auto") decls.push(`width: ${w}`);
    }
    if (decls.length) html.setAttribute("style", decls.join("; "));
    else html.removeAttribute("style");
  } else if (el.tagName === "IMG") {
    // Thẻ `img` không được mang `style`, nhưng `width`/`height` là THUỘC TÍNH và được cho qua —
    // giữ lại để ảnh chữ ký/logo không phình về kích thước gốc.
    html.removeAttribute("style");
    const w = Math.round(parseFloat(cs.width));
    const h = Math.round(parseFloat(cs.height));
    if (w > 0 && h > 0) {
      html.setAttribute("width", String(w));
      html.setAttribute("height", String(h));
    }
  } else {
    html.removeAttribute("style");
  }
  // Bỏ `class` sau khi đã ép style: để lại thì tên lớp của docx-preview trỏ vào bảng CSS không
  // còn tồn tại — rác vô ích trong nội dung mọi nhân viên tải về.
  html.removeAttribute("class");

  for (const child of Array.from(el.children)) flattenStyles(child, cs);
}

/** Có thẻ nào dựa vào `::before`/`::after` để hiện chữ không (docx-preview đánh số danh sách Word
 *  bằng CSS counter).
 *
 *  Vì sao phải dò thay vì cứ cảnh báo chung: nội quy gần như toàn bộ là điều khoản có số, mà mất
 *  số thì văn bản HỎNG trong khi nhìn vẫn tưởng đủ. Dò được thì nói mạnh hơn, đúng chỗ.
 *  Chữ sinh bằng CSS thì KHÔNG có cách nào mang theo: trình duyệt không trả về số đã tính của
 *  counter, chỉ trả về nguyên biểu thức `counter(...)`. Đừng "sửa" hàm này để cố lấy số. */
function coChuSinhBangCss(root: Element): boolean {
  for (const el of Array.from(root.querySelectorAll("*"))) {
    for (const pseudo of ["::before", "::after"]) {
      const c = getComputedStyle(el, pseudo).content;
      if (c && c !== "none" && c !== "normal" && c !== '""' && c !== "''") return true;
    }
  }
  return false;
}

/** Word → HTML **giàu định dạng**: giữ canh lề, cỡ chữ, font, màu, thụt lề, bề rộng cột bảng.
 *
 *  Chỉ đạt ~90% bản gốc (xem `coChuSinhBangCss`, và Word còn nhiều thứ HTML không có: khung
 *  text box, tab stop, ngắt trang). Muốn 100% thì xuất PDF rồi dùng `api.noiQuy.banGocPdf` — chỗ
 *  gọi phải nói câu đó ra, đừng để chủ tưởng phần lệch là lỗi. */
export async function docxToRichHtml(
  file: File,
  uploadImage: (file: File) => Promise<string>,
): Promise<ConvertResult> {
  const { renderAsync } = await import("docx-preview");
  const warnings: string[] = [];

  // Khay dựng ẩn nhưng PHẢI nằm trong trang thật (xem `flattenStyles`). Đẩy ra ngoài khung nhìn
  // chứ KHÔNG `display: none`: thẻ ẩn kiểu đó không có giá trị style nào để đọc.
  const host = document.createElement("div");
  host.setAttribute("aria-hidden", "true");
  host.style.cssText = "position:fixed; left:-10000px; top:0; width:820px;";
  // ~820px ≈ khổ A4 trừ lề: để bề rộng cột bảng tính ra con số hợp lý, không phải theo màn hình.
  // Màu chữ lấy theo màu chữ của app, để đoạn văn KHÔNG đổi màu không sinh ra khai báo `color`
  // nào — đỡ vài chục KB và giữ nội quy hoà vào giao diện.
  host.style.color = getComputedStyle(document.body).color;
  document.body.appendChild(host);

  try {
    const styleBox = document.createElement("div");
    const bodyBox = document.createElement("div");
    host.append(styleBox, bodyBox);

    await renderAsync(await file.arrayBuffer(), bodyBox, styleBox, {
      inWrapper: false,     // bỏ khung "tờ giấy" của docx-preview — nội quy hiện trong khung app
      breakPages: false,    // ngắt trang theo khổ giấy là vô nghĩa khi cuộn trên web
      ignoreWidth: true,    // đừng ép bề rộng khổ A4 vào màn hình điện thoại
      ignoreHeight: true,
      ignoreFonts: true,    // font nhúng trong .docx không mang theo được (cần `@font-face`)
      renderHeaders: false, // đầu/chân trang Word là số trang, không phải nội dung nội quy
      renderFooters: false,
      renderComments: false,
      renderChanges: false, // vết sửa "track changes" không phải nội quy đã chốt
    });

    // Phải dò TRƯỚC `flattenStyles` — hàm đó bỏ `class`, mà lớp CSS chính là chỗ neo `::before`.
    const matSoTuDong = coChuSinhBangCss(bodyBox);

    // Ảnh phải TẢI LÊN kho file: bộ lọc chỉ cho `<img src>` trỏ vào `/api/files/`, nên `blob:`
    // của docx-preview sẽ bị bỏ. Làm tuần tự cho dễ đọc — tài liệu nội quy chỉ vài ảnh.
    const imgs = Array.from(bodyBox.querySelectorAll("img"));
    let imageNo = 0;
    let boQua = 0;
    for (const img of imgs) {
      try {
        const blob = await (await fetch(img.src)).blob();
        const ext = blob.type === "image/png" ? "png" : blob.type === "image/jpeg" ? "jpg" : null;
        if (!ext) throw new Error(`định dạng ${blob.type || "không rõ"}`);
        imageNo += 1;
        img.src = await uploadImage(
          new File([blob], `anh-noi-quy-${imageNo}.${ext}`, { type: blob.type }),
        );
      } catch {
        // Một ảnh lỗi KHÔNG được kéo đổ cả bản chuyển đổi — bỏ đúng ảnh đó rồi đếm lại.
        img.remove();
        boQua += 1;
      }
    }
    if (boQua > 0) {
      warnings.push(
        `${boQua} ảnh trong file Word không đưa lên được (chỉ nhận JPG/PNG) nên đã bị bỏ.`,
      );
    }

    flattenStyles(bodyBox, getComputedStyle(host));
    return { html: bodyBox.innerHTML, warnings, matSoTuDong };
  } finally {
    host.remove();
  }
}
