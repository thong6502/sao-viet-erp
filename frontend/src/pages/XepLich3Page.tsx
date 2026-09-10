// XẾP LỊCH 3 — bàn xếp lịch cấp LỆNH SẢN XUẤT (module quyền `xep_lich_3`).
//
// MỤC TIÊU DUY NHẤT của màn: người dùng đặt GIỜ BẮT ĐẦU cho một lệnh, hệ trả NGÀY KẾT THÚC. Ngày
// kết thúc = tổng giờ chạy các bước + nghỉ giữa ca + thời gian ngoài ca. Không gán máy, không gán
// tổ, không xếp từng công đoạn — đó là màn 2 (đã ẩn theo cờ `XEP_LICH_2_ENABLED`).
//
// KHÔNG CHẶN GÌ HẾT: không cửa vật tư, không cửa hạn, phát hành bấm là đi. Lệnh trễ hạn vẫn xếp
// được, chỉ đổi màu để người điều độ tự quyết. Đây là yêu cầu nghiệp vụ, đừng "sửa lại" thành gate.
//
// Ba mảnh: HÀNG CHỜ (trái, kéo thẻ ra lưới) · GANTT 7 ngày (giữa, kéo thanh để dời giờ) · PANEL
// (phải, thông tin thật của lệnh + bảng công đoạn + nút phát hành). Real-time qua `eventTick` —
// AppShell bơm vào mỗi lần có SSE, cả ba mảnh tự nạp lại.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type Xl3ChiTiet as Xl3ChiTietData, type Xl3Dong, type Xl3The } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { useDebounced } from "../utils/useDebounced";
import { Xl3ChiTiet } from "./Xl3ChiTiet";
import { Xl3Gantt } from "./Xl3Gantt";
import { Xl3HangCho } from "./Xl3HangCho";
import { SO_NGAY, dauTuan, themNgay } from "./xl3Shared";
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

  const [tu, setTu] = useState<string>(() => dauTuan(new Date()));
  const den = useMemo(() => themNgay(tu, SO_NGAY - 1), [tu]);

  const [dong, setDong] = useState<Xl3Dong[]>([]);
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
  // Nhịp nạp lại NỘI BỘ: mọi lần ghi bump lên một nhịp, ba effect dưới cùng ăn theo. Không gọi
  // tay ba hàm nạp ở từng chỗ ghi — sót một chỗ là màn hiện số cũ mà không ai biết.
  const [nhip, setNhip] = useState(0);
  const lamMoi = useCallback(() => setNhip((n) => n + 1), []);

  // Thông báo tự tắt — băng đứng mãi thì lần trượt giờ sau người dùng tưởng là thông báo cũ.
  const hetGio = useRef<number | null>(null);
  useEffect(() => {
    if (!bao) return;
    if (hetGio.current) window.clearTimeout(hetGio.current);
    hetGio.current = window.setTimeout(() => setBao(null), 6000);
    return () => {
      if (hetGio.current) window.clearTimeout(hetGio.current);
    };
  }, [bao]);

  // ---------------------------------------------------------------- nạp
  useEffect(() => {
    if (!token) return;
    let huy = false;
    api.xepLich3
      .lich(token, { tu, den })
      .then((r) => !huy && setDong(r.dong))
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

  // Đổi từ khoá tìm ⇒ về trang 1, không thì gõ xong đứng ở trang 3 rỗng.
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
        // Băng lấy NGUYÊN câu của server: nó biết đã trượt sang mốc nào, màn đoán lại là sai.
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

  const thuHoi = useCallback(async () => {
    if (!token || chonId === null) return;
    // Lý do là cái VẾT của một quyết định đã thả xuống xưởng — server bắt buộc, hỏi thẳng ở đây
    // thay vì để người dùng ăn lỗi 400 rồi mới biết.
    const lyDo = window.prompt("Lý do thu hồi phát hành (ít nhất 3 ký tự):")?.trim();
    if (!lyDo || lyDo.length < 3) return;
    setDangGhi(true);
    try {
      await api.xepLich3.thuHoi(token, chonId, lyDo);
      setBao("Đã thu hồi phát hành.");
      sau(chonId);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thu hồi được.");
    } finally {
      setDangGhi(false);
    }
  }, [token, chonId, sau]);

  // ---------------------------------------------------------------- vẽ
  const nhanTuan = `${tu.slice(8)}/${tu.slice(5, 7)} – ${den.slice(8)}/${den.slice(5, 7)}/${den.slice(0, 4)}`;

  return (
    <div className="xl3">
      <header className="xl3__dau">
        <div className="xl3__tieu">
          <h1>Xếp lịch</h1>
          <p>
            Đặt giờ bắt đầu cho một lệnh — hệ tự cộng giờ chạy các bước, nghỉ giữa ca và thời gian
            ngoài ca để ra ngày kết thúc.
          </p>
        </div>
        <div className="xl3__tuan">
          <button type="button" onClick={() => setTu(themNgay(tu, -SO_NGAY))} aria-label="Tuần trước">
            ‹
          </button>
          <button type="button" className="xl3__nay" onClick={() => setTu(dauTuan(new Date()))}>
            {nhanTuan}
          </button>
          <button type="button" onClick={() => setTu(themNgay(tu, SO_NGAY))} aria-label="Tuần sau">
            ›
          </button>
        </div>
      </header>

      {loi && (
        <div className="xl3__bang xl3__bang--loi" role="alert">
          {loi}
          <button type="button" onClick={() => setLoi(null)}>
            ×
          </button>
        </div>
      )}
      {bao && (
        <div className="xl3__bang xl3__bang--bao" role="status">
          {bao}
        </div>
      )}

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
          onTim={setTim}
          onTrang={setTrang}
          onChon={setChonId}
          onKeo={setKeoTuHangCho}
        />

        <main className="xl3__luoi">
          <Xl3Gantt
            tu={tu}
            dong={dong}
            chonId={chonId}
            suaDuoc={suaDuoc}
            onChon={setChonId}
            onDatMoc={datMoc}
            keoTuHangCho={keoTuHangCho}
          />
        </main>

        <Xl3ChiTiet
          ct={ct}
          dangTai={taiCt}
          suaDuoc={suaDuoc}
          duyetDuoc={duyetDuoc}
          dangGhi={dangGhi}
          onDoiGio={(g) => chonId !== null && datMoc(chonId, g, ct?.updated_at ?? null)}
          onBoLich={boLich}
          onPhatHanh={phatHanh}
          onThuHoi={thuHoi}
          onDong={() => setChonId(null)}
        />
      </div>
    </div>
  );
}