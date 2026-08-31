// KCS kiêm nhiệm (mg 0250) — KPI strip + filter bar + 3 biểu đồ, đọc từ `GET /api/san-xuat/kcs/bao-cao`.
//
// Task 9 dựng KHUNG này đã TỰ HOẠT ĐỘNG (gọi đúng API, hiện đúng số) — KHÔNG phải placeholder.
// Task 10 sẽ hợp nhất filter này với bảng "Kết quả đã ghi" + nút Xuất Excel về một state chung nếu
// cần (xem docs/design-kcs-kiem-nhiem-ui.md mục 7); ở đây filter đang là NGUỒN RIÊNG cho dashboard.
//
// KPI lấy THẲNG từ response BE (tong_luot/tong_dat/tong_loi/ty_le_dat) — KHÔNG tính lại ở FE.
import { useEffect, useState } from "react";
import { ApiError, api, type SxKcsBaoCao, type SxKcsBatchLoai, type CongDoanLite } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { MonthBars, MixDonut } from "../../components/charts";
import { Select, type SelectOption } from "../../components/Select";
import { num } from "../keHoachSxShared";

export interface KcsDashFilters {
  tu: string;
  den: string;
  loai: SxKcsBatchLoai | null;
  congDoanId: number | null;
  tuKhoa: string;
}

export const KCS_DASH_FILTERS_RONG: KcsDashFilters = {
  tu: "", den: "", loai: null, congDoanId: null, tuKhoa: "",
};

const LOAI_OPTIONS: SelectOption<SxKcsBatchLoai | null>[] = [
  { value: null, label: "Tất cả loại" },
  { value: "routing", label: "Routing" },
  { value: "dot_xuat", label: "Đột xuất" },
];

function fmtNgay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function KcsDashboard({
  teamId, filters, onFiltersChange, refreshKey,
}: {
  /** Tổ đang mở màn — mặc định phạm vi báo cáo về ĐÚNG tổ này (header "KCS · Tổ …"), không gộp
   *  toàn nhà máy. Không phơi ra ô lọc riêng (đúng "bộ lọc gọn" §6.2) vì đã ngầm định bởi trang. */
  teamId: number;
  filters: KcsDashFilters;
  onFiltersChange: (f: KcsDashFilters) => void;
  /** Đổi giá trị (page bump sau mỗi lần "Lưu kết quả") ⇒ gọi lại `bao-cao` dù filters không đổi —
   *  nếu không KPI/biểu đồ đứng yên sau khi vừa ghi kết quả (chỉ 2 bảng Chờ/Đã ghi tự làm mới). */
  refreshKey?: number;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<SxKcsBaoCao | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [congDoanOpts, setCongDoanOpts] = useState<CongDoanLite[]>([]);

  useEffect(() => {
    if (!token) return;
    api.congDoan.list(token).then((r) => setCongDoanOpts(r.items)).catch(() => setCongDoanOpts([]));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api.sanXuat.baoCaoKcs(token, {
      tu: filters.tu || null,
      den: filters.den || null,
      kcs_department_id: teamId,
      tu_khoa: filters.tuKhoa || null,
      cong_doan_id: filters.congDoanId,
      loai: filters.loai,
    })
      .then((r) => { if (alive) { setData(r); setLoading(false); } })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof ApiError ? e.message : "Không tải được báo cáo KCS.");
        setLoading(false);
      });
    return () => { alive = false; };
  }, [token, teamId, filters.tu, filters.den, filters.tuKhoa, filters.congDoanId, filters.loai, refreshKey]);

  const congDoanOptions: SelectOption<number | null>[] = [
    { value: null, label: "Tất cả công đoạn" },
    ...congDoanOpts.map((c) => ({ value: c.id, label: `${c.ma} · ${c.ten}` })),
  ];

  const theoNgay = data?.theo_ngay ?? [];
  const nhomLoi = data?.nhom_loi ?? [];
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
          value={filters.loai} options={LOAI_OPTIONS}
          onChange={(v) => onFiltersChange({ ...filters, loai: v })}
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
              <h3>Nhóm lỗi nhiều nhất</h3>
              {nhomLoi.length === 0 ? (
                <p className="rc__empty-text">Chưa có lỗi nào.</p>
              ) : (
                <MixDonut
                  slices={nhomLoi.map((r) => ({ label: r.ten, value: r.tong_so_luong }))}
                  centerTop={num(nhomLoi.reduce((s, r) => s + r.tong_so_luong, 0))}
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
