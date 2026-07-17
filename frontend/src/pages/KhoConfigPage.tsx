// Cấu hình cỗ máy chứng từ (spec-13): 2 tab — Loại phiếu (hành vi) + Trạng thái hàng.
// Gate dm_kho. Loại phiếu quyết định chiều tồn/duyệt; trạng thái quyết định tồn khả dụng.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, api, type KhoVoucherType, type KhoItemStatus } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const GROUP_LABEL: Record<string, string> = {
  nhap: "Nhập", xuat: "Xuất", dieu_chuyen: "Điều chuyển", kiem_ke: "Kiểm kê", dieu_chinh: "Điều chỉnh",
};
const EFFECT_LABEL: Record<string, string> = {
  tang: "Tăng tồn", giam: "Giảm tồn", chuyen_vi_tri: "Chuyển vị trí", khong_tac_dong: "Không tác động",
};

export function KhoConfigPage() {
  const can = useCan();
  const canWrite = can("dm_kho", "create") || can("dm_kho", "update");
  const canDelete = can("dm_kho", "delete");
  const [tab, setTab] = useState<"types" | "statuses">("types");
  const [forbidden, setForbidden] = useState(false);

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập (403).</div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục · Kho</p>
        <h1 className="md-page__title">Cấu hình phiếu kho</h1>
        <p className="md-page__sub">
          Cỗ máy chứng từ: <strong>Loại phiếu</strong> khai hành vi (chiều tồn, kho nguồn/đích,
          duyệt); <strong>Trạng thái hàng</strong> quyết định tồn khả dụng.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__tabs">
          <button type="button" className={`md-page__tab${tab === "types" ? " is-active" : ""}`} onClick={() => setTab("types")}>Loại phiếu</button>
          <button type="button" className={`md-page__tab${tab === "statuses" ? " is-active" : ""}`} onClick={() => setTab("statuses")}>Trạng thái hàng</button>
        </div>
      </div>

      {tab === "types"
        ? <VoucherTypesTab canWrite={canWrite} canDelete={canDelete} onForbidden={() => setForbidden(true)} />
        : <ItemStatusesTab canWrite={canWrite} canDelete={canDelete} onForbidden={() => setForbidden(true)} />}
    </main>
  );
}

// ============ Loại phiếu ============
function VoucherTypesTab({ canWrite, canDelete, onForbidden }: { canWrite: boolean; canDelete: boolean; onForbidden: () => void }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<KhoVoucherType[]>([]);
  const [editing, setEditing] = useState<KhoVoucherType | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.kho.voucherTypes(token).then((r) => setRows(r.items))
      .catch((e) => { if (e instanceof ApiError && e.isForbidden) onForbidden(); });
  }, [token, onForbidden]);
  useEffect(() => { load(); }, [load]);

  async function remove(id: number) {
    if (!token) return;
    try { await api.kho.removeVoucherType(token, id); load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Không xóa được."); }
  }

  return (
    <>
      <div className="md-page__toolbar">
        <div className="md-page__toolbar-spacer" />
        {canWrite && <Button variant="primary" onClick={() => setCreating(true)}>+ Tạo loại phiếu</Button>}
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}
      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead><tr><th>Mã</th><th>Tên</th><th className="md-page__actions-col">Thao tác</th></tr></thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id} className="md-page__row" onClick={canWrite ? () => setEditing(t) : undefined} style={canWrite ? undefined : { cursor: "default" }}>
                <td className="md-page__mono">{t.code}</td>
                <td><strong>{t.name}</strong></td>
                <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                  {canWrite && <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setEditing(t)}>Sửa</button>}
                  {canDelete && <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => remove(t.id)}>Xóa</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(creating || editing) && (
        <VoucherTypeForm existing={editing} onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={() => { setCreating(false); setEditing(null); load(); }} />
      )}
    </>
  );
}

// Tự suy hành vi từ MÃ (đỡ phải chọn tay): NK-→nhập/tăng, XK-→xuất/giảm, DC-→chuyển kho.
function inferBehavior(code: string): Pick<KhoVoucherType, "voucher_group" | "stock_effect" | "require_src_wh" | "require_dst_wh"> {
  const prefix = code.trim().toUpperCase().split("-")[0];
  if (prefix.startsWith("X")) return { voucher_group: "xuat", stock_effect: "giam", require_src_wh: true, require_dst_wh: false };
  if (prefix.startsWith("D")) return { voucher_group: "dieu_chuyen", stock_effect: "chuyen_vi_tri", require_src_wh: true, require_dst_wh: true };
  return { voucher_group: "nhap", stock_effect: "tang", require_src_wh: false, require_dst_wh: true };
}

function VoucherTypeForm({ existing, onClose, onSaved }: { existing: KhoVoucherType | null; onClose: () => void; onSaved: () => void }) {
  const { token } = useAuth();
  const [f, setF] = useState<Omit<KhoVoucherType, "id">>(() => existing ?? {
    code: "", name: "", ...inferBehavior(""),
    require_approval: true, sync_misa: false, is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<typeof f>) => setF((x) => ({ ...x, ...patch }));
  // Đổi mã → tự suy hành vi (trừ khi đang sửa loại cũ để giữ nguyên cấu hình).
  const onCode = (v: string) => setF((x) => ({ ...x, code: v, ...(existing ? {} : inferBehavior(v)) }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    if (!f.code.trim() || !f.name.trim()) return setError("Mã và tên bắt buộc.");
    setSaving(true); setError(null);
    try {
      if (existing) await api.kho.updateVoucherType(token, existing.id, f);
      else await api.kho.createVoucherType(token, f);
      onSaved();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Lưu thất bại."); setSaving(false); }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{existing ? `Sửa: ${existing.code}` : "Tạo loại phiếu"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field"><span className="field__label">Mã *</span>
              <input className="input" placeholder="VD: NK-TP (nhập) / XK-KH (xuất)" value={f.code} onChange={(e) => onCode(e.target.value)} /></label>
            <label className="field"><span className="field__label">Tên *</span>
              <input className="input" placeholder="VD: Nhập thành phẩm" value={f.name} onChange={(e) => set({ name: e.target.value })} /></label>
          </div>
          {/* Cho biết hệ tự nhận gì từ mã — người dùng không phải chọn. */}
          <p className="md-page__muted" style={{ marginTop: 4 }}>
            Tự nhận: <strong>{GROUP_LABEL[f.voucher_group] ?? f.voucher_group}</strong> ·{" "}
            <strong>{EFFECT_LABEL[f.stock_effect] ?? f.stock_effect}</strong> ·{" "}
            {f.require_approval ? "Cần duyệt" : "Ghi thẳng"}
            {" — "}<span className="md-page__muted">mã bắt đầu NK-=nhập, XK-=xuất, DC-=chuyển kho.</span>
          </p>

          <label className="md-page__check" style={{ marginTop: 8 }}>
            <input type="checkbox" checked={f.is_active} onChange={(e) => set({ is_active: e.target.checked })} /><span>Đang dùng</span>
          </label>

          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============ Trạng thái hàng ============
function ItemStatusesTab({ canWrite, canDelete, onForbidden }: { canWrite: boolean; canDelete: boolean; onForbidden: () => void }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<KhoItemStatus[]>([]);
  const [editing, setEditing] = useState<KhoItemStatus | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.kho.itemStatuses(token).then((r) => setRows(r.items))
      .catch((e) => { if (e instanceof ApiError && e.isForbidden) onForbidden(); });
  }, [token, onForbidden]);
  useEffect(() => { load(); }, [load]);

  async function remove(id: number) {
    if (!token) return;
    try { await api.kho.removeItemStatus(token, id); load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Không xóa được."); }
  }

  return (
    <>
      <div className="md-page__toolbar">
        <div className="md-page__toolbar-spacer" />
        {canWrite && <Button variant="primary" onClick={() => setCreating(true)}>+ Tạo trạng thái</Button>}
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}
      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead><tr><th>Mã</th><th>Tên</th><th>Tồn thực tế</th><th>Khả dụng</th><th>Được xuất</th><th className="md-page__actions-col">Thao tác</th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="md-page__row" onClick={canWrite ? () => setEditing(s) : undefined} style={canWrite ? undefined : { cursor: "default" }}>
                <td className="md-page__mono">{s.code}{s.is_system && <span className="md-page__chip" style={{ marginLeft: 6 }}>hệ thống</span>}</td>
                <td><strong>{s.name}</strong></td>
                <td>{s.count_on_hand ? "Có" : "Không"}</td>
                <td>{s.count_available ? "Có" : "Không"}</td>
                <td>{s.allow_issue ? "Có" : "Không"}</td>
                <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                  {canWrite && <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setEditing(s)}>Sửa</button>}
                  {canDelete && !s.is_system && <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => remove(s.id)}>Xóa</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(creating || editing) && (
        <ItemStatusForm existing={editing} onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={() => { setCreating(false); setEditing(null); load(); }} />
      )}
    </>
  );
}

function ItemStatusForm({ existing, onClose, onSaved }: { existing: KhoItemStatus | null; onClose: () => void; onSaved: () => void }) {
  const { token } = useAuth();
  const [f, setF] = useState(() => {
    if (existing) {
      const { code, name, count_on_hand, count_available, allow_issue, is_active } = existing;
      return { code, name, count_on_hand, count_available, allow_issue, display_order: 100, is_active } as Omit<KhoItemStatus, "id" | "is_system">;
    }
    return { code: "", name: "", count_on_hand: true, count_available: true, allow_issue: true, display_order: 100, is_active: true } as Omit<KhoItemStatus, "id" | "is_system">;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<typeof f>) => setF((x) => ({ ...x, ...patch }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    if (!f.code.trim() || !f.name.trim()) return setError("Mã và tên bắt buộc.");
    setSaving(true); setError(null);
    try {
      if (existing) await api.kho.updateItemStatus(token, existing.id, f);
      else await api.kho.createItemStatus(token, f);
      onSaved();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Lưu thất bại."); setSaving(false); }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{existing ? `Sửa: ${existing.code}` : "Tạo trạng thái hàng"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field"><span className="field__label">Mã *</span>
              <input className="input" placeholder="HOLD" value={f.code} onChange={(e) => set({ code: e.target.value })} /></label>
            <label className="field"><span className="field__label">Tên *</span>
              <input className="input" placeholder="Giữ chỗ" value={f.name} onChange={(e) => set({ name: e.target.value })} /></label>
          </div>
          <div className="md-page__checks">
            <label className="md-page__check"><input type="checkbox" checked={f.count_on_hand} onChange={(e) => set({ count_on_hand: e.target.checked })} /><span>Cộng vào tồn thực tế</span></label>
            <label className="md-page__check"><input type="checkbox" checked={f.count_available} onChange={(e) => set({ count_available: e.target.checked })} /><span>Cộng vào tồn khả dụng</span></label>
            <label className="md-page__check"><input type="checkbox" checked={f.allow_issue} onChange={(e) => set({ allow_issue: e.target.checked })} /><span>Được xuất kho</span></label>
            <label className="md-page__check"><input type="checkbox" checked={f.is_active} onChange={(e) => set({ is_active: e.target.checked })} /><span>Đang dùng</span></label>
          </div>
          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
