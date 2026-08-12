// Bảng ROUTING của lệnh — kế thừa từ bài tính giá nhưng SỬA ĐƯỢC tại lệnh. Lưu = REPLACE-ALL,
// không đụng phiếu tính giá và không ảnh hưởng lệnh khác.
//
// Bảng cố tình chỉ giữ 7 cột — phần QUYẾT ĐỊNH: bước nào · ai làm · vào ra bao nhiêu · mất bao lâu.
// Phần KHAI BÁO (2 đơn vị + hệ số, 5 loại thời gian, số nhân công, điều kiện, 10 ô gia công ngoài)
// nằm trong drawer từng bước. Nhồi ~20 ô vào bảng thì mỗi ô còn ~60px và phải cuộn ngang liên tục.
//
// SỐ LƯỢNG là DẪN XUẤT: server chạy chuỗi ngược từ SL thành phẩm của bước CUỐI lên (`_ap_chuoi_nguoc`)
// rồi ghi thẳng vào/ra + hao của mọi bước. Bảng này KHÔNG gõ số nữa, và cũng không còn nút "Tính
// ngược" — số hiển thị chính là kết quả tính ngược. Ô duy nhất gõ được nằm trong drawer bước cuối.
// Các kiểm tra (chưa gán tổ, thuê ngoài thiếu NCC, đứt đơn vị) chỉ TÔ MÀU, không chặn lưu.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  LSX_LOAI_BUOC_META,
  type LsxBuocMacDinh,
  type LsxCongDoan,
  type LsxCongDoanBody,
  type LsxLeadTime,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { DagRoutingCanvas } from "../components/DagRoutingCanvas";
import { LsxBuocDrawer, type TabKey as DrawerTabKey } from "./LsxBuocDrawer";
import { ChuoiCongDoan, ngay, num } from "./keHoachSxShared";
import { tenDonVi, useNapTenDonVi } from "./tenDonVi";
import {
  type DonViChuoi,
  type EditRow,
  emptyRow,
  heSoChu,
  n,
  phut,
  thoiLuong,
  toBody,
  toEdit,
} from "./lsxBuoc";
import "./dag-routing.css";

export interface RefRow {
  id: number;
  ten: string;
  /** Máy: `loai_may` — để gom nhóm dropdown thay vì đổ 24 dòng phẳng. */
  nhom?: string | null;
  ma?: string;
  donVi?: string;
  /** MÁY — số để tính thời lượng NGAY trên form, trước khi lưu. Đổi máy trong drawer phải thấy
   *  chuẩn bị + thời gian chạy nhảy liền; đợi server trả `thoi_luong_dien_giai` thì phải bấm Lưu
   *  mới biết, mà đúng lúc đó người dùng đã lưu mù rồi. */
  tocDo?: number | null;
  tocDoMin?: number | null;
  tocDoMax?: number | null;
  donViTocDo?: string | null;
  chuanBiPhut?: number | null;
  chuanBiKhoan?: { ten?: string; phut?: number }[];
}

/** Nhãn đơn vị CỦA MỘT BƯỚC. Chưa khai đơn vị ⇒ “—”.
 *
 *  Tên lấy từ DANH MỤC, không còn bảng nhãn cứng. Chưa nạp xong ⇒ rơi về MÃ TRẦN, không bịa tên.
 *
 *  Bộ lọc legacy hẹp lại (12/08/2026): trước đây cứ `nhom === "prepress"` là trả “—”, bất kể bước
 *  khai đơn vị gì. Từ khi công đoạn khai đơn vị TỰ DO, bước ghi kẽm khai `m² → bài in` cho tử tế
 *  vẫn bị nuốt sạch nhãn — trong khi thẻ trên sơ đồ DAG (không đi qua hàm này) lại hiện đúng
 *  "m² → bài in". Cùng một bước, hai màn hai kiểu.
 *
 *  Thứ ĐÁNG giấu chỉ là ảnh chụp cũ `to → to` còn sót ở bước chế bản — nhận ra nó bằng "prepress
 *  MÀ lại đứng trên dòng giấy", chứ không phải bằng mỗi `nhom`. Bước khai đơn vị ngoài dòng giấy
 *  (`m² → bài in`) là dữ liệu THẬT, phải hiện. */
export function dvNhan(
  dv: string | null | undefined,
  buoc?: { nhom?: string | null; tren_dong_giay?: boolean } | null,
): string {
  if (buoc?.nhom === "prepress" && buoc?.tren_dong_giay) return "—";
  if (dv) return tenDonVi(dv) ?? dv;
  return "—";
}

/** Lỗi/nghi vấn của RIÊNG 1 dòng — chỉ tô màu, không chặn lưu. */
/** Nhãn ngắn cho badge trạng thái hàng gia công ngoài — dùng chung bảng và sơ đồ DAG. */
export function nhanGiaoNhan(r: EditRow): string {
  const gn = r.giao_nhan;
  if (!gn || gn.giao_nhan_trang_thai === "chua_gui") return "Chưa gửi đi";
  if (gn.giao_nhan_trang_thai === "dang_ngoai") {
    const tre = gn.qua_han_ngay ?? 0;
    return tre > 0 ? `Đang ở ngoài · quá hạn ${tre} ngày` : "Đang ở ngoài";
  }
  const hut = gn.so_hut ?? 0;
  return hut > 0 ? `Đã về · thiếu ${num(hut)}` : "Đã về";
}

function loiDong(rows: EditRow[], i: number): string[] {
  const r = rows[i];
  const out: string[] = [];
  const vao = n(r.so_luong_vao);
  const ra = n(r.so_luong_ra);
  if (r.don_vi_vao === r.don_vi_ra && vao > 0 && ra > vao) out.push("ra nhiều hơn vào");
  // KHÔNG kiểm `he_so <= 1` nữa: hệ số nay do server suy, và 1 là HỢP LỆ ở cả hai cầu
  // (1 tờ nguyên ra 1 tờ in là chuyện thường). Luật cũ bắt oan đúng ca đó.
  if (r.loai_buoc === "thue_ngoai") {
    if (!r.nha_cung_cap.trim()) out.push("chưa có nhà gia công");
    if (!r.ngay_gui_dk || !r.ngay_nhan_dk) out.push("chưa có ngày gửi / nhận");
  } else if (r.department_id == null && r.may_id == null) {
    out.push("chưa gán tổ / máy");
  }
  // Bước TRƯỚC trên dòng giấy (bỏ qua bước đơn vị trống, vd chế bản) phải nhả đúng đơn vị mà
  // bước này ăn. Không lọc thì chế bản đứng đầu routing đẻ cảnh báo giả với bước in ngay sau.
  if (r.don_vi_vao) {
    const truoc = rows.slice(0, i).reverse().find((x) => x.don_vi_vao && x.don_vi_ra);
    if (truoc && truoc.don_vi_ra !== r.don_vi_vao) out.push("đứt đơn vị");
  }
  if (i > 0 && r.ten && rows[i - 1].ten === r.ten) out.push("trùng bước trước");
  return out;
}

export function LsxRoutingTable({
  congDoans,
  soLuongDat,
  buHaoThem,
  leadTime,
  baiGhep,
  congDoanRefs,
  toRefs,
  mayRefs,
  khuonRefs,
  vatTuRefs,
  phuThuocRefs,
  canUpdate,
  saving,
  onSave,
  onPatchLsx,
  onMacDinhBuoc,
  onDauViecOptions,
  onGiaoNhan,
  onDirtyChange,
  dvChuoi,
}: {
  congDoans: LsxCongDoan[];
  soLuongDat: number;
  buHaoThem: number;
  leadTime: LsxLeadTime | null;
  /** Lệnh đang ghép chung tờ → thông số tờ do BÀI quyết, bước in khoá lại ở màn này. */
  baiGhep: import("../api/client").LsxBaiGhep | null;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  khuonRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  canUpdate: boolean;
  saving: boolean;
  onSave: (body: LsxCongDoanBody[], lyDo?: string) => void;
  /** Sửa cấp LỆNH từ drawer bước cuối (SL thành phẩm / hao thêm) → server tính lại cả chuỗi. */
  onPatchLsx: (p: { so_luong_dat?: number; bu_hao_to?: number }) => void;
  onMacDinhBuoc: (congDoanId: number) => Promise<LsxBuocMacDinh>;
  onDauViecOptions: (
    congDoanId: number, departmentId: number,
  ) => Promise<import("../api/client").LsxDauViecOption[]>;
  /** Ghi nhận giao/nhận hàng gia công ngoài — GHI THẲNG, không đi qua "Lưu công đoạn". */
  onGiaoNhan: (
    buocId: number, body: { su_kien: "giao" | "nhan"; luc?: string; so_luong?: number },
  ) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
  /** Đơn vị bốn chặng của lệnh — SERVER chấm, cha truyền xuống. Bảng KHÔNG tự suy lại từ `rows`:
   *  luật suy chặng chỉ có một bản, ở `dong_giay.don_vi_chuoi`. Đánh đổi: đổi công đoạn của một
   *  bước thì nhãn ở băng bài ghép cập nhật sau khi bấm Lưu, không tức thì. */
  dvChuoi: DonViChuoi;
}) {
  // Nhãn đơn vị đọc từ DANH MỤC — nạp một lần cho cả phiên. Hook ở ĐÂY (gốc của bảng + DAG +
  // drawer) nên mọi chỗ gọi `dvNhan` vẽ lại khi danh mục về, khỏi phải truyền prop qua 22 chỗ.
  useNapTenDonVi();
  const [rows, setRows] = useState<EditRow[]>(() => congDoans.map(toEdit));
  const [viewMode, setViewMode] = useState<"dag" | "table">("dag");
  const [undo, setUndo] = useState<{ row: EditRow; at: number } | null>(null);
  const [live, setLive] = useState("");
  const [moBuoc, setMoBuoc] = useState<number | null>(null);
  const [tabDau, setTabDau] = useState<DrawerTabKey | undefined>(undefined);
  const [keo, setKeo] = useState<number | null>(null);
  const [lyDo, setLyDo] = useState("");
  const goc = useRef(JSON.stringify(toBody(congDoans.map(toEdit))));
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const doiToSeq = useRef(0);
  // Hàng đang mở drawer — đóng lại thì trả tiêu điểm về đúng hàng đó (nợ của lát trước).
  const hangMo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const fresh = congDoans.map(toEdit);
    setRows(fresh);
    goc.current = JSON.stringify(toBody(fresh));
  }, [congDoans]);

  const dirty = JSON.stringify(toBody(rows)) !== goc.current;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);


  // Dải "hoàn tác" tự tắt sau 6s — xoá dòng chưa lưu không cần hỏi han.
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 6000);
    return () => clearTimeout(t);
  }, [undo]);

  const patch = useCallback((key: string, p: Partial<EditRow>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...p } : r)));
  }, []);

  /** Đổi công đoạn của 1 bước → kéo lại dữ liệu trung tính của công đoạn (tổ phụ trách, đơn vị,
   *  chuẩn bị). Loại bước và tài nguyên vẫn là quyết định của kế hoạch tại chính bước LSX.
   *
   *  Không làm việc này thì bước đổi xong vẫn đeo nguyên số của công đoạn CŨ — đổi "Dán hộp" (tổ,
   *  đếm con, 4.000 con/giờ) sang "Cán màng" (máy, đếm tờ) mà thời lượng và đơn vị vẫn của Dán hộp,
   *  chẳng cảnh báo gì.
   *
   *  KHÔNG đụng số lượng vào/ra: server tính lại cả chuỗi sau khi lưu routing.
   *  Luật đơn vị nằm ở BACKEND, ở đây chỉ áp kết quả để hai nơi không trôi khỏi nhau. */
  const doiCongDoan = useCallback(
    async (key: string, id: number | null, tenHienTai: string) => {
      if (id == null) {
        patch(key, { cong_doan_id: null });
        return;
      }
      try {
        const m = await onMacDinhBuoc(id);
        patch(key, {
          cong_doan_id: m.cong_doan_id, ten: m.ten, nhom: m.nhom,
          department_id: m.department_id,
          don_vi_vao: m.don_vi_vao, don_vi_ra: m.don_vi_ra,
          he_so_quy_doi: m.he_so_quy_doi > 1 ? String(m.he_so_quy_doi) : "",
          // Thời gian chuẩn bị + chạy KHÔNG còn nằm ở bước: kế thừa sống từ máy đang gán.
        });
        setLive(`Đã đổi sang ${m.ten} và lấy lại đơn vị, tổ phụ trách`);
      } catch {
        // Mất mạng / không có quyền đọc danh mục → ít nhất vẫn đổi được tên, đừng chặn người dùng.
        patch(key, { cong_doan_id: id, ten: tenHienTai, department_id: null });
      }
    },
    [onMacDinhBuoc, patch],
  );

  /** Đổi tổ phải đổi luôn tập đầu việc khoán; không được giữ snapshot/list của tổ cũ. */
  const doiTo = useCallback(async (key: string, departmentId: number | null) => {
    const seq = ++doiToSeq.current;
    const row = rows.find((x) => x.key === key);
    const reset: Partial<EditRow> = {
      department_id: departmentId,
      khoan_rate_id: null,
      khoan_chon_duoc: [],
      khoan_dien_giai: null,
      khoan_ly_do: null,
      nang_suat: "",
      don_vi_nang_suat: "",
      so_nhan_cong: "1",
      so_nhan_cong_tieu_chuan: 1,
      so_nhan_cong_toi_da: null,
    };
    patch(key, reset);
    if (!departmentId || !row?.cong_doan_id) return;
    try {
      const options = await onDauViecOptions(row.cong_doan_id, departmentId);
      if (seq !== doiToSeq.current) return;
      // Đúng MỘT đầu việc thì điền sẵn (không có gì để chọn nhầm); từ hai trở lên để TRỐNG cho
      // người lập lệnh quyết theo hàng. Cờ `is_default` khai ở danh mục đã gỡ 12/08/2026 (mg 0190)
      // — luật này phải khớp `lsx_service._khoan_mac_dinh`, lệch là FE điền một đằng BE một nẻo.
      const chosen = options.length === 1 ? options[0] : null;
      patch(key, {
        ...reset,
        khoan_chon_duoc: options,
        khoan_rate_id: chosen?.id ?? null,
        nang_suat: chosen ? String(chosen.nang_suat_nguoi_gio) : "",
        don_vi_nang_suat: chosen?.don_vi_nang_suat ?? "",
        so_nhan_cong: String(chosen?.so_nguoi_tieu_chuan ?? 1),
        so_nhan_cong_tieu_chuan: chosen?.so_nguoi_tieu_chuan ?? 1,
        so_nhan_cong_toi_da: chosen?.so_nguoi_toi_da ?? null,
      });
      setLive(options.length
        ? `Đã nạp ${options.length} đầu việc khoán của tổ mới`
        : "Tổ mới không có đầu việc khoán được gắn với công đoạn này");
    } catch {
      if (seq === doiToSeq.current) setLive("Không tải được bảng khoán của tổ mới");
    }
  }, [onDauViecOptions, patch, rows]);

  function move(idx: number, delta: number) {
    doiCho(idx, idx + delta);
  }

  function doiCho(from: number, to: number) {
    setRows((prev) => {
      if (to < 0 || to >= prev.length || from === to) return prev;
      const next = [...prev];
      const [row] = next.splice(from, 1);
      next.splice(to, 0, row);
      setLive(`Đã chuyển ${row.ten || "công đoạn"} tới vị trí ${to + 1}`);
      return next;
    });
  }

  function remove(idx: number) {
    setRows((prev) => {
      const row = prev[idx];
      setUndo({ row, at: idx });
      setLive(`Đã bỏ ${row.ten || "công đoạn"}, có thể hoàn tác`);
      return prev.filter((_, i) => i !== idx);
    });
    setMoBuoc(null);
  }

  function hoanTac() {
    if (!undo) return;
    setRows((prev) => {
      const next = [...prev];
      next.splice(Math.min(undo.at, next.length), 0, undo.row);
      return next;
    });
    setUndo(null);
    setLive("Đã hoàn tác");
  }

  function them() {
    setRows((prev) => [...prev, emptyRow()]);
    setLive("Đã thêm công đoạn mới ở cuối");
    setTimeout(() => {
      const last = tbodyRef.current?.querySelector<HTMLElement>("tr:last-of-type .khsx-rt__open");
      last?.focus();
      last?.scrollIntoView({ block: "nearest" });
    }, 0);
  }

  // `tinhNguoc` / `apDungGoiY` đã BỎ: số lượng mọi bước nay do SERVER tính ngược và ghi thẳng
  // (`_ap_chuoi_nguoc`), nên không còn "gợi ý" nào để đối chiếu rồi bấm áp dụng.

  function moDrawer(i: number, el: HTMLElement | null, tab?: DrawerTabKey) {
    hangMo.current = el;
    setTabDau(tab);
    setMoBuoc(i);
  }

  function dongDrawer() {
    setMoBuoc(null);
    hangMo.current?.focus();
  }

  function onRowKeyDown(e: KeyboardEvent, idx: number) {
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(idx, e.key === "ArrowUp" ? -1 : 1);
    }
  }

  const flow = useMemo(
    () => rows.map((r) => ({ ten: r.ten || "…", loai_buoc: r.loai_buoc })),
    [rows],
  );
  const tong = useMemo(
    () => rows.reduce(
      (acc, r) => {
        const t = thoiLuong(r, mayRefs?.find((m) => m.id === r.may_id) ?? null);
        // Bước không có dải (tổ / thuê ngoài / máy chưa khai min-max) góp CÙNG một số vào cả
        // hai đầu ⇒ chúng không làm khoảng rộng ra một cách giả tạo.
        return {
          chiemMay: acc.chiemMay + t.chiemMay,
          tong: acc.tong + t.tong,
          min: acc.min + t.chiemMin,
          max: acc.max + t.chiemMax,
          coDai: acc.coDai || t.coDai,
        };
      },
      { chiemMay: 0, tong: 0, min: 0, max: 0, coDai: false },
    ),
    [rows],
  );
  const soNgay = tong.tong / 60 / 8;
  const conLai = leadTime?.ngay_con_lai ?? null;
  const treHan = conLai != null && soNgay > conLai;
  const soNgoai = rows.filter((r) => r.loai_buoc === "thue_ngoai").length;
  // Chỉ hỏi lý do khi routing đã khác CẤU TRÚC ban đầu (thêm/bớt/đổi thứ tự/đổi loại bước) —
  // sửa số lượng hay thời gian là việc thường ngày, hỏi lý do mỗi lần là phiền vô ích.
  const doiCauTruc = useMemo(() => {
    const van = (cd: { ten: string; loai_buoc: string }) => `${cd.ten}|${cd.loai_buoc}`;
    return JSON.stringify(congDoans.map(van)) !== JSON.stringify(rows.map(van));
  }, [congDoans, rows]);

  return (
    <div className="khsx-rt">
      <div className="khsx-rt__bar">
        <div>
          <h3 className="khsx-rt__title">Chuỗi công đoạn ({rows.length})</h3>
          <p className="khsx-rt__origin">kế thừa từ bài tính giá · sửa được tại lệnh này</p>
        </div>

        <div className="dag-view-switch">
          <button
            type="button"
            className={`dag-view-switch__btn ${viewMode === "dag" ? "dag-view-switch__btn--active" : ""}`}
            onClick={() => setViewMode("dag")}
          >
            <Icon name="workflow" size={14} /> Sơ đồ DAG
          </button>
          <button
            type="button"
            className={`dag-view-switch__btn ${viewMode === "table" ? "dag-view-switch__btn--active" : ""}`}
            onClick={() => setViewMode("table")}
          >
            <Icon name="table" size={14} /> Bảng danh sách
          </button>
        </div>

        {canUpdate && (
          <div className="khsx-rt__baracts">
            <Button variant="secondary" onClick={them}>
              <Icon name="plus" size={14} /> Thêm công đoạn
            </Button>
            <Button
              variant="accent"
              disabled={!dirty}
              loading={saving}
              onClick={() => onSave(toBody(rows), doiCauTruc ? lyDo : undefined)}
            >
              Lưu công đoạn
            </Button>
          </div>
        )}
      </div>

      {/* Lệnh đang ghép chung tờ: quyền quyết định về TỜ đã chuyển sang bài. Nói ra ở đây, không
          để người kế hoạch sửa máy in rồi tưởng có tác dụng. */}
      {baiGhep && (
        <div className="khsx-ghep-bang">
          <Icon name="layers" size={14} />
          <span>
            Bước in do bài ghép <strong>{baiGhep.ma}</strong> điều phối —{" "}
            {baiGhep.may_ten ? `chạy máy ${baiGhep.may_ten}` : "chưa chọn máy"} ·{" "}
            {baiGhep.so_con_tren_to} {dvChuoi.tp}/{dvChuoi.to}
            {baiGhep.kho_in_dai && baiGhep.kho_in_rong
              ? ` · khổ ${baiGhep.kho_in_dai}×${baiGhep.kho_in_rong}`
              : ""}
            . Máy, giấy, khổ {dvChuoi.to} và số {dvChuoi.tp} sửa tại bài.
          </span>
        </div>
      )}

      <div className="khsx-rt__flow">
        <ChuoiCongDoan steps={flow} />
      </div>

      {viewMode === "dag" ? (
        <DagRoutingCanvas
          rows={rows}
          congDoanRefs={congDoanRefs}
          toRefs={toRefs}
          mayRefs={mayRefs}
          vatTuRefs={vatTuRefs}
          phuThuocRefs={phuThuocRefs}
          baiGhep={baiGhep}
          canUpdate={canUpdate}
          onUpdateRows={setRows}
          onOpenDrawer={(idx, tab) => moDrawer(idx, null, tab)}
          onAddStep={them}
        />
      ) : (
        <div className="khsx__tablewrap">
        <table className="khsx-rt__table">
          <caption className="sr-only">
            Danh sách công đoạn của lệnh. Bấm một hàng để mở chi tiết bước.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="khsx-rt__thord">#</th>
              <th scope="col">Công đoạn</th>
              <th scope="col">Thực hiện</th>
              <th scope="col" className="khsx-th--num">Vào → Ra</th>
              <th scope="col" className="khsx-th--num">Thời lượng</th>
              <th scope="col">Tiền nhiệm</th>
              <th scope="col">Cần xem lại</th>
              <th scope="col"><span className="sr-only">Thao tác</span></th>
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <div className="khsx-empty khsx-empty--inline">
                    <Icon name="workflow" size={32} />
                    <p className="khsx-empty__title">Chưa có công đoạn nào.</p>
                    <p className="khsx-empty__sub">
                      Bài tính giá không có công đoạn, hoặc đã xoá hết. Thêm ít nhất 1 công đoạn thì
                      lệnh mới sẵn sàng lập kế hoạch.
                    </p>
                    {canUpdate && (
                      <Button variant="secondary" onClick={them}>
                        <Icon name="plus" size={14} /> Thêm công đoạn
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const meta = LSX_LOAI_BUOC_META[r.loai_buoc];
              const t = thoiLuong(r, mayRefs?.find((m) => m.id === r.may_id) ?? null);
              const loi = loiDong(rows, i);
              const ngoai = r.loai_buoc === "thue_ngoai";
              const lamO = ngoai
                ? r.nha_cung_cap || "chưa có nhà gia công"
                : [toRefs?.find((x) => x.id === r.department_id)?.ten,
                   mayRefs?.find((x) => x.id === r.may_id)?.ten]
                    .filter(Boolean).join(" · ");
              return (
                <tr
                  key={r.key}
                  className={`khsx-rt__row khsx-rt__row--${meta.tone} ${keo === i ? "is-keo" : ""}`}
                  draggable={canUpdate}
                  onDragStart={() => setKeo(i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (keo != null) doiCho(keo, i);
                    setKeo(null);
                  }}
                  onDragEnd={() => setKeo(null)}
                  onKeyDown={(e) => onRowKeyDown(e, i)}
                >
                  <td>
                    <span className="khsx-rt__ord khsx-num">{(i + 1) * 10}</span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="khsx-rt__open"
                      onClick={(e) => moDrawer(i, e.currentTarget)}
                    >
                      <span className="khsx-rt__ten">{r.ten || "— chưa chọn công đoạn —"}</span>
                      <span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>
                      {!r.bat_buoc && <span className="khsx-lb khsx-lb--opt">tùy chọn</span>}
                    </button>
                  </td>
                  <td>
                    <span className={lamO ? "" : "khsx-muted"}>{lamO || "tổ mặc định"}</span>
                    {r.so_nhan_cong && n(r.so_nhan_cong) > 1 && (
                      <span className="khsx-rt__sub2">Kế hoạch {r.so_nhan_cong} người</span>
                    )}
                    {/* Hàng gửi ra ngoài đang ở đâu — bấm là nhảy thẳng vào sổ giao–nhận. Badge
                        chỉ để NHÌN và NHẢY: một cửa ghi duy nhất, nằm trong drawer. */}
                    {ngoai && r.giao_nhan && (
                      <button
                        type="button"
                        className={`khsx-gn-badge khsx-gn-badge--${r.giao_nhan.giao_nhan_trang_thai ?? "chua_gui"} ${
                          (r.giao_nhan.qua_han_ngay ?? 0) > 0 || r.giao_nhan.hut_vuot_dinh_muc
                            ? "is-canhbao"
                            : ""
                        }`}
                        onClick={(e) => moDrawer(i, e.currentTarget, "giao_nhan")}
                      >
                        {nhanGiaoNhan(r)}
                      </button>
                    )}
                  </td>
                  <td className="khsx-rt__qty">
                    {r.nhom === "prepress" || (!r.don_vi_vao && !r.don_vi_ra) ? (
                      <span className="khsx-muted">—</span>
                    ) : (
                      <>
                        <span className="khsx-num">{num(n(r.so_luong_vao))}</span>
                        <span className="khsx-rt__dv">{dvNhan(r.don_vi_vao, r)}</span>
                        <span className="khsx-rt__arrow" aria-label="ra">→</span>
                        <span className="khsx-num">{num(n(r.so_luong_ra))}</span>
                        <span className="khsx-rt__dv">{dvNhan(r.don_vi_ra, r)}</span>
                        {/* Bước ĐỔI ĐƠN VỊ: nói luôn hệ số, không thì "59 tờ in → 5.201 con" là số
                            từ trên trời (59 × 180 = 10.620, không phải 5.201 — chuỗi đi NGƯỢC).
                            `heSoChu` LẬT lại khi hệ số < 1 (sách gấp tay) → "10 Tờ in = 1 Thành
                            phẩm" thay vì "1 Tờ in = 0,1 Thành phẩm". */}
                        {heSoChu(n(r.he_so_quy_doi) || 1, r.don_vi_vao, r.don_vi_ra) && (
                          <span className="khsx-rt__sub2">
                            {heSoChu(n(r.he_so_quy_doi) || 1, r.don_vi_vao, r.don_vi_ra)}
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td className="khsx-rt__time">
                    <span className="khsx-dur">{phut(t.chiemMay)}</span>
                    {t.coDai && (
                      <span className="khsx-rt__sub2 khsx-rt__dai" title="Nhanh nhất – chậm nhất theo dải tốc độ của máy">
                        {phut(t.chiemMin)} – {phut(t.chiemMax)}
                      </span>
                    )}
                    {t.tong !== t.chiemMay && (
                      <span className="khsx-rt__sub2">bước sau bắt đầu sau {phut(t.tong)}</span>
                    )}
                  </td>
                  <td>
                    {r.phu_thuoc_step_keys.length ? (
                      <span className="khsx-need-stack">
                        {r.phu_thuoc_step_keys.slice(0, 2).map((k) => (
                          <span key={k} className="khsx-need khsx-need--soft">
                            {rows.find((x) => x.key === k)?.ten ?? "Bước LSX khác"}
                          </span>
                        ))}
                        {r.phu_thuoc_step_keys.length > 2 && <span className="khsx-need">+{r.phu_thuoc_step_keys.length - 2}</span>}
                      </span>
                    ) : <span className="khsx-muted">Gốc / song song</span>}
                  </td>
                  <td>
                    {loi.length === 0 ? (
                      <span className="khsx-muted">—</span>
                    ) : (
                      <span className="khsx-need-stack">
                        {loi.slice(0, 2).map((l) => (
                          <span key={l} className="khsx-need khsx-need--soft">
                            <Icon name="help" size={10} /> {l}
                          </span>
                        ))}
                        {loi.length > 2 && (
                          <span className="khsx-need khsx-need--more" title={loi.join(" · ")}>
                            +{loi.length - 2}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  {/* Không vẽ tay cầm kéo bằng ký tự ⠿: nó là glyph chữ lạc giữa bộ icon Lucide
                      của app. Cả hàng đã `cursor: grab` để kéo, còn đổi thứ tự vẫn làm được bằng
                      nút ▲▼ và Alt+↑↓ — rõ ràng hơn và dùng được bàn phím. */}
                  <td>
                    {canUpdate && (
                      <div className="khsx-rt__acts">
                        <button
                          type="button"
                          className="khsx-rt__btn khsx-rt__btn--up"
                          disabled={i === 0}
                          onClick={() => move(i, -1)}
                          aria-label={`Chuyển bước ${i + 1} lên`}
                        >
                          <Icon name="chevron" size={14} />
                        </button>
                        <button
                          type="button"
                          className="khsx-rt__btn"
                          disabled={i === rows.length - 1}
                          onClick={() => move(i, 1)}
                          aria-label={`Chuyển bước ${i + 1} xuống`}
                        >
                          <Icon name="chevron" size={14} />
                        </button>
                        <button
                          type="button"
                          className="khsx-rt__btn khsx-rt__btn--del"
                          onClick={() => remove(i)}
                          aria-label={`Bỏ bước ${i + 1}`}
                        >
                          <Icon name="trash" size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      )}

      {undo && (
        <div className="khsx-rt__undo">
          <span>Đã bỏ “{undo.row.ten || "công đoạn"}”</span>
          <button type="button" className="khsx-xlink" onClick={hoanTac}>
            Hoàn tác
          </button>
        </div>
      )}

      {rows.length > 0 && (
        <div className={`khsx-lead ${treHan ? "khsx-lead--tre" : ""}`}>
          <div className="khsx-lead__main">
            <span className="khsx-lead__label">Tổng thời gian dẫn</span>
            <strong className="khsx-lead__val khsx-dur">{phut(tong.tong)}</strong>
            <span className="khsx-lead__note">
              ≈ {soNgay.toFixed(1)} ngày làm việc · chiếm máy {phut(tong.chiemMay)}
              {tong.coDai && <> · nhanh–chậm {phut(tong.min)} – {phut(tong.max)}</>}
            </span>
          </div>
          <div className="khsx-lead__side">
            {leadTime?.ngay_du_kien_xong && !dirty && (
              <span>Dự kiến xong {ngay(leadTime.ngay_du_kien_xong)}</span>
            )}
            {conLai != null && (
              <span className={treHan ? "khsx-lead__warn" : ""}>
                {treHan
                  ? `Vượt hạn giao khách — chỉ còn ${conLai} ngày`
                  : `Còn ${conLai} ngày tới hạn giao khách`}
              </span>
            )}
            {soNgoai > 0 && <span>{soNgoai} bước thuê ngoài</span>}
          </div>
        </div>
      )}

      {canUpdate && doiCauTruc && (
        <label className="khsx-lydo">
          <span className="khsx-field__label">
            Routing đã khác bài tính giá — ghi lý do để lưu vào nhật ký
          </span>
          <input
            value={lyDo}
            placeholder="vd: khách đổi sang cán màng thuê ngoài"
            onChange={(e) => setLyDo(e.target.value)}
          />
        </label>
      )}

      <div className="khsx-rt__foot">
        <p className="khsx-rt__summary">
          {rows.length} công đoạn
          {soNgoai > 0 && ` · ${soNgoai} thuê ngoài`}
        </p>
        {canUpdate && (
          <Button
            variant="accent"
            disabled={!dirty}
            loading={saving}
            onClick={() => onSave(toBody(rows), doiCauTruc ? lyDo : undefined)}
          >
            Lưu công đoạn
          </Button>
        )}
      </div>

      <p className="sr-only" aria-live="polite">{live}</p>

      {moBuoc != null && rows[moBuoc] && (
        <LsxBuocDrawer
          row={rows[moBuoc]}
          index={moBuoc}
          tong={rows.length}
          soLuongDat={soLuongDat}
          buHaoThem={buHaoThem}
          congDoanRefs={congDoanRefs}
          toRefs={toRefs}
          mayRefs={mayRefs}
          khuonRefs={khuonRefs}
          vatTuRefs={vatTuRefs}
          phuThuocRefs={phuThuocRefs}
          baiGhep={baiGhep}
          dvChuoi={dvChuoi}
          canUpdate={canUpdate}
          onPatch={(p) => patch(rows[moBuoc].key, p)}
          onPatchLsx={onPatchLsx}
          onDoiCongDoan={(id) => doiCongDoan(rows[moBuoc].key, id, rows[moBuoc].ten)}
          onDoiTo={(id) => doiTo(rows[moBuoc].key, id)}
          onGiaoNhan={onGiaoNhan}
          tabDau={tabDau}
          onClose={dongDrawer}
          onPrev={() => setMoBuoc(Math.max(moBuoc - 1, 0))}
          onNext={() => setMoBuoc(Math.min(moBuoc + 1, rows.length - 1))}
        />
      )}
    </div>
  );
}
