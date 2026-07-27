// Bảng ROUTING của lệnh — kế thừa từ bài tính giá nhưng SỬA ĐƯỢC tại lệnh. Lưu = REPLACE-ALL,
// không đụng phiếu tính giá và không ảnh hưởng lệnh khác.
//
// Bảng cố tình chỉ giữ 7 cột — phần QUYẾT ĐỊNH: bước nào · ai làm · vào ra bao nhiêu · mất bao lâu.
// Phần KHAI BÁO (2 đơn vị + hệ số, 5 loại thời gian, số nhân công, điều kiện, 10 ô gia công ngoài)
// nằm trong drawer từng bước. Nhồi ~20 ô vào bảng thì mỗi ô còn ~60px và phải cuộn ngang liên tục.
//
// Máy CHỈ ĐỀ XUẤT: số gợi ý nằm ở placeholder + nút 1-click, KHÔNG tự ghi vào ô. Các kiểm tra
// (ra > vào, chưa gán tổ, thuê ngoài thiếu NCC, đứt chuyền) chỉ TÔ MÀU, không chặn lưu — phán đoán
// nghề để người kế hoạch quyết.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  LSX_DON_VI_LABELS,
  LSX_LOAI_BUOC_META,
  type LsxBuocMacDinh,
  type LsxCongDoan,
  type LsxCongDoanBody,
  type LsxLeadTime,
  type LsxTinhNguocRow,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { LsxBuocDrawer } from "./LsxBuocDrawer";
import { ChuoiCongDoan, ngay, num } from "./keHoachSxShared";
import {
  type EditRow,
  emptyRow,
  n,
  phut,
  thoiLuong,
  toBody,
  toEdit,
} from "./lsxBuoc";

export interface RefRow {
  id: number;
  ten: string;
}

/** Lỗi/nghi vấn của RIÊNG 1 dòng — chỉ tô màu, không chặn lưu. */
function loiDong(rows: EditRow[], i: number): string[] {
  const r = rows[i];
  const out: string[] = [];
  const vao = n(r.so_luong_vao);
  const ra = n(r.so_luong_ra);
  if (r.don_vi_vao === r.don_vi_ra && vao > 0 && ra > vao) out.push("ra nhiều hơn vào");
  if (r.don_vi_vao !== r.don_vi_ra && n(r.he_so_quy_doi) <= 1) out.push("thiếu hệ số quy đổi");
  if (r.loai_buoc === "thue_ngoai") {
    if (!r.nha_cung_cap.trim()) out.push("chưa có nhà gia công");
    if (!r.ngay_gui_dk || !r.ngay_nhan_dk) out.push("chưa có ngày gửi / nhận");
  } else if (r.loai_buoc !== "cho" && r.department_id == null && r.may_id == null) {
    out.push("chưa gán tổ / máy");
  }
  if (i > 0) {
    const truoc = rows[i - 1];
    const raTruoc = n(truoc.so_luong_ra);
    if (truoc.don_vi_ra === r.don_vi_vao && raTruoc > 0 && vao > raTruoc) out.push("đứt chuyền");
  }
  if (i > 0 && r.ten && rows[i - 1].ten === r.ten) out.push("trùng bước trước");
  return out;
}

export function LsxRoutingTable({
  congDoans,
  soToKeHoach,
  soLuongDat,
  soCon,
  leadTime,
  congDoanRefs,
  toRefs,
  mayRefs,
  canUpdate,
  saving,
  onSave,
  onTinhNguoc,
  onMacDinhBuoc,
  onDirtyChange,
}: {
  congDoans: LsxCongDoan[];
  soToKeHoach: number;
  soLuongDat: number;
  soCon: number;
  leadTime: LsxLeadTime | null;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  canUpdate: boolean;
  saving: boolean;
  onSave: (body: LsxCongDoanBody[], lyDo?: string) => void;
  onTinhNguoc: () => Promise<LsxTinhNguocRow[]>;
  onMacDinhBuoc: (congDoanId: number) => Promise<LsxBuocMacDinh>;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [rows, setRows] = useState<EditRow[]>(() => congDoans.map(toEdit));
  const [undo, setUndo] = useState<{ row: EditRow; at: number } | null>(null);
  const [live, setLive] = useState("");
  const [moBuoc, setMoBuoc] = useState<number | null>(null);
  const [keo, setKeo] = useState<number | null>(null);
  const [goiY, setGoiY] = useState<LsxTinhNguocRow[] | null>(null);
  const [dangTinh, setDangTinh] = useState(false);
  const [lyDo, setLyDo] = useState("");
  const goc = useRef(JSON.stringify(toBody(congDoans.map(toEdit))));
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  // Hàng đang mở drawer — đóng lại thì trả tiêu điểm về đúng hàng đó (nợ của lát trước).
  const hangMo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const fresh = congDoans.map(toEdit);
    setRows(fresh);
    goc.current = JSON.stringify(toBody(fresh));
    setGoiY(null);
  }, [congDoans]);

  const dirty = JSON.stringify(toBody(rows)) !== goc.current;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  // Dải "hoàn tác" tự tắt sau 6s — xoá dòng chưa lưu không cần hỏi han.
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 6000);
    return () => clearTimeout(t);
  }, [undo]);

  const patch = useCallback((key: string, p: Partial<EditRow>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...p } : r)));
  }, []);

  /** Đổi công đoạn của 1 bước → KÉO LẠI mặc định của công đoạn mới (loại bước · tổ · máy · đơn vị ·
   *  chuẩn bị · năng suất · vệ sinh).
   *
   *  Không làm việc này thì bước đổi xong vẫn đeo nguyên số của công đoạn CŨ — đổi "Dán hộp" (tổ,
   *  đếm con, 4.000 con/giờ) sang "Cán màng" (máy, đếm tờ) mà thời lượng và đơn vị vẫn của Dán hộp,
   *  chẳng cảnh báo gì.
   *
   *  GIỮ số lượng vào/ra: chúng thuộc CHUỖI (bước trước giao bao nhiêu thì bước này nhận bấy nhiêu),
   *  không thuộc công đoạn — lệch thì đã có cảnh báo "đứt chuyền" + nút Tính ngược.
   *  Luật suy loại bước/đơn vị nằm ở BACKEND, ở đây chỉ áp kết quả để hai nơi không trôi khỏi nhau. */
  const doiCongDoan = useCallback(
    async (key: string, id: number | null, tenHienTai: string) => {
      if (id == null) {
        patch(key, { cong_doan_id: null });
        return;
      }
      try {
        const m = await onMacDinhBuoc(id);
        patch(key, {
          cong_doan_id: m.cong_doan_id, ten: m.ten, nhom: m.nhom, loai_buoc: m.loai_buoc,
          department_id: m.department_id, may_id: m.may_id,
          don_vi_vao: m.don_vi_vao, don_vi_ra: m.don_vi_ra,
          he_so_quy_doi: m.he_so_quy_doi > 1 ? String(m.he_so_quy_doi) : "",
          setup_phut: m.setup_phut ? String(m.setup_phut) : "",
          nang_suat: m.nang_suat ? String(m.nang_suat) : "",
          don_vi_nang_suat: m.don_vi_nang_suat ?? "",
          ve_sinh_phut: m.ve_sinh_phut ? String(m.ve_sinh_phut) : "",
          chay_phut: "",   // bước mới ⇒ bỏ ghi đè cũ, để máy tính lại từ năng suất
        });
        setLive(`Đã đổi sang ${m.ten} và lấy lại số mặc định của công đoạn này`);
      } catch {
        // Mất mạng / không có quyền đọc danh mục → ít nhất vẫn đổi được tên, đừng chặn người dùng.
        patch(key, { cong_doan_id: id, ten: tenHienTai, department_id: null });
      }
    },
    [onMacDinhBuoc, patch],
  );

  function move(idx: number, delta: number) {
    doiCho(idx, idx + delta);
  }

  function doiCho(from: number, to: number) {
    setRows((prev) => {
      if (to < 0 || to >= prev.length || from === to) return prev;
      const next = [...prev];
      const [row] = next.splice(from, 1);
      next.splice(to, 0, row);
      setLive(`Đã chuyển ${row.ten || "công đoạn"} tới vị trí ${to + 1}`);
      return next;
    });
  }

  function remove(idx: number) {
    setRows((prev) => {
      const row = prev[idx];
      setUndo({ row, at: idx });
      setLive(`Đã bỏ ${row.ten || "công đoạn"}, có thể hoàn tác`);
      return prev.filter((_, i) => i !== idx);
    });
    setMoBuoc(null);
  }

  function hoanTac() {
    if (!undo) return;
    setRows((prev) => {
      const next = [...prev];
      next.splice(Math.min(undo.at, next.length), 0, undo.row);
      return next;
    });
    setUndo(null);
    setLive("Đã hoàn tác");
  }

  function them() {
    setRows((prev) => [...prev, emptyRow()]);
    setLive("Đã thêm công đoạn mới ở cuối");
    setTimeout(() => {
      const last = tbodyRef.current?.querySelector<HTMLElement>("tr:last-of-type .khsx-rt__open");
      last?.focus();
      last?.scrollIntoView({ block: "nearest" });
    }, 0);
  }

  async function tinhNguoc() {
    setDangTinh(true);
    try {
      setGoiY(await onTinhNguoc());
      setLive("Đã tính ngược — xem cột gợi ý rồi bấm áp dụng");
    } finally {
      setDangTinh(false);
    }
  }

  /** Máy ĐỀ XUẤT, người BẤM: chỉ khi bấm mới ghi số vào ô. */
  function apDungGoiY() {
    if (!goiY) return;
    setRows((prev) =>
      prev.map((r, i) => {
        const g = goiY[i];
        return g
          ? { ...r, so_luong_vao: String(g.so_luong_vao), so_luong_ra: String(g.so_luong_ra) }
          : r;
      }));
    setGoiY(null);
    setLive("Đã áp dụng số tính ngược cho cả chuỗi");
  }

  function moDrawer(i: number, el: HTMLElement | null) {
    hangMo.current = el;
    setMoBuoc(i);
  }

  function dongDrawer() {
    setMoBuoc(null);
    hangMo.current?.focus();
  }

  function onRowKeyDown(e: KeyboardEvent, idx: number) {
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(idx, e.key === "ArrowUp" ? -1 : 1);
    }
  }

  const flow = useMemo(
    () => rows.map((r) => ({ ten: r.ten || "…", loai_buoc: r.loai_buoc })),
    [rows],
  );
  const tong = useMemo(
    () => rows.reduce(
      (acc, r) => {
        const t = thoiLuong(r);
        return { chiemMay: acc.chiemMay + t.chiemMay, tong: acc.tong + t.tong };
      },
      { chiemMay: 0, tong: 0 },
    ),
    [rows],
  );
  const soNgay = tong.tong / 60 / 8;
  const conLai = leadTime?.ngay_con_lai ?? null;
  const treHan = conLai != null && soNgay > conLai;
  const soNgoai = rows.filter((r) => r.loai_buoc === "thue_ngoai").length;
  // Chỉ hỏi lý do khi routing đã khác CẤU TRÚC ban đầu (thêm/bớt/đổi thứ tự/đổi loại bước) —
  // sửa số lượng hay thời gian là việc thường ngày, hỏi lý do mỗi lần là phiền vô ích.
  const doiCauTruc = useMemo(() => {
    const van = (cd: { ten: string; loai_buoc: string }) => `${cd.ten}|${cd.loai_buoc}`;
    return JSON.stringify(congDoans.map(van)) !== JSON.stringify(rows.map(van));
  }, [congDoans, rows]);

  return (
    <div className="khsx-rt">
      <div className="khsx-rt__bar">
        <div>
          <h3 className="khsx-rt__title">Chuỗi công đoạn ({rows.length})</h3>
          <p className="khsx-rt__origin">kế thừa từ bài tính giá · sửa được tại lệnh này</p>
        </div>
        {canUpdate && (
          <div className="khsx-rt__baracts">
            <Button
              variant="ghost"
              disabled={rows.length === 0}
              loading={dangTinh}
              onClick={tinhNguoc}
              title="Chạy ngược từ số thành phẩm để ra số vào/ra từng bước"
            >
              <Icon name="workflow" size={14} /> Tính ngược từ SL thành phẩm
            </Button>
            <Button variant="secondary" onClick={them}>
              <Icon name="plus" size={14} /> Thêm công đoạn
            </Button>
            <Button
              variant="accent"
              disabled={!dirty}
              loading={saving}
              onClick={() => onSave(toBody(rows), doiCauTruc ? lyDo : undefined)}
            >
              Lưu công đoạn
            </Button>
          </div>
        )}
      </div>

      <div className="khsx-rt__flow">
        <ChuoiCongDoan steps={flow} />
      </div>

      {goiY && (
        <div className="khsx-goiy">
          <Icon name="help" size={15} />
          <p className="khsx-goiy__text">
            Đã chạy ngược từ <strong>{num(soLuongDat)}</strong> thành phẩm. Cột{" "}
            <em>gợi ý</em> trong bảng là số máy tính ra — chưa ghi vào đâu cả.
          </p>
          <div className="khsx-goiy__acts">
            <button type="button" className="khsx-xlink" onClick={() => setGoiY(null)}>
              Bỏ qua
            </button>
            <Button variant="primary" onClick={apDungGoiY}>Áp dụng cho cả chuỗi</Button>
          </div>
        </div>
      )}

      <div className="khsx__tablewrap">
        <table className="khsx-rt__table">
          <caption className="sr-only">
            Danh sách công đoạn của lệnh. Bấm một hàng để mở chi tiết bước.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="khsx-rt__thord">#</th>
              <th scope="col">Công đoạn</th>
              <th scope="col">Thực hiện</th>
              <th scope="col" className="khsx-th--num">Vào → Ra</th>
              <th scope="col" className="khsx-th--num">Thời lượng</th>
              <th scope="col">Cần xem lại</th>
              <th scope="col"><span className="sr-only">Thao tác</span></th>
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <div className="khsx-empty khsx-empty--inline">
                    <Icon name="workflow" size={32} />
                    <p className="khsx-empty__title">Chưa có công đoạn nào.</p>
                    <p className="khsx-empty__sub">
                      Bài tính giá không có công đoạn, hoặc đã xoá hết. Thêm ít nhất 1 công đoạn thì
                      lệnh mới sẵn sàng lập kế hoạch.
                    </p>
                    {canUpdate && (
                      <Button variant="secondary" onClick={them}>
                        <Icon name="plus" size={14} /> Thêm công đoạn
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const meta = LSX_LOAI_BUOC_META[r.loai_buoc];
              const t = thoiLuong(r);
              const loi = loiDong(rows, i);
              const g = goiY?.[i];
              const ngoai = r.loai_buoc === "thue_ngoai";
              const lamO = ngoai
                ? r.nha_cung_cap || "chưa có nhà gia công"
                : [toRefs?.find((x) => x.id === r.department_id)?.ten,
                   mayRefs?.find((x) => x.id === r.may_id)?.ten]
                    .filter(Boolean).join(" · ");
              return (
                <tr
                  key={r.key}
                  className={`khsx-rt__row khsx-rt__row--${meta.tone} ${keo === i ? "is-keo" : ""}`}
                  draggable={canUpdate}
                  onDragStart={() => setKeo(i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (keo != null) doiCho(keo, i);
                    setKeo(null);
                  }}
                  onDragEnd={() => setKeo(null)}
                  onKeyDown={(e) => onRowKeyDown(e, i)}
                >
                  <td>
                    <span className="khsx-rt__ord khsx-num">{(i + 1) * 10}</span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="khsx-rt__open"
                      onClick={(e) => moDrawer(i, e.currentTarget)}
                    >
                      <span className="khsx-rt__ten">{r.ten || "— chưa chọn công đoạn —"}</span>
                      <span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>
                      {!r.bat_buoc && <span className="khsx-lb khsx-lb--opt">tùy chọn</span>}
                    </button>
                  </td>
                  <td>
                    <span className={lamO ? "" : "khsx-muted"}>{lamO || "tổ mặc định"}</span>
                    {r.so_nhan_cong && n(r.so_nhan_cong) > 1 && (
                      <span className="khsx-rt__sub2">{r.so_nhan_cong} người</span>
                    )}
                  </td>
                  <td className="khsx-rt__qty">
                    <span className="khsx-num">{num(n(r.so_luong_vao))}</span>
                    <span className="khsx-rt__dv">{LSX_DON_VI_LABELS[r.don_vi_vao]}</span>
                    <span className="khsx-rt__arrow" aria-label="ra">→</span>
                    <span className="khsx-num">{num(n(r.so_luong_ra))}</span>
                    <span className="khsx-rt__dv">{LSX_DON_VI_LABELS[r.don_vi_ra]}</span>
                    {g && (g.so_luong_vao !== n(r.so_luong_vao)
                      || g.so_luong_ra !== n(r.so_luong_ra)) && (
                      <span className="khsx-rt__goiy">
                        gợi ý {num(g.so_luong_vao)} → {num(g.so_luong_ra)}
                      </span>
                    )}
                  </td>
                  <td className="khsx-rt__time">
                    <span className="khsx-dur">{phut(t.tong)}</span>
                    {t.tong !== t.chiemMay && (
                      <span className="khsx-rt__sub2">chiếm máy {phut(t.chiemMay)}</span>
                    )}
                  </td>
                  <td>
                    {loi.length === 0 ? (
                      <span className="khsx-muted">—</span>
                    ) : (
                      <span className="khsx-need-stack">
                        {loi.slice(0, 2).map((l) => (
                          <span key={l} className="khsx-need khsx-need--soft">
                            <Icon name="help" size={10} /> {l}
                          </span>
                        ))}
                        {loi.length > 2 && (
                          <span className="khsx-need khsx-need--more" title={loi.join(" · ")}>
                            +{loi.length - 2}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  {/* Không vẽ tay cầm kéo bằng ký tự ⠿: nó là glyph chữ lạc giữa bộ icon Lucide
                      của app. Cả hàng đã `cursor: grab` để kéo, còn đổi thứ tự vẫn làm được bằng
                      nút ▲▼ và Alt+↑↓ — rõ ràng hơn và dùng được bàn phím. */}
                  <td>
                    {canUpdate && (
                      <div className="khsx-rt__acts">
                        <button
                          type="button"
                          className="khsx-rt__btn khsx-rt__btn--up"
                          disabled={i === 0}
                          onClick={() => move(i, -1)}
                          aria-label={`Chuyển bước ${i + 1} lên`}
                        >
                          <Icon name="chevron" size={14} />
                        </button>
                        <button
                          type="button"
                          className="khsx-rt__btn"
                          disabled={i === rows.length - 1}
                          onClick={() => move(i, 1)}
                          aria-label={`Chuyển bước ${i + 1} xuống`}
                        >
                          <Icon name="chevron" size={14} />
                        </button>
                        <button
                          type="button"
                          className="khsx-rt__btn khsx-rt__btn--del"
                          onClick={() => remove(i)}
                          aria-label={`Bỏ bước ${i + 1}`}
                        >
                          <Icon name="trash" size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {undo && (
        <div className="khsx-rt__undo">
          <span>Đã bỏ “{undo.row.ten || "công đoạn"}”</span>
          <button type="button" className="khsx-xlink" onClick={hoanTac}>
            Hoàn tác
          </button>
        </div>
      )}

      {rows.length > 0 && (
        <div className={`khsx-lead ${treHan ? "khsx-lead--tre" : ""}`}>
          <div className="khsx-lead__main">
            <span className="khsx-lead__label">Tổng thời gian dẫn</span>
            <strong className="khsx-lead__val khsx-dur">{phut(tong.tong)}</strong>
            <span className="khsx-lead__note">
              ≈ {soNgay.toFixed(1)} ngày làm việc · chiếm máy {phut(tong.chiemMay)}
            </span>
          </div>
          <div className="khsx-lead__side">
            {leadTime?.ngay_du_kien_xong && !dirty && (
              <span>Dự kiến xong {ngay(leadTime.ngay_du_kien_xong)}</span>
            )}
            {conLai != null && (
              <span className={treHan ? "khsx-lead__warn" : ""}>
                {treHan
                  ? `Vượt hạn giao khách — chỉ còn ${conLai} ngày`
                  : `Còn ${conLai} ngày tới hạn giao khách`}
              </span>
            )}
            {soNgoai > 0 && <span>{soNgoai} bước thuê ngoài</span>}
          </div>
        </div>
      )}

      {canUpdate && doiCauTruc && (
        <label className="khsx-lydo">
          <span className="khsx-field__label">
            Routing đã khác bài tính giá — ghi lý do để lưu vào nhật ký
          </span>
          <input
            value={lyDo}
            placeholder="vd: khách đổi sang cán màng thuê ngoài"
            onChange={(e) => setLyDo(e.target.value)}
          />
        </label>
      )}

      <div className="khsx-rt__foot">
        <p className="khsx-rt__summary">
          {rows.length} công đoạn
          {soNgoai > 0 && ` · ${soNgoai} thuê ngoài`}
        </p>
        {canUpdate && (
          <Button
            variant="accent"
            disabled={!dirty}
            loading={saving}
            onClick={() => onSave(toBody(rows), doiCauTruc ? lyDo : undefined)}
          >
            Lưu công đoạn
          </Button>
        )}
      </div>

      <p className="sr-only" aria-live="polite">{live}</p>

      {moBuoc != null && rows[moBuoc] && (
        <LsxBuocDrawer
          row={rows[moBuoc]}
          index={moBuoc}
          tong={rows.length}
          soCon={soCon}
          soToKeHoach={soToKeHoach}
          soLuongDat={soLuongDat}
          congDoanRefs={congDoanRefs}
          toRefs={toRefs}
          mayRefs={mayRefs}
          canUpdate={canUpdate}
          onPatch={(p) => patch(rows[moBuoc].key, p)}
          onDoiCongDoan={(id) => doiCongDoan(rows[moBuoc].key, id, rows[moBuoc].ten)}
          onClose={dongDrawer}
          onPrev={() => setMoBuoc(Math.max(moBuoc - 1, 0))}
          onNext={() => setMoBuoc(Math.min(moBuoc + 1, rows.length - 1))}
        />
      )}
    </div>
  );
}
