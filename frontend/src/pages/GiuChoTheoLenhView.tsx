// CÁCH NHÌN THỨ HAI của Kế hoạch vật tư — gom theo LỆNH thay vì theo mặt hàng.
//
// Vì sao phải có hai cách nhìn chứ không nhồi thêm cột vào bảng cũ: hai câu hỏi khác nhau, và
// không câu nào trả lời hộ câu kia.
//   · Theo MẶT HÀNG hỏi *"còn thiếu gì, mua bao nhiêu"* — gộp mọi lệnh vào một đơn mua.
//   · Theo LỆNH hỏi   *"lệnh này chạy được chưa"* — mà GIỮ CHỖ và cửa xếp lịch đều phán theo CHỦ
//     THỂ. Muốn biết một lệnh đủ chưa trên bảng cũ thì phải mở hết mọi mặt hàng rồi tự dò xem lệnh
//     đó có mặt ở đâu, cộng nhẩm — tức là làm hộ máy đúng việc máy nên làm.
//
// Ba nút trên mỗi thẻ, đúng ba việc người lập kế hoạch làm ở đây:
//   Giữ chỗ  — đăng ký phần tồn cho lệnh này. Đây là ĐIỀU KIỆN DUY NHẤT để xếp lịch.
//   Đề nghị mua — phần còn thiếu, gộp mọi công đoạn của lệnh thành MỘT yêu cầu.
//   Nhả chỗ  — trả lại tồn cho người khác. Hỏi trước vì KHÔNG hoàn tác được.
//
// CỐ Ý KHÔNG CÓ, đừng thêm lại:
//   * KHÔNG có nút "Xếp lịch" ở đây — sai màn. Bảng này lo vật tư; xếp lịch là bàn khác, và cửa
//     chặn của nó đã tự đọc trạng thái giữ chỗ rồi.
//   * KHÔNG tự nhả chỗ giữ lâu. Thứ chạy ngầm mà nhả nhầm đúng hôm gấp thì không ai truy ra được.
//     Máy chỉ BÀY danh sách, người nhìn rồi tự quyết.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CanDoiKhoaDong,
  type CanDoiMau,
  type TheoLenhHang,
  type TheoLenhOut,
  type TheoLenhRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { BangLoi, ChipGap, EmptyState, Skeleton, classHan, ngay, num } from "./keHoachSxShared";

/** Nhãn ngắn của màu, dùng trong dòng mặt hàng. CHỊU ĐƯỢC mã lạ — cùng lý do với `metaCua()` bên
 *  `VatTuKeHoachView`: union TS chỉ là lời hứa lúc biên dịch, server thêm màu mới mà tra thẳng
 *  `Record` thì `undefined.cls` ném lỗi và React gỡ CẢ CÂY, trắng màn toàn app. */
/*  Hai trạng thái KHÔNG còn việc phải làm ("đã cấp" · "đủ") cùng dùng một màu TRUNG TÍNH thay vì
 *  mỗi cái một màu riêng. Tô xanh cho chúng thì thẻ nào cũng rực màu và đúng dòng đỏ lại chìm —
 *  màu phải đánh dấu THIỂU SỐ cần xử. Chữ đã nói rõ nên không mất thông tin.
 *  Bốn trạng thái còn lại tái dùng thẳng lớp màu của bảng theo-mặt-hàng: cùng một dữ liệu ở hai
 *  cách nhìn mà hai bảng màu thì người dùng phải học hai lần. */
const MAU_NGAN: Record<string, { label: string; cls: string }> = {
  xam: { label: "đã cấp", cls: "gclv-tt--yen" },
  xanh: { label: "đủ", cls: "gclv-tt--yen" },
  vang: { label: "đủ nhờ hàng về", cls: "khvt-pill--vang" },
  do: { label: "thiếu", cls: "khvt-pill--do" },
  khong_ro: { label: "chưa đánh giá được", cls: "khvt-pill--khongro" },
  ve_muon: { label: "hàng về muộn", cls: "khvt-pill--vemuon" },
};

function mauNgan(mau: CanDoiMau) {
  return MAU_NGAN[mau] ?? { label: String(mau), cls: "khvt-pill--khongro" };
}

function soGoc(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** Khoá của một thẻ — lệnh và bài ghép dùng chung một danh sách nên id phải mang cả loại. */
function khoaChu(r: { lsx_id: number | null; bai_ghep_id: number | null }): string {
  return r.lsx_id != null ? `l${r.lsx_id}` : `b${r.bai_ghep_id}`;
}

export function GiuChoTheoLenhView({
  eventTick,
  canDeNghiMua,
  onOpenLsx,
  onSoGiuLau,
  focusLsxMa,
}: {
  eventTick?: number;
  /** Bit "tạo yêu cầu mua cho bộ phận" — thiếu thì nút mua tự ẩn, thẻ vẫn xem được. */
  canDeNghiMua: boolean;
  onOpenLsx?: (id: number) => void;
  /** Báo ngược số lệnh "giữ lâu chưa chạy" lên trang cha để vẽ chip — cha KHÔNG tự gọi lại API
   *  (hai lần gọi là hai con số có thể lệch nhau trong cùng một màn). */
  onSoGiuLau?: (n: number) => void;
  /** Mã lệnh cần soi (đèn "Vật tư" ở Kế hoạch SX bấm sang) — điền sẵn ô tìm. */
  focusLsxMa?: string | null;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<TheoLenhOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState(focusLsxMa ?? "");
  // Bấm chấm lần thứ hai với mã khác (màn đã mount) phải đổi ô tìm theo — chỉ đặt giá trị khởi
  // tạo là lần sau vẫn đứng ở mã cũ.
  useEffect(() => {
    if (focusLsxMa) setQ(focusLsxMa);
  }, [focusLsxMa]);
  const [chiCanLo, setChiCanLo] = useState(false);
  const [chiGiuLau, setChiGiuLau] = useState(false);
  const [dangChay, setDangChay] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  /** Thẻ đang chờ xác nhận NHẢ CHỖ. Giữ cả dòng chứ không chỉ id: hộp thoại phải đọc được số
   *  lượng từng món và số lệnh khác đang thiếu, mà những số đó nằm ngay trên dòng. */
  const [hoiNha, setHoiNha] = useState<TheoLenhRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.keHoachVatTu
      .theoLenh(token, {
        q: q.trim() || undefined,
        chi_can_lo: chiCanLo,
        chi_giu_lau: chiGiuLau,
      })
      .then(setData)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, q, chiCanLo, chiGiuLau]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0); // debounce ô tìm
    return () => clearTimeout(t);
  }, [load, eventTick, q]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 6000);
    return () => clearTimeout(t);
  }, [flash]);

  const soGiuLau = data?.so_giu_lau ?? 0;
  useEffect(() => {
    if (data) onSoGiuLau?.(soGiuLau);
  }, [data, soGiuLau, onSoGiuLau]);

  /** Thay MỘT thẻ tại chỗ bằng bản server vừa trả. Không gọi lại cả danh sách: giữa hai lời gọi
   *  người dùng sẽ thấy thẻ cũ (nói dối) rồi thẻ mới nhảy — mà thao tác này bấm liên tục. */
  function thayThe(moi: TheoLenhRow) {
    setData((cu) => {
      if (!cu) return cu;
      const k = khoaChu(moi);
      const items = cu.items.map((r) => (khoaChu(r) === k ? { ...r, ...moi } : r));
      return {
        ...cu,
        items,
        so_giu_lau: items.filter((r) => r.giu_lau_chua_chay).length,
      };
    });
  }

  /** Nhả chỗ KHÔNG hoàn tác được (lệnh khác nhặt ngay phần vừa nhả) ⇒ hỏi trước, và hỏi KÈM SỐ.
   *  Câu chung chung "bạn có chắc không" thì người ta bấm qua theo phản xạ; con số cụ thể mới là
   *  thứ khiến họ dừng một nhịp — hoặc yên tâm bấm vì thấy đúng có lệnh khác đang cần món đó. */
  function doiGiuCho(r: TheoLenhRow, bat: boolean) {
    if (!bat) setHoiNha(r);
    else void chay(r, true);
  }

  async function chay(r: TheoLenhRow, bat: boolean) {
    if (!token) return;
    setDangChay(khoaChu(r));
    try {
      const moi = await api.keHoachVatTu.giuCho(token, bat, {
        lsx_id: r.lsx_id,
        bai_ghep_id: r.bai_ghep_id,
      });
      thayThe(moi);
      setHoiNha(null);
      setFlash(
        bat
          ? moi.du
            ? `${r.ma}: đã giữ đủ — xếp lịch được rồi.`
            : `${r.ma}: mới giữ được một phần. Công tắc vẫn BẬT, hàng về là tự nhặt bù.`
          : `${r.ma}: đã nhả hết chỗ giữ.`,
      );
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setHoiNha(null);
    } finally {
      setDangChay(null);
    }
  }

  async function deNghiMua(r: TheoLenhRow) {
    if (!token) return;
    const dong: CanDoiKhoaDong[] = r.hang.flatMap((h) => h.khoa_do);
    if (dong.length === 0) return;
    setDangChay(khoaChu(r));
    try {
      const kq = await api.keHoachVatTu.deNghiMua(token, dong);
      setFlash(
        `Đã lập yêu cầu mua ${kq.code} cho ${r.ma}. Mở màn Mua hàng xem lại số lượng rồi gửi — `
          + "hệ thống KHÔNG tự gửi.",
      );
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDangChay(null);
    }
  }

  const rows = data?.items ?? [];
  const tomTat = useMemo(
    () => ({
      daGiu: rows.filter((r) => r.du).length,
      dangCho: rows.filter((r) => r.bat && !r.du).length,
      chuaBat: rows.filter((r) => !r.bat).length,
    }),
    [rows],
  );

  return (
    <>
      <div className="khsx__toolbar">
        <span className="khvt-sum">
          <b>{num(rows.length)}</b> lệnh
          {tomTat.daGiu > 0 && (
            <span className="gclv-sum__du" title="Đã giữ đủ vật tư — xếp lịch được.">
              {num(tomTat.daGiu)} giữ đủ
            </span>
          )}
          {tomTat.dangCho > 0 && (
            <span
              className="khvt-sum__vemuon"
              title="Đã bật giữ chỗ nhưng chưa đủ — hàng về là tự nhặt bù, không phải bấm lại."
            >
              {num(tomTat.dangCho)} giữ dở
            </span>
          )}
          {tomTat.chuaBat > 0 && (
            <span className="khvt-sum__khongro" title="Chưa bật giữ chỗ ⇒ chưa xếp lịch được.">
              {num(tomTat.chuaBat)} chưa giữ
            </span>
          )}
        </span>
        <div className="khsx__spacer" />
        <label className="khvt-toggle">
          <input
            type="checkbox"
            checked={chiCanLo}
            onChange={(e) => setChiCanLo(e.target.checked)}
          />
          Chỉ lệnh còn việc phải lo
        </label>
        <label className="khsx__search">
          <Icon name="search" size={14} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã lệnh / mặt hàng"
            aria-label="Tìm lệnh trong kế hoạch vật tư"
          />
        </label>
      </div>

      {/* ── GIỮ LÂU MÀ CHƯA CHẠY ────────────────────────────────────────────────
          Thay cho cơ chế tự-hết-hạn (cố ý KHÔNG làm): máy bày ra, người tự quyết. Đặt ngay đây
          chứ không đẻ màn riêng — chỗ nhả chỗ giữ chính là các thẻ ngay bên dưới. */}
      {soGiuLau > 0 && (
        <div className="gclv-nhac" role="status">
          <Icon name="clock" size={15} />
          <span>
            <b>{num(soGiuLau)}</b> lệnh đang giữ vật tư trên một tuần mà <b>chưa đưa vào kế
            hoạch</b>. Chỗ giữ vẫn trừ vào tồn của mọi lệnh khác — xem lại rồi nhả bớt nếu chưa
            chạy tới.
          </span>
          <button
            type="button"
            className={`gclv-nhac__nut ${chiGiuLau ? "is-bat" : ""}`}
            onClick={() => setChiGiuLau((v) => !v)}
          >
            {chiGiuLau ? "Xem tất cả" : "Chỉ xem nhóm này"}
          </button>
        </div>
      )}

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          {flash}
        </div>
      )}
      {err && <BangLoi text={err} onRetry={load} />}

      {data === null ? (
        <div className="khsx__tablewrap">
          <table className="khsx__table">
            <Skeleton rows={4} cols={5} />
          </table>
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={q || chiCanLo || chiGiuLau ? "search" : "packageCheck"}
          title={
            q || chiCanLo || chiGiuLau
              ? "Không có lệnh nào khớp bộ lọc."
              : "Chưa có lệnh nào cần cân đối vật tư."
          }
          sub={
            q || chiCanLo || chiGiuLau
              ? undefined
              : "Bảng gom lệnh ở trạng thái Sẵn sàng · Đã lập kế hoạch · Đã phát hành."
          }
          action={
            q || chiCanLo || chiGiuLau ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setQ("");
                  setChiCanLo(false);
                  setChiGiuLau(false);
                }}
              >
                Xoá bộ lọc
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="khvt-list">
          {rows.map((r) => (
            <TheLenh
              key={khoaChu(r)}
              row={r}
              dangChay={dangChay === khoaChu(r)}
              canDeNghiMua={canDeNghiMua}
              onGiuCho={doiGiuCho}
              onDeNghiMua={deNghiMua}
              onOpenLsx={onOpenLsx}
            />
          ))}
        </div>
      )}

      <HopNhaCho
        row={hoiNha}
        busy={!!hoiNha && dangChay === khoaChu(hoiNha)}
        onXacNhan={() => hoiNha && void chay(hoiNha, false)}
        onHuy={() => setHoiNha(null)}
      />
    </>
  );
}

// --- HỘP XÁC NHẬN NHẢ CHỖ ---------------------------------------------------
/** Kê ĐÍCH DANH sắp nhả cái gì, bao nhiêu, và ai đang cần nó.
 *
 *  Ba câu, ba việc khác nhau:
 *    · bảng món  — *"nhả cái gì"*: không có số thì người dùng không biết mình vừa buông thứ mất
 *      hai tuần mới mua lại được.
 *    · "N lệnh khác đang thiếu" — *"nhả ra thì ai đỡ"*: đây là nửa TÍCH CỰC, và nó cũng quan
 *      trọng. Hộp thoại chỉ doạ thì người ta không bao giờ nhả, kể cả lúc nên nhả.
 *    · hệ quả    — *"nhả rồi thì sao"*: mất quyền xếp lịch, và bật lại có thể chẳng còn gì. */
function HopNhaCho({
  row,
  busy,
  onXacNhan,
  onHuy,
}: {
  row: TheoLenhRow | null;
  busy: boolean;
  onXacNhan: () => void;
  onHuy: () => void;
}) {
  const dangGiu = (row?.hang ?? []).filter((h) => h.dang_giu > 0);
  // Đếm theo MÓN, không cộng dồn số lượng: 40 kg giấy + 2 kg mực cộng thành "42" là vô nghĩa.
  const soLenhDoi = Math.max(0, ...dangGiu.map((h) => h.so_lenh_khac_thieu), 0);
  return (
    <ConfirmDialog
      open={!!row}
      danger
      busy={busy}
      title={`Nhả chỗ giữ của ${row?.ma ?? ""}?`}
      confirmLabel="Nhả chỗ"
      onConfirm={onXacNhan}
      onCancel={onHuy}
    >
      {dangGiu.length === 0 ? (
        <p className="gclv-hop__trong">Lệnh này chưa giữ được món nào — nhả chỉ tắt công tắc.</p>
      ) : (
        <>
          <p className="gclv-hop__dau">Sắp trả lại kho:</p>
          <ul className="gclv-hop__ds">
            {dangGiu.map((h) => (
              <li key={`${h.hang_loai}-${h.hang_id}`}>
                <b>
                  {soGoc(h.dang_giu)} {h.don_vi_goc ?? ""}
                </b>{" "}
                {h.hang_ten ?? h.hang_ma ?? "(đã gỡ khỏi danh mục)"}
                {h.so_lenh_khac_thieu > 0 && (
                  <span className="gclv-hop__doi">
                    {" "}— {h.so_lenh_khac_thieu} lệnh khác đang thiếu món này
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="gclv-hop__hq">
        {soLenhDoi > 0
          ? "Phần vừa nhả sẽ được lệnh cần sớm hơn nhặt ngay — bật lại có thể chẳng còn gì."
          : "Hiện chưa lệnh nào khác thiếu những món này, nhưng bật lại vẫn không chắc giữ lại được."}
        {" "}
        <b>{row?.ma}</b> cũng mất quyền xếp lịch cho tới khi giữ đủ lại.
      </p>
    </ConfirmDialog>
  );
}

// --- MỘT THẺ LỆNH -----------------------------------------------------------
function TheLenh({
  row: r,
  dangChay,
  canDeNghiMua,
  onGiuCho,
  onDeNghiMua,
  onOpenLsx,
}: {
  row: TheoLenhRow;
  dangChay: boolean;
  canDeNghiMua: boolean;
  onGiuCho: (r: TheoLenhRow, bat: boolean) => void;
  onDeNghiMua: (r: TheoLenhRow) => void;
  onOpenLsx?: (id: number) => void;
}) {
  const soDo = r.hang.reduce((s, h) => s + h.khoa_do.length, 0);
  const caiPhaiLo = r.so_thieu || r.so_khong_ro || r.so_ve_muon || r.giu_lau_chua_chay
    || r.ngoai_pham_vi;

  return (
    <section
      className={`khvt-card gclv-card ${caiPhaiLo ? "khvt-card--do" : ""} ${r.du ? "gclv-card--du" : ""}`}
    >
      <header className="khvt-card__head">
        <div className="khvt-card__id">
          {r.lsx_id && onOpenLsx ? (
            <button type="button" className="khvt-link" onClick={() => onOpenLsx(r.lsx_id!)}>
              {r.ma}
            </button>
          ) : (
            <span className="khsx__code">{r.ma}</span>
          )}
          {r.bai_ghep_id != null && (
            <span className="khsx-chip khsx-chip--ngoai">
              <Icon name="layers" size={11} /> bài ghép
            </span>
          )}
          {r.is_rush && <ChipGap />}
        </div>

        <dl className="khvt-stats">
          <div>
            <dt>Cần từ</dt>
            <dd className={r.moc_tam ? "" : classHan(r.ngay_can)}>
              {ngay(r.ngay_can)}
              {r.moc_tam && (
                <span
                  className="khvt-tam"
                  title="Bước chưa xếp lịch — mốc suy từ hạn sản xuất trừ tổng thời gian dẫn."
                >
                  mốc tạm
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt>Mặt hàng</dt>
            <dd>{num(r.so_mat_hang)}</dd>
          </div>
        </dl>

        <GiuChoPill row={r} />
      </header>

      {/* Câu CHỈ VIỆC — thẻ đỏ mà không nói phải làm gì thì người dùng đứng nhìn. */}
      {r.ngoai_pham_vi ? (
        <p className="gclv-nhan gclv-nhan--canh">
          Lệnh này <b>không còn trong kế hoạch</b> (bị kéo về nháp, hoặc đã tách khỏi bài ghép)
          nhưng vẫn đang giữ vật tư — chỗ giữ đó trừ vào tồn của mọi lệnh khác. Nhả đi nếu chưa
          định chạy lại.
        </p>
      ) : r.giu_lau_chua_chay ? (
        <p className="gclv-nhan gclv-nhan--canh">
          Giữ đã <b>{num(r.so_ngay_giu ?? 0)} ngày</b> mà chưa đưa vào kế hoạch. Máy KHÔNG tự nhả —
          nếu lệnh chưa chạy tới, nhả để lệnh khác dùng được.
        </p>
      ) : r.khong_ro ? (
        <p className="gclv-nhan gclv-nhan--canh">
          Có mặt hàng <b>chưa quy đổi được về đơn vị kho</b>. Máy không đoán, nên lệnh này không bao
          giờ được tính là đủ — kiểm lại đơn vị của mặt hàng bên danh mục.
        </p>
      ) : !r.bat ? (
        <p className="gclv-nhan">
          Chưa giữ chỗ ⇒ <b>chưa xếp lịch được</b>. Bấm “Giữ chỗ” để đăng ký phần tồn cho lệnh này;
          giữ được bao nhiêu hay bấy nhiêu, hàng về là tự nhặt bù.
        </p>
      ) : r.du ? (
        // Giữ đủ + hàng đã trong kho = KHÔNG có câu nào cả: viên trạng thái và vạch xanh mép trái
        // đã nói hết. Rải thêm một dòng chữ lên mọi thẻ bình thường là làm loãng đúng những thẻ
        // có việc phải làm. Chỉ nói khi có RÀNG BUỘC NGÀY — thứ hai dấu hiệu kia không diễn được.
        r.xep_som_nhat ? (
          <p className="gclv-nhan gclv-nhan--ok">
            Đã giữ đủ, nhưng một phần bám lô đang về — <b>không xếp trước {ngay(r.xep_som_nhat)}</b>.
          </p>
        ) : null
      ) : (
        <p className="gclv-nhan gclv-nhan--canh">
          Mới giữ được một phần. Công tắc vẫn <b>BẬT</b> — hàng về kho là tự nhặt bù, không phải
          bấm lại. Muốn chạy sớm thì đề nghị mua phần thiếu.
        </p>
      )}

      <ul className="gclv-mons">
        {r.hang.map((h) => (
          <DongMatHang key={`${h.hang_loai}-${h.hang_id}`} hang={h} />
        ))}
      </ul>

      <footer className="gclv-nut">
        {!r.bat ? (
          <Button onClick={() => onGiuCho(r, true)} disabled={dangChay}>
            <Icon name="lock" size={13} /> {dangChay ? "Đang giữ…" : "Giữ chỗ"}
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => onGiuCho(r, false)} disabled={dangChay}>
            <Icon name="lockOpen" size={13} /> {dangChay ? "Đang nhả…" : "Nhả chỗ"}
          </Button>
        )}
        {canDeNghiMua && soDo > 0 && (
          <Button variant="secondary" onClick={() => onDeNghiMua(r)} disabled={dangChay}>
            <Icon name="cart" size={13} /> Đề nghị mua {soDo} dòng thiếu
          </Button>
        )}
        {/* Đã bật mà chưa đủ thì vẫn cho nhặt lại: người dùng vừa nhập kho xong, muốn thấy ngay. */}
        {r.bat && !r.du && (
          <Button variant="secondary" onClick={() => onGiuCho(r, true)} disabled={dangChay}>
            <Icon name="refresh" size={13} /> Nhặt thêm ngay
          </Button>
        )}
        {r.da_xep_lich && (
          <span className="gclv-nut__ghi">
            <Icon name="calendar" size={12} /> đã đưa vào kế hoạch
          </span>
        )}
      </footer>
    </section>
  );
}

/** Viên trạng thái giữ chỗ — LUÔN kèm chữ, không chỉ dựa màu (a11y). */
function GiuChoPill({ row: r }: { row: TheoLenhRow }) {
  const [cls, label, hint] = !r.bat
    ? ["gclv-pill--tat", "Chưa giữ chỗ", "Chưa đăng ký tồn cho lệnh này ⇒ chưa xếp lịch được."]
    : r.du
      ? ["gclv-pill--du", "Đã giữ đủ", "Đủ 100% — cửa xếp lịch đã mở cho lệnh này."]
      : ["gclv-pill--dang", "Đang giữ dở", "Đã bật nhưng chưa đủ. Hàng về là tự nhặt bù."];
  return (
    <span className={`khsx-pill ${cls}`} title={hint}>
      <span className="khsx-pill__dot" aria-hidden="true" />
      {label}
    </span>
  );
}

/** Một mặt hàng trong thẻ. Đã GỘP mọi công đoạn — `so_buoc > 1` phải nói ra, không thì người đọc
 *  tưởng đó là số của một bước rồi đi mua thiếu. */
function DongMatHang({ hang: h }: { hang: TheoLenhHang }) {
  const m = mauNgan(h.trang_thai);
  return (
    <li className="gclv-mon">
      <span className="gclv-mon__ma">{h.hang_ma ?? "—"}</span>
      <span className="gclv-mon__ten">{h.hang_ten ?? "(đã gỡ khỏi danh mục)"}</span>
      {h.so_buoc > 1 && (
        <span className="gclv-mon__buoc" title="Món này khai ở nhiều công đoạn — số bên phải đã cộng cả.">
          {h.so_buoc} bước
        </span>
      )}
      <span className="gclv-mon__so">
        cần {soGoc(h.can)} <span className="khsx-unit">{h.don_vi_goc ?? ""}</span>
      </span>
      <span className="gclv-mon__giu">
        {h.dang_giu > 0 ? `giữ ${soGoc(h.dang_giu)}` : "chưa giữ"}
      </span>
      <span className={`khsx-pill gclv-mon__tt ${m.cls}`}>
        {h.thieu > 0 ? `${m.label} ${soGoc(h.thieu)}` : m.label}
      </span>
    </li>
  );
}
