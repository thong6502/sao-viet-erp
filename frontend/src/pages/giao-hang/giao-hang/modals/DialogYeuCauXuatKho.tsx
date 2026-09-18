// Hộp thoại YÊU CẦU XUẤT KHO cho một chuyến (tách từ pages/GiaoHangPage.tsx).
import { useEffect, useState } from "react";
import type { DeliveryTrip, HangCanXuat } from "../../../../api/client";
import { api } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { nhanDonVi } from "../../../lsxBuoc";
import { useNapTenDonVi } from "../../../tenDonVi";

// =============================================================================
// Dialog · Gửi yêu cầu xuất kho
// =============================================================================
export function DialogYeuCauXuatKho({
  trip,
  token,
  onClose,
  onXong,
}: {
  trip: DeliveryTrip;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  // `dvt` của dòng yêu cầu giao là MÃ danh mục (`don_vi_gia` của mặt hàng) — bày mã ra cho thủ kho
  // đọc là bắt họ tra mã. Nạp bảng tên rồi tra bằng `nhanDonVi`.
  useNapTenDonVi();
  const [hang, setHang] = useState<HangCanXuat[] | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [dangGui, setDangGui] = useState(false);

  // Dòng hàng do MÁY suy ra từ yêu cầu giao — người gửi không gõ, không sửa. Yêu cầu đã nói giao
  // cái gì bao nhiêu; cho gõ lại là mở đường cho lệch số và kho xuất nhầm hàng.
  useEffect(() => {
    api.giaoHang
      .hangCanXuat(token, trip.id)
      .then(setHang)
      .catch((e: unknown) => {
        setHang([]);
        setLoi(e instanceof Error ? e.message : "Không đọc được hàng cần xuất");
      });
  }, [token, trip.id]);

  const gui = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      // KHÔNG gửi `kho_id` (chủ 21/08/2026): người gửi không biết hàng nằm kho nào, thủ kho
      // mới biết. Màn Hộp yêu cầu bên kho vốn đã tự chọn được khi yêu cầu bỏ trống.
      .guiYeuCauXuatKho(token, trip.id, { ghi_chu: ghiChu || null })
      .then(onXong)
      .catch((e: unknown) =>
        setLoi(e instanceof Error ? e.message : "Không gửi được yêu cầu xuất kho"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Yêu cầu xuất kho · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body gh-form">
          <div className="gh-card" style={{ background: "#f8fafc", margin: 0 }}>
            <p className="rc__sub" style={{ margin: 0 }}>
              Đây là <strong>yêu cầu xuất kho bình thường</strong> — kho lập phiếu và ghi sổ như mọi
              phiếu vật tư khác. Hàng lấy thẳng từ yêu cầu giao, <strong>không sửa được</strong>.
              {" "}<strong>Xuất từ kho nào do thủ kho chọn</strong> lúc lập phiếu.
            </p>
          </div>

          {/* CHỈ XEM */}
          <div className="kho-lines__wrap" style={{ border: "1px solid #e2e8f0", borderRadius: "8px", overflow: "hidden" }}>
            <table className="kho-lines">
              <thead className="kho-lines__head">
                <tr>
                  <th style={{ width: 36 }}>STT</th>
                  <th>Mặt hàng</th>
                  <th style={{ width: 90 }}>ĐVT</th>
                  <th className="kho-num" style={{ width: 110 }}>Số lượng</th>
                </tr>
              </thead>
              <tbody>
                {hang === null && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center", padding: "20px", color: "#64748b" }}>Đang tải…</td>
                  </tr>
                )}
                {hang?.map((d, i) => (
                  <tr key={`${d.hang_loai}-${d.hang_id}`}>
                    <td className="kho-lines__code">{i + 1}</td>
                    <td>
                      <div className="kho-lines__name kho-name-clamp" title={d.hang_ten ?? ""} style={{ fontWeight: 500 }}>
                        {d.hang_ten ?? `${d.hang_loai}#${d.hang_id}`}
                      </div>
                    </td>
                    <td className="kho-lines__code">{nhanDonVi(d.dvt)}</td>
                    <td className="kho-num" style={{ fontWeight: 600 }}>{d.sl_de_nghi}</td>
                  </tr>
                ))}
                {hang?.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center", padding: "20px", color: "#64748b" }}>Không có hàng nào phải xuất.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <label>
            Ghi chú cho kho
            <input className="input" value={ghiChu} placeholder="Ghi chú thêm cho thủ kho..." onChange={(e) => setGhiChu(e.target.value)} />
          </label>

          {loi && (
            <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
              {loi}
            </div>
          )}

          <Button
            variant="accent"
            disabled={!hang || hang.length === 0 || dangGui}
            onClick={gui}
          >
            Gửi yêu cầu xuất kho
          </Button>
        </div>
      </aside>
    </div>
  );
}
