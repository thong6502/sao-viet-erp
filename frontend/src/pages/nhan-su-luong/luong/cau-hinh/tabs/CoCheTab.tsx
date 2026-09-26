// Tab con Cơ chế lương theo bộ phận (tách từ pages/CauHinhLuongTab.tsx).
import { useMemo } from "react";
import { Info } from "lucide-react";
import type {
  Department,
  DeptComponent,
  PayrollParams,
  SalaryComponentKey,
} from "../../../../../api/client";
import { KhoanKmEditor } from "../components/KhoanKmEditor";
import { ChiTieuNgayEditor } from "../components/ChiTieuNgayEditor";
import { ToTruongEditor } from "../components/ToTruongEditor";
import { DeptChips } from "../components/DeptChips";
import { NumInput, ParamField, Switch } from "../components/fields";
import { COMPONENT_ROWS, OT_FIELDS } from "../shared/constants";
import { toGio, toPct } from "../shared/helpers";

export function CoCheTab({
  token,
  p,
  setP,
  depts,
  deptId,
  onPickDept,
  comps,
  setComps,
  loading,
  readOnly,
  busy,
  khoanDaLuu = false,
}: {
  token: string;
  p: PayrollParams;
  setP: (key: keyof PayrollParams, value: number | boolean) => void;
  depts: Department[];
  deptId: number | null;
  onPickDept: (id: number) => void;
  comps: DeptComponent[];
  setComps: (f: (c: DeptComponent[]) => DeptComponent[]) => void;
  loading: boolean;
  readOnly: boolean;
  busy: boolean;
  /** Công tắc Lương khoán của tổ đã BẬT VÀ ĐÃ LƯU — backend chỉ nhận chỉ tiêu ngày cho tổ đó.
   *  Khác `khoanOn` (bản nháp): gạt bật mà chưa bấm Lưu thì chưa khai chỉ tiêu được. */
  khoanDaLuu?: boolean;
}) {
  const dept = depts.find((d) => d.id === deptId);
  const deptName = dept?.name ?? "";
  const empCounts = useMemo(() => {
    const m: Record<number, number> = {};
    for (const d of depts) m[d.id] = d.employee_count ?? 0;
    return m;
  }, [depts]);

  const patchComp = (key: SalaryComponentKey, patch: Partial<DeptComponent>) =>
    setComps((cs) =>
      cs.map((c) => {
        if (c.component_key === key) return { ...c, ...patch };
        // ⚠️ GỠ 17/08/2026 — trước đây Khoán ⟷ Tăng ca loại trừ nhau (bật cái này tự tắt cái kia).
        // Hai công tắc vẫn ĐỘC LẬP. Từ 14/09/2026 tổ khoán KHÔNG có tiền GIỜ tăng ca (chế độ khoán),
        // nhưng công tắc Tăng ca của tổ đó vẫn quyết cơm tăng ca + phần thêm ngày CN/lễ.
        return c;
      }),
    );
  const khoanOn =
    comps.find((c) => c.component_key === "luong_khoan")?.is_enabled ?? false;
  // Cờ Giao hàng dùng TRỰC TIẾP (không kế thừa cây) — khớp `_chup_don_gia_km` ở BE đọc cờ RIÊNG
  // của phòng tài xế. Tài xế phải thuộc đúng phòng bật cờ thì mới có khoán km.
  const laGiaoHang = depts.find((d) => d.id === deptId)?.la_giao_hang ?? false;

  return (
    <>
      <div className="cl-card">
        <h3 className="cl-card__title">Áp dụng toàn công ty</h3>
        <p className="cl-card__desc">
          Tham số nền cho mọi bộ phận. Bộ phận nào cần khác thì ghi đè ở khối
          dưới.
        </p>
        <div className="cl-card__body">
          <section className="rc-sec">
            <div className="rc-sec__title">Công chuẩn</div>
            <div className="cl-override-note">
              <Info size={14} />
              <span>
                <b>Công chuẩn / tháng</b> tự tính theo Chấm công →{" "}
                <b>Lịch &amp; Ngày lễ</b> (tuần làm việc − ngày lễ + làm bù)
                {/* nên mỗi tháng một khác — không khai tay ở đây nữa. */}
              </span>
            </div>
            <div className="rc-grid">
              <ParamField
                label="Giờ công chuẩn / ngày"
                hint="Quy ra đơn giá 1 giờ tăng ca, và là số giờ mọi ca phải làm (khi bật ô dưới)."
                suffix="h"
                step={0.5}
                min={1}
                max={24}
                readOnly={readOnly}
                value={p.standard_hours_per_day}
                onChange={(v) => setP("standard_hours_per_day", v)}
              />
              {/* Chủ chốt 07/09/2026: khai ca phải khớp giờ công chuẩn — "không thì sinh ra hệ thống làm gì". */}
              <label className="cl-check" style={{ gridColumn: "1 / -1" }}>
                <input
                  type="checkbox"
                  checked={p.ca_khop_gio_chuan ?? true}
                  disabled={readOnly}
                  onChange={(e) => setP("ca_khop_gio_chuan", e.target.checked)}
                />
                <span>
                  <b>Ca phải khớp giờ công chuẩn</b> — khai ca mà (giờ ra − giờ vào − nghỉ giữa ca)
                  khác số trên thì không cho lưu. Tắt chỉ khi có ca bán thời gian.
                </span>
              </label>
              <ParamField
                label="% lương thử việc"
                hint="Nhân vào mức nền của người đang thử việc."
                warn={
                  p.probation_ratio < 0.85
                    ? "Điều 26 BLLĐ tối thiểu 85% — vẫn lưu được, nhưng nên rà lại."
                    : null
                }
                suffix="%"
                min={1}
                max={100}
                readOnly={readOnly}
                value={toPct(p.probation_ratio)}
                onChange={(v) => setP("probation_ratio", v / 100)}
              />
              <ParamField
                label="Hạn mức chỉnh công / tháng"
                hint="Số NGÀY CÔNG mỗi người được tự xin chỉnh trong 1 tháng. Đếm theo ngày, không theo số đơn — quên cả giờ vào lẫn giờ ra của cùng một ngày vẫn là 1 lần. Đơn bị từ chối/hủy trả lại lượt. HCNS chấm bù trực tiếp KHÔNG bị giới hạn. 0 = không giới hạn."
                suffix="ngày"
                step={1}
                min={0}
                max={31}
                readOnly={readOnly}
                value={p.adjust_max_per_month}
                onChange={(v) => setP("adjust_max_per_month", Math.round(v))}
              />
              {/* Có cột từ 03/08/2026 và tài liệu ghi "khai được", nhưng thiếu cả ô nhập lẫn tên
                  trong allowlist của `update_params` ⇒ thực tế là số cứng 0,5. Nối nốt. */}
              <ParamField
                label="Công tối thiểu để hưởng cơm / phụ cấp ca"
                hint="Ngày nào đạt từ mức công này trở lên thì hưởng TRỌN tiền cơm + phụ cấp của ca hôm đó; dưới mức thì không có gì — cố ý không chia theo tỷ lệ, vì một suất ăn là có hoặc không. 0,5 = nghỉ nửa buổi vẫn được hưởng."
                suffix="công"
                step={0.25}
                min={0}
                max={1}
                readOnly={readOnly}
                value={p.phu_cap_ca_min_cong}
                onChange={(v) => setP("phu_cap_ca_min_cong", v)}
              />
              <ParamField
                label="Công tối thiểu để tạm ứng / nhận lương đợt 1"
                hint="Phải có ít nhất ngần này CÔNG TÍNH LƯƠNG (đi làm + phép có lương + lễ) tính từ ngày 1 của kỳ tới ngày lập phiếu thì mới lập được phiếu tạm ứng hoặc phiếu lương đợt 1 — kể cả phiếu nhân viên tự xin. Chưa đủ là bị chặn. 0 = tắt điều kiện."
                suffix="công"
                step={0.5}
                min={0}
                max={31}
                readOnly={readOnly}
                value={p.tam_ung_cong_toi_thieu}
                onChange={(v) => setP("tam_ung_cong_toi_thieu", v)}
              />
            </div>
          </section>
          <section className="rc-sec">
            <div className="rc-sec__title">
              Hệ số làm thêm &amp; ngày đặc biệt
            </div>
            <div className="rc-grid">
              {/* TRẦN GIỜ LÀM THÊM (Đ107) — chủ chốt 17/08/2026. Backend lưu bằng PHÚT, người
                  dùng nghĩ bằng GIỜ ⇒ ô nhập theo giờ, ×60 lúc lưu / ÷60 lúc đọc. Đây là chỗ
                  DUY NHẤT nới trần: hết trần thì phiếu tăng ca bị CHẶN CỨNG, không có nút xin
                  vượt, không có quyền đặc biệt. KHÔNG có trần theo NĂM — chủ đã bỏ. */}
              <ParamField
                label="Trần giờ tăng ca / tháng"
                hint="Số giờ tối đa MỘT người được làm thêm trong MỘT tháng (Điều 107: 40 giờ). Hết trần là KHÔNG tạo được phiếu nữa — không có đường vượt. Để 0 = TẮT TRẦN. Phiếu đang chờ duyệt cũng chiếm chỗ."
                suffix="giờ"
                step={0.5}
                min={0}
                max={744}
                readOnly={readOnly}
                value={toGio(p.ot_max_minutes_per_month)}
                onChange={(v) =>
                  setP("ot_max_minutes_per_month", Math.round(v * 60))
                }
              />
              <ParamField
                label="Trần giờ một phiếu tăng ca"
                hint="Độ dài tối đa của MỘT phiếu (Điều 107.1: 12 giờ)."
                warn={
                  p.ot_max_minutes_per_day <= 0
                    ? "Phải lớn hơn 0 — ô này KHÔNG có nghĩa “tắt”, để 0 là không lưu được."
                    : null
                }
                suffix="giờ"
                step={0.5}
                min={0.5}
                max={48}
                readOnly={readOnly}
                value={toGio(p.ot_max_minutes_per_day)}
                onChange={(v) =>
                  setP("ot_max_minutes_per_day", Math.round(v * 60))
                }
              />
              {OT_FIELDS.map((f) => (
                <ParamField
                  key={f.key}
                  label={f.label}
                  hint={f.hint}
                  warn={
                    p[f.key] < f.floor
                      ? `Thấp hơn mức tối thiểu Điều 98 BLLĐ (${f.floor * 100}%) — vẫn lưu được, nhưng nên rà lại.`
                      : null
                  }
                  suffix="%"
                  step={10}
                  min={100}
                  max={500}
                  readOnly={readOnly}
                  value={toPct(p[f.key])}
                  onChange={(v) => setP(f.key, v / 100)}
                />
              ))}
              {/* SUẤT CƠM TĂNG CA (12/08/2026). Hai ô đi liền nhau vì chúng chỉ có nghĩa cùng
                  nhau: mức = 0 là tắt hẳn, lúc đó ngưỡng vô nghĩa. Nói rõ luật NGÀY NGHỈ ngay
                  trong `hint` — nếu không HCNS khai 3 giờ rồi tưởng chủ nhật cũng phải đủ 3 giờ. */}
              <ParamField
                label="Tiền một suất cơm tăng ca"
                hint="Để 0 là TẮT hẳn khoản này. Khoản cơm tăng ca ĐỘC LẬP với cơm ca — một ngày có thể ăn cả hai. Miễn thuế TNCN như cơm ca."
                suffix="đ/suất"
                step={5000}
                min={0}
                readOnly={readOnly}
                value={p.com_tang_ca_muc}
                onChange={(v) => setP("com_tang_ca_muc", v)}
              />
              <ParamField
                label="Tăng ca bao nhiêu phút thì được một suất cơm"
                hint="CHỈ áp cho NGÀY LÀM VIỆC. Ngày nghỉ theo Lịch chung — gồm cả ngày lễ và ngày 'Nghỉ 1×' — thì cứ có tăng ca là có suất, dù chỉ 1 tiếng. Mặc định 180 phút = 3 giờ."
                suffix="phút"
                step={30}
                min={0}
                max={1440}
                readOnly={readOnly}
                value={p.com_tang_ca_nguong_phut}
                onChange={(v) => setP("com_tang_ca_nguong_phut", Math.round(v))}
              />
              <ParamField
                label="Phụ cấp làm ban đêm"
                hint="Cộng thêm cho giờ làm 22h–06h (≥30% theo luật). Giờ đêm TRONG ca theo lịch dùng hệ số riêng khai trên form Khai ca."
                suffix="%"
                step={5}
                min={0}
                max={200}
                readOnly={readOnly}
                value={toPct(p.night_pct)}
                onChange={(v) => setP("night_pct", v / 100)}
              />
              <ParamField
                label="Phụ cấp tăng ca đêm"
                hint="Cộng THÊM cho giờ TĂNG CA rơi 22h–06h (Điều 98.3, mặc định +20%). Vd tăng ca đêm ngày thường = 150% + 30% + 20% = 200%."
                suffix="%"
                step={5}
                min={0}
                max={200}
                readOnly={readOnly}
                value={toPct(p.ot_night_extra_pct)}
                onChange={(v) => setP("ot_night_extra_pct", v / 100)}
              />
            </div>
          </section>
        </div>
      </div>

      <DeptChips
        depts={depts}
        deptId={deptId}
        counts={empCounts}
        alert={false}
        disabled={busy}
        onPick={onPickDept}
      />

      <div className="cl-card">
        <h3 className="cl-card__title">Cơ chế lương — {deptName}</h3>
        <p className="cl-card__desc">
          Bật thành phần nào thì bộ phận này được tính thành phần đó. Công ty
          không đặt mức chung — khoản nào bật mà chưa khai mức tiền thì tính 0
          đ.
        </p>
        <div className="cl-card__body">
          <div className="cl-override-note">
            <Info size={14} />
            <span>
              <b>Chuyên cần</b>: tổ chỉ bật/tắt — mức tiền khai ở{" "}
              <b>hồ sơ từng nhân viên</b>, chưa khai thì 0 đ.
            </span>
          </div>
          {loading ? (
            <div className="cl-comp">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                <div className="cl-comp__row" key={`sk-${i}`}>
                  <span className="rc-skel" style={{ width: "36px" }} />
                  <span className="rc-skel" style={{ width: "60%" }} />
                  <span className="rc-skel" style={{ width: "80%" }} />
                  <span className="rc-skel" style={{ width: "40%" }} />
                  <span className="rc-skel" style={{ width: "60%" }} />
                </div>
              ))}
            </div>
          ) : (
            <div className="cl-comp">
              {COMPONENT_ROWS.map((def) => {
                const c = comps.find((x) => x.component_key === def.key);
                if (!c) return null;
                const off = !c.is_enabled;
                // C6: KHÔNG còn mức mặc định công ty để rơi xuống — bật mà bỏ trống là 0 đ.
                const blankZero =
                  def.zeroWhenBlank && c.is_enabled && c.value == null;
                return (
                  <div
                    className={`cl-comp__row${off ? " is-off" : ""}`}
                    key={def.key}
                  >
                    <span>
                      <Switch
                        on={c.is_enabled}
                        // Tổ Giao hàng KHÔNG bật được Lương khoán (chủ chốt 16/09/2026): hai cờ
                        // là hai nguồn tiền đem so với bù lỗ, bật cả hai thì máy cộng chung một
                        // vế. Backend cũng chặn — chỗ này chỉ để người khai hiểu ngay vì sao.
                        disabled={
                          readOnly
                          || busy
                          || (def.key === "luong_khoan" && laGiaoHang && !c.is_enabled)
                        }
                        label={def.name}
                        onChange={(v) => patchComp(def.key, { is_enabled: v })}
                      />
                    </span>
                    <span>
                      <span className="cl-comp__name">{def.name}</span>
                      <span className="cl-comp__desc">
                        {def.desc}
                        {def.key === "luong_khoan" && laGiaoHang && (
                          <>
                            {" "}
                            <b>Tổ này có cờ Bộ phận Giao hàng nên không bật được.</b> Tài xế /
                            phụ xe đã ăn khoán km theo chuyến giao; bật thêm khoán sản lượng là
                            hai khoản cộng chung MỘT vế khi đem so với lương bù lỗ — ai gán nhầm
                            một phiếu sản lượng cho tài xế là tháng đó họ mất tiền tăng ca. Muốn
                            tổ này ăn sản lượng thì bỏ cờ Giao hàng ở màn Phòng ban trước.
                          </>
                        )}
                        {def.key === "tang_ca" && laGiaoHang && (
                          <>
                            {" "}
                            <b>Tổ Giao hàng: tài xế / phụ xe CÓ tiền giờ tăng ca</b> (hệ số bình
                            thường) — tiền đó nằm trong vế thời gian (lương bù lỗ theo công + tăng
                            ca) đem so với khoán km, tháng nào lấy km thì không trả. Tắt công tắc
                            này là họ mất luôn tiền tăng ca, cơm tăng ca và phần thêm ngày Chủ
                            nhật / lễ.
                          </>
                        )}
                        {def.key === "tang_ca" && khoanOn && !laGiaoHang && (
                          <>
                            {" "}
                            <b>Tổ này ăn khoán sản lượng: KHÔNG có tiền tăng ca</b> (làm thêm giờ
                            đã trả qua tiền khoán) — công tắc này còn quyết cơm tăng ca và phần
                            thêm khi làm nguyên ngày Chủ nhật / lễ.
                          </>
                        )}
                      </span>
                    </span>
                    <span>
                      {def.kind ? (
                        <NumInput
                          value={c.value}
                          disabled={readOnly || off || busy}
                          suffix="đ"
                          step={100000}
                          min={0}
                          placeholder="0"
                          onChange={(v) => patchComp(def.key, { value: v })}
                        />
                      ) : null}
                    </span>
                    <span className="cl-comp__unit">{def.unit}</span>
                    <span className="cl-comp__src">
                      {blankZero && (
                        <span className="badge-sem badge-sem--amber">
                          Chưa khai mức = 0 đ
                        </span>
                      )}
                      {!c.company_enabled && (
                        <span className="badge-sem badge-sem--muted">
                          Công ty đang tắt
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* CHỈ TIÊU NGÀY (16/09/2026) — chỗ khai báo, CHƯA nối vào tính lương. Chỉ tổ đang ăn khoán
          sản lượng mới có; gạt bật khoán mà chưa Lưu thì nhắc Lưu trước (backend đọc trạng thái đã lưu). */}
      {khoanOn && deptId != null && (khoanDaLuu ? (
        <>
          <ChiTieuNgayEditor
            token={token}
            departmentId={deptId}
            deptName={deptName}
            readOnly={readOnly}
          />
          {/* TỔ TRƯỞNG ăn thưởng / ăn chia (19/09/2026) — cùng luật với Chỉ tiêu ngày: chỗ khai,
              chưa nối lương; chỉ tổ ăn sản lượng mới có. */}
          <ToTruongEditor
            token={token}
            departmentId={deptId}
            deptName={deptName}
            headName={dept?.head_name}
            headTitle={dept?.head_title}
            soNguoi={dept?.employee_count ?? 0}
            readOnly={readOnly}
          />
        </>
      ) : (
        <div className="banner banner--info">
          Bấm <b>Lưu thay đổi</b> để bật Lương khoán / sản lượng cho {deptName} trước, rồi khai{" "}
          <b>chỉ tiêu ngày</b> và <b>chế độ tổ trưởng</b> của tổ ở ngay khối này.
        </div>
      ))}

      {/* % chia tiền chuyến cho kíp xe — dữ liệu CỦA PHÒNG (`departments.pct_*`), nên ở lại màn
          theo bộ phận và chỉ hiện khi phòng bật cờ Giao hàng. Bảng GIÁ (Mức khoán km) là cấu hình
          chung, đã dời sang sub-tab "Khoán km giao hàng" (14/09/2026). */}
      {laGiaoHang && deptId != null && (
        <KhoanKmEditor
          token={token}
          departmentId={deptId}
          deptName={deptName}
          readOnly={readOnly}
        />
      )}
    </>
  );
}

/** 5 hệ số làm thêm / làm nguyên công — nhập & hiện bằng %, lưu DB vẫn là 1.5 / 2 / 3. */
