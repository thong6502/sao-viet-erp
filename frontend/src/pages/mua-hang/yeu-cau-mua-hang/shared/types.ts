// Kiểu dùng chung của màn Yêu cầu mua hàng (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseRequestLineInput,
  DepartmentPurchaseRequestLineOut,
  DepartmentPurchaseSourceType,
  DepartmentPurchaseWorkflowStatus,
} from "../../../../api/client";

export type StatusFilter = "all" | DepartmentPurchaseWorkflowStatus;

/** Đang hỏi bỏ MỘT MÓN khỏi yêu cầu — `reason` bắt buộc, `error` là lỗi máy chủ trả về. */
export interface BoMonState {
  line: DepartmentPurchaseRequestLineOut;
  reason: string;
  error: string | null;
}

export interface DepartmentPurchaseRequestsPageProps {
  eventTick?: number;
  /** Liên thông từ PMH/Phiếu chi: lọc + tô sáng đúng mã YCMH này khi mở trang. */
  focusRequestCode?: string | null;
  /** Liên thông từ Kho: mở form tạo, điền sẵn dòng vật tư (Tên + ĐVT) — bỏ trống SL/ghi chú. */
  seedLines?: DepartmentPurchaseRequestLineInput[] | null;
  seedPurpose?: string | null;
  /** Phần ĐẦU PHIẾU điền sẵn — hiện chỉ Kế hoạch vật tư gửi (20/08/2026).
   *
   *  Bên đó đã biết thừa ngày cần (mốc sớm nhất của các lệnh đã tick) và lệnh nào sinh ra yêu cầu
   *  này; bắt người dùng gõ lại là bắt họ đoán lại một con số máy vừa tính xong. Kho gửi seed
   *  không kèm đầu phiếu thì mọi thứ chạy y như cũ. */
  seedHeader?: {
    source_type?: DepartmentPurchaseSourceType | null;
    needed_date?: string | null;
    related_document_type?: string | null;
    related_document_code?: string | null;
  } | null;
}
