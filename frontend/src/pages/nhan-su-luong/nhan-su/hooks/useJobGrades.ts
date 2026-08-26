// Danh mục bậc tay nghề (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type JobGrade } from "../../../../api/client";
import { errMsg } from "../shared/helpers";

/** Danh mục bậc dùng chung cho wizard / dialog nâng bậc / điều chuyển.
 *  Để LOCAL trong file chứ không nâng thành prop của `EmployeeWizard`: màn Phòng ban cũng dựng
 *  wizard này, thêm một prop bắt buộc là vỡ chỗ đó. */
export function useJobGrades(token: string) {
  const [grades, setGrades] = useState<JobGrade[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(() => {
    setErr(null);
    return api.employees
      .jobGrades(token, { active_only: true })
      .then((r) => setGrades(r.items))
      .catch((e) => {
        setGrades(null);
        setErr(errMsg(e));
      });
  }, [token]);
  useEffect(() => {
    void reload();
  }, [reload]);
  /** Trả BẢN GHI vừa tạo để nơi gọi chọn luôn bậc đó — thêm xong mà còn phải tự tìm lại trong
   *  danh sách là thừa một bước, và dễ chọn nhầm bậc tên gần giống. */
  const addGrade = useCallback(
    async (name: string): Promise<JobGrade> => {
      const g = await api.employees.createJobGrade(token, { name });
      await reload();
      return g;
    },
    [token, reload],
  );
  return { grades, err, reload, addGrade };
}
