// Hàm dùng chung của màn Yêu cầu mua hàng (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseRequestInput,
  DepartmentPurchaseRequestLineInput,
  DepartmentPurchaseRequestLineOut,
  DepartmentPurchaseRequestRow,
  DepartmentPurchaseSourceType,
} from "../../../../api/client";

export function emptyLine(): DepartmentPurchaseRequestLineInput {
  return {
    item_name: "",
    unit: "",
    quantity: 0,
    note: "",
  };
}

export function emptyRequest(
  sourceType: DepartmentPurchaseSourceType | null = null,
): DepartmentPurchaseRequestInput {
  return {
    source_type: sourceType,
    related_document_type: null,
    related_document_code: null,
    content: "",
    needed_date: "",
    note: null,
    lines: [emptyLine()],
  };
}

/** Nội dung để HIỆN. Phiếu lập trước 07/08/2026 chưa có ô gộp ⇒ nối lại hai ô cũ. */
export function noiDungCu(purpose: string | null, note: string | null): string {
  return [purpose, note].map((x) => (x ?? "").trim()).filter(Boolean).join(" — ");
}

export function noiDung(row: DepartmentPurchaseRequestRow): string {
  return row.content?.trim() || noiDungCu(row.purpose, row.note);
}

/** Món CÒN SỐNG trong yêu cầu. Món bị bỏ vẫn được máy chủ trả về (kèm ai bỏ · lúc nào · vì sao)
 *  để còn tra lại, nên mọi chỗ đếm/xem-trước phải lọc, không thì con số phồng lên vô nghĩa. */
export function dongSong(
  row: DepartmentPurchaseRequestRow,
): DepartmentPurchaseRequestLineOut[] {
  return row.lines.filter((line) => !line.cancelled_at);
}

export function todayInputValue(): string {
  const now = new Date();
  const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localNow.toISOString().slice(0, 10);
}

/** Chuẩn hoá phiếu trước khi gửi máy chủ (nguyên văn từ file gốc, chỉ bỏ 2 dấu cách thụt đầu
 *  dòng do được nâng từ trong component ra ngoài module). */
export function cleanRequest(
  input: DepartmentPurchaseRequestInput,
): DepartmentPurchaseRequestInput {
  const trimOptional = (v?: string | null) => {
    const s = (v ?? "").trim();
    return s || null;
  };
  return {
    source_type: input.source_type ?? null,
    // GIỮ vết chứng từ nguồn thay vì xoá trắng (20/08/2026). Trước đây hai ô này luôn bị nullhoá
    // vì form gõ tay không có chỗ nhập chúng — nhưng nó cũng xoá luôn vết của phiếu ĐI TỪ màn
    // khác sang (Kế hoạch vật tư gửi mã lệnh), và xoá cả lúc SỬA một phiếu vốn đã có vết. Người
    // mua mở phiếu ra không còn biết mua cho lệnh nào; `openEdit` nạp vào rồi lưu là mất.
    related_document_type: trimOptional(input.related_document_type),
    related_document_code: trimOptional(input.related_document_code),
    content: (input.content ?? "").trim(),
    needed_date: (input.needed_date ?? "").trim(),
    note: null,
    lines: input.lines.map((line) => ({
      // Cặp mặt hàng gốc đi kèm: phiếu mua sinh sau đó nối thẳng về đúng món, không ghép bằng tên.
      hang_loai: line.hang_loai ?? null,
      hang_id: line.hang_id ?? null,
      item_name: (line.item_name ?? "").trim(),
      unit: (line.unit ?? "").trim(),
      quantity: Number(line.quantity),
      note: trimOptional(line.note),
    })),
  };
}
