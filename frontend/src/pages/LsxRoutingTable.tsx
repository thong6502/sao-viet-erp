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
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
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
import { nhanTram, tenDonVi, useNapTenDonVi } from "./tenDonVi";
import {
  boBuoc,
  chenBuoc,
  type DonViChuoi,
  type EditRow,
  emptyRow,
  heSoChu,
  loiDong,
  n,
  phut,
  tenBuoc,
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
  /** CÔNG ĐOẠN — nhóm máy (loai_may) làm được công đoạn này, để drawer LỌC dropdown máy. Chỉ có
   *  trên ref CÔNG ĐOẠN (congDoanRefs), không phải ref máy. null/rỗng = không giới hạn.
   *  Nay chỉ là tầng LÙI: `mayChoPhep` ngay dưới thắng khi công đoạn đã khai máy cụ thể. */
  nhomMayChoPhep?: string[] | null;
  /** CÔNG ĐOẠN — id các máy ở bảng "Máy chạy được công đoạn này" của danh mục Công đoạn.
   *  null/rỗng = công đoạn chưa khai máy nào, lùi về `nhomMayChoPhep`. */
  mayChoPhep?: number[] | null;
}

/** Nhãn đơn vị CỦA MỘT BƯỚC. Chưa khai đơn vị ⇒ “—”.
 *
 *  `don_vi_vao/ra` giữ MÃ CHẶNG dòng giấy (`to_nguyen · to · con · tay · cai`) nên tra bảng CHẶNG
 *  trước (`/api/don-vi/tram`), rồi mới tới danh mục Đơn vị cho bước NGOÀI dòng giấy (`m²`, `kem`).
 *  Đảo thứ tự là `to` đọc ra "tờ" ở đây trong khi màn Công đoạn nói "Tờ in" — cùng một bước, hai
 *  chữ. Chưa nạp xong ⇒ rơi về MÃ TRẦN, không bịa tên.
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
  if (dv) return nhanTram(dv) ?? tenDonVi(dv) ?? dv;
  return "—";
}

/** Lỗi/nghi vấn của RIÊNG 1 dòng — chỉ tô màu, không chặn lưu. */
export function LsxRoutingTable({
  congDoans,
  soLuongDat,
  leadTime,
  baiGhep,
  congDoanRefs,
  toRefs,
  mayRefs,
  khuonRefs,
  tenSanPham,
  tenKhach,
  onTaoKhuon,
  vatTuRefs,
  giayRefs,
  phuThuocRefs,
  canUpdate,
  giuCho,
  saving,
  onSave,
  onPatchLsx,
  onMacDinhBuoc,
  onDauViecOptions,
  onXemTruocBuoc,
  onXemTruocRouting,
  onDirtyChange,
  dvChuoi,
}: {
  congDoans: LsxCongDoan[];
  soLuongDat: number;
  leadTime: LsxLeadTime | null;
  /** Lệnh đang ghép chung tờ → thông số tờ do BÀI quyết, bước in khoá lại ở màn này. */
  baiGhep: import("../api/client").LsxBaiGhep | null;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  khuonRefs: import("../api/client").KhuonChonDuoc[] | null;
  /** Tên sản phẩm của lệnh — mặc định cho tên dao mới. */
  tenSanPham: string;
  /** Tên khách của lệnh — khối Khuôn của drawer bày ra để nói rõ đang lọc dao theo ai. */
  tenKhach: string;
  onTaoKhuon: (input: { ten: string; loai: string | null; ngay_ve: string }) => Promise<number>;
  vatTuRefs: RefRow[] | null;
  /** Danh mục GIẤY — NVL chính chọn tay ở bước (08/09/2026). Đi RIÊNG với `vatTuRefs` vì hai
   *  danh mục đánh số độc lập. */
  giayRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  canUpdate: boolean;
  /** Lệnh đang GIỮ CHỖ vật tư → server chặn MỌI đường ghi routing, kể cả bản xem trước. */
  giuCho: boolean;
  saving: boolean;
  onSave: (body: LsxCongDoanBody[], lyDo?: string) => void;
  /** Sửa cấp LỆNH từ drawer bước cuối (SL thành phẩm / hao thêm) → server tính lại cả chuỗi. */
  onPatchLsx: (p: { so_luong_dat?: number }) => void;
  onMacDinhBuoc: (congDoanId: number) => Promise<LsxBuocMacDinh>;
  onDauViecOptions: (
    congDoanId: number, departmentId: number,
  ) => Promise<import("../api/client").LsxDauViecOption[]>;
  /** Sửa bước → hỏi server giờ chạy + tiền công mới (chỉ backend quy đổi được SL vào sang đơn vị
   *  đích của bước, và chỉ nó chạy được công thức tiền công). */
  onXemTruocBuoc: (
    stepKey: string,
    dang: { mayId?: number | null; loaiBuoc?: string | null;
            pieceRateId?: number | null; soLuotChay?: number | null },
  ) => Promise<import("../api/client").LsxXemTruocBuoc>;
  /** Đổi/chèn công đoạn → hỏi server SỐ VÀO–RA + đơn vị của CẢ CHUỖI (chỉ backend chạy chuỗi
   *  ngược + bảng cầu quy đổi). Cùng lẽ với `onXemTruocBuoc`: số nhảy ngay, khỏi bấm Lưu. */
  onXemTruocRouting: (
    rows: import("../api/client").LsxXemTruocRoutingRow[],
  ) => Promise<import("../api/client").LsxXemTruocRoutingBuoc[]>;
  onDirtyChange: (dirty: boolean) => void;
  /** Đơn vị bốn chặng của lệnh — SERVER chấm, cha truyền xuống. Bảng KHÔNG tự suy lại từ `rows`:
   *  luật suy chặng chỉ có một bản, ở `dong_giay.don_vi_chuoi`. Đánh đổi: đổi công đoạn của một
   *  bước thì nhãn ở băng bài ghép cập nhật sau khi bấm Lưu, không tức thì. */
  dvChuoi: DonViChuoi;
}) {
  // Nhãn đơn vị đọc từ DANH MỤC — nạp một lần cho cả phiên. Hook ở ĐÂY (gốc của bảng + DAG +
  // drawer) nên mọi chỗ gọi `dvNhan` vẽ lại khi danh mục về, khỏi phải truyền prop qua 22 chỗ.
  useNapTenDonVi();
  // Quyền sửa THẬT = có quyền update VÀ lệnh không đang giữ chỗ vật tư. Tách khỏi `canUpdate` để
  // giữ được LÝ DO: hết quyền thì im lặng ẩn nút, còn giữ chỗ thì phải nói ra + chỉ đường lùi.
  // Backend `_chan_dang_giu_cho` chặn cả `PUT /routing` lẫn `POST /xem-truoc-routing`, nên để
  // bảng sửa được lúc này là mời người ta làm không công: mỗi lần đổi công đoạn ăn một 409 câm,
  // số vào–ra đứng im, tới khi bấm Lưu mới hiện băng đỏ.
  const suaDuoc = canUpdate && !giuCho;
  const [rows, setRows] = useState<EditRow[]>(() => congDoans.map(toEdit));
  const [viewMode, setViewMode] = useState<"dag" | "table">("dag");
  const [undo, setUndo] = useState<
    { row: EditRow; at: number; truoc: EditRow[] } | null>(null);
  const [live, setLive] = useState("");
  // Câu báo cho lần ĐỔI CÔNG ĐOẠN gần nhất hỏng dở — cả hai chặng của nó (lấy mặc định của công
  // đoạn, tính lại số cả chuỗi) đều do SERVER làm, hỏng chặng nào thì bảng cũng đang hiện số/nhãn
  // CŨ mà nhìn y như vừa cập nhật. Nuốt im lặng là để màn nói dối: đúng cách lỗi 500 của
  // `mac-dinh-buoc` và 409 của `xem-truoc-routing` sống được lâu đến thế.
  const [loiDoiCd, setLoiDoiCd] = useState<string | null>(null);
  const [moBuoc, setMoBuoc] = useState<number | null>(null);
  const [tabDau, setTabDau] = useState<DrawerTabKey | undefined>(undefined);
  const [keo, setKeo] = useState<number | null>(null);
  const [lyDo, setLyDo] = useState("");
  const goc = useRef(JSON.stringify(toBody(congDoans.map(toEdit))));
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const doiToSeq = useRef(0);
  const doiMaySeq = useRef(0);
  const doiCdSeq = useRef(0);
  // Ảnh chụp `rows` mới nhất cho xem-trước chuỗi: `doiCongDoan` vừa `patch` xong thì closure `rows`
  // còn CŨ, nên dựng payload từ ref này (đã cộng patch tay) mới đúng bước vừa đổi.
  const rowsRef = useRef(rows);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);
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

  /** Dựng payload xem-trước cho CẢ CHUỖI rồi khớp số server trả về theo `step_key`.
   *
   *  Gửi `r.key` cho MỌI bước — kể cả bước chưa lưu ("r…") — vì server echo lại chính key đó để FE
   *  khớp hàng (khác `toBody`, chỗ CỐ Ý bỏ key "r"). Chốt `seq` để phản hồi tới trễ không đè phản
   *  hồi mới hơn, giống lá chắn của `doiMay`. Server KHÔNG ghi DB — chỉ tính rồi rollback. */
  const xemTruocChuoi = useCallback(
    async (snapshot: EditRow[]) => {
      const seq = ++doiCdSeq.current;
      const payload = snapshot.map((r, i) => ({
        step_key: r.key,
        thu_tu: i,
        cong_doan_id: r.cong_doan_id,
        ten: r.ten || undefined,
        nhom: r.nhom,
        loai_buoc: r.loai_buoc,
        department_id: r.department_id,
        may_id: r.may_id,
        // Số lượng chạy theo `thu_tu` (thứ tự bảng), KHÔNG theo cạnh phụ thuộc — nên không gửi
        // `phu_thuoc_step_keys` (gửi vào chỉ tổ chạm guard tiền-nhiệm của replace_routing lúc vẽ
        // dở). Bước chèn giữa ra đúng số là nhờ nó nằm đúng vị trí `thu_tu` (chèn đúng chỗ khi thêm).
      }));
      try {
        const buocs = await onXemTruocRouting(payload);
        if (seq !== doiCdSeq.current) return;
        setLoiDoiCd(null);
        setRows((prev) =>
          prev.map((r) => {
            const b = buocs.find((x) => x.step_key === r.key);
            if (!b) return r;
            return {
              ...r,
              // Số + đơn vị là DẪN XUẤT (server chạy chuỗi ngược). 0 → "" để ô hiện gợi ý, khớp
              // đúng cách `toEdit` nạp số ban đầu.
              so_luong_vao: b.so_luong_vao ? String(b.so_luong_vao) : "",
              so_luong_ra: b.so_luong_ra ? String(b.so_luong_ra) : "",
              don_vi_vao: b.don_vi_vao ?? r.don_vi_vao,
              don_vi_ra: b.don_vi_ra ?? r.don_vi_ra,
              he_so_quy_doi: b.he_so_quy_doi > 1 ? String(b.he_so_quy_doi) : "",
              hao_hut: b.hao_hut ? String(b.hao_hut) : "",
              hao_hut_pct: b.hao_hut_pct ? String(b.hao_hut_pct) : "",
              don_vi_san_luong: b.don_vi_san_luong || "",
              tren_dong_giay: b.tren_dong_giay,
              loi_quy_doi: b.loi_quy_doi,
              san_luong_dien_giai: b.san_luong_dien_giai,
              // Số vừa tính = số chuẩn hiện tại ⇒ xoá cờ "danh mục đã đổi" để bảng khỏi gạch số cũ.
              so_luong_vao_moi: null,
              so_luong_ra_moi: null,
            };
          }),
        );
      } catch (e: unknown) {
        // KHÔNG nuốt. Hỏng thì số vào–ra trên bảng vẫn là số của công đoạn TRƯỚC khi đổi, mà
        // người dùng không có cách nào biết. Đúng cách 409 "lệnh đang giữ chỗ vật tư" chạy ngầm
        // mỗi lần đổi công đoạn suốt một thời gian: bảng im, tới lúc bấm Lưu mới hiện băng đỏ.
        if (seq !== doiCdSeq.current) return;
        setLoiDoiCd(
          `Chưa tính lại được số vào–ra của chuỗi: ${e instanceof Error ? e.message : String(e)}`
          + " — số đang hiện là số CŨ, bấm Lưu server sẽ chốt lại theo cách của nó.");
      }
    },
    [onXemTruocRouting],
  );

  /** Nạp đầu việc khoán cho cặp (công đoạn, tổ) rồi áp vào bước: đúng MỘT đầu việc thì điền sẵn,
   *  từ hai trở lên để TRỐNG cho người lập lệnh chọn theo hàng. Luật khớp phải trùng
   *  `lsx_service._khoan_mac_dinh` — lệch là FE điền một đằng, backend gate một nẻo.
   *
   *  Dùng CHUNG cho đổi TỔ và đổi CÔNG ĐOẠN: cả hai đều đổi tập đầu việc hợp lệ nên chỉ được có
   *  MỘT bản luật nạp. `seq` chốt qua `doiToSeq` để phản hồi tới trễ không đè lần đổi mới hơn. */
  const napDauViec = useCallback(
    async (key: string, congDoanId: number | null, departmentId: number | null, seq: number) => {
      if (!departmentId || !congDoanId) return;
      try {
        const options = await onDauViecOptions(congDoanId, departmentId);
        if (seq !== doiToSeq.current) return;
        const chosen = options.length === 1 ? options[0] : null;
        patch(key, {
          khoan_chon_duoc: options,
          khoan_rate_id: chosen?.id ?? null,
          nang_suat: chosen ? String(chosen.nang_suat_nguoi_gio) : "",
          don_vi_nang_suat: chosen?.don_vi_nang_suat ?? "",
          so_nhan_cong_tieu_chuan: chosen?.so_nguoi_tieu_chuan ?? 1,
        });
        setLive(options.length
          ? `Đã nạp ${options.length} đầu việc khoán`
          : "Công đoạn/tổ này chưa gắn đầu việc khoán");
      } catch {
        if (seq === doiToSeq.current) setLive("Không tải được bảng khoán");
      }
    },
    [onDauViecOptions, patch],
  );

  /** Đổi công đoạn của 1 bước → kéo lại dữ liệu trung tính của công đoạn (tổ phụ trách, đơn vị,
   *  chuẩn bị). Loại bước và tài nguyên vẫn là quyết định của kế hoạch tại chính bước LSX.
   *
   *  Không làm việc này thì bước đổi xong vẫn đeo nguyên số của công đoạn CŨ — đổi "Dán hộp" (tổ,
   *  đếm con, 4.000 con/giờ) sang "Cán màng" (máy, đếm tờ) mà thời lượng và đơn vị vẫn của Dán hộp,
   *  chẳng cảnh báo gì.
   *
   *  Số VÀO–RA + đơn vị của cả chuỗi thì hỏi server xem-trước (`xemTruocChuoi`) cho nhảy NGAY —
   *  chỉ backend chạy được chuỗi ngược + bảng cầu quy đổi; bấm "Lưu công đoạn" server chốt lại y
   *  hệt. Luật đơn vị nằm ở BACKEND, FE chỉ áp kết quả để hai nơi không trôi khỏi nhau. */
  const doiCongDoan = useCallback(
    async (key: string, id: number | null, tenHienTai: string) => {
      if (id == null) {
        patch(key, { cong_doan_id: null });
        return;
      }
      // Đổi công đoạn ⇒ đổi cả tổ mặc định ⇒ tập đầu việc khoán hợp lệ đổi theo. Chốt seq NGAY để
      // chặn phản hồi nạp-đầu-việc tới trễ đè lên lần đổi mới hơn (`napDauViec` so `doiToSeq`).
      const seq = ++doiToSeq.current;
      try {
        const m = await onMacDinhBuoc(id);
        const rowCu = rowsRef.current.find((r) => r.key === key);
        const loaiCu = rowCu?.tooling_type ?? null;
        // Máy GỢI Ý: chỉ điền khi dòng đang TRỐNG máy và không phải bước tổ. Cách đo giờ chạy và
        // tốc độ đều treo ở cặp (công đoạn × máy), nên bước trống máy thì bảng bóc tách thời gian
        // ra "—" mãi. Công đoạn khai đúng một máy còn dùng thì không có gì để đoán sai — server
        // quyết (`may_id_goi_y`), client không tự dò danh mục. KHÔNG đè máy người ta đã chọn.
        const mayGoiY =
          m.may_id_goi_y != null && rowCu?.loai_buoc !== "to" && !rowCu?.may_id
            ? { may_id: m.may_id_goi_y }
            : {};
        const applied: Partial<EditRow> = {
          ...mayGoiY,
          cong_doan_id: m.cong_doan_id, ten: m.ten, nhom: m.nhom,
          department_id: m.department_id,
          don_vi_vao: m.don_vi_vao, don_vi_ra: m.don_vi_ra,
          // Cờ dòng giấy đi CÙNG cặp đơn vị — nó là thuộc tính của cặp đó, không phải của dòng.
          // Giữ cờ cũ là bước vừa đổi sang ghi kẽm (`m² → bài in`) vẫn bị đem so đơn vị với bước
          // in ngay sau, tức đúng cảnh báo giả vừa sửa nhưng sống lại lúc người dùng đang sửa.
          tren_dong_giay: m.tren_dong_giay !== false,
          // Cờ DỤNG CỤ đi cùng công đoạn mới. Giữ cờ cũ là thẻ "Khuôn của bước" vẫn xưng loại của
          // công đoạn CŨ và ô chọn lọc kho theo loại đó — đổi Bế sang bước cần khung lụa thì vẫn
          // chỉ thấy dao bế. `khuon_be_id` PHẢI reset theo: con dao đang gán là của công đoạn cũ,
          // giữ lại là bước mang dao sai loại xuống xưởng.
          requires_tooling: !!m.requires_tooling,
          tooling_type: m.tooling_type ?? null,
          ...((m.tooling_type ?? null) === loaiCu ? {} : {
            khuon_be_id: null, khuon_be_ma: null, khuon_be_ten: null,
            khuon_be_so_ke: null, khuon_be_tinh_trang: null, khuon_be_ngay_ve: null,
          }),
          he_so_quy_doi: m.he_so_quy_doi > 1 ? String(m.he_so_quy_doi) : "",
          // RESET khoán: giữ `khoan_rate_id` cũ thì nó trỏ đầu việc của công đoạn CŨ → lưu thì backend
          // tự GỠ nó như đầu việc mồ côi + báo lưu ý (không chặn nữa). Reset ngay ở đây để luồng đổi
          // công đoạn thông thường KHỎI dính lưu ý đó; `napDauViec` ngay dưới điền lại đầu việc đúng
          // của công đoạn mới (đúng 1 thì tự chọn) — cùng một bản luật nạp khoán.
          khoan_rate_id: null, khoan_chon_duoc: [], khoan_dien_giai: null, khoan_ly_do: null,
          nang_suat: "", don_vi_nang_suat: "",
          so_nhan_cong_tieu_chuan: 1,
          // Thời gian chuẩn bị + chạy KHÔNG còn nằm ở bước: kế thừa sống từ máy đang gán.
        };
        patch(key, applied);
        setLive(`Đã đổi sang ${m.ten} và lấy lại đơn vị, tổ phụ trách`
          + ("may_id" in mayGoiY ? ", điền sẵn máy duy nhất của công đoạn" : ""));
        // Số vào–ra + đơn vị cả chuỗi phải nhảy NGAY (chủ 20/08/2026). Dựng ảnh chụp từ `rowsRef`
        // (đã cộng patch vừa áp) vì closure `rows` ở nhịp này còn CŨ, chưa thấy bước vừa đổi.
        const snapshot = rowsRef.current.map(
          (r) => (r.key === key ? { ...r, ...applied } : r));
        void xemTruocChuoi(snapshot);
        // Nạp lại đầu việc khoán theo (công đoạn mới, tổ mới) — đúng 1 thì điền sẵn, khỏi mất khoán.
        void napDauViec(key, m.cong_doan_id, m.department_id, seq);
      } catch (e: unknown) {
        // Mất mạng / không có quyền đọc danh mục → ít nhất vẫn đổi được tên, đừng chặn người dùng.
        // Tên lấy từ ref danh mục đang có sẵn trên màn, KHÔNG giữ `tenHienTai`: giữ tên cũ là bước
        // mang `cong_doan_id` mới mà nhãn vẫn của công đoạn cũ (hoặc nhãn tạm "Công đoạn") — đúng
        // cách dữ liệu trơ chữ "Công đoạn" đã sinh ra khi endpoint mặc-định-bước lỗi.
        patch(key, {
          cong_doan_id: id,
          ten: congDoanRefs?.find((c) => c.id === id)?.ten ?? tenHienTai,
          department_id: null,
        });
        // Và NÓI RA: bước vừa đổi mới có mỗi cái tên, đơn vị/tổ/khoán vẫn là của công đoạn cũ.
        // Im lặng ở đây chính là thứ đã biến lỗi 500 của `mac-dinh-buoc` thành dữ liệu hỏng lặng lẽ.
        setLoiDoiCd(
          `Chưa lấy được mặc định của công đoạn: ${e instanceof Error ? e.message : String(e)}`
          + " — bước mới chỉ đổi được TÊN, đơn vị và tổ phụ trách chưa lấy lại.");
      }
    },
    [onMacDinhBuoc, napDauViec, patch, xemTruocChuoi, congDoanRefs],
  );

  /** Đổi máy là LẤY SỐ NGAY, không đợi bấm "Lưu công đoạn" (chủ 20/08/2026: *"khi chọn máy là
   *  phải lấy số luôn chứ"*). Ở đây chỉ còn NỬA TẠI CHỖ (không chờ mạng): tốc độ + chuẩn bị thì
   *  `thoiLuongLive` đọc thẳng `mayRefs` nên tự nhảy. Nửa HỎI SERVER dời sang hiệu ứng
   *  `lamMoiXemTruoc` bên dưới — máy không phải thứ duy nhất làm ảnh chụp server hết hạn. */
  const doiMay = useCallback((key: string, mayId: number | null) => {
    const may = mayRefs?.find((m) => m.id === mayId) ?? null;
    // ĐỔI MÁY KHÔNG ĐỔI SỐ NGƯỜI (06/09/2026, mg `0270`): máy không còn khai kíp riêng, kíp của
    // mọi loại bước đến từ định mức đầu việc của công đoạn. Chọn máy chỉ đổi tốc độ + thời gian
    // chuẩn bị; muốn khác người thì sửa thẳng ô kíp trong drawer bước.
    patch(key, { may_id: mayId });
    setLive(may ? `Đã chọn ${may.ten}` : "Đã bỏ máy khỏi bước");
  }, [mayRefs, patch]);

  /** ẢNH CHỤP SERVER của bước đang mở phải theo kịp FORM (vá 07/09/2026).
   *
   *  `thoiLuongLive` là bản LAI: thứ client tính lại được (tốc độ · kíp · số lượt của bước máy) thì
   *  nó tự tính, còn thứ chỉ server biết — SL vào ĐÃ QUY ĐỔI về đơn vị đích, câu diễn giải quy đổi,
   *  và TIỀN CÔNG — thì nó đọc lại ảnh chụp `thoi_luong_dien_giai`. Trước đây ảnh chụp ấy chỉ được
   *  làm mới ở ĐÚNG MỘT chỗ: lúc đổi máy. Nhưng đích quy đổi còn đổi theo LOẠI BƯỚC (máy đo bằng
   *  đơn vị tốc độ của máy, tổ đo bằng đơn vị năng suất của đầu việc) và theo ĐẦU VIỆC, còn tiền
   *  công thì đổi theo SỐ LƯỢT. Hậu quả thấy tận mắt: bấm Máy→Tổ xong, khối "Chạy máy" vẫn bày
   *  công thức của MÁY dưới nhãn Tổ, phải bấm Lưu mới đúng.
   *
   *  Khoá phụ thuộc là CHUỖI các ô server quan tâm, KHÔNG phải cả `row`: `patch` bên dưới ghi
   *  `thoi_luong_dien_giai` vào chính hàng đó, lấy cả hàng làm phụ thuộc là vòng lặp vô tận.
   *  Bước chưa lưu (`id == null`) thì server chưa có `step_key` để tra ⇒ bỏ qua, giữ số cũ.
   */
  const buocMo = moBuoc != null ? rows[moBuoc] : null;
  const khoaXemTruoc = buocMo?.id != null
    ? [buocMo.key, buocMo.loai_buoc, buocMo.may_id ?? "", buocMo.khoan_rate_id ?? "",
       buocMo.so_luot_chay, buocMo.so_luong_vao].join("|")
    : null;
  useEffect(() => {
    if (!khoaXemTruoc) return;
    const [key, loaiBuoc, mayId, rateId, soLuot] = khoaXemTruoc.split("|");
    const seq = ++doiMaySeq.current;
    // Xoá tiền công của bộ số CŨ trước khi hỏi: trong lúc chờ mạng, drawer lùi về số của dropdown
    // đầu việc (đúng đầu việc đang chọn, chỉ chưa tính số lượt) — thà lệch một nhịp còn hơn dán số
    // của lựa chọn trước dưới lựa chọn mới.
    patch(key, { khoan_xem_truoc: null });
    void (async () => {
      try {
        const xt = await onXemTruocBuoc(key, {
          mayId: mayId === "" ? null : Number(mayId),
          loaiBuoc,
          pieceRateId: rateId === "" ? null : Number(rateId),
          soLuotChay: Math.max(Math.trunc(Number(soLuot)) || 1, 1),
        });
        if (seq !== doiMaySeq.current) return;
        patch(key, { thoi_luong_dien_giai: xt.thoi_luong_dien_giai, khoan_xem_truoc: xt.khoan });
      } catch {
        /* mất mạng / không đủ quyền → số giữ nguyên bản cũ, bấm Lưu vẫn ra đúng. */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [khoaXemTruoc]);

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
      // Chụp NGUYÊN mảng trước khi bỏ, không chỉ riêng dòng: `boBuoc` còn sửa `phu_thuoc_step_keys`
      // của các bước sau (bắc cầu qua chỗ trống), nên hoàn tác bằng cách nhét lại một dòng sẽ để
      // lại đúng cái dây đã bị nối tắt.
      setUndo({ row, at: idx, truoc: prev });
      setLive(`Đã bỏ ${row.ten || "công đoạn"}, có thể hoàn tác`);
      return boBuoc(prev, idx);
    });
    setMoBuoc(null);
  }

  function hoanTac() {
    if (!undo) return;
    setRows(undo.truoc);
    setUndo(null);
    setLive("Đã hoàn tác");
  }

  /** Thêm 1 bước. `neoKey` = bước làm mốc (node đang chọn trên sơ đồ DAG), `viTri` = chèn TRƯỚC
   *  hay SAU nó, để `thu_tu` đúng ngay — số lượng + số hiệu bám `thu_tu` nên chèn đúng chỗ là
   *  chúng tự đúng, khỏi "thêm cuối rồi kéo lên". Không truyền `neoKey` ⇒ thêm ở cuối như cũ.
   *
   *  Có "trước" vì bước ĐẦU chuỗi không thể chèn bằng "sau": không có bước nào đứng trước nó để
   *  làm neo. Chế bản / bình bài / ra kẽm luôn phải nhét lên trên bước in đang có sẵn. */
  function them(neoKey?: string, viTri: "truoc" | "sau" = "sau") {
    const at = neoKey ? rows.findIndex((r) => r.key === neoKey) : -1;
    const chen = at < 0 ? -1 : viTri === "truoc" ? at : at + 1;
    // `chenBuoc` chứ không `splice` trần: bước mới phải có dây, không thì sơ đồ DAG hiện nó mồ côi
    // trong khi bảng số vẫn chảy đúng (số bám `thu_tu`, dây bám `phu_thuoc_step_keys`).
    setRows((prev) => chenBuoc(prev, chen < 0 ? prev.length : chen, emptyRow()));
    const tenNeo = at >= 0 ? rows[at]?.ten || `bước ${at + 1}` : null;
    setLive(
      tenNeo
        ? `Đã chèn công đoạn mới ${viTri === "truoc" ? "trước" : "sau"} ${tenNeo}`
        : "Đã thêm công đoạn mới ở cuối",
    );
    setTimeout(() => {
      const rowsEl = tbodyRef.current?.querySelectorAll<HTMLElement>("tr");
      const tr = chen >= 0 ? rowsEl?.[chen] : rowsEl?.[(rowsEl?.length ?? 1) - 1];
      const btn = tr?.querySelector<HTMLElement>(".khsx-rt__open");
      btn?.focus();
      btn?.scrollIntoView({ block: "nearest" });
    }, 0);
  }

  /** Chèn 1 bước NGAY SAU hàng `idx` — khỏi phải "thêm ở cuối rồi kéo lên" cho chuỗi dài (chủ
   *  20/08/2026: muốn nhét 2–4 công đoạn vào GIỮA). Bước mới nằm ở `idx + 1`; đưa tiêu điểm về ô
   *  mở của chính nó để chọn công đoạn liền, và chèn tiếp cũng nhanh. */
  function themTai(idx: number) {
    setRows((prev) => chenBuoc(prev, idx + 1, emptyRow()));
    setLive(`Đã chèn công đoạn mới sau bước ${idx + 1}`);
    setTimeout(() => {
      const tr = tbodyRef.current?.querySelectorAll<HTMLElement>("tr")[idx + 1];
      const btn = tr?.querySelector<HTMLElement>(".khsx-rt__open");
      btn?.focus();
      btn?.scrollIntoView({ block: "nearest" });
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
    () => rows.map((r) => ({ ten: tenBuoc(r, congDoanRefs) || "…", loai_buoc: r.loai_buoc })),
    [rows, congDoanRefs],
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
  // Bước GIAO KHÁCH = bước CUỐI NẰM TRÊN DÒNG GIẤY (đơn vị thành phẩm), KHÔNG phải dòng cuối bảng.
  // Bước bản-kèm/CTP chèn vào giữa (tren_dong_giay=false) có thể xếp cuối theo thứ tự nhưng không
  // giao khách — khớp đúng backend `_canh_bao_don_vi` lấy `buoc[-1]` trong nhóm trên-dòng-giấy.
  const idxBuocGiao = useMemo(() => {
    let idx = -1;
    rows.forEach((r, i) => {
      if (r.tren_dong_giay && r.don_vi_ra) idx = i;
    });
    return idx;
  }, [rows]);
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
          {/* Câu này nói QUYỀN SỬA nên phải theo `suaDuoc`, không thì màn tự cãi nhau: băng khoá
              ngay dưới bảo không sửa được, dòng phụ ngay trên vẫn mời "sửa được tại lệnh này". */}
          <p className="khsx-rt__origin">
            kế thừa từ bài tính giá · {suaDuoc ? "sửa được tại lệnh này" : "chỉ xem"}
          </p>
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

        {suaDuoc && (
          <div className="khsx-rt__baracts">
            {/* Không còn nút "Thêm công đoạn" chung chung ở đây. Thêm bước = CHÈN SAU 1 bước cụ
                thể: bảng dùng nút "+" ở mỗi hàng (bấm "+" hàng cuối = thêm ở cuối), sơ đồ DAG
                chọn node rồi "Chèn sau: <bước>". Danh sách rỗng vẫn có nút thêm-bước-đầu ở ô
                trống bên dưới — không giấu mất đường tạo bước đầu tiên. */}
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

      {/* Lệnh đang giữ chỗ vật tư: routing KHOÁ ở server. Nói ngay đây kèm đường lùi — cùng lẽ với
          băng bài ghép trên. Nguyên văn lý do lấy đúng câu server trả lúc từ chối để hai đầu không
          nói hai kiểu. */}
      {canUpdate && giuCho && (
        <div className="khsx-ghep-bang khsx-ghep-bang--khoa">
          <Icon name="lock" size={14} />
          <span>
            Lệnh <strong>đang giữ chỗ vật tư</strong> nên công đoạn khoá lại — sửa được số nào thì
            phần giữ chỗ cũng không hay biết. Vào <strong>Kế hoạch vật tư › Theo lệnh sản xuất</strong>{" "}
            bấm <strong>Nhả chỗ</strong>, sửa công đoạn xong rồi <strong>Giữ chỗ</strong> lại.
          </span>
        </div>
      )}

      {loiDoiCd && (
        <div className="khsx-ghep-bang khsx-ghep-bang--loi">
          <Icon name="alert" size={14} />
          <span>{loiDoiCd}</span>
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
          canUpdate={suaDuoc}
          onUpdateRows={setRows}
          onOpenDrawer={(idx: number) => moDrawer(idx, null)}
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
                    {suaDuoc && (
                      <Button variant="secondary" onClick={() => them()}>
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
              // Thuê ngoài ĐỌC GIỐNG HỆT bước máy: nhà thầu là một máy trong danh mục.
              const lamO = [toRefs?.find((x) => x.id === r.department_id)?.ten,
                            mayRefs?.find((x) => x.id === r.may_id)?.ten]
                              .filter(Boolean).join(" · ");
              return (
                <tr
                  key={r.key}
                  className={`khsx-rt__row khsx-rt__row--${meta.tone} ${keo === i ? "is-keo" : ""}`}
                  draggable={suaDuoc}
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
                      <span className="khsx-rt__ten">{tenBuoc(r, congDoanRefs) || "— chưa chọn công đoạn —"}</span>
                      {/* Chip DÙNG CHUNG với mọi màn khác có mặt bước này (`components/ChipBuoc`).
                          Trước 04/09/2026 mỗi màn tự vẽ lại nhãn từ một dữ liệu khác nhau nên nhãn
                          đứt quãng giữa đường — bước gán Thuê ngoài mà chưa điền nơi làm thì tới
                          Gantt là mất dấu. */}
                      <ChipLoaiBuoc loai_buoc={r.loai_buoc} nha_cung_cap={r.nha_cung_cap} />
                      {/* Con dao của bước hiện NGAY TRÊN BẢNG, không bắt mở drawer từng bước mới
                          biết bước nào chưa có dao. */}
                      <ChipKhuon
                        can_khuon={r.requires_tooling}
                        khuon={{
                          ma: r.khuon_be_ma,
                          so_ke: r.khuon_be_so_ke,
                          tinh_trang: r.khuon_be_tinh_trang,
                          ngay_ve_du_kien: r.khuon_be_ngay_ve,
                        }}
                      />
                    </button>
                  </td>
                  <td>
                    <span className={lamO ? "" : "khsx-muted"}>{lamO || "tổ mặc định"}</span>
                    {/* HIỆN LUÔN, kể cả 1 người (21/08/2026). Điều kiện `> 1` cũ giấu mất số của
                        bước một người: nhìn bảng không biết bước đã khai người hay chưa, phải mở
                        từng drawer — trong khi đây đúng là con số bàn xếp lịch dùng cân quân số tổ. */}
                    <span
                      className="khsx-rt__sub2"
                      title="Kíp chuẩn của bước — chia thời lượng bước tổ và là số bàn xếp lịch cân quân số tổ."
                    >
                      Kíp {Math.max(1, Number(r.so_nhan_cong_tieu_chuan) || 1)} người
                    </span>
                  </td>
                  <td className="khsx-rt__qty">
                    {/* GỠ điều kiện `nhom === "prepress"` (14/08/2026): bước chế bản nay CÓ số
                        thật (ra ← công thức của đơn vị, vào suy ngược kèm hao) nên che bằng dấu —
                        là giấu mất số bản kẽm phải ghi. Chỉ còn che khi THẬT SỰ chưa khai đơn vị.

                        Và "chưa khai đơn vị" nay phải hỏi tới ĐƠN VỊ SẢN LƯỢNG (10/09/2026): từ mg
                        `0273`, BỎ TRỐNG cả hai ô đơn vị chặng CHÍNH LÀ cách khai "bước ngoài dòng
                        giấy", nên điều kiện cũ quay ra giấu số ở đúng bước cần đọc số nhất — ghi
                        kẽm mấy bản. Bước đó đo bằng đơn vị của chính công đoạn (`kem`), lấy từ
                        danh mục chứ không có ở dòng. */}
                    {!r.don_vi_vao && !r.don_vi_ra && !r.don_vi_san_luong ? (
                      <span className="khsx-muted">—</span>
                    ) : (
                      <>
                        {/* Danh mục đổi SAU khi tạo lệnh (bậc bù hao · công thức đơn vị · hệ số) thì
                            số đã lưu thành cũ mà không ai biết. Server so ngầm rồi phơi
                            `so_luong_*_moi`; ở đây gạch số cũ + hiện số mới. KHÔNG tự lưu — bấm
                            "Lưu công đoạn" mới ghi, vì lệnh là ảnh chụp. */}
                        {r.so_luong_vao_moi != null && (
                          <s className="khsx-rt__cu">{num(n(r.so_luong_vao))}</s>
                        )}
                        <span className="khsx-num">
                          {num(r.so_luong_vao_moi ?? n(r.so_luong_vao))}
                        </span>
                        <span className="khsx-rt__dv">{dvNhan(r.don_vi_vao || r.don_vi_san_luong, r)}</span>
                        <span className="khsx-rt__arrow" aria-label="ra">→</span>
                        {r.so_luong_ra_moi != null && (
                          <s className="khsx-rt__cu">{num(n(r.so_luong_ra))}</s>
                        )}
                        <span className="khsx-num">
                          {num(r.so_luong_ra_moi ?? n(r.so_luong_ra))}
                        </span>
                        <span className="khsx-rt__dv">{dvNhan(r.don_vi_ra || r.don_vi_san_luong, r)}</span>
                        {(r.so_luong_vao_moi != null || r.so_luong_ra_moi != null) && (
                          <span className="khsx-rt__sub2 khsx-rt__lech">
                            danh mục đã đổi — bấm Lưu công đoạn để chốt số mới
                          </span>
                        )}
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
                        {r.phu_thuoc_step_keys.slice(0, 2).map((k) => {
                          // Tách "không có trong bảng" (⇒ bước của LSX khác) khỏi "có nhưng chưa
                          // đặt tên" (bước vừa chèn, chưa chọn công đoạn). Gộp hai ca vào một nhãn
                          // là vu cho bước mới chèn là bước của lệnh khác — đúng thứ nhìn thấy
                          // ngay sau khi bấm "Chèn trước/sau".
                          const i = rows.findIndex((x) => x.key === k);
                          const ten = i >= 0 ? tenBuoc(rows[i], congDoanRefs) : "";
                          return (
                            <span key={k} className="khsx-need khsx-need--soft">
                              {ten || (i >= 0
                                ? `Bước ${i + 1} — chưa chọn công đoạn`
                                : "Bước LSX khác")}
                            </span>
                          );
                        })}
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
                    {suaDuoc && (
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
                          className="khsx-rt__btn khsx-rt__btn--ins"
                          onClick={() => themTai(i)}
                          aria-label={`Chèn công đoạn mới sau bước ${i + 1}`}
                          title="Chèn công đoạn ngay sau bước này"
                        >
                          <Icon name="plus" size={14} />
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

      {suaDuoc && doiCauTruc && (
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
        {suaDuoc && (
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
          laBuocGiao={moBuoc === idxBuocGiao}
          soLuongDat={soLuongDat}
          congDoanRefs={congDoanRefs}
          toRefs={toRefs}
          mayRefs={mayRefs}
          khuonRefs={khuonRefs}
          tenSanPham={tenSanPham}
          tenKhach={tenKhach}
          onTaoKhuon={onTaoKhuon}
          vatTuRefs={vatTuRefs}
          giayRefs={giayRefs}
          phuThuocRefs={phuThuocRefs}
          baiGhep={baiGhep}
          dvChuoi={dvChuoi}
          canUpdate={suaDuoc}
          onPatch={(p) => patch(rows[moBuoc].key, p)}
          onPatchLsx={onPatchLsx}
          onDoiCongDoan={(id) => doiCongDoan(rows[moBuoc].key, id, rows[moBuoc].ten)}
          onDoiMay={(id) => doiMay(rows[moBuoc].key, id)}
          tabDau={tabDau}
          onClose={dongDrawer}
          onPrev={() => setMoBuoc(Math.max(moBuoc - 1, 0))}
          onNext={() => setMoBuoc(Math.min(moBuoc + 1, rows.length - 1))}
        />
      )}
    </div>
  );
}
