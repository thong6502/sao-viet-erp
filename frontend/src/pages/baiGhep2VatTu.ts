// Bảng kê VẬT TƯ của MỘT bài ghép — nặn về đúng khuôn `BangKeVatTu` để DÙNG LẠI `LsxVatTuPanel`
// (cùng dải KPI + thẻ theo bước + khối TỔNG GOM của màn Lệnh). Không đẻ kiểu trình bày thứ hai.
//
// Bài ghép có HAI tầng, khác lệnh đơn:
//   · Bước CHUNG (`sd.gop`) — lượt chạy chung cho cả tờ (in chung, ghi kẽm chung). Có đủ tổ/máy/
//     số vào→ra ⇒ dựng được thẻ pipeline y như công đoạn của lệnh.
//   · Bước RIÊNG của từng thành viên — chi tiết theo bước nằm ở màn Lệnh, không vẽ lại ở đây.
//
// SỐ LƯỢNG lấy TỪ MỘT NGUỒN: bảng cân đối server (`materials`, engine `can_doi`) — đã quy đổi đơn
// vị, đã cộng đúng cả giấy lẫn vật tư bước riêng. Không tự cộng lại từ `vat_tus` thô kẻo hai màn
// lệch số. `sd.gop` ở đây CHỈ cho phần MÔ TẢ bước (tên/tổ/máy/vào→ra), không cho con số vật tư.
import type { BaiGhep2VatTuHieuLuc, BaiGhepSoDo } from "../api/client";
import type { BangKeVatTu, BuocKe, DongKe, NhomVatTu, TongKe } from "./lsxVatTu";
import { tenDonVi } from "./tenDonVi";

/** Cân đối chỉ đẻ hai nhóm: giấy là NVL chính, còn lại là vật tư tiêu hao. Khuôn/dụng cụ KHÔNG
 *  nằm trong bảng cân đối bài ghép (mượn-rồi-trả, không đi mua) nên không có nhánh `dung_cu`. */
function nhomCua(hang_loai: string): NhomVatTu {
  return hang_loai === "giay" ? "nvl" : "vat_tu";
}

/** Nhãn đơn vị đọc từ danh mục, ngã về mã trần khi mã lạ — cùng lối `lsxVatTu.ts`. */
function nhanDv(ma: string | null | undefined): string {
  const k = (ma ?? "").trim();
  return k ? (tenDonVi(k) ?? k) : "";
}

function soHoac0(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

const HANG: Record<NhomVatTu, number> = { nvl: 0, vat_tu: 1, dung_cu: 2 };

export function keVatTuBaiGhep(sd: BaiGhepSoDo, materials: BaiGhep2VatTuHieuLuc): BangKeVatTu {
  // (1) Chiếu vật tư của BƯỚC CHUNG xuống từng bước, theo `gang_step_key` server đã gắn. Chỉ dòng
  //     `pham_vi === "bai_ghep"` mới treo lên thẻ bước; dòng bước riêng của lệnh gom ở BOM tổng.
  const dongTheoBuoc = new Map<string, DongKe[]>();
  for (const item of materials.items) {
    const nhom = nhomCua(item.hang_loai);
    for (const d of item.dong) {
      if (d.pham_vi !== "bai_ghep" || !d.gang_step_key) continue;
      const line: DongKe = {
        nhom,
        khoa: `${item.hang_loai}:${item.hang_id}`,
        ma: item.hang_ma,
        ten: item.hang_ten || "Vật tư",
        so_luong: soHoac0(d.nhu_cau),
        don_vi: nhanDv(item.don_vi_goc),
        chu_thich: null,
      };
      const cu = dongTheoBuoc.get(d.gang_step_key);
      if (cu) cu.push(line);
      else dongTheoBuoc.set(d.gang_step_key, [line]);
    }
  }

  // (2) Thẻ pipeline = các BƯỚC CHUNG theo thứ tự chạy. `id` chỉ là khoá React nên dùng chỉ số.
  const buocs: BuocKe[] = [...sd.gop]
    .sort((a, b) => a.thu_tu - b.thu_tu)
    .map((g, i) => ({
      id: i,
      thu_tu: g.thu_tu,
      ten: g.ten,
      to: g.to_ten,
      may: g.may_ten,
      dau_viec: g.khoan_ten,
      tren_dong_giay: g.tren_giay,
      sl_vao: soHoac0(g.so_luong_vao),
      dv_vao: nhanDv(g.don_vi_vao),
      sl_ra: soHoac0(g.so_luong_ra),
      dv_ra: nhanDv(g.don_vi_ra),
      dong: dongTheoBuoc.get(g.step_key) ?? [],
      // Bước chung không mang dữ liệu khuôn ở sơ đồ ⇒ không dựng cảnh báo thiếu khuôn ở tầng bài.
      thieu_khuon: false,
    }));

  // (3) TỔNG GOM (BOM) = nguyên bảng cân đối — đầy đủ cả giấy lẫn vật tư bước riêng. KHÔNG cộng lại
  //     từ `buocs` (chỉ có bước chung) kẻo thiếu phần bước riêng. `buocs: []` vì món ở bài đến từ
  //     nhiều lệnh/bước, không quy về một `thu_tu` như lệnh đơn.
  const tong: TongKe[] = materials.items
    .map((item) => ({
      nhom: nhomCua(item.hang_loai),
      khoa: `${item.hang_loai}:${item.hang_id}`,
      ma: item.hang_ma,
      ten: item.hang_ten || "Vật tư",
      so_luong: soHoac0(item.tong_can),
      don_vi: nhanDv(item.don_vi_goc),
      chu_thich: null,
      buocs: [] as number[],
    }))
    .sort((a, b) => HANG[a.nhom] - HANG[b.nhom] || a.ten.localeCompare(b.ten, "vi"));

  return {
    buocs,
    tong,
    so_buoc_trong: buocs.filter((b) => b.dong.length === 0).length,
    so_buoc_chua_dau_viec: buocs.filter((b) => !b.dau_viec).length,
    so_mon: tong.length,
  };
}
