document.addEventListener("DOMContentLoaded", () => {
    // Elementos de Autenticación
    const authOverlay = document.getElementById("auth-overlay");
    const authPasswordInput = document.getElementById("auth-password-input");
    const authSubmitBtn = document.getElementById("auth-submit-btn");
    const authErrorMsg = document.getElementById("auth-error-msg");

    async function checkAuthentication() {
        const savedPassword = localStorage.getItem("access_password") || "";
        try {
            const res = await fetch(`/api/auth-check?password=${encodeURIComponent(savedPassword)}`);
            const data = await res.json();
            
            if (data.status === "disabled" || data.status === "authenticated") {
                authOverlay.classList.add("hidden");
            } else {
                authOverlay.classList.remove("hidden");
            }
        } catch (err) {
            console.error("Error al comprobar la autenticación:", err);
        }
    }

    // Comprobar autenticación en carga de página
    checkAuthentication();

    authSubmitBtn.addEventListener("click", performLogin);
    authPasswordInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") performLogin();
    });

    async function performLogin() {
        const password = authPasswordInput.value;
        authSubmitBtn.disabled = true;
        authErrorMsg.classList.add("hidden");
        
        try {
            const res = await fetch(`/api/auth-check?password=${encodeURIComponent(password)}`);
            const data = await res.json();
            
            if (data.status === "authenticated" || data.status === "disabled") {
                localStorage.setItem("access_password", password);
                authOverlay.classList.add("hidden");
            } else {
                authErrorMsg.classList.remove("hidden");
            }
        } catch (err) {
            console.error("Error al autenticar:", err);
        } finally {
            authSubmitBtn.disabled = false;
        }
    }

    const queryInput = document.getElementById("query-input");
    const startBtn = document.getElementById("start-btn");
    const clearBtn = document.getElementById("clear-console-btn");
    const connectionStatus = document.getElementById("connection-status");
    const consoleStream = document.getElementById("console-stream");
    const placeholderMsg = document.getElementById("console-placeholder-msg");
    const downloadsPanel = document.getElementById("downloads-panel");
    const suggestionTags = document.querySelectorAll(".suggestion-tag");
    
    // Elementos de la ampliación (Selección e Upload)
    const selectionPanel = document.getElementById("selection-panel");
    const papersContainer = document.getElementById("papers-selection-container");
    const uploadDropzone = document.getElementById("upload-dropzone");
    const fileUploader = document.getElementById("file-uploader");
    const uploadedList = document.getElementById("uploaded-files-list");
    const selectAllBtn = document.getElementById("select-all-btn");
    const confirmBtn = document.getElementById("confirm-selection-btn");
    const selectionCounter = document.getElementById("selection-counter");

    // Elementos del selector de formato
    const formatPanel = document.getElementById("format-panel");

    // Mapa: fragmento del nombre del agente SSE → ID del badge de sub-agente
    const AGENT_BADGE_MAP = {
        "TERMINÓLOGO": "sa-terminologo",
        "ESTRATEGA":   "sa-estratega",
        "RERANKER":    "sa-reranker",
        "REVISOR":     "sa-revisor",
        "Extractor Clínico": "sa-extractor",
        "Auditor de Evidencia": "sa-auditor-ev",
        "Curador PICO-S": "sa-curador",
        "Sintetizador": "sa-sintetizador",
        "Bioestadístico": "sa-bioestadistico",
        "Metodólogo": "sa-metodólogo",
        "Redactor Médico": "sa-redactor",
        "Auditor Farmacológico": "sa-auditor-qx",
        "Editor en Jefe": "sa-editor",
        "Diseñador de Diapositivas": "sa-disenador",
        "Auditor Visual": "sa-auditor-vis",
        "Programador PPTX": "sa-programador",
        "Compilación": "sa-compilador",
        "Renderizador": "sa-compilador"
    };

    function markSubAgent(agentName, done = false) {
        for (const [key, badgeId] of Object.entries(AGENT_BADGE_MAP)) {
            if (agentName && agentName.includes(key)) {
                const el = document.getElementById(badgeId);
                if (el) {
                    el.classList.remove("active", "done");
                    el.classList.add(done ? "done" : "active");
                }
                break;
            }
        }
    }
    const confirmFormatBtn = document.getElementById("confirm-format-btn");

    // Botones de Descarga
    const downloadWordBtn = document.getElementById("download-word-btn");
    const downloadPptxBtn = document.getElementById("download-pptx-btn");
    const downloadJsonBtn = document.getElementById("download-json-btn");

    // Elementos del indicador de cuota API
    const quotaCircleFill = document.getElementById("quota-circle-fill");
    const quotaPercentage = document.getElementById("quota-percentage");
    const quotaStatus = document.getElementById("quota-status");

    // --- LÓGICA DE CONFIGURACIÓN DE CLAVES API DE GEMINI ---
    const apiSettingsBtn = document.getElementById("api-settings-btn");
    const apiKeysModal = document.getElementById("api-keys-modal");
    const closeApiModalBtn = document.getElementById("close-api-modal-btn");
    const apiKeysListContainer = document.getElementById("api-keys-list-container");
    const addApiKeyBtn = document.getElementById("add-api-key-btn");
    const saveApiKeysBtn = document.getElementById("save-api-keys-btn");

    function getStoredGeminiKeys() {
        let keys = [];
        try {
            const stored = localStorage.getItem("gemini_api_keys");
            if (stored) {
                const trimmed = stored.trim();
                if (trimmed.startsWith("[")) {
                    keys = JSON.parse(trimmed);
                } else {
                    keys = trimmed.split(",").map(k => k.trim());
                }
            }
        } catch (e) {
            console.error("Error al obtener claves API:", e);
            keys = [];
        }
        if (!Array.isArray(keys)) {
            keys = [];
        }
        return keys.filter(k => k.trim().length > 0).join(",");
    }

    function initApiKeysUI() {
        let savedKeys = [];
        try {
            const stored = localStorage.getItem("gemini_api_keys");
            if (stored) {
                const trimmed = stored.trim();
                if (trimmed.startsWith("[")) {
                    savedKeys = JSON.parse(trimmed);
                } else {
                    savedKeys = trimmed.split(",").map(k => k.trim());
                }
            }
        } catch (e) {
            console.error("Error al inicializar claves API UI:", e);
            savedKeys = [];
        }
        if (!Array.isArray(savedKeys) || savedKeys.length === 0) {
            savedKeys = ["", ""];
        }
        renderApiKeyRows(savedKeys);
    }

    function renderApiKeyRows(keys) {
        apiKeysListContainer.innerHTML = "";
        keys.forEach(key => addApiKeyRow(key));
    }

    function addApiKeyRow(value = "") {
        const row = document.createElement("div");
        row.className = "api-key-row";
        row.style.display = "flex";
        row.style.gap = "8px";
        row.style.alignItems = "center";
        
        const input = document.createElement("input");
        input.type = "password";
        input.className = "api-key-input";
        input.placeholder = "AIzaSy...";
        input.value = value;
        input.style.flex = "1";
        input.style.backgroundColor = "#0b1019";
        input.style.border = "1px solid var(--border-color)";
        input.style.borderRadius = "8px";
        input.style.padding = "10px 14px";
        input.style.color = "var(--text-primary)";
        input.style.fontSize = "13px";
        input.style.fontFamily = "monospace";
        input.style.outline = "none";
        
        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "btn btn-outline btn-xs";
        toggleBtn.style.padding = "10px";
        toggleBtn.style.height = "38px";
        toggleBtn.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
        toggleBtn.onclick = () => {
            if (input.type === "password") {
                input.type = "text";
                toggleBtn.innerHTML = '<i class="fa-solid fa-eye"></i>';
            } else {
                input.type = "password";
                toggleBtn.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
            }
        };

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn btn-outline btn-xs";
        deleteBtn.style.padding = "10px";
        deleteBtn.style.height = "38px";
        deleteBtn.style.color = "var(--error-color)";
        deleteBtn.style.borderColor = "rgba(239, 68, 68, 0.2)";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.onclick = () => {
            row.remove();
        };

        row.appendChild(input);
        row.appendChild(toggleBtn);
        row.appendChild(deleteBtn);
        apiKeysListContainer.appendChild(row);
    }

    apiSettingsBtn.addEventListener("click", () => {
        initApiKeysUI();
        apiKeysModal.classList.remove("hidden");
    });

    closeApiModalBtn.addEventListener("click", () => {
        apiKeysModal.classList.add("hidden");
    });

    addApiKeyBtn.addEventListener("click", () => {
        addApiKeyRow("");
    });

    // ── Model selector ────────────────────────────────────────────────────────
    const geminiModelInput = document.getElementById("gemini-model-input");
    const testApiBtn = document.getElementById("test-api-btn");
    const apiTestResult = document.getElementById("api-test-result");

    function getStoredModel() {
        return localStorage.getItem("gemini_model") || "gemini-2.5-flash";
    }

    if (geminiModelInput) {
        geminiModelInput.value = getStoredModel();
    }

    if (testApiBtn) {
        testApiBtn.addEventListener("click", async () => {
            const model = (geminiModelInput?.value || "").trim() || "gemini-2.5-flash";
            const clientKeys = getStoredGeminiKeys();
            testApiBtn.disabled = true;
            testApiBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Probando...';
            apiTestResult.style.color = "var(--text-secondary)";
            apiTestResult.innerText = "Conectando con la API…";
            try {
                const headers = {
                    "X-Gemini-Model": model,
                    "X-Access-Password": localStorage.getItem("access_password") || ""
                };
                if (clientKeys) headers["X-Gemini-API-Keys"] = clientKeys;
                const resp = await fetch("/api/test-api", { method: "POST", headers });
                const data = await resp.json();
                if (data.status === "ok") {
                    apiTestResult.style.color = "#10b981";
                    apiTestResult.innerText = `✅ OK · ${model} · ${data.latency_ms} ms · respuesta: "${data.response}"`;
                } else {
                    apiTestResult.style.color = "#ef4444";
                    apiTestResult.innerText = `❌ Error · ${data.error || "desconocido"} · ${data.latency_ms} ms`;
                }
            } catch (err) {
                apiTestResult.style.color = "#ef4444";
                apiTestResult.innerText = `❌ Error de red: ${err.message}`;
            } finally {
                testApiBtn.disabled = false;
                testApiBtn.innerHTML = '<i class="fa-solid fa-flask-vial"></i> Probar API';
            }
        });
    }

    saveApiKeysBtn.addEventListener("click", () => {
        const inputs = apiKeysListContainer.querySelectorAll(".api-key-input");
        const keys = Array.from(inputs).map(inp => inp.value.trim()).filter(val => val.length > 0);
        localStorage.setItem("gemini_api_keys", JSON.stringify(keys));

        // Save selected model
        if (geminiModelInput) {
            const model = geminiModelInput.value.trim();
            if (model) localStorage.setItem("gemini_model", model);
        }

        saveApiKeysBtn.innerHTML = '<i class="fa-solid fa-check"></i> ¡Guardado!';
        setTimeout(() => {
            saveApiKeysBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar';
            apiKeysModal.classList.add("hidden");
        }, 800);
    });


    function updateApiQuotaVisual(percentage, statusText, state = "normal") {
        if (!quotaCircleFill || !quotaPercentage || !quotaStatus) return;
        
        quotaCircleFill.style.strokeDasharray = `${percentage}, 100`;
        quotaPercentage.innerText = `${percentage}%`;
        quotaStatus.innerText = statusText;
        
        quotaCircleFill.classList.remove("quota-warning", "quota-danger");
        quotaStatus.classList.remove("quota-text-warning", "quota-text-danger");
        
        if (state === "warning") {
            quotaCircleFill.classList.add("quota-warning");
            quotaStatus.classList.add("quota-text-warning");
        } else if (state === "danger") {
            quotaCircleFill.classList.add("quota-danger");
            quotaStatus.classList.add("quota-text-danger");
        }
    }

    let eventSource = null;
    let currentRunId = null;
    let availablePapers = []; // Lista local de papers mostrados en el selector
    let selectedDois = new Set();

    // --- WORKING TICKER ---
    const stepProgressBar = document.getElementById("step-progress-bar");
    let tickerInterval = null;
    let lastMsgTime = null;
    let currentStepLabel = "";

    const STEP_LABELS = {
        search: "Búsqueda",
        analyze: "PICO-S",
        meta_analyze: "GRADE",
        write: "Redacción",
        present: "Presentación",
        render: "Compilando"
    };

    function startTicker(stepName) {
        lastMsgTime = Date.now();
        currentStepLabel = STEP_LABELS[stepName] || stepName;

        if (tickerInterval) clearInterval(tickerInterval);
        updateTickerEl();
        tickerInterval = setInterval(updateTickerEl, 1000);
    }

    function stopTicker() {
        if (tickerInterval) { clearInterval(tickerInterval); tickerInterval = null; }
        const el = document.getElementById("working-ticker-el");
        if (el) el.remove();
    }

    function updateTickerEl() {
        const secs = Math.floor((Date.now() - lastMsgTime) / 1000);
        let el = document.getElementById("working-ticker-el");
        if (!el) {
            el = document.createElement("div");
            el.id = "working-ticker-el";
            el.className = "working-ticker";
            el.innerHTML = `
                <div class="dots"><span></span><span></span><span></span></div>
                <span class="ticker-step"></span>
                <span class="ticker-time"></span>
            `;
            consoleStream.appendChild(el);
        }
        el.querySelector(".ticker-step").textContent = "Procesando " + currentStepLabel + "...";
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        el.querySelector(".ticker-time").textContent = m > 0
            ? m + "m " + String(s).padStart(2, "0") + "s"
            : secs + "s";
        consoleStream.scrollTop = consoleStream.scrollHeight;
    }

    function updateStepPills(activeStage) {
        const order = ["search", "analyze", "meta_analyze", "write", "present"];
        const activeIdx = order.indexOf(activeStage);
        order.forEach((s, i) => {
            const pill = document.getElementById("spill-" + s);
            if (!pill) return;
            pill.classList.remove("active", "completed", "pending");
            if (i < activeIdx) {
                pill.classList.add("completed");
                pill.querySelector("i").className = "fa-solid fa-check";
            } else if (i === activeIdx) {
                pill.classList.add("active");
            } else {
                pill.classList.add("pending");
            }
        });
    }

    function resetStepPills() {
        const icons = {
            search: "fa-magnifying-glass",
            analyze: "fa-flask",
            meta_analyze: "fa-chart-bar",
            write: "fa-file-word",
            present: "fa-presentation-screen"
        };
        ["search", "analyze", "meta_analyze", "write", "present"].forEach(s => {
            const pill = document.getElementById("spill-" + s);
            if (!pill) return;
            pill.classList.remove("active", "completed");
            pill.classList.add("pending");
            pill.querySelector("i").className = "fa-solid " + icons[s];
        });
        stepProgressBar.classList.remove("visible");
    }

    function completeStepPills() {
        ["search", "analyze", "meta_analyze", "write", "present"].forEach(s => {
            const pill = document.getElementById("spill-" + s);
            if (!pill) return;
            pill.classList.remove("active", "pending");
            pill.classList.add("completed");
            pill.querySelector("i").className = "fa-solid fa-check";
        });
    }

    // --- Sugerencias Rápidas ---
    suggestionTags.forEach(tag => {
        tag.addEventListener("click", () => {
            queryInput.value = tag.getAttribute("data-query");
        });
    });

    // --- Limpiar Consola ---
    clearBtn.addEventListener("click", () => {
        clearConsole();
    });

    function clearConsole() {
        consoleStream.innerHTML = "";
        consoleStream.appendChild(placeholderMsg);
        placeholderMsg.classList.remove("hidden");
    }

    // --- Función para actualizar Nodos del Pipeline ---
    function updatePipelineNodes(activeStage) {
        const stages = ["search", "analyze", "meta_analyze", "write", "present", "render"];
        const currentIndex = stages.indexOf(activeStage);
        
        stages.forEach((stage, idx) => {
            const node = document.getElementById(`node-${stage}`);
            if (!node) return;
            
            node.classList.remove("pending", "active", "completed");
            
            if (idx < currentIndex) {
                node.classList.add("completed");
            } else if (idx === currentIndex) {
                node.classList.add("active");
            } else {
                node.classList.add("pending");
            }
        });
    }

    function resetPipelineNodes() {
        const stages = ["search", "analyze", "meta_analyze", "write", "present", "render"];
        stages.forEach(stage => {
            const node = document.getElementById(`node-${stage}`);
            if (node) {
                node.classList.remove("active", "completed");
                node.classList.add("pending");
            }
        });
        // Reset all sub-agent badges
        document.querySelectorAll(".sub-agent").forEach(el => {
            el.classList.remove("active", "done");
        });
    }

    function completeAllPipelineNodes() {
        const stages = ["search", "analyze", "meta_analyze", "write", "present", "render"];
        stages.forEach(stage => {
            const node = document.getElementById(`node-${stage}`);
            if (node) {
                node.classList.remove("pending", "active");
                node.classList.add("completed");
            }
        });
        // Mark all sub-agent badges as done
        document.querySelectorAll(".sub-agent").forEach(el => {
            el.classList.remove("active");
            el.classList.add("done");
        });
    }

    // --- Agregar Burbuja al Chat ---
    function addChatBubble(data) {
        placeholderMsg.classList.add("hidden");
        
        const bubble = document.createElement("div");
        bubble.classList.add("chat-bubble");
        
        if (data.stage === "render" || data.role === "Procesador") {
            bubble.classList.add("system-message");
        } else if (data.stage === "completed") {
            bubble.classList.add("completed-message");
        } else if (data.stage === "failed") {
            bubble.classList.add("failed-message");
        }
        
        bubble.style.borderLeft = `4px solid ${data.color}`;
        
        const header = document.createElement("div");
        header.classList.add("bubble-header");
        
        const iconBadge = document.createElement("span");
        iconBadge.classList.add("agent-icon-badge");
        iconBadge.style.color = data.color;
        iconBadge.innerHTML = data.icon.startsWith("fa-") ? `<i class="${data.icon}"></i>` : data.icon;
        
        const nameSpan = document.createElement("span");
        nameSpan.classList.add("agent-name");
        nameSpan.style.color = data.color;
        nameSpan.innerText = data.agent;
        
        const roleSpan = document.createElement("span");
        roleSpan.classList.add("agent-role");
        roleSpan.innerText = data.role;
        
        header.appendChild(iconBadge);
        header.appendChild(nameSpan);
        header.appendChild(roleSpan);
        
        const content = document.createElement("div");
        content.classList.add("bubble-content");
        content.innerText = data.content;
        
        bubble.appendChild(header);
        bubble.appendChild(content);
        
        consoleStream.appendChild(bubble);
        consoleStream.scrollTop = consoleStream.scrollHeight;
    }

    // --- RENDERIZAR LISTA DE SELECCIÓN DE PAPERS ---
    function renderPapersList() {
        papersContainer.innerHTML = "";
        
        availablePapers.forEach((paper) => {
            const card = document.createElement("div");
            card.classList.add("paper-selection-card");
            if (selectedDois.has(paper.doi)) {
                card.classList.add("selected");
            }
            
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.classList.add("paper-checkbox");
            checkbox.checked = selectedDois.has(paper.doi);
            checkbox.dataset.doi = paper.doi;
            
            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    selectedDois.add(paper.doi);
                    card.classList.add("selected");
                } else {
                    selectedDois.delete(paper.doi);
                    card.classList.remove("selected");
                }
                updateCounter();
            });

            const details = document.createElement("div");
            details.classList.add("paper-card-details");
            
            const title = document.createElement("h4");
            title.classList.add("paper-card-title");
            title.innerText = paper.title;
            
            const meta = document.createElement("div");
            meta.classList.add("paper-card-meta");
            
            // Badge según procedencia
            const badge = document.createElement("span");
            if (paper.authors && paper.authors.includes("Usuario")) {
                badge.classList.add("badge-upload");
                badge.innerText = "PROPIO";
            } else if (paper.is_guideline) {
                badge.classList.add("badge-guideline");
                badge.innerText = "GUÍA CLÍNICA";
            } else {
                badge.classList.add("badge-pubmed");
                badge.innerText = "PUBMED/DB";
            }

            // Badge OA disponible (verificado antes de la selección)
            const oaBadge = paper.oa_available ? (() => {
                const b = document.createElement("a");
                b.className = "fulltext-badge oa-badge";
                b.href = paper.oa_url || "#";
                b.target = "_blank";
                b.rel = "noopener noreferrer";
                b.innerHTML = `<i class="fa-solid fa-lock-open"></i> Acceso Abierto`;
                b.title = "PDF gratuito disponible (clic para abrir)";
                return b;
            })() : null;
            
            const metaText = document.createTextNode(` | ${paper.authors} (${paper.year}) • ${paper.journal}`);
            meta.appendChild(badge);
            meta.appendChild(metaText);

            // Botón y contenedor para expandir Abstract
            const toggleBtn = document.createElement("button");
            toggleBtn.classList.add("paper-abstract-toggle");
            toggleBtn.innerHTML = `<i class="fa-solid fa-chevron-down"></i> Ver Resumen / Abstract`;
            
            const abstractDiv = document.createElement("div");
            abstractDiv.classList.add("paper-abstract-content", "hidden");
            abstractDiv.innerText = paper.abstract;
            
            toggleBtn.addEventListener("click", () => {
                const isHidden = abstractDiv.classList.toggle("hidden");
                toggleBtn.innerHTML = isHidden 
                    ? `<i class="fa-solid fa-chevron-down"></i> Ver Resumen / Abstract`
                    : `<i class="fa-solid fa-chevron-up"></i> Ocultar Resumen`;
            });

            details.appendChild(title);
            details.appendChild(meta);
            details.appendChild(toggleBtn);
            details.appendChild(abstractDiv);

            // Indicador de texto completo disponible
            if (paper.has_fulltext) {
                const ftBadge = document.createElement("span");
                ftBadge.className = "fulltext-badge";
                ftBadge.innerHTML = `<i class="fa-solid fa-file-lines"></i> Texto completo`;
                details.appendChild(ftBadge);
            } else if (paper.doi && !paper.doi.startsWith("pubmed_") && !paper.doi.startsWith("user_upload_")) {
                // Botón buscar versión libre
                const freeBtn = document.createElement("button");
                freeBtn.className = "btn btn-outline btn-xs free-paper-btn";
                freeBtn.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> Buscar versión libre`;
                freeBtn.dataset.doi = paper.doi;
                freeBtn.dataset.title = paper.title;
                freeBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    freeBtn.disabled = true;
                    freeBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Buscando...`;
                    try {
                        const resp = await fetch(`/api/search-free/${currentRunId}`, {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                                "X-Access-Password": localStorage.getItem("access_password") || ""
                            },
                            body: JSON.stringify({ doi: paper.doi, title: paper.title })
                        });
                        const result = await resp.json();
                        if (result.status === "found") {
                            freeBtn.className = "btn btn-xs fulltext-badge";
                            freeBtn.innerHTML = `<i class="fa-solid fa-check"></i> Texto completo (${Math.round(result.chars/1000)}k chars)`;
                            freeBtn.disabled = true;
                            // Actualizar abstract visible
                            if (result.text_preview) {
                                abstractDiv.innerText = result.text_preview + "...";
                            }
                        } else {
                            freeBtn.innerHTML = `<i class="fa-solid fa-lock"></i> Solo de pago`;
                            freeBtn.disabled = true;
                            freeBtn.style.opacity = "0.5";
                        }
                    } catch {
                        freeBtn.innerHTML = `<i class="fa-solid fa-xmark"></i> Error`;
                        freeBtn.disabled = false;
                    }
                });
                details.appendChild(freeBtn);
            }

            // Badge de acceso abierto verificado (link directo al PDF libre)
            if (oaBadge) {
                details.appendChild(oaBadge);
            }

            // "Subir PDF" button — visible for every paper that doesn't have fulltext yet
            if (!paper.has_fulltext) {
                const uploadPdfBtn = document.createElement("button");
                uploadPdfBtn.className = "btn btn-outline btn-xs upload-pdf-btn";
                uploadPdfBtn.innerHTML = `<i class="fa-solid fa-file-arrow-up"></i> Subir PDF`;
                uploadPdfBtn.title = "Sube el PDF de este paper para que el sistema analice su contenido completo";

                const pdfInput = document.createElement("input");
                pdfInput.type = "file";
                pdfInput.accept = ".pdf";
                pdfInput.style.display = "none";

                uploadPdfBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    pdfInput.click();
                });

                pdfInput.addEventListener("change", async () => {
                    const file = pdfInput.files[0];
                    if (!file) return;
                    uploadPdfBtn.disabled = true;
                    uploadPdfBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Subiendo...`;
                    try {
                        const fd = new FormData();
                        fd.append("doi", paper.doi);
                        fd.append("file", file);
                        const resp = await fetch(`/api/upload-paper-pdf/${currentRunId}`, {
                            method: "POST",
                            headers: { "X-Access-Password": localStorage.getItem("access_password") || "" },
                            body: fd
                        });
                        const result = await resp.json();
                        if (result.status === "ok") {
                            uploadPdfBtn.className = "btn btn-xs fulltext-badge";
                            uploadPdfBtn.innerHTML = `<i class="fa-solid fa-check"></i> PDF cargado (${Math.round(result.chars / 1000)}k chars)`;
                            uploadPdfBtn.disabled = true;
                            paper.has_fulltext = true;
                            if (result.preview) {
                                abstractDiv.innerText = result.preview + "…";
                            }
                        } else {
                            uploadPdfBtn.innerHTML = `<i class="fa-solid fa-xmark"></i> Error al subir`;
                            uploadPdfBtn.disabled = false;
                        }
                    } catch {
                        uploadPdfBtn.innerHTML = `<i class="fa-solid fa-xmark"></i> Error`;
                        uploadPdfBtn.disabled = false;
                    }
                });

                details.appendChild(pdfInput);
                details.appendChild(uploadPdfBtn);
            }

            card.appendChild(checkbox);
            card.appendChild(details);

            papersContainer.appendChild(card);
        });
        
        updateCounter();
    }

    function updateCounter() {
        selectionCounter.innerText = `Artículos seleccionados: ${selectedDois.size}`;
        confirmBtn.disabled = selectedDois.size < 1; // Al menos 1 seleccionado para continuar
    }

    // --- Seleccionar Todos / Ninguno ---
    selectAllBtn.addEventListener("click", () => {
        const allSelected = selectedDois.size === availablePapers.length;
        
        if (allSelected) {
            selectedDois.clear();
        } else {
            availablePapers.forEach(p => selectedDois.add(p.doi));
        }
        
        renderPapersList();
    });

    // --- GESTIÓN DE CARGA DE ARCHIVOS ---
    uploadDropzone.addEventListener("click", () => {
        fileUploader.click();
    });

    // Eventos drag and drop
    ["dragenter", "dragover"].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadDropzone.classList.add("dragover");
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadDropzone.classList.remove("dragover");
        }, false);
    });

    uploadDropzone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    fileUploader.addEventListener("change", () => {
        handleFiles(fileUploader.files);
    });

    function handleFiles(files) {
        if (!currentRunId) {
            alert("Primero debes iniciar el proceso con el botón 'Iniciar Consenso' para poder vincular tus archivos.");
            return;
        }
        Array.from(files).forEach(uploadFile);
    }

    async function uploadFile(file) {
        // Crear elemento visual de carga en la lista
        const fileId = "file-" + Math.random().toString(36).substring(2, 9);
        const item = document.createElement("div");
        item.classList.add("uploaded-file-item");
        item.id = fileId;
        item.innerHTML = `
            <div class="file-info">
                <i class="fa-solid fa-file-medical"></i>
                <span class="file-name" title="${file.name}">${file.name}</span>
            </div>
            <span class="file-status"><i class="fa-solid fa-spinner fa-spin"></i> Procesando...</span>
        `;
        uploadedList.appendChild(item);
        uploadedList.scrollTop = uploadedList.scrollHeight;

        const formData = new FormData();
        formData.append("run_id", currentRunId);
        formData.append("file", file);

        try {
            const headers = { "X-Access-Password": localStorage.getItem("access_password") || "" };
            const clientKeys = getStoredGeminiKeys();
            if (clientKeys) {
                headers["X-Gemini-API-Keys"] = clientKeys;
            }
            const response = await fetch("/api/upload", {
                method: "POST",
                headers: headers,
                body: formData
            });


            if (!response.ok) {
                throw new Error("Error en la subida.");
            }

            const data = await response.json();
            
            // Actualizar estado visual
            const statusEl = item.querySelector(".file-status");
            statusEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> Listo`;
            statusEl.style.color = "var(--success-color)";
            
            // Añadir el paper parseado por la IA al selector
            availablePapers.unshift(data.paper); // Colocar al principio
            selectedDois.add(data.paper.doi); // Seleccionar por defecto
            
            renderPapersList();

        } catch (error) {
            console.error(error);
            const statusEl = item.querySelector(".file-status");
            statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error`;
            statusEl.style.color = "var(--error-color)";
        }
    }

    // --- CONFIRMAR SELECCIÓN (Reanuda el pipeline) ---
    confirmBtn.addEventListener("click", async () => {
        if (!currentRunId) return;

        confirmBtn.disabled = true;
        confirmBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Reanudando...`;
        
        // Bloquear zona de upload
        uploadDropzone.style.pointerEvents = "none";
        uploadDropzone.style.opacity = "0.5";
        
        try {
            const response = await fetch(`/api/confirm/${currentRunId}`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "X-Access-Password": localStorage.getItem("access_password") || ""
                },
                body: JSON.stringify({ selected_dois: Array.from(selectedDois) })
            });

            if (!response.ok) {
                throw new Error("Error al confirmar selección.");
            }

            // Ocultar panel de selección
            selectionPanel.classList.add("hidden");
            
            // Reactivar animación de carga en botón principal
            startBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analizando...`;
            
        } catch (error) {
            console.error(error);
            alert("No se pudo reanudar el análisis. Inténtalo de nuevo.");
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> Confirmar y Continuar Análisis`;
            uploadDropzone.style.pointerEvents = "auto";
            uploadDropzone.style.opacity = "1";
        }
    });

    // --- CONFIRMAR FORMATO DE SALIDA ---
    confirmFormatBtn.addEventListener("click", async () => {
        if (!currentRunId) return;

        const outputFormat = document.querySelector('input[name="output_format"]:checked')?.value || "both";
        const detailLevel = document.querySelector('input[name="detail_level"]:checked')?.value || "long";

        confirmFormatBtn.disabled = true;
        confirmFormatBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Iniciando análisis...`;

        try {
            const response = await fetch(`/api/confirm-format/${currentRunId}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Access-Password": localStorage.getItem("access_password") || ""
                },
                body: JSON.stringify({ output_format: outputFormat, detail_level: detailLevel })
            });

            if (!response.ok) throw new Error("Error al confirmar formato.");

            formatPanel.classList.add("hidden");
            startBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analizando...`;

        } catch (error) {
            console.error(error);
            alert("No se pudo configurar el formato. Inténtalo de nuevo.");
            confirmFormatBtn.disabled = false;
            confirmFormatBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Iniciar Análisis Completo`;
        }
    });

    // --- Iniciar Proceso (Llamada al Backend) ---
    startBtn.addEventListener("click", async () => {
        const query = queryInput.value.trim();
        if (!query) {
            alert("Por favor ingresa un tema de investigación quirúrgica.");
            return;
        }

        // 1. Limpieza de UI
        clearConsole();
        resetPipelineNodes();
        resetStepPills();
        stopTicker();
        downloadsPanel.classList.add("hidden");
        updateApiQuotaVisual(100, "Salud: 100%", "normal");
        selectionPanel.classList.add("hidden");
        formatPanel.classList.add("hidden");
        uploadedList.innerHTML = "";
        availablePapers = [];
        selectedDois.clear();

        // Reactivar dropzone
        uploadDropzone.style.pointerEvents = "auto";
        uploadDropzone.style.opacity = "1";
        confirmBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> Confirmar y Continuar Análisis`;
        confirmFormatBtn.disabled = false;
        confirmFormatBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Iniciar Análisis Completo`;

        startBtn.disabled = true;
        startBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Buscando papers...`;
        
        connectionStatus.className = "status-badge active";
        connectionStatus.querySelector(".status-text").innerText = "Investigando";

        if (eventSource) {
            eventSource.close();
        }

        try {
            const headers = { 
                "Content-Type": "application/json",
                "X-Access-Password": localStorage.getItem("access_password") || ""
            };
            const clientKeys = getStoredGeminiKeys();
            if (clientKeys) {
                headers["X-Gemini-API-Keys"] = clientKeys;
            }
            const selectedModel = getStoredModel();
            if (selectedModel && selectedModel !== "gemini-2.5-flash") {
                headers["X-Gemini-Model"] = selectedModel;
            }
            const pipeline_config = {
                reranking:   document.getElementById("toggle-reranking")?.checked ?? true,
                pmc_download: document.getElementById("toggle-pmc")?.checked ?? true,
                multimodal_pdf: document.getElementById("toggle-multimodal")?.checked ?? true
            };
            const response = await fetch("/api/start", {
                method: "POST",
                headers: headers,
                body: JSON.stringify({ query: query, pipeline_config })
            });


            if (!response.ok) {
                throw new Error("Fallo al iniciar.");
            }

            const data = await response.json();
            currentRunId = data.run_id;
            
            // Conectarse a SSE
            listenToEventStream(currentRunId);

        } catch (error) {
            console.error(error);
            addChatBubble({
                agent: "Sistema",
                role: "Error",
                color: "#ef4444",
                icon: "❌",
                stage: "failed",
                content: `Error al iniciar: No se pudo conectar con el servidor.`
            });
            resetControls();
        }
    });

    // --- Escuchar EventStream SSE ---
    function listenToEventStream(runId) {
        const savedPassword = localStorage.getItem("access_password") || "";
        eventSource = new EventSource(`/api/stream/${runId}?password=${encodeURIComponent(savedPassword)}`);

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Agregar burbuja de chat
                addChatBubble(data);

                // Resetear el ticker con cada mensaje nuevo
                if (data.stage && !["completed", "failed", "selection_required", "output_format_required"].includes(data.stage)) {
                    lastMsgTime = Date.now();
                }

                // Actualizar badge de sub-agente en tiempo real
                if (data.agent) markSubAgent(data.agent, false);

                // Actualizar pipeline de nodos
                if (data.stage && !["completed", "failed", "selection_required", "output_format_required"].includes(data.stage)) {
                    updatePipelineNodes(data.stage);
                    // Mostrar barra de progreso y arrancar ticker
                    stepProgressBar.classList.add("visible");
                    updateStepPills(data.stage);
                    startTicker(data.stage);
                    
                    // Actualizar círculo de cuota API
                    if (data.stage === "search") {
                        updateApiQuotaVisual(95, "Salud: 95%", "normal");
                    } else if (data.stage === "analyze") {
                        updateApiQuotaVisual(70, "Salud: 70%", "normal");
                    } else if (data.stage === "meta_analyze") {
                        updateApiQuotaVisual(60, "Salud: 60%", "normal");
                    } else if (data.stage === "write") {
                        updateApiQuotaVisual(30, "Límite: 30%", "warning");
                    } else if (data.stage === "present") {
                        updateApiQuotaVisual(15, "Límite: 15%", "warning");
                    } else if (data.stage === "render") {
                        updateApiQuotaVisual(10, "Límite: 10%", "warning");
                    }
                }
                
                // CASO ESPECIAL: Se requiere interactividad del usuario
                if (data.stage === "selection_required") {
                    updatePipelineNodes("search");

                    // Modificar estado de botón principal
                    startBtn.innerHTML = `<i class="fa-solid fa-hourglass-half"></i> Esperando Selección...`;

                    // Cargar los papers candidatos devueltos
                    availablePapers = data.papers || [];

                    // Seleccionar todos por defecto inicialmente
                    selectedDois.clear();
                    availablePapers.forEach(p => selectedDois.add(p.doi));

                    renderPapersList();

                    // Mostrar panel de selección y hacer scroll suave hacia él
                    selectionPanel.classList.remove("hidden");
                    selectionPanel.scrollIntoView({ behavior: "smooth" });
                }

                // CASO ESPECIAL: Selector de formato de salida
                if (data.stage === "output_format_required") {
                    startBtn.innerHTML = `<i class="fa-solid fa-hourglass-half"></i> Configurando salida...`;
                    formatPanel.classList.remove("hidden");
                    formatPanel.scrollIntoView({ behavior: "smooth" });
                }

                // Si completó con éxito
                if (data.stage === "completed") {
                    eventSource.close();
                    stopTicker();
                    completeStepPills();
                    completeAllPipelineNodes();
                    
                    connectionStatus.className = "status-badge completed";
                    connectionStatus.querySelector(".status-text").innerText = "Finalizado";
                    
                    setupDownloadLinks(runId);
                    
                    // Renderizar la biblioteca de evidencia utilizada
                    renderEvidenceLibrary(data.selected_papers);
                    
                    downloadsPanel.classList.remove("hidden");
                    downloadsPanel.scrollIntoView({ behavior: "smooth" });
                    resetControls();
                }
                
                // Si falló
                if (data.stage === "failed") {
                    eventSource.close();
                    stopTicker();
                    connectionStatus.className = "status-badge idle";
                    connectionStatus.querySelector(".status-text").innerText = "Fallo";
                    
                    // Verificar si fue por límite de cuota
                    const contentLower = (data.content || "").toLowerCase();
                    if (contentLower.includes("quota") || contentLower.includes("429") || contentLower.includes("exhausted") || contentLower.includes("cuota")) {
                        updateApiQuotaVisual(0, "Agotado (429)", "danger");
                    } else {
                        updateApiQuotaVisual(100, "Salud: 100%", "normal");
                    }
                    
                    resetControls();
                }

            } catch (err) {
                console.error("Error parseando evento SSE:", err);
            }
        };

        eventSource.onerror = (err) => {
            console.error("Error de EventSource SSE:", err);
            eventSource.close();
            stopTicker();
            resetControls();
        };
    }

    // --- Configurar Enlaces de Descarga ---
    function setupDownloadLinks(runId) {
        const outputFormat = document.querySelector('input[name="output_format"]:checked')?.value || "both";

        if (downloadWordBtn) {
            if (outputFormat === "pptx") {
                downloadWordBtn.disabled = true;
                downloadWordBtn.title = "No solicitado en esta ejecución";
            } else {
                downloadWordBtn.disabled = false;
                downloadWordBtn.onclick = () => { window.location.href = `/api/downloads/${runId}/word`; };
            }
        }
        if (downloadPptxBtn) {
            if (outputFormat === "word") {
                downloadPptxBtn.disabled = true;
                downloadPptxBtn.title = "No solicitado en esta ejecución";
            } else {
                downloadPptxBtn.disabled = false;
                downloadPptxBtn.onclick = () => { window.location.href = `/api/downloads/${runId}/powerpoint`; };
            }
        }
        if (downloadJsonBtn) {
            downloadJsonBtn.onclick = () => { window.location.href = `/api/downloads/${runId}/json`; };
        }
    }

    // --- Renderizar Biblioteca de Evidencia ---
    function renderEvidenceLibrary(papers) {
        const container = document.getElementById("evidence-library-list");
        if (!container) return;
        
        container.innerHTML = "";
        
        if (!papers || papers.length === 0) {
            container.innerHTML = `<p class="empty-library">No se registraron artículos en esta ejecución.</p>`;
            return;
        }
        
        papers.forEach(paper => {
            const item = document.createElement("div");
            item.classList.add("library-item");
            
            const fileIcon = document.createElement("i");
            if (paper.url.includes("/uploads/")) {
                fileIcon.className = "fa-solid fa-file-pdf library-icon-pdf";
            } else {
                fileIcon.className = "fa-solid fa-file-lines library-icon-web";
            }
            
            const details = document.createElement("div");
            details.classList.add("library-details");
            
            const titleLink = document.createElement("a");
            titleLink.href = paper.url;
            titleLink.target = "_blank";
            titleLink.innerText = paper.title;
            titleLink.classList.add("library-title-link");
            
            const meta = document.createElement("span");
            meta.classList.add("library-meta");
            
            const badge = document.createElement("span");
            if (paper.url.includes("/uploads/")) {
                badge.className = "badge-upload";
                badge.innerText = "PDF SUBIDO";
            } else {
                badge.className = "badge-pubmed";
                badge.innerText = "LITERATURA";
            }
            
            const metaText = document.createTextNode(` | ${paper.authors} (${paper.year}) • ${paper.journal}`);
            meta.appendChild(badge);
            meta.appendChild(metaText);
            
            details.appendChild(titleLink);
            details.appendChild(meta);
            
            item.appendChild(fileIcon);
            item.appendChild(details);
            
            // Botón de descarga/acción
            const actionBtn = document.createElement("a");
            actionBtn.href = paper.url;
            actionBtn.target = "_blank";
            actionBtn.classList.add("btn", "btn-outline", "btn-xs", "library-action-btn");
            if (paper.url.includes("/uploads/")) {
                actionBtn.innerHTML = `<i class="fa-solid fa-download"></i> Descargar`;
            } else {
                actionBtn.innerHTML = `<i class="fa-solid fa-external-link"></i> Abrir`;
            }
            item.appendChild(actionBtn);
            
            container.appendChild(item);
        });
    }

    // --- Resetear Controles ---
    function resetControls() {
        startBtn.disabled = false;
        startBtn.innerHTML = `<i class="fa-solid fa-play"></i> Iniciar Consenso`;
        stopTicker();
    }
});
