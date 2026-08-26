// Dải SAO của một nhà cung cấp — dùng chung cho BẢNG danh sách và HỒ SƠ trong drawer.
//
// ⚠️ Luật quan trọng nhất của khối này: `rating === null` là "CHƯA ĐÁNH GIÁ", KHÔNG phải 0 sao.
// Vẽ 5 ngôi sao rỗng cho một NCC vừa khai hồ sơ hôm qua là nói với người dùng rằng họ TỆ NHẤT —
// trong khi thật ra hệ chưa có một đơn nào để mà chấm. Thang sao thấp nhất là 1, nên 0 sao không
// bao giờ là một trạng thái hợp lệ ở đây.
//
// Không dùng emoji ⭐ (luật dự án): emoji đổi hình theo font từng máy, và trên Windows nó ra bản
// màu không chỉnh được sắc độ. Sao ở đây là SVG, tô bằng token màu như mọi thứ khác trong app.
import { useId } from "react";

/** 5 ngôi sao, tô ĐÚNG phần lẻ (4,2 sao ⇒ ngôi thứ 5 tô 20%) bằng một hình cắt chạy ngang. */
const O_SAO = 18;
const SO_SAO = 5;
const NET_SAO =
  "M9 1.4 10.82 6.49 16.23 6.65 11.95 9.96 13.47 15.15 9 12.1 4.53 15.15 6.05 9.96 1.77 6.65 7.18 6.49Z";

function soVi(v: number): string {
  return v.toLocaleString("vi-VN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function DaiSao({ rating, cao }: { rating: number; cao: number }) {
  // `useId` có dấu hai chấm — bỏ đi cho id an toàn khi nhiều dòng cùng vẽ trên một trang.
  const uid = useId().replace(/:/g, "");
  const rong = O_SAO * SO_SAO;
  const phanTo = (Math.max(0, Math.min(SO_SAO, rating)) / SO_SAO) * rong;
  const sao = Array.from({ length: SO_SAO }, (_, i) => i);
  return (
    <svg
      className="supplier__sao-svg"
      viewBox={`0 0 ${rong} ${O_SAO}`}
      width={(rong / O_SAO) * cao}
      height={cao}
      role="img"
      aria-label={`${soVi(rating)} trên 5 sao`}
      focusable="false"
    >
      <defs>
        <clipPath id={`sao-${uid}`}>
          <rect x="0" y="0" width={phanTo} height={O_SAO} />
        </clipPath>
      </defs>
      <g className="supplier__sao-nen">
        {sao.map((i) => (
          <path key={i} d={NET_SAO} transform={`translate(${i * O_SAO} 0)`} />
        ))}
      </g>
      <g className="supplier__sao-to" clipPath={`url(#sao-${uid})`}>
        {sao.map((i) => (
          <path key={i} d={NET_SAO} transform={`translate(${i * O_SAO} 0)`} />
        ))}
      </g>
    </svg>
  );
}

export function SaoNcc({
  rating,
  cao = 14,
  /** Ô hẹp (bảng) thì "chưa đánh giá" rút thành một gạch cho đỡ chật. */
  gonKhiTrong = false,
}: {
  rating: number | null;
  cao?: number;
  gonKhiTrong?: boolean;
}) {
  if (rating === null || rating === undefined) {
    return (
      <span
        className="supplier__sao supplier__sao--trong"
        title="Chưa có đơn hàng nào đủ dữ liệu để chấm"
      >
        {gonKhiTrong ? "—" : "Chưa đánh giá"}
      </span>
    );
  }
  return (
    <span className="supplier__sao">
      <DaiSao rating={rating} cao={cao} />
      <b className="supplier__sao-so">{soVi(rating)}</b>
    </span>
  );
}
