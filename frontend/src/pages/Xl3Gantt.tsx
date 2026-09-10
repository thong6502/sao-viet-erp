// XẾP LỊCH 3 — LƯỚI GANTT cấp LỆNH SẢN XUẤT.
//
// Một dòng = MỘT lệnh. Thanh vẽ HAI LỚP:
//   · lớp NHẠT  = dấu chân trên lịch, từ giờ bắt đầu tới giờ kết thúc;
//   · lớp ĐẬM   = các đoạn máy thực sự chạy.
// Khoảng hở giữa hai khối đậm chính là nghỉ giữa ca / ngoài ca / ngày nghỉ — nó là câu trả lời cho
// "vì sao thanh dài hơn giờ chạy?", nên KHÔNG được lấp cho đẹp.
//
// Sắc độ khối đậm mã hoá THỨ TỰ bước (bước 1 nhạt dần tới bước cuối), KHÔNG mã hoá loại bước: người
// nhìn cần thấy "chạy tới đoạn nào rồi", còn loại bước đã có ở bảng công đoạn trong panel.
//
// KÉO-THẢ đổi giờ bắt đầu là thao tác chính của màn. Kéo bằng chuột trên thanh, hoặc thả thẻ hàng
// chờ vào lưới. Cả hai đều làm tròn về bội 15 phút và đều đi qua ĐÚNG một đường ghi (`onDatMoc`).
import { useCallback, useEffect, useRef, useState } from "react";
import type { Xl3Dong } from "../api/client";
import {
  DONG_H, NGAY_W, NHAN_W, SO_NGAY,
  classHan, cuoiTuan, gio, khoiChay, khungBao, nhanNgay, ngayNgan, pxSangGio, themNgay, thoiLuong,
  treHan, x,
} from "./xl3Shared";

export interface Xl3GanttProps {
  tu: string;
  dong: Xl3Dong[];
  chonId: number | null;
  /** Cho phép sửa lịch (quyền `update`). Tắt thì lưới chỉ để xem — không kéo, không nhận thả. */
  suaDuoc: boolean;
  onChon(lsxId: number): void;
  onDatMoc(lsxId: number, batDauAt: string, expectedUpdatedAt: string | null): void;
  /** Thẻ hàng chờ đang được kéo (set bởi cột trái) — lưới nhận thả để xếp lần đầu. */
  keoTuHangCho: number | null;
}

const NGAY_MS = 86_400_000;
/** Ngưỡng nhả kéo (px). Dưới ngưỡng coi như BẤM CHỌN, không ghi gì. */
const NGUONG_KEO = 4;

export function Xl3Gantt({
  tu, dong, chonId, suaDuoc, onChon, onDatMoc, keoTuHangCho,
}: Xl3GanttProps) {
  const rongLuoi = NGAY_W * SO_NGAY;
  const ngays = Array.from({ length: SO_NGAY }, (_, i) => themNgay(tu, i));
  const luoiRef = useRef<HTMLDivElement | null>(null);

  // Kéo thanh: giữ nguyên OFFSET chỗ bấm so với mép trái thanh, không snap mép thanh về con trỏ —
  // bấm giữa thanh mà thanh nhảy sao cho mép trái trùng chuột là cảm giác "mất kiểm soát".
  //
  // `diChuyen` là NGƯỠNG NHẢ: chỉ coi là kéo khi con trỏ đã đi quá NGUONG_KEO px kể từ chỗ bấm.
  // Thiếu nó thì một cú BẤM để mở panel cũng chạy nốt đường ghi — chuột rung 1px, hoặc trình duyệt
  // bắn thêm mousemove giữa down và up, là lệnh tự dời giờ mà người dùng không hề kéo.
  const [keo, setKeo] = useState<
    { lsxId: number; lech: number; trai: number; bat: number; diChuyen: boolean } | null
  >(null);
  const keoRef = useRef(keo);
  keoRef.current = keo;

  // Đo từ THÂN lưới rồi trừ cột nhãn, KHÔNG đo từ dòng đầu tiên: lưới rỗng thì không có dòng nào
  // để đo, mà đúng lúc đó mới cần thả thẻ đầu tiên vào.
  const xTrongLuoi = useCallback((clientX: number): number => {
    const box = luoiRef.current?.getBoundingClientRect();
    return box ? clientX - box.left - NHAN_W : 0;
  }, []);

  useEffect(() => {
    if (!keo) return;
    const di = (e: MouseEvent) => {
      const k = keoRef.current;
      if (!k) return;
      const hienTai = xTrongLuoi(e.clientX);
      const daDi = k.diChuyen || Math.abs(hienTai - k.bat) >= NGUONG_KEO;
      if (!daDi) return;
      setKeo({
        ...k,
        diChuyen: true,
        trai: Math.max(-NGAY_W, Math.min(rongLuoi, hienTai - k.lech)),
      });
    };
    const tha = () => {
      const k = keoRef.current;
      setKeo(null);
      if (!k || !k.diChuyen) return;   // bấm chọn, không phải kéo
      const d = dong.find((r) => r.lsx_id === k.lsxId);
      if (!d) return;
      const gioMoi = pxSangGio(k.trai, tu);
      if (gioMoi.slice(0, 16) === (d.bat_dau_at ?? "").slice(0, 16)) return;  // không nhúc nhích
      onDatMoc(k.lsxId, gioMoi, d.updated_at);
    };
    window.addEventListener("mousemove", di);
    window.addEventListener("mouseup", tha);
    return () => {
      window.removeEventListener("mousemove", di);
      window.removeEventListener("mouseup", tha);
    };
  }, [keo, dong, tu, rongLuoi, xTrongLuoi, onDatMoc]);

  const thaVaoLuoi = (e: React.DragEvent) => {
    e.preventDefault();
    if (!suaDuoc || !keoTuHangCho) return;
    onDatMoc(keoTuHangCho, pxSangGio(xTrongLuoi(e.clientX), tu), null);
  };

  return (
    <div className="xl3-gantt">
      <div className="xl3-gantt__head" style={{ paddingLeft: NHAN_W }}>
        {ngays.map((d) => {
          const n = nhanNgay(d);
          return (
            <div
              key={d}
              className={`xl3-gantt__ngay${cuoiTuan(d) ? " xl3-gantt__ngay--nghi" : ""}${n.homNay ? " xl3-gantt__ngay--nay" : ""}`}
              style={{ width: NGAY_W }}
            >
              <span className="xl3-gantt__thu">{n.thu}</span>
              <span className="xl3-gantt__so">{n.so}</span>
            </div>
          );
        })}
      </div>

      <div
        className={`xl3-gantt__body${keoTuHangCho ? " xl3-gantt__body--nhan" : ""}`}
        ref={luoiRef}
        onDragOver={(e) => suaDuoc && keoTuHangCho && e.preventDefault()}
        onDrop={thaVaoLuoi}
      >
        {dong.length === 0 && (
          <p className="xl3-trong">
            Tuần này chưa có lệnh nào được xếp. Kéo một thẻ từ <strong>Hàng chờ</strong> vào lưới để
            đặt giờ bắt đầu.
          </p>
        )}
        {dong.map((d) => {
          const dangKeo = keo !== null && keo.lsxId === d.lsx_id && keo.diChuyen;
          const bao = khungBao(d, tu, rongLuoi);
          const traiKeo = dangKeo ? keo!.trai : null;
          const rongThat = bao
            ? ((Date.parse(d.ket_thuc ?? "") - Date.parse(d.bat_dau_at ?? "")) / NGAY_MS) * NGAY_W
            : 0;
          const tre = treHan(d);
          return (
            <div
              key={d.lsx_id}
              className={`xl3-hang${chonId === d.lsx_id ? " xl3-hang--chon" : ""}`}
              style={{ height: DONG_H }}
              onClick={() => onChon(d.lsx_id)}
            >
              <div className="xl3-hang__nhan" style={{ width: NHAN_W }}>
                <div className="xl3-hang__ma">
                  {d.is_rush && <span className="xl3-gap" title="Lệnh gấp">GẤP</span>}
                  <strong>{d.ma}</strong>
                </div>
                <div className="xl3-hang__phu">
                  {d.customer_name ?? "—"}
                  {d.may_ten ? ` · ${d.may_ten}` : ""}
                </div>
              </div>

              <div className="xl3-hang__luoi" style={{ width: rongLuoi }}>
                {ngays.map((n, i) => (
                  <span
                    key={n}
                    className={`xl3-cot${cuoiTuan(n) ? " xl3-cot--nghi" : ""}`}
                    style={{ left: i * NGAY_W, width: NGAY_W }}
                  />
                ))}
                {d.han_hoan_thanh_sx && (() => {
                  const hx = x(`${d.han_hoan_thanh_sx}T23:59`, tu);
                  return hx !== null && hx >= 0 && hx <= rongLuoi ? (
                    <span className="xl3-han" style={{ left: hx }} title={`Hạn SX ${ngayNgan(d.han_hoan_thanh_sx)}`} />
                  ) : null;
                })()}

                {bao && (
                  <div
                    className={`xl3-thanh ${classHan(d)}${dangKeo ? " xl3-thanh--keo" : ""}${d.trang_thai === "da_phat_hanh" ? " xl3-thanh--phat" : ""}`}
                    style={{
                      left: traiKeo ?? bao.trai,
                      width: traiKeo !== null ? Math.max(6, rongThat) : bao.rong,
                    }}
                    title={`${d.ma} · ${gio(d.bat_dau_at)} → ${gio(d.ket_thuc)} · chạy ${thoiLuong(d.chay_phut)}, nghỉ ${thoiLuong(d.nghi_ngoai_ca_phut)}`}
                    onMouseDown={(e) => {
                      if (!suaDuoc || e.button !== 0) return;
                      e.preventDefault();
                      const mep = x(d.bat_dau_at, tu) ?? 0;
                      const bat = xTrongLuoi(e.clientX);
                      setKeo({ lsxId: d.lsx_id, lech: bat - mep, trai: mep, bat, diChuyen: false });
                    }}
                  >
                    {bao.tranTrai && <span className="xl3-thanh__mui xl3-thanh__mui--trai" />}
                    {/* Khối đậm tính theo px TUYỆT ĐỐI trên lưới; đặt vào trong thanh thì trừ đi
                        mép trái của chính thanh. Lúc đang kéo, thanh vẽ nguyên chiều dài thật từ
                        mốc bắt đầu THẬT, nên trừ mốc đó — trừ mép đã kẹp cửa sổ là khối trượt. */}
                    {khoiChay(d.doan, tu, rongLuoi).map((k, i) => (
                      <span
                        key={i}
                        className={`xl3-khoi xl3-khoi--${k.buocIndex % 4}`}
                        style={{
                          left: k.trai - (traiKeo !== null ? (x(d.bat_dau_at, tu) ?? 0) : bao.trai),
                          width: k.rong,
                        }}
                      />
                    ))}
                    <span className="xl3-thanh__chu">
                      {gio(d.bat_dau_at)} → {gio(d.ket_thuc)}
                    </span>
                    {bao.tranPhai && <span className="xl3-thanh__mui xl3-thanh__mui--phai" />}
                  </div>
                )}
                {tre !== null && tre > 0 && bao && (
                  <span className="xl3-tre-chip" style={{ left: bao.trai + bao.rong + 6 }}>
                    trễ {tre} ngày
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
