// Gom dòng giao hàng theo CỤM BÁN (design nhập kho thành phẩm §3): Ruột + Bìa cùng nhãn nhóm là MỘT
// quyển, kho giữ một mã, giao / nhận cùng một số. Form bày MỘT ô cho cả cụm và gửi dòng ĐẦU cụm —
// máy chủ bung ra mọi dòng của cụm. Gõ hai ô riêng thì sớm muộn lệch số, máy chủ trả lỗi.

export interface DongCoCum {
  order_line_id: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  cum_khoa?: string | null;
  cum_ten?: string | null;
  cum_dvt?: string | null;
}

export interface CumDong<T extends DongCoCum> {
  /** Dòng đầu cụm — khoá của ô nhập và là dòng gửi lên máy chủ. */
  dau: T;
  dong: T[];
  ten: string;
  donVi: string | null;
}

/** Giữ thứ tự theo dòng đầu của mỗi cụm; dòng không có `cum_khoa` là cụm một dòng. */
export function gomCum<T extends DongCoCum>(lines: T[]): CumDong<T>[] {
  const ra: CumDong<T>[] = [];
  const theoKhoa = new Map<string, CumDong<T>>();
  for (const l of lines) {
    const k = l.cum_khoa;
    const co = k ? theoKhoa.get(k) : undefined;
    if (co) {
      co.dong.push(l);
      continue;
    }
    const c: CumDong<T> = {
      dau: l,
      dong: [l],
      ten: (k ? l.cum_ten : null) ?? l.mo_ta ?? "",
      donVi: (k ? l.cum_dvt : null) ?? l.don_vi_tinh,
    };
    ra.push(c);
    if (k) theoKhoa.set(k, c);
  }
  return ra;
}

/** "Kỷ yếu 25 năm (Ruột sách + Bìa sách)" — cụm một dòng thì chỉ mô tả dòng. */
export function nhanCum<T extends DongCoCum>(c: CumDong<T>): string {
  if (c.dong.length < 2) return c.ten;
  return `${c.ten} (${c.dong.map((d) => d.mo_ta ?? "").filter(Boolean).join(" + ")})`;
}
