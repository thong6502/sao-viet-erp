// Hợp đồng KHAI BÁO của màn danh mục dùng chung — một `CatalogConfig` mô tả trọn một màn.
//
// File này CHỈ được import `type ReactNode`. Mọi thứ khác trong `danh-muc/` đều trỏ về đây, nên
// hễ nó import ngược lại một component là cả cây thành vòng tròn (module rỗng lúc chạy, lỗi kiểu
// "Cannot access '...' before initialization" — rất khó lần).
import type { ReactNode } from "react";

export interface FieldDef {
  key: string;
  label: string;
  // `ref-search-ma` = như `ref-search` nhưng lưu MÃ (chuỗi) thay vì id — cho cột trỏ danh mục bằng
  // mã như `don_vi_gia` (quy đổi làm việc trên mã `kg`/`to`, không trên id).
  // `self-ref-multi` = như `ref-multi` nhưng nguồn chọn là CHÍNH danh mục đang mở (NVL thay thế) —
  // CatalogDrawer tự loại dòng đang sửa khỏi danh sách, người khai không tự chọn được chính mình.
  type?: "text" | "number" | "date" | "select" | "checkbox" | "ref" | "ref-multi" | "self-ref-multi" | "ref-search" | "ref-search-ma" | "bands" | "nhom_may" | "nhom_may-multi" | "formula" | "dau-viec-dinh-muc" | "chuan_bi_khoan" | "lich_bao_tri" | "don_vi_toc_do";
  options?: { value: string; label: string }[];
  /** Ô `formula`: ÉP bộ chip theo loại này thay vì suy từ màn. Cần khi MỘT màn có hai ô công thức
   *  hỏi hai câu khác nhau — "Công thức tính giá" (ra tiền) vs "Công thức tính lượng" (ra lượng,
   *  cần chip `sl_vao`/`sl_ra`, không cần chip đơn giá). */
  loaiO?: string;
  /** Ô `formula`: NHÃN của tab công thức chứa ô này. Cho phép MỘT màn tách nhiều tab công thức
   *  riêng — vd Giấy: ô `cong_thuc_gia` vào tab "Công thức tính giá", ô `cong_thuc_luong` vào tab
   *  "Công thức tính lượng". Ô công thức KHÔNG khai `nhanTab` rơi vào tab mặc định (nhãn
   *  `config.nhanTabCongThuc`, mặc định "Công thức tính giá") — nên màn 1 tab như cũ giữ nguyên. */
  nhanTab?: string;
  /** Ô `formula`: mã biến CẦN ẨN khỏi bảng chip của riêng Ô NÀY, dù `loaiO` cho phép — biến vẫn
   *  hợp lệ nếu gõ tay/đã lưu, chỉ không hiện chip bấm-để-chèn. Dùng khi có chip khác đúng hơn cho
   *  ngữ cảnh của ô (vd `to_dau_vao`/`to_sau_in` là số CẢ CHUỖI, còn `sl_vao`/`sl_ra` là số của
   *  CHÍNH BƯỚC — xem `bien_cong_thuc.py`). */
  an?: string[];
  refPrefix?: string;           // ref / ref-multi / ref-search: endpoint danh mục nguồn (đổ theo TÊN/MÃ)
  /** Query thêm khi nạp danh mục nguồn, vd `{ active: true }` — không lọc thì picker mời cả dòng
   *  đã ngừng dùng, người ta chọn xong bấm Lưu mới ăn lỗi từ server. */
  refParams?: Record<string, unknown>;
  required?: boolean;
  /** Chuỗi tĩnh, HOẶC hàm dựng câu từ chính form đang gõ — vd quy cách đóng gói hiện
   *  "1 thùng = 3 kg" ghép từ ô đơn vị đóng gói + ô hệ số + ĐVT. Câu đọc được kiểm bằng mắt
   *  ngay lúc khai, đỡ hơn hẳn hai ô số rời không nói lên nghĩa gì. */
  hint?: string | ((form: Record<string, unknown>) => string);
  group?: string;               // nhóm section trong drawer
  showIf?: (form: Record<string, unknown>) => boolean;  // ẩn/hiện field theo giá trị khác
  default?: unknown;            // prefill khi TẠO MỚI (giá trị thật, không phải placeholder "0")
  jsonKey?: string;             // field lưu LỒNG trong cột JSON này (vd "fields_theo_loai")
}

export interface ColumnDef {
  key: string;
  label: string;
  /** `extra` = dữ liệu PHỤ của chính dòng này, do `config.loadExtra` nạp song song (vd trạng thái
   *  máy lúc này). `undefined` khi chưa nạp xong hoặc dòng không có gì để nói. */
  render?: (r: Row, extra?: unknown) => ReactNode;
}

export interface FacetDef {
  key: string;                  // field lọc (vd "nhom")
  /** Tab khai CỨNG — chỉ dùng khi tập giá trị nằm trong code ở CẢ HAI đầu (vd `hang_loai` của
   *  Kho: thêm một loại là phải sửa backend). Màn nào lọc theo một danh mục người dùng khai
   *  được thì bỏ trống ô này và khai `source`. */
  values?: { value: string; label: string }[];
  /** DANH MỤC THẬT sinh ra tab (vd `/api/nhom-may` — chính nguồn đổ ô chọn trong drawer). Có
   *  `source` thì hàng tab bày đúng danh sách người dùng đang khai, kể cả mục chưa có dòng nào
   *  (số 0): nhóm vừa tạo mà không thấy tab đâu thì người khai tưởng nó không lưu được. */
  source?: string;
  /** Nối thêm tab cho giá trị CÓ THẬT trong dữ liệu mà `values`/`source` chưa liệt kê. Cần cho
   *  cột lưu CHỮ tự do: dòng cũ mang tên nhóm đã gỡ khỏi danh mục vẫn phải có lối lọc tới. */
  dynamic?: boolean;
}

/** Bản ghi danh mục. Khai lại ở đây (thay vì import từ `api/rebuildCatalog`) để `types.ts` giữ
 *  đúng lời hứa "không import gì ngoài `type ReactNode`" — hai khai báo phải khớp nhau. */
export type Row = Record<string, unknown> & { id: number; ma: string; ten: string };

export interface CatalogConfig {
  title: string;
  /** Tiêu đề H1 RIÊNG khi cần KHÁC `title` — vd menu là "Khai báo kho" nhưng danh từ ở nút/lọc vẫn
   *  là "kho hàng" ("Thêm kho hàng", "Lọc kho hàng"). Bỏ trống ⇒ H1 dùng luôn `title`. CHỈ đổi H1. */
  heading?: string;
  prefix: string;
  /** Khoá module RBAC gác các nút GHI của màn (Thêm = `create` · Xóa = `delete` · Bật lại =
   *  `update`). Lấy đúng chuỗi đang khai ở `components/Sidebar.tsx` — sai một ký tự là vai có
   *  quyền vẫn không thấy nút. Bỏ trống = KHÔNG gác, giữ y hành vi cũ (backend vẫn chặn bằng 403,
   *  đây chỉ để đừng bày ra nút bấm-xong-mới-báo-lỗi). */
  moduleQuyen?: string;
  /** Khoá loại của bản ghi trong nhật ký (`"{loai}:{id}"` — khớp `LOAI_MODULE` ở backend).
   *  Có khoá này thì drawer mọc thêm tab "Nhật ký" khi đang SỬA một bản ghi đã lưu. */
  nhatKyLoai?: string;
  columns: ColumnDef[];
  fields: FieldDef[];
  facet?: FacetDef;             // tab lọc phía trên (tùy chọn)
  /** Dữ liệu PHỤ nạp SONG SONG danh sách, khoá theo id bản ghi — cột nào cần thì đọc ở tham số
   *  thứ hai của `render`. Dùng cho số DẪN XUẤT không thuộc bản ghi (vd trạng thái máy suy từ sự
   *  cố + vùng khoá + lệnh đang chạy). Cố ý KHÔNG nhét vào schema CRUD dùng chung: schema đó
   *  đang đổ dropdown cho cả chục màn khác, bắt họ trả giá cho số chỉ một màn cần là sai chỗ.
   *  Hỏng thì NUỐT (trả `{}`) — mất cột phụ không được phép làm trắng cả bảng danh mục. */
  loadExtra?: (token: string) => Promise<Record<string, unknown>>;
  /** Nhãn của TAB chứa các ô công thức. Mặc định "Công thức tính giá" — đúng cho màn có ô ra TIỀN
   *  (Giấy · Vật tư · Công đoạn), SAI cho màn chỉ có ô ra LƯỢNG: máy khai cách đo theo đơn vị tốc
   *  độ, công việc khoán khai cách đo lượng khoán, cả hai không nhắc tới tiền. Nhãn sai ở đây mời
   *  người khai gõ công thức tiền vào ô lượng — mà gõ nhầm thì tiền chảy vào chỗ đếm lượng, không
   *  ai soi ra. Màn có `renderExtra` (Đơn vị) vẫn giữ nhãn riêng của nó. */
  nhanTabCongThuc?: string;
  /** Chia phần khai báo thành nhiều TAB theo `group`. Chỉ màn khai dài mới cần (Máy có 7 nhóm,
   *  cuộn một mạch rất mệt). Không khai thì render một mạch như cũ. Nhóm không liệt kê ở đây rơi
   *  vào tab ĐẦU TIÊN — quên khai một nhóm thì nó vẫn hiện, không biến mất im lặng. */
  tabsKhai?: { id: string; label: string; groups: string[] }[];
  // Block phụ cuối drawer (preview BHR của Máy · bảng quy đổi của Đơn vị). `existing` = null khi
  // đang TẠO — block nào cần id thì tự nhắc "lưu trước đã".
  renderExtra?: (form: Record<string, unknown>, existing: Row | null) => ReactNode;
  softDelete?: boolean;         // "Xóa" = ẩn mềm (active=false), giữ dữ liệu; list chỉ hiện active
  /** Danh mục do HỆ SINH, không ai gõ tay ⇒ giấu nút "Thêm". Máy chủ chặn song song
   *  (`VatLieuKhoService._chan_go_tay`) — giấu nút mà không chặn thì một lời gọi API thẳng vẫn
   *  đẻ được dòng. Dùng cho Thành phẩm: `OrderService.confirm()` khai, xem docs/prd-thanh-pham.md. */
  khongTaoTay?: boolean;
  /** Giấu nút "Xóa". Cho danh mục mà dòng có thể đang được lô tồn / chứng từ trỏ vào — xoá là
   *  làm mồ côi. Ngừng dùng thì tắt `active`. */
  khongXoa?: boolean;
  /** Bày nút "Nhân bản" ở mỗi dòng (gọi `crud(prefix).clone`, gác quyền `clone`). Server copy toàn
   *  bộ cột, tự đặt mã/tên "(bản sao)" không trùng; bấm xong mở luôn drawer bản ghi mới để đổi tên
   *  ngay. Chỉ bật ở danh mục khai tay, có endpoint `/clone` thật (xem `enable_clone` ở backend). */
  enableClone?: boolean;
  /** Bày 2 nút "Xuất Excel" / "Nhập Excel" ở đầu bảng.
   *
   *  "Xuất Excel" ra CHỈ dòng đang dùng nhưng ĐỦ ô cấu hình hiện hành — mọi công thức, bậc tính và
   *  bảng con nằm ở sheet riêng đọc được (không JSON thô), không kèm lịch sử. Danh mục rỗng thì chỉ
   *  còn dòng tiêu đề, tự đóng vai file mẫu; vì thế KHÔNG còn nút "Tải mẫu" riêng.
   *
   *  "Nhập Excel" là UPSERT theo mã, HAI BƯỚC (xem trước → xác nhận) và CẢ FILE LÀ MỘT GIAO DỊCH:
   *  còn một dòng lỗi thì không ghi gì cả. Chỉ bật ở danh mục có `CatalogExcelSpec` khai ở
   *  `services/catalog_excel_specs.py` (hiện đủ 13 màn).
   *
   *  HAI mức quyền khác nhau: "Xuất Excel" chỉ cần quyền ĐỌC (đã ngầm định vì đang xem được bảng);
   *  "Nhập Excel" đòi CẢ `create` LẪN `update` — một dòng có thể là tạo mới hoặc cập nhật, server
   *  cũng gác `/import-excel` bằng đúng cặp quyền đó. */
  enableImport?: boolean;
  autoCode?: boolean;           // mã sinh NGẦM ở backend → ẩn ô "Mã" lúc tạo, không gửi ma
  /** Tạo xong thì GIỮ drawer mở ở bản ghi vừa tạo. Dùng cho màn có khối con phải gắn vào id (vd
   *  Đơn vị: tạo "tấn" xong khai ngay quy đổi) — đóng phắt là bắt người ta đi tìm lại dòng. */
  moLaiSauKhiTao?: boolean;
  deriveInitial?: (existing: Row | null) => Record<string, unknown>;  // giá trị UI suy ra khi mở form (vd _method)
  // map field UI → body API trước khi gửi. `existing` = bản ghi đang sửa (null khi TẠO) — cần khi
  // phải GỘP vào một cột JSON: field bị `showIf` ẩn thì không có trong `body`, dựng lại cột JSON
  // từ số 0 là xoá mất các khoá khác của cột đó.
  transformSubmit?: (
    body: Record<string, unknown>,
    form: Record<string, unknown>,
    existing: Row | null,
  ) => Record<string, unknown>;
  /** Ghi đè luồng XÓA mặc định (`XoaDanhMucDialog` + ẩn mềm) bằng dialog riêng — vd Kho: kiểm kho
   *  còn tồn / phiếu chờ ghi sổ / đề nghị dở rồi bắt gõ mã mới cho xóa. Dialog tự gọi API; xong
   *  gọi ctx.onDone (đóng + reload), hủy thì ctx.onClose. */
  renderDeleteDialog?: (row: Row, ctx: { token: string; onClose: () => void; onDone: () => void }) => ReactNode;
}

/** "Nhóm máy" là CHỮ TỰ DO nên phải đoán bằng tên. Định nghĩa ở đây (không phải trong
 *  `rebuildCatalogConfigs`) vì cả trang lẫn config cùng dùng, mà config đã import từ file này —
 *  để bên kia rồi import ngược lại là thành vòng tròn. */
export const isMayIn = (val: unknown) => {
  const s = String(val || "").trim().toLowerCase();
  return s === "máy in" || s === "in ngoài" || s.startsWith("in ") || s.includes("máy in") || s.includes("in offset");
};

// ── Kiểu dữ liệu của các ô BẢNG ĐỘNG (fields/) ───────────────────────────────────
// Để ở đây chứ không ở từng file ô: `rebuildCatalogConfigs` cần `ChuanBiKhoanRow`, mà config đã
// import từ barrel rồi — gom kiểu về một chỗ thì đường import không phải rẽ theo từng ô.

/** Một bậc số lượng: Từ SL · Đến SL · Giá trị · Đơn vị (tờ hay %). */
export interface BacRow { sl_tu?: number | null; sl_den?: number | null; gia_tri?: number; don_vi?: string }

/** Một khoản chuẩn bị của máy (thay giấy 15p · thay mực 18p). Tổng là ô CHỈ ĐỌC, tự cộng. */
export interface ChuanBiKhoanRow { ten?: string; phut?: number }

/** Việc con bên trong một gói bảo trì. */
export interface HangMucConRow { id?: string; ten?: string }

export interface LichBaoTriRow {
  id?: string; viec?: string; so?: number; don_vi?: string;
  // Mốc cho kỳ ĐẦU TIÊN: kỳ 1 rơi đúng vào ngày này. Từ kỳ 2 trở đi hạn = ngày HOÀN THÀNH phiếu
  // gần nhất + chu kỳ, nên ô này khai MỘT LẦN rồi thôi.
  // ⚠️ KHÁC hẳn ô "Lần cuối làm" đã bỏ 12/08/2026: ô đó bắt sửa lại sau MỖI lần bảo trì nên không
  // ai sửa, còn ô này chỉ để mồi lần đầu. Đừng gộp/gỡ nhầm hai thứ.
  ngay_bat_dau?: string;  // ISO date (yyyy-mm-dd)
  lan_cuoi?: string;      // (đã bỏ khỏi form) giá trị cũ vẫn giữ nguyên trong JSON khi lưu
  dung_phut?: number;     // 0/trống = không phải dừng máy
  hang_muc?: HangMucConRow[];   // việc con trong gói — không có cũng chạy (gói khai từ trước)
}

// `nang_suat_nguoi_gio` = mức TRUNG BÌNH (số chảy vào công thức thời lượng bước Tổ); min/max chỉ
// để ra khoảng nhanh–chậm, để trống thì ba mức bằng nhau. `don_vi_nang_suat` là NHÃN khai báo —
// không quy đổi, dùng chung bảng mã với ô "Đơn vị tốc độ" của máy.
export interface DinhMucRow {
  piece_rate_id: number; nang_suat_nguoi_gio: number;
  nang_suat_nguoi_gio_min?: number | null; nang_suat_nguoi_gio_max?: number | null;
  don_vi_nang_suat?: string | null;
  // Ba mốc nhân lực: tối thiểu ≤ chuẩn ≤ tối đa. Tối thiểu mới là KHAI BÁO, chưa vào công thức.
  so_nguoi_toi_thieu?: number;
  so_nguoi_tieu_chuan: number; so_nguoi_toi_da: number;
  /** VẬT TƯ đầu việc này tiêu thụ (nền BOM, mg 0191) — chỉ DANH SÁCH, không có số lượng: định mức
   *  tuỳ quy cách từng lệnh nên số khai ở đây là số chết. Số suy lúc bung ở bước lệnh. */
  vat_tu_ids?: number[];
}
