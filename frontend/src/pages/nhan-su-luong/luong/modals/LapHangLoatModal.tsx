// Lập phiếu lương đợt 1 / tạm ứng — MỘT hộp cho cả một người lẫn nhiều người (25/09/2026).
//
// Chủ chốt: phải đủ ≥ N công tính lương (Cấu hình lương) từ ngày 1 của kỳ tới ngày lập phiếu mới
// được lập — chặn cứng ở máy chủ. Màn này hỏi máy chủ danh sách người trong phạm vi kèm công của
// từng người. Lập cho một người thì tìm tên rồi chọn; cho cả xưởng thì bấm "Chọn tất cả người đủ điều kiện".
// Lương đợt 1 điền sẵn số "Lương trả 1 lần" của từng người; tạm ứng thì nhập số chung rồi áp nhanh
// cho các dòng đã chọn. Có bộ lọc phân loại (Đủ điều kiện, Đã chọn, Chưa đủ công) và tìm kiếm tức thì.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  Coins,
  RotateCcw,
  Search,
  Users,
  Wallet,
  X,
} from "lucide-react";
import {
  api,
  type PayrollPeriod,
  type UngVienTamUng,
  type UngVienTamUngList,
} from "../../../../api/client";
import { Pager, trangHopLe } from "../../../../components/Pager";
import { khopGanDung } from "../../../../utils/timGanDung";
import { errText, khoangKyUng, money, trangThaiKyUng, vuongIds, ymLabel } from "../shared/helpers";

// Nhà máy ~1000 người (25/09/2026): bảng chỉ vẽ 50 dòng một trang (1000 ô tiền cùng lúc là giật),
// thêm lọc theo tổ; "Chọn đủ ĐK" vẫn chọn qua MỌI trang.
const CO_TRANG_HL = 50;

type Kind = "tam_ung" | "luong_dot_1";
type FilterTab = "tat_ca" | "du_dk" | "da_chon" | "chua_du";

function homNay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getInitials(name: string | null): string {
  if (!name) return "NV";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Ô nhập số tiền có định dạng số phân cách hàng nghìn (VND) và hậu tố "đ". */
function MoneyInput({
  value,
  onChange,
  disabled,
  placeholder = "0",
  hasError,
  ariaLabel,
}: {
  value: number;
  onChange: (val: number) => void;
  disabled?: boolean;
  placeholder?: string;
  hasError?: boolean;
  ariaLabel?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [rawText, setRawText] = useState("");

  const displayVal = editing ? rawText : value > 0 ? value.toLocaleString("vi-VN") : "";

  return (
    <div className={`lg-hl-money ${disabled ? "is-disabled" : ""} ${hasError ? "has-error" : ""}`}>
      <input
        type="text"
        inputMode="numeric"
        disabled={disabled}
        aria-label={ariaLabel}
        placeholder={placeholder}
        value={displayVal}
        onFocus={() => {
          setEditing(true);
          setRawText(value > 0 ? String(value) : "");
        }}
        onChange={(e) => {
          const digits = e.target.value.replace(/[^\d]/g, "");
          setRawText(digits);
          onChange(digits ? parseInt(digits, 10) : 0);
        }}
        onBlur={() => {
          setEditing(false);
        }}
      />
      <span className="lg-hl-money__unit">đ</span>
    </div>
  );
}

export function LapHangLoatModal({
  token,
  year,
  month,
  kindBanDau = "luong_dot_1",
  onClose,
  onSaved,
}: {
  token: string;
  year: number;
  month: number;
  kindBanDau?: Kind;
  onClose: () => void;
  onSaved: (soPhieu: number) => void;
}) {
  const [kind, setKind] = useState<Kind>(kindBanDau);
  const [ngay, setNgay] = useState(homNay());
  const ky = `${year}-${String(month).padStart(2, "0")}`;
  const [lyDo, setLyDo] = useState(
    kindBanDau === "luong_dot_1"
      ? `Thanh toán lương đợt 1 tháng ${ymLabel(ky)}`
      : `Tạm ứng lương tháng ${ymLabel(ky)}`
  );
  const [tienChung, setTienChung] = useState(0);
  const [tim, setTim] = useState("");
  const [filterTab, setFilterTab] = useState<FilterTab>("tat_ca");
  const [ds, setDs] = useState<UngVienTamUngList | null>(null);
  const [chon, setChon] = useState<Set<number>>(new Set());
  const [tien, setTien] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [trang, setTrang] = useState(1);
  // Nhân viên máy chủ báo VƯỚNG (cả lượt bị chặn) — nút bỏ chọn đúng họ rồi lập lại.
  const [vuong, setVuong] = useState<number[]>([]);

  const selectAllRef = useRef<HTMLInputElement>(null);

  // Đóng modal bằng phím Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, busy]);

  // Trạng thái KỲ: kỳ ngoài khoảng / đã chốt / đã chi thì khoá nút ngay.
  const [periods, setPeriods] = useState<PayrollPeriod[] | null>(null);
  const kyRange = useMemo(khoangKyUng, []);
  const kyNgoaiKhoang = ky < kyRange.min || ky > kyRange.max;
  const kyStatus = useMemo(() => {
    if (periods === null) return null;
    const p = periods.find((x) => x.year === year && x.month === month);
    return p ? p.status : "chua_tao";
  }, [periods, year, month]);
  const kyNote = trangThaiKyUng(kyStatus);
  const kyChan = kyNgoaiKhoang || kyStatus === "locked" || kyStatus === "paid";

  useEffect(() => {
    let alive = true;
    api.luong
      .periods(token)
      .then((r) => {
        if (alive) setPeriods(r.items);
      })
      .catch(() => {
        if (alive) setPeriods(null);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  // Tự cập nhật lý do gợi ý khi đổi loại phiếu nếu người dùng chưa sửa lý do riêng
  useEffect(() => {
    if (
      !lyDo ||
      lyDo.startsWith("Thanh toán lương đợt 1") ||
      lyDo.startsWith("Lương đợt 1") ||
      lyDo.startsWith("Tạm ứng lương") ||
      lyDo.startsWith("Tạm ứng")
    ) {
      setLyDo(
        kind === "luong_dot_1"
          ? `Thanh toán lương đợt 1 tháng ${ymLabel(ky)}`
          : `Tạm ứng lương tháng ${ymLabel(ky)}`
      );
    }
  }, [kind, ky]);

  const tai = useCallback(async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(ngay) || Number(ngay.slice(0, 4)) < 2000) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await api.luong.ungVienTamUng(token, { year, month, advanceDate: ngay, kind });
      setDs(r);
      setChon(new Set()); // không tick sẵn ai
      setTien(
        Object.fromEntries(
          r.items.map((x) => [x.employee_id, kind === "luong_dot_1" ? x.so_tien_goi_y ?? 0 : 0])
        )
      );
    } catch (e) {
      setErr(errText(e));
    } finally {
      setLoading(false);
    }
  }, [token, year, month, ngay, kind]);

  useEffect(() => {
    void tai();
  }, [tai]);

  const items = ds?.items ?? [];
  const duDk = useMemo(() => items.filter((x) => x.du_dieu_kien), [items]);
  const daChon = useMemo(() => items.filter((x) => chon.has(x.employee_id)), [items, chon]);
  const tong = useMemo(
    () => daChon.reduce((s, x) => s + (tien[x.employee_id] || 0), 0),
    [daChon, tien]
  );
  const chonHetDuDk = duDk.length > 0 && duDk.every((x) => chon.has(x.employee_id));

  // Cập nhật trạng thái indeterminate cho checkbox "chọn tất cả"
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = chon.size > 0 && !chonHetDuDk;
    }
  }, [chon.size, chonHetDuDk]);

  // Lọc theo tab và từ khoá tìm kiếm
  const hienThi = useMemo(() => {
    let list = items;
    if (filterTab === "du_dk") {
      list = list.filter((x) => x.du_dieu_kien);
    } else if (filterTab === "da_chon") {
      list = list.filter((x) => chon.has(x.employee_id));
    } else if (filterTab === "chua_du") {
      list = list.filter((x) => !x.du_dieu_kien);
    }
    if (to) list = list.filter((x) => String(x.department_id ?? "") === to);
    // Tìm KHÔNG DẤU: "nguyen van a" ra "Nguyễn Văn A".
    if (tim.trim()) list = list.filter((x) => khopGanDung(`${x.code ?? ""} ${x.name ?? ""}`, tim));
    return list;
  }, [items, filterTab, chon, tim, to]);
  const dsToHl = useMemo(() => {
    const m = new Map<string, string>();
    for (const x of items) {
      if (x.department_id != null) m.set(String(x.department_id), x.department_name ?? `Tổ #${x.department_id}`);
    }
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1], "vi"));
  }, [items]);
  const trangNay = hienThi.slice((trang - 1) * CO_TRANG_HL, trang * CO_TRANG_HL);
  useEffect(() => setTrang(1), [filterTab, tim, to, kind]);
  useEffect(() => {
    const ve = trangHopLe(trang, hienThi.length, CO_TRANG_HL);
    if (ve !== null) setTrang(ve);
  }, [trang, hienThi.length]);

  function doiChon(x: UngVienTamUng) {
    if (!x.du_dieu_kien) return;
    setChon((s) => {
      const n = new Set(s);
      if (n.has(x.employee_id)) n.delete(x.employee_id);
      else n.add(x.employee_id);
      return n;
    });
  }

  function chonTatCaDuDk() {
    setChon(chonHetDuDk ? new Set() : new Set(duDk.map((x) => x.employee_id)));
  }

  // Chọn người đủ điều kiện công và chưa có phiếu kỳ này (tránh lập trùng)
  const duDkChuaCoPhieu = useMemo(
    () => duDk.filter((x) => x.so_phieu_da_co === 0),
    [duDk]
  );

  function chonDuDkChuaCoPhieu() {
    setChon(new Set(duDkChuaCoPhieu.map((x) => x.employee_id)));
  }

  function apTienChung() {
    if (tienChung <= 0 || chon.size === 0) return;
    setTien((t) => {
      const n = { ...t };
      for (const id of chon) n[id] = tienChung;
      return n;
    });
  }

  function chonPreset(amt: number) {
    setTienChung(amt);
    if (chon.size > 0) {
      setTien((t) => {
        const n = { ...t };
        for (const id of chon) n[id] = amt;
        return n;
      });
    }
  }

  function khoiPhucDinhMuc() {
    if (!items.length) return;
    setTien(
      Object.fromEntries(
        items.map((x) => [x.employee_id, x.so_tien_goi_y ?? 0])
      )
    );
  }

  const thieuTien = daChon.filter((x) => !(tien[x.employee_id] > 0));

  async function luu() {
    if (daChon.length === 0) {
      setErr("Chưa chọn nhân viên nào để lập phiếu.");
      return;
    }
    if (kyChan) {
      setErr(
        kyNgoaiKhoang
          ? `Kỳ ${ymLabel(ky)} nằm ngoài khoảng lập phiếu (${ymLabel(kyRange.min)} – ${ymLabel(kyRange.max)}).`
          : `Kỳ ${ymLabel(ky)} đã khoá — không lập được phiếu cho kỳ này.`
      );
      return;
    }
    if (thieuTien.length > 0) {
      setErr(`${thieuTien.length} người đã chọn chưa có số tiền (vd: ${thieuTien[0].name}).`);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await api.luong.createAdvancesBulk(token, {
        period_year: year,
        period_month: month,
        advance_date: ngay,
        kind,
        reason: lyDo.trim() || null,
        items: daChon.map((x) => ({ employee_id: x.employee_id, amount: tien[x.employee_id] })),
      });
      onSaved(r.items.length);
    } catch (e) {
      setErr(errText(e));
      setVuong(vuongIds(e));
      setBusy(false);
    }
  }

  return (
    <div
      className="ns-modal"
      role="dialog"
      aria-modal="true"
      aria-label={kind === "luong_dot_1" ? "Lập phiếu lương đợt 1" : "Lập phiếu tạm ứng lương"}
    >
      <div className="ns-modal__box ns-modal__box--wide lg-hl">
        {/* Header hiện đại với icon chuyên biệt & badge kỳ lương */}
        <header className="ns-modal__head">
          <div className="lg-hl-head__title-wrap">
            <div className="lg-hl-head__icon">
              {kind === "luong_dot_1" ? <Wallet size={20} /> : <Coins size={20} />}
            </div>
            <div>
              <h2 className="lg-hl-head__title">
                {kind === "luong_dot_1" ? "Lập phiếu lương đợt 1" : "Lập phiếu tạm ứng lương"}
                <span className="lg-hl-head__badge">Kỳ {ymLabel(ky)}</span>
              </h2>
            </div>
          </div>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng" disabled={busy}>
            <X size={18} />
          </button>
        </header>

        <div className="ns-modal__body">
          {err && (
            <div className="banner banner--error" role="alert">
              <AlertCircle size={15} />
              <span>{err}</span>
              {vuong.length > 0 && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    setChon((s) => new Set([...s].filter((id) => !vuong.includes(id))));
                    setVuong([]);
                    setErr(null);
                  }}
                >
                  Bỏ chọn {vuong.length} người vướng
                </button>
              )}
            </div>
          )}

          {/* Cảnh báo trạng thái kỳ nếu bị khoá hoặc ngoài khoảng */}
          {kyNgoaiKhoang ? (
            <div className="banner banner--error" role="alert">
              <AlertCircle size={15} />
              <span>
                Kỳ {ymLabel(ky)} nằm ngoài khoảng lập phiếu ({ymLabel(kyRange.min)} – {ymLabel(kyRange.max)}) — vui lòng đổi kỳ trên thanh công cụ.
              </span>
            </div>
          ) : (
            kyChan &&
            kyNote && (
              <div className="banner banner--error" role="alert">
                <AlertCircle size={15} />
                <span>{kyNote.text}</span>
              </div>
            )
          )}

          {/* Bộ chọn loại phiếu (Segmented Switcher) */}
          <div className="lg-hl-mode">
            <div className="lg-hl-mode__tabs" role="radiogroup" aria-label="Loại phiếu">
              <button
                type="button"
                role="radio"
                aria-checked={kind === "luong_dot_1"}
                className={`lg-hl-mode__tab ${kind === "luong_dot_1" ? "is-active" : ""}`}
                onClick={() => setKind("luong_dot_1")}
              >
                <Wallet size={15} />
                <span>Lương đợt 1</span>
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={kind === "tam_ung"}
                className={`lg-hl-mode__tab ${kind === "tam_ung" ? "is-active" : ""}`}
                onClick={() => setKind("tam_ung")}
              >
                <Coins size={15} />
                <span>Tạm ứng</span>
              </button>
            </div>
            <div className="lg-hl-mode__desc">
              {kind === "luong_dot_1" ? (
                <span>
                  Tự động điền theo <b>“Lương trả 1 lần”</b> trong hồ sơ nhân sự (có thể sửa từng người).
                </span>
              ) : (
                <span>
                  Nhập số tiền linh hoạt hoặc áp hàng loạt số tiền cho các nhân viên được chọn.
                </span>
              )}
            </div>
          </div>

          {/* Dải chỉ số KPI gọn gàng (UI_DESIGN §4) */}
          <div className="lg-hl-kpi">
            <div className="lg-hl-kpi__item">
              <div className="lg-hl-kpi__icon">
                <Calendar size={14} />
              </div>
              <div className="lg-hl-kpi__content">
                <span className="lg-hl-kpi__label">Ngưỡng công</span>
                <span className="lg-hl-kpi__val">
                  {ds && ds.nguong > 0 ? (
                    <>
                      ≥ <b>{ds.nguong.toLocaleString("vi-VN")}</b> công ({ds.den_ngay}/{month})
                    </>
                  ) : (
                    "Không yêu cầu (tắt)"
                  )}
                </span>
              </div>
            </div>

            <div className="lg-hl-kpi__sep" />

            <div className="lg-hl-kpi__item">
              <div className="lg-hl-kpi__icon">
                <Users size={14} />
              </div>
              <div className="lg-hl-kpi__content">
                <span className="lg-hl-kpi__label">Đủ điều kiện</span>
                <span className="lg-hl-kpi__val">
                  <b>{duDk.length}</b> / {items.length} người
                </span>
              </div>
            </div>

            <div className="lg-hl-kpi__sep" />

            <div className="lg-hl-kpi__item">
              <div className="lg-hl-kpi__icon">
                <CheckCircle2 size={14} />
              </div>
              <div className="lg-hl-kpi__content">
                <span className="lg-hl-kpi__label">Đang chọn</span>
                <span className="lg-hl-kpi__val">
                  <b>{daChon.length}</b> người
                </span>
              </div>
            </div>

            <div className="lg-hl-kpi__sep" />

            <div className="lg-hl-kpi__item">
              <div className="lg-hl-kpi__icon">
                <Coins size={14} />
              </div>
              <div className="lg-hl-kpi__content">
                <span className="lg-hl-kpi__label">Tổng tạm tính</span>
                <span className="lg-hl-kpi__val">
                  <b>{money(tong)}đ</b>
                </span>
              </div>
            </div>
          </div>

          {/* Form tham số: Ngày lập, Lý do, Công cụ gán tiền */}
          <div className="lg-hl-form">
            <div className="lg-hl-form__main">
              <div className="lg-hl-field">
                <label className="lg-hl-field__label">
                  <Calendar size={13} />
                  <span>Ngày lập phiếu</span>
                </label>
                <input
                  type="date"
                  className="lg-hl-input"
                  value={ngay}
                  onChange={(e) => setNgay(e.target.value)}
                />
              </div>

              <div className="lg-hl-field lg-hl-field--grow">
                <label className="lg-hl-field__label">
                  <span>Lý do / Nội dung</span>
                </label>
                <input
                  type="text"
                  className="lg-hl-input"
                  value={lyDo}
                  onChange={(e) => setLyDo(e.target.value)}
                  placeholder={kind === "tam_ung" ? "vd: Tạm ứng giữa tháng..." : "vd: Thanh toán lương đợt 1..."}
                />
              </div>
            </div>

            {/* Mức chung cho CẢ HAI loại (chủ 25/09/2026: "lương đợt 1 vẫn có mức chung") — đợt 1
                điền sẵn theo hồ sơ, áp mức chung là đè lên; "Khôi phục định mức" quay về số hồ sơ. */}
            <div className="lg-hl-form__bulk">
              <div className="lg-hl-bulk-left">
                <span className="lg-hl-bulk-label">Áp số tiền chung:</span>
                <div className="lg-hl-presets">
                  {[1000000, 2000000, 3000000, 5000000].map((amt) => (
                    <button
                      key={amt}
                      type="button"
                      className="lg-hl-preset-btn"
                      onClick={() => chonPreset(amt)}
                      title={`Chọn nhanh ${money(amt)}đ`}
                    >
                      {amt / 1000000}tr
                    </button>
                  ))}
                </div>
                <div className="lg-hl-bulk-input-wrap">
                  <MoneyInput
                    value={tienChung}
                    onChange={setTienChung}
                    placeholder="Nhập số tiền..."
                    ariaLabel="Số tiền chung áp dụng"
                  />
                </div>
                <button
                  type="button"
                  className="btn btn--secondary lg-hl-bulk-btn"
                  onClick={apTienChung}
                  disabled={daChon.length === 0 || tienChung <= 0}
                  title={daChon.length === 0 ? "Chọn ít nhất 1 người để áp dụng" : undefined}
                >
                  Áp cho {daChon.length} người
                </button>
              </div>

              {kind === "luong_dot_1" && (
                <div className="lg-hl-bulk-right">
                  <button
                    type="button"
                    className="btn btn--ghost lg-hl-reset-btn"
                    onClick={khoiPhucDinhMuc}
                    title="Đặt lại số tiền của mọi người theo 'Lương trả 1 lần' trong hồ sơ"
                  >
                    <RotateCcw size={13} />
                    <span>Khôi phục định mức</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Thanh công cụ lọc tab, tìm kiếm và nút chọn nhanh */}
          <div className="lg-hl-toolbar">
            <div className="lg-hl-filters">
              <button
                type="button"
                className={`lg-hl-filter-btn ${filterTab === "tat_ca" ? "is-active" : ""}`}
                onClick={() => setFilterTab("tat_ca")}
              >
                Tất cả <span className="lg-hl-filter-count">{items.length}</span>
              </button>
              <button
                type="button"
                className={`lg-hl-filter-btn ${filterTab === "du_dk" ? "is-active" : ""}`}
                onClick={() => setFilterTab("du_dk")}
              >
                Đủ điều kiện{" "}
                <span className="lg-hl-filter-count">{duDk.length}</span>
              </button>
              <button
                type="button"
                className={`lg-hl-filter-btn ${filterTab === "da_chon" ? "is-active" : ""}`}
                onClick={() => setFilterTab("da_chon")}
              >
                Đã chọn{" "}
                <span className="lg-hl-filter-count">{chon.size}</span>
              </button>
              <button
                type="button"
                className={`lg-hl-filter-btn ${filterTab === "chua_du" ? "is-active" : ""}`}
                onClick={() => setFilterTab("chua_du")}
              >
                Chưa đủ công{" "}
                <span className="lg-hl-filter-count">{items.length - duDk.length}</span>
              </button>
            </div>

            <div className="lg-hl-actions">
              {dsToHl.length > 1 && (
                <select
                  className="lg-dept-filter"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  aria-label="Lọc theo tổ"
                >
                  <option value="">Tất cả phòng / tổ</option>
                  {dsToHl.map(([id, ten]) => (
                    <option key={id} value={id}>
                      {ten}
                    </option>
                  ))}
                </select>
              )}
              <div className="lg-hl-search">
                <Search size={14} className="lg-hl-search__icon" />
                <input
                  type="text"
                  placeholder="Tìm tên, mã nhân viên..."
                  value={tim}
                  onChange={(e) => setTim(e.target.value)}
                />
                {tim && (
                  <button
                    type="button"
                    className="lg-hl-search__clear"
                    onClick={() => setTim("")}
                    aria-label="Xoá tìm kiếm"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>

              <button
                type="button"
                className="btn btn--secondary lg-hl-quick-select"
                onClick={chonDuDkChuaCoPhieu}
                disabled={loading || duDkChuaCoPhieu.length === 0}
                title="Chọn tất cả người đủ điều kiện công và chưa có phiếu kỳ này"
              >
                <Check size={14} />
                <span>Chọn đủ ĐK ({duDkChuaCoPhieu.length})</span>
              </button>

              {chon.size > 0 && (
                <button
                  type="button"
                  className="btn btn--ghost lg-hl-deselect"
                  onClick={() => setChon(new Set())}
                >
                  Bỏ chọn ({chon.size})
                </button>
              )}
            </div>
          </div>

          {/* Bảng danh sách nhân viên */}
          <div className="lg-hl-table-container">
            <table className="ns__table lg-hl-table">
              <thead>
                <tr>
                  <th className="lg-hl-col-check">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      aria-label="Chọn tất cả người đủ điều kiện"
                      checked={chonHetDuDk}
                      disabled={duDk.length === 0}
                      onChange={chonTatCaDuDk}
                    />
                  </th>
                  <th className="lg-hl-col-emp">Nhân viên</th>
                  <th className="lg-hl-col-cong lg-num">Công tính lương</th>
                  <th className="lg-hl-col-status">Trạng thái phiếu</th>
                  <th className="lg-hl-col-amount lg-num">Số tiền</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} className="lg-hl__empty">
                      <div className="lg-hl-loading">
                        <span className="spinner" />
                        <span>Đang kiểm tra công và tính toán danh sách...</span>
                      </div>
                    </td>
                  </tr>
                ) : hienThi.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="lg-hl__empty">
                      <span>Không tìm thấy nhân viên nào phù hợp bộ lọc.</span>
                    </td>
                  </tr>
                ) : (
                  trangNay.map((x) => {
                    const isSelected = chon.has(x.employee_id);
                    const currentAmt = tien[x.employee_id] ?? 0;
                    const isMissingAmt = isSelected && !(currentAmt > 0);

                    return (
                      <tr
                        key={x.employee_id}
                        className={[
                          "lg-hl-row",
                          x.du_dieu_kien ? "is-eligible" : "is-ineligible",
                          isSelected ? "is-selected" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={(e) => {
                          const target = e.target as HTMLElement;
                          if (target.closest("input") || target.closest("button")) return;
                          doiChon(x);
                        }}
                      >
                        <td className="lg-hl-col-check">
                          <input
                            type="checkbox"
                            aria-label={`Chọn ${x.name ?? x.employee_id}`}
                            checked={isSelected}
                            disabled={!x.du_dieu_kien}
                            onChange={() => doiChon(x)}
                          />
                        </td>
                        <td className="lg-hl-col-emp">
                          <div className="lg-hl-emp-cell">
                            <div className="lg-hl-avatar">{getInitials(x.name)}</div>
                            <div className="lg-hl-emp-meta">
                              <span className="lg-hl-emp-name">{x.name || "—"}</span>
                              <span className="lg-hl-emp-code">{x.code || `#${x.employee_id}`}</span>
                            </div>
                          </div>
                        </td>
                        <td className="lg-hl-col-cong lg-num">
                          {x.du_dieu_kien ? (
                            <span className="lg-hl-cong-txt">
                              {x.cong.toLocaleString("vi-VN")} công
                            </span>
                          ) : (
                            <span
                              className="lg-hl-cong-txt is-warn"
                              title={`Cần tối thiểu ${ds?.nguong ?? 0} công`}
                            >
                              {x.cong.toLocaleString("vi-VN")} / {ds?.nguong ?? 0} công
                            </span>
                          )}
                        </td>
                        <td className="lg-hl-col-status">
                          {x.so_phieu_da_co > 0 ? (
                            <span
                              className="lg-hl-slip-txt"
                              title="Đã có phiếu cùng loại trong kỳ"
                            >
                              Đã có {x.so_phieu_da_co} phiếu
                            </span>
                          ) : (
                            <span className="lg-hl-slip-txt is-none">—</span>
                          )}
                        </td>
                        <td className="lg-hl-col-amount lg-num">
                          <MoneyInput
                            value={currentAmt}
                            disabled={!x.du_dieu_kien}
                            hasError={isMissingAmt}
                            ariaLabel={`Số tiền của ${x.name ?? x.employee_id}`}
                            onChange={(val) => {
                              setTien((t) => ({ ...t, [x.employee_id]: val }));
                              if (val > 0 && x.du_dieu_kien && !chon.has(x.employee_id)) {
                                setChon((s) => new Set(s).add(x.employee_id));
                              }
                            }}
                            placeholder="0"
                          />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <Pager
            total={hienThi.length}
            page={trang}
            size={CO_TRANG_HL}
            onPage={setTrang}
            unit="người"
          />
        </div>

        {/* Chân modal với tổng kết rõ ràng & nút xác nhận */}
        <footer className="ns-modal__foot lg-hl-foot">
          <div className="lg-hl-foot__summary">
            <div className="lg-hl-foot__stat">
              <span>Đã chọn:</span>
              <b className="lg-hl-foot__count">{daChon.length}</b>
              <span className="lg-hl-foot__unit">người</span>
            </div>
            <div className="lg-hl-foot__sep">·</div>
            <div className="lg-hl-foot__stat">
              <span>Tổng cộng:</span>
              <b className="lg-hl-foot__total">{money(tong)}đ</b>
            </div>
            {thieuTien.length > 0 && (
              <span className="lg-hl-foot__err-note">
                ⚠️ {thieuTien.length} người chưa có số tiền
              </span>
            )}
          </div>

          <div className="lg-hl-foot__actions">
            <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>
              Hủy
            </button>
            <button
              type="button"
              className="btn btn--primary lg-hl-submit-btn"
              onClick={() => void luu()}
              disabled={busy || loading || daChon.length === 0 || kyChan || thieuTien.length > 0}
              title={
                kyChan && kyNote
                  ? kyNote.text
                  : thieuTien.length > 0
                  ? "Vui lòng nhập đủ số tiền cho người đã chọn"
                  : undefined
              }
            >
              {busy ? (
                <>
                  <span className="spinner" />
                  <span>Đang lập phiếu...</span>
                </>
              ) : (
                <>
                  <Check size={15} />
                  <span>
                    Lập {daChon.length} phiếu ({money(tong)}đ)
                  </span>
                </>
              )}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
