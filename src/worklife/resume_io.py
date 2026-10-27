"""Text extraction for locally uploaded resumes; no external model or OCR calls."""

import io
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000


def extract_resume(filename, data):
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Укажите имя файла резюме")
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Размер резюме должен быть от 1 байта до 10 МБ")
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1251")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as document:
                if document.getinfo("word/document.xml").file_size > 5 * 1024 * 1024:
                    raise ValueError("Текст документа слишком большой")
                root = ElementTree.fromstring(document.read("word/document.xml"))
            prefix = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            removed = {prefix + "del", prefix + "moveFrom"}

            def visible(node):
                if node.tag in removed:
                    return ""
                if node.tag == prefix + "t":
                    return node.text or ""
                if node.tag == prefix + "tab":
                    return "\t"
                if node.tag in {prefix + "br", prefix + "cr"}:
                    return "\n"
                return "".join(visible(child) for child in node)

            def paragraphs(node):
                if node.tag in removed:
                    return
                if node.tag == prefix + "p":
                    yield visible(node)
                else:
                    for child in node:
                        yield from paragraphs(child)

            text = "\n\n".join(paragraphs(root))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            raise ValueError("Не удалось прочитать DOCX") from None
    elif suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("PDF защищён паролем. Загрузите доступную копию или текст")
            if len(reader.pages) > 100:
                raise ValueError("Резюме должно содержать не более 100 страниц")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except PyPdfError:
            raise ValueError("Не удалось прочитать PDF") from None
    else:
        raise ValueError("Поддерживаются PDF, DOCX, TXT и Markdown")
    text = text.strip()
    if not text:
        raise ValueError("В файле нет извлекаемого текста. Для скана нужен текст после OCR")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Текст резюме превышает 200 000 символов")
    return text
