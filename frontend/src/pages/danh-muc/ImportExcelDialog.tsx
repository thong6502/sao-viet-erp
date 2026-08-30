// Dialog "Nhập Excel" — HAI BƯỚC: chọn file → XEM TRƯỚC → "Xác nhận nhập".
//
// Trước 29/08/2026 dialog này ghi thẳng ngay lúc chọn file, dòng lỗi thì bỏ qua và ghi phần còn
// lại. Đổi vì cả file nay là MỘT giao dịch: còn một dòng sai thì backend không ghi gì cả, nên
// không có gì để "ghi thẳng" nữa — người khai phải thấy trước file của mình đụng vào bao nhiêu
// dòng rồi mới quyết. `preview` và `commit` chạy y hệt nhau ở backend (preview rollback ở cuối),
// nên con số ở bước xem trước là con số THẬT chứ không phải ước lượng.
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
  /** Đã ghi xong — nơi gọi tải lại bảng rồi mới đóng. */
  onImported: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [xem, setXem] = useState<ImportExcelOut | null>(null);      // kết quả XEM TRƯỚC
  const [xong, setXong] = useState<ImportExcelOut | null>(null);    // kết quả đã CHỐT

  async function chay(f: File, mode: "preview" | "commit") {
    setBusy(true);
    setError(null);
    try {
      const kq = await crud(prefix).importExcel(token, f, mode);
      if (mode === "commit" && kq.da_ghi) setXong(kq);
      else setXem(kq);
    } catch (err) {
      // 422 = file không đọc được, hoặc workbook của MÀN KHÁC / phiên bản sau. Câu tiếng Việt của
      // backend nói đúng phải làm gì, đừng thay bằng câu chung chung.
      setError(err instanceof ApiError ? err.message : "Không đọc được file.");
    } finally {
      setBusy(false);
    }
  }

  function chonFile(f: File | null) {
    setFile(f);
    setXem(null);
    setXong(null);
    if (f) void chay(f, "preview");
  }

  const kq = xong ?? xem;
  const dungDuoc = Boolean(xem && xem.hop_le && file && !xong);
  const seDoi = kq ? kq.tao_moi + kq.cap_nhat : 0;

  return (
    <DetailModal
      kicker="Nhập Excel"
      title={`Nhập ${ten} từ Excel`}
      onClose={onClose}
      footer={
        xong ? (
          <Button variant="primary" onClick={onImported}>Xong</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={busy}>Huỷ</Button>
            {dungDuoc && (
              <Button variant="primary" disabled={busy}
                onClick={() => { if (file) void chay(file, "commit"); }}>
                {seDoi > 0 ? `Xác nhận nhập ${seDoi} dòng` : "Xác nhận nhập"}
              </Button>
            )}
          </>
        )
      }
    >
      {!xong && (
        <>
          <p className="rc__import-hint">
            Bấm "Xuất Excel" cạnh nút này để lấy file đúng định dạng đang chạy (có sẵn dữ liệu hiện
            có; danh mục rỗng thì thành file mẫu), sửa trên chính file đó rồi chọn lại ở đây. Mã đã
            có sẽ CẬP NHẬT — ô để trống ở một cột CÓ trong file sẽ xoá giá trị cột đó, còn cột không
            có trong file thì giữ nguyên. Mã chưa có sẽ TẠO MỚI. Dòng không có trong file được giữ
            nguyên, không bị xoá. Cả file là MỘT lượt: còn một dòng lỗi thì không ghi gì cả.
          </p>
          <input type="file" accept=".xlsx" disabled={busy}
            onChange={(e) => { chonFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          {busy && <p className="rc__import-hint">Đang kiểm file…</p>}
        </>
      )}

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {kq && (
        <>
          <div
            className={`banner ${!kq.hop_le ? "banner--error" : xong ? "banner--success" : "banner--warn"}`}
            role="status"
          >
            {xong
              ? `Đã nhập xong: ${kq.tao_moi} dòng tạo mới, ${kq.cap_nhat} dòng cập nhật`
                + (kq.khong_doi > 0 ? `, ${kq.khong_doi} dòng không đổi.` : ".")
              : !kq.hop_le
                ? `File có ${kq.loi.length} chỗ chưa hợp lệ — sửa trong file rồi chọn lại. `
                  + "Chưa có dòng nào được ghi."
                : `Đọc được ${kq.tong_dong} dòng: ${kq.tao_moi} tạo mới, ${kq.cap_nhat} cập nhật`
                  + (kq.khong_doi > 0 ? `, ${kq.khong_doi} không đổi.` : ".")}
          </div>

          {kq.loi.length > 0 && (
            <div className="rc__tablewrap" style={{ maxHeight: "40vh" }}>
              <table className="rc__table">
                <thead>
                  <tr>
                    <th style={{ width: "26%" }}>Sheet</th>
                    <th style={{ width: "12%" }}>Dòng</th>
                    <th style={{ width: "24%" }}>Cột</th>
                    <th>Lý do</th>
                  </tr>
                </thead>
                <tbody>
                  {kq.loi.map((l, i) => (
                    <tr key={i}>
                      <td>{l.sheet}</td>
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
