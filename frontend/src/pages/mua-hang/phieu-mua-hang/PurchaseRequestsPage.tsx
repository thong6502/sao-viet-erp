// Màn MUA HÀNG — shell (tách từ pages/PurchaseRequestsPage.tsx).
// Giữ ở đây: state + fetch + effects + handlers (`save` / `runAction` / 4×`confirm*`) + chỗ mount.
// ⚠️ XƯƠNG SỐNG RELOAD là cặp `updateRow(next)` + `loadSources()`: mọi mutator phải gọi ĐỦ CẢ HAI,
// và component con nhận đủ cả hai qua props. `save` CỐ Ý ở lại đây (nó chạm `rows`/`tab`/
// `loadSuppliers` + cụm FormState) — drawer form chỉ nhận nó làm handler của <form>.
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  ApiError,
  api,
  type DepartmentPurchaseRequestRow,
  type PurchaseDeliveryRow,
  type PurchaseRequestRow,
  type SupplierRow,
} from "../../../api/client";
import { useDebounced } from "../../../utils/useDebounced";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import type { SeedLine } from "../../KhoDeNghiPage";
import { StatusTabs } from "../../../components/StatusTabs";
import { PurchaseDetailDrawer } from "./components/PurchaseDetailDrawer";
import { PurchaseFormDrawer } from "./components/PurchaseFormDrawer";
import { PurchaseModals } from "./components/PurchaseModals";
import { PhieuListTab } from "./tabs/PhieuListTab";
import { YeuCauInboxTab } from "./tabs/YeuCauInboxTab";
import { useNapTenDonVi } from "../../tenDonVi";
import { PAGE_SIZE, SOURCE_PAGE_SIZE } from "./shared/constants";
import {
  chaoGiaChoMatHang,
  emptyLine,
  emptyRequest,
  fromRequest,
  lineTotal,
  todayInputValue,
} from "./shared/helpers";
import type {
  DepositFilter,
  FormLine,
  FormState,
  PurchaseTab,
  SourceStatusFilter,
  StatusFilter,
} from "./shared/types";
import "../../master-data.css";
// Hộp khai số thực nhận mượn bảng gọn `.pay-table` của màn Công nợ — cùng một loại bảng phụ trong
// hộp thoại, không dựng bộ lớp thứ hai cho y hệt một việc.
import "../../payables.css";
import "../../purchase.css";

export function PurchaseRequestsPage({
  navigate,
  eventTick = 0,
  focusRequestCode = null,
  onDataRefreshed,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ màn khác (Công nợ / Kế toán thu mua / Phiếu chi): mã tài liệu cần soi.
   *  Mã `PMH-…` = phiếu mua → tab "phieu"; mã `YCMH-…` = yêu cầu → tab "yeu-cau".
   *  Xem effect "BẪY LIÊN THÔNG" bên dưới trước khi đụng vào. */
  focusRequestCode?: string | null;
  onDataRefreshed?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Nạp danh mục Đơn vị MỘT lần: mọi chỗ hiện số lượng ở màn này (dòng hàng, đợt giao, hộp ghi
  // đợt, phiếu in) đọc TÊN đơn vị qua `tenDonVi()`. Thiếu dòng này là tất cả rơi về mã trần.
  useNapTenDonVi();
  const canCreate = can("thu_mua", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  // Đợt giao ↔ phiếu nhập kho = CÙNG sự kiện hàng về: bấm "Nhập kho" ở một đợt → nhảy sang màn
  // Yêu cầu kho, mở sẵn form NHẬP điền theo hàng đã nhận. Ghi chú trỏ về mã đơn mua + số đợt.
  //
  // MẶT HÀNG auto-điền từ liên kết danh mục gốc của dòng đơn mua (mg 0174), khớp qua
  // `purchase_request_line_id`. Dòng đơn mua chỉ có tên chữ (không link danh mục) → hang null →
  // kho tự chọn (ô chọn vẫn mở dù dòng khoá). Tên hàng vẫn đẩy vào ghi chú để đối chiếu.
  const nhapKhoTuDot = (row: PurchaseRequestRow, dot: PurchaseDeliveryRow) => {
    // Khớp dòng giao → dòng đơn mua (đơn giá + mặt hàng gốc) qua purchase_request_line_id.
    const dongTheoId = new Map(row.lines.map((pl) => [pl.id, pl]));
    const seed: SeedLine[] = dot.lines.map((dl) => {
      const pl = dongTheoId.get(dl.purchase_request_line_id);
      return {
        hang_loai: pl?.hang_loai ?? null,
        hang_id: pl?.hang_id ?? null,
        hang_ma: pl?.hang_ma ?? null,
        hang_ten: pl?.hang_ten ?? null,
        dvt: dl.unit,
        he_so_ve_goc: null,
        sl_de_nghi: dl.quantity,
        don_gia: pl?.expected_unit_price ?? null,
        ghi_chu: [dl.item_name, dl.note].filter(Boolean).join(" — ") || null,
      };
    });
    navigate("kho-main", {
      khoNhapSeed: {
        seed,
        ngay_can: (dot.delivery_date || "").slice(0, 10),   // ngày nhập = ngày giao của đợt
        ghi_chu: `Nhập từ đơn mua ${row.code} — đợt ${dot.seq_no}`,
        locked: true,   // số liệu từ đơn mua → khoá, không cho sửa dòng
        deliveryId: dot.id,   // gắn nguồn đợt → yêu cầu chặn nhập trùng
        don_mua_ma: row.code,   // hiện rõ mã đơn mua ở THÔNG TIN CHUNG của form nhập
        dot_so: dot.seq_no,
      },
    });
  };
  // Đợt ĐÃ nhập → mở đúng yêu cầu nhập đã tạo (màn Kho, tab Yêu cầu) thay vì seed lại.
  const xemYeuCauNhap = (dot: PurchaseDeliveryRow) => {
    if (dot.stock_request_id == null) return;
    navigate("kho-main", { khoOpenRequest: { id: dot.stock_request_id, view: "denghi" } });
  };
  const canUpdate = can("thu_mua", "update");
  // Ba nút "Sửa số nhận · Mở lại đơn · Đóng đơn" gác bằng ô "Thao tác" (`update`) — gộp lại
  // ngày 12/08/2026 sau khi chủ chốt test ô riêng `manage_status` và kết luận nó không đáng có.
  const canApprovePurchase = can("thu_mua", "update");
  // KHÔNG còn `canApprove` ở màn này: duyệt đơn mua đã chuyển sang Kế toán thu mua (04/08/2026).
  //
  // ⚠️ Hộp "Lý do từ chối" (`reasonModal.kind === "reject"`) vẫn còn trong file nhưng KHÔNG CÒN AI
  // BẤM — chỉ nhánh `cancel` còn chạy. Giữ tạm để chép sang màn Đơn mua hàng; chép xong thì dọn,
  // đừng để nó nằm lại làm người đọc sau tưởng màn này vẫn từ chối được.
  // Tab đang mở. CỐ Ý mở màn ở "yeu-cau" và CỐ Ý không nhớ qua lần vào (không localStorage,
  // không nâng lên URL): hai người mở cùng màn phải thấy giống nhau, và việc của Thu mua luôn
  // bắt đầu từ hộp yêu cầu. Đừng "cải tiến" thành ghi nhớ lựa chọn.
  const [tab, setTab] = useState<PurchaseTab>("yeu-cau");
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [supplierFilter, setSupplierFilter] = useState<number | "all">("all");
  const [depositFilter, setDepositFilter] = useState<DepositFilter>("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [neededFrom, setNeededFrom] = useState("");
  const [neededTo, setNeededTo] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [sourceRows, setSourceRows] = useState<DepartmentPurchaseRequestRow[]>(
    [],
  );
  const [sourceTotal, setSourceTotal] = useState(0);
  // Số đếm trên TAB — CỐ Ý KHÁC số dòng của bảng bên trong, đừng "sửa cho khớp".
  //
  // Bảng yêu cầu mặc định lọc "Tất cả" (chủ chốt 08/08/2026) nên `sourceTotal` gồm cả phiếu đã
  // Hoàn tất / Đã huỷ. Con số trên tab là TÍN HIỆU CÓ VIỆC, nên nó chỉ đếm yêu cầu đang `open`
  // (chờ Thu mua xử lý). `somNhat` = ngày cần hàng sớm nhất trong nhóm đó — dùng cho dải nhắc và
  // cho tone đỏ của tab.
  const [choMua, setChoMua] = useState<{ soLuong: number; somNhat: string | null }>({
    soLuong: 0,
    somNhat: null,
  });
  const [sourceQ, setSourceQ] = useState("");
  const [sourceStatus, setSourceStatus] = useState<SourceStatusFilter>("all");
  const [sourceLoading, setSourceLoading] = useState(true);
  // Ô nhập vẫn bám state gốc (gõ tới đâu hiện tới đó); chỉ lời gọi máy chủ đọc bản đã
  // chậm 300ms — xem `utils/useDebounced`.
  const qDebounced = useDebounced(q);
  const sourceQDebounced = useDebounced(sourceQ);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [sourcePage, setSourcePage] = useState(1);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI DANH SÁCH — tách hẳn khỏi `error` (lỗi THAO TÁC).
   *
   *  Vì sao phải hai ô nhớ riêng: `error` bị hàng chục handler thao tác ghi vào (huỷ phiếu, ghi
   *  đợt giao, gán hoá đơn, thậm chí trình duyệt chặn cửa sổ in). Nếu ô rỗng của bảng đọc chung
   *  `error` thì chỉ cần bấm "In phiếu" mà bị chặn pop-up là CẢ BẢNG biến mất, thay bằng "Không
   *  đọc được dữ liệu" — dữ liệu còn nguyên trên máy chủ, chỉ là bảng tự xoá mình vì một lỗi in.
   *  Ô này CHỈ được ghi trong `catch` của hàm tải danh sách. */
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<PurchaseRequestRow | null>(null);
  const [form, setForm] = useState<FormState>(emptyRequest());
  const [formError, setFormError] = useState<string | null>(null);
  // Gom dòng theo NCC để nói trước "sẽ tạo mấy phiếu". Giữ THỨ TỰ NCC xuất hiện lần đầu — khớp
  // đúng cách backend nhóm, để bảng xem trước không nói một đằng, phiếu ra một nẻo.
  const phieuSeTao = useMemo(() => {
    const theoNcc = new Map<number, { ten: string; soDong: number; tien: number }>();
    for (const line of form.lines) {
      if (!line.supplier_id) continue;
      const cu = theoNcc.get(line.supplier_id) ?? {
        ten:
          suppliers.find((s) => s.id === line.supplier_id)?.name ??
          `NCC #${line.supplier_id}`,
        soDong: 0,
        tien: 0,
      };
      cu.soDong += 1;
      cu.tien += lineTotal(line);
      theoNcc.set(line.supplier_id, cu);
    }
    return [...theoNcc.values()];
  }, [form.lines, suppliers]);
  const minPurchaseDate = useMemo(() => todayInputValue(), []);
  // Ngày dự kiến nhận chỉ bị chặn bởi HÔM NAY, KHÔNG bởi ngày cần hàng (chủ 03/08/2026):
  // nhận hàng sớm hơn ngày cần là trường hợp mong muốn, chặn nó là cấm đúng cái tốt.
  const expectedReceiptMinDate = minPurchaseDate;
  const [deleting, setDeleting] = useState<PurchaseRequestRow | null>(null);
  // Dùng CHUNG một hộp "nhập lý do" cho cả huỷ / từ chối / lùi đã nhận — không dựng hộp thứ ba.
  const [reasonModal, setReasonModal] = useState<null | {
    // Chỉ còn "cancel" — HUỶ PHIẾU. Nhánh "undo_received" (nút "Mở lại đơn") đã gỡ 12/08/2026
    // theo chủ chốt; "reject" chuyển sang màn Đơn mua hàng (Kế toán) từ 11/08.
    kind: "cancel";
    row: PurchaseRequestRow;
    reason: string;
    error: string | null;
  }>(null);
  // Hộp khai SỐ THỰC NHẬN: mở khi bấm "Đã nhận" (mode `receive`) hoặc khi sửa lại sau (`edit`).
  const [receiveModal, setReceiveModal] = useState<null | {
    row: PurchaseRequestRow;
    mode: "receive" | "edit";
  }>(null);
  // --- Đợt giao: bốn hộp thoại, mỗi hộp một việc ---
  // `delivery: null` = ghi đợt MỚI, khác null = sửa đợt đó.
  const [deliveryModal, setDeliveryModal] = useState<null | {
    row: PurchaseRequestRow;
    delivery: PurchaseDeliveryRow | null;
  }>(null);
  const [invoiceModal, setInvoiceModal] = useState<PurchaseRequestRow | null>(
    null,
  );
  const [deletingDelivery, setDeletingDelivery] = useState<null | {
    row: PurchaseRequestRow;
    delivery: PurchaseDeliveryRow;
  }>(null);
  // "Đóng đơn (không giao nữa)" — cắt phần hàng chưa về ra khỏi công nợ nên BẮT lý do.
  const [closeModal, setCloseModal] = useState<null | {
    row: PurchaseRequestRow;
    reason: string;
    error: string | null;
  }>(null);

  const loadSuppliers = useCallback(() => {
    if (!token) return;
    api.suppliers
      .list(token, { status: "active", sort: "name", page: 1, size: 200 })
      .then((res) => setSuppliers(res.items))
      .catch(() => setSuppliers([]));
  }, [token]);

  /** Đếm yêu cầu ĐANG CHỜ MUA + ngày cần sớm nhất của nhóm đó.
   *
   * Phải hỏi riêng chứ không suy từ `sourceRows`: bảng đang lọc "Tất cả" và chỉ giữ 1 trang, nên
   * đếm tại chỗ sẽ ra số của trang hiện tại. `size: 1` + `sort: needed_date` là đủ: `total` cho số
   * lượng, dòng đầu cho ngày sớm nhất — không kéo cả danh sách về chỉ để lấy hai con số. */
  const loadChoMua = useCallback(() => {
    if (!token) return;
    api.departmentPurchaseRequests
      .list(token, { status: "open", sort: "needed_date", page: 1, size: 1 })
      .then((res) =>
        setChoMua({
          soLuong: res.total,
          somNhat: res.items[0]?.needed_date ?? null,
        }),
      )
      .catch(() => setChoMua({ soLuong: 0, somNhat: null }));
  }, [token]);

  const loadSources = useCallback(() => {
    if (!token) return;
    // Bám theo mọi lần nạp lại danh sách yêu cầu (mọi thao tác chạm YCMH đều gọi `loadSources`)
    // ⇒ số trên tab và dải nhắc không bao giờ đứng hình sau khi lập phiếu / huỷ / đóng đơn.
    loadChoMua();
    setSourceLoading(true);
    setSourceError(null);
    api.departmentPurchaseRequests
      .list(token, {
        q: sourceQDebounced.trim() || undefined,
        status: sourceStatus === "all" ? null : sourceStatus,
        sort: "-created_at",
        page: sourcePage,
        size: SOURCE_PAGE_SIZE,
      })
      .then((res) => {
        setSourceRows(res.items);
        setSourceTotal(res.total);
      })
      .catch(() => {
        setSourceRows([]);
        setSourceTotal(0);
        setSourceError("Không tải được danh sách yêu cầu mua hàng.");
      })
      .finally(() => setSourceLoading(false));
  }, [token, loadChoMua, sourceQDebounced, sourceStatus, sourcePage]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setListError(null);
    api.purchaseRequests
      .list(token, {
        q: qDebounced.trim() || undefined,
        status: status === "all" ? null : status,
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
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
        setSelectedId((current) =>
          current != null && res.items.some((row) => row.id === current)
            ? current
            : null,
        );
        onDataRefreshed?.();
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh sách đơn mua hàng.");
      })
      .finally(() => setLoading(false));
  }, [
    token,
    qDebounced,
    status,
    supplierFilter,
    depositFilter,
    createdFrom,
    createdTo,
    neededFrom,
    neededTo,
    page,
    onDataRefreshed,
  ]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    loadSuppliers();
    loadSources();
    load();
  }, [eventTick, loadSuppliers, loadSources, load]);

  // ⚠️ ĐƯỜNG PHÒNG THỦ — HIỆN CHƯA CÓ AI GỌI, ĐỪNG GỠ.
  //
  // Tình trạng thật (kiểm 08/08/2026): KHÔNG màn nào đang `navigate("mua-hang", …)` kèm mã. Các
  // màn Kế toán / Công nợ bấm mã thì nhảy sang `ke-toan-don-mua-hang` hoặc `yeu-cau-mua-hang`,
  // không vào đây. Nên đoạn dưới CHƯA chạy lần nào.
  //
  // Vì sao vẫn giữ: từ 08/08/2026 màn này mở mặc định ở tab "Yêu cầu chờ xử lý". Ngày nào có
  // người nối một đường nhảy vào đây kèm mã phiếu mà thiếu đoạn này, người dùng sẽ rơi vào tab
  // yêu cầu và KHÔNG THẤY GÌ — trông y hệt như phiếu đã bị xoá. Mã yêu cầu là `YCMH-…`, mã phiếu
  // mua là `PMH-…` (xem `purchase_service.py`), nên phân nhánh theo tiền tố.
  useEffect(() => {
    const code = (focusRequestCode ?? "").trim();
    if (!code) return;
    if (code.toUpperCase().startsWith("YCMH")) {
      setSourceQ(code);
      setSourceStatus("all");
      setSourcePage(1);
      setTab("yeu-cau");
    } else {
      setQ(code);
      setStatus("all");
      setPage(1);
      setTab("phieu");
    }
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const sourceTotalPages = Math.max(
    1,
    Math.ceil(sourceTotal / SOURCE_PAGE_SIZE),
  );
  // CÓ YÊU CẦU QUÁ HẠN chưa? — điều kiện DUY NHẤT bật tone đỏ ở tab và bật dải nhắc ở tab phiếu.
  // Ngày thường (còn hạn) thì không tô đỏ, không render dải nhắc: không tốn một pixel nào.
  // `minPurchaseDate` chính là HÔM NAY dạng yyyy-mm-dd (memo 1 lần) — dùng lại để khỏi có hai
  // cách tính "hôm nay" trong cùng một file.
  const coYcQuaHan =
    choMua.somNhat !== null && choMua.somNhat < minPurchaseDate;
  // Chỉ thay dòng trong danh sách, KHÔNG đụng selectedId: các nút thao tác nằm ở
  // bảng, chọn dòng ở đây sẽ tự bung popup chi tiết. Popup đang mở thì `selected`
  // tự lấy lại dòng mới từ `rows`.
  function updateRow(next: PurchaseRequestRow) {
    setRows((current) =>
      current.map((row) => (row.id === next.id ? next : row)),
    );
  }

  function openCreatePurchaseRequest(pickedSource: DepartmentPurchaseRequestRow) {
    if (pickedSource.status !== "open") {
      setError("Chỉ lập đơn mua hàng từ yêu cầu đang chờ Thu mua xử lý.");
      return;
    }
    const source = pickedSource;
    const lines = source.lines.map((line) => ({
      item_name: line.item_name,
      unit: line.unit,
      quantity: line.quantity,
      expected_unit_price: line.expected_unit_price,
      discount_percent: 0,
      vat_percent: 0,
      note: line.note ?? `Từ ${source.code}`,
      // Nối DÒNG ↔ DÒNG. Form dựng từ chính các dòng của yêu cầu nên id có sẵn ngay đây; không
      // gửi lên thì chi tiết yêu cầu không hiện được tình trạng từng sản phẩm, mà ghép bù theo
      // tên hàng thì trượt (thu mua sửa được tên cho khớp danh mục NCC).
      department_request_line_id: line.id,
    }));
    // Máy gán sẵn NCC RẺ NHẤT cho TỪNG DÒNG (không phải một NCC cho cả phiếu): phần lớn dòng chỉ
    // có một nơi bán nên tự khớp, người thu mua chỉ phải xử lý mấy chỗ có nhiều lựa chọn.
    // Dòng nào chưa ai bán thì để trống — ô chọn sẽ nói rõ, không im lặng.
    const daGan: FormLine[] = lines.map((line) => {
      const re = chaoGiaChoMatHang(line.item_name, suppliers)[0];
      if (!re) return { ...line, supplier_id: null };
      return {
        ...line,
        supplier_id: re.supplier_id,
        unit: line.unit || re.unit,
        expected_unit_price: re.unit_price,
        vat_percent: re.vat_percent,
      };
    });
    setEditing(null);
    setForm({
      supplier_id: null,
      source_request_ids: [source.id],
      content: source.content ?? source.purpose ?? "",
      needed_date: source.needed_date ?? "",
      expected_receipt_date: "",
      note: null,
      lines: daGan.length ? daGan : [emptyLine()],
    });
    setFormError(null);
    setMode("create");
  }

  function openEdit(row: PurchaseRequestRow) {
    setEditing(row);
    setForm(fromRequest(row));
    setFormError(null);
    setMode("edit");
  }

  function cleanRequest(input: FormState): FormState {
    const trimOptional = (v?: string | null) => {
      const s = (v ?? "").trim();
      return s || null;
    };
    return {
      supplier_id: input.supplier_id ?? null,
      source_request_ids: input.source_request_ids
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id) && id > 0),
      content: (input.content ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      expected_receipt_date: trimOptional(input.expected_receipt_date),
      note: null,
      lines: input.lines.map((line) => ({
        item_name: (line.item_name ?? "").trim(),
        unit: (line.unit ?? "").trim(),
        quantity: Number(line.quantity),
        expected_unit_price: Math.round(Number(line.expected_unit_price) || 0),
        discount_percent: Number(line.discount_percent) || 0,
        vat_percent: Number(line.vat_percent) || 0,
        note: trimOptional(line.note),
        supplier_id: line.supplier_id ?? null,
        department_request_line_id: line.department_request_line_id ?? null,
      })),
    };
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanRequest(form);
    // Chế độ TẠO: NCC gán ở từng DÒNG (kiểm ở dưới), không có ô NCC ở đầu phiếu.
    // Chế độ SỬA: phiếu đã thuộc về một NCC, giữ nguyên ô đầu phiếu.
    const missingHeader = [
      mode === "edit" && !payload.supplier_id ? "Nhà cung cấp" : "",
      !payload.needed_date ? "Ngày cần hàng" : "",
      !payload.content ? "Nội dung / mục đích" : "",
    ].filter(Boolean);
    if (missingHeader.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missingHeader.join(", ")}.`);
      return;
    }
    if (payload.needed_date && payload.needed_date < minPurchaseDate) {
      setFormError("Ngày cần hàng không được nhỏ hơn hôm nay.");
      return;
    }
    if (
      payload.expected_receipt_date &&
      payload.expected_receipt_date < minPurchaseDate
    ) {
      setFormError("Ngày dự kiến nhận hàng không được nhỏ hơn hôm nay.");
      return;
    }
    if (payload.source_request_ids.length !== 1) {
      setFormError("Mỗi đơn mua hàng chỉ được lập từ 1 yêu cầu mua hàng.");
      return;
    }
    if (
      !payload.lines.length ||
      payload.lines.some((line) => !line.item_name || !line.unit)
    ) {
      setFormError(
        "Mỗi phiếu cần ít nhất một dòng hàng; tên vật tư và đơn vị tính không được trống.",
      );
      return;
    }
    if (
      payload.lines.some(
        (line) => line.quantity <= 0 || line.expected_unit_price <= 0,
      )
    ) {
      setFormError("Số lượng và đơn giá dự kiến phải lớn hơn 0.");
      return;
    }
    if (
      payload.lines.some(
        (line) =>
          line.discount_percent < 0 ||
          line.discount_percent > 100 ||
          line.vat_percent < 0 ||
          line.vat_percent > 100,
      )
    ) {
      setFormError(
        "Giảm giá (%) và Thuế GTGT (%) phải trong khoảng 0 đến 100.",
      );
      return;
    }
    // Mỗi dòng phải biết mua của ai — không thì backend không nhóm được thành phiếu.
    if (mode !== "edit") {
      const chuaGan = payload.lines.filter((line) => !line.supplier_id);
      if (chuaGan.length > 0) {
        setFormError(
          `Chưa chọn nhà cung cấp cho: ${chuaGan
            .map((line) => line.item_name || "(dòng trống)")
            .join(", ")}.`,
        );
        return;
      }
    }
    setSaving(true);
    setFormError(null);
    try {
      if (mode === "edit" && editing) {
        const saved = await api.purchaseRequests.update(token, editing.id, {
          ...payload,
          lines: payload.lines.map(({ supplier_id: _bo, ...line }) => line),
        });
        updateRow(saved);
      } else {
        // Tách phiếu theo NCC trong MỘT lời gọi — gọi `create` nhiều lần sẽ bị chặn từ lần thứ
        // hai vì phiếu đầu đã giữ chỗ yêu cầu nguồn.
        const { items } = await api.purchaseRequests.createBatch(token, {
          source_request_ids: payload.source_request_ids,
          content: payload.content,
          needed_date: payload.needed_date,
          // KHÔNG gửi `expected_receipt_date`: lô này đẻ ra N đơn theo NCC và server đóng cùng
          // một ngày lên tất cả. Ngày giao khai riêng cho từng đơn ở màn Sửa (28/08/2026).
          note: payload.note,
          lines: payload.lines.map((line) => ({
            item_name: line.item_name,
            unit: line.unit,
            quantity: line.quantity,
            expected_unit_price: line.expected_unit_price,
            discount_percent: line.discount_percent,
            vat_percent: line.vat_percent,
            note: line.note,
            supplier_id: line.supplier_id as number,
            department_request_line_id: line.department_request_line_id,
          })),
        });
        setRows((current) => [...items, ...current]);
        setTotal((t) => t + items.length);
        // ⚠️ BẪY THỨ HAI — ĐỪNG GỠ. Nút "Tạo phiếu" nằm ở tab YÊU CẦU; lưu xong mà đứng nguyên
        // tại đó thì người dùng không thấy phiếu vừa lập (nó nằm ở tab kia), tưởng bấm hụt và bấm
        // lại — lần hai bị server chặn vì yêu cầu nguồn đã bị giữ chỗ. Kể cả đường tách nhiều
        // phiếu theo NCC cũng đi qua đây, nên một chỗ này là đủ cho cả hai.
        setTab("phieu");
      }
      setMode(null);
      loadSuppliers();
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không lưu được đơn mua hàng.");
    } finally {
      setSaving(false);
    }
  }

  async function runAction(
    row: PurchaseRequestRow,
    key: string,
    fn: () => Promise<PurchaseRequestRow>,
  ) {
    if (!token) return;
    setActionBusy(`${key}:${row.id}`);
    setError(null);
    try {
      updateRow(await fn());
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không thực hiện được thao tác.");
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmDelete() {
    if (!token || !deleting) return;
    setActionBusy(`delete:${deleting.id}`);
    try {
      await api.purchaseRequests.remove(token, deleting.id);
      setRows((current) => current.filter((row) => row.id !== deleting.id));
      setTotal((t) => Math.max(0, t - 1));
      setSelectedId(null);
      setDeleting(null);
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được phiếu.");
      setDeleting(null);
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmReason() {
    if (!token || !reasonModal) return;
    const { row, kind, reason } = reasonModal;
    // Huỷ phiếu là DỪNG HẲN một đề nghị chi tiền ⇒ bắt buộc ghi lý do để nhật ký còn truy được.
    if (!reason.trim()) {
      setReasonModal({ ...reasonModal, error: "Vui lòng nhập lý do huỷ phiếu." });
      return;
    }
    setActionBusy(`${kind}:${row.id}`);
    setReasonModal({ ...reasonModal, error: null });
    try {
      // HUỶ PHIẾU (12/08/2026). Đường này đã có ở máy chủ từ lâu — 5 test giữ hành vi thật —
      // nhưng CHƯA TỪNG có nút, nên chủ chốt test thấy "chả có gì". Nay nối nút vào.
      const next = await api.purchaseRequests.cancel(token, row.id, reason.trim());
      updateRow(next);
      setReasonModal(null);
      loadSources();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Không thực hiện được thao tác.";
      setReasonModal((current) =>
        current ? { ...current, error: message } : current,
      );
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmXoaDot() {
    if (!token || !deletingDelivery) return;
    const { row, delivery } = deletingDelivery;
    setActionBusy(`del-dot:${delivery.id}`);
    setError(null);
    try {
      updateRow(
        await api.purchaseRequests.deleteDelivery(token, row.id, delivery.id),
      );
      setDeletingDelivery(null);
      loadSources();
    } catch (err) {
      // Ca hay gặp: đợt đã có phiếu chi gắn vào ⇒ server chặn. Câu báo của server nói rõ phiếu
      // nào, nên đừng nuốt nó bằng câu chung chung.
      setError(err instanceof ApiError ? err.message : "Không xóa được đợt giao.");
      setDeletingDelivery(null);
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmDongDon() {
    if (!token || !closeModal) return;
    const { row, reason } = closeModal;
    if (!reason.trim()) {
      setCloseModal({ ...closeModal, error: "Vui lòng nhập lý do đóng đơn." });
      return;
    }
    setActionBusy(`close:${row.id}`);
    setCloseModal({ ...closeModal, error: null });
    try {
      updateRow(await api.purchaseRequests.close(token, row.id, reason.trim()));
      setCloseModal(null);
      loadSources();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Không đóng được đơn.";
      setCloseModal((current) =>
        current ? { ...current, error: message } : current,
      );
    } finally {
      setActionBusy(null);
    }
  }

  function setLine(index: number, patch: Partial<FormLine>) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, i) =>
        i === index ? { ...line, ...patch } : line,
      ),
    }));
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Mua hàng (403).
        </div>
      </main>
    );
  }

  // Banner lỗi dùng CHUNG cho cả hai tab, vì `error` là MỘT state và cả hai tab đều ghi vào nó:
  // tab yêu cầu ghi khi lập phiếu từ một yêu cầu không còn chờ xử lý, tab phiếu ghi khi thao tác
  // trên phiếu / in phiếu hỏng. Nếu chỉ treo banner ở một tab thì lời báo lỗi của tab kia biến mất
  // trong im lặng — người dùng bấm mà không hiểu vì sao không có gì xảy ra.
  const bannerLoi = error ? (
    <div className="banner banner--error" role="alert">
      {error}
    </div>
  ) : null;

  return (
    <main className="md-page acct-mh">
      {/* Đầu màn gọn 1 HÀNG như màn "Yêu cầu mua hàng": tiêu đề trái, 2 tab con phải.
          Bỏ eyebrow + đoạn mô tả để không chiếm chiều cao. Số trên tab yêu cầu là số ĐANG
          CHỜ MUA (`open`), KHÁC số dòng bảng bên trong (bảng lọc "Tất cả") — xem `choMua`. */}
      <div className="purchase__topbar-unified">
        <div className="purchase__topbar-left">
          <h1 className="purchase__topbar-title">Mua hàng</h1>
        </div>
        <div className="purchase__topbar-actions">
          <StatusTabs
            active={tab}
            onChange={(key) => setTab(key as PurchaseTab)}
            tabs={[
              {
                key: "yeu-cau",
                label: "Yêu cầu chờ xử lý",
                count: choMua.soLuong,
                tone: coYcQuaHan ? "alert" : "default",
              },
              { key: "phieu", label: "Đơn mua hàng", count: total },
            ]}
          />
        </div>
      </div>

      {/* Chỉ dựng nội dung của tab ĐANG MỞ (bảng kia không nằm dưới mép màn nữa, nó không tồn tại).
          Nhưng DỮ LIỆU vẫn tải cả hai ngay từ đầu — số đếm trên tab kia phải đúng ngay. */}
      {tab === "yeu-cau" && (
        <YeuCauInboxTab
          bannerLoi={bannerLoi}
          sourceQ={sourceQ}
          setSourceQ={setSourceQ}
          sourceStatus={sourceStatus}
          setSourceStatus={setSourceStatus}
          sourcePage={sourcePage}
          setSourcePage={setSourcePage}
          sourceLoading={sourceLoading}
          sourceError={sourceError}
          sourceRows={sourceRows}
          sourceTotal={sourceTotal}
          sourceTotalPages={sourceTotalPages}
          loadSources={loadSources}
          canCreate={canCreate}
          openCreatePurchaseRequest={openCreatePurchaseRequest}
        />
      )}

      {tab === "phieu" && (
        <PhieuListTab
          coYcQuaHan={coYcQuaHan}
          choMua={choMua}
          setTab={setTab}
          q={q}
          setQ={setQ}
          page={page}
          setPage={setPage}
          status={status}
          setStatus={setStatus}
          supplierFilter={supplierFilter}
          setSupplierFilter={setSupplierFilter}
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
          suppliers={suppliers}
          loading={loading}
          listError={listError}
          load={load}
          rows={rows}
          selected={selected}
          setSelectedId={setSelectedId}
          openYcmh={openYcmh}
          total={total}
          totalPages={totalPages}
        />
      )}

      {/* Hộp thoại nằm NGOÀI hai tab: mở từ tab nào cũng phải sống tiếp khi tab đổi (lập phiếu
          xong là màn tự nhảy sang tab phiếu — kéo hộp vào trong tab thì nó bị gỡ giữa chừng). */}
      {selected && (
        <PurchaseDetailDrawer
          selected={selected}
          setSelectedId={setSelectedId}
          openYcmh={openYcmh}
          canUpdate={canUpdate}
          canApprovePurchase={canApprovePurchase}
          updateRow={updateRow}
          setError={setError}
          actionBusy={actionBusy}
          runAction={runAction}
          openEdit={openEdit}
          nhapKhoTuDot={nhapKhoTuDot}
          xemYeuCauNhap={xemYeuCauNhap}
          setReceiveModal={setReceiveModal}
          setReasonModal={setReasonModal}
          setDeliveryModal={setDeliveryModal}
          setInvoiceModal={setInvoiceModal}
          setDeletingDelivery={setDeletingDelivery}
          setCloseModal={setCloseModal}
        />
      )}

      {mode && (
        <PurchaseFormDrawer
          mode={mode}
          setMode={setMode}
          editing={editing}
          form={form}
          setForm={setForm}
          setLine={setLine}
          save={save}
          saving={saving}
          formError={formError}
          suppliers={suppliers}
          minPurchaseDate={minPurchaseDate}
          expectedReceiptMinDate={expectedReceiptMinDate}
          phieuSeTao={phieuSeTao}
        />
      )}

      <PurchaseModals
        actionBusy={actionBusy}
        updateRow={updateRow}
        loadSources={loadSources}
        deleting={deleting}
        setDeleting={setDeleting}
        confirmDelete={confirmDelete}
        reasonModal={reasonModal}
        setReasonModal={setReasonModal}
        confirmReason={confirmReason}
        receiveModal={receiveModal}
        setReceiveModal={setReceiveModal}
        deliveryModal={deliveryModal}
        setDeliveryModal={setDeliveryModal}
        invoiceModal={invoiceModal}
        setInvoiceModal={setInvoiceModal}
        deletingDelivery={deletingDelivery}
        setDeletingDelivery={setDeletingDelivery}
        confirmXoaDot={confirmXoaDot}
        closeModal={closeModal}
        setCloseModal={setCloseModal}
        confirmDongDon={confirmDongDon}
      />
    </main>
  );
}
