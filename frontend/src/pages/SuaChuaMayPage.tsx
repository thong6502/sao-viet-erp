// Sửa chữa máy — MỘT phiếu chạy từ lúc ghi nhận hỏng tới lúc sửa xong.
//
// Cố ý không tách "báo hỏng" và "sửa chữa" thành hai chứng từ: cùng một máy, cùng một lần hỏng,
// tách ra là bắt thợ nhập hai lần rồi tự đi nối lại. Không có bước duyệt — một vai thao tác, cái
// gác cửa là ẢNH chứng thực chứ không phải chữ ký người thứ hai.
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import {
  kyThuatMay, NHAN_MUC_DO, NHAN_TT_SUA_CHUA, TT_SUA_CHUA, type SuaChua,
} from "../api/kyThuatMay";
import { AnhBox, Badge, NhatKyPhieu, PhanTrang, fmtNgayGio } from "./KyThuatMayChung";

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

export function SuaChuaMayPage() {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can("ky_thuat_may", "update");

  const [rows, setRows] = useState<SuaChua[]>([]);
  const [dem, setDem] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  // Mặc định: máy CÒN NẰM. Phiếu đã đóng tích lại theo tháng, để chung là càng chạy càng phải cuộn.
  const [tab, setTab] = useState<string>("can_lam");
  const [mo, setMo] = useState<SuaChua | "new" | null>(null);
  const [may, setMay] = useState<Row[]>([]);

  // Lọc + tìm kiếm + phân trang ở SERVER (xem ghi chú cùng chỗ bên màn Phiếu bảo trì).
  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    kyThuatMay.listSuaChua(token, {
      q: q.trim() || undefined,
      trang_thai: tab === "all" ? undefined : tab,
      page,
      size: SIZE,
    })
      .then((r) => { setRows(r.items); setDem(r.dem ?? {}); setTotal(r.total); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, q, tab, page]);

  useEffect(load, [load]);
  useEffect(() => {
    if (!token) return;
    mayThietBi.list(token).then((r) => setMay(r.items)).catch(() => setMay([]));
  }, [token]);

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
        <div className="rc__unified-right" style={{ marginLeft: "auto" }}>
          <div className="rc__search-wrapper">
            <Icon name="search" size={15} />
            <input className="rc__search" placeholder="Tìm mã phiếu, máy, bộ phận hỏng…"
              value={q} onChange={(e) => doiLoc(() => setQ(e.target.value))} />
          </div>
          {suaDuoc && (
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
              Array.from({ length: 4 }).map((_, i) => (
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
                    <p className="rc__empty-text">
                      {tongTatCa === 0
                        ? "Chưa có phiếu sửa chữa nào. Máy hỏng thì ghi nhận ngay để có vết."
                        : "Không có phiếu nào khớp bộ lọc."}
                    </p>
                    {/* Màn rỗng phải chỉ ra BƯỚC KẾ TIẾP, không bỏ người dùng đứng đó. */}
                    {tongTatCa === 0 ? (
                      suaDuoc && (
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
                  {r.may_ma ?? "—"}
                  <div className="ktm-phu">{r.may_ten ?? ""}</div>
                </td>
                <td>
                  <strong>{r.bo_phan_hong}</strong>
                  {r.mo_ta && <div className="ktm-phu ktm-phu--cat">{r.mo_ta}</div>}
                </td>
                <td><Badge kieu={`muc-${r.muc_do}`}>{NHAN_MUC_DO[r.muc_do] ?? r.muc_do}</Badge></td>
                <td><Badge kieu={`tt-${r.trang_thai}`}>{NHAN_TT_SUA_CHUA[r.trang_thai] ?? r.trang_thai}</Badge></td>
                <td className="text-center rc__nowrap">
                  {/* Cột này trả lời đúng một câu: phiếu đã đủ bằng chứng để đóng chưa. */}
                  {r.so_anh > 0 ? (
                    <span className={r.co_anh_sau ? "ktm-anhdem is-du" : "ktm-anhdem"}>{r.so_anh}</span>
                  ) : <span className="ktm-anhdem is-trong">0</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PhanTrang page={page} size={SIZE} total={total} onDoi={setPage} />

      {mo && (
        <SuaChuaDrawer
          phieu={mo === "new" ? null : mo}
          may={may}
          suaDuoc={suaDuoc}
          onClose={() => setMo(null)}
          onSaved={(p) => { load(); setMo(p); }}
        />
      )}
    </div>
  );
}

function SuaChuaDrawer({ phieu, may, suaDuoc, onClose, onSaved }: {
  phieu: SuaChua | null;
  may: Row[];
  suaDuoc: boolean;
  onClose: () => void;
  onSaved: (p: SuaChua) => void;
}) {
  const { token } = useAuth();
  const [form, setForm] = useState<FormState>(FORM_RONG);
  const [luu, setLuu] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [anhTick, setAnhTick] = useState(0);   // đổi ⇒ nạp lại phiếu để cập nhật cờ `co_anh_sau`
  const [hienTai, setHienTai] = useState<SuaChua | null>(phieu);
  const [tab, setTab] = useState<"chi-tiet" | "lich-su">("chi-tiet");

  const dong = hienTai?.trang_thai === "da_sua_xong";
  const khoaSua = !suaDuoc || dong;

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
  // cờ đó do backend tính.
  useEffect(() => {
    if (!token || !hienTai || anhTick === 0) return;
    kyThuatMay.listSuaChua(token, { may_id: hienTai.may_id })
      .then((r) => {
        const moi = r.items.find((x) => x.id === hienTai.id);
        if (moi) setHienTai(moi);
      })
      .catch(() => {});
  }, [anhTick, token, hienTai?.id]);

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
      nguoi_bao_ten: form.nguoi_bao_ten.trim() || null,
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
    if (!token || !hienTai) return;
    setLoi(null);
    try {
      const p = await kyThuatMay.trangThaiSuaChua(token, hienTai.id, tt);
      setHienTai(p);
      onSaved(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không đổi được trạng thái.");
    }
  };

  const mayHienTai = may.find((m) => String(m.id) === form.may_id);

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

          <section className="rc-sec">
            <div className="rc-sec__title">Chi tiết hỏng hóc</div>
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Máy *</span>
                <select className="rc-input" value={form.may_id} disabled={khoaSua}
                  onChange={(e) => set("may_id", e.target.value)}>
                  <option value="">— Chọn máy —</option>
                  {may.map((m) => (
                    <option key={m.id} value={m.id}>{String(m.ma)} · {String(m.ten)}</option>
                  ))}
                </select>
                {mayHienTai && <span className="ktm-hint">{String(mayHienTai.loai_may ?? "")}</span>}
              </label>

              <label className="rc-field">
                <span className="rc-field__label">Bộ phận hỏng *</span>
                <input className="rc-input" value={form.bo_phan_hong} disabled={khoaSua}
                  placeholder="vd: Trục cán & bạc đạn"
                  onChange={(e) => set("bo_phan_hong", e.target.value)} />
              </label>

              <label className="rc-field">
                <span className="rc-field__label">Mức độ</span>
                <select className="rc-input" value={form.muc_do} disabled={khoaSua}
                  onChange={(e) => set("muc_do", e.target.value)}>
                  {MUC_DO_CHON.map((m) => <option key={m} value={m}>{NHAN_MUC_DO[m]}</option>)}
                </select>
              </label>

              <label className="rc-field">
                <span className="rc-field__label">Người báo</span>
                {/* Ô CHỮ, không tự điền người đang đăng nhập: thợ đứng máy báo miệng, tổ kỹ thuật
                    nhập hộ — lấy tên người đang gõ là ghi sai ngay từ đầu. */}
                <input className="rc-input" value={form.nguoi_bao_ten} disabled={khoaSua}
                  placeholder="Ai báo máy hỏng"
                  onChange={(e) => set("nguoi_bao_ten", e.target.value)} />
              </label>

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Triệu chứng</span>
                <textarea className="rc-input" rows={3} value={form.mo_ta} disabled={khoaSua}
                  placeholder="Máy chạy phát tiếng ồn bất thường ở tốc độ cao, màng cán không thẳng…"
                  onChange={(e) => set("mo_ta", e.target.value)} />
              </label>

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Nguyên nhân & phương án sửa</span>
                <textarea className="rc-input" rows={3} value={form.nguyen_nhan_phuong_an} disabled={khoaSua}
                  placeholder="Ghi khi đã soi ra nguyên nhân — vd: bạc đạn mòn, cần thay và căn chỉnh lại trục."
                  onChange={(e) => set("nguyen_nhan_phuong_an", e.target.value)} />
              </label>

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Ghi chú</span>
                <input className="rc-input" value={form.ghi_chu} disabled={khoaSua}
                  placeholder="vd: đang chờ bạc đạn trục cán về"
                  onChange={(e) => set("ghi_chu", e.target.value)} />
              </label>
            </div>

            {!khoaSua && (
              <div className="ktm-actions">
                <Button variant="accent" onClick={luuPhieu} disabled={luu}>
                  {luu ? "Đang lưu…" : hienTai ? "Lưu thay đổi" : "Tạo phiếu"}
                </Button>
              </div>
            )}
          </section>

          {hienTai && (
            <>
              <AnhBox loai="sua_chua" phieuId={hienTai.id} giaiDoan="truoc"
                tieuDe="Ảnh hiện trạng hỏng" khoa={khoaSua}
                moTa="Chụp trước khi tháo — không bắt buộc, nhưng đây là thứ giúp cãi lại được khi có tranh cãi."
                onChanged={() => setAnhTick((t) => t + 1)} />

              <AnhBox loai="sua_chua" phieuId={hienTai.id} giaiDoan="sau"
                tieuDe="Ảnh chứng thực sau sửa" batBuoc khoa={dong}
                moTa="Bắt buộc để đóng phiếu."
                onChanged={() => setAnhTick((t) => t + 1)} />

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
                          disabled={dangO}
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
                    disabled={!hienTai.co_anh_sau}
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
      </aside>
    </div>
  );
}
