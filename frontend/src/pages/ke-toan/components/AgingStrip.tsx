// DẢI PHÂN TUỔI NỢ — dùng chung cho Công nợ phải trả và Công nợ phải thu.
//
// Server đã gom rổ từ lâu (`AGING_BUCKETS` ở accounting_service.py) và trả về qua `summary.aging`,
// nhưng tới 29/08/2026 chưa màn nào VẼ nó ra — cả hai màn chỉ hiện một ô "Quá hạn" gộp tất, nên
// khoản trễ 3 ngày và khoản trễ 90 ngày nằm chung, nhìn vào không biết đòi/trả cái nào trước.
//
// MỘT component cho HAI màn, không chép đôi: hai bảng công nợ là cặp song sinh, để chúng vẽ rổ
// theo hai kiểu là người dùng phải học lại cách đọc khi đổi màn.
//
// Bấm một rổ = LỌC danh sách theo rổ đó. Bộ lọc chạy trên danh sách đã dựng, SAU khi thẻ tổng đã
// chốt — nên mấy con số ở dải này và ở KPI đầu màn KHÔNG nhảy theo lúc bấm. Đó là chủ ý: dải rổ
// là bức tranh toàn cảnh, bấm vào chỉ để soi, không phải để đổi bức tranh.
import type { AgingBucket } from "../../../api/client";
import { money } from "../../../utils/format";

/** Rổ "chưa tới hạn" gom cả khoản CHƯA tới hạn lẫn khoản KHÔNG CÓ HẠN (chưa khai số ngày nợ) —
 *  khớp đúng `AGING_CHUA_TOI_HAN` bên server. Nó KHÔNG phải nợ xấu nên không tô cảnh báo. */
export const CHUA_TOI_HAN = "chua_toi_han";
/** Từ 31 ngày trở lên coi là NẶNG — cùng ngưỡng `AGING_DANGER` mà pill từng dòng đang dùng. */
const NANG = new Set(["d31_60", "d60_plus"]);

export function AgingStrip({
  buckets,
  dangChon,
  onChon,
}: {
  buckets: AgingBucket[];
  /** Khoá rổ đang lọc, `null` = không lọc. */
  dangChon: string | null;
  onChon: (khoa: string | null) => void;
}) {
  // Không nợ đồng nào thì THÔI hiện hẳn dải: sáu ô 0đ nằm chình ình chỉ tổ chiếm chỗ của bảng.
  if (!buckets.some((b) => b.amount > 0)) return null;

  return (
    <section className="aging-strip" aria-label="Phân tuổi nợ">
      {buckets.map((b) => {
        const chon = dangChon === b.key;
        const rong = b.amount <= 0;
        return (
          <button
            key={b.key}
            type="button"
            className={[
              "aging-strip__o",
              chon ? "is-chon" : "",
              b.key === CHUA_TOI_HAN ? "aging-strip__o--yen" : "",
              NANG.has(b.key) && !rong ? "aging-strip__o--nang" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            // Rổ RỖNG vẫn hiện (để mắt so được sáu mốc với nhau) nhưng KHOÁ bấm — lọc ra danh
            // sách trống là một cú bấm phí kèm màn hình trắng.
            disabled={rong}
            aria-pressed={chon}
            onClick={() => onChon(chon ? null : b.key)}
          >
            <span className="aging-strip__nhan">{b.label}</span>
            <b className="aging-strip__tien">{money(b.amount)}</b>
            <span className="aging-strip__dem">
              {b.count > 0 ? `${b.count} khoản` : "—"}
            </span>
          </button>
        );
      })}
    </section>
  );
}
