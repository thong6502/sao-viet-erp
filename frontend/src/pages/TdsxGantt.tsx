// Tab GANTT TỔNG THỂ của màn "Theo dõi sản xuất" (Task 18b, Bước W2) — MỘT DÒNG = MỘT LỆNH (Ruling
// C118), khác Theo máy (một khối = một công việc). Bàn TRA tổng thể theo lệnh: lệnh nào đang chạy
// khoảng nào, lệnh nào chưa đủ dữ liệu để vẽ.
//
// Ruling C138 (task-18b-brief.md) — KHÔNG mount `Xl2Gantt.tsx` (18 props kéo-thả của bàn Xếp lịch,
// không hợp một tab CHỈ ĐỌC), rút trục thời gian của `TdsxTheoMay.tsx` ra `./tdsxTimeline` rồi dùng
// lại NGUYÊN ở đây — xem module đó cho lý do đầy đủ. Giá phải trả: không có 4 mức thu phóng/ruy
// băng ca/tô ngày lễ mà `Xl2Gantt` có; chấp nhận được vì đây không phải bàn xếp lịch.
//
// PHÂN TRANG Ở MÁY CHỦ (`total` đã là số SAU lọc) — cấm `rows.slice`/`rows.filter`, đổi trang phải
// gọi lại API. `du_kien_bat_dau`/`du_kien_ket_thuc` CÙNG `null` ⇒ "Chưa đủ dữ liệu", TUYỆT ĐỐI
// không tự vẽ một thanh bịa (docstring `GanttRowOut` phía máy chủ).
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import { ApiError, api } from "../api/client";
import type { TdsxGanttRow, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { Pager, trangHopLe } from "../components/Pager";
import { EmptyState, classHan, ngay, ngayGio } from "./keHoachSxShared";
import { useCotNhanW, useTdsxTimeline, type TdsxTimelineMoc } from "./tdsxTimeline";

const BAR_TOI_THIEU_PX = 24;
/** Thanh hẹp hơn mức này thì mã lệnh đứng NGOÀI mép phải thanh ("LSX26-0004" cỡ `--fs-xs` rộng ~75px,
 *  cộng đệm hai mép). Mỗi dòng chỉ có một thanh nên nhãn ngoài không bao giờ đè thanh khác. */
const BAR_HEP_PX = 96;
const PAGE_SIZE_MAC_DINH = 50;

export function TdsxGantt({
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
  const [rows, setRows] = useState<TdsxGanttRow[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_MAC_DINH);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false);
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const labelW = useCotNhanW();
  // Số thứ tự lượt gọi API còn đang bay — đổi `params` khi đang đứng trang > 1 khiến effect dưới
  // đây (deps `[active, load, refreshTick]`) và effect `setPage(1)` NGAY TRÊN chạy CÙNG một lượt
  // render nhưng theo thứ tự khai báo: `load` với `page` CŨ bắn request A trước, `setPage(1)` mới
  // chỉ lên lịch; render kế tiếp với `page=1` mới bắn request B. A/B không có gì huỷ nhau — nếu A về
  // SAU B thì đè `rows` của B bằng dữ liệu trang cũ, và `trangHopLe(page cũ, ...)` của A còn có thể
  // ném người dùng sang một trang sai. Gắn số thứ tự: chỉ lượt MỚI NHẤT được phép ghi state (vòng
  // sửa 1, mục D#2). DB soi màn hiện chỉ có `total=4` nên không demo sống được — xem báo cáo.
  const seqRef = useRef(0);

  // Đổi BẤT KỲ bộ lọc chung nào ⇒ về trang 1 — đứng trang 3 rồi gõ tìm còn 1 kết quả là bảng trống
  // trơn, người dùng tưởng mất dữ liệu (khuôn `LenhSanXuatPage`).
  useEffect(() => {
    setPage(1);
  }, [params]);

  const load = useCallback(() => {
    if (!token) return;
    const luotNay = ++seqRef.current;
    setLoading(true);
    api.theoDoiSanXuat
      .gantt(token, { ...params, page })
      .then((r) => {
        if (seqRef.current !== luotNay) return; // đã có lượt mới hơn bay sau — bỏ kết quả lượt này
        setRows(r.rows);
        setTotal(r.total);
        setPageSize(r.page_size);
        setLoi(null);
        setDaTai(true);
        // `total` co lại giữa hai lượt (SSE) — đang đứng trang 3 mà tập tụt còn 1 trang thì bảng
        // rỗng trơn, phải tự nhảy về trang hợp lệ.
        const ve = trangHopLe(page, r.total, r.page_size);
        if (ve !== null) setPage(ve);
      })
      .catch((e) => {
        if (seqRef.current !== luotNay) return;
        const cam = e instanceof ApiError && e.isForbidden;
        setLoi({
          text: cam
            ? "Bạn không có quyền xem Theo dõi sản xuất."
            : "Không tải được bảng Theo dõi sản xuất. Kiểm tra mạng rồi thử lại.",
          cam,
        });
      })
      .finally(() => {
        if (seqRef.current === luotNay) setLoading(false);
      });
  }, [token, params, page]);

  useEffect(() => {
    if (!active) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, load, refreshTick]);

  const mocs = useMemo<TdsxTimelineMoc[]>(
    () => rows.map((r) => ({ batDau: r.du_kien_bat_dau, ketThuc: r.du_kien_ket_thuc })),
    [rows],
  );
  const { domain, pxPerGio, trackWidth, ticks, monthGroups, luoiDoc, xOf, nowX, hasNowLine, dateRangeLabel } =
    useTdsxTimeline(mocs);

  const dangLoc = Object.values(params).some((v) => v !== undefined);
  const rong = daTai && !loading && total === 0;

  return (
    <div className="tdsx-gt" aria-label="Gantt tổng thể theo lệnh" role="group">
      {active &&
        khay &&
        daTai &&
        createPortal(
          <>
            <span className="tdsx__ctlnote">{dateRangeLabel}</span>
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

      {!loi && rong && (
        <div className="tdsx-gt__rong">
          {dangLoc ? (
            <EmptyState
              icon="search"
              title="Không có lệnh nào khớp bộ lọc."
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

      {!loi && (!daTai || !rong) && (
        <>
          <div className="tdsx-tm__scroll" ref={scrollRef}>
            <div
              className={`tdsx-tm__grid${loading && daTai ? " is-mo" : ""}`}
              style={
                {
                  gridTemplateColumns: `${labelW}px ${trackWidth}px`,
                  "--tdsx-cot-nhan-w": `${labelW}px`,
                  ...luoiDoc,
                } as CSSProperties
              }
            >
              {/* Trục HAI tầng (tháng / ngày-giờ) giống hệt Theo máy — bản một tầng cũ chỉ còn lại
                  vài chữ ngày lẻ loi giữa một dải đầu bảng cao 44px, ô góc thì trống trơn. */}
              <div
                className="tdsx-tm__corner"
                title="Mỗi dòng là một lệnh. Thanh chạy từ giờ bắt đầu dự kiến của công đoạn sớm nhất tới giờ kết thúc dự kiến của công đoạn muộn nhất; vạch đứt là hạn hoàn thành."
              >
                <span className="tdsx-tm__corner-head">Lệnh</span>
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
                ? Array.from({ length: 4 }).map((_, i) => <GanttSkeletonRow key={i} trackWidth={trackWidth} />)
                : rows.map((r, i) => (
                    <GanttRow
                      key={r.lsx_id}
                      row={r}
                      soc={i % 2 === 1}
                      xOf={xOf}
                      trackWidth={trackWidth}
                      onOpen={() => onOpenHoSo(r.lsx_id)}
                    />
                  ))}
            </div>
          </div>
          <Pager total={total} page={page} size={pageSize} onPage={setPage} loading={loading} unit="lệnh" />
        </>
      )}
    </div>
  );
}

/** "26/8 18:04 → 22:53" — bỏ ngày ở vế phải khi hai mốc CÙNG ngày (đa số việc trong xưởng gọn
 *  trong một ngày, lặp lại ngày chỉ tốn chỗ ở cột nhãn 240px, xuống 120px ở màn hẹp). Thiếu mốc
 *  thì nói thẳng, không bịa khoảng — cùng giao kèo với `GanttRowOut` phía máy chủ. */
function nhanKhoang(batDau: string | null, ketThuc: string | null): string {
  if (!batDau || !ketThuc) return "Chưa có mốc dự kiến";
  const a = new Date(batDau);
  const b = new Date(ketThuc);
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return "Chưa có mốc dự kiến";
  const gio = (d: Date) => d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  const nd = (d: Date) => `${d.getDate()}/${d.getMonth() + 1}`;
  const cungNgay = a.toDateString() === b.toDateString();
  return cungNgay ? `${nd(a)} ${gio(a)} → ${gio(b)}` : `${nd(a)} ${gio(a)} → ${nd(b)} ${gio(b)}`;
}

function GanttSkeletonRow({ trackWidth }: { trackWidth: number }) {
  return (
    <>
      <div className="tdsx-gt__label">
        <span className="khsx-skel__bar" style={{ width: 100 }} />
      </div>
      <div className="tdsx-gt__track" style={{ width: trackWidth }}>
        <span className="khsx-skel__bar tdsx-gt__skelbar" style={{ width: 160 }} />
      </div>
    </>
  );
}

function GanttRow({
  row,
  soc,
  xOf,
  trackWidth,
  onOpen,
}: {
  row: TdsxGanttRow;
  /** Dòng ở vị trí LẺ — vằn ngựa vằn, xem `.tdsx-gt__label.is-soc`. */
  soc: boolean;
  xOf: (iso: string) => number;
  trackWidth: number;
  onOpen: () => void;
}) {
  const quaHan = row.han_hoan_thanh_sx != null && classHan(row.han_hoan_thanh_sx) === "khsx-date--late";
  const thieuMoc = !row.du_kien_bat_dau || !row.du_kien_ket_thuc;
  let left = 0;
  let width = 0;
  if (!thieuMoc) {
    left = xOf(row.du_kien_bat_dau as string);
    width = Math.max(BAR_TOI_THIEU_PX, xOf(row.du_kien_ket_thuc as string) - left);
  }
  // Hạn giao cũng là một MỐC THỜI GIAN, nên vẽ nó lên chính trục thời gian — đứng cạnh thanh kế
  // hoạch thì thấy ngay lệnh chạy xong trước hay sau hạn, việc mà một dòng chữ ở cột nhãn không
  // nói được. `han_hoan_thanh_sx` là DATE; "hạn hoàn thành ngày X" nghĩa là phải xong TRONG ngày X
  // nên mốc đặt ở CUỐI ngày, không phải 00:00 — lấy 00:00 thì một lệnh xong lúc 08:21 ngày X lại
  // hiện ra bên phải vạch hạn, tức vẽ ngược hẳn sự thật. `xOf` KHÔNG kẹp biên: hạn rơi ngoài miền
  // trục thì bỏ vạch, thà thiếu còn hơn vẽ một vạch ở toạ độ âm (nhãn vẫn còn chip "Quá hạn").
  let hanX: number | null = null;
  if (row.han_hoan_thanh_sx) {
    const x = xOf(`${row.han_hoan_thanh_sx}T23:59:59`);
    if (x >= 0 && x <= trackWidth) hanX = x;
  }

  return (
    <>
      <button
        type="button"
        className={`tdsx-gt__label${soc ? " is-soc" : ""}`}
        onClick={onOpen}
        title={`${row.ma}${row.ten ? " · " + row.ten : ""}`}
      >
        <span className="tdsx-gt__row1">
          <span className="tdsx-gt__ma">{row.ma}</span>
          {quaHan && (
            <span className="tdsx-gt__quahan">
              <Icon name="alert" size={11} />
              Quá hạn {ngay(row.han_hoan_thanh_sx)}
            </span>
          )}
        </span>
        <span className="tdsx-gt__meta">
          {row.khach_hang ?? "—"} · {row.ten ?? "—"}
        </span>
        {/* Khoảng kế hoạch viết THÀNH CHỮ ngay ở cột nhãn, không chỉ nằm trong thanh: miền thời
         * gian của bàn này thường vắt nhiều ngày (pxPerGio tụt còn 14 khi span > 30 giờ) nên phần
         * lớn thanh nằm NGOÀI khung nhìn — đo thật 4 lệnh ở 1440px thì 3 thanh đứng tại x 1794 và
         * 2384, người dùng chỉ thấy ba dòng trống trơn và tưởng lệnh chưa có lịch. Có dòng này thì
         * dù thanh ở đâu, dòng vẫn tự nói nó chạy lúc nào. Hạn nhập chung dòng này khi CHƯA trễ —
         * trễ rồi thì nó lên dòng đầu thành chip đỏ. */}
        <span className="tdsx-gt__kehoach">
          {nhanKhoang(row.du_kien_bat_dau, row.du_kien_ket_thuc)}
          {row.han_hoan_thanh_sx && !quaHan ? ` · hạn ${ngay(row.han_hoan_thanh_sx)}` : ""}
        </span>
      </button>
      <div className={`tdsx-gt__track${soc ? " is-soc" : ""}`}>
        {hanX !== null && (
          <span
            className="tdsx-gt__hanmoc"
            style={{ left: hanX }}
            title={`Hạn hoàn thành ${ngay(row.han_hoan_thanh_sx)}`}
            aria-hidden="true"
          />
        )}
        {thieuMoc ? (
          <span className="tdsx-gt__thieumoc">Chưa đủ dữ liệu</span>
        ) : (
          <button
            type="button"
            className={`tdsx-gt__bar${quaHan ? " tdsx-gt__bar--quahan" : ""}`}
            style={{ left, width }}
            onClick={onOpen}
            title={`${row.ma} · ${ngayGio(row.du_kien_bat_dau)} → ${ngayGio(row.du_kien_ket_thuc)}`}
            aria-label={`Mở hồ sơ lệnh ${row.ma}`}
          >
            {/* Thanh trơn không chữ trông như khung chờ tải. Mã lệnh nằm trong lòng thanh khi đủ
                rộng, không thì đứng ngoài mép phải — không bao giờ cắt cụt. */}
            <span className={`tdsx-gt__barma${width < BAR_HEP_PX ? " tdsx-gt__barma--ngoai" : ""}`} aria-hidden="true">
              {row.ma}
            </span>
          </button>
        )}
      </div>
    </>
  );
}
