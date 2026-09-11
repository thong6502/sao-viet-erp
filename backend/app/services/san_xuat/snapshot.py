"""Dựng SNAPSHOT phát hành — chụp routing/tổ/máy/định mức/khoán/vật tư tại thời điểm phát hành.

Nguyên tắc (spec §4.2):

  · CHỤP MỘT LẦN. Sau phát hành, xưởng sửa danh mục (đổi tổ, đổi định mức khoán) KHÔNG được làm
    xê dịch việc đã thả xuống — mọi số của công việc nằm ở đây, không đọc-sống lên routing.
  · MỘT BÀI GHÉP = MỘT CÔNG VIỆC (spec §3.3). Bước đã gộp vào bài ghép chỉ đẻ ĐÚNG MỘT công việc
    chung; các bước LSX bị nó phủ (`bai_ghep_cong_doan_map.lsx_step_key`) KHÔNG đẻ công việc riêng.
  · Số dẫn xuất (tiền khoán, sản lượng thực) KHÔNG chụp — tính lúc đọc ở pha thực thi.

Hàm ở đây THUẦN dựng-bản-ghi: nhận gói + phiên bản đã tạo, ghi công việc/phụ thuộc vào session,
KHÔNG commit (người gọi — `release.py` — chủ giao dịch).
"""
from __future__ import annotations

from ...models.san_xuat import (
    BUOC_MAY,
    CV_PHAT_HANH,
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatPhuThuoc,
)
from ...repositories.san_xuat_repo import SanXuatRepository
from ..dong_giay import ban_do_tram, tren_dong_giay


def _num(x) -> float | None:
    """Numeric (Decimal) → float cho JSON; None giữ None."""
    return None if x is None else float(x)


class _SoPhatHanh:
    """HỘP SỐ DẪN XUẤT của gói phát hành — dựng service TRỄ, cache quy cách theo lệnh / theo bài.

    Bốn thứ đi cùng thẻ việc phải TÍNH mới có (không đọc thẳng được từ cột nào của bước): đơn giá
    hiệu dụng · câu diễn giải sản lượng của bước ngoài dòng · dải thời lượng chạy máy · thẻ quy
    cách rút gọn. Cả bốn đều cần đúng MỘT thứ đắt tiền — bộ biến quy cách (`quy_cach_bien(lsx)`
    hoặc `quy_cach_bien_cua_bai(bai)`, mà bản của bài còn phải chạy `tinh_so_to`) — nên gom về một
    hộp, dựng trễ và cache: mỗi lệnh / mỗi bài chỉ dựng quy cách MỘT lần cho cả gói.

    Vì sao chốt Ở ĐÂY chứ không lúc lập kế hoạch: mọi số trên đều ăn `sl_vao`/`sl_ra` và quy cách
    của lệnh, mà những thứ ấy còn đổi suốt lúc lập kế hoạch. Phát hành là ĐÚNG khoảnh khắc kế
    hoạch đóng băng, cũng là lúc mọi ảnh chụp khác của công việc được chụp — chốt sớm hơn thì số
    ghim lệch với số đang hiện trên màn Kế hoạch.

    (Tên cũ `_DonGiaHieuDung` — 10/09/2026 lớp này nhận thêm ba vai ở trên nên đổi tên cho khớp.)
    """

    def __init__(self, db) -> None:
        self.db = db
        self._svc = None
        self._qc_lsx: dict[int, dict] = {}
        self._qc_bai: dict[int, dict] = {}

    def _lsx_svc(self):
        if self._svc is None:
            from ...repositories.lsx_repo import LsxRepository
            from ..lsx_service import LsxService

            # `audit`/`sequence` = None: hàm dùng ở đây chỉ ĐỌC và tính, không ghi vết nào —
            # cùng cách `ke_hoach_vat_tu_service` dựng service chỉ để hỏi số.
            self._svc = LsxService(self.db, LsxRepository(self.db), None, None)
        return self._svc

    def _quy_cach_lsx(self, lsx_id: int) -> dict:
        if lsx_id not in self._qc_lsx:
            from ...models.lsx import Lsx
            from ..bien_cong_thuc import quy_cach_bien

            lsx = self.db.get(Lsx, lsx_id)
            self._qc_lsx[lsx_id] = quy_cach_bien(lsx) if lsx is not None else {}
        return self._qc_lsx[lsx_id]

    def _quy_cach_bai(self, bg_id: int) -> dict:
        if bg_id not in self._qc_bai:
            from ...models.bai_ghep import BaiGhep
            from ...repositories.bai_ghep_repo import BaiGhepRepository
            from ..bai_ghep_service import BaiGhepService

            bg = self.db.get(BaiGhep, bg_id)
            svc = BaiGhepService(self.db, BaiGhepRepository(self.db), None, None)
            self._qc_bai[bg_id] = svc.quy_cach_bien_cua_bai(bg) if bg is not None else {}
        return self._qc_bai[bg_id]

    def quy_cach(self, *, lsx_id: int | None = None, bai_ghep_id: int | None = None) -> dict:
        """Bộ biến quy cách của nguồn số đứng sau bước: bài ghép thắng lệnh (bước chạy chung đo ở
        CẤP BÀI — `so_kem`/`so_mau` đã gộp của mọi thành viên)."""
        if bai_ghep_id:
            return self._quy_cach_bai(bai_ghep_id)
        return self._quy_cach_lsx(lsx_id) if lsx_id else {}

    def khoan_json(self, cd, *, lsx_id: int | None = None, bai_ghep_id: int | None = None):
        """`khoan_json` đem ghim vào công việc = ảnh chụp của bước, GẮN THÊM `don_gia_hd` nếu có.

        Chỉ những bước có ô tiền công RA THẲNG TIỀN (gọi chip `don_gia_khoan`) mới có khoá mới:
        công thức của chúng ra tổng tiền của bước, mà tầng trả lương thì nhân `đơn giá × phần sản
        lượng của từng người`, nên phải quy về một đơn giá trên đơn vị TRƯỚC khi đóng băng vào
        công việc. Xem `LsxService.don_gia_hieu_dung`.

        Khoá mới nằm CẠNH `don_gia` chứ không đè lên: `don_gia` vẫn là đơn giá gốc của đầu việc để
        đọc lại ảnh chụp và đối chiếu nhật ký, `don_gia_hd` mới là số tầng lương nhân. Đè lên thì
        không còn cách nào biết bước này ăn công thức hay ăn đơn giá thẳng.
        """
        kh = getattr(cd, "khoan_json", None)
        if not kh:
            return kh
        qc = self.quy_cach(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
        dg = self._lsx_svc().don_gia_hieu_dung(cd, qc)
        return kh if dg is None else {**kh, "don_gia_hd": round(dg, 4)}

    def _cong_doan(self, cd):
        """Dòng DANH MỤC đứng sau bước. `db.get` đi qua identity map nên gọi lặp không sinh query."""
        from ...models.cong_doan import CongDoan

        cid = getattr(cd, "cong_doan_id", None)
        return self.db.get(CongDoan, cid) if cid else None

    def don_vi_san_luong(self, cd) -> str | None:
        """ĐƠN VỊ bản địa của bước NGOÀI dòng giấy — `cong_doan.don_vi_san_luong` (mg `0289`).

        Bước ngoài dòng để trống cả hai ô đơn vị chặng (menu công đoạn chỉ còn 5 chặng từ mg
        `0273`), nên nếu không lấy ở đây thì công việc xuống tổ với đơn vị RỖNG: ô Ghi mẻ sản
        lượng không có chữ nào, bàn giao/KCS/yêu cầu kho cũng vậy.
        """
        cd_obj = self._cong_doan(cd)
        return (getattr(cd_obj, "don_vi_san_luong", None) or "").strip() or None

    def sl_dien_giai(self, cd, qc: dict) -> str | None:
        """Câu *"Số bản kẽm = 4 bản kẽm"* — vì sao bước ngoài dòng lại ra đúng con số ấy.

        Bước trên dòng giấy KHÔNG có câu này (số suy ngược theo chuỗi bù hao, không có công thức
        riêng) — nơi gọi tự lọc, hàm này trả None nốt nếu công đoạn chưa khai công thức.
        """
        return self._lsx_svc().san_luong_dien_giai(cd, self._cong_doan(cd), qc)

    def thoi_luong(self, cd, qc: dict) -> dict:
        """`{chay_phut, chay_phut_min, chay_phut_max}` của CẢ bước (chưa chia theo phân đoạn).

        Ba số này KHÔNG có cột sẵn — phải chạy `thoi_luong_buoc`, đúng engine mà màn Kế hoạch và
        Gantt đang dùng, để bàn tổ không nói một giờ khác với hai màn kia. Máy chưa khai dải tốc độ
        thì cả ba bằng nhau (râu co về một điểm), KHÔNG phải khoảng 0.

        Máy lấy từ `cd.may_id` (máy bước đã chọn), không lấy máy của DÒNG LỊCH: hai chỗ gần như
        luôn trùng, mà `cd.may_id` là thứ màn Kế hoạch hiển thị giờ theo — lệch nguồn là lệch số
        giữa hai màn nói về cùng một bước.
        """
        from ...models.may_thiet_bi import MayThietBi
        from ..lsx_service import thoi_luong_buoc

        may = self.db.get(MayThietBi, cd.may_id) if getattr(cd, "may_id", None) else None
        svc = self._lsx_svc()
        t = thoi_luong_buoc(cd, may, svc.sl_tinh_cua_buoc(cd, may, qc))
        dg = t["dien_giai"]
        return {
            "chay_phut": t["chay_phut"],
            "chay_phut_min": dg["chay_phut_min"],
            "chay_phut_max": dg["chay_phut_max"],
        }

    def the_quy_cach(self, qc: dict) -> dict | None:
        """THẺ QUY CÁCH rút gọn — 8 dòng đủ để đứng máy, không bê cả `lsx.quy_cach_json`.

        Số đọc qua `ngu_canh_lenh` chứ không đọc thẳng khoá JSON: cùng một thứ có tới ba tên khoá
        tuỳ đời ảnh chụp (`dai_in` · `kho_in_dai` · `dai`), mà hàm ấy là nơi DUY NHẤT trong hệ biết
        đủ cả ba. Kích thước nó trả về ở MÉT nên nhân lại 1.000 cho ra mm — đơn vị xưởng nói.

        Hai khổ gộp thành MỘT chuỗi `"640 × 450"`: thẻ này là thứ để ĐỌC, và tách bốn khoá số thì
        mỗi màn đọc lại tự ghép chuỗi theo một kiểu. Khoá nào không có số thì BỎ HẲN — thẻ rỗng
        trả None (cột `none_as_null`), vì một dict toàn `null` đọc như "có quy cách mà mất dữ liệu".
        """
        from ..bien_cong_thuc import ngu_canh_lenh

        qc = qc or {}
        ctx = ngu_canh_lenh(qc)

        def _kho(dai: float, rong: float) -> str | None:
            # `ngu_canh_lenh` coi 0 là CHƯA BIẾT (xem docstring của nó) — giữ nguyên luật đó ở đây.
            return f"{round(dai * 1000):g} × {round(rong * 1000):g}" if dai > 0 and rong > 0 else None

        def _so(v) -> float | None:
            return float(v) if v and float(v) > 0 else None

        the = {
            "giay": (qc.get("giay_ten") or "").strip() or None,
            # gsm là số xưởng nói ("giấy 150"), `ngu_canh_lenh` thì trả kg/m² cho công thức.
            "dinh_luong": _so(ctx["dinh_luong"] * 1000.0),
            "kho_in": _kho(ctx["dai_in"], ctx["rong_in"]),
            "kho_tp": _kho(ctx["dai_tp"], ctx["rong_tp"]),
            "so_mat": _so(ctx["so_mat"]),
            "so_mau": _so(ctx["so_mau"]),
            "so_kem": _so(ctx["so_kem"]),
            "so_con": _so(ctx["so_con"]),
            "so_luong": _so(ctx["so_luong"]),
            "ghi_chu_ky_thuat": (qc.get("ghi_chu_ky_thuat") or "").strip() or None,
        }
        the = {k: v for k, v in the.items() if v is not None}
        return the or None


def _dinh_muc(cd, hanh_ly: dict, ty_le: float) -> dict:
    """Ảnh định mức nhân lực + thời gian của một bước (LSX hoặc bài ghép — cùng hình dạng).

    Ba số phút nhân `ty_le` = phần sản lượng của phân đoạn này: bước tách làm hai mẻ 5.000 tờ thì
    MỖI thẻ chạy nửa thời gian, ghim nguyên giờ của cả bước lên cả hai thẻ là nói dối gấp đôi.
    Chỉ phần CHẠY co giãn theo số — chuẩn bị máy và thời gian khác thì mẻ nào cũng tốn đủ, nên
    chúng không nhân (cùng luật với `lsxBuoc.ts` bên frontend).

    `chay_phut` đổi nguồn 10/09/2026: trước đọc cột `cd.chay_phut` (ô NHẬP ĐÈ, dormant từ chốt
    2026-08-04 nên thực tế luôn NULL ⇒ bàn tổ không có lấy một con số giờ nào), nay lấy từ chính
    engine `thoi_luong_buoc` — cùng nguồn với `chay_phut_min`/`chay_phut_max` mới thêm, ba số cùng
    thang mới so được với nhau.
    """
    tl = hanh_ly["thoi_luong"]
    return {
        "so_nhan_cong_tieu_chuan": getattr(cd, "so_nhan_cong_tieu_chuan", None),
        "setup_phut": _num(getattr(cd, "setup_phut", None)),
        "nang_suat": _num(getattr(cd, "nang_suat", None)),
        "don_vi_nang_suat": getattr(cd, "don_vi_nang_suat", None),
        "chay_phut": round(tl["chay_phut"] * ty_le, 2),
        "chay_phut_min": round(tl["chay_phut_min"] * ty_le, 2),
        "chay_phut_max": round(tl["chay_phut_max"] * ty_le, 2),
        "phat_sinh_phut": _num(getattr(cd, "phat_sinh_phut", None)),
        # Cờ + câu diễn giải của bước NGOÀI dòng giấy. Chụp cờ chứ không để màn hạ nguồn tự suy từ
        # mã đơn vị: sau khi snapshot điền `don_vi_vao/ra` bằng đơn vị sản lượng (`kem`), hai cột
        # ấy không còn phân biệt được trong/ngoài dòng nữa — luật `tren_dong_giay` chỉ chấm được
        # trên bản ghi KẾ HOẠCH.
        "ngoai_dong": hanh_ly["ngoai_dong"],
        "sl_dien_giai": hanh_ly["sl_dien_giai"],
    }


def _hanh_ly(so: _SoPhatHanh, cd, *, lsx_id: int | None, bai_ghep_id: int | None,
             tram: dict[str, str]) -> dict:
    """HÀNH LÝ của thẻ việc — thứ một bước phải mang theo xuống tổ, tính MỘT LẦN cho cả bước.

    Nguyên tắc (`docs/superpowers/specs/2026-09-10-ban-to-du-thong-tin-design.md` §2): thẻ việc
    thả xuống tổ phải TỰ ĐỦ ĐỂ LÀM. Tổ trưởng không có quyền `lsx` nên không mở nổi hồ sơ lệnh, và
    lệnh thì còn sửa được sau khi phát hành (§4.2) — nên mọi thứ ở đây là ẢNH CHỤP, không phải cửa
    tra ngược.

    Đơn vị: bước NGOÀI dòng giấy để trống cả `don_vi_vao`/`don_vi_ra`, lấp bằng đơn vị sản lượng
    của công đoạn. Điền đúng một chỗ này thì cả năm khối hạ nguồn (ghi mẻ · bàn giao · KCS · yêu
    cầu kho · phân bổ lương) tự có đơn vị — trong module Thực hiện SX hai cột ấy chỉ đóng vai đơn
    vị BẢN ĐỊA của bước, không ai đọc chúng để hỏi "bước này ở chặng nào".
    """
    qc = so.quy_cach(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
    ngoai = not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram)
    dv = so.don_vi_san_luong(cd) if ngoai else None
    return {
        "don_vi_vao": cd.don_vi_vao or dv,
        "don_vi_ra": cd.don_vi_ra or dv,
        "ngoai_dong": ngoai,
        "sl_dien_giai": so.sl_dien_giai(cd, qc) if ngoai else None,
        "thoi_luong": so.thoi_luong(cd, qc),
        # Dặn dò của người lập kế hoạch (ô "Ghi chú kỹ thuật cho thợ"). KHÔNG chụp
        # `yeu_cau_ky_thuat`: câu đó viết cho NHÀ GIA CÔNG, không phải cho tổ trong xưởng.
        "ghi_chu": (getattr(cd, "ghi_chu", None) or "").strip() or None,
        "quy_cach_json": so.the_quy_cach(qc),
    }


def _khuon(db, cd) -> dict | None:
    """Ảnh chụp con dao của bước. `None` khi bước không trỏ dao nào (kể cả bước không cần dụng cụ).

    Đọc ĐÍCH DANH cột thay vì trả cả object: ảnh chụp phải là dữ liệu chết, không phải một hàng ORM
    còn sống mà lần đọc sau lại ra giá trị khác. Cùng lý do với `_vat_tu` ngay dưới.
    """
    kid = getattr(cd, "khuon_be_id", None)
    if not kid:
        return None
    from ...models.khuon_be import KhuonBe

    k = db.get(KhuonBe, kid)
    if k is None:
        return None
    return {
        "id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
        "tinh_trang": k.tinh_trang,
    }


def _vat_tu(cd) -> list[dict]:
    """Ảnh danh sách vật tư của bước (đọc quan hệ `.vat_tus` — đã snapshot mã/tên/đơn vị từ trước)."""
    out: list[dict] = []
    for vt in getattr(cd, "vat_tus", []) or []:
        out.append({
            "vat_tu_id": vt.vat_tu_id,
            "ma": vt.vat_tu_ma_snapshot,
            "ten": vt.vat_tu_ten_snapshot,
            "don_vi": vt.don_vi_snapshot,
            "so_luong": _num(vt.so_luong),
        })
    return out


def _chia(tong, ty_les: list[float]) -> list[float | None]:
    """Chia `tong` theo `ty_les`; phần CUỐI gánh phần lẻ làm tròn ⇒ Σ khép ĐÚNG `tong`.

    Cùng cách khép tổng với `phan_doan.tach`: cột là NUMERIC(18,3), làm tròn từng phần rồi cộng
    lại là tổng trôi một tờ — mà lệch một tờ là lệch cả bảng cân đối vật tư lẫn định mức khoán.
    """
    if tong is None:
        return [None] * len(ty_les)
    t = float(tong)
    ra = [round(t * r, 3) for r in ty_les]
    ra[-1] = round(t - sum(ra[:-1]), 3)
    return ra


def _chia_theo_phan_doan(lich: list[tuple], cd) -> list[tuple]:
    """Số `(vào, ra)` của TỪNG phân đoạn lịch, Σ khép đúng số của bước.

    Tỉ lệ lấy từ CHÍNH CỤM (Σ `so_luong` của các dòng) — cùng MỘT đường với
    `phan_doan.ty_le_trong_cum` mà engine thời lượng đang dùng, đừng đẻ đường thứ hai:

      · suy từ `phan_doan_tong` kiểu 1/N là sai ngay khi ai đó chia 6.000 + 4.000;
      · lấy `so_luong_vao` của bước làm mẫu số thì bước chưa khai số (0) sẽ cho MỖI phân đoạn ăn
        TRỌN số của bước — nhân bản sản lượng, im lặng.

    Chia CẢ hai cột theo cùng tỉ lệ, không gán thẳng `so_luong` của dòng vào `so_luong_vao`: bước
    có hệ số quy đổi (in: vào tờ, ra con) mà chỉ chia một cột là hai cột nói hai thang khác nhau.
    """
    if len(lich) == 1 and lich[0][4] is None:
        # Bước CHƯA tách — giữ NGUYÊN số của bước (Decimal), không đi vòng qua float. Đây là
        # đường của mọi lệnh đang chạy, đừng để nó lệch một phần nghìn so với trước.
        return [(cd.so_luong_vao, cd.so_luong_ra)]
    n = len(lich)
    tong_cum = sum(float(r[4] or 0) for r in lich)
    ty_les = (
        [float(r[4] or 0) / tong_cum for r in lich] if tong_cum > 0 else [1.0 / n] * n
    )
    return list(zip(_chia(cd.so_luong_vao, ty_les), _chia(cd.so_luong_ra, ty_les)))


def _ten_phan_doan(ten: str | None, phan_doan_so: int, phan_doan_tong: int) -> str:
    """Tên công việc của một phân đoạn — bước chưa tách giữ nguyên tên bước.

    Tổ nhìn hai thẻ cùng công đoạn mà không có hậu tố thì không biết thẻ nào là mẻ nào. Cột
    `ten_cong_doan` là String(255) nên cắt phần TÊN chứ đừng cắt hậu tố: mất "lần 2/2" là mất
    đúng thứ dùng để phân biệt.
    """
    goc = ten or ""
    if phan_doan_tong <= 1:
        return goc
    hau_to = f" (lần {phan_doan_so}/{phan_doan_tong})"
    return goc[: 255 - len(hau_to)] + hau_to


def _checklist(cd, tieu_chi_theo_cd: dict[int, list]) -> list[dict] | None:
    """Checklist KCS của bước — lấy từ danh mục theo `cong_doan_id`, KHÔNG gate theo `la_kcs`.

    08/09/2026 (`docs/design-kcs-theo-cong-doan.md`): KCS đổi sang ba tầng Giai đoạn → Công đoạn →
    Checklist, nên MỌI công đoạn có tiêu chí gắn vào đều là một điểm kiểm — không riêng bước cuối
    routing. Gate cũ (`if not la_kcs: return None`) làm bàn KCS chỉ thấy đúng một bước cuối, đúng
    thứ tờ ISO của xưởng KHÔNG làm: tờ đó kiểm ở cả khâu in lẫn từng công đoạn sau in.

    `la_kcs` vẫn sống nhưng nói việc KHÁC — "thẻ việc này thuộc về tổ KCS" (và `la_kcs_cuoi` mở cửa
    nhập kho thành phẩm). Đừng gộp hai khái niệm: bật `la_kcs` cho mọi công đoạn có checklist là ném
    toàn bộ việc sản xuất lên bàn KCS.

    TRẢ None (không phải `[]`) khi công đoạn không có tiêu chí nào: cột NULL chính là bộ lọc "thẻ
    việc này có phải điểm kiểm không" mà bàn KCS truy vấn. Ghi `[]` là đẻ ra điểm kiểm rỗng.

    Nguồn DUY NHẤT là danh mục — ô "Tiêu chí KCS bổ sung" của bước lệnh đã gỡ ở mg `0283`.
    """
    ds = tieu_chi_theo_cd.get(cd.cong_doan_id) if cd.cong_doan_id else None
    if not ds:
        return None
    return [
        {
            "tieu_chi_id": tc.id, "ma": tc.ma, "ten": tc.ten, "huong_dan": tc.huong_dan,
            "bat_buoc": bool(tc.bat_buoc), "nguon": "danh_muc", "thu_tu": tc.thu_tu,
        }
        for tc in ds
    ]


def _moc_xep_lich_3(db, cd) -> tuple | None:
    """`(bắt_đầu, kết_thúc)` của MỘT bước lệnh theo Xếp lịch 3, hoặc `None` nếu lệnh chưa xếp ở đó.

    Bước chạy chung của bài ghép không đi đường này (`cd` khi đó là `BaiGhepCongDoan`, không có
    `lsx_id`) — màn 3 làm việc ở cấp lệnh, bài ghép giữ nguyên đường cũ.
    """
    lsx_id = getattr(cd, "lsx_id", None)
    if not lsx_id:
        return None
    from ..xep_lich_3.moc import moc_theo_buoc

    return moc_theo_buoc(db, [lsx_id]).get(cd.id)


def _cong_viec_theo_phan_doan(
    repo: SanXuatRepository,
    *,
    lich: list[tuple],
    cd,
    tieu_chi_theo_cd: dict[int, list],
    la_kcs: bool,
    chung: dict,
    khoan_json: dict | None,
    hanh_ly: dict,
) -> list[SanXuatCongViec]:
    """Đẻ MỘT công việc cho MỖI phân đoạn lịch của một bước; trả danh sách theo `phan_doan_so`.

    Dùng chung cho cả hai nhánh (bước riêng của lệnh + bước chạy chung của bài ghép) vì hai bên
    chỉ khác ở mấy khoá neo — gom vào `chung`. `lich` là kết quả `repo.lich_lsx_step` /
    `lich_bg_step`: mỗi phần tử `(may_id, start, finish, phan_doan_so, so_luong)`.

    Bước CHƯA vào kế hoạch (không dòng lịch nào) vẫn phải ra đúng một công việc — trước đây
    `thoi_gian_*_step` trả `(None, None, None)` và snapshot vẫn ghi; giữ nguyên hành vi đó bằng
    một phần tử giả, không thì lệnh phát hành khi chưa xếp giờ sẽ RỖNG bàn tổ.

    `la_kcs` tính MỘT LẦN cho cả bước rồi áp cho mọi phân đoạn: KCS là tính chất của BƯỚC (vị trí
    trong routing + tổ), không phải của lần chạy.
    """
    if not lich:
        # Lệnh xếp ở Xếp lịch 3 KHÔNG có dòng `xep_lich_cong_doan` — mốc từng bước là số dẫn xuất
        # từ một mốc duy nhất của cả lệnh. Không lấy ở đây thì thẻ việc dưới xưởng ra trống giờ,
        # bàn tổ không xếp được thứ tự làm. Máy vẫn lấy từ chính bước (`cd.may_id`) ở dưới.
        moc = _moc_xep_lich_3(repo.db, cd)
        lich = [(None, moc[0], moc[1], 1, None)] if moc else [(None, None, None, 1, None)]
    tong = len(lich)
    so_luongs = _chia_theo_phan_doan(lich, cd)
    vao_buoc = float(cd.so_luong_vao or 0)
    ra: list[SanXuatCongViec] = []
    for (may_id, start, finish, phan_doan_so, _sl), (sl_vao, sl_ra) in zip(lich, so_luongs):
        # Phần sản lượng của phân đoạn này — hệ số co giãn của ba số phút chạy. Bước chưa tách (và
        # bước chưa khai số vào) về 1,0: giữ nguyên giờ của cả bước, không chia cho 0.
        ty_le = (float(sl_vao or 0) / vao_buoc) if vao_buoc > 0 and tong > 1 else 1.0
        cv = SanXuatCongViec(
            **chung,
            step_key=cd.step_key,
            # Cặp số phân đoạn ghi THÀNH CỘT chứ không chỉ nằm trong tên: "Phát hành cập nhật"
            # phải khớp công việc ↔ dòng lịch bằng số, không bằng cách đọc lại nhãn tiếng Việt.
            phan_doan_so=phan_doan_so, phan_doan_tong=tong,
            ten_cong_doan=_ten_phan_doan(cd.ten, phan_doan_so, tong),
            nhom_cong_doan=cd.nhom, loai_buoc=cd.loai_buoc or BUOC_MAY,
            department_id=cd.department_id, la_kcs=la_kcs,
            may_id=may_id or cd.may_id,
            du_kien_bat_dau=start, du_kien_ket_thuc=finish,
            so_luong_vao=sl_vao, so_luong_ra=sl_ra,
            don_vi_vao=hanh_ly["don_vi_vao"], don_vi_ra=hanh_ly["don_vi_ra"],
            he_so_quy_doi=cd.he_so_quy_doi,
            # Định mức/khoán/vật tư KHÔNG chia theo phân đoạn: chúng là ĐỊNH MỨC (trên một đơn vị
            # / trên một lượt), chia nữa là chia hai lần. Sản lượng đã mang phần của phân đoạn —
            # và ba số PHÚT CHẠY thì có, vì chúng là tổng chứ không phải định mức (xem `_dinh_muc`).
            dinh_muc_json=_dinh_muc(cd, hanh_ly, ty_le),
            khoan_json=khoan_json, vat_tu_json=_vat_tu(cd),
            # Dặn dò + thẻ quy cách: chụp CÙNG LÚC với vật tư, cùng lý do — thẻ việc phải tự đủ.
            ghi_chu=hanh_ly["ghi_chu"], quy_cach_json=hanh_ly["quy_cach_json"],
            # Nhà gia công + con dao: chụp CÙNG LÚC với vật tư, cùng một lý do — bàn tổ và các màn
            # theo dõi phải tự đứng được, không tra ngược lệnh (lệnh còn sửa được sau khi phát).
            nha_cung_cap=getattr(cd, "nha_cung_cap", None),
            khuon_json=_khuon(repo.db, cd),
            # Gọi lại `_checklist` cho TỪNG phân đoạn: mỗi dòng phải giữ bản JSON riêng, dùng
            # chung một list Python là sửa checklist của mẻ này lan sang mẻ kia.
            kcs_tieu_chi_json=_checklist(cd, tieu_chi_theo_cd),
            trang_thai=CV_PHAT_HANH,
        )
        repo.add(cv)
        repo.flush()
        ra.append(cv)
    return ra


def dung_cong_viec(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    tieu_chi_theo_cd: dict[int, list] | None = None,
) -> dict[str, list[SanXuatCongViec]]:
    """Đẻ công việc cho gói phát hành; trả map `step_key` → DANH SÁCH công việc theo phân đoạn.

    Trước 31/08/2026 map này là `step_key` → MỘT công việc, vì một bước chỉ có một dòng lịch. Từ
    khi tách được LẦN CHẠY (spec-thuc-te-vs-ke-hoach §2.4), một bước có N dòng lịch ⇒ N công việc,
    xếp theo `phan_doan_so`. Bước chưa tách vẫn ra danh sách MỘT phần tử — bên gọi không cần phân
    biệt hai trường hợp.

    Với bước LSX bị bài ghép phủ, `step_key` của nó cũng trỏ về danh sách công việc CHUNG — cạnh
    phụ thuộc chéo neo vào đúng bản ghi thực hiện chung.
    """
    cv_by_step: dict[str, list[SanXuatCongViec]] = {}
    tieu_chi_theo_cd = tieu_chi_theo_cd or {}
    so = _SoPhatHanh(repo.db)
    tram = ban_do_tram(repo.db)

    # KCS kiêm nhiệm — suy TỰ ĐỘNG (không còn khai tay ở danh mục Công đoạn): một bước là KCS khi
    # nó là bước CUỐI CÙNG trong routing của một LSX VÀ tổ thực hiện có `Department.is_kcs=true`
    # (xem docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem-suy-tu-dong.md). Nạp trước "bước cuối
    # của mỗi LSX" một lần để tra O(1) ở cả hai nhánh dưới (LSX riêng + bước dùng chung bài ghép).
    kcs_dept_ids = repo.kcs_department_ids()
    steps_by_lsx = {lsx_id: repo.routing_steps(lsx_id) for lsx_id in lsx_ids}
    buoc_cuoi_key_by_lsx = {
        lid: steps[-1].step_key for lid, steps in steps_by_lsx.items() if steps
    }

    # (1) Bước dùng chung của bài ghép — MỘT công việc mỗi bước, phủ nhiều bước LSX.
    covered_step_keys: set[str] = set()
    for bg_id in sorted(bai_ghep_ids):
        for cd in repo.bai_ghep_cong_doans(bg_id):
            covered = repo.covered_step_keys_of_cd(cd.id)
            covered_step_keys |= covered
            covered_lsx_ids = repo.lsx_ids_covered_by_cd(cd.id)
            # Nhóm của công việc chung: nếu mọi LSX được phủ cùng một nhóm thì gán nhóm đó, khác
            # nhau (bài ghép nối nhiều nhóm) thì để trống — phân bổ sản lượng theo nhóm ở pha sau.
            nhom_ids = {
                nhom_by_lsx[lid].id
                for lid in covered_lsx_ids
                if lid in nhom_by_lsx
            }
            nhom_id = next(iter(nhom_ids)) if len(nhom_ids) == 1 else None
            # KCS: bước chung này có phải bước cuối của ÍT NHẤT MỘT LSX nó phủ, VÀ tổ thực hiện
            # (của chính lượt chạy chung — gán lúc lập kế hoạch gộp) có `is_kcs=true`.
            la_kcs = cd.department_id in kcs_dept_ids and any(
                buoc_cuoi_key_by_lsx.get(lid) in covered for lid in covered_lsx_ids
            )
            cvs = _cong_viec_theo_phan_doan(
                repo, lich=repo.lich_bg_step(cd.id), cd=cd,
                tieu_chi_theo_cd=tieu_chi_theo_cd, la_kcs=la_kcs,
                khoan_json=so.khoan_json(cd, bai_ghep_id=bg_id),
                hanh_ly=_hanh_ly(so, cd, lsx_id=None, bai_ghep_id=bg_id, tram=tram),
                chung=dict(
                    goi_id=goi.id, phien_ban_so=phien_ban_so,
                    nhom_id=nhom_id, lsx_id=None, bai_ghep_id=bg_id,
                    bai_ghep_cong_doan_id=cd.id,
                ),
            )
            cv_by_step[cd.step_key] = cvs
            for sk in covered:
                cv_by_step[sk] = cvs

    # (2) Bước RIÊNG của từng LSX — bỏ bước đã bị bài ghép phủ.
    for lsx_id in sorted(lsx_ids):
        grp = nhom_by_lsx.get(lsx_id)
        buoc_cuoi_key = buoc_cuoi_key_by_lsx.get(lsx_id)
        for cd in steps_by_lsx.get(lsx_id) or []:
            if cd.step_key in covered_step_keys:
                continue
            la_kcs = cd.step_key == buoc_cuoi_key and cd.department_id in kcs_dept_ids
            cv_by_step[cd.step_key] = _cong_viec_theo_phan_doan(
                repo, lich=repo.lich_lsx_step(cd.id), cd=cd,
                tieu_chi_theo_cd=tieu_chi_theo_cd, la_kcs=la_kcs,
                khoan_json=so.khoan_json(cd, lsx_id=lsx_id),
                hanh_ly=_hanh_ly(so, cd, lsx_id=lsx_id, bai_ghep_id=None, tram=tram),
                chung=dict(
                    goi_id=goi.id, phien_ban_so=phien_ban_so,
                    nhom_id=grp.id if grp else None, lsx_id=lsx_id, bai_ghep_id=None,
                    lsx_cong_doan_id=cd.id,
                ),
            )

    return cv_by_step


def danh_dau_kcs_cuoi(
    repo: SanXuatRepository,
    *,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> dict[int, int]:
    """Suy KCS-cuối của MỖI nhóm (spec §3.2/§4.4): bước KCS nằm ở CUỐI routing của một LSX thành
    viên. Đúng một ứng viên/nhóm → đánh `la_kcs_cuoi` + chốt LSX thân chính. Không có / nhiều hơn
    một → để engine kiểm-phát-hành báo (không tự đoán).

    Bước KCS-cuối bị TÁCH lần chạy: đánh dấu MỌI phân đoạn, không riêng phân đoạn cuối. `la_kcs_cuoi`
    là tính chất của BƯỚC, và ba chỗ đọc nó đều đọc theo TẬP: `kho.tao_yeu_cau_kho_mot_nut` chặn
    thẳng công việc thiếu cờ (bỏ cờ ở lần chạy 1 ⇒ số ĐẠT của mẻ đầu không có đường vào kho), còn
    `dong_nhom` cộng `so_luong_ra` + gom batch KCS trên đúng tập ấy (thiếu một phân đoạn ⇒ mục tiêu
    nhóm tụt đúng phần của nó). "Nhóm chỉ đóng khi mẻ cuối xong" vẫn giữ, do điều kiện "mọi công
    việc đã hoàn thành" của `dong_nhom._danh_gia` lo.

    Trả map nhom_id → lsx_id thân chính (chỉ nhóm xác định được).
    """
    kcs_dept_ids = repo.kcs_department_ids()
    ung_vien: dict[int, list[tuple[int, str]]] = {}  # nhom_id → [(lsx_id, step_key)]
    for lsx_id in lsx_ids:
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        steps = repo.routing_steps(lsx_id)
        if not steps:
            continue
        cuoi = steps[-1]  # đã sort theo thu_tu, id
        if cuoi.department_id in kcs_dept_ids and cuoi.step_key in cv_by_step:
            ung_vien.setdefault(grp.id, []).append((lsx_id, cuoi.step_key))

    than_chinh: dict[int, int] = {}
    for nhom_id, ds in ung_vien.items():
        if len(ds) != 1:
            continue
        lsx_id, step_key = ds[0]
        for cv in cv_by_step[step_key]:
            cv.la_kcs_cuoi = True
        than_chinh[nhom_id] = lsx_id
    return than_chinh


def dung_phu_thuoc(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> int:
    """Chụp cạnh phụ thuộc CHÉO giữa các LSX trong gói thành `san_xuat_phu_thuoc` (bước ghép §3.2).

    Chỉ nối cạnh mà CẢ hai đầu đều có công việc trong gói này; neo về công việc chung nếu đầu đó đã
    bị bài ghép phủ (nhờ `cv_by_step` đã map cả step_key bị phủ). Nhóm lấy từ LSX ĐÍCH (luôn có
    trong gói) — `cong_viec.nhom_id` có thể trống nếu đầu đó là bước dùng chung nối nhiều nhóm, mà
    cột `san_xuat_phu_thuoc.nhom_id` NOT NULL. Tỷ lệ ghép để trống — kế hoạch tinh chỉnh ở pha sau.

    Bước đã TÁCH lần chạy: nguồn là phân đoạn CUỐI, đích là phân đoạn ĐẦU. Nối vào phân đoạn đầu
    của nguồn là cho bước sau chạy khi mới xong 60% — đúng thứ mà tách lần chạy sinh ra để tránh."""
    dem = 0
    for truoc, sau in repo.cross_lsx_edges_chi_tiet(lsx_ids):
        nguon_ds = cv_by_step.get(truoc.step_key) or []
        dich_ds = cv_by_step.get(sau.step_key) or []
        if not nguon_ds or not dich_ds:
            continue
        nguon, dich = nguon_ds[-1], dich_ds[0]
        if nguon.id == dich.id:
            continue
        grp = nhom_by_lsx.get(sau.lsx_id) or nhom_by_lsx.get(truoc.lsx_id)
        if grp is None:
            continue  # không truy được nhóm (dữ liệu cũ) — bỏ cạnh còn hơn vỡ NOT NULL
        repo.add(SanXuatPhuThuoc(
            goi_id=goi.id, phien_ban_so=phien_ban_so,
            nhom_id=grp.id,
            nguon_cong_viec_id=nguon.id, dich_cong_viec_id=dich.id,
            don_vi_nguon=truoc.don_vi_ra, don_vi_dich=sau.don_vi_vao,
        ))
        dem += 1
    repo.flush()
    return dem


def dung_diem_toa(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, list[SanXuatCongViec]],
) -> int:
    """Chụp cạnh TOẢ từ điểm-toả bài ghép sang từng nhánh LSX riêng thành `san_xuat_phu_thuoc`.

    Điểm toả = bước dùng chung CUỐI CÙNG trên dòng giấy của một LSX thành viên (theo `thu_tu`
    routing); đích = bước RIÊNG đầu tiên ngay sau đó của chính LSX đó. Chỉ nhận bước dùng chung
    nằm TRÊN DÒNG GIẤY (`tren_dong_giay`) — bước như ghi kẽm/CTP không đếm, tránh lấy nhầm điểm
    toả. LSX không còn bước riêng nào sau bước chung cuối (mọi bước đều dùng chung, hoặc bài ghép
    chưa có bước chung nào trên dòng giấy) thì không có gì để toả — bỏ qua, không phải lỗi.

    Điểm toả bị TÁCH lần chạy: MỖI phân đoạn một cạnh. Cạnh này không phải cổng chặn mà là đường
    tự chia sản lượng (`san_luong._toa_san_luong` chạy theo từng batch của CÔNG VIỆC NGUỒN) — chỉ
    nối phân đoạn cuối thì số của mẻ đầu không bao giờ toả xuống nhánh, mất im lặng. Đích thì
    ngược lại, chỉ MỘT: phân đoạn đầu của bước riêng."""
    if not bai_ghep_ids:
        return 0
    so_con = repo.thanh_vien_so_con(bai_ghep_ids)
    tram = ban_do_tram(repo.db)
    dem = 0
    for lsx_id in sorted(lsx_ids):
        con = so_con.get(lsx_id)
        if not con or con <= 0:
            continue
        steps = repo.routing_steps(lsx_id)
        diem_toa_idx = None
        for i, cd in enumerate(steps):
            cvs = cv_by_step.get(cd.step_key)
            if not cvs or cvs[0].bai_ghep_id is None:
                continue
            if not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram):
                continue
            diem_toa_idx = i
        if diem_toa_idx is None:
            continue
        nguon_cvs = cv_by_step[steps[diem_toa_idx].step_key]
        dich_cd = next(
            (
                cd for cd in steps[diem_toa_idx + 1:]
                if (cv_by_step.get(cd.step_key)
                    and cv_by_step[cd.step_key][0].bai_ghep_id is None)
            ),
            None,
        )
        if dich_cd is None:
            continue
        dich_cv = cv_by_step[dich_cd.step_key][0]
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        don_vi_ra = steps[diem_toa_idx].don_vi_ra
        don_vi_vao = dich_cd.don_vi_vao
        for nguon_cv in nguon_cvs:
            repo.add(SanXuatPhuThuoc(
                goi_id=goi.id, phien_ban_so=phien_ban_so,
                nhom_id=grp.id,
                nguon_cong_viec_id=nguon_cv.id, dich_cong_viec_id=dich_cv.id,
                ty_le_ghep=float(con),
                don_vi_nguon=don_vi_ra, don_vi_dich=don_vi_vao,
                quy_tac_quy_doi=(
                    f"Điểm toả bài ghép: 1 {don_vi_ra or '?'} chung → {con} {don_vi_vao or '?'} riêng của lệnh"
                ),
            ))
            dem += 1
    repo.flush()
    return dem
