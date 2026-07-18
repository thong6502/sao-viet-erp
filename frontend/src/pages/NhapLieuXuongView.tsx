// MÀN THỢ — Nhập liệu xưởng (Chunk 8, TEXTLESS). Cho thợ/tổ trưởng ít chữ, thao tác bằng TRÍ NHỚ.
//
// LUỒNG CỐ ĐỊNH (thành phản xạ):
//   1) Quét QR / gõ MÃ LỆNH (bàn phím số TO) → mở lệnh.
//   2) Chọn công đoạn (icon+màu) → gõ ĐẠT / HỎNG (số TO) → 1 chạm "GHI SỐ".
//   3) "GIAO" số đạt sang tổ kế · phía nhận bấm "NHẬN" (1 chạm).
//   4) QC: chụp ảnh lỗi + chọn tổ bị quy → gửi · tổ trưởng "XÁC NHẬN".
//
// Gần như KHÔNG CHỮ: icon + MÀU (moss=chạy/đạt · amber=chờ · signal=lỗi/hỏng · rust=hành động) +
// SỐ TO. Nút TO cho tay dính mực/đeo găng. Máy CHỈ GHI NHẬN — không lọc/validate; backend chặn cổng
// cứng (chưa phát → 409) thì hiện icon/màu đỏ, ít chữ.
//
// Nền dữ liệu (đọc, resolve như các màn LSX khác): công đoạn = catalog `cong_doan`; tổ = phòng ban;
// ấn phẩm/khách = Đơn theo (order_id, phieu_thanh_phan_id); tổ của người đăng nhập = Employee.department_id.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  assetUrl,
  type BanGiaoRow,
  type Department,
  type LenhSXDetailOut,
  type OrderDetail,
  type QcDefectRow,
} from "../api/client";
import { congDoan, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { ToastStack, useToasts } from "./LsxToast";
import "./lenh-san-xuat.css";
import "./nhap-lieu-xuong.css";

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;
const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";
const numOrNull = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

const MAX_CODE = 6;
const MAX_CNT = 7;
/** Áp 1 phím số vào chuỗi (thay '0' dẫn đầu, cắt độ dài). k ∈ "0".."9" | "back" | "clear". */
function applyKey(cur: string, k: string, max: number): string {
  if (k === "clear") return "";
  if (k === "back") return cur.slice(0, -1);
  return ((cur === "0" ? "" : cur) + k).slice(0, max);
}
const toInt = (s: string): number => {
  const n = parseInt(s, 10);
  return Number.isFinite(n) && n >= 0 ? n : 0;
};

// Thứ tự nhóm công đoạn (vị trí CỐ ĐỊNH để thợ nhớ chỗ bấm): trước in → in → sau in.
const NHOM_RANK: Record<string, number> = { prepress: 0, print: 1, finishing: 2 };
const nhomOf = (c: Row): string => String(c.nhom ?? "finishing");
const cdName = (c: Row): string =>
  String(c.ten_hien_thi ?? c.ten ?? c.ma ?? `#${c.id}`);

// Trạng thái lệnh → màu + icon (thợ đọc bằng MÀU, không bằng chữ).
type StateVariant = "run" | "wait" | "done" | "danger";
const LENH_STATE: Record<string, { variant: StateVariant; label: string }> = {
  dang_chay: { variant: "run", label: "Đang chạy" },
  nhap: { variant: "wait", label: "Chờ phát" },
  xong: { variant: "done", label: "Xong" },
  huy: { variant: "danger", label: "Đã hủy" },
};

export function NhapLieuXuongView() {
  const { token } = useAuth();
  const toasts = useToasts();

  // --- Catalog (tải 1 lần) ---
  const [congDoans, setCongDoans] = useState<Row[]>([]);
  const [depts, setDepts] = useState<Department[]>([]);
  const [myDeptId, setMyDeptId] = useState<number | null>(null);

  // --- Entry (quét/gõ mã) ---
  const [code, setCode] = useState("");

  // --- Lệnh đang mở ---
  const [detail, setDetail] = useState<LenhSXDetailOut | null>(null);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [lenhLoading, setLenhLoading] = useState(false);
  const [lenhErr, setLenhErr] = useState<string | null>(null);

  // --- Ghi sản lượng ---
  const [selCd, setSelCd] = useState<number | null>(null);
  const [active, setActive] = useState<"dat" | "hong">("dat");
  const [soDat, setSoDat] = useState("");
  const [soHong, setSoHong] = useState("");
  const [recording, setRecording] = useState(false);
  const [flash, setFlash] = useState(false);

  // --- Giao ---
  const [giaoOpen, setGiaoOpen] = useState(false);
  const [giaoTo, setGiaoTo] = useState<number | null>(null);
  const [giaoSo, setGiaoSo] = useState("");
  const [giaoing, setGiaoing] = useState(false);

  // --- QC ---
  const [qcAnh, setQcAnh] = useState<string | null>(null);
  const [qcTo, setQcTo] = useState<number | null>(null);
  const [qcSending, setQcSending] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // --- Busy 1 hành động (nhận/xác nhận QC) ---
  const [busyId, setBusyId] = useState<string | null>(null);

  // Catalog load.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      const [cd, dp, me] = await Promise.all([
        congDoan.list(token).then((r) => r.items).catch(() => [] as Row[]),
        api.rbac.departments(token).catch(() => [] as Department[]),
        api.employees.me(token).catch(() => null),
      ]);
      if (!alive) return;
      const sorted = [...cd].sort(
        (a, b) =>
          (NHOM_RANK[nhomOf(a)] ?? 9) - (NHOM_RANK[nhomOf(b)] ?? 9) ||
          String(a.ma).localeCompare(String(b.ma)),
      );
      setCongDoans(sorted);
      setDepts(dp);
      setMyDeptId(me?.employee?.department_id ?? null);
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  const cdById = useMemo(() => new Map(congDoans.map((c) => [c.id, c])), [congDoans]);
  const deptName = useCallback(
    (id: number | null): string => {
      if (id == null) return "—";
      return depts.find((d) => d.id === id)?.name ?? `Tổ #${id}`;
    },
    [depts],
  );

  const loadLenh = useCallback(
    (id: number) => {
      if (!token) return;
      setLenhLoading(true);
      setLenhErr(null);
      api.lenhSanXuat
        .get(token, id)
        .then(async (d) => {
          setDetail(d);
          setOrder(await api.orders.get(token, d.order_id).catch(() => null));
          // Reset ô nhập; preselect công đoạn theo TỔ của người đăng nhập, else công đoạn đầu.
          setSoDat("");
          setSoHong("");
          setActive("dat");
          setGiaoOpen(false);
          setGiaoTo(null);
          setQcAnh(null);
          setQcTo(null);
          const mine = congDoans.find((c) => numOrNull(c.department_id) === myDeptId && myDeptId != null);
          setSelCd(mine?.id ?? congDoans[0]?.id ?? null);
        })
        .catch((e) => setLenhErr(e instanceof ApiError ? e.message : "Không mở được lệnh."))
        .finally(() => setLenhLoading(false));
    },
    [token, congDoans, myDeptId],
  );

  function openCode() {
    const id = toInt(code);
    if (id <= 0) return;
    loadLenh(id);
  }
  function reload() {
    if (detail) loadLenh(detail.id);
  }
  function backToScan() {
    setDetail(null);
    setOrder(null);
    setLenhErr(null);
    setCode("");
  }

  // --- Ghi sản lượng ---
  async function ghiSanLuong() {
    if (!token || !detail || recording) return;
    setRecording(true);
    const cd = selCd != null ? cdById.get(selCd) : undefined;
    try {
      await api.lenhSanXuat.ghiSanLuong(token, detail.id, {
        cong_doan_id: selCd,
        to_id: numOrNull(cd?.department_id) ?? myDeptId,
        so_dat: toInt(soDat),
        so_hong: toInt(soHong),
      });
      toasts.ok(`Đã ghi ${fmt(toInt(soDat))} đạt${toInt(soHong) > 0 ? ` · ${fmt(toInt(soHong))} hỏng` : ""}`);
      setSoDat("");
      setSoHong("");
      setActive("dat");
      setFlash(true);
      window.setTimeout(() => setFlash(false), 700);
      reload();
    } catch (e) {
      // 409 = lệnh chưa phát → hiện màu đỏ + thông báo ngắn.
      toasts.err(e instanceof ApiError ? e.message : "Chưa ghi được số.");
    } finally {
      setRecording(false);
    }
  }

  // --- Giao ---
  function openGiao() {
    const datCd = (detail?.san_luong ?? [])
      .filter((r) => r.cong_doan_id === selCd)
      .reduce((s, r) => s + (r.so_dat || 0), 0);
    setGiaoSo(datCd > 0 ? String(datCd) : "");
    setGiaoTo(null);
    setGiaoOpen((v) => !v);
  }
  async function doGiao() {
    if (!token || !detail || giaoing || giaoTo == null) return;
    setGiaoing(true);
    const cd = selCd != null ? cdById.get(selCd) : undefined;
    try {
      await api.lenhSanXuat.banGiao(token, detail.id, {
        cong_doan_tu_id: selCd,
        cong_doan_toi_id: null,
        so_giao: toInt(giaoSo),
        to_giao_id: numOrNull(cd?.department_id) ?? myDeptId,
        to_nhan_id: giaoTo,
      });
      toasts.ok(`Đã giao ${fmt(toInt(giaoSo))} cho ${deptName(giaoTo)}`);
      setGiaoOpen(false);
      reload();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Chưa giao được.");
    } finally {
      setGiaoing(false);
    }
  }

  // --- Nhận (1 chạm) ---
  async function doNhan(bg: BanGiaoRow) {
    if (!token || busyId) return;
    setBusyId(`nhan-${bg.id}`);
    try {
      await api.lenhSanXuat.xacNhanNhan(token, bg.id);
      toasts.ok(`Đã nhận ${fmt(bg.so_giao)} từ ${deptName(bg.to_giao_id)}`);
      reload();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Chưa nhận được.");
    } finally {
      setBusyId(null);
    }
  }

  // --- QC: chụp ảnh (thu nhỏ về data URL) ---
  async function onPickPhoto(file: File) {
    try {
      const url = await downscale(file, 640, 0.6);
      setQcAnh(url);
    } catch {
      toasts.err("Không đọc được ảnh.");
    }
  }
  async function doGuiLoi() {
    if (!token || !detail || qcSending || qcTo == null) return;
    setQcSending(true);
    try {
      await api.lenhSanXuat.ghiLoiQc(token, detail.id, {
        cong_doan_id: selCd,
        to_bi_quy_id: qcTo,
        anh_url: qcAnh,
        mo_ta: null,
      });
      toasts.ok(`Đã gửi lỗi · quy ${deptName(qcTo)} (chờ tổ trưởng xác nhận)`);
      setQcAnh(null);
      setQcTo(null);
      reload();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Chưa gửi được lỗi.");
    } finally {
      setQcSending(false);
    }
  }
  async function doXacNhanQc(qc: QcDefectRow) {
    if (!token || busyId) return;
    setBusyId(`qc-${qc.id}`);
    try {
      await api.lenhSanXuat.toTruongXacNhanQc(token, qc.id);
      toasts.ok("Đã xác nhận lỗi");
      reload();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Chưa xác nhận được.");
    } finally {
      setBusyId(null);
    }
  }

  // ============================ RENDER ============================
  if (!detail) {
    return (
      <main className="nlx">
        <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
        <div className="nlx-card nlx-scan">
          <div className="nlx-scan__frame" aria-hidden="true">
            <span className="c1" />
            <span className="c2" />
            <QrIcon />
          </div>
          <div className="nlx-scan__hint">Quét QR hoặc gõ mã lệnh</div>
          <div className="nlx-code">
            <span className="nlx-code__pre">LSX-</span>
            <span className={`nlx-code__val${code ? "" : " is-empty"}`}>
              {code ? String(code).padStart(4, "0") : "0000"}
            </span>
          </div>
          <NumPad onKey={(k) => setCode((c) => applyKey(c, k, MAX_CODE))} />
          <button
            type="button"
            className="nlx-bigbtn nlx-bigbtn--go"
            disabled={toInt(code) <= 0 || lenhLoading}
            onClick={openCode}
          >
            {lenhLoading ? "Đang mở…" : "MỞ LỆNH"} <ArrowRightIcon />
          </button>
          {lenhErr ? (
            <div className="nlx-gate nlx-gate--danger" style={{ width: "100%" }}>
              <span className="nlx-gate__ic"><AlertIcon /></span>
              <div>
                <div className="nlx-gate__t">Không thấy lệnh</div>
                <div className="nlx-gate__s">{lenhErr}</div>
              </div>
            </div>
          ) : null}
        </div>
      </main>
    );
  }

  const st = LENH_STATE[detail.trang_thai] ?? { variant: "wait" as StateVariant, label: detail.trang_thai };
  const recordable = detail.trang_thai === "dang_chay" || detail.trang_thai === "xong";
  const anPham =
    order?.lines.find((l) => l.phieu_thanh_phan_id === detail.phieu_thanh_phan_id)?.description?.trim() ||
    (detail.phieu_thanh_phan_id ? `Ấn phẩm #${detail.phieu_thanh_phan_id}` : "Lệnh sản xuất");
  const muc = detail.muc_tieu_sl ?? 0;
  const dat = detail.tong_dat ?? 0;
  const pct = muc > 0 ? Math.min(100, Math.round((dat / muc) * 100)) : null;
  const tongHong = detail.san_luong.reduce((s, r) => s + (r.so_hong || 0), 0);
  const choNhan = detail.ban_giao.filter((b) => !b.nhan_at);
  const choXacNhanQc = detail.qc.filter((q) => q.trang_thai === "cho");

  return (
    <main className="nlx">
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />

      {/* Topbar: đổi lệnh + mã */}
      <div className="nlx-topbar">
        <button type="button" className="nlx-back" onClick={backToScan}>
          <QrIcon small /> Đổi lệnh
        </button>
        <span className="nlx-topbar__code">{maLenh(detail.id)}</span>
      </div>

      {/* Header lệnh + tiến độ */}
      <div className="nlx-card">
        <div className="nlx-hd">
          <span className={`nlx-hd__disc nlx-hd__disc--${st.variant}`} aria-hidden="true">
            <StateIcon variant={st.variant} />
          </span>
          <div className="nlx-hd__body">
            <span className="nlx-hd__name">{anPham}</span>
            {order?.customer_name ? <span className="nlx-hd__cust">{order.customer_name}</span> : null}
            <span className={`nlx-hd__state nlx-hd__state--${st.variant}`}>
              <StateIcon variant={st.variant} small /> {st.label}
            </span>
          </div>
        </div>
        <div className="nlx-prog">
          <div className="nlx-prog__row">
            <span className="nlx-prog__big">
              {fmt(dat)}
              <span className="u">/ {muc > 0 ? fmt(muc) : "—"}</span>
            </span>
            {pct != null ? <span className="nlx-prog__pct">{pct}%</span> : null}
          </div>
          {pct != null ? (
            <div className="nlx-prog__bar">
              <div className="nlx-prog__fill" style={{ width: `${pct}%` }} />
            </div>
          ) : null}
          {tongHong > 0 ? <div className="nlx-prog__hong">Hỏng: {fmt(tongHong)}</div> : null}
        </div>
      </div>

      {/* Cổng chặn: chưa phát / đã hủy */}
      {!recordable ? (
        <div className={`nlx-gate${detail.trang_thai === "huy" ? " nlx-gate--danger" : ""}`}>
          <span className="nlx-gate__ic">{detail.trang_thai === "huy" ? <AlertIcon /> : <LockIcon />}</span>
          <div>
            <div className="nlx-gate__t">{detail.trang_thai === "huy" ? "ĐÃ HỦY" : "CHƯA PHÁT"}</div>
            <div className="nlx-gate__s">
              {detail.trang_thai === "huy" ? "Lệnh đã hủy — không ghi số." : "Lệnh chưa xuống xưởng — chưa ghi được số."}
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Ghi sản lượng */}
          <section className={`nlx-sec${flash ? " nlx-flash" : ""}`}>
            <div className="nlx-sec__hd">
              <GaugeIcon /> Ghi sản lượng
            </div>
            <div className="nlx-cdrow" role="group" aria-label="Chọn công đoạn">
              {congDoans.map((c) => {
                const on = c.id === selCd;
                const nh = nhomOf(c);
                return (
                  <button
                    key={c.id}
                    type="button"
                    className={`nlx-cd${on ? " nlx-cd--on" : ""}`}
                    aria-pressed={on}
                    onClick={() => setSelCd(c.id)}
                  >
                    <span className={`nlx-cd__ic nlx-cd__ic--${nh}`}>
                      <NhomIcon nhom={nh} />
                    </span>
                    <span className="nlx-cd__t">{cdName(c)}</span>
                  </button>
                );
              })}
              {congDoans.length === 0 ? <span className="nlx-hint">Chưa có công đoạn.</span> : null}
            </div>

            <div className="nlx-counts">
              <button
                type="button"
                className={`nlx-count nlx-count--dat${active === "dat" ? " nlx-count--on" : ""}`}
                onClick={() => setActive("dat")}
              >
                <span className="nlx-count__k"><span className="sw" /> ĐẠT</span>
                <div className="nlx-count__v">{fmt(toInt(soDat))}</div>
              </button>
              <button
                type="button"
                className={`nlx-count nlx-count--hong${active === "hong" ? " nlx-count--on" : ""}`}
                onClick={() => setActive("hong")}
              >
                <span className="nlx-count__k"><span className="sw" /> HỎNG</span>
                <div className="nlx-count__v">{fmt(toInt(soHong))}</div>
              </button>
            </div>

            <NumPad
              onKey={(k) =>
                active === "dat"
                  ? setSoDat((s) => applyKey(s, k, MAX_CNT))
                  : setSoHong((s) => applyKey(s, k, MAX_CNT))
              }
            />

            <button
              type="button"
              className="nlx-bigbtn nlx-bigbtn--ok"
              disabled={recording || (toInt(soDat) === 0 && toInt(soHong) === 0) || selCd == null}
              onClick={ghiSanLuong}
            >
              <CheckIcon /> {recording ? "Đang ghi…" : "GHI SỐ"}
            </button>
          </section>

          {/* Giao */}
          <section className="nlx-sec">
            <button
              type="button"
              className="nlx-bigbtn nlx-bigbtn--go"
              onClick={openGiao}
              aria-expanded={giaoOpen}
            >
              <HandoffIcon /> GIAO SANG TỔ KẾ
            </button>
            {giaoOpen ? (
              <div className="nlx-giao__panel">
                <div className="nlx-fieldrow">
                  <span className="nlx-fieldrow__k">Số giao</span>
                  <span className="nlx-fieldrow__v">{fmt(toInt(giaoSo))}</span>
                </div>
                <NumPad onKey={(k) => setGiaoSo((s) => applyKey(s, k, MAX_CNT))} />
                <div className="nlx-sec__hd" style={{ fontSize: 14 }}>
                  <UsersIcon /> Giao cho tổ
                </div>
                <ToTiles depts={depts} value={giaoTo} onPick={setGiaoTo} exclude={myDeptId} />
                <button
                  type="button"
                  className="nlx-bigbtn nlx-bigbtn--go"
                  disabled={giaoing || giaoTo == null || toInt(giaoSo) === 0}
                  onClick={doGiao}
                >
                  <HandoffIcon /> {giaoing ? "Đang giao…" : "GIAO"}
                </button>
              </div>
            ) : null}
          </section>
        </>
      )}

      {/* Chờ nhận (1 chạm) */}
      {choNhan.length > 0 ? (
        <section className="nlx-sec">
          <div className="nlx-sec__hd">
            <InboxIcon /> Chờ nhận <span className="n">{choNhan.length}</span>
          </div>
          <div className="nlx-inbox">
            {choNhan.map((b) => (
              <div key={b.id} className="nlx-inbox__row">
                <span className="nlx-inbox__flow">
                  {deptName(b.to_giao_id)} <ArrowRightIcon /> {deptName(b.to_nhan_id)}
                </span>
                <span className="nlx-inbox__num">{fmt(b.so_giao)}</span>
                <button
                  type="button"
                  className="nlx-bigbtn nlx-bigbtn--ok nlx-inbox__btn"
                  disabled={busyId === `nhan-${b.id}`}
                  onClick={() => doNhan(b)}
                >
                  <CheckIcon /> NHẬN
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* QC lỗi — chỉ hiện khi ghi được (báo lỗi) hoặc có lỗi chờ xác nhận */}
      {recordable || choXacNhanQc.length > 0 ? (
      <section className="nlx-sec">
        <div className="nlx-sec__hd">
          <ShieldIcon /> Báo lỗi (QC)
        </div>
        {recordable ? (
          <>
            <div className="nlx-qc__cam">
              {qcAnh ? (
                <div className="nlx-qc__thumb">
                  <img src={assetUrl(qcAnh) ?? qcAnh} alt="Ảnh lỗi" />
                  <button type="button" className="nlx-qc__thumbx" aria-label="Bỏ ảnh" onClick={() => setQcAnh(null)}>
                    <XIcon />
                  </button>
                </div>
              ) : null}
              <button type="button" className="nlx-qc__shot" onClick={() => fileRef.current?.click()}>
                <CameraIcon /> {qcAnh ? "Chụp lại" : "Chụp ảnh lỗi"}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void onPickPhoto(f);
                  e.target.value = "";
                }}
              />
            </div>
            <div className="nlx-sec__hd" style={{ fontSize: 14 }}>
              <UsersIcon /> Tổ bị quy
            </div>
            <ToTiles depts={depts} value={qcTo} onPick={setQcTo} />
            <button
              type="button"
              className="nlx-bigbtn nlx-bigbtn--danger"
              disabled={qcSending || qcTo == null}
              onClick={doGuiLoi}
            >
              <AlertIcon /> {qcSending ? "Đang gửi…" : "GỬI LỖI"}
            </button>
          </>
        ) : null}

        {choXacNhanQc.length > 0 ? (
          <div className="nlx-qc__pending">
            {choXacNhanQc.map((q) => (
              <div key={q.id} className="nlx-inbox__row">
                {q.anh_url ? (
                  <span className="nlx-qc__thumb" style={{ width: 56, height: 56 }}>
                    <img src={assetUrl(q.anh_url) ?? q.anh_url} alt="Ảnh lỗi" />
                  </span>
                ) : (
                  <span className="nlx-gate__ic" style={{ width: 44, height: 44, background: "var(--signal)" }}>
                    <AlertIcon />
                  </span>
                )}
                <span className="nlx-inbox__flow">Quy {deptName(q.to_bi_quy_id)}</span>
                <button
                  type="button"
                  className="nlx-bigbtn nlx-bigbtn--ok nlx-inbox__btn"
                  disabled={busyId === `qc-${q.id}`}
                  onClick={() => doXacNhanQc(q)}
                >
                  <CheckIcon /> XÁC NHẬN
                </button>
              </div>
            ))}
          </div>
        ) : null}

        {recordable ? (
          <p className="nlx-hint">
            <InfoIcon /> Máy chỉ ghi nhận. Lỗi cần tổ trưởng tổ bị quy xác nhận mới thành lỗi chính thức.
          </p>
        ) : null}
      </section>
      ) : null}
    </main>
  );
}

// ============================ Sub-components ============================
function NumPad({ onKey }: { onKey: (k: string) => void }) {
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"];
  return (
    <div className="nlx-pad" role="group" aria-label="Bàn phím số">
      {keys.map((k) => {
        if (k === "clear")
          return (
            <button key={k} type="button" className="nlx-key nlx-key--util" onClick={() => onKey("clear")} aria-label="Xóa hết">
              C
            </button>
          );
        if (k === "back")
          return (
            <button key={k} type="button" className="nlx-key nlx-key--util" onClick={() => onKey("back")} aria-label="Xóa một số">
              <BackspaceIcon />
            </button>
          );
        return (
          <button key={k} type="button" className="nlx-key" onClick={() => onKey(k)} aria-label={`Số ${k}`}>
            {k}
          </button>
        );
      })}
    </div>
  );
}

/** Tiles chọn TỔ (giao / bị quy). Hàng cuộn ngang, icon người + màu; chọn = viền rust. */
function ToTiles({
  depts,
  value,
  onPick,
  exclude,
}: {
  depts: Department[];
  value: number | null;
  onPick: (id: number) => void;
  exclude?: number | null;
}) {
  const list = depts.filter((d) => d.id !== exclude);
  if (list.length === 0) return <span className="nlx-hint">Chưa có tổ để chọn.</span>;
  return (
    <div className="nlx-cdrow" role="group" aria-label="Chọn tổ">
      {list.map((d) => {
        const on = d.id === value;
        return (
          <button
            key={d.id}
            type="button"
            className={`nlx-cd${on ? " nlx-cd--on" : ""}`}
            aria-pressed={on}
            onClick={() => onPick(d.id)}
          >
            <span className="nlx-cd__ic nlx-cd__ic--prepress">
              <UsersIcon />
            </span>
            <span className="nlx-cd__t">{d.name}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Thu nhỏ ảnh về data URL JPEG (giảm dung lượng lưu DB — không có endpoint upload riêng cho QC). */
function downscale(file: File, maxPx: number, quality: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("img"));
      img.onload = () => {
        const scale = Math.min(1, maxPx / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) return reject(new Error("ctx"));
        ctx.drawImage(img, 0, 0, w, h);
        try {
          resolve(canvas.toDataURL("image/jpeg", quality));
        } catch {
          reject(new Error("encode"));
        }
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

// ============================ Icons (nét đậm, dễ nhìn) ============================
function QrIcon({ small }: { small?: boolean }) {
  const s = small ? 16 : 56;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="nlx-scan__qr" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <path d="M14 14h3v3M20 14v.01M14 20h.01M17 20h.01M20 17v4" />
    </svg>
  );
}
const ArrowRightIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
const BackspaceIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 5H8L3 12l5 7h13a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1Z" />
    <path d="m17 9-6 6M11 9l6 6" />
  </svg>
);
const CheckIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const XIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
function StateIcon({ variant, small }: { variant: StateVariant; small?: boolean }) {
  const s = small ? 15 : 34;
  const common = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (variant === "run") return <svg {...common}><path d="m8 5 11 7-11 7V5Z" /></svg>;
  if (variant === "done") return <svg {...common}><path d="M20 6 9 17l-5-5" /></svg>;
  if (variant === "danger") return <svg {...common}><path d="M6 6l12 12M18 6 6 18" /></svg>;
  return <svg {...common}><path d="M8 5v14M16 5v14" /></svg>; // wait = pause
}
function NhomIcon({ nhom }: { nhom: string }) {
  const common = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (nhom === "print")
    return (
      <svg {...common}>
        <path d="M6.5 9V3.5h11V9" />
        <rect x="4" y="9" width="16" height="8" rx="2" />
        <path d="M7 14.5h10v6H7z" />
      </svg>
    );
  if (nhom === "prepress")
    return (
      <svg {...common}>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
        <path d="M14 3v5h5M9 13l2 2 4-4" />
      </svg>
    );
  // finishing = kéo (cắt/bế/gia công)
  return (
    <svg {...common}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12" />
    </svg>
  );
}
const GaugeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 14 15 9" />
    <path d="M3.5 18a9 9 0 1 1 17 0" />
    <circle cx="12" cy="14" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);
const HandoffIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 17h11M15 17l-3-3M15 17l-3 3" />
    <path d="M20 7H9M9 7l3-3M9 7l3 3" />
  </svg>
);
const InboxIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.5 6.5 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-5.5A2 2 0 0 0 16.8 5.6H7.2A2 2 0 0 0 5.5 6.5Z" />
  </svg>
);
const ShieldIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
    <path d="M12 8.5v4M12 15.5h.01" />
  </svg>
);
const CameraIcon = () => (
  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 8.5h3l1.5-2h7L18 8.5h2a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z" />
    <circle cx="12" cy="13.5" r="3.2" />
  </svg>
);
const UsersIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.2a3 3 0 0 1 0 5.6M17.5 20a5.5 5.5 0 0 0-3-4.9" />
  </svg>
);
const LockIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4.5" y="11" width="15" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </svg>
);
const AlertIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.3 3.9 2.4 18a1.9 1.9 0 0 0 1.7 2.9h15.8a1.9 1.9 0 0 0 1.7-2.9L13.7 3.9a1.9 1.9 0 0 0-3.4 0Z" />
    <path d="M12 9v4M12 16.5h.01" />
  </svg>
);
const InfoIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
);
