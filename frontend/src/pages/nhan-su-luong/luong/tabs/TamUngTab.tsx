// Tab Tạm ứng (tách từ pages/LuongPage.tsx). Từ 25/09/2026 chạy cho nhà máy ~1000 người: tab trạng
// thái + lọc loại / tổ / tìm + 50 dòng một trang, chọn nhiều qua mọi trang — luật ở `tamUngLoc.ts`.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Calendar, Wallet } from "lucide-react";
import {
  api,
  type SalaryAdvance,
} from "../../../../api/client";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import type { NavigateFn } from "../../../../components/AppShell";
import { MonthPicker } from "../../../../components/MonthPicker";
import { Pager, trangHopLe } from "../../../../components/Pager";
import { useCan } from "../../../../auth/permissions";
import { curYm, errText, money, vuongIds } from "../shared/helpers";
import { LapHangLoatModal } from "../modals/LapHangLoatModal";
import { LapPhieuChiModal } from "../modals/LapPhieuChiModal";
import { PhieuChiMotLuotModal } from "../modals/PhieuChiMotLuotModal";
import { TamUngBang } from "./TamUngBang";
import { TamUngBoLoc } from "./TamUngBoLoc";
import { TamUngChonNhieu, taiFileChuyenKhoan, useTiaLuaChon } from "./TamUngChonNhieu";
import { TuNote } from "./TamUngHanhDong";
import {
  BO_LOC_TRONG,
  CO_TRANG,
  demTheoTab,
  dsTo,
  khopBoLoc,
  tachLoai,
  thuocTab,
  type BoLocTamUng,
  type TabTrangThai,
} from "./tamUngLoc";

export function TamUngTab({
  token,
  navigate,
  eventTick,
  canCreateAdvance,
  canApproveAdvance,
}: {
  token: string;
  navigate?: NavigateFn;
  eventTick?: number;
  canCreateAdvance: boolean;
  canApproveAdvance: boolean;
}) {
  const can = useCan();
  // Lập phiếu chi là việc của KẾ TOÁN, không phải của người duyệt tạm ứng (tách vai từ
  // 04/08/2026) ⇒ đi theo ô của phân hệ Phiếu chi, không theo `luong:approve`.
  const canLapPhieuChi = can("phieu_chi", "create");
  const canXemPhieuChi = can("phieu_chi", "read");
  const canXuat = can("luong", "export");
  const [ym, setYm] = useState(curYm);
  const [items, setItems] = useState<SalaryAdvance[]>([]);
  const [tab, setTab] = useState<TabTrangThai>("tat_ca");
  const [loc, setLoc] = useState<BoLocTamUng>(BO_LOC_TRONG);
  const [trang, setTrang] = useState(1);
  const [chon, setChon] = useState<Set<number>>(() => new Set());
  const [chiXemChon, setChiXemChon] = useState(false);
  const [hangLoat, setHangLoat] = useState(false);
  const [lapPcCho, setLapPcCho] = useState<SalaryAdvance | null>(null);
  // Phiếu chi vừa lập — lẻ hay MỘT LƯỢT đều là MỘT phiếu chi (25/09/2026); `soPhieu` = số phiếu tạm ứng.
  const [pcVuaLap, setPcVuaLap] = useState<{ id: number; code: string; tong: number; soPhieu: number } | null>(null);
  const [actErr, setActErr] = useState<string | null>(null);
  const [actVuong, setActVuong] = useState<number[]>([]);
  const [busyNhieu, setBusyNhieu] = useState(false);
  const [xacNhan, setXacNhan] = useState<{ duyet: boolean; advs: SalaryAdvance[] } | null>(null);
  const [pcNhieuCho, setPcNhieuCho] = useState<SalaryAdvance[] | null>(null);
  const [daDuyetNhieu, setDaDuyetNhieu] = useState<string | null>(null);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    // Máy chủ gắn sẵn mã phiếu chi lên từng dòng (`phieu_chi_code`) — không còn tự tải sổ phiếu
    // chi cả công ty để dò (chỉ 1000 phiếu gần nhất: sang tháng thứ hai là mất mã trên dòng).
    api.luong
      .advances(token, year, month)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, year, month]);
  useEffect(() => {
    load();
  }, [load, eventTick]);

  // Đổi KỲ hoặc TAB ⇒ xoá lựa chọn (mỗi tab một loại việc). Đổi loại / tổ / tìm / trang ⇒ GIỮ.
  function xoaChon() {
    setChon(new Set());
    setChiXemChon(false);
    setTrang(1);
  }
  const doiKy = (v: string) => (setYm(v), xoaChon());
  const doiTab = (t: TabTrangThai) => (setTab(t), xoaChon());
  function doiLoc(l: BoLocTamUng) {
    setLoc(l);
    setTrang(1);
  }

  const tabRows = useMemo(() => items.filter((a) => thuocTab(a, tab)), [items, tab]);
  const dangLoc = useMemo(() => tabRows.filter((a) => khopBoLoc(a, loc)), [tabRows, loc]);
  const hien = chiXemChon ? tabRows.filter((a) => chon.has(a.id)) : dangLoc;
  const trangNay = hien.slice((trang - 1) * CO_TRANG, trang * CO_TRANG);
  const dem = useMemo(() => demTheoTab(items, loc), [items, loc]);
  const to = useMemo(() => dsTo(items), [items]);
  const coCotChon =
    (tab === "cho_duyet" && canApproveAdvance) ||
    (tab === "cho_chi" && (canLapPhieuChi || canXuat));
  useTiaLuaChon(items, setChon, (a) => thuocTab(a, tab), tab);
  useEffect(() => {
    const ve = trangHopLe(trang, hien.length, CO_TRANG);
    if (ve !== null) setTrang(ve);
  }, [trang, hien.length]);

  // File chuyển khoản theo mẫu lô lương BIZ MBBank — xuất ĐÚNG những phiếu đã duyệt / đã chi đang
  // hiện theo tab + bộ lọc (hoặc phiếu đang tick).
  function xuatExcel(advs: SalaryAdvance[]) {
    setActErr(null);
    setActVuong([]);
    const ids = advs.filter((a) => a.status === "approved" || a.status === "paid").map((a) => a.id);
    if (ids.length === 0) {
      setActErr("Không có phiếu đã duyệt / đã chi nào trong bộ lọc đang xem để xuất.");
      return;
    }
    taiFileChuyenKhoan(token, year, month, ids).catch((e) => setActErr(errText(e)));
  }

  async function quyetNhieu(advs: SalaryAdvance[], approve: boolean) {
    setBusyNhieu(true);
    setActErr(null);
    setActVuong([]);
    setDaDuyetNhieu(null);
    try {
      const r = await api.luong.decideAdvancesBulk(token, { ids: advs.map((a) => a.id), approve });
      setDaDuyetNhieu(`Đã ${approve ? "duyệt" : "từ chối"} ${r.items.length} phiếu.`);
      setChon(new Set());
      setChiXemChon(false);
      load();
    } catch (e) {
      // Một phiếu vướng là không phiếu nào đổi — hiện nguyên câu server và cho bỏ chọn đúng phiếu vướng.
      setActErr(errText(e));
      setActVuong(vuongIds(e));
    } finally {
      setBusyNhieu(false);
      setXacNhan(null);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setActErr(null);
    setActVuong([]);
    try {
      await fn();
      load();
    } catch (e) {
      // Huỷ tạm ứng ĐÃ lập phiếu chi bị chặn kèm CÂU GIẢI THÍCH + mã phiếu chi — hiện NGUYÊN CÂU.
      setActErr(errText(e));
    }
  }

  function boChonVuong() {
    setChon((cu) => new Set([...cu].filter((id) => !actVuong.includes(id))));
    setActErr(null);
    setActVuong([]);
  }

  const totalApproved = items
    .filter((a) => a.status === "approved" || a.status === "paid")
    .reduce((s, a) => s + a.amount, 0);
  const biCheKhiXacNhan = xacNhan
    ? xacNhan.advs.filter((a) => !dangLoc.some((b) => b.id === a.id)).length
    : 0;

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar lg-toolbar">
        <div className="lg-toolbar-filters">
          <div className="lg-date-wrapper">
            <span className="lg-date-icon">
              <Calendar size={14} />
            </span>
            <MonthPicker value={ym} onChange={doiKy} ariaLabel="Kỳ lương" />
          </div>
        </div>
        <div className="lg-toolbar-actions">
          <span className="lg-approved-badge">
            Đã duyệt: <b>{money(totalApproved)}đ</b>
          </span>
          {canXuat && (
            <button
              className="btn btn--ghost"
              onClick={() => xuatExcel(dangLoc)}
              title="File chuyển khoản các phiếu đã duyệt / đã chi đang hiện theo tab + bộ lọc — mẫu lô lương BIZ MBBank; tiền mặt ghi TIỀN MẶT"
            >
              Xuất Excel
            </button>
          )}
          {/* MỘT nút cho cả tạm ứng lẫn lương đợt 1, một người hay nhiều người (25/09/2026). */}
          {canCreateAdvance && (
            <button
              className="btn btn--primary"
              onClick={() => setHangLoat(true)}
              title="Lập phiếu tạm ứng / lương đợt 1 — cho một người hoặc chọn tất cả người đủ điều kiện công"
            >
              + Lập phiếu
            </button>
          )}
        </div>
      </div>

      {actErr && (
        <TuNote
          tone="error"
          onClose={() => {
            setActErr(null);
            setActVuong([]);
          }}
          link={
            actVuong.length > 0
              ? { label: `Bỏ chọn ${actVuong.length} phiếu vướng`, onClick: boChonVuong }
              : null
          }
        >
          {actErr}
        </TuNote>
      )}
      {/* Báo THÀNH CÔNG ở lại tới khi tự đóng (không tự tắt sau vài giây) vì nó mang MÃ PHIẾU
          CHI bấm được — mã trôi mất là kế toán phải đi tìm lại trong sổ quỹ. */}
      {pcVuaLap && (
        <TuNote
          tone="success"
          onClose={() => setPcVuaLap(null)}
          link={
            navigate
              ? {
                  label: "Mở phiếu chi",
                  onClick: () => navigate("ke-toan-phieu-chi", { focusVoucherQuery: pcVuaLap.code }),
                }
              : null
          }
        >
          Đã lập phiếu chi <b className="lg-tu-note__code">{pcVuaLap.code}</b>
          {pcVuaLap.soPhieu > 1 ? ` cho ${pcVuaLap.soPhieu} phiếu — tổng ` : " — "}
          {money(pcVuaLap.tong)}đ, tiền đã ra khỏi két.
        </TuNote>
      )}
      {daDuyetNhieu && (
        <TuNote tone="success" onClose={() => setDaDuyetNhieu(null)}>
          {daDuyetNhieu}
        </TuNote>
      )}

      {items.length === 0 ? (
        <div className="lg-table-empty-state">
          <div className="lg-table-empty-icon">
            <Wallet size={20} />
          </div>
          <span className="lg-table-empty-title">Chưa có tạm ứng tháng này</span>
          <span className="lg-table-empty-desc">
            Nhấp nút "+ Lập phiếu" để lập phiếu tạm ứng / lương đợt 1 cho nhân viên trong kỳ.
          </span>
        </div>
      ) : (
        <>
          <TamUngBoLoc tab={tab} onTab={doiTab} dem={dem} loc={loc} onLoc={doiLoc} to={to} />
          <TamUngChonNhieu
            tab={tab}
            tabRows={tabRows}
            dangLoc={dangLoc}
            chon={chon}
            setChon={setChon}
            chiXemChon={chiXemChon}
            setChiXemChon={(v) => {
              setChiXemChon(v);
              setTrang(1);
            }}
            busy={busyNhieu}
            canDuyet={canApproveAdvance}
            canLapPhieuChi={canLapPhieuChi}
            canXuat={canXuat}
            onDuyet={(advs) => setXacNhan({ duyet: true, advs })}
            onTuChoi={(advs) => setXacNhan({ duyet: false, advs })}
            onLapPhieuChi={(advs) => setPcNhieuCho(advs)}
            onXuatExcel={xuatExcel}
          />
          {hien.length === 0 ? (
            <div className="lg-table-empty-state">
              <span className="lg-table-empty-title">Không có phiếu nào khớp</span>
              <span className="lg-table-empty-desc">
                Đổi tab trạng thái, bỏ bớt bộ lọc loại / tổ hoặc từ khoá tìm rồi xem lại.
              </span>
            </div>
          ) : (
            <>
              <TamUngBang
                rows={trangNay}
                coCotChon={coCotChon}
                chon={chon}
                setChon={setChon}
                navigate={canXemPhieuChi ? navigate : undefined}
                canApproveAdvance={canApproveAdvance}
                canLapPhieuChi={canLapPhieuChi}
                act={act}
                token={token}
                onLapPhieuChi={setLapPcCho}
              />
              <Pager
                total={hien.length}
                page={trang}
                size={CO_TRANG}
                onPage={setTrang}
                unit="phiếu"
                note={coCotChon ? "ô tick đầu bảng chọn cả trang đang xem" : undefined}
              />
            </>
          )}
        </>
      )}

      {hangLoat && (
        <LapHangLoatModal
          token={token}
          year={year}
          month={month}
          onClose={() => setHangLoat(false)}
          onSaved={() => {
            setHangLoat(false);
            load();
          }}
        />
      )}

      {pcNhieuCho && (
        <PhieuChiMotLuotModal
          token={token}
          advs={pcNhieuCho}
          onClose={() => setPcNhieuCho(null)}
          onDone={(r) => {
            const [pc] = r.vouchers;
            setPcVuaLap({ id: pc.id, code: pc.code, tong: r.total_amount, soPhieu: pcNhieuCho.length });
            setPcNhieuCho(null);
            setActErr(null);
            setChon(new Set());
            setChiXemChon(false);
            load();
          }}
        />
      )}

      <ConfirmDialog
        open={xacNhan != null}
        title={`${xacNhan?.duyet ? "Duyệt" : "Từ chối"} ${xacNhan?.advs.length ?? 0} phiếu?`}
        message={
          xacNhan
            ? tachLoai(xacNhan.advs) +
              (biCheKhiXacNhan > 0
                ? ` — trong đó ${biCheKhiXacNhan} phiếu đang không hiện vì bộ lọc.`
                : ".") +
              (xacNhan.duyet
                ? ""
                : " Phiếu bị từ chối không duyệt lại được — muốn ứng tiếp thì lập phiếu mới.")
            : undefined
        }
        confirmLabel={`${xacNhan?.duyet ? "Duyệt" : "Từ chối"} ${xacNhan?.advs.length ?? 0} phiếu`}
        danger={!xacNhan?.duyet}
        busy={busyNhieu}
        onConfirm={() => xacNhan && void quyetNhieu(xacNhan.advs, xacNhan.duyet)}
        onCancel={() => setXacNhan(null)}
      />

      {lapPcCho && (
        <LapPhieuChiModal
          token={token}
          adv={lapPcCho}
          onClose={() => setLapPcCho(null)}
          onDone={(pc) => {
            setLapPcCho(null);
            setActErr(null);
            setPcVuaLap({ id: pc.id, code: pc.code, tong: pc.amount, soPhieu: 1 });
            load();
          }}
        />
      )}
    </div>
  );
}
