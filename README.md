<<<<<<< HEAD
# Huffman Compression Project

A Flask dashboard for compressing files, keeping SQLite-backed history, viewing Huffman codes, and downloading compressed outputs.

## Supported File Types

| File Type | Compression Method | Decompression |
|-----------|--------------------|---------------|
| `.txt` / `.bin` | Huffman entropy coding | Yes, built in |
| `.pdf` | Page/image re-encoding via PyMuPDF and Pillow | Not required |
| `.doc` / `.docx` | Embedded image optimization and ZIP repacking | Not required |

Quality levels apply to PDF and DOCX jobs:

| Quality | PDF Settings | DOCX Settings |
|---------|--------------|---------------|
| `low` | DPI 72, JPEG 40% | JPEG 40%, max image dimension 800px |
| `medium` | DPI 120, JPEG 65% | JPEG 65%, max image dimension 1200px |
| `high` | DPI 150, JPEG 80% | JPEG 80%, max image dimension 1600px |

## Project Structure

```text
huffman_project/
├── app.py
├── huffman.py
├── pdf_compressor.py
├── docx_compressor.py
├── database.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── images/
├── uploads/
├── compressed/
├── decompressed/
└── history/
    └── huffman.db
```

The database file is created automatically the first time the app starts.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

## API Summary

- `POST /api/compress` accepts `file` and optional `quality=low|medium|high`.
- `POST /api/decompress` accepts Huffman `.huf` files.
- `GET /api/history` returns recent jobs. Add `?type=text|pdf|docx` to filter.
- `GET /api/history/<id>/detail` returns one full history row.
- `DELETE /api/history` clears all history.
- `DELETE /api/history/<id>` deletes one job.
- `GET /api/codes/<id>` returns Huffman codes for text jobs.
- `GET /api/stats` returns dashboard summary metrics.
=======
# Pdf-compression-
Full-stack Flask application for file compression and decompression with Huffman Coding, PDF/DOCX optimization, SQLite database, and interactive dashboard.
