// Mã gợi ý cho bản ghi MỚI của một danh mục.
//
import { crud } from "../../api/rebuildCatalog";
import type { Row } from "./types";

export function tienToMa(prefix: string): string {
  if (prefix.includes("loai-san-pham")) return "LSP-";
  if (prefix.includes("may-thiet-bi")) return "TB-";
  if (prefix.includes("cong-doan")) return "CD-";
  if (prefix.endsWith("/kho")) return "KHO-";
  if (prefix.includes("giay")) return "GL-";
  if (prefix.includes("muc")) return "MUC-";
  if (prefix.includes("ban-kem")) return "KEM-";
  if (prefix.includes("quy-tac-binh-bai")) return "BB-";
  return "MA-";
}

export function soLonNhat(rows: Row[], codePrefix: string): number {
  const numRegex = new RegExp(`^${codePrefix}(\\d+)$`);
  let maxNum = 0;
  for (const r of rows) {
    const m = String(r.ma).trim().toUpperCase().match(numRegex);
    if (m) {
      const val = parseInt(m[1], 10);
      if (val > maxNum) maxNum = val;
    }
  }
  return maxNum;
}

/** Mã gợi ý cho bản ghi mới — HỎI MÁY CHỦ, không đoán từ mấy dòng đang hiện trên bảng.
 *
 *  Từ khi màn phân trang ở máy chủ, bảng chỉ cầm 20 dòng: đoán mã lớn nhất trong đó là đứng ở
 *  trang 1 (sắp theo mã tăng dần) sẽ gợi ý ra mã ĐÃ CÓ, người khai bấm Lưu mới ăn lỗi trùng.
 *  Danh sách sắp tăng dần nên mã lớn nhất nằm ở TRANG CUỐI — hai request nhẹ (một để biết tổng,
 *  một để lấy trang cuối) thay cho việc kéo cả danh mục về. */
export async function goiYMaTiepTheo(prefix: string, token: string): Promise<string> {
  const codePrefix = tienToMa(prefix);
  const api = crud(prefix);
  const dau = await api.list(token, { q: codePrefix, size: 1 });
  const soTrang = Math.max(1, Math.ceil(dau.total / 200));
  const cuoi = dau.total > 1
    ? await api.list(token, { q: codePrefix, size: 200, page: soTrang })
    : dau;
  return `${codePrefix}${String(soLonNhat(cuoi.items, codePrefix) + 1).padStart(4, "0")}`;
}
