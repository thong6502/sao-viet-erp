// CHI TIẾT BÀI GHÉP — Studio 1 màn hình duy nhất (xem & sửa sơ đồ DAG + Side Inspector nhập liệu).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  BAI_GHEP_CANH_BAO_LABELS,
  BAI_GHEP_THIEU_LABELS,
  type BaiGhepBuocChungBody,
  type BaiGhepDetail,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { BaiGhepSoDo, type Form } from "./BaiGhepSoDo";
import { BangLoi, TrangThaiPill, classHan, ngay, num } from "./keHoachSxShared";

const toForm = (d: BaiGhepDetail): Form => ({
  giay_id: d.giay_id,
  kho_in_dai: d.kho_in_dai,
  kho_in_rong: d.kho_in_rong,
  hao_hut_setup: d.hao_hut_setup,
  hao_hut_chay: d.hao_hut_chay,
  ghi_chu: d.ghi_chu ?? "",
});

export function BaiGhepDetailView({
  baiGhepId,
  onBack,
  onChanged,
  navigate,
}: {
  baiGhepId: number;
  onBack: () => void;
  onChanged?: () => void;
  /** Bấm một bước trên sơ đồ → sang màn Kế hoạch SX, mở đúng lệnh đó. */
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const canUpdate = useCan()("san_xuat", "update");
  const [d, setD] = useState<BaiGhepDetail | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  // Sơ đồ tự nạp riêng (đồ thị dẫn xuất, khác payload chi tiết) — bump sau mỗi lần ghi.
  const [soDoTick, setSoDoTick] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [readyErr, setReadyErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingXoa, setConfirmingXoa] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const apply = useCallback(
    (r: BaiGhepDetail) => {
      setD(r);
      setForm(toForm(r));
      setSoDoTick((n) => n + 1);
      onChanged?.();
    },
    [onChanged],
  );

  const load = useCallback(() => {
    if (!token) return;
    api.baiGhep
      .get(token, baiGhepId)
      .then((r) => {
        setD(r);
        setForm(toForm(r));
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, baiGhepId]);

  useEffect(() => load(), [load]);

  const dirty = useMemo(() => {
    if (!d || !form) return false;
    return JSON.stringify(form) !== JSON.stringify(toForm(d));
  }, [d, form]);

  async function luu() {
    if (!token || !form) return;
    setSaving(true);
    setErr(null);
    try {
      apply(await api.baiGhep.update(token, baiGhepId, { ...form }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function doiTrangThai(tt: "nhap" | "san_sang") {
    if (!token) return;
    setReadyErr(null);
    try {
      apply(await api.baiGhep.setTrangThai(token, baiGhepId, tt));
    } catch (e) {
      setReadyErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function suaUps(tvId: number, soCon: number) {
    if (!token) return;
    try {
      apply(await api.baiGhep.suaThanhVien(token, baiGhepId, tvId, soCon));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  // --- Gộp / tách / lập kế hoạch lượt chung -----------------------------------
  // Cửa ghi nằm ở đây, sơ đồ chỉ đẩy lên — cùng luật với thông số tờ. Ba hàm này đều `apply()`
  // nên bảng thành viên và sơ đồ cùng nhận số mới trong một nhịp, không lệch nhau.
  async function gop(stepKeys: string[]) {
    if (!token) return;
    try {
      apply(await api.baiGhep.gop(token, baiGhepId, stepKeys));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function tach(gangStepKey: string) {
    if (!token) return;
    try {
      apply(await api.baiGhep.tach(token, baiGhepId, gangStepKey));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function luuBuocChung(gangStepKey: string, body: BaiGhepBuocChungBody) {
    if (!token) return;
    try {
      apply(await api.baiGhep.luuBuocChung(token, baiGhepId, gangStepKey, body));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function hoiUngVien(stepKeys: string[]) {
    if (!token) return {};
    return (await api.baiGhep.ungVienGop(token, baiGhepId, stepKeys)).ung_vien;
  }

  async function boThanhVien(tvId: number) {
    if (!token) return;
    try {
      apply(await api.baiGhep.boThanhVien(token, baiGhepId, tvId));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function themThanhVien(lsxIds: number[]) {
    if (!token || !lsxIds.length) return;
    try {
      apply(await api.baiGhep.themThanhVien(token, baiGhepId, lsxIds));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function thucHienXoa() {
    if (!token || !d) return;
    setDeleting(true);
    try {
      await api.baiGhep.remove(token, baiGhepId);
      onChanged?.();
      onBack();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setConfirmingXoa(false);
    } finally {
      setDeleting(false);
    }
  }

  if (err && !d) return <BangLoi text={err} onRetry={load} />;
  if (!d || !form) return <p className="khsx-muted">Đang tải…</p>;

  const giayOptions = Array.from(
    new Map(
      d.thanh_vien
        .filter((t) => t.giay_id != null)
        .map((t) => [t.giay_id as number, t.giay_ten] as [number, string | null]),
    ).entries(),
  );

  return (
    <div className="khsx-detail">
      {err && <BangLoi text={err} onRetry={load} />}

      {/* Unified Compact Header Bar */}
      <div className="bghep-unified-header">
        {/* Row 1: Back Link + Code + Status Badges + Actions */}
        <div className="bghep-uh-row1">
          <div className="bghep-uh-titlegroup">
            <button type="button" className="khsx-back bghep-back-btn" onClick={onBack}>
              ‹ Danh sách bài ghép
            </button>
            <div className="bghep-uh-titlewrap">
              <h1 className="khsx-detail__ma bghep-ma-title">{d.ma}</h1>
              <TrangThaiPill tt={d.trang_thai} lg />

              <div
                className={`bghep-badge-ready ${
                  d.trang_thai === "san_sang"
                    ? "bghep-badge-ready--done"
                    : d.thieu.length
                    ? "bghep-badge-ready--blocked"
                    : "bghep-badge-ready--ok"
                }`}
              >
                <Icon name={d.trang_thai === "san_sang" ? "check" : d.thieu.length ? "x" : "check"} size={13} />
                <span>
                  {d.trang_thai === "san_sang"
                    ? "Sẵn sàng xếp lịch"
                    : d.thieu.length
                    ? `Còn thiếu ${d.thieu.length} mục`
                    : "Đủ điều kiện"}
                </span>
              </div>

              <div className="bghep-badge-note" title="Nhớ thêm bước xả tờ ở từng lệnh khi in ghép — hệ không tự chèn">
                <Icon name="help" size={13} />
                <span>Nhớ bước <strong>xả tờ</strong></span>
              </div>

              {d.canh_bao.length > 0 && (
                <div className="bghep-badge-luuy" title={d.canh_bao.map((code) => BAI_GHEP_CANH_BAO_LABELS[code] ?? code).join(" · ")}>
                  <Icon name="help" size={13} />
                  <span>
                    Lưu ý ({d.canh_bao.length}): {d.canh_bao.map((code) => BAI_GHEP_CANH_BAO_LABELS[code] ?? code).join(" · ")}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="bghep-uh-actions">
            <Button variant="ghost" onClick={() => setConfirmingXoa(true)} title="Xoá bài ghép">
              <Icon name="trash" size={14} /> Xoá
            </Button>

            {d.trang_thai === "san_sang" ? (
              <Button variant="ghost" onClick={() => doiTrangThai("nhap")}>
                Mở lại để sửa
              </Button>
            ) : d.thieu.length ? (
              <Button variant="accent" disabled>
                Sẵn sàng xếp lịch ({d.thieu.length} thiếu)
              </Button>
            ) : (
              <Button variant="accent" onClick={() => doiTrangThai("san_sang")}>
                Sẵn sàng xếp lịch
              </Button>
            )}

            {dirty && (
              <>
                <Button variant="ghost" onClick={() => setForm(toForm(d))}>
                  Hoàn tác
                </Button>
                <Button variant="primary" loading={saving} onClick={luu}>
                  Lưu thay đổi
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Row 2: Micro KPI Metric Strip */}
        <div className="bghep-uh-metrics">
          <div className="bghep-uh-metric-item">
            <span className="bghep-uh-m-label">Số lệnh:</span>
            <strong className="bghep-uh-m-val">{num(d.thanh_vien.length)}</strong>
          </div>
          <span className="bghep-uh-m-sep">•</span>
          <div className="bghep-uh-metric-item">
            <span className="bghep-uh-m-label">Số tờ tốt:</span>
            <strong className="bghep-uh-m-val">{num(d.so_to.so_to_tot)}</strong>
          </div>
          <span className="bghep-uh-m-sep">•</span>
          {/* Hai số, không gộp: tờ IN là sản phẩm của lượt in; giấy LĨNH KHO còn cộng hao canh
              máy. Nhãn "Tổng tờ cấp" cũ mập mờ, ai cầm số đó đi lĩnh giấy là thiếu. */}
          <div className="bghep-uh-metric-item">
            <span className="bghep-uh-m-label">Tờ in:</span>
            <strong className="bghep-uh-m-val">{num(d.so_to.so_to_tot)}</strong>
          </div>
          <span className="bghep-uh-m-sep">•</span>
          <div
            className="bghep-uh-metric-item"
            title={
              d.so_to.so_buoc_chung > 0
                ? `Gồm ${num(d.so_to.hao_setup_de_xuat)} tờ canh máy + ${num(
                    d.so_to.hao_chay_de_xuat,
                  )} tờ hao chạy của ${d.so_to.so_buoc_chung} lượt chạy chung`
                : "Chưa gộp bước nào — chưa có lượt chạy chung nào để tính hao"
            }
          >
            <span className="bghep-uh-m-label">Giấy lĩnh kho:</span>
            <strong className="bghep-uh-m-val">{num(d.so_to.to_nguyen_can)}</strong>
          </div>
          {/* T1: tỷ lệ hao/tốt — makeready cố định nuốt lô nhỏ (230 tờ hao cho 20 tờ tốt = ×11,5).
              Tô cảnh báo khi hao ≥ số tờ tốt → gợi ý gộp thêm lệnh cùng giấy để chia canh máy. */}
          {d.so_to.so_buoc_chung > 0 && (
            <>
              <span className="bghep-uh-m-sep">•</span>
              <div
                className="bghep-uh-metric-item"
                title={
                  `Hao ${num(d.so_to.hao_ap_dung)} tờ trên ${num(d.so_to.so_to_tot)} tờ tốt` +
                  (d.so_to.hao_theo_buoc.length
                    ? " — gồm " +
                      d.so_to.hao_theo_buoc.map((b) => `${b.ten} ${num(b.hao)}`).join(" + ")
                    : "") +
                  (d.so_to.ty_le_hao >= 100
                    ? ". Makeready lớn hơn sản lượng — cân nhắc gộp thêm lệnh cùng giấy."
                    : "")
                }
              >
                <span className="bghep-uh-m-label">Hao:</span>
                <strong
                  className={`bghep-uh-m-val${
                    d.so_to.ty_le_hao >= 100 ? " bghep-uh-m-val--canh" : ""
                  }`}
                >
                  {num(d.so_to.hao_ap_dung)} tờ (×{(d.so_to.ty_le_hao / 100).toFixed(1)})
                </strong>
              </div>
            </>
          )}
          <span className="bghep-uh-m-sep">•</span>
          <div className="bghep-uh-metric-item">
            <span className="bghep-uh-m-label">Tờ dùng:</span>
            {/* CHỈ hiển thị, KHÔNG phán — cả "vượt khổ" lẫn "bài thưa". `con/tờ` ở đây là số người
                bình bài bằng phần mềm khác rồi khai lại, còn khổ thành phẩm chưa trừ xén/chừa;
                lấy hai thứ đó nhân với nhau rồi kêu bài không xếp lọt (hoặc kêu thưa) là kêu oan.
                Người cân bài nhìn con số là đủ, họ có nghiệp vụ đó. */}
            <strong className="bghep-uh-m-val">
              {d.so_to.fill_pct == null ? "—" : `${d.so_to.fill_pct}%`}
            </strong>
          </div>
          <span className="bghep-uh-m-sep">•</span>
          <div className="bghep-uh-metric-item">
            <span className="bghep-uh-m-label">Hạn in gần nhất:</span>
            <strong className={`bghep-uh-m-val ${classHan(d.so_to.han_in_muon_nhat)}`}>
              {ngay(d.so_to.han_in_muon_nhat) || "—"}
            </strong>
          </div>
        </div>

        {/* Cảnh báo thiếu mục */}
        {d.trang_thai !== "san_sang" && d.thieu.length > 0 && (
          <div className="bghep-uh-missing">
            <span>Còn thiếu:</span>
            {d.thieu.map((code) => (
              <span key={code} className="bghep-uh-missing-tag">
                • {BAI_GHEP_THIEU_LABELS[code] ?? code}
              </span>
            ))}
          </div>
        )}
      </div>

      {readyErr && <BangLoi text={readyErr} onRetry={() => setReadyErr(null)} />}

      {/* Main Studio Workspace: 100% Sơ đồ & Side Inspector */}
      <div className="khsx-detail__main" style={{ width: "100%" }}>
        <BaiGhepSoDo
          baiGhepId={baiGhepId}
          tick={soDoTick}
          canUpdate={canUpdate}
          detail={d}
          form={form}
          setForm={setForm}
          giayOptions={giayOptions}
          onMoLenh={(lsxId) => navigate?.("ke-hoach-sx", { openLsxId: lsxId })}
          onSuaThanhVien={suaUps}
          onBoThanhVien={boThanhVien}
          onThemThanhVien={themThanhVien}
          onSuaThongSoTo={luu}
          dirtyThongSoTo={dirty}
          dangLuuThongSoTo={saving}
          onGop={gop}
          onTach={tach}
          onLuuBuocChung={luuBuocChung}
          onHoiUngVien={hoiUngVien}
        />
      </div>

      <ConfirmDialog
        open={confirmingXoa}
        title="Xác nhận xoá bài ghép"
        message={`Xoá bài ghép ${d.ma}? Các lệnh sẽ được trả về hàng chờ ghép.`}
        confirmLabel="Xoá bài ghép"
        cancelLabel="Hủy"
        danger
        busy={deleting}
        onConfirm={thucHienXoa}
        onCancel={() => setConfirmingXoa(false)}
      />
    </div>
  );
}
