import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PayableSupplierRow,
  type PayablesDetail,
  type PayablesSummary,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { DetailModal } from "../components/DetailModal";
import { fmtDate, fmtDateTime, money } from "../utils/format";
import "./accounting.css";
import "./payables.css";
import "./purchase.css";
import { Icon } from "../components/Icons";

/**
 * CÔNG NỢ PHẢI TRẢ — không có bảng công nợ nào dưới DB.
 *
 * Mọi con số SUY RA từ phiếu mua + phiếu chi. Không ai gõ tay sửa được ⇒ không bao giờ lệch với
 * chứng từ. Muốn một món nợ biến mất chỉ có hai đường: lập phiếu chi rồi chi, hoặc huỷ đơn.
 *
 * Ba rổ:
 * Một đồng tiền đi qua bốn chặng, mỗi lúc chỉ nằm ở ĐÚNG MỘT cột:
 *   1. Duyệt đơn, chờ hàng   → chưa nằm ở đâu (chưa nợ ai)
 *   2. Hàng về, chưa lập phiếu → 🔴 CHƯA VÀO SỔ
 *   3. Lập phiếu, tiền chưa ra → 🟡 CHỜ CHI
 *   4. Bấm "Đã chi", tiền ra  → ✅ ĐÃ TRẢ
 * Chặng 2 + 3 = "Tổng còn nợ". Chặng 4 = "Đã trả".
 *
 *   🔴 CHƯA VÀO SỔ — hàng đã nhận mà chưa ai lập phiếu chi. Bỏ rổ này là GIẤU NỢ: bảng sạch bong
 *      trong khi vẫn đang nợ NCC.
 *   🟡 CHỜ CHI — đã lập phiếu, tiền chưa ra. Có hạn trả.
 *   ✅ ĐÃ TRẢ — từng LẦN TRẢ, cộng lại đúng bằng cột "Đã trả".
 *
 * ⚠️ Nhãn "Đã trả" phải GIỐNG NHAU ở cột ngoài bảng và ở khối trong drawer. Trước 05/08/2026 ngoài
 * bảng ghi "Đã trả" mà trong drawer ghi "Đã chi trong kỳ" — cùng một con số, hai tên, chủ đọc
 * không hiểu là cái gì. Đổi nhãn thì đổi CẢ HAI.
 *
 * Đơn đã duyệt mà hàng chưa về KHÔNG nằm ở đây — chưa nợ ai.
 *
 * ⚠️ LUẬT SỐNG CÒN của màn này: **im lặng không được đồng nghĩa với hết nợ.** Khi tải hỏng thì
 * hiện `—`, KHÔNG hiện `0đ` — 05/08/2026 đã có lần API chết mà màn vẫn đổ ra "0đ / chưa nợ ai",
 * suýt làm chủ tin là đã trả hết.
 */

/** Rổ đang xem trong drawer. Bấm số nào ngoài bảng thì mở sẵn rổ đó — đỡ một nhịp lọc tay. */
type Bucket = "all" | "unrecorded" | "waiting" | "overdue" | "paid";

const BUCKET_LABEL: Record<Bucket, string> = {
  all: "Tất cả đơn còn nợ",
  unrecorded: "Chưa lập phiếu",
  waiting: "Chờ chi",
  overdue: "Quá hạn",
  paid: "Đã trả",
};

/** Lọc ở BẢNG NGOÀI (khác `Bucket` — cái kia lọc trong drawer). */
type ListFilter = "all" | "overdue" | "due_soon" | "unrecorded";

const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "due_soon", label: "Sắp tới hạn (7 ngày)" },
  { id: "unrecorded", label: "Chưa lập phiếu" },
];

const PAID_PAGE = 10;

/** `—` khi CHƯA BIẾT (đang tải / lỗi), số khi đã tính ra. Đừng bao giờ lẫn hai thứ. */
function kpi(value: number | undefined, biet: boolean): string {
  return biet && value != null ? money(value) : "—";
}

export function AccountingPayablesPage({
  navigate,
  eventTick = 0,
}: {
  navigate: NavigateFn;
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreateVoucher = can("ke_toan", "create");
  const [summary, setSummary] = useState<PayablesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ListFilter>("all");
  const [q, setQ] = useState("");
  const [timDaGui, setTimDaGui] = useState("");
  const [open, setOpen] = useState<{
    row: PayableSupplierRow;
    bucket: Bucket;
  } | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .payables(token, timDaGui)
      .then(setSummary)
      .catch((err) => {
        // Xoá số cũ đi. Giữ lại là để màn hiện số của lần tải trước như thể vừa chốt xong.
        setSummary(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được công nợ phải trả.",
        );
      })
      .finally(() => setLoading(false));
  }, [token, timDaGui]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  // Ô tìm gọi SERVER (không lọc tại chỗ): NCC đã trả hết và im lặng lâu thì không có dòng nào
  // trong danh sách để mà lọc — phải để server lôi họ ra.
  useEffect(() => {
    const t = setTimeout(() => setTimDaGui(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  const biet = !loading && !error && summary != null;

  const rows = useMemo(() => {
    const items = summary?.items ?? [];
    return items.filter((row) => {
      if (filter === "overdue") return row.overdue_amount > 0;
      if (filter === "unrecorded") return row.unrecorded_amount > 0;
      // "Sắp tới hạn" suy từ chi tiết, mà bảng ngoài không có ngày ⇒ ở đây hiểu là CÓ nợ đã vào sổ
      // nhưng chưa quá hạn. Con số ngày cụ thể nằm trong drawer.
      if (filter === "due_soon")
        return row.waiting_amount > 0 && row.overdue_amount === 0;
      return true;
    });
  }, [summary, filter]);

  const soThang = summary?.period_months ?? 3;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán thu mua</p>
        <h1 className="md-page__title">Công nợ phải trả</h1>
        <p className="md-page__sub">
          Tất cả khoản đang nợ nhà cung cấp, gom về một chỗ. Số liệu suy ra từ
          đơn mua hàng và phiếu chi — không nhập tay, nên không lệch với chứng
          từ.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error} — các con số bên dưới đang để trống, KHÔNG phải bằng 0.
        </div>
      )}

      <section className="pay-kpis pay-kpis--4">
        <article className="pay-kpi">
          <span className="pay-kpi__label">Tổng phải trả</span>
          <strong className="pay-kpi__value">
            {kpi(summary?.total_due, biet)}
          </strong>
          <small>
            {biet ? `${rows.length} nhà cung cấp` : "chưa tính được"}
          </small>
        </article>
        <article className="pay-kpi pay-kpi--danger">
          <span className="pay-kpi__label">Quá hạn</span>
          <strong className="pay-kpi__value">
            {kpi(summary?.overdue_amount, biet)}
          </strong>
          <small>đã trễ ngày hẹn trả</small>
        </article>
        <article className="pay-kpi pay-kpi--warn">
          <span className="pay-kpi__label">Chưa tạo phiếu chi</span>
          <strong className="pay-kpi__value">
            {kpi(summary?.unrecorded_amount, biet)}
          </strong>
          <small>hàng đã về, chưa lập phiếu chi</small>
        </article>
        <article className="pay-kpi pay-kpi--ok">
          <span className="pay-kpi__label">Đã trả ({soThang} tháng)</span>
          <strong className="pay-kpi__value">
            {kpi(summary?.paid_in_period, biet)}
          </strong>
          <small>tiền đã rời két</small>
        </article>
      </section>

      <section className="acct-toolbar">
        <form
          className="md-page__search"
          onSubmit={(event) => event.preventDefault()}
        >
          <input
            className="input"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Tìm nhà cung cấp (kể cả đã trả hết)..."
          />
        </form>
        <div className="pay-pills">
          {LIST_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pay-pill${filter === item.id ? " pay-pill--on" : ""}`}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card md-page__tablewrap acct-list">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Nhà cung cấp</th>
              <th className="acct-amount-cell">Đơn còn nợ</th>
              <th className="acct-amount-cell">Chưa vào sổ</th>
              <th className="acct-amount-cell">Chờ chi</th>
              <th className="acct-amount-cell">Quá hạn</th>
              <th className="acct-amount-cell">Đã trả ({soThang} tháng)</th>
              <th className="acct-amount-cell">Tổng còn nợ</th>
              <th className="acct-amount-cell"> Thao tác </th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7}>Đang tải...</td>
              </tr>
            )}
            {error && !loading && (
              <tr>
                <td colSpan={7}>
                  Chưa đọc được số liệu — xem thông báo lỗi ở trên.
                </td>
              </tr>
            )}
            {biet && rows.length === 0 && (
              <tr>
                <td colSpan={7}>
                  {q.trim() ? (
                    <>Không tìm thấy nhà cung cấp nào tên "{q.trim()}".</>
                  ) : summary && summary.items.length > 0 ? (
                    "Không có nhà cung cấp nào khớp bộ lọc."
                  ) : (
                    // Nói THẲNG là đã chốt và chốt lúc nào. Câu cụt "chưa nợ ai" trông y hệt lúc
                    // màn hỏng — mà đó đúng là chuyện đã xảy ra.
                    <>
                      <strong>Không còn nợ nhà cung cấp nào</strong> — chốt lúc{" "}
                      {fmtDateTime(summary?.as_of)}
                    </>
                  )}
                </td>
              </tr>
            )}
            {biet &&
              rows.map((row) => (
                <tr
                  key={row.supplier_id ?? row.supplier_name}
                  onClick={() => setOpen({ row, bucket: "all" })}
                >
                  <td className="acct-supplier-cell" title={row.supplier_name}>
                    <strong>{row.supplier_name}</strong>
                    {row.total_due === 0 && row.paid_in_period > 0 && (
                      <small className="pay-ok">Đã trả hết</small>
                    )}
                  </td>
                  {/* Mọi con số bấm được, mở drawer LỌC SẴN đúng rổ đó. */}
                  <td className="acct-amount-cell">
                    <PayCell
                      value={row.order_count}
                      row={row}
                      bucket="all"
                      onOpen={setOpen}
                      raw
                    />
                  </td>
                  <td className="acct-amount-cell">
                    <PayCell
                      value={row.unrecorded_amount}
                      row={row}
                      bucket="unrecorded"
                      onOpen={setOpen}
                      tone="warn"
                    />
                  </td>
                  <td className="acct-amount-cell">
                    <PayCell
                      value={row.waiting_amount}
                      row={row}
                      bucket="waiting"
                      onOpen={setOpen}
                    />
                  </td>
                  <td className="acct-amount-cell">
                    <PayCell
                      value={row.overdue_amount}
                      row={row}
                      bucket="overdue"
                      onOpen={setOpen}
                      tone="danger"
                    />
                  </td>
                  <td className="acct-amount-cell">
                    <PayCell
                      value={row.paid_in_period}
                      row={row}
                      bucket="paid"
                      onOpen={setOpen}
                      tone="ok"
                    />
                  </td>
                  <td className="acct-amount-cell">
                    <strong>{money(row.total_due)}</strong>
                  </td>

                  <td className="acct-amount-cell">
                    <Icon name="eye" size={17} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>

      {open && open.row.supplier_id != null && (
        <PayablesDrawer
          key={`${open.row.supplier_id}:${open.bucket}`}
          supplierId={open.row.supplier_id}
          supplierName={open.row.supplier_name}
          bucket={open.bucket}
          canCreateVoucher={canCreateVoucher}
          navigate={navigate}
          onClose={() => setOpen(null)}
          onChanged={load}
        />
      )}
    </main>
  );
}

function PayCell({
  value,
  row,
  bucket,
  onOpen,
  tone,
  raw,
}: {
  value: number;
  row: PayableSupplierRow;
  bucket: Bucket;
  onOpen: (next: { row: PayableSupplierRow; bucket: Bucket }) => void;
  tone?: "warn" | "danger" | "ok";
  raw?: boolean;
}) {
  // Số không đọc được (server cũ chưa trả trường này) ⇒ `—`, KHÔNG để `money()` đẻ ra "NaN đ".
  // "—" nghĩa là chưa biết, đúng tinh thần: im lặng không được giả làm số 0.
  if (!Number.isFinite(value) || value <= 0)
    return <span className="pay-cell pay-cell--zero">—</span>;
  return (
    <button
      type="button"
      className={`pay-cell pay-cell--link${tone ? ` pay-cell--${tone}` : ""}`}
      onClick={() => onOpen({ row, bucket })}
      title={`Xem ${BUCKET_LABEL[bucket].toLowerCase()} của ${row.supplier_name}`}
    >
      {raw ? value : money(value)}
    </button>
  );
}

/** Số hoá đơn — thứ phân biệt các ĐỢT GIAO của cùng một đơn. */
function HoaDon({ so, ngay }: { so: string | null; ngay: string | null }) {
  if (!so) return <small className="pay-cell--zero">chưa ghi</small>;
  return (
    <>
      <strong>{so}</strong>
      {ngay && <small>{fmtDate(ngay)}</small>}
    </>
  );
}

function PayablesDrawer({
  supplierId,
  supplierName,
  bucket,
  canCreateVoucher,
  navigate,
  onClose,
  onChanged,
}: {
  supplierId: number;
  supplierName: string;
  bucket: Bucket;
  canCreateVoucher: boolean;
  navigate: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<PayablesDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Bucket>(bucket);
  // Rổ ✅ mặc định THU GỌN. Mở sẵn khi người dùng bấm thẳng vào con số "Đã trả".
  const [paidOpen, setPaidOpen] = useState(bucket === "paid");
  const [paidShown, setPaidShown] = useState(PAID_PAGE);
  // Nới rổ "đã chi" ra toàn bộ lịch sử. NCC trả hết từ 5 tháng trước thì rổ này rỗng theo kỳ —
  // tra ra "không nợ" mà không thấy đã trả những gì. Nới chỉ cho MỘT NCC nên vẫn nhẹ.
  const [xemHetLichSu, setXemHetLichSu] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .payablesDetail(token, supplierId, xemHetLichSu)
      .then(setDetail)
      .catch((err) => {
        setDetail(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được chi tiết công nợ.",
        );
      })
      .finally(() => setLoading(false));
  }, [token, supplierId, xemHetLichSu]);

  const hienDo = tab === "all" || tab === "unrecorded";
  const hienVang = tab === "all" || tab === "waiting" || tab === "overdue";
  const choChi = useMemo(() => {
    const items = detail?.waiting ?? [];
    return tab === "overdue" ? items.filter((x) => x.overdue_days > 0) : items;
  }, [detail, tab]);

  return (
    <DetailModal
      kicker="Công nợ phải trả"
      title={supplierName}
      subtitle={
        detail
          ? `Còn nợ ${money(detail.unrecorded_amount + detail.waiting_amount)} · chốt ngày ${fmtDate(detail.as_of)}`
          : undefined
      }
      onClose={onClose}
      footer={
        <Button variant="ghost" onClick={onClose}>
          Đóng
        </Button>
      }
    >
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      {loading && <p>Đang tải...</p>}

      {/* Chặn TRẮNG TRANG khi backend cũ hơn giao diện: thiếu `paid` là `detail.paid.length` ném
          lỗi và React gỡ nguyên cây, mất cả màn. Báo rõ ra thay vì sập — và cũng không im lặng
          coi như danh sách rỗng, vì rỗng có nghĩa khác hẳn. */}
      {detail && !Array.isArray(detail.paid) && (
        <div className="banner banner--error" role="alert">
          Dữ liệu trả về thiếu phần "đã trả" — máy chủ đang chạy bản cũ hơn giao
          diện. Khởi động lại backend rồi tải lại trang.
        </div>
      )}

      {detail && Array.isArray(detail.paid) && (
        <>
          <div className="pay-pills pay-pills--drawer">
            {(["all", "unrecorded", "waiting", "overdue"] as Bucket[]).map(
              (id) => (
                <button
                  key={id}
                  type="button"
                  className={`pay-pill${tab === id ? " pay-pill--on" : ""}`}
                  onClick={() => setTab(id)}
                >
                  {BUCKET_LABEL[id]}
                </button>
              ),
            )}
          </div>

          {hienDo && (
            <section className="pay-block pay-block--danger">
              <header className="pay-block__head">
                <h3>Hàng đã nhận, chưa lập phiếu</h3>
                <strong>{money(detail.unrecorded_amount)}</strong>
              </header>
              <p className="pay-block__hint">
                Nợ có thật nhưng chưa vào sổ — kế toán chưa lập phiếu chi cho
                phần này.
              </p>
              {detail.unrecorded.length === 0 ? (
                <p className="pay-empty">Không có đơn nào.</p>
              ) : (
                <table className="pay-table">
                  <thead>
                    <tr>
                      <th>Đơn mua hàng</th>
                      <th className="pay-num">Giá trị đơn</th>
                      <th className="pay-num">Thực nhận</th>
                      <th className="pay-num">Còn thiếu phiếu</th>
                      {canCreateVoucher && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.unrecorded.map((row) => (
                      <tr key={row.purchase_request_id}>
                        <td>
                          <strong>{row.code}</strong>
                          {row.expected_receipt_date && (
                            <small>
                              {" "}
                              · hẹn {fmtDate(row.expected_receipt_date)}
                            </small>
                          )}
                        </td>
                        <td className="pay-num">{money(row.total_estimate)}</td>
                        <td className="pay-num">
                          {money(row.received_total)}
                          {row.received_total < row.total_estimate && (
                            <small className="pay-short"> giao thiếu</small>
                          )}
                        </td>
                        <td className="pay-num">
                          <strong>{money(row.amount)}</strong>
                        </td>
                        {canCreateVoucher && (
                          <td className="pay-num">
                            <Button
                              variant="ghost"
                              onClick={() => {
                                onChanged();
                                onClose();
                                navigate("ke-toan-don-mua-hang", {
                                  focusRequestCode: row.code,
                                });
                              }}
                            >
                              Lập phiếu chi
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {hienVang && (
            <section className="pay-block pay-block--warn">
              <header className="pay-block__head">
                <h3>Đã lập phiếu, chờ chi</h3>
                <strong>{money(detail.waiting_amount)}</strong>
              </header>
              <p className="pay-block__hint">
                Nợ đã vào sổ, tiền chưa ra khỏi két. Xác nhận đã chi ở màn Phiếu
                chi.
              </p>
              {choChi.length === 0 ? (
                <p className="pay-empty">Không có phiếu nào.</p>
              ) : (
                <table className="pay-table">
                  <thead>
                    <tr>
                      <th>Phiếu chi</th>
                      <th>Hoá đơn</th>
                      <th>Đơn nguồn</th>
                      <th>Hạn trả</th>
                      <th className="pay-num">Số tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {choChi.map((row) => (
                      <tr key={row.voucher_id}>
                        <td>
                          <strong>{row.doc_no ?? row.code}</strong>
                          {!row.has_attachment && (
                            // CẢNH BÁO, không chặn. Siết cứng khi chưa biết thực tế kẹt bao nhiêu
                            // là dễ tắc việc — chủ xem số liệu thật rồi mới quyết.
                            <small className="pay-warn">chưa có chứng từ</small>
                          )}
                        </td>
                        <td>
                          <HoaDon
                            so={row.invoice_number}
                            ngay={row.invoice_date}
                          />
                        </td>
                        <td>{row.purchase_code}</td>
                        <td>
                          {row.planned_payment_date ? (
                            <>
                              {fmtDate(row.planned_payment_date)}
                              {row.overdue_days > 0 && (
                                <span className="pay-badge pay-badge--danger">
                                  Quá hạn {row.overdue_days} ngày
                                </span>
                              )}
                            </>
                          ) : (
                            // Phiếu cũ lập trước khi hạn trả thành bắt buộc. Không có hạn thì nó
                            // KHÔNG BAO GIỜ vào cột Quá hạn — phải lôi ra, đừng để lặng lẽ.
                            <span className="pay-badge pay-badge--warn">
                              Chưa đặt hạn
                            </span>
                          )}
                        </td>
                        <td className="pay-num">
                          <strong>{money(row.amount)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          <section className="pay-block pay-block--ok">
            <header className="pay-block__head">
              <button
                type="button"
                className="pay-toggle"
                onClick={() => setPaidOpen((v) => !v)}
              >
                {paidOpen ? "▾" : "▸"}{" "}
                {detail.all_history
                  ? "Đã trả — toàn bộ lịch sử"
                  : `Đã trả (${detail.period_months} tháng)`}{" "}
                ({detail.paid.length} lần)
              </button>
              <strong>{money(detail.paid_in_period)}</strong>
            </header>
            {paidOpen &&
              (detail.paid.length === 0 ? (
                <>
                  <p className="pay-empty">
                    {detail.all_history
                      ? "Chưa trả lần nào cho nhà cung cấp này."
                      : `Chưa trả lần nào trong ${detail.period_months} tháng gần nhất.`}
                  </p>
                  {!detail.all_history && (
                    <Button
                      variant="ghost"
                      onClick={() => setXemHetLichSu(true)}
                    >
                      Xem lịch sử cũ hơn
                    </Button>
                  )}
                </>
              ) : (
                <>
                  <p className="pay-block__hint">
                    Tiền đã rời két — từng lần một, cộng lại đúng bằng cột "Đã
                    trả" ngoài bảng. Đặt cạnh sao kê nhà cung cấp là đối chiếu
                    được từng dòng.
                  </p>
                  <table className="pay-table">
                    <thead>
                      <tr>
                        <th>Ngày trả</th>
                        <th>Phiếu chi</th>
                        <th>Hoá đơn</th>
                        <th>Đơn nguồn</th>
                        <th className="pay-num">Số tiền</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.paid.slice(0, paidShown).map((row) => (
                        <tr key={row.voucher_id}>
                          <td>{fmtDate(row.paid_date)}</td>
                          <td>{row.doc_no ?? row.code}</td>
                          <td>
                            <HoaDon
                              so={row.invoice_number}
                              ngay={row.invoice_date}
                            />
                          </td>
                          <td>{row.purchase_code}</td>
                          <td className="pay-num">{money(row.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {detail.paid.length > paidShown && (
                    <Button
                      variant="ghost"
                      onClick={() => setPaidShown((n) => n + PAID_PAGE)}
                    >
                      Xem thêm {detail.paid.length - paidShown} lần trả
                    </Button>
                  )}
                  {!detail.all_history && (
                    <Button
                      variant="ghost"
                      onClick={() => setXemHetLichSu(true)}
                    >
                      Xem lịch sử cũ hơn {detail.period_months} tháng
                    </Button>
                  )}
                </>
              ))}
          </section>
        </>
      )}
    </DetailModal>
  );
}
