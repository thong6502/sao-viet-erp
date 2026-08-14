"""Ticker in-process nhắc PHIẾU BẢO TRÌ tới hạn (12/08/2026).

Cùng khuôn với `care_reminders.py` (lịch hẹn chăm sóc) và cùng lý do: CLAUDE.md — thông báo nội bộ
phải REAL-TIME, badge tự nhảy + toast tức thì, không bắt ai F5 mới biết máy tới kỳ bảo trì.

Khác một điểm quan trọng với lịch hẹn: hẹn có GIỜ nên "ting" đúng lúc giờ đó trôi qua; phiếu bảo
trì chỉ có NGÀY, nên mỗi lần quét là hỏi "hôm nay có phiếu nào tới hạn / quá hạn mà chưa xong
không". Để không ting lại mỗi vòng lặp, ghi nhớ id đã ting trong RAM và **xoá sổ khi sang ngày
mới** — phiếu còn dở sang hôm sau vẫn được nhắc lại một lần nữa, đúng cái người ta cần.

Nhớ trong RAM (không cột DB) là cố ý: đây là thông báo, không phải dữ liệu nghiệp vụ. Restart giữa
ngày thì mỗi phiếu bị nhắc lại đúng một lần — phiền hơn hẳn việc đẻ thêm một cột chỉ để phục vụ
cái toast.

Ai nhận:
  · phiếu ĐÃ có người nhận ⇒ chỉ người đó (việc của họ);
  · chưa ai nhận ⇒ mọi tài khoản đang hoạt động có quyền SỬA module `ky_thuat_may` — tức tổ sửa
    chữa. Không broadcast toàn công ty: kế toán không cần biết máy bế tới kỳ tra dầu.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from .db import SessionLocal
from .models.ky_thuat_may import TT_BT_DANG_MO, BaoTriMay
from .models.may_thiet_bi import MayThietBi
from .models.role import RolePermission
from .models.user import User
from .realtime import hub
from .repositories.audit_repo import AuditLogRepository
from .repositories.ky_thuat_may_repo import KyThuatMayRepository
from .services.ky_thuat_may_service import KyThuatMayService, hom_nay_vn

log = logging.getLogger(__name__)

MODULE = "ky_thuat_may"

# {ngày: {phieu_id}} — chỉ giữ đúng NGÀY HÔM NAY, sang ngày mới là thay sạch.
_da_ting: dict[date, set[int]] = {}


def _nguoi_nhan_thong_bao(db) -> list[int]:
    """Tài khoản đang hoạt động có quyền SỬA `ky_thuat_may` — tổ sửa chữa."""
    return [int(i) for i in db.execute(
        select(User.id)
        .join(RolePermission, RolePermission.role_id == User.role_id)
        .where(
            RolePermission.module_key == MODULE,
            RolePermission.can_update.is_(True),
            User.is_active.is_(True),
        )
    ).scalars()]


def _scan_once(hom_nay: date) -> int:
    """Đến ngày thì TỰ ĐẺ PHIẾU rồi ting. Trả số phiếu vừa ting.

    Hai việc phải đi liền và đúng thứ tự này: sinh trước, nhắc sau. Chỉ nhắc thôi thì gói tới hạn
    mà chưa ai bấm tạo phiếu sẽ nằm im mãi trên lịch dưới dạng chấm mờ — không có phiếu thì không
    có gì để nhắc, và người ta chỉ phát hiện khi máy đã hỏng (chủ soi ra 14/08/2026).
    """
    db = SessionLocal()
    try:
        da = _da_ting.setdefault(hom_nay, set())
        for cu in [d for d in _da_ting if d != hom_nay]:
            _da_ting.pop(cu, None)          # sang ngày mới: quên sổ cũ, nhắc lại phiếu còn dở

        # PHẢI truyền `AuditLogRepository`, không thì `_ghi` im lặng bỏ qua và phiếu tự sinh không
        # có một dòng lịch sử nào — mở tab "Lịch sử thao tác" ra trống trơn, không ai biết nó ở đâu
        # ra. actor_id=None ⇒ nhật ký ghi "Hệ thống", đúng sự thật: không người nào bấm cái này.
        svc = KyThuatMayService(db, KyThuatMayRepository(db), AuditLogRepository(db))
        moi_sinh = svc.sinh_phieu_den_han(hom_nay=hom_nay)
        if moi_sinh:
            db.commit()
        if moi_sinh:
            log.info("bao tri: tu sinh %d phieu den han", len(moi_sinh))

        rows = list(db.execute(
            select(BaoTriMay).where(
                BaoTriMay.ngay_ke_hoach <= hom_nay,
                BaoTriMay.trang_thai.in_(TT_BT_DANG_MO),
            )
        ).scalars())
        moi = [p for p in rows if p.id not in da]
        if not moi:
            return 0

        may_ten = dict(db.execute(
            select(MayThietBi.id, MayThietBi.ma).where(
                MayThietBi.id.in_({p.may_id for p in moi})
            )
        ).all())
        chung = None                        # danh sách người nhận chung, chỉ query khi cần

        for p in moi:
            su_kien = {
                "type": "bao_tri_due",
                "phieu_id": p.id,
                "ma": p.ma,
                "may": may_ten.get(p.may_id) or "",
                "goi": p.goi_ten or "Bảo trì",
                "qua_han": p.ngay_ke_hoach < hom_nay,
            }
            if p.nguoi_thuc_hien_id:
                hub.publish(p.nguoi_thuc_hien_id, su_kien)
            else:
                if chung is None:
                    chung = _nguoi_nhan_thong_bao(db)
                for uid in chung:
                    hub.publish(uid, su_kien)
            da.add(p.id)
        return len(moi)
    finally:
        db.close()


async def run_bao_tri_reminder_loop(interval: int) -> None:
    """Vòng lặp nền. Nuốt mọi lỗi để một lần fail (vd DB chớp) không giết vòng lặp.

    Quét NGAY một lượt rồi mới ngủ: máy tắt qua đêm, sáng bật lên là kỳ của hôm nay có phiếu ngay,
    không bắt người ta đợi hết một chu kỳ ticker mới thấy việc của mình.
    """
    while True:
        try:
            # Ngày theo giờ NHÀ MÁY. Lấy UTC là 0h–7h sáng giờ VN ticker vẫn quét theo ngày HÔM QUA:
            # kỳ của hôm nay không ra phiếu, ca sáng vào làm không thấy việc của mình.
            n = await asyncio.to_thread(_scan_once, hom_nay_vn())
            if n:
                log.info("bao tri reminder: ting %d phiếu tới hạn", n)
        except Exception:  # noqa: BLE001 — vòng lặp nền phải sống sót mọi lỗi
            log.exception("bao tri reminder loop scan failed")
        await asyncio.sleep(interval)
