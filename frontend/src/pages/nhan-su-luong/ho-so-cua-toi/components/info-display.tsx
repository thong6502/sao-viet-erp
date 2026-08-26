// Dòng khoá–giá trị + chip "HCNS quản lý" của màn "Hồ sơ của tôi"
// (tách từ pages/HoSoCuaToiPage.tsx).
import { Icon } from "../../../../components/Icons";

export function Row({ k, v, rong = "Chưa khai", hint }: {
  k: string; v: string | null | undefined; rong?: string; hint?: string;
}) {
  const co = v !== null && v !== undefined && v !== "";
  return (
    <div className="ns-kv">
      <span className="ns-kv__k">{k}</span>
      <span className="ns-kv__v">
        <span className={co ? undefined : "mine__kv--empty"}>
          {!co && <Icon name="alert" size={11} />}
          {co ? v : rong}
        </span>
        {hint && <span className="mine__kv-hint">{hint}</span>}
      </span>
    </div>
  );
}

/** Chip khoá cạnh tiêu đề khối do HCNS quản — bấm là mở thẳng form đề nghị. Đặt ngay cạnh
 *  field bị khoá nên không cần thêm link "Cần đổi tên?" ở hero nữa. */
export function LockChip({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button" className="mine__lockchip" onClick={onClick}
      title="Mục này do HCNS quản lý. Bấm để gửi đề nghị sửa."
      aria-label="Mục này do HCNS quản lý. Bấm để gửi đề nghị sửa."
    >
      <Icon name="lock" size={11} /> HCNS quản lý
    </button>
  );
}
