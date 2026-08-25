// Hộp ĐÍNH KÈM của một chuyến — ảnh/PDF minh chứng (tách từ pages/GiaoHangPage.tsx).
import { useCallback, useEffect, useState } from "react";
import type { DinhKemChuyen } from "../../../../api/client";
import { api, assetUrl } from "../../../../api/client";
import { fmtDateTime } from "../../../../utils/format";

// =============================================================================
// Drawer · Chi tiết yêu cầu
// =============================================================================
/** File minh chứng của chuyến — ảnh/PDF.
 *
 * Việc thật: hàng đi kèm hoá đơn. Trước lúc đi đính hoá đơn cho tài xế cầm theo, giao xong chụp
 * lại tờ khách đã ký. KHÔNG chia "hoá đơn đi" với "biên nhận về": chia ra là bắt người dùng chọn
 * loại trước khi tải, chọn sai thì phải xoá tải lại. */
export function DinhKemChuyenBox({ tripId, token }: { tripId: number; token: string | null }) {
  const [ds, setDs] = useState<DinhKemChuyen[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const nap = useCallback(() => {
    if (!token) return;
    api.giaoHang.dinhKemChuyen(token, tripId)
      .then((r) => setDs(r.items))
      .catch(() => setDs([]));
  }, [token, tripId]);
  useEffect(nap, [nap]);

  async function them(f: File | null) {
    if (!token || !f) return;
    setDangTai(true);
    setLoi(null);
    try {
      await api.giaoHang.themDinhKemChuyen(token, tripId, f);
      nap();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tải lên được.");
    } finally {
      setDangTai(false);
    }
  }

  async function xoa(id: number) {
    if (!token) return;
    try {
      await api.giaoHang.xoaDinhKemChuyen(token, tripId, id);
      nap();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xoá được.");
    }
  }

  return (
    <div className="gh-dinhkem">
      <div className="gh-dinhkem__head">
        <strong>Hoá đơn / minh chứng</strong>
        <label className="btn btn--secondary gh-dinhkem__add">
          {dangTai ? "Đang tải…" : "Thêm file"}
          <input type="file" accept="image/*,application/pdf" hidden disabled={dangTai}
                 onChange={(e) => { void them(e.target.files?.[0] ?? null); e.target.value = ""; }} />
        </label>
      </div>
      <p className="rc__sub">Ảnh hoặc PDF, tối đa 10 MB mỗi file.</p>
      {loi && <div className="banner banner--error" role="alert">{loi}</div>}
      {ds.length === 0 && <p className="rc__sub">Chưa có file nào.</p>}
      {ds.map((f) => (
        <div key={f.id} className="gh-line">
          {/* PHẢI qua `assetUrl`: `file_url` là đường TƯƠNG ĐỐI (`/api/files/...`), mà giao diện
              chạy khác cổng với API — để nguyên là trình duyệt tìm file ở cổng của giao diện rồi
              báo không thấy. `assetUrl` ghép đúng gốc API; cookie đọc file trình duyệt tự gửi. */}
          <a href={assetUrl(f.file_url) ?? "#"} target="_blank" rel="noreferrer">{f.file_name}</a>
          <span>{fmtDateTime(f.uploaded_at)}</span>
          <button type="button" className="dhb__invoice-cancel" onClick={() => void xoa(f.id)}>
            Xoá
          </button>
        </div>
      ))}
    </div>
  );
}
