// VIEW "THẺ CÔNG VIỆC" (WORKSTATION TASK CARDS) của Bàn tổ — Chế độ hiển thị rộng rãi,
// trực quan, giúp thợ & tổ trưởng dễ theo dõi sản lượng, trạng thái và bấm thao tác 1-click.
import { Icon, type IconName } from "../components/Icons";
import type { SxVatTuDinhMuc, SxWorkItem } from "../api/client";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { phutChayText, slText, sxNguonIcon, sxSerial, ThsxTrangThaiPill } from "./thsxShared";

interface Props {
  timed: SxWorkItem[];
  outWin: SxWorkItem[];
  untimed: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
  onBatDau?: (w: SxWorkItem) => void;
  onTamDung?: (w: SxWorkItem) => void;
  onKetThuc?: (w: SxWorkItem) => void;
}

function dinhMucText(vt: SxVatTuDinhMuc[]): string {
  if (!vt || vt.length === 0) return "";
  const head = vt.slice(0, 2).map((v) => {
    const ten = (v.ten || "").trim() || "—";
    const sl = v.so_luong == null ? "" : ` ${num(v.so_luong)}${v.don_vi ? ` ${nhanDonVi(v.don_vi)}` : ""}`;
    return `${ten}${sl}`;
  });
  const rest = vt.length - head.length;
  return rest > 0 ? `${head.join(", ")} +${rest} khác` : head.join(", ");
}

export function ThsxCards({
  timed, outWin, untimed, selectedId, onPick, onBatDau, onTamDung, onKetThuc,
}: Props) {
  return (
    <div className="thsx-cards__scroll">
      <CardSection
        label="Trong cửa sổ" icon="calendar" viec={timed}
        selectedId={selectedId} onPick={onPick}
        onBatDau={onBatDau} onTamDung={onTamDung} onKetThuc={onKetThuc}
      />
      <CardSection
        label="Ngoài cửa sổ" icon="history" viec={outWin}
        selectedId={selectedId} onPick={onPick}
        onBatDau={onBatDau} onTamDung={onTamDung} onKetThuc={onKetThuc}
      />
      <CardSection
        label="Chưa định giờ" icon="clock" viec={untimed}
        selectedId={selectedId} onPick={onPick}
        onBatDau={onBatDau} onTamDung={onTamDung} onKetThuc={onKetThuc}
      />
    </div>
  );
}

function CardSection({
  label, icon, viec, selectedId, onPick, onBatDau, onTamDung, onKetThuc,
}: {
  label: string;
  icon: IconName;
  viec: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
  onBatDau?: (w: SxWorkItem) => void;
  onTamDung?: (w: SxWorkItem) => void;
  onKetThuc?: (w: SxWorkItem) => void;
}) {
  if (viec.length === 0) return null;
  return (
    <div className="thsx-cards__sec">
      <div className="thsx-cards__sech">
        <Icon name={icon} size={14} /> <span>{label}</span>
        <span className="thsx-cards__secn thsx-num">{viec.length}</span>
      </div>
      <div className="thsx-cards__grid">
        {viec.map((w) => (
          <TaskCard
            key={w.id} w={w} selected={w.id === selectedId}
            onPick={() => onPick(w)}
            onBatDau={onBatDau ? () => onBatDau(w) : undefined}
            onTamDung={onTamDung ? () => onTamDung(w) : undefined}
            onKetThuc={onKetThuc ? () => onKetThuc(w) : undefined}
          />
        ))}
      </div>
    </div>
  );
}

function TaskCard({
  w, selected, onPick, onBatDau, onTamDung, onKetThuc,
}: {
  w: SxWorkItem;
  selected: boolean;
  onPick: () => void;
  onBatDau?: () => void;
  onTamDung?: () => void;
  onKetThuc?: () => void;
}) {
  const phut = phutChayText(w);
  const vatTu = dinhMucText(w.dinh_muc_vat_tu);

  return (
    <div
      className={`thsx-card${selected ? " thsx-card--sel" : ""}${w.la_kcs ? " thsx-card--kcs" : ""}`}
      tabIndex={0}
      role="region"
      aria-label={`Thẻ việc ${w.ten_cong_doan || ""}`}
      onClick={onPick}
      onKeyDown={(e) => { if (e.key === "Enter") { onPick(); } }}
    >
      {/* Header thẻ */}
      <div className="thsx-card__top">
        <div className="thsx-card__serial-grp">
          <Icon name={sxNguonIcon(w.nguon_loai)} size={14} className="thsx-card__src-ic" />
          <span className="thsx-card__serial thsx-num">{sxSerial(w.nguon_ma)}</span>
        </div>
        <ThsxTrangThaiPill tt={w.trang_thai} size="sm" />
      </div>

      {w.nguon_ten && (
        <div className="thsx-card__src-name" title={w.nguon_ten}>
          {w.nguon_ten}
        </div>
      )}

      {/* Tên công đoạn & máy */}
      <div className="thsx-card__body">
        <h3 className="thsx-card__title">
          {w.ten_cong_doan || "—"}
          {w.la_kcs && <span className="thsx-card__kcs-badge">KCS</span>}
        </h3>

        <div className="thsx-card__chips">
          {w.may && (
            <span className="thsx-card__chip thsx-card__chip--may">
              <Icon name="printer" size={12} /> {w.may}
            </span>
          )}
          <ChipLoaiBuoc loai_buoc={w.loai_buoc} nha_cung_cap={w.nha_cung_cap} />
          <ChipKhuon can_khuon={!!w.khuon} khuon={{ ...(w.khuon ?? {}), da_nhan: w.khuon_da_nhan }} />
        </div>

        {/* Khối lượng & Thời gian */}
        <div className="thsx-card__metrics">
          <div className="thsx-card__metric">
            <span className="thsx-card__metric-lbl">Khối lượng</span>
            <span className="thsx-card__metric-val thsx-num">{slText(w)}</span>
          </div>
          {phut && (
            <div className="thsx-card__metric">
              <span className="thsx-card__metric-lbl">Thời lượng</span>
              <span className="thsx-card__metric-val thsx-num">{phut}</span>
            </div>
          )}
        </div>

        {/* Định mức vật tư nếu có */}
        {vatTu && (
          <div className="thsx-card__vattu" title={vatTu}>
            <Icon name="box" size={12} />
            <span>{vatTu}</span>
          </div>
        )}

        {w.du_kien_bat_dau && (
          <div className="thsx-card__time">
            <Icon name="clock" size={12} />
            <span className="thsx-num">{ngayGio(w.du_kien_bat_dau)}</span>
          </div>
        )}
      </div>

      {/* Footer 1-Click Action Bar */}
      <div className="thsx-card__ftr" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="thsx-card__btn thsx-card__btn--subtle"
          title="Xem chi tiết việc"
          onClick={onPick}
        >
          <Icon name="clipboard" size={13} /> Chi tiết
        </button>

        {w.trang_thai === "released" && onBatDau && (
          <button
            type="button"
            className="thsx-card__btn thsx-card__btn--start"
            onClick={onBatDau}
          >
            <Icon name="play" size={13} /> Bắt đầu
          </button>
        )}

        {w.trang_thai === "paused" && onBatDau && (
          <button
            type="button"
            className="thsx-card__btn thsx-card__btn--start"
            onClick={onBatDau}
          >
            <Icon name="play" size={13} /> Tiếp tục
          </button>
        )}

        {w.trang_thai === "running" && (
          <div className="thsx-card__btn-group">
            {onTamDung && (
              <button
                type="button"
                className="thsx-card__btn thsx-card__btn--pause"
                onClick={onTamDung}
                title="Tạm dừng"
              >
                <Icon name="pause" size={13} /> Tạm dừng
              </button>
            )}
            {onKetThuc && (
              <button
                type="button"
                className="thsx-card__btn thsx-card__btn--done"
                onClick={onKetThuc}
                title="Kết thúc việc"
              >
                <Icon name="check" size={13} /> Kết thúc
              </button>
            )}
          </div>
        )}

        {w.trang_thai === "completed" && (
          <span className="thsx-card__done-lbl">
            <Icon name="check" size={13} /> Đã xong
          </span>
        )}
      </div>
    </div>
  );
}
