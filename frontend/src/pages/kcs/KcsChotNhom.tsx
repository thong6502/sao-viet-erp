// CHỐT NHÓM ở màn KCS — cửa vào cho hai việc §13.3/§14.2 trước đây không màn nào mở được:
//   · "Đóng thiếu nhóm"  — nhóm giao hụt (960/1.000) phải có người đóng lại, nếu không lệnh treo.
//   · "Phân loại BTP dư" — cổng đóng đòi "hết BTP chờ kho nhận"; không phân loại thì không giải được.
// Hai panel này vốn nằm trong drawer bàn tổ (`ThsxDrawer`), nhưng drawer đó chỉ sống ở
// `ThucHienSxPage mode="production"` — nơi backend lọc `la_kcs=false` — nên bước KCS không bao giờ
// mở tới. Chỗ đúng của chúng là màn KCS: §13.3 giao việc đóng thiếu cho TRƯỞNG KCS.
//
// Component tự gọi API (trang KCS không có controller `exec` của bàn tổ) và chỉ mượn lại phần
// hiển thị: `ThsxDongNhomPanel` + `PhanLoaiBtpForm` — hai panel đã được sửa để nhận đúng một mặt
// ghi thay vì cả object `ThsxExec`.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, api,
  type SxDongNhomDieuKien, type SxDongThieuIn, type SxKhoChiTiet, type SxLyDo,
  type SxPhanLoaiBtpIn, type SxWorkItem,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { num } from "../keHoachSxShared";
import { ThsxDongNhomPanel, PhanLoaiBtpForm, PL_LABEL } from "../ThsxG5";
import "../thuc-hien-sx.css";

interface NhomRow {
  nhomId: number;
  nhan: string;
  /** Các bước KCS của CHÍNH tổ này thuộc nhóm — nguồn để phân loại BTP dư theo công việc. */
  viec: SxWorkItem[];
}

export function KcsChotNhom({
  items, canAssign, eventTick, onDone,
}: {
  items: SxWorkItem[];
  canAssign: boolean;
  /** Bump khi có sự kiện SX (SSE) — tải lại điều kiện của nhóm đang mở. */
  eventTick?: number;
  onDone: () => void;
}) {
  const { token } = useAuth();
  const [moId, setMoId] = useState<number | null>(null);

  // Gom nhóm theo ĐÚNG luật rơi-về của backend (`dong_nhom._danh_gia`): ưu tiên bước `la_kcs_cuoi`;
  // chỉ khi tổ không có bước nào được đánh dấu KCS cuối mới rơi về `la_kcs`. `la_kcs_cuoi` chỉ được
  // gán thật lúc phát hành LSX, nên dữ liệu dựng tay chỉ có `la_kcs`.
  const nhomRows: NhomRow[] = useMemo(() => {
    const coNhom = items.filter((i) => i.nhom_id != null);
    const nguon = coNhom.some((i) => i.la_kcs_cuoi)
      ? coNhom.filter((i) => i.la_kcs_cuoi)
      : coNhom.filter((i) => i.la_kcs);
    const theoNhom = new Map<number, NhomRow>();
    for (const i of nguon) {
      const id = i.nhom_id!;
      const cu = theoNhom.get(id);
      if (cu) { cu.viec.push(i); continue; }
      theoNhom.set(id, {
        nhomId: id,
        nhan: [i.nguon_ma, i.nhom].filter(Boolean).join(" · ") || `Nhóm #${id}`,
        viec: [i],
      });
    }
    return [...theoNhom.values()];
  }, [items]);

  if (nhomRows.length === 0) return null;

  return (
    <section className="kcs-section">
      <h2>Chốt nhóm <span className="rc__count">{nhomRows.length}</span></h2>
      <p className="kcs-chot__hint">
        Nhóm kiểm đủ thì tự đóng. Nhóm giao hụt hoặc còn BTP dư thì chốt tại đây.
      </p>
      <ul className="kcs-chot">
        {nhomRows.map((n) => (
          <li key={n.nhomId} className="kcs-chot__it">
            <button type="button" className="kcs-chot__hd" aria-expanded={moId === n.nhomId}
              onClick={() => setMoId((cu) => (cu === n.nhomId ? null : n.nhomId))}>
              <Icon name="chevron" size={14} className={`kcs-chot__ic${moId === n.nhomId ? " is-open" : ""}`} />
              <span className="kcs-chot__ten">{n.nhan}</span>
              <span className="kcs-chot__sl">{n.viec.length} bước KCS</span>
            </button>
            {moId === n.nhomId && (
              <ChotNhomThan nhom={n} token={token} canAssign={canAssign} eventTick={eventTick} onDone={onDone} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ChotNhomThan({
  nhom, token, canAssign, eventTick, onDone,
}: {
  nhom: NhomRow;
  token: string | null;
  canAssign: boolean;
  eventTick?: number;
  onDone: () => void;
}) {
  const [dieuKien, setDieuKien] = useState<SxDongNhomDieuKien | null>(null);
  const [kho, setKho] = useState<SxKhoChiTiet | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [plOpen, setPlOpen] = useState(false);
  const [cvId, setCvId] = useState<number>(nhom.viec[0].id);
  const lyDoCache = useRef<Record<string, SxLyDo[]>>({});

  const tai = useCallback(() => {
    if (!token) return;
    Promise.all([
      api.sanXuat.dieuKienDongNhom(token, nhom.nhomId),
      api.sanXuat.khoChiTietNhom(token, nhom.nhomId).catch(() => null),
    ])
      .then(([dk, k]) => { setDieuKien(dk); setKho(k); setLoi(null); })
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không đọc được điều kiện đóng nhóm."));
  }, [token, nhom.nhomId]);

  useEffect(() => { tai(); }, [tai, eventTick]);

  const loadLyDo = useCallback(async (n: string): Promise<SxLyDo[]> => {
    if (!token) return [];
    const c = lyDoCache.current[n];
    if (c) return c;
    try {
      const r = await api.sanXuat.lyDo(token, n);
      lyDoCache.current[n] = r.items;
      return r.items;
    } catch { return []; }
  }, [token]);

  // Một đường ghi duy nhất cho cả hai mặt: gọi → tải lại điều kiện → báo cho trang làm mới bảng.
  async function ghi(goi: () => Promise<unknown>): Promise<boolean> {
    if (!token || busy) return false;
    setBusy(true);
    setLoi(null);
    try {
      await goi();
      tai();
      onDone();
      return true;
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const onDongThieu = (nhomId: number, body: SxDongThieuIn) =>
    ghi(() => api.sanXuat.dongThieu(token!, nhomId, body));
  const onPhanLoai = (body: SxPhanLoaiBtpIn) =>
    ghi(() => api.sanXuat.phanLoaiBtp(token!, body));

  const cv = nhom.viec.find((v) => v.id === cvId) ?? nhom.viec[0];
  const daPhanLoai = kho?.lot ?? [];

  return (
    <div className="kcs-chot__than">
      {loi && <div className="banner banner--error" role="alert"><span>{loi}</span></div>}

      <ThsxDongNhomPanel dieuKien={dieuKien} canAssign={canAssign} busy={busy}
        loadLyDo={loadLyDo} onDongThieu={onDongThieu} />

      <section className="thsx-psec thsx-x">
        <div className="thsx-psec__h">
          <span className="thsx-psec__title"><Icon name="box" size={13} /> BTP dư</span>
        </div>
        {canAssign && (
          <div className="thsx-x-pb--empty">
            <span className="thsx-x-pb__none">Phân loại phần bán thành phẩm còn dư.</span>
            <Button variant="ghost" onClick={() => setPlOpen((o) => !o)} disabled={busy} aria-expanded={plOpen}>
              <Icon name="plus" size={12} /> Phân loại
            </Button>
          </div>
        )}
        {plOpen && (
          <>
            {nhom.viec.length > 1 && (
              <label className="kcs-chot__cv">
                <span>Của bước</span>
                <select className="thsx-x-sel" value={cvId} onChange={(e) => setCvId(Number(e.target.value))}>
                  {nhom.viec.map((v) => (
                    <option key={v.id} value={v.id}>{v.ten_cong_doan}</option>
                  ))}
                </select>
              </label>
            )}
            <PhanLoaiBtpForm cvId={cv.id} donVi={cv.don_vi_ra ?? cv.don_vi_vao ?? null}
              slBatches={[]} busy={busy} onXong={() => setPlOpen(false)} onPhanLoai={onPhanLoai} />
          </>
        )}
        {daPhanLoai.length === 0 ? (
          <p className="thsx-x-pb__none">Chưa phân loại phần dư nào.</p>
        ) : (
          // MỘT danh sách duy nhất: `kho.lot` đã bao gồm cả lô đang chờ kho nhận, nên không lặp lại
          // `btp_tra_cho_kho` — bày cả hai thì mỗi lô BTP chờ hiện hai lần.
          <ul className="thsx-x-list">
            {daPhanLoai.map((lot) => (
              <li key={lot.id} className="thsx-x-vt">
                <Icon name={lot.kho_xac_nhan ? "packageCheck" : "box"} size={15}
                  className={`thsx-x-vt__ic${lot.kho_xac_nhan ? " is-ok" : ""}`} />
                <span className="thsx-x-vt__ma">
                  {lot.loai_hang === "thanh_pham" ? "Thành phẩm" : PL_LABEL[lot.phan_loai ?? "nhap_btp"]}
                </span>
                <span className="thsx-num">{num(lot.so_luong)} {lot.don_vi}</span>
                <span className="thsx-x-item__spacer" />
                <span className={`thsx-x-pill ${lot.kho_xac_nhan ? "thsx-x-pill--ok" : "thsx-x-pill--wait"}`}>
                  {lot.kho_xac_nhan ? "đã vào sổ" : "chờ kho nhận"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
