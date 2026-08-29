import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type PayableSupplierRow,
  type PayablesSummary,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import { Button } from "../../../components/Button";
import { Icon } from "../../../components/Icons";
import { money } from "../../../utils/format";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị.
import { useNapTenDonVi } from "../../tenDonVi";
import { AgingStrip } from "../components/AgingStrip";
import { PayablesDrawer } from "./components/PayablesDrawer";
import { PayCell } from "./components/payablesCells";
import { LIST_FILTERS, PAGE_SIZE } from "./shared/constants";
import { kpi } from "./shared/helpers";
import type { Bucket, ListFilter } from "./shared/types";
import "../../accounting.css";
import "../../payables.css";
import "../../purchase.css";

/**
 * CÔNG NỢ PHẢI TRẢ — không có bảng công nợ nào dưới DB.
 *
 * Mọi con số SUY RA từ phiếu mua + phiếu chi. Không ai gõ tay sửa được ⇒ không bao giờ lệch với
 * chứng từ. Muốn một món nợ biến mất chỉ có hai đường: chi tiền, hoặc đóng/huỷ đơn.
 *
 * CÔNG THỨC (chốt 06/08/2026 — docs/prd-mua-hang-cong-no.md §5.3):
 *
 *     công nợ = max(0, giá trị hàng ĐÃ GIAO − đã chi ròng)
 *
 * Ba thay đổi so với bản trước, mỗi cái vá một lỗi có thật:
 *   1. Nợ đo theo **ĐỢT GIAO**, không theo cả đơn. Đơn giao 1/3 đợt trước đây ở `purchased` nên
 *      màn này hiện **0đ** trong khi đã nợ thật — giấu nợ.
 *   2. **Bỏ hẳn rổ "Chờ chi"**: lập phiếu chi = tiền đã ra, không còn khoảng giữa. Vì thế cũng
 *      không còn rổ "chưa vào sổ" — mọi khoản nợ chỉ có một trạng thái: CÒN NỢ.
 *   3. Hạn trả quy về **đợt giao** (`due_date` ?? ngày giao + số ngày cho nợ của NCC), không quy
 *      về phiếu chi nữa.
 *
 * ⚠️ Nhãn "Đã trả" phải GIỐNG NHAU ở cột ngoài bảng và ở khối trong drawer — cùng một con số mà
 * hai tên thì chủ đọc không hiểu là cái gì. Đổi nhãn thì đổi CẢ HAI.
 *
 * ⚠️ LUẬT SỐNG CÒN của màn này: **im lặng không được đồng nghĩa với hết nợ.** Khi tải hỏng thì
 * hiện `—`, KHÔNG hiện `0đ` — 05/08/2026 đã có lần API chết mà màn vẫn đổ ra "0đ / chưa nợ ai",
 * suýt làm chủ tin là đã trả hết.
 */

export function AccountingPayablesPage({
  navigate,
  eventTick = 0,
}: {
  navigate: NavigateFn;
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  // NẠP danh mục đơn vị (một lần/phiên) cho popup "hàng đã nhận" của đợt giao. Thiếu dòng này
  // thì popup in ra MÃ trần — "100 cai" thay vì "100 cái"; `tenDonVi()` đọc từ cache mà cache
  // chỉ được đổ bởi chính hook này. Gọi ở TRANG chứ không ở popup: hook chạy khi popup mở thì
  // lần vẽ đầu vẫn kịp hiện mã trần rồi mới nhảy sang tên.
  useNapTenDonVi();
  // Nút "Lập phiếu chi" trên màn Công nợ ⇒ hỏi quyền của MÀN PHIẾU CHI, không phải màn này.
  const canCreateVoucher = can("phieu_chi", "create");
  const [summary, setSummary] = useState<PayablesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ListFilter>("all");
  // Rổ tuổi đang lọc. `null` = không lọc. Tách khỏi `filter` chứ không gộp: hai bộ lọc này
  // CHỒNG nhau được (vd "vượt hạn mức" + "trễ > 60 ngày"), gộp làm một là mất đúng cái giao đó.
  const [roTuoi, setRoTuoi] = useState<string | null>(null);
  const [page, setPage] = useState(1);
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
      .payables(token, { q: timDaGui, filter, aging: roTuoi, page, size: PAGE_SIZE })
      .then((data) => {
        setSummary(data);
        if (data.page !== page) setPage(data.page);
      })
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
  }, [token, timDaGui, filter, roTuoi, page]);

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

  const rows = summary?.items ?? [];

  const soThang = summary?.period_months ?? 3;

  return (
    <main className="md-page acct-cnt">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán thu mua</p>
        <h1 className="md-page__title">Công nợ phải trả</h1>
        <p className="md-page__sub">
          Nợ tính theo hàng ĐÃ GIAO trừ đi tiền đã chi ròng, gom về từng nhà
          cung cấp. Số liệu suy ra từ đợt giao và phiếu chi — không nhập tay,
          nên không lệch với chứng từ.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error} — các con số bên dưới đang để trống, KHÔNG phải bằng 0.
        </div>
      )}

      {/* Dải pill gộp (~38px) thay 4 thẻ KPI cao — UI_DESIGN §4. Bảng dữ liệu là nội dung thật của
          màn này, không đẩy nó xuống dưới màn hình vì mấy con số đọc mất một giây. */}
      <section className="pay-kpibar" aria-label="Tổng quan công nợ">
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--steel">
            <Icon name="calculator" size={14} />
          </span>
          <b className="pay-kpibar__val">{kpi(summary?.total_due, biet)}</b>
          <span className="pay-kpibar__label">Tổng phải trả</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--danger">
            <Icon name="alert" size={14} />
          </span>
          <b className="pay-kpibar__val pay-kpibar__val--danger">
            {kpi(summary?.overdue_amount, biet)}
          </b>
          <span className="pay-kpibar__label">Quá hạn</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--ok">
            <Icon name="fileCheck" size={14} />
          </span>
          <b className="pay-kpibar__val">{kpi(summary?.paid_in_period, biet)}</b>
          <span className="pay-kpibar__label">Đã trả ({soThang} tháng)</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--warn">
            <Icon name="shield" size={14} />
          </span>
          <b className="pay-kpibar__val">
            {biet ? (summary?.vuot_han_muc_count ?? 0) : "—"}
          </b>
          <span className="pay-kpibar__label">NCC vượt hạn mức</span>
        </div>
      </section>
      {/* DẢI PHÂN TUỔI NỢ — server gom rổ từ lâu nhưng tới 29/08/2026 chưa màn nào vẽ ra, nên
          khoản trễ 3 ngày và khoản trễ 90 ngày cùng nằm trong một ô "Quá hạn". Đặt DƯỚI dải KPI
          và TRÊN thanh công cụ: KPI trả lời "tổng bao nhiêu", dải này trả lời "nặng tới đâu",
          rồi mới tới chỗ lọc/tìm. */}
      <AgingStrip
        buckets={summary?.aging ?? []}
        dangChon={roTuoi}
        onChon={(khoa) => {
          setRoTuoi(khoa);
          setPage(1);
        }}
      />


      <section className="acct-toolbar">
        <form
          className="md-page__search"
          onSubmit={(event) => event.preventDefault()}
        >
          <input
            className="input"
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="Tìm nhà cung cấp (kể cả đã trả hết)..."
          />
        </form>
        <div className="pay-pills">
          {LIST_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pay-pill${filter === item.id ? " pay-pill--on" : ""}`}
              onClick={() => {
                setFilter(item.id);
                setPage(1);
              }}
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
              {/* KHÔNG còn cột "Thao tác": bấm vào DÒNG (hoặc bất kỳ con số nào) mở drawer chi
                  tiết công nợ (24/08/2026 — gộp thao tác vào bản ghi). */}
              <th>Nhà cung cấp</th>
              <th className="acct-count-cell">Đơn còn nợ</th>
              <th className="acct-amount-cell">Còn nợ</th>
              <th className="acct-amount-cell">Quá hạn</th>
              <th className="acct-amount-cell">Đã trả ({soThang} tháng)</th>
              <th className="acct-amount-cell">Hạn mức</th>
              <th className="acct-amount-cell">Vượt hạn mức</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "160px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                </tr>
              ))}
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
                  ) : filter !== "all" ? (
                    "Không có nhà cung cấp nào khớp bộ lọc."
                  ) : (
                    <strong>Không còn nợ nhà cung cấp nào</strong>
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
                  <td className="pay-supplier-cell" title={row.supplier_name}>
                    <strong>{row.supplier_name}</strong>
                    {row.total_due === 0 && row.paid_in_period > 0 && (
                      <small className="pay-ok">Đã trả hết</small>
                    )}
                  </td>
                  {/* Mọi con số bấm được, mở drawer LỌC SẴN đúng rổ đó. */}
                  <td className="acct-count-cell">
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
                      value={row.total_due}
                      row={row}
                      bucket="all"
                      onOpen={setOpen}
                      strong
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
                  {/* Không phải PayCell — Hạn mức không lọc rổ nào, chỉ đọc. */}
                  <td className="acct-amount-cell">
                    {row.credit_limit > 0 ? money(row.credit_limit) : "—"}
                  </td>
                  {/* CẢNH BÁO MỀM (Đ6): số đỏ nói vượt bao nhiêu, không chặn gì cả. Cột riêng
                      thay vì nhét dưới tên NCC — nhét dưới tên làm hàng cao thấp không đều. */}
                  <td className="acct-amount-cell">
                    {row.vuot_han_muc ? (
                      <span className="pay-badge pay-badge--danger">
                        <i className="pay-badge__dot" />
                        {money(row.vuot_bao_nhieu)}
                      </span>
                    ) : (
                      <span className="pay-cell--zero">—</span>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!loading && (
          <div className="md-page__pager">
            <span className="md-page__muted">
              Tổng {summary?.total ?? 0} nhà cung cấp
              {(summary?.pages ?? 1) > 1 ? ` · Trang ${summary?.page}/${summary?.pages}` : ""}
            </span>
            {(summary?.pages ?? 1) > 1 && (
              <div className="md-page__pager-btns">
                <Button variant="ghost" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                  Trước
                </Button>
                <Button
                  variant="ghost"
                  disabled={page >= (summary?.pages ?? 1) || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Sau
                </Button>
              </div>
            )}
          </div>
        )}
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
