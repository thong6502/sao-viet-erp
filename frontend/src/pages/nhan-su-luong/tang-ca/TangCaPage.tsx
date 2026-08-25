// Màn Tăng ca (module `tang_ca`) — 2 tab:
//   • Phiếu của tôi — NV tự gửi phiếu, theo dõi trạng thái, tự hủy khi chưa được duyệt.
//   • Duyệt phiếu   — tổ trưởng/HCNS duyệt (chọn nhiều → duyệt cả mẻ). Scope `department` nên tổ
//                     trưởng CHỈ thấy người trong tổ mình.
// Nguyên tắc (chốt với chủ 23/07/2026): phiếu = GIẤY PHÉP + MỨC TRẦN. Lượt bấm RA mới quyết tiền,
// nên màn này KHÔNG nhập giờ làm thực — chỉ khai khoảng được phép tăng ca.
// (tách từ pages/TangCaPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type OvertimeRequest } from "../../../api/client";
import { useCan, useSelfService } from "../../../auth/permissions";
import { useAuth } from "../../../auth/useAuth";
import { Button } from "../../../components/Button";
import { Pager, trangHopLe } from "../../../components/Pager";
import { RowActionButton } from "../../../components/RowActionButton";
import { RequestTable } from "./components/RequestTable";
import { OvertimeFormModal } from "./modals/OvertimeFormModal";
import { RejectModal } from "./modals/RejectModal";
import { PAGE_SIZE } from "./shared/constants";
import { errText } from "./shared/helpers";
import type { Tab } from "./shared/types";
import "../../nhan-su.css";
import "../../tang-ca.css";

// --- Màn chính ---------------------------------------------------------------

export function TangCaPage({
  onChanged,
  eventTick,
}: {
  onChanged?: () => void;
  /** Tăng theo mỗi sự kiện real-time (SSE) → tải lại bảng NGAY khi bên kia duyệt/từ chối/gửi phiếu. */
  eventTick?: number;
}) {
  const { token: authToken } = useAuth();
  const token = authToken ?? ""; // AppShell chỉ render màn này sau khi đăng nhập
  const can = useCan();
  const canApprove = can("tang_ca", "approve");
  // Ô TỰ PHỤC VỤ (đợt 3) — quản trị TẮT ĐƯỢC. Không hỏi thì tắt xong nút vẫn bày ra, bấm
  // mới ăn 403: trông như hệ thống hỏng chứ không như "anh không có quyền".
  const tuPhucVu = useSelfService();
  // Ô THAO TÁC của Tự phục vụ — TÁCH khỏi ô Xem ngày 11/08/2026. Tab/danh sách đi theo ô
  // Xem; còn nút GỬI · SỬA · HUỶ thì đi theo ô này.
  // GHI LÀ GHI — gửi / sửa / huỷ đơn của CHÍNH MÌNH vẫn đòi ô Thao tác của màn Tăng ca
  // (chủ chốt 15/08/2026: *"tôi chưa bật thao tác vẫn bấm gửi đơn được nè"*). Chỉ phần ĐỌC dữ
  // liệu của mình mới là quyền đương nhiên.
  const tuPhucVuGhi = can("tang_ca", "create");
  const [tab, setTab] = useState<Tab>(canApprove && !tuPhucVu ? "approve" : "mine");
  const [mine, setMine] = useState<OvertimeRequest[]>([]);
  const [mineTotal, setMineTotal] = useState(0);
  const [minePage, setMinePage] = useState(1);
  const [hasEmployee, setHasEmployee] = useState(true);
  const [queue, setQueue] = useState<OvertimeRequest[]>([]);
  const [queueTotal, setQueueTotal] = useState(0);
  const [queuePage, setQueuePage] = useState(1);
  /** Số phiếu CHỜ DUYỆT trong phạm vi — đếm ở DB qua `/api/overtime/summary`, KHÔNG đếm mảng
   *  `queue` đã tải. Sau phân trang mảng đó chỉ còn 20 dòng của trang, đếm nó ra số của trang
   *  và cái nhãn "Duyệt phiếu (N)" thành nói dối (badge sidebar báo 47, tab báo 20). */
  const [pendingCount, setPendingCount] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState<null | "mine" | "for">(null);
  const [editing, setEditing] = useState<OvertimeRequest | null>(null);
  const [rejecting, setRejecting] = useState<null | number[]>(null);
  /** Lỗi THAO TÁC (duyệt / hủy / từ chối) → băng đỏ trên đầu màn, bảng vẫn còn dữ liệu. */
  const [err, setErr] = useState<string | null>(null);
  // Hai bảng = hai lần gọi máy chủ ĐỘC LẬP ⇒ mỗi bảng một cặp "đang tải / lỗi tải" riêng.
  // Dùng chung một ô nhớ thì hàng đợi duyệt hỏng cũng làm bảng phiếu của tôi biến mất.
  const [loadingMine, setLoadingMine] = useState(true);
  const [errMine, setErrMine] = useState<string | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [errQueue, setErrQueue] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoadingMine(true);
    setErrMine(null);
    api.overtime
      .mine(token, { page: minePage, size: PAGE_SIZE })
      .then((r) => {
        setHasEmployee(r.has_employee);
        setMine(r.items ?? []);
        setMineTotal(r.total);
        // Hủy nốt phiếu cuối của trang 3 ⇒ chỉ còn 2 trang: nhảy về trang cuối còn thật.
        const trangCanVe = trangHopLe(minePage, r.total, PAGE_SIZE);
        if (trangCanVe !== null) setMinePage(trangCanVe);
      })
      .catch((e) => setErrMine(errText(e)))
      .finally(() => setLoadingMine(false));
    if (canApprove) {
      setLoadingQueue(true);
      setErrQueue(null);
      // ⚠️ PHẢI truyền `statusFilter: "pending"` — bỏ ra là hàng đợi này VÔ DỤNG.
      //
      // Backend sắp xếp theo `status` tăng dần, mà giá trị là CHUỖI THƯỜNG nên thứ tự chữ cái là
      // approved < cancelled < pending < rejected: phiếu ĐÃ DUYỆT đứng trước, phiếu CHỜ DUYỆT bị
      // đẩy xuống cuối. Trước khi có phân trang thì cả 200 dòng nằm chung một bảng nên cuộn xuống
      // vẫn thấy; cắt còn 20 dòng/trang là trang 1 sạch bóng phiếu chờ duyệt, trong khi tab vẫn
      // ghi "Duyệt phiếu (3)" và tiêu đề bảng vẫn ghi "Phiếu chờ duyệt".
      // Tổ trưởng mở ra thấy toàn phiếu đã duyệt, tưởng hết việc rồi bỏ đi.
      api.overtime
        .list(token, {
          statusFilter: "pending",
          page: queuePage,
          size: PAGE_SIZE,
        })
        .then((r) => {
          setQueue(r.items);
          setQueueTotal(r.total);
          const trangCanVe = trangHopLe(queuePage, r.total, PAGE_SIZE);
          if (trangCanVe !== null) setQueuePage(trangCanVe);
        })
        .catch((e) => setErrQueue(errText(e)))
        .finally(() => setLoadingQueue(false));
      // Số trên nút tab lấy từ CÙNG nguồn với badge sidebar ⇒ hai chỗ không bao giờ vênh nhau.
      api.overtime
        .summary(token)
        .then((s) => setPendingCount(s.pending_in_scope ?? 0))
        .catch(() => undefined);
    }
    api.overtime.markSeen(token).catch(() => undefined);
    onChanged?.(); // badge sidebar + chuông cập nhật ngay sau mỗi thao tác
  }, [token, canApprove, onChanged, minePage, queuePage]);

  // `eventTick` đổi = có sự kiện real-time → tải lại bảng, khỏi bắt người dùng F5.
  useEffect(() => {
    load();
  }, [load, eventTick]);

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      setSelected(new Set());
      load();
    } catch (e) {
      setErr(errText(e));
    }
  }

  return (
    <div className="ns">
      {/* `.ns__head` là flex ngang: để `h1` và đoạn mô tả làm HAI con trực tiếp thì chúng
          nằm cạnh nhau, không phải trên–dưới. Bọc chung một `<div>` cho khớp mọi màn khác
          trong nhóm (Hồ sơ nhân sự / Nghỉ phép / Nội quy) rồi mới thêm eyebrow. */}
      <header className="ns__head">
        <div>
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="ns__title">Tăng ca</h1>
          <p className="ns__sub">
            Muốn tính tiền tăng ca thì phải có phiếu được duyệt. Không có phiếu
            vẫn <b>đủ công ca chính</b> — chỉ phần giờ vượt ca là không ra tiền.
          </p>
        </div>
      </header>

      {err && <div className="banner banner--error">{err}</div>}

      <div className="tc-tabs">
        {tuPhucVu && (
          <button
            className={`btn ${tab === "mine" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setTab("mine")}
          >
            Phiếu của tôi
          </button>
        )}
        {canApprove && (
          <button
            className={`btn ${tab === "approve" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setTab("approve")}
          >
            Duyệt phiếu{pendingCount ? ` (${pendingCount})` : ""}
          </button>
        )}
      </div>

      {tab === "mine" && tuPhucVu && (
        <>
          <div className="cc-toolbar">
            <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
              Phiếu tăng ca của tôi
            </h4>
            {/* Hành động chính của tab → cam. Hai tab không bao giờ hiện cùng lúc nên màn
                vẫn chỉ có ĐÚNG một nút cam. */}
            {hasEmployee && tuPhucVuGhi && (
              <Button variant="accent" onClick={() => setCreating("mine")}>
                + Gửi phiếu
              </Button>
            )}
          </div>
          {!hasEmployee ? (
            <div className="tc-note">
              <span>
                Tài khoản của bạn chưa gắn hồ sơ nhân viên nên chưa gửi phiếu
                được.
              </span>
            </div>
          ) : (
            <RequestTable
              rows={mine}
              showEmployee={false}
              selectable={false}
              selected={selected}
              onToggle={toggle}
              loading={loadingMine}
              listError={errMine}
              onRetry={load}
              emptyTitle="Chưa có phiếu tăng ca nào"
              emptySub="Bấm “+ Gửi phiếu” để xin khoảng được phép tăng ca."
              actions={(r) =>
                r.status === "pending" || r.status === "approved" ? (
                  <>
                    {r.status === "pending" && (
                      <RowActionButton
                        dense
                        label="Sửa phiếu"
                        icon="pencil"
                        onClick={() => setEditing(r)}
                      />
                    )}
                    {/* GIỮ `danger`: hủy phiếu đã duyệt là mất luôn giấy phép tăng ca. */}
                    <RowActionButton
                      dense
                      danger
                      label="Hủy phiếu"
                      icon="x"
                      onClick={() => run(() => api.overtime.cancel(token, r.id))}
                    />
                  </>
                ) : null
              }
            />
          )}
          {/* Chân bảng CHỈ hiện khi có dòng (chuẩn §2.7) — lúc tải/lỗi/rỗng thì khối trong
              bảng đã nói hết rồi. */}
          {hasEmployee && !loadingMine && !errMine && mine.length > 0 && (
            <Pager
              total={mineTotal}
              page={minePage}
              size={PAGE_SIZE}
              loading={loadingMine}
              unit="phiếu"
              onPage={setMinePage}
            />
          )}
        </>
      )}

      {tab === "approve" && canApprove && (
        <>
          <div className="cc-toolbar">
            <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
              Phiếu chờ duyệt trong phạm vi của bạn
            </h4>
            <Button variant="accent" onClick={() => setCreating("for")}>
              + Tạo hộ thợ
            </Button>
          </div>
          {selected.size > 0 && (
            <div className="tc-bulkbar">
              <span>Đã chọn {selected.size} phiếu</span>
              <button
                className="btn btn--primary"
                onClick={() =>
                  run(() => api.overtime.bulkApprove(token, [...selected]))
                }
              >
                Duyệt tất cả
              </button>
              <button
                className="btn btn--ghost ns-danger"
                onClick={() => setRejecting([...selected])}
              >
                Từ chối tất cả
              </button>
            </div>
          )}
          <RequestTable
            rows={queue}
            showEmployee
            selectable
            selected={selected}
            onToggle={toggle}
            loading={loadingQueue}
            listError={errQueue}
            onRetry={load}
            emptyTitle="Chưa có phiếu nào trong phạm vi của bạn"
            emptySub="Thợ gửi phiếu tăng ca thì việc sẽ hiện ở đây."
            actions={(r) =>
              r.status === "pending" ? (
                <>
                  <RowActionButton
                    dense
                    label="Duyệt"
                    icon="check"
                    onClick={() => run(() => api.overtime.approve(token, r.id))}
                  />
                  <RowActionButton
                    dense
                    danger
                    label="Từ chối"
                    icon="ban"
                    onClick={() => setRejecting([r.id])}
                  />
                </>
              ) : null
            }
          />
          {!loadingQueue && !errQueue && queue.length > 0 && (
            <Pager
              total={queueTotal}
              page={queuePage}
              size={PAGE_SIZE}
              loading={loadingQueue}
              unit="phiếu"
              onPage={setQueuePage}
              // "Duyệt tất cả / Từ chối tất cả" chạy trên `selected`, mà ô tick chỉ có ở dòng
              // của trang đang xem ⇒ nói thẳng giới hạn đó, đừng để tổ trưởng tưởng đã dọn
              // sạch cả hàng đợi.
              note={queueTotal > PAGE_SIZE ? "duyệt hàng loạt chỉ áp cho trang đang xem" : undefined}
            />
          )}
        </>
      )}

      {creating && (
        <OvertimeFormModal
          token={token}
          forEmployee={creating === "for"}
          onClose={() => setCreating(null)}
          onSaved={() => {
            setCreating(null);
            load();
          }}
        />
      )}
      {editing && (
        <OvertimeFormModal
          token={token}
          forEmployee={false}
          editing={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {rejecting && (
        <RejectModal
          count={rejecting.length}
          onClose={() => setRejecting(null)}
          onConfirm={(note) => {
            const ids = rejecting;
            setRejecting(null);
            run(() =>
              ids.length > 1
                ? api.overtime.bulkReject(token, ids, note)
                : api.overtime.reject(token, ids[0], note),
            );
          }}
        />
      )}
    </div>
  );
}
