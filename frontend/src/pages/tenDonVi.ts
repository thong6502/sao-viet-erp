// TÊN đơn vị đọc từ DANH MỤC — thay ba bảng nhãn cứng đã gỡ (12/08/2026).
//
// Vì sao phải có file này: đơn vị là danh mục ĐỘNG, xưởng tự khai và tự đổi tên. Trước đây frontend
// giữ tới BA bảng nhãn khai cứng, và chúng lệch nhau lẫn lệch với danh mục:
//
//     danh mục Đơn vị      `to` = "tờ"        `cai` = "cái"
//     rebuildCatalogConfigs `to` = "Tờ in"     `cai` = "Thành phẩm"
//     client.LSX_DON_VI_LABELS `to` = "Tờ in"  `cai` = "Thành phẩm"
//     lsxBuoc.DON_VI        `to` = "Tờ"        `cai` = "Con"     ← ba tên cho một thứ
//
// Nên cùng một bước hiện "Tờ in → Thành phẩm" ở bảng danh mục nhưng "tờ → cái" khi mở drawer ra.
// Nay một nguồn: danh mục. Thêm đơn vị mới là mọi màn hiện đúng ngay, không phải đi sửa hằng.
//
// Nạp MỘT lần cho cả phiên (bảng ~20 dòng, gần như không đổi) — cùng lối `useBienCongThuc`.
import { useEffect, useState } from "react";
import { authed } from "../api/client";
import { useAuth } from "../auth/useAuth";

type DonViRow = { ma?: unknown; ten?: unknown };

let _cache: Map<string, string> | null = null;
let _choDoi: Promise<Map<string, string>> | null = null;

/** Tên của một mã đơn vị. Chưa nạp xong / mã lạ ⇒ trả `undefined` để nơi gọi hiện MÃ TRẦN —
 *  thà thấy `to` còn hơn nuốt mất rồi đoán một cái tên không có trong danh mục. */
export function tenDonVi(ma: string | null | undefined): string | undefined {
  const k = (ma ?? "").trim().toLowerCase();
  return k ? _cache?.get(k) : undefined;
}

/** Gọi MỘT lần ở màn nào cần nhãn đơn vị (Lệnh SX · Kế hoạch). Trả version để component vẽ lại khi
 *  danh mục vừa về — không có nó thì lần vẽ đầu hiện mã trần rồi đứng im ở đó. */
export function useNapTenDonVi(): number {
  const { token } = useAuth();
  const [v, setV] = useState(_cache ? 1 : 0);
  useEffect(() => {
    if (!token || _cache) return;
    const cho = (_choDoi ??= authed<{ items: DonViRow[] }>("/api/don-vi?size=200", token)
      .then((r) => (_cache = new Map(
        (r.items ?? [])
          .map((d) => [String(d.ma ?? "").trim().toLowerCase(), String(d.ten ?? "")] as const)
          .filter(([ma, ten]) => ma && ten),
      )))
      .catch(() => new Map<string, string>()));
    let song = true;
    cho.then(() => { if (song) setV((x) => x + 1); });
    return () => { song = false; };
  }, [token]);
  return v;
}
