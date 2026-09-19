// TAB "SẢN LƯỢNG" của bàn tổ (spec 2026-09-14 §6, sửa 2026-09-18 §7.3b).
//
// Trả lời "từ ngày này tới ngày kia, tổ (và các tổ trực thuộc) làm ra bao nhiêu, cho lệnh nào, ai có
// mặt". Mẻ có MỘT chủ (tổ của bước) nên bảng chia hai mục:
//   · MẺ CỦA TỔ — cộng vào dòng tổng;
//   · NGƯỜI CỦA TỔ ĐI LÀM Ở TỔ KHÁC — cùng con số của mẻ, KHÔNG cộng tổng (đếm hai lượt là sai
//     sản lượng xưởng).
// Mỗi mục là MỘT bảng phẳng, mỗi dòng một mẻ: lệnh · tổ · công đoạn · mẻ · công việc · số lượng ·
// người tham gia (19/09/2026 — bỏ kiểu bấm mở ba tầng LỆNH → CÔNG ĐOẠN → MẺ). Không chia ai
// được bao nhiêu, không số phút, không tiền — "ghi nhận thế thôi, đừng có chia bất cứ gì".
//
// Mọi thứ lọc · cắt trang · cộng tổng Ở MÁY CHỦ. Ngày là ngày BẮT ĐẦU mẻ theo giờ xưởng. Số luôn đi
// theo ĐƠN VỊ — không cộng tờ với cái.
import { useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type SxSanLuongTo, type SxSlCongDoan, type SxSlKho, type SxSlLenh, type SxSlMe,
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

/** Màn điện thoại (≤640px) ⇒ bảng 8 cột đổi sang THẺ mỗi lệnh một thẻ. Chỉ vẽ MỘT bố cục, không
 *  vẽ cả hai rồi ẩn bằng CSS (chữ nhân đôi, test bắt trùng). jsdom không có matchMedia ⇒ coi là rộng. */
function useManDienThoai(): boolean {
  const truyVan = "(max-width: 640px)";
  const coMq = typeof window !== "undefined" && typeof window.matchMedia === "function";
  const [hep, setHep] = useState(() => coMq && window.matchMedia(truyVan).matches);
  useEffect(() => {
    if (!coMq) return;
    const mq = window.matchMedia(truyVan);
    const doi = () => setHep(mq.matches);
    doi();
    mq.addEventListener("change", doi);
    return () => mq.removeEventListener("change", doi);
  }, [coMq]);
  return hep;
}

/** "01/09 → 19/09" — tóm tắt khoảng ngày cho nút Lọc đang thu gọn. */
function ngayNgan(v: string): string {
  return v ? `${v.slice(8, 10)}/${v.slice(5, 7)}` : "…";
}

/** Tổng số làm được theo công đoạn (gộp các lần chạy cùng tên + cùng đơn vị), giữ thứ tự bảng. */
function gomTheoCd(cds: SxSlCongDoan[]): { khoa: string; ten: string; tot: number }[] {
  const m = new Map<string, { khoa: string; ten: string; tot: number }>();
  for (const c of cds) {
    for (const s of c.san_luong) {
      const khoa = `${c.ten_cong_doan}|${s.don_vi ?? ""}`;
      const x = m.get(khoa) ?? { khoa, ten: c.ten_cong_doan || "—", tot: 0 };
      x.tot += s.tot;
      m.set(khoa, x);
    }
  }
  return [...m.values()];
}

function ngayDu(d: Date): string {
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

/** Ngày đủ dd/mm/yyyy + khung giờ. Mẻ vắt qua ngày khác thì giờ kết thúc kèm luôn ngày của nó. */
function khungMe(m: SxSlMe): { ngay: string; gio: string | null } {
  // `ngay` là "YYYY-MM-DD" theo giờ xưởng — cắt thẳng ra, khỏi qua Date (lệch múi).
  const d = m.ngay ? `${m.ngay.slice(8, 10)}/${m.ngay.slice(5, 7)}/${m.ngay.slice(0, 4)}` : "—";
  if (!m.bat_dau) return { ngay: d, gio: null };
  const kt = m.ket_thuc ? new Date(m.ket_thuc) : null;
  const ktNgay = kt && !Number.isNaN(kt.getTime()) ? ngayDu(kt) : null;
  const duoi = !m.ket_thuc ? ""
    : ktNgay && ktNgay !== d ? ` → ${gioNgan(m.ket_thuc)} ${ktNgay}` : `–${gioNgan(m.ket_thuc)}`;
  return { ngay: d, gio: `${gioNgan(m.bat_dau)}${duoi}` };
}

/** mm → cm, số lẻ một chữ (78,5) — đúng cách xưởng ghi quy cách. */
function cm(mm: number): string {
  return (Math.round(mm) / 10).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

/** Giấy + ba khổ của lệnh: tên giấy + định lượng, rồi mỗi khổ một dòng "nhãn … dài × rộng" (cm). */
function QuyCachLenh({ qc }: { qc: SxSlLenh["quy_cach"] }) {
  if (!qc) return <span className="thsx-sl__trong">Chưa có quy cách</span>;
  const kho: [string, SxSlKho | null][] = [
    ["Tờ nguyên", qc.to_nguyen], ["Tờ in", qc.to_in], ["Con", qc.con],
  ];
  return (
    <div className="thsx-sl__qc">
      <div className="thsx-sl__qc-giay">
        <b>{qc.giay || "Chưa khai giấy"}</b>
        {qc.dinh_luong ? <span className="thsx-sl__qc-gsm thsx-num">{num(qc.dinh_luong)} gsm</span> : null}
      </div>
      <dl className="thsx-sl__qc-kho" aria-label="Quy cách dài × rộng, đơn vị cm">
        {kho.map(([nhan, k]) => (
          <div key={nhan}>
            <dt>{nhan}</dt>
            <dd className="thsx-num">{k ? <>{cm(k.dai)}<i>×</i>{cm(k.rong)}</> : "—"}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Việc phát sinh của mẻ — khối riêng dưới tên việc khoán, KHÔNG cộng vào cột Số lượng. */
function PhatSinhMe({ ds }: { ds: SxSlMe["phat_sinh"] }) {
  if (!ds?.length) return null;
  return (
    <div className="thsx-sl__ps" title="Việc phát sinh — không cộng vào sản lượng">
      <span className="thsx-sl__ps-tieu">Phát sinh</span>
      <ul>
        {ds.map((p, i) => (
          <li key={i}>
            <span className="thsx-sl__ps-ten">{p.ten || "—"}</span>
            <span className="thsx-sl__ps-so">
              <b className="thsx-num">{num(p.so_luong)}</b>
              {p.don_vi_ten || p.don_vi ? ` ${p.don_vi_ten || p.don_vi}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Mỗi người một dòng — tên tổ khách ghi nhỏ bên cạnh. */
function NguoiMe({ ds }: { ds: SxSlMe["nguoi"] }) {
  if (ds.length === 0) return <span className="thsx-sl__trong">Chưa ai vào mẻ</span>;
  return (
    <ul className="thsx-sl__ds-nguoi">
      {ds.map((n) => (
        <li key={n.employee_id}>
          {n.ho_ten}
          {n.to_ten && <span className="thsx-sl__to">{n.to_ten}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Bảng PHẲNG, mỗi dòng MỘT mẻ: Lệnh · Tổ · Công đoạn · Mẻ · Công việc · Số lượng · Người tham gia.
 *  Lệnh và công đoạn gộp ô theo số mẻ bên dưới (rowSpan) để đọc một lệnh liền một khối, không phải
 *  bấm mở từng tầng. Dòng tổng của lệnh nằm ngay dưới khối lệnh. */
function BangMuc({ muc, ds }: { muc: Muc; ds: { l: SxSlLenh; cds: SxSlCongDoan[] }[] }) {
  return (
    <div className="thsx-sl__wrap">
      <table className="thsx-sl__bang">
        <thead>
          <tr>
            <th>Lệnh sản xuất</th>
            <th>Giấy · quy cách (cm)</th>
            <th>{muc === "chu" ? "Tổ" : "Tổ chủ mẻ"}</th>
            <th>Công đoạn</th>
            <th>Mẻ</th>
            <th>Công việc</th>
            <th className="thsx-sl__r">Số lượng</th>
            <th>Người tham gia</th>
          </tr>
        </thead>
        {ds.map(({ l, cds }) => {
          // Công đoạn không có mẻ trên trang vẫn chiếm một dòng để không mất khỏi bảng.
          const dongCd = cds.map((c) => ({ c, me: c.me.length ? c.me : [null] }));
          const soDong = dongCd.reduce((a, x) => a + x.me.length, 0);
          // Dòng Cộng theo TỪNG CÔNG ĐOẠN, chỉ số: các bước khác đơn vị (tờ · con · cái) nên cộng
          // chung một số là sai, mà ghi đơn vị thì xưởng không muốn — tên công đoạn đã nói số nào của ai.
          const congCd = gomTheoCd(cds);
          const soMe = cds.reduce((a, c) => a + c.so_me, 0);
          return (
            <tbody key={`${muc}:${khoaLenh(l)}`} className="thsx-sl__khoi">
              {dongCd.map(({ c, me }, ic) =>
                me.map((m, im) => {
                  const k = khungMe(m ?? ({} as SxSlMe));
                  return (
                    <tr key={`${c.cong_viec_id}:${m?.batch_id ?? "trong"}`}>
                      {ic === 0 && im === 0 && (
                        <td rowSpan={soDong} className="thsx-sl__o-lenh">
                          <b className="thsx-num">{l.ma || "—"}</b>
                          {l.nguon_loai === "bai_ghep" && <span className="thsx-sl__nhan">Bài ghép</span>}
                          {l.ten && <span className="thsx-sl__phu-dong">{l.ten}</span>}
                        </td>
                      )}
                      {ic === 0 && im === 0 && (
                        <td rowSpan={soDong} className="thsx-sl__o-qc"><QuyCachLenh qc={l.quy_cach} /></td>
                      )}
                      {im === 0 && (
                        <>
                          <td rowSpan={me.length} className="thsx-sl__o-to">{c.to_ten || "—"}</td>
                          <td rowSpan={me.length} className="thsx-sl__o-cd">{c.ten_cong_doan || "—"}</td>
                        </>
                      )}
                      <td className="thsx-sl__o-me">
                        {m ? (
                          <>
                            <span className="thsx-num">{k.ngay}</span>
                            {k.gio && <span className="thsx-sl__phu-dong thsx-num">{k.gio}</span>}
                          </>
                        ) : <span className="thsx-sl__trong">—</span>}
                      </td>
                      <td>
                        {!m ? <span className="thsx-sl__trong">—</span>
                          : m.viec_khoan_ten ?? <span className="thsx-sl__canh">Chưa khai việc khoán</span>}
                        {m && <PhatSinhMe ds={m.phat_sinh} />}
                      </td>
                      <td className="thsx-sl__r">
                        {m ? <b className="thsx-num">{num(m.tot)}</b> : <span className="thsx-sl__trong">—</span>}
                      </td>
                      <td>{m ? <NguoiMe ds={m.nguoi} /> : <span className="thsx-sl__trong">—</span>}</td>
                    </tr>
                  );
                }),
              )}
              <tr className="thsx-sl__cong">
                <td colSpan={6}>
                  Cộng {l.ma || "lệnh"} · {soMe} mẻ
                  {muc === "khach" && <span className="thsx-sl__trong"> · không cộng vào tổng của tổ</span>}
                </td>
                <td className="thsx-sl__r">
                  {congCd.length === 0 ? <span className="thsx-sl__trong">—</span>
                    : congCd.length === 1 ? <b className="thsx-num">{num(congCd[0].tot)}</b>
                    : (
                      <dl className="thsx-sl__cong-cd">
                        {congCd.map((x) => (
                          <div key={x.khoa}>
                            <dt>{x.ten}</dt>
                            <dd className="thsx-num">{num(x.tot)}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                </td>
                <td />
              </tr>
            </tbody>
          );
        })}
      </table>
    </div>
  );
}

/** Điện thoại: mỗi lệnh MỘT thẻ — đầu thẻ là mã + quy cách, rồi từng công đoạn, mỗi mẻ một khối
 *  "ngày giờ … số lớn" + việc + người. Cùng dữ liệu, cùng cách cộng với bảng — chỉ đổi hình. */
function TheMuc({ muc, ds }: { muc: Muc; ds: { l: SxSlLenh; cds: SxSlCongDoan[] }[] }) {
  return (
    <div className="thsx-sl__the-ds">
      {ds.map(({ l, cds }) => {
        const congCd = gomTheoCd(cds);
        const soMe = cds.reduce((a, c) => a + c.so_me, 0);
        return (
          <article key={`${muc}:${khoaLenh(l)}`} className="thsx-sl__the">
            <header className="thsx-sl__the-dau">
              <b className="thsx-num">{l.ma || "—"}</b>
              {l.nguon_loai === "bai_ghep" && <span className="thsx-sl__nhan">Bài ghép</span>}
              {l.ten && <span className="thsx-sl__the-ten">{l.ten}</span>}
            </header>
            <div className="thsx-sl__the-qc"><QuyCachLenh qc={l.quy_cach} /></div>
            {cds.map((c) => (
              <section key={c.cong_viec_id} className="thsx-sl__the-cd">
                <h4>
                  <span>{c.ten_cong_doan || "—"}</span>
                  {c.to_ten && <span className="thsx-sl__the-to">{c.to_ten}</span>}
                </h4>
                {c.me.length === 0 ? (
                  <p className="thsx-sl__trong thsx-sl__the-trong">Không có mẻ trong khoảng này</p>
                ) : (
                  <ul className="thsx-sl__the-me">
                    {c.me.map((m) => {
                      const k = khungMe(m);
                      return (
                        <li key={m.batch_id}>
                          <div className="thsx-sl__the-me-dau">
                            <span className="thsx-num">
                              {k.ngay}
                              {k.gio && <span className="thsx-sl__phu-dong">{k.gio}</span>}
                            </span>
                            <b className="thsx-num thsx-sl__the-so">{num(m.tot)}</b>
                          </div>
                          <div className="thsx-sl__the-viec">
                            {m.viec_khoan_ten ?? <span className="thsx-sl__canh">Chưa khai việc khoán</span>}
                          </div>
                          <PhatSinhMe ds={m.phat_sinh} />
                          <NguoiMe ds={m.nguoi} />
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            ))}
            <footer className="thsx-sl__the-cong">
              <span className="thsx-sl__the-cong-nhan">
                Cộng · {soMe} mẻ
                {muc === "khach" && <span className="thsx-sl__trong"> · không cộng vào tổng của tổ</span>}
              </span>
              {congCd.map((x) => (
                <span key={x.khoa} className="thsx-sl__the-cong-cd">
                  {x.ten} <b className="thsx-num">{num(x.tot)}</b>
                </span>
              ))}
            </footer>
          </article>
        );
      })}
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
  const [lanNap, setLanNap] = useState(0); // bấm "Tải lại"
  const hep = useManDienThoai();
  // Điện thoại: ngày + đơn vị THU vào nút "Lọc" — bày hết ra thì bảng chỉ còn 1/4 màn hình.
  const [moLoc, setMoLoc] = useState(false);

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
  const tenTo = toId == null ? "Cả bàn này" : (data?.cac_to ?? []).find((t) => t.id === toId)?.ten ?? "Một tổ";
  const Bang = hep ? TheMuc : BangMuc;
  const oTim = (
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
  );

  return (
    <section className={`thsx-sl${hep ? " thsx-sl--hep" : ""}`} aria-label="Sản lượng của tổ">
      {hep && (
        <div className="thsx-subbar thsx-sl__loc-gon">
          {oTim}
          <button type="button" className={`thsx-sl__nut-loc${moLoc ? " is-mo" : ""}`}
            aria-expanded={moLoc} onClick={() => setMoLoc((v) => !v)}>
            <Icon name="calendar" size={14} />
            <span className="thsx-num">{ngayNgan(tu)} → {ngayNgan(den)}</span>
            {toId != null && <span className="thsx-sl__nut-loc-to" title={tenTo}>· {tenTo}</span>}
            <Icon name="chevron" size={13} className="thsx-sl__nut-loc-mui" />
          </button>
        </div>
      )}
      {(!hep || moLoc) && (
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
        {!hep && oTim}
      </div>
      )}

      {data && !ngaySai && (
        <div className="thsx-sl__tong" aria-label="Tổng theo bộ lọc">
          {tron ? (data.tong.length === 0 ? (
            <span className="thsx-sl__trong">Tổ không có mẻ nào trong khoảng này.</span>
          ) : (
            // MỘT dòng cho cả tổ — mỗi đơn vị một cụm số (tờ không cộng với cái), số mẻ cộng chung
            // ở cuối. Trước đây mỗi đơn vị một dòng "Mẻ của tổ · làm được…" lặp lại, chiếm nửa màn điện thoại.
            <p className="thsx-sl__tong-dong">
              <span className="thsx-sl__tong-nhan">Tổ làm được</span>
              {data.tong.map((t) => (
                <span key={t.don_vi ?? "—"} className="thsx-sl__chip">
                  <b className="thsx-num">{num(t.tot)}</b>{dv(t.don_vi)}
                  {t.hong > 0 && <span className="thsx-sl__hong-cum"> (hỏng <b className="thsx-num">{num(t.hong)}</b>)</span>}
                </span>
              ))}
              <span className="thsx-sl__phu">
                {num(data.tong.reduce((a, t) => a + t.so_me, 0))} mẻ
              </span>
            </p>
          )) : (
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
              : <Bang muc="chu" ds={dsChu} />}
            {dsKhach.length > 0 && (
              <>
                <h3 className="thsx-sl__muc thsx-sl__muc--khach">
                  Người của tổ đi làm ở tổ khác <span className="thsx-sl__muc-phu">— không cộng vào tổng</span>
                </h3>
                <Bang muc="khach" ds={dsKhach} />
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
