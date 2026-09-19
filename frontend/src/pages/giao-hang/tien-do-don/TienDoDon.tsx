// Tiến độ đơn cho Kinh doanh — Sản xuất → Nhập kho → Giao hàng (19/09/2026).
// Thiết kế: docs/superpowers/plans/2026-09-19-giao-hang-tien-do-don.md.
//
// Số liệu do máy chủ tính (`GET /api/orders/{id}/tien-do`) — FE chỉ vẽ, không tự suy "giao được".
// Luật chốt: KHÔNG lập yêu cầu giao cho phần chưa nhập kho ⇒ ô số lượng trần = `giao_duoc`.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  connectQuoteEvents,
  type DonTienDo,
  type DonTienDoCum,
  type DonTienDoYeuCau,
  type OrderDetail,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { Button } from "../../../components/Button";
import { DetailModal } from "../../../components/DetailModal";
import { fmtDate, fmtDateTime } from "../../../utils/format";
import { NHAN_TRANG_THAI_YC } from "../giao-hang/shared/constants";
import { nhanChuyen } from "../giao-hang/shared/helpers";

const SU_KIEN_TAI_LAI = new Set([
  "giao_hang_changed",
  "giao_hang_chuyen",
  "san_xuat_kho_changed",
  "san_xuat_cong_viec_changed",
]);

/** Tải tiến độ + tự tươi khi giao hàng / kho / bàn tổ đổi (SSE, không bắt F5). */
export function useTienDoDon(orderId: number, bat: boolean) {
  const { token } = useAuth();
  const [td, setTd] = useState<DonTienDo | null>(null);
  const tai = useCallback(() => {
    if (!token || !bat) return;
    api.orders.tienDo(token, orderId).then(setTd).catch(() => setTd(null));
  }, [token, orderId, bat]);
  useEffect(() => {
    setTd(null);
    tai();
  }, [tai]);
  useEffect(() => {
    if (!token || !bat) return;
    return connectQuoteEvents(token, (e) => {
      if (SU_KIEN_TAI_LAI.has(e.type)) tai();
    });
  }, [token, bat, tai]);
  return { td, taiLai: tai };
}

const so = (n: number) => n.toLocaleString("vi-VN", { maximumFractionDigits: 2 });

export const NHAN_LY_DO_TRE: Record<string, string> = {
  su_co: "máy sự cố",
  tam_dung: "lệnh tạm dừng",
  tre_han: "trễ hạn công đoạn",
  kcs_khong_dat: "KCS không đạt",
  thieu_vat_tu: "thiếu vật tư",
  chua_xuong_xuong: "có lệnh chưa xuống xưởng",
};

/** Phần hàng của sản phẩm ĐÃ CÓ cho đơn. Có lệnh: kho đã nhận từ KCS. Không lệnh (giao từ tồn):
 *  đã giao + đang giữ cho yêu cầu + còn giao được từ tồn — tức phần tồn kho gánh được. */
export function coHangCum(c: DonTienDoCum): number {
  const co = c.co_lenh ? c.kho_da_nhan : c.da_giao + c.dang_giu + c.giao_duoc;
  return Math.max(0, Math.min(c.dat, co));
}

/** Sản phẩm KHÔNG có lệnh sản xuất mà tồn kho không đủ ⇒ không có đường nào về đủ hàng. */
export function thieuNguonCum(c: DonTienDoCum): number {
  return c.co_lenh ? 0 : Math.max(0, c.dat - coHangCum(c));
}

/** Tổng hợp cho ba chấm SX / Nhập kho / Giao trên thanh vòng đời. */
export function tomTatTienDo(td: DonTienDo | null) {
  const cum = td?.cum ?? [];
  const coLenh = cum.filter((c) => c.co_lenh);
  const lenh = coLenh.flatMap((c) => c.lenh);
  const sxPct = lenh.length ? lenh.reduce((a, l) => a + l.pct, 0) / lenh.length : 0;
  const sxXong = coLenh.length > 0 && coLenh.every((c) => c.sx_xong);
  // Nhập kho tính trên MỌI sản phẩm (kể cả hàng lấy từ tồn), bình quân tỉ lệ từng món — cộng
  // thẳng số lượng thì hộp với tờ lẫn đơn vị, món 20.000 tờ nuốt mất món 500 hộp.
  const khoPct = cum.length ? cum.reduce((a, c) => a + coHangCum(c) / (c.dat || 1), 0) / cum.length * 100 : 0;
  const soMonDuHang = cum.filter((c) => coHangCum(c) >= c.dat).length;
  const khoXong = cum.length > 0 && soMonDuHang === cum.length;
  const thieuNguon = cum.filter((c) => thieuNguonCum(c) > 0);
  const dat = cum.reduce((a, c) => a + c.dat, 0);
  const daGiao = cum.reduce((a, c) => a + Math.min(c.dat, c.da_giao), 0);
  const giaoPct = dat > 0 ? (daGiao / dat) * 100 : 0;
  const giaoXong = cum.length > 0 && cum.every((c) => c.con_phai_giao <= 0);
  return {
    soLenh: lenh.length,
    lenhXong: lenh.filter((l) => l.xong).length,
    sxPct, sxXong, khoPct, khoXong, giaoPct, giaoXong,
    soMon: cum.length, soMonDuHang, thieuNguon,
    coLenh: coLenh.length > 0,
    soYeuCauMo: (td?.yeu_cau ?? []).filter((y) => y.trang_thai === "cho_len_ke_hoach" || y.trang_thai === "dang_thuc_hien").length,
  };
}

export function ThanhNho({ pct, xong }: { pct: number; xong?: boolean }) {
  const w = Math.max(0, Math.min(100, pct));
  return (
    <span className="dhb__td-mini" aria-hidden>
      <span className={`dhb__td-mini-fill${xong ? " is-xong" : ""}`} style={{ width: `${w}%` }} />
    </span>
  );
}

/** Dòng cảnh báo trễ: dự kiến xong SX so với ngày giao cam kết. */
export function CanhBaoTre({ td }: { td: DonTienDo | null }) {
  if (!td) return null;
  const lyDo = td.ly_do.map((k) => NHAN_LY_DO_TRE[k] ?? k).join(", ");
  if (td.tre_ngay != null && td.tre_ngay > 0) {
    return (
      <div className="banner banner--error dhb__td-tre" role="alert">
        Dự kiến xong sản xuất {fmtDate(td.du_kien_xong)} — <b>trễ {td.tre_ngay} ngày</b> so với hạn
        giao {fmtDate(td.han_cam_ket)}.{lyDo ? ` Lý do: ${lyDo}.` : ""}
      </div>
    );
  }
  if (td.chua_du_du_lieu) {
    return (
      <div className="banner dhb__td-tre">
        Chưa ước được ngày xong sản xuất{lyDo ? ` (${lyDo})` : ""}.
      </div>
    );
  }
  if (td.du_kien_xong && td.han_cam_ket) {
    return (
      <div className="dhb__td-dung">
        Dự kiến xong sản xuất {fmtDate(td.du_kien_xong)} · kịp hạn giao {fmtDate(td.han_cam_ket)}.
      </div>
    );
  }
  return null;
}

/** Tách số đặt của một sản phẩm thành 5 khúc: đã giao / trong kho / chờ kho nhận / đang SX / chưa làm. */
function khucCum(c: DonTienDoCum) {
  const dat = Math.max(c.dat, 0);
  const giao = Math.min(dat, c.da_giao);
  const kho = c.co_lenh
    ? Math.max(0, Math.min(dat - giao, c.kho_da_nhan - c.da_giao))
    : Math.max(0, Math.min(dat - giao, c.ton_that));
  const choKho = Math.max(0, Math.min(dat - giao - kho, c.cho_kho));
  const conLai = Math.max(0, dat - giao - kho - choKho);
  const dangChay = c.lenh.some((l) => l.da_xuong_xuong && !l.xong);
  return { dat, giao, kho, choKho, sx: dangChay ? conLai : 0, chua: dangChay ? 0 : conLai };
}

const KHUC = [
  { k: "giao", nhan: "Đã giao", cls: "giao" },
  { k: "kho", nhan: "Trong kho chờ giao", cls: "kho" },
  { k: "choKho", nhan: "Chờ kho nhận", cls: "chokho" },
  { k: "sx", nhan: "Đang sản xuất", cls: "sx" },
  { k: "chua", nhan: "Chưa làm", cls: "chua" },
] as const;

/** Thanh chồng theo từng sản phẩm — dùng chung cho ba bước SX / Nhập kho / Giao. */
export function BangCum({ td, buoc }: { td: DonTienDo | null; buoc: "sanxuat" | "nhapkho" | "giao" }) {
  if (!td) return <p className="dhb__td-note">Đang tải tiến độ…</p>;
  if (td.cum.length === 0) return <p className="dhb__td-note">Đơn chưa có sản phẩm.</p>;
  return (
    <div className="dhb__td-cums">
      <div className="dhb__td-legend">
        {KHUC.map((x) => (
          <span key={x.k}><i className={`dhb__td-seg--${x.cls}`} />{x.nhan}</span>
        ))}
      </div>
      {td.cum.map((c) => {
        const k = khucCum(c);
        const dv = c.don_vi ?? "";
        return (
          <div key={c.khoa} className="dhb__td-cum">
            <div className="dhb__td-cum-head">
              <b>{c.ten}</b>
              <span className="dhb__mono">{so(c.dat)} {dv}</span>
            </div>
            <div className="dhb__td-bar" role="img"
              aria-label={KHUC.map((x) => `${x.nhan} ${so(k[x.k])}`).join(", ")}>
              {KHUC.map((x) => k[x.k] > 0 && (
                <span key={x.k} className={`dhb__td-seg--${x.cls}`}
                  style={{ width: `${(k[x.k] / (k.dat || 1)) * 100}%` }}
                  title={`${x.nhan}: ${so(k[x.k])} ${dv}`} />
              ))}
            </div>
            <div className="dhb__td-cum-nums">
              {buoc === "sanxuat" && (
                c.co_lenh ? (
                  c.lenh.map((l) => (
                    <span key={l.id}>
                      <b className="dhb__mono">{l.ma}</b>{" "}
                      {!l.da_xuong_xuong ? "chưa xuống xưởng"
                        : l.xong ? "xong"
                        : `${so(l.pct)}%${l.uoc_tinh ? " (ước)" : ""}${l.buoc_hien_tai ? ` · đang ${l.buoc_hien_tai}` : ""}${l.du_kien_xong ? ` · dự kiến ${fmtDate(l.du_kien_xong)}` : ""}`}
                      {l.canh_bao.length > 0 && (
                        <em className="dhb__td-warn"> · {l.canh_bao.map((w) => NHAN_LY_DO_TRE[w] ?? w).join(", ")}</em>
                      )}
                    </span>
                  ))
                ) : thieuNguonCum(c) > 0 ? (
                  <span className="dhb__td-warn">
                    Không có lệnh sản xuất, tồn kho chỉ có {so(c.ton_that)} {dv} — <b>thiếu {so(thieuNguonCum(c))} {dv}</b>.
                    Báo Kế hoạch lên lệnh hoặc nhập thêm hàng.
                  </span>
                ) : <span>Không qua sản xuất — giao từ tồn kho ({so(c.ton_that)} {dv}).</span>
              )}
              {buoc === "nhapkho" && (
                c.co_lenh ? (
                  <span>
                    KCS đã gửi {so(c.kho_de_nghi)} · kho đã nhận <b>{so(c.kho_da_nhan)}</b>
                    {c.cho_kho > 0 && <> · chờ kho nhận {so(c.cho_kho)}</>} · tồn thực {so(c.ton_that)} {dv}
                  </span>
                ) : (
                  <span>
                    Lấy từ tồn kho — tồn thực {so(c.ton_that)} {dv}
                    {thieuNguonCum(c) > 0 && <em className="dhb__td-warn"> · thiếu {so(thieuNguonCum(c))} {dv}, chưa có lệnh sản xuất</em>}.
                  </span>
                )
              )}
              {buoc === "giao" && (
                <span>
                  Đã giao <b>{so(c.da_giao)}</b>
                  {c.dang_giu > 0 && <> · đang giữ cho yêu cầu {so(c.dang_giu)}</>}
                  {" "}· còn phải giao {so(c.con_phai_giao)} · <b>giao được ngay {so(c.giao_duoc)}</b> {dv}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function homNay(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const TONE_YC: Record<string, string> = {
  cho_len_ke_hoach: "upcoming",
  dang_thuc_hien: "active",
  da_giao_du: "done",
  giao_thieu: "active",
  that_bai: "cancelled",
  chuyen_da_huy: "cancelled",
  da_huy: "cancelled",
};

/** Bước "Giao hàng": danh sách yêu cầu + chuyến, và form lập yêu cầu trần theo `giao_duoc`. */
export function BuocGiaoHang({
  order, td, taiLai, onIn, navigate,
}: {
  order: OrderDetail;
  td: DonTienDo | null;
  taiLai: () => void;
  onIn: (yc: DonTienDoYeuCau) => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canRead = can("giao_hang", "read");
  const canWrite = can("giao_hang", "create");
  const [mo, setMo] = useState(false);
  const [sua, setSua] = useState<DonTienDoYeuCau | null>(null);
  const [huy, setHuy] = useState<DonTienDoYeuCau | null>(null);
  const [lyDoHuy, setLyDoHuy] = useState("");
  const [loi, setLoi] = useState<string | null>(null);

  if (!canRead) return <p className="dhb__td-note">Vai của bạn chưa được xem màn Giao hàng.</p>;
  if (!td) return <p className="dhb__td-note">Đang tải…</p>;
  if (order.status !== "ordered" && td.yeu_cau.length === 0) {
    return <p className="dhb__td-note">Đơn phải chốt trước mới lập yêu cầu giao được.</p>;
  }
  const tongGiaoDuoc = td.cum.reduce((a, c) => a + c.giao_duoc, 0);
  const conPhai = td.cum.some((c) => c.con_phai_giao > 0);

  const huyYc = () => {
    if (!token || !huy) return;
    setLoi(null);
    api.giaoHang.cancelRequest(token, huy.id, lyDoHuy.trim())
      .then(() => { setHuy(null); setLyDoHuy(""); taiLai(); })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không huỷ được yêu cầu"));
  };

  return (
    <div className="dhb__td-giao">
      <BangCum td={td} buoc="giao" />

      {loi && <div className="banner banner--error" role="alert">{loi}</div>}

      <div className="dhb__td-yc-list">
        {td.yeu_cau.length === 0 && <p className="dhb__td-note">Chưa có yêu cầu giao hàng nào.</p>}
        {td.yeu_cau.map((y) => {
          const ch = y.chuyen;
          const suaDuoc = canWrite && y.trang_thai === "cho_len_ke_hoach" && !ch;
          const huyDuoc = canWrite && (y.trang_thai === "cho_len_ke_hoach" || y.trang_thai === "chuyen_da_huy");
          return (
            <div key={y.id} className="dhb__td-yc">
              <div className="dhb__td-yc-head">
                <b className="dhb__mono">{y.code}</b>
                <span className={`dhb__lifecycle-badge dhb__lifecycle-badge--${TONE_YC[y.trang_thai] ?? "upcoming"}`}>
                  {NHAN_TRANG_THAI_YC[y.trang_thai] ?? y.trang_thai}
                </span>
                <span className="dhb__td-yc-ngay">cần giao {fmtDate(y.ngay_can_giao)}</span>
                <span style={{ flex: 1 }} />
                <button type="button" className="dhb__td-link" onClick={() => onIn(y)}>In phiếu giao</button>
                {suaDuoc && <button type="button" className="dhb__td-link" onClick={() => { setSua(y); setMo(false); }}>Sửa</button>}
                {huyDuoc && <button type="button" className="dhb__td-link dhb__td-link--do" onClick={() => { setHuy(y); setLyDoHuy(""); }}>Huỷ</button>}
              </div>
              <div className="dhb__td-yc-body">
                {y.dong.map((d) => (
                  <span key={d.order_line_id}>
                    {d.ten || "Hàng"}: <b>{so(d.qty)}</b>{d.da_giao > 0 && d.da_giao !== d.qty ? ` (đã giao ${so(d.da_giao)})` : ""}
                  </span>
                ))}
                <span className="dhb__td-yc-dc">{y.dia_chi}{y.nguoi_nhan ? ` · ${y.nguoi_nhan}` : ""}{y.sdt_nguoi_nhan ? ` · ${y.sdt_nguoi_nhan}` : ""}</span>
                {y.trang_thai === "da_huy" && y.ly_do_huy && <span className="dhb__td-warn">Lý do huỷ: {y.ly_do_huy}</span>}
              </div>
              {ch ? (
                <div className="dhb__td-yc-chuyen">
                  Chuyến: <b>{nhanChuyen(ch)}</b>
                  {ch.tai_xe && <> · tài xế {ch.tai_xe}</>}
                  {ch.xe && <> · xe {ch.xe}</>}
                  {" "}· lấy hàng {fmtDateTime(ch.gio_lay_hang)} · dự kiến giao {fmtDateTime(ch.gio_du_kien_giao)}
                  {ch.thoi_gian_ket_thuc && <> · kết thúc {fmtDateTime(ch.thoi_gian_ket_thuc)}</>}
                  {ch.nguoi_nhan_thuc_te && <> · người nhận {ch.nguoi_nhan_thuc_te}</>}
                  {ch.ly_do_that_bai && <> · lý do: {ch.ly_do_that_bai}</>}
                  {ch.so_anh > 0 && <> · {ch.so_anh} ảnh</>}
                  {ch.tra_hang_ma && (
                    <> · trả hàng {ch.tra_hang_ma}: {ch.tra_hang_xong ? "kho đã nhận lại" : "chờ kho nhận lại"}</>
                  )}
                </div>
              ) : y.trang_thai === "cho_len_ke_hoach" ? (
                <div className="dhb__td-yc-chuyen">Chờ điều phối lên chuyến.</div>
              ) : null}
              {huy?.id === y.id && (
                <div className="dhb__td-yc-huy">
                  <input className="input" placeholder="Lý do huỷ yêu cầu…" value={lyDoHuy}
                    aria-label={`Lý do huỷ ${y.code}`} onChange={(e) => setLyDoHuy(e.target.value)} />
                  <Button variant="accent" disabled={!lyDoHuy.trim()} onClick={huyYc}>Xác nhận huỷ</Button>
                  <Button variant="ghost" onClick={() => setHuy(null)}>Bỏ</Button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {order.status === "ordered" && canWrite && conPhai && (
        <div className="dhb__td-tao">
          <Button variant="accent" disabled={tongGiaoDuoc <= 0} onClick={() => setMo(true)}>
            Tạo yêu cầu giao hàng
          </Button>
          {tongGiaoDuoc <= 0 && (
            <span className="dhb__td-note">
              Chưa có hàng trong kho để giao — chỉ lập yêu cầu cho phần kho đã nhận.
            </span>
          )}
        </div>
      )}
      {order.status === "ordered" && !canWrite && conPhai && (
        <p className="dhb__td-note">Chỉ xem — vai của bạn chưa được bật ô Thao tác ở màn Giao hàng.</p>
      )}
      {mo && (
        <FormYeuCau order={order} td={td} navigate={navigate}
          onXong={() => { setMo(false); taiLai(); }} onBo={() => setMo(false)} />
      )}
      {sua && (
        <FormYeuCau order={order} td={td} sua={sua} navigate={navigate}
          onXong={() => { setSua(null); taiLai(); }} onBo={() => setSua(null)} />
      )}
    </div>
  );
}

/** Lập mới (không có `sua`) hoặc sửa yêu cầu chưa lên chuyến. Hàng + số lượng của yêu cầu đã lập
 *  KHÔNG sửa — muốn đổi thì huỷ rồi lập lại (giữ vết đúng một chỗ).
 *
 *  NƠI NHẬN KHÔNG GÕ TAY (chủ chốt 19/09/2026): chỉ CHỌN — mặc định nơi nhận của đơn (đơn kế thừa từ
 *  báo giá, báo giá chọn từ khách), đổi thì chọn trong sổ địa chỉ / người liên hệ của khách. Thiếu thì
 *  bổ sung ở hồ sơ khách hàng, một chỗ, mọi nơi khác tự lấy theo. */
function FormYeuCau({
  order, td, sua, onXong, onBo, navigate,
}: {
  order: OrderDetail;
  td: DonTienDo;
  sua?: DonTienDoYeuCau;
  onXong: () => void;
  onBo: () => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const HOM_NAY = homNay();
  const nn = td.noi_nhan;
  const coTheoDon = Boolean(nn.dia_chi?.trim());
  // "" = theo đơn. Đơn không có địa chỉ ⇒ mặc định địa chỉ mặc định của khách (hoặc cái đầu sổ).
  const dcMacDinh = (): string => {
    if (sua) {
      const trung = nn.so_dia_chi.find((x) => x.dia_chi === sua.dia_chi);
      if (trung && sua.dia_chi !== nn.dia_chi) return String(trung.id);
      return coTheoDon ? "" : trung ? String(trung.id) : "";
    }
    if (coTheoDon) return "";
    const d = nn.so_dia_chi.find((x) => x.mac_dinh) ?? nn.so_dia_chi[0];
    return d ? String(d.id) : "";
  };
  const lhMacDinh = (): string => {
    if (sua && sua.nguoi_nhan && sua.nguoi_nhan !== nn.nguoi_nhan) {
      const trung = nn.lien_he.find((x) => x.ten === sua.nguoi_nhan);
      if (trung) return String(trung.id);
    }
    if (nn.nguoi_nhan) return "";
    const c = nn.lien_he.find((x) => x.chinh) ?? nn.lien_he[0];
    return c ? String(c.id) : "";
  };
  const [ngay, setNgay] = useState(sua ? sua.ngay_can_giao.slice(0, 10) : "");
  const [dcId, setDcId] = useState(dcMacDinh);
  const [lhId, setLhId] = useState(lhMacDinh);
  const coHang = td.cum.filter((c) => c.giao_duoc > 0);
  // Điền sẵn TOÀN BỘ phần giao được — ca hay gặp nhất; ai muốn giao ít hơn thì sửa số.
  const [soLuong, setSoLuong] = useState<Record<string, string>>(
    () => Object.fromEntries(coHang.map((c) => [c.khoa, String(c.giao_duoc)])),
  );
  const [loi, setLoi] = useState<string | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const ngayQuaKhu = ngay !== "" && ngay < HOM_NAY;
  const khongCoDiaChi = !coTheoDon && nn.so_dia_chi.length === 0;

  const dong = coHang
    .map((c) => ({ c, qty: Number(soLuong[c.khoa] ?? 0) }))
    .filter((x) => x.qty > 0);
  const vuot = dong.find((x) => x.qty > x.c.giao_duoc);
  const noiNhan = {
    dia_chi_id: dcId ? Number(dcId) : null,
    lien_he_id: lhId ? Number(lhId) : null,
  };

  const gui = () => {
    if (!token) return;
    setLoi(null);
    setDangGui(true);
    const p = sua
      ? api.giaoHang.updateRequest(token, sua.id, { ngay_can_giao: ngay, ...noiNhan })
      : api.giaoHang.createRequest(token, {
          order_id: order.id,
          ngay_can_giao: ngay,
          // Một cụm gửi MỘT dòng (dòng đầu) — máy chủ bung ra mọi dòng của cụm cùng số.
          lines: dong.map((x) => ({ order_line_id: x.c.order_line_ids[0], qty: x.qty })),
          ...noiNhan,
        });
    p.then(onXong)
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không lưu được yêu cầu"))
      .finally(() => setDangGui(false));
  };

  const chuaCoHang = td.cum.filter((c) => c.giao_duoc <= 0 && c.con_phai_giao > 0);
  const luuY = nn.luu_y?.trim();
  // Chân popup: nút khoá thì nói lý do ngay cạnh nút, không bắt người dùng đoán.
  const lyDoKhoa = khongCoDiaChi ? "Khách chưa có địa chỉ giao"
    : !sua && dong.length === 0 ? "Chưa có hàng nào để giao"
    : vuot ? "Số lượng vượt phần giao được"
    : !ngay ? "Chọn ngày cần giao"
    : ngayQuaKhu ? "Ngày cần giao đã qua"
    : null;
  const tomTat = sua ? "Chỉ sửa ngày và nơi nhận — số lượng giữ như lúc lập" : `Giao ${dong.length} sản phẩm`;

  return (
    <DetailModal
      kicker="Giao hàng"
      title={sua ? `Sửa yêu cầu ${sua.code}` : "Tạo yêu cầu giao hàng"}
      subtitle={[order.order_no, order.customer_name].filter(Boolean).join(" · ")}
      width={620}
      onClose={onBo}
      footer={
        <>
          <span className={`dmodal__foot-note ${lyDoKhoa ? "is-warn" : ""}`}>{lyDoKhoa ?? tomTat}</span>
          <Button variant="ghost" onClick={onBo}>Bỏ</Button>
          <Button variant="accent" disabled={dangGui || lyDoKhoa !== null} onClick={gui}>
            {sua ? "Lưu thay đổi" : "Gửi yêu cầu"}
          </Button>
        </>
      }
    >
      <div className="pform">
        {!sua && (
          <section>
            <h3 className="pform__section-title">Hàng giao đợt này</h3>
            <div className="pform__items">
              {coHang.length === 0 && (
                <div className="pform__item"><span className="pform__item-name">Kho chưa nhận hàng nào của đơn này.</span></div>
              )}
              {coHang.map((c) => {
                const qty = Number(soLuong[c.khoa] ?? 0);
                return (
                  <div key={c.khoa} className="pform__item">
                    <span className="pform__item-name">
                      {c.ten}
                      <small className={qty > c.giao_duoc ? "pform__hint is-error" : undefined}>
                        {qty > c.giao_duoc ? "Vượt — " : ""}giao được tối đa {so(c.giao_duoc)} {c.don_vi ?? ""}
                      </small>
                    </span>
                    <span className="pform__suffix">
                      <input
                        className="input"
                        type="number" min="0" step="1" max={c.giao_duoc}
                        aria-label={`Số lượng giao — ${c.ten}`}
                        value={soLuong[c.khoa] ?? ""}
                        onChange={(e) => setSoLuong((p) => ({ ...p, [c.khoa]: e.target.value }))}
                      />
                      <span>{c.don_vi ?? "SL"}</span>
                    </span>
                  </div>
                );
              })}
              {chuaCoHang.length > 0 && (
                <div className="pform__items-off">
                  Chưa có hàng trong kho: {chuaCoHang.map((c) => c.ten).join(", ")}
                </div>
              )}
            </div>
          </section>
        )}

        <section>
          <h3 className="pform__section-title">Ngày & nơi nhận</h3>
          <div className="pform__grid">
            <label className="pform__field">
              Ngày cần giao
              <input className="input" type="date" value={ngay} min={HOM_NAY} onChange={(e) => setNgay(e.target.value)} />
              {ngayQuaKhu && <span className="pform__hint is-error">Không được ở quá khứ — hôm nay là {fmtDate(HOM_NAY)}.</span>}
            </label>
          </div>
        </section>

        {khongCoDiaChi ? (
          <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
            Khách <b>{order.customer_name ?? ""}</b> chưa có địa chỉ giao — thêm ở hồ sơ khách hàng rồi quay
            lại chọn.{" "}
            {navigate && (
              <button type="button" className="dhb__td-link" onClick={() => navigate("khach-hang")}>
                Mở màn Khách hàng ↗
              </button>
            )}
          </div>
        ) : (
          <fieldset className="pform__choices">
            <legend>Giao tới</legend>
            {coTheoDon && (
              <TheChon name="gh-yc-dia-chi" value="" chon={dcId} onChon={setDcId}
                tieuDe="Địa chỉ ghi trên đơn" nhan="Theo đơn" dong2={nn.dia_chi} />
            )}
            {nn.so_dia_chi.map((x) => (
              <TheChon key={x.id} name="gh-yc-dia-chi" value={String(x.id)} chon={dcId} onChon={setDcId}
                tieuDe={x.nhan} nhan={x.mac_dinh ? "Mặc định" : undefined} dong2={x.dia_chi} />
            ))}
          </fieldset>
        )}

        <fieldset className="pform__choices">
          <legend>Người nhận</legend>
          {nn.nguoi_nhan && (
            <TheChon name="gh-yc-nguoi-nhan" value="" chon={lhId} onChon={setLhId}
              tieuDe={nn.nguoi_nhan} nhan="Theo đơn" phai={nn.sdt ?? undefined} />
          )}
          {nn.lien_he.map((x) => (
            <TheChon key={x.id} name="gh-yc-nguoi-nhan" value={String(x.id)} chon={lhId} onChon={setLhId}
              tieuDe={x.ten} nhan={x.chinh ? "Liên hệ chính" : undefined}
              dong2={x.chuc_vu ?? undefined} phai={x.sdt ?? undefined} />
          ))}
          {!nn.nguoi_nhan && nn.lien_he.length === 0 && (
            <p className="pform__hint" style={{ margin: 0 }}>Khách chưa có người liên hệ — thêm ở hồ sơ khách hàng.</p>
          )}
        </fieldset>
        <p className="pform__hint" style={{ margin: "-8px 0 0" }}>
          Địa chỉ và người nhận lấy từ hồ sơ khách — muốn thêm mới thì sửa ở hồ sơ khách hàng.
        </p>

        {luuY && (
          <div className="pform__note">
            <b>Lưu ý giao của đơn</b>
            <span>{luuY}</span>
          </div>
        )}

        {loi && <div className="banner banner--error" role="alert" style={{ margin: 0 }}>{loi}</div>}
      </div>
    </DetailModal>
  );
}

/** Một lựa chọn dạng thẻ (radio) — tên đậm, dòng phụ bên dưới, số điện thoại canh phải; thay cho
 *  `<select>` nhồi mọi thông tin vào một dòng ngăn bằng dấu chấm. */
function TheChon({
  name, value, chon, onChon, tieuDe, nhan, dong2, phai,
}: {
  name: string;
  value: string;
  chon: string;
  onChon: (v: string) => void;
  tieuDe: string;
  nhan?: string;
  dong2?: string | null;
  phai?: string;
}) {
  const on = chon === value;
  return (
    <label className={`pform__choice ${on ? "is-on" : ""}`}>
      <input type="radio" name={name} value={value} checked={on} onChange={() => onChon(value)} aria-label={tieuDe} />
      <span className="pform__choice-main">
        <span className="pform__choice-title">
          {tieuDe}
          {nhan && <em>{nhan}</em>}
        </span>
        {dong2 && <span className="pform__choice-sub">{dong2}</span>}
      </span>
      {phai && <span className="pform__choice-side">{phai}</span>}
    </label>
  );
}
