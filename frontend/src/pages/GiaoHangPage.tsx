// Màn Giao hàng — docs/prd-giao-hang.md §10.
//
// BA TAB, MỖI TAB MỘT Ô QUYỀN (luật "một ô = một tab", chốt 15/08/2026):
//   Đơn giao hàng          ← can_read        (tab mặc định)
//   Yêu cầu giao           ← can_plan
//   Nhân viên giao hàng    ← can_view_drivers
//
// Phạm vi LỌC DÒNG chứ không ẩn tab — máy chủ đã lọc, FE không tự suy lại. Và trạng thái của
// YÊU CẦU do máy chủ tính (hàm của các lần giao), FE chỉ hiển thị: tính lại ở đây là hai nơi
// hiểu khác nhau.
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  DeliveryDriver,
  HangCanXuat,
  DeliveryDriverPick,
  DeliveryRequest,
  DeliveryRequestDetail,
  DeliveryTrip,
  DinhKemChuyen,
  KetQuaInput,
} from "../api/client";
import { api, assetUrl } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { fmtDate, fmtDateTime } from "../utils/format";
import "./rebuild-catalog.css";
import "./giao-hang.css";
import "./kho-request.css";

type TabId = "ke-hoach" | "cho-len-ke-hoach" | "nhan-vien";

const NHAN_TRANG_THAI_YC: Record<string, string> = {
  cho_len_ke_hoach: "Chờ lên kế hoạch",
  dang_thuc_hien: "Đang thực hiện",
  da_giao_du: "Đã giao đủ",
  da_huy: "Đã huỷ",
};

const NHAN_TRANG_THAI_CHUYEN: Record<string, string> = {
  da_len_ke_hoach: "Đã lên kế hoạch",
  dang_chuan_bi: "Kho đang chuẩn bị",
  da_lay_hang: "Đã lấy hàng",
  dang_giao: "Đang giao",
  thanh_cong: "Giao thành công",
  giao_thieu: "Giao thiếu",
  hen_lai: "Khách hẹn lại",          // dòng CŨ trước 22/08/2026 — không còn khai mới
  that_bai: "Giao thất bại",
  dang_tra_hang: "Đang trả hàng",
  da_tra_hang: "Đã trả hàng",
  da_huy: "Đã huỷ",
};

/** Nhãn trạng thái của MỘT chuyến — MỘT hàm cho MỌI chỗ render.
 *
 *  Kho lập phiếu xong ⇒ hàng đã soạn, tài xế tới lấy được, nên chữ đổi thành "Kho đã chuẩn bị
 *  xong" (chủ chốt 20/08/2026). Kho KHÔNG bấm gì trên màn này — cờ `kho_da_lap_phieu` đọc ngược
 *  từ sổ kho.
 *
 *  Viết thành hàm vì bảng chuyến render ở HAI chỗ (tab Đơn giao hàng và tab Yêu cầu giao); chép
 *  hai bản là sớm muộn hai chỗ nói hai kiểu. */
function nhanChuyen(t: { trang_thai: string; kho_da_lap_phieu?: boolean }): string {
  if (t.trang_thai === "dang_chuan_bi" && t.kho_da_lap_phieu) return "Kho đã chuẩn bị xong";
  return NHAN_TRANG_THAI_CHUYEN[t.trang_thai] ?? t.trang_thai;
}

const NHAN_TRANG_THAI_NV: Record<string, string> = {
  ranh: "Rảnh",
  co_lich: "Có lịch",
  dang_giao: "Đang giao",
  dang_tra_hang: "Đang trả hàng",
  nghi: "Nghỉ",
};

/** Pill trạng thái — dùng chung ba tab để mắt không phải học hai bảng màu. */
function Pill({ text, tone }: { text: string; tone: "on" | "off" | "warn" }) {
  return (
    <span className={`rc-pill rc-pill--${tone === "warn" ? "off" : tone}`}>{text}</span>
  );
}

function toneChuyen(tt: string): "on" | "off" | "warn" {
  if (tt === "thanh_cong") return "on";
  if (tt === "that_bai" || tt === "da_huy") return "off";
  return "warn";
}

export default function GiaoHangPage({ eventTick = 0 }: { eventTick?: number }) {
  const { token } = useAuth();
  const can = useCan();
  const canPlan = can("giao_hang", "plan");
  const canViewDrivers = can("giao_hang", "view_drivers");
  const canWrite = can("giao_hang", "create");
  const canCancel = can("giao_hang", "cancel");

  const [tab, setTab] = useState<TabId>("ke-hoach");
  const [trips, setTrips] = useState<DeliveryTrip[]>([]);
  const [requests, setRequests] = useState<DeliveryRequest[]>([]);
  const [drivers, setDrivers] = useState<DeliveryDriver[]>([]);
  const [detail, setDetail] = useState<DeliveryRequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [planFor, setPlanFor] = useState<DeliveryRequest | null>(null);
  const [ketQuaFor, setKetQuaFor] = useState<DeliveryTrip | null>(null);
  const [xuatKhoFor, setXuatKhoFor] = useState<DeliveryTrip | null>(null);
  // Tháng đang xem ở tab Nhân viên. `YYYY-MM` theo giờ ĐỊA PHƯƠNG — `toISOString()` trả UTC nên
  // đầu/cuối tháng có thể nhảy sang tháng bên cạnh.
  const [thang, setThang] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    const viec: Promise<unknown>[] = [
      api.giaoHang.trips(token).then((r) => setTrips(r.items)),
      api.giaoHang.requests(token).then((r) => setRequests(r.items)),
    ];
    // Tab nào không có ô thì KHÔNG gọi — gọi rồi nuốt 403 là che mất lỗi cấu hình thật.
    if (canViewDrivers)
      viec.push(api.giaoHang.nhanVien(token, { thang }).then((r) => setDrivers(r.items)));
    Promise.all(viec)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Không tải được dữ liệu"))
      .finally(() => setLoading(false));
    // `thang` PHẢI có ở đây — thiếu thì đổi tháng mà bảng đứng im.
  }, [token, canViewDrivers, thang]);

  // `eventTick` tăng mỗi sự kiện SSE ⇒ bảng tự tải lại. Tài xế không phải F5 để biết kho đã
  // soạn xong hàng chưa (CLAUDE.md: gửi/thông báo nội bộ phải tức thì).
  useEffect(() => {
    load();
  }, [load, eventTick]);

  const dsDon = useMemo(() => gopTheoYeuCau(trips), [trips]);

  const choLenKeHoach = useMemo(
    () => requests.filter((r) => r.trang_thai === "cho_len_ke_hoach"),
    [requests],
  );

  /** Gọi một hành động rồi tải lại; lỗi hiện lên banner thay vì nuốt im. */
  const goi = useCallback(
    (viec: Promise<unknown>) => {
      viec
        .then(load)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Không thao tác được"));
    },
    [load],
  );

  const moChiTiet = useCallback(
    (requestId: number) => {
      if (!token) return;
      api.giaoHang
        .request(token, requestId)
        .then(setDetail)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Không mở được chi tiết"));
    },
    [token],
  );

  const tabs: { id: TabId; label: string; count: number; hien: boolean }[] = [
    { id: "ke-hoach", label: "Đơn giao hàng", count: dsDon.length, hien: true },
    {
      id: "cho-len-ke-hoach",
      label: "Yêu cầu giao",
      count: choLenKeHoach.length,
      hien: canPlan,
    },
    { id: "nhan-vien", label: "Nhân viên giao hàng", count: drivers.length, hien: canViewDrivers },
  ];
  const tabHien = tabs.filter((t) => t.hien);
  const tabDang = tabHien.some((t) => t.id === tab) ? tab : "ke-hoach";

  return (
    // `.rc` là KHUNG TRANG (max-width 1200 · canh giữa · padding) — màn top-level nào cũng phải
    // có. `.kho-list` chỉ là móc chỉnh bảng của ba màn Kho, KHÔNG mang layout: để mình nó thì nội
    // dung dán sát hai mép màn hình. Ba màn Kho không lộ ra lỗi này vì `KhoPage` bọc `.rc` sẵn.
    <main className="rc">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Giao hàng</h1>
          <span className="rc__count">{dsDon.length} đơn giao</span>
        </div>
        <p className="rc__sub">
          Yêu cầu từ Bán hàng → lên đơn giao hàng → gửi đề nghị xuất hàng → kho duyệt → tài xế
          lấy hàng và giao.
        </p>
      </header>

      <div className="rc__toolbar">
        <div className="gh-seg" role="tablist">
          {tabHien.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tabDang === t.id}
              className={`gh-seg__btn${tabDang === t.id ? " is-active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              <span className="gh-seg__n">{t.count}</span>
            </button>
          ))}
        </div>
        <div className="rc__spacer" />
        <Button variant="ghost" onClick={load}>
          <Icon name="refresh" size={16} /> Tải lại
        </Button>
      </div>

      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
        </div>
      )}

      {tabDang === "ke-hoach" && (
        <BangKeHoach trips={trips} loading={loading} onMo={moChiTiet}
          onKetQua={canWrite ? setKetQuaFor : undefined}
          onGuiDeNghi={canPlan ? setXuatKhoFor : undefined}
          onDaLay={canWrite && token ? (t) => goi(api.giaoHang.daLayHang(token, t.id)) : undefined}
          onDaTra={
            canWrite && token
              ? (t) =>
                  api.giaoHang
                    .daTraHang(token, t.id)
                    .then(load)
                    .catch((e: unknown) =>
                      setError(e instanceof Error ? e.message : "Không ghi được đã trả hàng"))
              : undefined
          }
          onBatDau={
            canWrite && token
              ? (t) =>
                  api.giaoHang
                    .batDauGiao(token, t.id)
                    .then(load)
                    .catch((e: unknown) =>
                      setError(e instanceof Error ? e.message : "Không bắt đầu giao được"))
              : undefined
          }
        />
      )}

      {tabDang === "cho-len-ke-hoach" && (
        <BangChoLenKeHoach rows={choLenKeHoach} loading={loading} onMo={moChiTiet}
          onLenKeHoach={setPlanFor} />
      )}

      {tabDang === "nhan-vien" && (
        <BangNhanVien rows={drivers} loading={loading} thang={thang} onDoiThang={setThang} />
      )}

      {detail && (
        <DrawerChiTiet
          detail={detail}
          canCancel={canCancel}
          onClose={() => setDetail(null)}
          onHuy={
            canCancel && token
              ? (lyDo) =>
                  api.giaoHang
                    .cancelRequest(token, detail.request.id, lyDo)
                    .then(() => {
                      setDetail(null);
                      load();
                    })
                    .catch((e: unknown) =>
                      setError(e instanceof Error ? e.message : "Không huỷ được"))
              : undefined
          }
        />
      )}

      {planFor && token && (
        <DialogLenKeHoach
          request={planFor}
          token={token}
          onClose={() => setPlanFor(null)}
          onXong={() => {
            setPlanFor(null);
            load();
          }}
        />
      )}

      {xuatKhoFor && token && (
        <DialogYeuCauXuatKho
          trip={xuatKhoFor}
          token={token}
          onClose={() => setXuatKhoFor(null)}
          onXong={() => {
            setXuatKhoFor(null);
            load();
          }}
        />
      )}

      {ketQuaFor && token && (
        <DialogKetQua
          trip={ketQuaFor}
          token={token}
          onClose={() => setKetQuaFor(null)}
          onXong={() => {
            setKetQuaFor(null);
            load();
          }}
        />
      )}
    </main>
  );
}

// =============================================================================
// Tab · Đơn giao hàng
// =============================================================================
/** Khoảng trống có HƯỚNG DẪN. Ô "Chưa có gì" chỉ nói hết chuyện, không nói phải làm gì tiếp. */
function KhoangTrong({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="gh-empty">
      <div className="gh-empty__title">{title}</div>
      <p className="gh-empty__desc">{desc}</p>
    </div>
  );
}

/** Một dòng của bảng = MỘT YÊU CẦU, không phải một chuyến. */
interface DongKeHoach {
  /** Chuyến MỚI NHẤT — nguồn của mọi cột hiện trên dòng và của mọi nút thao tác. */
  moi: DeliveryTrip;
  /** Tổng số lần giao đã thực hiện cho yêu cầu này. */
  /** TỔNG km cả các lần — PRD §9: lần 1 thất bại 18km + lần 2 thành công 22km = 40km. */
  tongKm: number;
}

/** Một dòng bảng = một YÊU CẦU giao.
 *
 * Từ 22/08/2026 một yêu cầu chỉ có MỘT chuyến (chặn ở service + chỉ số UNIQUE mg 0229), nên hàm
 * này gần như là ánh xạ 1–1. GIỮ nó thay vì đọc thẳng danh sách chuyến: dữ liệu gieo trước ngày
 * đó vẫn có thể có hai chuyến một yêu cầu, và bảng phải hiện tình trạng HIỆN TẠI chứ không hiện
 * hai dòng trùng mã trùng khách. */
function gopTheoYeuCau(trips: DeliveryTrip[]): DongKeHoach[] {
  const theo = new Map<number, DeliveryTrip[]>();
  for (const t of trips) {
    const ds = theo.get(t.request_id);
    if (ds) ds.push(t);
    else theo.set(t.request_id, [t]);
  }
  return [...theo.values()]
    .map((ds) => {
      const moi = ds.reduce((a, b) => (b.lan_thu > a.lan_thu ? b : a));
      return {
        moi,
        tongKm: ds.reduce((n, t) => n + (t.km ?? 0), 0),
      };
    })
    .sort((a, b) => b.moi.gio_lay_hang.localeCompare(a.moi.gio_lay_hang));
}

function BangKeHoach({
  trips,
  loading,
  onMo,
  onGuiDeNghi,
  onDaLay,
  onBatDau,
  onKetQua,
  onDaTra,
}: {
  trips: DeliveryTrip[];
  loading: boolean;
  onMo: (requestId: number) => void;
  onGuiDeNghi?: (t: DeliveryTrip) => void;
  onDaLay?: (t: DeliveryTrip) => void;
  onBatDau?: (t: DeliveryTrip) => void;
  onKetQua?: (t: DeliveryTrip) => void;
  onDaTra?: (t: DeliveryTrip) => void;
}) {
  const dong = gopTheoYeuCau(trips);
  if (!loading && trips.length === 0)
    return (
      <KhoangTrong
        title="Chưa có đơn giao hàng nào"
        desc="Đơn giao hàng sinh ra khi quản lý phân công tài xế cho một yêu cầu giao. Yêu cầu thì Bán hàng lập từ màn Đơn hàng bán, ở khối “Giao hàng” cuối trang đơn đã chốt."
      />
    );
  return (
    <div className="rc__tablewrap">
      <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th style={{ width: "11%" }}>Yêu cầu</th>
            <th style={{ width: "9%" }}>Đơn hàng</th>
            {/* Khách hàng KHÔNG khai bề ngang — nó ăn phần còn lại. Trước đây 8 cột kia cộng
                lại 92% nên tên khách bị ép xuống 8%, gãy làm hai dòng. */}
            <th>Khách hàng</th>
            <th style={{ width: "12%" }}>Nhân viên giao</th>
            <th style={{ width: "12%" }}>Giờ lấy hàng</th>
            <th style={{ width: "12%" }}>Dự kiến giao</th>
            <th style={{ width: "13%" }}>Trạng thái</th>
            {/* TỔNG km cả các lần giao của yêu cầu — không phải km của riêng lần cuối. */}
            <th style={{ width: "6%" }}>Tổng km</th>
            <th style={{ width: "11%" }} />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={9}>Đang tải…</td>
            </tr>
          )}
          {dong.map(({ moi: t, tongKm }) => (
            <tr key={t.request_id}>
              <td>
                <button type="button" className="gh-link" onClick={() => onMo(t.request_id)}>
                  {t.request_code}
                </button>
              </td>
              <td>{t.order_code}</td>
              <td>{t.customer_name}</td>
              <td>{t.employee_name}</td>
              <td className="gh-nowrap">{fmtDateTime(t.gio_lay_hang)}</td>
              <td className="gh-nowrap">{fmtDateTime(t.gio_du_kien_giao)}</td>
              {/* `gh-nowrap`: "Kho đã chuẩn bị xong" dài hơn nhãn cũ nên cột hẹp bẻ nó xuống
                  hai dòng giữa chữ, viên pill vỡ làm đôi. */}
              <td className="gh-nowrap">
                <Pill
                  text={nhanChuyen(t)}
                  tone={toneChuyen(t.trang_thai)}
                />
              </td>
              <td className="gh-num">{tongKm || "—"}</td>
              <td>
                {/* Hàng ra khỏi kho phải có phiếu kho — giao khách không ngoại lệ. Nút này
                    lập một YÊU CẦU XUẤT KHO thật, kho lập phiếu bằng luồng sẵn có. */}
                {t.trang_thai === "da_len_ke_hoach" && !t.yeu_cau_kho_ma && onGuiDeNghi && (
                  <Button variant="accent" onClick={() => onGuiDeNghi(t)}>
                    Gửi yêu cầu xuất kho
                  </Button>
                )}
                {/* Mã yêu cầu kho (DNX…) KHÔNG hiện ở cột Thao tác — nó không phải thao tác,
                    không có nhãn, và đứng cạnh nút thì trông như một nút hỏng (bỏ 20/08/2026).
                    Mã vẫn còn ở chi tiết yêu cầu, chỗ có ngữ cảnh để đọc. */}
                {/* Tài xế TỰ bấm — người cầm hàng mới biết hàng đã ra khỏi kho. */}
                {t.trang_thai === "dang_chuan_bi" && onDaLay && (
                  <Button variant="accent" onClick={() => onDaLay(t)}>
                    Đã lấy hàng
                  </Button>
                )}
                {t.trang_thai === "da_lay_hang" && onBatDau && (
                  <Button variant="ghost" onClick={() => onBatDau(t)}>
                    Bắt đầu giao
                  </Button>
                )}
                {t.trang_thai === "dang_giao" && onKetQua && (
                  <Button variant="accent" onClick={() => onKetQua(t)}>
                    Nhập kết quả
                  </Button>
                )}
                {/* Thiếu nút này thì chuyến giao hỏng nằm mãi ở "Đang trả hàng": API có, giao
                    diện quên — chuyến tắc mà không ai biết vì sao. */}
                {t.trang_thai === "dang_tra_hang" && onDaTra && (
                  <Button variant="ghost" onClick={() => onDaTra(t)}>
                    Kho đã nhận lại
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// =============================================================================
// Tab · Yêu cầu giao
// =============================================================================
function BangChoLenKeHoach({
  rows,
  loading,
  onMo,
  onLenKeHoach,
}: {
  rows: DeliveryRequest[];
  loading: boolean;
  onMo: (id: number) => void;
  onLenKeHoach: (r: DeliveryRequest) => void;
}) {
  if (!loading && rows.length === 0)
    return (
      <KhoangTrong
        title="Không có yêu cầu giao nào đang chờ"
        desc="Mọi yêu cầu Bán hàng gửi sang đều đã lên đơn giao hàng. Yêu cầu mới sẽ hiện ở đây ngay, không cần tải lại trang."
      />
    );
  return (
    <div className="rc__tablewrap">
      <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th style={{ width: "12%" }}>Mã yêu cầu</th>
            <th style={{ width: "11%" }}>Đơn hàng</th>
            <th>Khách hàng</th>
            <th style={{ width: "12%" }}>Ngày cần giao</th>
            <th style={{ width: "20%" }}>Hàng hoá</th>
            <th style={{ width: "13%" }}>Người yêu cầu</th>
            {/* Cột "Lệnh SX" GỠ 20/08/2026: bộ phận giao hàng chỉ nhận yêu cầu, sản xuất tới
                đâu là việc của xưởng. Cột chỉ-để-nhìn mà không ai quyết theo nó là cột thừa. */}
            <th style={{ width: "12%" }} />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={7}>Đang tải…</td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <button type="button" className="gh-link" onClick={() => onMo(r.id)}>
                  {r.code}
                </button>
              </td>
              <td>{r.order_code}</td>
              <td>{r.customer_name}</td>
              <td>{fmtDate(r.ngay_can_giao)}</td>
              {/* CHỈ ĐẾM, không liệt kê. Đổ cả danh sách ra đây làm dòng cao gấp ba và đẩy
                  cột Thao tác ra rìa — mà tên sản phẩm in thì dài sẵn ("Hộp thuốc 10 vỉ — in 2
                  màu, cán bóng"). Muốn xem gì thì bấm mã yêu cầu để mở chi tiết.
                  `title` để rê chuột xem nhanh — không tốn chỗ nào trên bảng. */}
              <td className="gh-nowrap" title={r.lines
                .map((l) => `${l.mo_ta ?? ""} × ${l.qty}${l.don_vi_tinh ? ` ${l.don_vi_tinh}` : ""}`)
                .join(" · ")}>
                {r.lines.length} mặt hàng
              </td>
              <td>{r.created_by_name}</td>
              <td>
                <Button variant="accent" onClick={() => onLenKeHoach(r)}>
                  Lên đơn giao hàng
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// =============================================================================
// Tab · Nhân viên giao hàng
// =============================================================================
function BangNhanVien({ rows, loading, thang, onDoiThang }: {
  rows: DeliveryDriver[]; loading: boolean;
  thang: string; onDoiThang: (t: string) => void;
}) {
  // Ô chọn tháng đứng NGOÀI nhánh rỗng: hết người trong tháng này không có nghĩa là hết người —
  // ẩn ô chọn lúc đó là nhốt người dùng ở đúng cái tháng trống, không quay lại được.
  const dauBang = (
    <div className="gh-nvbar">
      <label className="gh-nvbar__thang">
        <span>Tháng</span>
        <input className="input" type="month" value={thang}
          onChange={(e) => onDoiThang(e.target.value)} />
      </label>
      <span className="rc__sub">
        Hai cột <strong>tháng này</strong> đổi theo ô trên. Cột <strong>hôm nay</strong> và trạng
        thái luôn là hiện tại.
      </span>
    </div>
  );

  if (!loading && rows.length === 0)
    return (
      <>
        {dauBang}
        <KhoangTrong
          title="Chưa có nhân viên giao hàng nào"
          desc="Bảng liệt kê người thuộc Bộ phận Giao hàng (bật ở màn Phòng ban), cộng người đã được phân chuyến."
        />
      </>
    );
  return (
    // Dải chọn tháng đứng NGOÀI `.rc__tablewrap`: thẻ đó có viền + `overflow-x: auto`, để ô chọn
    // vào trong là nó nằm trong khung bảng và trôi ngang theo bảng khi màn hẹp.
    <>
      {dauBang}
      <div className="rc__tablewrap">
        <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th>Nhân viên</th>
            <th style={{ width: "14%" }}>Trạng thái</th>
            <th style={{ width: "16%" }}>Đang thực hiện</th>
            <th style={{ width: "16%" }}>Chuyến kế tiếp</th>
            {/* Bốn cột SỐ đều căn phải — trộn trái/phải thì mắt phải nhảy qua nhảy lại để
                so hàng, và các số nhiều chữ số trông như lệch cột. */}
            {/* "Xong hôm nay" đổi thành "Đã giao hôm nay" (chủ 21/08/2026: "nhìn vào người ta
                không hiểu đâu") — "xong" không nói xong CÁI GÌ. Đếm số CHUYẾN hàng tới tay
                khách, tính cả chuyến giao thiếu. */}
            <th className="gh-num" style={{ width: "10%" }}>Đã giao hôm nay</th>
            <th className="gh-num" style={{ width: "10%" }}>Km hôm nay</th>
            {/* Hai khung thời gian, hai câu hỏi khác nhau: cột NGÀY để điều độ ("giờ ai đang
                rảnh"), cột THÁNG để theo dõi định kỳ. Gộp một cột là mất một trong hai. */}
            <th className="gh-num" style={{ width: "10%" }}>Đã giao tháng này</th>
            <th className="gh-num" style={{ width: "10%" }}>Km tháng này</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={8}>Đang tải…</td>
            </tr>
          )}
          {rows.map((d) => (
            <tr key={d.employee_id}>
              <td>{d.ho_ten}</td>
              <td>
                <Pill
                  text={NHAN_TRANG_THAI_NV[d.trang_thai] ?? d.trang_thai}
                  tone={d.trang_thai === "ranh" ? "on" : d.trang_thai === "nghi" ? "off" : "warn"}
                />
              </td>
              <td>{d.chuyen_dang_thuc_hien ?? "—"}</td>
              <td>{d.chuyen_ke_tiep ?? "—"}</td>
              <td className="gh-num">{d.so_chuyen_xong}</td>
              {/* Số km CHỈ ĐỂ THỐNG KÊ — không vào lương (PRD quyết định #3). */}
              <td className="gh-num">{d.tong_km}</td>
              <td className="gh-num">{d.so_chuyen_thang ?? 0}</td>
              <td className="gh-num">{d.tong_km_thang ?? 0}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </>
  );
}

// =============================================================================
// Drawer · Chi tiết yêu cầu
// =============================================================================
/** File minh chứng của chuyến — ảnh/PDF.
 *
 * Việc thật: hàng đi kèm hoá đơn. Trước lúc đi đính hoá đơn cho tài xế cầm theo, giao xong chụp
 * lại tờ khách đã ký. KHÔNG chia "hoá đơn đi" với "biên nhận về": chia ra là bắt người dùng chọn
 * loại trước khi tải, chọn sai thì phải xoá tải lại. */
function DinhKemChuyenBox({ tripId, token }: { tripId: number; token: string | null }) {
  const [ds, setDs] = useState<DinhKemChuyen[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const nap = useCallback(() => {
    if (!token) return;
    api.giaoHang.dinhKemChuyen(token, tripId)
      .then((r) => setDs(r.items))
      .catch(() => setDs([]));
  }, [token, tripId]);
  useEffect(nap, [nap]);

  async function them(f: File | null) {
    if (!token || !f) return;
    setDangTai(true);
    setLoi(null);
    try {
      await api.giaoHang.themDinhKemChuyen(token, tripId, f);
      nap();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tải lên được.");
    } finally {
      setDangTai(false);
    }
  }

  async function xoa(id: number) {
    if (!token) return;
    try {
      await api.giaoHang.xoaDinhKemChuyen(token, tripId, id);
      nap();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xoá được.");
    }
  }

  return (
    <div className="gh-dinhkem">
      <div className="gh-dinhkem__head">
        <strong>Hoá đơn / minh chứng</strong>
        <label className="btn btn--secondary gh-dinhkem__add">
          {dangTai ? "Đang tải…" : "Thêm file"}
          <input type="file" accept="image/*,application/pdf" hidden disabled={dangTai}
                 onChange={(e) => { void them(e.target.files?.[0] ?? null); e.target.value = ""; }} />
        </label>
      </div>
      <p className="rc__sub">Ảnh hoặc PDF, tối đa 10 MB mỗi file.</p>
      {loi && <div className="banner banner--error" role="alert">{loi}</div>}
      {ds.length === 0 && <p className="rc__sub">Chưa có file nào.</p>}
      {ds.map((f) => (
        <div key={f.id} className="gh-line">
          {/* PHẢI qua `assetUrl`: `file_url` là đường TƯƠNG ĐỐI (`/api/files/...`), mà giao diện
              chạy khác cổng với API — để nguyên là trình duyệt tìm file ở cổng của giao diện rồi
              báo không thấy. `assetUrl` ghép đúng gốc API; cookie đọc file trình duyệt tự gửi. */}
          <a href={assetUrl(f.file_url) ?? "#"} target="_blank" rel="noreferrer">{f.file_name}</a>
          <span>{fmtDateTime(f.uploaded_at)}</span>
          <button type="button" className="dhb__invoice-cancel" onClick={() => void xoa(f.id)}>
            Xoá
          </button>
        </div>
      ))}
    </div>
  );
}

function DrawerChiTiet({
  detail,
  canCancel,
  onClose,
  onHuy,
}: {
  detail: DeliveryRequestDetail;
  canCancel: boolean;
  onClose: () => void;
  onHuy?: (lyDo: string) => void;
}) {
  const { token } = useAuth();
  const [lyDo, setLyDo] = useState("");
  const r = detail.request;
  const huyDuoc = canCancel && r.trang_thai === "cho_len_ke_hoach" && detail.trips.length === 0;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <Pill
              text={NHAN_TRANG_THAI_YC[r.trang_thai] ?? r.trang_thai}
              tone={r.trang_thai === "da_giao_du" ? "on" : r.trang_thai === "da_huy" ? "off" : "warn"}
            />
            <h2 className="rc-drawer__title">{r.code}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        <div className="rc-drawer__body">
          <section>
            <h3>Đơn hàng &amp; khách</h3>
            <p>
              {r.order_code} · {r.customer_name}
            </p>
            <p>Ngày cần giao: {fmtDate(r.ngay_can_giao)}</p>
            {/* Địa chỉ là SNAPSHOT lúc lập yêu cầu — sửa địa chỉ đơn sau này KHÔNG đổi dòng này. */}
            <p>
              {r.dia_chi}
              {r.nguoi_nhan ? ` — ${r.nguoi_nhan}` : ""}
              {r.sdt_nguoi_nhan ? ` · ${r.sdt_nguoi_nhan}` : ""}
            </p>
            {r.ghi_chu && <p>{r.ghi_chu}</p>}
          </section>

          <section>
            <h3>Hàng cần giao</h3>
            <table className="rc__table">
              <thead>
                <tr>
                  <th>Mặt hàng</th>
                  <th>Yêu cầu</th>
                  <th>Đã giao</th>
                </tr>
              </thead>
              <tbody>
                {r.lines.map((l) => (
                  <tr key={l.id}>
                    <td>{l.mo_ta}</td>
                    <td>
                      {l.qty} {l.don_vi_tinh}
                    </td>
                    <td>{l.da_giao}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            {/* MỘT yêu cầu = MỘT chuyến (22/08/2026). Bỏ tiêu đề đếm "Các lần giao (N)" — đếm một
                thứ luôn bằng 1 là bắt người đọc hỏi "sao lại có số đếm ở đây". Muốn giao lại thì
                lập yêu cầu mới, nên phần này chỉ còn là dòng thông tin của chính chuyến đó. */}
            <h3>Chuyến giao</h3>
            {detail.trips.length === 0 && <p>Chưa lên kế hoạch.</p>}
            {detail.trips.map((t) => (
              <div key={t.id} className="gh-line">
                <Pill
                  text={nhanChuyen(t)}
                  tone={toneChuyen(t.trang_thai)}
                />
                <span>
                  {t.employee_name} · {fmtDateTime(t.gio_lay_hang)}
                  {t.km != null ? ` · ${t.km} km` : ""}
                  {t.yeu_cau_kho_ma ? ` · ${t.yeu_cau_kho_ma}` : ""}
                </span>
                {t.ly_do_that_bai && <em>{t.ly_do_that_bai}</em>}
              </div>
            ))}
            {detail.trips[0] && <DinhKemChuyenBox tripId={detail.trips[0].id} token={token} />}
          </section>

          <section>
            <h3>Lịch sử trạng thái</h3>
            {detail.lich_su.map((h) => (
              <div key={h.id} className="gh-line">
                <span>
                  {fmtDateTime(h.luc)} · {NHAN_TRANG_THAI_CHUYEN[h.den_trang_thai] ?? h.den_trang_thai}
                  {h.nguoi_thao_tac_name ? ` · ${h.nguoi_thao_tac_name}` : ""}
                  {h.ly_do ? ` — ${h.ly_do}` : ""}
                </span>
              </div>
            ))}
          </section>

          {huyDuoc && onHuy && (
            <section>
              <h3>Huỷ yêu cầu</h3>
              <input
                className="input"
                placeholder="Lý do huỷ"
                value={lyDo}
                onChange={(e) => setLyDo(e.target.value)}
              />
              <Button variant="ghost" disabled={!lyDo.trim()} onClick={() => onHuy(lyDo.trim())}>
                Huỷ yêu cầu
              </Button>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}

// =============================================================================
// Dialog · Lên đơn giao hàng
// =============================================================================
function DialogLenKeHoach({
  request,
  token,
  onClose,
  onXong,
}: {
  request: DeliveryRequest;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  // Phụ xe — TUỲ CHỌN, tối đa một người (mg 0231). Cùng danh sách với tài xế: vai trò do Ô THẢ
  // NGƯỜI VÀO quyết định, không phải thuộc tính của người. Hôm nay lái, mai đi phụ.
  const [phuXeId, setPhuXeId] = useState("");
  const [taiXe, setTaiXe] = useState<DeliveryDriverPick[]>([]);
  const [lay, setLay] = useState("");
  const [giao, setGiao] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [dangGui, setDangGui] = useState(false);

  // Bắt quản lý GÕ MÃ nhân viên là bắt họ nhớ số — sai một chữ số là phân công nhầm người mà
  // không có gì báo. Chọn trong danh sách thì không sai được.
  useEffect(() => {
    api.giaoHang.taiXeChon(token).then((r) => setTaiXe(r.items)).catch(() => setTaiXe([]));
  }, [token]);

  const gui = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      .plan(token, {
        request_id: request.id,
        employee_id: Number(employeeId),
        // KHÔNG gửi khi để trống (đừng gửi `null`): ở đường ĐỔI kế hoạch `null` nghĩa là GỠ phụ
        // xe, nên giữ hai nghĩa tách bạch ngay từ màn tạo cho khỏi lẫn về sau.
        ...(phuXeId ? { phu_xe_employee_id: Number(phuXeId) } : {}),
        gio_lay_hang: new Date(lay).toISOString(),
        gio_du_kien_giao: new Date(giao).toISOString(),
        ghi_chu_phan_cong: ghiChu || null,
      })
      .then((r) => {
        // Cảnh báo "sát giờ" KHÔNG chặn — hiện ra rồi vẫn lưu (PRD §6).
        if (r.canh_bao.length) {
          setCanhBao(r.canh_bao);
          window.setTimeout(onXong, 1500);
        } else {
          onXong();
        }
      })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không lưu được kế hoạch"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Lên đơn giao hàng · {request.code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body">
          <p>
            Lưu xong, đơn giao hàng vào tab <strong>Đơn giao hàng</strong>. Bấm{" "}
            <strong>Gửi đề nghị xuất hàng</strong> ở đó thì kho mới thấy để duyệt.
          </p>
          <label>
            Nhân viên giao
            <select className="input" value={employeeId}
              onChange={(e) => {
                setEmployeeId(e.target.value);
                // Đổi tài xế thành đúng người đang làm phụ xe ⇒ GỠ ô phụ xe. Chỉ lọc danh sách
                // là chưa đủ: giá trị cũ còn trong state, gửi lên máy chủ mới báo lỗi.
                if (e.target.value === phuXeId) setPhuXeId("");
              }}>
              <option value="">— Chọn tài xế —</option>
              {taiXe.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.full_name}
                  {t.code ? ` · ${t.code}` : ""}
                  {t.department ? ` · ${t.department}` : ""}
                  {t.co_thao_tac
                    ? ""
                    : t.co_tai_khoan === false
                      ? " — chưa có tài khoản"
                      : " — chưa bấm nút được"}
                </option>
              ))}
            </select>
          </label>
          {/* Danh sách CHỈ gồm người vào được màn Giao hàng — tài xế còn phải bấm "Đã lấy hàng"
              rồi nhập kết quả, ai không mở được màn thì nhận chuyến xong là chuyến tắc. */}
          {taiXe.length === 0 && (
            <p className="rc__sub">
              Chưa ai được cấp ô <b>Giao hàng</b> ngoài bạn. Tài xế phải có tài khoản đăng nhập và
              vai của họ phải bật ô Giao hàng, nếu không họ không bấm được “Đã lấy hàng”.
            </p>
          )}
          {/* HAI tình huống, HAI câu — gộp một câu thì người đọc không biết đi đâu sửa. */}
          {(() => {
            const nv = taiXe.find((t) => String(t.id) === employeeId);
            if (!nv || nv.co_thao_tac) return null;
            return (
              // MỘT DÒNG. Bản đầu viết cả đoạn hướng dẫn đường đi nước bước — chủ chốt bảo
              // "dài quá" (20/08/2026): cảnh báo trong form là để người ta BIẾT rồi bấm tiếp,
              // không phải để đọc tài liệu. Việc phải làm nói gọn, ai cần chi tiết thì hỏi.
              <div className="banner banner--warn" role="status">
                <b>{nv.full_name}</b>{" "}
                {nv.co_tai_khoan === false ? "chưa có tài khoản" : "chưa được cấp quyền thao tác"}
                {" "}— vẫn phân chuyến được, nhưng bạn phải bấm hộ.
              </div>
            );
          })()}
          <label>
            Phụ xe <span className="gh-opt">(không bắt buộc)</span>
            <select
              className="input"
              value={phuXeId}
              onChange={(e) => setPhuXeId(e.target.value)}
            >
              <option value="">— Đi một mình —</option>
              {taiXe
                // Bỏ chính tài xế khỏi danh sách: máy chủ chặn trùng người, nhưng bày ra rồi báo
                // lỗi là mời người ta bấm vào một cái sai.
                .filter((t) => String(t.id) !== employeeId)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name}
                    {t.code ? ` · ${t.code}` : ""}
                  </option>
                ))}
            </select>
          </label>
          <p className="rc__sub">
            Có phụ xe thì tiền chuyến chia theo tỷ lệ khai ở <b>Phòng ban</b>; đi một mình thì tài
            xế ăn trọn.
          </p>
          <label>
            Giờ lấy hàng
            <input className="input" type="datetime-local" value={lay}
              onChange={(e) => setLay(e.target.value)} />
          </label>
          <label>
            Giờ dự kiến giao
            <input className="input" type="datetime-local" value={giao}
              onChange={(e) => setGiao(e.target.value)} />
          </label>
          <label>
            Ghi chú phân công
            <input className="input" value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)} />
          </label>

          {canhBao.map((c) => (
            <div key={c} className="banner banner--warn" role="status">
              {c}
            </div>
          ))}
          {loi && (
            <div className="banner banner--error" role="alert">
              {loi}
            </div>
          )}

          <Button variant="accent" disabled={!employeeId || !lay || !giao || dangGui} onClick={gui}>
            Lưu kế hoạch
          </Button>
        </div>
      </aside>
    </div>
  );
}

// =============================================================================
// Dialog · Gửi yêu cầu xuất kho
// =============================================================================
function DialogYeuCauXuatKho({
  trip,
  token,
  onClose,
  onXong,
}: {
  trip: DeliveryTrip;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  const [hang, setHang] = useState<HangCanXuat[] | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [dangGui, setDangGui] = useState(false);

  // Dòng hàng do MÁY suy ra từ yêu cầu giao — người gửi không gõ, không sửa. Yêu cầu đã nói giao
  // cái gì bao nhiêu; cho gõ lại là mở đường cho lệch số và kho xuất nhầm hàng.
  useEffect(() => {
    api.giaoHang
      .hangCanXuat(token, trip.id)
      .then(setHang)
      .catch((e: unknown) => {
        setHang([]);
        setLoi(e instanceof Error ? e.message : "Không đọc được hàng cần xuất");
      });
  }, [token, trip.id]);

  const gui = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      // KHÔNG gửi `kho_id` (chủ 21/08/2026): người gửi không biết hàng nằm kho nào, thủ kho
      // mới biết. Màn Hộp yêu cầu bên kho vốn đã tự chọn được khi yêu cầu bỏ trống.
      .guiYeuCauXuatKho(token, trip.id, { ghi_chu: ghiChu || null })
      .then(onXong)
      .catch((e: unknown) =>
        setLoi(e instanceof Error ? e.message : "Không gửi được yêu cầu xuất kho"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Yêu cầu xuất kho · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body gh-form">
          <p className="rc__sub">
            Đây là <strong>yêu cầu xuất kho bình thường</strong> — kho lập phiếu và ghi sổ như mọi
            phiếu vật tư khác. Hàng lấy thẳng từ yêu cầu giao, <strong>không sửa được</strong>.
            {" "}<strong>Xuất từ kho nào do thủ kho chọn</strong> lúc lập phiếu.
          </p>

          {/* CHỈ XEM. Bản trước bắt gõ tay mặt hàng + số lượng ở đây — sai: yêu cầu giao đã nói
              rõ giao cái gì bao nhiêu, gõ lại là mời gõ sai. */}
          <div className="kho-lines__wrap">
            <table className="kho-lines">
              <thead className="kho-lines__head">
                <tr>
                  <th style={{ width: 28 }} />
                  <th>Mặt hàng</th>
                  <th style={{ width: 90 }}>ĐVT</th>
                  <th className="kho-num" style={{ width: 100 }}>Số lượng</th>
                </tr>
              </thead>
              <tbody>
                {hang === null && (
                  <tr>
                    <td colSpan={4}>Đang tải…</td>
                  </tr>
                )}
                {hang?.map((d, i) => (
                  <tr key={`${d.hang_loai}-${d.hang_id}`}>
                    <td className="kho-lines__code">{i + 1}</td>
                    <td>
                      <div className="kho-lines__name kho-name-clamp" title={d.hang_ten ?? ""}>
                        {d.hang_ten ?? `${d.hang_loai}#${d.hang_id}`}
                      </div>
                    </td>
                    <td className="kho-lines__code">{d.dvt}</td>
                    <td className="kho-num">{d.sl_de_nghi}</td>
                  </tr>
                ))}
                {hang?.length === 0 && (
                  <tr>
                    <td colSpan={4}>Không có hàng nào phải xuất.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <label>
            Ghi chú cho kho
            <input className="input" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} />
          </label>

          {loi && (
            <div className="banner banner--error" role="alert">
              {loi}
            </div>
          )}

          <Button
            variant="accent"
            disabled={!hang || hang.length === 0 || dangGui}
            onClick={gui}
          >
            Gửi yêu cầu xuất kho
          </Button>
        </div>
      </aside>
    </div>
  );
}

// =============================================================================
// Dialog · Nhập kết quả
// =============================================================================
/** Một dòng hàng còn phải giao TRONG PHẠM VI một yêu cầu. */
interface DongConLai {
  order_line_id: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  con: number;
}
function DialogKetQua({
  trip,
  token,
  onClose,
  onXong,
}: {
  trip: DeliveryTrip;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  const [ketQua, setKetQua] = useState<KetQuaInput["ket_qua"]>("thanh_cong");
  const [km, setKm] = useState("");
  const [nguoiNhan, setNguoiNhan] = useState("");
  const [lyDo, setLyDo] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [xacNhanKm, setXacNhanKm] = useState(false);
  // Số thực nhận TỪNG DÒNG. Bản đầu chỉ có một ô cho `lines[0]` — đơn hai mặt hàng là ghi thiếu
  // hẳn một dòng mà không ai báo.
  const [nhan, setNhan] = useState<Record<number, string>>({});
  const [conLai, setConLai] = useState<DongConLai[]>([]);

  // Đọc từ CHÍNH YÊU CẦU, không phải từ đơn: chuyến này chỉ giao phần của yêu cầu đó, và phần
  // "còn lại" phải trừ những lần giao trước của cùng yêu cầu — đúng phép máy chủ đang tính.
  useEffect(() => {
    api.giaoHang
      .request(token, trip.request_id)
      .then((d) => {
        const ds = d.request.lines
          .map((l) => ({
            order_line_id: l.order_line_id,
            mo_ta: l.mo_ta,
            don_vi_tinh: l.don_vi_tinh,
            con: l.qty - l.da_giao,
          }))
          .filter((l) => l.con > 0);
        setConLai(ds);
        setNhan(Object.fromEntries(ds.map((l) => [l.order_line_id, String(l.con)])));
      })
      .catch(() => setConLai([]));
  }, [token, trip.request_id]);

  const gui = () => {
    setLoi(null);
    const body: KetQuaInput = {
      ket_qua: ketQua,
      km: Number(km),
      xac_nhan_km_lon: xacNhanKm,
    };
    if (ketQua === "thanh_cong" || ketQua === "giao_thieu") body.nguoi_nhan_thuc_te = nguoiNhan;
    if (ketQua === "giao_thieu")
      body.so_thuc_nhan = conLai.map((l) => ({
        order_line_id: l.order_line_id,
        qty: Number(nhan[l.order_line_id] ?? 0),
      }));
    if (ketQua === "that_bai") {
      body.ly_do_that_bai = lyDo;
      // Chỉ còn MỘT hướng xử lý (22/08/2026): hàng về kho. "Chờ giao lại" giữ hàng trên xe trong
      // khi sổ kho ghi đã xuất — chính chỗ đó che mất lỗi "trả hàng về không vào sổ".
      body.huong_xu_ly = "tra_ve";
    }
    api.giaoHang
      .ghiKetQua(token, trip.id, body)
      .then(onXong)
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Không ghi được kết quả";
        setLoi(msg);
        // Km lớn bất thường là chặn MỀM — hiện nút xác nhận thay vì bắt gõ lại.
        if (msg.includes("bất thường")) setXacNhanKm(false);
      });
  };

  const kmLon = Number(km) > 500;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Kết quả · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body">
          <label>
            Kết quả
            <select className="input" value={ketQua}
              onChange={(e) => setKetQua(e.target.value as KetQuaInput["ket_qua"])}>
              <option value="thanh_cong">Giao thành công</option>
              <option value="giao_thieu">Giao thiếu</option>
              {/* "Khách hẹn lại" GỠ 22/08/2026: nó là trạng thái treo — chuyến chưa xong mà cũng
                  không kết thúc, hàng nằm trên xe không biết tới bao giờ. Khách hẹn lại thì chọn
                  "Giao thất bại", hàng về kho, rồi lập YÊU CẦU MỚI cho ngày hẹn. */}
              <option value="that_bai">Giao thất bại</option>
            </select>
          </label>

          <label>
            Số km thực tế
            {/* `type="number"` chứ KHÔNG phải `inputMode` — inputMode chỉ đổi bàn phím điện
                thoại, bàn phím máy tính vẫn gõ chữ vào được. `min=0` vì 0 km là số THẬT. */}
            <input className="input" type="number" min="0" step="1" value={km}
              onChange={(e) => setKm(e.target.value)} />
          </label>
          {/* 0 km là số THẬT (xe chưa lăn bánh) — không chặn. Chỉ hỏi lại khi lớn bất thường. */}
          {kmLon && (
            <label className="gh-line">
              <input type="checkbox" checked={xacNhanKm}
                onChange={(e) => setXacNhanKm(e.target.checked)} />
              {" "}Xác nhận {km} km là đúng
            </label>
          )}

          {/* SỐ LƯỢNG THỰC NHẬN hiện ở CẢ HAI kết quả. Trước đây chọn "Giao thành công" thì
              máy tự điền, người bấm không thấy mình đang xác nhận bao nhiêu — mà đây là con số
              cộng thẳng vào "đã giao" của đơn hàng. */}
          {(ketQua === "thanh_cong" || ketQua === "giao_thieu") && (
            <fieldset className="gh-pick">
              <legend>
                {ketQua === "thanh_cong" ? "Khách nhận đủ" : "Số khách thực nhận"}
              </legend>
              {conLai.length === 0 && <p className="rc__sub">Không còn hàng nào để giao.</p>}
              {conLai.map((l) => (
                <div key={l.order_line_id} className="gh-pick__row">
                  <span className="gh-pick__tick">
                    <span>
                      {l.mo_ta}
                      <em> · còn {l.con} {l.don_vi_tinh}</em>
                    </span>
                  </span>
                  <input
                    className="input gh-pick__qty"
                    type="number" min="0" step="1" max={l.con}
                    // Thành công = nhận đủ ⇒ khoá ô, chỉ để XEM. Muốn sửa số thì đổi kết quả
                    // sang "Giao thiếu" — để lựa chọn nằm ở dropdown, không nằm ở việc gõ số.
                    disabled={ketQua === "thanh_cong"}
                    aria-label={`Số thực nhận — ${l.mo_ta ?? ""}`}
                    value={ketQua === "thanh_cong" ? String(l.con) : (nhan[l.order_line_id] ?? "")}
                    onChange={(e) =>
                      setNhan((p) => ({ ...p, [l.order_line_id]: e.target.value }))
                    }
                  />
                </div>
              ))}
            </fieldset>
          )}

          {(ketQua === "thanh_cong" || ketQua === "giao_thieu") && (
            <label>
              Người nhận hàng
              <input className="input" value={nguoiNhan}
                onChange={(e) => setNguoiNhan(e.target.value)} />
            </label>
          )}

          {ketQua === "that_bai" && (
            <>
              <label>
                Lý do thất bại
                <input className="input" value={lyDo} onChange={(e) => setLyDo(e.target.value)} />
              </label>
              {/* Không còn ô chọn: chỉ một hướng. Nói TRƯỚC hệ quả, đừng để người dùng phát
                  hiện sau khi bấm. */}
              <p className="rc__sub">
                Hàng sẽ được <strong>trả về kho</strong>. Muốn giao lại thì lập
                {" "}<strong>yêu cầu giao mới</strong>.
              </p>
            </>
          )}

          {loi && (
            <div className="banner banner--error" role="alert">
              {loi}
            </div>
          )}

          <Button variant="accent" disabled={km === ""} onClick={gui}>
            Lưu kết quả
          </Button>
        </div>
      </aside>
    </div>
  );
}
