"""Quyền THEO TỔ — ai thấy / làm được gì ở Bàn tổ (bản chốt 14/09/2026, mg 0302).

Spec: `docs/superpowers/specs/2026-09-14-quyen-theo-to-va-tab-san-luong.md`.

MỘT DÒNG QUYỀN CHO MỖI NÚT của khối Sản xuất trong cây Phòng ban (kể cả cấp gom), khoá
`to_sx_<id phòng ban>`. Dòng tự sinh / đổi tên / xoá theo phòng ban (`dong_bo_dong_quyen_to`).
Mỗi dòng có Xem (`can_read`) · Phạm vi (`scope`) · 4 quyền chi tiết (`can_run_order`,
`can_confirm_output`, `can_qc`, `can_warehouse`).

PHẠM VI tính từ VỊ TRÍ NGƯỜI XEM, trong VÙNG của dòng (vùng = nút đó + mọi đơn vị trực thuộc):
  · `own`        — chỉ phần của chính mình (việc mình đang được giao) trong vùng.
  · `department` — phòng mình + các đơn vị trực thuộc của phòng mình, phần nằm trong vùng.
  · `all`        — toàn bộ vùng, dù mình đứng ở nấc nào.
Phạm vi áp cho cả Xem lẫn 4 quyền chi tiết; nhiều dòng chồng nhau thì lấy phần RỘNG nhất.

KHÔNG còn luật cứng "phải đứng tên trưởng tổ" — `head_user_id` chỉ còn là thông tin tổ chức.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from ..repositories.quyen_to_repo import KHOA_TIEN_TO, QuyenToRepository

VIEC_XEM = "read"
VIEC_THUC_HIEN = "run_order"
VIEC_XAC_NHAN = "confirm_output"
VIEC_KCS = "qc"
VIEC_KHO = "warehouse"

#: việc → cột `role_permissions`.
COT_VIEC: dict[str, str] = {
    VIEC_XEM: "can_read",
    VIEC_THUC_HIEN: "can_run_order",
    VIEC_XAC_NHAN: "can_confirm_output",
    VIEC_KCS: "can_qc",
    VIEC_KHO: "can_warehouse",
}
VIEC_CHI_TIET = (VIEC_THUC_HIEN, VIEC_XAC_NHAN, VIEC_KCS, VIEC_KHO)

MUC_TAT_CA = "all"   # thấy / làm trên mọi việc của tổ
MUC_CUA_TOI = "own"  # chỉ việc mình đang được giao

_THONG_BAO_THIEU = {
    VIEC_XEM: "Bạn không có quyền xem tổ này",
    VIEC_THUC_HIEN: "Bạn không có quyền Thực hiện lệnh ở tổ này",
    VIEC_XAC_NHAN: "Bạn không có quyền Xác nhận sản lượng ở tổ này",
    VIEC_KCS: "Bạn không có quyền KCS ở tổ này",
    VIEC_KHO: "Bạn không có quyền Kho ở tổ này",
}


def khoa_to(dept_id: int) -> str:
    return f"{KHOA_TIEN_TO}{dept_id}"


def dept_cua_khoa(key: str) -> int | None:
    if not key.startswith(KHOA_TIEN_TO):
        return None
    duoi = key[len(KHOA_TIEN_TO):]
    return int(duoi) if duoi.isdigit() else None


# --- Cây khối Sản xuất ---------------------------------------------------------------------


@dataclass
class CayKhoi:
    """Ảnh chụp cây khối Sản xuất: nút = phòng tự bật `la_san_xuat` hoặc có tổ tiên bật."""

    ten: dict[int, str]
    cha: dict[int, int | None]
    #: Cha của MỌI phòng ban (cả ngoài khối) — người xem có thể ngồi ở phòng cha ngoài khối.
    cha_day_du: dict[int, int | None]
    con: dict[int, list[int]]
    kcs: set[int]
    goc: list[int]
    _cache: dict[int, frozenset[int]] = field(default_factory=dict)

    def co(self, dept_id: int | None) -> bool:
        return dept_id is not None and dept_id in self.ten

    def vung(self, dept_id: int | None) -> frozenset[int]:
        """Nút + mọi đơn vị trực thuộc (trong khối). Nút ngoài khối → rỗng."""
        if not self.co(dept_id):
            return frozenset()
        if dept_id not in self._cache:
            ket, hang = set(), [dept_id]
            while hang:
                x = hang.pop()
                if x in ket:
                    continue
                ket.add(x)
                hang.extend(self.con.get(x, []))
            self._cache[dept_id] = frozenset(ket)
        return self._cache[dept_id]

    def la_to_tien(self, tren: int | None, duoi: int | None) -> bool:
        """`tren` là chính `duoi` hoặc tổ tiên của nó, dò theo cây phòng ban ĐẦY ĐỦ."""
        if tren is None:
            return False
        cur, seen = duoi, set()
        while cur is not None and cur not in seen:
            if cur == tren:
                return True
            seen.add(cur)
            cur = self.cha_day_du.get(cur)
        return False

    def la(self, dept_id: int) -> bool:
        return not self.con.get(dept_id)

    def thu_tu(self) -> list[tuple[int, int]]:
        """(id, cấp) theo thứ tự duyệt sâu — để ma trận quyền / menu thụt lề theo cây."""
        ket: list[tuple[int, int]] = []

        def di(x: int, cap: int) -> None:
            ket.append((x, cap))
            for c in self.con.get(x, []):
                di(c, cap + 1)

        for g in self.goc:
            di(g, 0)
        return ket


def doc_cay(db: Session) -> CayKhoi:
    rows = QuyenToRepository(db).cay_phong_ban()
    by = {r[0]: r for r in rows}

    def thuoc_khoi(did: int) -> bool:
        cur, seen = by.get(did), set()
        while cur is not None and cur[0] not in seen:
            seen.add(cur[0])
            if cur[3]:
                return True
            cur = by.get(cur[1]) if cur[1] is not None else None
        return False

    khoi = [r for r in rows if thuoc_khoi(r[0])]
    ids = {r[0] for r in khoi}
    con: dict[int, list[int]] = {}
    for r in khoi:
        if r[1] in ids:
            con.setdefault(r[1], []).append(r[0])
    return CayKhoi(
        ten={r[0]: r[2] for r in khoi},
        cha={r[0]: (r[1] if r[1] in ids else None) for r in khoi},
        cha_day_du={r[0]: r[1] for r in rows},
        con=con,
        kcs={r[0] for r in khoi if r[4]},
        goc=[r[0] for r in khoi if r[1] not in ids],
    )


def dong_bo_dong_quyen_to(db: Session) -> None:
    """Dòng quyền theo tổ khớp đúng cây hiện tại: nút mới → thêm dòng, đổi tên → đổi nhãn, nút
    rời khối (xoá / gỡ cờ / chuyển nhánh) → gỡ dòng cùng các ô đã cấp. Idempotent."""
    repo = QuyenToRepository(db)
    cay = doc_cay(db)
    muon = {khoa_to(d): ten for d, ten in cay.ten.items()}
    dang_co = repo.module_to()
    doi = False
    for key, ten in muon.items():
        if key not in dang_co:
            repo.tao_module(key, ten)
            doi = True
        elif dang_co[key] != ten:
            repo.doi_nhan_module(key, ten)
            doi = True
    for key in dang_co.keys() - muon.keys():
        repo.xoa_module(key)
        doi = True
    if doi:
        db.commit()


# --- Quyền hiệu lực của một người ------------------------------------------------------------


class QuyenTo:
    """Quyền hiệu lực của MỘT người trên các tổ: với mỗi việc, tập tổ làm được trọn (`all`) và
    tập tổ chỉ làm được phần của mình (`own`). Cả hai tập đều ĐÓNG theo cây con."""

    def __init__(self, cay: CayKhoi, user: User, dong: list) -> None:
        self.cay = cay
        self.user = user
        self.tron: dict[str, set[int]] = {v: set() for v in COT_VIEC}
        self.rieng: dict[str, set[int]] = {v: set() for v in COT_VIEC}
        #: Nút mở bàn "của tôi" (nút của mình nếu nằm trong vùng, không thì chính nút của dòng).
        self._ban_rieng: set[int] = set()
        for p in dong:
            goc = dept_cua_khoa(p.module_key)
            vung = cay.vung(goc)
            if not vung:
                continue
            if p.scope == SCOPE_ALL:
                tron = set(vung)
            elif p.scope == SCOPE_DEPARTMENT:
                # Phòng mình + trực thuộc, phần nằm trong vùng: mình đứng TRÊN (hoặc tại) nút của
                # dòng → cả vùng; đứng DƯỚI nút → cây con của mình; ở nhánh khác → không có gì.
                if cay.la_to_tien(user.department_id, goc):
                    tron = set(vung)
                elif user.department_id in vung:
                    tron = set(cay.vung(user.department_id))
                else:
                    tron = set()
            else:
                tron = set()
            for viec, cot in COT_VIEC.items():
                if not getattr(p, cot, False):
                    continue
                if p.scope == SCOPE_OWN:
                    self.rieng[viec] |= vung
                    if viec == VIEC_XEM:
                        self._ban_rieng.add(
                            user.department_id if user.department_id in vung else goc
                        )
                else:
                    self.tron[viec] |= tron
        for viec in COT_VIEC:
            self.rieng[viec] -= self.tron[viec]

    def muc(self, viec: str, team_id: int | None) -> str | None:
        if team_id is None:
            return None
        if team_id in self.tron[viec]:
            return MUC_TAT_CA
        if team_id in self.rieng[viec]:
            return MUC_CUA_TOI
        return None

    def co_tron(self, viec: str, team_id: int | None) -> bool:
        """Làm được `viec` trên TRỌN tổ (mọi việc của tổ, không chỉ việc mình được giao)."""
        return team_id is not None and team_id in self.tron[viec]

    def pham_vi_ban(self, team_id: int | None, viec: str = VIEC_XEM) -> tuple[set[int], set[int]]:
        """Bàn của nút `team_id` phủ VÙNG của nút đó. Trả (tổ thấy trọn, tổ chỉ thấy việc của mình)
        trong vùng — hai tập rời nhau; cả hai rỗng = ngoài phạm vi."""
        vung = self.cay.vung(team_id)
        return set(vung & self.tron[viec]), set(vung & self.rieng[viec])

    def co_gi(self) -> bool:
        return any(self.tron[v] or self.rieng[v] for v in COT_VIEC)

    def co_viec(self, viec: str) -> bool:
        return bool(self.tron[viec] or self.rieng[viec])

    def ban_thay_duoc(self) -> list[tuple[int, int, str]]:
        """(id nút, cấp, mức xem) của các bàn hiện trên menu, theo thứ tự cây.

        Mức `all` hiện mọi nút trong tập (đã đóng theo cây con); mức `own` chỉ hiện nút mở bàn
        của mình — thợ không cần thấy cả dãy nhóm mà mở ra đều chỉ có việc của mình."""
        ket = []
        for did, cap in self.cay.thu_tu():
            if did in self.tron[VIEC_XEM]:
                ket.append((did, cap, MUC_TAT_CA))
            elif did in self._ban_rieng:
                ket.append((did, cap, MUC_CUA_TOI))
        return ket

    def bang(self) -> dict[int, dict[str, str]]:
        """`{id tổ: {việc: mức}}` cho mọi nút có ít nhất một quyền — giao diện dựng nút theo đây."""
        ket: dict[int, dict[str, str]] = {}
        for did in self.cay.ten:
            dong = {v: m for v in COT_VIEC if (m := self.muc(v, did))}
            if dong:
                ket[did] = dong
        return ket


def quyen_to_cua(db: Session, user: User, cay: CayKhoi | None = None) -> QuyenTo:
    if cay is None:
        cay = doc_cay(db)
    dong = QuyenToRepository(db).dong_quyen_cua_vai(user.role_id) if user.role_id else []
    return QuyenTo(cay, user, dong)


def quyen_cua_uid(db: Session, uid: int | None) -> QuyenTo | None:
    user = db.get(User, uid) if uid is not None else None
    return quyen_to_cua(db, user) if user is not None else None


def thong_bao_thieu(viec: str) -> str:
    return _THONG_BAO_THIEU[viec]


def gate_to(
    db: Session,
    uid: int | None,
    team_id: int | None,
    viec: str,
    *,
    cong_viec_id: int | None = None,
) -> None:
    """Chặn (PermissionError) nếu tài khoản `uid` không làm được `viec` trên tổ `team_id`.

    Mức `own` chỉ qua khi `cong_viec_id` là việc người đó ĐANG được giao — không có công việc để
    đối chiếu (vd xác nhận nhận vật tư theo tổ) thì `own` không đủ."""
    q = quyen_cua_uid(db, uid)
    muc = q.muc(viec, team_id) if q is not None else None
    if muc == MUC_TAT_CA:
        return
    if muc == MUC_CUA_TOI and cong_viec_id is not None and la_viec_cua_toi(db, uid, cong_viec_id):
        return
    raise PermissionError(_THONG_BAO_THIEU[viec])


def gate_to_tron(db: Session, uid: int | None, team_id: int | None, viec: str) -> None:
    """Như `gate_to` nhưng đòi mức TRỌN tổ — thao tác cấp tổ không gắn một việc cụ thể của ai
    (hỗ trợ chéo, xác nhận nhận vật tư theo tổ, đóng thiếu nhóm): phạm vi "Của tôi" không đủ."""
    q = quyen_cua_uid(db, uid)
    if q is None or not q.co_tron(viec, team_id):
        raise PermissionError(_THONG_BAO_THIEU[viec])


def quyen_tren_viec(db: Session, uid: int | None, cong_viec, *, q: QuyenTo | None = None) -> dict[str, bool]:
    """`{việc chi tiết: làm được?}` của MỘT người trên MỘT công việc — giao diện bật/tắt nút theo
    đây thay vì tự suy từ phạm vi (mức `own` chỉ tính khi việc đang giao cho chính người đó)."""
    if q is None:
        q = quyen_cua_uid(db, uid)
    if q is None or cong_viec is None:
        return {v: False for v in VIEC_CHI_TIET}
    cua_toi: bool | None = None
    ket: dict[str, bool] = {}
    for v in VIEC_CHI_TIET:
        muc = q.muc(v, cong_viec.department_id)
        if muc == MUC_TAT_CA:
            ket[v] = True
        elif muc == MUC_CUA_TOI:
            if cua_toi is None:
                cua_toi = la_viec_cua_toi(db, uid, cong_viec.id)
            ket[v] = cua_toi
        else:
            ket[v] = False
    return ket


def la_viec_cua_toi(db: Session, uid: int, cong_viec_id: int) -> bool:
    from ..repositories.san_xuat_thuc_thi_repo import SanXuatThucThiRepository

    tt = SanXuatThucThiRepository(db)
    nv = tt.nhan_vien_theo_user(uid)
    return nv is not None and cong_viec_id in tt.cong_viec_ids_duoc_giao(nv.id, {cong_viec_id})


def nguoi_co_quyen(db: Session, team_id: int | None, viec: str) -> list[int]:
    """Tài khoản làm được TRỌN `viec` trên tổ `team_id` — người nhận thông báo real-time của tổ.

    Phạm vi `own` không nhận thông báo cấp tổ (họ chỉ được đụng việc của chính mình)."""
    if team_id is None:
        return []
    cay = doc_cay(db)
    ket: set[int] = set()
    for uid, dept, key, scope in QuyenToRepository(db).nguoi_giu_quyen(COT_VIEC[viec]):
        goc = dept_cua_khoa(key)
        if team_id not in cay.vung(goc):
            continue
        if scope == SCOPE_ALL or (scope == SCOPE_DEPARTMENT and cay.la_to_tien(dept, team_id)):
            ket.add(uid)
    return sorted(ket)
