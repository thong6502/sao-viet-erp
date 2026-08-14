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
  · không có cả hai ⇒ coi như tới hạn hôm nay, để gói khai thiếu vẫn ra được phiếu thay vì im lặng
    biến mất khỏi màn hình.
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
# 🔴 Bản đầu có nhánh thứ ba "chưa có mốc ⇒ coi như tới hạn HÔM NAY", định làm đường lui cho gói
# khai thiếu. Thực tế (12/08/2026): bấm "Sinh phiếu từ lịch" một lần đẻ ra 41 phiếu cùng hạn hôm
# nay, không ai đặt hàng cái nào. Đường lui đó ĐÃ BỎ — thiếu mốc thì KHÔNG đoán, chỉ nói ra cho
# người khai đi điền "Bắt đầu từ". Đừng khôi phục.


class KyThuatMayError(Exception):
    pass


class KyThuatMayNotFound(KyThuatMayError):
    pass


class KyThuatMayValidationError(KyThuatMayError):
    pass


class KyThuatMayThieuAnh(KyThuatMayError):
    """Đóng phiếu khi chưa có ảnh chứng thực — 409, không phải 422: dữ liệu gửi lên hợp lệ, chỉ là
    TRẠNG THÁI chưa cho đóng."""


def _f(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _hom_nay() -> date:
    return datetime.now(timezone.utc).date()


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


def cong_chu_ky(moc: date, so: float, don_vi: str | None) -> date:
    """`moc` + `so` × đơn vị. Chu kỳ lẻ (2,5 tháng) làm tròn — không ai khai bảo trì kiểu đó, mà
    giữ số lẻ thì hạn rơi vào ngày không giải thích được."""
    n = max(1, int(round(_f(so, 1))))
    if don_vi == "tuan":
        return moc + timedelta(weeks=n)
    if don_vi == "thang":
        return _cong_thang(moc, n)
    if don_vi == "nam":
        return _cong_thang(moc, n * 12)
    return moc + timedelta(days=n)  # "ngay" + mọi giá trị lạ


def goi_bao_tri_cua(may: MayThietBi) -> list[dict]:
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

    def dem_sua_chua(self) -> dict[str, int]:
        return self.repo.dem_theo_trang_thai_sua_chua()

    def _validate_sua_chua(self, data: dict) -> None:
        if not data.get("may_id"):
            raise KyThuatMayValidationError("Chưa chọn máy.")
        if not (data.get("bo_phan_hong") or "").strip():
            raise KyThuatMayValidationError("Chưa ghi bộ phận hỏng.")
        muc_do = data.get("muc_do")
        if muc_do and muc_do not in MUC_DO:
            raise KyThuatMayValidationError(f"Mức độ không hợp lệ: {muc_do}")

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

    # 🔴 KHÔNG có `xoa_sua_chua` (chủ chốt 12/08/2026). Bản trước chỉ chặn phiếu ĐÃ ĐÓNG, nhưng
    # phiếu chưa đóng cũng là vết thật: máy đã hỏng, có người đã báo, có thể đã chụp ảnh hiện trạng.
    # Ghi nhầm thì SỬA nội dung — không có nút nào dọn sạch lịch sử hỏng hóc của một cái máy.

    # ================= Phiếu bảo trì =================

    def get_bao_tri(self, phieu_id: int) -> BaoTriMay:
        phieu = self.repo.get_bao_tri(phieu_id)
        if phieu is None:
            raise KyThuatMayNotFound("Không tìm thấy phiếu bảo trì.")
        return phieu

    def list_bao_tri(self, **kw):
        return self.repo.list_bao_tri(**kw)

    def dem_bao_tri(self) -> dict[str, int]:
        return self.repo.dem_theo_trang_thai_bao_tri()

    def tao_bao_tri(self, data: dict, *, actor_id: int | None = None) -> BaoTriMay:
        """Tạo phiếu. Hai lối vào, cùng một hàm:

        · **đột xuất** — người dùng bấm "Tạo phiếu", không có `goi_id`;
        · **định kỳ** — bấm một ô KỲ DỰ KIẾN trên lịch, có `goi_id` ⇒ chép luôn chu kỳ + việc con
          của gói. (Nút "Sinh phiếu từ lịch" quét-cả-loạt đã gỡ 12/08/2026.)
        """
        if not data.get("may_id"):
            raise KyThuatMayValidationError("Chưa chọn máy.")
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
        data = dict(data)
        # Đổi ngày ở đây là SỬA nội dung, không phải "dời lịch" (dời lịch bắt buộc có lý do và đi
        # qua `doi_lich`). Chặn để hai đường không đá nhau.
        data.pop("ngay_ke_hoach", None)
        phieu = self.repo.update_bao_tri(phieu, data)
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update", f"{phieu.ma} · sửa nội dung", actor_id)
        return phieu

    def tick_hang_muc(self, phieu_id: int, hang_muc_id: str, xong: bool, *,
                      actor_id: int | None = None) -> BaoTriMay:
        phieu = self.get_bao_tri(phieu_id)
        if phieu.trang_thai == TT_BT_HOAN_THANH:
            raise KyThuatMayValidationError("Phiếu đã hoàn thành — không đổi checklist nữa.")
        rows = phieu.hang_muc if isinstance(phieu.hang_muc, list) else []
        # ⚠️ Phải gán LIST MỚI: sửa tại chỗ phần tử của cột JSON thì SQLAlchemy không thấy gì thay
        # đổi và lặng lẽ không UPDATE (tick xong, F5 lại mất sạch).
        moi = [
            {**h, "xong": bool(xong)} if isinstance(h, dict) and h.get("id") == hang_muc_id else h
            for h in rows
        ]
        if moi == rows:
            raise KyThuatMayValidationError("Không tìm thấy hạng mục trong phiếu.")
        phieu.hang_muc = moi
        self.db.commit()
        self.db.refresh(phieu)
        ten_viec = next(
            (h.get("ten") for h in moi if isinstance(h, dict) and h.get("id") == hang_muc_id), ""
        )
        # Ghi vết TỪNG việc con: đây là thứ trả lời "hôm đó thợ đã làm những gì" khi máy hỏng lại
        # ngay sau kỳ bảo trì. Không ghi thì checklist chỉ còn là mấy ô tick không ai truy được.
        self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "update",
                  f"{phieu.ma} · {'✓' if xong else '✗'} {ten_viec}", actor_id)
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

    # 🔴 KHÔNG có `xoa_bao_tri` — cùng lý do với phiếu sửa chữa. Riêng phiếu bảo trì còn thêm một
    # điều: phiếu đã hoàn thành là MỐC tính kỳ kế tiếp, xoá là chuỗi kỳ phía sau lặng lẽ đổi.

    # ================= Lịch bảo trì của MÁY → hạn & sinh phiếu =================

    def han_ke_tiep(self, may_id: int, goi: dict) -> tuple[date | None, str]:
        """(hạn, nguồn). `hạn = None` ⇒ KHÔNG tính được, và lý do nằm ở `nguồn`:

          · `thieu_chu_ky`      — gói khai tên nhưng bỏ trống "Mỗi … tháng";
          · `thieu_ngay_bat_dau` — có chu kỳ nhưng chưa từng làm lần nào VÀ chưa khai "Bắt đầu từ",
            nên không có gốc để cộng chu kỳ. KHÔNG đoán là hôm nay (xem ghi chú ở đầu file).
        """
        so = _f(goi.get("so"))
        if so <= 0:
            return None, BO_QUA_THIEU_CHU_KY
        goi_id = (goi.get("id") or "").strip()
        moc = self.repo.ngay_hoan_thanh_gan_nhat(may_id, goi_id) if goi_id else None
        if moc is not None:
            return cong_chu_ky(moc, so, goi.get("don_vi")), NGUON_PHIEU
        bat_dau = _parse_date(goi.get("ngay_bat_dau"))
        if bat_dau is not None:
            return bat_dau, NGUON_NGAY_BAT_DAU
        return None, BO_QUA_THIEU_NGAY_BAT_DAU

    def han_cua_may(self, may_id: int) -> list[dict]:
        """Hạn kế tiếp từng gói của MỘT máy — tab "Lịch bảo trì" ở màn Thiết bị đọc cái này."""
        may = self._may(may_id)
        out: list[dict] = []
        for goi in goi_bao_tri_cua(may):
            han, nguon = self.han_ke_tiep(may_id, goi)
            goi_id = (goi.get("id") or "").strip() or None
            out.append({
                "goi_id": goi_id,
                "goi_ten": (goi.get("viec") or "").strip() or None,
                "han": han,
                "nguon": nguon,
                "phieu_dang_mo_id": (
                    p.id if goi_id and (p := self.repo.phieu_dang_mo_cua_goi(may_id, goi_id)) else None
                ),
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

        du_kien: list[dict] = []
        for may in self.db.execute(select(MayThietBi).order_by(MayThietBi.ma.asc())).scalars():
            for goi in goi_bao_tri_cua(may):
                so = _f(goi.get("so"))
                if so <= 0:
                    continue                      # chưa khai chu kỳ ⇒ không đoán được kỳ nào
                goi_id = (goi.get("id") or "").strip()
                don_vi = goi.get("don_vi")
                han, _ = self.han_ke_tiep(may.id, goi)
                if han is None:
                    continue
                mo = self.repo.phieu_dang_mo_cua_goi(may.id, goi_id) if goi_id else None
                moc = cong_chu_ky(mo.ngay_ke_hoach, so, don_vi) if mo is not None else han
                # Cap 60 mốc/gói: chu kỳ 1 ngày mà xem cả năm là 365 chấm trên một lịch tháng —
                # vẽ ra cũng không ai đọc được, mà vòng lặp thì tốn thật.
                for _ in range(60):
                    if moc > den:
                        break
                    if moc >= tu:
                        du_kien.append({
                            "may_id": may.id, "may_ma": may.ma, "may_ten": may.ten,
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
        ra: list[BaoTriMay] = []
        for may in self.db.execute(select(MayThietBi).order_by(MayThietBi.ma.asc())).scalars():
            for goi in goi_bao_tri_cua(may):
                goi_id = (goi.get("id") or "").strip()
                han, _ = self.han_ke_tiep(may.id, goi)
                if han is None or han > hom_nay:
                    continue
                if goi_id and self.repo.phieu_dang_mo_cua_goi(may.id, goi_id) is not None:
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
                }, ma=self.repo.next_ma_bao_tri())
                ra.append(phieu)
                self._ghi(NHAT_KY_LOAI_BAO_TRI, phieu.id, "create",
                          f"{phieu.ma} · tự sinh khi tới hạn · {may.ma} · "
                          f"{(goi.get('viec') or '').strip() or 'gói chưa đặt tên'}", actor_id)
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
