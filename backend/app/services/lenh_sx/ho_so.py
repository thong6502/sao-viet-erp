"""HỒ SƠ một lệnh — cửa HTTP thứ hai của tầng đọc (Task 10), nguồn dữ liệu của màn chi tiết.

CHỈ ĐỌC. Không một đường ghi nào trong file này; mọi con số dẫn xuất TÍNH LÚC ĐỌC, không cột cache,
không bảng mới ⇒ task này không có migration.

--- KHÁC `danh_sach.py` Ở CHỖ NÀO -------------------------------------------------------------
`danh_sach` gánh ~200 lệnh một trang nên mọi thứ phải hằng số theo số lệnh. Ở đây tập luôn có ĐÚNG
MỘT lệnh, nên đổi lại: được phép đọc thêm những bảng mà `boi_canh` cố ý không nạp cho cả trang
(routing gốc, phân công đã rút, gói phát hành, phiếu sửa, tên người). Đó là lý do file này có
truy vấn riêng — cùng lối `trang_thai.den_vat_tu_theo_lo` đã làm.

CHI PHÍ, ĐO CHỨ KHÔNG ĐOÁN (đếm `before_cursor_execute` quanh một lần gọi `ho_so()`):

    DB không có bài ghép nào :  86 câu  ->  69   (bớt 17)
    DB có 1 bài ghép         : 132 câu  -> 100   (bớt 32)

Cột trái là bản chạy engine vật tư HAI lượt; cột phải là bản hôm nay. Vế trái đo bằng cách cộng
lượt engine đã gỡ (`_dung_vat_tu` + `can_doi()`) vào lượt còn lại — vòng trước đo trực tiếp bản
hai lượt được 86 và 143.

`boi_canh.nap` là 21 câu và KHÔNG đổi theo bài ghép; file này tự gọi DB 8 lần. Phần phình còn lại
là `ke_hoach_vat_tu_service.can_doi()`, và nó phình theo **số bài ghép đang tồn tại trong kế
hoạch** chứ không theo bài ghép của lệnh đang mở (phán quyết C68 để nguyên).

Vì sao còn 69/100 chứ không ít hơn: engine vật tư nay chạy ĐÚNG MỘT lượt.
`trang_thai.den_va_bang` trả về CẢ bảng cân đối đã dựng, nên hồ sơ không phải gọi lại lượt thứ hai
chỉ để lấy các DÒNG (bản trước: một lượt cho MỘT chữ "đỏ/vàng/ok", một lượt nữa cho dòng). Chữ ký
`den_vat_tu_theo_lo` giữ nguyên cho màn danh sách (nó gọi cho tới 200 lệnh một trang), nên
`test_so_cau_sql_hang_tren_truc_lenh` không phải đổi.

--- BA CHỖ SAI ĐƯỢC MÀ KHÔNG GÃY GÌ ------------------------------------------------------------
  · Bảng cân đối là bảng của CẢ KẾ HOẠCH, không phải của lệnh đang mở. `can_doi()` chạy không
    tham số, và kể cả truyền `include_lsx_ids={id}` cũng không lọc được: `_lenh_trong_pham_vi` đi
    qua `lsx_repo.cho_mrp`, hàm này luôn OR thêm mọi lệnh `trang_thai IN TRANG_THAI_TINH` (đã đo).
    Phải CHIẾU lại về đúng lệnh + đúng bài của nó, đúng khuôn
    `ke_hoach_vat_tu_service.vat_tu_hieu_luc`. Không chiếu thì hồ sơ bày vật tư của lệnh hàng xóm,
    rất tự tin.
  · `BoiCanh.phan_cong` chỉ nạp dòng `active` — đúng cho bảng danh sách, THIẾU cho hồ sơ: khối
    lịch sử nhân lực sống bằng chính những dòng `removed`. Đọc thêm ở đây, KHÔNG nới điều kiện của
    tầng nạp chung (mọi màn khác sẽ ăn theo mà không ai muốn).
  · Bước bị BÀI GHÉP phủ không đẻ công việc riêng: routing phải bắc cầu `buoc_phu` mới gắn được ca
    in ghép vào node của lệnh. Bỏ qua thì hồ sơ hiện "In · chưa bắt đầu" trong khi ca ghép đang
    chạy máy.

--- KHÔNG MỘT SỐ TIỀN NÀO ------------------------------------------------------------------------
Ràng buộc toàn cục của plan. Đáng nói riêng ở đây vì hai nguồn của file này CÓ mang tiền:
`lsx.quy_cach_json` chép nguyên cụm trường vô hướng của phiếu tính giá (kể cả `phi_giao_hang`), và
`san_xuat_phan_cong.la_luong_khoan` là ảnh chụp chế độ lương.

LƯỚI THẬT LÀ SCHEMA, KHÔNG PHẢI FILE NÀY. `response_model` lặng lẽ vứt mọi khoá không khai ở
`ThongSoOut`, nên kể cả khi ai đó đổ nguyên `quy_cach_json` ra ở `_thong_so` thì tiền vẫn KHÔNG ra
tới response — đã kiểm bằng đột biến: đổ `**qc` mà `test_khong_lo_tien` vẫn XANH. Đừng đọc câu này
thành "vậy service muốn làm gì cũng được": khai từng trường ở đây là lớp thứ hai, và là lớp DUY
NHẤT có ích cho người đọc code (đọc `_thong_so` là thấy đúng những gì hồ sơ bày ra). Nhưng lúc
thêm trường thì chỗ phải soi là SCHEMA — thêm một tên khoá mang tiền vào `ThongSoOut` là tiền ra
thật, và bài `test_khong_lo_tien` (đọc JSON thật qua HTTP) là thứ bắt được đúng ca đó.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.department import Department
from ...models.employee import Employee
from ...models.khuon_be import KhuonBe
from ...models.ky_thuat_may import SuaChuaMay
from ...models.lsx import Lsx, LsxCongDoan
from ...models.san_xuat import GOI_DANG_PHAT_HANH, SanXuatGoiPhatHanh, SanXuatPhienBan
from ...models.san_xuat_thuc_thi import (
    PC_DA_RUT, PHIEN_DOI_MAY, PHIEN_KET_THUC, PHIEN_TAM_DUNG, SanXuatPhanCong,
)
from ...models.user import User
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from . import boi_canh, danh_sach, pham_vi, tien_do, trang_thai
from .boi_canh import BoiCanh

# Màu của bảng cân đối coi là "không phải việc phải lo": `xanh` = đủ bằng tồn đang có, `xam` = đã
# cấp đủ. Ba màu còn lại (`vang` chỉ đủ nhờ hàng đang về, `do`, `ve_muon`, `khong_ro`) đều là thứ
# người điều độ phải nhìn thấy. Khai ở đây thay vì import hằng của `ke_hoach_vat_tu_service`: chỗ
# đó là module nặng (kéo cả chuỗi kho/mua), và đây chỉ là hai chuỗi.
_VT_YEN_TAM = ("xanh", "xam")

# Nhãn tiếng Việt của `SanXuatKcsBatch.ket_luan`, CHỈ dùng cho chuỗi timeline — chuỗi đó là câu đã
# dựng sẵn cho người đọc, không phải dữ liệu. Trường `kcs.batch[].ket_luan` vẫn trả khoá THÔ để FE
# tự dịch bằng bảng nhãn của nó (`LenhSxHoSoView.KCS_KET_LUAN`), đừng đổi.
# Giá trị lạ KHÔNG được rơi về khoá: một chữ máy giữa câu tiếng Việt là thứ tổ trưởng đọc rồi đi
# hỏi, còn "chưa rõ kết luận" thì tự nói được là hệ chưa biết.
_KCS_KET_LUAN_NHAN = {
    "dat": "Đạt",
    "dat_mot_phan": "Đạt một phần",
    "khong_dat": "Không đạt",
}

#: Tên 13 khối `ho_so()` dựng ra — cũng là tập giá trị hợp lệ của tham số `chi_khoi`. Khai thành
#: hằng để nơi gọi (`phieu_cong_nghe`) đặt tên khối bằng chuỗi mà vẫn có chỗ đối chiếu, và để
#: `ho_so()` chặn được khoá gõ sai NGAY thay vì lặng lẽ trả thiếu khối.
KHOI = (
    "thong_tin", "tien_do", "thong_so", "routing", "vat_tu", "nhan_luc", "san_luong",
    "su_co", "kcs", "kho", "giao_hang", "timeline", "phien_ban",
)


def _aware(dt: datetime) -> datetime:
    """SQLite trả datetime NAIVE — ép aware UTC trước khi so/sắp (bẫy tái phát của repo). Khai lại
    cục bộ thay vì import `tien_do._aware`, đúng thói quen sẵn có của gói này."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _f(x) -> float:
    """`Numeric` ⇒ `Decimal`; ép `float` NGAY tại chỗ đọc (bẫy `Decimal / float` của repo)."""
    return float(x or 0)


# --- Đầu hồ sơ ----------------------------------------------------------------------------------
def _thong_tin(bc: BoiCanh, lsx_id: int) -> dict:
    """Danh tính lệnh: mã · tên · đơn · khách · người bán · số lượng · hạn. Không một số tiền nào —
    đơn hàng có `don_gia`, hồ sơ này thì không đọc tới."""
    lsx = bc.lenh[lsx_id]
    don = bc.don.get(lsx.order_id)
    khach = bc.khach.get(don.customer_id) if don is not None and don.customer_id else None
    sale = bc.sale.get(don.sale_user_id) if don is not None and don.sale_user_id else None
    return {
        "id": lsx.id,
        "ma": lsx.ma,
        "ten": lsx.ten,
        "loai": lsx.loai,
        "order_id": lsx.order_id,
        "order_no": don.order_no if don is not None else None,
        "order_line_id": lsx.order_line_id,
        "khach_hang": khach.name if khach is not None else None,
        "khach_hang_id": khach.id if khach is not None else None,
        "sale": sale.name if sale is not None else None,
        "so_luong_dat": lsx.so_luong_dat,
        "don_vi_tinh": lsx.don_vi_tinh,
        "is_rush": bool(lsx.is_rush),
        "han_hoan_thanh_sx": lsx.han_hoan_thanh_sx,
        "han_giao_khach": lsx.han_giao_khach,
        "ban_giao_at": lsx.ban_giao_at,
        "ghi_chu": lsx.ghi_chu,
        "tao_luc": lsx.created_at,
    }


def _tien_do(bc: BoiCanh, lsx_id: int, bay_gio: datetime, tinh: dict) -> dict:
    """Cùng bộ số với cột tiến độ của bảng danh sách — CỐ Ý, không phải tiện tay.

    Mở hồ sơ ra thấy 40% trong khi bảng vừa nói 55% là mất niềm tin vào cả hai màn, nên hai bên
    phải gọi ĐÚNG một hàm (`tien_do.phan_tram` / `gio_may` / `du_kien_xong`) chứ không mỗi bên tự
    tính. `uoc_tinh=True` = phần trăm đang đo bằng THỜI LƯỢNG kế hoạch vì bước chưa khai sản lượng;
    hai mức tin cậy đó phải ra tới UI, gộp làm một là mời người ta quyết trên con số họ tưởng chắc.
    """
    cv = danh_sach.buoc_hien_tai(bc, lsx_id)
    may = bc.may.get(danh_sach.may_cua_buoc(bc, cv))
    pct, uoc_tinh = tien_do.phan_tram(bc, lsx_id)
    return {
        "phan_tram": pct,
        "uoc_tinh": uoc_tinh,
        "gio_may": tien_do.gio_may(bc, lsx_id, bay_gio),
        "du_kien_xong": tinh["xong"],
        "trang_thai": tinh["trang_thai"],
        "canh_bao": tinh["canh_bao"],
        "buoc_hien_tai": cv.ten_cong_doan if cv is not None else None,
        "buoc_hien_tai_cong_viec_id": cv.id if cv is not None else None,
        "nhom_cong_doan": cv.nhom_cong_doan if cv is not None else None,
        "may": may.ten if may is not None else None,
        "nguoi": bc.nguoi_cua(cv.id) if cv is not None else [],
        "da_giao": bc.da_giao_cua(lsx_id),
    }


def _thong_so(lsx: Lsx) -> dict:
    """Thông số kỹ thuật thợ cần trước khi chạm vào việc: giấy · khổ nguyên · khổ tờ in · khổ thành
    phẩm · cách in · mực · số con · số tờ · số kẽm.

    KHAI TỪNG TRƯỜNG, không đổ `quy_cach_json` ra ngoài. Hai lý do, cái nào cũng đủ:
      · `lsx_service._tinh_dong` chép NGUYÊN mọi trường vô hướng của phiếu tính giá vào JSON đó,
        chỉ trừ 7 khoá trong `_QC_BO_QUA` — `phi_giao_hang` KHÔNG nằm trong 7 khoá ấy. Đổ cả dict
        ở đây KHÔNG làm tiền ra tới response (schema `ThongSoOut` chặn — đã kiểm bằng đột biến),
        nhưng nó làm mất thứ duy nhất cho người đọc biết hồ sơ bày ra CÁI GÌ. Cửa chặn thật nằm ở
        schema; đây là chỗ giữ danh sách cho người đọc.
      · Ảnh chụp của lệnh CŨ thiếu các khoá thêm sau (bleed, khe cắt…). Đọc bằng `.get` để chỗ
        thiếu ra `None` — UI hiện "—". Đừng để một hàm ép kiểu biến khoá thiếu thành 0 rồi bày ra
        như số thật của phiếu.
    """
    qc = lsx.quy_cach_json or {}
    return {
        "giay_ten": qc.get("giay_ten"),
        "dinh_luong": qc.get("dinh_luong"),
        "kho_nguyen_dai": qc.get("kho_nguyen_dai"),
        "kho_nguyen_rong": qc.get("kho_nguyen_rong"),
        "kho_in_dai": qc.get("kho_in_dai"),
        "kho_in_rong": qc.get("kho_in_rong"),
        "dai_thanh_pham": qc.get("dai_thanh_pham"),
        "rong_thanh_pham": qc.get("rong_thanh_pham"),
        "quy_cach_in": qc.get("quy_cach_in"),
        "so_mau_a": qc.get("so_mau_a"),
        "so_mau_b": qc.get("so_mau_b"),
        "muc_a": list(qc.get("muc_a") or []),
        "muc_b": list(qc.get("muc_b") or []),
        "so_trang": qc.get("so_trang"),
        "trang_moi_tay": qc.get("trang_moi_tay"),
        "so_kem": qc.get("so_kem"),
        "so_manh_xa": qc.get("so_manh_xa"),
        "loai_san_pham": qc.get("loai_san_pham_ten"),
        "ghi_chu_ky_thuat": qc.get("ghi_chu_ky_thuat"),
        # Bốn số DẪN XUẤT nằm trên cột thật của `lsx` (không trong JSON) — chuỗi ngược của engine
        # ghi vào đó, và bảng vật tư/bình bài đọc chính chúng.
        "so_con": lsx.so_con,
        "so_to_ke_hoach": lsx.so_to_ke_hoach,
        "so_to_nguyen": lsx.so_to_nguyen,
        "don_vi_tinh": lsx.don_vi_tinh,
    }


# --- Routing: node + cạnh, có LỚP để vẽ được nhánh song song ------------------------------------
def _lop_topo(ids: list[int], canh: list[tuple[int, int]]) -> dict[int, int]:
    """`{buoc_id: lớp}` — lớp = ĐƯỜNG DÀI NHẤT từ một bước không có tiền nhiệm tới nó.

    Vì sao không lấy `thu_tu` làm lớp: `thu_tu` là thứ tự BẢNG (kế hoạch gõ từ trên xuống), không
    phải quan hệ phụ thuộc. Bìa và ruột chạy SONG SONG nhưng `thu_tu` của chúng vẫn 1 và 2 — bày
    theo `thu_tu` là vẽ ra một chuỗi tuần tự không tồn tại, và người đọc kết luận sai về việc gì
    đang chặn việc gì.

    Lấy `max` (đường dài nhất) chứ không `min`: một bước chỉ bắt đầu được khi MỌI tiền nhiệm xong,
    nên vị trí thật của nó là nhánh chậm nhất. Kahn lặp, không đệ quy — routing xấu (chu trình do
    dữ liệu trôi) chỉ để lại vài node ở lớp 0 chứ không được phép làm sập màn hồ sơ.
    """
    truoc: dict[int, int] = {i: 0 for i in ids}
    sau: dict[int, list[int]] = {i: [] for i in ids}
    for a, b in canh:
        if a in truoc and b in truoc:
            sau[a].append(b)
            truoc[b] += 1
    lop = {i: 0 for i in ids}
    hang = [i for i in ids if truoc[i] == 0]
    while hang:
        i = hang.pop()
        for j in sau[i]:
            lop[j] = max(lop[j], lop[i] + 1)
            truoc[j] -= 1
            if truoc[j] == 0:
                hang.append(j)
    return lop


def _khuon_buoc(db: Session, buocs: list[LsxCongDoan]) -> dict[int, dict]:
    """`{khuon_be_id: {mã · tên · số kệ · tình trạng · ngày về}}` — nạp MỘT lô cho cả routing.

    Cùng hình dạng khoá với `lsx_service._khuon_map` (tiền tố `khuon_be_`) để hai đường đọc bày ra
    cùng một bộ tên; đổi một bên là FE/phiếu giấy bên kia mất chữ mà không ai báo.
    """
    ids = {b.khuon_be_id for b in buocs if b.khuon_be_id}
    if not ids:
        return {}
    rows = db.execute(select(KhuonBe).where(KhuonBe.id.in_(ids))).scalars()
    return {
        k.id: {
            "khuon_be_ma": k.ma,
            "khuon_be_ten": k.ten,
            "khuon_be_so_ke": k.so_ke,
            "khuon_be_tinh_trang": k.tinh_trang,
            "khuon_be_ngay_ve": k.ngay_ve_du_kien,
        }
        for k in rows
    }


def _routing(bc: BoiCanh, lsx_id: int, buocs: list[LsxCongDoan], ten_to: dict[int, str],
             khuon: dict[int, dict]) -> dict:
    """Đồ thị routing của lệnh: `nodes` (bước + công việc thực thi của nó) và `canh` (cặp bước).

    NODE LÀ BƯỚC ROUTING (`lsx_cong_doan`), không phải công việc: bước bị bài ghép phủ KHÔNG có
    công việc riêng — cả cụm dùng chung một `SanXuatCongViec` mang `lsx_id IS NULL`. Lấy công việc
    làm node là mất đúng bước nặng nhất của lệnh (ca in ghép) và mất luôn mọi cạnh chạm nó.

    Cầu bước ↔ công việc chung đi qua `bc.buoc_phu` (`boi_canh` đã dựng bằng `lsx_step_key`, không
    bằng id — sửa routing là replace-all nên id tái sinh). `la_buoc_ghep` phải ra tới UI: "đang
    chạy" của một ca ghép là sự thật của CẢ CA, không riêng lệnh này.
    """
    cv_theo_buoc: dict[int, tuple] = {}
    for cv in bc.cong_viec[lsx_id]:
        if cv.lsx_cong_doan_id is not None:
            cv_theo_buoc[cv.lsx_cong_doan_id] = (cv, False)
    for cv in bc.cong_viec_ghep[lsx_id]:
        for b in bc.buoc_phu[cv.id]:
            cv_theo_buoc[b] = (cv, True)

    ids = [b.id for b in buocs]
    canh = [(a, b) for a, b in bc.phu_thuoc_buoc[lsx_id] if a in set(ids) and b in set(ids)]
    lop = _lop_topo(ids, canh)
    truoc: dict[int, list[int]] = {i: [] for i in ids}
    for a, b in canh:
        truoc[b].append(a)

    hien_tai = danh_sach.buoc_hien_tai(bc, lsx_id)
    nodes = []
    for b in sorted(buocs, key=lambda x: (lop[x.id], x.thu_tu, x.id)):
        cv, la_ghep = cv_theo_buoc.get(b.id, (None, False))
        may = bc.may.get(danh_sach.may_cua_buoc(bc, cv)) if cv is not None else None
        to_id = (cv.department_id if cv is not None else None) or b.department_id
        nodes.append({
            "id": b.id,
            "thu_tu": b.thu_tu,
            "lop": lop[b.id],
            "phu_thuoc": sorted(truoc[b.id]),
            "ten": b.ten,
            "nhom": b.nhom,
            "loai_buoc": b.loai_buoc,
            "bat_buoc": bool(b.bat_buoc),
            "nha_cung_cap": b.nha_cung_cap,
            "cong_viec_id": cv.id if cv is not None else None,
            "la_buoc_ghep": la_ghep,
            "la_kcs": bool(cv.la_kcs) if cv is not None else False,
            "la_buoc_hien_tai": cv is not None and hien_tai is not None and cv.id == hien_tai.id,
            "trang_thai": cv.trang_thai if cv is not None else None,
            "may": may.ten if may is not None else None,
            "to": ten_to.get(to_id) if to_id else None,
            "nguoi": bc.nguoi_cua(cv.id) if cv is not None else [],
            "du_kien_bat_dau": cv.du_kien_bat_dau if cv is not None else None,
            "du_kien_ket_thuc": cv.du_kien_ket_thuc if cv is not None else None,
            "hoan_thanh_luc": cv.hoan_thanh_luc if cv is not None else None,
            "so_luong_vao": _f(b.so_luong_vao),
            "so_luong_ra": _f(b.so_luong_ra),
            "don_vi_vao": b.don_vi_vao,
            "don_vi_ra": b.don_vi_ra,
            # Khuôn/khung của bước — mã · số kệ · tình trạng · ngày về. Ra tới đây vì cả màn hồ sơ
            # LẪN phiếu công nghệ giấy đều cần: thợ cầm tờ giấy đi lấy dao chứ không mở màn hình.
            **khuon.get(b.khuon_be_id or 0, {}),
        })
    return {"nodes": nodes, "canh": [[a, b] for a, b in sorted(canh)]}


# --- Vật tư: hai mức + phần ĐÃ CẤP --------------------------------------------------------------
def _dong_vat_tu(nhom: dict, row: dict, pham_vi_dong: str) -> dict:
    """Một dòng vật tư của hồ sơ = dòng cân đối + danh tính mặt hàng của nhóm chứa nó.

    LẤY NGUYÊN con số của `can_doi` (`nhu_cau` · `da_cap` · `dang_linh` · `con_phai_co` · `thieu` ·
    `trang_thai`), không tính lại cái nào. Đặc biệt `da_cap`/`dang_linh`: chúng do
    `_da_cap_dang_linh` đọc từ `stock_request_lines` rồi QUY VỀ ĐƠN VỊ GỐC bằng đúng khổ giấy mà
    phần nhu cầu đã dùng. Viết một truy vấn vật tư thứ hai ở đây là đẻ nguồn sự thật thứ hai, và nó
    sẽ lệch đúng ở ca quy đổi — ca không ai nhìn ra.
    """
    return {
        "pham_vi": pham_vi_dong,
        "ma": row["ma"],
        "ten_viec": row.get("ten_viec"),
        "buoc_id": row.get("buoc_id"),
        "hang_loai": nhom["hang_loai"],
        "hang_id": nhom["hang_id"],
        "hang_ma": nhom.get("hang_ma"),
        "hang_ten": nhom.get("hang_ten"),
        "don_vi_goc": nhom.get("don_vi_goc"),
        "ton": nhom.get("ton"),
        "nhu_cau": row.get("nhu_cau"),
        "nhu_cau_hien_thi": row.get("nhu_cau_hien_thi"),
        "da_cap": row.get("da_cap"),
        "dang_linh": row.get("dang_linh"),
        "con_phai_co": row.get("con_phai_co"),
        "thieu": row.get("thieu"),
        "trang_thai": row.get("trang_thai"),
        "ngay_can": row.get("ngay_can"),
        "ngay_du_hang": row.get("ngay_du_hang"),
    }


def _vat_tu(bc: BoiCanh, lsx_id: int, *, bang: dict | None, ma_bai: dict[int, str],
            thu_tu_buoc: dict[int, int], thu_tu_hien_tai: int) -> dict:
    """Vật tư của lệnh, chia làm BA phần vì chúng trả lời ba câu khác nhau:

      · `hien_tai` — bước ĐANG LÀM có đủ đồ không (`du`). Đây là câu tổ trưởng hỏi trước khi bấm
        Bắt đầu.
      · `canh_bao_sau` — bước SẮP TỚI đang hụt gì. Câu của điều độ, để còn kịp đi mua/đổi lịch.
      · `da_cap` — kho đã xuất bao nhiêu rồi. Câu của người đi lĩnh, để khỏi xin trùng.

    Gộp ba thành một danh sách là mất nghĩa: "thiếu keo" ở bước đóng gói KHÔNG phải lý do chặn ca
    in đang chạy, mà cũng không được phép im.

    CHIẾU VỀ ĐÚNG LỆNH (xem docstring module): `bang` là bảng cân đối của CẢ kế hoạch, nên chỉ giữ
    dòng của chính lệnh, cộng dòng của BÀI GHÉP mà lệnh là thành viên — dòng của bài là vật tư
    THẬT của lệnh (giấy của cả tờ in ghép), bỏ đi là hồ sơ nói lệnh không cần giấy.

    Vị trí của dòng lấy theo BƯỚC: dòng của bài neo `bai_ghep_cong_doan.id` nên phải bắc qua
    `buoc_phu` mới biết nó nằm ở đoạn nào của lệnh. Dòng không xác định được bước (`buoc_id` trống,
    hoặc bước đã bị xoá khi sửa routing) coi như CẦN RỒI — xếp vào `hien_tai`. Giấu nó xuống
    "cảnh báo sau" là hứa hẹn một thứ đang thiếu ngay bây giờ.
    """
    bang = bang or {"items": [], "bo_qua": []}
    ma_lenh = bc.lenh[lsx_id].ma
    bai_ids = {cv.bai_ghep_id for cv in bc.cong_viec_ghep[lsx_id] if cv.bai_ghep_id is not None}
    # Bước của lệnh mà một công đoạn ghép phủ ⇒ vị trí của dòng bài trong chuỗi của lệnh.
    thu_tu_ghep: dict[int, int] = {}
    for cv in bc.cong_viec_ghep[lsx_id]:
        vt = [thu_tu_buoc[b] for b in bc.buoc_phu[cv.id] if b in thu_tu_buoc]
        if vt and cv.bai_ghep_cong_doan_id is not None:
            thu_tu_ghep[cv.bai_ghep_cong_doan_id] = min(vt)

    hien_tai: list[dict] = []
    canh_bao_sau: list[dict] = []
    da_cap: list[dict] = []
    for nhom in bang.get("items", []):
        for row in nhom.get("dong", []):
            la_bai = row.get("bai_ghep_id") in bai_ids and row.get("bai_ghep_id") is not None
            la_lenh = row.get("bai_ghep_id") is None and row.get("lsx_id") == lsx_id
            if not (la_bai or la_lenh):
                continue
            dong = _dong_vat_tu(nhom, row, "bai_ghep" if la_bai else "lsx")
            bang_thu_tu = thu_tu_ghep if la_bai else thu_tu_buoc
            vi_tri = bang_thu_tu.get(row.get("buoc_id"), -1)
            if vi_tri <= thu_tu_hien_tai:
                hien_tai.append(dong)
            elif dong["trang_thai"] not in _VT_YEN_TAM:
                canh_bao_sau.append(dong)
            if _f(dong["da_cap"]) > 0:
                da_cap.append(dong)

    return {
        "hien_tai": {
            "du": all(d["trang_thai"] in _VT_YEN_TAM for d in hien_tai),
            "dong": hien_tai,
        },
        "canh_bao_sau": canh_bao_sau,
        "da_cap": da_cap,
        # Dòng engine KHÔNG đối chiếu được (thiếu công thức lượng, đơn vị lạ). Phải bày ra: một
        # bảng vật tư im lặng bỏ qua vài món trông y hệt một bảng đủ.
        #
        # Lọc theo MÃ, và phải nhận CẢ HAI loại mã: dòng bỏ qua của lệnh mang `lsx.ma`, còn dòng
        # của bài ghép mang `bai_ghep.ma` (`ke_hoach_vat_tu_service.py:995`). Chỉ so với `ma_lenh`
        # là lệnh nằm trong bài mà bài chưa chọn giấy chung sẽ thấy `bo_qua` RỖNG — đúng kiểu im
        # lặng bỏ sót mà chính khối này sinh ra để chống. Bài canh: `test_bo_qua_nhan_dong_bai_ghep`.
        "bo_qua": [
            r for r in bang.get("bo_qua", [])
            if r.get("ma") == ma_lenh or r.get("ma") in set(ma_bai.values())
        ],
    }


# --- Nhân lực: ai đang làm, và ai từng làm ------------------------------------------------------
def _nhan_luc(db: Session, bc: BoiCanh, lsx_id: int, *, cv_ids: list[int],
              ten_to: dict[int, str]) -> dict:
    """`hien_tai` = roster đang mở theo từng bước; `lich_su` = VẾT của mọi lần đổi người và đổi máy.

    Vì sao lịch sử phải đọc riêng: `BoiCanh.phan_cong` lọc `trang_thai='active'` — đúng cho bảng
    danh sách (cột "Máy/người" chỉ nói ai đang làm), nhưng hồ sơ là chỗ trả lời "ai từng làm việc
    này, và vì sao đổi". Người bị rút vẫn còn dòng `removed` (`thuc_thi.go_phan_cong` giữ lịch sử,
    không xoá dòng) kèm `ly_do_rut`.

    ĐỔI MÁY không có bảng lịch sử nào cả: `thuc_thi.doi_may` đóng phiên đang chạy bằng
    `loai_dong='doi_may'` rồi mở ngay phiên mới trên máy mới. Cặp phiên liền kề ĐÓ chính là vết
    đổi máy, và là vết duy nhất — `cong_viec.may_id` chỉ còn nhớ máy CUỐI CÙNG. Ghép theo
    `so_thu_tu` liền sau, không ghép theo thời gian: hai phiên có CÙNG mốc `now` (service cố ý
    không để hở giây nào), sắp theo thời gian là hai bản ghi có thể đảo chỗ nhau.
    """
    pc_rows = list(db.execute(
        select(SanXuatPhanCong, Employee)
        .join(Employee, Employee.id == SanXuatPhanCong.employee_id)
        .where(SanXuatPhanCong.cong_viec_id.in_(cv_ids))
    ).all()) if cv_ids else []
    ten_cv = {cv.id: cv.ten_cong_doan for cv in bc.cong_viec_du(lsx_id)}

    lich_su: list[dict] = []
    for pc, emp in pc_rows:
        lich_su.append({
            "loai": "giao_nguoi",
            "luc": _aware(pc.created_at),
            "cong_viec_id": pc.cong_viec_id,
            "ten_viec": ten_cv.get(pc.cong_viec_id),
            "nguoi": emp.full_name,
            "may_cu": None, "may_moi": None, "ly_do": None,
        })
        if pc.trang_thai == PC_DA_RUT:
            lich_su.append({
                "loai": "rut_nguoi",
                # `updated_at` mang `onupdate` nên nó là mốc của chính lần rút — dòng phân công
                # không có đường ghi nào khác sau khi rút.
                "luc": _aware(pc.updated_at),
                "cong_viec_id": pc.cong_viec_id,
                "ten_viec": ten_cv.get(pc.cong_viec_id),
                "nguoi": emp.full_name,
                "may_cu": None, "may_moi": None,
                "ly_do": pc.ly_do_rut,
            })

    for cv in bc.cong_viec_du(lsx_id):
        phien = sorted(bc.phien[cv.id], key=lambda p: (p.so_thu_tu, p.id))
        for i, p in enumerate(phien):
            if p.loai_dong != PHIEN_DOI_MAY:
                continue
            sau = phien[i + 1] if i + 1 < len(phien) else None
            cu = bc.may.get(p.may_id)
            moi = bc.may.get(sau.may_id) if sau is not None else None
            lich_su.append({
                "loai": "doi_may",
                "luc": _aware(p.ket_thuc) if p.ket_thuc is not None else _aware(p.bat_dau),
                "cong_viec_id": cv.id,
                "ten_viec": cv.ten_cong_doan,
                "nguoi": None,
                "may_cu": cu.ten if cu is not None else None,
                "may_moi": moi.ten if moi is not None else None,
                "ly_do": p.ly_do,
            })
    lich_su.sort(key=lambda e: (e["luc"], e["loai"]))

    hien_tai = []
    for cv in bc.cong_viec_du(lsx_id):
        may = bc.may.get(danh_sach.may_cua_buoc(bc, cv))
        hien_tai.append({
            "cong_viec_id": cv.id,
            "buoc_id": cv.lsx_cong_doan_id,
            "ten_viec": cv.ten_cong_doan,
            "to": ten_to.get(cv.department_id) if cv.department_id else None,
            "may": may.ten if may is not None else None,
            "nguoi": bc.nguoi_cua(cv.id),
        })
    return {"hien_tai": hien_tai, "lich_su": lich_su}


# --- Sản lượng · KCS · sự cố · kho ---------------------------------------------------------------
def _san_luong(bc: BoiCanh, lsx_id: int) -> dict:
    """Tổng tốt/hỏng + từng batch. Số của bước GHÉP là số của CẢ CA — nói rõ bằng `la_buoc_ghep`,
    không im lặng cộng nó vào như thể của riêng lệnh này."""
    ghep = {cv.id for cv in bc.cong_viec_ghep[lsx_id]}
    dong = []
    tong = tot = hong = 0.0
    for cv in bc.cong_viec_du(lsx_id):
        for b in sorted(bc.batch[cv.id], key=lambda x: _aware(x.ket_thuc)):
            tong += _f(b.tong)
            tot += _f(b.tot)
            hong += _f(b.hong)
            dong.append({
                "id": b.id,
                "cong_viec_id": cv.id,
                "ten_viec": cv.ten_cong_doan,
                "la_buoc_ghep": cv.id in ghep,
                "bat_dau": b.bat_dau,
                "ket_thuc": b.ket_thuc,
                "tong": _f(b.tong),
                "tot": _f(b.tot),
                "hong": _f(b.hong),
                "don_vi": b.don_vi,
                "mo_ta_loi": b.mo_ta_loi,
            })
    return {"tong": tong, "tot": tot, "hong": hong, "batch": dong}


def _kcs(bc: BoiCanh, lsx_id: int) -> dict:
    """Tổng nhận/đạt/không đạt + từng batch. Tỉ lệ tính THEO SỐ (Σđạt/Σnhận), không phải trung bình
    cộng các batch — batch 10 cái và batch 10.000 cái không cân nhau. Chưa kiểm cái nào ⇒ `None`,
    KHÔNG phải 0.0: "0% đạt" là một lời báo động sai."""
    ghep = {cv.id for cv in bc.cong_viec_ghep[lsx_id]}
    dong = []
    nhan = dat = khong_dat = 0.0
    for cv in bc.cong_viec_du(lsx_id):
        for k in sorted(bc.kcs[cv.id], key=lambda x: _aware(x.ket_thuc)):
            nhan += _f(k.so_luong_nhan)
            dat += _f(k.so_luong_dat)
            khong_dat += _f(k.so_luong_khong_dat)
            dong.append({
                "id": k.id,
                "cong_viec_id": cv.id,
                "ten_viec": cv.ten_cong_doan,
                "la_buoc_ghep": cv.id in ghep,
                "la_kcs_cuoi": bool(cv.la_kcs_cuoi),
                "ket_thuc": k.ket_thuc,
                "so_luong_nhan": _f(k.so_luong_nhan),
                "so_luong_dat": _f(k.so_luong_dat),
                "so_luong_khong_dat": _f(k.so_luong_khong_dat),
                "don_vi": k.don_vi,
                "ket_luan": k.ket_luan,
                "ghi_chu": k.ghi_chu,
            })
    return {
        "tong_nhan": nhan,
        "tong_dat": dat,
        "tong_khong_dat": khong_dat,
        "ty_le_dat": (100.0 * dat / nhan) if nhan > 0 else None,
        "batch": dong,
    }


def _su_co(db: Session, bc: BoiCanh, lsx_id: int) -> list[dict]:
    """Yêu cầu sửa chữa của lệnh, KÈM phiếu sửa đã sinh ra từ nó.

    `yeu_cau.phieu_id` là soft-ref sang `ky_thuat_sua_chua.id` — không FK, không relationship ORM,
    nên phải nối tay. Thiếu nhịp nối này thì người báo hỏng nhìn thấy "đã tạo phiếu" mà không có
    đường nào biết thợ đang làm tới đâu, và họ sẽ đi hỏi bằng điện thoại — đúng thứ phần mềm sinh
    ra để bỏ.

    Sự cố báo trên bước bị bài ghép phủ về được đây qua `cong_viec_id` (`boi_canh` câu 10 đi hai
    đường OR): ca in ghép hỏng máy thì MỌI lệnh trên tờ in ấy đều đứng.
    """
    ycs = sorted(bc.su_co[lsx_id], key=lambda y: _aware(y.thoi_diem))
    phieu_ids = {y.phieu_id for y in ycs if y.phieu_id is not None}
    phieu = {
        p.id: p for p in db.execute(
            select(SuaChuaMay).where(SuaChuaMay.id.in_(phieu_ids))
        ).scalars()
    } if phieu_ids else {}
    ten_cv = {cv.id: cv.ten_cong_doan for cv in bc.cong_viec_du(lsx_id)}
    ra = []
    for y in ycs:
        may = bc.may.get(y.may_id)
        p = phieu.get(y.phieu_id) if y.phieu_id is not None else None
        ra.append({
            "id": y.id,
            "ma": y.ma,
            "cong_viec_id": y.cong_viec_id,
            "ten_viec": ten_cv.get(y.cong_viec_id),
            "may": may.ten if may is not None else None,
            "bo_phan_hong": y.bo_phan_hong,
            "mo_ta": y.mo_ta,
            "muc_do": y.muc_do,
            "may_dung": bool(y.may_dung),
            "nguoi_bao": y.nguoi_bao_ten,
            "thoi_diem": y.thoi_diem,
            "trang_thai": y.trang_thai,
            "ly_do_tu_choi": y.ly_do_tu_choi,
            "phieu": None if p is None else {
                "id": p.id,
                "ma": p.ma,
                "trang_thai": p.trang_thai,
                "nguyen_nhan_phuong_an": p.nguyen_nhan_phuong_an,
                "hoan_thanh_at": p.hoan_thanh_at,
            },
        })
    return ra


def _kho(bc: BoiCanh, lsx_id: int, *, so_lenh_trong_nhom: int) -> dict:
    """Yêu cầu nhập kho thành phẩm + lot BTP của lệnh.

    ⚠️ `so_luong_yeu_cau`/`so_luong_xac_nhan` ở đây là số của NHÓM, không phải phần đóng góp của
    riêng lệnh này: một nhóm gồm nhiều lệnh (Ruột + Bìa → Kỷ yếu) cùng đọc CHUNG một tập yêu cầu.
    Cộng qua các lệnh của một trang là nhân con số thật lên đúng bằng số thành viên nhóm.

    Nói ra bằng `so_lenh_trong_nhom` — SỐ, không phải cờ. Bản trước trả `cap_nhom=True` hằng, tức
    một lời chú thích đội lốt trường dữ liệu: nó đúng cả khi nhóm chỉ có một lệnh (lúc đó số của
    nhóm CHÍNH LÀ số của lệnh, cộng thoải mái) lẫn khi nhóm có ba lệnh (cộng là sai gấp ba). Có
    con số thì mặt đọc tự quyết được; có mỗi cờ thì không. `0` = lệnh chưa vào nhóm nào.
    """
    yeu_cau = []
    for yc in sorted(bc.nhap_kho_yc[lsx_id], key=lambda y: y.id):
        yeu_cau.append({
            "id": yc.id,
            "kcs_batch_id": yc.kcs_batch_id,
            "nhom_id": yc.nhom_id,
            "so_luong_yeu_cau": _f(yc.so_luong_yeu_cau),
            "so_luong_xac_nhan": _f(yc.so_luong_xac_nhan),
            "con_lai": max(0.0, _f(yc.so_luong_yeu_cau) - _f(yc.so_luong_xac_nhan)),
            "don_vi": yc.don_vi,
            "quy_cach": yc.quy_cach,
            "trang_thai": yc.trang_thai,
            "tao_luc": yc.created_at,
            "xac_nhan_luc": yc.xac_nhan_last_luc,
        })
    btp = [
        {
            "id": l.id,
            "so_luong": _f(l.so_luong),
            "don_vi": l.don_vi,
            "phan_loai": l.phan_loai,
            "kho_xac_nhan": bool(l.kho_xac_nhan),
            "quy_cach": l.quy_cach,
        }
        for l in sorted(bc.lot[lsx_id], key=lambda l: l.id)
    ]
    return {"so_lenh_trong_nhom": so_lenh_trong_nhom, "yeu_cau": yeu_cau, "btp": btp}


def _giao_hang(db: Session, bc: BoiCanh, lsx_id: int, *, nhom_id: int | None) -> dict:
    """Tồn thành phẩm còn giao được + mọi ô form giao hàng phải điền sẵn.

    KHÔNG có phép tính nào ở đây: gọi thẳng `san_xuat/kho.ton_kha_dung_thanh_pham` — MỘT hàm dùng
    chung với form giao hàng. Hai bên tự tính thì sớm muộn một bên cho bấm cái bên kia từ chối, và
    người dùng không có cách nào biết bên nào đúng.

    TRẦN NẰM Ở TỪNG DÒNG `hang[]`, không có scalar `so_toi_da` cấp nhóm — xem docstring của hàm
    kia. Đừng thêm lại một con số tổng ở đây: hai con số cạnh nhau mà một cái sai thì mặt đọc sẽ
    nhặt cái tiện tay hơn.

    `da_giao` LUÔN mang nghĩa CẤP NHÓM (tổng đã thực nhận của mọi dòng đơn trong nhóm). Lệnh chưa
    vào nhóm nào ⇒ `0.0`, KHÔNG phải số đã giao của riêng dòng đơn lệnh này — số đó vẫn có ở
    `tien_do.da_giao`, và để hai nghĩa dưới cùng một tên khoá là bẫy cho Task 12. `so_lenh_trong_nhom`
    nói mức gộp của cả khối: `1` thì số của nhóm chính là số của lệnh.

    Lệnh chưa vào nhóm nào (chưa có công việc, hoặc nhóm chưa dựng) ⇒ chưa có gì trong kho để giao:
    trả rỗng và TẮT nút. Đừng lấy `so_luong_dat` hay tổng đã nhập kho làm "khả dụng" — đó là mời
    người ta lập phiếu vượt số hàng có thật.
    """
    from ..san_xuat.kho import ton_kha_dung_thanh_pham

    if nhom_id is None:
        return {
            "nhom_id": None,
            "order_id": bc.lenh[lsx_id].order_id,
            "order_line_ids": [],
            "so_lenh_trong_nhom": 0,
            "hang": [],
            "da_nhap_kho": 0.0,
            "da_giao": 0.0,
            "co_the_giao": False,
            "don_vi_lech": False,
        }
    return ton_kha_dung_thanh_pham(db, nhom_id)


# --- Phiên bản + timeline -------------------------------------------------------------------------
def _goi_id(db: Session, bc: BoiCanh, lsx_id: int) -> int | None:
    """Gói phát hành ĐANG HIỆU LỰC của lệnh — đi qua `cong_viec.goi_id`, đường DUY NHẤT.

    `san_xuat_goi_phat_hanh` không neo `lsx_id` (một gói ôm nhiều lệnh + nhiều bài trong một lần
    thả xuống xưởng). Lệnh chưa có công việc nào ⇒ chưa từng được phát hành ⇒ `None`, và mọi thứ
    đọc từ gói cũng phải `None` theo — trả 1 là bịa ra một phiên bản chưa từng tồn tại.

    MỘT LỆNH CÓ THỂ MANG CÔNG VIỆC CỦA NHIỀU GÓI. `release_update.thu_hoi_goi` chỉ đổi
    `goi.trang_thai` và ĐỂ NGUYÊN các dòng `SanXuatCongViec` của gói cũ, nên sau một lượt
    thu-hồi-rồi-phát-hành-lại thì `cong_viec_du()` trả về cả hai lứa. Bản đầu của hàm này lấy
    `goi_id` ĐẦU TIÊN gặp, và trên DB dev nó rơi đúng vào gói đã chết: hồ sơ LSX26-0029 in
    "Phiên bản 1" trong khi bàn xếp lịch nói "phiên bản 2" cho cùng lệnh ấy. Không phải lỗi
    cosmetic — QR trên phiếu công nghệ mã hoá `pv=<phien_ban>` lấy từ chính con số này, nên phiếu
    in ra mang `pv` cũ và băng "phiếu giấy này là bản cũ" không bao giờ bật.

    Lọc `dang_phat_hanh` cho khớp `SanXuatRepository.goi_hien_tai_cua` — hai nơi cùng trả lời câu
    "gói nào đang hiệu lực cho lệnh này" thì phải trả lời giống nhau. Mọi gói đều đã thu hồi ⇒
    `None` (không có phiên bản nào đang hiệu lực để nói), đúng luật "không bịa" ở trên.
    """
    ids = {cv.goi_id for cv in bc.cong_viec_du(lsx_id) if cv.goi_id is not None}
    if not ids:
        return None
    goi = db.execute(
        select(SanXuatGoiPhatHanh)
        .where(
            SanXuatGoiPhatHanh.id.in_(ids),
            SanXuatGoiPhatHanh.trang_thai == GOI_DANG_PHAT_HANH,
        )
        .order_by(SanXuatGoiPhatHanh.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return goi.id if goi is not None else None


def _timeline(db: Session, bc: BoiCanh, lsx_id: int, *, goi_id: int | None,
              lich_su_nhan_luc: list[dict]) -> list[dict]:
    """Mọi việc đã xảy ra với lệnh, MỘT dòng thời gian, sắp tăng dần theo mốc MÁY CHỦ.

    Bảy nguồn, vì bảy nơi ghi: gói phát hành · phiên chạy · sản lượng · KCS · sự cố · kho ·
    phân công/đổi máy (nhận lại từ `_nhan_luc` thay vì đọc `san_xuat_phan_cong` lần thứ hai).

    KHÔNG có giao hàng — CÓ NGUỒN, CỐ Ý CHƯA DÙNG (phán quyết C70). Nguồn sẵn sàng là
    `DeliveryStatusHistory` (`models/delivery.py:312-330`): nó mang đủ `luc` + `nguoi_thao_tac_id`
    + `den_trang_thai`, tức đúng hình dạng một bảng timeline, chỉ thiếu một lượt đọc ở đây. Lý do
    chưa nối: màn hồ sơ (Task 12) vẽ giao hàng thành KHỐI RIÊNG, không đòi nó nằm trong dòng thời
    gian, và số đã giao đã có ở khối `giao_hang`.

    (Bản đầu của docstring này viết "không có mốc thời gian nào" — SAI, và đã sửa. Một lý do sai
    nằm trong chú thích như sự thật đã rà thì người sau sẽ tin mà không tra lại.)

    Mọi mốc ép AWARE trước khi sắp: SQLite trả naive, Postgres trả aware — trộn hai loại là
    `TypeError` khi so, và nó chỉ nổ trên đúng một trong hai DB.
    """
    ra: list[dict] = []
    ten_cv = {cv.id: cv.ten_cong_doan for cv in bc.cong_viec_du(lsx_id)}
    # Nhật ký viết cho NGƯỜI đọc, nên bày TÊN đơn vị ("tờ") chứ không bày MÃ ("to") — cột `don_vi`
    # khắp tầng sản xuất giữ mã. Nạp MỘT lần cho cả dòng thời gian, đừng tra từng dòng.
    dv_ten = DonViDoRepository(db).ten_theo_ma()

    if goi_id is not None:
        for pb in db.execute(
            select(SanXuatPhienBan).where(SanXuatPhienBan.goi_id == goi_id)
        ).scalars():
            ly_do = f" — {pb.ly_do}" if pb.ly_do else ""
            ra.append({
                "loai": "phat_hanh",
                "luc": _aware(pb.created_at),
                "nguoi_id": pb.phat_hanh_by_id,
                "cong_viec_id": None,
                "ten_viec": None,
                "noi_dung": f"Phát hành phiên bản {pb.so}{ly_do}",
            })

    _DONG = {
        PHIEN_KET_THUC: "Kết thúc",
        PHIEN_TAM_DUNG: "Tạm dừng",
        PHIEN_DOI_MAY: "Đổi máy giữa chừng",
    }
    for cv in bc.cong_viec_du(lsx_id):
        ten = ten_cv.get(cv.id)
        for p in bc.phien[cv.id]:
            ra.append({
                "loai": "bat_dau",
                "luc": _aware(p.bat_dau),
                "nguoi_id": p.created_by,
                "cong_viec_id": cv.id,
                "ten_viec": ten,
                "noi_dung": f"Bắt đầu chạy {ten}",
            })
            if p.ket_thuc is not None:
                nhan = _DONG.get(p.loai_dong or "", "Dừng")
                ly_do = f" — {p.ly_do}" if p.ly_do else ""
                ra.append({
                    "loai": p.loai_dong or "dung",
                    "luc": _aware(p.ket_thuc),
                    "nguoi_id": p.created_by,
                    "cong_viec_id": cv.id,
                    "ten_viec": ten,
                    "noi_dung": f"{nhan} {ten}{ly_do}",
                })
        for b in bc.batch[cv.id]:
            ra.append({
                "loai": "san_luong",
                "luc": _aware(b.ket_thuc),
                "nguoi_id": b.created_by,
                "cong_viec_id": cv.id,
                "ten_viec": ten,
                "noi_dung": (f"Ghi sản lượng {ten}: {_f(b.tot):g} tốt · "
                             f"{_f(b.hong):g} hỏng {nhan_don_vi(dv_ten, b.don_vi)}"),
            })
        for k in bc.kcs[cv.id]:
            ra.append({
                "loai": "kcs",
                "luc": _aware(k.ket_thuc),
                "nguoi_id": None,
                "cong_viec_id": cv.id,
                "ten_viec": ten,
                "noi_dung": (
                    f"KCS {ten}: {_f(k.so_luong_dat):g} đạt · "
                    f"{_f(k.so_luong_khong_dat):g} không đạt "
                    f"({_KCS_KET_LUAN_NHAN.get(k.ket_luan or '', 'chưa rõ kết luận')})"
                ),
            })

    for y in bc.su_co[lsx_id]:
        ra.append({
            "loai": "su_co",
            "luc": _aware(y.thoi_diem),
            "nguoi_id": y.nguoi_bao_id,
            "cong_viec_id": y.cong_viec_id,
            "ten_viec": ten_cv.get(y.cong_viec_id),
            "noi_dung": f"Báo sự cố {y.ma}: {y.bo_phan_hong}",
        })

    for yc in bc.nhap_kho_yc[lsx_id]:
        ra.append({
            "loai": "de_nghi_nhap_kho",
            "luc": _aware(yc.created_at),
            "nguoi_id": yc.created_by,
            "cong_viec_id": None,
            "ten_viec": None,
            "noi_dung": f"Đề nghị nhập kho {_f(yc.so_luong_yeu_cau):g} {nhan_don_vi(dv_ten, yc.don_vi)}",
        })
        if yc.xac_nhan_last_luc is not None:
            ra.append({
                "loai": "kho_nhan",
                "luc": _aware(yc.xac_nhan_last_luc),
                "nguoi_id": yc.xac_nhan_last_by_id,
                "cong_viec_id": None,
                "ten_viec": None,
                "noi_dung": f"Kho đã nhận {_f(yc.so_luong_xac_nhan):g} {nhan_don_vi(dv_ten, yc.don_vi)}",
            })

    for e in lich_su_nhan_luc:
        if e["loai"] == "giao_nguoi":
            noi_dung = f"Giao {e['nguoi']} vào {e['ten_viec']}"
        elif e["loai"] == "rut_nguoi":
            ly_do = f" — {e['ly_do']}" if e["ly_do"] else ""
            noi_dung = f"Rút {e['nguoi']} khỏi {e['ten_viec']}{ly_do}"
        else:
            noi_dung = f"Đổi máy {e['may_cu']} → {e['may_moi']} ở {e['ten_viec']}"
        ra.append({
            "loai": e["loai"],
            "luc": e["luc"],
            "nguoi_id": None,
            "cong_viec_id": e["cong_viec_id"],
            "ten_viec": e["ten_viec"],
            "noi_dung": noi_dung,
            "nguoi_ten": e["nguoi"],
        })

    ten_user = _ten_user(db, {e.get("nguoi_id") for e in ra})
    for e in ra:
        e["nguoi"] = e.pop("nguoi_ten", None) or ten_user.get(e.pop("nguoi_id", None))
        e.pop("nguoi_id", None)
    ra.sort(key=lambda e: (e["luc"], e["loai"]))
    return ra


def _ma_bai_ghep(db: Session, bc: BoiCanh, lsx_id: int) -> dict[int, str]:
    """`{bai_ghep_id: mã bài}` của những bài mà lệnh là thành viên. Rỗng ⇒ KHÔNG chạm DB.

    `boi_canh` chỉ nạp công việc ghép (`cv.bai_ghep_id`), không nạp bản thân bài — mà dòng "bỏ
    qua" của bảng cân đối chỉ nhận diện được bằng MÃ (`ke_hoach_vat_tu_service.py:995` ghi
    `bg.ma`). Một câu cho cả tập, và chỉ khi lệnh thật sự nằm trong bài ghép.
    """
    from ...models.bai_ghep import BaiGhep

    ids = {cv.bai_ghep_id for cv in bc.cong_viec_ghep[lsx_id] if cv.bai_ghep_id is not None}
    if not ids:
        return {}
    return {
        int(r[0]): r[1]
        for r in db.execute(select(BaiGhep.id, BaiGhep.ma).where(BaiGhep.id.in_(ids))).all()
    }


def _ten_user(db: Session, ids) -> dict[int, str]:
    """`{user_id: tên}` cho MỘT lượt đọc — mặt đọc phơi tên chứ không phơi id trần, và một câu cho
    cả danh sách thay vì N+1 (cùng lối `san_xuat_kho_repo.ten_kho_theo_ids`)."""
    can = {int(i) for i in ids if i is not None}
    if not can:
        return {}
    return {
        int(r[0]): r[1]
        for r in db.execute(select(User.id, User.name).where(User.id.in_(can))).all()
    }


# --- Cửa vào ------------------------------------------------------------------------------------
def ho_so(
    db: Session, lsx_id: int, *, sale_ids: set[int] | None, bay_gio: datetime | None = None,
    chi_khoi: set[str] | None = None,
) -> dict:
    """Hồ sơ đầy đủ của MỘT lệnh đã phát hành. `sale_ids=None` = thấy hết (scope `all`).

    CHẶN TRƯỚC, DỰNG SAU: `pham_vi.chan_ngoai_pham_vi` ném 404 khi lệnh không tồn tại hoặc chưa
    phát hành, ném 403 khi lệnh có thật nhưng ngoài phạm vi người gọi — và câu 403 KHÔNG mang một
    chữ nào của nội dung lệnh. Hai mã khác nhau vì hai câu khác nhau: 404 nói "màn này không có
    lệnh nào như thế", 403 nói "có, nhưng không phải phần việc của bạn". Trả 404 cho cả hai là
    giấu luôn cả thông tin người dùng có quyền biết (rằng họ cần xin quyền, chứ không phải gõ sai).

    `bay_gio` để bài test chốt được con số, đúng lý do `danh_sach.danh_sach` nhận tham số ấy.

    --- `chi_khoi`: DỰNG ÍT KHỐI HƠN, KHÔNG PHẢI ĐỌC BẰNG ĐƯỜNG KHÁC ---------------------------
    `None` (mặc định) = y hệt trước: dựng cả 13 khối, trả cả 13 khoá. Truyền một tập tên khối thì
    hàm CHỈ dựng đúng những khối đó và chỉ trả đúng những khoá đó.

    Vì sao có tham số này thay vì để nơi gọi tự truy vấn: phiếu công nghệ (`phieu_cong_nghe`) chỉ
    cần `thong_tin` · `thong_so` · `routing` · `phien_ban`, nhưng nó PHẢI đi qua đúng cửa quyền ở
    đây. Mở một đường đọc thứ hai cho phiếu là hai chỗ phải nhớ luật 404/403 và hai chỗ có thể
    SELECT nhầm một cột tiền. Cái giá của bản cũ không chỉ là chậm mà là GIÒN: engine cân đối vật
    tư (`trang_thai.den_va_bang` → `ke_hoach_vat_tu_service.can_doi()`, phình theo số bài ghép
    trong TOÀN kế hoạch) hay khối giao hàng ném lỗi vì một trạng thái dữ liệu chẳng liên quan gì
    tới tờ giấy thì nút In chết theo, trong khi tổ trưởng đang đứng chờ.

    `chan_ngoai_pham_vi` vẫn chạy TRƯỚC mọi thứ, không phụ thuộc `chi_khoi` — đừng đảo thứ tự đó.

    Vài khối là NGUỒN của khối khác nên vẫn được dựng dù không nằm trong `chi_khoi` (chỉ không trả
    ra): `nhan_luc` nuôi `timeline`, `giao_hang` nuôi `so_lenh_trong_nhom` của `kho`.
    """
    can = set(KHOI) if chi_khoi is None else set(chi_khoi)
    la = can - set(KHOI)
    if la:
        # Gõ sai tên khối mà im lặng thì nơi gọi nhận một dict THIẾU khoá và nổ ở chỗ khác, xa
        # nguyên nhân. Đây là lỗi lập trình, ném ngay tại chỗ.
        raise ValueError(f"chi_khoi có khối lạ: {sorted(la)} — hợp lệ: {sorted(KHOI)}")

    lsx = db.get(Lsx, lsx_id)
    pham_vi.chan_ngoai_pham_vi(db, lsx, sale_ids)
    bay_gio = _aware(bay_gio) if bay_gio is not None else datetime.now(timezone.utc)

    bc = boi_canh.nap(db, [lsx_id])
    # MỘT lượt engine vật tư cho cả hồ sơ: `den_va_bang` trả kèm chính bảng cân đối mà nó vừa
    # dựng để tính đèn. Bản trước gọi `can_doi()` lượt thứ hai ở đây — chạy lại đúng engine vừa
    # chạy xong, đo được 143 câu SQL cho một lần mở hồ sơ (1 bài ghép trong kho).
    den = bang = None
    tinh = None
    if can & {"tien_do", "vat_tu"}:
        den, bang = trang_thai.den_va_bang(db, [lsx_id])
    if "tien_do" in can:
        xong = tien_do.du_kien_xong(bc, lsx_id, bay_gio)
        tinh = {
            "xong": xong,
            "canh_bao": trang_thai.co_canh_bao(bc, lsx_id, bay_gio, den_vat_tu=den, xong=xong),
            "trang_thai": trang_thai.trang_thai_chinh(
                bc, lsx_id, bay_gio, den_vat_tu=den, xong=xong
            ),
        }

    buocs: list[LsxCongDoan] = []
    if can & {"routing", "vat_tu"}:
        buocs = list(db.execute(
            select(LsxCongDoan)
            .where(LsxCongDoan.lsx_id == lsx_id)
            .order_by(LsxCongDoan.thu_tu, LsxCongDoan.id)
        ).scalars())
    thu_tu_buoc = {b.id: b.thu_tu for b in buocs}

    cvs = bc.cong_viec_du(lsx_id)
    cv_ids = [cv.id for cv in cvs]
    can_nhan_luc = bool(can & {"nhan_luc", "timeline"})
    ten_to: dict[int, str] = {}
    if can_nhan_luc or "routing" in can:
        to_ids = {cv.department_id for cv in cvs if cv.department_id is not None}
        to_ids |= {b.department_id for b in buocs if b.department_id is not None}
        ten_to = {
            int(r[0]): r[1]
            for r in db.execute(
                select(Department.id, Department.name).where(Department.id.in_(to_ids))
            ).all()
        } if to_ids else {}

    # Vị trí của bước ĐANG LÀM trong chuỗi — mốc chia vật tư thành "cần bây giờ" và "cần sau".
    # Không có bước nào (lệnh chưa có công việc) ⇒ mốc là bước ĐẦU: mọi thứ đều là chuyện sắp tới.
    thu_tu_hien_tai = 0
    if "vat_tu" in can:
        hien_tai = danh_sach.buoc_hien_tai(bc, lsx_id)
        if hien_tai is not None:
            cua_no = [hien_tai.lsx_cong_doan_id] if hien_tai.lsx_cong_doan_id is not None else []
            cua_no += bc.buoc_phu.get(hien_tai.id, [])
            vt = [thu_tu_buoc[b] for b in cua_no if b in thu_tu_buoc]
            thu_tu_hien_tai = min(vt) if vt else 0

    nhan_luc = (
        _nhan_luc(db, bc, lsx_id, cv_ids=cv_ids, ten_to=ten_to)
        if can_nhan_luc else {"hien_tai": [], "lich_su": []}
    )
    goi_id = _goi_id(db, bc, lsx_id) if can & {"phien_ban", "timeline"} else None
    goi = db.get(SanXuatGoiPhatHanh, goi_id) if goi_id is not None else None
    giao_hang = None
    if can & {"giao_hang", "kho"}:
        nhom_id = next((cv.nhom_id for cv in cvs if cv.nhom_id is not None), None)
        giao_hang = _giao_hang(db, bc, lsx_id, nhom_id=nhom_id)
    ma_bai = _ma_bai_ghep(db, bc, lsx_id) if "vat_tu" in can else {}

    ra: dict = {}
    if "thong_tin" in can:
        ra["thong_tin"] = _thong_tin(bc, lsx_id)
    if "tien_do" in can:
        ra["tien_do"] = _tien_do(bc, lsx_id, bay_gio, tinh)
    if "thong_so" in can:
        ra["thong_so"] = _thong_so(lsx)
    if "routing" in can:
        ra["routing"] = _routing(bc, lsx_id, buocs, ten_to, _khuon_buoc(db, buocs))
    if "vat_tu" in can:
        ra["vat_tu"] = _vat_tu(
            bc, lsx_id, bang=bang, ma_bai=ma_bai,
            thu_tu_buoc=thu_tu_buoc, thu_tu_hien_tai=thu_tu_hien_tai,
        )
    if "nhan_luc" in can:
        ra["nhan_luc"] = nhan_luc
    if "san_luong" in can:
        ra["san_luong"] = _san_luong(bc, lsx_id)
    if "su_co" in can:
        ra["su_co"] = _su_co(db, bc, lsx_id)
    if "kcs" in can:
        ra["kcs"] = _kcs(bc, lsx_id)
    if "kho" in can:
        ra["kho"] = _kho(bc, lsx_id, so_lenh_trong_nhom=giao_hang["so_lenh_trong_nhom"])
    if "giao_hang" in can:
        ra["giao_hang"] = giao_hang
    if "timeline" in can:
        ra["timeline"] = _timeline(
            db, bc, lsx_id, goi_id=goi_id, lich_su_nhan_luc=nhan_luc["lich_su"]
        )
    if "phien_ban" in can:
        # ĐỌC TỪ GÓI, không phải cột trên `lsx` (không có cột nào như thế, và đừng thêm).
        ra["phien_ban"] = goi.version_hien_tai if goi is not None else None
    return ra
