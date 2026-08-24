// TAB THEO LỆNH SẢN XUẤT — cân đối vật tư và giữ chỗ theo từng lệnh.
// Thanh lọc + tìm kiếm, hai chế độ xem (bảng dòng chảy ↔ thẻ), và drawer bóc tách.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CanDoiKhoaDong,
  type CanDoiMau,
  type DeNghiMuaXemTruoc,
  type HangLoai,
  type TheoLenhHang,
  type TheoLenhOut,
  type TheoLenhRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon, type IconName } from "../components/Icons";
import { BangLoi, ChipGap, EmptyState, Skeleton, ngay, num } from "./keHoachSxShared";
import { moTaPhieuMua, tomTatPhieuMua, vetDangKep } from "./phieuMuaNhan";

/** Nhãn ngắn & màu cho trạng thái vật tư.
 *  Màu lấy THẲNG từ biến hệ thống (tokens.css) chứ không gõ mã hex tại chỗ — gõ tay thì màn này
 *  trôi khỏi bảng màu chung, đúng cái đã xảy ra: nền/chữ ở đây từng là hệ Tailwind rời. Hai ô
 *  `bg`/`text` cũ không nơi nào đọc (đã grep) nên bỏ; nền/chữ do lớp `cls` lo. */
const MAU_VATTU: Record<string, { label: string; cls: string; dotColor: string }> = {
  xam: { label: "Đã cấp", cls: "khvt-stream-chip--xam", dotColor: "var(--ash-2)" },
  xanh: { label: "Đủ tồn", cls: "khvt-stream-chip--xanh", dotColor: "var(--moss)" },
  vang: { label: "Chờ hàng về", cls: "khvt-stream-chip--vang", dotColor: "var(--amber)" },
  do: { label: "Thiếu cần mua", cls: "khvt-stream-chip--do", dotColor: "var(--signal)" },
  khong_ro: { label: "Chưa rõ ĐVT", cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" },
  ve_muon: { label: "Hàng về muộn", cls: "khvt-stream-chip--vemuon", dotColor: "var(--rust)" },
};

function mauVatTu(mau: CanDoiMau) {
  return MAU_VATTU[mau] ?? { label: String(mau), cls: "khvt-stream-chip--khongro", dotColor: "var(--steel)" };
}

function iconLoaiHang(loai: HangLoai): IconName {
  if (loai === "giay") return "fileText";
  return "box";
}

function nhanLoaiHang(loai: HangLoai): { label: string; cls: string } {
  if (loai === "giay") return { label: "Giấy", cls: "khvt-tag--giay" };
  return { label: "Vật tư", cls: "khvt-tag--phu" };
}

function soGoc(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** Món ĐÃ đặt mua rồi nhưng lô về SAU ngày cần. Đây là lý do DUY NHẤT khiến một lệnh đang thiếu
 *  hàng lại không có nút "Mua": server chặn mua thêm để khỏi mua đúp đúng lô đang trên đường về. */
function monVeMuon(r: { hang: TheoLenhHang[] }): TheoLenhHang[] {
  return r.hang.filter((h) => h.trang_thai === "ve_muon");
}

/** Lô về trễ mấy ngày so với mốc món đó cần. null khi thiếu một trong hai mốc. */
function soNgayTre(h: TheoLenhHang): number | null {
  if (!h.ngay_du_hang || !h.ngay_can) return null;
  const a = new Date(h.ngay_du_hang).getTime();
  const b = new Date(h.ngay_can).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((a - b) / 86_400_000);
}

/** Một dòng gọn cho món về muộn: "PMH-VT-02 · về 1/9 · trễ 6 ngày". */
function moTaVeMuon(h: TheoLenhHang): string {
  const tre = soNgayTre(h);
  return [
    h.phieu_ve ?? null,
    `về ${ngay(h.ngay_du_hang)}`,
    tre != null && tre > 0 ? `trễ ${tre} ngày` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Câu giải thích vì sao nút mua bị khoá — phải GỌI TÊN phiếu và ngày về. Nút biến mất không một
 *  lời nào thì người dùng đọc thành "phần mềm hỏng", đúng câu hỏi đã nhận ngày 20/08/2026. */
function lyDoKhoaMua(hs: TheoLenhHang[]): string {
  const ke = hs.slice(0, 3).map((h) => `• ${h.hang_ten ?? h.hang_ma ?? "Vật tư"}: ${moTaVeMuon(h)}`);
  const them = hs.length > 3 ? `\n• …và ${hs.length - 3} món nữa` : "";
  return (
    "Đã đặt mua rồi — mua thêm là MUA ĐÚP đúng lô đang về:\n" +
    ke.join("\n") +
    them +
    "\nViệc cần làm: dời bước tiêu thụ sang sau ngày về, hoặc hối nhà cung cấp giao sớm."
  );
}

function khoaChu(r: { lsx_id: number | null; bai_ghep_id: number | null }): string {
  return r.lsx_id != null ? `l${r.lsx_id}` : `b${r.bai_ghep_id}`;
}

type FilterLenhType = "all" | "du" | "dang" | "tat" | "giu_lau";
type ViewMode = "table" | "cards";

export function GiuChoTheoLenhView({
  eventTick,
  canDeNghiMua,
  onOpenLsx,
  onSoGiuLau,
  focusLsxMa,
  onMoFormMua,
}: {
  eventTick?: number;
  canDeNghiMua: boolean;
  onOpenLsx?: (id: number) => void;
  onSoGiuLau?: (n: number) => void;
  focusLsxMa?: string | null;
  /** Mở form "Tạo yêu cầu mua hàng" đã điền sẵn — xem `VatTuKeHoachView`. Hai cách nhìn của cùng
   *  một bảng thì bấm Mua phải ra cùng một chỗ, không thể bên mở form bên tự lập phiếu. */
  onMoFormMua?: (nhap: DeNghiMuaXemTruoc) => void;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<TheoLenhOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState(focusLsxMa ?? "");
  const [filterType, setFilterType] = useState<FilterLenhType>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [dangChay, setDangChay] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [hoiNha, setHoiNha] = useState<TheoLenhRow | null>(null);
  const [selectedRow, setSelectedRow] = useState<TheoLenhRow | null>(null);

  useEffect(() => {
    if (focusLsxMa) setQ(focusLsxMa);
  }, [focusLsxMa]);

  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.keHoachVatTu
      .theoLenh(token, {
        q: q.trim() || undefined,
        chi_can_lo: filterType === "dang" || filterType === "tat",
        chi_giu_lau: filterType === "giu_lau",
      })
      .then(setData)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, q, filterType]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, eventTick, q]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 6000);
    return () => clearTimeout(t);
  }, [flash]);

  const soGiuLau = data?.so_giu_lau ?? 0;
  useEffect(() => {
    if (data) onSoGiuLau?.(soGiuLau);
  }, [data, soGiuLau, onSoGiuLau]);

  function thayThe(moi: TheoLenhRow) {
    setData((cu) => {
      if (!cu) return cu;
      const k = khoaChu(moi);
      const items = cu.items.map((r) => (khoaChu(r) === k ? { ...r, ...moi } : r));
      return {
        ...cu,
        items,
        so_giu_lau: items.filter((r) => r.giu_lau_chua_chay).length,
      };
    });
    if (selectedRow && khoaChu(selectedRow) === khoaChu(moi)) {
      setSelectedRow(moi);
    }
  }

  function doiGiuCho(r: TheoLenhRow, bat: boolean) {
    if (!bat) setHoiNha(r);
    else void chay(r, true);
  }

  async function chay(r: TheoLenhRow, bat: boolean) {
    if (!token) return;
    setDangChay(khoaChu(r));
    try {
      const moi = await api.keHoachVatTu.giuCho(token, bat, {
        lsx_id: r.lsx_id,
        bai_ghep_id: r.bai_ghep_id,
      });
      thayThe(moi);
      setHoiNha(null);
      setFlash(
        bat
          ? moi.du
            ? `✓ ${r.ma}: Đã giữ đủ 100% — Mở khoá xếp lịch sản xuất.`
            : `⏳ ${r.ma}: Đã bật giữ chỗ. Hàng về kho sẽ tự nhặt bù.`
          : `✓ ${r.ma}: Đã nhả hết chỗ giữ vật tư.`,
      );
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setHoiNha(null);
    } finally {
      setDangChay(null);
    }
  }

  async function deNghiMua(r: TheoLenhRow) {
    if (!token) return;
    const dong: CanDoiKhoaDong[] = r.hang.flatMap((h) => h.khoa_do);
    if (dong.length === 0) return;
    setDangChay(khoaChu(r));
    try {
      // MỞ FORM, KHÔNG TỰ LẬP PHIẾU — giống hệt cách nhìn theo mặt hàng (20/08/2026).
      const nhap = await api.keHoachVatTu.xemTruocDeNghiMua(token, dong);
      if (onMoFormMua) {
        onMoFormMua(nhap);
        return;
      }
      const kq = await api.keHoachVatTu.deNghiMua(token, dong);
      setFlash(
        `✓ Đã tạo đề nghị mua hàng ${kq.code} cho ${r.ma}. Mở phân hệ Mua Hàng để duyệt & gửi PO.`,
      );
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDangChay(null);
    }
  }

  const rows = data?.items ?? [];
  const tomTat = useMemo(
    () => ({
      daGiu: rows.filter((r) => r.du).length,
      dangCho: rows.filter((r) => r.bat && !r.du).length,
      chuaBat: rows.filter((r) => !r.bat).length,
    }),
    [rows],
  );

  const rowsHienThi = useMemo(() => {
    if (filterType === "du") return rows.filter((r) => r.du);
    if (filterType === "dang") return rows.filter((r) => r.bat && !r.du);
    if (filterType === "tat") return rows.filter((r) => !r.bat);
    if (filterType === "giu_lau") return rows.filter((r) => r.giu_lau_chua_chay);
    return rows;
  }, [rows, filterType]);

  return (
    <div className="khvt-view">
      {/* ── 1. UNIFIED TOOLBAR: STATUS TABS + SEARCH + VIEW MODE SWITCH ── */}
      <div className="khvt-unified-bar">
        <div className="khvt-unified-tabs" role="tablist" aria-label="Bộ lọc lệnh">
          <button
            type="button"
            role="tab"
            aria-selected={filterType === "all"}
            className={`khvt-utab ${filterType === "all" ? "is-active" : ""}`}
            onClick={() => setFilterType("all")}
          >
            <span>Tất cả</span>
            <span className="khvt-utab__count">{num(rows.length)}</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "du"}
            className={`khvt-utab khvt-utab--du ${filterType === "du" ? "is-active" : ""}`}
            onClick={() => setFilterType("du")}
          >
            <span className="khvt-utab__dot" />
            <span>Giữ đủ</span>
            <span className="khvt-utab__count khvt-utab__count--du">{num(tomTat.daGiu)}</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "dang"}
            className={`khvt-utab khvt-utab--vemuon ${filterType === "dang" ? "is-active" : ""}`}
            onClick={() => setFilterType("dang")}
          >
            <span className="khvt-utab__dot" />
            <span>Đang giữ dở</span>
            {tomTat.dangCho > 0 && (
              <span className="khvt-utab__count khvt-utab__count--vemuon">{num(tomTat.dangCho)}</span>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "tat"}
            className={`khvt-utab khvt-utab--khongro ${filterType === "tat" ? "is-active" : ""}`}
            onClick={() => setFilterType("tat")}
          >
            <span className="khvt-utab__dot" />
            <span>Chưa giữ</span>
            <span className="khvt-utab__count khvt-utab__count--khongro">{num(tomTat.chuaBat)}</span>
          </button>

          {soGiuLau > 0 && (
            <button
              type="button"
              role="tab"
              aria-selected={filterType === "giu_lau"}
              className={`khvt-utab khvt-utab--do ${filterType === "giu_lau" ? "is-active" : ""}`}
              onClick={() => setFilterType("giu_lau")}
            >
              <span className="khvt-utab__dot" />
              <span>Giữ lâu (&gt;7 ngày)</span>
              <span className="khvt-utab__count khvt-utab__count--do">{num(soGiuLau)}</span>
            </button>
          )}
        </div>

        <div className="khvt-toolbar__actions">
          <div className="khvt-toolbar__search">
            <Icon name="search" size={14} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm theo mã lệnh, tên sản phẩm, mặt hàng..."
              aria-label="Tìm lệnh trong kế hoạch vật tư"
            />
            {q && (
              <button
                type="button"
                className="khvt-toolbar__clear"
                onClick={() => setQ("")}
                title="Xoá tìm kiếm"
              >
                ✕
              </button>
            )}
          </div>

          {/* Công tắc chuyển đổi chế độ xem Bảng Stream ↔ Thẻ Bento */}
          <div className="khvt-view-switcher" role="group" aria-label="Chuyển chế độ xem">
            <button
              type="button"
              className={`khvt-view-btn ${viewMode === "table" ? "is-active" : ""}`}
              onClick={() => setViewMode("table")}
              title="Dạng Bảng Dòng Chảy Vật Tư (Stream Table)"
            >
              <Icon name="table" size={15} />
              <span>Bảng</span>
            </button>
            <button
              type="button"
              className={`khvt-view-btn ${viewMode === "cards" ? "is-active" : ""}`}
              onClick={() => setViewMode("cards")}
              title="Dạng Thẻ Bento Command Cards"
            >
              <Icon name="grid" size={15} />
              <span>Thẻ</span>
            </button>
          </div>
        </div>
      </div>

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          <Icon name="check" size={16} />
          <span>{flash}</span>
        </div>
      )}

      {err && <BangLoi text={err} onRetry={load} />}

      {/* ── 2. NỘI DUNG CHÍNH: STREAM TABLE HOẶC BENTO CARDS ── */}
      {data === null ? (
        <div className="khsx__tablewrap">
          <table className="khsx__table">
            <Skeleton rows={5} cols={7} />
          </table>
        </div>
      ) : rowsHienThi.length === 0 ? (
        <EmptyState
          icon={q || filterType !== "all" ? "search" : "packageCheck"}
          title={
            q || filterType !== "all"
              ? "Không có lệnh nào khớp bộ lọc."
              : "Chưa có lệnh nào cần cân đối vật tư."
          }
          sub={
            q || filterType !== "all"
              ? "Thử xoá tìm kiếm hoặc chuyển sang bộ lọc khác."
              : "Bảng gom lệnh ở trạng thái Sẵn sàng · Đã lập kế hoạch · Đã phát hành."
          }
          action={
            q || filterType !== "all" ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setQ("");
                  setFilterType("all");
                }}
              >
                Xoá bộ lọc
              </Button>
            ) : undefined
          }
        />
      ) : viewMode === "table" ? (
        /* ── CHẾ ĐỘ 1: STREAM TABLE GRID (MẶC ĐỊNH) ── */
        <div className="khvt-master-card">
          <div className="khvt-table-wrap">
            <table className="khvt-master-table">
              <thead>
                <tr>
                  <th style={{ width: 170 }}>Lệnh sản xuất</th>
                  <th style={{ width: 120 }}>Ngày cần</th>
                  <th>Dòng chảy vật tư</th>
                  <th style={{ width: 130 }}>Độ sẵn sàng</th>
                  <th style={{ width: 140 }}>Cửa xếp lịch</th>
                  <th style={{ width: 130 }}>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {rowsHienThi.map((r) => {
                  const k = khoaChu(r);
                  const soDo = r.hang.reduce((s, h) => s + h.khoa_do.length, 0);
                  const veMuon = monVeMuon(r);
                  const soMonDu = r.hang.filter((h) => h.trang_thai === "xanh" || h.trang_thai === "xam").length;
                  const tongMon = r.hang.length;
                  const pctGiu = tongMon > 0 ? Math.round((soMonDu / tongMon) * 100) : 0;
                  const isDangChay = dangChay === k;

                  return (
                    <tr
                      key={k}
                      className={`khvt-row ${r.du ? "khvt-row--du" : !r.bat ? "khvt-row--tat" : "khvt-row--thieu"}`}
                      onClick={() => setSelectedRow(r)}
                    >
                      {/* Cột 1: Lệnh sản xuất */}
                      <td>
                        <div className="khvt-cell-lsx">
                          <div className="khvt-cell-lsx__top">
                            {r.lsx_id && onOpenLsx ? (
                              <button
                                type="button"
                                className="khvt-lsx-link"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onOpenLsx(r.lsx_id!);
                                }}
                                title="Mở chi tiết lệnh sản xuất"
                              >
                                {r.ma}
                              </button>
                            ) : (
                              <span className="khvt-lsx-code">{r.ma}</span>
                            )}
                            {r.bai_ghep_id != null && (
                              <span className="khsx-chip khsx-chip--ngoai" title="Bài ghép nhiều sản phẩm">
                                <Icon name="layers" size={11} /> ghép
                              </span>
                            )}
                            {r.is_rush && <ChipGap />}
                          </div>
                          {r.giu_lau_chua_chay && (
                            <span className="khvt-mini-alert" title="Giữ tồn lâu chưa đưa vào kế hoạch sản xuất">
                              <Icon name="clock" size={11} /> Giữ {num(r.so_ngay_giu)} ngày
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Cột 2: Ngày cần */}
                      <td>
                        <div className="khvt-cell-date">
                          <span className="khvt-date-val">{ngay(r.ngay_can)}</span>
                          {r.moc_tam && <small className="khvt-tam-badge">mốc tạm</small>}
                        </div>
                      </td>

                      {/* Cột 3: Dòng chảy vật tư (Interactive Stream Chips) */}
                      <td>
                        <div className="khvt-material-stream">
                          {r.hang.map((h) => {
                            const meta = mauVatTu(h.trang_thai);
                            const icon = iconLoaiHang(h.hang_loai);
                            // Chỉ bày ở món CÒN PHẢI LO. Món đã đủ kho mà vẫn đeo mã phiếu
                            // thì cả hàng chip toàn chữ, và cái cần đọc chìm mất; ai muốn
                            // tra vẫn có tooltip + drawer.
                            const vet = h.thieu > 0 || h.trang_thai === "khong_ro"
                              ? tomTatPhieuMua(h.phieu_mua)
                              : null;
                            return (
                              <div
                                key={`${h.hang_loai}-${h.hang_id}`}
                                className={`khvt-stream-chip ${meta.cls}`}
                                title={`${h.hang_ten ?? h.hang_ma}\n• Nhu cầu: ${soGoc(h.can)} ${h.don_vi_goc ?? ""}\n• Đang giữ: ${soGoc(h.dang_giu)} ${h.don_vi_goc ?? ""}${h.thieu > 0 ? `\n• Thiếu: ${soGoc(h.thieu)}` : ""}${h.trang_thai === "ve_muon" ? `\n• Đã đặt mua: ${moTaVeMuon(h)}` : ""}${vet ? `\n${vet.title}` : ""}`}
                              >
                                <Icon name={icon} size={12} />
                                <span className="khvt-stream-chip__name">
                                  {h.hang_ten ?? h.hang_ma ?? "Vật tư"}
                                </span>
                                {h.thieu > 0 ? (
                                  <span className="khvt-stream-chip__deficit">
                                    -{soGoc(h.thieu)} {h.don_vi_goc ?? ""}
                                  </span>
                                ) : (
                                  <span className="khvt-stream-chip__ok">
                                    {soGoc(h.dang_giu || h.can)}
                                  </span>
                                )}
                                {h.trang_thai === "ve_muon" && h.ngay_du_hang ? (
                                  <span className="khvt-stream-chip__eta">
                                    <Icon name="truck" size={10} /> về {ngay(h.ngay_du_hang)}
                                  </span>
                                ) : (
                                  /* Chưa có lô nào phủ được chỗ thiếu, NHƯNG đã có người lập
                                     phiếu — nói ra ngay trên chip để khỏi ai bấm Mua chồng lên. */
                                  vet && (
                                    <span className="khvt-stream-chip__po">
                                      <Icon name="cart" size={10} /> {vet.chinh}
                                      {vet.them > 0 && <b>+{vet.them}</b>}
                                    </span>
                                  )
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </td>

                      {/* Cột 4: Độ sẵn sàng */}
                      <td>
                        <div className="khvt-cell-readiness">
                          <div className={`khvt-readiness-badge ${pctGiu >= 100 ? "is-ready" : pctGiu >= 50 ? "is-partial" : "is-deficit"}`}>
                            {pctGiu >= 100 ? (
                              <>
                                <Icon name="check" size={11} /> <b>100%</b> <small>({soMonDu}/{tongMon} món)</small>
                              </>
                            ) : (
                              <>
                                <b>{soMonDu}/{tongMon} món</b> <small>({pctGiu}%)</small>
                              </>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Cột 5: Cửa xếp lịch */}
                      <td>
                        {r.du ? (
                          <span className="khvt-lock-badge khvt-lock-badge--open" title="Đã giữ đủ vật tư — Sẵn sàng xếp lịch">
                            <Icon name="check" size={12} /> Mở khóa
                          </span>
                        ) : !r.bat ? (
                          <span className="khvt-lock-badge khvt-lock-badge--locked" title="Chưa giữ chỗ — Chặn xếp lịch">
                            <Icon name="lock" size={12} /> Chặn lịch
                          </span>
                        ) : (
                          <span className="khvt-lock-badge khvt-lock-badge--partial" title="Đang giữ dở — Chờ hàng về bù tồn">
                            <Icon name="clock" size={12} /> Chờ bù tồn
                          </span>
                        )}
                      </td>

                      {/* Cột 6: Hành động nhanh */}
                      <td>
                        <div
                          className="khvt-row-actions"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {!r.bat ? (
                            <Button
                              onClick={() => doiGiuCho(r, true)}
                              disabled={isDangChay}
                              className="khvt-btn-action"
                            >
                              <Icon name="lock" size={12} /> {isDangChay ? "Đang giữ…" : "Giữ chỗ"}
                            </Button>
                          ) : (
                            <Button
                              variant="secondary"
                              onClick={() => doiGiuCho(r, false)}
                              disabled={isDangChay}
                              title="Nhả chỗ giữ trả lại kho chung"
                            >
                              <Icon name="lockOpen" size={12} /> Nhả chỗ
                            </Button>
                          )}
                          {canDeNghiMua && soDo > 0 && (
                            <Button
                              variant="secondary"
                              onClick={() => deNghiMua(r)}
                              disabled={isDangChay}
                              className="khvt-btn-buy"
                              title={`Lập yêu cầu mua cho ${soDo} dòng thiếu`}
                            >
                              <Icon name="cart" size={12} /> Mua ({soDo})
                            </Button>
                          )}
                          {canDeNghiMua && soDo === 0 && veMuon.length > 0 && (
                            <div className="khvt-po-chip" title={lyDoKhoaMua(veMuon)}>
                              <Icon name="truck" size={11} />
                              <span>
                                {veMuon.length === 1 && veMuon[0].ngay_du_hang
                                  ? `Đã đặt · về ${ngay(veMuon[0].ngay_du_hang)}`
                                  : `Đã đặt (${veMuon.length} món)`}
                              </span>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* ── CHẾ ĐỘ 2: BENTO COMMAND CARDS (LƯỚI THẺ 2 CỘT CÂN ĐỐI) ── */
        <div className="khvt-bento-grid">
          {rowsHienThi.map((r) => {
            const k = khoaChu(r);
            const soDo = r.hang.reduce((s, h) => s + h.khoa_do.length, 0);
            const veMuon = monVeMuon(r);
            const soMonDu = r.hang.filter((h) => h.trang_thai === "xanh" || h.trang_thai === "xam").length;
            const tongMon = r.hang.length;
            const pctGiu = tongMon > 0 ? Math.round((soMonDu / tongMon) * 100) : 0;
            const isDangChay = dangChay === k;

            return (
              <section
                key={k}
                className={`khvt-bcard ${r.du ? "khvt-bcard--du" : !r.bat ? "khvt-bcard--tat" : "khvt-bcard--thieu"}`}
                onClick={() => setSelectedRow(r)}
              >
                {/* Phân khu Trái: Thông tin Lệnh, Readiness & Dynamic Actions */}
                <div className="khvt-bcard__left">
                  <div className="khvt-bcard__header">
                    <div className="khvt-bcard__id-group">
                      {r.lsx_id && onOpenLsx ? (
                        <button
                          type="button"
                          className="khvt-lsx-link"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenLsx(r.lsx_id!);
                          }}
                        >
                          {r.ma}
                        </button>
                      ) : (
                        <span className="khvt-lsx-code">{r.ma}</span>
                      )}
                      {r.bai_ghep_id != null && (
                        <span className="khsx-chip khsx-chip--ngoai">
                          <Icon name="layers" size={11} /> ghép
                        </span>
                      )}
                      {r.is_rush && <ChipGap />}
                    </div>

                    <div className="khvt-bcard__date">
                      <Icon name="calendar" size={12} />
                      <span>Cần từ: <b>{ngay(r.ngay_can)}</b></span>
                      {r.moc_tam && <small className="khvt-tam-badge">mốc tạm</small>}
                    </div>
                  </div>

                  {/* Readiness Meter */}
                  <div className="khvt-bcard__readiness">
                    <div className="khvt-bcard__readiness-head">
                      <span>Độ sẵn sàng vật tư:</span>
                      <b>{soMonDu}/{tongMon} món ({pctGiu}%)</b>
                    </div>
                    <div className="khvt-bcard__progress">
                      <div
                        className={`khvt-bcard__progress-fill ${r.du ? "is-full" : r.bat ? "is-partial" : pctGiu >= 100 ? "is-ready" : "is-deficit"}`}
                        style={{ width: `${Math.max(5, pctGiu)}%` }}
                      />
                    </div>
                  </div>

                  {/* Visual Lock Status */}
                  <div className="khvt-bcard__lock-status">
                    {r.du ? (
                      <span className="khvt-lock-badge khvt-lock-badge--open">
                        <Icon name="check" size={13} /> SẴN SÀNG XẾP LỊCH CHẠY MÁY
                      </span>
                    ) : !r.bat ? (
                      <span className="khvt-lock-badge khvt-lock-badge--locked">
                        <Icon name="lock" size={13} /> CHƯA BẬT GIỮ — CHẶN XẾP LỊCH
                      </span>
                    ) : (
                      <span className="khvt-lock-badge khvt-lock-badge--partial">
                        <Icon name="clock" size={13} /> ĐANG GIỮ DỞ — CHỜ BÙ TỒN
                      </span>
                    )}
                  </div>

                  {/* Smart Advice / Cảnh báo */}
                  {r.giu_lau_chua_chay && (
                    <div className="khvt-recommend-box khvt-recommend-box--warn">
                      <Icon name="clock" size={13} />
                      <span>Giữ đã <b>{num(r.so_ngay_giu)} ngày</b> mà chưa đưa vào kế hoạch sản xuất.</span>
                    </div>
                  )}

                  {/* Dynamic Action Buttons */}
                  <div className="khvt-bcard__actions" onClick={(e) => e.stopPropagation()}>
                    {!r.bat ? (
                      <Button onClick={() => doiGiuCho(r, true)} disabled={isDangChay} className="khvt-btn-action">
                        <Icon name="lock" size={13} /> {isDangChay ? "Đang giữ…" : "Giữ chỗ ngay"}
                      </Button>
                    ) : (
                      <Button variant="secondary" onClick={() => doiGiuCho(r, false)} disabled={isDangChay}>
                        <Icon name="lockOpen" size={13} /> Nhả chỗ giữ
                      </Button>
                    )}
                    {canDeNghiMua && soDo > 0 && (
                      <Button variant="secondary" onClick={() => deNghiMua(r)} disabled={isDangChay} className="khvt-btn-buy">
                        <Icon name="cart" size={13} /> Đề nghị mua ({soDo} dòng)
                      </Button>
                    )}
                    {canDeNghiMua && soDo === 0 && veMuon.length > 0 && (
                      <span className="khvt-buy-lock" title={lyDoKhoaMua(veMuon)}>
                        <Button variant="secondary" disabled className="khvt-btn-buy khvt-btn-buy--khoa">
                          <Icon name="truck" size={13} /> Đã đặt mua — chờ hàng về
                        </Button>
                      </span>
                    )}
                  </div>
                </div>

                {/* Phân khu Phải: Chi tiết Dòng chảy vật tư (Material Stream Breakdown) */}
                <div className="khvt-bcard__right">
                  <div className="khvt-bcard__stream-title">
                    <Icon name="layers" size={13} />
                    <span>CÁC MẶT HÀNG TIÊU THỤ:</span>
                  </div>
                  <ul className="khvt-bcard__item-list">
                    {r.hang.map((h) => {
                      const meta = mauVatTu(h.trang_thai);
                      const icon = iconLoaiHang(h.hang_loai);
                      return (
                        <li key={`${h.hang_loai}-${h.hang_id}`} className="khvt-bcard__item">
                          <div className="khvt-bcard__item-main">
                            <span className="khvt-bcard__item-icon" style={{ color: meta.dotColor }}>
                              <Icon name={icon} size={14} />
                            </span>
                            <span className="khvt-bcard__item-name">
                              {h.hang_ten ?? h.hang_ma ?? "(đã gỡ khỏi danh mục)"}
                            </span>
                            {h.so_buoc > 1 && (
                              <span className="khvt-bcard__buoc-tag">{h.so_buoc} bước</span>
                            )}
                          </div>

                          <div className="khvt-bcard__item-stats">
                            <span className="khvt-bcard__item-need">
                              cần <b>{soGoc(h.can)}</b> {h.don_vi_goc ?? ""}
                            </span>
                            <span className="khvt-bcard__item-hold">
                              {h.dang_giu > 0 ? `giữ ${soGoc(h.dang_giu)}` : "chưa giữ"}
                            </span>
                            <span className={`khvt-bcard__item-badge ${meta.cls}`}>
                              {h.thieu > 0 ? `thiếu ${soGoc(h.thieu)}` : meta.label}
                            </span>
                          </div>

                          {/* "Đã có ai lo món này chưa" — không có dòng này thì "đã đề nghị" và
                              "chưa ai đụng vào" hiện y hệt nhau, và người sau bấm Mua lần nữa. */}
                          {h.trang_thai === "ve_muon" ? (
                            <div className="khvt-bcard__item-po">
                              <Icon name="truck" size={10} /> {moTaVeMuon(h)}
                            </div>
                          ) : (
                            (h.thieu > 0 || h.trang_thai === "khong_ro") &&
                            h.phieu_mua.length > 0 && (
                              <div className="khvt-bcard__item-po">
                                <Icon name="cart" size={10} />{" "}
                                {h.phieu_mua.map((pm, i) => (
                                  <span
                                    key={pm.ma}
                                    className={vetDangKep(pm) ? "khvt-po--kep" : undefined}
                                  >
                                    {i > 0 ? " · " : ""}
                                    {moTaPhieuMua(pm)}
                                  </span>
                                ))}
                              </div>
                            )
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {/* ── 3. DRAWER BÓC TÁCH CHI TIẾT LỆNH (LenhVatTuDrawer) ── */}
      {selectedRow && (
        <LenhVatTuDrawer
          row={selectedRow}
          dangChay={dangChay === khoaChu(selectedRow)}
          canDeNghiMua={canDeNghiMua}
          onClose={() => setSelectedRow(null)}
          onGiuCho={doiGiuCho}
          onDeNghiMua={deNghiMua}
          onOpenLsx={onOpenLsx}
        />
      )}

      {/* ── 4. HỘP THOẠI XÁC NHẬN NHẢ CHỖ ── */}
      <HopNhaCho
        row={hoiNha}
        busy={!!hoiNha && dangChay === khoaChu(hoiNha)}
        onXacNhan={() => hoiNha && void chay(hoiNha, false)}
        onHuy={() => setHoiNha(null)}
      />
    </div>
  );
}

// ============================================================================
// DRAWER BÓC TÁCH CHI TIẾT VẬT TƯ CỦA LỆNH (LenhVatTuDrawer)
// ============================================================================
function LenhVatTuDrawer({
  row: r,
  dangChay,
  canDeNghiMua,
  onClose,
  onGiuCho,
  onDeNghiMua,
  onOpenLsx,
}: {
  row: TheoLenhRow;
  dangChay: boolean;
  canDeNghiMua: boolean;
  onClose: () => void;
  onGiuCho: (r: TheoLenhRow, bat: boolean) => void;
  onDeNghiMua: (r: TheoLenhRow) => void;
  onOpenLsx?: (id: number) => void;
}) {
  const soDo = r.hang.reduce((s, h) => s + h.khoa_do.length, 0);
  const veMuon = monVeMuon(r);
  const soMonDu = r.hang.filter((h) => h.trang_thai === "xanh" || h.trang_thai === "xam").length;
  const tongMon = r.hang.length;
  const pctGiu = tongMon > 0 ? Math.round((soMonDu / tongMon) * 100) : 0;

  // Đóng bằng Esc
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="rc-drawer__scrim khvt-drawer-scrim" onClick={onClose} role="presentation">
      <aside
        className="rc-drawer rc-drawer--wide khvt-drawer"
        style={{ width: "min(720px, 94vw)" }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Bóc tách vật tư của ${r.ma}`}
      >
        {/* Header */}
        <header className="rc-drawer__head khvt-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              <span>Kế hoạch vật tư · Giữ chỗ theo lệnh</span>
            </div>
            <h2 className="rc-drawer__title khvt-drawer__title">
              Bóc tách chi tiết vật tư của lệnh
            </h2>
            <div className="khvt-drawer__subline">
              <span>Mã lệnh:</span>
              <span className="khvt-drawer__code">{r.ma}</span>
              {r.bai_ghep_id != null && (
                <span className="khsx-chip khsx-chip--ngoai">
                  <Icon name="layers" size={11} /> Bài ghép
                </span>
              )}
              {r.is_rush && <ChipGap />}
            </div>
          </div>
          <button
            type="button"
            className="rc-drawer__x"
            onClick={onClose}
            aria-label="Đóng"
            title="Đóng (Esc)"
          >
            ✕
          </button>
        </header>

        {/* Body */}
        <div className="rc-drawer__body khvt-drawer__body">
          {/* Dải KPI Bento Grid */}
          <div className="khvt-drawer-kpi-grid">
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">TỔNG SỐ MÓN</span>
              <span className="khvt-bento-kpi__val">
                <b>{num(tongMon)}</b> <small>món</small>
              </span>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">ĐÃ ĐỦ KHO</span>
              <span className="khvt-bento-kpi__val khvt-bento-kpi__val--ok">
                <b>{num(soMonDu)}</b> <small>món</small>
              </span>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">CẦN ĐẶT MUA</span>
              <div className="khvt-bento-kpi__val">
                {soDo > 0 ? (
                  <span className="khvt-kpi-badge khvt-kpi-badge--deficit">
                    Thiếu <b>{num(soDo)}</b> dòng
                  </span>
                ) : (
                  <span className="khvt-kpi-badge khvt-kpi-badge--ok">
                    Đủ hàng
                  </span>
                )}
              </div>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">ĐỘ SẴN SÀNG</span>
              <div className="khvt-bento-kpi__cov">
                <span className="khvt-bento-kpi__cov-pct">{pctGiu}%</span>
                <div className="khvt-mini-bar">
                  <div
                    className={`khvt-mini-bar__fill ${pctGiu >= 100 ? "is-full" : soDo > 0 ? "is-deficit" : "is-partial"}`}
                    style={{ width: `${Math.max(4, pctGiu)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Smart Message / Guidance Box */}
          {r.du ? (
            <div className="khvt-recommend-box khvt-recommend-box--ok">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--ok">
                <Icon name="check" size={14} />
              </div>
              <div className="khvt-recommend-box__content">
                Lệnh đã <b>giữ đủ 100% vật tư</b> trong kho — Cửa xếp lịch sản xuất đã mở!
              </div>
            </div>
          ) : !r.bat ? (
            <div className="khvt-recommend-box khvt-recommend-box--lock">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--lock">
                <Icon name="lock" size={14} />
              </div>
              <div className="khvt-recommend-box__content">
                Lệnh <b>chưa bật giữ chỗ</b> ⇒ Chưa thể xếp lịch chạy máy. Bấm "Giữ chỗ ngay" để đăng ký tồn kho.
              </div>
            </div>
          ) : (
            <div className="khvt-recommend-box khvt-recommend-box--warn">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--warn">
                <Icon name="clock" size={14} />
              </div>
              <div className="khvt-recommend-box__content">
                Lệnh đang <b>giữ được {soMonDu}/{tongMon} món</b>. Các món còn thiếu sẽ tự động nhặt bù khi lô mua hàng (PO) nhập kho.
              </div>
            </div>
          )}

          {/* Đã mua rồi mà hàng về muộn — việc phải làm là DỜI LỊCH, không phải mua tiếp. Nói
              ngay ở đây thì người dùng khỏi đi tìm nút mua đã bị khoá ở chân drawer. */}
          {veMuon.length > 0 && (
            <div className="khvt-recommend-box khvt-recommend-box--truck">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--truck">
                <Icon name="truck" size={14} />
              </div>
              <div className="khvt-recommend-box__content">
                <strong>Đã đặt mua — không mua thêm:</strong>{" "}
                {veMuon.map((h) => `${h.hang_ten ?? h.hang_ma ?? "Vật tư"} (${moTaVeMuon(h)})`).join("; ")}.
                Mua thêm là <b>mua đúp</b> đúng lô đang về —{" "}
                <span className="khvt-recommend-box__action">dời bước tiêu thụ</span> sang sau ngày
                về, hoặc hối nhà cung cấp giao sớm.
              </div>
            </div>
          )}

          {/* BOM Breakdown Table */}
          <div className="khvt-drawer-breakdown">
            <div className="khvt-drawer-breakdown__head">
              <h3 className="khvt-drawer-breakdown__title">
                Danh sách chi tiết từng loại vật tư ({r.hang.length} mặt hàng)
              </h3>
            </div>

            <div className="khsx__tablewrap">
              <table className="khsx__table khvt-table">
                <thead>
                  <tr>
                    <th scope="col">Mặt hàng &amp; Quy cách</th>
                    <th scope="col" className="khsx-th--num" style={{ width: 130 }}>
                      Nhu cầu
                    </th>
                    <th scope="col" className="khsx-th--num" style={{ width: 130 }}>
                      Đang giữ
                    </th>
                    <th scope="col" style={{ width: 160, textAlign: "right" }}>
                      Trạng thái
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {r.hang.map((h) => {
                    const meta = mauVatTu(h.trang_thai);
                    const tag = nhanLoaiHang(h.hang_loai);
                    return (
                      <tr key={`${h.hang_loai}-${h.hang_id}`}>
                        <td>
                          <div className="khvt-cell-item">
                            {/* Tên món đứng đầu, KHÔNG kèm mã danh mục — drawer này để xem còn
                                thiếu gì, mã chỉ làm dày dòng chữ. */}
                            <div className="khvt-cell-item__top">
                              <span className="khvt-item-name" title={h.hang_ten ?? undefined}>
                                {h.hang_ten ?? "(đã gỡ khỏi danh mục)"}
                              </span>
                              <span className={`khvt-item-tag ${tag.cls}`}>{tag.label}</span>
                              {h.so_buoc > 1 && (
                                <span className="khvt-bcard__buoc-tag" title="Món này khai ở nhiều công đoạn">
                                  {h.so_buoc} bước
                                </span>
                              )}
                            </div>
                            {h.so_lenh_khac_thieu > 0 && (
                              <div className="khvt-compete-alert">
                                <Icon name="alert" size={11} /> Có {h.so_lenh_khac_thieu} lệnh khác cũng đang chờ món này
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="khsx-num khvt-num-cell">
                          <div className="khvt-num-primary"><b>{soGoc(h.can)}</b> <small>{h.don_vi_goc ?? ""}</small></div>
                        </td>
                        <td className="khsx-num khvt-num-cell">
                          <div className="khvt-num-primary">
                            <span className={h.dang_giu > 0 ? "khvt-num-sub--ok" : "khvt-text-ash"}>
                              <b>{soGoc(h.dang_giu)}</b> <small>{h.don_vi_goc ?? ""}</small>
                            </span>
                          </div>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <span className={`khsx-pill ${meta.cls}`} title={meta.label}>
                            <span className="khsx-pill__dot" aria-hidden="true" />
                            {h.thieu > 0 ? `Thiếu ${soGoc(h.thieu)}` : meta.label}
                          </span>
                          {h.trang_thai === "ve_muon" && (
                            <div className="khvt-pill-note">{moTaVeMuon(h)}</div>
                          )}
                          {/* Drawer là chỗ TRA nên kê ĐỦ phiếu đang chạy, kể cả khi dòng đã xanh —
                              hai phiếu cùng một món nằm cạnh nhau chính là dấu hiệu đề nghị trùng.
                              Bỏ đúng cái phiếu vừa gọi tên ở dòng trên để khỏi nói hai lần. */}
                          {h.phieu_mua.filter((pm) => pm.ma !== h.phieu_ve).length > 0 && (
                            <div className="khvt-pill-note khvt-pill-note--po">
                              {h.phieu_mua
                                .filter((pm) => pm.ma !== h.phieu_ve)
                                .map((pm) => (
                                  <span
                                    key={pm.ma}
                                    className={vetDangKep(pm) ? "khvt-po--kep" : undefined}
                                    title={
                                      vetDangKep(pm)
                                        ? "Thu mua đã lập đơn cho món này nhưng đơn bị từ chối. Việc đang đứng — chờ thêm cũng không có hàng, cần thu mua lập lại đơn."
                                        : undefined
                                    }
                                  >
                                    <Icon
                                      name={vetDangKep(pm) ? "alert" : "cart"}
                                      size={10}
                                    />{" "}
                                    {moTaPhieuMua(pm, { dayDu: true })}
                                  </span>
                                ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="rc-drawer__foot khvt-drawer__foot">
          <div className="khvt-drawer__foot-left">
            {r.lsx_id && onOpenLsx && (
              <Button
                variant="secondary"
                onClick={() => {
                  onClose();
                  onOpenLsx(r.lsx_id!);
                }}
              >
                <Icon name="link" size={13} /> Mở Lệnh SX
              </Button>
            )}
          </div>

          <div className="khvt-drawer__foot-right">
            {!r.bat ? (
              <Button
                onClick={() => {
                  onGiuCho(r, true);
                  onClose();
                }}
                disabled={dangChay}
                className="khvt-btn-action"
              >
                <Icon name="lock" size={13} /> {dangChay ? "Đang giữ…" : "Giữ chỗ ngay"}
              </Button>
            ) : (
              <Button
                variant="secondary"
                onClick={() => {
                  onGiuCho(r, false);
                  onClose();
                }}
                disabled={dangChay}
              >
                <Icon name="lockOpen" size={13} /> Nhả chỗ giữ
              </Button>
            )}
            {canDeNghiMua && soDo > 0 && (
              <Button
                onClick={() => {
                  onDeNghiMua(r);
                  onClose();
                }}
                disabled={dangChay}
                className="khvt-btn-buy"
              >
                <Icon name="cart" size={13} /> Đề nghị mua ({soDo} dòng)
              </Button>
            )}
            {canDeNghiMua && soDo === 0 && veMuon.length > 0 && (
              <span className="khvt-buy-lock" title={lyDoKhoaMua(veMuon)}>
                <Button disabled className="khvt-btn-buy khvt-btn-buy--khoa">
                  <Icon name="truck" size={13} /> Đã đặt mua — chờ hàng về
                </Button>
              </span>
            )}
          </div>
        </footer>
      </aside>
    </div>
  );
}

// ============================================================================
// HỘP XÁC NHẬN NHẢ CHỖ GIỮ
// ============================================================================
function HopNhaCho({
  row,
  busy,
  onXacNhan,
  onHuy,
}: {
  row: TheoLenhRow | null;
  busy: boolean;
  onXacNhan: () => void;
  onHuy: () => void;
}) {
  const dangGiu = (row?.hang ?? []).filter((h) => h.dang_giu > 0);
  const soLenhDoi = Math.max(0, ...dangGiu.map((h) => h.so_lenh_khac_thieu), 0);

  return (
    <ConfirmDialog
      open={!!row}
      danger
      busy={busy}
      title={`Nhả chỗ giữ của ${row?.ma ?? ""}?`}
      confirmLabel="Nhả chỗ"
      onConfirm={onXacNhan}
      onCancel={onHuy}
    >
      {dangGiu.length === 0 ? (
        <p className="gclv-hop__trong">Lệnh này chưa giữ được món nào — nhả chỉ tắt công tắc.</p>
      ) : (
        <>
          <p className="gclv-hop__dau">Sắp trả lại kho:</p>
          <ul className="gclv-hop__ds">
            {dangGiu.map((h) => (
              <li key={`${h.hang_loai}-${h.hang_id}`}>
                <b>
                  {soGoc(h.dang_giu)} {h.don_vi_goc ?? ""}
                </b>{" "}
                {h.hang_ten ?? h.hang_ma ?? "(đã gỡ khỏi danh mục)"}
                {h.so_lenh_khac_thieu > 0 && (
                  <span className="gclv-hop__doi">
                    {" "}— {h.so_lenh_khac_thieu} lệnh khác đang thiếu món này
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="gclv-hop__hq">
        {soLenhDoi > 0
          ? "Phần vừa nhả sẽ được lệnh cần sớm hơn nhặt ngay — bật lại có thể chẳng còn gì."
          : "Hiện chưa lệnh nào khác thiếu những món này, nhưng bật lại vẫn không chắc giữ lại được."}
        {" "}
        <b>{row?.ma}</b> cũng mất quyền xếp lịch cho tới khi giữ đủ lại.
      </p>
    </ConfirmDialog>
  );
}
