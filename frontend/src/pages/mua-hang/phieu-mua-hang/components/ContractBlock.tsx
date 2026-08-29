// Khối HỢP ĐỒNG & CHỨNG TỪ trong drawer chi tiết đơn (tách từ pages/PurchaseRequestsPage.tsx).
import { useRef, useState } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type PurchaseAttachmentRow,
  type PurchaseRequestRow,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { fmtDate, hanTraTuMoc, money } from "../../../../utils/format";
import { ATTACHMENT_IMAGE_TYPES } from "../shared/constants";

/**
 * HỢP ĐỒNG & CHỨNG TỪ — số hợp đồng, cọc dự kiến, ảnh/PDF hợp đồng.
 *
 * Cố ý KHÔNG đẻ danh mục hợp đồng và không đẻ màn mới (Đ3): hợp đồng ở đây là một con số để đối
 * chiếu cộng vài cái ảnh. Tách khỏi form Sửa phiếu vì form đó chỉ mở được với phiếu nháp/bị từ
 * chối, mà hợp đồng thường ký SAU khi phiếu đã duyệt — bắt sửa ở màn nháp là không bao giờ điền
 * được.
 *
 * "Cọc dự kiến" chỉ để NHẮC — nó KHÔNG vào công thức công nợ (tiền cọc THẬT luôn là một phiếu chi
 * loại Đặt cọc; cho số này vào công thức là trừ cọc hai lần). Nhưng nó ĐƯỢC dùng để điền sẵn số
 * tiền khi kế toán lập phiếu Đặt cọc, nên phải khai đúng.
 *
 * CỌC KHOÁ SAU KHI DUYỆT (chủ chốt 06/08/2026): đó là con số người duyệt đã đồng ý; cho sửa sau
 * là đổi số đã ký mà không ai duyệt lại. Số hợp đồng và ảnh thì KHÔNG khoá — hợp đồng ký sau.
 */
export function ContractBlock({
  row,
  canUpdate,
  onChanged,
  onError,
}: {
  row: PurchaseRequestRow;
  canUpdate: boolean;
  onChanged: (next: PurchaseRequestRow) => void;
  onError: (message: string | null) => void;
}) {
  const { token } = useAuth();
  const [soHopDong, setSoHopDong] = useState(row.contract_number ?? "");
  const [ngayChot, setNgayChot] = useState(row.debt_cutoff_date ?? "");
  const [coc, setCoc] = useState(String(row.deposit_expected || ""));
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Input file THẬT bị ẩn; cái người dùng thấy là một nút theo khuôn `.pdot__pick` — cùng nút với
  // hộp Ghi đợt giao ngay dưới. Ô `<input type=file>` trần ("Chọn tệp | Không có tệp nào được
  // chọn") là giao diện mặc định của trình duyệt, lạc hẳn khỏi phần còn lại của hộp thoại.
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Cọc chỉ sửa được khi phiếu còn ở nháp / chờ duyệt / bị từ chối — khớp chốt bên service.
  const cocKhoa = !["draft", "pending_approval", "rejected"].includes(row.status);
  // TRẦN CỌC = tổng dự kiến của đơn (chủ chốt 15/08/2026). Cọc là ứng trước một phần của chính
  // đơn này nên không thể vượt giá trị đơn — mà số khai thừa không nằm yên: nó thành hạn mức
  // lập phiếu chi cọc, tiền ra khỏi két rồi mới có người hỏi.
  // Chặn ở đây chỉ để báo SỚM; luật thật nằm ở `PurchaseService._chan_coc_vuot_tong`.
  const tranCoc = row.total_estimate ?? 0;
  const cocVuot = !cocKhoa && Math.round(Number(coc) || 0) > tranCoc;
  const hopDong = row.attachments.filter((a) => a.kind === "hop_dong");
  const banDau =
    (row.contract_number ?? "") === soHopDong.trim() &&
    (row.debt_cutoff_date ?? "") === ngayChot &&
    (row.deposit_expected || 0) === (Number(coc) || 0);

  async function luu() {
    if (!token || busy || cocVuot) return;
    setBusy(true);
    onError(null);
    try {
      onChanged(
        await api.purchaseRequests.updateContract(token, row.id, {
          contract_number: soHopDong.trim() || null,
          // Chuỗi rỗng phải hoá `null`, không gửi "" — server nhận `date | None`, "" là 422.
          debt_cutoff_date: ngayChot || null,
          // Cọc đã khoá thì gửi lại ĐÚNG số cũ — server chỉ chặn khi số THAY ĐỔI, nhờ vậy sửa
          // riêng số hợp đồng trên đơn đã duyệt vẫn lưu được.
          deposit_expected: cocKhoa
            ? row.deposit_expected
            : Math.max(0, Math.round(Number(coc) || 0)),
        }),
      );
    } catch (err) {
      onError(
        err instanceof ApiError ? err.message : "Không lưu được thông tin hợp đồng.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function tai(list: FileList | null) {
    if (!token || !list?.length) return;
    setUploading(true);
    onError(null);
    try {
      let moi = row;
      for (const file of Array.from(list)) {
        moi = await api.purchaseRequests.uploadAttachment(
          token,
          row.id,
          file,
          "hop_dong",
        );
      }
      onChanged(moi);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Không tải được file lên.");
    } finally {
      setUploading(false);
    }
  }

  async function xoa(attachment: PurchaseAttachmentRow) {
    if (!token) return;
    setUploading(true);
    onError(null);
    try {
      onChanged(
        await api.purchaseRequests.deleteAttachment(token, row.id, attachment.id),
      );
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Không xóa được file.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="pdot">
      <header className="pdot__head">
        <h3>Hợp đồng &amp; chứng từ</h3>
        {canUpdate && (
          // ⚠️ GIỮ `ghost`, ĐỪNG nâng lên `accent`. Nút này nằm CÙNG hộp thoại Chi tiết phiếu với
          // "Ghi đợt giao" (DeliveriesBlock) — luật là TỐI ĐA MỘT nút cam mỗi hộp thoại, và suất
          // cam đó thuộc về "Ghi đợt giao": đó là việc làm gần như mỗi lần hàng về và là đường
          // DUY NHẤT sinh công nợ, còn hợp đồng khai một lần rồi thôi. Hai nút cam cạnh nhau là
          // mắt không biết nhìn đâu.
          // `disabled={banDau}` giữ nguyên: chưa sửa gì thì không có gì để lưu. Thêm `cocVuot`:
          // để bấm được rồi ăn 422 thì người dùng phải đọc toast mới hiểu, trong khi câu giải
          // thích đã nằm ngay dưới ô nhập.
          <Button
            type="button"
            variant="ghost"
            loading={busy}
            disabled={banDau || cocVuot}
            onClick={luu}
          >
            Lưu hợp đồng
          </Button>
        )}
      </header>

      <div className="pdot__contract">
        <label className="purchase__field">
          <span>Số hợp đồng</span>
          <input
            className="input"
            maxLength={64}
            readOnly={!canUpdate}
            value={soHopDong}
            onChange={(e) => setSoHopDong(e.target.value)}
            placeholder="Chưa có hợp đồng"
          />
        </label>
        {/* NGÀY CHỐT CÔNG NỢ — đứng CẠNH số hợp đồng, không đứng cạnh cọc, vì nó cùng loại:
            thứ NCC báo lại SAU khi đơn đã lập. Và như số hợp đồng, nó KHÔNG khoá theo duyệt —
            nó không đổi đồng tiền nào, chỉ đổi HẠN trả, mà hạn thì NCC có quyền báo muộn hoặc
            dời. Khoá lại là ép kế toán canh một cái hạn họ biết là sai.
            KHÔNG đặt ở form TẠO đơn: form đó tách thành N đơn theo NCC mà mỗi NCC báo một mốc
            chốt khác nhau — đúng cái bẫy đã gỡ với "ngày dự kiến nhận hàng". */}
        <label className="purchase__field">
          <span>Ngày chốt công nợ</span>
          <input
            className="input"
            type="date"
            readOnly={!canUpdate}
            value={ngayChot}
            onChange={(e) => setNgayChot(e.target.value)}
          />
          <small className="pdot__hint">
            {ngayChot && (row.supplier_credit_days ?? null) !== null ? (
              <>
                NCC cho nợ <strong>{row.supplier_credit_days} ngày</strong> kể từ mốc này ⇒ hạn
                trả <strong>{hanTraTuMoc(ngayChot, row.supplier_credit_days)}</strong>. Qua ngày đó
                chưa trả mới tính quá hạn.
              </>
            ) : ngayChot ? (
              <>
                NCC <strong>chưa khai số ngày cho nợ</strong> nên chưa suy ra hạn trả được — khai
                ở danh mục Nhà cung cấp.
              </>
            ) : (
              <>
                Mốc NCC chốt sổ cho đơn này. Bỏ trống thì hạn trả tính từ{" "}
                <strong>ngày hoá đơn</strong> của từng đợt như cũ.
              </>
            )}
          </small>
        </label>
        <label className="purchase__field">
          <span>Cọc dự kiến{cocKhoa && " (đã duyệt — khoá)"}</span>
          {/* KHOÁ rồi thì đây không còn là ô nhập — in ra như một con số có dấu chấm ngăn nghìn.
              `type=number` bày "3500000" trần, không ai đọc ra ba triệu rưỡi, mà lại còn giả vờ
              mời gõ trong khi gõ không được. Còn sửa được thì giữ nguyên ô số. */}
          {cocKhoa || !canUpdate ? (
            <span className="input purchase__number-input pdot__readonly-money">
              {money(Number(coc) || 0)}
            </span>
          ) : (
            <input
              className="input purchase__number-input"
              type="number"
              min={0}
              step={1000}
              max={tranCoc || undefined}
              value={coc}
              onChange={(e) => setCoc(e.target.value)}
              placeholder="0"
              aria-invalid={cocVuot || undefined}
            />
          )}
          <small className={`pdot__hint${cocVuot ? " pdot__hint--loi" : ""}`}>
            {cocKhoa ? (
              <>
                Đơn đã duyệt nên cọc khoá — đây là con số người duyệt đã đồng ý.
                Cần đổi thì lùi phiếu về nháp rồi duyệt lại.
              </>
            ) : cocVuot ? (
              <>
                Cọc đang lớn hơn tổng dự kiến của đơn ({money(tranCoc)}). Cọc là ứng
                trước một phần của chính đơn này nên không thể vượt giá trị đơn.
              </>
            ) : (
              <>
                Tối đa {money(tranCoc)} (tổng dự kiến của đơn). Tiền cọc thật là một{" "}
                <strong>phiếu chi Đặt cọc</strong> bên Kế toán — số này{" "}
                <strong>không</strong> vào công nợ, nhưng sẽ được{" "}
                <strong>điền sẵn</strong> khi kế toán lập phiếu cọc.
              </>
            )}
          </small>
        </label>
      </div>

      <div className="pdot__files">
        {hopDong.length === 0 ? (
          <p className="pdot__empty">Chưa đính kèm ảnh/PDF hợp đồng nào.</p>
        ) : (
          <div className="pdot__filegrid">
            {hopDong.map((a) => {
              const href = assetUrl(a.file_url) ?? "#";
              const isImage = ATTACHMENT_IMAGE_TYPES.includes(a.file_type ?? "");
              return (
                <div className="pdot__file" key={a.id}>
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    title={
                      a.uploaded_by_name
                        ? `${a.file_name}\n${a.uploaded_by_name} tải lên ${fmtDate(a.uploaded_at)}`
                        : a.file_name
                    }
                  >
                    {isImage ? (
                      <img
                        className="pdot__thumb"
                        src={href}
                        alt={a.file_name}
                      />
                    ) : (
                      // Ô GIẤY + icon, y như hộp Ghi đợt giao. Trước đây nhồi cả TÊN FILE vào ô
                      // 76px nên nó ra một mẩu chữ cụt ("CÁC LỖI THƯỜNG GẶP K…") đứng lệch cạnh
                      // nút ×; tên đầy đủ vốn đã nằm ở `title` của thẻ <a> bao ngoài.
                      <span className="pdot__thumb pdot__thumb--pdf">
                        <Icon name="fileText" size={22} />
                      </span>
                    )}
                  </a>
                  {canUpdate && (
                    <button
                      type="button"
                      className="pdot__filex"
                      aria-label={`Xóa ${a.file_name}`}
                      disabled={uploading}
                      onClick={() => xoa(a)}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {canUpdate && (
          <>
            <input
              type="file"
              hidden
              multiple
              accept="image/*,application/pdf"
              ref={fileRef}
              onChange={(e) => {
                tai(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="pdot__pick"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              <Icon name="fileText" size={16} />
              {uploading
                ? "Đang tải lên…"
                : hopDong.length > 0
                  ? "Thêm ảnh / PDF hợp đồng"
                  : "Chọn ảnh / PDF hợp đồng"}
            </button>
            <small className="pdot__hint">Ảnh hoặc PDF, tối đa 10 MB mỗi file.</small>
          </>
        )}
      </div>
    </section>
  );
}
