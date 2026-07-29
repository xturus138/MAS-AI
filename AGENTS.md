# AGENTS.md — Project MAS AI (kode implementasi skripsi)

File ini dimuat otomatis oleh Hermes ketika working directory = folder project ini.
Jangan simpan progress sesi harian di sini — status sesi tidak lagi dilacak lewat file
terpisah di repo ini; gunakan `git log` untuk riwayat commit dan auto-memory (`Dokumen
Kepake/memory/MEMORY.md`) untuk konteks riset jangka panjang.

**Hubungan folder:** ini adalah **repo kode** implementasi. Dokumen skripsi/bimbingan/paper ada di folder terpisah `Dokumen Kepake` (bukan di sini).

## 1. Identitas project

- **Nama repo:** MAS AI — Multi-Agent Android Testing Framework
- **Peran:** implementasi sistem agentic multi-agent untuk otomasi pengujian fungsional GUI Android (skripsi Raditya Aryabudhi Ramadhan / 10122032)
- **Stack inti:** Python 3.10+, LangGraph, LangChain, ADB / uiautomator2, Figma API, Gemini vision grounding (default widget detection) + EasyOCR/OpenCV (fallback), MIRIX memory (SQLite+JSON), PyQt5 monitor
- **Dua mode workflow** (`WORKFLOW_STRATEGY` di `.env`):
  - `predefined` — langkah dari skenario Excel; pipeline linear
  - `autonomous` — goal-driven; orchestrator hub-and-spoke via `Command(goto=...)`
- **Target eksekusi:** device Android fisik/emulator lewat ADB (`TARGET_DEVICE`)
- **Peran agent di folder ini:** coding, debugging, refactor, run diagnostics, analisis output run — **bukan** menulis bab skripsi (itu di `Dokumen Kepake`)

## 2. Peta folder

```
MAS AI/
├── AGENTS.md              ← aturan + konteks stabil (file ini)
├── CLAUDE.md              ← arsitektur & convention detail (Claude Code / coding agent)
├── README.md              ← overview manusia + quick start
├── PROVIDER_SWITCH.md     ← cheat sheet ganti provider LLM keempat agent
├── main.py                ← entry point
├── requirements.txt
├── .env / .env.example    ← config runtime (JANGAN commit secret; jangan dump .env ke chat)
├── agents/                ← observer, decider, executor, reflector, recorder
├── core/
│   ├── models/            ← AgentState (TypedDict)
│   ├── ports/             ← ILLMClient, IDeviceClient
│   ├── workflow/          ← graph predefined + autonomous + orchestrator
│   └── utils/             ← logger, output_manager, pricing, dll.
├── memory/                ← MIRIX (meta_manager, schemas, stores, retrieval)
├── adapters/              ← device (ADB), llm (LangChain), figma
├── tools/                 ← executor_tools, observer_tools
├── shared/                ← config.py + prompts/ per agent
├── visual/                ← PyQt5 overlay monitor
├── analysis/              ← compare_runs
├── scripts/               ← cleanup_outputs, dll.
├── tests/                 ← script integrasi standalone (bukan suite pytest)
├── scenarios/             ← aset skenario (chitchat, notes, …)
├── docs/                  ← prompting plan, pricing, analisis codebase
├── outputs/               ← artefak run (bisa besar; jangan commit bulk)
└── vaultkey/              ← key material lokal (sensitif)
```

### Peran file penting

| File / folder | Kapan dipakai |
|---------------|----------------|
| `CLAUDE.md` | Detail arsitektur, loop agent, MIRIX, convention coding |
| `README.md` | Overview + setup + research framing |
| `PROVIDER_SWITCH.md` | Ganti provider/model 4 agent (copy-paste ke `.env`) |
| `.env.example` | Template config; jangan mengarang env key di luar ini tanpa cek `shared/config.py` |
| `main.py` | Entry run framework |
| `agents/` + `core/workflow/` | Logika agent & graph |
| `memory/` | Persistensi di luar LangGraph state |
| `shared/prompts/` | Prompt engineering per agent |
| `outputs/` | Hasil run, log, metrics, screenshot per skenario |
| `tests/check_*.py` | Diagnostik koneksi Figma / model / Vertex |

## 3. Aturan kerja agent

1. **Session start:** ikuti file ini; untuk status kerja terbaru cek `git log --oneline -10`; untuk detail arsitektur baca `CLAUDE.md` (jangan salin ulang isinya ke sini).
2. **Sumber kebenaran kode:** file `.py` di repo + `shared/config.py` + `.env.example`. README/CLAUDE bisa telat — verifikasi di kode jika ragu.
3. **Secret:** jangan print/commit/isi chat dengan isi `.env`, API key, token Figma, atau isi `vaultkey/`.
4. **Edit aman:** prefer patch kecil; jangan rewrite massal agent/prompt tanpa permintaan eksplisit.
5. **Dependency:** jangan tambah package baru jika stdlib / dep di `requirements.txt` sudah cukup (lazy senior rule).
6. **Run:** default `python main.py` (mode dari `.env`). Diagnostik: `tests/check_figma_connection.py`, `tests/check_models.py`. Cleanup output: dry-run dulu (`scripts/cleanup_outputs.py --dry-run`).
7. **Tests folder:** script standalone, **bukan** pytest suite — jangan asumsikan `pytest` jalan out-of-the-box.
8. **Progress berubah:** rely pada commit message yang jelas. Jangan rewrite `AGENTS.md` untuk status harian.
9. **Scope memory:** konteks project lewat `AGENTS.md` di folder ini (+ baca `CLAUDE.md` saat coding). Jangan cache body file ke fact_store global.
10. **Skripsi dokumen:** draft/bimbingan/paper → folder `Dokumen Kepake`, bukan repo ini. Cross-link saja jika user minta sinkron konsep.

## 4. Prioritas baca per jenis tugas

| Tugas | Baca dulu |
|-------|-----------|
| Pahami arsitektur / loop agent | `CLAUDE.md` → `core/models/state.py` → `core/workflow/` |
| Ubah 1 agent | `agents/<agent>_agent.py` + `shared/prompts/<agent>_prompts.py` |
| Ubah memory MIRIX | `memory/meta_manager.py` + `memory/schemas.py` + `memory/retrieval/` |
| Provider / model LLM | `PROVIDER_SWITCH.md` + `.env.example` + `shared/config.py` + `adapters/llm/` |
| Device / ADB / aksi UI | `adapters/device/` + `tools/executor_tools.py` |
| Observer vision/XML | `agents/observer_agent.py` + `tools/observer_tools.py` |
| Analisis hasil run | `outputs/` (run terbaru) + `analysis/compare_runs.py` |
| Setup / onboarding | `README.md` + `.env.example` + `requirements.txt` |
| Dokumen skripsi / metode / paper | **bukan di sini** → `Dokumen Kepake/AGENTS.md` |

## 5. Domain ringkas (stabil)

- **Loop bersama:** `ORCHESTRATOR → OBSERVER → DECIDER → EXECUTOR → REFLECTOR → (kembali)`
- **AgentState** = working memory langkah berjalan (~field terbatas). Persistensi jangka panjang = **MIRIX** via `memory.retrieve` / `memory.update` saja (jangan bypass store).
- **Enam store MIRIX:** Core, Episodic, Semantic, Procedural, Resource, Knowledge Vault.
- **Ports:** `ILLMClient`, `IDeviceClient` — implementasi di `adapters/`.
- **Observer:** screenshot → deteksi widget via `OBSERVER_DETECTION_METHOD` (default `llm` = zero-shot VLM grounding satu-panggilan; fallback `cv_ocr` = Canny+OCR klasik saat API gagal atau dikonfigurasi manual) → uiautomator XML + IoU matching widget; mode `OBSERVER_MODE` (`xml_first` / `pure_vision`).
- **Reflector final step:** verifikasi 3 arah (screenshot vs expected text vs Figma gold standard) bila Figma tersedia.
- **Output run:** di bawah `outputs/runs/{predefined|autonomous}/YYYY-MM-DD/{tcs_id}__{timestamp}/` (process.log, metrics, steps, memory snapshot, reports).
- **Riset framing:** bandingkan strategi predefined vs autonomous dengan kemampuan persepsi yang sama (bukan bandingkan “bisa lihat vs tidak”).

## 6. Yang tidak boleh dimasukkan ke AGENTS.md

- Status bug hari ini / blocker run terakhir → commit message / auto-memory
- Isi penuh prompt, dump log, atau seluruh tree `outputs/`
- API key, device ID pribadi, token Figma
- Salinan panjang `CLAUDE.md` / README (cukup rujuk path)
- Preferensi global Hermes di luar project ini
- Isi bab skripsi atau keputusan metodologi penelitian (itu milik `Dokumen Kepake`)
