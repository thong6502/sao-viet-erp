// TAB "SẢN LƯỢNG" của bàn tổ (spec 2026-09-14 §6).
//
// Trả lời "từ ngày này tới ngày kia, tổ (và các tổ trực thuộc) làm ra bao nhiêu, cho lệnh nào, ai
// được bao nhiêu". Bảng mở ba tầng: LỆNH → CÔNG ĐOẠN (tốt · hỏng) → NGƯỜI (đã chốt · tạm tính).
//
// Mọi thứ lọc · cắt trang · cộng tổng Ở MÁY CHỦ. Ngày là ngày BẮT ĐẦU mẻ theo giờ xưởng. Số luôn đi
// theo ĐƠN VỊ — không cộng tờ với cái. Tổ chỉ thấy "của tôi" thì không có số tổ, không có tầng người:
// số là phần ĐÃ CHỐT của chính mình (bản chia nháp công nhân chưa được xem).
import { Fragment, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import {
  ApiError, api,
  type SxSanLuongTo, type SxSlCuaToi, type SxSlLenh, type SxSlTotHong,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { useDebounced } from "../utils/useDebounced";
import { BangLoi, EmptyState, ngay, num } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";

const CO_TRANG = 20;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function dauThang(d: Date): string {
  return ymd(new Date(d.getFullYear(), d.getMonth(), 1));
}

function dv(ma: string | null | undefined): string {
  return ma ? ` ${nhanDonVi(ma)}` : "";
}

/** Mỗi đơn vị một dòng — hai đơn vị nằm chồng, không bao giờ cộng thành một số. */
function CotSo({ ds, truong }: { ds: SxSlTotHong[]; truong: "tot" | "hong" }) {
  if (ds.length === 0) return <span className="thsx-sl__trong">—</span>;
  return (
    <span className="thsx-sl__so">
      {ds.map((s) => (
        <span key={s.don_vi ?? "—"}>
          <b className="thsx-num">{num(s[truong])}</b>{dv(s.don_vi)}
        </span>
      ))}
    </span>
  );
}

function CotCuaToi({ ds }: { ds: SxSlCuaToi[] }) {
  if (ds.length === 0) return <span className="thsx-sl__trong">—</span>;
  return (
    <span className="thsx-sl__so">
      {ds.map((s) => (
        <span key={s.don_vi ?? "—"}>
          <b className="thsx-num">{num(s.da_chot)}</b>{dv(s.don_vi)}
        </span>
      ))}
    </span>
  );
}

function khoaLenh(l: SxSlLenh): string {
  return `${l.nguon_loai}:${l.nguon_id ?? "-"}`;
}

export function ThsxSanLuongTab({ teamId, eventTick }: { teamId: number; eventTick?: number }) {
  const { token } = useAuth();
  const [tu, setTu] = useState(() => dauThang(new Date()));
  const [den, setDen] = useState(() => ymd(new Date()));
  const [toId, setToId] = useState<number | null>(null);
  const [tim, setTim] = useState("");
  const timD = useDebounced(tim, 250);
  const [trang, setTrang] = useState(1);
  const [data, setData] = useState<SxSanLuongTo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dangNap, setDangNap] = useState(false);
  const [moLenh, setMoLenh] = useState<Set<string>>(new Set());
  const [moCd, setMoCd] = useState<Set<number>>(new Set());
  const [lanNap, setLanNap] = useState(0); // bấm "Tải lại"

  const ngaySai = !!tu && !!den && tu > den;

  // Đổi bàn ⇒ ô Đơn vị của bàn cũ không còn nghĩa.
  useEffect(() => { setToId(null); }, [teamId]);
  // Đổi bộ lọc ⇒ về trang 1. SSE (`eventTick`) thì GIỮ trang đang đứng.
  useEffect(() => { setTrang(1); }, [teamId, tu, den, toId, timD]);

  useEffect(() => {
    if (!token || ngaySai || !tu || !den) return;
    let huy = false;
    setDangNap(true);
    api.sanXuat.sanLuongTo(token, {
      team_id: teamId, tu, den, to_id: toId, tim: timD, trang, co_trang: CO_TRANG,
    })
      .then((r) => { if (!huy) { setData(r); setErr(null); } })
      .catch((e: unknown) => {
        if (huy) return;
        setErr(e instanceof ApiError
          ? (e.isForbidden ? "Đơn vị này ngoài phạm vi của bạn." : e.message)
          : String(e));
      })
      .finally(() => { if (!huy) setDangNap(false); });
    return () => { huy = true; };
  }, [token, teamId, tu, den, toId, timD, trang, ngaySai, eventTick, lanNap]);

  const capGoc = useMemo(() => {
    const cap = (data?.cac_to ?? []).map((t) => t.cap);
    return cap.length ? Math.min(...cap) : 0;
  }, [data?.cac_to]);
  const tron = !!data?.co_pham_vi_tron;
  const rieng = !!data?.co_pham_vi_rieng;
  const soTrang = Math.max(1, Math.ceil((data?.tong_lenh ?? 0) / CO_TRANG));
  const soCot = 4 + (tron ? 2 : 0) + (rieng ? 1 : 0);

  const doiMo = <T,>(set: Dispatch<SetStateAction<Set<T>>>, k: T) =>
    set((cu) => {
      const moi = new Set(cu);
      if (moi.has(k)) moi.delete(k); else moi.add(k);
      return moi;
    });

  return (
    <section className="thsx-sl" aria-label="Sản lượng của tổ">
      <div className="thsx-subbar thsx-sl__loc">
        <label className="thsx-sl__f">
          <span>Từ ngày</span>
          <input type="date" value={tu} max={den || undefined} min="2000-01-01"
            onChange={(e) => setTu(e.target.value)} />
        </label>
        <label className="thsx-sl__f">
          <span>Đến ngày</span>
          <input type="date" value={den} min={tu || undefined} max="2200-12-31"
            onChange={(e) => setDen(e.target.value)} />
        </label>
        <button type="button" className="thsx-trang__nut"
          onClick={() => { const nay = new Date(); setTu(dauThang(nay)); setDen(ymd(nay)); }}>
          Tháng này
        </button>
        <label className="thsx-sl__f">
          <span>Đơn vị</span>
          <select value={toId ?? ""} onChange={(e) => setToId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Cả bàn này</option>
            {(data?.cac_to ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {"   ".repeat(Math.max(0, t.cap - capGoc))}{t.ten}
              </option>
            ))}
          </select>
        </label>
        <div className="thsx-search">
          <Icon name="search" size={15} className="thsx-search__ic" />
          <input type="search" className="thsx-search__in" value={tim}
            onChange={(e) => setTim(e.target.value)}
            placeholder="Tìm mã / tên lệnh…" aria-label="Tìm lệnh" />
          {tim && (
            <button type="button" className="thsx-search__clear" aria-label="Xoá tìm" onClick={() => setTim("")}>
              <Icon name="x" size={13} />
            </button>
          )}
        </div>
      </div>

      {data && !ngaySai && (
        <div className="thsx-sl__tong" aria-label="Tổng theo bộ lọc">
          {tron && (data.tong.length === 0 ? (
            <span className="thsx-sl__trong">Không có mẻ nào trong khoảng này.</span>
          ) : data.tong.map((t) => (
            <span key={t.don_vi ?? "—"} className="thsx-sl__chip">
              Tốt <b className="thsx-num">{num(t.tot)}</b>{dv(t.don_vi)}
              {t.hong > 0 && <> · hỏng <b className="thsx-num">{num(t.hong)}</b></>}
              <span className="thsx-sl__phu"> · {t.so_me} mẻ</span>
            </span>
          )))}
          {rieng && (
            <span className="thsx-sl__chip thsx-sl__chip--toi">
              Phần của tôi (đã chốt):{" "}
              {data.tong_cua_toi.length === 0 ? "chưa có" : data.tong_cua_toi.map((t, i) => (
                <Fragment key={t.don_vi ?? "—"}>
                  {i > 0 && " · "}<b className="thsx-num">{num(t.da_chot)}</b>{dv(t.don_vi)}
                </Fragment>
              ))}
            </span>
          )}
          {dangNap && <span className="thsx-sl__phu">Đang cập nhật…</span>}
        </div>
      )}

      <div className="thsx-ds__scroll">
        {ngaySai ? (
          <BangLoi text="Từ ngày phải trước hoặc bằng đến ngày." />
        ) : err ? (
          <BangLoi text={err} onRetry={() => setLanNap((n) => n + 1)} />
        ) : data == null ? (
          <div className="thsx-sl__trong">Đang nạp…</div>
        ) : data.lenh.length === 0 ? (
          <EmptyState icon={timD ? "search" : "clipboard"}
            title={timD ? "Không có lệnh khớp tìm kiếm" : "Chưa có sản lượng"}
            sub={`Không có mẻ nào bắt đầu từ ${ngay(data.tu)} đến ${ngay(data.den)} trong phạm vi của bạn.`} />
        ) : (
          <>
            <div className="thsx-ds__tbl-wrap thsx-sl__wrap">
              <table className="thsx-ds__tbl thsx-sl__tbl">
                <thead>
                  <tr>
                    <th aria-label="Mở rộng" />
                    <th>Lệnh / công đoạn</th>
                    <th>Ngày mẻ</th>
                    <th className="thsx-sl__r">Mẻ</th>
                    {tron && <th className="thsx-sl__r">Tốt</th>}
                    {tron && <th className="thsx-sl__r">Hỏng</th>}
                    {rieng && <th className="thsx-sl__r">Của tôi (đã chốt)</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.lenh.map((l) => {
                    const k = khoaLenh(l);
                    const mo = moLenh.has(k);
                    return (
                      <Fragment key={k}>
                        <tr className="thsx-ds__row thsx-sl__lenh" aria-expanded={mo}
                          tabIndex={0} onClick={() => doiMo(setMoLenh, k)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); doiMo(setMoLenh, k); } }}>
                          <td className="thsx-sl__mo"><Icon name="chevron" size={14} className={`thsx-sl__chev${mo ? " is-mo" : ""}`} /></td>
                          <td>
                            <b>{l.ma || "—"}</b>
                            {l.ten && <span className="thsx-sl__ten"> · {l.ten}</span>}
                            {l.nguon_loai === "bai_ghep" && <span className="thsx-sl__nhan">Bài ghép</span>}
                          </td>
                          <td className="thsx-sl__ngay">
                            {ngay(l.ngay_dau)}{l.ngay_cuoi && l.ngay_cuoi !== l.ngay_dau ? ` – ${ngay(l.ngay_cuoi)}` : ""}
                          </td>
                          <td className="thsx-sl__r thsx-num">{l.so_me}</td>
                          {tron && <td className="thsx-sl__r"><CotSo ds={l.san_luong} truong="tot" /></td>}
                          {tron && <td className="thsx-sl__r"><CotSo ds={l.san_luong} truong="hong" /></td>}
                          {rieng && <td className="thsx-sl__r"><CotCuaToi ds={l.phan_cua_toi} /></td>}
                        </tr>
                        {mo && l.cong_doan.map((c) => {
                          const moC = moCd.has(c.cong_viec_id);
                          const coNguoi = !c.cua_toi && c.nguoi.length > 0;
                          return (
                            <Fragment key={c.cong_viec_id}>
                              <tr className={`thsx-sl__cd${coNguoi ? " thsx-ds__row" : ""}`}
                                aria-expanded={coNguoi ? moC : undefined}
                                tabIndex={coNguoi ? 0 : undefined}
                                onClick={coNguoi ? () => doiMo(setMoCd, c.cong_viec_id) : undefined}
                                onKeyDown={coNguoi ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); doiMo(setMoCd, c.cong_viec_id); } } : undefined}>
                                <td />
                                <td>
                                  <div className="thsx-sl__cdten">
                                    {coNguoi
                                      ? <Icon name="chevron" size={12} className={`thsx-sl__chev${moC ? " is-mo" : ""}`} />
                                      : <span className="thsx-sl__cham" aria-hidden />}
                                    <span>
                                      {c.ten_cong_doan || "—"}
                                      {c.to_ten && <span className="thsx-sl__ten"> · {c.to_ten}</span>}
                                      {c.chua_chia > 0 && (
                                        <span className="thsx-sl__nhan thsx-sl__nhan--cho">{c.chua_chia} mẻ chưa chia</span>
                                      )}
                                    </span>
                                  </div>
                                </td>
                                <td />
                                <td className="thsx-sl__r thsx-num">{c.so_me}</td>
                                {tron && (c.cua_toi
                                  ? <td className="thsx-sl__r" colSpan={2}><span className="thsx-sl__trong">Chỉ thấy phần của mình</span></td>
                                  : <>
                                    <td className="thsx-sl__r"><CotSo ds={c.san_luong} truong="tot" /></td>
                                    <td className="thsx-sl__r"><CotSo ds={c.san_luong} truong="hong" /></td>
                                  </>)}
                                {rieng && <td className="thsx-sl__r"><CotCuaToi ds={c.phan_cua_toi} /></td>}
                              </tr>
                              {moC && coNguoi && (
                                <tr className="thsx-sl__nguoi-row">
                                  <td />
                                  <td colSpan={soCot - 1}>
                                    <table className="thsx-sl__nguoi">
                                      <thead>
                                        <tr>
                                          <th>Người</th>
                                          <th className="thsx-sl__r">Đã chốt</th>
                                          <th className="thsx-sl__r">Tạm tính</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {c.nguoi.map((n) => (
                                          <tr key={`${n.employee_id}-${n.don_vi}-${n.la_ho_tro}`}>
                                            <td>
                                              {n.ho_ten}
                                              {n.la_ho_tro && <span className="thsx-sl__nhan">Hỗ trợ chéo</span>}
                                            </td>
                                            <td className="thsx-sl__r">
                                              {n.da_chot ? <><b className="thsx-num">{num(n.da_chot)}</b>{dv(n.don_vi)}</> : <span className="thsx-sl__trong">—</span>}
                                            </td>
                                            <td className="thsx-sl__r">
                                              {n.tam_tinh ? <><span className="thsx-num">{num(n.tam_tinh)}</span>{dv(n.don_vi)}</> : <span className="thsx-sl__trong">—</span>}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          );
                        })}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {soTrang > 1 && (
              <div className="thsx-trang">
                <button type="button" className="thsx-trang__nut" disabled={trang <= 1}
                  onClick={() => setTrang((t) => Math.max(1, t - 1))}>
                  <Icon name="chevron" size={14} className="thsx-rot90" /> Trước
                </button>
                <span className="thsx-trang__vt">
                  Trang <b className="thsx-num">{trang}</b>/<b className="thsx-num">{soTrang}</b>
                  <span className="thsx-trang__tong"> · <b className="thsx-num">{data.tong_lenh}</b> lệnh</span>
                </span>
                <button type="button" className="thsx-trang__nut" disabled={trang >= soTrang}
                  onClick={() => setTrang((t) => Math.min(soTrang, t + 1))}>
                  Sau <Icon name="chevron" size={14} className="thsx-rot-90" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
