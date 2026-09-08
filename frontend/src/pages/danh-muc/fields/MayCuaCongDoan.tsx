// MÁY chạy được công đoạn này, mỗi dòng mang cách đo GIỜ và cách tính GIÁ của riêng cặp đó.
//
// Vì sao là bảng ở đây chứ không phải cột trên máy (06/09/2026): cùng một máy chạy hai công đoạn
// thì đo khác nhau — In khổ 79×109 và In khổ 11×11 không thể chung một công thức. Cùng lẽ đó,
// đơn giá cũng theo máy: máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có giá khác nhau.
//
// Hàng tick "Máy làm được công đoạn này" (nhóm máy) nay chỉ là BỘ LỌC cho bảng này.
import { useMemo, useState } from "react";

import { Select, type SelectOption } from "../../../components/Select";
import { TrashIcon } from "../icons";
import type { MayCongDoanRow, Row } from "../types";
import { FormulaField } from "./FormulaField";
import { FormulaPopover } from "./FormulaPopover";

export function MayCuaCongDoanField({ value, options, nhomChoPhep, nhomCongDoan, onChange }: {
  value: MayCongDoanRow[]; options: Row[]; nhomChoPhep: string[];
  nhomCongDoan: string; onChange: (v: MayCongDoanRow[]) => void;
}) {
  const chon = Array.isArray(value) ? value : [];
  // Nhóm chưa tick ⇒ bày MỌI máy: "chưa khai = không ràng buộc", cùng luật với nơi gán máy ở bước.
  const duocChon = useMemo(
    () => (nhomChoPhep.length === 0
      ? options
      : options.filter((o) => nhomChoPhep.includes(String(o.loai_may)))),
    [options, nhomChoPhep],
  );
  const theoId = useMemo(() => new Map(options.map((o) => [Number(o.id), o])), [options]);
  const daChon = new Set(chon.map((r) => r.may_id));
  // Ô "＋ Chọn máy": nhãn CHỈ tên máy. Danh sách ~40 máy mà mã đứng trước thì cả cột chỉ thấy
  // "BE-01 / BE-02 / BOI-01…", mắt phải đọc qua tiền tố mới tới tên. Mã chuyển sang `search` —
  // vẫn gõ "be-07" ra được, chỉ là không chiếm chỗ.
  const mayOpts = useMemo<SelectOption<string>[]>(
    () => duocChon
      .filter((o) => !daChon.has(Number(o.id)))
      .map((o) => ({ value: String(o.id), label: String(o.ten), search: String(o.ma ?? "") })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [duocChon, chon],
  );
  // Panel đang mở khoá theo CẶP (máy, ô) chứ không theo dòng: bảng có hai ô công thức mỗi dòng,
  // khoá theo dòng thì bấm ô "Cách tính giá" của dòng 3 vẫn ra panel dòng đang mở, người khai
  // tưởng mình đang sửa dòng 3 mà thật ra đang sửa dòng 1.
  //
  // `neo` = chính cái nút vừa bấm, để panel NỔI dán vào đó (07/09/2026 — xem `FormulaPopover`).
  //
  // `banDau` = công thức lúc MỞ panel, để nút ✕ trả ô về đúng chỗ cũ. Ô công thức ghi thẳng vào form
  // theo từng nhịp gõ nên không có nó thì "bỏ sửa" chỉ còn cách đóng drawer rồi mở lại.
  const [mo, setMo] = useState<
    { may: number; o: "gio" | "gia"; neo: HTMLElement; banDau: string | null } | null>(null);
  const bat = (may: number, o: "gio" | "gia", neo: HTMLElement, banDau: string | null) =>
    setMo(mo && mo.may === may && mo.o === o ? null : { may, o, neo, banDau });
  const patch = (i: number, p: Partial<MayCongDoanRow>) =>
    onChange(chon.map((r, j) => (j === i ? { ...r, ...p } : r)));
  // Chỉ công đoạn nhóm In mới có ô giá: phiếu tính giá chỉ chọn máy ở khối In của thành phần, nên
  // công thức giá khai cho máy bế/cán sẽ không có đường nào chảy tới. Dùng ENUM nhóm công đoạn
  // (`print`) chứ KHÔNG so tên nhóm máy — tên nhóm máy là danh mục người dùng sửa được.
  const coOGia = nhomCongDoan === "print";
  // Panel nằm NGOÀI vòng lặp bảng nên phải tra lại dòng theo `may_id`. Máy vừa bị xoá khỏi bảng
  // ⇒ `-1` ⇒ không vẽ panel (ô neo cũng đã rời DOM, `FormulaPopover` tự đóng).
  const iMo = mo ? chon.findIndex((r) => r.may_id === mo.may) : -1;
  // BỎ SỬA: dùng chung cho nút ✕ trên hàng tên ô và cho phím Esc.
  const huy = () => {
    if (!mo || iMo < 0) return;
    patch(iMo, mo.o === "gio" ? { cong_thuc_gio: mo.banDau } : { cong_thuc_gia: mo.banDau });
    setMo(null);
  };

  return <div className="rc-bands rc-bands--dinh-muc">
    <div className="rc-dinh-muc-wrapper">
      <table className="rc-dinh-muc-table">
        <thead><tr>
          <th className="rc-col--left">Máy</th>
          <th className="rc-col--left">Cách đo giờ chạy</th>
          {coOGia && <th className="rc-col--left">Cách tính giá</th>}
          <th className="rc-col--center" style={{ width: 36 }} />
        </tr></thead>
        <tbody>
          {chon.length === 0 && <tr><td colSpan={coOGia ? 4 : 3} className="rc-bands__empty">
            {duocChon.length === 0
              ? "Chưa có máy nào thuộc nhóm đã tick ở trên."
              : "Chưa chọn máy nào cho công đoạn này."}
          </td></tr>}
          {chon.map((r, i) => {
            const may = theoId.get(r.may_id);
            const moGio = mo?.may === r.may_id && mo.o === "gio";
            const moGia = mo?.may === r.may_id && mo.o === "gia";
            return (
              <tr key={r.may_id}>
                <td className="rc-col--left rc-dinh-muc-name">
                  {/* Bấm tên mở ô GIỜ: ô đó nhóm công đoạn nào cũng có, còn ô giá thì không. */}
                  <button type="button" className={`rc-dm-vt__pill ${moGio ? "is-open" : ""}`}
                    onClick={(e) => bat(r.may_id, "gio", e.currentTarget, r.cong_thuc_gio ?? null)}>
                    {may ? `${String(may.ma)} · ${String(may.ten)}` : `#${r.may_id}`}
                  </button>
                </td>
                {/* Ô công thức là NÚT: bấm thẳng vào con số muốn sửa là mở đúng ô đó của đúng dòng đó. */}
                <td className="rc-col--left rc-dinh-muc-unit">
                  <button type="button" title="Sửa cách đo giờ chạy của máy này"
                    className={`rc-ct-cell ${moGio ? "is-open" : ""} ${r.cong_thuc_gio ? "" : "is-empty"}`}
                    onClick={(e) => bat(r.may_id, "gio", e.currentTarget, r.cong_thuc_gio ?? null)}>{r.cong_thuc_gio || "—"}</button>
                </td>
                {coOGia && <td className="rc-col--left rc-dinh-muc-unit">
                  <button type="button" title="Sửa cách tính giá của máy này"
                    className={`rc-ct-cell ${moGia ? "is-open" : ""} ${r.cong_thuc_gia ? "" : "is-empty"}`}
                    onClick={(e) => bat(r.may_id, "gia", e.currentTarget, r.cong_thuc_gia ?? null)}>{r.cong_thuc_gia || "—"}</button>
                </td>}
                <td className="rc-col--center">
                  <button type="button" className="rc-bands__del"
                    onClick={() => onChange(chon.filter((_, j) => j !== i))}><TrashIcon /></button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {mo && iMo >= 0 && <FormulaPopover neo={mo.neo} onClose={() => setMo(null)} onHuy={huy}
      nhan={mo.o === "gio" ? "Công thức giờ chạy" : "Công thức giá"}>
      {/* `id` phải DUY NHẤT: drawer còn những ô công thức khác, trùng id là hai ô dính nhau. */}
      {mo.o === "gio" ? <FormulaField
        id={`ct-gio-${mo.may}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
        nhanO="Công thức giờ chạy" onDong={huy}
        goY="Ra LƯỢNG theo đơn vị tốc độ của máy. Bỏ trống = hệ tự quy đổi. vd máy 5 màu chạy 2 lượt: sl_vao * so_mau / 5. ĐỪNG nhân so_luot_chay — hệ đã tự nhân."
        value={chon[iMo].cong_thuc_gio ?? ""}
        onChange={(v) => patch(iMo, { cong_thuc_gio: v })} /> : <FormulaField
        id={`ct-gia-${mo.may}`} configPrefix="/api/cong-doan" loaiO="cong_doan"
        nhanO="Công thức giá" onDong={huy}
        goY="Ghi đè công thức giá của công đoạn khi phiếu tính giá chọn đúng máy này. Bỏ trống = dùng công thức chung."
        value={chon[iMo].cong_thuc_gia ?? ""}
        onChange={(v) => patch(iMo, { cong_thuc_gia: v })} />}
    </FormulaPopover>}
    <div className="rc-dinh-muc-add">
      <Select
        options={mayOpts}
        value=""
        placeholder="＋ Chọn máy cho công đoạn"
        ariaLabel="Chọn máy cho công đoạn"
        searchable
        searchPlaceholder="Gõ tên hoặc mã máy…"
        portal
        className="rc-dinh-muc-add__select"
        onChange={(v) => {
          const id = Number(v);
          if (id) onChange([...chon, { may_id: id, cong_thuc_gio: null, cong_thuc_gia: null }]);
        }}
      />
    </div>
  </div>;
}
