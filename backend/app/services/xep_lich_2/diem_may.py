"""Chấm điểm MÁY cho một bước — đổi câu hỏi từ "máy nào xong sớm nhất" sang **"máy nào kịp hạn mà
ít phí nhất"**.

Vì sao phải đổi: "sớm nhất" là cái đích SAI. Bài chỉ cần kịp hạn SX; xong sớm hơn hạn 3 ngày hay 5
ngày không khác gì nhau với xưởng. Đua sớm nhất thì hệ luôn bốc máy khoẻ nhất cho bài đầu tiên nó
gặp, để rồi bài cần đúng máy đó hôm sau không còn chỗ — mà không ai nhìn ra, vì từng quyết định lẻ
đều "tối ưu".

BA TRỤC, thang 100:

  · `kip_han` (45) — ĐỆM tới hạn SX, không phải giờ xong tuyệt đối. Mọi máy kịp thoải mái đều ăn
    trọn điểm ⇒ trục này TỰ IM khi không có gì phải tranh, nhường quyền quyết cho hai trục dưới.
    Không có hạn thì đo tương đối so với máy xong sớm nhất — chứ KHÔNG bỏ trục: bỏ là mất hẳn yếu
    tố thời gian, hệ sẽ chọn một máy xong muộn mười ngày chỉ vì hôm đó nó rảnh.
  · `doi_bai` (30) — nối ngay sau việc cùng giấy · khổ · bộ mực thì gần như khỏi canh lại máy. Đây
    là tiền tiết kiệm sờ được. Trước đây tiêu chí này chỉ là cái phá hoà bên trong cửa sổ dung sai
    60 phút, nên gần như không bao giờ có cửa thắng.
  · `san_tai` (25) — máy đã kín bao nhiêu phần quỹ giờ ca ngày đó; kín thì trừ, để việc rải đều và
    để dành chỗ cho bài tới.

CỐ Ý KHÔNG chấm KHỔ · SỐ MÀU · ĐỊNH LƯỢNG. Không phải quên: 09/08/2026 chủ đã cho gỡ mọi phép kết
luận theo ba thứ đó khỏi v2 (spec §6) và có test §12.8 soi mã nguồn canh chừng. Trục "vừa khổ máy"
(để dành máy khổ lớn cho bài khổ lớn) đã viết rồi lại gỡ ra vì đúng luật đó — muốn bật thì phải chủ
gật trước, không phải lách test.

GATE THEO DỮ LIỆU: trục nào KHÔNG đo được thì bỏ khỏi cả tử số lẫn MẪU SỐ, không chấm 0. Chấm 0 cho
thứ chưa khai là phạt oan mọi máy như nhau — vô nghĩa, mà còn kéo tụt điểm khiến người đọc tưởng cả
xưởng đều tệ.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

# Trọng số ba trục. Đổi số ở đây là đổi CHÍNH SÁCH xếp lịch, không phải tinh chỉnh kỹ thuật.
TRONG_SO = {"kip_han": 45.0, "doi_bai": 30.0, "san_tai": 25.0}
TEN_TRUC = {
    "kip_han": "Kịp hạn",
    "doi_bai": "Đổi bài rẻ",
    "san_tai": "San tải",
}

# Đệm (ngày) tới hạn SX được coi là "thoải mái" — từ đây trở lên ăn trọn điểm trục kịp hạn.
DEM_THOAI_MAI = 2.0
# Xong muộn hơn máy nhanh nhất bấy nhiêu giờ vẫn coi như ngang nhau (CHỈ dùng khi không có hạn).
TRE_BO_QUA_GIO = 4.0
# ...và tới mốc này thì trục kịp hạn về 0.
TRE_HET_DIEM_GIO = 48.0

# Ngưỡng đọc kết quả: trục đạt từ `NGUONG_MANH` trở lên mới được kể là ĐIỂM MẠNH; dưới `NGUONG_TRU`
# thì bị nêu ra như điểm trừ. Giữa hai ngưỡng là "bình thường", không nói gì — nói hết thành nhiễu.
NGUONG_MANH = 0.60
NGUONG_TRU = 0.40


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def quy_ca_phut(ca) -> float:
    """Tổng phút làm việc của MỘT ngày theo lịch ca — mẫu số đo tải máy.

    `ca` là list `(phút bắt đầu, phút kết thúc, có qua đêm)` trong ngày. Ca qua đêm đếm phần đuôi
    ngày cộng phần đầu ngày hôm sau: đó vẫn là một ca của một ngày công.
    """
    tong = 0.0
    for bat_dau, ket_thuc, qua_dem in ca or []:
        b, e = _f(bat_dau), _f(ket_thuc)
        tong += (1440.0 - b) + e if qua_dem else max(0.0, e - b)
    return tong


def _pct(ty: float) -> int:
    return int(round(max(0.0, min(1.0, ty)) * 100))


def _het_han(han: date | None) -> datetime | None:
    """Mốc CUỐI của ngày hạn (= 0h ngày hôm sau). Xong lúc 23h ngày hạn vẫn là kịp."""
    if han is None:
        return None
    return datetime.combine(han, time.min, tzinfo=timezone.utc) + timedelta(days=1)


def _kip_han(u: dict, het: datetime | None, tot: datetime) -> tuple[float, str, bool]:
    """(điểm, câu, có trễ hạn không). Luôn đo được nên KHÔNG bao giờ trả None."""
    toi_da = TRONG_SO["kip_han"]
    finish = u["finish"]
    if het is not None:
        if finish > het:
            tre = (finish - het).total_seconds() / 86400.0
            return 0.0, f"TRỄ hạn SX khoảng {max(1, int(round(tre)))} ngày.", True
        dem = (het - finish).total_seconds() / 86400.0
        dat = min(toi_da, 28.0 + 17.0 * min(1.0, dem / DEM_THOAI_MAI))
        if dem < 1.0:
            return dat, "Xong ngay trong ngày hạn SX — sát nút.", False
        return dat, f"Xong trước hạn SX {int(dem)} ngày.", False
    # Không có hạn ⇒ so tương đối với máy xong sớm nhất, chứ không bỏ trục.
    tre_gio = (finish - tot).total_seconds() / 3600.0
    if tre_gio <= TRE_BO_QUA_GIO:
        return toi_da, "Xong sớm nhất trong các máy làm được bước này.", False
    thua = (tre_gio - TRE_BO_QUA_GIO) / (TRE_HET_DIEM_GIO - TRE_BO_QUA_GIO)
    return toi_da * max(0.0, 1.0 - thua), f"Xong muộn hơn máy nhanh nhất {int(round(tre_gio))} giờ.", False


def _doi_bai(u: dict) -> tuple[float, str] | None:
    """Lệnh chưa đủ quy cách để dựng khoá gom ⇒ KHÔNG đo được, bỏ trục — đừng phạt oan."""
    if not u.get("co_gom"):
        return None
    if u.get("cung_gom"):
        return (TRONG_SO["doi_bai"],
                "Nối ngay sau việc cùng giấy · khổ · bộ mực nên gần như khỏi canh lại máy.")
    return 0.0, "Việc liền trước trên máy này khác giấy · khổ · mực nên phải canh lại máy."


def _san_tai(u: dict, quy: float) -> tuple[float, str] | None:
    """Chưa khai ca nào ⇒ không có mẫu số ⇒ bỏ trục."""
    if quy <= 0:
        return None
    ty = min(1.0, _f(u.get("tai_ngay")) / quy)
    dat = TRONG_SO["san_tai"] * (1.0 - ty)
    if ty <= 1.0 - NGUONG_MANH:
        return dat, f"Máy còn rảnh {_pct(1.0 - ty)}% quỹ ca ngày đó."
    return dat, f"Máy đã kín {_pct(ty)}% quỹ ca ngày đó."


def _truc(ma: str, dat: float, cau: str) -> dict:
    toi_da = TRONG_SO[ma]
    return {"ma": ma, "ten": TEN_TRUC[ma], "dat": round(dat, 1), "toi_da": toi_da,
            "ty_le": (dat / toi_da) if toi_da else 0.0, "cau": cau}


def cham_tat_ca(ung_vien: list[dict], *, han: date | None, ca) -> None:
    """Gắn `u["diem"]` cho TỪNG ứng viên, tại chỗ.

    Chấm MỘT LẦN trên cả danh sách (không chấm lẻ từng máy) vì trục `kip_han` ở chế độ không-hạn
    cần biết giờ xong tốt nhất của cả nhóm. Nhờ vậy điểm là con số TUYỆT ĐỐI: nhánh gợi ý bốc dần
    từng máy ra khỏi danh sách vẫn không làm điểm của những máy còn lại nhảy lung tung.
    """
    if not ung_vien:
        return
    het = _het_han(han)
    tot = min(u["finish"] for u in ung_vien)
    quy = quy_ca_phut(ca)
    for u in ung_vien:
        dat_kh, cau_kh, tre = _kip_han(u, het, tot)
        truc: list[dict] = [_truc("kip_han", dat_kh, cau_kh)]
        for ma, ket in (("doi_bai", _doi_bai(u)),
                        ("san_tai", _san_tai(u, quy))):
            if ket is not None:
                truc.append(_truc(ma, ket[0], ket[1]))
        tong_toi_da = sum(t["toi_da"] for t in truc)
        diem = int(round(100.0 * sum(t["dat"] for t in truc) / tong_toi_da)) if tong_toi_da else 0
        xep = sorted(truc, key=lambda t: -t["ty_le"])
        manh = [t["cau"] for t in xep if t["ty_le"] >= NGUONG_MANH][:2]
        yeu = [t for t in xep if t["ty_le"] < NGUONG_TRU]
        u["diem"] = {
            "diem": diem,
            "tre_han": tre,
            "truc": truc,
            "manh": manh or [xep[0]["cau"]],
            "tru": yeu[-1]["cau"] if yeu else None,
        }
