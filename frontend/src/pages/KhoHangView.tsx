import "./rebuild-catalog.css";
import "./kho-request.css";

export function KhoHangView({ ten, ma }: { ten: string; ma?: string }) {
  return (
    <main className="rc">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{ten}</h1>
          {ma && <span className="rc__code-badge">{ma}</span>}
        </div>
        <p className="rc__sub">Thông tin danh tính và cấu hình quản lý kho vật lý.</p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--sp-4)", marginBottom: "var(--sp-6)" }}>
        <div className="card card--dense" style={{ display: "flex", alignItems: "center", gap: "var(--sp-4)" }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: "var(--r-3)",
            background: "var(--rust-soft)",
            color: "var(--rust-deep)",
            display: "grid",
            placeItems: "center"
          }}>
            <WarehouseIcon />
          </div>
          <div>
            <div className="stat__label">Tên Kho Vật Lý</div>
            <div className="stat__value" style={{ fontSize: "16px", fontWeight: "var(--fw-bold)" }}>{ten}</div>
            <div className="stat__hint">{ma ? `Mã kho: ${ma}` : "Chưa gắn mã"}</div>
          </div>
        </div>

        <div className="card card--dense" style={{ display: "flex", alignItems: "center", gap: "var(--sp-4)" }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: "var(--r-3)",
            background: "var(--moss-soft)",
            color: "var(--moss-deep)",
            display: "grid",
            placeItems: "center"
          }}>
            <CheckCircleIcon />
          </div>
          <div>
            <div className="stat__label">Trạng Thái Kho</div>
            <div style={{ marginTop: 2 }}>
              <span className="badge-sem badge-sem--moss">HOẠT ĐỘNG</span>
            </div>
            <div className="stat__hint">Kho sẵn sàng phục vụ nhập / xuất</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ textAlign: "center", padding: "var(--sp-8) var(--sp-6)" }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: "var(--r-pill)",
          background: "var(--paper)",
          border: "1px solid var(--rule-soft)",
          margin: "0 auto var(--sp-4)",
          display: "grid",
          placeItems: "center",
          color: "var(--ash)"
        }}>
          <WarehouseIcon size={28} />
        </div>
        <h3 style={{ margin: "0 0 var(--sp-2)", fontSize: "16px", fontWeight: "var(--fw-bold)", color: "var(--ink)" }}>
          {ten} — Đã được khai báo hệ thống
        </h3>
        <p style={{ margin: "0 auto", maxWidth: 480, color: "var(--ash)", fontSize: "13px", lineHeight: "1.6" }}>
          Mọi dữ liệu tồn kho, chứng từ và phân bổ lô của kho này được quản lý tự động từ dải menu 
          <strong> Yêu cầu nhập xuất</strong> và tab <strong> Tồn kho</strong>.
        </p>
      </div>
    </main>
  );
}

function WarehouseIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 8.6 12 4l9 4.6" />
      <path d="M5 10.4V20h14v-9.6" />
      <rect x="9" y="13.5" width="6" height="6.5" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

