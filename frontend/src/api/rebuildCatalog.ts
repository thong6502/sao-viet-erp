// API — 10 danh mục Cấu hình danh mục (xem `REBUILD_CONFIGS`). File riêng dùng chung
// `authed` của client.ts (silent-refresh nhất quán). Wiring Phase E.
import { authed, blobUrl } from "./client";

export interface ListOut<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  /** Số dòng theo TỪNG giá trị của cột tab lọc (`{"Máy in": 12, "": 2}` — khoá rỗng = dòng chưa
   *  khai giá trị đó). Chỉ 3 endpoint có tab lọc mới trả: Máy · Công đoạn · Khuôn bế.
   *  Màn danh mục phân trang ở máy chủ nên chỉ cầm 20 dòng — số trên tab phải do server đếm. */
  facets?: Record<string, number>;
}

export type Row = Record<string, unknown> & { id: number; ma: string; ten: string };

function qs(params: Record<string, unknown>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

// -- Danh sách THAM CHIẾU cho ô chọn trong drawer (nhớ trong phiên) ---------------------------
// Đo 14/09/2026, drawer Công đoạn: tên trên ô chọn chỉ hiện sau 0,5–1 s dù mỗi danh sách ở máy
// chủ chỉ 25–60 ms — mỗi lần MỞ drawer là hỏi lại từ đầu 6 danh mục nguồn (StrictMode ở dev nhân
// đôi thành 12), socket nghỉ quá 5 s đã bị uvicorn đóng nên phải bắt tay lại. Nhớ lại danh sách lần
// trước thì mở lần sau có tên NGAY, bản mới vẫn hỏi lại nền rồi đè lên (người khác vừa sửa danh mục
// thì tên chỉ cũ trong một nhịp mạng). Khoá theo NGƯỜI (sub của token) chứ không theo token: token
// đổi sau mỗi lượt refresh, khoá theo nó thì cứ refresh là mất nhớ; khoá theo người thì đăng xuất
// đổi tài khoản không thấy danh mục của người trước.
const nhoThamChieu = new Map<string, Row[]>();
const dangHoiThamChieu = new Map<string, Promise<Row[]>>();

function nguoiCuaToken(token: string): string {
  try {
    return String(JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).sub);
  } catch {
    return token;
  }
}

/** Bỏ nhớ mọi danh sách tham chiếu của một danh mục — gọi sau khi GHI vào danh mục đó. */
function boNhoThamChieu(prefix: string): void {
  for (const khoa of [...nhoThamChieu.keys()]) {
    const path = khoa.slice(khoa.indexOf("|") + 1);
    if (path === prefix || path.startsWith(`${prefix}?`)) nhoThamChieu.delete(khoa);
  }
}

/** CRUD generic cho 1 prefix (vd "/api/may-thiet-bi"). */
export function crud(prefix: string) {
  return {
    list(token: string, params: Record<string, unknown> = {}): Promise<ListOut<Row>> {
      return authed<ListOut<Row>>(`${prefix}${qs({ size: 200, ...params })}`, token);
    },
    /** Danh sách cho Ô CHỌN tham chiếu: `nho` = bản đã nhớ từ lần trước (có thì bày ngay), `moi` =
     *  bản vừa hỏi lại. Hai chỗ cùng hỏi một danh sách lúc nó đang bay (StrictMode chạy effect hai
     *  lần) thì dùng chung MỘT request; `batMoi` bỏ qua request đang bay — dùng khi vừa sửa danh mục
     *  nguồn ngay trong drawer, request cũ có thể đã rời máy trước lúc sửa. */
    thamChieu(token: string, params: Record<string, unknown> = {}, batMoi = false): { nho?: Row[]; moi: Promise<Row[]> } {
      const path = `${prefix}${qs({ size: 200, ...params })}`;
      const khoa = `${nguoiCuaToken(token)}|${path}`;
      let moi = batMoi ? undefined : dangHoiThamChieu.get(khoa);
      if (!moi) {
        const p: Promise<Row[]> = authed<ListOut<Row>>(path, token)
          .then((r) => {
            // Request cũ về SAU request mới (`batMoi`) thì không được đè bản mới vào nhớ.
            if (dangHoiThamChieu.get(khoa) === p) nhoThamChieu.set(khoa, r.items);
            return r.items;
          })
          .finally(() => { if (dangHoiThamChieu.get(khoa) === p) dangHoiThamChieu.delete(khoa); });
        dangHoiThamChieu.set(khoa, p);
        moi = p;
      }
      return { nho: nhoThamChieu.get(khoa), moi };
    },
    /** Chỉ ĐỌC bản đã nhớ, không hỏi mạng — để khởi tạo state ngay lần render đầu (đợi tới effect
     *  thì drawer đã vẽ một nhịp "#13" rồi mới ra tên). */
    daNho(token: string, params: Record<string, unknown> = {}): Row[] | undefined {
      return nhoThamChieu.get(`${nguoiCuaToken(token)}|${prefix}${qs({ size: 200, ...params })}`);
    },
    get(token: string, id: number): Promise<Row> {
      return authed<Row>(`${prefix}/${id}`, token);
    },
    create(token: string, body: Record<string, unknown>): Promise<Row> {
      boNhoThamChieu(prefix);
      return authed<Row>(prefix, token, { method: "POST", body: JSON.stringify(body) });
    },
    update(token: string, id: number, body: Record<string, unknown>): Promise<Row> {
      boNhoThamChieu(prefix);
      return authed<Row>(`${prefix}/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
    },
    /** BẬT / NGỪNG dùng một dòng. Route RIÊNG chứ không phải `update({active})`.
     *
     *  `PUT /{id}` nhận schema ĐẦY ĐỦ nên gửi mỗi `{active:false}` là Pydantic chặn ở cổng với
     *  422 "field required" — đúng lỗi làm nút "Ngừng dùng"/"Bật lại" bấm-không-ăn ở cả bốn danh
     *  mục xoá mềm. Vẫn gửi ĐÚNG một trường: kèm cả dòng vào là kéo theo field server tự tính
     *  (`don_vi_ten`, `quy_doi_chips`…) rồi nhật ký ghi một đống "thay đổi" ma. */
    datActive(token: string, id: number, active: boolean): Promise<Row> {
      boNhoThamChieu(prefix);
      return authed<Row>(`${prefix}/${id}/active`, token, {
        method: "PATCH", body: JSON.stringify({ active }),
      });
    },
    remove(token: string, id: number): Promise<void> {
      boNhoThamChieu(prefix);
      return authed<void>(`${prefix}/${id}`, token, { method: "DELETE" });
    },
    /** Nhân bản một dòng — server copy toàn bộ cột, tự đặt mã/tên "(bản sao)" không trùng. */
    clone(token: string, id: number): Promise<Row> {
      boNhoThamChieu(prefix);
      return authed<Row>(`${prefix}/${id}/clone`, token, { method: "POST" });
    },
    /** Lịch sử ĐẦY ĐỦ một ô công thức (mục 3+7) — "Xem thêm lịch sử" trong `FormulaField`. Chỉ
     *  danh mục bật `cong_thuc_truong` ở router mới có route này. */
    lichSuCongThuc(token: string, id: number): Promise<CongThucLichSuItem[]> {
      return authed<CongThucLichSuItem[]>(`${prefix}/${id}/lich-su-cong-thuc`, token);
    },
    /** Xuất Excel — blob URL, tải về ngay. CHỈ dòng đang dùng, nhưng ĐỦ ô cấu hình hiện hành:
     *  mọi công thức, bậc tính và bảng con (bậc bù hao, đầu việc, gói bảo trì…) đi ra sheet con
     *  đọc được. Không kèm lịch sử. Danh mục rỗng thì chỉ còn dòng tiêu đề, tự đóng vai file mẫu. */
    templateBlobUrl(token: string): Promise<string> {
      return blobUrl(`${prefix}/mau-excel`, token);
    },
    /** Nhập Excel — UPSERT theo mã, CẢ FILE là MỘT giao dịch.
     *
     *  `mode="preview"` chạy y hệt `commit` rồi rollback, nên con số xem trước là con số THẬT
     *  (kể cả lỗi chỉ lộ ra lúc service validate) — không phải một bản kiểm sơ bộ dễ dãi hơn,
     *  thứ khiến người dùng bấm Xác nhận rồi mới ăn lỗi. `mode="commit"` mới ghi, và chỉ ghi khi
     *  KHÔNG còn dòng lỗi nào. */
    importExcel(token: string, file: File, mode: "preview" | "commit"): Promise<ImportExcelOut> {
      if (mode === "commit") boNhoThamChieu(prefix);
      const form = new FormData();
      form.append("file", file);
      return authed<ImportExcelOut>(`${prefix}/import-excel?mode=${mode}`, token, {
        method: "POST", body: form,
      });
    },
  };
}

/** Kết quả một lượt nhập Excel — khớp `ImportExcelOut` ở `catalog_base.py`.
 *
 *  `preview` và `commit` trả CÙNG một hình dạng; khác nhau đúng ở `da_ghi`. */
export interface ImportExcelOut {
  /** Không còn dòng lỗi nào. `false` ⇒ chắc chắn chưa ghi gì cả. */
  hop_le: boolean;
  tong_dong: number;
  tao_moi: number;
  cap_nhat: number;
  /** Dòng không đổi một ô nào — KHÔNG gọi service, nên cũng không đẻ dòng nhật ký. */
  khong_doi: number;
  /** Đã thực sự ghi xuống DB. Luôn `false` ở `mode=preview`. */
  da_ghi: boolean;
  loi: { sheet: string; dong: number; cot: string; ly_do: string }[];
}

/** Một mốc trong lịch sử một ô công thức — xem `crud().lichSuCongThuc`. */
export interface CongThucLichSuItem {
  id: number;
  gia_tri_cu: string | null;
  gia_tri_moi: string | null;
  sua_boi: number | null;
  sua_luc: string;
}

export const mayThietBi = crud("/api/may-thiet-bi");
export const congDoan = crud("/api/cong-doan");
export const loaiSanPham = crud("/api/loai-san-pham");
// Vật liệu Kho: 3 loại con dưới cùng prefix.
export const giay = crud("/api/vat-lieu-kho/giay");
/** Danh mục ĐƠN VỊ ĐO — nguồn cho ô ĐVT trên phiếu tính giá. */
export const donViDo = crud("/api/don-vi");
export const muc = crud("/api/vat-lieu-kho/muc");
export const banKem = crud("/api/vat-lieu-kho/ban-kem");
export const vatTu = crud("/api/vat-lieu-kho/vat-tu-in-an"); // vật tư in ấn gộp (mực/kẽm/màng/keo)

// -- Trạng thái máy LÚC NÀY (dẫn xuất: sự cố · vùng khoá · lệnh đang chạy) --------------------
/** Máy KHÔNG có mặt trong map = đang rảnh — backend chỉ trả máy có chuyện. */
export interface TrangThaiMay {
  trang_thai: "may_dung" | "bao_tri" | "khoa" | "dang_chay" | "ranh";
  nhan: string;                 // nhãn tiếng Việt dựng ở backend — hai màn khỏi tự đặt tên lệch nhau
  chi_tiet: string | null;
  phieu_id: number | null;      // phiếu sự cố đang mở
  den: string | null;
}
export function trangThaiMay(token: string): Promise<Record<string, TrangThaiMay>> {
  return authed<{ items: Record<string, TrangThaiMay> }>("/api/may-thiet-bi/trang-thai", token)
    .then((r) => r.items ?? {});
}

// -- Lịch sử giá Giấy (phiên bản) — GET danh sách + POST thêm phiên bản (mirror đơn giá hiện hành) --
export interface GiayGiaVersion {
  id: number; giay_id: number; version_no: number; ngay_hieu_luc: string | null;
  is_current: boolean; kho_dai: number; kho_rong: number; gsm: number | null;
  don_vi_gia: string; don_gia: number; gia_thi_truong: number | null;
  ghi_chu: string | null; created_at: string | null;
}
export function giayVersions(token: string, giayId: number): Promise<GiayGiaVersion[]> {
  return authed(`/api/vat-lieu-kho/giay/${giayId}/versions`, token);
}
export function addGiayVersion(
  token: string, giayId: number, body: Record<string, unknown>,
): Promise<GiayGiaVersion> {
  return authed(`/api/vat-lieu-kho/giay/${giayId}/versions`, token, {
    method: "POST", body: JSON.stringify(body),
  });
}

// -- Nhật ký của MỘT bản ghi danh mục (ai đổi gì, lúc nào) — một cửa chung cho 10 màn --
export interface NhatKyItem {
  at: string;
  /** "Phòng ban · Chức vụ · Tên"; null khi do hệ thống/seed sinh ra. */
  actor_name: string | null;
  action: string;
  /** Các thay đổi trong cùng một lần lưu, nối bằng " · ". */
  detail: string;
}
export function nhatKyDanhMuc(
  token: string, loai: string, id: number,
): Promise<{ items: NhatKyItem[] }> {
  return authed(`/api/nhat-ky-danh-muc/${loai}/${id}`, token);
}

// -- "Còn ai dùng không?" — hỏi TRƯỚC khi xoá, chung cho 8 màn danh mục --------------
export interface KiemXoa {
  /** Chưa ai dùng ⇒ cho xoá hẳn. Khai nhầm thì xoá ngay, đừng giữ lại làm rác danh mục. */
  xoa_han_duoc: boolean;
  /** Nơi ĐANG DÙNG, dạng câu có số: "3 bước trong lệnh sản xuất". Có cái này ⇒ chỉ ngừng dùng. */
  chan: string[];
  /** Thứ sẽ BAY THEO nếu xoá hẳn (CASCADE ở DB) — phải nói bằng số trước khi người ta bấm. */
  keo_theo: string[];
}
export function kiemXoa(token: string, loai: string, id: number): Promise<KiemXoa> {
  return authed(`/api/danh-muc/${loai}/${id}/kiem-xoa`, token);
}

// `mayBhr` (BHR preview cho Máy) ĐÃ GỠ 11/08/2026 — không page nào gọi, và endpoint
// `/api/may-thiet-bi/{id}/bhr` cũng đã gỡ cùng cả khối cột BHR (không có ô nhập nào).


