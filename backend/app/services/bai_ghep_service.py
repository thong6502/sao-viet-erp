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
from ..models.bai_ghep_cong_doan import (
    BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu,
)
from ..models.bu_hao import BuHao
from ..models.cong_doan import CongDoan
from ..models.customer import Customer
from ..models.khuon_be import KhuonBe
from ..models.lsx import (
    LB_MAY,
    TT_DA_LAP_KE_HOACH as LSX_DA_LAP, TT_SAN_SANG as LSX_SAN_SANG,
    Lsx, LsxCongDoan, LsxCongDoanPhuThuoc,
)
from ..models.may_thiet_bi import MayThietBi
from ..models.order import STATUS_ORDERED, Order
from ..models.vat_lieu_kho import GiayNguyen, VatTuInAn
from .bai_ghep_graph import (
    Buoc as GBuoc, CanhGoc as GCanh, co_do_thi, kiem_gop,
    ung_vien_gop as _ung_vien_gop,
)
from ._may_fit import LY_DO_GSM, LY_DO_KHO, LY_DO_SO_MAU, kiem_kha_nang
from .bu_hao_engine import chuoi_nguoc_dv, hao_buoc
from ..models.don_vi_do import TRAM_CAI, TRAM_TAY, TRAM_TO, TRAM_TO_NGUYEN
from .dong_giay import ban_do_tram, don_vi_chuoi, tram_cua, tren_dong_giay
from .piece_work_service import khoan_snapshot
from .thanh_phan_engine import (
    cau_to_sang_cai, la_gap_tay, so_kem_moi_tay, so_mau_dan_xuat, so_tay_moi_cuon, tap_muc,
    tap_muc_tu_so,
)
from .tinh_gia_service import _bu_hao_to_dict

NHOM_PRINT = "print"
LECH_HAN_NGAY = 7  # chênh hạn in > ngưỡng này → cảnh báo "lệch hạn xa"
# Nhãn tiếng Việt cho lý do máy không kham (mã từ `_may_fit`).
_LY_DO_MAY_VN = {
    LY_DO_KHO: "Khổ tờ ghép vượt khổ máy",
    LY_DO_SO_MAU: "Số màu vượt số đầu mực máy",
    LY_DO_GSM: "Định lượng giấy ngoài dải máy",
}


class BaiGhepError(Exception):
    """Lỗi nghiệp vụ bài ghép (router map sang HTTP)."""


class BaiGhepNotFound(BaiGhepError):
    pass


class BaiGhepValidationError(BaiGhepError):
    pass


class BaiGhepConflict(BaiGhepError):
    pass


class BaiGhepVongPhuThuoc(BaiGhepConflict):
    """Gộp sẽ tạo vòng — mang theo CHU TRÌNH và NHÂN CHỨNG, không chỉ một câu chữ.

    Router trả nguyên cấu trúc này xuống 409 để canvas tô đúng cặp bước mâu thuẫn thay vì chỉ
    hiện một dòng chữ rồi để người dùng tự dò xem bước nào chọi bước nào.
    """

    def __init__(self, vong) -> None:
        super().__init__(vong.thong_diep)
        self.nut = list(vong.nut)
        self.tu_tro = bool(vong.tu_tro)
        self.nhan_chung = [{"truoc": c.truoc, "sau": c.sau} for c in vong.nhan_chung]


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
        self._bu_hao_cache: list[dict] | None = None
        self._tram_cache: dict[str, str] | None = None

    def _tram(self) -> dict[str, str]:
        """Bản đồ `{mã đơn vị: trạm}` — CACHE. Hỏi lại danh mục trong vòng lặp thành viên là N+1."""
        if self._tram_cache is None:
            self._tram_cache = ban_do_tram(self.db)
        return self._tram_cache

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
            # Ruột sách KHÔNG ghép chung tờ được — xem `_validate_them`. Lọc ở Python chứ không
            # nhét vào SQL của repo: `trang_moi_tay` nằm trong JSON, truy vấn JSON phải rẽ nhánh
            # SQLite/Postgres, mà hàng chờ vốn đã lọc `giay_id`/`q` ngay tại đây rồi.
            if la_gap_tay(qc):
                continue
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
                # Gửi kèm TẬP MỰC: người ghép chọn ứng viên ngay ở bảng này, mà "4/1" của hai
                # lệnh có thể là hai bộ mực khác nhau (CMYK/K với CMYK/185C) — chung tờ là chung
                # bản, nên nhìn con số mà gật là ghép một bài không in chung được.
                "so_mau_a": qc.get("so_mau_a"), "so_mau_b": qc.get("so_mau_b"),
                "muc_a": tap_muc(qc.get("muc_a")), "muc_b": tap_muc(qc.get("muc_b")),
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
            # §5(b): KHÔNG bắt phải có bước IN — bài chỉ gộp CTP/cán vẫn hợp lệ (mô hình gộp đa
            # công đoạn). Chỉ chặn lệnh KHÔNG có công đoạn nào (không ghép được gì với ai).
            if not l.cong_doans:
                raise BaiGhepValidationError(f"LSX {l.ma} chưa có công đoạn nào để ghép")
            # Ruột sách: một cuốn 10 tay = 10 TỜ IN KHÁC NHAU, mỗi tay một bộ kẽm. Mô hình bài ghép
            # giả định mỗi thành viên góp ĐÚNG MỘT bố cục tờ (`so_con_tren_to`), nên không diễn tả
            # nổi — cho vào là ra số vô nghĩa chứ không phải số xấp xỉ. BÌA sách vẫn ghép bình
            # thường vì bìa là hàng cắt rời. Chặn ở đây chứ không chỉ ở hàng chờ: hàng chờ là bộ
            # lọc HIỂN THỊ, API vẫn gọi thẳng được.
            if la_gap_tay(l.quy_cach_json):
                tay = so_tay_moi_cuon(
                    trang_moi_tay=(l.quy_cach_json or {}).get("trang_moi_tay"),
                    so_trang=(l.quy_cach_json or {}).get("so_trang"),
                )
                raise BaiGhepValidationError(
                    f"LSX {l.ma} là sách gấp tay ({tay} tay/cuốn) — mỗi tay là một tờ in riêng nên "
                    f"không ghép chung tờ được. Bìa sách thì ghép bình thường."
                )
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
                # KHÔNG neo sẵn bước in: bài mở ra là routing đầy đủ của từng lệnh, chưa gộp gì.
                # Bước nào chạy chung do NGƯỜI khai (`bai_ghep_cong_doan`) — máy đoán hộ thì vừa
                # sai (còn CTP/cán/bế chung) vừa cướp mất quyết định của người lập kế hoạch.
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
                # KHÔNG neo sẵn bước in: bài mở ra là routing đầy đủ của từng lệnh, chưa gộp gì.
                # Bước nào chạy chung do NGƯỜI khai (`bai_ghep_cong_doan`) — máy đoán hộ thì vừa
                # sai (còn CTP/cán/bế chung) vừa cướp mất quyết định của người lập kế hoạch.
            ))
        self.db.flush()
        # Thêm lệnh → `so_to_tot` (max nhu cầu) và tổng con trên tờ đổi → số của bước chung đổi.
        self._tinh_lai(bg)
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
        # Lệnh rời bài thì lớp ĐÈ của nó phải đi theo. Không dọn thì map thành mồ côi: lệnh đã ra
        # khỏi bài vẫn bị chặn sửa routing ("tách bước khỏi bài trước") mà UI không còn đường nào
        # để tách, lại vẫn bị bỏ hao ở bước in nên mua thiếu giấy.
        self._go_lop_de(bg, lsx_id_bo)
        # Gỡ khỏi bài → thông số in trả về bài tính giá gốc (bố cục in riêng), không giữ số của bài.
        self._tinh_lai(bg, [lsx_id_bo])
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="bo_thanh_vien",
            target=f"bai_ghep:{bg.id}", detail=f"Bỏ 1 LSX khỏi {bg.ma}",
        )
        self.repo.commit()
        return self._get(bg.id)

    def sua_thanh_vien(self, *, bai_ghep_id: int, thanh_vien_id: int, so_con_tren_to: int,
                       actor) -> BaiGhep:
        """Sửa `con/tờ` của một lệnh trong bài.

        `con/tờ` CHỈ GHI NHẬN — người bình bài bằng phần mềm khác rồi vào đây khai lại. Nhưng nó
        là khoá của mọi phép chia sau điểm toả (sản lượng, giấy), nên vẫn phải tính lại lệnh ngay.
        """
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        tv = next((t for t in bg.thanh_viens if t.id == thanh_vien_id), None)
        if tv is None:
            raise BaiGhepNotFound("Không tìm thấy thành viên")
        if int(so_con_tren_to) < 0:
            raise BaiGhepValidationError("Số con/tờ không hợp lệ")
        tv.so_con_tren_to = int(so_con_tren_to)
        # `con/tờ` đổi → tổng con trên tờ đổi → RA của bước gộp `to → cai` đổi theo. Phải tính lại
        # CẢ hai tầng, không riêng tầng lệnh.
        self._tinh_lai(bg, [tv.lsx_id])
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
        # Khổ tờ in đổi → số mảnh xả của thành viên đổi theo. Hao khai tay đổi → số tờ cấp đổi.
        if {"kho_in_dai", "kho_in_rong", "hao_hut_setup", "hao_hut_chay"} & set(patch):
            self._tinh_lai(bg)
        self.repo.commit()
        return self._get(bg.id)

    def _go_lop_de(self, bg: BaiGhep, lsx_id: int) -> None:
        """Gỡ mọi lớp đè liên quan tới một lệnh vừa rời bài. KHÔNG commit.

        Bước chung còn dưới 2 lệnh thì không còn là "chạy chung" nữa — xoá luôn cả dòng, đừng để
        lại một lượt chung một mình. Xoá dòng thì map của nó theo cascade.
        """
        chungs = self._buoc_chungs(bg)
        if not chungs:
            return
        maps = list(self.db.execute(
            select(BaiGhepCongDoanMap).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_([c.id for c in chungs])
            )
        ).scalars())
        con_lai: dict[int, int] = {c.id: 0 for c in chungs}
        for m in maps:
            if m.lsx_id == lsx_id:
                self.db.delete(m)
            else:
                con_lai[m.bai_ghep_cong_doan_id] += 1
        for c in chungs:
            if con_lai[c.id] < 2:
                self.db.delete(c)
        self.db.flush()
        self._sap_lai_thu_tu(bg)

    def _tinh_lai(self, bg: BaiGhep, lsx_ids: list[int] | None = None) -> None:
        """Tính lại CẢ HAI tầng: số của bước chung, rồi chuỗi ngược của từng lệnh. KHÔNG commit.

        Phải theo thứ tự này: chuỗi lệnh bỏ hao ở bước bị đè, nên số của bài phải chốt trước.
        """
        self._ap_so_luong_chung(bg)
        self._tinh_lai_lenh(bg, lsx_ids)

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

    # ================= BƯỚC CHUNG (lớp ghi đè do NGƯỜI khai) =================

    def _buoc_chungs(self, bg: BaiGhep) -> list[BaiGhepCongDoan]:
        """Các bước chạy chung của bài, theo thứ tự khai."""
        return list(self.db.execute(
            select(BaiGhepCongDoan)
            .where(BaiGhepCongDoan.bai_ghep_id == bg.id)
            .order_by(BaiGhepCongDoan.thu_tu, BaiGhepCongDoan.id)
        ).scalars())

    def _gop_theo_lsx(self, bg: BaiGhep) -> dict[int, set[str]]:
        """`lsx_id → các step_key của lệnh đang bị bước chung ĐÈ`.

        KHÔNG suy từ `buoc_in_step_key` nữa: cột đó giả định bước in là điểm gộp duy nhất, mà
        thực tế còn CTP/cán/bế chung. Không khai thì không gộp — máy không tự đúc node in chung.
        """
        ket: dict[int, set[str]] = {}
        for m in self.db.execute(
            select(BaiGhepCongDoanMap)
            .join(BaiGhepCongDoan, BaiGhepCongDoan.id == BaiGhepCongDoanMap.bai_ghep_cong_doan_id)
            .where(BaiGhepCongDoan.bai_ghep_id == bg.id)
        ).scalars():
            ket.setdefault(m.lsx_id, set()).add(m.lsx_step_key)
        return ket

    def _toa_tai(self, lsx: Lsx | None, bo_hao: set[str]) -> str | None:
        """Bước gộp CUỐI CÙNG của lệnh = điểm TOẢ; sau nó lệnh chạy chuỗi riêng.

        Gộp thêm cán/bế thì điểm toả tự dịch sang phải. Chưa gộp gì → `None`, lệnh chạy riêng từ
        đầu tới cuối và bài chưa chia sẻ tờ nào với nó.
        """
        if lsx is None or not bo_hao:
            return None
        return next(
            (cd.step_key for cd in sorted(lsx.cong_doans, key=lambda c: c.thu_tu, reverse=True)
             if cd.step_key in bo_hao),
            None,
        )

    # ================= GỘP / TÁCH (cửa ghi duy nhất của lớp đè) =================

    def _do_thi_cua(self, bg: BaiGhep) -> tuple[list[GBuoc], list[GCanh]]:
        """Nạp bước + cạnh trong tầm ngắm để kiểm vòng.

        Tầm ngắm ĐÓNG BAO THEO CẠNH, không bó trong bài và cũng không dừng ở một bậc `order_id`:
        bắt đầu từ các lệnh trong bài, cứ thấy cạnh trỏ ra một bước lạ thì kéo cả lệnh chứa bước
        đó vào, lặp tới khi không kéo thêm được ai. Sách = bìa + ruột nối nhau ở "vào bìa" thường
        cùng một đơn, nhưng chuỗi có thể dài hơn thế (bìa của đơn này chờ ruột của đơn kia khi
        khách gộp đơn) — lọc theo `order_id` một bậc là cắt mất đúng cạnh đó, mà cắt cạnh thì kiểm
        vòng báo "gộp được" rồi xưởng mới phát hiện kẹt.
        """
        trong_bai = {tv.lsx_id for tv in bg.thanh_viens}
        if not trong_bai:
            return [], []

        da_nap: set[int] = set()
        can_nap = set(trong_bai)
        rows: list = []
        while can_nap:
            them = self.db.execute(
                select(LsxCongDoan, Lsx.ma, Lsx.id)
                .join(Lsx, Lsx.id == LsxCongDoan.lsx_id)
                .where(Lsx.id.in_(can_nap))
            ).all()
            rows.extend(them)
            da_nap |= can_nap
            ids = {cd.id for cd, _, _ in rows}
            # Cạnh chạm tập hiện có nhưng đầu kia còn lạ → kéo nốt lệnh chứa đầu kia vào.
            lan = set(self.db.execute(
                select(LsxCongDoan.lsx_id).where(LsxCongDoan.id.in_(
                    select(LsxCongDoanPhuThuoc.buoc_truoc_id).where(
                        LsxCongDoanPhuThuoc.buoc_sau_id.in_(ids)
                    ).union(
                        select(LsxCongDoanPhuThuoc.buoc_sau_id).where(
                            LsxCongDoanPhuThuoc.buoc_truoc_id.in_(ids)
                        )
                    )
                ))
            ).scalars())
            can_nap = lan - da_nap

        buocs = [
            GBuoc(key=cd.step_key, lsx_id=lsx_id, lsx_ma=ma, ten=cd.ten,
                  cong_doan_id=cd.cong_doan_id, trong_bai=lsx_id in trong_bai)
            for cd, ma, lsx_id in rows
        ]
        theo_id = {cd.id: cd.step_key for cd, _, _ in rows}
        canhs = [
            GCanh(truoc=theo_id[e.buoc_truoc_id], sau=theo_id[e.buoc_sau_id])
            for e in self.db.execute(
                select(LsxCongDoanPhuThuoc).where(
                    LsxCongDoanPhuThuoc.buoc_truoc_id.in_(theo_id),
                    LsxCongDoanPhuThuoc.buoc_sau_id.in_(theo_id),
                )
            ).scalars()
        ]

        # CHUỖI NGẦM theo `thu_tu` của từng lệnh. `lsx_cong_doan_phu_thuoc` chỉ lưu cạnh NGƯỜI
        # nối tay (thường là cạnh CHÉO lệnh); chuỗi trong một lệnh là ngầm — đúng chuỗi mà
        # `_ap_chuoi_nguoc` đi và đúng thứ tự sơ đồ vẽ.
        #
        # Bỏ nó thì routing chưa nối dây cho ra đồ thị RỜI RẠC: Kahn trả thứ tự tuỳ ý,
        # `_sap_lai_thu_tu` đánh số sai chiều, rồi `_node_chungs` chạy ngược chia hao theo đúng
        # thứ tự sai đó — sai số lặng lẽ, không ai báo. Thêm cạnh ngầm cũng làm `kiem_gop` chặt
        # hơn đúng chỗ cần: gộp chéo (A2+B3 trong khi B2+A3 đã gộp) nay lộ ra là vòng thật.
        co_san = {(c.truoc, c.sau) for c in canhs}
        theo_lsx: dict[int, list] = {}
        for cd, _, lsx_id in rows:
            theo_lsx.setdefault(lsx_id, []).append(cd)
        for cds in theo_lsx.values():
            cds.sort(key=lambda c: (c.thu_tu or 0, c.id))
            for truoc, sau in zip(cds, cds[1:]):
                canh = (truoc.step_key, sau.step_key)
                if canh not in co_san:
                    co_san.add(canh)
                    canhs.append(GCanh(truoc=canh[0], sau=canh[1]))
        return buocs, canhs

    def _nhom_hien_co(self, bg: BaiGhep) -> list[list[str]]:
        """Các nhóm đã gộp, dạng đồ thị co ăn được."""
        theo_chung: dict[int, list[str]] = {}
        for m in self.db.execute(
            select(BaiGhepCongDoanMap)
            .join(BaiGhepCongDoan, BaiGhepCongDoan.id == BaiGhepCongDoanMap.bai_ghep_cong_doan_id)
            .where(BaiGhepCongDoan.bai_ghep_id == bg.id)
        ).scalars():
            theo_chung.setdefault(m.bai_ghep_cong_doan_id, []).append(m.lsx_step_key)
        return list(theo_chung.values())

    def ung_vien_gop(self, bg: BaiGhep, dang_chon: list[str]) -> dict[str, dict]:
        """Với tập đang chọn, bước nào gộp thêm vào được — canvas dùng để quyết thẻ nào sáng.

        Kiểm TRƯỚC nên nút Gộp không bao giờ bấm rồi mới bị từ chối; thẻ tắt thì rê chuột hiện
        đúng lý do của cặp mâu thuẫn.
        """
        buocs, canhs = self._do_thi_cua(bg)
        ket = _ung_vien_gop(buocs, canhs, self._nhom_hien_co(bg), dang_chon)
        return {
            k: {"gop_duoc": v is None, "ly_do": v.thong_diep if v else None}
            for k, v in ket.items()
        }

    def gop(self, *, bai_ghep_id: int, step_keys: list[str], actor) -> BaiGhep:
        """Gộp N bước CÙNG CÔNG ĐOẠN ở N lệnh thành một lượt chạy chung.

        Sinh MỘT dòng `bai_ghep_cong_doan` + N dòng map. Bước gốc của mỗi lệnh còn nguyên: đây là
        lớp ĐÈ, tách ra là số cũ tự quay lại.
        """
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        keys = list(dict.fromkeys(k for k in step_keys if k))
        if len(keys) < 2:
            raise BaiGhepValidationError("Chọn ít nhất 2 bước để gộp")

        lsx_map = self._lsx_map(bg)
        theo_key = {cd.step_key: (cd, l) for l in lsx_map.values() for cd in l.cong_doans}
        thieu = [k for k in keys if k not in theo_key]
        if thieu:
            raise BaiGhepValidationError("Có bước không thuộc lệnh nào trong bài")

        cds = [theo_key[k][0] for k in keys]
        if len({cd.cong_doan_id for cd in cds}) != 1 or cds[0].cong_doan_id is None:
            raise BaiGhepValidationError("Chỉ gộp được các bước CÙNG một công đoạn")
        lsx_ids = [theo_key[k][1].id for k in keys]
        if len(set(lsx_ids)) != len(lsx_ids):
            raise BaiGhepValidationError("Mỗi lệnh chỉ góp một bước vào một lượt chạy chung")
        da_gop = set(self._de_len(self._buoc_chungs(bg)))
        if trung := [k for k in keys if k in da_gop]:
            raise BaiGhepValidationError(
                f"Bước \"{theo_key[trung[0]][0].ten}\" đã nằm trong một lượt chung khác"
            )

        buocs, canhs = self._do_thi_cua(bg)
        if vong := kiem_gop(buocs, canhs, [*self._nhom_hien_co(bg), keys]):
            raise BaiGhepVongPhuThuoc(vong)

        mau = cds[0]
        chung = BaiGhepCongDoan(
            bai_ghep_id=bg.id,
            cong_doan_id=mau.cong_doan_id, ten=mau.ten, nhom=mau.nhom,
            loai_buoc=mau.loai_buoc, bat_buoc=bool(mau.bat_buoc),
            # CHƯA gán tổ/máy: gộp xong là phải lập lại kế hoạch cho lượt chạy chung, không thừa
            # kế mù của bất kỳ lệnh nào — hai lệnh có thể đang khai hai máy khác nhau.
            so_nhan_cong_tieu_chuan=int(mau.so_nhan_cong_tieu_chuan or 1),
            so_nhan_cong=int(mau.so_nhan_cong_tieu_chuan or 1),
            so_nhan_cong_toi_da=mau.so_nhan_cong_toi_da,
            so_nhan_cong_toi_thieu=mau.so_nhan_cong_toi_thieu,
            don_vi_nang_suat=mau.don_vi_nang_suat,
            # Đơn vị vào/ra là thứ NGƯỜI khai ở danh mục công đoạn, không phải thứ bài tự đặt.
            # Đóng đinh `tờ ➔ tờ` là nói sai ngay khi bước gộp là bế (`to → cai`): thẻ chung ghi
            # "5.075 tờ ➔ 5.075 tờ" trong khi thẻ liền kề ghi "vào 20.300 cái".
            don_vi_vao=mau.don_vi_vao, don_vi_ra=mau.don_vi_ra,
            # CHỜ KỸ THUẬT (mục B) — lấy mức LỚN NHẤT của các bước gộp, không lấy của bước mẫu.
            # Chạy chung một lượt thì cả bài phải chờ theo lệnh khô lâu nhất: lấy bước mẫu là ăn
            # may đúng, mà sai thì xếp cán chồng lên lúc mực của lệnh kia chưa khô — hỏng hàng thật
            # chứ không phải lệch lịch. Máy vẫn KHÔNG bị chiếm trong khoảng này.
            thu_tu=int(mau.thu_tu or 0),
        )
        self.db.add(chung)
        self.db.flush()
        for k in keys:
            self.db.add(BaiGhepCongDoanMap(
                bai_ghep_cong_doan_id=chung.id, lsx_id=theo_key[k][1].id, lsx_step_key=k,
            ))
        self.db.flush()
        self._sap_lai_thu_tu(bg)
        self._tinh_lai(bg)               # hao bước bị đè chuyển tầng → ghi lại số của bài lẫn lệnh
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="gop_buoc_bai_ghep",
            target=f"bai_ghep:{bg.id}",
            detail=f'Gộp {len(keys)} bước "{mau.ten}" của {bg.ma}',
        )
        self.repo.commit()
        return self._get(bg.id)

    def tach(self, *, bai_ghep_id: int, gang_step_key: str, actor) -> BaiGhep:
        """Tách lượt chung → mỗi lệnh lấy lại bước và số của chính nó.

        Không phải "khôi phục": bước gốc chưa bao giờ bị sửa, chỉ bị đè. Bỏ lớp đè là xong.
        """
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        chung = next((c for c in self._buoc_chungs(bg) if c.step_key == gang_step_key), None)
        if chung is None:
            raise BaiGhepNotFound("Không tìm thấy bước chung")
        ten = chung.ten
        self.db.delete(chung)            # cascade gỡ map + vật tư
        self.db.flush()
        self._sap_lai_thu_tu(bg)
        self._tinh_lai(bg)
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="tach_buoc_bai_ghep",
            target=f"bai_ghep:{bg.id}", detail=f'Tách bước chung "{ten}" khỏi {bg.ma}',
        )
        self.repo.commit()
        return self._get(bg.id)

    # Trường NGƯỜI nhập cho lượt chạy chung. Số lượng/hao/thời lượng KHÔNG có ở đây: chúng là
    # dẫn xuất, engine tính lúc đọc — cho sửa là đẻ nguồn sự thật thứ hai.
    _SUA_DUOC_BUOC_CHUNG = (
        # `khoan_json` KHÔNG có ở đây: nó là ảnh chụp server tự chụp từ `piece_rate_id`
        # (xem `_ghim_khoan_chung`), không phải thứ client gửi thẳng.
        # Thời lượng KẾ THỪA từ máy (2026-08-04): client chỉ còn gửi `phat_sinh_phut`.
        # `setup_phut`/`chay_phut`/`di_chuyen_phut`/`ve_sinh_phut` đã rời bộ này.
        "department_id", "may_id", "so_nhan_cong", "loai_buoc",
        "nang_suat", "don_vi_nang_suat", "phat_sinh_phut",
        # Chờ kỹ thuật: gộp lấy mức lớn nhất làm MẶC ĐỊNH, người lập kế hoạch sửa đè được (mục B).
        "so_luot_chay", "ghi_chu",
        "nha_cung_cap", "sl_gui", "ngay_gui_dk", "van_chuyen_ngay", "gia_cong_ngay",
        "ngay_nhan_dk", "hao_hut_cho_phep", "don_gia_gia_cong", "yeu_cau_ky_thuat",
    )

    def lap_ke_hoach_buoc_chung(
        self, *, bai_ghep_id: int, gang_step_key: str, patch: dict, actor,
    ) -> BaiGhep:
        """Lập kế hoạch cho lượt chạy chung: một tổ, một máy, một kíp, một bộ vật tư."""
        bg = self._get(bai_ghep_id)
        self._chan_da_lap(bg)
        chung = next((c for c in self._buoc_chungs(bg) if c.step_key == gang_step_key), None)
        if chung is None:
            raise BaiGhepNotFound("Không tìm thấy bước chung")
        for field in self._SUA_DUOC_BUOC_CHUNG:
            if field in patch:
                setattr(chung, field, patch[field])
        # Sau vòng trên: tổ có thể vừa đổi trong cùng lượt lưu, mà đầu việc khoán lọc THEO TỔ.
        if "piece_rate_id" in patch:
            self._ghim_khoan_chung(chung, patch["piece_rate_id"], giu_kip="so_nhan_cong" in patch)
        if "vat_tus" in patch:
            self._thay_vat_tu_chung(chung, patch["vat_tus"] or [])
        self.db.flush()
        # Đổi `loai_buoc` là đổi cách suy thời lượng; ghi lại số để `thoi_luong_buoc` đọc đúng.
        self._ap_so_luong_chung(bg)
        self._mark_nhap(bg)
        self.audit.create(
            actor_user_id=getattr(actor, "id", None), action="ke_hoach_buoc_chung",
            target=f"bai_ghep:{bg.id}", detail=f'Lập kế hoạch bước chung "{chung.ten}" của {bg.ma}',
        )
        self.repo.commit()
        return self._get(bg.id)

    def _ghim_khoan_chung(
        self, chung: BaiGhepCongDoan, rate_id: int | None, *, giu_kip: bool,
    ) -> None:
        """Ghim đầu việc khoán cho lượt chạy chung — mượn NGUYÊN luật của bước lệnh.

        Khoán của một lượt chạy chung không có gì khác khoán của một bước lệnh: vẫn là "tổ này
        làm đầu việc nào, đơn giá bao nhiêu". Nên chỗ này gọi thẳng `LsxService` chứ không chép
        lại phép lọc theo tổ + kiểm đầu việc thuộc công đoạn + gắp định mức.

        Kéo theo định mức (năng suất · số người) y như bước lệnh: chọn đầu việc xong mà năng suất
        vẫn trống thì thẻ vẫn kêu "Chưa có năng suất", người dùng phải gõ lại số đã có sẵn.
        """
        from .lsx_service import _dinh_muc_snapshot

        svc = self._lsx_svc()
        cd_obj = self.db.get(CongDoan, chung.cong_doan_id) if chung.cong_doan_id else None
        rid = int(rate_id or 0)
        rate = next((x for x in svc._piece_rates() if x.id == rid), None) if rid else None
        if rid and rate is None:
            raise BaiGhepValidationError("Không tìm thấy đầu việc khoán")
        if rate is not None:
            allowed = {x.id for x in svc._dau_viec_cua_cong_doan(cd_obj, chung.department_id)}
            if rate.id not in allowed:
                raise BaiGhepValidationError("Đầu việc không thuộc công đoạn hoặc tổ phụ trách")
        chung.khoan_json = khoan_snapshot(rate) if rate is not None else None
        if rate is None:
            return
        dm = next((x for x in (getattr(cd_obj, "dau_viec_dinh_muc", None) or [])
                   if x.piece_rate_id == rate.id), None)
        if dm is None:
            return
        # Bước chung của bài cũng là "một bước có kế hoạch" → ghim NGUYÊN bộ định mức như bước
        # lệnh, gồm cả dải năng suất min/max và đơn vị khai báo.
        chung.khoan_json.update(_dinh_muc_snapshot(dm))
        chung.nang_suat = _f(dm.nang_suat_nguoi_gio)
        # Đơn vị năng suất = đơn vị ĐƠN GIÁ KHOÁN. Bảng ánh xạ `_DV_VAO_SANG_NS` đã gỡ 15/08/2026
        # cùng hai cơ chế đơn vị cũ — thời lượng nay quy SL vào về chính đơn vị này.
        chung.don_vi_nang_suat = rate.unit
        chung.so_nhan_cong_tieu_chuan = int(dm.so_nguoi_tieu_chuan)
        chung.so_nhan_cong_toi_da = int(dm.so_nguoi_toi_da)
        chung.so_nhan_cong_toi_thieu = int(getattr(dm, "so_nguoi_toi_thieu", 1) or 1)
        if not giu_kip:                       # người dùng vừa gõ tay kíp thì đừng đè lên
            chung.so_nhan_cong = int(dm.so_nguoi_tieu_chuan)

    def _khoan_chung_dict(self, c: BaiGhepCongDoan) -> dict:
        """Khối khoán của thẻ bước chung: phần ghim + danh sách chọn được + tiền DỰ KIẾN.

        Tiền tính bằng đúng `_khoan_derived` của bước lệnh. Quy cách truyền `{}` là CÓ Ý: tờ ghép
        không thuộc quy cách của lệnh nào cả, nên cầu quy đổi nào cần quy cách sẽ báo thiếu qua
        `khoan_thieu` thay vì lặng lẽ mượn số của một thành viên bất kỳ.
        """
        svc = self._lsx_svc()
        cd_obj = self.db.get(CongDoan, c.cong_doan_id) if c.cong_doan_id else None
        kh = c.khoan_json or {}
        return {
            "khoan_rate_id": kh.get("rate_id"),
            "khoan_ten": kh.get("ten"),
            "khoan_don_vi": kh.get("don_vi"),
            "khoan_don_gia": _f(kh.get("don_gia")) or None,
            "khoan_chon_duoc": svc._dau_viec_option_dicts(cd_obj, c.department_id),
            **svc._khoan_derived(c, {}),
        }

    def _thay_vat_tu_chung(self, chung: BaiGhepCongDoan, vat_tus: list[dict]) -> None:
        """Thay toàn bộ vật tư của bước chung. Snapshot mã/tên/đơn vị để đổi danh mục không làm
        đổi kế hoạch đã chốt — cùng luật với `lsx_cong_doan_vat_tu`."""
        ids = [int(v.get("vat_tu_id") or 0) for v in vat_tus]
        if len(ids) != len(set(ids)):
            raise BaiGhepValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
        mats = {
            v.id: v for v in self.db.execute(
                select(VatTuInAn).where(VatTuInAn.id.in_(ids))
            ).scalars()
        } if ids else {}
        # Vật tư đã nằm trên bài ghép từ trước thì giữ lại được, kể cả khi danh mục đã ngừng nó —
        # chặn cả hai kiểu thì bài ghép cũ không lưu lại được dù chỉ sửa một con số khác.
        dang_co = {int(v.vat_tu_id) for v in chung.vat_tus if v.vat_tu_id}
        chung.vat_tus[:] = []
        for i, v in enumerate(vat_tus):
            mat = mats.get(int(v.get("vat_tu_id") or 0))
            if mat is None:
                raise BaiGhepValidationError("Vật tư không tồn tại")
            if not mat.active and mat.id not in dang_co:
                raise BaiGhepValidationError(
                    f"Vật tư “{mat.ten}” đã ngừng dùng — chọn vật tư khác")
            chung.vat_tus.append(BaiGhepCongDoanVatTu(
                # `don_vi_gia`, KHÔNG phải `don_vi` — `VatTuInAn` không có cột nào tên `don_vi`.
                # Gõ nhầm ở đây là AttributeError lúc chạy, 500 ngay khi bấm Lưu; bước lệnh
                # (`lsx_service`) vẫn luôn dùng đúng `don_vi_gia`.
                # `or ""`: đơn vị gốc của vật tư có thể CHƯA KHAI (cột nullable từ 2026-08-08), mà
                # cột snapshot này NOT NULL — không chặn thì IntegrityError 500 lúc bấm Lưu.
                vat_tu_id=mat.id, vat_tu_ma_snapshot=mat.ma, vat_tu_ten_snapshot=mat.ten,
                don_vi_snapshot=mat.don_vi_gia or "", so_luong=_f(v.get("so_luong")), thu_tu=i,
            ))

    def _sap_lai_thu_tu(self, bg: BaiGhep) -> None:
        """Đánh lại `thu_tu` các bước chung theo THỨ TỰ TOPO của đồ thị đã co.

        Chuỗi chung chạy ngược để chia hao (`_node_chungs`) nên thứ tự phải đúng chiều phụ thuộc,
        không phải thứ tự người bấm gộp.
        """
        chungs = self._buoc_chungs(bg)
        if not chungs:
            return
        thanh_vien: dict[int, list[str]] = {}
        for m in self.db.execute(
            select(BaiGhepCongDoanMap).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_([c.id for c in chungs])
            )
        ).scalars():
            thanh_vien.setdefault(m.bai_ghep_cong_doan_id, []).append(m.lsx_step_key)
        buocs, canhs = self._do_thi_cua(bg)
        kq = co_do_thi(buocs, canhs, list(thanh_vien.values()))
        if not kq.thu_tu:
            return                       # có vòng (không nên xảy ra) — giữ nguyên, đừng đoán
        vi_tri = {k: i for i, k in enumerate(kq.thu_tu)}
        for c in chungs:
            keys = thanh_vien.get(c.id) or []
            rep = kq.dai_dien.get(keys[0]) if keys else None
            c.thu_tu = vi_tri.get(rep, c.thu_tu or 0)

    # ================= ENGINE (thuần) =================

    def _bu_hao_rows(self) -> list[dict]:
        if self._bu_hao_cache is None:
            # KHÔNG lọc `active`: bài ghép tính lại số tờ của bản ĐÃ CÓ. Ẩn một mã bù hao mà lọc
            # ở đây thì bài ghép cũ tự đổi số, không ai đụng vào mà vẫn lệch.
            self._bu_hao_cache = [
                _bu_hao_to_dict(b) for b in self.db.execute(select(BuHao)).scalars()
            ]
        return self._bu_hao_cache

    def _quy_tac_hao(self, cong_doan_id: int | None) -> dict:
        """Quy tắc bù hao của DANH MỤC công đoạn — `hao_buoc` chỉ cần 3 khoá này."""
        dm = self.db.get(CongDoan, cong_doan_id) if cong_doan_id else None
        return {} if dm is None else {
            "kieu_bu_hao": dm.kieu_bu_hao, "bu_hao_id": dm.bu_hao_id,
            "so_to_bu_hao": dm.so_to_bu_hao,
        }

    def _hao_o_bac(self, cong_doan_id: int | None, sl: float) -> tuple[float, float]:
        """`(cố định, %)` của một công đoạn, tra ở bậc `sl` — ĐÚNG đơn vị của bước.

        `sl` là số của BÀI, không phải của từng lệnh: trước đây mỗi lệnh tra bằng số tờ riêng nên
        đều rơi bậc thấp nhất rồi cộng dồn thành nhiều bộ hao cho CÙNG một lần lên máy.
        """
        qt = self._quy_tac_hao(cong_doan_id)
        if not qt:
            return 0.0, 0.0
        fixed, pct = hao_buoc(qt, rows=self._bu_hao_rows(), sl=float(sl))
        return fixed, min(max(pct, 0.0), 99.0)

    @staticmethod
    def _cai_moi_to(lsx: Lsx | None, so_con: int) -> float:
        """Cầu `tờ → cái` của MỘT lệnh. Gọi thẳng luật dùng chung — xem `cau_to_sang_cai`.

        Bản đầu tôi CHÉP luật sang đây, rồi lệch ngay: chép thiếu nhánh gấp tay, sau đó chép thừa
        chỗ đọc `so_to_per_sp`. Ba tầng (tính giá · lệnh · bài ghép) phải gọi cùng một hàm.
        """
        qc = (getattr(lsx, "quy_cach_json", None) or {}) if lsx else {}
        return cau_to_sang_cai(
            trang_moi_tay=qc.get("trang_moi_tay"), so_trang=qc.get("so_trang"), con=so_con,
        )

    def _cau_quy_doi(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        """Bảng CẦU quy đổi của BÀI — cùng hình dạng `he_so_dv` của engine tính giá.

        Hai cầu, HAI NGUỒN KHÁC NHAU (đừng gộp):
        - `to → cai`: **tổng `cai_moi_to` của mọi thành viên** trên tờ ghép. Cắt rời góp `con_i`,
          gấp tay góp `1/so_tay_i` — không phải cứ cộng số con. Đây cũng là khoá chia sản lượng
          và giấy về từng lệnh.
        - `to_nguyen → to`: số mảnh xả, tính theo khổ tờ in của BÀI (`_he_so_cau` lo phần đó).

        Hệ số thuộc về PHIẾU/BÀI, KHÔNG thuộc danh mục công đoạn — danh mục chỉ khai đơn vị vào/ra.
        Khai hệ số ở danh mục là đẻ nguồn sự thật thứ hai (đúng luật engine tính giá đang theo).
        """
        tong = sum(
            self._cai_moi_to(lsx_map.get(tv.lsx_id), int(tv.so_con_tren_to or 0))
            for tv in bg.thanh_viens
        )
        xa = 0.0
        for tv in bg.thanh_viens:
            l = lsx_map.get(tv.lsx_id)
            if l is not None:
                xa = _f(self._lsx_svc()._he_so_cau(
                    l, so_con=int(tv.so_con_tren_to or 0) or None
                ).get((TRAM_TO_NGUYEN, TRAM_TO)))
                break
        to_cai = tong if tong > 0 else 1.0
        # Khoá theo TRẠM (giống `LsxService._he_so_cau`) — nơi tra phải dịch mã qua `tram_cua`.
        return {
            (TRAM_TO, TRAM_CAI): to_cai,
            (TRAM_TO_NGUYEN, TRAM_TO): max(xa, 1.0),
            # Đường DÀI của sách (gấp → bắt tay + vào keo). Gấp không sinh không mất tờ nên cầu
            # đầu là 1, cầu sau lấy lại nguyên cầu tắt — tích hai cầu luôn bằng `to → cai`.
            (TRAM_TO, TRAM_TAY): 1.0,
            (TRAM_TAY, TRAM_CAI): to_cai,
        }

    def _nhu_cau_to(self, lsx: Lsx | None, so_con: int, bo_hao: set[str] | None = None) -> int:
        """Số TỜ IN mà lệnh này thật sự cần khi xếp `so_con` con/tờ.

        Lấy từ chuỗi ngược của lệnh nên ĐÃ GỒM hao của mọi bước riêng (gấp, bắt tay, vào keo,
        xén). Công thức cũ `ceil(SL đặt / con)` lấy số thành phẩm giao khách — thiếu đúng phần
        hao đó, nên bài ghép cấp không đủ giấy mà không ai báo.

        `bo_hao` = các bước đã gộp: hao của chúng đã chuyển tầng lên bài (đếm một lần cho cả
        lượt), để lại đây nữa là mỗi lệnh cộng thêm một bộ hao cho cùng lần lên máy đó.

        Không tính được (lệnh chưa có routing dòng giấy) → rơi về `ceil(SL đặt / con)`, tức đúng
        bằng hành vi cũ, chứ không trả 0 làm bài tưởng không cần tờ nào.
        """
        can = int(getattr(lsx, "so_luong_dat", 0) or 0) if lsx else 0
        if lsx is None or so_con <= 0 or can <= 0:
            return 0
        rows = {r["idx"]: r for r in self._lsx_svc().tinh_nguoc_routing(
            lsx, so_con=so_con, bo_hao_step_keys=set(bo_hao) if bo_hao else None,
        )}
        buoc = sorted(lsx.cong_doans, key=lambda c: c.thu_tu)
        # Bước đếm TỜ IN = bước có đơn vị đứng ở TRẠM `to`, không phải bước có mã bằng "to":
        # `don_vi_vao` là mã do xưởng đặt (`to_chay`…), so mã là trượt hết rồi rơi về `can/so_con`
        # — số tờ của bài lệch trong im lặng ngay khi xưởng đổi tên đơn vị.
        bd = self._tram()
        vao_to = next(
            (r["so_luong_vao"] for i, cd in enumerate(buoc)
             if tram_cua(cd.don_vi_vao, bd) == TRAM_TO and (r := rows.get(i))),
            None,
        )
        return ceil(_f(vao_to)) if vao_to else ceil(can / so_con)

    def _con_toi_da(self, l: Lsx | None, bg: BaiGhep) -> int:
        """Ước lượng con/tờ TỐI ĐA theo hình học: khổ tờ in của bài ÷ khổ thành phẩm (xét xoay 90°).
        THÔ — chưa trừ nhíp/chừa xén/khe, chỉ làm GỢI Ý trần cho người bình bài, KHÔNG ép."""
        qc = (l.quy_cach_json or {}) if l else {}
        dai_tp, rong_tp = _f(qc.get("dai_thanh_pham")), _f(qc.get("rong_thanh_pham"))
        kd, kr = _f(bg.kho_in_dai), _f(bg.kho_in_rong)
        if min(dai_tp, rong_tp, kd, kr) <= 0:
            return 0
        thang = int(kd // dai_tp) * int(kr // rong_tp)
        xoay = int(kd // rong_tp) * int(kr // dai_tp)
        return max(thang, xoay)

    def tinh_so_to(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        gop = self._gop_theo_lsx(bg)
        chungs = self._buoc_chungs(bg)
        rows: list[dict] = []
        so_to_tot = 0
        for tv in bg.thanh_viens:
            l = lsx_map.get(tv.lsx_id)
            can = int(getattr(l, "so_luong_dat", 0) or 0) if l else 0
            con = int(tv.so_con_tren_to or 0)
            bo_hao = gop.get(tv.lsx_id, set())
            per = self._nhu_cau_to(l, con, bo_hao)
            if con > 0:
                so_to_tot = max(so_to_tot, per)
            rows.append({"thanh_vien_id": tv.id, "lsx_id": tv.lsx_id, "can": can, "con": con,
                         "nhu_cau_to": per, "co_gop": bool(bo_hao),
                         "con_toi_da": self._con_toi_da(l, bg),
                         "toa_step_key": self._toa_tai(l, bo_hao), "_lsx": l})
        # D3: gợi ý CÂN sản lượng — chọn con/tờ để các lệnh về đích GẦN CÙNG số tờ, giảm dư. `S` =
        # số tờ chung nhỏ nhất khả thi khi mỗi lệnh xếp tối đa con/tờ; con gợi ý = ceil(can/S), trần
        # là con tối đa. Chỉ là GỢI Ý (con/tờ vẫn do người bình bài quyết), KHÔNG tự ghi.
        kha_thi = [ceil(r["can"] / r["con_toi_da"]) for r in rows if r["con_toi_da"] and r["can"]]
        s_muc_tieu = max(kha_thi) if kha_thi else 0
        for r in rows:
            cap = r["con_toi_da"]
            r["con_goi_y"] = (
                min(ceil(r["can"] / s_muc_tieu), cap)
                if s_muc_tieu > 0 and r["can"] > 0 and cap > 0 else 0
            )
        # LƯỢT ĐI: bài chạy `so_to_tot` tờ chung, từ ĐIỂM TOẢ mỗi lệnh chạy xuôi chuỗi riêng để
        # biết sản lượng THẬT. Trước đây chỗ này là `so_to_tot × con` — bỏ qua sạch hao sau in nên
        # số dư báo lên gấp cả chục lần (vd 8.603 trong khi thật là 683).
        svc = self._lsx_svc()
        for r in rows:
            l, con, toa = r.pop("_lsx"), r["con"], r["toa_step_key"]
            if not r["co_gop"]:
                # Chưa gộp bước nào thì lệnh không dùng chung tờ với bài — nó chạy đúng nhu cầu
                # riêng, không dôi ra gì. Báo dư lúc này là báo một con số chưa có nghĩa.
                r["san_luong_du_kien"] = r["can"]
                r["du"] = r["du_to"] = 0
                continue
            if l is None or con <= 0 or not toa:
                r["san_luong_du_kien"] = so_to_tot * con if con > 0 else 0
            else:
                xuoi = svc.tinh_xuoi_tu_to(l, tu_step_key=toa, so_to=so_to_tot, so_con=con)
                r["san_luong_du_kien"] = int(xuoi[-1]["so_luong_ra"]) if xuoi else so_to_tot * con
            r["du"] = r["san_luong_du_kien"] - r["can"]
            # Dư TỜ ngay tại điểm toả — đại lượng có nghĩa ở nút thắt, khác hẳn dư con ở cuối chuỗi.
            r["du_to"] = so_to_tot - r["nhu_cau_to"] if con > 0 else 0
        # Hao của MỖI bước chung: một lần lên máy, một lần canh. Tách đôi setup/chạy vì hai thứ
        # áp khác nhau — gộp làm một số thì người khai không sửa lại được phần nào cho đúng.
        # Bậc tra theo `ra` của CHÍNH bước đó (đúng đơn vị của nó), không tra mọi bước bằng số tờ:
        # bước bế đếm CON thì bậc của nó là số con, giống hệt engine tính giá.
        cau = self._cau_quy_doi(bg, lsx_map)
        hang, _cb = self._chuoi_chung(bg, chungs, so_to_tot, cau)
        hao_setup = hao_chay = 0.0
        hao_theo_buoc: list[dict] = []   # T4: breakdown hao đề xuất per bước (In 150 + Cán 50…)
        for c in chungs:
            h = hang.get(c.id)
            if h is None:
                continue
            fixed, pct = self._hao_o_bac(c.cong_doan_id, h["ra"])
            chay_i = max(_f(h["hao"]) - fixed, 0.0)
            hao_setup += fixed
            hao_chay += chay_i
            hao_theo_buoc.append({"ten": c.ten, "hao": int(round(fixed + chay_i))})
        hao_de_xuat = hao_setup + hao_chay
        # NULL = chưa ai khai → lấy số máy đề xuất. Khai rồi (kể cả khai 0) → tôn trọng đúng số
        # người gõ: "chạy đúng số, không bù" là một quyết định hợp lệ, trước đây `or hao_de_xuat`
        # nuốt mất vì 0 rơi vào nhánh falsy.
        da_khai = bg.hao_hut_setup is not None or bg.hao_hut_chay is not None
        hao_ap_dung = (
            int(bg.hao_hut_setup or 0) + int(bg.hao_hut_chay or 0) if da_khai else int(hao_de_xuat)
        )
        # `tong_to` và `to_nguyen_can` cùng nghĩa "tờ phải cấp", chỉ khác đơn vị (tờ in ↔ tờ
        # nguyên) — nên phải cùng một cơ sở hao. Trước đây `tong_to` chỉ cộng hao khai tay còn
        # `to_nguyen_can` cộng `hao_ap_dung`: bài chưa khai hao thì hai số nói hai chuyện.
        tong_to = so_to_tot + hao_ap_dung

        # Tờ IN là sản phẩm của lượt in; tờ NGUYÊN mới là thứ đi lĩnh kho. Hai số khác nhau đúng
        # bằng phần hao canh máy — gộp làm một là lĩnh thiếu giấy mà không ai báo.
        #
        # Quy đổi phải đi qua ĐÚNG cầu `to_nguyen → to` (số mảnh xả từ tờ giấy nguyên), là cầu
        # NGƯỜI khai ở danh mục công đoạn. Trước đây chỗ này lấy hệ số của BƯỚC TOẢ — mà bước toả
        # thường là bế (`to → cai`), hệ số của nó là con/tờ. Lấy nhầm cầu thì 5.075 tờ với 4 con/tờ
        # ra 1.269 tờ nguyên: ai cầm số đó đi lĩnh giấy là thiếu 3/4.
        #
        # Hao đếm ở TỜ IN (bậc bù hao tra theo đơn vị của bước in), nên phải cộng vào TRƯỚC rồi
        # mới chia mảnh xả. Cộng sau phép chia là tính hao bằng tờ nguyên: tờ nguyên xả 4 mảnh
        # thì 100 tờ hao bị đòi thành 100 tờ nguyên = 400 mảnh, thừa gấp 4.
        to_nguyen_can = tong_to
        for r in rows:
            l = lsx_map.get(r["lsx_id"])
            if l is None:
                continue
            xa = _f(self._lsx_svc()._he_so_cau(
                l, so_con=r["con"] or None).get((TRAM_TO_NGUYEN, TRAM_TO)))
            if xa > 0:
                to_nguyen_can = ceil(tong_to / xa)
            break

        # PHẦN GIẤY của từng lệnh — chia theo CON, cùng khoá với phép chia sản lượng ở điểm toả.
        # Tờ giấy là dùng chung nên không có "tờ của lệnh nào"; cái chia được là CHI PHÍ giấy, và
        # chia theo diện tích chiếm trên tờ = tỉ lệ `cai_moi_to`. Không có số này thì kế toán phải
        # tự bổ đôi bằng tay, mà bổ đôi là sai ngay khi hai lệnh khác số con.
        tong_cmt = sum(
            self._cai_moi_to(lsx_map.get(r["lsx_id"]), r["con"]) for r in rows
        ) or 1.0
        for r in rows:
            phan = self._cai_moi_to(lsx_map.get(r["lsx_id"]), r["con"]) / tong_cmt
            r["ty_le_giay"] = round(phan * 100, 1)
            r["phan_giay_to"] = int(round(to_nguyen_can * phan))

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
            "hao_de_xuat": int(hao_de_xuat),
            "hao_setup_de_xuat": int(hao_setup),
            "hao_chay_de_xuat": int(hao_chay),
            # T1: hao THẬT đang áp (đã tôn trọng khai tay / khai 0) + tỷ lệ hao/tốt để cảnh báo
            # makeready nuốt sản lượng (vd 230/20 = 1150%). Dẫn xuất, không cột.
            "hao_ap_dung": int(hao_ap_dung),
            "ty_le_hao": round((tong_to - so_to_tot) / so_to_tot * 100, 1) if so_to_tot else 0.0,
            # T4: breakdown hao đề xuất per bước — để tooltip "Giấy lĩnh kho" nối được tổng với thẻ.
            "hao_theo_buoc": hao_theo_buoc,
            "to_nguyen_can": int(to_nguyen_can),
            "so_buoc_chung": len(chungs),
            "fill_pct": fill_pct,
            "han_in_muon_nhat": min(hans) if hans else None,
            "rows": rows,
        }

    # ================= SƠ ĐỒ (dẫn xuất, không lưu cạnh) =================

    def so_do(self, bg: BaiGhep) -> dict:
        """Đồ thị của bài: routing ĐẦY ĐỦ của từng lệnh + các bước NGƯỜI đã khai là chạy chung.

        DẪN XUẤT hoàn toàn, dựng lúc đọc từ: thành viên bài + routing từng lệnh + lớp đè
        `bai_ghep_cong_doan`. KHÔNG thêm cạnh xuyên đơn vào `lsx_cong_doan_phu_thuoc` — hình
        tụ-rồi-toả rơi ra từ phép co nút, khai thêm cạnh là mở cửa cho khai bừa.

        Chưa gộp gì thì trả đúng N routing rời — KHÔNG tự đúc node "in chung tờ". Ghép bài chung
        cả CTP/cán/bế chứ không riêng bước in, nên chọn bước nào là việc của người.
        """
        lsx_map = self._lsx_map(bg)
        so_to = self.tinh_so_to(bg, lsx_map)
        du_by_tv = {r["thanh_vien_id"]: r for r in so_to["rows"]}
        cust = self._customer_names({l.order_id for l in lsx_map.values()})
        svc = self._lsx_svc()
        chungs = self._buoc_chungs(bg)
        de_len = self._de_len(chungs)                 # lsx_step_key → BaiGhepCongDoan

        dept_names = svc._dept_names(
            {cd.department_id for l in lsx_map.values() for cd in l.cong_doans if cd.department_id}
            | {c.department_id for c in chungs if c.department_id}
        )
        may_names = svc._may_names(
            {cd.may_id for l in lsx_map.values() for cd in l.cong_doans if cd.may_id}
            | {c.may_id for c in chungs if c.may_id} | {bg.may_id}
        )
        # Chuỗi của lượt chung — dùng cho CẢ thẻ chung lẫn các thẻ bị đè bên nhánh, để hai chỗ
        # không tự tính riêng rồi lệch nhau.
        cau_bai = self._cau_quy_doi(bg, lsx_map)
        hang_chung, _cb_dv = self._chuoi_chung(bg, chungs, so_to["so_to_tot"], cau_bai)

        trong_so_do: set[str] = set()
        nhanh: list[dict] = []

        for mau, tv in enumerate(bg.thanh_viens):
            l = lsx_map.get(tv.lsx_id)
            if l is None:
                continue
            buoc = sorted(l.cong_doans, key=lambda c: c.thu_tu)
            trong_so_do.update(cd.step_key for cd in buoc)
            r = du_by_tv.get(tv.id, {})
            con = int(tv.so_con_tren_to or 0)
            toa = r.get("toa_step_key")
            bo_hao = {k for k in de_len if any(cd.step_key == k for cd in buoc)}

            # Bước SAU điểm toả: số THẬT của lượt đi (bài chạy `so_to_tot` tờ chung rồi mới toả).
            # Bước TRƯỚC đó mà không gộp: số của chính lệnh, lấy từ lượt về đã bỏ hao ở bước gộp.
            xuoi = {
                x["step_key"]: x for x in svc.tinh_xuoi_tu_to(
                    l, tu_step_key=toa, so_to=so_to["so_to_tot"], so_con=con or None,
                )
            } if toa else {}
            nguoc_rows = svc.tinh_nguoc_routing(
                l, so_con=con or None, bo_hao_step_keys=bo_hao or None,
            )
            nguoc = {buoc[x["idx"]].step_key: x for x in nguoc_rows if x["idx"] < len(buoc)}

            # Bước BỊ ĐÈ: lấy số của LƯỢT CHUNG, KHÔNG lấy nhu cầu riêng của lệnh. Lệnh nhỏ trong
            # bài cần 4.000 tờ nhưng bài chạy 5.075 tờ thì nó THẬT SỰ nhận 5.075 — để nguyên số
            # 4.000 trên thẻ là thẻ đá nhau với chính chip "dư tờ 1.075" ngay bên cạnh.
            # Tờ thì dùng chung nguyên vẹn; qua cầu `to → cai` mới nhân `cai_moi_to` của lệnh này.
            hs_lenh = self._cai_moi_to(l, con)
            de = {}
            for cd in buoc:
                g = de_len.get(cd.step_key)
                h = hang_chung.get(g.id) if g else None
                if h is None:
                    continue
                doi = h["dv_vao"] != h["dv_ra"]
                de[cd.step_key] = {
                    "so_luong_vao": h["vao"],
                    "so_luong_ra": h["ra_quy"] * hs_lenh if doi else h["ra"],
                    "hao_hut": h["hao"],
                }

            nhanh.append({
                "thanh_vien_id": tv.id, "lsx_id": l.id, "lsx_ma": l.ma, "lsx_ten": l.ten,
                "customer_name": cust.get(l.order_id),
                "han_hoan_thanh_sx": l.han_hoan_thanh_sx,
                "is_rush": bool(l.is_rush),
                "mau": mau,
                "so_con_tren_to": tv.so_con_tren_to,
                "toa_step_key": toa,
                "nhu_cau_to": r.get("nhu_cau_to", 0), "du_to": r.get("du_to", 0),
                "du": r.get("du", 0),
                "san_luong_du_kien": r.get("san_luong_du_kien", 0),
                # Phần giấy gánh theo con — tờ thì dùng chung, chia được là chi phí.
                "phan_giay_to": r.get("phan_giay_to", 0), "ty_le_giay": r.get("ty_le_giay", 0),
                "buoc": [
                    self._node(
                        cd, dept_names, may_names,
                        # Thứ tự ưu tiên: bị đè → số của lượt chung; sau toả → lượt đi; còn lại →
                        # lượt về của chính lệnh.
                        sl=de.get(cd.step_key) or xuoi.get(cd.step_key) or nguoc.get(cd.step_key),
                        gop_step_key=(g.step_key if (g := de_len.get(cd.step_key)) else None),
                    )
                    for cd in buoc
                ],
            })

        # Tiền nhiệm NGOÀI sơ đồ (vd ruột sách của cùng đơn, không nằm trong bài) → node bóng mờ.
        can_ngoai = {
            k for n in nhanh for cd in n["buoc"]
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
                "hao_de_xuat": so_to["hao_de_xuat"],
                "hao_setup_de_xuat": so_to["hao_setup_de_xuat"],
                "hao_chay_de_xuat": so_to["hao_chay_de_xuat"],
                "to_nguyen_can": so_to["to_nguyen_can"],
                "so_buoc_chung": so_to["so_buoc_chung"],
                "fill_pct": so_to["fill_pct"],
            },
            "nhanh": nhanh,
            "gop": self._node_chungs(bg, chungs, lsx_map, so_to["so_to_tot"], dept_names, may_names),
            "ngoai": ngoai,
        }

    def _de_len(self, chungs: list[BaiGhepCongDoan]) -> dict[str, BaiGhepCongDoan]:
        """`lsx_step_key → bước chung đang đè lên nó`."""
        if not chungs:
            return {}
        rows = self.db.execute(
            select(BaiGhepCongDoanMap).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_([c.id for c in chungs])
            )
        ).scalars()
        theo_id = {c.id: c for c in chungs}
        return {m.lsx_step_key: theo_id[m.bai_ghep_cong_doan_id] for m in rows}

    def _chuoi_chung(
        self, bg: BaiGhep, chungs: list[BaiGhepCongDoan], so_to_tot: int, cau: dict,
    ) -> tuple[dict[int, dict], list[str]]:
        """`bước chung → {vao, ra, hao, dv_vao, dv_ra}` + cảnh báo, chạy NGƯỢC từ điểm toả.

        Dùng THẲNG `bu_hao_engine.chuoi_nguoc_dv` — đúng hàm engine tính giá đang chạy. Trước đây
        chỗ này tự cuộn vòng lặp và `if` cứng đúng một cặp đơn vị `to → cai`; tự cuộn thì (a) cặp
        đơn vị nào chưa nghĩ tới là âm thầm chạy hệ số 1, (b) bậc bù hao tra theo số TỜ cho mọi
        bước, trong khi bước đếm CON phải tra theo số con — đúng cái `chuoi_nguoc_dv` sinh ra để
        chữa. Hàm chung còn kêu khi chuỗi ĐỨT ĐƠN VỊ hoặc thiếu hệ số, thay vì lặng lẽ lấy 1.

        Một nguồn duy nhất cho cả thẻ sơ đồ, cửa ghi số, và màn lệnh — ba chỗ tự tính riêng là ba
        con số lệch nhau.
        """
        if not chungs:
            return {}, []
        # Bước KHÔNG chạm dòng giấy (ghi kẽm…) — loại khỏi chuỗi hao bằng CỜ TRẠM của đơn vị, và
        # bước CHƯA khai đơn vị thì lùi về luật cũ theo `nhom` (danh mục chưa backfill thì bước IN
        # cũng NULL, loại nhầm là hao về 0). Giữ lại thì lối lùi coerce nó về đơn vị tờ in, thành nút
        # `to→to` giả đá vào `to_nguyen` của bước in → cảnh báo "đứt đơn vị" GIẢ và số tờ vô nghĩa.
        tram = self._tram()
        tren_giay = [c for c in chungs
                     if tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram, nhom=c.nhom)]
        if not tren_giay:
            return {}, []
        # Đơn vị hiệu dụng: bước chưa backfill đơn vị (danh mục NULL) nối tiếp bằng đơn vị chặng TỜ
        # IN CỦA CHÍNH BÀI NÀY — đọc từ routing chứ KHÔNG đóng đinh mã `to`. Xưởng khai `to_chay`
        # mà ở đây coerce về `to` là đẻ nút `to→to` giả, đá vào chặng tờ in thật của bước in.
        # Kèm TRẠM: bảng cầu `cau` khoá theo trạm, tra bằng mã là xưởng khai mã riêng cho một chặng
        # thì không khớp — ăn hệ số 1 và số tờ của cả bài sai (xem `bu_hao_engine.chuoi_nguoc_dv`).
        dv_to_bai = don_vi_chuoi(tren_giay, tram)["to"]
        dvs = [(c, c.don_vi_vao or dv_to_bai, c.don_vi_ra or dv_to_bai) for c in tren_giay]
        buoc = [
            {"cd": self._quy_tac_hao(c.cong_doan_id), "ten": c.ten, "dv_vao": dv_v, "dv_ra": dv_r,
             "tram_vao": tram_cua(dv_v, tram) or dv_v, "tram_ra": tram_cua(dv_r, tram) or dv_r}
            for (c, dv_v, dv_r) in dvs
        ]
        # Đích của chuỗi chung: điểm toả phải nhận đủ `so_to_tot` TỜ. Bước chung cuối nhả đơn vị
        # gì thì quy đích về đơn vị đó trước — giống `to_can` của engine tính giá.
        tram_cuoi = buoc[-1]["tram_ra"]
        to_can = float(so_to_tot) * (
            1.0 if tram_cuoi == TRAM_TO else _f(cau.get((TRAM_TO, tram_cuoi))) or 1.0)
        hang, canh_bao = chuoi_nguoc_dv(
            buoc, rows=self._bu_hao_rows(), to_can=to_can, he_so=cau,
        )
        # Bồi thêm `he_so` + `ra_quy` và làm tròn Y HỆT `bu_hao_chi_tiet` của tính giá. Thiếu hai
        # số đó thì dòng đổi đơn vị đọc lên vô lý ("20.500 tờ → 2.050 cuốn" mà không nói 10 tờ =
        # 1 cuốn), và hao phải là `ceil(vào) − ceil(ra_quy)` chứ không phải hiệu số thô — nếu
        # không, hai màn cùng một phép tính lại lệch nhau một đơn vị ở đúng chỗ người dùng soi kỹ.
        ket: dict[int, dict] = {}
        for (c, dv_v, dv_r), h in zip(dvs, hang):
            tv, tr = h.get("tram_vao") or dv_v, h.get("tram_ra") or dv_r
            hs = 1.0 if tv == tr else (_f(cau.get((tv, tr))) or 1.0)
            vao, ra_quy = ceil(h["vao"]), ceil(h["ra"] / hs)
            ket[c.id] = {
                **h, "vao": float(vao), "ra": float(ceil(h["ra"])),
                "he_so": hs, "ra_quy": float(ra_quy), "hao": float(vao - ra_quy),
                "canh_bao": [],
            }
        # Cảnh báo đơn vị gắn ĐÚNG bước liên quan (không dán chung lên mọi thẻ): ranh giới đứt
        # giữa hai bước liền kề → gắn cho cả hai; đổi đơn vị mà thiếu hệ số → gắn cho chính bước đó.
        for (a, _av, a_r), (b, b_v, _br) in zip(dvs, dvs[1:]):
            if a_r != b_v:
                ket[a.id]["canh_bao"].append(
                    f"Ra {a_r} không khớp bước sau '{b.ten}' (vào {b_v})"
                )
                ket[b.id]["canh_bao"].append(
                    f"Vào {b_v} không khớp bước trước '{a.ten}' (ra {a_r})"
                )
        for (c, dv_v, dv_r) in dvs:
            if dv_v != dv_r and _f(cau.get((dv_v, dv_r))) <= 0:
                ket[c.id]["canh_bao"].append(
                    f"Đổi {dv_v}→{dv_r} nhưng chưa có hệ số quy đổi (tạm tính 1)"
                )
        return ket, canh_bao

    def _ap_so_luong_chung(self, bg: BaiGhep) -> None:
        """GHI số dẫn xuất của các bước chung xuống DB. KHÔNG commit (caller commit).

        Số là DẪN XUẤT nhưng vẫn phải ghi, đúng như `lsx_cong_doan` (xem `_ap_chuoi_nguoc`):
        `thoi_luong_buoc()` đọc thẳng `so_luong_vao` để suy giờ chạy, và `lsx_service` đọc mấy cột
        này để dựng khối bài ghép cho màn lệnh. Không ghi thì hai chỗ đó đọc ra 0 — thẻ báo thời
        lượng 0 phút và drawer lệnh báo "bài cấp 0 tờ".

        Gọi ở MỌI cửa làm số đổi: gộp · tách · thêm/bỏ thành viên · sửa con/tờ · sửa khổ tờ in.
        """
        chungs = self._buoc_chungs(bg)
        if not chungs:
            return
        lsx_map = self._lsx_map(bg)
        so_to_tot = int(self.tinh_so_to(bg, lsx_map)["so_to_tot"])
        cau = self._cau_quy_doi(bg, lsx_map)
        hang, _cb = self._chuoi_chung(bg, chungs, so_to_tot, cau)
        for c in chungs:
            h = hang.get(c.id)
            if h is None:
                continue
            # Bậc bù hao tra theo `ra` — ĐÚNG đơn vị của bước, giống `chuoi_nguoc_dv` vừa chạy.
            _fixed, pct = self._hao_o_bac(c.cong_doan_id, h["ra"])
            c.so_luong_vao = h["vao"]
            c.so_luong_ra = h["ra"]
            c.he_so_quy_doi = h["he_so"]
            c.hao_hut = h["hao"]
            c.hao_hut_pct = pct

    def _node_chungs(
        self, bg: BaiGhep, chungs: list[BaiGhepCongDoan], lsx_map: dict[int, Lsx],
        so_to_tot: int, dept_names: dict, may_names: dict,
    ) -> list[dict]:
        """Thẻ của các bước chạy chung, kèm số của CẢ LƯỢT và danh sách lệnh bị đè.

        Số ở đây tính bằng TỜ ghép — một lượt chạy thì đếm tờ, không đếm con. Con là chuyện của
        điểm toả: qua đó mới nhân `con/tờ` của từng lệnh, và đó cũng là khoá chia giấy.
        """
        if not chungs:
            return []
        thanh_vien: dict[int, list[dict]] = {}
        for m in self.db.execute(
            select(BaiGhepCongDoanMap).where(
                BaiGhepCongDoanMap.bai_ghep_cong_doan_id.in_([c.id for c in chungs])
            )
        ).scalars():
            l = lsx_map.get(m.lsx_id)
            thanh_vien.setdefault(m.bai_ghep_cong_doan_id, []).append({
                "lsx_id": m.lsx_id, "lsx_ma": l.ma if l else None,
                "lsx_step_key": m.lsx_step_key,
                "ghi_chu_ky_thuat": next(
                    (cd.ghi_chu for cd in (l.cong_doans if l else []) if cd.step_key == m.lsx_step_key),
                    None,
                ),
            })

        cau = self._cau_quy_doi(bg, lsx_map)
        hang, _canh_bao_dv = self._chuoi_chung(bg, chungs, so_to_tot, cau)  # cảnh báo nay gắn per-thẻ
        qc_bai = self._qc_bai(bg, lsx_map)   # T3: quy cách tờ ghép để kiểm khả năng máy

        from .lsx_service import thoi_luong_buoc

        # Nhãn đơn vị cho bước CHƯA khai đơn vị: lấy chặng tờ in của chính bài, không đóng đinh `to`.
        dv_to_bai = don_vi_chuoi(chungs, self._tram())["to"]
        out: list[dict] = []
        for c in chungs:
            hh = hang.get(c.id)
            # `tren_giay=False` = bước chế bản (prepress) đã bị loại khỏi chuỗi giấy: KHÔNG có số
            # tờ vào/ra (thẻ hiện "chung bản" thay vì "0 tờ"), và KHÔNG có cảnh báo đơn vị giả.
            tren_giay = hh is not None
            h = hh or {"vao": 0.0, "ra": 0.0, "hao": 0.0, "he_so": 1.0, "ra_quy": None,
                       "canh_bao": []}
            _fixed, pct = self._hao_o_bac(c.cong_doan_id, h["ra"]) if tren_giay else (0.0, 0.0)
            may_obj = self.db.get(MayThietBi, c.may_id) if c.may_id else None
            cd_obj = self.db.get(CongDoan, c.cong_doan_id) if c.cong_doan_id else None
            # Quy cách `{}` như khối khoán (`_khoan_chung_dict`): tờ ghép không thuộc quy cách của
            # lệnh nào, nên công thức nào cần biến quy cách sẽ báo tịt thay vì mượn số của một
            # thành viên bất kỳ.
            t = thoi_luong_buoc(c, may_obj, self._lsx_svc().sl_tinh_cua_buoc(c, may_obj, {}))
            ds = sorted(thanh_vien.get(c.id, []), key=lambda x: x["lsx_ma"] or "")
            out.append({
                "step_key": c.step_key, "ten": c.ten, "nhom": c.nhom,
                "cong_doan_id": c.cong_doan_id,
                "loai_buoc": c.loai_buoc, "thu_tu": c.thu_tu,
                # Bước chế bản chạy chung = CHUNG BẢN (1 bộ kẽm), không đếm tờ trên dòng giấy.
                "tren_giay": tren_giay,
                "so_luong_vao": h["vao"], "so_luong_ra": h["ra"],
                # Đơn vị lấy từ KHAI BÁO của công đoạn, không đóng đinh.
                "don_vi_vao": c.don_vi_vao or dv_to_bai, "don_vi_ra": c.don_vi_ra or dv_to_bai,
                # `ra` quy về đơn vị VÀO + hệ số đã dùng — cùng bộ số `bu_hao_chi_tiet` của tính
                # giá trả ra, để thẻ nói được "10 tờ = 1 cuốn" thay vì để người xem tự đoán.
                "he_so_quy_doi": h.get("he_so", 1.0), "so_luong_ra_quy": h.get("ra_quy"),
                # Hao đếm ở ĐƠN VỊ VÀO — thứ mất trên máy là tờ, không phải con.
                "hao_hut": h["hao"], "hao_hut_pct": pct,
                # Cảnh báo đơn vị gắn ĐÚNG bước này (per-thẻ), không dán chung lên mọi thẻ.
                "canh_bao_don_vi": h.get("canh_bao", []),
                # Trả cả ID lẫn TÊN: ô <select> cần id để chọn đúng, nhãn cần tên. Trước đây chỉ
                # có tên nên form phải lấy tên làm `value` — so chuỗi với id số, tổ đã gán vẫn
                # hiện "— chọn tổ —".
                "department_id": c.department_id, "to_ten": dept_names.get(c.department_id),
                "may_id": c.may_id, "may_ten": may_names.get(c.may_id),
                # T3: cảnh báo MỀM máy không hợp công đoạn (sai loại / vượt khổ-màu-gsm) + danh sách
                # nhóm máy cho phép để FE lọc dropdown ("Bế" chỉ hiện máy Bế).
                "may_khong_hop": self._may_hop_cong_doan(may_obj, cd_obj, qc_bai),
                "nhom_may_cho_phep": (cd_obj.nhom_may_cho_phep or []) if cd_obj is not None else [],
                "nha_cung_cap": c.nha_cung_cap,
                "tong_phut": t["tong_phut"], "chiem_may_phut": t["chiem_may_phut"],
                "chiem_may_phut_min": t["chiem_may_phut_min"],
                "chiem_may_phut_max": t["chiem_may_phut_max"],
                # Giá trị NGƯỜI đã khai — form phải mồi lại được, không thì mỗi lần mở drawer là
                # ô trống và lưu đè mất số cũ.
                "so_nhan_cong": c.so_nhan_cong,
                "nang_suat": _f(c.nang_suat) or None, "don_vi_nang_suat": c.don_vi_nang_suat,
                # Chuẩn bị + chạy là SỐ DẪN XUẤT từ máy, không phải cột cũ (đã dormant).
                "chay_phut": t["chay_phut"],
                "setup_phut": t["dien_giai"]["setup_phut"],
                "phat_sinh_phut": _f(c.phat_sinh_phut),
                # Chờ kỹ thuật của lượt chung — trả từ CỘT (thứ người gõ đè được), không qua `t`.
                "so_luot_chay": c.so_luot_chay,
                **self._khoan_chung_dict(c),
                "vat_tus": [
                    {"vat_tu_id": v.vat_tu_id, "ma": v.vat_tu_ma_snapshot,
                     "ten": v.vat_tu_ten_snapshot, "don_vi": v.don_vi_snapshot,
                     "so_luong": _f(v.so_luong)}
                    for v in c.vat_tus
                ],
                # Gia công ngoài (dự kiến) — bước chung thuê ngoài thì cả bài đi MỘT phiếu.
                "sl_gui": _f(c.sl_gui) or None, "ngay_gui_dk": c.ngay_gui_dk,
                "van_chuyen_ngay": _f(c.van_chuyen_ngay) or None,
                "gia_cong_ngay": _f(c.gia_cong_ngay) or None,
                "ngay_nhan_dk": c.ngay_nhan_dk,
                "hao_hut_cho_phep": _f(c.hao_hut_cho_phep) or None,
                "don_gia_gia_cong": _f(c.don_gia_gia_cong) or None,
                "yeu_cau_ky_thuat": c.yeu_cau_ky_thuat,
                "ghi_chu": c.ghi_chu,
                "thanh_vien": ds,
                "ma_bai_ghep": bg.ma,
                "thieu": self._thieu_buoc_chung(c),
                # Cờ THẬT cho câu hỏi "tách ra có mất kế hoạch không". FE từng suy bằng cách dò
                # chuỗi `thieu.includes("Chưa chọn tổ")` — đổi câu chữ bên này là bên kia lặng lẽ
                # tách không hỏi, và ai đã khai máy + năng suất nhưng chưa chọn tổ thì mất trắng.
                "da_lap_ke_hoach": bool(
                    c.department_id or c.may_id or _f(c.phat_sinh_phut)
                    or _f(c.nang_suat) or (c.ghi_chu or "").strip()
                    or (c.nha_cung_cap or "").strip() or c.vat_tus or c.khoan_json
                ),
            })
        return out

    def _qc_bai(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        """Quy cách TỔNG HỢP của tờ ghép để kiểm khả năng máy: khổ tờ in của BÀI + số màu/định
        lượng LỚN NHẤT trong các thành viên (máy phải kham được cái nặng nhất trên tờ)."""
        so_mau_a = so_mau_b = gsm = 0.0
        muc_a: set[str] = set()
        muc_b: set[str] = set()
        for tv in bg.thanh_viens:
            qc = (lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {}
            so_mau_a = max(so_mau_a, _f(qc.get("so_mau_a")))
            so_mau_b = max(so_mau_b, _f(qc.get("so_mau_b")))
            gsm = max(gsm, _f(qc.get("gsm")))
            muc_a |= {str(m).strip().upper() for m in (qc.get("muc_a") or []) if str(m or "").strip()}
            muc_b |= {str(m).strip().upper() for m in (qc.get("muc_b") or []) if str(m or "").strip()}
        return {
            "kho_in_dai": bg.kho_in_dai, "kho_in_rong": bg.kho_in_rong,
            "so_mau_a": so_mau_a, "so_mau_b": so_mau_b, "gsm": gsm,
            "muc_a": sorted(muc_a), "muc_b": sorted(muc_b),
        }

    def muc_gop(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> dict:
        """Số màu + số kẽm của CẢ BÀI — `{so_mau_a, so_mau_b, so_mau_pha, so_kem}`.

        Bài ghép in MỘT lượt trên MỘT bộ bản, nên bản phải mang HỢP tập mực của mọi thành viên:
        thẻ CMYK ghép với bìa CMYK + Pantone 185C ⇒ form 5 bản, không phải 4. Đây không phải suy
        đoán — `_qc_bai` đã hợp tập mực sẵn cho việc kiểm khả năng máy; hàm này chỉ đếm ra số.

        Đếm bằng ĐÚNG hàm của engine tính giá (`so_mau_dan_xuat` · `so_kem_moi_tay`) chứ không tự
        cộng: luật kẽm khác nhau theo cách in (AB cộng hai mặt, tự trở hợp hai mặt), viết lại ở đây
        là chỗ thứ hai để lệch. Số tay = 1 vì bài ghép LÀ một tay in.

        Thành viên chưa khai mực (dữ liệu trước mig `0154`) → dựng tập từ ba con số cũ, đúng luật
        migration dùng. Không có gì để đếm thì trả rỗng, nơi gọi để 0 chứ không bịa.
        """
        qc = self._qc_bai(bg, lsx_map)
        a, b = tap_muc(qc.get("muc_a")), tap_muc(qc.get("muc_b"))
        if not a and not b:
            a, b = tap_muc_tu_so(qc.get("so_mau_a"), qc.get("so_mau_b"), 0)
        if not a and not b:
            return {}
        kieu = next(
            (k for tv in bg.thanh_viens
             if (k := ((lsx_map.get(tv.lsx_id).quy_cach_json or {}) if lsx_map.get(tv.lsx_id)
                       else {}).get("quy_cach_in"))),
            "mot_mat",
        )
        sa, sb, sp = so_mau_dan_xuat(a, b)
        return {"so_mau_a": sa, "so_mau_b": sb, "so_mau_pha": sp,
                "so_kem": so_kem_moi_tay(a, b, str(kieu))}

    def _may_hop_cong_doan(self, may, cd, qc_bai: dict) -> list[str]:
        """Cảnh báo MỀM khi máy của bước chung không hợp công đoạn — máy chỉ ghi nhận, không chặn.

        Hai kiểu: (a) SAI LOẠI (`may.loai_may` ngoài `cong_doan.nhom_may_cho_phep` — bắt vụ CTP gán
        máy Bế); (b) khổ/số màu/gsm vượt máy (tái dùng `_may_fit.kiem_kha_nang` với quy cách cả tờ
        ghép). Rỗng = hợp / chưa đủ dữ liệu để nghi.
        """
        if may is None:
            return []
        out: list[str] = []
        allowed = (cd.nhom_may_cho_phep or []) if cd is not None else []
        if allowed and may.loai_may not in allowed:
            out.append(f"Máy '{may.ten}' ({may.loai_may}) không làm được công đoạn này")
        out.extend(_LY_DO_MAY_VN.get(ld, ld) for ld in kiem_kha_nang(qc_bai, may))
        return out

    def _thieu_buoc_chung(self, c: BaiGhepCongDoan) -> list[str]:
        """Chip ⚠️ trên thẻ bước chung — cùng cơ chế "thiếu dữ liệu" của thẻ KHSX.

        Bước chung sinh ra ở trạng thái CHƯA gán tổ/máy: gộp xong là phải lập lại kế hoạch cho
        lượt chạy đó, không thừa kế mù của bất kỳ lệnh nào.
        """
        thieu: list[str] = []
        if not c.department_id:
            thieu.append("Chưa chọn tổ")
        if c.loai_buoc == LB_MAY and not c.may_id:
            thieu.append("Chưa chọn máy")
        if c.loai_buoc == "thue_ngoai" and not (c.nha_cung_cap or "").strip():
            thieu.append("Chưa có nhà cung cấp")
        # Bước máy lấy tốc độ SỐNG từ máy đang gán; thiếu thì chip "Chưa chọn máy" ở trên đã nói.
        if c.loai_buoc != LB_MAY and not _f(c.nang_suat):
            thieu.append("Chưa có năng suất")
        return thieu

    def _node(self, cd, dept_names: dict, may_names: dict, sl: dict | None = None,
              gop_step_key: str | None = None) -> dict:
        """Node cho sơ đồ: làm gì · ai làm · vào/ra bao nhiêu · bao lâu · chờ ai · có bị đè không.

        `sl` là hàng số lượng đã chọn đúng nguồn ở caller: sau điểm toả thì là LƯỢT ĐI (số thật
        khi bài chạy `so_to_tot` tờ), trước đó là lượt về của chính lệnh. Hai thứ khác nhau ngay
        khi ghép, nên thẻ phải nói rõ nó đang đứng bên nào của điểm toả.

        `gop_step_key` khác `None` = bước này đang bị một bước chung ĐÈ; số/tổ/máy hiển thị lấy
        theo thẻ chung, thẻ lệnh chỉ còn là mảnh ghép của nó.
        """
        from .bien_cong_thuc import quy_cach_bien
        from .lsx_service import thoi_luong_buoc

        may_obj = self.db.get(MayThietBi, cd.may_id) if cd.may_id else None
        svc = self._lsx_svc()
        # Bước LỆNH có quy cách của lệnh nó thuộc về; thẻ bước CHUNG (`BaiGhepCongDoan`) thì không
        # có `.lsx` nên đi với `{}` — công thức cần biến quy cách sẽ báo tịt, không mượn số bừa.
        qc = quy_cach_bien(cd.lsx) if getattr(cd, "lsx", None) is not None else {}
        t = thoi_luong_buoc(cd, may_obj, svc.sl_tinh_cua_buoc(cd, may_obj, qc))
        sl = sl or {}
        return {
            "so_luong_vao": sl.get("so_luong_vao"), "so_luong_ra": sl.get("so_luong_ra"),
            "don_vi_vao": cd.don_vi_vao, "don_vi_ra": cd.don_vi_ra,
            "hao_hut": sl.get("hao_hut"),
            "step_key": cd.step_key, "ten": cd.ten, "nhom": cd.nhom,
            "cong_doan_id": cd.cong_doan_id,
            "loai_buoc": cd.loai_buoc, "thu_tu": cd.thu_tu,
            "gop_step_key": gop_step_key,
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

        # MỰC: ghép chung tờ là chung một bộ bản, nên phải khớp CHÍNH XÁC TỪNG MỰC, không phải
        # khớp số lượng. Hai lệnh cùng nhãn "4/1" mà một bên mặt sau là K còn bên kia là 185C thì
        # bản kẽm khác nhau — so con số sẽ gật "phù hợp" cho một bài không in chung được.
        # Lệnh cũ chưa có tập mực (`quy_cach_json` trước 2026-08-05) → rơi về nhãn số như trước.
        def _nhan_muc(qc: dict) -> str:
            a, b = tap_muc(qc.get("muc_a")), tap_muc(qc.get("muc_b"))
            if not a and not b:
                return f"{qc.get('so_mau_a') or 0}/{qc.get('so_mau_b') or 0}"
            return f"{'+'.join(a) or '—'} / {'+'.join(b) or '—'}"

        maus = [_nhan_muc(qc) for qc in qcs]
        rows.append(_row("Mực in", maus, "phu_hop" if len(set(maus)) <= 1 else "can_xac_nhan"))

        # Số mặt/trở.
        mats = [qc.get("quy_cach_in") or "—" for qc in qcs]
        rows.append(_row("Số mặt/trở", mats, "phu_hop" if len(set(mats)) <= 1 else "can_xac_nhan"))

        # Khổ thành phẩm — CHỈ hiển thị (khác khổ TP là bình thường, không phán mức).
        khos = [_kho(qc.get("dai_thanh_pham"), qc.get("rong_thanh_pham")) or "—" for qc in qcs]
        rows.append(_row("Khổ thành phẩm", khos, "phu_hop"))

        # KHUÔN BẾ (mục C) — dụng cụ DÙNG CHUNG, chỉ có MỘT cái: hai lệnh khác khuôn ghép chung tờ
        # thì tới bước bế phải tháo lắp khuôn giữa chừng, hoặc chạy hai lượt. Không chặn cứng (đúng
        # lối dòng Giấy/Mực ngay trên), nhưng phải BÀY RA — hôm nay bảng này im lặng về khuôn, người
        # ghép chỉ phát hiện lúc đã tới máy bế.
        # Lệnh KHÔNG có bước cần dụng cụ thì khuôn trống là bình thường ⇒ bỏ hẳn dòng này, không
        # bắt người ta đọc một dòng "—" vô nghĩa cho bài toàn tờ phẳng.
        kb_ids = [(lsx_map[tv.lsx_id].khuon_be_id if tv.lsx_id in lsx_map else None) for tv in tvs]
        if any(kb_ids):
            ten_kb: dict[int, str] = {}
            for k in {i for i in kb_ids if i}:
                kb = self.db.get(KhuonBe, k)
                if kb is not None:
                    ten_kb[k] = f"{kb.ma} · {kb.ten}"
            co_du = all(kb_ids)
            rows.append(_row(
                "Khuôn bế",
                [ten_kb.get(i, "—") if i else "Chưa gán" for i in kb_ids],
                "phu_hop" if (co_du and len(set(kb_ids)) == 1) else "can_xac_nhan",
            ))

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
        # Chưa gộp bước nào thì chưa có gì chạy chung — đó là N lệnh rời, không phải bài ghép.
        chungs = self._buoc_chungs(bg)
        if not chungs:
            thieu.append("thieu_buoc_chung")
        # Gộp rồi thì lượt chạy chung phải được LẬP KẾ HOẠCH lại: một tổ, một máy, một năng suất.
        elif any(self._thieu_buoc_chung(c) for c in chungs):
            thieu.append("thieu_ke_hoach_buoc_chung")
        # Số tờ chạy = MAX nhu cầu các thành viên, nên không thành viên nào có thể thiếu tờ —
        # "thiếu giấy" trước đây là hệ quả của công thức cũ (lấy SL đặt, bỏ hao các bước sau in),
        # sửa công thức là hết, không cần thêm cổng chặn.
        if self.tinh_so_to(bg, lsx_map)["so_to_tot"] <= 0:
            thieu.append("thieu_so_to")
        return thieu

    def canh_bao_cua(self, bg: BaiGhep, lsx_map: dict[int, Lsx] | None = None,
                     so_to: dict | None = None) -> list[str]:
        """Rổ cảnh báo MỀM — chỉ tô màu, KHÔNG chặn. Chỉ còn tín hiệu về TRẠNG THÁI đơn/lệnh.

        `so_to` giữ trong chữ ký cho caller cũ khỏi phải sửa, nhưng KHÔNG còn dùng: cảnh báo duy
        nhất đọc nó là "bài thưa" (fill thấp) và cái đó đã bỏ.
        """
        lsx_map = lsx_map or self._lsx_map(bg)
        cb: list[str] = []
        # KHÔNG còn cảnh báo "khác quy cách" (khác giấy / số màu / số mặt) và "bài thưa".
        # Điều kiện gộp CHỈ là cùng công đoạn — quy cách thì người dùng có nghiệp vụ đó, máy không
        # phán hộ. Bảng `kiem_tuong_thich` vẫn BÀY ĐỦ các giá trị để người tự so, và `fill_pct`
        # vẫn hiện dưới dạng con số; chỉ bỏ phần MÁY KẾT LUẬN hộ.
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
                "hao_de_xuat": so_to["hao_de_xuat"],
                "to_nguyen_can": so_to["to_nguyen_can"],
                "so_buoc_chung": so_to["so_buoc_chung"],
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
                # Điểm TOẢ của lệnh = bước gộp cuối cùng; `None` = lệnh chưa gộp bước nào.
                "toa_step_key": r.get("toa_step_key"),
                # Số tờ lệnh này THẬT SỰ cần (đã gồm hao các bước riêng) — để màn bài giải thích
                # được vì sao số tờ chạy là 5.075 chứ không phải 5.000.
                "nhu_cau_to": r.get("nhu_cau_to", 0), "du_to": r.get("du_to", 0),
                "san_luong_du_kien": r.get("san_luong_du_kien", 0), "du": r.get("du", 0),
                "phan_giay_to": r.get("phan_giay_to", 0), "ty_le_giay": r.get("ty_le_giay", 0),
                # D3: gợi ý con/tờ — tối đa theo khổ (ước lượng) + gợi ý cân sản lượng để giảm dư.
                "con_toi_da": r.get("con_toi_da", 0), "con_goi_y": r.get("con_goi_y", 0),
                "giay_id": qc.get("giay_id"), "giay_ten": qc.get("giay_ten"),
                # Gửi kèm TẬP MỰC: người ghép chọn ứng viên ngay ở bảng này, mà "4/1" của hai
                # lệnh có thể là hai bộ mực khác nhau (CMYK/K với CMYK/185C) — chung tờ là chung
                # bản, nên nhìn con số mà gật là ghép một bài không in chung được.
                "so_mau_a": qc.get("so_mau_a"), "so_mau_b": qc.get("so_mau_b"),
                "muc_a": tap_muc(qc.get("muc_a")), "muc_b": tap_muc(qc.get("muc_b")),
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
