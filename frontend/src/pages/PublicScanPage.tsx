// Trang TRA KHO CÔNG KHAI — mở khi quét tem QR dán kệ (`#s=<token>`), KHÔNG cần đăng nhập.
// Đứng RIÊNG (ngoài AppShell): brand bar + thẻ tóm tắt vật tư + 2 bảng (theo vị trí · chi tiết lô).
// Chỉ đọc dữ liệu công khai từ /api/public/kho-scan (đã bỏ mọi trường tiền ở backend).
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type PublicScan, type PublicScanLot } from "../api/client";
import { fmtDateISO } from "../utils/format";
import { fmtQty } from "./khoShared";
import "./public-scan.css";

/** Còn ≤ 30 ngày tới HSD (kể cả đã quá hạn) → cảnh báo amber. */
const HSD_WARN_DAYS = 30;

type BinStatus = "du" | "sap_het" | "het";
const STATUS_META: Record<BinStatus, { label: string }> = {
  du: { label: "Bình thường" },
  sap_het: { label: "Sắp hết hạn" },
  het: { label: "Hết hàng" },
};

interface Bin {
  key: string;
  totalRemain: number;
  activeLots: number;
  minHsd: string | null;
  status: BinStatus;
}

/** Số ngày từ hôm nay tới HSD (âm = đã quá hạn); null nếu không có/không parse được. */
function daysToHsd(hsd: string | null): number | null {
  if (!hsd) return null;
  const d = new Date(hsd);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  const day = 86400000;
  return Math.round(
    (Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) -
      Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) /
      day,
  );
}

/** So chuỗi ISO (yyyy-mm-dd) tăng dần; null xuống cuối khi nullLast. */
function cmpIso(a: string | null, b: string | null, nullLast: boolean): number {
  if (a === b) return 0;
  if (a == null) return nullLast ? 1 : -1;
  if (b == null) return nullLast ? -1 : 1;
  return a < b ? -1 : 1;
}

/** Đọc token QR đã ký từ URL (`#s=<payload>.<sig>`). Trả null nếu không phải link tra kho. */
export function readScanToken(): string | null {
  const hash = window.location.hash;
  if (!hash.startsWith("#")) return null;
  const s = new URLSearchParams(hash.slice(1)).get("s");
  // Token luôn có dạng "<payload>.<chữ ký>" → có dấu chấm; lọc bớt nhầm với hash khác.
  return s && s.includes(".") ? s : null;
}

export function PublicScanPage({ scanToken }: { scanToken: string }) {
  const [data, setData] = useState<PublicScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.public
      .khoScan(scanToken)
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(
            e instanceof ApiError
              ? e.status === 404
                ? "Mã QR không hợp lệ hoặc vật tư không tồn tại."
                : e.message
              : "Không tải được thông tin. Kiểm tra kết nối rồi thử lại.",
          );
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [scanToken]);

  const dvt = data?.dvt ?? "";

  // Gom lô → các ô (theo vị trí): tổng còn, số lô còn>0, HSD gần nhất, trạng thái ô.
  const { bins, lotRows, overall } = useMemo(() => {
    const lots = data?.lots ?? [];
    const groups = new Map<string, PublicScanLot[]>();
    for (const lot of lots) {
      const key = lot.vi_tri && lot.vi_tri.trim() ? lot.vi_tri.trim() : "Chưa gán vị trí";
      const arr = groups.get(key);
      if (arr) arr.push(lot);
      else groups.set(key, [lot]);
    }

    const list: Bin[] = [];
    for (const [key, arr] of groups) {
      const active = arr.filter((l) => l.sl_con_lai > 0);
      const totalRemain = active.reduce((s, l) => s + l.sl_con_lai, 0);
      const hsds = active.map((l) => l.hsd).filter((h): h is string => !!h);
      const minHsd = hsds.length ? hsds.reduce((m, h) => (h < m ? h : m)) : null;
      let status: BinStatus;
      if (totalRemain <= 0) status = "het";
      else if (active.some((l) => l.hsd != null && (daysToHsd(l.hsd) ?? Infinity) <= HSD_WARN_DAYS))
        status = "sap_het";
      else status = "du";
      list.push({ key, totalRemain, activeLots: active.length, minHsd, status });
    }
    // Ô còn hàng lên trước, rồi nhiều SL trước.
    list.sort((a, b) => {
      const av = a.totalRemain > 0 ? 0 : 1;
      const bv = b.totalRemain > 0 ? 0 : 1;
      return av !== bv ? av - bv : b.totalRemain - a.totalRemain;
    });

    // Chi tiết lô — FEFO (HSD gần trước, không HSD xuống cuối); chỉ lô còn hàng.
    const rows = lots
      .filter((l) => l.sl_con_lai > 0)
      .sort((a, b) => {
        const byHsd = cmpIso(a.hsd, b.hsd, true);
        return byHsd !== 0 ? byHsd : cmpIso(a.ngay_nhap, b.ngay_nhap, true);
      });

    const onHand = data?.on_hand ?? 0;
    let ov: BinStatus;
    if (onHand <= 0) ov = "het";
    else if (
      lots.some(
        (l) => l.sl_con_lai > 0 && l.hsd != null && (daysToHsd(l.hsd) ?? Infinity) <= HSD_WARN_DAYS,
      )
    )
      ov = "sap_het";
    else ov = "du";

    return { bins: list, lotRows: rows, overall: ov };
  }, [data]);

  return (
    <div className="pscan">
      <header className="pscan__brand">
        <span className="pscan__brand-mark">SVN</span>
        <span className="pscan__brand-text">Sao Việt Nhật · Tra kho</span>
      </header>

      <main className="pscan__main">
        {loading ? (
          <div className="pscan__card pscan__card--skel">
            <span className="pscan__skel" style={{ width: "55%", height: 24 }} />
            <span className="pscan__skel" style={{ width: "75%" }} />
            <span className="pscan__skel" style={{ width: "40%", height: 32 }} />
          </div>
        ) : error ? (
          <div className="pscan__state pscan__state--error">
            <div className="pscan__state-icon">!</div>
            <p>{error}</p>
          </div>
        ) : data ? (
          <>
            <section className="pscan__card">
              <div className="pscan__titlerow">
                <h1 className="pscan__title">
                  {data.material_name ?? data.material_code ?? "Vật tư"}
                </h1>
                <span className={`pscan__pill pscan__pill--${overall}`}>
                  <span className={`pscan__dot pscan__dot--${overall}`} />
                  {STATUS_META[overall].label}
                </span>
              </div>
              <div className="pscan__meta">
                {data.material_code && (
                  <span>
                    SKU <b>{data.material_code}</b>
                  </span>
                )}
                {dvt && (
                  <span>
                    ĐVT <b>{dvt}</b>
                  </span>
                )}
                {data.kho_ten && (
                  <span>
                    Kho <b>{data.kho_ten}</b>
                  </span>
                )}
              </div>
              <div className="pscan__total">
                <span className="pscan__total-num">{fmtQty(data.on_hand)}</span>
                <span className="pscan__total-lbl">Tổng tồn khả dụng{dvt ? ` (${dvt})` : ""}</span>
              </div>
            </section>

            {lotRows.length === 0 ? (
              <div className="pscan__state">
                <p>Vật tư này hiện chưa có tồn tại kho.</p>
              </div>
            ) : (
              <>
                <section className="pscan__sec">
                  <h2 className="pscan__sec-title">Vị trí trong kho</h2>
                  <div className="pscan__tablewrap">
                    <table className="pscan__table">
                      <thead>
                        <tr>
                          <th>Ô / vị trí</th>
                          <th className="pscan__num">SL còn</th>
                          <th className="pscan__num">Số lô</th>
                          <th>HSD gần nhất</th>
                          <th>Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bins.map((bin) => (
                          <tr key={bin.key}>
                            <td className="pscan__loc">
                              <span className={`pscan__dot pscan__dot--${bin.status}`} />
                              {bin.key}
                            </td>
                            <td className="pscan__num pscan__strong">
                              {fmtQty(bin.totalRemain)}
                              {dvt && <span className="pscan__unit"> {dvt}</span>}
                            </td>
                            <td className="pscan__num">{bin.activeLots}</td>
                            <td>
                              {bin.minHsd ? (
                                <span className="pscan__hsd">{fmtDateISO(bin.minHsd)}</span>
                              ) : (
                                <span className="pscan__muted">—</span>
                              )}
                            </td>
                            <td>
                              <span className={`pscan__pill pscan__pill--${bin.status}`}>
                                {STATUS_META[bin.status].label}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="pscan__sec">
                  <h2 className="pscan__sec-title">Chi tiết lô còn hàng</h2>
                  <div className="pscan__tablewrap">
                    <table className="pscan__table">
                      <thead>
                        <tr>
                          <th>Mã lô</th>
                          <th>Vị trí</th>
                          <th>Ngày nhập</th>
                          <th>HSD</th>
                          <th className="pscan__num">Còn</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lotRows.map((lot, i) => (
                          <tr key={`${lot.ma_lo ?? "lo"}-${i}`}>
                            <td className="pscan__code">{lot.ma_lo ?? "—"}</td>
                            <td>{lot.vi_tri?.trim() || <span className="pscan__muted">—</span>}</td>
                            <td>{fmtDateISO(lot.ngay_nhap)}</td>
                            <td>
                              {lot.hsd ? (
                                fmtDateISO(lot.hsd)
                              ) : (
                                <span className="pscan__muted">—</span>
                              )}
                            </td>
                            <td className="pscan__num pscan__strong">
                              {fmtQty(lot.sl_con_lai)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
          </>
        ) : null}
      </main>

      <footer className="pscan__foot">Sao Việt Nhật ERP — quét tem để tra vị trí lưu kho</footer>
    </div>
  );
}
