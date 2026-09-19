// Ô hiển thị dùng chung của màn Giao hàng: pill trạng thái + khoảng trống có hướng dẫn
// (tách từ pages/GiaoHangPage.tsx).
import { useState, type ReactNode } from "react";
import { Button } from "../../../../components/Button";

/** Nút gọi máy chủ — TỰ KHOÁ khi lệnh đang đi. Bấm "Kho đã nhận lại" hai lần liền từng bắn hai
 *  lệnh: lệnh sau ăn 400 "không có hàng nào phải trả về kho" dù việc đã xong (bấm thử 18/09/2026). */
export function NutCho({
  variant = "accent",
  bam,
  children,
}: {
  variant?: "accent" | "ghost";
  bam: () => Promise<unknown>;
  children: ReactNode;
}) {
  const [dang, setDang] = useState(false);
  return (
    <Button variant={variant} disabled={dang}
      onClick={() => {
        setDang(true);
        bam().finally(() => setDang(false));
      }}>
      {children}
    </Button>
  );
}

/** Pill trạng thái — dùng chung ba tab để mắt không phải học hai bảng màu. */
export function Pill({ text, tone }: { text: string; tone: "on" | "off" | "warn" }) {
  return (
    <span className={`rc-pill rc-pill--${tone === "warn" ? "off" : tone} gh-pill gh-pill--${tone}`}>
      {text}
    </span>
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

/** Chuyến tài xế CHƯA cầm hàng — còn đổi người / đổi giờ / huỷ được. */
export const CHUA_CAM_HANG = ["da_len_ke_hoach", "dang_chuan_bi"];

/** Trả hàng về kho sau giao thiếu / thất bại (19/09/2026): máy TỰ lập yêu cầu nhập, THỦ KHO ghi sổ
 *  phiếu nhập là chuyến sang "Đã trả hàng" — tài xế không tự bấm "kho đã nhận" nữa. Chuyến cũ chưa
 *  có yêu cầu nhập thì còn nút lập phiếu trả kho. */
export function TraHang({
  t,
  onDaTra,
}: {
  t: { trang_thai: string; tra_hang_ma?: string | null; tra_hang_trang_thai?: string | null };
  onDaTra?: () => Promise<unknown>;
}) {
  if (t.tra_hang_ma) {
    const xong = t.tra_hang_trang_thai === "done";
    return <Pill text={`${xong ? "Kho đã nhận lại" : "Chờ kho nhận lại"} · ${t.tra_hang_ma}`} tone={xong ? "on" : "warn"} />;
  }
  if (t.trang_thai === "dang_tra_hang" && onDaTra)
    return <NutCho variant="ghost" bam={onDaTra}>Lập phiếu trả kho</NutCho>;
  return null;
}
