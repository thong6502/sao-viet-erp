// Tab "Đơn giao hàng" — danh sách KHỐI (chủ chốt 18/09/2026): mỗi LƯỢT XE là một khối đủ các điểm
// (`KhoiLuot`), chuyến ngoài lượt là một thẻ gọn. Trước đó là bảng một dòng một yêu cầu: các đơn chung
// một vòng xe nằm rải rác, chỉ nối nhau bằng một mã lượt nhỏ — người lên đơn lẫn tài xế "khó hiểu quá".
// Máy chủ trang hoá theo khối (`/bang-giao`) nên một lượt không bị cắt đôi qua hai trang.
import type { BangGiaoItem, DeliveryTrip } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDateTime } from "../../../../utils/format";
import { nhanChuyen, toneChuyen } from "../shared/helpers";
import { CHUA_CAM_HANG, KhoangTrong, NutCho, Pill, TraHang } from "../components/giaoHangCells";
import { KhoiLuot } from "../components/KhoiLuot";

// =============================================================================
// Tab · Đơn giao hàng
// =============================================================================
export function BangKeHoach({
  items,
  loading,
  token,
  canPlan,
  canWrite,
  luotMoi,
  onDoi,
  onMo,
  onGuiDeNghi,
  onDaLay,
  onBatDau,
  onKetQua,
  onDaTra,
  onDoiChuyen,
}: {
  items: BangGiaoItem[];
  loading: boolean;
  token: string;
  canPlan: boolean;
  canWrite: boolean;
  /** Lượt vừa lập — khối đó được làm nổi + cuộn tới. */
  luotMoi?: number | null;
  onDoi: () => void;
  onMo: (requestId: number) => void;
  onGuiDeNghi?: (t: DeliveryTrip) => void;
  onDaLay?: (t: DeliveryTrip) => Promise<unknown>;
  onBatDau?: (t: DeliveryTrip) => Promise<unknown>;
  onKetQua?: (t: DeliveryTrip) => void;
  onDaTra?: (t: DeliveryTrip) => Promise<unknown>;
  onDoiChuyen?: (t: DeliveryTrip) => void;
}) {
  if (!loading && items.length === 0)
    return (
      <KhoangTrong
        title="Chưa có đơn giao hàng nào"
        desc="Đơn giao hàng sinh ra khi quản lý phân công tài xế cho một yêu cầu giao. Yêu cầu thì Bán hàng lập từ màn Đơn hàng bán, ở khối “Giao hàng” cuối trang đơn đã chốt."
      />
    );
  return (
    <div className="gh-ds">
      {loading && items.length === 0 && <p className="rc__sub" style={{ textAlign: "center", padding: "24px" }}>Đang tải…</p>}
      {items.map((it) =>
        it.luot ? (
          <KhoiLuot key={`luot-${it.luot.id}`} luot={it.luot} token={token}
            canPlan={canPlan} canWrite={canWrite} moi={it.luot.id === luotMoi}
            onDoi={onDoi} onMo={onMo} onKetQua={onKetQua} onDaTra={onDaTra} onDoiChuyen={onDoiChuyen} />
        ) : it.trip ? (
          <TheChuyen key={`chuyen-${it.trip.id}`} t={it.trip} onMo={onMo}
            onGuiDeNghi={onGuiDeNghi} onDaLay={onDaLay} onBatDau={onBatDau}
            onKetQua={onKetQua} onDaTra={onDaTra} onDoiChuyen={onDoiChuyen} />
        ) : null,
      )}
    </div>
  );
}

/** Chuyến NGOÀI lượt (dữ liệu cũ, hoặc danh mục chưa có xe) — một thẻ gọn, đủ nút như bảng cũ. */
function TheChuyen({
  t,
  onMo,
  onGuiDeNghi,
  onDaLay,
  onBatDau,
  onKetQua,
  onDaTra,
  onDoiChuyen,
}: {
  t: DeliveryTrip;
  onMo: (requestId: number) => void;
  onGuiDeNghi?: (t: DeliveryTrip) => void;
  onDaLay?: (t: DeliveryTrip) => Promise<unknown>;
  onBatDau?: (t: DeliveryTrip) => Promise<unknown>;
  onKetQua?: (t: DeliveryTrip) => void;
  onDaTra?: (t: DeliveryTrip) => Promise<unknown>;
  onDoiChuyen?: (t: DeliveryTrip) => void;
}) {
  return (
    <article className="gh-le" aria-label={`Đơn giao ${t.request_code ?? ""}`}>
      <div className="gh-le__chinh">
        <span className="gh-diem__ten">{t.customer_name}</span>
        <span className="gh-ma rc__sub">
          <button type="button" className="gh-link" onClick={() => onMo(t.request_id)}>
            {t.request_code}
          </button>
          {t.order_code && <span className="gh-nowrap">· {t.order_code}</span>}
        </span>
      </div>
      <div className="gh-le__phu rc__sub">
        <span style={{ fontWeight: 600, color: "#0f172a" }}>{t.employee_name}</span>
        <span className="gh-nowrap">Lấy {fmtDateTime(t.gio_lay_hang)}</span>
        <span className="gh-nowrap">Giao {fmtDateTime(t.gio_du_kien_giao)}</span>
      </div>
      <span className="gh-le__tt gh-nowrap"><Pill text={nhanChuyen(t)} tone={toneChuyen(t.trang_thai)} /></span>
      <span className="gh-le__km"><span className="gh-num">{t.tong_km || "—"}</span> km</span>
      <div className="gh-le__nut">
        {t.trang_thai === "da_len_ke_hoach" && !t.yeu_cau_kho_ma && onGuiDeNghi && (
          <Button variant="accent" onClick={() => onGuiDeNghi(t)}>
            Gửi yêu cầu xuất kho
          </Button>
        )}
        {t.trang_thai === "dang_chuan_bi" && onDaLay && (
          <NutCho bam={() => onDaLay(t)}>Đã lấy hàng</NutCho>
        )}
        {t.trang_thai === "da_lay_hang" && onBatDau && (
          <NutCho variant="ghost" bam={() => onBatDau(t)}>Bắt đầu giao</NutCho>
        )}
        {t.trang_thai === "dang_giao" && onKetQua && (
          <Button variant="accent" onClick={() => onKetQua(t)}>
            Nhập kết quả
          </Button>
        )}
        <TraHang t={t} onDaTra={onDaTra ? () => onDaTra(t) : undefined} />
        {CHUA_CAM_HANG.includes(t.trang_thai) && onDoiChuyen && (
          <Button variant="ghost" onClick={() => onDoiChuyen(t)}>Đổi / huỷ chuyến</Button>
        )}
      </div>
    </article>
  );
}
