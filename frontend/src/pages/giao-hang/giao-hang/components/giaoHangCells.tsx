// Ô hiển thị dùng chung của màn Giao hàng: pill trạng thái + khoảng trống có hướng dẫn
// (tách từ pages/GiaoHangPage.tsx).

/** Pill trạng thái — dùng chung ba tab để mắt không phải học hai bảng màu. */
export function Pill({ text, tone }: { text: string; tone: "on" | "off" | "warn" }) {
  return (
    <span className={`rc-pill rc-pill--${tone === "warn" ? "off" : tone}`}>{text}</span>
  );
}

/** Khoảng trống có HƯỚNG DẪN. Ô "Chưa có gì" chỉ nói hết chuyện, không nói phải làm gì tiếp. */
export function KhoangTrong({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="gh-empty">
      <div className="gh-empty__title">{title}</div>
      <p className="gh-empty__desc">{desc}</p>
    </div>
  );
}
