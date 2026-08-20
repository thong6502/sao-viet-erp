// GỘP DÒNG KHI IN CHO KHÁCH — dùng chung cho bản in Báo giá và bản in Xác nhận đơn hàng.
//
// Vì sao cần: phiếu tính giá bắt buộc tách sách thành nhiều dòng (ruột, bìa) — mỗi dòng là 1 tờ
// giấy chạy máy riêng. Khách thì mua MỘT quyển. Nhãn `nhom` (gõ ở phiếu tính giá, đông cứng
// sang báo giá rồi sang đơn) cho biết những dòng nào thuộc cùng một sản phẩm thương mại.
//
// CHỈ gộp ở lớp trình bày. Dữ liệu vẫn 1 dòng/thành phần vì `lsx_service` sinh 1 LỆNH SẢN XUẤT
// cho MỖI dòng đơn — gộp ở tầng dữ liệu là mất lệnh bìa.

/** Một dòng bất kỳ đem gộp: chỉ cần các trường dưới đây. */
export interface DongGopDuoc {
  nhom?: string | null;
  /** Tên hiển thị của dòng con (Ruột / Bìa…) — dùng làm tiền tố khi gộp diễn giải. */
  ten: string;
  soLuong: number;
  donViTinh: string;
  /** Thành tiền NET của dòng (đã trừ chiết khấu, chưa VAT). */
  thanhTien: number;
  tienVat: number;
  vatPct: number;
  /** Khổ/spec dạng chữ — chỉ giữ khi mọi dòng trong nhóm giống nhau. */
  kichThuoc?: string | null;
  /** Diễn giải quy cách, mỗi dòng = 1 gạch đầu dòng. */
  dienGiai?: string | null;
}

export interface DongDaGop<T> {
  /** Khoá React + nhận diện nhóm. */
  key: string;
  ten: string;
  soLuong: number;
  donViTinh: string;
  thanhTien: number;
  tienVat: number;
  /** null = các dòng trong nhóm lệch VAT% → cột % để trống, tiền vẫn cộng đủ. */
  vatPct: number | null;
  kichThuoc: string | null;
  /** Gạch đầu dòng đã gộp; nhóm nhiều dòng thì mỗi dòng con 1 gạch có tiền tố tên. */
  dienGiai: string[];
  /** Đơn giá cho khách = Σ thành tiền ÷ SL nhóm. */
  donGia: number;
  /** Các dòng gốc (nguyên bản) — để chỗ gọi lấy thêm dữ liệu nếu cần. */
  goc: T[];
}

/** Khoá gộp: bỏ khoảng trắng thừa + không phân biệt hoa thường (gõ lệch hoa vẫn gộp được). */
function khoaNhom(nhom: string | null | undefined): string | null {
  const s = (nhom ?? "").trim();
  return s ? s.toLowerCase() : null;
}

/**
 * Gom các dòng cùng nhãn `nhom` thành 1 dòng. Dòng không có nhãn đứng riêng như cũ.
 * Thứ tự giữ nguyên theo vị trí dòng ĐẦU TIÊN của mỗi nhóm.
 *
 * Quy ước (chốt với nghiệp vụ):
 * - SL và ĐVT lấy của dòng ĐẦU nhóm (ruột) — KHÔNG cộng dồn, vì khách mua 1.200 cuốn chứ không
 *   phải 2.400 (1.200 ruột + 1.200 bìa).
 * - Thành tiền và tiền VAT cộng dồn; đơn giá suy ra = Σ thành tiền ÷ SL.
 * - VAT% chỉ hiện khi mọi dòng cùng mức; lệch thì null (tiền vẫn đúng).
 */
export function gopTheoNhom<T>(
  rows: T[],
  chonDong: (r: T) => DongGopDuoc,
): DongDaGop<T>[] {
  const out: DongDaGop<T>[] = [];
  const viTri = new Map<string, number>();   // khoá nhóm → index trong `out`

  rows.forEach((row, i) => {
    const d = chonDong(row);
    const k = khoaNhom(d.nhom);
    const idx = k !== null ? viTri.get(k) : undefined;

    if (idx === undefined) {
      if (k !== null) viTri.set(k, out.length);
      out.push({
        key: k ?? `don-${i}`,
        ten: k !== null ? (d.nhom ?? "").trim() : d.ten,
        soLuong: d.soLuong,
        donViTinh: d.donViTinh,
        thanhTien: d.thanhTien,
        tienVat: d.tienVat,
        vatPct: d.vatPct,
        kichThuoc: d.kichThuoc ?? null,
        // Nhóm 1 dòng: giữ nguyên gạch đầu dòng gốc. Có dòng thứ 2 gộp vào thì `themVaoNhom`
        // sẽ viết lại thành dạng có tiền tố tên.
        dienGiai: tachDienGiai(d.dienGiai),
        donGia: d.soLuong > 0 ? Math.round(d.thanhTien / d.soLuong) : d.thanhTien,
        goc: [row],
      });
      return;
    }

    const g = out[idx];
    if (g.goc.length === 1) {
      // Chuyển dòng đầu sang dạng có tiền tố ngay khi nhóm có từ 2 dòng trở lên.
      const dau = chonDong(g.goc[0]);
      g.dienGiai = [gachDauDong(dau)];
    }
    g.dienGiai.push(gachDauDong(d));
    g.thanhTien += d.thanhTien;
    g.tienVat += d.tienVat;
    if (g.vatPct !== null && g.vatPct !== d.vatPct) g.vatPct = null;
    if (g.kichThuoc !== (d.kichThuoc ?? null)) g.kichThuoc = null;
    g.donGia = g.soLuong > 0 ? Math.round(g.thanhTien / g.soLuong) : g.thanhTien;
    g.goc.push(row);
  });

  return out;
}

function tachDienGiai(s: string | null | undefined): string[] {
  return (s ?? "").split("\n").map((x) => x.trim()).filter(Boolean);
}

/** 1 dòng con trong nhóm → 1 gạch đầu dòng: "Ruột: KT 840×592mm · Ford 70 70g · In 1 màu 2 mặt". */
function gachDauDong(d: DongGopDuoc): string {
  const y = tachDienGiai(d.dienGiai);
  const ten = (d.ten || "").trim();
  if (!y.length) return ten;
  return ten ? `${ten}: ${y.join(" · ")}` : y.join(" · ");
}

/** Một nhóm bị lệch SL: tên nhóm, số sẽ IN cho khách (SL phần ĐẦU), và từng phần con. */
export interface NhomLechSoLuong {
  ten: string;
  /** SL in trên bản gửi khách = SL của phần đầu nhóm (bản in không cộng dồn). */
  slInChoKhach: number;
  /** Từng phần con theo thứ tự khai — để câu cảnh báo nêu thẳng phần nào bao nhiêu. */
  phan: { ten: string; soLuong: number }[];
}

/**
 * Nhóm có nhiều dòng nhưng SL lệch nhau → cảnh báo trên màn soạn (bản in vẫn lấy SL phần đầu).
 * Trả CHI TIẾT (không chỉ tên) để câu cảnh báo nêu rõ phần nào bao nhiêu + số in cho khách.
 */
export function nhomLechSoLuong<T>(
  rows: T[],
  chonDong: (r: T) => DongGopDuoc,
): NhomLechSoLuong[] {
  const theoNhom = new Map<string, { ten: string; phan: { ten: string; soLuong: number }[] }>();
  for (const row of rows) {
    const d = chonDong(row);
    const k = khoaNhom(d.nhom);
    if (k === null) continue;
    const cur = theoNhom.get(k) ?? { ten: (d.nhom ?? "").trim(), phan: [] };
    cur.phan.push({ ten: d.ten, soLuong: d.soLuong });
    theoNhom.set(k, cur);
  }
  return [...theoNhom.values()]
    .filter((v) => new Set(v.phan.map((p) => p.soLuong)).size > 1)
    .map((v) => ({ ten: v.ten, slInChoKhach: v.phan[0].soLuong, phan: v.phan }));
}
