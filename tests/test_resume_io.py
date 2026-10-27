import io
import zipfile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from worklife.resume_io import extract_resume


def test_docx_extracts_current_visible_text_and_preserves_separators():
    xml = b"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Python</w:t><w:tab/><w:t>SQL</w:t><w:br/><w:t>Experience</w:t></w:r><w:del><w:r><w:delText>Removed certification</w:delText></w:r></w:del></w:p><w:del><w:p><w:r><w:t>Deleted paragraph</w:t></w:r></w:p></w:del><w:p><w:ins><w:r><w:t>Current work</w:t></w:r></w:ins></w:p></w:body></w:document>"""
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert extract_resume("cv.docx", data.getvalue()) == "Python\tSQL\nExperience\n\nCurrent work"


def test_pdf_extracts_actual_text_and_reports_empty_scan():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Python services) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    assert "Python services" in extract_resume("cv.pdf", data.getvalue())
    blank = PdfWriter()
    blank.add_blank_page(width=612, height=792)
    empty = io.BytesIO()
    blank.write(empty)
    with pytest.raises(ValueError, match="OCR"):
        extract_resume("scan.pdf", empty.getvalue())
