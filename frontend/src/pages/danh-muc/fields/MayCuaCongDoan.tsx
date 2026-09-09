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
import { nhanDonViTocDo } from "./DonViTocDo";
import { FormulaField } from "./FormulaField";
import { FormulaPopover } from "./FormulaPopover";

// Số NĂNG LỰC kế thừa từ danh mục Thiết bị & Máy móc: trống / 0 / rác đều hiện TRẮNG chứ không
// phải "—". Trong chính bảng này "—" đang mang nghĩa "chưa khai, bấm vào khai" ở hai ô công thức;
// rải nó sang ô chỉ-đọc là mời một cú bấm không có thật.
function so(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n.toLocaleString("vi-VN") : "";
}

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
      <table className={`rc-dinh-muc-table rc-dinh-muc-table--may ${coOGia ? "rc-dinh-muc-table--may-gia" : ""}`}>
        <thead>
          <tr className="rc-dinh-muc-table__group-row">
            <th rowSpan={2} className="rc-col--left">Máy</th>
            {/* Ba mốc + đơn vị đọc thành một DẢI, đúng ngữ pháp "Năng suất khoán" của bảng đầu việc
                ngay phía trên: số xếp cột canh phải thì so DỌC giữa các máy được ngay, nối thành
                một dòng thì mắt phải đếm vị trí ở từng dòng mới biết số nào là số nào. */}
            <th colSpan={4} className="rc-col--group rc-group--may"
              title="Khai ở danh mục Thiết bị & Máy móc. Trung bình là tốc độ hệ dùng để tính thời lượng bước; tối thiểu/tối đa chỉ dựng khoảng nhanh–chậm khi xếp lịch.">Tốc độ chạy</th>
            {/* Canh máy luôn tính bằng phút ⇒ đơn vị lên đầu cột, ô chỉ còn con số trần. */}
            <th rowSpan={2} className="rc-col--num rc-group--may"
              title="Thời gian canh máy mặc định — Xếp lịch cộng thẳng vào thời gian chiếm máy. Khai ở danh mục Thiết bị & Máy móc.">Canh máy (phút)</th>
            <th rowSpan={2} className="rc-col--left">Cách đo giờ chạy</th>
            {coOGia && <th rowSpan={2} className="rc-col--left">Cách tính giá</th>}
            <th rowSpan={2} className="rc-col--center" style={{ width: 36 }} />
          </tr>
          <tr className="rc-dinh-muc-table__sub-row">
            {/* Thứ tự tối thiểu → trung bình → tối đa: đọc thành một dải tăng dần, y bảng trên. */}
            <th className="rc-col--num">Tối thiểu</th>
            <th className="rc-col--num">Trung bình</th>
            <th className="rc-col--num">Tối đa</th>
            <th className="rc-col--unit rc-col--unit-hep">Đơn vị</th>
          </tr>
        </thead>
        <tbody>
          {chon.length === 0 && <tr><td colSpan={coOGia ? 9 : 8} className="rc-bands__empty">
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
                {/* NĂNG LỰC MÁY — chỉ đọc, kế thừa từ danh mục Thiết bị & Máy móc. Bày ở đây vì
                    người khai "Cách đo giờ chạy" cần biết máy chạy nhanh cỡ nào theo đơn vị nào
                    thì mới viết nổi công thức; trước 08/09/2026 phải mở sang màn Máy mà tra. */}
                <td className="rc-col--num rc-may-nl">{so(may?.toc_do_min)}</td>
                <td className="rc-col--num rc-may-nl rc-may-nl--tb">{so(may?.toc_do)}</td>
                <td className="rc-col--num rc-may-nl">{so(may?.toc_do_max)}</td>
                <td className="rc-col--unit rc-col--unit-hep rc-may-nl">{may ? nhanDonViTocDo(may) : ""}</td>
                {/* Đọc THẲNG `makeready_time_default` chứ không cộng lại `chuan_bi_khoan`: form Máy
                    đã ghi tổng các khoản xuống đúng cột này lúc lưu (`CFG_MAY.transformSubmit`), và
                    đây mới là cột Xếp lịch cộng vào thời gian chiếm máy. Tự cộng lại là bày một con
                    số mà hệ không dùng. */}
                <td className="rc-col--num rc-may-nl">{so(may?.makeready_time_default)}</td>
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
    {/* Nói thẳng bốn cột kia sửa ở đâu — không có dòng này thì người khai bấm mãi vào con số. */}
    {chon.length > 0 && <div className="rc-dinh-muc-note">
      Tốc độ và canh máy khai ở danh mục Thiết bị &amp; Máy móc — ở đây chỉ đọc.
    </div>}
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
