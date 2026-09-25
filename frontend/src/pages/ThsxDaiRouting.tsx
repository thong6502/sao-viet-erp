// DẢI ROUTING của lệnh trên bàn tổ (docs/design-dai-routing-tren-ban-to.md).
//
// Tổ chỉ thao tác với bước của mình nhưng phải ĐỌC được cả chuỗi: bước trước xong chưa, ra bao
// nhiêu, đã giao sang chưa; làm xong thì hàng đi đâu. Trước đây thẻ lệnh chỉ hiện đúng bước của
// tổ nên câu đó phải hỏi miệng ngoài xưởng.
//
// HÌNH: BĂNG CHUYỀN, không phải một hàng thẻ (dựng lại 23/09/2026). Lệnh là giấy chảy qua máy
// theo MỘT CHIỀU và đổi đơn vị dọc đường (1.300 tờ → 3.000 con), nên dải vẽ thành một đường ray:
// đoạn đã đi qua liền nét, đoạn chưa tới đứt nét, số hàng đã bàn giao nằm NGAY TRÊN đoạn ray
// giữa hai bước. Bản thẻ cũ phủ nhận điều đó — bốn hộp xám rời, cao bằng nhau nên hở đáy, bốn
// chip trạng thái xếp hàng gây nhiễu, và số "đã giao" bị in lại lần nữa ở dòng dưới.
//
// CHỈ ĐỌC — không `<button>`, không `onClick`, không mở drawer. Bước của tổ khác không mang
// `cong_viec_id` nên cũng không có gì để mở.
import { Icon, type IconName } from "../components/Icons";
import type { SxRoutingBuoc } from "../api/client";
import { nhanChang } from "./lsxBuoc";
import { ttMeta } from "./thsxShared";

/** Số kiểu Việt: 10.200 · 2,5 — cùng cách đọc với phần còn lại của bàn tổ. */
function so(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}

/** Mốc trên ray mang HÌNH riêng cho từng trạng thái, không chỉ màu riêng: xưởng có người mù màu,
 *  và màn hình xưởng hay bị chói. Cùng bộ icon với pill trạng thái để hai chỗ nói một kiểu. */
function mocIcon(tt: string): IconName {
  return ttMeta(tt).icon;
}

/** Trạng thái nào đáng NÓI THÀNH CHỮ. Xong và chờ làm thì đoạn ray đã nói rồi — viết thêm chỉ là
 *  bốn nhãn xếp hàng. Chỉ hai trạng thái BẤT THƯỜNG mới cần chữ. */
function chuTrangThai(tt: string): string | null {
  return tt === "running" || tt === "paused" ? ttMeta(tt).label.toLowerCase() : null;
}

const DA_QUA = new Set(["completed"]);

/** Bước ĐANG TỚI TAY tổ — chỉ MỘT, để dải còn một chỗ nhấn mạnh duy nhất.
 *
 * Một tổ thường giữ NHIỀU bước của cùng một lệnh (Tổ cắt ôm cả Cắt cuộn · Tề giấy · Cắt thành
 * phẩm). Bản đầu lấy `findIndex(la_cua_toi)` — bước ĐẦU TIÊN — nên khi tổ đã làm xong bước đầu,
 * dải vẫn chỉ vào đó và tổ không biết việc đang nằm ở bước nào.
 *
 * Thứ tự ưu tiên: đang chạy → tạm dừng → chờ làm sớm nhất → bước cuối của tổ (đã xong hết).
 */
function buocTrongTam(dai: SxRoutingBuoc[]): number {
  const cua = dai.map((b, i) => [b, i] as const).filter(([b]) => b.la_cua_toi);
  if (!cua.length) return -1;
  for (const tt of ["running", "paused", "released"]) {
    const v = cua.find(([b]) => b.trang_thai === tt);
    if (v) return v[1];
  }
  return cua[cua.length - 1][1];
}

export function ThsxDaiRouting({ dai }: { dai: SxRoutingBuoc[] }) {
  // Lệnh một bước: vẽ một mốc lẻ trên một đoạn ray là nhiễu, không phải thông tin.
  if (!dai || dai.length < 2) return null;
  // HIỆN ĐỦ MỌI CÔNG ĐOẠN (sửa 23/09/2026). Bản trước cắt cửa sổ 5 ô rồi gom hai đầu thành mốc
  // "+N", nên chuỗi 6 bước là bước cuối biến mất — đúng thứ tổ cần thấy nhất ("hàng của tôi rồi
  // đi tới đâu") lại bị giấu. Dải hẹp thì để lưới tự xuống dòng (xem `thuc-hien-sx.css`), còn
  // dưới 900px ray đã dựng đứng nên dài bao nhiêu cũng chứa được.
  const iTam = buocTrongTam(dai);
  const tamKey = iTam >= 0 ? dai[iTam].step_key : null;
  // BÀN GIAO chỉ tồn tại khi hàng ĐỔI TỔ. Hai bước liền nhau cùng tổ + cùng lệnh không có cổng,
  // không có bàn giao (`dau_vao.cung_to_cung_lsx`) — dán "chờ giao" vào giữa chúng là bịa ra một
  // việc tổ không phải làm, mà bản đầu dán đúng như thế.
  const doiTo = (i: number) =>
    i > 0 && i < dai.length && dai[i - 1].la_cua_toi !== dai[i].la_cua_toi;
  // …và chỉ khi bước của tổ ĐÃ XONG mà bước nhận VẪN CHƯA ĐỘNG VÀO. Bước của tổ còn đang chạy thì
  // chưa có gì để giao; còn bước nhận đã chạy/đã xong thì hàng rõ ràng đã sang rồi — dán "chờ
  // giao" lên đó là nói ngược với chính cái dấu ✓ nằm ngay cạnh.
  const raNgoai = (i: number) =>
    doiTo(i) && dai[i - 1].la_cua_toi && DA_QUA.has(dai[i - 1].trang_thai)
    && dai[i].trang_thai === "released";
  const choGiao = new Set(              // step_key của bước NHẬN hàng từ tổ mình
    dai.map((b, i) => (raNgoai(i) ? b.step_key : null)).filter(Boolean),
  );
  // Số hàng ĐÃ VỀ TAY tổ, gắn lên đoạn ray ngay trước bước nhận. `da_nhan` là số đã lọc đúng đơn
  // vị đầu vào (luật `board._thuc_nhan`); không có thì lùi về tổng bàn giao đã chốt của bước liền
  // trước. Chỉ ở chỗ ĐỔI TỔ — MỘT số, đặt đúng chỗ nó xảy ra, không in lại ở dòng dưới.
  const soNhan = (i: number): number | null =>
    (doiTo(i) && dai[i].la_cua_toi
      ? dai[i].da_nhan ?? dai[i - 1].da_giao_sang_toi ?? null
      : null);

  return (
    <ol className="thsx-ray" aria-label="Chuỗi công đoạn của lệnh">
      {dai.map((b, iDai) => {
        const laCuoiRay = iDai === dai.length - 1;
        const chu = chuTrangThai(b.trang_thai);
        const nhan = soNhan(iDai);
        return (
          <li
            key={b.step_key ?? b.thu_tu}
            className="thsx-ray__b"
            data-toi={b.la_cua_toi || undefined}
            data-tam={(tamKey != null && b.step_key === tamKey) || undefined}
            data-qua={DA_QUA.has(b.trang_thai) || undefined}
            data-cuoi={laCuoiRay || undefined}
            data-cho-giao={raNgoai(iDai + 1) || undefined}
          >
            <span className={`thsx-ray__moc thsx-ray__moc--${b.trang_thai}`} aria-hidden="true">
              <Icon name={mocIcon(b.trang_thai)} size={11} />
            </span>
            {nhan != null && (
              <span className="thsx-ray__giao" title="Đã nhận từ công đoạn trước">
                {so(nhan)}
              </span>
            )}
            {b.step_key != null && choGiao.has(b.step_key) && (
              <span className="thsx-ray__giao thsx-ray__giao--cho">chờ giao</span>
            )}
            {/* Chốt cuối chuyền — xem `.thsx-ray__chot`. Đường ray chạy hết bề ngang ô cuối rồi
                đụng vạch chặn này; thiếu nó thì ray hoặc cụt ngay tại mốc cuối (bản trước), hoặc
                thành một đường lửng đọc ra "còn bước nữa chưa hiện". */}
            {laCuoiRay && <span className="thsx-ray__chot" aria-hidden="true" />}
            <div className="thsx-ray__content">
              <div className="thsx-ray__row-h">
                <span className="thsx-ray__ten">
                  {b.ten_cong_doan}
                  <span className="thsx-ray__sr"> — {ttMeta(b.trang_thai).label}</span>
                </span>
                <span className="thsx-ray__to">
                  {b.la_cua_toi ? "Tổ của bạn" : (b.to_ten ?? "chưa rõ tổ")}
                </span>
              </div>
              <div className="thsx-ray__row-sub">
                <span className="thsx-ray__so">
                  <b>{b.thuc_te > 0 ? so(b.thuc_te) : (b.ke_hoach != null ? so(b.ke_hoach) : "—")}</b>
                  {b.don_vi ? <i>{nhanChang(b.don_vi) ?? b.don_vi}</i> : null}
                </span>
                {(chu || b.phan_doan_tong > 1 || b.chay_chung || b.la_kcs_cuoi) && (
                  <span className="thsx-ray__ghi">
                    {chu && <em className={`thsx-ray__tt thsx-ray__tt--${b.trang_thai}`}>{chu}</em>}
                    {b.phan_doan_tong > 1 && <em>{b.phan_doan_tong} lần</em>}
                    {b.chay_chung && <em>chạy chung</em>}
                    {b.la_kcs_cuoi && <em className="thsx-ray__kcs">KCS cuối</em>}
                  </span>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
