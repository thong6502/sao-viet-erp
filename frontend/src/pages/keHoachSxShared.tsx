// Mảnh dùng chung của bàn Kế hoạch sản xuất: pill trạng thái · chip cờ · chip thiếu · skeleton ·
// empty-state · helper định dạng số/ngày. Tách riêng để 4 view (hàng chờ · preview · list · chi
// tiết) không chép lại — và để mọi nhãn trạng thái nằm ĐÚNG MỘT chỗ.
import type { ReactNode } from "react";
import { Icon, type IconName } from "../components/Icons";
import {
  LSX_LOAI_BUOC_META,
  LSX_THIEU_LABELS,
  nhanMa,
  type DonViNhan,
  type LsxDen,
  type LsxLoaiBuoc,
  type LsxTrangThai,
} from "../api/client";

// --- định dạng --------------------------------------------------------------
export function num(v: number | null | undefined): string {
  return v == null ? "—" : Number(v).toLocaleString("vi-VN");
}

export function ngay(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function ngayGio(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Số ngày còn lại tới hạn (âm = đã quá hạn). null khi không có hạn. */
export function conLai(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

/** Class cảnh báo hạn: quá hạn (đỏ) / ≤3 ngày (hổ phách). */
export function classHan(dateStr: string | null | undefined): string {
  const n = conLai(dateStr);
  if (n == null) return "";
  if (n < 0) return "khsx-date--late";
  if (n <= 3) return "khsx-date--soon";
  return "";
}

/** Class cảnh báo hạn ưu tiên LỊCH THẬT, lùi về đếm ngày lịch khi lệnh chưa vào kế hoạch.
 *
 *  `classHan` chỉ so hôm nay với ngày hạn. Câu đó bỏ sót đúng trường hợp đáng lo nhất: lệnh còn
 *  10 ngày tới hạn nhưng lịch đã kéo qua hạn 2 ngày thì nó ĐANG trễ, mà ô vẫn xanh. `slack_ngay`
 *  (độ dư nhỏ nhất giữa các bước đã xếp, âm = trễ — xem `services/lsx_tong_quan.py::_slack`) trả
 *  lời thẳng câu đó. Không thêm ô nào, chỉ đổi NGUỒN tô màu của cột sẵn có. */
export function classHanLich(
  slack: number | null | undefined,
  dateStr: string | null | undefined,
): string {
  if (slack == null) return classHan(dateStr);
  if (slack < 0) return "khsx-date--late";
  if (slack <= 1) return "khsx-date--soon";
  return "";
}

// --- nhóm công đoạn (enum `cong_doan.NHOM` ở backend) -----------------------
/** 4 giá trị CỐ ĐỊNH của `cong_doan.nhom` — enum ở backend (`models/cong_doan.py`), KHÔNG phải
 *  danh mục động, nên khai cứng ở đây là đúng chỗ.
 *
 *  DỜI TỪ `rebuildCatalogConfigs.tsx` (02/09/2026) chứ không chép: màn "Hồ sơ lệnh sản xuất" cần
 *  đúng bốn nhãn này cho ô lọc Nhóm công đoạn, mà import ngược từ `rebuildCatalogConfigs` sẽ kéo
 *  cả bộ máy 13 màn danh mục vào bundle của một màn tra cứu. Đặt ở module dùng chung của họ Sản
 *  xuất (file này vốn đã là nơi "mọi nhãn nằm ĐÚNG MỘT chỗ") và cho bên danh mục import sang. */
export const NHOM_CONG_DOAN: Record<string, string> = {
  prepress: "Trước In",
  print: "In",
  finishing: "Gia công sau in",
  other: "Dịch vụ khác",
};

// --- trạng thái lệnh --------------------------------------------------------
const PILL: Record<LsxTrangThai, { label: string; cls: string }> = {
  nhap: { label: "Nháp", cls: "khsx-pill--nhap" },
  // `cho_bo_sung` KHÔNG còn mặt riêng (18/08/2026): server vẫn lật cờ này khi lưu một lệnh còn
  // dở, nhưng cột phải màn chi tiết đã kêu "Còn thiếu N mục" — hai chỗ báo cùng một việc gây rối,
  // và pill đứng yên ở Nháp cho tới lần lưu kế nên nó nói sai nhiều hơn nói đúng. Giữ KHOÁ để
  // lệnh cũ trong DB vẫn render được, chỉ cho đội lốt Nháp.
  cho_bo_sung: { label: "Nháp", cls: "khsx-pill--nhap" },
  san_sang: { label: "Sẵn sàng", cls: "khsx-pill--sansang" },
  da_lap_ke_hoach: { label: "Đã lập kế hoạch", cls: "khsx-pill--dakethoach" },
  da_phat_hanh: { label: "Đã phát hành", cls: "khsx-pill--phathanh" },
};

export function TrangThaiPill({ tt, lg = false }: { tt: LsxTrangThai; lg?: boolean }) {
  const meta = PILL[tt] ?? PILL.nhap;
  return (
    <span className={`khsx-pill ${meta.cls} ${lg ? "khsx-pill--lg" : ""}`}>
      <span className="khsx-pill__dot" aria-hidden="true" />
      {meta.label}
    </span>
  );
}

// `key` có thể là NHIỀU trạng thái ngăn bằng dấu phẩy — repo backend nhận danh sách (`IN`), FE đếm
// bằng cách tách chuỗi. Tab "Nháp" ôm luôn `cho_bo_sung` vì hai cái nay là một mặt.
export const TRANG_THAI_TABS: { key: string; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "nhap,cho_bo_sung", label: "Nháp" },
  { key: "san_sang", label: "Sẵn sàng" },
];

// --- trạng thái XẾP LỊCH (bàn Xếp lịch công đoạn) ---------------------------
// Mọi nhãn của bàn xếp lịch nằm ĐÚNG MỘT chỗ (cùng file với pill/chip lệnh) — không đẻ file nhãn riêng.

/** Thời lượng phút → "1 giờ 13 phút". Chữ CÓ DẤU nên KHÔNG dùng mono; canh cột bằng tabular-nums ở CSS. */
export function thoiLuong(phut: number | null | undefined): string {
  if (phut == null || phut <= 0) return "—";
  const t = Math.round(phut);
  const gio = Math.floor(t / 60);
  const p = t % 60;
  if (gio && p) return `${gio} giờ ${p} phút`;
  if (gio) return `${gio} giờ`;
  return `${p} phút`;
}

/** Thời lượng phút → "1g16" / "45ph" — bản NGẮN cho chỗ chật (thanh Gantt). Chữ dài "1 giờ 16
 *  phút" ăn hết bề ngang chip rồi bị cắt cụt, nên chip dùng bản này, tooltip/drawer dùng bản dài. */
export function thoiLuongNgan(phut: number | null | undefined): string {
  if (phut == null || phut <= 0) return "—";
  const t = Math.round(phut);
  const gio = Math.floor(t / 60);
  const p = t % 60;
  if (gio && p) return `${gio}g${String(p).padStart(2, "0")}`;
  if (gio) return `${gio}g`;
  return `${p}ph`;
}

/** Pill trạng thái xếp lịch (bo TRÒN, bám .khsx-pill). Suy từ trang_thai + is_locked + co_xung_dot;
 *  ưu tiên Xung đột > Khóa > Đã xếp > Chờ. CÓ CHỮ (không chỉ dựa màu — a11y). */
export function LichTrangThaiPill({
  trangThai,
  isLocked = false,
  coXungDot = false,
}: {
  trangThai: string;
  isLocked?: boolean;
  coXungDot?: boolean;
}) {
  let cls = "xlcd-lpill--cho";
  let label = "Chờ xếp lịch";
  let icon: IconName | null = null;
  if (coXungDot) {
    cls = "xlcd-lpill--xungdot";
    label = "Có xung đột";
    icon = "ban";
  } else if (isLocked) {
    cls = "xlcd-lpill--khoa";
    label = "Đã khóa";
    icon = "lock";
  } else if (trangThai === "da_xep") {
    cls = "xlcd-lpill--daxep";
    label = "Đã xếp lịch";
  }
  return (
    <span className={`khsx-pill ${cls}`}>
      {icon ? <Icon name={icon} size={11} /> : <span className="khsx-pill__dot" aria-hidden="true" />}
      {label}
    </span>
  );
}

const RUI_RO_META: Record<string, { label: string; cls: string }> = {
  an_toan: { label: "An toàn", cls: "xlcd-risk--an-toan" },
  sap_toi_han: { label: "Sắp tới hạn", cls: "xlcd-risk--sap" },
  nguy_co_tre: { label: "Nguy cơ trễ", cls: "xlcd-risk--nguy-co" },
  da_tre: { label: "Đã trễ", cls: "xlcd-risk--tre" },
  chua_co_han: { label: "Chưa có hạn", cls: "xlcd-risk--chua" },
};

/** Chip nguy cơ trễ (bo VUÔNG nhẹ) — nhãn rủi ro + độ dư ("−2d"/"+5d"). CÓ CHỮ (a11y color-not-only). */
export function NguyCoTreChip({
  nhan,
  slackNgay = null,
}: {
  nhan: string | null | undefined;
  slackNgay?: number | null;
}) {
  const meta = RUI_RO_META[nhan ?? "chua_co_han"] ?? RUI_RO_META.chua_co_han;
  const slack =
    slackNgay == null
      ? null
      : `${slackNgay > 0 ? "+" : slackNgay < 0 ? "−" : ""}${Math.abs(slackNgay)}d`;
  return (
    <span className={`xlcd-risk ${meta.cls}`}>
      <span className="xlcd-risk__dot" aria-hidden="true" />
      <span className="xlcd-risk__txt">{meta.label}</span>
      {slack && <span className="xlcd-risk__slack">{slack}</span>}
    </span>
  );
}

// --- chip -------------------------------------------------------------------
export function ChipGap() {
  return (
    <span className="khsx-chip khsx-chip--rush">
      <Icon name="bell" size={11} /> GẤP
    </span>
  );
}

export function ChipNgoai({ ncc }: { ncc?: string | null }) {
  return (
    <span className="khsx-chip khsx-chip--ngoai" title={ncc ? `Thuê ngoài: ${ncc}` : "Thuê ngoài"}>
      <Icon name="truck" size={11} /> {ncc || "thuê ngoài"}
    </span>
  );
}

// --- Hàng đèn tiến độ (Đợt 1 redesign 18/08/2026) ---------------------------
// Ba thứ bảng lệnh CHƯA nói: vật tư đã có chủ chưa · lịch đã đứng được chưa · có ai làm không.
// Hạn và Định mức KHÔNG có đèn ở đây — cột `Hạn` đã tô bằng `classHan` và cột `CĐ` đã đỏ khi lệnh
// chưa có công đoạn; đèn thứ tư chỉ nói lại chuyện cột bên cạnh vừa nói.

const DEN_META: Record<keyof LsxDen, { label: string; icon: IconName }> = {
  vat_tu: { label: "Vật tư", icon: "box" },
  may_gio: { label: "Máy & giờ", icon: "printer" },
  nguoi: { label: "Người", icon: "users" },
};
const DEN_KEYS = ["vat_tu", "may_gio", "nguoi"] as const;

/** Chỉ vẽ chấm cho `do`/`vang`; `ok` để trống ô.
 *
 *  20 lệnh × 3 chấm mà đa số xanh thì mắt không bắt được cái đỏ — điều độ quét bảng để TÌM chỗ
 *  tắc, không cần được xác nhận chỗ không tắc. `den == null` = chưa tải xong (đèn gọi rời sau
 *  bảng): giữ ô trống, đừng nhấp nháy skeleton trên từng dòng.
 */
export function DenTienDo({
  den,
  lg = false,
  onNhay,
}: {
  den: LsxDen | null | undefined;
  lg?: boolean;
  onNhay?: (nhay: { man: string; id: number }) => void;
}) {
  if (!den) return <span className="khsx-den khsx-den--cho" aria-hidden="true" />;
  const hien = DEN_KEYS.filter((k) => den[k].muc !== "ok");
  if (!hien.length) {
    return (
      <span className="khsx-den__ok" title="Không vướng gì">
        {lg ? (
          <>
            <Icon name="check" size={12} /> Không vướng gì
          </>
        ) : (
          "—"
        )}
      </span>
    );
  }
  return (
    <span className={`khsx-den ${lg ? "khsx-den--lg" : ""}`}>
      {hien.map((k) => {
        const d = den[k];
        const meta = DEN_META[k];
        const day = `${meta.label}: ${d.chu}`;
        const noi = (
          <>
            <Icon name={meta.icon} size={12} />
            <span className="khsx-den__txt">{lg ? d.chu : meta.label}</span>
            {!lg && <span className="sr-only">: {d.chu}</span>}
          </>
        );
        const cls = `khsx-den__chip khsx-den__chip--${d.muc}`;
        return d.nhay && onNhay ? (
          <button
            key={k}
            type="button"
            className={`${cls} khsx-den__chip--bam`}
            title={day}
            // Chấm nằm TRONG dòng bấm-được của bảng lệnh: không chặn nổi bọt thì bấm chấm vừa nhảy
            // màn vừa mở chi tiết lệnh, người dùng thấy hai việc xảy ra cho một cú bấm.
            onClick={(e) => {
              e.stopPropagation();
              onNhay(d.nhay!);
            }}
          >
            {noi}
          </button>
        ) : (
          <span key={k} className={cls} title={day}>
            {noi}
          </span>
        );
      })}
    </span>
  );
}

/** Chip THIẾU — bo vuông (khác pill trạng thái bo tròn) để không lẫn.
 *
 *  `dv` = đơn vị bốn chặng của CHÍNH lệnh/dòng đang xét. Bốn câu checklist có nhắc đơn vị sẽ gọi
 *  tên xưởng đặt thay vì chữ cứng "tờ in → con" (xem `LSX_THIEU_LABELS`). Không truyền cũng chạy:
 *  câu lùi về bản chung. */
export function ChipThieu({ code, dv }: { code: string; dv?: DonViNhan | null }) {
  return (
    <span className="khsx-need">
      <Icon name="x" size={10} /> {nhanMa(LSX_THIEU_LABELS, code, dv)}
    </span>
  );
}

/** Xếp chồng chip thiếu, tối đa `max` rồi gộp phần dư → chiều cao hàng không giật. */
export function ThieuStack(
  { codes, max = 2, dv }: { codes: string[]; max?: number; dv?: DonViNhan | null },
) {
  if (!codes.length) return <span className="khsx-muted">—</span>;
  const hien = codes.slice(0, max);
  const du = codes.slice(max);
  return (
    <span className="khsx-need-stack">
      {hien.map((c) => (
        <ChipThieu key={c} code={c} dv={dv} />
      ))}
      {du.length > 0 && (
        <span
          className="khsx-need khsx-need--more"
          title={du.map((c) => nhanMa(LSX_THIEU_LABELS, c, dv)).join(" · ")}
        >
          +{du.length}
        </span>
      )}
    </span>
  );
}

/** Cảnh báo MỀM (không nền) — phân cấp: đỏ có nền = chặn, vàng không nền = lưu ý. */
export function CanhBaoMem({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="khsx-warn-inline" title={title}>
      <Icon name="help" size={11} /> {children}
    </span>
  );
}

/** Chuỗi công đoạn "In › Cán › Bế › Dán" — nhìn 1 giây là hiểu cả routing.
 *
 *  Nhận `loai_buoc` (không phải cờ thuê-ngoài) để màn "lệnh dự kiến" và màn lệnh đã tạo dùng
 *  CHUNG một cách gọi tên. Chỉ đánh dấu bước NGOẠI LỆ — bước máy/tổ là phần lớn routing, tô hết
 *  thì màu hết mang tin. */
export function ChuoiCongDoan({
  steps,
  activeIndex,
}: {
  steps: { ten: string; loai_buoc?: string }[];
  /** Tô đậm bước ĐANG xem (drawer 1 công đoạn) — bỏ trống thì không tô (giữ nguyên hành vi cũ). */
  activeIndex?: number;
}) {
  if (!steps.length) {
    return <span className="khsx-flow khsx-flow--none">chưa có công đoạn</span>;
  }
  return (
    <span className="khsx-flow">
      {steps.map((s, i) => {
        const meta = s.loai_buoc ? LSX_LOAI_BUOC_META[s.loai_buoc as LsxLoaiBuoc] : undefined;
        const ngoaiLe = !!meta && s.loai_buoc !== "may" && s.loai_buoc !== "to";
        const active = i === activeIndex;
        return (
          <span
            key={`${s.ten}-${i}`}
            className={`khsx-flow__step ${ngoaiLe ? `khsx-flow__step--${meta.tone}` : ""} ${active ? "khsx-flow__step--active" : ""}`}
            title={meta?.hint}
            aria-current={active ? "step" : undefined}
          >
            {s.loai_buoc === "thue_ngoai" && <Icon name="truck" size={10} />}
            {s.ten}
          </span>
        );
      })}
    </span>
  );
}

// --- ô key–value ------------------------------------------------------------
/** Ô nhãn–giá trị CHỈ ĐỌC (khuôn `.khsx-kv` trong ke-hoach-sx.css). Dùng cho số DẪN XUẤT: cái gì
 *  gõ được thì là `<label class="khsx-kv khsx-kv--edit">`, không phải ô này. */
export function Kv({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="khsx-kv">
      <span className="khsx-kv__k">{k}</span>
      <span className="khsx-kv__v">{v}</span>
    </div>
  );
}

// --- trạng thái tải / rỗng / lỗi -------------------------------------------
export function Skeleton({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <tbody className="khsx-skel">
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c}>
              <span className="khsx-skel__bar" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

export function EmptyState({
  icon,
  title,
  sub,
  action,
}: {
  icon: IconName;
  title: string;
  sub?: string;
  action?: ReactNode;
}) {
  return (
    <div className="khsx-empty">
      <Icon name={icon} size={44} />
      <p className="khsx-empty__title">{title}</p>
      {sub && <p className="khsx-empty__sub">{sub}</p>}
      {action}
    </div>
  );
}

export function BangLoi({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="banner banner--error" role="alert">
      <span>{text}</span>
      {onRetry && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          Tải lại
        </button>
      )}
    </div>
  );
}
