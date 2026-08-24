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
import { donViChuoi, nhanDonVi } from "./lsxBuoc";

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
            <p className="khsx-drawer__kicker">
              <span className="khsx-badge-kicker">Lệnh dự kiến · chưa ghi DB</span>
            </p>
            <h2 className="khsx-drawer__title" id="khsx-drawer-title" tabIndex={-1} ref={titleRef}>
              {data ? `${data.order_no} · ${data.customer_name ?? "—"}` : "Đang tải…"}
            </h2>
            {data && (
              <div className="khsx-drawer__meta">
                <span className="khsx-meta-item">
                  <Icon name="calendar" size={13} /> Giao {ngay(data.delivery_committed_date)}
                </span>
                {data.sale_name && (
                  <span className="khsx-meta-item">
                    <Icon name="users" size={13} /> Sale {data.sale_name}
                  </span>
                )}
                {data.is_rush && <ChipGap />}
              </div>
            )}
          </div>
          <button type="button" className="khsx-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="khsx-drawer__body">
          <p className="khsx-callout khsx-callout--steel khsx-callout--compact">
            <Icon name="help" size={14} />
            <span>
              Số dưới đây máy <strong>bung sẵn</strong> từ bài tính giá — là đề xuất, sửa được sau khi tạo lệnh.
            </span>
          </p>

          {data?.production_note && (
            <p className="khsx-callout khsx-callout--amber khsx-callout--compact">
              <Icon name="bell" size={14} />
              <span>Lưu ý từ Sale: {data.production_note}</span>
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
                    <th scope="col" className="khsx-th--num">Vào máy</th>
                    <th scope="col" className="khsx-th--num">Giấy nguyên</th>
                    <th scope="col" className="khsx-th--num">Bình bài</th>
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
                    {gomDongLenh(data?.lines ?? []).flatMap((node) => {
                      const dong = (l: LsxPreviewLine, con: boolean, cuoi = false) => (
                        <PreviewRow
                          key={l.order_line_id}
                          line={l}
                          con={con}
                          conCuoi={cuoi}
                          checked={picked.has(l.order_line_id)}
                          onToggle={() => toggle(l.order_line_id)}
                          onOpenLsx={onOpenLsx}
                        />
                      );
                      if (node.kind === "don") return [dong(node.line, false)];
                      return [
                        <tr key={`nh-${node.key}`} className="khsx-prev__nhom">
                          <td />
                          <td colSpan={9}>
                            <span className="khsx-prev__nhomTen">{node.ten}</span>
                            <span className="khsx-prev__nhomSub">
                              {node.members.length} phần · {node.members.length} lệnh riêng
                            </span>
                          </td>
                        </tr>,
                        ...node.members.map((m, i) => dong(m, true, i === node.members.length - 1)),
                      ];
                    })}
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

type NodeLenh =
  | { kind: "don"; key: string; line: LsxPreviewLine }
  | { kind: "nhom"; key: string; ten: string; members: LsxPreviewLine[] };

function gomDongLenh(lines: LsxPreviewLine[]): NodeLenh[] {
  const out: NodeLenh[] = [];
  const viTri = new Map<string, number>();
  for (const l of lines) {
    const nh = (l.nhom ?? "").trim();
    if (!nh) {
      out.push({ kind: "don", key: `d${l.order_line_id}`, line: l });
      continue;
    }
    const k = nh.toLowerCase();
    const at = viTri.get(k);
    if (at === undefined) {
      viTri.set(k, out.length);
      out.push({ kind: "nhom", key: k, ten: nh, members: [l] });
    } else {
      (out[at] as { members: LsxPreviewLine[] }).members.push(l);
    }
  }
  return out;
}

function PreviewRow({
  line,
  con,
  conCuoi,
  checked,
  onToggle,
  onOpenLsx,
}: {
  line: LsxPreviewLine;
  con?: boolean;
  conCuoi?: boolean;
  checked: boolean;
  onToggle: () => void;
  onOpenLsx: (id: number) => void;
}) {
  const daCo = line.lsx_id != null;
  const dvDong = donViChuoi(line, line.don_vi_tinh);
  const { to: dvTo, tp: dvTp } = dvDong;
  return (
    <tr
      className={
        `khsx-prev__row${daCo ? " khsx-prev__row--done" : ""}` +
        `${con ? " khsx-prev__row--con" : ""}${conCuoi ? " khsx-prev__row--conCuoi" : ""}`
      }
    >
      <td>
        <label className="khsx-prev__tick">
          <input type="checkbox" checked={checked} onChange={onToggle} disabled={daCo} />
          <span className="sr-only">Chọn {line.ten}</span>
        </label>
      </td>
      <td>
        <div className="khsx-prev__name-inline">
          <span className="khsx-prev__name">{line.ten}</span>
          {daCo ? (
            <button
              type="button"
              className="khsx-action-link"
              onClick={() => onOpenLsx(line.lsx_id!)}
              title="Bấm để mở lệnh sản xuất này"
            >
              {line.lsx_ma} — mở lệnh →
            </button>
          ) : line.ptg_ma ? (
            <span className="khsx-chip khsx-chip--ptg">{line.ptg_ma}</span>
          ) : null}
        </div>
      </td>
      <td className="khsx-num khsx-num--val">
        <span className="khsx-num__main">{num(line.so_luong_dat)}</span> <span className="khsx-unit">{line.don_vi_tinh}</span>
        {line.sl_ptg != null && (
          <span className="khsx-num__ptg-warn">
            <CanhBaoMem
              title={`Bài tính giá làm với ${num(line.sl_ptg)}; đơn đặt ${num(line.so_luong_dat)}. Số dùng thật là của đơn.`}
            >
              {num(line.sl_ptg)}
            </CanhBaoMem>
          </span>
        )}
      </td>
      <td className="khsx-num khsx-num--val" title={dvTo ? `${num(line.bu_hao_to)} ${dvTo}` : undefined}>
        <span className="khsx-num__main">{num(line.bu_hao_to)}</span>
      </td>
      <td className="khsx-num khsx-num--val">
        <span className="khsx-num__main">{num(line.so_to_ke_hoach)}</span> <span className="khsx-unit">{dvTo}</span>
      </td>
      <td className="khsx-num khsx-num--val">
        <span className="khsx-num__main">{num(line.so_to_nguyen)}</span>{" "}
        <span className="khsx-unit">{nhanDonVi(line.don_vi_to_nguyen) || dvTo}</span>
      </td>
      <td
        className="khsx-num khsx-num--val"
        title={dvTp && dvTo ? `${num(line.so_con)} ${dvTp} trên 1 ${dvTo}` : undefined}
      >
        <span className="khsx-num__main">{num(line.so_con)}</span> <span className="khsx-unit">{dvTp}</span>
      </td>
      <td className="khsx-num khsx-num--val">
        {line.so_kem == null && line.so_luot == null ? (
          <span className="khsx-muted">—</span>
        ) : (
          <span className="khsx-num__pair">
            <span className="khsx-num__main">{num(line.so_kem)}</span><span className="khsx-unit">kẽm</span>
            <span className="khsx-num__sep">·</span>
            <span className="khsx-num__main">{num(line.so_luot)}</span><span className="khsx-unit">lượt</span>
          </span>
        )}
      </td>
      <td className="khsx-prev__flow-col">
        <ChuoiCongDoan steps={line.routing} />
      </td>
      <td>
        <ThieuStack codes={line.thieu} dv={dvDong} />
      </td>
    </tr>
  );
}


