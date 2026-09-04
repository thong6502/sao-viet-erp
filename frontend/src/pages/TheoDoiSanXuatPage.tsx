// Màn "Theo dõi sản xuất" — bàn quét TOÀN XƯỞNG cho điều độ/QC/trưởng phòng KD (Task 15-17).
// Trả lời "việc nào đang tắc / máy nào đang trống / lệnh nào sắp trễ" ở một cái nhìn tổng, khác
// hẳn "Hồ sơ lệnh sản xuất" (tra MỘT lệnh theo mã). Cùng module `lenh_sx`, khác module RBAC
// (`theo_doi_san_xuat`, ô quyền đã seed từ Task 1) vì khác câu hỏi, khác dữ liệu nguồn.
//
// ⚠️ MÀN NÀY KHÔNG GHI GÌ CẢ — y hệt nguyên tắc của `LenhSanXuatPage`. Bốn tab: Kanban · Theo máy ·
// Theo ca · Gantt theo lệnh. Task 17b dựng khung + hai tab đầu; Task 18b (đợt này) cắm nốt
// `TdsxTheoCa`/`TdsxGantt` vào đúng chỗ `hidden` 17b đã chừa — khung tab/thanh lọc không đổi.
//
// Thiết kế duyệt: `.superpowers/sdd/2026-08-31-lenh-sx-va-theo-doi-sx/task-17-thiet-ke.md`.
//
// C122 — KHÔNG giữ tab/bộ lọc trong URL hash: `AppShell` cố ý không đồng bộ URL với state màn con
// (hash là cửa vào MỘT LẦN cho deep-link QR, dùng xong bị xoá — xem `AppShell.tsx:282`). Tám tham
// số lọc + tab đều là state cục bộ, y khuôn `LenhSanXuatPage`.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { TdsxBoLocOut, TdsxThanhLocParams } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigateFn } from "../components/AppShell";
import { Icon } from "../components/Icons";
import { useTre } from "../lib/useTre";
import { LenhSxHoSoView } from "./LenhSxHoSoView";
import { NHOM_CONG_DOAN } from "./keHoachSxShared";
import { TDSX_TT_META, TdsxKanban } from "./TdsxKanban";
import { TdsxGantt } from "./TdsxGantt";
import { TdsxTheoCa } from "./TdsxTheoCa";
import { TdsxTheoMay } from "./TdsxTheoMay";
// `ke-hoach-sx.css` trước để `.khsx-skel__bar` / `.khsx-empty` / `.khsx-date--*` sẵn sàng; `lenh-
// san-xuat.css` để tái dùng NGUYÊN các khối `.hslsx__*` (đầu trang, thanh lọc, dải tab) — hai file
// này AppShell đã nạp tĩnh qua `LenhSanXuatPage`/`KeHoachSXPage` nên không tốn thêm request, khai
// lại ở đây chỉ để phòng ngày nào đó hai màn kia tách lazy-load. Nạp CUỐI CÙNG để `.tdsx-*` của
// riêng màn này thắng khi trùng độ ưu tiên với hai file mượn trên.
import "./ke-hoach-sx.css";
import "./lenh-san-xuat.css";
import "./theo-doi-san-xuat.css";

// Task 18b (W3) đổi 2000 → 400: `useTre` ở đây chính là `useDebounced` (GỘP sự kiện sát nhau, không
// nhân số lần gọi) nên 400ms gộp tốt y hệt 2000ms mà bảng tươi hơn 1,6 giây — đúng "debounce ~400ms"
// plan Bước 3 đòi. Cảnh báo (KHÔNG vá ở task này): debounce thuần có thể "chết đói" — sự kiện về
// đều đặn dày hơn cửa sổ gộp thì nó KHÔNG BAO GIỜ bắn, bảng đứng hình; muốn chắc phải thêm một mốc
// chờ tối đa, ngoài phạm vi 18b.
const SSE_GOP_MS = 400;

type TdsxTab = "kanban" | "theo_may" | "theo_ca" | "gantt";
const TABS: { key: TdsxTab; label: string }[] = [
  { key: "kanban", label: "Kanban" },
  { key: "theo_may", label: "Theo máy" },
  { key: "theo_ca", label: "Theo ca" },
  { key: "gantt", label: "Gantt theo lệnh" },
];

export function TheoDoiSanXuatPage({
  eventTick,
  navigate,
}: {
  eventTick?: number;
  navigate?: NavigateFn;
}) {
  const { token } = useAuth();

  // --- bộ lọc chung (LỌC Ở MÁY CHỦ — không rows.filter/rows.slice ở đây) --------------------
  const [q, setQ] = useState("");
  const qTre = useTre(q);
  const [khachHangId, setKhachHangId] = useState("");
  const [mayId, setMayId] = useState("");
  const [nhomCd, setNhomCd] = useState("");
  const [congNhanId, setCongNhanId] = useState("");
  const [trangThaiViec, setTrangThaiViec] = useState("");
  const [uuTien, setUuTien] = useState("");

  const params: TdsxThanhLocParams = useMemo(
    () => ({
      q: qTre.trim() || undefined,
      khach_hang_id: khachHangId ? Number(khachHangId) : undefined,
      may_id: mayId ? Number(mayId) : undefined,
      nhom_cong_doan: nhomCd || undefined,
      cong_nhan_id: congNhanId ? Number(congNhanId) : undefined,
      trang_thai_viec: trangThaiViec || undefined,
      uu_tien: uuTien ? (uuTien as "gap" | "binh_thuong") : undefined,
    }),
    [qTre, khachHangId, mayId, nhomCd, congNhanId, trangThaiViec, uuTien],
  );
  const dangLoc =
    qTre.trim() !== "" ||
    khachHangId !== "" ||
    mayId !== "" ||
    nhomCd !== "" ||
    congNhanId !== "" ||
    trangThaiViec !== "" ||
    uuTien !== "";
  const xoaLoc = useCallback(() => {
    setQ("");
    setKhachHangId("");
    setMayId("");
    setNhomCd("");
    setCongNhanId("");
    setTrangThaiViec("");
    setUuTien("");
  }, []);

  // --- nguồn thanh lọc: `/bo-loc` RIÊNG của màn này (CẤM mượn `/api/lenh-san-xuat/bo-loc` — ô
  // quyền khác, xem vết thương ghi ở `client.ts`). Hỏng ⇒ `null` ⇒ các ô phụ thuộc (Máy/Công nhân/
  // Khách hàng) tự ẩn, ba ô tĩnh (Nhóm CĐ/Trạng thái/Ưu tiên) vẫn chạy vì không phụ thuộc nó. ---
  const [boLoc, setBoLoc] = useState<TdsxBoLocOut | null>(null);
  const tickTre = useTre(eventTick ?? 0, SSE_GOP_MS);
  useEffect(() => {
    if (!token) return;
    let song = true;
    api.theoDoiSanXuat
      .boLoc(token)
      .then((r) => {
        if (song) setBoLoc(r);
      })
      .catch(() => {
        if (song) setBoLoc(null);
      });
    return () => {
      song = false;
    };
  }, [token, tickTre]);

  // --- 4 tab: giữ TRONG DOM (hidden), mỗi tab tự giữ vị trí cuộn của nó -----------------------
  const [tab, setTab] = useState<TdsxTab>("kanban");
  const tabIdx = Math.max(0, TABS.findIndex((t) => t.key === tab));
  const [tabFocus, setTabFocus] = useState(tabIdx);
  useEffect(() => setTabFocus(tabIdx), [tabIdx]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  function phimTab(e: React.KeyboardEvent, i: number) {
    let toi = i;
    if (e.key === "ArrowRight") toi = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") toi = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") toi = 0;
    else if (e.key === "End") toi = TABS.length - 1;
    else return;
    e.preventDefault();
    setTabFocus(toi);
    tabRefs.current[toi]?.focus();
  }

  // --- "Thêm bộ lọc" — popover Công nhân/Khách hàng (Ca CỐ Ý không có mặt ở đây: `/kanban` và
  // `/theo-may` không nhận `ca_id`, xem C130 trong báo cáo). Chỉ mọc khi CÓ ít nhất một nhóm để
  // bày — mọc popover rỗng là mời bấm vào chỗ không làm gì. ---
  const [themLocMo, setThemLocMo] = useState(false);
  const themLocRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!themLocMo) return;
    function ngoai(e: MouseEvent) {
      if (themLocRef.current && !themLocRef.current.contains(e.target as Node)) setThemLocMo(false);
    }
    function phimEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setThemLocMo(false);
    }
    document.addEventListener("mousedown", ngoai);
    document.addEventListener("keydown", phimEsc);
    return () => {
      document.removeEventListener("mousedown", ngoai);
      document.removeEventListener("keydown", phimEsc);
    };
  }, [themLocMo]);
  const coThemLoc = (boLoc?.cong_nhan.length ?? 0) > 0 || (boLoc?.khach_hang.length ?? 0) > 0;

  // --- hồ sơ một lệnh = LỚP PHỦ do CHÍNH màn này mở (y khuôn `LenhSanXuatPage`) ----------------
  const [hoSoId, setHoSoId] = useState<number | null>(null);
  const moHoSo = useCallback((id: number) => setHoSoId(id), []);
  const dongHoSo = useCallback(() => setHoSoId(null), []);

  return (
    <main className="tdsx hslsx">
      <header className="hslsx__head">
        <div className="hslsx__headrow">
          <h1 className="hslsx__title">Theo dõi sản xuất</h1>
          <span className="hslsx__ro" title="Màn tra cứu — không có thao tác ghi nào">
            Chỉ xem
          </span>
          <div className="hslsx__spacer" />
        </div>
        <p className="hslsx__sub">
          Toàn xưởng theo thời gian thực — việc nào đang tắc, máy nào đang trống, lệnh nào sắp trễ.
          Tra một lệnh theo mã thì dùng màn Hồ sơ lệnh sản xuất.
        </p>
      </header>

      <section className="hslsx__filters">
        <div className="hslsx__search">
          <Icon name="search" size={15} />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={120}
            placeholder="Tìm mã lệnh, tên sản phẩm, khách hàng"
            aria-label="Tìm mã lệnh, tên sản phẩm, khách hàng"
          />
          {q !== "" && (
            <button type="button" className="hslsx__clearq" onClick={() => setQ("")} aria-label="Xóa ô tìm">
              <Icon name="x" size={14} />
            </button>
          )}
        </div>

        <label className="hslsx__field">
          <span className="hslsx__field-lb">Nhóm CĐ</span>
          <select value={nhomCd} onChange={(e) => setNhomCd(e.target.value)}>
            <option value="">Tất cả</option>
            {Object.entries(NHOM_CONG_DOAN).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>

        {/* Ô Máy chỉ mọc khi `/bo-loc` thật sự trả được danh sách — khuôn `dsMay` của
            `LenhSanXuatPage`. Máy đã ngừng dùng vẫn liệt (có nhãn riêng) vì lane của nó vẫn tồn tại
            ở tab Theo máy. */}
        {boLoc && boLoc.may.length > 0 && (
          <label className="hslsx__field">
            <span className="hslsx__field-lb">Máy</span>
            <select value={mayId} onChange={(e) => setMayId(e.target.value)}>
              <option value="">Tất cả</option>
              {boLoc.may.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.ten}
                  {m.ngung_dung ? " (ngừng dùng)" : ""}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="hslsx__field">
          <span className="hslsx__field-lb">Trạng thái</span>
          <select value={trangThaiViec} onChange={(e) => setTrangThaiViec(e.target.value)}>
            <option value="">Tất cả</option>
            {(Object.keys(TDSX_TT_META) as (keyof typeof TDSX_TT_META)[]).map((k) => (
              <option key={k} value={k}>
                {TDSX_TT_META[k].label}
              </option>
            ))}
          </select>
        </label>

        <label className="hslsx__field">
          <span className="hslsx__field-lb">Ưu tiên</span>
          <select value={uuTien} onChange={(e) => setUuTien(e.target.value)}>
            <option value="">Tất cả</option>
            <option value="gap">Gấp</option>
            <option value="binh_thuong">Bình thường</option>
          </select>
        </label>

        {/* "Thêm bộ lọc" — popover Công nhân/Khách hàng. Design gốc có thêm ô "Ca" ở đây, nhưng
            C130 (task-17b-brief.md) chốt ẨN HẲN cho tới khi tab Theo ca (18b) tồn tại: `/kanban` và
            `/theo-may` không nhận `ca_id`, bày ô ra mà không dùng được là hứa suông. */}
        {coThemLoc && (
          <div className="tdsx-themloc" ref={themLocRef}>
            <button
              type="button"
              className="hslsx__linkbtn"
              aria-expanded={themLocMo}
              onClick={() => setThemLocMo((v) => !v)}
            >
              Thêm bộ lọc ▾
            </button>
            {themLocMo && (
              <div className="tdsx-themloc__pop" role="dialog" aria-label="Thêm bộ lọc">
                {boLoc && boLoc.cong_nhan.length > 0 && (
                  <label className="hslsx__field">
                    <span className="hslsx__field-lb">Công nhân</span>
                    <select value={congNhanId} onChange={(e) => setCongNhanId(e.target.value)}>
                      <option value="">Tất cả</option>
                      {boLoc.cong_nhan.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.ten}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {boLoc && boLoc.khach_hang.length > 0 && (
                  <label className="hslsx__field">
                    <span className="hslsx__field-lb">Khách hàng</span>
                    <select value={khachHangId} onChange={(e) => setKhachHangId(e.target.value)}>
                      <option value="">Tất cả</option>
                      {boLoc.khach_hang.map((k) => (
                        <option key={k.id} value={k.id}>
                          {k.ten}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
          </div>
        )}

        {dangLoc && (
          <button type="button" className="hslsx__linkbtn" onClick={xoaLoc}>
            Xóa bộ lọc
          </button>
        )}
      </section>

      <div className="hslsx__tabs" role="tablist" aria-label="Chọn góc nhìn">
        {TABS.map((t, i) => (
          <button
            key={t.key}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`tdsx-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`tdsx-panel-${t.key}`}
            tabIndex={i === tabFocus ? 0 : -1}
            className={`hslsx__tab${tab === t.key ? " is-active" : ""}`}
            onKeyDown={(e) => phimTab(e, i)}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div
        id="tdsx-panel-kanban"
        role="tabpanel"
        aria-labelledby="tdsx-tab-kanban"
        hidden={tab !== "kanban"}
        tabIndex={0}
      >
        <TdsxKanban
          active={tab === "kanban"}
          token={token}
          params={params}
          refreshTick={tickTre}
          onOpenHoSo={moHoSo}
          onXoaLoc={xoaLoc}
        />
      </div>

      <div
        id="tdsx-panel-theo_may"
        role="tabpanel"
        aria-labelledby="tdsx-tab-theo_may"
        hidden={tab !== "theo_may"}
        tabIndex={0}
      >
        <TdsxTheoMay
          active={tab === "theo_may"}
          token={token}
          params={params}
          refreshTick={tickTre}
          onOpenHoSo={moHoSo}
          onXoaLoc={xoaLoc}
        />
      </div>

      <div
        id="tdsx-panel-theo_ca"
        role="tabpanel"
        aria-labelledby="tdsx-tab-theo_ca"
        hidden={tab !== "theo_ca"}
        tabIndex={0}
      >
        <TdsxTheoCa
          active={tab === "theo_ca"}
          token={token}
          params={params}
          refreshTick={tickTre}
          caFacet={boLoc?.ca ?? []}
          onOpenHoSo={moHoSo}
          onXoaLoc={xoaLoc}
        />
      </div>

      <div
        id="tdsx-panel-gantt"
        role="tabpanel"
        aria-labelledby="tdsx-tab-gantt"
        hidden={tab !== "gantt"}
        tabIndex={0}
      >
        <TdsxGantt
          active={tab === "gantt"}
          token={token}
          params={params}
          refreshTick={tickTre}
          onOpenHoSo={moHoSo}
          onXoaLoc={xoaLoc}
        />
      </div>

      {/* Hồ sơ nằm TRONG `<main className="tdsx hslsx">` để mọi rule nền mượn từ `.hslsx` (focus,
          `.sr-only`, `.hslsx-pill--*`…) áp được vào lớp phủ mà không phải chép lại lần hai. */}
      {hoSoId !== null && (
        <LenhSxHoSoView
          lsxId={hoSoId}
          pv={null}
          onClose={dongHoSo}
          eventTick={eventTick}
          onMoDon={navigate ? (orderId) => navigate("don-hang-ban", { openOrderId: orderId }) : undefined}
        />
      )}
    </main>
  );
}
