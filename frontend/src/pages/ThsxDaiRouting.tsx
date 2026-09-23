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

/** Cửa sổ 5 bước quanh bước của mình; thừa hai đầu gom thành mốc "+N".
 *  Không cuộn ngang: màn xưởng thao tác bằng tay, cuộn ngang là bẫy. */
function cuaSo(dai: SxRoutingBuoc[]): { truoc: number; hien: SxRoutingBuoc[]; sau: number } {
  if (dai.length <= 5) return { truoc: 0, hien: dai, sau: 0 };
  const i = Math.max(0, dai.findIndex((b) => b.la_cua_toi));
  let dau = Math.max(0, i - 2);
  if (dau + 5 > dai.length) dau = dai.length - 5;
  return { truoc: dau, hien: dai.slice(dau, dau + 5), sau: dai.length - dau - 5 };
}

export function ThsxDaiRouting({ dai }: { dai: SxRoutingBuoc[] }) {
  // Lệnh một bước: vẽ một mốc lẻ trên một đoạn ray là nhiễu, không phải thông tin.
  if (!dai || dai.length < 2) return null;
  const { truoc, hien, sau } = cuaSo(dai);
  const iToi = dai.findIndex((b) => b.la_cua_toi);
  const keSau = iToi >= 0 && iToi + 1 < dai.length ? dai[iToi + 1].step_key : null;
  const toi = iToi >= 0 ? dai[iToi] : undefined;
  // Số hàng ĐÃ VỀ TAY tổ, gắn lên đoạn ray ngay trước bước của mình. `da_nhan` là số đã lọc đúng
  // đơn vị đầu vào (luật `board._thuc_nhan`); không có thì lùi về tổng bàn giao đã chốt của bước
  // liền trước. MỘT số, đặt đúng chỗ nó xảy ra — không in lại ở dòng dưới như bản cũ.
  const nhan = toi?.da_nhan ?? (iToi > 0 ? dai[iToi - 1].da_giao_sang_toi : null) ?? null;

  return (
    <ol className="thsx-ray" aria-label="Chuỗi công đoạn của lệnh">
      {truoc > 0 && (
        <li className="thsx-ray__b thsx-ray__b--gom">
          <span className="thsx-ray__moc" aria-hidden="true">+{truoc}</span>
          <span className="thsx-ray__ten">{truoc} công đoạn trước</span>
        </li>
      )}
      {hien.map((b, i) => {
        const laCuoiRay = i === hien.length - 1 && sau === 0;
        const chu = chuTrangThai(b.trang_thai);
        return (
          <li
            key={b.step_key ?? b.thu_tu}
            className="thsx-ray__b"
            data-toi={b.la_cua_toi || undefined}
            data-qua={DA_QUA.has(b.trang_thai) || undefined}
            data-cuoi={laCuoiRay || undefined}
            data-cho-giao={(b.la_cua_toi && keSau != null) || undefined}
          >
            <span className={`thsx-ray__moc thsx-ray__moc--${b.trang_thai}`} aria-hidden="true">
              <Icon name={mocIcon(b.trang_thai)} size={11} />
            </span>
            {b.la_cua_toi && iToi > 0 && nhan != null && (
              <span className="thsx-ray__giao" title="Đã nhận từ công đoạn trước">
                {so(nhan)}
              </span>
            )}
            {b.step_key != null && b.step_key === keSau && (
              <span className="thsx-ray__giao thsx-ray__giao--cho">chờ giao</span>
            )}
            <span className="thsx-ray__ten">
              {b.ten_cong_doan}
              {/* Trạng thái "xong"/"chờ làm" chỉ vẽ bằng mốc + nét ray, nên trình đọc màn hình
                  phải được nói thành chữ ở đây, không thì mất hẳn thông tin. */}
              <span className="thsx-ray__sr"> — {ttMeta(b.trang_thai).label}</span>
            </span>
            <span className="thsx-ray__to">
              {b.la_cua_toi ? "Tổ của bạn" : (b.to_ten ?? "chưa rõ tổ")}
            </span>
            <span className="thsx-ray__so">
              <b>{b.thuc_te > 0 ? so(b.thuc_te) : (b.ke_hoach != null ? so(b.ke_hoach) : "—")}</b>
              {b.don_vi ? <i>{nhanChang(b.don_vi) ?? b.don_vi}</i> : null}
            </span>
            {(chu || b.phan_doan_tong > 1 || b.chay_chung || b.la_kcs_cuoi) && (
              <span className="thsx-ray__ghi">
                {chu && <em className={`thsx-ray__tt thsx-ray__tt--${b.trang_thai}`}>{chu}</em>}
                {b.phan_doan_tong > 1 && <em>{b.phan_doan_tong} lần chạy</em>}
                {b.chay_chung && <em>chạy chung</em>}
                {b.la_kcs_cuoi && <em className="thsx-ray__kcs">KCS cuối</em>}
              </span>
            )}
          </li>
        );
      })}
      {sau > 0 && (
        <li className="thsx-ray__b thsx-ray__b--gom">
          <span className="thsx-ray__moc" aria-hidden="true">+{sau}</span>
          <span className="thsx-ray__ten">{sau} công đoạn sau</span>
        </li>
      )}
    </ol>
  );
}
