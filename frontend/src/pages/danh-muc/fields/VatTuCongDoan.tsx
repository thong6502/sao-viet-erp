// Tab VẬT TƯ của công đoạn (18/09/2026, mg `0316`): công đoạn tiêu thụ những món nào, mỗi món mang
// CÔNG THỨC ĐỊNH MỨC của riêng nó. Bước lệnh gắn công đoạn nào thì bung đúng danh sách này, số
// lượng thế quy cách lệnh vào công thức.
//
// Thay bảng "Đầu việc và định mức của tổ" (`DinhMucDauViec.tsx`, gỡ cùng ngày, mg `0320`) — trước
// đây vật tư treo DƯỚI từng đầu việc của tổ, nên muốn khai mực cho công đoạn In thì phải chọn một
// đầu việc trước đã. Nay một tầng phẳng: công đoạn → vật tư → công thức.
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { crud } from "../../../api/rebuildCatalog";
import { TrashIcon } from "../icons";
import type { Row, VatTuCongDoanRow } from "../types";
import { FormulaField } from "./FormulaField";
import { FormulaPopover } from "./FormulaPopover";

export function VatTuCongDoanField({ value, onChange }: {
  value: VatTuCongDoanRow[];
  onChange: (v: VatTuCongDoanRow[]) => void;
}) {
  const { token } = useAuth();
  // Danh mục Vật tư khác — nạp TẠI ĐÂY như ô cũ: đọc bản nhớ trước để bảng có tên ngay lúc mở.
  const [vatTu, setVatTu] = useState<Row[]>(
    () => (token && crud("/api/vat-lieu-kho/vat-tu-in-an").daNho(token, { active: true })) || []);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    const { nho, moi } = crud("/api/vat-lieu-kho/vat-tu-in-an").thamChieu(token, { active: true });
    if (nho) setVatTu(nho);
    moi.then((items) => { if (alive) setVatTu(items); })
      .catch(() => { if (alive && !nho) setVatTu([]); });
    return () => { alive = false; };
  }, [token]);
  const theoId = useMemo(() => new Map(vatTu.map((v) => [Number(v.id), v])), [vatTu]);

  // Dòng đang mở ô công thức. `neo` = nút vừa bấm (panel NỔI dán vào đó); `banDau` = công thức lúc
  // mở, để ✕/Esc trả ô về đúng chỗ cũ — ô công thức ghi thẳng vào form theo từng nhịp gõ.
  const [mo, setMo] = useState<{ id: number; neo: HTMLElement; banDau: string | null } | null>(null);
  const bat = (id: number, neo: HTMLElement, banDau: string | null) =>
    setMo(mo?.id === id ? null : { id, neo, banDau });
  const k = mo ? value.findIndex((v) => v.vat_tu_id === mo.id) : -1;
  const sua = (i: number, cong_thuc_luong: string | null) =>
    onChange(value.map((v, j) => (j === i ? { ...v, cong_thuc_luong } : v)));
  const huy = () => {
    if (!mo || k < 0) return;
    sua(k, mo.banDau);
    setMo(null);
  };

  return <div className="rc-bands rc-bands--dinh-muc">
    <div className="rc-dm-vt">
      <table className="rc-dinh-muc-table">
        <thead><tr>
          <th className="rc-col--left">Mã</th>
          <th className="rc-col--left">Tên vật tư</th>
          <th className="rc-col--unit">ĐVT</th>
          <th className="rc-col--left" title="Ra LƯỢNG theo ĐVT của vật tư — bỏ trống thì bước lệnh không bung dòng này.">
            Công thức định mức
          </th>
          <th className="rc-col--center" style={{ width: 36 }} />
        </tr></thead>
        <tbody>
          {value.length === 0 && <tr><td colSpan={5} className="rc-bands__empty">
            Chưa khai vật tư nào — chọn ở ô bên dưới.
          </td></tr>}
          {value.map((v, i) => { const vt = theoId.get(v.vat_tu_id); return (
            <tr key={v.vat_tu_id}>
              <td className="rc-col--left">
                <button type="button" className={`rc-dm-vt__pill ${mo?.id === v.vat_tu_id ? "is-open" : ""}`}
                  onClick={(e) => bat(v.vat_tu_id, e.currentTarget, v.cong_thuc_luong ?? null)}>
                  {String(vt?.ma ?? `#${v.vat_tu_id}`)}
                </button>
              </td>
              <td className="rc-col--left">{String(vt?.ten ?? "(đã gỡ khỏi danh mục)")}</td>
              <td className="rc-col--unit">{String(vt?.don_vi_gia ?? "—")}</td>
              <td className="rc-col--left rc-dinh-muc-unit">
                <button type="button" title="Sửa công thức định mức của món này"
                  className={`rc-ct-cell ${mo?.id === v.vat_tu_id ? "is-open" : ""} ${v.cong_thuc_luong ? "" : "is-empty"}`}
                  onClick={(e) => bat(v.vat_tu_id, e.currentTarget, v.cong_thuc_luong ?? null)}>
                  {v.cong_thuc_luong || "—"}
                </button>
              </td>
              <td className="rc-col--center">
                <button type="button" className="rc-bands__del" title="Bỏ vật tư khỏi công đoạn"
                  onClick={() => onChange(value.filter((_, j) => j !== i))}>
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ); })}
        </tbody>
      </table>
      <select className="rc-dinh-muc-add__select" value="" aria-label="Thêm vật tư"
        onChange={(e) => { const id = Number(e.target.value); if (id)
          onChange([...value, { vat_tu_id: id, cong_thuc_luong: null }]); }}>
        <option value="">＋ chọn từ danh mục vật tư khác</option>
        {vatTu.filter((v) => !value.some((x) => x.vat_tu_id === Number(v.id))).map((v) => (
          <option key={v.id} value={v.id}>{String(v.ma)} · {String(v.ten)} ({String(v.don_vi_gia ?? "—")})</option>
        ))}
      </select>
      <p className="rc-dm-vt__note">
        Định mức khai <b>theo từng món</b>: mực ăn theo số tờ, dung môi rửa máy ăn theo số màu.
      </p>
    </div>
    {mo && k >= 0 && <FormulaPopover neo={mo.neo} nhan="Công thức định mức"
      onClose={() => setMo(null)} onHuy={huy}>
      <FormulaField
        id={`ct-vt-${mo.id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
        nhanO="Công thức định mức" onDong={huy}
        goY="Ra LƯỢNG theo ĐVT của vật tư. vd mực ăn theo số tờ: sl_vao / 40000 · dung môi rửa máy ăn theo số màu: so_mau * 0.3. Bỏ trống = bước lệnh KHÔNG bung dòng này."
        value={value[k].cong_thuc_luong ?? ""}
        onChange={(nv) => sua(k, nv)} />
    </FormulaPopover>}
  </div>;
}
