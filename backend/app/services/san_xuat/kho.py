"""Thực hiện sản xuất — NHẬP KHO THÀNH PHẨM qua "Yêu cầu nhập xuất" (17/09/2026).

Thiết kế: `docs/design-nhap-kho-thanh-pham-qua-yeu-cau-nhap-xuat.md`.

Sản xuất KHÔNG còn sổ kho riêng (`san_xuat_nhap_kho_yc` / `san_xuat_kho_lot` / `san_xuat_kho_hang`
đã gỡ, mg `0310`). Nút "Tạo yêu cầu nhập kho" ở công đoạn KCS cuối lập MỘT yêu cầu NHẬP thật
(`stock_requests`, tự duyệt, kho để trống) cho món Thành phẩm của cụm bán. Thủ kho nhận bằng phiếu
nhập như mọi hàng khác, chọn kho lúc lập phiếu. Sản xuất cần biết "đã đề nghị / kho đã nhận" thì ĐỌC
NGƯỢC dòng yêu cầu có `san_xuat_cong_viec_id` = công đoạn (`dong_nhap_kho_cua_cong_viec`) — không có
bước chép số nào.

Luật:
  · Mặt hàng = mã Thành phẩm của CỤM BÁN (`thanh_pham_khai_bao.cum_ban`, cùng luật `gop-nhom.ts`).
    Nhóm sản xuất trùng một cụm ⇒ một dòng; nhóm chứa nhiều cụm ⇒ chia số gửi theo SL cụm / Σ SL
    các cụm, phần cuối nhận phần dư. Hai cụm ra cùng một mã (cùng tên, khác SL) thì gộp một dòng.
  · Trần tính theo CÔNG ĐOẠN: được gửi thêm = min(Σ đạt, Σ tốt) − Σ đã đề nghị còn hiệu lực. Yêu cầu
    còn sống tính mục tiêu hiệu lực (số kho chốt nếu có, không thì số duyệt); đã huỷ / bị từ chối chỉ
    tính phần kho đã nhận — kho huỷ yêu cầu thì phần chưa nhận tự quay về cho KCS gửi lại.
  · Số KCS theo đơn vị ra của công đoạn; dòng yêu cầu ghi theo đơn vị của món (`don_vi_gia`), quy đổi
    qua `quy_ve_goc`.
  · Giá gốc = 0 (kế toán kho nhập sau); giá bán = Σ thành tiền cụm ÷ SL cụm (`don_gia_ban`).
  · `lsx_id` của dòng = lệnh thân chính của nhóm.

Gate: người thuộc tổ KCS (`kcs.gate_kcs`). Người KCS không cần ô quyền kho — service gọi thẳng
`StockRequestService.create`, như Giao hàng.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from ...models.stock_request import REQ_CANCELLED, REQ_NHAP, REQ_REJECTED
from ...realtime import hub
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.delivery_repo import DeliveryRepository
from ...repositories.don_vi_do_repo import DonViDoRepository, nhan_don_vi
from ...repositories.kho_hang_repo import KhoHangRepository
from ...repositories.order_repo import OrderRepository
from ...repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from ...repositories.stock_lot_repo import StockLotRepository
from ...repositories.stock_request_repo import StockRequestRepository
from ..stock_request_service import StockRequestError, StockRequestService
from ..thanh_pham_khai_bao import CumBan, cum_ban, gia_ban_cum, khai_cum, tim_theo_ten
from ..vat_lieu_kho_service import VatLieuKhoError
from .kcs import _EPS, gate_kcs
from .vat_tu_de_nghi import _hang_service, _req_service

# Yêu cầu đã KẾT THÚC mà không nhận hết: chỉ phần kho đã nhận còn tính là "đã gửi".
_HET_HIEU_LUC = (REQ_CANCELLED, REQ_REJECTED)


class KhongConSoDuGuiKho(ValueError):
    """Không còn số đạt chưa gửi kho cho công đoạn này — router dịch thành 409 (khác ValueError thường
    dịch 400). Kế thừa ValueError để nếu lỡ không được bắt riêng, `_chay` vẫn dịch 400, không bao
    giờ rơi thành 500 không rõ nguyên nhân."""


@dataclass
class DongNhapKhoTp:
    """MỘT dòng yêu cầu NHẬP thành phẩm có nguồn là công đoạn KCS cuối — mặt đọc duy nhất của sản
    xuất về kho. Số `sl_*` theo `dvt` của dòng (đơn vị món); `he_so_kcs` = 1 đơn vị ra của công
    đoạn bằng bao nhiêu `dvt` (chia cho nó để quy về đơn vị KCS).

    `he_so_kcs` tính LƯỜI: quy đổi đọc danh mục đơn vị theo từng món, mà trang danh sách lệnh chỉ cần
    "kho đã nhận chưa" — tính sẵn thì số câu SQL của bối cảnh lệnh tăng theo số món."""

    request_id: int
    request_ma: str
    trang_thai: str
    line_id: int
    cong_viec_id: int
    lsx_id: int | None
    hang_id: int
    dvt: str
    sl_de_nghi: float
    sl_hieu_luc: float
    sl_da_nhan: float
    created_at: datetime | None
    created_by: int | None
    updated_at: datetime | None
    #: Phiếu nhập ghi sổ muộn nhất ứng dòng này (mốc "kho đã nhận"); None = kho chưa nhận gì.
    nhan_luc: datetime | None = None
    nhan_boi: int | None = None
    quy_doi: Callable[[], float] = field(default=lambda: 1.0, repr=False, compare=False)

    @property
    def he_so_kcs(self) -> float:
        return self.quy_doi()

    @property
    def con_hieu_luc(self) -> bool:
        return self.trang_thai not in _HET_HIEU_LUC

    @property
    def sl_da_de_nghi(self) -> float:
        """Phần còn tính là "đã gửi kho" theo `dvt` dòng."""
        return self.sl_hieu_luc if self.con_hieu_luc else self.sl_da_nhan

    def _ve_kcs(self, so: float) -> float:
        return so / self.he_so_kcs if self.he_so_kcs else so

    @property
    def sl_da_de_nghi_kcs(self) -> float:
        return self._ve_kcs(self.sl_da_de_nghi)

    @property
    def sl_da_nhan_kcs(self) -> float:
        return self._ve_kcs(self.sl_da_nhan)

    @property
    def sl_cho_kho_kcs(self) -> float:
        """Phần đã gửi mà kho CHƯA nhận (đơn vị KCS) — 0 khi yêu cầu đã kết thúc."""
        return self._ve_kcs(max(0.0, self.sl_hieu_luc - self.sl_da_nhan)) if self.con_hieu_luc else 0.0

    @property
    def cho_kho(self) -> bool:
        return self.con_hieu_luc and self.sl_da_nhan + _EPS < self.sl_hieu_luc


# --- Quy đổi đơn vị KCS ⇄ đơn vị món ------------------------------------------------------------
def _he_so(hang, hang_id: int, tu_dv: str | None, sang_dv: str | None) -> float:
    """1 `tu_dv` = bao nhiêu `sang_dv` của món `hang_id`. Raise `VatLieuKhoError` nếu không đổi được."""
    tu = float(hang.quy_ve_goc("vat_tu", hang_id, tu_dv, 1)["he_so_ve_goc"])
    sang = float(hang.quy_ve_goc("vat_tu", hang_id, sang_dv, 1)["he_so_ve_goc"])
    return tu / sang if sang else 1.0


def _he_so_cho_nhap(db: Session, hang, tp, don_vi_kcs: str) -> float:
    """Hệ số quy số đạt (đơn vị ra công đoạn) sang đơn vị của món — lỗi nói bằng lời nghiệp vụ."""
    if not (tp.don_vi_gia or "").strip():
        raise ValueError(
            f"Thành phẩm {tp.ma} chưa khai đơn vị — khai ở Cấu hình danh mục ▸ Thành phẩm rồi gửi lại."
        )
    if not don_vi_kcs:
        raise ValueError("Công đoạn cuối chưa khai đơn vị ra nên chưa quy đổi được sang đơn vị kho.")
    try:
        return _he_so(hang, tp.id, don_vi_kcs, tp.don_vi_gia)
    except VatLieuKhoError:
        bang = DonViDoRepository(db).ten_theo_ma()
        raise ValueError(
            f"Không quy đổi được từ «{nhan_don_vi(bang, don_vi_kcs)}» sang "
            f"«{nhan_don_vi(bang, tp.don_vi_gia)}» cho {tp.ma}."
        ) from None


# --- Đọc ngược -----------------------------------------------------------------------------------
def dong_nhap_kho_cua_cong_viec(db: Session, cong_viec_ids) -> dict[int, list[DongNhapKhoTp]]:
    """`{cong_viec_id: [dòng]}` của mọi yêu cầu NHẬP có nguồn là các công đoạn này, theo thứ tự tạo.
    Công đoạn chưa gửi gì thì vắng mặt. Hai truy vấn cho cả tập (không N+1); hệ số quy về đơn vị KCS
    chỉ đọc khi có người hỏi `he_so_kcs`, nhớ theo (món, đơn vị ra, đơn vị dòng)."""
    req_repo = StockRequestRepository(db)
    rows = req_repo.dong_nhap_tu_cong_viec(cong_viec_ids)
    if not rows:
        return {}
    nhan = req_repo.lan_nhan_cuoi_theo_dong([ln.id for _, ln in rows])
    cv_ids = {int(req.san_xuat_cong_viec_id) for req, _ in rows}
    nho: dict = {}

    def he_so(cv_id: int, hang_id: int, dvt: str) -> float:
        if "don_vi_ra" not in nho:
            nho["don_vi_ra"] = SanXuatRepository(db).don_vi_ra_cua(cv_ids)
        dv_kcs = (nho["don_vi_ra"].get(cv_id) or "").strip()
        khoa = (hang_id, dv_kcs, dvt)
        if khoa not in nho:
            if not dv_kcs:
                nho[khoa] = 1.0
            else:
                nho.setdefault("hang", _hang_service(db))
                try:
                    nho[khoa] = _he_so(nho["hang"], hang_id, dv_kcs, dvt)
                except VatLieuKhoError:
                    # Danh mục đổi sau khi gửi (bỏ quy cách…): đọc 1:1 thay vì làm vỡ cả màn KCS.
                    nho[khoa] = 1.0
        return nho[khoa]

    out: dict[int, list[DongNhapKhoTp]] = {}
    for req, ln in rows:
        cv_id = int(req.san_xuat_cong_viec_id)
        out.setdefault(cv_id, []).append(DongNhapKhoTp(
            request_id=req.id,
            request_ma=req.ma,
            trang_thai=req.trang_thai,
            line_id=ln.id,
            cong_viec_id=cv_id,
            lsx_id=ln.lsx_id,
            hang_id=ln.hang_id,
            dvt=ln.dvt,
            sl_de_nghi=float(ln.sl_de_nghi or 0),
            sl_hieu_luc=StockRequestService.muc_tieu_hieu_luc(ln),
            sl_da_nhan=float(ln.sl_da_ung or 0),
            created_at=req.created_at,
            created_by=req.nguoi_tao_id,
            updated_at=req.updated_at,
            nhan_luc=(nhan.get(ln.id) or (None, None))[0],
            nhan_boi=(nhan.get(ln.id) or (None, None))[1],
            quy_doi=lambda c=cv_id, h=ln.hang_id, d=ln.dvt: he_so(c, h, d),
        ))
    return out


def so_da_de_nghi_kcs(dong: list[DongNhapKhoTp]) -> float:
    """Σ đã đề nghị còn hiệu lực, theo đơn vị KCS."""
    return sum(d.sl_da_de_nghi_kcs for d in dong)


def so_con_gui_kho(db: Session, cv, dong: list[DongNhapKhoTp], *, lan_kiem=None, tot=None) -> float:
    """được gửi thêm = min(Σ đạt, Σ tốt) − Σ đã đề nghị còn hiệu lực (đơn vị KCS), kẹp ≥ 0.

    `lan_kiem` / `tot` truyền sẵn khi bên gọi đã nạp (màn KCS duyệt cả chuỗi) để khỏi đọc lại."""
    if lan_kiem is None:
        lan_kiem = SanXuatKcsRepository(db).cac_kcs_batch(cv.id)
    if tot is None:
        tot = SanXuatSanLuongRepository(db).tong_tot(cv.id)
    dat = sum(float(k.so_luong_dat or 0) for k in lan_kiem)
    return max(0.0, min(dat, float(tot or 0)) - so_da_de_nghi_kcs(dong))


# --- Nhóm → cụm bán ------------------------------------------------------------------------------
@dataclass
class _NguonNhom:
    order: object
    lenh: list            # [Lsx] của nhóm
    than_chinh: object    # Lsx thân chính
    cums: list[CumBan]    # cụm bán chứa dòng đơn của nhóm, theo thứ tự cụm trên đơn


def _nguon_nhom(db: Session, *, nhom_id: int | None, lsx_id: int | None) -> _NguonNhom | None:
    """Đơn + lệnh + cụm bán của một nhóm thành phẩm. Công đoạn chưa gắn nhóm thì đọc riêng lệnh của nó."""
    sx = SanXuatRepository(db)
    nhom = sx.nhom(nhom_id) if nhom_id else None
    if nhom is not None:
        thanh_vien = sx.lenh_cua_nhom(nhom.id)
        lenh = [l for l, _ in thanh_vien]
        dong_don = {tv.order_line_id or l.order_line_id for l, tv in thanh_vien}
        than_chinh = next((l for l in lenh if l.id == nhom.than_chinh_lsx_id), None) or next(
            (l for l, tv in thanh_vien if tv.la_than_chinh), None)
        order_id = nhom.order_id
    else:
        l = sx.lsx(lsx_id) if lsx_id else None
        if l is None:
            return None
        lenh, dong_don, than_chinh, order_id = [l], {l.order_line_id}, l, l.order_id
    if not lenh:
        return None
    order = OrderRepository(db).get_by_id(order_id)
    if order is None:
        return None
    cums = [c for c in cum_ban(order) if any(ln.id in dong_don for ln in c.dong)]
    return _NguonNhom(order=order, lenh=lenh, than_chinh=than_chinh or lenh[0], cums=cums)


def _chia_theo_cum(so: float, cums: list[CumBan]) -> list[float]:
    """Chia `so` cho các cụm theo SL cụm / Σ SL; phần cuối nhận phần dư để tổng khớp tuyệt đối."""
    if len(cums) == 1:
        return [so]
    tong = sum(c.so_luong for c in cums)
    phan = [round(so * ((c.so_luong / tong) if tong > 0 else 1 / len(cums)), 2) for c in cums[:-1]]
    return phan + [so - sum(phan)]


# --- Ghi -----------------------------------------------------------------------------------------
def tao_yeu_cau_nhap_kho_cong_doan(db: Session, *, user, cong_viec_id: int) -> dict:
    """Nút "Tạo yêu cầu nhập kho" trên công đoạn KCS cuối — server tự tính phần đạt chưa gửi, KHÔNG
    nhận số từ client. Khoá dòng các lần kiểm TRƯỚC khi đọc số và tạo yêu cầu bằng
    `create(commit=False)` trong CÙNG giao dịch, để bấm đúp không đẻ hai yêu cầu. Báo kho sau commit."""
    gate_kcs(db, user)
    cv = SanXuatRepository(db).cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công đoạn.")
    if not cv.la_kcs_cuoi:
        raise ValueError("Chỉ công đoạn cuối của nhóm thành phẩm mới tạo yêu cầu nhập kho.")

    SanXuatKcsRepository(db).khoa_kcs_cua_cong_viec(cv.id)   # khoá TRƯỚC khi đọc — chặn bấm đúp
    dong = dong_nhap_kho_cua_cong_viec(db, [cv.id]).get(cv.id, [])
    con = so_con_gui_kho(db, cv, dong)
    if con <= _EPS:
        raise KhongConSoDuGuiKho("Không còn số đạt chưa gửi kho ở công đoạn này.")

    nguon = _nguon_nhom(db, nhom_id=cv.nhom_id, lsx_id=cv.lsx_id)
    if nguon is None or not nguon.cums:
        raise ValueError("Nhóm thành phẩm chưa nối được dòng đơn nào nên chưa thể nhập kho.")

    hang = _hang_service(db)
    don_vi_kcs = (cv.don_vi_ra or "").strip()
    # Gộp theo mã: hai cụm cùng tên khác SL ra CÙNG một thành phẩm — kho cấm hai dòng cùng món cùng lệnh.
    theo_ma: dict[int, dict] = {}
    for cum, sl_kcs in zip(nguon.cums, _chia_theo_cum(con, nguon.cums)):
        tp = khai_cum(db, nguon.order, cum)
        sl = round(sl_kcs * _he_so_cho_nhap(db, hang, tp, don_vi_kcs), 2)
        if sl <= 0:
            continue
        d = theo_ma.setdefault(tp.id, {"tp": tp, "sl": 0.0, "tien": 0.0, "du_gia": True})
        gia = gia_ban_cum(cum)
        d["sl"] += sl
        d["tien"] += sl * (gia or 0)
        d["du_gia"] = d["du_gia"] and gia is not None
    if not theo_ma:
        raise KhongConSoDuGuiKho("Không còn số đạt chưa gửi kho ở công đoạn này.")

    lines: list[dict] = []
    ra: list[dict] = []
    for d in theo_ma.values():
        tp, sl = d["tp"], round(d["sl"], 2)
        gia_ban = int(round(d["tien"] / d["sl"])) if d["du_gia"] and d["sl"] > 0 else None
        lines.append({"hang_loai": "vat_tu", "hang_id": tp.id, "lsx_id": nguon.than_chinh.id,
                      "dvt": tp.don_vi_gia, "sl_de_nghi": sl, "don_gia": 0, "don_gia_ban": gia_ban})
        ra.append({"hang_id": tp.id, "ma_hang": tp.ma, "ten_hang": tp.ten, "dvt": tp.don_vi_gia,
                   "sl_de_nghi": sl, "don_gia_ban": gia_ban})

    req_svc = _req_service(db, hang)
    ten = " + ".join(c.ten for c in nguon.cums)
    try:
        req = req_svc.create(
            user=user, loai=REQ_NHAP, lines=lines, commit=False,
            # Bộ phận = tổ của công đoạn cuối (không phải phòng của người bấm) — cùng luật đề nghị
            # vật tư: scope `department` của kho và ô "Bộ phận" trên bản in đọc cột này.
            bo_phan_id=cv.department_id or user.department_id,
            san_xuat_cong_viec_id=cv.id,
            ghi_chu=f"Nhập thành phẩm từ KCS · {nguon.than_chinh.ma} · {ten}"[:1000],
        )
    except StockRequestError as e:
        db.rollback()
        raise ValueError(str(e)) from None

    # ⚠️ `audit_repo.create` tự commit — đặt SAU khi yêu cầu đã flush để cả hai chốt chung một nhịp.
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_kho_yeu_cau_nhap",
        target=f"san_xuat_cong_viec:{cv.id}",
        detail=f"stock_request={req.id} ma={req.ma} so_luong_kcs={con:g}",
    )
    db.commit()
    req_svc.thong_bao_yeu_cau_moi(req)
    phat_su_kien_kho(req, bao_nguoi_tao=False)
    return {
        "request_id": req.id,
        "ma": req.ma,
        "cong_viec_id": cv.id,
        "so_luong": round(con, 3),
        "don_vi": don_vi_kcs or None,
        "dong": ra,
    }


def phat_su_kien_kho(req, *, bao_nguoi_tao: bool) -> None:
    """Yêu cầu nhập thành phẩm đổi (KCS vừa gửi / kho vừa ghi sổ phiếu nhập) → refresh màn KCS + hồ sơ
    lệnh; kho ghi sổ thì ĐẨY đích danh tới người KCS đã gửi (kho đã nhận tới đâu). Gọi SAU commit.
    Yêu cầu không có nguồn công đoạn KCS thì im lặng."""
    cv_id = getattr(req, "san_xuat_cong_viec_id", None)
    if not cv_id:
        return
    su_kien = {"cong_viec_id": cv_id, "request_id": req.id, "ma": req.ma, "trang_thai": req.trang_thai}
    hub.broadcast({"type": "san_xuat_kho_changed", **su_kien})
    if bao_nguoi_tao and req.nguoi_tao_id:
        hub.publish(req.nguoi_tao_id, {"type": "san_xuat_kho", **su_kien})


# --- Giao hàng: tồn thành phẩm của nhóm ------------------------------------------------------------
def ton_thanh_pham_cua_nhom(db: Session, nhom_id: int) -> dict:
    """Khối Giao hàng của Hồ sơ lệnh: mỗi cụm bán của nhóm = một món `TP-…`, tách theo KHO.

    Hai con số trên mỗi dòng (cùng hai số Giao hàng và kho tự kiểm, nên ba bên không vênh):
      · `so_luong` — tồn THẬT của món ở kho đó (lô khả dụng, `on_hand_by_kho`);
      · `so_toi_da` — trần lập phiếu = min(tồn ở kho đó, còn phải giao của dòng đầu cụm).

    `da_nhap_kho` = Σ kho đã nhận trên các yêu cầu NHẬP của công đoạn cuối nhóm (đơn vị món);
    `da_giao` = Σ đã thực nhận của dòng đầu mỗi cụm. Tồn là tồn của MÓN (mọi đơn cùng tên), không
    riêng nhóm này — kho giữ hàng theo mã, không theo lệnh. Hai cụm cùng tên (khác SL) là MỘT món:
    một dòng mỗi kho, còn phải giao cộng cả hai cụm.

    Chỉ ĐỌC: món chưa khai (đơn cũ trước khi có khai lúc chốt) thì coi như chưa có tồn, không đẻ mã.
    """
    from ..delivery_service import DeliveryService

    rong = {"nhom_id": nhom_id, "order_id": None, "order_line_ids": [], "so_lenh_trong_nhom": 0,
            "hang": [], "da_nhap_kho": 0.0, "da_giao": 0.0, "co_the_giao": False,
            "don_vi_lech": False}
    nguon = _nguon_nhom(db, nhom_id=nhom_id, lsx_id=None)
    if nguon is None:
        return rong
    order = nguon.order
    cv_ids = [cv.id for cv in SanXuatRepository(db).cong_viec_hien_tai_cua_nhom(nhom_id)
              if cv.la_kcs_cuoi]
    dong = [d for ds in dong_nhap_kho_cua_cong_viec(db, cv_ids).values() for d in ds]

    tp_theo_cum = [(cum, tp) for cum in nguon.cums if (tp := tim_theo_ten(db, cum.ten)) is not None]
    ton = StockLotRepository(db).on_hand_by_kho(list({("vat_tu", tp.id) for _, tp in tp_theo_cum}))
    ten_kho = KhoHangRepository(db).ten_theo_ids({k for per in ton.values() for k in per})
    con_giao = DeliveryService(DeliveryRepository(db), OrderRepository(db), None, None, None) \
        .con_phai_giao(order.id)
    da_giao_dong = DeliveryRepository(db).da_giao_theo_dong(order.id)
    bang_dv = DonViDoRepository(db).ten_theo_ma()

    theo_tp: dict[int, tuple] = {}
    for cum, tp in tp_theo_cum:
        _tp, con = theo_tp.get(tp.id, (tp, 0.0))
        theo_tp[tp.id] = (tp, con + float(con_giao.get(cum.dong_dau.id, 0)))

    hang: list[dict] = []
    for tp, con in theo_tp.values():
        for kho_id, sl in sorted(ton.get(("vat_tu", tp.id), {}).items()):
            hang.append({
                "hang_id": tp.id,
                "ma": tp.ma,
                "ten": tp.ten,
                "quy_cach": None,
                "don_vi": nhan_don_vi(bang_dv, tp.don_vi_gia),
                "kho_id": kho_id,
                "kho_ten": ten_kho.get(kho_id),
                "so_luong": round(sl, 3),
                "so_toi_da": round(max(0.0, min(sl, con)), 3),
                "khong_tinh_duoc": False,
            })
    return {
        "nhom_id": nhom_id,
        "order_id": order.id,
        "order_line_ids": sorted({ln.id for cum in nguon.cums for ln in cum.dong}),
        "so_lenh_trong_nhom": len(nguon.lenh),
        "hang": hang,
        "da_nhap_kho": round(sum(d.sl_da_nhan for d in dong), 3),
        "da_giao": float(sum(da_giao_dong.get(cum.dong_dau.id, 0) for cum in nguon.cums)),
        "co_the_giao": any(d["so_toi_da"] > _EPS for d in hang),
        "don_vi_lech": len({tp.don_vi_gia for _, tp in tp_theo_cum}) > 1,
    }
