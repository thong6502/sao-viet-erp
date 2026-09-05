// Tab KANBAN của màn "Theo dõi sản xuất" (Task 17b, Bước 3).
//
// MỘT LỆNH = MỘT CARD, kể cả routing rẽ nhiều nhánh (Ruling C113/thiết kế §0, đã được chủ dự án
// đọc và duyệt). Các nhánh đang chạy/tạm dừng cùng lúc hiện thành DANH SÁCH chip `chip_dang_chay`
// bên TRONG card đó — KHÔNG tách thành nhiều card. Card neo cứng `lsx_id` nên bấm card luôn mở
// thẳng hồ sơ, không có tình huống phải chọn (khác hẳn khối của tab Theo máy).
//
// Khung cột dựng từ `/meta` (`cot: [{key, ten}]`), KHÔNG dựng từ dữ liệu card — cột "khac" do máy
// chủ trả CUỐI danh sách sẵn (`bang_theo_doi.meta`), không cần sắp lại ở đây. `/meta` nạp CÙNG NHỊP
// với `/kanban` trong MỘT lượt `Promise.all` (Ruling C125) — không cache `/meta` riêng, tránh cảnh
// danh mục công đoạn đổi giữa hai lượt gọi làm card rơi câm vào cột không còn tồn tại.
//
// LỌC Ở MÁY CHỦ: `params` do `TheoDoiSanXuatPage` dựng một chỗ rồi truyền xuống, component này
// không tự lọc/cắt gì trên mảng `cards` nhận về.
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import type { TdsxKanbanCard, TdsxKanbanMeta, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { ChipKhuon, ChipLoaiBuoc, nhanKhuon } from "../components/ChipBuoc";
import { Icon, type IconName } from "../components/Icons";
import { ChipGap, EmptyState, classHan, ngay, num } from "./keHoachSxShared";

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
  refreshTick,
  onOpenHoSo,
  onXoaLoc,
}: {
  /** Tab Kanban đang được xem hay không — `false` thì component vẫn ở trong DOM (`hidden`, giữ vị
   *  trí cuộn của nó) nhưng KHÔNG tự gọi lại API khi bộ lọc đổi ở nền; bù lại, hễ chuyển sang active
   *  là một lượt tải MỚI chạy ngay để không bao giờ hiện dữ liệu cũ hơn bộ lọc hiện tại. */
  active: boolean;
  token: string | null;
  params: TdsxThanhLocParams;
  /** Nhịp SSE đã gộp của `TheoDoiSanXuatPage` — đổi giá trị (kể cả khi đang active) là một tín hiệu
   *  "có sự kiện mới, tải lại". */
  refreshTick: number;
  /** Mở lớp phủ hồ sơ đúng lệnh — bấm bất kỳ đâu trên card. */
  onOpenHoSo: (lsxId: number) => void;
  /** Xóa toàn bộ bộ lọc — dùng cho nút trong khối rỗng "Không có việc nào khớp bộ lọc." (thiết kế
   *  §7 tình huống b), để người dùng không phải cuộn lên thanh lọc chung. */
  onXoaLoc: () => void;
}) {
  const [meta, setMeta] = useState<TdsxKanbanMeta | null>(null);
  const [cards, setCards] = useState<TdsxKanbanCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false);
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);
  /** Mặc định ẨN cột chưa có việc. `/meta` trả NGUYÊN danh mục công đoạn (đo thật: 24 cột, 22 cột
   *  rỗng ⇒ board rộng 6756px, phải kéo ngang 5608px mới hết) nên để nguyên thì việc thật bị chôn
   *  giữa một rừng cột trống. Ẩn để đọc được, nhưng luôn nói RÕ đang ẩn mấy cột kèm nút mở lại —
   *  không cột nào biến mất im lặng. */
  const [hienCotRong, setHienCotRong] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([api.theoDoiSanXuat.meta(token), api.theoDoiSanXuat.kanban(token, params)])
      .then(([m, k]) => {
        setMeta(m);
        setCards(k.cards);
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

  // MỘT effect duy nhất: chạy khi (1) tab vừa chuyển sang active, (2) bộ lọc/token đổi trong lúc
  // đang active, hoặc (3) một nhịp SSE mới tới trong lúc đang active. Tab đang ẩn thì mọi thay đổi
  // ở trên chỉ khiến effect chạy rồi thoát ngay dòng đầu — không có request nào bay ra nền.
  useEffect(() => {
    if (!active) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, load, refreshTick]);

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
                <Button variant="ghost" onClick={load}>
                  Tải lại
                </Button>
              )
            }
          />
        </div>
      )}

      {!loi && daTai && !loading && meta && meta.cot.length > 0 && tongTheLoc === 0 && (
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

      {(!daTai || tongTheLoc > 0 || !meta || meta.cot.length === 0) && !loi && soCotRong > 0 && (
        <div className="tdsx-kb__cotloc">
          <span className="tdsx-kb__cotloc-chu">
            {hienCotRong
              ? `Đang hiện đủ ${cotTatCa.length} công đoạn của danh mục.`
              : `Đang ẩn ${soCotRong} công đoạn chưa có việc.`}
          </span>
          <Button variant="ghost" onClick={() => setHienCotRong((v) => !v)}>
            {hienCotRong ? "Ẩn công đoạn trống" : "Hiện tất cả công đoạn"}
          </Button>
        </div>
      )}

      {(!daTai || tongTheLoc > 0 || !meta || meta.cot.length === 0) && !loi && (
        <div className={`tdsx-kb__board${loading && daTai ? " is-mo" : ""}`}>
          {cotHien.map((cot) => {
            const trongCot = theoCot.get(cot.key) ?? [];
            return (
              <section key={cot.key} className="tdsx-kb__col" aria-label={`Công đoạn ${cot.ten}`}>
                <header className="tdsx-kb__colhead">
                  <span className="tdsx-kb__colten">{cot.ten}</span>
                  {daTai && <span className="tdsx-kb__coln">{num(trongCot.length)}</span>}
                </header>
                <div className="tdsx-kb__body">
                  {!daTai ? (
                    <>
                      <span className="khsx-skel__bar khsx-skel__bar--card" />
                      <span className="khsx-skel__bar khsx-skel__bar--card" />
                    </>
                  ) : trongCot.length === 0 ? (
                    <p className="tdsx-kb__colrong">Chưa có việc nào ở công đoạn này.</p>
                  ) : (
                    trongCot.map((card) => (
                      <TheCard key={card.lsx_id} card={card} onOpen={() => onOpenHoSo(card.lsx_id)} />
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

function TheCard({ card, onOpen }: { card: TdsxKanbanCard; onOpen: () => void }) {
  const qua_han = card.han_hoan_thanh_sx != null && classHan(card.han_hoan_thanh_sx) === "khsx-date--late";
  const chips = card.chip_dang_chay;
  const chipHien = chips.length > CHIP_HIEN_TOI_DA ? chips.slice(0, CHIP_RUT_GON_CON_LAI) : chips;
  const chipConLai = chips.length - chipHien.length;

  return (
    <button type="button" className="tdsx-kb__card" onClick={onOpen}>
      <span className="tdsx-kb__row1">
        <span className="tdsx-kb__ma">{card.ma}</span>
        {card.is_rush && <ChipGap />}
      </span>

      <span className="tdsx-kb__row2" title={`${card.khach_hang ?? "—"} · ${card.ten ?? "—"}`}>
        {card.khach_hang ?? "—"} · {card.ten ?? "—"}
      </span>

      <span className="tdsx-kb__row3">
        <span className="tdsx-kb__sl">{num(card.so_luong_dat)}</span>
        <span className={`tdsx-kb__han ${classHan(card.han_hoan_thanh_sx)}`}>
          {qua_han && <Icon name="alert" size={12} />}
          {qua_han ? "Quá hạn" : "Hạn"} {ngay(card.han_hoan_thanh_sx)}
        </span>
      </span>

      <span className="tdsx-kb__row4">{card.buoc_hien_tai ?? "—"}</span>

      {chips.length > 0 && (
        <span className="tdsx-kb__chips">
          {chipHien.map((c) => {
            const m = tdsxTtMeta(c.trang_thai);
            // Chữ phải nằm trong MỘT span riêng: `.tdsx-tt` là inline-flex, chữ trần thành flex
            // item vô danh nên `text-overflow: ellipsis` không ăn — đo thật ở thẻ Kanban rộng
            // 218px mà nội dung 281px, "…Thợ Tổ Cán màng 1" bị cắt ngang chữ, không dấu ba chấm,
            // không cách nào đọc lại. `title` để hover ra đủ (thẻ cha có `title` riêng của nó).
            const chu = `${c.may}${
              c.nguoi.length === 1 ? ` · ${c.nguoi[0]}` : c.nguoi.length > 1 ? ` · ${c.nguoi.length} người` : ""
            }`;
            return (
              <span key={c.cong_viec_id} className="tdsx-kb__chip">
                <span className={`tdsx-tt ${m.cls}`} title={`${chu} · ${m.label}`}>
                  <i aria-hidden="true" />
                  <span className="tdsx-tt__chu">{chu}</span>
                </span>
                {/* Nhãn của BƯỚC (04/09/2026) — gán ở màn Kế hoạch thì phải theo bước tới tận
                    đây, không phải mỗi màn tự suy lấy rồi đứt quãng giữa đường. */}
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
