// Modal "Xác nhận tăng ca theo phiếu" — Flat Clean UI (07/09/2026 — Đợt 1, mục 1.5; nâng cấp 10/09/2026).
//
// Chủ giữ luật 4 lượt bấm; thợ hay quên cặp bấm tăng ca ⇒ tiền TC = 0 lặng lẽ lúc chốt. Đây là
// đường bù HÀNG LOẠT cho tổ trưởng/HCNS: chọn ngày → máy liệt kê phiếu TC đã duyệt của ngày đó
// (trong phạm vi Chấm bù của người dùng) + tình trạng cặp bấm → tích người thiếu cặp → một nút
// sinh cặp bấm tay có audit. Ai không thiếu (đã có / không đi làm / treo) máy tự bỏ qua, nói rõ vì sao.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type OtConfirmCandidate,
  type OtConfirmResult,
} from "../../../../api/client";
import {
  AlertTriangle,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  FileText,
  Info,
  RefreshCw,
  X,
} from "lucide-react";

// `viec` = VIỆC NGƯỜI PHẢI LÀM khi máy không tự bù được (chủ 10/09/2026: *"vẫn thấy tên nhân viên
// đó nhưng không cho bấm, mà như vậy cũng khó hiểu lắm"*). Trước đó cột "Máy sẽ làm" để "—" nên
// người dùng đứng nhìn cái tên mà không biết bước tiếp theo là gì.
const TINH_TRANG: Record<string, { text: string; cls: string; viec?: string }> = {
  thieu_cap: { text: "Thiếu cặp bấm TC", cls: "thieu_cap" },
  da_co: { text: "Đã có cặp bấm", cls: "da_co", viec: "Không cần làm gì" },
  treo: {
    text: "Thiếu RA ca chính (treo)",
    cls: "treo",
    viec: "Mở ô ngày, chấm bù lượt RA ca chính trước rồi quay lại đây",
  },
  khong_cham: { text: "Không bấm lượt nào", cls: "khong_cham" },
  chua_gan_ca: {
    text: "Chưa gán ca",
    cls: "chua_gan_ca",
    viec: "Gán ca cho ngày này ở Khai ca → Phân ca tháng rồi quay lại",
  },
};

const KIEU: Record<string, string> = {
  bu_cap: "thêm VÀO + RA tăng ca theo phiếu",
  tach_phien: "tách phiên: RA ca chính lúc hết ca + VÀO tăng ca; lượt RA thật thành RA tăng ca",
  chi_cap_tc: "CHỈ thêm VÀO + RA tăng ca theo phiếu — ngày này sẽ KHÔNG có công ca chính",
};

/** Tick được = máy sinh được cặp bấm. Ngày trắng lượt bấm cũng tick được, nhưng phải xác nhận
 *  thêm một nhịp vì nó đóng băng ngày đó thành "chỉ có tăng ca". */
const tickDuoc = (tt: string) => tt === "thieu_cap" || tt === "khong_cham";

type TabSegment = "all" | "thieu_cap" | "khong_cham" | "manual";

export function OtConfirmModal({
  token,
  defaultDate,
  depts,
  onClose,
  onDone,
  onOpenDay,
}: {
  token: string;
  defaultDate: string;
  depts: { id: number; name: string }[];
  onClose: () => void;
  /** Gọi sau khi máy đã sinh cặp bấm — cha tải lại bảng công + kỳ công. */
  onDone: () => void;
  /** Mở ô ngày của đúng người/ngày đó để chấm bù tay — lối ra cho dòng máy không bù được. */
  onOpenDay: (employeeId: number, employeeName: string, date: string) => void;
}) {
  const [date, setDate] = useState(defaultDate);
  const [deptId, setDeptId] = useState<number | "">("");
  const [items, setItems] = useState<OtConfirmCandidate[] | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OtConfirmResult | null>(null);
  const [segment, setSegment] = useState<TabSegment>("all");
  const [showSkipped, setShowSkipped] = useState(false);

  /** Đã hiện lời cảnh báo "ngày trắng ⇒ không có công ca chính" và đang chờ cú bấm thứ hai. */
  const [hoiLaiNgayTrang, setHoiLaiNgayTrang] = useState(false);
  // Lời cảnh báo nằm CUỐI thân modal, mà thân modal cuộn riêng — không kéo nó vào tầm mắt thì
  // người dùng chỉ thấy nút đổi chữ mà không biết vì sao (1440×900 là đủ để nó rơi khỏi màn).
  const canhBaoRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (hoiLaiNgayTrang) {
      canhBaoRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [hoiLaiNgayTrang]);

  const deptMap = useMemo(() => new Map(depts.map((d) => [d.id, d.name])), [depts]);

  const load = useCallback(() => {
    setItems(null);
    setError(null);
    api.attendance
      .otConfirmCandidates(token, date, deptId === "" ? null : deptId)
      .then((r) => {
        setItems(r.items);
        // Tích sẵn ĐÚNG người thiếu cặp bấm. Ngày trắng lượt bấm tick được nhưng KHÔNG tích sẵn:
        // nó đóng băng ngày đó thành "chỉ có tăng ca", phải là quyết định có ý thức của HCNS.
        setChecked(
          new Set(
            r.items
              .filter((x) => x.tinh_trang === "thieu_cap")
              .map((x) => x.employee_id),
          ),
        );
        setHoiLaiNgayTrang(false);
      })
      .catch((e) => {
        setItems([]);
        setError(
          e instanceof Error ? e.message : "Không tải được danh sách phiếu.",
        );
      });
  }, [token, date, deptId]);

  useEffect(() => {
    setResult(null);
    load();
  }, [load]);

  function toggle(id: number, on: boolean) {
    setHoiLaiNgayTrang(false); // đổi danh sách thì hỏi lại từ đầu
    setChecked((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  }

  async function confirm() {
    if (checked.size === 0) return;
    // Ngày trắng lượt bấm: nói thẳng hậu quả rồi mới cho bấm lần hai.
    if (ngayTrangDaChon.length > 0 && !hoiLaiNgayTrang) {
      setHoiLaiNgayTrang(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.attendance.otConfirm(token, {
        date,
        employee_ids: [...checked],
        reason: reason.trim() || null,
        cho_phep_ngay_trang: ngayTrangDaChon.length > 0,
      });
      setResult(res);
      onDone();
      // Tải lại để bảng phản ánh tình trạng mới (đã có cặp bấm).
      const r = await api.attendance.otConfirmCandidates(
        token,
        date,
        deptId === "" ? null : deptId,
      );
      setItems(r.items);
      setChecked(new Set());
      setHoiLaiNgayTrang(false);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Lỗi khi xác nhận tăng ca theo phiếu.",
      );
    } finally {
      setBusy(false);
    }
  }

  // Người ĐÃ CÓ CẶP BẤM thì không còn việc gì ở màn này — ẩn khỏi bảng, chỉ đếm lại một dòng
  // (chủ 10/09/2026: *"đã có cặp bấm tăng ca rồi hiện lên làm gì nữa"*).
  const hienThi = useMemo(
    () => (items ?? []).filter((x) => x.tinh_trang !== "da_co"),
    [items],
  );
  const soDaCo = (items ?? []).length - hienThi.length;
  const soThieu = useMemo(
    () => hienThi.filter((x) => x.tinh_trang === "thieu_cap").length,
    [hienThi],
  );
  const soKhongCham = useMemo(
    () => hienThi.filter((x) => x.tinh_trang === "khong_cham").length,
    [hienThi],
  );
  const soManual = useMemo(
    () => hienThi.filter((x) => !tickDuoc(x.tinh_trang)).length,
    [hienThi],
  );

  const ngayTrangDaChon = useMemo(
    () => hienThi.filter((x) => x.tinh_trang === "khong_cham" && checked.has(x.employee_id)),
    [hienThi, checked],
  );

  const filteredRows = useMemo(() => {
    if (segment === "thieu_cap") return hienThi.filter((x) => x.tinh_trang === "thieu_cap");
    if (segment === "khong_cham") return hienThi.filter((x) => x.tinh_trang === "khong_cham");
    if (segment === "manual") return hienThi.filter((x) => !tickDuoc(x.tinh_trang));
    return hienThi;
  }, [hienThi, segment]);

  // Master checkbox support
  const tickableInFiltered = useMemo(
    () => filteredRows.filter((x) => tickDuoc(x.tinh_trang)),
    [filteredRows],
  );
  const allChecked =
    tickableInFiltered.length > 0 &&
    tickableInFiltered.every((x) => checked.has(x.employee_id));
  const someChecked =
    tickableInFiltered.some((x) => checked.has(x.employee_id)) && !allChecked;

  const masterCheckRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (masterCheckRef.current) {
      masterCheckRef.current.indeterminate = someChecked;
    }
  }, [someChecked]);

  function toggleAll(on: boolean) {
    setHoiLaiNgayTrang(false);
    setChecked((prev) => {
      const next = new Set(prev);
      for (const x of tickableInFiltered) {
        if (on) next.add(x.employee_id);
        else next.delete(x.employee_id);
      }
      return next;
    });
  }

  function renderActionCell(x: OtConfirmCandidate) {
    const st = TINH_TRANG[x.tinh_trang];
    const ok = tickDuoc(x.tinh_trang);

    if (ok && x.kieu) {
      const badgeCls = `cc-otc-action-badge cc-otc-action-badge--${x.kieu}`;
      const badgeText =
        x.kieu === "bu_cap"
          ? "Bù cặp VÀO/RA"
          : x.kieu === "tach_phien"
            ? "Tách phiên"
            : "Chỉ cặp TC";

      return (
        <div className="cc-otc-action-combo">
          <span className={badgeCls}>{badgeText}</span>
          <span className="cc-otc-guidance-text">
            {x.tinh_trang === "khong_cham"
              ? "Ngày trắng: chỉ tính giờ TC theo phiếu"
              : KIEU[x.kieu] ?? "Tự động bù cặp bấm"}
          </span>
          {x.tinh_trang === "khong_cham" && (
            <button
              type="button"
              className="cc-otc-open-day-btn"
              onClick={() => onOpenDay(x.employee_id, x.employee_name, date)}
            >
              Mở ô ngày để chấm bù ca chính
            </button>
          )}
        </div>
      );
    }

    return (
      <div className="cc-otc-action-combo">
        <span className="cc-otc-action-badge cc-otc-action-badge--manual">
          Sửa thủ công
        </span>
        <span className="cc-otc-guidance-text">
          {st?.viec ?? "Cần kiểm tra lại dữ liệu"}
        </span>
        {(x.tinh_trang === "treo" || x.tinh_trang === "chua_gan_ca") && (
          <button
            type="button"
            className="cc-otc-open-day-btn"
            onClick={() => onOpenDay(x.employee_id, x.employee_name, date)}
          >
            Mở ô ngày
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-otc-modal-box">
        <header className="cc-otc-header">
          <div className="cc-otc-header-left">
            <div className="cc-otc-icon-badge">
              <CheckCheck size={18} />
            </div>
            <div className="cc-otc-title-group">
              <div className="cc-otc-title-row">
                <h2 className="cc-otc-title">Xác nhận tăng ca theo phiếu</h2>
                <span className="cc-otc-date-pill">{date}</span>
              </div>
              <p className="cc-otc-subtitle">
                Sinh cặp bấm tăng ca cho người có phiếu đã duyệt nhưng quên bấm — cả tổ một lần.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="cc-otc-close-btn"
            onClick={onClose}
            aria-label="Đóng"
          >
            <X size={18} />
          </button>
        </header>

        <div className="cc-otc-body">
          {error && <div className="banner banner--error cc-otc-error-banner">{error}</div>}

          {/* Level 1 Toolbar: Filters */}
          <div className="cc-otc-toolbar-level1">
            <label className="cc-otc-filter-field">
              <span className="cc-otc-filter-label">Ngày công</span>
              <input
                type="date"
                className="cc-otc-input cc-otc-date-input"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label className="cc-otc-filter-field">
              <span className="cc-otc-filter-label">Phòng ban / tổ</span>
              <select
                className="cc-otc-select"
                value={deptId}
                onChange={(e) =>
                  setDeptId(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">Tất cả trong phạm vi</option>
                {depts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn btn--ghost cc-otc-refresh-btn"
              onClick={load}
              disabled={busy}
              title="Tải lại danh sách"
            >
              <RefreshCw
                size={14}
                className={items === null ? "cc-animate-spin" : ""}
              />
              <span>Tải lại</span>
            </button>
          </div>

          {/* Level 2 Toolbar: Segment Filter Tabs */}
          {items !== null && hienThi.length > 0 && (
            <div className="cc-otc-toolbar-level2">
              <div className="cc-otc-segs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={segment === "all"}
                  className={`cc-otc-seg ${segment === "all" ? "is-active" : ""}`}
                  onClick={() => setSegment("all")}
                >
                  Tất cả <span className="cc-otc-seg-count">{hienThi.length}</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={segment === "thieu_cap"}
                  className={`cc-otc-seg ${segment === "thieu_cap" ? "is-active" : ""}`}
                  onClick={() => setSegment("thieu_cap")}
                >
                  Cần bù cặp <span className="cc-otc-seg-count">{soThieu}</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={segment === "khong_cham"}
                  className={`cc-otc-seg ${segment === "khong_cham" ? "is-active" : ""}`}
                  onClick={() => setSegment("khong_cham")}
                >
                  Ngày trắng <span className="cc-otc-seg-count">{soKhongCham}</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={segment === "manual"}
                  className={`cc-otc-seg ${segment === "manual" ? "is-active" : ""}`}
                  onClick={() => setSegment("manual")}
                >
                  Cần sửa tay <span className="cc-otc-seg-count">{soManual}</span>
                </button>
              </div>

              {soDaCo > 0 && (
                <span className="cc-otc-hidden-hint">
                  Đã ẩn <b>{soDaCo}</b> người đã đủ cặp bấm
                </span>
              )}
            </div>
          )}

          {/* Candidates Table */}
          {items === null ? (
            <p className="cc-otc-empty">Đang tải danh sách phiếu tăng ca…</p>
          ) : items.length === 0 ? (
            <p className="cc-otc-empty">
              Ngày này không có phiếu tăng ca đã duyệt nào trong phạm vi của bạn.
            </p>
          ) : hienThi.length === 0 ? (
            <div className="cc-otc-empty cc-otc-empty--done">
              {soDaCo > 1 ? `Cả ${soDaCo} phiếu` : "Phiếu"} tăng ca của ngày này{" "}
              {soDaCo > 1 ? "đều " : ""}
              <b>đã có cặp bấm</b> — không còn gì phải bù.
            </div>
          ) : filteredRows.length === 0 ? (
            <p className="cc-otc-empty">Không có người nào trong phân loại này.</p>
          ) : (
            <div className="cc-otc-table-wrap">
              <table className="cc-otc-table">
                <thead>
                  <tr>
                    <th style={{ width: 36, textAlign: "center" }}>
                      <input
                        ref={masterCheckRef}
                        type="checkbox"
                        className="cc-otc-checkbox"
                        checked={allChecked}
                        disabled={tickableInFiltered.length === 0}
                        onChange={(e) => toggleAll(e.target.checked)}
                        aria-label="Chọn tất cả người bù được"
                      />
                    </th>
                    <th>Nhân viên</th>
                    <th>Phiếu tăng ca</th>
                    <th>Lượt bấm hôm đó</th>
                    <th>Tình trạng</th>
                    <th>Máy sẽ làm / Hướng dẫn</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((x) => {
                    const st = TINH_TRANG[x.tinh_trang] ?? {
                      text: x.tinh_trang,
                      cls: x.tinh_trang,
                    };
                    const ok = tickDuoc(x.tinh_trang);
                    const deptName = x.department_id
                      ? deptMap.get(x.department_id)
                      : undefined;

                    return (
                      <tr key={x.ticket_id}>
                        <td style={{ textAlign: "center" }}>
                          <input
                            type="checkbox"
                            className="cc-otc-checkbox"
                            disabled={!ok}
                            checked={ok && checked.has(x.employee_id)}
                            onChange={(e) => toggle(x.employee_id, e.target.checked)}
                            aria-label={`Chọn ${x.employee_name}`}
                          />
                        </td>
                        <td>
                          <div className="cc-otc-emp-cell">
                            <span className="cc-otc-emp-name">{x.employee_name}</span>
                            <div className="cc-otc-emp-meta">
                              {x.employee_code && (
                                <span className="cc-otc-emp-code">
                                  {x.employee_code}
                                </span>
                              )}
                              {x.employee_code && deptName && (
                                <span className="cc-otc-emp-sep">·</span>
                              )}
                              {deptName && (
                                <span className="cc-otc-emp-dept">{deptName}</span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td>
                          <div className="cc-otc-time-pill">
                            <span>
                              {x.from_time}
                              {x.from_next_day && (
                                <span className="cc-otc-next-badge">(+1)</span>
                              )}
                            </span>
                            <span className="cc-otc-time-arrow">→</span>
                            <span>
                              {x.to_time}
                              {x.to_next_day && (
                                <span className="cc-otc-next-badge">(+1)</span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td>
                          {x.punches.length === 0 ? (
                            <span className="cc-otc-muted">Không có</span>
                          ) : (
                            <div className="cc-otc-punch-list">
                              {x.punches.map((p, idx) => (
                                <span
                                  key={idx}
                                  className={`cc-otc-punch-chip ${
                                    p.check_type === "in"
                                      ? "cc-otc-punch-chip--in"
                                      : "cc-otc-punch-chip--out"
                                  }`}
                                >
                                  <span className="cc-otc-punch-type">
                                    {p.check_type === "in" ? "V" : "R"}
                                  </span>
                                  <span className="cc-otc-punch-time">{p.time}</span>
                                  {p.next_day && (
                                    <span className="cc-otc-punch-next">(+1)</span>
                                  )}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>
                          <span
                            className={`cc-otc-status-badge cc-otc-status-badge--${st.cls}`}
                          >
                            <span className="cc-otc-status-dot" />
                            <span>{st.text}</span>
                          </span>
                        </td>
                        <td>{renderActionCell(x)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Cảnh báo Ngày Trắng — nhịp xác nhận thứ 2 */}
          {hoiLaiNgayTrang && ngayTrangDaChon.length > 0 && (
            <div className="cc-otc-warn-callout" ref={canhBaoRef}>
              <AlertTriangle size={18} className="cc-otc-warn-callout-icon" />
              <div className="cc-otc-warn-callout-content">
                <div className="cc-otc-warn-callout-title">
                  Cảnh báo: <b>{ngayTrangDaChon.map((x) => x.employee_name).join(", ")}</b>{" "}
                  không bấm lượt nào cả ngày.
                </div>
                <p>
                  Máy chỉ sinh <b>cặp tăng ca theo phiếu</b> — ngày này sẽ{" "}
                  <b>KHÔNG có công ca chính</b>. Đúng khi thợ chỉ được gọi riêng buổi tối;
                  còn nếu họ có làm cả ngày mà quên bấm thì mở ô ngày để chấm bù cả ca
                  chính trước.
                </p>
                <div className="cc-otc-warn-callout-action">
                  <button
                    type="button"
                    className="cc-otc-link-action"
                    onClick={() =>
                      onOpenDay(
                        ngayTrangDaChon[0].employee_id,
                        ngayTrangDaChon[0].employee_name,
                        date,
                      )
                    }
                  >
                    Mở ô ngày cho {ngayTrangDaChon[0].employee_name}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Audit reason input */}
          <div className="cc-otc-audit-box">
            <div className="cc-otc-audit-input-wrap">
              <FileText size={15} className="cc-otc-audit-icon" />
              <input
                type="text"
                className="cc-otc-audit-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Lý do xác nhận (ghi vào nhật ký chấm công — vd: Cả tổ làm tới 20h30 theo lệnh SX)..."
              />
            </div>
          </div>

          {/* Info note */}
          <div className="cc-otc-info-note">
            <Info size={15} className="cc-otc-info-icon" />
            <span>
              Lượt sinh ra là <b>chấm bù</b> có lý do và tên người xác nhận, nguyên nhân
              &quot;được duyệt&quot;; tiền tăng ca vẫn tính theo <b>phiếu ∩ giờ bấm</b>. Xoá
              được ở chi tiết ngày nếu bấm nhầm.
            </span>
          </div>

          {/* Result card with expandable skipped list */}
          {result && (
            <div className="cc-otc-result-banner">
              <div className="cc-otc-result-header">
                <CheckCheck size={16} className="cc-otc-result-icon" />
                <span className="cc-otc-result-title">
                  Đã sinh cặp bấm thành công cho <b>{result.done.length}</b> người.
                </span>
                {result.skipped.length > 0 && (
                  <button
                    type="button"
                    className="cc-otc-skipped-toggle"
                    onClick={() => setShowSkipped(!showSkipped)}
                  >
                    {showSkipped
                      ? "Ẩn danh sách bỏ qua"
                      : `Xem ${result.skipped.length} người bị bỏ qua`}
                    {showSkipped ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                )}
              </div>
              {result.skipped.length > 0 && showSkipped && (
                <ul className="cc-otc-skipped-list">
                  {result.skipped.map((s) => (
                    <li key={s.employee_id}>
                      <b>{s.employee_name ?? `NV #${s.employee_id}`}</b>: {s.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <footer className="cc-otc-footer">
          <div className="cc-otc-footer-summary">
            <span>
              Đã chọn <strong className="cc-otc-num">{checked.size}</strong> người
            </span>
            {ngayTrangDaChon.length > 0 && (
              <span style={{ color: "var(--signal, #b43403)", fontSize: 12 }}>
                (trong đó có {ngayTrangDaChon.length} ngày trắng)
              </span>
            )}
          </div>
          <div className="cc-otc-footer-actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onClose}
              disabled={busy}
            >
              Đóng
            </button>
            <button
              type="button"
              className={`btn btn--primary cc-otc-confirm-btn ${
                hoiLaiNgayTrang ? "cc-otc-confirm-btn--warn" : ""
              }`}
              onClick={confirm}
              disabled={busy || checked.size === 0}
              title={
                checked.size === 0 && soThieu === 0
                  ? 'Không ai trong danh sách này bù được bằng một nút — xem cột "Máy sẽ làm" để biết phải làm gì trước'
                  : undefined
              }
            >
              {busy ? (
                <RefreshCw className="cc-animate-spin" size={14} />
              ) : hoiLaiNgayTrang ? (
                `Tôi hiểu — xác nhận ${checked.size} người`
              ) : (
                `Xác nhận (${checked.size} người)`
              )}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
