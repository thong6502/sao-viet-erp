"""Kỹ thuật máy — service: phiếu sửa chữa · phiếu bảo trì · ảnh minh chứng.

Hai luật xương sống của module này, cả hai nằm ở ĐÂY chứ không ở router/FE:

1. **Đóng phiếu phải có ảnh.** `da_sua_xong` / `hoan_thanh` đòi ≥1 ảnh `giai_doan="sau"`. Không có
   cờ quyền nào bỏ qua được — cấp quyền "bỏ qua ảnh" cho một người là luật chết với tất cả.
2. **Chu kỳ bảo trì đọc từ MÁY, không lưu lại lần hai.** Nguồn là
   `may_thiet_bi.fields_theo_loai["lich_bao_tri"]` — gói `{id, viec, so, don_vi, ngay_bat_dau,
   hang_muc[]}` do người khai máy dựng ở tab "Lịch bảo trì". Phiếu chỉ neo `goi_id` + snapshot.

`han_ke_tiep` — chỗ hay bị hiểu nhầm nhất — chạy theo đúng ba nhánh:
  · gói ĐÃ có phiếu hoàn thành ⇒ ngày hoàn thành GẦN NHẤT + chu kỳ;
  · chưa có phiếu nào mà gói khai `ngay_bat_dau` ⇒ chính ngày đó (kỳ 1);
  · không có cả hai ⇒ KHÔNG đoán: trả `None` kèm lý do để màn hình nói thành lời "chưa khai Bắt
    đầu từ". (Bản đầu đoán là "tới hạn hôm nay" và một cú bấm đẻ ra 41 phiếu rác — xem ghi chú ở
    hằng số `NGUON_*` bên dưới. Đừng khôi phục.)
Mốc "lần cuối làm" KHÔNG ghi ngược vào JSON của máy: form Máy dựng lại `fields_theo_loai` từ bản
JSON nó đang giữ (`transformSubmit` bên FE), backend ghi vào đó là sớm muộn bị lưu đè mất.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.ky_thuat_may import (
    GIAI_DOAN,
    GIAI_DOAN_SAU,
    GIAI_DOAN_TRUOC,
    LOAI_BAO_TRI,
    LOAI_BT_DINH_KY,
    LOAI_PHIEU_BAO_TRI,
    LOAI_PHIEU_SUA_CHUA,
    MUC_DO,
    MUC_DO_TRUNG_BINH,
    TRANG_THAI_BAO_TRI,
    TRANG_THAI_SUA_CHUA,
    TT_BT_CHO_THUC_HIEN,
    TT_BT_HOAN_THANH,
    TT_SC_DA_SUA_XONG,
    BaoTriMay,
    SuaChuaMay,
)
from ..models.may_thiet_bi import MayThietBi
from ..repositories.ky_thuat_may_repo import KyThuatMayRepository

NHAT_KY_LOAI_SUA_CHUA = "ky_thuat_sua_chua"
NHAT_KY_LOAI_BAO_TRI = "ky_thuat_bao_tri"

# Lý do KHÔNG tính được hạn cho một gói — `han_ke_tiep` trả về kèm, để màn hình nói thành lời
# ("chưa khai Bắt đầu từ") thay vì im lặng bỏ gói đó ra khỏi lịch.
BO_QUA_THIEU_CHU_KY = "thieu_chu_ky"
BO_QUA_THIEU_NGAY_BAT_DAU = "thieu_ngay_bat_dau"

# Nguồn của hạn — để màn hình nói rõ "tính từ đâu" thay vì phun ra một ngày không ai kiểm được.
NGUON_PHIEU = "phieu"
NGUON_NGAY_BAT_DAU = "ngay_bat_dau"


# Sentinel: phân biệt "chưa nạp mốc, tự đi hỏi DB" với "đã nạp rồi, gói này KHÔNG có mốc" (None).
_CHUA_NAP = object()


class KyThuatMayError(Exception):
    pass


class KyThuatMayNotFound(KyThuatMayError):
    pass


class KyThuatMayValidationError(KyThuatMayError):
    pass


class KyThuatMayThieuAnh(KyThuatMayError):
    """Đóng phiếu khi chưa có ảnh chứng thực — 409, không phải 422: dữ liệu gửi lên hợp lệ, chỉ là
    TRẠNG THÁI chưa cho đóng."""


class KyThuatMayChuaXongViec(KyThuatMayError):
    """Đóng phiếu bảo trì khi checklist còn việc chưa tick và cũng chưa đánh "không áp dụng".

    Cùng hạng với cửa ảnh (409): trước 14/08/2026 khối "Điều kiện xác nhận" ngoài màn hình liệt kê
    checklist như một điều kiện nhưng chỉ ẢNH mới thật sự chặn — nhìn như luật mà không phải luật.
    """


def _f(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# Giờ NHÀ MÁY, không phải UTC. Cùng chuẩn với `sequence_service.BUSINESS_TZ` / `attendance_service
# .VN_TZ`. Chỗ này từng lệch: service+router tính "hôm nay" bằng UTC còn repo dùng `date.today()`
# (giờ máy chủ) — container VPS chạy UTC nên từ 0h đến 7h sáng giờ VN cả hệ vẫn tưởng là HÔM QUA:
# ticker chưa sinh phiếu của kỳ hôm nay, badge chưa đếm, cờ `qua_han` trễ một ngày, và thợ ca đêm
# bấm "Xác nhận đã bảo trì xong" với ngày mặc định (trình duyệt lấy giờ VN) thì bị 422 "ngày ở
# tương lai". Một nguồn duy nhất, mọi tầng gọi hàm này.
BUSINESS_TZ = timezone(timedelta(hours=7))


def hom_nay_vn() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _hom_nay() -> date:
    return hom_nay_vn()


def _parse_date(v: Any) -> date | None:
    """Ngày từ JSON là chuỗi `yyyy-mm-dd` (ô <input type="date">). Chuỗi rác thì trả None chứ không
    nổ — dữ liệu này người dùng gõ tay vào một ô JSON tự do."""
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str) and v.strip():
        try:
            return date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


def _cong_thang(moc: date, n: int) -> date:
    """Cộng tháng có CHẶN NGÀY CUỐI: 31/01 + 1 tháng = 28/02, không phải 03/03."""
    thang = moc.month - 1 + n
    nam = moc.year + thang // 12
    thang = thang % 12 + 1
    ngay = min(moc.day, calendar.monthrange(nam, thang)[1])
    return date(nam, thang, ngay)


CHU_KY_NGAY = "ngay"
CHU_KY_TUAN = "tuan"
CHU_KY_THANG = "thang"
CHU_KY_NAM = "nam"
CHU_KY_DON_VI = (CHU_KY_NGAY, CHU_KY_TUAN, CHU_KY_THANG, CHU_KY_NAM)


def cong_chu_ky(moc: date, so: float, don_vi: str | None) -> date:
    """`moc` + `so` × đơn vị. Chu kỳ lẻ (2,5 tháng) làm tròn — không ai khai bảo trì kiểu đó, mà
    giữ số lẻ thì hạn rơi vào ngày không giải thích được."""
    n = max(1, int(round(_f(so, 1))))
    if don_vi == CHU_KY_TUAN:
        return moc + timedelta(weeks=n)
    if don_vi == CHU_KY_THANG:
        return _cong_thang(moc, n)
    if don_vi == CHU_KY_NAM:
        return _cong_thang(moc, n * 12)
    # "ngay" + mọi giá trị lạ. Đường lui này CỐ Ý giữ cho gói đã khai từ trước: chặn ở đây là gói
    # biến mất khỏi lịch không một lời nào. Cửa chặn đặt ở chỗ NGƯỜI GÕ (`_validate_chu_ky`), nơi
    # còn nói được "đơn vị không hợp lệ" cho đúng người đang sửa.
    return moc + timedelta(days=n)


def goi_bao_tri_cua(may: Any) -> list[dict]:
    # `may` là bản ghi máy HOẶC hàng rút gọn từ `_may_co_lich()` — cả hai đều có `.fields_theo_loai`.
    """Danh sách GÓI bảo trì đã khai trên máy. Dữ liệu nằm trong cột JSON tự do nên phải phòng thủ:
    khoá thiếu / kiểu sai vẫn phải trả về danh sách chạy được."""
    box = may.fields_theo_loai if isinstance(may.fields_theo_loai, dict) else {}
    raw = box.get("lich_bao_tri")
    if not isinstance(raw, list):
        return []
    return [g for g in raw if isinstance(g, dict)]


def hang_muc_snapshot(goi: dict) -> list[dict]:
    """Chụp lại việc con lúc SINH phiếu: người khai sửa gói về sau không làm đổi nội dung việc đã
    giao. Bỏ dòng chưa đặt tên — giao cho thợ một ô trắng thì không ai biết phải làm gì."""
    raw = goi.get("hang_muc")
    if not isinstance(raw, list):
        return []
    out = []
    for h in raw:
        if not isinstance(h, dict):
            continue
        ten = (h.get("ten") or "").strip()
        if not ten:
            continue
        out.append({"id": h.get("id"), "ten": ten, "xong": False})
    return out


class KyThuatMayService:
    def __init__(self, db: Session, repo: KyThuatMayRepository, audit=None) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit

    # ================= dùng chung =================

    def _ghi(self, loai: str, obj_id: int, action: str, detail: str, actor_id: int | None) -> None:
        if self.audit is None:
            return
        self.audit.create(
            actor_user_id=actor_id, action=action, target=f"{loai}:{obj_id}", detail=detail,
        )

    def _may(self, may_id: int) -> MayThietBi:
        may = self.db.get(MayThietBi, may_id)
        if may is None:
            raise KyThuatMayValidationError("Không tìm thấy máy.")
        return may

    def may_map(self, may_ids: list[int]) -> dict[int, dict]:
        """{may_id: {ma, ten, loai_may}} cho cả trang danh sách — tránh N+1 khi vẽ cột Máy."""
        ids = [i for i in dict.fromkeys(may_ids) if i]
        if not ids:
            return {}
        rows = self.db.execute(
            select(MayThietBi.id, MayThietBi.ma, MayThietBi.ten, MayThietBi.loai_may)
            .where(MayThietBi.id.in_(ids))
        ).all()
        return {int(r[0]): {"ma": r[1], "ten": r[2], "loai_may": r[3]} for r in rows}

    def _kiem_anh_chung_thuc(self, loai_phieu: str, phieu_id: int) -> None:
        if self.repo.dem_anh_sau(loai_phieu, phieu_id) < 1:
            raise KyThuatMayThieuAnh(
                "Cần ít nhất 1 ảnh chứng thực sau khi làm xong mới xác nhận được."
            )

    # ================= Phiếu sửa chữa =================

    def get_sua_chua(self, phieu_id: int) -> SuaChuaMay:
        phieu = self.repo.get_sua_chua(phieu_id)
        if phieu is None:
            raise KyThuatMayNotFound("Không tìm thấy phiếu sửa chữa.")
        return phieu

    def list_sua_chua(self, **kw):
        return self.repo.list_sua_chua(**kw)

    def dem_sua_chua(self, **kw) -> dict[str, int]:
        """Số cho dãy tab — nhận CÙNG bộ lọc với `list_sua_chua` (trừ trạng thái)."""
        return self.repo.dem_sua_chua(**kw)

    def _validate_sua_chua(self, data: dict) -> None:
        if not data.get("may_id"):
            raise KyThuatMayValidationError("Chưa chọn máy.")
        if not (data.get("bo_phan_hong") or "").strip():
            raise KyThuatMayValidationError("Chưa ghi bộ phận hỏng.")
        muc_do = data.get("muc_do")
        if muc_do and muc_do not in MUC_DO:
            raise KyThuatMayValidationError(f"Mức độ không hợp lệ: {muc_do}")

    def _validate_chu_ky(self, data: dict) -> None:
        """Đơn vị chu kỳ do client gửi lên. `cong_chu_ky` coi mọi giá trị lạ là NGÀY, nên không chặn
        ở đây thì một phiếu khai "quý" lặng lẽ thành chu kỳ 1 ngày và kỳ kế tiếp sai hẳn một mùa."""
        don_vi = data.get("chu_ky_don_vi")
        if don_vi and don_vi not in CHU_KY_DON_VI:
            raise KyThuatMayValidationError(
                f"Đơn vị chu kỳ không hợp lệ: {don_vi} (nhận: {', '.join(CHU_KY_DON_VI)})"
            )

    def tao_sua_chua(self, data: dict, *, actor_id: int | None = None) -> SuaChuaMay:
        self._validate_sua_chua(data)
        may = self._may(int(data["may_id"]))
        data = {**data, "muc_do": data.get("muc_do") or MUC_DO_TRUNG_BINH}
        phieu = self.repo.create_sua_chua(data, ma=self.repo.next_ma_sua_chua())
        self._ghi(NHAT_KY_LOAI_SUA_CHUA, phieu.id, "create",
                  f"{phieu.ma} · {may.ma} · {phieu.bo_phan_hong}", actor_id)
        return phieu

    def sua_sua_chua(self, phieu_id: int, data: dict, *, actor_id: int | None = None) -> SuaChuaMay:
        phieu = self.get_sua_chua(phieu_id)
        if phieu.trang_thai == TT_SC_DA_SUA_XONG:
            raise KyThuatMayValidationError("Phiếu đã đóng — không sửa được nữa.")
        if "may_id" in data or "bo_phan_hong" in data:
            self._validate_sua_chua({**{"may_id": phieu.may_id,
                                        "bo_phan_hong": phieu.bo_phan_hong}, **data})
        # Đổi sang máy KHÔNG CÓ THẬT thì trước đây lọt: `_validate_sua_chua` chỉ xem ô có trống
        # không. Phiếu neo vào id máy đã xoá là cột Máy trống trơn và không ai lần ra được máy nào.
        if data.get("may_id") and int(data["may_id"]) != phieu.may_id:
            self._may(int(data["may_id"]))
        phieu = self.repo.update_sua_chua(phieu, data)
        self._ghi(NHAT_KY_LOAI_SUA_CHUA, phieu.id, "update", f"{phieu.ma} · sửa nội dung", actor_id)
        return phieu

    def doi_trang_thai_sua_chua(self, phieu_id: int, trang_thai: str, *,
                                actor_id: int | None = None) -> SuaChuaMay:
        """Chuyển bước. ĐÓNG phiếu (`da_sua_xong`) đi qua đây và bị cửa ảnh chặn."""
        if trang_thai not in TRANG_THAI_SUA_CHUA:
            raise KyThuatMayValidationError(f"Trạng thái không hợp lệ: {trang_thai}")
        phieu = self.get_sua_chua(phieu_id)
        if trang_thai == TT_SC_DA_SUA_XONG:
            self._kiem_anh_chung_thuc(LOAI_PHIEU_SUA_CHUA, phieu.id)
            phieu.hoan_thanh_at = datetime.now(timezone.utc)
            phieu.hoan_thanh_boi = actor_id
        else:
            # Mở lại phiếu đã đóng thì phải dọn mốc, không thì phiếu "đang sửa" vẫn mang giờ hoàn
            # thành cũ và mọi báo cáo đọc theo mốc đó đều sai.
            phieu.hoan_thanh_at = None
            phieu.hoan_thanh_boi = None
        phieu.trang_thai = trang_thai
        self.db.commit()
        self.db.refresh(phieu)
        self._ghi(NHAT_KY_LOAI_SUA_CHUA, phieu.id, "update",
                  f"{phieu.ma} · trạng thái → {trang_thai}", actor_id)
        return phieu


    # ================= Phiếu bảo trì =================

    def get_bao_tri(self, phieu_id: int) -> BaoTriMay:
        phieu = self.repo.get_bao_tri(phieu_id)
        if phieu is None:
            raise KyThuatMayNotFound("Không tìm thấy phiếu bảo trì.")
        return phieu

    def list_bao_tri(self, **kw):
        return self.repo.list_bao_tri(hom_nay=hom_nay_vn(), **kw)

    def dem_bao_tri(self, **kw) -> dict[str, int]:
        """Số cho dãy tab — nhận CÙNG bộ lọc với `list_bao_tri` (trừ trạng thái)."""
        return self.repo.dem_bao_tri(hom_nay=hom_nay_vn(), **kw)

    def dem_den_han(self) -> tuple[int, int]:
        """(tới hạn còn dở, trong đó quá hạn) — badge cạnh mục "Phiếu bảo trì" trên thanh bên."""
        dem = self.repo.dem_bao_tri(hom_nay=hom_nay_vn())
        return dem.get("den_hom_nay", 0), dem.get("qua_han", 0)

    def tao_bao_tri(self, data: dict, *, actor_id: int | None = None) -> BaoTriMay:
        """Tạo phiếu. Hai lối vào, cùng một hàm:

        · **đột xuất** — người dùng bấm "Tạo phiếu", không có `goi_id`;
        · **định kỳ** — bấm một ô KỲ DỰ KIẾN trên lịch, có `goi_id` ⇒ chép luôn chu kỳ + việc con
          của gói. (Nút "Sinh phiếu từ lịch" quét-cả-loạt đã gỡ 12/08/2026.)
        """
        if not data.get("may_id"):
            raise KyThuatMayValidationError("Chưa chọn máy.")
        self._validate_chu_ky(data)
        ngay = _parse_date(data.get("ngay_ke_hoach")) or _hom_nay()
        loai = data.get("loai") or LOAI_BT_DINH_KY
        if loai not in LOAI_BAO_TRI:
            raise KyThuatMayValidationError(f"Loại bảo trì không hợp lệ: {loai}")
        may = self._may(int(data["may_id"]))
        payload = {**data, "ngay_ke_hoach": ngay, "loai": loai}
        # Lập tay theo một gói có sẵn ⇒ chép luôn chu kỳ + việc con của gói đó, khỏi gõ lại.
        goi_id = (data.get("goi_id") or "").strip() or None
        if goi_id:
            goi = next((g for g in goi_bao_tri_cua(may) if g.get("id") == goi_id), None)
            if goi is not None:
                payload.setdefault("goi_ten", (goi.get("viec") or "").strip() or None)
                payload.setdefault("chu_ky_so", goi.get("so"))
                payload.setdefault("chu_ky_don_vi", goi.get("don_vi"))
                if not payload.get("hang_muc"):
                    payload["hang_muc"] = hang_muc_snapshot(goi)
        phieu = self.repo.create_bao_tri(payload, ma=self.repo.next_ma_bao_tri())
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "create",
                  f"{phieu.ma} · {may.ma} · {phieu.goi_ten or 'đột xuất'}", actor_id)
        return phieu

    def sua_bao_tri(self, phieu_id: int, data: dict, *, actor_id: int | None = None) -> BaoTriMay:
        phieu = self.get_bao_tri(phieu_id)
        if phieu.trang_thai == TT_BT_HOAN_THANH:
            raise KyThuatMayValidationError("Phiếu đã hoàn thành — không sửa được nữa.")
        self._validate_chu_ky(data)
        data = dict(data)
        # Đổi ngày ở đây là SỬA nội dung, không phải "dời lịch" (dời lịch bắt buộc có lý do và đi
        # qua `doi_lich`). Chặn để hai đường không đá nhau.
        data.pop("ngay_ke_hoach", None)
        phieu = self.repo.update_bao_tri(phieu, data)
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update", f"{phieu.ma} · sửa nội dung", actor_id)
        return phieu

    def tick_hang_muc(self, phieu_id: int, hang_muc_id: str, xong: bool, *,
                      bo_qua: bool | None = None, ly_do: str | None = None,
                      actor_id: int | None = None) -> BaoTriMay:
        """Tick một việc con, hoặc đánh việc đó là "không áp dụng lần này" kèm lý do.

        Đường "không áp dụng" tồn tại vì checklist nay là CỬA CHẶN: bắt tick hết mà không chừa lối
        cho việc thật sự không phải làm (gói chung cho 3 máy, kỳ này máy không có bộ phận đó) thì
        thợ sẽ tick bừa — và cái checklist mất sạch giá trị. Lý do là bắt buộc, ghi thẳng vào JSON
        `hang_muc` nên KHÔNG cần cột mới.
        """
        phieu = self.get_bao_tri(phieu_id)
        if phieu.trang_thai == TT_BT_HOAN_THANH:
            raise KyThuatMayValidationError("Phiếu đã hoàn thành — không đổi checklist nữa.")
        rows = phieu.hang_muc if isinstance(phieu.hang_muc, list) else []
        # Kiểm TỒN TẠI riêng, đừng suy từ "danh sách mới có khác danh sách cũ không": tick lại đúng
        # giá trị đang có thì hai danh sách giống hệt nhau và người dùng nhận về câu "không tìm thấy
        # hạng mục" — sai hoàn toàn với việc họ vừa làm.
        if not any(isinstance(h, dict) and h.get("id") == hang_muc_id for h in rows):
            raise KyThuatMayValidationError("Không tìm thấy hạng mục trong phiếu.")

        if bo_qua:
            ly_do_sach = (ly_do or "").strip()
            if not ly_do_sach:
                raise KyThuatMayValidationError(
                    "Phải ghi lý do khi đánh dấu hạng mục là không áp dụng."
                )
            thay = {"xong": False, "bo_qua": True, "ly_do_bo_qua": ly_do_sach[:200]}
        else:
            # Tick (hoặc bỏ tick) là quay về luồng thường ⇒ nhả luôn dấu "không áp dụng".
            thay = {"xong": bool(xong), "bo_qua": False, "ly_do_bo_qua": None}

        # ⚠️ Phải gán LIST MỚI: sửa tại chỗ phần tử của cột JSON thì SQLAlchemy không thấy gì thay
        # đổi và lặng lẽ không UPDATE (tick xong, F5 lại mất sạch).
        moi = [
            {**h, **thay} if isinstance(h, dict) and h.get("id") == hang_muc_id else h
            for h in rows
        ]
        phieu.hang_muc = moi
        self.db.commit()
        self.db.refresh(phieu)
        ten_viec = next(
            (h.get("ten") for h in moi if isinstance(h, dict) and h.get("id") == hang_muc_id), ""
        )
        dau = f"⊘ (không áp dụng: {thay['ly_do_bo_qua']})" if bo_qua else ("✓" if xong else "✗")
        # Ghi vết TỪNG việc con: đây là thứ trả lời "hôm đó thợ đã làm những gì" khi máy hỏng lại
        # ngay sau kỳ bảo trì. Không ghi thì checklist chỉ còn là mấy ô tick không ai truy được.
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update",
                  f"{phieu.ma} · {dau} {ten_viec}", actor_id)
        return phieu

    def doi_lich(self, phieu_id: int, ngay_moi: Any, ly_do: str, *,
                 actor_id: int | None = None) -> BaoTriMay:
        """Dời ngày kế hoạch. Bắt buộc lý do: một phiếu bị dời ba lần không kèm chữ nào thì tháng
        sau không ai giải thích được vì sao máy chưa được bảo trì."""
        phieu = self.get_bao_tri(phieu_id)
        if phieu.trang_thai == TT_BT_HOAN_THANH:
            raise KyThuatMayValidationError("Phiếu đã hoàn thành — không dời lịch được.")
        ngay = _parse_date(ngay_moi)
        if ngay is None:
            raise KyThuatMayValidationError("Ngày dời không hợp lệ.")
        if not (ly_do or "").strip():
            raise KyThuatMayValidationError("Phải ghi lý do dời lịch.")
        cu = phieu.ngay_ke_hoach
        if phieu.ngay_ke_hoach_goc is None:
            phieu.ngay_ke_hoach_goc = cu
        phieu.ngay_ke_hoach = ngay
        phieu.ly_do_doi = ly_do.strip()[:300]
        self.db.commit()
        self.db.refresh(phieu)
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update",
                  f"{phieu.ma} · dời {cu:%d/%m/%Y} → {ngay:%d/%m/%Y} · {phieu.ly_do_doi}", actor_id)
        return phieu

    @staticmethod
    def hang_muc_con_lai(phieu: BaoTriMay) -> list[str]:
        """Tên các việc con CHƯA xong và cũng chưa đánh "không áp dụng"."""
        rows = phieu.hang_muc if isinstance(phieu.hang_muc, list) else []
        return [
            (h.get("ten") or "việc chưa đặt tên")
            for h in rows
            if isinstance(h, dict) and not h.get("xong") and not h.get("bo_qua")
        ]

    def _kiem_checklist(self, phieu: BaoTriMay) -> None:
        """Cửa thứ hai (cùng hạng với cửa ảnh): còn việc con chưa tick thì chưa đóng phiếu được.

        Phiếu không có checklist (đột xuất, hoặc gói không khai việc con) thì cửa này không chặn gì.
        """
        con = self.hang_muc_con_lai(phieu)
        if not con:
            return
        ke = ", ".join(con[:3]) + ("…" if len(con) > 3 else "")
        raise KyThuatMayChuaXongViec(
            f"Còn {len(con)} hạng mục chưa làm ({ke}). Tick xong, hoặc đánh dấu "
            f'"không áp dụng" kèm lý do.'
        )

    def _ten_user(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        from ..models.user import User
        return self.db.execute(select(User.name).where(User.id == user_id)).scalar()

    def doi_trang_thai_bao_tri(self, phieu_id: int, trang_thai: str, *,
                               ngay_hoan_thanh: Any = None,
                               actor_id: int | None = None) -> BaoTriMay:
        if trang_thai not in TRANG_THAI_BAO_TRI:
            raise KyThuatMayValidationError(f"Trạng thái không hợp lệ: {trang_thai}")
        phieu = self.get_bao_tri(phieu_id)

        # NGƯỜI LÀM = người bấm XÁC NHẬN XONG. Không có bước nhận việc, nên cũng không có chuyện
        # "giữ người nhận cũ": ai ký cái phiếu này thì tên người đó nằm trên phiếu.
        if trang_thai == TT_BT_HOAN_THANH:
            phieu.nguoi_thuc_hien_id = actor_id
            phieu.nguoi_thuc_hien = self._ten_user(actor_id)
        else:
            # Mở lại phiếu về hàng chờ ⇒ nhả tên, không để phiếu "chờ làm" mà vẫn mang tên ai đó.
            phieu.nguoi_thuc_hien_id = None
            phieu.nguoi_thuc_hien = None

        if trang_thai == TT_BT_HOAN_THANH:
            self._kiem_checklist(phieu)
            self._kiem_anh_chung_thuc(LOAI_PHIEU_BAO_TRI, phieu.id)
            # Cho khai ngày làm THẬT (thợ làm thứ Bảy, thứ Hai mới vào bấm) — đây là mốc tính kỳ
            # sau nên lấy giờ bấm nút là đẩy lệch cả chuỗi kỳ về sau.
            ngay = _parse_date(ngay_hoan_thanh) or _hom_nay()
            # ...nhưng chỉ lùi về QUÁ KHỨ. Không ai hoàn thành được việc chưa làm, mà nhận ngày mai
            # thì phiếu thành đã-xong trong khi máy chưa ai đụng, và kỳ kế tiếp bị đẩy lùi theo.
            if ngay > _hom_nay():
                raise KyThuatMayValidationError(
                    "Ngày hoàn thành không được ở tương lai — chỉ ghi ngày đã làm xong thật."
                )
            phieu.ngay_hoan_thanh = ngay
            phieu.hoan_thanh_boi = actor_id
        else:
            phieu.ngay_hoan_thanh = None
            phieu.hoan_thanh_boi = None
        phieu.trang_thai = trang_thai
        self.db.commit()
        self.db.refresh(phieu)
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update",
                  f"{phieu.ma} · trạng thái → {trang_thai}", actor_id)
        return phieu


    # ================= Lịch bảo trì của MÁY → hạn & sinh phiếu =================

    def han_ke_tiep(self, may_id: int, goi: dict, *, moc: Any = _CHUA_NAP) -> tuple[date | None, str]:
        """(hạn, nguồn). `hạn = None` ⇒ KHÔNG tính được, và lý do nằm ở `nguồn`:

          · `thieu_chu_ky`      — gói khai tên nhưng bỏ trống "Mỗi … tháng";
          · `thieu_ngay_bat_dau` — có chu kỳ nhưng chưa từng làm lần nào VÀ chưa khai "Bắt đầu từ",
            nên không có gốc để cộng chu kỳ. KHÔNG đoán là hôm nay (xem ghi chú ở đầu file).

        `moc` = ngày hoàn thành gần nhất của gói. Người gọi duyệt NHIỀU gói (lịch, ticker) truyền
        sẵn từ `repo.moc_hoan_thanh_map()` để khỏi hỏi DB từng gói; bỏ trống thì hàm tự hỏi.
        """
        so = _f(goi.get("so"))
        if so <= 0:
            return None, BO_QUA_THIEU_CHU_KY
        goi_id = (goi.get("id") or "").strip()
        if moc is _CHUA_NAP:
            moc = self.repo.ngay_hoan_thanh_gan_nhat(may_id, goi_id) if goi_id else None
        if moc is not None:
            return cong_chu_ky(moc, so, goi.get("don_vi")), NGUON_PHIEU
        bat_dau = _parse_date(goi.get("ngay_bat_dau"))
        if bat_dau is not None:
            return bat_dau, NGUON_NGAY_BAT_DAU
        return None, BO_QUA_THIEU_NGAY_BAT_DAU

    def _may_co_lich(self):
        """Máy kèm túi JSON lịch bảo trì — CHỈ 5 cột cần dùng, không nạp cả bản ghi máy (máy in có
        vài chục field thông số). Lịch và ticker đều duyệt qua đây."""
        return self.db.execute(
            select(
                MayThietBi.id, MayThietBi.ma, MayThietBi.ten,
                MayThietBi.loai_may, MayThietBi.fields_theo_loai,
            ).order_by(MayThietBi.ma.asc())
        ).all()

    def han_cua_may(self, may_id: int) -> list[dict]:
        """Hạn kế tiếp từng gói của MỘT máy — tab "Lịch bảo trì" ở màn Thiết bị đọc cái này."""
        may = self._may(may_id)
        # Nạp sẵn cho RIÊNG máy này (2 query) thay vì hỏi 2 query cho mỗi gói — máy 5 gói từng tốn
        # 10 query. Cùng đường với `lich()`, không đẻ cơ chế thứ hai.
        moc_map = self.repo.moc_hoan_thanh_map(may_id)
        mo_map = self.repo.phieu_dang_mo_map(may_id)
        out: list[dict] = []
        for goi in goi_bao_tri_cua(may):
            goi_id_raw = (goi.get("id") or "").strip()
            han, nguon = self.han_ke_tiep(may_id, goi, moc=moc_map.get((may_id, goi_id_raw)))
            goi_id = goi_id_raw or None
            mo = mo_map.get((may_id, goi_id_raw)) if goi_id else None
            out.append({
                "goi_id": goi_id,
                "goi_ten": (goi.get("viec") or "").strip() or None,
                "han": han,
                "nguon": nguon,
                "phieu_dang_mo_id": mo.id if mo is not None else None,
            })
        return out

    def lich(self, tu: date, den: date) -> dict:
        """Dữ liệu cho màn LỊCH: phiếu THẬT + kỳ DỰ KIẾN chưa sinh phiếu, trong khoảng [tu, den].

        Kỳ dự kiến **không lưu ở đâu cả** — tính lúc đọc từ chu kỳ gói. Nhờ vậy sửa chu kỳ ở màn
        Thiết bị là lịch đổi theo ngay, không có bảng thứ hai để lệch.

        Mốc bắt đầu chuỗi dự kiến:
          · gói đang có phiếu MỞ ⇒ kỳ kế tiếp tính từ ngày kế hoạch của phiếu đó (kỳ này đã thành
            phiếu thật rồi, vẽ thêm một chấm mờ chồng lên là nói dối);
          · còn lại ⇒ từ `han_ke_tiep`.
        """
        phieu = list(self.db.execute(
            select(BaoTriMay)
            .where(BaoTriMay.ngay_ke_hoach >= tu, BaoTriMay.ngay_ke_hoach <= den)
            .order_by(BaoTriMay.ngay_ke_hoach.asc(), BaoTriMay.id.asc())
        ).scalars())

        # Nạp SẴN hai bảng tra thay vì hỏi lẻ từng gói: 40 máy × 3 gói từng là ~240 query cho một
        # lần mở lịch (mà Lịch là view mặc định), nay là 2 query cố định dù bao nhiêu máy.
        moc_map = self.repo.moc_hoan_thanh_map()
        mo_map = self.repo.phieu_dang_mo_map()

        du_kien: list[dict] = []
        for may in self._may_co_lich():
            for goi in goi_bao_tri_cua(may):
                so = _f(goi.get("so"))
                if so <= 0:
                    continue                      # chưa khai chu kỳ ⇒ không đoán được kỳ nào
                goi_id = (goi.get("id") or "").strip()
                don_vi = goi.get("don_vi")
                han, _ = self.han_ke_tiep(may.id, goi, moc=moc_map.get((may.id, goi_id)))
                if han is None:
                    continue
                mo = mo_map.get((may.id, goi_id)) if goi_id else None
                moc = cong_chu_ky(mo.ngay_ke_hoach, so, don_vi) if mo is not None else han
                # Cap 60 mốc/gói: chu kỳ 1 ngày mà xem cả năm là 365 chấm trên một lịch tháng —
                # vẽ ra cũng không ai đọc được, mà vòng lặp thì tốn thật.
                for _ in range(60):
                    if moc > den:
                        break
                    if moc >= tu:
                        du_kien.append({
                            "may_id": may.id, "may_ma": may.ma, "may_ten": may.ten,
                            "may_loai": may.loai_may,
                            "goi_id": goi_id or None,
                            "goi_ten": (goi.get("viec") or "").strip() or None,
                            "ngay": moc, "chu_ky_so": so, "chu_ky_don_vi": don_vi,
                        })
                    moc = cong_chu_ky(moc, so, don_vi)
        return {"phieu": phieu, "du_kien": du_kien}

    def sinh_phieu_den_han(self, *, hom_nay: date | None = None,
                           actor_id: int | None = None) -> list[BaoTriMay]:
        """ĐẾN NGÀY thì tự đẻ phiếu — ticker nền gọi mỗi vòng, không ai phải bấm nút.

        Khác hẳn nút "Sinh phiếu từ lịch" đã gỡ, dù cùng đọc một nguồn:

        · nút cũ là NGƯỜI bấm một phát quét sạch mọi máy × mọi gói, kể cả kỳ còn xa và gói khai
          thiếu mốc ⇒ 41 phiếu rác trong một cú bấm;
        · hàm này chạy theo NGÀY: chỉ gói đã TỚI HẠN mới ra phiếu, mỗi gói đúng một cái, và gói
          chưa khai chu kỳ / chưa khai "Bắt đầu từ" thì `han_ke_tiep` trả None ⇒ bỏ qua.

        Idempotent: gói còn phiếu ĐANG MỞ thì thôi. Nhờ vậy ticker chạy 10 phút/lần cả ngày cũng
        chỉ ra một phiếu cho mỗi kỳ.
        """
        hom_nay = hom_nay or _hom_nay()
        moc_map = self.repo.moc_hoan_thanh_map()
        mo_map = self.repo.phieu_dang_mo_map()
        ra: list[BaoTriMay] = []
        for may in self._may_co_lich():
            for goi in goi_bao_tri_cua(may):
                goi_id = (goi.get("id") or "").strip()
                han, _ = self.han_ke_tiep(may.id, goi, moc=moc_map.get((may.id, goi_id)))
                if han is None or han > hom_nay:
                    continue
                if goi_id and mo_map.get((may.id, goi_id)) is not None:
                    continue
                phieu = self.repo.create_bao_tri({
                    "may_id": may.id,
                    "goi_id": goi_id or None,
                    "goi_ten": (goi.get("viec") or "").strip() or None,
                    "chu_ky_so": goi.get("so"),
                    "chu_ky_don_vi": goi.get("don_vi"),
                    "loai": LOAI_BT_DINH_KY,
                    "ngay_ke_hoach": han,
                    "hang_muc": hang_muc_snapshot(goi),
                    # Một vòng quét có thể ra nhiều phiếu ⇒ chốt MỘT lần ở cuối, không commit lẻ
                    # từng cái (xem `repo.create_bao_tri`).
                }, ma=self.repo.next_ma_bao_tri(), commit=False)
                ra.append(phieu)
                # Ghi ngay vào bảng tra: bảng này nạp MỘT lần đầu vòng lặp, không cập nhật thì gói
                # vừa ra phiếu vẫn bị coi là "chưa có phiếu mở" ở các nhánh sau.
                if goi_id:
                    mo_map[(may.id, goi_id)] = phieu
                self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "create",
                          f"{phieu.ma} · tự sinh khi tới hạn · {may.ma} · "
                          f"{(goi.get('viec') or '').strip() or 'gói chưa đặt tên'}", actor_id)
        if ra:
            # Chốt MỘT lần cho cả loạt: hoặc cả kỳ hôm nay ra phiếu, hoặc không phiếu nào —
            # không để lại nửa vời khi vòng quét gãy giữa chừng.
            self.db.commit()
            for p in ra:
                self.db.refresh(p)
        return ra

    # `don_phieu_chua_dung()` cũng gỡ theo: nó chỉ tồn tại để hốt đống rác của cái nút trên. Phiếu
    # lẻ tạo nhầm thì mở ra bấm "Xoá phiếu" — không cần một lệnh xoá-hàng-loạt nằm chờ sẵn.

    # ================= Ảnh =================

    def list_anh(self, loai_phieu: str, phieu_id: int):
        return self.repo.list_anh(loai_phieu, phieu_id)

    def them_anh(self, loai_phieu: str, phieu_id: int, *, giai_doan: str,
                 file_name: str, file_url: str, file_type: str | None,
                 actor_id: int | None = None):
        if giai_doan not in GIAI_DOAN:
            raise KyThuatMayValidationError(f"Giai đoạn ảnh không hợp lệ: {giai_doan}")
        anh = self.repo.add_anh(
            loai_phieu=loai_phieu, phieu_id=phieu_id, giai_doan=giai_doan,
            file_name=file_name, file_url=file_url, file_type=file_type, uploaded_by=actor_id,
        )
        # Ảnh là BẰNG CHỨNG của phiếu ⇒ ai thêm, ai gỡ đều phải có vết. Không ghi thì một tấm ảnh
        # chứng thực biến mất mà không ai truy được là do đâu.
        self._ghi(self._nhat_ky_loai(loai_phieu), phieu_id, "update",
                  f"thêm ảnh {'hiện trạng' if giai_doan == GIAI_DOAN_TRUOC else 'chứng thực'}: {file_name}",
                  actor_id)
        return anh

    @staticmethod
    def _nhat_ky_loai(loai_phieu: str) -> str:
        return (NHAT_KY_LOAI_SUA_CHUA if loai_phieu == LOAI_PHIEU_SUA_CHUA
                else NHAT_KY_LOAI_BAO_TRI)

    def xoa_anh(self, anh_id: int, *, actor_id: int | None = None):
        anh = self.repo.get_anh(anh_id)
        if anh is None:
            raise KyThuatMayNotFound("Không tìm thấy ảnh.")
        # Gỡ ảnh chứng thực của phiếu ĐÃ đóng là làm rỗng bằng chứng của một việc đã ký — chặn.
        if anh.giai_doan == GIAI_DOAN_SAU:
            if anh.loai_phieu == LOAI_PHIEU_SUA_CHUA:
                p = self.repo.get_sua_chua(anh.phieu_id)
                if p is not None and p.trang_thai == TT_SC_DA_SUA_XONG:
                    raise KyThuatMayValidationError("Phiếu đã đóng — không gỡ ảnh chứng thực được.")
            else:
                p = self.repo.get_bao_tri(anh.phieu_id)
                if p is not None and p.trang_thai == TT_BT_HOAN_THANH:
                    raise KyThuatMayValidationError("Phiếu đã hoàn thành — không gỡ ảnh chứng thực được.")
        self.repo.delete_anh(anh)
        self._ghi(self._nhat_ky_loai(anh.loai_phieu), anh.phieu_id, "update",
                  f"gỡ ảnh {'hiện trạng' if anh.giai_doan == GIAI_DOAN_TRUOC else 'chứng thực'}: {anh.file_name}",
                  actor_id)
        return anh
