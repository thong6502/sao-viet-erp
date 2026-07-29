// Bảng ĐƠN GIÁ khoán dùng chung ở 2 nơi:
//  - Tab "Lương khoán" tổng (departmentId = null) → mọi tổ, có ô chọn "Tổ".
//  - Panel Cấu hình lương của TỔ (departmentId = <id>) → chỉ tổ đó; tự gắn department_id +
//    group_name = tên tổ, ẩn ô "Tổ" (tổ suy từ ngữ cảnh).
// CRUD lưu ngay qua modal (độc lập với nút "Lưu thay đổi" của cấu hình component).
import { useCallback, useEffect, useState } from "react";
import { api, type PieceRate, type PieceRateInput } from "../api/client";
import { money } from "../utils/format";

// Tổ khoán (nhãn) — chỉ dùng cho ô chọn ở tab tổng.
const KHOAN_GROUPS: { key: string; label: string }[] = [
  { key: "to_boi", label: "Tổ Bồi" },
  { key: "to_can_phu", label: "Tổ Cán/Phủ" },
  { key: "to_cat", label: "Tổ Cắt" },
  { key: "may_in_5mau", label: "Máy in 5 màu" },
  { key: "may_in_2mau", label: "Máy in 2 màu" },
  { key: "to_thanh_pham", label: "Tổ Thành phẩm" },
];
const KHOAN_GROUP_LABEL: Record<string, string> = Object.fromEntries(
  KHOAN_GROUPS.map((g) => [g.key, g.label]),
);
// ⚠️ KHÔNG còn bảng dịch mã→nhãn cho đơn vị (chủ 29/07/2026). `unit` lưu thẳng CHỮ HIỂN THỊ và
// người dùng GÕ TỰ DO; gợi ý lấy từ `GET /khoan/units` = mồi mặc định ∪ đơn vị nhà máy đã dùng.
// Dựng lại danh sách cứng ở đây là trói lại đúng thứ vừa mở ra.

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

export function KhoanRatesEditor({
  token,
  departmentId = null,
  deptName,
}: {
  token: string;
  departmentId?: number | null;
  deptName?: string;
}) {
  const perDept = departmentId != null;
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [editing, setEditing] = useState<PieceRate | "new" | null>(null);
  // Gợi ý cho ô "Đơn vị". Nạp lại sau mỗi lần lưu để đơn vị vừa gõ xuất hiện ngay lần sau.
  const [units, setUnits] = useState<string[]>([]);
  const load = useCallback(() => {
    api.luong
      .khoanRates(token, departmentId)
      .then((r) => setRates(r.items))
      .catch(() => setRates([]));
    api.luong
      .khoanUnits(token)
      .then((r) => setUnits(r.items))
      .catch(() => setUnits([]));
  }, [token, departmentId]);
  useEffect(() => {
    load();
  }, [load]);
  async function remove(id: number) {
    await api.luong.deleteKhoanRate(token, id);
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
          {perDept ? "Đơn giá khoán của tổ" : "Đơn giá khoán theo tổ"}
        </h4>
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          + Thêm đơn giá
        </button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr>
              {!perDept && <th>Tổ</th>}
              <th>Mã</th>
              <th>Công việc</th>
              <th>Đơn vị</th>
              <th className="lg-num">Đơn giá</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r) => (
              <tr key={r.id}>
                {!perDept && <td>{KHOAN_GROUP_LABEL[r.group_name] ?? r.group_name}</td>}
                <td>{r.code ?? "—"}</td>
                <td>{r.name}</td>
                <td>{r.unit}</td>
                <td className="lg-num">{money(r.unit_price)}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(r)}>
                    Sửa
                  </button>
                  <button
                    className="btn btn--ghost ns-danger"
                    onClick={() => remove(r.id)}
                  >
                    Xóa
                  </button>
                </td>
              </tr>
            ))}
            {rates.length === 0 && (
              <tr>
                <td colSpan={perDept ? 5 : 6} className="ns__empty">
                  Chưa có đơn giá khoán nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <KhoanRateModal
          token={token}
          rate={editing === "new" ? null : editing}
          departmentId={departmentId}
          deptName={deptName}
          units={units}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function KhoanRateModal({
  token,
  rate,
  departmentId = null,
  deptName,
  units,
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  departmentId?: number | null;
  deptName?: string;
  /** Gợi ý đơn vị — KHÔNG phải whitelist; gõ ngoài danh sách vẫn lưu được. */
  units: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const perDept = departmentId != null;
  const [group, setGroup] = useState(rate?.group_name ?? KHOAN_GROUPS[0].key);
  const [code, setCode] = useState(rate?.code ?? "");
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "m²");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    // Trong ngữ cảnh tổ: gắn department_id + group_name = tên tổ (nhãn). Tab tổng: dùng ô "Tổ".
    const input: PieceRateInput = {
      group_name: perDept ? (deptName ?? String(departmentId)).slice(0, 40) : group,
      department_id: departmentId,
      code: code || null,
      name,
      unit,
      unit_price: price,
      is_active: true,
    };
    try {
      if (rate) await api.luong.updateKhoanRate(token, rate.id, input);
      else await api.luong.createKhoanRate(token, input);
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {/* Thứ tự trường theo TẦM QUAN TRỌNG: tên công việc (thứ đang đặt tên) → đơn giá +
              đơn vị (cặp đi liền) → mã (không bắt buộc, để cuối). Bản cũ đặt "Mã (nếu có)" lên
              đầu và đẩy "Công việc *" xuống cuối — bắt buộc lại nằm dưới không bắt buộc. */}
          <div className="ns-grid">
            {!perDept && (
              <label className="ns-field ns-wizard__full">
                <span className="ns-field__label">Tổ *</span>
                <select value={group} onChange={(e) => setGroup(e.target.value)}>
                  {KHOAN_GROUPS.map((g) => (
                    <option key={g.key} value={g.key}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="ns-field ns-wizard__full">
              <span className="ns-field__label">Công việc *</span>
              <input
                value={name}
                autoFocus
                onChange={(e) => setName(e.target.value)}
                placeholder="vd: Bồi carton 3 lớp E,B"
              />
            </label>
            {/* GÕ TỰ DO + gợi ý, không phải <select> (chủ 29/07/2026). `datalist` cho phép
                chọn nhanh từ đơn vị đã dùng mà vẫn gõ được đơn vị mới. */}
            <label className="ns-field">
              <span className="ns-field__label">Đơn vị</span>
              <input
                list="khoan-units"
                value={unit}
                maxLength={24}
                placeholder="vd: m², kg, mét tới…"
                onChange={(e) => setUnit(e.target.value)}
              />
              <datalist id="khoan-units">
                {units.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá *</span>
              {/* Hậu tố ĐỘNG theo ô Đơn vị bên trái — "160.000 đ/m²" đọc thành câu ngay tại
                  chỗ, khỏi phải tự nối hai ô với nhau.
                  KHÔNG dùng `rc-input` của RebuildCatalog: nó khác bo góc / cỡ chữ / màu focus
                  so với `ns-field input`, đặt cạnh 3 ô kia là lạc lõng ngay. */}
              <div className="cl-suffixed">
                <input
                  type="number"
                  min={0}
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                />
                <span>đ/{unit.trim() || "đơn vị"}</span>
              </div>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Mã</span>
              <input
                value={code}
                placeholder="A–F, bỏ trống cũng được"
                onChange={(e) => setCode(e.target.value)}
              />
            </label>
            <p className="cc-card__hint ns-wizard__full" style={{ margin: 0 }}>
              Đơn vị gõ được tự do (kg, bộ, mét tới…); đơn vị đã dùng sẽ tự vào gợi ý lần sau.
            </p>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          {/* Thiếu tên công việc thì KHOÁ luôn, đừng để bấm xong mới báo đỏ. */}
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !name.trim()}
            title={!name.trim() ? "Nhập tên công việc trước" : undefined}
          >
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
