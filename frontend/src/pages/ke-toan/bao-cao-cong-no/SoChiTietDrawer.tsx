// SỔ CHI TIẾT CÔNG NỢ của MỘT đối tượng — PRD §5.1, mở khi bấm một dòng ở sổ tổng hợp.
//
// Vì sao phải có màn này: sổ tổng hợp nói "PS Nợ 304.500.000" nhưng KHÔNG nói gồm phiếu nào. Tab
// "Chi tiết đơn & đợt" cũng không trả lời được — nó chỉ liệt kê ĐỢT GIAO (bên Có), còn tiền đã
// trả bị nén thành một con số. Chủ chốt 05/09/2026: *"chưa có nợ (là các phiếu đã chi)"*.
//
// Bố cục theo đúng sổ kế toán: SỐ DƯ ĐẦU KỲ → từng chứng từ xếp theo ngày → SỐ DƯ CUỐI KỲ. Cột
// "Luỹ kế" chạy dồn nên đọc tới dòng nào cũng biết lúc đó còn nợ bao nhiêu — và dòng cuối bắt
// buộc bằng ô "Dư cuối kỳ" của chính đối tượng đó bên sổ tổng hợp (server đọc chung một luồng
// chứng từ, có test đối chiếu canh).
//
// CHỈ ĐỌC nên đóng thoải mái: bấm nền mờ hoặc Esc đều được — khác các form tiền, đóng nhầm không
// mất gì.
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type SoChiTietCongNo } from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import type { NavigateFn } from "../../../components/AppShell";
import { Icon } from "../../../components/Icons";
import { fmtDate } from "../../../utils/format";

/** Nhãn tiếng Việt cho từng loại chứng từ. Server trả khoá máy, giao diện đặt tên. */
const NHAN_LOAI: Record<string, string> = {
  hoa_don: "Hoá đơn bán",
  phieu_thu: "Phiếu thu",
  dot_giao: "Hàng đã nhận",
  phieu_chi: "Phiếu chi",
  hoan_tien: "NCC hoàn tiền",
};

/** Mỗi trang bao nhiêu chứng từ. Cùng cỡ với danh sách "đã trả" ở drawer Công nợ phải trả. */
const MOI_TRANG = 20;

/** `HH:mm` của mốc ghi nhận. Rỗng khi chứng từ cũ chưa có mốc — KHÔNG bịa ra "00:00", vì 00:00 là
 *  một giờ có thật, người đọc sẽ tưởng chứng từ được ghi lúc nửa đêm. */
function gioPhut(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function So({ v, manh = false }: { v: number; manh?: boolean }) {
  if (!v) return <span className="bccn__khong">—</span>;
  return (
    <span className={manh ? "bccn__tien bccn__tien--manh" : "bccn__tien"}>
      {Math.round(v).toLocaleString("vi-VN")}
    </span>
  );
}

export function SoChiTietDrawer({
  ben,
  doiTuongId,
  tenLui,
  tuNgay,
  denNgay,
  onClose,
  navigate: _navigate,
}: {
  ben: "receivables" | "payables";
  /** `null` = dòng gom "ngoài danh mục" — KHÔNG phải "lấy tất cả". */
  doiTuongId: number | null;
  /** Tên lấy sẵn từ dòng vừa bấm, để hiện ngay lúc còn đang tải. */
  tenLui: string;
  tuNgay: string;
  denNgay: string;
  onClose: () => void;
  navigate?: NavigateFn;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<SoChiTietCongNo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trang, setTrang] = useState(1);

  // Sắp xếp chứng từ phát sinh: MỚI NHẤT LÊN ĐẦU (chủ chốt chọn Cách 1: Đầu kỳ → Phát sinh mới đến cũ → Cuối kỳ).
  // Bố cục hiển thị: SỐ DƯ ĐẦU KỲ → PHÁT SINH TRONG KỲ (mới → cũ) → SỐ DƯ CUỐI KỲ.
  // Cả hai mốc dư đầu kỳ và cuối kỳ luôn cố định ở mọi trang; phân trang chỉ áp dụng cho
  // các dòng chứng từ con trong khối phát sinh.
  const dongHien = useMemo(() => [...(data?.dong ?? [])].reverse(), [data]);
  const soTrang = Math.max(1, Math.ceil(dongHien.length / MOI_TRANG));
  const trangAnToan = Math.min(trang, soTrang);
  const dongTrang = useMemo(
    () => dongHien.slice((trangAnToan - 1) * MOI_TRANG, trangAnToan * MOI_TRANG),
    [dongHien, trangAnToan]
  );

  useEffect(() => {
    if (!token) return;
    let huy = false;
    setLoading(true);
    setError(null);
    api.accounting
      .soChiTietCongNo(token, ben, { doiTuongId, tuNgay, denNgay })
      .then((d) => {
        if (!huy) setData(d);
      })
      .catch((err) => {
        if (huy) return;
        setData(null);
        setError(err instanceof ApiError ? err.message : "Không tải được sổ chi tiết.");
      })
      .finally(() => {
        if (!huy) setLoading(false);
      });
    return () => {
      huy = true;
    };
  }, [token, ben, doiTuongId, tuNgay, denNgay]);

  useEffect(() => {
    setTrang(1);
  }, [ben, doiTuongId, tuNgay, denNgay]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="rc-drawer__scrim" onClick={onClose}>
      <aside
        className="rc-drawer acct-drawer-wide"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Sổ chi tiết công nợ — ${data?.ten ?? tenLui}`}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">
                {data?.tieu_de ?? "Sổ chi tiết công nợ"}
              </span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{data?.ten ?? tenLui}</h2>
                {/* Tạm thời comment nút điều hướng sang màn công nợ:
                {navigate && doiTuongId != null && (
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    style={{ marginLeft: "12px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                    onClick={() => {
                      onClose();
                      navigate(ben === "payables" ? "ke-toan-cong-no" : "ke-toan-cong-no-phai-thu");
                    }}
                    title={
                      ben === "payables"
                        ? "Mở màn Công nợ phải trả để xem chi tiết đợt giao và lập phiếu chi"
                        : "Mở màn Công nợ phải thu để xem chi tiết hoá đơn và thu tiền"
                    }
                  >
                    <Icon name="externalLink" size={13} />
                    <span>{ben === "payables" ? "Xem đợt nợ & thanh toán" : "Xem HĐ nợ & thu tiền"}</span>
                  </button>
                )}
                */}
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={onClose}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>TK {data?.tk ?? (ben === "payables" ? "331" : "131")}</span>
            {data?.ma && (
              <>
                <span className="purchase__hero-dot">•</span>
                <span>Mã {data.ma}</span>
              </>
            )}
            <span className="purchase__hero-dot">•</span>
            <span>
              {fmtDate(tuNgay)} – {fmtDate(denNgay)}
            </span>
          </div>
        </div>

        <div className="rc-drawer__body">
          {error && (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          )}
          {loading && <p className="md-page__muted">Đang tải…</p>}

          {!loading && data && (
            <>
              <table className="pay-table bccn__soct">
                <thead>
                  <tr>
                    <th>Ngày · giờ</th>
                    <th>Chứng từ</th>
                    <th className="pay-num">Nợ</th>
                    <th className="pay-num">Có</th>
                    <th className="pay-num">Luỹ kế</th>
                  </tr>
                </thead>
                <tbody>
                  {/* 1) SỐ DƯ ĐẦU KỲ: Cố định ở đầu bảng tại MỌI trang */}
                  <tr className="bccn__soct-moc">
                    <td colSpan={2}>
                      Số dư đầu kỳ <small>trước {fmtDate(tuNgay)}</small>
                    </td>
                    <td className="pay-num"><So v={data.dau_no} manh /></td>
                    <td className="pay-num"><So v={data.dau_co} manh /></td>
                    <td className="pay-num">
                      <So v={data.dau_no || data.dau_co} manh />
                      {(data.dau_no || data.dau_co) > 0 && (
                        <small className="bccn__soct-ben">{data.dau_no ? "Nợ" : "Có"}</small>
                      )}
                    </td>
                  </tr>

                  {/* 2) PHÁT SINH TRONG KỲ: Cố định ở MỌI trang, phân trang mini gắn trực tiếp ở cột Luỹ kế */}
                  <tr className="bccn__soct-khoi">
                    <td colSpan={2}>
                      Phát sinh trong kỳ <small>{dongHien.length} chứng từ</small>
                    </td>
                    <td className="pay-num"><So v={data.ps_no} manh /></td>
                    <td className="pay-num"><So v={data.ps_co} manh /></td>
                    <td className="bccn__soct-pt-cell">
                      {soTrang > 1 && (
                        <div className="bccn__soct-mini-pt" aria-label="Phân trang chứng từ">
                          <button
                            type="button"
                            className="bccn__soct-mini-btn"
                            disabled={trangAnToan <= 1}
                            onClick={() => setTrang((t) => Math.max(1, t - 1))}
                            title="Trang trước"
                            aria-label="Trang trước"
                          >
                            ‹
                          </button>
                          <span className="bccn__soct-mini-text">
                            Trang <b>{trangAnToan}</b>/{soTrang}
                          </span>
                          <button
                            type="button"
                            className="bccn__soct-mini-btn"
                            disabled={trangAnToan >= soTrang}
                            onClick={() => setTrang((t) => Math.min(soTrang, t + 1))}
                            title="Trang sau"
                            aria-label="Trang sau"
                          >
                            ›
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>

                  {dongHien.length === 0 && (
                    <tr>
                      <td colSpan={5} className="bccn__trong">
                        Kỳ này không có chứng từ nào của đối tượng này.
                      </td>
                    </tr>
                  )}

                  {dongTrang.map((d, i) => (
                    <tr key={`${d.ngay}-${d.so_ct}-${i}`}>
                      <td>
                        {fmtDate(d.ngay)}
                        {gioPhut(d.luc) && (
                          <small className="bccn__soct-gio">{gioPhut(d.luc)}</small>
                        )}
                      </td>
                      <td>
                        <div className="bccn__soct-ct-dau">
                          <span className="bccn__soct-loai">
                            {NHAN_LOAI[d.loai] ?? d.loai}
                          </span>
                          <span className="bccn__soct-ct">{d.so_ct}</span>
                        </div>
                        {/* Diễn giải cắt một dòng + `title` giữ nguyên văn: nội dung phiếu do
                            người dùng gõ, dài ngắn tuỳ hứng, để nó xuống dòng tự do là bảng vỡ. */}
                        {d.dien_giai && d.dien_giai !== (NHAN_LOAI[d.loai] ?? "") && (
                          <div className="bccn__soct-dg" title={d.dien_giai}>
                            {d.dien_giai}
                          </div>
                        )}
                      </td>
                      <td className="pay-num"><So v={d.no} /></td>
                      <td className="pay-num"><So v={d.co} /></td>
                      <td className="pay-num">
                        <So v={d.luy_ke_no || d.luy_ke_co} />
                        {(d.luy_ke_no || d.luy_ke_co) > 0 && (
                          <small className="bccn__soct-ben">
                            {d.luy_ke_no ? "Nợ" : "Có"}
                          </small>
                        )}
                      </td>
                    </tr>
                  ))}

                  {/* 3) SỐ DƯ CUỐI KỲ: Cố định ở cuối bảng tại MỌI trang */}
                  <tr className="bccn__soct-moc">
                    <td colSpan={2}>
                      Số dư cuối kỳ <small>{fmtDate(denNgay)}</small>
                    </td>
                    <td className="pay-num"><So v={data.cuoi_no} manh /></td>
                    <td className="pay-num"><So v={data.cuoi_co} manh /></td>
                    <td className="pay-num">
                      <So v={data.cuoi_no || data.cuoi_co} manh />
                      {(data.cuoi_no || data.cuoi_co) > 0 && (
                        <small className="bccn__soct-ben">{data.cuoi_no ? "Nợ" : "Có"}</small>
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>

              <p className="bccn__soct-foot">
                <Icon name="fileText" size={13} />{" "}
                Cần file lưu trữ? Dùng nút{" "}
                <strong>Xuất Excel</strong> ở sổ tổng hợp — sổ chi
                tiết này để tra tại chỗ khi ngồi đối chiếu.
              </p>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
