// Trang Phiếu kho — cỗ máy chứng từ (spec-13). Một khung phiếu cho mọi nghiệp vụ; hành vi
// (chiều tồn, kho nguồn/đích, duyệt) lấy từ loại phiếu. Nháp → Nộp → (Duyệt) → Ghi sổ. Gate `kho`.
import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type VoucherRow,
  type VoucherLineInput,
  type VoucherInput,
  type VoucherAttachment,
  type ProductionOrderOption,
  type KhoVoucherType,
  type KhoItemStatus,
  type KhoMaterialOption,
  type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ProductionOrderForm } from "./ProductionOrdersPage";
import { MaterialForm } from "./MaterialsCatalogPage";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./master-data.css";

const STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", pending: "Chờ duyệt", posted: "Đã ghi sổ", cancelled: "Đã hủy",
};
// Màu pill trạng thái theo vòng đời (dùng token hệ: hổ phách=chờ, xanh rêu=ghi sổ, đỏ=hủy).
const V_STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  draft: { bg: "var(--paper-2, #ece6d7)", color: "#6f6752" },
  pending: { bg: "var(--amber-soft, #efe4c4)", color: "var(--amber-deep, #7a5c0f)" },
  posted: { bg: "var(--moss-soft, #dbe7dd)", color: "var(--moss-deep, #244a2e)" },
  cancelled: { bg: "var(--signal-soft, #efd5d5)", color: "var(--signal, #8a1f1f)" },
};

export function StockVoucherPage({ fixedTypeId = null }: { fixedTypeId?: number | null }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("kho", "create");
  const canApprove = can("kho", "approve");

  const [rows, setRows] = useState<VoucherRow[]>([]);
  const [types, setTypes] = useState<KhoVoucherType[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [materials, setMaterials] = useState<KhoMaterialOption[]>([]);
  const [statuses, setStatuses] = useState<KhoItemStatus[]>([]);
  const [statusF, setStatusF] = useState("");
  const [typeF, setTypeF] = useState<number | null>(null);
  const [partnerF, setPartnerF] = useState(""); // lọc NCC/đối tượng (client)
  const [createdByF, setCreatedByF] = useState(""); // lọc người nhập theo tên (client)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<VoucherRow | null>(null);

  const typeById = useMemo(() => new Map(types.map((t) => [t.id, t])), [types]);
  const whById = useMemo(() => new Map(warehouses.map((w) => [w.id, w])), [warehouses]);
  const fixedType = fixedTypeId != null ? typeById.get(fixedTypeId) : null;

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.kho.listVouchers(token, {
      status: statusF || undefined,
      voucher_type_id: fixedTypeId ?? typeF,
      size: 100,
    })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách phiếu.");
      })
      .finally(() => setLoading(false));
  }, [token, statusF, typeF, fixedTypeId]);

  // Danh sách người nhập (từ dữ liệu đã tải) cho dropdown lọc.
  const creators = useMemo(
    () => Array.from(new Set(rows.map((v) => v.created_by_name).filter(Boolean))) as string[],
    [rows],
  );
  // Lọc phía client: NCC (chứa) + người nhập (đúng tên).
  const shownRows = useMemo(
    () => rows.filter((v) =>
      (!partnerF.trim() || (v.partner_ref ?? "").toLowerCase().includes(partnerF.trim().toLowerCase())) &&
      (!createdByF || v.created_by_name === createdByF)),
    [rows, partnerF, createdByF],
  );

  useEffect(() => {
    if (!token) return;
    api.kho.voucherTypes(token).then((r) => setTypes(r.items)).catch(() => {});
    api.warehouses.list(token, { size: 200, sort: "code" }).then((r) => setWarehouses(r.items)).catch(() => {});
    api.kho.materialOptions(token).then(setMaterials).catch(() => {});
    api.kho.itemStatuses(token).then((r) => setStatuses(r.items)).catch(() => {});
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập Phiếu kho (403).</div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kho · Chứng từ</p>
        <h1 className="md-page__title">{fixedType ? fixedType.name : "Phiếu kho"}</h1>
        <p className="md-page__sub">
          {fixedType
            ? `Danh sách phiếu "${fixedType.name}" và tạo phiếu mới loại này. Nộp → (duyệt nếu cần) → ghi sổ.`
            : "Một khung phiếu cho mọi nghiệp vụ. Loại phiếu quyết định chiều tồn + kho nguồn/đích + duyệt."}
        </p>
      </header>

      <div className="md-page__toolbar">
        <select className="input" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
          <option value="">— Tất cả trạng thái —</option>
          <option value="draft">Nháp</option>
          <option value="pending">Chờ duyệt</option>
          <option value="posted">Đã ghi sổ</option>
          <option value="cancelled">Đã hủy</option>
        </select>
        {!fixedType && (
          <select className="input" value={typeF ?? ""} onChange={(e) => setTypeF(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— Tất cả loại phiếu —</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
          </select>
        )}
        <select className="input" value={createdByF} onChange={(e) => setCreatedByF(e.target.value)}>
          <option value="">— Tất cả người nhập —</option>
          {creators.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input className="input" placeholder="Lọc theo NCC/đối tượng…" value={partnerF} onChange={(e) => setPartnerF(e.target.value)} />
        <div className="md-page__toolbar-spacer" />
        {canCreate && <Button variant="primary" onClick={() => setCreating(true)}>+ Tạo phiếu</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr><th>Mã phiếu</th><th>Loại phiếu</th><th>Kho</th><th>Nhập từ</th><th>Người nhập</th><th>Số dòng</th><th>Trạng thái</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="md-page__status">Đang tải...</td></tr>
            ) : shownRows.length === 0 ? (
              <tr><td colSpan={7} className="md-page__empty">{rows.length === 0 ? "Chưa có phiếu. Bấm “Tạo phiếu”." : "Không có phiếu khớp bộ lọc."}</td></tr>
            ) : (
              shownRows.map((v) => {
                const t = typeById.get(v.voucher_type_id);
                const src = v.src_warehouse_id ? whById.get(v.src_warehouse_id)?.code : null;
                const dst = v.dst_warehouse_id ? whById.get(v.dst_warehouse_id)?.code : null;
                return (
                  <tr key={v.id} className="md-page__row" onClick={() => setDetail(v)}>
                    <td className="md-page__mono">{v.code}</td>
                    <td>{t ? t.name : `#${v.voucher_type_id}`}</td>
                    <td>{[src, dst].filter(Boolean).join(" → ") || <span className="md-page__muted">—</span>}</td>
                    <td>{v.partner_ref || <span className="md-page__muted">—</span>}</td>
                    <td>{v.created_by_name || <span className="md-page__muted">—</span>}</td>
                    <td>{v.lines.length}</td>
                    <td>
                      <span className={`md-page__status-badge ${v.status === "posted" ? "is-active" : "is-inactive"}`}>
                        {STATUS_LABEL[v.status] ?? v.status}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {creating && (
        <VoucherForm types={types} warehouses={warehouses} materials={materials} statuses={statuses}
          lockedTypeId={fixedTypeId}
          onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />
      )}
      {detail && (
        <VoucherDetail voucher={detail} types={types} warehouses={warehouses} materials={materials} statuses={statuses}
          canApprove={canApprove} canCreate={canCreate}
          onClose={() => setDetail(null)} onChanged={() => { setDetail(null); load(); }} />
      )}
    </main>
  );
}

const EMPTY_LINE: VoucherLineInput = { material_id: 0, quantity: 0 };

// --- Cấu hình form theo LOẠI phiếu (BRD Module Kho §2) ----------------------
// Mỗi nghiệp vụ nhập/xuất có đối tượng, chứng từ gốc và cột dòng khác nhau. Khai báo
// ở đây thay vì viết cứng từng form: map theo mã phiếu, fallback theo chiều tồn.
type PartnerKind = "ncc" | "khach" | "lsx" | "bo_phan" | "may";
interface VoucherFieldSpec {
  partnerKind: PartnerKind | null; // null = không có khối đối tượng (vd chuyển kho)
  partnerLabel: string;
  partnerPlaceholder: string;
  refLabel: string | null; // chứng từ gốc; null = ẩn
  refType: string | null; // lưu vào ref_type
  refPlaceholder: string;
  showCost: boolean; // cột Đơn giá (giá vốn nhập) — chỉ nhập mua
  showStatus: boolean; // cột Trạng thái hàng (KCS) — phiếu nhập
  showOnHand: boolean; // cột SL tồn (đối chiếu khi xuất)
  qtyLabel: string;
}

const SPEC_BY_CODE: Record<string, VoucherFieldSpec> = {
  // §2.2 — nhập NVL mua từ nhà cung cấp: đối tượng NCC, chứng từ = PO, có giá vốn + KCS.
  "NK-NVL": { partnerKind: "ncc", partnerLabel: "Nhà cung cấp", partnerPlaceholder: "VD: Cty Giấy An Bình",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: true, showStatus: false, showOnHand: false, qtyLabel: "SL thực nhận" },
  // Nhập giấy khách gửi: đối tượng KHÁCH, hàng khách gửi → KHÔNG ghi giá trị tồn (§1.5).
  "NK-GK": { partnerKind: "khach", partnerLabel: "Khách hàng (chủ giấy)", partnerPlaceholder: "VD: Cty ABC",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: false, qtyLabel: "SL thực nhận" },
  // §2.3 — nhập thành phẩm sau sản xuất: đối tượng LSX/đơn hàng, không nhập giá vốn (giá thành hệ thống).
  "NK-XUONG": { partnerKind: "lsx", partnerLabel: "LSX / Đơn hàng", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: false, qtyLabel: "SL bàn giao" },
  // §2.11 — xuất giao khách hàng: đối tượng KHÁCH, đối chiếu SL tồn.
  "XK-KH": { partnerKind: "khach", partnerLabel: "Khách hàng", partnerPlaceholder: "VD: Cty ABC",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // Xuất trả nhà cung cấp: đối tượng NCC.
  "XK-NCC": { partnerKind: "ncc", partnerLabel: "Nhà cung cấp (trả)", partnerPlaceholder: "VD: Cty Giấy An Bình",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL trả" },
  // §2.5 — xuất NVL cho sản xuất theo LSX (gồm giấy + vật tư khác). LSX là đối tượng.
  "XK-SX": { partnerKind: "lsx", partnerLabel: "LSX", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // §2.7 — nhập trả vật tư thừa từ SX: đối tượng LSX + tham chiếu phiếu xuất gốc; có trạng thái (đạt/lỗi).
  "NK-TRA": { partnerKind: "lsx", partnerLabel: "LSX", partnerPlaceholder: "VD: LSX-2026-088",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: false, qtyLabel: "SL trả" },
  // §2.8 — cấp phát vật tư tiêu hao/CCDC nội bộ: đối tượng bộ phận/tổ nhận.
  "XK-CCDC": { partnerKind: "bo_phan", partnerLabel: "Bộ phận / tổ nhận", partnerPlaceholder: "VD: Tổ In 1",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL cấp" },
  // §2.9 — xuất phụ tùng/bảo trì cho máy: đối tượng máy/thiết bị (lý do ghi ở Diễn giải).
  "XK-BT": { partnerKind: "may", partnerLabel: "Máy / thiết bị", partnerPlaceholder: "VD: Máy in Komori #1",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" },
  // §2.14 — xuất hủy/thanh lý: không có đối tượng; lý do ghi ở Diễn giải. Bắt buộc chọn hàng còn tồn.
  "XK-HUY": { partnerKind: null, partnerLabel: "Đối tượng", partnerPlaceholder: "",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL hủy" },
};

export function specForType(vt: KhoVoucherType | undefined): VoucherFieldSpec {
  if (vt && SPEC_BY_CODE[vt.code]) return SPEC_BY_CODE[vt.code];
  // Fallback theo chiều tồn cho loại phiếu tự tạo.
  if (vt?.stock_effect === "tang")
    return { partnerKind: "ncc", partnerLabel: "Nhập từ (NCC/đối tượng)", partnerPlaceholder: "VD: Cty Giấy An Bình",
      refLabel: null, refType: null, refPlaceholder: "",
      showCost: true, showStatus: false, showOnHand: false, qtyLabel: "Số lượng" };
  if (vt?.stock_effect === "giam")
    return { partnerKind: "bo_phan", partnerLabel: "Giao cho (bộ phận/khách)", partnerPlaceholder: "VD: Tổ In / Cty ABC",
      refLabel: null, refType: null, refPlaceholder: "",
      showCost: false, showStatus: false, showOnHand: true, qtyLabel: "SL xuất" };
  // Chuyển kho / khác: không có đối tượng.
  return { partnerKind: null, partnerLabel: "Đối tượng", partnerPlaceholder: "",
    refLabel: null, refType: null, refPlaceholder: "",
    showCost: false, showStatus: false, showOnHand: true, qtyLabel: "Số lượng" };
}

// Ô ký trên phiếu in — ĐỦ các vai tham gia quy trình theo "Vai trò tham gia" của BRD.
// Quy ước: "Thủ kho (người lập)" = Bộ phận Kho vừa nhận/xuất vừa lập phiếu (BRD §2.2/2.3/2.5).
// Ô "Kế toán / Người duyệt" thêm khi loại phiếu yêu cầu duyệt VÀ chưa có ô duyệt riêng
// (tránh 2 ô "duyệt" cạnh nhau ở XK-CCDC/XK-BT/XK-HUY — nơi tổ trưởng/Ban GĐ đã là người duyệt).
function signRolesFor(vt: KhoVoucherType | undefined, spec: VoucherFieldSpec): string[] {
  let roles: string[] = [];
  let hasApprover = false; // phiếu đã có sẵn ô duyệt riêng?

  switch (vt?.code) {
    // §2.11 — giao bán: khách nhận · tài xế giao · kho lập.
    case "XK-KH":
      roles = ["Người nhận hàng", "Người giao hàng", "Người lập phiếu"]; break;
    // §2.2 — nhập từ NCC: NCC giao · KCS kiểm chất lượng · kho nhận+lập.
    case "NK-NVL":
      roles = ["Người giao hàng", "KCS", "Thủ kho (người lập)"]; break;
    // §2.3 — nhập TP: xưởng bàn giao · KCS xác nhận đạt · kho nhận+lập.
    case "NK-XUONG":
      roles = ["Đại diện sản xuất", "KCS", "Thủ kho (người lập)"]; break;
    // §2.5 — xuất NVL cho SX: công nhân nhận · tổ trưởng SX · kho xuất+lập.
    case "XK-SX":
      roles = ["Người nhận (sản xuất)", "Tổ trưởng sản xuất", "Thủ kho (người lập)"]; break;
    // §2.7 — trả vật tư thừa: tổ SX trả · tổ trưởng xác nhận · kho nhận+lập.
    case "NK-TRA":
      roles = ["Người trả (sản xuất)", "Tổ trưởng", "Thủ kho (người lập)"]; break;
    // §2.8 — cấp CCDC nội bộ: người nhận · tổ trưởng/QL duyệt đề xuất · kho cấp+lập.
    case "XK-CCDC":
      roles = ["Người nhận (bộ phận)", "Tổ trưởng / Quản lý duyệt", "Thủ kho (người lập)"];
      hasApprover = true; break;
    // §2.9 — xuất bảo trì: bộ phận bảo trì nhận · tổ trưởng/QL duyệt · kho xuất+lập.
    case "XK-BT":
      roles = ["Người nhận (bảo trì)", "Tổ trưởng / Quản lý duyệt", "Thủ kho (người lập)"];
      hasApprover = true; break;
    // §2.14 — hủy/thanh lý: kho lập · KCS xác nhận lỗi · Ban GĐ/Quản lý duyệt.
    case "XK-HUY":
      roles = ["Thủ kho (người lập)", "KCS", "Ban GĐ / Quản lý duyệt"];
      hasApprover = true; break;
    // §2.10 — chuyển kho: bên giao / bên nhận (công đoạn/kho).
    case "DC-KHO":
      roles = ["Bên giao", "Bên nhận"]; break;
    default: {
      // Còn lại (NK-GK, XK-NCC, loại tự tạo…): bên đối tác + thủ kho kiêm lập.
      const kind = spec.partnerKind;
      if (vt?.stock_effect === "tang") {
        if (kind === "ncc") roles.push("Người giao hàng");
        else if (kind === "khach") roles.push("Người gửi hàng");
        else if (kind === "lsx") roles.push("Đại diện sản xuất");
      } else if (vt?.stock_effect === "giam") {
        if (kind === "khach") roles.push("Người nhận hàng");
        else if (kind === "ncc") roles.push("Người nhận (NCC)");
        else if (kind === "lsx") roles.push("Người nhận (sản xuất)");
        else if (kind === "bo_phan") roles.push("Người nhận (bộ phận)");
      }
      roles.push("Thủ kho (người lập)");
    }
  }
  // Người duyệt & ghi sổ (kế toán kho / quản lý kho) — vai thực sự chốt phiếu.
  if (vt?.require_approval && !hasApprover) roles.push("Kế toán / Người duyệt");
  return roles;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Điền sẵn form từ 1 Lệnh sản xuất (LSX) — dùng khi "sinh phiếu kho từ phiếu sản xuất". */
export interface VoucherPrefillLsx {
  id: number; code: string;
  customerName?: string | null; productName?: string | null; quantity?: number | null;
}

/** Điền sẵn form từ 1 Đơn mua hàng (PO) — dùng khi "tạo phiếu nhập kho từ PO đã nhận hàng". */
export interface VoucherPrefillPo {
  id: number; code: string; supplierName?: string | null;
  items?: { name: string; unit: string; qty: number }[];
}

export function VoucherForm({
  types, warehouses, materials, statuses,
  lockedWarehouse = null, restrictEffect = null, lockedTypeId = null,
  prefillLsx = null, prefillPo = null, editing = null, onClose, onSaved,
}: {
  types: KhoVoucherType[]; warehouses: WarehouseRow[]; materials: KhoMaterialOption[];
  statuses: KhoItemStatus[];
  /** Nếu set: SỬA phiếu Nháp này (điền sẵn + PUT). Loại phiếu bị khóa. */
  editing?: VoucherRow | null;
  /** Nếu set: khóa kho nguồn/đích theo kho này (dùng cho phiếu trong 1 kho cụ thể). */
  lockedWarehouse?: WarehouseRow | null;
  /** Nếu set: chỉ cho chọn loại phiếu có chiều tồn này (tang=nhập, giam=xuất, chuyen_vi_tri=chuyển kho). */
  restrictEffect?: "tang" | "giam" | "chuyen_vi_tri" | null;
  /** Nếu set: khóa cứng vào 1 loại phiếu (menu phiếu theo loại). */
  lockedTypeId?: number | null;
  /** Nếu set: sinh phiếu từ 1 LSX — điền sẵn đối tượng + gắn ref_id + hiện panel LSX read-only. */
  prefillLsx?: VoucherPrefillLsx | null;
  /** Nếu set: tạo phiếu nhập từ 1 PO — điền sẵn NCC + gắn ref_id + hiện danh sách hàng của PO. */
  prefillPo?: VoucherPrefillPo | null;
  onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const shownTypes = useMemo(
    () => {
      // Chỉ cho tạo phiếu bằng loại đang bật (is_active); loại đã gộp/ẩn không hiện.
      const active = types.filter((t) => t.is_active !== false);
      // SỬA: khóa vào đúng loại của phiếu (kể cả loại đã ẩn) để không đổi được.
      if (editing) { const et = types.find((t) => t.id === editing.voucher_type_id); return et ? [et] : active; }
      if (lockedTypeId != null) return active.filter((t) => t.id === lockedTypeId);
      if (restrictEffect) return active.filter((t) => t.stock_effect === restrictEffect);
      return active;
    },
    [types, restrictEffect, lockedTypeId, editing],
  );
  const typeLocked = lockedTypeId != null || !!editing;
  const [typeId, setTypeId] = useState<number | null>(editing?.voucher_type_id ?? lockedTypeId ?? shownTypes[0]?.id ?? null);
  const [docDate, setDocDate] = useState(editing?.doc_date ?? todayISO());
  const [srcWh, setSrcWh] = useState<number | null>(editing?.src_warehouse_id ?? null);
  const [dstWh, setDstWh] = useState<number | null>(editing?.dst_warehouse_id ?? null);
  const [partner, setPartner] = useState(editing?.partner_ref ?? ""); // NCC / khách / LSX / bộ phận — theo loại phiếu
  const [docRef, setDocRef] = useState(editing?.note ?? ""); // chứng từ gốc (PO / LSX / đơn hàng)
  const [receiver, setReceiver] = useState(editing?.receiver ?? ""); // Tổ/Người nhận vật tư (BRD §2.5, xuất NVL cho SX)
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [lines, setLines] = useState<VoucherLineInput[]>(
    editing
      ? editing.lines.map((l) => ({
          material_id: l.material_id, quantity: Number(l.quantity), uom: l.uom,
          lot_id: l.lot_id, location: l.location, dest_location: l.dest_location,
          status_id: l.status_id, unit_cost: l.unit_cost, note: l.note,
        }))
      : [],
  ); // rỗng lúc đầu — thêm qua popup (hoặc điền sẵn khi sửa)
  const [onHand, setOnHand] = useState<Record<number, number>>({}); // SL tồn theo vật tư (kho nguồn)
  const [lsxOptions, setLsxOptions] = useState<ProductionOrderOption[]>([]);
  const [lsxId, setLsxId] = useState<number | null>(null); // LSX đã chọn (ref_id)
  const [partnerOpts, setPartnerOpts] = useState<{ id: number; name: string }[]>([]); // gợi ý NCC/khách
  // Phiếu kho chỉ CHỌN mặt hàng — việc tạo/sửa vật tư làm ở trang "Danh mục vật tư".
  const [newItemFor, setNewItemFor] = useState<number | "new" | null>(null);

  // Áp một mặt hàng đã chọn vào dòng target; "new" = thêm dòng mới.
  function applyMaterialToLine(target: number | "new", m: KhoMaterialOption) {
    const avail = statuses.find((s) => s.code === "AVAILABLE");
    const patch: Partial<VoucherLineInput> = { material_id: m.id, uom: m.unit || "", note: m.note?.trim() || "", status_id: spec.showStatus ? (avail?.id ?? null) : null };
    setLines((ls) => (target === "new"
      ? [...ls, { ...EMPTY_LINE, ...patch }]
      : ls.map((l, k) => (k === target ? { ...l, ...patch } : l))));
  }

  const allMaterials = useMemo(() => {
    const seen = new Set<number>();
    const out: KhoMaterialOption[] = [];
    for (const m of materials) {
      if (seen.has(m.id)) continue;
      seen.add(m.id);
      out.push(m);
    }
    return out;
  }, [materials]);
  const matByIdForm = useMemo(() => new Map(allMaterials.map((m) => [m.id, m])), [allMaterials]);
  const [quickLsx, setQuickLsx] = useState(false); // mở modal tạo LSX nhanh
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const vt = shownTypes.find((t) => t.id === typeId);
  const spec = specForType(vt);
  const isLsx = spec.partnerKind === "lsx";

  // Nạp danh sách LSX đang mở khi loại phiếu tham chiếu LSX (nhập thành phẩm / xuất NVL).
  useEffect(() => {
    if (!token || !isLsx) return;
    api.production.orderOptions(token).then(setLsxOptions).catch(() => {});
  }, [token, isLsx]);

  // A. Nạp gợi ý đối tượng từ danh mục khi loại phiếu dùng NCC / Khách hàng.
  const partnerCatalog: "ncc" | "khach" | null =
    spec.partnerKind === "ncc" ? "ncc" : spec.partnerKind === "khach" ? "khach" : null;
  useEffect(() => {
    if (!token || !partnerCatalog) { setPartnerOpts([]); return; }
    api.kho.partnerOptions(token, partnerCatalog).then(setPartnerOpts).catch(() => setPartnerOpts([]));
  }, [token, partnerCatalog]);

  // B. Tạo phiếu từ PO: tự đổ dòng — khớp GẦN ĐÚNG tên hàng PO với vật tư trong danh mục.
  // PO không gắn material_id nên đây là best-effort; khớp được thì điền sẵn vật tư, không thì
  // để trống ô vật tư (người dùng chọn) nhưng vẫn điền SL/đơn vị + ghi tên PO vào ghi chú.
  useEffect(() => {
    if (!prefillPo?.items?.length || !materials.length) return;
    const norm = (s: string) => s.trim().toLowerCase();
    const matchMaterial = (name: string) => {
      const n = norm(name);
      if (!n) return undefined;
      return (
        materials.find((m) => norm(m.code) === n) ||
        materials.find((m) => norm(m.name) === n) ||
        materials.find((m) => norm(m.name).includes(n) || n.includes(norm(m.name)))
      );
    };
    setLines(prefillPo.items.map((it) => {
      const m = matchMaterial(it.name);
      return {
        ...EMPTY_LINE,
        material_id: m?.id ?? 0,
        quantity: it.qty,
        uom: it.unit || "",
        note: m ? "" : `PO: ${it.name}`,
      };
    }));
    // Chạy 1 lần theo PO; không phụ thuộc thay đổi materials sau đó.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillPo, materials.length]);

  function pickLsx(id: number | null) {
    setLsxId(id);
    const opt = lsxOptions.find((o) => o.id === id);
    setPartner(opt ? opt.code : "");
  }

  // Sinh phiếu từ LSX: điền sẵn đối tượng (LSX hoặc khách) + đưa LSX vào danh sách chọn.
  useEffect(() => {
    if (!prefillLsx) return;
    if (isLsx) {
      setLsxId(prefillLsx.id);
      setPartner(prefillLsx.code);
      setLsxOptions((os) => os.some((o) => o.id === prefillLsx.id) ? os
        : [{ id: prefillLsx.id, code: prefillLsx.code, label: `${prefillLsx.code}${prefillLsx.productName ? ` · ${prefillLsx.productName}` : ""}` }, ...os]);
    } else if (spec.partnerKind === "khach") {
      setPartner(prefillLsx.customerName ?? "");
    }
  }, [prefillLsx, isLsx, spec.partnerKind]);

  // Mức B — nạp NVL đã XUẤT cho lệnh đó (gộp theo vật tư) để đối chiếu lúc nhập thành phẩm.
  // Lệnh lấy theo LSX gắn sẵn (prefillLsx) HOẶC LSX vừa chọn trong dropdown (lsxId).
  // Chỉ tính phiếu xuất (stock_effect='giam') chưa hủy.
  const refLsxId = prefillLsx?.id ?? lsxId;
  const [issuedNvl, setIssuedNvl] = useState<{ name: string; unit: string; qty: number }[]>([]);
  const [showIssuedNvl, setShowIssuedNvl] = useState(false); // thu gọn mặc định, bấm mới mở
  useEffect(() => {
    if (!token || !refLsxId) { setIssuedNvl([]); return; }
    const outTypeIds = new Set(types.filter((t) => t.stock_effect === "giam").map((t) => t.id));
    api.kho.listVouchers(token, { ref_type: "lsx", ref_id: refLsxId, size: 200 })
      .then((r) => {
        const agg = new Map<string, { name: string; unit: string; qty: number }>();
        for (const v of r.items) {
          if (v.status === "cancelled" || !outTypeIds.has(v.voucher_type_id)) continue;
          for (const l of v.lines) {
            const name = l.material_name ?? `#${l.material_id}`;
            const unit = l.uom ?? "";
            const key = `${name}|${unit}`;
            const cur = agg.get(key) ?? { name, unit, qty: 0 };
            cur.qty += Number(l.quantity) || 0;
            agg.set(key, cur);
          }
        }
        setIssuedNvl(Array.from(agg.values()));
      })
      .catch(() => setIssuedNvl([]));
  }, [token, refLsxId, types]);

  // Tạo phiếu nhập từ PO: điền sẵn NCC (đối tượng) + số PO (chứng từ gốc).
  useEffect(() => {
    if (!prefillPo) return;
    setPartner(prefillPo.supplierName ?? "");
    setDocRef(prefillPo.code);
  }, [prefillPo]);
  const needSrc = vt?.require_src_wh || vt?.stock_effect === "giam" || vt?.stock_effect === "chuyen_vi_tri";
  const needDst = vt?.require_dst_wh || vt?.stock_effect === "tang" || vt?.stock_effect === "chuyen_vi_tri";
  // Kho khóa sẵn: nhập → khóa đích; xuất → khóa nguồn; CHUYỂN KHO (cần cả 2) → khóa NGUỒN,
  // để đích cho người dùng chọn.
  const isTransfer = needSrc && needDst;
  // Xuất NVL cho sản xuất (XK-SX): đối tượng = LSX + chiều giảm → khai thêm Tổ/Người nhận (BRD §2.5).
  const showReceiver = isLsx && vt?.stock_effect === "giam";
  const lockSrc = !!lockedWarehouse && needSrc;
  const lockDst = !!lockedWarehouse && needDst && !isTransfer;
  const effSrc = lockSrc ? lockedWarehouse!.id : srcWh;
  const effDst = lockDst ? lockedWarehouse!.id : dstWh;

  // Kho để lọc picker: xuất/chuyển → kho nguồn; nhập → kho đích. Nạp tập mặt hàng đang có tồn.
  const pickerWhId = effSrc ?? effDst;
  const [inKhoIds, setInKhoIds] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!token || !pickerWhId) { setInKhoIds(new Set()); return; }
    let alive = true;
    api.kho.stock(token, { warehouse_id: pickerWhId })
      .then((r) => { if (alive) setInKhoIds(new Set(r.items.filter((x) => (x.on_hand ?? 0) !== 0).map((x) => x.material_id))); })
      .catch(() => { if (alive) setInKhoIds(new Set()); });
    return () => { alive = false; };
  }, [token, pickerWhId]);

  // SL tồn: nạp tồn kho nguồn cho các vật tư đã chọn (phiếu xuất/chuyển). Đổi kho → nạp lại.
  const matKey = lines.map((l) => l.material_id).filter(Boolean).join(",");
  useEffect(() => {
    if (!token || !spec.showOnHand || !effSrc) { setOnHand({}); return; }
    const ids = Array.from(new Set(matKey.split(",").filter(Boolean).map(Number)));
    if (!ids.length) { setOnHand({}); return; }
    let alive = true;
    Promise.all(ids.map((id) =>
      api.kho.stock(token, { material_id: id, warehouse_id: effSrc })
        .then((r) => [id, r.items.reduce((s, x) => s + (x.on_hand ?? 0), 0)] as const)
        .catch(() => [id, 0] as const),
    )).then((pairs) => { if (alive) setOnHand(Object.fromEntries(pairs)); });
    return () => { alive = false; };
  }, [token, spec.showOnHand, effSrc, matKey]);

  function setLine(i: number, patch: Partial<VoucherLineInput>) {
    setLines((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (!typeId) return setError("Chọn loại phiếu.");
    if (needSrc && !effSrc) return setError("Loại phiếu này cần Kho nguồn.");
    if (needDst && !effDst) return setError("Loại phiếu này cần Kho đích.");
    if (isLsx && !lsxId) return setError("Chọn Lệnh sản xuất (LSX). Chưa có thì bấm “+ Tạo nhanh”.");
    if (spec.partnerKind && !isLsx && !partner.trim()) return setError(`Cần nhập ${spec.partnerLabel}.`);
    const valid = lines.filter((l) => l.material_id && Number(l.quantity) > 0);
    if (!valid.length) return setError("Cần ít nhất 1 dòng (vật tư + số lượng > 0).");

    const payload: VoucherInput = {
      voucher_type_id: typeId,
      doc_date: docDate || null,
      src_warehouse_id: needSrc ? effSrc : null,
      dst_warehouse_id: needDst ? effDst : null,
      partner_kind: spec.partnerKind && partner.trim() ? spec.partnerKind : null,
      partner_ref: partner.trim() || null,
      // LSX → FK cứng (ref_id). Sinh phiếu từ LSX luôn gắn ref bất kể loại phiếu.
      ref_type: prefillPo ? "po" : (prefillLsx ? "lsx" : (isLsx ? "lsx" : (docRef.trim() ? spec.refType : null))),
      ref_id: prefillPo ? prefillPo.id : (prefillLsx ? prefillLsx.id : (isLsx ? lsxId : null)),
      receiver: showReceiver ? (receiver.trim() || null) : null,
      note: docRef.trim() || null, // chứng từ gốc (PO/đơn hàng) — text tự do
      reason: reason.trim() || null,
      lines: valid.map((l) => ({
        material_id: l.material_id, quantity: Number(l.quantity),
        uom: l.uom?.trim() || null,
        status_id: spec.showStatus ? (l.status_id ?? null) : null,
        unit_cost: spec.showCost && l.unit_cost != null && String(l.unit_cost) !== "" ? Number(l.unit_cost) : null,
        note: l.note?.trim() || null,
      })),
    };
    setSaving(true);
    try {
      if (editing) await api.kho.updateVoucher(token, editing.id, payload);
      else await api.kho.createVoucher(token, payload);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu phiếu thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 940, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>{editing ? `Sửa phiếu · ${editing.code}` : prefillPo ? `Tạo phiếu nhập kho từ PO` : prefillLsx ? `Tạo phiếu ${vt ? vt.name : "kho"} từ LSX` : `Tạo phiếu kho${vt ? ` · ${vt.name}` : ""}`}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {prefillLsx && (
            <div className="md-page__wh-badge" style={{ display: "block", margin: "0 0 14px", padding: "10px 12px" }}>
              <div className="md-page__muted" style={{ marginBottom: 4 }}>Theo phiếu sản xuất</div>
              <div><strong className="md-page__mono">{prefillLsx.code}</strong>
                {prefillLsx.customerName ? ` · ${prefillLsx.customerName}` : ""}</div>
              {prefillLsx.productName && <div style={{ fontSize: 13 }}>Ấn phẩm: {prefillLsx.productName}
                {prefillLsx.quantity != null ? ` · SL: ${prefillLsx.quantity}` : ""}</div>}
            </div>
          )}
          {/* Mức B — đối chiếu NVL đã xuất cho lệnh này. Thu gọn mặc định để đỡ rối; bấm để mở. */}
          {refLsxId && vt?.stock_effect === "tang" && issuedNvl.length > 0 && (
            <div style={{ margin: "0 0 14px" }}>
              <button type="button" onClick={() => setShowIssuedNvl((s) => !s)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 13, color: "var(--rust, #b5531f)" }}>
                {showIssuedNvl ? "▾" : "▸"} NVL đã xuất cho lệnh này ({issuedNvl.length}) — để đối chiếu
              </button>
              {showIssuedNvl && (
                <div className="md-page__wh-badge" style={{ display: "block", margin: "8px 0 0", padding: "10px 12px" }}>
                  <table className="md-page__table" style={{ fontSize: 13 }}>
                    <thead><tr><th>Vật tư</th><th style={{ textAlign: "right" }}>SL đã xuất</th><th>Đơn vị</th></tr></thead>
                    <tbody>
                      {issuedNvl.map((r, i) => (
                        <tr key={i}><td>{r.name}</td><td style={{ textAlign: "right" }}>{fmtNum(r.qty)}</td><td>{r.unit}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
          {prefillPo && (
            <div className="md-page__wh-badge" style={{ display: "block", margin: "0 0 14px", padding: "10px 12px" }}>
              <div className="md-page__muted" style={{ marginBottom: 4 }}>Theo đơn mua hàng</div>
              <div><strong className="md-page__mono">{prefillPo.code}</strong>
                {prefillPo.supplierName ? ` · ${prefillPo.supplierName}` : ""}</div>
              {prefillPo.items && prefillPo.items.length > 0 && (
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  <span className="md-page__muted">Hàng trên PO (chọn vật tư tương ứng ở dưới):</span>
                  <ul style={{ margin: "2px 0 0", paddingLeft: 18 }}>
                    {prefillPo.items.map((it, i) => (
                      <li key={i}>{it.name} — {it.qty} {it.unit}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Loại phiếu *</span>
              {typeLocked ? (
                <div className="md-page__wh-badge" style={{ margin: 0 }}>
                  <strong>{vt?.name ?? shownTypes[0]?.name}</strong>
                </div>
              ) : (
                <select className="input" value={typeId ?? ""} onChange={(e) => setTypeId(Number(e.target.value))}>
                  {shownTypes.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
                </select>
              )}
            </label>
            <label className="field">
              <span className="field__label">Ngày phiếu</span>
              <input className="input" type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} />
            </label>
            {needSrc && (
              <label className="field">
                <span className="field__label">Kho nguồn *</span>
                {lockSrc ? (
                  <div className="md-page__wh-badge" style={{ margin: 0 }}>
                    <span className="md-page__mono">{lockedWarehouse!.code}</span>
                    <strong>{lockedWarehouse!.name}</strong>
                  </div>
                ) : (
                  <select className="input" value={srcWh ?? ""} onChange={(e) => setSrcWh(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn —</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
                  </select>
                )}
              </label>
            )}
            {needDst && (
              <label className="field">
                <span className="field__label">Kho đích *</span>
                {lockDst ? (
                  <div className="md-page__wh-badge" style={{ margin: 0 }}>
                    <span className="md-page__mono">{lockedWarehouse!.code}</span>
                    <strong>{lockedWarehouse!.name}</strong>
                  </div>
                ) : (
                  <select className="input" value={dstWh ?? ""} onChange={(e) => setDstWh(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn kho đích —</option>
                    {warehouses.filter((w) => w.id !== lockedWarehouse?.id).map((w) => <option key={w.id} value={w.id}>{w.code} · {w.name}</option>)}
                  </select>
                )}
              </label>
            )}
            {isLsx ? (
              <label className="field">
                <span className="field__label">{spec.partnerLabel} *</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <select className="input" style={{ flex: 1 }} value={lsxId ?? ""} onChange={(e) => pickLsx(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— Chọn LSX —</option>
                    {lsxOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                  <Button type="button" variant="ghost" onClick={() => setQuickLsx(true)}>+ Tạo nhanh</Button>
                </div>
              </label>
            ) : spec.partnerKind ? (
              <label className="field">
                <span className="field__label">{spec.partnerLabel} *</span>
                {partnerCatalog ? (
                  <>
                    <input className="input" list="vf-partner-dl" placeholder={`Chọn hoặc gõ · ${spec.partnerPlaceholder}`}
                      value={partner} onChange={(e) => setPartner(e.target.value)} />
                    <datalist id="vf-partner-dl">
                      {partnerOpts.map((p) => <option key={p.id} value={p.name} />)}
                    </datalist>
                  </>
                ) : (
                  <input className="input" placeholder={spec.partnerPlaceholder} value={partner} onChange={(e) => setPartner(e.target.value)} />
                )}
              </label>
            ) : null}
            {spec.refLabel && (
              <label className="field">
                <span className="field__label">{spec.refLabel}</span>
                <input className="input" placeholder={spec.refPlaceholder} value={docRef} onChange={(e) => setDocRef(e.target.value)} />
              </label>
            )}
            {showReceiver && (
              <label className="field">
                <span className="field__label">Tổ / Người nhận</span>
                <input className="input" placeholder="VD: Tổ In 1 / Nguyễn Văn A" value={receiver} onChange={(e) => setReceiver(e.target.value)} />
              </label>
            )}
            <label className="field md-page__form-wide">
              <span className="field__label">Diễn giải / Lý do</span>
              <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>

          <div className="md-page__lines-head">
            <strong>Dòng hàng</strong>
            <Button type="button" variant="primary" onClick={() => setNewItemFor("new")}>+ Thêm mặt hàng</Button>
          </div>
          {lines.length === 0 ? (
            <div className="md-page__empty" style={{ padding: "22px 12px", textAlign: "center", border: "1px dashed var(--rule)", borderRadius: 8 }}>
              Chưa có mặt hàng nào. Bấm <strong>“+ Thêm mặt hàng”</strong> để chọn hoặc tạo mới.
            </div>
          ) : (
          <div className="md-page__tablewrap" style={{ marginTop: 0 }}>
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Vật tư</th>
                  {spec.showOnHand && <th>SL tồn</th>}
                  <th>{spec.qtyLabel}</th>
                  <th>Đơn vị</th>
                  {spec.showCost && <th>Đơn giá</th>}
                  {spec.showStatus && <th>Trạng thái</th>}
                  <th>Ghi chú</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, i) => {
                  const bal = l.material_id ? onHand[l.material_id] : undefined;
                  const over = spec.showOnHand && bal != null && Number(l.quantity) > bal;
                  return (
                  <tr key={i}>
                    <td>
                      <button type="button" className="input" style={{ textAlign: "left", cursor: "pointer", width: "100%", minWidth: 180 }}
                        onClick={() => setNewItemFor(i)}>
                        {l.material_id
                          ? (() => {
                              const m = matByIdForm.get(l.material_id);
                              if (!m) return `#${l.material_id}`;
                              return (<><div>{m.name}</div><div className="md-page__muted" style={{ fontSize: 12 }}>{m.code}</div></>);
                            })()
                          : <span className="md-page__muted">— Chọn mặt hàng —</span>}
                      </button>
                    </td>
                    {spec.showOnHand && (
                      <td className="md-page__mono" style={over ? { color: "var(--danger, #c0392b)", fontWeight: 600 } : undefined}>
                        {l.material_id ? (bal != null ? bal : "…") : "—"}
                      </td>
                    )}
                    <td><input className="input" type="number" step="0.001" style={{ width: 100 }} value={l.quantity || ""} onChange={(e) => setLine(i, { quantity: Number(e.target.value) })} /></td>
                    <td><input className="input" placeholder="ream/kg…" style={{ width: 90 }} value={l.uom ?? ""} onChange={(e) => setLine(i, { uom: e.target.value })} /></td>
                    {spec.showCost && (
                      <td><input className="input" type="number" step="1" placeholder="đ/đơn vị" style={{ width: 110 }} value={l.unit_cost ?? ""} onChange={(e) => setLine(i, { unit_cost: e.target.value ? Number(e.target.value) : null })} /></td>
                    )}
                    {spec.showStatus && (
                      <td>
                        <select className="input" value={l.status_id ?? ""} onChange={(e) => setLine(i, { status_id: e.target.value ? Number(e.target.value) : null })}>
                          {statuses.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                      </td>
                    )}
                    <td><input className="input" placeholder="Ghi chú" style={{ minWidth: 120 }} value={l.note ?? ""} onChange={(e) => setLine(i, { note: e.target.value })} /></td>
                    <td><button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => setLines((ls) => ls.filter((_, k) => k !== i))}>✕</button></td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
          {spec.showOnHand && lines.some((l) => l.material_id && onHand[l.material_id] != null && Number(l.quantity) > onHand[l.material_id]) && (
            <p className="md-page__muted" style={{ marginTop: 6, color: "var(--danger, #c0392b)" }}>
              ⚠ Có dòng xuất vượt tồn kho nguồn — sẽ bị chặn khi ghi sổ.
            </p>
          )}
          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu phiếu (nháp)</Button>
          </div>
        </form>
      </div>
      {quickLsx && (
        <ProductionOrderForm
          onClose={() => setQuickLsx(false)}
          onSaved={(created) => {
            setQuickLsx(false);
            const opt: ProductionOrderOption = { id: created.id, code: created.code, label: `${created.code}${created.product_name ? ` · ${created.product_name}` : ""}` };
            setLsxOptions((os) => [opt, ...os]);
            setLsxId(created.id);
            setPartner(created.code);
          }}
        />
      )}
      {/* CHỌN mặt hàng (chỉ chọn — tạo/sửa vật tư ở trang "Danh mục vật tư"). */}
      {newItemFor !== null && (
        <MaterialForm
          material={null}
          canUpdate={false}
          allowCreate={false}
          pickList={needDst
            // NHẬP: CHỈ vật tư thuộc kho đích (không lấy vật tư cũ chưa gán / kho khác).
            ? allMaterials.filter((m) => effDst != null && m.warehouse_id === effDst)
            // XUẤT: chỉ mặt hàng đang có tồn ở kho nguồn.
            : allMaterials.filter((m) => inKhoIds.has(m.id))}
          onPickExisting={(m) => { const t = newItemFor; setNewItemFor(null); if (t !== null) applyMaterialToLine(t, m); }}
          onClose={() => setNewItemFor(null)}
          onSaved={() => setNewItemFor(null)}
        />
      )}
    </div>
  );
}
// Định dạng ngày/số cho màn chi tiết.
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  return d && m && y ? `${d}/${m}/${y}` : s;
}
function fmtDateTime(s: string | null): string {
  if (!s) return "—";
  const dt = new Date(s);
  return isNaN(dt.getTime()) ? s : dt.toLocaleString("vi-VN");
}
function fmtNum(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}
function escHtml(v: unknown): string {
  return String(v ?? "—").replace(/[&<>]/g, (c) => (c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"));
}

// Thông tin công ty in trên phiếu — Sao Việt Nhật. Trường pháp lý để trống ("—")
// chờ khảo sát, điền giá trị thật khi có (luật dự án: không hardcode số liệu).
const SVN_COMPANY = {
  name: "CÔNG TY SAO VIỆT NHẬT",
  address: "—",
  taxCode: "—",
  phone: "—",
};

function readTriple(value: number, full: boolean): string {
  const names = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"];
  const hundred = Math.floor(value / 100);
  const ten = Math.floor((value % 100) / 10);
  const unit = value % 10;
  const parts: string[] = [];
  if (hundred > 0 || full) parts.push(`${names[hundred]} trăm`);
  if (ten > 1) {
    parts.push(`${names[ten]} mươi`);
    if (unit === 1) parts.push("mốt");
    else if (unit === 4) parts.push("tư");
    else if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (ten === 1) {
    parts.push("mười");
    if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (unit > 0) {
    if (hundred > 0 || full) parts.push("lẻ");
    parts.push(names[unit]);
  }
  return parts.join(" ");
}
function amountInWords(amount: number): string {
  let value = Math.max(0, Math.round(amount));
  if (value === 0) return "Không đồng";
  const scales = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"];
  const groups: number[] = [];
  while (value > 0) { groups.push(value % 1000); value = Math.floor(value / 1000); }
  const parts: string[] = [];
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    if (groups[i] === 0) continue;
    parts.push(`${readTriple(groups[i], i < groups.length - 1 && groups[i] < 100)}${scales[i] ? ` ${scales[i]}` : ""}`);
  }
  const result = `${parts.join(" ")} đồng`;
  return result.charAt(0).toUpperCase() + result.slice(1);
}

/** In phiếu kho — hàm dùng chung: mở cửa sổ in với letterhead cty + bảng hàng + ô ký.
 * Dùng bởi VoucherDetail và bảng "phiếu lập từ đề nghị". Tự tính t/spec/tồn/giá từ opts. */
export function printVoucher(
  voucher: VoucherRow,
  opts: {
    types: KhoVoucherType[];
    warehouses: WarehouseRow[];
    materials: KhoMaterialOption[];
    statuses?: KhoItemStatus[];
    canPrice?: boolean;
  },
) {
  const { types, warehouses, materials, statuses = [], canPrice = false } = opts;
  const t = types.find((x) => x.id === voucher.voucher_type_id);
  const spec = specForType(t);
  const matById = new Map(materials.map((m) => [m.id, m]));
  const statusById = new Map(statuses.map((s) => [s.id, s.name]));
  const whLabel = (id: number | null) => {
    if (!id) return null;
    const w = warehouses.find((x) => x.id === id);
    return w ? `${w.code} · ${w.name}` : `#${id}`;
  };
  const khoText = [whLabel(voucher.src_warehouse_id), whLabel(voucher.dst_warehouse_id)].filter(Boolean).join("  →  ") || "—";
  const showCost = spec.showCost && canPrice;
  const totalQty = voucher.lines.reduce((s, l) => s + Number(l.quantity), 0);
  const totalValue = voucher.lines.reduce((s, l) => s + Number(l.quantity) * Number(l.unit_cost || 0), 0);

  const w = window.open("", "_blank", "width=920,height=1040");
  if (!w) return;
  const logoAbs = new URL(logoUrl, window.location.href).href;

  const dSrc = voucher.doc_date || (voucher.created_at ? voucher.created_at.slice(0, 10) : "");
  const [yy, mm, dd] = dSrc ? dSrc.split("-") : ["", "", ""];
  const dateLine = dd && mm && yy ? `Ngày ${dd} tháng ${mm} năm ${yy}` : "";

  const legal = [
    SVN_COMPANY.address !== "—" ? `Địa chỉ: ${escHtml(SVN_COMPANY.address)}` : "",
    SVN_COMPANY.taxCode !== "—" ? `MST: ${escHtml(SVN_COMPANY.taxCode)}` : "",
    SVN_COMPANY.phone !== "—" ? `Điện thoại: ${escHtml(SVN_COMPANY.phone)}` : "",
  ].filter(Boolean).map((x) => `<div>${x}</div>`).join("");

  const partyLabel = spec.partnerKind ? spec.partnerLabel : "Đối tượng";
  const partyRows = [
    [partyLabel, escHtml(voucher.partner_ref)],
    ["Kho", escHtml(khoText)],
    ...(voucher.receiver ? [["Tổ / Người nhận", escHtml(voucher.receiver)] as [string, string]] : []),
    ...(voucher.handover_at ? [["Đã bàn giao", `${escHtml(voucher.handover_by_name)} · ${fmtDateTime(voucher.handover_at)}`] as [string, string]] : []),
    ...(spec.refLabel && voucher.note ? [[spec.refLabel, escHtml(voucher.note)] as [string, string]] : []),
    ...(voucher.reason ? [["Diễn giải", escHtml(voucher.reason)] as [string, string]] : []),
  ].map(([k, v]) => `<div class="party__row"><span class="party__k">${k}:</span> <span class="party__v">${v}</span></div>`).join("");

  const lineRows = voucher.lines.map((l, i) => {
    const m = matById.get(l.material_id);
    const code = l.material_code ?? m?.code ?? "";
    const name = l.material_name ?? m?.name ?? `#${l.material_id}`;
    const val = Number(l.quantity) * Number(l.unit_cost || 0);
    return `<tr>
      <td class="c">${i + 1}</td>
      <td class="mono">${escHtml(code || "—")}</td>
      <td>${escHtml(name)}</td>
      <td class="c">${escHtml(l.uom || "—")}</td>
      <td class="r">${fmtNum(Number(l.quantity))}</td>
      ${showCost ? `<td class="r">${l.unit_cost != null ? fmtNum(Number(l.unit_cost)) : "—"}</td><td class="r">${l.unit_cost != null ? fmtNum(val) : "—"}</td>` : ""}
      ${spec.showStatus ? `<td>${escHtml(l.status_id != null ? statusById.get(l.status_id) ?? "—" : "—")}</td>` : ""}
      <td>${escHtml(l.note || "")}</td>
    </tr>`;
  }).join("");

  const footRows = `<tr class="foot">
    <td colspan="4" class="r">Cộng</td>
    <td class="r">${fmtNum(totalQty)}</td>
    ${showCost ? `<td></td><td class="r">${fmtNum(totalValue)}</td>` : ""}
    ${spec.showStatus ? `<td></td>` : ""}
    <td></td>
  </tr>`;

  w.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>${escHtml(voucher.code)}</title>
<style>
  * { font-family: 'Times New Roman', 'Segoe UI', serif; box-sizing: border-box; }
  body { margin: 0; color: #111; font-size: 13.5px; line-height: 1.4; }
  .sheet { padding: 16mm 14mm; }
  .head { display: flex; align-items: flex-start; gap: 14px; padding-bottom: 8px; margin-bottom: 4px; }
  .head img { height: 60px; }
  .company__name { font-size: 16px; font-weight: 700; text-transform: uppercase; }
  .company__legal { font-size: 12.5px; color: #222; margin-top: 2px; }
  .company__legal div { margin: 1px 0; }
  h1 { font-size: 22px; text-align: center; margin: 14px 0 4px; text-transform: uppercase; font-weight: 700; letter-spacing: .5px; }
  .datebar { text-align: center; font-size: 13px; margin-bottom: 2px; }
  .docno { text-align: center; font-size: 13px; margin-bottom: 12px; }
  .docno b { letter-spacing: .5px; }
  .status-tag { color: #8a1f1f; font-weight: 700; }
  .party { margin-bottom: 12px; }
  .party__row { margin: 2px 0; }
  .party__k { color: #333; }
  .party__v { font-weight: 700; }
  table.lines { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
  table.lines th, table.lines td { border: 1px solid #333; padding: 6px 8px; font-size: 13px; vertical-align: top; }
  table.lines th { background: #eee; text-align: center; font-weight: 700; }
  td.r, th.r { text-align: right; } td.c, th.c { text-align: center; }
  td.mono { font-family: 'Consolas', monospace; font-size: 12.5px; white-space: nowrap; }
  tr.foot td { font-weight: 700; background: #f6f6f6; }
  .words { margin: 6px 0 4px; font-size: 13px; }
  .words b { font-style: italic; }
  .status-note { font-size: 12.5px; color: #555; margin: 2px 0 10px; }
  .sign { display: flex; justify-content: space-around; gap: 10px; margin-top: 34px; text-align: center; font-size: 12.5px; }
  .sign > div { flex: 1 1 0; max-width: 33%; }
  .sign__role { line-height: 1.25; }
  .sign__role { font-weight: 700; }
  .sign__hint { font-style: italic; font-size: 12px; color: #444; }
  .sign__space { height: 78px; }
  @media print { .sheet { padding: 12mm; } body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head>
<body onload="window.print()" onafterprint="window.close()">
  <div class="sheet">
    <div class="head">
      <img src="${logoAbs}" alt="logo">
      <div>
        <div class="company__name">${escHtml(SVN_COMPANY.name)}</div>
        ${legal ? `<div class="company__legal">${legal}</div>` : ""}
      </div>
    </div>

    <h1>${escHtml(t?.name ?? "Phiếu kho")}</h1>
    ${dateLine ? `<div class="datebar">${dateLine}</div>` : ""}
    <div class="docno">Số: <b>${escHtml(voucher.code)}</b></div>

    <div class="party">
      ${partyRows}
      <div class="party__row"><span class="party__k">Người lập:</span> <span class="party__v">${escHtml(voucher.created_by_name)}</span> · <span class="party__k">Ngày lập:</span> ${fmtDateTime(voucher.created_at)}${voucher.approved_at ? ` · <span class="party__k">Ngày duyệt:</span> ${fmtDateTime(voucher.approved_at)}` : ""}</div>
    </div>

    <table class="lines">
      <thead><tr>
        <th class="c" style="width:34px">STT</th><th style="width:110px">Mã hàng</th><th>Tên hàng</th><th class="c" style="width:56px">ĐVT</th>
        <th class="r" style="width:80px">${escHtml(spec.qtyLabel)}</th>
        ${showCost ? `<th class="r" style="width:96px">Đơn giá</th><th class="r" style="width:110px">Thành tiền</th>` : ""}
        ${spec.showStatus ? `<th style="width:90px">Trạng thái</th>` : ""}
        <th style="width:120px">Ghi chú</th>
      </tr></thead>
      <tbody>${lineRows}${footRows}</tbody>
    </table>

    ${showCost ? `<div class="words">Số tiền bằng chữ: <b>${escHtml(amountInWords(totalValue))}</b></div>` : ""}
    ${voucher.status !== "posted" ? `<div class="status-note">Trạng thái phiếu: <span class="status-tag">${escHtml(STATUS_LABEL[voucher.status] ?? voucher.status)}</span></div>` : ""}

    <div class="sign">
      ${signRolesFor(t, spec).map((role) => `<div><div class="sign__role">${escHtml(role)}</div><div class="sign__hint">(Ký, họ tên)</div><div class="sign__space"></div></div>`).join("")}
    </div>
  </div>
</body></html>`);
  w.document.close();
}

/** In chứng từ kho DẠNG CHUNG (letterhead cty + bảng + ô ký) — cùng bộ khung với phiếu kho.
 * Dùng cho phiếu đề nghị (và các chứng từ kho khác) để đồng bộ giao diện in. */
export function openKhoPrint(opts: {
  title: string;
  code: string;
  dateLine?: string;
  metaRows: [string, string][];
  columns: { label: string; align?: "l" | "r" | "c"; width?: string }[];
  rows: (string | number)[][];
  footRow?: (string | number)[];
  note?: string;
  signRoles: string[];
}) {
  const w = window.open("", "_blank", "width=920,height=1040");
  if (!w) return;
  const logoAbs = new URL(logoUrl, window.location.href).href;
  const legal = [
    SVN_COMPANY.address !== "—" ? `Địa chỉ: ${escHtml(SVN_COMPANY.address)}` : "",
    SVN_COMPANY.taxCode !== "—" ? `MST: ${escHtml(SVN_COMPANY.taxCode)}` : "",
    SVN_COMPANY.phone !== "—" ? `Điện thoại: ${escHtml(SVN_COMPANY.phone)}` : "",
  ].filter(Boolean).map((x) => `<div>${x}</div>`).join("");
  const ac = (a?: string) => (a === "r" ? "r" : a === "c" ? "c" : "");
  const thead = opts.columns
    .map((c) => `<th class="${ac(c.align)}"${c.width ? ` style="width:${c.width}"` : ""}>${escHtml(c.label)}</th>`)
    .join("");
  const body = opts.rows
    .map((r) => `<tr>${r.map((cell, i) => `<td class="${ac(opts.columns[i]?.align)}">${escHtml(cell)}</td>`).join("")}</tr>`)
    .join("");
  const foot = opts.footRow
    ? `<tr class="foot">${opts.footRow.map((cell, i) => `<td class="${ac(opts.columns[i]?.align)}">${escHtml(cell)}</td>`).join("")}</tr>`
    : "";
  const meta = opts.metaRows
    .map(([k, v]) => `<div class="party__row"><span class="party__k">${escHtml(k)}:</span> <span class="party__v">${escHtml(v)}</span></div>`)
    .join("");
  w.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>${escHtml(opts.code)}</title>
<style>
  * { font-family: 'Times New Roman', 'Segoe UI', serif; box-sizing: border-box; }
  body { margin: 0; color: #111; font-size: 13.5px; line-height: 1.4; }
  .sheet { padding: 16mm 14mm; }
  .head { display: flex; align-items: flex-start; gap: 14px; padding-bottom: 8px; margin-bottom: 4px; }
  .head img { height: 60px; }
  .company__name { font-size: 16px; font-weight: 700; text-transform: uppercase; }
  .company__legal { font-size: 12.5px; color: #222; margin-top: 2px; }
  .company__legal div { margin: 1px 0; }
  h1 { font-size: 22px; text-align: center; margin: 14px 0 4px; text-transform: uppercase; font-weight: 700; letter-spacing: .5px; }
  .datebar { text-align: center; font-size: 13px; margin-bottom: 2px; }
  .docno { text-align: center; font-size: 13px; margin-bottom: 12px; }
  .docno b { letter-spacing: .5px; }
  .status-tag { color: #8a1f1f; font-weight: 700; }
  .party { margin-bottom: 12px; }
  .party__row { margin: 2px 0; }
  .party__k { color: #333; }
  .party__v { font-weight: 700; }
  table.lines { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
  table.lines th, table.lines td { border: 1px solid #333; padding: 6px 8px; font-size: 13px; vertical-align: top; }
  table.lines th { background: #eee; text-align: center; font-weight: 700; }
  td.r, th.r { text-align: right; } td.c, th.c { text-align: center; }
  tr.foot td { font-weight: 700; background: #f6f6f6; }
  .status-note { font-size: 12.5px; color: #555; margin: 2px 0 10px; }
  .sign { display: flex; justify-content: space-around; gap: 10px; margin-top: 34px; text-align: center; font-size: 12.5px; }
  .sign > div { flex: 1 1 0; max-width: 33%; }
  .sign__role { line-height: 1.25; font-weight: 700; }
  .sign__hint { font-style: italic; font-size: 12px; color: #444; }
  .sign__space { height: 78px; }
  @media print { .sheet { padding: 12mm; } body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head>
<body onload="window.print()" onafterprint="window.close()">
  <div class="sheet">
    <div class="head">
      <img src="${logoAbs}" alt="logo">
      <div>
        <div class="company__name">${escHtml(SVN_COMPANY.name)}</div>
        ${legal ? `<div class="company__legal">${legal}</div>` : ""}
      </div>
    </div>
    <h1>${escHtml(opts.title)}</h1>
    ${opts.dateLine ? `<div class="datebar">${escHtml(opts.dateLine)}</div>` : ""}
    <div class="docno">Số: <b>${escHtml(opts.code)}</b></div>
    <div class="party">${meta}</div>
    <table class="lines">
      <thead><tr>${thead}</tr></thead>
      <tbody>${body}${foot}</tbody>
    </table>
    ${opts.note ? `<div class="status-note">${escHtml(opts.note)}</div>` : ""}
    <div class="sign">
      ${opts.signRoles.map((role) => `<div><div class="sign__role">${escHtml(role)}</div><div class="sign__hint">(Ký, họ tên)</div><div class="sign__space"></div></div>`).join("")}
    </div>
  </div>
</body></html>`);
  w.document.close();
}

export function VoucherDetail({
  voucher, types, warehouses, materials, statuses = [], canApprove, canCreate, onClose, onChanged,
}: {
  voucher: VoucherRow; types: KhoVoucherType[]; warehouses: WarehouseRow[]; materials: KhoMaterialOption[];
  statuses?: KhoItemStatus[];
  canApprove: boolean; canCreate: boolean; onClose: () => void; onChanged: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canPrice = can("kho", "manage_price");
  const canConfirm = canCreate || can("kho", "manage_status"); // xác nhận nhận vật tư
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = types.find((x) => x.id === voucher.voucher_type_id);
  const spec = specForType(t);
  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  const statusById = useMemo(() => new Map(statuses.map((s) => [s.id, s.name])), [statuses]);
  const whLabel = (id: number | null) => {
    if (!id) return null;
    const w = warehouses.find((x) => x.id === id);
    return w ? `${w.code} · ${w.name}` : `#${id}`;
  };
  const khoText = [whLabel(voucher.src_warehouse_id), whLabel(voucher.dst_warehouse_id)].filter(Boolean).join("  →  ") || "—";

  // Tồn hiện tại theo vật tư (kho của phiếu) — tham chiếu trên dòng sản phẩm.
  const stockWh = voucher.dst_warehouse_id ?? voucher.src_warehouse_id;
  const [stockMap, setStockMap] = useState<Map<number, number>>(new Map());
  useEffect(() => {
    if (!token || !stockWh) { setStockMap(new Map()); return; }
    api.kho.stock(token, { warehouse_id: stockWh }).then((r) => {
      const mm = new Map<number, number>();
      for (const b of r.items) mm.set(b.material_id, (mm.get(b.material_id) ?? 0) + b.on_hand);
      setStockMap(mm);
    }).catch(() => {});
  }, [token, stockWh]);

  // Chứng từ đính kèm — thêm/xóa khi phiếu còn Nháp/Chờ duyệt.
  const [atts, setAtts] = useState<VoucherAttachment[]>([]);
  const [attBusy, setAttBusy] = useState(false);
  const canEditAtt = canCreate && (voucher.status === "draft" || voucher.status === "pending");
  const loadAtts = useCallback(() => {
    if (!token) return;
    api.kho.voucherAttachments(token, voucher.id).then((r) => setAtts(r.items)).catch(() => {});
  }, [token, voucher.id]);
  useEffect(() => { loadAtts(); }, [loadAtts]);

  // Truy vết ngược Mức A — phiếu gắn LSX nào (ref_type='lsx'): nạp mã LSX để hiển thị.
  const [lsxCode, setLsxCode] = useState<string | null>(null);
  useEffect(() => {
    if (!token || voucher.ref_type !== "lsx" || !voucher.ref_id) { setLsxCode(null); return; }
    api.production.getOrder(token, voucher.ref_id).then((o) => setLsxCode(o.code)).catch(() => setLsxCode(null));
  }, [token, voucher.ref_type, voucher.ref_id]);

  async function onUploadFiles(list: FileList | null) {
    if (!token || !list || !list.length) return;
    setAttBusy(true); setError(null);
    try { for (const f of Array.from(list)) await api.kho.uploadVoucherAttachment(token, voucher.id, f); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Tải file thất bại."); }
    finally { setAttBusy(false); }
  }
  async function onDeleteAtt(aid: number) {
    if (!token) return;
    setAttBusy(true); setError(null);
    try { await api.kho.deleteVoucherAttachment(token, voucher.id, aid); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Xóa file thất bại."); }
    finally { setAttBusy(false); }
  }

  const showCost = spec.showCost && canPrice;
  const totalQty = voucher.lines.reduce((s, l) => s + Number(l.quantity), 0);
  const totalValue = voucher.lines.reduce((s, l) => s + Number(l.quantity) * Number(l.unit_cost || 0), 0);

  // In phiếu kho — dùng hàm dùng chung printVoucher (cũng được bảng "phiếu từ đề nghị" gọi lại).
  const onPrint = () => printVoucher(voucher, { types, warehouses, materials, statuses, canPrice });

  async function act(fn: () => Promise<VoucherRow>) {
    if (!token || busy) return;
    setBusy(true); setError(null);
    try { await fn(); onChanged(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Thao tác thất bại."); setBusy(false); }
  }

  const st = V_STATUS_STYLE[voucher.status] ?? V_STATUS_STYLE.draft;
  const infoItems: [string, ReactNode][] = [
    ["Loại phiếu", t?.name ?? `#${voucher.voucher_type_id}`],
    ["Ngày phiếu", fmtDate(voucher.doc_date)],
    ["Kho", khoText],
    ...(voucher.ref_type === "lsx" && voucher.ref_id
      ? [["Lệnh sản xuất", <span className="md-page__mono">{lsxCode ?? `#${voucher.ref_id}`}</span>] as [string, ReactNode]]
      : []),
    ...(voucher.receiver ? [["Tổ / Người nhận", voucher.receiver] as [string, ReactNode]] : []),
    ...(voucher.handover_at ? [["Đã bàn giao", `${voucher.handover_by_name ?? ""} · ${fmtDateTime(voucher.handover_at)}`] as [string, ReactNode]] : []),
    ...(voucher.note ? [["Chứng từ", voucher.note] as [string, ReactNode]] : []),
    ["Người nhập", voucher.created_by_name || "—"],
    ["Ngày tạo", fmtDateTime(voucher.created_at)],
    ...(voucher.approved_at ? [["Ngày duyệt", fmtDateTime(voucher.approved_at)] as [string, ReactNode]] : []),
  ];

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 900, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2 style={{ display: "flex", alignItems: "center" }}>
            Chi tiết phiếu&nbsp;<span className="md-page__mono">{voucher.code}</span>
            <span className="vd__status" style={{ background: st.bg, color: st.color }}>
              {STATUS_LABEL[voucher.status] ?? voucher.status}
            </span>
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <div className="vd__grid">
            {/* Khối đối tượng — nhãn theo loại phiếu (NCC / Khách hàng / LSX / Bộ phận) */}
            <section className="vd__card vd__card--party">
              <p className="vd__eyebrow">{spec.partnerKind ? spec.partnerLabel : "Đối tượng"}</p>
              {voucher.partner_ref ? (
                <div className="vd__party-name">{voucher.partner_ref}</div>
              ) : (
                <p className="md-page__muted" style={{ margin: 0 }}>— Nội bộ / không có đối tượng —</p>
              )}
              {voucher.reason && (
                <p style={{ margin: "10px 0 0", fontSize: 13.5 }}>
                  <span className="md-page__muted">Diễn giải: </span>{voucher.reason}
                </p>
              )}
            </section>

            {/* Thông tin phiếu */}
            <section className="vd__card">
              <p className="vd__eyebrow">Thông tin phiếu</p>
              <dl className="vd__kv">
                {infoItems.map(([k, v]) => (
                  <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>
                ))}
              </dl>
            </section>
          </div>

          <div>
          <p className="vd__section-title">Sản phẩm</p>
          <div className="md-page__tablewrap vd__lines" style={{ marginTop: 4 }}>
            <table className="md-page__table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th style={{ width: 90 }}>Mã</th>
                  <th>Tên sản phẩm</th>
                  <th>ĐVT</th>
                  <th style={{ textAlign: "right" }}>Tồn hiện tại</th>
                  <th style={{ textAlign: "right" }}>{spec.qtyLabel}</th>
                  {showCost && <th style={{ textAlign: "right" }}>Đơn giá</th>}
                  {showCost && <th style={{ textAlign: "right" }}>Thành tiền</th>}
                  {spec.showStatus && <th>Trạng thái</th>}
                  <th>NCC</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {voucher.lines.map((l, i) => {
                  const m = matById.get(l.material_id);
                  const name = l.material_name ?? m?.name ?? `#${l.material_id}`;
                  const code = l.material_code ?? m?.code ?? null;
                  const onHand = stockMap.get(l.material_id);
                  return (
                    <tr key={l.id}>
                      <td>{i + 1}</td>
                      <td className="md-page__mono">{code || <span className="md-page__muted">—</span>}</td>
                      <td>{name}</td>
                      <td>{l.uom || "—"}</td>
                      <td style={{ textAlign: "right" }} className="vd__num">{onHand != null ? onHand.toLocaleString("vi-VN") : <span className="md-page__muted">—</span>}</td>
                      <td style={{ textAlign: "right" }} className="vd__num vd__qty">{fmtNum(Number(l.quantity))}</td>
                      {showCost && <td style={{ textAlign: "right" }}>{l.unit_cost != null ? fmtNum(Number(l.unit_cost)) : "—"}</td>}
                      {showCost && <td style={{ textAlign: "right" }}>{l.unit_cost != null ? fmtNum(Number(l.quantity) * Number(l.unit_cost)) : "—"}</td>}
                      {spec.showStatus && <td>{l.status_id != null ? statusById.get(l.status_id) ?? "—" : "—"}</td>}
                      <td>{m?.default_supplier || <span className="md-page__muted">—</span>}</td>
                      <td>{l.note || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={5} style={{ fontWeight: 700 }}>Tổng cộng</td>
                  <td className="vd__total" style={{ textAlign: "right" }}>{fmtNum(totalQty)}</td>
                  {showCost && <td />}
                  {showCost && <td className="vd__total" style={{ textAlign: "right" }}>{fmtNum(totalValue)}</td>}
                  <td colSpan={(spec.showStatus ? 1 : 0) + 2} />
                </tr>
              </tfoot>
            </table>
          </div>
          </div>

          <div>
          <p className="vd__section-title">Đính kèm chứng từ</p>
          {atts.length > 0 && (
            <ul className="md-page__filelist" style={{ marginBottom: 8 }}>
              {atts.map((a) => (
                <li key={a.id}>
                  <a className="md-page__file-name" href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">📎 {a.file_name}</a>
                  {canEditAtt && <button type="button" className="md-page__file-x" disabled={attBusy} onClick={() => onDeleteAtt(a.id)}>✕</button>}
                </li>
              ))}
            </ul>
          )}
          {atts.length === 0 && !canEditAtt && <p className="md-page__muted" style={{ margin: 0 }}>Chưa có file đính kèm.</p>}
          {canEditAtt && (
            <label className="vd__filebtn">
              📎 Đính kèm tệp
              <input type="file" multiple disabled={attBusy}
                onChange={(e) => { onUploadFiles(e.target.files); e.target.value = ""; }} />
            </label>
          )}
          </div>

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onPrint}>🖨 In phiếu</Button>
            {/* Xác nhận đã bàn giao/nhận vật tư (BRD §2.5) — phiếu xuất theo LSX, đã ghi sổ. */}
            {voucher.status === "posted" && voucher.ref_type === "lsx" && (
              voucher.handover_at
                ? <span className="md-page__muted" style={{ alignSelf: "center", fontSize: 13, color: "#244a2e" }}>✓ Đã bàn giao{voucher.handover_by_name ? ` · ${voucher.handover_by_name}` : ""} · {fmtDateTime(voucher.handover_at)}</span>
                : canConfirm ? <Button variant="primary" onClick={() => act(() => api.kho.confirmReceipt(token!, voucher.id))} loading={busy}>Xác nhận đã nhận vật tư</Button> : null
            )}
            <div style={{ flex: 1 }} />
            {voucher.status === "draft" && canCreate && (
              <>
                <Button variant="danger" onClick={() => act(() => api.kho.cancelVoucher(token!, voucher.id))} loading={busy}>Hủy phiếu</Button>
                <Button variant="primary" onClick={() => act(() => api.kho.submitVoucher(token!, voucher.id))} loading={busy}>Nộp phiếu</Button>
              </>
            )}
            {voucher.status === "pending" && (
              <>
                {canCreate && <Button variant="danger" onClick={() => act(() => api.kho.cancelVoucher(token!, voucher.id))} loading={busy}>Hủy</Button>}
                {canApprove && <Button variant="primary" onClick={() => act(() => api.kho.approveVoucher(token!, voucher.id))} loading={busy}>Duyệt & ghi sổ</Button>}
              </>
            )}
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
