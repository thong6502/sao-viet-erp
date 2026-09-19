// XẾP LỊCH 3 — BÀN XẾP LỊCH CẤP LỆNH SẢN XUẤT (BOTTOM DOCK STUDIO LAYOUT)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, RotateCcw, Send } from "lucide-react";
import {
  ApiError, api,
  type XlChiTiet as XlChiTietData, type XlDong, type XlGoiPhatHanh, type XlThe,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { useDebounced } from "../utils/useDebounced";
import { XlChiTiet } from "./XlChiTiet";
import { XlGantt } from "./XlGantt";
import { XlHangCho } from "./XlHangCho";
import {
  NGAY_NHAP_MAX, NGAY_NHAP_MIN, dauTuan, gioPhut, loiKhoangNgay, phutChayTrongCuaSo, soNgayGiua, themNgay, treHan,
} from "./xlShared";
import "./xep-lich.css";

const MOI_TRANG = 20;

export function XepLichPage({
  eventTick = 0,
  onBadgeStale,
}: {
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can("xep_lich", "update");
  const duyetDuoc = can("xep_lich", "approve");

  const [soNgay, setSoNgay] = useState<number>(7);
  const [tu, setTu] = useState<string>(() => dauTuan(new Date()));
  const den = useMemo(() => themNgay(tu, soNgay - 1), [tu, soNgay]);

  // Ô chọn KHOẢNG ngày tự do. Gõ vào bản nháp `nhapTu/nhapDen`, bấm Áp dụng mới đổi cửa sổ — đổi
  // theo từng phím thì mỗi ô ngày gõ dở là một lượt `/lich` với khoảng rác.
  const [moKhoang, setMoKhoang] = useState(false);
  const [nhapTu, setNhapTu] = useState(tu);
  const [nhapDen, setNhapDen] = useState(den);
  const nhanKhoangRef = useRef<HTMLSpanElement>(null);
  const oKhoangRef = useRef<HTMLFormElement>(null);
  const loiKhoang = loiKhoangNgay(nhapTu, nhapDen);
  const batKhoang = () => {
    if (!moKhoang) { setNhapTu(tu); setNhapDen(den); }
    setMoKhoang(!moKhoang);
  };
  useEffect(() => {
    if (!moKhoang) return;
    const ngoai = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!oKhoangRef.current?.contains(t) && !nhanKhoangRef.current?.contains(t)) setMoKhoang(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMoKhoang(false); };
    document.addEventListener("mousedown", ngoai);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", ngoai);
      document.removeEventListener("keydown", esc);
    };
  }, [moKhoang]);

  const [dong, setDong] = useState<XlDong[]>([]);
  // Ngày không làm việc của ĐÚNG cửa sổ đang xem — lễ, làm bù, cấu hình tuần. Đi kèm `/lich` chứ
  // không hỏi riêng: cùng một lượt, cùng một nguồn với lịch đang vẽ.
  const [ngayNghi, setNgayNghi] = useState<string[]>([]);
  const [the, setThe] = useState<XlThe[]>([]);
  const [tongCho, setTongCho] = useState(0);
  const [tim, setTim] = useState("");
  const timCho = useDebounced(tim, 300);
  const [trang, setTrang] = useState(1);

  const [chonId, setChonId] = useState<number | null>(null);
  const [ct, setCt] = useState<XlChiTietData | null>(null);
  const [taiCt, setTaiCt] = useState(false);
  const [dangGhi, setDangGhi] = useState(false);
  const [taiCho, setTaiCho] = useState(false);

  const [loi, setLoi] = useState<string | null>(null);
  const [bao, setBao] = useState<string | null>(null);
  const [keoTuHangCho, setKeoTuHangCho] = useState<number | null>(null);
  const [nhip, setNhip] = useState(0);
  const lamMoi = useCallback(() => setNhip((n) => n + 1), []);
  // Đọc trong callback ghi mà không đưa vào deps — `datMoc` đổi danh tính là effect kéo thả của
  // Gantt gỡ/gắn lại listener giữa chừng.
  const tickRef = useRef(eventTick);
  tickRef.current = eventTick;
  const theRef = useRef(the);
  theRef.current = the;

  const hetGio = useRef<number | null>(null);
  useEffect(() => {
    if (!bao) return;
    if (hetGio.current) window.clearTimeout(hetGio.current);
    hetGio.current = window.setTimeout(() => setBao(null), 6000);
    return () => {
      if (hetGio.current) window.clearTimeout(hetGio.current);
    };
  }, [bao]);

  // Màn hẹp mở ra là hàng chờ đã THU GỌN sẵn: ở ≤768px nó là ngăn kéo phủ lên lưới (§78
  // `responsive.css`), để mở sẵn thì người dùng vào màn Xếp lịch mà không thấy cái lịch nào.
  // Chỉ lấy lúc dựng — sau đó là quyền của người dùng, đổi bề ngang không giật cánh cửa lại.
  const [choCollapsed, setChoCollapsed] = useState(
    () => window.matchMedia("(max-width: 768px)").matches,
  );
  // Hộp thoại lý do dùng CHUNG cho hai việc trái chiều nhau — rút gói về (`thu_hoi`) và đẩy lịch
  // mới xuống (`cap_nhat`). Cùng một ô nhập, cùng một ngưỡng 3 ký tự; khác chữ và khác đích.
  const [chePrompt, setChePrompt] = useState<"thu_hoi" | "cap_nhat" | null>(null);
  const [lyDo, setLyDo] = useState("");
  const [loiLyDo, setLoiLyDo] = useState<string | null>(null);
  const [goi, setGoi] = useState<XlGoiPhatHanh | null>(null);

  // ---------------------------------------------------------------- nạp
  useEffect(() => {
    if (!token) return;
    let huy = false;
    api.xepLich
      .lich(token, { tu, den })
      .then((r) => {
        if (huy) return;
        setDong(r.dong);
        setNgayNghi(r.ngay_nghi ?? []);
      })
      .catch((e) => !huy && setLoi(e instanceof ApiError ? e.message : "Không tải được lịch."));
    return () => {
      huy = true;
    };
  }, [token, tu, den, eventTick, nhip]);

  useEffect(() => {
    if (!token) return;
    let huy = false;
    setTaiCho(true);
    api.xepLich
      .hangCho(token, { tim: timCho, trang, moi_trang: MOI_TRANG })
      .then((r) => {
        if (huy) return;
        setThe(r.dong);
        setTongCho(r.tong);
      })
      .catch((e) => !huy && setLoi(e instanceof ApiError ? e.message : "Không tải được hàng chờ."))
      .finally(() => !huy && setTaiCho(false));
    return () => {
      huy = true;
    };
  }, [token, timCho, trang, eventTick, nhip]);

  useEffect(() => {
    if (!token || chonId === null) {
      setCt(null);
      return;
    }
    let huy = false;
    setTaiCt(true);
    api.xepLich
      .chiTiet(token, chonId)
      .then((r) => !huy && setCt(r))
      .catch((e) => !huy && setLoi(e instanceof ApiError ? e.message : "Không tải được chi tiết lệnh."))
      .finally(() => !huy && setTaiCt(false));
    return () => {
      huy = true;
    };
  }, [token, chonId, eventTick, nhip]);

  // Trạng thái gói đã thả xuống xưởng — hỏi TRƯỚC khi bày nút, không thì màn mời người dùng thu
  // hồi một gói đã có việc chạy rồi mới ném 409 sau khi họ gõ xong lý do. Câu hỏi PHỤ: hỏng thì
  // panel vẫn mở bình thường, chỉ mất phần gợi ý (nút quay về dáng cũ).
  useEffect(() => {
    if (!token || chonId === null) {
      setGoi(null);
      return;
    }
    let huy = false;
    api.xepLich
      .goiPhatHanh(token, chonId)
      .then((r) => !huy && setGoi(r))
      .catch(() => !huy && setGoi(null));
    return () => {
      huy = true;
    };
  }, [token, chonId, eventTick, nhip]);

  useEffect(() => setTrang(1), [timCho]);

  // ---------------------------------------------------------------- ghi
  const sau = useCallback(
    (lsxId: number) => {
      setChonId(lsxId);
      lamMoi();
      onBadgeStale?.();
    },
    [lamMoi, onBadgeStale],
  );

  const datMoc = useCallback(
    async (lsxId: number, batDauAt: string, expected: string | null) => {
      if (!token || !suaDuoc) return;
      setDangGhi(true);
      setLoi(null);
      // Nhịp SSE lấy LÚC GỬI: máy chủ phát sự kiện trước khi trả phản hồi, nên nhịp của chính lần
      // ghi này có thể về trước cả `await` bên dưới.
      const tickTruoc = tickRef.current;
      const tuHangCho = theRef.current.some((t) => t.lsx_id === lsxId);
      try {
        const r = await api.xepLich.datMoc(token, lsxId, batDauAt, expected);
        setBao(r.thong_bao ?? null);
        // VẼ NGAY bằng dòng PUT trả về — máy chủ dựng nó bằng đúng `_dong` của `/lich`. Trước
        // 14/09/2026 dòng này bị bỏ, thanh nhảy về chỗ cũ rồi đứng đó chờ tải lại cả lịch.
        setDong((ds) => (ds.some((d) => d.lsx_id === lsxId)
          ? ds.map((d) => (d.lsx_id === lsxId ? r : d))
          : [...ds, r]));
        if (tuHangCho) {
          setThe((ds) => ds.filter((t) => t.lsx_id !== lsxId));
          setTongCho((n) => Math.max(0, n - 1));
        }
        // KHÔNG chọn lệnh: kéo thả xong chỉ cần thanh dài/ngắn lại, muốn xem chi tiết thì bấm.
        // KHÔNG tự tải lại: máy chủ phát `xep_lich_changed`, AppShell tăng `eventTick` (màn tải
        // lại lịch + hàng chờ + chi tiết đang mở) và tự nạp badge khối Sản xuất. Tự gọi thêm ở đây
        // là mỗi lần thả tải hai lượt, cộng `onBadgeStale` nạp badge của MỌI module (~25 request).
        // Chỉ khi SSE im quá 3 giây (mất kết nối) mới tự tải, để màn không đứng số cũ.
        window.setTimeout(() => {
          if (tickRef.current !== tickTruoc) return;
          lamMoi();
          onBadgeStale?.();
        }, 3000);
      } catch (e) {
        setLoi(
          e instanceof ApiError && e.status === 409
            ? "Người khác vừa dời lệnh này — màn đang tải lại bản mới nhất."
            : e instanceof ApiError
              ? e.message
              : "Không lưu được giờ bắt đầu.",
        );
        lamMoi();
      } finally {
        setDangGhi(false);
        setKeoTuHangCho(null);
      }
    },
    [token, suaDuoc, lamMoi, onBadgeStale],
  );

  const boLich = useCallback(async () => {
    if (!token || chonId === null) return;
    setDangGhi(true);
    try {
      await api.xepLich.xoaMoc(token, chonId);
      setBao("Đã bỏ lịch — lệnh quay lại hàng chờ.");
      sau(chonId);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không bỏ được lịch.");
    } finally {
      setDangGhi(false);
    }
  }, [token, chonId, sau]);

  const phatHanh = useCallback(async () => {
    if (!token || chonId === null) return;
    setDangGhi(true);
    try {
      await api.xepLich.phatHanh(token, chonId);
      setBao("Đã phát hành xuống xưởng.");
      sau(chonId);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không phát hành được.");
    } finally {
      setDangGhi(false);
    }
  }, [token, chonId, sau]);

  const moPrompt = useCallback((che: "thu_hoi" | "cap_nhat") => {
    setLyDo("");
    setLoiLyDo(null);
    setChePrompt(che);
  }, []);

  const xacNhanPrompt = useCallback(async () => {
    if (!token || chonId === null || chePrompt === null) return;
    const ld = lyDo.trim();
    if (ld.length < 3) {
      setLoiLyDo(
        chePrompt === "thu_hoi"
          ? "Vui lòng nhập lý do thu hồi dài ít nhất 3 ký tự."
          : "Vui lòng nhập lý do cập nhật dài ít nhất 3 ký tự.",
      );
      return;
    }
    setDangGhi(true);
    setLoiLyDo(null);
    try {
      if (chePrompt === "thu_hoi") {
        await api.xepLich.thuHoi(token, chonId, ld);
        setBao("Đã thu hồi phát hành.");
      } else {
        const r = await api.xepLich.phatHanhCapNhat(token, chonId, ld);
        setBao(
          `Đã đẩy lịch mới xuống xưởng: cập nhật ${r.so_cong_viec_cap_nhat} việc, giữ nguyên ` +
            `${r.so_giu_nguyen} việc đã bắt đầu.` +
            // Việc lệch lần chạy KHÔNG được cập nhật — nuốt con số này là xưởng chạy lịch cũ mà
            // màn báo "xong".
            (r.so_lech_phan_doan
              ? ` Còn ${r.so_lech_phan_doan} việc giữ nguyên lịch cũ vì lần chạy đã tách/gộp lại.`
              : ""),
        );
      }
      setChePrompt(null);
      setLyDo("");
      sau(chonId);
    } catch (e) {
      // Lỗi hiện NGAY TRONG hộp thoại: người dùng đang nhìn vào đây, mà câu server trả về ("gói đã
      // có việc bắt đầu") là câu trả lời cho đúng nút họ vừa bấm.
      setLoiLyDo(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangGhi(false);
    }
  }, [token, chonId, chePrompt, lyDo, sau]);

  const dongPrompt = useCallback(() => {
    setChePrompt(null);
    setLyDo("");
    setLoiLyDo(null);
  }, []);

  const laThuHoi = chePrompt === "thu_hoi";
  const maLenh = ct?.ma ?? `LSX #${chonId}`;

  const kpi = useMemo(() => {
    const tong = dong.length;
    const daPhatHanh = dong.filter((d) => d.trang_thai === "da_phat_hanh").length;
    const tre = dong.filter((d) => (treHan(d) ?? 0) > 0).length;
    const phutChay = phutChayTrongCuaSo(dong, tu, soNgay);
    return { tong, daPhatHanh, tre, tongCho, phutChay };
  }, [dong, tongCho, tu, soNgay]);

  const nhanTuan = `${tu.slice(8)}/${tu.slice(5, 7)}${tu.slice(0, 4) !== den.slice(0, 4) ? `/${tu.slice(0, 4)}` : ""} – ${den.slice(8)}/${den.slice(5, 7)}/${den.slice(0, 4)}`;

  return (
    <div className="xl">
      <header className="xl__dau">
        <div className="xl__tieu-cum">
          <div className="xl__tieu">
            <h1>Xếp lịch</h1>
            <p>Điều độ và lập tiến độ sản xuất lệnh</p>
          </div>

          <div className="xl-kpi-bar">
            <span className="xl-kpi-pill">
              Tuần này: <strong>{kpi.tong}</strong>
            </span>
            <span className="xl-kpi-sep" />
            <span className="xl-kpi-pill xl-kpi-pill--moss">
              Đã phát hành: <strong>{kpi.daPhatHanh}</strong>
            </span>
            <span className="xl-kpi-sep" />
            <span className="xl-kpi-pill xl-kpi-pill--amber">
              Chờ xếp: <strong>{kpi.tongCho}</strong>
            </span>
            <span className="xl-kpi-sep" />
            <span
              className="xl-kpi-pill"
              title="Tổng giờ máy chạy của các lệnh, chỉ tính phần nằm trong khoảng ngày đang xem"
            >
              Giờ chạy trong cửa sổ: <strong>{gioPhut(kpi.phutChay)}</strong>
            </span>
            {kpi.tre > 0 && (
              <>
                <span className="xl-kpi-sep" />
                <span className="xl-kpi-pill xl-kpi-pill--tre">
                  Trễ hạn: <strong>{kpi.tre}</strong>
                </span>
              </>
            )}
          </div>
        </div>

        <div className="xl__tuan">
          <div className="xl-view-switcher">
            <button
              type="button"
              className={`xl-view-btn${soNgay === 7 ? " xl-view-btn--active" : ""}`}
              onClick={() => setSoNgay(7)}
            >
              7 Ngày
            </button>
            <button
              type="button"
              className={`xl-view-btn${soNgay === 14 ? " xl-view-btn--active" : ""}`}
              onClick={() => setSoNgay(14)}
            >
              14 Ngày
            </button>
            <button
              type="button"
              className={`xl-view-btn${soNgay === 30 ? " xl-view-btn--active" : ""}`}
              onClick={() => setSoNgay(30)}
            >
              30 Ngày
            </button>
          </div>

          <button
            type="button"
            className="xl__nut-nay"
            onClick={() => setTu(dauTuan(new Date()))}
          >
            Hôm nay
          </button>
          <div className="xl__tuan-cum">
            <button
              type="button"
              onClick={() => setTu(themNgay(tu, -soNgay))}
              aria-label="Kỳ trước"
            >
              <ChevronLeft size={16} />
            </button>
            <span
              ref={nhanKhoangRef}
              className="xl__tuan-nhan"
              role="button"
              tabIndex={0}
              aria-haspopup="dialog"
              aria-expanded={moKhoang}
              title="Chọn từ ngày đến ngày"
              onClick={batKhoang}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); batKhoang(); } }}
            >
              <Calendar size={13} style={{ color: "var(--ash)" }} />
              {nhanTuan}
            </span>
            <button
              type="button"
              onClick={() => setTu(themNgay(tu, soNgay))}
              aria-label="Kỳ sau"
            >
              <ChevronRight size={16} />
            </button>
          </div>
          {moKhoang && (
            <form
              ref={oKhoangRef}
              className="xl-khoang"
              role="dialog"
              aria-label="Chọn khoảng ngày"
              onSubmit={(e) => {
                e.preventDefault();
                if (loiKhoang) return;
                setTu(nhapTu);
                setSoNgay(soNgayGiua(nhapTu, nhapDen));
                setMoKhoang(false);
              }}
            >
              <label className="xl-khoang__o">
                <span>Từ ngày</span>
                <input
                  type="date"
                  value={nhapTu}
                  min={NGAY_NHAP_MIN}
                  max={NGAY_NHAP_MAX}
                  autoFocus
                  onChange={(e) => setNhapTu(e.target.value)}
                />
              </label>
              <label className="xl-khoang__o">
                <span>Đến ngày</span>
                <input
                  type="date"
                  value={nhapDen}
                  min={/^\d{4}-\d{2}-\d{2}$/.test(nhapTu) ? nhapTu : NGAY_NHAP_MIN}
                  max={NGAY_NHAP_MAX}
                  onChange={(e) => setNhapDen(e.target.value)}
                />
              </label>
              <div className="xl-khoang__chan">
                <span className={loiKhoang ? "xl-khoang__loi" : "xl-khoang__dem"} role={loiKhoang ? "alert" : undefined}>
                  {loiKhoang ?? `${soNgayGiua(nhapTu, nhapDen)} ngày`}
                </span>
                <button type="submit" className="xl-khoang__ap" disabled={!!loiKhoang}>
                  Áp dụng
                </button>
              </div>
            </form>
          )}
        </div>
      </header>

      {/* Băng thông báo NỔI trên mọi lớp phủ. Trước đây nó là khối trong dòng chảy ngay dưới
          header, mà panel lệnh (z-index 100) và hộp lý do (9999) đều là overlay phủ kín + blur —
          nên mọi câu báo trong lúc panel mở đều rơi lên đỉnh trang, mờ tịt sau lưng người dùng.
          Câu báo THÀNH CÔNG chịu đúng lỗi đó và không ai từng thấy nó. */}
      {(loi || bao) && (
        <div className="xl__bangs">
          {loi && (
            <div className="xl__bang xl__bang--loi" role="alert">
              {loi}
              <button type="button" onClick={() => setLoi(null)} aria-label="Đóng thông báo lỗi">
                ×
              </button>
            </div>
          )}
          {bao && (
            <div className="xl__bang xl__bang--bao" role="status">
              {bao}
            </div>
          )}
        </div>
      )}

      {/* Thân trang: 2 cột ngang (Hàng chờ + Lưới Gantt full chiều ngang) */}
      <div className="xl__than">
        <XlHangCho
          the={the}
          tong={tongCho}
          tim={tim}
          trang={trang}
          moiTrang={MOI_TRANG}
          dangTai={taiCho}
          chonId={chonId}
          keoDuoc={suaDuoc}
          isCollapsed={choCollapsed}
          onToggleCollapse={() => setChoCollapsed((c) => !c)}
          onTim={setTim}
          onTrang={setTrang}
          onChon={setChonId}
          onKeo={setKeoTuHangCho}
        />

        <main className="xl__luoi">
          <XlGantt
            tu={tu}
            soNgay={soNgay}
            dong={dong}
            ngayNghi={ngayNghi}
            chonId={chonId}
            suaDuoc={suaDuoc}
            onChon={setChonId}
            onDatMoc={datMoc}
            keoTuHangCho={keoTuHangCho}
          />
        </main>
      </div>

      {/* BOTTOM DOCK INSPECTOR — Hiện dưới đáy khi có lệnh được chọn */}
      {chonId !== null && (
        <XlChiTiet
          ct={ct}
          dangTai={taiCt}
          suaDuoc={suaDuoc}
          duyetDuoc={duyetDuoc}
          dangGhi={dangGhi}
          onDoiGio={(g) => chonId !== null && datMoc(chonId, g, ct?.updated_at ?? null)}
          goi={goi}
          onBoLich={boLich}
          onPhatHanh={phatHanh}
          onThuHoi={() => moPrompt("thu_hoi")}
          onCapNhat={() => moPrompt("cap_nhat")}
          onDong={() => setChonId(null)}
          onSoSanh={(a, b) => api.xepLich.soSanhPhienBan(token ?? "", chonId, a, b)}
        />
      )}

      {/* HỘP THOẠI LÝ DO — dùng chung cho Thu hồi (rút gói về) và Phát hành cập nhật (đẩy lịch
          mới xuống). Hai việc trái chiều nhau nhưng cùng một hình: một ô lý do, cùng ngưỡng 3 ký
          tự, cùng chỗ hiện lỗi server. */}
      {chePrompt !== null && (
        <div
          className="xl-prompt-overlay"
          onClick={(e) => e.target === e.currentTarget && dongPrompt()}
        >
          <div className="xl-prompt-box" role="dialog" aria-modal="true">
            <div className="xl-prompt-head">
              <div className="xl-prompt-icon-wrap">
                {laThuHoi ? <RotateCcw size={20} /> : <Send size={20} />}
              </div>
              <div className="xl-prompt-tieu-wrap">
                <h3 className="xl-prompt-tieu">
                  {laThuHoi ? "Thu hồi phát hành" : "Phát hành cập nhật"}
                </h3>
                <p className="xl-prompt-sub">
                  {laThuHoi ? (
                    <>
                      Thu hồi lệnh <strong>{maLenh}</strong> khỏi danh sách đã phát hành xuống xưởng.
                    </>
                  ) : (
                    <>
                      Đẩy lịch mới xuống xưởng cho <strong>{goi?.so_chua_bat_dau ?? 0} việc chưa bắt đầu</strong>{" "}
                      của lệnh <strong>{maLenh}</strong>. {goi?.so_da_bat_dau ?? 0} việc đã chạy giữ nguyên,
                      tổ nhận việc cập nhật phải xác nhận lại phân công.
                    </>
                  )}
                </p>
              </div>
            </div>
            <div className="xl-prompt-body">
              <label className="xl-prompt-label" htmlFor="xl-ly-do-input">
                {laThuHoi ? "Lý do thu hồi" : "Lý do cập nhật"} <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <textarea
                id="xl-ly-do-input"
                className="xl-prompt-textarea"
                placeholder={laThuHoi
                  ? "Nhập lý do cụ thể (vd: Khách yêu cầu thay đổi thông số tờ in, đổi quy cách...)"
                  : "Nhập lý do cụ thể (vd: Dời giờ chạy do máy in kẹt, đổi sang máy cán 1500...)"}
                value={lyDo}
                onChange={(e) => {
                  setLyDo(e.target.value);
                  if (loiLyDo && e.target.value.trim().length >= 3) setLoiLyDo(null);
                }}
                autoFocus
              />
              {loiLyDo && (
                <div className="xl-prompt-err" id="xl-ly-do-loi" role="alert">
                  {loiLyDo}
                </div>
              )}
            </div>
            <div className="xl-prompt-foot">
              <button type="button" className="xl-nut xl-nut--phu" onClick={dongPrompt} disabled={dangGhi}>
                Hủy
              </button>
              <button
                type="button"
                className={`xl-nut ${laThuHoi ? "xl-nut--thu-hoi" : "xl-nut--chinh"}`}
                onClick={xacNhanPrompt}
                /* CỐ Ý không khoá theo độ dài lý do: nút xám mà không nói vì sao là màn câm —
                   câu giải thích nằm trong `xacNhanPrompt`, mà `disabled` thì `onClick` không nổ,
                   nên người dùng gõ 2 ký tự sẽ kẹt vô hạn. Để nút bấm được, bấm mới hiện lỗi. */
                disabled={dangGhi}
                aria-describedby={loiLyDo ? "xl-ly-do-loi" : undefined}
              >
                {laThuHoi ? <RotateCcw size={13} /> : <Send size={13} />}
                {dangGhi
                  ? "Đang xử lý..."
                  : laThuHoi
                    ? "Xác nhận thu hồi"
                    : "Đẩy lịch mới xuống xưởng"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}