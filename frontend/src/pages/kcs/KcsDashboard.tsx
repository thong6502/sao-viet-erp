// Màn KCS (KCS theo lệnh, mg 0306) — KPI strip + filter bar + 3 biểu đồ, đọc từ `GET /kcs/bao-cao`.
//
// KPI lấy THẲNG từ response BE (tong_luot/tong_dat/tong_loi/ty_le_dat) — KHÔNG tính lại ở FE.
//
// Dữ liệu `bao-cao` do `KcsTheoLenhPage` GỌI rồi truyền xuống: cùng một response còn nuôi bảng
// "Kết quả đã ghi" (khoá `lich_su`) — để mỗi bên tự gọi là hai lượt mạng cho cùng bộ lọc, và hai
// khối có thể lệch nhau một nhịp. Loại lần kiểm (routing/đột xuất/điểm kiểm) ĐÃ GỠ: nay chỉ còn
// một kiểu "kiểm công đoạn".
import { type SxKcsBaoCao, type SxKcsCongDoanLoc } from "../../api/client";
import { MonthBars, MixDonut } from "../../components/charts";
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

function fmtNgay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function KcsDashboard({
  filters, onFiltersChange, congDoanOpts, data, loading, error,
}: {
  filters: KcsDashFilters;
  onFiltersChange: (f: KcsDashFilters) => void;
  /** Danh sách công đoạn cho dropdown lọc — fetch ở `KcsTheoLenhPage` (dùng chung để lọc cả bảng
   *  "Kết quả đã ghi"), truyền xuống đây thay vì fetch trùng lần thứ hai. */
  congDoanOpts: SxKcsCongDoanLoc[];
  /** Response `GET /kcs/bao-cao` do trang cha giữ — người KCS thấy mọi tổ. */
  data: SxKcsBaoCao | null;
  loading: boolean;
  error: string | null;
}) {

  const congDoanOptions: SelectOption<number | null>[] = [
    { value: null, label: "Tất cả công đoạn" },
    ...congDoanOpts.map((c) => ({ value: c.id, label: `${c.ma} · ${c.ten}` })),
  ];

  const theoNgay = data?.theo_ngay ?? [];
  const to = data?.to ?? [];
  const congDoan = data?.cong_doan ?? [];

  return (
    <section className="kcs-dash">
      <div className="rc__filterbar kcs-dash__filters">
        <input
          type="date" value={filters.tu} aria-label="Từ ngày"
          onChange={(e) => onFiltersChange({ ...filters, tu: e.target.value })}
        />
        <input
          type="date" value={filters.den} aria-label="Đến ngày"
          onChange={(e) => onFiltersChange({ ...filters, den: e.target.value })}
        />
        <Select
          value={filters.congDoanId} options={congDoanOptions}
          onChange={(v) => onFiltersChange({ ...filters, congDoanId: v })}
        />
        <input
          type="text" placeholder="Mã đơn/LSX" value={filters.tuKhoa}
          onChange={(e) => onFiltersChange({ ...filters, tuKhoa: e.target.value })}
        />
      </div>

      {error ? (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
        </div>
      ) : (
        <>
          <div className="kcs-dash__strip">
            <div className="kcs-dash__seg">
              <span className="kcs-dash__label">Tổng lượt</span>
              <span className="kcs-dash__val">{loading ? "…" : num(data?.tong_luot ?? 0)}</span>
            </div>
            <div className="kcs-dash__seg">
              <span className="kcs-dash__label">Tổng đạt</span>
              <span className="kcs-dash__val">{loading ? "…" : num(data?.tong_dat ?? 0)}</span>
            </div>
            <div className="kcs-dash__seg">
              <span className="kcs-dash__label">Tổng lỗi</span>
              <span className="kcs-dash__val">{loading ? "…" : num(data?.tong_loi ?? 0)}</span>
            </div>
            <div className="kcs-dash__seg">
              <span className="kcs-dash__label">Tỷ lệ đạt</span>
              <span className="kcs-dash__val">
                {loading ? "…" : data?.ty_le_dat != null ? `${(data.ty_le_dat * 100).toFixed(1)}%` : "—"}
              </span>
            </div>
          </div>

          <div className="kcs-dash__charts">
            <div className="kcs-dash__chart">
              <h3>Xu hướng lỗi theo ngày</h3>
              {theoNgay.length === 0 ? (
                <p className="rc__empty-text">Chưa có dữ liệu.</p>
              ) : (
                <MonthBars
                  data={theoNgay.map((r) => ({
                    label: fmtNgay(r.ngay),
                    value: r.tong_loi,
                    sub: `Đạt ${num(r.tong_dat)}`,
                  }))}
                  height={200}
                  formatValue={(v) => `${num(v)} lỗi`}
                  formatAxis={(v) => num(v)}
                />
              )}
            </div>
            <div className="kcs-dash__chart">
              {/* Trước đây là "Nhóm lỗi nhiều nhất"; danh mục Lý do & lỗi SX ĐÃ GỠ (mg 0288) nên
                  lỗi chỉ còn mô tả tự do — gom nhóm chuỗi tự do là thống kê nói dối. Ô này chuyển
                  sang bảng xếp hạng TỔ mà báo cáo vẫn tính nhưng chưa chỗ nào vẽ. */}
              <h3>Tổ bị ghi lỗi nhiều nhất</h3>
              {to.length === 0 ? (
                <p className="rc__empty-text">Chưa có lỗi nào.</p>
              ) : (
                <MixDonut
                  slices={to.map((r) => ({ label: r.ten, value: r.tong_so_luong }))}
                  centerTop={num(to.reduce((s, r) => s + r.tong_so_luong, 0))}
                  centerBottom="lỗi"
                  formatValue={(v) => num(v)}
                  height={140}
                />
              )}
            </div>
            <div className="kcs-dash__chart">
              <h3>Công đoạn bị ghi lỗi nhiều nhất</h3>
              {congDoan.length === 0 ? (
                <p className="rc__empty-text">Chưa có lỗi nào.</p>
              ) : (
                <MixDonut
                  slices={congDoan.map((r) => ({ label: r.ten_cong_doan, value: r.tong_so_luong }))}
                  centerTop={num(congDoan.reduce((s, r) => s + r.tong_so_luong, 0))}
                  centerBottom="lỗi"
                  formatValue={(v) => num(v)}
                  height={140}
                />
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
