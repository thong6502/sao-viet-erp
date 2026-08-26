// Hàm dùng chung của màn Giao hàng (tách từ pages/GiaoHangPage.tsx).
import type { DeliveryTrip } from "../../../../api/client";
import { NHAN_TRANG_THAI_CHUYEN } from "./constants";
import type { DongKeHoach } from "./types";

/** Nhãn trạng thái của MỘT chuyến — MỘT hàm cho MỌI chỗ render.
 *
 *  Kho lập phiếu xong ⇒ hàng đã soạn, tài xế tới lấy được, nên chữ đổi thành "Kho đã chuẩn bị
 *  xong" (chủ chốt 20/08/2026). Kho KHÔNG bấm gì trên màn này — cờ `kho_da_lap_phieu` đọc ngược
 *  từ sổ kho.
 *
 *  Viết thành hàm vì bảng chuyến render ở HAI chỗ (tab Đơn giao hàng và tab Yêu cầu giao); chép
 *  hai bản là sớm muộn hai chỗ nói hai kiểu. */
export function nhanChuyen(t: { trang_thai: string; kho_da_lap_phieu?: boolean }): string {
  if (t.trang_thai === "dang_chuan_bi" && t.kho_da_lap_phieu) return "Kho đã chuẩn bị xong";
  return NHAN_TRANG_THAI_CHUYEN[t.trang_thai] ?? t.trang_thai;
}

export function toneChuyen(tt: string): "on" | "off" | "warn" {
  if (tt === "thanh_cong") return "on";
  if (tt === "that_bai" || tt === "da_huy") return "off";
  return "warn";
}

/** Một dòng bảng = một YÊU CẦU giao.
 *
 * Từ 22/08/2026 một yêu cầu chỉ có MỘT chuyến (chặn ở service + chỉ số UNIQUE mg 0229), nên hàm
 * này gần như là ánh xạ 1–1. GIỮ nó thay vì đọc thẳng danh sách chuyến: dữ liệu gieo trước ngày
 * đó vẫn có thể có hai chuyến một yêu cầu, và bảng phải hiện tình trạng HIỆN TẠI chứ không hiện
 * hai dòng trùng mã trùng khách. */
export function gopTheoYeuCau(trips: DeliveryTrip[]): DongKeHoach[] {
  const theo = new Map<number, DeliveryTrip[]>();
  for (const t of trips) {
    const ds = theo.get(t.request_id);
    if (ds) ds.push(t);
    else theo.set(t.request_id, [t]);
  }
  return [...theo.values()]
    .map((ds) => {
      const moi = ds.reduce((a, b) => (b.lan_thu > a.lan_thu ? b : a));
      return {
        moi,
        tongKm: ds.reduce((n, t) => n + (t.km ?? 0), 0),
      };
    })
    .sort((a, b) => b.moi.gio_lay_hang.localeCompare(a.moi.gio_lay_hang));
}
