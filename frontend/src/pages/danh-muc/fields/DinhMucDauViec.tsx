// ĐỊNH MỨC ĐẦU VIỆC của một công đoạn: năng suất khoán · định mức nhân lực · vật tư tiêu thụ.
//
// `donViVao` vẫn nằm trong props (chỗ gọi truyền vào) nhưng KHÔNG dùng nữa: đơn vị năng suất
// do người khai chọn ở từng dòng, không còn suy theo đơn vị vào của công đoạn.
import { Fragment, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { crud } from "../../../api/rebuildCatalog";
import { TrashIcon } from "../icons";
import type { DinhMucRow, Row } from "../types";
import { DonViTocDoField } from "./DonViTocDo";
import { FormulaField } from "./FormulaField";
import { FormulaPopover } from "./FormulaPopover";

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
  // Danh mục Đơn vị & quy đổi cho ô chọn "Đơn vị" của Năng suất khoán. Nạp TẠI ĐÂY chứ không qua
  // `refData` chung: bộ nạp chung khoá theo MỘT `refPrefix` mỗi field, mà field này đã dùng
  // `refPrefix` cho danh sách đầu việc.
  const [donVi, setDonVi] = useState<Row[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    crud("/api/don-vi").list(token, { active: true, size: 200 })
      .then((r) => { if (alive) setDonVi(r.items); })
      .catch(() => { if (alive) setDonVi([]); });
    return () => { alive = false; };
  }, [token]);
  // Hàng phụ đang mở — mỗi lúc một dòng, mở cái khác thì cái cũ đóng (bảng đã 10 cột, bung hai
  // hàng cùng lúc là mất dấu dòng nào của ai).
  const [moVatTu, setMoVatTu] = useState<number | null>(null);
  // Dòng vật tư đang mở ô công thức — khoá theo id vật tư nên hai đầu việc cùng gắn một món thì
  // mở ở đầu việc này cũng bung ở đầu việc kia; chấp nhận được vì mỗi lúc chỉ mở MỘT bảng vật tư.
  //
  // `neo` = chính nút vừa bấm, để panel công thức NỔI dán vào đó (07/09/2026 — `FormulaPopover`).
  //
  // `banDau` = công thức lúc MỞ panel, để nút ✕ trả ô về đúng chỗ cũ — ô công thức ghi thẳng vào
  // form theo từng nhịp gõ nên không có nó thì "bỏ sửa" chỉ còn cách đóng drawer rồi mở lại.
  const [moVtCt, setMoVtCt] =
    useState<{ id: number; neo: HTMLElement; banDau: string | null } | null>(null);
  // Panel công thức TIỀN CÔNG của đầu việc — mở độc lập với panel vật tư, vì hai thứ khai ở hai
  // nhịp khác nhau: tiền công là một ô, vật tư là cả một bảng con.
  const [moCt, setMoCongThuc] =
    useState<{ id: number; neo: HTMLElement; banDau: string | null } | null>(null);
  const batCt = (id: number, neo: HTMLElement, banDau: string | null) =>
    setMoCongThuc(moCt?.id === id ? null : { id, neo, banDau });
  const batVtCt = (id: number, neo: HTMLElement, banDau: string | null) =>
    setMoVtCt(moVtCt?.id === id ? null : { id, neo, banDau });
  // Panel CÁCH ĐO GIỜ — tách hẳn panel tiền công: hai ô trả lời hai câu khác nhau (bao nhiêu tiền
  // / bao nhiêu phút), mở lẫn nhau là chỗ gõ nhầm ô.
  const [moCtGio, setMoCtGio] =
    useState<{ id: number; neo: HTMLElement; banDau: string | null } | null>(null);
  const batCtGio = (id: number, neo: HTMLElement, banDau: string | null) =>
    setMoCtGio(moCtGio?.id === id ? null : { id, neo, banDau });
  // Panel nằm NGOÀI vòng lặp bảng nên phải tra lại dòng. Dòng vừa bị xoá ⇒ `-1` ⇒ không vẽ panel.
  const iCt = moCt ? value.findIndex((r) => r.piece_rate_id === moCt.id) : -1;
  const iCtGio = moCtGio ? value.findIndex((r) => r.piece_rate_id === moCtGio.id) : -1;
  // Vật tư khoá theo (đầu việc ĐANG mở bảng con, id vật tư) — id vật tư một mình không đủ, cùng
  // một món gắn ở hai đầu việc là hai công thức khác nhau.
  const iVt = moVatTu == null ? -1 : value.findIndex((r) => r.piece_rate_id === moVatTu);
  const kVt = iVt < 0 || !moVtCt ? -1 : (value[iVt].vat_tus ?? []).findIndex((v) => v.vat_tu_id === moVtCt.id);
  // BỎ SỬA: dùng chung cho nút ✕ trên hàng tên ô và cho phím Esc.
  const huyKhoan = () => {
    if (!moCt || iCt < 0) return;
    patch(iCt, { cong_thuc_khoan: moCt.banDau });
    setMoCongThuc(null);
  };
  const huyGio = () => {
    if (!moCtGio || iCtGio < 0) return;
    patch(iCtGio, { cong_thuc_gio: moCtGio.banDau });
    setMoCtGio(null);
  };
  const huyVt = () => {
    if (!moVtCt || iVt < 0 || kVt < 0) return;
    patch(iVt, {
      vat_tus: (value[iVt].vat_tus ?? [])
        .map((x, m) => (m === kVt ? { ...x, cong_thuc_luong: moVtCt.banDau } : x)),
    });
    setMoVtCt(null);
  };
  return <div className="rc-bands rc-bands--dinh-muc">
    {!departmentId ? <div className="rc-bands__empty">Chọn Tổ phụ trách trước.</div> : <>
      <div className="rc-dinh-muc-wrapper">
        <table className="rc-dinh-muc-table">
          <thead>
            <tr className="rc-dinh-muc-table__group-row">
              <th rowSpan={2} className="rc-col--left">Đầu việc chi tiết</th>
              <th colSpan={4} className="rc-col--group rc-group--ns">Năng suất khoán</th>
              {/* MỘT ô người duy nhất (06/09/2026, mg `0270`): hai mốc tối thiểu/tối đa đã gỡ.
                  Số này điền sẵn vào bước lệnh cho MỌI loại bước — máy · tổ · thuê ngoài. */}
              <th rowSpan={2} className="rc-col--num rc-group--nl"
                title="Kíp chuẩn của công đoạn — số người điền sẵn vào bước lệnh, sửa đè được tại từng lệnh.">Kíp chuẩn (người)</th>
              {/* Tiền công khai THEO CÔNG ĐOẠN chứ không theo bảng đơn giá khoán (06/09/2026):
                  cùng một đầu việc chạy ở hai công đoạn thì đếm lượng theo hai cách khác nhau. */}
              <th rowSpan={2} className="rc-col--left"
                title="Ra LƯỢNG theo đơn vị đơn giá khoán — hệ nhân đơn giá sau.">Công thức tiền công</th>
              {/* Đối xứng bảng "Máy chạy được công đoạn này": máy có cặp (Cách đo giờ chạy · Cách
                  tính giá), đầu việc có cặp (Công thức tiền công · Cách đo giờ chạy). Trước
                  07/09/2026 đầu việc chỉ có MỘT ô và hệ dùng nó cho cả tiền lẫn giờ, nên khai
                  `so_luot_chay` là nhân đôi cả hai — tiền thì đúng, giờ thì sai. */}
              <th rowSpan={2} className="rc-col--left"
                title="Ra LƯỢNG theo đơn vị Năng suất khoán — hệ chia cho năng suất sau.">Cách đo giờ chạy</th>
              {/* Cột "Mặc định" (radio chọn đầu việc điền sẵn) GỠ 12/08/2026 — xem mg 0190. Bế tay
                  hay bế máy là quyết định theo HÀNG, không khai một lần ở danh mục được. */}
              {/* VẬT TƯ đầu việc tiêu thụ (mg 0191) — nền BOM. Chỉ danh sách, KHÔNG có số lượng. */}
              <th rowSpan={2} className="rc-col--center"
                title="Vật tư đầu việc này tiêu thụ. Số lượng tính ở lệnh theo quy cách.">Vật tư</th>
              <th rowSpan={2} className="rc-col--center" style={{ width: 36 }} />
            </tr>
            <tr className="rc-dinh-muc-table__sub-row">
              {/* Thứ tự tối thiểu → trung bình → tối đa: đọc thành một DẢI tăng dần. */}
              <th className="rc-col--num">Tối thiểu</th>
              <th className="rc-col--num">Trung bình</th>
              <th className="rc-col--num">Tối đa</th>
              <th className="rc-col--unit">Đơn vị</th>
            </tr>
          </thead>
          <tbody>{value.length === 0 && <tr><td colSpan={10} className="rc-bands__empty">
            {allowed.length === 0 ? "Tổ này chưa có đầu việc khoán để liên kết." : "Chưa chọn đầu việc định mức."}
          </td></tr>}{value.map((r, i) => { const opt = options.find((o) => o.id === r.piece_rate_id); const vts = r.vat_tus ?? []; const mo = moVatTu === r.piece_rate_id; return <Fragment key={r.piece_rate_id}><tr>
            {/* Bấm tên để bung panel công thức tính tiền công — cùng lối bấm-dòng-mở-panel với
                bảng máy và bảng vật tư, để ba chỗ khai công thức trong drawer này thao tác giống
                nhau (06/09/2026). */}
            <td className="rc-col--left rc-dinh-muc-name">
              <button type="button" className={`rc-dm-vt__pill ${moCt?.id === r.piece_rate_id ? "is-open" : ""}`}
                onClick={(e) => batCt(r.piece_rate_id, e.currentTarget, r.cong_thuc_khoan ?? null)}>
                {opt ? `${opt.ma} · ${opt.ten}` : `#${r.piece_rate_id}`}
              </button>
            </td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_min ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_min: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" value={r.nang_suat_nguoi_gio} onChange={(e) => patch(i, { nang_suat_nguoi_gio: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_max ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_max: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            {/* CHỌN ĐƯỢC trở lại từ 07/09/2026 (khoá cứng theo đơn giá khoán 10/08/2026 → mở).
                Hồi đó khoá vì tiền và giờ dùng CHUNG một công thức nên hai đơn vị buộc phải là
                một; nay ô "Cách đo giờ chạy" bên phải tách hai thứ ra, nên khai được "tiền tính
                theo kg mực, giờ tính theo tờ". Bỏ trống = lùi về đơn vị của đơn giá khoán. */}
            <td className="rc-col--unit rc-dinh-muc-unit"
              title={opt?.don_vi_ten ? `Bỏ trống = ${opt.don_vi_ten}/h (đơn vị đơn giá khoán)` : undefined}>
              <DonViTocDoField value={String(r.don_vi_nang_suat ?? "")} donViList={donVi}
                onChange={(v) => patch(i, { don_vi_nang_suat: v || null })} />
            </td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_tieu_chuan} onChange={(e) => patch(i, { so_nguoi_tieu_chuan: Number(e.target.value) })} /></td>
            {/* Bấm thẳng vào ô công thức cũng mở panel, không bắt đi đường vòng qua tên ở cột đầu. */}
            <td className="rc-col--left rc-dinh-muc-unit">
              <button type="button" title="Sửa công thức tính tiền công của đầu việc này"
                className={`rc-ct-cell ${moCt?.id === r.piece_rate_id ? "is-open" : ""} ${r.cong_thuc_khoan ? "" : "is-empty"}`}
                onClick={(e) => batCt(r.piece_rate_id, e.currentTarget, r.cong_thuc_khoan ?? null)}>
                {r.cong_thuc_khoan || "—"}
              </button>
            </td>
            <td className="rc-col--left rc-dinh-muc-unit">
              <button type="button" title="Sửa cách đo giờ chạy của đầu việc này"
                className={`rc-ct-cell ${moCtGio?.id === r.piece_rate_id ? "is-open" : ""} ${r.cong_thuc_gio ? "" : "is-empty"}`}
                onClick={(e) => batCtGio(r.piece_rate_id, e.currentTarget, r.cong_thuc_gio ?? null)}>
                {r.cong_thuc_gio || "—"}
              </button>
            </td>
            {/* Bấm để bung HÀNG PHỤ ngay dưới — không mở drawer lồng drawer, người khai vẫn thấy
                cả bảng để so các dòng với nhau. */}
            <td className="rc-col--center">
              <button type="button" className={`rc-dm-vt__pill ${mo ? "is-open" : ""} ${vts.length ? "" : "is-empty"}`}
                title="Vật tư đầu việc này tiêu thụ"
                onClick={() => setMoVatTu(mo ? null : r.piece_rate_id)}>
                {vts.length ? `${vts.length} vật tư` : "＋ gắn"}
              </button>
            </td>
            <td className="rc-col--center"><button type="button" className="rc-bands__del" onClick={() => onChange(value.filter((_, j) => j !== i))}><TrashIcon /></button></td>
          </tr>{mo && <tr className="rc-dm-vt__row"><td colSpan={10}>
            <div className="rc-dm-vt">
              {/* BẢNG chứ không phải dãy chip (06/09/2026): mỗi món nay mang ĐỊNH MỨC riêng, mà
                  công thức là chuỗi dài — xếp chip cạnh nhau thì không còn chỗ đọc công thức. */}
              <table className="rc-dinh-muc-table">
                <thead><tr>
                  <th className="rc-col--left">Mã</th>
                  <th className="rc-col--left">Tên vật tư</th>
                  <th className="rc-col--unit">ĐVT</th>
                  <th className="rc-col--left">Công thức định mức</th>
                  <th className="rc-col--center" style={{ width: 36 }} />
                </tr></thead>
                <tbody>
                  {vts.length === 0 && <tr><td colSpan={5} className="rc-bands__empty">
                    Chưa gắn vật tư nào.
                  </td></tr>}
                  {vts.map((v, k) => { const vt = vatTuTheoId.get(v.vat_tu_id); return (
                      <tr key={v.vat_tu_id}>
                        <td className="rc-col--left">
                          <button type="button" className={`rc-dm-vt__pill ${moVtCt?.id === v.vat_tu_id ? "is-open" : ""}`}
                            onClick={(e) => batVtCt(v.vat_tu_id, e.currentTarget, v.cong_thuc_luong ?? null)}>
                            {String(vt?.ma ?? `#${v.vat_tu_id}`)}
                          </button>
                        </td>
                        <td className="rc-col--left">{String(vt?.ten ?? "(đã gỡ khỏi danh mục)")}</td>
                        <td className="rc-col--unit">{String(vt?.don_vi_gia ?? "—")}</td>
                        <td className="rc-col--left rc-dinh-muc-unit">
                          <button type="button" title="Sửa công thức định mức của món này"
                            className={`rc-ct-cell ${moVtCt?.id === v.vat_tu_id ? "is-open" : ""} ${v.cong_thuc_luong ? "" : "is-empty"}`}
                            onClick={(e) => batVtCt(v.vat_tu_id, e.currentTarget, v.cong_thuc_luong ?? null)}>
                            {v.cong_thuc_luong || "—"}
                          </button>
                        </td>
                        <td className="rc-col--center">
                          <button type="button" className="rc-bands__del" title="Bỏ vật tư khỏi đầu việc"
                            onClick={() => patch(i, { vat_tus: vts.filter((_, m) => m !== k) })}>
                            <TrashIcon />
                          </button>
                        </td>
                      </tr>
                  ); })}
                </tbody>
              </table>
              <select className="rc-dinh-muc-add__select" value=""
                onChange={(e) => { const id = Number(e.target.value); if (id)
                  patch(i, { vat_tus: [...vts, { vat_tu_id: id, cong_thuc_luong: null }] }); }}>
                <option value="">＋ chọn từ danh mục vật tư khác</option>
                {vatTu.filter((v) => !vts.some((x) => x.vat_tu_id === Number(v.id))).map((v) => (
                  <option key={v.id} value={v.id}>{String(v.ma)} · {String(v.ten)} ({String(v.don_vi_gia ?? "—")})</option>
                ))}
              </select>
              <p className="rc-dm-vt__note">
                Định mức khai <b>theo từng món</b>: mực ăn theo số tờ, dung môi rửa máy ăn theo số màu.
              </p>
            </div>
          </td></tr>}</Fragment>; })}</tbody>
        </table>
      </div>
      {moCt && iCt >= 0 && <FormulaPopover neo={moCt.neo} nhan="Công thức tính tiền công"
        onClose={() => setMoCongThuc(null)} onHuy={huyKhoan}>
        <FormulaField
          id={`ct-khoan-${moCt.id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
          nhanO="Công thức tính tiền công" onDong={huyKhoan}
          goY="Ra LƯỢNG theo đơn vị đơn giá khoán, hệ nhân đơn giá sau. Bỏ trống = hệ tự quy đổi. vd in trở 2 lượt: sl_vao * so_luot_chay. Lệnh ĐÃ phát giữ cách đo cũ."
          value={value[iCt].cong_thuc_khoan ?? ""}
          onChange={(v) => patch(iCt, { cong_thuc_khoan: v })} />
      </FormulaPopover>}
      {moCtGio && iCtGio >= 0 && <FormulaPopover neo={moCtGio.neo} nhan="Cách đo giờ chạy"
        onClose={() => setMoCtGio(null)} onHuy={huyGio}>
        <FormulaField
          id={`ct-gio-${moCtGio.id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
          nhanO="Cách đo giờ chạy" onDong={huyGio}
          goY="Ra LƯỢNG theo đơn vị Năng suất khoán, hệ chia cho năng suất sau. Bỏ trống = hệ tự quy đổi. Ở bước tổ hệ KHÔNG tự nhân số lượt — hai lượt in chồng trên cùng một tờ thì cứ để nguyên sl_vao. Lệnh ĐÃ phát giữ cách đo cũ."
          value={value[iCtGio].cong_thuc_gio ?? ""}
          onChange={(v) => patch(iCtGio, { cong_thuc_gio: v })} />
      </FormulaPopover>}
      {moVtCt && kVt >= 0 && <FormulaPopover neo={moVtCt.neo} nhan="Công thức định mức"
        onClose={() => setMoVtCt(null)} onHuy={huyVt}>
        <FormulaField
          id={`ct-vt-${value[iVt].piece_rate_id}-${moVtCt.id}`}
          configPrefix="/api/cong-doan" loaiO="quy_doi"
          nhanO="Công thức định mức" onDong={huyVt}
          goY="Ra LƯỢNG theo ĐVT của vật tư. vd mực ăn theo số tờ: sl_vao / 40000 · dung môi rửa máy ăn theo số màu: so_mau * 0.3. Bỏ trống = bước lệnh KHÔNG bung dòng này."
          value={(value[iVt].vat_tus ?? [])[kVt].cong_thuc_luong ?? ""}
          onChange={(nv) => patch(iVt, {
            vat_tus: (value[iVt].vat_tus ?? []).map((x, m) => (m === kVt ? { ...x, cong_thuc_luong: nv } : x)),
          })} />
      </FormulaPopover>}
      <div className="rc-dinh-muc-add">
        <select className="rc-dinh-muc-add__select" value="" onChange={(e) => { const id = Number(e.target.value); if (id) onChange([...value, { piece_rate_id: id, nang_suat_nguoi_gio: 1, nang_suat_nguoi_gio_min: null, nang_suat_nguoi_gio_max: null, don_vi_nang_suat: null, so_nguoi_tieu_chuan: 1, cong_thuc_gio: null, vat_tus: [] }]); }}>
          <option value="">＋ Chọn đầu việc của tổ</option>{allowed.filter((o) => !selected.has(o.id)).map((o) => <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>)}
        </select>
      </div>
    </>}
  </div>;
}
