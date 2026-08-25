// Modal khai báo & điều chỉnh lương của một nhân viên (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  PIT_MODE_META,
  PIT_MODE_ORDER,
  type EmployeeDetail,
  type EmployeeInput,
  type EmployeeRow,
  type EmployeeSalary,
  type PayrollComponent,
  type PayrollParams,
  type PitMode,
  type SalaryPreview,
} from "../../../../api/client";
import { useCan } from "../../../../auth/permissions";
import { fmtDateTime } from "../../../../utils/format";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { EmptyRow } from "../../../../components/EmptyState";
import type { CompRow, SysRow } from "../shared/types";
import { errText, fmtYmd, money, todayYmd } from "../shared/helpers";

export function SalaryModal({
  token,
  emp,
  onClose,
}: {
  token: string;
  emp: EmployeeRow;
  onClose: () => void;
}) {
  const can = useCan();
  // `pit_mode` là field lương/BHXH của HỒ SƠ nhân sự ⇒ backend đòi `nhan_su:update` +
  // `nhan_su:edit_salary`. Thiếu quyền thì hiện chỉ-đọc chứ đừng cho bấm rồi im lặng không ăn.
  const canEditPit = can("nhan_su", "update") && can("nhan_su", "edit_salary");
  const [preview, setPreview] = useState<SalaryPreview | null>(null);
  // null = ĐANG TẢI (khởi tạo [] sẽ in "Chưa khai lương" ngay lúc còn fetch — báo sai).
  const [history, setHistory] = useState<EmployeeSalary[] | null>(null);
  const [histErr, setHistErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // form khai/điều chỉnh lương — hiệu lực LUÔN LÀ HÔM NAY (không cho chọn ngày):
  // sửa hôm nay thì áp dụng từ hôm nay, và mốc vừa lưu là mốc mới nhất nên màn không "nhảy" về số cũ.
  // C2: mức HỢP ĐỒNG của chính NV — gõ riêng 2 ô, không tự tách từ một số tổng.
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  // "Lương trả 1 lần" (đợt 1): mức trả trong MỘT lần — chỉ là số điền sẵn khi lập phiếu
  // "thanh toán lương đợt 1". Khai ở đây, muốn trả thì sang tab Tạm ứng lập phiếu + duyệt.
  const [luongDot1, setLuongDot1] = useState(0);
  // % hoa hồng NV kinh doanh — nhập theo PHẦN TRĂM ở UI, lưu xuống là PHÂN SỐ. Sửa ở ĐÂY chứ
  // không ở drawer nhân sự: mỗi lần POST là một mốc lương MỚI mang TOÀN BỘ các số, mà drawer
  // không giữ `luong_vi_tri`/phụ cấp ⇒ post từ đó là lương của người ta về 0.
  const [commissionPct, setCommissionPct] = useState(0);
  // Ô phụ cấp GỘP MỘT CỤC của dữ liệu cũ — chỉ đọc, giữ nguyên số để không mất tiền của NV;
  // khoản mới khai theo DANH MỤC ở `comps` bên dưới.
  const [allowance, setAllowance] = useState(0); // phụ cấp KHÁC (gộp — legacy)
  const [chuyenCan, setChuyenCan] = useState(0); // chuyên cần riêng NV
  // 2 phụ cấp khai tay còn lại. TRƯỚC ĐÂY modal không có 2 ô này nên mỗi lần bấm Lưu là chúng
  // bị ghi về 0 (mỗi lần lưu tạo MỘT mốc lương mới, field thiếu = mặc định 0) — mất tiền của NV.
  const [phuCapCa, setPhuCapCa] = useState(0);
  const [phuCapThamNien, setPhuCapThamNien] = useState(0);
  // TẦNG 2 — khoản ĐANG GÁN cho người này. null = ĐANG TẢI (khởi tạo [] sẽ báo "chưa gán khoản
  // nào" ngay lúc còn fetch — sai). `compBusy` khoá dòng đang gọi "Gỡ".
  const [comps, setComps] = useState<CompRow[] | null>(null);
  const [compBusy, setCompBusy] = useState<number | null>(null);
  const [compsErr, setCompsErr] = useState<string | null>(null);
  // Danh mục GỐC (Tầng 1) — chỉ để dựng dropdown "+ Thêm khoản". null = chưa đọc được (đang
  // tải hoặc thiếu quyền cấu hình) ⇒ khoá nút thêm chứ không chặn cả bảng.
  const [catalog, setCatalog] = useState<PayrollComponent[] | null>(null);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  // BH đóng ở nơi khác → công ty không trừ BHXH/BHYT/BHTN của NV, chỉ chịu TNLĐ-BNN.
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  // Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định không).
  const [unionMember, setUnionMember] = useState(false);
  // Giảm trừ bản thân — luật cho đăng ký ở ĐÚNG MỘT nơi làm việc. Mặc định BẬT (đại đa số chỉ
  // làm một nơi); tắt là ngoại lệ.
  const [applySelfDeduction, setApplySelfDeduction] = useState(true);
  const [params, setParams] = useState<PayrollParams | null>(null); // tỷ lệ BHXH/BHYT/BHTN + trần
  // Hồ sơ NV — chỉ để đọc `pit_mode` + `dependents_count` cho khối thuế. null = đang tải HOẶC
  // không đọc được (thiếu `nhan_su:read`): khối thuế lùi về chỉ-đọc chứ không chặn cả modal.
  const [detail, setDetail] = useState<EmployeeDetail | null>(null);
  const [detailErr, setDetailErr] = useState<string | null>(null);
  const [pitMode, setPitMode] = useState<PitMode | null>(null);
  const [pitConfirm, setPitConfirm] = useState(false);

  const reload = useCallback(async () => {
    const [prev, hist] = await Promise.all([
      api.luong.salaryPreview(token, emp.id).catch(() => null),
      // Đọc lịch sử hỏng thì phải NÓI RA (ca `lỗi` của bảng cuối màn). Bản cũ nuốt lỗi rồi trả
      // danh sách rỗng ⇒ màn in "Chưa khai lương" cho người ĐÃ có lương, và người dùng khai
      // lại một mốc đã tồn tại. Trả null = không đụng gì tới số đang hiện.
      api.luong.salaries(token, emp.id).catch((e) => {
        setHistErr(errText(e));
        return null;
      }),
    ]);
    setPreview(prev);
    if (!hist) return;
    setHistErr(null);
    setHistory(hist.items);
    // Điền sẵn theo bản lương mới nhất (để SỬA thay vì khai lại từ đầu).
    const latest = hist.items.length
      ? [...hist.items].sort((a, b) =>
          b.effective_from.localeCompare(a.effective_from),
        )[0]
      : null;
    if (latest) {
      setAllowance(latest.allowance ?? 0);
      setChuyenCan(latest.chuyen_can ?? 0);
      setPhuCapCa(latest.phu_cap_ca ?? 0);
      setPhuCapThamNien(latest.phu_cap_tham_nien ?? 0);
      setLuongDot1(latest.luong_dot_1 ?? 0);
      setCommissionPct((latest.commission_pct ?? 0) * 100);
      setInsuranceElsewhere(!!latest.insurance_elsewhere);
      setUnionMember(!!latest.union_member);
      setApplySelfDeduction(latest.apply_self_deduction ?? true);
      // Bản ghi cũ chưa tách 2 ô → dồn base_amount vào lương cơ bản để sửa tiếp, không mất số.
      const vt = latest.luong_vi_tri ?? 0;
      const tn = latest.luong_trach_nhiem ?? 0;
      if (vt > 0 || tn > 0) {
        setLuongViTri(vt);
        setLuongTrachNhiem(tn);
      } else {
        setLuongViTri(latest.base_amount ?? 0);
        setLuongTrachNhiem(0);
      }
    }
  }, [token, emp.id]);
  useEffect(() => {
    reload();
  }, [reload]);
  useEffect(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
  }, [token]);
  // Hồ sơ NV cho khối thuế TNCN. `pit_mode` về null = backend CHE (thiếu `nhan_su:view_salary`)
  // chứ không phải chưa khai ⇒ khoá sửa, và tuyệt đối không gửi lại null (schema có pattern ⇒ 422).
  useEffect(() => {
    let alive = true;
    api.employees
      .get(token, emp.id)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setPitMode(d.pit_mode);
        setDetailErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setDetail(null);
        setPitMode(null);
        setDetailErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token, emp.id]);

  // Bảng khoản = đúng những khoản NGƯỜI NÀY đang được gán (`/components/employee/{id}` chỉ trả
  // khoản có tiền). KHÔNG đổ phẳng cả danh mục ra thành ô tiền — màn dài ngoằng và không ai
  // biết khoản nào đang thật sự áp dụng.
  const loadComps = useCallback(async () => {
    try {
      const r = await api.luong.components.employeeValues(token, emp.id);
      setComps(
        r.items.map((v) => ({
          component_id: v.component_id,
          name: v.name,
          kind: v.kind,
          is_taxable: v.is_taxable,
          is_active: v.is_active,
          saved: v.amount,
          savedNote: v.note,
          draft: v.amount,
          note: v.note ?? "",
        })),
      );
      setCompsErr(null);
    } catch (e) {
      // GIỮ NGUYÊN `comps`: gán [] khi lỗi sẽ báo "chưa gán khoản nào" — sai, và người dùng
      // sẽ gán lại từ đầu thành gán trùng.
      setCompsErr(errText(e));
    }
  }, [token, emp.id]);
  useEffect(() => {
    loadComps();
  }, [loadComps]);
  // Danh mục gốc chỉ để dựng dropdown "+ Thêm khoản" — đọc hỏng thì khoá nút thêm, bảng khoản
  // đang gán vẫn dùng bình thường.
  useEffect(() => {
    let alive = true;
    api.luong.components
      .list(token)
      .then((r) => {
        if (!alive) return;
        setCatalog(r.items);
        setCatalogErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setCatalogErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token]);

  function setRow(id: number, patch: Partial<CompRow>) {
    setComps((list) =>
      (list ?? []).map((r) => (r.component_id === id ? { ...r, ...patch } : r)),
    );
  }

  /** Khoản CHƯA gán cho người này + đang bật — đúng tập được phép chọn. Khoản đã gán ẩn khỏi
   *  danh sách (chống gán trùng, đúng ràng buộc UNIQUE ở DB); khoản đã ngừng áp dụng cũng ẩn
   *  (backend chặn gán mới). */
  const assigned = new Set((comps ?? []).map((r) => r.component_id));
  const addable = (catalog ?? []).filter(
    (c) => c.is_active && !assigned.has(c.id),
  );

  /** Chọn khoản từ danh mục ⇒ thêm MỘT dòng nháp (chưa gọi API). Số tiền + ghi chú gõ xong
   *  mới bấm "Lưu điều chỉnh" — cùng một nhịp lưu với các ô lương, không lưu lắt nhắt. */
  function addComp(componentId: number) {
    const c = (catalog ?? []).find((x) => x.id === componentId);
    if (!c) return;
    setComps((list) => [
      ...(list ?? []),
      {
        component_id: c.id,
        name: c.name,
        kind: c.kind,
        is_taxable: c.is_taxable,
        is_active: c.is_active,
        saved: null,
        savedNote: null,
        draft: 0,
        note: "",
      },
    ]);
    setPicking(false);
  }

  /** "Gỡ" = thôi trả khoản này cho người đó từ kỳ sau (`amount: null`). Dòng chưa lưu thì chỉ
   *  bỏ khỏi màn. Dòng đã lưu gọi API NGAY — đây là lệnh dứt điểm, gom vào nút Lưu chung sẽ
   *  làm người dùng tưởng đã gỡ trong khi tiền vẫn đang chạy. */
  async function removeComp(row: CompRow) {
    if (row.saved === null) {
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      return;
    }
    setCompBusy(row.component_id);
    setErr(null);
    try {
      await api.luong.components.setEmployeeValues(token, emp.id, [
        { component_id: row.component_id, amount: null },
      ]);
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      setOk(
        `Đã gỡ khoản “${row.name}” khỏi ${emp.full_name}. Kỳ lương đã chốt giữ nguyên số cũ.`,
      );
    } catch (e) {
      setErr(errText(e));
    } finally {
      setCompBusy(null);
    }
  }

  /** Đổi cách tính thuế = đổi TIỀN THUẾ của người đó (bỏ/lấy lại giảm trừ gia cảnh) ⇒ hỏi lại
   *  trước khi lưu, không để bấm nhầm. Không đổi nhánh thì lưu thẳng. */
  const pitChanged =
    canEditPit &&
    pitMode != null &&
    detail != null &&
    pitMode !== detail.pit_mode;
  function saveSalary() {
    if (pitChanged) {
      setPitConfirm(true);
      return;
    }
    void doSave();
  }

  /** Dòng khoản có gì để gửi: đổi số, đổi ghi chú, hoặc là dòng mới chọn (`saved === null`). */
  const compChanged = (comps ?? []).filter(
    (r) =>
      r.saved === null ||
      r.draft !== r.saved ||
      (r.note.trim() || null) !== r.savedNote,
  );

  async function doSave() {
    setPitConfirm(false);
    // Khoản vừa chọn mà để 0 thì backend lưu 0 rồi lọc mất khi đọc lại — người dùng thấy khoản
    // "biến mất" và tưởng hệ thống nuốt. Chặn ngay ở đây, nói rõ phải làm gì.
    const emptyNew = compChanged.find((r) => r.saved === null && r.draft <= 0);
    if (emptyNew) {
      setErr(
        `Nhập số tiền cho khoản “${emptyNew.name}” (hoặc bấm Gỡ để bỏ dòng đó) rồi lưu lại.`,
      );
      return;
    }
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const eff = todayYmd(); // hiệu lực = hôm nay
      await api.luong.setSalary(token, emp.id, {
        effective_from: eff,
        amount_mode: "manual",
        luong_vi_tri: luongViTri,
        luong_trach_nhiem: luongTrachNhiem,
        luong_dot_1: luongDot1,
        allowance,
        chuyen_can: chuyenCan,
        phu_cap_ca: phuCapCa,
        phu_cap_tham_nien: phuCapThamNien,
        insurance_elsewhere: insuranceElsewhere,
        union_member: unionMember,
        apply_self_deduction: applySelfDeduction,
        // Backend nhận PHÂN SỐ và chặn `le=1` ⇒ kẹp trần 100% ở đây, đừng để gõ nhầm "150"
        // ăn nguyên cục 422 mà không hiểu vì sao.
        commission_pct: Math.min(commissionPct, 100) / 100,
      });
      // Khoản danh mục: chỉ gửi dòng ĐỔI (số hoặc ghi chú) — gửi cả bảng là ghi lại hàng loạt
      // bản ghi không đổi, làm bẩn nhật ký và dễ ghi đè số người khác vừa sửa.
      if (compChanged.length) {
        await api.luong.components.setEmployeeValues(
          token,
          emp.id,
          compChanged.map((r) => ({
            component_id: r.component_id,
            amount: r.draft,
            note: r.note.trim() || null,
          })),
        );
        // Đọc LẠI từ server thay vì suy từ nháp: khoản để 0 bị backend lọc khỏi danh sách,
        // đoán bừa là màn hiện một dòng không còn tồn tại.
        await loadComps();
      }
      // Cách tính thuế nằm ở HỒ SƠ (`employees.pit_mode`) nên phải PUT hồ sơ. Endpoint này ghi
      // ĐÈ mọi field sửa được ⇒ gửi NGUYÊN bản hồ sơ vừa đọc, chỉ đổi đúng `pit_mode`; gửi
      // body rút gọn sẽ XOÁ TRẮNG số điện thoại / địa chỉ / STK của người ta.
      let pitNote = "";
      if (pitChanged && detail && pitMode) {
        // try RIÊNG: lương ĐÃ lưu xong ở trên rồi. Ném lỗi ra ngoài sẽ hiện mỗi câu đỏ và
        // người dùng tưởng KHÔNG có gì được lưu → gõ lại lần nữa, sinh thêm một mốc lương.
        try {
          const res = await api.employees.update(token, emp.id, {
            ...(detail as unknown as EmployeeInput),
            pit_mode: pitMode,
          });
          setDetail(res.employee);
          setPitMode(res.employee.pit_mode);
          // Thiếu `nhan_su:edit_salary` thì backend BỎ QUA field này mà KHÔNG báo lỗi — đọc lại
          // kết quả rồi mới nói, đừng báo "đã đổi" cho một việc chưa xảy ra.
          pitNote =
            res.employee.pit_mode === pitMode
              ? ` Cách tính thuế TNCN: ${PIT_MODE_META[pitMode].label}.`
              : " ⚠ Cách tính thuế TNCN CHƯA đổi được — tài khoản của bạn không có quyền sửa" +
                " dữ liệu lương/BHXH của hồ sơ nhân sự.";
        } catch (e) {
          setPitMode(detail.pit_mode); // trả ô về đúng số đang nằm trên server
          setErr(
            `Lương đã lưu, nhưng KHÔNG đổi được cách tính thuế TNCN: ${errText(e)}`,
          );
        }
      }
      setOk(
        "Đã lưu lương (hiệu lực từ hôm nay " + fmtYmd(eff) + ")." + pitNote,
      );
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // Tiền BHXH/BHYT/BHTN nhân viên đóng — theo TỶ LỆ đã cấu hình + áp trần RIÊNG đúng như engine
  // (_compute): mức đóng BH = LƯƠNG CƠ BẢN (chỉ vị trí), KHÔNG gồm trách nhiệm.
  const salaryBase = luongViTri + luongTrachNhiem; // mức nền: prorate công + gốc tính tăng ca
  const bhBase = luongViTri; // đóng BH trên lương cơ bản (vị trí)

  // Tổng khoản THU của danh mục (khoản `tru` là khấu trừ, không cộng vào đây) + số cũ gộp cục.
  const compThu = (comps ?? []).reduce(
    (s, r) => (r.kind === "thu" ? s + r.draft : s),
    0,
  );
  const compTru = (comps ?? []).reduce(
    (s, r) => (r.kind === "tru" ? s + r.draft : s),
    0,
  );
  const isProbation = emp.status === "probation";
  const bhCapY =
    params && params.bh_base_cap > 0
      ? Math.min(bhBase, params.bh_base_cap)
      : bhBase;
  const bhCapTN =
    params && params.bhtn_base_cap > 0
      ? Math.min(bhBase, params.bhtn_base_cap)
      : bhBase;
  const bhxhAmt = params ? bhCapY * params.bhxh_rate : 0;
  const bhytAmt = params ? bhCapY * params.bhyt_rate : 0;
  const bhtnAmt = params ? bhCapTN * params.bhtn_rate : 0;
  const bhTotal = bhxhAmt + bhytAmt + bhtnAmt;
  const pctOf = (r: number) =>
    (r * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

  // 4 ô lương HỆ THỐNG (+ ô "Phụ cấp ca" ĐÃ NGƯNG, chỉ hiện khi còn số cũ) — đứng chung bảng
  // với khoản danh mục (chốt chủ 27/07/2026). Cờ chịu thuế
  // bám ĐÚNG engine (xem chú thích type SysRow) — đây là nơi dễ "dạy sai" nhất của màn này.
  const sysRows: SysRow[] = [
    {
      key: "luong_vi_tri",
      name: "Lương cơ bản",
      note: "BHXH/BHYT/BHTN đóng trên số này",
      taxable: true,
      value: luongViTri,
      set: setLuongViTri,
    },
    {
      key: "luong_trach_nhiem",
      name: "Lương trách nhiệm",
      note: `Mức nền = cơ bản + trách nhiệm: ${money(salaryBase)}đ — tăng ca tính trên số này`,
      taxable: true,
      value: luongTrachNhiem,
      set: setLuongTrachNhiem,
    },
    {
      key: "chuyen_can",
      name: "Thưởng chuyên cần",
      note: "Để 0 = dùng mức của tổ. Trừ dần theo ngày nghỉ",
      taxable: true,
      value: chuyenCan,
      set: setChuyenCan,
    },
    // Ô ĐÃ NGƯNG (chủ 21/08/2026: "không dùng tới nữa thì xóa đi hiển thị làm gì").
    // CHỈ hiện khi người này CÒN SỐ CŨ — engine đã trả 0 tuyệt đối (`night_pay = 0.0`), nên với
    // người để 0 thì ô này là một dòng chết, đọc xong không làm được gì.
    // Không xoá hẳn nhánh: kỳ cũ đã chốt còn số thì vẫn phải tra được, đúng như phiếu lương bên
    // dưới cũng chỉ in dòng "Phụ cấp ca (khai tay — đã ngưng)" khi còn số.
    // Đếm trước khi gỡ (21/08/2026): 0/6 dòng `employee_salaries` · 0/15 dòng `payroll_lines`.
    ...(phuCapCa > 0
      ? [{
      key: "phu_cap_ca",
      name: "Phụ cấp ca (đã ngưng)",
      // Chú thích cũ ghi "engine miễn TNCN như tiền tăng ca / ca đêm" — câu đó KHẲNG ĐỊNH SAI:
      // phần miễn thuế là di sản từ hồi ô này là tiền ca đêm ĐƯỢC TÍNH, còn TT 111/2013 Đ3.1.i
      // chỉ miễn phần trả CAO HƠN gắn với giờ đêm/tăng ca THỰC TẾ.
      note: "KHÔNG còn ra tiền từ 03/08/2026 — cơm & phụ cấp ca nay tính theo CA THỰC LÀM (khai ở từng ca, màn Chấm công). Số cũ giữ lại để tra lịch sử.",
      taxable: true,
      value: phuCapCa,
      set: setPhuCapCa,
      readOnly: true,
        }] as SysRow[]
      : []),
    {
      key: "phu_cap_tham_nien",
      name: "Phụ cấp thâm niên",
      note: "Số cố định khai tay, không tự tính theo năm công tác",
      taxable: true,
      value: phuCapThamNien,
      set: setPhuCapThamNien,
    },
  ];
  const sysThu = sysRows.reduce((s, r) => s + r.value, 0);

  // --- Khối thuế TNCN --------------------------------------------------------
  // Người phụ thuộc lấy từ HỒ SƠ (ô `dependents_count` đã có sẵn ở đó) — ở đây chỉ nhẩm hộ.
  const dependents = detail?.dependents_count ?? 0;
  // `pitKnown` = đã ĐỌC ĐƯỢC cách tính thuế thật của người này. Chưa đọc được (đang tải, thiếu
  // quyền, hoặc backend che) ⇒ không được đoán, và tuyệt đối không PUT đè.
  const pitKnown = detail != null && detail.pit_mode != null;
  const pitEff = pitMode ?? "luy_tien";
  const hasDeduction = pitEff === "luy_tien"; // 2 nhánh còn lại KHÔNG có giảm trừ gia cảnh

  // Khối "Cấu hình tính thuế TNCN" trong modal này ĐANG TẮT (JSX bị comment ở ~2494–2616). Giữ
  // nguyên phần tính ở trên để bật lại chỉ cần bỏ comment khối JSX. Mấy dòng `void` dưới đây chỉ
  // để TypeScript thôi báo "khai mà không dùng" — không chạy gì, không đổi hành vi.
  void PIT_MODE_ORDER;
  void detailErr;
  void pitKnown;
  void hasDeduction;
  const deductionSelf = params ? params.deduction_self : null;
  const deductionDependent = params ? params.deduction_dependent : null;
  const deductionTotal =
    deductionSelf == null || deductionDependent == null
      ? null
      : (applySelfDeduction ? deductionSelf : 0) +
        deductionDependent * dependents;

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>
            Lương — {emp.full_name} <span className="ns__code">{emp.code}</span>
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {/* `banner--ok` KHÔNG có trong global.css ⇒ trước đây câu báo thành công hiện trần
              như chữ thường. Class đúng là `banner--success`. */}
          {ok && <div className="banner banner--success">{ok}</div>}

          {preview && (
            <div className="lg-preview">
              Mức lương hiện tại: <b>{money(preview.monthly)}đ</b>{" "}
              <span className="ns-badge ns-badge--muted">
                {preview.source === "manual" || preview.source === "employee"
                  ? "mức hợp đồng riêng"
                  : preview.source === "dept_row"
                    ? "theo bảng lương tổ (dữ liệu cũ)"
                    : preview.source === "rule"
                      ? "theo quy tắc"
                      : "chưa có"}
              </span>
              {/* {" · "}phụ cấp {money(preview.allowance)} */}
               · đóng BH trên{" "}
              {money(preview.insurance_base)}
            </div>
          )}

          {/* Ô lương HỆ THỐNG (`employee_salaries`) — GIỮ RIÊNG, không trộn với bảng khoản
              danh mục bên dưới: mấy ô này không gỡ được, trộn chung làm người dùng tưởng gỡ
              được. Cờ chịu thuế do ENGINE quyết (xem type SysRow) nên chỉ đọc. */}
          <h4 className="ns-section__title">Lương &amp; phụ cấp cố định</h4>
          <p className="cc-note">
            Ô cố định của phần mềm: sửa được <b>số tiền</b>, không gỡ được.
            Khi lưu, mức mới <b>áp dụng từ hôm nay</b> và mốc cũ được giữ trong
            Lịch sử điều chỉnh.
          </p>
          <div className="lg-comp lg-comp--sys">
            <div className="lg-comp__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền / tháng</span>
            </div>
            {sysRows.map((r) => (
              <div key={r.key} className="lg-comp__row lg-comp__row--sys">
                <div className="lg-comp__name">
                  {r.name}
                  <span className="lg-comp__src">{r.note}</span>
                </div>
                <div>
                  <span
                    className={`ns-badge ${r.taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                  >
                    {r.taxable ? "Chịu thuế" : "Miễn thuế"}
                  </span>
                </div>
                <div className="lg-comp__money">
                  <input
                    type="number"
                    min={0}
                    step={100000}
                    aria-label={`Số tiền ${r.name}`}
                    value={r.value}
                    // Ô đã ngưng: cho XEM số cũ nhưng KHÔNG cho sửa. Ẩn hẳn thì người ta không
                    // tra được lịch sử; để sửa được thì lại hứa suông vì số đó không ra tiền nữa.
                    readOnly={r.readOnly}
                    disabled={r.readOnly}
                    onChange={(e) => r.set(Number(e.target.value))}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* TẦNG 2 — khoản thu nhập theo DANH MỤC, gán cho riêng người này. Chỉ hiện khoản
              ĐANG GÁN; muốn thêm thì CHỌN từ danh mục gốc (bước 2 của quy trình 2 bước). */}
          <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Khoản thu nhập theo danh mục
          </h4>
          <p className="cc-note">
            Khoản gán ở đây được trả <b>lặp lại mọi tháng</b> cho tới khi bạn
            gỡ. Chip <b>Chịu thuế / Miễn thuế</b> kế thừa từ danh mục gốc —{" "}
            <b>không sửa ở đây</b>. Thưởng nóng chỉ có một tháng thì đừng gán
            vào đây: khai ở{" "}
            <b>Bảng lương → Sửa dòng → Khoản phát sinh tháng này</b>.
          </p>
          <div className="lg-comp lg-comp--cat">
            <div className="lg-comp__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền / tháng</span>
              <span>Ghi chú</span>
              <span />
            </div>
            {comps === null ? (
              <div className="lg-comp__empty">
                {compsErr ? (
                  <>
                    Không đọc được khoản của người này ({compsErr}).{" "}
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => void loadComps()}
                    >
                      Thử lại
                    </button>
                  </>
                ) : (
                  "Đang tải các khoản đang gán…"
                )}
              </div>
            ) : comps.length === 0 ? (
              <div className="lg-comp__empty">
                Người này chưa được gán khoản thu nhập nào. Bấm{" "}
                <b>“+ Thêm khoản thu nhập”</b> để chọn từ danh mục.
              </div>
            ) : (
              comps.map((r) => (
                <div
                  key={r.component_id}
                  className={`lg-comp__row${r.is_active ? "" : " lg-comp__row--off"}`}
                >
                  <div className="lg-comp__name">
                    {r.name}
                    {r.kind === "tru" && (
                      <span
                        className="ns-badge ns-badge--danger"
                        style={{ marginLeft: 6 }}
                      >
                        Trừ
                      </span>
                    )}
                    {r.saved === null && (
                      <span
                        className="ns-badge ns-badge--muted"
                        style={{ marginLeft: 6 }}
                      >
                        chưa lưu
                      </span>
                    )}
                    {/* Khoản đã ngừng áp dụng: CẢNH BÁO thôi, vẫn hiện số tiền bình thường —
                        lương đang trả khoản này, gạch ngang / ẩn đi là nói dối. */}
                    {!r.is_active && (
                      <span className="lg-comp__warn">
                        Khoản này đã ngừng áp dụng. Gỡ bỏ hoặc để 0.
                      </span>
                    )}
                  </div>
                  <div>
                    <span
                      className={`ns-badge ${r.is_taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                    >
                      {r.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                    </span>
                  </div>
                  <div className="lg-comp__money">
                    <input
                      type="number"
                      min={0}
                      step={50000}
                      aria-label={`Số tiền khoản ${r.name}`}
                      value={r.draft}
                      disabled={compBusy === r.component_id}
                      onChange={(e) =>
                        setRow(r.component_id, {
                          draft: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div className="lg-comp__note">
                    <input
                      type="text"
                      maxLength={255}
                      placeholder="vd: theo dự án X"
                      aria-label={`Ghi chú khoản ${r.name}`}
                      value={r.note}
                      disabled={compBusy === r.component_id}
                      onChange={(e) =>
                        setRow(r.component_id, { note: e.target.value })
                      }
                    />
                  </div>
                  <div className="lg-comp__act">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      title="Thôi trả khoản này cho người đó (kỳ đã chốt giữ nguyên số cũ)"
                      disabled={compBusy === r.component_id}
                      onClick={() => void removeComp(r)}
                    >
                      Gỡ
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Thêm khoản = CHỌN từ danh mục gốc. KHÔNG có ô gõ tên tự do — muốn khoản mới thì
              phải tạo ở Cấu hình lương trước (quy trình 2 bước, chốt của chủ). */}
          <div className="lg-comp__add">
            {picking ? (
              <>
                <select
                  className="lg-comp__pick"
                  autoFocus
                  aria-label="Chọn khoản thu nhập từ danh mục"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) addComp(Number(e.target.value));
                  }}
                >
                  <option value="">— chọn khoản trong danh mục —</option>
                  {addable.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · {c.is_taxable ? "chịu thuế" : "miễn thuế"}
                      {c.kind === "tru" ? " · khấu trừ" : ""}
                    </option>
                  ))}
                  <option value="" disabled>
                    Không thấy khoản cần dùng? Tạo ở Cấu hình lương → Danh mục
                    khoản thu nhập.
                  </option>
                </select>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setPicking(false)}
                >
                  Hủy
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={catalog === null || addable.length === 0}
                onClick={() => setPicking(true)}
              >
                + Thêm khoản thu nhập
              </button>
            )}
            {catalogErr && (
              <span className="cc-card__hint">
                Không đọc được danh mục khoản thu nhập ({catalogErr}) — chưa
                chọn thêm khoản được.
              </span>
            )}
            {catalog !== null && addable.length === 0 && !picking && (
              <span className="cc-card__hint">
                Đã gán hết khoản đang bật trong danh mục. Cần khoản mới thì tạo
                ở <b>Cấu hình lương → Danh mục khoản thu nhập</b>.
              </span>
            )}
          </div>

          <p className="cc-card__hint">
            Tổng cộng mỗi tháng: <b>{money(sysThu + compThu)}đ</b> (ô cố định{" "}
            {money(sysThu)}đ · khoản danh mục {money(compThu)}đ)
            {compTru > 0 && (
              <>
                {" · "}khấu trừ: <b>{money(compTru)}đ</b>
              </>
            )}
            . Để <b>0</b> = thôi trả khoản đó (lưu xong dòng sẽ rời khỏi bảng).
          </p>

          {/* "Lương trả 1 lần" KHÔNG phải khoản thu nhập hằng tháng (không cộng vào lương) nên
              để ngoài bảng — nó chỉ là số điền sẵn cho phiếu tạm ứng đợt 1. */}
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Lương trả 1 lần (đợt 1)</span>
              <input
                type="number"
                min={0}
                step={100000}
                value={luongDot1}
                onChange={(e) => setLuongDot1(Number(e.target.value))}
              />
              <span className="cc-card__hint">
                Mức trả trong MỘT lần, KHÔNG cộng vào lương tháng. Đây chỉ là số
                điền sẵn — muốn trả đợt 1 thì sang tab <b>Tạm ứng</b> bấm{" "}
                <b>“+ Phiếu lương đợt 1”</b>, duyệt xong mới trừ vào lương.
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">
                % hoa hồng (NV kinh doanh)
              </span>
              <input
                type="number"
                min={0}
                max={100}
                step={0.5}
                placeholder="0"
                value={commissionPct || ""}
                onChange={(e) =>
                  setCommissionPct(
                    e.target.value === "" ? 0 : Number(e.target.value),
                  )
                }
              />
              <span className="cc-card__hint">
                Bỏ trống / 0 nếu không phải nhân viên kinh doanh.
                {/* Ô này <b>chỉ để KHAI</b> — hệ
                thống <b>CHƯA tự cộng hoa hồng vào lương</b>. Muốn trả thì vẫn phải thêm bằng tay
                ở <b>khoản thu nhập</b> của nhân viên hoặc ngay trên phiếu lương. */}
              </span>
            </label>
          </div>

          {/* Số phụ cấp GỘP MỘT CỤC của dữ liệu cũ — CHỈ ĐỌC, không xoá dữ liệu cũ. */}
          {allowance > 0 && (
            <div className="ns-field lg-legacy" style={{ marginTop: 12 }}>
              <span className="ns-field__label">
                Các khoản phụ cấp (số cũ, gộp một cục)
              </span>
              <input
                type="number"
                value={allowance}
                readOnly
                tabIndex={-1}
                aria-label="Các khoản phụ cấp gộp một cục (số cũ, chỉ đọc)"
              />
              <span className="cc-card__hint">
                Số cũ gộp một cục — nên tách ra từng khoản bên trên. Hệ thống
                vẫn cộng đủ số này như trước nên tách xong mà chưa bỏ số cũ là{" "}
                <b>cộng hai lần</b>.{" "}
                <button
                  type="button"
                  className="lg-linkbtn"
                  onClick={() => setAllowance(0)}
                >
                  Đưa về 0 sau khi đã tách
                </button>{" "}
                (các mốc lương cũ trong Lịch sử điều chỉnh vẫn giữ nguyên số).
              </span>
            </div>
          )}

          <label className="ns-check" style={{ marginTop: 6 }}>
            <input
              type="checkbox"
              checked={insuranceElsewhere}
              onChange={(e) => setInsuranceElsewhere(e.target.checked)}
            />
            Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN
          </label>
          <p className="cc-card__hint">
            Tích khi NV đã được nơi khác đóng BHXH/BHYT/BHTN. Công ty không trừ
            3 khoản này của họ.
          </p>

          <label className="ns-check" style={{ marginTop: 6 }}>
            <input
              type="checkbox"
              checked={unionMember}
              onChange={(e) => setUnionMember(e.target.checked)}
            />
            Đoàn viên công đoàn — có trừ đoàn phí công đoàn
          </label>
          <p className="cc-card__hint">
            Chỉ đoàn viên mới bị trừ đoàn phí công đoàn (theo tỷ lệ ở Cấu hình
            lương). Không tích = không trừ.
          </p>

          {/* Cấu hình tính thuế TNCN theo TỪNG NGƯỜI. Mọi con số (giảm trừ, tỷ lệ khấu trừ,
              ngưỡng) LẤY TỪ `GET /api/luong/params` — viết cứng vào chuỗi là màn hình nói dối
              ngay lần luật đổi mức. */}
          {/* <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Cấu hình tính thuế TNCN
          </h4>
          {detailErr && (
            <p className="cc-card__hint">
              ⚠ Không đọc được hồ sơ nhân sự của người này ({detailErr}) — phần
              cách tính thuế và người phụ thuộc chỉ hiện được khi đọc được hồ
              sơ.
            </p>
          )}
          <div className="lg-pit">
            <label className="ns-field lg-pit__mode">
              <span className="ns-field__label">Cách tính thuế TNCN</span>
              <select
                value={pitKnown ? pitEff : ""}
                disabled={!canEditPit || !pitKnown}
                onChange={(e) => setPitMode(e.target.value as PitMode)}
              >
                {!pitKnown && (
                  <option value="">
                    {detail == null
                      ? "— đang đọc hồ sơ —"
                      : "— không xem được —"}
                  </option>
                )}
                {PIT_MODE_ORDER.map((m) => (
                  <option key={m} value={m}>
                    {PIT_MODE_META[m].label}
                  </option>
                ))}
              </select>
              {pitKnown && (
                <span className="cc-card__hint">
                  {PIT_MODE_META[pitEff].hint}
                  {pitEff === "khau_tru_10" && params && (
                    <>
                      {" "}
                      Thuế = <b>{pctOf(params.pit_flat_rate)}%</b> × thu nhập
                      chịu thuế, chỉ khấu trừ khi thu nhập chịu thuế đạt{" "}
                      <b>{money(params.pit_flat_threshold)}đ</b> trở lên.
                    </>
                  )}
                  {pitEff === "cam_ket_08" && (
                    <>
                      {" "}
                      Chỉ chọn khi đã nhận đủ bản cam kết và người này có mã số
                      thuế cá nhân.
                    </>
                  )}
                </span>
              )}
              {!canEditPit && (
                <span className="cc-card__hint">
                  Tài khoản của bạn không có quyền sửa nhóm dữ liệu lương/BHXH
                  của hồ sơ nhân sự nên ô này chỉ để xem.
                </span>
              )}
              {canEditPit && detail != null && detail.pit_mode == null && (
                <span className="cc-card__hint">
                  Không xem được cách tính thuế hiện tại của người này (thiếu
                  quyền xem dữ liệu lương của hồ sơ) — khoá sửa để không ghi đè
                  nhầm.
                </span>
              )}
            </label>

            <div
              className={`lg-pit__ded${hasDeduction ? "" : " lg-pit__ded--off"}`}
            >
              {!hasDeduction && (
                <p className="lg-pit__note">
                  Cách tính này <b>không áp dụng giảm trừ gia cảnh</b>.
                </p>
              )}
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={applySelfDeduction}
                  disabled={!hasDeduction}
                  onChange={(e) => setApplySelfDeduction(e.target.checked)}
                />
                Áp dụng giảm trừ bản thân
              </label>
              <p className="cc-card__hint">
                {deductionSelf == null ? (
                  "Đang đọc mức giảm trừ từ Cấu hình lương…"
                ) : (
                  <>
                    Giảm trừ <b>{money(deductionSelf)}đ</b>/tháng. Bỏ tích nếu
                    người này đã đăng ký giảm trừ ở nơi làm việc khác (chỉ được
                    đăng ký ở <b>MỘT</b> nơi).
                  </>
                )}
              </p>
              <div className="lg-pit__dep">
                <span className="lg-pit__dep-label">Người phụ thuộc</span>
                {detail == null ? (
                  <span className="lg-pit__dep-val">—</span>
                ) : (
                  <span className="lg-pit__dep-val">
                    <b>{dependents} người</b>
                    {deductionDependent != null && (
                      <>
                        {" → giảm trừ "}
                        <b>{money(deductionDependent * dependents)}đ</b>
                      </>
                    )}
                  </span>
                )}
              </div>
              <p className="cc-card__hint">
                Số người phụ thuộc khai ở{" "}
                <b>Nhân sự → hồ sơ → tab Lương &amp; BHXH</b>; ở đây chỉ nhẩm hộ
                ra tiền.
                {hasDeduction && deductionTotal != null && detail != null && (
                  <>
                    {" "}
                    Tổng giảm trừ mỗi tháng: <b>{money(deductionTotal)}đ</b>.
                  </>
                )}
              </p>
            </div>
          </div> */}

          <div className="ns-grid" style={{ marginTop: 12 }}>
            <div
              className="ns-field"
              style={{ alignItems: "flex-end", gap: 6 }}
            >
              {ok && (
                <span
                  style={{ color: "#2e7d32", fontSize: 13, fontWeight: 600 }}
                >
                  ✓ {ok}
                </span>
              )}
              {err && (
                <span
                  style={{ color: "#c62828", fontSize: 13, fontWeight: 600 }}
                >
                  ⚠ {err}
                </span>
              )}
              <button
                className="btn btn--primary"
                onClick={saveSalary}
                disabled={busy}
              >
                {busy ? "Đang lưu…" : "Lưu điều chỉnh"}
              </button>
            </div>
          </div>

          {params && (
            <div className="lg-preview lg-bh" style={{ marginTop: 10 }}>
              {isProbation ? (
                <>
                  NV <b>thử việc</b> — chưa đóng BHXH/BHYT/BHTN (hợp đồng thử
                  việc).
                </>
              ) : insuranceElsewhere ? (
                <>
                  NV có <b>BH đóng ở nơi khác</b> — công ty KHÔNG trừ
                  BHXH/BHYT/BHTN của NV.
                  <br />→ Công ty chỉ đóng <b>TNLĐ-BNN</b>{" "}
                  {pctOf(params.tnld_bnn_rate)}% ={" "}
                  <b>{money(bhBase * params.tnld_bnn_rate)}đ</b> (chi phí công
                  ty, không trừ vào lương NV).
                </>
              ) : (
                <>
                  Đóng BH trên lương cơ bản <b>{money(bhBase)}đ</b>, nhân viên
                  đóng gồm:
                  <br />· BHXH {pctOf(params.bhxh_rate)}% ={" "}
                  <b>{money(bhxhAmt)}đ</b>
                  {"  ·  "}BHYT {pctOf(params.bhyt_rate)}% ={" "}
                  <b>{money(bhytAmt)}đ</b>
                  {"  ·  "}BHTN {pctOf(params.bhtn_rate)}% ={" "}
                  <b>{money(bhtnAmt)}đ</b>
                  <br />→ Tổng nhân viên đóng: <b>{money(bhTotal)}đ/tháng</b>
                </>
              )}
            </div>
          )}

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Lịch sử điều chỉnh
          </h4>
          <div className="ns__tablewrap" style={{ overflowX: "auto" }}>
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Trạng thái</th>
                  <th>Thời điểm sửa</th>
                  <th>Người sửa</th>
                  <th>Hiệu lực từ</th>
                  <th className="lg-num">Vị trí</th>
                  <th className="lg-num">Trách nhiệm</th>
                  <th className="lg-num">Mức nền</th>
                  <th className="lg-num">Phụ cấp</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {(history ?? []).map((s) => {
                  const vt = s.luong_vi_tri ?? 0;
                  const tn = s.luong_trach_nhiem ?? 0;
                  const nen = vt + tn > 0 ? vt + tn : (s.base_amount ?? 0);
                  return (
                    <tr key={s.id}>
                      <td>
                        {s.is_current ? (
                          <span className="ns-badge ns-badge--ok">
                            Đang áp dụng
                          </span>
                        ) : s.effective_to == null ? (
                          <span className="ns-badge ns-badge--muted">
                            Sắp áp dụng
                          </span>
                        ) : (
                          <span className="ns-badge ns-badge--muted">
                            Đã thay
                          </span>
                        )}
                      </td>
                      <td>{fmtDateTime(s.created_at)}</td>
                      <td>{s.actor_name ?? "—"}</td>
                      <td>{fmtYmd(s.effective_from)}</td>
                      <td className="lg-num">{vt ? money(vt) : "—"}</td>
                      <td className="lg-num">{tn ? money(tn) : "—"}</td>
                      <td className="lg-num">
                        <b>{money(nen)}</b>
                      </td>
                      <td className="lg-num">{money(s.allowance)}</td>
                      <td>{s.note ?? "—"}</td>
                    </tr>
                  );
                })}
                {(history ?? []).length === 0 && (
                  <EmptyRow
                    colSpan={9}
                    trangThai={
                      histErr ? "loi" : history === null ? "dang-tai" : "rong"
                    }
                    loi={histErr}
                    onThuLai={() => void reload()}
                    icon="clock"
                    title="Chưa khai lương cho người này"
                    sub="Điền các ô ở trên rồi bấm “Lưu điều chỉnh” — mốc đầu tiên sẽ nằm ở đây."
                  />
                )}
              </tbody>
            </table>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>

      {/* Đổi cách tính thuế = đổi TIỀN THUẾ của người này. Bỏ luỹ tiến là mất toàn bộ giảm trừ
          gia cảnh ⇒ thuế nhảy vọt. Bắt xác nhận, và nói bằng SỐ THẬT lấy từ cấu hình. */}
      <ConfirmDialog
        open={pitConfirm}
        danger={pitEff !== "luy_tien"}
        title="Đổi cách tính thuế TNCN của người này?"
        confirmLabel="Đổi và lưu"
        busy={busy}
        countdownSeconds={pitEff === "luy_tien" ? 0 : 3}
        onCancel={() => {
          if (!busy) setPitConfirm(false);
        }}
        onConfirm={() => void doSave()}
      >
        <p className="cdlg__msg">
          <b>{emp.full_name}</b> đang tính theo{" "}
          <b>{PIT_MODE_META[detail?.pit_mode ?? "luy_tien"].label}</b>, sẽ
          chuyển sang <b>{PIT_MODE_META[pitEff].label}</b>.
        </p>
        {pitEff === "khau_tru_10" && (
          <p className="cdlg__msg">
            Từ kỳ tính tới, người này <b>KHÔNG còn được giảm trừ gia cảnh</b>
            {params && (
              <>
                {" "}
                ({money(params.deduction_self)}đ bản thân
                {dependents > 0 && (
                  <>
                    {" "}
                    + {money(params.deduction_dependent * dependents)}đ cho{" "}
                    {dependents} người phụ thuộc
                  </>
                )}
                )
              </>
            )}
            {params && (
              <>
                {" "}
                mà bị khấu trừ thẳng <b>{pctOf(params.pit_flat_rate)}%</b> trên
                thu nhập chịu thuế (từ {money(params.pit_flat_threshold)}đ trở
                lên)
              </>
            )}
            . <b>Tiền thuế sẽ tăng vọt.</b> Chỉ chọn cho HĐ dưới 3 tháng / thời
            vụ / thực tập.
          </p>
        )}
        {pitEff === "cam_ket_08" && (
          <p className="cdlg__msg">
            Hệ thống sẽ <b>KHÔNG khấu trừ thuế TNCN</b> của người này. Chỉ chọn
            khi đã nhận đủ bản cam kết <b>08/CK-TNCN</b> — khai sai thì công ty
            chịu trách nhiệm khấu trừ thiếu.
          </p>
        )}
        {pitEff === "luy_tien" && (
          <p className="cdlg__msg">
            Người này quay lại tính theo{" "}
            <b>bảng thuế luỹ tiến + giảm trừ gia cảnh</b>
            {deductionTotal != null && (
              <> (tổng giảm trừ hiện tại {money(deductionTotal)}đ/tháng)</>
            )}
            .
          </p>
        )}
        <p className="cdlg__msg">
          Kỳ lương đã chốt/đã chi giữ nguyên số cũ; thay đổi chỉ ăn vào kỳ tính
          từ đây về sau.
        </p>
      </ConfirmDialog>
    </div>
  );
}
