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
  group: string;    // "Nhóm phiếu" — dòng cùng nhóm gộp vào 1 phiếu/đề nghị
  typeText: string; // "Loại phiếu" — mã/tên loại phiếu (để trống = dùng loại mặc định ở hộp thoại)
  partner: string;  // "Đối tượng" — NCC / khách / bộ phận của phiếu
}

export const LINE_HEADERS = ["Mã vật tư", "Tên vật tư", "Số lượng", "Đơn vị", "Nhà cung cấp", "Ghi chú"];

/** Tải file mẫu .xlsx (header + vài dòng ví dụ).
 *  `withPrice` = có cột Đơn giá (phiếu nhập mua). `withGroups` = có cột Loại phiếu + Nhóm phiếu + Đối tượng
 *  (1 file tạo nhiều phiếu; dòng cùng "Nhóm phiếu" gộp thành 1 phiếu).
 *  `types` = danh sách loại phiếu → kèm sheet tra cứu "LoaiPhieu" để user biết mã điền. */
export function downloadLineTemplate(
  filename: string,
  opts?: { withPrice?: boolean; withGroups?: boolean; types?: { code: string; name: string; group: string }[] },
): void {
  const withPrice = !!opts?.withPrice;
  const withGroups = !!opts?.withGroups;
  const headers = [
    ...(withGroups ? ["Loại phiếu", "Nhóm phiếu"] : []),
    "Mã vật tư", "Tên vật tư", "Số lượng", "Đơn vị",
    ...(withPrice ? ["Đơn giá"] : []),
    withGroups ? "Đối tượng" : "Nhà cung cấp", "Ghi chú",
  ];
  const row = (
    type: string, grp: string, code: string, name: string, qty: number, unit: string,
    price: number, partner: string, note: string,
  ) => [
    ...(withGroups ? [type, grp] : []),
    code, name, qty, unit, ...(withPrice ? [price] : []), partner, note,
  ];
  const examples = withGroups
    ? [
        row("NK-GK", "1", "", "Giấy Couche 150gsm 65x86", 1000, "tờ", 2000, "Khách A", "Phiếu 1 · sản phẩm 1"),
        row("NK-GK", "1", "GY002", "", 500, "tờ", 2500, "Khách A", "Phiếu 1 · sản phẩm 2 (cùng Nhóm 1 → chung 1 phiếu)"),
        row("NK-NVL", "2", "VT001", "", 50, "kg", 8000, "Cty ABC", "Phiếu 2 · Nhóm khác → phiếu riêng"),
      ]
    : [
        row("", "", "", "Giấy Couche 150gsm 65x86", 1000, "tờ", 2000, "Cty Giấy An Bình", "Ví dụ – có thể xóa dòng này"),
        row("", "", "GY002", "", 500, "tờ", 2500, "", "Điền Mã HOẶC Tên để khớp vật tư"),
      ];
  const ws = XLSX.utils.aoa_to_sheet([headers, ...examples]);
  ws["!cols"] = headers.map((h) => ({ wch: h.length + (h === "Tên vật tư" ? 18 : h === "Ghi chú" ? 22 : 5) }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "DongHang");

  // Sheet tra cứu loại phiếu: copy "Mã loại" vào cột "Loại phiếu" của sheet DongHang.
  const types = opts?.types;
  if (withGroups && types && types.length) {
    const refAoa: (string | number)[][] = [
      ["Mã loại", "Tên loại", "Nhóm"],
      ...types.map((t) => [t.code, t.name, t.group === "xuat" ? "Xuất kho" : "Nhập kho"]),
    ];
    const refWs = XLSX.utils.aoa_to_sheet(refAoa);
    refWs["!cols"] = [{ wch: 14 }, { wch: 34 }, { wch: 12 }];
    XLSX.utils.book_append_sheet(wb, refWs, "LoaiPhieu");
  }
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
  const iType = idx(["loại phiếu", "loai phieu", "loại", "loai", "type"]);
  const iGroup = idx(["nhóm phiếu", "nhom phieu", "nhóm", "nhom", "group", "phiếu số", "stt phiếu"]);
  const iPartner = idx(["đối tượng", "doi tuong", "nhà cung cấp", "nha cung cap", "ncc", "khách hàng", "khach hang", "partner"]);
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
      group: cell(cells, iGroup),
      typeText: cell(cells, iType),
      partner: cell(cells, iPartner),
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
