// Khối CHỨNG TỪ THAM CHIẾU (số hoá đơn / ngày hoá đơn / số hợp đồng / ghi chú)
// — tách từ pages/PaymentVoucherDialog.tsx.
import type { PaymentVoucherBaseInput } from "../../../../api/client";
import { HOM_NAY } from "../shared/constants";

export function VoucherRefSection({
  form,
  set,
}: {
  form: PaymentVoucherBaseInput;
  set: <K extends keyof PaymentVoucherBaseInput>(
    key: K,
    value: PaymentVoucherBaseInput[K],
  ) => void;
}) {
  return (
    <>
    {/* Khối "Định khoản" ĐÃ BỎ (chủ chốt 12/08/2026): hai ô Nợ / Có bắt kế toán gõ số
        hiệu tài khoản cho từng phiếu, mà hệ thống không hạch toán gì từ chúng — chỉ in ra.
        Cột `debit_account` và `credit_account` GIỮ NGUYÊN trong DB để phiếu cũ in lại vẫn
        đúng; chỉ gỡ ô nhập. */}
    <section className="acct-form-section">
      <h3>Chứng từ tham chiếu</h3>
      <div className="acct-form-grid acct-form-grid--3">
        <label className="acct-field">
          <span>Số hóa đơn</span>
          <input
            className="input"
            value={form.invoice_number ?? ""}
            onChange={(e) => set("invoice_number", e.target.value)}
          />
        </label>
        <label className="acct-field">
          <span>Ngày hóa đơn</span>
          <input
            className="input"
            type="date"
            max={HOM_NAY}
            value={form.invoice_date ?? ""}
            onChange={(e) => set("invoice_date", e.target.value || null)}
          />
        </label>
        <label className="acct-field">
          <span>Số hợp đồng</span>
          <input
            className="input"
            value={form.contract_number ?? ""}
            onChange={(e) => set("contract_number", e.target.value)}
          />
        </label>
      </div>
      <label className="acct-field">
        <span>Ghi chú</span>
        <textarea
          className="input acct-textarea"
          value={form.note ?? ""}
          onChange={(e) => set("note", e.target.value)}
        />
      </label>
    </section>
    </>
  );
}
