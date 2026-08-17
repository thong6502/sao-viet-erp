"""Service Vấn đề kế hoạch — danh sách XUNG ĐỘT & NGUY CƠ TRỄ + duyệt/xử lý + gate PHÁT HÀNH.

Bàn kiểm soát cuối trước khi thả kế hoạch xuống xưởng (bám BC Planning Worksheet: cảnh báo + action
message recompute mỗi lần đọc, KHÔNG lưu). Vấn đề là DẪN XUẤT từ `XepLichService.danh_sach()` (đã tính
sẵn cờ trùng máy / nhãn nguy cơ / bị chặn / cần xác nhận) cùng các detector đè khóa máy và sai tiền
nhiệm. Chỉ PHẦN CON NGƯỜI XỬ LÝ lưu ở `xep_lich_van_de` (neo `issue_key`); lịch sử dùng
AuditLog. Máy-chỉ-ghi-nhận: máy phát hiện + tính trễ + gợi ý; người Tiếp nhận rồi mới xử lý/duyệt ngoại lệ.

Phân mức: Chặn (bắt buộc xử lý trước phát hành) · Nghiêm trọng · Cao · Cảnh báo. `da_phat_hanh`
(≈ Released) chỉ set khi entity hết xung đột Chặn CHƯA ngoại lệ.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import (
    TT_DA_LAP_KE_HOACH as BG_DA_LAP, TT_DA_PHAT_HANH as BG_DA_PHAT_HANH, BaiGhep, BaiGhepThanhVien,
)
from ..models.lsx import (
    LB_THUE_NGOAI, TT_DA_LAP_KE_HOACH as LSX_DA_LAP,
    TT_DA_PHAT_HANH as LSX_DA_PHAT_HANH, Lsx,
)
from ..models.xep_lich_van_de import (
    TT_DANG_XU_LY, TT_DA_XU_LY, TT_MOI, TT_NGOAI_LE, TT_TAM_HOAN, TT_TIEP_NHAN,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.xep_lich_repo import XepLichRepository
from ..repositories.xep_lich_van_de_repo import XepLichVanDeRepository
from .xep_lich_service import (
    PHUT_LAM_NGAY, XepLichConflict, XepLichNotFound, XepLichService,
    _aware, _cuoi_ngay, _dau_ngay, _naive, _utcnow,
)

# --- Mức nghiêm trọng (4 mức; Chặn = chặn phát hành) ---
SEV_CHAN = "chan"
SEV_NGHIEM_TRONG = "nghiem_trong"
SEV_CAO = "cao"
SEV_CANH_BAO = "canh_bao"
SEV_ORDER = {SEV_CHAN: 0, SEV_NGHIEM_TRONG: 1, SEV_CAO: 2, SEV_CANH_BAO: 3}

# --- Nhóm vấn đề ---
CAT_TRUNG_MAY = "trung_may"
CAT_DE_KHOA_MAY = "de_khoa_may"
CAT_SAI_TIEN_NHIEM = "sai_tien_nhiem"
CAT_THIEU_DU_LIEU = "thieu_du_lieu"
CAT_NGUY_CO_TRE = "nguy_co_tre"
CAT_MAY_KHONG_KHAM = "may_khong_kham"
CAT_QUA_TAI_MAY = "qua_tai_may"
CAT_HAN_BAI_GHEP = "han_bai_ghep"
CAT_THUE_NGOAI = "thue_ngoai"
# --- Đợt 2 (2026-08-09) ---
CAT_THIEU_VAT_TU = "thieu_vat_tu"            # F: bảng cân đối có dòng đỏ cho lệnh/bài này
CAT_THIEU_NGUOI = "thieu_nguoi"              # G: tổ bố trí dưới số người tối thiểu
CAT_QUA_TAI_TO = "qua_tai_to"                # I: Σ người các việc cùng lúc > quân số có mặt của tổ

# §3.1 ngưỡng tải máy trên CỬA SỔ TRƯỢT (§6 dùng hằng cấu hình thay bảng planning_issue_rules):
# 85–100% → Cảnh báo, >100% → Cao. Cửa sổ = số ngày tới tính từ hôm nay.
TAI_CUA_SO_NGAY = 7
TAI_PCT_CAO = 100.0
TAI_PCT_CANH_BAO = 85.0

_RUI_RO_SEV = {"da_tre": SEV_NGHIEM_TRONG, "nguy_co_tre": SEV_CAO, "sap_toi_han": SEV_CANH_BAO}
_RUI_RO_RANK = {"da_tre": 0, "nguy_co_tre": 1, "sap_toi_han": 2, "an_toan": 3, "chua_co_han": 4}
_RUI_RO_LABEL = {"da_tre": "đã trễ", "nguy_co_tre": "nguy cơ trễ", "sap_toi_han": "sắp tới hạn"}
_XN_LABEL = {"kho_vuot_may": "khổ vượt máy", "so_mau_vuot_units": "số màu vượt máy",
             "gsm_ngoai_khoang": "định lượng ngoài khoảng máy"}


def _fmt(dt) -> str:
    """Mốc → 'dd/mm HH:MM' theo giờ nhà máy (bỏ tz để hiển thị wall-clock)."""
    a = _aware(dt)
    if a is None:
        return "—"
    return a.replace(tzinfo=None).strftime("%d/%m %H:%M")


def _phut_str(phut: float) -> str:
    t = int(round(phut or 0))
    if t <= 0:
        return "0 phút"
    gio, p = divmod(t, 60)
    if gio and p:
        return f"{gio} giờ {p} phút"
    return f"{gio} giờ" if gio else f"{p} phút"


def _overlap_phut(s1, e1, s2, e2) -> float:
    lo, hi = max(s1, s2), min(e1, e2)
    return (hi - lo).total_seconds() / 60.0 if hi > lo else 0.0


def _uniq(xs: list) -> list:
    out: list = []
    for x in xs:
        if x is not None and x not in out:
            out.append(x)
    return out


class XepLichVanDeService:
    """Dẫn xuất danh sách vấn đề + neo state người xử lý + gate phát hành."""

    def __init__(self, db: Session, audit: AuditLogRepository | None = None) -> None:
        self.db = db
        self.audit = audit or AuditLogRepository(db)
        self.xl = XepLichService(db, XepLichRepository(db), self.audit)
        self.repo = XepLichVanDeRepository(db)
        # Cache trong VÒNG ĐỜI service (= một request): bảng cân đối vật tư đắt, mà `_build()`
        # chạy hai lượt mỗi lần mở bàn xếp lịch. Xem `_can_doi_vat_tu`.
        self._kh_vt = None
        self._kh_vt_bang: dict | None = None

    # ================= DẪN XUẤT DANH SÁCH VẤN ĐỀ =================

    def _impact(self, rows: list[dict], *, extra_bg: list[int] | None = None) -> dict:
        return {
            "lsx_ids": _uniq([r.get("lsx_id") for r in rows]),
            "bai_ghep_ids": _uniq([r.get("bai_ghep_id") for r in rows] + (extra_bg or [])),
            "may_ids": _uniq([r.get("may_id") for r in rows]),
            "dong_ids": _uniq([r.get("id") for r in rows]),
            "mas": _uniq([r.get("lsx_ma") for r in rows]),
        }

    def _build(self) -> list[dict]:
        """Mọi vấn đề dẫn xuất (chưa lọc), đã trộn state người xử lý."""
        rows = self.xl.danh_sach()["items"]
        issues: list[dict] = []
        issues += self._trung_may(rows)
        issues += self._de_khoa_may(rows)
        issues += self._sai_tien_nhiem(rows)
        issues += self._thieu_du_lieu(rows)
        issues += self._nguy_co_tre(rows)
        issues += self._may_khong_kham(rows)
        issues += self._qua_tai_may(rows)
        issues += self._han_som_bai_ghep(rows)
        issues += self._thue_ngoai(rows)
        issues += self._thieu_nguoi(rows)
        issues += self._qua_tai_to(rows)
        issues += self._thieu_vat_tu(rows)
        self._merge_state(issues)
        return issues

    def liet_ke(self, *, severity: str | None = None, category: str | None = None,
                trang_thai: str | None = None, lsx_id: int | None = None,
                may_id: int | None = None) -> dict:
        issues = self._build()

        def keep(it: dict) -> bool:
            if severity and it["severity"] != severity:
                return False
            if category and it["category"] != category:
                return False
            if trang_thai and it["trang_thai"] != trang_thai:
                return False
            if lsx_id and lsx_id not in it["impacts"]["lsx_ids"]:
                return False
            if may_id and may_id not in it["impacts"]["may_ids"]:
                return False
            return True

        vis = [it for it in issues if keep(it)]
        vis.sort(key=lambda it: (SEV_ORDER[it["severity"]], it["category"], it["issue_key"]))
        return {"items": vis, "summary": self._summary(issues), "total": len(vis)}

    def _summary(self, issues: list[dict]) -> dict:
        def n(sev: str) -> int:
            return sum(1 for it in issues if it["severity"] == sev and it["trang_thai"] != TT_NGOAI_LE)
        return {
            "chan": n(SEV_CHAN),
            "nghiem_trong": n(SEV_NGHIEM_TRONG),
            "cao": n(SEV_CAO),
            "canh_bao": n(SEV_CANH_BAO),
            "ngoai_le": sum(1 for it in issues if it["trang_thai"] == TT_NGOAI_LE),
            "tong": len(issues),
        }

    def _merge_state(self, issues: list[dict]) -> None:
        sm = self.repo.get_map([it["issue_key"] for it in issues])
        for it in issues:
            st = sm.get(it["issue_key"])
            if st is None:
                it.update(trang_thai=TT_MOI, assigned_to=None, note=None, tai_phat=0,
                          mo_lai=False, exception=None)
                continue
            # Vấn đề vẫn dẫn xuất mà state = đã xử lý → nó TÁI PHÁT: hiện lại như cần xử lý.
            eff = st.trang_thai
            mo_lai = False
            if st.trang_thai == TT_DA_XU_LY:
                eff, mo_lai = TT_TIEP_NHAN, True
            it.update(
                trang_thai=eff, assigned_to=st.assigned_to, note=st.note,
                tai_phat=st.tai_phat, mo_lai=mo_lai,
                exception=(
                    {"ly_do": st.exception_ly_do, "by": st.exception_by,
                     "expires_at": _naive(st.exception_expires_at)}
                    if st.trang_thai == TT_NGOAI_LE else None
                ),
            )

    # ---- Detector: các dòng đã xếp có máy + giờ ----
    @staticmethod
    def _da_xep_co_may(rows: list[dict]) -> list[dict]:
        return [r for r in rows
                if r["trang_thai"] == "da_xep" and r["may_id"] and r["start_at"] and r["finish_at"]]

    def _trung_may(self, rows: list[dict]) -> list[dict]:
        """Hai công đoạn chồng giờ trên cùng một máy (Chặn). NETRONIC: gạch chân đỏ."""
        by_may: dict[int, list[dict]] = {}
        for r in self._da_xep_co_may(rows):
            by_may.setdefault(r["may_id"], []).append(r)
        out: list[dict] = []
        for mid, rs in by_may.items():
            rs.sort(key=lambda r: _aware(r["start_at"]))
            for i in range(len(rs)):
                a = rs[i]
                sa, ea = _aware(a["start_at"]), _aware(a["finish_at"])
                for j in range(i + 1, len(rs)):
                    b = rs[j]
                    sb, eb = _aware(b["start_at"]), _aware(b["finish_at"])
                    if sb >= ea:
                        break  # sort theo start: b này và sau đều bắt đầu ≥ kết thúc của a
                    ov = _overlap_phut(sa, ea, sb, eb)
                    if ov <= 0:
                        continue
                    lo, hi = (a, b) if a["id"] <= b["id"] else (b, a)
                    out.append({
                        "issue_key": f"{CAT_TRUNG_MAY}:{mid}:{lo['id']}:{hi['id']}",
                        "category": CAT_TRUNG_MAY, "severity": SEV_CHAN,
                        "title": (f"{a['lsx_ma']} · {a['cong_doan_ten']} ({_fmt(sa)}–{_fmt(ea)}) "
                                  f"trùng {b['lsx_ma']} · {b['cong_doan_ten']} ({_fmt(sb)}–{_fmt(eb)}) "
                                  f"trên {a['may_ten']} — {_phut_str(ov)}"),
                        "nguyen_nhan": "Hai công đoạn cùng chiếm một máy trong khoảng thời gian chồng nhau.",
                        "impacts": self._impact([a, b]),
                        "delay_phut": round(ov),
                        "group_key": f"may:{mid}",
                    })
        return out

    def _de_khoa_may(self, rows: list[dict]) -> list[dict]:
        """Công đoạn xếp đè vùng khóa/bảo trì máy (Chặn) — engine né khi tính giờ nhưng không bắt
        khi người gán start_at rơi vào giữa vùng khóa."""
        periods: dict[int, list] = {}
        out: list[dict] = []
        for r in self._da_xep_co_may(rows):
            mid = r["may_id"]
            if mid not in periods:
                periods[mid] = self.xl.unavail_repo.list_by_may(mid)
            s, e = _aware(r["start_at"]), _aware(r["finish_at"])
            for p in periods[mid]:
                ps, pe = _aware(p.unavailable_from), _aware(p.unavailable_to)
                ov = _overlap_phut(s, e, ps, pe)
                if ov <= 0:
                    continue
                out.append({
                    "issue_key": f"{CAT_DE_KHOA_MAY}:{r['id']}:{p.id}",
                    "category": CAT_DE_KHOA_MAY, "severity": SEV_CHAN,
                    "title": (f"{r['lsx_ma']} · {r['cong_doan_ten']} xếp {_fmt(s)}–{_fmt(e)} đè vùng "
                              f"khóa máy {r['may_ten']} ({p.reason}) {_fmt(ps)}–{_fmt(pe)}"),
                    "nguyen_nhan": "Công đoạn được xếp vào khoảng máy đang bảo trì/khóa.",
                    "impacts": self._impact([r]),
                    "delay_phut": round(ov),
                    "group_key": f"khoa:{mid}:{p.id}",
                })
        return out

    def _sai_tien_nhiem(self, rows: list[dict]) -> list[dict]:
        """Công đoạn xếp bắt đầu TRƯỚC khi bước trước xong (sớm nhất) — sai thứ tự routing (Chặn)."""
        out: list[dict] = []
        for r in rows:
            if r["nguon"] != "lsx" or not r["start_at"] or not r["som_nhat"]:
                continue
            st, som = _aware(r["start_at"]), _aware(r["som_nhat"])
            gap = (som - st).total_seconds() / 60.0
            if gap <= 1:  # cho phép sai số làm tròn 1 phút
                continue
            out.append({
                "issue_key": f"{CAT_SAI_TIEN_NHIEM}:{r['id']}",
                "category": CAT_SAI_TIEN_NHIEM, "severity": SEV_CHAN,
                "title": (f"{r['lsx_ma']} · {r['cong_doan_ten']} xếp {_fmt(st)} nhưng bước trước xong "
                          f"lúc {_fmt(som)} — sớm hơn {_phut_str(gap)}"),
                "nguyen_nhan": "Công đoạn sau được xếp bắt đầu trước khi công đoạn trước kết thúc.",
                "impacts": self._impact([r]),
                "delay_phut": None,
                "group_key": f"lsx:{r['lsx_id']}",
            })
        return out

    def _thieu_du_lieu(self, rows: list[dict]) -> list[dict]:
        """Bước BẮT BUỘC thiếu dữ liệu để xếp (chưa gán máy / chưa khai năng suất) — Chặn."""
        out: list[dict] = []
        for r in rows:
            if r["blocked_reason"] not in ("thieu_may", "thieu_thoi_luong"):
                continue
            orm = self.xl.repo.get(r["id"])
            lcd = self.xl._lcd(orm.lsx_cong_doan_id) if orm else None
            # in_ghep (lcd None) = in chung bắt buộc; bước nội bộ theo cờ bat_buoc.
            if lcd is not None and not lcd.bat_buoc:
                continue
            txt = ("chưa gán máy/tổ" if r["blocked_reason"] == "thieu_may"
                   else "chưa khai năng suất → không tính được thời lượng")
            out.append({
                "issue_key": f"{CAT_THIEU_DU_LIEU}:{r['id']}",
                "category": CAT_THIEU_DU_LIEU, "severity": SEV_CHAN,
                "title": f"{r['lsx_ma']} · {r['cong_doan_ten']}: {txt}",
                "nguyen_nhan": "Công đoạn bắt buộc thiếu dữ liệu nên không lên được lịch.",
                "impacts": self._impact([r]),
                "delay_phut": None,
                "group_key": (f"lsx:{r['lsx_id']}" if r["lsx_id"] else f"bai_ghep:{r['bai_ghep_id']}"),
            })
        return out

    def _nguy_co_tre(self, rows: list[dict]) -> list[dict]:
        """Nguy cơ trễ gom theo LSX (mức xấu nhất trong chuỗi): da_tre→Nghiêm trọng, nguy_co_tre→Cao,
        sap_toi_han→Cảnh báo. NETRONIC: kẻ sọc trễ hạn."""
        by_lsx: dict[int, list[dict]] = {}
        for r in rows:
            if r["nguon"] == "lsx" and r["lsx_id"]:
                by_lsx.setdefault(r["lsx_id"], []).append(r)
        out: list[dict] = []
        for lid, rs in by_lsx.items():
            risky = [r for r in rs if r["nhan_rui_ro"] in _RUI_RO_SEV]
            if not risky:
                continue
            worst = min(risky, key=lambda r: _RUI_RO_RANK.get(r["nhan_rui_ro"], 9))["nhan_rui_ro"]
            slacks = [r["slack_ngay"] for r in rs if r["slack_ngay"] is not None]
            min_slack = min(slacks) if slacks else None
            delay = (abs(min_slack) * PHUT_LAM_NGAY) if (min_slack is not None and min_slack < 0) else None
            slack_txt = f" (độ dư {min_slack:+d}d)" if min_slack is not None else ""
            out.append({
                "issue_key": f"{CAT_NGUY_CO_TRE}:{lid}",
                "category": CAT_NGUY_CO_TRE, "severity": _RUI_RO_SEV[worst],
                "title": f"{rs[0]['lsx_ma']}: {_RUI_RO_LABEL[worst]}{slack_txt}",
                "nguyen_nhan": "Dự kiến hoàn thành so với hạn cho thấy lệnh có nguy cơ trễ.",
                "impacts": self._impact(rs),
                "delay_phut": round(delay) if delay else None,
                "group_key": f"lsx:{lid}",
            })
        return out

    def _may_khong_kham(self, rows: list[dict]) -> list[dict]:
        """Máy đang gán có thể không kham nổi công đoạn (khổ/số màu/định lượng) — Cao (soft, người quyết)."""
        out: list[dict] = []
        for r in rows:
            if not r["can_xac_nhan"]:
                continue
            ly = ", ".join(_XN_LABEL.get(x, x) for x in (r["ly_do_xac_nhan"] or []))
            out.append({
                "issue_key": f"{CAT_MAY_KHONG_KHAM}:{r['id']}",
                "category": CAT_MAY_KHONG_KHAM, "severity": SEV_CAO,
                "title": f"{r['lsx_ma']} · {r['cong_doan_ten']}: máy {r['may_ten']} có thể không kham ({ly})",
                "nguyen_nhan": "Thông số máy đang gán vượt spec công đoạn — cần xác nhận hoặc đổi máy.",
                "impacts": self._impact([r]),
                "delay_phut": None,
                "group_key": f"may:{r['may_id']}",
            })
        return out

    def _qua_tai_may(self, rows: list[dict]) -> list[dict]:
        """Tổng giờ đã xếp / giờ khả dụng của 1 máy trong CỬA SỔ 7 ngày tới (Cao/Cảnh báo). Khác
        trùng-máy: từng thanh Gantt chưa chồng nhau nhưng TỔNG tải vượt công suất → nguy cơ trễ."""
        today = _utcnow().date()
        den = today + timedelta(days=TAI_CUA_SO_NGAY - 1)
        win_s, win_e = _dau_ngay(today), _dau_ngay(today + timedelta(days=TAI_CUA_SO_NGAY))
        by_may: dict[int, list[dict]] = {}
        for r in self._da_xep_co_may(rows):
            by_may.setdefault(r["may_id"], []).append(r)
        out: list[dict] = []
        for mid, rs in by_may.items():
            # Giờ đã xếp = Σ giờ CHIẾM MÁY của các dòng BẮT ĐẦU trong cửa sổ (cùng đơn vị "giờ làm"
            # với giờ khả dụng — không đếm wall-clock đêm/ngoài-ca mà job trải qua).
            xep = sum((r["chiem_may_phut"] or 0) for r in rs if win_s <= _aware(r["start_at"]) < win_e)
            if xep <= 0:
                continue
            # Giờ khả dụng = Σ khoảng-làm (clamp vào cửa sổ) − phần khóa máy giao khoảng-làm.
            nen = self.xl.lich_nen_may(may_id=mid, tu=today, den=den)
            khoa = [(_aware(k["start"]), _aware(k["finish"])) for k in nen["khoang_khoa"]]
            avail = 0.0
            for kl in nen["khoang_lam"]:
                ks, ke = max(_aware(kl["start"]), win_s), min(_aware(kl["finish"]), win_e)
                if ke <= ks:
                    continue
                dur = (ke - ks).total_seconds() / 60.0 - sum(_overlap_phut(bs, be, ks, ke) for bs, be in khoa)
                avail += max(0.0, dur)
            pct = (xep / avail * 100.0) if avail > 0 else float("inf")
            if pct < TAI_PCT_CANH_BAO:
                continue
            sev = SEV_CAO if pct >= TAI_PCT_CAO else SEV_CANH_BAO
            if avail > 0:
                title = (f"{rs[0]['may_ten']}: tải {pct:.0f}% trong {TAI_CUA_SO_NGAY} ngày tới "
                         f"({xep / 60.0:.0f}h đã xếp / {avail / 60.0:.0f}h khả dụng)")
            else:
                title = (f"{rs[0]['may_ten']}: {xep / 60.0:.0f}h đã xếp nhưng KHÔNG có giờ khả dụng "
                         f"trong {TAI_CUA_SO_NGAY} ngày tới")
            out.append({
                "issue_key": f"{CAT_QUA_TAI_MAY}:{mid}",
                "category": CAT_QUA_TAI_MAY, "severity": sev,
                "title": title,
                "nguyen_nhan": "Tổng giờ công việc đã xếp trên máy vượt (hoặc sát) công suất khả dụng của kỳ.",
                "impacts": self._impact(rs),
                "delay_phut": None,
                "group_key": f"may:{mid}",
            })
        return out

    def _han_som_bai_ghep(self, rows: list[dict]) -> list[dict]:
        """Thành viên bài ghép có HẠN hoàn thành sớm hơn thời điểm in ghép xong (Nghiêm trọng).
        Sau in mới xả tờ tách ra chạy tiếp — hạn trước lúc in xong là bất khả về mặt kế hoạch."""
        by_bg: dict[int, list] = {}
        for r in rows:
            if (r["nguon"] == "in_ghep" and r["bai_ghep_id"]
                    and r["trang_thai"] == "da_xep" and r["finish_at"]):
                by_bg.setdefault(r["bai_ghep_id"], []).append(_aware(r["finish_at"]))
        out: list[dict] = []
        for bgid, finishes in by_bg.items():
            finish_in = max(finishes)
            bg = self.xl.bg_repo.get(bgid)
            if bg is None:
                continue
            lsx_cua_tv = self.xl.bg_repo.lsx_by_ids([tv.lsx_id for tv in bg.thanh_viens])
            for tv in bg.thanh_viens:
                lsx = lsx_cua_tv.get(tv.lsx_id)
                han = self.xl._han(lsx)
                if han is None or _aware(_cuoi_ngay(han)) >= finish_in:
                    continue
                member_rows = [r for r in rows if r["nguon"] == "lsx" and r["lsx_id"] == tv.lsx_id]
                out.append({
                    "issue_key": f"{CAT_HAN_BAI_GHEP}:{tv.lsx_id}:{bgid}",
                    "category": CAT_HAN_BAI_GHEP, "severity": SEV_NGHIEM_TRONG,
                    "title": (f"{lsx.ma}: hạn hoàn thành {_fmt(_cuoi_ngay(han))} SỚM HƠN lúc bài ghép "
                              f"{bg.ma} in xong {_fmt(finish_in)}"),
                    "nguyen_nhan": "Lệnh có hạn sớm hơn thời điểm bài ghép in xong — không kịp xả tờ chạy tiếp.",
                    "impacts": self._impact(member_rows, extra_bg=[bgid]),
                    "delay_phut": round((finish_in - _aware(_cuoi_ngay(han))).total_seconds() / 60.0),
                    "group_key": f"bai_ghep:{bgid}",
                })
        return out

    def _thue_ngoai(self, rows: list[dict]) -> list[dict]:
        """Bước gia công ngoài: (a) thiếu NCC / ngày gửi-nhận → Chặn (không chốt được lịch nhận);
        (b) bước SAU (trong LSX) xếp bắt đầu TRƯỚC mốc nhận hàng → Nghiêm trọng;
        (c) hàng đang ở ngoài mà QUÁ HẠN nhận → Nghiêm trọng;
        (d) nhận về HỤT vượt định mức cho phép → Nghiêm trọng.

        Mốc nhận lấy SỐ THỰC khi đã có (`nhan_luc`), chưa về mới rơi về `ngay_nhan_dk`. Một bộ
        luật cho cả dự kiến lẫn thực tế — đừng để màn lệnh và màn xung đột phán hai kiểu.
        """
        out: list[dict] = []
        for r in rows:
            if r["loai_buoc"] != LB_THUE_NGOAI:
                continue
            orm = self.xl.repo.get(r["id"])
            lcd = self.xl._lcd(orm.lsx_cong_doan_id) if orm else None
            if lcd is None or not lcd.bat_buoc:
                continue
            # (a) thiếu dữ liệu gia công ngoài
            thieu = []
            if not (lcd.nha_cung_cap or "").strip():
                thieu.append("chưa chọn nhà gia công")
            if lcd.ngay_gui_dk is None or lcd.ngay_nhan_dk is None:
                thieu.append("chưa có ngày gửi/nhận")
            if thieu:
                out.append({
                    "issue_key": f"thue_ngoai_thieu:{r['id']}",
                    "category": CAT_THUE_NGOAI, "severity": SEV_CHAN,
                    "title": f"{r['lsx_ma']} · {r['cong_doan_ten']} (thuê ngoài): {', '.join(thieu)}",
                    "nguyen_nhan": "Bước gia công ngoài thiếu dữ liệu nên không chốt được lịch nhận hàng.",
                    "impacts": self._impact([r]),
                    "delay_phut": None,
                    "group_key": f"lsx:{r['lsx_id']}",
                })
            # (b) bước sau xếp trước MỐC NHẬN — thực tế thắng dự kiến khi hàng đã về
            da_ve = lcd.nhan_luc is not None
            nhan = (_aware(lcd.nhan_luc) if da_ve
                    else _aware(_cuoi_ngay(lcd.ngay_nhan_dk)) if lcd.ngay_nhan_dk else None)
            if nhan is not None and orm is not None and r["lsx_id"]:
                starts = [_aware(x.start_at) for x in self.xl.repo.by_lsx(r["lsx_id"])
                          if x.source_thu_tu > orm.source_thu_tu and x.start_at]
                early = min(starts) if starts else None
                if early is not None and early < nhan:
                    moc = "đã nhận" if da_ve else "dự kiến"
                    out.append({
                        "issue_key": f"thue_ngoai_tre:{r['id']}",
                        "category": CAT_THUE_NGOAI, "severity": SEV_NGHIEM_TRONG,
                        "title": (f"{r['lsx_ma']}: bước sau xếp {_fmt(early)} — TRƯỚC khi nhận hàng gia công "
                                  f"{r['cong_doan_ten']} ({moc} {_fmt(nhan)})"),
                        "nguyen_nhan": "Công đoạn sau được xếp bắt đầu trước lúc nhận hàng gia công về.",
                        "impacts": self._impact([r]),
                        "delay_phut": round((nhan - early).total_seconds() / 60.0),
                        "group_key": f"lsx:{r['lsx_id']}",
                    })
            # (c) hàng ĐANG Ở NGOÀI mà quá hạn nhận — chỉ đếm khi đã thật sự giao đi
            if lcd.giao_luc is not None and not da_ve and lcd.ngay_nhan_dk is not None:
                tre = (date.today() - lcd.ngay_nhan_dk).days
                if tre > 0:
                    out.append({
                        "issue_key": f"thue_ngoai_qua_han:{r['id']}",
                        "category": CAT_THUE_NGOAI, "severity": SEV_NGHIEM_TRONG,
                        "title": (f"{r['lsx_ma']} · {r['cong_doan_ten']}: hàng đang ở ngoài, "
                                  f"quá hạn nhận {tre} ngày"),
                        "nguyen_nhan": (f"Đã giao cho {lcd.nha_cung_cap or 'nhà gia công'} nhưng chưa "
                                        f"nhận về, hẹn {lcd.ngay_nhan_dk:%d/%m}."),
                        "impacts": self._impact([r]),
                        "delay_phut": tre * 24 * 60,
                        "group_key": f"lsx:{r['lsx_id']}",
                    })
            # (d) nhận về hụt vượt định mức — định mức TRỐNG là chưa khai, đừng phán
            if (lcd.sl_giao_thuc is not None and lcd.sl_nhan_thuc is not None
                    and lcd.hao_hut_cho_phep is not None):
                hut = float(lcd.sl_giao_thuc) - float(lcd.sl_nhan_thuc)
                cho_phep = float(lcd.hao_hut_cho_phep)
                if hut > cho_phep:
                    out.append({
                        "issue_key": f"thue_ngoai_hut:{r['id']}",
                        "category": CAT_THUE_NGOAI, "severity": SEV_NGHIEM_TRONG,
                        "title": (f"{r['lsx_ma']} · {r['cong_doan_ten']}: nhận về hụt "
                                  f"{hut:,.0f}, định mức cho phép {cho_phep:,.0f}".replace(",", ".")),
                        "nguyen_nhan": (f"Giao {float(lcd.sl_giao_thuc):,.0f} nhận "
                                        f"{float(lcd.sl_nhan_thuc):,.0f} — thiếu hàng cho bước sau."
                                        ).replace(",", "."),
                        "impacts": self._impact([r]),
                        "delay_phut": None,
                        "group_key": f"lsx:{r['lsx_id']}",
                    })
        return out

    # ================= HÀNH ĐỘNG NGƯỜI XỬ LÝ =================

    def _act(self, issue_key: str, actor, *, fields: dict, action: str, detail: str):
        row, _ = self.repo.get_or_create(issue_key, created_by=getattr(actor, "id", None))
        # Tái phát: đang ở "đã xử lý" mà có hành động mở lại → tăng đếm tái phát.
        if row.trang_thai == TT_DA_XU_LY and fields.get("trang_thai") not in (None, TT_DA_XU_LY):
            row.tai_phat = (row.tai_phat or 0) + 1
        for k, v in fields.items():
            setattr(row, k, v)
        self.audit.create(actor_user_id=getattr(actor, "id", None), action=action,
                          target=f"xep_lich_van_de:{issue_key}", detail=detail)
        self.repo.commit()
        return row

    def tiep_nhan(self, *, issue_key: str, actor):
        return self._act(issue_key, actor, fields={"trang_thai": TT_TIEP_NHAN},
                         action="van_de_tiep_nhan", detail=f"Tiếp nhận vấn đề {issue_key}")

    def giao(self, *, issue_key: str, user_id: int, actor):
        return self._act(issue_key, actor, fields={"assigned_to": user_id, "trang_thai": TT_DANG_XU_LY},
                         action="van_de_giao", detail=f"Giao vấn đề {issue_key} cho user #{user_id}")

    def ghi_chu(self, *, issue_key: str, note: str, actor):
        return self._act(issue_key, actor, fields={"note": note},
                         action="van_de_ghi_chu", detail=f"Ghi chú vấn đề {issue_key}")

    def danh_dau_xu_ly(self, *, issue_key: str, actor):
        return self._act(issue_key, actor, fields={"trang_thai": TT_DA_XU_LY, "resolved_at": _utcnow()},
                         action="van_de_xu_ly", detail=f"Đánh dấu đã xử lý {issue_key}")

    def tam_hoan(self, *, issue_key: str, actor):
        return self._act(issue_key, actor, fields={"trang_thai": TT_TAM_HOAN},
                         action="van_de_tam_hoan", detail=f"Tạm hoãn vấn đề {issue_key}")

    def ngoai_le(self, *, issue_key: str, ly_do: str, expires_at, actor):
        """Chấp nhận ngoại lệ (router gate `approve`). KHÔNG cho ngoại lệ vấn đề kỹ thuật bất khả:
        máy không kham khổ giấy/số màu là chặn kỹ thuật — phải đổi máy, không bỏ qua bằng ngoại lệ."""
        if issue_key.startswith(f"{CAT_MAY_KHONG_KHAM}:"):
            raise XepLichConflict("Vấn đề kỹ thuật (máy không đáp ứng) không thể duyệt ngoại lệ — đổi máy.")
        return self._act(
            issue_key, actor,
            fields={"trang_thai": TT_NGOAI_LE, "exception_ly_do": ly_do,
                    "exception_by": getattr(actor, "id", None), "exception_expires_at": _aware(expires_at)},
            action="van_de_ngoai_le", detail=f"Chấp nhận ngoại lệ {issue_key}: {ly_do}",
        )

    # ================= GATE PHÁT HÀNH (Released) =================

    def _blocking_for(self, issues: list[dict], *, lsx_ids: set[int], bg_ids: set[int]) -> list[dict]:
        out: list[dict] = []
        for it in issues:
            if it["severity"] != SEV_CHAN or it["trang_thai"] == TT_NGOAI_LE:
                continue
            imp = it["impacts"]
            if (set(imp["lsx_ids"]) & lsx_ids) or (set(imp["bai_ghep_ids"]) & bg_ids):
                out.append(it)
        return out

    def phat_hanh_lsx(self, *, lsx_id: int, actor) -> Lsx:
        lsx = self.xl.lsx_repo.get(lsx_id)
        if lsx is None:
            raise XepLichNotFound("Không tìm thấy lệnh sản xuất")
        if lsx.trang_thai != LSX_DA_LAP:
            raise XepLichConflict(f"Lệnh {lsx.ma} chưa lập kế hoạch — không thể phát hành")
        if self.xl.bg_repo.lsx_da_ghep([lsx_id]):
            raise XepLichConflict("Lệnh nằm trong bài ghép — phát hành qua bài ghép")
        blk = self._blocking_for(self._build(), lsx_ids={lsx_id}, bg_ids=set())
        if blk:
            raise XepLichConflict(f"Còn {len(blk)} xung đột CHẶN chưa xử lý/ngoại lệ — không thể phát hành")
        lsx.trang_thai = LSX_DA_PHAT_HANH
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_phat_hanh",
                          target=f"lsx:{lsx.id}", detail=f"Phát hành lệnh {lsx.ma}")
        self.repo.commit()
        return lsx

    def phat_hanh_bai_ghep(self, *, bai_ghep_id: int, actor) -> BaiGhep:
        bg = self.xl.bg_repo.get(bai_ghep_id)
        if bg is None:
            raise XepLichNotFound("Không tìm thấy bài ghép")
        if bg.trang_thai != BG_DA_LAP:
            raise XepLichConflict(f"Bài ghép {bg.ma} chưa lập kế hoạch — không thể phát hành")
        members = {tv.lsx_id for tv in bg.thanh_viens}
        blk = self._blocking_for(self._build(), lsx_ids=members, bg_ids={bai_ghep_id})
        if blk:
            raise XepLichConflict(f"Còn {len(blk)} xung đột CHẶN chưa xử lý/ngoại lệ — không thể phát hành")
        bg.trang_thai = BG_DA_PHAT_HANH
        for lid in members:
            lsx = self.xl.lsx_repo.get(lid)
            if lsx is not None:
                lsx.trang_thai = LSX_DA_PHAT_HANH
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_phat_hanh",
                          target=f"bai_ghep:{bg.id}", detail=f"Phát hành bài ghép {bg.ma}")
        self.repo.commit()
        return bg

    @staticmethod
    def _chot_ly_do_go(ly_do: str | None) -> str:
        """BẮT GÕ LÝ DO khi gỡ phát hành (G2).

        Gỡ phát hành là đảo một quyết định đã thả xuống xưởng — hệ CHƯA có lớp thực thi nên nó
        không biết thợ đã chạy tới đâu. Thứ duy nhất còn lại là VẾT: ai gỡ, lúc nào, vì sao. Cho
        gỡ mà không cần lý do là xoá luôn cái vết đó.
        """
        ly_do = (ly_do or "").strip()
        if len(ly_do) < 3:
            raise XepLichConflict(
                "Gỡ phát hành phải ghi lý do — lệnh đã xuống xưởng, cần vết để đối chiếu sau."
            )
        return ly_do[:500]

    def go_phat_hanh_lsx(self, *, lsx_id: int, actor, ly_do: str | None = None) -> Lsx:
        lsx = self.xl.lsx_repo.get(lsx_id)
        if lsx is None:
            raise XepLichNotFound("Không tìm thấy lệnh sản xuất")
        if lsx.trang_thai == LSX_DA_PHAT_HANH:
            ly_do = self._chot_ly_do_go(ly_do)
            lsx.trang_thai = LSX_DA_LAP
            self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_go_phat_hanh",
                              target=f"lsx:{lsx.id}",
                              detail=f"Thu hồi phát hành lệnh {lsx.ma} — {ly_do}")
            self.repo.commit()
        return lsx

    def go_phat_hanh_bai_ghep(self, *, bai_ghep_id: int, actor, ly_do: str | None = None) -> BaiGhep:
        bg = self.xl.bg_repo.get(bai_ghep_id)
        if bg is None:
            raise XepLichNotFound("Không tìm thấy bài ghép")
        if bg.trang_thai == BG_DA_PHAT_HANH:
            ly_do = self._chot_ly_do_go(ly_do)
            bg.trang_thai = BG_DA_LAP
            for tv in bg.thanh_viens:
                lsx = self.xl.lsx_repo.get(tv.lsx_id)
                if lsx is not None and lsx.trang_thai == LSX_DA_PHAT_HANH:
                    lsx.trang_thai = LSX_DA_LAP
            self.audit.create(actor_user_id=getattr(actor, "id", None), action="xep_lich_go_phat_hanh",
                              target=f"bai_ghep:{bg.id}",
                              detail=f"Thu hồi phát hành bài ghép {bg.ma} — {ly_do}")
            self.repo.commit()
        return bg

    # ================= SẴN SÀNG PHÁT HÀNH (cho UI) =================

    def san_sang_phat_hanh(self) -> dict:
        """LSX/bài ghép đã lập kế hoạch + số xung đột CHẶN còn lại (0 = phát hành được).

        Trả CẢ những cái ĐÃ PHÁT HÀNH (`da_phat_hanh=True`, mục G2). Trước đây danh sách chỉ có
        `da_lap_ke_hoach`, nên phát hành xong là entity biến mất khỏi màn — mà `lsx_service.update`
        thì chặn *"Lệnh đã lập kế hoạch — gỡ kế hoạch trước khi sửa"*, còn gỡ kế hoạch lại đòi gỡ
        phát hành trước. Kết quả: lệnh ĐÓNG BĂNG VĨNH VIỄN vì UI không có nút nào để quay lại.
        """
        issues = self._build()
        items: list[dict] = []
        lsxs = self.db.execute(
            select(Lsx).where(
                Lsx.trang_thai.in_([LSX_DA_LAP, LSX_DA_PHAT_HANH]),
                ~exists(select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)),
            ).order_by(Lsx.created_at.desc())
        ).scalars()
        for lsx in lsxs:
            blk = self._blocking_for(issues, lsx_ids={lsx.id}, bg_ids=set())
            items.append({"nguon": "lsx", "id": lsx.id, "ma": lsx.ma, "blocking": len(blk),
                          "da_phat_hanh": lsx.trang_thai == LSX_DA_PHAT_HANH})
        bgs = self.db.execute(
            select(BaiGhep).where(BaiGhep.trang_thai.in_([BG_DA_LAP, BG_DA_PHAT_HANH]))
            .order_by(BaiGhep.created_at.desc())
        ).scalars()
        for bg in bgs:
            members = {tv.lsx_id for tv in bg.thanh_viens}
            blk = self._blocking_for(issues, lsx_ids=members, bg_ids={bg.id})
            items.append({"nguon": "in_ghep", "id": bg.id, "ma": bg.ma, "blocking": len(blk),
                          "da_phat_hanh": bg.trang_thai == BG_DA_PHAT_HANH})
        return {"items": items, "total": len(items)}

    # ================= ĐỢT 2 — DETECTOR MỚI =================

    def _thieu_nguoi(self, rows: list[dict]) -> list[dict]:
        """Bước của TỔ bố trí ít người hơn mức TỐI THIỂU (Chặn) — dưới mức đó không mở máy được.

        `cong_doan_dau_viec.so_nguoi_toi_thieu` trước đây chỉ là khai báo; đây là chỗ nó thành ràng
        buộc thật. Chỉ so khi ĐÃ khai (> 1): mặc định 1 nghĩa là chưa khai, không phải "cần 1".
        """
        out: list[dict] = []
        for r in rows:
            toi_thieu = r.get("so_nhan_cong_toi_thieu")
            bo_tri = r.get("so_nhan_cong")
            if not toi_thieu or int(toi_thieu) <= 1 or not bo_tri:
                continue
            if int(bo_tri) >= int(toi_thieu):
                continue
            out.append({
                "issue_key": f"{CAT_THIEU_NGUOI}:{r['id']}",
                "category": CAT_THIEU_NGUOI, "severity": SEV_CHAN,
                "title": (f"{r['lsx_ma']} · {r['cong_doan_ten']}: bố trí {bo_tri} người, "
                          f"tối thiểu {toi_thieu}"),
                "nguyen_nhan": ("Định mức đầu việc yêu cầu số người tối thiểu — dưới mức đó "
                                "không vận hành được."),
                "impacts": self._impact([r]),
                "delay_phut": None,
                "group_key": f"lsx:{r['lsx_id']}",
            })
        return out

    def _qua_tai_to(self, rows: list[dict]) -> list[dict]:
        """Σ số người các việc CHẠY CÙNG LÚC trong một tổ vượt quân số có mặt hôm đó → Chặn (mục I).

        Đây là thứ THAY cho luật "trùng giờ = xung đột" ở dòng tổ. Tổ Dán 8 người hoàn toàn có thể
        chia 5 người việc A và 3 người việc B cùng lúc — đối xử tổ y như máy (chiếm trọn khoảng giờ)
        là bịa ra xung đột không có thật, rồi người dùng học cách bỏ qua báo đỏ. Ràng buộc THẬT nằm
        ở NGƯỜI: 5 + 3 ≤ 8 thì được, 5 + 5 thì không.

        Quét theo MỐC (sweep-line) chứ không so từng cặp: ba việc 3+3+3 người chồng nhau từng đôi
        một vẫn có thể vừa 9 người, mà so từng cặp thì báo đỏ cả ba. Chỉ tổng ở từng mốc mới đúng.

        Quân số lấy theo NGÀY của mốc — mỗi ngày một con số (nghỉ phép, mượn người).
        """
        theo_id = {r["id"]: r for r in rows}
        out: list[dict] = []
        for k in self.xl.khoang_tai_to(rows):
            if not k["qua_tai"]:
                continue
            chay = [theo_id[i] for i in k["dong_ids"] if i in theo_id]
            moc = _aware(k["start"])
            ten_to = k.get("department_ten") or f"Tổ #{k['department_id']}"
            out.append({
                "issue_key": f"{CAT_QUA_TAI_TO}:{k['department_id']}:{moc:%Y%m%d%H%M}",
                "category": CAT_QUA_TAI_TO, "severity": SEV_CHAN,
                "title": (f"{ten_to} {_fmt(moc)}: cần {k['dung']} người, "
                          f"có mặt {k['quan_so']}"),
                "nguyen_nhan": (
                    f"{len(chay)} việc chạy cùng lúc trong tổ, cộng lại {k['dung']} người trong khi "
                    f"quân số ngày {moc:%d/%m} là {k['quan_so']}. Dời bớt một việc, hoặc sửa quân "
                    f"số ngày đó nếu có mượn người tổ khác."
                ),
                "impacts": self._impact(chay),
                "delay_phut": None,
                "group_key": f"to:{k['department_id']}",
            })
        return out

    def _thieu_vat_tu(self, rows: list[dict]) -> list[dict]:
        """Lệnh / bài có dòng ĐỎ trên bảng cân đối vật tư → vấn đề mức Chặn (F).

        Đọc THẲNG `ke_hoach_vat_tu_service`, không chép lại phép cân đối — hai nơi tính là hai nơi
        lệch, mà lệch ở đây là phát hành một lệnh không có giấy.

        **KHÔNG chặn lúc xếp** (chủ chốt): xếp lịch trước rồi mới biết bao giờ cần hàng, cấm xếp
        khi thiếu là cấm đúng bước sinh ra thông tin để đi mua. Chỉ chặn ở cửa PHÁT HÀNH.

        Gộp MỘT vấn đề cho mỗi lệnh/bài (không phải mỗi mặt hàng): người xử lý cần biết "lệnh này
        thiếu vật tư", còn thiếu những gì thì mở bảng cân đối ra xem — đẻ 5 vấn đề cho 5 loại giấy
        là làm ngập danh sách bằng cùng một việc.
        """
        try:
            bang = self._can_doi_vat_tu()
        except Exception as exc:
            # Bảng cân đối hỏng KHÔNG được làm sập cả màn Vấn đề: 9 detector kia vẫn phải chạy.
            # NHƯNG cũng KHÔNG được im lặng trả rỗng — rỗng đọc y hệt "không lệnh nào thiếu vật tư",
            # và cửa phát hành sẽ mở cho một lệnh không có giấy. Không kiểm được thì phải NÓI ra.
            return [{
                "issue_key": "thieu_vat_tu:khong_kiem_duoc",
                "category": CAT_THIEU_VAT_TU,
                "severity": SEV_CANH_BAO,
                "title": "Không kiểm được vật tư",
                "nguyen_nhan": (
                    "Bảng cân đối vật tư lỗi nên không biết lệnh nào thiếu hàng: "
                    f"{type(exc).__name__}. Mở tab Vật tư ở bàn Kế hoạch SX để xem lỗi thật, "
                    "và tự đối chiếu tồn trước khi phát hành."
                ),
                "impacts": self._impact([]),
                "delay_phut": None,
                "group_key": "thieu_vat_tu:loi",
            }]
        thieu_lsx: dict[int, list[str]] = {}
        thieu_bg: dict[int, list[str]] = {}
        for nhom in bang.get("items", []):
            if nhom.get("loai_nhom") != "vat_tu":
                continue
            for d in nhom.get("dong", []):
                if d.get("trang_thai") != "do":
                    continue
                ten = nhom.get("hang_ten") or nhom.get("hang_ma") or "?"
                if d.get("lsx_id"):
                    thieu_lsx.setdefault(d["lsx_id"], []).append(ten)
                elif d.get("bai_ghep_id"):
                    thieu_bg.setdefault(d["bai_ghep_id"], []).append(ten)

        ma_lsx = {r["lsx_id"]: r["lsx_ma"] for r in rows if r.get("lsx_id")}
        ma_bg = {r["bai_ghep_id"]: r["lsx_ma"] for r in rows if r.get("bai_ghep_id")}
        out: list[dict] = []
        for lsx_id, tens in thieu_lsx.items():
            lien_quan = [r for r in rows if r.get("lsx_id") == lsx_id]
            if not lien_quan:
                continue                     # lệnh chưa vào kế hoạch thì chưa phải việc của bàn này
            out.append(self._van_de_thieu_vt(
                f"lsx:{lsx_id}", ma_lsx.get(lsx_id), tens, lien_quan, None))
        for bg_id, tens in thieu_bg.items():
            lien_quan = [r for r in rows if r.get("bai_ghep_id") == bg_id]
            if not lien_quan:
                continue
            out.append(self._van_de_thieu_vt(
                f"bai_ghep:{bg_id}", ma_bg.get(bg_id), tens, lien_quan, bg_id))
        return out

    def _van_de_thieu_vt(self, khoa: str, ma: str | None, tens: list[str],
                         lien_quan: list[dict], bg_id: int | None) -> dict:
        ds = _uniq(tens)
        hien = ", ".join(ds[:3]) + (f" và {len(ds) - 3} thứ khác" if len(ds) > 3 else "")
        return {
            "issue_key": f"{CAT_THIEU_VAT_TU}:{khoa}",
            "category": CAT_THIEU_VAT_TU, "severity": SEV_CHAN,
            "title": f"{ma or khoa}: thiếu {hien}",
            "nguyen_nhan": ("Bảng cân đối vật tư báo thiếu — tồn cộng hàng đang về vẫn không đủ "
                            "tới ngày cần."),
            "impacts": self._impact(lien_quan, extra_bg=[bg_id] if bg_id else None),
            "delay_phut": None,
            "group_key": khoa,
        }

    def _can_doi_vat_tu(self) -> dict:
        """Bảng cân đối vật tư — dựng service TRỄ và nhớ luôn KẾT QUẢ trong vòng đời service.

        Nhớ kết quả chứ không chỉ nhớ service: `can_doi()` nạp toàn bộ lệnh + bài + phiếu mua + tồn
        và tính `thoi_luong_buoc` từng bước. `_build()` chạy ở CẢ `danh_sach` (view Vấn đề) LẪN
        `san_sang_phat_hanh` (badge + cửa phát hành), nên mỗi lần mở bàn xếp lịch là hai lượt quét
        y hệt nhau. Service sống trong MỘT request nên cache ở đây không bao giờ trả số cũ.
        """
        if getattr(self, "_kh_vt_bang", None) is not None:
            return self._kh_vt_bang
        if getattr(self, "_kh_vt", None) is None:
            from ..repositories.bai_ghep_repo import BaiGhepRepository
            from ..repositories.don_vi_do_repo import DonViDoRepository
            from ..repositories.lsx_repo import LsxRepository
            from ..repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
            from ..repositories.stock_lot_repo import StockLotRepository
            from ..repositories.stock_request_repo import StockRequestRepository
            from ..repositories.vat_lieu_kho_repo import VatLieuKhoRepository
            from .ke_hoach_vat_tu_service import KeHoachVatTuService
            from .vat_lieu_kho_service import VatLieuKhoService

            self._kh_vt = KeHoachVatTuService(
                self.db,
                lsx_repo=LsxRepository(self.db),
                bai_ghep_repo=BaiGhepRepository(self.db),
                hang=VatLieuKhoService(VatLieuKhoRepository(self.db), DonViDoRepository(self.db)),
                lots=StockLotRepository(self.db),
                requests=StockRequestRepository(self.db),
                purchases=PurchaseRequestRepository(self.db),
                suppliers=SupplierRepository(self.db),
                don_vi=DonViDoRepository(self.db),
            )
        self._kh_vt_bang = self._kh_vt.can_doi()
        return self._kh_vt_bang
