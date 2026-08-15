// ĐỊNH MỨC ĐẦU VIỆC của một công đoạn: năng suất khoán · định mức nhân lực · vật tư tiêu thụ.
//
// `donViVao` vẫn nằm trong props (chỗ gọi truyền vào) nhưng KHÔNG dùng nữa: đơn vị năng suất giờ
// do người khai chọn ở từng dòng, không còn suy theo đơn vị vào của công đoạn.
import { Fragment, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { crud } from "../../../api/rebuildCatalog";
import { TrashIcon } from "../icons";
import type { DinhMucRow, Row } from "../types";

export function DinhMucDauViecField({ value, options, departmentId, onChange }: {
  value: DinhMucRow[]; options: Row[]; departmentId: number | null; donViVao: string;
  onChange: (v: DinhMucRow[]) => void;
}) {
  const { token } = useAuth();
  const allowed = options.filter((o) => Number(o.department_id) === departmentId);
  const selected = new Set(value.map((r) => r.piece_rate_id));
  const patch = (i: number, p: Partial<DinhMucRow>) => onChange(value.map((r, j) => j === i ? { ...r, ...p } : r));

  // Danh mục Vật tư khác cho dropdown gắn vật tư. Nạp TẠI ĐÂY chứ không qua `refData` chung: cột
  // này là danh mục thứ HAI của cùng một field, mà bộ nạp chung khoá theo một `refPrefix` mỗi field.
  const [vatTu, setVatTu] = useState<Row[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true })
      .then((r) => { if (alive) setVatTu(r.items); })
      .catch(() => { if (alive) setVatTu([]); });
    return () => { alive = false; };
  }, [token]);
  const vatTuTheoId = useMemo(() => new Map(vatTu.map((v) => [Number(v.id), v])), [vatTu]);
  // Hàng phụ đang mở — mỗi lúc một dòng, mở cái khác thì cái cũ đóng (bảng đã 10 cột, bung hai
  // hàng cùng lúc là mất dấu dòng nào của ai).
  const [moVatTu, setMoVatTu] = useState<number | null>(null);
  return <div className="rc-bands rc-bands--dinh-muc">
    {!departmentId ? <div className="rc-bands__empty">Chọn Tổ phụ trách trước.</div> : <>
      <div className="rc-dinh-muc-wrapper">
        <table className="rc-dinh-muc-table">
          <thead>
            <tr className="rc-dinh-muc-table__group-row">
              <th rowSpan={2} className="rc-col--left">Đầu việc chi tiết</th>
              <th colSpan={4} className="rc-col--group rc-group--ns">Năng suất khoán</th>
              <th colSpan={3} className="rc-col--group rc-group--nl">Định mức nhân lực (người)</th>
              {/* Cột "Mặc định" (radio chọn đầu việc điền sẵn) GỠ 12/08/2026 — xem mg 0190. Bế tay
                  hay bế máy là quyết định theo HÀNG, không khai một lần ở danh mục được. */}
              {/* VẬT TƯ đầu việc tiêu thụ (mg 0191) — nền BOM. Chỉ danh sách, KHÔNG có số lượng. */}
              <th rowSpan={2} className="rc-col--center"
                title="Vật tư đầu việc này tiêu thụ. Số lượng tính ở lệnh theo quy cách.">Vật tư</th>
              <th rowSpan={2} className="rc-col--center" style={{ width: 36 }} />
            </tr>
            <tr className="rc-dinh-muc-table__sub-row">
              <th className="rc-col--num">Trung bình</th>
              <th className="rc-col--num">Tối thiểu</th>
              <th className="rc-col--num">Tối đa</th>
              <th className="rc-col--unit">Đơn vị</th>
              <th className="rc-col--num">Tối thiểu</th>
              <th className="rc-col--num">Chuẩn</th>
              <th className="rc-col--num">Tối đa</th>
            </tr>
          </thead>
          <tbody>{value.length === 0 && <tr><td colSpan={10} className="rc-bands__empty">
            {allowed.length === 0 ? "Tổ này chưa có đầu việc khoán để liên kết." : "Chưa chọn đầu việc định mức."}
          </td></tr>}{value.map((r, i) => { const opt = options.find((o) => o.id === r.piece_rate_id); const vtIds = r.vat_tu_ids ?? []; const mo = moVatTu === r.piece_rate_id; return <Fragment key={r.piece_rate_id}><tr>
            <td className="rc-col--left rc-dinh-muc-name">{opt ? `${opt.ma} · ${opt.ten}` : `#${r.piece_rate_id}`}</td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" value={r.nang_suat_nguoi_gio} onChange={(e) => patch(i, { nang_suat_nguoi_gio: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_min ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_min: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_max ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_max: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            {/* KHOÁ theo đơn vị của ĐƠN GIÁ KHOÁN (chủ chốt 10/08/2026) — chữ, không phải ô chọn.
                Cùng một đầu việc thì tính tiền và đếm năng suất bằng cùng một thứ; khai ở Lương
                khoán rồi thì đừng bắt chọn lại. Đổi đơn vị ⇒ sửa ở màn Lương khoán. */}
            <td className="rc-col--unit rc-dinh-muc-unit">{opt?.don_vi ? `${opt.don_vi}/h` : "—"}</td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_toi_thieu ?? 1} onChange={(e) => patch(i, { so_nguoi_toi_thieu: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_tieu_chuan} onChange={(e) => patch(i, { so_nguoi_tieu_chuan: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_toi_da} onChange={(e) => patch(i, { so_nguoi_toi_da: Number(e.target.value) })} /></td>
            {/* Bấm để bung HÀNG PHỤ ngay dưới — không mở drawer lồng drawer, người khai vẫn thấy
                cả bảng để so các dòng với nhau. */}
            <td className="rc-col--center">
              <button type="button" className={`rc-dm-vt__pill ${mo ? "is-open" : ""} ${vtIds.length ? "" : "is-empty"}`}
                title="Vật tư đầu việc này tiêu thụ"
                onClick={() => setMoVatTu(mo ? null : r.piece_rate_id)}>
                {vtIds.length ? `${vtIds.length} vật tư` : "＋ gắn"}
              </button>
            </td>
            <td className="rc-col--center"><button type="button" className="rc-bands__del" onClick={() => onChange(value.filter((_, j) => j !== i))}><TrashIcon /></button></td>
          </tr>{mo && <tr className="rc-dm-vt__row"><td colSpan={10}>
            <div className="rc-dm-vt">
              {vtIds.length === 0 && <div className="rc-dm-vt__empty">Chưa gắn vật tư nào.</div>}
              {vtIds.map((vid) => { const vt = vatTuTheoId.get(vid); return (
                <div className="rc-dm-vt__item" key={vid}>
                  <span className="rc-dm-vt__ma">{String(vt?.ma ?? `#${vid}`)}</span>
                  <span className="rc-dm-vt__ten">{String(vt?.ten ?? "(đã gỡ khỏi danh mục)")}</span>
                  <span className="rc-dm-vt__dv">{String(vt?.don_vi_gia ?? "—")}</span>
                  <button type="button" className="rc-bands__del" title="Bỏ vật tư khỏi đầu việc"
                    onClick={() => patch(i, { vat_tu_ids: vtIds.filter((x) => x !== vid) })}>
                    <TrashIcon />
                  </button>
                </div>
              ); })}
              <select className="rc-dinh-muc-add__select" value=""
                onChange={(e) => { const id = Number(e.target.value); if (id) patch(i, { vat_tu_ids: [...vtIds, id] }); }}>
                <option value="">＋ chọn từ danh mục vật tư khác</option>
                {vatTu.filter((v) => !vtIds.includes(Number(v.id))).map((v) => (
                  <option key={v.id} value={v.id}>{String(v.ma)} · {String(v.ten)} ({String(v.don_vi_gia ?? "—")})</option>
                ))}
              </select>
              <p className="rc-dm-vt__note">
                Số lượng tính ở lệnh theo quy cách — chỗ này chỉ khai <b>dùng những gì</b>.
              </p>
            </div>
          </td></tr>}</Fragment>; })}</tbody>
        </table>
      </div>
      <div className="rc-dinh-muc-add">
        <select className="rc-dinh-muc-add__select" value="" onChange={(e) => { const id = Number(e.target.value); if (id) onChange([...value, { piece_rate_id: id, nang_suat_nguoi_gio: 1, nang_suat_nguoi_gio_min: null, nang_suat_nguoi_gio_max: null, don_vi_nang_suat: null, so_nguoi_toi_thieu: 1, so_nguoi_tieu_chuan: 1, so_nguoi_toi_da: 1, vat_tu_ids: [] }]); }}>
          <option value="">＋ Chọn đầu việc của tổ</option>{allowed.filter((o) => !selected.has(o.id)).map((o) => <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>)}
        </select>
      </div>
    </>}
  </div>;
}
