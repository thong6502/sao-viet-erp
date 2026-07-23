// Bảng ROUTING của lệnh — kế thừa từ bài tính giá nhưng SỬA ĐƯỢC tại lệnh (thêm/bỏ/đổi thứ tự/đổi
// tổ/đổi máy/thuê ngoài/số lượng vào-ra). Lưu = REPLACE-ALL, không đụng phiếu tính giá và không
// ảnh hưởng lệnh khác.
//
// Máy CHỈ ĐỀ XUẤT: số gợi ý nằm ở placeholder + nút "dùng số gợi ý" (1 click), KHÔNG tự ghi vào ô.
// Các kiểm tra (ra > vào, chưa gán tổ, thuê ngoài thiếu NCC, trùng bước liền kề) chỉ TÔ MÀU,
// không chặn lưu — phán đoán nghề để người kế hoạch quyết.
import { Fragment, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { LsxCongDoan, LsxCongDoanBody } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ChuoiCongDoan } from "./keHoachSxShared";

export interface RefRow {
  id: number;
  ten: string;
}

interface EditRow {
  key: string;
  cong_doan_id: number | null;
  ten: string;
  nhom: string | null;
  department_id: number | null;
  may_id: number | null;
  so_luong_vao: string;
  so_luong_ra: string;
  don_vi: string;
  hao_hut: string;
  thue_ngoai: boolean;
  nha_cung_cap: string;
  ghi_chu: string;
}

const DON_VI: { key: string; label: string }[] = [
  { key: "to", label: "Tờ" },
  { key: "cai", label: "Con" },
  { key: "kem", label: "Kẽm" },
];

/** Giá trị select cho bước có TÊN TỰ DO (không gắn danh mục công đoạn). */
const KEEP = "__keep__";

let seq = 0;
function newKey(): string {
  seq += 1;
  return `r${seq}`;
}

function toEdit(cd: LsxCongDoan): EditRow {
  return {
    key: newKey(),
    cong_doan_id: cd.cong_doan_id,
    ten: cd.ten,
    nhom: cd.nhom,
    department_id: cd.department_id,
    may_id: cd.may_id,
    so_luong_vao: cd.so_luong_vao ? String(cd.so_luong_vao) : "",
    so_luong_ra: cd.so_luong_ra ? String(cd.so_luong_ra) : "",
    don_vi: cd.don_vi || "to",
    hao_hut: cd.hao_hut ? String(cd.hao_hut) : "",
    thue_ngoai: cd.thue_ngoai,
    nha_cung_cap: cd.nha_cung_cap ?? "",
    ghi_chu: cd.ghi_chu ?? "",
  };
}

function emptyRow(): EditRow {
  return {
    key: newKey(), cong_doan_id: null, ten: "", nhom: null, department_id: null, may_id: null,
    so_luong_vao: "", so_luong_ra: "", don_vi: "to", hao_hut: "", thue_ngoai: false,
    nha_cung_cap: "", ghi_chu: "",
  };
}

function toBody(rows: EditRow[]): LsxCongDoanBody[] {
  return rows.map((r, i) => ({
    thu_tu: i,
    cong_doan_id: r.cong_doan_id,
    ten: r.ten || "Công đoạn",
    nhom: r.nhom,
    // Để TRỐNG tổ → server tự lấy tổ mặc định của công đoạn (không ép người dùng khai lại).
    department_id: r.department_id,
    may_id: r.may_id,
    so_luong_vao: Number(r.so_luong_vao || 0),
    so_luong_ra: Number(r.so_luong_ra || 0),
    don_vi: r.don_vi,
    hao_hut: Number(r.hao_hut || 0),
    thue_ngoai: r.thue_ngoai,
    nha_cung_cap: r.thue_ngoai ? r.nha_cung_cap || null : null,
    ghi_chu: r.ghi_chu || null,
  }));
}

export function LsxRoutingTable({
  congDoans,
  soToKeHoach,
  soLuongDat,
  congDoanRefs,
  toRefs,
  mayRefs,
  canUpdate,
  saving,
  onSave,
  onDirtyChange,
}: {
  congDoans: LsxCongDoan[];
  soToKeHoach: number;
  soLuongDat: number;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  canUpdate: boolean;
  saving: boolean;
  onSave: (body: LsxCongDoanBody[]) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [rows, setRows] = useState<EditRow[]>(() => congDoans.map(toEdit));
  const [undo, setUndo] = useState<{ row: EditRow; at: number } | null>(null);
  const [live, setLive] = useState("");
  const goc = useRef(JSON.stringify(toBody(congDoans.map(toEdit))));
  const tbodyRef = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    const fresh = congDoans.map(toEdit);
    setRows(fresh);
    goc.current = JSON.stringify(toBody(fresh));
  }, [congDoans]);

  const dirty = JSON.stringify(toBody(rows)) !== goc.current;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  // Dải "hoàn tác" tự tắt sau 6s — xoá dòng chưa lưu không cần hỏi han.
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 6000);
    return () => clearTimeout(t);
  }, [undo]);

  function patch(key: string, p: Partial<EditRow>) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...p } : r)));
  }

  function move(idx: number, delta: number) {
    setRows((prev) => {
      const to = idx + delta;
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [row] = next.splice(idx, 1);
      next.splice(to, 0, row);
      setLive(`Đã chuyển ${row.ten || "công đoạn"} tới vị trí ${to + 1}`);
      return next;
    });
  }

  function remove(idx: number) {
    setRows((prev) => {
      const row = prev[idx];
      setUndo({ row, at: idx });
      setLive(`Đã bỏ ${row.ten || "công đoạn"}, có thể hoàn tác`);
      return prev.filter((_, i) => i !== idx);
    });
  }

  function hoanTac() {
    if (!undo) return;
    setRows((prev) => {
      const next = [...prev];
      next.splice(Math.min(undo.at, next.length), 0, undo.row);
      return next;
    });
    setUndo(null);
    setLive("Đã hoàn tác");
  }

  function them() {
    setRows((prev) => [...prev, emptyRow()]);
    setLive("Đã thêm công đoạn mới ở cuối");
    // Cuộn + focus ô đầu của hàng vừa thêm.
    setTimeout(() => {
      const last = tbodyRef.current?.querySelector<HTMLElement>("tr:last-of-type select, tr:last-of-type input");
      last?.focus();
      last?.scrollIntoView({ block: "nearest" });
    }, 0);
  }

  /** Số gợi ý cho ô SL: bước đầu = số tờ kế hoạch; bước sau = SL ra của bước trước. */
  function goiY(i: number, row: EditRow): number {
    if (row.don_vi === "cai") return soLuongDat;
    if (i === 0) return soToKeHoach;
    const truoc = rows[i - 1];
    const raTruoc = Number(truoc.so_luong_ra || truoc.so_luong_vao || 0);
    return raTruoc || soToKeHoach;
  }

  const flow = useMemo(
    () => rows.map((r) => ({ ten: r.ten || "…", thue_ngoai: r.thue_ngoai })),
    [rows],
  );
  const soNgoai = rows.filter((r) => r.thue_ngoai).length;
  const soChuaTo = rows.filter((r) => r.department_id == null).length;

  function onRowKeyDown(e: KeyboardEvent, idx: number) {
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(idx, e.key === "ArrowUp" ? -1 : 1);
    }
  }

  return (
    <div className="khsx-rt">
      <div className="khsx-rt__bar">
        <div>
          <h3 className="khsx-rt__title">Chuỗi công đoạn ({rows.length})</h3>
          <p className="khsx-rt__origin">kế thừa từ bài tính giá · sửa được tại lệnh này</p>
        </div>
        {canUpdate && (
          <div className="khsx-rt__baracts">
            <Button variant="secondary" onClick={them}>
              <Icon name="plus" size={14} /> Thêm công đoạn
            </Button>
            <Button
              variant="accent"
              disabled={!dirty}
              loading={saving}
              onClick={() => onSave(toBody(rows))}
            >
              Lưu công đoạn
            </Button>
          </div>
        )}
      </div>

      <div className="khsx-rt__flow">
        <ChuoiCongDoan steps={flow} />
      </div>

      <div className="khsx__tablewrap">
        <table className="khsx-rt__table">
          <caption className="sr-only">Danh sách công đoạn của lệnh, sửa được</caption>
          <thead>
            <tr>
              <th scope="col" className="khsx-rt__thord">#</th>
              <th scope="col">Công đoạn</th>
              <th scope="col">Tổ phụ trách</th>
              <th scope="col">Máy</th>
              <th scope="col" className="khsx-th--num">SL vào</th>
              <th scope="col" className="khsx-th--num">SL ra</th>
              <th scope="col">ĐVT</th>
              <th scope="col" className="khsx-th--num">Hao hụt</th>
              <th scope="col">Ngoài</th>
              <th scope="col">Ghi chú</th>
              <th scope="col"><span className="sr-only">Thao tác</span></th>
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {rows.length === 0 && (
              <tr>
                <td colSpan={11}>
                  <div className="khsx-empty khsx-empty--inline">
                    <Icon name="workflow" size={32} />
                    <p className="khsx-empty__title">Chưa có công đoạn nào.</p>
                    <p className="khsx-empty__sub">
                      Bài tính giá không có công đoạn, hoặc đã xoá hết. Thêm ít nhất 1 công đoạn thì
                      lệnh mới sẵn sàng lập kế hoạch.
                    </p>
                    {canUpdate && (
                      <Button variant="secondary" onClick={them}>
                        <Icon name="plus" size={14} /> Thêm công đoạn
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const vao = Number(r.so_luong_vao || 0);
              const ra = Number(r.so_luong_ra || 0);
              const hao = Number(r.hao_hut || 0);
              const raQua = ra > 0 && vao > 0 && ra > vao;
              const lechHao = vao > 0 && ra > 0 && Math.abs(vao - ra - hao) > 0.001;
              const trungTruoc = i > 0 && r.ten && rows[i - 1].ten === r.ten;
              return (
                <Fragment key={r.key}>
                  <tr
                    className={`khsx-rt__row ${r.thue_ngoai ? "khsx-rt__row--ngoai" : ""}`}
                    onKeyDown={(e) => onRowKeyDown(e, i)}
                  >
                    <td>
                      <span className="khsx-rt__ord">{i + 1}</span>
                    </td>
                    <td>
                      {congDoanRefs ? (
                        <select
                          className="khsx-rt__cd"
                          value={r.cong_doan_id ?? (r.ten ? KEEP : "")}
                          disabled={!canUpdate}
                          onChange={(e) => {
                            if (e.target.value === KEEP) return;   // giữ nguyên tên tự do
                            const id = e.target.value ? Number(e.target.value) : null;
                            const ref = congDoanRefs.find((c) => c.id === id);
                            // Đổi công đoạn → bỏ tổ đã chọn tay để server điền lại tổ mặc định.
                            patch(r.key, { cong_doan_id: id, ten: ref?.ten ?? r.ten, department_id: null });
                          }}
                          aria-label={`Công đoạn bước ${i + 1}`}
                        >
                          <option value="">— chọn công đoạn —</option>
                          {/* Bước lấy từ bài tính giá có thể là TÊN TỰ DO (không gắn danh mục), hoặc
                              công đoạn nằm ngoài trang danh mục đang tải → giữ nguyên tên đã chụp,
                              không để select rơi về rỗng làm mất dữ liệu. */}
                          {r.cong_doan_id == null && r.ten && <option value={KEEP}>{r.ten} (tên tự do)</option>}
                          {r.cong_doan_id != null && !congDoanRefs.some((c) => c.id === r.cong_doan_id) && (
                            <option value={r.cong_doan_id}>{r.ten}</option>
                          )}
                          {congDoanRefs.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.ten}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          className="khsx-rt__cd"
                          value={r.ten}
                          disabled={!canUpdate}
                          onChange={(e) => patch(r.key, { ten: e.target.value })}
                          aria-label={`Tên công đoạn bước ${i + 1}`}
                        />
                      )}
                      {trungTruoc && <div className="khsx-warn-inline">trùng bước trước?</div>}
                    </td>
                    <td>
                      {toRefs ? (
                        <select
                          className={`khsx-rt__to ${r.department_id == null ? "khsx-rt__to--empty" : ""}`}
                          value={r.department_id ?? ""}
                          disabled={!canUpdate}
                          onChange={(e) =>
                            patch(r.key, { department_id: e.target.value ? Number(e.target.value) : null })
                          }
                          aria-label={`Tổ phụ trách bước ${i + 1}`}
                          title={r.department_id == null ? "Để trống → lấy tổ mặc định của công đoạn" : undefined}
                        >
                          <option value="">— tổ mặc định —</option>
                          {toRefs.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.ten}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="khsx-muted">tổ mặc định</span>
                      )}
                    </td>
                    <td>
                      {mayRefs ? (
                        <select
                          className="khsx-rt__may"
                          value={r.may_id ?? ""}
                          disabled={!canUpdate}
                          onChange={(e) => patch(r.key, { may_id: e.target.value ? Number(e.target.value) : null })}
                          aria-label={`Máy bước ${i + 1}`}
                        >
                          <option value="">— chưa gán —</option>
                          {mayRefs.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.ten}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="khsx-muted">—</span>
                      )}
                    </td>
                    <td className="khsx-rt__numcell">
                      <input
                        type="number"
                        className="khsx-rt__num"
                        value={r.so_luong_vao}
                        placeholder={String(goiY(i, r))}
                        disabled={!canUpdate}
                        onChange={(e) => patch(r.key, { so_luong_vao: e.target.value })}
                        aria-label={`Số lượng vào bước ${i + 1}`}
                      />
                      {canUpdate && !r.so_luong_vao && (
                        <button
                          type="button"
                          className="khsx-rt__fill"
                          title="Dùng số gợi ý cho cả dòng"
                          onClick={() => {
                            const g = goiY(i, r);
                            patch(r.key, { so_luong_vao: String(g), so_luong_ra: String(g) });
                          }}
                        >
                          <Icon name="check" size={11} />
                        </button>
                      )}
                    </td>
                    <td className="khsx-rt__numcell">
                      <input
                        type="number"
                        className={`khsx-rt__num ${raQua ? "khsx-rt__num--bad" : ""}`}
                        value={r.so_luong_ra}
                        placeholder={String(goiY(i, r))}
                        disabled={!canUpdate}
                        title={raQua ? "Ra nhiều hơn vào — kiểm tra lại" : undefined}
                        onChange={(e) => patch(r.key, { so_luong_ra: e.target.value })}
                        aria-label={`Số lượng ra bước ${i + 1}`}
                      />
                    </td>
                    <td>
                      <div className="khsx-rt__unit" role="group" aria-label={`Đơn vị bước ${i + 1}`}>
                        {DON_VI.map((u) => (
                          <button
                            key={u.key}
                            type="button"
                            className={r.don_vi === u.key ? "is-active" : ""}
                            disabled={!canUpdate}
                            onClick={() => patch(r.key, { don_vi: u.key })}
                            aria-pressed={r.don_vi === u.key}
                          >
                            {u.label}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="khsx-rt__numcell">
                      <input
                        type="number"
                        className="khsx-rt__num"
                        value={r.hao_hut}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => patch(r.key, { hao_hut: e.target.value })}
                        aria-label={`Hao hụt bước ${i + 1}`}
                      />
                      {lechHao && <div className="khsx-rt__gap">lệch {Math.abs(vao - ra - hao)}</div>}
                    </td>
                    <td>
                      <label className="khsx-rt__ext">
                        <input
                          type="checkbox"
                          checked={r.thue_ngoai}
                          disabled={!canUpdate}
                          onChange={(e) => patch(r.key, { thue_ngoai: e.target.checked })}
                        />
                        <span className="sr-only">Thuê ngoài bước {i + 1}</span>
                      </label>
                    </td>
                    <td>
                      <input
                        className="khsx-rt__note"
                        value={r.ghi_chu}
                        disabled={!canUpdate}
                        onChange={(e) => patch(r.key, { ghi_chu: e.target.value })}
                        aria-label={`Ghi chú bước ${i + 1}`}
                      />
                    </td>
                    <td>
                      {canUpdate && (
                        <div className="khsx-rt__acts">
                          <button
                            type="button"
                            className="khsx-rt__btn khsx-rt__btn--up"
                            disabled={i === 0}
                            onClick={() => move(i, -1)}
                            aria-label={`Chuyển bước ${i + 1} lên`}
                          >
                            <Icon name="chevron" size={14} />
                          </button>
                          <button
                            type="button"
                            className="khsx-rt__btn"
                            disabled={i === rows.length - 1}
                            onClick={() => move(i, 1)}
                            aria-label={`Chuyển bước ${i + 1} xuống`}
                          >
                            <Icon name="chevron" size={14} />
                          </button>
                          <button
                            type="button"
                            className="khsx-rt__btn khsx-rt__btn--del"
                            onClick={() => remove(i)}
                            aria-label={`Bỏ bước ${i + 1}`}
                          >
                            <Icon name="trash" size={14} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {r.thue_ngoai && (
                    <tr className="khsx-rt__sub">
                      <td />
                      <td colSpan={10}>
                        <label className="khsx-rt__sublabel">
                          Nhà cung cấp gia công
                          <input
                            className={`khsx-rt__ncc ${!r.nha_cung_cap ? "khsx-rt__num--bad" : ""}`}
                            value={r.nha_cung_cap}
                            disabled={!canUpdate}
                            placeholder="Tên cơ sở nhận gia công"
                            onChange={(e) => patch(r.key, { nha_cung_cap: e.target.value })}
                          />
                        </label>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {undo && (
        <div className="khsx-rt__undo">
          <span>Đã bỏ “{undo.row.ten || "công đoạn"}”</span>
          <button type="button" className="khsx-xlink" onClick={hoanTac}>
            Hoàn tác
          </button>
        </div>
      )}

      <div className="khsx-rt__foot">
        <p className="khsx-rt__summary">
          {rows.length} công đoạn
          {soNgoai > 0 && ` · ${soNgoai} thuê ngoài`}
          {soChuaTo > 0 && ` · ${soChuaTo} lấy tổ mặc định`}
        </p>
        {canUpdate && (
          <Button variant="accent" disabled={!dirty} loading={saving} onClick={() => onSave(toBody(rows))}>
            Lưu công đoạn
          </Button>
        )}
      </div>

      <p className="sr-only" aria-live="polite">
        {live}
      </p>
    </div>
  );
}
