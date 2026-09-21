import type { KhoanCongDoanValue, Row } from "../types";
import { FormulaField } from "./FormulaField";
import { RefSearchField } from "./RefFields";
import { ViecPhatSinhField } from "./ViecPhatSinh";

export function KhoanCongDoanField({ value, donViOptions, onChange }: {
  value: KhoanCongDoanValue | null;
  donViOptions: Row[];
  onChange: (value: KhoanCongDoanValue) => void;
}) {
  const v = value ?? {};
  const set = (patch: Partial<KhoanCongDoanValue>) => onChange({ ...v, ...patch });

  return (
    <div className="rc-khoan">
      <section className="rc-card-section rc-khoan__section">
        <div className="rc-card-section__title">Đơn giá</div>
        <div className="rc-grid rc-khoan__price-grid">
          <label className="rc-field">
            <span className="rc-field__label">Đơn vị tính khoán *</span>
            <RefSearchField
              value={v.unit || null}
              options={donViOptions}
              placeholder="Gõ để tìm đơn vị…"
              byMa
              onChange={(unit) => set({ unit: unit == null ? "" : String(unit) })}
            />
          </label>
          <label className="rc-field">
            <span className="rc-field__label">Đơn giá *</span>
            <div className="rc-input-wrapper">
              <input
                className="rc-input rc-input--num"
                aria-label="Đơn giá khoán"
                type="number"
                min={0}
                step="any"
                inputMode="decimal"
                value={v.unit_price == null ? "" : String(v.unit_price)}
                onChange={(e) => set({ unit_price: e.target.value === "" ? null : Number(e.target.value) })}
              />
              <span className="rc-input-suffix">đ</span>
            </div>
          </label>
        </div>
      </section>

      <section className="rc-card-section rc-khoan__section">
        <div className="rc-card-section__title">Công thức khoán</div>
        <p className="rc-khoan__note">Đang lưu cấu hình, chưa áp dụng tính tự động.</p>
        <FormulaField
          value={v.cong_thuc_khoan ?? ""}
          onChange={(cong_thuc_khoan) => set({ cong_thuc_khoan })}
          configPrefix="/api/cong-doan"
          loaiO="quy_doi"
          id="formula-cong-thuc-khoan"
          nhanO="Công thức khoán"
          goY="Bỏ trống nếu chưa khai cách tính lượng khoán."
          recordId={null}
          truocGiaTri={null}
          truocSuaLuc={null}
        />
      </section>

      <section className="rc-card-section rc-khoan__section">
        <div className="rc-card-section__title">Việc phát sinh</div>
        <ViecPhatSinhField
          value={v.viec_phat_sinh ?? []}
          donViOptions={donViOptions}
          onChange={(viec_phat_sinh) => set({ viec_phat_sinh })}
        />
      </section>
    </div>
  );
}
