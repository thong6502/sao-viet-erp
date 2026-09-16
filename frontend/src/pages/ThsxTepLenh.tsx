// Thẻ "Tệp của lệnh" trong drawer Bàn tổ / KCS — maket, bản vẽ Kế hoạch SX đính kèm vào lệnh, tổ
// xem trước và tải về ngay tại việc mình làm (không có quyền mở hồ sơ lệnh). CHỈ ĐỌC: thêm/xoá tệp
// vẫn ở tab Tệp đính kèm của Kế hoạch SX.
//
// Danh sách gọn cho drawer hẹp (16/09/2026): mỗi tệp MỘT dòng thấp, bấm ảnh/tên để xem trước, hai
// nút biểu tượng Xem/Tải về bên phải; quá `HIEN_TRUOC` tệp thì gấp phần còn lại sau nút "Xem thêm".
// Không dùng `DinhKemTep` (khung tải lên đầy đủ) — chỉ mượn hộp xem trước và màu theo loại tệp.
//
// Công việc bài ghép thuộc nhiều lệnh ⇒ mỗi lệnh một nhóm, có nhãn mã lệnh. `dinhKemDem` là bộ đếm
// SSE `lsx_dinh_kem_changed` theo lệnh (AppShell): kế hoạch vừa thêm/xoá tệp thì thẻ tự nạp lại.
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError, assetUrl, type SxTepLenhNhom } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { layLopDuoi, XemTruoc } from "../components/DinhKemTep";
import { Icon } from "../components/Icons";
import { duoiTep, dungLuong, kieuXemTruoc, type TepDinhKem } from "../components/tepDinhKem";
import { ngayGio } from "./keHoachSxShared";

/** Số tệp hiện sẵn — đủ thấy maket chính, không đẩy Lịch sử phiên chạy xuống quá xa. */
const HIEN_TRUOC = 3;

function DongTep({ t, onXem }: { t: TepDinhKem; onXem: (t: TepDinhKem) => void }) {
  const kieu = kieuXemTruoc(t);
  const url = assetUrl(t.file_url) ?? undefined;
  const lop = layLopDuoi(t.ten_tep);
  const duoi = duoiTep(t.ten_tep);
  const than = (
    <>
      <span className={`thsx-tep__thumb ${kieu === "anh" ? "thsx-tep__thumb--anh" : lop}`} aria-hidden="true">
        {kieu === "anh" ? <img src={url} alt="" loading="lazy" /> : duoi || "TỆP"}
      </span>
      <span className="thsx-tep__chu">
        <span className="thsx-tep__ten" title={t.ten_tep}>{t.ten_tep}</span>
        <span className="thsx-tep__meta">
          {dungLuong(t.kich_thuoc)} · {ngayGio(t.tai_luc)}
          {t.nguoi_tai_ten ? ` · ${t.nguoi_tai_ten}` : ""}
        </span>
      </span>
    </>
  );
  return (
    <li className="thsx-tep">
      {kieu === "khac" ? (
        <span className="thsx-tep__chinh">{than}</span>
      ) : (
        <button type="button" className="thsx-tep__chinh thsx-tep__chinh--xem" onClick={() => onXem(t)}
          title={`Xem trước ${t.ten_tep}`}>
          {than}
        </button>
      )}
      <span className="thsx-tep__nut">
        {kieu !== "khac" && (
          <button type="button" className="thsx-tep__icon" onClick={() => onXem(t)}
            aria-label={`Xem trước ${t.ten_tep}`} title="Xem trước">
            <Icon name="eye" size={16} />
          </button>
        )}
        <a className="thsx-tep__icon" href={url} download={t.ten_tep} target="_blank" rel="noopener"
          aria-label={`Tải về ${t.ten_tep}`} title="Tải về">
          <Icon name="download" size={16} />
        </a>
      </span>
    </li>
  );
}

export function ThsxTepLenh({
  congViecId,
  dinhKemDem,
}: {
  congViecId: number;
  dinhKemDem?: Record<number, number>;
}) {
  const { token } = useAuth();
  const [nhom, setNhom] = useState<SxTepLenhNhom[] | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [lanNap, setLanNap] = useState(0);
  const [moHet, setMoHet] = useState(false);
  const [xem, setXem] = useState<TepDinhKem | null>(null);

  // Chỉ nạp lại khi bộ đếm của CHÍNH các lệnh trong thẻ đổi — lệnh khác thêm tệp không kéo API.
  const lsxIds = nhom?.map((n) => n.lsx_id) ?? [];
  const dem = lsxIds.reduce((s, id) => s + (dinhKemDem?.[id] ?? 0), 0);

  useEffect(() => {
    if (!token) return;
    let bo = false;
    setLoi(null);
    api.sanXuat
      .tepLenh(token, congViecId)
      .then((r) => { if (!bo) setNhom(r); })
      .catch((e) => {
        if (bo) return;
        setLoi(e instanceof ApiError && e.isNetwork ? "Mất kết nối tới máy chủ" : "Không nạp được tệp của lệnh");
      });
    return () => { bo = true; };
  }, [token, congViecId, dem, lanNap]);

  // Đổi sang việc khác thì gấp lại — mỗi việc mở ra đều bắt đầu gọn.
  useEffect(() => { setMoHet(false); }, [congViecId]);

  const tong = nhom?.reduce((s, n) => s + n.items.length, 0) ?? 0;
  const nhieuLenh = (nhom?.length ?? 0) > 1;

  // Cắt theo TỔNG số tệp, không theo từng nhóm: bài ghép 3 lệnh vẫn chỉ hiện 3 dòng khi gấp.
  let conCho = moHet ? Infinity : HIEN_TRUOC;
  const nhomHien = (nhom ?? []).map((n) => {
    const items = n.items.slice(0, Math.max(conCho, 0));
    conCho -= items.length;
    return { ...n, items, an: n.items.length - items.length };
  });
  const soAn = tong - nhomHien.reduce((s, n) => s + n.items.length, 0);

  return (
    <div className="thsx-card thsx-teplenh">
      <div className="thsx-psec__h">
        <Icon name="paperclip" size={14} />
        <span className="thsx-psec__title">Tệp của lệnh{nhom && tong > 0 ? ` (${tong})` : ""}</span>
      </div>
      {loi ? (
        <div className="thsx-tep__loi" role="alert">
          <span><Icon name="alert" size={14} /> {loi}</span>
          <button type="button" className="thsx-tep__thu-lai" onClick={() => setLanNap((n) => n + 1)}>
            <Icon name="refresh" size={14} /> Thử lại
          </button>
        </div>
      ) : nhom === null ? (
        <ul className="thsx-tep__ds" aria-busy="true" aria-label="Đang nạp tệp của lệnh">
          {[0, 1].map((i) => (
            <li key={i} className="thsx-tep thsx-tep--cho">
              <span className="thsx-tep__thumb" />
              <span className="thsx-tep__chu"><span className="thsx-tep__vach" /><span className="thsx-tep__vach thsx-tep__vach--ngan" /></span>
            </li>
          ))}
        </ul>
      ) : tong === 0 ? (
        <p className="thsx-dando thsx-dando--trong">Lệnh chưa có tệp đính kèm</p>
      ) : (
        <>
          {nhomHien.map((n) =>
            n.items.length === 0 ? (
              // Nhóm bị gấp hết thì thôi không vẽ nhãn; nhóm vốn trống (bài ghép) mới nói "chưa có tệp".
              n.an === 0 && nhieuLenh ? (
                <p key={n.lsx_id} className="thsx-teplenh__lenh">
                  {n.lsx_ma} <span className="thsx-teplenh__trong">· chưa có tệp</span>
                </p>
              ) : null
            ) : (
              <div key={n.lsx_id} className="thsx-teplenh__nhom">
                {nhieuLenh && (
                  <p className="thsx-teplenh__lenh" title={n.lsx_ten ?? undefined}>
                    {n.lsx_ma}{n.lsx_ten ? ` · ${n.lsx_ten}` : ""}
                  </p>
                )}
                <ul className="thsx-tep__ds">
                  {n.items.map((t) => <DongTep key={t.id} t={t} onXem={setXem} />)}
                </ul>
              </div>
            ),
          )}
          {(soAn > 0 || moHet) && tong > HIEN_TRUOC && (
            <button type="button" className="thsx-tep__them" aria-expanded={moHet} onClick={() => setMoHet((m) => !m)}>
              {moHet ? "Thu gọn" : `Xem thêm ${soAn} tệp`}
              <Icon name="chevron" size={14} className={moHet ? "thsx-tep__chev--len" : undefined} />
            </button>
          )}
        </>
      )}
      {/* Ra thẳng body: drawer có transform trượt vào nên `position: fixed` bên trong bị nhốt trong drawer. */}
      {xem && createPortal(<XemTruoc tep={xem} onDong={() => setXem(null)} />, document.body)}
    </div>
  );
}
