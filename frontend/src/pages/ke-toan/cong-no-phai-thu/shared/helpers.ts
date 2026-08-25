// Hàm dùng chung của màn Công nợ phải thu (tách từ pages/AccountingReceivablesPage.tsx).
import { money } from "../../../../utils/format";

export function kpi(value: number | undefined, known: boolean): string {
  return known && value != null ? money(value) : "—";
}

export function methodText(value: string): string {
  return value === "bank_transfer" ? "Chuyển khoản" : "Tiền mặt";
}

export function localToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}
