// XẾP LỊCH 3 — BÀN XẾP LỊCH CẤP LỆNH SẢN XUẤT (BOTTOM DOCK STUDIO LAYOUT)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, RotateCcw, Send } from "lucide-react";
import {
  ApiError, api,
  type Xl3ChiTiet as Xl3ChiTietData, type Xl3Dong, type Xl3GoiPhatHanh, type Xl3The,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { useDebounced } from "../utils/useDebounced";
import { Xl3ChiTiet } from "./Xl3ChiTiet";
import { Xl3Gantt } from "./Xl3Gantt";
import { Xl3HangCho } from "./Xl3HangCho";
import { dauTuan, themNgay, treHan } from "./xl3Shared";
import "./xep-lich-3.css";

const MOI_TRANG = 20;

export function XepLich3Page({
  eventTick = 0,
  onBadgeStale,
}: {
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can("xep_lich_3", "update");
  const duyetDuoc = can("xep_lich_3", "approve");

  const [soNgay, setSoNgay] = useState<number>(7);
  const [tu, setTu] = useState<string>(() => dauTuan(new Date()));
  const den = useMemo(() => themNgay(tu, soNgay - 1), [tu, soNgay]);

  const [dong, setDong] = useState<Xl3Dong[]>([]);
  // Ngày không làm việc của ĐÚNG cửa sổ đang xem — lễ, làm bù, cấu hình tuần. Đi kèm `/lich` chứ
  // không hỏi riêng: cùng một lượt, cùng một nguồn với lịch đang vẽ.
  const [ngayNghi, setNgayNghi] = useState<string[]>([]);
  const [the, setThe] = useState<Xl3The[]>([]);
  const [tongCho, setTongCho] = useState(0);
  const [tim, setTim] = useState("");
  const timCho = useDebounced(tim, 300);
  const [trang, setTrang] = useState(1);

  const [chonId, setChonId] = useState<number | null>(null);
  const [ct, setCt] = useState<Xl3ChiTietData | null>(null);
  const [taiCt, setTaiCt] = useState(false);
  const [dangGhi, setDangGhi] = useState(false);
  const [taiCho, setTaiCho] = useState(false);

  const [loi, setLoi] = useState<string | null>(null);
  const [bao, setBao] = useState<string | null>(null);
  const [keoTuHangCho, setKeoTuHangCho] = useState<number | null>(null);
  const [nhip, setNhip] = useState(0);
  const lamMoi = useCallback(() => setNhip((n) => n + 1), []);

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
  const [goi, setGoi] = useState<Xl3GoiPhatHanh | null>(null);

  // ---------------------------------------------------------------- nạp
  useEffect(() => {
    if (!token) return;
    let huy = false;
    api.xepLich3
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
    api.xepLich3
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
    api.xepLich3
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
    api.xepLich3
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
      try {
        const r = await api.xepLich3.datMoc(token, lsxId, batDauAt, expected);
        setBao(r.thong_bao ?? null);
        sau(lsxId);
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
    [token, suaDuoc, sau, lamMoi],
  );

  const boLich = useCallback(async () => {
    if (!token || chonId === null) return;
    setDangGhi(true);
    try {
      await api.xepLich3.xoaMoc(token, chonId);
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
      await api.xepLich3.phatHanh(token, chonId);
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
        await api.xepLich3.thuHoi(token, chonId, ld);
        setBao("Đã thu hồi phát hành.");
      } else {
        const r = await api.xepLich3.phatHanhCapNhat(token, chonId, ld);
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
    return { tong, daPhatHanh, tre, tongCho };
  }, [dong, tongCho]);

  const nhanTuan = `${tu.slice(8)}/${tu.slice(5, 7)} – ${den.slice(8)}/${den.slice(5, 7)}/${den.slice(0, 4)}`;

  return (
    <div className="xl3">
      <header className="xl3__dau">
        <div className="xl3__tieu-cum">
          <div className="xl3__tieu">
            <h1>Xếp lịch</h1>
            <p>Điều độ và lập tiến độ sản xuất lệnh</p>
          </div>

          <div className="xl3-kpi-bar">
            <span className="xl3-kpi-pill">
              Tuần này: <strong>{kpi.tong}</strong>
            </span>
            <span className="xl3-kpi-sep" />
            <span className="xl3-kpi-pill xl3-kpi-pill--moss">
              Đã phát hành: <strong>{kpi.daPhatHanh}</strong>
            </span>
            <span className="xl3-kpi-sep" />
            <span className="xl3-kpi-pill xl3-kpi-pill--amber">
              Chờ xếp: <strong>{kpi.tongCho}</strong>
            </span>
            {kpi.tre > 0 && (
              <>
                <span className="xl3-kpi-sep" />
                <span className="xl3-kpi-pill xl3-kpi-pill--tre">
                  Trễ hạn: <strong>{kpi.tre}</strong>
                </span>
              </>
            )}
          </div>
        </div>

        <div className="xl3__tuan">
          <div className="xl3-view-switcher">
            <button
              type="button"
              className={`xl3-view-btn${soNgay === 7 ? " xl3-view-btn--active" : ""}`}
              onClick={() => setSoNgay(7)}
            >
              7 Ngày
            </button>
            <button
              type="button"
              className={`xl3-view-btn${soNgay === 14 ? " xl3-view-btn--active" : ""}`}
              onClick={() => setSoNgay(14)}
            >
              14 Ngày
            </button>
            <button
              type="button"
              className={`xl3-view-btn${soNgay === 30 ? " xl3-view-btn--active" : ""}`}
              onClick={() => setSoNgay(30)}
            >
              30 Ngày
            </button>
          </div>

          <button
            type="button"
            className="xl3__nut-nay"
            onClick={() => setTu(dauTuan(new Date()))}
          >
            Hôm nay
          </button>
          <div className="xl3__tuan-cum">
            <button
              type="button"
              onClick={() => setTu(themNgay(tu, -soNgay))}
              aria-label="Kỳ trước"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="xl3__tuan-nhan" onClick={() => setTu(dauTuan(new Date()))}>
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
        </div>
      </header>

      {/* Băng thông báo NỔI trên mọi lớp phủ. Trước đây nó là khối trong dòng chảy ngay dưới
          header, mà panel lệnh (z-index 100) và hộp lý do (9999) đều là overlay phủ kín + blur —
          nên mọi câu báo trong lúc panel mở đều rơi lên đỉnh trang, mờ tịt sau lưng người dùng.
          Câu báo THÀNH CÔNG chịu đúng lỗi đó và không ai từng thấy nó. */}
      {(loi || bao) && (
        <div className="xl3__bangs">
          {loi && (
            <div className="xl3__bang xl3__bang--loi" role="alert">
              {loi}
              <button type="button" onClick={() => setLoi(null)} aria-label="Đóng thông báo lỗi">
                ×
              </button>
            </div>
          )}
          {bao && (
            <div className="xl3__bang xl3__bang--bao" role="status">
              {bao}
            </div>
          )}
        </div>
      )}

      {/* Thân trang: 2 cột ngang (Hàng chờ + Lưới Gantt full chiều ngang) */}
      <div className="xl3__than">
        <Xl3HangCho
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

        <main className="xl3__luoi">
          <Xl3Gantt
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
        <Xl3ChiTiet
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
          onSoSanh={(a, b) => api.xepLich3.soSanhPhienBan(token ?? "", chonId, a, b)}
        />
      )}

      {/* HỘP THOẠI LÝ DO — dùng chung cho Thu hồi (rút gói về) và Phát hành cập nhật (đẩy lịch
          mới xuống). Hai việc trái chiều nhau nhưng cùng một hình: một ô lý do, cùng ngưỡng 3 ký
          tự, cùng chỗ hiện lỗi server. */}
      {chePrompt !== null && (
        <div
          className="xl3-prompt-overlay"
          onClick={(e) => e.target === e.currentTarget && dongPrompt()}
        >
          <div className="xl3-prompt-box" role="dialog" aria-modal="true">
            <div className="xl3-prompt-head">
              <div className="xl3-prompt-icon-wrap">
                {laThuHoi ? <RotateCcw size={20} /> : <Send size={20} />}
              </div>
              <div className="xl3-prompt-tieu-wrap">
                <h3 className="xl3-prompt-tieu">
                  {laThuHoi ? "Thu hồi phát hành" : "Phát hành cập nhật"}
                </h3>
                <p className="xl3-prompt-sub">
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
            <div className="xl3-prompt-body">
              <label className="xl3-prompt-label" htmlFor="xl3-ly-do-input">
                {laThuHoi ? "Lý do thu hồi" : "Lý do cập nhật"} <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <textarea
                id="xl3-ly-do-input"
                className="xl3-prompt-textarea"
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
                <div className="xl3-prompt-err" id="xl3-ly-do-loi" role="alert">
                  {loiLyDo}
                </div>
              )}
            </div>
            <div className="xl3-prompt-foot">
              <button type="button" className="xl3-nut xl3-nut--phu" onClick={dongPrompt} disabled={dangGhi}>
                Hủy
              </button>
              <button
                type="button"
                className={`xl3-nut ${laThuHoi ? "xl3-nut--thu-hoi" : "xl3-nut--chinh"}`}
                onClick={xacNhanPrompt}
                /* CỐ Ý không khoá theo độ dài lý do: nút xám mà không nói vì sao là màn câm —
                   câu giải thích nằm trong `xacNhanPrompt`, mà `disabled` thì `onClick` không nổ,
                   nên người dùng gõ 2 ký tự sẽ kẹt vô hạn. Để nút bấm được, bấm mới hiện lỗi. */
                disabled={dangGhi}
                aria-describedby={loiLyDo ? "xl3-ly-do-loi" : undefined}
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