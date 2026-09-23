// XIN HỦY đơn nghỉ phép / phiếu tăng ca ĐÃ DUYỆT (chủ chốt 23/09/2026 —
// docs/prd-xin-huy-don-da-duyet.md). Dùng CHUNG cho màn Nghỉ phép và màn Tăng ca vì hai bên cùng
// một luật: người lao động chỉ XIN hủy, ai có quyền duyệt thì Đồng ý hủy / Giữ nguyên, đơn vẫn
// hiệu lực tới khi được đồng ý.
import { useEffect, useState, type ReactNode } from "react";
import type { YeuCauHuy } from "../../../api/client";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { fmtDate, fmtDateTime } from "../../../utils/format";
import { AlertCircle, Clock } from "lucide-react";
import "./xin-huy.css";

/** Ngày hôm nay `YYYY-MM-DD` theo giờ máy (máy ở xưởng — giờ VN). */
export function homNayYmd(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const dangXinHuy = (yc: YeuCauHuy | null | undefined): yc is YeuCauHuy =>
  !!yc && yc.trang_thai === "cho";

/** Nhãn trạng thái xin hủy dưới ô Trạng thái của một dòng đơn. Không có yêu cầu / đã rút lại ⇒ không
 *  vẽ gì. Kết quả đã quyết kèm lý do để người lao động không phải mở chi tiết mới biết. */
export function XinHuyNhan({ yc }: { yc: YeuCauHuy | null | undefined }) {
  if (!yc || yc.trang_thai === "rut_lai") return null;
  if (yc.trang_thai === "cho") {
    return (
      <span className="xh-nhan">
        <span className="ns-badge ns-badge--warn xh-badge xh-badge--cho">Đang xin hủy</span>
        {yc.huy_tu_ngay && <span className="xh-nhan__phu">từ {fmtDate(yc.huy_tu_ngay)}</span>}
      </span>
    );
  }
  if (yc.trang_thai === "giu_nguyen") {
    return (
      <span className="xh-nhan">
        <span className="ns-badge ns-badge--muted xh-badge xh-badge--giu-nguyen">Không được hủy</span>
        {yc.ly_do_quyet && <span className="xh-nhan__phu">{yc.ly_do_quyet}</span>}
      </span>
    );
  }
  // dong_y
  if (yc.den_ngay_cu) {
    return (
      <span className="xh-nhan">
        <span className="ns-badge ns-badge--info xh-badge xh-badge--dong-y">Rút ngắn</span>
        <span className="xh-nhan__phu">gốc tới {fmtDate(yc.den_ngay_cu)}</span>
      </span>
    );
  }
  const lyDo = yc.truc_tiep ? yc.ly_do : yc.ly_do_quyet;
  return lyDo ? (
    <span className="xh-nhan">
      <span className="xh-nhan__phu">{yc.truc_tiep ? "Người duyệt hủy: " : "Hủy theo yêu cầu: "}{lyDo}</span>
    </span>
  ) : null;
}

/** Hộp nhập lý do trên nền `ConfirmDialog` — xin hủy / giữ nguyên / người duyệt hủy thẳng. */
export function LyDoDialog({
  open,
  title,
  message,
  label,
  placeholder,
  confirmLabel,
  batBuoc = true,
  danger = false,
  busy,
  error,
  children,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message?: string;
  label: string;
  placeholder?: string;
  confirmLabel: string;
  /** Lý do bắt buộc (xin hủy, giữ nguyên, hủy thẳng). Đồng ý hủy thì không. */
  batBuoc?: boolean;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  children?: ReactNode;
  onConfirm: (lyDo: string) => void;
  onCancel: () => void;
}) {
  const [lyDo, setLyDo] = useState("");
  // Mỗi lần MỞ là ô trống: gửi xong hộp chỉ ẩn (không unmount), để nguyên thì lần xin sau chữ cũ
  // còn nằm đó và chữ mới gõ dính vào (bắt được khi bấm thử 23/09/2026).
  useEffect(() => {
    if (open) setLyDo("");
  }, [open]);
  const dong = () => {
    if (busy) return;
    setLyDo("");
    onCancel();
  };
  return (
    <ConfirmDialog
      open={open}
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      cancelLabel="Quay lại"
      danger={danger}
      busy={busy}
      error={error}
      confirmDisabled={batBuoc && !lyDo.trim()}
      onCancel={dong}
      onConfirm={() => onConfirm(lyDo.trim())}
    >
      {children}
      <label className="xh-field">
        <span className="xh-field__label">
          {label}
          {batBuoc ? " *" : ""}
        </span>
        <textarea
          className="xh-field__input"
          rows={3}
          maxLength={500}
          value={lyDo}
          placeholder={placeholder}
          autoFocus
          onChange={(e) => setLyDo(e.target.value)}
        />
        <div className="xh-field__hint-row">
          <span className="xh-field__hint">Tối đa 500 ký tự</span>
          <span className="xh-field__counter">{lyDo.length}/500</span>
        </div>
      </label>
    </ConfirmDialog>
  );
}

/** Một dòng trong hàng đợi xin hủy của người duyệt. */
export interface XinHuyDong {
  yc: YeuCauHuy;
  ten: string;
  /** Tóm tắt đơn gốc: "Phép năm · 06/10–08/10/2026 (3 ngày)" / "06/10/2026 · 18:00 → 20:00". */
  don: string;
}

/** Khối "Yêu cầu hủy đơn đã duyệt" đặt TRÊN bảng chờ duyệt của người duyệt. Rỗng ⇒ không vẽ. */
export function XinHuyHangDoi({
  dong,
  donVi,
  onQuyet,
}: {
  dong: XinHuyDong[];
  /** "đơn" / "phiếu" — để câu chữ khớp màn. */
  donVi: string;
  /** Trả Promise: lỗi thì hộp thoại giữ nguyên và hiện lỗi. */
  onQuyet: (yc: YeuCauHuy, dongY: boolean, ghiChu: string) => Promise<unknown>;
}) {
  const [dangMo, setDangMo] = useState<{ d: XinHuyDong; dongY: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (dong.length === 0) return null;

  const xacNhan = async (ghiChu: string) => {
    if (!dangMo) return;
    setBusy(true);
    setErr(null);
    try {
      await onQuyet(dangMo.d.yc, dangMo.dongY, ghiChu);
      setDangMo(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Không lưu được quyết định. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="xh-hang-doi" aria-label={`Yêu cầu hủy ${donVi} đã duyệt`}>
      <header className="xh-hang-doi__head">
        <div className="xh-hang-doi__head-main">
          <div className="xh-hang-doi__emblem">
            <AlertCircle size={18} className="xh-hang-doi__emblem-icon" />
          </div>
          <div className="xh-hang-doi__title-group">
            <div className="xh-hang-doi__title-row">
              <h4 className="xh-hang-doi__title">
                Xin hủy {donVi} đã duyệt
              </h4>
              <span className="xh-hang-doi__so">{dong.length}</span>
            </div>
            <p className="xh-hang-doi__sub">
              {donVi[0].toUpperCase() + donVi.slice(1)} vẫn hiệu lực tới khi bạn đồng ý hủy.
            </p>
          </div>
        </div>
      </header>
      <ul className="xh-hang-doi__list">
        {dong.map((d) => (
          <li key={d.yc.id} className="xh-dong">
            <div className="xh-dong__main">
              <div className="xh-dong__header-row">
                <span className="xh-dong__ten">{d.ten}</span>
                <span className="xh-dong__don">{d.don}</span>
              </div>
              <div className="xh-dong__reason-card">
                <span className="xh-dong__ly-do">
                  Lý do: {d.yc.ly_do}
                  {d.yc.huy_tu_ngay && (
                    <> · đang nghỉ dở — hủy từ <b>{fmtDate(d.yc.huy_tu_ngay)}</b>, giữ các ngày trước</>
                  )}
                </span>
              </div>
              {d.yc.created_at && (
                <div className="xh-dong__luc">
                  <Clock size={12} className="xh-dong__luc-icon" />
                  <span>Gửi lúc {fmtDateTime(d.yc.created_at)}</span>
                </div>
              )}
            </div>
            <div className="xh-dong__act">
              <button
                type="button"
                className="btn btn--ghost xh-btn-giu"
                onClick={() => { setErr(null); setDangMo({ d, dongY: false }); }}
              >
                Giữ nguyên
              </button>
              <button
                type="button"
                className="btn btn--primary ns-danger xh-btn-huy"
                onClick={() => { setErr(null); setDangMo({ d, dongY: true }); }}
              >
                Đồng ý hủy
              </button>
            </div>
          </li>
        ))}
      </ul>
      <LyDoDialog
        open={dangMo != null}
        title={dangMo?.dongY ? `Đồng ý hủy ${donVi}?` : `Giữ nguyên ${donVi}?`}
        message={
          dangMo
            ? dangMo.dongY
              ? dangMo.d.yc.huy_tu_ngay
                ? `${dangMo.d.ten} · ${dangMo.d.don}. Đơn được rút ngắn: giữ các ngày trước ${fmtDate(dangMo.d.yc.huy_tu_ngay)}, hủy từ ngày đó trở đi.`
                : `${dangMo.d.ten} · ${dangMo.d.don}. ${donVi[0].toUpperCase() + donVi.slice(1)} sẽ bị hủy.`
              : `${dangMo.d.ten} · ${dangMo.d.don}. ${donVi[0].toUpperCase() + donVi.slice(1)} vẫn giữ như đã duyệt.`
            : undefined
        }
        label={dangMo?.dongY ? "Ghi chú" : "Lý do giữ nguyên"}
        placeholder={dangMo?.dongY ? "Không bắt buộc" : "vd: tổ đã xếp người thay, không đổi được"}
        confirmLabel={dangMo?.dongY ? "Đồng ý hủy" : "Giữ nguyên"}
        batBuoc={!dangMo?.dongY}
        danger={!!dangMo?.dongY}
        busy={busy}
        error={err}
        onConfirm={xacNhan}
        onCancel={() => setDangMo(null)}
      />
    </section>
  );
}
