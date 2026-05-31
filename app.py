import os

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from database import (
    clear_history,
    delete_job,
    get_all_history,
    get_codes_for_job,
    get_job_detail,
    get_stats_summary,
    init_db,
    insert_compression_record,
    insert_huffman_codes,
)
from docx_compressor import CorruptDocxError, compress_docx
from huffman import compress_file, decompress_file
from pdf_compressor import PasswordProtectedPDFError, compress_pdf


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
COMPRESSED_FOLDER = os.path.join(BASE_DIR, "compressed")
DECOMPRESSED_FOLDER = os.path.join(BASE_DIR, "decompressed")
ALLOWED_QUALITIES = {"low", "medium", "high"}


app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["COMPRESSED_FOLDER"] = COMPRESSED_FOLDER
app.config["DECOMPRESSED_FOLDER"] = DECOMPRESSED_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


for folder in (UPLOAD_FOLDER, COMPRESSED_FOLDER, DECOMPRESSED_FOLDER):
    os.makedirs(folder, exist_ok=True)

with app.app_context():
    init_db()


def detect_file_type(filename: str) -> str:
    extension = os.path.splitext(filename)[1].lower()
    if extension == ".pdf":
        return "pdf"
    if extension in (".doc", ".docx"):
        return "docx"
    return "text"


def _unique_filename(directory: str, filename: str) -> str:
    stem, extension = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{stem}_{counter}{extension}"
        counter += 1
    return candidate


def _compressed_filename(original_filename: str, file_type: str, quality: str) -> str:
    stem = os.path.splitext(original_filename)[0]
    if file_type == "pdf":
        return f"{stem}_compressed_{quality}.pdf"
    if file_type == "docx":
        return f"{stem}_compressed_{quality}.docx"
    return f"{stem}_huffman.huf"


def _decompressed_filename(original_filename: str, fallback_filename: str) -> str:
    original = secure_filename(original_filename) if original_filename else ""
    if original:
        stem, extension = os.path.splitext(original)
        return f"{stem}_decompressed{extension or '.bin'}"

    stem = os.path.splitext(secure_filename(fallback_filename))[0]
    return f"{stem}_decompressed.bin"


def _warning_if_larger(result: dict) -> str | None:
    if result["compressed_size"] >= result["original_size"]:
        return "Compressed file is not smaller than the original. Try a lower quality setting."
    return None


def _insert_pdf_history(original_filename: str, compressed_filename: str, quality: str, result: dict) -> int:
    history_id = insert_compression_record({
        "original_filename": original_filename,
        "compressed_filename": compressed_filename,
        "file_type": "pdf",
        "quality_level": quality,
        "original_size": result["original_size"],
        "compressed_size": result["compressed_size"],
        "space_saved_percent": result["space_saved_percent"],
        "total_chars": result["total_chars"],
        "total_bits": result["total_bits"],
        "compression_ratio": result["compression_ratio"],
        "pdf_page_count": result["page_count"],
        "pdf_image_count": result["image_count"],
        "pdf_dpi_used": result["dpi_used"],
    })
    insert_huffman_codes(history_id, {}, {})
    return history_id


def _insert_docx_history(original_filename: str, compressed_filename: str, quality: str, result: dict) -> int:
    history_id = insert_compression_record({
        "original_filename": original_filename,
        "compressed_filename": compressed_filename,
        "file_type": "docx",
        "quality_level": quality,
        "original_size": result["original_size"],
        "compressed_size": result["compressed_size"],
        "space_saved_percent": result["space_saved_percent"],
        "total_chars": result["total_chars"],
        "total_bits": result["total_bits"],
        "compression_ratio": result["compression_ratio"],
        "docx_paragraph_count": result["paragraph_count"],
        "docx_image_count": result["image_count"],
        "docx_table_count": result["table_count"],
    })
    insert_huffman_codes(history_id, {}, {})
    return history_id


def _insert_text_history(original_filename: str, compressed_filename: str, result: dict) -> int:
    history_id = insert_compression_record({
        "original_filename": original_filename,
        "compressed_filename": compressed_filename,
        "file_type": "text",
        "quality_level": None,
        "original_size": result["original_size"],
        "compressed_size": result["compressed_size"],
        "space_saved_percent": result["space_saved_percent"],
        "total_chars": result["total_chars"],
        "total_bits": result["total_bits"],
        "compression_ratio": result["compression_ratio"],
    })
    insert_huffman_codes(history_id, result["huffman_codes"], result["frequency_table"])
    return history_id


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/compress")
def compress_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file was uploaded."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Please choose a file to compress."}), 400

    original_filename = secure_filename(uploaded_file.filename)
    file_type = detect_file_type(original_filename)
    quality = request.form.get("quality", "medium")
    if quality not in ALLOWED_QUALITIES:
        quality = "medium"

    upload_filename = _unique_filename(UPLOAD_FOLDER, original_filename)
    upload_path = os.path.join(UPLOAD_FOLDER, upload_filename)
    uploaded_file.save(upload_path)

    compressed_filename = _unique_filename(
        COMPRESSED_FOLDER,
        _compressed_filename(original_filename, file_type, quality),
    )
    compressed_path = os.path.join(COMPRESSED_FOLDER, compressed_filename)

    try:
        if file_type == "pdf":
            result = compress_pdf(upload_path, compressed_path, quality=quality)
            history_id = _insert_pdf_history(original_filename, compressed_filename, quality, result)
        elif file_type == "docx":
            result = compress_docx(upload_path, compressed_path, quality=quality)
            history_id = _insert_docx_history(original_filename, compressed_filename, quality, result)
        else:
            result = compress_file(upload_path, compressed_path, original_filename=original_filename)
            history_id = _insert_text_history(original_filename, compressed_filename, result)
    except PasswordProtectedPDFError:
        return jsonify({
            "error": "PDF is password-protected. Please remove the password before compressing."
        }), 400
    except CorruptDocxError:
        return jsonify({
            "error": "Could not read the DOCX file. It may be corrupt or an unsupported format."
        }), 400
    except Exception as exc:
        return jsonify({"error": f"Compression failed: {exc}"}), 500

    response = {
        "success": True,
        "history_id": history_id,
        "file_type": file_type,
        "quality": quality if file_type in ("pdf", "docx") else None,
        "original_filename": original_filename,
        "compressed_filename": compressed_filename,
        "download_url": url_for("download_compressed_file", filename=compressed_filename),
        "original_size": result["original_size"],
        "compressed_size": result["compressed_size"],
        "space_saved_percent": result["space_saved_percent"],
        "total_chars": result["total_chars"],
        "total_bits": result["total_bits"],
        "compression_ratio": result["compression_ratio"],
        "pdf_page_count": result.get("page_count"),
        "pdf_image_count": result.get("image_count"),
        "pdf_dpi_used": result.get("dpi_used"),
        "docx_paragraph_count": result.get("paragraph_count"),
        "docx_image_count": result.get("image_count"),
        "docx_table_count": result.get("table_count"),
    }

    warning = _warning_if_larger(result)
    if warning:
        response["warning"] = warning

    return jsonify(response)


@app.post("/api/decompress")
def decompress_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file was uploaded."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Please choose a .huf file to decompress."}), 400

    compressed_filename = secure_filename(uploaded_file.filename)
    upload_filename = _unique_filename(UPLOAD_FOLDER, compressed_filename)
    upload_path = os.path.join(UPLOAD_FOLDER, upload_filename)
    uploaded_file.save(upload_path)

    try:
        header_probe = decompress_file
        output_name = _unique_filename(DECOMPRESSED_FOLDER, f"{os.path.splitext(compressed_filename)[0]}_decompressed.bin")
        output_path = os.path.join(DECOMPRESSED_FOLDER, output_name)
        result = header_probe(upload_path, output_path)

        desired_name = _decompressed_filename(result.get("original_filename", ""), compressed_filename)
        desired_name = _unique_filename(DECOMPRESSED_FOLDER, desired_name)
        desired_path = os.path.join(DECOMPRESSED_FOLDER, desired_name)
        if desired_path != output_path:
            os.replace(output_path, desired_path)
            output_name = desired_name
    except Exception as exc:
        return jsonify({"error": f"Decompression failed: {exc}"}), 400

    return jsonify({
        "success": True,
        "decompressed_filename": output_name,
        "download_url": url_for("download_decompressed_file", filename=output_name),
        "compressed_size": result["compressed_size"],
        "decompressed_size": os.path.getsize(os.path.join(DECOMPRESSED_FOLDER, output_name)),
    })


@app.get("/api/codes/<int:history_id>")
def api_codes(history_id: int):
    return jsonify(get_codes_for_job(history_id))


@app.get("/api/history")
def api_history():
    file_type = request.args.get("type")
    if file_type not in {"text", "pdf", "docx"}:
        file_type = None
    return jsonify(get_all_history(file_type=file_type))


@app.get("/api/history/<int:history_id>/detail")
def api_history_detail(history_id: int):
    row = get_job_detail(history_id)
    if not row:
        return jsonify({"error": "Not found"}), 404
    row["download_url"] = url_for("download_compressed_file", filename=row["compressed_filename"])
    return jsonify(row)


@app.delete("/api/history")
def api_clear_history():
    clear_history()
    return jsonify({"success": True})


@app.delete("/api/history/<int:history_id>")
def api_delete_history_item(history_id: int):
    delete_job(history_id)
    return jsonify({"success": True})


@app.get("/api/stats")
def api_stats():
    return jsonify(get_stats_summary())


@app.get("/download/compressed/<path:filename>")
def download_compressed_file(filename: str):
    return send_from_directory(COMPRESSED_FOLDER, filename, as_attachment=True)


@app.get("/download/decompressed/<path:filename>")
def download_decompressed_file(filename: str):
    return send_from_directory(DECOMPRESSED_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
