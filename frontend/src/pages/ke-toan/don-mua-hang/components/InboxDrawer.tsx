// Drawer CHI TIẾT đơn mua hàng (Kế toán) — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type {
  PaymentVoucherRow,
  PurchaseRequestRow,
  SupplierCredit,
} from "../../../../api/client";
import { CodeLink } from "../../../../components/CodeLink";
import { PurchaseActivityTimeline } from "../../../../components/PurchaseActivityTimeline";
import { fmtDate, money } from "../../../../utils/format";
import {
  PAYMENT_STAGE_LABEL,
  STATUS_META,
  VOUCHER_STATUS_LABEL,
  VOUCHER_TYPE_LABEL,
} from "../shared/constants";

export function InboxDrawer({
  selected,
  setSelectedId,
  vouchers,
  vouchersLoading,
  credit,
  openYcmh,
  actions,
}: {
  selected: PurchaseRequestRow;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  vouchers: PaymentVoucherRow[];
  vouchersLoading: boolean;
  credit: SupplierCredit | null;
  openYcmh: (code: string) => void;
  actions: (row: PurchaseRequestRow, compact?: boolean) => ReactNode;
}) {
  // Tính trước để chân drawer bỏ hẳn khung `.purchase__drawer-footer` khi không có thao tác
  // nào khả dụng (thay vì render khung rỗng chiếm ~57px vô ích).
  const footer = actions(selected);
  return (
    <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
      <aside
        className="rc-drawer purchase__drawer-780 acct-dmh-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={selected.code}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Chi tiết đơn</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{selected.code}</h2>
                <span
                  className={`acct-dmh__state acct-dmh__state--${STATUS_META[selected.status].tone}`}
                >
                  <i className="acct-dmh__dot" />
                  {STATUS_META[selected.status].label}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={() => setSelectedId(null)}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
        </div>
        <div className="rc-drawer__body acct-dmh__body">
      {/* Nhắc TRƯỚC khi bấm Duyệt, nhưng không khoá nút — người duyệt cầm số liệu rồi tự
          quyết. Chỉ hiện khi NCC thật sự đã vượt: bày cả lúc bình thường là nhiễu. */}
      {credit?.vuot_han_muc && (
        <div className="banner banner--warn" role="status">
          Đang nợ nhà cung cấp {money(credit.no_hien_tai)} — vượt hạn
          mức {money(credit.credit_limit)} là{" "}
          <strong>{money(credit.vuot_bao_nhieu)}</strong>. Đây là cảnh báo,
          không chặn duyệt.
        </div>
      )}
      <dl className="purchase__facts">
        <div>
          <dt>Nhà cung cấp</dt>
          <dd>{selected.supplier_name}</dd>
        </div>
        <div>
          <dt>Ngày cần hàng</dt>
          <dd>{fmtDate(selected.needed_date)}</dd>
        </div>
        <div>
          <dt>Người lập</dt>
          <dd>{selected.created_by_name || "—"}</dd>
        </div>
        <div>
          <dt>Gửi duyệt</dt>
          <dd>{fmtDate(selected.submitted_at)}</dd>
        </div>
        <div>
          <dt>Yêu cầu nguồn</dt>
          <dd>
            {selected.sources.map((source, index) => (
              <span key={source.id}>
                {index > 0 && ", "}
                <CodeLink code={source.code} onOpen={openYcmh} />
              </span>
            ))}
          </dd>
        </div>
        <div>
          <dt>Phòng ban nguồn</dt>
          <dd>
            {[
              ...new Set(
                selected.sources
                  .map((source) => source.requesting_department_name)
                  .filter(Boolean),
              ),
            ].join(", ") || "—"}
          </dd>
        </div>
      </dl>
      <div className="acct-purpose">
        <span>Nội dung / mục đích</span>
        <strong>
          {selected.content?.trim() ||
            [selected.purpose, selected.note]
              .map((x) => (x ?? "").trim())
              .filter(Boolean)
              .join(" — ") ||
            "—"}
        </strong>
      </div>
      {selected.reject_reason && (
        <div className="purchase__note purchase__note--reject">
          <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
        </div>
      )}
      <table className="md-page__table purchase__lines-table">
        <thead>
          <tr>
            <th>Vật tư</th>
            <th className="num">Số lượng</th>
            <th className="num">VAT</th>
            <th className="num">Thành tiền</th>
          </tr>
        </thead>
        <tbody>
          {selected.lines.map((line) => (
            <tr key={line.id}>
              <td>
                <strong>{line.item_name}</strong>
              </td>
              <td className="num">
                {line.quantity.toLocaleString("vi-VN")} {line.unit}
              </td>
              <td className="num">{line.vat_percent}%</td>
              <td className="num">
                <strong>{money(line.line_total)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* Bốn con số theo đúng công thức mới: nợ = HÀNG ĐÃ VỀ − đã chi ròng. "Đang chờ chi" đã
          bỏ (không còn phiếu chờ chi), thay bằng "Hàng đã giao" — số thật sự đẻ ra công nợ. */}
      <div className="acct-payment-grid">
        <div>
          <span>Tổng đơn</span>
          <strong>{money(selected.total_estimate)}</strong>
        </div>
        <div>
          <span>Hàng đã giao</span>
          <strong>{money(selected.gia_tri_da_giao)}</strong>
        </div>
        <div>
          <span>Đã chi ròng</span>
          <strong>{money(selected.net_paid)}</strong>
        </div>
        <div className="acct-dmh__lead">
          <span>Còn nợ</span>
          <strong>{money(selected.outstanding_amount)}</strong>
        </div>
      </div>
      {/* Hợp đồng + CỌC DỰ KIẾN — kế toán phải thấy ở đây, vì đây là màn họ lập phiếu chi.
          Thiếu nó thì thu mua khai cọc bên Mua hàng mà kế toán không hề biết, rồi lập phiếu
          cọc bằng một số tự nghĩ ra. Chỉ ĐỌC: cọc là con số người duyệt đã đồng ý. */}
      {(selected.contract_number || selected.deposit_expected > 0) && (
        <dl className="purchase__facts acct-contract-facts">
          {selected.contract_number && (
            <div>
              <dt>Số hợp đồng</dt>
              <dd>{selected.contract_number}</dd>
            </div>
          )}
          {selected.deposit_expected > 0 && (
            <div>
              <dt>Cọc dự kiến</dt>
              <dd>
                <strong>{money(selected.deposit_expected)}</strong>
                <small> — điền sẵn khi lập phiếu Đặt cọc</small>
              </dd>
            </div>
          )}
        </dl>
      )}
      <section className="acct-deliveries">
        <p className="eyebrow">Đợt giao hàng</p>
        {selected.deliveries.length === 0 ? (
          <div className="md-page__muted">Chưa có đợt giao nào.</div>
        ) : (
          <div className="acct-dmh__scroll">
            <table className="md-page__table acct-deliveries__table">
              <thead>
                <tr>
                  <th>Đợt</th>
                  <th>Ngày giao</th>
                  <th>Hàng đã nhận</th>
                  <th>Hạn thanh toán</th>
                  <th className="acct-amount-cell">Giá trị</th>
                  <th className="acct-amount-cell">Đã chi</th>
                  <th className="acct-amount-cell">Còn nợ</th>
                  <th>Người ghi</th>
                </tr>
              </thead>
              <tbody>
                {selected.deliveries.map((dot) => (
                  <tr key={dot.id}>
                    <td>Đợt {dot.seq_no}</td>
                    <td>{fmtDate(dot.delivery_date)}</td>
                    <td>
                      <div className="acct-deliveries__lines">
                        {dot.lines.map((line) => (
                          <span key={line.id}>
                            <strong>{line.item_name}</strong>
                            {": "}
                            {line.quantity.toLocaleString("vi-VN")} {line.unit}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{dot.chua_dat_han ? "Chưa đặt hạn" : fmtDate(dot.due_date)}</td>
                    <td className="acct-amount-cell">{money(dot.amount)}</td>
                    <td className="acct-amount-cell">{money(dot.paid_amount)}</td>
                    <td className="acct-amount-cell">{money(dot.con_no)}</td>
                    <td>
                      {dot.created_by_name || "—"}
                      {dot.created_at && (
                        <small>{fmtDate(dot.created_at)}</small>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="acct-vouchers">
        <p className="eyebrow">Chứng từ chi / UNC</p>
        {vouchersLoading ? (
          <div className="md-page__muted">Đang tải chứng từ...</div>
        ) : vouchers.length === 0 ? (
          <div className="md-page__muted">Chưa lập chứng từ chi nào.</div>
        ) : (
          <div className="acct-dmh__scroll">
            <table className="md-page__table acct-vouchers__table">
              <thead>
                <tr>
                  <th>Mã chứng từ</th>
                  <th>Loại</th>
                  <th>Đợt thanh toán</th>
                  <th>Ngày chứng từ</th>
                  <th className="acct-amount-cell">Số tiền</th>
                  <th>Trạng thái</th>
                  <th>Người lập / chi</th>
                </tr>
              </thead>
              <tbody>
                {vouchers.map((voucher) => (
                  <tr key={voucher.id}>
                    <td className="acct-code-cell">
                      <strong>{voucher.code}</strong>
                      {voucher.delivery_seq_no && (
                        <small>Đợt giao {voucher.delivery_seq_no}</small>
                      )}
                    </td>
                    <td>{VOUCHER_TYPE_LABEL[voucher.voucher_type]}</td>
                    <td>{PAYMENT_STAGE_LABEL[voucher.payment_stage]}</td>
                    <td>{fmtDate(voucher.voucher_date)}</td>
                    <td className="acct-amount-cell">
                      {money(voucher.amount_vnd)}
                    </td>
                    <td>
                      <span
                        className={`acct-dmh__state acct-dmh__state--${voucher.status}`}
                      >
                        <i className="acct-dmh__dot" />
                        {VOUCHER_STATUS_LABEL[voucher.status]}
                      </span>
                    </td>
                    <td>
                      {voucher.created_by_name || "—"}
                      <small>
                        {fmtDate(voucher.created_at)}
                        {voucher.paid_by_name
                          ? ` · Chi bởi ${voucher.paid_by_name}`
                          : ""}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="acct-history">
        <p className="eyebrow">Lịch sử đơn mua hàng</p>
        <PurchaseActivityTimeline items={selected.activity_history} />
      </section>
        </div>
        {footer && <div className="purchase__drawer-footer">{footer}</div>}
      </aside>
    </div>
  );
}
