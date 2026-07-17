// Mẫu Excel + đọc file danh mục vật tư (dùng chung cho tab Danh mục và Import tồn đầu kỳ).
// Cột = đúng các trường nhập liệu trong form vật tư (Thông tin chung + Thuộc tính).
// Tồn đầu kỳ dùng thêm cột "Tồn đầu kỳ (SL)" (withQty) — vật tư chưa có sẽ được tạo mới.
import * as XLSX from "xlsx";
import type { MaterialInput, KhoMaterialOption } from "../api/client";
import { exportXlsx, matchMaterial } from "./xlsxImport";

// Loại vật tư (khớp VALID_MATERIAL_TYPES backend) + nhãn tiếng Việt.
export const MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: "vat_tu", label: "NVL / Vật tư chung" },
  { value: "thanh_pham", label: "Thành phẩm" },
  { value: "ban_thanh_pham", label: "Bán thành phẩm" },
  { value: "vat_tu_tieu_hao", label: "Vật tư tiêu hao" },
  { value: "ccdc", label: "Công cụ dụng cụ (CCDC)" },
  { value: "phu_tung", label: "Phụ tùng" },
  { value: "hang_khach_gui", label: "Hàng khách gửi" },
  { value: "paper", label: "Giấy" },
  { value: "carton", label: "Carton / Bìa" },
  { value: "film", label: "Màng / Film" },
  { value: "lamination", label: "Cán màng" },
  { value: "glue", label: "Keo" },
  { value: "decal", label: "Decal" },
  { value: "pp", label: "PP" },
  { value: "canvas", label: "Canvas" },
  { value: "formex", label: "Formex" },
  { value: "chemical", label: "Hóa chất" },
];
export const TYPE_LABEL: Record<string, string> = Object.fromEntries(MATERIAL_TYPES.map((t) => [t.value, t.label]));

// 17 cột trùng form. Import tồn thêm cột QTY_HEADER ở cuối.
export const MATERIAL_HEADERS = [
  "Mã", "Tên", "Loại", "Đơn vị", "Nhóm hàng", "NCC mặc định",
  "ĐVT mua", "ĐVT xuất", "Quy cách", "Đơn vị quy đổi",
  "Họ giấy", "Khổ rộng (cm)", "Khổ cao/dài (cm)", "Định lượng (gsm)", "Độ dày (mm)",
  "Ghi chú", "Trạng thái",
];
const QTY_HEADER = "Tồn đầu kỳ (SL)";

// "ram=500; thùng=1000" → [{uom:"ram",factor:500},{uom:"thùng",factor:1000}]. Ngăn bằng ; hoặc xuống dòng.
export function parseUomsCell(s: string): { uom: string; factor: number }[] {
  const out: { uom: string; factor: number }[] = [];
  for (const part of s.split(/[;\n]+/)) {
    const seg = part.trim();
    if (!seg) continue;
    const eq = seg.split(/[=:]/);
    if (eq.length < 2) continue;
    const uom = eq[0].trim();
    const factor = Number(eq[1].replace(",", ".").trim());
    if (uom && factor > 0) out.push({ uom, factor });
  }
  return out;
}

/** Tải mẫu .xlsx danh mục vật tư (đủ cột). `withQty` = thêm cột "Tồn đầu kỳ (SL)" cho import tồn. */
export function downloadMaterialTemplate(filename: string, opts?: { withQty?: boolean }): void {
  const withQty = !!opts?.withQty;
  const headers = withQty ? [...MATERIAL_HEADERS, QTY_HEADER] : MATERIAL_HEADERS;
  const ex1 = [
    "", "Giấy Couche 150", "Giấy", "tờ", "Giấy in", "Cty Giấy An Bình",
    "ream", "tờ", "150gsm 65x86", "ream=500",
    "Couche", 65, 86, 150, "",
    "Ví dụ – có thể xóa dòng này", "Hoạt động",
    ...(withQty ? [1000] : []),
  ];
  const ex2 = [
    "", "Mực in đen", "Vật tư tiêu hao", "kg", "Mực in", "",
    "", "", "", "",
    "", "", "", "", "",
    withQty ? "Vật tư chưa có sẽ được tạo mới; đã có chỉ cần Mã + SL" : "Vật tư thường – không cần Họ giấy/GSM", "Hoạt động",
    ...(withQty ? [50] : []),
  ];
  exportXlsx(filename, headers, [ex1, ex2], "VatTu");
}

export interface ParsedMaterialRow {
  rowNum: number;
  code: string;
  name: string;
  unit: string;
  qty: number | null;     // chỉ có khi withQty
  payload: MaterialInput; // dùng để tạo mới vật tư nếu chưa có
}

/** Đọc file .xlsx/.xls/.csv danh mục vật tư → payload từng dòng + lỗi.
 *  `warehouseId` gán vào vật tư tạo mới. `withQty` = đọc & bắt buộc cột "Tồn đầu kỳ (SL)" > 0.
 *  `existing` (nếu có) = vật tư đã có: dòng khớp Mã/Tên thì KHÔNG bắt buộc nhập lại Tên/Đơn vị. */
export async function parseMaterialFile(
  file: File,
  warehouseId: number | null,
  opts?: { withQty?: boolean; existing?: KhoMaterialOption[] },
): Promise<{ rows: ParsedMaterialRow[]; errs: string[] }> {
  const withQty = !!opts?.withQty;
  const existing = opts?.existing;
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const ws = wb.Sheets[wb.SheetNames[0]];
  const raw = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, blankrows: false, defval: "" });
  const rowsData: string[][] = raw
    .map((row) => (Array.isArray(row) ? row.map((c) => (c == null ? "" : String(c))) : []))
    .filter((r) => r.some((c) => c.trim()));
  if (rowsData.length < 2) return { rows: [], errs: [] };

  const header = rowsData[0].map((h) => h.trim().toLowerCase());
  const idx = (names: string[]) => header.findIndex((h) => names.includes(h));
  const iMa = idx(["mã", "ma", "code", "mã vật tư", "ma vat tu"]);
  const iTen = idx(["tên", "ten", "name", "tên vật tư", "ten vat tu"]);
  const iLoai = idx(["loại", "loai", "type"]);
  const iDv = idx(["đơn vị", "don vi", "dvt", "unit"]);
  const iNhom = idx(["nhóm hàng", "nhom hang", "group"]);
  const iNcc = idx(["ncc mặc định", "ncc mac dinh", "ncc", "supplier", "nhà cung cấp", "nha cung cap"]);
  const iMua = idx(["đvt mua", "dvt mua", "purchase_uom"]);
  const iTieu = idx(["đvt xuất", "dvt xuat", "đvt tiêu hao", "dvt tieu hao", "consumption_uom"]);
  const iQc = idx(["quy cách", "quy cach", "spec", "spec_text"]);
  const iQd = idx(["đơn vị quy đổi", "don vi quy doi", "đvt quy đổi", "quy đổi", "uoms"]);
  const iHo = idx(["họ giấy", "ho giay", "paper_family"]);
  const iRong = idx(["khổ rộng (cm)", "khổ rộng", "kho rong", "width", "width_cm"]);
  const iCao = idx(["khổ cao/dài (cm)", "khổ cao (cm)", "khổ cao", "kho cao", "height", "height_cm"]);
  const iGsm = idx(["định lượng (gsm)", "định lượng", "dinh luong", "gsm"]);
  const iDay = idx(["độ dày (mm)", "độ dày", "do day", "thickness", "thickness_mm"]);
  const iGhi = idx(["ghi chú", "ghi chu", "note"]);
  const iTt = idx(["trạng thái", "trang thai", "status"]);
  const iQty = idx(["tồn đầu kỳ (sl)", "tồn đầu kỳ", "ton dau ky", "số lượng", "so luong", "sl", "qty"]);

  if (iTen < 0 || iDv < 0) {
    return { rows: [], errs: ["File thiếu cột Tên hoặc Đơn vị. Hãy tải đúng file mẫu."] };
  }

  const cell = (cells: string[], i: number) => (i >= 0 ? (cells[i] ?? "").trim() : "");
  const numCell = (cells: string[], i: number): number | null => {
    const v = cell(cells, i).replace(",", ".");
    const n = Number(v);
    return v !== "" && !Number.isNaN(n) ? n : null;
  };
  // Số lượng tồn: bỏ dấu ngăn nghìn (20.000 → 20000) trước khi parse.
  const numQty = (cells: string[], i: number): number | null => {
    const s = cell(cells, i);
    const v = s.replace(/[.,](?=\d{3}\b)/g, "").replace(",", ".");
    const n = Number(v);
    return s !== "" && !Number.isNaN(n) ? n : null;
  };

  const rows: ParsedMaterialRow[] = [];
  const errs: string[] = [];
  for (let r = 1; r < rowsData.length; r++) {
    const cells = rowsData[r];
    const code = cell(cells, iMa);
    const name = cell(cells, iTen);
    const unit = cell(cells, iDv);
    const qty = withQty ? numQty(cells, iQty) : null;
    if (!code && !name && !(withQty && qty)) continue; // dòng trống → bỏ qua
    const matched = existing ? matchMaterial(existing, code, name) : null;
    if (withQty && !(qty && qty > 0)) { errs.push(`Dòng ${r + 1} (${name || code}): Tồn đầu kỳ (SL) phải > 0`); continue; }
    // Vật tư đã có (khớp Mã/Tên) → chỉ ghi tồn, không cần Tên/Đơn vị. Chưa có → cần Tên + Đơn vị để tạo mới.
    if (!matched) {
      if (!name) { errs.push(`Dòng ${r + 1}: thiếu Tên (vật tư chưa có — cần Tên để tạo mới)`); continue; }
      if (!unit) { errs.push(`Dòng ${r + 1} (${name}): thiếu Đơn vị`); continue; }
    }

    const loaiRaw = cell(cells, iLoai).toLowerCase();
    const mt = MATERIAL_TYPES.find((t) => t.value === loaiRaw || t.label.toLowerCase() === loaiRaw)?.value ?? "vat_tu";
    const isPaperRow = mt === "paper";
    const ttRaw = cell(cells, iTt).toLowerCase();
    const isActive = ttRaw === "" ? true : !/(ẩn|an khoi|khóa|khoa|ngừng|ngung|inactive|false|^0$)/.test(ttRaw);

    rows.push({
      rowNum: r + 1,
      code,
      name,
      unit,
      qty,
      payload: {
        code: code || null,
        name, material_type: mt, unit,
        warehouse_id: warehouseId,
        group_name: cell(cells, iNhom) || null,
        default_supplier: cell(cells, iNcc) || null,
        purchase_uom: cell(cells, iMua) || null,
        consumption_uom: cell(cells, iTieu) || null,
        spec_text: cell(cells, iQc) || null,
        uoms: parseUomsCell(cell(cells, iQd)),
        paper_family: isPaperRow ? cell(cells, iHo) || null : null,
        width_cm: isPaperRow ? numCell(cells, iRong) : null,
        height_cm: isPaperRow ? numCell(cells, iCao) : null,
        gsm: isPaperRow ? numCell(cells, iGsm) : null,
        thickness_mm: numCell(cells, iDay),
        note: cell(cells, iGhi) || null,
        is_active: isActive,
      },
    });
  }
  return { rows, errs };
}
