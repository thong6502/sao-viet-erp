// DRAWER khai báo của màn danh mục — một form dựng từ `config.fields`.
//
// Lưới test: `CatalogDrawer.test.tsx` (đủ ô · autoCode · body POST đúng kiểu · PUT đúng id · tabs
// khai · `showIf` không lọt vào body). Sửa phần dựng `body` thì chạy lưới đó trước khi đi tiếp.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { useAuth } from "../../auth/useAuth";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DiscardChangesDialog } from "../../components/DiscardChangesDialog";
import { useTre } from "../../lib/useTre";
import { ApiError } from "../../api/client";
import { crud, type Row } from "../../api/rebuildCatalog";
import { Drawer } from "./components/Drawer";
import {
  BandsField, ChuanBiKhoanField, DinhMucDauViecField, DonViTocDoField, FormulaField,
  LichBaoTriField, NhomMayField, NhomMayMultiField, RefMultiField, RefSearchField,
  SelfRefMultiField,
} from "./fields";
import { goiYMaTiepTheo } from "./maGoiY";
import { NhatKyTab } from "./nhat-ky/NhatKyTab";
import type {
  BacRow, CatalogConfig, ChuanBiKhoanRow, DinhMucRow, FieldDef, LichBaoTriRow,
} from "./types";

/** Tách đuôi đơn vị khỏi nhãn: "Khổ rộng (cm)" → nhãn "Khổ rộng" + hậu tố "cm" dán trong ô. */
function parseLabelAndSuffix(label: string): { cleanLabel: string; suffix: string | null } {
  const parenMatch = label.match(/\s*\(([^)]+)\)\s*$/);
  if (parenMatch) {
    return { cleanLabel: label.replace(parenMatch[0], "").trim(), suffix: parenMatch[1] };
  }
  const percentMatch = label.match(/\s*%\s*$/);
  if (percentMatch) {
    return { cleanLabel: label.replace(percentMatch[0], "").trim(), suffix: "%" };
  }
  return { cleanLabel: label, suffix: null };
}

export function CatalogDrawer({ config, existing, onClose, onSaved }: {
  config: CatalogConfig; existing: Row | null;
  onClose: () => void; onSaved: (moi?: Row) => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {
      // Mã gợi ý điền SAU (hỏi máy chủ, xem effect bên dưới) — mở drawer ra ô mã trống một nhịp
      // còn hơn điền sẵn một mã đã có người dùng.
      ma: existing?.ma ?? "",
      ten: existing?.ten ?? ""
    };
    for (const f of config.fields) {
      if (f.type === "ref-multi" || f.type === "self-ref-multi" || f.type === "nhom_may-multi" || f.type === "bands" || f.type === "dau-viec-dinh-muc") {
        const ev = existing?.[f.key];
        init[f.key] = Array.isArray(ev) ? ev : [];
      } else if (f.jsonKey) {
        // field lồng trong cột JSON (vd fields_theo_loai.click_mau)
        const box = existing?.[f.jsonKey] as Record<string, unknown> | undefined;
        const raw = existing ? box?.[f.key] : undefined;
        // Field kiểu DANH SÁCH phải rơi về [] chứ không phải "" — đưa "" cho editor mảng là vỡ.
        init[f.key] = f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri"
          ? (Array.isArray(raw) ? raw : [])
          : (existing ? raw ?? "" : f.default ?? "");
      } else {
        init[f.key] = existing ? existing[f.key] ?? "" : f.default ?? "";
      }
    }
    if (config.deriveInitial) Object.assign(init, config.deriveInitial(existing));  // vd suy _method từ pricing_basis
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  /** MỐC "chưa sửa gì" — bản `form` lúc mở drawer. So với mốc này chứ KHÔNG so với `existing`:
   *  `form` còn có field suy ra (`deriveInitial`), field `default` khi tạo mới, và mọi giá trị
   *  `null` đã đổi thành `""` — so lệch là hộp thoại "bỏ thay đổi?" nhảy ra ở MỌI lần đóng, mà
   *  hỏi sai kiểu đó thì hai hôm sau người dùng bấm "Thoát" theo phản xạ, đúng lúc mất việc thật. */
  const mocBanDau = useRef(form);
  // Bản `form` mới nhất, để `yeuCauDong` đọc mà không phải nhận `form` làm dependency — nhận vào
  // thì mỗi phím gõ đổi identity hàm, `Drawer` gỡ/gắn lại listener Esc và set lại `overflow` của
  // body theo từng ký tự.
  const formMoiNhat = useRef(form);
  formMoiNhat.current = form;
  const [hoiBoThayDoi, setHoiBoThayDoi] = useState(false);
  /** Ô "Tổ phụ trách" đang chờ xác nhận đổi (null = không có). Chuỗi rỗng LÀ giá trị hợp lệ
   *  (chọn "— chọn —"), nên phải so `!== null`, đừng so truthy. */
  const [doiToChoXacNhan, setDoiToChoXacNhan] = useState<string | null>(null);
  const dangHoi = hoiBoThayDoi || doiToChoXacNhan !== null;

  /** Cửa DUY NHẤT để đóng drawer. `Drawer` gom cả ba đường đóng (nút ✕ · bấm ra nền · phím Esc)
   *  vào `onClose`, nên chặn ở đây là chặn đủ ba. */
  const yeuCauDong = useCallback(() => {
    // Esc lúc hộp thoại đang mở: `Drawer` và `ConfirmDialog` cùng nghe trên `document` nên cả hai
    // đều chạy. Không có cửa này thì hộp thoại đóng rồi mở lại ngay — nhìn như phím Esc chết.
    if (dangHoi) return;
    if (JSON.stringify(formMoiNhat.current) !== JSON.stringify(mocBanDau.current)) {
      setHoiBoThayDoi(true);
      return;
    }
    onClose();
  }, [dangHoi, onClose]);

  // Mã gợi ý cho bản ghi MỚI (màn nào để người dùng tự đặt mã). Hỏi xong mới điền, và chỉ điền
  // khi ô mã vẫn còn trống — người khai gõ tay trước thì tôn trọng cái họ gõ.
  useEffect(() => {
    if (isEdit || config.autoCode || !token) return;
    let huy = false;
    goiYMaTiepTheo(config.prefix, token)
      .then((ma) => {
        if (huy) return;
        setForm((p) => {
          if (String(p.ma ?? "")) return p;      // người khai gõ trước thì tôn trọng cái họ gõ
          // Mã này do MÁY điền, không phải người dùng sửa ⇒ đẩy mốc theo, không thì mở drawer ra
          // rồi đóng ngay cũng bị hỏi "bỏ thay đổi?". (Gán idempotent nên StrictMode gọi hai lần
          // vẫn ra đúng một kết quả.)
          mocBanDau.current = { ...mocBanDau.current, ma };
          return { ...p, ma };
        });
      })
      .catch(() => {});   // hỏng thì để trống, người khai tự gõ — không chặn việc tạo mới
    return () => { huy = true; };
  }, [isEdit, config.autoCode, config.prefix, token]);
  const setRef = (key: string, value: string) => {
    if (key !== "department_id" || String(form.department_id ?? "") === value) {
      set(key, value);
      return;
    }
    const dinhMuc = Array.isArray(form.dau_viec_dinh_muc) ? form.dau_viec_dinh_muc : [];
    // Đổi tổ là XOÁ SẠCH bảng định mức đã khai — phải hỏi. Hỏi bằng `ConfirmDialog` của hệ chứ
    // không `window.confirm`: hộp của trình duyệt khoá cả tab, không theo được tông màu/tiếng Việt
    // của app, và ở Chrome còn có ô "chặn hộp thoại" — tick vào là từ đó về sau đổi tổ mất định
    // mức KHÔNG một lời cảnh báo nào.
    if (dinhMuc.length > 0) { setDoiToChoXacNhan(value); return; }
    setForm((prev) => ({ ...prev, department_id: value, dau_viec_dinh_muc: [] }));
  };

  // Đổ dropdown "chọn theo tên" cho field ref/ref-multi từ danh mục nguồn.
  const [refData, setRefData] = useState<Record<string, Row[]>>({});
  // Nạp lại danh mục nguồn sau khi người dùng sửa nó NGAY TRONG drawer (vd bật/gỡ đơn vị tốc độ) —
  // `config.fields` là hằng nên effect dưới không tự chạy lại.
  const [refTick, setRefTick] = useState(0);
  const onRefChanged = useCallback(() => setRefTick((t) => t + 1), []);
  useEffect(() => {
    if (!token) return;
    // Gộp `refParams` theo prefix: nhiều field có thể cùng trỏ một danh mục (vd ĐVT và Đơn vị đóng
    // gói đều lấy `/api/don-vi`) — nạp một lần, query là hợp của các field đó.
    const theoPrefix = new Map<string, Record<string, unknown>>();
    for (const f of config.fields) {
      if (!f.refPrefix) continue;
      if (!(f.type === "ref" || f.type === "ref-multi" || f.type === "self-ref-multi" || f.type === "ref-search" || f.type === "ref-search-ma" || f.type === "dau-viec-dinh-muc" || f.type === "don_vi_toc_do" || f.type === "nhom_may" || f.type === "nhom_may-multi")) continue;
      theoPrefix.set(f.refPrefix, { ...(theoPrefix.get(f.refPrefix) ?? {}), ...(f.refParams ?? {}) });
    }
    if (theoPrefix.size === 0) return;
    let alive = true;
    Promise.all([...theoPrefix].map(([p, params]) =>
      crud(p).list(token, params).then((r) => [p, r.items] as const).catch(() => [p, [] as Row[]] as const)))
      .then((entries) => { if (alive) setRefData(Object.fromEntries(entries)); });
    return () => { alive = false; };
  }, [token, config.fields, refTick]);

  const visibleFields = useMemo(
    () => config.fields.filter((f) => !f.showIf || f.showIf(form)),
    [config.fields, form],
  );

  // Tab đang mở. Màn không chia tab khai báo thì vẫn là "info" như trước; màn có chia (Máy) thì
  // giá trị là id của tab khai. Dùng chung một state với tab "formula"/"nhatky" — hai bộ state
  // song song là sớm muộn có lúc cả hai cùng "đang mở".
  const [formulaTab, setFormulaTab] = useState<string>(config.tabsKhai?.[0]?.id ?? "info");

  const renderField = (f: FieldDef) => {
    const { cleanLabel, suffix } = parseLabelAndSuffix(f.label);
    const hint = typeof f.hint === "function" ? f.hint(form) : f.hint;
    const laDonVi = config.prefix.includes("don-vi");
    const isFullWidth = f.type === "bands" || f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri" || f.type === "ref-multi" || f.type === "self-ref-multi" || f.type === "nhom_may-multi" || f.type === "dau-viec-dinh-muc" || f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta";
    // "div" chứ không "label": khối này chứa NHIỀU input, bọc trong <label> là bấm đâu cũng nhảy
    // focus vào ô đầu tiên.
    const Tag = f.type === "formula" || f.type === "bands" || f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri" ? "div" : "label";
    return (
      <Tag className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}${isFullWidth ? " rc-field--full" : ""}`} key={f.key}>
        <span className="rc-field__label">{cleanLabel}{f.required ? " *" : ""}</span>
        {f.type === "lich_bao_tri" ? (
          <LichBaoTriField value={Array.isArray(form[f.key]) ? (form[f.key] as LichBaoTriRow[]) : []}
            mayId={isEdit && existing ? Number(existing.id) : null}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "chuan_bi_khoan" ? (
          <ChuanBiKhoanField value={Array.isArray(form[f.key]) ? (form[f.key] as ChuanBiKhoanRow[]) : []}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "bands" ? (
          <BandsField value={Array.isArray(form[f.key]) ? (form[f.key] as BacRow[]) : []}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "dau-viec-dinh-muc" ? (
          <DinhMucDauViecField value={Array.isArray(form[f.key]) ? form[f.key] as DinhMucRow[] : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            departmentId={form.department_id ? Number(form.department_id) : null}
            donViVao={String(form.don_vi_vao ?? "")}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "select" ? (
          <div className="rc-input-wrapper">
            <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
              <option value="">—</option>
              {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        ) : f.type === "nhom_may" ? (
          <NhomMayField
            value={String(form[f.key] ?? "")}
            onChange={(v) => set(f.key, v)}
            options={refData[f.refPrefix ?? ""] ?? []}
            onCatalogChanged={onRefChanged}
          />
        ) : f.type === "nhom_may-multi" ? (
          <NhomMayMultiField
            value={Array.isArray(form[f.key]) ? (form[f.key] as string[]) : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "don_vi_toc_do" ? (
          <DonViTocDoField
            value={String(form[f.key] ?? "")}
            onChange={(v) => set(f.key, v)}
            donViList={refData[f.refPrefix ?? ""] ?? []}
          />
        ) : f.type === "ref" ? (
          <div className="rc-input-wrapper">
            <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => setRef(f.key, e.target.value)}>
              <option value="">— chọn —</option>
              {/* Chịu được CẢ HAI cách đặt tên cột: 10 màn danh mục dùng `ma`/`ten`, còn Khách
                  hàng (mà màn Khuôn trỏ tới) dùng `code`/`name`. Không đỡ thì ô chọn ra một dãy
                  "undefined · undefined" — hỏng câm, vì `undefined` vẫn render thành chữ. */}
              {(refData[f.refPrefix ?? ""] ?? []).map((o) => {
                const ma = o.ma ?? o.code;
                const ten = o.ten ?? o.name;
                return (
                  <option key={o.id} value={o.id}>{ma ? `${ma} · ${ten}` : String(ten ?? o.id)}</option>
                );
              })}
            </select>
          </div>
        ) : f.type === "ref-search" ? (
          <RefSearchField
            value={form[f.key] == null || form[f.key] === "" ? null : Number(form[f.key])}
            options={refData[f.refPrefix ?? ""] ?? []}
            placeholder={hint ?? "Gõ mã / tên để tìm…"}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "ref-search-ma" ? (
          <RefSearchField
            value={form[f.key] == null || form[f.key] === "" ? null : String(form[f.key])}
            options={refData[f.refPrefix ?? ""] ?? []}
            placeholder={hint ?? "Gõ mã / tên để tìm…"}
            byMa
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "ref-multi" ? (
          <RefMultiField
            value={Array.isArray(form[f.key]) ? (form[f.key] as number[]) : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "self-ref-multi" ? (
          <SelfRefMultiField
            value={Array.isArray(form[f.key]) ? (form[f.key] as number[]) : []}
            options={(refData[f.refPrefix ?? ""] ?? []).filter(
              (o) => !isEdit || Number(o.id) !== Number(existing?.id))}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "formula" ? (
          <FormulaField value={String(form[f.key] ?? "")} onChange={(v) => set(f.key, v)}
            configPrefix={config.prefix}
            // Ô tự khai loại (vd "Công thức tính lượng" ở Vật tư/Giấy) thì ÉP bộ chip theo nó —
            // một màn có thể có hai ô công thức hỏi hai câu khác nhau.
            loaiO={f.loaiO}
            id={`formula-${f.key}`}
            // Nhãn TRONG khung đi theo nhãn của CHÍNH field. Trước 17/08/2026 nó đóng đinh
            // "Công thức tính giá", chấp nhận được khi mỗi màn chỉ có một ô; nay Giấy và Vật tư
            // có hai ô (giá · lượng) nên để cả hai cùng đội một tên là mời gõ nhầm ô — mà gõ nhầm
            // ở đây thì tiền chảy vào chỗ đếm lượng, không ai soi ra.
            //
            // Màn Đơn vị đứng riêng: ô của nó ra LƯỢNG chứ không ra tiền, và nhãn field ("Cách đo")
            // không đủ nói điều đó. Viết bằng TOÁN TỬ BA NGÔI chứ không spread đè lên `nhanO` —
            // spread hai lần cùng một prop là TS2783, và người đọc phải dò xem cái nào thắng.
            nhanO={laDonVi ? "Cách đo của đơn vị này" : cleanLabel}
            goY={laDonVi
              ? "vd: dai_in * rong_in * to_sau_in  (một m² tờ in đo thế nào)"
              : (hint || undefined)}
            // "Lần trước" (mục 3+7): chỉ có khi ĐANG SỬA — dòng mới tạo chưa có lịch sử.
            recordId={isEdit && existing ? Number(existing.id) : null}
            truocGiaTri={existing ? (existing[`${f.key}_truoc`] as string | null | undefined) ?? null : null}
            truocSuaLuc={existing ? (existing[`${f.key}_sua_luc`] as string | null | undefined) ?? null : null} />
        ) : f.type === "checkbox" ? (
          <label className="rc-switch">
            <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
            <span className="rc-switch__slider" />
            <span className="rc-switch__label">{form[f.key] ? "Có" : "Không"}</span>
          </label>
        ) : f.type === "date" ? (
          <div className="rc-input-wrapper">
            <input className="rc-input" type="date"
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
          </div>
        ) : f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta" ? (
          <div className="rc-input-wrapper">
            <textarea className="rc-textarea" rows={2} value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} placeholder="Nhập ghi chú hoặc thông tin bổ sung..." />
          </div>
        ) : (
          <div className="rc-input-wrapper">
            <input className={`rc-input${f.type === "number" ? " rc-input--num" : ""}`}
              type={f.type === "number" ? "number" : "text"} step="any" inputMode={f.type === "number" ? "decimal" : undefined}
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
            {suffix && <span className="rc-input-suffix">{suffix}</span>}
          </div>
        )}
        {hint && !(f.type === "ref-search" || f.type === "ref-search-ma") && <span className="rc-field__hint">{hint}</span>}
      </Tag>
    );
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || isMaDuplicate) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ten: form.ten };
    if (!config.autoCode || isEdit) body.ma = form.ma;
    for (const f of visibleFields) {
      let v = form[f.key];
      if (f.type === "ref-multi" || f.type === "self-ref-multi" || f.type === "nhom_may-multi" || f.type === "bands" || f.type === "dau-viec-dinh-muc") { body[f.key] = Array.isArray(v) ? v : []; continue; }
      if (v === "" || v === undefined) {
        const kieuChu = !f.type || f.type === "text" || f.type === "date" || f.type === "nhom_may";
        const voonCoGiaTri = isEdit && existing != null && existing[f.key] != null
          && existing[f.key] !== "";
        if (!f.required && !(kieuChu && voonCoGiaTri)) continue;
      }
      if ((f.type === "number" || f.type === "ref" || f.type === "ref-search") && v !== "" && v != null) v = Number(v);
      if (f.jsonKey) {
        const box = (body[f.jsonKey] as Record<string, unknown>) ??
          { ...((existing?.[f.jsonKey] as Record<string, unknown>) ?? {}) };
        box[f.key] = v;
        body[f.jsonKey] = box;
        continue;
      }
      body[f.key] = v;
    }
    try {
      // transformSubmit nằm TRONG try: nó ném thì trước đây thoát khỏi hàm async mà cờ `saving`
      // vẫn bật ⇒ nút quay mãi, không một chữ báo lỗi.
      const finalBody = config.transformSubmit ? config.transformSubmit(body, form, existing) : body;
      const moi = isEdit && existing
        ? await api.update(token, existing.id, finalBody)
        : await api.create(token, finalBody);
      // Vừa lưu xong = MỐC MỚI. Cần thật, không phải cho đẹp: `config.moLaiSauKhiTao` (màn Đơn vị)
      // GIỮ drawer mở sau khi tạo, mà component không bị remount nên mốc cũ còn nguyên — không đẩy
      // mốc thì đóng drawer ngay sau khi lưu vẫn bị hỏi "bỏ thay đổi?".
      mocBanDau.current = form;
      onSaved(moi);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Lưu thất bại.");
    } finally {
      // Lưu xong drawer KHÔNG chắc đóng: `config.moLaiSauKhiTao` (màn Đơn vị) giữ nó lại để khai
      // quy đổi ngay. Tắt cờ ở nhánh lỗi thôi là tạo xong nút kẹt vĩnh viễn ở trạng thái quay.
      setSaving(false);
    }
  }

  const typedMa = String(form.ma ?? "").trim().toUpperCase();
  const maTre = useTre(typedMa, 400);
  // Cảnh báo trùng mã: HỎI MÁY CHỦ (bảng chỉ còn 20 dòng nên không tự biết được). Một request
  // nhẹ sau khi gõ xong, lọc sẵn theo chính chuỗi vừa gõ. Đây chỉ là cảnh báo SỚM — chốt chặn
  // thật vẫn là ràng buộc trùng mã ở backend, nên sót một ca hiếm cũng không lọt vào DB.
  const [isMaDuplicate, setMaTrung] = useState(false);
  useEffect(() => {
    if (isEdit || !maTre || !token) { setMaTrung(false); return; }
    let huy = false;
    api.list(token, { q: maTre, size: 50 })
      .then((r) => {
        if (!huy) setMaTrung(r.items.some((x) => String(x.ma).trim().toUpperCase() === maTre));
      })
      .catch(() => { if (!huy) setMaTrung(false); });
    return () => { huy = true; };
  }, [isEdit, maTre, token, api]);

  /** Các TAB CÔNG THỨC. Gom ô `formula` theo `nhanTab`; ô không khai rơi vào tab mặc định (nhãn
   *  `nhanTabCongThuc`). Nhờ vậy Giấy tách được "Tính giá" / "Tính lượng" mà màn 1 tab vẫn y cũ.
   *  `renderExtra` (khối quy đổi của Đơn vị) bám tab ĐẦU — chỉ Đơn vị dùng, luôn 1 tab. */
  const formulaTabs = useMemo(() => {
    const ff = visibleFields.filter((f) => f.type === "formula");
    if (ff.length === 0 && config.renderExtra == null) return [];
    const nhanMacDinh =
      config.nhanTabCongThuc ?? (config.renderExtra ? "Quy đổi & số lượng" : "Công thức tính giá");
    const thuTu: string[] = [];
    const theoNhan = new Map<string, FieldDef[]>();
    ff.forEach((f) => {
      const nhan = f.nhanTab ?? nhanMacDinh;
      if (!theoNhan.has(nhan)) { theoNhan.set(nhan, []); thuTu.push(nhan); }
      theoNhan.get(nhan)!.push(f);
    });
    // Không có ô formula nhưng có renderExtra (Đơn vị) → vẫn cần 1 tab mặc định để chứa khối kia.
    if (thuTu.length === 0) { thuTu.push(nhanMacDinh); theoNhan.set(nhanMacDinh, []); }
    return thuTu.map((nhan, i) => ({
      id: `formula:${i}`,
      label: nhan,
      fields: theoNhan.get(nhan)!,
      coExtra: i === 0,
    }));
  }, [visibleFields, config.nhanTabCongThuc, config.renderExtra]);
  const hasFormulaField = formulaTabs.length > 0;
  // Nhật ký chỉ có nghĩa với bản ghi ĐÃ LƯU — đang thêm mới thì chưa có gì để xem.
  const coNhatKy = isEdit && !!config.nhatKyLoai && !!existing?.id;

  /** Tab khai báo có field THẬT ĐỂ HIỆN. Nhóm nào không được tab nào nhận thì dồn vào tab đầu —
   *  quên khai một nhóm trong config thì nó vẫn hiện chứ không biến mất im lặng. Tab rỗng (vd
   *  máy Bế không có nhóm "Khổ kẽm & Vùng in") bị bỏ hẳn, không bày ra rồi mở ra trắng trơn. */
  const tabsKhai = useMemo(() => {
    if (!config.tabsKhai?.length) return null;
    const daKhai = new Set(config.tabsKhai.flatMap((t) => t.groups));
    const conLai = [...new Set(visibleFields.map((f) => f.group || "Thông tin khác"))]
      .filter((g) => !daKhai.has(g));
    const coField = (groups: string[]) =>
      visibleFields.some((f) => f.type !== "formula" && groups.includes(f.group || "Thông tin khác"));
    return config.tabsKhai
      .map((t, i) => ({ ...t, groups: i === 0 ? [...t.groups, ...conLai] : t.groups, laDau: i === 0 }))
      .filter((t) => t.laDau || coField(t.groups));
  }, [config.tabsKhai, visibleFields]);

  // Tab đang chọn có thể vừa bị ẩn (đổi nhóm máy làm cả nhóm field biến mất) → rơi về tab đầu.
  const tabKhaiHienTai = tabsKhai
    ? (tabsKhai.find((t) => t.id === formulaTab) ?? tabsKhai[0])
    : null;
  const laTabCongThuc = formulaTab.startsWith("formula:");
  const dangOTabKhai = !tabsKhai
    ? formulaTab === "info"
    : !laTabCongThuc && formulaTab !== "nhatky";
  const coTabs = hasFormulaField || coNhatKy || (tabsKhai?.length ?? 0) > 1;

  const renderFieldsContent = (chiNhom?: string[], keoTheoMaTen = true) => {
    const fieldsToRender = visibleFields.filter((f) => f.type !== "formula")
      .filter((f) => !chiNhom || chiNhom.includes(f.group || "Thông tin khác"));
    const hasGroups = fieldsToRender.some((f) => f.group);

    const baseFields = !(config.autoCode && !isEdit) ? (
      <>
        <label className="rc-field">
          <span className="rc-field__label">Mã <em>*</em></span>
          <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
            <input className="rc-input rc-mono" value={String(form.ma ?? "")}
              disabled={isEdit} onChange={(e) => set("ma", e.target.value.toUpperCase())} required placeholder="Mã..." />
          </div>
          {!isEdit && typedMa && (
            <span style={{ fontSize: "11px", fontWeight: "600", marginTop: "1px", color: isMaDuplicate ? "var(--signal, #8a1f1f)" : "var(--moss, #2f5d3a)" }}>
              {isMaDuplicate ? "Mã đã tồn tại!" : "Mã hợp lệ!"}
            </span>
          )}
        </label>
        <label className="rc-field">
          <span className="rc-field__label">Tên <em>*</em></span>
          <div className="rc-input-wrapper">
            <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
          </div>
        </label>
      </>
    ) : (
      <label className="rc-field rc-field--full">
        <span className="rc-field__label">Tên <em>*</em></span>
        <div className="rc-input-wrapper">
          <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
        </div>
      </label>
    );

    if (!hasGroups) {
      return (
        <section className="rc-card-section" style={{ padding: "16px 20px" }}>
          <div className="rc-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: "12px 16px" }}>
            {keoTheoMaTen && baseFields}
            {fieldsToRender.map(renderField)}
          </div>
        </section>
      );
    }

    const sectionsMap = new Map<string, FieldDef[]>();
    fieldsToRender.forEach((f) => {
      const gName = f.group || "Thông tin khác";
      if (!sectionsMap.has(gName)) sectionsMap.set(gName, []);
      sectionsMap.get(gName)!.push(f);
    });

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {Array.from(sectionsMap.entries()).map(([gName, fields], idx) => {
          const isFirst = idx === 0;
          const colCount = gName === "Thông số chừa lề tờ in" && fields.length === 3 ? 3 : 2;
          return (
            <section className="rc-card-section" style={{ padding: "16px 20px" }} key={gName}>
              <div className="rc-card-section__title">{gName}</div>
              <div className="rc-grid" style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)`, gap: "12px 16px" }}>
                {keoTheoMaTen && isFirst && baseFields}
                {fields.map(renderField)}
              </div>
            </section>
          );
        })}
      </div>
    );
  };

  return (
    <Drawer
      kicker={isEdit ? "Chỉnh sửa" : "Thêm mới"}
      title={isEdit ? String(existing?.ten) : config.title}
      rong={hasFormulaField}
      onClose={yeuCauDong}
      foot={
        <>
          <Button type="button" variant="ghost" onClick={yeuCauDong}>Hủy</Button>
          <Button type="button" variant="primary" loading={saving} disabled={isMaDuplicate || (!isEdit && !config.autoCode && !typedMa)} onClick={() => submit(new Event("submit") as unknown as FormEvent)}>
            {isEdit ? "Lưu thay đổi" : "Tạo mới"}
          </Button>
        </>
      }
    >
      <form className="rc-drawer__body" onSubmit={submit}>
        {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}

        {coTabs ? (
          <div>
            <div className="rc-drawer__tabs" style={{ marginBottom: "var(--sp-4)" }}>
              {tabsKhai ? tabsKhai.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`rc-drawer__tab${tabKhaiHienTai?.id === t.id && dangOTabKhai ? " is-active" : ""}`}
                  onClick={() => setFormulaTab(t.id)}
                >
                  {t.label}
                </button>
              )) : (
                <button
                  type="button"
                  className={`rc-drawer__tab${formulaTab === "info" ? " is-active" : ""}`}
                  onClick={() => setFormulaTab("info")}
                >
                  Khai báo thông tin
                </button>
              )}
              {formulaTabs.map((ft) => (
                <button
                  key={ft.id}
                  type="button"
                  className={`rc-drawer__tab${formulaTab === ft.id ? " is-active" : ""}`}
                  onClick={() => setFormulaTab(ft.id)}
                >
                  {ft.label}
                </button>
              ))}
              {coNhatKy && (
                <button
                  type="button"
                  className={`rc-drawer__tab${formulaTab === "nhatky" ? " is-active" : ""}`}
                  onClick={() => setFormulaTab("nhatky")}
                >
                  Nhật ký
                </button>
              )}
            </div>

            {dangOTabKhai && (tabKhaiHienTai
              ? renderFieldsContent(tabKhaiHienTai.groups, tabKhaiHienTai.laDau)
              : renderFieldsContent())}
            {laTabCongThuc && (() => {
              // Tab đang chọn có thể vừa biến mất (ô formula bị `showIf` ẩn) → lùi về tab đầu, đừng
              // hiện khoảng trắng. Chỉ render field của CHÍNH tab này để "Tính giá" và "Tính lượng"
              // không lẫn sang nhau.
              const ft = formulaTabs.find((t) => t.id === formulaTab) ?? formulaTabs[0];
              if (!ft) return null;
              return (
                <div>
                  {ft.fields.map(renderField)}
                  {ft.coExtra && config.renderExtra?.(form, existing)}
                </div>
              );
            })()}
            {formulaTab === "nhatky" && coNhatKy && (
              <NhatKyTab loai={config.nhatKyLoai!} id={Number(existing!.id)} />
            )}
          </div>
        ) : (
          renderFieldsContent()
        )}
      </form>

      {/* Hai hộp thoại nằm TRONG `Drawer` (z-index 500 > scrim 60 nên vẫn phủ lên trên): để ngoài
          thì drawer đóng là chúng biến mất cùng, đúng lúc đang hỏi có nên đóng hay không. */}
      <DiscardChangesDialog
        open={hoiBoThayDoi}
        onDiscard={() => { setHoiBoThayDoi(false); onClose(); }}
        onKeepEditing={() => setHoiBoThayDoi(false)}
      />
      <ConfirmDialog
        open={doiToChoXacNhan !== null}
        title="Đổi tổ phụ trách?"
        message="Các đầu việc định mức đã chọn sẽ bị bỏ hết — định mức gắn theo tổ, đổi tổ là chúng không còn nghĩa."
        confirmLabel="Đổi tổ, bỏ định mức"
        cancelLabel="Giữ nguyên"
        danger
        onConfirm={() => {
          setForm((prev) => ({ ...prev, department_id: doiToChoXacNhan, dau_viec_dinh_muc: [] }));
          setDoiToChoXacNhan(null);
        }}
        onCancel={() => setDoiToChoXacNhan(null)}
      />
    </Drawer>
  );
}
