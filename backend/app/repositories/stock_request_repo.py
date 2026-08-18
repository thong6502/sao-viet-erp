"""Repository — Yêu cầu kho (spec-kho-de-nghi §3–§5).

Chỉ truy vấn/ghi DB. Luật nghiệp vụ (ai được duyệt, chặn ứng vượt duyệt, chuyển trạng
thái) nằm ở `services/stock_request_service.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from ..models.stock_request import (
    REQ_CANCELLED,
    REQ_DONE,
    REQ_NHAP,
    REQ_REJECTED,
    REQ_XUAT,
    StockRequest,
    StockRequestLine,
)

# Mốc gốc so "chưa xem" khi người tạo chưa từng mở yêu cầu (quyet_dinh_xem_luc NULL).
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_HEADER_FIELDS = ("bo_phan_id", "kho_id", "ngay_can", "uu_tien", "ghi_chu", "loai_kho",
                  "purchase_delivery_id",
                  # ĐIỀU CHUYỂN KHO (mig 0203) — set từ service khi ấn điều chuyển.
                  "dieu_chuyen", "kho_nguon_id", "xuat_voucher_id")


def _build_line(ln: dict, loai: str) -> StockRequestLine:
    """Dựng 1 dòng đề nghị từ dict payload. Đơn giá chỉ áp cho đề nghị NHẬP (người đề nghị biết
    giá NCC); XUẤT → null (giá vốn lấy đích danh từ lô).

    Không còn `ten_tu_do`/`don_vi_phu`/`he_so_quy_doi` (mg 0171): mặt hàng bắt buộc chọn từ danh
    mục gốc, còn quy đổi lấy từ đồ thị đơn vị dùng chung.
    """
    return StockRequestLine(
        hang_loai=ln["hang_loai"],
        hang_id=ln["hang_id"],
        lsx_id=ln.get("lsx_id"),
        bai_ghep_id=ln.get("bai_ghep_id"),
        dvt=ln["dvt"],
        sl_de_nghi=ln["sl_de_nghi"],
        don_gia=ln.get("don_gia") if loai == "NHAP" else None,
        ghi_chu=ln.get("ghi_chu"),
    )


class StockRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, request_id: int) -> StockRequest | None:
        return self.db.get(StockRequest, request_id)

    def lenh_ton_tai(self, lsx_id: int | None, bai_ghep_id: int | None) -> tuple[bool, bool]:
        """`(lệnh có thật, bài ghép có thật)` cho ô "cho lệnh nào" (mg 0175).

        Truy vấn nằm ở ĐÂY chứ không ở service: service từng mượn `self.requests.db` để tự
        `db.get(...)` — thò tay qua repo lấy session là phá đúng ranh giới mà lớp repo dựng ra.
        Id để trống ⇒ `True` (không gắn lệnh là hợp lệ: xin lặt vặt).
        """
        from ..models.bai_ghep import BaiGhep
        from ..models.lsx import Lsx

        co_lsx = lsx_id in (None, "") or self.db.get(Lsx, int(lsx_id)) is not None
        co_bg = bai_ghep_id in (None, "") or self.db.get(BaiGhep, int(bai_ghep_id)) is not None
        return co_lsx, co_bg

    def get_by_ma(self, ma: str) -> StockRequest | None:
        return self.db.execute(
            select(StockRequest).where(func.upper(StockRequest.ma) == ma.strip().upper())
        ).scalars().first()

    def get_with_lines(self, request_id: int) -> StockRequest | None:
        return self.db.execute(
            select(StockRequest)
            .options(selectinload(StockRequest.lines))
            .where(StockRequest.id == request_id)
        ).scalars().first()

    def get_line(self, line_id: int) -> StockRequestLine | None:
        return self.db.get(StockRequestLine, line_id)

    def count_by_loai(self, trang_thai: list[str], *, nguoi_tao_id: int | None = None,
                      bo_phan_id: int | None = None) -> dict[str, int]:
        """Đếm yêu cầu chờ xử lý theo CHIỀU cho badge: `nhap` · `xuat` · `dieu_chuyen`.
        `nhap`/`xuat` KHÔNG tính điều chuyển (đã tách sang bucket riêng); vế XUẤT nguồn nội bộ luôn
        bị ẩn. LỌC THEO SCOPE (nguoi_tao_id/bo_phan_id) GIỐNG `list` để badge khớp đúng list."""
        conds = [StockRequest.trang_thai.in_(trang_thai)]
        # ẨN vế XUẤT nguồn của điều chuyển (bút toán nội bộ, tự ghi sổ khi đích nhập) khỏi badge.
        conds.append(or_(StockRequest.dieu_chuyen.is_(False), StockRequest.loai != REQ_XUAT))
        if nguoi_tao_id is not None:
            conds.append(StockRequest.nguoi_tao_id == nguoi_tao_id)
        if bo_phan_id is not None:
            conds.append(StockRequest.bo_phan_id == bo_phan_id)
        rows = self.db.execute(
            select(StockRequest.loai, StockRequest.dieu_chuyen, func.count())
            .where(*conds)
            .group_by(StockRequest.loai, StockRequest.dieu_chuyen)
        ).all()
        out = {"nhap": 0, "xuat": 0, "dieu_chuyen": 0}
        for loai, dc, n in rows:
            if dc:
                out["dieu_chuyen"] += int(n)   # điều chuyển (yêu cầu NHẬP đích) — bucket riêng
            elif loai == REQ_NHAP:
                out["nhap"] += int(n)
            else:
                out["xuat"] += int(n)
        return out

    # --- Badge "kho đã PHẢN HỒI yêu cầu của tôi" (hoàn tất / không thành) — seen theo TỪNG yêu cầu ---
    # "Phản hồi" = trạng thái CUỐI, KHÔNG tính yêu cầu vừa tạo (luồng bỏ duyệt → tạo là 'approved'
    # ngay, đó là hành động của chính người tạo nên không báo). Mốc so = `updated_at` (lúc kho chốt
    # kết quả) > lần người tạo MỞ XEM yêu cầu đó (`quyet_dinh_xem_luc`).
    _TERM_DONE = (REQ_DONE,)
    _TERM_FAIL = (REQ_REJECTED, REQ_CANCELLED)

    def unseen_response_counts(self, nguoi_tao_id: int) -> dict[str, int]:
        """Số phản hồi kho CHƯA XEM của `nguoi_tao_id`, tách theo bộ lọc: done=Hoàn tất, fail=Không thành."""
        fresh = StockRequest.updated_at > func.coalesce(StockRequest.quyet_dinh_xem_luc, _EPOCH)

        def cnt(statuses: tuple[str, ...]) -> int:
            stmt = select(func.count()).select_from(StockRequest).where(
                StockRequest.nguoi_tao_id == nguoi_tao_id,
                StockRequest.trang_thai.in_(statuses),
                fresh,
            )
            return int(self.db.execute(stmt).scalar() or 0)

        return {"done": cnt(self._TERM_DONE), "fail": cnt(self._TERM_FAIL)}

    def mark_seen_one(self, request_id: int, nguoi_tao_id: int) -> None:
        """Người tạo MỞ XEM 1 yêu cầu CỦA MÌNH → đánh dấu đã xem (chỉ yêu cầu do chính họ tạo).

        GIỮ NGUYÊN `updated_at` (set = chính nó) để `onupdate=_utcnow` KHÔNG kích — nếu để nó nhảy
        thì `updated_at` (mốc phản hồi để so) bị đẩy lên ~now, badge sẽ không bao giờ tắt."""
        self.db.execute(
            update(StockRequest)
            .where(
                StockRequest.id == request_id,
                StockRequest.nguoi_tao_id == nguoi_tao_id,
            )
            .values(
                quyet_dinh_xem_luc=datetime.now(timezone.utc),
                updated_at=StockRequest.updated_at,
            )
        )
        self.db.commit()

    def by_ids_with_lines(self, ids) -> dict[int, StockRequest]:
        """Nạp NHIỀU yêu cầu kèm dòng trong 1 (+lines) query — tránh N+1 khi serialize danh sách phiếu."""
        ids = [i for i in set(ids) if i is not None]
        if not ids:
            return {}
        rows = self.db.execute(
            select(StockRequest)
            .options(selectinload(StockRequest.lines))
            .where(StockRequest.id.in_(ids))
        ).scalars()
        return {r.id: r for r in rows}

    def _base_conds(self, *, loai=None, trang_thai=None, q=None, nguoi_tao_id=None,
                    bo_phan_id=None, kho_id=None, dieu_chuyen=None,
                    ngay_can_tu=None, ngay_can_den=None, tao_tu=None, tao_den=None):
        """Điều kiện lọc CHUNG cho `list` và `count_by_status` — để badge tab khớp đúng list.
        `ngay_can_tu/den` lọc theo NGÀY CẦN (cột Date); `tao_tu/den` lọc theo NGÀY TẠO (created_at)."""
        # ẨN vế XUẤT nguồn của điều chuyển (bút toán nội bộ): nó tự ghi sổ khi kho đích nhập, người
        # dùng không thao tác trực tiếp → không hiện. Yêu cầu NHẬP đích (kho_nguon_id ≠ null) VẪN hiện.
        conds = [or_(StockRequest.dieu_chuyen.is_(False), StockRequest.loai != REQ_XUAT)]
        if dieu_chuyen is not None:
            conds.append(StockRequest.dieu_chuyen.is_(dieu_chuyen))
        if loai:
            conds.append(StockRequest.loai == loai)
        if trang_thai:
            conds.append(StockRequest.trang_thai.in_(trang_thai))
        if nguoi_tao_id is not None:
            conds.append(StockRequest.nguoi_tao_id == nguoi_tao_id)
        if bo_phan_id is not None:
            conds.append(StockRequest.bo_phan_id == bo_phan_id)
        if kho_id is not None:
            conds.append(StockRequest.kho_id == kho_id)
        if ngay_can_tu is not None:
            conds.append(StockRequest.ngay_can >= ngay_can_tu)
        if ngay_can_den is not None:
            conds.append(StockRequest.ngay_can <= ngay_can_den)
        if tao_tu is not None:
            conds.append(func.date(StockRequest.created_at) >= tao_tu)
        if tao_den is not None:
            conds.append(func.date(StockRequest.created_at) <= tao_den)
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(
                func.lower(StockRequest.ma).like(like),
                func.lower(func.coalesce(StockRequest.ghi_chu, "")).like(like),
            ))
        return conds

    def list(self, *, loai: str | None = None, trang_thai: list[str] | None = None,
             q: str | None = None, nguoi_tao_id: int | None = None,
             bo_phan_id: int | None = None, kho_id: int | None = None,
             dieu_chuyen: bool | None = None,
             ngay_can_tu=None, ngay_can_den=None, tao_tu=None, tao_den=None,
             order: str = "id", page: int = 1, size: int = 50):
        """Danh sách yêu cầu (BE-paging). `nguoi_tao_id` / `bo_phan_id` áp SCOPE: người yêu cầu
        (scope `own`) chỉ thấy yêu cầu của chính mình — đó là lý do họ không nhìn thấy kho.
        `dieu_chuyen`: True = CHỈ yêu cầu điều chuyển · False = nhập/xuất thường · None = không lọc.
        `order`: 'id' = mới TẠO trước (mặc định) · 'updated' = vừa ĐỔI (duyệt/cấp/hủy) trước (Hộp yêu cầu)."""
        conds = self._base_conds(
            loai=loai, trang_thai=trang_thai, q=q, nguoi_tao_id=nguoi_tao_id,
            bo_phan_id=bo_phan_id, kho_id=kho_id, dieu_chuyen=dieu_chuyen,
            ngay_can_tu=ngay_can_tu, ngay_can_den=ngay_can_den, tao_tu=tao_tu, tao_den=tao_den,
        )
        base = select(StockRequest).options(selectinload(StockRequest.lines))
        count_stmt = select(func.count()).select_from(StockRequest)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        order_cols = (
            [StockRequest.updated_at.desc(), StockRequest.id.desc()]
            if order == "updated" else [StockRequest.id.desc()]
        )
        base = base.order_by(*order_cols).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def count_by_status(self, *, loai=None, q=None, nguoi_tao_id=None, bo_phan_id=None,
                        kho_id=None, dieu_chuyen=None, base_trang_thai=None,
                        ngay_can_tu=None, ngay_can_den=None, tao_tu=None,
                        tao_den=None) -> dict[str, int]:
        """Đếm yêu cầu theo TỪNG TRẠNG THÁI (cùng bộ lọc như `list`, TRỪ tab) → FE cộng theo tab
        cho badge. `base_trang_thai`: giới hạn tập nền (vd Hộp yêu cầu chỉ tính trạng thái INBOX)."""
        conds = self._base_conds(
            loai=loai, trang_thai=base_trang_thai, q=q, nguoi_tao_id=nguoi_tao_id,
            bo_phan_id=bo_phan_id, kho_id=kho_id, dieu_chuyen=dieu_chuyen,
            ngay_can_tu=ngay_can_tu, ngay_can_den=ngay_can_den, tao_tu=tao_tu, tao_den=tao_den,
        )
        rows = self.db.execute(
            select(StockRequest.trang_thai, func.count()).where(*conds)
            .group_by(StockRequest.trang_thai)
        ).all()
        return {str(s): int(n) for s, n in rows}

    def dong_xuat_theo_lenh(self) -> list[tuple[StockRequestLine, str]]:
        """Dòng đề nghị XUẤT đã gắn lệnh/bài — nguồn "đã cấp" + "đang lĩnh" của bảng cân đối vật tư.

        Trả kèm `trang_thai` của header để phía gọi khỏi lazy-load từng cái (N+1 trên màn cân đối
        là hàng trăm query). CHỈ đề nghị XUẤT: đề nghị NHẬP là hàng ĐI VÀO kho, trừ nó vào nhu cầu
        sản xuất là trừ ngược dấu.

        Bỏ đề nghị đã HỦY / BỊ TỪ CHỐI: chúng không còn sinh ra phiếu nào nên `sl_duyet` của chúng
        không phải hàng "đang lĩnh".
        """
        stmt = (
            select(StockRequestLine, StockRequest.trang_thai)
            .join(StockRequest, StockRequest.id == StockRequestLine.request_id)
            .where(
                StockRequest.loai == REQ_XUAT,
                StockRequest.trang_thai.notin_([REQ_REJECTED, REQ_CANCELLED]),
                or_(
                    StockRequestLine.lsx_id.is_not(None),
                    StockRequestLine.bai_ghep_id.is_not(None),
                ),
            )
        )
        return [(ln, tt) for ln, tt in self.db.execute(stmt)]

    def create(self, *, ma: str, loai: str, nguoi_tao_id: int, lines: list[dict],
               **header) -> StockRequest:
        obj = StockRequest(ma=ma, loai=loai, nguoi_tao_id=nguoi_tao_id)
        for k in _HEADER_FIELDS:
            if k in header:
                setattr(obj, k, header[k])
        for ln in lines:
            obj.lines.append(_build_line(ln, loai))
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def replace_lines(self, obj: StockRequest, lines: list[dict]) -> None:
        """Thay toàn bộ dòng (chỉ dùng khi yêu cầu còn sửa được). Xóa-rồi-thêm thay vì
        khớp từng dòng: yêu cầu còn nháp thì chưa có phiếu nào trỏ vào dòng cũ."""
        obj.lines.clear()
        self.db.flush()
        for ln in lines:
            obj.lines.append(_build_line(ln, obj.loai))

    def update_header(self, obj: StockRequest, data: dict) -> StockRequest:
        for k in _HEADER_FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        return obj

    def save(self, obj: StockRequest) -> StockRequest:
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: StockRequest) -> None:
        self.db.delete(obj)
        self.db.commit()
