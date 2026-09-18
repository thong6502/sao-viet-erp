// TAB "SẢN LƯỢNG" của bàn tổ (spec 2026-09-14 §6, sửa 2026-09-18 §7.3b).
//
// Trả lời "từ ngày này tới ngày kia, tổ (và các tổ trực thuộc) làm ra bao nhiêu, cho lệnh nào, ai có
// mặt". Mẻ có MỘT chủ (tổ của bước) nên bảng chia hai mục:
//   · MẺ CỦA TỔ — cộng vào dòng tổng;
//   · NGƯỜI CỦA TỔ ĐI LÀM Ở TỔ KHÁC — cùng con số của mẻ, KHÔNG cộng tổng (đếm hai lượt là sai
//     sản lượng xưởng).
// Mỗi mục mở ba tầng: LỆNH → CÔNG ĐOẠN → MẺ (việc khoán · tốt · hỏng · người tham gia). Không chia ai
// được bao nhiêu, không số phút, không tiền — "ghi nhận thế thôi, đừng có chia bất cứ gì".
//
// Mọi thứ lọc · cắt trang · cộng tổng Ở MÁY CHỦ. Ngày là ngày BẮT ĐẦU mẻ theo giờ xưởng. Số luôn đi
// theo ĐƠN VỊ — không cộng tờ với cái.
import {
  Fragment, useEffect, useMemo, useState,
  type Dispatch, type KeyboardEvent, type SetStateAction,
} from "react";
import {
  ApiError, api,
  type SxSanLuongTo, type SxSlCongDoan, type SxSlLenh, type SxSlMe, type SxSlTotHong,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { useDebounced } from "../utils/useDebounced";
import { BangLoi, EmptyState, gioNgan, ngay, num } from "./keHoachSxShared";
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

function khoaLenh(l: SxSlLenh): string {
  return `${l.nguon_loai}:${l.nguon_id ?? "-"}`;
}

type Muc = "chu" | "khach";

/** Tách công đoạn của từng lệnh theo mục; lệnh không còn công đoạn nào ở mục đó thì bỏ. */
function theoMuc(lenh: SxSlLenh[], muc: Muc): { l: SxSlLenh; cds: SxSlCongDoan[] }[] {
  return lenh
    .map((l) => ({ l, cds: l.cong_doan.filter((c) => c.la_khach === (muc === "khach")) }))
    .filter((x) => x.cds.length > 0);
}

/** Dòng lệnh của mục KHÁCH: gom số của vài công đoạn khách trên trang đang xem để tổ đọc cho nhanh.
 *  Mục này không vào dòng tổng nào — đây chỉ là số hiển thị của đúng một dòng. */
function gomSo(cds: SxSlCongDoan[]): SxSlTotHong[] {
  const m = new Map<string | null, SxSlTotHong>();
  for (const c of cds) {
    for (const s of c.san_luong) {
      const cu = m.get(s.don_vi) ?? { don_vi: s.don_vi, tot: 0, hong: 0 };
      m.set(s.don_vi, { don_vi: s.don_vi, tot: cu.tot + s.tot, hong: cu.hong + s.hong });
    }
  }
  return [...m.values()];
}

function khoangNgay(cds: SxSlCongDoan[]): string {
  const ds = cds.flatMap((c) => c.me.map((m) => m.ngay)).filter((d): d is string => !!d).sort();
  if (ds.length === 0) return "—";
  const dau = ds[0], cuoi = ds[ds.length - 1];
  return dau === cuoi ? ngay(dau) : `${ngay(dau)} – ${ngay(cuoi)}`;
}

function khungMe(m: SxSlMe): string {
  // `ngay` là "YYYY-MM-DD" theo giờ xưởng — cắt thẳng ra dd/mm, khỏi qua Date (lệch múi).
  const d = m.ngay ? `${m.ngay.slice(8, 10)}/${m.ngay.slice(5, 7)}` : "—";
  return m.bat_dau ? `${d} · ${gioNgan(m.bat_dau)}${m.ket_thuc ? `–${gioNgan(m.ket_thuc)}` : ""}` : d;
}

function NguoiMe({ ds }: { ds: SxSlMe["nguoi"] }) {
  if (ds.length === 0) return <span className="thsx-sl__trong">chưa ai vào mẻ</span>;
  return (
    <span className="thsx-sl__ds-nguoi">
      {ds.map((n, i) => (
        <Fragment key={n.employee_id}>
          {i > 0 && " · "}
          <span>{n.ho_ten}{n.to_ten && <span className="thsx-sl__to"> ({n.to_ten})</span>}</span>
        </Fragment>
      ))}
    </span>
  );
}

function BangMuc({ muc, ds, moLenh, moCd, doiLenh, doiCd }: {
  muc: Muc; ds: { l: SxSlLenh; cds: SxSlCongDoan[] }[];
  moLenh: Set<string>; moCd: Set<string>;
  doiLenh: (k: string) => void; doiCd: (k: string) => void;
}) {
  const bamPhim = (f: () => void) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); f(); }
  };
  return (
    <div className="thsx-ds__tbl-wrap thsx-sl__wrap">
      <table className="thsx-ds__tbl thsx-sl__tbl">
        <thead>
          <tr>
            <th aria-label="Mở rộng" />
            <th>{muc === "chu" ? "Lệnh / công đoạn" : "Lệnh / công đoạn · chủ mẻ"}</th>
            <th>Ngày mẻ</th>
            <th className="thsx-sl__r">Mẻ</th>
            <th className="thsx-sl__r">Tốt</th>
            <th className="thsx-sl__r">Hỏng</th>
          </tr>
        </thead>
        <tbody>
          {ds.map(({ l, cds }) => {
            const k = `${muc}:${khoaLenh(l)}`;
            const mo = moLenh.has(k);
            // Mục chủ lấy số máy chủ đã cộng (chỉ gồm mẻ của tổ); mục khách gom tại chỗ để hiển thị.
            const sl = muc === "chu" ? l.san_luong : gomSo(cds);
            return (
              <Fragment key={k}>
                <tr className="thsx-ds__row thsx-sl__lenh" aria-expanded={mo}
                  tabIndex={0} onClick={() => doiLenh(k)} onKeyDown={bamPhim(() => doiLenh(k))}>
                  <td className="thsx-sl__mo"><Icon name="chevron" size={14} className={`thsx-sl__chev${mo ? " is-mo" : ""}`} /></td>
                  <td>
                    <b>{l.ma || "—"}</b>
                    {l.ten && <span className="thsx-sl__ten"> · {l.ten}</span>}
                    {l.nguon_loai === "bai_ghep" && <span className="thsx-sl__nhan">Bài ghép</span>}
                  </td>
                  <td className="thsx-sl__ngay">{khoangNgay(cds)}</td>
                  <td className="thsx-sl__r thsx-num">{cds.reduce((a, c) => a + c.so_me, 0)}</td>
                  <td className="thsx-sl__r"><CotSo ds={sl} truong="tot" /></td>
                  <td className="thsx-sl__r"><CotSo ds={sl} truong="hong" /></td>
                </tr>
                {mo && cds.map((c) => {
                  const kc = `${muc}:${c.cong_viec_id}`;
                  const moC = moCd.has(kc);
                  return (
                    <Fragment key={kc}>
                      <tr className="thsx-sl__cd thsx-ds__row" aria-expanded={moC} tabIndex={0}
                        onClick={() => doiCd(kc)} onKeyDown={bamPhim(() => doiCd(kc))}>
                        <td />
                        <td>
                          <div className="thsx-sl__cdten">
                            <Icon name="chevron" size={12} className={`thsx-sl__chev${moC ? " is-mo" : ""}`} />
                            <span>
                              {c.ten_cong_doan || "—"}
                              {c.to_ten && (
                                <span className="thsx-sl__ten"> · {muc === "khach" ? `chủ mẻ: ${c.to_ten}` : c.to_ten}</span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td />
                        <td className="thsx-sl__r thsx-num">{c.so_me}</td>
                        <td className="thsx-sl__r"><CotSo ds={c.san_luong} truong="tot" /></td>
                        <td className="thsx-sl__r"><CotSo ds={c.san_luong} truong="hong" /></td>
                      </tr>
                      {moC && (
                        <tr className="thsx-sl__nguoi-row">
                          <td />
                          <td colSpan={5}>
                            <table className="thsx-sl__nguoi thsx-sl__me">
                              <thead>
                                <tr>
                                  <th>Mẻ</th>
                                  <th>Công việc khoán</th>
                                  <th className="thsx-sl__r">Tốt</th>
                                  <th className="thsx-sl__r">Hỏng</th>
                                  <th>Người tham gia</th>
                                </tr>
                              </thead>
                              <tbody>
                                {c.me.map((m) => (
                                  <tr key={m.batch_id}>
                                    <td className="thsx-num">{khungMe(m)}</td>
                                    <td>{m.viec_khoan_ten ?? <span className="thsx-sl__trong">— chưa khai việc khoán</span>}</td>
                                    <td className="thsx-sl__r"><b className="thsx-num">{num(m.tot)}</b>{dv(m.don_vi)}</td>
                                    <td className="thsx-sl__r">
                                      {m.hong ? <span className="thsx-num">{num(m.hong)}</span> : <span className="thsx-sl__trong">—</span>}
                                    </td>
                                    <td><NguoiMe ds={m.nguoi} /></td>
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
  );
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
  const [moCd, setMoCd] = useState<Set<string>>(new Set());
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
  const soTrang = Math.max(1, Math.ceil((data?.tong_lenh ?? 0) / CO_TRANG));
  const dsChu = useMemo(() => theoMuc(data?.lenh ?? [], "chu"), [data?.lenh]);
  const dsKhach = useMemo(() => theoMuc(data?.lenh ?? [], "khach"), [data?.lenh]);

  const doiMo = <T,>(set: Dispatch<SetStateAction<Set<T>>>, k: T) =>
    set((cu) => {
      const moi = new Set(cu);
      if (moi.has(k)) moi.delete(k); else moi.add(k);
      return moi;
    });
  const doiLenh = (k: string) => doiMo(setMoLenh, k);
  const doiCd = (k: string) => doiMo(setMoCd, k);

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
                {"   ".repeat(Math.max(0, t.cap - capGoc))}{t.ten}
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
          {tron ? (data.tong.length === 0 ? (
            <span className="thsx-sl__trong">Tổ không có mẻ nào trong khoảng này.</span>
          ) : data.tong.map((t) => (
            <span key={t.don_vi ?? "—"} className="thsx-sl__chip">
              Mẻ của tổ · tốt <b className="thsx-num">{num(t.tot)}</b>{dv(t.don_vi)}
              {t.hong > 0 && <> · hỏng <b className="thsx-num">{num(t.hong)}</b></>}
              <span className="thsx-sl__phu"> · {t.so_me} mẻ</span>
            </span>
          ))) : (
            // Quyền chỉ "Của tôi": không có tổng của tổ — thấy đúng các mẻ mình có mặt (§12.3).
            <span className="thsx-sl__phu">Bạn thấy các mẻ mình có mặt — không có dòng tổng của tổ.</span>
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
            <h3 className="thsx-sl__muc">Mẻ của tổ</h3>
            {dsChu.length === 0
              ? <p className="thsx-sl__trong thsx-sl__muc-trong">Trang này không có mẻ nào của tổ.</p>
              : <BangMuc muc="chu" ds={dsChu} moLenh={moLenh} moCd={moCd} doiLenh={doiLenh} doiCd={doiCd} />}
            {dsKhach.length > 0 && (
              <>
                <h3 className="thsx-sl__muc thsx-sl__muc--khach">
                  Người của tổ đi làm ở tổ khác <span className="thsx-sl__muc-phu">— không cộng vào tổng</span>
                </h3>
                <BangMuc muc="khach" ds={dsKhach} moLenh={moLenh} moCd={moCd} doiLenh={doiLenh} doiCd={doiCd} />
              </>
            )}
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
