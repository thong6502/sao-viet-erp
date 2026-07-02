import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type MachineRow,
  type MachineInput,
  type MachineRateInput,
  type MachineRateRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

const MACHINE_TYPES = [
  { value: "offset", label: "In Offset (Tờ rời)" },
  { value: "digital", label: "In Kỹ thuật số" },
  { value: "large_format", label: "In Khổ lớn (Quảng cáo)" },
  { value: "flexo", label: "In Flexo (Cuộn)" },
  { value: "other", label: "Thiết bị khác" },
];

const PROCESS_TYPES = [
  { value: "in", label: "In ấn" },
  { value: "can_mang", label: "Cán màng" },
  { value: "be", label: "Bế hình / Đột" },
  { value: "gap", label: "Gấp nếp" },
  { value: "dong_cuon", label: "Đóng cuốn" },
  { value: "dong_goi", label: "Đóng gói" },
  { value: "other", label: "Gia công khác" },
];

export function MachinesCatalogPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<MachineRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort] = useState("code");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit" | "rates">(null);
  const [selected, setSelected] = useState<MachineRow | null>(null);
  const [deleting, setDeleting] = useState<MachineRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.machines
      .list(token, {
        q: q.trim() || undefined,
        machine_type: typeFilter || null,
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
        else setError("Không tải được danh mục máy in.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeFilter, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.machines.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được máy.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Thiết bị & Máy in (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Thiết bị & Máy in</h1>
        <p className="md-page__sub">
          Quản lý toàn bộ danh sách máy in, máy gia công, công suất vận hành, và biểu giá giờ máy tương ứng.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={onSearch}>
          <input
            className="input"
            placeholder="Tìm theo tên / mã máy in..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button type="submit" variant="ghost">Tìm</Button>
        </form>

        <select
          className="input md-page__filter"
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
        >
          <option value="">Tất cả loại công nghệ</option>
          {MACHINE_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <div className="md-page__toolbar-spacer" />
        <Button
          variant="primary"
          onClick={() => { setSelected(null); setMode("create"); }}
        >
          + Tạo máy in / Thiết bị
        </Button>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã máy</th>
              <th>Tên thiết bị</th>
              <th>Công nghệ</th>
              <th>Phương thức</th>
              <th>Khổ máy tối đa (cm)</th>
              <th>Tốc độ in</th>
              <th>Giá giờ máy</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="md-page__status">Đang tải dữ liệu...</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="md-page__empty">Không tìm thấy thiết bị nào.</td>
              </tr>
            ) : (
              rows.map((row) => {
                const activeRate = row.rates.find((r) => r.effective_to === null);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => { setSelected(row); setMode("edit"); }}>
                    <td className="md-page__mono">{row.code}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{MACHINE_TYPES.find((t) => t.value === row.machine_type)?.label ?? row.machine_type}</td>
                    <td>
                      <span className="md-page__tag-calc">
                        {PROCESS_TYPES.find((p) => p.value === row.process_type)?.label ?? row.process_type}
                      </span>
                    </td>
                    <td>
                      {row.max_width_cm && row.max_height_cm ? (
                        <span className="md-page__specs">{row.max_width_cm}x{row.max_height_cm} cm</span>
                      ) : (
                        <span className="md-page__muted">Không giới hạn</span>
                      )}
                    </td>
                    <td>
                      <span className="md-page__specs">{row.speed.toLocaleString("vi-VN")} {row.speed_unit}</span>
                    </td>
                    <td>
                      {activeRate ? (
                        <span className="md-page__price">
                          {activeRate.hourly_rate.toLocaleString("vi-VN")} đ/h
                        </span>
                      ) : (
                        <span className="md-page__danger-text">Chưa cấu hình</span>
                      )}
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Kích hoạt" : "Tạm dừng"}
                      </span>
                    </td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("edit"); }}
                      >
                        Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("rates"); }}
                      >
                        Giá giờ máy
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger"
                        onClick={() => setDeleting(row)}
                      >
                        Xóa
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng số: {total} thiết bị · Trang {page}/{totalPages}
          </span>
          <div className="md-page__pager-btns">
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

      {/* Create / Edit Dialog */}
      {(mode === "create" || mode === "edit") && (
        <MachineFormDialog
          existing={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Machine Rates Dialog */}
      {mode === "rates" && selected && (
        <MachineRatesDialog
          machine={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Delete Confirmation */}
      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa thiết bị</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa vĩnh viễn thiết bị <strong>{deleting.name}</strong> ({deleting.code})?</p>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" onClick={() => setDeleting(null)}>Hủy</Button>
                <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function MachineFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: MachineRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [name, setName] = useState(existing?.name ?? "");
  const [mType, setMType] = useState(existing?.machine_type ?? "offset");
  const [pType, setPType] = useState(existing?.process_type ?? "in");
  const [maxWidth, setMaxWidth] = useState(existing?.max_width_cm ? String(existing.max_width_cm) : "");
  const [maxHeight, setMaxHeight] = useState(existing?.max_height_cm ? String(existing.max_height_cm) : "");
  const [minWidth, setMinWidth] = useState(existing?.min_width_cm ? String(existing.min_width_cm) : "");
  const [minHeight, setMinHeight] = useState(existing?.min_height_cm ? String(existing.min_height_cm) : "");
  const [speed, setSpeed] = useState(existing?.speed ? String(existing.speed) : "");
  const [speedUnit, setSpeedUnit] = useState(existing?.speed_unit ?? "to/gio");
  const [setupTime, setSetupTime] = useState(existing?.setup_time_mins ? String(existing.setup_time_mins) : "0");
  const [changeoverTime, setChangeoverTime] = useState(existing?.changeover_time_mins ? String(existing.changeover_time_mins) : "0");
  const [setupWaste, setSetupWaste] = useState(existing?.setup_waste_sheets ? String(existing.setup_waste_sheets) : "0");
  const [materials, setMaterials] = useState<string[]>(existing?.supported_materials ?? ["paper"]);
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const MAT_CHOICES = [
    { value: "paper", label: "Giấy in thường" },
    { value: "decal", label: "Giấy decal dán" },
    { value: "pp", label: "Vải PP quảng cáo" },
    { value: "canvas", label: "Canvas tranh ảnh" },
    { value: "carton", label: "Carton bao bì" },
  ];

  function toggleMaterial(val: string) {
    if (materials.includes(val)) {
      setMaterials(materials.filter((x) => x !== val));
    } else {
      setMaterials([...materials, val]);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) return setError("Tên thiết bị không được trống.");
    const sp = Number(speed);
    if (!sp || sp <= 0) return setError("Tốc độ vận hành phải lớn hơn 0 để tránh chia cho 0 khi tính toán.");
    if (!speedUnit.trim()) return setError("Đơn vị đo tốc độ là bắt buộc.");

    const payload: MachineInput = {
      name: name.trim(),
      machine_type: mType,
      process_type: pType,
      max_width_cm: maxWidth ? Number(maxWidth) : null,
      max_height_cm: maxHeight ? Number(maxHeight) : null,
      min_width_cm: minWidth ? Number(minWidth) : null,
      min_height_cm: minHeight ? Number(minHeight) : null,
      speed: sp,
      speed_unit: speedUnit.trim(),
      setup_time_mins: Number(setupTime) || 0,
      changeover_time_mins: Number(changeoverTime) || 0,
      setup_waste_sheets: Number(setupWaste) || 0,
      supported_materials: materials,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.machines.update(token, existing.id, payload);
      } else {
        await api.machines.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu thiết bị thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa thông số máy: ${existing?.code}` : "Tạo máy in / Thiết bị mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field md-page__form-wide">
              <span className="field__label">Tên thiết bị / máy in *</span>
              <input
                className="input"
                placeholder="VD: Offset Mitsubishi 4 màu khổ lớn"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Công nghệ máy</span>
              <select className="input" value={mType} onChange={(e) => setMType(e.target.value)} disabled={isEdit}>
                {MACHINE_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">Công đoạn đảm nhận</span>
              <select className="input" value={pType} onChange={(e) => setPType(e.target.value)}>
                {PROCESS_TYPES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">Tốc độ in tối đa *</span>
              <input
                className="input"
                type="number"
                value={speed}
                onChange={(e) => setSpeed(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Đơn vị tốc độ *</span>
              <input
                className="input"
                placeholder="VD: to/gio, trang/phut, m2/gio"
                value={speedUnit}
                onChange={(e) => setSpeedUnit(e.target.value)}
              />
            </label>

            <label className="field">
              <span className="field__label">Khổ in Rộng tối đa (cm)</span>
              <input className="input" type="number" value={maxWidth} onChange={(e) => setMaxWidth(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Khổ in Cao tối đa (cm)</span>
              <input className="input" type="number" value={maxHeight} onChange={(e) => setMaxHeight(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Khổ in Rộng tối thiểu (cm)</span>
              <input className="input" type="number" value={minWidth} onChange={(e) => setMinWidth(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Khổ in Cao tối thiểu (cm)</span>
              <input className="input" type="number" value={minHeight} onChange={(e) => setMinHeight(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Thời gian Setup (phút)</span>
              <input className="input" type="number" value={setupTime} onChange={(e) => setSetupTime(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Thời gian Chuyển đổi (phút)</span>
              <input className="input" type="number" value={changeoverTime} onChange={(e) => setChangeoverTime(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Hao hụt Setup ban đầu (tờ)</span>
              <input className="input" type="number" value={setupWaste} onChange={(e) => setSetupWaste(e.target.value)} />
            </label>

            <label className="field">
              <span className="field__label">Trạng thái</span>
              <div className="md-page__toggle-wrap">
                <input
                  type="checkbox"
                  id="mc-active-check"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                />
                <label htmlFor="mc-active-check">Kích hoạt hoạt động</label>
              </div>
            </label>
          </div>

          <div className="md-page__choices">
            <span className="field__label">Chất liệu được hỗ trợ</span>
            <div className="md-page__checkboxes">
              {MAT_CHOICES.map((c) => (
                <label key={c.value} className="md-page__checkbox-label">
                  <input
                    type="checkbox"
                    checked={materials.includes(c.value)}
                    onChange={() => toggleMaterial(c.value)}
                  />
                  <span>{c.label}</span>
                </label>
              ))}
            </div>
          </div>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu thiết bị</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MachineRatesDialog({
  machine,
  onClose,
  onSaved,
}: {
  machine: MachineRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();

  const [rates, setRates] = useState<MachineRateRow[]>([]);
  const [hourlyRate, setHourlyRate] = useState("");
  const [minCharge, setMinCharge] = useState("0");
  const [minRunTime, setMinRunTime] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRates = useCallback(() => {
    if (!token) return;
    api.machines
      .get(token, machine.id)
      .then((res) => setRates(res.rates))
      .catch(() => setError("Không tải được biểu giá giờ máy."));
  }, [token, machine.id]);

  useEffect(() => {
    loadRates();
  }, [loadRates]);

  async function handleAddRate(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    const hr = Number(hourlyRate);
    if (!hourlyRate.trim() || hr < 0) return setError("Đơn giá giờ máy phải lớn hơn hoặc bằng 0.");

    const payload: MachineRateInput = {
      hourly_rate: hr,
      min_charge: Number(minCharge) || 0,
      min_run_time_mins: Number(minRunTime) || 0,
      effective_from: effectiveFrom,
    };

    setSaving(true);
    try {
      await api.machines.addRate(token, machine.id, payload);
      setHourlyRate("");
      loadRates();
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu đơn giá mới thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Quản lý giá giờ máy: {machine.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <form className="md-page__rates-form" onSubmit={handleAddRate}>
            <h3 className="md-page__section-title">Thiết lập đơn giá giờ mới</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Giá vận hành / giờ (đ) *</span>
                <input
                  className="input"
                  type="number"
                  placeholder="VD: 550000"
                  value={hourlyRate}
                  onChange={(e) => setHourlyRate(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Cước tối thiểu 1 ca (đ)</span>
                <input
                  className="input"
                  type="number"
                  value={minCharge}
                  onChange={(e) => setMinCharge(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Thời gian chạy tối thiểu (phút)</span>
                <input
                  className="input"
                  type="number"
                  value={minRunTime}
                  onChange={(e) => setMinRunTime(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">Ngày hiệu lực *</span>
                <input
                  className="input"
                  type="date"
                  value={effectiveFrom}
                  onChange={(e) => setEffectiveFrom(e.target.value)}
                />
              </label>
              <div className="md-page__field-btn-align md-page__form-wide">
                <Button type="submit" variant="primary" loading={saving}>Áp dụng đơn giá</Button>
              </div>
            </div>
          </form>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Lịch sử biểu giá</h3>
            <div className="md-page__tablewrap">
              <table className="md-page__table">
                <thead>
                  <tr>
                    <th>Giá giờ (đ/h)</th>
                    <th>Cước tối thiểu (đ)</th>
                    <th>Thời gian chạy tối thiểu</th>
                    <th>Từ ngày</th>
                    <th>Đến ngày</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="md-page__empty">Chưa có biểu giá lịch sử nào.</td>
                    </tr>
                  ) : (
                    rates.map((r) => {
                      const isActive = r.effective_to === null;
                      return (
                        <tr key={r.id}>
                          <td><strong>{r.hourly_rate.toLocaleString("vi-VN")} đ</strong></td>
                          <td>{r.min_charge.toLocaleString("vi-VN")} đ</td>
                          <td>{r.min_run_time_mins} phút</td>
                          <td>{r.effective_from}</td>
                          <td>{r.effective_to ?? <span className="md-page__status-badge is-active">Hiện hành</span>}</td>
                          <td>
                            {isActive ? (
                              <span className="md-page__status-badge is-active">Đang chạy</span>
                            ) : (
                              <span className="md-page__muted">Hết hạn</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
