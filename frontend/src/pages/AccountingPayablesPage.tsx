import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PayableItemRow,
  type PayableSupplierRow,
  type PayablesDetail,
  type PayablesSummary,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { fmtDate, fmtDateTime, money } from "../utils/format";
import "./accounting.css";
import "./payables.css";
import "./purchase.css";

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

/** Rổ đang xem trong drawer. Bấm số nào ngoài bảng thì mở sẵn rổ đó — đỡ một nhịp lọc tay. */
type Bucket = "all" | "overdue" | "paid";

const BUCKET_LABEL: Record<Bucket, string> = {
  all: "Tất cả đợt còn nợ",
  overdue: "Quá hạn",
  paid: "Đã trả",
};

/** Lọc ở BẢNG NGOÀI (khác `Bucket` — cái kia lọc trong drawer). */
type ListFilter = "all" | "overdue" | "chua_han" | "vuot_han_muc";

const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "chua_han", label: "Chưa tới hạn" },
  { id: "vuot_han_muc", label: "Vượt hạn mức" },
];

const PAID_PAGE = 10;

/** `—` khi CHƯA BIẾT (đang tải / lỗi), số khi đã tính ra. Đừng bao giờ lẫn hai thứ. */
function kpi(value: number | undefined, biet: boolean): string {
  return biet && value != null ? money(value) : "—";
}

/** Nhãn một khoản nợ trong phạm vi MỘT đơn: "Đợt 2", hoặc "Cả đơn" với đơn cũ không theo đợt. */
function tenKhoan(row: PayableItemRow): string {
  return row.seq_no != null ? `Đợt ${row.seq_no}` : "Cả đơn";
}

/** Gom các khoản nợ theo ĐƠN MUA, giữ nguyên thứ tự server đã sắp (hạn trả, chưa-có-hạn lên đầu).
 *
 *  Vì sao phải gom (chủ 07/08/2026): đổ phẳng mọi đợt của mọi PMH vào một bảng thì có 3 đơn là ba
 *  nhóm đợt trộn lẫn, và dòng "Đặt cọc cho cả đơn" ở dưới gộp cọc của cả ba — ghi "cả đơn" mà liệt
 *  kê ba mã, không ai biết cọc nào của đơn nào. Gom lại thì mỗi đơn tự mang cọc của chính nó. */
function gomTheoDon(items: PayableItemRow[], cocs: PayablesDetail["coc_chung"]) {
  const cocTheoDon = new Map(cocs.map((c) => [c.purchase_request_id, c]));
  const nhom = new Map<
    number,
    { code: string; items: PayableItemRow[]; coc: PayablesDetail["coc_chung"][number] | null }
  >();
  for (const row of items) {
    let g = nhom.get(row.purchase_request_id);
    if (!g) {
      g = {
        code: row.code,
        items: [],
        coc: cocTheoDon.get(row.purchase_request_id) ?? null,
      };
      nhom.set(row.purchase_request_id, g);
    }
    g.items.push(row);
  }
  return [...nhom.entries()].map(([id, g]) => ({
    purchase_request_id: id,
    ...g,
    con_no: g.items.reduce((sum, r) => sum + r.con_no, 0),
  }));
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
  // Nút "Lập phiếu chi" trên màn Công nợ ⇒ hỏi quyền của MÀN PHIẾU CHI, không phải màn này.
  const canCreateVoucher = can("phieu_chi", "create");
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
      if (filter === "chua_han") return row.no_han_amount > 0;
      if (filter === "vuot_han_muc") return row.vuot_han_muc;
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
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__label">
            {biet ? `chốt ${fmtDateTime(summary?.as_of)}` : "chưa chốt được"}
          </span>
        </div>
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
              <th className="acct-amount-cell">Còn nợ</th>
              <th className="acct-amount-cell">Quá hạn</th>
              <th className="acct-amount-cell">Đã trả ({soThang} tháng)</th>
              <th className="acct-amount-cell">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6}>Đang tải...</td>
              </tr>
            )}
            {error && !loading && (
              <tr>
                <td colSpan={6}>
                  Chưa đọc được số liệu — xem thông báo lỗi ở trên.
                </td>
              </tr>
            )}
            {biet && rows.length === 0 && (
              <tr>
                <td colSpan={6}>
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
                  {/* Class RIÊNG, không mượn `.acct-supplier-cell`: ô đó `nowrap` + cắt ở 200px
                      nên pill "Vượt hạn mức" sẽ bị xén mất. Viết class mới thay vì đè lại — bẫy
                      cascade ở UI_DESIGN §10. */}
                  <td className="pay-supplier-cell" title={row.supplier_name}>
                    <strong>{row.supplier_name}</strong>
                    {/* CẢNH BÁO MỀM (Đ6): pill đỏ nói vượt bao nhiêu, không chặn gì cả. */}
                    {row.vuot_han_muc && (
                      <span className="pay-badge pay-badge--danger">
                        Vượt hạn mức {money(row.vuot_bao_nhieu)}
                      </span>
                    )}
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
  strong,
}: {
  value: number;
  row: PayableSupplierRow;
  bucket: Bucket;
  onOpen: (next: { row: PayableSupplierRow; bucket: Bucket }) => void;
  tone?: "warn" | "danger" | "ok";
  raw?: boolean;
  strong?: boolean;
}) {
  // Số không đọc được (server cũ chưa trả trường này) ⇒ `—`, KHÔNG để `money()` đẻ ra "NaN đ".
  // "—" nghĩa là chưa biết, đúng tinh thần: im lặng không được giả làm số 0.
  if (!Number.isFinite(value) || value <= 0)
    return <span className="pay-cell pay-cell--zero">—</span>;
  return (
    <button
      type="button"
      className={`pay-cell pay-cell--link${tone ? ` pay-cell--${tone}` : ""}${
        strong ? " pay-cell--strong" : ""
      }`}
      onClick={() => onOpen({ row, bucket })}
      title={`Xem ${BUCKET_LABEL[bucket].toLowerCase()} của ${row.supplier_name}`}
    >
      {raw ? value : money(value)}
    </button>
  );
}

/** Số hoá đơn — nhiều đợt cùng số nghĩa là cùng MỘT hoá đơn. */
function HoaDon({ so, ngay }: { so: string | null; ngay?: string | null }) {
  if (!so) return <small className="pay-cell--zero">chưa ghi</small>;
  return (
    <>
      <strong>{so}</strong>
      {ngay && <small> {fmtDate(ngay)}</small>}
    </>
  );
}

/** Hạn trả của MỘT đợt giao + mức khẩn. Đợt chưa có hạn không bao giờ vào cột Quá hạn nên phải
 *  đeo badge — nó đã được server đẩy lên đầu danh sách, đây là nửa còn lại của việc chống giấu nợ. */
function HanTra({ row }: { row: PayableItemRow }) {
  if (row.chua_dat_han) {
    return (
      <span className="pay-badge pay-badge--warn">
        {row.delivery_id == null ? "Đơn không theo đợt" : "Chưa đặt hạn"}
      </span>
    );
  }
  return (
    <>
      {fmtDate(row.due_date)}
      {row.overdue_days > 0 && (
        <span className="pay-badge pay-badge--danger">
          Quá hạn {row.overdue_days} ngày
        </span>
      )}
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

  const hienNo = tab === "all" || tab === "overdue";
  const khoanNo = useMemo(() => {
    const items = detail?.items ?? [];
    return tab === "overdue" ? items.filter((x) => x.overdue_days > 0) : items;
  }, [detail, tab]);
  // Server đã sắp: đợt chưa có hạn lên ĐẦU, còn lại theo hạn trả tăng dần. Không sắp lại ở đây —
  // sắp hai nơi là hai nơi lệch nhau.
  const chuaDatHan = useMemo(
    () => (detail?.items ?? []).filter((x) => x.chua_dat_han).length,
    [detail],
  );
  const conDuocNo = detail
    ? Math.max(0, detail.credit_limit - detail.total_due)
    : 0;

  return (
    <DetailModal
      kicker="Công nợ phải trả"
      title={supplierName}
      subtitle={
        detail
          ? `Còn nợ ${money(detail.total_due)} · chốt ngày ${fmtDate(detail.as_of)}`
          : undefined
      }
      badge={
        detail?.vuot_han_muc ? (
          <span className="pay-badge pay-badge--danger">
            Vượt hạn mức {money(detail.vuot_bao_nhieu)}
          </span>
        ) : undefined
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

      {/* Chặn TRẮNG TRANG khi backend cũ hơn giao diện: thiếu `items`/`paid` là `.length` ném lỗi
          và React gỡ nguyên cây, mất cả màn. Báo rõ ra thay vì sập — và cũng không im lặng coi như
          danh sách rỗng, vì rỗng có nghĩa khác hẳn. */}
      {detail && !(Array.isArray(detail.items) && Array.isArray(detail.paid)) && (
        <div className="banner banner--error" role="alert">
          Dữ liệu trả về thiếu phần công nợ theo đợt giao — máy chủ đang chạy
          bản cũ hơn giao diện. Khởi động lại backend rồi tải lại trang.
        </div>
      )}

      {detail && Array.isArray(detail.items) && Array.isArray(detail.paid) && (
        <>
          {/* HẠN MỨC đứng trên cùng: đây là khung để đọc mọi con số bên dưới. Chưa đặt hạn mức thì
              nói thẳng "chưa đặt", đừng hiện 0đ — 0 trông như "hạn mức bằng không". */}
          <dl className="pay-credit">
            <div>
              <dt>Hạn mức công nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(detail.credit_limit)
                ) : (
                  <span className="pay-cell--zero">Chưa đặt</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Đang nợ</dt>
              <dd className={detail.vuot_han_muc ? "pay-cell--danger" : ""}>
                {money(detail.total_due)}
              </dd>
            </div>
            <div>
              <dt>Còn được nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(conDuocNo)
                ) : (
                  <span className="pay-cell--zero">Không giới hạn</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Số ngày cho nợ</dt>
              <dd>
                {/* 0 và "chưa đặt" là HAI ca khác hẳn — gộp là hiểu sai cả cột Quá hạn. */}
                {detail.credit_days == null ? (
                  <span className="pay-cell--zero">Chưa đặt</span>
                ) : detail.credit_days === 0 ? (
                  "Trả ngay"
                ) : (
                  `${detail.credit_days} ngày`
                )}
              </dd>
            </div>
          </dl>

          <div className="pay-pills pay-pills--drawer">
            {(["all", "overdue"] as Bucket[]).map((id) => (
              <button
                key={id}
                type="button"
                className={`pay-pill${tab === id ? " pay-pill--on" : ""}`}
                onClick={() => setTab(id)}
              >
                {BUCKET_LABEL[id]}
              </button>
            ))}
          </div>

          {hienNo && (
            <section className="pay-block pay-block--danger">
              <header className="pay-block__head">
                <h3>Đợt giao còn nợ</h3>
                <strong>
                  {money(
                    tab === "overdue"
                      ? detail.overdue_amount
                      : detail.total_due,
                  )}
                </strong>
              </header>
              <p className="pay-block__hint">
                Hàng đã về tới đâu thì nợ tới đó, gom theo từng đơn mua. Cột{" "}
                <strong>Đã trả</strong> chỉ đếm tiền trả{" "}
                <strong>đích danh đợt đó</strong> (khớp sao kê nhà cung cấp).{" "}
                <strong>Còn nợ</strong> đã trừ cả tiền cọc của đơn — nên có đợt
                chưa trả đồng nào mà còn nợ vẫn nhỏ hơn giá trị đợt.
                {chuaDatHan > 0 && (
                  <>
                    {" "}
                    Có <strong>{chuaDatHan} khoản chưa có hạn trả</strong> —
                    chúng không bao giờ vào cột Quá hạn nên được đẩy lên đầu;
                    khai "Số ngày cho nợ" ở hồ sơ nhà cung cấp để hết ca này.
                  </>
                )}
              </p>
              {khoanNo.length === 0 ? (
                <p className="pay-empty">
                  {tab === "overdue"
                    ? "Không có khoản nào quá hạn."
                    : "Không còn khoản nợ nào với nhà cung cấp này."}
                </p>
              ) : (
                gomTheoDon(khoanNo, detail.coc_chung).map((don) => (
                  <div className="pay-don" key={don.purchase_request_id}>
                    <div className="pay-don__head">
                      <strong className="pay-don__code">{don.code}</strong>
                      {don.coc && don.coc.amount > 0 && (
                        // Cọc của CHÍNH đơn này, không phải tổng cọc của mọi đơn. `da_dung` nói
                        // rõ nó đã bù vào đâu — thiếu số đó thì người đọc thấy một khoản trừ mà
                        // không biết trừ vào đợt nào.
                        <span className="pay-don__coc">
                          cọc {money(don.coc.amount)}
                          {don.coc.da_dung > 0 && ` · đã bù ${money(don.coc.da_dung)}`}
                          {don.coc.con_du > 0 && ` · còn dư ${money(don.coc.con_du)}`}
                        </span>
                      )}
                      <span className="pay-don__due">
                        còn nợ <b>{money(don.con_no)}</b>
                      </span>
                      {canCreateVoucher && (
                        // MỘT nút cho cả đơn, không phải mỗi đợt một nút: màn đích là hộp lập
                        // phiếu chi của ĐƠN, chọn đợt nào là chọn trong đó.
                        <Button
                          variant="ghost"
                          onClick={() => {
                            onChanged();
                            onClose();
                            navigate("ke-toan-don-mua-hang", {
                              focusRequestCode: don.code,
                            });
                          }}
                        >
                          Lập phiếu chi
                        </Button>
                      )}
                    </div>
                    <table className="pay-table">
                      <thead>
                        <tr>
                          <th>Đợt</th>
                          <th>Ngày giao</th>
                          <th>Hóa đơn</th>
                          <th>Hạn trả</th>
                          <th className="pay-num">Giá trị</th>
                          <th className="pay-num">Đã trả</th>
                          <th className="pay-num">Còn nợ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {don.items.map((row) => (
                          <tr key={row.delivery_id ?? 0}>
                            <td>
                              <strong>{tenKhoan(row)}</strong>
                            </td>
                            <td>{fmtDate(row.delivery_date)}</td>
                            <td>
                              <HoaDon
                                so={row.invoice_number}
                                ngay={row.invoice_date}
                              />
                            </td>
                            <td>
                              <HanTra row={row} />
                            </td>
                            <td className="pay-num">{money(row.amount)}</td>
                            <td className="pay-num">{money(row.paid)}</td>
                            <td className="pay-num">
                              <strong>{money(row.con_no)}</strong>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))
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
                        <th>Hóa đơn</th>
                        <th>Đơn · Đợt</th>
                        <th className="pay-num">Số tiền</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.paid.slice(0, paidShown).map((row) => (
                        <tr key={row.voucher_id}>
                          <td>{fmtDate(row.paid_date)}</td>
                          <td>
                            {row.doc_no ?? row.code}
                            {!row.has_attachment && (
                              // CẢNH BÁO, không chặn — tiền đã ra rồi, chặn ở đây chẳng cứu được gì.
                              <small className="pay-warn">
                                {" "}
                                chưa có chứng từ
                              </small>
                            )}
                          </td>
                          <td>
                            <HoaDon
                              so={row.invoice_number}
                              ngay={row.invoice_date}
                            />
                          </td>
                          <td>
                            {row.purchase_code}
                            {/* Phải nói ĐỢT MẤY, không được ghi "trả theo đợt" chung chung: người
                                cầm sao kê nhà cung cấp đối chiếu từng dòng cần biết dòng nào ứng
                                với đợt nào. */}
                            <small>
                              {" "}
                              {row.payment_stage === "advance"
                                ? "· đặt cọc"
                                : row.delivery_seq_no != null
                                  ? `· Đợt ${row.delivery_seq_no}`
                                  : "· không theo đợt"}
                            </small>
                          </td>
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
