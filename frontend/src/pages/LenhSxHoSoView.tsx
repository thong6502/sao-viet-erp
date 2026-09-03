// Hồ sơ MỘT lệnh sản xuất — lớp phủ CHỈ ĐỌC mở từ bảng tra cứu (`LenhSanXuatPage`).
//
// ⚠️ KHÔNG MỘT NÚT GHI NÀO, cùng luật với màn danh sách. Không Bắt đầu/Tạm dừng/Kết thúc, không
// giao/rút người, không sửa routing, không lập phiếu. Thứ duy nhất đi RA khỏi màn là một LIÊN KẾT
// sang form giao hàng đã có — điều hướng, không phải ghi.
//
// ⚠️ KHÔNG MỘT SỐ TIỀN NÀO, kể cả trong `title`. Máy chủ đã không trả (`test_khong_lo_tien` giữ,
// và `ThongSoOut` cố ý khai từng trường để `phi_giao_hang` của phiếu tính giá không lọt ra) —
// đừng tính bù ở đây.
//
// ⚠️ KHÔNG tái dùng `LsxDetailView.tsx`: đó là màn LẬP kế hoạch, có chế độ sửa. Dựng lại từ DTO
// chỉ đọc để không vô tình lộ CTA hay đụng logic lập lệnh.
//
// ⚠️ ĐỌC, KHÔNG TÍNH LẠI. Mọi con số dưới đây lấy nguyên từ `LenhSxHoSoOut`. Cộng/trừ ở FE là đẻ
// nguồn sự thật thứ hai, và nó sẽ lệch đúng ở ca quy đổi đơn vị — ca không ai nhìn ra.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, LSX_LOAI_BUOC_META, api } from "../api/client";
import type {
  LenhSxGiaoHangHang,
  LenhSxHoSoOut,
  LenhSxRoutingNode,
  LenhSxVatTuDong,
  LsxTheoDoiCanhBao,
  LsxTheoDoiTrangThai,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon, type IconName } from "../components/Icons";
import {
  BangLoi,
  ChipGap,
  EmptyState,
  NHOM_CONG_DOAN,
  classHan,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { useNapTenDonVi } from "./tenDonVi";

/** Pill trạng thái lệnh — CÙNG bộ chữ và cùng họ màu với bảng danh sách. Mở hồ sơ ra thấy một
 *  nhãn khác cái vừa đọc trên dòng là mất niềm tin vào cả hai màn. */
const PILL: Record<LsxTheoDoiTrangThai, { label: string; cls: string }> = {
  dang_sx: { label: "Đang SX", cls: "hslsx-pill--steel" },
  canh_bao: { label: "Cảnh báo", cls: "hslsx-pill--signal" },
  kcs: { label: "KCS", cls: "hslsx-pill--plum" },
  cho_nhap_kho: { label: "Chờ nhập kho", cls: "hslsx-pill--amber" },
  san_sang_giao: { label: "Sẵn sàng giao", cls: "hslsx-pill--moss" },
  hoan_thanh: { label: "Hoàn thành", cls: "hslsx-pill--xong" },
};

const CANH_BAO: Record<LsxTheoDoiCanhBao, { label: string; cls: string }> = {
  su_co: { label: "Sự cố", cls: "hslsx-badge--signal" },
  tam_dung: { label: "Tạm dừng", cls: "hslsx-badge--amber" },
  tre_han: { label: "Trễ hạn", cls: "hslsx-badge--signal" },
  kcs_khong_dat: { label: "KCS không đạt", cls: "hslsx-badge--signal" },
  thieu_vat_tu: { label: "Thiếu vật tư", cls: "hslsx-badge--amber" },
};

/** Loại lệnh (`lsx.loai`) — sáu giá trị của `models/lsx.LOAI_LSX`. Lệnh bù / làm lại đọc rất khác
 *  lệnh mới: nó nói tại sao lô này tồn tại, nên phải ra chữ chứ không để nguyên khoá. */
const LOAI_LENH: Record<string, string> = {
  san_xuat_moi: "Sản xuất mới",
  bo_sung: "Bổ sung",
  bu: "Bù",
  lam_lai: "Làm lại",
  mau: "Mẫu",
  noi_bo: "Nội bộ",
};

/** Trạng thái CÔNG VIỆC của một bước (`SanXuatCongViec.trang_thai`). `null` = bước chưa có công
 *  việc, tức lệnh chưa phát hành tới đó — khác hẳn "chờ làm", nên có nhãn riêng ở chỗ dùng. */
const TT_BUOC: Record<string, { label: string; cls: string }> = {
  released: { label: "Chờ làm", cls: "hslsx-pill--xong" },
  running: { label: "Đang chạy", cls: "hslsx-pill--steel" },
  paused: { label: "Tạm dừng", cls: "hslsx-pill--amber" },
  completed: { label: "Hoàn thành", cls: "hslsx-pill--moss" },
};

/** Màu bảng cân đối vật tư. Nhãn nói HỆ QUẢ, không nói màu — cùng chữ với màn Kế hoạch vật tư
 *  (`VatTuKeHoachView.MAU_META`) để hai màn không dạy người dùng hai bộ từ vựng. */
const VT_MAU: Record<string, { label: string; cls: string }> = {
  xam: { label: "Đã cấp đủ", cls: "hslsx-pill--xong" },
  xanh: { label: "Đủ trong kho", cls: "hslsx-pill--moss" },
  vang: { label: "Đủ nhờ hàng về", cls: "hslsx-pill--amber" },
  do: { label: "Thiếu", cls: "hslsx-pill--signal" },
  ve_muon: { label: "Hàng về muộn", cls: "hslsx-pill--signal" },
  khong_ro: { label: "Chưa đánh giá được", cls: "hslsx-pill--plum" },
};

const KCS_KET_LUAN: Record<string, { label: string; cls: string }> = {
  dat: { label: "Đạt", cls: "hslsx-pill--moss" },
  dat_mot_phan: { label: "Đạt một phần", cls: "hslsx-pill--amber" },
  khong_dat: { label: "Không đạt", cls: "hslsx-pill--signal" },
};

/** Yêu cầu sửa chữa (`ky_thuat_may.TRANG_THAI_YEU_CAU`) — lời BÁO hỏng, ba nấc. */
const SU_CO_TT: Record<string, { label: string; cls: string }> = {
  cho_tiep_nhan: { label: "Chờ tiếp nhận", cls: "hslsx-pill--amber" },
  da_tao_phieu: { label: "Đã tạo phiếu", cls: "hslsx-pill--steel" },
  tu_choi: { label: "Từ chối", cls: "hslsx-pill--xong" },
};

/** Phiếu sửa (`ky_thuat_may.TRANG_THAI_SUA_CHUA`) — VIỆC của thợ, bốn nấc. Khác hẳn ba nấc trên:
 *  một cái là lời báo, cái kia là công việc. */
const PHIEU_SUA_TT: Record<string, { label: string; cls: string }> = {
  cho_sua: { label: "Chờ sửa", cls: "hslsx-pill--amber" },
  dang_sua: { label: "Đang sửa", cls: "hslsx-pill--steel" },
  cho_vat_tu: { label: "Chờ vật tư", cls: "hslsx-pill--signal" },
  da_sua_xong: { label: "Đã sửa xong", cls: "hslsx-pill--moss" },
};

const MUC_DO: Record<string, string> = {
  nhe: "Nhẹ",
  trung_binh: "Trung bình",
  nghiem_trong: "Nghiêm trọng",
};

/** Yêu cầu nhập kho thành phẩm (`san_xuat_kho.TRANG_THAI_YC`). */
const KHO_YC_TT: Record<string, { label: string; cls: string }> = {
  cho_kho: { label: "Chờ kho nhận", cls: "hslsx-pill--amber" },
  nhap_mot_phan: { label: "Nhập một phần", cls: "hslsx-pill--steel" },
  da_nhap: { label: "Đã nhập đủ", cls: "hslsx-pill--moss" },
  huy: { label: "Đã hủy", cls: "hslsx-pill--xong" },
};

/** Phân loại lot BTP (`san_xuat_kho.PHAN_LOAI_BTP_DU`). `mau_luu`/`phe` KHÔNG vào tồn khả dụng —
 *  bày đúng chữ để không ai cộng chúng vào số giao được. */
const BTP_PHAN_LOAI: Record<string, string> = {
  nhap_btp: "Nhập kho BTP",
  mau_luu: "Mẫu lưu",
  phe: "Phế / hỏng",
};

/** Loại sự kiện timeline — nhãn ngắn đứng trước nội dung (nội dung đã là câu đầy đủ do máy chủ
 *  dựng, nên nhãn chỉ để quét mắt và tô họ màu). */
const TL_LOAI: Record<string, { label: string; cls: string }> = {
  phat_hanh: { label: "Phát hành", cls: "hslsx-pill--plum" },
  bat_dau: { label: "Bắt đầu", cls: "hslsx-pill--steel" },
  ket_thuc: { label: "Kết thúc", cls: "hslsx-pill--moss" },
  tam_dung: { label: "Tạm dừng", cls: "hslsx-pill--amber" },
  doi_may: { label: "Đổi máy", cls: "hslsx-pill--amber" },
  dung: { label: "Dừng", cls: "hslsx-pill--xong" },
  san_luong: { label: "Sản lượng", cls: "hslsx-pill--steel" },
  kcs: { label: "KCS", cls: "hslsx-pill--plum" },
  su_co: { label: "Sự cố", cls: "hslsx-pill--signal" },
  de_nghi_nhap_kho: { label: "Đề nghị nhập kho", cls: "hslsx-pill--amber" },
  kho_nhan: { label: "Kho nhận", cls: "hslsx-pill--moss" },
  giao_nguoi: { label: "Giao người", cls: "hslsx-pill--xong" },
  rut_nguoi: { label: "Rút người", cls: "hslsx-pill--xong" },
};

/** Số THẬP PHÂN của xưởng (sản lượng, tồn, nhu cầu): cắt đuôi `,0` vô nghĩa nhưng giữ tối đa 2
 *  chữ số khi có phần lẻ thật. `num()` của `keHoachSxShared` nhắm số nguyên nên không đủ ở đây. */
function so(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** `so()` nhưng 0 cũng ra "—". Dùng cho những ô mà máy chủ ép `None → 0.0` (`ho_so._f`), nên số 0
 *  ở đó KHÔNG phân biệt được với "chưa khai" — bày "0" là khẳng định một điều chưa ai nói. */
function soHoac(v: number | null | undefined): string {
  return v ? so(v) : "—";
}

function pct1(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

/** Câu dùng chung khi một con số tổng trộn nhiều thang đo. CÙNG chữ với khối Giao hàng
 *  (`don_vi_lech`) — hai chỗ nói hai kiểu là dạy người dùng hai từ vựng cho một sự thật. */
const NHIEU_DON_VI = "Nhiều đơn vị — không cộng được";

/** `ma` là MÃ trong danh mục (`to`, `kem`) — thứ để GOM, không phải thứ để bày. Gom theo mã chứ
 *  không theo tên: hai mã lỡ trùng tên thì gom theo tên là cộng nhầm hai thang thành một. Bày ra
 *  màn thì bọc `nhanDonVi(ma)`. */
type LoDonVi = { so: number; ma: string | null };

/** Đơn vị của một tập lô (sản lượng hoặc KCS).
 *
 *  Máy chủ CỘNG THẲNG `tot/hong/tong` và `nhan/dat/khong_dat` qua mọi công việc của lệnh mà không
 *  đọc `don_vi` — trong khi đơn vị là của TỪNG bước (`cong_viec.don_vi_ra`). Nên tổng đó chỉ có
 *  nghĩa khi cả lệnh ghi bằng MỘT thang: bước Phơi kẽm 8 kẽm + bước In 500 tờ ra ô "508", một con
 *  số không ai giải thích nổi, nằm đúng chỗ điều độ liếc mắt lấy số. Với KCS còn nặng hơn: tỉ lệ
 *  (1000 tờ + 400 cái)/(1000 tờ + 500 cái) = 93,3 % che mất việc 1/5 thành phẩm cuối trượt KCS.
 *
 *  `so >= 2` ⇒ chỗ dùng phải IM con số tổng, đúng khuôn `don_vi_lech` mà khối Giao hàng đã theo.
 *  `so === 0` (không lô nào khai đơn vị) ⇒ giữ nguyên hành vi cũ: không có bằng chứng trộn thang
 *  thì cũng đừng hô hoán, chỉ là không gắn được đơn vị vào. */
function donViLo(batch: { don_vi: string | null }[]): LoDonVi {
  const s = new Set(batch.map((b) => b.don_vi).filter((v): v is string => !!v));
  return { so: s.size, ma: s.size === 1 ? [...s][0] : null };
}

/** Một con số TỔNG kèm đơn vị — hoặc câu từ chối khi tổng đó trộn thang. */
function tongTheoDonVi(v: number | null | undefined, dv: LoDonVi): string {
  if (dv.so >= 2) return NHIEU_DON_VI;
  return dv.ma ? `${so(v)} ${nhanDonVi(dv.ma)}` : so(v);
}

/** Nhãn an toàn cho một chuỗi enum bất kỳ: máy chủ thêm giá trị mới thì màn hiện chính chuỗi đó
 *  chứ không hiện ô trống — ô trống làm người đọc tưởng dữ liệu thiếu. */
function pillMeta(
  map: Record<string, { label: string; cls: string }>,
  k: string | null | undefined,
): { label: string; cls: string } | null {
  if (!k) return null;
  return map[k] ?? { label: k, cls: "hslsx-pill--xong" };
}

function Pill({ meta }: { meta: { label: string; cls: string } | null }) {
  if (!meta) return null;
  return <span className={`hslsx-pill ${meta.cls}`}>{meta.label}</span>;
}

/** Một ô "nhãn — giá trị" của lưới thông tin. Giá trị rỗng hiện "—" chứ không ẩn ô: ô biến mất
 *  làm lưới xô lệch và người đọc không biết trường đó có tồn tại hay không. */
function Kv({ k, v, title }: { k: string; v: ReactNode; title?: string }) {
  return (
    <div className="hslsx-hs__kv" title={title}>
      <span className="hslsx-hs__kv-k">{k}</span>
      <span className="hslsx-hs__kv-v">{v === null || v === undefined || v === "" ? "—" : v}</span>
    </div>
  );
}

/** Khối RỖNG nói VÌ SAO rỗng. Một khoảng trắng câm trông y hệt một khối hỏng — và ở màn tra cứu
 *  thì "không có" và "không tải được" là hai kết luận trái ngược nhau. */
function Trong({ children }: { children: ReactNode }) {
  return <p className="hslsx-hs__trong">{children}</p>;
}

/** Một khối gập. `dem` hiện ngay trên thanh tiêu đề nên khối ĐANG ĐÓNG vẫn nói được một câu —
 *  gập mà im hẳn thì người dùng phải mở từng cái để biết có gì bên trong. */
function Khoi({
  id,
  icon,
  ten,
  dem,
  canhBao,
  moSan = false,
  children,
}: {
  id: string;
  icon: IconName;
  ten: string;
  /** Câu tóm tắt trên thanh tiêu đề (số dòng, tỉ lệ…). */
  dem?: ReactNode;
  /** Tô thanh tiêu đề khi bên trong có thứ phải xử — dùng dè, tô hết thì màu hết mang tin. */
  canhBao?: boolean;
  moSan?: boolean;
  children: ReactNode;
}) {
  const [mo, setMo] = useState(moSan);
  return (
    <section className={`hslsx-hs__khoi${canhBao ? " is-canhbao" : ""}`}>
      <h3 className="hslsx-hs__khoi-h">
        <button
          type="button"
          className="hslsx-hs__khoi-btn"
          aria-expanded={mo}
          aria-controls={`hslsx-hs-${id}`}
          onClick={() => setMo((v) => !v)}
        >
          <Icon name="chevron" size={14} className={mo ? "is-mo" : undefined} />
          <Icon name={icon} size={15} />
          <span className="hslsx-hs__khoi-ten">{ten}</span>
          {dem !== undefined && <span className="hslsx-hs__khoi-dem">{dem}</span>}
        </button>
      </h3>
      {/* Giữ node trong DOM khi đóng (chỉ `hidden`) để trình đọc màn hình thấy quan hệ
          `aria-controls`, và để vị trí cuộn bên trong khối không mất sau mỗi lần gập. */}
      <div id={`hslsx-hs-${id}`} className="hslsx-hs__khoi-b" hidden={!mo}>
        {children}
      </div>
    </section>
  );
}

/** Khung cuộn NGANG riêng cho từng bảng. Bảng khai `min-width`, TUYỆT ĐỐI không `width: 100%` —
 *  bảng 100% nằm trong khung `overflow-x:auto` bị ép đúng bề ngang khung nên cột không nở và
 *  khung cuộn thành vô dụng (khuôn lỗi (b) của §9 thiết kế). */
function BangCuon({ children }: { children: ReactNode }) {
  return <div className="hslsx-hs__bangwrap">{children}</div>;
}

export function LenhSxHoSoView({
  lsxId,
  pv,
  onClose,
  onMoDon,
  eventTick,
}: {
  lsxId: number;
  /** Phiên bản in trên tờ giấy đã quét (Task 14, deep link QR `#lsx=&pv=`) — `null`/`undefined`
   *  khi hồ sơ mở tay từ bảng (không có tờ giấy nào để so). Có giá trị VÀ nhỏ hơn `d.phien_ban`
   *  hiện tại ⇒ bày băng cảnh báo NGAY DƯỚI, KHÔNG dựng lại nội dung màn theo `pv` — màn luôn hiện
   *  dữ liệu HIỆN TẠI, băng chỉ báo "tờ giấy trong tay bạn đã cũ". */
  pv?: number | null;
  onClose: () => void;
  /** Điều hướng sang màn Đơn hàng bán và mở drawer của đơn — đường đã chạy sẵn (Báo giá dùng).
   *  Form "Tạo yêu cầu giao hàng" nằm TRONG drawer đó và tự nạp phần còn lại bằng
   *  `api.giaoHang.conPhaiGiao(orderId)`, nên thứ duy nhất cần truyền là `orderId`. */
  onMoDon?: (orderId: number) => void;
  /** Nhích theo mỗi nhịp SSE đã gộp của màn danh sách — hồ sơ tươi theo CÙNG một nhịp với bảng
   *  phía sau, để hai mặt đọc không nói hai chuyện về một lệnh. */
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Mọi cột `don_vi` dưới đây là MÃ danh mục (`to`, `kem`, `cai`). Nạp bảng tên MỘT lần cho cả
  // phiên rồi bọc `nhanDonVi(...)` ở từng chỗ bày ra — người đọc ở xưởng không tra mã.
  useNapTenDonVi();
  const [d, setD] = useState<LenhSxHoSoOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loi, setLoi] = useState<{ text: string; thuLaiDuoc: boolean } | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.lenhSanXuat
      .hoSo(token, lsxId)
      .then((r) => {
        setD(r);
        setLoi(null);
      })
      .catch((e) => {
        // 404 và 403 nói hai câu khác nhau: "màn này không có lệnh nào như thế" (chưa phát hành,
        // hoặc id sai) vs "có, nhưng không phải phần việc của bạn". Gộp thành một lời là giấu mất
        // thứ người dùng có quyền biết — rằng họ cần xin quyền, chứ không phải gõ nhầm.
        const st = e instanceof ApiError ? e.status : 0;
        setLoi({
          text:
            st === 403
              ? "Lệnh này nằm ngoài phạm vi của bạn."
              : st === 404
                ? "Không tìm thấy lệnh này trong danh sách lệnh đã phát hành."
                : e instanceof ApiError
                  ? e.message
                  : "Máy chủ không phản hồi.",
          thuLaiDuoc: st !== 403 && st !== 404,
        });
      })
      .finally(() => setLoading(false));
  }, [token, lsxId]);

  // `lsxId` ĐỔI trong lúc lớp phủ vẫn mounted (deep-link, hoặc Shift+Tab lọt xuống một dòng đang
  // bị che rồi bấm Enter) ⇒ phải XOÁ hồ sơ cũ trước. Không xoá thì nhánh render `d && tt && td`
  // vẫn đúng và màn bày nguyên dữ liệu + MÃ LỆNH CŨ suốt thời gian chờ mạng rồi đột ngột thay số —
  // người đọc không có cách nào biết mình đang nhìn lệnh nào. Effect này phải đứng TRƯỚC effect
  // gọi `load()` để lượt render kế tiếp rơi đúng vào nhánh "Đang tải hồ sơ lệnh…".
  useEffect(() => {
    setD(null);
    setLoi(null);
  }, [lsxId]);

  useEffect(() => {
    load();
  }, [load]);

  // Tươi theo nhịp SSE đã gộp của màn danh sách. KHÔNG chớp skeleton: giữ nguyên nội dung cũ và
  // chỉ thay số khi lượt mới về — hồ sơ đang được đọc mà nhấp nháy dưới tay là làm phiền.
  const tickDau = useRef(eventTick ?? 0);
  useEffect(() => {
    const t = eventTick ?? 0;
    if (t === tickDau.current) return;
    tickDau.current = t;
    load();
  }, [eventTick, load]);

  // `onClose` là hàm mới mỗi lần render (chỗ gọi khai inline) nên phải đi qua ref — để nó trong
  // deps thì mỗi lượt render là một lần gỡ/gắn listener VÀ một lần set lại `overflow` của body.
  const dongRef = useRef(onClose);
  dongRef.current = onClose;

  // Esc đóng + KHOÁ CUỘN NỀN, gộp một effect vì cả hai đều là "trong lúc lớp phủ đang mở" (chép
  // khuôn `danh-muc/components/Drawer.tsx:42-65`).
  //
  // Khoá cuộn = chặn KHUNG CUỘN CỦA TÀI LIỆU. Đo trên dev-browser (1280×560, nền dài hơn khung):
  // lăn chuột trên dải nền hai bên KHÔNG làm `.shell__content` trôi — vì `.hslsx-hs` là
  // `position: fixed`, chuỗi cuộn của nó bỏ qua mọi khung cuộn tổ tiên và rơi thẳng xuống tài
  // liệu. Nên hôm nay dòng này là lớp chặn cho đúng cái đích đó, và là lớp phòng khi vỏ ứng dụng
  // đổi sang cho tài liệu tự cuộn. Chép khuôn `Drawer.tsx` để hai lớp phủ hành xử như nhau.
  //
  // Esc đăng ký ở `document` vì tiêu điểm có thể đang nằm trong một khung cuộn con.
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") dongRef.current();
    };
    document.addEventListener("keydown", f);
    const cuonCu = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", f);
      document.body.style.overflow = cuonCu;
    };
  }, []);

  // Mở ra thì tiêu điểm phải nhảy vào lớp phủ, nếu không người đi bàn phím vẫn đang đứng ở bảng
  // phía sau và Tab tiếp theo chạy vào những dòng đang bị che.
  const quayLaiRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    quayLaiRef.current?.focus();
  }, [lsxId]);

  // --- in phiếu công nghệ ----------------------------------------------------
  const [dangIn, setDangIn] = useState(false);
  const [inLoi, setInLoi] = useState<string | null>(null);

  async function inPhieu() {
    if (!token || dangIn) return;
    setDangIn(true);
    setInLoi(null);
    try {
      // Endpoint đòi Bearer nên phải kéo về blob rồi mới mở — trỏ tab mới thẳng vào URL là mở
      // một tab không mang token và ăn 401.
      const url = await api.lenhSanXuat.phieuCongNghePdf(token, lsxId);
      // KHÔNG khai `noopener` trong chuỗi tính năng: theo chuẩn HTML, `window.open` với `noopener`
      // trả `null` NGAY CẢ KHI mở thành công, nên còn cờ đó thì không phân biệt nổi "đã mở" với
      // "bị chặn". Đích ở đây là blob CÙNG GỐC do chính màn này dựng (một tờ PDF), không phải trang
      // lạ — nên cắt `opener` bằng tay là đủ, và đổi lại ta đọc được giá trị trả về.
      const w = window.open(url, "_blank");
      if (!w) {
        // `window.open` chạy SAU một `await` mạng: quá cửa sổ transient activation của trình duyệt
        // (lệnh routing dài mất vài giây là đủ) thì cửa sổ bật bị chặn, `catch` KHÔNG chạy vì fetch
        // đã thành công. Không kiểm ở đây là nút nhấp nháy "Đang dựng phiếu…" rồi im — không tab
        // nào mở, không một chữ báo, bấm lại lần nữa cũng thế.
        URL.revokeObjectURL(url);
        setInLoi("Trình duyệt đã chặn cửa sổ mới — cho phép mở cửa sổ cho trang này rồi bấm lại.");
        return;
      }
      try {
        w.opener = null;
      } catch {
        /* Cùng gốc thì không rơi vào đây; có rơi thì cũng chỉ mất một lớp phòng thủ thừa. */
      }
      // Thu hồi TRỄ: revoke ngay sau `open` thì tab kia chưa kịp nạp xong và mở ra trang trắng.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      const st = e instanceof ApiError ? e.status : 0;
      setInLoi(
        st === 403
          ? "Bạn không có quyền in phiếu của lệnh này."
          : // 404 ở route này nghĩa đúng những gì `pham_vi.chan_ngoai_pham_vi` ném ra (giống hệt
            // `GET /api/lenh-san-xuat/{id}`, cùng cửa quyền): lệnh không tồn tại, hoặc không còn ở
            // trạng thái ĐÃ PHÁT HÀNH nữa — không phải "tính năng in chưa bật".
            st === 404
            ? "Không tìm thấy lệnh sản xuất này — có thể lệnh chưa/không còn ở trạng thái đã phát hành."
            : "Không in được phiếu công nghệ. Thử lại sau.",
      );
    } finally {
      setDangIn(false);
    }
  }

  const tt = d?.thong_tin;
  const td = d?.tien_do;
  const pct = td ? Math.max(0, Math.min(100, Math.round(td.phan_tram))) : 0;

  // Bước hiện tại đứng ở đâu trong routing — để bảng routing khỏi phải dò lại.
  const nhomLb = td?.nhom_cong_doan
    ? (NHOM_CONG_DOAN[td.nhom_cong_doan] ?? td.nhom_cong_doan)
    : null;

  const lopRouting = useMemo(() => gomTheoLop(d?.routing.nodes ?? []), [d]);
  const dvSanLuong = useMemo(() => donViLo(d?.san_luong.batch ?? []), [d]);
  const dvKcs = useMemo(() => donViLo(d?.kcs.batch ?? []), [d]);

  // Cú bấm chỉ được coi là "bấm ra nền" khi nó BẮT ĐẦU ở tấm phủ. `stopPropagation` trên panel
  // không đủ: `mousedown` trong panel + `mouseup` trên nền thì trình duyệt bắn `click` ở TỔ TIÊN
  // CHUNG, tức chính tấm phủ ⇒ bôi đen mã lệnh để copy mà kéo quá mép panel rồi nhả là hồ sơ sập,
  // mất luôn chỗ đang đọc trong khối gập.
  const nhanTrenNen = useRef(false);

  return (
    <div
      className="hslsx-hs"
      onMouseDown={(e) => {
        nhanTrenNen.current = e.target === e.currentTarget;
      }}
      // Bấm ra ngoài tấm phủ = đóng, đúng thói quen của drawer đơn hàng.
      onClick={(e) => {
        if (e.target !== e.currentTarget || !nhanTrenNen.current) return;
        onClose();
      }}
    >
      {/* `role="dialog" aria-modal` phải nằm trên PANEL, không phải trên tấm phủ: gán vai hộp
          thoại cho lớp phủ trang trí thì trình đọc màn hình coi CẢ lớp phủ là nội dung hộp thoại
          (đúng lỗi mà `danh-muc/components/Drawer.tsx:10-12` đã sửa một lần rồi). */}
      <section
        className="hslsx-hs__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hslsx-hs-title"
      >
        <header className="hslsx-hs__top">
          <div className="hslsx-hs__toprow">
            <button
              type="button"
              ref={quayLaiRef}
              className="hslsx-hs__back"
              onClick={onClose}
            >
              <Icon name="chevron" size={15} />
              Quay lại danh sách
            </button>
            <div className="hslsx__spacer" />
            {/* Nút In là ĐƯỜNG RA thứ hai của màn — nó ĐỌC ra một tờ giấy, không ghi gì vào lệnh
                (tải phiếu không làm tăng `phien_ban`). Không gài sau cờ nào cả: một tờ phiếu công
                nghệ là thứ tổ nào cũng cần cầm xuống xưởng, và nút này luôn bấm được. */}
            <Button variant="secondary" onClick={inPhieu} disabled={dangIn || !token}>
              <Icon name="printer" size={14} /> {dangIn ? "Đang dựng phiếu…" : "In phiếu công nghệ"}
            </Button>
          </div>

          {/* Hỏng thì nói NGAY dưới nút, không toast: người vừa bấm đang nhìn đúng chỗ này, và
              câu trả lời phải ở lại đủ lâu để đọc. */}
          {inLoi && (
            <p className="hslsx-hs__inloi" role="alert">
              <Icon name="alert" size={14} /> {inLoi}
            </p>
          )}

          <div className="hslsx-hs__ident">
            <h2 className="hslsx-hs__ma" id="hslsx-hs-title">
              {tt?.ma ?? `Lệnh #${lsxId}`}
            </h2>
            {tt?.is_rush && <ChipGap />}
            {td && <Pill meta={PILL[td.trang_thai] ?? PILL.dang_sx} />}
            {td?.canh_bao.map((c) => {
              const meta = CANH_BAO[c];
              return (
                <span key={c} className={`hslsx-badge ${meta?.cls ?? ""}`}>
                  {meta?.label ?? c}
                </span>
              );
            })}
            {/* `phien_ban` = null khi lệnh chưa có công việc nào, tức CHƯA TỪNG phát hành. Bày
                "v1" ở đó là bịa ra một phiên bản chưa tồn tại. */}
            {d && (
              <span className="hslsx-hs__ver" title="Phiên bản phát hành đang hiệu lực">
                {d.phien_ban == null ? "Chưa phát hành" : `Phiên bản ${d.phien_ban}`}
              </span>
            )}
            <span className="hslsx__ro" title="Màn tra cứu — không có thao tác ghi nào">
              Chỉ xem
            </span>
          </div>
          <p className="hslsx-hs__sub">
            {tt?.ten ?? "Chưa đặt tên"}
            {tt?.khach_hang ? ` · ${tt.khach_hang}` : ""}
            {tt?.order_no ? ` · Đơn ${tt.order_no}` : ""}
          </p>

          {/* Task 14 (deep link QR): tờ giấy trong tay người quét cũ hơn phiên bản đang hiệu lực.
              So bằng `!=` (không `!==`) để chấp cả `undefined` lẫn `null` làm "không có pv" — hai
              nguồn gọi component (mở tay vs. AppShell rỗng navParams) không hẹn trước sẽ dùng cái
              nào. Nội dung màn phía dưới KHÔNG đổi theo `pv` — luôn là dữ liệu hiện tại (brief
              Bước 2); băng này chỉ CẢNH BÁO, không phải bộ lọc/snapshot. */}
          {d && pv != null && d.phien_ban != null && pv < d.phien_ban && (
            <div className="banner banner--warn hslsx-hs__pvcanh" role="status">
              Phiếu giấy v{pv}, lệnh hiện tại đã là v{d.phien_ban}
            </div>
          )}
        </header>

        <div className="hslsx-hs__body">
          {loading && !d ? (
            <p className="hslsx-hs__dangtai">Đang tải hồ sơ lệnh…</p>
          ) : loi && !d ? (
            <EmptyState
              icon="alert"
              title={loi.text}
              sub={
                loi.thuLaiDuoc
                  ? undefined
                  : "Danh sách phía sau vẫn còn nguyên — quay lại và chọn lệnh khác."
              }
              action={
                loi.thuLaiDuoc ? (
                  <Button variant="ghost" onClick={load}>
                    Tải lại
                  </Button>
                ) : undefined
              }
            />
          ) : d && tt && td ? (
            <>
              {/* Lỗi khi ĐÃ CÓ dữ liệu ⇒ banner, giữ nguyên hồ sơ cũ. Hồ sơ cũ đọc được còn hơn
                  màn trắng — và người đang đọc không mất chỗ. */}
              {loi && <BangLoi text="Không làm mới được hồ sơ." onRetry={load} />}

              {/* ---------- Dải tổng quan: ba câu hỏi đầu tiên của người mở hồ sơ ---------- */}
              <section className="hslsx-hs__sum" aria-label="Tổng quan lệnh">
                <div className="hslsx-hs__tile hslsx-hs__tile--wide">
                  <span className="hslsx-hs__tile-lb">Tiến độ</span>
                  <span className="hslsx-hs__tile-val">
                    {td.uoc_tinh ? "~" : ""}
                    {pct}%
                  </span>
                  <span
                    className="hslsx__bar"
                    role="progressbar"
                    aria-valuenow={pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuetext={
                      td.uoc_tinh ? `khoảng ${pct} phần trăm, ước tính` : `${pct} phần trăm`
                    }
                  >
                    <span
                      className={`hslsx__barfill${td.uoc_tinh ? " is-uoc" : ""}`}
                      style={{ width: `${pct}%` }}
                    />
                  </span>
                  {/* Cờ ước tính phải ra tới MẶT MÀN, không giấu trong tooltip: 40% "đo được" và
                      40% "ước tính" là hai mức tin cậy khác hẳn nhau. */}
                  <span className="hslsx-hs__tile-phu">
                    {td.uoc_tinh
                      ? "Ước tính theo thời lượng kế hoạch — bước chưa khai sản lượng"
                      : "Đo theo sản lượng đã khai"}
                  </span>
                </div>

                <div className="hslsx-hs__tile">
                  <span className="hslsx-hs__tile-lb">Bước hiện tại</span>
                  <span className="hslsx-hs__tile-val hslsx-hs__tile-val--chu">
                    {td.buoc_hien_tai ?? "—"}
                  </span>
                  <span className="hslsx-hs__tile-phu">
                    {[nhomLb, td.may].filter(Boolean).join(" · ") || "Chưa gắn máy"}
                    {td.nguoi.length > 0 ? ` · ${td.nguoi.join(", ")}` : ""}
                  </span>
                </div>

                {/* Tổng sản lượng chỉ có nghĩa khi cả lệnh ghi bằng MỘT thang đo — xem `donViLo`.
                    Trộn thang thì im cả con số lẫn dòng phụ, đừng bày một nửa. */}
                <div className="hslsx-hs__tile">
                  <span className="hslsx-hs__tile-lb">Sản lượng tốt</span>
                  {dvSanLuong.so >= 2 ? (
                    <>
                      <span className="hslsx-hs__tile-val hslsx-hs__tile-val--chu">
                        {NHIEU_DON_VI}
                      </span>
                      <span className="hslsx-hs__tile-phu">
                        Mỗi bước ghi một thang đo riêng — đọc số ở khối «Sản lượng theo lượt ghi».
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="hslsx-hs__tile-val">
                        {so(d.san_luong.tot)}
                        {dvSanLuong.ma && <small>{nhanDonVi(dvSanLuong.ma)}</small>}
                      </span>
                      <span className="hslsx-hs__tile-phu">
                        {so(d.san_luong.hong)} hỏng · {so(d.san_luong.tong)} tổng đã ghi
                      </span>
                    </>
                  )}
                </div>

                <div className="hslsx-hs__tile">
                  <span className="hslsx-hs__tile-lb">Giờ máy đã chạy</span>
                  <span className="hslsx-hs__tile-val">
                    {so(Math.round(td.gio_may * 10) / 10)}
                    <small>giờ</small>
                  </span>
                  {/* Một lượt in ghép 3 lệnh được đếm ĐỦ cho cả 3 — số này không cộng qua nhiều
                      lệnh được, và nói ra tại chỗ rẻ hơn sửa một báo cáo đã sai. */}
                  <span className="hslsx-hs__tile-phu">
                    Ca in ghép tính đủ cho mọi lệnh trên tờ — đừng cộng qua nhiều lệnh
                  </span>
                </div>

                <div className="hslsx-hs__tile">
                  <span className="hslsx-hs__tile-lb">Hạn SX nội bộ</span>
                  <span
                    className={`hslsx-hs__tile-val hslsx-hs__tile-val--chu hslsx__han ${classHan(
                      tt.han_hoan_thanh_sx,
                    )}`}
                  >
                    {ngay(tt.han_hoan_thanh_sx)}
                  </span>
                  {/* `null` ⇒ "Chưa đủ dữ liệu", KHÔNG "—": máy chủ cố ý im khi có bước thiếu thời
                      lượng, thà im còn hơn bịa một mốc mà điều độ đem đi hứa với khách. */}
                  <span className="hslsx-hs__tile-phu">
                    Dự kiến xong: {td.du_kien_xong ? ngayGio(td.du_kien_xong) : "chưa đủ dữ liệu"}
                  </span>
                </div>
              </section>

              {/* ---------- Sản phẩm & đơn hàng — định danh, KHÔNG gập ---------- */}
              <section className="hslsx-hs__khoi">
                <h3 className="hslsx-hs__khoi-h hslsx-hs__khoi-h--tinh">
                  <Icon name="clipboard" size={15} />
                  <span className="hslsx-hs__khoi-ten">Sản phẩm &amp; đơn hàng</span>
                </h3>
                <div className="hslsx-hs__khoi-b">
                  <div className="hslsx-hs__kvs">
                    <Kv k="Tên sản phẩm" v={tt.ten} />
                    <Kv k="Loại lệnh" v={tt.loai ? (LOAI_LENH[tt.loai] ?? tt.loai) : null} />
                    <Kv
                      k="Số lượng đặt"
                      v={`${num(tt.so_luong_dat)} ${tt.don_vi_tinh ?? ""}`.trim()}
                    />
                    {/* Số đã giao của RIÊNG dòng đơn lệnh này — khác `giao_hang.da_giao` (cấp
                        NHÓM). Hai nghĩa dưới một cái tên là bẫy, nên nhãn phải nói rõ. */}
                    <Kv
                      k="Đã giao (dòng đơn này)"
                      v={td.da_giao > 0 ? num(td.da_giao) : "Chưa giao"}
                    />
                    <Kv k="Số đơn" v={tt.order_no} />
                    <Kv k="Khách hàng" v={tt.khach_hang} />
                    <Kv k="Người bán" v={tt.sale} />
                    <Kv k="Hạn giao khách" v={ngay(tt.han_giao_khach)} />
                    <Kv k="Bàn giao lúc" v={tt.ban_giao_at ? ngayGio(tt.ban_giao_at) : null} />
                    <Kv k="Tạo lệnh lúc" v={tt.tao_luc ? ngayGio(tt.tao_luc) : null} />
                  </div>
                  {tt.ghi_chu && <p className="hslsx-hs__ghichu">{tt.ghi_chu}</p>}
                </div>
              </section>

              {/* ---------- Routing ---------- */}
              <Khoi
                id="routing"
                icon="workflow"
                ten="Công đoạn & routing"
                dem={demRouting(d.routing.nodes)}
                moSan
              >
                {d.routing.nodes.length === 0 ? (
                  <Trong>
                    Lệnh chưa có bước công đoạn nào. Routing được lập ở màn Kế hoạch sản xuất.
                  </Trong>
                ) : (
                  <>
                    {/* Bước cùng LỚP = chạy SONG SONG được. Lớp là đường DÀI NHẤT từ bước gốc,
                        KHÔNG phải `thu_tu` (thứ tự bảng) — bìa và ruột có `thu_tu` 1 và 2 nhưng
                        vẫn chạy cùng lúc, xếp theo `thu_tu` là vẽ ra một chuỗi không tồn tại. */}
                    <p className="hslsx-hs__note">
                      Xếp theo <b>lớp phụ thuộc</b>: các bước cùng một lớp chạy song song được.
                    </p>
                    <BangCuon>
                      <table className="hslsx-hs__bang hslsx-hs__bang--routing">
                        <caption className="sr-only">
                          Các bước công đoạn của lệnh, nhóm theo lớp phụ thuộc
                        </caption>
                        <thead>
                          <tr>
                            <th scope="col">Bước</th>
                            <th scope="col">Trạng thái</th>
                            <th scope="col">Máy</th>
                            <th scope="col">Tổ / người</th>
                            <th scope="col">Kế hoạch</th>
                            <th scope="col">Hoàn thành</th>
                            <th scope="col">Số lượng vào → ra</th>
                          </tr>
                        </thead>
                        {lopRouting.map(([lop, nodes]) => (
                          <tbody key={lop}>
                            <tr className="hslsx-hs__loprow">
                              <td colSpan={7}>
                                Lớp {lop + 1}
                                {nodes.length > 1
                                  ? ` · ${nodes.length} bước chạy song song`
                                  : ""}
                              </td>
                            </tr>
                            {nodes.map((n) => (
                              <RoutingRow key={n.id} n={n} />
                            ))}
                          </tbody>
                        ))}
                      </table>
                    </BangCuon>
                  </>
                )}
              </Khoi>

              {/* ---------- Thông số kỹ thuật ---------- */}
              <Khoi
                id="thongso"
                icon="settings"
                ten="Thông số kỹ thuật"
                dem={d.thong_so.giay_ten ?? "chưa chọn giấy"}
              >
                <p className="hslsx-hs__note">
                  Ảnh chụp từ phiếu tính giá lúc tạo lệnh. Ô trống nghĩa là phiếu chưa khai mục
                  đó — không phải bằng 0.
                </p>
                <div className="hslsx-hs__kvs">
                  <Kv k="Giấy" v={d.thong_so.giay_ten} />
                  <Kv
                    k="Định lượng"
                    v={d.thong_so.dinh_luong == null ? null : `${so(d.thong_so.dinh_luong)} g/m²`}
                  />
                  <Kv
                    k="Khổ nguyên"
                    v={khoMm(d.thong_so.kho_nguyen_dai, d.thong_so.kho_nguyen_rong)}
                  />
                  <Kv k="Khổ tờ in" v={khoMm(d.thong_so.kho_in_dai, d.thong_so.kho_in_rong)} />
                  <Kv
                    k="Khổ thành phẩm"
                    v={khoMm(d.thong_so.dai_thanh_pham, d.thong_so.rong_thanh_pham)}
                  />
                  <Kv k="Cách in" v={nhanCachIn(d.thong_so.quy_cach_in)} />
                  <Kv k="Số màu mặt A" v={d.thong_so.so_mau_a} />
                  <Kv k="Số màu mặt B" v={d.thong_so.so_mau_b} />
                  <Kv k="Mực mặt A" v={d.thong_so.muc_a.join(", ")} />
                  <Kv k="Mực mặt B" v={d.thong_so.muc_b.join(", ")} />
                  <Kv k="Số trang" v={d.thong_so.so_trang} />
                  <Kv k="Trang mỗi tay" v={d.thong_so.trang_moi_tay} />
                  <Kv k="Số kẽm" v={d.thong_so.so_kem} />
                  <Kv k="Số mảnh xả" v={d.thong_so.so_manh_xa} />
                  <Kv k="Loại sản phẩm" v={d.thong_so.loai_san_pham} />
                  <Kv k="Số con trên tờ" v={d.thong_so.so_con} />
                  <Kv k="Số tờ kế hoạch" v={num(d.thong_so.so_to_ke_hoach)} />
                  <Kv k="Số tờ nguyên" v={num(d.thong_so.so_to_nguyen)} />
                </div>
                {d.thong_so.ghi_chu_ky_thuat && (
                  <p className="hslsx-hs__ghichu">{d.thong_so.ghi_chu_ky_thuat}</p>
                )}
              </Khoi>

              {/* ---------- Vật tư ---------- */}
              <Khoi
                id="vattu"
                icon="box"
                ten="Vật tư"
                canhBao={!d.vat_tu.hien_tai.du}
                dem={
                  d.vat_tu.hien_tai.du
                    ? "bước đang làm đủ đồ"
                    : "bước đang làm còn thiếu"
                }
                moSan
              >
                {/* BA câu hỏi khác nhau, ba danh sách. Gộp là mất nghĩa: "thiếu keo" ở bước đóng
                    gói KHÔNG phải lý do chặn ca in đang chạy, mà cũng không được phép im. */}
                <VatTuMuc
                  ten="Bước đang làm cần"
                  phu="Câu tổ trưởng hỏi trước khi bấm Bắt đầu."
                  dong={d.vat_tu.hien_tai.dong}
                  khiRong="Bước đang làm không cần vật tư nào theo bảng cân đối."
                />
                <VatTuMuc
                  ten="Bước sắp tới đang hụt"
                  phu="Câu của điều độ — để còn kịp đi mua hoặc đổi lịch."
                  dong={d.vat_tu.canh_bao_sau}
                  khiRong="Không bước nào phía sau đang hụt vật tư."
                />
                <VatTuMuc
                  ten="Kho đã cấp"
                  phu="Câu của người đi lĩnh — để khỏi xin trùng."
                  dong={d.vat_tu.da_cap}
                  khiRong="Kho chưa xuất món nào cho lệnh này."
                />
                {d.vat_tu.bo_qua.length > 0 && (
                  <div className="hslsx-hs__muc">
                    <h4 className="hslsx-hs__muc-h">Engine chưa đối chiếu được</h4>
                    {/* Một bảng vật tư im lặng bỏ sót vài món trông y hệt một bảng đủ. */}
                    <p className="hslsx-hs__note">
                      Những dòng dưới đây KHÔNG nằm trong ba mục trên — phải tự kiểm bằng tay.
                    </p>
                    <ul className="hslsx-hs__ul">
                      {d.vat_tu.bo_qua.map((r, i) => (
                        <li key={i}>
                          <b>{String(r.ma ?? "—")}</b> — {String(r.ly_do ?? "không rõ lý do")}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Khoi>

              {/* ---------- Nhân lực ---------- */}
              <Khoi
                id="nhanluc"
                icon="users"
                ten="Tổ · máy · người"
                dem={`${d.nhan_luc.hien_tai.length} bước · ${d.nhan_luc.lich_su.length} lượt đổi`}
              >
                <div className="hslsx-hs__muc">
                  <h4 className="hslsx-hs__muc-h">Đang phân công</h4>
                  {d.nhan_luc.hien_tai.length === 0 ? (
                    <Trong>Chưa có công việc nào được phát hành xuống tổ.</Trong>
                  ) : (
                    <BangCuon>
                      <table className="hslsx-hs__bang hslsx-hs__bang--nl">
                        <thead>
                          <tr>
                            <th scope="col">Việc</th>
                            <th scope="col">Tổ</th>
                            <th scope="col">Máy</th>
                            <th scope="col">Người</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.nhan_luc.hien_tai.map((b) => (
                            <tr key={b.cong_viec_id}>
                              <td>{b.ten_viec ?? "—"}</td>
                              <td>{b.to ?? "—"}</td>
                              <td>{b.may ?? "—"}</td>
                              <td>{b.nguoi.length > 0 ? b.nguoi.join(", ") : "Chưa giao ai"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </BangCuon>
                  )}
                </div>
                <div className="hslsx-hs__muc">
                  <h4 className="hslsx-hs__muc-h">Lịch sử giao · rút · đổi máy</h4>
                  {d.nhan_luc.lich_su.length === 0 ? (
                    <Trong>Chưa có lượt giao người hay đổi máy nào.</Trong>
                  ) : (
                    <ul className="hslsx-hs__ul">
                      {d.nhan_luc.lich_su.map((e, i) => (
                        <li key={i}>
                          <span className="hslsx-hs__luc">{ngayGio(e.luc)}</span>{" "}
                          {e.loai === "giao_nguoi"
                            ? `Giao ${e.nguoi} vào ${e.ten_viec ?? "việc"}`
                            : e.loai === "rut_nguoi"
                              ? `Rút ${e.nguoi} khỏi ${e.ten_viec ?? "việc"}${
                                  e.ly_do ? ` — ${e.ly_do}` : ""
                                }`
                              : `Đổi máy ${e.may_cu ?? "—"} → ${e.may_moi ?? "—"} ở ${
                                  e.ten_viec ?? "việc"
                                }${e.ly_do ? ` — ${e.ly_do}` : ""}`}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Khoi>

              {/* ---------- Sản lượng ---------- */}
              <Khoi
                id="sanluong"
                icon="layers"
                ten="Sản lượng theo lượt ghi"
                dem={`${d.san_luong.batch.length} lượt`}
              >
                {d.san_luong.batch.length === 0 ? (
                  <Trong>Chưa tổ nào ghi sản lượng cho lệnh này.</Trong>
                ) : (
                  <BangCuon>
                    <table className="hslsx-hs__bang hslsx-hs__bang--sl">
                      <thead>
                        <tr>
                          <th scope="col">Việc</th>
                          <th scope="col">Từ → đến</th>
                          <th scope="col">Tốt</th>
                          <th scope="col">Hỏng</th>
                          <th scope="col">Tổng</th>
                          <th scope="col">Mô tả lỗi</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.san_luong.batch.map((b) => (
                          <tr key={b.id}>
                            <td>
                              {b.ten_viec ?? "—"}
                              {/* Số của bước GHÉP là số của CẢ CA, không riêng lệnh này. */}
                              {b.la_buoc_ghep && <span className="hslsx-hs__chip">ca ghép</span>}
                            </td>
                            <td className="hslsx-hs__num">
                              {b.bat_dau ? ngayGio(b.bat_dau) : "—"} →{" "}
                              {b.ket_thuc ? ngayGio(b.ket_thuc) : "—"}
                            </td>
                            <td className="hslsx-hs__num">{so(b.tot)}</td>
                            <td className="hslsx-hs__num">{so(b.hong)}</td>
                            <td className="hslsx-hs__num">
                              {so(b.tong)} {nhanDonVi(b.don_vi)}
                            </td>
                            <td>{b.mo_ta_loi ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </BangCuon>
                )}
              </Khoi>

              {/* ---------- Sự cố & phiếu sửa ---------- */}
              <Khoi
                id="suco"
                icon="alert"
                ten="Sự cố & phiếu sửa"
                dem={d.su_co.length === 0 ? "không có" : `${d.su_co.length} lượt báo`}
                canhBao={d.su_co.some((s) => s.trang_thai !== "tu_choi" && s.may_dung)}
                moSan={d.su_co.length > 0}
              >
                {d.su_co.length === 0 ? (
                  <Trong>Chưa ai báo sự cố trên lệnh này.</Trong>
                ) : (
                  <ul className="hslsx-hs__cards">
                    {d.su_co.map((s) => (
                      <li key={s.id} className="hslsx-hs__card">
                        <div className="hslsx-hs__card-h">
                          <b className="hslsx-hs__ma-nho">{s.ma}</b>
                          <Pill meta={pillMeta(SU_CO_TT, s.trang_thai)} />
                          {s.may_dung && (
                            <span className="hslsx-badge hslsx-badge--signal">Máy dừng</span>
                          )}
                          <span className="hslsx-hs__luc">
                            {s.thoi_diem ? ngayGio(s.thoi_diem) : "—"}
                          </span>
                        </div>
                        <p className="hslsx-hs__card-p">
                          {[s.ten_viec, s.may, s.bo_phan_hong].filter(Boolean).join(" · ") || "—"}
                          {s.muc_do ? ` · mức ${MUC_DO[s.muc_do] ?? s.muc_do}` : ""}
                          {s.nguoi_bao ? ` · ${s.nguoi_bao} báo` : ""}
                        </p>
                        {s.mo_ta && <p className="hslsx-hs__card-p">{s.mo_ta}</p>}
                        {s.ly_do_tu_choi && (
                          <p className="hslsx-hs__card-p">Lý do từ chối: {s.ly_do_tu_choi}</p>
                        )}
                        {/* Không có phiếu ⇒ chưa ai tiếp nhận, KHÔNG phải lỗi. Nói ra để người báo
                            hỏng khỏi phải cầm điện thoại đi hỏi thợ đang làm tới đâu. */}
                        {s.phieu ? (
                          <p className="hslsx-hs__card-p hslsx-hs__card-p--phieu">
                            Phiếu sửa <b>{s.phieu.ma}</b>{" "}
                            <Pill meta={pillMeta(PHIEU_SUA_TT, s.phieu.trang_thai)} />
                            {s.phieu.nguyen_nhan_phuong_an
                              ? ` — ${s.phieu.nguyen_nhan_phuong_an}`
                              : ""}
                            {s.phieu.hoan_thanh_at
                              ? ` · xong ${ngayGio(s.phieu.hoan_thanh_at)}`
                              : ""}
                          </p>
                        ) : s.trang_thai === "cho_tiep_nhan" ? (
                          <p className="hslsx-hs__card-p hslsx-hs__card-p--phieu">
                            Tổ kỹ thuật chưa tiếp nhận — chưa có phiếu sửa.
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </Khoi>

              {/* ---------- KCS ---------- */}
              <Khoi
                id="kcs"
                icon="shield"
                ten="KCS"
                // `null` ⇒ CHƯA kiểm lô nào, khác hẳn 0 % = kiểm rồi và trượt sạch.
                //
                // Thanh tiêu đề là thứ người ta đọc KHI KHỐI ĐÓNG, nên tỉ lệ sai ở đây hỏng nặng
                // nhất: quản lý chất lượng gập khối lại, đọc "93,3 % đạt" rồi bỏ qua, trong khi
                // con số đó có thể đang trộn 1000 tờ giữa chuyền với 500 cái thành phẩm cuối.
                dem={
                  d.kcs.ty_le_dat == null
                    ? "chưa kiểm lô nào"
                    : dvKcs.so >= 2
                      ? `${d.kcs.batch.length} lô · nhiều đơn vị, không gộp được tỉ lệ`
                      : `${pct1(d.kcs.ty_le_dat)} đạt · ${d.kcs.batch.length} lô`
                }
                canhBao={d.kcs.tong_khong_dat > 0}
              >
                {d.kcs.batch.length === 0 ? (
                  <Trong>Chưa lô nào của lệnh này qua KCS.</Trong>
                ) : (
                  <>
                    {/* Câu này từng bảo chứng cho một phép cộng trộn thang: đúng về cách CHIA
                        nhưng im về chuyện tử số và mẫu số đang cộng táo với cam. Nay nó phải nói
                        đúng cả hai ca. */}
                    <p className="hslsx-hs__note">
                      {dvKcs.so >= 2 ? (
                        <>
                          Các lô của lệnh này ghi bằng <b>nhiều đơn vị khác nhau</b> nên không cộng
                          được thành một tổng, cũng không ra được một tỉ lệ chung — đọc số ở từng
                          dòng bảng dưới.
                        </>
                      ) : (
                        <>
                          Tỉ lệ tính theo <b>số lượng</b> (tổng đạt / tổng nhận), không phải trung
                          bình cộng các lô.
                        </>
                      )}
                    </p>
                    <div className="hslsx-hs__kvs">
                      <Kv k="Tổng nhận" v={tongTheoDonVi(d.kcs.tong_nhan, dvKcs)} />
                      <Kv k="Tổng đạt" v={tongTheoDonVi(d.kcs.tong_dat, dvKcs)} />
                      <Kv k="Tổng không đạt" v={tongTheoDonVi(d.kcs.tong_khong_dat, dvKcs)} />
                      <Kv
                        k="Tỉ lệ đạt"
                        v={dvKcs.so >= 2 ? NHIEU_DON_VI : pct1(d.kcs.ty_le_dat)}
                      />
                    </div>
                    <BangCuon>
                      <table className="hslsx-hs__bang hslsx-hs__bang--kcs">
                        <thead>
                          <tr>
                            <th scope="col">Việc</th>
                            <th scope="col">Xong lúc</th>
                            <th scope="col">Nhận</th>
                            <th scope="col">Đạt</th>
                            <th scope="col">Không đạt</th>
                            <th scope="col">Kết luận</th>
                            <th scope="col">Ghi chú</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.kcs.batch.map((b) => (
                            <tr key={b.id}>
                              <td>
                                {b.ten_viec ?? "—"}
                                {b.la_buoc_ghep && <span className="hslsx-hs__chip">ca ghép</span>}
                                {/* KCS CUỐI là mốc chốt hàng đạt để gửi kho — khác một lô kiểm
                                    giữa chuyền, nên phải phân biệt được bằng mắt. */}
                                {b.la_kcs_cuoi && (
                                  <span className="hslsx-hs__chip">KCS cuối</span>
                                )}
                              </td>
                              <td className="hslsx-hs__num">
                                {b.ket_thuc ? ngayGio(b.ket_thuc) : "—"}
                              </td>
                              <td className="hslsx-hs__num">{so(b.so_luong_nhan)}</td>
                              <td className="hslsx-hs__num">{so(b.so_luong_dat)}</td>
                              <td className="hslsx-hs__num">{so(b.so_luong_khong_dat)}</td>
                              <td>
                                <Pill meta={pillMeta(KCS_KET_LUAN, b.ket_luan)} />
                              </td>
                              <td>{b.ghi_chu ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </BangCuon>
                  </>
                )}
              </Khoi>

              {/* ---------- Nhập kho ---------- */}
              <Khoi
                id="kho"
                icon="warehouse"
                ten="Nhập kho"
                dem={`${d.kho.yeu_cau.length} đề nghị · ${d.kho.btp.length} lô`}
              >
                {/* Số của NHÓM, không phải phần đóng góp của riêng lệnh. `so_lenh_trong_nhom` là
                    SỐ chứ không phải cờ, nên mặt đọc tự quyết được có cộng được hay không. */}
                {d.kho.so_lenh_trong_nhom > 1 && (
                  <p className="hslsx-hs__note">
                    Nhóm thành phẩm này gồm <b>{d.kho.so_lenh_trong_nhom} lệnh</b> — các con số dưới
                    đây là của cả nhóm, không phải riêng lệnh này. Đừng cộng qua nhiều lệnh.
                  </p>
                )}
                <div className="hslsx-hs__muc">
                  <h4 className="hslsx-hs__muc-h">Đề nghị nhập kho</h4>
                  {d.kho.yeu_cau.length === 0 ? (
                    <Trong>
                      Chưa có đề nghị nhập kho nào — KCS chưa chốt được lô hàng đạt để gửi kho.
                    </Trong>
                  ) : (
                    <BangCuon>
                      <table className="hslsx-hs__bang hslsx-hs__bang--kho">
                        <thead>
                          <tr>
                            <th scope="col">Đề nghị lúc</th>
                            <th scope="col">Yêu cầu</th>
                            <th scope="col">Kho xác nhận</th>
                            <th scope="col">Còn lại</th>
                            <th scope="col">Quy cách</th>
                            <th scope="col">Trạng thái</th>
                            <th scope="col">Xác nhận lúc</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.kho.yeu_cau.map((y) => (
                            <tr key={y.id}>
                              <td className="hslsx-hs__num">
                                {y.tao_luc ? ngayGio(y.tao_luc) : "—"}
                              </td>
                              <td className="hslsx-hs__num">
                                {so(y.so_luong_yeu_cau)} {nhanDonVi(y.don_vi)}
                              </td>
                              <td className="hslsx-hs__num">{so(y.so_luong_xac_nhan)}</td>
                              <td className="hslsx-hs__num">{so(y.con_lai)}</td>
                              <td>{y.quy_cach ?? "—"}</td>
                              <td>
                                <Pill meta={pillMeta(KHO_YC_TT, y.trang_thai)} />
                              </td>
                              <td className="hslsx-hs__num">
                                {y.xac_nhan_luc ? ngayGio(y.xac_nhan_luc) : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </BangCuon>
                  )}
                </div>
                <div className="hslsx-hs__muc">
                  <h4 className="hslsx-hs__muc-h">Lô bán thành phẩm của lệnh</h4>
                  {d.kho.btp.length === 0 ? (
                    <Trong>Lệnh chưa có lô bán thành phẩm nào trong kho.</Trong>
                  ) : (
                    <BangCuon>
                      <table className="hslsx-hs__bang hslsx-hs__bang--btp">
                        <thead>
                          <tr>
                            <th scope="col">Số lượng</th>
                            <th scope="col">Phân loại</th>
                            <th scope="col">Quy cách</th>
                            <th scope="col">Kho xác nhận</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.kho.btp.map((l) => (
                            <tr key={l.id}>
                              <td className="hslsx-hs__num">
                                {so(l.so_luong)} {nhanDonVi(l.don_vi)}
                              </td>
                              <td>
                                {l.phan_loai
                                  ? (BTP_PHAN_LOAI[l.phan_loai] ?? l.phan_loai)
                                  : "—"}
                              </td>
                              <td>{l.quy_cach ?? "—"}</td>
                              <td>{l.kho_xac_nhan ? "Đã nhận" : "Chưa nhận"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </BangCuon>
                  )}
                </div>
              </Khoi>

              {/* ---------- Giao hàng ---------- */}
              <Khoi
                id="giaohang"
                icon="truck"
                ten="Giao hàng"
                dem={demGiaoHang(d.giao_hang)}
                moSan
              >
                <GiaoHangKhoi
                  gh={d.giao_hang}
                  // Chỉ mời đi lập phiếu khi CÓ hàng thật VÀ người này ghi được bên giao hàng.
                  // Bày một liên kết để rồi ăn 403 giữa luồng là đúng thứ dự án đã bỏ công gỡ.
                  choPhepLap={can("giao_hang", "create")}
                  onMoDon={onMoDon}
                />
              </Khoi>

              {/* ---------- Timeline ---------- */}
              <Khoi
                id="timeline"
                icon="history"
                ten="Dòng thời gian"
                dem={`${d.timeline.length} sự kiện`}
              >
                {d.timeline.length === 0 ? (
                  <Trong>Chưa có sự kiện nào — lệnh chưa được phát hành xuống xưởng.</Trong>
                ) : (
                  <>
                    {/* Nói ra chỗ CÒN THIẾU: nguồn `DeliveryStatusHistory` có thật, chỉ chưa nối
                        (`ho_so._timeline`). Im lặng thì người đọc tưởng chuyến giao chưa chạy. */}
                    <p className="hslsx-hs__note">
                      Cũ nhất ở trên. Chưa gồm mốc giao hàng — số đã giao xem ở khối Giao hàng.
                    </p>
                    <ol className="hslsx-hs__tl">
                      {d.timeline.map((e, i) => (
                        <li key={i} className="hslsx-hs__tl-i">
                          <span className="hslsx-hs__luc">{ngayGio(e.luc)}</span>
                          <Pill meta={pillMeta(TL_LOAI, e.loai)} />
                          <span className="hslsx-hs__tl-txt">
                            {e.noi_dung}
                            {e.nguoi ? <em> — {e.nguoi}</em> : null}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
              </Khoi>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/** `[[lớp, các bước của lớp]]` theo thứ tự lớp tăng dần. Máy chủ đã sắp `nodes` theo
 *  `(lop, thu_tu, id)` nên chỉ cần gom liền kề — KHÔNG sort lại (sort lại là bỏ mất thứ tự trong
 *  cùng một lớp mà máy chủ đã quyết). */
function gomTheoLop(nodes: LenhSxRoutingNode[]): [number, LenhSxRoutingNode[]][] {
  const ra: [number, LenhSxRoutingNode[]][] = [];
  for (const n of nodes) {
    const cuoi = ra[ra.length - 1];
    if (cuoi && cuoi[0] === n.lop) cuoi[1].push(n);
    else ra.push([n.lop, [n]]);
  }
  return ra;
}

/** Thanh tiêu đề khối Giao hàng — thứ người ta đọc KHI KHỐI ĐÓNG, nên nó không được nói ngược
 *  với thân khối.
 *
 *  `hang[]` KHÔNG phải danh sách mặt hàng: nó là danh sách cặp (mặt hàng × kho) — `san_xuat/kho.py`
 *  gom theo `(hang_id, kho_id)` — và nó GIỮ LẠI cả dòng đã giao hết (`so_toi_da = 0`). Nên
 *  `hang.length` + chữ "mặt hàng còn giao được" sai hai lần: một mặt hàng nằm 2 kho mà kho A đã
 *  cạn thì hiện "2" trong khi sự thật là 1 dòng; và khi cả nhóm `khong_tinh_duoc` thì nó khẳng
 *  định chắc nịch "còn giao được" trong lúc MỌI ô trần bên dưới ghi "chưa tính được".
 *
 *  Điều kiện phân loại lấy ĐÚNG của ô trần trong bảng (`GiaoHangRow`) để hai chỗ không lệch nhau. */
function demGiaoHang(gh: LenhSxHoSoOut["giao_hang"]): string {
  if (gh.hang.length === 0) return "chưa có hàng để giao";
  const chuaRo = gh.hang.filter((h) => h.khong_tinh_duoc || h.so_toi_da == null).length;
  const conDu = gh.hang.filter(
    (h) => !h.khong_tinh_duoc && h.so_toi_da != null && h.so_toi_da > 0,
  ).length;
  const ve: string[] = [];
  if (conDu > 0) ve.push(`${conDu} dòng kho còn giao được`);
  // Mệnh đề RIÊNG, không gộp vào số trên: "chưa biết trần" không phải "còn giao được".
  if (chuaRo > 0) ve.push(`${chuaRo} dòng chưa tính được trần`);
  if (ve.length === 0) return "đã giao hết theo sổ";
  return ve.join(" · ");
}

function demRouting(nodes: LenhSxRoutingNode[]): string {
  if (nodes.length === 0) return "chưa có bước nào";
  const xong = nodes.filter((n) => n.trang_thai === "completed").length;
  return `${xong}/${nodes.length} bước xong`;
}

/** Cách in — bốn giá trị khớp `<select>` ở màn Kế hoạch SX (`LsxDetailView.tsx`). Ảnh chụp thông
 *  số giữ nguyên KHOÁ (`mot_mat`…), và khoá là thứ chỉ máy đọc được: bày thẳng ra màn là bắt
 *  người điều độ tự dịch. Khoá lạ (ảnh chụp của lệnh cũ, hoặc danh mục thêm cách in mới) thì trả
 *  về nguyên văn — thà hiện một chữ khó đọc còn hơn nuốt mất thông số. */
const CACH_IN: Record<string, string> = {
  mot_mat: "1 mặt",
  hai_mat: "2 mặt (AB)",
  tu_tro: "Tự trở",
  tro_nhip: "Trở nhíp",
};

function nhanCachIn(v: string | null): string | null {
  if (!v) return null;
  return CACH_IN[v] ?? v;
}

/** "860 × 650 mm" — hai chiều luôn đi cùng nhau; thiếu một chiều thì cả cặp vô nghĩa nên trả
 *  `null` để ô hiện "—" thay vì "860 × — mm".
 *
 *  Đơn vị là MILIMÉT. Phiếu tính giá và màn Kế hoạch SX đều nhập khổ bằng mm
 *  (`LsxDetailView.tsx` ghi rõ `suffix="mm"` ở cả ba cặp ô), và hồ sơ chỉ chép lại ảnh chụp đó.
 *  Ghi "cm" ở đây là ra một tờ giấy nguyên "860 × 650 cm" — to bằng gian phòng. */
function khoMm(dai: number | null, rong: number | null): string | null {
  if (dai == null || rong == null) return null;
  return `${so(dai)} × ${so(rong)} mm`;
}

function RoutingRow({ n }: { n: LenhSxRoutingNode }) {
  const lb = n.loai_buoc ? LSX_LOAI_BUOC_META[n.loai_buoc as "may" | "to" | "thue_ngoai"] : null;
  const nhomLb = n.nhom ? (NHOM_CONG_DOAN[n.nhom] ?? n.nhom) : null;
  return (
    <tr className={n.la_buoc_hien_tai ? "is-buoc-hien-tai" : undefined}>
      <td>
        <span className="hslsx-hs__buocten">{n.ten ?? "—"}</span>
        <span className="hslsx-hs__chips">
          {nhomLb && <span className="hslsx-hs__chip">{nhomLb}</span>}
          {lb && (
            <span className="hslsx-hs__chip" title={lb.hint}>
              {lb.label}
            </span>
          )}
          {n.la_kcs && <span className="hslsx-hs__chip">KCS</span>}
          {/* Trạng thái/máy/người của bước ghép là sự thật của CẢ CA in, không riêng lệnh này. */}
          {n.la_buoc_ghep && (
            <span
              className="hslsx-hs__chip"
              title="Bước do một ca in ghép đảm nhiệm — trạng thái, máy và người là của cả ca"
            >
              ca ghép
            </span>
          )}
          {n.la_buoc_hien_tai && <span className="hslsx-hs__chip is-now">đang ở đây</span>}
          {n.nha_cung_cap && <span className="hslsx-hs__chip">{n.nha_cung_cap}</span>}
        </span>
      </td>
      <td>
        {/* `trang_thai = null` = bước CHƯA có công việc, khác hẳn "chờ làm" (đã phát hành, đang
            xếp hàng). Đổ chung một nhãn là nói lệnh đã xuống xưởng trong khi nó chưa. */}
        {n.trang_thai ? (
          <Pill meta={pillMeta(TT_BUOC, n.trang_thai)} />
        ) : (
          <span className="hslsx-hs__mo">Chưa phát hành</span>
        )}
      </td>
      <td>{n.may ?? "—"}</td>
      <td>
        {n.to ?? "—"}
        {n.nguoi.length > 0 && <span className="hslsx-hs__nho">{n.nguoi.join(", ")}</span>}
      </td>
      <td className="hslsx-hs__num">
        {n.du_kien_bat_dau || n.du_kien_ket_thuc ? (
          <>
            {n.du_kien_bat_dau ? ngayGio(n.du_kien_bat_dau) : "—"}
            <span className="hslsx-hs__nho">
              → {n.du_kien_ket_thuc ? ngayGio(n.du_kien_ket_thuc) : "—"}
            </span>
          </>
        ) : (
          "Chưa xếp lịch"
        )}
      </td>
      <td className="hslsx-hs__num">{n.hoan_thanh_luc ? ngayGio(n.hoan_thanh_luc) : "—"}</td>
      <td className="hslsx-hs__num">
        {/* Máy chủ ép `None → 0.0`, nên 0 ở đây KHÔNG phân biệt được với "chưa khai". */}
        {soHoac(n.so_luong_vao)} {nhanDonVi(n.don_vi_vao)} → {soHoac(n.so_luong_ra)}{" "}
        {nhanDonVi(n.don_vi_ra)}
      </td>
    </tr>
  );
}

/** MỘT mục của khối Vật tư. Ba mục dùng chung khuôn này nhưng KHÔNG gộp danh sách: chúng trả lời
 *  ba câu khác nhau và trộn vào nhau là mất nghĩa. */
function VatTuMuc({
  ten,
  phu,
  dong,
  khiRong,
}: {
  ten: string;
  phu: string;
  dong: LenhSxVatTuDong[];
  khiRong: string;
}) {
  return (
    <div className="hslsx-hs__muc">
      <h4 className="hslsx-hs__muc-h">
        {ten} <small>{phu}</small>
      </h4>
      {dong.length === 0 ? (
        <Trong>{khiRong}</Trong>
      ) : (
        <BangCuon>
          <table className="hslsx-hs__bang hslsx-hs__bang--vt">
            <thead>
              <tr>
                <th scope="col">Mặt hàng</th>
                <th scope="col">Ở bước</th>
                <th scope="col">Nhu cầu</th>
                <th scope="col">Tồn</th>
                <th scope="col">Đã cấp</th>
                <th scope="col">Đang lĩnh</th>
                <th scope="col">Thiếu</th>
                <th scope="col">Trạng thái</th>
                <th scope="col">Ngày cần</th>
              </tr>
            </thead>
            <tbody>
              {dong.map((v, i) => (
                <tr key={`${v.hang_loai}-${v.hang_id}-${v.buoc_id ?? "x"}-${i}`}>
                  <td>
                    <span className="hslsx-hs__buocten">{v.hang_ten ?? v.hang_ma ?? "—"}</span>
                    <span className="hslsx-hs__chips">
                      {v.hang_ma && <span className="hslsx-hs__chip">{v.hang_ma}</span>}
                      {/* Giấy của cả tờ in ghép vẫn là vật tư THẬT của lệnh — nhưng người đi lĩnh
                          phải biết mình đang lĩnh cho ai. */}
                      {v.pham_vi === "bai_ghep" && (
                        <span className="hslsx-hs__chip" title={`Dòng của bài ghép ${v.ma ?? ""}`}>
                          bài ghép
                        </span>
                      )}
                    </span>
                  </td>
                  <td>{v.ten_viec ?? "—"}</td>
                  <td className="hslsx-hs__num">
                    {/* `nhu_cau_hien_thi` là chuỗi engine đã dựng (kèm quy đổi) — ưu tiên nó, vì
                        con số trần mất mất đơn vị trung gian. */}
                    {v.nhu_cau_hien_thi ?? `${so(v.nhu_cau)} ${nhanDonVi(v.don_vi_goc)}`.trim()}
                  </td>
                  <td className="hslsx-hs__num">{so(v.ton)}</td>
                  <td className="hslsx-hs__num">{so(v.da_cap)}</td>
                  <td className="hslsx-hs__num">{so(v.dang_linh)}</td>
                  <td className="hslsx-hs__num">{soHoac(v.thieu)}</td>
                  <td>
                    <Pill meta={pillMeta(VT_MAU, v.trang_thai)} />
                  </td>
                  <td className="hslsx-hs__num">
                    {ngay(v.ngay_can)}
                    {v.ngay_du_hang && (
                      <span className="hslsx-hs__nho">về {ngay(v.ngay_du_hang)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </BangCuon>
      )}
    </div>
  );
}

/** Khối Giao hàng: đối chiếu tồn + đường sang form lập phiếu.
 *
 *  KHÔNG nhúng form ghi vào đây. Form "Tạo yêu cầu giao hàng" đã có, nằm trong drawer đơn hàng ở
 *  màn Đơn hàng bán, và nó TỰ nạp phần còn lại (`api.giaoHang.conPhaiGiao`). Thứ duy nhất cần
 *  truyền qua là `orderId`. */
function GiaoHangKhoi({
  gh,
  choPhepLap,
  onMoDon,
}: {
  gh: LenhSxHoSoOut["giao_hang"];
  choPhepLap: boolean;
  onMoDon?: (orderId: number) => void;
}) {
  const chuaTinhDuoc = gh.hang.filter((h) => h.khong_tinh_duoc);
  return (
    <>
      {gh.so_lenh_trong_nhom > 1 && (
        <p className="hslsx-hs__note">
          Nhóm thành phẩm gồm <b>{gh.so_lenh_trong_nhom} lệnh</b> — hai con số tổng dưới đây là của
          cả nhóm.
        </p>
      )}
      <div className="hslsx-hs__kvs">
        {/* `don_vi_lech` ⇒ nhóm có nhiều đơn vị khác nhau, con số tổng KHÔNG có nghĩa. Im nó đi
            thay vì bày ra một số cộng lẫn thùng với cái. */}
        <Kv
          k="Đã nhập kho (nhóm)"
          v={gh.don_vi_lech ? "Nhiều đơn vị — không cộng được" : so(gh.da_nhap_kho)}
        />
        <Kv
          k="Đã giao (nhóm)"
          v={gh.don_vi_lech ? "Nhiều đơn vị — không cộng được" : so(gh.da_giao)}
        />
      </div>

      {gh.hang.length === 0 ? (
        <Trong>
          {gh.nhom_id == null
            ? "Lệnh chưa vào nhóm thành phẩm nào nên chưa có gì trong kho để giao."
            : "Kho chưa xác nhận nhận lô thành phẩm nào của nhóm này."}
        </Trong>
      ) : (
        <>
          <BangCuon>
            <table className="hslsx-hs__bang hslsx-hs__bang--gh">
              <thead>
                <tr>
                  <th scope="col">Thành phẩm</th>
                  <th scope="col">Kho</th>
                  <th scope="col">Tồn thật</th>
                  <th scope="col">Còn giao được</th>
                  <th scope="col">Quy cách</th>
                </tr>
              </thead>
              <tbody>
                {gh.hang.map((h) => (
                  <GiaoHangRow key={`${h.hang_id}-${h.kho_id ?? "x"}`} h={h} />
                ))}
              </tbody>
            </table>
          </BangCuon>

          {/* ⚠️ TRẦN CHƯA TÍNH ĐƯỢC — `co_the_giao` vẫn TRUE ở ca này (tắt nút lúc kho còn hàng
              thật là cái hại nặng hơn), nên chỗ duy nhất báo được là đây. Máy chủ KHÔNG đỡ hộ:
              lưới bên giao hàng chặn theo số còn phải giao của DÒNG ĐƠN chứ không biết tồn kho. */}
          {chuaTinhDuoc.length > 0 && (
            <p className="hslsx-hs__canhbao" role="note">
              <Icon name="alert" size={14} />
              <span>
                {chuaTinhDuoc.length === gh.hang.length ? "Các" : `${chuaTinhDuoc.length}`} mặt hàng
                có ô <b>Còn giao được</b> để trống: hệ chưa dựng được ánh xạ mặt hàng ⇄ dòng đơn nên
                chưa biết đã giao bao nhiêu của riêng món đó. Hàng vẫn còn trong kho —{" "}
                <b>tự đối chiếu kho trước khi lập phiếu</b>, đừng lấy cột «Tồn thật» làm trần.
              </span>
            </p>
          )}
        </>
      )}

      {/* Liên kết CHỈ mọc khi có hàng thật + có quyền ghi + biết đơn nào. Thiếu một trong ba thì
          không vẽ gì — nút bấm vào ăn 403 (hoặc rơi vào đơn trống) là lời mời hỏng. */}
      {gh.co_the_giao && choPhepLap && gh.order_id != null && onMoDon && (
        <div className="hslsx-hs__cta">
          <Button variant="secondary" onClick={() => onMoDon(gh.order_id as number)}>
            <Icon name="truck" size={14} /> Tạo yêu cầu giao hàng
          </Button>
          <span className="hslsx-hs__nho">
            Mở đơn hàng bán — phần lập yêu cầu giao nằm trong hồ sơ đơn đó.
          </span>
        </div>
      )}
    </>
  );
}

function GiaoHangRow({ h }: { h: LenhSxGiaoHangHang }) {
  return (
    <tr className={h.khong_tinh_duoc ? "is-chua-ro" : undefined}>
      <td>
        <span className="hslsx-hs__buocten">{h.ten ?? h.ma ?? `#${h.hang_id}`}</span>
        {h.ma && <span className="hslsx-hs__nho">{h.ma}</span>}
      </td>
      <td>{h.kho_ten ?? "—"}</td>
      <td className="hslsx-hs__num">
        {so(h.so_luong)} {nhanDonVi(h.don_vi)}
      </td>
      <td className="hslsx-hs__num">
        {/* Ô TRỐNG CÓ LÝ DO, KHÔNG phải số 0 và KHÔNG ẩn dòng: hàng vẫn còn trong kho, chỉ là hệ
            chưa biết chắc đã giao bao nhiêu của riêng món này. Đổ `so_luong` vào đây là mời người
            ta lập phiếu vượt số hàng có thật. */}
        {h.khong_tinh_duoc || h.so_toi_da == null ? (
          <span className="hslsx-hs__chua-ro" title="Chưa dựng được ánh xạ mặt hàng ⇄ dòng đơn">
            chưa tính được
          </span>
        ) : (
          so(h.so_toi_da)
        )}
      </td>
      <td>{h.quy_cach ?? "—"}</td>
    </tr>
  );
}
