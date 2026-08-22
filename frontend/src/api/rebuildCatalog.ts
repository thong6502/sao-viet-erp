// API — 10 danh mục Cấu hình danh mục (xem `REBUILD_CONFIGS`). File riêng dùng chung
// `authed` của client.ts (silent-refresh nhất quán). Wiring Phase E.
import { authed } from "./client";

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

/** CRUD generic cho 1 prefix (vd "/api/may-thiet-bi"). */
export function crud(prefix: string) {
  return {
    list(token: string, params: Record<string, unknown> = {}): Promise<ListOut<Row>> {
      return authed<ListOut<Row>>(`${prefix}${qs({ size: 200, ...params })}`, token);
    },
    get(token: string, id: number): Promise<Row> {
      return authed<Row>(`${prefix}/${id}`, token);
    },
    create(token: string, body: Record<string, unknown>): Promise<Row> {
      return authed<Row>(prefix, token, { method: "POST", body: JSON.stringify(body) });
    },
    update(token: string, id: number, body: Record<string, unknown>): Promise<Row> {
      return authed<Row>(`${prefix}/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
    },
    /** BẬT / NGỪNG dùng một dòng. Route RIÊNG chứ không phải `update({active})`.
     *
     *  `PUT /{id}` nhận schema ĐẦY ĐỦ nên gửi mỗi `{active:false}` là Pydantic chặn ở cổng với
     *  422 "field required" — đúng lỗi làm nút "Ngừng dùng"/"Bật lại" bấm-không-ăn ở cả bốn danh
     *  mục xoá mềm. Vẫn gửi ĐÚNG một trường: kèm cả dòng vào là kéo theo field server tự tính
     *  (`don_vi_ten`, `quy_doi_chips`…) rồi nhật ký ghi một đống "thay đổi" ma. */
    datActive(token: string, id: number, active: boolean): Promise<Row> {
      return authed<Row>(`${prefix}/${id}/active`, token, {
        method: "PATCH", body: JSON.stringify({ active }),
      });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`${prefix}/${id}`, token, { method: "DELETE" });
    },
  };
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


