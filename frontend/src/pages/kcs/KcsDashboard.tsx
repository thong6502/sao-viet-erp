// Màn KCS (KCS theo lệnh, mg 0306) — phần báo cáo, đọc từ `GET /kcs/bao-cao`.
//
// Bố cục (18/09/2026, theo mẫu dashboard kiểm tra chất lượng): một thẻ KPI chạy ngang trên cùng,
// dưới là lưới hai cột — cột trái là bảng lệnh (trang cha truyền vào qua `bangLenh`) + xu hướng lỗi
// theo ngày, cột phải là "Lỗi theo công đoạn" (thanh ngang) và "Lỗi theo tổ" (donut).
// Bộ lọc báo cáo (`KcsBaoCaoLoc`) nằm trên dải tiêu đề trang, cạnh nút Xuất Excel dùng chung bộ lọc.
//
// KPI lấy THẲNG từ response BE (tong_luot/tong_nhan/tong_dat/tong_loi/ty_le_dat) — KHÔNG tính lại ở FE.
//
// Dữ liệu `bao-cao` do `KcsTheoLenhPage` GỌI rồi truyền xuống (trang cha giữ bộ lọc, tải lại khi
// có sự kiện). Loại lần kiểm (routing/đột xuất/điểm kiểm) ĐÃ GỠ: nay chỉ còn một kiểu "kiểm công
// đoạn".
import type { ReactNode } from "react";
import { type SxKcsBaoCao, type SxKcsCongDoanLoc } from "../../api/client";
import { MonthBars, MixDonut } from "../../components/charts";
import { Icon, type IconName } from "../../components/Icons";
import { Select, type SelectOption } from "../../components/Select";
import { num } from "../keHoachSxShared";

export interface KcsDashFilters {
  tu: string;
  den: string;
  congDoanId: number | null;
  tuKhoa: string;
}

export const KCS_DASH_FILTERS_RONG: KcsDashFilters = {
  tu: "", den: "", congDoanId: null, tuKhoa: "",
};

/** Số công đoạn hiện thanh ở cột phải — dài hơn thì gộp phần đuôi thành một dòng đếm. */
const SO_THANH_CONG_DOAN = 6;

function fmtNgay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function phanTram(tyLe: number): string {
  return `${(tyLe * 100).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`;
}

/** Bộ lọc báo cáo — nằm trên dải tiêu đề trang. Lọc KPI + biểu đồ + file Excel, KHÔNG lọc bảng lệnh
 *  (bảng lệnh có ô tìm riêng). */
export function KcsBaoCaoLoc({
  filters, onFiltersChange, congDoanOpts,
}: {
  filters: KcsDashFilters;
  onFiltersChange: (f: KcsDashFilters) => void;
  /** Danh sách công đoạn cho dropdown lọc — fetch ở `KcsTheoLenhPage`. */
  congDoanOpts: SxKcsCongDoanLoc[];
}) {
  const congDoanOptions: SelectOption<number | null>[] = [
    { value: null, label: "Tất cả công đoạn" },
    ...congDoanOpts.map((c) => ({ value: c.id, label: `${c.ma} · ${c.ten}` })),
  ];
  return (
    <div className="kcs-loc" role="group" aria-label="Lọc báo cáo KCS">
      <div className="kcs-loc__ngay">
        <Icon name="calendar" size={14} className="kcs-loc__ngay-ic" />
        <input
          type="date" value={filters.tu} aria-label="Từ ngày" max={filters.den || undefined}
          onChange={(e) => onFiltersChange({ ...filters, tu: e.target.value })}
        />
        <span className="kcs-loc__ngay-sep" aria-hidden="true">–</span>
        <input
          type="date" value={filters.den} aria-label="Đến ngày" min={filters.tu || undefined}
          onChange={(e) => onFiltersChange({ ...filters, den: e.target.value })}
        />
      </div>
      <div className="kcs-loc__cd">
        <Select
          value={filters.congDoanId} options={congDoanOptions} ariaLabel="Lọc theo công đoạn"
          onChange={(v) => onFiltersChange({ ...filters, congDoanId: v })}
        />
      </div>
      <input
        className="kcs-loc__ma" type="text" placeholder="Mã đơn / lệnh" value={filters.tuKhoa}
        aria-label="Lọc theo mã đơn hoặc mã lệnh"
        onChange={(e) => onFiltersChange({ ...filters, tuKhoa: e.target.value })}
      />
    </div>
  );
}

interface KpiO {
  id: string;
  icon: IconName;
  tone: "amber" | "moss" | "rust" | "steel";
  nhan: string;
  giaTri: string;
  phu?: string;
}

/** Danh sách thanh ngang "Lỗi theo công đoạn": tên + số trên một dòng, thanh bên dưới — tên dài
 *  vẫn đọc trọn, không bị cắt như nhãn trục của biểu đồ. */
function ThanhLoi({ rows }: { rows: { ten: string; so: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.so));
  const tong = rows.reduce((s, r) => s + r.so, 0) || 1;
  const hien = rows.slice(0, SO_THANH_CONG_DOAN);
  const conLai = rows.slice(SO_THANH_CONG_DOAN);
  return (
    <ul className="kcs-thanh">
      {hien.map((r) => (
        <li key={r.ten} className="kcs-thanh__it">
          <div className="kcs-thanh__dau">
            <span className="kcs-thanh__ten">{r.ten}</span>
            <span className="kcs-thanh__so">
              {num(r.so)}<span className="kcs-thanh__pt">{Math.round((r.so / tong) * 100)}%</span>
            </span>
          </div>
          <div className="kcs-thanh__ray" aria-hidden="true">
            <span className="kcs-thanh__day" style={{ width: `${(r.so / max) * 100}%` }} />
          </div>
        </li>
      ))}
      {conLai.length > 0 && (
        <li className="kcs-thanh__them">
          và {conLai.length} công đoạn khác · {num(conLai.reduce((s, r) => s + r.so, 0))} lỗi
        </li>
      )}
    </ul>
  );
}

export function KcsDashboard({
  data, loading, error, bangLenh,
}: {
  /** Response `GET /kcs/bao-cao` do trang cha giữ — người KCS thấy mọi tổ. */
  data: SxKcsBaoCao | null;
  loading: boolean;
  error: string | null;
  /** Thẻ bảng lệnh — nằm ở cột trái, ngay dưới dải KPI. */
  bangLenh: ReactNode;
}) {
  const theoNgay = data?.theo_ngay ?? [];
  const to = data?.to ?? [];
  const congDoan = data?.cong_doan ?? [];
  const tongLoi = data?.tong_loi ?? 0;
  const dangTaiLanDau = loading && data == null;
  /** Câu thay biểu đồ khi không có gì để vẽ — phân biệt đang tải / lỗi tải / thật sự rỗng. */
  const trong = (rong: string) => (dangTaiLanDau ? "Đang tải…" : error ? "Không tải được báo cáo." : rong);

  const kpi: KpiO[] = [
    {
      id: "luot", icon: "clipboard", tone: "steel", nhan: "Lượt kiểm",
      giaTri: num(data?.tong_luot ?? 0),
      phu: data && data.tong_nhan > 0 ? `${num(data.tong_nhan)} đã kiểm` : undefined,
    },
    { id: "dat", icon: "fileCheck", tone: "moss", nhan: "Đạt", giaTri: num(data?.tong_dat ?? 0) },
    { id: "loi", icon: "alert", tone: "rust", nhan: "Lỗi", giaTri: num(tongLoi) },
    {
      id: "ty_le", icon: "activity", tone: "amber", nhan: "Tỷ lệ đạt",
      giaTri: data?.ty_le_dat != null ? phanTram(data.ty_le_dat) : "—",
    },
  ];

  return (
    <div className="kcs-dash">
      {error ? (
        <div className="banner banner--error" role="alert"><span>{error}</span></div>
      ) : (
        <section className="kcs-kpi" aria-label="Chỉ số KCS theo bộ lọc">
          {kpi.map((k) => (
            <div key={k.id} className={`kcs-kpi__o${k.id === "loi" && tongLoi > 0 ? " is-loi" : ""}`}>
              <span className={`kcs-kpi__ic kcs-kpi__ic--${k.tone}`}><Icon name={k.icon} size={16} /></span>
              <div className="kcs-kpi__than">
                <span className="kcs-kpi__nhan">{k.nhan}</span>
                <span className="kcs-kpi__so">{loading && data == null ? "…" : k.giaTri}</span>
                {k.phu && <span className="kcs-kpi__phu">{k.phu}</span>}
              </div>
            </div>
          ))}
        </section>
      )}

      <div className="kcs-dash__luoi">
        <div className="kcs-dash__trai">
          {bangLenh}

          <section className="kcs-the">
            <header className="kcs-the__dau">
              <h3>Xu hướng lỗi theo ngày</h3>
              {theoNgay.length > 0 && <span className="kcs-the__phu">{theoNgay.length} ngày có kiểm</span>}
            </header>
            {theoNgay.length === 0 ? (
              <p className="kcs-the__trong">{trong("Chưa có lần kiểm nào trong khoảng này.")}</p>
            ) : (
              <MonthBars
                data={theoNgay.map((r) => ({
                  label: fmtNgay(r.ngay),
                  value: r.tong_loi,
                  sub: `Đạt ${num(r.tong_dat)}`,
                }))}
                height={180}
                formatValue={(v) => `${num(v)} lỗi`}
                formatAxis={(v) => num(v)}
              />
            )}
          </section>
        </div>

        <aside className="kcs-dash__phai" aria-label="Phân bổ lỗi">
          <section className="kcs-the">
            <header className="kcs-the__dau">
              <h3>Lỗi theo công đoạn</h3>
            </header>
            {congDoan.length === 0 ? (
              <p className="kcs-the__trong">{trong("Chưa ghi lỗi nào.")}</p>
            ) : (
              <ThanhLoi rows={congDoan.map((r) => ({ ten: r.ten_cong_doan, so: r.tong_so_luong }))} />
            )}
          </section>

          <section className="kcs-the">
            {/* Trước đây là "Nhóm lỗi nhiều nhất"; danh mục Lý do & lỗi SX ĐÃ GỠ (mg 0288) nên
                lỗi chỉ còn mô tả tự do — gom nhóm chuỗi tự do là thống kê nói dối. Ô này xếp hạng
                TỔ mà báo cáo vẫn tính. */}
            <header className="kcs-the__dau">
              <h3>Lỗi theo tổ</h3>
            </header>
            {to.length === 0 ? (
              <p className="kcs-the__trong">{trong("Chưa ghi lỗi nào.")}</p>
            ) : (
              <MixDonut
                stacked
                slices={to.map((r) => ({ label: r.ten, value: r.tong_so_luong }))}
                centerTop={num(to.reduce((s, r) => s + r.tong_so_luong, 0))}
                centerBottom="lỗi"
                formatValue={(v) => `${num(v)} lỗi`}
                height={150}
              />
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
