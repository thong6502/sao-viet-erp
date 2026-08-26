// Dialog "Nhập Excel" (mục 1 "Bảng định mức") — TẠO MỚI trực tiếp từng dòng ngay khi chọn file,
// KHÔNG có bước xem trước như luồng CSV của KhachHangPage: backend `POST {prefix}/import-excel`
// đã kiểm + ghi trong CÙNG một lượt gọi, dòng lỗi không chặn các dòng khác.
import { useState } from "react";
import { Button } from "../../components/Button";
import { DetailModal } from "../../components/DetailModal";
import { ApiError } from "../../api/client";
import { crud, type ImportExcelOut } from "../../api/rebuildCatalog";

export function ImportExcelDialog({
  prefix, ten, token, onClose, onImported,
}: {
  prefix: string;
  /** Tên danh mục số ít, viết thường — vd "công đoạn", "giấy". */
  ten: string;
  token: string;
  onClose: () => void;
  /** Đã có dòng tạo thành công (kể cả khi vẫn còn lỗi) — nơi gọi tải lại bảng rồi mới đóng. */
  onImported: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportExcelOut | null>(null);

  async function chonFile(f: File | null) {
    if (!f || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await crud(prefix).importExcel(token, f));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đọc được file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <DetailModal
      kicker="Nhập Excel"
      title={`Nhập ${ten} từ Excel`}
      onClose={onClose}
      footer={
        result ? (
          <Button variant="primary" onClick={onImported}>Xong</Button>
        ) : (
          <Button variant="ghost" onClick={onClose} disabled={busy}>Huỷ</Button>
        )
      }
    >
      {!result && (
        <>
          <p className="rc__import-hint">
            Tải file mẫu ở nút "Tải mẫu" cạnh nút này, điền theo đúng cột tiêu đề rồi chọn lại file
            đó ở đây. Chỉ TẠO MỚI — mã đã có trong danh mục sẽ báo lỗi đúng dòng đó, các dòng còn
            lại vẫn được tạo bình thường.
          </p>
          <input type="file" accept=".xlsx" disabled={busy}
            onChange={(e) => { void chonFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          {busy && <p className="rc__import-hint">Đang nhập…</p>}
        </>
      )}

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {result && (
        <>
          <div className={`banner ${result.loi.length > 0 ? "banner--warn" : "banner--success"}`} role="status">
            {`Đã tạo ${result.thanh_cong}/${result.tong_dong} dòng`
              + (result.loi.length > 0 ? `, ${result.loi.length} dòng lỗi bị bỏ qua.` : ".")}
          </div>
          {result.loi.length > 0 && (
            <div className="rc__tablewrap" style={{ maxHeight: "40vh" }}>
              <table className="rc__table">
                <thead>
                  <tr><th style={{ width: "18%" }}>Dòng</th><th style={{ width: "28%" }}>Cột</th><th>Lý do</th></tr>
                </thead>
                <tbody>
                  {result.loi.map((l, i) => (
                    <tr key={i}>
                      <td className="rc__mono rc__nowrap">{l.dong}</td>
                      <td>{l.cot}</td>
                      <td>{l.ly_do}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </DetailModal>
  );
}
