// Bảng phiếu của tab Tạm ứng — MỘT TRANG (50 dòng) đã lọc (25/09/2026). Ô tick đầu bảng chọn / bỏ
// cả trang đang xem; muốn chọn qua mọi trang thì dùng "Chọn tất cả N phiếu đang lọc" ở thanh chọn.
import type { Dispatch, SetStateAction } from "react";
import type { SalaryAdvance } from "../../../../api/client";
import type { NavigateFn } from "../../../../components/AppShell";
import { money } from "../shared/helpers";
import { KIND, STATUS, TamUngHanhDong } from "./TamUngHanhDong";

export function TamUngBang({
  rows,
  coCotChon,
  chon,
  setChon,
  navigate,
  canApproveAdvance,
  canLapPhieuChi,
  act,
  token,
  onLapPhieuChi,
}: {
  rows: SalaryAdvance[];
  coCotChon: boolean;
  chon: Set<number>;
  setChon: Dispatch<SetStateAction<Set<number>>>;
  /** Chỉ truyền khi người xem có ô xem Phiếu chi — chip mã PC mới bấm sang Kế toán được. */
  navigate?: NavigateFn;
  canApproveAdvance: boolean;
  canLapPhieuChi: boolean;
  act: (fn: () => Promise<unknown>) => void;
  token: string;
  onLapPhieuChi: (a: SalaryAdvance) => void;
}) {
  const heTrang = rows.length > 0 && rows.every((a) => chon.has(a.id));

  function doiChon(id: number) {
    setChon((cu) => {
      const moi = new Set(cu);
      if (moi.has(id)) moi.delete(id);
      else moi.add(id);
      return moi;
    });
  }

  function doiCaTrang(bat: boolean) {
    setChon((cu) => {
      const moi = new Set(cu);
      for (const a of rows) {
        if (bat) moi.add(a.id);
        else moi.delete(a.id);
      }
      return moi;
    });
  }

  return (
    <div className="lg-emp-table-wrapper">
      <table className="ns__table">
        <thead>
          <tr>
            {coCotChon && (
              <th className="lg-tu-chon__o">
                <input
                  type="checkbox"
                  aria-label="Chọn cả trang này"
                  title="Chọn / bỏ cả trang đang xem"
                  checked={heTrang}
                  disabled={rows.length === 0}
                  onChange={(e) => doiCaTrang(e.target.checked)}
                />
              </th>
            )}
            <th>Mã</th>
            <th>Nhân viên</th>
            <th>Loại</th>
            <th>Ngày ứng</th>
            <th className="lg-num">Số tiền</th>
            <th>Lý do</th>
            <th>Trạng thái</th>
            {/* "Thao tác" — tên cột thống nhất toàn hệ, KHÔNG dùng "Hành động". */}
            <th className="lg-actcol">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const [label, cls] = STATUS[a.status] ?? [a.status, "ns-badge--muted"];
            const [kLabel, kCls] = KIND[a.kind] ?? KIND.tam_ung;
            const pc =
              a.phieu_chi_id && a.phieu_chi_code
                ? { id: a.phieu_chi_id, code: a.phieu_chi_code }
                : null;
            return (
              <tr key={a.id} className={chon.has(a.id) ? "is-selected" : undefined}>
                {coCotChon && (
                  <td className="lg-tu-chon__o">
                    <input
                      type="checkbox"
                      aria-label={`Chọn phiếu của ${a.employee_name ?? a.id}`}
                      checked={chon.has(a.id)}
                      onChange={() => doiChon(a.id)}
                    />
                  </td>
                )}
                <td>{a.code ?? "—"}</td>
                <td>
                  <b>{a.employee_name ?? `NV#${a.employee_id}`}</b>
                  {a.employee_code && <div className="lg-tu-ma">{a.employee_code}</div>}
                </td>
                <td>
                  <span className={`ns-badge ${kCls}`}>{kLabel}</span>
                </td>
                <td>{a.advance_date}</td>
                <td className="lg-num">{money(a.amount)}đ</td>
                <td>{a.reason ?? "—"}</td>
                <td>
                  <span className={`ns-badge ${cls}`}>{label}</span>
                </td>
                <TamUngHanhDong
                  a={a}
                  pc={pc}
                  navigate={navigate}
                  canApproveAdvance={canApproveAdvance}
                  canLapPhieuChi={canLapPhieuChi}
                  act={act}
                  token={token}
                  onLapPhieuChi={onLapPhieuChi}
                />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
