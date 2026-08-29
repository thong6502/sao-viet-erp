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
// Đơn vị lưu bằng MÃ (`cai`, `to`, `m2`); tên hiển thị ("cái", "tờ", "m²") nằm ở danh mục Đơn vị.
// `?? line.unit` cố ý: danh mục chưa nạp xong hoặc mã lạ thì hiện MÃ TRẦN, thà thấy `cai` còn hơn
// nuốt mất đơn vị của một con số lượng hàng. Xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
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
      {/* ĐIỀU KIỆN THANH TOÁN VỚI NCC — khối RIÊNG, cố ý không nhét vào `purchase__facts` ngay
          dưới (chủ chốt 28/08/2026: *"thiết kế hiển thị sao cho đẹp chứ đừng nhét bừa"*).
          Bảng đó gồm 6 mục nói về ĐƠN NÀY (ngày cần hàng, người lập, gửi duyệt, yêu cầu nguồn…);
          ba số ở đây nói về NHÀ CUNG CẤP. Trộn vào là "Hạn mức nợ" đứng ngang hàng "Người lập",
          thành một danh sách 9 dòng phẳng lì không có chỗ cho mắt dừng.

          "Đang nợ" được thêm dù chủ chốt chỉ xin ba trường: "hạn mức 100 triệu" đứng một mình là
          con số chết, câu kế toán thật sự đang hỏi trước nút Duyệt là *còn được nợ bao nhiêu
          nữa*. Số đó server đã tính sẵn (`no_hien_tai`), trước chỉ lôi ra khi vượt hạn mức.
          (Thanh đo % hạn mức đã dựng rồi bỏ theo yêu cầu — đừng dựng lại.) */}
      {credit && (
        <section className="acct-terms">
          <header className="acct-terms__head">
            <span>Điều kiện thanh toán</span>
            <strong>{selected.supplier_name || "—"}</strong>
          </header>
          <div className="acct-terms__row">
            <span>Điều khoản</span>
            <strong className={credit.payment_terms ? "" : "acct-terms__trong"}>
              {credit.payment_terms?.trim() || "Chưa khai"}
            </strong>
          </div>
          <div className="acct-terms__grid">
            <div>
              <span>Cho nợ</span>
              {/* BA ca khác hẳn nhau: chưa khai · 0 = trả ngay · N ngày. Ép `null` thành 0 là
                  biến "chưa đặt hạn" thành "phải trả ngay hôm nay". */}
              <strong className={credit.credit_days == null ? "acct-terms__trong" : ""}>
                {credit.credit_days == null
                  ? "Chưa đặt hạn"
                  : credit.credit_days === 0
                    ? "Trả ngay"
                    : `${credit.credit_days} ngày`}
              </strong>
            </div>
            <div>
              <span>Hạn mức</span>
              {/* 0 = KHÔNG đặt hạn mức (mọi NCC cũ đều để 0), không phải "hạn mức 0đ". */}
              <strong className={credit.credit_limit > 0 ? "" : "acct-terms__trong"}>
                {credit.credit_limit > 0 ? money(credit.credit_limit) : "Không đặt"}
              </strong>
            </div>
            <div>
              <span>Đang nợ</span>
              <strong className={credit.vuot_han_muc ? "acct-terms__vuot" : ""}>
                {money(credit.no_hien_tai)}
              </strong>
            </div>
          </div>
        </section>
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
                {line.quantity.toLocaleString("vi-VN")} {tenDonVi(line.unit) ?? line.unit}
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
                  {/* Ngày giao gộp vào ô "Đợt" thành dòng phụ (đúng lối `acct-code-cell` dùng khắp
                      các bảng kế toán): số đợt và ngày của chính nó là MỘT thứ, mà tách ra thì
                      riêng tiêu đề "NGÀY GIAO" đã ăn hơn 100px của một bảng đang phải cuộn ngang. */}
                  <th>Đợt</th>
                  <th>Hàng đã nhận</th>
                  {/* "Hạn trả" — cùng chữ với bảng đợt giao bên Thu mua và cột Hạn trả bên Công
                      nợ phải trả. "Hạn thanh toán" cũ dài gấp đôi, một mình nó ăn 140px trong khi
                      nội dung chỉ là một ngày. */}
                  <th>Hạn trả</th>
                  <th className="acct-amount-cell">Giá trị</th>
                  <th className="acct-amount-cell">Đã chi</th>
                  {/* TRỪ CỌC — thiếu cột này thì đợt được cọc bù đọc ra vô lý: giá trị 3.400.000,
                      đã chi 0, mà còn nợ 0. Cọc là tiền chi cho CẢ ĐƠN nên không nằm ở "Đã chi"
                      của đợt nào; phải có cột riêng thì phép trừ mới hiện ra.
                      Cùng bộ cột với bảng đợt giao bên Thu mua và khối "Đợt giao còn nợ" bên Công
                      nợ phải trả — ba màn nói về CÙNG một đợt, lệch cột là lệch cách đọc. */}
                  <th className="acct-amount-cell">Trừ cọc</th>
                  <th className="acct-amount-cell">Còn nợ</th>
                  <th>Người ghi</th>
                </tr>
              </thead>
              <tbody>
                {selected.deliveries.map((dot) => (
                  <tr key={dot.id}>
                    <td className="acct-code-cell">
                      <strong>Đợt {dot.seq_no}</strong>
                      <small>{fmtDate(dot.delivery_date)}</small>
                    </td>
                    <td>
                      <div className="acct-deliveries__lines">
                        {dot.lines.map((line) => (
                          <span key={line.id}>
                            <strong>{line.item_name}</strong>
                            {": "}
                            {line.quantity.toLocaleString("vi-VN")}{" "}
                            {tenDonVi(line.unit) ?? line.unit}
                            {/* PHẦN DƯ — nhận nhiều hơn số đặt nên tính 0đ (28/08/2026). Kế toán
                                PHẢI thấy con số này: đây là màn quyết chi, mà "thành tiền" bên
                                cạnh đã trừ phần dư ra rồi. Không hiện thì hoá đơn NCC ghi 700 cái
                                còn hệ ghi 200 cái, không ai giải thích nổi vênh ở đâu. */}
                            {line.quantity_du > 0 && (
                              <em
                                className="pdot__du"
                                title={`${line.quantity_tinh_tien.toLocaleString("vi-VN")} tính tiền · ${line.quantity_du.toLocaleString("vi-VN")} vượt số đặt, giá 0đ`}
                              >
                                {" · "}
                                {line.quantity_du.toLocaleString("vi-VN")} dư
                              </em>
                            )}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{dot.chua_dat_han ? "Chưa đặt hạn" : fmtDate(dot.due_date)}</td>
                    <td className="acct-amount-cell">{money(dot.amount)}</td>
                    {/* 0 đ ở ba cột liền nhau là ba con số không mang tin, át mất cột phải đọc.
                        Gạch mờ = "chưa có gì ở đây". */}
                    <td className="acct-amount-cell">
                      {dot.paid_amount > 0 ? money(dot.paid_amount) : <span className="pay-cell--zero">—</span>}
                    </td>
                    <td className="acct-amount-cell">
                      {dot.coc_bu > 0 ? money(dot.coc_bu) : <span className="pay-cell--zero">—</span>}
                    </td>
                    <td className="acct-amount-cell">
                      {dot.con_no > 0 ? (
                        <strong>{money(dot.con_no)}</strong>
                      ) : (
                        <span className="pay-cell--zero">xong</span>
                      )}
                    </td>
                    {/* Tên dài ("Hồ Thị Minh Châu") trước đây vỡ làm 3 dòng, thổi chiều cao cả
                        hàng lên gấp đôi. Cắt bằng "…" + tooltip: đây là cột tra cứu, không phải
                        cột phải đọc trọn từng ký tự. */}
                    <td className="acct-user-cell">
                      <div title={dot.created_by_name ?? undefined}>
                        {dot.created_by_name || "—"}
                      </div>
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
