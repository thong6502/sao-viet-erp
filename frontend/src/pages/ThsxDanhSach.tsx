// VIEW "DANH SÁCH BẢN GHI" của bàn tổ (Workstation Studio Table View)
// Thiết kế gọn gàng, hiện đại, tối ưu chiều cao hàng, các thẻ quy cách nằm ngang sắc nét.
import { Icon } from "../components/Icons";
import type { SxLenhNhom, SxVatTuDinhMuc, SxWorkItem, SxQuyCachThe } from "../api/client";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { ThsxLenhGroups } from "./ThsxLenhGroups";
import { slText, sxNguonIcon, sxSerial, ThsxTrangThaiPill } from "./thsxShared";

interface Props {
  /** MỘT TRANG lệnh/bài ghép (máy chủ đã cắt, đếm theo lệnh); bảng bước nằm trong từng lệnh. */
  lenh: SxLenhNhom[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
  onBatDau?: (w: SxWorkItem) => void;
  onTamDung?: (w: SxWorkItem) => void;
  onKetThuc?: (w: SxWorkItem) => void;
}

/** Tóm tắt quy cách in gọn gàng trên 1 dòng duy nhất với dấu chấm giữa */
function renderQuyCachLine(qc: SxQuyCachThe | null | undefined) {
  if (!qc) return null;
  const parts: string[] = [];
  if (qc.giay) parts.push(`${qc.giay}${qc.dinh_luong ? ` ${qc.dinh_luong}gsm` : ""}`);
  else if (qc.dinh_luong) parts.push(`${qc.dinh_luong}gsm`);
  if (qc.kho_in) parts.push(`Khổ ${qc.kho_in}`);
  if (qc.so_mau != null) parts.push(`${qc.so_mat ? `${qc.so_mat} mặt ` : ""}${qc.so_mau} màu`);
  if (qc.so_kem != null && qc.so_kem > 0) parts.push(`${qc.so_kem} kẽm`);

  if (parts.length === 0) return null;

  return (
    <div className="thsx-ds__qc-line" title={parts.join(" · ")}>
      {parts.join(" · ")}
    </div>
  );
}

/** Format định mức vật tư dạng 1 dòng gọn */
function renderVatTuInline(vt: SxVatTuDinhMuc[]) {
  if (!vt || vt.length === 0) return <span className="thsx-ds__vt-none">—</span>;
  const v = vt[0];
  const ten = (v.ten || "").trim() || "—";
  const sl = v.so_luong == null ? "" : ` ${num(v.so_luong)}${v.don_vi ? ` ${nhanDonVi(v.don_vi)}` : ""}`;
  const rest = vt.length - 1;

  return (
    <div className="thsx-ds__vt-inline" title={vt.map((x) => `${x.ten || ""} ${num(x.so_luong)}${x.don_vi || ""}`).join(", ")}>
      <span className="thsx-ds__vt-text">
        <b>{ten}</b>
        {sl && <span className="thsx-num thsx-ds__vt-val">{sl}</span>}
      </span>
      {rest > 0 && <span className="thsx-ds__vt-more">+{rest} khác</span>}
    </div>
  );
}

/** Format thời lượng chạy rút gọn (VD: "84 phút") */
function phutChayGon(w: SxWorkItem): { main: string; sub?: string } | null {
  if (w.chay_phut == null || w.chay_phut <= 0) return null;
  const giua = Math.round(w.chay_phut);
  const lo = w.chay_phut_min == null ? giua : Math.round(w.chay_phut_min);
  const hi = w.chay_phut_max == null ? giua : Math.round(w.chay_phut_max);
  const sub = lo !== giua || hi !== giua ? `Dải: ${lo}–${hi} phút` : undefined;
  return { main: `${giua} phút`, sub };
}

export function ThsxDanhSach({
  lenh, selectedId, onPick, onBatDau, onTamDung, onKetThuc,
}: Props) {
  return (
    <div className="thsx-ds__scroll">
      <ThsxLenhGroups
        lenh={lenh}
        selectedId={selectedId}
        render={(viec) => (
          <DsBang
            viec={viec}
            selectedId={selectedId}
            onPick={onPick} onBatDau={onBatDau} onTamDung={onTamDung} onKetThuc={onKetThuc}
          />
        )}
      />
    </div>
  );
}

/** Bảng bước CỦA MỘT LỆNH. Nhãn "đang chạy / tạm dừng" của khúc đầu bảng đã dời lên dòng lệnh
 *  (`LenhDigest`), ở đây chỉ còn bảng — khỏi đếm hai lần trên cùng một màn. */
function DsBang({
  viec, selectedId, onPick, onBatDau, onTamDung, onKetThuc,
}: {
  viec: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
  onBatDau?: (w: SxWorkItem) => void;
  onTamDung?: (w: SxWorkItem) => void;
  onKetThuc?: (w: SxWorkItem) => void;
}) {
  if (viec.length === 0) return null;

  return (
    <div className="thsx-ds__sec">
      <div className="thsx-ds__tbl-wrap">
        <table className="thsx-ds__tbl">
          <thead>
            <tr>
              <th className="thsx-ds__th-src">Nguồn & Mã</th>
              <th className="thsx-ds__th-cd">Công đoạn & Quy cách</th>
              <th className="thsx-ds__th-may">Máy / Trạm</th>
              <th className="thsx-ds__th-gio">Giờ hẹn</th>
              <th className="thsx-ds__th-sl">Tiến độ sản lượng</th>
              <th className="thsx-ds__th-vt">Định mức vật tư</th>
              <th className="thsx-ds__th-act">Trạng thái & Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {viec.map((w) => {
              const isSelected = w.id === selectedId;
              return (
                <DsRowBlock
                  key={w.id}
                  w={w}
                  selected={isSelected}
                  onPick={() => onPick(w)}
                  onBatDau={onBatDau ? () => onBatDau(w) : undefined}
                  onTamDung={onTamDung ? () => onTamDung(w) : undefined}
                  onKetThuc={onKetThuc ? () => onKetThuc(w) : undefined}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DsRowBlock({
  w, selected, onPick, onBatDau, onTamDung, onKetThuc,
}: {
  w: SxWorkItem;
  selected: boolean;
  onPick: () => void;
  onBatDau?: () => void;
  onTamDung?: () => void;
  onKetThuc?: () => void;
}) {
  const durInfo = phutChayGon(w);
  const daLam = w.da_lam ?? 0;
  const mucTieu = w.muc_tieu ?? w.so_luong_ra ?? 0;
  const pct = mucTieu > 0 ? Math.min(100, Math.round((daLam / mucTieu) * 100)) : 0;
  const statusCls = `thsx-ds__row--${w.trang_thai}`;

  return (
    <tr
      className={`thsx-ds__row ${statusCls}${selected ? " thsx-ds__row--sel" : ""}${w.la_kcs ? " thsx-ds__row--kcs" : ""}`}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      onClick={onPick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}
    >
      {/* Nguồn & Mã */}
      <td>
        <div className="thsx-ds__src-cell">
          <div className="thsx-ds__src-main">
            <span className="thsx-ds__src">
              <Icon name={sxNguonIcon(w.nguon_loai)} size={13} className="thsx-ds__src-ic" />
              <span className="thsx-num">{sxSerial(w.nguon_ma)}</span>
            </span>
            {w.nguon_ten && (
              <div className="thsx-ds__srcten" title={w.nguon_ten}>
                {w.nguon_ten}
              </div>
            )}
          </div>
        </div>
      </td>

      {/* Công đoạn & Quy cách */}
      <td>
        <div className="thsx-ds__cd-cell">
          <div className="thsx-ds__cd-head">
            <span className="thsx-ds__cd-name">{w.ten_cong_doan || "—"}</span>
            {w.la_kcs && <span className="thsx-lrow__kcs thsx-ds__kcs">KCS</span>}
            <ChipLoaiBuoc loai_buoc={w.loai_buoc} nha_cung_cap={w.nha_cung_cap} />
            <ChipKhuon can_khuon={!!w.khuon} khuon={{ ...(w.khuon ?? {}), da_nhan: w.khuon_da_nhan }} />
          </div>
          {renderQuyCachLine(w.quy_cach)}
        </div>
      </td>

      {/* Máy */}
      <td>
        {w.may ? (
          <span className="thsx-ds__may-chip">
            <Icon name="printer" size={11} />
            <span>{w.may}</span>
          </span>
        ) : (
          <span className="thsx-ds__empty-val">—</span>
        )}
      </td>

      {/* Giờ hẹn & Thời lượng */}
      <td>
        <div className="thsx-ds__time-cell">
          <span className="thsx-ds__time-val thsx-num">
            {w.du_kien_bat_dau ? ngayGio(w.du_kien_bat_dau) : "—"}
          </span>
          {durInfo && (
            <span className="thsx-ds__dur-inline thsx-num" title={durInfo.sub}>
              <Icon name="clock" size={10} /> {durInfo.main}
            </span>
          )}
        </div>
      </td>

      {/* Sản lượng & Tiến độ */}
      <td>
        <div className="thsx-ds__sl-cell">
          <div className="thsx-ds__sl-main thsx-num" title={w.sl_dien_giai || undefined}>
            {slText(w)}
          </div>
          {mucTieu > 0 ? (
            <div className="thsx-ds__prog-wrap">
              <div className="thsx-ds__prog-bar">
                <div className="thsx-ds__prog-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="thsx-ds__prog-txt thsx-num">
                <span>{num(daLam)}/{num(mucTieu)}</span>
                <b>{pct}%</b>
              </div>
            </div>
          ) : null}
          {w.thuc_nhan != null && (
            <div className="thsx-ds__recv-badge thsx-num">
              Đã nhận: {num(w.thuc_nhan)}
            </div>
          )}
        </div>
      </td>

      {/* Định mức vật tư */}
      <td>{renderVatTuInline(w.dinh_muc_vat_tu)}</td>

      {/* Trạng thái & Thao tác nhanh */}
      <td>
        <div className="thsx-ds__act-cell" onClick={(e) => e.stopPropagation()}>
          <ThsxTrangThaiPill tt={w.trang_thai} size="xs" />
          {(w.trang_thai === "released" || w.trang_thai === "paused") && w.chay_duoc && onBatDau && (
            <button
              type="button"
              className="thsx-ds__actbtn thsx-ds__actbtn--play"
              title="Bắt đầu thực hiện công việc"
              onClick={onBatDau}
            >
              <Icon name="play" size={11} /> Bắt đầu
            </button>
          )}
          {w.trang_thai === "running" && w.chay_duoc && (
            <div className="thsx-ds__act-grp">
              {onTamDung && (
                <button
                  type="button"
                  className="thsx-ds__actbtn thsx-ds__actbtn--pause"
                  title="Tạm dừng công việc"
                  onClick={onTamDung}
                >
                  <Icon name="pause" size={11} /> Tạm dừng
                </button>
              )}
              {onKetThuc && (
                <button
                  type="button"
                  className="thsx-ds__actbtn thsx-ds__actbtn--check"
                  title="Hoàn thành & Kết thúc"
                  onClick={onKetThuc}
                >
                  <Icon name="check" size={11} /> Kết thúc
                </button>
              )}
            </div>
          )}
          <button
            type="button"
            className="thsx-ds__actbtn thsx-ds__actbtn--view"
            title="Mở chi tiết công việc ở panel phải"
            onClick={onPick}
          >
            <Icon name="chevron" size={11} className="thsx-rot270" />
          </button>
        </div>
      </td>
    </tr>
  );
}


