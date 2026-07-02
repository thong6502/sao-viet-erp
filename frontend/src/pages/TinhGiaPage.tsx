// Tính giá (Costing / giá thành nội bộ) — spec-08, feat-039 LÀM-NGAY slice.
// Danh sách phương án (F1) + Tạo/Sửa: Khối A đầu bài (SP qua SEAM-11, qty_final>0, mã
// chỉ-đọc, KHÔNG bậc SL) + Khối B phương án giấy (giấy qua SEAM-07 "chưa sẵn sàng", số
// con/khổ NHẬP TAY với GỢI Ý SONG SONG cạnh ô, grain_locked) + Khối E công đoạn gia công
// (execution_mode internal/outsourced) + Xoá. Giá vốn/số tờ/đơn giá TREO SEAM-07..12
// (feat-040..042) — màn này KHÔNG số giả.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CostingDetailOut,
  type CostingEnumsOut,
  type CostingInput,
  type CostingRow,
  type EnumOption,
  type OperationInput,
  type PaperOptionInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./tinh-gia.css";

const PAGE_SIZE = 10;

function labelOf(options: EnumOption[], value: string | null): string {
  if (!value) return "—";
  return options.find((o) => o.value === value)?.label ?? value;
}

export function TinhGiaPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<CostingRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [enums, setEnums] = useState<CostingEnumsOut | null>(null);

  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<CostingDetailOut | null>(null);
  const [deleting, setDeleting] = useState<CostingRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    api.costings
      .list(token, {
        q: q.trim() || undefined,
        status: statusFilter || null,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh sách phương án tính giá.");
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, q, statusFilter, sort, page]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sort, page, statusFilter]);

  useEffect(() => {
    if (!token) return;
    api.costings
      .enums(token)
      .then(setEnums)
      .catch(() => setEnums(null));
  }, [token]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function openEdit(row: CostingRow) {
    if (!token) return;
    try {
      const detail = await api.costings.get(token, row.id);
      setEditing(detail);
      setMode("edit");
    } catch {
      setListError("Không tải được chi tiết phương án.");
    }
  }

  async function confirmDelete() {
    if (!token || !deleting) return;
    const target = deleting;
    try {
      await api.costings.remove(token, target.id);
      setDeleting(null);
      if (rows.length === 1 && page > 1) setPage((p) => p - 1);
      else load();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setListError("Bạn không có quyền xoá phương án.");
      else setListError("Xoá không thành công. Vui lòng thử lại.");
      setDeleting(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const statuses = enums?.statuses ?? [];

  if (forbidden) {
    return (
      <main className="tg">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Tính giá (403).
        </div>
      </main>
    );
  }

  return (
    <main className="tg">
      <header className="tg__head">
        <p className="eyebrow">Kinh doanh</p>
        <h1 className="tg__title">Tính giá</h1>
        <p className="tg__sub">
          Giá thành / giá vốn nội bộ: chọn phương án giấy, nhập số con/khổ, engine bù hao ra
          giá vốn — Báo giá đọc lại. Không bậc SL, không lãi/chiết khấu, không snapshot.
        </p>
      </header>

      <div className="tg__toolbar">
        <form className="tg__search" onSubmit={onSearch} role="search">
          <input
            className="input"
            placeholder="Tìm theo mã…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm phương án tính giá"
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <select
          className="input tg__statusfilter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          aria-label="Lọc theo trạng thái"
        >
          <option value="">Tất cả trạng thái</option>
          {statuses.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <div className="tg__toolbar-spacer" />

        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setMode("create");
          }}
        >
          + Tạo phương án
        </Button>
      </div>

      <div className="card tg__tablewrap">
        <table className="tg__table">
          <thead>
            <tr>
              <th>
                <SortBtn label="Mã" col="code" sort={sort} onSort={setSort} />
              </th>
              <th>Sản phẩm</th>
              <th className="tg__num">
                <SortBtn label="Số lượng" col="qty_final" sort={sort} onSort={setSort} />
              </th>
              <th className="tg__num">Phương án giấy</th>
              <th className="tg__num">Giá vốn tổng</th>
              <th>
                <SortBtn label="Trạng thái" col="status" sort={sort} onSort={setSort} />
              </th>
              <th className="tg__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="tg__status" role="status">
                  Đang tải…
                </td>
              </tr>
            ) : listError ? (
              <tr>
                <td colSpan={7} className="tg__status">
                  <div className="banner banner--error" role="alert">
                    <span>{listError}</span>
                    <button type="button" className="btn btn--ghost" onClick={() => load()}>
                      Thử lại
                    </button>
                  </div>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="tg__empty">
                  <p>Chưa có phương án tính giá.</p>
                  <Button
                    variant="primary"
                    onClick={() => {
                      setEditing(null);
                      setMode("create");
                    }}
                  >
                    + Tạo phương án
                  </Button>
                </td>
              </tr>
            ) : (
              rows.map((c) => (
                <tr key={c.id} className="tg__row" onClick={() => openEdit(c)}>
                  <td className="tg__mono">{c.code}</td>
                  <td>
                    {c.product_id != null ? (
                      <span className="tg__mono">SP #{c.product_id}</span>
                    ) : (
                      <span className="tg__muted">Chưa chọn SP</span>
                    )}
                  </td>
                  <td className="tg__num">{c.qty_final.toLocaleString("vi-VN")}</td>
                  <td className="tg__num">{c.paper_option_count}</td>
                  <td className="tg__num">
                    {c.total_cost != null ? (
                      c.total_cost.toLocaleString("vi-VN")
                    ) : (
                      <span className="tg__muted" title="Cần Giấy/Định mức/Máy/NCC (SEAM-07..12)">
                        —
                      </span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`tg__badge${c.status === "ready" ? " tg__badge--ready" : ""}`}
                    >
                      {labelOf(statuses, c.status)}
                    </span>
                  </td>
                  <td className="tg__actions-col" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="btn btn--ghost tg__rowbtn"
                      onClick={() => openEdit(c)}
                    >
                      Sửa
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost tg__rowbtn tg__rowbtn--danger"
                      onClick={() => setDeleting(c)}
                    >
                      Xoá
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !listError && rows.length > 0 && (
        <div className="tg__pager">
          <span className="tg__muted">
            {total} phương án · trang {page}/{totalPages}
          </span>
          <div className="tg__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau ›
            </button>
          </div>
        </div>
      )}

      {mode && enums && (
        <CostingFormDialog
          enums={enums}
          existing={mode === "edit" ? editing : null}
          onClose={() => {
            setMode(null);
            setEditing(null);
          }}
          onSaved={() => {
            setMode(null);
            setEditing(null);
            if (mode === "create") setPage(1);
            load();
          }}
        />
      )}

      {deleting && (
        <ConfirmDeleteDialog
          costing={deleting}
          onCancel={() => setDeleting(null)}
          onConfirm={confirmDelete}
        />
      )}
    </main>
  );
}

// --- Sort header button -----------------------------------------------------

function SortBtn({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: string;
  sort: string;
  onSort: (s: string) => void;
}) {
  const active = sort === col || sort === `-${col}`;
  const desc = sort === `-${col}`;
  return (
    <button
      type="button"
      className={`tg__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : col)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
}

// --- Create / Edit dialog (Khối A + Khối B + Khối E) -----------------------

interface PaperForm {
  key: string;
  sheet_paper_master_id: string;
  sheet_w: string;
  sheet_h: string;
  pieces_per_sheet: string;
  grain_locked: boolean;
  selected: boolean;
}

interface OpForm {
  key: string;
  name: string;
  execution_mode: string;
}

let ROW_KEY = 0;
function newPaper(): PaperForm {
  ROW_KEY += 1;
  return {
    key: `p${ROW_KEY}`,
    sheet_paper_master_id: "",
    sheet_w: "",
    sheet_h: "",
    pieces_per_sheet: "",
    grain_locked: false,
    selected: false,
  };
}
function newOp(mode = "internal"): OpForm {
  ROW_KEY += 1;
  return { key: `o${ROW_KEY}`, name: "", execution_mode: mode };
}

function CostingFormDialog({
  enums,
  existing,
  onClose,
  onSaved,
}: {
  enums: CostingEnumsOut;
  existing: CostingDetailOut | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [productId, setProductId] = useState(
    existing?.product_id != null ? String(existing.product_id) : "",
  );
  const [qtyFinal, setQtyFinal] = useState(
    existing ? String(existing.qty_final) : "",
  );
  const [status, setStatus] = useState(existing?.status ?? "draft");
  const [note, setNote] = useState(existing?.note ?? "");
  const [papers, setPapers] = useState<PaperForm[]>(
    existing && existing.paper_options.length > 0
      ? existing.paper_options.map((p) => {
          ROW_KEY += 1;
          return {
            key: `ep${p.id}-${ROW_KEY}`,
            sheet_paper_master_id:
              p.sheet_paper_master_id != null ? String(p.sheet_paper_master_id) : "",
            sheet_w: String(p.sheet_w),
            sheet_h: String(p.sheet_h),
            pieces_per_sheet: String(p.pieces_per_sheet),
            grain_locked: p.grain_locked,
            selected: p.selected,
          };
        })
      : [newPaper()],
  );
  const [ops, setOps] = useState<OpForm[]>(
    existing
      ? existing.operations.map((o) => {
          ROW_KEY += 1;
          return { key: `eo${o.id}-${ROW_KEY}`, name: o.name, execution_mode: o.execution_mode };
        })
      : [],
  );

  const [saving, setSaving] = useState(false);
  const [qtyError, setQtyError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // SEAM-07 paper-cost picker state (fetched once; "chưa sẵn sàng" until Danh mục Giấy built).
  const [paperReady, setPaperReady] = useState(false);
  const [paperMsg, setPaperMsg] = useState("Danh mục Giấy chưa sẵn sàng");
  useEffect(() => {
    if (!token) return;
    api.costings
      .papers(token)
      .then((p) => {
        setPaperReady(p.available);
        if (!p.available && p.message) setPaperMsg(p.message);
      })
      .catch(() => setPaperReady(false));
  }, [token]);

  function updatePaper(key: string, patch: Partial<PaperForm>) {
    setPapers((ps) => ps.map((p) => (p.key === key ? { ...p, ...patch } : p)));
    setFormError(null);
  }
  function addPaper() {
    setPapers((ps) => [...ps, newPaper()]);
    setFormError(null);
  }
  function removePaper(key: string) {
    setPapers((ps) => (ps.length > 1 ? ps.filter((p) => p.key !== key) : ps));
  }

  function updateOp(key: string, patch: Partial<OpForm>) {
    setOps((os) => os.map((o) => (o.key === key ? { ...o, ...patch } : o)));
    setFormError(null);
  }
  function addOp() {
    setOps((os) => [...os, newOp(enums.execution_modes[0]?.value ?? "internal")]);
  }
  function removeOp(key: string) {
    setOps((os) => os.filter((o) => o.key !== key));
  }

  function validate(): string | null {
    const qty = Number(qtyFinal);
    if (!qtyFinal.trim() || !Number.isInteger(qty) || qty <= 0) {
      setQtyError("Số lượng cần giao phải lớn hơn 0.");
      return "qty";
    }
    if (papers.length === 0) return "Cần ít nhất 1 phương án giấy.";
    for (let i = 0; i < papers.length; i++) {
      const p = papers[i];
      const pcs = Number(p.pieces_per_sheet);
      if (!Number.isInteger(pcs) || pcs <= 0)
        return `Phương án giấy ${i + 1}: số con/khổ phải lớn hơn 0.`;
    }
    for (let i = 0; i < ops.length; i++) {
      if (!ops[i].name.trim()) return `Công đoạn ${i + 1}: tên công đoạn là bắt buộc.`;
    }
    return null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setQtyError(null);
    setFormError(null);
    const problem = validate();
    if (problem === "qty") return;
    if (problem) {
      setFormError(problem);
      return;
    }

    const paper_options: PaperOptionInput[] = papers.map((p) => ({
      sheet_paper_master_id: p.sheet_paper_master_id
        ? Number(p.sheet_paper_master_id)
        : null,
      sheet_w: Number(p.sheet_w || "0"),
      sheet_h: Number(p.sheet_h || "0"),
      pieces_per_sheet: Number(p.pieces_per_sheet),
      grain_locked: p.grain_locked,
      selected: p.selected,
    }));
    const operations: OperationInput[] = ops.map((o, i) => ({
      name: o.name.trim(),
      execution_mode: o.execution_mode,
      sequence: i,
    }));
    const input: CostingInput = {
      product_id: productId ? Number(productId) : null,
      qty_final: Number(qtyFinal),
      note: note.trim() || null,
      status,
      paper_options,
      operations,
    };

    setSaving(true);
    try {
      if (isEdit && existing) await api.costings.update(token, existing.id, input);
      else await api.costings.create(token, input);
      onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden) {
        setFormError("Bạn không có quyền thực hiện thao tác này.");
      } else if (err instanceof ApiError && err.status === 422) {
        setFormError(err.message);
      } else {
        setFormError("Lưu không thành công. Vui lòng thử lại.");
      }
      setSaving(false);
    }
  }

  const title = isEdit ? `Sửa phương án · ${existing!.code}` : "Tạo phương án tính giá";

  return (
    <div className="tg__overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="tg__dialog card">
        <div className="tg__dialog-head">
          <h2>{title}</h2>
          <button type="button" className="tg__close" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>

        <form className="tg__dialog-body" onSubmit={onSubmit} noValidate>
          {/* Khối A — Costing header */}
          <section>
            <h3 className="tg__section-title">Đầu bài</h3>
            <div className="tg__form-grid">
              <label className="field">
                <span className="field__label">Mã</span>
                <input
                  className="input"
                  value={existing?.code ?? "(tự sinh)"}
                  readOnly
                  disabled
                />
              </label>
              <label className="field">
                <span className="field__label">Số lượng cần giao *</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  value={qtyFinal}
                  onChange={(e) => {
                    setQtyFinal(e.target.value);
                    setQtyError(null);
                  }}
                  aria-invalid={!!qtyError}
                />
                {qtyError && (
                  <span className="tg__err" role="alert">
                    {qtyError}
                  </span>
                )}
              </label>

              {/* Khối A — SP picker (SEAM-11). SP read khi san_pham expose ProductRead. */}
              <label className="field">
                <span className="field__label">Sản phẩm (SEAM-11)</span>
                <div className="tg__seam" role="note">
                  <input
                    className="input"
                    type="number"
                    min="1"
                    placeholder="ID sản phẩm (tạm thời)"
                    value={productId}
                    onChange={(e) => setProductId(e.target.value)}
                    aria-label="ID sản phẩm"
                  />
                  <span className="tg__muted">
                    Kéo cấu phần (khổ/màu/số trang) tự động khi phân hệ Sản phẩm mở ProductRead
                    (SEAM-11).
                  </span>
                </div>
              </label>

              <label className="field">
                <span className="field__label">Trạng thái</span>
                <select
                  className="input"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  {enums.statuses.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field tg__form-wide">
                <span className="field__label">Ghi chú</span>
                <input
                  className="input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
            </div>
          </section>

          {/* Khối B — Paper options */}
          <section>
            <div className="tg__section-head">
              <h3 className="tg__section-title">
                Phương án giấy <span className="tg__req">(bắt buộc ≥1)</span>
              </h3>
              <button type="button" className="btn btn--ghost" onClick={addPaper}>
                + Thêm phương án giấy
              </button>
            </div>
            <div className="tg__opt-list">
              {papers.map((p, i) => (
                <PaperEditor
                  key={p.key}
                  paper={p}
                  index={i}
                  canRemove={papers.length > 1}
                  paperReady={paperReady}
                  paperMsg={paperMsg}
                  token={token}
                  onChange={(patch) => updatePaper(p.key, patch)}
                  onRemove={() => removePaper(p.key)}
                />
              ))}
            </div>
          </section>

          {/* Khối E — Operations (gia công) */}
          <section>
            <div className="tg__section-head">
              <h3 className="tg__section-title">Công đoạn gia công</h3>
              <button type="button" className="btn btn--ghost" onClick={addOp}>
                + Thêm công đoạn
              </button>
            </div>
            {ops.length === 0 ? (
              <p className="tg__muted tg__opt-empty">
                Chưa có công đoạn gia công. Đơn giá khoán/NCC treo SEAM-08/12.
              </p>
            ) : (
              <div className="tg__opt-list">
                {ops.map((o, i) => (
                  <div className="tg__opt card" key={o.key}>
                    <div className="tg__opt-head">
                      <span className="tg__opt-badge">#{i + 1}</span>
                      <div className="tg__opt-tools">
                        <button
                          type="button"
                          className="btn btn--ghost tg__rowbtn tg__rowbtn--danger"
                          onClick={() => removeOp(o.key)}
                        >
                          Xoá
                        </button>
                      </div>
                    </div>
                    <div className="tg__opt-grid">
                      <label className="field tg__form-wide">
                        <span className="field__label">Tên công đoạn *</span>
                        <input
                          className="input"
                          value={o.name}
                          onChange={(e) => updateOp(o.key, { name: e.target.value })}
                          placeholder="Cán màng, bế, đóng cuốn…"
                        />
                      </label>
                      <label className="field">
                        <span className="field__label">Hình thức</span>
                        <select
                          className="input"
                          value={o.execution_mode}
                          onChange={(e) =>
                            updateOp(o.key, { execution_mode: e.target.value })
                          }
                        >
                          {enums.execution_modes.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="field">
                        <span className="field__label">Đơn giá</span>
                        <span className="tg__suggest tg__suggest--warn">
                          {o.execution_mode === "internal"
                            ? "Đơn giá khoán chưa sẵn sàng (SEAM-08)"
                            : "Đơn giá NCC chưa sẵn sàng (SEAM-12)"}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {formError && (
            <div className="banner banner--error" role="alert">
              {formError}
            </div>
          )}

          <div className="tg__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>
              Huỷ
            </Button>
            <Button type="submit" variant="primary" loading={saving}>
              Lưu
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PaperEditor({
  paper,
  index,
  canRemove,
  paperReady,
  paperMsg,
  token,
  onChange,
  onRemove,
}: {
  paper: PaperForm;
  index: number;
  canRemove: boolean;
  paperReady: boolean;
  paperMsg: string;
  token: string | null;
  onChange: (patch: Partial<PaperForm>) => void;
  onRemove: () => void;
}) {
  // Parallel số-con/khổ suggestion (§31a) — pure geometry via the backend endpoint. It
  // needs a piece size; until SEAM-11 supplies SP cấu phần, the estimator may enter a
  // reference piece size to preview the hint (the manual pieces value stays authoritative).
  const [pieceW, setPieceW] = useState("");
  const [pieceH, setPieceH] = useState("");
  const [suggest, setSuggest] = useState<{ pieces: number; message: string | null } | null>(
    null,
  );

  useEffect(() => {
    if (!token) return;
    const sw = Number(paper.sheet_w);
    const sh = Number(paper.sheet_h);
    const pw = Number(pieceW);
    const ph = Number(pieceH);
    if (!(sw > 0 && sh > 0 && pw > 0 && ph > 0)) {
      setSuggest(null);
      return;
    }
    let cancelled = false;
    api.costings
      .suggestPieces(token, {
        sheet_w: sw,
        sheet_h: sh,
        piece_w: pw,
        piece_h: ph,
        grain_locked: paper.grain_locked,
      })
      .then((res) => !cancelled && setSuggest(res))
      .catch(() => !cancelled && setSuggest(null));
    return () => {
      cancelled = true;
    };
  }, [token, paper.sheet_w, paper.sheet_h, pieceW, pieceH, paper.grain_locked]);

  const entered = Number(paper.pieces_per_sheet);
  const showMismatch =
    suggest != null && suggest.pieces > 0 && Number.isInteger(entered) && entered > 0 &&
    entered !== suggest.pieces;

  return (
    <div className="tg__opt card">
      <div className="tg__opt-head">
        <span className="tg__opt-badge">Giấy #{index + 1}</span>
        <div className="tg__opt-tools">
          <button
            type="button"
            className="btn btn--ghost tg__rowbtn tg__rowbtn--danger"
            disabled={!canRemove}
            onClick={onRemove}
          >
            Xoá
          </button>
        </div>
      </div>

      <div className="tg__opt-grid">
        {/* SEAM-07: paper cost picker — explicit "chưa sẵn sàng" until Danh mục Giấy built. */}
        <label className="field tg__form-wide">
          <span className="field__label">Giấy tờ in (SEAM-07)</span>
          {paperReady ? (
            <input
              className="input"
              value={paper.sheet_paper_master_id}
              onChange={(e) => onChange({ sheet_paper_master_id: e.target.value })}
              placeholder="Chọn giấy"
            />
          ) : (
            <div className="tg__seam" role="note">
              <span className="tg__seam-tag">{paperMsg}</span>
              <span className="tg__muted">
                Giá per-ram/kg + lô + giấy khách (cost=0) khi phân hệ Giấy/Kho có sẵn (SEAM-07).
              </span>
            </div>
          )}
        </label>

        <label className="field">
          <span className="field__label">Khổ tờ rộng (cm)</span>
          <input
            className="input"
            type="number"
            step="0.1"
            value={paper.sheet_w}
            onChange={(e) => onChange({ sheet_w: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field__label">Khổ tờ cao (cm)</span>
          <input
            className="input"
            type="number"
            step="0.1"
            value={paper.sheet_h}
            onChange={(e) => onChange({ sheet_h: e.target.value })}
          />
        </label>

        <label className="field">
          <span className="field__label">Số con/khổ * (nhập tay)</span>
          <input
            className="input"
            type="number"
            min="1"
            value={paper.pieces_per_sheet}
            onChange={(e) => onChange({ pieces_per_sheet: e.target.value })}
          />
          {suggest != null && suggest.pieces > 0 && (
            <span className={`tg__suggest${showMismatch ? " tg__suggest--warn" : ""}`}>
              Gợi ý: <strong>{suggest.pieces}</strong> con/khổ
              {showMismatch ? ` — bạn nhập ${entered}?` : ""}
            </span>
          )}
          {suggest != null && suggest.pieces === 0 && suggest.message && (
            <span className="tg__suggest tg__suggest--warn">{suggest.message}</span>
          )}
        </label>

        <label className="field">
          <span className="field__label">Khổ SP tham chiếu — rộng (cm)</span>
          <input
            className="input"
            type="number"
            step="0.1"
            value={pieceW}
            onChange={(e) => setPieceW(e.target.value)}
            placeholder="để xem gợi ý"
          />
        </label>
        <label className="field">
          <span className="field__label">Khổ SP tham chiếu — cao (cm)</span>
          <input
            className="input"
            type="number"
            step="0.1"
            value={pieceH}
            onChange={(e) => setPieceH(e.target.value)}
            placeholder="để xem gợi ý"
          />
        </label>

        <label className="tg__check field">
          <input
            type="checkbox"
            checked={paper.grain_locked}
            onChange={(e) => onChange({ grain_locked: e.target.checked })}
          />
          <span>Ràng buộc thớ (grain locked — gợi ý bỏ nhánh xoay)</span>
        </label>
        <label className="tg__check field">
          <input
            type="checkbox"
            checked={paper.selected}
            onChange={(e) => onChange({ selected: e.target.checked })}
          />
          <span>Phương án được chọn</span>
        </label>
      </div>
    </div>
  );
}

// --- Delete confirm ---------------------------------------------------------

function ConfirmDeleteDialog({
  costing,
  onCancel,
  onConfirm,
}: {
  costing: CostingRow;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="tg__overlay" role="dialog" aria-modal="true" aria-label="Xoá phương án">
      <div className="tg__dialog tg__dialog--sm card">
        <div className="tg__dialog-head">
          <h2>Xoá phương án tính giá</h2>
          <button type="button" className="tg__close" aria-label="Đóng" onClick={onCancel}>
            ✕
          </button>
        </div>
        <div className="tg__dialog-body">
          <p>
            Xoá phương án <strong>{costing.code}</strong>? Các phương án giấy + công đoạn con sẽ
            bị xoá theo. Hành động không thể hoàn tác.
          </p>
          <div className="tg__dialog-actions">
            <Button type="button" variant="ghost" onClick={onCancel}>
              Huỷ
            </Button>
            <Button
              type="button"
              variant="primary"
              loading={busy}
              onClick={() => {
                setBusy(true);
                onConfirm();
              }}
            >
              Xoá
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
