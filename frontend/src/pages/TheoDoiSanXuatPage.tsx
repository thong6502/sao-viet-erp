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

import { ApiError, api } from "../api/client";
import type { TdsxBoLocOut, TdsxKanbanCard, TdsxThanhLocParams } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigateFn } from "../components/AppShell";
import { Icon } from "../components/Icons";
import { useTre } from "../lib/useTre";
import { LenhSxHoSoView } from "./LenhSxHoSoView";
import { NHOM_CONG_DOAN, classHan } from "./keHoachSxShared";
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

  // HAI nguồn "tải lại" trộn thành MỘT số: nhịp SSE đã gộp, và nút Làm mới. Bốn tab chỉ dùng
  // `refreshTick` làm TÍN HIỆU đổi (không đọc giá trị) nên `Date.now()` là đủ — chắc chắn khác
  // lần trước. Nút Làm mới trước đây gọi `window.location.reload()`: nạp lại cả ứng dụng, trắng
  // màn, mất luôn tab và bộ lọc đang đứng — vô lý ngay cạnh một màn tự đẩy dữ liệu qua SSE.
  const [lamMoi, setLamMoi] = useState(0);
  const nhipTai = useMemo(() => Date.now(), [tickTre, lamMoi]);

  // Chỗ neo cho thanh điều khiển RIÊNG của tab đang mở (Kanban: ẩn/hiện cột trống · Theo máy: dải
  // ngày + chú giải · Theo ca: ngày + ca). Mỗi tab tự `createPortal` điều khiển của nó vào đây:
  // state vẫn ở tab, mà trên màn chúng đứng cùng hàng với dải tab thay vì chiếm thêm một tầng
  // ngang chạy hết bề rộng. Callback ref qua `useState` để node vào DOM là re-render ngay.
  const [khayDieuKhien, setKhayDieuKhien] = useState<HTMLDivElement | null>(null);

  // --- dữ liệu Kanban ở TRANG, không ở tab Kanban ------------------------------------------
  // `/kanban` trả MỌI lệnh đã phát hành kèm việc đang chạy của nó — tức là bức ảnh cả xưởng, thứ
  // dải số dưới tiêu đề cần. Trước đây nó nằm trong `TdsxKanban` và tab ẩn thì KHÔNG gọi, nên số
  // ở đầu màn sẽ đứng hình ngay khi người dùng sang Theo máy/Theo ca/Gantt. Nâng lên đây: một
  // request duy nhất nuôi cả dải số lẫn tab Kanban — không nhân đôi, không số cũ. Giá phải trả là
  // ở ba tab kia vẫn tốn request đó; đổi lại đầu màn luôn nói đúng, và đây là màn người ta MỞ ĐỂ
  // NHÌN CON SỐ.
  const [cards, setCards] = useState<TdsxKanbanCard[]>([]);
  const [cardsDangTai, setCardsDangTai] = useState(true);
  const [cardsLoi, setCardsLoi] = useState<{ text: string; cam: boolean } | null>(null);
  useEffect(() => {
    if (!token) return;
    let song = true;
    setCardsDangTai(true);
    api.theoDoiSanXuat
      .kanban(token, params)
      .then((r) => {
        if (!song) return;
        setCards(r.cards);
        setCardsLoi(null);
      })
      .catch((e) => {
        if (!song) return;
        const cam = e instanceof ApiError && e.isForbidden;
        setCardsLoi({
          text: cam
            ? "Bạn không có quyền xem Theo dõi sản xuất."
            : "Không tải được bảng Theo dõi sản xuất. Kiểm tra mạng rồi thử lại.",
          cam,
        });
      })
      .finally(() => {
        if (song) setCardsDangTai(false);
      });
    return () => {
      song = false;
    };
  }, [token, params, nhipTai]);

  // Bốn con số đầu màn. Đếm theo VIỆC cho ba cột đầu (một lệnh có thể chạy nhiều bước song song
  // nên đếm theo lệnh sẽ nói dối về tải xưởng), theo LỆNH cho cột trễ — trễ là chuyện của cả lệnh.
  const tomTat = useMemo(() => {
    let chay = 0;
    let dung = 0;
    let tre = 0;
    for (const c of cards) {
      for (const ch of c.chip_dang_chay) {
        if (ch.trang_thai === "running") chay += 1;
        else if (ch.trang_thai === "paused") dung += 1;
      }
      if (c.han_hoan_thanh_sx && classHan(c.han_hoan_thanh_sx) === "khsx-date--late") tre += 1;
    }
    return { chay, dung, tre, lenh: cards.length };
  }, [cards]);
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

  const searchRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    function globalKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", globalKey);
    return () => window.removeEventListener("keydown", globalKey);
  }, []);

  return (
    <main className="tdsx hslsx">
      {/* MỘT hàng cho tiêu đề + dấu trực tiếp + nút làm mới. Breadcrumb "Sản xuất › Theo dõi sản
          xuất" đã bỏ: thanh bên luôn tô sáng đúng mục đang xem, dòng đó chỉ nhắc lại chính nó. */}
      <header className="tdsx__head">
        <h1 className="tdsx__title">Theo dõi sản xuất</h1>
        <span
          className="tdsx__live"
          title="Màn tự cập nhật khi xưởng bấm máy — không phải bấm Làm mới mới thấy việc mới."
        >
          <i aria-hidden="true" />
          trực tiếp
        </span>
        <span className="hslsx__spacer" />
        <button
          type="button"
          className="tdsx__reload"
          title="Gọi lại dữ liệu của tab đang xem"
          onClick={() => setLamMoi((v) => v + 1)}
        >
          <Icon name="refresh" size={13} />
          <span>Làm mới</span>
        </button>
      </header>

      {/* Bốn con số, không viền không nền — chỉ cỡ chữ làm việc phân cấp. Một màn tên là "Theo dõi
          sản xuất" mà mở ra phải đọc cả bàn mới biết xưởng đang chạy mấy việc thì nó chưa theo dõi
          gì cả. Số tôn trọng bộ lọc đang áp, nên lọc theo máy/tổ là ra tải của riêng chỗ đó. */}
      <section className="tdsx__stats" aria-label="Tổng quan xưởng">
        <StatSo n={tomTat.chay} nhan="đang chạy" bien="chay" dangTai={cardsDangTai} />
        <StatSo n={tomTat.dung} nhan="tạm dừng" bien="dung" dangTai={cardsDangTai} />
        <StatSo n={tomTat.tre} nhan="lệnh trễ hạn" bien="tre" dangTai={cardsDangTai} />
        <StatSo n={tomTat.lenh} nhan="lệnh đang theo dõi" bien="thuong" dangTai={cardsDangTai} />
      </section>

      {/* Bộ lọc là MỘT HÀNG TRẦN, không phải một thẻ có nền + viền + đổ bóng riêng: thẻ đó tốn
          114px chiều cao mà không nói thêm điều gì. Viên lọc dùng NGUYÊN `.hslsx__field` của "Hồ
          sơ lệnh sản xuất" — cùng bộ lọc thì phải cùng hình dạng — và viên có giá trị tự sẫm lại,
          nên KHÔNG cần dải "Đang lọc: …" nói lại lần thứ hai ngay bên dưới (dải đó đã gỡ). */}
      <section className="tdsx__deck">
        <div className="hslsx__search">
          <Icon name="search" size={15} />
          <input
            ref={searchRef}
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={120}
            placeholder="Tìm mã lệnh, tên sản phẩm, khách hàng (Ctrl+K)"
            aria-label="Tìm mã lệnh, tên sản phẩm, khách hàng"
          />
          {q === "" ? (
            <kbd className="hslsx__kbd">Ctrl K</kbd>
          ) : (
            <button type="button" className="hslsx__clearq" onClick={() => setQ("")} aria-label="Xóa ô tìm">
              <Icon name="x" size={14} />
            </button>
          )}
        </div>

        <label className={`hslsx__field${nhomCd !== "" ? " is-active" : ""}`}>
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

        {boLoc && boLoc.may.length > 0 && (
          <label className={`hslsx__field${mayId !== "" ? " is-active" : ""}`}>
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

        <label className={`hslsx__field${trangThaiViec !== "" ? " is-active" : ""}`}>
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

        <label className={`hslsx__field${uuTien !== "" ? " is-active" : ""}`}>
          <span className="hslsx__field-lb">Ưu tiên</span>
          <select value={uuTien} onChange={(e) => setUuTien(e.target.value)}>
            <option value="">Tất cả</option>
            <option value="gap">Gấp</option>
            <option value="binh_thuong">Bình thường</option>
          </select>
        </label>

        {coThemLoc && (
          <div className="tdsx-themloc" ref={themLocRef}>
            <button
              type="button"
              className={`hslsx__field tdsx__morefilter${congNhanId !== "" || khachHangId !== "" ? " is-active" : ""}`}
              aria-expanded={themLocMo}
              onClick={() => setThemLocMo((v) => !v)}
            >
              Thêm bộ lọc
              <Icon name="chevron" size={12} />
            </button>
            {themLocMo && (
              <div className="tdsx-themloc__pop" role="dialog" aria-label="Thêm bộ lọc">
                {boLoc && boLoc.cong_nhan.length > 0 && (
                  <label className={`hslsx__field${congNhanId !== "" ? " is-active" : ""}`}>
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
                  <label className={`hslsx__field${khachHangId !== "" ? " is-active" : ""}`}>
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

      {/* Dải tab VÀ thanh điều khiển riêng của tab đang mở đứng CHUNG một hàng. `role="tablist"`
          chỉ được ôm các `role="tab"` nên khay điều khiển đứng NGOÀI nó, cạnh bên. */}
      <div className="tdsx__tabsrow">
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
        <div className="tdsx__ctl" ref={setKhayDieuKhien} />
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
          cards={cards}
          dangTai={cardsDangTai}
          loi={cardsLoi}
          onTaiLai={() => setLamMoi((v) => v + 1)}
          khay={khayDieuKhien}
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
          refreshTick={nhipTai}
          khay={khayDieuKhien}
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
          refreshTick={nhipTai}
          khay={khayDieuKhien}
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
          refreshTick={nhipTai}
          khay={khayDieuKhien}
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

// Một con số đầu màn. Số to (`--fs-2xl`) đứng trên nhãn nhỏ, không viền không nền — phân cấp do
// cỡ chữ và màu làm, không do hộp. Màu theo luật bảng màu: chạy = moss, dừng = amber, trễ = rust,
// còn lại trung tính. Lúc chưa có số thì hiện dấu "—" chứ KHÔNG hiện 0: 0 là một khẳng định
// ("xưởng không chạy việc nào"), nói ra lúc chưa biết là nói dối.
function StatSo({
  n,
  nhan,
  bien,
  dangTai,
}: {
  n: number;
  nhan: string;
  bien: "chay" | "dung" | "tre" | "thuong";
  dangTai: boolean;
}) {
  return (
    <div className={`tdsx__stat tdsx__stat--${bien}${dangTai || n === 0 ? " is-zero" : ""}`}>
      <span className="tdsx__stat-n">{dangTai ? "—" : n}</span>
      <span className="tdsx__stat-nhan">{nhan}</span>
    </div>
  );
}
