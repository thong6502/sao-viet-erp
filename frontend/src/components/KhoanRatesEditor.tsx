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
const UNIT_LABEL: Record<string, string> = {
  m2: "m²",
  bai_in: "bài in",
  tan: "tấn",
  cuon: "cuốn",
  luot: "lượt",
  hop: "hộp",
  to: "tờ",
  khac: "khác",
};

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
  const load = useCallback(() => {
    api.luong
      .khoanRates(token, departmentId)
      .then((r) => setRates(r.items))
      .catch(() => setRates([]));
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
                <td>{UNIT_LABEL[r.unit] ?? r.unit}</td>
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
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  departmentId?: number | null;
  deptName?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const perDept = departmentId != null;
  const [group, setGroup] = useState(rate?.group_name ?? KHOAN_GROUPS[0].key);
  const [code, setCode] = useState(rate?.code ?? "");
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "m2");
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
          <div className="ns-grid">
            {!perDept && (
              <label className="ns-field">
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
            <label className="ns-field">
              <span className="ns-field__label">Mã (A–F, nếu có)</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đơn vị</span>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                {Object.entries(UNIT_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá/đơn vị *</span>
              <input
                type="number"
                min={0}
                value={price}
                onChange={(e) => setPrice(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Công việc *</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="vd: Bồi carton 3 lớp E,B"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
