// Sửa chữa máy — HAI cửa vào cùng một câu chuyện "máy này hỏng", trên MỘT màn.
//
//   • Yêu cầu báo hỏng (`yeu_cau_sua_chua`): người ngoài tổ kỹ thuật — thợ đứng máy, QC, tổ
//     trưởng — nói "máy tôi hỏng". Là LỜI BÁO, chưa phải việc.
//   • Phiếu sửa chữa (`ky_thuat_may`): sổ công việc của tổ sửa chữa. Mã SC chạy liên tục, mức độ
//     là kết luận nghề, đóng phiếu đòi ảnh chứng thực.
//
// Không tách thành hai màn (dù là hai bảng, hai ô quyền): người tổ kỹ thuật phải nhìn thấy hàng
// chờ báo hỏng NGAY CẠNH hàng việc đang làm thì mới tiếp nhận kịp; bắt họ đổi màn là lời báo nằm
// đó cả ca. Chuyển cửa bằng công tắc đầu thanh công cụ, mỗi lúc chỉ một khung được gắn.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { Pager, trangHopLe } from "../components/Pager";
import { useTre } from "../lib/useTre";
import {
  kyThuatMay, NHAN_MUC_DO, NHAN_TT_SUA_CHUA, NHAN_TT_YEU_CAU, TT_SUA_CHUA, TT_YEU_CAU,
  type Anh, type MayChon, type SuaChua, type YeuCau,
} from "../api/kyThuatMay";
import { AnhBox, Badge, NhatKyPhieu, fmtNgayGio } from "./KyThuatMayChung";

const SIZE = 20;
import "./rebuild-catalog.css";
import "./ky-thuat-may.css";

const MUC_DO_CHON = ["nhe", "trung_binh", "nghiem_trong"];

interface FormState {
  may_id: string;
  bo_phan_hong: string;
  mo_ta: string;
  muc_do: string;
  nguoi_bao_ten: string;
  nguyen_nhan_phuong_an: string;
  ghi_chu: string;
}

const FORM_RONG: FormState = {
  may_id: "", bo_phan_hong: "", mo_ta: "", muc_do: "trung_binh",
  nguoi_bao_ten: "", nguyen_nhan_phuong_an: "", ghi_chu: "",
};

interface YcFormState {
  may_id: string;
  bo_phan_hong: string;
  mo_ta: string;
  muc_do: string;
  may_dung: boolean;
}

const YC_FORM_RONG: YcFormState = {
  may_id: "", bo_phan_hong: "", mo_ta: "", muc_do: "trung_binh", may_dung: false,
};

/** Ô chọn máy dùng chung cho cả hai khung. Dữ liệu lấy từ `/ky-thuat-may/may-chon` chứ KHÔNG từ
 *  danh mục thiết bị: `dm_thiet_bi` là quyền của phòng kỹ thuật, thợ đứng máy không có ⇒ dùng
 *  `mayThietBi.list` ở đây là ô chọn rỗng trơn và họ không báo hỏng được. */
function ChonMay({ giaTri, may, loiMay, khoa, onChange }: {
  giaTri: string;
  may: MayChon[];
  loiMay: string | null;
  khoa: boolean;
  onChange: (v: string) => void;
}) {
  const dangChon = may.find((m) => String(m.id) === giaTri);
  return (
    <label className="rc-field">
      <span className="rc-field__label">Máy *</span>
      <select className="rc-input" value={giaTri} disabled={khoa}
        onChange={(e) => onChange(e.target.value)}>
        <option value="">— Chọn máy —</option>
        {may.map((m) => <option key={m.id} value={m.id}>{m.ma} · {m.ten}</option>)}
      </select>
      {loiMay
        ? <span className="ktm-hint ktm-hint--loi">{loiMay}</span>
        : dangChon?.loai_may && <span className="ktm-hint">{dangChon.loai_may}</span>}
    </label>
  );
}

export function SuaChuaMayPage({ eventTick = 0, onBadgeStale }: {
  /** Nhích mỗi lần có sự kiện SSE (AppShell truyền xuống) — khung yêu cầu nạp lại theo nó để lời
   *  báo mới hiện ngay, không bắt tổ sửa chữa bấm F5. */
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const xemPhieu = can("ky_thuat_may", "read");
  // Ai vào được màn này cũng xem được hàng chờ báo hỏng: người thứ hai phải THẤY máy đó có người
  // báo rồi thì mới thôi báo trùng.
  const xemYc = can("yeu_cau_sua_chua", "read") || xemPhieu;
  const guiYcDuoc = can("yeu_cau_sua_chua", "create");
  const tiepNhanDuoc = can("ky_thuat_may", "create");
  const tuChoiDuoc = can("ky_thuat_may", "update");

  // Tổ sửa chữa mở ra là thấy VIỆC của mình trước; người ngoài chỉ có một khung nên vào thẳng.
  const [khung, setKhung] = useState<"phieu" | "yeu-cau">(xemPhieu ? "phieu" : "yeu-cau");
  const [choXuLy, setChoXuLy] = useState(0);
  const [ycTick, setYcTick] = useState(0);
  // Vừa tiếp nhận một yêu cầu ⇒ nhảy thẳng sang phiếu vừa sinh, khỏi bắt người ta đi tìm mã SC.
  const [moPhieuId, setMoPhieuId] = useState<number | null>(null);

  // Danh sách máy nạp LƯỜI và dùng chung hai khung: chỉ cần khi có ai đó mở form.
  const [may, setMay] = useState<MayChon[]>([]);
  const [loiMay, setLoiMay] = useState<string | null>(null);
  const [canMay, setCanMay] = useState(false);
  useEffect(() => {
    if (!token || !canMay || may.length > 0) return;
    setLoiMay(null);
    kyThuatMay.mayChon(token).then(setMay)
      // Nuốt lỗi ở đây là ô chọn máy rỗng trơn và người dùng tưởng xưởng chưa khai máy nào.
      .catch((e) => setLoiMay(e instanceof Error ? e.message : "Không tải được danh sách máy."));
  }, [token, canMay, may.length]);

  // Số trên công tắc = yêu cầu chưa ai tiếp nhận. Chỉ hỏi khi có quyền phiếu (cửa của endpoint) —
  // người báo hỏng không cần con số này, nó là hàng chờ của tổ sửa chữa.
  useEffect(() => {
    if (!token || !xemPhieu) return;
    kyThuatMay.choXuLy(token).then((r) => setChoXuLy(r.total)).catch(() => {});
  }, [token, xemPhieu, eventTick, ycTick]);

  const doiKhung = (k: "phieu" | "yeu-cau") => { setKhung(k); setMoPhieuId(null); };

  // Công tắc đứng ĐẦU thanh công cụ: nó đổi cả màn bên dưới, nấp ở góc phải thì không ai tìm ra.
  const chuyen = xemPhieu && xemYc ? (
    <div className="ktm-xem" role="group" aria-label="Chế độ xem">
      <button type="button" className={`ktm-xem__nut${khung === "phieu" ? " is-active" : ""}`}
        onClick={() => doiKhung("phieu")}>
        <Icon name="settings" size={14} /> Phiếu sửa chữa
      </button>
      <button type="button" className={`ktm-xem__nut${khung === "yeu-cau" ? " is-active" : ""}`}
        onClick={() => doiKhung("yeu-cau")}>
        <Icon name="bell" size={14} /> Yêu cầu báo hỏng
        {choXuLy > 0 && <span className="ktm-xem__so">{choXuLy}</span>}
      </button>
    </div>
  ) : null;

  const ycThayDoi = () => { setYcTick((t) => t + 1); onBadgeStale?.(); };

  if (khung === "phieu" && xemPhieu) {
    return (
      <KhungPhieu
        chuyen={chuyen}
        may={may} loiMay={loiMay} onCanMay={() => setCanMay(true)}
        moId={moPhieuId} onDaMo={() => setMoPhieuId(null)}
      />
    );
  }
  return (
    <KhungYeuCau
      chuyen={chuyen}
      guiDuoc={guiYcDuoc} tiepNhanDuoc={tiepNhanDuoc} tuChoiDuoc={tuChoiDuoc}
      may={may} loiMay={loiMay} onCanMay={() => setCanMay(true)}
      eventTick={eventTick}
      onThayDoi={ycThayDoi}
      onMoPhieu={xemPhieu ? (id) => { setMoPhieuId(id); setKhung("phieu"); } : undefined}
    />
  );
}

// ==================== Khung 1: phiếu sửa chữa ====================

function KhungPhieu({ chuyen, may, loiMay, onCanMay, moId, onDaMo }: {
  chuyen: ReactNode;
  may: MayChon[];
  loiMay: string | null;
  onCanMay: () => void;
  moId: number | null;
  onDaMo: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can("ky_thuat_may", "update");
  // Tạo phiếu là quyền `create`, sửa nội dung là `update` — gate chung bằng `update` thì vai chỉ
  // được lập phiếu (không được sửa) sẽ không thấy nút nào.
  const taoDuoc = can("ky_thuat_may", "create");

  const [rows, setRows] = useState<SuaChua[]>([]);
  const [dem, setDem] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const qTre = useTre(q);            // gõ xong 300ms mới hỏi máy chủ, không phải mỗi phím một request
  // Mặc định: máy CÒN NẰM. Phiếu đã đóng tích lại theo tháng, để chung là càng chạy càng phải cuộn.
  const [tab, setTab] = useState<string>("can_lam");
  const [mo, setMo] = useState<SuaChua | "new" | null>(null);

  // Lọc + tìm kiếm + phân trang ở SERVER (xem ghi chú cùng chỗ bên màn Phiếu bảo trì).
  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    kyThuatMay.listSuaChua(token, {
      q: qTre.trim() || undefined,
      trang_thai: tab === "all" ? undefined : tab,
      page,
      size: SIZE,
    })
      .then((r) => {
        setRows(r.items); setDem(r.dem ?? {}); setTotal(r.total); setError(null);
        // Đang đứng trang 3 mà bộ lọc co danh sách còn 2 trang ⇒ nhảy về trang cuối, không để
        // người dùng nhìn một bảng rỗng rồi tưởng mất sạch dữ liệu.
        const ve = trangHopLe(page, r.total, SIZE);
        if (ve !== null) setPage(ve);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, qTre, tab, page]);

  useEffect(load, [load]);

  // Vừa tiếp nhận một yêu cầu bên khung kia ⇒ mở thẳng phiếu vừa sinh. Nạp ĐÚNG phiếu đó, không
  // dò trong trang hiện tại: phiếu mới nhất chưa chắc nằm ở tab/trang đang đứng.
  useEffect(() => {
    if (!token || moId === null) return;
    kyThuatMay.getSuaChua(token, moId).then(setMo).catch(() => {}).finally(onDaMo);
  }, [token, moId]);

  useEffect(() => { if (mo === "new") onCanMay(); }, [mo, onCanMay]);

  // `rows` là trang server trả về — không lọc lại ở đây.
  const hien = rows;

  // Số trên tab đếm ở DB (`dem`), không phải đếm trang đang xem.
  const soCanLam = (dem.cho_sua ?? 0) + (dem.dang_sua ?? 0) + (dem.cho_vat_tu ?? 0);
  const tongTatCa = soCanLam + (dem.da_sua_xong ?? 0);

  const doiLoc = (fn: () => void) => { fn(); setPage(1); };

  return (
    <div className="rc ktm">
      <div className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Sửa chữa máy</h1>
          <span className="rc__count">{tongTatCa} phiếu</span>
          {soCanLam > 0 && (
            <span className="ktm-chip ktm-chip--canh-bao">
              {/* Đếm PHIẾU chưa đóng, không phải số máy: có phân trang rồi thì không gom được
                  theo máy trên toàn bảng nếu chỉ nhìn trang hiện tại — mà con số nửa vời còn tệ
                  hơn không có. */}
              <Icon name="alert" size={13} /> {soCanLam} việc chưa xong
            </span>
          )}
        </div>
        <p className="rc__sub">
          Ghi nhận máy hỏng, mô tả hiện trạng kèm ảnh, sửa xong thì đóng phiếu.
          <strong> Phải có ảnh chứng thực sau sửa mới xác nhận được.</strong>
        </p>
      </div>

      <div className="rc__unified-bar">
        {chuyen}
        <div className="rc__unified-right" style={{ marginLeft: "auto" }}>
          <div className="rc__search-wrapper">
            <Icon name="search" size={15} />
            <input className="rc__search" placeholder="Tìm mã phiếu, máy, bộ phận hỏng…"
              value={q} onChange={(e) => doiLoc(() => setQ(e.target.value))} />
          </div>
          {taoDuoc && (
            <Button variant="accent" onClick={() => setMo("new")}>
              <Icon name="plus" size={15} /> Ghi nhận máy hỏng
            </Button>
          )}
        </div>
      </div>

      <div className="rc__tabs">
        <button className={`rc__tab${tab === "can_lam" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("can_lam"))}>
          Cần làm <span className="rc__tabn">{soCanLam}</span>
        </button>
        <button className={`rc__tab${tab === "all" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("all"))}>
          Tất cả <span className="rc__tabn">{tongTatCa}</span>
        </button>
        {TT_SUA_CHUA.map((tt) => (
          <button key={tt} className={`rc__tab${tab === tt ? " is-active" : ""}`}
            onClick={() => doiLoc(() => setTab(tt))}>
            {NHAN_TT_SUA_CHUA[tt]} <span className="rc__tabn">{dem[tt] ?? 0}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={load}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "11%" }}>Mã phiếu</th>
              <th style={{ width: "18%" }}>Máy</th>
              <th>Hỏng hóc</th>
              <th style={{ width: "13%" }}>Mức độ</th>
              <th style={{ width: "14%" }}>Trạng thái</th>
              <th style={{ width: "8%" }} className="text-center">Ảnh</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: 6 }).map((__, j) => (
                    <td key={j}><span className="rc-skel" style={{ width: "70%" }} /></td>
                  ))}
                </tr>
              ))
            ) : hien.length === 0 ? (
              <tr>
                <td colSpan={6} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    {/* Cùng cỡ/nét với màn danh mục: bảng rỗng không có hình thì nhìn như lỗi render. */}
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="rc__empty-icon">
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                    </svg>
                    <p className="rc__empty-text">
                      {tongTatCa === 0
                        ? "Chưa có phiếu sửa chữa nào. Máy hỏng thì ghi nhận ngay để có vết."
                        : "Không có phiếu nào khớp bộ lọc."}
                    </p>
                    {/* Màn rỗng phải chỉ ra BƯỚC KẾ TIẾP, không bỏ người dùng đứng đó. */}
                    {tongTatCa === 0 ? (
                      taoDuoc && (
                        <Button variant="ghost" onClick={() => setMo("new")}>
                          <Icon name="plus" size={15} /> Ghi nhận máy hỏng
                        </Button>
                      )
                    ) : (
                      <Button variant="ghost" onClick={() => doiLoc(() => { setQ(""); setTab("all"); })}>
                        Xoá bộ lọc
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : hien.map((r) => (
              <tr key={r.id} className="rc__row" onClick={() => setMo(r)}>
                <td className="rc__mono rc__nowrap">
                  <span className="rc__code-badge">{r.ma}</span>
                  <div className="ktm-phu">{fmtNgayGio(r.thoi_diem)}</div>
                </td>
                <td className="rc__name">
                  {/* Cùng kiểu với bảng Phiếu bảo trì: mã máy là BADGE. Hai màn cùng nói về một cái
                      máy mà một bên badge một bên chữ trần thì người dùng phải học hai lần. */}
                  {r.may_ma ? <span className="ktm-may-badge">{r.may_ma}</span> : "—"}
                  <div className="ktm-phu">{r.may_ten ?? ""}</div>
                </td>
                <td>
                  <strong>{r.bo_phan_hong}</strong>
                  {r.mo_ta && <div className="ktm-phu ktm-phu--cat">{r.mo_ta}</div>}
                </td>
                <td><Badge kieu={`muc-${r.muc_do}`}>{NHAN_MUC_DO[r.muc_do] ?? r.muc_do}</Badge></td>
                <td><Badge kieu={`tt-${r.trang_thai}`}>{NHAN_TT_SUA_CHUA[r.trang_thai] ?? r.trang_thai}</Badge></td>
                <td className="text-center rc__nowrap">
                  {/* Cột này trả lời đúng một câu: phiếu đã đủ bằng chứng để đóng chưa. Dùng chung
                      chip với màn Phiếu bảo trì — con số trần không nói được "đủ" hay "còn thiếu". */}
                  <span className={`ktm-anhchip${r.so_anh === 0 ? "" : r.co_anh_sau ? " is-du" : " is-thieu"}`}>
                    <Icon name="camera" size={12} /> {r.so_anh} ảnh
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager total={total} page={page} size={SIZE} onPage={setPage} loading={loading} unit="phiếu" />

      {mo && (
        <SuaChuaDrawer
          phieu={mo === "new" ? null : mo}
          may={may}
          loiMay={loiMay}
          suaDuoc={suaDuoc}
          onClose={() => setMo(null)}
          onSaved={(p) => { load(); setMo(p); }}
        />
      )}
    </div>
  );
}

function SuaChuaDrawer({ phieu, may, loiMay, suaDuoc, onClose, onSaved }: {
  phieu: SuaChua | null;
  may: MayChon[];
  loiMay: string | null;
  suaDuoc: boolean;
  onClose: () => void;
  onSaved: (p: SuaChua) => void;
}) {
  const { token } = useAuth();
  const [form, setForm] = useState<FormState>(FORM_RONG);
  const [luu, setLuu] = useState(false);
  const [dangDoi, setDangDoi] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [anhTick, setAnhTick] = useState(0);   // đổi ⇒ nạp lại phiếu để cập nhật cờ `co_anh_sau`
  const [anh, setAnh] = useState<Anh[]>([]);
  const [hienTai, setHienTai] = useState<SuaChua | null>(phieu);
  const [tab, setTab] = useState<"chi-tiet" | "lich-su">("chi-tiet");

  const dong = hienTai?.trang_thai === "da_sua_xong";
  const khoaSua = !suaDuoc || dong;
  // Phiếu SINH TỪ lời báo của bộ phận khác. Không phải mọi ô đều của tổ sửa chữa: tên người báo
  // là snapshot TÀI KHOẢN đã bấm gửi yêu cầu — nó là đường duy nhất để hỏi lại khi phiếu thiếu
  // chi tiết, gõ đè một cái là đứt.
  const tuNguon = !!hienTai?.yeu_cau_ma;

  useEffect(() => {
    setHienTai(phieu);
    setForm(phieu ? {
      may_id: String(phieu.may_id),
      bo_phan_hong: phieu.bo_phan_hong ?? "",
      mo_ta: phieu.mo_ta ?? "",
      muc_do: phieu.muc_do ?? "trung_binh",
      nguoi_bao_ten: phieu.nguoi_bao_ten ?? "",
      nguyen_nhan_phuong_an: phieu.nguyen_nhan_phuong_an ?? "",
      ghi_chu: phieu.ghi_chu ?? "",
    } : FORM_RONG);
  }, [phieu]);

  // Sau khi thêm/xoá ảnh phải nạp lại phiếu: nút "Xác nhận đã sửa" mở/khoá theo `co_anh_sau` mà
  // cờ đó do backend tính. Nạp ĐÚNG một phiếu — kéo cả danh sách theo máy rồi `find` thì phiếu nằm
  // ngoài trang đầu là không thấy, và nút cứ khoá mãi dù ảnh đã tải lên.
  useEffect(() => {
    if (!token || !hienTai || anhTick === 0) return;
    kyThuatMay.getSuaChua(token, hienTai.id).then(setHienTai).catch(() => {});
  }, [anhTick, token, hienTai?.id]);

  // Ảnh nạp một lần cho cả hai khối (trước/sau) — xem ghi chú ở `AnhBox`.
  const napAnh = useCallback(() => {
    if (!token || !hienTai) { setAnh([]); return; }
    kyThuatMay.listAnh(token, "sua_chua", hienTai.id).then(setAnh)
      // Nuốt lỗi ở đây là ảnh đã tải lên rồi mà khối ảnh vẫn trống và nút xác nhận vẫn khoá —
      // không một dòng nào nói vì sao.
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách ảnh."));
  }, [token, hienTai?.id]);
  useEffect(napAnh, [napAnh]);

  const set = (k: keyof FormState, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const luuPhieu = async () => {
    if (!token) return;
    if (!form.may_id) { setLoi("Chưa chọn máy."); return; }
    if (!form.bo_phan_hong.trim()) { setLoi("Chưa ghi bộ phận hỏng."); return; }
    setLuu(true);
    setLoi(null);
    const body = {
      may_id: Number(form.may_id),
      bo_phan_hong: form.bo_phan_hong.trim(),
      mo_ta: form.mo_ta.trim() || null,
      muc_do: form.muc_do,
      // Phiếu có nguồn thì KHÔNG gửi ô này lên. Backend chặn đổi, nhưng gửi kèm giá trị cũ
      // là thừa một cửa để lỡ tay ghi đè.
      ...(tuNguon ? {} : { nguoi_bao_ten: form.nguoi_bao_ten.trim() || null }),
      nguyen_nhan_phuong_an: form.nguyen_nhan_phuong_an.trim() || null,
      ghi_chu: form.ghi_chu.trim() || null,
    };
    try {
      const p = hienTai
        ? await kyThuatMay.updateSuaChua(token, hienTai.id, body)
        : await kyThuatMay.createSuaChua(token, body);
      setHienTai(p);
      onSaved(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Lưu không thành công.");
    } finally {
      setLuu(false);
    }
  };

  const doiTrangThai = async (tt: string) => {
    // `dangDoi` chặn bấm dồn: hai lượt gọi chồng nhau thì lượt về sau ghi đè trạng thái của lượt
    // về trước, và màn hình hiện cái người dùng KHÔNG bấm cuối cùng.
    if (!token || !hienTai || dangDoi) return;
    setLoi(null);
    setDangDoi(true);
    try {
      const p = await kyThuatMay.trangThaiSuaChua(token, hienTai.id, tt);
      setHienTai(p);
      onSaved(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không đổi được trạng thái.");
    } finally {
      setDangDoi(false);
    }
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer ktm-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {hienTai ? `Phiếu sửa chữa · ${NHAN_TT_SUA_CHUA[hienTai.trang_thai] ?? ""}` : "Ghi nhận máy hỏng"}
            </div>
            <h2 className="rc-drawer__title">
              {hienTai ? `${hienTai.ma} · ${hienTai.bo_phan_hong}` : "Phiếu mới"}
            </h2>
            {hienTai && (
              <div className="ktm-meta">
                <span>{hienTai.may_ma} · {hienTai.may_ten}</span>
                {hienTai.nguoi_bao_ten && <span>Báo bởi <strong>{hienTai.nguoi_bao_ten}</strong></span>}
                <span>{fmtNgayGio(hienTai.thoi_diem)}</span>
                {/* Phiếu sinh từ lời báo của bộ phận khác: nói rõ nguồn để tổ sửa chữa biết hỏi ai
                    khi cần thêm chi tiết. Đọc NGƯỢC qua `phieu_id` bên bảng yêu cầu. */}
                {hienTai.yeu_cau_ma && (
                  <span className="ktm-tuyc">
                    <Icon name="bell" size={12} /> Từ {hienTai.yeu_cau_ma}
                    {hienTai.yeu_cau_bo_phan ? ` · ${hienTai.yeu_cau_bo_phan}` : ""}
                  </span>
                )}
              </div>
            )}
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={14} />
          </button>
        </header>

        {/* Tab chỉ hiện khi phiếu ĐÃ TỒN TẠI: phiếu mới chưa có gì để kể lại. */}
        {hienTai && (
          <div className="ktm-tab">
            <button type="button" className={`ktm-tab__nut${tab === "chi-tiet" ? " is-active" : ""}`}
              onClick={() => setTab("chi-tiet")}>Chi tiết</button>
            <button type="button" className={`ktm-tab__nut${tab === "lich-su" ? " is-active" : ""}`}
              onClick={() => setTab("lich-su")}>Lịch sử thao tác</button>
          </div>
        )}

        {/* Bọc FORM: Enter trong ô là lưu được, khỏi phải rê chuột đi tìm nút. Form ôm cả body lẫn
            chân drawer nên nút Lưu dính đáy vẫn submit đúng form này. */}
        <form className="ktm-drawer__form" onSubmit={(e) => { e.preventDefault(); void luuPhieu(); }}>
        <div className="rc-drawer__body">
          {hienTai && tab === "lich-su" ? (
            <NhatKyPhieu loai="ky_thuat_sua_chua" phieuId={hienTai.id} />
          ) : (
          <>
          {loi && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{loi}</div>}
          {dong && (
            <div className="ktm-thongbao ktm-thongbao--xong">
              <Icon name="check" size={14} /> Phiếu đã đóng ngày {fmtNgayGio(hienTai?.hoan_thanh_at)} — nội dung khoá lại.
            </div>
          )}

          {/* HAI khối chứ không một, vì HAI NGƯỜI khác nhau viết ra chúng: người phát hiện máy
              hỏng kể chuyện, tổ sửa chữa kết luận. Gộp làm một khối 7 ô trắng như nhau thì ô
              "Người báo" của phiếu sinh từ yêu cầu cũng gõ đè được — sửa xong là không còn ai
              biết ai đã báo, mà đó chính là người duy nhất trả lời được câu "hỏng thế nào". */}
          <section className="rc-sec">
            <div className="rc-sec__title">Lời báo hỏng</div>
            <div className="rc-grid">
              <ChonMay giaTri={form.may_id} may={may} loiMay={loiMay} khoa={khoaSua}
                onChange={(v) => set("may_id", v)} />

              <label className="rc-field">
                <span className="rc-field__label">Bộ phận hỏng *</span>
                <input className="rc-input" value={form.bo_phan_hong} disabled={khoaSua}
                  placeholder="vd: Trục cán & bạc đạn"
                  onChange={(e) => set("bo_phan_hong", e.target.value)} />
              </label>

              <label className="rc-field">
                <span className="rc-field__label">
                  Mức độ
                  {/* Chỉ NGHIÊM TRỌNG mới được tô. Tô cả ba mức thì cái cần chú ý chìm nghỉm —
                      đúng cái bảng danh sách đã tránh (xem `.ktm-badge--muc-*`). */}
                  {form.muc_do === "nghiem_trong" && (
                    <span className="ktm-badge ktm-badge--muc-nghiem_trong ktm-nhan-muc">Nặng</span>
                  )}
                </span>
                <select className="rc-input" value={form.muc_do} disabled={khoaSua}
                  onChange={(e) => set("muc_do", e.target.value)}>
                  {MUC_DO_CHON.map((m) => <option key={m} value={m}>{NHAN_MUC_DO[m]}</option>)}
                </select>
                {tuNguon && (
                  <span className="rc-field__hint">
                    Người báo chỉ đoán mức; mức trên phiếu là kết luận của tổ sửa chữa, sửa được.
                  </span>
                )}
              </label>

              {/* KHOÁ TẠI CHỖ, KHÔNG giấu đi: vẫn đọc được ai báo và nói luôn vì sao không sửa
                  được. Giấu ô đi thì tổ sửa chữa tưởng phiếu thiếu dữ liệu. */}
              {tuNguon ? (
                <div className="rc-field">
                  <span className="rc-field__label">Người báo</span>
                  <div className="ktm-nguon">
                    <span className="ktm-nguon__ten">
                      <Icon name="users" size={13} />
                      {hienTai?.nguoi_bao_ten || hienTai?.yeu_cau_nguoi_bao || "—"}
                      {hienTai?.yeu_cau_bo_phan && <em>· {hienTai.yeu_cau_bo_phan}</em>}
                    </span>
                    <span className="ktm-nguon__vi">
                      <Icon name="lock" size={11} />
                      Tài khoản đã gửi {hienTai?.yeu_cau_ma}. Đổi ở đây là mất dấu ai báo máy hỏng.
                    </span>
                  </div>
                </div>
              ) : (
                <label className="rc-field">
                  <span className="rc-field__label">Người báo</span>
                  {/* Phiếu tổ kỹ thuật TỰ lập: ô chữ, không tự điền người đang đăng nhập — thợ
                      đứng máy báo miệng, tổ kỹ thuật nhập hộ. */}
                  <input className="rc-input" value={form.nguoi_bao_ten} disabled={khoaSua}
                    placeholder="Ai báo máy hỏng"
                    onChange={(e) => set("nguoi_bao_ten", e.target.value)} />
                  <span className="rc-field__hint">Tên người phát hiện, không phải người đang gõ.</span>
                </label>
              )}

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Triệu chứng</span>
                <textarea className="rc-input" rows={3} value={form.mo_ta} disabled={khoaSua}
                  placeholder="Máy chạy phát tiếng ồn bất thường ở tốc độ cao, màng cán không thẳng…"
                  onChange={(e) => set("mo_ta", e.target.value)} />
                {tuNguon && (
                  <span className="rc-field__hint">
                    Chép từ {hienTai?.yeu_cau_ma}. Soi ra thêm gì thì viết nối vào, đừng xoá lời người ta.
                  </span>
                )}
              </label>
            </div>
          </section>

          <section className="rc-sec">
            <div className="rc-sec__title">Tổ sửa chữa ghi</div>
            <div className="rc-grid">
              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Nguyên nhân & phương án sửa</span>
                <textarea className="rc-input" rows={3} value={form.nguyen_nhan_phuong_an} disabled={khoaSua}
                  placeholder="Ghi khi đã soi ra nguyên nhân — vd: bạc đạn mòn, cần thay và căn chỉnh lại trục."
                  onChange={(e) => set("nguyen_nhan_phuong_an", e.target.value)} />
              </label>

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Ghi chú</span>
                {/* textarea 2 dòng, không phải input 1 dòng: ghi chú thật ("chờ bạc đạn về, hãng
                    báo thứ 5") tràn ô một dòng, và ô cao khác ô trên làm khối lệch. */}
                <textarea className="rc-input" rows={2} value={form.ghi_chu} disabled={khoaSua}
                  placeholder="vd: đang chờ bạc đạn trục cán về, hãng báo thứ 5 tới"
                  onChange={(e) => set("ghi_chu", e.target.value)} />
              </label>
            </div>
          </section>

          {hienTai && (
            <>
              <AnhBox loai="sua_chua" phieuId={hienTai.id} giaiDoan="truoc"
                tieuDe="Ảnh hiện trạng hỏng" khoa={khoaSua}
                moTa="Chụp trước khi tháo — không bắt buộc, nhưng đây là thứ giúp cãi lại được khi có tranh cãi."
                tatCaAnh={anh}
                onChanged={() => { napAnh(); setAnhTick((t) => t + 1); }} />

              <AnhBox loai="sua_chua" phieuId={hienTai.id} giaiDoan="sau"
                tieuDe="Ảnh chứng thực sau sửa" batBuoc khoa={dong}
                moTa="Bắt buộc để đóng phiếu."
                tatCaAnh={anh}
                onChanged={() => { napAnh(); setAnhTick((t) => t + 1); }} />

              {suaDuoc && (
                <section className="rc-sec">
                  <div className="rc-sec__title">Bước xử lý</div>
                  {/* Chỉ các bước ĐANG LÀM. Đóng phiếu là hành động có điều kiện ⇒ tách xuống khối
                      xác nhận riêng bên dưới, không nấp thành một pill giống mấy pill kia. */}
                  <div className="ktm-buoc">
                    {TT_SUA_CHUA.filter((tt) => tt !== "da_sua_xong").map((tt) => {
                      const dangO = hienTai.trang_thai === tt;
                      return (
                        <button key={tt} type="button"
                          className={`ktm-buoc__nut${dangO ? " is-active" : ""}`}
                          disabled={dangO || dangDoi}
                          onClick={() => doiTrangThai(tt)}>
                          {NHAN_TT_SUA_CHUA[tt]}
                        </button>
                      );
                    })}
                    {dong && <span className="ktm-buoc__da-xong">Đã sửa xong</span>}
                  </div>
                </section>
              )}

              {suaDuoc && !dong && (
                <section className="ktm-xacnhan">
                  <div className="ktm-xacnhan__title">Xác nhận đã sửa chữa xong</div>
                  {!hienTai.co_anh_sau && (
                    <p className="ktm-xacnhan__chan">
                      <Icon name="alert" size={13} /> Cần ít nhất 1 ảnh chứng thực sau sửa mới xác nhận được.
                    </p>
                  )}
                  <button type="button" className="ktm-xacnhan__nut"
                    disabled={!hienTai.co_anh_sau || dangDoi}
                    onClick={() => doiTrangThai("da_sua_xong")}>
                    <Icon name="check" size={15} /> Xác nhận đã sửa chữa xong
                  </button>
                </section>
              )}

              {/* KHÔNG có nút xoá phiếu — cũng không có endpoint (12/08/2026). Đây là lịch sử hỏng
                  hóc của máy; ghi nhầm thì sửa nội dung. */}
            </>
          )}
          </>
          )}
        </div>

        {/* Chân drawer DÍNH ĐÁY như mọi màn khác: trước đây nút Lưu nằm giữa thân, cuộn xuống
            checklist ảnh là mất dấu nó — người dùng tưởng phiếu tự lưu. */}
        {!khoaSua && (!hienTai || tab === "chi-tiet") && (
          <footer className="rc-drawer__foot">
            <Button variant="ghost" type="button" onClick={onClose}>Hủy</Button>
            <Button variant="accent" type="submit" disabled={luu}>
              {luu ? "Đang lưu…" : hienTai ? "Lưu thay đổi" : "Tạo phiếu"}
            </Button>
          </footer>
        )}
        </form>
      </aside>
    </div>
  );
}

// ==================== Khung 2: yêu cầu báo hỏng ====================

function KhungYeuCau({
  chuyen, guiDuoc, tiepNhanDuoc, tuChoiDuoc, may, loiMay, onCanMay, eventTick,
  onThayDoi, onMoPhieu,
}: {
  chuyen: ReactNode;
  guiDuoc: boolean;
  tiepNhanDuoc: boolean;
  tuChoiDuoc: boolean;
  may: MayChon[];
  loiMay: string | null;
  onCanMay: () => void;
  eventTick: number;
  onThayDoi: () => void;
  onMoPhieu?: (phieuId: number) => void;
}) {
  const { token } = useAuth();
  const [rows, setRows] = useState<YeuCau[]>([]);
  const [dem, setDem] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const qTre = useTre(q);
  const [tab, setTab] = useState<string>("cho_tiep_nhan");
  // "Chỉ của tôi" cắt NGANG các tab (một yêu cầu vừa của tôi vừa đang chờ) ⇒ là công tắc riêng,
  // không phải tab thứ năm.
  const [cuaToi, setCuaToi] = useState(false);
  const [mo, setMo] = useState<YeuCau | "new" | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    kyThuatMay.listYeuCau(token, {
      q: qTre.trim() || undefined,
      trang_thai: tab === "all" ? undefined : tab,
      cua_toi: cuaToi ? 1 : undefined,
      page,
      size: SIZE,
    })
      .then((r) => {
        setRows(r.items); setDem(r.dem ?? {}); setTotal(r.total); setError(null);
        const ve = trangHopLe(page, r.total, SIZE);
        if (ve !== null) setPage(ve);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
    // `eventTick`: có yêu cầu mới đẩy về là danh sách tự nhích, không bắt tổ sửa chữa bấm tải lại.
  }, [token, qTre, tab, cuaToi, page, eventTick]);

  useEffect(load, [load]);
  useEffect(() => { if (mo === "new") onCanMay(); }, [mo, onCanMay]);

  const soCho = dem.cho_tiep_nhan ?? 0;
  const tongTatCa = soCho + (dem.da_tao_phieu ?? 0) + (dem.tu_choi ?? 0);
  const doiLoc = (fn: () => void) => { fn(); setPage(1); };

  const sauKhiLuu = () => { load(); onThayDoi(); };

  return (
    <div className="rc ktm">
      <div className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Sửa chữa máy</h1>
          <span className="rc__count">{tongTatCa} yêu cầu</span>
          {soCho > 0 && (
            <span className="ktm-chip ktm-chip--canh-bao">
              <Icon name="alert" size={13} /> {soCho} chờ tiếp nhận
            </span>
          )}
        </div>
        <p className="rc__sub">
          Bộ phận nào thấy máy hỏng cũng báo được ngay tại đây — kèm ảnh chụp là tốt nhất.
          <strong> Tổ sửa chữa đọc rồi mới lập phiếu; nếu không lập, họ phải ghi lý do.</strong>
        </p>
      </div>

      <div className="rc__unified-bar">
        {chuyen}
        <div className="rc__unified-right" style={{ marginLeft: "auto" }}>
          <button type="button" className={`ktm-loc${cuaToi ? " is-active" : ""}`}
            aria-pressed={cuaToi} onClick={() => doiLoc(() => setCuaToi((v) => !v))}>
            <Icon name="users" size={14} /> Chỉ của tôi
          </button>
          <div className="rc__search-wrapper">
            <Icon name="search" size={15} />
            <input className="rc__search" placeholder="Tìm mã YC, máy, bộ phận hỏng, người báo…"
              value={q} onChange={(e) => doiLoc(() => setQ(e.target.value))} />
          </div>
          {guiDuoc && (
            <Button variant="accent" onClick={() => setMo("new")}>
              <Icon name="plus" size={15} /> Báo máy hỏng
            </Button>
          )}
        </div>
      </div>

      <div className="rc__tabs">
        <button className={`rc__tab${tab === "cho_tiep_nhan" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("cho_tiep_nhan"))}>
          Chờ tiếp nhận <span className="rc__tabn">{soCho}</span>
        </button>
        <button className={`rc__tab${tab === "all" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("all"))}>
          Tất cả <span className="rc__tabn">{tongTatCa}</span>
        </button>
        {TT_YEU_CAU.filter((tt) => tt !== "cho_tiep_nhan").map((tt) => (
          <button key={tt} className={`rc__tab${tab === tt ? " is-active" : ""}`}
            onClick={() => doiLoc(() => setTab(tt))}>
            {NHAN_TT_YEU_CAU[tt]} <span className="rc__tabn">{dem[tt] ?? 0}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={load}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "12%" }}>Mã YC</th>
              <th style={{ width: "18%" }}>Máy</th>
              <th>Hỏng hóc</th>
              <th style={{ width: "16%" }}>Người báo</th>
              <th style={{ width: "16%" }}>Trạng thái</th>
              <th style={{ width: "8%" }} className="text-center">Ảnh</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: 6 }).map((__, j) => (
                    <td key={j}><span className="rc-skel" style={{ width: "70%" }} /></td>
                  ))}
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="rc__empty-icon">
                      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                    </svg>
                    <p className="rc__empty-text">
                      {tongTatCa === 0
                        ? "Chưa ai báo máy hỏng. Máy trục trặc thì báo ngay — tổ sửa chữa thấy liền."
                        : tab === "cho_tiep_nhan"
                          ? "Không còn yêu cầu nào chờ tiếp nhận."
                          : "Không có yêu cầu nào khớp bộ lọc."}
                    </p>
                    {tongTatCa === 0 ? (
                      guiDuoc && (
                        <Button variant="ghost" onClick={() => setMo("new")}>
                          <Icon name="plus" size={15} /> Báo máy hỏng
                        </Button>
                      )
                    ) : (
                      <Button variant="ghost"
                        onClick={() => doiLoc(() => { setQ(""); setCuaToi(false); setTab("all"); })}>
                        Xoá bộ lọc
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : rows.map((r) => (
              <tr key={r.id} className="rc__row" onClick={() => setMo(r)}>
                <td className="rc__mono rc__nowrap">
                  <span className="rc__code-badge">{r.ma}</span>
                  <div className="ktm-phu">{fmtNgayGio(r.thoi_diem)}</div>
                </td>
                <td className="rc__name">
                  {r.may_ma ? <span className="ktm-may-badge">{r.may_ma}</span> : "—"}
                  {/* "Máy đang dừng" là dấu hiệu DUY NHẤT được ăn màu ở bảng này — nó là thứ ít
                      dòng có và là thứ đẩy yêu cầu lên đầu hàng chờ. */}
                  {r.may_dung && (
                    <span className="ktm-chip ktm-chip--dung">
                      <Icon name="pause" size={11} /> Đang dừng
                    </span>
                  )}
                  <div className="ktm-phu">{r.may_ten ?? ""}</div>
                </td>
                <td>
                  <div className="ktm-hong">
                    <strong>{r.bo_phan_hong}</strong>
                    <Badge kieu={`muc-${r.muc_do}`}>{NHAN_MUC_DO[r.muc_do] ?? r.muc_do}</Badge>
                  </div>
                  {r.mo_ta && <div className="ktm-phu ktm-phu--cat">{r.mo_ta}</div>}
                </td>
                <td>
                  {r.nguoi_bao_ten ?? "—"}
                  {r.bo_phan && <div className="ktm-phu">{r.bo_phan}</div>}
                </td>
                <td>
                  <Badge kieu={`tt-${r.trang_thai}`}>
                    {NHAN_TT_YEU_CAU[r.trang_thai] ?? r.trang_thai}
                  </Badge>
                  {r.phieu_ma && <div className="ktm-phu">{r.phieu_ma}</div>}
                </td>
                <td className="text-center rc__nowrap">
                  <span className={`ktm-anhchip${r.so_anh === 0 ? "" : " is-du"}`}>
                    <Icon name="camera" size={12} /> {r.so_anh} ảnh
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager total={total} page={page} size={SIZE} onPage={setPage} loading={loading} unit="yêu cầu" />

      {mo && (
        <YeuCauDrawer
          yc={mo === "new" ? null : mo}
          may={may} loiMay={loiMay}
          tiepNhanDuoc={tiepNhanDuoc} tuChoiDuoc={tuChoiDuoc}
          onClose={() => setMo(null)}
          onSaved={(y) => { sauKhiLuu(); setMo(y); }}
          onMoPhieu={onMoPhieu}
        />
      )}
    </div>
  );
}

function YeuCauDrawer({ yc, may, loiMay, tiepNhanDuoc, tuChoiDuoc, onClose, onSaved, onMoPhieu }: {
  yc: YeuCau | null;
  may: MayChon[];
  loiMay: string | null;
  tiepNhanDuoc: boolean;
  tuChoiDuoc: boolean;
  onClose: () => void;
  onSaved: (y: YeuCau) => void;
  onMoPhieu?: (phieuId: number) => void;
}) {
  const { token, user } = useAuth();
  const [form, setForm] = useState<YcFormState>(YC_FORM_RONG);
  const [luu, setLuu] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [anh, setAnh] = useState<Anh[]>([]);
  const [hienTai, setHienTai] = useState<YeuCau | null>(yc);
  const [tab, setTab] = useState<"chi-tiet" | "lich-su">("chi-tiet");
  // Nội dung tổ sửa chữa chỉnh lại LÚC TIẾP NHẬN — để trống là bê nguyên lời người báo.
  const [tn, setTn] = useState({ bo_phan_hong: "", muc_do: "", nguyen_nhan_phuong_an: "" });
  const [dangTiepNhan, setDangTiepNhan] = useState(false);
  const [hoiTuChoi, setHoiTuChoi] = useState(false);
  const [phieuVua, setPhieuVua] = useState<SuaChua | null>(null);

  const daXuLy = !!hienTai && hienTai.trang_thai !== "cho_tiep_nhan";
  const cuaToi = !!hienTai && !!user && hienTai.nguoi_bao_id === user.id;
  // Sửa lời báo: chính người gửi, hoặc tổ sửa chữa (họ mới là bên phải làm việc với nội dung đó).
  // Backend chốt lại y hệt ở `_kiem_chu_yeu_cau` — chỗ này chỉ để không bày nút bấm vào rồi 403.
  const khoaSua = !!hienTai && (daXuLy || !(cuaToi || tuChoiDuoc));

  useEffect(() => {
    setHienTai(yc);
    setPhieuVua(null);
    setForm(yc ? {
      may_id: String(yc.may_id),
      bo_phan_hong: yc.bo_phan_hong ?? "",
      mo_ta: yc.mo_ta ?? "",
      muc_do: yc.muc_do ?? "trung_binh",
      may_dung: yc.may_dung ?? false,
    } : YC_FORM_RONG);
    setTn({
      bo_phan_hong: yc?.bo_phan_hong ?? "",
      muc_do: yc?.muc_do ?? "trung_binh",
      nguyen_nhan_phuong_an: "",
    });
  }, [yc]);

  const napAnh = useCallback(() => {
    if (!token || !hienTai) { setAnh([]); return; }
    // Ảnh ĐỔI CHỦ sang phiếu lúc tiếp nhận ⇒ yêu cầu đã thành phiếu thì đọc theo cặp mới, đọc
    // theo `yeu_cau` sẽ ra rỗng và người báo tưởng ảnh của mình bay mất.
    const loai = hienTai.phieu_id ? "sua_chua" : "yeu_cau";
    const id = hienTai.phieu_id ?? hienTai.id;
    kyThuatMay.listAnh(token, loai, id).then(setAnh)
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách ảnh."));
  }, [token, hienTai?.id, hienTai?.phieu_id]);
  useEffect(napAnh, [napAnh]);

  const set = <K extends keyof YcFormState>(k: K, v: YcFormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const luuYc = async () => {
    if (!token) return;
    if (!form.may_id) { setLoi("Chưa chọn máy."); return; }
    if (!form.bo_phan_hong.trim()) { setLoi("Chưa ghi bộ phận hỏng."); return; }
    setLuu(true);
    setLoi(null);
    const body = {
      may_id: Number(form.may_id),
      bo_phan_hong: form.bo_phan_hong.trim(),
      mo_ta: form.mo_ta.trim() || null,
      muc_do: form.muc_do,
      may_dung: form.may_dung,
    };
    try {
      const y = hienTai
        ? await kyThuatMay.suaYeuCau(token, hienTai.id, body)
        : await kyThuatMay.taoYeuCau(token, body);
      setHienTai(y);
      onSaved(y);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Gửi không thành công.");
    } finally {
      setLuu(false);
    }
  };

  const tiepNhan = async () => {
    if (!token || !hienTai || dangTiepNhan) return;
    setLoi(null);
    setDangTiepNhan(true);
    try {
      const r = await kyThuatMay.taoPhieuTuYeuCau(token, hienTai.id, {
        bo_phan_hong: tn.bo_phan_hong.trim() || undefined,
        muc_do: tn.muc_do || undefined,
        nguyen_nhan_phuong_an: tn.nguyen_nhan_phuong_an.trim() || undefined,
      });
      setPhieuVua(r.phieu);
      setHienTai(r.yeu_cau);
      onSaved(r.yeu_cau);
    } catch (e) {
      // 409 = người khác vừa tiếp nhận trước. Câu của backend đã nói rõ phiếu nào, cứ hiện nguyên.
      setLoi(e instanceof Error ? e.message : "Không tạo được phiếu.");
    } finally {
      setDangTiepNhan(false);
    }
  };

  const tuChoi = async (lyDo: string) => {
    if (!token || !hienTai) return;
    setLoi(null);
    try {
      const y = await kyThuatMay.tuChoiYeuCau(token, hienTai.id, lyDo);
      setHienTai(y);
      onSaved(y);
      setHoiTuChoi(false);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không từ chối được.");
    }
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer ktm-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {hienTai
                ? `Yêu cầu báo hỏng · ${NHAN_TT_YEU_CAU[hienTai.trang_thai] ?? ""}`
                : "Báo máy hỏng"}
            </div>
            <h2 className="rc-drawer__title">
              {hienTai ? `${hienTai.ma} · ${hienTai.bo_phan_hong}` : "Yêu cầu mới"}
            </h2>
            {hienTai && (
              <div className="ktm-meta">
                <span>{hienTai.may_ma} · {hienTai.may_ten}</span>
                {hienTai.nguoi_bao_ten && (
                  <span>
                    Báo bởi <strong>{hienTai.nguoi_bao_ten}</strong>
                    {hienTai.bo_phan ? ` · ${hienTai.bo_phan}` : ""}
                  </span>
                )}
                <span>{fmtNgayGio(hienTai.thoi_diem)}</span>
              </div>
            )}
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={14} />
          </button>
        </header>

        {hienTai && (
          <div className="ktm-tab">
            <button type="button" className={`ktm-tab__nut${tab === "chi-tiet" ? " is-active" : ""}`}
              onClick={() => setTab("chi-tiet")}>Chi tiết</button>
            <button type="button" className={`ktm-tab__nut${tab === "lich-su" ? " is-active" : ""}`}
              onClick={() => setTab("lich-su")}>Lịch sử thao tác</button>
          </div>
        )}

        <form className="ktm-drawer__form" onSubmit={(e) => { e.preventDefault(); void luuYc(); }}>
        <div className="rc-drawer__body">
          {hienTai && tab === "lich-su" ? (
            <NhatKyPhieu loai="ky_thuat_yeu_cau" phieuId={hienTai.id} />
          ) : (
          <>
          {loi && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{loi}</div>}

          {/* Kết cục của lời báo phải nằm NGAY TRÊN CÙNG: người gửi mở ra là biết ngay được xử lý
              thế nào, không phải cuộn đi tìm. */}
          {hienTai?.trang_thai === "da_tao_phieu" && (
            <div className="ktm-thongbao ktm-thongbao--xong">
              <Icon name="check" size={14} />
              <span>
                Đã lập phiếu <strong>{hienTai.phieu_ma ?? phieuVua?.ma ?? ""}</strong>
                {hienTai.xu_ly_ten ? ` · ${hienTai.xu_ly_ten}` : ""} · {fmtNgayGio(hienTai.xu_ly_at)}
                {anh.length > 0 && " · ảnh đã chuyển sang phiếu"}
              </span>
              {onMoPhieu && hienTai.phieu_id && (
                <button type="button" className="rc__link-btn"
                  onClick={() => onMoPhieu(hienTai.phieu_id as number)}>
                  Mở phiếu
                </button>
              )}
            </div>
          )}
          {hienTai?.trang_thai === "tu_choi" && (
            <div className="ktm-thongbao ktm-thongbao--huy">
              <Icon name="ban" size={14} />
              <span>
                Không lập phiếu: <strong>{hienTai.ly_do_tu_choi}</strong>
                {hienTai.xu_ly_ten ? ` — ${hienTai.xu_ly_ten}` : ""} · {fmtNgayGio(hienTai.xu_ly_at)}
              </span>
            </div>
          )}

          <section className="rc-sec">
            <div className="rc-sec__title">Máy hỏng thế nào</div>
            <div className="rc-grid">
              <ChonMay giaTri={form.may_id} may={may} loiMay={loiMay} khoa={khoaSua}
                onChange={(v) => set("may_id", v)} />

              <label className="rc-field">
                <span className="rc-field__label">Bộ phận hỏng *</span>
                <input className="rc-input" value={form.bo_phan_hong} disabled={khoaSua}
                  placeholder="vd: Trục cán & bạc đạn"
                  onChange={(e) => set("bo_phan_hong", e.target.value)} />
              </label>

              <label className="rc-field">
                <span className="rc-field__label">Mức độ (theo bạn thấy)</span>
                <select className="rc-input" value={form.muc_do} disabled={khoaSua}
                  onChange={(e) => set("muc_do", e.target.value)}>
                  {MUC_DO_CHON.map((m) => <option key={m} value={m}>{NHAN_MUC_DO[m]}</option>)}
                </select>
                <span className="ktm-hint">Cứ chọn theo cảm nhận — tổ sửa chữa sẽ đánh giá lại.</span>
              </label>

              <label className="rc-field ktm-tick">
                {/* Đây mới là ô quyết định thứ tự hàng chờ, không phải "mức độ": máy dừng hẳn là
                    thứ người báo BIẾT CHẮC, còn mức độ chỉ là phỏng đoán. */}
                <input type="checkbox" checked={form.may_dung} disabled={khoaSua}
                  onChange={(e) => set("may_dung", e.target.checked)} />
                <span>
                  <strong>Máy đang dừng, không chạy được</strong>
                  <span className="ktm-hint">Đánh dấu là yêu cầu này lên đầu hàng chờ.</span>
                </span>
              </label>

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Triệu chứng</span>
                <textarea className="rc-input" rows={3} value={form.mo_ta} disabled={khoaSua}
                  placeholder="Kể đúng cái mình thấy: máy kêu to ở tốc độ cao, tờ in ra bị nhăn mép…"
                  onChange={(e) => set("mo_ta", e.target.value)} />
              </label>
            </div>
          </section>

          {hienTai && (
            <AnhBox loai={hienTai.phieu_id ? "sua_chua" : "yeu_cau"}
              phieuId={hienTai.phieu_id ?? hienTai.id} giaiDoan="truoc"
              tieuDe="Ảnh chỗ hỏng" khoa={khoaSua}
              moTa="Chụp bằng điện thoại là đủ — một tấm ảnh nói nhanh hơn cả đoạn mô tả."
              tatCaAnh={anh}
              onChanged={napAnh} />
          )}

          {/* Tiếp nhận là quyết định MỘT CHIỀU (sinh mã SC, kéo ảnh sang phiếu) ⇒ tách hẳn khối
              riêng, không nấp thành một nút thường lẫn giữa các ô nhập. */}
          {hienTai && !daXuLy && tiepNhanDuoc && (
            <section className="ktm-xacnhan">
              <div className="ktm-xacnhan__title">Tiếp nhận · lập phiếu sửa chữa</div>
              <p className="ktm-xacnhan__mo-ta">
                Sinh phiếu SC mới từ lời báo này; ảnh kèm theo chuyển sang phiếu. Để trống các ô
                dưới là giữ nguyên lời người báo.
              </p>
              <div className="rc-grid">
                <label className="rc-field">
                  <span className="rc-field__label">Bộ phận hỏng ghi trên phiếu</span>
                  <input className="rc-input" value={tn.bo_phan_hong}
                    onChange={(e) => setTn((s) => ({ ...s, bo_phan_hong: e.target.value }))} />
                </label>
                <label className="rc-field">
                  <span className="rc-field__label">Mức độ (tổ kỹ thuật đánh giá)</span>
                  <select className="rc-input" value={tn.muc_do}
                    onChange={(e) => setTn((s) => ({ ...s, muc_do: e.target.value }))}>
                    {MUC_DO_CHON.map((m) => <option key={m} value={m}>{NHAN_MUC_DO[m]}</option>)}
                  </select>
                </label>
                <label className="rc-field rc-field--full">
                  <span className="rc-field__label">Nguyên nhân & phương án sửa</span>
                  <textarea className="rc-input" rows={2} value={tn.nguyen_nhan_phuong_an}
                    placeholder="Ghi được ngay thì ghi, không thì bổ sung sau trong phiếu."
                    onChange={(e) => setTn((s) => ({ ...s, nguyen_nhan_phuong_an: e.target.value }))} />
                </label>
              </div>
              <button type="button" className="ktm-xacnhan__nut" disabled={dangTiepNhan}
                onClick={() => void tiepNhan()}>
                <Icon name="check" size={15} />
                {dangTiepNhan ? "Đang lập phiếu…" : "Tạo phiếu sửa chữa"}
              </button>
              {tuChoiDuoc && (
                <button type="button" className="rc__link-btn ktm-link-huy"
                  onClick={() => setHoiTuChoi(true)}>
                  Không lập phiếu · từ chối kèm lý do
                </button>
              )}
            </section>
          )}

          {/* KHÔNG có nút xoá yêu cầu — cũng không có endpoint. Bỏ một lời báo phải đi qua "từ
              chối kèm lý do": xoá lặng là người báo không bao giờ biết vì sao. */}
          </>
          )}
        </div>

        {!khoaSua && (!hienTai || tab === "chi-tiet") && (
          <footer className="rc-drawer__foot">
            <Button variant="ghost" type="button" onClick={onClose}>Hủy</Button>
            <Button variant="accent" type="submit" disabled={luu}>
              {luu ? "Đang gửi…" : hienTai ? "Lưu thay đổi" : "Gửi yêu cầu"}
            </Button>
          </footer>
        )}
        </form>
      </aside>

      <TuChoiDialog open={hoiTuChoi} ma={hienTai?.ma ?? ""}
        onCancel={() => setHoiTuChoi(false)} onConfirm={tuChoi} />
    </div>
  );
}

/** Từ chối BẮT BUỘC kèm lý do — và lý do đó đẩy thẳng về người báo. Cùng khuôn với hộp huỷ phiếu
 *  bảo trì: hộp thoại riêng, không phải `window.prompt`. */
function TuChoiDialog({ open, ma, onCancel, onConfirm }: {
  open: boolean;
  ma: string;
  onCancel: () => void;
  onConfirm: (lyDo: string) => Promise<void>;
}) {
  const [lyDo, setLyDo] = useState("");
  const [busy, setBusy] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => { if (open) { setLyDo(""); setLoi(null); } }, [open]);

  const chay = async () => {
    if (!lyDo.trim()) { setLoi("Phải ghi lý do — người báo cần đọc được vì sao."); return; }
    setBusy(true);
    setLoi(null);
    try {
      await onConfirm(lyDo.trim());
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không từ chối được.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog open={open} danger busy={busy} error={loi}
      title={<span className="ktm-dialog-title"><Icon name="ban" size={16} /> Từ chối {ma}</span>}
      confirmLabel="Từ chối yêu cầu" cancelLabel="Quay lại"
      confirmDisabled={!lyDo.trim()}
      onConfirm={() => void chay()} onCancel={onCancel}>
      <div className="ktm-boqua-form">
        <p>Yêu cầu sẽ đóng lại và người báo nhận được lý do này ngay.</p>
        <label className="rc-field">
          <span className="rc-field__label">Lý do *</span>
          <textarea className="rc-input" rows={3} value={lyDo} autoFocus
            placeholder="vd: máy này đã có YC-0004 báo cùng lỗi · chỉnh lại được tại chỗ, không cần thay"
            onChange={(e) => setLyDo(e.target.value)} />
        </label>
      </div>
    </ConfirmDialog>
  );
}
