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
// Tab "Đơn giao hàng" là danh sách KHỐI (18/09/2026): mỗi LƯỢT XE một khối đủ các điểm, thao tác
// cả lượt nằm ngay trên khối (`KhoiLuot`); chuyến ngoài lượt một thẻ gọn.
//
// Shell (tách từ pages/GiaoHangPage.tsx): state + `load()` + `moChiTiet()` + bộ tab + chỗ mount ba
// bảng, drawer chi tiết và ba hộp thoại.
import { useCallback, useEffect, useState } from "react";
import type {
  BangGiaoItem,
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
import { DialogDoiChuyen } from "./modals/DialogDoiChuyen";
import { DialogKetQua } from "./modals/DialogKetQua";
import { DialogLenKeHoach } from "./modals/DialogLenKeHoach";
import { DialogYeuCauXuatKho } from "./modals/DialogYeuCauXuatKho";
import { BangChoLenKeHoach } from "./tabs/BangChoLenKeHoach";
import { BangKeHoach } from "./tabs/BangKeHoach";
import { BangNhanVien } from "./tabs/BangNhanVien";
import type { TabId } from "./shared/types";
import "../../rebuild-catalog.css";
import "../../giao-hang.css";
import "../../kho-request.css";

// Phân trang máy chủ (CLAUDE.md/best-practice, khớp Đơn hàng bán + Tính giá). Tab Đơn giao hàng
// đếm theo KHỐI (một lượt = một khối), không theo đơn.
const PAGE_SIZE = 20;
// Tab "Yêu cầu giao" lọc theo TRẠNG THÁI TÍNH (nhiều bảng, không phải cột thô) nên không trang
// hoá được ở SQL — lấy một CỬA SỔ 200 yêu cầu mới nhất rồi lọc/trang ở FE, giống Đơn hàng bán.
// Nếu quá 200 yêu cầu đang "chờ lên kế hoạch" cùng lúc thì badge/đếm có thể thiếu — chấp nhận vì
// hàng chờ lên kế hoạch bình thường không tồn đọng lớn vậy.
const CLIENT_FILTER_WINDOW = 200;

export default function GiaoHangPage({ eventTick = 0 }: { eventTick?: number }) {
  const { token } = useAuth();
  const can = useCan();
  const canPlan = can("giao_hang", "plan");
  const canViewDrivers = can("giao_hang", "view_drivers");
  const canWrite = can("giao_hang", "create");
  const canCancel = can("giao_hang", "cancel");

  const [tab, setTab] = useState<TabId>("ke-hoach");
  const [khoi, setKhoi] = useState<BangGiaoItem[]>([]);
  const [khoiPage, setKhoiPage] = useState(1);
  const [khoiTotal, setKhoiTotal] = useState(0);
  const [soDon, setSoDon] = useState(0);
  const [choLenKeHoachRows, setChoLenKeHoachRows] = useState<DeliveryRequest[]>([]);
  const [reqPage, setReqPage] = useState(1);
  const [reqTotal, setReqTotal] = useState(0);
  const [drivers, setDrivers] = useState<DeliveryDriver[]>([]);
  const [detail, setDetail] = useState<DeliveryRequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Lên đơn: MỘT yêu cầu (nút ở dòng) hoặc NHIỀU yêu cầu chung một lượt xe (tick + "Lên lượt xe").
  const [planFor, setPlanFor] = useState<
    { requests: DeliveryRequest[]; theoLuot: boolean } | null
  >(null);
  // Lượt vừa lập — khối của nó được làm nổi + cuộn tới (bước kế tiếp: gửi yêu cầu xuất kho).
  const [luotMoi, setLuotMoi] = useState<number | null>(null);
  const [ketQuaFor, setKetQuaFor] = useState<DeliveryTrip | null>(null);
  const [xuatKhoFor, setXuatKhoFor] = useState<DeliveryTrip | null>(null);
  const [doiFor, setDoiFor] = useState<DeliveryTrip | null>(null);
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
      api.giaoHang
        .bangGiao(token, { page: khoiPage, size: PAGE_SIZE })
        .then((r) => {
          setKhoi(r.items);
          setKhoiTotal(r.total);
          setSoDon(r.so_don);
        }),
      api.giaoHang
        .requests(token, { page: 1, size: CLIENT_FILTER_WINDOW })
        .then((r) => {
          const loc = r.items.filter((x) => x.trang_thai === "cho_len_ke_hoach");
          setReqTotal(loc.length);
          setChoLenKeHoachRows(loc.slice((reqPage - 1) * PAGE_SIZE, reqPage * PAGE_SIZE));
        }),
    ];
    // Tab nào không có ô thì KHÔNG gọi — gọi rồi nuốt 403 là che mất lỗi cấu hình thật.
    if (canViewDrivers)
      viec.push(api.giaoHang.nhanVien(token, { thang }).then((r) => setDrivers(r.items)));
    Promise.all(viec)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Không tải được dữ liệu"))
      .finally(() => setLoading(false));
    // `thang` PHẢI có ở đây — thiếu thì đổi tháng mà bảng đứng im.
  }, [token, canViewDrivers, thang, khoiPage, reqPage]);

  // `eventTick` tăng mỗi sự kiện SSE ⇒ bảng tự tải lại. Tài xế không phải F5 để biết kho đã
  // soạn xong hàng chưa (CLAUDE.md: gửi/thông báo nội bộ phải tức thì).
  useEffect(() => {
    load();
  }, [load, eventTick]);

  // Nổi một lúc rồi thôi — để lâu thì khối đó trông như "có gì bất thường".
  useEffect(() => {
    if (luotMoi == null) return;
    const h = window.setTimeout(() => setLuotMoi(null), 6000);
    return () => window.clearTimeout(h);
  }, [luotMoi]);

  const khoiTotalPages = Math.max(1, Math.ceil(khoiTotal / PAGE_SIZE));
  const reqTotalPages = Math.max(1, Math.ceil(reqTotal / PAGE_SIZE));

  /** Gọi một hành động rồi tải lại; lỗi hiện lên banner thay vì nuốt im. Trả Promise để nút tự
   *  khoá tới khi lệnh xong (bấm hai lần liền là hai lệnh). */
  const lam = useCallback(
    (viec: Promise<unknown>, loiMacDinh: string) =>
      viec
        .then(load)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : loiMacDinh)),
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
    { id: "ke-hoach", label: "Đơn giao hàng", count: soDon, hien: true },
    {
      id: "cho-len-ke-hoach",
      label: "Yêu cầu giao",
      count: reqTotal,
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
          <span className="rc__count">{soDon} đơn giao</span>
        </div>
        <p className="rc__sub">
          Yêu cầu từ Bán hàng → lên đơn giao hàng (nhiều đơn chung một lượt xe) → gửi yêu cầu xuất
          kho → tài xế lấy hàng và giao.
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

      {tabDang === "ke-hoach" && token && (
        <BangKeHoach items={khoi} loading={loading} token={token}
          canPlan={canPlan} canWrite={canWrite} luotMoi={luotMoi} onDoi={load} onMo={moChiTiet}
          onKetQua={canWrite ? setKetQuaFor : undefined}
          onGuiDeNghi={canPlan ? setXuatKhoFor : undefined}
          onDaLay={canWrite
            ? (t) => lam(api.giaoHang.daLayHang(token, t.id), "Không ghi được đã lấy hàng")
            : undefined}
          onBatDau={canWrite
            ? (t) => lam(api.giaoHang.batDauGiao(token, t.id), "Không bắt đầu giao được")
            : undefined}
          onDaTra={canWrite
            ? (t) => lam(api.giaoHang.daTraHang(token, t.id), "Không lập được phiếu trả kho")
            : undefined}
          onDoiChuyen={canPlan ? setDoiFor : undefined}
        />
      )}
      {tabDang === "ke-hoach" && !loading && khoi.length > 0 && (
        <div className="gh-pager">
          <span className="gh-pager__info">
            Tổng {soDon} đơn giao · Trang {khoiPage}/{khoiTotalPages}
          </span>
          <div className="gh-pager__btns">
            <button type="button" className="gh-pager__btn" disabled={khoiPage <= 1}
              onClick={() => setKhoiPage((p) => Math.max(1, p - 1))}>
              Trước
            </button>
            <button type="button" className="gh-pager__btn" disabled={khoiPage >= khoiTotalPages}
              onClick={() => setKhoiPage((p) => Math.min(khoiTotalPages, p + 1))}>
              Sau
            </button>
          </div>
        </div>
      )}

      {tabDang === "cho-len-ke-hoach" && (
        <BangChoLenKeHoach rows={choLenKeHoachRows} loading={loading} onMo={moChiTiet}
          onLenKeHoach={(r) => setPlanFor({ requests: [r], theoLuot: false })}
          onLenLuot={(rs) => setPlanFor({ requests: rs, theoLuot: true })} />
      )}
      {tabDang === "cho-len-ke-hoach" && !loading && choLenKeHoachRows.length > 0 && (
        <div className="gh-pager">
          <span className="gh-pager__info">
            Tổng {reqTotal} yêu cầu · Trang {reqPage}/{reqTotalPages}
          </span>
          <div className="gh-pager__btns">
            <button type="button" className="gh-pager__btn" disabled={reqPage <= 1}
              onClick={() => setReqPage((p) => Math.max(1, p - 1))}>
              Trước
            </button>
            <button type="button" className="gh-pager__btn" disabled={reqPage >= reqTotalPages}
              onClick={() => setReqPage((p) => Math.min(reqTotalPages, p + 1))}>
              Sau
            </button>
          </div>
        </div>
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
          requests={planFor.requests}
          theoLuot={planFor.theoLuot}
          token={token}
          onClose={() => setPlanFor(null)}
          onXong={(luotId) => {
            setPlanFor(null);
            // Lên lượt xong ⇒ về tab Đơn giao hàng, khối lượt đó nổi lên: bước kế tiếp (gửi yêu
            // cầu xuất kho cả lượt) nằm ngay trên khối.
            if (luotId != null) {
              setTab("ke-hoach");
              setKhoiPage(1);
              setLuotMoi(luotId);
            }
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

      {doiFor && token && (
        <DialogDoiChuyen
          trip={doiFor}
          token={token}
          onClose={() => setDoiFor(null)}
          onXong={() => {
            setDoiFor(null);
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
