"""Tiến độ MỘT đơn hàng bán cho Kinh doanh — Sản xuất → Nhập kho → Giao hàng (19/09/2026).

Thiết kế: `docs/superpowers/plans/2026-09-19-giao-hang-tien-do-don.md`.

Chỉ ĐỌC, không một cột nào mới. Ba nguồn đã có sẵn, gộp theo CỤM BÁN (một sản phẩm khách mua):
  · Sản xuất — lệnh của đơn (`lsx.order_line_id`), % và dự kiến xong tính bằng đúng hàm bảng lệnh
    dùng (`lenh_sx.danh_sach._soi`, `tien_do.phan_tram`) để hai màn không vênh số;
  · Nhập kho — dòng yêu cầu NHẬP thành phẩm KCS gửi cho lệnh của đơn (đề nghị / kho đã nhận);
  · Giao hàng — `DeliveryService.nguon_giao_theo_cum` (đã giao / đang giữ / giao được).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.lsx import TT_DA_PHAT_HANH, Lsx
from ..models.san_xuat import CV_HOAN_THANH
from ..repositories.delivery_repo import DeliveryRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.order_repo import OrderRepository
from .delivery_service import DeliveryService


def _ngay(dt: datetime | None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def tien_do_don(db: Session, order) -> dict:
    from .lenh_sx import danh_sach, tien_do

    bay_gio = datetime.now(timezone.utc)
    deliveries = DeliveryRepository(db)
    svc = DeliveryService(deliveries, OrderRepository(db), EmployeeRepository(db), None, None)
    nguon = svc.nguon_giao_theo_cum(order)

    lsx_ids = sorted({s for n in nguon for s in n["lsx_ids"]})
    lenh = {l.id: l for l in db.query(Lsx).filter(Lsx.id.in_(lsx_ids)).all()} if lsx_ids else {}
    chay = [i for i in lsx_ids if lenh[i].trang_thai == TT_DA_PHAT_HANH]
    bc, tinh = danh_sach._soi(db, chay, bay_gio) if chay else (None, {})

    def mot_lenh(i: int) -> dict:
        l = lenh[i]
        if i not in tinh:
            return {"id": i, "ma": l.ma, "da_xuong_xuong": False, "pct": 0.0, "uoc_tinh": False,
                    "xong": False, "buoc_hien_tai": None, "du_kien_xong": None,
                    "trang_thai": None, "canh_bao": []}
        pct, uoc = tien_do.phan_tram(bc, i)
        cvs = bc.cong_viec_du(i)
        cv = danh_sach.buoc_hien_tai(bc, i)
        return {
            "id": i, "ma": l.ma, "da_xuong_xuong": True,
            "pct": round(float(pct), 1), "uoc_tinh": bool(uoc),
            "xong": bool(cvs) and all(c.trang_thai == CV_HOAN_THANH for c in cvs),
            "buoc_hien_tai": cv.ten_cong_doan if cv is not None else None,
            "du_kien_xong": tinh[i]["xong"],
            "trang_thai": tinh[i]["trang_thai"],
            "canh_bao": list(tinh[i]["canh_bao"]),
        }

    cum_out: list[dict] = []
    moc_xong: list[datetime] = []
    thieu_moc = False
    ly_do: set[str] = set()
    for n in nguon:
        c = n["cum"]
        ls = [mot_lenh(i) for i in n["lsx_ids"]]
        for x in ls:
            if x["xong"]:
                continue
            ly_do.update(x["canh_bao"])
            if not x["da_xuong_xuong"]:
                ly_do.add("chua_xuong_xuong")
                thieu_moc = True
            elif x["du_kien_xong"] is None:
                thieu_moc = True
            else:
                moc_xong.append(x["du_kien_xong"])
        de_nghi, da_nhan = n["kho_de_nghi"], n["kho_da_nhan"]
        cum_out.append({
            "khoa": c.khoa,
            "ten": c.ten,
            "don_vi": getattr(c.dong_dau, "don_vi_tinh", None),
            "order_line_ids": [od.id for od in c.dong],
            "dat": n["dat"],
            "co_lenh": n["co_lenh"],
            "lenh": ls,
            "sx_pct": round(sum(x["pct"] for x in ls) / len(ls), 1) if ls else None,
            "sx_xong": bool(ls) and all(x["xong"] for x in ls),
            "kho_de_nghi": round(de_nghi, 3),
            "kho_da_nhan": round(da_nhan, 3),
            "cho_kho": round(max(0.0, de_nghi - da_nhan), 3),
            "ton_that": round(n["ton_that"], 3),
            "da_giao": n["da_giao"],
            "dang_giu": n["dang_giu"],
            "con_phai_giao": n["con_phai_giao"],
            "giao_duoc": n["giao_duoc"],
        })

    han = order.delivery_committed_date
    du_kien = max(moc_xong) if moc_xong and not thieu_moc else None
    tre = None
    if han is not None and du_kien is not None:
        tre = max(0, (_ngay(du_kien) - han).days)
    return {
        "order_id": order.id,
        "han_cam_ket": han,
        "du_kien_xong": du_kien,
        "chua_du_du_lieu": thieu_moc and any(not x["sx_xong"] for x in cum_out if x["co_lenh"]),
        "tre_ngay": tre,
        "ly_do": sorted(ly_do),
        "cum": cum_out,
        "yeu_cau": _yeu_cau(svc, order),
        "noi_nhan": _noi_nhan(db, order),
    }


def _noi_nhan(db: Session, order) -> dict:
    """Nơi nhận để form yêu cầu giao CHỌN — mặc định của đơn + sổ địa chỉ / người liên hệ của khách.

    Trả kèm ở đây (quyền đọc đơn) chứ không bắt FE gọi `/api/customers/...`: Kinh doanh lập yêu cầu
    giao không nhất thiết có ô xem hồ sơ khách, gọi rồi ăn 403 là form trống oan.
    """
    from ..models.customer import CustomerAddress, CustomerContact

    kid = order.customer_id
    dc = (db.query(CustomerAddress).filter(CustomerAddress.customer_id == kid)
          .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id).all()) if kid else []
    lh = (db.query(CustomerContact).filter(CustomerContact.customer_id == kid)
          .order_by(CustomerContact.is_primary.desc(), CustomerContact.id).all()) if kid else []
    return {
        "khach_id": kid,
        "dia_chi": order.delivery_address,
        "nguoi_nhan": order.delivery_contact_name,
        "sdt": order.delivery_contact_phone,
        "luu_y": order.delivery_note,
        "so_dia_chi": [{"id": a.id, "nhan": a.label, "dia_chi": a.address, "sdt": a.phone,
                        "mac_dinh": bool(a.is_default)} for a in dc],
        "lien_he": [{"id": c.id, "ten": c.name, "chuc_vu": c.title, "sdt": c.phone,
                     "chinh": bool(c.is_primary)} for c in lh],
    }


def _yeu_cau(svc: DeliveryService, order) -> list[dict]:
    """Yêu cầu giao của đơn + chuyến (một yêu cầu một chuyến, mg 0229) cho Kinh doanh theo dõi."""
    from ..models.employee import Employee

    db = svc.deliveries.db
    cum_theo_dong = {}
    from .thanh_pham_khai_bao import cum_ban

    for c in cum_ban(order):
        for od in c.dong:
            cum_theo_dong[od.id] = c
    ra: list[dict] = []
    reqs = sorted(svc.deliveries.requests_cua_don_ca_huy(order.id), key=lambda r: r.id,
                  reverse=True)
    for r in reqs:
        trips = svc.deliveries.trips_cua_yeu_cau(r.id)
        t = trips[-1] if trips else None
        da = svc.deliveries.da_giao_cua_yeu_cau(r.id)
        dong: list[dict] = []
        da_co: set[str] = set()
        for ln in r.lines:
            c = cum_theo_dong.get(ln.order_line_id)
            khoa = c.khoa if c is not None else str(ln.order_line_id)
            if khoa in da_co:
                continue
            da_co.add(khoa)
            dong.append({"order_line_id": ln.order_line_id,
                         "ten": c.ten if c is not None else "",
                         "qty": int(ln.qty), "da_giao": int(da.get(ln.order_line_id, 0))})
        chuyen = None
        if t is not None:
            nv = db.get(Employee, t.employee_id) if t.employee_id else None
            tra = svc.deliveries.yeu_cau_kho_cua_chuyen(t.id, "NHAP")
            xe = None
            if t.vehicle_id:
                from ..models.xe import Xe
                x = db.get(Xe, t.vehicle_id)
                xe = f"{x.ma} · {x.ten}" if x is not None else None
            chuyen = {
                "id": t.id,
                "trang_thai": t.trang_thai,
                "gio_lay_hang": t.gio_lay_hang,
                "gio_du_kien_giao": t.gio_du_kien_giao,
                "tai_xe": getattr(nv, "full_name", None),
                "xe": xe,
                "thoi_gian_ket_thuc": t.thoi_gian_ket_thuc,
                "nguoi_nhan_thuc_te": t.nguoi_nhan_thuc_te,
                "ly_do_that_bai": t.ly_do_that_bai,
                "tra_hang_ma": getattr(tra, "ma", None),
                "tra_hang_xong": tra is not None and tra.trang_thai == "done",
                "kho_da_lap_phieu": svc.kho_da_lap_phieu(t.id),
                "so_anh": len(svc.deliveries.dinh_kem_cua_trip(t.id)),
            }
        ra.append({
            "id": r.id,
            "code": r.code,
            "ngay_can_giao": r.ngay_can_giao,
            "trang_thai": svc.trang_thai_yeu_cau(r),
            "ly_do_huy": r.ly_do_huy,
            "dia_chi": r.dia_chi,
            "nguoi_nhan": r.nguoi_nhan,
            "sdt_nguoi_nhan": r.sdt_nguoi_nhan,
            "ghi_chu": r.ghi_chu,
            "created_at": r.created_at,
            "dong": dong,
            "chuyen": chuyen,
        })
    return ra
