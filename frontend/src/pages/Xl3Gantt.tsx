// XẾP LỊCH 3 — LƯỚI GANTT (GỌN GÀNG · TINH TẾ · CHUYÊN NGHIỆP)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, Layers, Sparkles, Target, Truck } from "lucide-react";
import type { Xl3Dong } from "../api/client";
import {
  classHan, gio, gioChu, khoiChay, khoiThucTe, khungBao, khungDaVaoViec, khungLuoi, nacCuaSo, nhanNgay, ngayGio, ngayNgan,
  pxSangGio, themNgay, treHan, veDen, veTu, x,
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
  /** Trả Promise thì thanh ĐỨNG YÊN chỗ vừa thả cho tới khi lưu xong — không nháy về chỗ cũ. */
  onDatMoc(lsxId: number, batDauAt: string, expectedUpdatedAt: string | null): void | Promise<void>;
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
  const nac = nacCuaSo(nNgay);
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
  // Vừa thả một thanh đã KÉO ⇒ nuốt cú `click` trình duyệt bắn ngay sau `mouseup`, không thì dòng
  // nhận click và popup chi tiết bật lên sau mỗi lần kéo. Tự tắt ở lượt kế tiếp của vòng sự kiện:
  // thả ra ngoài dòng thì không có click nào để nuốt, cờ không được treo sang cú bấm thật sau đó.
  const vuaKeoRef = useRef(false);
  // Thanh vừa thả, ĐANG LƯU: giữ nó ở chỗ thả. Xoá trạng thái kéo mà không giữ thì thanh vẽ lại
  // theo mốc CŨ trong lúc chờ máy chủ — người dùng thấy nó bật về rồi mới nhảy sang.
  const [choLuu, setChoLuu] = useState<{ lsxId: number; trai: number } | null>(null);

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
      vuaKeoRef.current = true;
      window.setTimeout(() => { vuaKeoRef.current = false; }, 0);
      const d = dong.find((r) => r.lsx_id === k.lsxId);
      if (!d) return;
      const gioMoi = pxSangGio(k.trai, tu, 15, ngayW);
      if (gioMoi.slice(0, 16) === (d.bat_dau_at ?? "").slice(0, 16)) return;
      setChoLuu({ lsxId: k.lsxId, trai: k.trai });
      Promise.resolve(onDatMoc(k.lsxId, gioMoi, d.updated_at)).finally(() => setChoLuu(null));
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

          if (nac === 30) {
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

          if (nac === 14) {
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
          <div className="xl3-gantt__empty-container">
            {/* Hàng lưới rỗng tạo background chuẩn cho khung Gantt */}
            {Array.from({ length: 6 }).map((_, idx) => (
              <div key={idx} className="xl3-hang xl3-hang--trong" style={{ height: dongH }}>
                <div className="xl3-hang__nhan" style={{ width: nhanW }} />
                <div className="xl3-hang__luoi" style={{ width: rongLuoi }}>
                  {ngays.map((n, i) => (
                    <span
                      key={n}
                      className={`xl3-cot${nghi.has(n) ? " xl3-cot--nghi" : ""}`}
                      style={{ left: i * ngayW, width: ngayW }}
                    />
                  ))}
                </div>
              </div>
            ))}

            {/* Box thông báo trống căn chỉnh chuẩn giữa vùng lịch */}
            <div className="xl3-trong-box-wrap" style={{ paddingLeft: nhanW }}>
              <div className="xl3-trong-box">
                <div className="xl3-trong-icon-wrap">
                  <CalendarDays size={24} />
                </div>
                <h3>Khung thời gian chưa có lệnh xếp</h3>
                <p>
                  Kéo thả một thẻ từ <strong>Hàng chờ</strong> ở bên trái vào ô thời gian tương ứng trên lưới để đặt giờ sản xuất.
                </p>
                <div className={`xl3-trong-hint${keoTuHangCho ? " xl3-trong-hint--active" : ""}`}>
                  {keoTuHangCho ? (
                    <>
                      <Sparkles size={14} />
                      <span>Thả thẻ vào lưới để đặt mốc xếp lịch</span>
                    </>
                  ) : (
                    <>
                      <Layers size={14} />
                      <span>Kéo thẻ từ Hàng chờ vào đây</span>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {dong.map((d) => {
          const dangKeo = keo !== null && keo.lsxId === d.lsx_id && keo.diChuyen;
          const bao = khungBao(d, tu, rongLuoi, ngayW);
          const daVaoViec = khungDaVaoViec(d, tu, rongLuoi, ngayW);
          const traiKeo = dangKeo ? keo!.trai : choLuu?.lsxId === d.lsx_id ? choLuu.trai : null;
          const rongThat = bao
            ? ((Date.parse(veDen(d) ?? "") - Date.parse(d.bat_dau_at ?? "")) / NGAY_MS) * ngayW
            : 0;
          const tre = treHan(d);

          return (
            <div
              key={d.lsx_id}
              className={`xl3-hang${chonId === d.lsx_id ? " xl3-hang--chon" : ""}`}
              style={{ height: dongH }}
              onClick={() => { if (!vuaKeoRef.current) onChon(d.lsx_id); }}
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

                <div className="xl3-hang__dong-khach">
                  <div className="xl3-hang__phu" title={`${d.customer_name ?? "Khách lẻ"}${d.may_ten ? ` · ${d.may_ten}` : ""}`}>
                    <span className="xl3-hang__khach">{d.customer_name ?? "Khách lẻ"}</span>
                    {d.may_ten && <span className="xl3-hang__may"> · {d.may_ten}</span>}
                  </div>
                  {tre !== null && tre > 0 && (
                    <span className="xl3-hang__tre" title={`Dự kiến xong sau hạn SX ${tre} ngày`}>Trễ hạn</span>
                  )}
                </div>

                {/* Sản lượng · số tờ in · con/tờ — ba số người điều độ đọc để ước độ nặng của lệnh. */}
                {(() => {
                  const sl = [
                    d.so_luong_dat > 0 ? `${d.so_luong_dat.toLocaleString("vi-VN")} ${d.don_vi_tinh ?? "sp"}` : null,
                    d.so_to_ke_hoach > 0 ? `${d.so_to_ke_hoach.toLocaleString("vi-VN")} tờ` : null,
                    `${d.so_con} con/tờ`,
                  ].filter(Boolean).join(" · ");
                  return <div className="xl3-hang__sl" title={sl}>{sl}</div>;
                })()}
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

                {/* Hai vạch hạn, CÓ CHỮ: vạch trơn chỉ nói "có một mốc", không nói mốc gì — người
                    điều độ phải rê chuột từng vạch mới biết đâu là hạn SX, đâu là ngày giao khách.
                    Cùng một ngày thì gộp một vạch, không thì hai chữ đè lên nhau. */}
                {(() => {
                  const cungNgay = d.han_hoan_thanh_sx && d.han_hoan_thanh_sx === d.han_giao_khach;
                  const vach = (ngay: string | null, loai: "sx" | "kh", chu: string, title: string) => {
                    if (!ngay) return null;
                    const hx = x(`${ngay}T23:59`, tu, ngayW);
                    if (hx === null || hx < 0 || hx > rongLuoi) return null;
                    // Vạch sát mép phải: lật chữ sang TRÁI vạch, không thì chữ tràn ra ngoài lưới.
                    const lat = hx > rongLuoi - 85;
                    return (
                      <div
                        key={loai}
                        className={`xl3-han xl3-han--${loai}${lat ? " xl3-han--lat" : ""}`}
                        style={{ left: hx }}
                        title={title}
                      >
                        <span className="xl3-han-tag">
                          {cungNgay ? (
                            <>
                              <Target size={10} className="xl3-han-svg" />
                              <Truck size={10} className="xl3-han-svg" />
                            </>
                          ) : loai === "kh" ? (
                            <Truck size={10} className="xl3-han-svg" />
                          ) : (
                            <Target size={10} className="xl3-han-svg" />
                          )}
                          <span className="xl3-han-text">{chu}</span>
                        </span>
                      </div>
                    );
                  };
                  return (
                    <>
                      {!cungNgay && vach(d.han_giao_khach, "kh", "giao khách", `Hạn giao khách ${ngayNgan(d.han_giao_khach)} (Nghiêm ngặt)`)}
                      {vach(
                        d.han_hoan_thanh_sx, "sx", cungNgay ? "hạn SX · giao khách" : "hạn SX",
                        `Hạn hoàn thành SX ${ngayNgan(d.han_hoan_thanh_sx)}${cungNgay ? " — cũng là ngày giao khách" : ""}`,
                      )}
                    </>
                  );
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
                    title={`${d.ma} · ${d.ten ?? ""} · ${d.thuc_bat_dau_lenh ? "phần còn lại " : ""}${gio(d.bat_dau_at)} → ${gio(veDen(d))} · Làm ${gioChu(d.chay_phut)}, nghỉ & ngoài ca ${gioChu(d.nghi_ngoai_ca_phut)}`}
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

                {/* Nhãn NGÀY XONG cạnh đuôi thanh — mục tiêu của cả màn là "đặt giờ bắt đầu → ra ngày
                    kết thúc", nên ngày kết thúc phải đọc được không cần rê chuột. Ẩn khi đang kéo
                    (số cũ, sai ngay) và khi thanh tràn mép phải (đuôi nằm ngoài cửa sổ). Không đủ
                    chỗ bên phải thì lật sang trái đầu thanh; không đủ cả hai thì để lưới cắt. */}
                {bao && !bao.tranPhai && !dangKeo && (() => {
                  const muon = tre !== null && tre > 0;
                  const rongChu = muon ? 200 : 110;
                  const phai = bao.trai + bao.rong + 6;
                  const lat = phai + rongChu > rongLuoi && bao.trai - 6 - rongChu >= 0;
                  return (
                    <span
                      className={`xl3-xong${muon ? " xl3-xong--tre" : ""}${lat ? " xl3-xong--lat" : ""}`}
                      style={{ left: lat ? bao.trai - 6 : phai }}
                    >
                      {muon && <>⚠ trễ {tre} ngày · </>}
                      xong <b>{ngayGio(veDen(d))}</b>
                    </span>
                  );
                })()}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


