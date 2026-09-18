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
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import { ApiError, api } from "../api/client";
import type { TdsxLsxThamChieu, TdsxMayLane, TdsxMayLaneBlock, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { nhanTomTat } from "../components/ChipBuoc";
import { Icon } from "../components/Icons";
import { EmptyState } from "./keHoachSxShared";
import { TDSX_TT_META, tdsxTtMeta } from "./TdsxKanban";
import { ChonLenhPopover, useChonLenh } from "./tdsxChonLenh";
import { useCotNhanW, useTdsxTimeline, NGUONG_DAI_GIO, type TdsxTimelineMoc } from "./tdsxTimeline";

/** Block hẹp hơn mức này (px) thì rút nhãn chỉ còn mã lệnh — đúng cách `Xl2Gantt` rút gọn theo
 *  `isWide`/`isMedium`, không đẻ quy ước mới. */
const BLOCK_HEP_PX = 90;
/** Dưới mức này thì trong lòng thanh không còn chỗ cho cả dấu gọn (🚚 / 🔧) — nhãn đã ra ngoài
 *  từ mốc `BLOCK_HEP_PX` rồi, mốc này chỉ còn quyết định hai cái dấu đó. */
const BLOCK_RAT_HEP_PX = 44;
const BLOCK_TOI_THIEU_PX = 20;

export function TdsxTheoMay({
  active,
  token,
  params,
  refreshTick,
  onOpenHoSo,
  onXoaLoc,
  khay,
}: {
  active: boolean;
  token: string | null;
  params: TdsxThanhLocParams;
  refreshTick: number;
  onOpenHoSo: (lsxId: number) => void;
  onXoaLoc: () => void;
  /** Khay điều khiển trên dải tab — xem ghi chú cùng tên ở `TdsxKanban`. */
  khay: HTMLElement | null;
}) {
  const [lanes, setLanes] = useState<TdsxMayLane[]>([]);
  /** Máy KHÔNG có việc nào mặc định gập lại. Đo thật: 37/43 lane trống, mỗi lane cao 56px ⇒ 2072px
   *  cuộn dọc toàn dòng rỗng, việc thật nằm lẫn đâu đó giữa. Bảng kế hoạch là để thấy chỗ tắc và
   *  chỗ còn chỗ nhét việc, không phải để liệt kê tài sản. */
  const [hienTrong, setHienTrong] = useState(false);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false);
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
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

  // Ba nhóm, theo mức cần nhìn tới: (1) rổ "Chưa xếp máy" — việc điều độ phải xử (C129 giữ nguyên
  // ở đầu); (2) máy CÓ việc, trong đó máy đang CHẠY lên trước máy chỉ có việc chờ/tạm dừng; (3) máy
  // trống, gập lại. Trong mỗi nhóm giữ NGUYÊN thứ tự máy chủ trả (thứ tự danh mục máy) — lane chỉ
  // đổi chỗ khi máy đó thật sự bắt đầu/kết thúc việc, không nhảy lung tung mỗi lượt vẽ.
  const { lanesHien, soTrong } = useMemo(() => {
    const chuaXep = lanes.filter((l) => l.may_id === null);
    const may = lanes.filter((l) => l.may_id !== null);
    const coViec = may.filter((l) => l.blocks.length > 0);
    const dangChay = coViec.filter((l) => l.blocks.some((b) => b.trang_thai === "running"));
    const coViecKhac = coViec.filter((l) => !l.blocks.some((b) => b.trang_thai === "running"));
    const trong = may.filter((l) => l.blocks.length === 0);
    return {
      lanesHien: [...chuaXep, ...dangChay, ...coViecKhac, ...(hienTrong ? trong : [])],
      soTrong: trong.length,
    };
  }, [lanes, hienTrong]);
  // Trục thời gian phải tính trên MỌI lane, kể cả lane đang gập — không thì bấm "hiện" một cái là
  // cả miền thời gian nhảy.
  const lanesXep = lanes;

  const mocs = useMemo<TdsxTimelineMoc[]>(
    () =>
      lanesXep.flatMap((l) => l.blocks.map((b) => ({ batDau: b.du_kien_bat_dau, ketThuc: b.du_kien_ket_thuc }))),
    [lanesXep],
  );
  const { domain, spanGio, pxPerGio, trackWidth, ticks, monthGroups, luoiDoc, xOf, nowX, hasNowLine, dateRangeLabel } =
    useTdsxTimeline(mocs);

  const [picker, moPicker, dongPicker] = useChonLenh();
  /** Cột tên máy (sticky trái): 240px, co về 120px ở màn ≤480px — cùng một hook với tab Gantt. */
  const labelW = useCotNhanW();

  const boCoViec = lanesXep.some((l) => l.blocks.length > 0);
  const dangLoc = Object.values(params).some((v) => v !== undefined);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  return (
    <div className="tdsx-tm" aria-label="Mini-Gantt theo máy" role="group">
      {/* Thanh điều khiển lên dải tab. Hai chip đã bỏ: "Lưu ý kế hoạch" (câu giải thích dài, nay là
          `title` của chính ô góc bảng — chỗ nó nói về) và "Thu phóng: Giờ/Ngày" (suy được từ nhãn
          trục ngay bên dưới, nay là `title` của dải ngày). */}
      {active &&
        khay &&
        createPortal(
          <>
            {daTai && (
              <span className="tdsx-lg" aria-hidden="true">
                {(Object.keys(TDSX_TT_META) as (keyof typeof TDSX_TT_META)[]).map((k) => (
                  <span key={k} className={`tdsx-lg__item tdsx-lg__item--${k}`}>
                    <i /> {TDSX_TT_META[k].label}
                  </span>
                ))}
              </span>
            )}
            <span
              className="tdsx__ctlnote"
              title={spanGio <= NGUONG_DAI_GIO ? "Lưới trục chia theo giờ" : "Lưới trục chia theo ngày"}
            >
              {dateRangeLabel}
            </span>
            {hasNowLine && (
              <button
                type="button"
                className="hslsx__linkbtn"
                onClick={() => scrollRef.current?.scrollTo({ left: Math.max(0, nowX - 250), behavior: "smooth" })}
                title="Cuộn tới vạch thời gian hiện tại"
              >
                Đến hôm nay
              </button>
            )}
          </>,
          khay,
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
            style={{ gridTemplateColumns: `${labelW}px ${trackWidth}px`, "--tdsx-cot-nhan-w": `${labelW}px`, ...luoiDoc } as CSSProperties}
          >
            <div
              className="tdsx-tm__corner"
              title="Thanh vẽ KẾ HOẠCH của công việc đang gán trên máy — không phải khoảng máy này thật sự bận. Sau khi đổi máy, việc nằm trọn ở lane máy hiện tại."
            >
              <span className="tdsx-tm__corner-head">Máy</span>
            </div>
            <div className="tdsx-tm__axis" style={{ width: trackWidth }}>
              <div className="tdsx-tm__axis-top">
                {monthGroups.map((g, i) => (
                  <span key={i} className="tdsx-tm__month-bar" style={{ left: g.left, width: g.width }}>
                    <span className="tdsx-tm__month-chu">{g.label}</span>
                  </span>
                ))}
              </div>
              <div className="tdsx-tm__axis-bot">
                {ticks.map((t) => (
                  <span
                    key={t.t}
                    className={`tdsx-tm__tick${t.dam ? " is-dam" : ""}${t.isToday ? " is-today" : ""}`}
                    style={{ left: ((t.t - domain.start) / 3_600_000) * pxPerGio }}
                  >
                    {t.nhan}
                  </span>
                ))}
              </div>
            </div>

            {hasNowLine && (
              <div className="tdsx-tm__now-line" style={{ left: labelW + nowX }} title="Thời gian hiện tại">
                <span className="tdsx-tm__now-badge">bây giờ</span>
              </div>
            )}

            {!daTai
              ? Array.from({ length: 3 }).map((_, i) => (
                  <FragmentSkeleton key={i} trackWidth={trackWidth} />
                ))
              : lanesHien.map((lane, i) => (
                  <Lane
                    key={lane.may_id ?? "chua-xep"}
                    lane={lane}
                    soc={i % 2 === 1}
                    trackWidth={trackWidth}
                    xOf={xOf}
                    onOpenHoSo={onOpenHoSo}
                    onChon={moPicker}
                  />
                ))}

            {daTai && soTrong > 0 && (
              <div className="tdsx-tm__foldrow">
                <button type="button" className="tdsx-tm__fold" onClick={() => setHienTrong((v) => !v)}>
                  <Icon name="chevron" size={12} />
                  {hienTrong ? `Ẩn ${soTrong} máy đang trống` : `${soTrong} máy đang trống`}
                </button>
              </div>
            )}
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
  soc,
  trackWidth,
  xOf,
  onOpenHoSo,
  onChon,
}: {
  lane: TdsxMayLane;
  /** Lane ở vị trí LẺ — tô vằn để mắt lần được từ tên máy ở mép trái sang thanh việc cách đó cả
   *  nghìn pixel. 43 lane trắng bong xếp chồng nhau chính là thứ làm tab này trông như tờ giấy. */
  soc: boolean;
  trackWidth: number;
  xOf: (iso: string) => number;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const rong = lane.blocks.length === 0;
  const isChuaXep = lane.may_id === null;

  // Nhãn đứng ngoài của thanh hẹp chiếm khoảng trống TỚI thanh kế bên. Lane dày (việc nối đuôi
  // nhau, mỗi việc vài giờ trên thang 14px/giờ) thì thanh kế bên vẽ SAU nên che mất nửa mã, còn trơ
  // "LSX26-00" — đúng khuôn lỗi ⓓ. Đo thật sau khi vẽ: nhãn nào lấn sang một thanh khác thì ẩn hẳn
  // (mã vẫn ở `title`, bấm vẫn mở đúng lệnh). Ẩn bằng `visibility` để lượt đo sau vẫn lấy được bề
  // rộng chữ; đo lại khi phông tải xong vì chữ phông dự phòng hẹp hơn.
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [nhanBiChe, setNhanBiChe] = useState<ReadonlySet<number>>(() => new Set());
  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const doLai = () => {
      const khoi = Array.from(track.children)
        .filter((el): el is HTMLElement => el instanceof HTMLElement && el.classList.contains("tdsx-tm__block"))
        .map((el) => ({
          id: Number(el.dataset.cv),
          r: el.getBoundingClientRect(),
          nhan: el.querySelector(".tdsx-tm__nhan--ngoai")?.getBoundingClientRect() ?? null,
        }));
      const che = new Set<number>();
      for (const k of khoi) {
        const nhan = k.nhan;
        if (nhan && khoi.some((o) => o !== k && o.r.left < nhan.right && o.r.right > nhan.left)) che.add(k.id);
      }
      setNhanBiChe((cu) => (cu.size === che.size && [...che].every((id) => cu.has(id)) ? cu : che));
    };
    doLai();
    let conSong = true;
    document.fonts?.ready.then(() => {
      if (conSong) doLai();
    });
    return () => {
      conSong = false;
    };
  }, [lane.blocks, xOf]);

  return (
    <>
      <div
        className={`tdsx-tm__label${soc ? " is-soc" : ""}${lane.ngung_dung ? " is-ngung" : ""}${isChuaXep ? " is-chua-xep" : ""}`}
      >
        {isChuaXep ? (
          <span className="tdsx-tm__unassigned-tag">Chưa xếp máy</span>
        ) : (
          <>
            <span className="tdsx-tm__labelten" title={lane.ten}>
              {lane.ten}
            </span>
            {lane.ngung_dung && <span className="tdsx-tm__labeltag">Ngừng dùng</span>}
          </>
        )}
      </div>
      <div
        className={`tdsx-tm__track${soc ? " is-soc" : ""}${lane.ngung_dung ? " is-ngung" : ""}${isChuaXep ? " is-chua-xep" : ""}`}
        style={{ width: trackWidth }}
        ref={trackRef}
      >
        {rong &&
          (lane.ngung_dung ? (
            <span className="tdsx-tm__trongchu">Máy đã ngừng dùng</span>
          ) : isChuaXep ? (
            <span className="tdsx-tm__trongchu">Không có việc nào đang chờ xếp máy</span>
          ) : (
            // Chữ xám nhạt, không huy hiệu. Trước đây mỗi lane trống đeo một viên xanh lá "Máy đang
            // trống — sẵn sàng nhận việc": đo thật 37 viên trên một màn có đúng 2 việc thật.
            <span className="tdsx-tm__trongchu">Trống</span>
          ))}
        {lane.blocks.map((b) => (
          <Khoi
            key={b.cong_viec_id}
            block={b}
            ngungDung={lane.ngung_dung}
            nhanBiChe={nhanBiChe.has(b.cong_viec_id)}
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
  nhanBiChe,
  xOf,
  onOpenHoSo,
  onChon,
}: {
  block: TdsxMayLaneBlock;
  ngungDung: boolean;
  /** Nhãn đứng ngoài sẽ lấn lên một thanh khác — `Lane` đo rồi báo xuống. */
  nhanBiChe: boolean;
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
      className={
        `tdsx-tm__block${ngungDung ? " tdsx-tm__block--khoa" : ` ${meta.cls}`}` +
        (hep ? " tdsx-tm__block--nhanngoai" : "")
      }
      style={{ left, width }}
      data-cv={block.cong_viec_id}
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
        {!ratHep && tomTat && (
          <span className="tdsx-tm__dau" aria-hidden="true">
            {block.nhan?.loai_buoc === "thue_ngoai" ? "🚚" : ""}
            {block.nhan?.khuon_ma ? "🔧" : ""}
          </span>
        )}
      </span>
      {/* Việc 20 phút trên thang 4 ngày chỉ được 20px — không chữ nào lọt vào trong. Trước đây
          nhánh hẹp bỏ nhãn luôn (thành hộp rỗng), rồi đến lượt bản vá đầu ghi mã cụt "0004". Nhãn
          nay đứng NGOÀI mép phải thanh nên hết giới hạn bề ngang: ghi thẳng MÃ ĐẦY ĐỦ.
          `pointer-events: none` để chữ không cướp cú bấm của thanh kế bên. */}
      {hep && (
        <span className={`tdsx-tm__nhan tdsx-tm__nhan--ngoai${nhanBiChe ? " is-che" : ""}`}>
          {nhieuLenh ? `${block.lsx.length} lệnh ghép` : maChinh}
        </span>
      )}
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
