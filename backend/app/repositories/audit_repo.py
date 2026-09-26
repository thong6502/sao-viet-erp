"""Audit-log data access. The only layer that touches the DB for audit rows."""
from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from ..audit_context import hien_tai
from ..models.audit import AuditLog
from ..models.user import User


@dataclass
class BoLoc:
    """Bộ lọc của màn Nhật ký hoạt động — gom vào một chỗ vì ba câu hỏi dùng chung nó:
    lấy trang, đếm tổng, đếm số dòng bị che vì thiếu quyền."""

    q: str | None = None
    tu: datetime | None = None
    den: datetime | None = None
    actions: list[str] = field(default_factory=list)
    actor_ids: list[int] = field(default_factory=list)
    #: tiền tố của `target` ("employee", "giay"…) — lọc theo LOẠI đối tượng. Cần vì 12 màn danh mục
    #: dùng chung đúng ba mã `dm_tao`/`dm_sua`/`dm_xoa`, lọc theo hành động không tách được chúng.
    loais: list[str] = field(default_factory=list)


class AuditLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target: str = "",
        detail: str = "",
        commit: bool = True,
    ) -> AuditLog:
        """`commit=False` cho người gọi đang gom NHIỀU thao tác vào MỘT giao dịch (vd báo sự cố:
        ghi yêu cầu sửa chữa + tạm dừng công việc + đóng phiên máy phải cùng sống hoặc cùng chết).
        Audit tự chốt ở giữa là phá đúng tính nguyên tử đó — và để lại một dòng nhật ký nói về
        việc chưa hề xảy ra khi khúc sau gãy. Vẫn `flush()` để bản ghi có khoá chính dùng ngay."""
        ip, ua = hien_tai()
        entry = AuditLog(
            actor_user_id=actor_user_id, action=action, target=target, detail=detail,
            # Ba cột vết điền TẠI ĐÂY, một chỗ duy nhất, nên hơn 200 đường ghi audit đều có mà
            # không phải sửa chữ ký hàm nào. Rỗng = việc của máy (seeder / tác vụ nền).
            actor_name_luc_do=self._ten_luc_do(actor_user_id), ip=ip, user_agent=ua,
        )
        self.db.add(entry)
        if commit:
            self.db.commit()
            self.db.refresh(entry)
            _bao_co_dong_moi()
        else:
            self.db.flush()
        return entry

    def _ten_luc_do(self, actor_user_id: int | None) -> str:
        """Tên người thao tác, chụp tại lúc ghi. Truy vấn thẳng cột `name` chứ không nạp cả
        `User` — đây là đường nóng, mọi thao tác trong hệ đều đi qua."""
        if actor_user_id is None:
            return ""
        ten = self.db.execute(
            select(User.name).where(User.id == actor_user_id)
        ).scalar_one_or_none()
        return (ten or "")[:120]

    def create_collapsing(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target: str,
        detail: str = "",
    ) -> AuditLog:
        """Như `create` nhưng GỘP thao tác lặp liên tiếp: nếu bản ghi MỚI NHẤT của cùng `target`
        trùng cả `action` lẫn actor → CẬP NHẬT thời điểm + chi tiết của nó thay vì thêm dòng mới.
        Dùng cho các thao tác dễ lặp (vd lưu nháp báo giá nhiều lần) để nhật ký không phình vô tận;
        một action KHÁC xen vào giữa sẽ tách thành mục mới. Không dùng cho audit tuân thủ (cần đủ dòng)."""
        latest = self.db.execute(
            select(AuditLog)
            .where(AuditLog.target == target)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.action == action and latest.actor_user_id == actor_user_id:
            latest.created_at = datetime.now(timezone.utc)
            latest.detail = detail
            self.db.commit()
            self.db.refresh(latest)
            return latest
        return self.create(
            actor_user_id=actor_user_id, action=action, target=target, detail=detail
        )

    def max_created_at(self, actions) -> datetime | None:
        """Thời điểm MỚI NHẤT của một nhóm hành động — chốt lương L15 hỏi "hồ sơ lương / tham số có đổi
        SAU lần Tính lại không" cho các bảng không có `updated_at` (08/09/2026)."""
        acts = [a for a in (actions or []) if a]
        if not acts:
            return None
        return self.db.execute(
            select(func.max(AuditLog.created_at)).where(AuditLog.action.in_(acts))
        ).scalar()

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return list(
            self.db.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
            ).scalars()
        )

    # --- Màn Nhật ký hoạt động: lọc + phân trang Ở MÁY CHỦ ----------------------------------
    # Trước 25/09/2026 màn này gọi `list_recent(100)` rồi lọc/cắt trang/xuất CSV bằng JavaScript
    # trên đúng 100 dòng ấy: dòng thứ 101 trở đi KHÔNG có đường nào lấy ra, và "30 ngày qua" chỉ
    # lọc trong ảnh chụp đó. Ba hàm dưới đây là đường thay thế.

    @staticmethod
    def _dieu_kien(loc: BoLoc, chan_action: list[str], chan_dm: list[str]) -> list:
        dk = []
        if loc.tu is not None:
            dk.append(AuditLog.created_at >= loc.tu)
        if loc.den is not None:
            dk.append(AuditLog.created_at <= loc.den)
        if loc.actions:
            dk.append(AuditLog.action.in_(loc.actions))
        if loc.actor_ids:
            dk.append(AuditLog.actor_user_id.in_(loc.actor_ids))
        if loc.loais:
            dk.append(or_(*[AuditLog.target.like(f"{l}:%") for l in loc.loais]))
        if loc.q:
            mau = f"%{loc.q.strip()}%"
            dk.append(or_(AuditLog.detail.ilike(mau), AuditLog.target.ilike(mau)))
        cam = AuditLogRepository._dieu_kien_cam(chan_action, chan_dm)
        if cam is not None:
            dk.append(not_(cam))
        return dk

    @staticmethod
    def _dieu_kien_cam(chan_action: list[str], chan_dm: list[str]):
        """Điều kiện khớp những dòng người xem KHÔNG được đọc (thiếu quyền trên màn sinh ra dòng).

        Hai vế vì ba mã danh mục dùng chung (`dm_tao`/`dm_sua`/`dm_xoa`) không tự nói nó thuộc màn
        nào — màn nằm ở tiền tố của `target`."""
        ve = []
        if chan_action:
            ve.append(AuditLog.action.in_(chan_action))
        if chan_dm:
            ve.append(
                and_(
                    AuditLog.action.in_(("dm_tao", "dm_sua", "dm_xoa")),
                    or_(*[AuditLog.target.like(f"{l}:%") for l in chan_dm]),
                )
            )
        if not ve:
            return None
        return or_(*ve)

    def tim(
        self,
        loc: BoLoc,
        *,
        chan_action: list[str] | None = None,
        chan_dm: list[str] | None = None,
        limit: int = 50,
        trang: int = 1,
        neo: str | None = None,
    ) -> tuple[list[AuditLog], str | None]:
        """Một trang, mới nhất trước. Trả `(dòng, neo)` — `neo` là mốc của dòng ĐẦU trang 1.

        Màn cần nhảy thẳng tới trang bất kỳ (1 · 2 · 3 … n) nên phải OFFSET, mà OFFSET trần trên
        bảng này thì trượt: dòng mới rơi vào ĐẦU danh sách (sắp xếp mới-nhất-trước), đẩy mọi thứ
        xuống một nấc, trang 2 lặp lại dòng cuối trang 1. Cách chữa là **neo**: trang 1 chụp mốc
        `(created_at, id)` của dòng trên cùng, các trang sau gửi lại mốc đó và chỉ lấy dòng KHÔNG
        MỚI HƠN nó. Cả xấp trang vì thế là một ảnh chụp đứng yên; dòng mới đến trong lúc đọc không
        chen vào giữa mà báo bằng băng "Có bản ghi mới" để người dùng tự quyết lúc nạp lại.

        Mốc gói bằng base64-url vì `isoformat()` trên Postgres có dấu `+` của offset, mà `+` trong
        query string giải mã thành DẤU CÁCH: để trần thì chạy đúng trên SQLite của test rồi vỡ im
        lặng trên Postgres. Giá trị lấy THẲNG từ DB nên tự khớp kiểu ngày giờ của từng dialect
        (Postgres aware / SQLite naive), không tự dựng lại rồi lệch múi giờ."""
        dk = self._dieu_kien(loc, chan_action or [], chan_dm or []) + _dk_neo(neo)
        rows = list(
            self.db.execute(
                select(AuditLog).where(*dk)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset(max(0, (max(1, trang) - 1) * limit))
                .limit(limit)
            ).scalars()
        )
        # Neo chỉ sinh ở TRANG 1 — các trang sau gửi lại đúng mốc đó, không tự chụp mốc mới.
        if neo is None and trang <= 1 and rows:
            neo = _goi_cursor(rows[0].created_at, rows[0].id)
        return rows, neo

    def dem(self, loc: BoLoc, *, chan_action: list[str] | None = None,
            chan_dm: list[str] | None = None, neo: str | None = None) -> int:
        dk = self._dieu_kien(loc, chan_action or [], chan_dm or []) + _dk_neo(neo)
        return self.db.execute(
            select(func.count()).select_from(AuditLog).where(*dk)
        ).scalar_one()

    def dem_bi_chan(self, loc: BoLoc, *, chan_action: list[str], chan_dm: list[str],
                    neo: str | None = None) -> int:
        """Bao nhiêu dòng khớp bộ lọc nhưng bị che vì thiếu quyền. Màn hiện con số này ra —
        nhật ký mà nuốt dòng im lặng thì người đọc không biết mình đang thiếu gì."""
        cam = self._dieu_kien_cam(chan_action, chan_dm)
        if cam is None:
            return 0
        dk = self._dieu_kien(loc, [], []) + _dk_neo(neo) + [cam]
        return self.db.execute(
            select(func.count()).select_from(AuditLog).where(*dk)
        ).scalar_one()

    def facet_action(self, loc: BoLoc, *, chan_action: list[str] | None = None,
                     chan_dm: list[str] | None = None) -> list[tuple[str, int]]:
        """(`action`, số dòng) trong PHẠM VI BỘ LỌC — để dropdown hành động và chip nhóm đếm theo
        toàn bộ dữ liệu khớp, không phải theo trang đang xem."""
        dk = self._dieu_kien(loc, chan_action or [], chan_dm or [])
        rows = self.db.execute(
            select(AuditLog.action, func.count()).where(*dk).group_by(AuditLog.action)
        ).all()
        return [(a, n) for a, n in rows]

    def facet_actor(self, loc: BoLoc, *, chan_action: list[str] | None = None,
                    chan_dm: list[str] | None = None) -> list[tuple[int | None, int]]:
        dk = self._dieu_kien(loc, chan_action or [], chan_dm or [])
        rows = self.db.execute(
            select(AuditLog.actor_user_id, func.count()).where(*dk)
            .group_by(AuditLog.actor_user_id)
        ).all()
        return [(a, n) for a, n in rows]

    def list_by_action(self, action: str, limit: int = 200) -> list[AuditLog]:
        """Audit rows của MỘT loại thao tác (vd ``kho_export``), mới nhất trước — cho màn lịch sử."""
        return list(
            self.db.execute(
                select(AuditLog)
                .where(AuditLog.action == action)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def list_by_target(self, target: str, limit: int = 200) -> list[AuditLog]:
        """Audit rows for one entity (e.g. ``customer:42``), newest first — feeds the
        per-record "Nhật ký" timeline."""
        return list(
            self.db.execute(
                select(AuditLog)
                .where(AuditLog.target == target)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def list_for_target(self, target: str, limit: int = 50) -> list[AuditLog]:
        """Recent audit rows whose action targeted a given entity (spec-08 per-user activity)."""
        return self.list_by_target(target, limit=limit)

    def count(self) -> int:
        return self.db.execute(select(func.count()).select_from(AuditLog)).scalar_one()


def _goi_cursor(at: datetime, id_: int) -> str:
    return urlsafe_b64encode(f"{at.isoformat()}|{id_}".encode()).decode().rstrip("=")


def _dk_neo(neo: str | None) -> list:
    """Điều kiện "không mới hơn mốc neo". Dùng CHUNG cho `tim` và hai hàm đếm — nếu đếm mà bỏ neo
    thì tổng bao gồm cả dòng vừa ghi xong, số trang nhảy trong lúc người ta đang đọc."""
    moc = _doc_cursor(neo)
    if moc is None:
        return []
    at, id_ = moc
    return [
        or_(AuditLog.created_at < at,
            and_(AuditLog.created_at == at, AuditLog.id <= id_))
    ]


def _doc_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    """Cursor → mốc keyset. Cursor rác thì coi như không có (trả trang đầu) chứ không 500 — nó
    đến từ query string, người dùng sửa tay được."""
    if not cursor:
        return None
    try:
        tho = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        phan_at, _, phan_id = tho.rpartition("|")
        return datetime.fromisoformat(phan_at), int(phan_id)
    except (ValueError, UnicodeDecodeError, BinasciiError):
        return None


# --- Báo cho màn Nhật ký đang mở biết có dòng mới ---------------------------------------------
# Nguyên tắc sản phẩm (CLAUDE.md): việc nội bộ tới người nhận NGAY, không bắt họ F5. Badge "Đồng bộ
# Live" trên màn Nhật ký trước 25/09/2026 là chữ trang trí — màn chỉ nạp một lần lúc mở.
#
# Tín hiệu NHẸ và CÓ TIẾT CHẾ: mọi thao tác trong hệ đều ghi một dòng audit, bắn mỗi dòng một sự
# kiện là tự làm ngập kênh chung. Nhiều dòng trong cùng vài giây chỉ cần MỘT tiếng "có cái mới";
# màn hình tự hỏi lại số chính xác. Cũng KHÔNG đẩy nội dung dòng: người đang mở màn chưa chắc có
# quyền đọc dòng vừa ghi (xem `ActivityService._chan`).
_GIAN_CACH_BAO = 3.0
_lan_bao_cuoi = 0.0


def _bao_co_dong_moi() -> None:
    global _lan_bao_cuoi
    bay_gio = monotonic()
    if bay_gio - _lan_bao_cuoi < _GIAN_CACH_BAO:
        return
    _lan_bao_cuoi = bay_gio
    try:
        from ..realtime import hub

        hub.broadcast({"type": "nhat_ky_moi"})
    except Exception:
        # Kênh đẩy hỏng KHÔNG được làm hỏng việc ghi nhật ký — dòng đã commit rồi.
        pass
