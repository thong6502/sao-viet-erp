// Lưới thưởng/phạt tổ trưởng: KHOẢNG SẢN LƯỢNG × TỶ LỆ LỖI → % (chủ 04/09/2026).
//
// Chủ: *"nó phải sét 2 điều kiện 1 là khoảng sản lượng, 2 là tỷ lệ lỗi"* và *"nó cũng tương tự
// như cái này nè"* (trỏ ô "Bậc số lượng → giá trị" của màn danh mục). Nên bảng này dùng LẠI đúng
// khung `RowEditor` của `danh-muc/fields/Bands.tsx` — cùng kiểu gõ Từ SL · Đến SL, cùng quy ước
// để trống = ∞ — thay vì vẽ một bảng thứ hai trông na ná mà thao tác lại khác.
import { useEffect, useState } from "react";
import { api } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { RowEditor } from "../../../../danh-muc/fields/RowEditor";
import { money } from "../../../../../utils/format";
import type { BracketRow } from "../shared/types";
import { errText } from "../shared/helpers";
import { NumInput } from "./fields";

/** Bảng mẫu đúng ví dụ chủ nêu — nút mồi ở màn rỗng, khai tay 7 dòng thì ai cũng nản. */
const MAU: BracketRow[] = [
  { sl_tu: 0, sl_den: 5000, up_to: 5, rate: 5, note: "" },
  { sl_tu: 0, sl_den: 5000, up_to: null, rate: -5, note: "" },
  { sl_tu: 5000, sl_den: 10000, up_to: 3, rate: 7, note: "" },
  { sl_tu: 5000, sl_den: 10000, up_to: 20, rate: -8, note: "" },
  { sl_tu: 5000, sl_den: 10000, up_to: null, rate: -15, note: "" },
  { sl_tu: 10000, sl_den: null, up_to: 3, rate: 10, note: "" },
  { sl_tu: 10000, sl_den: null, up_to: null, rate: -15, note: "" },
];

const so = (n: number) => n.toLocaleString("vi-VN");

/** Khoá nhóm — hai dòng cùng khoảng sản lượng thì cùng khoá. */
const khoaKhoang = (r: BracketRow) => `${r.sl_tu}|${r.sl_den ?? "∞"}`;

const docKhoang = (r: BracketRow) =>
  r.sl_den == null ? `trên ${so(r.sl_tu)}` : `${so(r.sl_tu)}–${so(r.sl_den)}`;

/** Gom các dòng liền nhau cùng khoảng sản lượng — dùng cho câu đọc và cho ô "trở lên" của nhóm. */
function gomNhom(rows: BracketRow[]): BracketRow[][] {
  const out: BracketRow[][] = [];
  for (const r of rows) {
    const cuoi = out[out.length - 1];
    if (cuoi && khoaKhoang(cuoi[0]) === khoaKhoang(r)) cuoi.push(r);
    else out.push([r]);
  }
  return out;
}

export function LeaderBonusEditor({
  token,
  departmentId,
  deptName,
  hasLeader,
  readOnly,
}: {
  token: string;
  departmentId: number;
  deptName: string;
  hasLeader: boolean;
  readOnly: boolean;
}) {
  const [rows, setRows] = useState<BracketRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // Ba ô thử: cả BA đều tác động tới tiền (sản lượng vừa là điều kiện vừa là thừa số), khác hẳn
  // khối thử cũ nơi "sản lượng giả định" chỉ dùng so ngưỡng nên đổi nó mà tiền đứng im.
  const [thuSL, setThuSL] = useState<number | null>(5000);
  const [thuLoi, setThuLoi] = useState<number | null>(3);
  const [thuDonGia, setThuDonGia] = useState<number | null>(300);

  useEffect(() => {
    let alive = true;
    // Đổi tổ là đổi hẳn bảng bậc ⇒ dọn luôn băng "Đã lưu"/"Lỗi" của tổ trước, không thì nó đứng
    // lại trên tổ mới và đọc thành "tổ này vừa lưu xong".
    setOk(null);
    setErr(null);
    api.luong
      .leaderBrackets(token, departmentId)
      .then((r) => {
        if (!alive) return;
        setRows(
          r.items.map((b) => ({
            sl_tu: b.sl_tu ?? 0,
            sl_den: b.sl_den,
            up_to: b.up_to_defect_pct,
            rate: b.rate_pct,
            note: b.note ?? "",
          })),
        );
        setErr(null);
      })
      .catch((e) => alive && setErr(errText(e)));
    return () => {
      alive = false;
    };
  }, [token, departmentId]);

  function patch(i: number, f: Partial<BracketRow>) {
    setRows((rs) => (rs ?? []).map((r, k) => (k === i ? { ...r, ...f } : r)));
  }

  function them() {
    setRows((rs) => {
      const cur = rs ?? [];
      const last = cur[cur.length - 1];
      if (!last) return [{ sl_tu: 0, sl_den: null, up_to: 5, rate: 0, note: "" }];
      // Dòng "trở lên" đã đóng khoảng ⇒ mở khoảng MỚI nối tiếp ngay tại trần cũ (không hở khe).
      if (last.up_to == null && last.sl_den != null) {
        return [...cur, { sl_tu: last.sl_den, sl_den: null, up_to: 5, rate: 0, note: "" }];
      }
      // Khoảng ∞ đã có dòng "trở lên" ⇒ KHÔNG mở được khoảng nào sau nó nữa. Nối thêm ở đuôi sẽ
      // ra HAI dòng "trở lên" trong cùng một khoảng — lưới hỏng, bấm Lưu là 400. Nên chèn mốc lỗi
      // mới NGAY TRƯỚC dòng "trở lên" để nó vẫn nằm chốt cuối khoảng.
      if (last.up_to == null) {
        const mocCuoi = [...cur]
          .reverse()
          .find((r) => r.sl_tu === last.sl_tu && r.up_to != null);
        const them: BracketRow = {
          sl_tu: last.sl_tu,
          sl_den: last.sl_den,
          up_to: (mocCuoi?.up_to ?? 0) + 5,
          rate: 0,
          note: "",
        };
        return [...cur.slice(0, cur.length - 1), them, last];
      }
      // Khoảng chưa đóng ⇒ thêm một mốc lỗi nữa cho CHÍNH khoảng đó.
      return [
        ...cur,
        { sl_tu: last.sl_tu, sl_den: last.sl_den, up_to: last.up_to + 5, rate: 0, note: "" },
      ];
    });
  }

  async function luu() {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const r = await api.luong.setLeaderBrackets(
        token,
        departmentId,
        (rows ?? []).map((x) => ({
          sl_tu: x.sl_tu,
          sl_den: x.sl_den,
          up_to_defect_pct: x.up_to,
          rate_pct: x.rate,
          note: x.note.trim() || null,
        })),
      );
      setRows(
        r.items.map((b) => ({
          sl_tu: b.sl_tu ?? 0,
          sl_den: b.sl_den,
          up_to: b.up_to_defect_pct,
          rate: b.rate_pct,
          note: b.note ?? "",
        })),
      );
      setOk("Đã lưu bậc thưởng/phạt tổ trưởng.");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  /** Tra bậc — MIRROR đúng `PieceWorkService.leader_bonus_pct`: lọc theo khoảng sản lượng
   *  (`sl_tu < SL ≤ sl_den`) rồi trong nhóm đó lấy dòng đầu tiên có `lỗi ≤ trần`.
   *  Hai bên lệch nhau thì ô thử nhanh nói dối về chính thứ chủ đang khai. */
  function traBac(sl: number | null, loi: number): number | null {
    if (sl == null) return null;
    const rs = rows ?? [];
    const idx = rs
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => r.sl_tu < sl && (r.sl_den == null || sl <= r.sl_den));
    if (!idx.length) return null;
    for (const { r, i } of idx) if (r.up_to == null || loi <= r.up_to) return i;
    return idx[idx.length - 1].i;
  }

  const iTrung = traBac(thuSL, thuLoi ?? 0);
  const bacTrung = iTrung == null ? null : (rows ?? [])[iTrung];
  const tienThu =
    bacTrung == null
      ? 0
      : Math.round(((thuSL ?? 0) * (thuDonGia ?? 0) * bacTrung.rate) / 100);

  const nhom = gomNhom(rows ?? []);
  /** Đọc lưới thành câu tiếng Việt, mỗi khoảng sản lượng một câu — nhìn bảng số khó hình dung. */
  const cauDoc = nhom.map((g) => {
    const ve = g
      .map((r, k) => {
        const truoc = k === 0 ? null : g[k - 1].up_to;
        const pham =
          r.up_to == null
            ? `trên ${truoc ?? 0}%`
            : truoc == null
              ? `≤ ${r.up_to}%`
              : `trên ${truoc}–${r.up_to}%`;
        const act =
          r.rate > 0
            ? `thưởng ${r.rate}%`
            : r.rate < 0
              ? `phạt ${Math.abs(r.rate)}%`
              : "không thưởng/phạt";
        return `lỗi ${pham} ⇒ ${act}`;
      })
      .join(" · ");
    return `Sản lượng ${docKhoang(g[0])}: ${ve}`;
  });
  const deuBang0 = (rows ?? []).length > 0 && (rows ?? []).every((r) => r.rate === 0);

  const saiKhoang = (r: BracketRow) => r.sl_den != null && r.sl_den <= r.sl_tu;

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Thưởng / phạt tổ trưởng theo chất lượng — {deptName}</h3>
          <p className="cl-card__desc">
            Lệnh sản xuất kết thúc thì xét <b>hai điều kiện</b>: sản lượng tổ làm được trong lệnh
            rơi vào khoảng nào, và tỷ lệ hàng lỗi KCS của lệnh đó. Tiền ={" "}
            <b>sản lượng × % của bậc trúng × đơn giá khoán của đầu việc</b>, cộng hoặc trừ thẳng
            vào lương tổ trưởng.
          </p>
        </div>
      </div>

      <div className="cl-card__body">
        {/* 04/09/2026: đã nối vào luồng thật (`services/san_xuat/thuong_to_truong.py`). Băng cũ
            nói "chưa ra tiền" đã gỡ — giữ lại là nói dối theo chiều ngược lại. Băng này nói ĐÚNG
            lúc nào tính và số nào được dùng, vì đó là chỗ người khai hay đoán sai. */}
        <div className="banner banner--info">
          <span>
            Tính <b>khi đóng nhóm thành phẩm</b>: sản lượng lấy từ phân bổ đã chốt của tổ, tỷ lệ
            lỗi lấy từ <b>phiếu KCS</b> (lỗi tổ đã nhận). Tiền vào cột <b>Thưởng/phạt tổ trưởng</b>
            trên bảng lương. Số đã ghi <b>không đổi</b> khi sửa bậc về sau.
          </span>
        </div>
        {!hasLeader && (
          <div className="banner banner--warn">
            <span>
              Tổ này <b>chưa có tổ trưởng</b> — khai bậc xong vẫn chưa có ai nhận. Gán ở màn
              <b> Phòng ban</b>.
            </span>
          </div>
        )}
        {err && <div className="banner banner--error">{err}</div>}
        {ok && <div className="banner banner--success">{ok}</div>}

        {rows === null ? (
          <p className="cl-hint-inline">Đang tải bậc thưởng/phạt…</p>
        ) : rows.length === 0 && readOnly ? (
          <div className="cl-empty">
            <span className="cl-empty__title">Tổ này chưa áp thưởng/phạt tổ trưởng</span>
          </div>
        ) : (
          <>
            {readOnly ? (
              <div className="cl-table__wrap">
                <table className="cl-table">
                  <thead>
                    <tr>
                      <th>Từ SL</th>
                      <th>Đến SL</th>
                      <th>Tỷ lệ lỗi</th>
                      <th>Thưởng (+) / Phạt (−)</th>
                      <th>Ghi chú</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td>{so(r.sl_tu)}</td>
                        <td>{r.sl_den == null ? "∞" : so(r.sl_den)}</td>
                        <td>{r.up_to == null ? "trở lên" : `${r.up_to} %`}</td>
                        <td className={r.rate < 0 ? "lg-minus" : undefined}>
                          {r.rate > 0 ? `+${r.rate}` : r.rate} %
                        </td>
                        <td>{r.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <RowEditor
                rows={rows}
                khoa="cl-lb__grid"
                cot={["Từ SL", "Đến SL", "Tỷ lệ lỗi", "Thưởng (+) / Phạt (−)", "Ghi chú"]}
                trong="Chưa có bậc — bấm “＋ Thêm bậc”, hoặc dùng bảng mẫu bên dưới."
                themNhan="＋ Thêm bậc"
                onThem={them}
                onXoa={(i) => setRows((rs) => (rs ?? []).filter((_, k) => k !== i))}
                xoaTitle="Xoá bậc"
                lopHang={(r, i) =>
                  [saiKhoang(r) ? "rc-bands__row--invalid" : "", i === iTrung ? "is-trung" : ""]
                    .filter(Boolean)
                    .join(" ") || undefined
                }
                veHang={(r, i) => (
                  <>
                    <td>
                      <NumInput
                        value={r.sl_tu}
                        onChange={(v) => patch(i, { sl_tu: v ?? 0 })}
                        min={0}
                        step={1000}
                        invalid={saiKhoang(r)}
                      />
                    </td>
                    <td>
                      <NumInput
                        value={r.sl_den}
                        onChange={(v) => patch(i, { sl_den: v })}
                        min={0}
                        step={1000}
                        placeholder="∞"
                        invalid={saiKhoang(r)}
                      />
                    </td>
                    <td>
                      <NumInput
                        value={r.up_to}
                        onChange={(v) => patch(i, { up_to: v })}
                        suffix="%"
                        min={0}
                        max={100}
                        step={1}
                        placeholder="trở lên"
                      />
                    </td>
                    <td>
                      <div className="cl-lb__rate">
                        <NumInput
                          value={r.rate}
                          onChange={(v) => patch(i, { rate: v ?? 0 })}
                          suffix="%"
                          min={-100}
                          max={100}
                          step={1}
                        />
                        {/* Dấu âm dễ đọc lướt thành dương ⇒ hiện chip chữ cho chắc. */}
                        <span
                          className={`ns-badge ${
                            r.rate > 0
                              ? "ns-badge--ok"
                              : r.rate < 0
                                ? "ns-badge--warn"
                                : "ns-badge--muted"
                          }`}
                        >
                          {r.rate > 0 ? "Thưởng" : r.rate < 0 ? "Phạt" : "Hòa"}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="rc-input-wrapper">
                        <input
                          className="rc-input"
                          type="text"
                          maxLength={255}
                          placeholder="vd: đạt chuẩn"
                          value={r.note}
                          onChange={(e) => patch(i, { note: e.target.value })}
                        />
                      </div>
                    </td>
                  </>
                )}
              />
            )}

            {rows.length === 0 && !readOnly && (
              <p className="cl-hint-inline">
                <Button variant="ghost" onClick={() => setRows(MAU.map((r) => ({ ...r })))}>
                  Dùng bảng mẫu 3 khoảng
                </Button>{" "}
                — đổ sẵn 0–5.000 · 5.000–10.000 · trên 10.000, sửa lại được.
              </p>
            )}

            {rows.length > 0 && (
              <div className="cl-hint-inline cl-lb__read">
                {deuBang0
                  ? "Bảng đang không thưởng cũng không phạt."
                  : cauDoc.map((c) => <div key={c}>{c}</div>)}
              </div>
            )}

            {/* Thử nhanh — bám đúng helper "Tính nhanh phạt" của bảng phạt đi trễ. Ba ô này là ba
                thứ engine thật sẽ lấy: sản lượng của tổ trong lệnh, tỷ lệ lỗi KCS, đơn giá khoán
                của đầu việc. Dòng trúng được tô sáng ngay trên bảng. */}
            <div className="cl-lb__try">
              <label className="ns-field">
                <span className="ns-field__label">Thử: sản lượng của lệnh</span>
                <NumInput value={thuSL} onChange={setThuSL} min={0} step={1000} />
              </label>
              <label className="ns-field">
                <span className="ns-field__label">Tỷ lệ lỗi KCS</span>
                <NumInput value={thuLoi} onChange={setThuLoi} suffix="%" min={0} max={100} />
              </label>
              <label className="ns-field">
                <span className="ns-field__label">Đơn giá khoán đầu việc</span>
                <NumInput value={thuDonGia} onChange={setThuDonGia} suffix="đ" min={0} step={50} />
              </label>
              <div className="cl-lb__out">
                {rows.length === 0 ? (
                  "Chưa khai bậc nào."
                ) : thuSL == null ? (
                  "Nhập sản lượng để thử."
                ) : bacTrung == null ? (
                  <>
                    Sản lượng {so(thuSL)} <b>không rơi vào khoảng nào</b> — thêm khoảng phủ mức
                    sản lượng này.
                  </>
                ) : (
                  <>
                    Trúng bậc <b>{(iTrung ?? 0) + 1}</b> (sản lượng {docKhoang(bacTrung)},{" "}
                    {bacTrung.up_to == null ? "lỗi trở lên" : `lỗi ≤ ${bacTrung.up_to}%`}) ⇒{" "}
                    <b>{bacTrung.rate > 0 ? `+${bacTrung.rate}` : bacTrung.rate}%</b> ⇒{" "}
                    <b className={tienThu < 0 ? "lg-minus" : ""}>
                      {tienThu < 0 ? "−" : "+"}
                      {money(Math.abs(tienThu))}
                    </b>
                  </>
                )}
              </div>
            </div>

            {!readOnly && (
              <div className="cl-lb__foot">
                <Button onClick={() => void luu()} disabled={busy}>
                  {busy ? "Đang lưu…" : "Lưu bậc thưởng/phạt"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
