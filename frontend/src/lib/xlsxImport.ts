// Tiện ích dùng chung: tải mẫu + đọc file Excel dòng hàng (Mã/Tên vật tư + SL) và khớp vật tư.
// Dùng cho import Tồn kho (tồn đầu kỳ), Đề nghị, Phiếu từ đề nghị.
import * as XLSX from "xlsx";
import type { KhoMaterialOption } from "../api/client";

export interface ImportLine {
  code: string;
  name: string;
  qty: number;
  unit: string;
  unitCost: number | null;
  note: string;
}

export const LINE_HEADERS = ["Mã vật tư", "Tên vật tư", "Số lượng", "Đơn vị", "Nhà cung cấp", "Ghi chú"];
const LINE_HEADERS_PRICE = ["Mã vật tư", "Tên vật tư", "Số lượng", "Đơn vị", "Đơn giá", "Nhà cung cấp", "Ghi chú"];

/** Tải file mẫu .xlsx (header + vài dòng ví dụ). `withPrice` = có cột Đơn giá (cho phiếu nhập/xuất).
 * Cột "Nhà cung cấp" chỉ để tham chiếu khi điền — import không ghi đè NCC của vật tư. */
export function downloadLineTemplate(filename: string, opts?: { withPrice?: boolean }): void {
  const withPrice = !!opts?.withPrice;
  const headers = withPrice ? LINE_HEADERS_PRICE : LINE_HEADERS;
  const examples = withPrice
    ? [
        ["", "Giấy Couche 150gsm 65x86", 1000, "tờ", 2000, "Cty Giấy An Bình", "Ví dụ – có thể xóa dòng này"],
        ["GY002", "", 500, "tờ", 2500, "", "Điền Mã HOẶC Tên để khớp vật tư"],
      ]
    : [
        ["", "Giấy Couche 150gsm 65x86", 1000, "tờ", "Cty Giấy An Bình", "Ví dụ – có thể xóa dòng này"],
        ["GY002", "", 500, "tờ", "", "Điền Mã HOẶC Tên để khớp vật tư"],
      ];
  const ws = XLSX.utils.aoa_to_sheet([headers, ...examples]);
  ws["!cols"] = headers.map((h) => ({ wch: h.length + (h === "Tên vật tư" ? 18 : 6) }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "DongHang");
  XLSX.writeFile(wb, filename);
}

/** Xuất bảng ra file .xlsx: header + các dòng. Tự canh độ rộng cột. */
export function exportXlsx(
  filename: string,
  headers: string[],
  rows: (string | number | null)[][],
  sheetName = "Data",
): void {
  const aoa: (string | number | null)[][] = [headers, ...rows];
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  ws["!cols"] = headers.map((h, c) => {
    let w = h.length;
    for (const r of rows) w = Math.max(w, String(r[c] ?? "").length);
    return { wch: Math.min(42, w + 3) };
  });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheetName);
  XLSX.writeFile(wb, filename);
}

/** Đọc file .xlsx/.xls/.csv → danh sách dòng hàng (đúng mã hóa, ô số đọc đúng). */
export async function parseLineFile(file: File): Promise<ImportLine[]> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const ws = wb.Sheets[wb.SheetNames[0]];
  const raw = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, blankrows: false, defval: "" });
  const rows = raw
    .map((r) => (Array.isArray(r) ? r.map((c) => (c == null ? "" : String(c))) : []))
    .filter((r) => r.some((c) => c.trim()));
  if (rows.length < 2) return [];
  const header = rows[0].map((h) => h.trim().toLowerCase());
  const idx = (names: string[]) => header.findIndex((h) => names.includes(h));
  const iCode = idx(["mã vật tư", "mã", "ma vat tu", "ma", "code"]);
  const iName = idx(["tên vật tư", "tên", "ten vat tu", "ten", "name"]);
  const iQty = idx(["số lượng", "so luong", "sl", "qty", "quantity"]);
  const iUnit = idx(["đơn vị", "don vi", "đvt", "dvt", "unit"]);
  const iCost = idx(["đơn giá", "don gia", "gia", "unit_cost", "price"]);
  const iNote = idx(["ghi chú", "ghi chu", "note"]);
  const cell = (r: string[], i: number) => (i >= 0 ? (r[i] ?? "").trim() : "");
  const numOf = (s: string): number | null => {
    const v = s.replace(/[.,](?=\d{3}\b)/g, "").replace(",", ".");
    const n = Number(v);
    return s !== "" && !Number.isNaN(n) ? n : null;
  };
  const out: ImportLine[] = [];
  for (let r = 1; r < rows.length; r++) {
    const cells = rows[r];
    const code = cell(cells, iCode);
    const name = cell(cells, iName);
    if (!code && !name) continue;
    out.push({
      code, name,
      qty: numOf(cell(cells, iQty)) ?? 0,
      unit: cell(cells, iUnit),
      unitCost: numOf(cell(cells, iCost)),
      note: cell(cells, iNote),
    });
  }
  return out;
}

/** Khớp 1 dòng Excel với vật tư đã có trong kho: ưu tiên đúng Mã, rồi đúng Tên, rồi Tên chứa nhau. */
export function matchMaterial(materials: KhoMaterialOption[], code: string, name: string): KhoMaterialOption | null {
  const c = code.trim().toLowerCase();
  const n = name.trim().toLowerCase();
  if (c) {
    const m = materials.find((x) => x.code.toLowerCase() === c);
    if (m) return m;
  }
  if (n) {
    const exact = materials.find((x) => x.name.toLowerCase() === n);
    if (exact) return exact;
    const partial = materials.find((x) => x.name.toLowerCase().includes(n) || n.includes(x.name.toLowerCase()));
    if (partial) return partial;
  }
  return null;
}
