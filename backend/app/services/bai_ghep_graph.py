"""Đồ thị co (quotient graph) của bài ghép — gộp bước rồi kiểm vòng.

Gộp N bước thành MỘT lượt chạy chung chính là phép CO NÚT trên đồ thị phụ thuộc: mọi bước trong
nhóm nhập thành một đại diện, cạnh `a→b` thành `find(a)→find(b)`. Hình "tụ vào rồi toả ra" của
bài ghép rơi ra từ đó — không ai phải khai cạnh cho bài, và khai ở hai nơi là hai nguồn sự thật.

Hai kiểu hỏng, bắt TRƯỚC khi ghi:

1. **Cạnh tự trỏ chính mình** — gộp hai bước vốn đã phụ thuộc nhau (lệnh xếp `Cán màng → Ép kim`
   mà đòi gộp cả hai). Một lượt chạy không thể vừa trước vừa sau chính nó.
2. **Vòng giữa các đại diện** — mỗi lệnh xếp một thứ tự khác nhau, gộp xong hai nhóm khoá nhau:
   lệnh A `Cán → Ép kim`, lệnh B `Ép kim → Cán`, gộp cả hai công đoạn là kẹt.

Cạnh CHÉO LỆNH giữ nguyên. Sách = bìa (một lệnh) + ruột (một lệnh) nối nhau ở bước "vào bìa",
nên bộ lọc "hai đầu cạnh cùng một LSX" trong `lsx_service._kiem_chu_trinh_phu_thuoc` KHÔNG dùng
lại được ở đây — nó mù đúng với loại cạnh mà bài ghép hay đụng nhất.

Thuần Python, không chạm DB: canvas hỏi "thẻ nào gộp vào được" là N lần thử gộp liên tiếp, chạy
hết trên dữ liệu đã nạp sẵn chứ không N vòng truy vấn.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Buoc:
    """Một bước trong tầm ngắm — của lệnh trong bài, hoặc của lệnh ngoài bài nối vào (ruột sách)."""

    key: str                    # `lsx_cong_doan.step_key`
    lsx_id: int
    lsx_ma: str
    ten: str
    cong_doan_id: int | None
    trong_bai: bool = True      # False = node bóng mờ, chỉ để kiểm vòng, không cho gộp


@dataclass(frozen=True)
class CanhGoc:
    """Cạnh phụ thuộc THẬT giữa hai bước — dùng làm nhân chứng khi báo vòng."""

    truoc: str
    sau: str


@dataclass
class Vong:
    """Một chu trình phát hiện được, kèm nhân chứng là các cạnh GỐC.

    Giữ nhân chứng để câu báo lỗi chỉ đúng cặp mâu thuẫn, thay vì "có vòng ở đâu đó".
    """

    nut: list[str]                          # chuỗi key đại diện, phần tử cuối lặp lại phần tử đầu
    nhan_chung: list[CanhGoc]
    thong_diep: str
    tu_tro: bool = False                    # True = kiểu hỏng 1 (gộp hai bước phụ thuộc nhau)


@dataclass
class DoThiCo:
    dai_dien: dict[str, str]                          # step_key → key đại diện
    canh: dict[tuple[str, str], list[CanhGoc]]        # cạnh đã co → các cạnh gốc sinh ra nó
    thu_tu: list[str] = field(default_factory=list)   # topo order của đại diện ([] nếu vòng)
    vong: Vong | None = None


class _UnionFind:
    def __init__(self, keys) -> None:
        self.cha = {k: k for k in keys}

    def find(self, k: str) -> str:
        cha = self.cha
        goc = k
        while cha[goc] != goc:
            goc = cha[goc]
        while cha[k] != goc:            # nén đường
            cha[k], k = goc, cha[k]
        return goc

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.cha[rb] = ra


def _ten_nut(dai_dien_key: str, thanh_vien: dict[str, list[Buoc]]) -> str:
    """Tên hiển thị của một đại diện. Nhóm gộp toàn bước cùng công đoạn nên lấy cái đầu là đủ."""
    ds = thanh_vien.get(dai_dien_key) or []
    return ds[0].ten if ds else dai_dien_key


def co_do_thi(
    buocs: list[Buoc],
    canhs: list[CanhGoc],
    nhom_gop: list[list[str]] | None = None,
) -> DoThiCo:
    """Co đồ thị theo các nhóm gộp rồi kiểm vòng.

    `nhom_gop` là danh sách nhóm, mỗi nhóm là các `step_key` chạy chung một lượt. Bước không nằm
    trong nhóm nào tự làm đại diện của chính nó.
    """
    theo_key = {b.key: b for b in buocs}
    uf = _UnionFind(theo_key)

    # Đại diện = key nhỏ nhất trong nhóm → kết quả ổn định giữa các lần chạy, dễ so trong test.
    for nhom in nhom_gop or []:
        co_that = sorted(k for k in nhom if k in theo_key)
        for k in co_that[1:]:
            uf.union(co_that[0], k)

    dai_dien = {k: uf.find(k) for k in theo_key}
    thanh_vien: dict[str, list[Buoc]] = {}
    for k, b in theo_key.items():
        thanh_vien.setdefault(dai_dien[k], []).append(b)

    canh: dict[tuple[str, str], list[CanhGoc]] = {}
    for c in canhs:
        if c.truoc not in dai_dien or c.sau not in dai_dien:
            continue                        # cạnh trỏ ra ngoài tầm ngắm — bỏ, không đoán
        ra, rb = dai_dien[c.truoc], dai_dien[c.sau]
        if ra == rb:
            if c.truoc == c.sau:
                continue                    # cạnh tự thân trong dữ liệu — bỏ qua, không phải lỗi gộp
            return DoThiCo(
                dai_dien=dai_dien, canh=canh,
                vong=Vong(
                    nut=[ra, ra], nhan_chung=[c], tu_tro=True,
                    thong_diep=(
                        f'Không gộp được: lệnh {theo_key[c.truoc].lsx_ma} xếp '
                        f'"{theo_key[c.sau].ten}" sau "{theo_key[c.truoc].ten}" — hai bước phụ '
                        f"thuộc nhau thì không thể chạy chung một lượt."
                    ),
                ),
            )
        canh.setdefault((ra, rb), []).append(c)

    nut = sorted(thanh_vien)
    ke: dict[str, set[str]] = {n: set() for n in nut}
    bac_vao = {n: 0 for n in nut}
    for (a, b) in canh:
        if b not in ke[a]:
            ke[a].add(b)
            bac_vao[b] += 1

    hang_doi = [n for n in nut if bac_vao[n] == 0]
    thu_tu: list[str] = []
    while hang_doi:
        n = hang_doi.pop()
        thu_tu.append(n)
        for ke_tiep in sorted(ke[n]):
            bac_vao[ke_tiep] -= 1
            if bac_vao[ke_tiep] == 0:
                hang_doi.append(ke_tiep)

    if len(thu_tu) == len(nut):
        return DoThiCo(dai_dien=dai_dien, canh=canh, thu_tu=thu_tu)

    chu_trinh = _tim_chu_trinh({n: ke[n] for n in nut if n not in set(thu_tu)})
    nhan_chung = [
        sorted(canh[(chu_trinh[i], chu_trinh[i + 1])], key=lambda c: (c.truoc, c.sau))[0]
        for i in range(len(chu_trinh) - 1)
        if (chu_trinh[i], chu_trinh[i + 1]) in canh
    ]
    duong = " → ".join(f'"{_ten_nut(n, thanh_vien)}"' for n in chu_trinh)
    ly_do = "; ".join(
        f'lệnh {theo_key[c.truoc].lsx_ma} xếp "{theo_key[c.sau].ten}" sau "{theo_key[c.truoc].ten}"'
        for c in nhan_chung
    )
    return DoThiCo(
        dai_dien=dai_dien, canh=canh,
        vong=Vong(
            nut=chu_trinh, nhan_chung=nhan_chung,
            thong_diep=f"Gộp sẽ tạo vòng: {duong}." + (f" Vì {ly_do}." if ly_do else ""),
        ),
    )


def _tim_chu_trinh(ke: dict[str, set[str]]) -> list[str]:
    """DFS lặp tìm một chu trình, trả `[n0, …, n0]`. Duyệt theo thứ tự sắp xếp cho ổn định."""
    trang: dict[str, int] = {}          # 1 = đang trong ngăn xếp, 2 = đã xong
    cha: dict[str, str] = {}
    for goc in sorted(ke):
        if trang.get(goc):
            continue
        trang[goc] = 1
        ngan_xep = [(goc, iter(sorted(ke.get(goc, ()))))]
        while ngan_xep:
            nut, con = ngan_xep[-1]
            ke_tiep = next(con, None)
            if ke_tiep is None:
                trang[nut] = 2
                ngan_xep.pop()
                continue
            if ke_tiep not in ke:
                continue                # cạnh chạy ra ngoài phần còn kẹt
            if trang.get(ke_tiep) == 1:          # cạnh lùi → dựng ngược chu trình
                chu = [ke_tiep]
                cur = nut
                while cur != ke_tiep:
                    chu.append(cur)
                    cur = cha[cur]
                chu.append(ke_tiep)
                chu.reverse()
                return chu
            if not trang.get(ke_tiep):
                trang[ke_tiep] = 1
                cha[ke_tiep] = nut
                ngan_xep.append((ke_tiep, iter(sorted(ke.get(ke_tiep, ())))))
    return []


def kiem_gop(
    buocs: list[Buoc],
    canhs: list[CanhGoc],
    nhom_gop: list[list[str]],
) -> Vong | None:
    """`None` = gộp được. Ngược lại trả `Vong` kèm câu báo chỉ đúng cặp mâu thuẫn."""
    return co_do_thi(buocs, canhs, nhom_gop).vong


def ung_vien_gop(
    buocs: list[Buoc],
    canhs: list[CanhGoc],
    nhom_hien_co: list[list[str]],
    dang_chon: list[str],
) -> dict[str, Vong | None]:
    """Với tập đang chọn, mỗi bước CÙNG CÔNG ĐOẠN ở lệnh khác gộp vào được không.

    Canvas dùng để quyết thẻ nào sáng lên: khoá `None` là sáng, khoá có `Vong` là mờ kèm lý do
    hiện lúc rê chuột. Kiểm TRƯỚC nên nút Gộp không bao giờ bấm rồi mới bị từ chối.
    """
    theo_key = {b.key: b for b in buocs}
    chon = [k for k in dang_chon if k in theo_key]
    if not chon:
        return {}
    cd = theo_key[chon[0]].cong_doan_id
    da_gop = {k for nhom in nhom_hien_co for k in nhom}
    lsx_da_chon = {theo_key[k].lsx_id for k in chon}

    ket: dict[str, Vong | None] = {}
    for b in buocs:
        if (
            b.key in chon or b.key in da_gop or not b.trong_bai
            or b.cong_doan_id is None or b.cong_doan_id != cd
            or b.lsx_id in lsx_da_chon      # cùng một lệnh thì không tự gộp với chính nó
        ):
            continue
        ket[b.key] = kiem_gop(buocs, canhs, [*nhom_hien_co, [*chon, b.key]])
    return ket
