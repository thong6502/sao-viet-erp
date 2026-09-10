"""Xếp lịch 3 — điều phối bàn xếp lịch cấp LỆNH SẢN XUẤT.

Mục tiêu DUY NHẤT của màn: người đặt giờ bắt đầu cho một lệnh, hệ trả ngay ngày kết thúc. Không
gán máy (máy đã nằm sẵn trên `lsx_cong_doan.may_id` từ lúc tạo lệnh), không xếp từng công đoạn,
và **không chặn gì hết** — thiếu vật tư hay trễ hạn thì bày MÀU, người điều độ vẫn quyết.

Số dẫn xuất tính lúc đọc qua `trai_lich`. Ranh giới hiệu năng (spec §4.1): khung giờ làm dựng ĐÚNG
MỘT LẦN mỗi request, routing cả lô nạp bằng MỘT truy vấn, mọi đường đọc cắt theo cửa sổ hoặc theo
tập id.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from ...models.lsx import (
    LB_MAY, LB_THUE_NGOAI, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH, TT_SAN_SANG,
)
from ...models.xep_lich_lenh import XepLichLenh
from ..xep_lich_service import _aware, _naive
from .trai_lich import BuocVao, KetQuaTrai, MocBuoc, trai_lich


class XepLich3Error(Exception):
    """Lỗi nghiệp vụ chung → 400."""


class XepLich3NotFound(XepLich3Error):
    """→ 404."""


class XepLich3Conflict(XepLich3Error):
    """Người khác vừa đổi mốc → 409."""


# Lệnh được phép nằm trên bàn xếp lịch. `da_phat_hanh` vẫn giữ mốc để bàn tổ đọc, nhưng không
# quay lại hàng chờ.
TT_XEP_DUOC = (TT_SAN_SANG, TT_DA_LAP_KE_HOACH)


def _chu(v: object) -> str | None:
    """Ép một ô quy cách về CHUỖI cho `ChiTietOut`.

    `quy_cach_json` là ảnh chụp lúc tạo lệnh, giá trị có thể là SỐ (`so_kem: 4`, `so_mau: 4`) chứ
    không phải chuỗi. Schema khai `str | None`, trả thẳng số là `ResponseValidationError` — mà lỗi
    đó ném NGOÀI `CORSMiddleware` nên trình duyệt chỉ thấy "blocked by CORS policy", không thấy 500.
    """
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _ngay_thue_ngoai(cd) -> int | None:
    """Số NGÀY LỊCH một bước gia công ngoài chiếm chỗ. `None` = chưa khai đủ để biết.

    Hai nguồn, ưu tiên nguồn KHAI TAY vì nó là cam kết của nhà cung cấp:
      1. `van_chuyen_ngay` (MỘT chiều, nên nhân 2) + `gia_cong_ngay`;
      2. `ngay_nhan_dk - ngay_gui_dk` nếu khai cả hai mốc.

    Cờ nhận biết bước thuê ngoài là `loai_buoc == LB_THUE_NGOAI` — KHÔNG có cột boolean nào.
    """
    vc, gc = getattr(cd, "van_chuyen_ngay", None), getattr(cd, "gia_cong_ngay", None)
    if vc is not None or gc is not None:
        return int(round(float(vc or 0) * 2 + float(gc or 0)))
    gui, nhan = getattr(cd, "ngay_gui_dk", None), getattr(cd, "ngay_nhan_dk", None)
    if gui and nhan:
        return max(0, (nhan - gui).days)
    return None


class _LsxCoRouting:
    """Proxy đọc-thuộc-tính cho `quy_cach_bien`: ép nó dùng routing ĐÃ NẠP SẴN.

    `quy_cach_bien` duyệt `lsx.cong_doans` để tìm bước in; quan hệ đó lazy-load, nên gọi thẳng
    trong vòng lặp là N+1 đúng nghĩa — một truy vấn routing cho MỖI lệnh, ngay bên cạnh truy vấn
    theo lô vừa nạp đủ. Test `test_lich_khong_N_cong_1_truy_van_routing` chốt đúng chỗ này.
    """

    def __init__(self, lsx, cds) -> None:
        self._lsx = lsx
        self.cong_doans = cds

    def __getattr__(self, k):
        return getattr(self._lsx, k)


class XepLich3Service:
    def __init__(self, db: Session, repo, audit=None) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self._lich = None       # khung giờ làm — dựng LƯỜI, đúng một lần mỗi request
        self._svc_dur = None    # LsxService rút gọn, chỉ để hỏi thời lượng bước
        self._nho_don: dict[int, object] = {}   # order_id -> Order (nhớ trong MỘT request)
        self._nho_kh: dict[int, object] = {}    # customer_id -> Customer

    # ================= nền tính =================

    def _khung(self):
        """Khung giờ làm của xưởng — dựng ĐÚNG MỘT LẦN mỗi request rồi dùng lại.

        Mỗi lần dựng là một lượt đọc `work_shifts` + lịch nghỉ; gọi trong vòng lặp là nhân số truy
        vấn theo số lệnh. `lien_tuc` để mặc định `False`: khung THEO CA, nên thời gian ngoài ca
        được cộng vào thanh — đúng mục tiêu của module.

        Dựng lại hai mảnh của `XepLichService` (`_ca_lich_may` + `nghi_xuong`) chứ KHÔNG khởi tạo
        cả service đó: nó kéo theo `BaiGhepService` + năm repository mà màn này không dùng. Hai
        mảnh đều là wrapper mỏng nên nguồn SQL và luật nghỉ vẫn là MỘT chỗ duy nhất.
        """
        if self._lich is None:
            from ...repositories.attendance_repo import AttendanceRepository
            from ...repositories.audit_repo import AuditLogRepository
            from ...repositories.calendar_repo import CalendarRepository
            from ..calendar_service import CalendarService
            from ..xep_lich_2 import constraint as C
            from ..xep_lich_service import LichXuong

            ca = AttendanceRepository(self.db).ca_lich_xuong()
            nghi = tuple(C.doan_nghi_trong_ngay([
                (int(s.start_minute), int(s.end_minute),
                 bool(s.is_overnight) or int(s.end_minute) <= int(s.start_minute),
                 getattr(s, "break_start_minute", None), getattr(s, "break_end_minute", None))
                for s in ca
            ]))
            cal = CalendarService(
                CalendarRepository(self.db), self.audit or AuditLogRepository(self.db)
            )
            self._lich = LichXuong(cal, ca, nghi=nghi)
        return self._lich

    def _dur(self):
        """`LsxService` rút gọn — chỉ để hỏi thời lượng bước.

        Bám precedent `ke_hoach_vat_tu_service.py:911` và `san_xuat/snapshot.py:63`: constructor
        chỉ dựng cache rỗng, `repo` là thứ duy nhất thật sự dùng tới.
        """
        if self._svc_dur is None:
            from ...repositories.lsx_repo import LsxRepository
            from ..lsx_service import LsxService

            self._svc_dur = LsxService(self.db, LsxRepository(self.db), None, None)
        return self._svc_dur

    def _buoc_vao(self, lsx, cds) -> list[BuocVao]:
        """`LsxCongDoan` → `BuocVao`.

        Dùng `chiem_may_phut` (đã gồm chuẩn bị) chứ không `chay_phut`: thứ chiếm chỗ trên trục thời
        gian là toàn bộ thời lượng bước, kể cả canh máy. Máy đọc SỐNG qua `_may_cua_buoc` — tốc độ
        và thời gian chuẩn bị kế thừa từ module Máy, không truyền máy vào là tốc độ 0 ⇒ chạy 0.
        """
        from ..bien_cong_thuc import quy_cach_bien
        from ..lsx_service import thoi_luong_buoc

        svc = self._dur()
        qc = quy_cach_bien(_LsxCoRouting(lsx, cds))
        ra: list[BuocVao] = []
        for cd in cds:
            tt = int(cd.thu_tu or 0)
            if (cd.loai_buoc or LB_MAY) == LB_THUE_NGOAI:
                ra.append(BuocVao(lsx_cong_doan_id=cd.id, thu_tu=tt, chay_phut=0.0,
                                  thue_ngoai_ngay=_ngay_thue_ngoai(cd), la_thue_ngoai=True))
                continue
            may = svc._may_cua_buoc(cd)
            t = thoi_luong_buoc(cd, may, svc.sl_tinh_cua_buoc(cd, may, qc))
            ra.append(BuocVao(lsx_cong_doan_id=cd.id, thu_tu=tt,
                              chay_phut=float(t.get("chiem_may_phut") or 0.0)))
        return ra

    def _trai(self, lsx, cds, moc: datetime) -> KetQuaTrai:
        return trai_lich(moc, self._buoc_vao(lsx, cds), self._khung())

    # ================= đọc =================

    def hang_cho(self, *, tim: str | None = None, trang: int = 1, cd_trang: int = 20) -> dict:
        """Thẻ chờ xếp: lệnh đủ điều kiện mà chưa có mốc. Lọc + phân trang ở MÁY CHỦ."""
        rows, tong = self.repo.hang_cho(
            trang_thai=TT_XEP_DUOC, tim=tim, trang=trang, cd_trang=cd_trang,
        )
        routing = self.repo.routing_theo_lo([r.id for r in rows])
        dong = []
        for l in rows:
            cds = routing.get(l.id, [])
            phut = sum(b.chay_phut for b in self._buoc_vao(l, cds))
            dong.append({
                "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
                "customer_name": self._ten_khach(l),
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
                "han_giao_khach": l.han_giao_khach,
                "is_rush": bool(l.is_rush),
                "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
                "so_luong_dat": int(l.so_luong_dat or 0),
                "don_vi_tinh": l.don_vi_tinh,
                "chay_phut": round(phut, 2),
                "so_buoc": len(cds),
            })
        return {"dong": dong, "tong": tong}

    def lich(self, *, tu: date, den: date) -> dict:
        """Các lệnh CHẠM cửa sổ `[tu, den]`, mỗi lệnh một dòng đã trải sẵn.

        Cắt hai nhịp: SQL loại lệnh bắt đầu sau mép phải, rồi sau khi trải mới loại được lệnh kết
        thúc trước mép trái — `ket_thuc` không có cột nên SQL không biết nó.
        """
        d_tu = datetime.combine(tu, time.min)
        d_den = datetime.combine(den, time.max)
        moc_rows = self.repo.truoc_moc(_aware(d_den))
        lsx_map = self.repo.lsx_theo_ids([m.lsx_id for m in moc_rows])
        routing = self.repo.routing_theo_lo(list(lsx_map))

        dong = []
        for m in moc_rows:
            l = lsx_map.get(m.lsx_id)
            if l is None:                        # lệnh đã xoá, FK CASCADE dọn sau
                continue
            kq = self._trai(l, routing.get(l.id, []), _naive(m.bat_dau_at))
            if kq.ket_thuc < d_tu:               # nằm trọn bên trái cửa sổ
                continue
            dong.append(self._dong(l, m, kq))
        return {"dong": dong, "tong": len(dong)}

    def chi_tiet(self, lsx_id: int) -> dict:
        """Panel dưới: thông tin THẬT của một lệnh + bảng công đoạn.

        Bảng công đoạn KHÔNG có cột mốc bắt đầu/kết thúc: đây là màn cấp LỆNH, mốc từng bước là số
        thừa ở đây (bốn chỗ khác cần thì lấy qua `moc_cong_doan`).
        """
        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        cds = self.repo.routing_theo_lo([lsx_id]).get(lsx_id, [])
        m = self.repo.theo_lsx(lsx_id)
        kq = self._trai(l, cds, _naive(m.bat_dau_at)) if m else None

        qc = dict(l.quy_cach_json or {})         # ẢNH CHỤP lúc tạo lệnh — khoá có thể trống
        don = self._don_cua(l)
        ra = {
            "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
            "trang_thai": l.trang_thai,
            "is_rush": bool(l.is_rush),
            "customer_name": self._ten_khach(l),
            "order_no": getattr(don, "order_no", None),
            "customer_po_no": getattr(don, "customer_po_no", None),
            "sale_name": self._ten_nguoi(getattr(don, "sale_user_id", None)),
            "so_luong_dat": int(l.so_luong_dat or 0),
            "don_vi_tinh": l.don_vi_tinh,
            "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
            "so_to_nguyen": int(l.so_to_nguyen or 0),
            "so_con": int(l.so_con or 1),
            "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
            "han_giao_khach": l.han_giao_khach,
            "nguoi_phu_trach_ten": self._ten_nguoi(l.nguoi_phu_trach_id),
            "luu_y_gui_xuong": l.ghi_chu,
            "giay": _chu(qc.get("giay_ten") or qc.get("giay")),
            "kho_in": _chu(qc.get("kho_in") or qc.get("kho")),
            "so_mau": _chu(qc.get("so_mau") or qc.get("mau")),
            "so_kem": _chu(qc.get("so_kem")),
            "kip_chuan": sum(int(c.so_nhan_cong_tieu_chuan or 0) for c in cds),
            "cong_doans": [self._cd_dict(c, i) for i, c in enumerate(cds)],
        }
        ra.update(self._so_lich(m, kq))
        return ra

    def moc_cong_doan(self, lsx_ids: list[int]) -> dict[int, list[MocBuoc]]:
        """Mốc DẪN XUẤT của từng bước — đường riêng cho bốn chỗ tiêu thụ lịch.

        Không nằm trong payload của màn (spec §4): bàn xếp lịch cấp lệnh cố ý không bày mốc bước.
        """
        moc = self.repo.theo_nhieu_lsx(lsx_ids)
        if not moc:
            return {}
        lsx_map = self.repo.lsx_theo_ids(list(moc))
        routing = self.repo.routing_theo_lo(list(moc))
        ra: dict[int, list[MocBuoc]] = {}
        for lsx_id, m in moc.items():
            l = lsx_map.get(lsx_id)
            if l is None:
                continue
            ra[lsx_id] = self._trai(l, routing.get(lsx_id, []), _naive(m.bat_dau_at)).buoc
        return ra

    # ================= ghi =================

    def dat_moc(self, lsx_id: int, moc: datetime,
                expected_updated_at: datetime | None = None, *, nguoi_id: int | None = None) -> dict:
        """Đặt / dời mốc bắt đầu của một lệnh. KHÔNG chặn gì hết.

        Mốc rơi ngoài giờ chạy thì TRƯỢT vào đầu khoảng chạy được gần nhất và lưu MỐC ĐÃ TRƯỢT —
        lưu mốc người thả thì mỗi lần đọc lại trượt thêm một nhát nữa, và thanh tự đi.
        """
        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        if moc is None:
            raise XepLich3Error("Thiếu giờ bắt đầu.")

        row = self.repo.theo_lsx(lsx_id)
        if row is not None and expected_updated_at is not None:
            hien = _aware(row.updated_at)
            if hien is not None and abs((hien - _aware(expected_updated_at)).total_seconds()) > 1:
                raise XepLich3Conflict(
                    "Lệnh vừa được người khác dời — màn đã cập nhật theo bản mới nhất."
                )

        cds = self.repo.routing_theo_lo([lsx_id]).get(lsx_id, [])
        kq = self._trai(l, cds, moc)
        if row is None:
            row = self.repo.them(XepLichLenh(
                lsx_id=lsx_id, bat_dau_at=_aware(kq.bat_dau), created_by=nguoi_id,
            ))
        else:
            row.bat_dau_at = _aware(kq.bat_dau)
        self.db.flush()
        self.db.commit()
        self.db.refresh(row)

        ra = self._dong(l, row, kq)
        ra["da_doi"] = kq.da_doi
        ra["thong_bao"] = (
            f"Ngoài giờ chạy — đã dời sang {kq.bat_dau.strftime('%H:%M ngày %d/%m')}."
            if kq.da_doi else None
        )
        return ra

    def xoa_moc(self, lsx_id: int, *, nguoi_id: int | None = None) -> None:
        """Bỏ lịch của lệnh — thẻ quay lại hàng chờ. Không đụng trạng thái lệnh."""
        row = self.repo.theo_lsx(lsx_id)
        if row is None:
            raise XepLich3NotFound("Lệnh chưa được xếp lịch.")
        self.repo.xoa(row)
        self.db.commit()

    def phat_hanh(self, lsx_id: int, *, actor=None) -> dict:
        """Phát hành xuống xưởng — BẤM LÀ ĐI.

        KHÔNG gọi `XepLichVanDeService.phat_hanh_lsx`: dù truyền `bo_qua_xung_dot=True` thì hàm đó
        vẫn còn BỐN cửa gác — lệnh phải đang `da_lap_ke_hoach`, cả cụm liên thông phải đã lập kế
        hoạch, vật tư phải giữ đủ, mỗi nhóm thành phẩm phải có đúng một bước KCS cuối. Spec §1 của
        màn 3 là "KHÔNG CHẶN GÌ HẾT", nên ở đây làm thẳng phần THẬT của việc phát hành: đổi trạng
        thái cả cụm + đóng băng gói công việc. Vướng gì thì bày MÀU trên thanh, người điều độ quyết.

        ĐỪNG "sửa lại" thành gọi `phat_hanh_lsx` cho gọn — đó là màn 2, cố ý khác.

        Đơn vị phát hành vẫn là CẢ CỤM liên thông (cùng nhóm thành phẩm · phụ thuộc chéo · bài
        ghép), giống màn 2: gói công việc dưới xưởng dựng theo cụm, thả nửa cụm là snapshot lệch.
        """
        from ...models.bai_ghep import TT_DA_PHAT_HANH as BG_PHAT_HANH
        from ...models.lsx import TT_DA_PHAT_HANH
        from ...repositories.san_xuat_repo import SanXuatRepository
        from ..san_xuat.component import thanh_phan_lien_thong
        from ..san_xuat.release import phat_hanh as _sx_phat_hanh

        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        if l.trang_thai == TT_DA_PHAT_HANH:
            # Không phải cửa gác mà là chống bấm hai lần: phát hành lại đè lên gói đang chạy.
            raise XepLich3Conflict(f"Lệnh {l.ma} đã phát hành rồi — thu hồi trước nếu muốn làm lại.")
        if self.repo.theo_lsx(lsx_id) is None:
            raise XepLich3Error("Lệnh chưa có giờ bắt đầu — đặt mốc trước khi phát hành.")

        sx_repo = SanXuatRepository(self.db)
        tp = thanh_phan_lien_thong(sx_repo, {lsx_id})
        for x in self.repo.lsx_theo_ids(sorted(tp.lsx_ids)).values():
            if x.trang_thai != TT_DA_PHAT_HANH:
                x.trang_thai = TT_DA_PHAT_HANH
        for bg in self._bai_ghep(tp.bai_ghep_ids):
            if bg.trang_thai != BG_PHAT_HANH:
                bg.trang_thai = BG_PHAT_HANH
        _sx_phat_hanh(self.db, lsx_ids=tp.lsx_ids, bai_ghep_ids=tp.bai_ghep_ids, actor=actor)
        if self.audit is not None:
            self.audit.create(
                actor_user_id=getattr(actor, "id", None), action="xep_lich_3_phat_hanh",
                target=f"lsx:{l.id}",
                detail=f"Phát hành lệnh {l.ma} (cụm {len(tp.lsx_ids)} LSX + "
                       f"{len(tp.bai_ghep_ids)} bài ghép) — màn Xếp lịch 3, không cửa gác",
            )
        self.db.commit()
        return {"lsx_id": l.id, "trang_thai": l.trang_thai,
                "cum_lsx": sorted(tp.lsx_ids), "cum_bai_ghep": sorted(tp.bai_ghep_ids)}

    def thu_hoi(self, lsx_id: int, *, actor=None, ly_do: str | None = None) -> dict:
        """Thu hồi phát hành. Đi ĐƯỜNG CHUNG `go_phat_hanh_lsx` — hai điều kiện của nó KHÔNG phải
        cửa gác xếp lịch mà là chuyện dưới xưởng: bắt gõ LÝ DO (đảo một quyết định đã thả xuống
        thì thứ duy nhất còn lại là cái vết), và chặn khi đã có công việc BẮT ĐẦU chạy (§4.3) —
        rút gói lúc thợ đang làm là xoá việc đang chạy, không phải "không chặn gì hết".
        """
        from ..xep_lich_van_de_service import XepLichVanDeService

        l = self.repo.lsx_theo_ids([lsx_id]).get(lsx_id)
        if l is None:
            raise XepLich3NotFound("Không tìm thấy lệnh sản xuất.")
        # Chặn TRƯỚC để ra 400: đường chung ném `XepLichConflict` cho thiếu lý do, mà 409 nghĩa là
        # "người khác vừa đổi" — FE bắt theo mã sẽ hiện sai câu. Cùng ngưỡng 3 ký tự.
        if len((ly_do or "").strip()) < 3:
            raise XepLich3Error(
                "Thu hồi phát hành phải ghi lý do — lệnh đã xuống xưởng, cần vết để đối chiếu sau."
            )
        XepLichVanDeService(self.db, self.audit).go_phat_hanh_lsx(
            lsx_id=lsx_id, actor=actor, ly_do=ly_do,
        )
        return {"lsx_id": lsx_id, "trang_thai": l.trang_thai}

    def _bai_ghep(self, ids) -> list:
        if not ids:
            return []
        from sqlalchemy import select

        from ...models.bai_ghep import BaiGhep

        return list(self.db.execute(select(BaiGhep).where(BaiGhep.id.in_(sorted(ids)))).scalars())

    # ================= dựng payload =================

    def _dong(self, l, m: XepLichLenh, kq: KetQuaTrai) -> dict:
        ra = {
            "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
            "customer_name": self._ten_khach(l),
            "trang_thai": l.trang_thai,
            "is_rush": bool(l.is_rush),
            "so_luong_dat": int(l.so_luong_dat or 0),
            "don_vi_tinh": l.don_vi_tinh,
            "so_to_ke_hoach": int(l.so_to_ke_hoach or 0),
            "so_con": int(l.so_con or 1),
            "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
            "han_giao_khach": l.han_giao_khach,
            "may_ten": self._ten_may_chinh(l),
        }
        ra.update(self._so_lich(m, kq))
        return ra

    def _so_lich(self, m: XepLichLenh | None, kq: KetQuaTrai | None) -> dict:
        """Phần LỊCH của payload — tách ra vì cả dòng Gantt lẫn panel đều cần đúng khối này."""
        if m is None or kq is None:
            return {
                "bat_dau_at": None, "ket_thuc": None, "chay_phut": 0.0,
                "nghi_ngoai_ca_phut": 0.0, "doan": [], "ghi_chu": [], "updated_at": None,
            }
        tong = (kq.ket_thuc - kq.bat_dau).total_seconds() / 60.0
        return {
            "bat_dau_at": kq.bat_dau,
            "ket_thuc": kq.ket_thuc,
            "chay_phut": round(kq.chay_phut, 2),
            # Khoảng hở giữa các đoạn: nghỉ giữa ca + ngoài ca + ngày nghỉ. Đây là con số trả lời
            # đúng câu hỏi của người dùng: "vì sao thanh dài hơn giờ chạy?".
            "nghi_ngoai_ca_phut": round(max(0.0, tong - kq.chay_phut), 2),
            "doan": [
                {"tu": d.tu, "den": d.den, "buoc_index": d.buoc_index} for d in kq.doan
            ],
            "ghi_chu": kq.ghi_chu,
            "updated_at": _naive(m.updated_at),
        }

    def _cd_dict(self, cd, i: int) -> dict:
        from ..lsx_service import thoi_luong_buoc

        svc = self._dur()
        ngoai = (cd.loai_buoc or LB_MAY) == LB_THUE_NGOAI
        may = svc._may_cua_buoc(cd)
        phut = 0.0 if ngoai else float(
            thoi_luong_buoc(cd, may, svc.sl_tinh_cua_buoc(cd, may, None))
            .get("chiem_may_phut") or 0.0
        )
        return {
            "id": cd.id, "thu_tu": int(cd.thu_tu or 0), "ten": cd.ten,
            "loai_buoc": cd.loai_buoc,
            "may_id": cd.may_id,
            "may_ten": getattr(may, "ten", None),
            "to_ten": self._ten_to(cd.department_id),
            "so_luong_vao": float(cd.so_luong_vao or 0),
            "don_vi_vao": cd.don_vi_vao,
            "kip_chuan": int(cd.so_nhan_cong_tieu_chuan or 0),
            "chay_phut": round(phut, 2),
            "thue_ngoai_ngay": _ngay_thue_ngoai(cd) if ngoai else None,
            "mau_index": i % 4,     # sắc độ khối chạy — mã hoá THỨ TỰ bước, không mã hoá loại
        }

    # ================= tra tên =================

    def _don_cua(self, l):
        """Đơn hàng nguồn của lệnh.

        `Lsx` KHÔNG khai relationship `order` — chỉ có FK `order_id` — nên `getattr(l, "order")`
        luôn trả None và bốn ô đầu panel (khách · đơn · PO · sale) hiện "—" mà không lỗi gì. Đọc
        thẳng bằng id, và NHỚ theo id: `_ten_khach` chạy trên từng dòng của hàng chờ lẫn lưới, đọc
        lại mỗi dòng là hoá N+1.
        """
        oid = getattr(l, "order_id", None)
        if not oid:
            return None
        if oid not in self._nho_don:
            from ...models.order import Order

            self._nho_don[oid] = self.db.get(Order, oid)
        return self._nho_don[oid]

    def _ten_khach(self, l) -> str | None:
        cid = getattr(self._don_cua(l), "customer_id", None)
        if not cid:
            return None
        if cid not in self._nho_kh:
            from ...models.customer import Customer

            self._nho_kh[cid] = self.db.get(Customer, cid)
        return getattr(self._nho_kh[cid], "name", None)

    def _ten_nguoi(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        from ...models.user import User

        u = self.db.get(User, user_id)
        return getattr(u, "full_name", None) or getattr(u, "username", None)

    def _ten_to(self, dept_id: int | None) -> str | None:
        if not dept_id:
            return None
        from ...models.department import Department

        return getattr(self.db.get(Department, dept_id), "name", None)

    def _ten_may_chinh(self, l) -> str | None:
        """Máy của bước IN — nhãn nhận diện dòng trên Gantt, không phải danh sách đủ máy."""
        from ...models.may_thiet_bi import MayThietBi

        if not l.may_id:
            return None
        return getattr(self.db.get(MayThietBi, l.may_id), "ten", None)
