// Dialog "Nhập Excel" — HAI BƯỚC: chọn file → XEM TRƯỚC → "Xác nhận nhập".
//
// Trước 29/08/2026 dialog này ghi thẳng ngay lúc chọn file, dòng lỗi thì bỏ qua và ghi phần còn
// lại. Đổi vì cả file nay là MỘT giao dịch: còn một dòng sai thì backend không ghi gì cả, nên
// không có gì để "ghi thẳng" nữa — người khai phải thấy trước file của mình đụng vào bao nhiêu
// dòng rồi mới quyết. `preview` và `commit` chạy y hệt nhau ở backend (preview rollback ở cuối),
// nên con số ở bước xem trước là con số THẬT chứ không phải ước lượng.
//
// Chuyển từ `pages/danh-muc/` ra đây 10/09/2026: màn Hồ sơ nhân sự dùng chung dialog này. Nơi gọi
// tự đưa hàm `chay` (gọi endpoint của chính màn mình) — dialog không biết gì về đường dẫn API.
import { useState } from "react";
import { Button } from "./Button";
import { DetailModal } from "./DetailModal";
import { ApiError } from "../api/client";
import type { ImportExcelOut } from "../api/rebuildCatalog";
import "./import-excel-dialog.css";

export function ImportExcelDialog({
  ten, chay: chayNgoai, onClose, onImported, taiMau, luat,
}: {
  /** Tên thứ đang nhập, số ít viết thường — vd "công đoạn", "giấy", "hồ sơ nhân sự". */
  ten: string;
  /** Gọi endpoint nhập của màn. `preview` không được ghi gì; `commit` mới chốt. */
  chay: (file: File, mode: "preview" | "commit") => Promise<ImportExcelOut>;
  onClose: () => void;
  /** Đã ghi xong — nơi gọi tải lại bảng rồi mới đóng. */
  onImported: () => void;
  /** Có thì hiện nút "Tải file mẫu" ngay trong dialog (màn nào có endpoint mẫu riêng). */
  taiMau?: () => void | Promise<void>;
  /** Câu mô tả luật nhập của màn — thay dòng mặc định (vốn viết cho danh mục). */
  luat?: string;
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
      const kq = await chayNgoai(f, mode);
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
          <p className="imx__hint">
            {luat ??
              `Bấm "Xuất Excel" cạnh nút này để lấy file đúng định dạng đang chạy (có sẵn dữ liệu
               hiện có; danh mục rỗng thì thành file mẫu), sửa trên chính file đó rồi chọn lại ở
               đây. Mã đã có sẽ CẬP NHẬT — ô để trống ở một cột CÓ trong file sẽ xoá giá trị cột
               đó, còn cột không có trong file thì giữ nguyên. Mã chưa có sẽ TẠO MỚI. Dòng không
               có trong file được giữ nguyên, không bị xoá. Cả file là MỘT lượt: còn một dòng lỗi
               thì không ghi gì cả.`}
          </p>
          {taiMau && (
            <p>
              <Button variant="ghost" onClick={() => void taiMau()} disabled={busy}>
                Tải file mẫu
              </Button>
            </p>
          )}
          <input type="file" accept=".xlsx" disabled={busy}
            onChange={(e) => { chonFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          {busy && <p className="imx__hint">Đang kiểm file…</p>}
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
            <div className="imx__wrap">
              <table className="imx__table">
                <thead>
                  <tr>
                    <th style={{ width: "22%" }}>Sheet</th>
                    <th style={{ width: "10%" }}>Dòng</th>
                    <th style={{ width: "22%" }}>Cột</th>
                    <th>Lý do</th>
                  </tr>
                </thead>
                <tbody>
                  {kq.loi.map((l, i) => (
                    <tr key={i}>
                      <td>{l.sheet}</td>
                      <td className="imx__num">{l.dong}</td>
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
