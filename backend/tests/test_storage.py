"""Tầng kho file (app/storage.py) — quy tắc khoá/URL và đường ghi đĩa.

Khoá là hợp đồng dữ liệu: cột `file_url` trong DB sinh ra từ đây, nên `url_from_key` và
`key_from_url` phải khứ hồi khớp nhau, và `is_safe_key` phải chặn được đường dẫn vượt thư mục
trước khi router chạm tới đĩa.
"""
from __future__ import annotations

import pytest

from app.storage import (
    LocalStorage,
    StorageFileNotFound,
    is_safe_key,
    key_from_url,
    make_key,
    safe_name,
    url_from_key,
)


def test_url_va_key_khu_hoi():
    key = "hr/12/ab12cd34_cccd.jpg"
    assert key_from_url(url_from_key(key)) == key


def test_key_from_url_bo_qua_url_la():
    assert key_from_url(None) is None
    assert key_from_url("") is None
    assert key_from_url("/static/hr/1/x.jpg") is None  # tiền tố cũ, không còn phục vụ
    assert key_from_url("https://cdn.example.com/x.jpg") is None


def test_make_key_co_token_chong_trung_ten():
    key1, safe1 = make_key("hr", 12, "cccd.jpg")
    key2, safe2 = make_key("hr", 12, "cccd.jpg")
    assert safe1 == safe2 == "cccd.jpg"
    assert key1 != key2  # cùng tên, cùng chủ → vẫn không đè nhau
    assert key1.startswith("hr/12/") and key1.endswith("_cccd.jpg")


def test_safe_name_chan_traversal_va_ky_tu_cam():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name(r"C:\Users\me\cccd.jpg") == "cccd.jpg"
    assert safe_name(None) == "file"
    assert safe_name("   ") == "file"
    assert ":" not in safe_name('a:b*c?.jpg')


@pytest.mark.parametrize(
    "key",
    ["hr/12/x.jpg", "avatars/user_1_ab.png", "ke-toan-thu/3/hoa-don.pdf"],
)
def test_is_safe_key_chap_nhan_khoa_hop_le(key):
    assert is_safe_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/hr/12/x.jpg",          # tuyệt đối
        "hr/../../dev.db",       # vượt thư mục
        "hr//x.jpg",             # đoạn rỗng
        "hr\\12\\x.jpg",         # tách kiểu Windows
        "C:/Windows/x.ini",      # có ổ đĩa
        "hr/12/x\x00.jpg",       # null byte
    ],
)
def test_is_safe_key_tu_choi_khoa_nguy_hiem(key):
    assert not is_safe_key(key)


def test_local_storage_ghi_doc_xoa(tmp_path):
    store = LocalStorage(root=tmp_path)
    key = "hr/12/ab_cccd.jpg"

    store.save(key, b"noi-dung", "image/jpeg")
    stream, size, content_type = store.open_stream(key)
    assert b"".join(stream) == b"noi-dung"
    assert size == len(b"noi-dung")
    assert content_type is None  # đĩa không giữ content-type — router tự đoán theo đuôi

    store.delete(key)
    with pytest.raises(StorageFileNotFound):
        store.open_stream(key)


def test_local_storage_xoa_file_khong_co_thi_im_lang(tmp_path):
    # Xoá là dọn dẹp best-effort: file rác không được làm hỏng việc xoá bản ghi.
    LocalStorage(root=tmp_path).delete("khong/co/that.jpg")
