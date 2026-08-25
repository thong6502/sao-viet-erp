// Tab con Bảo hiểm & Thuế (tách từ pages/CauHinhLuongTab.tsx).
import type { PayrollParams } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { RowActionButton } from "../../../../../components/RowActionButton";
import { money } from "../../../../../utils/format";
import { NumInput, ParamField } from "../components/fields";
import { INSURANCE_ROWS } from "../shared/constants";
import { toPct } from "../shared/helpers";
import type { BracketDraft, PenaltyDraft } from "../shared/types";

export function PhuCapTab({
  p,
  setP,
  brackets,
  setBrackets,
  bracketErrors,
  penalties,
  setPenalties,
  penaltyErrors,
  readOnly,
  busy,
}: {
  p: PayrollParams;
  setP: (key: keyof PayrollParams, value: number) => void;
  brackets: BracketDraft[];
  setBrackets: (f: (b: BracketDraft[]) => BracketDraft[]) => void;
  bracketErrors: Set<number>;
  penalties: PenaltyDraft[];
  setPenalties: (f: (b: PenaltyDraft[]) => PenaltyDraft[]) => void;
  penaltyErrors: Set<number>;
  readOnly: boolean;
  busy: boolean;
}) {
  const totalEr = p.bhxh_rate_er + p.bhyt_rate_er + p.bhtn_rate_er;
  const totalEe = p.bhxh_rate + p.bhyt_rate + p.bhtn_rate;

  function addPenalty() {
    setPenalties((bs) => {
      // Gợi ý rule-based: mốc phút bậc mới = mốc kế cuối + 30; tiền = tiền bậc cuối.
      const withCap = bs.filter((b) => b.up_to_minute != null);
      const lastCap = withCap.length
        ? (withCap[withCap.length - 1].up_to_minute as number)
        : 0;
      const amount = bs.length ? bs[bs.length - 1].amount : 20000;
      const row: PenaltyDraft = {
        key: `n${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        id: null,
        up_to_minute: lastCap + 30,
        amount,
      };
      // Bậc ∞ (up_to_minute rỗng) luôn phải đứng CUỐI → chèn bậc mới ngay trước nó.
      const tailInfinite =
        bs.length > 0 && bs[bs.length - 1].up_to_minute == null;
      return tailInfinite
        ? [...bs.slice(0, -1), row, bs[bs.length - 1]]
        : [...bs, row];
    });
  }

  function addBracket() {
    setBrackets((bs) => {
      // Gợi ý rule-based: mức của bậc mới = mức bậc kế cuối × 1,5; thuế suất giữ của bậc cuối.
      const withCap = bs.filter((b) => b.up_to != null);
      const lastCap = withCap.length
        ? (withCap[withCap.length - 1].up_to as number)
        : 5_000_000;
      const rate = bs.length ? bs[bs.length - 1].rate : 0.05;
      const row: BracketDraft = {
        key: `n${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        id: null,
        up_to: Math.round(lastCap * 1.5),
        rate,
      };
      // Bậc ∞ (up_to rỗng) luôn phải đứng CUỐI → chèn bậc mới ngay trước nó.
      const tailInfinite = bs.length > 0 && bs[bs.length - 1].up_to == null;
      return tailInfinite
        ? [...bs.slice(0, -1), row, bs[bs.length - 1]]
        : [...bs, row];
    });
  }

  return (
    <>
      {/* <div className="cl-override-note">
        <Info size={14} />
        <span>
          Bốn khoản phụ cấp (ca · trách nhiệm · thâm niên · khác) KHÔNG khai ở
          đây — gõ tay theo TỪNG NGƯỜI ở tab “Lương nhân viên”, một số cố định
          dùng cho mọi tháng.
        </span>
      </div> */}

      <div className="cl-card">
        <h3 className="cl-card__title">Bảo hiểm bắt buộc</h3>
        <div className="cl-card__body">
          <table className="cl-ins">
            <thead>
              <tr>
                <th>Khoản</th>
                <th className="num">NSDLĐ (%)</th>
                <th className="num">NLĐ (%)</th>
              </tr>
            </thead>
            <tbody>
              {INSURANCE_ROWS.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="num">
                    <NumInput
                      value={toPct(p[r.er])}
                      disabled={readOnly || busy}
                      suffix="%"
                      step={0.5}
                      min={0}
                      max={100}
                      onChange={(v) => setP(r.er, (v ?? 0) / 100)}
                    />
                  </td>
                  <td className="num">
                    <NumInput
                      value={toPct(p[r.ee])}
                      disabled={readOnly || busy}
                      suffix="%"
                      step={0.5}
                      min={0}
                      max={100}
                      onChange={(v) => setP(r.ee, (v ?? 0) / 100)}
                    />
                  </td>
                </tr>
              ))}
              <tr className="cl-ins__total">
                <td>Tổng</td>
                <td className="num">{toPct(totalEr)}%</td>
                <td className="num">{toPct(totalEe)}%</td>
              </tr>
            </tbody>
          </table>
          <p className="cl-hint-inline">
            Cột NSDLĐ KHÔNG trừ vào lương nhân viên — chỉ dùng để tính chi phí
            bảo hiểm của công ty và tổng quỹ lương.
          </p>
          <p className="cl-hint-inline">
            Nhân viên thử việc chưa đóng bảo hiểm.
          </p>
          <section className="rc-sec">
            <div className="rc-grid">
              <ParamField
                label="Trần đóng BHXH + BHYT"
                hint="Phần lương vượt trần không tính đóng BHXH và BHYT."
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.bh_base_cap}
                onChange={(v) => setP("bh_base_cap", v)}
              />
              <ParamField
                label="Trần đóng BHTN"
                hint="Trần riêng của BHTN, khác trần BHXH/BHYT."
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.bhtn_base_cap}
                onChange={(v) => setP("bhtn_base_cap", v)}
              />
              <ParamField
                label="Đoàn phí công đoàn (NV đóng)"
                hint="Trừ vào thực nhận, KHÔNG giảm thu nhập chịu thuế TNCN."
                suffix="%"
                step={0.5}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.cong_doan_rate)}
                onChange={(v) => setP("cong_doan_rate", v / 100)}
              />
              <ParamField
                label="TNLĐ-BNN (công ty đóng)"
                hint="Tai nạn LĐ – Bệnh nghề nghiệp. Dùng khi NV có BH đóng ở nơi khác — công ty chỉ chịu khoản này. KHÔNG trừ vào lương NV."
                suffix="%"
                step={0.1}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.tnld_bnn_rate)}
                onChange={(v) => setP("tnld_bnn_rate", v / 100)}
              />
              {/* Trước 29/07/2026 số 30% viết cứng trong engine, không đổi được từ màn. */}
              <ParamField
                label="Trần khấu trừ kỷ luật"
                hint="Điều 102 BLLĐ: tiền phạt / bồi thường trừ vào lương KHÔNG QUÁ 30% lương thực trả sau BHXH và thuế. Đặt 0 = TẮT trần (trừ trọn số đã ghi)."
                suffix="%"
                step={1}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.phat_cap_pct)}
                onChange={(v) => setP("phat_cap_pct", v / 100)}
              />
              {/* Cảnh báo, KHÔNG chặn: chủ toàn quyền, nhưng phải thấy mình đang vượt mức luật. */}
              {(toPct(p.phat_cap_pct) > 30 || toPct(p.phat_cap_pct) === 0) && (
                <p className="cl-hint-inline cl-warn-legal">
                  ⚠{" "}
                  {toPct(p.phat_cap_pct) === 0
                    ? "Đang TẮT trần — phạt bao nhiêu trừ bấy nhiêu (thực nhận vẫn không âm)."
                    : `Đang đặt ${toPct(p.phat_cap_pct)}%, VƯỢT mức 30% của Điều 102 BLLĐ.`}{" "}
                  Đây là mức luật định, không phải chính sách công ty.
                </p>
              )}
              {/* Trước 04/08/2026 số 14 viết cứng trong `payroll_service`. Đây là số NGÀY —
                  KHÔNG bọc `toPct` như mấy ô tỷ lệ ngay trên, chép nhầm là lệch 100 lần. */}
              <ParamField
                label="Không đóng BHXH nếu nghỉ không lương từ"
                hint="QĐ 595/QĐ-BHXH Đ42.4: tháng nào người lao động không làm việc và không hưởng lương từ 14 ngày làm việc trở lên thì tháng đó không đóng BHXH. Phủ luôn người vào/nghỉ việc giữa tháng. Đặt 0 = TẮT luật (tháng nào cũng trừ BHXH)."
                suffix="ngày"
                step={1}
                min={0}
                max={31}
                readOnly={readOnly}
                value={p.bhxh_mien_tu_so_ngay}
                onChange={(v) => setP("bhxh_mien_tu_so_ngay", Math.round(v))}
              />
              {/* Cảnh báo, KHÔNG chặn — cùng lối với trần Điều 102 ngay trên. */}
              {p.bhxh_mien_tu_so_ngay !== 14 && (
                <p className="cl-hint-inline cl-warn-legal">
                  ⚠{" "}
                  {p.bhxh_mien_tu_so_ngay === 0
                    ? "Đang TẮT luật — tháng nào cũng trừ BHXH, kể cả tháng nghỉ không lương cả tháng."
                    : `Đang đặt ${p.bhxh_mien_tu_so_ngay} ngày, LỆCH mức 14 ngày của QĐ 595 Đ42.4.`}{" "}
                  Đây là mức luật định, không phải chính sách công ty.
                </p>
              )}
            </div>
          </section>
        </div>
      </div>

      <div className="cl-card">
        <h3 className="cl-card__title">Thuế thu nhập cá nhân</h3>
        <p className="cl-card__desc">
          Thu nhập tính thuế = thu nhập chịu thuế − bảo hiểm − giảm trừ gia
          cảnh. Biểu lũy tiến từng phần, tính theo tháng. Sửa khi luật đổi (mặc
          định 2026: Luật 109/2025).
        </p>
        {/* Hai ô "khấu trừ tại nguồn" nằm CHUNG khối này vì cùng là số đổi theo luật, nhưng
            chúng đi đường thuế KHÁC HẲN: không giảm trừ gia cảnh, không trừ bảo hiểm. Không nói
            rõ thì người khai tưởng nó cộng thêm vào đường lũy tiến ở trên. */}
        <p className="cl-card__desc">
          Riêng hai ô <b>khấu trừ tại nguồn</b> chỉ áp cho người có cách tính
          thuế là <b>Khấu trừ 10%</b> (hợp đồng dưới 3 tháng · thời vụ · thực
          tập). Nhóm đó <b>không</b> được giảm trừ gia cảnh và <b>không</b> trừ
          bảo hiểm khi tính thuế — hai ô ở trên không ảnh hưởng tới họ.
        </p>
        <div className="cl-card__body">
          <section className="rc-sec">
            <div className="rc-grid">
              <ParamField
                label="Giảm trừ bản thân"
                hint={money(p.deduction_self)}
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.deduction_self}
                onChange={(v) => setP("deduction_self", v)}
              />
              <ParamField
                label="Giảm trừ mỗi người phụ thuộc"
                hint={money(p.deduction_dependent)}
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.deduction_dependent}
                onChange={(v) => setP("deduction_dependent", v)}
              />
              {/* Cảnh báo MỀM (vẫn lưu được) theo đúng kiểu ô "% lương thử việc": khai 0 là một
                  con số hợp lệ, nhưng hậu quả của nó im lặng — cả nhóm hợp đồng ngắn ra thuế 0đ
                  mà bảng lương trông vẫn bình thường. */}
              <ParamField
                label="Thuế suất khấu trừ tại nguồn"
                hint="Áp cho hợp đồng dưới 3 tháng · thời vụ · thực tập. Luật hiện hành: 10%."
                warn={
                  p.pit_flat_rate <= 0
                    ? "Khai 0% nghĩa là nhóm hợp đồng ngắn ra thuế 0đ — KHÔNG phải miễn thuế, và hệ thống không báo gì thêm."
                    : null
                }
                suffix="%"
                step={1}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.pit_flat_rate)}
                onChange={(v) => setP("pit_flat_rate", v / 100)}
              />
              <ParamField
                label="Ngưỡng bắt đầu khấu trừ tại nguồn"
                hint={`${money(p.pit_flat_threshold)} — dưới ngưỡng thì chưa khấu trừ. Tính trên TỔNG thu nhập chịu thuế cả tháng.`}
                warn={
                  p.pit_flat_threshold <= 0
                    ? "Khai 0 nghĩa là khấu trừ ngay từ đồng đầu tiên."
                    : null
                }
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.pit_flat_threshold}
                onChange={(v) => setP("pit_flat_threshold", v)}
              />
            </div>
          </section>

          <div className="cl-table__wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Bậc</th>
                  <th>Thu nhập tính thuế đến</th>
                  <th className="num" style={{ width: 160 }}>
                    Thuế suất
                  </th>
                  {/* Tên cột thống nhất là "Thao tác" (không phải "Xóa"), và có chữ hẳn hoi. */}
                  {!readOnly && (
                    <th className="act" style={{ width: 96 }}>
                      Thao tác
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {brackets.map((b, i) => (
                  <tr
                    key={b.key}
                    className={bracketErrors.has(i) ? "cl-row--invalid" : ""}
                  >
                    <td className="mono">
                      <strong>Bậc {i + 1}</strong>
                    </td>
                    <td>
                      <NumInput
                        value={b.up_to}
                        disabled={readOnly || busy}
                        suffix={b.up_to == null ? undefined : "đ"}
                        step={1000000}
                        min={0}
                        placeholder="∞ (bậc cao nhất)"
                        invalid={bracketErrors.has(i)}
                        onChange={(v) =>
                          setBrackets((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, up_to: v } : x,
                            ),
                          )
                        }
                      />
                      {b.up_to != null && (
                        <span className="cl-cell__sub">{money(b.up_to)}</span>
                      )}
                    </td>
                    <td className="num">
                      <NumInput
                        value={Math.round(b.rate * 100)}
                        disabled={readOnly || busy}
                        suffix="%"
                        step={1}
                        min={0}
                        max={100}
                        invalid={bracketErrors.has(i)}
                        onChange={(v) =>
                          setBrackets((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, rate: (v ?? 0) / 100 } : x,
                            ),
                          )
                        }
                      />
                    </td>
                    {!readOnly && (
                      <td className="act">
                        <RowActionButton
                          dense
                          danger
                          label={`Xoá bậc ${i + 1}`}
                          icon="trash"
                          onClick={() =>
                            setBrackets((bs) => bs.filter((_, j) => j !== i))
                          }
                        />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {bracketErrors.size > 0 && (
            <p className="cl-err">
              Mức của các bậc phải TĂNG DẦN · chỉ bậc CUỐI được để trống (∞) ·
              thuế suất từ 0 đến 100%.
            </p>
          )}
          {!readOnly && (
            <div className="cl-note">
              <Button variant="ghost" onClick={addBracket}>
                + Thêm bậc
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="cl-card">
        <h3 className="cl-card__title">khấu trừ đi trễ / về sớm</h3>
        <p className="cl-card__desc">
          Áp cho buổi đi trễ / về sớm KHÔNG phép (quá dung sai ca) — khấu trừ
          theo TỪNG LẦN
          {/* tra bảng theo số phút, Chủ nhật ×2 phút. Máy tự tính từ chấm
          công sẽ có ở bước sau; hiện dùng ở ô “Tính nhanh khấu trừ” của modal Sửa
          lương. */}
        </p>
        <div className="cl-card__body">
          <div className="cl-table__wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Bậc</th>
                  <th>Đến phút (∞ = trên hết)</th>
                  <th className="num" style={{ width: 200 }}>
                    Số tiền / lần
                  </th>
                  {/* Tên cột thống nhất là "Thao tác" (không phải "Xóa"), và có chữ hẳn hoi. */}
                  {!readOnly && (
                    <th className="act" style={{ width: 96 }}>
                      Thao tác
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {penalties.map((b, i) => (
                  <tr
                    key={b.key}
                    className={penaltyErrors.has(i) ? "cl-row--invalid" : ""}
                  >
                    <td className="mono">
                      <strong>Bậc {i + 1}</strong>
                    </td>
                    <td>
                      <NumInput
                        value={b.up_to_minute}
                        disabled={readOnly || busy}
                        suffix={b.up_to_minute == null ? undefined : "phút"}
                        step={5}
                        min={0}
                        placeholder="∞ (trên hết)"
                        invalid={penaltyErrors.has(i)}
                        onChange={(v) =>
                          setPenalties((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, up_to_minute: v } : x,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="num">
                      <NumInput
                        value={b.amount}
                        disabled={readOnly || busy}
                        suffix="đ"
                        step={10000}
                        min={0}
                        placeholder="0"
                        invalid={penaltyErrors.has(i)}
                        onChange={(v) =>
                          setPenalties((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, amount: v ?? 0 } : x,
                            ),
                          )
                        }
                      />
                      <span className="cl-cell__sub">{money(b.amount)}</span>
                    </td>
                    {!readOnly && (
                      <td className="act">
                        <RowActionButton
                          dense
                          danger
                          label={`Xoá bậc ${i + 1}`}
                          icon="trash"
                          onClick={() =>
                            setPenalties((bs) => bs.filter((_, j) => j !== i))
                          }
                        />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {penaltyErrors.size > 0 && (
            <p className="cl-err">
              Số phút của các bậc phải TĂNG DẦN · chỉ bậc CUỐI được để trống (∞)
              · số tiền ≥ 0.
            </p>
          )}
          {!readOnly && (
            <div className="cl-note">
              <Button variant="ghost" onClick={addPenalty}>
                + Thêm bậc
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
