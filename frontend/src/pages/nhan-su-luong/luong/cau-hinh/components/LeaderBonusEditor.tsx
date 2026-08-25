// Bảng thưởng tổ trưởng theo bậc (tách từ pages/CauHinhLuongTab.tsx).
import { useEffect, useState } from "react";
import { api } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { RowActionButton } from "../../../../../components/RowActionButton";
import { money } from "../../../../../utils/format";
import type { BracketRow } from "../shared/types";
import { errText } from "../shared/helpers";
import { NumInput } from "./fields";

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
  const [thuLoi, setThuLoi] = useState(7);          // ô thử nhanh: tỷ lệ lỗi
  const [thuKhoan, setThuKhoan] = useState(0);      // tổng lương khoán giả định (TIỀN)
  const [thuSanLuong, setThuSanLuong] = useState(0); // sản lượng giả định (SỐ LƯỢNG)
  // Ngưỡng SẢN LƯỢNG tối thiểu để XÉT thưởng/phạt. 0 = không gác (giữ nguyên hành vi cũ).
  // ⚠️ Khác hẳn `thuKhoan`: ngưỡng là SỐ LƯỢNG, còn % thưởng/phạt nhân trên TIỀN.
  const [nguong, setNguong] = useState(0);

  useEffect(() => {
    let alive = true;
    api.luong
      .leaderBrackets(token, departmentId)
      .then((r) => {
        if (!alive) return;
        setRows(
          r.items.map((b) => ({
            up_to: b.up_to_defect_pct,
            rate: b.rate_pct,
            note: b.note ?? "",
          })),
        );
        setNguong(r.min_output_qty ?? 0);
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
      // Gợi ý rule-based: mốc mới = mốc kế cuối + 5. Bậc "trở lên" luôn giữ ở cuối.
      const coMoc = cur.filter((r) => r.up_to != null);
      const moc = coMoc.length ? (coMoc[coMoc.length - 1].up_to as number) + 5 : 5;
      const cuoi = cur.filter((r) => r.up_to == null);
      return [...coMoc, { up_to: moc, rate: 0, note: "" }, ...(cuoi.length ? cuoi : [
        { up_to: null, rate: 0, note: "" },
      ])];
    });
  }

  async function luu() {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const r = await api.luong.setLeaderBrackets(token, departmentId, (rows ?? []).map((x) => ({
        up_to_defect_pct: x.up_to,
        rate_pct: x.rate,
        note: x.note.trim() || null,
      })), nguong);
      setRows(
        r.items.map((b) => ({
          up_to: b.up_to_defect_pct,
          rate: b.rate_pct,
          note: b.note ?? "",
        })),
      );
      setNguong(r.min_output_qty ?? 0);
      setOk("Đã lưu bậc thưởng/phạt tổ trưởng.");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  /** Tra bậc — MIRROR đúng `PieceWorkService.leader_bonus_pct` ở backend: bậc ĐẦU TIÊN có
   *  `lỗi ≤ trần` thắng. Hai bên lệch nhau thì ô thử nhanh nói dối. */
  function traBac(loi: number): BracketRow | null {
    for (const r of rows ?? []) {
      if (r.up_to == null || loi <= r.up_to) return r;
    }
    const rs = rows ?? [];
    return rs.length ? rs[rs.length - 1] : null;
  }

  const bacTrung = traBac(thuLoi);
  /** MIRROR `PieceWorkService.duoi_nguong`: so bằng `<` — đúng bằng ngưỡng thì ĐƯỢC xét
   *  ("ít nhất X"). Lệch một chỗ ở đây là ô thử nói dối về chính thứ chủ đang khai.
   *  So với SẢN LƯỢNG, không phải với tiền khoán — hai con số khác nhau. */
  const duoiNguong = nguong > 0 && thuSanLuong < nguong;
  const tienThu = !bacTrung || duoiNguong ? 0 : Math.round((thuKhoan * bacTrung.rate) / 100);

  /** Đọc bảng mốc thành câu tiếng Việt — nhìn bảng số khó hình dung, đọc câu thì ra ngay. */
  const cauDoc = (rows ?? [])
    .map((r, i, arr) => {
      const truoc = i === 0 ? null : arr[i - 1].up_to;
      const pham =
        r.up_to == null
          ? `trên ${truoc ?? 0}%`
          : truoc == null
            ? `≤ ${r.up_to}%`
            : `trên ${truoc}–${r.up_to}%`;
      const act =
        r.rate > 0 ? `thưởng ${r.rate}%` : r.rate < 0 ? `phạt ${Math.abs(r.rate)}%` : "không thưởng/phạt";
      return `lỗi ${pham} ⇒ ${act}`;
    })
    .join(" · ");

  // Vế ngưỡng đứng TRƯỚC các vế bậc: nó chặn trước, đọc sau thì hiểu ngược thứ tự áp dụng.
  const nguongDoc = nguong.toLocaleString("vi-VN");
  const cauNguong =
    nguong > 0 ? `sản lượng của tổ dưới ${nguongDoc} ⇒ không xét thưởng/phạt` : "";

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Thưởng / phạt tổ trưởng theo chất lượng — {deptName}</h3>
          <p className="cl-card__desc">
            Tỷ lệ hàng lỗi của tổ càng thấp thì tổ trưởng được thưởng càng nhiều; lỗi vượt mốc
            thì bị trừ. Số % ở đây là <b>% trên TỔNG TIỀN KHOÁN của tổ</b> — tức là tiền.
          </p>
        </div>
        {!readOnly && (
          <Button variant="ghost" onClick={them}>
            + Thêm bậc
          </Button>
        )}
      </div>

      <div className="cl-card__body">
        {/* Sự thật phải nói thẳng: khai xong CHƯA ra tiền. ĐỪNG GỠ — cả mốc lẫn ngưỡng đều đang
            chờ nguồn sản lượng; khai xong mà tưởng đã chạy là mất niềm tin. */}
        <div className="banner banner--warn">
          <span>
            Tổng lương khoán của tổ hiện <b>luôn = 0</b> vì chưa có nguồn nhập sản lượng — khai mốc
            và ngưỡng ở đây là <b>chuẩn bị trước</b>, chưa ra tiền cho tới khi mở lại phần sản lượng.
          </span>
        </div>
        {!hasLeader && (
          <div className="banner banner--warn">
            <span>
              Tổ này <b>chưa có tổ trưởng</b> — khai mốc xong vẫn chưa có ai nhận. Gán ở màn
              <b> Phòng ban</b>.
            </span>
          </div>
        )}
        {err && <div className="banner banner--error">{err}</div>}
        {ok && <div className="banner banner--success">{ok}</div>}

        {rows === null ? (
          <p className="cl-hint-inline">Đang tải bậc thưởng/phạt…</p>
        ) : rows.length === 0 ? (
          <div className="cl-empty">
            <span className="cl-empty__title">Tổ này chưa áp thưởng/phạt tổ trưởng</span>
            <span className="cl-empty__desc">
              Bấm “+ Thêm bậc” để khai. Ví dụ: lỗi ≤ 5% ⇒ thưởng 2%; trên 10% ⇒ phạt 10%.
            </span>
          </div>
        ) : (
          <>
            {/* Ngưỡng đặt TRƯỚC bảng bậc vì nó chặn trước: dưới ngưỡng thì bảng bậc không được xét
                tới. Đặt sau bảng là đọc ngược thứ tự áp dụng. */}
            <div className="cl-lb__gate">
              <label className="ns-field">
                <span className="ns-field__label">Chỉ xét khi tổng sản lượng của tổ đạt ít nhất</span>
                <NumInput
                  value={nguong}
                  onChange={(v) => setNguong(v ?? 0)}
                  min={0}
                  step={100}
                  disabled={readOnly}
                />
              </label>
              <p className="cl-hint-inline">
                Để <b>0</b> là không chặn. Dùng khi tổ làm quá ít: hỏng 2 tờ trên 20 tờ đã là 10%
                lỗi, đủ rơi xuống bậc phạt nặng nhất dù thực tế chưa làm được gì.
              </p>
            </div>

            <div className="cl-table__wrap">
              <table className="cl-table cl-lb__table">
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>Bậc</th>
                    <th style={{ width: 190 }}>Tỷ lệ lỗi tới</th>
                    <th style={{ width: 210 }}>Thưởng (+) / Phạt (−)</th>
                    <th>Ghi chú</th>
                    {/* Ô tiêu đề trống (chỉ có aria-label) đọc được bằng máy nhưng người nhìn
                        bảng không biết cột cuối làm gì — cho CHỮ "Thao tác" như mọi bảng khác.
                        Nới 56 → 96 để chữ không ép cột "Ghi chú" xuống dòng. */}
                    {!readOnly && (
                      <th className="act" style={{ width: 96 }}>
                        Thao tác
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>
                        {r.up_to == null ? (
                          <span className="cl-muted">trở lên (mọi tỷ lệ cao hơn)</span>
                        ) : (
                          <NumInput
                            value={r.up_to}
                            onChange={(v) => patch(i, { up_to: v ?? 0 })}
                            suffix="%"
                            min={0}
                            max={100}
                            step={1}
                            disabled={readOnly}
                          />
                        )}
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
                            disabled={readOnly}
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
                            disabled={readOnly}
                            value={r.note}
                            onChange={(e) => patch(i, { note: e.target.value })}
                          />
                        </div>
                      </td>
                      {!readOnly && (
                        <td className="act">
                          <RowActionButton
                            dense
                            danger
                            label={`Xoá bậc ${i + 1}`}
                            icon="trash"
                            onClick={() =>
                              setRows((rs) => (rs ?? []).filter((_, k) => k !== i))
                            }
                          />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="cl-hint-inline cl-lb__read">
              {cauNguong ? `${cauNguong} · ${cauDoc}` : cauDoc}
            </p>

            {/* Thử nhanh — bám đúng helper "Tính nhanh phạt" của bảng phạt đi trễ.
                Đây là cách DUY NHẤT kiểm được cửa chặn hôm nay: chưa có nguồn sản lượng nên không
                có số thật nào để nhìn. */}
            <div className="cl-lb__try">
              <label className="ns-field">
                <span className="ns-field__label">Thử: tỷ lệ lỗi</span>
                <NumInput
                  value={thuLoi}
                  onChange={(v) => setThuLoi(v ?? 0)}
                  suffix="%"
                  min={0}
                  max={100}
                />
              </label>
             
              <label className="ns-field">
                <span className="ns-field__label">Sản lượng giả định</span>
                <NumInput
                  value={thuSanLuong}
                  onChange={(v) => setThuSanLuong(v ?? 0)}
                  min={0}
                  step={100}
                />
              </label>
              <label className="ns-field">
                <span className="ns-field__label">Tổng lương khoán giả định</span>
                <NumInput
                  value={thuKhoan}
                  onChange={(v) => setThuKhoan(v ?? 0)}
                  suffix="đ"
                  min={0}
                  step={1000000}
                />
              </label>
              <div className="cl-lb__out">
                {/* Dưới ngưỡng thì nói HẲN là không xét, đừng hiện "trúng bậc N ⇒ 0đ" — cùng ra 0
                    nhưng hai lý do khác hẳn nhau, và chủ cần biết là lý do nào. */}
                {!bacTrung ? (
                  "Chưa khai bậc nào."
                ) : duoiNguong ? (
                  <>
                    Dưới ngưỡng {nguongDoc} ⇒ <b>không xét thưởng/phạt</b>
                  </>
                ) : (
                  <>
                    Trúng bậc <b>{(rows ?? []).indexOf(bacTrung) + 1}</b> ⇒{" "}
                    <b>{bacTrung.rate > 0 ? `+${bacTrung.rate}` : bacTrung.rate}%</b>
                    {thuKhoan > 0 && (
                      <>
                        {" "}
                        ⇒{" "}
                        <b className={tienThu < 0 ? "lg-minus" : ""}>
                          {tienThu < 0 ? "−" : "+"}
                          {money(Math.abs(tienThu))}
                        </b>
                      </>
                    )}
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

// --- Tab con: Danh mục khoản thu nhập — TẦNG 1 (PRD v2, chốt chủ 27/07/2026) --
// Đây là BƯỚC 1 của quy trình 2 bước: muốn có khoản mới thì tạo Ở ĐÂY trước, rồi mới sang
// hồ sơ nhân viên (Lương → Lương nhân viên → Sửa lương) CHỌN khoản đó và nhập tiền. Hồ sơ NV
// không có ô gõ tên khoản tự do — nếu không, mỗi người một cách gọi và cờ "Chịu thuế" loạn.
// Cờ `is_taxable` CHỈ sống ở tầng này; tầng 2/3 chép lại, không sửa được.
// LƯU NGAY từng thao tác (không gom vào thanh lưu sticky): xoá là lệnh dứt điểm và câu báo
// phải khớp ĐÚNG việc backend vừa làm — xoá hẳn hay chỉ ngừng áp dụng.
