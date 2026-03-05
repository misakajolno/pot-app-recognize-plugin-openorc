const DEFAULT_TIMEOUT_MS = 180000;
const DEFAULT_TASK = "ocr";
const DEFAULT_MODE = "mobile";
const DEFAULT_BACKEND = "onnx";
const DEFAULT_MERGE_LINES = true;
const DEFAULT_PYTHON_CMD = "python";

function normalizePath(value) {
    return String(value ?? "").trim().replaceAll("\\", "/").replace(/\/+$/, "");
}

function toBoolean(value, fallback) {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
        const lowered = value.trim().toLowerCase();
        if (["true", "1", "yes", "on"].includes(lowered)) return true;
        if (["false", "0", "no", "off"].includes(lowered)) return false;
    }
    return fallback;
}

function toPositiveInteger(value, fallback) {
    const number = Number(value);
    if (Number.isFinite(number) && number > 0) {
        return Math.floor(number);
    }
    return fallback;
}

function summarizeOutput(output, maxLength = 280) {
    const text = String(output ?? "").replace(/\s+/g, " ").trim();
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength)}...`;
}

function resolveRuntimeConfig(config = {}, pluginDir = "") {
    const pluginBase = normalizePath(pluginDir);
    const pythonCmd = String(config.python_cmd || DEFAULT_PYTHON_CMD).trim();
    const bridgeScriptPath = normalizePath(config.bridge_script_path);

    return {
        pluginBase,
        pythonCmd,
        bridgeScriptPath,
        task: String(config.task || DEFAULT_TASK).trim().toLowerCase(),
        mode: String(config.mode || DEFAULT_MODE).trim().toLowerCase(),
        backend: normalizeBackend(config.backend || DEFAULT_BACKEND),
        mergeLines: toBoolean(config.merge_lines, DEFAULT_MERGE_LINES),
        timeoutMs: toPositiveInteger(config.timeout_ms, DEFAULT_TIMEOUT_MS),
    };
}

function extractResultJson(stdout) {
    const raw = String(stdout ?? "").trim();
    if (!raw) {
        throw Error("OpenOCR bridge output is empty.");
    }

    const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).reverse();
    for (const line of lines) {
        if (line.startsWith("{") && line.endsWith("}")) {
            try {
                return JSON.parse(line);
            } catch (_) {
                // Keep scanning the rest of the lines.
            }
        }
    }

    const tailObjectMatch = raw.match(/\{[\s\S]*\}\s*$/);
    if (tailObjectMatch) {
        try {
            return JSON.parse(tailObjectMatch[0]);
        } catch (_) {
            // Fallthrough to parse failure below.
        }
    }

    throw Error(`Failed to parse OpenOCR bridge JSON output: ${summarizeOutput(raw)}`);
}

function withTimeout(promise, timeoutMs) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            reject(new Error(`OpenOCR process timed out after ${timeoutMs}ms.`));
        }, timeoutMs);

        Promise.resolve(promise).then(
            (value) => {
                clearTimeout(timer);
                resolve(value);
            },
            (error) => {
                clearTimeout(timer);
                reject(error);
            }
        );
    });
}

function buildArgs(runtime, imagePath, lang) {
    return [
        normalizePath(runtime.bridgeScriptPath),
        "--image",
        normalizePath(imagePath),
        "--lang",
        String(lang || "auto"),
        "--task",
        runtime.task || DEFAULT_TASK,
        "--mode",
        runtime.mode || DEFAULT_MODE,
        "--backend",
        runtime.backend || DEFAULT_BACKEND,
        "--merge-lines",
        runtime.mergeLines ? "1" : "0",
    ];
}

function normalizeBackend(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "onnxruntime") return "onnx";
    if (normalized === "onnx") return "onnx";
    if (normalized === "torch") return "torch";
    return DEFAULT_BACKEND;
}

function pushUnique(arr, value) {
    const normalized = normalizePath(value);
    if (!normalized) return;
    if (!arr.includes(normalized)) {
        arr.push(normalized);
    }
}

function getBridgeScriptCandidates(runtime) {
    const candidates = [];
    pushUnique(candidates, runtime.bridgeScriptPath);
    pushUnique(candidates, `${runtime.pluginBase}/scripts/openorc_bridge.py`);
    pushUnique(candidates, `${runtime.pluginBase}/openorc_bridge.py`);
    return candidates;
}

function isBridgeScriptMissing(result) {
    const stderr = String(result?.stderr ?? "").toLowerCase();
    const stdout = String(result?.stdout ?? "").toLowerCase();
    return (
        (stderr.includes("can't open file") || stdout.includes("can't open file")) &&
        (stderr.includes("openorc_bridge.py") || stdout.includes("openorc_bridge.py"))
    );
}

async function recognize(_base64, lang, options = {}) {
    const { utils = {}, config = {} } = options;
    const { run, cacheDir, pluginDir } = utils;

    if (typeof run !== "function") {
        throw Error("Pot runtime error: utils.run is unavailable.");
    }
    if (!cacheDir) {
        throw Error("Pot runtime error: cacheDir is unavailable.");
    }

    const runtime = resolveRuntimeConfig(config, pluginDir);
    if (!runtime.pythonCmd) {
        throw Error("Plugin config error: python_cmd is required.");
    }
    const imagePath = `${normalizePath(cacheDir)}/pot_screenshot_cut.png`;
    const scriptCandidates = getBridgeScriptCandidates(runtime);
    if (scriptCandidates.length === 0) {
        throw Error("Plugin config error: no available bridge script path.");
    }

    try {
        let lastError = null;
        for (const scriptPath of scriptCandidates) {
            const runTimeWithScript = { ...runtime, bridgeScriptPath: scriptPath };
            const args = buildArgs(runTimeWithScript, imagePath, lang);
            const result = await withTimeout(run(runtime.pythonCmd, args), runtime.timeoutMs);
            if (!result || typeof result.status !== "number") {
                lastError = new Error("Invalid process result from OpenOCR bridge.");
                continue;
            }

            if (result.status !== 0) {
                if (isBridgeScriptMissing(result)) {
                    lastError = new Error(
                        `Bridge script missing at ${scriptPath}. Trying next candidate...`
                    );
                    continue;
                }
                const stderr = summarizeOutput(result.stderr);
                const stdout = summarizeOutput(result.stdout);
                throw Error(
                    `OpenOCR bridge failed (status ${result.status}). ` +
                    `stderr: ${stderr || "[empty]"}; stdout: ${stdout || "[empty]"}`
                );
            }

            const payload = extractResultJson(result.stdout);
            if (payload && payload.error) {
                throw Error(String(payload.error));
            }

            const text = String(payload?.text || "").trim();
            if (!text) {
                throw Error("OpenOCR returned empty text.");
            }
            return text;
        }

        const candidatesText = scriptCandidates.join(" | ");
        throw Error(
            `OpenOCR bridge script not found. Tried: ${candidatesText}. ` +
            `Last error: ${lastError?.message || "unknown"}`
        );
    } catch (error) {
        throw Error(`OpenOCR launch failed: ${error?.message || String(error)}`);
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        recognize,
        resolveRuntimeConfig,
        extractResultJson,
        withTimeout,
        buildArgs,
        normalizePath,
    };
}
