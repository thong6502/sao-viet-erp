// Tab THEO MÁY của màn "Theo dõi sản xuất" (Task 17b, Bước 4) — mini-Gantt theo lane máy.
//
// Khối trong lane = MỘT CÔNG VIỆC, có thể phục vụ NHIỀU lệnh (`block.lsx`, khác hẳn card Kanban
// vốn neo cứng một lệnh). Ràng buộc C123 (chủ dự án đã đọc và duyệt): bấm khối có ĐÚNG 1 lệnh thì
// mở thẳng hồ sơ; TỪ 2 lệnh trở lên thì BẮT BUỘC bày danh sách cho người dùng chọn, CẤM đoán lấy
// lệnh đầu tiên.
//
// C129: lane "Chưa xếp máy" (`may_id === null`) đặt ĐẦU danh sách — ngược với thứ tự máy chủ trả
// (`_khoa_lane_may` xếp nó CUỐI, xem `bang_theo_doi.py`), vì đây là hộp việc-cần-làm của điều độ,
// không phải rổ hứng dữ liệu lọt lưới như cột "Khác" của Kanban. Sắp lại HOÀN TOÀN ở phía client,
// không đổi gì ở phần còn lại của thứ tự máy chủ trả.
//
// C124 — CHỈ vẽ mốc KẾ HOẠCH (`du_kien_bat_dau`/`du_kien_ket_thuc`); vế THỰC TẾ chưa có ở API này.
// "Chừa khung": viền ngoài khối = 100% khung KẾ HOẠCH, bên trong trừ ra một dải `--tdsx-tm-inner`
// (4px hai mép, đúng biến `inner` mà `Xl2Gantt.tsx:779-800` dùng) làm vùng lõi. Task 17b để vùng
// lõi TRỐNG (chỉ tô phẳng theo trạng thái) — khi có vế thực tế, chỉ cần thêm MỘT `<span>` con tô
// dải `--moss` từ mép trái vùng lõi rộng theo `%` tiến độ (đúng khuôn "lớp thực tế đè lên, không vẽ
// lại" đã chạy ở `Xl2Gantt`/`ThucHienSxPage`) — không phải sửa cấu trúc DOM/CSS của khối.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { TdsxLsxThamChieu, TdsxMayLane, TdsxMayLaneBlock, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { nhanTomTat } from "../components/ChipBuoc";
import { Icon } from "../components/Icons";
import { EmptyState } from "./keHoachSxShared";
import { TDSX_TT_META, tdsxTtMeta } from "./TdsxKanban";
import { ChonLenhPopover, useChonLenh } from "./tdsxChonLenh";
import { useTdsxTimeline, type TdsxTimelineMoc } from "./tdsxTimeline";

/** Bề rộng cột nhãn máy (sticky trái) — hằng SỐ vì cả nhãn lẫn track đều cần biết để tính
 *  `grid-template-columns` bằng tay (CSS Grid không tự đồng bộ được state layout kiểu này). */
const LABEL_W = 176;
/** Block hẹp hơn mức này (px) thì rút nhãn chỉ còn mã lệnh — đúng cách `Xl2Gantt` rút gọn theo
 *  `isWide`/`isMedium`, không đẻ quy ước mới. */
const BLOCK_HEP_PX = 90;
/** Dưới mức này thì KHÔNG in chữ nào. `.tdsx-tm__inner` chừa 4px mỗi mép, chữ `--fs-2xs` hệ
 *  monospace rộng ~6,5px/ký tự ⇒ 44px chỉ vừa 4-5 ký tự. Trước đây mọi block hẹp đều in NGUYÊN
 *  `LSX26-0029` rồi để `text-overflow` cắt: block 20px thật sự hiện ra "5-", block 24px ra "6-" —
 *  rác, tệ hơn là để trống (tooltip `title` vẫn có đủ mã + trạng thái). */
const BLOCK_RAT_HEP_PX = 44;
const BLOCK_TOI_THIEU_PX = 20;

/** "LSX26-0029" → "0029". Đoạn đuôi là phần người xưởng đọc để phân biệt lệnh; tiền tố năm giống
 *  nhau ở mọi lệnh nên cắt đi không mất thông tin phân biệt. */
function maNgan(ma: string): string {
  const i = ma.lastIndexOf("-");
  return i >= 0 && i < ma.length - 1 ? ma.slice(i + 1) : ma;
}

export function TdsxTheoMay({
  active,
  token,
  params,
  refreshTick,
  onOpenHoSo,
  onXoaLoc,
}: {
  active: boolean;
  token: string | null;
  params: TdsxThanhLocParams;
  refreshTick: number;
  onOpenHoSo: (lsxId: number) => void;
  onXoaLoc: () => void;
}) {
  const [lanes, setLanes] = useState<TdsxMayLane[]>([]);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false);
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    // KHÔNG truyền `tu`/`den`: vắng mặt cả hai = "backlog trọn đời" (docstring `bang_theo_doi.
    // theo_may`) — 17b không thêm điều hướng khoảng ngày, trục giờ tự tính từ chính mốc dữ liệu trả
    // về (xem `useMemo` domain bên dưới).
    api.theoDoiSanXuat
      .theoMay(token, params)
      .then((r) => {
        setLanes(r.lanes);
        setLoi(null);
        setDaTai(true);
      })
      .catch((e) => {
        const cam = e instanceof ApiError && e.isForbidden;
        setLoi({
          text: cam
            ? "Bạn không có quyền xem Theo dõi sản xuất."
            : "Không tải được bảng Theo dõi sản xuất. Kiểm tra mạng rồi thử lại.",
          cam,
        });
      })
      .finally(() => setLoading(false));
  }, [token, params]);

  useEffect(() => {
    if (!active) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, load, refreshTick]);

  // C129: kéo lane `may_id === null` lên ĐẦU. Backend luôn trả ĐÚNG MỘT lane như vậy (LUÔN có mặt,
  // kể cả rỗng) nên không cần xử lý "không tìm thấy".
  const lanesXep = useMemo(() => {
    const chuaXep = lanes.filter((l) => l.may_id === null);
    const conLai = lanes.filter((l) => l.may_id !== null);
    return [...chuaXep, ...conLai];
  }, [lanes]);

  // C138 (task-18b-brief.md) — trục thời gian RÚT ra `tdsxTimeline.ts` dùng chung với tab Gantt
  // tổng thể; công thức giữ NGUYÊN 100% (đệm 2 giờ, ngưỡng 30 giờ, hai mật độ px/giờ...), chỉ đổi
  // CHỖ Ở của code — hành vi tab này không đổi.
  const mocs = useMemo<TdsxTimelineMoc[]>(
    () =>
      lanesXep.flatMap((l) => l.blocks.map((b) => ({ batDau: b.du_kien_bat_dau, ketThuc: b.du_kien_ket_thuc }))),
    [lanesXep],
  );
  const { domain, pxPerGio, trackWidth, ticks, xOf } = useTdsxTimeline(mocs);

  // C123: popover chọn lệnh khi một khối phục vụ ≥2 lệnh. Neo bằng toạ độ của chính khối vừa bấm.
  // Dùng CHUNG với tab Theo ca (`tdsxChonLenh.tsx`) — cùng một tình huống dữ liệu, một bản code.
  const [picker, moPicker, dongPicker] = useChonLenh();

  const boCoViec = lanesXep.some((l) => l.blocks.length > 0);
  const dangLoc = Object.values(params).some((v) => v !== undefined);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  return (
    <div className="tdsx-tm" aria-label="Mini-Gantt theo máy" role="group">
      <p className="tdsx-tm__note">
        <Icon name="alert" size={13} />
        {/* Toàn bộ chữ (kể cả <b>) gói trong MỘT span để chỉ sinh ra ĐÚNG 2 flex-item (icon + span)
            — để rời như trước, mỗi đoạn chữ quanh <b> tự thành flex-item riêng, ép 3 "cột" lên
            một hàng rồi mỗi cột tự xuống dòng bên trong bề rộng hẹp của nó. */}
        <span>
          Thanh hiển thị KẾ HOẠCH của <b>cả công việc</b> đang gán trên máy — không phải khoảng máy
          này thật sự bận. Sau khi đổi máy, việc nằm trọn ở lane máy hiện tại.
        </span>
      </p>

      {daTai && (
        <div className="tdsx-lg" aria-hidden="true">
          {(Object.keys(TDSX_TT_META) as (keyof typeof TDSX_TT_META)[]).map((k) => (
            <span key={k} className={`tdsx-lg__item tdsx-lg__item--${k}`}>
              <i /> {TDSX_TT_META[k].label}
            </span>
          ))}
        </div>
      )}

      {loi && (
        <EmptyState
          icon="alert"
          title={loi.text}
          action={
            loi.cam ? undefined : (
              <Button variant="ghost" onClick={load}>
                Tải lại
              </Button>
            )
          }
        />
      )}

      {!loi && daTai && !loading && !boCoViec && (
        <div className="tdsx-tm__rong">
          {dangLoc ? (
            <EmptyState
              icon="search"
              title="Không có việc nào khớp bộ lọc."
              sub="Thử bỏ bớt điều kiện lọc ở thanh phía trên."
              action={
                <Button variant="ghost" onClick={onXoaLoc}>
                  Xóa bộ lọc
                </Button>
              }
            />
          ) : (
            <EmptyState icon="clipboard" title="Chưa có lệnh sản xuất nào đang chạy trong phạm vi của bạn." />
          )}
        </div>
      )}

      {!loi && (!daTai || boCoViec || lanesXep.length === 0) && (
        <div className="tdsx-tm__scroll" ref={scrollRef}>
          <div
            className={`tdsx-tm__grid${loading && daTai ? " is-mo" : ""}`}
            style={{ gridTemplateColumns: `${LABEL_W}px ${trackWidth}px` }}
          >
            <div className="tdsx-tm__corner" aria-hidden="true" />
            <div className="tdsx-tm__axis" style={{ width: trackWidth }}>
              {ticks.map((t) => (
                <span
                  key={t.t}
                  className={`tdsx-tm__tick${t.dam ? " is-dam" : ""}`}
                  style={{ left: ((t.t - domain.start) / 3_600_000) * pxPerGio }}
                >
                  {t.nhan}
                </span>
              ))}
            </div>

            {!daTai
              ? Array.from({ length: 3 }).map((_, i) => (
                  <FragmentSkeleton key={i} trackWidth={trackWidth} />
                ))
              : lanesXep.map((lane) => (
                  <Lane
                    key={lane.may_id ?? "chua-xep"}
                    lane={lane}
                    trackWidth={trackWidth}
                    xOf={xOf}
                    onOpenHoSo={onOpenHoSo}
                    onChon={moPicker}
                  />
                ))}
          </div>
        </div>
      )}

      {picker && (
        <ChonLenhPopover state={picker} onDong={dongPicker} onChon={onOpenHoSo} nhan="Khối" />
      )}
    </div>
  );
}

function FragmentSkeleton({ trackWidth }: { trackWidth: number }) {
  return (
    <>
      <div className="tdsx-tm__label">
        <span className="khsx-skel__bar" style={{ width: 90 }} />
      </div>
      <div className="tdsx-tm__track" style={{ width: trackWidth }}>
        <span className="khsx-skel__bar" style={{ width: 160, margin: "18px 0 0 24px" }} />
      </div>
    </>
  );
}

function Lane({
  lane,
  trackWidth,
  xOf,
  onOpenHoSo,
  onChon,
}: {
  lane: TdsxMayLane;
  trackWidth: number;
  xOf: (iso: string) => number;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const rong = lane.blocks.length === 0;
  return (
    <>
      <div className={`tdsx-tm__label${lane.ngung_dung ? " is-ngung" : ""}`}>
        {lane.ngung_dung && <Icon name="lock" size={12} />}
        <span className="tdsx-tm__labelten" title={lane.ten}>
          {lane.ten}
        </span>
        {lane.ngung_dung && <span className="tdsx-tm__labeltag">Ngừng dùng</span>}
      </div>
      <div className={`tdsx-tm__track${lane.ngung_dung ? " is-ngung" : ""}`} style={{ width: trackWidth }}>
        {rong &&
          (lane.ngung_dung ? (
            <span className="tdsx-tm__trongchu">Không có việc nào.</span>
          ) : lane.may_id === null ? (
            <span className="tdsx-tm__trongchu">Không có việc nào đang chờ xếp máy.</span>
          ) : (
            <span className="tdsx-tm__trongchu">Máy đang trống — sẵn sàng nhận việc.</span>
          ))}
        {lane.blocks.map((b) => (
          <Khoi
            key={b.cong_viec_id}
            block={b}
            ngungDung={lane.ngung_dung}
            xOf={xOf}
            onOpenHoSo={onOpenHoSo}
            onChon={onChon}
          />
        ))}
      </div>
    </>
  );
}

function Khoi({
  block,
  ngungDung,
  xOf,
  onOpenHoSo,
  onChon,
}: {
  block: TdsxMayLaneBlock;
  ngungDung: boolean;
  xOf: (iso: string) => number;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  // Cả hai mốc đều CÓ THỂ vắng (schema khai `datetime | None`) — xưởng thật gần như luôn khai đủ
  // vì Xếp lịch 2 mới gán được máy, nhưng phòng ca hiếm khai thiếu: kẹp về mép trái của khối liền
  // trước / +1 giờ, thà vẽ lệch còn hơn một khối biến mất khỏi lane không lời giải thích.
  const batDau = block.du_kien_bat_dau ?? block.du_kien_ket_thuc ?? null;
  const ketThuc = block.du_kien_ket_thuc ?? (batDau ? new Date(new Date(batDau).getTime() + 3_600_000).toISOString() : null);
  if (!batDau || !ketThuc) return null;

  const left = xOf(batDau);
  const width = Math.max(BLOCK_TOI_THIEU_PX, xOf(ketThuc) - left);
  const hep = width < BLOCK_HEP_PX;
  const ratHep = width < BLOCK_RAT_HEP_PX;
  const meta = tdsxTtMeta(block.trang_thai);
  // Nhãn của bước trên thanh HẸP: thanh Gantt không đủ bề ngang cho chip thật, nên dùng hai dấu
  // gọn (xe = thuê ngoài, cờ-lê = có khuôn) và nói đủ chữ ở `title`. Nhãn vẫn KHÔNG được biến mất
  // ở màn này — đó đúng là chỗ nó từng đứt.
  const tomTat = nhanTomTat(block.nhan);
  const nhieuLenh = block.lsx.length >= 2;
  const maChinh = block.lsx[0]?.ma ?? "—";

  function bam(e: React.MouseEvent<HTMLButtonElement>) {
    if (ngungDung || block.lsx.length === 0) return;
    if (block.lsx.length === 1) {
      onOpenHoSo(block.lsx[0].lsx_id);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    onChon(block.lsx, r.left, r.bottom + 4);
  }

  return (
    <button
      type="button"
      className={`tdsx-tm__block${ngungDung ? " tdsx-tm__block--khoa" : ` ${meta.cls}`}`}
      style={{ left, width }}
      onClick={bam}
      disabled={ngungDung}
      title={
        ngungDung
          ? `${lsxNhan(block)} — máy đã ngừng dùng, không mở được từ đây`
          : `${lsxNhan(block)} · ${meta.label}${tomTat ? ` · ${tomTat}` : ""}`
      }
    >
      {/* Vùng lõi CHỪA KHUNG cho vế thực tế (C124) — Task 17b để trống, chỉ tô phẳng qua class cha. */}
      <span className="tdsx-tm__inner">
        {!hep && (
          <span className="tdsx-tm__nhan">
            {nhieuLenh ? (
              <>
                <Icon name="layers" size={11} /> {block.lsx.length} lệnh ghép
              </>
            ) : (
              `${maChinh}${block.ten ? " · " + block.ten : ""}`
            )}
          </span>
        )}
        {hep && !ratHep && (
          <span className="tdsx-tm__nhan tdsx-tm__nhan--gon">{nhieuLenh ? block.lsx.length : maNgan(maChinh)}</span>
        )}
        {!ratHep && tomTat && (
          <span className="tdsx-tm__dau" aria-hidden="true">
            {block.nhan?.loai_buoc === "thue_ngoai" ? "🚚" : ""}
            {block.nhan?.khuon_ma ? "🔧" : ""}
          </span>
        )}
      </span>
    </button>
  );
}

function lsxNhan(block: TdsxMayLaneBlock): string {
  if (block.lsx.length === 0) return block.ten ?? "—";
  if (block.lsx.length === 1) return block.lsx[0].ma;
  return `${block.lsx.length} lệnh ghép: ${block.lsx.map((l) => l.ma).join(", ")}`;
}

// Trục thời gian (domain/lưới giờ/`xOf`) không còn định nghĩa Ở ĐÂY nữa — đã rút sang
// `./tdsxTimeline` (Ruling C138, task-18b-brief.md) để tab Gantt tổng thể dùng lại NGUYÊN công
// thức thay vì đẻ một thang thời gian thứ hai. Xem `useTdsxTimeline` import ở đầu file.
