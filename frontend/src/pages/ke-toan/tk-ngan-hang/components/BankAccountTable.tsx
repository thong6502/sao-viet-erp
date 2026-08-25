// Bảng danh sách tài khoản ngân hàng (tách từ pages/AccountingBankAccountsPage.tsx).
import { isCompanyAccount } from "../shared/helpers";
import type { AccountRow, AccountTab } from "../shared/types";

export function BankAccountTable({
  tab,
  loading,
  rows,
  canManage,
  openEdit,
}: {
  tab: AccountTab;
  loading: boolean;
  rows: AccountRow[];
  canManage: boolean;
  openEdit: (row: AccountRow) => void;
}) {
  return (
    <section className="card md-page__tablewrap">
      <table className="md-page__table">
        <thead>
          <tr>
            {tab === "supplier" && <th>Nhà cung cấp</th>}
            <th>Chủ tài khoản</th>
            <th>Số tài khoản</th>
            <th>Ngân hàng</th>
            <th>Chi nhánh</th>
            <th>Loại tiền</th>
            {tab === "company" && <th>Mục đích</th>}
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="purchase__skeleton-row">
                <td><div className="purchase__skeleton-bar" style={{ width: "140px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "60px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "70px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
              </tr>
            ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={7}>Chưa có tài khoản ngân hàng.</td>
            </tr>
          )}
          {!loading &&
            rows.map((row) => {
              const company = isCompanyAccount(row) ? row : null;
              return (
                // Bấm cả DÒNG để mở phiếu sửa (thao tác nay nằm TRONG bản ghi, không còn cột
                // "Thao tác" bên ngoài). CHỈ mở cho người có quyền sửa — `save()` không tự
                // chặn quyền nên đừng để người chỉ-xem mở được form. Trạng thái Hoạt
                // động/Ngừng dùng đổi bằng ô tick "Đang hoạt động" ngay trong phiếu rồi Lưu.
                <tr
                  key={`${tab}-${row.id}`}
                  className={canManage ? "acct-clickrow" : undefined}
                  onClick={canManage ? () => openEdit(row) : undefined}
                >
                  {tab === "supplier" && (
                    <td>
                      {"supplier_name" in row ? row.supplier_name : "—"}
                    </td>
                  )}
                  <td>
                    <strong>{row.account_holder}</strong>
                  </td>
                  <td>{row.account_number}</td>
                  <td>{row.bank_name}</td>
                  <td>{row.bank_branch}</td>
                  <td>{row.currency}</td>
                  {tab === "company" && (
                    <td>
                      <div className="acct-purpose-tags">
                        {company?.use_for_receipts && <span>Thu</span>}
                        {company?.use_for_payments && <span>Chi</span>}
                      </div>
                    </td>
                  )}
                  <td>
                    <span
                      className={`acct-voucher-status acct-voucher-status--${
                        row.is_active ? "paid" : "cancelled"
                      }`}
                    >
                      {row.is_active ? "Hoạt động" : "Ngừng dùng"}
                    </span>
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </section>
  );
}
