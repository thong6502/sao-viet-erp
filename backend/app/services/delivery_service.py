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

from .thanh_pham_khai_bao import khai_mot_dong
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
from ..models.order import STATUS_ORDERED
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN

# Hai chuyến cách nhau dưới ngần này thì CẢNH BÁO (không chặn) — PRD §6.
DEM_SAT_GIO = timedelta(minutes=30)

# Trạng thái dẫn xuất của yêu cầu — KHÔNG lưu, chỉ trả cho FE.
YC_DANG_THUC_HIEN = "dang_thuc_hien"
YC_DA_GIAO_DU = "da_giao_du"


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
                 stock_requests=None, stock_vouchers=None) -> None:
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
    def con_phai_giao(self, order_id: int) -> dict[int, int]:
        """{order_line_id: còn phải giao} = đặt − đã giao − đang nằm trong yêu cầu MỞ.

        Trừ cả phần đang nằm trong yêu cầu chưa giao xong, nếu không thì lập hai yêu cầu liên
        tiếp là đặt vượt số đơn mà mỗi lần kiểm đều thấy "còn đủ".
        """
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise DeliveryNotFound("Không tìm thấy đơn hàng bán")
        dat = {ln.id: int(ln.qty or 0) for ln in order.lines}
        da_giao = self.deliveries.da_giao_theo_dong(order_id)

        dang_giu: dict[int, int] = {}
        for req in self.deliveries.requests_mo_cua_don(order_id):
            da_cua_req = self.deliveries.da_giao_cua_yeu_cau(req.id)
            for ln in req.lines:
                # Phần của yêu cầu này CHƯA tới tay khách vẫn đang bị giữ chỗ.
                chua_giao = int(ln.qty) - int(da_cua_req.get(ln.order_line_id, 0))
                if chua_giao > 0:
                    dang_giu[ln.order_line_id] = dang_giu.get(ln.order_line_id, 0) + chua_giao

        return {
            lid: max(0, so - int(da_giao.get(lid, 0)) - int(dang_giu.get(lid, 0)))
            for lid, so in dat.items()
        }

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
        if self.deliveries.trip_dang_chay(request.id) is not None:
            return YC_DANG_THUC_HIEN
        # Mọi chuyến đã đóng mà chưa giao đủ ⇒ chờ quản lý xếp chuyến mới.
        return YC_CHO_LEN_KE_HOACH

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

    def tao_yeu_cau(self, *, order_id, ngay_can_giao, lines, actor,
                    dia_chi=None, nguoi_nhan=None, sdt_nguoi_nhan=None, ghi_chu=None) -> dict:
        order = self.orders.get_by_id(order_id)
        if order is None:
            raise DeliveryNotFound("Không tìm thấy đơn hàng bán")
        if order.status != STATUS_ORDERED:
            raise DeliveryError("Chỉ tạo yêu cầu giao từ đơn hàng ĐÃ CHỐT")
        if not lines:
            raise DeliveryError("Phải chọn ít nhất một dòng hàng để giao")

        con_lai = self.con_phai_giao(order_id)
        hop_le = {ln.id for ln in order.lines}
        for ln in lines:
            lid, qty = int(ln["order_line_id"]), int(ln["qty"])
            if lid not in hop_le:
                raise DeliveryError("Dòng hàng không thuộc đơn hàng này")
            if qty <= 0:
                raise DeliveryError("Số lượng giao phải lớn hơn 0")
            if qty > con_lai.get(lid, 0):
                raise DeliveryError(
                    f"Vượt số còn phải giao: dòng chỉ còn {con_lai.get(lid, 0)}, đang yêu cầu {qty}"
                )

        # CHẶN CỨNG, không phải cảnh báo (chủ chốt 20/08/2026: "nay ngày 20 tôi lập phiếu yêu
        # cầu thì sao mà chọn được ngày 19"). Bản đầu chỉ cảnh báo với lý do "nhập bù đơn hôm
        # qua" — nhưng yêu cầu giao là việc SẮP LÀM, không phải sổ ghi việc đã làm: hàng chưa ra
        # khỏi kho thì không có gì để nhập bù. Ngày quá khứ ở đây chỉ có thể là gõ nhầm, mà gõ
        # nhầm thì kéo lệch cả hàng chờ giao lẫn thống kê trễ hạn.
        self._chan_ngay_qua_khu(ngay_can_giao)
        canh_bao: list[str] = []

        code = self._sinh_ma("YCGH", self.deliveries.get_request_by_code)
        req = self.deliveries.create_request(
            code=code,
            order_id=order_id,
            customer_id=getattr(order, "customer_id", None),
            department_id=getattr(actor, "department_id", None),
            ngay_can_giao=ngay_can_giao,
            # SNAPSHOT: điền sẵn từ đơn nếu người lập không sửa. Đông lại ngay, không đọc-sống.
            dia_chi=(dia_chi if dia_chi is not None else (order.delivery_address or "")),
            nguoi_nhan=(nguoi_nhan if nguoi_nhan is not None else order.delivery_contact_name),
            sdt_nguoi_nhan=(sdt_nguoi_nhan if sdt_nguoi_nhan is not None
                            else order.delivery_contact_phone),
            ghi_chu=(ghi_chu if ghi_chu is not None else order.delivery_note),
            trang_thai=YC_CHO_LEN_KE_HOACH,
            created_by=getattr(actor, "id", None),
        )
        dong_don = {d.id: d for d in order.lines}
        for ln in lines:
            od = dong_don[int(ln["order_line_id"])]
            # Tự khai mặt hàng kho từ chính dòng đơn — người lập KHÔNG phải chọn gì.
            mh = self._mat_hang_cua_dong_don(order, od)
            self.deliveries.add_request_line(
                req.id, od.id, int(ln["qty"]),
                hang_loai="vat_tu", hang_id=mh.id, dvt=mh.don_vi_gia,
            )
        return {"request": req, "canh_bao": canh_bao}

    def huy_yeu_cau(self, request_id: int, *, ly_do: str, actor, scope=None) -> None:
        req = self.deliveries.get_request(request_id)
        if req is None:
            raise DeliveryNotFound("Không tìm thấy yêu cầu giao hàng")
        self.chan_ngoai_pham_vi_yeu_cau(req, scope=scope, actor=actor)
        if req.trang_thai == YC_DA_HUY:
            raise DeliveryError("Yêu cầu đã huỷ rồi")
        if self.deliveries.trips_cua_yeu_cau(request_id):
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
        for truong in ("ngay_can_giao", "dia_chi", "nguoi_nhan", "sdt_nguoi_nhan", "ghi_chu"):
            if truong in thay_doi and thay_doi[truong] is not None:
                setattr(req, truong, thay_doi[truong])

    def chan_huy_don_khi_con_yeu_cau_mo(self, order_id: int) -> None:
        """Nghiệm thu #12 — huỷ đơn bán khi còn yêu cầu giao chưa đóng thì bị chặn.

        Thông báo nêu ĐÚNG mã yêu cầu đang mở; bắt người ta đi mò là lỗi giao diện."""
        con_mo = [
            r.code for r in self.deliveries.requests_mo_cua_don(order_id)
            if self.trang_thai_yeu_cau(r) != YC_DA_GIAO_DU
        ]
        if con_mo:
            raise DeliveryError(
                "Đơn còn yêu cầu giao hàng chưa đóng: " + ", ".join(sorted(con_mo))
                + ". Huỷ các yêu cầu đó trước."
            )

    # =====================================================================================
    # Lên kế hoạch — và đề nghị xuất hàng đi kèm
    # =====================================================================================
    def kiem_lich_tai_xe(self, *, employee_id, gio_lay_hang, gio_du_kien_giao,
                         bo_qua_trip_id=None) -> list[str]:
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
            bo_qua_trip_id=bo_qua_trip_id,
        )
        if trung:
            ma = ", ".join(f"#{t.id}" for t in trung)
            raise DeliveryError(f"Tài xế đã có chuyến trùng giờ: {ma}")
        # Sát giờ = không trùng nhưng đệm dưới 30 phút ⇒ cho lưu, chỉ nhắc.
        ke = self.deliveries.trung_lich(
            employee_id=employee_id,
            bat_dau=gio_lay_hang - DEM_SAT_GIO,
            ket_thuc=gio_du_kien_giao + DEM_SAT_GIO,
            bo_qua_trip_id=bo_qua_trip_id,
        )
        if ke:
            return [f"Tài xế có chuyến khác cách dưới {int(DEM_SAT_GIO.total_seconds() // 60)} phút"]
        return []

    def len_ke_hoach(self, *, request_id, employee_id, gio_lay_hang, gio_du_kien_giao,
                     actor, kho_id=None, ghi_chu_phan_cong=None, scope=None) -> dict:
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

        self._chan_gio_qua_khu(gio_lay_hang, "Giờ lấy hàng")
        self._chan_gio_qua_khu(gio_du_kien_giao, "Giờ dự kiến giao")
        canh_bao = self.kiem_lich_tai_xe(
            employee_id=employee_id, gio_lay_hang=gio_lay_hang, gio_du_kien_giao=gio_du_kien_giao,
        )

        # (đẩy realtime sau khi có `trip` — xem cuối hàm)
        trip = self.deliveries.create_trip(
            request_id=request_id,
            lan_thu=self.deliveries.lan_thu_ke_tiep(request_id),
            employee_id=employee_id,
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
        # KHÔNG tự sinh đề nghị xuất hàng ở đây — quản lý bấm tay ở bước sau (luật 6).
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
        """
        yc = self.yeu_cau_kho_cua_trip(trip_id)
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
        ra: list[dict] = []
        for ln in req.lines:
            con = int(ln.qty) - int(da_giao.get(ln.order_line_id, 0))
            if con <= 0:
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

    def gui_yeu_cau_xuat_kho(self, trip_id, *, actor, kho_id, scope=None,
                             ngay_can=None, ghi_chu=None):
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
        )
        # Kho đã nhận việc ⇒ chuyến sang "Kho đang chuẩn bị". Không có bước duyệt nào ở giữa:
        # `create()` của họ duyệt luôn (bỏ bước duyệt 06/08/2026).
        self._doi_trang_thai(trip, LG_DANG_CHUAN_BI, actor=actor,
                             ghi_chu=f"Yêu cầu xuất kho {req.ma}")
        self.bao_tai_xe(trip, f"Đã gửi yêu cầu xuất kho {req.ma} — chờ kho soạn hàng.",
                        viec="gui_kho")
        return req

    def doi_ke_hoach(self, trip_id, *, actor, scope=None, employee_id=None,
                     gio_lay_hang=None, gio_du_kien_giao=None, ghi_chu_phan_cong=None) -> dict:
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
        canh_bao = self.kiem_lich_tai_xe(
            employee_id=moi_nv, gio_lay_hang=moi_lay, gio_du_kien_giao=moi_giao,
            bo_qua_trip_id=trip.id,
        )

        doi_gio = moi_lay != trip.gio_lay_hang
        # Đổi TÀI XẾ thì báo người MỚI. Người cũ không báo ở đây — họ chưa cầm hàng (điều kiện
        # đầu hàm), nên với họ chuyến này coi như chưa từng bắt đầu.
        doi_nguoi = moi_nv != trip.employee_id
        trip.employee_id = moi_nv
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
        self._doi_trang_thai(trip, LG_DA_HUY, actor=actor, ly_do=ly_do.strip())

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

    def bat_dau_giao(self, trip_id, *, actor, scope=None):
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DA_LAY_HANG:
            raise DeliveryError("Chưa lấy hàng thì chưa bắt đầu giao được")
        self._doi_trang_thai(trip, LG_DANG_GIAO, actor=actor)
        return trip

    def ghi_ket_qua(self, trip_id, *, ket_qua, km, actor, scope=None,
                    thoi_gian_ket_thuc=None, nguoi_nhan_thuc_te=None, ly_do_that_bai=None,
                    huong_xu_ly=None, ghi_chu=None, so_thuc_nhan=None,
                    xac_nhan_km_lon=False) -> dict:
        trip = self.deliveries.get_trip(trip_id)
        if trip is None:
            raise DeliveryNotFound("Không tìm thấy chuyến giao")
        self.chan_ngoai_pham_vi_trip(trip, scope=scope, actor=actor)
        if trip.trang_thai != LG_DANG_GIAO:
            raise DeliveryError("Chỉ ghi kết quả cho chuyến đang giao")
        # `hen_lai` đã gỡ khỏi danh sách hợp lệ (22/08/2026) — khai nó ⇒ báo lỗi, không âm thầm bỏ.
        if ket_qua not in (LG_THANH_CONG, LG_GIAO_THIEU, LG_THAT_BAI):
            raise DeliveryError("Kết quả không hợp lệ")

        if km is None:
            raise DeliveryError("Phải nhập số km thực tế")
        km = int(km)
        if km < 0:
            raise DeliveryError("Số km không được âm")
        canh_bao: list[str] = []
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

        trip.km = km
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
        return {"trip": trip, "canh_bao": canh_bao}

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
            for m in so_thuc_nhan:
                lid, qty = int(m["order_line_id"]), int(m["qty"])
                if lid not in con:
                    raise DeliveryError("Dòng hàng không nằm trong phần còn phải giao")
                if qty < 0:
                    raise DeliveryError("Số thực nhận không được âm")
                if qty > con[lid]:
                    raise DeliveryError(
                        f"Số thực nhận {qty} vượt phần còn phải giao {con[lid]}"
                    )
                nhan[lid] = qty
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

        # Số đã DUYỆT xuất cho chuyến, theo mặt hàng (yêu cầu tạo là duyệt luôn nên đây là số thật).
        da_xuat: dict[tuple[str, int], float] = {}
        gia: dict[tuple[str, int], int] = {}
        for rl in yc_xuat.lines:
            khoa = (rl.hang_loai, rl.hang_id)
            da_xuat[khoa] = da_xuat.get(khoa, 0.0) + float(rl.sl_duyet or 0)

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
            raise DeliveryError(f"Chuyến này đã có phiếu nhập trả hàng {da_co.ma}")

        lines = self.hang_tra_ve(trip)
        if lines and self.stock_requests is not None:
            yc_xuat = self.yeu_cau_kho_cua_trip(trip.id)
            self.stock_requests.create(
                user=actor,
                loai="NHAP",
                lines=lines,
                # ĐÚNG kho đã xuất — đây là đảo lại một phiếu cụ thể, không cho chọn kho khác.
                kho_id=getattr(yc_xuat, "kho_id", None),
                ghi_chu=f"Trả hàng về — chuyến giao {trip.id}",
                delivery_trip_id=trip.id,
            )

        # Chỉ ca thất bại mới có nhãn "đã trả hàng" để đi tới. Ca giao thiếu giữ nguyên
        # `giao_thieu`; dấu hiệu đã trả hàng là PHIẾU NHẬP tồn tại, không phải trạng thái.
        if trip.trang_thai == LG_DANG_TRA_HANG:
            self._doi_trang_thai(trip, LG_DA_TRA_HANG, actor=actor)
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
        return {"so_chuyen_xong": xong, "tong_km": tong_km}
