// GIAI ĐOẠN 5 của bàn THỰC HIỆN SẢN XUẤT — KCS §13 · Kho thành phẩm/BTP §14 · Đóng nhóm §16/§13.3.
//
// Gộp thẳng vào drawer `ThsxExecPanels`/`ThsxDrawer` (KHÔNG đẻ màn mới): ba khối panel gấp/mở trong
// drawer + hai HỘP THƯ mức trang (phản hồi trách nhiệm lỗi · kho xác nhận nhập). Component KHÔNG tự
// gọi API: mọi mặt GHI đi qua `exec.*` / callback controller (khoá lạc quan + refetch + toast).
//
//  · KcsPanel  — hiện khi bước là KCS (`la_kcs`): ghi mẻ kiểm tra, ghi lỗi + ≥1 ảnh, thêm/xoá ảnh.
//  · KhoPanel  — hiện khi KCS + có nhóm (`nhom_id`): tạo yêu cầu nhập thành phẩm, phân loại BTP dư.
//  · DongNhomPanel — hiện khi KCS CUỐI + có nhóm: checklist cổng đóng + nút "Đóng thiếu" kèm lý do.
//  · KcsHopThu / KhoHopThu — hộp thư mức trang, hiện khi CÓ việc chờ (real-time qua eventTick/g5Tick).
import { useEffect, useState } from "react";
import type {
  SxWorkItemChiTiet, SxKcsChiTiet, SxKcsBatchChiTiet, SxKcsLoi, SxKcsAnh,
  SxKhoChiTiet, SxNhapKhoYc, SxKhoLot, SxKhoHopThu, SxDongNhomDieuKien,
  SxPhanLoaiBtp, SxLyDo,
} from "../api/client";
import { assetUrl } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { num, ngayGio } from "./keHoachSxShared";
import { Field, LyDoSelect, toNum, toDtLocal, type ThsxExec } from "./ThsxExecPanels";

export type Opt = { id: number; ten: string };

// ============================ bảng nhãn trạng thái ==========================
const KL: Record<string, { txt: string; cls: string }> = {
  dat: { txt: "đạt", cls: "thsx-x-pill--ok" },
  dat_mot_phan: { txt: "đạt một phần", cls: "thsx-x-pill--adj" },
  khong_dat: { txt: "không đạt", cls: "thsx-x-pill--bad" },
};
const LOI_TT: Record<string, { txt: string; cls: string }> = {
  pending: { txt: "chờ tổ phản hồi", cls: "thsx-x-pill--wait" },
  accepted: { txt: "tổ đã nhận lỗi", cls: "thsx-x-pill--ok" },
  rejected: { txt: "tổ từ chối", cls: "thsx-x-pill--bad" },
};
const YC_TT: Record<string, { txt: string; cls: string }> = {
  cho_kho: { txt: "chờ kho nhận", cls: "thsx-x-pill--wait" },
  nhap_mot_phan: { txt: "đã nhập một phần", cls: "thsx-x-pill--adj" },
  da_nhap: { txt: "đã nhập đủ", cls: "thsx-x-pill--ok" },
  huy: { txt: "đã huỷ", cls: "thsx-x-pill--off" },
};
const PL_LABEL: Record<SxPhanLoaiBtp, string> = {
  nhap_btp: "Nhập kho BTP", mau_luu: "Mẫu lưu", phe: "Phế",
};
const NHOM_TT: Record<string, { txt: string; cls: string }> = {
  in_production: { txt: "đang sản xuất", cls: "thsx-x-pill--adj" },
  cho_dieu_kien: { txt: "chờ điều kiện", cls: "thsx-x-pill--wait" },
  closed_full: { txt: "đã đóng đủ", cls: "thsx-x-pill--ok" },
  closed_short: { txt: "đóng thiếu", cls: "thsx-x-pill--bad" },
};

function Pill({ map, k }: { map: Record<string, { txt: string; cls: string }>; k: string }) {
  const m = map[k] ?? { txt: k, cls: "thsx-x-pill--off" };
  return <span className={`thsx-x-pill ${m.cls}`}>{m.txt}</span>;
}

// ════════════════════════════ KCS §13 (panel drawer) ════════════════════════
export function ThsxKcsPanel({
  chiTiet, ct, canAssign, busy, loadLyDo, toChiuOpts, congDoanRefOpts, exec,
}: {
  chiTiet: SxWorkItemChiTiet;
  ct: SxKcsChiTiet | null;
  canAssign: boolean;
  busy: boolean;
  loadLyDo: (nhom: string) => Promise<SxLyDo[]>;
  toChiuOpts: Opt[];
  congDoanRefOpts: Opt[];
  exec: ThsxExec;
}) {
  const cv = chiTiet.cong_viec;
  const [formOpen, setFormOpen] = useState(false);
  const batches = ct?.batch ?? [];
  const tong = batches.reduce(
    (a, b) => ({ nhan: a.nhan + b.so_luong_nhan, dat: a.dat + b.so_luong_dat, kd: a.kd + b.so_luong_khong_dat }),
    { nhan: 0, dat: 0, kd: 0 },
  );

  return (
    <section className="thsx-psec thsx-x thsx-x-kcs">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="shield" size={13} /> Kiểm tra KCS</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen((o) => !o)} disabled={busy} aria-expanded={formOpen}>
            <Icon name="plus" size={13} /> Ghi mẻ
          </Button>
        )}
      </div>

      <div className="thsx-x-stat">
        <span className="thsx-x-stat__it">nhận <b className="thsx-num">{num(tong.nhan)}</b></span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it">đạt <b className="thsx-num">{num(tong.dat)}</b></span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it thsx-x-stat__it--bad">không đạt <b className="thsx-num">{num(tong.kd)}</b></span>
      </div>

      {formOpen && <KcsBatchForm cv={cv} busy={busy} onXong={() => setFormOpen(false)} exec={exec} />}

      {ct == null ? (
        <p className="thsx-note">Đang tải kết quả kiểm tra…</p>
      ) : batches.length === 0 ? (
        <p className="thsx-note">Chưa ghi mẻ kiểm tra nào.</p>
      ) : (
        <ul className="thsx-x-list">
          {batches.map((b) => (
            <KcsBatchRow key={b.id} b={b} canAssign={canAssign} busy={busy}
              loadLyDo={loadLyDo} toChiuOpts={toChiuOpts} congDoanRefOpts={congDoanRefOpts} exec={exec} />
          ))}
        </ul>
      )}
    </section>
  );
}

function KcsBatchForm({
  cv, busy, onXong, exec,
}: {
  cv: SxWorkItemChiTiet["cong_viec"]; busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const [batDau, setBatDau] = useState(toDtLocal(cv.du_kien_bat_dau));
  const [ketThuc, setKetThuc] = useState(toDtLocal(cv.du_kien_ket_thuc));
  const [nhan, setNhan] = useState("");
  const [dat, setDat] = useState("");
  const [coMau, setCoMau] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const nNhan = toNum(nhan), nDat = toNum(dat), nMau = toNum(coMau);
  const kd = Math.max(0, nNhan - nDat);
  const donVi = cv.don_vi_ra ?? cv.don_vi_vao ?? null;
  const ketLuan = nNhan <= 0 ? "" : nDat >= nNhan ? "dat" : nDat <= 0 ? "khong_dat" : "dat_mot_phan";
  const hopLe = !!batDau && !!ketThuc && ketThuc > batDau
    && nNhan > 0 && nDat >= 0 && nDat <= nNhan && nMau <= nNhan;

  async function luu() {
    if (await exec.taoBatchKcs(cv.id, {
      bat_dau: batDau, ket_thuc: ketThuc, so_luong_nhan: nNhan, so_luong_dat: nDat,
      so_luong_khong_dat: kd, co_mau: nMau > 0 ? nMau : null,
      don_vi: donVi, ghi_chu: ghiChu.trim() || null,
    })) onXong();
  }

  return (
    <div className="thsx-x-form">
      <div className="thsx-x-grid2">
        <Field label="Bắt đầu">
          <input type="datetime-local" className="thsx-x-in" value={batDau} onChange={(e) => setBatDau(e.target.value)} />
        </Field>
        <Field label="Kết thúc">
          <input type="datetime-local" className="thsx-x-in" value={ketThuc} onChange={(e) => setKetThuc(e.target.value)} />
        </Field>
        <Field label={`Số nhận${donVi ? ` (${donVi})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in" value={nhan} onChange={(e) => setNhan(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Số đạt">
          <input type="number" min={0} className="thsx-x-in" value={dat} onChange={(e) => setDat(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Có mẫu (nếu có)">
          <input type="number" min={0} className="thsx-x-in" value={coMau} onChange={(e) => setCoMau(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Ghi chú">
          <input type="text" className="thsx-x-in" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} placeholder="tuỳ chọn" />
        </Field>
      </div>
      <div className={`thsx-x-hong${nNhan > 0 && kd > 0 ? " is-bad" : ""}`}>
        <Icon name={kd > 0 ? "alert" : "check"} size={13} />
        <span>không đạt <b className="thsx-num">{num(kd)}</b>{ketLuan && <> · kết luận <b>{KL[ketLuan]?.txt}</b></>}</span>
        {!hopLe && nNhan > 0 && <span className="thsx-x-err">Số đạt phải ≤ số nhận</span>}
      </div>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Ghi mẻ kiểm tra
        </Button>
      </div>
    </div>
  );
}

function KcsBatchRow({
  b, canAssign, busy, loadLyDo, toChiuOpts, congDoanRefOpts, exec,
}: {
  b: SxKcsBatchChiTiet; canAssign: boolean; busy: boolean;
  loadLyDo: (nhom: string) => Promise<SxLyDo[]>; toChiuOpts: Opt[]; congDoanRefOpts: Opt[]; exec: ThsxExec;
}) {
  const [open, setOpen] = useState(false);
  const [loiOpen, setLoiOpen] = useState(false);

  return (
    <li className="thsx-x-item">
      <button type="button" className="thsx-x-item__h" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name="chevron" size={13} className={open ? "" : "thsx-rot-90"} />
        <span className="thsx-x-item__time">{ngayGio(b.bat_dau)}</span>
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-item__q">
          <b className="thsx-num">{num(b.so_luong_dat)}</b>/<span className="thsx-num">{num(b.so_luong_nhan)}</span>
          <span className="thsx-x-unit"> {b.don_vi}</span>
        </span>
        <Pill map={KL} k={b.ket_luan} />
      </button>
      {open && (
        <div className="thsx-x-item__body">
          <div className="thsx-x-kv"><span>Nhận</span><b className="thsx-num">{num(b.so_luong_nhan)} {b.don_vi}</b></div>
          <div className="thsx-x-kv"><span>Đạt</span><b className="thsx-num">{num(b.so_luong_dat)}</b></div>
          <div className="thsx-x-kv"><span>Không đạt</span><b className="thsx-num">{num(b.so_luong_khong_dat)}</b></div>
          {b.co_mau != null && b.co_mau > 0 && (
            <div className="thsx-x-kv"><span>Có mẫu</span><b className="thsx-num">{num(b.co_mau)}</b></div>
          )}
          {b.ghi_chu && <div className="thsx-x-kv"><span>Ghi chú</span><span>{b.ghi_chu}</span></div>}

          <div className="thsx-x-pb">
            <div className="thsx-x-pb__h">
              <Icon name="alert" size={13} />
              <span className="thsx-x-pb__ttl">Lỗi ({b.loi.length})</span>
              <span className="thsx-x-item__spacer" />
              {canAssign && (
                <Button variant="ghost" onClick={() => setLoiOpen((o) => !o)} disabled={busy} aria-expanded={loiOpen}>
                  <Icon name="plus" size={12} /> Ghi lỗi
                </Button>
              )}
            </div>
            {loiOpen && (
              <KcsLoiForm batch={b} busy={busy} loadLyDo={loadLyDo}
                toChiuOpts={toChiuOpts} congDoanRefOpts={congDoanRefOpts}
                onXong={() => setLoiOpen(false)} exec={exec} />
            )}
            {b.loi.length === 0 ? (
              <p className="thsx-x-pb__none">Chưa ghi lỗi nào.</p>
            ) : (
              <ul className="thsx-x-loilist">
                {b.loi.map((l) => (
                  <KcsLoiRow key={l.id} loi={l} canAssign={canAssign} busy={busy} exec={exec} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function KcsLoiForm({
  batch, busy, loadLyDo, toChiuOpts, congDoanRefOpts, onXong, exec,
}: {
  batch: SxKcsBatchChiTiet; busy: boolean; loadLyDo: (nhom: string) => Promise<SxLyDo[]>;
  toChiuOpts: Opt[]; congDoanRefOpts: Opt[]; onXong: () => void; exec: ThsxExec;
}) {
  const [nhomLoiId, setNhomLoiId] = useState<number | null>(null);
  const [soLuong, setSoLuong] = useState("");
  const [moTa, setMoTa] = useState("");
  const [toChiu, setToChiu] = useState<number | null>(null);
  const [congDoanRef, setCongDoanRef] = useState<number | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const hopLe = nhomLoiId != null && files.length >= 1;

  async function luu() {
    if (await exec.ghiLoiKcs(batch.id, {
      nhom_loi_id: nhomLoiId!,
      to_chiu_id: toChiu,
      cong_doan_ref_id: congDoanRef,
      so_luong: toNum(soLuong),
      mo_ta: moTa.trim() || null,
      don_vi: batch.don_vi || null,
      files,
    })) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <div className="thsx-x-grid2">
        <Field label="Nhóm lỗi">
          <LyDoSelect nhom="loi" loadLyDo={loadLyDo} value={nhomLoiId} onChange={setNhomLoiId} />
        </Field>
        <Field label={`Số lượng${batch.don_vi ? ` (${batch.don_vi})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in" value={soLuong} onChange={(e) => setSoLuong(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Tổ chịu trách nhiệm">
          <select className="thsx-x-sel" value={toChiu ?? ""} onChange={(e) => setToChiu(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— Không chỉ định —</option>
            {toChiuOpts.map((o) => <option key={o.id} value={o.id}>{o.ten}</option>)}
          </select>
        </Field>
        <Field label="Công đoạn liên đới">
          <select className="thsx-x-sel" value={congDoanRef ?? ""} onChange={(e) => setCongDoanRef(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— Không chỉ định —</option>
            {congDoanRefOpts.map((o) => <option key={o.id} value={o.id}>{o.ten}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Mô tả lỗi">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)} placeholder="mô tả ngắn (tuỳ chọn)" />
      </Field>
      <label className="thsx-x-fld">
        <span className="thsx-x-fld__l">Ảnh bằng chứng (bắt buộc ≥1)</span>
        <input type="file" accept="image/*" multiple className="thsx-x-file"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      </label>
      {files.length > 0 && <p className="thsx-x-hint">Đã chọn <b>{files.length}</b> ảnh.</p>}
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Ghi lỗi
        </Button>
      </div>
      {!hopLe && <p className="thsx-x-hint">Cần chọn nhóm lỗi và ít nhất một ảnh.</p>}
    </div>
  );
}

function KcsLoiRow({
  loi, canAssign, busy, exec,
}: {
  loi: SxKcsLoi; canAssign: boolean; busy: boolean; exec: ThsxExec;
}) {
  const chuaTraLoi = loi.trang_thai === "pending";
  return (
    <li className="thsx-x-loi">
      <div className="thsx-x-loi__h">
        <span className="thsx-x-loi__ten">{loi.nhom_loi_ten ?? "Lỗi"}</span>
        {loi.so_luong > 0 && (
          <span className="thsx-x-loi__q thsx-num">{num(loi.so_luong)}{loi.don_vi ? ` ${loi.don_vi}` : ""}</span>
        )}
        <span className="thsx-x-item__spacer" />
        <Pill map={LOI_TT} k={loi.trang_thai} />
      </div>
      {loi.mo_ta && <p className="thsx-x-loi__mo">{loi.mo_ta}</p>}
      {loi.trang_thai === "rejected" && loi.ly_do_tu_choi && (
        <p className="thsx-x-loi__reject"><Icon name="x" size={12} /> Tổ từ chối: “{loi.ly_do_tu_choi}”</p>
      )}
      <AnhLuoi anh={loi.anh} canAssign={canAssign && chuaTraLoi} busy={busy} loiId={loi.id} exec={exec} />
    </li>
  );
}

function AnhLuoi({
  anh, canAssign, busy, loiId, exec,
}: {
  anh: SxKcsAnh[]; canAssign: boolean; busy: boolean; loiId: number; exec: ThsxExec;
}) {
  return (
    <div className="thsx-x-anh">
      {anh.map((a) => (
        <div key={a.id} className="thsx-x-anh__it">
          <a href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer" title={a.file_name}>
            <img src={assetUrl(a.file_url) ?? ""} alt={a.file_name} loading="lazy" />
          </a>
          {canAssign && (
            <button type="button" className="thsx-x-anh__del" disabled={busy || anh.length <= 1}
              title={anh.length <= 1 ? "Phải giữ ít nhất một ảnh" : "Xoá ảnh"}
              onClick={() => void exec.xoaAnhKcs(a.id)}>
              <Icon name="x" size={11} />
            </button>
          )}
        </div>
      ))}
      {canAssign && (
        <label className="thsx-x-anh__add" title="Thêm ảnh">
          <Icon name="camera" size={15} />
          <input type="file" accept="image/*" multiple hidden disabled={busy}
            onChange={(e) => {
              const fs = Array.from(e.target.files ?? []);
              if (fs.length) void exec.themAnhLoiKcs(loiId, fs);
              e.target.value = "";
            }} />
        </label>
      )}
    </div>
  );
}

// ════════════════════════════ KHO §14 (panel drawer) ════════════════════════
export function ThsxKhoPanel({
  chiTiet, kho, kcsBatches, canAssign, busy, exec,
}: {
  chiTiet: SxWorkItemChiTiet;
  kho: SxKhoChiTiet | null;
  kcsBatches: SxKcsBatchChiTiet[];
  canAssign: boolean;
  busy: boolean;
  exec: ThsxExec;
}) {
  const cv = chiTiet.cong_viec;
  const [ncOpen, setNcOpen] = useState(false);
  const [plOpen, setPlOpen] = useState(false);
  // Nguồn tạo yêu cầu nhập: mẻ KCS có số đạt > 0.
  const datBatches = kcsBatches.filter((b) => b.so_luong_dat > 0);
  const slBatches = chiTiet.san_luong.batches;

  return (
    <section className="thsx-psec thsx-x thsx-x-kho">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="warehouse" size={13} /> Kho thành phẩm / BTP</span>
      </div>

      {/* Nhập kho thành phẩm */}
      <div className="thsx-x-sub">Nhập kho thành phẩm</div>
      {canAssign && (
        <div className="thsx-x-pb--empty">
          <span className="thsx-x-pb__none">Tạo yêu cầu nhập từ một mẻ đã đạt KCS.</span>
          <Button variant="ghost" onClick={() => setNcOpen((o) => !o)}
            disabled={busy || datBatches.length === 0} aria-expanded={ncOpen}>
            <Icon name="plus" size={12} /> Tạo yêu cầu
          </Button>
        </div>
      )}
      {ncOpen && (
        <YeuCauNhapForm batches={datBatches} busy={busy} onXong={() => setNcOpen(false)} exec={exec} />
      )}
      {kho == null ? (
        <p className="thsx-note">Đang tải…</p>
      ) : kho.yeu_cau.length === 0 ? (
        <p className="thsx-x-pb__none">Chưa có yêu cầu nhập kho.</p>
      ) : (
        <ul className="thsx-x-list">
          {kho.yeu_cau.map((yc) => (
            <YeuCauRow key={yc.id} yc={yc} canAssign={canAssign} busy={busy} exec={exec} />
          ))}
        </ul>
      )}

      {/* Phân loại BTP dư */}
      <div className="thsx-x-sub">BTP dư</div>
      {canAssign && (
        <div className="thsx-x-pb--empty">
          <span className="thsx-x-pb__none">Phân loại phần bán thành phẩm còn dư.</span>
          <Button variant="ghost" onClick={() => setPlOpen((o) => !o)} disabled={busy} aria-expanded={plOpen}>
            <Icon name="plus" size={12} /> Phân loại
          </Button>
        </div>
      )}
      {plOpen && (
        <PhanLoaiBtpForm cvId={cv.id} donVi={cv.don_vi_ra ?? cv.don_vi_vao ?? null}
          slBatches={slBatches} busy={busy} onXong={() => setPlOpen(false)} exec={exec} />
      )}
      {kho && kho.btp_tra_cho_kho.length > 0 && (
        <ul className="thsx-x-list">
          {kho.btp_tra_cho_kho.map((lot) => (
            <li key={lot.id} className="thsx-x-vt">
              <Icon name="box" size={15} className="thsx-x-vt__ic" />
              <span className="thsx-x-vt__ma">{PL_LABEL[lot.phan_loai ?? "nhap_btp"]}</span>
              <span className="thsx-num">{num(lot.so_luong)} {lot.don_vi}</span>
              <span className="thsx-x-item__spacer" />
              <span className="thsx-x-pill thsx-x-pill--wait">chờ kho nhận</span>
            </li>
          ))}
        </ul>
      )}

      {/* Lot đã nhập kho */}
      {kho && kho.lot.length > 0 && (
        <>
          <div className="thsx-x-sub">Đã nhập kho</div>
          <ul className="thsx-x-list">
            {kho.lot.map((lot) => (
              <li key={lot.id} className="thsx-x-vt">
                <Icon name="packageCheck" size={15} className={`thsx-x-vt__ic${lot.kho_xac_nhan ? " is-ok" : ""}`} />
                <span className="thsx-x-vt__ma">
                  {lot.loai_hang === "thanh_pham" ? "Thành phẩm" : PL_LABEL[lot.phan_loai ?? "nhap_btp"]}
                </span>
                <span className="thsx-num">{num(lot.so_luong)} {lot.don_vi}</span>
                {/* Kho ĐÃ NHẬN lot — trống ở mẫu lưu/phế và lot cũ trước khi có kho đích. */}
                {lot.kho_ten && <span className="thsx-x-vt__kho">tại {lot.kho_ten}</span>}
                <span className="thsx-x-item__spacer" />
                <span className={`thsx-x-pill ${lot.kho_xac_nhan ? "thsx-x-pill--ok" : "thsx-x-pill--wait"}`}>
                  {lot.kho_xac_nhan ? "kho đã nhận" : "chờ kho nhận"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function YeuCauNhapForm({
  batches, busy, onXong, exec,
}: {
  batches: SxKcsBatchChiTiet[]; busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const [batchId, setBatchId] = useState<number | null>(batches.length === 1 ? batches[0].id : null);
  const [soLuong, setSoLuong] = useState("");
  const [quyCach, setQuyCach] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const chon = batches.find((b) => b.id === batchId) ?? null;
  const nSl = toNum(soLuong);
  const hopLe = batchId != null && nSl > 0 && (!chon || nSl <= chon.so_luong_dat);

  async function luu() {
    if (await exec.taoYeuCauNhap({
      kcs_batch_id: batchId!, so_luong: nSl,
      quy_cach: quyCach.trim() || null, ghi_chu: ghiChu.trim() || null,
    })) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <Field label="Từ mẻ KCS đạt">
        <select className="thsx-x-sel" value={batchId ?? ""} onChange={(e) => setBatchId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Chọn mẻ —</option>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>{ngayGio(b.bat_dau)} · đạt {num(b.so_luong_dat)} {b.don_vi}</option>
          ))}
        </select>
      </Field>
      <div className="thsx-x-grid2">
        <Field label={`Số lượng${chon ? ` (≤ ${num(chon.so_luong_dat)})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in" value={soLuong} onChange={(e) => setSoLuong(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Quy cách">
          <input type="text" className="thsx-x-in" value={quyCach} onChange={(e) => setQuyCach(e.target.value)} placeholder="tuỳ chọn" />
        </Field>
      </div>
      <Field label="Ghi chú">
        <input type="text" className="thsx-x-in" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} placeholder="tuỳ chọn" />
      </Field>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="send" size={13} /> Gửi yêu cầu nhập
        </Button>
      </div>
    </div>
  );
}

function YeuCauRow({
  yc, canAssign, busy, exec,
}: {
  yc: SxNhapKhoYc; canAssign: boolean; busy: boolean; exec: ThsxExec;
}) {
  return (
    <li className="thsx-x-bg">
      <div className="thsx-x-bg__main">
        <Icon name="warehouse" size={15} className="thsx-x-bg__ic" />
        <span className="thsx-x-bg__q thsx-num">
          {num(yc.so_luong_xac_nhan)}/{num(yc.so_luong_yeu_cau)} {yc.don_vi}
        </span>
        <span className="thsx-x-item__spacer" />
        <Pill map={YC_TT} k={yc.trang_thai} />
      </div>
      <div className="thsx-x-bg__sub">
        {yc.con_lai > 0 && <span>còn <b className="thsx-num">{num(yc.con_lai)}</b> chưa nhận</span>}
        {yc.quy_cach && <span> · {yc.quy_cach}</span>}
        {canAssign && yc.con_lai > 0 && yc.trang_thai !== "huy" && (
          <button type="button" className="thsx-x-linkbtn" disabled={busy}
            onClick={() => void exec.huyPhanChuaNhan(yc.id, { expected_version: yc.version })}>
            Huỷ phần chưa nhận
          </button>
        )}
      </div>
    </li>
  );
}

function PhanLoaiBtpForm({
  cvId, donVi, slBatches, busy, onXong, exec,
}: {
  cvId: number; donVi: string | null; slBatches: SxWorkItemChiTiet["san_luong"]["batches"];
  busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const [soLuong, setSoLuong] = useState("");
  const [phanLoai, setPhanLoai] = useState<SxPhanLoaiBtp>("nhap_btp");
  const [quyCach, setQuyCach] = useState("");
  const [nguonBatch, setNguonBatch] = useState<number | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const nSl = toNum(soLuong);
  const hopLe = nSl > 0;

  async function luu() {
    if (await exec.phanLoaiBtp({
      cong_viec_id: cvId, so_luong: nSl, phan_loai: phanLoai,
      quy_cach: quyCach.trim() || null, nguon_batch_id: nguonBatch, ghi_chu: ghiChu.trim() || null,
    })) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <div className="thsx-x-seg" role="group" aria-label="Phân loại BTP dư">
        {(["nhap_btp", "mau_luu", "phe"] as SxPhanLoaiBtp[]).map((k) => (
          <button key={k} type="button" className="thsx-x-seg__btn" aria-pressed={phanLoai === k}
            onClick={() => setPhanLoai(k)}>{PL_LABEL[k]}</button>
        ))}
      </div>
      <div className="thsx-x-grid2">
        <Field label={`Số lượng${donVi ? ` (${donVi})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in" value={soLuong} onChange={(e) => setSoLuong(e.target.value)} placeholder="0" />
        </Field>
        <Field label="Quy cách">
          <input type="text" className="thsx-x-in" value={quyCach} onChange={(e) => setQuyCach(e.target.value)} placeholder="tuỳ chọn" />
        </Field>
      </div>
      {slBatches.length > 0 && (
        <Field label="Từ mẻ sản lượng (tuỳ chọn)">
          <select className="thsx-x-sel" value={nguonBatch ?? ""} onChange={(e) => setNguonBatch(e.target.value ? Number(e.target.value) : null)}>
            <option value="">— Không chỉ định —</option>
            {slBatches.map((b) => (
              <option key={b.id} value={b.id}>{ngayGio(b.bat_dau)} · tốt {num(b.tot)}</option>
            ))}
          </select>
        </Field>
      )}
      <Field label="Ghi chú">
        <input type="text" className="thsx-x-in" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} placeholder="tuỳ chọn" />
      </Field>
      {phanLoai === "nhap_btp" && (
        <p className="thsx-x-hint">Phần “nhập kho BTP” sẽ vào hộp thư kho chờ xác nhận nhận.</p>
      )}
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Ghi phân loại
        </Button>
      </div>
    </div>
  );
}

// ══════════════════════ ĐÓNG NHÓM §16 / §13.3 (panel drawer) ═════════════════
export function ThsxDongNhomPanel({
  dieuKien, canAssign, busy, loadLyDo, exec,
}: {
  dieuKien: SxDongNhomDieuKien | null;
  canAssign: boolean;
  busy: boolean;
  loadLyDo: (nhom: string) => Promise<SxLyDo[]>;
  exec: ThsxExec;
}) {
  const [dongOpen, setDongOpen] = useState(false);
  const [lyDoId, setLyDoId] = useState<number | null>(null);

  if (dieuKien == null) {
    return (
      <section className="thsx-psec thsx-x">
        <div className="thsx-psec__h"><span className="thsx-psec__title"><Icon name="packageCheck" size={13} /> Đóng nhóm thành phẩm</span></div>
        <p className="thsx-note">Đang tải điều kiện đóng…</p>
      </section>
    );
  }

  const daDong = dieuKien.trang_thai === "closed_full" || dieuKien.trang_thai === "closed_short";

  async function dong() {
    if (lyDoId == null) return;
    if (await exec.dongThieu(dieuKien!.nhom_id, { ly_do_id: lyDoId, expected_version: dieuKien!.version })) {
      setDongOpen(false); setLyDoId(null);
    }
  }

  return (
    <section className="thsx-psec thsx-x thsx-x-dong">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="packageCheck" size={13} /> Đóng nhóm thành phẩm</span>
        <Pill map={NHOM_TT} k={dieuKien.trang_thai} />
      </div>

      <ul className="thsx-x-check">
        {dieuKien.dieu_kien.map((d) => (
          <li key={d.ma} className={`thsx-x-check__it${d.dat ? " is-ok" : ""}`}>
            <Icon name={d.dat ? "check" : "clock"} size={14} />
            <span className="thsx-x-check__ten">{d.ten}</span>
            {!d.dat && d.chi_tiet && <span className="thsx-x-check__ct">{d.chi_tiet}</span>}
          </li>
        ))}
      </ul>

      {daDong ? (
        <p className="thsx-note thsx-note--ok">
          <Icon name="check" size={13} /> Nhóm đã {dieuKien.trang_thai === "closed_full" ? "đóng đủ" : "đóng thiếu"}.
        </p>
      ) : dieuKien.du_dong_du ? (
        <p className="thsx-note thsx-note--ok">
          <Icon name="check" size={13} /> Đủ điều kiện — nhóm tự đóng khi công việc cuối hoàn tất.
        </p>
      ) : (
        <>
          <p className="thsx-note">
            {dieuKien.du_dong_thieu
              ? "Còn việc chưa xong nhưng các điều kiện toàn vẹn đã sạch — có thể đóng thiếu."
              : "Chưa đủ điều kiện đóng. Xử lý các mục còn thiếu ở trên."}
          </p>
          {canAssign && dieuKien.du_dong_thieu && (
            !dongOpen ? (
              <div className="thsx-x-act thsx-x-act--row">
                <Button variant="secondary" onClick={() => setDongOpen(true)} disabled={busy}>
                  <Icon name="packageCheck" size={13} /> Đóng thiếu nhóm
                </Button>
              </div>
            ) : (
              <div className="thsx-x-form thsx-x-form--sub">
                <Field label="Lý do đóng thiếu">
                  <LyDoSelect nhom="dong_thieu" loadLyDo={loadLyDo} value={lyDoId} onChange={setLyDoId} />
                </Field>
                <p className="thsx-x-hint">Đóng thiếu sẽ báo ngay cho Sale và Kế hoạch SX.</p>
                <div className="thsx-x-act">
                  <Button variant="ghost" onClick={() => { setDongOpen(false); setLyDoId(null); }} disabled={busy}>Huỷ</Button>
                  <Button variant="accent" onClick={dong} disabled={busy || lyDoId == null}>
                    <Icon name="check" size={13} /> Xác nhận đóng thiếu
                  </Button>
                </div>
              </div>
            )
          )}
        </>
      )}
    </section>
  );
}

// ════════════════════════════ HỘP THƯ (mức trang) ═══════════════════════════
export function ThsxHopThuBar({
  kcsItems, khoHopThu, khoOpts, canKhoRead, canKhoCreate, busy,
  onPhanHoiLoi, onKhoXacNhanNhap, onKhoXacNhanBtp,
}: {
  kcsItems: SxKcsLoi[];
  khoHopThu: SxKhoHopThu | null;
  /** Kho ĐÍCH chọn được (danh mục kho đang dùng) — rỗng nghĩa là chưa khai kho nào. */
  /** `null` = chưa đọc được danh mục kho; `[]` = danh mục rỗng thật. */
  khoOpts: Opt[] | null;
  canKhoRead: boolean;
  canKhoCreate: boolean;
  busy: boolean;
  onPhanHoiLoi: (loiId: number, chapNhan: boolean, lyDo: string | null, version: number) => void;
  onKhoXacNhanNhap: (ycId: number, soLuong: number, khoId: number, version: number) => void;
  onKhoXacNhanBtp: (lotId: number) => void;
}) {
  const khoN = canKhoRead
    ? (khoHopThu?.yeu_cau_nhap.length ?? 0) + (khoHopThu?.btp_cho_nhan.length ?? 0)
    : 0;
  if (kcsItems.length === 0 && khoN === 0) return null;

  return (
    <div className="thsx-hopthu">
      {kcsItems.length > 0 && (
        <div className="thsx-hopthu__col">
          <div className="thsx-hopthu__h">
            <Icon name="shield" size={14} />
            <span>Lỗi KCS chờ tổ bạn phản hồi</span>
            <span className="thsx-hopthu__n thsx-num">{kcsItems.length}</span>
          </div>
          <ul className="thsx-hopthu__list">
            {kcsItems.map((l) => <KcsHopThuRow key={l.id} loi={l} busy={busy} onPhanHoi={onPhanHoiLoi} />)}
          </ul>
        </div>
      )}
      {canKhoRead && khoN > 0 && (
        <div className="thsx-hopthu__col">
          <div className="thsx-hopthu__h">
            <Icon name="warehouse" size={14} />
            <span>Kho chờ xác nhận</span>
            <span className="thsx-hopthu__n thsx-num">{khoN}</span>
          </div>
          <ul className="thsx-hopthu__list">
            {(khoHopThu?.yeu_cau_nhap ?? []).map((yc) => (
              <KhoNhapHopThuRow key={`yc${yc.id}`} yc={yc} khoOpts={khoOpts}
                canCreate={canKhoCreate} busy={busy} onXacNhan={onKhoXacNhanNhap} />
            ))}
            {(khoHopThu?.btp_cho_nhan ?? []).map((lot) => (
              <KhoBtpHopThuRow key={`lot${lot.id}`} lot={lot} canCreate={canKhoCreate} busy={busy} onXacNhan={onKhoXacNhanBtp} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function KcsHopThuRow({
  loi, busy, onPhanHoi,
}: {
  loi: SxKcsLoi; busy: boolean;
  onPhanHoi: (loiId: number, chapNhan: boolean, lyDo: string | null, version: number) => void;
}) {
  const [tuChoiMo, setTuChoiMo] = useState(false);
  const [lyDo, setLyDo] = useState("");
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <span className="thsx-hopthu__ten">{loi.nhom_loi_ten ?? "Lỗi"}</span>
        {loi.so_luong > 0 && <span className="thsx-num">{num(loi.so_luong)}{loi.don_vi ? ` ${loi.don_vi}` : ""}</span>}
      </div>
      {loi.mo_ta && <p className="thsx-hopthu__mo">{loi.mo_ta}</p>}
      {loi.anh.length > 0 && (
        <div className="thsx-x-anh">
          {loi.anh.map((a) => (
            <a key={a.id} className="thsx-x-anh__it" href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer" title={a.file_name}>
              <img src={assetUrl(a.file_url) ?? ""} alt={a.file_name} loading="lazy" />
            </a>
          ))}
        </div>
      )}
      {!tuChoiMo ? (
        <div className="thsx-x-act thsx-x-act--row">
          <Button variant="ghost" onClick={() => setTuChoiMo(true)} disabled={busy}>
            <Icon name="x" size={12} /> Từ chối
          </Button>
          <Button variant="accent" onClick={() => onPhanHoi(loi.id, true, null, loi.version)} disabled={busy}>
            <Icon name="check" size={13} /> Nhận trách nhiệm
          </Button>
        </div>
      ) : (
        <div className="thsx-x-form thsx-x-form--sub">
          <Field label="Lý do từ chối">
            <input type="text" className="thsx-x-in" value={lyDo} onChange={(e) => setLyDo(e.target.value)} placeholder="vì sao không nhận lỗi này?" autoFocus />
          </Field>
          <div className="thsx-x-act">
            <Button variant="ghost" onClick={() => { setTuChoiMo(false); setLyDo(""); }} disabled={busy}>Huỷ</Button>
            <Button variant="accent" onClick={() => onPhanHoi(loi.id, false, lyDo.trim() || null, loi.version)}
              disabled={busy || lyDo.trim() === ""}>
              <Icon name="check" size={13} /> Gửi từ chối
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function KhoNhapHopThuRow({
  yc, khoOpts, canCreate, busy, onXacNhan,
}: {
  yc: SxNhapKhoYc; khoOpts: Opt[] | null; canCreate: boolean; busy: boolean;
  onXacNhan: (ycId: number, soLuong: number, khoId: number, version: number) => void;
}) {
  const [sl, setSl] = useState(String(yc.con_lai));
  // KHO ĐÍCH bắt buộc, KHÔNG mặc định ngầm kể cả khi danh mục chỉ có một kho: hàng cất sai chỗ mà
  // hệ thống vẫn báo "đã nhập" là thứ không ai phát hiện ra cho tới lúc đi tìm hàng.
  const [khoId, setKhoId] = useState<number | null>(null);
  // Xác nhận MỘT PHẦN xong thì `version`/`con_lai` của yêu cầu đổi, nhưng hàng này KHÔNG remount
  // (key bám `yc.id`). Phải tự dọn: trả ô kho về "chưa chọn" — giữ lại kho lần trước chính là
  // "mặc định ngầm" mà luật cấm, phần còn lại rất hay cất chỗ khác — và đưa ô số về số còn lại mới.
  useEffect(() => {
    setKhoId(null);
    setSl(String(yc.con_lai));
  }, [yc.version, yc.con_lai]);
  const nSl = toNum(sl);
  const soHopLe = nSl > 0 && nSl <= yc.con_lai;
  const hopLe = soHopLe && khoId != null;
  const chuaDocDuocKho = khoOpts == null;
  const khoRong = khoOpts != null && khoOpts.length === 0;
  // Vì sao nút chưa bấm được — nói thẳng, không để nút câm. Tách "chưa đọc được danh mục" khỏi
  // "danh mục rỗng": bảo thủ kho đi khai kho mới trong khi danh mục vẫn đủ kho là chỉ sai đường.
  const vuong = chuaDocDuocKho
    ? "Chưa đọc được danh mục Kho — tải lại trang, còn lỗi thì báo quản trị."
    : khoRong ? "Chưa khai kho nào trong danh mục Kho — không có chỗ để nhập."
    : khoId == null ? "Chọn kho đích trước khi xác nhận."
    : !soHopLe ? `Số nhận phải lớn hơn 0 và không quá ${num(yc.con_lai)} ${yc.don_vi}.`
    : null;
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <Icon name="warehouse" size={14} />
        <span className="thsx-hopthu__ten">Nhập thành phẩm</span>
        <span className="thsx-num">còn {num(yc.con_lai)}/{num(yc.so_luong_yeu_cau)} {yc.don_vi}</span>
      </div>
      {yc.quy_cach && <p className="thsx-hopthu__mo">{yc.quy_cach}</p>}
      {yc.kho_ten && <p className="thsx-hopthu__mo">KCS đề nghị kho: {yc.kho_ten}</p>}
      {canCreate ? (
        <>
          <div className="thsx-x-act thsx-x-act--row thsx-hopthu__xn">
            <select className="thsx-x-sel" value={khoId ?? ""} aria-label="Kho đích"
              disabled={busy || chuaDocDuocKho || khoRong}
              onChange={(e) => setKhoId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">— Chọn kho đích —</option>
              {(khoOpts ?? []).map((k) => <option key={k.id} value={k.id}>{k.ten}</option>)}
            </select>
            <input type="number" min={0} max={yc.con_lai} className="thsx-x-in" value={sl}
              onChange={(e) => setSl(e.target.value)} aria-label="Số lượng nhận" />
            <Button variant="accent" onClick={() => onXacNhan(yc.id, nSl, khoId!, yc.version)}
              disabled={busy || !hopLe}>
              <Icon name="packageCheck" size={13} /> Xác nhận nhập
            </Button>
          </div>
          {vuong && <p className="thsx-x-hint">{vuong}</p>}
        </>
      ) : (
        <p className="thsx-hopthu__mo">Chỉ nhân viên kho mới xác nhận nhập.</p>
      )}
    </li>
  );
}

function KhoBtpHopThuRow({
  lot, canCreate, busy, onXacNhan,
}: {
  lot: SxKhoLot; canCreate: boolean; busy: boolean; onXacNhan: (lotId: number) => void;
}) {
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <Icon name="box" size={14} />
        <span className="thsx-hopthu__ten">Nhận BTP</span>
        <span className="thsx-num">{num(lot.so_luong)} {lot.don_vi}</span>
      </div>
      {lot.quy_cach && <p className="thsx-hopthu__mo">{lot.quy_cach}</p>}
      {canCreate ? (
        <div className="thsx-x-act thsx-x-act--row">
          <Button variant="accent" onClick={() => onXacNhan(lot.id)} disabled={busy}>
            <Icon name="packageCheck" size={13} /> Xác nhận nhận BTP
          </Button>
        </div>
      ) : (
        <p className="thsx-hopthu__mo">Chỉ nhân viên kho mới xác nhận nhận.</p>
      )}
    </li>
  );
}
