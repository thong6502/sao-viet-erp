// Một dòng tệp chỉ đọc trong ngăn chi tiết bàn tổ: ảnh thu nhỏ + tên + dòng phụ, bấm ảnh/tên để xem
// trước, hai nút biểu tượng Xem/Tải về bên phải. Dùng chung cho "Tệp của lệnh" và ảnh lỗi KCS để hai
// chỗ trông và bấm y như nhau. Đặt trong `.thsx-tep__ds` (khung viền chung); dòng phụ do nơi gọi soạn.
// Có `onBo` là ảnh CHƯA lưu (đang chờ trong form, URL `blob:`) — nút Tải về đổi thành nút Bỏ.
import type { ReactNode } from "react";
import { assetUrl } from "../api/client";
import { layLopDuoi } from "../components/DinhKemTep";
import { Icon } from "../components/Icons";
import { duoiTep, kieuXemTruoc, type TepXem } from "../components/tepDinhKem";

export function DongTep({
  t, meta, onXem, onBo,
}: { t: TepXem; meta?: ReactNode; onXem: (t: TepXem) => void; onBo?: () => void }) {
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
        {meta && <span className="thsx-tep__meta">{meta}</span>}
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
        {onBo ? (
          <button type="button" className="thsx-tep__icon" onClick={onBo}
            aria-label={`Bỏ ${t.ten_tep}`} title="Bỏ ảnh này">
            <Icon name="x" size={16} />
          </button>
        ) : (
          <a className="thsx-tep__icon" href={url} download={t.ten_tep} target="_blank" rel="noopener"
            aria-label={`Tải về ${t.ten_tep}`} title="Tải về">
            <Icon name="download" size={16} />
          </a>
        )}
      </span>
    </li>
  );
}
