// Tab KANBAN của màn "Theo dõi sản xuất" (Task 17b, Bước 3).
//
// MỘT LỆNH = MỘT CARD, kể cả routing rẽ nhiều nhánh (Ruling C113/thiết kế §0, đã được chủ dự án
// đọc và duyệt). Các nhánh đang chạy/tạm dừng cùng lúc hiện thành DANH SÁCH chip `chip_dang_chay`
// bên TRONG card đó — KHÔNG tách thành nhiều card. Card neo cứng `lsx_id` nên bấm card luôn mở
// thẳng hồ sơ, không có tình huống phải chọn (khác hẳn khối của tab Theo máy).
//
// Khung cột dựng từ `/meta` (`cot: [{key, ten}]`), KHÔNG dựng từ dữ liệu card — cột "khac" do máy
// chủ trả CUỐI danh sách sẵn (`bang_theo_doi.meta`), không cần sắp lại ở đây.
//
// `/kanban` KHÔNG còn gọi ở đây: dải bốn con số trên đầu màn cần đúng bức ảnh đó kể cả khi người
// dùng đang đứng ở tab khác, nên `TheoDoiSanXuatPage` giữ lượt gọi và truyền `cards`/`dangTai`/`loi`
// xuống. `/meta` vẫn ở lại (danh mục công đoạn, không phụ thuộc bộ lọc) và được gọi lại mỗi khi
// `cards` đổi — giữ đúng tinh thần Ruling C125 là cột và card cùng một nhịp, chỉ khác là hai
// request nối nhau thay vì một `Promise.all`.
//
// LỌC Ở MÁY CHỦ: `params` do `TheoDoiSanXuatPage` dựng một chỗ rồi truyền xuống, component này
// không tự lọc/cắt gì trên mảng `cards` nhận về.
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../api/client";
import type { TdsxKanbanCard, TdsxKanbanMeta, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { ChipKhuon, ChipLoaiBuoc, nhanKhuon } from "../components/ChipBuoc";
import { Icon, type IconName } from "../components/Icons";
import { EmptyState, classHan, ngay, num } from "./keHoachSxShared";

/** Bốn trạng thái CÔNG VIỆC (`models/san_xuat.py`) — dùng CHUNG cho chip Kanban (chỉ bao giờ
 *  `running`/`paused`, xem docstring `KanbanChipOut`) và khối Theo máy (đủ cả bốn). Định nghĩa MỘT
 *  chỗ ở đây rồi `TdsxTheoMay.tsx` import lại, tránh hai nơi tự gõ tay bốn nhãn và lệch nhau về
 *  sau. Bảng màu đúng thiết kế §6, đã chạy thật ở `.thsx-lg` của Thực hiện SX — nhãn/màu tái dùng
 *  NGUYÊN, chỉ đổi tên class (`.tdsx-*`) để màn này không phải kéo theo cả `thuc-hien-sx.css`.
 */
export type TdsxTrangThaiViec = "released" | "running" | "paused" | "completed";
export const TDSX_TT_META: Record<TdsxTrangThaiViec, { label: string; icon: IconName; cls: string }> = {
  released: { label: "Chờ làm", icon: "clock", cls: "tdsx-tt--released" },
  running: { label: "Đang chạy", icon: "play", cls: "tdsx-tt--running" },
  paused: { label: "Tạm dừng", icon: "pause", cls: "tdsx-tt--paused" },
  completed: { label: "Hoàn thành", icon: "check", cls: "tdsx-tt--completed" },
};
export function tdsxTtMeta(tt: string) {
  return TDSX_TT_META[tt as TdsxTrangThaiViec] ?? TDSX_TT_META.released;
}

/** Quá 3 chip mới rút gọn (thiết kế §4 mục 5): "quá 3" = TỪ 4 trở lên. */
const CHIP_HIEN_TOI_DA = 3;
const CHIP_RUT_GON_CON_LAI = 2;

export function TdsxKanban({
  active,
  token,
  params,
  cards,
  dangTai,
  loi,
  onTaiLai,
  onOpenHoSo,
  onXoaLoc,
  khay,
}: {
  /** Tab Kanban đang được xem hay không — `false` thì component vẫn ở trong DOM (`hidden`, giữ vị
   *  trí cuộn của nó) nhưng KHÔNG tự gọi lại API khi bộ lọc đổi ở nền; bù lại, hễ chuyển sang active
   *  là một lượt tải MỚI chạy ngay để không bao giờ hiện dữ liệu cũ hơn bộ lọc hiện tại. */
  active: boolean;
  token: string | null;
  params: TdsxThanhLocParams;
  /** Card của lượt `/kanban` do trang cha giữ (xem chú thích đầu file). Mảng đổi tham chiếu là một
   *  tín hiệu "vừa có dữ liệu mới" — `/meta` bám theo đó để nạp lại. */
  cards: TdsxKanbanCard[];
  /** Lượt `/kanban` đang bay. Lượt ĐẦU thì dựng skeleton, lượt sau chỉ làm mờ board. */
  dangTai: boolean;
  /** Lỗi của lượt `/kanban` (403 hay mạng) — hiển thị y như trước, chỉ khác là do cha truyền xuống. */
  loi: { text: string; cam: boolean } | null;
  /** Gọi lại `/kanban` — lượt gọi nằm ở trang cha nên nút "Tải lại" trong băng lỗi phải nhờ cha
   *  bấm hộ (đúng cái nút "Làm mới" trên đầu màn đang dùng). */
  onTaiLai: () => void;
  /** Mở lớp phủ hồ sơ đúng lệnh — bấm bất kỳ đâu trên card. */
  onOpenHoSo: (lsxId: number) => void;
  /** Xóa toàn bộ bộ lọc — dùng cho nút trong khối rỗng "Không có việc nào khớp bộ lọc." (thiết kế
   *  §7 tình huống b), để người dùng không phải cuộn lên thanh lọc chung. */
  onXoaLoc: () => void;
  /** Khay điều khiển trên dải tab (do `TheoDoiSanXuatPage` dựng). Tab đang mở đẩy nút "ẩn/hiện
   *  cột trống" của nó lên đó bằng `createPortal` — state ở lại đây, chỗ đứng thì lên cùng hàng
   *  với dải tab thay vì chiếm một tầng ngang riêng. */
  khay: HTMLElement | null;
}) {
  const [meta, setMeta] = useState<TdsxKanbanMeta | null>(null);
  const [daTai, setDaTai] = useState(false);
  /** Mặc định ẨN cột chưa có việc. `/meta` trả NGUYÊN danh mục công đoạn (đo thật: 24 cột, 22 cột
   *  rỗng ⇒ board rộng 6756px, phải kéo ngang 5608px mới hết) nên để nguyên thì việc thật bị chôn
   *  giữa một rừng cột trống. Ẩn để đọc được, nhưng luôn nói RÕ đang ẩn mấy cột kèm nút mở lại —
   *  không cột nào biến mất im lặng. */
  const [hienCotRong, setHienCotRong] = useState(false);

  // `/meta` chỉ nạp khi tab này ĐANG mở — ba tab kia không dùng danh mục cột nên không việc gì
  // phải trả tiền cho nó. Bám `cards` để cột và card luôn cùng một nhịp; lỗi `/meta` KHÔNG dựng
  // băng đỏ (băng đỏ là việc của `loi`), mất cột thì `SKELETON_COT` đỡ và board vẫn đọc được.
  useEffect(() => {
    if (!active || !token) return;
    let song = true;
    api.theoDoiSanXuat
      .meta(token)
      .then((m) => {
        if (song) setMeta(m);
      })
      .catch(() => {});
    return () => {
      song = false;
    };
  }, [active, token, cards]);

  // `daTai` DÍNH: một khi đã thấy dữ liệu thật thì những lượt tải sau chỉ làm mờ board, không hạ
  // nó về skeleton và không bung lại 22 cột rỗng dưới chân người đang đọc.
  useEffect(() => {
    if (meta && !dangTai && !loi) setDaTai(true);
  }, [meta, dangTai, loi]);

  // "Đang lọc" suy từ chính object `params` (do trang cha dựng) — không giữ một bản cờ riêng ở
  // đây dễ lệch với logic "Xóa bộ lọc" của thanh lọc chung.
  const dangLoc = Object.values(params).some((v) => v !== undefined);
  const tongTheLoc = cards.length;

  // Gom card về cột MỘT lần (trước đây mỗi cột tự `cards.filter` — 24 cột × N card mỗi lượt vẽ).
  const theoCot = useMemo(() => {
    const m = new Map<string, TdsxKanbanCard[]>();
    for (const c of cards) {
      const ds = m.get(c.cot);
      if (ds) ds.push(c);
      else m.set(c.cot, [c]);
    }
    return m;
  }, [cards]);
  const cotTatCa = meta?.cot ?? SKELETON_COT;
  // Chỉ lọc khi ĐÃ có dữ liệu: lượt đầu (`!daTai`) mọi cột đều đếm 0, lọc lúc đó thì khung skeleton
  // trắng bong.
  const soCotRong = daTai ? cotTatCa.filter((c) => !theoCot.has(c.key)).length : 0;
  const cotHien = daTai && !hienCotRong ? cotTatCa.filter((c) => theoCot.has(c.key)) : cotTatCa;

  return (
    <div className="tdsx-kb" aria-label="Bảng Kanban theo công đoạn" role="group">
      {loi && (
        <div className={`tdsx-kb__loi${cards.length > 0 ? "" : " tdsx-kb__loi--full"}`}>
          <EmptyState
            icon="alert"
            title={loi.text}
            action={
              loi.cam ? undefined : (
                <Button variant="ghost" onClick={onTaiLai}>
                  Tải lại
                </Button>
              )
            }
          />
        </div>
      )}

      {!loi && daTai && !dangTai && meta && meta.cot.length > 0 && tongTheLoc === 0 && (
        <div className="tdsx-kb__loi tdsx-kb__loi--full">
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
            <EmptyState
              icon="clipboard"
              title="Chưa có lệnh sản xuất nào đang chạy trong phạm vi của bạn."
            />
          )}
        </div>
      )}

      {active &&
        khay &&
        (!daTai || tongTheLoc > 0 || !meta || meta.cot.length === 0) &&
        !loi &&
        soCotRong > 0 &&
        createPortal(
          <>
            <span className="tdsx__ctlnote">
              {num(cotTatCa.length - soCotRong)}/{num(cotTatCa.length)} công đoạn có việc
            </span>
            <button type="button" className="hslsx__linkbtn" onClick={() => setHienCotRong((v) => !v)}>
              {hienCotRong ? `Ẩn ${soCotRong} công đoạn trống` : `Hiện ${soCotRong} công đoạn trống`}
            </button>
          </>,
          khay,
        )}

      {(!daTai || tongTheLoc > 0 || !meta || meta.cot.length === 0) && !loi && (
        <div className={`tdsx-kb__board${dangTai && daTai ? " is-mo" : ""}`}>
          {cotHien.map((cot) => {
            const trongCot = theoCot.get(cot.key) ?? [];
            const isZero = trongCot.length === 0;
            return (
              <section key={cot.key} className={`tdsx-kb__col${isZero ? " is-empty" : ""}`} aria-label={`Công đoạn ${cot.ten}`}>
                <header className="tdsx-kb__colhead">
                  <span className="tdsx-kb__colten">{cot.ten}</span>
                  {daTai && (
                    <span className={`tdsx-kb__coln ${isZero ? "tdsx-kb__coln--zero" : "tdsx-kb__coln--active"}`}>
                      {num(trongCot.length)}
                    </span>
                  )}
                </header>
                <div className="tdsx-kb__body">
                  {!daTai ? (
                    <>
                      <span className="khsx-skel__bar khsx-skel__bar--card" />
                      <span className="khsx-skel__bar khsx-skel__bar--card" />
                    </>
                  ) : isZero ? (
                    // Cột rỗng nói MỘT câu, bằng chữ xám nhạt. Trước đây nó là một khối viền đứt
                    // + icon tròn xanh + tiêu đề + huy hiệu "Sẵn sàng nhận việc": bốn phần tử,
                    // màu sáng nhất bảng, cho thứ KHÔNG có gì để xem. Màu để dành cho việc đang
                    // chạy và việc trễ.
                    <p className="tdsx-kb__trong">Không có việc</p>
                  ) : (
                    trongCot.map((card) => (
                      <TheCard
                        key={card.lsx_id}
                        card={card}
                        cotTen={cot.ten}
                        onOpen={() => onOpenHoSo(card.lsx_id)}
                      />
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Ba cột giả để vẽ khung + skeleton ngay LƯỢT ĐẦU, trước khi `/meta` kịp về (khuôn "khung hiện
 *  ngay, không đợi dữ liệu con" — thiết kế §7). Nhãn không quan trọng vì bị skeleton che ngay. */
const SKELETON_COT: TdsxKanbanMeta["cot"] = [
  { key: "s1", ten: "…" },
  { key: "s2", ten: "…" },
  { key: "s3", ten: "…" },
];

/** Một thẻ = một lệnh. Ba dòng chữ, không viên bọc quanh từng mẩu:
 *  ① mã lệnh (cam đậm — đây là thứ người xưởng đọc trước) + dấu Gấp + chip "Quá hạn" nếu trễ;
 *  ② tên sản phẩm, tối đa 2 dòng;
 *  ③ khách · số lượng · hạn — chữ nhỏ, một dòng, không icon;
 *  ④ chip nhánh đang chạy (giữ nguyên).
 *  Bản cũ bọc mã trong hộp xám, số lượng trong một viên có icon + chữ "sp", khách hàng có icon
 *  người, hạn trong một viên nữa, cộng một viên "bước hiện tại" thường LẶP LẠI đúng tên cột đang
 *  đứng — năm cái viền cho bốn mẩu chữ. */
function TheCard({ card, cotTen, onOpen }: { card: TdsxKanbanCard; cotTen: string; onOpen: () => void }) {
  const qua_han = card.han_hoan_thanh_sx != null && classHan(card.han_hoan_thanh_sx) === "khsx-date--late";
  const chips = card.chip_dang_chay;
  const chipHien = chips.length > CHIP_HIEN_TOI_DA ? chips.slice(0, CHIP_RUT_GON_CON_LAI) : chips;
  const chipConLai = chips.length - chipHien.length;
  // Bước hiện tại chỉ in ra khi nó KHÁC tên cột — đứng trong cột "Bế" mà thẻ còn đeo nhãn "Bế" là
  // nói hai lần. Cột gom "Khác" thì tên bước mới thật sự thêm thông tin.
  const buocKhacCot = card.buoc_hien_tai && card.buoc_hien_tai !== cotTen ? card.buoc_hien_tai : null;

  const phu = [
    card.khach_hang,
    `${num(card.so_luong_dat)} sp`,
    card.han_hoan_thanh_sx && !qua_han ? `hạn ${ngay(card.han_hoan_thanh_sx)}` : null,
    buocKhacCot,
  ].filter(Boolean) as string[];

  return (
    <button type="button" className="tdsx-kb__card" onClick={onOpen}>
      <span className="tdsx-kb__c1">
        <span className="tdsx-kb__ma">{card.ma}</span>
        {card.is_rush && <span className="tdsx-kb__gap">Gấp</span>}
        {qua_han && (
          <span className="tdsx-kb__quahan">
            <Icon name="alert" size={11} />
            Quá hạn {ngay(card.han_hoan_thanh_sx)}
          </span>
        )}
      </span>

      <span className="tdsx-kb__ten" title={card.ten ?? undefined}>
        {card.ten ?? "Chưa có tên sản phẩm"}
      </span>

      <span className="tdsx-kb__phu" title={card.khach_hang ?? undefined}>
        {phu.join(" · ")}
      </span>

      {chips.length > 0 && (
        <span className="tdsx-kb__chips">
          {chipHien.map((c) => {
            const m = tdsxTtMeta(c.trang_thai);
            const chu = `${c.may}${
              c.nguoi.length === 1 ? ` · ${c.nguoi[0]}` : c.nguoi.length > 1 ? ` · ${c.nguoi.length} người` : ""
            }`;
            return (
              <span key={c.cong_viec_id} className="tdsx-kb__chip">
                <span className={`tdsx-tt ${m.cls}`} title={`${chu} · ${m.label}`}>
                  <i aria-hidden="true" />
                  <span className="tdsx-tt__chu">{chu}</span>
                </span>
                <ChipLoaiBuoc loai_buoc={c.nhan?.loai_buoc} nha_cung_cap={c.nhan?.nha_cung_cap} />
                <ChipKhuon can_khuon={!!c.nhan?.khuon_ma} khuon={nhanKhuon(c.nhan)} />
              </span>
            );
          })}
          {chipConLai > 0 && <span className="tdsx-kb__chipthem">+{chipConLai} nhánh khác</span>}
        </span>
      )}
    </button>
  );
}
