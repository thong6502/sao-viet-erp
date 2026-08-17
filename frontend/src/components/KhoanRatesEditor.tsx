// Bảng ĐƠN GIÁ KHOÁN của MỘT TỔ — panel trong Cấu hình lương của tổ.
//
// Nguồn dữ liệu: danh mục "Công việc khoán" (`/api/cong-viec-khoan`), CÙNG cửa với màn Cấu hình
// danh mục → Công việc khoán. Không có đường API riêng nữa (5 route `/api/luong/khoan/rates` gỡ
// 17/08/2026): hai đường ghi vào một bảng thì đường không đi qua service danh mục sẽ không ghi nhật
// ký, và tab Nhật ký của màn lặng lẽ thiếu dòng.
//
// Vì sao GIỮ panel này thay vì bắt đi qua màn danh mục: người khai cấu hình lương của một tổ đang
// đứng đúng ngữ cảnh "tổ này ăn khoán những việc gì" — đẩy họ sang màn khác rồi lọc lại theo tổ là
// thêm ba bước cho cùng một việc. Panel lọc `?to=<id tổ>` nên nó là một KHUNG NHÌN của cùng dữ
// liệu, không phải bản sao.
//
// Xoá ở đây là XOÁ MỀM (`PATCH /{id}/active`) — panel không có chỗ bày lý do "còn 3 bước lệnh đang
// dùng" như hộp thoại của màn danh mục, mà xoá hẳn một đơn giá đang được định mức đầu việc trỏ tới
// thì làm mồ côi dữ liệu. Muốn xoá hẳn thì qua màn danh mục, ở đó có đủ câu trả lời.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Info,
  Save,
  X,
} from "lucide-react";
import { type PieceRate, type PieceRateInput } from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";
import { nhanTo } from "../pages/danh-muc/nhanTo";
import { money } from "../utils/format";

const apiKhoan = crud("/api/cong-viec-khoan");
const apiDonVi = crud("/api/don-vi");

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

/** Một đơn vị chọn được: lưu MÃ (`to`), hiện TÊN ("tờ"). */
interface DonViOpt {
  ma: string;
  ten: string;
}

export function KhoanRatesEditor({
  token,
  departmentId,
  deptName,
  onMoDanhMuc,
}: {
  token: string;
  /** Tổ đang khai. Panel LUÔN thuộc một tổ — bảng của mọi tổ thì xem ở màn Cấu hình danh mục. */
  departmentId: number;
  deptName?: string;
  /** Mở màn Cấu hình danh mục → Công việc khoán. Bỏ trống = không hiện đường dẫn (panel vẫn chạy).
   *  Cần có: ba việc panel này KHÔNG làm — xoá hẳn, xem nhật ký, xem/bật lại mục đã ngừng — đều ở
   *  màn kia. Không chỉ đường thì người dùng phải tự mò menu, mà họ đang ở giữa luồng khai lương. */
  onMoDanhMuc?: () => void;
}) {
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [soDaNgung, setSoDaNgung] = useState(0);
  const [editing, setEditing] = useState<PieceRate | "new" | null>(null);
  const [donVis, setDonVis] = useState<DonViOpt[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    // Lọc Ở MÁY CHỦ theo id tổ (`?to=<id>`): so bằng id thì không hụt dòng vì nhãn tổ lệch một chữ.
    // `active: true` — panel này CHỈ khai việc còn dùng. Không lọc thì dòng đã ngừng nằm lẫn vào
    // bảng mà không có dấu hiệu gì, và nút của nó vẫn là "Ngừng dùng" (bấm lại chẳng đổi gì).
    apiKhoan
      .list(token, { to: String(departmentId), active: true, size: 200 })
      .then((r) => setRates(r.items as unknown as PieceRate[]))
      .catch((e) => { setRates([]); setErr(errText(e)); });
    // Đếm mục ĐÃ NGỪNG của tổ (1 request rẻ, chỉ lấy `total`) — chỉ để CHỈ ĐƯỜNG sang màn danh mục,
    // nơi có công tắc "Hiện mục đã ngừng" và nút Bật lại. Không có số này thì người dùng ngừng dùng
    // một dòng, nó biến mất, và không còn dấu hiệu nào cho biết nó đang ở đâu.
    apiKhoan
      .list(token, { to: String(departmentId), active: false, size: 1 })
      .then((r) => setSoDaNgung(r.total))
      .catch(() => setSoDaNgung(0));
    // Đơn vị = danh mục Đơn vị & quy đổi, chỉ mục CÒN DÙNG: mời chọn một đơn vị đã ngừng dùng thì
    // bấm Lưu mới ăn lỗi từ server.
    apiDonVi
      .list(token, { active: true, size: 200 })
      .then((r) => setDonVis(r.items.map((d: Row) => ({ ma: String(d.ma), ten: String(d.ten) }))))
      .catch(() => setDonVis([]));
  }, [token, departmentId]);

  useEffect(() => {
    load();
  }, [load]);

  /** Ngừng dùng một dòng — xem ghi chú đầu file về việc KHÔNG xoá hẳn ở panel này. */
  async function ngungDung(id: number) {
    try {
      await apiKhoan.datActive(token, id, false);
      load();
    } catch (e) {
      setErr(errText(e));
    }
  }

  const tenDonVi = (ma: unknown) => {
    const m = String(ma ?? "").trim();
    if (!m) return "—";
    return donVis.find((d) => d.ma.toLowerCase() === m.toLowerCase())?.ten ?? m;
  };

  return (
    <div>
      {/* KHÔNG in lại tiêu đề "Đơn giá khoán của tổ": thẻ bọc panel đã ghi "Đơn giá khoán — <tên
          tổ>" ngay trên, hai dòng chữ gần trùng nhau đọc như hai khối khác nhau. Hàng này chỉ còn
          hai HÀNH ĐỘNG: thêm dòng mới, và đường sang màn danh mục cho ba việc panel không làm. */}
      <div className="cc-toolbar">
        {onMoDanhMuc && (
          <button type="button" className="btn btn--ghost" onClick={onMoDanhMuc}
            title="Xoá hẳn · xem nhật ký ai đổi giá · xem và bật lại mục đã ngừng — đều ở màn danh mục">
            Mở trong Cấu hình danh mục
            {soDaNgung > 0 && <span className="chip-count" style={{ marginLeft: 6 }}>{soDaNgung} đã ngừng</span>}
          </button>
        )}
        <div style={{ flex: 1 }} />
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          + Thêm đơn giá
        </button>
      </div>
      {err && (
        <div className="banner banner--error" style={{ marginBottom: 12 }}>
          <AlertCircle size={16} />
          <span>{err}</span>
        </div>
      )}
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr>
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
                <td>{r.ma ?? "—"}</td>
                <td>{r.ten}</td>
                <td>{r.don_vi_ten ?? tenDonVi(r.unit)}</td>
                <td className="lg-num">{money(r.unit_price)}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(r)}>
                    Sửa
                  </button>
                  {/* Chữ "Ngừng dùng" chứ không "Xóa": đó đúng là việc nút này làm. Nhãn "Xóa" mà
                      hành vi là ẩn mềm thì người dùng đi tìm dòng đã "xóa" ở đâu cũng không thấy. */}
                  <button
                    className="btn btn--ghost ns-danger"
                    title="Ẩn khỏi các ô chọn. Bước lệnh và chứng từ cũ giữ nguyên. Xoá hẳn thì vào Cấu hình danh mục → Công việc khoán."
                    onClick={() => ngungDung(r.id)}
                  >
                    Ngừng dùng
                  </button>
                </td>
              </tr>
            ))}
            {rates.length === 0 && (
              <tr>
                <td colSpan={5} className="ns__empty">
                  Chưa có đơn giá khoán nào của tổ {nhanTo(deptName) === "—" ? "này" : nhanTo(deptName)}.
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
          donVis={donVis}
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
  departmentId,
  donVis,
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  departmentId: number;
  donVis: DonViOpt[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [ten, setTen] = useState(rate?.ten ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const nhanDonVi = (ma: string) =>
    donVis.find((d) => d.ma.toLowerCase() === ma.toLowerCase())?.ten ?? ma;

  async function save() {
    setBusy(true);
    setErr(null);
    // `ma` KHÔNG gửi: server cấp `KH-####` khi tạo, và giữ nguyên mã cũ khi sửa (không gửi = không
    // đổi). `group_name` cũng không gửi — server suy từ `department_id`.
    const input: PieceRateInput = {
      department_id: departmentId,
      ten,
      unit,
      unit_price: price,
    };
    try {
      if (rate) await apiKhoan.update(token, rate.id, { ...input, ma: rate.ma });
      else await apiKhoan.create(token, input as unknown as Record<string, unknown>);
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--khoan">
        <header className="ns-modal__head">
          <div>
            <h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
            <div className="ns-modal__subtitle">Công việc, đơn vị tính và đơn giá của tổ này</div>
          </div>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng modal">
            <X size={18} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && (
            <div className="banner banner--error" style={{ marginBottom: 16 }}>
              <AlertCircle size={16} />
              <span>{err}</span>
            </div>
          )}
          <div className="ns-grid">
            <label className="ns-field ns-wizard__full">
              <span className="ns-field__label">Công việc *</span>
              <input
                value={ten}
                autoFocus
                onChange={(e) => setTen(e.target.value)}
                placeholder="vd: Bồi carton 3 lớp E,B"
              />
            </label>
            <div className="ns-field">
              <span className="ns-field__label">Đơn vị *</span>
              {/* Lưu MÃ, hiện TÊN. Dòng cũ mang đơn vị ngoài danh mục thì vẫn tự chèn chính giá trị
                  của nó vào danh sách — không ép đổi, nhưng cũng không lặng lẽ xoá mất. */}
              <ComboBox
                value={unit}
                placeholder="Gõ để tìm đơn vị…"
                options={[
                  ...(unit && !donVis.some((d) => d.ma.toLowerCase() === unit.toLowerCase())
                    ? [{ value: unit, label: `${unit} (ngoài danh mục)` }]
                    : []),
                  ...donVis.map((d) => ({ value: d.ma, label: d.ten })),
                ]}
                emptyText="Không có đơn vị nào khớp. Thêm ở Cấu hình danh mục → Đơn vị & quy đổi."
                onChange={setUnit}
              />
            </div>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá *</span>
              <div className="cl-suffixed">
                <input
                  type="number"
                  min={0}
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                />
                <span>đ/{nhanDonVi(unit.trim()) || "đơn vị"}</span>
              </div>
            </label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !ten.trim() || !unit.trim()}
            title={
              !ten.trim() ? "Nhập tên công việc trước"
                : !unit.trim() ? "Chọn đơn vị trước"
                  : undefined
            }
          >
            <Save size={15} style={{ marginRight: 6 }} />
            {busy ? "Đang lưu…" : "Lưu đơn giá"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ComboBox({
  value,
  options,
  placeholder,
  emptyText = "Không có dòng nào khớp.",
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  placeholder?: string;
  emptyText?: string;
  onChange: (v: string) => void;
}) {
  const [q, setQ] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const nhan = options.find((o) => o.value === value)?.label ?? value ?? "";
  const nq = norm((q ?? "").trim());
  const loc = nq ? options.filter((o) => norm(o.label).includes(nq)) : options;

  const reposition = useCallback(() => {
    if (!inputRef.current) return;
    const r = inputRef.current.getBoundingClientRect();
    const listHeight = listRef.current?.offsetHeight || 210;
    const spaceBelow = window.innerHeight - r.bottom;
    const showAbove = spaceBelow < listHeight && r.top > listHeight;

    setRect({
      top: showAbove ? Math.max(10, r.top - listHeight - 6) : r.bottom + 4,
      left: r.left,
      width: r.width,
    });
  }, []);

  useLayoutEffect(() => {
    if (open) {
      reposition();
    }
  }, [open, reposition, loc.length]);

  useEffect(() => {
    if (!open) return;
    const handleDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        wrapRef.current?.contains(target) ||
        listRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
      setQ(null);
    };

    document.addEventListener("mousedown", handleDown);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("mousedown", handleDown);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open, reposition]);

  const chon = (v: string) => {
    onChange(v);
    setQ(null);
    setOpen(false);
  };

  const portalContent = open && (
    <div
      ref={listRef}
      className="khoan-cbx__list"
      role="listbox"
      style={
        rect
          ? {
              position: "fixed",
              top: rect.top,
              left: rect.left,
              width: rect.width,
              zIndex: 9999,
            }
          : { display: "none" }
      }
    >
      {loc.map((o, i) => {
        const selected = o.value === value;
        const active = i === idx;
        return (
          <button
            key={o.value}
            type="button"
            role="option"
            aria-selected={selected}
            className={`khoan-cbx__item${active ? " is-active" : ""}${selected ? " is-on" : ""}`}
            onMouseEnter={() => setIdx(i)}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => chon(o.value)}
          >
            <span className="khoan-cbx__item-text">{o.label}</span>
            {selected && <Check className="khoan-cbx__item-check" size={15} />}
          </button>
        );
      })}
      {loc.length === 0 && (
        <div className="khoan-cbx__empty">
          <Info size={16} className="khoan-cbx__empty-icon" />
          <span>{emptyText}</span>
        </div>
      )}
    </div>
  );

  return (
    <div className={`khoan-cbx${open ? " is-open" : ""}`} ref={wrapRef}>
      <div className="khoan-cbx__input-wrap">
        <input
          ref={inputRef}
          className="khoan-cbx__input"
          value={q ?? nhan}
          placeholder={placeholder}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
            setOpen(true);
          }}
          onFocus={() => {
            setQ("");
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setIdx((i) => Math.min(i + 1, loc.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIdx((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && open && loc[idx]) {
              e.preventDefault();
              chon(loc[idx].value);
            } else if (e.key === "Escape") {
              setOpen(false);
              setQ(null);
            }
          }}
        />
        <ChevronDown className="khoan-cbx__arrow" size={16} />
      </div>
      {createPortal(portalContent, document.body)}
    </div>
  );
}
