// Một LƯỢT XE = MỘT khối trên tab "Đơn giao hàng" (chủ chốt 18/09/2026: ghép nhiều yêu cầu mà
// hiện rời từng dòng thì tài xế lẫn người lên đơn "khó hiểu quá").
//
// Khối gồm: đầu (mã lượt · xe · kíp · giờ lấy hàng) · thanh 5 bước · MỘT chỗ bấm cho bước kế tiếp
// của CẢ lượt · các điểm theo thứ tự chặng. Mỗi điểm chỉ còn nút của RIÊNG nó (Nhập kết quả / Kho
// đã nhận lại) — mỗi khách một số đồng hồ, một kết cục. Gửi kho · lấy hàng · xuất phát · về kho
// giống nhau cho mọi điểm nên chỉ bấm một lần ở đầu khối, không bày lại ở từng dòng.
import { useEffect, useRef, useState } from "react";
import type { CaLuotKetQua, DeliveryTrip, LuotXeChiTiet } from "../../../../api/client";
import { api } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { fmtDateTime } from "../../../../utils/format";
import { nhanChuyen, toneChuyen } from "../shared/helpers";
import { FormSoDongHo } from "./FormSoDongHo";
import { NutCho, Pill } from "./giaoHangCells";

const CHUA_KET_QUA = ["da_len_ke_hoach", "dang_chuan_bi", "da_lay_hang", "dang_giao"];
const so = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("vi-VN"));

/** Trạng thái CẢ lượt — một câu, đọc từ số đếm máy chủ trả (không tự suy từ từng dòng hai kiểu). */
function trangThaiLuot(l: LuotXeChiTiet, coKetQua: number): { text: string; tone: "on" | "warn" } {
  if (l.ve_kho_luc) return { text: "Đã về kho", tone: "on" };
  if (l.cho_ve_kho) return { text: "Chờ về kho", tone: "warn" };
  if (l.so_dang_giao > 0) return { text: `Đang giao · ${coKetQua}/${l.diem.length} điểm`, tone: "warn" };
  if (l.so_cho_bat_dau > 0) return { text: "Đã lấy hàng", tone: "warn" };
  if (l.so_cho_lay_hang > 0) {
    const xong = l.diem.every((t) => t.trang_thai !== "dang_chuan_bi" || t.kho_da_lap_phieu);
    return { text: xong ? "Kho đã chuẩn bị xong" : "Kho đang chuẩn bị", tone: "warn" };
  }
  return { text: "Chờ gửi kho", tone: "warn" };
}

type Mo = null | "gui_kho" | "xuat_phat" | "ve_kho";

export function KhoiLuot({
  luot: l,
  token,
  canPlan,
  canWrite,
  moi = false,
  onDoi,
  onMo,
  onKetQua,
  onDaTra,
}: {
  luot: LuotXeChiTiet;
  token: string;
  canPlan: boolean;
  canWrite: boolean;
  /** Lượt vừa lập xong — làm nổi + cuộn tới để người lên đơn thấy ngay bước kế tiếp. */
  moi?: boolean;
  /** Có thao tác làm đổi trạng thái ⇒ bảng tải lại. */
  onDoi: () => void;
  onMo: (requestId: number) => void;
  onKetQua?: (t: DeliveryTrip) => void;
  onDaTra?: (t: DeliveryTrip) => Promise<unknown>;
}) {
  const [mo, setMo] = useState<Mo>(null);
  // MẶC ĐỊNH KHÉP (chủ chốt 18/09/2026: "mặc định nó khép lại đi, muốn xem thêm thì mở rộng ra,
  // sổ ra cả vậy xấu quá"). Khép vẫn thấy trạng thái, km, tên khách và nút cho bước kế tiếp.
  const [moRong, setMoRong] = useState(false);
  const [ghiChu, setGhiChu] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [tin, setTin] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [loi, setLoi] = useState<string | null>(null);
  const goc = useRef<HTMLElement>(null);

  useEffect(() => {
    if (moi) goc.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [moi]);

  // Dòng báo THÀNH CÔNG tự tắt — bước sau (nhập kết quả ở hộp riêng, SSE của người khác) không đi
  // qua khối nên không có chỗ nào khác xoá nó. Cảnh báo thì giữ tới lần bấm sau: nó cần người đọc.
  useEffect(() => {
    if (!tin) return;
    const h = window.setTimeout(() => setTin(null), 8000);
    return () => window.clearTimeout(h);
  }, [tin]);

  const ds = l.diem;
  const coKetQua = ds.filter((t) => !CHUA_KET_QUA.includes(t.trang_thai)).length;
  const tt = trangThaiLuot(l, coKetQua);
  const dau = ds[0];

  const buoc = [
    { nhan: "Gửi kho", xong: l.so_cho_gui_kho === 0 },
    { nhan: "Lấy hàng", xong: l.so_cho_gui_kho === 0 && l.so_cho_lay_hang === 0 },
    { nhan: l.so_dong_ho_xuat_phat != null ? `Xuất phát ${so(l.so_dong_ho_xuat_phat)}` : "Xuất phát",
      xong: l.so_dong_ho_xuat_phat != null },
    { nhan: `Giao từng điểm ${coKetQua}/${ds.length}`, xong: ds.length > 0 && coKetQua === ds.length },
    { nhan: l.ve_kho_luc ? `Về kho ${so(l.so_dong_ho_ve_kho)}` : "Về kho", xong: !!l.ve_kho_luc },
  ];
  const dangO = buoc.findIndex((b) => !b.xong);

  /** Một thao tác cả lượt: xong thì báo số điểm vừa đi tiếp + cảnh báo, rồi tải lại bảng. */
  const lam = (viec: Promise<CaLuotKetQua>, noi: (r: CaLuotKetQua) => string) => {
    setLoi(null);
    setTin(null);
    setCanhBao([]);
    setDangGui(true);
    viec
      .then((r) => {
        setTin(noi(r));
        setCanhBao(r.canh_bao);
        setMo(null);
        onDoi();
      })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không thao tác được"))
      .finally(() => setDangGui(false));
  };

  // Các bước còn làm được — cái ĐẦU là việc chính (nút đậm), còn lại nút nhạt. Thường chỉ có một;
  // có hai khi lượt lệch nhịp (một điểm kho còn soạn, điểm kia đã lên xe) — lúc đó vẫn bắt đầu giao
  // được những điểm đã lấy hàng, không bắt cả xe đứng chờ.
  const nut: { nhan: string; bam: () => void }[] = [];
  if (canPlan && l.so_cho_gui_kho > 0)
    nut.push({ nhan: `Gửi yêu cầu xuất kho (${l.so_cho_gui_kho})`, bam: () => moO("gui_kho") });
  if (canWrite && l.so_cho_lay_hang > 0)
    nut.push({
      nhan: `Đã lấy hàng cả lượt (${l.so_cho_lay_hang})`,
      bam: () => lam(api.giaoHang.daLayHangCaLuot(token, l.id), (r) => `Đã lấy hàng ${r.so_chuyen} điểm.`),
    });
  if (canWrite && l.so_cho_bat_dau > 0)
    nut.push({
      nhan: `Bắt đầu giao (${l.so_cho_bat_dau} điểm)`,
      // Chưa có số xuất phát ⇒ hỏi số trước; có rồi (xe đi dở, bốc thêm điểm) thì đi luôn.
      bam: () => (l.so_dong_ho_xuat_phat == null
        ? moO("xuat_phat")
        : lam(api.giaoHang.batDauGiaoCaLuot(token, l.id), (r) => `Đã bắt đầu giao ${r.so_chuyen} điểm.`)),
    });
  if (canWrite && l.cho_ve_kho) nut.push({ nhan: "Về kho", bam: () => moO("ve_kho") });

  const xongSoDongHo = () => {
    setMo(null);
    onDoi();
  };

  /** Mở một ô nhập ⇒ xoá dòng báo của bước trước. Bấm thử 18/09/2026: "Đã lấy hàng 2 điểm." còn
   *  treo trên khối tới tận lúc về kho, đọc như việc vừa xảy ra. */
  const moO = (o: Mo) => {
    setTin(null);
    setCanhBao([]);
    setLoi(null);
    setMo(o);
    setMoRong(true);   // ô nhập nằm trong thân khối — bấm từ đầu khối đang khép thì mở ra
  };

  const idThan = `luot-${l.id}-than`;
  // Tên khách gộp trùng ("Minh Long ×2") — hai điểm cùng một khách là chuyện thường (hai đơn).
  const demKhach = new Map<string, number>();
  for (const t of ds)
    if (t.customer_name) demKhach.set(t.customer_name, (demKhach.get(t.customer_name) ?? 0) + 1);
  const tenKhach = [...demKhach].map(([ten, n]) => (n > 1 ? `${ten} ×${n}` : ten));
  const tomTatKhach = tenKhach.length > 3
    ? `${tenKhach.slice(0, 3).join(" · ")} +${tenKhach.length - 3}`
    : tenKhach.join(" · ");
  const nutChinh = nut[0];

  return (
    <article ref={goc} className={`gh-khoi${moi ? " is-moi" : ""}${moRong ? " is-mo" : ""}`}
      aria-label={`Lượt ${l.code}`}>
      <header className="gh-khoi__dau">
        <h3 className="gh-khoi__h">
          <button type="button" className="gh-khoi__mo" aria-expanded={moRong} aria-controls={idThan}
            onClick={() => setMoRong((v) => !v)}>
            <Icon name="chevron" size={16} className="gh-khoi__chev" aria-hidden="true" />
            <Icon name="truck" size={18} aria-hidden="true" />
            <span className="gh-khoi__ma">Lượt {l.code}</span>
          </button>
        </h3>
        <Pill text={tt.text} tone={tt.tone} />
        <span className="gh-khoi__phai">
          {l.tong_km > 0 && <span className="gh-khoi__km">Đã chạy <b>{so(l.tong_km)}</b> km</span>}
          {/* Khép vẫn bấm được bước KẾ TIẾP — không bắt mở khối chỉ để bấm một nút. */}
          {!moRong && mo === null && nutChinh && (
            <Button variant="accent" disabled={dangGui} onClick={nutChinh.bam}>{nutChinh.nhan}</Button>
          )}
          {!moRong && !nutChinh && l.so_dang_giao > 0 && (
            <Button variant="ghost" onClick={() => setMoRong(true)}>
              Nhập kết quả ({l.so_dang_giao} điểm)
            </Button>
          )}
        </span>
      </header>
      <p className="gh-khoi__meta">
        Xe <b>{l.xe_bien_so ?? "—"}</b>{l.xe_ten ? ` (${l.xe_ten})` : ""}
        {dau && <> · <span>{dau.employee_name}</span>{dau.phu_xe_name ? ` + ${dau.phu_xe_name}` : ""}</>}
        {dau && ` · lấy hàng ${fmtDateTime(dau.gio_lay_hang)}`}
        {` · ${ds.length} điểm`}
        {!moRong && tomTatKhach && `: ${tomTatKhach}`}
      </p>

      {tin && <div className="banner banner--success" role="status">{tin}</div>}
      {canhBao.map((c) => (
        <div key={c} className="banner banner--warn" role="status">{c}</div>
      ))}
      {loi && <div className="banner banner--error" role="alert">{loi}</div>}

      {moRong && (
        <div id={idThan} className="gh-khoi__than">
          <ol className="gh-buoc" aria-label="Tiến độ lượt">
            {buoc.map((b, i) => (
              <li key={b.nhan}
                className={`gh-buoc__i${b.xong ? " is-xong" : i === dangO ? " is-dang" : ""}`}
                aria-current={i === dangO ? "step" : undefined}>
                {b.xong && <Icon name="check" size={12} aria-hidden="true" />}
                {b.nhan}
              </li>
            ))}
          </ol>

          {mo === null && (nut.length > 0 || l.so_dang_giao > 0) && (
            <div className="gh-khoi__viec">
              {nut.map((n, i) => (
                <Button key={n.nhan} variant={i === 0 ? "accent" : "ghost"} disabled={dangGui}
                  onClick={n.bam}>
                  {n.nhan}
                </Button>
              ))}
              {nut.length === 0 && l.so_dang_giao > 0 && (
                <span className="rc__sub">
                  Tới khách nào thì bấm <b>Nhập kết quả</b> ở điểm đó, kèm số đồng hồ lúc tới.
                </span>
              )}
            </div>
          )}

          {mo === "gui_kho" && (
            <div className="gh-khoi__panel gh-form">
              <p className="rc__sub">
                Mỗi điểm một phiếu yêu cầu xuất kho ({l.so_cho_gui_kho} phiếu). Ghi chú phiếu tự mang mã
                lượt để kho biết các phiếu lên cùng một xe.
              </p>
              <label>
                Ghi chú cho kho <span className="gh-opt">(không bắt buộc)</span>
                <input className="input" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} />
              </label>
              <div className="gh-actions">
                <Button variant="accent" disabled={dangGui}
                  onClick={() => lam(api.giaoHang.guiXuatKhoCaLuot(token, l.id, ghiChu),
                    (r) => `Đã gửi ${r.so_chuyen} phiếu yêu cầu xuất kho: ${r.phieu.join(", ")}.`)}>
                  Gửi {l.so_cho_gui_kho} phiếu
                </Button>
                <Button variant="ghost" onClick={() => setMo(null)}>Thôi</Button>
              </div>
            </div>
          )}
          {mo === "xuat_phat" && (
            <div className="gh-khoi__panel">
              <FormSoDongHo
                cheDo="xuat_phat"
                luot={l}
                moTa={`Xe rời kho với ${l.so_cho_bat_dau} điểm đã lấy hàng. Chặng tới khách đầu tiên trừ từ số này.`}
                nhanNut={`Bắt đầu giao ${l.so_cho_bat_dau} điểm`}
                gui={(n) => api.giaoHang.batDauGiaoCaLuot(token, l.id, { so_dong_ho_xuat_phat: n })
                  .then((r) => {
                    onDoi();
                    return r.canh_bao;
                  })}
                onXong={xongSoDongHo}
                onHuy={() => setMo(null)}
              />
            </div>
          )}
          {mo === "ve_kho" && (
            <div className="gh-khoi__panel">
              <FormSoDongHo
                cheDo="ve_kho"
                luot={l}
                moTa="Mọi điểm đã có kết quả. Chặng về kho tính tiền theo bậc km như các chặng khác, chia cho kíp của điểm giao cuối."
                nhanNut="Lưu về kho"
                gui={(n, xacNhan) => api.giaoHang.veKho(token, l.id, { so_dong_ho: n, xac_nhan_km_lon: xacNhan })
                  .then((r) => {
                    onDoi();
                    return r.canh_bao;
                  })}
                onXong={xongSoDongHo}
                onHuy={() => setMo(null)}
              />
            </div>
          )}

          {/* Điểm theo THỨ TỰ CHẶNG (máy chủ xếp theo số đồng hồ; chưa có số thì theo thứ tự lên đơn). */}
          <ol className="gh-diem-ds">
            {ds.map((t, i) => (
              <li key={t.id} className="gh-diem">
                <span className="gh-diem__so" aria-hidden="true">{i + 1}</span>
                <div className="gh-diem__khach">
                  <span className="gh-diem__ten">{t.customer_name}</span>
                  <span className="gh-ma rc__sub">
                    <button type="button" className="gh-link" onClick={() => onMo(t.request_id)}>
                      {t.request_code}
                    </button>
                    {t.order_code && <span className="gh-nowrap">· {t.order_code}</span>}
                  </span>
                </div>
                <span className="gh-diem__tt"><Pill text={nhanChuyen(t)} tone={toneChuyen(t.trang_thai)} /></span>
                <span className="gh-diem__km">
                  {t.luot?.so_dong_ho != null ? (
                    <>
                      <span>{so(t.luot.so_dong_ho)}</span>
                      <b>{so(t.km)} km</b>
                    </>
                  ) : "—"}
                </span>
                <span className="gh-diem__nut">
                  {t.trang_thai === "dang_giao" && onKetQua && (
                    <Button variant="accent" onClick={() => onKetQua(t)}>Nhập kết quả</Button>
                  )}
                  {t.trang_thai === "dang_tra_hang" && onDaTra && (
                    <NutCho variant="ghost" bam={() => onDaTra(t)}>Kho đã nhận lại</NutCho>
                  )}
                </span>
              </li>
            ))}
            {l.ve_kho_luc && (
              <li className="gh-diem gh-diem--kho">
                <span className="gh-diem__so" aria-hidden="true"><Icon name="truck" size={12} /></span>
                <div className="gh-diem__khach">
                  <span className="gh-diem__ten">Về kho</span>
                  <span className="rc__sub">{fmtDateTime(l.ve_kho_luc)}</span>
                </div>
                <span className="gh-diem__tt" />
                <span className="gh-diem__km">
                  <span>{so(l.so_dong_ho_ve_kho)}</span>
                  <b>{so(l.km_ve_kho)} km</b>
                </span>
                <span className="gh-diem__nut" />
              </li>
            )}
          </ol>
        </div>
      )}
    </article>
  );
}
