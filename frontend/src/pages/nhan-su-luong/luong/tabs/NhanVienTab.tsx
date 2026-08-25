// Tab Lương nhân viên (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, type EmployeeRow } from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";
import { RowActionButton } from "../../../../components/RowActionButton";
import { errText } from "../shared/helpers";
import { SalaryModal } from "../modals/SalaryModal";

// --- Tab: Lương nhân viên ---------------------------------------------------

export function NhanVienTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  focusEmployeeId?: number;
}) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<EmployeeRow | null>(null);
  // Ba ca của bảng: đang tải · rỗng thật · gọi hỏng. `listErr` CHỈ giữ lỗi TẢI DANH SÁCH.
  const [listErr, setListErr] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);

  const load = useCallback(() => {
    setListLoading(true);
    api.employees
      .list(token, { size: 200, sort: "code" })
      .then((r) => {
        setEmps(r.items);
        setListErr(null);
      })
      // Trước đây nuốt lỗi rồi gán [] ⇒ bảng in "không có nhân viên" trong khi thật ra là gọi
      // hỏng. Giữ nguyên danh sách cũ và nói đúng ca `lỗi`.
      .catch((e) => setListErr(errText(e)))
      .finally(() => setListLoading(false));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Liên thông: khi mở từ Hồ sơ NV, tự bật modal lương của NV đó — CHỈ MỘT LẦN cho mỗi
  // focusEmployeeId. Không dùng ref-guard thì reload danh sách sau khi Đóng sẽ mở lại modal
  // (dep `emps` đổi) → tưởng "không đóng được".
  const autoOpenedFor = useRef<number | null>(null);
  useEffect(() => {
    if (
      focusEmployeeId &&
      emps.length &&
      autoOpenedFor.current !== focusEmployeeId
    ) {
      const e = emps.find((x) => x.id === focusEmployeeId);
      if (e) {
        setPicked(e);
        autoOpenedFor.current = focusEmployeeId;
      }
    }
  }, [focusEmployeeId, emps]);

  const shown = emps.filter(
    (e) =>
      !q ||
      e.full_name.toLowerCase().includes(q.toLowerCase()) ||
      e.code.includes(q),
  );

  return (
    <div>
      <div className="cc-toolbar">
        <div className="lg-search-wrapper">
          <span className="lg-search-icon">
            <Search size={14} />
          </span>
          <input
            className="lg-search-input"
            placeholder="Tìm theo tên / mã…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className="lg-emp-table-wrapper">
        <table className="ns__table">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Họ tên</th>
              <th>Vị trí</th>
              <th>Trạng thái</th>
              {/* "Thao tác" — tên cột thống nhất toàn hệ, KHÔNG dùng "Hành động". */}
              <th className="lg-actcol">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => {
              const statusLabels: Record<
                string,
                { label: string; className: string }
              > = {
                probation: {
                  label: "Thử việc",
                  className: "ns-badge ns-badge--warn",
                },
                // Vẫn ăn lương thử việc ⇒ bộ lọc "Thử việc" phía trên vẫn gom người này vào
                // (nó lọc theo `is_probation` của dòng lương, không theo trạng thái hồ sơ).
                probation_ended: {
                  label: "Hết thử việc · chờ xác nhận",
                  className: "ns-badge ns-badge--due",
                },
                active: {
                  label: "Chính thức",
                  className: "ns-badge ns-badge--ok",
                },
                on_leave: {
                  label: "Nghỉ phép",
                  className: "ns-badge ns-badge--info",
                },
                suspended: {
                  label: "Tạm đình chỉ",
                  className: "ns-badge ns-badge--danger",
                },
                resigned: {
                  label: "Đã thôi việc",
                  className: "ns-badge ns-badge--muted",
                },
              };
              const statusInfo = statusLabels[e.status] ?? {
                label: e.status,
                className: "ns-badge ns-badge--muted",
              };
              return (
                <tr key={e.id}>
                  <td className="ns__code">{e.code}</td>
                  <td>
                    <b>{e.full_name}</b>
                  </td>
                  <td>{e.position ?? "—"}</td>
                  <td>
                    <span className={statusInfo.className}>
                      {statusInfo.label}
                    </span>
                  </td>
                  {/* Nút chữ trên dòng → `RowActionButton` dạng dense (icon + tooltip) như mọi
                      bảng khác của hệ. Nhãn vẫn là "Thiết lập lương" — nó thành aria-label và
                      nội dung tooltip, không mất chữ cho người đọc màn hình. */}
                  <td className="lg-rowact">
                    <RowActionButton
                      dense
                      label="Thiết lập lương"
                      icon="settings"
                      onClick={() => setPicked(e)}
                    />
                  </td>
                </tr>
              );
            })}
            {shown.length === 0 && (
              <EmptyRow
                colSpan={5}
                trangThai={listErr ? "loi" : listLoading ? "dang-tai" : "rong"}
                loi={listErr}
                onThuLai={load}
                icon="users"
                title={
                  emps.length ? "Chưa có ai khớp từ khoá" : "Chưa có nhân viên"
                }
                sub={
                  emps.length
                    ? "Thử gõ ngắn hơn, hoặc tìm bằng mã nhân viên."
                    : "Khai hồ sơ ở màn Nhân sự trước, rồi quay lại thiết lập lương."
                }
                action={
                  emps.length ? (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => setQ("")}
                    >
                      Xoá từ khoá
                    </button>
                  ) : undefined
                }
              />
            )}
          </tbody>
        </table>
      </div>
      {picked && (
        <SalaryModal
          token={token}
          emp={picked}
          onClose={() => {
            setPicked(null);
            load();
          }}
        />
      )}
    </div>
  );
}
