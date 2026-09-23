"""Kế hoạch vật tư — bảng CÂN ĐỐI: *cần bao nhiêu · có bao nhiêu · thiếu bao nhiêu · bao giờ phải đặt*.

Hệ đã tính ngược ra nhu cầu từng bước (lệnh hộp 10.000 cái → 2.961 tờ nguyên), kho đã có sổ lô và
tồn theo mặt hàng gốc, thu mua đã có yêu cầu mua + ngày về dự kiến — nhưng ba khối đó không nhìn
thấy nhau. File này là chỗ chúng gặp nhau, và **chỉ đọc**: không khoá lô, không giữ chỗ vật lý,
không lĩnh hộ ai. "Giữ chỗ" ở đây chỉ là THỨ TỰ TRONG BẢNG theo hạn sản xuất — lệnh nào phải xong
trước thì được tính trước, lệnh sau nhìn phần còn lại.

Bốn giai đoạn của `can_doi()`:
  (a) gom dòng nhu cầu (giấy của lệnh chưa ghép · giấy của bài ghép · vật tư khai tay · khuôn bế),
  (b) đọc NGÀY CẦN của từng dòng từ yêu cầu mua hàng đã lập cho lệnh đó — KHÔNG suy,
  (c) quy mọi thứ về ĐƠN VỊ GỐC của mặt hàng (kho đếm theo đơn vị đó),
  (d) chạy con trỏ tồn theo hạn sản xuất cho từng mặt hàng.

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

import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bai_ghep import BaiGhep
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan
from ..models.customer import Customer
from ..models.order import Order
from ..models.don_vi_do import TRAM_TO
from ..services.dong_giay import ban_do_tram, don_vi_chuoi, ma_cua_tram
from ..models.lsx import (
    TT_DA_LAP_KE_HOACH,
    TT_DA_PHAT_HANH,
    TT_SAN_SANG,
    Lsx,
)
from ..models.purchase import (
    DPR_IN_PURCHASE,
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    PR_DRAFT,
    PR_PENDING,
)
from ..models.stock_request import REQ_DONE
from ..models.vat_lieu_kho import HANG_GIAY
from ..repositories.ke_hoach_vat_tu_repo import KeHoachVatTuRepository
from ..repositories.purchase_repo import DepartmentPurchaseRequestRepository
from .bien_cong_thuc import quy_cach_bien, quy_cach_bien_bai
from .bien_cong_thuc import MAC_DINH_TANG_LENH, ngu_canh_lenh
from .thanh_phan_engine import safe_eval
from .quy_doi_service import _so, bien_trong, cap_map, doi, don_vi_map
from .stock_request_service import StockRequestService

# Lệnh ở ba trạng thái này là thứ kế hoạch phải lo giấy: đã chốt kỹ thuật, chỉ còn chờ chạy.
# `nhap`/`cho_bo_sung` chưa chốt quy cách nên số tờ còn xê dịch — đưa vào bảng là mua theo số sắp đổi.
TRANG_THAI_TINH = (TT_SAN_SANG, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH)

MAU_XAM, MAU_XANH, MAU_VANG, MAU_DO = "xam", "xanh", "vang", "do"
# Trạng thái THỨ NĂM: dòng KHÔNG ĐÁNH GIÁ ĐƯỢC (thiếu đường quy đổi đơn vị).
#
# Vì sao không gộp vào `xam`: xám nghĩa là "đã cấp đủ, hết việc phải lo" — mạnh hơn cả "đủ". Dòng
# hệ thống không tính nổi mà đeo nhãn đó là nói ngược sự thật, và tệ hơn: nó rơi khỏi bộ lọc "chỉ
# mặt hàng đang thiếu", tức biến mất đúng lúc người ta đi tìm việc phải lo.
MAU_KHONG_RO = "khong_ro"
# Cờ cảnh báo trên dòng — tập MỞ, phía FE chỉ cần biết dòng có cảnh báo thì tô nhạt + hiện tooltip.
CB_KHONG_DOI_CHIEU = "khong_doi_chieu_duoc"

# NGÀY CẦN KHÔNG SUY (18/09/2026, chủ chốt): trước đây hệ tự tính "giờ bắt đầu bước − 2 tiếng",
# lệnh chưa xếp thì "hạn SX − thời gian dẫn", rồi còn chặn đề nghị mua / không cộng hàng về sau
# ngày đó. Nay ngày cần CHỈ là "Ngày cần hàng" người lập gõ trên yêu cầu mua hàng, đọc ngược qua
# `yeu_cau_mua_nguon_lenh`; lệnh không phải mua thì để trống, và không có gì bị chặn theo ngày.


class KeHoachVatTuError(Exception):
    pass


class KeHoachVatTuValidationError(KeHoachVatTuError):
    pass


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# HAI TRẠNG THÁI CHIP CHỈ CÓ Ở CẤP MÓN — không phải trạng thái của phiếu nào cả.
#
# Chủ chốt 24/08/2026 (*"đọc thì phải hiển thị lên ui chứ"*): món đã đi qua thu mua rồi mà hỏng
# giữa chừng thì KHÔNG được nói "mới đề nghị". `YCMH-260820-JI8X` là ca thật: thu mua đã lập
# `PMH-260820-YC1U` cho đúng món Couché 300 đó, phiếu bị TỪ CHỐI, việc đang đứng chờ người lập lại
# — mà chip vẫn báo "mới đề nghị", người lập kế hoạch tưởng chỉ cần chờ.
#
# Phải đặt tên riêng chứ không mượn trạng thái PMH: chip mang mã YCMH, dán chữ "rejected" lên đó
# là người đọc tưởng CHÍNH YÊU CẦU bị từ chối.
VET_DANG_LAP_DON = "dang_lap_don"
VET_DON_BI_TU_CHOI = "don_bi_tu_choi"


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
    # `don_bi_tu_choi` xếp CUỐI đúng theo luật chắc→lỏng: nó là món đang kẹt, chưa ai hứa gì.
    # Đẩy nó lên đầu thì một mặt hàng vừa có hàng về 30/8 vừa có món kẹt sẽ khoe cái kẹt trước —
    # tin xấu che mất tin tốt, đúng cái docstring trên vừa cấm.
    return {
        DPR_IN_PURCHASE: 3,
        VET_DANG_LAP_DON: 3,
        DPR_PENDING_APPROVAL: 4,
        VET_DON_BI_TU_CHOI: 6,
    }.get(v.get("trang_thai"), 5)


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
        `_dv_giay` có thể được gọi trước nó. Bảng cân đối duyệt cả trăm lệnh nên hỏi lại danh mục
        theo từng lệnh là đúng bài N+1.
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
        # ⚠️ Và CHỈ cho GIẤY (20/08/2026), nay hẹp thêm: chỉ giấy của BÀI GHÉP (08/09/2026) — nơi
        # gọi bật cờ theo từng dòng, xem `_quy_doi_dong`. Ranh giới thật không phải "giấy hay vật
        # tư" mà là "dòng mang số gì":
        #   * BÀI GHÉP: dòng mang SỐ TỜ của cả bài, phải có công thức mới ra kg ⇒ chạy ở đây là đúng.
        #   * DÒNG CỦA BƯỚC (vật tư lẫn giấy): lấy thẳng `lsx_cong_doan_vat_tu.so_luong` — số đó
        #     CHÍNH LÀ kết quả công thức, `LsxService._luong_vat_tu` đã tính lúc lưu công đoạn bằng
        #     ngữ cảnh ĐẦY ĐỦ có cả `sl_vao`/`sl_ra` của bước. Chạy lại ở đây là tính lần hai bằng
        #     ngữ cảnh NGHÈO hơn (`_quy_cach_cua` trả None cho mọi thứ không phải giấy ⇒ 16 biến
        #     đều 0), nên mọi món có công thức đều rơi vào "Chưa biết <biến>" và nhu cầu về 0 —
        #     đúng hỏng đã thấy ở LSX26-0020: BOM ghi 10 bản kẽm · 100 kg mực · 91.000 m² màng,
        #     kế hoạch vật tư hiện "0 · Chưa rõ ĐVT" cho cả năm dòng.
        ct = (getattr(obj, "cong_thuc_luong", None) or "").strip() if (
            tong_lenh and hang[0] == HANG_GIAY) else ""
        if ct:
            # Đường này chạy ở TẦNG LỆNH cho GIẤY — không đứng trong bước nào, nên số lượt
            # lấy mặc định 1 chứ không hỏi được ai.
            ctx = {**ngu_canh_lenh(qc), **MAC_DINH_TANG_LENH}
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

    def _lenh_trong_pham_vi(
        self, include_lsx_ids: set[int] | None = None, *, chi_lsx_ids: set[int] | None = None
    ) -> list[Lsx]:
        # `chi_lsx_ids` = hỏi ĐÍCH DANH, không kèm `trang_thai IN TRANG_THAI_TINH`: người gọi đã
        # tự chọn tập lệnh (đúng trang đang hiện), lọc thêm trạng thái ở đây chỉ làm đèn của lệnh
        # nháp im lặng biến mất. Xem docstring `can_doi` cho ranh giới hai phạm vi.
        if chi_lsx_ids:
            return self.lsx_repo.theo_ids(set(chi_lsx_ids))
        include = {int(i) for i in (include_lsx_ids or set()) if i}
        return self.lsx_repo.cho_mrp(trang_thai=TRANG_THAI_TINH, include_ids=include)

    def _bai_trong_pham_vi(self, lenh_ids: set[int], *, hep: bool = False) -> list[BaiGhep]:
        """Bài ghép có ÍT NHẤT MỘT lệnh thành viên đang trong phạm vi.

        Không lọc theo trạng thái của chính bài: bài còn `nhap` mà thành viên đã `san_sang` thì
        giấy vẫn phải mua — trạng thái bài nói về việc bình bài đã xong chưa, không nói về giấy.

        `hep=True` đẩy phép lọc đó xuống SQL thay vì kéo mọi bài của xưởng về rồi lọc bằng Python.
        Kết quả y hệt; chỉ đường toàn xưởng mới cần bản kéo-hết, vì ở đó `lenh_ids` là cả xưởng.
        """
        if hep:
            return self.bai_ghep_repo.chua_lsx(lenh_ids)
        return [
            b
            for b in self.bai_ghep_repo.list()
            if any(tv.lsx_id in lenh_ids for tv in b.thanh_viens)
        ]

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

    # ================== (b) NGÀY CẦN ==================

    def _nap_ngay_can(self, lsx_ids: set[int], bai_ids: set[int]) -> None:
        """Ngày cần hàng trên các YCMH còn hiệu lực đã lập cho những lệnh/bài này — MỘT câu."""
        self._ngay_can_map = (
            self.dpr.ngay_can_theo_chu_the(lsx_ids, bai_ids) if (lsx_ids or bai_ids) else {}
        )

    def _ngay_can_cua(self, hang: tuple, lsx_id: int | None, bai_ghep_id: int | None) -> date | None:
        return getattr(self, "_ngay_can_map", {}).get((hang[0], int(hang[1]), lsx_id, bai_ghep_id))

    # ================== (b') KHÁCH HÀNG CỦA LỆNH ==================

    def _nap_khach(self, lenh: list[Lsx]) -> None:
        """`lsx_id → tên khách`, MỘT câu cho cả bảng.

        Người lập kế hoạch nhìn bảng này để quyết mua gì trước; "lệnh của ai" là một nửa câu trả
        lời, mà lệnh chỉ giữ `order_id` nên tên khách phải đi qua đơn hàng. Tra từng lệnh một là
        đúng cái N+1 mà `LsxService._customer_names` đã dựng hàm gộp để tránh — bảng cân đối duyệt
        cả xưởng nên còn tệ hơn.

        `isouter`: đơn chưa gắn khách (`customer_id` NULL) vẫn phải giữ dòng lệnh trên bảng, chỉ
        là ô khách để trống.
        """
        self._khach_map: dict[int, str | None] = {}
        order_ids = {int(l.order_id) for l in lenh if getattr(l, "order_id", None)}
        if not order_ids:
            return
        rows = self.db.execute(
            select(Order.id, Customer.name)
            .select_from(Order)
            .join(Customer, Customer.id == Order.customer_id, isouter=True)
            .where(Order.id.in_(order_ids))
        ).all()
        theo_don = {oid: ten for oid, ten in rows}
        self._khach_map = {
            l.id: theo_don.get(int(l.order_id)) for l in lenh if getattr(l, "order_id", None)
        }

    def _khach_cua(self, lsx_id: int | None) -> str | None:
        return getattr(self, "_khach_map", {}).get(lsx_id) if lsx_id else None

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
                (0.0 if trang_thai == REQ_DONE else StockRequestService.con_lai(ln),
                 dang_linh),
            ):
                if nguon <= 0:
                    continue
                kq = self._ve_goc(hang, ln.dvt, nguon,
                                  self._qc_theo_khoa.get((lsx_id, bg_id)))
                if "sl" in kq:
                    bang[khoa] = bang.get(khoa, 0.0) + kq["sl"]
        return da_cap, dang_linh

    def nap_nen_quy_doi(self, hangs: list[tuple]) -> None:
        """Nạp ĐỦ nền để `_ve_goc()` chạy được NGOÀI `can_doi()`.

        `_objs` (object mặt hàng) và `_dvs`/`_cap` (danh mục đơn vị + đồ thị cặp quy đổi) chỉ được
        nạp bên trong `can_doi()`. Đường ĐỐI SOÁT giữ chỗ (`GiuChoService.doi_soat_dang_ve`, chạy
        khi PMH huỷ/đóng/đổi đợt giao) chỉ hỏi MỘT mặt hàng: dựng cả bảng cân đối ở đó là chạy
        nguyên engine cho TOÀN kế hoạch chỉ để đọc một con số. Nạp đúng phần cần, không gọi
        `can_doi()`.

        Bỏ hàm này thì `_hang_dang_ve()` nổ `AttributeError: '_objs'` — `deps.py` bơm một
        `KeHoachVatTuService` VỪA DỰNG vào `PurchaseService`, nó chưa từng dựng bảng.
        """
        if not hasattr(self, "_dvs"):
            self._nap_don_vi()
        if not hasattr(self, "_objs"):
            self._objs = {}
        thieu = [h for h in hangs if h not in self._objs]
        if thieu:
            self._objs.update(self.hang.map_theo_cap(thieu))

    def _hang_dang_ve(self) -> dict[tuple, list[tuple[date, float, str | None, int]]]:
        """`{hang: [(ngày về, số còn về, mã phiếu mua, id dòng phiếu)]}` đã sắp theo ngày — đơn vị GỐC.

        Mã phiếu + id dòng phiếu đi kèm cho giữ chỗ (`GiuChoService`) bám đúng dòng phiếu mua.

        "Đang mua" và "hàng đang về" là MỘT thứ; đây là chỗ DUY NHẤT nó được cộng vào. Dòng phiếu
        KHÔNG gắn mặt hàng gốc thì bỏ qua hẳn — ghép ngược bằng tên hàng là đoán, mà đoán trúng
        nhầm lô giấy khác thì bảng báo đủ trong khi thật ra thiếu.

        `expected_receipt_date` trống ⇒ KHÔNG cộng: hàng không có ngày về thì không hứa được với
        lệnh nào cả.
        """
        from .purchase_service import da_giao_theo_dong

        ra: dict[tuple, list[tuple[date, float, str | None, int]]] = {}
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
                        (ngay_ve, kq["sl"], getattr(phieu, "code", None), int(ln.id)))
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

        * PMH duyệt rồi, có ngày về  → cộng vào hàng đang về, dòng thành vàng (đã nói được).
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

        phieu_song = [*self.purchases.dong_dang_ve(), *self.purchases.dong_cho_duyet()]
        # DÒNG YÊU CẦU ĐÃ CÓ ĐƠN MUA ĐANG CHẠY. Dựng từ chính danh sách vừa nạp (không thêm query)
        # để đoạn YCMH bên dưới biết món nào Thu mua đã cầm — TRẢ LỜI THEO TỪNG MÓN, không theo
        # trạng thái của cả yêu cầu (chủ chốt 24/08/2026: *"phải đi vào trong trạng thái của từng
        # sản phẩm trong yêu cầu ấy chứ không phải yêu cầu"*). Trước đây yêu cầu 3 món mà Thu mua
        # mới lập đơn cho 1 món thì CẢ BA món đều đeo chip "đang mua" — hai món kia thực ra vẫn
        # đang nằm chờ, không ai lo.
        # Cố ý KHÔNG loại dòng đã nhận đủ ở đây: nhận đủ rồi thì món đó cũng hết "đang chờ Thu mua".
        dong_yc_da_co_don: set[int] = {
            int(ln.department_request_line_id)
            for phieu in phieu_song
            for ln in phieu.lines
            if getattr(ln, "department_request_line_id", None) is not None
        }
        # DÒNG YÊU CẦU ĐÃ ĐI QUA THU MUA NHƯNG CHƯA THÀNH LỜI HỨA NÀO (24/08/2026).
        # Phiếu nháp và phiếu bị từ chối không cộng một ký hàng nào, nên chúng KHÔNG nằm trong
        # `phieu_song` ở trên — và trước hôm nay chúng cũng không nói được câu nào, món rơi thẳng
        # về nhãn "mới đề nghị" như thể chưa ai đụng vào. Đọc thêm đúng một câu truy vấn để chip
        # nói được món đang kẹt ở đâu.
        #
        # NHÁP THẮNG BỊ-TỪ-CHỐI: thu mua bị trả phiếu rồi mở phiếu mới gõ lại thì việc đang chạy
        # tiếp, không còn kẹt. Ngược lại thì chip báo kẹt trong khi người ta đang làm.
        dong_yc_kep: dict[int, str] = {}
        for phieu in self.purchases.dong_nhap_hoac_bi_tu_choi():
            nhan_kep = (
                VET_DANG_LAP_DON if phieu.status == PR_DRAFT else VET_DON_BI_TU_CHOI
            )
            for ln in phieu.lines:
                src = getattr(ln, "department_request_line_id", None)
                if src is None:
                    continue
                if dong_yc_kep.get(int(src)) == VET_DANG_LAP_DON:
                    continue
                dong_yc_kep[int(src)] = nhan_kep

        for phieu in phieu_song:
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
                # Món đã bị bộ phận BỎ khỏi yêu cầu (mg 0233) — không còn ai chờ nó nữa.
                if getattr(ln, "cancelled_at", None) is not None:
                    continue
                # Món đã có đơn mua đang chạy → chip PMH ở trên đã nói rồi, nói thêm chip YCMH chỉ
                # làm người đọc tưởng có hai việc song song.
                if ln.id in dong_yc_da_co_don:
                    continue
                hang = (ln.hang_loai, int(ln.hang_id))
                if hang not in self._objs:
                    continue
                # Trạng thái của CHÍNH MÓN NÀY, không phải của yêu cầu cha: tới được đây nghĩa
                # là chưa đơn mua sống nào cầm nó. Còn nó đang *đứng ở đâu* thì hỏi tiếp đơn cũ —
                # chưa đơn nào là "mới đề nghị", có đơn nháp là thu mua đang gõ, có đơn bị từ chối
                # là việc đang kẹt chờ lập lại. Ba tình huống, ba câu khác nhau.
                _them(hang, yc.code, "ycmh", dong_yc_kep.get(ln.id, DPR_OPEN), None)

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
        chi_lsx_ids: set[int] | None = None,
    ) -> dict:
        """Bảng cân đối vật tư. `chi_lsx_ids` giới hạn phạm vi về ĐÚNG những lệnh đó.

        Hai phạm vi, đừng lẫn. Mặc định (không truyền gì) là phạm vi TOÀN XƯỞNG: mọi lệnh trong
        `TRANG_THAI_TINH`. Màn Kế hoạch vật tư phải dùng bản này — nó vẽ cả bảng cân đối, cắt bớt
        là âm thầm tính THIẾU nhu cầu và mua hụt giấy.

        `chi_lsx_ids` là phạm vi HẸP cho đường chỉ cần nhu cầu của vài lệnh đã biết tên: hàng ba
        đèn của màn Kế hoạch SX hỏi đúng 50 lệnh đang hiện, rồi chỉ đọc ra `nhu_cau` của từng lệnh
        (`GiuChoService.trang_thai` → `_nhu_cau_theo_chu_the`). Nhu cầu của một lệnh không phụ
        thuộc lệnh khác, nên hai phạm vi cho CÙNG một con số — chỉ khác cái giá. Không có nó thì
        mở một trang 50 lệnh là kéo cả xưởng về RAM: đo 18/09/2026 thấy hỏi cùng 6 lệnh mà phải
        nạp 12 → 48 dòng khi số lệnh trong xưởng gấp bốn, tức tuyến tính theo lịch sử nhập liệu.

        `include_lsx_ids` KHÁC hẳn: nó THÊM lệnh vào phạm vi toàn xưởng (lệnh đang mở trên màn dù
        trạng thái nào). Truyền cả hai thì `chi_lsx_ids` thắng và `include_lsx_ids` nhập vào nó.
        """
        self._nap_don_vi()
        hep = {int(i) for i in (chi_lsx_ids or set()) if i}
        if hep:
            hep |= {int(i) for i in (include_lsx_ids or set()) if i}
        lenh = self._lenh_trong_pham_vi(include_lsx_ids, chi_lsx_ids=hep or None)
        lenh_map = {l.id: l for l in lenh}
        bais = self._bai_trong_pham_vi(set(lenh_map), hep=bool(hep))
        # lệnh thành viên → bài chứa nó; dùng để quy "đã cấp" gắn nhầm vào lệnh về đúng dòng bài.
        self._bai_cua_lenh: dict[int, int] = {
            tv.lsx_id: b.id for b in bais for tv in b.thanh_viens
        }

        self._qc_cache: dict[int, dict] = {}
        self._nap_ngay_can(set(lenh_map), {b.id for b in bais})
        self._nap_khach(lenh)

        tho = self._gom_nhu_cau(lenh, lenh_map, bais)
        self._nap_mat_hang(tho)
        self._quy_doi_dong(tho)
        # Khổ giấy ĐÃ DÙNG cho từng lệnh/bài ở phần nhu cầu — để phần "đã cấp / đang lĩnh" quy đổi
        # bằng ĐÚNG khổ đó. Hai bên của phép trừ mà đổi tờ→kg bằng hai khổ khác nhau thì con số
        # "còn phải có" sai, và sai theo kiểu không ai nhìn ra.
        self._qc_theo_khoa = {
            (d.get("lsx_id"), d.get("bai_ghep_id")): d.get("qc") for d in tho if d.get("qc")
        }

        # Dựng `_qc_theo_khoa` TRƯỚC khi rụng: phần "đã cấp" của một chủ thể vừa rụng hết dòng vẫn
        # phải quy đổi được về đơn vị gốc, không thì nó rơi ra khỏi phép trừ ngay dưới.
        tho, da_tieu = self._bo_buoc_da_xong(tho)

        da_cap, dang_linh = self._da_cap_dang_linh()
        # Phần đã cấp cho bước VỪA RỤNG coi như đã tiêu vào chính bước đó. Không trừ thì số ấy trôi
        # sang dòng còn lại của cùng lệnh + cùng mặt hàng (`da_cap` không có chiều bước — xem
        # `_da_cap_dang_linh`) và dán "đã cấp đủ" lên một bước chưa hề nhận hàng.
        for khoa, sl in da_tieu.items():
            if khoa in da_cap:
                da_cap[khoa] = max(0.0, da_cap[khoa] - sl)
        dang_ve = self._hang_dang_ve()
        vet_mua = self._vet_mua_theo_hang()
        ton = self.lots.on_hand_map(sorted({d["hang"] for d in tho if d["hang"]}))

        nhom = self._chay_con_tro(tho, ton=ton, dang_ve=dang_ve, da_cap=da_cap,
                                  dang_linh=dang_linh, vet_mua=vet_mua)
        return {"items": self._loc(nhom, q=q, chi_thieu=chi_thieu)}

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
        return {"bai_ghep_id": bg.id, "items": items}

    def nhu_cau_cua_cong_viec(self, cv) -> list[dict]:
        """Vật tư KẾ HOẠCH của MỘT công việc sản xuất (spec-de-nghi-cap-vat-tu-cong-doan §3).

        Đi qua ĐÚNG `_gom_nhu_cau` mà bảng cân đối đang dùng, rồi LỌC về đúng bước — không viết
        lại MRP. Hai nguồn tính nhu cầu thì sớm muộn lệch, và lệch ở đây là tổ xin sai số vật tư.

        KHÔNG đọc `cv.vat_tu_json`: snapshot ấy dựng lúc phát hành công việc, còn `_gom_nhu_cau`
        đọc dòng vật tư SỐNG của bước — hai nguồn lệch nhau sau mỗi lần sửa lệnh.

        Giấy neo vào ĐÚNG bước người lập kế hoạch khai nó (08/09/2026), nên chỉ công việc của bước
        đó mới thấy dòng giấy — đúng nghiệp vụ: tổ cán màng không đi xin giấy in.
        """
        lsx_id = cv.lsx_id
        bai_id = cv.bai_ghep_id
        if not lsx_id and not bai_id:
            return []

        self._nap_don_vi()
        # Đường này chỉ cần mặt hàng + số, không cần ngày cần.
        self._qc_cache = {}
        self._ngay_can_map = {}
        # Phạm vi HẸP thật: đúng lệnh/bài của công việc này. Đừng quay lại `_lenh_trong_pham_vi`
        # — nó đi qua `cho_mrp`, hàm luôn OR thêm `trang_thai IN TRANG_THAI_TINH`, nên nó kéo về
        # mọi lệnh còn sống của xưởng và biến một lần mở form thành một lần `can_doi()` toàn bảng.
        if bai_id:
            b = self.bai_ghep_repo.get(bai_id)
            bais = [b] if b is not None else []
        elif lsx_id:
            # Lệnh có thể là thành viên một bài ghép: khi đó giấy nằm ở dòng BÀI, không ở dòng
            # lệnh (xem `_dong_bai`). Vẫn phải tìm bài chứa nó, nếu không `bais` rỗng và dòng giấy
            # của bài biến mất khỏi kết quả.
            bais = self._bai_trong_pham_vi({int(lsx_id)})
        else:
            bais = []
        lsx_ids = {int(lsx_id)} if lsx_id else set()
        lsx_ids |= {tv.lsx_id for b in bais for tv in b.thanh_viens}
        lenh = self.lsx_repo.theo_ids(lsx_ids)
        lenh_map = {l.id: l for l in lenh}

        tho = self._gom_nhu_cau(lenh, lenh_map, bais)

        # Neo về ĐÚNG bước: dòng lệnh so `buoc_id` với `lsx_cong_doan_id`, dòng bài so với
        # `bai_ghep_cong_doan_id` (hai không gian id khác nhau — cặp `(lsx_id, bai_ghep_id)` trên
        # dòng đã phân biệt sẵn, xem chú thích `_dong_bai`).
        neo_lsx = cv.lsx_cong_doan_id
        neo_bg = cv.bai_ghep_cong_doan_id
        cua_buoc = [
            d for d in tho
            if (d["bai_ghep_id"] and neo_bg and d["buoc_id"] == neo_bg)
            or (d["lsx_id"] and neo_lsx and d["lsx_id"] == lsx_id and d["buoc_id"] == neo_lsx)
        ]
        if not cua_buoc:
            return []

        self._nap_mat_hang(cua_buoc)
        self._quy_doi_dong(cua_buoc)

        # Gộp trùng SAU khi đã về đơn vị gốc — gộp trước là cộng 100 tờ với 12 kg.
        # `_nap_mat_hang`/`_quy_doi_dong` không đặt khoá `ten_hang`/`dvt_goc`/`sl_goc` lên dòng:
        # tên lấy thẳng từ `self._objs`, đơn vị gốc là `obj.don_vi_gia`, số gốc là `d["nhu_cau"]`
        # (khoá do `_quy_doi_dong` đặt).
        gom: dict[tuple, dict] = {}
        for d in cua_buoc:
            loai, hid = d["hang"]
            k = (loai, int(hid))
            obj = self._objs.get(d["hang"])
            ten = obj.ten if obj is not None else f"#{hid}"
            dvt_goc = getattr(obj, "don_vi_gia", None) if obj is not None else None
            sl_goc = float(d.get("nhu_cau") or 0)
            cu = gom.get(k)
            if cu is None:
                gom[k] = {
                    "hang_loai": loai, "hang_id": int(hid), "ten": ten,
                    "dvt": d["dvt"], "sl": float(d["sl"] or 0),
                    "dvt_goc": dvt_goc or d["dvt"], "sl_goc": sl_goc,
                }
            else:
                cu["sl_goc"] += sl_goc
                # Đơn vị hiển thị chỉ cộng được khi TRÙNG; khác đơn vị thì bày theo đơn vị GỐC,
                # đừng cộng bừa hai thang rồi in ra một con số không có nghĩa.
                if cu["dvt"] == d["dvt"]:
                    cu["sl"] += float(d["sl"] or 0)
                else:
                    cu["dvt"] = cu["dvt_goc"]
                    cu["sl"] = cu["sl_goc"]
        return list(gom.values())

    def ve_don_vi_goc(self, hang_loai: str, hang_id: int, dvt: str, sl: float) -> tuple[float, str]:
        """Quy `sl` từ `dvt` về đơn vị GỐC của mặt hàng `(hang_loai, hang_id)`.

        Wrapper CÔNG KHAI mỏng quanh `_ve_goc` — Task 3 (đề nghị cấp vật tư) dùng nó để BE tự quy
        đổi lại số client gửi lên, không tin số của client. Tự nạp `self._objs` cho mặt hàng này
        nếu chưa có (gọi thẳng từ ngoài `can_doi()`/`nhu_cau_cua_cong_viec` là bình thường — vd
        dòng khai thêm ngoài kế hoạch).

        Ném `KeHoachVatTuError` khi không quy đổi được, KHÔNG trả 0 im lặng: Task 3 dùng con số
        này để so lệch kế hoạch, trả 0 âm thầm là một dòng "lệch" giả.
        """
        hang = (hang_loai, int(hang_id))
        self.nap_nen_quy_doi([hang])
        kq = self._ve_goc(hang, dvt, float(sl))
        if "loi" in kq:
            raise KeHoachVatTuError(kq["loi"])
        return float(kq["sl"]), kq["don_vi_goc_ten"]

    # ---- (a) ----------------------------------------------------------------

    def _qc(self, lsx: Lsx) -> dict:
        """`quy_cach_bien(lsx)` — NHỚ LẠI theo lệnh. Một lệnh sinh nhiều dòng (mỗi bước một dòng),
        mà hàm này gom 16 biến từ JSON + 5 cột dẫn xuất."""
        qc = self._qc_cache.get(lsx.id)
        if qc is None:
            qc = self._qc_cache[lsx.id] = quy_cach_bien(lsx)
        return qc

    def _gom_nhu_cau(self, lenh, lenh_map, bais) -> list[dict]:
        tho: list[dict] = []

        # --- giấy của LỆNH: ĐÃ GỠ 08/09/2026 -------------------------------
        # Trước đây lệnh tự đẻ một dòng giấy từ `quy_cach_json.giay_id` + `so_to_nguyen`, rồi treo
        # ngày cần lên "bước đầu tiên chạm tờ" (`_buoc_dau_dong_giay`). Hai chỗ đoán, hai chỗ sai:
        # người lập kế hoạch không chọn được loại giấy nào khác, không đổi được bước tiêu thụ, và
        # một lệnh chỉ ôm được ĐÚNG MỘT loại giấy — trong khi hộp carton cần giấy mặt + giấy sóng
        # + giấy đáy, mỗi loại vào một bước khác nhau.
        #
        # Nay giấy là một DÒNG VẬT TƯ của bước (`lsx_cong_doan_vat_tu` với `hang_loai='giay'`), đi
        # chung vòng "vật tư khai tay ở bước lệnh" ngay dưới; ngày cần lấy theo CHÍNH bước mang nó.
        # BÀI GHÉP giữ nguyên `bai_ghep.giay_id`: giấy in của một lượt chạy chung thuộc về BÀI.

        # --- giấy của BÀI GHÉP: MỘT dòng cho cả bài ------------------------
        # Thành viên + ba số tờ nạp MỘT lần cho mỗi bài rồi dùng lại ở vòng vật tư dưới: cả hai
        # vòng đều cần chúng để dựng ngữ cảnh biến, mà `tinh_so_to` chạy cả chuỗi ngược của từng
        # thành viên — gọi hai lần là trả giá hai lần cho cùng một con số.
        #
        # Mọi thứ engine hỏi TỪNG BÀI (bước chung, bản đồ gộp, "lệnh thuộc bài nào", thành viên
        # nằm ngoài phạm vi) nạp LÔ một lần ở đây — hỏi trong vòng lặp là mỗi bài đội ~15 câu.
        self._bai_ctx: dict[int, tuple[dict, dict, dict]] = {}
        bai_ids = [bg.id for bg in bais]
        tv_ids = [tv.lsx_id for bg in bais for tv in bg.thanh_viens]
        ngoai = self.bai_ghep_repo.lsx_by_ids(sorted({i for i in tv_ids if i not in lenh_map}))
        self._chung_nap = self.bai_ghep_repo.buoc_chung_theo_bai(bai_ids)
        if bais:
            self._bg().nap_truoc(bai_ids, tv_ids, buoc_chung=self._chung_nap)
        for bg in bais:
            ids = [tv.lsx_id for tv in bg.thanh_viens]
            lsx_map = {i: lenh_map[i] if i in lenh_map else ngoai[i]
                       for i in ids if i in lenh_map or i in ngoai}
            so_to_dict = self._tinh_so_to(bg, lsx_map)
            self._bai_ctx[bg.id] = (lsx_map, so_to_dict, self._muc_gop(bg, lsx_map))
            if not bg.giay_id:
                continue
            so_to = int(so_to_dict.get("to_nguyen_can") or 0)
            if so_to <= 0:
                continue
            buoc = sorted(self._buoc_chung(bg.id), key=lambda c: c.thu_tu)
            neo = buoc[0] if buoc else None
            tho.append(
                self._dong_bai(bg, ("giay", int(bg.giay_id)),
                               self._dv_giay(buoc, neo), so_to, neo, ct_mat_hang=True)
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
                    # `vt.hang_loai` chứ không đóng đinh `"vat_tu"`: từ 08/09/2026 dòng của bước
                    # có thể trỏ vào danh mục GIẤY — đó là đường DUY NHẤT giấy vào bảng cân đối ở
                    # tầng lệnh.
                    self._dong_lenh(l, (vt.hang_loai, int(vt.vat_tu_id)), vt.don_vi_snapshot,
                                    _f(vt.so_luong), cd)
                )

        # --- lệnh/bài không sinh dòng nào: KHÔNG nói gì (23/09/2026) --------
        # Trước đây khối này đẻ danh sách `bo_qua` ("Lệnh chưa khai vật tư nào ở bước — kể cả
        # giấy.", "Bài ghép chưa chọn giấy chung.") để ba màn bày lên thành băng cảnh báo. Đã gỡ
        # hẳn: bảng cân đối chỉ cân đối thứ ĐÃ được khai, chưa khai thì vắng mặt, không phải một
        # cảnh báo phải đọc mỗi lần mở màn. Cửa chặn thật vẫn nguyên ở xếp lịch —
        # `xep_lich_service._chan_chua_giu_du` (giữ chỗ đủ mới cho xếp) và cửa phát hành
        # `xep_lich/release.py`, cả hai đều tự hỏi `GiuChoService.trang_thai`, không đọc danh sách
        # này. Đừng dựng lại nó ở tầng engine.

        # --- vật tư khai tay ở bước CHUNG của bài ---------------------------
        # Một câu cho mọi bài; giữ thứ tự bài → dòng vật tư như vòng hỏi từng bài trước đây.
        chung = {c.id: (c, bg) for bg in bais for c in self._buoc_chung(bg.id)}
        theo_bai: dict[int, list] = {}
        for vt in self.repo.vat_tu_theo_buoc_chung(list(chung)):
            theo_bai.setdefault(chung[vt.bai_ghep_cong_doan_id][1].id, []).append(vt)
        for bg in bais:
            for vt in theo_bai.get(bg.id, []):
                if _f(vt.so_luong) <= 0:
                    continue
                tho.append(
                    self._dong_bai(bg, ("vat_tu", int(vt.vat_tu_id)), vt.don_vi_snapshot,
                                   _f(vt.so_luong), chung[vt.bai_ghep_cong_doan_id][0])
                )
        return tho

    def _bo_buoc_da_xong(self, tho: list[dict]) -> tuple[list[dict], dict[tuple, float]]:
        """Bỏ dòng của BƯỚC đã chạy xong — trả `(dòng còn lại, {khoá đã cấp: lượng coi như tiêu})`.

        Bản chất bảng cân đối là "CÒN phải lo gì". Một bước chạy xong tức là nó đã có đủ đồ để
        chạy — không còn gì để mua, để giữ chỗ, để nhắc. Trước 23/09/2026 dòng ấy nằm lại vĩnh
        viễn dưới dạng "đã cấp đủ" (xám, `con_phai_co = 0`), vì `lsx.trang_thai` dừng ở
        `da_phat_hanh` và không có mốc nào sau đó — bảng chỉ dài thêm, không bao giờ ngắn lại.

        Mốc rụng là BƯỚC, không phải LỆNH: vật tư neo vào đúng bước tiêu thụ nó (08/09/2026), nên
        lệnh in xong mà chưa cán màng thì dòng giấy rụng còn dòng keo vẫn ở lại. Chờ cả lệnh xong
        mới rụng là giữ lại đúng những dòng đã hết việc.

        Lượng trả về ở vế thứ hai theo ĐƠN VỊ GỐC (dòng đã qua `_quy_doi_dong`) và dùng CHÍNH khoá
        mà `_chay_con_tro` tra `da_cap` — khoá nào không khớp thì tầng gọi trừ 0, vô hại.
        """
        co_buoc = [d for d in tho if d.get("buoc_id")]
        if not co_buoc:
            return tho, {}
        xong_lsx, xong_bai = self.repo.buoc_da_chay_xong(
            lsx_buoc_ids={int(d["buoc_id"]) for d in co_buoc if not d.get("bai_ghep_id")},
            bai_buoc_ids={int(d["buoc_id"]) for d in co_buoc if d.get("bai_ghep_id")},
        )
        if not xong_lsx and not xong_bai:
            return tho, {}
        con_lai: list[dict] = []
        da_tieu: dict[tuple, float] = {}
        for d in tho:
            buoc = d.get("buoc_id")
            xong = bool(buoc) and (
                int(buoc) in (xong_bai if d.get("bai_ghep_id") else xong_lsx)
            )
            if not xong:
                con_lai.append(d)
                continue
            khoa = (d["hang"], d["lsx_id"], d["bai_ghep_id"])
            da_tieu[khoa] = da_tieu.get(khoa, 0.0) + _f(d.get("nhu_cau"))
        return con_lai, da_tieu

    def _buoc_chung(self, bai_ghep_id: int) -> list[BaiGhepCongDoan]:
        nap = getattr(self, "_chung_nap", None)
        if nap is not None and bai_ghep_id in nap:
            return nap[bai_ghep_id]
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
        return {
            "hang": hang, "loai": "vat_tu", "lsx_id": l.id, "bai_ghep_id": None,
            "buoc_id": getattr(buoc, "id", None),
            "ma": l.ma, "ten_viec": getattr(buoc, "ten", None),
            "ngay_can": self._ngay_can_cua(hang, l.id, None),
            # "Lệnh của ai, giao ngày nào" — hai câu mà người lập kế hoạch luôn phải hỏi kèm khi
            # nhìn một dòng thiếu hàng. `han_giao_khach` là hạn KHÁCH (lấy từ đơn), khác
            # `han_sx` ở trên là hạn nội bộ do kế hoạch đặt — đừng thay nhau.
            "khach_ten": self._khach_cua(l.id),
            "han_giao_khach": getattr(l, "han_giao_khach", None),
            # Thứ tự ăn tồn — xem `_chay_con_tro`. Hạn là ngày NGƯỜI khai, không phải ngày suy.
            "han_sx": getattr(l, "han_hoan_thanh_sx", None),
            "dvt": dvt, "sl": sl,
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

    def _khach_han_bai(self, lsx_map: dict) -> dict:
        """Khách + hạn giao của một BÀI, gộp từ các lệnh thành viên."""
        tens = sorted({t for t in (self._khach_cua(lid) for lid in (lsx_map or {})) if t})
        hans = [h for h in (getattr(l, "han_giao_khach", None)
                            for l in (lsx_map or {}).values()) if h]
        return {
            "khach_ten": (tens[0] if len(tens) == 1 else (f"{len(tens)} khách" if tens else None)),
            "han_giao_khach": min(hans) if hans else None,
        }

    def _dong_bai(self, bg: BaiGhep, hang, dvt, sl, buoc, *, ct_mat_hang: bool = False) -> dict:
        lsx_map, so_to, muc = getattr(self, "_bai_ctx", {}).get(bg.id, ({}, {}, {}))
        # Bài chạy chung một lượt ⇒ xếp theo hạn SỚM NHẤT của các thành viên.
        hans = [h for h in (getattr(l, "han_hoan_thanh_sx", None)
                            for l in (lsx_map or {}).values()) if h]
        return {
            "hang": hang, "loai": "vat_tu", "lsx_id": None, "bai_ghep_id": bg.id,
            # Cùng lý do như `_dong_lenh`. Ở đây `buoc_id` là `bai_ghep_cong_doan.id` — KHÁC không
            # gian id với bước lệnh, nhưng cặp `(lsx_id, bai_ghep_id)` trong khoá đã phân biệt sẵn
            # (dòng bài luôn có `lsx_id=None`), nên không cần thêm cờ loại.
            "buoc_id": getattr(buoc, "id", None),
            "ma": bg.ma, "ten_viec": getattr(buoc, "ten", None),
            "ngay_can": self._ngay_can_cua(hang, None, bg.id),
            "han_sx": min(hans) if hans else None,
            # Bài gom nhiều lệnh ⇒ có thể nhiều khách. Một tên thì nói tên; nhiều tên thì nói
            # ĐÚNG là "3 khách" chứ không bốc một cái tên làm đại diện — người đọc sẽ tưởng cả
            # bài của khách đó. Hạn giao lấy SỚM NHẤT, cùng lẽ với `han_sx` ngay trên.
            **self._khach_han_bai(lsx_map),
            "dvt": dvt, "sl": sl,
            # Dòng này mang SỐ TỜ của cả bài chứ không mang lượng theo đơn vị gốc ⇒ phải chạy công
            # thức lượng của mặt hàng mới ra kg. Xem `_ve_goc(tong_lenh=…)`.
            "ct_mat_hang": ct_mat_hang,
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
            # `tong_lenh` bật theo TỪNG DÒNG (08/09/2026), không bật cứng cho cả đường nhu cầu
            # nữa: chỉ dòng giấy của BÀI GHÉP mang số TỜ và cần công thức lượng của mặt hàng mới
            # ra kg. Dòng của BƯỚC — vật tư lẫn giấy — đã mang sẵn số theo đơn vị gốc, chạy công
            # thức thêm lần nữa là vứt số thật đi. Hai đường "đã cấp"/"đang về" thì không bao giờ.
            kq = self._ve_goc(d["hang"], d["dvt"], d["sl"], d.get("qc"),
                              tong_lenh=bool(d.get("ct_mat_hang")))
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

    # ---- (d) ----------------------------------------------------------------

    def _chay_con_tro(self, tho, *, ton, dang_ve, da_cap, dang_linh, vet_mua=None) -> list[dict]:
        # Phần đã cấp CÒN LẠI chưa gán cho dòng nào — bản sao để trừ dần, không đụng dict gốc.
        cap_con = dict(da_cap)
        theo_hang: dict[tuple, list[dict]] = {}
        for d in tho:
            theo_hang.setdefault(d["hang"], []).append(d)

        ra: list[dict] = []
        for hang, ds in theo_hang.items():
            obj = self._objs.get(hang)
            # THỨ TỰ ĂN TỒN = HẠN SẢN XUẤT (18/09/2026): lệnh phải xong trước được tính trước. Không
            # còn xếp theo ngày cần — ngày đó giờ chỉ có khi đã lập yêu cầu mua, tức sau khi bảng đã
            # cân đối xong. Lệnh chưa khai hạn xuống CUỐI: không được chen lên trước lệnh có hạn.
            ds.sort(key=lambda d: (d.get("han_sx") is None, d.get("han_sx") or date.max, d["ma"]))
            # Số dòng của cùng (mặt hàng, chủ thể) — quyết định có phải CHIA phần đã cấp không.
            so_dong_khoa: dict[tuple, int] = {}
            for d in ds:
                k = (hang, d["lsx_id"], d["bai_ghep_id"])
                so_dong_khoa[k] = so_dong_khoa.get(k, 0) + 1
            con_lai_chi_ton = float(ton.get(hang, 0.0))
            # ⚠️ Bẫy đếm hai lần #2: hàng đang về cộng MỘT lần, ở đây, cho cả mặt hàng — không có
            # phép trừ "đang mua" nào nữa ở dưới. Không so ngày về với ngày cần: hệ không suy ngày
            # cần, nên cũng không có "về muộn" để loại lô nào ra.
            con_lai = con_lai_chi_ton + sum(sl for _ngay, sl, _ma, _lid in dang_ve.get(hang, []))
            dong_out: list[dict] = []
            so_do = 0
            so_khong_ro = 0
            tong_can = 0.0
            for d in ds:
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
                # Phần thiếu RIÊNG của dòng này = phần nó không được phủ. KHÔNG lấy `−con_lai`
                # (thiếu luỹ kế): tick hai dòng đỏ rồi gộp một yêu cầu mua thì số luỹ kế cộng
                # chồng lên nhau, đi mua thừa đúng phần đã đếm hai lần.
                thieu = max(0.0, con_phai_co - max(0.0, truoc))
                if mau == MAU_DO:
                    so_do += 1
                elif mau == MAU_KHONG_RO:
                    so_khong_ro += 1
                tong_can += con_phai_co
                dong_out.append({
                    "loai": d["loai"],
                    "lsx_id": d["lsx_id"],
                    "bai_ghep_id": d["bai_ghep_id"],
                    "buoc_id": d.get("buoc_id"),
                    "is_rush": bool(d.get("is_rush")),
                    "ma": d["ma"],
                    "ten_viec": d["ten_viec"],
                    "ngay_can": d["ngay_can"],
                    "khach_ten": d.get("khach_ten"),
                    "han_giao_khach": d.get("han_giao_khach"),
                    "nhu_cau": round(_f(d["nhu_cau"]), 4),
                    "nhu_cau_hien_thi": d["nhu_cau_hien_thi"],
                    "da_cap": round(cap, 4),
                    "dang_linh": round(linh, 4),
                    "con_phai_co": round(con_phai_co, 4),
                    "con_lai_sau": round(con_lai, 4),
                    "thieu": round(thieu, 4),
                    "trang_thai": mau,
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
                # Vết mua treo ở MẶT HÀNG chứ không ở dòng: phiếu mua không biết lệnh nào, nó chỉ
                # biết mua món gì. Dán xuống từng dòng là bịa ra quan hệ phiếu↔lệnh không có thật.
                "phieu_mua": (vet_mua or {}).get(hang, []),
                "dong": dong_out,
            })
        # Nhóm không đánh giá được xếp ngay sau nhóm thiếu: cả hai đều là việc phải lo, chỉ khác
        # là một cái biết thiếu bao nhiêu, một cái chưa biết gì.
        ra.sort(key=lambda g: (-g["so_dong_do"], -g["so_dong_khong_ro"], g["hang_ma"] or ""))
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
            ra = [g for g in ra
                  if g["so_dong_do"] > 0
                  or g.get("so_dong_khong_ro", 0) > 0]
        return ra

    # ================== ĐỀ NGHỊ MUA ==================

    def gom_de_nghi(self, chon: list[dict]) -> dict:
        """Gom các dòng được tick thành MỘT yêu cầu mua bộ phận.

        Trả `{lines, needed_date, related_document_code, nguon}` để router gọi service thu mua hiện
        có — không đẻ đường tạo yêu cầu mua thứ hai.

        Số lượng = ĐÚNG phần thiếu của từng dòng, KHÔNG làm tròn ram/kiện: thu mua tự làm tròn lúc
        đặt, còn kế hoạch làm tròn thì con số gửi đi không còn kiểm lại được với bảng.

        `needed_date` luôn `None` (18/09/2026): người lập tự gõ ngày cần hàng trên form, và CHÍNH
        ngày đó quay về làm "Ngày cần" của lệnh qua `nguon` (khoá các dòng đã tick).
        """
        bang = self.can_doi()
        tra: dict[tuple, dict] = {}
        for g in bang["items"]:
            if g["loai_nhom"] != "vat_tu":
                continue
            for d in g["dong"]:
                tra[_khoa_dong(g["hang_loai"], g["hang_id"], d)] = (g, d)
        lines: list[dict] = []
        mas: list[str] = []
        nguon: list[dict] = []
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
            if _f(d["thieu"]) <= 0:
                raise KeHoachVatTuValidationError(
                    f"Dòng {d['ma']} không còn thiếu — không đề nghị mua nữa."
                )
            key = (g["hang_loai"], g["hang_id"])
            cur = gop.setdefault(key, {"g": g, "sl": 0.0})
            cur["sl"] += _f(d["thieu"])
            if d["ma"] not in mas:
                mas.append(d["ma"])
            nguon.append({
                "hang_loai": g["hang_loai"], "hang_id": g["hang_id"],
                "lsx_id": d.get("lsx_id"), "bai_ghep_id": d.get("bai_ghep_id"),
                "buoc_id": d.get("buoc_id"),
            })
        if not gop:
            raise KeHoachVatTuValidationError("Chưa chọn dòng nào.")
        for (loai, hid), cur in gop.items():
            g = cur["g"]
            lines.append({
                "hang_loai": loai,
                "hang_id": hid,
                "item_name": g["hang_ten"],
                "unit": g["don_vi_goc"] or "",
                # Làm tròn LÊN tới 0,01: cột `quantity` là Numeric(14,2) và ô số lượng trên form
                # YCMH đi bước 0,01 — số 3 lẻ (vd 79,475) bị trình duyệt chặn Lưu. Mua dư một chút
                # thì còn phủ đủ chỗ thiếu; làm tròn xuống là mua hụt.
                "quantity": math.ceil(round(cur["sl"] * 100, 6)) / 100,
            })
        return {
            "lines": lines,
            "needed_date": None,
            "related_document_code": ", ".join(mas[:5]),
            "nguon": nguon,
        }
