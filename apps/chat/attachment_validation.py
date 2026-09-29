from io import BytesIO
import os
from pathlib import PurePath
from tempfile import NamedTemporaryFile
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
MAX_MESSAGE_LENGTH = 2000
MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 40_000_000

ALLOWED_TYPES = {
    "jpg": ("image/jpeg", "image"),
    "jpeg": ("image/jpeg", "image"),
    "png": ("image/png", "image"),
    "webp": ("image/webp", "image"),
    "pdf": ("application/pdf", "pdf"),
}


class AttachmentValidationError(ValueError):
    pass


def _extension(name):
    parts = PurePath(name or "").name.lower().split(".")
    if len(parts) != 2 or not parts[0] or parts[1] not in ALLOWED_TYPES:
        raise AttachmentValidationError("Formato de arquivo não permitido.")
    return parts[1]


def _verify_clean_image(data, extension):
    with Image.open(BytesIO(data)) as image:
        expected_format = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[extension]
        if image.format != expected_format:
            raise AttachmentValidationError("A imagem processada contém metadados.")
        image.verify()
    with Image.open(BytesIO(data)) as image:
        if image.getexif():
            raise AttachmentValidationError("A imagem processada contém metadados.")
        forbidden_info = {
            "exif", "xmp", "comment", "icc_profile", "photoshop",
            "XML:com.adobe.xmp",
        }
        if forbidden_info.intersection(image.info):
            raise AttachmentValidationError("A imagem processada contém metadados.")


def _validate_image(data, extension):
    temporary_path = None
    try:
        with NamedTemporaryFile(suffix=f".{extension}", delete=False) as temporary:
            temporary.write(data)
            temporary.flush()
            temporary_path = temporary.name
            with Image.open(temporary_path) as image:
                expected_format = {
                    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"
                }[extension]
                if image.format != expected_format:
                    raise AttachmentValidationError("A extensão não corresponde ao conteúdo do arquivo.")
                if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                    raise AttachmentValidationError("Dimensões da imagem não permitidas.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise AttachmentValidationError("Quantidade de pixels não permitida.")
                image.verify()

            with Image.open(temporary_path) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                output = BytesIO()
                normalized.save(
                    output,
                    format=expected_format,
                    exif=b"",
                    icc_profile=None,
                    xmp=b"",
                    comment=None,
                )
                cleaned = output.getvalue()
                _verify_clean_image(cleaned, extension)
                return cleaned
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if isinstance(exc, AttachmentValidationError):
            raise
        raise AttachmentValidationError("Imagem corrompida ou inválida.") from exc
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def validate_attachment(uploaded_file, content):
    if not uploaded_file:
        raise AttachmentValidationError("Anexo obrigatório.")
    if uploaded_file.size == 0:
        raise AttachmentValidationError("O arquivo está vazio.")
    if uploaded_file.size > MAX_ATTACHMENT_SIZE:
        raise AttachmentValidationError("Arquivo muito grande (máximo 10 MB).")
    if len(content) != uploaded_file.size:
        raise AttachmentValidationError("Não foi possível ler o arquivo.")

    extension = _extension(uploaded_file.name)
    expected_mime, attachment_type = ALLOWED_TYPES[extension]
    if (uploaded_file.content_type or "").lower() != expected_mime:
        raise AttachmentValidationError("O MIME declarado não corresponde ao formato permitido.")

    if attachment_type == "image":
        content = _validate_image(content, extension)
    elif not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
        raise AttachmentValidationError("O conteúdo não é um PDF válido.")

    if len(content) > MAX_ATTACHMENT_SIZE:
        raise AttachmentValidationError("Arquivo processado muito grande (máximo 10 MB).")

    filename = f"{uuid4().hex}.{extension}"
    return ContentFile(content, name=filename), attachment_type
