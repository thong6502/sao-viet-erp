"""Service Bài ghép — nghiệp vụ gom công đoạn in của nhiều LSX chạy chung 1 tờ.

Số tờ / dư / tổng tờ / % tờ dùng là DẪN XUẤT, tính lúc đọc (`tinh_so_to`), KHÔNG lưu cột. Kiểm
tương thích MỀM (3 mức, không chặn) — người quyết. Gate cứng `san_sang` chỉ 4 điều kiện tối thiểu.
Guard "1 LSX ≤ 1 bài ghép" ở đây (cross-table, soft không unique gọn được). Máy chỉ ghi nhận.
"""
from __future__ import annotations

from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.bai_ghep import (
    TRANG_THAI_BAI_GHEP, TT_DA_LAP_KE_HOACH, TT_NHAP, TT_SAN_SANG, BaiGhep, BaiGhepThanhVien,
)
from ..models.customer import Customer
from ..models.lsx import (
    DV_TO, LB_MAY, TT_DA_LAP_KE_HOACH as LSX_DA_LAP, TT_SAN_SANG as LSX_SAN_SANG,
    Lsx, LsxCongDoan,
)
from ..models.may_thiet_bi import MayThietBi
from ..models.order import STATUS_ORDERED, Order
from ..models.vat_lieu_kho import GiayNguyen

NHOM_PRINT = "print"
LECH_HAN_NGAY = 7  # chênh hạn in > ngưỡng này → cảnh báo "lệch hạn xa"
FILL_THAP = 55.0   # % tờ dùng dưới ngưỡng → cảnh báo "bài thưa, phí giấy"


class BaiGhepError(Exception):
    """Lỗi nghiệp vụ bài ghép (router map sang HTTP)."""


class BaiGhepNotFound(BaiGhepError):
    pass


class BaiGhepValidationError(BaiGhepError):
    pass


class BaiGhepConflict(BaiGhepError):
    pass


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _kho(d, r) -> str | None:
    return f"{int(d)}×{int(r)}" if d and r else None


def _cac_buoc_in(lsx: Lsx) -> list:
    """Mọi bước IN MÁY của lệnh, theo thứ tự routing.

    Lệnh thường có đúng một; nhưng in 2 lượt (mặt trước / mặt sau tách dòng, in nền + màu pha)
    thì có nhiều — lúc đó máy KHÔNG được đoán lượt nào ghép chung tờ.
    """
    return sorted(
        (cd for cd in lsx.cong_doans if cd.nhom == NHOM_PRINT and cd.loai_buoc == LB_MAY),
        key=lambda cd: cd.thu_tu,
    )


def _co_cong_doan_in(lsx: Lsx) -> bool:
    return bool(_cac_buoc_in(lsx))


class BaiGhepService:
    def __init__(self, db: Session, repo, audit, sequence) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.sequence = sequence
        self._lsx_service = None   # dựng trễ, xem `_lsx_svc`

    # ================= tra cứu phụ trợ =================

    def _lsx_svc(self):
        """`LsxService` dựng trễ để hỏi chuỗi ngược của lệnh.

        Import trong hàm + dựng theo yêu cầu: `lsx_service` là module nặng và bài ghép chỉ cần
        đúng một hàm THUẦN của nó (`tinh_nguoc_routing`), không cần vòng đời chung.
        """
        if self._lsx_service is None:
            from ..repositories.lsx_repo import LsxRepository
            from .lsx_service import LsxService

            self._lsx_service = LsxService(
                self.db, LsxRepository(self.db), self.audit, self.sequence
            )
        return self._lsx_service

    def _get(self, bai_ghep_id: int) -> BaiGhep:
        bg = self.repo.get(bai_ghep_id)
        if bg is None:
            raise BaiGhepNotFound("Không tìm thấy bài ghép")
        return bg

    def _lsx_map(self, bg: BaiGhep) -> dict[int, Lsx]:
        return self.repo.lsx_by_ids([tv.lsx_id for tv in bg.thanh_viens])

    def _giay_names(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(
            select(GiayNguyen.id, GiayNguyen.ten).where(GiayNguyen.id.in_(ids))
        ).all()
        return {i: n for i, n in rows}

    def _may_names(self, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.db.execute(
            select(MayThietBi.id, MayThietBi.ten).where(MayThietBi.id.in_(ids))
        ).all()
        return {i: n for i, n in rows}

    def _customer_names(self, order_ids: set[int]) -> dict[int, str | None]:
        order_ids = {i for i in order_ids if i}
        if not order_ids:
            return {}
        rows = self.db.execute(
            select(Order.id, Customer.name)
            .join(Customer, Customer.id == Order.customer_id, isouter=True)
            .where(Order.id.in_(order_ids))
        ).all()
        return {oid: name for oid, name in rows}

    def _mark_nhap(self, bg: BaiGhep) -> None:
        """Sửa/thêm/bỏ thành viên khi bài đã 'sẵn sàng' → tự rớt về nháp (cancel + recombine)."""
        if bg.trang_thai == TT_SAN_SANG:
            bg.trang_thai = TT_NHAP

    def _chan_da_lap(self, bg: BaiGhep) -> None:
        """Đã lập kế hoạch → khóa sửa thành viên/giấy (gỡ kế hoạch ở màn Xếp lịch để mở lại)."""
        if bg.trang_thai == TT_DA_LAP_KE_HOACH:
            raise BaiGhepConflict("Bài ghép đã lập kế hoạch — gỡ kế hoạch trước khi sửa")

    # ================= HÀNG CHỜ GHÉP =================

    def hang_cho_ghep(self, *, giay_id: int | None = None, q: str | None = None) -> list[dict]:
        lsxs = self.repo.hang_cho_ghep()
        cust = self._customer_names({l.order_id for l in lsxs})
        out: list[dict] = []
        for l in lsxs:
            qc = l.quy_cach_json or {}
            if giay_id is not None and qc.get("giay_id") != giay_id:
                continue
            if q:
                like = q.strip().lower()
                if like not in (l.ma or "").lower() and like not in (l.ten or "").lower():
                    continue
            out.append({
                "lsx_id": l.id, "ma": l.ma, "ten": l.ten,
                "so_luong_dat": l.so_luong_dat, "don_vi_tinh": l.don_vi_tinh,
                "so_con": l.so_con,
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx, "is_rush": bool(l.is_rush),
                "order_id": l.order_id, "customer_name": cust.get(l.order_id),
                "giay_id": qc.get("giay_id"), "giay_ten": qc.get("giay_ten"), "gsm": qc.get("gsm"),
                "so_mau_a": qc.get("so_mau_a"), "so_mau_b": qc.get("so_mau_b"),
                "quy_cach_in": qc.get("quy_cach_in"),
                "kho_tp": _kho(qc.get("dai_thanh_pham"), qc.get("rong_thanh_pham")),
                "kho_in": _kho(qc.get("kho_in_dai"), qc.get("kho_in_rong")),
            })
        return out

    # ================= TẠO / SỬA THÀNH VIÊN =================

    def _validate_them(self, lsx_ids: list[int], lsx_map: dict[int, Lsx]) -> None:
        for i in lsx_ids:
            l = lsx_map.get(i)
            if l is None:
                raise BaiGhepValidationError(f"LSX #{i} không tồn tại")
            if l.trang_thai != LSX_SAN_SANG:
                raise BaiGhepValidationError(f"LSX {l.ma} chưa sẵn sàng lập kế hoạch")
            if not _co_cong_doan_in(l):
                raise BaiGhepValidationError(f"LSX {l.ma} không có công đoạn in")
        da = self.repo.lsx_da_ghep(lsx_ids)
        if da:
            raise BaiGhepConflict("Có LSX đã thuộc bài ghép khác — gỡ khỏi bài đó trước")

    def tao(self, *, lsx_ids: list[int], actor) -> BaiGhep:
        ids = list(dict.fromkeys(int(i) for i in lsx_ids if i))  # khử trùng, giữ thứ tự
        if not ids:
            raise BaiGhepValidationError("Chưa chọn LSX nào để ghép")
        lsx_map = self.repo.lsx_by_ids(ids)
        self._validate_them(ids, lsx_map)
        bg = BaiGhep(
            ma=self.sequence.generate_code("bai_ghep"),
            trang_thai=TT_NHAP,
            created_by=getattr(actor, "id", None),
        )
        for i in ids:
            bg.thanh_viens.append(BaiGhepThanhVien(
                lsx_id=i,
                so_con_tren_to=int(lsx_map[i].so_con or 1),
                # Lệnh một lượt in → điền luôn, người dùng không phải làm gì. Nhiều lượt thì để
                # trống và `thieu_cua` sẽ đòi chọn — máy không đoán khi câu trả lời không hiển nhiên.
                buoc_in_step_key=(
                    buoc_in[0].step_key if len(buoc_in := _cac_buoc_in(lsx_map[i])) == 1 else None
                ),
            ))
        self._goi_y_giay_kho(bg, lsx_map)
        self.repo.add(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="tao_bai_ghep",
            target=f"bai_ghep:{bg.id}", detail=f"Tạo bài ghép {bg.ma} ({len(ids)} LSX)",
        )
        self.repo.commit()
        return self._get(bg.id)

    def _goi_y_giay_kho(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> None:
        """Gợi ý giấy + khổ in chung từ thành viên nếu đồng nhất — người sửa được sau."""
        giay_ids, kho = set(), None
        for tv in bg.thanh_viens:
            qc = (lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {}
            giay_ids.add(qc.get("giay_id"))
            if kho is None and qc.get("kho_in_dai") and qc.get("kho_in_rong"):
                kho = (int(qc["kho_in_dai"]), int(qc["kho_in_rong"]))
        if len(giay_ids) == 1 and (only := next(iter(giay_ids))):
            bg.giay_id = only
        if kho:
            bg.kho_in_dai, bg.kho_in_rong = kho

    def them_thanh_vien(self, *, bai_ghep_id: int, lsx_ids: list[int], actor) -> BaiGhep:
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        co_san = {tv.lsx_id for tv in bg.thanh_viens}
        ids = [int(i) for i in dict.fromkeys(lsx_ids) if int(i) not in co_san]
        if not ids:
            raise BaiGhepValidationError("Không có LSX mới để thêm")
        lsx_map = self.repo.lsx_by_ids(ids)
        self._validate_them(ids, lsx_map)
        for i in ids:
            bg.thanh_viens.append(BaiGhepThanhVien(
                lsx_id=i,
                so_con_tren_to=int(lsx_map[i].so_con or 1),
                # Lệnh một lượt in → điền luôn, người dùng không phải làm gì. Nhiều lượt thì để
                # trống và `thieu_cua` sẽ đòi chọn — máy không đoán khi câu trả lời không hiển nhiên.
                buoc_in_step_key=(
                    buoc_in[0].step_key if len(buoc_in := _cac_buoc_in(lsx_map[i])) == 1 else None
                ),
            ))
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="them_thanh_vien",
            target=f"bai_ghep:{bg.id}", detail=f"Thêm {len(ids)} LSX vào {bg.ma}",
        )
        self.repo.commit()
        return self._get(bg.id)

    def bo_thanh_vien(self, *, bai_ghep_id: int, thanh_vien_id: int, actor) -> BaiGhep:
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        tv = next((t for t in bg.thanh_viens if t.id == thanh_vien_id), None)
        if tv is None:
            raise BaiGhepNotFound("Không tìm thấy thành viên")
        lsx_id_bo = tv.lsx_id
        bg.thanh_viens.remove(tv)
        self.db.flush()
        # Gỡ khỏi bài → thông số in trả về bài tính giá gốc (bố cục in riêng), không giữ số của bài.
        self._tinh_lai_lenh(bg, [lsx_id_bo])
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="bo_thanh_vien",
            target=f"bai_ghep:{bg.id}", detail=f"Bỏ 1 LSX khỏi {bg.ma}",
        )
        self.repo.commit()
        return self._get(bg.id)

    def sua_thanh_vien(self, *, bai_ghep_id: int, thanh_vien_id: int, so_con_tren_to: int,
                       actor, buoc_in_step_key: str | None = None) -> BaiGhep:
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        tv = next((t for t in bg.thanh_viens if t.id == thanh_vien_id), None)
        if tv is None:
            raise BaiGhepNotFound("Không tìm thấy thành viên")
        if int(so_con_tren_to) < 0:
            raise BaiGhepValidationError("Số con/tờ không hợp lệ")
        tv.so_con_tren_to = int(so_con_tren_to)
        if buoc_in_step_key is not None:
            lsx = self.repo.lsx_by_ids([tv.lsx_id]).get(tv.lsx_id)
            hop_le = {cd.step_key for cd in _cac_buoc_in(lsx)} if lsx else set()
            if buoc_in_step_key not in hop_le:
                raise BaiGhepValidationError("Bước đã chọn không phải công đoạn in của lệnh này")
            tv.buoc_in_step_key = buoc_in_step_key
        self._tinh_lai_lenh(bg, [tv.lsx_id])
        self._mark_nhap(bg)
        self.repo.commit()
        return self._get(bg.id)

    def sua(self, *, bai_ghep_id: int, patch: dict, actor) -> BaiGhep:
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        for field in ("giay_id", "kho_in_dai", "kho_in_rong", "may_id", "hao_hut_setup",
                      "hao_hut_chay", "ghi_chu"):
            if field in patch:
                setattr(bg, field, patch[field])
        # Khổ tờ in đổi → số mảnh xả của thành viên đổi theo.
        if {"kho_in_dai", "kho_in_rong"} & set(patch):
            self._tinh_lai_lenh(bg)
        self.repo.commit()
        return self._get(bg.id)

    def _tinh_lai_lenh(self, bg: BaiGhep, lsx_ids: list[int] | None = None) -> None:
        """Chạy lại chuỗi ngược cho các lệnh liên quan — KHÔNG commit (caller commit).

        Thông số tờ của lệnh là DẪN XUẤT của bài khi đã ghép (số con, khổ tờ in → số mảnh xả).
        Không có chỗ nối này thì sửa số con ở bài xong, màn lệnh vẫn giữ số tờ cũ — hai màn lệch
        nhau ngay lần gõ đầu tiên. Gỡ khỏi bài cũng gọi hàm này: hết ghép thì `_he_so_cau` tự rơi
        về số của bài tính giá.
        """
        ids = lsx_ids if lsx_ids is not None else [tv.lsx_id for tv in bg.thanh_viens]
        if not ids:
            return
        svc = self._lsx_svc()
        for lsx in self.repo.lsx_by_ids(ids).values():
            svc._ap_chuoi_nguoc(lsx)

    # ================= ENGINE (thuần) =================

    def _nhu_cau_to(self, lsx: Lsx | None, so_con: int) -> int:
        """Số TỜ IN mà lệnh này thật sự cần khi xếp `so_con` con/tờ.

        Lấy từ chuỗi ngược của lệnh nên ĐÃ GỒM hao của mọi bước sau in (gấp, bắt tay, vào keo,
        xén). Công thức cũ `ceil(SL đặt / con)` lấy số thành phẩm giao khách — thiếu đúng phần
        hao đó, nên bài ghép cấp không đủ giấy mà không ai báo.

        Không tính được (lệnh chưa có routing dòng giấy) → rơi về `ceil(SL đặt / con)`, tức đúng
        bằng hành vi cũ, chứ không trả 0 làm bài tưởng không cần tờ nào.
        """
        can = int(getattr(lsx, "so_luong_dat", 0) or 0) if lsx else 0
        if lsx is None or so_con <= 0 or can <= 0:
            return 0
        rows = {r["idx"]: r for r in self._lsx_svc().tinh_nguoc_routing(lsx, so_con=so_con)}
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        vao_to = next(
            (r["so_luong_vao"] for i, cd in enumerate(buoc)
             if cd.don_vi_vao == DV_TO and (r := rows.get(i))),
            None,
        )
        return ceil(_f(vao_to)) if vao_to else ceil(can / so_con)

    def tinh_so_to(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        rows: list[dict] = []
        so_to_tot = 0
        for tv in bg.thanh_viens:
            l = lsx_map.get(tv.lsx_id)
            can = int(getattr(l, "so_luong_dat", 0) or 0) if l else 0
            con = int(tv.so_con_tren_to or 0)
            per = self._nhu_cau_to(l, con)
            if con > 0:
                so_to_tot = max(so_to_tot, per)
            rows.append({"thanh_vien_id": tv.id, "lsx_id": tv.lsx_id, "can": can, "con": con,
                         "nhu_cau_to": per})
        for r in rows:
            r["san_luong_du_kien"] = so_to_tot * r["con"] if r["con"] > 0 else 0
            r["du"] = r["san_luong_du_kien"] - r["can"]
        tong_to = so_to_tot + int(bg.hao_hut_setup or 0) + int(bg.hao_hut_chay or 0)

        fill_pct = None
        if bg.kho_in_dai and bg.kho_in_rong:
            area = _f(bg.kho_in_dai) * _f(bg.kho_in_rong)
            used = 0.0
            for tv in bg.thanh_viens:
                qc = (lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {}
                used += _f(qc.get("dai_thanh_pham")) * _f(qc.get("rong_thanh_pham")) * int(tv.so_con_tren_to or 0)
            fill_pct = round(used / area * 100, 1) if area > 0 else None

        hans = [l.han_hoan_thanh_sx for tv in bg.thanh_viens
                if (l := lsx_map.get(tv.lsx_id)) and l.han_hoan_thanh_sx]
        return {
            "so_to_tot": so_to_tot,
            "tong_to": tong_to,
            "fill_pct": fill_pct,
            "han_in_muon_nhat": min(hans) if hans else None,
            "rows": rows,
        }

    # ================= SƠ ĐỒ (dẫn xuất, không lưu cạnh) =================

    def so_do(self, bg: BaiGhep) -> dict:
        """Đồ thị của bài: N nhánh vào → MỘT node IN → N nhánh ra.

        DẪN XUẤT hoàn toàn, dựng lúc đọc từ ba nguồn đã có: thành viên bài + routing từng lệnh +
        vị trí bước in trong routing đó. KHÔNG thêm cạnh xuyên đơn vào `lsx_cong_doan_phu_thuoc`
        — quan hệ ghép sinh từ vật lý tờ giấy, bằng chứng là bản ghi thành viên, không phải quan
        hệ người dùng khai. Mở cửa cho cạnh xuyên đơn là mở cửa cho khai bừa.

        Mỗi lệnh giữ chuỗi riêng CẢ TRƯỚC LẪN SAU in (kể cả chế bản) — chỉ tờ giấy trên máy in là
        chung.
        """
        lsx_map = self._lsx_map(bg)
        so_to = self.tinh_so_to(bg, lsx_map)
        du_by_tv = {r["thanh_vien_id"]: r for r in so_to["rows"]}
        cust = self._customer_names({l.order_id for l in lsx_map.values()})
        svc = self._lsx_svc()
        dept_names = svc._dept_names(
            {cd.department_id for l in lsx_map.values() for cd in l.cong_doans if cd.department_id}
        )
        may_names = svc._may_names(
            {cd.may_id for l in lsx_map.values() for cd in l.cong_doans if cd.may_id}
            | {bg.may_id}
        )
        trong_so_do: set[str] = set()
        nhanh: list[dict] = []

        for mau, tv in enumerate(bg.thanh_viens):
            l = lsx_map.get(tv.lsx_id)
            if l is None:
                continue
            buoc = sorted(l.cong_doans, key=lambda c: c.thu_tu)
            key_in = tv.buoc_in_step_key or next(
                (cd.step_key for cd in _cac_buoc_in(l)), None
            )
            vi_tri = next((i for i, cd in enumerate(buoc) if cd.step_key == key_in), None)
            truoc = buoc[:vi_tri] if vi_tri is not None else buoc
            sau = buoc[vi_tri + 1:] if vi_tri is not None else []
            trong_so_do.update(cd.step_key for cd in buoc)
            r = du_by_tv.get(tv.id, {})
            nhanh.append({
                "thanh_vien_id": tv.id, "lsx_id": l.id, "lsx_ma": l.ma, "lsx_ten": l.ten,
                "customer_name": cust.get(l.order_id),
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
                "is_rush": bool(l.is_rush),
                "mau": mau,
                "so_con_tren_to": tv.so_con_tren_to,
                "buoc_in_step_key": key_in,
                "buoc_in_chon_duoc": [
                    {"step_key": cd.step_key, "ten": cd.ten, "thu_tu": cd.thu_tu}
                    for cd in _cac_buoc_in(l)
                ],
                "nhu_cau_to": r.get("nhu_cau_to", 0),
                "du": r.get("du", 0),
                "truoc_in": [self._node(cd, dept_names, may_names) for cd in truoc],
                "sau_in": [self._node(cd, dept_names, may_names) for cd in sau],
            })

        # Tiền nhiệm NGOÀI sơ đồ (vd ruột sách của cùng đơn, không nằm trong bài) → node bóng mờ.
        # Hai kiểu hội tụ khác nhau: ở IN là máy suy, ở nhánh là người khai — vẽ cả hai mới đủ.
        can_ngoai = {
            k for n in nhanh for cd in (n["truoc_in"] + n["sau_in"])
            for k in cd["phu_thuoc_step_keys"] if k not in trong_so_do
        }
        ngoai = [
            {"step_key": cd.step_key, "ten": cd.ten,
             "lsx_ma": (lx.ma if (lx := self.db.get(Lsx, cd.lsx_id)) else None)}
            for cd in self.db.execute(
                select(LsxCongDoan).where(LsxCongDoan.step_key.in_(can_ngoai))
            ).scalars()
        ] if can_ngoai else []

        return {
            "bai_ghep": {
                "id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai,
                "may_id": bg.may_id, "may_ten": may_names.get(bg.may_id),
                "giay_id": bg.giay_id,
                "giay_ten": self._giay_names({bg.giay_id}).get(bg.giay_id),
                "kho_in_dai": bg.kho_in_dai, "kho_in_rong": bg.kho_in_rong,
                "hao_hut_setup": bg.hao_hut_setup, "hao_hut_chay": bg.hao_hut_chay,
                "so_to_tot": so_to["so_to_tot"], "tong_to": so_to["tong_to"],
                "fill_pct": so_to["fill_pct"],
            },
            "nhanh": nhanh,
            "ngoai": ngoai,
        }

    def _node(self, cd, dept_names: dict, may_names: dict) -> dict:
        """Node gọn cho sơ đồ — chỉ thứ mắt cần: làm gì · ai làm · bao lâu · chờ ai."""
        from .lsx_service import thoi_luong_buoc

        t = thoi_luong_buoc(cd)
        return {
            "step_key": cd.step_key, "ten": cd.ten, "nhom": cd.nhom,
            "loai_buoc": cd.loai_buoc, "thu_tu": cd.thu_tu,
            "to_ten": dept_names.get(cd.department_id),
            "may_ten": may_names.get(cd.may_id),
            "nha_cung_cap": cd.nha_cung_cap,
            "tong_phut": t["tong_phut"], "chiem_may_phut": t["chiem_may_phut"],
            "phu_thuoc_step_keys": [
                p.step_key for edge in cd.phu_thuoc
                if (p := self.db.get(LsxCongDoan, edge.buoc_truoc_id)) is not None
            ],
        }

    # ================= KIỂM TƯƠNG THÍCH (mềm) =================

    def kiem_tuong_thich(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        tvs = bg.thanh_viens
        qcs = [(lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {} for tv in tvs]

        def _row(nhan, vals, muc):
            return {"thuoc_tinh": nhan, "gia_tri": vals, "muc": muc}

        rows = []
        # Giấy: thiếu → không phù hợp; khác → cần xác nhận; giống → phù hợp.
        giays = [qc.get("giay_id") for qc in qcs]
        giay_ten = [qc.get("giay_ten") for qc in qcs]
        if any(g is None for g in giays):
            muc = "khong_phu_hop"
        elif len(set(giays)) <= 1:
            muc = "phu_hop"
        else:
            muc = "can_xac_nhan"
        rows.append(_row("Giấy", [t or "—" for t in giay_ten], muc))

        # Số màu (proxy — không auto phù hợp theo con số): giống → phù hợp, khác → cần xác nhận.
        maus = [f"{qc.get('so_mau_a') or 0}/{qc.get('so_mau_b') or 0}" for qc in qcs]
        rows.append(_row("Số màu", maus, "phu_hop" if len(set(maus)) <= 1 else "can_xac_nhan"))

        # Số mặt/trở.
        mats = [qc.get("quy_cach_in") or "—" for qc in qcs]
        rows.append(_row("Số mặt/trở", mats, "phu_hop" if len(set(mats)) <= 1 else "can_xac_nhan"))

        # Khổ thành phẩm — CHỈ hiển thị (khác khổ TP là bình thường, không phán mức).
        khos = [_kho(qc.get("dai_thanh_pham"), qc.get("rong_thanh_pham")) or "—" for qc in qcs]
        rows.append(_row("Khổ thành phẩm", khos, "phu_hop"))

        return {"thanh_vien": [{"lsx_id": tv.lsx_id} for tv in tvs], "rows": rows}

    # ================= CHECKLIST =================

    def thieu_cua(self, bg: BaiGhep, lsx_map: dict[int, Lsx] | None = None) -> list[str]:
        """Gate CHẶN 'sẵn sàng xếp lịch' — tối thiểu để bài chạy được."""
        lsx_map = lsx_map or self._lsx_map(bg)
        thieu: list[str] = []
        if len(bg.thanh_viens) < 2:
            thieu.append("thieu_thanh_vien")
        if not bg.giay_id:
            thieu.append("thieu_giay")
        if not (bg.kho_in_dai and bg.kho_in_rong):
            thieu.append("thieu_kho_in")
        if any(int(tv.so_con_tren_to or 0) <= 0 for tv in bg.thanh_viens):
            thieu.append("thieu_ups")
        # Lệnh nhiều lượt in mà chưa chỉ lượt nào ghép chung → không biết cắt chuỗi ở đâu.
        if any(tv.buoc_in_step_key is None and len(_cac_buoc_in(l)) > 1
               for tv in bg.thanh_viens if (l := lsx_map.get(tv.lsx_id))):
            thieu.append("thieu_buoc_in")
        # Số tờ chạy = MAX nhu cầu các thành viên, nên không thành viên nào có thể thiếu tờ —
        # "thiếu giấy" trước đây là hệ quả của công thức cũ (lấy SL đặt, bỏ hao các bước sau in),
        # sửa công thức là hết, không cần thêm cổng chặn.
        if self.tinh_so_to(bg, lsx_map)["so_to_tot"] <= 0:
            thieu.append("thieu_so_to")
        return thieu

    def canh_bao_cua(self, bg: BaiGhep, lsx_map: dict[int, Lsx] | None = None,
                     so_to: dict | None = None) -> list[str]:
        """Rổ cảnh báo MỀM — chỉ tô màu, KHÔNG chặn. Phán đoán nghề để người quyết."""
        lsx_map = lsx_map or self._lsx_map(bg)
        so_to = so_to or self.tinh_so_to(bg, lsx_map)
        cb: list[str] = []
        qcs = [(lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {}
               for tv in bg.thanh_viens]

        if len({qc.get("giay_id") for qc in qcs}) > 1:
            cb.append("khac_giay")
        if len({f"{qc.get('so_mau_a') or 0}/{qc.get('so_mau_b') or 0}" for qc in qcs}) > 1:
            cb.append("khac_so_mau")
        if len({qc.get("quy_cach_in") for qc in qcs}) > 1:
            cb.append("khac_so_mat")

        lsxs = [lsx_map.get(tv.lsx_id) for tv in bg.thanh_viens]
        if any(l and l.is_rush for l in lsxs):
            cb.append("co_gap")
        hans = [l.han_hoan_thanh_sx for l in lsxs if l and l.han_hoan_thanh_sx]
        if len(hans) >= 2 and (max(hans) - min(hans)).days > LECH_HAN_NGAY:
            cb.append("lech_han")
        if any(l and l.trang_thai not in (LSX_SAN_SANG, LSX_DA_LAP) for l in lsxs):
            cb.append("thanh_vien_khong_san_sang")
        # Đơn thành viên bị huỷ sau khi ghép.
        order_ids = {l.order_id for l in lsxs if l}
        if order_ids:
            con_ban = set(self.db.execute(
                select(Order.id).where(Order.id.in_(order_ids), Order.status == STATUS_ORDERED)
            ).scalars())
            if any(l and l.order_id not in con_ban for l in lsxs):
                cb.append("don_huy")

        fill = so_to.get("fill_pct")
        if fill is not None and fill < FILL_THAP:
            cb.append("bai_thua")
        return cb

    # ================= TRẠNG THÁI / XOÁ =================

    def set_trang_thai(self, *, bai_ghep_id: int, trang_thai: str, actor) -> BaiGhep:
        bg = self._get(bai_ghep_id)
        if trang_thai not in TRANG_THAI_BAI_GHEP:
            raise BaiGhepValidationError("Trạng thái không hợp lệ")
        if trang_thai == TT_DA_LAP_KE_HOACH:
            raise BaiGhepValidationError("Lập kế hoạch qua màn Xếp lịch, không đổi trực tiếp ở đây")
        if bg.trang_thai == TT_DA_LAP_KE_HOACH:
            raise BaiGhepConflict("Bài ghép đã lập kế hoạch — gỡ kế hoạch trước")
        if trang_thai == TT_SAN_SANG and self.thieu_cua(bg):
            raise BaiGhepConflict("Còn thiếu dữ liệu — bổ sung xong mới đánh dấu sẵn sàng")
        bg.trang_thai = trang_thai
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="bai_ghep_trang_thai",
            target=f"bai_ghep:{bg.id}", detail=f"Bài ghép {bg.ma} → {trang_thai}",
        )
        self.repo.commit()
        return self._get(bg.id)

    def xoa(self, *, bai_ghep_id: int, actor) -> None:
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        ma = bg.ma
        self.repo.delete(bg)  # cascade xoá thành viên → LSX tự do lại
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="xoa_bai_ghep",
            target=f"bai_ghep:{bai_ghep_id}", detail=f"Xoá bài ghép {ma}",
        )
        self.repo.commit()

    # ================= DTO cho router =================

    def list_rows(self) -> list[dict]:
        bgs = self.repo.list()
        lsx_map = self.repo.lsx_by_ids([tv.lsx_id for bg in bgs for tv in bg.thanh_viens])
        giay = self._giay_names({bg.giay_id for bg in bgs})
        out = []
        for bg in bgs:
            so_to = self.tinh_so_to(bg, lsx_map)
            out.append({
                "id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai,
                "so_lsx": len(bg.thanh_viens),
                "giay_ten": giay.get(bg.giay_id),
                "kho_in": _kho(bg.kho_in_dai, bg.kho_in_rong),
                "so_to_tot": so_to["so_to_tot"], "tong_to": so_to["tong_to"],
                "han_in_muon_nhat": so_to["han_in_muon_nhat"],
                "so_canh_bao": len(self.canh_bao_cua(bg, lsx_map, so_to)),
            })
        return out

    def detail_dict(self, bg: BaiGhep) -> dict:
        lsx_map = self._lsx_map(bg)
        so_to = self.tinh_so_to(bg, lsx_map)
        du_by_tv = {r["thanh_vien_id"]: r for r in so_to["rows"]}
        giay = self._giay_names({bg.giay_id} | {
            (lsx_map[tv.lsx_id].quy_cach_json or {}).get("giay_id")
            for tv in bg.thanh_viens if tv.lsx_id in lsx_map
        })
        may = self._may_names({bg.may_id})

        thanh_vien = []
        for tv in bg.thanh_viens:
            l = lsx_map.get(tv.lsx_id)
            qc = (l.quy_cach_json or {}) if l else {}
            r = du_by_tv.get(tv.id, {})
            thanh_vien.append({
                "thanh_vien_id": tv.id, "lsx_id": tv.lsx_id,
                "lsx_ma": l.ma if l else None, "lsx_ten": l.ten if l else None,
                "so_luong_dat": l.so_luong_dat if l else 0,
                "don_vi_tinh": l.don_vi_tinh if l else None,
                "is_rush": bool(l.is_rush) if l else False,
                "trang_thai_lsx": l.trang_thai if l else None,
                "so_con_tren_to": tv.so_con_tren_to,
                # Bước in nào của lệnh chạy chung tờ + các lượt in chọn được (lệnh in 2 lượt).
                "buoc_in_step_key": tv.buoc_in_step_key,
                "buoc_in_chon_duoc": [
                    {"step_key": cd.step_key, "ten": cd.ten, "thu_tu": cd.thu_tu}
                    for cd in (_cac_buoc_in(l) if l else [])
                ],
                # Số tờ lệnh này THẬT SỰ cần (đã gồm hao các bước sau in) — để màn bài giải thích
                # được vì sao số tờ chạy là 5.075 chứ không phải 5.000.
                "nhu_cau_to": r.get("nhu_cau_to", 0),
                "san_luong_du_kien": r.get("san_luong_du_kien", 0), "du": r.get("du", 0),
                "giay_id": qc.get("giay_id"), "giay_ten": qc.get("giay_ten"),
                "so_mau_a": qc.get("so_mau_a"), "so_mau_b": qc.get("so_mau_b"),
                "quy_cach_in": qc.get("quy_cach_in"),
                "kho_tp": _kho(qc.get("dai_thanh_pham"), qc.get("rong_thanh_pham")),
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx if l else None,
            })

        return {
            "id": bg.id, "ma": bg.ma, "trang_thai": bg.trang_thai,
            "giay_id": bg.giay_id, "giay_ten": giay.get(bg.giay_id),
            "kho_in_dai": bg.kho_in_dai, "kho_in_rong": bg.kho_in_rong,
            "may_id": bg.may_id, "may_ten": may.get(bg.may_id),
            "hao_hut_setup": bg.hao_hut_setup, "hao_hut_chay": bg.hao_hut_chay,
            "ghi_chu": bg.ghi_chu,
            "thanh_vien": thanh_vien,
            "so_to": so_to,
            "tuong_thich": self.kiem_tuong_thich(bg, lsx_map),
            "thieu": self.thieu_cua(bg, lsx_map),
            "canh_bao": self.canh_bao_cua(bg, lsx_map, so_to),
        }
