// Màn PHIẾU THU — shell (tách từ pages/PaymentReceiptsPage.tsx).
// Giữ ở đây: state + `load()` + handlers (`startPrint` · `uploadAttachments` ·
// `removeAttachment` · `openEdit` · `confirmReceived` · `confirmCancel`) + `actions()`.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PaymentReceiptAttachment,
  type PaymentReceiptRow,
  type PaymentVoucherRow,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import { ReceiptRowActions } from "./components/ReceiptRowActions";
import { ReceiptsDrawer } from "./components/ReceiptsDrawer";
import { ReceiptsTable } from "./components/ReceiptsTable";
import { ReceiptsToolbar } from "./components/ReceiptsToolbar";
import { OtherReceiptDialog } from "./modals/OtherReceiptDialog";
import { ReceiptConfirmModals } from "./modals/ReceiptConfirmModals";
import { PaymentReceiptDialog } from "./PaymentReceiptDialog";
import { printReceipt } from "./print";
import { PAGE_SIZE } from "./shared/constants";
import "../../accounting.css";
import "../../purchase.css";

export function PaymentReceiptsPage({
  navigate,
  eventTick = 0,
  focusQuery = null,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ trang Phiếu chi: lọc theo mã PC/UNC khi mở trang. */
  focusQuery?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Phiếu thu (tách 10/08/2026). `create` = LẬP/SỬA phiếu + gán chứng từ;
  // trước đây gọi là `approve` nên nhìn ma trận tưởng là quyền duyệt.
  const canApprove = can("phieu_thu", "create");
  const canMarkReceived = can("phieu_thu", "manage_status");
  const canCancel = can("phieu_thu", "cancel");
  const canExport = can("phieu_thu", "export");
  const [rows, setRows] = useState<PaymentReceiptRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState(focusQuery ?? "");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editState, setEditState] = useState<null | {
    voucher: PaymentVoucherRow;
    receipt: PaymentReceiptRow;
  }>(null);
  const [creatingOther, setCreatingOther] = useState(false);
  const [marking, setMarking] = useState<PaymentReceiptRow | null>(null);
  const [bankReference, setBankReference] = useState("");
  const [cancelling, setCancelling] = useState<PaymentReceiptRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [attachments, setAttachments] = useState<PaymentReceiptAttachment[]>(
    [],
  );
  const [attachmentBusy, setAttachmentBusy] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .receipts(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
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
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Không tải được phiếu thu.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  useEffect(() => {
    if (!focusQuery) return;
    setQ(focusQuery);
    setStatusFilter("all");
    setPage(1);
  }, [focusQuery]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const openSource = (row: PaymentReceiptRow) => {
    if (row.source_type === "purchase_refund" && row.payment_voucher_code) {
      navigate("ke-toan-phieu-chi", { focusVoucherQuery: row.payment_voucher_code });
      return;
    }
    if (row.source_type === "order_deposit" && row.order_id) {
      navigate("don-hang-ban", { openOrderId: row.order_id });
      return;
    }
    if (row.source_type === "sales_invoice" && row.order_id) {
      navigate("don-hang-ban", { openOrderId: row.order_id });
    }
  };
  const selectedReceiptId = selected?.id ?? null;
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
    if (!token || selectedReceiptId == null) {
      setAttachments([]);
      return;
    }
    let cancelled = false;
    api.accounting
      .receiptAttachments(token, selectedReceiptId)
      .then((response) => {
        if (!cancelled) setAttachments(response.items);
      })
      .catch(() => {
        if (!cancelled) setAttachments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selectedReceiptId]);

  function startPrint(row: PaymentReceiptRow) {
    if (!printReceipt(row))
      setError(
        "Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.",
      );
  }

  async function uploadAttachments(list: FileList | null) {
    if (!token || selectedReceiptId == null || !list?.length) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      for (const file of Array.from(list)) {
        await api.accounting.uploadReceiptAttachment(
          token,
          selectedReceiptId,
          file,
        );
      }
      const response = await api.accounting.receiptAttachments(
        token,
        selectedReceiptId,
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

  async function removeAttachment(attachment: PaymentReceiptAttachment) {
    if (!token || selectedReceiptId == null) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      await api.accounting.deleteReceiptAttachment(
        token,
        selectedReceiptId,
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

  async function openEdit(row: PaymentReceiptRow) {
    if (!token) return;
    if (!row.payment_voucher_id) {
      setError("Phiếu thu này không có phiếu chi nguồn để sửa ở form thu hoàn.");
      return;
    }
    setBusy(true);
    try {
      const voucher = await api.accounting.voucher(
        token,
        row.payment_voucher_id,
      );
      setEditState({ voucher, receipt: row });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không tải được phiếu chi nguồn.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmReceived() {
    if (!token || !marking) return;
    if (marking.receipt_method === "bank_transfer" && !bankReference.trim()) {
      setError("Thu qua ngân hàng phải có mã giao dịch hoặc số báo có.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.markReceiptReceived(
        token,
        marking.id,
        bankReference.trim() || null,
      );
      setMarking(null);
      setBankReference("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không xác nhận được phiếu thu.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmCancel() {
    if (!token || !cancelling) return;
    if (!cancelReason.trim()) {
      setError("Vui lòng nhập lý do hủy.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.cancelReceipt(
        token,
        cancelling.id,
        cancelReason.trim(),
      );
      setCancelling(null);
      setCancelReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không hủy được phiếu thu.",
      );
    } finally {
      setBusy(false);
    }
  }

  function actions(row: PaymentReceiptRow) {
    return (
      <ReceiptRowActions
        row={row}
        canExport={canExport}
        startPrint={startPrint}
        canApprove={canApprove}
        closeDetailThen={closeDetailThen}
        openEdit={openEdit}
        busy={busy}
        canMarkReceived={canMarkReceived}
        setMarking={setMarking}
        setBankReference={setBankReference}
        canCancel={canCancel}
        setCancelling={setCancelling}
        setCancelReason={setCancelReason}
      />
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Phiếu thu</h1>
        <p className="md-page__sub">
          Ghi nhận các khoản tiền vào công ty: thu cọc đơn bán, thu hóa đơn,
          thu hoàn từ phiếu chi và các khoản thu khác phát sinh độc lập.
        </p>
      </header>
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      <ReceiptsToolbar
        q={q}
        setQ={setQ}
        setPage={setPage}
        load={load}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        canApprove={canApprove}
        setCreatingOther={setCreatingOther}
      />
      <ReceiptsTable
        loading={loading}
        rows={rows}
        selected={selected}
        setSelectedId={setSelectedId}
        openSource={openSource}
        total={total}
        page={page}
        setPage={setPage}
        totalPages={totalPages}
      />
      {selected && (
        <ReceiptsDrawer
          selected={selected}
          setSelectedId={setSelectedId}
          canApprove={canApprove}
          openSource={openSource}
          attachments={attachments}
          attachmentBusy={attachmentBusy}
          uploadAttachments={uploadAttachments}
          removeAttachment={removeAttachment}
          actions={actions}
        />
      )}
      {editState && (
        <PaymentReceiptDialog
          key={editState.receipt.id}
          voucher={editState.voucher}
          receipt={editState.receipt}
          onClose={() => setEditState(null)}
          onSaved={() => {
            setEditState(null);
            load();
          }}
        />
      )}
      {creatingOther && (
        <OtherReceiptDialog
          onClose={() => setCreatingOther(false)}
          onSaved={() => {
            setCreatingOther(false);
            load();
          }}
        />
      )}
      <ReceiptConfirmModals
        marking={marking}
        setMarking={setMarking}
        bankReference={bankReference}
        setBankReference={setBankReference}
        busy={busy}
        confirmReceived={confirmReceived}
        cancelling={cancelling}
        setCancelling={setCancelling}
        cancelReason={cancelReason}
        setCancelReason={setCancelReason}
        confirmCancel={confirmCancel}
      />
    </main>
  );
}
