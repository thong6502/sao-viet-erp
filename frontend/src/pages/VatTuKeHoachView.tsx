// TAB VẬT TƯ của bàn Kế hoạch sản xuất — bảng CÂN ĐỐI "cần · có · thiếu · bao giờ phải đặt".
//
// Đọc `GET /api/ke-hoach-vat-tu/can-doi`. Gom theo MẶT HÀNG: một khối = một thứ phải lo, các dòng
// bên trong là các lệnh đang giành nhau nó, xếp theo NGÀY CẦN — lệnh cần trước được tính trước, lệnh
// sau nhìn phần còn lại. Đó là toàn bộ ý nghĩa của cột "Còn lại sau".
//
// BA THỨ CỐ Ý KHÔNG CÓ, đừng thêm lại:
//   * KHÔNG có nút "Đề nghị lĩnh" — sai vai. Kế hoạch chỉ MUA; lĩnh là việc tổ trưởng làm ở màn Kho
//     khi sắp chạy máy.
//   * KHÔNG có cột tiền/giá vốn — bảng mở cho vai Kế hoạch SX, giá vốn thuộc quyền Kho/Kế toán.
//   * KHÔNG tự gửi yêu cầu mua đi — bấm xong trả về MÃ để người ta mở lên xem rồi tự gửi.
//
// Hiển thị HAI ĐƠN VỊ ở cột "Cần" ("2.961 tờ ≈ 116 kg"): kế hoạch nghĩ theo tờ, kho đếm theo đơn vị
// gốc. Hiện một cái thôi là bắt một trong hai bên nhẩm trong đầu.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CanDoiDong,
  type CanDoiKhoaDong,
  type CanDoiMau,
  type CanDoiNhom,
  type CanDoiOut,
  type HangLoai,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BangLoi, EmptyState, Skeleton, classHan, ngay, num } from "./keHoachSxShared";

/** Bốn màu — LUÔN kèm chữ, không chỉ dựa màu (a11y). Nhãn nói HỆ QUẢ, không nói màu. */
const MAU_META: Record<CanDoiMau, { label: string; cls: string; hint: string }> = {
  xam: { label: "Đã cấp đủ", cls: "khvt-pill--xam", hint: "Kho đã xuất đủ cho lệnh này." },
  xanh: { label: "Đủ trong kho", cls: "khvt-pill--xanh", hint: "Đủ bằng chính tồn đang có." },
  vang: {
    label: "Đủ nhờ hàng về",
    cls: "khvt-pill--vang",
    hint: "Chỉ đủ nếu lô hàng đang mua về đúng hẹn.",
  },
  do: { label: "Thiếu", cls: "khvt-pill--do", hint: "Không đủ — cần đặt mua thêm." },
  // Không gộp vào "Đã cấp đủ": nhãn đó mạnh hơn cả "đủ", dán lên dòng máy chưa tính nổi là nói
  // ngược sự thật — và người lập kế hoạch sẽ bỏ qua đúng thứ cần xem lại.
  khong_ro: {
    label: "Chưa đánh giá được",
    cls: "khvt-pill--khongro",
    hint: "Chưa quy đổi được về đơn vị kho — hệ thống KHÔNG đoán. Kiểm lại đơn vị của mặt hàng.",
  },
};

const KHUON_META: Record<string, string> = {
  dang_dung: "Đang dùng",
  dang_dat_lam: "Đang đặt làm",
  hong: "Hỏng",
  thanh_ly: "Đã thanh lý",
};

/** Khoá duy nhất của một dòng trong cả bảng — dùng cho tick chọn và cho payload đề nghị mua. */
function khoa(nhom: CanDoiNhom, d: CanDoiDong): string {
  return `${nhom.hang_loai}:${nhom.hang_id}:${d.lsx_id ?? ""}:${d.bai_ghep_id ?? ""}`;
}

/** Số theo đơn vị gốc — 2 chữ số thập phân, bỏ phần thập phân vô nghĩa. */
function soGoc(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

export function VatTuKeHoachView({
  eventTick,
  canDeNghiMua,
  onOpenLsx,
  onSoDo,
}: {
  /** Tăng mỗi lần có event SSE → refetch, không bắt người dùng F5. */
  eventTick?: number;
  /** Bit "tạo yêu cầu mua cho bộ phận". Thiếu thì NÚT TỰ ẨN — bảng vẫn xem được bình thường. */
  canDeNghiMua: boolean;
  onOpenLsx?: (id: number) => void;
  /** Báo ngược số dòng đỏ lên trang cha để vẽ chip trên nút tab — trang cha KHÔNG tự gọi lại API
   *  (hai lần gọi là hai con số có thể lệch nhau trong cùng một màn). */
  onSoDo?: (n: number) => void;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<CanDoiOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [chiThieu, setChiThieu] = useState(false);
  const [chon, setChon] = useState<Set<string>>(new Set());
  const [dangGui, setDangGui] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.keHoachVatTu
      .canDoi(token, { q: q.trim() || undefined, chi_thieu: chiThieu })
      .then(setData)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, q, chiThieu]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0); // debounce ô tìm
    return () => clearTimeout(t);
  }, [load, eventTick, q]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 6000);
    return () => clearTimeout(t);
  }, [flash]);

  // Tick chỉ có nghĩa với dòng ĐỎ (dòng khác không có gì để mua). Giữ map để dựng payload.
  const dongDo = useMemo(() => {
    const m = new Map<string, { nhom: CanDoiNhom; dong: CanDoiDong }>();
    for (const nhom of data?.items ?? []) {
      if (nhom.loai_nhom !== "vat_tu") continue;
      for (const d of nhom.dong) {
        if (d.trang_thai === "do") m.set(khoa(nhom, d), { nhom, dong: d });
      }
    }
    return m;
  }, [data]);

  // Dòng đã tick mà biến mất sau refetch (kho vừa cấp, hàng vừa về) phải rụng khỏi lựa chọn —
  // không thì bấm "Đề nghị mua" sẽ nhận lỗi "dòng đã đổi" mà người dùng không hiểu vì sao.
  useEffect(() => {
    setChon((cu) => {
      const moi = new Set([...cu].filter((k) => dongDo.has(k)));
      return moi.size === cu.size ? cu : moi;
    });
  }, [dongDo]);

  function toggle(k: string) {
    setChon((cu) => {
      const s = new Set(cu);
      if (s.has(k)) s.delete(k);
      else s.add(k);
      return s;
    });
  }

  function tickCaNhom(nhom: CanDoiNhom, bat: boolean) {
    const keys = nhom.dong.filter((d) => d.trang_thai === "do").map((d) => khoa(nhom, d));
    setChon((cu) => {
      const s = new Set(cu);
      for (const k of keys) {
        if (bat) s.add(k);
        else s.delete(k);
      }
      return s;
    });
  }

  async function deNghiMua() {
    if (!token || chon.size === 0) return;
    const dong: CanDoiKhoaDong[] = [...chon]
      .map((k) => dongDo.get(k))
      .filter((x): x is { nhom: CanDoiNhom; dong: CanDoiDong } => !!x)
      .map(({ nhom, dong: d }) => ({
        hang_loai: nhom.hang_loai as HangLoai,
        hang_id: nhom.hang_id,
        lsx_id: d.lsx_id,
        bai_ghep_id: d.bai_ghep_id,
      }));
    setDangGui(true);
    try {
      const r = await api.keHoachVatTu.deNghiMua(token, dong);
      setChon(new Set());
      setFlash(
        `Đã lập yêu cầu mua ${r.code}. Mở màn Mua hàng để xem lại số lượng rồi gửi — hệ thống KHÔNG tự gửi.`,
      );
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDangGui(false);
    }
  }

  const nhoms = data?.items ?? [];
  const tongDo = nhoms.reduce((s, n) => s + n.so_dong_do, 0);
  const tongKhongRo = nhoms.reduce((s, n) => s + n.so_dong_khong_ro, 0);

  // Chip trên nút tab chỉ đúng khi KHÔNG lọc — bảng đang lọc thì con số không nói về cả kế hoạch.
  useEffect(() => {
    if (data && !q.trim() && !chiThieu) onSoDo?.(tongDo + tongKhongRo);
  }, [data, q, chiThieu, tongDo, tongKhongRo, onSoDo]);

  return (
    <>
      <div className="khsx__toolbar">
        <span className="khvt-sum">
          <b>{num(nhoms.length)}</b> mặt hàng
          {tongDo > 0 && <span className="khvt-sum__do">{num(tongDo)} dòng thiếu</span>}
          {tongKhongRo > 0 && (
            <span
              className="khvt-sum__khongro"
              title="Chưa quy đổi được về đơn vị kho — hệ thống KHÔNG đoán."
            >
              {num(tongKhongRo)} chưa đánh giá được
            </span>
          )}
        </span>
        <div className="khsx__spacer" />
        <label className="khvt-toggle">
          <input
            type="checkbox"
            checked={chiThieu}
            onChange={(e) => setChiThieu(e.target.checked)}
          />
          Chỉ mặt hàng đang thiếu
        </label>
        <label className="khsx__search">
          <Icon name="search" size={14} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã lệnh / mặt hàng"
            aria-label="Tìm trong bảng cân đối vật tư"
          />
        </label>
      </div>

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          {flash}
        </div>
      )}
      {err && <BangLoi text={err} onRetry={load} />}

      {(data?.bo_qua.length ?? 0) > 0 && (
        <div className="banner banner--warn" role="status">
          <span>
            {data!.bo_qua.length} lệnh/bài chưa cân đối được:{" "}
            {data!.bo_qua.map((b) => `${b.ma} (${b.ly_do})`).join(" · ")}
          </span>
        </div>
      )}

      {data === null ? (
        <div className="khsx__tablewrap">
          <table className="khsx__table">
            <Skeleton rows={4} cols={6} />
          </table>
        </div>
      ) : nhoms.length === 0 ? (
        <EmptyState
          icon={chiThieu || q ? "search" : "packageCheck"}
          title={
            chiThieu || q
              ? "Không có mặt hàng nào khớp bộ lọc."
              : "Chưa có nhu cầu vật tư nào cần cân đối."
          }
          sub={
            chiThieu || q
              ? undefined
              : "Bảng gom nhu cầu của lệnh ở trạng thái Sẵn sàng · Đã lập kế hoạch · Đã phát hành."
          }
          action={
            chiThieu || q ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setChiThieu(false);
                  setQ("");
                }}
              >
                Xoá bộ lọc
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="khvt-list">
          {nhoms.map((nhom) =>
            nhom.loai_nhom === "cong_cu" ? (
              <KhoiCongCu key={`cc-${nhom.hang_id}`} nhom={nhom} onOpenLsx={onOpenLsx} />
            ) : (
              <KhoiMatHang
                key={`${nhom.hang_loai}-${nhom.hang_id}`}
                nhom={nhom}
                chon={chon}
                onToggle={toggle}
                onTickNhom={tickCaNhom}
                canChon={canDeNghiMua}
                onOpenLsx={onOpenLsx}
              />
            ),
          )}
        </div>
      )}

      {canDeNghiMua && chon.size > 0 && (
        <div className="khvt-bar" role="region" aria-label="Thao tác với dòng đã chọn">
          <span>
            Đã chọn <b>{chon.size}</b> dòng thiếu
          </span>
          <span className="khvt-bar__hint">
            Gộp thành MỘT yêu cầu mua, số lượng đúng phần thiếu — không làm tròn ram/kiện.
          </span>
          <Button variant="secondary" onClick={() => setChon(new Set())}>
            Bỏ chọn
          </Button>
          <Button onClick={deNghiMua} disabled={dangGui}>
            {dangGui ? "Đang lập…" : "Đề nghị mua"}
          </Button>
        </div>
      )}
    </>
  );
}

// --- Khối MẶT HÀNG (có so tồn) ----------------------------------------------
function KhoiMatHang({
  nhom,
  chon,
  onToggle,
  onTickNhom,
  canChon,
  onOpenLsx,
}: {
  nhom: CanDoiNhom;
  chon: Set<string>;
  onToggle: (k: string) => void;
  onTickNhom: (nhom: CanDoiNhom, bat: boolean) => void;
  canChon: boolean;
  onOpenLsx?: (id: number) => void;
}) {
  const keysDo = nhom.dong.filter((d) => d.trang_thai === "do").map((d) => khoa(nhom, d));
  const daTickHet = keysDo.length > 0 && keysDo.every((k) => chon.has(k));
  return (
    <section className={`khvt-card ${nhom.so_dong_do > 0 ? "khvt-card--do" : ""}`}>
      <header className="khvt-card__head">
        <div className="khvt-card__id">
          <span className="khsx__code">{nhom.hang_ma ?? "—"}</span>
          <h3 className="khvt-card__ten">{nhom.hang_ten ?? "(mặt hàng đã gỡ khỏi danh mục)"}</h3>
        </div>
        <dl className="khvt-stats">
          <div>
            <dt>Tồn</dt>
            <dd>
              {soGoc(nhom.ton)} <span className="khsx-unit">{nhom.don_vi_goc ?? ""}</span>
            </dd>
          </div>
          <div>
            <dt>Tổng cần</dt>
            <dd>
              {soGoc(nhom.tong_can)} <span className="khsx-unit">{nhom.don_vi_goc ?? ""}</span>
            </dd>
          </div>
        </dl>
        {nhom.so_dong_do > 0 && (
          <span className="khvt-badge">
            <Icon name="ban" size={11} /> {nhom.so_dong_do} dòng thiếu
          </span>
        )}
        {nhom.so_dong_khong_ro > 0 && (
          <span className="khvt-badge khvt-badge--khongro">
            <Icon name="help" size={11} /> {nhom.so_dong_khong_ro} dòng chưa đánh giá được
          </span>
        )}
        {canChon && keysDo.length > 0 && (
          <label className="khvt-tickall">
            <input
              type="checkbox"
              checked={daTickHet}
              onChange={(e) => onTickNhom(nhom, e.target.checked)}
            />
            Chọn hết dòng thiếu
          </label>
        )}
      </header>

      <div className="khsx__tablewrap">
        <table className="khsx__table khvt-table">
          <caption className="sr-only">
            Các lệnh cần {nhom.hang_ten}, xếp theo ngày cần
          </caption>
          <thead>
            <tr>
              {canChon && <th scope="col" className="khvt-th--tick"><span className="sr-only">Chọn</span></th>}
              <th scope="col">Ngày cần</th>
              <th scope="col">Lệnh / Bài</th>
              <th scope="col" className="khsx-th--num">Cần</th>
              <th scope="col" className="khsx-th--num">Còn lại sau</th>
              <th scope="col">Trạng thái</th>
              <th scope="col" className="khsx__col--opt">Hạn đặt</th>
            </tr>
          </thead>
          <tbody>
            {nhom.dong.map((d) => {
              const k = khoa(nhom, d);
              const meta = MAU_META[d.trang_thai];
              const chonDuoc = canChon && d.trang_thai === "do";
              return (
                <tr key={k} className={`khsx__row ${chon.has(k) ? "khvt-row--chon" : ""}`}>
                  {canChon && (
                    <td className="khvt-td--tick">
                      {chonDuoc ? (
                        <input
                          type="checkbox"
                          checked={chon.has(k)}
                          onChange={() => onToggle(k)}
                          aria-label={`Chọn dòng ${d.ma} để đề nghị mua`}
                        />
                      ) : null}
                    </td>
                  )}
                  <td className={`khsx-num ${d.moc_tam ? "" : classHan(d.ngay_can)}`}>
                    {ngay(d.ngay_can)}
                    {d.moc_tam && (
                      <div className="khvt-tam" title="Bước chưa xếp lịch — mốc suy từ hạn sản xuất trừ tổng thời gian dẫn, chưa phải giờ chốt.">
                        mốc tạm
                      </div>
                    )}
                  </td>
                  <td>
                    {d.lsx_id && onOpenLsx ? (
                      <button
                        type="button"
                        className="khvt-link"
                        onClick={() => onOpenLsx(d.lsx_id!)}
                      >
                        {d.ma}
                      </button>
                    ) : (
                      <span className="khsx__code">{d.ma}</span>
                    )}
                    {d.ten_viec && <div className="khsx__sub">{d.ten_viec}</div>}
                  </td>
                  <td className="khsx-num">
                    {d.nhu_cau_hien_thi}
                    {(d.da_cap ?? 0) > 0 && (
                      <div className="khsx__sub">đã cấp {soGoc(d.da_cap)}</div>
                    )}
                    {(d.dang_linh ?? 0) > 0 && (
                      <div
                        className="khsx__sub"
                        title="Đề nghị kho đã lập nhưng CHƯA ghi sổ — hàng vẫn còn trong kho, nên không trừ vào tồn."
                      >
                        đang lĩnh {soGoc(d.dang_linh)}
                      </div>
                    )}
                  </td>
                  <td className={`khsx-num ${(d.con_lai_sau ?? 0) < 0 ? "khsx__bad" : ""}`}>
                    {soGoc(d.con_lai_sau)}
                    {(d.thieu ?? 0) > 0 && (
                      <div className="khsx__sub khsx__sub--do">thiếu {soGoc(d.thieu)}</div>
                    )}
                  </td>
                  <td>
                    <span className={`khsx-pill ${meta.cls}`} title={meta.hint}>
                      <span className="khsx-pill__dot" aria-hidden="true" />
                      {meta.label}
                    </span>
                    {d.canh_bao.includes("khong_doi_chieu_duoc") && (
                      <div className="khsx-warn-inline" title={d.ly_do_canh_bao ?? undefined}>
                        <Icon name="help" size={11} /> chưa quy đổi được đơn vị
                      </div>
                    )}
                  </td>
                  <td className="khsx__col--opt">
                    {d.han_dat ? (
                      <div className={`khsx-num ${d.dat_muon ? "khsx-date--late" : classHan(d.han_dat)}`}>
                        {ngay(d.han_dat)}
                      </div>
                    ) : (
                      <span className="khsx-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --- Khối CÔNG CỤ (khuôn bế — KHÔNG so tồn) ---------------------------------
function KhoiCongCu({
  nhom,
  onOpenLsx,
}: {
  nhom: CanDoiNhom;
  onOpenLsx?: (id: number) => void;
}) {
  return (
    <section className={`khvt-card khvt-card--cc ${nhom.so_dong_do > 0 ? "khvt-card--do" : ""}`}>
      <header className="khvt-card__head">
        <div className="khvt-card__id">
          <span className="khsx__code">{nhom.hang_ma ?? "KHUÔN"}</span>
          <h3 className="khvt-card__ten">{nhom.hang_ten}</h3>
        </div>
        <span className="khsx-chip khsx-chip--ngoai">
          <Icon name="workflow" size={11} /> công cụ — không so tồn
        </span>
        {nhom.khuon_tinh_trang && (
          <span className="khsx__sub">
            {KHUON_META[nhom.khuon_tinh_trang] ?? nhom.khuon_tinh_trang}
            {nhom.khuon_ngay_ve && ` · về ${ngay(nhom.khuon_ngay_ve)}`}
          </span>
        )}
        {nhom.so_dong_do > 0 && (
          <span className="khvt-badge">
            <Icon name="ban" size={11} /> {nhom.so_dong_do} lệnh chưa có khuôn
          </span>
        )}
      </header>
      {/* KHÔNG có nút "Đề nghị đặt làm" (chủ chốt 2026-08-09): khuôn không nằm trong danh mục mặt
          hàng nên không đi được đường mua hàng tự động. Nhưng bảng đã bày đủ để người kế hoạch tự
          xử — chỉ thiếu câu chỉ đường, mà thiếu nó thì người ta đứng nhìn dòng đỏ không biết làm gì. */}
      {nhom.so_dong_do > 0 && (
        <p className="khvt-cc-nhac">
          Khuôn không đi qua đường mua hàng tự động. Sang <b>Mua hàng → Yêu cầu của bộ phận</b> lập
          phiếu đặt làm, ghi mã khuôn <b>{nhom.hang_ma ?? "—"}</b> và mã lệnh cần nó vào ghi chú.
        </p>
      )}
      <div className="khsx__tablewrap">
        <table className="khsx__table khvt-table">
          <caption className="sr-only">Các lệnh cần khuôn này</caption>
          <thead>
            <tr>
              <th scope="col">Ngày cần</th>
              <th scope="col">Lệnh</th>
              <th scope="col">Bước</th>
              <th scope="col">Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {nhom.dong.map((d) => {
              const meta = MAU_META[d.trang_thai];
              return (
                <tr key={`${d.lsx_id}`} className="khsx__row">
                  <td className={`khsx-num ${d.moc_tam ? "" : classHan(d.ngay_can)}`}>
                    {ngay(d.ngay_can)}
                    {d.moc_tam && <div className="khvt-tam">mốc tạm</div>}
                  </td>
                  <td>
                    {d.lsx_id && onOpenLsx ? (
                      <button type="button" className="khvt-link" onClick={() => onOpenLsx(d.lsx_id!)}>
                        {d.ma}
                      </button>
                    ) : (
                      <span className="khsx__code">{d.ma}</span>
                    )}
                  </td>
                  <td>{d.ten_viec ?? "—"}</td>
                  <td>
                    <span className={`khsx-pill ${meta.cls}`} title={meta.hint}>
                      <span className="khsx-pill__dot" aria-hidden="true" />
                      {d.trang_thai === "do"
                        ? "Chưa sẵn sàng"
                        : d.trang_thai === "vang"
                          ? "Đang đặt làm, về kịp"
                          : "Sẵn sàng"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
