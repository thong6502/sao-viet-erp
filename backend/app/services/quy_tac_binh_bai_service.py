"""Service — Quy tắc bình bài. Validate + integrity §12 + audit + preview (gọi engine §5/§6).

Sửa cấu hình = LUÔN đẻ version mới (không sửa đè). Header chỉ giữ danh tính; ma bất biến.
"""
from __future__ import annotations

from ..models.quy_tac_binh_bai import (
    GRAIN_CONSTRAINTS,
    LAYOUT_MODES,
    TRANG_THAI,
    WORK_STYLES,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.quy_tac_binh_bai_repo import QuyTacBinhBaiRepository
from . import imposition_engine as E

_NON_NEG = ("side_margin_mm", "tail_colorbar_mm", "gutter_mm", "bleed_default_mm",
           "min_gutter_mm", "matrix_allowance_mm")


class QuyTacBinhBaiError(Exception):
    pass


class ValidationError(QuyTacBinhBaiError):
    pass


class DuplicateError(QuyTacBinhBaiError):
    pass


class NotFoundError(QuyTacBinhBaiError):
    pass


class QuyTacBinhBaiService:
    def __init__(self, repo: QuyTacBinhBaiRepository, audit: AuditLogRepository) -> None:
        self.repo = repo
        self.audit = audit

    # -- validation --------------------------------------------------------
    def _validate_header(self, ma: str | None, ten: str, trang_thai: str | None,
                         *, require_ma: bool) -> None:
        if require_ma and not (ma or "").strip():
            raise ValidationError("Mã quy tắc không được trống.")
        if not (ten or "").strip():
            raise ValidationError("Tên quy tắc không được trống.")
        if trang_thai is not None and trang_thai not in TRANG_THAI:
            raise ValidationError("Trạng thái không hợp lệ.")

    def _validate_config(self, cfg: dict) -> None:
        if cfg.get("layout_mode") not in LAYOUT_MODES:
            raise ValidationError("layout_mode không hợp lệ.")
        if cfg.get("grain_constraint", "none") not in GRAIN_CONSTRAINTS:
            raise ValidationError("Ràng buộc thớ không hợp lệ.")
        if cfg.get("work_style", "sheetwise") not in WORK_STYLES:
            raise ValidationError("Kiểu trở (work_style) không hợp lệ.")
        pps = cfg.get("pages_per_sig")
        if pps is not None and int(pps) not in (4, 8, 16, 32):
            raise ValidationError("Trang mỗi tay phải là 4/8/16/32 (hoặc để trống = auto).")
        for f in _NON_NEG:
            v = cfg.get(f)
            if v is not None and float(v) < 0:
                raise ValidationError(f"Tham số '{f}' không được âm.")
        mn, mx = cfg.get("min_pages"), cfg.get("max_pages")
        if mn is not None and mx is not None and int(mx) < int(mn):
            raise ValidationError("max_pages phải ≥ min_pages.")

    # -- reads -------------------------------------------------------------
    def list_items(self, *, q=None, trang_thai=None, page=1, size=50):
        rows, total = self.repo.list_headers(q=q, trang_thai=trang_thai, page=page, size=size)
        return rows, total

    def get_header(self, rule_id: int):
        h = self.repo.get_header(rule_id)
        if h is None:
            raise NotFoundError("Không tìm thấy quy tắc bình bài.")
        return h

    def current_version(self, rule_id: int):
        return self.repo.current_version(rule_id)

    def version_count(self, rule_id: int) -> int:
        return self.repo.version_count(rule_id)

    def versions_of(self, rule_id: int):
        return self.repo.versions_of(rule_id)

    # -- writes ------------------------------------------------------------
    def create_item(self, data: dict, *, actor):
        ma = (data.get("ma") or "").strip().upper()
        ten = data.get("ten") or ""
        self._validate_header(ma, ten, None, require_ma=True)
        cfg = dict(data.get("config") or {})
        self._validate_config(cfg)
        if self.repo.find_by_ma(ma) is not None:
            raise DuplicateError("Mã quy tắc bình bài đã tồn tại.")
        header = self.repo.create_rule(ma=ma, ten=ten, mo_ta=data.get("mo_ta"),
                                       config=cfg, actor_id=getattr(actor, "id", None))
        self._audit(actor, "create_binh_bai", header.id, f"{header.ma} - {header.ten}")
        return header

    def update_header(self, rule_id: int, data: dict, *, actor):
        header = self.get_header(rule_id)
        ten = data.get("ten") or header.ten
        self._validate_header(None, ten, data.get("trang_thai"), require_ma=False)
        header = self.repo.update_header(header, ten=ten, mo_ta=data.get("mo_ta"),
                                         trang_thai=data.get("trang_thai"))
        self._audit(actor, "update_binh_bai", header.id, f"{header.ma} - {header.ten}")
        return header

    def create_version(self, rule_id: int, data: dict, *, actor):
        header = self.get_header(rule_id)
        cfg = dict(data.get("config") or {})
        self._validate_config(cfg)
        nv = self.repo.new_version(rule_id=rule_id, config=cfg,
                                   ghi_chu=data.get("ghi_chu_version"),
                                   actor_id=getattr(actor, "id", None))
        self._audit(actor, "version_binh_bai", header.id,
                    f"{header.ma} v{nv.version_no}")
        return nv

    def delete_item(self, *, rule_id: int, actor):
        header = self.get_header(rule_id)
        # §4.3/§12.5: chỉ xoá khi không có SP gán VÀ không báo giá ghim — cả hai chưa tồn tại
        # (link Loại SP = Phase 6, ghim báo giá = Phase 7). Khi build 2 pha đó, thêm guard ở ĐÂY:
        #   if self._has_product_assignments(rule_id) or self._has_quote_pins(rule_id):
        #       raise ValidationError("Đang được tham chiếu — hãy tạm ngưng (inactive) thay vì xoá.")
        ma, ten = header.ma, header.ten
        self.repo.delete_rule(header)
        self._audit(actor, "delete_binh_bai", rule_id, f"{ma} - {ten}")

    # -- preview (Bảng thử → engine §6) ------------------------------------
    def preview(self, config: dict, bench: dict) -> dict:
        self._validate_config(config)
        rule = self._to_rule(config)
        machine = E.Machine(
            gripper_mm=_f(bench.get("gripper_mm"), 12), max_w=_f(bench.get("max_w")),
            max_h=_f(bench.get("max_h")), min_w=_f(bench.get("min_w")), min_h=_f(bench.get("min_h")),
        )
        product = E.Product(
            rong_tp=_f(bench.get("rong_tp")), dai_tp=_f(bench.get("dai_tp")),
            bleed_mm=_f_opt(bench.get("bleed_mm")), so_trang=_i_opt(bench.get("so_trang")),
            binding=bench.get("binding") or None, cover_separate=bool(bench.get("cover_separate")),
            blank_w=_f_opt(bench.get("blank_w")), blank_h=_f_opt(bench.get("blank_h")),
            caliper_mm=_f_opt(bench.get("caliper_mm")),
        )
        raw = E.RawSheet(
            rong_ng=_f(bench.get("rong_ng")), dai_ng=_f(bench.get("dai_ng")),
            gsm=_f(bench.get("gsm")), gia_kg=_f(bench.get("gia_kg")), tho=bench.get("tho") or "none",
        )
        res = E.resolve(rule, machine, product, raw,
                        so_luong=_i(bench.get("so_luong")),
                        so_mau_truoc=_i(bench.get("so_mau_truoc"), 4),
                        so_mau_sau=_i(bench.get("so_mau_sau")))
        return _result_to_dict(res)

    @staticmethod
    def _to_rule(cfg: dict) -> "E.RuleVersion":
        fields = {f.name for f in E.RuleVersion.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return E.RuleVersion(**{k: v for k, v in cfg.items() if k in fields})

    def _audit(self, actor, action: str, target_id: int, detail: str) -> None:
        try:
            self.audit.create(actor_user_id=getattr(actor, "id", None), action=action,
                              target=f"quy_tac_binh_bai:{target_id}", detail=detail)
        except Exception:
            pass


# -- helpers ---------------------------------------------------------------
def _f(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _f_opt(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else int(default)
    except (TypeError, ValueError):
        return int(default)


def _i_opt(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _result_to_dict(res: "E.ImpositionResult") -> dict:
    ks = res.kho_to_in
    return {
        "layout_mode": res.layout_mode,
        "kho_to_in": ({"rong": ks.rong, "dai": ks.dai, "kieu_cat": ks.kieu_cat,
                       "per_nguyen": ks.per_nguyen} if ks else None),
        "don_vi_per_to_in": res.don_vi_per_to_in,
        "to_in_per_nguyen": res.to_in_per_nguyen,
        "tong_don_vi_per_nguyen": res.tong_don_vi_per_nguyen,
        "so_kem": res.so_kem,
        "hao_hinh_hoc_pct": res.hao_hinh_hoc_pct,
        "so_to_in": res.so_to_in,
        "so_to_nguyen": res.so_to_nguyen,
        "so_tay": res.so_tay,
        "danh_sach_tay": res.danh_sach_tay,
        "spine_mm": res.spine_mm,
        "creep_mm": res.creep_mm,
        "warnings": [{"code": w.code, "message": w.message, "severity": w.severity}
                     for w in res.warnings],
    }
