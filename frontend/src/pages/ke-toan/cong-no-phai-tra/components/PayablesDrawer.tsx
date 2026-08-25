// Drawer CHI TIẾT công nợ một nhà cung cấp (tách từ pages/AccountingPayablesPage.tsx).
// Hai khối con — "Đợt giao còn nợ" và "Đã trả" — là hai <section> anh em, giữ nguyên thứ tự.
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type PayablesDetail } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import type { NavigateFn } from "../../../../components/AppShell";
import { money } from "../../../../utils/format";
import { BUCKET_LABEL, PAID_PAGE } from "../shared/constants";
import type { Bucket } from "../shared/types";
import { DaTraBlock } from "./DaTraBlock";
import { DotConNoBlock } from "./DotConNoBlock";

export function PayablesDrawer({
  supplierId,
  supplierName,
  bucket,
  canCreateVoucher,
  navigate,
  onClose,
  onChanged,
}: {
  supplierId: number;
  supplierName: string;
  bucket: Bucket;
  canCreateVoucher: boolean;
  navigate: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<PayablesDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Bucket>(bucket);
  // Rổ ✅ mặc định THU GỌN. Mở sẵn khi người dùng bấm thẳng vào con số "Đã trả".
  const [paidOpen, setPaidOpen] = useState(bucket === "paid");
  const [paidShown, setPaidShown] = useState(PAID_PAGE);
  // Nới rổ "đã chi" ra toàn bộ lịch sử. NCC trả hết từ 5 tháng trước thì rổ này rỗng theo kỳ —
  // tra ra "không nợ" mà không thấy đã trả những gì. Nới chỉ cho MỘT NCC nên vẫn nhẹ.
  const [xemHetLichSu, setXemHetLichSu] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .payablesDetail(token, supplierId, xemHetLichSu)
      .then(setDetail)
      .catch((err) => {
        setDetail(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Không tải được chi tiết công nợ.",
        );
      })
      .finally(() => setLoading(false));
  }, [token, supplierId, xemHetLichSu]);

  // Drawer chỉ-xem: Esc để đóng (trước đây do DetailModal lo, nay drawer tự nghe).
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hienNo = tab === "all" || tab === "overdue";
  const khoanNo = useMemo(() => {
    const items = detail?.items ?? [];
    return tab === "overdue" ? items.filter((x) => x.overdue_days > 0) : items;
  }, [detail, tab]);
  // Server đã sắp: đợt chưa có hạn lên ĐẦU, còn lại theo hạn trả tăng dần. Không sắp lại ở đây —
  // sắp hai nơi là hai nơi lệch nhau.
  const chuaDatHan = useMemo(
    () => (detail?.items ?? []).filter((x) => x.chua_dat_han).length,
    [detail],
  );
  const conDuocNo = detail
    ? Math.max(0, detail.credit_limit - detail.total_due)
    : 0;

  return (
    <div className="rc-drawer__scrim" onClick={onClose}>
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={supplierName}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Công nợ phải trả</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{supplierName}</h2>
                {detail?.vuot_han_muc ? (
                  <span className="pay-badge pay-badge--danger">
                    Vượt hạn mức {money(detail.vuot_bao_nhieu)}
                  </span>
                ) : null}
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={onClose}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            {detail && (
              <>
                <span>Đang nợ {money(detail.total_due)}</span>
                {detail.overdue_amount > 0 && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>Quá hạn {money(detail.overdue_amount)}</span>
                  </>
                )}
                <span className="purchase__hero-dot">•</span>
                <span>Hạn mức {detail.credit_limit > 0 ? money(detail.credit_limit) : "Chưa đặt"}</span>
              </>
            )}
          </div>
        </div>
        <div className="rc-drawer__body">
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      {loading && <p>Đang tải...</p>}

      {/* Chặn TRẮNG TRANG khi backend cũ hơn giao diện: thiếu `items`/`paid` là `.length` ném lỗi
          và React gỡ nguyên cây, mất cả màn. Báo rõ ra thay vì sập — và cũng không im lặng coi như
          danh sách rỗng, vì rỗng có nghĩa khác hẳn. */}
      {detail && !(Array.isArray(detail.items) && Array.isArray(detail.paid)) && (
        <div className="banner banner--error" role="alert">
          Dữ liệu trả về thiếu phần công nợ theo đợt giao — máy chủ đang chạy
          bản cũ hơn giao diện. Khởi động lại backend rồi tải lại trang.
        </div>
      )}

      {detail && Array.isArray(detail.items) && Array.isArray(detail.paid) && (
        <>
          {/* HẠN MỨC đứng trên cùng: đây là khung để đọc mọi con số bên dưới. Chưa đặt hạn mức thì
              nói thẳng "chưa đặt", đừng hiện 0đ — 0 trông như "hạn mức bằng không". */}
          <dl className="pay-credit">
            <div>
              <dt>Hạn mức công nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(detail.credit_limit)
                ) : (
                  <span className="pay-cell--zero">Chưa đặt</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Đang nợ</dt>
              <dd className={detail.vuot_han_muc ? "pay-cell--danger" : ""}>
                {money(detail.total_due)}
              </dd>
            </div>
            <div>
              <dt>Còn được nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(conDuocNo)
                ) : (
                  <span className="pay-cell--zero">Không giới hạn</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Số ngày cho nợ</dt>
              <dd>
                {/* 0 và "chưa đặt" là HAI ca khác hẳn — gộp là hiểu sai cả cột Quá hạn. */}
                {detail.credit_days == null ? (
                  <span className="pay-cell--zero">Chưa đặt</span>
                ) : detail.credit_days === 0 ? (
                  "Trả ngay"
                ) : (
                  `${detail.credit_days} ngày`
                )}
              </dd>
            </div>
          </dl>

          <div className="pay-pills pay-pills--drawer">
            {(["all", "overdue"] as Bucket[]).map((id) => (
              <button
                key={id}
                type="button"
                className={`pay-pill${tab === id ? " pay-pill--on" : ""}`}
                onClick={() => setTab(id)}
              >
                {BUCKET_LABEL[id]}
              </button>
            ))}
          </div>

          {hienNo && (
            <DotConNoBlock
              detail={detail}
              tab={tab}
              khoanNo={khoanNo}
              chuaDatHan={chuaDatHan}
              canCreateVoucher={canCreateVoucher}
              navigate={navigate}
              onClose={onClose}
              onChanged={onChanged}
            />
          )}

          <DaTraBlock
            detail={detail}
            paidOpen={paidOpen}
            setPaidOpen={setPaidOpen}
            paidShown={paidShown}
            setPaidShown={setPaidShown}
            setXemHetLichSu={setXemHetLichSu}
          />
        </>
      )}
        </div>
      </aside>
    </div>
  );
}
