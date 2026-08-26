// Màn PHIẾU CHI — shell (tách từ pages/PaymentVouchersPage.tsx).
// ⚠️ TIỀN THẬT: phiếu chi lập ra là tiền ĐÃ rời két. Giữ ở đây nguyên văn state + `load()` +
// `confirmCancel()` + `uploadAttachments`/`removeAttachment` + `actions()`.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PaymentVoucherAttachment,
  type PaymentVoucherRow,
  type PurchaseRequestRow,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import { VOUCHER_PAGE_LABEL } from "../../../constants/features";
import { PaymentReceiptDialog } from "../phieu-thu/PaymentReceiptDialog";
import { VoucherRowActions } from "./components/VoucherRowActions";
import { VouchersDrawer } from "./components/VouchersDrawer";
import { VouchersTable } from "./components/VouchersTable";
import { VouchersToolbar } from "./components/VouchersToolbar";
import { CancelVoucherModal } from "./modals/CancelVoucherModal";
import { StandaloneVoucherDialog } from "./modals/StandaloneVoucherDialog";
import { PaymentVoucherDialog } from "./PaymentVoucherDialog";
import { printVoucher } from "./print";
import { PAGE_SIZE } from "./shared/list-constants";
import "../../accounting.css";
import "../../purchase.css";

export function PaymentVouchersPage({
  navigate,
  eventTick = 0,
  focusQuery = null,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ trang Phiếu thu: điền sẵn ô tìm kiếm (mã PC/UNC). */
  focusQuery?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Phiếu chi (tách 10/08/2026). `create` = LẬP phiếu + gán chứng từ.
  const canApprove = can("phieu_chi", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const openReceipts = (query: string) =>
    navigate("ke-toan-phieu-thu", { focusReceiptQuery: query });
  // KHÔNG còn `canMarkPaid`: bước "Xác nhận đã chi" đã bỏ cùng với trạng thái Chờ chi (Đ1).
  const canCancel = can("phieu_chi", "cancel");
  const canExport = can("phieu_chi", "export");
  const [rows, setRows] = useState<PaymentVoucherRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editState, setEditState] = useState<null | {
    voucher: PaymentVoucherRow | null;
    purchase: PurchaseRequestRow;
  }>(null);
  const [cancelling, setCancelling] = useState<PaymentVoucherRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [receiptFor, setReceiptFor] = useState<PaymentVoucherRow | null>(null);
  const [standaloneOpen, setStandaloneOpen] = useState(false);
  const [attachments, setAttachments] = useState<PaymentVoucherAttachment[]>(
    [],
  );
  const [attachmentBusy, setAttachmentBusy] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .vouchers(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        voucher_type: typeFilter === "all" ? null : typeFilter,
        // "group": phiếu cùng PMH đứng cạnh nhau, nhóm có phiếu mới nhất lên đầu.
        sort: "-group",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        // Chỉ giữ popup đang mở nếu phiếu đó còn trong kết quả; KHÔNG tự chọn
        // dòng đầu (sẽ làm popup tự bung khi vào trang).
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : null,
        );
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Không tải được Phiếu chi.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, typeFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  // Liên thông từ trang Phiếu thu: điền mã vào ô tìm → load() tự chạy lại.
  useEffect(() => {
    if (!focusQuery) return;
    setQ(focusQuery);
    setStatusFilter("all");
    setTypeFilter("all");
    setPage(1);
  }, [focusQuery]);

  // Phiếu đang mở popup (null = không mở).
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const selectedVoucherId = selected?.id ?? null;
  /** Đóng popup rồi mới mở form — không chồng hai lớp cửa sổ. */
  function closeDetailThen(action: () => void) {
    setSelectedId(null);
    action();
  }

  // Drawer chi tiết: Esc để đóng (trước đây do DetailModal lo, nay drawer tự nghe).
  useEffect(() => {
    if (selectedId == null) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedId(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedId]);

  useEffect(() => {
    if (!token || selectedVoucherId == null) {
      setAttachments([]);
      return;
    }
    let cancelled = false;
    api.accounting
      .voucherAttachments(token, selectedVoucherId)
      .then((response) => {
        if (!cancelled) setAttachments(response.items);
      })
      .catch(() => {
        if (!cancelled) setAttachments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selectedVoucherId]);

  async function uploadAttachments(list: FileList | null) {
    if (!token || selectedVoucherId == null || !list?.length) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      for (const file of Array.from(list)) {
        await api.accounting.uploadVoucherAttachment(
          token,
          selectedVoucherId,
          file,
        );
      }
      const response = await api.accounting.voucherAttachments(
        token,
        selectedVoucherId,
      );
      setAttachments(response.items);
      load(); // cập nhật attachment_count → badge "Thiếu chứng từ" ở bảng
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không tải được file lên.",
      );
    } finally {
      setAttachmentBusy(false);
    }
  }

  async function removeAttachment(attachment: PaymentVoucherAttachment) {
    if (!token || selectedVoucherId == null) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      await api.accounting.deleteVoucherAttachment(
        token,
        selectedVoucherId,
        attachment.id,
      );
      setAttachments((current) =>
        current.filter((row) => row.id !== attachment.id),
      );
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không xóa được file đính kèm.",
      );
    } finally {
      setAttachmentBusy(false);
    }
  }
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ĐÃ GỠ 07/08/2026 — `openEdit`. Không còn đường sửa phiếu chi đã lập.

  // async function openTopUp(row: PaymentVoucherRow) {
  //   if (!token) return;
  //   setBusy(true);
  //   setError(null);
  //   try {
  //     const purchase = await api.purchaseRequests.get(
  //       token,
  //       row.purchase_request_id,
  //     );
  //     if (!["approved", "purchased", "partially_received", "received"]
  //           .includes(purchase.status)) {
  //       setError(
  //         `PMH ${purchase.code} không còn ở trạng thái được lập chứng từ.`,
  //       );
  //       return;
  //     }
  //     // `available_amount` ĐÃ BỎ (06/08/2026). Trần nay có HAI mức theo loại phiếu:
  //     // `tran_dat_coc` (đặt cọc) và `outstanding_amount` = công nợ (thanh toán).
  //     if (Math.max(purchase.tran_dat_coc, purchase.outstanding_amount) <= 0) {
  //       setError(`PMH ${purchase.code} đã được lập đủ chứng từ thanh toán.`);
  //       return;
  //     }
  //     setEditState({ voucher: null, purchase });
  //   } catch (err) {
  //     setError(
  //       err instanceof ApiError ? err.message : "Không tải được PMH nguồn.",
  //     );
  //   } finally {
  //     setBusy(false);
  //   }
  // }

  async function confirmCancel() {
    if (!token || !cancelling) return;
    if (!cancelReason.trim()) {
      setError("Vui lòng nhập lý do hủy.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.cancelVoucher(
        token,
        cancelling.id,
        cancelReason.trim(),
      );
      setCancelling(null);
      setCancelReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không hủy được chứng từ.",
      );
    } finally {
      setBusy(false);
    }
  }

  function startPrint(row: PaymentVoucherRow) {
    if (!printVoucher(row))
      setError(
        "Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.",
      );
  }
  function actions(row: PaymentVoucherRow) {
    return (
      <VoucherRowActions
        row={row}
        canExport={canExport}
        startPrint={startPrint}
        closeDetailThen={closeDetailThen}
        canCancel={canCancel}
        setCancelling={setCancelling}
        setCancelReason={setCancelReason}
      />
    );
  }

  return (
    <main className="md-page acct-pc">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">{VOUCHER_PAGE_LABEL}</h1>
        <p className="md-page__sub">
          Lập phiếu chi là tiền đã ra khỏi két — phiếu sinh ra đã là "Đã chi".
          Ghi nhận nhầm thì hủy phiếu (bắt lý do), nguồn chi có thể là Đơn mua hàng,
          chi phí nội bộ, hoàn tiền khách hàng hoặc khoản chi khác.
        </p>
      </header>
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      <VouchersToolbar
        q={q}
        setQ={setQ}
        setPage={setPage}
        load={load}
        typeFilter={typeFilter}
        setTypeFilter={setTypeFilter}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        canApprove={canApprove}
        setStandaloneOpen={setStandaloneOpen}
      />
      <VouchersTable
        loading={loading}
        rows={rows}
        selected={selected}
        setSelectedId={setSelectedId}
        total={total}
        page={page}
        setPage={setPage}
        totalPages={totalPages}
      />
      {selected && (
        <VouchersDrawer
          selected={selected}
          setSelectedId={setSelectedId}
          canApprove={canApprove}
          openYcmh={openYcmh}
          openReceipts={openReceipts}
          attachments={attachments}
          attachmentBusy={attachmentBusy}
          uploadAttachments={uploadAttachments}
          removeAttachment={removeAttachment}
          actions={actions}
        />
      )}

      {editState && (
        <PaymentVoucherDialog
          key={editState.voucher?.id ?? "new"}
          purchase={editState.purchase}
          voucher={editState.voucher}
          onClose={() => setEditState(null)}
          onSaved={() => {
            setEditState(null);
            load();
          }}
        />
      )}
      {standaloneOpen && (
        <StandaloneVoucherDialog
          onClose={() => setStandaloneOpen(false)}
          onSaved={(saved) => {
            setStandaloneOpen(false);
            setSelectedId(saved.id);
            load();
          }}
        />
      )}
      {receiptFor && (
        <PaymentReceiptDialog
          key={`receipt-${receiptFor.id}`}
          voucher={receiptFor}
          onClose={() => setReceiptFor(null)}
          onSaved={() => {
            setReceiptFor(null);
            load();
          }}
        />
      )}
      {/* ĐÃ GỠ 06/08/2026 — hộp "Xác nhận đã chi". Phiếu lập ra đã là tiền ra khỏi két, không còn
          bước xác nhận nào ở giữa (Đ1). Endpoint `mark-paid` cũng đã gỡ khỏi backend. */}
      {cancelling && (
        <CancelVoucherModal
          cancelling={cancelling}
          setCancelling={setCancelling}
          cancelReason={cancelReason}
          setCancelReason={setCancelReason}
          busy={busy}
          confirmCancel={confirmCancel}
        />
      )}
    </main>
  );
}
