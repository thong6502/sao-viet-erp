// Danh mục "Tiêu chí KCS" — KHAI THEO CÂY, không phải bảng phẳng (08/09/2026, chủ chốt chốt:
// "chọn giai đoạn → chọn công đoạn → thêm hạng mục kiểm cho công đoạn, HẾT").
//
// Vì sao KHÔNG dùng nền `RebuildCatalogPage` như 12 màn danh mục kia: nền đó bày MỘT bảng phẳng,
// mỗi dòng một bản ghi. Ở đây đơn vị người dùng nghĩ tới là CÔNG ĐOẠN (một dòng của tờ ISO
// 9001-2015 treo ở xưởng), còn hạng mục kiểm là các gạch đầu dòng bên dưới nó — bày phẳng thì
// người khai phải tự nhớ mình đang khai cho công đoạn nào ở từng dòng.
//
// Ba tầng: Giai đoạn (`cong_doan.nhom`, 4 mã cố định) → Công đoạn → hạng mục kiểm.
// GIAI ĐOẠN KHÔNG phải bản ghi: nó là thuộc tính sẵn có của công đoạn, ở đây chỉ dùng để GOM
// nhóm khi đọc và để LỌC ô chọn khi thêm. Thêm "công đoạn cần kiểm" = khai hạng mục đầu tiên
// cho nó; xoá hạng mục cuối cùng thì công đoạn tự rời khỏi danh sách.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type CongDoanLite, type KcsHangMuc, type KcsKhaiBaoGiaiDoan,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { NHOM_CONG_DOAN } from "../keHoachSxShared";
import "../rebuild-catalog.css";
import "./kcs-khai-bao.css";

const MODULE = "dm_kcs_tieu_chi";

/** Form của MỘT hạng mục — dùng chung cho thêm mới và sửa.
 *  KHÔNG có ô "Thứ tự" và ô "Bắt buộc" (08/09/2026): tờ ISO của xưởng là một danh sách gạch đầu
 *  dòng — thứ tự chính là thứ tự khai (`thu_tu` tự đánh số ở đây), và mọi dòng đều phải tick nên
 *  `bat_buoc` luôn true. Hai ô đó chỉ bắt người khai trả lời hai câu hỏi mà họ không có ý kiến. */
interface FormState {
  id: number | null;
  cong_doan_id: number;
  ten: string;
  huong_dan: string;
  thu_tu: number;
}

function formRong(cong_doan_id: number, thu_tu: number): FormState {
  return { id: null, cong_doan_id, ten: "", huong_dan: "", thu_tu };
}

export function KcsKhaiBaoPage() {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can(MODULE, "update");
  const xoaDuoc = can(MODULE, "delete");

  const [giaiDoan, setGiaiDoan] = useState<KcsKhaiBaoGiaiDoan[] | null>(null);
  const [congDoanOpts, setCongDoanOpts] = useState<CongDoanLite[]>([]);
  const [loi, setLoi] = useState<string | null>(null);

  // Form đang mở: `null` = không mở cái nào. Mỗi lúc chỉ một form — màn này là khai báo, không
  // phải nhập liệu hàng loạt, mở nhiều ô cùng lúc chỉ làm lạc chỗ.
  const [form, setForm] = useState<FormState | null>(null);
  const [dangLuu, setDangLuu] = useState(false);

  // Khối "thêm công đoạn": chọn giai đoạn trước, ô công đoạn lọc theo giai đoạn đó.
  const [themNhom, setThemNhom] = useState<string>("");
  const [themCongDoanId, setThemCongDoanId] = useState<number | "">("");

  const tai = useCallback(() => {
    if (!token) return;
    setLoi(null);
    Promise.all([api.kcsHangMuc.khaiBao(token), api.congDoan.list(token)])
      .then(([kb, cd]) => {
        setGiaiDoan(kb.giai_doan);
        setCongDoanOpts(cd.items);
      })
      .catch((e) => {
        setGiaiDoan([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được danh mục.");
      });
  }, [token]);

  useEffect(() => { tai(); }, [tai]);

  const daKhai = useMemo(
    () => new Set((giaiDoan ?? []).flatMap((g) => g.cong_doan.map((c) => c.cong_doan_id))),
    [giaiDoan],
  );
  // Ô chọn công đoạn của khối "thêm": lọc theo giai đoạn đang chọn và BỎ công đoạn đã có mặt
  // trong cây (muốn thêm hạng mục cho nó thì bấm ngay trên thẻ của nó, đừng thêm lần hai).
  const congDoanChonDuoc = useMemo(
    () => congDoanOpts
      .filter((c) => (c.nhom ?? "") === themNhom && !daKhai.has(c.id))
      .sort((a, b) => a.ma.localeCompare(b.ma)),
    [congDoanOpts, themNhom, daKhai],
  );

  const soCongDoan = (giaiDoan ?? []).reduce((n, g) => n + g.cong_doan.length, 0);

  async function luu() {
    if (!token || !form) return;
    const ten = form.ten.trim();
    if (!ten) { setLoi("Nhập câu chữ hạng mục kiểm."); return; }
    setDangLuu(true);
    setLoi(null);
    try {
      const body = {
        cong_doan_id: form.cong_doan_id,
        ten,
        huong_dan: form.huong_dan.trim() || null,
        // Cột còn trong DB (bàn KCS đọc để chặn gửi khi còn dòng chưa chấm) nhưng KHÔNG còn là câu
        // hỏi cho người khai: mọi hạng mục trên tờ ISO đều phải tick.
        bat_buoc: true,
        thu_tu: form.thu_tu,
        active: true,
      };
      if (form.id == null) await api.kcsHangMuc.tao(token, body);
      else await api.kcsHangMuc.sua(token, form.id, body);
      setForm(null);
      setThemCongDoanId("");
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không lưu được hạng mục kiểm.");
    } finally {
      setDangLuu(false);
    }
  }

  async function xoa(h: KcsHangMuc) {
    if (!token) return;
    if (!window.confirm(`Xoá hạng mục “${h.ten}”?`)) return;
    setLoi(null);
    try {
      await api.kcsHangMuc.xoa(token, h.id);
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được hạng mục kiểm.");
    }
  }

  /** Form một hạng mục — đặt ngay dưới bảng của công đoạn đang khai, không dựng drawer: người
   *  khai cần NHÌN THẤY các hạng mục đã có để không viết lại cùng một ý. */
  function formHangMuc() {
    if (!form) return null;
    return (
      <div className="kkb-form">
        <label className="kkb-form__ten">
          <span>Hạng mục kiểm *</span>
          <input
            type="text" className="rc-input" autoFocus value={form.ten}
            placeholder="vd: Chồng màu đúng mẫu đã ký"
            onChange={(e) => setForm({ ...form, ten: e.target.value })}
          />
        </label>
        <label className="kkb-form__hd">
          <span>Hướng dẫn kiểm</span>
          <input
            type="text" className="rc-input" value={form.huong_dan}
            placeholder="vd: Soi dưới đèn D50, so với tờ mẫu khách ký"
            onChange={(e) => setForm({ ...form, huong_dan: e.target.value })}
          />
        </label>
        <div className="kkb-form__nut">
          <button type="button" className="btn btn--ghost" onClick={() => setForm(null)}>Huỷ</button>
          <button type="button" className="btn btn--accent" onClick={luu} disabled={dangLuu}>
            {dangLuu ? "Đang lưu…" : form.id == null ? "Thêm hạng mục" : "Lưu"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <main className="rc kkb">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Tiêu chí KCS</h1>
          <span className="rc__count">{soCongDoan} công đoạn cần kiểm</span>
        </div>
        <p className="rc__sub">
          Khai theo tờ ISO của xưởng: chọn <strong>giai đoạn</strong> → chọn{" "}
          <strong>công đoạn</strong> → thêm <strong>hạng mục kiểm</strong> cho công đoạn đó. Khi
          phát hành lệnh sản xuất, bước nào chạy công đoạn có hạng mục ở đây sẽ thành điểm kiểm
          trên bàn KCS.
        </p>
      </header>

      {loi && (
        <div className="banner banner--error" role="alert">
          <span>{loi}</span>
        </div>
      )}

      {suaDuoc && (
        <section className="kkb-them">
          <h2>Thêm công đoạn cần kiểm</h2>
          <div className="kkb-them__row">
            <label>
              <span>Giai đoạn *</span>
              <select
                className="rc-input"
                value={themNhom}
                onChange={(e) => { setThemNhom(e.target.value); setThemCongDoanId(""); }}
              >
                <option value="">— Chọn giai đoạn —</option>
                {Object.entries(NHOM_CONG_DOAN).map(([ma, nhan]) => (
                  <option key={ma} value={ma}>{nhan}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Công đoạn *</span>
              <select
                className="rc-input"
                value={themCongDoanId}
                disabled={!themNhom}
                onChange={(e) => setThemCongDoanId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">
                  {!themNhom ? "— Chọn giai đoạn trước —"
                    : congDoanChonDuoc.length === 0 ? "— Giai đoạn này đã khai hết —"
                      : "— Chọn công đoạn —"}
                </option>
                {congDoanChonDuoc.map((c) => (
                  <option key={c.id} value={c.id}>{c.ma} · {c.ten}</option>
                ))}
              </select>
            </label>
            <button
              type="button" className="btn btn--accent"
              disabled={themCongDoanId === ""}
              onClick={() => setForm(formRong(Number(themCongDoanId), 1))}
            >
              Thêm hạng mục kiểm
            </button>
          </div>
          {/* Công đoạn CHƯA có trong cây thì form nằm ngay đây — chưa có thẻ nào để gắn vào. */}
          {form && form.id == null && !daKhai.has(form.cong_doan_id) && formHangMuc()}
        </section>
      )}

      {giaiDoan == null ? (
        <div className="rc__tablewrap">
          <table className="rc__table">
            <tbody>
              {Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="rc-skel__row"><td><span className="rc-skel" style={{ width: "60%" }} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : soCongDoan === 0 ? (
        <div className="rc__empty-state">
          <p className="rc__empty-text">Chưa khai công đoạn nào cần kiểm.</p>
          <p className="rc__empty-sub">Chọn giai đoạn và công đoạn ở khối trên để bắt đầu.</p>
        </div>
      ) : (
        giaiDoan.map((gd) => (
          <section key={gd.nhom || "khac"} className="kkb-giaidoan">
            <h2 className="kkb-giaidoan__ten">
              {NHOM_CONG_DOAN[gd.nhom] ?? "Chưa xếp giai đoạn"}
              <span className="rc__count">{gd.cong_doan.length}</span>
            </h2>
            {gd.cong_doan.map((cd) => (
              <article key={cd.cong_doan_id} className="kkb-cd">
                <header className="kkb-cd__head">
                  <h3>{cd.ten}</h3>
                  <span className="kkb-cd__ma">{cd.ma}</span>
                  <span className="rc__spacer" />
                  {suaDuoc && (
                    <button
                      type="button" className="btn btn--ghost btn--sm"
                      onClick={() => setForm(formRong(cd.cong_doan_id, cd.hang_muc.length + 1))}
                    >
                      + Hạng mục
                    </button>
                  )}
                </header>
                {/* KHÔNG có <thead>: bảng này lặp lại ở MỖI thẻ công đoạn, in cùng một dòng tiêu
                    đề 5-10 lần chỉ làm trang rối. Hướng dẫn kiểm nằm ngay DƯỚI câu chữ hạng mục
                    (không tách cột) — tách cột thì câu ngắn để lại một khoảng trắng chết dài suốt
                    chiều ngang, mà mắt vẫn phải bắc cầu ngang mới ghép được hai vế. */}
                <table className="rc__table kkb-table">
                  <colgroup>
                    <col className="kkb-col--num" />
                    <col />
                    <col className="kkb-col--nut" />
                  </colgroup>
                  <tbody>
                    {cd.hang_muc.map((h, i) => (
                      <tr key={h.id} className={h.active ? undefined : "kkb-row--tat"}>
                        <td className="num">{i + 1}</td>
                        <td>
                          <div className="kkb-hm__ten">
                            {h.ten}{!h.active && <span className="kkb-tat"> · ngừng dùng</span>}
                          </div>
                          {h.huong_dan && <div className="kkb-hm__hd">{h.huong_dan}</div>}
                        </td>
                        <td className="kkb-td--nut">
                          {suaDuoc && (
                            <button
                              type="button" className="btn btn--ghost btn--sm"
                              onClick={() => setForm({
                                id: h.id, cong_doan_id: h.cong_doan_id, ten: h.ten,
                                huong_dan: h.huong_dan ?? "", thu_tu: h.thu_tu,
                              })}
                            >
                              Sửa
                            </button>
                          )}
                          {xoaDuoc && (
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => xoa(h)}>
                              Xoá
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {form && form.cong_doan_id === cd.cong_doan_id && formHangMuc()}
              </article>
            ))}
          </section>
        ))
      )}
    </main>
  );
}
