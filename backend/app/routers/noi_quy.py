"""Nội quy công ty (module quyền `noi_quy`) — chủ 30/07/2026.

Giám đốc soạn + ban hành; **mọi nhân viên đọc được**.

⚠️ `GET /current` CỐ Ý chỉ đòi đăng nhập, KHÔNG gác `require_permission` — xem chú thích tại chỗ.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from ..deps import CurrentUser, get_noi_quy_service, get_user_repository, require_permission
from ..models.user import User
from ..repositories.user_repo import UserRepository
from ..schemas.noi_quy import (
    NoiQuyAttachmentOut,
    NoiQuyDocumentIn,
    NoiQuyDocumentPatch,
    NoiQuyDocumentRow,
    NoiQuyDocumentsOut,
    NoiQuyDraftIn,
    NoiQuyOut,
    NoiQuyPageOut,
    NoiQuyVersionRow,
    NoiQuyVersionsOut,
)
from ..services.noi_quy_service import (
    NoiQuyError,
    NoiQuyInfrastructureError,
    NoiQuyNotFound,
    NoiQuyService,
    NoiQuyValidationError,
    pdf_thanh_anh,
)
from ..storage import get_storage, make_key, url_from_key

router = APIRouter(prefix="/api/noi-quy", tags=["noi_quy"])

MODULE = "noi_quy"

# Thư mục lưu file trong kho chung. CỐ Ý KHÔNG khai trong `_PREFIX_PERMISSION` của
# `routers/files.py` ⇒ ai đăng nhập cũng tải được (giống `avatars/`). Thêm vào bảng đó là chỉ
# Giám đốc mở được PDF — phá đúng yêu cầu "tất cả nhân viên thấy". Có test canh.
_NQ_SUBDIR = "noi-quy"

# Chặn loại + dung lượng NGAY TẠI SERVER. Chốt phía FE chỉ là phép lịch sự — ai gọi thẳng API là
# đi vòng qua nó. Bản nội quy đã ký thường là PDF/ảnh chụp; 20 MB là rộng rãi cho một văn bản
# scan mà vẫn chặn được người tải nhầm cả thư mục ảnh vào đây.
_NQ_MAX_BYTES = 20 * 1024 * 1024
# Ảnh trong THÂN nội quy — hẹp hơn đính kèm: chỉ ảnh, vì nó được nhúng thẳng vào trang mọi
# nhân viên mở. PDF/Word thì thuộc về đính kèm, không nhúng vào bài.
_NQ_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
_NQ_ALLOWED_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
}
_NQ_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}

Service = Annotated[NoiQuyService, Depends(get_noi_quy_service)]
Users = Annotated[UserRepository, Depends(get_user_repository)]
Editor = Annotated[User, Depends(require_permission(MODULE, "update"))]


def _raise(exc: Exception) -> None:
    if isinstance(exc, NoiQuyNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NoiQuyInfrastructureError):
        # 503 chứ KHÔNG 400. Mã 4xx nghĩa là "bạn gửi sai" — người dùng sẽ đi sửa file của mình
        # trong khi lỗi nằm ở server. Mã sai làm người ta chữa sai chỗ.
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, NoiQuyValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _ten_nguoi(users: UserRepository, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = users.get_by_id(user_id)
    return (u.name or u.username) if u is not None else None


def _out(svc: NoiQuyService, users: UserRepository, v) -> NoiQuyOut:
    if v is None:
        return NoiQuyOut(has_content=False)
    return NoiQuyOut(
        has_content=True, id=v.id, document_id=v.document_id, title=v.title,
        noi_dung=v.noi_dung or "", ghi_chu=v.ghi_chu,
        source_kind=v.source_kind, status=v.status, published_at=v.published_at,
        updated_at=v.updated_at, published_by_name=_ten_nguoi(users, v.published_by),
        attachments=[NoiQuyAttachmentOut.model_validate(a) for a in svc.attachments(v.id)],
        pages=[NoiQuyPageOut.model_validate(p) for p in svc.pages(v.id)],
    )


# --- ĐỌC: mọi nhân viên -----------------------------------------------------


@router.get("/documents", response_model=NoiQuyDocumentsOut)
def list_documents(svc: Service, user: CurrentUser) -> NoiQuyDocumentsOut:
    """DANH SÁCH TÀI LIỆU cho cột phải — ai đăng nhập cũng gọi được.

    ⚠️ **Đây là endpoint dễ gác nhầm quyền nhất của cả module.** Thêm `require_permission` vào đây
    là cả công ty mở màn nội quy ra thấy cột phải TRỐNG — không còn đường nào tới nội dung. Cùng lý
    lẽ với `GET /current`.

    Chỉ trả tài liệu đang dùng VÀ đã ban hành ít nhất một lần: tiêu đề chưa có nội dung thì bấm vào
    ra trang trắng, trông y như hỏng."""
    return NoiQuyDocumentsOut(items=[
        NoiQuyDocumentRow(id=d.id, title=d.title, seq=d.seq, is_active=d.is_active,
                          published_at=v.published_at)
        for d, v in svc.documents_for_reader()
    ])


@router.get("/documents/tat-ca", response_model=NoiQuyDocumentsOut)
def list_documents_for_editor(svc: Service, user: Editor) -> NoiQuyDocumentsOut:
    """Danh sách cho NGƯỜI SOẠN — kèm tài liệu chưa ban hành và tài liệu đã ẩn.

    Khai TRƯỚC `/documents/{doc_id}/current` không bắt buộc (khác số đoạn đường dẫn) nhưng để cạnh
    nhau cho dễ đọc."""
    return NoiQuyDocumentsOut(items=[
        NoiQuyDocumentRow(id=d.id, title=d.title, seq=d.seq, is_active=d.is_active,
                          published_at=v.published_at if v else None,
                          co_nhap=svc.co_nhap(d.id))
        for d, v in svc.documents_for_editor()
    ])


@router.get("/documents/{doc_id}/current", response_model=NoiQuyOut)
def document_current(doc_id: int, svc: Service, users: Users, user: CurrentUser) -> NoiQuyOut:
    """Bản đang hiệu lực của MỘT tài liệu — ai đăng nhập cũng đọc được (xem `/documents`)."""
    return _out(svc, users, svc.current(doc_id))


@router.get("/current", response_model=NoiQuyOut)
def current(svc: Service, users: Users, user: CurrentUser) -> NoiQuyOut:
    """Bản nội quy ĐANG HIỆU LỰC — ai đăng nhập cũng đọc được.

    ⚠️ KHÔNG gác `require_permission` là CỐ Ý, đừng "siết bảo mật" thêm vào đây. Gác bằng ô quyền
    thì phải nhớ cấp cho MỌI vai; quên một vai là người đó không đọc được nội quy — mà "tất cả
    nhân viên thấy" chính là yêu cầu. Cùng cách `GET /api/employees/me` đang làm.

    Chỉ trả bản `published`: bản nháp Giám đốc đang viết dở KHÔNG lọt ra đây.

    Từ khi có nhiều tài liệu, endpoint này trả tài liệu ĐẦU DANH SÁCH. Giữ lại thêm một nhịp phát
    hành để lúc deploy, bản giao diện cũ đang mở sẵn trong trình duyệt nhân viên không gãy."""
    return _out(svc, users, svc.current_dau_tien())


# --- SOẠN THẢO: chỉ vai có quyền (hiện là Giám đốc) -------------------------


@router.post("/documents", response_model=NoiQuyDocumentRow, status_code=201)
def create_document(body: NoiQuyDocumentIn, svc: Service, user: Editor) -> NoiQuyDocumentRow:
    """Tạo một tài liệu mới trong bộ nội quy (chưa có nội dung)."""
    try:
        d = svc.create_document(title=body.title)
    except NoiQuyError as exc:
        _raise(exc)
    return NoiQuyDocumentRow(id=d.id, title=d.title, seq=d.seq, is_active=d.is_active)


@router.patch("/documents/{doc_id}", response_model=NoiQuyDocumentRow)
def patch_document(doc_id: int, body: NoiQuyDocumentPatch, svc: Service,
                   user: Editor) -> NoiQuyDocumentRow:
    """Đổi tên / xếp lại thứ tự / ẩn. **KHÔNG có DELETE** — xem chú thích ở model `NoiQuyDocument`:
    xoá tài liệu là kéo theo cả lịch sử ban hành + ảnh trang + hàng file qua CASCADE."""
    try:
        d = svc.update_document(doc_id, title=body.title, seq=body.seq, is_active=body.is_active)
    except NoiQuyError as exc:
        _raise(exc)
    return NoiQuyDocumentRow(id=d.id, title=d.title, seq=d.seq, is_active=d.is_active)


@router.get("/documents/{doc_id}/versions", response_model=NoiQuyVersionsOut)
def list_versions(doc_id: int, svc: Service, users: Users, user: Editor) -> NoiQuyVersionsOut:
    """Lịch sử các bản ĐÃ ban hành CỦA MỘT TÀI LIỆU — để tra "hồi tháng 5 luật là gì"."""
    return NoiQuyVersionsOut(items=[
        NoiQuyVersionRow(id=v.id, ghi_chu=v.ghi_chu, published_at=v.published_at,
                         published_by_name=_ten_nguoi(users, v.published_by))
        for v in svc.list_versions(doc_id)
    ])


@router.get("/documents/{doc_id}/draft", response_model=NoiQuyOut)
def get_draft(doc_id: int, svc: Service, users: Users, user: Editor) -> NoiQuyOut:
    """Mở nháp của MỘT tài liệu. Chưa có thì tạo, chép sẵn nội dung + file + ảnh trang của bản
    hiệu lực CỦA CHÍNH TÀI LIỆU ĐÓ."""
    try:
        v = svc.get_or_create_draft(doc_id)
    except NoiQuyError as exc:
        _raise(exc)
    return _out(svc, users, v)


@router.put("/documents/{doc_id}/draft", response_model=NoiQuyOut)
def save_draft(doc_id: int, body: NoiQuyDraftIn, svc: Service, users: Users,
               user: Editor) -> NoiQuyOut:
    """Lưu nháp — KHÔNG đụng bản nhân viên đang đọc."""
    try:
        v = svc.save_draft(doc_id, noi_dung=body.noi_dung, ghi_chu=body.ghi_chu,
                           source_kind=body.source_kind)
    except NoiQuyError as exc:
        _raise(exc)
    return _out(svc, users, v)


@router.post("/documents/{doc_id}/publish", response_model=NoiQuyOut)
def publish(doc_id: int, svc: Service, users: Users, user: Editor) -> NoiQuyOut:
    """Ban hành MỘT tài liệu. Các tài liệu khác giữ nguyên ngày ban hành cũ."""
    try:
        v = svc.publish(doc_id, actor=user)
    except NoiQuyError as exc:
        _raise(exc)
    return _out(svc, users, v)


@router.post("/documents/{doc_id}/draft/ban-goc-pdf", response_model=NoiQuyOut)
async def dat_ban_goc_pdf(
    doc_id: int,
    svc: Service,
    users: Users,
    user: Editor,
    file: UploadFile = File(...),
) -> NoiQuyOut:
    """Tải bản nội quy PDF lên cho MỘT tài liệu và **hiện đúng bản đó** — đường "giữ nguyên dáng".

    Dựng ảnh từng trang, nên bố cục, kiểu chữ, canh lề, chữ ký, dấu đỏ đều giữ nguyên 100%. Bản
    SCAN cũng dùng được — không cần lớp chữ, không cần OCR.

    Dựng ảnh NGAY LÚC TẢI LÊN, không đợi tới lúc ban hành: chủ thấy luôn đúng thứ nhân viên sẽ
    thấy, và nếu file có vấn đề thì biết ngay chứ không phải lúc bấm Ban hành."""
    loai = (file.content_type or "").lower()
    ten = (file.filename or "").lower()
    if loai != "application/pdf" and not ten.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chức năng này chỉ nhận file PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tệp rỗng.")
    if len(data) > _NQ_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Tệp vượt quá 20 MB.")

    try:
        anh_trang = pdf_thanh_anh(data)
    except NoiQuyError as exc:
        _raise(exc)

    try:
        draft = svc.get_or_create_draft(doc_id)
    except NoiQuyError as exc:
        _raise(exc)
    store = get_storage()

    # Ghi file GỐC trước, rồi mới tới ảnh: file gốc là thứ chủ tải lên và là chứng từ đối chiếu.
    key_goc, ten_an_toan = make_key(_NQ_SUBDIR, draft.id, file.filename)
    store.save(key_goc, data, file.content_type)

    trang: list[tuple[str, int, int]] = []
    for so, (anh, rong, cao) in enumerate(anh_trang, start=1):
        key, _ = make_key(_NQ_SUBDIR, f"{draft.id}-trang", f"{so:03d}.jpg")
        store.save(key, anh, "image/jpeg")
        trang.append((url_from_key(key), rong, cao))

    try:
        v = svc.dat_ban_goc_pdf(
            doc_id, trang=trang, file_name=ten_an_toan, file_url=url_from_key(key_goc),
            file_type=file.content_type, actor=user,
        )
    except NoiQuyError as exc:
        _raise(exc)
    return _out(svc, users, v)


@router.post("/documents/{doc_id}/draft/attachments", response_model=NoiQuyAttachmentOut,
             status_code=201)
async def upload_attachment(
    doc_id: int,
    svc: Service,
    user: Editor,
    file: UploadFile = File(...),
) -> NoiQuyAttachmentOut:
    """Đính bản PDF/Word đã ký vào BẢN NHÁP (bản đã ban hành không sửa được)."""
    loai = (file.content_type or "").lower()
    ten = (file.filename or "").lower()
    extension_hop_le = any(ten.endswith(ext) for ext in _NQ_ALLOWED_EXTENSIONS)
    loai_chung = loai in {"", "application/octet-stream"}
    if loai not in _NQ_ALLOWED_TYPES and not (loai_chung and extension_hop_le):
        raise HTTPException(
            status_code=400,
            detail="Chỉ nhận file PDF, Word hoặc ảnh (JPG/PNG).",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tệp rỗng.")
    if len(data) > _NQ_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Tệp vượt quá 20 MB.")

    try:
        draft = svc.get_or_create_draft(doc_id)
    except NoiQuyError as exc:
        _raise(exc)
    key, safe_name = make_key(_NQ_SUBDIR, draft.id, file.filename)
    get_storage().save(key, data, file.content_type)
    try:
        att = svc.add_attachment(
            version_id=draft.id, file_name=safe_name, file_url=url_from_key(key),
            file_type=file.content_type, actor=user,
        )
    except NoiQuyError as exc:
        _raise(exc)
    return NoiQuyAttachmentOut.model_validate(att)


@router.post("/draft/images", status_code=201)
async def upload_image(
    user: Editor,
    file: UploadFile = File(...),
) -> dict:
    """Tải MỘT ảnh nằm TRONG thân nội quy, trả về URL để nhúng vào `<img src>`.

    Vì sao cần endpoint riêng thay vì để ảnh nằm luôn trong nội dung: khi nhập từ file Word,
    thư viện chuyển đổi mặc định nhúng ảnh thành chuỗi base64 ngay trong HTML. Một nội quy có
    vài ảnh chữ ký là `noi_dung` phình vài MB — và **mọi nhân viên tải lại chừng đó mỗi lần mở
    màn**. Đẩy ảnh ra kho file thì `noi_dung` chỉ còn thẻ `<img src="/api/files/...">`.

    Khác `POST /draft/attachments`: cái kia là CHỨNG TỪ (bản PDF đã ký, hiện ở cột phải);
    cái này là ảnh nằm trong thân bài, không vào danh sách đính kèm."""
    loai = (file.content_type or "").lower()
    if loai not in _NQ_ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Ảnh trong nội quy phải là JPG hoặc PNG.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Tệp ảnh rỗng.")
    if len(data) > _NQ_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh vượt quá 20 MB.")

    key, _ = make_key(_NQ_SUBDIR, "anh", file.filename)
    get_storage().save(key, data, file.content_type)
    # `lam_sach_html` chỉ giữ `src` bắt đầu bằng `/api/files/` — `url_from_key` cho đúng dạng đó.
    return {"url": url_from_key(key)}


@router.delete(
    "/draft/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_attachment(attachment_id: int, svc: Service, user: Editor) -> Response:
    try:
        svc.delete_attachment(attachment_id=attachment_id)
    except NoiQuyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
