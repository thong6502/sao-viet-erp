"""Migration 0131 — nội quy: `source_kind` + `is_import_source`.

Cột MỚI ⇒ bắt buộc migration: `create_all` chỉ tạo bảng THIẾU, không bao giờ ALTER bảng đã có.
Thiếu migration này thì DB live (đã có 2 bảng nội quy từ đợt trước) thiếu cột và mọi lần đọc nội quy
sẽ nổ — mà nội quy là màn CẢ CÔNG TY mở.

Thứ phải đúng, theo mức đau:

1. **Bản nội quy đang hiệu lực không được đổi hành vi.** DB cũ nâng cấp lên thì mọi bản phải là
   `source_kind='html'` — tức đúng cách chúng đang hiển thị. Mặc định sai là cả công ty mở nội quy
   ra thấy trống (hệ thống đi tìm ảnh trang không có).
2. **File chứng từ đã đính kèm không được biến thành "file gốc của lần nhập".** `is_import_source`
   phải mặc định `false`: hàng `true` là hàng sẽ bị XOÁ khi nhập lại. Mặc định sai là lần nhập tới
   xoá mất bản PDF đã ký của chủ.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db_migrations import (
    _migrate_noi_quy_nguon_va_file_goc,
    _migrate_noi_quy_nhieu_tai_lieu,
)


def _engine_cu():
    """DB "cũ": 2 bảng nội quy như đợt trước, CHƯA có 2 cột mới.

    Dựng sẵn một bản đã ban hành + một file đã ký để kiểm hai điều ở §1 và §2."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE noi_quy_versions (id INTEGER PRIMARY KEY, "
            "noi_dung TEXT NOT NULL DEFAULT '', ghi_chu VARCHAR(255), "
            "status VARCHAR(12) NOT NULL DEFAULT 'draft')"))
        cn.execute(text(
            "CREATE TABLE noi_quy_attachments (id INTEGER PRIMARY KEY, "
            "version_id INTEGER NOT NULL, file_name VARCHAR(255) NOT NULL, "
            "file_url VARCHAR(500) NOT NULL)"))
        cn.execute(text(
            "INSERT INTO noi_quy_versions (id, noi_dung, status) "
            "VALUES (1, '<p>Điều 1. Đi làm đúng giờ.</p>', 'published')"))
        cn.execute(text(
            "INSERT INTO noi_quy_attachments (id, version_id, file_name, file_url) "
            "VALUES (1, 1, 'noi-quy-da-ky.pdf', '/api/files/noi-quy/1/noi-quy-da-ky.pdf')"))
    return engine


def _cols(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_ban_cu_van_hien_theo_duong_HTML_nhu_truoc():
    """⭐ Nâng cấp KHÔNG được đổi cách bản đang hiệu lực hiển thị.

    Mọi bản có trước đợt này đều là nội dung gõ trong app ⇒ phải là `'html'`. Nếu mặc định thành
    `'file'` thì hệ thống đi tìm ảnh trang (không có) và cả công ty mở nội quy ra thấy TRỐNG."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_noi_quy_nguon_va_file_goc(db)

    assert "source_kind" in _cols(engine, "noi_quy_versions")
    with engine.begin() as cn:
        assert cn.execute(text("SELECT source_kind FROM noi_quy_versions")).scalar() == "html"
        # Nội dung không bị đụng tới.
        assert cn.execute(text("SELECT noi_dung FROM noi_quy_versions")).scalar() \
            == "<p>Điều 1. Đi làm đúng giờ.</p>"


def test_file_da_ky_KHONG_bi_coi_la_file_goc_cua_lan_nhap():
    """⭐ `is_import_source=true` là hàng sẽ bị XOÁ khi nhập lại.

    Bản PDF đã ký chủ tự đính kèm phải là `false`, nếu không lần nhập tới nó biến mất — im lặng,
    và đúng cái file có giá trị pháp lý nhất."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_noi_quy_nguon_va_file_goc(db)

    assert "is_import_source" in _cols(engine, "noi_quy_attachments")
    with engine.begin() as cn:
        assert cn.execute(text(
            "SELECT COUNT(*) FROM noi_quy_attachments WHERE is_import_source"
        )).scalar() == 0, "file đã ký phải KHÔNG bị đánh dấu là file gốc của lần nhập"


def test_chay_lai_lan_hai_khong_no_va_khong_de_len_gia_tri_da_khai():
    """Migration chạy MỖI lần khởi động app ⇒ guard theo cột, lần 2 phải là no-op.

    Quan trọng hơn: một bản đã chuyển sang `'file'` thì lần chạy sau KHÔNG được kéo về `'html'` —
    kéo về là bản nội quy dạng ảnh trang bỗng hiện trống."""
    engine = _engine_cu()
    with Session(engine) as db:
        _migrate_noi_quy_nguon_va_file_goc(db)
    with engine.begin() as cn:
        cn.execute(text("UPDATE noi_quy_versions SET source_kind = 'file'"))
        cn.execute(text("UPDATE noi_quy_attachments SET is_import_source = true"))

    with Session(engine) as db:
        _migrate_noi_quy_nguon_va_file_goc(db)   # không được nổ

    with engine.begin() as cn:
        assert cn.execute(text("SELECT source_kind FROM noi_quy_versions")).scalar() == "file"
        assert cn.execute(text(
            "SELECT COUNT(*) FROM noi_quy_attachments WHERE is_import_source")).scalar() == 1


# --- 0132: một bản ban hành → nhiều tài liệu --------------------------------

def _engine_truoc_0132():
    """DB đã qua 0131: có bản ban hành + nháp + trang + file, CHƯA có tầng tài liệu.

    Dựng đúng cảnh DB thật của chủ: nhiều lần ban hành lại của CÙNG một văn bản, cộng một nháp
    đang treo."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as cn:
        cn.execute(text(
            "CREATE TABLE noi_quy_documents (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, "
            "seq INTEGER NOT NULL DEFAULT 1, is_active BOOLEAN NOT NULL DEFAULT true, "
            "created_at TIMESTAMP)"))
        cn.execute(text(
            "CREATE TABLE noi_quy_versions (id INTEGER PRIMARY KEY, "
            "noi_dung TEXT NOT NULL DEFAULT '', ghi_chu VARCHAR(255), "
            "status VARCHAR(12) NOT NULL DEFAULT 'draft', source_kind VARCHAR(8) DEFAULT 'html')"))
        cn.execute(text(
            "CREATE TABLE noi_quy_pages (id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, "
            "page_no INTEGER NOT NULL, file_url VARCHAR(500) NOT NULL)"))
        for i in (1, 2, 3):
            cn.execute(text(
                "INSERT INTO noi_quy_versions (id, noi_dung, ghi_chu, status, source_kind) "
                "VALUES (:i, :nd, :gc, 'published', 'file')"),
                {"i": i, "nd": f"<p>Ban {i}</p>", "gc": f"Bổ sung quy định lần {i}"})
            cn.execute(text(
                "INSERT INTO noi_quy_pages (version_id, page_no, file_url) "
                "VALUES (:v, 1, :u)"), {"v": i, "u": f"/api/files/noi-quy/{i}/t1.jpg"})
        cn.execute(text(
            "INSERT INTO noi_quy_versions (id, noi_dung, status) VALUES (9, '<p>nhap</p>', 'draft')"))
    return engine


def test_moi_ban_cu_deu_duoc_gan_vao_DUNG_MOT_tai_lieu():
    """⭐ Bỏ sót bản nào là bản đó thành mồ côi: không tài liệu nào trỏ tới ⇒ cả công ty mở nội quy
    ra thấy "chưa ban hành", dù dòng vẫn nằm nguyên trong DB.

    Và phải gom vào ĐÚNG MỘT tài liệu — 3 bản published kia là 3 lần ban hành lại của cùng một văn
    bản, tách thành 3 tài liệu là bịa ra 3 văn bản không hề tồn tại."""
    engine = _engine_truoc_0132()
    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)

    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM noi_quy_documents")).scalar() == 1
        assert cn.execute(text(
            "SELECT COUNT(*) FROM noi_quy_versions WHERE document_id IS NULL")).scalar() == 0
        # Cả 4 dòng (3 published + 1 nháp) cùng trỏ về một tài liệu.
        assert cn.execute(text(
            "SELECT COUNT(DISTINCT document_id) FROM noi_quy_versions")).scalar() == 1
        assert cn.execute(text("SELECT COUNT(*) FROM noi_quy_versions")).scalar() == 4


def test_KHONG_dung_ghi_chu_lam_ten_tai_lieu():
    """`ghi_chu` là *ghi chú thay đổi* ("Bổ sung quy định lần 3"), không phải tên văn bản.

    Lấy nó làm tiêu đề thì SAI mà nhìn vẫn hợp lý — loại sai tệ nhất, vì không ai soi lại."""
    engine = _engine_truoc_0132()
    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)

    with engine.begin() as cn:
        ten = cn.execute(text("SELECT title FROM noi_quy_documents")).scalar()
    assert ten == "Nội quy lao động"
    assert "Bổ sung" not in ten


def test_noi_dung_va_anh_trang_KHONG_bi_dung_toi():
    """Migration này chỉ GẮN tài liệu, tuyệt đối không đụng nội dung. Chủ có nội quy thật ở đây."""
    engine = _engine_truoc_0132()
    with engine.begin() as cn:
        truoc = cn.execute(text(
            "SELECT id, noi_dung, status, source_kind FROM noi_quy_versions ORDER BY id")).all()
        trang_truoc = cn.execute(text("SELECT COUNT(*) FROM noi_quy_pages")).scalar()

    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)

    with engine.begin() as cn:
        sau = cn.execute(text(
            "SELECT id, noi_dung, status, source_kind FROM noi_quy_versions ORDER BY id")).all()
        assert cn.execute(text("SELECT COUNT(*) FROM noi_quy_pages")).scalar() == trang_truoc
    assert sau == truoc, "nội dung/trạng thái/nguồn phải y nguyên"


def test_0132_chay_lai_lan_hai_KHONG_de_them_tai_lieu_rac():
    """Migration chạy MỖI lần khởi động. Guard theo DỮ LIỆU MỒ CÔI (không phải "đã insert chưa")
    nên lần hai là no-op — và nếu chủ đã tự tạo tài liệu thật thì cũng không đẻ thêm cái nào."""
    engine = _engine_truoc_0132()
    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)
    with engine.begin() as cn:
        cn.execute(text("INSERT INTO noi_quy_documents (title, seq, is_active) "
                        "VALUES ('An toàn lao động', 2, true)"))

    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)   # không được nổ

    with engine.begin() as cn:
        assert cn.execute(text("SELECT COUNT(*) FROM noi_quy_documents")).scalar() == 2, \
            "lần hai không được đẻ thêm tài liệu"


def test_0132_bo_qua_khi_chua_co_bang():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_noi_quy_nhieu_tai_lieu(db)   # không được nổ


def test_bo_qua_khi_chua_co_bang():
    """DB trắng: `create_all` chưa chạy ⇒ chưa có bảng nào. Migration phải im lặng bỏ qua, không nổ.

    Đây là thứ tự thật lúc khởi động một DB mới hoàn toàn."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        _migrate_noi_quy_nguon_va_file_goc(db)   # không được nổ
