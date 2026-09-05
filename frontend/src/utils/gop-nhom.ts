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
  /** ĐVT THẬT của dòng con này ("cái" cho tấm bìa). */
  donViTinh: string;
  /** ĐVT của CỤM, do phiếu tính giá chọn ("cuốn"). Dòng gộp in nhãn này; bỏ trống thì rơi về
   *  `donViTinh` của dòng ĐẦU cụm — luật cũ, dữ liệu cũ không đổi một chữ. */
  dvtNhom?: string | null;
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

/** Nhãn nhóm đã chuẩn hoá: bỏ khoảng trắng thừa + không phân biệt hoa thường (gõ lệch hoa vẫn
 *  gộp được). `null` = dòng không có nhãn, đứng riêng. */
function khoaNhan(nhom: string | null | undefined): string | null {
  const s = (nhom ?? "").trim();
  return s ? s.toLowerCase() : null;
}

/** Khoá gộp THẬT: cùng nhãn **và cùng số lượng** mới gộp (chủ chốt 26/08/2026).
 *
 *  Trước đây chỉ so nhãn rồi lấy SL của dòng ĐẦU: cụm "sách" gồm 10.000 cuốn + 100 cuốn in ra
 *  "10.000 cuốn · 27.972.034 đ" ⇒ đơn giá 2.797 đ/cuốn — sai cả SL lẫn đơn giá gửi cho khách.
 *  Nay hai phần đó tách thành 2 dòng, mỗi dòng đúng SL và đúng đơn giá của chính nó; ruột 1.200 +
 *  bìa 1.200 vẫn gộp thành 1 dòng như cũ.
 *
 *  ĐVT KHÔNG nằm trong khoá — chốt vậy. Cùng SL mà khác đơn vị (1.000 cuốn + 1.000 thẻ) thì vẫn
 *  gộp và in nhãn đơn vị của dòng ĐẦU; đừng "sửa" thành xét cả ĐVT mà không hỏi lại chủ. */
function khoaGop(d: DongGopDuoc): string | null {
  const nhan = khoaNhan(d.nhom);
  if (nhan === null) return null;
  return `${nhan}|${d.soLuong}`;
}

/**
 * Gom các dòng cùng nhãn `nhom` thành 1 dòng. Dòng không có nhãn đứng riêng như cũ.
 * Thứ tự giữ nguyên theo vị trí dòng ĐẦU TIÊN của mỗi nhóm.
 *
 * Quy ước (chốt với nghiệp vụ):
 * - CHỈ gộp các dòng cùng nhãn **và cùng SL**. Lệch SL thì tách dòng, mỗi dòng giữ đúng SL +
 *   đơn giá của nó (xem `khoaGop`). Nhãn nhóm bị tách làm nhiều dòng thì mọi dòng của nó đều ghi
 *   tiền tố tên phần, để khách biết dòng nào là phần nào.
 * - SL lấy của dòng ĐẦU cụm — KHÔNG cộng dồn, vì khách mua 1.200 cuốn chứ không phải 2.400
 *   (1.200 ruột + 1.200 bìa); cụm đã cùng SL nên lấy dòng nào cũng như nhau.
 * - ĐVT dòng gộp lấy `dvtNhom` (đơn vị của CỤM, khai ở phiếu tính giá — "cuốn"). Cụm không khai
 *   thì rơi về ĐVT của dòng ĐẦU như trước. Đừng quay lại lối cũ là ĐÈ đơn vị cụm lên mọi dòng
 *   con: nó làm mọi màn KHÔNG gộp (đơn hàng, phiếu giao) hiện "Bìa sách — 2.000 cuốn".
 * - Thành tiền và tiền VAT cộng dồn; đơn giá suy ra = Σ thành tiền ÷ SL.
 * - VAT% chỉ hiện khi mọi dòng cùng mức; lệch thì null (tiền vẫn đúng).
 */
export function gopTheoNhom<T>(
  rows: T[],
  chonDong: (r: T) => DongGopDuoc,
): DongDaGop<T>[] {
  const out: DongDaGop<T>[] = [];
  const viTri = new Map<string, number>();       // khoá gộp (nhãn+SL) → index trong `out`
  const oTheoNhan = new Map<string, number[]>(); // nhãn → các index của nhãn đó trong `out`

  rows.forEach((row, i) => {
    const d = chonDong(row);
    const k = khoaGop(d);
    const idx = k !== null ? viTri.get(k) : undefined;

    if (idx === undefined) {
      const nhan = khoaNhan(d.nhom);
      if (k !== null && nhan !== null) {
        viTri.set(k, out.length);
        oTheoNhan.set(nhan, [...(oTheoNhan.get(nhan) ?? []), out.length]);
      }
      out.push({
        key: k ?? `don-${i}`,
        ten: k !== null ? (d.nhom ?? "").trim() : d.ten,
        soLuong: d.soLuong,
        // Dòng thuộc cụm: nhãn đơn vị của CỤM nếu đã khai. Dòng đứng riêng (`k === null`) thì
        // `dvtNhom` không có nghĩa — đơn vị của nó là của nó.
        donViTinh: (k !== null ? (d.dvtNhom ?? "").trim() : "") || d.donViTinh,
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

  // Một nhãn bị tách làm nhiều dòng (lệch SL): khách sẽ thấy 2 dòng cùng tên "sách". Ghi tiền
  // tố tên phần vào diễn giải của MỌI dòng thuộc nhãn đó để phân biệt — cụm nhiều dòng đã có sẵn
  // tiền tố ở trên, chỉ cần bù cho cụm 1 dòng.
  for (const idxs of oTheoNhan.values()) {
    if (idxs.length < 2) continue;
    for (const i of idxs) {
      const g = out[i];
      if (g.goc.length === 1) g.dienGiai = [gachDauDong(chonDong(g.goc[0]))];
    }
  }

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

/** Một nhãn nhóm bị lệch SL: tên nhãn, số DÒNG sẽ in cho khách, và từng phần con. */
export interface NhomLechSoLuong {
  ten: string;
  /** Nhãn này sẽ in ra mấy dòng trên bản gửi khách (mỗi mức SL một dòng). */
  soDongSeIn: number;
  /** Từng phần con theo thứ tự khai — để câu cảnh báo nêu thẳng phần nào bao nhiêu. */
  phan: { ten: string; soLuong: number; donViTinh: string }[];
}

/**
 * Cùng nhãn nhóm nhưng SL lệch nhau → cảnh báo trên màn soạn. Bản in KHÔNG gộp chúng nữa (xem
 * `khoaGop`) nên số gửi khách không còn sai; cảnh báo giữ lại vì lệch SL trong một cụm thường là
 * khai nhầm (bìa 1.000 / ruột 500), và vì người soạn cần biết trước là sẽ in ra 2 dòng.
 */
export function nhomLechSoLuong<T>(
  rows: T[],
  chonDong: (r: T) => DongGopDuoc,
): NhomLechSoLuong[] {
  const theoNhom = new Map<
    string,
    { ten: string; phan: { ten: string; soLuong: number; donViTinh: string }[] }
  >();
  for (const row of rows) {
    const d = chonDong(row);
    const nhan = khoaNhan(d.nhom);
    if (nhan === null) continue;
    const cur = theoNhom.get(nhan) ?? { ten: (d.nhom ?? "").trim(), phan: [] };
    cur.phan.push({ ten: d.ten, soLuong: d.soLuong, donViTinh: d.donViTinh });
    theoNhom.set(nhan, cur);
  }
  const cum = (p: { soLuong: number }) => String(p.soLuong);
  return [...theoNhom.values()]
    .filter((v) => new Set(v.phan.map(cum)).size > 1)
    .map((v) => ({ ten: v.ten, soDongSeIn: new Set(v.phan.map(cum)).size, phan: v.phan }));
}
