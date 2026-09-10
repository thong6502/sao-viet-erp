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
// 09/09/2026 — HAI TỪ VỰNG, mỗi từ vựng vẫn đúng MỘT nguồn, đừng trộn lại:
//   · ĐƠN VỊ kho / mua hàng / khoán (`kg`, `thùng`, `hộp`) → danh mục Đơn vị, hàm `tenDonVi`.
//   · CHẶNG dòng giấy (`to_nguyen · to · con · tay · cai`) → hằng của backend, `nhanTram` bên dưới.
// Chuỗi mã trùng nhau nhưng hai thứ khác hẳn: `cong_doan.don_vi_vao/ra` hỏi "bước này đứng ở chặng
// nào", không hỏi "đếm bằng đơn vị kho nào". Bảng nhãn cứng `TRAM_DONG_GIAY` từng nằm ở
// `rebuildCatalogConfigs.tsx` đã GỠ cùng ngày — nó là bản sao thứ hai của `models/don_vi_do.TRAM_NHAN`.
//
// Nạp MỘT lần cho cả phiên (bảng ~20 dòng, gần như không đổi) — cùng lối `useBienCongThuc`.
import { useEffect, useState } from "react";
import { authed } from "../api/client";
import { useAuth } from "../auth/useAuth";

type DonViRow = { ma?: unknown; ten?: unknown };
type TramRow = { ma?: unknown; nhan?: unknown; nhan_ngan?: unknown };

let _cache: Map<string, string> | null = null;
let _choDoi: Promise<Map<string, string>> | null = null;

// ── CHẶNG dòng giấy — bảng RIÊNG, nạp cùng chuyến với danh mục Đơn vị ──────────────────────────
//
// `cong_doan.don_vi_vao/ra` (và mọi cột kế thừa nó: bước lệnh · bước bài ghép · công việc tổ) giữ
// MÃ CHẶNG `to_nguyen · to · con · tay · cai`, KHÔNG phải mã đơn vị kho — dù chuỗi trùng nhau.
// Tra chúng vào danh mục Đơn vị là cùng một công đoạn Đóng gói hiện "Con → Thành phẩm" ở màn danh
// mục nhưng "20.000 con → 20.000 cái" ở phiếu tính giá, và ai đổi tên đơn vị `con` ở màn Kho là
// chữ ở màn Công đoạn đổi theo. Nhãn chặng vì thế đi đường riêng: `nhanTram` / `nhanTramDai`.
//
// Nạp GHÉP vào `useNapTenDonVi` chứ không đẻ hook thứ hai: mọi màn bày `don_vi_vao/ra` đều đã gọi
// hook đó rồi, tách ra là 15 màn phải nhớ gọi thêm một cái nữa — quên một chỗ thì chỗ ấy hiện mã
// trần mà không ai thấy. Bảng 5 dòng, đi kèm không tốn gì.
let _tram: Map<string, { nhan: string; ngan: string }> | null = null;

/** Nhãn chặng ĐỨNG SAU CON SỐ ("2.750 tờ in"). `undefined` = không phải mã chặng ⇒ nơi gọi tự lo. */
export function nhanTram(ma: string | null | undefined): string | undefined {
  const k = (ma ?? "").trim().toLowerCase();
  return k ? _tram?.get(k)?.ngan : undefined;
}

/** Nhãn chặng ĐỨNG MỘT MÌNH (menu, cột danh mục). `undefined` như `nhanTram`. */
export function nhanTramDai(ma: string | null | undefined): string | undefined {
  const k = (ma ?? "").trim().toLowerCase();
  return k ? _tram?.get(k)?.nhan : undefined;
}

/** 5 chặng cho Ô CHỌN, THEO ĐÚNG THỨ TỰ server trả (thứ tự dòng giấy chảy, không phải a→z).
 *
 *  Rỗng = CHƯA nạp được, KHÔNG phải "danh mục không có gì". Nơi gọi phải hiện đúng nghĩa đó (xem
 *  `CatalogDrawer`: ô chọn bày "Đang nạp danh sách chặng…") — 09/09/2026 ô Đơn vị đầu vào/ra rơi
 *  vào cảnh chỉ còn mỗi dòng "—", người khai tưởng menu mất sạch mà không có lấy một câu báo. */
export function tramOptions(): { value: string; label: string }[] {
  return [..._tram ?? []].map(([value, v]) => ({ value, label: v.nhan }));
}

// Ai đang chờ bảng nhãn. Một chuyến nạp phải đánh thức MỌI màn đang mở, không riêng màn tình cờ
// gọi hook đúng lúc đó: bảng về muộn mà chỉ drawer vẽ lại thì cột "Đơn vị" sau lưng nó còn nằm
// nguyên `con → cai` cho tới khi người dùng vô tình chạm vào thứ khác.
const _nguoiCho = new Set<() => void>();

/** ĐỦ CẢ HAI bảng chưa. Thiếu một bảng vẫn coi là chưa xong ⇒ màn sau còn nạp lại. */
function _daDu(): boolean {
  return !!_cache && !!_tram?.size;
}

/** Kết một chuyến nạp.
 *
 *  ⚠️ ĐỪNG chốt `_choDoi` khi nạp HỤT. Trước 09/09/2026 chuyến hỏng vẫn được giữ lại làm kết quả
 *  của cả phiên: một cú `/api/don-vi/tram` rơi trúng lúc backend restart là bảng chặng rỗng cho
 *  tới khi người dùng F5 — ô "Đơn vị đầu vào/đầu ra" ở màn Công đoạn chỉ còn mỗi dòng "—", không
 *  chọn được gì, mà không màn nào báo một câu. Xoá `_choDoi` ở đây để lần mount sau thử lại;
 *  hỏng liên tục thì mỗi lần mở màn tốn thêm 2 request bảng nhỏ, đổi lấy việc nó TỰ LÀNH.
 */
function _xongMotChuyen(): Map<string, string> {
  if (!_daDu()) _choDoi = null;
  for (const bao of _nguoiCho) bao();
  return _cache ?? new Map<string, string>();
}

/** Tên của một mã đơn vị. Chưa nạp xong / mã lạ ⇒ trả `undefined` để nơi gọi hiện MÃ TRẦN —
 *  thà thấy `to` còn hơn nuốt mất rồi đoán một cái tên không có trong danh mục. */
export function tenDonVi(ma: string | null | undefined): string | undefined {
  const k = (ma ?? "").trim().toLowerCase();
  return k ? _cache?.get(k) : undefined;
}

/** Cả danh mục Đơn vị cho Ô CHỌN, theo đúng thứ tự server trả.
 *
 *  Dùng ở drawer bước NGOÀI dòng giấy (ghi kẽm, đóng thùng): bước đó không nằm trên chuỗi giấy nên
 *  không khai bằng CHẶNG được, người kế hoạch chọn thẳng đơn vị thật (`bài in`, `bản kẽm`).
 *
 *  Rỗng = CHƯA nạp được, KHÔNG phải "danh mục không có gì" — cùng nghĩa với `tramOptions`, nơi gọi
 *  phải nói ra điều đó thay vì bày một ô chọn trống trơn. */
export function donViOptions(): { value: string; label: string }[] {
  return [..._cache ?? []].map(([value, label]) => ({ value, label }));
}

/** Gọi MỘT lần ở màn nào cần nhãn đơn vị HOẶC nhãn chặng (Lệnh SX · Kế hoạch · danh mục Công đoạn).
 *  Trả version để component vẽ lại khi bảng vừa về — không có nó thì lần vẽ đầu hiện mã trần rồi
 *  đứng im ở đó.
 *
 *  Nạp HAI bảng trong một chuyến: đơn vị (danh mục, xưởng đổi được) và chặng dòng giấy (hằng của
 *  code, `/api/don-vi/tram`). Lý do ghép chung xem khối chú thích `_tram` ở trên. */
export function useNapTenDonVi(): number {
  const { token } = useAuth();
  const [v, setV] = useState(_daDu() ? 1 : 0);
  useEffect(() => {
    const ve = () => setV((x) => x + 1);
    _nguoiCho.add(ve);
    return () => { _nguoiCho.delete(ve); };
  }, []);
  useEffect(() => {
    if (!token || _daDu()) return;
    const cho = (_choDoi ??= Promise.all([
      // Chặng hỏng KHÔNG được kéo theo đơn vị và ngược lại: `catch` riêng từng chuyến, thiếu bảng
      // nào thì chỉ chỗ dùng bảng ấy chịu, `null` = chuyến đó hụt (khác `items: []` là "server
      // trả rỗng thật").
      authed<{ items: DonViRow[] }>("/api/don-vi?size=200", token).catch(() => null),
      authed<{ items: TramRow[] }>("/api/don-vi/tram", token).catch(() => null),
    ])
      .then(([dv, tr]) => {
        if (tr) {
          _tram = new Map(
            (tr.items ?? [])
              .map((t) => [String(t.ma ?? "").trim().toLowerCase(), {
                nhan: String(t.nhan ?? ""), ngan: String(t.nhan_ngan ?? ""),
              }] as const)
              .filter(([ma, n]) => ma && n.nhan && n.ngan),
          );
        }
        if (dv) {
          _cache = new Map(
            (dv.items ?? [])
              .map((d) => [String(d.ma ?? "").trim().toLowerCase(), String(d.ten ?? "")] as const)
              .filter(([ma, ten]) => ma && ten),
          );
        }
        return _xongMotChuyen();
      })
      .catch(() => _xongMotChuyen()));
    // Không cần `.then(setV)` ở đây: `_xongMotChuyen` đã gọi mọi người chờ, kể cả chính hook này.
    void cho;
  }, [token]);
  return v;
}
