// Tab con Cơ chế lương theo bộ phận (tách từ pages/CauHinhLuongTab.tsx).
import { useMemo } from "react";
import { Info } from "lucide-react";
import type {
  Department,
  DeptComponent,
  PayrollParams,
  SalaryComponentKey,
} from "../../../../../api/client";
import { KhoanRatesEditor } from "../../../../../components/KhoanRatesEditor";
import { KhoanKmEditor } from "../components/KhoanKmEditor";
import { DeptChips } from "../components/DeptChips";
import { NumInput, ParamField, Switch } from "../components/fields";
import { LeaderBonusEditor } from "../components/LeaderBonusEditor";
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
  navigate,
}: {
  token: string;
  p: PayrollParams;
  setP: (key: keyof PayrollParams, value: number) => void;
  depts: Department[];
  deptId: number | null;
  onPickDept: (id: number) => void;
  comps: DeptComponent[];
  setComps: (f: (c: DeptComponent[]) => DeptComponent[]) => void;
  loading: boolean;
  readOnly: boolean;
  busy: boolean;
  navigate?: (id: string) => void;
}) {
  const deptName = depts.find((d) => d.id === deptId)?.name ?? "";
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
        // Chủ đảo lại: "Tổ khoán VẪN CÓ tăng ca". Hai công tắc nay độc lập, backend cũng đã gỡ.
        return c;
      }),
    );
  const khoanOn =
    comps.find((c) => c.component_key === "luong_khoan")?.is_enabled ?? false;

  // "Bật sản xuất" tính theo CÂY: chính tổ tích, HOẶC có tổ tiên tích — đúng ghi chú ở
  // `client.ts:848` ("Effective tính theo cây ở FE"). Chỉ soi mỗi cờ của chính tổ thì tổ con
  // của khối Sản xuất sẽ không được coi là sản xuất.
  const laSanXuat = useMemo(() => {
    const byId = new Map(depts.map((d) => [d.id, d]));
    let cur = deptId == null ? undefined : byId.get(deptId);
    const daQua = new Set<number>();          // chặn vòng lặp nếu cây bị khai sai
    while (cur && !daQua.has(cur.id)) {
      if (cur.la_san_xuat) return true;
      daQua.add(cur.id);
      cur = cur.parent_id == null ? undefined : byId.get(cur.parent_id);
    }
    return false;
  }, [depts, deptId]);
  const toTruongUserId = depts.find((d) => d.id === deptId)?.head_user_id ?? null;
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
                hint="Dùng để quy ra đơn giá 1 giờ tăng ca."
                suffix="h"
                step={0.5}
                min={1}
                max={24}
                readOnly={readOnly}
                value={p.standard_hours_per_day}
                onChange={(v) => setP("standard_hours_per_day", v)}
              />
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
                        disabled={readOnly || busy}
                        label={def.name}
                        onChange={(v) => patchComp(def.key, { is_enabled: v })}
                      />
                    </span>
                    <span>
                      <span className="cl-comp__name">{def.name}</span>
                      <span className="cl-comp__desc">{def.desc}</span>
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

      {khoanOn && deptId != null && (
        <div className="cl-card">
          <h3 className="cl-card__title">Đơn giá khoán — {deptName}</h3>
          {/* Mô tả nói ĐÚNG những gì khai được ở ĐÂY. Từ 17/08/2026 bảng đơn giá là danh mục
              "Công việc khoán" (Cấu hình danh mục) — panel này là một khung nhìn theo tổ của cùng
              dữ liệu, nên phải nói rõ chỗ nào làm được gì, không thì người dùng đi tìm nút Xoá và
              tab Nhật ký ngay tại đây. */}
          <p className="cl-card__desc">
            Khai công việc + đơn giá khoán của tổ này (vd “dán bìa các tông” = 170đ/tờ). Cùng dữ liệu
            với <b>Cấu hình danh mục → Công việc khoán</b>; xoá hẳn, nhật ký ai đổi giá và mục đã
            ngừng dùng thì xem ở màn đó.
          </p>
          <div className="cl-card__body">
            <KhoanRatesEditor
              token={token}
              departmentId={deptId}
              deptName={deptName}
              onMoDanhMuc={navigate ? () => navigate("cong-viec-khoan") : undefined}
            />
          </div>
        </div>
      )}

      {/* Chủ 29/07/2026: "tổ nào bật sản xuất VÀ lương khoán thì nó sẽ hiện cái form điền %". */}
      {khoanOn && laSanXuat && deptId != null && (
        <LeaderBonusEditor
          token={token}
          departmentId={deptId}
          deptName={deptName}
          hasLeader={toTruongUserId != null}
          readOnly={readOnly}
        />
      )}

      {/* Đơn giá khoán km giao hàng (chủ chốt 24/08/2026 — dời từ màn Phòng ban sang đây). Hiện
          khi tổ bật cờ Bộ phận Giao hàng. Cả cụm (bậc đơn giá + % chia kíp) ở một chỗ. */}
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
