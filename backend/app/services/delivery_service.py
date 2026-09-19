"""Giao hàng — luật nghiệp vụ (docs/prd-giao-hang.md).

Router chỉ điều phối; mọi luật nằm ở đây. Sáu luật hay bị "sửa cho gọn" rồi vỡ:

1. **Trạng thái yêu cầu là HÀM** (`trang_thai_yeu_cau`) — chỉ `cho_len_ke_hoach`/`da_huy` được lưu.
   Đừng thêm cột: tầng dưới có 8 trạng thái × 4 kết quả, quên cập nhật ngược một nhánh là yêu cầu
   treo mãi ở "đang thực hiện".
2. **"Đã giao" luôn là `SUM`** từ `delivery_trip_lines` (repo). Không cache, không cột cộng dồn.
3. **Một yêu cầu chỉ MỘT lần giao đang chạy** (nghiệm thu #3) — điều kiện giữ cho luật 1 tính được.
4. **Trùng lịch tài xế thì CHẶN; sát giờ thì CẢNH BÁO** (PRD §6). Hai vế khác nhau, đừng gộp.
5. **`km >= 0`**, không phải `> 0`. Khách không nghe máy khi xe chưa lăn bánh thì 0 km là số THẬT.
   `> KM_CANH_BAO` chỉ cảnh báo, KHÔNG chặn.
6. **Hàng ra khỏi kho thì PHẢI CÓ PHIẾU KHO — không có ngoại lệ cho giao khách.** Quản lý bấm
   *Gửi yêu cầu xuất kho* ⇒ tạo ĐÚNG MỘT `stock_requests` loại XUẤT, y như mọi bộ phận khác xin
   vật tư. Kho lập phiếu · ghi sổ · trừ tồn bằng chính luồng sẵn có; **không một dòng code nào
   bên kho bị sửa, kho không phải học gì mới**.

   Ba bản trước đều sai và đều bị chủ chốt bắt (19/08/2026): (a) tự sinh chứng từ lúc lưu kế
   hoạch; (b) dựng chứng từ song song `delivery_issue_requests` với nút *Duyệt* riêng — trong khi
   kho **không có bước duyệt** (bỏ từ 06/08/2026: tạo yêu cầu là duyệt luôn), họ **lập phiếu**;
   (c) lấy cớ "thành phẩm không có trong danh mục" để bỏ hẳn phiếu. Danh mục Giấy / Vật tư khác
   là danh mục PHẲNG, xưởng vẫn khai thành phẩm vào đó rồi nhập kho lấy số lượng — đường đã có
   sẵn, chỉ là tôi không hỏi.

   Sau khi kho ghi sổ, **TÀI XẾ tự bấm** *Đã lấy hàng* — người cầm hàng mới là người biết.
"""
from __future__ import annotations

import secrets
import string
from datetime import date, datetime, timedelta, timezone

from .stock_request_service import StockRequestService
from .thanh_pham_khai_bao import cum_ban, khai_mot_dong
from ..realtime import hub
from ..models.delivery import (
    HUONG_XU_LY,
    KM_CANH_BAO,
    LAN_GIAO_CO_HANG_DEN_TAY,
    LAN_GIAO_SUA_DUOC,
    LG_DA_HUY,
    LG_DA_LAY_HANG,
    LG_DA_LEN_KE_HOACH,
    LG_DA_TRA_HANG,
    LG_DANG_CHUAN_BI,
    LG_DANG_GIAO,
    LG_DANG_TRA_HANG,
    LG_GIAO_THIEU,
    LG_THANH_CONG,
    LG_THAT_BAI,
    XU_LY_TRA_VE,
    YC_CHO_LEN_KE_HOACH,
    YC_DA_HUY,
)
from ..models.delivery import LAN_GIAO_DANG_CHAY
from ..models.order import STATUS_ORDERED
from ..models.stock_request import REQ_DONE
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN

# Hai chuyến cách nhau dưới ngần này thì CẢNH BÁO (không chặn) — PRD §6.
DEM_SAT_GIO = timedelta(minutes=30)

#: Ô Lượt xe lúc lên đơn = "Lượt mới" (PRD khoán km §14). Số nguyên = ghép vào lượt đang mở.
LUOT_MOI = "moi"
#: Ngày của lượt theo giờ VIỆT NAM — chuyến lấy hàng 6h sáng giờ VN là 23h hôm trước theo UTC.
_VN_TZ = timezone(timedelta(hours=7))
#: Chuyến còn CHƯA có kết quả — lượt còn điểm ở mấy trạng thái này thì chưa về kho được.
_CHUA_KET_QUA = (LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI, LG_DA_LAY_HANG, LG_DANG_GIAO)

#: Mốc "người gọi KHÔNG gửi trường này" — phân biệt với `None` nghĩa là "gửi lên để XOÁ".
#: Cần cho `doi_ke_hoach(phu_xe_employee_id=...)`: dùng `None` làm mặc định thì không có đường nào
#: gỡ phụ xe đã xếp, vì gỡ và không-đụng-tới trông giống hệt nhau.
_KHONG_GUI = object()

# Trạng thái dẫn xuất của yêu cầu — KHÔNG lưu, chỉ trả cho FE.
YC_DANG_THUC_HIEN = "dang_thuc_hien"
YC_DA_GIAO_DU = "da_giao_du"
YC_GIAO_THIEU = "giao_thieu"
YC_THAT_BAI = "that_bai"
YC_CHUYEN_DA_HUY = "chuyen_da_huy"


class DeliveryError(Exception):
    """Lỗi nghiệp vụ giao hàng — router dịch thành HTTP 400/403/404."""


class DeliveryNotFound(DeliveryError):
    pass


class DeliveryForbidden(DeliveryError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryService:
    def __init__(self, deliveries, orders, employees, users, departments,
                 stock_requests=None, stock_vouchers=None, xe=None, muc_km=None) -> None:
        self.deliveries = deliveries
        self.orders = orders
        self.employees = employees
        self.users = users
        self.departments = departments
        # Service YÊU CẦU KHO của chính họ. Giao hàng KHÔNG tự dựng chứng từ — nó gọi đúng cửa
        # mà mọi bộ phận khác đang gọi, nên luật kho (mặt hàng phải có trong danh mục, đơn vị
        # phải đổi được, tạo là duyệt luôn) áp cho giao hàng y hệt, miễn phí.
        self.stock_requests = stock_requests
        # Service PHIẾU kho — chỉ dùng cho đường TRẢ HÀNG VỀ (chuyến hỏng / giao thiếu). Giao hàng
        # vẫn không tự dựng chứng từ: nó gọi đúng cửa của kho, luật kho áp y hệt.
        self.stock_vouchers = stock_vouchers
        # REPO danh mục Xe + Mức khoán km (12/09/2026). Tuỳ chọn như `stock_*` để mọi nơi đang
        # dựng service bằng 5 tham số cũ không phải sửa; thiếu thì đường khai mức / gán xe báo
        # "không tìm thấy" chứ không lặng lẽ ghi bừa.
        self.xe = xe
        self.muc_km = muc_km

    # =====================================================================================
    # Mã chứng từ
    # =====================================================================================
    def _sinh_ma(self, tien_to: str, da_ton_tai) -> str:
        """`YCGH-yymmdd-XXXX` / `DNXGH-yymmdd-XXXX` — cùng khuôn `YCMH-` bên Thu mua."""
        hom_nay = _utcnow().strftime("%y%m%d")
        bang_chu = string.ascii_uppercase + string.digits
        for _ in range(20):
            duoi = "".join(secrets.choice(bang_chu) for _ in range(4))
            ma = f"{tien_to}-{hom_nay}-{duoi}"
            if da_ton_tai(ma) is None:
                return ma
        raise DeliveryError("Không sinh được mã chứng từ duy nhất, vui lòng thử lại.")

    # =====================================================================================
    # Phạm vi — lọc DÒNG, không ẩn tab
    # =====================================================================================
    def _phong_duoc_xem(self, *, scope: str | None, actor) -> list[int] | None:
        """Danh sách `department_id` người gọi được xem. None = không giới hạn (Tất cả)."""
        if scope is None or scope == SCOPE_ALL:
            return None
        phong = getattr(actor, "department_id", None)
        if phong is None:
            return []
        if scope == SCOPE_DEPARTMENT:
            return [phong]
        return [phong]

    def _employee_cua_user(self, actor) -> int | None:
        emp = self.employees.get_by_user_id(actor.id) if actor is not None else None
        return emp.id if emp is not None else None

    def chan_ngoai_pham_vi_yeu_cau(self, request, *, scope, actor) -> None:
        """403 khi đọc/ghi một yêu cầu ngoài phạm vi. Gọi ở MỌI đường có id trên URL —
        lọc danh sách mà quên gác đường id là hàng rào chỉ có ở màn hình."""
        if scope is None or scope == SCOPE_ALL:
            return
        if scope == SCOPE_OWN:
            # Bán hàng: yêu cầu mình lập. Tài xế: yêu cầu có chuyến của mình.
            if request.created_by == getattr(actor, "id", None):
                return
            eid = self._employee_cua_user(actor)
            if eid is not None:
                for t in self.deliveries.trips_cua_yeu_cau(request.id):
                    if t.employee_id == eid:
                        return
            raise DeliveryForbidden("Bạn không có quyền xem yêu cầu giao hàng này")
        phong = self._phong_duoc_xem(scope=scope, actor=actor)
        if phong is not None and request.department_id not in phong:
            raise DeliveryForbidden("Bạn không có quyền xem yêu cầu giao hàng này")

    def chan_ngoai_pham_vi_trip(self, trip, *, scope, actor) -> None:
        if scope is None or scope == SCOPE_ALL:
            return
        if scope == SCOPE_OWN:
            eid = self._employee_cua_user(actor)
            if eid is not None and trip.employee_id == eid:
                return
            req = self.deliveries.get_request(trip.request_id)
            if req is not None and req.created_by == getattr(actor, "id", None):
                return
            raise DeliveryForbidden("Bạn không có quyền xem chuyến giao này")
        req = self.deliveries.get_request(trip.request_id)
        phong = self._phong_duoc_xem(scope=scope, actor=actor)
        if req is None or (phong is not None and req.department_id not in phong):
            raise DeliveryForbidden("Bạn không có quyền xem chuyến giao này")

    # =====================================================================================
    # Số lượng — còn phải giao
    # =====================================================================================
    def dang_giu_hang(self, req) -> bool:
        """Yêu cầu còn GIỮ phần chưa giao của nó không (19/09/2026).

        Giữ khi: chưa có chuyến · chuyến đang chạy (kể cả đang chở hàng về) · chuyến giao thiếu mà
        phiếu nhập trả về chưa ghi sổ xong. Còn lại — chuyến đã huỷ, thất bại đã nhận lại hàng, giao
        thiếu đã nhận lại — thì NHẢ: phần đó quay về "giao được" để lập yêu cầu mới. Bản cũ giữ mãi
        mọi yêu cầu chưa huỷ, nên phần hỏng của một chuyến thất bại không bao giờ giao lại được.
        """
        if req.trang_thai == YC_DA_HUY:
            return False
        trips = self.deliveries.trips_cua_yeu_cau(req.id)
        if not trips:
            return True
        for t in trips:
            if t.trang_thai in LAN_GIAO_DANG_CHAY:
                return True
            if t.trang_thai == LG_GIAO_THIEU:
                tra = self.deliveries.yeu_cau_kho_cua_chuyen(t.id, "NHAP")
                if tra is not None and tra.trang_thai != REQ_DONE:
                    return True
        return False

    def _so_giao(self, order) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
        """(đặt, đã giao, đang giữ) theo `order_line_id`."""
        dat = {ln.id: int(ln.qty or 0) for ln in order.lines}
        da_giao = self.deliveries.da_giao_theo_dong(order.id)
        dang_giu: dict[int, int] = {}
        for req in self.deliveries.requests_mo_cua_don(order.id):
            if not self.dang_giu_hang(req):
                continue
            da_cua_req = self.deliveries.da_giao_cua_yeu_cau(req.id)
            for ln in req.lines:
                chua_giao = int(ln.qty) - int(da_cua_req.get(ln.order_line_id, 0))
                if chua_giao > 0:
                    dang_giu[ln.order_line_id] = dang_giu.get(ln.order_line_id, 0) + chua_giao
        return dat, da_giao, dang_giu

    def con_phai_giao(self, order_id: int) -> dict[int, int]:
        """{order_line_id: còn phải giao} = đặt − đã giao − đang GIỮ (xem `dang_giu_hang`).

        Trừ cả phần yêu cầu đang giữ, nếu không thì lập hai yêu cầu liên tiếp là đặt vượt số đơn
        mà mỗi lần kiểm đều thấy "còn đủ".
        """
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise DeliveryNotFound("Không tìm thấy đơn hàng bán")
        dat, da_giao, dang_giu = self._so_giao(order)
        return {
            lid: max(0, so - int(da_giao.get(lid, 0)) - int(dang_giu.get(lid, 0)))
            for lid, so in dat.items()
        }

    def nguon_giao_theo_cum(self, order) -> list[dict]:
        """Mỗi cụm bán: đặt · đã giao · đang giữ · kho đã nhận · tồn thật · GIAO ĐƯỢC (19/09/2026).

        Luật chủ chốt: "không được giao phần chưa nhập kho". Giao được =
          · cụm CÓ lệnh: kho ĐÃ NHẬN từ yêu cầu nhập của lệnh CHÍNH ĐƠN NÀY − đã giao − đang giữ.
            Không đọc tồn chung của mã: hai đơn trùng tên hàng dùng chung một mã Thành phẩm, đọc tồn
            chung là đơn này giao lấn hàng của đơn kia;
          · cụm KHÔNG có lệnh (hàng có sẵn, không qua xưởng): tồn thật của mã − đang giữ;
        rồi kẹp bởi còn phải giao và tồn thật của mã. Hai cụm cùng một mã dùng CHUNG phần kho — số
        `giao_duoc` của từng cụm là trần riêng, `tao_yeu_cau` kiểm tổng theo mã.
        """
        from ..models.stock_request import REQ_CANCELLED, REQ_REJECTED
        from ..repositories.stock_lot_repo import StockLotRepository
        from .thanh_pham_khai_bao import tim_theo_ten

        db = self.deliveries.db
        cums = cum_ban(order)
        dat, da_giao, dang_giu = self._so_giao(order)
        lenh = self.deliveries.lenh_theo_dong_don(order.id)

        tp_cua_cum = {c.khoa: tim_theo_ten(db, c.ten) for c in cums}
        tp_ids = {tp.id for tp in tp_cua_cum.values() if tp is not None}
        ton_kho = StockLotRepository(db).on_hand_by_kho([("vat_tu", i) for i in tp_ids])
        ton = {i: sum(ton_kho.get(("vat_tu", i), {}).values()) for i in tp_ids}

        lsx_ids = [s for ds in lenh.values() for s in ds]
        de_nghi: dict[int, float] = {}
        da_nhan: dict[int, float] = {}
        for req, ln in self.deliveries.dong_nhap_tp_cua_lenh(lsx_ids):
            nhan = float(ln.sl_da_ung or 0)
            song = req.trang_thai not in (REQ_CANCELLED, REQ_REJECTED)
            de_nghi[ln.hang_id] = de_nghi.get(ln.hang_id, 0.0) + (
                StockRequestService.muc_tieu_hieu_luc(ln) if song else nhan)
            da_nhan[ln.hang_id] = da_nhan.get(ln.hang_id, 0.0) + nhan

        # Phần kho CÒN DÙNG ĐƯỢC của mỗi mã = nguồn − Σ(đã giao + đang giữ) mọi cụm dùng mã đó.
        dung: dict[int, float] = {}
        co_lenh_theo_tp: dict[int, bool] = {}
        for c in cums:
            tp = tp_cua_cum[c.khoa]
            if tp is None:
                continue
            d = c.dong_dau.id
            dung[tp.id] = dung.get(tp.id, 0.0) + da_giao.get(d, 0) + dang_giu.get(d, 0)
            co_lenh_theo_tp[tp.id] = co_lenh_theo_tp.get(tp.id, False) or any(
                lenh.get(od.id) for od in c.dong)
        con_kho: dict[int, float] = {}
        for i in tp_ids:
            if co_lenh_theo_tp.get(i):
                nguon = da_nhan.get(i, 0.0) - dung.get(i, 0.0)
                con_kho[i] = max(0.0, min(nguon, ton[i]))
            else:
                # Hàng có sẵn: tồn thật đã trừ phần xuất rồi, chỉ trừ phần đang giữ chưa xuất.
                giu = sum(dang_giu.get(c.dong_dau.id, 0) for c in cums
                          if tp_cua_cum[c.khoa] is not None and tp_cua_cum[c.khoa].id == i)
                con_kho[i] = max(0.0, ton[i] - giu)

        ra: list[dict] = []
        for c in cums:
            tp = tp_cua_cum[c.khoa]
            d = c.dong_dau.id
            con = min(max(0, dat[od.id] - da_giao.get(od.id, 0) - dang_giu.get(od.id, 0))
                      for od in c.dong)
            ra.append({
                "cum": c,
                "tp_id": tp.id if tp is not None else None,
                "co_lenh": any(lenh.get(od.id) for od in c.dong),
                "lsx_ids": sorted({s for od in c.dong for s in lenh.get(od.id, [])}),
                "dat": int(c.so_luong),
                "da_giao": int(da_giao.get(d, 0)),
                "dang_giu": int(dang_giu.get(d, 0)),
                "con_phai_giao": int(con),
                "kho_de_nghi": de_nghi.get(tp.id, 0.0) if tp is not None else 0.0,
                "kho_da_nhan": da_nhan.get(tp.id, 0.0) if tp is not None else 0.0,
                "ton_that": ton.get(tp.id, 0.0) if tp is not None else 0.0,
                "con_kho": con_kho.get(tp.id, 0.0) if tp is not None else 0.0,
                "giao_duoc": int(min(con, con_kho.get(tp.id, 0.0))) if tp is not None else 0,
            })
        return ra

    def da_giao_du(self, order_id: int) -> bool:
        """Cờ cho kế toán: đơn đã giao đủ ⇒ đủ điều kiện xuất hoá đơn (PRD §16)."""
        order = self.orders.get_by_id(order_id)
        if order is None or not order.lines:
            return False
        da_giao = self.deliveries.da_giao_theo_dong(order_id)
        return all(int(da_giao.get(ln.id, 0)) >= int(ln.qty or 0) for ln in order.lines)

    def trang_thai_yeu_cau(self, request) -> str:
        """Trạng thái HIỂN THỊ của yêu cầu — hàm, không lưu (PRD §7 tầng 1)."""
        if request.trang_thai == YC_DA_HUY:
            return YC_DA_HUY
        trips = self.deliveries.trips_cua_yeu_cau(request.id)
        if not trips:
            return YC_CHO_LEN_KE_HOACH
        da_giao = self.deliveries.da_giao_cua_yeu_cau(request.id)
        if all(int(da_giao.get(ln.order_line_id, 0)) >= int(ln.qty) for ln in request.lines):
            return YC_DA_GIAO_DU
        if any(t.trang_thai in LAN_GIAO_DANG_CHAY for t in trips):
            return YC_DANG_THUC_HIEN
        # Mọi chuyến đã đóng mà chưa giao đủ. Bản cũ trả "chờ lên kế hoạch" — nhưng unique index
        # mg 0229 cấm chuyến thứ hai, nên yêu cầu treo ở hàng chờ mãi. Nay nói đúng kết cục; phần
        # chưa giao đã nhả về "giao được", giao lại = lập yêu cầu mới.
        cuoi = trips[-1].trang_thai
        if cuoi == LG_GIAO_THIEU:
            return YC_GIAO_THIEU
        if cuoi == LG_DA_HUY:
            return YC_CHUYEN_DA_HUY
        return YC_THAT_BAI

    # =====================================================================================
    # Yêu cầu giao hàng
    # =====================================================================================
    def _mat_hang_cua_dong_don(self, order, order_line):
        """Mặt hàng kho của MỘT dòng đơn — LƯỚI AN TOÀN cho đơn chốt TRƯỚC mg 0203.

        Đường chính là `OrderService.confirm()`: chốt đơn là khai thành phẩm vào danh mục
        (docs/prd-thanh-pham.md L1). Đơn đã chốt từ trước KHÔNG backfill (chủ chốt 19/08/2026 —
        "xoá", không nhét lại dữ liệu cũ), nên đơn cũ nào cần giao thì khai ở đây.

        Gọi ĐÚNG hàm mà `confirm()` gọi, không chép lại: chép hai bản là hai công thức mã, lệch
        nhau lúc nào không biết, và lúc đó một dòng đơn có hai dòng danh mục.
        """
        return khai_mot_dong(self.deliveries.db, order, order_line)

    def _noi_nhan(self, order, dia_chi_id=None, lien_he_id=None) -> tuple[str, str | None, str | None]:
        """Nơi nhận của một yêu cầu giao — (địa chỉ, người nhận, SĐT), CHỌN từ khách, không gõ tay.

        Không chọn gì ⇒ nơi nhận của đơn (đơn kế thừa từ báo giá, báo giá chọn từ sổ của khách).
        Chọn ⇒ id phải thuộc ĐÚNG khách của đơn, rồi chụp lại chữ: khách đổi địa chỉ sau này
        không làm phiếu giao cũ đổi theo.
        """
        from ..models.customer import CustomerAddress, CustomerContact

        db = self.deliveries.db
        dia_chi = order.delivery_address or ""
        nguoi = order.delivery_contact_name
        sdt = order.delivery_contact_phone
        if dia_chi_id is not None:
            a = db.get(CustomerAddress, dia_chi_id)
            if a is None or a.customer_id != order.customer_id:
                raise DeliveryError("Địa chỉ giao không thuộc khách hàng của đơn")
            dia_chi = a.address
            sdt = a.phone or sdt
        if lien_he_id is not None:
            c = db.get(CustomerContact, lien_he_id)
            if c is None or c.customer_id != order.customer_id:
                raise DeliveryError("Người nhận không thuộc khách hàng của đơn")
            nguoi, sdt = c.name, c.phone or sdt
        if not (dia_chi or "").strip():
            raise DeliveryError(
                "Khách chưa có địa chỉ giao — thêm địa chỉ ở hồ sơ khách hàng rồi chọn lại")
        return dia_chi, nguoi, sdt

    def tao_yeu_cau(self, *, order_id, ngay_can_giao, lines, actor,
                    dia_chi_id=None, lien_he_id=None) -> dict:
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise DeliveryNotFound("Không tìm thấy đơn hàng bán")
        if order.status != STATUS_ORDERED:
            raise DeliveryError("Chỉ tạo yêu cầu giao từ đơn hàng ĐÃ CHỐT")
        if not lines:
            raise DeliveryError("Phải chọn ít nhất một dòng hàng để giao")

        con_lai = self.con_phai_giao(order_id)
        hop_le = {ln.id for ln in order.lines}
        # CỤM BÁN (design nhập kho thành phẩm §3): người lập chọn cụm và gõ SL MỘT lần. Gửi dòng
        # nào của cụm cũng được; hệ bung ra MỌI dòng của cụm với cùng SL, để đơn vẫn biết Ruột lẫn
        # Bìa đã giao đủ. Hai dòng cùng cụm mà khác SL là tự mâu thuẫn — chặn.
        cum_theo_dong = {ln.id: c for c in cum_ban(order) for ln in c.dong}
        theo_cum: dict[str, tuple] = {}
        for ln in lines:
            lid, qty = int(ln["order_line_id"]), int(ln["qty"])
            if lid not in hop_le:
                raise DeliveryError("Dòng hàng không thuộc đơn hàng này")
            if qty <= 0:
                raise DeliveryError("Số lượng giao phải lớn hơn 0")
            cum = cum_theo_dong[lid]
            da = theo_cum.get(cum.khoa)
            if da is not None and da[1] != qty:
                raise DeliveryError(
                    f"Các phần của «{cum.ten}» giao cùng nhau — số lượng phải bằng nhau"
                )
            theo_cum[cum.khoa] = (cum, qty)
        for cum, qty in theo_cum.values():
            for od in cum.dong:
                if qty > con_lai.get(od.id, 0):
                    raise DeliveryError(
                        f"Vượt số còn phải giao: «{cum.ten}» chỉ còn {con_lai.get(od.id, 0)}, "
                        f"đang yêu cầu {qty}"
                    )
        self._chan_vuot_giao_duoc(order, [(cum, qty) for cum, qty in theo_cum.values()])

        # CHẶN CỨNG, không phải cảnh báo (chủ chốt 20/08/2026: "nay ngày 20 tôi lập phiếu yêu
        # cầu thì sao mà chọn được ngày 19"). Bản đầu chỉ cảnh báo với lý do "nhập bù đơn hôm
        # qua" — nhưng yêu cầu giao là việc SẮP LÀM, không phải sổ ghi việc đã làm: hàng chưa ra
        # khỏi kho thì không có gì để nhập bù. Ngày quá khứ ở đây chỉ có thể là gõ nhầm, mà gõ
        # nhầm thì kéo lệch cả hàng chờ giao lẫn thống kê trễ hạn.
        self._chan_ngay_qua_khu(ngay_can_giao)
        dia_chi, nguoi_nhan, sdt_nguoi_nhan = self._noi_nhan(order, dia_chi_id, lien_he_id)
        canh_bao: list[str] = []

        code = self._sinh_ma("YCGH", self.deliveries.get_request_by_code)
        req = self.deliveries.create_request(
            code=code,
            order_id=order_id,
            customer_id=getattr(order, "customer_id", None),
            department_id=getattr(actor, "department_id", None),
            ngay_can_giao=ngay_can_giao,
            # SNAPSHOT: đông lại ngay, không đọc-sống. Lưu ý giao luôn là của đơn.
            dia_chi=dia_chi,
            nguoi_nhan=nguoi_nhan,
            sdt_nguoi_nhan=sdt_nguoi_nhan,
            ghi_chu=order.delivery_note,
            trang_thai=YC_CHO_LEN_KE_HOACH,
            created_by=getattr(actor, "id", None),
        )
        for cum, qty in theo_cum.values():
            # Tự khai mặt hàng kho từ chính cụm — người lập KHÔNG phải chọn gì. CHỈ dòng đầu cụm
            # mang mã: phiếu xuất kho có một dòng cho cả cụm; mang mã ở mọi dòng là trừ kho hai lần.
            mh = self._mat_hang_cua_dong_don(order, cum.dong_dau)
            for i, od in enumerate(cum.dong):
                if i == 0:
                    self.deliveries.add_request_line(
                        req.id, od.id, qty, hang_loai="vat_tu", hang_id=mh.id, dvt=mh.don_vi_gia,
                    )
                else:
                    self.deliveries.add_request_line(req.id, od.id, qty)
        return {"request": req, "canh_bao": canh_bao}

    def _chan_vuot_giao_duoc(self, order, cum_qty: list[tuple]) -> None:
        """Chủ chốt 19/09/2026: "không được với phần chưa nhập kho" — xem `nguon_giao_theo_cum`."""
        nguon = {n["cum"].khoa: n for n in self.nguon_giao_theo_cum(order)}
        tong_tp: dict[int, int] = {}
        for cum, qty in cum_qty:
            n = nguon[cum.khoa]
            if qty > n["giao_duoc"]:
                goc = (f"kho đã nhận {n['kho_da_nhan']:g} từ sản xuất" if n["co_lenh"]
                       else f"tồn kho {n['ton_that']:g}")
                raise DeliveryError(
                    f"«{cum.ten}» mới giao được {n['giao_duoc']} ({goc}, đã giao {n['da_giao']}, "
                    f"đang chờ giao {n['dang_giu']}) — đang yêu cầu {qty}. "
                    "Phần chưa nhập kho chưa lập yêu cầu giao được."
                )
            tong_tp[n["tp_id"]] = tong_tp.get(n["tp_id"], 0) + qty
            if tong_tp[n["tp_id"]] > n["con_kho"]:
                raise DeliveryError(
                    f"Các sản phẩm cùng mã với «{cum.ten}» chỉ còn {n['con_kho']:g} trong kho "
                    f"để giao, đang yêu cầu tổng {tong_tp[n['tp_id']]}."
                )

    def huy_yeu_cau(self, request_id: int, *, ly_do: str, actor, scope=None) -> None:
        req = self.deliveries.get_request(request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        self.chan_ngoai_pham_vi_yeu_cau(req, scope=scope, actor=actor)
        if req.trang_thai == YC_DA_HUY:
            raise DeliveryError("Yêu cầu đã huỷ rồi")
        # Chuyến đã HUỶ thì yêu cầu huỷ được — không thì nó kẹt: unique index mg 0229 cấm lên chuyến
        # thứ hai, mà chặn huỷ vì "còn chuyến" thì không còn đường nào đóng nó.
        if any(t.trang_thai != LG_DA_HUY for t in self.deliveries.trips_cua_yeu_cau(request_id)):
            raise DeliveryError("Đã lên kế hoạch — phải huỷ kế hoạch trước khi huỷ yêu cầu")
        if not (ly_do or "").strip():
            raise DeliveryError("Phải nhập lý do huỷ")
        req.trang_thai = YC_DA_HUY
        req.ly_do_huy = ly_do.strip()

    #: Dung sai khi kiểm "giờ quá khứ". Người xếp lịch chọn "lấy hàng lúc 14:00" rồi còn gõ ghi
    #: chú, bấm lưu mất vài phút — không có dung sai thì đúng cái ca hay gặp nhất bị chặn oan.
    DUNG_SAI_PHUT = 5

    @classmethod
    def _chan_gio_qua_khu(cls, gio, nhan: str) -> None:
        """Giờ lấy hàng / giờ dự kiến giao không được nằm ở quá khứ.

        Cùng lý do với ngày cần giao: kế hoạch chuyến là việc SẮP LÀM. Xếp chuyến lấy hàng lúc
        8h sáng hôm qua thì tài xế không có cách nào làm, và nó kéo lệch cả bảng chuyến trong
        ngày lẫn thống kê trễ hạn.
        """
        if gio is None:
            return
        moc = datetime.now(timezone.utc) - timedelta(minutes=cls.DUNG_SAI_PHUT)
        # Giờ từ client có thể "naive" (không mang múi giờ) — so trực tiếp là `TypeError`.
        g = gio if gio.tzinfo is not None else gio.replace(tzinfo=timezone.utc)
        if g < moc:
            raise DeliveryError(f"{nhan} không được ở quá khứ.")

    @staticmethod
    def _chan_ngay_qua_khu(ngay) -> None:
        """Ngày cần giao không được nằm trước hôm nay.

        Đặt thành hàm riêng vì có HAI cửa vào — lập mới và sửa. Bản đầu chỉ kiểm ở cửa lập, nên
        sửa yêu cầu là lùi ngày về quá khứ thoải mái: chặn một cửa mà để hở cửa kia thì coi như
        không chặn.
        """
        if ngay is not None and ngay < date.today():
            raise DeliveryError(
                f"Ngày cần giao không được ở quá khứ — hôm nay là {date.today():%d/%m/%Y}."
            )

    def sua_yeu_cau(self, request_id: int, *, actor, scope=None, **thay_doi) -> None:
        req = self.deliveries.get_request(request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        self.chan_ngoai_pham_vi_yeu_cau(req, scope=scope, actor=actor)
        if req.trang_thai == YC_DA_HUY:
            raise DeliveryError("Yêu cầu đã huỷ, không sửa được")
        if self.deliveries.trips_cua_yeu_cau(request_id):
            raise DeliveryError("Đã lên kế hoạch — không sửa được hàng và số lượng nữa")
        # Cửa vào THỨ HAI của ngày cần giao — chặn ở đây nữa, xem `_chan_ngay_qua_khu`.
        if thay_doi.get("ngay_can_giao") is not None:
            self._chan_ngay_qua_khu(thay_doi["ngay_can_giao"])
            req.ngay_can_giao = thay_doi["ngay_can_giao"]
        if "dia_chi_id" in thay_doi or "lien_he_id" in thay_doi:
            order = self.orders.get_by_id(req.order_id)
            req.dia_chi, req.nguoi_nhan, req.sdt_nguoi_nhan = self._noi_nhan(
                order, thay_doi.get("dia_chi_id"), thay_doi.get("lien_he_id"))

    def chan_huy_don_khi_con_yeu_cau_mo(self, order_id: int) -> None:
        """Nghiệm thu #12 — huỷ đơn bán khi còn yêu cầu giao chưa đóng thì bị chặn.

        Thông báo nêu ĐÚNG mã yêu cầu đang mở; bắt người ta đi mò là lỗi giao diện."""
        con_mo = [
            r.code for r in self.deliveries.requests_mo_cua_don(order_id)
            if self.dang_giu_hang(r)
        ]
        if con_mo:
            raise DeliveryError(
                "Đơn còn yêu cầu giao hàng đang chạy: " + ", ".join(sorted(con_mo))
                + ". Huỷ các yêu cầu / chuyến đó trước."
            )

    # =====================================================================================
    # Lên kế hoạch — và đề nghị xuất hàng đi kèm
    # =====================================================================================
    # --- % chia tiền chuyến cho kíp xe (dữ liệu của PHÒNG: `departments.pct_*`) -----------------
    def khoan_km_pct(self, department_id: int) -> tuple[float, float]:
        """(% tài xế, % phụ xe) của phòng — cho màn Cấu hình lương hiện sẵn."""
        pb = self.departments.get_by_id(department_id) if self.departments else None
        return (float(getattr(pb, "pct_tai_xe", 60) or 60),
                float(getattr(pb, "pct_phu_xe", 40) or 40))

    @staticmethod
    def _kiem_cau_truc_bac(items: list[dict]) -> list[dict]:
        """Ba luật, mỗi cái chặn một kiểu sai làm tra bậc ra số vô nghĩa.

        1. Trần km phải TĂNG DẦN — bậc xếp lộn thì `MucKhoanKmRepository.tra_don_gia` (duyệt theo
           thứ tự) trả nhầm.
        2. Bậc vô hạn (`up_to_km=None`) chỉ một, và phải ở CUỐI — nó nuốt mọi km từ chỗ nó đứng.
        3. Trần trùng nhau thì có đoạn hai giá, không ai biết lấy giá nào.
        """
        sach = [it for it in (items or [])]
        vo_han = [i for i, it in enumerate(sach) if it.get("up_to_km") in (None, 0)]
        if len(vo_han) > 1:
            raise DeliveryError("Chỉ được một bậc 'từ … trở lên' (để trống trần km).")
        if vo_han and vo_han[0] != len(sach) - 1:
            raise DeliveryError("Bậc 'từ … trở lên' phải nằm CUỐI bảng.")
        tran = [it["up_to_km"] for it in sach if it.get("up_to_km")]
        if any(b <= a for a, b in zip(tran, tran[1:])):
            raise DeliveryError("Trần km phải tăng dần và không trùng nhau.")
        return [{"up_to_km": it.get("up_to_km") or None, "don_gia": it["don_gia"]} for it in sach]

    # --- MỨC khoán km: mỗi mức một bảng bậc, nhiều xe dùng chung một mức ---------------------
    def _muc_repo(self):
        if self.muc_km is None:
            raise DeliveryError("Chưa nối repo Mức khoán km.")
        return self.muc_km

    def danh_sach_muc(self) -> list[dict]:
        """Mọi mức + bảng bậc + SỐ XE đang dùng.

        Trả kèm `so_xe` để màn cấu hình nói được "sửa mức này là đổi giá của 3 xe" TRƯỚC khi người
        ta gõ — đó là khác biệt lớn nhất so với sửa bảng giá của riêng một chiếc.
        """
        ra = []
        for m in self._muc_repo().list():
            ra.append({
                "id": m.id, "ten": m.ten,
                # `ma` RỖNG, cố ý: ô chọn dùng chung của nền danh mục (`RefSearchField`) vẽ
                # "mã · tên" nhưng tự giấu phần mã khi rỗng — mức chỉ có TÊN, và cái tên đã đủ.
                "ma": "",
                "ghi_chu": m.ghi_chu, "active": bool(m.active),
                "items": self.km_brackets_muc(m.id),
                "so_xe": self.xe.dem_theo_muc(m.id) if self.xe is not None else 0,
            })
        return ra

    def km_brackets_muc(self, muc_id: int) -> list[dict]:
        return [{"up_to_km": b.up_to_km, "don_gia": float(b.don_gia)}
                for b in self._muc_repo().bac_cua(muc_id)]

    def tao_muc(self, *, ten: str, ghi_chu=None) -> int:
        ten = (ten or "").strip()
        if not ten:
            raise DeliveryError("Tên mức không được trống.")
        if self._muc_repo().find_by_ten(ten) is not None:
            raise DeliveryError(f"Đã có mức tên “{ten}”.")
        return self._muc_repo().create(ten=ten, ghi_chu=ghi_chu).id

    def sua_muc(self, muc_id: int, **fields) -> None:
        m = self._muc_repo().get(muc_id)
        if m is None:
            raise DeliveryNotFound("Không tìm thấy mức khoán km")
        # `active` gửi `null` = không nói gì, KHÔNG phải "tắt": cột NOT NULL, ghi thẳng là vỡ.
        if "active" in fields and fields["active"] is None:
            fields.pop("active")
        if "ten" in fields:
            ten = (fields["ten"] or "").strip()
            if not ten:
                raise DeliveryError("Tên mức không được trống.")
            trung = self._muc_repo().find_by_ten(ten)
            if trung is not None and trung.id != muc_id:
                raise DeliveryError(f"Đã có mức tên “{ten}”.")
            fields["ten"] = ten
        self._muc_repo().update(m, **fields)

    def xoa_muc(self, muc_id: int) -> None:
        """Xoá một mức — CHẶN nếu còn xe đang gán.

        Xoá khi còn xe dùng là để lại những chiếc xe trỏ vào một mức không còn — chuyến của chúng
        hoặc bị chặn lên đơn, hoặc (chuyến cũ) âm thầm ăn đơn giá phẳng. Muốn bỏ mức thì chuyển xe
        sang mức khác trước.
        """
        m = self._muc_repo().get(muc_id)
        if m is None:
            raise DeliveryNotFound("Không tìm thấy mức khoán km")
        n = self.xe.dem_theo_muc(muc_id) if self.xe is not None else 0
        if n:
            raise DeliveryError(
                f"Còn {n} xe đang ăn mức này — chuyển các xe đó sang mức khác rồi mới xoá."
            )
        self._muc_repo().delete(m)

    def ghi_bac_muc(self, muc_id: int, items: list[dict]) -> list[dict]:
        """Ghi bảng bậc của MỘT MỨC — cấu hình chung, KHÔNG có tham số phòng ban (14/09/2026).

        CHẶN để trống bảng giá khi mức còn xe đang ăn. Từ 14/09 lên đơn bằng xe có mức rỗng bị
        chặn (`_doi_xe`), nên xoá trắng ở đây là âm thầm khoá đơn giao hàng của mọi xe đó — và
        người vấp là người lên đơn, người không có quyền sửa bảng giá.
        """
        m = self._muc_repo().get(muc_id)
        if m is None:
            raise DeliveryNotFound("Không tìm thấy mức khoán km")
        sach = self._kiem_cau_truc_bac(items)
        if not sach:
            n = self.xe.dem_theo_muc(muc_id) if self.xe is not None else 0
            if n:
                raise DeliveryError(
                    f"Còn {n} xe đang ăn mức “{m.ten}” — không để trống bảng giá được. "
                    "Chuyển các xe đó sang mức khác trước."
                )
        self._muc_repo().ghi_lai_bac(muc_id, sach)
        return self.km_brackets_muc(muc_id)

    def ghi_khoan_km_pct(self, department_id: int, *, pct_tai_xe, pct_phu_xe) -> tuple[float, float]:
        """Lưu % chia tiền một chuyến cho kíp xe.

        Trước 12/09/2026 hai ô này đi ké endpoint ghi bảng bậc cấp phòng. Bảng bậc đó đã GỠ (mọi
        xe ăn theo MỨC), nên % tách ra đường riêng — giữ lại vì nó vẫn là luật thật: tiền một
        chuyến chia cho tài xế và phụ xe, đi một mình thì tài xế ăn trọn.

        Kiểm cộng đúng 100 ở đây — cùng luật với `_dat_khoan_km` bên department_service, một chỗ
        chặn cho một đường ghi. Không đủ 100 thì tổng chi một chuyến đổi theo số người đi, và
        không ai giải thích được vì sao.
        """
        pb = self.departments.get_by_id(department_id) if self.departments else None
        if pb is None:
            raise DeliveryNotFound("Không tìm thấy phòng ban")
        tx = float(pct_tai_xe if pct_tai_xe is not None else pb.pct_tai_xe)
        px = float(pct_phu_xe if pct_phu_xe is not None else pb.pct_phu_xe)
        if abs(tx + px - 100.0) > 0.01:
            raise DeliveryError(
                f"% tài xế + % phụ xe phải bằng 100 (đang {tx:g} + {px:g} = {tx + px:g})."
            )
        pb.pct_tai_xe = tx
        pb.pct_phu_xe = px
        return tx, px

    def _chup_don_gia_km(self, trip) -> None:
        """CHỤP đơn giá + tỷ lệ chia của phòng ban vào chuyến, ngay lúc ghi kết quả (mg 0231).

        ⭐ Vì sao chụp chứ không đọc lúc tính lương: chủ chỉnh đơn giá tháng 9 thì bảng lương
        tháng 5 đã chốt sẽ đổi theo — số cũ không tái lập được, mà không ai thấy nó đổi. Đúng bài
        học `orders.commission_pct` ngày 21/08/2026.

        Lấy theo phòng ban của TÀI XẾ (người chịu trách nhiệm chuyến). Tài xế ngoài khối Giao hàng
        (`_thuoc_khoi_giao_hang` — cờ RIÊNG của phòng, không kế thừa) ⇒ để NGUYÊN `NULL`: nghĩa là
        "chuyến này không thuộc diện khoán km", engine bỏ qua. Ghi 0 vào đó là nói dối rằng đã chụp
        và bằng 0.

        ĐƠN GIÁ THEO BẬC (chủ chốt 24/08/2026): toàn km × đơn giá của bậc km rơi vào. Chụp lại
        ĐÚNG MỘT số (đơn giá đã tra) vào chuyến, nên engine lương / bảng chi tiết / chia kíp KHÔNG
        đổi gì: chúng vẫn đọc `trip.don_gia_km`.

        BẬC THEO MỨC CỦA XE (chủ chốt 12/09/2026 — PRD §11). Đường tra: chuyến → XE → MỨC của xe →
        bảng bậc. Ba nấc, dừng ở nấc đầu tiên có số:

            1. bảng bậc của MỨC mà xe đang ăn
            2. `pb.don_gia_km` (đơn giá phẳng) ← CHỈ còn cho chuyến không khai xe (chuyến cũ, hoặc
               lúc danh mục Xe còn trống)

        Bậc cấp PHÒNG (nấc giữa, có từ 24/08/2026) đã GỠ 12/09/2026: mọi xe đều ăn theo mức nên
        nó thành nơi thứ hai nói cùng một thứ — và là nơi âm thầm nuốt những xe khai thiếu. Từ
        14/09/2026 xe không mức / mức chưa có bậc bị chặn ở `_doi_xe` trước khi tới đây, nên nấc 2
        không còn nuốt được xe nào.
        """
        pb = self._phong_khoan_km(trip)
        if pb is None:
            return
        trip.don_gia_km = self._don_gia_chang(trip, int(trip.km or 0), pb=pb)
        trip.pct_tai_xe = pb.pct_tai_xe
        trip.pct_phu_xe = pb.pct_phu_xe

    def _phong_khoan_km(self, trip):
        """Phòng của TÀI XẾ chuyến, nếu chuyến thuộc diện khoán km — None nếu không."""
        if not self._thuoc_khoi_giao_hang(trip.employee_id):
            return None
        nv = self.employees.get_by_id(trip.employee_id)
        return self.departments.get_by_id(nv.department_id)

    def _don_gia_chang(self, trip, km: int, *, pb=None):
        """Đơn giá của MỘT quãng `km` chạy bằng xe của `trip` — bậc km theo MỨC của xe (PRD §11).

        Tách khỏi `_chup_don_gia_km` từ khi có lượt xe (§14): chặng VỀ KHO không có chuyến riêng,
        nó tra bậc theo km của chính nó trên xe + phòng của chuyến ở điểm cuối."""
        pb = pb if pb is not None else self._phong_khoan_km(trip)
        if pb is None:
            return None
        muc_id = None
        if trip.vehicle_id is not None and self.xe is not None:
            x = self.xe.get(trip.vehicle_id)
            muc_id = getattr(x, "muc_khoan_km_id", None) if x is not None else None
        theo_bac = (self.muc_km.tra_don_gia(muc_id, int(km or 0))
                    if self.muc_km is not None else None)
        return theo_bac if theo_bac is not None else pb.don_gia_km

    # =====================================================================================
    # Lượt xe — tiền km theo CHẶNG (PRD khoán km §14, chủ chốt 18/09/2026)
    # =====================================================================================
    def _xep_vao_luot(self, trip, *, luot_xe_id, actor):
        """Ô Lượt xe lúc lên đơn. `None` = không vào lượt (đường cũ: một ô km cho cả chuyến);
        `"moi"` = lượt mới; số = ghép vào lượt ĐANG MỞ của CÙNG xe.

        Một lượt một xe: số đồng hồ là của một chiếc xe, trộn hai xe là trừ số đồng hồ xe này cho
        số xe kia."""
        if luot_xe_id in (None, ""):
            return None
        if trip.vehicle_id is None:
            raise DeliveryError("Chọn xe trước khi xếp vào lượt — lượt là vòng chạy của một chiếc xe.")
        if str(luot_xe_id) == LUOT_MOI:
            luot = self.deliveries.create_luot(
                code=self._sinh_ma("LX", self.deliveries.get_luot_by_code),
                vehicle_id=trip.vehicle_id,
                ngay=trip.gio_lay_hang.astimezone(_VN_TZ).date(),
                created_by=getattr(actor, "id", None),
            )
        else:
            luot = self.deliveries.get_luot(int(luot_xe_id))
            if luot is None:
                raise DeliveryNotFound("Không tìm thấy lượt xe")
            if luot.ve_kho_luc is not None:
                raise DeliveryError(f"Lượt {luot.code} đã về kho — chọn lượt mới.")
            if luot.vehicle_id != trip.vehicle_id:
                raise DeliveryError(
                    f"Lượt {luot.code} chạy xe khác — một lượt chỉ một xe, vì số đồng hồ là của "
                    "một chiếc xe.")
        self.deliveries.them_diem(luot.id, trip.id)
        return luot

    def luot_mo_cua_xe(self, vehicle_id: int) -> list[dict]:
        """Lượt chưa về kho của một xe — nuôi ô Lượt xe lúc lên đơn."""
        ra = []
        for luot in self.deliveries.luot_mo_cua_xe(int(vehicle_id)):
            trips = [self.deliveries.get_trip(d.delivery_trip_id) for d in luot.diem]
            dau = next((t for t in trips if t is not None), None)
            nv = self.employees.get_by_id(dau.employee_id) if dau is not None else None
            ra.append({
                "id": luot.id, "code": luot.code, "ngay": luot.ngay, "so_diem": len(luot.diem),
                "tai_xe": getattr(nv, "full_name", None),
                "da_xuat_phat": luot.so_dong_ho_xuat_phat is not None,
            })
        return ra

    def _tinh_lai_luot(self, luot) -> None:
        """Tính lại MỌI chặng của lượt từ số đồng hồ — gọi mỗi lần có số mới.

        Chặng xếp theo SỐ ĐỒNG HỒ tăng dần, không theo thứ tự xếp lúc lên đơn: ghé khách nào trước
        là chuyện ngoài đường, đồng hồ mới là sự thật. Km + đơn giá của chặng tới điểm nào chụp vào
        CHÍNH chuyến đó (`trip.km`, `trip.don_gia_km`) ⇒ bảng lương, bảng đối chiếu, chia kíp đọc
        như cũ. Chặng về kho chụp trên lượt, chia cho kíp của điểm cuối."""
        xp = luot.so_dong_ho_xuat_phat
        if xp is None:
            return
        diem = sorted((d for d in luot.diem if d.so_dong_ho is not None),
                      key=lambda d: (int(d.so_dong_ho), d.id))
        truoc, cuoi = int(xp), None
        for d in diem:
            trip = self.deliveries.get_trip(d.delivery_trip_id)
            trip.km = int(d.so_dong_ho) - truoc
            self._chup_don_gia_km(trip)
            truoc, cuoi = int(d.so_dong_ho), trip
        if luot.so_dong_ho_ve_kho is not None and cuoi is not None:
            luot.km_ve_kho = int(luot.so_dong_ho_ve_kho) - truoc
            luot.ve_kho_trip_id = cuoi.id
            luot.don_gia_ve_kho = self._don_gia_chang(cuoi, luot.km_ve_kho)

    def _chan_ngoai_pham_vi_luot(self, luot, *, scope, actor) -> list:
        """Trả các chuyến của lượt; 403 nếu người gọi không xem được chuyến NÀO trong lượt."""
        trips = [t for t in (self.deliveries.get_trip(d.delivery_trip_id) for d in luot.diem)
                 if t is not None]
        loi = None
        for t in trips:
            try:
                self.chan_ngoai_pham_vi_trip(t, scope=scope, actor=actor)
                return trips
            except DeliveryForbidden as e:
                loi = e
        raise loi or DeliveryForbidden("Bạn không có quyền với lượt xe này")

    def _canh_bao_xuat_phat(self, luot, so: int) -> list[str]:
        """Số lúc xuất phát lệch số cuối đã ghi của xe ⇒ NHẮC, không chặn (sổ cũ gõ nhầm mà chặn
        là xe không chạy được lượt nào nữa, trong khi chưa có màn sửa số)."""
        cuoi = self.deliveries.so_dong_ho_cuoi_cua_xe(luot.vehicle_id, bo_qua_luot_id=luot.id)
        if cuoi is None or so == cuoi:
            return []
        if so > cuoi:
            return [f"Xe chạy ngoài sổ {so - cuoi} km kể từ lượt trước (số cuối đã ghi {cuoi})."]
        return [f"Số đồng hồ {so} nhỏ hơn số cuối đã ghi của xe ({cuoi}) — kiểm lại."]

    def goi_y_xuat_phat(self, luot) -> int | None:
        return self.deliveries.so_dong_ho_cuoi_cua_xe(luot.vehicle_id, bo_qua_luot_id=luot.id)

    def luot_cua_trip(self, trip) -> dict | None:
        """Lượt xe nhìn từ MỘT chuyến — bảng chuyến đọc để biết hiện nút nào (None = ngoài lượt)."""
        diem = self.deliveries.diem_cua_trip(trip.id)
        if diem is None:
            return None
        luot = self.deliveries.get_luot(diem.luot_xe_id)
        if luot is None:
            return None
        trips = [self.deliveries.get_trip(d.delivery_trip_id) for d in luot.diem]
        so_da_ghi = [(int(d.so_dong_ho), d.delivery_trip_id) for d in luot.diem
                     if d.so_dong_ho is not None]
        cuoi = max(so_da_ghi)[1] if so_da_ghi else None
        gan_nhat = max([s for s, _ in so_da_ghi]
                       + ([int(luot.so_dong_ho_xuat_phat)]
                          if luot.so_dong_ho_xuat_phat is not None else []), default=None)
        con_chua_xong = any(t is not None and t.trang_thai in _CHUA_KET_QUA for t in trips)
        return {
            "id": luot.id, "code": luot.code, "vehicle_id": luot.vehicle_id, "ngay": luot.ngay,
            "so_diem": len(luot.diem),
            "so_dong_ho_xuat_phat": luot.so_dong_ho_xuat_phat,
            "so_dong_ho_ve_kho": luot.so_dong_ho_ve_kho,
            "ve_kho_luc": luot.ve_kho_luc, "km_ve_kho": luot.km_ve_kho,
            "so_dong_ho": diem.so_dong_ho,
            "so_dong_ho_gan_nhat": gan_nhat,
            "goi_y_xuat_phat": (self.goi_y_xuat_phat(luot)
                                if luot.so_dong_ho_xuat_phat is None else None),
            "cho_ve_kho": (luot.ve_kho_luc is None and bool(so_da_ghi) and not con_chua_xong),
            "la_diem_cuoi": cuoi == trip.id,
        }

    def ve_kho(self, luot_id, *, so_dong_ho, actor, scope=None, xac_nhan_km_lon=False) -> dict:
        """Ghi số đồng hồ VỀ KHO ⇒ đóng lượt, tính chặng về kho (PRD khoán km §14)."""
        luot = self.deliveries.get_luot(int(luot_id))
        if luot is None:
            raise DeliveryNotFound("Không tìm thấy lượt xe")
        trips = self._chan_ngoai_pham_vi_luot(luot, scope=scope, actor=actor)
        if luot.ve_kho_luc is not None:
            raise DeliveryError(f"Lượt {luot.code} đã về kho rồi.")
        if luot.so_dong_ho_xuat_phat is None:
            raise DeliveryError(f"Lượt {luot.code} chưa có số đồng hồ lúc xuất phát.")
        con = [t for t in trips if t.trang_thai in _CHUA_KET_QUA]
        if con:
            raise DeliveryError(
                f"Còn {len(con)} điểm chưa nhập kết quả — nhập xong mới về kho được.")
        so_diem = [int(d.so_dong_ho) for d in luot.diem if d.so_dong_ho is not None]
        if not so_diem:
            raise DeliveryError(f"Lượt {luot.code} chưa có điểm giao nào có số đồng hồ.")
        if so_dong_ho is None:
            raise DeliveryError("Phải nhập số đồng hồ lúc về kho")
        so, cuoi = int(so_dong_ho), max(so_diem)
        if so < cuoi:
            raise DeliveryError(
                f"Số đồng hồ về kho ({so}) nhỏ hơn số ở điểm giao cuối ({cuoi}).")
        if so - cuoi > KM_CANH_BAO and not xac_nhan_km_lon:
            raise DeliveryError(
                f"Chặng về kho {so - cuoi} km lớn bất thường (> {KM_CANH_BAO}). Xác nhận lại nếu đúng.")
        luot.so_dong_ho_ve_kho = so
        luot.ve_kho_luc = _utcnow()
        self._tinh_lai_luot(luot)
        return {"luot": luot, "canh_bao": []}

    # -- Gom theo lượt: MỘT lần bấm cho cả lượt ---------------------------------------------
    # Chủ chốt 18/09/2026: "gom nhiều phiếu lại chạy 1 lượt" — MỖI yêu cầu vẫn MỘT chuyến, MỘT
    # phiếu xuất kho, MỘT kết cục; lượt chỉ gom ĐƯỜNG ĐI. Các hàm dưới gọi lại đúng hàm của từng
    # chuyến nên mọi luật cũ áp y hệt. Tất cả hoặc không gì: một chuyến hỏng là ném lỗi, router
    # không commit, cả lô không lưu — lưu nửa lô thì người bấm phải tự dò cái nào đã qua.
    def len_luot(self, *, request_ids, employee_id, vehicle_id, gio_lay_hang, gio_du_kien_giao,
                 actor, luot_xe_id=LUOT_MOI, phu_xe_employee_id=None, ghi_chu_phan_cong=None,
                 scope=None) -> dict:
        """Lên đơn NHIỀU yêu cầu giao vào MỘT lượt xe (lượt mới hoặc lượt đang mở của xe đó)."""
        ids = list(dict.fromkeys(int(x) for x in (request_ids or [])))
        if not ids:
            raise DeliveryError("Chọn ít nhất một yêu cầu giao")
        if vehicle_id in (None, "", 0):
            raise DeliveryError("Chọn xe — lượt là vòng chạy của một chiếc xe.")
        luot = LUOT_MOI if luot_xe_id in (None, "") else luot_xe_id
        trips, canh_bao = [], []
        for rid in ids:
            try:
                kq = self.len_ke_hoach(
                    request_id=rid, employee_id=employee_id, gio_lay_hang=gio_lay_hang,
                    gio_du_kien_giao=gio_du_kien_giao, actor=actor, scope=scope,
                    phu_xe_employee_id=phu_xe_employee_id, vehicle_id=vehicle_id,
                    ghi_chu_phan_cong=ghi_chu_phan_cong, luot_xe_id=luot, bao=False,
                )
            except DeliveryError as e:
                # Nói RÕ yêu cầu nào hỏng — cả lô bị bỏ, người bấm cần biết gỡ cái nào ra.
                req = self.deliveries.get_request(rid)
                raise type(e)(f"Yêu cầu {getattr(req, 'code', None) or f'#{rid}'}: {e}") from e
            trips.append(kq["trip"])
            canh_bao += kq["canh_bao"]
            # Chuyến đầu mở lượt MỚI ⇒ các chuyến sau ghép vào CHÍNH lượt đó (và nhờ vậy không bị
            # tính trùng giờ với nhau — `len_ke_hoach` bỏ qua các chuyến cùng lượt).
            luot = self.deliveries.diem_cua_trip(kq["trip"].id).luot_xe_id
        luot_obj = self.deliveries.get_luot(int(luot))
        self.bao_tai_xe(trips[0], f"Bạn được phân lượt {luot_obj.code} — {len(trips)} điểm giao.",
                        viec="phan_chuyen")
        return {"luot": luot_obj, "trips": trips, "canh_bao": list(dict.fromkeys(canh_bao))}

    def _lay_luot(self, luot_id):
        luot = self.deliveries.get_luot(int(luot_id))
        if luot is None:
            raise DeliveryNotFound("Không tìm thấy lượt xe")
        return luot

    def _trips_luot_duoc_lam(self, luot, *, scope, actor) -> list:
        """Chuyến của lượt mà người gọi được THAO TÁC, theo thứ tự xếp vào lượt. Chuyến ngoài phạm
        vi thì bỏ qua (không chặn cả lượt); không còn chuyến nào thì 403."""
        ra = []
        for d in luot.diem:
            t = self.deliveries.get_trip(d.delivery_trip_id)
            if t is None:
                continue
            try:
                self.chan_ngoai_pham_vi_trip(t, scope=scope, actor=actor)
            except DeliveryForbidden:
                continue
            ra.append(t)
        if not ra:
            raise DeliveryForbidden("Bạn không có quyền với lượt xe này")
        return ra

    def gui_xuat_kho_ca_luot(self, luot_id, *, actor, scope=None, ghi_chu=None) -> list:
        """Gửi yêu cầu xuất kho cho mọi chuyến của lượt còn chờ gửi — MỖI chuyến MỘT phiếu. Ghi chú
        mỗi phiếu mang mã lượt để kho biết những phiếu nào lên cùng một xe.

        Phiếu tạo với `commit=False` ⇒ NGƯỜI GỌI commit rồi gọi `stock_requests.thong_bao_yeu_cau_moi`
        cho từng phiếu (router làm việc đó)."""
        luot = self._lay_luot(luot_id)
        can = [t for t in self._trips_luot_duoc_lam(luot, scope=scope, actor=actor)
               if t.trang_thai == LG_DA_LEN_KE_HOACH and self.yeu_cau_kho_cua_trip(t.id) is None]
        if not can:
            raise DeliveryError(f"Lượt {luot.code} không còn chuyến nào chờ gửi yêu cầu xuất kho.")
        phieu = []
        for t in can:
            gc = f"Giao khách — lượt {luot.code}, chuyến {t.request_id}/lần {t.lan_thu}"
            phieu.append(self.gui_yeu_cau_xuat_kho(
                t.id, actor=actor, kho_id=None, scope=scope, bao=False, commit_kho=False,
                ghi_chu=f"{gc} · {ghi_chu.strip()}" if (ghi_chu or "").strip() else gc,
            ))
        self.bao_tai_xe(can[0], f"Đã gửi {len(phieu)} yêu cầu xuất kho cho lượt {luot.code} — "
                                "chờ kho soạn hàng.", viec="gui_kho")
        return phieu

    def da_lay_hang_ca_luot(self, luot_id, *, actor, scope=None) -> list:
        luot = self._lay_luot(luot_id)
        can = [t for t in self._trips_luot_duoc_lam(luot, scope=scope, actor=actor)
               if t.trang_thai == LG_DANG_CHUAN_BI]
        if not can:
            raise DeliveryError(f"Lượt {luot.code} không có chuyến nào đang chờ lấy hàng.")
        for t in can:
            self.da_lay_hang(t.id, actor=actor, scope=scope)
        return can

    def bat_dau_giao_ca_luot(self, luot_id, *, actor, scope=None, so_dong_ho_xuat_phat=None) -> dict:
        """Xe rời kho với mọi chuyến ĐÃ LẤY HÀNG của lượt; số đồng hồ xuất phát ghi MỘT lần.

        Chuyến chưa lấy hàng thì để lại (không chặn) nhưng NHẮC: xe đi rồi mà còn đơn chưa lên xe
        là chuyện người lên đơn phải biết — hoặc huỷ khỏi lượt, hoặc đơn đó đi lượt sau."""
        luot = self._lay_luot(luot_id)
        trips = self._trips_luot_duoc_lam(luot, scope=scope, actor=actor)
        can = [t for t in trips if t.trang_thai == LG_DA_LAY_HANG]
        if not can:
            raise DeliveryError(f"Lượt {luot.code} không có chuyến nào đã lấy hàng để bắt đầu giao.")
        canh_bao: list[str] = []
        for t in can:
            canh_bao += self.bat_dau_giao(t.id, actor=actor, scope=scope,
                                          so_dong_ho_xuat_phat=so_dong_ho_xuat_phat)["canh_bao"]
        chua_lay = [t for t in trips if t.trang_thai in (LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI)]
        if chua_lay:
            canh_bao.append(f"Còn {len(chua_lay)} chuyến của lượt chưa lấy hàng — chưa bắt đầu giao.")
        return {"trips": can, "canh_bao": canh_bao}

    def chi_tiet_luot(self, luot_id, *, actor, scope=None) -> dict:
        """Cả lượt nhìn một chỗ: các điểm theo THỨ TỰ CHẶNG (số đồng hồ tăng dần; điểm chưa có số
        xếp cuối theo thứ tự xếp vào lượt) + số đếm để giao diện biết bày nút nào."""
        luot = self._lay_luot(luot_id)
        trips = {t.id: t for t in self._chan_ngoai_pham_vi_luot(luot, scope=scope, actor=actor)}
        diem = sorted(luot.diem, key=lambda d: (d.so_dong_ho is None, int(d.so_dong_ho or 0), d.id))
        ds = [trips[d.delivery_trip_id] for d in diem if d.delivery_trip_id in trips]
        co_so = {d.delivery_trip_id for d in diem if d.so_dong_ho is not None}

        def dem(tt) -> int:
            return sum(1 for t in ds if t.trang_thai == tt)

        so_da_ghi = [int(d.so_dong_ho) for d in diem if d.so_dong_ho is not None]
        return {
            "luot": luot,
            "trips": ds,
            "goi_y_xuat_phat": (self.goi_y_xuat_phat(luot)
                                if luot.so_dong_ho_xuat_phat is None else None),
            "so_dong_ho_gan_nhat": max(
                so_da_ghi + ([int(luot.so_dong_ho_xuat_phat)]
                             if luot.so_dong_ho_xuat_phat is not None else []), default=None),
            "cho_ve_kho": (luot.ve_kho_luc is None and bool(so_da_ghi)
                           and not any(t.trang_thai in _CHUA_KET_QUA for t in ds)),
            "so_cho_gui_kho": sum(1 for t in ds if t.trang_thai == LG_DA_LEN_KE_HOACH
                                  and self.yeu_cau_kho_cua_trip(t.id) is None),
            "so_cho_lay_hang": dem(LG_DANG_CHUAN_BI),
            "so_cho_bat_dau": dem(LG_DA_LAY_HANG),
            "so_dang_giao": dem(LG_DANG_GIAO),
            # Km chặng chỉ có nghĩa khi điểm đã có số đồng hồ; + chặng về kho.
            "tong_km": sum(int(t.km or 0) for t in ds if t.id in co_so) + int(luot.km_ve_kho or 0),
        }

    def _chuan_hoa_phu_xe(self, employee_id, phu_xe_employee_id):
        """Kiểm phụ xe và trả về id đã chuẩn hoá (None nếu không có).

        ⭐ Chặn xếp CÙNG MỘT NGƯỜI vào cả hai ô. Không chặn thì họ ăn `pct_tai_xe` + `pct_phu_xe`
        = 100% của chính chuyến đó — nhìn bảng lương không thấy gì bất thường, vì tổng vẫn đúng
        bằng tiền một chuyến. Chỉ có điều đáng ra phải chia cho hai người.
        """
        if phu_xe_employee_id in (None, "", 0):
            return None
        phu_xe_employee_id = int(phu_xe_employee_id)
        if phu_xe_employee_id == int(employee_id):
            raise DeliveryError("Tài xế và phụ xe không được là cùng một người")
        if self.employees.get_by_id(phu_xe_employee_id) is None:
            raise DeliveryNotFound("Không tìm thấy nhân viên phụ xe")
        return phu_xe_employee_id

    def kiem_lich_kip_xe(self, *, employee_id, phu_xe_employee_id, gio_lay_hang,
                         gio_du_kien_giao, bo_qua_trip_id=None, bo_qua_luot_id=None) -> list[str]:
        """Kiểm trùng lịch cho CẢ KÍP, không riêng tài xế.

        ⭐ Phụ xe cũng là một con người: không mở rộng vế này thì một người làm phụ xe hai chuyến
        cùng giờ vẫn lọt, mà kíp xe là thứ SINH RA TIỀN — trùng lịch nghĩa là trả tiền hai chuyến
        cho một khoảng thời gian.
        """
        canh_bao = list(self.kiem_lich_tai_xe(
            employee_id=employee_id, gio_lay_hang=gio_lay_hang,
            gio_du_kien_giao=gio_du_kien_giao, bo_qua_trip_id=bo_qua_trip_id,
            bo_qua_luot_id=bo_qua_luot_id,
        ))
        if phu_xe_employee_id:
            canh_bao += [
                f"Phụ xe: {c}" for c in self.kiem_lich_tai_xe(
                    employee_id=phu_xe_employee_id, gio_lay_hang=gio_lay_hang,
                    gio_du_kien_giao=gio_du_kien_giao, bo_qua_trip_id=bo_qua_trip_id,
                    nhan="Phụ xe", bo_qua_luot_id=bo_qua_luot_id,
                )
            ]
        return canh_bao

    def kiem_lich_tai_xe(self, *, employee_id, gio_lay_hang, gio_du_kien_giao,
                         bo_qua_trip_id=None, nhan="Tài xế", bo_qua_luot_id=None) -> list[str]:
        """CHẶN nếu trùng; trả về danh sách CẢNH BÁO nếu chỉ sát giờ (PRD §6)."""
        if gio_du_kien_giao <= gio_lay_hang:
            raise DeliveryError("Giờ dự kiến giao phải sau giờ lấy hàng")
        # ⚠️ KHÔNG kiểm "giờ quá khứ" ở đây. Hàm này dùng chung cho cả LÊN và ĐỔI kế hoạch,
        # và lúc đổi nó nhận giờ ĐÃ GỘP (`moi_lay` = giờ cũ nếu người dùng không gửi giờ mới).
        # Kiểm ở đây là chuyến xếp từ hôm qua không đổi nổi tài xế — chặn oan đúng thao tác
        # vô hại nhất. Chỗ kiểm đúng là `len_ke_hoach` / `doi_ke_hoach`, trên giá trị NGƯỜI
        # DÙNG VỪA GỬI. (Đã cắn 20/08/2026.)
        trung = self.deliveries.trung_lich(
            employee_id=employee_id, bat_dau=gio_lay_hang, ket_thuc=gio_du_kien_giao,
            bo_qua_trip_id=bo_qua_trip_id, bo_qua_luot_id=bo_qua_luot_id,
        )
        if trung:
            ma = ", ".join(f"#{t.id}" for t in trung)
            # `nhan` để câu báo chỉ ĐÚNG NGƯỜI: hàm này nay dùng cho cả phụ xe, mà báo
            # "Tài xế đã có chuyến trùng giờ" khi kẹt phụ xe là cử người đi sửa nhầm ô.
            raise DeliveryError(f"{nhan} đã có chuyến trùng giờ: {ma}")
        # Sát giờ = không trùng nhưng đệm dưới 30 phút ⇒ cho lưu, chỉ nhắc.
        ke = self.deliveries.trung_lich(
            employee_id=employee_id,
            bat_dau=gio_lay_hang - DEM_SAT_GIO,
            ket_thuc=gio_du_kien_giao + DEM_SAT_GIO,
            bo_qua_trip_id=bo_qua_trip_id, bo_qua_luot_id=bo_qua_luot_id,
        )
        if ke:
            return [f"Tài xế có chuyến khác cách dưới {int(DEM_SAT_GIO.total_seconds() // 60)} phút"]
        return []

    def len_ke_hoach(self, *, request_id, employee_id, gio_lay_hang, gio_du_kien_giao,
                     actor, kho_id=None, ghi_chu_phan_cong=None, scope=None,
                     phu_xe_employee_id=None, vehicle_id=None, luot_xe_id=None,
                     bao: bool = True) -> dict:
        """`bao=False`: không đẩy tin cho tài xế — `len_luot` gọi hàm này N lần rồi báo MỘT tin cho
        cả lượt, thay vì N cái toast cùng lúc."""
        req = self.deliveries.get_request(request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        self.chan_ngoai_pham_vi_yeu_cau(req, scope=scope, actor=actor)
        if req.trang_thai == YC_DA_HUY:
            raise DeliveryError("Yêu cầu đã huỷ, không lên kế hoạch được")
        # MỘT YÊU CẦU = MỘT CHUYẾN (chủ chốt 22/08/2026, PRD `prd-giao-hang-mot-yeu-cau-mot-chuyen`).
        # Trước đây chỉ chặn chuyến ĐANG CHẠY, tức chuyến hỏng xong là xếp tiếp được chuyến thứ hai
        # trong cùng yêu cầu. Nay muốn giao lại thì lập YÊU CẦU MỚI — một yêu cầu chỉ có một kết cục.
        cu = self.deliveries.trips_cua_yeu_cau(request_id)
        if cu:
            raise DeliveryError(
                "Yêu cầu này đã có chuyến giao. Muốn giao lại thì lập yêu cầu giao mới."
            )
        if self.trang_thai_yeu_cau(req) == YC_DA_GIAO_DU:
            raise DeliveryError("Yêu cầu đã giao đủ")
        if self.employees.get_by_id(employee_id) is None:
            raise DeliveryNotFound("Không tìm thấy nhân viên giao hàng")
        phu_xe_employee_id = self._chuan_hoa_phu_xe(employee_id, phu_xe_employee_id)
        vehicle_id = self._chuan_hoa_xe(vehicle_id)
        self._doi_xe(employee_id, vehicle_id)

        self._chan_gio_qua_khu(gio_lay_hang, "Giờ lấy hàng")
        self._chan_gio_qua_khu(gio_du_kien_giao, "Giờ dự kiến giao")
        # Ghép vào lượt đang mở ⇒ các chuyến CÙNG lượt không tính là trùng giờ (gom đơn một vòng).
        cung_luot = (int(luot_xe_id) if luot_xe_id not in (None, "")
                     and str(luot_xe_id) != LUOT_MOI else None)
        canh_bao = self.kiem_lich_kip_xe(
            employee_id=employee_id, phu_xe_employee_id=phu_xe_employee_id,
            gio_lay_hang=gio_lay_hang, gio_du_kien_giao=gio_du_kien_giao,
            bo_qua_luot_id=cung_luot,
        )

        # (đẩy realtime sau khi có `trip` — xem cuối hàm)
        trip = self.deliveries.create_trip(
            request_id=request_id,
            lan_thu=self.deliveries.lan_thu_ke_tiep(request_id),
            employee_id=employee_id,
            phu_xe_employee_id=phu_xe_employee_id,
            vehicle_id=vehicle_id,
            gio_lay_hang=gio_lay_hang,
            gio_du_kien_giao=gio_du_kien_giao,
            ghi_chu_phan_cong=ghi_chu_phan_cong,
            trang_thai=LG_DA_LEN_KE_HOACH,
            created_by=getattr(actor, "id", None),
        )
        self.deliveries.ghi_lich_su(
            trip_id=trip.id, tu_trang_thai=None, den_trang_thai=LG_DA_LEN_KE_HOACH,
            nguoi_thao_tac_id=getattr(actor, "id", None), ghi_chu=ghi_chu_phan_cong,
        )
        # Lượt xe (PRD khoán km §14): người lên đơn xếp chuyến vào lượt mới hoặc lượt đang mở.
        self._xep_vao_luot(trip, luot_xe_id=luot_xe_id, actor=actor)
        # KHÔNG tự sinh đề nghị xuất hàng ở đây — quản lý bấm tay ở bước sau (luật 6).
        if bao:
            self.bao_tai_xe(trip, "Bạn được phân một chuyến giao mới.", viec="phan_chuyen")
        return {"trip": trip, "canh_bao": canh_bao}

    def yeu_cau_kho_cua_trip(self, trip_id: int):
        """Yêu cầu XUẤT kho còn sống của chuyến (None nếu chưa gửi hoặc đã huỷ)."""
        if self.stock_requests is None:
            return None
        return self.stock_requests.requests.tim_theo_delivery_trip(trip_id, loai="XUAT")

    def yeu_cau_tra_hang_cua_trip(self, trip_id: int):
        """Yêu cầu NHẬP kho (trả hàng về) của chuyến — None nếu chưa trả."""
        if self.stock_requests is None:
            return None
        return self.stock_requests.requests.tim_theo_delivery_trip(trip_id, loai="NHAP")

    def bao_tai_xe(self, trip, message: str, *, viec: str) -> None:
        """Đẩy REAL-TIME tới tài xế của chuyến (CLAUDE.md: gửi nội bộ phải tức thì).

        Tài xế không ngồi canh màn hình — họ đang ở kho hoặc trên đường. Bắt họ F5 để biết
        "kho soạn xong chưa" là bắt đoán, mà đoán sai thì hoặc đi sớm ngồi chờ, hoặc đi muộn.

        Im lặng khi không tìm được tài khoản: tài xế có thể chưa được cấp login (hồ sơ nhân sự
        có trước tài khoản). Ném lỗi ở đây là chặn cả thao tác nghiệp vụ chỉ vì không gửi được
        một cái toast.
        """
        emp = self.employees.get_by_id(getattr(trip, "employee_id", None) or 0)
        uid = getattr(emp, "user_id", None)
        if not uid:
            return
        req = self.deliveries.get_request(trip.request_id)
        hub.publish(int(uid), {
            "type": "giao_hang_chuyen",
            "viec": viec,
            "trip_id": trip.id,
            "request_code": getattr(req, "code", None),
            "khach": getattr(req, "customer_name", None),
            "message": message,
        })

    def thong_ke_thang(self, employee_id: int, *, ngay: date | None = None) -> dict:
        """Số chuyến hoàn thành + tổng km trong THÁNG chứa `ngay` (tab Nhân viên giao hàng).

        Khác `thong_ke_ngay` ở đúng một chỗ: khung thời gian. Tách hàm chứ không thêm cờ vào hàm
        kia — hai câu hỏi khác nhau ("hôm nay tài xế này chạy bao nhiêu" để điều độ, "tháng này
        bao nhiêu" để theo dõi), và gộp thành một hàm có cờ thì nơi gọi phải nhớ cờ nghĩa là gì.
        """
        ngay = ngay or date.today()
        xong, tong_km = 0, 0
        for t in self.deliveries.list_trips(employee_ids=[employee_id]):
            ket = t.thoi_gian_ket_thuc
            if ket is None or (ket.year, ket.month) != (ngay.year, ngay.month):
                continue
            if t.trang_thai in LAN_GIAO_CO_HANG_DEN_TAY:
                xong += 1
            tong_km += int(t.km or 0)
        # Chặng về kho của lượt xe (PRD khoán km §14) không nằm trong km chuyến nào.
        tong_km += sum(km for luc, km in self.deliveries.ve_kho_cua_tai_xe(employee_id)
                       if (luc.year, luc.month) == (ngay.year, ngay.month))
        return {"so_chuyen_xong": xong, "tong_km": tong_km}

    def kho_da_lap_phieu(self, trip_id: int) -> bool:
        """Kho đã LẬP PHIẾU cho chuyến này chưa ⇒ "Kho đã chuẩn bị xong" (chủ chốt 20/08/2026).

        SUY RA, không phải trạng thái lưu sẵn — cùng luật với "đã giao = tổng số thực nhận": kho
        thao tác trên màn của HỌ, không ai bấm gì trên màn Giao hàng, nên một cột lưu ở đây sớm
        muộn lệch với sổ kho.

        Mốc là **lập phiếu**, KHÔNG phải ghi sổ: lập phiếu nghĩa là kho đã soạn hàng và viết
        chứng từ — tài xế tới lấy được. Ghi sổ (`REQ_DONE`) chỉ đến sau khi hàng đã ra khỏi kho,
        lúc đó thì muộn rồi.

        Phiếu đã HUỶ không tính — huỷ là quay về chưa chuẩn bị.

        Đọc qua repo giao hàng chứ không qua service kho: tiến độ đơn dựng service KHÔNG kèm kho,
        đi đường kia thì drawer đơn luôn báo "đang chuẩn bị" trong khi màn Giao hàng báo "xong".
        """
        yc = self.deliveries.yeu_cau_kho_cua_chuyen(trip_id, "XUAT")
        if yc is None:
            return False
        from ..models.stock_voucher import VOUCHER_CANCELLED, StockVoucher

        return self.deliveries.db.query(
            StockVoucher.id
        ).filter(
            StockVoucher.request_id == yc.id,
            StockVoucher.trang_thai != VOUCHER_CANCELLED,
        ).first() is not None

    def hang_can_xuat(self, trip) -> list[dict]:
        """Dòng xuất kho SUY RA từ yêu cầu giao — không ai gõ tay.

        = mặt hàng + đơn vị đã khai trên dòng yêu cầu, số lượng = phần CÒN PHẢI GIAO của chính
        yêu cầu đó (trừ các lần giao trước). Yêu cầu đã nói rõ giao cái gì bao nhiêu; bắt gõ lại
        ở bước xuất kho là mời gõ sai, mà sai thì kho xuất nhầm hàng.
        """
        req = self.deliveries.get_request(trip.request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        da_giao = self.deliveries.da_giao_cua_yeu_cau(req.id)
        theo_sau = self._dong_theo_sau_cum(req)
        ra: list[dict] = []
        for ln in req.lines:
            con = int(ln.qty) - int(da_giao.get(ln.order_line_id, 0))
            if con <= 0 or ln.order_line_id in theo_sau:
                continue
            if not ln.hang_loai or ln.hang_id is None or not ln.dvt:
                raise DeliveryError(
                    "Dòng hàng chưa khai mặt hàng kho — sửa yêu cầu giao và chọn mặt hàng trong "
                    "danh mục Giấy / Vật tư khác trước khi gửi kho."
                )
            ra.append({"hang_loai": ln.hang_loai, "hang_id": ln.hang_id,
                       "dvt": ln.dvt, "sl_de_nghi": con})
        if not ra:
            raise DeliveryError("Không còn hàng nào phải xuất cho chuyến này")
        return ra

    def _dong_theo_sau_cum(self, req) -> set[int]:
        """`order_line_id` các dòng THEO SAU trong cụm bán mà dòng đầu cụm có mặt trên yêu cầu.

        Những dòng này không xuất kho riêng (dòng đầu đã mang mã cả cụm). Dòng trống mặt hàng mà
        KHÔNG thuộc cụm nào vẫn phải báo lỗi như cũ, nên không lọc bừa theo `hang_id is None`.
        """
        order = self.orders.get_by_id(req.order_id)
        if order is None:
            return set()
        tren_yc = {ln.order_line_id for ln in req.lines if ln.hang_id is not None}
        ra: set[int] = set()
        for cum in cum_ban(order):
            if len(cum.dong) > 1 and cum.dong_dau.id in tren_yc:
                ra.update(od.id for od in cum.dong[1:])
        return ra

    def gui_yeu_cau_xuat_kho(self, trip_id, *, actor, kho_id, scope=None,
                             ngay_can=None, ghi_chu=None, bao: bool = True,
                             commit_kho: bool = True):
        """Gửi YÊU CẦU XUẤT KHO thật cho chuyến — không phải chứng từ riêng của Giao hàng.

        Gọi thẳng `StockRequestService.create()`: mọi luật của kho (mặt hàng phải có trong danh
        mục Giấy / Vật tư khác, đơn vị phải đổi được về đơn vị gốc, tạo là duyệt luôn) áp cho
        giao hàng y hệt mọi bộ phận khác — miễn phí, và không sửa gì bên kho.

        Dòng hàng KHÔNG nhận từ ngoài — suy ra từ chính yêu cầu giao (`hang_can_xuat`). Người
        gửi chỉ chọn KHO. Yêu cầu đã nói giao cái gì bao nhiêu, nên xuất kho phải khớp y hệt;
        cho gõ lại là mở đường cho lệch số và xuất nhầm hàng (chủ chốt 19/08/2026).
        """
        if self.stock_requests is None:
            raise DeliveryError("Chưa nối được service kho")
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DA_LEN_KE_HOACH:
            raise DeliveryError("Chỉ gửi yêu cầu xuất kho cho chuyến vừa lên kế hoạch")
        dang_co = self.yeu_cau_kho_cua_trip(trip.id)
        if dang_co is not None:
            raise DeliveryError(f"Chuyến này đã có yêu cầu xuất kho {dang_co.ma}")

        lines = self.hang_can_xuat(trip)
        self._chan_thieu_ton(lines, kho_id)
        req = self.stock_requests.create(
            user=actor,
            loai="XUAT",
            lines=lines,
            kho_id=kho_id,
            # Kho xếp thứ tự soạn theo cột "Cần ngày" — với giao khách nó chính là ngày tài xế
            # tới lấy, nên bơm đúng số đó vào chứ không để trống.
            ngay_can=ngay_can or trip.gio_lay_hang.date(),
            ghi_chu=ghi_chu or f"Giao khách — chuyến {trip.request_id}/lần {trip.lan_thu}",
            delivery_trip_id=trip.id,
            # `commit_kho=False` (gửi CẢ LƯỢT): kho mặc định tự commit từng phiếu — phiếu thứ ba
            # hỏng là hai phiếu đầu đã nằm sổ. Tắt đi để cả lượt là MỘT giao dịch; người gọi tự đẩy
            # tin cho kho SAU commit (`thong_bao_yeu_cau_moi`).
            commit=commit_kho,
        )
        # Kho đã nhận việc ⇒ chuyến sang "Kho đang chuẩn bị". Không có bước duyệt nào ở giữa:
        # `create()` của họ duyệt luôn (bỏ bước duyệt 06/08/2026).
        self._doi_trang_thai(trip, LG_DANG_CHUAN_BI, actor=actor,
                             ghi_chu=f"Yêu cầu xuất kho {req.ma}")
        if bao:
            self.bao_tai_xe(trip, f"Đã gửi yêu cầu xuất kho {req.ma} — chờ kho soạn hàng.",
                            viec="gui_kho")
        return req

    def _chan_thieu_ton(self, lines: list[dict], kho_id) -> None:
        """Kiểm lại TỒN THẬT ở kho được chọn lúc gửi xuất (19/09/2026). Lúc lập yêu cầu hàng đã có,
        nhưng từ đó tới lúc xếp chuyến kho có thể đã xuất cho việc khác — gửi yêu cầu xuất mà kho
        không có hàng là để thủ kho và tài xế tự phát hiện ở cửa kho."""
        from ..repositories.stock_lot_repo import StockLotRepository
        from ..models.vat_lieu_kho import VatTuInAn

        ton = StockLotRepository(self.deliveries.db).on_hand_by_kho(
            [(ln["hang_loai"], ln["hang_id"]) for ln in lines])
        for ln in lines:
            theo_kho = ton.get((ln["hang_loai"], ln["hang_id"]), {})
            # Kho để trống (thủ kho chọn kho lúc lập phiếu) ⇒ so với tổng mọi kho.
            co = (float(theo_kho.get(int(kho_id), 0.0)) if kho_id is not None
                  else float(sum(theo_kho.values())))
            if co + 1e-9 < float(ln["sl_de_nghi"]):
                h = self.deliveries.db.get(VatTuInAn, ln["hang_id"]) if ln["hang_loai"] == "vat_tu" else None
                ten = getattr(h, "ten", None) or f"mặt hàng #{ln['hang_id']}"
                raise DeliveryError(
                    f"Kho chỉ còn {co:g} «{ten}», chuyến cần {float(ln['sl_de_nghi']):g}. "
                    "Chọn kho khác hoặc chờ nhập kho thêm.")

    def doi_ke_hoach(self, trip_id, *, actor, scope=None, employee_id=None,
                     gio_lay_hang=None, gio_du_kien_giao=None, ghi_chu_phan_cong=None,
                     phu_xe_employee_id=_KHONG_GUI, vehicle_id=_KHONG_GUI) -> dict:
        """Đổi người / đổi giờ khi tài xế CHƯA cầm hàng.

        Đã gửi yêu cầu xuất kho mà đổi giờ thì CẢNH BÁO, không tự huỷ phiếu bên kho — đó là
        chứng từ của họ, huỷ hộ là đụng sổ sách bên đó (nghiệm thu #15).
        """
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai not in LAN_GIAO_SUA_DUOC:
            raise DeliveryError("Tài xế đã nhận hàng — không đổi kế hoạch được nữa")

        # CHỈ kiểm giờ NGƯỜI DÙNG VỪA GỬI LÊN, không kiểm giờ cũ của chuyến: chuyến xếp từ hôm
        # qua mà nay chỉ đổi tài xế thì giờ cũ đã thành quá khứ — kiểm cả cụm là chặn oan đúng
        # thao tác vô hại nhất.
        self._chan_gio_qua_khu(gio_lay_hang, "Giờ lấy hàng")
        self._chan_gio_qua_khu(gio_du_kien_giao, "Giờ dự kiến giao")

        moi_nv = employee_id if employee_id is not None else trip.employee_id
        moi_lay = gio_lay_hang if gio_lay_hang is not None else trip.gio_lay_hang
        moi_giao = gio_du_kien_giao if gio_du_kien_giao is not None else trip.gio_du_kien_giao
        # `_KHONG_GUI` chứ không phải `None`: người dùng GỠ phụ xe cũng gửi `None` lên. Lấy `None`
        # làm "không gửi" thì không có đường nào gỡ được phụ xe đã xếp.
        moi_phu = (trip.phu_xe_employee_id if phu_xe_employee_id is _KHONG_GUI
                   else self._chuan_hoa_phu_xe(moi_nv, phu_xe_employee_id))
        # `_KHONG_GUI` y như phụ xe: gỡ xe đã xếp cũng gửi `None` lên.
        moi_xe = (trip.vehicle_id if vehicle_id is _KHONG_GUI
                  else self._chuan_hoa_xe(vehicle_id))
        diem = self.deliveries.diem_cua_trip(trip.id)
        if diem is not None and moi_xe != trip.vehicle_id:
            # Chuyến trong lượt ăn số đồng hồ của XE lượt — đổi xe riêng một chuyến là trừ số
            # đồng hồ xe này cho số xe kia.
            luot = self.deliveries.get_luot(diem.luot_xe_id)
            raise DeliveryError(
                f"Chuyến thuộc lượt {getattr(luot, 'code', '')} — không đổi xe riêng một chuyến. "
                "Huỷ kế hoạch rồi lên đơn lại vào lượt của xe kia.")
        self._doi_xe(moi_nv, moi_xe)
        if moi_phu is not None and moi_phu == moi_nv:
            # Đổi TÀI XẾ thành đúng người đang làm phụ xe — hai ô hoá ra một người mà mỗi ô kiểm
            # riêng thì không ai bắt được.
            raise DeliveryError("Tài xế và phụ xe không được là cùng một người")
        canh_bao = self.kiem_lich_kip_xe(
            employee_id=moi_nv, phu_xe_employee_id=moi_phu,
            gio_lay_hang=moi_lay, gio_du_kien_giao=moi_giao,
            bo_qua_trip_id=trip.id,
            bo_qua_luot_id=diem.luot_xe_id if diem is not None else None,
        )

        doi_gio = moi_lay != trip.gio_lay_hang
        # Đổi TÀI XẾ thì báo người MỚI. Người cũ không báo ở đây — họ chưa cầm hàng (điều kiện
        # đầu hàm), nên với họ chuyến này coi như chưa từng bắt đầu.
        doi_nguoi = moi_nv != trip.employee_id
        trip.employee_id = moi_nv
        trip.phu_xe_employee_id = moi_phu
        trip.vehicle_id = moi_xe
        trip.gio_lay_hang = moi_lay
        trip.gio_du_kien_giao = moi_giao
        if ghi_chu_phan_cong is not None:
            trip.ghi_chu_phan_cong = ghi_chu_phan_cong

        # Đã gửi yêu cầu xuất kho mà đổi giờ ⇒ CẢNH BÁO chứ không tự huỷ phiếu của kho.
        # Yêu cầu kho là chứng từ của HỌ; huỷ hộ là đụng vào sổ sách bên đó. Quản lý tự vào màn
        # Kho huỷ nếu cần — đúng ranh giới.
        if doi_gio and self.yeu_cau_kho_cua_trip(trip.id) is not None:
            canh_bao.append(
                "Đã có yêu cầu xuất kho cho chuyến này — kho đang soạn theo giờ cũ. "
                "Báo kho hoặc huỷ yêu cầu bên màn Kho."
            )
        if doi_nguoi:
            self.bao_tai_xe(trip, "Bạn được phân một chuyến giao mới.", viec="phan_chuyen")
        elif doi_gio:
            self.bao_tai_xe(trip, "Chuyến của bạn vừa đổi giờ.", viec="doi_gio")
        return {"trip": trip, "canh_bao": canh_bao}

    def huy_ke_hoach(self, trip_id, *, ly_do, actor, scope=None) -> None:
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai not in LAN_GIAO_SUA_DUOC:
            raise DeliveryError("Tài xế đã nhận hàng — không huỷ kế hoạch được nữa")
        if not (ly_do or "").strip():
            raise DeliveryError("Phải nhập lý do huỷ kế hoạch")
        # Đề nghị xuất kho đã gửi thì huỷ theo — để sống là kho vẫn soạn và xuất hàng cho một
        # chuyến không còn. Kho đã lập phiếu (hàng đã soạn) thì kho phải tự huỷ phiếu trước.
        yc_kho = self.yeu_cau_kho_cua_trip(trip.id)
        if yc_kho is not None:
            if self.kho_da_lap_phieu(trip.id):
                raise DeliveryError(
                    "Kho đã lập phiếu xuất cho chuyến này — báo kho huỷ phiếu trước rồi mới huỷ chuyến")
            self.stock_requests.cancel_by_kho(yc_kho, f"Chuyến giao đã huỷ: {ly_do.strip()}")
        self._doi_trang_thai(trip, LG_DA_HUY, actor=actor, ly_do=ly_do.strip())
        # Chuyến huỷ thì xe không ghé điểm đó ⇒ rút khỏi lượt; lượt không còn điểm nào thì xoá.
        diem = self.deliveries.diem_cua_trip(trip.id)
        if diem is not None:
            luot = self.deliveries.get_luot(diem.luot_xe_id)
            self.deliveries.xoa_diem(diem)
            if luot is not None:
                self.deliveries.db.refresh(luot)
                if not luot.diem:
                    self.deliveries.xoa_luot(luot)

    # =====================================================================================
    # Kho — ba nút trong Hộp yêu cầu
    # =====================================================================================
    def da_lay_hang(self, trip_id, *, actor, scope=None):
        """TÀI XẾ tự bấm khi đã cầm được hàng ở kho.

        Trước đây do KHO bấm ("đã giao tài xế"). Đổi 19/08/2026: kho không thao tác gì trên màn
        Giao hàng, và người cầm hàng mới là người biết hàng đã ra khỏi kho — số liệu thật hơn.

        Vẫn đòi ĐÃ CÓ yêu cầu xuất kho: chưa có giấy thì hàng chưa ra được cửa kho, bấm ở đây là
        ghi một chuyện chưa xảy ra.
        """
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DANG_CHUAN_BI:
            raise DeliveryError("Kho chưa duyệt đề nghị xuất hàng cho chuyến này")
        self._doi_trang_thai(trip, LG_DA_LAY_HANG, actor=actor)
        return trip

    def bat_dau_giao(self, trip_id, *, actor, scope=None, so_dong_ho_xuat_phat=None):
        """Chuyến ĐẦU của một lượt xe phải kèm số đồng hồ lúc xuất phát (PRD khoán km §14) — chặng
        đầu tiên trừ từ số này. Các chuyến sau của cùng lượt không phải nhập lại."""
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DA_LAY_HANG:
            raise DeliveryError("Chưa lấy hàng thì chưa bắt đầu giao được")
        canh_bao: list[str] = []
        diem = self.deliveries.diem_cua_trip(trip.id)
        if diem is not None:
            luot = self.deliveries.get_luot(diem.luot_xe_id)
            if luot.so_dong_ho_xuat_phat is None:
                if so_dong_ho_xuat_phat is None:
                    raise DeliveryError(
                        f"Nhập số đồng hồ lúc xuất phát của lượt {luot.code} (xe đi khỏi kho).")
                so = int(so_dong_ho_xuat_phat)
                if so < 0:
                    raise DeliveryError("Số đồng hồ không được âm")
                canh_bao = self._canh_bao_xuat_phat(luot, so)
                luot.so_dong_ho_xuat_phat = so
        self._doi_trang_thai(trip, LG_DANG_GIAO, actor=actor)
        return {"trip": trip, "canh_bao": canh_bao}

    def _chuan_hoa_xe(self, vehicle_id):
        """Kiểm xe rồi trả id đã chuẩn hoá (None nếu bỏ trống).

        KHÔNG đòi `active`: xe vừa ngưng dùng vẫn phải ghi được kết quả cho chuyến nó đang chạy dở.
        Cờ `active` chỉ giấu xe khỏi ô chọn của chuyến MỚI.
        """
        if vehicle_id in (None, "", 0):
            return None
        vehicle_id = int(vehicle_id)
        if self.xe is None or self.xe.get(vehicle_id) is None:
            raise DeliveryNotFound("Không tìm thấy xe")
        return vehicle_id

    def _phai_khai_xe(self, employee_id) -> bool:
        """Chuyến của tài xế này có BẮT BUỘC khai xe không?

        Hai điều kiện, phải đủ cả hai:

        1. Danh mục Xe đã có xe còn dùng. ⭐ Luật TỰ BẬT theo dữ liệu, cố ý: đòi vô điều kiện thì
           ngày triển khai — lúc chưa ai kịp khai chiếc nào — không lên nổi một đơn giao hàng nào,
           tức chặn cả phân hệ vì một ô vừa mới sinh ra. Khai chiếc xe đầu tiên = bật luật.
        2. Tài xế thuộc khối Giao hàng (`_thuoc_khoi_giao_hang`). Ngoài khối đó thì chuyến không ra
           tiền khoán km (`_chup_don_gia_km` trả sớm), đòi xe là bắt khai một thứ không dùng vào
           việc gì.
        """
        if self.xe is None or not self.xe.co_xe_dang_dung():
            return False
        return self._thuoc_khoi_giao_hang(employee_id)

    def _thuoc_khoi_giao_hang(self, employee_id) -> bool:
        """Người này có thuộc khối Giao hàng không — MỘT câu hỏi, MỘT hàm (chủ chốt 14/09/2026).

        Hỏi thẳng `DepartmentRepository.dept_ids_giao_hang()` — CÙNG hàm với ô chọn tài xế và tab
        Nhân viên giao hàng. Trước đó chỗ này đọc cờ riêng của phòng còn ô chọn đi kế thừa theo
        cây: tài xế ở tổ con được phân chuyến bình thường mà không có tiền khoán km, không ai báo.
        """
        if self.departments is None:
            return False
        nv = self.employees.get_by_id(employee_id)
        dept_id = getattr(nv, "department_id", None) if nv is not None else None
        return bool(dept_id) and dept_id in self.departments.dept_ids_giao_hang()

    def _doi_xe(self, employee_id, vehicle_id) -> None:
        """Chặn nếu chuyến thuộc diện khoán km mà không nói nó chạy xe nào.

        Gọi ở CẢ BA cửa (chủ chốt 12/09/2026): **lên đơn giao hàng**, **đổi kế hoạch** (API
        `PUT /plans/{id}`) và **ghi kết quả**. Ban đầu
        chỉ chặn lúc ghi kết quả với lý do "đổi xe phút chót là chuyện thường" — nhưng như thế thì
        người phân chuyến bỏ trống được, và cái giá phải trả dồn hết sang người đóng chuyến, lúc
        đó mới biết chuyến nào thiếu. Chủ chốt: bắt buộc ngay từ lúc lên đơn. Đổi xe vẫn làm được
        bình thường qua *Đổi kế hoạch* và qua chính ô Xe ở màn ghi kết quả.

        Có xe rồi thì xe đó phải RA ĐƯỢC GIÁ (14/09/2026): chưa gán mức, hoặc mức chưa khai bậc
        nào, là chặn. Để lọt thì chuyến đóng xong âm thầm ăn đơn giá phẳng `departments.don_gia_km`
        — đúng cái lỗ "xe không mức ăn 3.600đ/km mà không màn nào hiện" vừa bịt ở danh mục Xe.
        Chỉ kiểm cho tài xế THUỘC khối Giao hàng: ngoài khối thì chuyến không ra tiền khoán km, mức
        của xe không dùng vào việc gì.
        """
        if vehicle_id is None:
            if self._phai_khai_xe(employee_id):
                raise DeliveryError(
                    "Phải chọn xe cho chuyến này (đơn giá khoán km tra theo mức của xe).")
            return
        if self.xe is None or not self._thuoc_khoi_giao_hang(employee_id):
            return
        x = self.xe.get(vehicle_id)
        if x is None:
            return   # `_chuan_hoa_xe` đã chặn xe không tồn tại
        muc = (self.muc_km.get(x.muc_khoan_km_id)
               if self.muc_km is not None and x.muc_khoan_km_id else None)
        if muc is None:
            raise DeliveryError(
                f"Xe {x.ma} chưa gán mức khoán km — gán mức cho xe ở danh mục Xe giao hàng trước.")
        if not self.muc_km.bac_cua(muc.id):
            raise DeliveryError(
                f"Mức “{muc.ten}” của xe {x.ma} chưa có bảng giá — khai bậc km ở "
                "Cấu hình lương › Khoán km giao hàng trước.")

    def ghi_ket_qua(self, trip_id, *, ket_qua, km, actor, scope=None,
                    thoi_gian_ket_thuc=None, nguoi_nhan_thuc_te=None, ly_do_that_bai=None,
                    huong_xu_ly=None, ghi_chu=None, so_thuc_nhan=None,
                    xac_nhan_km_lon=False, vehicle_id=None, so_dong_ho=None) -> dict:
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DANG_GIAO:
            raise DeliveryError("Chỉ ghi kết quả cho chuyến đang giao")
        # `hen_lai` đã gỡ khỏi danh sách hợp lệ (22/08/2026) — khai nó ⇒ báo lỗi, không âm thầm bỏ.
        if ket_qua not in (LG_THANH_CONG, LG_GIAO_THIEU, LG_THAT_BAI):
            raise DeliveryError("Kết quả không hợp lệ")

        canh_bao: list[str] = []
        # LƯỢT XE (PRD khoán km §14): chuyến trong lượt KHÔNG gõ km — tài xế ghi số đồng hồ lúc TỚI
        # khách, máy trừ ra km chặng. Chuyến ngoài lượt giữ nguyên đường cũ (một ô km).
        diem = self.deliveries.diem_cua_trip(trip.id)
        luot = self.deliveries.get_luot(diem.luot_xe_id) if diem is not None else None
        if luot is not None:
            if luot.so_dong_ho_xuat_phat is None:
                raise DeliveryError(
                    f"Lượt {luot.code} chưa có số đồng hồ lúc xuất phát — bấm Bắt đầu giao để nhập.")
            if so_dong_ho is None:
                raise DeliveryError("Phải nhập số đồng hồ lúc tới khách")
            so = int(so_dong_ho)
            if so < int(luot.so_dong_ho_xuat_phat):
                raise DeliveryError(
                    f"Số đồng hồ {so} nhỏ hơn số lúc xuất phát ({luot.so_dong_ho_xuat_phat}).")
            truoc = max([int(d.so_dong_ho) for d in luot.diem
                         if d.id != diem.id and d.so_dong_ho is not None and int(d.so_dong_ho) <= so]
                        + [int(luot.so_dong_ho_xuat_phat)])
            if so - truoc > KM_CANH_BAO and not xac_nhan_km_lon:
                raise DeliveryError(
                    f"Chặng {so - truoc} km lớn bất thường (> {KM_CANH_BAO}). Xác nhận lại nếu đúng.")
            if vehicle_id is not None and int(vehicle_id) != luot.vehicle_id:
                raise DeliveryError(
                    f"Chuyến thuộc lượt {luot.code} — xe của lượt, không đổi riêng một chuyến.")
            vehicle_id = None
            km = None
        else:
            if km is None:
                raise DeliveryError("Phải nhập số km thực tế")
            km = int(km)
            if km < 0:
                raise DeliveryError("Số km không được âm")
            if km > KM_CANH_BAO and not xac_nhan_km_lon:
                # KHÔNG chặn — chỉ bắt xác nhận lại. Lỗi hay gặp là gõ nhầm 180 thành 1800.
                raise DeliveryError(
                    f"Số km {km} lớn bất thường (> {KM_CANH_BAO}). Xác nhận lại nếu đúng."
                )

        req = self.deliveries.get_request(trip.request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")

        if ket_qua in (LG_THANH_CONG, LG_GIAO_THIEU):
            if not (nguoi_nhan_thuc_te or "").strip():
                raise DeliveryError("Phải nhập người nhận hàng")
            self._ghi_dong_thuc_nhan(trip, req, ket_qua=ket_qua, so_thuc_nhan=so_thuc_nhan)
        else:
            if not (ly_do_that_bai or "").strip():
                raise DeliveryError("Phải nhập lý do thất bại")
            if huong_xu_ly not in HUONG_XU_LY:
                raise DeliveryError("Phải chọn hướng xử lý hàng: trả về hoặc chờ giao lại")
            trip.ly_do_that_bai = ly_do_that_bai.strip()
            trip.huong_xu_ly = huong_xu_ly

        if vehicle_id is not None:
            trip.vehicle_id = self._chuan_hoa_xe(vehicle_id)
        self._doi_xe(trip.employee_id, trip.vehicle_id)
        if luot is not None:
            diem.so_dong_ho = int(so_dong_ho)
            # Số mới có thể chen GIỮA hai số cũ (ghi muộn một điểm) ⇒ tính lại cả lượt, không riêng
            # chặng này.
            self._tinh_lai_luot(luot)
        else:
            trip.km = km
            self._chup_don_gia_km(trip)
        trip.thoi_gian_ket_thuc = thoi_gian_ket_thuc or _utcnow()
        trip.nguoi_nhan_thuc_te = nguoi_nhan_thuc_te
        trip.ghi_chu_ket_qua = ghi_chu
        self._doi_trang_thai(trip, ket_qua, actor=actor, ly_do=ly_do_that_bai, ghi_chu=ghi_chu)

        # ⚠️ CHỈ ca THẤT BẠI mới đổi trạng thái sang "đang trả hàng". Ca GIAO THIẾU cũng phải trả
        # phần thừa về kho, nhưng KHÔNG được đổi trạng thái: `giao_thieu` là KẾT CỤC, mà mọi phép
        # cộng "đã giao" chỉ đếm chuyến ở `thanh_cong`/`giao_thieu`. Đẩy nó sang `dang_tra_hang`
        # là phần khách ĐÃ NHẬN biến mất khỏi sổ — thử rồi, test #08b đỏ ngay với `da_giao = 0`.
        # Ca giao thiếu nhận lại hàng thẳng từ trạng thái `giao_thieu` (xem `kho_nhan_lai_hang`).
        if ket_qua == LG_THAT_BAI and huong_xu_ly == XU_LY_TRA_VE:
            self._doi_trang_thai(trip, LG_DANG_TRA_HANG, actor=actor)
        # Hàng không tới tay khách ⇒ máy TỰ lập yêu cầu NHẬP trả về ngay (19/09/2026). Người xác
        # nhận "kho đã nhận lại" là THỦ KHO — bằng phiếu nhập ghi sổ trên màn Kho
        # (`sau_ghi_so_tra_hang`), không còn là tài xế tự bấm hộ kho.
        if ket_qua in (LG_THAT_BAI, LG_GIAO_THIEU):
            self._lap_yeu_cau_tra_hang(trip, actor=actor)
        return {"trip": trip, "canh_bao": canh_bao}

    def _lap_yeu_cau_tra_hang(self, trip, *, actor):
        """Yêu cầu NHẬP trả hàng về ĐÚNG kho đã xuất. Không có gì để trả (chưa xuất / khách nhận
        đủ phần đã xuất) thì chuyến thất bại đi thẳng tới "đã trả hàng"."""
        if self.stock_requests is None or self.yeu_cau_tra_hang_cua_trip(trip.id) is not None:
            return None
        # Dòng thực nhận vừa ghi cùng nhịp (`_ghi_dong_thuc_nhan`) chưa có trong `trip.lines` đã
        # nạp — không nạp lại là giao thiếu 80/100 mà trả về kho cả 100.
        self.deliveries.db.flush()
        self.deliveries.db.expire(trip, ["lines"])
        lines = self.hang_tra_ve(trip)
        if not lines:
            if trip.trang_thai == LG_DANG_TRA_HANG:
                self._doi_trang_thai(trip, LG_DA_TRA_HANG, actor=actor)
            return None
        yc_xuat = self.yeu_cau_kho_cua_trip(trip.id)
        return self.stock_requests.create(
            user=actor,
            loai="NHAP",
            lines=lines,
            kho_id=getattr(yc_xuat, "kho_id", None),
            ghi_chu=f"Trả hàng về — chuyến giao {trip.id}",
            delivery_trip_id=trip.id,
        )

    def sau_ghi_so_tra_hang(self, stock_request, *, actor) -> bool:
        """Kho ghi sổ phiếu nhập trả hàng xong (yêu cầu `done`) ⇒ chuyến thất bại sang "đã trả
        hàng". Giao thiếu giữ nguyên `giao_thieu` (kết cục, căn cứ cộng "đã giao"); dấu "kho đã nhận
        lại" của nó là yêu cầu nhập `done`. Trả True nếu có đổi gì."""
        if (getattr(stock_request, "loai", None) != "NHAP"
                or not getattr(stock_request, "delivery_trip_id", None)
                or stock_request.trang_thai != REQ_DONE):
            return False
        trip = self.deliveries.get_trip(int(stock_request.delivery_trip_id))
        if trip is None or trip.trang_thai != LG_DANG_TRA_HANG:
            return False
        self._doi_trang_thai(trip, LG_DA_TRA_HANG, actor=actor,
                             ghi_chu=f"Kho nhận lại hàng — {stock_request.ma}")
        return True

    def _ghi_dong_thuc_nhan(self, trip, req, *, ket_qua, so_thuc_nhan) -> None:
        """ĐIỀN LUÔN LUÔN — thành công thì bằng đúng số còn phải giao của yêu cầu.

        Một luật, không rẽ nhánh (PRD §13). Chỉ điền khi giao thiếu là tạo hai đường tính
        "đã giao bao nhiêu", mà hai đường thì sớm muộn lệch.
        """
        da_giao = self.deliveries.da_giao_cua_yeu_cau(req.id)
        con: dict[int, int] = {}
        for ln in req.lines:
            thieu = int(ln.qty) - int(da_giao.get(ln.order_line_id, 0))
            if thieu > 0:
                con[ln.order_line_id] = thieu

        if ket_qua == LG_THANH_CONG:
            nhan = dict(con)
        else:
            if not so_thuc_nhan:
                raise DeliveryError("Giao thiếu thì phải nhập số thực nhận từng dòng")
            nhan = {}
            # Cụm bán: khách nhận 480 cuốn nghĩa là nhận 480 ruột VÀ 480 bìa — gõ ở một dòng, ghi
            # cho mọi dòng của cụm.
            order = self.orders.get_by_id(req.order_id)
            cum_theo_dong = (
                {ln.id: c for c in cum_ban(order) for ln in c.dong} if order is not None else {}
            )
            for m in so_thuc_nhan:
                lid, qty = int(m["order_line_id"]), int(m["qty"])
                if lid not in con:
                    raise DeliveryError("Dòng hàng không nằm trong phần còn phải giao")
                if qty < 0:
                    raise DeliveryError("Số thực nhận không được âm")
                cum = cum_theo_dong.get(lid)
                cung_cum = [od.id for od in cum.dong if od.id in con] if cum else [lid]
                for dich in cung_cum:
                    if qty > con[dich]:
                        raise DeliveryError(
                            f"Số thực nhận {qty} vượt phần còn phải giao {con[dich]}"
                        )
                    if dich in nhan and nhan[dich] != qty:
                        raise DeliveryError(
                            f"Các phần của «{cum.ten}» nhận cùng nhau — số thực nhận phải bằng nhau"
                        )
                    nhan[dich] = qty
            if sum(nhan.values()) >= sum(con.values()):
                raise DeliveryError("Nhận đủ rồi thì chọn Giao thành công, không phải Giao thiếu")

        for lid, qty in nhan.items():
            self.deliveries.add_trip_line(trip.id, lid, qty)

    def hang_tra_ve(self, trip) -> list[dict]:
        """Phần hàng KHÔNG tới tay khách của chuyến — dòng cho phiếu NHẬP trả về kho.

        = số đã xuất cho chuyến TRỪ số khách thực nhận. Thất bại thì trả toàn bộ; giao thiếu thì
        chỉ trả phần thừa. Trả nguyên cả lô cho ca giao thiếu là thổi phồng tồn kho.

        Đơn vị KHÔNG phải quy đổi: yêu cầu xuất vốn dựng từ `hang_can_xuat` theo đúng `ln.dvt` của
        dòng yêu cầu giao, nên số xuất và số nhận cùng một thang.
        """
        req = self.deliveries.get_request(trip.request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        yc_xuat = self.yeu_cau_kho_cua_trip(trip.id)
        if yc_xuat is None:
            return []                       # chưa từng xuất kho ⇒ không có gì để trả

        # Số THẬT SỰ rời kho cho chuyến, theo mặt hàng. Phải đi qua `muc_tieu_hieu_luc` chứ KHÔNG
        # cộng thẳng `sl_duyet`: mệnh đề cũ ("tạo là duyệt luôn nên `sl_duyet` là số thật") hết đúng
        # từ khi có `stock_voucher_service.dieu_chinh_xuat` — kho hạ số xuống thì số chốt nằm ở
        # `sl_chot_thuc_xuat`, `sl_duyet` giữ nguyên con số ban đầu. Lấy `sl_duyet` là trả về kho
        # phần chưa bao giờ rời kho: xuất 500 → điều chỉnh 460 → khách nhận 440 ra 60 thay vì 20,
        # tức tồn phình 40 đơn vị ma kèm lô giá vốn dựng theo số đó.
        da_xuat: dict[tuple[str, int], float] = {}
        gia: dict[tuple[str, int], int] = {}
        for rl in yc_xuat.lines:
            khoa = (rl.hang_loai, rl.hang_id)
            da_xuat[khoa] = da_xuat.get(khoa, 0.0) + StockRequestService.muc_tieu_hieu_luc(rl)

        # Số khách THỰC NHẬN của chính chuyến này, quy về mặt hàng qua dòng yêu cầu giao.
        hang_cua_dong = {ln.order_line_id: (ln.hang_loai, ln.hang_id) for ln in req.lines}
        da_nhan: dict[tuple[str, int], float] = {}
        for tl in (trip.lines or []):          # quan hệ sẵn có trên model, không cần query riêng
            khoa = hang_cua_dong.get(tl.order_line_id)
            if khoa is None or khoa[0] is None:
                continue
            da_nhan[khoa] = da_nhan.get(khoa, 0.0) + float(tl.qty_giao or 0)

        # Giá vốn để dựng lại lô: lấy từ chính lô đã xuất, bình quân theo số lượng. Để 0 là đẻ ra
        # lô giá 0 — tồn còn đúng số nhưng giá trị kho tụt, kế toán không lần ra vì sao.
        gia = self._gia_von_da_xuat(yc_xuat)

        ra: list[dict] = []
        for khoa, xuat in da_xuat.items():
            tra = xuat - float(da_nhan.get(khoa, 0.0))
            if tra <= 1e-9:
                continue
            dvt = next((rl.dvt for rl in yc_xuat.lines
                        if (rl.hang_loai, rl.hang_id) == khoa), None)
            ra.append({"hang_loai": khoa[0], "hang_id": khoa[1], "dvt": dvt,
                       "sl_de_nghi": tra, "don_gia": int(gia.get(khoa, 0))})
        return ra

    def _gia_von_da_xuat(self, yc_xuat) -> dict[tuple[str, int], int]:
        """{(hang_loai, hang_id): đơn giá bình quân} lấy từ các LÔ mà phiếu xuất đã ăn."""
        if self.stock_vouchers is None:
            return {}
        tong_tien: dict[tuple[str, int], float] = {}
        tong_sl: dict[tuple[str, int], float] = {}
        # `list()` trả CẶP (rows, total) — lặp thẳng lên nó là lặp qua cả con số tổng.
        rows, _ = self.stock_vouchers.vouchers.list(request_id=yc_xuat.id, size=200)
        for v in rows:
            if v.trang_thai == "cancelled":
                continue
            for ln in getattr(v, "lines", []) or []:
                if not ln.lot_id:
                    continue
                lot = self.stock_vouchers.lots.get(ln.lot_id)
                if lot is None:
                    continue
                khoa = (ln.hang_loai, ln.hang_id)
                sl = float(ln.sl_goc or 0)
                tong_tien[khoa] = tong_tien.get(khoa, 0.0) + sl * float(lot.don_gia_nhap or 0)
                tong_sl[khoa] = tong_sl.get(khoa, 0.0) + sl
        return {k: int(round(tong_tien[k] / tong_sl[k])) for k in tong_sl if tong_sl[k] > 0}

    def kho_nhan_lai_hang(self, trip_id, *, actor, scope=None):
        """Thủ kho xác nhận đã nhận lại hàng ⇒ LẬP PHIẾU NHẬP rồi mới đổi trạng thái.

        ⚠️ THỨ TỰ QUAN TRỌNG (PRD một-yêu-cầu-một-chuyến §3). Trước 22/08/2026 hàm này chỉ đổi
        nhãn, KHÔNG lập phiếu — hàng chở về mà sổ kho vẫn ghi là đã xuất. Lỗi đó chưa lộ vì đường
        "chờ giao lại" giữ hàng trên xe rồi giao tiếp, không xuất lần hai; bỏ đường đó đi thì mỗi
        lần giao lại trừ kho thêm một lần nữa.

        Đổi nhãn TRƯỚC rồi lập phiếu sau là mở cửa cho trạng thái nói một đằng, sổ kho một nẻo.
        """
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        # HAI ngả vào bước này:
        #   · `dang_tra_hang` — chuyến thất bại, xe chở toàn bộ về;
        #   · `giao_thieu`    — khách nhận một phần, phần thừa về kho. Trạng thái GIỮ NGUYÊN
        #     `giao_thieu` (nó là kết cục, và là căn cứ cộng "đã giao"), nên ngả này không có
        #     cổng trạng thái nào chặn bấm lần hai — phải chặn bằng phiếu đã lập.
        if trip.trang_thai not in (LG_DANG_TRA_HANG, LG_GIAO_THIEU):
            raise DeliveryError("Chuyến này không có hàng nào phải trả về kho")

        da_co = self.yeu_cau_tra_hang_cua_trip(trip.id)
        if da_co is not None:
            raise DeliveryError(
                f"Đã có yêu cầu nhập trả hàng {da_co.ma} — thủ kho nhận lại bằng phiếu nhập bên Kho.")

        # Đường CŨ: chỉ còn cho chuyến ghi kết quả trước 19/09/2026 (chưa tự lập yêu cầu nhập).
        # Chuyến sang "đã trả hàng" khi THỦ KHO ghi sổ phiếu nhập (`sau_ghi_so_tra_hang`).
        self._lap_yeu_cau_tra_hang(trip, actor=actor)
        return trip

    # =====================================================================================
    # File minh chứng của chuyến (ảnh / PDF)
    # =====================================================================================
    #: Cùng hạn mức với đính kèm chứng từ kế toán — một luật cho cả hệ, đừng đẻ ngưỡng thứ hai.
    DINH_KEM_TOI_DA_BYTE = 10 * 1024 * 1024
    DINH_KEM_TOI_DA_FILE = 20
    DINH_KEM_THU_MUC = "giao-hang"

    def dinh_kem_cua_trip(self, trip_id: int, *, actor=None, scope=None) -> list:
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        if actor is not None:
            self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        return self.deliveries.dinh_kem_cua_trip(trip_id)

    def dinh_kem_them(self, trip_id: int, *, actor, file_name, content_type, data, scope=None):
        """Đính ảnh/PDF làm MINH CHỨNG cho chuyến.

        Cho đính ở BẤT KỲ lúc nào trong đời chuyến, cố ý: trước khi đi là hoá đơn tài xế cầm theo,
        giao xong là tờ khách đã ký. Chặn theo trạng thái ở đây là bắt người ta đoán đúng thời
        điểm mới tải được.
        """
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)

        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise DeliveryError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise DeliveryError("Tệp rỗng.")
        if len(data) > self.DINH_KEM_TOI_DA_BYTE:
            raise DeliveryError("Tệp vượt quá 10 MB.")
        if len(self.deliveries.dinh_kem_cua_trip(trip_id)) >= self.DINH_KEM_TOI_DA_FILE:
            raise DeliveryError(f"Mỗi chuyến tối đa {self.DINH_KEM_TOI_DA_FILE} file đính kèm.")

        from ..storage import get_storage, make_key, url_from_key

        key, ten_sach = make_key(self.DINH_KEM_THU_MUC, trip.id, file_name)
        get_storage().save(key, data, content_type)
        return self.deliveries.them_dinh_kem(
            trip_id=trip.id, file_name=ten_sach, file_url=url_from_key(key),
            file_type=content_type, uploaded_by=getattr(actor, "id", None),
        )

    def dinh_kem_xoa(self, trip_id: int, attachment_id: int, *, actor, scope=None) -> None:
        """Xoá file đính kèm. CHO xoá kể cả khi chuyến đã có kết quả — tài xế chụp mờ, chụp nhầm
        là chuyện thường, khoá lại là buộc họ để rác trong hồ sơ. Ai xoá lúc nào nằm ở nhật ký."""
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        row = self.deliveries.get_dinh_kem(attachment_id)
        if row is None or row.trip_id != trip.id:
            raise DeliveryNotFound("Không tìm thấy file đính kèm của chuyến này")

        from ..storage import get_storage, key_from_url

        key = key_from_url(row.file_url)
        if key:
            try:
                get_storage().delete(key)
            except Exception:
                # Xoá được dòng là đủ để người dùng thấy đúng; bytes mồ côi không làm sai số liệu.
                pass
        self.deliveries.xoa_dinh_kem(row)

    # =====================================================================================
    # Nội bộ
    # =====================================================================================
    def _doi_trang_thai(self, trip, den, *, actor, ghi_chu=None, ly_do=None) -> None:
        truoc = trip.trang_thai
        trip.trang_thai = den
        self.deliveries.ghi_lich_su(
            trip_id=trip.id, tu_trang_thai=truoc, den_trang_thai=den,
            nguoi_thao_tac_id=getattr(actor, "id", None), ghi_chu=ghi_chu, ly_do=ly_do,
        )

    # =====================================================================================
    # Tab Nhân viên giao hàng
    # =====================================================================================
    def trang_thai_nhan_vien(self, employee_id: int, *, ngay: date | None = None) -> str:
        """Rảnh / có lịch / đang giao / đang trả hàng / nghỉ — TÍNH, không cho nhập tay.

        "Nghỉ" đọc từ đơn `nghi_phep` ĐÃ DUYỆT, không đẻ ô khai tay thứ hai (PRD §6).
        """
        ngay = ngay or date.today()
        if self._dang_nghi(employee_id, ngay):
            return "nghi"
        trips = self.deliveries.list_trips(employee_ids=[employee_id])
        for t in trips:
            if t.trang_thai == LG_DANG_GIAO:
                return "dang_giao"
        for t in trips:
            if t.trang_thai == LG_DANG_TRA_HANG:
                return "dang_tra_hang"
        for t in trips:
            if t.trang_thai in (LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI,
                                LG_DA_LAY_HANG) and t.gio_lay_hang.date() == ngay:
                return "co_lich"
        return "ranh"

    def _dang_nghi(self, employee_id: int, ngay: date) -> bool:
        kiem = getattr(self.employees, "dang_nghi_phep", None)
        if kiem is None:
            # Chưa nối được nguồn nghỉ ⇒ trả False chứ KHÔNG bịa. Số giả tệ hơn khoảng trống.
            return False
        try:
            return bool(kiem(employee_id, ngay))
        except Exception:
            return False

    def thong_ke_ngay(self, employee_id: int, *, ngay: date | None = None) -> dict:
        """Số chuyến hoàn thành + tổng km trong ngày (tab Nhân viên giao hàng)."""
        ngay = ngay or date.today()
        xong, tong_km = 0, 0
        for t in self.deliveries.list_trips(employee_ids=[employee_id]):
            if t.thoi_gian_ket_thuc is None or t.thoi_gian_ket_thuc.date() != ngay:
                continue
            if t.trang_thai in LAN_GIAO_CO_HANG_DEN_TAY:
                xong += 1
            tong_km += int(t.km or 0)
        tong_km += sum(km for luc, km in self.deliveries.ve_kho_cua_tai_xe(employee_id)
                       if luc.date() == ngay)
        return {"so_chuyen_xong": xong, "tong_km": tong_km}
