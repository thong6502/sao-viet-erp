"""Công đoạn — service: CRUD + validate (§8).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..models.cong_doan import (
    CHE_DO_TINH, KIEU_BU_HAO, NHOM, PRICING_BASIS, TOOLING_TYPE, CongDoan,
)
from ..models.don_vi_do import TRAM_DONG_GIAY, tram_chay_xuoi
from ..repositories.cong_doan_repo import CongDoanRepository
from .bien_cong_thuc import LOAI_CONG_DOAN, LOAI_QUY_DOI
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)
from .thanh_phan_engine import kiem_cong_thuc

class CongDoanError(CatalogError):
    pass


class CongDoanValidationError(CongDoanError, CatalogValidationError):
    pass


class CongDoanDuplicate(CongDoanError, CatalogDuplicate):
    pass


class CongDoanNotFound(CongDoanError, CatalogNotFound):
    pass


class CongDoanService(CatalogService):
    LOAI = "cong_doan"
    E_NOT_FOUND = CongDoanNotFound
    E_DUPLICATE = CongDoanDuplicate
    E_VALIDATION = CongDoanValidationError
    MSG_NOT_FOUND = "Không tìm thấy công đoạn."
    MSG_DUPLICATE = "Mã công đoạn đã tồn tại."

    def __init__(self, repo: CongDoanRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _chuan_hoa(self, data: dict) -> dict:
        """Khử trùng danh sách tổ phụ trách, GIỮ thứ tự chọn (tổ đầu là mặc định của bước lệnh).

        `department_ids = None` là VẮNG (giữ nguyên danh sách đang có — ô trống ở file Excel) — bỏ
        khoá hẳn để repo không tưởng đó là "xoá hết tổ". Danh sách RỖNG thì đúng là gỡ hết tổ.
        """
        data = dict(data)
        if "department_ids" in data:
            ids = data.get("department_ids")
            if ids is None:
                data.pop("department_ids")
            else:
                data["department_ids"] = list(dict.fromkeys(int(i) for i in ids if i))
        return data

    def _anh_chup_nhan_ban(self, goc) -> dict:
        """Bản sao mang theo danh sách tổ — ảnh chụp nhật ký chỉ có chúng dưới dạng chữ."""
        data = super()._anh_chup_nhan_ban(goc)
        data["department_ids"] = list(goc.department_ids)
        return data

    def _kiem_to(self, data: dict, obj: CongDoan | None) -> list[int]:
        """Danh sách tổ SẼ LƯU (vắng = giữ của bản ghi). Tổ MỚI thêm phải có thật trong cây tổ chức;
        tổ đang lưu mà nay đã bị xoá thì để yên — form nạp lại đúng danh sách cũ, chặn là khoá luôn
        đường sửa công đoạn đó."""
        cu = list(obj.department_ids) if obj is not None else []
        if "department_ids" not in data:
            return cu
        ids = data["department_ids"]
        moi = {i for i in ids if i not in cu}
        if moi and moi - {d.id for d in self.repo.phong_ban_tat_ca()}:
            raise CongDoanValidationError("Không tìm thấy tổ phụ trách đã chọn.")
        return ids

    def _validate(self, data: dict, obj: CongDoan | None = None) -> None:
        if not (data.get("ma") or "").strip():
            raise CongDoanValidationError("Mã công đoạn không được trống.")
        if not (data.get("ten") or "").strip():
            raise CongDoanValidationError("Tên công đoạn không được trống.")
        if data.get("nhom") not in NHOM:
            raise CongDoanValidationError("Nhóm công đoạn không hợp lệ.")
        # MÁY của công đoạn phải CÓ THẬT và còn dùng — `may_id` là soft-ref nên không có FK gác hộ.
        # Máy đã thanh lý mà vẫn nằm trong danh sách thì bước lệnh gán được một máy không tồn tại
        # trên bàn xếp lịch.
        may_rows = data.get("may_lam_duoc") or []
        if may_rows:
            may_ids = [int(r.get("may_id") or 0) for r in may_rows]
            if len(set(may_ids)) != len(may_ids):
                raise CongDoanValidationError("Một máy chỉ khai được một lần trong công đoạn.")
            song = self.repo.mays(set(may_ids))
            for mid in may_ids:
                may = song.get(mid)
                if may is None or not may.active:
                    raise CongDoanValidationError(
                        "Máy không còn trong danh mục hoặc đã ngừng dùng.")
            for r in may_rows:
                # Chuẩn hoá TẠI ĐÂY để mọi đường vào (form, Excel, API) cùng một dạng: khoảng
                # trắng thừa làm `if cong_thuc:` ở engine tưởng có khai rồi `safe_eval("  ")` nổ.
                for k in ("cong_thuc_gio", "cong_thuc_gia"):
                    r[k] = ((r.get(k) or "").strip()) or None
            # W-CD-GIA-NGOAI-IN: công thức GIÁ chỉ có nghĩa ở công đoạn nhóm In — phiếu tính giá
            # chỉ chọn máy ở khối In của thành phần, nên câu khai cho máy bế/cán không có đường
            # nào chảy tới. Màn danh mục đã ẩn ô này ngoài nhóm In, nhưng bảng Excel thì KHÔNG:
            # không dọn ở đây thì một câu gõ nhầm vẫn nằm trong DB và `tinh_gia_service` vẫn đọc
            # ra, giá lệch mà chẳng màn nào bày cho người dùng thấy vì sao.
            if data.get("nhom") != "print":
                for r in may_rows:
                    r["cong_thuc_gia"] = None
            # Soi SAU khi dọn: ngoài nhóm In ô giá vừa bị ép None, chặn nó là chặn một câu sắp bị
            # vứt đi. Gọi tên MÁY trong câu lỗi — bảng nhiều dòng, không nói tên thì người khai
            # phải mở từng panel để dò xem mình gõ hỏng ở đâu.
            for r in may_rows:
                ten_may = getattr(song.get(int(r.get("may_id") or 0)), "ten", "")
                o = f" (máy {ten_may})" if ten_may else ""
                self._kiem_o(r.get("cong_thuc_gio"), nhan=f"Công thức giờ chạy{o}",
                             loai=LOAI_QUY_DOI)
                self._kiem_o(r.get("cong_thuc_gia"), nhan=f"Công thức giá{o}",
                             loai=LOAI_CONG_DOAN)
        self._kiem_to(data, obj)
        # ⚠️ Khối validate "định mức đầu việc" (năng suất người-giờ · kíp chuẩn · công thức tiền
        #    công · cách đo giờ) GỠ 18/09/2026 (mg `0320`): công đoạn thôi khai đầu việc. Việc khoán
        #    nay chọn LÚC GHI MẺ ở bàn tổ, còn thời lượng bước tổ do người lập lệnh gõ tay
        #    (`so_gio_ke_hoach`). Vật tư ở lại nhưng treo thẳng vào CÔNG ĐOẠN (§3.1).
        self._kiem_vat_tu(data.get("vat_tus") or [], self._vat_tu_dang_co(obj))

        che_do = data.get("che_do_tinh", "theo_san_luong")
        if che_do not in CHE_DO_TINH:
            raise CongDoanValidationError("Chế độ tính không hợp lệ.")
        if data.get("pricing_basis") not in PRICING_BASIS:
            raise CongDoanValidationError("Tính theo sản lượng cần pricing_basis hợp lệ. [E-CD-BASIS]")
        # GIỮ ĐƯỢC giá trị vốn có, chỉ chặn GÁN MỚI — cùng luật với đơn vị đã ngừng dùng
        # (`vat_lieu_kho_service._kiem_don_vi`). Cần vì `"kem"` vừa bị gỡ khỏi `TOOLING_TYPE`
        # (16/08/2026): công đoạn cũ nào còn mang giá trị đó thì sửa TÊN thôi cũng ăn lỗi
        # "Loại dụng cụ không hợp lệ", trong khi người dùng chẳng đụng vào ô ấy. Đo trên DB dev
        # là 0/13, nhưng prod chưa đếm được nên không đoán.
        tooling = data.get("tooling_type")
        if tooling not in (None, "") and tooling not in TOOLING_TYPE                 and tooling != getattr(obj, "tooling_type", None):
            raise CongDoanValidationError("Loại dụng cụ không hợp lệ.")
        if data.get("kieu_bu_hao", "khong") not in KIEU_BU_HAO:
            raise CongDoanValidationError("Kiểu bù hao không hợp lệ. [E-CD-BUHAO]")
        # Đơn vị vào/ra là MENU ĐÓNG 5 CHẶNG dòng giấy (06/09/2026) — không còn trỏ vào danh mục
        # Đơn vị & quy đổi. Hai ca hợp lệ, không có ca thứ ba:
        #   - cùng để TRỐNG        → bước NGOÀI dòng giấy (ghi kẽm, đóng thùng): đứng ngoài chuỗi bù
        #                            hao; đơn vị + số do người lập lệnh tự khai ở bước
        #                            (`lsx_service.tu_khai_don_vi`)
        #   - hai đầu đều là CHẶNG → bước trên dòng giấy, phải đúng chiều (`tram_chay_xuoi`)
        #
        # Trước đây bước ngoài dòng khai đơn vị THẬT của nó (`bai → kem`) và "có nằm trên dòng
        # giấy không" hỏi cờ `don_vi_do.tram_dong_giay`. Cờ ấy đã gỡ: nó chỉ cho ĐỔI TÊN một chặng
        # chứ không thêm được chặng thứ 6, đổi lại bắt người khai danh mục đơn vị (kho, mua hàng)
        # phải hiểu dòng giấy. Nay bỏ trống chính là câu "ngoài dòng giấy" — nói thẳng, một ô.
        #
        # GỠ 18/09/2026 (mg `0324`): "Công thức sản lượng ra" + "Đơn vị sản lượng" của bước ngoài
        # dòng giấy, kèm luật chặn vòng tròn `sl_vao`/`sl_ra` trong công thức ấy.
        dv_vao = (data.get("don_vi_vao") or "").strip() or None
        dv_ra = (data.get("don_vi_ra") or "").strip() or None
        data["don_vi_vao"], data["don_vi_ra"] = dv_vao, dv_ra
        if (dv_vao is None) != (dv_ra is None):
            raise CongDoanValidationError(
                "Đơn vị đầu vào và đầu ra phải cùng khai, hoặc cùng để trống. [E-CD-DONVI]")
        if dv_vao is not None:
            if la := [m for m in dict.fromkeys((dv_vao, dv_ra)) if m not in TRAM_DONG_GIAY]:
                raise CongDoanValidationError(
                    f"Đơn vị {' · '.join(la)} không nằm trên dòng giấy. Ô đơn vị của công đoạn "
                    f"chỉ nhận 5 chặng: tờ nguyên · tờ in · con · tay sách · thành phẩm — hoặc "
                    f"để TRỐNG cả hai nếu bước không chạm giấy. [E-CD-DONVI]")
            if not tram_chay_xuoi(dv_vao, dv_ra):
                raise CongDoanValidationError(
                    f"Không quy đổi được {dv_vao} → {dv_ra}. Dòng giấy chỉ chảy một chiều: "
                    f"tờ nguyên → tờ in → con/tay → thành phẩm. [E-CD-DONVI]"
                )
        # W-CD-PRINT-SPOIL: bước in không nên có spoilage (bù hao lấy từ máy) — ép 0.
        if data.get("nhom") == "print" and data.get("spoilage_pct"):
            data["spoilage_pct"] = 0
        # Công thức phải CHẠY ĐƯỢC mới cho lưu (07/09/2026) — trước đây không ô công thức nào của
        # công đoạn bị soi ở server. Kiểm cuối cùng để câu lỗi cú pháp không chen trước những câu
        # lỗi nghiệp vụ cụ thể hơn (chiều dòng giấy) — người khai cần nghe cái bệnh nặng trước.
        self._kiem_o(data.get("cong_thuc_gia"), nhan="Công thức tính giá", loai=LOAI_CONG_DOAN)

    @staticmethod
    def _kiem_o(cong_thuc: str | None, *, nhan: str, loai: str) -> None:
        """Một ô công thức — xem `thanh_phan_engine.kiem_cong_thuc`. Đổi sang họ lỗi của màn này
        để `loi_http` trả 422 kèm câu chữ cho người khai, không lọt thành 500."""
        try:
            kiem_cong_thuc(cong_thuc, nhan=nhan, loai=loai)
        except ValueError as e:
            raise CongDoanValidationError(str(e)) from e

    @staticmethod
    def _vat_tu_dang_co(obj: CongDoan | None) -> set[int]:
        """Vật tư ĐÃ khai trên công đoạn này — để `_kiem_vat_tu` biết cái nào là giữ lại chứ
        không phải gán mới. Rỗng khi tạo mới."""
        return {
            int(v.vat_tu_id)
            for v in (getattr(obj, "vat_tus", None) or [])
            if v.vat_tu_id
        }

    def _kiem_vat_tu(self, rows: list[dict], dang_co: set[int] | None = None) -> None:
        """Vật tư gắn vào CÔNG ĐOẠN (nền BOM, mg 0191 → chuyển tầng mg `0316`) — id phải có thật
        và còn dùng.

        Vật tư đã ngừng dùng mà lọt vào đây thì tới lúc bung ở bước lệnh nó sẽ rơi im lặng (query
        bung lọc `active`), và người khai không hiểu vì sao dòng mình khai không hiện ra.
        Chỉ kiểm DANH SÁCH — số lượng không khai ở tầng này, mỗi dòng chỉ mang CÔNG THỨC định
        mức (`cong_thuc_luong`), số suy lúc bung theo quy cách lệnh.

        `dang_co` = vật tư vốn đã khai trên công đoạn này. Chặn GÁN MỚI vật tư đã ngừng, nhưng
        không chặn khi giữ nguyên: nếu không thì đổi mỗi cái tên công đoạn cũng bị chặn chỉ vì một
        vật tư trong đó đã ngừng từ lâu, và người dùng không có đường nào sửa nữa.
        """
        ids = [int(r["vat_tu_id"]) for r in rows if r.get("vat_tu_id")]
        if not ids:
            return
        if len(ids) != len(set(ids)):
            raise CongDoanValidationError("Một vật tư không được chọn trùng trong công đoạn.")
        can = set(ids)
        co = self.repo.vat_tus(can)
        giu = dang_co or set()
        for vid in sorted(can):
            vt = co.get(vid)
            if vt is None:
                raise CongDoanValidationError("Vật tư không tồn tại hoặc đã ngừng sử dụng.")
            if not vt.active and vid not in giu:
                raise CongDoanValidationError(
                    f"Vật tư “{vt.ten}” đã ngừng dùng — chọn vật tư khác, "
                    f"hoặc bật lại ở màn Vật tư khác.")
            if not (vt.don_vi_gia or "").strip():
                raise CongDoanValidationError(
                    f"Vật tư “{vt.ten}” chưa chọn đơn vị tính — chưa quy đổi ra số lượng được. "
                    f"Khai đơn vị ở màn Vật tư khác trước.")
        # Ô công thức của TỪNG DÒNG vật tư (mg 0274) — soi ở đây vì chỉ chỗ này có tên vật tư để
        # gọi trong câu lỗi; một công đoạn gắn nhiều món, không nói tên là bắt người khai dò.
        # Chuẩn hoá luôn: khoảng trắng thừa làm `if cong_thuc:` ở engine tưởng có khai rồi
        # `safe_eval("  ")` nổ.
        for r in rows:
            r["cong_thuc_luong"] = ((r.get("cong_thuc_luong") or "").strip()) or None
            ten_vt = getattr(co.get(int(r["vat_tu_id"])), "ten", "")
            self._kiem_o(r.get("cong_thuc_luong"),
                         nhan=f"Công thức định mức của vật tư “{ten_vt}”", loai=LOAI_QUY_DOI)

    # GỠ 08/09/2026: `gan_ten_don_vi` — tra `don_vi_vao`/`don_vi_ra` vào danh mục Đơn vị & quy đổi
    # rồi gán `don_vi_vao_ten`/`don_vi_ra_ten`. Nó ra đời (12/08/2026) khi hai ô ấy CÒN trỏ danh
    # mục, và mục đích là dẹp một bảng nhãn cứng bên frontend đang lệch với danh mục.
    #
    # Từ mg `0273` (06/09/2026) hai ô đó KHÔNG còn trỏ danh mục nữa: chúng là menu ĐÓNG đúng 5
    # chặng dòng giấy (`TRAM_DONG_GIAY`). Phép tra ở lại thành ra lấy tên của một đơn vị KHO tình
    # cờ trùng mã, nên đúng cái lỗi hàm này từng dẹp lại quay về — chỉ đảo vai: danh sách hiện
    # "con → cái" (tên đơn vị kho) còn drawer hiện "Con (mảnh bế ra) → Thành phẩm" (nhãn chặng).
    # Tệ hơn: ai đổi tên đơn vị `con` ở màn Kho là chữ trong cột Đơn vị của màn Công đoạn đổi theo,
    # dù dòng giấy chẳng liên quan gì.
    #
    # Nay CHẶNG chỉ có một bộ nhãn (`models/don_vi_do.TRAM_NHAN`, frontend soi `TRAM_DONG_GIAY`),
    # server thôi gửi tên.

    def dem_theo_nhom(self, **kw) -> dict[str, int]:
        """Số công đoạn theo giai đoạn — cho tab lọc của màn Công đoạn (xem repo)."""
        return self.repo.dem_theo_nhom(**kw)

    def phong_ban_options(self) -> list[dict]:
        """TỔ cho dropdown 'Phòng ban / Tổ phụ trách' ở form Công đoạn (`{id, ma, ten}`).

        Dùng ĐỊNH NGHĨA CHUNG `to_san_xuat()` = nút LÁ trong nhánh Khối Sản xuất (mục H). Trước
        đây endpoint này đổ CẢ CHA LẪN CON, nên người khai chọn được "Xưởng in" (một tầng giữa)
        làm tổ phụ trách — và quỹ giờ-người ở bàn xếp lịch đếm chồng quân số của chính tổ con.

        ⚠️ KHÔNG phá dữ liệu cũ: công đoạn đã trỏ nút cha thì GIỮ NGUYÊN giá trị đó, chỉ kèm nhãn
        "(không còn là tổ)" để người khai biết mà sửa dần. Không tự xoá, không chặn lưu, không
        đụng lệnh đang chạy — đổi định nghĩa mà đi dọn dữ liệu người ta là tự ý sửa số liệu vận
        hành.

        Ở tầng service chứ không phải router (trước 15/08/2026 nó nằm trong
        `routers/cong_doan.list_phong_ban_options`, và router tự dựng hai repository).
        """
        tos = self.repo.phong_ban_tos()
        items = [{"id": d.id, "ma": d.code, "ten": d.name} for d in tos]
        con_thieu = self.repo.department_ids_dang_dung() - {d.id for d in tos}
        if con_thieu:
            items.extend(
                {"id": d.id, "ma": d.code, "ten": f"{d.name} (không còn là tổ)"}
                for d in self.repo.phong_ban_tat_ca() if d.id in con_thieu
            )
        return items

    # ⚠️ `dau_viec_options()` GỠ 18/09/2026 (mg `0320`): bảng "Đầu việc và định mức của tổ" đã
    #    biến khỏi drawer Công đoạn nên không còn dropdown nào cần đổ. Việc khoán của tổ nay đọc ở
    #    bàn tổ lúc ghi mẻ (`san_xuat/san_luong.viec_khoan_cua_to`).
