// Màn ĐƠN MUA HÀNG (Kế toán) — shell (tách từ pages/AccountingPurchaseInboxPage.tsx).
// Giữ ở đây: state + `load()`/`loadSuppliers()` + effects + `approve()`/`reject()` +
// `closeDetailThen()` + `actions()` (closure trên quyền & busy, drawer nhận làm prop).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PaymentVoucherRow,
  type PurchaseRequestRow,
  type SupplierCredit,
  type SupplierRow,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import { UNC_ENABLED } from "../../../constants/features";
import { PaymentVoucherDialog } from "../phieu-chi/PaymentVoucherDialog";
import { InboxDrawer } from "./components/InboxDrawer";
import { InboxRowActions } from "./components/InboxRowActions";
import { InboxTable } from "./components/InboxTable";
import { InboxToolbar } from "./components/InboxToolbar";
import { RejectModal } from "./modals/RejectModal";
import { PAGE_SIZE } from "./shared/constants";
import type { DepositFilter } from "./shared/types";
import "../../accounting.css";
import "../../purchase.css";

export function AccountingPurchaseInboxPage({
  navigate,
  eventTick = 0,
  focusRequestCode,
  onDataRefreshed,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Mã PMH cần mở sẵn — màn Công nợ phải trả nhảy sang đây để lập phiếu chi cho đúng đơn đó.
      Không có nó thì bấm "Lập phiếu chi" chỉ đổ ra danh sách trắng, người dùng phải tự đi tìm. */
  focusRequestCode?: string | null;
  onDataRefreshed?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  // DUYỆT đơn mua = quyết định CHI TIỀN ⇒ gác bằng `thu_mua:approve`, KHÔNG phải `ke_toan:approve`.
  // Sáng 04/08/2026 đã gỡ ô này khỏi bộ phận Mua hàng nên giờ chỉ giám đốc và người được trao
  // quyền còn. Để `ke_toan:approve` thì kế toán tự duyệt khoản chi rồi tự viết phiếu chi — đúng
  // lỗi tách vai vừa vá bên thu mua.
  // Ô này DỜI sang khoá `ke_toan` ngày 11/08/2026 (nút Duyệt / Từ chối chỉ có ở màn này nên ô
  // quyền cũng về đây). Lần dời trước sửa máy chủ mà QUÊN dòng này ⇒ quản trị tick ô mới, giao
  // diện vẫn hỏi ô cũ, nút không hiện — "cấp quyền rồi mà không thấy nút".
  const canApprove = can("ke_toan", "approve");
  // LẬP PHIẾU CHI là việc của kế toán — quyền khác hẳn quyền duyệt. Kế toán không có quyền duyệt
  // vẫn thấy đủ danh sách và trạng thái, chỉ không thấy nút Duyệt.
  // Nút "Lập phiếu chi" ⇒ quyền LẬP trên màn Phiếu chi. Trước đây hỏi `ke_toan:approve` —
  // cùng một ô với "gán chứng từ" và "lập phiếu thu", bật một cái là mở cả ba.
  const canCreateVoucher = can("phieu_chi", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState(focusRequestCode ?? "");
  // Mới vào hiện TẤT CẢ (chủ 04/08/2026). Trước đây mặc định lọc "chờ duyệt" nên mở màn ra là
  // giấu mất đơn đã duyệt, đã mua, đã nhận — kế toán tưởng chưa có gì để lập phiếu chi.
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [supplierFilter, setSupplierFilter] = useState<number | "all">("all");
  const [depositFilter, setDepositFilter] = useState<DepositFilter>("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [neededFrom, setNeededFrom] = useState("");
  const [neededTo, setNeededTo] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [voucherMode, setVoucherMode] = useState<null | {
    purchase: PurchaseRequestRow;
  }>(null);
  const [rejecting, setRejecting] = useState<PurchaseRequestRow | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .inbox(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        supplier_id: supplierFilter === "all" ? null : supplierFilter,
        deposit_status: depositFilter === "all" ? null : depositFilter,
        created_from: createdFrom || null,
        created_to: createdTo || null,
        needed_from: neededFrom || null,
        needed_to: neededTo || null,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : null,
        );
        onDataRefreshed?.();
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được yêu cầu Kế toán.",
        ),
      )
      .finally(() => setLoading(false));
  }, [
    token,
    q,
    statusFilter,
    supplierFilter,
    depositFilter,
    createdFrom,
    createdTo,
    neededFrom,
    neededTo,
    page,
    onDataRefreshed,
  ]);

  const loadSuppliers = useCallback(() => {
    if (!token) return;
    api.suppliers
      .list(token, { status: "active", sort: "name", page: 1, size: 200 })
      .then((res) => setSuppliers(res.items))
      .catch(() => setSuppliers([]));
  }, [token]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  // Sang màn này từ nơi khác kèm mã PMH ⇒ nhét luôn vào ô tìm và về trang 1.
  useEffect(() => {
    if (!focusRequestCode) return;
    setQ(focusRequestCode);
    setPage(1);
  }, [focusRequestCode]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

  // Drawer chi tiết đơn: Esc để đóng (trước đây do DetailModal lo, nay drawer tự nghe).
  useEffect(() => {
    if (selectedId == null) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedId(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedId]);

  const [vouchers, setVouchers] = useState<PaymentVoucherRow[]>([]);
  const [vouchersLoading, setVouchersLoading] = useState(false);

  useEffect(() => {
    if (!token || selected == null) {
      setVouchers([]);
      setVouchersLoading(false);
      return;
    }
    let ignore = false;
    setVouchersLoading(true);
    api.accounting
      .vouchers(token, {
        purchase_request_id: selected.id,
        sort: "-created_at",
        page: 1,
        size: 50,
      })
      .then((data) => {
        if (!ignore) setVouchers(data.items);
      })
      .catch(() => {
        if (!ignore) setVouchers([]);
      })
      .finally(() => {
        if (!ignore) setVouchersLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [token, selected, eventTick]);

  // HẠN MỨC CÔNG NỢ của NCC trên đơn đang mở — CẢNH BÁO MỀM (Đ6): chỉ nhắc, KHÔNG chặn duyệt.
  // Chặn cứng ở đây là đúng lúc gấp nhất (hết giấy, phải mua ngay) thì hệ khoá đường mua.
  // Gọi riêng chứ không nhét vào danh sách: một lần một đơn, chỉ khi người ta thật sự mở ra xem.
  const [credit, setCredit] = useState<SupplierCredit | null>(null);
  useEffect(() => {
    if (!token || selected == null) {
      setCredit(null);
      return;
    }
    let bo = false;
    api.purchaseRequests
      .supplierCredit(token, selected.id)
      .then((data) => {
        if (!bo) setCredit(data);
      })
      // Nuốt lỗi có chủ đích: đây là cảnh báo phụ, hỏng nó không được chặn màn chi tiết.
      .catch(() => {
        if (!bo) setCredit(null);
      });
    return () => {
      bo = true;
    };
  }, [token, selected]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  /** Đóng popup rồi mới mở form — không chồng hai lớp cửa sổ. */
  function closeDetailThen(action: () => void) {
    setSelectedId(null);
    action();
  }

  /** DUYỆT đơn mua — một bước riêng, không kèm lập phiếu chi.
   *
   * Gọi thẳng API của Thu mua (`/purchase-requests/{id}/approve`) chứ không đẻ endpoint kế toán
   * riêng: thứ đang duyệt là PHIẾU MUA, chỉ khác chỗ đứng bấm. Nhờ vậy chốt chống tự duyệt ở
   * service (người lập không duyệt phiếu của chính mình) vẫn chạy nguyên. */
  async function approve(row: PurchaseRequestRow) {
    if (!token) return;
    setBusy(`approve-${row.id}`);
    setError(null);
    try {
      await api.purchaseRequests.approve(token, row.id);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không duyệt được đơn mua hàng.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function reject() {
    if (!token || !rejecting) return;
    if (!rejectReason.trim()) {
      setError("Vui lòng nhập lý do từ chối.");
      return;
    }
    setBusy(`reject:${rejecting.id}`);
    try {
      await api.purchaseRequests.reject(
        token,
        rejecting.id,
        rejectReason.trim(),
      );
      setRejecting(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không từ chối được đơn mua hàng.",
      );
    } finally {
      setBusy(null);
    }
  }

  function actions(row: PurchaseRequestRow, compact = false) {
    return (
      <InboxRowActions
        row={row}
        compact={compact}
        canApprove={canApprove}
        canCreateVoucher={canCreateVoucher}
        busy={busy}
        closeDetailThen={closeDetailThen}
        approve={approve}
        setRejecting={setRejecting}
        setRejectReason={setRejectReason}
        setVoucherMode={setVoucherMode}
      />
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán thu mua</p>
        {/* Tên cũ "Yêu cầu mua hàng" SAI: màn này hiển thị PHIẾU MUA HÀNG (PMH), không phải YCMH. */}
        <h1 className="md-page__title">Đơn mua hàng</h1>
        <p className="md-page__sub">
          Giám đốc duyệt đơn Thu mua gửi đến; đơn đã duyệt thì Kế toán lập Phiếu chi
          {UNC_ENABLED ? " hoặc Ủy nhiệm chi" : ""}. Hai bước, hai người.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <InboxToolbar
        q={q}
        setQ={setQ}
        setPage={setPage}
        load={load}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        supplierFilter={supplierFilter}
        setSupplierFilter={setSupplierFilter}
        suppliers={suppliers}
        depositFilter={depositFilter}
        setDepositFilter={setDepositFilter}
        createdFrom={createdFrom}
        setCreatedFrom={setCreatedFrom}
        createdTo={createdTo}
        setCreatedTo={setCreatedTo}
        neededFrom={neededFrom}
        setNeededFrom={setNeededFrom}
        neededTo={neededTo}
        setNeededTo={setNeededTo}
      />

      <InboxTable
        loading={loading}
        rows={rows}
        selected={selected}
        setSelectedId={setSelectedId}
        openYcmh={openYcmh}
        total={total}
        page={page}
        setPage={setPage}
        totalPages={totalPages}
      />

      {selected && (
        <InboxDrawer
          selected={selected}
          setSelectedId={setSelectedId}
          vouchers={vouchers}
          vouchersLoading={vouchersLoading}
          credit={credit}
          openYcmh={openYcmh}
          actions={actions}
        />
      )}

      {voucherMode && (
        <PaymentVoucherDialog
          purchase={voucherMode.purchase}
          onClose={() => setVoucherMode(null)}
          onSaved={() => {
            setVoucherMode(null);
            load();
          }}
        />
      )}

      {rejecting && (
        <RejectModal
          rejecting={rejecting}
          setRejecting={setRejecting}
          rejectReason={rejectReason}
          setRejectReason={setRejectReason}
          busy={busy}
          reject={reject}
        />
      )}
    </main>
  );
}
