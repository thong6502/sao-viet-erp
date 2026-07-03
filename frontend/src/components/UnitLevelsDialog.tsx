// Danh mục cấp đơn vị (spec-06 / PBI-4009): a self-contained modal to add / edit / delete
// organizational tiers (Khối, Phòng, Tổ…). Name + rank must be unique (409 shown inline);
// deleting a level still used by a department is blocked (409). Reuses the ConfirmDialog
// modal shell (cdlg-*) for a consistent look.
import { useEffect, useState } from "react";
import { ApiError, api, type UnitLevel } from "../api/client";
import { useCan } from "../auth/permissions";
import { Button } from "./Button";
import "./confirm-dialog.css";
import "./unit-levels-dialog.css";

interface Props {
  open: boolean;
  token: string | null;
  onClose: () => void;
  /** Called after any successful change so callers can refresh derived data (head titles). */
  onChanged?: () => void;
}

export function UnitLevelsDialog({ open, token, onClose, onChanged }: Props) {
  const [levels, setLevels] = useState<UnitLevel[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Add-row form.
  const [name, setName] = useState("");
  const [rank, setRank] = useState("");
  const [headTitle, setHeadTitle] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // Inline edit of one row.
  const [editId, setEditId] = useState<number | null>(null);
  const [eName, setEName] = useState("");
  const [eRank, setERank] = useState("");
  const [eTitle, setETitle] = useState("");
  const [rowError, setRowError] = useState<string | null>(null);
  const [rowBusy, setRowBusy] = useState(false);

  const can = useCan();
  const canCreate = can("phong_ban", "create");
  const canUpdate = can("phong_ban", "update");
  const canDelete = can("phong_ban", "delete");

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setEditId(null);
    api.rbac
      .unitLevels(token)
      .then((ls) => !cancelled && setLevels(ls))
      .catch(() => !cancelled && setLoadError("Không tải được danh mục cấp."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, token]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !adding && !rowBusy) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, adding, rowBusy, onClose]);

  if (!open) return null;

  async function reload() {
    if (!token) return;
    setLevels(await api.rbac.unitLevels(token));
    onChanged?.();
  }

  async function add() {
    const rk = Number(rank);
    if (!token || !name.trim() || !rank.trim() || !Number.isInteger(rk) || rk < 1) {
      setAddError("Nhập tên và thứ tự (số ≥ 1) hợp lệ.");
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      await api.rbac.createUnitLevel(token, name.trim(), rk, headTitle.trim());
      setName("");
      setRank("");
      setHeadTitle("");
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setAddError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setAddError("Bạn không có quyền thêm cấp.");
      else setAddError("Không thêm được cấp. Vui lòng thử lại.");
    } finally {
      setAdding(false);
    }
  }

  function startEdit(lv: UnitLevel) {
    setEditId(lv.id);
    setEName(lv.name);
    setERank(String(lv.rank));
    setETitle(lv.head_title);
    setRowError(null);
  }

  async function saveEdit() {
    const rk = Number(eRank);
    if (!token || editId == null || !eName.trim() || !Number.isInteger(rk) || rk < 1) {
      setRowError("Nhập tên và thứ tự (số ≥ 1) hợp lệ.");
      return;
    }
    setRowBusy(true);
    setRowError(null);
    try {
      await api.rbac.updateUnitLevel(token, editId, eName.trim(), rk, eTitle.trim());
      setEditId(null);
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) setRowError(err.message);
      else setRowError("Không lưu được cấp. Vui lòng thử lại.");
    } finally {
      setRowBusy(false);
    }
  }

  async function remove(lv: UnitLevel) {
    if (!token || rowBusy) return;
    setRowBusy(true);
    setRowError(null);
    setEditId(lv.id);
    try {
      await api.rbac.deleteUnitLevel(token, lv.id);
      setEditId(null);
      await reload();
    } catch (err) {
      // 409 = a department still uses this level (delete blocked).
      if (err instanceof ApiError && err.isConflict) setRowError(err.message);
      else if (err instanceof ApiError && err.isForbidden)
        setRowError("Bạn không có quyền xóa cấp.");
      else setRowError("Không xóa được cấp. Vui lòng thử lại.");
    } finally {
      setRowBusy(false);
    }
  }

  return (
    <div className="cdlg-overlay" onMouseDown={() => !adding && !rowBusy && onClose()}>
      <div
        className="cdlg cdlg--wide"
        role="dialog"
        aria-modal="true"
        aria-label="Danh mục cấp đơn vị"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="cdlg__head">
          <h2 className="cdlg__title">Danh mục cấp đơn vị</h2>
        </div>
        <div className="cdlg__body">
          <p className="ulvl__hint">
            Khai báo các cấp (vd Khối → Phòng → Tổ) với thứ tự cao→thấp và chức danh người đứng đầu.
          </p>

          {loading ? (
            <p className="depts__status">Đang tải…</p>
          ) : loadError ? (
            <div className="banner banner--error" role="alert">
              {loadError}
            </div>
          ) : (
            <>
              <div className="ulvl__row ulvl__row--head" aria-hidden="true">
                <span>Tên cấp</span>
                <span>Thứ tự</span>
                <span>Chức danh đứng đầu</span>
                <span />
              </div>
              {levels.length === 0 ? (
                <p className="depts__hint">
                  {canCreate ? "Chưa có cấp nào. Thêm cấp đầu tiên bên dưới." : "Chưa có cấp nào."}
                </p>
              ) : (
                <ul className="ulvl__list">
                  {levels.map((lv) =>
                    editId === lv.id ? (
                      <li key={lv.id} className="ulvl__row ulvl__row--edit">
                        <input
                          className="input"
                          value={eName}
                          onChange={(e) => setEName(e.target.value)}
                          aria-label="Tên cấp"
                        />
                        <input
                          className="input"
                          type="number"
                          min={1}
                          value={eRank}
                          onChange={(e) => setERank(e.target.value)}
                          aria-label="Thứ tự"
                        />
                        <input
                          className="input"
                          value={eTitle}
                          onChange={(e) => setETitle(e.target.value)}
                          aria-label="Chức danh đứng đầu"
                        />
                        <span className="ulvl__actions">
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={rowBusy}
                            onClick={saveEdit}
                          >
                            Lưu
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={rowBusy}
                            onClick={() => setEditId(null)}
                          >
                            Hủy
                          </button>
                        </span>
                      </li>
                    ) : (
                      <li key={lv.id} className="ulvl__row">
                        <span className="ulvl__name">{lv.name}</span>
                        <span className="ulvl__rank">{lv.rank}</span>
                        <span className="ulvl__title">{lv.head_title || "—"}</span>
                        <span className="ulvl__actions">
                          {canUpdate && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={rowBusy}
                              onClick={() => startEdit(lv)}
                            >
                              Sửa
                            </button>
                          )}
                          {canDelete && (
                            <button
                              type="button"
                              className="btn btn--ghost depts__danger-text"
                              disabled={rowBusy}
                              onClick={() => remove(lv)}
                            >
                              Xóa
                            </button>
                          )}
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              )}

              {rowError && (
                <div className="banner banner--error" role="alert">
                  {rowError}
                </div>
              )}

              {/* Add a new level (only if allowed to create). */}
              {canCreate && (
              <div className="ulvl__row ulvl__row--add">
                <input
                  className={`input${addError ? " input--error" : ""}`}
                  placeholder="VD: Ban"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (addError) setAddError(null);
                  }}
                  aria-label="Tên cấp mới"
                />
                <input
                  className={`input${addError ? " input--error" : ""}`}
                  type="number"
                  min={1}
                  placeholder="Thứ tự"
                  value={rank}
                  onChange={(e) => {
                    setRank(e.target.value);
                    if (addError) setAddError(null);
                  }}
                  aria-label="Thứ tự cấp mới"
                />
                <input
                  className="input"
                  placeholder="VD: Trưởng ban"
                  value={headTitle}
                  onChange={(e) => setHeadTitle(e.target.value)}
                  aria-label="Chức danh đứng đầu"
                />
                <span className="ulvl__actions">
                  <Button
                    type="button"
                    variant="accent"
                    loading={adding}
                    disabled={!name.trim() || !rank.trim()}
                    onClick={add}
                  >
                    Thêm
                  </Button>
                </span>
              </div>
              )}
              {addError && (
                <span className="field__error" role="alert">
                  {addError}
                </span>
              )}
            </>
          )}
        </div>
        <div className="cdlg__foot">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onClose}
            disabled={adding || rowBusy}
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
