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
//
// Shell (tách từ pages/GiaoHangPage.tsx): state + `load()` + `goi()` + `moChiTiet()` + bộ tab +
// chỗ mount ba bảng, drawer và ba hộp thoại.
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  DeliveryDriver,
  DeliveryRequest,
  DeliveryRequestDetail,
  DeliveryTrip,
} from "../../../api/client";
import { api } from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { Button } from "../../../components/Button";
import { Icon } from "../../../components/Icons";
import { DrawerChiTiet } from "./components/DrawerChiTiet";
import { DialogKetQua } from "./modals/DialogKetQua";
import { DialogLenKeHoach } from "./modals/DialogLenKeHoach";
import { DialogYeuCauXuatKho } from "./modals/DialogYeuCauXuatKho";
import { BangChoLenKeHoach } from "./tabs/BangChoLenKeHoach";
import { BangKeHoach } from "./tabs/BangKeHoach";
import { BangNhanVien } from "./tabs/BangNhanVien";
import { gopTheoYeuCau } from "./shared/helpers";
import type { TabId } from "./shared/types";
import "../../rebuild-catalog.css";
import "../../giao-hang.css";
import "../../kho-request.css";

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
