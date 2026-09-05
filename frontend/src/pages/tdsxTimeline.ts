// Trục thời gian DÙNG CHUNG cho các tab dạng mini-Gantt của "Theo dõi sản xuất" — Theo máy
// (Task 17b) và Gantt tổng thể (Task 18b). Rút NGUYÊN công thức từ `TdsxTheoMay.tsx` (bản 17b,
// hàm `tinhDomain`/`tinhLuoiGio` ở cuối file) — Ruling C138 (task-18b-brief.md) chốt rút PHẦN
// TÍNH TOÁN này ra module riêng, KHÔNG đổi hằng số/công thức, để tab Theo máy giữ NGUYÊN hành vi
// sau khi rút.
//
// C138 cũng chốt KHÔNG mượn `xl2Shared` của Xếp lịch 2 (thang đó khoá vào lịch làm việc nhiều
// ngày + nghỉ lễ, nặng hơn mức "mini-Gantt chỉ đọc" hai tab này cần) và KHÔNG mount `Xl2Gantt.tsx`
// vào tab Gantt (18 props kéo-thả — `khoaMay`/`taiMay`/`onPropose`/`onDropQueue`... — không hợp
// một màn CHỈ ĐỌC). Giá phải trả: tab Gantt không có 4 mức thu phóng / ruy-băng ca / tô ngày lễ mà
// `Xl2Gantt` có — chấp nhận được vì đây là bàn TRA tổng thể theo lệnh, không phải bàn xếp lịch.
import { useCallback, useMemo } from "react";

/** Hai mật độ trục giờ: dải NGẮN (≤30 giờ, ca hiện tại + vài ngày tới) hiện lưới GIỜ cho đọc chi
 *  tiết; dải DÀI hơn (backlog trọn đời có thể vắt qua nhiều tuần) hiện lưới NGÀY để tổng bề rộng
 *  không phình tới hàng trăm nghìn pixel. */
export const PX_PER_GIO_NGAN = 72;
export const PX_PER_GIO_DAI = 14;
export const NGUONG_DAI_GIO = 30;

/** MỘT khoảng có thể vẽ lên trục. `batDau`/`ketThuc` là ISO string hoặc `null` — mốc thiếu bị BỎ
 *  QUA khi tính domain (không kéo domain méo theo một giá trị rác), đúng hành vi gốc của
 *  `TdsxTheoMay` (mỗi bên `if (b.du_kien_bat_dau) {...}` xét riêng, không đòi cả cặp). */
export interface TdsxTimelineMoc {
  batDau: string | null;
  ketThuc: string | null;
}

/** Domain (mili-giây epoch) của trục — MIN mọi `batDau` tới MAX mọi `ketThuc`, đệm 2 giờ hai đầu
 *  để khối sát mép vẫn còn khoảng đọc nhãn. Không có mốc nào (mảng rỗng, hoặc toàn `null`) ⇒ lùi
 *  về "hôm nay 00:00 → +24h" thay vì domain rỗng vô nghĩa — khuôn gốc của Theo máy. */
export function tinhDomain(mocs: TdsxTimelineMoc[]): { start: number; end: number } {
  let min: number | null = null;
  let max: number | null = null;
  for (const m of mocs) {
    if (m.batDau) {
      const t = new Date(m.batDau).getTime();
      if (min === null || t < min) min = t;
    }
    if (m.ketThuc) {
      const t = new Date(m.ketThuc).getTime();
      if (max === null || t > max) max = t;
    }
  }
  if (min === null || max === null) {
    const nay = new Date();
    nay.setHours(0, 0, 0, 0);
    return { start: nay.getTime(), end: nay.getTime() + 24 * 3_600_000 };
  }
  const DEM_GIO = 2 * 3_600_000; // đệm 2 giờ hai đầu để khối sát mép vẫn còn khoảng đọc nhãn
  return { start: min - DEM_GIO, end: Math.max(max + DEM_GIO, min + 3_600_000) };
}

/** Lưới mốc hiện trên trục: giờ tròn (dải ngắn) hoặc nửa đêm mỗi ngày (dải dài). */
export function tinhLuoiGio(
  domain: { start: number; end: number },
  spanGio: number,
): { t: number; nhan: string; dam: boolean }[] {
  const out: { t: number; nhan: string; dam: boolean }[] = [];
  if (spanGio <= NGUONG_DAI_GIO) {
    const start = new Date(domain.start);
    start.setMinutes(0, 0, 0);
    for (let t = start.getTime(); t <= domain.end; t += 3_600_000) {
      const d = new Date(t);
      out.push({ t, nhan: `${String(d.getHours()).padStart(2, "0")}:00`, dam: d.getHours() % 2 === 0 });
    }
  } else {
    const start = new Date(domain.start);
    start.setHours(0, 0, 0, 0);
    for (let t = start.getTime(); t <= domain.end; t += 24 * 3_600_000) {
      const d = new Date(t);
      out.push({
        t,
        nhan: `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`,
        dam: true,
      });
    }
  }
  return out;
}

/** Bó trọn domain + lưới + hệ số px/giờ + `xOf` (ISO → toạ độ x px) — cả hai tab mini-Gantt (Theo
 *  máy, Gantt tổng thể) gọi lại NGUYÊN bó này, chỉ khác nhau ở cách mỗi tab GOM `mocs` từ dữ liệu
 *  riêng của nó (Theo máy gom từ `lane.blocks`, Gantt gom thẳng từ mỗi dòng lệnh). */
export function useTdsxTimeline(mocs: TdsxTimelineMoc[]) {
  const domain = useMemo(() => tinhDomain(mocs), [mocs]);
  const spanGio = (domain.end - domain.start) / 3_600_000;
  const pxPerGio = spanGio <= NGUONG_DAI_GIO ? PX_PER_GIO_NGAN : PX_PER_GIO_DAI;
  const trackWidth = Math.max(1, Math.round(spanGio * pxPerGio));
  const ticks = useMemo(() => tinhLuoiGio(domain, spanGio), [domain, spanGio]);
  const xOf = useCallback(
    (iso: string) => ((new Date(iso).getTime() - domain.start) / 3_600_000) * pxPerGio,
    [domain, pxPerGio],
  );
  return { domain, spanGio, pxPerGio, trackWidth, ticks, xOf };
}
