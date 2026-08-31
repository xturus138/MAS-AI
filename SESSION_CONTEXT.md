# SESSION CONTEXT — Branch: `optimize/efficiency-cost-reduction`

> Last updated: 2026-08-31  
> Branch: `optimize/efficiency-cost-reduction`  
> Base: `main` (commit `3f2bca1`)  
> Remote: `https://github.com/xturus138/MAS-AI.git`

---

## Ringkasan Sesi Ini

Sesi ini mencakup **audit arsitektur, pemahaman mendalam multi-agent team, review referensi paper, dan implementasi 5 optimasi produksi** pada framework MAS AI (skripsi S1 Raditya — pengujian GUI Android otomatis berbasis multi-agent AI).

---

## 1. Pemahaman Arsitektur yang Sudah Dikonfirmasi

### Multi-Agent Loop
```
Orchestrator → Observer → Decider → Executor → Reflector → (kembali ke Orchestrator)
```

### Peran Tiap Agent
| Agent | LLM? | Tugas |
|---|---|---|
| **Observer** | Hybrid (OmniParser lokal + opsional VLM) | Deteksi elemen UI dari screenshot — murni perseptual |
| **Decider** | YA | Pilih aksi atomik berdasarkan instruksi & widget list |
| **Executor** | TIDAK | Eksekusi ADB fisik (tap/input/swipe) |
| **Reflector** | YA | Validasi apakah aksi berhasil (3 aspek: loading, UI change, validity) |
| **Orchestrator (Predefined)** | Kondisional | State machine linear + Bridge recovery |
| **Orchestrator (Autonomous)** | YA | Dynamic routing via LangGraph Command(goto=...) |
| **Recorder** | TIDAK | Finalisasi laporan Excel & JSON (1x di akhir run) |

### Memori MIRIX
6 store terisolasi: `Core`, `Episodic` (SQLite FTS5), `Semantic` (SQLite FTS5), `Procedural`, `Resource`, `Knowledge Vault`. Operasi paralel: `retrieve()` + `update()`. **Benar sesuai paper MIRIX (Wang & Chen, 2024)**.

---

## 2. Paper Referensi Baru yang Telah Didownload ke Folder Referensi Jurnal

Lokasi: `D:\Kuliah\SKRIPSI\RESEARCH TEMA PROKSI\AUTOMATED TESTING ANDROID\Dokumen Kepake\Referensi Jurnal Proksi\`

| File | Paper | Tahun | Konteks ke MAS AI |
|---|---|---|---|
| `SafeGround - Know When to Trust GUI Grounding Models via Uncertainty Calibration (2026).pdf` | Wang et al., ICML 2026 | 2026 | Dasar threshold $\tau$ untuk DSE Safety Gate |
| `RecAgent - Uncertainty-Aware GUI Agent through Adaptive Perception (2025).pdf` | Hao et al., PolyU/Peking 2025 | 2025 | Dasar Target-Only DSE & perceptual uncertainty |
| `EpiDroid - Dependency-Guided Recomposition for Deep State Discovery in Mobile GUI Testing (2026).pdf` | Song et al., ZJU 2026 | 2026 | Dasar Decoupled Trace Integrity di Bridge/Recovery |
| `ScenGen - Scenario-Guided LLM-based Mobile App GUI Testing (2025).pdf` | Yu & Ling, Nanjing 2025 | 2025 | Dasar Precondition State Verification |
| `Swift-Hand - Guided GUI Testing of Android Apps with Minimal Restart (2013).pdf` | Choi et al., UC Berkeley 2013 | 2013 | Dasar Event-Based Recovery, tolak hard restart |
| `TimeMachine - Time-Travel Testing of Android Apps (2020).pdf` | Dong et al., NUS/ICSE 2020 | 2020 | Dasar state-level feedback & state corpus |

---

## 3. Optimasi yang Sudah Diimplementasikan (Branch ini)

### Poin 1: Reflector Single-Pass Verification
- **File**: `agents/reflector_agent.py`
- **Sebelum**: 3 VLM call per step (Loading → UI Change → Validity)
- **Sesudah**: 1 unified VLM call via `SinglePassVerdict` schema + OpenCV pixel diff lokal ($0 token)
- **Referensi**: *Polo et al. (2024) — Efficient multi-prompt evaluation of LLMs* & *Kolthoff (2024) — GUISpector*
- **Hemat**: ~66% token Reflector per step

### Poin 2: Decider Fast-Path Action Pruning
- **File**: `agents/decider_agent.py`
- **Sebelum**: 100% instruksi selalu memanggil LLM Decider
- **Sesudah**: `_try_deterministic_fast_path()` mencocokkan instruksi atomik langsung ke widget label OmniParser tanpa LLM
- **Referensi**: *AutoDroid (Wen et al., 2023) §4.2 Memory-guided action pruning*
- **Hemat**: ~50–70% panggilan LLM Decider

### Poin 3: MIRIX Bounded Context Truncation
- **File**: `memory/retrieval/active_retrieval.py`
- **Sebelum**: Detail episodic log 300 char/entri, ada kode retrieval duplikat
- **Sesudah**: Truncation 120 char/entri, hapus blok retrieval duplikat, filter tag kosong
- **Referensi**: *MIRIX §3.2 (Wang & Chen, 2024)* & *CoALA (Sumers et al., 2024)*
- **Hemat**: ~40% input prompt tokens

### Poin 4: Target-Only DSE & Threshold Gate
- **Files**: `agents/observer_agent.py`, `core/uncertainty/config.py`, `core/uncertainty/service.py`, `shared/config.py`
- **Sebelum**: DSE mengukur semua 30–50 widget di layar (lambat, boros)
- **Sesudah**: DSE hanya mengukur 1 widget target yang dipilih Decider + dukungan threshold $\tau$ dari env
- **Config Baru di `.env`**:
  - `OBSERVER_UNCERTAINTY_ENABLED=false` — nonaktif untuk baseline run
  - `OBSERVER_UNCERTAINTY_TARGET_ONLY=true` — hanya ukur target widget
  - `OBSERVER_UNCERTAINTY_THRESHOLD=` — threshold tau (dikosongkan sampai kalibrasi selesai)
- **Referensi**: *SafeGround (Wang et al., 2026)* & *RecAgent (Hao et al., 2025)*

### Poin 5: Bridge/Recovery Phase — Zero Overhead
- **Files**: `core/workflow/predefined/orchestrator.py`, `agents/observer_agent.py`
- **Diterapkan**:
  1. **Fast-path rule heuristics** di `plan_recovery_transition()`: Jika keyboard/dialog terbuka → `press back`; jika di sub-editor/detail → `click Back button` (0 LLM call)
  2. **DSE & uncertainty 100% dinonaktifkan** selama bridge/recovery (`current_step < 0` atau `"recovery"` di path step_dir)
- **Referensi**: *Swift-Hand (Choi et al., 2013)* & *EpiDroid (Song et al., 2026)*

---

## 4. Tool Test yang Disimpan (Berguna)

- `scripts/test_observer_single_image.py`: Runner mandiri uji OmniParser pada 1 gambar screenshot nyata. Menghasilkan folder `outputs/test_observer_inspection/` berisi:
  - `raw_image.png` — gambar asli
  - `annotated_bounding_boxes.png` — visualisasi bounding box berwarna dengan ID
  - `detected_widgets.json` — data terstruktur semua elemen
  - Cara jalankan: `& ".\venv\Scripts\python.exe" scripts/test_observer_single_image.py`

---

## 5. Status Test Suite
```
tests/test_reflector_agent.py         → 6 passed (diupdate ke SinglePassVerdict)
tests/test_predefined_runner_*.py     → 74+ passed
tests/test_predefined_recovery.py     → passed
tests/test_predefined_batch.py        → passed
tests/test_observer_agent.py          → passed
tests/test_uncertainty_service.py     → 29 passed
tests/test_dse_math.py                → passed
```

---

## 6. Hal yang BELUM Dikerjakan / Lanjutan

- [ ] Kalibrasi threshold $\tau$ DSE — butuh hasil run 69 test case Firebase Chat dulu untuk menentukan nilai tau aktual
- [ ] Poin 4 (Tiered LLM / Heterogeneous Model Routing) — `X-MAS (Ye et al., 2024)` — sengaja ditunda
- [ ] Verifikasi end-to-end bridge recovery dengan device Android nyata (HP fisik)
- [ ] PR dari branch `optimize/efficiency-cost-reduction` ke `main` — tunggu konfirmasi Anda

---

## 7. Perintah Berguna

```powershell
# Jalankan test suite utama
& ".\venv\Scripts\python.exe" -m pytest tests/test_reflector_agent.py tests/test_predefined_runner_integration.py tests/test_predefined_recovery.py -q

# Test observer single image (OmniParser)
& ".\venv\Scripts\python.exe" scripts/test_observer_single_image.py

# Cek branch aktif
git log --oneline -5

# Push ke remote
git push MAS-AI optimize/efficiency-cost-reduction
```

---

## 8. Konteks untuk Agent Sesi Baru

> **Kamu berada di branch `optimize/efficiency-cost-reduction`** dari repo MAS AI.
> Semua optimasi (Poin 1–5 di atas) sudah diimplementasikan dan di-push ke remote.
> Referensi paper baru (SafeGround, RecAgent, EpiDroid, ScenGen, Swift-Hand, TimeMachine) sudah ada di folder jurnal.
> Langkah selanjutnya yang paling mungkin:
> 1. Merge branch ini ke main setelah review.
> 2. Kalibrasi threshold DSE tau setelah 69 test case Firebase Chat dijalankan.
> 3. Verifikasi live run end-to-end dengan device Android nyata.
