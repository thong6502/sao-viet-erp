// Khối CHỨNG TỪ ĐÃ MUA (ảnh/PDF đính kèm lúc lập) — tách từ pages/PaymentVoucherDialog.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PaymentVoucherRow } from "../../../../api/client";

export function VoucherAttachSection({
  voucher,
  files,
  setFiles,
  addFiles,
}: {
  voucher: PaymentVoucherRow | null;
  files: File[];
  setFiles: Dispatch<SetStateAction<File[]>>;
  addFiles: (list: FileList | null) => void;
}) {
  return (
    <>
    {!voucher && (
      <section className="acct-form-section">
        <h3>Chứng từ đã mua (hóa đơn, biên nhận, UNC…)</h3>
        <label className="acct-field">
          <span>Ảnh / PDF — tối đa 10 MB mỗi file</span>
          <input
            className="input"
            type="file"
            multiple
            accept="image/*,application/pdf"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        {files.length > 0 && (
          <ul className="acct-filelist">
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`}>
                📎 {file.name}
                <button
                  type="button"
                  className="acct-modal__x acct-filelist__x"
                  aria-label={`Bỏ ${file.name}`}
                  onClick={() =>
                    setFiles((current) =>
                      current.filter((_, i) => i !== index),
                    )
                  }
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    )}
    </>
  );
}
