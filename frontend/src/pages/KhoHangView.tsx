// Màn TẠM cho 1 kho đã khai báo (bấm 1 kho dưới SECTION "Kho hàng" trên navbar). Bản này
// chỉ hiển thị danh tính kho; vận hành nhập/xuất/tồn là bản sau. Tái dùng visual "coming
// soon" của Sản xuất (.lsx-soon) cho nhất quán, chỉ đổi icon kho + hiện tên/mã kho.
import "./lenh-san-xuat.css";

export function KhoHangView({ ten, ma }: { ten: string; ma?: string }) {
  return (
    <main className="lsx">
      <div className="lsx-soon">
        <span className="lsx-soon__ic">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 8.6 12 4l9 4.6" />
            <path d="M5 10.4V20h14v-9.6" />
            <rect x="9" y="13.5" width="6" height="6.5" />
          </svg>
        </span>
        <h1 className="lsx-soon__title">{ten}</h1>
        {ma && (
          <p className="lsx-soon__sub" style={{ fontFamily: "var(--ff-num)", letterSpacing: "0.04em" }}>{ma}</p>
        )}
        <p className="lsx-soon__sub">
          Kho đã được khai báo. Chức năng nhập / xuất / tồn kho đang được xây dựng — sẽ có ở bản sau.
        </p>
      </div>
    </main>
  );
}
