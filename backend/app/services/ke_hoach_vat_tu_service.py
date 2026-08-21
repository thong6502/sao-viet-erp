"""Kế hoạch vật tư — bảng CÂN ĐỐI: *cần bao nhiêu · có bao nhiêu · thiếu bao nhiêu · bao giờ phải đặt*.

Hệ đã tính ngược ra nhu cầu từng bước (lệnh hộp 10.000 cái → 2.961 tờ nguyên), kho đã có sổ lô và
tồn theo mặt hàng gốc, thu mua đã có yêu cầu mua + ngày về dự kiến — nhưng ba khối đó không nhìn
thấy nhau. File này là chỗ chúng gặp nhau, và **chỉ đọc**: không khoá lô, không giữ chỗ vật lý,
không lĩnh hộ ai. "Giữ chỗ" ở đây chỉ là THỨ TỰ TRONG BẢNG theo ngày cần — lệnh nào cần trước thì
được tính trước, lệnh sau nhìn phần còn lại.

Bốn giai đoạn của `can_doi()`:
  (a) gom dòng nhu cầu (giấy của lệnh chưa ghép · giấy của bài ghép · vật tư khai tay · khuôn bế),
  (b) suy NGÀY CẦN của từng dòng,
  (c) quy mọi thứ về ĐƠN VỊ GỐC của mặt hàng (kho đếm theo đơn vị đó),
  (d) chạy con trỏ tồn theo ngày cần cho từng mặt hàng.

⚠️ HAI BẪY ĐẾM HAI LẦN — sai chỗ này là đi mua giấy thừa mà không ai phát hiện:

1. **Đã cấp**: kho xuất rồi thì `stock_lots.sl_con_lai` ĐÃ GIẢM, tức tồn đã phản ánh. Phần đã cấp
   vì thế chỉ được trừ vào NHU CẦU, TUYỆT ĐỐI không trừ thêm lần nữa vào tồn.
2. **"Đang mua" chính là "hàng đang về"** — cùng một lô hàng, một cái tên khác. Chỉ cộng MỘT lần,
   ở dòng cộng hàng đang về. Không có thêm phép trừ "đang mua" nào khỏi nhu cầu.

Và một cái bẫy ngược lại: *đang lĩnh* (đề nghị kho đã lập, kho CHƯA ghi sổ) chỉ được hiện làm NHÃN.
Hàng chưa ra khỏi kho thì tồn vẫn còn — trừ nó là trừ một thứ chưa xảy ra.

Mọi số ở đây DẪN XUẤT, tính lúc đọc, không lưu bảng nào.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
from ..models.don_vi_do import TRAM_TO, TRAM_TO_NGUYEN
from ..services.dong_giay import ban_do_tram, don_vi_chuoi, ma_cua_tram, tram_cua
from ..models.lsx import (
    LB_MAY,
    TT_DA_LAP_KE_HOACH,
    TT_DA_PHAT_HANH,
    TT_SAN_SANG,
    Lsx,
    LsxCongDoan,
)
from ..models.purchase import DPR_IN_PURCHASE, DPR_PENDING_APPROVAL, PR_PENDING
from ..models.stock_request import REQ_DONE
from ..models.vat_lieu_kho import HANG_GIAY
from ..repositories.ke_hoach_vat_tu_repo import KeHoachVatTuRepository
from ..repositories.purchase_repo import DepartmentPurchaseRequestRepository
from .bien_cong_thuc import quy_cach_bien, quy_cach_bien_bai
from .bien_cong_thuc import ngu_canh_lenh
from .thanh_phan_engine import safe_eval
from .quy_doi_service import _so, bien_trong, cap_map, doi, don_vi_map

# Lệnh ở ba trạng thái này là thứ kế hoạch phải lo giấy: đã chốt kỹ thuật, chỉ còn chờ chạy.
# `nhap`/`cho_bo_sung` chưa chốt quy cách nên số tờ còn xê dịch — đưa vào bảng là mua theo số sắp đổi.
TRANG_THAI_TINH = (TT_SAN_SANG, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH)

# Vật tư phải nằm ở chân máy TRƯỚC giờ chạy chừng này phút (lấy hàng, cân, cắt, chuyển tới máy).
# Hằng số module chứ không phải cột khai: đây là thói quen xưởng, không phải thuộc tính của món hàng.
CAP_PHAT_TRUOC_PHUT = 120

# Đệm kiểm nhập: hàng về tới cổng chưa dùng được ngay (đếm, kiểm, nhập kho). Cộng vào lúc suy
# HẠN CHÓT PHẢI ĐẶT để cái đèn "đặt muộn" không bật đúng vào hôm đã quá muộn.
DEM_KIEM_NHAP_NGAY = 1

# Giờ làm quy đổi khi suy MỐC TẠM cho lệnh chưa xếp — cùng con số `lsx_service` dùng, để hai nơi
# không nói hai chuyện về "lệnh này chạy mất mấy ngày".
GIO_LAM_MOI_NGAY = 8

MAU_XAM, MAU_XANH, MAU_VANG, MAU_DO = "xam", "xanh", "vang", "do"
# Trạng thái THỨ NĂM: dòng KHÔNG ĐÁNH GIÁ ĐƯỢC (thiếu đường quy đổi đơn vị).
#
# Vì sao không gộp vào `xam`: xám nghĩa là "đã cấp đủ, hết việc phải lo" — mạnh hơn cả "đủ". Dòng
# hệ thống không tính nổi mà đeo nhãn đó là nói ngược sự thật, và tệ hơn: nó rơi khỏi bộ lọc "chỉ
# mặt hàng đang thiếu", tức biến mất đúng lúc người ta đi tìm việc phải lo.
MAU_KHONG_RO = "khong_ro"
# Trạng thái THỨ SÁU (17/08/2026): ĐÃ MUA RỒI, hàng đang về — nhưng về SAU ngày cần.
#
# Vì sao không để chung `do`: lô về sau ngày cần thì không được cộng vào tồn, nên dòng đỏ y hệt
# dòng CHƯA MUA GÌ. Hai ca đó có cách xử NGƯỢC NHAU — chưa mua thì đi mua, còn đã mua mà về muộn
# thì phải DỜI LỊCH bước tiêu thụ (hoặc hối NCC). Người dùng nhìn màu đỏ rồi tick đi mua lần nữa
# là MUA ĐÚP đúng lô đang trên đường về.
MAU_VE_MUON = "ve_muon"

# Cờ cảnh báo trên dòng — tập MỞ, phía FE chỉ cần biết dòng có cảnh báo thì tô nhạt + hiện tooltip.
CB_KHONG_DOI_CHIEU = "khong_doi_chieu_duoc"
# Mốc tạm KHÔNG suy được: lệnh chưa xếp mà cũng chưa gán máy ⇒ `thoi_luong_buoc` ra 0 (tốc độ và
# thời gian chuẩn bị đều lấy từ MÁY) ⇒ "hạn SX − 0" = đúng hạn SX. Đó chính là cái bẫy plan gạch
# chân: hạn SX là mốc CUỐI chuỗi, giấy cần ở ĐẦU chuỗi, lấy thẳng là đặt hàng trễ cả chuỗi.
#
# Xử bằng cách NÓI RA, không bịa số ngày mặc định: bịa là biến một lỗ im lặng thành một con số sai
# im lặng, tệ hơn.
CB_DAN_KHONG_SUY_DUOC = "dan_khong_suy_duoc"

# Ba lý do khiến mốc tạm không suy được → câu chữ cho người mua. MỘT bảng dùng chung cho cả câu
# "mọi dòng đều mờ" lẫn câu "trộn lệnh rõ với lệnh mờ" — hai chỗ nói cùng một chuyện thì phải nói
# cùng một cách, không thì người đọc tưởng là hai vấn đề khác nhau.
_LY_DO_MOC = {
    "chua_gan_may": "còn bước chưa gán máy",
    "chua_co_han": "chưa khai hạn sản xuất",
    "khong_co_thanh_vien": "bài ghép chưa có thành viên nào",
}


class KeHoachVatTuError(Exception):
    pass


class KeHoachVatTuValidationError(KeHoachVatTuError):
    pass


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _hom_nay() -> date:
    return datetime.now(timezone.utc).date()


def _xep_vet(v: dict) -> int:
    """Thứ tự CHẮC → LỎNG của một vết mua. Chip vật tư chỉ đủ chỗ MỘT dòng nên nó lấy phần tử đầu;
    thứ tự này quyết định người dùng đọc được câu nào trước.

    Phiếu đã duyệt kèm ngày về là lời hứa chắc nhất (*"1/9 có hàng"*); YCMH vừa lập là lỏng nhất
    (*"đã có người đề nghị, chưa ai duyệt"*). Xếp ngược lại thì chip báo "mới đề nghị" trong khi
    hàng đã nằm trên xe — đúng kiểu tin xấu che mất tin tốt.
    """
    if v.get("loai") == "pmh":
        if v.get("trang_thai") == PR_PENDING:
            return 2
        return 0 if v.get("ngay_ve") else 1
    return {DPR_IN_PURCHASE: 3, DPR_PENDING_APPROVAL: 4}.get(v.get("trang_thai"), 5)


def _khoa_dong(hang_loai, hang_id, d: dict) -> tuple:
    """KHOÁ nhận dạng MỘT dòng của bảng cân đối — hợp đồng giữa bảng và nút "Đề nghị mua".

    Phải khớp từng phần với `khoa()` bên `VatTuKeHoachView.tsx`; lệch một phần tử là client tick
    một dòng mà server tra ra dòng khác (hoặc không tra ra gì).

    """
    return (hang_loai, hang_id, d.get("lsx_id"), d.get("bai_ghep_id"), d.get("buoc_id"))


class KeHoachVatTuService:
    """Bảng cân đối vật tư. CHỈ ĐỌC — không có đường nào từ đây ghi vào kho.

    Nhận sẵn service/repo từ router (`get_service(db)`), không tự dựng: cùng lối
    `routers/kho_request.py`, và nhờ vậy test bơm được bản giả cho từng nguồn số liệu.
    """

    def __init__(
        self,
        db: Session,
        *,
        lsx_repo,
        bai_ghep_repo,
        hang,
        lots,
        requests,
        purchases,
        suppliers,
        don_vi,
        repo=None,
        dpr=None,
    ) -> None:
        self.db = db
        # Repo RIÊNG của bảng cân đối — mọi truy vấn của màn này đi qua đây, service thôi tự
        # `db.execute`. Mặc định tự dựng để chỗ gọi cũ không phải sửa; test bơm bản giả được.
        self.repo = repo or KeHoachVatTuRepository(db)
        self.lsx_repo = lsx_repo
        self.bai_ghep_repo = bai_ghep_repo
        self.hang = hang                # VatLieuKhoService — danh mục gốc + quy đổi
        self.lots = lots                # StockLotRepository
        self.requests = requests        # StockRequestRepository
        self.purchases = purchases      # PurchaseRequestRepository
        # YCMH của bộ phận — chỉ để bảng NÓI ĐƯỢC "đã có ai đề nghị mua món này chưa". Tự dựng
        # như `repo` ở trên để chỗ gọi cũ khỏi phải sửa; test bơm bản giả được.
        self.dpr = dpr or DepartmentPurchaseRequestRepository(db)
        self.suppliers = suppliers      # SupplierRepository
        self.don_vi = don_vi            # DonViDoRepository

    # ================== (c) QUY VỀ ĐƠN VỊ GỐC ==================

    def _nap_don_vi(self) -> None:
        """Nạp danh mục đơn vị + bảng cặp MỘT lần cho cả bảng (không N+1 theo dòng)."""
        # `all_rows`: bảng tra để QUY VỀ ĐƠN VỊ GỐC cho kế hoạch đã lập. Đơn vị ngừng dùng mà lọc
        # ở đây thì dòng vật tư cũ mất đường quy đổi, số về 0 trong im lặng.
        self._dvs = don_vi_map(self.don_vi.all_rows())
        self._cap_rows = list(self.don_vi.cap_rows())
        # Đồ thị cặp quy đổi dựng SẴN một lần cho cả bảng. Trước 18/08/2026 chỗ này đi qua
        # `doi_theo_quy_cach`, mà hàm đó gọi `cap_map(...)` — dựng LẠI nguyên đồ thị — ở MỖI dòng.
        # Bảng cân đối có bao nhiêu dòng thì đồ thị dựng lại bấy nhiêu lần, trong khi bảng cặp là
        # danh mục dùng chung, không đổi giữa hai dòng. Đo hồ sơ 300 lệnh: 30% thời gian `can_doi`
        # rơi vào `_quy_doi_dong` mà phần lớn là dựng lại đồ thị này.
        self._cap = cap_map(self._cap_rows)
        self._tram_cache = None

    def _tram(self) -> dict[str, str]:
        """Bản đồ `{mã đơn vị: trạm}` — CACHE.

        `getattr` chứ không đọc thẳng thuộc tính: `_nap_don_vi` mới là nơi khởi tạo cache, mà
        `_buoc_dau_dong_giay` có thể được gọi trước nó. Bảng cân đối duyệt cả trăm lệnh nên hỏi lại
        danh mục theo từng lệnh là đúng bài N+1.
        """
        if getattr(self, "_tram_cache", None) is None:
            self._tram_cache = ban_do_tram(self.db)
        return self._tram_cache

    def _quy_cach_cua(self, hang_loai: str, obj, qc_lenh: dict | None = None) -> dict | None:
        """Biến cho quy đổi ĐỘNG của mặt hàng đang xét.

        GIẤY: bơm `dai`/`rong` (mét) + `gsm` — đây chính là cách cạnh động
        `1 tờ = dinh_luong × dai × rong` kg được bật lên. Bơm từ NƠI GỌI là đúng thiết kế của
        `quy_doi_service`: chỉ nơi gọi mới biết mình đang đếm tờ NGUYÊN (mua giấy) hay tờ IN.

        **Khổ lấy từ LỆNH trước, danh mục sau (chủ chốt 2026-08-09).** Danh mục Giấy cố ý KHÔNG có
        ô khổ (chốt 21/07: giá theo đ/kg, khổ nhập ở phiếu tính giá), nên giấy do người dùng tự khai
        không có khổ nào để đổi tờ→kg và mọi dòng của nó rơi vào "chưa đánh giá được". Mà lệnh thì
        LUÔN mang sẵn khổ tờ in + định lượng — và đó mới là khổ giấy THỰC SỰ bị tiêu thụ, đúng hơn
        cả một khổ mặc định trong danh mục.

        Vẫn ngã về danh mục khi lệnh cũ chưa có khổ trong quy cách. Không nơi nào có khổ ⇒ cạnh tắt
        ⇒ dòng nhận cờ `khong_doi_chieu_duoc`, KHÔNG đoán một con số.
        """
        if hang_loai != HANG_GIAY:
            return None
        qc = dict(qc_lenh or {})
        # Bơm TRỌN quy cách lệnh rồi chèn khổ đã chốt lên trên: từ 11/08/2026 công thức quy đổi
        # dùng tên khổ CỤ THỂ (`dai_in`/`dai_nguyen`) thay cho biến vai trò `dai`/`rong`, nên phải
        # đưa cả hai mức. Thiếu khổ nguyên thì dòng `1 tờ nguyên = … kg` không dùng được — và đó
        # đúng là câu trả lời thật, hơn là cân bằng khổ tờ in.
        qc["dai_in"] = (_f(qc.get("kho_in_dai")) or _f(getattr(obj, "kho_dai", 0))) / 1000.0
        qc["rong_in"] = (_f(qc.get("kho_in_rong")) or _f(getattr(obj, "kho_rong", 0))) / 1000.0
        # Khổ NGUYÊN: lệnh → danh mục → **khổ tờ IN**. Nhánh thứ ba thêm 14/08/2026 cùng lúc gỡ cặp
        # động: công thức lượng của giấy đếm bằng `dai_nguyen`, mà lệnh dựng tay / lệnh cũ có thể chỉ
        # mang khổ in. Thà lấy khổ tờ in — đúng thứ giấy THỰC SỰ bị tiêu thụ, như docstring trên đã
        # chốt — còn hơn để 0 rồi cả dòng giấy rơi vào "chưa tính được".
        qc["dai_nguyen"] = (_f(qc.get("kho_nguyen_dai")) or _f(getattr(obj, "kho_dai", 0))
                            or _f(qc.get("kho_in_dai"))) / 1000.0
        qc["rong_nguyen"] = (_f(qc.get("kho_nguyen_rong")) or _f(getattr(obj, "kho_rong", 0))
                             or _f(qc.get("kho_in_rong"))) / 1000.0
        qc["dinh_luong"] = (_f(qc.get("gsm")) or _f(getattr(obj, "gsm", 0))) / 1000.0
        return qc

    def _ve_goc(self, hang: tuple[str, int], dvt: str, so_luong: float,
                qc_lenh: dict | None = None, *, tong_lenh: bool = False) -> dict:
        """Quy `so_luong` từ `dvt` về ĐƠN VỊ GỐC của mặt hàng.

        Trả `{sl, don_vi_goc_ten, hien_thi}` hoặc `{loi}`. Đi qua ĐÚNG một engine
        (`doi_theo_quy_cach`) như kho và NCC — hai đường tính là hai đường lệch, mà lệch ở đây là
        lệch số giấy đi mua.

        `qc_lenh` = quy cách của LỆNH/BÀI sinh ra dòng này — nguồn khổ giấy ưu tiên (xem
        `_quy_cach_cua`). Không truyền thì rơi về khổ ở danh mục như cũ.
        """
        obj = self._objs.get(hang)
        if obj is None:
            return {"loi": "Mặt hàng không còn trong danh mục."}
        goc = (getattr(obj, "don_vi_gia", None) or "").strip()
        if not goc:
            return {"loi": f"“{obj.ten}” chưa chọn đơn vị tính ở danh mục."}
        qc = self._quy_cach_cua(hang[0], obj, qc_lenh)
        # CÔNG THỨC LƯỢNG của chính mặt hàng đi TRƯỚC (mg 0194/0195): nó đã tự nhân số lượng của
        # lệnh nên ra thẳng TỔNG theo đơn vị gốc — không quy đổi từ `dvt` nữa.
        #
        # Ở đây quy đổi vẫn còn (khác `LsxService._luong_vat_tu`, đã bỏ hẳn 18/08/2026) vì hai bên
        # hỏi hai câu khác nhau: bên kia hỏi "một tờ ăn mấy kg keo" — tuỳ món, phải có công thức;
        # bên này chỉ đổi ĐƠN VỊ ĐO của cùng một món (kế hoạch nghĩ theo tờ, kho đếm theo ram), là
        # quan hệ bất biến đúng tầm của cầu quy đổi.
        #
        # ⚠️ CHỈ cho đường NHU CẦU (`tong_lenh=True`). Công thức trả TỔNG của cả lệnh, nên chạy nó ở
        # đường "đã cấp" / "đang về" là VỨT số thật của phiếu kho rồi thay bằng tổng nhu cầu — bảng
        # cân đối sẽ luôn báo đã cấp đủ. Chưa nổ vì tới 14/08/2026 chưa mặt hàng nào khai công thức;
        # điền công thức vào là nổ ngay, nên chặn ở đây cùng lượt.
        #
        # ⚠️ Và CHỈ cho GIẤY (20/08/2026). Hai loại dòng hỏi hai câu khác nhau:
        #   * GIẤY: dòng mang SỐ TỜ của lệnh, phải có công thức mới ra kg ⇒ chạy ở đây là đúng.
        #   * VẬT TƯ: dòng lấy thẳng `lsx_cong_doan_vat_tu.so_luong` — số đó CHÍNH LÀ kết quả công
        #     thức, `LsxService._luong_vat_tu` đã tính lúc lưu công đoạn, bằng ngữ cảnh ĐẦY ĐỦ có
        #     cả `sl_vao`/`sl_ra` của bước. Chạy lại ở đây là tính lần hai bằng ngữ cảnh NGHÈO hơn
        #     (`_quy_cach_cua` trả None cho mọi thứ không phải giấy ⇒ 16 biến đều 0), nên mọi món
        #     có công thức đều rơi vào "Chưa biết <biến>" và nhu cầu về 0 — đúng hỏng đã thấy ở
        #     LSX26-0020: BOM ghi 10 bản kẽm · 100 kg mực · 91.000 m² màng, kế hoạch vật tư hiện
        #     "0 · Chưa rõ ĐVT" cho cả năm dòng.
        ct = (getattr(obj, "cong_thuc_luong", None) or "").strip() if (
            tong_lenh and hang[0] == HANG_GIAY) else ""
        if ct:
            ctx = ngu_canh_lenh(qc)
            thieu = [b for b in bien_trong(ct) if _f(ctx.get(b)) <= 0]
            if thieu:
                return {"loi": f"Chưa biết {', '.join(thieu)} nên chưa tính được lượng {obj.ten}."}
            try:
                so_luong, dvt = float(safe_eval(ct, ctx)), goc
            except (ValueError, ZeroDivisionError) as e:
                return {"loi": f"Công thức lượng của {obj.ten} không chạy được ({e})."}
        # `doi` thẳng thay cho `doi_theo_quy_cach`: hàm kia chỉ làm thêm đúng hai việc — bỏ `qc`
        # (đã hết dùng từ 14/08/2026) và dựng `cap_map`, thứ nay đã có sẵn ở `self._cap`.
        kq = doi(so_luong, dvt, goc, self._dvs, self._cap)
        if "gia_tri" not in kq:
            return {"loi": kq.get("ly_do") or "Không đổi được đơn vị."}
        goc_ten = (self._dvs.get(goc.lower()) or {}).get("ten") or goc
        dvt_ten = (self._dvs.get((dvt or "").strip().lower()) or {}).get("ten") or dvt
        # Hai đơn vị cùng lúc: kế hoạch NGHĨ theo tờ, kho ĐẾM theo đơn vị gốc. Hiện một cái thôi là
        # một trong hai bên phải nhẩm trong đầu, mà nhẩm thì sai.
        hien_thi = (
            f"{_so(so_luong)} {dvt_ten}"
            if dvt_ten == goc_ten
            else f"{_so(so_luong)} {dvt_ten} ≈ {_so(kq['gia_tri'])} {goc_ten}"
        )
        return {"sl": float(kq["gia_tri"]), "don_vi_goc_ten": goc_ten, "hien_thi": hien_thi}

    # ================== (a) GOM DÒNG NHU CẦU ==================

    def _lenh_trong_pham_vi(self, include_lsx_ids: set[int] | None = None) -> list[Lsx]:
        include = {int(i) for i in (include_lsx_ids or set()) if i}
        return self.lsx_repo.cho_mrp(trang_thai=TRANG_THAI_TINH, include_ids=include)

    def _bai_trong_pham_vi(self, lenh_ids: set[int]) -> list[BaiGhep]:
        """Bài ghép có ÍT NHẤT MỘT lệnh thành viên đang trong phạm vi.

        Không lọc theo trạng thái của chính bài: bài còn `nhap` mà thành viên đã `san_sang` thì
        giấy vẫn phải mua — trạng thái bài nói về việc bình bài đã xong chưa, không nói về giấy.
        """
        return [
            b
            for b in self.bai_ghep_repo.list()
            if any(tv.lsx_id in lenh_ids for tv in b.thanh_viens)
        ]

    def _buoc_dau_dong_giay(self, lsx: Lsx) -> LsxCongDoan | None:
        """Bước ĐẦU TIÊN chạm tờ giấy — nơi giấy phải có mặt.

        Neo vào bước tiêu thụ chứ không vào bước cuối: giấy cần ở ĐẦU chuỗi. Neo nhầm vào cuối là
        đặt hàng muộn đúng bằng độ dài cả chuỗi sản xuất.

        Nhận diện theo TRẠM (`don_vi_do.tram_dong_giay`), không theo mã: `don_vi_vao` là mã xưởng
        tự đặt. So mã với `("to_nguyen","to")` thì lệnh nào khai `to_chay` cũng trượt hết vòng lặp
        rồi rơi về `buoc[0]` — thường là bước GHI KẼM, tức neo ngày cần giấy vào nhầm bước.
        """
        bd = self._tram()
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        for cd in buoc:
            if tram_cua(cd.don_vi_vao, bd) in (TRAM_TO_NGUYEN, TRAM_TO):
                return cd
        return buoc[0] if buoc else None

    def _dv_giay(self, buocs, buoc_neo=None) -> str | None:
        """MÃ đơn vị để ĐẾM số giấy của một lệnh/bài — đọc từ routing, không đóng đinh `to`.

        Đây KHÔNG phải nhãn trang trí: `_ve_goc` lấy nó đi quy đổi sang đơn vị gốc của giấy
        (tờ → kg), sai đơn vị là sai số giấy đi mua.

        Lấy chặng TỜ IN — giữ đúng ngữ nghĩa cũ, chỉ thay mã cứng bằng mã đọc từ routing. (Số đi
        kèm là `so_to_nguyen` trong khi đơn vị là chặng tờ in: chỗ lệch này CÓ SẴN từ trước, sửa nó
        là đổi lượng giấy trên bảng cân đối nên phải hỏi chủ trước, không gộp vào đây.)

        Lệnh chưa khai công đoạn nào ⇒ routing không nói gì ⇒ hỏi danh mục Đơn vị: đơn vị nào đứng
        ở trạm tờ in. Danh mục có nhiều hơn một thì KHÔNG đoán — trả None để dòng đeo cảnh báo
        "chưa đối chiếu được", thà báo còn hơn quy đổi bằng một mã bịa.
        """
        tram = self._tram()
        dv = don_vi_chuoi(buocs, tram)
        return (dv["to"] or ma_cua_tram(TRAM_TO, tram)
                or getattr(buoc_neo, "don_vi_vao", None))

    def _nap_lich(self, lsx_ids: set[int], bai_ids: set[int]) -> None:
        """Giờ bắt đầu đã xếp, tra theo bước — nguồn chính của NGÀY CẦN."""
        self._start_buoc: dict[int, datetime] = {}
        self._start_buoc_bai: dict[int, datetime] = {}
        if not lsx_ids and not bai_ids:
            return
        for r in self.repo.dong_lich_da_xep():
            if r.lsx_cong_doan_id and r.lsx_id in lsx_ids:
                self._start_buoc[r.lsx_cong_doan_id] = r.start_at
            if r.bai_ghep_cong_doan_id and r.bai_ghep_id in bai_ids:
                self._start_buoc_bai[r.bai_ghep_cong_doan_id] = r.start_at

    # ================== (b) NGÀY CẦN ==================

    def _moc_tam(self, lsx: Lsx) -> tuple[date | None, bool, str]:
        """Lệnh CHƯA xếp: `(hạn SX − tổng thời gian dẫn, suy được hay không)`.

        ⚠️ KHÔNG lấy thẳng hạn SX. Hạn SX là mốc CUỐI chuỗi, còn giấy cần ở ĐẦU chuỗi — lấy thẳng
        là đặt hàng trễ đúng bằng số ngày chạy lệnh, và cái sai đó im lặng (bảng vẫn xanh).

        Nhưng thời gian dẫn lấy từ MÁY (`thoi_luong_buoc`: tốc độ + thời gian chuẩn bị đều là thuộc
        tính của máy), nên lệnh có bước máy CHƯA GÁN MÁY thì tổng ra 0 và hiệu số rơi đúng về hạn
        SX — nhìn y như đã tính. Trả cờ `False` để dòng đó đeo cảnh báo, thay vì bịa một số ngày.

        Phần tử THỨ BA là LÝ DO không suy được (`chua_co_han` / `chua_gan_may` / rỗng). Trả về chứ
        không để nơi gọi đoán: ở dòng BÀI GHÉP, `ngay_can` lấy từ thành viên CÓ mốc còn cờ hỏng đến
        từ thành viên KHÁC, nên suy lý do bằng `bool(ngay_can)` là chẩn đoán sai — bảo người ta đi
        gán máy trong khi máy đã gán đủ, chỉ một thành viên thiếu hạn.
        """
        han = lsx.han_hoan_thanh_sx
        if han is None:
            return None, False, "chua_co_han"
        tong_phut = self._tong_phut_cua(lsx)
        # Có bước cần máy mà chưa gán ⇒ phần thời gian của nó chưa vào tổng.
        thieu_may = any(
            (cd.loai_buoc or LB_MAY) == LB_MAY and not cd.may_id for cd in lsx.cong_doans
        )
        so_ngay = ceil(tong_phut / 60.0 / GIO_LAM_MOI_NGAY) if tong_phut else 0
        return han - timedelta(days=so_ngay), not thieu_may, ("chua_gan_may" if thieu_may else "")

    def _ngay_can_buoc(self, buoc_id: int | None, *, cua_bai: bool = False) -> date | None:
        bang = self._start_buoc_bai if cua_bai else self._start_buoc
        start = bang.get(buoc_id) if buoc_id else None
        if start is None:
            return None
        return (start - timedelta(minutes=CAP_PHAT_TRUOC_PHUT)).date()

    # ================== CÁC NGUỒN SỐ ĐÃ CÓ ==================

    def _da_cap_dang_linh(self) -> tuple[dict, dict]:
        """`{(hang, lsx_id, bai_ghep_id): số}` cho ĐÃ CẤP và ĐANG LĨNH, đơn vị GỐC.

        `sl_da_ung` = kho ĐÃ ghi sổ (tồn đã trừ) ⇒ **đã cấp**.
        `sl_duyet − sl_da_ung` = đề nghị còn treo, kho chưa ghi sổ ⇒ **đang lĩnh** (chỉ là nhãn).

        ⚠️ KHOÁ Ở ĐÂY CHỈ CÓ 3 PHẦN TỬ — thiếu chiều BƯỚC, khác `_khoa_dong()` (5 phần tử). Cố ý,
        vì phiếu xuất kho chỉ gắn `lsx_id`/`bai_ghep_id`, KHÔNG có `lsx_cong_doan_id`: kho xuất cho
        một LỆNH, không xuất cho một bước.

        Hệ quả CHƯA XỬ: lệnh ăn cùng một món ở hai bước thì cùng một số "đã cấp" bị trừ vào CẢ HAI
        dòng ⇒ cả hai ra `con_phai_co = 0` ⇒ bảng báo "đã cấp đủ" trong khi xưởng còn thiếu một nửa.
        Kiểu sai tệ hơn báo thiếu oan.

        Chưa nổ vì tới 17/08/2026 `stock_request_lines` còn RỖNG. Nhưng Đợt 2 §2.3 sẽ nối "xuất kho
        cho lệnh → giảm phần giữ chỗ", tức nhánh này bắt đầu có dữ liệu — **phải quyết cách PHÂN BỔ
        số đã cấp cấp-lệnh xuống từng bước TRƯỚC khi dựng `ton_tu_do`**, không thì tồn tự do kế
        thừa nguyên phép trừ hai lần. Không sửa được bằng cách thêm `buoc_id` vào khoá: dữ liệu
        nguồn không mang chiều đó.

        Số trên dòng đề nghị theo ĐƠN VỊ NGƯỜI KHAI, phải quy về gốc mới so được với nhu cầu.
        """
        da_cap: dict[tuple, float] = {}
        dang_linh: dict[tuple, float] = {}
        self._qc_theo_khoa = getattr(self, "_qc_theo_khoa", {})
        for ln, trang_thai in self.requests.dong_xuat_theo_lenh():
            hang = (ln.hang_loai, int(ln.hang_id))
            if hang not in self._objs:
                continue
            # ⚠️ Giấy của lệnh THÀNH VIÊN bài ghép KHÔNG có dòng nhu cầu riêng (một dòng cho cả
            # bài, chống đếm đôi). Thủ kho lại chọn được "lệnh" thay vì "bài" trên cùng một ô, nên
            # phần đã cấp phải QUY VỀ BÀI — không thì nó rơi vào một khoá chẳng dòng nào tra tới,
            # và bài ghép hiện đỏ dù kho đã cấp đủ giấy.
            lsx_id, bg_id = ln.lsx_id, ln.bai_ghep_id
            if bg_id is None and lsx_id in self._bai_cua_lenh:
                lsx_id, bg_id = None, self._bai_cua_lenh[lsx_id]
            khoa = (hang, lsx_id, bg_id)
            for nguon, bang in (
                (_f(ln.sl_da_ung), da_cap),
                # Đề nghị đã DONE thì phần chênh duyệt−ứng là phần kho chốt KHÔNG cấp nữa (giao
                # thiếu, đóng phiếu), không phải hàng đang trên đường ra khỏi kho.
                (0.0 if trang_thai == REQ_DONE else max(0.0, _f(ln.sl_duyet) - _f(ln.sl_da_ung)),
                 dang_linh),
            ):
                if nguon <= 0:
                    continue
                kq = self._ve_goc(hang, ln.dvt, nguon,
                                  self._qc_theo_khoa.get((lsx_id, bg_id)))
                if "sl" in kq:
                    bang[khoa] = bang.get(khoa, 0.0) + kq["sl"]
        return da_cap, dang_linh

    def _hang_dang_ve(self) -> dict[tuple, list[tuple[date, float, str | None]]]:
        """`{hang: [(ngày về, số còn về, mã phiếu mua)]}` đã sắp theo ngày — đơn vị GỐC.

        Mã phiếu đi kèm để dòng `ve_muon` GỌI TÊN được lô đang trên đường về. Câu "đã có hàng
        đang về" trần thì người đọc không tra được đơn nào, mà việc phải làm (hối NCC hay dời
        lịch) lại nằm đúng trong tờ phiếu đó.

        "Đang mua" và "hàng đang về" là MỘT thứ; đây là chỗ DUY NHẤT nó được cộng vào. Dòng phiếu
        KHÔNG gắn mặt hàng gốc thì bỏ qua hẳn — ghép ngược bằng tên hàng là đoán, mà đoán trúng
        nhầm lô giấy khác thì bảng báo đủ trong khi thật ra thiếu.

        `expected_receipt_date` trống ⇒ KHÔNG cộng: hàng không có ngày về thì không hứa được với
        lệnh nào cả.
        """
        from .purchase_service import da_giao_theo_dong

        ra: dict[tuple, list[tuple[date, float, str | None]]] = {}
        for phieu in self.purchases.dong_dang_ve():
            ngay_ve = phieu.expected_receipt_date
            if ngay_ve is None:
                continue
            da_giao = da_giao_theo_dong(phieu)
            for ln in phieu.lines:
                if not ln.hang_loai or not ln.hang_id:
                    continue
                hang = (ln.hang_loai, int(ln.hang_id))
                if hang not in self._objs:
                    continue
                # Phiếu CÓ đợt giao ⇒ Σ các đợt. Phiếu CHƯA có đợt nào (mọi phiếu lập trước
                # 06/08/2026) ⇒ đọc `received_quantity`, KHÔNG mặc định 0: đường cũ `mark_received`
                # cho khai nhận một phần rồi "mở lại đơn" đưa phiếu về `purchased`; coi là chưa
                # nhận gì thì phần đã nhập kho bị đếm HAI LẦN (một lần ở tồn, một lần ở đang về)
                # và bảng báo đủ trong khi thật ra thiếu.
                #
                # Cố ý KHÔNG tái dùng `qty_thuc_nhan`: hàm đó đọc `received_quantity` NULL là "nhận
                # đủ" — đúng cho câu hỏi công nợ, sai cho câu hỏi này (mọi phiếu `purchased` bình
                # thường sẽ ra `con_ve = 0`, tức không phiếu nào được tính là đang về).
                nhan = (
                    float(da_giao.get(ln.id, 0.0)) if da_giao is not None
                    else _f(ln.received_quantity)
                )
                con_ve = _f(ln.quantity) - nhan
                if con_ve <= 0:
                    continue
                kq = self._ve_goc(hang, ln.unit, con_ve)
                if "sl" in kq:
                    ra.setdefault(hang, []).append(
                        (ngay_ve, kq["sl"], getattr(phieu, "code", None)))
        for ds in ra.values():
            ds.sort(key=lambda x: x[0])
        return ra

    def hang_dang_mua_khong_ngay(self) -> set[tuple]:
        """TẬP mặt hàng có phiếu mua ĐANG VỀ nhưng NCC CHƯA hẹn ngày (`expected_receipt_date` trống).

        Đây đúng là nhánh mà `_hang_dang_ve` CỐ Ý bỏ (không ngày thì không hứa được với lệnh nào),
        nên trên bảng cân đối nó rơi vào MÀU ĐỎ y như chưa mua gì. Cửa phát hành cần tách riêng để
        NÓI ĐÚNG việc: "đã đặt mua, giục NCC chốt ngày" khác hẳn "chưa mua gì". Chỉ cần định danh
        mặt hàng để giao với danh sách còn thiếu — KHÔNG quy đổi số lượng (câu hỏi là "có/không",
        không phải "bao nhiêu").
        """
        from .purchase_service import da_giao_theo_dong

        ra: set[tuple] = set()
        for phieu in self.purchases.dong_dang_ve():
            if phieu.expected_receipt_date is not None:
                continue
            da_giao = da_giao_theo_dong(phieu)
            for ln in phieu.lines:
                if not ln.hang_loai or not ln.hang_id:
                    continue
                nhan = (
                    float(da_giao.get(ln.id, 0.0)) if da_giao is not None
                    else _f(ln.received_quantity)
                )
                if _f(ln.quantity) - nhan > 0:
                    ra.add((ln.hang_loai, int(ln.hang_id)))
        return ra

    def _vet_mua_theo_hang(self) -> dict[tuple, list[dict]]:
        """`{hang: [{ma, loai, trang_thai, ngay_ve}]}` — MỌI phiếu đang chạy của mặt hàng đó.

        Thuần NHÃN, không đụng một phép cộng nào của bảng: số vẫn chỉ nhận hàng từ `_hang_dang_ve`.
        Chỗ này trả lời câu người dùng hỏi ngày 20/08/2026 — *"sao biết được cái nào đang yêu cầu
        mua"* — vì trước đó ba tình huống khác hẳn nhau lại vẽ y hệt nhau trên màn:

        * PMH duyệt rồi, có ngày về  → cộng vào tồn, dòng thành `ve_muon` (đã nói được).
        * PMH duyệt rồi, NCC chưa hẹn ngày → ĐỎ, giống hệt chưa mua gì.
        * YCMH mới đề nghị / chờ duyệt   → ĐỎ + còn nguyên nút Mua ⇒ bấm phát nữa là phiếu trùng.

        Gộp cả hai chuỗi (YCMH của bộ phận → PMH của thu mua) vì người lập kế hoạch chỉ cần biết
        "đã có ai lo món này chưa", không cần biết nó đang nằm ở khâu nào.
        """
        from .purchase_service import da_giao_theo_dong

        ra: dict[tuple, list[dict]] = {}

        def _them(hang: tuple, ma: str | None, loai: str, trang_thai: str, ngay_ve) -> None:
            if not ma:
                return
            ds = ra.setdefault(hang, [])
            # Một phiếu khai cùng mặt hàng ở hai dòng (hai khổ, hai lô) vẫn chỉ là MỘT phiếu.
            if any(x["ma"] == ma for x in ds):
                return
            ds.append({"ma": ma, "loai": loai, "trang_thai": trang_thai, "ngay_ve": ngay_ve})

        for phieu in [*self.purchases.dong_dang_ve(), *self.purchases.dong_cho_duyet()]:
            da_giao = da_giao_theo_dong(phieu)
            for ln in phieu.lines:
                if not ln.hang_loai or not ln.hang_id:
                    continue
                hang = (ln.hang_loai, int(ln.hang_id))
                if hang not in self._objs:
                    continue
                nhan = (
                    float(da_giao.get(ln.id, 0.0)) if da_giao is not None
                    else _f(ln.received_quantity)
                )
                # Dòng đã nhận đủ thì phiếu không còn là việc đang chạy của mặt hàng này.
                if _f(ln.quantity) - nhan <= 0:
                    continue
                _them(hang, getattr(phieu, "code", None), "pmh", phieu.status,
                      phieu.expected_receipt_date)

        for yc in self.dpr.dang_de_nghi():
            for ln in yc.lines:
                if not ln.hang_loai or not ln.hang_id:
                    continue
                hang = (ln.hang_loai, int(ln.hang_id))
                if hang not in self._objs:
                    continue
                _them(hang, yc.code, "ycmh", yc.status, None)

        for ds in ra.values():
            ds.sort(key=lambda v: (_xep_vet(v), v["ngay_ve"] or date.max, v["ma"]))
        return ra

    # ================== HÀM CHÍNH ==================

    def can_doi(
        self,
        *,
        q: str | None = None,
        chi_thieu: bool = False,
        include_lsx_ids: set[int] | None = None,
    ) -> dict:
        self._nap_don_vi()
        lenh = self._lenh_trong_pham_vi(include_lsx_ids)
        lenh_map = {l.id: l for l in lenh}
        bais = self._bai_trong_pham_vi(set(lenh_map))
        thanh_vien: set[int] = {tv.lsx_id for b in bais for tv in b.thanh_viens}
        # lệnh thành viên → bài chứa nó; dùng để quy "đã cấp" gắn nhầm vào lệnh về đúng dòng bài.
        self._bai_cua_lenh: dict[int, int] = {
            tv.lsx_id: b.id for b in bais for tv in b.thanh_viens
        }

        self._nap_thoi_luong(lenh)
        self._nap_lich(set(lenh_map), {b.id for b in bais})

        tho, bo_qua = self._gom_nhu_cau(lenh, lenh_map, bais, thanh_vien)
        self._nap_mat_hang(tho)
        self._quy_doi_dong(tho)
        # Khổ giấy ĐÃ DÙNG cho từng lệnh/bài ở phần nhu cầu — để phần "đã cấp / đang lĩnh" quy đổi
        # bằng ĐÚNG khổ đó. Hai bên của phép trừ mà đổi tờ→kg bằng hai khổ khác nhau thì con số
        # "còn phải có" sai, và sai theo kiểu không ai nhìn ra.
        self._qc_theo_khoa = {
            (d.get("lsx_id"), d.get("bai_ghep_id")): d.get("qc") for d in tho if d.get("qc")
        }

        da_cap, dang_linh = self._da_cap_dang_linh()
        dang_ve = self._hang_dang_ve()
        vet_mua = self._vet_mua_theo_hang()
        ton = self.lots.on_hand_map(sorted({d["hang"] for d in tho if d["hang"]}))

        nhom = self._chay_con_tro(tho, ton=ton, dang_ve=dang_ve, da_cap=da_cap,
                                  dang_linh=dang_linh, vet_mua=vet_mua)
        return {"items": self._loc(nhom, q=q, chi_thieu=chi_thieu), "bo_qua": bo_qua}

    def vat_tu_hieu_luc(self, bai_ghep_id: int) -> dict:
        """Chiếu bảng cân đối xuống đúng một bài cho tab Vật tư của Bài ghép 2.

        Engine ``can_doi`` vẫn là nguồn duy nhất của quy đổi/số lượng. Phép chiếu chỉ giữ giấy và
        vật tư của chính bài hoặc bước riêng của thành viên, rồi tính lại tổng sau lọc; tuyệt đối
        không bê ``tong_can`` toàn xưởng vào tab bài.
        """
        bg = self.bai_ghep_repo.get(bai_ghep_id)
        if bg is None:
            from .bai_ghep_service import BaiGhepNotFound
            raise BaiGhepNotFound("Không tìm thấy bài ghép")
        member_ids = {tv.lsx_id for tv in bg.thanh_viens}
        member_rows = self.bai_ghep_repo.lsx_by_ids(list(member_ids))
        ma_hieu_luc = {bg.ma, *(l.ma for l in member_rows.values())}
        gang_step_keys = {c.id: c.step_key for c in self._buoc_chung(bg.id)}
        can_doi = self.can_doi(include_lsx_ids=member_ids)
        items: list[dict] = []
        for nhom in can_doi["items"]:
            dong = []
            for row in nhom.get("dong", []):
                la_bai = row.get("bai_ghep_id") == bg.id
                la_lenh = row.get("bai_ghep_id") is None and row.get("lsx_id") in member_ids
                if not (la_bai or la_lenh):
                    continue
                dong.append({
                    "pham_vi": "bai_ghep" if la_bai else "lsx",
                    "lsx_id": row.get("lsx_id"),
                    "bai_ghep_id": row.get("bai_ghep_id"),
                    "buoc_id": row.get("buoc_id"),
                    "gang_step_key": gang_step_keys.get(row.get("buoc_id")) if la_bai else None,
                    "ma": row["ma"],
                    "ten_viec": row.get("ten_viec"),
                    "nhu_cau": round(_f(row.get("nhu_cau")), 4),
                    "nhu_cau_hien_thi": row.get("nhu_cau_hien_thi") or "",
                })
            if not dong:
                continue
            items.append({
                "loai_nhom": nhom["loai_nhom"],
                "hang_loai": nhom["hang_loai"],
                "hang_id": nhom["hang_id"],
                "hang_ma": nhom.get("hang_ma"),
                "hang_ten": nhom.get("hang_ten"),
                "don_vi_goc": nhom.get("don_vi_goc"),
                "tong_can": round(sum(_f(row["nhu_cau"]) for row in dong), 4),
                "dong": dong,
            })
        return {
            "bai_ghep_id": bg.id,
            "items": items,
            "bo_qua": [row for row in can_doi["bo_qua"] if row.get("ma") in ma_hieu_luc],
        }

    # ---- (a) ----------------------------------------------------------------

    def _nap_thoi_luong(self, lenh: list[Lsx]) -> None:
        """Chuẩn bị NGỮ CẢNH để tính thời lượng bước — KHÔNG tính sẵn cho cả bảng.

        Thời lượng chỉ phục vụ MỘT việc: suy mốc tạm ở `_moc_tam`, và `_moc_tam` chỉ chạy cho lệnh
        chưa xếp lịch (`_ngay_can_buoc` trả None) hoặc cho thành viên của bài chưa xếp. Tính sẵn
        cho mọi bước của mọi lệnh là làm thừa đúng phần lệnh ĐÃ xếp — mà đó lại là phần phình lên
        theo thời gian, vì `da_phat_hanh` đang là trạng thái cuối nên lệnh in xong vẫn nằm trong
        phạm vi. Đo 18/08/2026: khoản này chiếm ~30% thời gian `can_doi`.

        Cái đáng nạp lô thì vẫn nạp lô ở đây (máy của mọi bước — tra từng cái là N+1), chỉ hoãn
        phần TÍNH sang `_tong_phut_cua`. Vẫn dùng lại đúng công thức của `lsx_service`.
        """
        from .lsx_service import LsxService

        self._trong_pham_vi = {l.id for l in lenh}
        self._mays = self.repo.may_theo_ids({cd.may_id for l in lenh for cd in l.cong_doans})
        # Một service cho cả bảng: nó cache danh mục đơn vị + bảng cặp, dựng mới mỗi bước là mỗi
        # bước một lượt query.
        self._svc_dur = LsxService(self.db, self.lsx_repo, None, None)
        self._tong_phut: dict[int, float] = {}
        self._qc_cache: dict[int, dict] = {}

    def _qc(self, lsx: Lsx) -> dict:
        """`quy_cach_bien(lsx)` — NHỚ LẠI theo lệnh. Cùng một lệnh bị hỏi hai lần (một lần để tính
        thời lượng, một lần để dựng dòng), mà hàm này gom 16 biến từ JSON + 5 cột dẫn xuất."""
        qc = self._qc_cache.get(lsx.id)
        if qc is None:
            qc = self._qc_cache[lsx.id] = quy_cach_bien(lsx)
        return qc

    def _tong_phut_cua(self, lsx: Lsx) -> float:
        """Tổng thời lượng MỌI bước của một lệnh — tính lúc cần, nhớ lại theo lệnh."""
        from .lsx_service import thoi_luong_buoc

        tong = self._tong_phut.get(lsx.id)
        if tong is not None:
            return tong
        if lsx.id not in self._trong_pham_vi:
            # Lệnh NGOÀI phạm vi vẫn lọt vào đây qua `_dong_bai`: bài được chọn vì có MỘT thành
            # viên trong phạm vi, nhưng `_moc_tam` chạy cho MỌI thành viên. Bản cũ tra bảng
            # `_dur` — bảng chỉ chứa bước của lệnh trong phạm vi — nên những lệnh này cộng ra 0.
            # Giữ nguyên đúng con số đó: đây là lượt tối ưu, không phải lượt đổi cách tính.
            self._tong_phut[lsx.id] = 0.0
            return 0.0
        qc = self._qc(lsx)
        tong = 0.0
        for cd in lsx.cong_doans:
            may = self._mays.get(cd.may_id)
            tong += _f(thoi_luong_buoc(
                cd, may, self._svc_dur.sl_tinh_cua_buoc(cd, may, qc))["tong_phut"])
        self._tong_phut[lsx.id] = tong
        return tong

    def _gom_nhu_cau(self, lenh, lenh_map, bais, thanh_vien) -> tuple[list[dict], list[dict]]:
        tho: list[dict] = []
        bo_qua: list[dict] = []

        # --- giấy của lệnh CHƯA GHÉP ---------------------------------------
        for l in lenh:
            if l.id in thanh_vien:
                continue  # lệnh trong bài ghép KHÔNG sinh dòng giấy riêng — xem `_giay_bai`
            qc = l.quy_cach_json or {}
            # GỠ 2026-08-09 (Đợt 4 · K): nhánh bỏ qua lệnh "khách cấp giấy". Nguồn giấy khách đã
            # gỡ khỏi phiếu tính giá, nên MỌI lệnh đều cần công ty lo giấy và đều phải cân đối.
            # Lệnh CŨ còn cờ đó trong `quy_cach_json` nay cũng hiện dòng — đúng: giấy vẫn phải có
            # mặt ở xưởng, còn ai trả tiền là chuyện của phiếu, không phải của bảng cân đối.
            giay_id = qc.get("giay_id")
            if not giay_id:
                bo_qua.append({"ma": l.ma, "ly_do": "Lệnh chưa chọn giấy trong quy cách."})
                continue
            so_to = int(l.so_to_nguyen or 0)
            if so_to <= 0:
                continue
            buoc = self._buoc_dau_dong_giay(l)
            tho.append(self._dong_lenh(l, ("giay", int(giay_id)),
                                       self._dv_giay(l.cong_doans, buoc), so_to, buoc))

        # --- giấy của BÀI GHÉP: MỘT dòng cho cả bài ------------------------
        # Thành viên + ba số tờ nạp MỘT lần cho mỗi bài rồi dùng lại ở vòng vật tư dưới: cả hai
        # vòng đều cần chúng để dựng ngữ cảnh biến, mà `tinh_so_to` chạy cả chuỗi ngược của từng
        # thành viên — gọi hai lần là trả giá hai lần cho cùng một con số.
        self._bai_ctx: dict[int, tuple[dict, dict, dict]] = {}
        for bg in bais:
            ids = [tv.lsx_id for tv in bg.thanh_viens]
            lsx_map = {i: lenh_map[i] for i in ids if i in lenh_map}
            lsx_map.update(self.bai_ghep_repo.lsx_by_ids([i for i in ids if i not in lsx_map]))
            so_to_dict = self._tinh_so_to(bg, lsx_map)
            self._bai_ctx[bg.id] = (lsx_map, so_to_dict, self._muc_gop(bg, lsx_map))
            if not bg.giay_id:
                bo_qua.append({"ma": bg.ma, "ly_do": "Bài ghép chưa chọn giấy chung."})
                continue
            so_to = int(so_to_dict.get("to_nguyen_can") or 0)
            if so_to <= 0:
                continue
            buoc = sorted(self._buoc_chung(bg.id), key=lambda c: c.thu_tu)
            neo = buoc[0] if buoc else None
            tho.append(
                self._dong_bai(bg, ("giay", int(bg.giay_id)),
                               self._dv_giay(buoc, neo), so_to, neo)
            )

        # --- vật tư khai tay ở bước lệnh ------------------------------------
        buoc_map = {cd.id: (cd, l) for l in lenh for cd in l.cong_doans}
        bi_buoc_chung_de = self.repo.step_keys_bi_buoc_chung_de({bg.id for bg in bais})
        if buoc_map:
            for vt in self.repo.vat_tu_theo_buoc_lenh(list(buoc_map)):
                cd, l = buoc_map[vt.lsx_cong_doan_id]
                if cd.step_key in bi_buoc_chung_de or _f(vt.so_luong) <= 0:
                    continue
                tho.append(
                    self._dong_lenh(l, ("vat_tu", int(vt.vat_tu_id)), vt.don_vi_snapshot,
                                    _f(vt.so_luong), cd)
                )

        # --- vật tư khai tay ở bước CHUNG của bài ---------------------------
        for bg in bais:
            chung = {c.id: c for c in self._buoc_chung(bg.id)}
            if not chung:
                continue
            for vt in self.repo.vat_tu_theo_buoc_chung(list(chung)):
                if _f(vt.so_luong) <= 0:
                    continue
                tho.append(
                    self._dong_bai(bg, ("vat_tu", int(vt.vat_tu_id)), vt.don_vi_snapshot,
                                   _f(vt.so_luong), chung[vt.bai_ghep_cong_doan_id])
                )
        return tho, bo_qua

    def _buoc_chung(self, bai_ghep_id: int) -> list[BaiGhepCongDoan]:
        return self.repo.buoc_chung(bai_ghep_id)

    def _bg(self):
        """Engine bài ghép, dựng một lần cho cả request. `sequence=None`: đường này chỉ ĐỌC."""
        if getattr(self, "_bg_svc", None) is None:
            from ..repositories.audit_repo import AuditLogRepository
            from .bai_ghep_service import BaiGhepService

            self._bg_svc = BaiGhepService(
                self.db, self.bai_ghep_repo, AuditLogRepository(self.db), None
            )
        return self._bg_svc

    def _tinh_so_to(self, bg: BaiGhep, lsx_map: dict) -> dict:
        """Số tờ NGUYÊN của cả bài — gọi thẳng engine bài ghép, KHÔNG tự cộng lại.

        Đây là chỗ dễ ngứa tay viết lại `so_to_tot + hao` cho nhanh. Đừng: `tinh_so_to` còn phải đi
        qua đúng cầu `to_nguyen → to` (số mảnh xả) và cộng hao TRƯỚC khi chia — cộng sau là đòi
        giấy gấp mấy lần. Một engine, một kết quả.
        """
        return self._bg().tinh_so_to(bg, lsx_map)

    def _muc_gop(self, bg: BaiGhep, lsx_map: dict) -> dict:
        """Số màu/kẽm của cả bài — hợp tập mực các thành viên. Engine bài ghép giữ luật, không chép."""
        return self._bg().muc_gop(bg, lsx_map)

    def _dong_lenh(self, l: Lsx, hang, dvt, sl, buoc) -> dict:
        ngay = self._ngay_can_buoc(getattr(buoc, "id", None))
        moc_tam = ngay is None
        suy_duoc = True
        moc_ly_do = ""
        if moc_tam:
            ngay, suy_duoc, moc_ly_do = self._moc_tam(l)
        return {
            "hang": hang, "loai": "vat_tu", "lsx_id": l.id, "bai_ghep_id": None,
            "buoc_id": getattr(buoc, "id", None),
            "ma": l.ma, "ten_viec": getattr(buoc, "ten", None),
            "ngay_can": ngay, "moc_tam": moc_tam, "dvt": dvt, "sl": sl,
            "moc_suy_duoc": suy_duoc,
            "moc_ly_do": moc_ly_do,
            # Cờ GẤP của lệnh — chỉ để BÀY, máy không xếp ưu tiên hộ (chủ chốt 17/08/2026).
            # Người lập kế hoạch nhìn cờ rồi tự quyết nhả chỗ của lệnh nào.
            "is_rush": bool(getattr(l, "is_rush", False)),
            # Quy cách của CHÍNH lệnh này — nguồn ưu tiên để đổi tờ → kg. Lấy qua `quy_cach_bien`
            # (không phải `quy_cach_json` trần) để công thức quy đổi dùng được cả năm số dẫn xuất
            # nằm ở cột: SL đặt · con/tờ · tờ in · tờ nguyên · tờ sau in.
            #
            # `dict(...)` để mỗi dòng giữ bản của riêng nó: `self._qc` nhớ lại theo lệnh, mà một
            # lệnh có thể sinh nhiều dòng — chia chung một dict là mở đường cho sửa dòng này lây
            # sang dòng kia.
            "qc": dict(self._qc(l)),
        }

    def _dong_bai(self, bg: BaiGhep, hang, dvt, sl, buoc) -> dict:
        lsx_map, so_to, muc = getattr(self, "_bai_ctx", {}).get(bg.id, ({}, {}, {}))
        ngay = self._ngay_can_buoc(getattr(buoc, "id", None), cua_bai=True)
        moc_tam = ngay is None
        suy_duoc = True
        moc_ly_do = ""
        if moc_tam:
            # Bài chạy chung một lượt: mốc tạm là mốc SỚM NHẤT trong các lệnh thành viên — cả bài
            # phải có giấy trước khi lệnh gấp nhất của nó cần.
            cap = [self._moc_tam(l) for l in (lsx_map or {}).values()]
            mocs = [m for m, _ok, _ld in cap if m]
            ngay = min(mocs) if mocs else None
            # Chỉ cần MỘT thành viên không suy được là cả mốc của bài đáng ngờ.
            suy_duoc = bool(cap) and all(ok for _m, ok, _ld in cap)
            # Lý do lấy từ thành viên HỎNG, không suy từ `ngay_can` của bài: bài vẫn có ngày (từ
            # thành viên tốt) trong khi cờ hỏng đến từ thành viên khác. Bài không nạp được thành
            # viên nào (`cap` rỗng) cũng là một ca — gọi tên riêng, đừng gộp vào hai ca kia.
            ly_do_tv = [ld for _m, ok, ld in cap if not ok and ld]
            moc_ly_do = ly_do_tv[0] if ly_do_tv else ("" if cap else "khong_co_thanh_vien")
        return {
            "hang": hang, "loai": "vat_tu", "lsx_id": None, "bai_ghep_id": bg.id,
            # Cùng lý do như `_dong_lenh`. Ở đây `buoc_id` là `bai_ghep_cong_doan.id` — KHÁC không
            # gian id với bước lệnh, nhưng cặp `(lsx_id, bai_ghep_id)` trong khoá đã phân biệt sẵn
            # (dòng bài luôn có `lsx_id=None`), nên không cần thêm cờ loại.
            "buoc_id": getattr(buoc, "id", None),
            "ma": bg.ma, "ten_viec": getattr(buoc, "ten", None),
            "ngay_can": ngay, "moc_tam": moc_tam, "dvt": dvt, "sl": sl,
            "moc_suy_duoc": suy_duoc,
            "moc_ly_do": moc_ly_do,
            # Bài GẤP khi có ÍT NHẤT MỘT thành viên gấp — cả bài chạy chung một lượt, không tách được.
            "is_rush": any(bool(getattr(l, "is_rush", False)) for l in (lsx_map or {}).values()),
            # Ngữ cảnh biến của BÀI — cùng bộ 16 biến với lệnh và với phiếu tính giá, xem
            # `bien_cong_thuc`. Trước 11/08/2026 chỗ này dựng tay ba khoá (khổ in + gsm) nên 13/16
            # biến bằng 0 trong im lặng: công thức quy đổi nào chạm `to_dau_vao` hay `so_kem` là
            # cạnh tắt, dòng bài ghép nhận "chưa đánh giá được" mà không ai biết vì sao.
            "qc": quy_cach_bien_bai(bg, thanh_vien=(lsx_map or {}).values(), so_to=so_to, muc=muc),
        }

    # ---- (c) ----------------------------------------------------------------

    def _nap_mat_hang(self, tho: list[dict]) -> None:
        self._objs = self.hang.map_theo_cap([d["hang"] for d in tho if d["hang"]])

    def _quy_doi_dong(self, tho: list[dict]) -> None:
        for d in tho:
            # `tong_lenh=True`: đây là đường NHU CẦU — hỏi "lệnh này cần bao nhiêu", đúng câu mà
            # công thức lượng của mặt hàng trả lời. Hai đường "đã cấp"/"đang về" thì không.
            kq = self._ve_goc(d["hang"], d["dvt"], d["sl"], d.get("qc"), tong_lenh=True)
            if "loi" in kq:
                d["nhu_cau"] = 0.0
                d["nhu_cau_hien_thi"] = f"{_so(d['sl'])} {d['dvt']}"
                d["canh_bao"] = [CB_KHONG_DOI_CHIEU]
                d["ly_do_canh_bao"] = kq["loi"]
            else:
                d["nhu_cau"] = kq["sl"]
                d["nhu_cau_hien_thi"] = kq["hien_thi"]
                d["canh_bao"] = []
                d["ly_do_canh_bao"] = None
            if d["moc_tam"] and not d.get("moc_suy_duoc", True):
                d["canh_bao"].append(CB_DAN_KHONG_SUY_DUOC)
                d["ly_do_canh_bao"] = (d["ly_do_canh_bao"] or "") + (
                    " " if d["ly_do_canh_bao"] else ""
                ) + (
                    "Lệnh còn bước máy chưa gán máy nên chưa suy được thời gian dẫn — ngày cần "
                    "đang bằng đúng hạn sản xuất, tức MUỘN hơn thực tế."
                )

    # ---- (d) ----------------------------------------------------------------

    def _chay_con_tro(self, tho, *, ton, dang_ve, da_cap, dang_linh, vet_mua=None) -> list[dict]:
        hom_nay = _hom_nay()
        # Phần đã cấp CÒN LẠI chưa gán cho dòng nào — bản sao để trừ dần, không đụng dict gốc.
        cap_con = dict(da_cap)
        theo_hang: dict[tuple, list[dict]] = {}
        for d in tho:
            theo_hang.setdefault(d["hang"], []).append(d)

        ra: list[dict] = []
        for hang, ds in theo_hang.items():
            obj = self._objs.get(hang)
            # Dòng chưa có ngày cần (lệnh không hạn SX, chưa xếp) xuống CUỐI: không biết bao giờ
            # cần thì không được chen lên trước lệnh có hạn rõ ràng để ăn tồn.
            ds.sort(key=lambda d: (d["ngay_can"] is None, d["ngay_can"] or date.max, d["ma"]))
            # Số dòng của cùng (mặt hàng, chủ thể) — quyết định có phải CHIA phần đã cấp không.
            so_dong_khoa: dict[tuple, int] = {}
            for d in ds:
                k = (hang, d["lsx_id"], d["bai_ghep_id"])
                so_dong_khoa[k] = so_dong_khoa.get(k, 0) + 1
            ve = list(dang_ve.get(hang, []))
            i = 0
            con_lai = float(ton.get(hang, 0.0))
            con_lai_chi_ton = con_lai
            dong_out: list[dict] = []
            so_do = 0
            so_khong_ro = 0
            so_ve_muon = 0
            tong_can = 0.0
            for d in ds:
                ngay = d["ngay_can"]
                # ⚠️ Bẫy đếm hai lần #2: mỗi đợt hàng về chỉ được cộng MỘT lần, nhờ con trỏ `i`
                # chạy tiến — không có phép trừ "đang mua" nào nữa ở dưới.
                while i < len(ve) and ngay is not None and ve[i][0] <= ngay:
                    con_lai += ve[i][1]
                    i += 1
                khoa_cap = (hang, d["lsx_id"], d["bai_ghep_id"])
                cap_tong = _f(da_cap.get(khoa_cap))
                if so_dong_khoa.get(khoa_cap, 0) <= 1:
                    cap = cap_tong
                else:
                    cap = min(_f(cap_con.get(khoa_cap)), _f(d["nhu_cau"]))
                    cap_con[khoa_cap] = _f(cap_con.get(khoa_cap)) - cap
                linh = dang_linh.get(khoa_cap, 0.0)
                # ⚠️ Bẫy đếm hai lần #1: `cap` chỉ trừ vào NHU CẦU. Tồn (`con_lai`) đã giảm sẵn khi
                # kho ghi sổ — trừ thêm lần nữa là lệnh sau báo thiếu oan.
                #
                # Kẹp sàn 0: cấp DƯ không được biến thành hàng trả lại kho. Bản kế hoạch viết
                # `con_lai -= con_phai_co` trần, nhưng `con_phai_co` âm thì phép trừ đó CỘNG vào
                # tồn một số hàng không tồn tại.
                con_phai_co = max(0.0, _f(d["nhu_cau"]) - cap)
                truoc = con_lai
                con_lai -= con_phai_co
                con_lai_chi_ton -= con_phai_co
                if CB_KHONG_DOI_CHIEU in d["canh_bao"]:
                    # Nhu cầu = 0 vì KHÔNG ĐỔI ĐƯỢC, không phải vì không cần. Rơi vào nhánh `xam`
                    # dưới là dán nhãn "đã cấp đủ" lên một dòng chưa ai tính nổi.
                    mau = MAU_KHONG_RO
                elif con_phai_co <= 0:
                    mau = MAU_XAM
                elif con_lai_chi_ton >= 0:
                    mau = MAU_XANH          # đủ bằng chính tồn đang có
                elif con_lai >= 0:
                    mau = MAU_VANG          # chỉ đủ nhờ hàng đang về
                else:
                    mau = MAU_DO
                # ĐỎ vì THIẾU THẬT, hay đỏ vì HÀNG VỀ MUỘN? Con trỏ `i` chỉ cộng những lô về KỊP
                # (`ngày về ≤ ngày cần`), nên phần đang về chưa dùng nằm ở `ve[i:]` — toàn bộ là lô
                # về SAU ngày cần của dòng này. Gộp nó vào mà phủ nổi ⇒ hàng đã mua rồi, chỉ sai
                # ngày. Đi mua tiếp là mua đúp.
                #
                # Ngày trả về là ngày của lô ĐỦ ĐỂ PHỦ chỗ thiếu, KHÔNG phải lô gần nhất. Lấy lô đầu
                # là chỉ sai đường: `ve[i]=(25/8, 1kg)` + `ve[i+1]=(30/9, 500kg)` mà thiếu 400kg thì
                # câu "dời bước sang sau 25/8" đưa người ta tới đúng ngày vẫn không có giấy.
                #
                # Dòng KHÔNG có ngày cần thì bỏ qua hẳn: "về muộn" là muộn SO VỚI một mốc, mà dòng
                # này chưa có mốc nào. Dán nhãn đó vào là vừa cấm tick mua vừa chặn phát hành với
                # câu "dời bước tiêu thụ" — trong khi việc thật là đi khai hạn sản xuất.
                ngay_du_hang = None
                # Mã phiếu của lô QUYẾT ĐỊNH ngày đủ hàng — cùng lô sinh ra `ngay_du_hang`,
                # không phải lô đầu danh sách. Lô khác cũng góp vào phần phủ, nhưng chỉ lô
                # này mới là chỗ đi hỏi khi muốn hàng sớm hơn.
                phieu_ve = None
                if mau == MAU_DO and ngay is not None:
                    luy_ke = 0.0
                    for ngay_lo, sl_lo, ma_lo in ve[i:]:
                        luy_ke += sl_lo
                        if con_lai + luy_ke >= 0:
                            mau = MAU_VE_MUON
                            ngay_du_hang = ngay_lo
                            phieu_ve = ma_lo
                            break
                # Phần thiếu RIÊNG của dòng này = phần nó không được phủ. KHÔNG lấy `−con_lai`
                # (thiếu luỹ kế): tick hai dòng đỏ rồi gộp một yêu cầu mua thì số luỹ kế cộng
                # chồng lên nhau, đi mua thừa đúng phần đã đếm hai lần.
                thieu = max(0.0, con_phai_co - max(0.0, truoc))
                if mau == MAU_DO:
                    so_do += 1
                elif mau == MAU_KHONG_RO:
                    so_khong_ro += 1
                elif mau == MAU_VE_MUON:
                    so_ve_muon += 1
                tong_can += con_phai_co
                # HẠN CHÓT PHẢI ĐẶT = ngày cần − số ngày kiểm nhập. Trước đây còn trừ "số ngày NCC
                # giao" khai tay ở bảng giá NCC; bỏ 10/08/2026 vì lúc khai danh mục chưa ai biết
                # ông ấy giao mấy ngày — số đoán mà lại đi bật đèn báo trễ. Cần chính xác hơn thì
                # suy từ lịch sử mua (ngày đặt → ngày nhận thật), không bắt khai tay.
                han_dat = None
                dat_muon = False
                if thieu > 0 and ngay is not None:
                    han_dat = ngay - timedelta(days=DEM_KIEM_NHAP_NGAY)
                    dat_muon = han_dat < hom_nay
                dong_out.append({
                    "loai": d["loai"],
                    "lsx_id": d["lsx_id"],
                    "bai_ghep_id": d["bai_ghep_id"],
                    "buoc_id": d.get("buoc_id"),
                    "moc_ly_do": d.get("moc_ly_do") or "",
                    "is_rush": bool(d.get("is_rush")),
                    "ma": d["ma"],
                    "ten_viec": d["ten_viec"],
                    "ngay_can": ngay,
                    "moc_tam": d["moc_tam"],
                    "nhu_cau": round(_f(d["nhu_cau"]), 4),
                    "nhu_cau_hien_thi": d["nhu_cau_hien_thi"],
                    "da_cap": round(cap, 4),
                    "dang_linh": round(linh, 4),
                    "con_phai_co": round(con_phai_co, 4),
                    "con_lai_sau": round(con_lai, 4),
                    "thieu": round(thieu, 4),
                    "trang_thai": mau,
                    "ngay_du_hang": ngay_du_hang,
                    "phieu_ve": phieu_ve,
                    "han_dat": han_dat,
                    "dat_muon": dat_muon,
                    "canh_bao": d["canh_bao"],
                    "ly_do_canh_bao": d["ly_do_canh_bao"],
                })
            ra.append({
                "loai_nhom": "vat_tu",
                "hang_loai": hang[0],
                "hang_id": hang[1],
                "hang_ma": getattr(obj, "ma", None),
                "hang_ten": getattr(obj, "ten", None),
                "don_vi_goc": (getattr(obj, "don_vi_gia", None) or None),
                "ton": round(float(ton.get(hang, 0.0)), 4),
                "tong_can": round(tong_can, 4),
                "so_dong_do": so_do,
                "so_dong_khong_ro": so_khong_ro,
                "so_dong_ve_muon": so_ve_muon,
                # Vết mua treo ở MẶT HÀNG chứ không ở dòng: phiếu mua không biết lệnh nào, nó chỉ
                # biết mua món gì. Dán xuống từng dòng là bịa ra quan hệ phiếu↔lệnh không có thật.
                "phieu_mua": (vet_mua or {}).get(hang, []),
                "dong": dong_out,
            })
        # Nhóm không đánh giá được xếp ngay sau nhóm thiếu: cả hai đều là việc phải lo, chỉ khác
        # là một cái biết thiếu bao nhiêu, một cái chưa biết gì. Nhóm "về muộn" xếp sau cùng trong
        # ba loại phải lo — nó đã mua rồi, việc còn lại là dời lịch chứ không phải chạy đi mua.
        ra.sort(key=lambda g: (-g["so_dong_do"], -g["so_dong_khong_ro"], -g["so_dong_ve_muon"],
                               g["hang_ma"] or ""))
        return ra

    # ---- 1.3 DÒNG CÔNG CỤ (khuôn bế) ---------------------------------------

    # ---- lọc hiển thị -------------------------------------------------------

    @staticmethod
    def _loc(nhom: list[dict], *, q: str | None, chi_thieu: bool) -> list[dict]:
        ra = nhom
        if q:
            k = q.strip().lower()
            ra = [
                g for g in ra
                if k in (g["hang_ma"] or "").lower()
                or k in (g["hang_ten"] or "").lower()
                or any(k in (d["ma"] or "").lower() for d in g["dong"])
            ]
        if chi_thieu:
            # Giữ NGUYÊN mọi dòng của nhóm còn lại: các dòng xám/xanh phía trên chính là thứ đã ăn
            # hết tồn, bỏ chúng đi thì con số "còn lại sau" trong bảng không cộng ra được nữa.
            #
            # Nhóm KHÔNG ĐÁNH GIÁ ĐƯỢC cũng ở lại: "chỉ thứ đang thiếu" nghĩa là "chỉ thứ phải lo",
            # mà thứ máy không tính nổi thì phải lo NHIỀU HƠN chứ không phải ít hơn. Lọc nó đi là
            # giấu đúng cái cần thấy.
            #
            # Nhóm VỀ MUỘN cũng ở lại, cùng lý do: hàng mua rồi nhưng về sau ngày cần thì lệnh VẪN
            # đứng máy — việc phải lo, chỉ khác là việc dời lịch chứ không phải việc mua.
            ra = [g for g in ra
                  if g["so_dong_do"] > 0
                  or g.get("so_dong_khong_ro", 0) > 0
                  or g.get("so_dong_ve_muon", 0) > 0]
        return ra

    # ================== ĐỀ NGHỊ MUA ==================

    def gom_de_nghi(self, chon: list[dict]) -> dict:
        """Gom các dòng được tick thành MỘT yêu cầu mua bộ phận.

        Trả `{lines, needed_date, related_document_code}` để router gọi service thu mua hiện có —
        không đẻ đường tạo yêu cầu mua thứ hai.

        Số lượng = ĐÚNG phần thiếu của từng dòng, KHÔNG làm tròn ram/kiện: thu mua tự làm tròn lúc
        đặt, còn kế hoạch làm tròn thì con số gửi đi không còn kiểm lại được với bảng.
        """
        bang = self.can_doi()
        tra: dict[tuple, dict] = {}
        for g in bang["items"]:
            if g["loai_nhom"] != "vat_tu":
                continue
            for d in g["dong"]:
                tra[_khoa_dong(g["hang_loai"], g["hang_id"], d)] = (g, d)
        lines: list[dict] = []
        ngays: list[date] = []
        mas: list[str] = []
        chi_tiet: list[tuple[str, date, bool]] = []
        # Có dòng nào mang ngày cần không — dùng để phân biệt HAI nguyên nhân khiến `ngays` rỗng.
        co_ngay = False
        # Lệnh/bài có ngày cần KHÔNG TIN ĐƯỢC — `(mã, mã lý do)`. Phải gọi tên ra, kể cả khi yêu
        # cầu vẫn có ngày từ lệnh khác: trộn lệnh rõ với lệnh mờ mà chỉ in ngày của lệnh rõ thì
        # người mua tưởng cả lô cần ngày đó.
        #
        # ⚠️ Lấy LÝ DO THẬT từ `_moc_tam`, KHÔNG suy từ `bool(ngay_can)`. Ba nguồn:
        #   · `chua_gan_may`        — có hạn SX nhưng còn bước máy chưa gán ⇒ mốc rơi về đúng hạn
        #   · `chua_co_han`         — chưa khai hạn sản xuất
        #   · `khong_co_thanh_vien` — bài ghép không nạp được thành viên nào
        #
        # Suy từ `bool(ngay_can)` SAI ở dòng BÀI GHÉP: bài vẫn có ngày (lấy từ thành viên tốt)
        # trong khi cờ hỏng đến từ thành viên KHÁC. In cứng một lý do là chỉ người ta sửa nhầm chỗ
        # — bảo "gán máy đi" trong khi máy đã gán đủ. Vài lần thế là không ai đọc câu ⚠ nữa, mà cả
        # đợt này dựng lên để những câu ⚠ đó đáng tin.
        mo: list[tuple[str, str]] = []
        gop: dict[tuple, dict] = {}
        # Khoá đã tick — CHỐNG TRÙNG. Client gửi hai lần cùng một khoá (bấm đúp, hoặc bảng cũ) thì
        # vòng dưới sẽ cộng `thieu` hai lượt và đi mua gấp đôi. `Set` chặn ngay tại cửa.
        da_xet: set[tuple] = set()
        for c in chon:
            khoa = _khoa_dong(c.get("hang_loai"), int(c.get("hang_id") or 0), c)
            if khoa in da_xet:
                continue
            da_xet.add(khoa)
            found = tra.get(khoa)
            if found is None:
                raise KeHoachVatTuValidationError(
                    "Dòng đã đổi kể từ lúc mở bảng (được cấp hoặc đã có hàng về) — tải lại bảng "
                    "cân đối rồi chọn lại."
                )
            g, d = found
            if d["trang_thai"] == MAU_VE_MUON:
                raise KeHoachVatTuValidationError(
                    f"Dòng {d['ma']} đã có hàng đang về"
                    + (f" theo phiếu {d['phieu_ve']}" if d.get("phieu_ve") else "")
                    + (f" ngày {d['ngay_du_hang']:%d/%m}" if d.get("ngay_du_hang") else "")
                    + " — mua thêm là mua đúp. Dời lịch bước tiêu thụ hoặc hối nhà cung cấp."
                )
            if _f(d["thieu"]) <= 0:
                raise KeHoachVatTuValidationError(
                    f"Dòng {d['ma']} không còn thiếu — không đề nghị mua nữa."
                )
            key = (g["hang_loai"], g["hang_id"])
            cur = gop.setdefault(key, {"g": g, "sl": 0.0})
            cur["sl"] += _f(d["thieu"])
            # ⚠️ Ngày cần chỉ lấy từ dòng SUY ĐƯỢC. Dòng đeo cờ `dan_khong_suy_duoc` mang đúng hạn
            # SX (muộn hơn thực tế) vì lệnh còn bước chưa gán máy — hệ ĐÃ tự nhận là không tính
            # nổi, lấy nó đi đặt hàng là đặt theo một con số mình vừa tuyên bố là sai.
            tin_duoc = CB_DAN_KHONG_SUY_DUOC not in (d.get("canh_bao") or [])
            if d["ngay_can"]:
                co_ngay = True
                if tin_duoc:
                    ngays.append(d["ngay_can"])
            if not tin_duoc and d["ma"] not in [x[0] for x in mo]:
                mo.append((d["ma"], d.get("moc_ly_do") or "chua_gan_may"))
            if d["ma"] not in mas:
                mas.append(d["ma"])
            # Ngày cần của TỪNG lệnh, để người mua biết trong lô có lệnh nào thật sự gấp — yêu cầu
            # chỉ mang MỘT ngày (sớm nhất), nhìn nó không đoán ra được các mốc còn lại.
            #
            # CHỈ liệt kê dòng TIN ĐƯỢC: kèm ngày của dòng vừa bị loại khỏi `needed_date` thì ghi
            # chú tự cãi nhau — vừa bảo "chưa suy được ngày" vừa đưa ra một ngày cụ thể.
            if d["ngay_can"] and tin_duoc and d["ma"] not in [x[0] for x in chi_tiet]:
                chi_tiet.append((d["ma"], d["ngay_can"], bool(d.get("is_rush"))))
        if not gop:
            raise KeHoachVatTuValidationError("Chưa chọn dòng nào.")
        for (loai, hid), cur in gop.items():
            g = cur["g"]
            lines.append({
                "hang_loai": loai,
                "hang_id": hid,
                "item_name": g["hang_ten"],
                "unit": g["don_vi_goc"] or "",
                "quantity": round(cur["sl"], 3),
            })
        hom_nay = _hom_nay()
        # Ngày cần SỚM NHẤT trong các dòng gộp: gộp rồi thì cả yêu cầu phải kịp cho lệnh gấp nhất.
        # Kẹp sàn HÔM NAY vì ngày cần có thể đã qua (lệnh đang trễ) — thu mua không nhận ngày quá
        # khứ, mà chặn ở đó thì đúng lúc cháy nhất lại không lập nổi yêu cầu mua.
        can = min(ngays) if ngays else hom_nay
        # `ngays` rỗng có HAI đường, và chúng cần hai câu khác nhau — chẩn đoán sai thì thu mua đi
        # sửa nhầm chỗ:
        #   · có ngày cần nhưng MỌI dòng đeo cờ "chưa suy được" ⇒ lệnh còn bước chưa gán máy
        #   · không dòng nào có ngày cần        ⇒ lệnh chưa khai hạn sản xuất
        # `ngays` rỗng ⇒ lấy lý do THẬT của dòng mờ đầu tiên; không còn suy từ `co_ngay`. Giữ
        # `co_ngay` làm đường lùi cho dòng cũ chưa mang `moc_ly_do`.
        ly_do_ngay = "" if ngays else (
            (mo[0][1] if mo else "") or ("chua_gan_may" if co_ngay else "chua_co_han")
        )
        return {
            "lines": lines,
            "needed_date": max(can, hom_nay),
            "related_document_code": ", ".join(mas[:5]),
            "ghi_chu_ngay": self._ghi_chu_ngay(chi_tiet, ly_do_ngay, mo),
        }

    @staticmethod
    def _ghi_chu_ngay(chi_tiet: list[tuple[str, date, bool]], ly_do_ngay: str,
                      mo: list[tuple[str, str]] | None = None) -> str:
        """Câu mô tả NGÀY CẦN của từng lệnh, ghép vào nội dung yêu cầu mua.

        Yêu cầu chỉ mang MỘT ngày (sớm nhất trong các dòng gộp), nên người mua nhìn nó không biết
        trong lô còn lệnh nào cần muộn hơn hay lệnh nào đang gấp. Thiếu thông tin đó thì họ dễ hối
        cả đơn cho kịp mốc sớm nhất, hoặc chia đơn nhầm chỗ.
        """
        phan: list[str] = []
        if ly_do_ngay:
            phan.append(
                f"⚠ Ngày cần chưa suy được ({_LY_DO_MOC.get(ly_do_ngay, ly_do_ngay)}) — "
                "thu mua xác nhận lại trước khi đặt."
            )
        if chi_tiet:
            phan.append(" · ".join(
                f"{ma} cần {ngay:%d/%m}{' (GẤP)' if gap else ''}"
                for ma, ngay, gap in sorted(chi_tiet, key=lambda x: x[1])[:8]
            ))
        # Gọi TÊN lệnh có ngày không tin được, kể cả khi yêu cầu vẫn có ngày từ lệnh khác. Không nói
        # thì người mua đọc "LSX-A, LSX-B · cần 21/08" rồi tưởng cả hai cùng cần 21/08.
        #
        # Hai nhóm, hai lý do — cùng bộ chữ với `ly_do_ngay` ở trên để người đọc không phải học hai
        # cách diễn đạt cho cùng một chuyện.
        if mo and ly_do_ngay == "":
            for ma_ly_do, ly_do in _LY_DO_MOC.items():
                nhom = [ma for ma, ld in mo if ld == ma_ly_do]
                if not nhom:
                    continue
                # Cắt bao nhiêu thì NÓI ra bấy nhiêu: câu này tồn tại để chống im lặng, cắt im lặng
                # ngay trong nó là tự phản.
                them = f" và {len(nhom) - 5} lệnh nữa" if len(nhom) > 5 else ""
                phan.append(
                    f"⚠ Chưa suy được ngày cần cho {', '.join(nhom[:5])}{them} ({ly_do}) — "
                    "ngày trên yêu cầu chỉ đúng cho các lệnh còn lại."
                )
        return " ".join(phan)
