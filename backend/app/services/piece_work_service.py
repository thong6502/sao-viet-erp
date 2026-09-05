"""Lương khoán (module `luong`, nhịp 2) — nghiệp vụ.

Không còn tầng "sổ khoán" (quỹ tổ + bù lỗ + thưởng + chia hệ số). Chỉ còn:
  - khoan_map / defect_map: tổng hợp tiền khoán mỗi NV từ Phiếu sản lượng THEO NGƯỜI của kỳ,
    cộng thẳng vào cột `khoan` của payroll_lines lúc tính lương.
  - Thưởng/phạt tổ trưởng theo KHOẢNG SẢN LƯỢNG × tỷ lệ hàng lỗi của lệnh sản xuất.

CRUD bảng đơn giá (`piece_rates`) KHÔNG còn ở đây — từ 17/08/2026 nó là danh mục "Công việc khoán"
(`services/cong_viec_khoan_service.py`). Hai hàm THUẦN còn lại (`dau_viec_khop`, `khoan_snapshot`)
chỉ ĐỌC một dòng đơn giá, Kế hoạch SX gọi khi bung lệnh — không ghi gì nên vẫn thuộc về đây.

Cổng chốt = Chốt kỳ lương (payroll_lines đóng băng số khoán khi kỳ chốt). Không có chốt riêng.
"""
from __future__ import annotations


class PieceWorkError(Exception):
    pass


class PieceWorkValidationError(PieceWorkError):
    pass


class PieceWorkNotFound(PieceWorkError):
    pass


def _r(x) -> float:
    return float(round(float(x or 0)))


def _doc_khoang(tu: float, den: float | None) -> str:
    """Tên khoảng sản lượng để ghép vào câu báo lỗi — người khai nhìn bảng chứ không nhìn `seq`."""
    return f"{tu:g}–{den:g}" if den is not None else f"trên {tu:g}"


def _trong_khoang(san_luong: float, b) -> bool:
    """`sl_tu < SL <= sl_den`, `sl_den` None = ∞ — ĐÚNG quy ước bậc số lượng của `bu_hao_engine`."""
    tu = float(getattr(b, "sl_tu", 0) or 0)
    den = getattr(b, "sl_den", None)
    return tu < san_luong and (den is None or san_luong <= float(den))


def dau_viec_khop(rates, *, department_id: int | None) -> list:
    """Các đầu việc khoán của một TỔ — HÀM THUẦN (Kế hoạch SX gọi khi bung lệnh).

    Luật khớp chỉ còn một dòng: cùng tổ. Bảng đơn giá là bảng KHAI BÁO thuần — nó không biết và
    không cần biết việc nào của tổ dùng dòng nào; gốc là bên sản xuất, người lập lệnh nhìn các
    đơn giá của tổ rồi chọn. Bản trước cho khai "áp cho công đoạn nào" ngay trên dòng giá, thành
    ra một luật khớp ngầm (dòng khai riêng thắng dòng khai chung) mà mở form ra không ai đoán được.

    Trả list (0 = tổ không ăn khoán / chưa khai · 1 = tự điền được · >1 = để người chọn).
    """
    return [
        r for r in (rates or [])
        if (getattr(r, "active", None) if hasattr(r, "active") else getattr(r, "is_active", True))
        and (department_id is None or r.department_id == department_id)
    ]


def khoan_snapshot(rate) -> dict:
    """Ảnh chụp đầu việc để GHIM vào bước lệnh — xưởng lên giá khoán về sau không được xê dịch
    lệnh đã phát, nên bước giữ số của chính nó thay vì đọc-sống bảng giá.

    `cong_thuc` (mg `0213`) ghim CÙNG LÚC với đơn giá, và vì đúng một lý do: nó quyết định LƯỢNG mà
    đơn giá nhân vào, nên sửa nó ở danh mục cũng là đổi tiền. Ghim một nửa (giá đóng băng, cách đo
    đọc sống) là kiểu sai khó thấy nhất — tiền của lệnh cũ tự đổi mà không dòng nhật ký nào giải
    thích. Bước cũ muốn ăn công thức mới thì chọn lại đầu việc.

    Khoá VẮNG khi công thức rỗng (không ghi `None`): `khoan_json` là ảnh chụp đọc bằng mắt trong
    nhật ký lệnh, thêm một khoá luôn null chỉ làm dài dòng.
    """
    snap = {
        "rate_id": rate.id,
        "ten": getattr(rate, "ten", getattr(rate, "name", "")),
        "don_vi": getattr(rate, "don_vi", getattr(rate, "unit", "")),
        "don_gia": float(getattr(rate, "unit_price", getattr(rate, "don_gia", 0)) or 0),
    }
    if (ct := (getattr(rate, "cong_thuc_luong", None) or "").strip()):
        snap["cong_thuc"] = ct
    return snap



class PieceWorkService:
    def __init__(self, piece, outputs=None) -> None:
        self.piece = piece          # PieceWorkRepository (đơn giá khoán)
        self.outputs = outputs      # ProductionOutputRepository — nguồn tiền khoán theo người. None → bỏ.

    # --- đơn giá khoán: CRUD ĐÃ CHUYỂN ĐI -----------------------------------
    #
    # `list_rates` / `create_rate` / `update_rate` / `delete_rate` gỡ ngày 17/08/2026. Bảng
    # `piece_rates` nay là màn "Công việc khoán" của Cấu hình danh mục — mọi đường đọc/ghi đi qua
    # `CongViecKhoanService` (nền `CatalogService`: canh trùng mã, mã tự sinh `KH-####`, xoá mềm,
    # và GHI NHẬT KÝ trong cùng giao dịch). Giữ lại một bộ CRUD thứ hai ở đây là giữ một đường ghi
    # không có nhật ký.
    #
    # Còn ở lớp này: tiền khoán vào bảng lương (`khoan_map`) + thưởng/phạt tổ trưởng.

    # --- Bậc thưởng/phạt tổ trưởng theo tỷ lệ hàng lỗi (chủ 29/07/2026) ------

    def leader_brackets(self, department_id: int):
        return self.piece.list_leader_brackets(department_id)

    def set_leader_brackets(self, *, department_id: int, rows: list[dict]):
        """Thay CẢ BỘ bậc của một tổ, sau khi kiểm bảng có hợp lệ không.

        Validate không phải để làm khó: bảng có lỗ, chồng khoảng hay không tăng dần thì hàm tra rơi
        vào bậc SAI ⇒ ra sai tiền thưởng/phạt, mà đây là tiền thật của tổ trưởng."""
        clean: list[dict] = []
        for i, r in enumerate(rows or [], start=1):
            up = r.get("up_to_defect_pct")
            rate = r.get("rate_pct")
            tu = r.get("sl_tu")
            den = r.get("sl_den")
            if rate is None:
                raise PieceWorkValidationError(f"Bậc {i}: thiếu % thưởng/phạt.")
            if not (-100 <= float(rate) <= 100):
                raise PieceWorkValidationError(
                    f"Bậc {i}: % thưởng/phạt phải trong khoảng −100 đến 100."
                )
            if up is not None and float(up) < 0:
                raise PieceWorkValidationError(f"Bậc {i}: tỷ lệ lỗi không được âm.")
            tu_f = 0.0 if tu is None else float(tu)
            if tu_f < 0:
                raise PieceWorkValidationError(f"Bậc {i}: sản lượng 'từ' không được âm.")
            if den is not None and float(den) <= tu_f:
                raise PieceWorkValidationError(
                    f"Bậc {i}: sản lượng 'đến' phải lớn hơn 'từ' ({tu_f:g})."
                )
            clean.append({
                "seq": i,
                "sl_tu": tu_f,
                "sl_den": None if den is None else float(den),
                "up_to_defect_pct": None if up is None else float(up),
                "rate_pct": float(rate),
                "note": (r.get("note") or None),
            })

        if not clean:
            # Bộ RỖNG là hợp lệ = "tổ này không áp thưởng/phạt tổ trưởng". Cho xoá sạch.
            self.piece.replace_leader_brackets(department_id, [])
            return self.leader_brackets(department_id)

        self._kiem_luoi(clean)
        self.piece.replace_leader_brackets(department_id, clean)
        return self.leader_brackets(department_id)

    @staticmethod
    def _kiem_luoi(clean: list[dict]) -> None:
        """Kiểm bảng HAI CHIỀU: các khoảng sản lượng phủ kín trục, mỗi khoảng phủ kín trục lỗi.

        Hai chiều hỏng theo hai kiểu khác nhau nên câu báo lỗi cũng phải khác nhau — người khai cần
        biết mình thiếu dòng ở chiều nào."""
        # --- Chiều 1: khoảng sản lượng. Gom theo (sl_tu, sl_den), GIỮ NGUYÊN thứ tự xuất hiện.
        nhom: list[tuple[tuple[float, float | None], list[dict]]] = []
        for r in clean:
            khoa = (r["sl_tu"], r["sl_den"])
            if nhom and nhom[-1][0] == khoa:
                nhom[-1][1].append(r)
            else:
                if any(k == khoa for k, _ in nhom):
                    raise PieceWorkValidationError(
                        f"Khoảng sản lượng {_doc_khoang(*khoa)} bị tách làm hai chỗ — "
                        "gom các dòng của cùng một khoảng lại liền nhau."
                    )
                nhom.append((khoa, [r]))

        khoang = [k for k, _ in nhom]
        if khoang[0][0] != 0:
            raise PieceWorkValidationError(
                f"Khoảng sản lượng đầu tiên phải bắt đầu từ 0, đang là {khoang[0][0]:g} — "
                "lệnh có sản lượng nhỏ hơn sẽ không rơi vào khoảng nào."
            )
        for (a_tu, a_den), (b_tu, _b_den) in zip(khoang, khoang[1:]):
            if a_den is None:
                raise PieceWorkValidationError(
                    "Khoảng để trống ô 'đến SL' (∞) phải là khoảng CUỐI — nó hứng mọi sản lượng "
                    "cao hơn, xếp giữa bảng thì các khoảng sau không bao giờ tới lượt."
                )
            if b_tu != a_den:
                raise PieceWorkValidationError(
                    f"Khoảng sản lượng bị hở hoặc chồng nhau: {_doc_khoang(a_tu, a_den)} rồi tới "
                    f"{b_tu:g}. Khoảng sau phải bắt đầu ĐÚNG tại {a_den:g}."
                )
        if khoang[-1][1] is not None:
            raise PieceWorkValidationError(
                "Khoảng sản lượng cuối phải để TRỐNG ô 'đến SL' (∞) — thiếu nó thì lệnh có sản "
                "lượng lớn hơn mọi khoảng không được thưởng cũng không bị phạt."
            )

        # --- Chiều 2: trong TỪNG khoảng, trần tỷ lệ lỗi tăng dần + đúng một dòng ∞ ở cuối khoảng.
        for khoa, rs in nhom:
            ten = _doc_khoang(*khoa)
            vo_cuc = [i for i, r in enumerate(rs, start=1) if r["up_to_defect_pct"] is None]
            if len(vo_cuc) != 1:
                raise PieceWorkValidationError(
                    f"Khoảng sản lượng {ten}: phải có ĐÚNG MỘT dòng để trống ô 'tỷ lệ lỗi' — đó là "
                    "dòng 'trở lên', hứng mọi tỷ lệ cao hơn."
                )
            if vo_cuc[0] != len(rs):
                raise PieceWorkValidationError(
                    f"Khoảng sản lượng {ten}: dòng để trống ô 'tỷ lệ lỗi' phải nằm CUỐI khoảng."
                )
            moc = [r["up_to_defect_pct"] for r in rs[:-1]]
            for a, b in zip(moc, moc[1:]):
                if b <= a:
                    raise PieceWorkValidationError(
                        f"Khoảng sản lượng {ten}: tỷ lệ lỗi phải TĂNG DẦN "
                        f"({a:g}% rồi tới {b:g}% là sai thứ tự)."
                    )

    @staticmethod
    def leader_bonus_pct(san_luong, defect_pct, brackets) -> float:
        """% thưởng/phạt ứng với SẢN LƯỢNG của tổ trong lệnh và TỶ LỆ HÀNG LỖI của lệnh đó.

        Hai điều kiện, tra đúng thứ tự đó (chủ 04/09/2026: *"nó phải sét 2 điều kiện"*):
          1. Lọc các dòng có `sl_tu < sản lượng <= sl_den` (`sl_den` None = ∞). Ranh giới lấy y hệt
             bậc bù hao (`bu_hao_engine`) — sản lượng đúng 5.000 thuộc khoảng 0–5.000.
          2. Trong nhóm đó, dòng ĐẦU TIÊN có `tỷ lệ lỗi <= up_to_defect_pct` thắng; `None` = ∞.

        `san_luong=None` (CHƯA BIẾT) trả 0: chưa xác nhận được tổ làm bao nhiêu thì không phát
        thưởng mà cũng không phạt. Fail-closed có chủ ý, thừa kế đúng tinh thần cửa ngưỡng cũ.

        Trả DƯƠNG = thưởng, ÂM = phạt, 0 = không thưởng không phạt."""
        if not brackets or san_luong is None:
            return 0.0
        sl = float(san_luong)
        nhom = [b for b in brackets if _trong_khoang(sl, b)]
        if not nhom:
            return 0.0
        d = float(defect_pct or 0)
        for b in nhom:
            if b.up_to_defect_pct is None or d <= float(b.up_to_defect_pct):
                return float(b.rate_pct)
        return float(nhom[-1].rate_pct)

    @classmethod
    def leader_bonus_amount(cls, *, san_luong, don_gia_khoan, defect_pct, brackets) -> float:
        """Tiền thưởng/phạt tổ trưởng = **sản lượng × % của bậc trúng × đơn giá khoán**. Âm = trừ.

        Chủ 04/09/2026: *"tổng sản lượng của lệnh sản xuất tổ đó làm được nhân % sau đó kết hợp với
        đơn giá khoán của đầu việc đó là ra tiền thưởng"*. Đúng số chủ nêu: lệnh 5.000 sản phẩm,
        đơn giá khoán 300đ, lỗi 3% trúng bậc +5% ⇒ 5.000 × 5% × 300 = +75.000đ.

        Nhân trên TỔNG sản lượng làm ra, KHÔNG trừ hàng lỗi (chủ chốt: *"nhân trên 5000 chứ"*).

        Luồng thật KHÔNG gọi hàm này mà gọi `leader_bonus_pct` rồi nhân vào TỔNG TIỀN KHOÁN của tổ
        trong nhóm (`services/san_xuat/thuong_to_truong.py`): một tổ có thể làm nhiều công đoạn,
        mỗi công đoạn một đơn giá, nên "một đơn giá" không đủ mô tả. Hai cách ra CÙNG một số khi tổ
        chỉ làm một công đoạn — hàm này giữ lại vì nó là cách phát biểu gọn nhất công thức chủ nêu,
        và có test riêng (`test_khoan_api.py`) canh nó không trôi khỏi công thức đó."""
        pct = cls.leader_bonus_pct(san_luong, defect_pct, brackets)
        if pct == 0:
            return 0.0
        return _r(float(san_luong or 0) * float(don_gia_khoan or 0) * pct / 100.0)

    # ⚠️ `duoi_nguong` / `leader_settings` / `set_leader_settings` GỠ 04/09/2026 cùng bảng
    # `piece_leader_bonus_settings` (mg `0262`). Cửa chặn "sản lượng cả kỳ dưới X thì không xét"
    # sinh ra vì bảng bậc chỉ có MỘT chiều; nay khoảng sản lượng nằm ngay trên từng dòng bậc, nên
    # khoảng thấp nhất khai 0% đã gánh đúng việc đó — ngay trong bảng người khai đang nhìn.

    # --- tiền khoán vào bảng lương ------------------------------------------

    def khoan_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng tiền khoán} = Σ Phiếu sản lượng theo NGƯỜI (có tính khoán) của kỳ.

        Tiền mỗi phiếu = max(0, SL × đơn giá − trừ lỗi). Sàn 0 (không đẩy lương âm — Điều 102 BLLĐ).
        Không còn cổng "chốt sổ": phiếu tính khoán chảy vào lương khi HCNS tính lương; đóng băng khi
        Chốt kỳ lương.
        """
        out: dict[int, float] = {}
        if self.outputs is None:
            return out
        for o in self.outputs.list_nguoi_by_period(year, month):
            if not o.tinh_khoan or not o.employee_id:
                continue
            amt = max(0.0, float(o.unit_price) * float(o.quantity) - float(o.defect_deduction or 0))
            out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(amt)
        return out

    def defect_map(self, year: int, month: int) -> dict[int, float]:
        """{employee_id → tổng TRỪ LỖI khoán theo NGƯỜI} của kỳ — Lương gộp vào trần khấu trừ 30%
        (Điều 102). Cùng nguồn Phiếu sản lượng theo người + tính khoán như khoan_map."""
        out: dict[int, float] = {}
        if self.outputs is None:
            return out
        for o in self.outputs.list_nguoi_by_period(year, month):
            if not o.tinh_khoan or not o.employee_id:
                continue
            out[o.employee_id] = out.get(o.employee_id, 0.0) + _r(float(o.defect_deduction or 0))
        return out
