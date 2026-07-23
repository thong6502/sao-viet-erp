// Drawer "Xem trước lệnh dự kiến" — máy BUNG SẴN mỗi dòng đơn thành 1 lệnh, người kế hoạch tick
// và xác nhận. Chưa bấm xác nhận thì CHƯA có gì ghi vào hệ thống.
//
// Nguyên tắc: máy không tự tạo, không tự bỏ dòng nào. Dòng còn thiếu dữ liệu VẪN tick được — lệnh
// sinh ra ở trạng thái "Chờ bổ sung", đúng nghiệp vụ (thiếu khuôn/giấy vẫn phải có lệnh để làm tiếp).
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type LsxPreviewLine, type LsxPreviewOut } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BangLoi, ChipGap, ChuoiCongDoan, CanhBaoMem, ThieuStack, ngay, num } from "./keHoachSxShared";

export function LsxPreviewDrawer({
  orderId,
  canCreate,
  onClose,
  onCreated,
  onOpenLsx,
}: {
  orderId: number;
  canCreate: boolean;
  onClose: () => void;
  /** Tạo xong → controller nhảy sang tab Lệnh SX đã lọc theo đơn này. */
  onCreated: (orderId: number, maList: string[]) => void;
  onOpenLsx: (lsxId: number) => void;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<LsxPreviewOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const allRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    api.lsx
      .preview(token, orderId)
      .then((d) => {
        setData(d);
        // Tick sẵn mọi dòng CHƯA có lệnh — luồng chuẩn là tạo hết, ít click.
        setPicked(new Set(d.lines.filter((l) => l.lsx_id == null).map((l) => l.order_line_id)));
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [token, orderId]);

  useEffect(() => load(), [load]);
  useEffect(() => titleRef.current?.focus(), [data]);

  // Esc đóng drawer (bám hành vi các drawer khác trong app).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const chuaCoLenh = data?.lines.filter((l) => l.lsx_id == null) ?? [];
  const tatCaDaCoLenh = (data?.lines.length ?? 0) > 0 && chuaCoLenh.length === 0;
  const soThieu = chuaCoLenh.filter((l) => picked.has(l.order_line_id) && l.thieu.length > 0).length;

  // Checkbox "chọn tất cả" ở header — trạng thái nửa vời khi tick một phần.
  useEffect(() => {
    if (allRef.current) {
      allRef.current.indeterminate = picked.size > 0 && picked.size < chuaCoLenh.length;
    }
  }, [picked, chuaCoLenh.length]);

  function toggle(id: number) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setPicked((prev) =>
      prev.size === chuaCoLenh.length ? new Set() : new Set(chuaCoLenh.map((l) => l.order_line_id)),
    );
  }

  async function xacNhan() {
    if (!token || !data || picked.size === 0) return;
    setSaving(true);
    setErr(null);
    try {
      const r = await api.lsx.tao(token, data.order_id, [...picked]);
      onCreated(data.order_id, r.items.map((i) => i.ma));
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="khsx-scrim" onClick={onClose} role="presentation">
      <aside
        className="khsx-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="khsx-drawer-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="khsx-drawer__head">
          <div className="khsx-drawer__headmain">
            <p className="khsx-drawer__kicker">Lệnh dự kiến · chưa ghi vào hệ thống</p>
            <h2 className="khsx-drawer__title" id="khsx-drawer-title" tabIndex={-1} ref={titleRef}>
              {data ? `${data.order_no} · ${data.customer_name ?? "—"}` : "Đang tải…"}
            </h2>
            {data && (
              <p className="khsx-drawer__meta">
                Giao {ngay(data.delivery_committed_date)}
                {data.sale_name ? ` · Sale ${data.sale_name}` : ""}
                {data.is_rush && <ChipGap />}
              </p>
            )}
          </div>
          <button type="button" className="khsx-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        <div className="khsx-drawer__body">
          <p className="khsx-callout khsx-callout--steel">
            <Icon name="help" size={14} />
            <span>
              Số dưới đây máy <strong>bung sẵn</strong> từ bài tính giá — là <strong>đề xuất</strong>,
              sửa được sau khi tạo lệnh. Máy không tự tạo và không tự bỏ dòng nào.
            </span>
          </p>

          {data?.production_note && (
            <p className="khsx-callout khsx-callout--amber">
              <Icon name="bell" size={14} />
              <span>Lưu ý sản xuất từ Sale: {data.production_note}</span>
            </p>
          )}

          {data && data.warnings.length > 0 && (
            <div className="banner banner--warn">
              <ul className="khsx-warnlist">
                {data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {err && <BangLoi text={err} onRetry={load} />}

          {tatCaDaCoLenh ? (
            <div className="khsx-empty khsx-empty--inline">
              <Icon name="check" size={36} />
              <p className="khsx-empty__title">Tất cả dòng của đơn này đã lên lệnh.</p>
              <Button variant="secondary" onClick={() => onCreated(orderId, [])}>
                Xem lệnh của đơn →
              </Button>
            </div>
          ) : (
            <div className="khsx__tablewrap">
              <table className="khsx-prev">
                <caption className="sr-only">Danh sách lệnh sản xuất dự kiến của đơn</caption>
                <thead>
                  <tr>
                    <th scope="col" className="khsx-prev__tickcol">
                      <label className="khsx-prev__tick">
                        <input
                          ref={allRef}
                          type="checkbox"
                          checked={picked.size > 0 && picked.size === chuaCoLenh.length}
                          onChange={toggleAll}
                          disabled={loading || chuaCoLenh.length === 0}
                        />
                        <span className="sr-only">Chọn tất cả dòng chưa có lệnh</span>
                      </label>
                    </th>
                    <th scope="col">Sản phẩm</th>
                    <th scope="col" className="khsx-th--num">SL đơn</th>
                    <th scope="col" className="khsx-th--num">Bù hao</th>
                    <th scope="col" className="khsx-th--num">Tờ in</th>
                    <th scope="col" className="khsx-th--num">Tờ nguyên</th>
                    <th scope="col" className="khsx-th--num">Con/tờ</th>
                    <th scope="col" className="khsx-th--num">Kẽm · lượt</th>
                    <th scope="col">Công đoạn</th>
                    <th scope="col">Thiếu</th>
                  </tr>
                </thead>
                {loading ? (
                  <tbody className="khsx-skel">
                    {Array.from({ length: 3 }).map((_, r) => (
                      <tr key={r}>
                        {Array.from({ length: 10 }).map((__, c) => (
                          <td key={c}>
                            <span className="khsx-skel__bar" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                ) : (
                  <tbody>
                    {(data?.lines ?? []).map((l) => (
                      <PreviewRow
                        key={l.order_line_id}
                        line={l}
                        checked={picked.has(l.order_line_id)}
                        onToggle={() => toggle(l.order_line_id)}
                        onOpenLsx={onOpenLsx}
                      />
                    ))}
                  </tbody>
                )}
              </table>
            </div>
          )}
        </div>

        {!tatCaDaCoLenh && (
          <footer className="khsx-drawer__foot">
            <p className="khsx-drawer__tally" aria-live="polite">
              Đã chọn <strong>{picked.size}</strong>/{chuaCoLenh.length} dòng
              {soThieu > 0 && ` · ${soThieu} dòng còn thiếu → lệnh vào Chờ bổ sung`}
            </p>
            <div className="khsx-drawer__footbtns">
              <Button variant="ghost" onClick={onClose}>
                Đóng
              </Button>
              <Button
                variant="accent"
                onClick={xacNhan}
                loading={saving}
                disabled={!canCreate || picked.size === 0}
                title={canCreate ? undefined : "Bạn không có quyền tạo lệnh sản xuất"}
              >
                Xác nhận tạo {picked.size} lệnh sản xuất
              </Button>
            </div>
          </footer>
        )}
      </aside>
    </div>
  );
}

function PreviewRow({
  line,
  checked,
  onToggle,
  onOpenLsx,
}: {
  line: LsxPreviewLine;
  checked: boolean;
  onToggle: () => void;
  onOpenLsx: (id: number) => void;
}) {
  const daCo = line.lsx_id != null;
  return (
    <tr className={daCo ? "khsx-prev__row khsx-prev__row--done" : "khsx-prev__row"}>
      <td>
        <label className="khsx-prev__tick">
          <input type="checkbox" checked={checked} onChange={onToggle} disabled={daCo} />
          <span className="sr-only">Chọn {line.ten}</span>
        </label>
      </td>
      <td>
        <div className="khsx-prev__name">{line.ten}</div>
        <div className="khsx-prev__nameSub">
          {daCo ? (
            <button type="button" className="khsx-xlink" onClick={() => onOpenLsx(line.lsx_id!)}>
              {line.lsx_ma} — mở lệnh →
            </button>
          ) : line.ptg_ma ? (
            <span className="khsx-chip khsx-chip--ptg">{line.ptg_ma}</span>
          ) : null}
        </div>
      </td>
      <td className="khsx-num">
        {num(line.so_luong_dat)} <span className="khsx-unit">{line.don_vi_tinh}</span>
        {line.sl_ptg != null && (
          <div>
            <CanhBaoMem
              title={`Bài tính giá làm với ${num(line.sl_ptg)}; đơn đặt ${num(line.so_luong_dat)}. Số dùng thật là của đơn.`}
            >
              tính giá {num(line.sl_ptg)}
            </CanhBaoMem>
          </div>
        )}
      </td>
      <td className="khsx-num">{num(line.bu_hao_to)}</td>
      <td className="khsx-num">{num(line.so_to_ke_hoach)}</td>
      <td className="khsx-num">{num(line.so_to_nguyen)}</td>
      <td className="khsx-num">{num(line.so_con)}</td>
      <td className="khsx-num">
        {num(line.so_kem)} · {num(line.so_luot)}
      </td>
      <td>
        <ChuoiCongDoan steps={line.routing} />
      </td>
      <td>
        <ThieuStack codes={line.thieu} />
      </td>
    </tr>
  );
}
