// SỔ tài sản & công cụ dụng cụ — bảng tra cứu "xưởng đang có những gì, còn lại bao nhiêu".
//
// Tìm · lọc · phân trang đều Ở MÁY CHỦ. Kéo cả bảng về rồi `filter` trong JS thì qua trang thứ
// hai con số bắt đầu sai mà không có lỗi nào bật ra — đã bị bác đúng chuyện này ở màn khác.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Department } from "../../api/client";
import {
  NHAN_LOAI,
  NHAN_TRANG_THAI,
  taiSanApi,
  type TaiSanChiTiet,
  type TaiSanRow,
} from "../../api/taiSan";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Icon } from "../../components/Icons";
import { Pager, trangHopLe } from "../../components/Pager";
import { RowActionButton } from "../../components/RowActionButton";
import { useDebounced } from "../../utils/useDebounced";
import { Badge, ngay, tien } from "./chung";
import { BienDongDialog } from "./BienDongDialog";
import { ChiTietDialog } from "./ChiTietDialog";
import { GhiTangDialog } from "./GhiTangDialog";

const SIZE = 20;

export function DanhSachView() {
  const { token } = useAuth();
  const can = useCan();
  const taoDuoc = can("tai_san", "create");
  const suaDuoc = can("tai_san", "update");
  const xoaDuoc = can("tai_san", "delete");

  const [rows, setRows] = useState<TaiSanRow[]>([]);
  const [tong, setTong] = useState(0);
  const [page, setPage] = useState(1);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const qCham = useDebounced(q, 300);
  const [loai, setLoai] = useState("");
  const [boPhanLoc, setBoPhanLoc] = useState("");
  const [trangThai, setTrangThai] = useState("");

  const [boPhan, setBoPhan] = useState<Department[]>([]);
  const [moGhiTang, setMoGhiTang] = useState(false);
  const [dangSua, setDangSua] = useState<TaiSanChiTiet | null>(null);
  const [bienDong, setBienDong] = useState<TaiSanChiTiet | null>(null);
  // Bấm vào DÒNG là xem chi tiết + bảng khấu hao dự kiến (chủ 08/09/2026) — trước đây lịch chỉ
  // hiện đúng một lần ngay sau khi lưu phiếu.
  const [xem, setXem] = useState<TaiSanChiTiet | null>(null);
  const [xoa, setXoa] = useState<TaiSanRow | null>(null);
  const [dangXoa, setDangXoa] = useState(false);
  const [loiXoa, setLoiXoa] = useState<string | null>(null);

  // Máy chủ tính hao mòn tới hết tháng TRƯỚC (tháng đang chạy chưa hết thì chưa trích). Mốc ấy
  // chỉ nằm ở tooltip tiêu đề cột — chủ 08/09/2026 không muốn dòng "hết MM/YYYY" hiện ra bảng.
  const denThang = rows[0]?.luy_ke_den
    ? `${rows[0].luy_ke_den.slice(5, 7)}/${rows[0].luy_ke_den.slice(0, 4)}`
    : "";

  const nap = useCallback(() => {
    if (!token) return;
    setDangTai(true);
    setLoi(null);
    taiSanApi
      .danhSach(token, {
        q: qCham, loai, bo_phan_id: boPhanLoc, trang_thai: trangThai,
        offset: (page - 1) * SIZE, limit: SIZE,
      })
      .then((kq) => {
        setRows(kq.items);
        setTong(kq.total);
        // Xoá nốt dòng cuối trang 3 ⇒ trang đó rỗng trơn, người dùng tưởng mất sạch dữ liệu.
        const ve = trangHopLe(page, kq.total, SIZE);
        if (ve) setPage(ve);
      })
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không tải được sổ tài sản."))
      .finally(() => setDangTai(false));
  }, [token, qCham, loai, boPhanLoc, trangThai, page]);

  useEffect(() => { nap(); }, [nap]);

  useEffect(() => {
    if (!token) return;
    api.rbac.departments(token).then(setBoPhan).catch(() => setBoPhan([]));
  }, [token]);

  const doiLoc = (fn: () => void) => { fn(); setPage(1); };

  /** Cả ba ngăn kéo đều cần CHI TIẾT, không phải dòng bảng: form ghi tăng cần các dòng cấu
   *  thành nguyên giá, hộp biến động và ngăn xem cần lịch sử chứng từ — bảng chỉ có tổng. */
  async function moChiTiet(r: TaiSanRow, dich: "sua" | "bien-dong" | "xem") {
    if (!token) return;
    try {
      const ct = await taiSanApi.chiTiet(token, r.id);
      if (dich === "sua") setDangSua(ct);
      else if (dich === "xem") setXem(ct);
      else setBienDong(ct);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không mở được tài sản này.");
    }
  }

  async function xacNhanXoa() {
    if (!token || !xoa) return;
    setDangXoa(true);
    setLoiXoa(null);
    try {
      await taiSanApi.xoa(token, xoa.id);
      setXoa(null);
      nap();
    } catch (e) {
      setLoiXoa(e instanceof ApiError ? e.message : "Không xoá được.");
    } finally {
      setDangXoa(false);
    }
  }

  return (
    <>
      <div className="rc__unified-bar">
        <div className="rc__unified-right" style={{ marginLeft: "auto" }}>
          <div className="rc__search-wrapper">
            <Icon name="search" size={15} className="rc__search-icon" />
            <input className="rc__search" placeholder="Tìm theo mã hoặc tên…"
              value={q} onChange={(e) => doiLoc(() => setQ(e.target.value))} />
          </div>
          <select className="rc-input" value={loai} aria-label="Lọc theo loại"
            onChange={(e) => doiLoc(() => setLoai(e.target.value))}>
            <option value="">Mọi loại</option>
            <option value="tscd">{NHAN_LOAI.tscd}</option>
            <option value="ccdc">{NHAN_LOAI.ccdc}</option>
          </select>
          <select className="rc-input" value={boPhanLoc} aria-label="Lọc theo bộ phận"
            onChange={(e) => doiLoc(() => setBoPhanLoc(e.target.value))}>
            <option value="">Mọi bộ phận</option>
            {boPhan.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <select className="rc-input" value={trangThai} aria-label="Lọc theo trạng thái"
            onChange={(e) => doiLoc(() => setTrangThai(e.target.value))}>
            <option value="">Mọi trạng thái</option>
            <option value="dang_dung">{NHAN_TRANG_THAI.dang_dung}</option>
          </select>
          {taoDuoc && (
            <Button variant="accent" onClick={() => setMoGhiTang(true)}>
              <Icon name="plus" size={15} /> Ghi tăng
            </Button>
          )}
        </div>
      </div>

      {loi && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{loi}</span>
          <button type="button" className="btn btn--ghost" onClick={nap}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        {/* Chín cột, và cột Tên là cột người ta ĐỌC. Bề ngang phải khai đủ CẢ CHÍN: `.rc__table`
            là `table-layout: fixed`, cột nào không khai chỉ được phần thừa — trước đây Tên không
            khai nên nhận đúng 9% (89px trên màn 1280) và "Máy in Komori 4 màu (LS440)" rơi bốn
            dòng. Tổng đúng 100%; sàn 1180px để trên laptop 1366 các cột không bị bóp dưới bề
            ngang tối thiểu của chúng (badge loại 141px, cụm ba nút 124px) mà cuộn ngang. */}
        <table className="rc__table ts-table--so">
          <thead>
            <tr>
              <th style={{ width: "9%" }}>Mã</th>
              <th style={{ width: "20%" }} className="ts-col-ten">Tên</th>
              <th style={{ width: "12%" }}>Loại</th>
              <th style={{ width: "9%" }}>Bộ phận</th>
              <th style={{ width: "10%" }} className="ts-num">Nguyên giá</th>
              <th style={{ width: "10%" }} className="ts-num"
                title={denThang ? `Cộng dồn theo lịch tới hết tháng ${denThang}` : undefined}>
                Đã hao mòn
              </th>
              <th style={{ width: "10%" }} className="ts-num">Còn lại</th>
              <th style={{ width: "9%" }}>Trạng thái</th>
              <th style={{ width: "11%" }} className="text-center ts-actcol">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {dangTai ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: 9 }).map((__, j) => (
                    <td key={j}><span className="rc-skel" style={{ width: "70%" }} /></td>
                  ))}
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <p className="rc__empty-text">
                      {tong === 0 && !qCham && !loai && !boPhanLoc && !trangThai
                        ? "Sổ tài sản còn trống. Ghi tăng món đầu tiên, hoặc nạp số dư đầu kỳ cho những máy đã chạy từ trước."
                        : "Không có món nào khớp bộ lọc."}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="ts-row--xem" onClick={() => moChiTiet(r, "xem")}
                  title="Bấm để xem chi tiết và bảng khấu hao dự kiến">
                  <td><span className="rc__code-badge">{r.ma}</span></td>
                  <td className="ts-col-ten">
                    <div>{r.ten}</div>
                    <div className="ts-phu">
                      Dùng từ {ngay(r.ngay_su_dung)} · {r.so_thang} tháng
                      {r.so_luong > 1 ? ` · ${r.so_luong} cái` : ""}
                    </div>
                  </td>
                  <td><Badge he={r.loai}>{NHAN_LOAI[r.loai] ?? r.loai}</Badge></td>
                  <td className="rc__clip" title={r.bo_phan_ten ?? ""}>{r.bo_phan_ten ?? "—"}</td>
                  <td className="ts-num">{tien(r.nguyen_gia)}</td>
                  <td className="ts-num">{tien(r.hao_mon_luy_ke)}</td>
                  <td className={`ts-num ts-num--manh${r.con_lai <= 0 ? " ts-num--het" : ""}`}>
                    {tien(r.con_lai)}
                  </td>
                  <td>
                    <Badge he={r.trang_thai}>
                      {NHAN_TRANG_THAI[r.trang_thai] ?? r.trang_thai}
                    </Badge>
                    {r.ngay_giam && <div className="ts-phu">{ngay(r.ngay_giam)}</div>}
                  </td>
                  {/* Nút thao tác không được kéo theo ngăn xem — chặn nổi bọt lên <tr>. */}
                  <td className="text-center ts-actcol" onClick={(e) => e.stopPropagation()}>
                    <RowActionButton dense label="Sửa" icon="pencil"
                      disabled={!suaDuoc} onClick={() => moChiTiet(r, "sua")} />
                    <RowActionButton dense label="Biến động" icon="workflow"
                      disabled={!suaDuoc} onClick={() => moChiTiet(r, "bien-dong")} />
                    <RowActionButton dense danger label="Xoá" icon="trash"
                      disabled={!xoaDuoc} onClick={() => { setLoiXoa(null); setXoa(r); }} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pager total={tong} page={page} size={SIZE} onPage={setPage} loading={dangTai}
        unit="món" />

      {token && (moGhiTang || dangSua) && (
        <GhiTangDialog
          token={token}
          taiSan={dangSua}
          boPhan={boPhan}
          onClose={() => { setMoGhiTang(false); setDangSua(null); }}
          onSaved={nap}
        />
      )}

      {token && xem && (
        <ChiTietDialog token={token} taiSan={xem} onClose={() => setXem(null)} />
      )}

      {token && bienDong && (
        <BienDongDialog
          token={token}
          taiSan={bienDong}
          boPhan={boPhan}
          onClose={() => setBienDong(null)}
          onSaved={nap}
        />
      )}

      <ConfirmDialog
        open={xoa !== null}
        danger
        busy={dangXoa}
        error={loiXoa}
        title={`Xoá ${xoa?.ma ?? ""}?`}
        message={
          "Xoá là gỡ hẳn khỏi sổ: mất cả lịch sử điều chuyển / sửa chữa lớn và các tháng đã trích, "
          + "không hoàn lại được. Món đã bán, hỏng, không dùng nữa thì xoá."
        }
        confirmLabel="Xoá khỏi sổ"
        onConfirm={xacNhanXoa}
        onCancel={() => setXoa(null)}
      />
    </>
  );
}
