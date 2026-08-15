// Trang TRA KHO CÔNG KHAI — mở khi quét tem QR dán kệ (`#s=<token>`), KHÔNG cần đăng nhập.
// Đứng RIÊNG (ngoài AppShell): brand bar + thẻ tóm tắt vật tư + 2 bảng (theo vị trí · lịch sử nhập/xuất).
// Chỉ đọc dữ liệu công khai từ /api/public/kho-scan (đã bỏ mọi trường tiền ở backend).
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, assetUrl, type PublicScan, type PublicScanLot } from "../api/client";
import { fmtDateISO } from "../utils/format";
import { fmtQty } from "./khoShared";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./public-scan.css";

// Trạng thái ô/tổng CHỈ dựa vào TỒN: còn hàng = "Bình thường", hết = "Hết hàng".
// (Đã bỏ cảnh báo HSD — kho giấy không quản hạn dùng.)
type BinStatus = "du" | "het";
const STATUS_META: Record<BinStatus, { label: string }> = {
  du: { label: "Bình thường" },
  het: { label: "Hết hàng" },
};

interface Bin {
  key: string;
  totalRemain: number;
  activeLots: number;
  status: BinStatus;
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
  // Bấm ảnh vật tư → xem ảnh FULL (lightbox). Bấm nền/nút ✕ để đóng.
  const [zoom, setZoom] = useState(false);

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
  const { bins, overall } = useMemo(() => {
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
      list.push({
        key,
        totalRemain,
        activeLots: active.length,
        status: totalRemain <= 0 ? "het" : "du",
      });
    }
    // Ô còn hàng lên trước, rồi nhiều SL trước.
    list.sort((a, b) => {
      const av = a.totalRemain > 0 ? 0 : 1;
      const bv = b.totalRemain > 0 ? 0 : 1;
      return av !== bv ? av - bv : b.totalRemain - a.totalRemain;
    });

    const onHand = data?.on_hand ?? 0;
    const overall: BinStatus = onHand <= 0 ? "het" : "du";
    return { bins: list, overall };
  }, [data]);

  const history = data?.history ?? [];

  return (
    <div className="pscan">
      <header className="pscan__brand">
        <img className="pscan__brand-logo" src={logoUrl} alt="" width={30} height={30} />
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
              <div className="pscan__head">
                {data.anh_url && (
                  <button
                    type="button"
                    className="pscan__photobtn"
                    onClick={() => setZoom(true)}
                    aria-label="Xem ảnh phóng to"
                    title="Bấm để xem ảnh lớn"
                  >
                    <img
                      className="pscan__photo"
                      src={assetUrl(data.anh_url) ?? undefined}
                      alt={data.material_name ?? "Ảnh vật tư"}
                    />
                  </button>
                )}
                <div className="pscan__headmain">
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
                </div>
              </div>
              <div className="pscan__total">
                <span className="pscan__total-num">{fmtQty(data.on_hand)}</span>
                <span className="pscan__total-lbl">Tổng tồn khả dụng{dvt ? ` (${dvt})` : ""}</span>
              </div>
            </section>

            {bins.length === 0 && history.length === 0 ? (
              <div className="pscan__state">
                <p>Vật tư này hiện chưa có tồn và chưa có phát sinh nhập/xuất tại kho.</p>
              </div>
            ) : (
              <>
                {bins.length > 0 && (
                  <section className="pscan__sec">
                    <h2 className="pscan__sec-title">Vị trí trong kho</h2>
                    <div className="pscan__tablewrap">
                      <table className="pscan__table">
                        <thead>
                          <tr>
                            <th>Ô / vị trí</th>
                            <th className="pscan__num">SL còn</th>
                            <th className="pscan__num">Số đợt nhập</th>
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
                )}

                {history.length > 0 && (
                  <section className="pscan__sec">
                    <h2 className="pscan__sec-title">Lịch sử nhập / xuất gần đây</h2>
                    <div className="pscan__tablewrap">
                      <table className="pscan__table">
                        <thead>
                          <tr>
                            <th>Loại</th>
                            <th>Ngày</th>
                            <th>Số chứng từ</th>
                            <th className="pscan__num">Số lượng</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history.map((mv, i) => {
                            const isNhap = mv.loai === "NHAP";
                            return (
                              <tr key={`${mv.so_ct}-${i}`}>
                                <td>
                                  <span
                                    className={`pscan__pill pscan__pill--${isNhap ? "nhap" : "xuat"}`}
                                  >
                                    {isNhap ? "Nhập" : "Xuất"}
                                  </span>
                                </td>
                                <td>
                                  {mv.ngay ? (
                                    fmtDateISO(mv.ngay)
                                  ) : (
                                    <span className="pscan__muted">—</span>
                                  )}
                                </td>
                                <td className="pscan__code">{mv.so_ct || "—"}</td>
                                <td className="pscan__num pscan__strong">
                                  {isNhap ? "+" : "−"}
                                  {fmtQty(mv.so_luong)}
                                  {dvt && <span className="pscan__unit"> {dvt}</span>}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </>
            )}
          </>
        ) : null}
      </main>

      <footer className="pscan__foot">Sao Việt Nhật ERP · Dữ liệu tồn kho tại thời điểm tra cứu</footer>

      {zoom && data?.anh_url && (
        <div
          className="pscan__lightbox"
          role="dialog"
          aria-modal="true"
          onClick={() => setZoom(false)}
        >
          <button
            type="button"
            className="pscan__lightbox-x"
            onClick={() => setZoom(false)}
            aria-label="Đóng"
          >
            ✕
          </button>
          <img
            src={assetUrl(data.anh_url) ?? undefined}
            alt={data.material_name ?? "Ảnh vật tư"}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
