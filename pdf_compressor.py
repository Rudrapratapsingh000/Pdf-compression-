import io
import os


SUPPORTED_PDF_QUALITIES = {
    "low": {"dpi": 72, "jpeg_quality": 40},
    "medium": {"dpi": 120, "jpeg_quality": 65},
    "high": {"dpi": 150, "jpeg_quality": 80},
}


class PasswordProtectedPDFError(Exception):
    pass


def compress_pdf(input_path: str, output_path: str, quality: str = "medium") -> dict:
    try:
        import fitz
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing PDF dependencies. Install PyMuPDF and Pillow from requirements.txt."
        ) from exc

    settings = SUPPORTED_PDF_QUALITIES.get(quality, SUPPORTED_PDF_QUALITIES["medium"])
    dpi = settings["dpi"]
    jpeg_quality = settings["jpeg_quality"]

    src_doc = fitz.open(input_path)
    if src_doc.needs_pass:
        src_doc.close()
        raise PasswordProtectedPDFError()

    out_doc = fitz.open()
    page_count = src_doc.page_count
    image_count = sum(len(page.get_images(full=True)) for page in src_doc)

    try:
        for page in src_doc:
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            image_bytes = buffer.getvalue()

            out_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            out_page.insert_image(out_page.rect, stream=image_bytes)

        out_doc.set_metadata({})
        out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    finally:
        src_doc.close()
        out_doc.close()

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    space_saved = round((1 - compressed_size / original_size) * 100, 2) if original_size else 0
    ratio = round(original_size / compressed_size, 4) if compressed_size else 1.0

    return {
        "page_count": page_count,
        "image_count": image_count,
        "dpi_used": dpi,
        "original_size": original_size,
        "compressed_size": compressed_size,
        "space_saved_percent": space_saved,
        "compression_ratio": ratio,
        "total_chars": 0,
        "total_bits": 0,
    }
