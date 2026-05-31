const els = {
    compressForm: document.querySelector("#compress-form"),
    decompressForm: document.querySelector("#decompress-form"),
    fileInput: document.querySelector("#file-input"),
    fileHint: document.querySelector("#file-hint"),
    fileTypePill: document.querySelector("#file-type-pill"),
    qualitySelect: document.querySelector("#quality-select"),
    compressStatus: document.querySelector("#compress-status"),
    decompressStatus: document.querySelector("#decompress-status"),
    resultPanel: document.querySelector("#result-panel"),
    decompressResult: document.querySelector("#decompress-result"),
    historyBody: document.querySelector("#history-body"),
    modal: document.querySelector("#modal"),
    modalTitle: document.querySelector("#modal-title"),
    modalBody: document.querySelector("#modal-body"),
};

let activeHistoryType = "";

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (Math.abs(value) < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB"];
    let size = value / 1024;
    let index = 0;
    while (Math.abs(size) >= 1024 && index < units.length - 1) {
        size /= 1024;
        index += 1;
    }
    return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function relativeTime(isoValue) {
    if (!isoValue) return "";
    const date = new Date(`${isoValue}${isoValue.endsWith("Z") ? "" : "Z"}`);
    const seconds = Math.round((date.getTime() - Date.now()) / 1000);
    const absolute = Math.abs(seconds);
    const units = [
        ["year", 31536000],
        ["month", 2592000],
        ["day", 86400],
        ["hour", 3600],
        ["minute", 60],
    ];
    for (const [unit, unitSeconds] of units) {
        if (absolute >= unitSeconds) {
            const amount = Math.round(seconds / unitSeconds);
            return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(amount, unit);
        }
    }
    return "just now";
}

function fileTypeFromName(filename) {
    const lower = filename.toLowerCase();
    if (lower.endsWith(".pdf")) return "pdf";
    if (lower.endsWith(".doc") || lower.endsWith(".docx")) return "docx";
    return "text";
}

function typeLabel(type) {
    if (type === "pdf") return "PDF";
    if (type === "docx") return "DOCX";
    return "TEXT";
}

function savedClass(percent) {
    const value = Number(percent) || 0;
    if (value >= 30) return "saved-good";
    if (value >= 10) return "saved-mid";
    return "saved-low";
}

function setStatus(element, message, kind = "") {
    element.textContent = message;
    element.className = `status ${kind}`.trim();
}

function updateFileHint() {
    const file = els.fileInput.files[0];
    if (!file) {
        els.fileHint.textContent = "Choose a .txt, .bin, .pdf, .doc, or .docx file.";
        els.fileTypePill.textContent = "No file";
        els.fileTypePill.className = "pill neutral";
        return;
    }

    const type = fileTypeFromName(file.name);
    const messages = {
        text: "Huffman entropy coding will be applied.",
        pdf: "PDF images will be re-compressed at chosen quality.",
        docx: "Embedded images will be re-compressed at chosen quality.",
    };
    els.fileHint.textContent = messages[type];
    els.fileTypePill.textContent = typeLabel(type);
    els.fileTypePill.className = `badge ${type}`;
}

function resultMetric(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function renderCompressionResult(data) {
    const rows = [
        resultMetric("Original", formatBytes(data.original_size)),
        resultMetric("Compressed", formatBytes(data.compressed_size)),
        resultMetric("Saved", `${data.space_saved_percent}%`),
        resultMetric("Ratio", `${Number(data.compression_ratio).toFixed(2)}x`),
    ];

    if (data.file_type === "text") {
        rows.push(resultMetric("Characters", data.total_chars));
        rows.push(resultMetric("Encoded Bits", data.total_bits));
    }
    if (data.file_type === "pdf") {
        rows.push(resultMetric("Pages", data.pdf_page_count ?? 0));
        rows.push(resultMetric("Images Found", data.pdf_image_count ?? 0));
        rows.push(resultMetric("DPI Used", data.pdf_dpi_used ?? ""));
    }
    if (data.file_type === "docx") {
        rows.push(resultMetric("Paragraphs", data.docx_paragraph_count ?? 0));
        rows.push(resultMetric("Images Compressed", data.docx_image_count ?? 0));
        rows.push(resultMetric("Tables", data.docx_table_count ?? 0));
    }

    const warning = data.warning ? `<p class="result-warning">${escapeHtml(data.warning)}</p>` : "";
    els.resultPanel.innerHTML = `
        ${warning}
        <dl>${rows.join("")}</dl>
        <p><a href="${escapeHtml(data.download_url)}">Download ${escapeHtml(data.compressed_filename)}</a></p>
    `;
    els.resultPanel.hidden = false;
}

function renderDecompressionResult(data) {
    els.decompressResult.innerHTML = `
        <dl>
            ${resultMetric("Compressed", formatBytes(data.compressed_size))}
            ${resultMetric("Decompressed", formatBytes(data.decompressed_size))}
        </dl>
        <p><a href="${escapeHtml(data.download_url)}">Download ${escapeHtml(data.decompressed_filename)}</a></p>
    `;
    els.decompressResult.hidden = false;
}

async function loadStats() {
    const response = await fetch("/api/stats");
    const stats = await response.json();
    document.querySelector("#stat-total").textContent = stats.total_jobs;
    document.querySelector("#stat-text").textContent = stats.text_jobs;
    document.querySelector("#stat-pdf").textContent = stats.pdf_jobs;
    document.querySelector("#stat-docx").textContent = stats.docx_jobs;
    document.querySelector("#stat-ratio").textContent = `${Number(stats.avg_ratio).toFixed(2)}x`;
    document.querySelector("#stat-saved").textContent = formatBytes(stats.total_bytes_saved);
}

async function loadHistory() {
    const query = activeHistoryType ? `?type=${encodeURIComponent(activeHistoryType)}` : "";
    const response = await fetch(`/api/history${query}`);
    const rows = await response.json();

    if (!rows.length) {
        els.historyBody.innerHTML = `<tr><td colspan="11" class="empty-state">No compression jobs yet.</td></tr>`;
        return;
    }

    els.historyBody.innerHTML = rows.map((row, index) => {
        const type = row.file_type || "text";
        const quality = type === "text" ? "" : (row.quality_level || "");
        const viewTitle = type === "text" ? "View Huffman codes" : "View file details";
        return `
            <tr>
                <td>${index + 1}</td>
                <td><span class="badge ${escapeHtml(type)}">${typeLabel(type)}</span></td>
                <td class="filename-cell" title="${escapeHtml(row.original_filename)}">${escapeHtml(row.original_filename)}</td>
                <td>${formatBytes(row.original_size)}</td>
                <td>${formatBytes(row.compressed_size)}</td>
                <td class="${savedClass(row.space_saved_percent)}">${Number(row.space_saved_percent).toFixed(2)}%</td>
                <td>${Number(row.compression_ratio).toFixed(2)}x</td>
                <td>${escapeHtml(quality)}</td>
                <td title="${escapeHtml(row.created_at)}">${relativeTime(row.created_at)}</td>
                <td>
                    <button class="icon-button view-button" type="button" title="${viewTitle}" aria-label="${viewTitle}" data-id="${row.id}" data-type="${escapeHtml(type)}">&#128065;</button>
                </td>
                <td>
                    <button class="icon-button delete-button" type="button" title="Delete job" aria-label="Delete job" data-id="${row.id}">&#128465;</button>
                </td>
            </tr>
        `;
    }).join("");
}

function openModal(title, body) {
    els.modalTitle.textContent = title;
    els.modalBody.innerHTML = body;
    els.modal.showModal();
}

async function showCodes(historyId) {
    const response = await fetch(`/api/codes/${historyId}`);
    const codes = await response.json();
    if (!codes.length) {
        openModal("Huffman Codes", `<p>No Huffman codes are stored for this job.</p>`);
        return;
    }

    const body = `
        <table class="codes-table">
            <thead>
                <tr>
                    <th>Character</th>
                    <th>Frequency</th>
                    <th>Binary Code</th>
                    <th>Length</th>
                </tr>
            </thead>
            <tbody>
                ${codes.map((code) => `
                    <tr>
                        <td>${escapeHtml(code.character)}</td>
                        <td>${escapeHtml(code.frequency)}</td>
                        <td>${escapeHtml(code.binary_code)}</td>
                        <td>${escapeHtml(code.code_length)}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;
    openModal("Huffman Codes", body);
}

function detailItem(label, value) {
    return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "")}</strong></div>`;
}

async function showDetails(historyId) {
    const response = await fetch(`/api/history/${historyId}/detail`);
    const detail = await response.json();
    if (!response.ok) {
        openModal("Details", `<p>${escapeHtml(detail.error || "Could not load details.")}</p>`);
        return;
    }

    const type = detail.file_type;
    const metrics = [
        detailItem("Original Filename", detail.original_filename),
        detailItem("Compressed Filename", detail.compressed_filename),
        detailItem("Original Size", formatBytes(detail.original_size)),
        detailItem("Compressed Size", formatBytes(detail.compressed_size)),
        detailItem("Space Saved", `${Number(detail.space_saved_percent).toFixed(2)}%`),
        detailItem("Ratio", `${Number(detail.compression_ratio).toFixed(2)}x`),
        detailItem("Quality", detail.quality_level || ""),
    ];

    if (type === "pdf") {
        metrics.push(detailItem("Page Count", detail.pdf_page_count ?? 0));
        metrics.push(detailItem("Images Found", detail.pdf_image_count ?? 0));
        metrics.push(detailItem("DPI Used", detail.pdf_dpi_used ?? ""));
    }
    if (type === "docx") {
        metrics.push(detailItem("Paragraphs", detail.docx_paragraph_count ?? 0));
        metrics.push(detailItem("Tables", detail.docx_table_count ?? 0));
        metrics.push(detailItem("Images Compressed", detail.docx_image_count ?? 0));
    }

    openModal(`${typeLabel(type)} Details`, `
        <div class="detail-grid">${metrics.join("")}</div>
        <p><a href="${escapeHtml(detail.download_url)}">Download compressed file</a></p>
    `);
}

async function refreshAll() {
    await Promise.all([loadStats(), loadHistory()]);
}

els.fileInput.addEventListener("change", updateFileHint);

els.compressForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData();
    formData.append("file", els.fileInput.files[0]);
    formData.append("quality", els.qualitySelect.value);

    setStatus(els.compressStatus, "Compressing...");
    els.resultPanel.hidden = true;

    const response = await fetch("/api/compress", {
        method: "POST",
        body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
        setStatus(els.compressStatus, data.error || "Compression failed.", "error");
        return;
    }

    renderCompressionResult(data);
    setStatus(els.compressStatus, "Compression complete.", "success");
    await refreshAll();
});

els.decompressForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.querySelector("#decompress-input");
    const formData = new FormData();
    formData.append("file", input.files[0]);

    setStatus(els.decompressStatus, "Decompressing...");
    els.decompressResult.hidden = true;

    const response = await fetch("/api/decompress", {
        method: "POST",
        body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
        setStatus(els.decompressStatus, data.error || "Decompression failed.", "error");
        return;
    }

    renderDecompressionResult(data);
    setStatus(els.decompressStatus, "Decompression complete.", "success");
});

document.querySelector("#history-body").addEventListener("click", async (event) => {
    const viewButton = event.target.closest(".view-button");
    const deleteButton = event.target.closest(".delete-button");

    if (viewButton) {
        const id = viewButton.dataset.id;
        if (viewButton.dataset.type === "text") {
            await showCodes(id);
        } else {
            await showDetails(id);
        }
    }

    if (deleteButton) {
        await fetch(`/api/history/${deleteButton.dataset.id}`, { method: "DELETE" });
        await refreshAll();
    }
});

document.querySelectorAll(".filter-tab").forEach((button) => {
    button.addEventListener("click", async () => {
        document.querySelectorAll(".filter-tab").forEach((tab) => tab.classList.remove("active"));
        button.classList.add("active");
        activeHistoryType = button.dataset.type;
        await loadHistory();
    });
});

document.querySelector("#clear-history-button").addEventListener("click", async () => {
    await fetch("/api/history", { method: "DELETE" });
    await refreshAll();
});

document.querySelector("#refresh-button").addEventListener("click", refreshAll);
document.querySelector("#modal-close").addEventListener("click", () => els.modal.close());

refreshAll();
