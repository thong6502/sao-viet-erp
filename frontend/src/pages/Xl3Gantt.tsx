// XẾP LỊCH 3 — LƯỚI GANTT (GỌN GÀNG · TINH TẾ · CHUYÊN NGHIỆP)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Xl3Dong } from "../api/client";
import {
  classHan, gio, khoiChay, khoiThucTe, khungBao, khungDaVaoViec, khungLuoi, nhanNgay, ngayNgan,
  pxSangGio, themNgay, thoiLuong, treHan, veDen, veTu, x,
} from "./xl3Shared";

export interface Xl3GanttProps {
  tu: string;
  soNgay?: number;
  dong: Xl3Dong[];
  /** Ngày KHÔNG làm việc trong cửa sổ (YYYY-MM-DD), do máy chủ trả kèm `/lich`. Trước 10/09/2026
   *  chỗ này tự suy "T7 + CN" ngay tại FE, trong khi xưởng khai làm thứ 7 — bàn tô thứ 7 thành
   *  ngày nghỉ còn engine vẫn xếp việc vào đó; lễ và ngày làm bù thì không có đường nào đoán. */
  ngayNghi: string[];
  chonId: number | null;
  suaDuoc: boolean;
  onChon(lsxId: number): void;
  onDatMoc(lsxId: number, batDauAt: string, expectedUpdatedAt: string | null): void;
  keoTuHangCho: number | null;
}

const NGAY_MS = 86_400_000;
const NGUONG_KEO = 4;

/** Bề ngang cửa sổ, có nghe `resize`. Phải là STATE chứ không đọc `innerWidth` lúc render: xoay
 *  máy hay kéo cửa sổ mà số không đổi thì cột nhãn giữ bề rộng cũ trong khi CSS đã co — nhãn và
 *  lưới lệch nhau đúng phần chênh, thanh vẽ sai chỗ. */
function useBeNgangCuaSo(): number {
  const [w, setW] = useState(() => window.innerWidth);
  useEffect(() => {
    const doLai = () => setW(window.innerWidth);
    window.addEventListener("resize", doLai);
    return () => window.removeEventListener("resize", doLai);
  }, []);
  return w;
}

const TRANG_THAI_NHAN: Record<string, string> = {
  nhap: "Nháp",
  cho_bo_sung: "Chờ BS",
  san_sang: "Sẵn sàng",
  da_lap_ke_hoach: "Kế hoạch",
  da_phat_hanh: "Đã phát hành",
};

export function Xl3Gantt({
  tu, soNgay = 7, dong, ngayNghi, chonId, suaDuoc, onChon, onDatMoc, keoTuHangCho,
}: Xl3GanttProps) {
  const nNgay = soNgay ?? 7;
  const nghi = useMemo(() => new Set(ngayNghi ?? []), [ngayNghi]);
  const { nhanW, ngayW, dongH } = khungLuoi(useBeNgangCuaSo(), nNgay);
  const rongLuoi = ngayW * nNgay;
  const ngays = Array.from({ length: nNgay }, (_, i) => themNgay(tu, i));
  const luoiRef = useRef<HTMLDivElement | null>(null);

  // Thống kê tải xưởng theo ngày
  const statsByDay = useMemo(() => {
    const map: Record<string, { count: number; phut: number }> = {};
    for (const d of ngays) {
      map[d] = { count: 0, phut: 0 };
    }
    for (const r of dong) {
      // Đếm theo khoảng VẼ: lệnh chạy dở phải tính vào cả những ngày nó đã chạy, không thì cột
      // ngày nói "9/9 không có lệnh nào" trong khi hôm đó tổ đang làm.
      const bd = veTu(r);
      const kt = veDen(r);
      if (!bd || !kt) continue;
      const bdDay = bd.slice(0, 10);
      const ktDay = kt.slice(0, 10);
      for (const d of ngays) {
        if (d >= bdDay && d <= ktDay) {
          map[d].count += 1;
          map[d].phut += r.chay_phut;
        }
      }
    }
    return map;
  }, [dong, ngays]);

  // Vị trí mốc "Hiện tại"
  const nowX = useMemo(() => {
    const nowIso = new Date().toISOString().slice(0, 19);
    const px = x(nowIso, tu, ngayW);
    return px !== null && px >= 0 && px <= rongLuoi ? px : null;
  }, [tu, rongLuoi, ngayW]);

  const [keo, setKeo] = useState<
    { lsxId: number; lech: number; trai: number; bat: number; diChuyen: boolean } | null
  >(null);
  const keoRef = useRef(keo);
  keoRef.current = keo;

  const xTrongLuoi = useCallback((clientX: number): number => {
    const box = luoiRef.current?.getBoundingClientRect();
    return box ? clientX - box.left - nhanW : 0;
  }, [nhanW]);

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
        trai: Math.max(-ngayW, Math.min(rongLuoi, hienTai - k.lech)),
      });
    };
    const tha = () => {
      const k = keoRef.current;
      setKeo(null);
      if (!k || !k.diChuyen) return;
      const d = dong.find((r) => r.lsx_id === k.lsxId);
      if (!d) return;
      const gioMoi = pxSangGio(k.trai, tu, 15, ngayW);
      if (gioMoi.slice(0, 16) === (d.bat_dau_at ?? "").slice(0, 16)) return;
      onDatMoc(k.lsxId, gioMoi, d.updated_at);
    };
    window.addEventListener("mousemove", di);
    window.addEventListener("mouseup", tha);
    return () => {
      window.removeEventListener("mousemove", di);
      window.removeEventListener("mouseup", tha);
    };
  }, [keo, dong, tu, rongLuoi, ngayW, xTrongLuoi, onDatMoc]);

  const thaVaoLuoi = (e: React.DragEvent) => {
    e.preventDefault();
    if (!suaDuoc || !keoTuHangCho) return;
    onDatMoc(keoTuHangCho, pxSangGio(xTrongLuoi(e.clientX), tu, 15, ngayW), null);
  };

  return (
    <div className="xl3-gantt">
      {/* Header Ngày Lưới Giàu Thông Tin — Adaptive theo N Ngày */}
      <div className="xl3-gantt__head" style={{ paddingLeft: nhanW }}>
        {ngays.map((d) => {
          const n = nhanNgay(d);
          const st = statsByDay[d];
          const hasLoad = st && st.count > 0;
          const ngaySo = d.slice(8, 10); // Lấy số ngày (VD: "10")

          if (nNgay >= 30) {
            return (
              <div
                key={d}
                className={`xl3-gantt__ngay xl3-gantt__ngay--v30${nghi.has(d) ? " xl3-gantt__ngay--nghi" : ""}${n.homNay ? " xl3-gantt__ngay--nay" : ""}`}
                style={{ width: ngayW }}
                title={`${n.thu} ${n.so}${hasLoad ? ` · ${st.count} lệnh` : ""}`}
              >
                <span className="xl3-gantt__so-v30">{ngaySo}</span>
                <span className="xl3-gantt__thu-v30">{n.thu}</span>
                {hasLoad && <span className="xl3-day-dot" />}
              </div>
            );
          }

          if (nNgay >= 14) {
            return (
              <div
                key={d}
                className={`xl3-gantt__ngay xl3-gantt__ngay--v14${nghi.has(d) ? " xl3-gantt__ngay--nghi" : ""}${n.homNay ? " xl3-gantt__ngay--nay" : ""}`}
                style={{ width: ngayW }}
              >
                <div className="xl3-gantt__ngay-dong1">
                  <span className="xl3-gantt__thu">{n.thu}</span>
                  <span className="xl3-gantt__so">{n.so}</span>
                </div>
                {hasLoad && (
                  <span className="xl3-day-badge xl3-day-badge--sm" title={`${st.count} lệnh đang chạy trong ngày`}>
                    {st.count}L
                  </span>
                )}
              </div>
            );
          }

          return (
            <div
              key={d}
              className={`xl3-gantt__ngay xl3-gantt__ngay--v7${nghi.has(d) ? " xl3-gantt__ngay--nghi" : ""}${n.homNay ? " xl3-gantt__ngay--nay" : ""}`}
              style={{ width: ngayW }}
            >
              <div className="xl3-gantt__ngay-dong1">
                <span className="xl3-gantt__thu">{n.thu}</span>
                <span className="xl3-gantt__so">{n.so}</span>
              </div>
              
              {hasLoad && (
                <span className="xl3-day-badge" title={`${st.count} lệnh đang chạy trong ngày`}>
                  {st.count} lệnh
                </span>
              )}
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
        {nowX !== null && (
          <div className="xl3-now-line" style={{ left: nhanW + nowX }}>
            <span className="xl3-now-dot" />
            <span className="xl3-now-pill">HÔM NAY</span>
          </div>
        )}

        {dong.length === 0 && (
          <div className="xl3-trong-box">
            <p>Khung thời gian này chưa có lệnh nào được xếp. Kéo thả một thẻ từ Hàng chờ vào lưới để đặt giờ.</p>
          </div>
        )}

        {dong.map((d) => {
          const dangKeo = keo !== null && keo.lsxId === d.lsx_id && keo.diChuyen;
          const bao = khungBao(d, tu, rongLuoi, ngayW);
          const daVaoViec = khungDaVaoViec(d, tu, rongLuoi, ngayW);
          const traiKeo = dangKeo ? keo!.trai : null;
          const rongThat = bao
            ? ((Date.parse(veDen(d) ?? "") - Date.parse(d.bat_dau_at ?? "")) / NGAY_MS) * ngayW
            : 0;
          const tre = treHan(d);

          return (
            <div
              key={d.lsx_id}
              className={`xl3-hang${chonId === d.lsx_id ? " xl3-hang--chon" : ""}`}
              style={{ height: dongH }}
              onClick={() => onChon(d.lsx_id)}
            >
              {/* Cột nhãn trái (260px màn rộng, co còn 184px khi màn hẹp — xem `khungLuoi`) */}
              <div className="xl3-hang__nhan" style={{ width: nhanW }}>
                <div className="xl3-hang__ma">
                  {d.is_rush && <span className="xl3-gap" title="Lệnh gấp">GẤP</span>}
                  <span className="xl3-hang__ma-text">{d.ma}</span>
                  <span className={`xl3-tt xl3-tt--${d.trang_thai}`}>
                    {TRANG_THAI_NHAN[d.trang_thai] ?? d.trang_thai}
                  </span>
                </div>
                
                {/* Tên sản phẩm nổi bật */}
                {d.ten && (
                  <div className="xl3-hang__ten-sp" title={d.ten}>
                    {d.ten}
                  </div>
                )}

                <div className="xl3-hang__phu" title={`${d.customer_name ?? "Khách lẻ"}${d.so_luong_dat ? ` · ${d.so_luong_dat.toLocaleString("vi-VN")} ${d.don_vi_tinh ?? "sp"}` : ""}${d.may_ten ? ` · ${d.may_ten}` : ""}`}>
                  <span className="xl3-hang__khach">{d.customer_name ?? "Khách lẻ"}</span>
                  {d.so_luong_dat > 0 && (
                    <span className="xl3-hang__sl"> · {d.so_luong_dat.toLocaleString("vi-VN")} {d.don_vi_tinh ?? "sp"}</span>
                  )}
                  {d.may_ten && <span className="xl3-hang__may"> · {d.may_ten}</span>}
                </div>
              </div>

              {/* Lưới Gantt Bar Chuẩn Studio */}
              <div className="xl3-hang__luoi" style={{ width: rongLuoi }}>
                {ngays.map((n, i) => (
                  <span
                    key={n}
                    className={`xl3-cot${nghi.has(n) ? " xl3-cot--nghi" : ""}`}
                    style={{ left: i * ngayW, width: ngayW }}
                  />
                ))}

                {d.han_hoan_thanh_sx && (() => {
                  const hx = x(`${d.han_hoan_thanh_sx}T23:59`, tu, ngayW);
                  return hx !== null && hx >= 0 && hx <= rongLuoi ? (
                    <span className="xl3-han" style={{ left: hx }} title={`Mục tiêu hoàn thành SX ${ngayNgan(d.han_hoan_thanh_sx)}`} />
                  ) : null;
                })()}

                {/* ĐOẠN ĐÃ VÀO VIỆC — cố định, không kéo được. Nó là chuyện đã rồi; cho kéo thì
                    người dùng nắm mép trái sẽ tưởng đang dời cả lệnh, trong khi thứ duy nhất dời
                    được là phần còn lại.
                    HAI LỚP, cố ý: nền nhạt = đã vào việc rồi NẰM CHỜ, khối đậm = máy thật sự quay.
                    Một tông cho cả dải đọc thành "chạy suốt 5 ngày" trong khi máy quay 13 phút. */}
                {daVaoViec && (
                  <div
                    className="xl3-thanh xl3-thanh--cho"
                    style={{ left: daVaoViec.trai, width: daVaoViec.rong }}
                    title={`${d.ma} · vào việc ${gio(d.thuc_bat_dau_lenh)}, chờ tới ${gio(d.bat_dau_at)} — đoạn này không dời được`}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    {khoiThucTe(d.doan_thuc_te, tu, rongLuoi, ngayW).map((k, i) => (
                      <span
                        key={i}
                        className="xl3-that"
                        style={{ left: k.trai - daVaoViec.trai, width: k.rong }}
                        title={`Máy chạy thật: ${gio(k.tu)} → ${gio(k.den)}`}
                      />
                    ))}
                  </div>
                )}

                {bao && (
                  <div
                    className={`xl3-thanh ${classHan(d)}${dangKeo ? " xl3-thanh--keo" : ""}${d.trang_thai === "da_phat_hanh" ? " xl3-thanh--phat" : ""}`}
                    style={{
                      left: traiKeo ?? bao.trai,
                      width: traiKeo !== null ? Math.max(12, rongThat) : bao.rong,
                    }}
                    title={`${d.ma} · ${d.ten ?? ""} · ${d.thuc_bat_dau_lenh ? "phần còn lại " : ""}${gio(d.bat_dau_at)} → ${gio(veDen(d))} · Chạy ${thoiLuong(d.chay_phut)}, nghỉ ${thoiLuong(d.nghi_ngoai_ca_phut)}`}
                    onMouseDown={(e) => {
                      if (!suaDuoc || e.button !== 0) return;
                      e.preventDefault();
                      const mep = x(d.bat_dau_at, tu, ngayW) ?? 0;
                      const bat = xTrongLuoi(e.clientX);
                      setKeo({ lsxId: d.lsx_id, lech: bat - mep, trai: mep, bat, diChuyen: false });
                    }}
                  >
                    {bao.tranTrai && <span className="xl3-thanh__mui xl3-thanh__mui--trai" />}
                    
                    {/* Các đường phân chia đoạn công đoạn mảnh & sắc nét */}
                    {khoiChay(d.doan, tu, rongLuoi, ngayW).map((k, i) => (
                      <span
                        key={i}
                        className="xl3-khoi"
                        style={{
                          left: k.trai - (traiKeo !== null ? (x(d.bat_dau_at, tu, ngayW) ?? 0) : bao.trai),
                          width: k.rong,
                        }}
                      />
                    ))}

                    {/* Nhãn tiến độ tích hợp thanh Gantt chuẩn gọn gàng */}
                    <span className="xl3-thanh__ten">
                      <strong>{d.ma}</strong>
                      {d.ten ? ` · ${d.ten}` : ""}
                      {d.so_luong_dat ? ` (${d.so_luong_dat.toLocaleString("vi-VN")} ${d.don_vi_tinh ?? "sp"})` : ""}
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


