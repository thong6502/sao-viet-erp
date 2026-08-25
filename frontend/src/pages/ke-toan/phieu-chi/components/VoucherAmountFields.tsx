// Cụm ô SỐ TIỀN / ĐỢT GIAO / TỶ GIÁ của hộp lập phiếu chi
// (tách từ pages/PaymentVoucherDialog.tsx).
// ⚠️ TIỀN THẬT — trần `maxAmountVnd`, `conNoDot()` và ô quy đổi move nguyên văn.
import type {
  PaymentStage,
  PaymentVoucherBaseInput,
  PaymentVoucherRow,
  PurchaseRequestRow,
} from "../../../../api/client";
import { fmtDate, money } from "../../../../utils/format";
import { HOM_NAY, STAGE_LABELS } from "../shared/constants";
import { conNoDot } from "../shared/helpers";
import type { LoaiPhieu } from "../shared/types";
import type { Dispatch, SetStateAction } from "react";

export function VoucherAmountFields({
  loai,
  coDotGiao,
  form,
  setForm,
  set,
  voucher,
  purchase,
  dotDangChon,
  maxAmountVnd,
  amountVnd,
}: {
  loai: LoaiPhieu;
  coDotGiao: boolean;
  form: PaymentVoucherBaseInput;
  setForm: Dispatch<SetStateAction<PaymentVoucherBaseInput>>;
  set: <K extends keyof PaymentVoucherBaseInput>(
    key: K,
    value: PaymentVoucherBaseInput[K],
  ) => void;
  voucher: PaymentVoucherRow | null;
  purchase: PurchaseRequestRow;
  dotDangChon: PurchaseRequestRow["deliveries"][number] | null;
  maxAmountVnd: number;
  amountVnd: number;
}) {
  return (
    <div className="acct-form-grid acct-form-grid--3">
      {loai === "thanh_toan" && coDotGiao ? (
        <label className="acct-field">
          <span>
            Đợt giao <b>*</b>
          </span>
          <select
            className="input"
            value={form.delivery_id ?? ""}
            disabled={!!voucher}
            onChange={(e) => {
              // Đổi đợt là đổi TRẦN ⇒ điền lại số tiền theo đợt mới. Giữ số cũ là người dùng
              // bấm Lưu với con số của đợt trước rồi ăn lỗi mà không hiểu vì sao.
              const id = e.target.value ? Number(e.target.value) : null;
              setForm((current) => ({
                ...current,
                delivery_id: id,
                amount: conNoDot(purchase, id),
              }));
            }}
          >
            <option value="">Chọn đợt giao</option>
            {purchase.deliveries.map((d) => (
              <option key={d.id} value={d.id}>
                Đợt {d.seq_no} · {fmtDate(d.delivery_date)} ·{" "}
                {d.con_no > 0 ? `còn nợ ${money(d.con_no)}` : "đã trả xong"}
              </option>
            ))}
          </select>
          {dotDangChon && (
            <small>
              Giá trị đợt {money(dotDangChon.amount)} · đã trả{" "}
              {money(dotDangChon.paid_amount)}

              {` · còn nợ ${money(dotDangChon.con_no)}`}
              {dotDangChon.invoice_number
                ? ` · HĐ ${dotDangChon.invoice_number}`
                : " · chưa gán hóa đơn"}
            </small>
          )}
        </label>
      ) : (
        <label className="acct-field">
          <span>Đợt thanh toán</span>
          <select
            className="input"
            value={form.payment_stage}
            disabled={loai === "dat_coc"}
            onChange={(e) =>
              set("payment_stage", e.target.value as PaymentStage)
            }
          >
            {Object.entries(STAGE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="acct-field">
        <span>
          Ngày chứng từ <b>*</b>
        </span>
        {/* Chặn TƯƠNG LAI, KHÔNG chặn quá khứ: hoá đơn về muộn là chuyện thường, phiếu phải
            mang ngày chi tiêu thật mới vào đúng kỳ kế toán. */}
        <input
          className="input"
          type="date"
          max={HOM_NAY}
          value={form.voucher_date}
          onChange={(e) => set("voucher_date", e.target.value)}
        />
      </label>
      {/* Ô "Hạn trả tiền" ĐÃ BỎ (06/08/2026). Phiếu chi là tiền đã ra thì nó không có hạn
          trả; hạn nay thuộc về ĐỢT GIAO (`due_date`, suy từ số ngày cho nợ của NCC), khai ở
          màn Mua hàng. Để lại ô này là đẻ hai nơi khai cùng một thứ. */}
      <label className="acct-field">
        <span>
          Số tiền nguyên tệ <b>*</b>
        </span>
        <input
          className="input acct-money-input"
          type="number"
          min="1"
          step="1"
          value={form.amount}
          onChange={(e) => set("amount", Number(e.target.value))}
        />
        <small>
          Tối đa {maxAmountVnd.toLocaleString("vi-VN")} đ
        </small>
      </label>
      <label className="acct-field">
        <span>
          Loại tiền <b>*</b>
        </span>
        <input
          className="input"
          maxLength={3}
          readOnly={form.voucher_type === "bank_transfer"}
          value={form.currency}
          onChange={(e) => {
            const currency = e.target.value.toUpperCase();
            setForm((current) => ({
              ...current,
              currency,
              exchange_rate:
                currency === "VND" ? 1 : current.exchange_rate,
            }));
          }}
        />
      </label>
      <label className="acct-field">
        <span>
          Tỷ giá VND <b>*</b>
        </span>
        <input
          className="input acct-money-input"
          type="number"
          min="0.000001"
          step="0.000001"
          disabled={form.currency === "VND"}
          value={form.exchange_rate}
          onChange={(e) => set("exchange_rate", Number(e.target.value))}
        />
        <small>Quy đổi: {amountVnd.toLocaleString("vi-VN")} đ</small>
      </label>
    </div>
  );
}
