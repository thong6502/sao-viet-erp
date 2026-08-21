// LỊCH BẢO TRÌ ĐỊNH KỲ — GÓI (có chu kỳ + hạn) → VIỆC CON (nội dung phải làm).
//
// Lưu LỒNG trong `fields_theo_loai.lich_bao_tri` (jsonKey) — không cột mới, không migration.
// Chỉ GÓI mới có chu kỳ: một lần dừng máy 4 tiếng mà mỗi việc con một hạn riêng thì bảng việc của
// thợ cả đỏ rực 5 dòng cùng nội dung, nhìn vài hôm là hết tin.
//
// KHÔNG dùng `RowEditor`: đây là danh sách THẺ, không phải bảng — xem ghi chú đầu `RowEditor.tsx`.
import { useEffect, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { kyThuatMay } from "../../../api/kyThuatMay";
import { TrashIcon } from "../icons";
import type { HangMucConRow, LichBaoTriRow } from "../types";

const DON_VI_CHU_KY = [
  { v: "ngay", n: "ngày" }, { v: "tuan", n: "tuần" },
  { v: "thang", n: "tháng" }, { v: "nam", n: "năm" },
];

/** `id` ỔN ĐỊNH cho mỗi hạng mục — phiếu bảo trì neo vào đây. Neo theo TÊN thì đổi tên là mất
 *  sạch mốc; neo theo THỨ TỰ thì xoá một dòng là mọi phiếu trỏ nhầm hạng mục, im lặng. */
function _hangMucId(): string {
  return `hm-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

export function LichBaoTriField({
  value,
  onChange,
  mayId = null,
}: { value: LichBaoTriRow[]; onChange: (v: LichBaoTriRow[]) => void; mayId?: number | null }) {
  const { token } = useAuth();
  const rows = value ?? [];
  // Hạn kế tiếp từng gói — CHỈ ĐỌC, tính ở backend từ phiếu bảo trì gần nhất (hoặc "Bắt đầu từ"
  // khi chưa có phiếu nào). Máy chưa lưu (`mayId` null) thì chưa có gì để hỏi.
  const [han, setHan] = useState<Record<string, { han: string | null; nguon: string }>>({});
  useEffect(() => {
    if (!token || !mayId) return;
    let huy = false;
    kyThuatMay.hanCuaMay(token, mayId)
      .then((items) => {
        if (huy) return;
        const m: Record<string, { han: string | null; nguon: string }> = {};
        for (const it of items) if (it.goi_id) m[it.goi_id] = { han: it.han, nguon: it.nguon };
        setHan(m);
      })
      // Nuốt lỗi có chủ đích: dòng "Kỳ tới" là thông tin PHỤ, thiếu quyền đọc module Kỹ thuật máy
      // thì vẫn phải khai được lịch bảo trì như thường.
      .catch(() => setHan({}));
    return () => { huy = true; };
  }, [token, mayId]);
  const setRow = (i: number, patch: Partial<LichBaoTriRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => onChange([...rows, { id: _hangMucId(), viec: "", so: undefined, don_vi: "thang", hang_muc: [] }]);
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));

  const setViecCon = (i: number, list: HangMucConRow[]) => setRow(i, { hang_muc: list });

  return (
    <div className="rc-goi-list">
      {rows.length === 0 && (
        <p className="rc-goi__empty">
          Chưa có gói bảo trì nào. Một gói = một lần dừng máy theo chu kỳ (vd “Bảo trì 3 tháng”),
          bên trong liệt kê những việc phải làm trong lần đó.
        </p>
      )}
      {rows.map((r, i) => {
        const viecCon = r.hang_muc ?? [];
        return (
          <section className="rc-goi" key={r.id ?? i}>
            <div className="rc-goi__head">
              <input
                className="rc-input rc-goi__ten"
                value={r.viec ?? ""}
                placeholder="Tên gói — vd: Bảo trì 3 tháng"
                onChange={(e) => setRow(i, { viec: e.target.value })}
              />
              <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xoá gói bảo trì">
                <TrashIcon />
              </button>
            </div>

            <div className="rc-goi__so">
              <label className="rc-goi__o">
                <span>Mỗi</span>
                <input
                  className="rc-input rc-input--num"
                  type="number" step="any" min={1} inputMode="numeric"
                  value={r.so === undefined || r.so === null ? "" : String(r.so)}
                  onChange={(e) => setRow(i, { so: e.target.value === "" ? undefined : Number(e.target.value) })}
                />
                <select
                  className="rc-input"
                  value={r.don_vi ?? "thang"}
                  onChange={(e) => setRow(i, { don_vi: e.target.value })}
                >
                  {DON_VI_CHU_KY.map((d) => <option key={d.v} value={d.v}>{d.n}</option>)}
                </select>
              </label>
              {/* Mốc kỳ ĐẦU. Không có nó thì màn Phiếu bảo trì không biết gói này tới hạn chưa —
                  đành coi là tới hạn ngay hôm nay, nên bấm "Sinh phiếu từ lịch" là ra một loạt
                  phiếu cùng ngày. Khai một lần ở đây là hết cảnh đó. */}
              <label className="rc-goi__o rc-goi__o--ngay">
                <span>Bắt đầu từ</span>
                <input
                  className="rc-input"
                  type="date"
                  value={r.ngay_bat_dau ?? ""}
                  onChange={(e) => setRow(i, { ngay_bat_dau: e.target.value || undefined })}
                />
              </label>
              {/* "Lần cuối làm" + "Dừng máy (phút)" đã BỎ khỏi form 12/08/2026 (chủ xưởng chốt).
                  Giá trị cũ trong JSON vẫn được giữ nguyên khi lưu (xem transformSubmit) — chỉ là
                  không khai ở đây nữa. Mốc các kỳ SAU đi ra từ PHIẾU bảo trì, đúng một nguồn;
                  "Bắt đầu từ" ở trên chỉ mồi cho kỳ 1, không phải ô đó sống lại. */}
            </div>
            {(r.so ?? 0) > 0 && !r.ngay_bat_dau && !han[r.id ?? ""]?.han && (
              <p className="rc-goi__nhac">
                Chưa có ngày bắt đầu — gói này sẽ bị coi là tới hạn ngay khi sinh phiếu.
              </p>
            )}
            {/* Kỳ tới: CHỈ ĐỌC. Nó đi ra từ phiếu bảo trì gần nhất nên khai tay ở đây là đẻ ra hai
                nguồn sự thật — mốc thật nằm ở phiếu, không nằm trong ô. */}
            {han[r.id ?? ""]?.han && (
              <p className="rc-goi__ky">
                Kỳ tới: <strong>{new Date(`${han[r.id!]!.han}T00:00:00`).toLocaleDateString("vi-VN")}</strong>
                <span className="rc-goi__ky-nguon">
                  {han[r.id!]!.nguon === "phieu"
                    ? "tính từ phiếu bảo trì gần nhất"
                    : han[r.id!]!.nguon === "ngay_bat_dau"
                      ? "kỳ đầu, theo ngày bắt đầu"
                      : "chưa có mốc — coi như tới hạn"}
                </span>
              </p>
            )}

            <div className="rc-goi__viec">
              <div className="rc-goi__viec-head">
                Việc phải làm trong gói
                {/* Đếm việc ĐÃ CÓ TÊN, không đếm dòng trống vừa bấm thêm — "4 việc" trong khi cả
                    4 ô còn trắng là con số nói dối ngay trước mắt người đang gõ. */}
                <span className="rc-goi__dem">
                  {viecCon.filter((h) => (h.ten ?? "").trim()).length || "chưa khai"}
                  {viecCon.some((h) => (h.ten ?? "").trim()) ? " việc" : ""}
                </span>
              </div>
              <ol className="rc-goi__ol">
                {viecCon.map((h, j) => (
                  <li key={h.id ?? j}>
                    <input
                      className="rc-input"
                      value={h.ten ?? ""}
                      placeholder="vd: Thay set dao bế (4 dao)"
                      onChange={(e) => setViecCon(i, viecCon.map((x, k) => (k === j ? { ...x, ten: e.target.value } : x)))}
                    />
                    <button
                      type="button" className="rc-bands__del" title="Xoá việc"
                      onClick={() => setViecCon(i, viecCon.filter((_, k) => k !== j))}
                    >
                      <TrashIcon />
                    </button>
                  </li>
                ))}
              </ol>
              <button
                type="button" className="rc-bands__add"
                onClick={() => setViecCon(i, [...viecCon, { id: _hangMucId(), ten: "" }])}
              >
                ＋ Thêm việc
              </button>
            </div>
          </section>
        );
      })}
      <button type="button" className="rc-bands__add rc-goi__add" onClick={add}>＋ Thêm gói bảo trì</button>
    </div>
  );
}
