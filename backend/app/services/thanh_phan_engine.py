"""Engine tính giá vốn THEO THÀNH PHẦN — hàm THUẦN (không I/O, không ORM).

Bản REDESIGN (theo `docs/redesign-tinh-gia.md` §0/§1.6): giá vốn theo SẢN LƯỢNG, KHÔNG hệ số.
CHI PHÍ CHỈ 2 LOẠI DÒNG (không còn rổ A/B/C/D):

  • Nguyên vật liệu (nvl) ← giấy + vật tư in ấn (kẽm/mực/keo/màng…).
  • Công đoạn (cong_doan) ← MỌI công đoạn (chế bản/kẽm · in · gia công) theo thứ tự routing.

Quy cách in (mẫu/cách/màu/kẽm) chỉ MÔ TẢ + phơi biến (so_mau/so_mat/so_kem) cho công thức — KHÔNG
phải rổ chi phí. Giá vốn = Σ dòng nvl + Σ dòng công đoạn.

BỐN KHỔ (mm) — không lẫn:
  ① khổ giấy nguyên (kho_ng_dai/rong) — MUA về, tính tiền giấy.
  ② khổ tờ in (kho_in_dai/rong)       — chạy máy, tính số lượt + bình bài. Thiếu → = ① (không xả).
  ③ khổ thành phẩm (dai/rong_thanh_pham) — input bình bài.
  ④ con/tờ = tự bình bài ③ lên ② (trừ chừa); override bằng so_con khi con_auto=False.

HAI PHÉP CHIA:
  • Xả giấy ① → ②: số mảnh = fit hình học của ② lên ① (min 1).
  • Bình bài ② → ④: con = fit hình học của ③ lên (② − chừa).

KHÔNG hệ số (mọi hệ số khoán/quy đổi = 1 → đã gỡ). Giá vốn → BỎ QUA lợi nhuận dòng finishing.
"""
from __future__ import annotations

import ast
import operator
import re
from math import ceil, floor

from .routing_engine import basis_qty, compute_step_cost
# TRẠM dòng giấy, KHÔNG phải mã đơn vị: chuỗi bù hao khoá hệ số và đọc mốc số tờ theo trạm, để
# xưởng khai mã riêng cho một chặng (`to_in` gắn cờ *tờ in*) vẫn khớp. Xem `services/dong_giay.py`.
from ..models.don_vi_do import TRAM_CAI, TRAM_CON, TRAM_TAY, TRAM_TO, TRAM_TO_NGUYEN
from .bien_cong_thuc import MA_TANG_BUOC_TIEN, ngu_canh_phieu
from .bu_hao_engine import chuoi_nguoc_dv
from .dong_giay import dich_chuoi


def cau_to_sang_cai(*, trang_moi_tay, so_trang, con) -> float:
    """Hệ số cầu `tờ in → cái` của MỘT sản phẩm. NGUỒN SỰ THẬT DUY NHẤT cho cả tính giá, lệnh sản
    xuất và bài ghép — ba tầng tự suy riêng thì ba số khác nhau cho cùng một cuốn sách.

    HAI KIỂU LÀM khác hẳn nhau, `trang_moi_tay` là thứ phân biệt (không cần thêm cờ nào):

    - **GẤP TAY** (sách, trang mỗi tay > 1): tờ in gấp NGUYÊN VẸN thành một tay → 1 tờ = 1 tay,
      một cuốn cần `so_tay` tờ. Hệ số **`1/so_tay`**, NHỎ HƠN 1. Tờ không bị cắt rời nên `con`
      KHÔNG vào công thức — nó chỉ để vẽ sơ đồ bình bài và kiểm khổ có vừa tờ.
    - **CẮT RỜI** (tờ rơi, danh thiếp, hộp): một tờ cắt ra `con` cái.

    Lấy `con` cho cả hai kiểu là sai hẳn với sách: 10 tờ mới ra 1 cuốn mà tính thành 1 tờ ra N
    cuốn thì số giấy hụt đúng `con × so_tay` lần, và hụt một chiều (không bao giờ thừa).

    `so_tay` TÍNH LẠI từ `so_trang / trang_moi_tay`; đừng nhận `so_to_per_sp` đã lưu — đó là số
    engine GHI RA, snapshot của nó thiu ngay khi ai sửa số trang mà không chạy lại.
    """
    tmt = max(int(_f(trang_moi_tay) or 1), 1)
    if tmt > 1:
        return 1.0 / so_tay_moi_cuon(trang_moi_tay=trang_moi_tay, so_trang=so_trang)
    return float(max(int(_f(con) or 0), 1))


def so_tay_moi_cuon(*, trang_moi_tay, so_trang) -> int:
    """Số TAY (= số tờ in) của một cuốn. `ceil(số trang / trang mỗi tay)`, tối thiểu 1."""
    tmt = max(int(_f(trang_moi_tay) or 1), 1)
    return max(ceil(max(_f(so_trang), 1.0) / tmt), 1)


def la_gap_tay(quy_cach) -> bool:
    """Sản phẩm GẤP TAY (sách) hay CẮT RỜI?

    Dùng ĐÚNG tiêu chí `cau_to_sang_cai` dùng để chọn nhánh `1/so_tay` — hai chỗ hỏi cùng một câu
    thì không thể trả lời lệch nhau. Ai cần biết "lệnh này có phải sách không" thì gọi hàm này,
    đừng tự gõ lại `trang_moi_tay > 1` ở chỗ khác.
    """
    return max(int(_f((quy_cach or {}).get("trang_moi_tay")) or 1), 1) > 1


MUC_PROCESS = ("C", "M", "Y", "K")


def tap_muc(v) -> list[str]:
    """Chuẩn hoá tập mực của MỘT mặt: viết hoa, bỏ khoảng trắng thừa, bỏ trùng, GIỮ THỨ TỰ khai.

    Không có danh mục mực nên chuẩn hoá chuỗi là hàng rào duy nhất chống `185C` / `185 c` /
    ` 185C ` thành ba mực khác nhau. An toàn vì hợp `A ∪ B` chỉ tính trong phạm vi MỘT thành phần
    (ruột và bìa là hai bộ bản riêng), tức mã chỉ cần khớp trong tầm một cái form — và UI cho bấm
    lại mã của mặt kia thay vì gõ lại.
    """
    if not isinstance(v, (list, tuple)):
        return []
    out: list[str] = []
    for x in v:
        ma = " ".join(str(x or "").split()).upper()
        if ma and ma not in out:
            out.append(ma)
    return out


def tap_muc_tu_so(so_mau_a, so_mau_b, so_mau_pha) -> tuple[list[str], list[str]]:
    """Dựng tập mực TỪ ba con số cũ — luật DUY NHẤT để đọc dữ liệu chưa khai mực.

    Dùng ở hai chỗ và phải giống hệt nhau: migration `0154` backfill DB, và engine đọc thành phần
    do seed/script dựng tay (chúng bơm số chứ không bơm tập). Viết hai bản là hai chỗ để lệch.

    `N màu process` → tiền tố `[K, C, M, Y]` (đen trước — xưởng gọi "1 màu" là đen), màu pha gắn
    vào mặt A. Hệ quả CỐ Ý: tập bên ít màu luôn là con của bên nhiều màu, nên `|A ∪ B| = max` —
    đúng bằng số kẽm tự trở mà engine cũ tính, và ba số dẫn xuất quay về y hệt giá trị vào.
    Nói cách khác: dữ liệu chỉ-có-số KHÔNG đổi giá; chỉ ai khai mực thật mới thấy số kẽm khác.
    """
    n_a = max(int(_f(so_mau_a)), 0)
    n_b = max(int(_f(so_mau_b)), 0)
    n_pha = max(int(_f(so_mau_pha)), 0)
    proc = list(("K", "C", "M", "Y"))
    # Quá 4 là dữ liệu lạ (process chỉ có 4) — phần dư thành mực chưa rõ tên nhưng vẫn đếm đủ bản.
    # Đặt tên theo MẶT để hai bên không vô tình gộp làm một khi hợp tập.
    a = proc[:n_a] + [f"MỰC A{i}" for i in range(5, n_a + 1)]
    b = proc[:n_b] + [f"MỰC B{i}" for i in range(5, n_b + 1)]
    a += [f"PHA {i}" for i in range(1, n_pha + 1)]
    return a, b


def so_kem_moi_tay(muc_a, muc_b, quy_cach_in: str) -> int:
    """Số bản kẽm cho MỘT tay (một bài in). NGUỒN SỰ THẬT DUY NHẤT của công thức kẽm.

    - **AB** (sheetwise): hai mặt hai bộ bản riêng → `|A| + |B|`. Cùng một Pantone dùng ở cả hai
      mặt vẫn phải ra hai bản, nên cộng chứ không hợp.
    - **Tự trở / trở nhíp** (work-and-turn / work-and-tumble): cả hai mặt nằm CHUNG một bộ bản,
      in xong lật tờ chạy lại chính bản đó → `|A ∪ B|`. Mỗi mực riêng biệt vẫn cần một bản riêng.
      Hai kiểu này khác nhau ở TRỤC LẬT (rủi ro chồng màu, khổ giấy), không khác số bản.
    - **1 mặt**: `|A|`.

    `max(|A|, |B|)` là rút gọn SAI cho nhánh tự trở — nó chỉ đúng khi tập mặt ít màu nằm gọn trong
    tập mặt kia. Mặt A `CMYK` với mặt B `185C` phải ra 5 bản, `max` ra 4 và thiếu đúng bản Pantone.
    """
    a, b = tap_muc(muc_a), tap_muc(muc_b)
    if quy_cach_in == "mot_mat":
        return len(a)
    if quy_cach_in in ("tu_tro", "tro_nhip"):
        return len(set(a) | set(b))
    return len(a) + len(b)


def so_mau_dan_xuat(muc_a, muc_b) -> tuple[int, int, int]:
    """`(so_mau_a, so_mau_b, so_mau_pha)` suy từ tập mực — GIỮ ĐÚNG NGHĨA CŨ của ba cột đó.

    `so_mau_a/b` đếm mực PROCESS mỗi mặt; `so_mau_pha` đếm mực pha PHÂN BIỆT của cả hai mặt gộp
    lại (một Pantone dùng ở hai mặt vẫn là một màu pha phải pha). Giữ nguyên nghĩa để công thức
    mực `so_mau_a + so_mau_b + so_mau_pha`, `_may_fit`, lệnh SX, bài ghép và báo giá không phải
    sửa dòng nào — và để phiếu cũ sau backfill ra y hệt số đang lưu.
    """
    a, b = tap_muc(muc_a), tap_muc(muc_b)
    proc = set(MUC_PROCESS)
    pha = {m for m in a + b if m not in proc}
    return (
        sum(1 for m in a if m in proc),
        sum(1 for m in b if m in proc),
        len(pha),
    )


def _f(v, d: float = 0.0) -> float:
    if v is None:
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _i(v, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _r(v: float) -> float:
    """Làm tròn 2 số lẻ → number (JSON)."""
    return round(_f(v), 2)


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# So sánh — CHỈ dùng làm điều kiện của `if(...)`, không hỗ trợ chuỗi kiểu `1 < x < 10` (đó là AND
# ẩn, ngoài phạm vi đã chốt: có nhiều điều kiện thì lồng `if` chứ không AND/OR).
COMPARATORS = {
    ast.Lt: operator.lt,
    ast.Gt: operator.gt,
    ast.LtE: operator.le,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

FUNCTIONS = {
    'ceil': ceil,
    'floor': floor,
    'round': round,
    'max': max,
    'min': min,
    'if': lambda dieu_kien, dung, sai: dung if dieu_kien else sai,
}

MATH_FUNCS = {"ceil", "floor", "round", "max", "min", "if"}


def _eval_node(node, variables: dict) -> float:
    if isinstance(node, ast.Num):
        return float(node.n)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Hằng số không hợp lệ: {node.value}")
    elif isinstance(node, ast.Name):
        name = node.id
        if name in variables:
            return float(variables[name] or 0.0)
        raise ValueError(f"Biến không xác định: {name}")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](left, right)
        raise ValueError(f"Toán tử không được hỗ trợ: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](operand)
        raise ValueError(f"Toán tử một ngôi không được hỗ trợ: {op_type}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Gọi hàm không hợp lệ")
        func_name = node.func.id
        if func_name == 'if_':  # 'if' là từ khoá Python, xem ghi chú tại _CHUYEN_TU_IF trong safe_eval
            func_name = 'if'
        if func_name not in FUNCTIONS:
            raise ValueError(f"Hàm không được hỗ trợ: {func_name}")
        args = [_eval_node(arg, variables) for arg in node.args]
        if func_name == 'if':
            return FUNCTIONS['if'](*args)
        return float(FUNCTIONS[func_name](*args))
    elif isinstance(node, ast.Compare):
        if len(node.ops) != 1:
            raise ValueError("Chỉ so sánh 1 điều kiện (vd a > b), không so chuỗi kiểu a > b > c")
        op_type = type(node.ops[0])
        if op_type not in COMPARATORS:
            raise ValueError(f"Toán tử so sánh không được hỗ trợ: {op_type}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.comparators[0], variables)
        return COMPARATORS[op_type](left, right)
    else:
        raise ValueError(f"Cú pháp không được hỗ trợ: {type(node)}")


# `if` là từ khoá Python — ast.parse("if(...)") nổ SyntaxError trước khi kịp vào _eval_node.
# Đổi tên thành `if_(` chỉ để qua cửa parser; _eval_node dịch ngược lại 'if' khi tra FUNCTIONS.
_CHUYEN_TU_IF = re.compile(r'\bif\s*\(')


def safe_eval(expr_str: str, variables: dict) -> float:
    if not expr_str or not expr_str.strip():
        return 0.0
    expr_str = expr_str.replace('×', '*').replace('÷', '/').replace('−', '-')
    expr_str = _CHUYEN_TU_IF.sub('if_(', expr_str)
    try:
        node = ast.parse(expr_str.strip(), mode='eval').body
        result = _eval_node(node, variables)
        if isinstance(result, bool):
            raise ValueError("Kết quả là điều kiện đúng/sai — cần bọc trong if(dieu_kien, dung, sai)")
        return float(result)
    except Exception as e:
        raise ValueError(f"Lỗi công thức: {e}")


# Biến ĐƠN GIÁ mà công thức vật tư / giấy có thể dùng. Đặt hết = 1 thì công thức tiền nhả ra chính
# LƯỢNG — xem `luong_tu_cong_thuc`. Mỗi ô một biến giá, tên nói rõ của ai (11/08/2026).
_BIEN_DON_GIA = ("don_gia_giay", "don_gia_vat_tu")


def _don_gia_co_so(don_gia: float, don_vi_gia: str | None) -> float:
    """Đơn giá quy về ĐƠN VỊ CƠ SỞ mà công thức đang đếm — khai đ/tấn thì về đ/kg.

    Trước 11/08/2026 việc này làm bằng một biến RIÊNG (`don_gia_kg`) phơi ra cho người dùng, thành
    ra ô Giấy có hai chip "Đơn giá" và "Đơn giá theo cân" cho cùng một số ở mọi mặt hàng đang có
    (23/23 dòng giấy khai đ/kg), rồi lặng lẽ lệch 1.000 lần ở đúng ca hiếm. Chủ chốt bỏ: quy đổi
    là việc của MÁY, người khai chỉ nên thấy một chip.
    """
    return don_gia / 1000.0 if don_vi_gia == "tan" else don_gia


def luong_tu_cong_thuc(formula_str: str, eval_ctx: dict) -> float | None:
    """LƯỢNG tiêu thụ suy ngược từ công thức TIỀN — đặt mọi biến đơn giá = 1 (Đợt 4 · L).

    Công thức tiền của vật tư luôn có dạng *lượng × đơn giá* (tiền bắt buộc tỉ lệ thuận với giá),
    nên thay đơn giá bằng 1 thì kết quả chính là lượng, theo đúng đơn vị của đơn giá::

        mực CMYK  `so_mau * dai_in * rong_in * don_gia_vat_tu * to_dau_vao * 0.0003` → **kg**
        màng bóng `dai_in * rong_in * don_gia_vat_tu * to_sau_in`                → **m²**

    (Chú thích cũ ở đây nói hai công thức trên "sai thang 10⁶ vì `dai_in`/`rong_in` là milimét" —
    ĐÃ LỖI THỜI, gỡ 11/08/2026. Engine chia 1000 TRƯỚC khi bơm nên trong công thức chúng là MÉT:
    mực CMYK ra 14,02 kg cho 11.683 m² = 1,20 g/m², đúng mức thực tế của offset 4 màu.)

    Hàm này trả đúng cái công thức nói, kể cả khi công thức sai: nó không có cách nào biết xưởng
    định lấy đơn vị gì.

    Cách này KHÔNG đụng công thức tính giá và KHÔNG bắt khai định mức riêng — đúng ranh giới plan
    chốt: kế hoạch chỉ *hỏi* "lệnh này cần bao nhiêu" rồi đọc con số.

    Trả `None` (KHÔNG đoán) khi công thức không hề nhắc tới đơn giá — vd một khoản phí phẳng
    `50000`: đặt đơn giá = 1 sẽ ra "50000 kg", một con số vô nghĩa mà lại trông như thật.
    """
    if not formula_str or not formula_str.strip():
        return None
    if not any(re.search(rf"\b{b}\b", formula_str) for b in _BIEN_DON_GIA):
        return None
    ctx = dict(eval_ctx)
    for b in _BIEN_DON_GIA:
        ctx[b] = 1.0
    try:
        luong = safe_eval(formula_str, ctx)
    except Exception:
        return None
    return luong if luong > 0 else None


def format_substituted_formula(formula_str: str, variables: dict) -> str:
    if not formula_str or not formula_str.strip():
        return ""
    word_regex = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
    def replacer(match):
        word = match.group(1)
        if word in MATH_FUNCS:
            return word
        if word in variables:
            val = variables[word]
            return f"{word}({_vi(val)})"
        return word
    substituted = word_regex.sub(replacer, formula_str)
    substituted = substituted.replace('*', ' × ').replace('/', ' ÷ ').replace('-', ' − ').replace('+', ' + ')
    substituted = re.sub(r'\s+', ' ', substituted).strip()
    return substituted


# 2 nhóm duy nhất (§1.6): Nguyên vật liệu (giấy + vật tư) · Công đoạn (chế bản/in/gia công).
_COLS = {
    "nvl": [
        {"key": "ten", "label": "Nguyên vật liệu", "align": "left", "kind": "text"},
        {"key": "so_to", "label": "SL tờ", "align": "right", "kind": "number"},
        {"key": "don_gia", "label": "Đơn giá", "align": "right", "kind": "money"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "gia_don_sp", "label": "đ/TP", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức thế số", "align": "left", "kind": "formula"},
    ],
    "cong_doan": [
        {"key": "ten", "label": "Công đoạn", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "gia_don_sp", "label": "đ/TP", "align": "right", "kind": "money"},
        # Bỏ cột "Ghi chú" (25/08/2026): 100% dòng để trống nên bảng gánh một cột rỗng. Hai thứ
        # từng rơi vào đó nay về đúng chỗ — lỗi công thức đã nằm ở `warnings` + ô Diễn giải, còn
        # "thuê ngoài" đi liền TÊN BƯỚC (xem dưới) để đọc một dòng là biết ai làm.
        {"key": "cong_thuc", "label": "Công thức thế số", "align": "left", "kind": "formula"},
    ],
    # GIAO HÀNG — nhóm thứ ba, CHỈ mọc khi sản phẩm có khai phí (xem `compute_phieu`). Cùng bộ cột
    # với Công đoạn vì cùng bản chất "một khoản tiền + diễn giải", không có số tờ để bày.
    "giao_hang": [
        {"key": "ten", "label": "Giao hàng", "align": "left", "kind": "text"},
        {"key": "thanh_tien", "label": "Số tiền", "align": "right", "kind": "money"},
        {"key": "gia_don_sp", "label": "đ/TP", "align": "right", "kind": "money"},
        {"key": "cong_thuc", "label": "Công thức thế số", "align": "left", "kind": "formula"},
    ],
}
_NAMES = {"nvl": "Nguyên vật liệu", "cong_doan": "Công đoạn", "giao_hang": "Giao hàng"}


def chuan_hoa_cot(result: dict | None) -> dict | None:
    """Đắp lại `columns` của ẢNH CHỤP cũ theo khai báo HIỆN TẠI (`_COLS`) — trả bản MỚI, không sửa.

    Cột là CÁCH BÀY, không phải dữ liệu: ảnh chụp giữ nguyên số tiền của lần tính cũ (chủ ý —
    xem `tinh_gia_service`), còn bảng bày mấy cột là chuyện của hôm nay. Không có hàm này thì
    phiếu tính trước 25/08/2026 vẫn kéo theo cột "Ghi chú" đã bỏ, tới khi ai đó bấm Tính giá lại.
    """
    if not result or not isinstance(result.get("groups"), list):
        return result
    groups = [{**g, "columns": _COLS.get(g.get("idx")) or g.get("columns")}
              for g in result["groups"]]
    return {**result, "groups": groups}

# Loại dụng cụ ĐƯỢC PHÉP mang phí khuôn — dao lưu kho, mua một lần rồi cất kho dùng lại.
# `kem` (bản kẽm) CỐ Ý ĐỨNG NGOÀI: nó là vật tư tiêu hao, mỗi bài phơi mới, và tiền nó đã nằm
# trong công thức của bước chế bản (`so_kem × đơn giá`). Cho nó ô phí nữa là tính hai lần.
TOOLING_CO_PHI = frozenset({"khuon_be", "khuon_ep", "khung_lua"})
# Nhãn đọc được của loại dao — vào thẳng tên dòng tiền ("Xén 3 mặt · phí khuôn bế"). Khớp
# `DAO_CO_PHI` bên frontend; lệch thì hai màn gọi cùng một con dao bằng hai tên.
TOOLING_NHAN = {"khuon_be": "khuôn bế", "khuon_ep": "khuôn ép nhũ / dập nổi", "khung_lua": "khung lụa"}


def _canh_bao_khuon(chain: list[dict]) -> list[str]:
    """Lời nhắc về phí khuôn, đọc theo NGUỒN KHUÔN sale đã chọn (chốt 04/09/2026).

    · `co_san` → im lặng: đó là một câu trả lời đúng, không phải chỗ trống bị bỏ quên.
    · `lam_moi` mà 0đ → nhắc: đã chọn làm dao mới thì phải có tiền, không thì báo giá thiếu.
    · chưa chọn (NULL, phiếu cũ) → giữ nguyên lời nhắc cũ.

    Gom MỘT câu cho cả chuỗi thay vì kêu từng bước — ba bước cần dao là ba dòng đọc rất mệt, mà
    nhắc nhiều thì người lập phiếu tắt mắt với lời nhắc.
    """
    thieu_cu: list[str] = []
    thieu_moi: list[str] = []
    for row in chain:
        cd = row.get("cong_doan") or {}
        if not cd.get("requires_tooling") or cd.get("tooling_type") not in TOOLING_CO_PHI:
            continue
        if _f(row.get("phi_khuon")) > 0:
            continue
        ten_b = row.get("ten") or cd.get("ten") or "Công đoạn"
        nguon = row.get("khuon_nguon")
        if nguon == "co_san":
            continue
        (thieu_moi if nguon == "lam_moi" else thieu_cu).append(ten_b)
    ra: list[str] = []
    if thieu_moi:
        ra.append(
            "Đã chọn làm khuôn mới nhưng chưa nhập tiền khuôn: "
            + ", ".join(thieu_moi) + " — báo giá đang thiếu khoản này."
        )
    if thieu_cu:
        ra.append(
            "Chưa cho biết khuôn có sẵn hay làm mới: " + ", ".join(thieu_cu)
            + " — để trống thì hiểu là dùng khuôn cũ, không tính tiền."
        )
    return ra


def _pre(name: str, label: str) -> str:
    name = (name or "").strip()
    return f"{name} · {label}" if name else label


def _ten_buoc(row: dict) -> str:
    """Tên bước để HIỆN — dòng gắn danh mục thì lấy tên SỐNG của danh mục.

    Phiếu chỉ chụp ảnh SỐ TIỀN (xem `tinh_gia_service.danh_muc_doi_sau_khi_tinh`), KHÔNG chụp
    ảnh CÁI TÊN: xưởng đổi tên một công đoạn là mọi phiếu phải gọi nó bằng tên mới, nếu không
    người đọc phiếu và người đứng máy nói hai tên cho cùng một việc. `row["ten"]` (tên chép lúc
    thêm bước) chỉ còn dùng cho dòng TỰ NHẬP — dòng không có `cong_doan_id` thì không có danh
    mục nào để hỏi. Ưu tiên `ten_hien_thi` cho khớp chip bên màn phiếu (`cdName` bên FE).
    """
    cd = row.get("cong_doan") or {}
    return cd.get("ten_hien_thi") or cd.get("ten") or row.get("ten") or "Công đoạn"


def _fit(outer_d: float, outer_r: float, inner_d: float, inner_r: float) -> int:
    """Số ô (inner) xếp vừa vào (outer) — thử cả 2 hướng, lấy max. 0 nếu không vừa."""
    if inner_d <= 0 or inner_r <= 0 or outer_d <= 0 or outer_r <= 0:
        return 0
    straight = floor(outer_d / inner_d) * floor(outer_r / inner_r)
    rotated = floor(outer_d / inner_r) * floor(outer_r / inner_d)
    return max(straight, rotated)


def _suc_chua(usable: float, canh: float, khe: float) -> int:
    """Số ô xếp trên 1 chiều: k×cạnh + (k−1)×khe ≤ usable ⟺ k ≤ (usable+khe)/(cạnh+khe). >= 0."""
    buoc = canh + khe
    if buoc <= 0 or usable <= 0:
        return 0
    return max(floor((usable + khe) / buoc), 0)


def chua_theo_chieu(tp: dict) -> tuple[float, float]:
    """Chừa của một thành phần → (chừa chiều DÀI, chừa chiều RỘNG), mm.

    NGUỒN LÀ DANH MỤC MÁY. Chừa tờ in là đặc tính của máy in, không phải của bài — khai một lần ở
    máy thì mọi phiếu chọn máy đó ăn theo:
      · DÀI  ← nhíp GIẤY (1 đầu, cạnh nạp) + đuôi/thanh màu (`nhip_giay_mm` + `duoi_thang_mau_mm`).
      · RỘNG ← lề hông ×2 (`le_hong_mm`, trừ mỗi bên).

    KHÔNG gộp một số trừ đều hai chiều — nhíp là mép máy kẹp ở CẠNH NẠP, không ăn chiều rộng.
    Chỉ dùng nhíp GIẤY; mép nhíp trên BẢN KẼM (~44mm) là chuyện khác, dùng nhầm là hụt 14-19% số con.

    Đè duy nhất còn lại: `chua_nhip` trên phiếu — khoản đổi theo job (hướng bài, cạnh nạp). Lề hông
    · đuôi · xén · cả gáy đã bỏ khỏi phiếu (mig 0139): chúng chưa từng có chỗ nhập, mà xén/gáy còn
    bị cộng đều cả hai chiều nên chỉ làm số con sai lệch âm thầm.

    ĐÂY LÀ BẢN DUY NHẤT của phép cộng này. Màn lệnh sản xuất từng tự cộng năm khoản thành một số
    rồi trừ đều hai chiều nên vẽ sơ đồ ra 105 con trong khi phiếu tính giá ra 99 — cùng một tờ,
    hai hình khác nhau.
    """
    nhip = _f(tp.get("chua_nhip")) or _f(tp.get("nhip_giay_mm"))
    duoi = _f(tp.get("duoi_thang_mau_mm"))
    le_hong = _f(tp.get("le_hong_mm"))
    return nhip + duoi, le_hong * 2


def binh_bai_layout(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                    chua_mm: float = 0.0, chua_dai_mm: float | None = None,
                    chua_rong_mm: float | None = None,
                    bleed_mm: float = 0.0, khe_cat_mm: float = 0.0) -> dict:
    """Bình bài ③ lên ② (trừ chừa) — trả LAYOUT đầy đủ để FE vẽ sơ đồ ĐÚNG engine.

    CHỪA TÁCH THEO CHIỀU: `chua_dai_mm` (nhíp giấy + đuôi/thanh màu — cạnh nạp, ăn chiều DÀI) và
    `chua_rong_mm` (lề hông 2 bên — ăn chiều RỘNG). Bỏ trống CẢ HAI thì lùi về `chua_mm` trừ đều
    mỗi chiều như bản cũ — caller cũ giữ nguyên hành vi.

    Con để bình = ③ + 2×`bleed_mm` mỗi chiều (tràn lề); giữa 2 con kề nhau chừa `khe_cat_mm`
    (n con chỉ có n−1 khe, không phải n).

    Trả {con, cols, rows, rotated, usable_dai, usable_rong, chua_dai, chua_rong, piece_dai,
    piece_rong, kho_in_dai, kho_in_rong, dai_tp, rong_tp}. cols = theo chiều RỘNG, rows = chiều DÀI.
    """
    chua_d = _f(chua_mm) if chua_dai_mm is None else _f(chua_dai_mm)
    chua_r = _f(chua_mm) if chua_rong_mm is None else _f(chua_rong_mm)
    bleed, khe = max(_f(bleed_mm), 0.0), max(_f(khe_cat_mm), 0.0)
    piece_d = dai_tp + 2 * bleed if dai_tp > 0 else dai_tp
    piece_r = rong_tp + 2 * bleed if rong_tp > 0 else rong_tp
    usable_d = max(kho_in_dai - chua_d, 0.0)
    usable_r = max(kho_in_rong - chua_r, 0.0)
    base = {"kho_in_dai": kho_in_dai, "kho_in_rong": kho_in_rong,
            "dai_tp": dai_tp, "rong_tp": rong_tp,
            "usable_dai": usable_d, "usable_rong": usable_r,
            "chua_dai": chua_d, "chua_rong": chua_r,
            "piece_dai": piece_d, "piece_rong": piece_r}
    if piece_d <= 0 or piece_r <= 0 or usable_d <= 0 or usable_r <= 0:
        return {**base, "con": 0, "cols": 0, "rows": 0, "rotated": False}
    s_rows = _suc_chua(usable_d, piece_d, khe)      # thẳng
    s_cols = _suc_chua(usable_r, piece_r, khe)
    r_rows = _suc_chua(usable_d, piece_r, khe)      # xoay 90°
    r_cols = _suc_chua(usable_r, piece_d, khe)
    if r_rows * r_cols > s_rows * s_cols:
        rows, cols, rot = r_rows, r_cols, True
    else:
        rows, cols, rot = s_rows, s_cols, False
    con = rows * cols
    if con == 0:                      # không vừa → không vẽ lưới lệch (1 chiều lọt vẫn = 0 con)
        rows = cols = 0
    return {**base, "con": con, "cols": cols, "rows": rows, "rotated": rot}


def binh_bai_con(*, kho_in_dai: float, kho_in_rong: float, dai_tp: float, rong_tp: float,
                 chua_mm: float = 0.0, chua_dai_mm: float | None = None,
                 chua_rong_mm: float | None = None,
                 bleed_mm: float = 0.0, khe_cat_mm: float = 0.0) -> int:
    """Số con/tờ in (chỉ số) — bọc `binh_bai_layout`. mm. >= 0."""
    return binh_bai_layout(kho_in_dai=kho_in_dai, kho_in_rong=kho_in_rong,
                           dai_tp=dai_tp, rong_tp=rong_tp, chua_mm=chua_mm,
                           chua_dai_mm=chua_dai_mm, chua_rong_mm=chua_rong_mm,
                           bleed_mm=bleed_mm, khe_cat_mm=khe_cat_mm)["con"]


def _vi(n) -> str:
    """Số → chuỗi vi-VN (chấm ngăn nghìn, phẩy thập phân) cho ghi chú diễn giải."""
    n = _f(n)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _ct(dan: str, tien: float, sl: int) -> str:
    """Công thức đã-THAY-SỐ cho phiếu in: '<dẫn giải> ÷ <SL> = <đ/sp>'. sl≤0 → chỉ tổng.

    `dan` = chuỗi dẫn giải cho ra `tien` (vd '24 × 28.000đ'). Cho người đọc tự cộng lại được.
    """
    tien = _f(tien)
    if sl <= 0:
        return f"{dan} = {_vi(tien)}đ"
    # Diễn giải đã có phép chia của CHÍNH NÓ ⇒ đóng ngoặc trước khi nối "÷ SL". Không ngoặc thì
    # đọc lên là "a ÷ b ÷ 4.000" — không ai biết vế nào chia cho vế nào. Trước 25/08/2026 chỗ gọi
    # xử lý bằng cách BỎ LUÔN vế "÷ SL" khi thấy dấu ÷, nên công thức có phép chia thì mất hẳn số
    # đ/sp — đúng chỗ người dùng kêu ở dòng Giấy.
    ve = f"({dan})" if "÷" in dan else dan
    return f"{ve} ÷ {_vi(sl)} = {_vi(round(tien / sl, 2))}đ/sp"


def _chia_duoc(dan: str) -> bool:
    """`dan` là diễn giải THẬT hay là câu báo lỗi ('thiếu công thức — 0đ')? Câu báo lỗi mà nối
    thêm '÷ 4.000 = 0đ/sp' thì đọc như một phép tính có thật."""
    return "đ/sp" not in dan and "thiếu" not in dan and "lỗi" not in dan


def _step_cost_safe(cd: dict, ctx: dict, warnings: list[str], ten: str) -> tuple[float, str]:
    """Tiền 1 công đoạn theo compute_step_cost, KHÔNG crash. Ghi chú = diễn giải `số × đơn giá`."""
    try:
        res = compute_step_cost(cd, ctx)
    except Exception as e:  # noqa: BLE001 — không crash, gom vào warnings
        warnings.append(f"Công đoạn '{ten}': không tính được ({e}) — tính 0đ.")
        return 0.0, "lỗi cấu hình — 0đ"
    rate = res.get("rate_used")
    bq = res.get("basis_qty")
    ghi = f"{_vi(bq)} × {_vi(rate)}đ" if (rate is not None and bq is not None) else ""
    return _f(res.get("total")), ghi


def _compute_one(tp: dict, so_luong_mac_dinh: int, warnings: list[str], flags: dict, bu_hao_rows: list[dict]) -> dict:
    """Tính chi phí 1 SẢN PHẨM → 2 nhóm (nvl · cong_doan). Trả {name, rows, total, meta}."""
    name = tp.get("ten") or ""
    sl = _i(tp.get("so_luong")) or _i(so_luong_mac_dinh)   # SL của sản phẩm này; 0 → SL mặc định phiếu
    # Số TRANG nội dung của 1 sản phẩm + số trang mỗi tay gấp — người dùng khai, engine LƯU.
    # Số tờ in đi thẳng từ đây (`sl × so_trang / con`), không qua "số bài in" nữa: chia số TAY cho
    # số CON là chia hai đại lượng khác đơn vị, sách bình tay vì thế ra sai.
    so_trang = max(_i(tp.get("so_trang"), 1), 1)
    trang_moi_tay = max(_i(tp.get("trang_moi_tay"), 1), 1)
    # Số TAY = số bài in (khuôn) — DẪN XUẤT, mỗi tay 1 bộ kẽm. Sách 160 trang tay 16 → 10 tay.
    # Tờ rời 1/1 → 1 tay, y như trước.
    so_tay = max(ceil(so_trang / trang_moi_tay), 1)
    so_to_per_sp = so_tay
    qc = tp.get("quy_cach_in", "mot_mat")
    passes = 1 if qc == "mot_mat" else 2                    # số mặt qua máy (2 mặt / tự trở = 2)

    # --- Khổ (mm) ---
    kho_ng_d = _f(tp.get("kho_dai"))     # giấy nguyên ①
    kho_ng_r = _f(tp.get("kho_rong"))
    kho_in_d = _f(tp.get("kho_in_dai"))  # tờ in ② (= VÙNG IN khi chọn máy) → bình bài con + m²
    kho_in_r = _f(tp.get("kho_in_rong"))
    if kho_in_d <= 0 or kho_in_r <= 0:   # thiếu khổ in → in thẳng khổ giấy nguyên (không xả)
        kho_in_d, kho_in_r = kho_ng_d, kho_ng_r
    # Cảnh báo: khổ tờ in > khổ giấy nguyên (bất khả thi vật lý) → bình bài trên vùng ảo, số con
    # thổi phồng, giá thành thiếu. MÁY CHỈ GHI NHẬN — chỉ nhắc, KHÔNG tự sửa/chặn.
    if kho_ng_d > 0 and kho_ng_r > 0 and (kho_in_d > kho_ng_d or kho_in_r > kho_ng_r):
        warnings.append(
            f"Thành phần '{name}': khổ tờ in {kho_in_d:g}×{kho_in_r:g} lớn hơn khổ giấy "
            f"{kho_ng_d:g}×{kho_ng_r:g} — số con có thể sai (bình bài vượt khổ giấy)."
        )
    # Khổ giấy CHẠY máy (cho XẢ GIẤY): khác khổ tờ in ② (vùng in) khi chọn máy. Thiếu → = khổ tờ in.
    kho_may_d = _f(tp.get("kho_may_dai")) or kho_in_d
    kho_may_r = _f(tp.get("kho_may_rong")) or kho_in_r
    # A: khổ tờ in KHÔNG lọt khổ giấy MÁY nhận (kho_may = kho_max máy) — máy không kẹp/chạy được tờ
    # này (xét cả XOAY qua `_fit`). Chỉ nhắc, không chặn. Không có máy → kho_may = kho_in → luôn lọt.
    if kho_may_d > 0 and kho_may_r > 0 and _fit(kho_may_d, kho_may_r, kho_in_d, kho_in_r) < 1:
        warnings.append(
            f"Thành phần '{name}': khổ tờ in {kho_in_d:g}×{kho_in_r:g} lớn hơn khổ giấy máy nhận "
            f"{kho_may_d:g}×{kho_may_r:g} — máy không chạy được tờ này."
        )
    dai_tp = _f(tp.get("dai_thanh_pham"))    # thành phẩm ③
    rong_tp = _f(tp.get("rong_thanh_pham"))
    chua_dai, chua_rong = chua_theo_chieu(tp)
    bleed = _f(tp.get("bleed_mm"))
    khe_cat = _f(tp.get("khe_cat_mm"))

    # --- ④ con/tờ: auto bình bài, override được ---
    con_auto = tp.get("con_auto", True)
    con = 0
    if con_auto and dai_tp > 0 and rong_tp > 0 and kho_in_d > 0 and kho_in_r > 0:
        lay = binh_bai_layout(kho_in_dai=kho_in_d, kho_in_rong=kho_in_r,
                              dai_tp=dai_tp, rong_tp=rong_tp,
                              chua_dai_mm=chua_dai, chua_rong_mm=chua_rong,
                              bleed_mm=bleed, khe_cat_mm=khe_cat)
        con = lay["con"]
        # Bài (phần đặt con, chưa kể chừa) phải lọt VÙNG IN máy — chỉ nhắc, KHÔNG chặn/tự sửa.
        vung_d, vung_r = _f(tp.get("vung_in_dai")), _f(tp.get("vung_in_rong"))
        if con > 0 and vung_d > 0 and vung_r > 0:
            bai_d = lay["rows"] * (lay["piece_rong"] if lay["rotated"] else lay["piece_dai"])
            bai_r = lay["cols"] * (lay["piece_dai"] if lay["rotated"] else lay["piece_rong"])
            bai_d += max(lay["rows"] - 1, 0) * khe_cat
            bai_r += max(lay["cols"] - 1, 0) * khe_cat
            if bai_d > vung_d + 1e-6 or bai_r > vung_r + 1e-6:
                warnings.append(
                    f"Thành phần '{name}': bài bình {bai_d:g}×{bai_r:g} vượt vùng in máy "
                    f"{vung_d:g}×{vung_r:g} — máy không in hết bài."
                )
        if con < 1:
            warnings.append(f"Thành phần '{name}': khổ thành phẩm lớn hơn khổ tờ in — bình bài = 0, tạm 1 con/tờ.")
            con = 1
    if con < 1:
        con = max(_i(tp.get("so_con"), 1), 1)   # fallback: nhập tay

    # --- Số mảnh xả (② lên ①): cắt tờ giấy CHẠY MÁY (kho_may) từ giấy nguyên, KHÔNG dùng vùng in ---
    xa = _fit(kho_ng_d, kho_ng_r, kho_may_d, kho_may_r) if (kho_ng_d > 0 and kho_ng_r > 0) else 1
    xa = max(xa, 1)

    # --- Số tờ CẦN in (net) — tính TRƯỚC để tra bù hao THEO SỐ TỜ (không phải số lượng) ---
    # HAI KIỂU LÀM khác hẳn nhau, `trang_moi_tay` là thứ phân biệt (không cần thêm cờ nào):
    #  · GẤP TAY (sách, trang mỗi tay > 1): tờ in gấp NGUYÊN VẸN thành một tay → 1 tờ = 1 tay, một
    #    cuốn cần `so_tay` tờ. Tờ không bị cắt rời nên `con` KHÔNG vào công thức — nó chỉ để vẽ sơ
    #    đồ bình bài và kiểm khổ có vừa tờ. Bật/tắt `con_auto` vì thế không làm sai số giấy.
    #  · CẮT RỜI (tờ rơi, danh thiếp, hộp): một tờ cắt ra `con` cái.
    # `cai_moi_to` dùng lại làm HỆ SỐ quy đổi tờ↔cái cho chuỗi bù hao ngược ở dưới — một nguồn duy
    # nhất, khỏi hai chỗ tính lệch nhau.
    cai_moi_to = cau_to_sang_cai(trang_moi_tay=trang_moi_tay, so_trang=so_trang, con=con)
    to_net = ceil(sl / cai_moi_to) if sl > 0 and cai_moi_to > 0 else 0

    # --- Bù hao NGƯỢC theo công đoạn: đi từ CUỐI chuỗi lên, mỗi bước tra bậc theo số đi qua CHÍNH
    # NÓ, ở ĐÚNG đơn vị của nó (bước in rơi bậc cao hơn bước xén cuối — cộng xuôi phẳng theo
    # `to_net` thì mọi bước tra cùng một bậc). LUÔN tính: cột `tinh_bu_hao_cd` đã XOÁ (mg `0201`),
    # tắt bù hao tự là mở đường cho báo giá hụt giấy mà không ai biết. Muốn cộng thêm thì có ô
    # "+ Bù thêm"; muốn bớt thì đi sửa định mức của công đoạn. ---
    chain = tp.get("thanh_phams") or []

    def _tram(cd: dict, dau: str) -> str | None:
        """TRẠM dòng giấy ở một đầu của bước. Tầng gọi (`tinh_gia_service`) tra danh mục rồi bơm
        `tram_vao`/`tram_ra` vào đây — engine này là hàm THUẦN, không đụng DB được.

        Thiếu khoá đó thì lùi về chính mã đơn vị: đúng với dữ liệu thời chỉ 5 mã dòng giấy khai
        được, và giữ cho các test gọi thẳng engine bằng dict tự dựng vẫn chạy như cũ.
        """
        return cd.get(f"tram_{dau}", cd.get(f"don_vi_{dau}"))

    # Bước ở trên DÒNG GIẤY = CẢ HAI đầu đứng ở một trạm. Ghi kẽm khai `bai → kem` (hai đầu ngoài
    # trạm) nên tự rơi ra khỏi đây — không cần luật riêng theo `nhom`.
    idx_giay = [i for i, r in enumerate(chain)
                if _tram(r.get("cong_doan") or {}, "vao")
                and _tram(r.get("cong_doan") or {}, "ra")]
    # Bước rơi khỏi dòng giấy thì bù hao của nó biến mất KHÔNG kèn không trống — phải kêu, đừng để
    # số 0 im lặng. Trừ chế bản: nó vốn không chạm giấy, kêu là kêu oan mỗi phiếu.
    for i, r in enumerate(chain):
        cd = r.get("cong_doan") or {}
        if i not in idx_giay and cd.get("nhom") != "prepress":
            thieu = not (cd.get("don_vi_vao") and cd.get("don_vi_ra"))
            ly_do = ("chưa khai đơn vị vào/ra" if thieu
                     else f"đơn vị {cd.get('don_vi_vao')} → {cd.get('don_vi_ra')} không nằm trên "
                          f"dòng giấy")
            warnings.append(
                f"Thành phần '{name}': công đoạn '{r.get('ten') or cd.get('ten') or '?'}' {ly_do} "
                f"— không được tính vào dòng giấy (bù hao của nó bỏ qua)."
            )
    # Đơn vị vào/ra KHAI ở danh mục công đoạn. HỆ SỐ thì phiếu cấp — `con` (bình bài) và `xa`
    # (số mảnh xả) đã tính ở trên, khai lại vào danh mục là đẻ nguồn sự thật thứ hai.
    # Ranh giới tờ in → cái: cắt rời thì 1 tờ ra `con` cái; GẤP TAY thì ngược chiều — phải gom
    # `so_tay` tờ mới ra 1 cuốn (hệ số 1/so_tay). Không có nó, chuỗi ngược chạy 1:1 và mỗi cuốn
    # hỏng ở bước xén chỉ đòi bù 1 tờ thay vì `so_tay` tờ.
    # Sách còn đi ĐƯỜNG DÀI qua TAY: gấp (tờ in → tay) rồi bắt tay + vào keo (tay → cuốn). Cầu
    # đầu là 1 — gấp không sinh không mất tờ; cầu sau vì thế phải gánh trọn `cai_moi_to`, và lấy
    # THẲNG biến đó chứ không gõ lại `1/so_tay`: tích hai cầu buộc phải bằng đúng cầu tắt
    # `to → cai`, hai công thức song song là hai chỗ để lệch nhau.
    # Tờ rời cũng có ĐƯỜNG DÀI qua CON, tuỳ người khai đặt đầu ra bước bế/cắt là `con` hay thẳng
    # `thành phẩm`: 1 tờ cắt ra 49 con, mỗi con là một thẻ nên `con → thành phẩm` = 1. Viết dạng
    # CHIA thay vì hằng số 1 để tích hai cầu luôn khoá bằng cầu tắt — mai kia có hàng cần 2 con
    # ghép thành 1 thành phẩm (thân hộp + nắp) thì `cai_moi_to` đổi là cầu này tự đổi theo.
    # Số giấy hai đường ra như nhau; khác nhau ở chỗ bù hao tra bậc theo CON hay theo TỜ.
    # Thiếu hai cầu này thì lệnh sản xuất (đã có đủ) và phiếu tính giá ra hai số giấy khác nhau.
    # Khoá theo TRẠM (không theo mã đơn vị): xưởng khai mã riêng cho một chặng thì cặp mã không có
    # trong bảng này, engine ăn hệ số 1 và số giấy sai — im lặng.
    so_con_qd = float(max(int(con or 0), 1))
    he_so_dv = {
        (TRAM_TO, TRAM_CAI): cai_moi_to, (TRAM_TO_NGUYEN, TRAM_TO): float(xa),
        (TRAM_TO, TRAM_TAY): 1.0, (TRAM_TAY, TRAM_CAI): cai_moi_to,
        (TRAM_TO, TRAM_CON): so_con_qd, (TRAM_CON, TRAM_CAI): cai_moi_to / so_con_qd,
    }
    buoc_in = []
    for i in idx_giay:
        cd = chain[i].get("cong_doan") or {}
        buoc_in.append({
            "cd": cd,
            "ten": chain[i].get("ten") or cd.get("ten") or "Công đoạn",
            "dv_vao": cd.get("don_vi_vao"),
            "dv_ra": cd.get("don_vi_ra"),
            "tram_vao": _tram(cd, "vao"),
            "tram_ra": _tram(cd, "ra"),
        })
    # Đích của chuỗi nói bằng đúng thứ bước CUỐI nhả ra — kết ở thành phẩm thì là SL đặt, kết ở con
    # thì là số con, kết ở tờ thì là số tờ. Một công thức chung với lệnh sản xuất, xem `dich_chuoi`.
    tram_cuoi = buoc_in[-1]["tram_ra"] if buoc_in else None
    to_can = dich_chuoi(sl, tram_ra_cuoi=tram_cuoi, cai_moi_to=cai_moi_to, he_so=he_so_dv)
    buoc_giay, canh_bao_dv = chuoi_nguoc_dv(
        buoc_in, rows=bu_hao_rows, to_can=to_can, he_so=he_so_dv)
    for _c in canh_bao_dv:
        warnings.append(f"Thành phần '{name}': {_c}")

    # --- Số tờ: đọc RA KHỎI CHUỖI tại đúng ranh giới đơn vị, không tính riêng bên ngoài ---

    def _vao_tai(tram: str) -> float | None:
        """Số lượng VÀO của bước đầu tiên đứng ở TRẠM `tram` — mốc cần ở ranh giới đó.

        Dò theo TRẠM chứ không theo mã: xưởng khai mã riêng cho chặng tờ in (`to_in`) thì dò mã
        không thấy, mốc rơi về `to_net` và MẤT SẠCH bù hao — hỏng im lặng, không cảnh báo nào.
        """
        return next((b["vao"] for b in buoc_giay if b.get("tram_vao") == tram), None)

    to_can_vao = _vao_tai(TRAM_TO)
    if to_can_vao is None:      # chuỗi rỗng, hoặc toàn bước không chạm tờ in
        to_can_vao = float(to_net)
    finishing_spoilage_sum = ceil(to_can_vao) - to_net       # Σ bù hao công đoạn (hiện trên panel)
    to_dau_vao = ceil(to_can_vao)
    # Chuỗi CÓ bước xả giấy → tờ nguyên đọc thẳng từ bước đó; không có thì quy đổi ở đây như cũ.
    _vao_nguyen = _vao_tai(TRAM_TO_NGUYEN)
    if _vao_nguyen is not None:
        to_nguyen = ceil(_vao_nguyen)
    else:
        to_nguyen = ceil(to_dau_vao / xa) if to_dau_vao > 0 else 0
    # Tờ TỐT còn lại sau in = `ra` của bước IN (bước in cuối nếu chuỗi có nhiều) — nuôi công thức
    # tiền của công đoạn sau in. Chuỗi không có bước in → giữ nguyên tờ vào máy (tương thích cũ).
    to_sau_in = float(to_dau_vao)
    for _i_row, _b in zip(idx_giay, buoc_giay):
        if (chain[_i_row].get("cong_doan") or {}).get("nhom") == "print":
            to_sau_in = float(ceil(_b["ra"]))
    # Phân rã từng bước cho UI: bước nào ăn bao nhiêu tờ. Chế bản KHÔNG có mặt (không chạm tờ).
    buoc = {i: b for i, b in zip(idx_giay, buoc_giay)}   # tra theo chỉ số dòng GỐC
    bu_hao_chi_tiet = [
        {
            # KHÓA GHÉP với dòng tiền (`rows["cong_doan"][].buoc_idx`): cùng là chỉ số dòng trong
            # `chain`. Bắt buộc phải có khóa vì hai danh sách KHÔNG cùng độ dài — chế bản không
            # chạm tờ nên vắng mặt ở đây mà vẫn có dòng tiền. Ghép bằng cách so TÊN thì hôm nào
            # xưởng đổi tên một công đoạn là tiền rơi khỏi thẻ mà không lỗi nào báo.
            "buoc_idx": i,
            "ten": _ten_buoc(chain[i]),
            "nhom": (chain[i].get("cong_doan") or {}).get("nhom"),   # UI neo "Tờ sau in" vào bước in
            "dv_vao": b["dv_vao"], "dv_ra": b["dv_ra"],   # UI hiện chỗ ĐỔI đơn vị
            "vao": ceil(b["vao"]),
            "ra": ceil(b["ra"]),
            # `ra` QUY về đơn vị vào + hệ số đã dùng. Không có hai số này thì dòng đổi đơn vị đọc
            # lên vô lý: "55 tờ in → 5.070 con" mà 55 × 210 = 11.550, người xem không kiểm được.
            # Ràng buộc: ra_quy + hao == vao (đúng theo cách `hao` tính ngay dưới).
            "ra_quy": ceil(b["ra"] / (he_so_dv.get((b["tram_vao"], b["tram_ra"])) or 1.0)),
            "he_so": he_so_dv.get((b["tram_vao"], b["tram_ra"])) or 1.0,
            # Hao đo bằng ĐƠN VỊ VÀO: bước bế vào 74 tờ ra 15.540 con thì hao là 50 TỜ, không phải
            # hiệu hai con số khác đơn vị.
            "hao": ceil(b["vao"]) - ceil(b["ra"] / (he_so_dv.get((b["tram_vao"], b["tram_ra"])) or 1.0)),
        }
        for i, b in zip(idx_giay, buoc_giay)
    ]
    # Khép mạch về ĐƠN VỊ KHÁCH ĐẶT: số ra khỏi bước cuối → số thành phẩm thật sự có.
    # Không có dòng này thì panel nhảy thẳng từ "5.000 cái" sang "24 tờ" mà giấu chỗ quy đổi.
    #
    # Bước cuối nhả ra thứ gì thì chia lại đúng cầu đó — nghịch đảo của `dich_chuoi`: kết ở thành
    # phẩm giữ nguyên, kết ở TỜ thì × số cái mỗi tờ, kết ở CON thì × cái/con. Bản cũ chỉ tách hai
    # ca (`cai` hay không) nên chuỗi kết ở `con` bị nhân nguyên `cai_moi_to` — đếm thừa `con` lần.
    to_ra_cuoi = ceil(buoc_giay[-1]["ra"]) if buoc_giay else to_dau_vao
    cau_cuoi = (1.0 if not tram_cuoi or tram_cuoi == TRAM_TO
                else float(he_so_dv.get((TRAM_TO, tram_cuoi)) or 1.0))
    so_tp_ra = floor(to_ra_cuoi * cai_moi_to / cau_cuoi) if cau_cuoi > 0 else 0

    # --- Mực in: TẬP mã mỗi mặt là nguồn sự thật; ba số màu là dẫn xuất ---
    muc_a, muc_b = tap_muc(tp.get("muc_a")), tap_muc(tp.get("muc_b"))
    if not muc_a and not muc_b:
        # Thành phần chỉ có ba con số (seed/script dựng tay, phiếu chưa qua backfill) → dựng tập
        # theo ĐÚNG luật migration `0154` dùng. Không có nhánh này thì chúng ra 0 kẽm lặng lẽ.
        muc_a, muc_b = tap_muc_tu_so(
            tp.get("so_mau_a"), tp.get("so_mau_b"), tp.get("so_mau_pha"))
    so_mau_a, so_mau_b, so_mau_pha = so_mau_dan_xuat(muc_a, muc_b)
    so_mau = so_mau_a + so_mau_b + so_mau_pha
    co_in = bool(tp.get("co_in", True))

    # --- Biến đổi đơn vị cho biến công thức (mm -> m) ---
    dai_tp_m = dai_tp / 1000.0
    rong_tp_m = rong_tp / 1000.0
    dai_nguyen_m = kho_ng_d / 1000.0
    rong_nguyen_m = kho_ng_r / 1000.0
    dai_in_m = kho_in_d / 1000.0
    rong_in_m = kho_in_r / 1000.0
    dinh_luong = _f(tp.get("gsm")) / 1000.0  # gsm / 1000 -> kg/m2 (0.25)

    # --- Số kẽm --- mỗi TAY một bộ bản (mỗi tay một nội dung khác), xem `so_kem_moi_tay`.
    kem_mau = so_kem_moi_tay(muc_a, muc_b, qc)
    so_kem = kem_mau * so_to_per_sp
    so_luot = to_dau_vao * passes

    # --- Ngữ cảnh biến dùng chung: dựng từ TỪ ĐIỂN, không khai lại dict ở đây ---
    # Trước 11/08/2026 đây là một dict rời, còn danh sách chip thì nằm cứng bên frontend — hai nửa
    # của cùng một sự thật, không gì ép khớp, và đã lệch thật (`so_mau_pha` có giá trị mà không gõ
    # được). Nay `bien_cong_thuc` là nguồn duy nhất; thiếu biến là TypeError ngay, không im lặng.
    ctx_vars = ngu_canh_phieu(
        dai_tp=dai_tp_m, rong_tp=rong_tp_m,
        dai_nguyen=dai_nguyen_m, rong_nguyen=rong_nguyen_m,
        dai_in=dai_in_m, rong_in=rong_in_m,
        so_luong=sl, so_tp=con,
        so_trang=so_trang, trang_moi_tay=trang_moi_tay,
        to_dau_vao=to_dau_vao, to_sau_in=to_sau_in, to_nguyen=to_nguyen,
        so_mau=so_mau, so_mau_pha=so_mau_pha, so_mat=passes, so_kem=so_kem,
        dinh_luong=dinh_luong,
    )

    # 2 nhóm: nvl (giấy + vật tư) · cong_doan (chế bản/in/gia công theo thứ tự routing).
    rows: dict[str, list[dict]] = {"nvl": [], "cong_doan": [], "giao_hang": []}

    # --- Giấy (Nguyên vật liệu) ---
    # GỠ 2026-08-09 (Đợt 4 · K): nhánh "khách cấp giấy → 0đ". Cột `nguon_giay` còn trong DB nhưng
    # engine KHÔNG đọc nữa — mọi thành phần đều tính tiền giấy theo công thức.
    # ⚠️ Phiếu CŨ có `nguon_giay='khach'` mở ra tính lại sẽ NHẢY GIÁ TĂNG (trước không tính tiền
    # giấy, nay có). Báo giá đã chốt không ảnh hưởng — chúng đã chụp giá tại thời điểm gửi.
    don_gia_giay = _f(tp.get("don_gia_giay"))
    don_vi = tp.get("don_gia_don_vi", "to")
    giay_ten = tp.get("giay_ten") or tp.get("kho_nguyen") or "Giấy"

    formula = tp.get("cong_thuc_gia")
    if not formula or not formula.strip():
        if don_vi in ("kg", "tan"):   # giấy bán theo CÂN → tiền = khối lượng × đ/kg
            formula = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_giay * to_nguyen"
        else:                          # to | ram | cai → tính theo tờ
            formula = "don_gia_giay * to_nguyen"

    eval_ctx = dict(ctx_vars)
    eval_ctx["don_gia_giay"] = _don_gia_co_so(don_gia_giay, don_vi)

    try:
        gia_giay = safe_eval(formula, eval_ctx)
    except Exception as e:
        warnings.append(f"Thành phần '{name}': lỗi công thức giấy ({e}) — tính 0đ.")
        gia_giay = 0.0

    rows["nvl"].append({
        # Nhóm `nvl` trộn GIẤY với vật tư (mực/màng/keo) trong cùng một danh sách. Panel số tờ của
        # sản phẩm cần tách riêng dòng giấy nên phải có cờ — dò bằng "dòng đầu tiên" là đúng hôm
        # nay và sai ngay hôm engine đổi thứ tự.
        "loai": "giay",
        "cong_thuc_goc": (formula or "").strip(),   # xem chú thích ở nhóm `cong_doan`
        "ten": _pre(name, giay_ten),
        "so_to": to_nguyen,
        "don_gia": _r(don_gia_giay),
        "thanh_tien": _r(gia_giay),
        "gia_don_sp": _r(gia_giay / sl) if sl > 0 else 0.0,
        # Nối vế "÷ SL = đ/sp" y như dòng công đoạn. Tiền giấy là khoản to nhất phiếu mà lại là
        # dòng DUY NHẤT không quy ra đơn giá/sản phẩm — người lập phiếu phải bấm máy tính tay để
        # so với mấy dòng công đoạn ngay bên dưới (kêu 25/08/2026).
        "cong_thuc": _ct(format_substituted_formula(formula, eval_ctx), gia_giay, sl),
    })

    # --- Vật tư in ấn thêm (mực/màng/keo…) → Nguyên vật liệu: thế biến vào CÔNG THỨC của vật tư
    # (HỆT giấy — công thức nằm ở danh mục vật tư, engine chỉ thế số). `don_gia_vat_tu` phơi sẵn. ---
    for vt in tp.get("vat_tus") or []:
        vt_ten = vt.get("ten") or "Vật tư"
        vt_formula = vt.get("cong_thuc_gia")
        vt_don_gia = _f(vt.get("don_gia"))
        vt_don_vi = vt.get("don_vi_gia", "kg")
        luong_vt = None
        if not vt_formula or not vt_formula.strip():
            warnings.append(f"Vật tư '{vt_ten}' (thành phần '{name}'): chưa có công thức — tính 0đ.")
            tien_vt, dan_vt = 0.0, "thiếu công thức — 0đ"
        else:
            eval_ctx = dict(ctx_vars)
            eval_ctx["don_gia_vat_tu"] = _don_gia_co_so(vt_don_gia, vt_don_vi)
            try:
                tien_vt = safe_eval(vt_formula, eval_ctx)
                dan_vt = format_substituted_formula(vt_formula, eval_ctx)
            except Exception as e:
                warnings.append(f"Vật tư '{vt_ten}': lỗi công thức ({e}) — tính 0đ.")
                tien_vt, dan_vt = 0.0, "lỗi công thức — 0đ"
            # LƯỢNG tiêu thụ (Đợt 4 · L) — suy từ chính công thức tiền, không khai định mức riêng.
            # `don_gia` đã quy về đơn vị cơ sở ở trên, nên lượng ra theo kg kể cả khi giá khai đ/tấn.
            luong_vt = luong_tu_cong_thuc(vt_formula, eval_ctx)
        rows["nvl"].append({
            "loai": "vat_tu",
            "cong_thuc_goc": (vt_formula or "").strip(),
            "ten": _pre(name, vt_ten),
            "so_to": to_dau_vao,
            "don_gia": _r(vt_don_gia),
            "thanh_tien": _r(tien_vt),
            "gia_don_sp": _r(tien_vt / sl) if sl > 0 else 0.0,
            "cong_thuc": _ct(dan_vt, tien_vt, sl) if _chia_duoc(dan_vt) else dan_vt,
            # Kế hoạch vật tư đọc hai field này. `None` = công thức không suy được lượng ⇒ KHÔNG
            # có dòng cân đối, thà thiếu còn hơn bịa một con số để đi mua hàng theo.
            # 4 số lẻ chứ KHÔNG dùng `_r` (2 số lẻ như tiền): lượng mực cho một lệnh nhỏ có thể là
            # 0,003 kg — làm tròn 2 số lẻ là biến nó thành 0 và dòng cân đối biến mất.
            "luong": round(luong_vt, 4) if luong_vt is not None else None,
            "luong_don_vi": vt_don_vi if luong_vt is not None else None,
            "vat_tu_id": vt.get("vat_tu_id"),
        })

    # Chuỗi công đoạn là NGUỒN DUY NHẤT: In / Chế bản phải nằm trong routing như mọi công đoạn
    # khác. KHÔNG tự đẻ dòng thay thế khi chuỗi thiếu — chỉ NHẮC để người dùng tự thêm.
    chain_nhoms = {((r.get("cong_doan") or {}).get("nhom")) for r in (tp.get("thanh_phams") or [])}
    if co_in and "print" not in chain_nhoms:
        warnings.append(f"Thành phần '{name}': chuỗi chưa có công đoạn IN — chưa tính tiền in.")
    if co_in and so_kem > 0 and "prepress" not in chain_nhoms:
        warnings.append(f"Thành phần '{name}': chuỗi chưa có công đoạn CHẾ BẢN/KẼM — chưa tính tiền kẽm.")

    # --- Công đoạn trong chuỗi (chế bản/in/gia công) theo thứ tự routing ---
    ctx_base = {
        "so_to_in_gross": to_net,
        "so_luong_thanh_pham": sl,
        "dt_to_in_cm2": (kho_in_d / 10.0) * (kho_in_r / 10.0),
        "so_con": con,
        "size_cm": max(dai_tp, rong_tp) / 10.0,
        "so_trang": 0, "so_cuon": 0, "so_bao": 0, "so_thung": 0,
    }

    for idx_buoc, row in enumerate(chain):
        cd = row.get("cong_doan") or {}
        ten_r = _ten_buoc(row)

        ctx = dict(ctx_base)
        # SỐ CỦA CHÍNH BƯỚC NÀY (đọc từ chuỗi ngược) — đây là hai chip `sl_vao`/`sl_ra` ở ô Công
        # thức tính giá của danh mục Công đoạn. Không có chúng thì công thức tiền chỉ với được
        # `to_dau_vao` — số tờ vào máy đã gồm bù hao của CẢ chuỗi — nên bước đứng sau in tính tiền
        # cả trên số tờ mà bước trước đã đốt. Đo trên phiếu thật: gấp tay chạm 5.000 mà tính 5.200.
        #
        # Đo bằng ĐƠN VỊ CỦA BƯỚC, đúng như hai con số panel đang hiện trên thẻ (`bu_hao_chi_tiet`):
        # bước gấp là 5.000 tờ → 5.000 tay, bước vào keo là 5.000 tay → 1.000 cuốn.
        #
        # Bước không nằm trên dòng giấy (chế bản: nhả kẽm, không chạm tờ) rơi về tờ vào máy — kẽm
        # phục vụ cả lượt in. KHÔNG để trống: công thức lỡ gõ `sl_vao` sẽ thiếu biến rồi ra 0đ.
        _b_nay = buoc.get(idx_buoc)
        ctx["sl_vao"] = ceil(_b_nay["vao"]) if _b_nay else to_dau_vao
        ctx["sl_ra"] = ceil(_b_nay["ra"]) if _b_nay else to_dau_vao
        # Kích thước/số lượng khung lụa của CHÍNH bước — ba ô nhập riêng ở phiếu, TÁCH BIỆT với
        # `phi_khuon`. Bơm cho MỌI bước (không chỉ bước khung lụa): công thức không gõ tới thì vô
        # hại, gõ tới mà không bơm mới là thứ nổ `KeyError` ở vòng `MA_TANG_BUOC_TIEN` dưới đây.
        ctx["dai_khung_lua"] = _f(row.get("dai_khung_lua"))
        ctx["rong_khung_lua"] = _f(row.get("rong_khung_lua"))
        ctx["so_khung_lua"] = _f(row.get("so_khung_lua"))
        # so_mat: dòng IN (nhom=print) LUÔN theo số mặt cách in (passes) — KHÔNG để field mặc định=1
        # nuốt (N2: model so_mat default=1 khiến fallback passes thành code chết). Finishing tự set
        # so_mat (cán 1/2 mặt); ≤0 → dùng passes.
        if cd.get("nhom") == "print":
            ctx["so_mat"] = passes
        else:
            _rm = _i(row.get("so_mat"))
            ctx["so_mat"] = _rm if _rm > 0 else passes
        ctx["so_vi_tri"] = _i(row.get("so_vi_tri"))
        ctx["dt_thanh_pham_cm2"] = _f(row.get("dien_tich"))

        formula = cd.get("cong_thuc_gia") if cd else None
        if formula and formula.strip():
            eval_ctx = dict(ctx_vars)
            eval_ctx["so_mat"] = ctx["so_mat"]
            # Bơm ĐỦ bộ biến tầng bước — `ngu_canh_phieu` không bơm được (nó chạy một lần cho cả
            # thành phần, chưa biết bước nào). Đọc theo danh sách khai thay vì gõ tay từng tên:
            # thêm biến tầng bước sau này mà quên bơm thì `KeyError` nổ ngay, không ra 0đ im lặng.
            for _ma in MA_TANG_BUOC_TIEN:
                eval_ctx[_ma] = ctx[_ma]

            try:
                tien = safe_eval(formula, eval_ctx)
                dan_d = format_substituted_formula(formula, eval_ctx)
            except Exception as e:
                warnings.append(f"Dòng '{ten_r}': lỗi công thức ({e}) — tính 0đ.")
                tien = 0.0
                dan_d = "lỗi công thức — 0đ"
        else:
            # Formula-only (chốt 2026-07-22, siết trọn 11/08/2026): công đoạn CHƯA khai công thức
            # → 0đ + cảnh báo, KHÔNG trừ nhóm nào. Không dùng fallback đơn giá routing / rate cũ
            # (tránh "×400đ ma" không ai chủ ý nhập).
            warnings.append(f"Công đoạn '{ten_r}': chưa khai công thức tính giá — tính 0đ.")
            tien = 0.0
            dan_d = "thiếu công thức — 0đ"

        cong_thuc = _ct(dan_d, tien, sl) if _chia_duoc(dan_d) else dan_d
        # Thuê ngoài đi LIỀN TÊN BƯỚC (chỗ cũ là cột "Ghi chú" đã bỏ): ai làm việc này là một
        # phần của việc, đọc rời sang cột khác thì mắt phải bắc cầu qua ba cột số.
        ten_dong = f"{ten_r} · thuê ngoài: {row['nha_cung_cap']}" if row.get("nha_cung_cap") else ten_r

        # MỌI công đoạn (chế bản/in/gia công) vào chung nhóm "Công đoạn", giữ thứ tự routing.
        rows["cong_doan"].append({
            "buoc_idx": idx_buoc,   # khóa ghép với `bu_hao_chi_tiet[].buoc_idx` — xem chú thích ở đó
            # Công thức NGUYÊN VĂN như người ta khai trong danh mục. `cong_thuc` bên dưới là bản đã
            # thế số — hai thứ khác nhau và panel cần CẢ HAI: một dòng nói "tính bằng gì", một dòng
            # nói "ra số nào". Chỉ có bản thế số thì người đọc không biết `5.200` là biến nào.
            "cong_thuc_goc": (formula or "").strip(),
            "ten": _pre(name, ten_dong),
            "thanh_tien": _r(tien),
            "gia_don_sp": _r(tien / sl) if sl > 0 else 0.0,
            "cong_thuc": cong_thuc,
        })


    # --- PHÍ KHUÔN: khoản MỘT LẦN, GỘP vào giá vốn ---------------------------------------------
    #
    # Chốt 15/08/2026: gộp thẳng thành dòng tiền trong nhóm Công đoạn để báo giá chỉ còn MỘT dòng.
    # Bản đầu tách riêng (giá vốn không gồm dao, báo giá đẻ dòng thứ hai) — chủ dự án đổi sang gộp
    # cho gọn khâu báo giá. Hệ quả đã biết: tiền dao bị chia theo sản lượng, xem chú thích ở dưới.
    #
    # CHỈ nhận phí ở bước có cờ dụng cụ là dao lưu kho. `kem` bị loại: bản kẽm là vật tư tiêu hao và
    # tiền nó đã nằm trong công thức của bước chế bản — lấy thêm ở đây là tính hai lần.
    khuon_dong: list[dict] = []
    for row in chain:
        cd = row.get("cong_doan") or {}
        if not cd.get("requires_tooling") or cd.get("tooling_type") not in TOOLING_CO_PHI:
            continue
        ten_b = row.get("ten") or cd.get("ten") or "Công đoạn"
        tien = _f(row.get("phi_khuon"))
        if tien > 0:
            nhan_dao = TOOLING_NHAN.get(cd.get("tooling_type") or "", "khuôn")
            khuon_dong.append({"ten": ten_b, "loai": cd.get("tooling_type"), "thanh_tien": _r(tien)})
            # Thành DÒNG TIỀN THẬT trong nhóm Công đoạn ⇒ `total` cộng nó vào, kéo theo `gia_von_tp`
            # và đơn giá/sản phẩm. Chủ dự án chọn gộp (15/08/2026) để báo giá chỉ còn MỘT dòng.
            #
            # ⚠️ Hệ quả đã biết và đã chấp nhận: tiền dao KHÔNG đổi theo sản lượng nên khi bị chia,
            # đơn nhỏ gánh nặng hơn đơn lớn — cùng con dao 734.300đ, đơn 500 cuốn thành 1.469 đ/cuốn
            # còn đơn 5.000 cuốn chỉ 147 đ/cuốn.
            #
            # KHÔNG gắn `buoc_idx`: khoá đó dùng để ghép dòng tiền với thẻ số tờ của bước. Gắn vào
            # đây là hai dòng cùng khoá, map `tienTheoBuoc` bên FE nuốt mất một — thẻ bước sẽ hiện
            # tiền dao thay cho tiền công chạy máy.
            rows["cong_doan"].append({
                "loai": "khuon",
                "ten": _pre(name, f"{ten_b} · phí {nhan_dao}"),
                "thanh_tien": _r(tien),
                "gia_don_sp": _r(tien / sl) if sl > 0 else 0.0,
                # Cũng phải quy ra đ/sp. Tiền dao KHÔNG co giãn theo sản lượng (chú thích ở trên),
                # nhưng nó ĐANG bị chia vào giá vốn — giấu con số bị chia đi thì người lập phiếu
                # không thấy đơn nhỏ đang gánh bao nhiêu, mà đó chính là lúc cần thấy nhất.
                "cong_thuc": _ct(f"{_vi(_r(tien))}đ làm {nhan_dao}, một lần", tien, sl),
            })
    # NHẮC, không chặn: dùng lại dao cũ là chuyện thường ngày, chặn là phiền vô cớ. Nội dung lời
    # nhắc do `_canh_bao_khuon` quyết theo nguồn khuôn sale đã chọn.
    for _cb in _canh_bao_khuon(chain):
        warnings.append(f"Thành phần '{name}': {_cb}")

    # --- PHÍ GIAO HÀNG: khoản MỘT LẦN của CẢ SẢN PHẨM, GỘP vào giá vốn --------------------------
    #
    # Người lập phiếu gõ TỔNG tiền chở hàng cho toàn bộ sản lượng của sản phẩm này (v1: số phẳng
    # nhập tay — chưa tính theo vùng/km/khối lượng). Cộng vào giá vốn ⇒ sang Báo giá nó chịu markup
    # cùng phần còn lại, đúng ý "phí giao hàng là một phần giá thành", KHÔNG phải khoản thu hộ.
    #
    # KHÔNG gắn vào bước nào nên đứng thành NHÓM RIÊNG: nhét chung nhóm Công đoạn thì nó lọt vào
    # danh sách "các bước chạy máy" ở panel sản phẩm và bị đếm thành một công đoạn.
    #
    # 0 = không thu ⇒ KHÔNG đẻ dòng: dòng 0đ chỉ tổ làm dài bảng, và nhóm rỗng ở bản in đọc như
    # "có giao hàng mà quên nhập tiền".
    phi_gh = _f(tp.get("phi_giao_hang"))
    if phi_gh > 0:
        rows["giao_hang"].append({
            "loai": "giao_hang",
            "ten": _pre(name, "Giao hàng"),
            "thanh_tien": _r(phi_gh),
            # Cũng quy ra đ/sp — hệt tiền dao, khoản này KHÔNG co giãn theo sản lượng nên đơn nhỏ
            # gánh nặng hơn đơn lớn; giấu con số bị chia đi thì đúng lúc cần thấy nhất lại không thấy.
            "gia_don_sp": _r(phi_gh / sl) if sl > 0 else 0.0,
            "cong_thuc": _ct(f"{_vi(_r(phi_gh))}đ phí giao hàng, một lần", phi_gh, sl),
        })

    total = sum(_f(r.get("thanh_tien")) for grp in rows.values() for r in grp)
    return {
        "name": name,
        "rows": rows,
        "phi_khuon_dong": khuon_dong,
        "phi_khuon": _r(sum(_f(d["thanh_tien"]) for d in khuon_dong)),
        "phi_giao_hang": _r(phi_gh),
        "total": _r(total),
        "meta": {
            "so_luong": sl, "gia_von_don": _r(total / sl) if sl > 0 else 0.0,
            "con": con, "con_auto": bool(con_auto), "so_manh_xa": xa,
            "to_net": to_net, "to_gross": to_dau_vao, "to_nguyen": to_nguyen,
            "so_kem": so_kem, "so_luot": so_luot,
            # Mực + ba số dẫn xuất trả ngược lên UI: người dùng gõ TẬP, engine chốt SỐ — client
            # khỏi phải cài lại luật đếm process/pha rồi lệch với backend.
            "muc_a": muc_a, "muc_b": muc_b, "kem_moi_tay": kem_mau,
            "so_mau_a": so_mau_a, "so_mau_b": so_mau_b, "so_mau_pha": so_mau_pha,
            "to_dau_vao": to_dau_vao, "to_sau_in": to_sau_in,
            "bu_hao_auto": _r(finishing_spoilage_sum),   # Σ bù hao công đoạn (chuỗi ngược)
            "bu_hao_chi_tiet": bu_hao_chi_tiet,          # phân rã: bước nào ăn bao nhiêu tờ
            "so_trang": so_trang, "trang_moi_tay": trang_moi_tay,   # người dùng khai
            "so_to_per_sp": so_to_per_sp,                # số bài in — DẪN XUẤT: so_trang / trang_moi_tay
            "to_ra_cuoi": to_ra_cuoi, "so_tp_ra": so_tp_ra,  # khép mạch tờ → thành phẩm
            # Hai ô nhập tay đã bỏ hẳn ("− Hao" trước, "+ Bù thêm" 15/08/2026) — giữ khoá trả về
            # ở 0 để phiếu cũ và màn cũ đọc không vỡ; đừng dựng lại ô nào ở đây.
            "bu_hao_tay": 0, "hao_tay": 0,
        },
    }


def compute_phieu(*, so_luong: int, thanh_phans: list[dict], bu_hao_rows: list[dict] | None = None, warnings: list[str] | None = None) -> dict:
    """Tính giá vốn 1 phiếu theo thành phần → 2 nhóm (nvl · cong_doan).

    Returns:
        {meta:{so_luong, so_thanh_phan, gia_von_don, components:[{idx,name,gia_von_tp,...}]},
         groups:[{idx,name,columns,rows,subtotal}], grand_total, warnings}.
    """
    warns = warnings if warnings is not None else []
    so_luong = _i(so_luong)
    flags: dict = {}

    grouped: dict[str, list[dict]] = {"nvl": [], "cong_doan": [], "giao_hang": []}
    components: list[dict] = []

    bu_hao_list = bu_hao_rows or []

    for i, tp in enumerate(thanh_phans or []):
        one = _compute_one(tp, so_luong, warns, flags, bu_hao_list)
        for idx in ("nvl", "cong_doan", "giao_hang"):
            grouped[idx].extend(one["rows"][idx])
        components.append({
            "idx": i, "name": one["name"], "gia_von_tp": one["total"],
            # ⚠️ Phí khuôn ĐÃ NẰM TRONG `gia_von_tp` — nó là một dòng tiền của nhóm Công đoạn
            # (xem `_compute_one`) nên `total` cộng rồi. Hai khoá dưới chỉ để BÀY RA "trong giá vốn
            # có bao nhiêu tiền dao"; cộng thêm lần nữa là tính hai lần, mà báo giá lấy thẳng
            # `gia_von_tp` làm giá vốn khoá nên sai sẽ chạy tới tận hoá đơn.
            "phi_khuon": one["phi_khuon"], "phi_khuon_dong": one["phi_khuon_dong"],
            # ⚠️ Phí giao hàng CŨNG đã nằm trong `gia_von_tp` (một dòng của nhóm Giao hàng). Khoá
            # này chỉ để BÀY RA, cộng thêm lần nữa là tính hai lần — mà Báo giá lấy thẳng
            # `gia_von_tp` làm giá vốn khoá nên sai sẽ chạy tới tận hoá đơn.
            "phi_giao_hang": one["phi_giao_hang"],
            **one["meta"],
        })

    if not thanh_phans:
        warns.append("Phiếu chưa có thành phần nào — giá vốn = 0.")

    groups = []
    grand_total = 0.0
    for idx in ("nvl", "cong_doan", "giao_hang"):
        rws = grouped[idx]
        # Nhóm Giao hàng chỉ tồn tại khi CÓ phí: phiếu cũ và phiếu không thu tiền chở phải ra đúng
        # hai nhóm như trước, không thêm một khối rỗng vào bảng chi tiết lẫn bản in.
        if idx == "giao_hang" and not rws:
            continue
        subtotal = sum(_f(r.get("thanh_tien")) for r in rws)
        grand_total += subtotal
        groups.append({"idx": idx, "name": _NAMES[idx], "columns": _COLS[idx],
                       "rows": rws, "subtotal": _r(subtotal)})

    tong_sl = sum(_i(c.get("so_luong")) for c in components)
    gia_von_don = (grand_total / tong_sl) if tong_sl > 0 else 0.0
    return {
        "meta": {
            "so_luong": so_luong,            # SL mặc định phiếu (dùng khi sản phẩm chưa nhập SL)
            "tong_so_luong": tong_sl,        # Σ SL các sản phẩm
            "so_thanh_phan": len(thanh_phans or []),   # = SỐ SẢN PHẨM
            "gia_von_don": _r(gia_von_don),            # đơn giá BÌNH QUÂN (Σ giá vốn / Σ SL)
            # Σ phí khuôn CẢ PHIẾU — số để SOI, đã nằm SẴN trong `grand_total` và `gia_von_don`.
            # Báo giá KHÔNG đẻ dòng riêng cho nó: nó lấy `gia_von_tp` của từng sản phẩm làm giá vốn
            # rồi markup, nên tiền dao được markup cùng phần còn lại. Đừng cộng nó vào đâu nữa.
            "phi_khuon": _r(sum(_f(c.get("phi_khuon")) for c in components)),
            "components": components,
        },
        "groups": groups,
        "grand_total": _r(grand_total),
        "warnings": warns,
    }
