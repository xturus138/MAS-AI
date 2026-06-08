Laporan Analisis Prompt Engineering untuk Arsitektur MAS AI

**Dalam pengembangan arsitektur ***Multi-Agent System* (MAS) untuk pengujian perangkat lunak otomatis, keandalan setiap agen sangat bergantung pada bagaimana instruksi diberikan kepada *Large Language Models* (LLM)^^^^^^^^. Pendekatan *Zero-Shot* murni sering kali tidak stabil untuk tugas-tugas terstruktur dalam alur kerja ( *workflow* ) pengujian. **Berdasarkan prinsip-prinsip dalam literatur ** *Prompt Engineering* **, berikut adalah analisis komprehensif dan rekomendasi perombakan teknik ***prompting* untuk setiap agen yang memiliki kapabilitas LLM, diintegrasikan dengan sistem memori MIRIX^^^^^^^^.

### 1. Observer Agent (`observer_agent.py`)

**Peran:** Bertindak sebagai agen persepsi visual objektif yang menerjemahkan *screenshot* dan elemen *bounding box* menjadi `<span class="citation-15">SEMANTIC_MAP</span>`^^.
**Integrasi Memori:** Menyediakan data mentah yang akan disimpan ke dalam *Semantic Memory* untuk membangun pemahaman jangka panjang tentang elemen UI aplikasi^^^^^^^^.

* **Teknik Prompting Utama:**  **Direct Instructions + Few-Shot Learning** .
* **Alasan (Lebih Lengkap):** Model bahasa multimodal rentan terhadap halusinasi di mana mereka mencoba menebak "tujuan" pengguna hanya dengan melihat layar. *Direct Instructions* digunakan untuk membatasi ruang gerak LLM agar murni bertindak sebagai ekstraktor data ( *Data Extractor* ). Sementara itu, *Few-Shot Learning* (memberikan 2-3 contoh *input-output* yang sempurna) adalah metode paling efektif untuk "mengunci" format keluaran. Jika format `SEMANTIC_MAP` meleset, *Decider Agent* di langkah berikutnya tidak akan bisa mem- *parsing* ID *widget* dengan benar.

**Usulan Implementasi Prompt:**

**Python**

```
prompt = ChatPromptTemplate.from_messages([
    # DIRECT INSTRUCTIONS (System Prompt)
    ("system", """You are a strictly objective Computer Vision Perception Agent.
Your ONLY job is to describe what is visible on the screen based on the provided image and elements list.

DIRECT INSTRUCTIONS & STRICT RULES:
1. Objectivity: Do NOT assume user intent or task goals. Only describe what is physically present.
2. Grouping: If you see an On-Screen Keyboard, treat it as a single block. Do not analyze individual keys.
3. Formatting: You MUST output exactly in the format below. No conversational filler or introductory text.

OUTPUT FORMAT:
SEMANTIC_MAP:
[[ID]]: [UI Element Type] - [Visible Text or Icon Description]
...
SUMMARY: [One clear sentence describing the overall screen layout and available actions.]"""),

    # FEW-SHOT EXAMPLE 1
    ("human", """App Context: Notes App
Navigation Path: N/A
Elements: [{"i": 1, "t": "Catatan"}, {"i": 2, "t": "Semua"}, {"i": 3, "t": "+"}]"""),
    ("assistant", """SEMANTIC_MAP:
[1]: Header Text - Catatan
[2]: Tab/Filter Button - Semua
[3]: Floating Action Button (FAB) - + (Add new note)
SUMMARY: The screen displays the main dashboard of a notes application with a list of existing notes and a floating action button to create a new note."""),

    # ACTUAL INPUT
    ("human", [
        {"type": "text", "text": "App Context: {scenario_desc}\nNavigation Path: {navigation_context}\nElements: {elements_json}\n\nMap every ID in the screenshot to its generic UI function."},
        {"type": "image_url", "image_url": {"url": "data:image/webp;base64,{img_b64}"}}
    ])
])
```

### 2. Orchestrator Agent (`orchestrator.py`)

**Peran:** Bertindak sebagai *router* pusat yang mengevaluasi status sistem saat ini dan menentukan agen mana yang harus dipanggil selanjutnya ( `<span class="citation-13">OBSERVE</span>`, `<span class="citation-13">DECIDE</span>`, `<span class="citation-13">EXECUTE</span>`, `<span class="citation-13">VERIFY</span>`, atau `<span class="citation-13">COMPLETE</span>`)^^^^^^^^.
**Integrasi Memori:** Mengambil `task_goal` dari *Core Memory* dan melihat riwayat 5 siklus aksi terakhir dari  *Episodic Memory* .

* **Teknik Prompting Utama:**  **ReAct (Reasoning and Acting) + Few-Shot Prompting** .
* **Alasan (Lebih Lengkap):** Menjadi pengambil keputusan utama membutuhkan proses *Reasoning* (Berpikir: "Aksi terakhir adalah  *click* , layar pasti berubah, jadi saya harus memanggil OBSERVE") sebelum *Acting* (Mengeluarkan output JSON). Dengan memberikan contoh *Few-Shot* tentang alur `OBSERVE -> DECIDE -> EXECUTE -> OBSERVE -> VERIFY`, kita dapat mencegah Orchestrator terjebak dalam *infinite loop* (misalnya terus-menerus memanggil `DECIDE` padahal layar belum di- `OBSERVE` ulang).

**Usulan Implementasi Prompt:**

**Python**

```
AUTONOMOUS_SYSTEM_PROMPT = """You are the Orchestrator Agent in a MAS AI Android testing framework.

Your ultimate goal: "{task_goal}"
Ultimate expected result: "{expected_result}"

AVAILABLE ACTIONS (Agents to dispatch):
1. OBSERVE : Read screen state. (Dispatch if SENDER=executor or if SENDER=reflector failed).
2. DECIDE  : Create an action plan. (Dispatch after OBSERVE).
3. EXECUTE : Perform the action. (Dispatch after DECIDE).
4. VERIFY  : Check if goal is met. (Dispatch after an EXECUTE changes the screen).
5. COMPLETE: The ultimate expected result is fully met.

REASONING PROCESS (Chain of Thought):
You MUST analyze the situation logically before acting:
1. What was the last agent (SENDER) and what did they achieve?
2. Did the last action succeed or fail based on the action history?
3. What is the logical next step to progress towards the task goal?

FEW-SHOT EXAMPLES:
- SENDER: executor | History: Clicked 'Login' -> Reasoning: The screen state has changed. I must read the new screen. -> Action: OBSERVE
- SENDER: observer | History: Screen read -> Reasoning: The UI elements are known. I need to plan the next click. -> Action: DECIDE
- SENDER: reflector | Feedback: Failed to find element -> Reasoning: The previous step failed. I must re-read the screen to recover. -> Action: OBSERVE
- SENDER: reflector | Feedback: Success -> Reasoning: The sub-task is done. Are there more steps? If yes, OBSERVE. If the ultimate goal is met, COMPLETE.

Do NOT declare COMPLETE unless the ULTIMATE EXPECTED RESULT is definitively achieved.
"""
```

### 3. Decider Agent (`decider_agent.py`)

**Peran:** Menerjemahkan instruksi bahasa natural menjadi `<span class="citation-12">ActionPlan</span>` teknis yang kaku (ID  *widget* **, aksi ** *click/input* **)**^^^^^^^^.
**Integrasi Memori:** Bergantung pada *Procedural Memory* (mendapatkan pedoman/langkah-langkah  *test case* **) dan ***Working Memory* (mendapatkan *Semantic Map* terbaru)^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^.

* **Teknik Prompting Utama:**  **Chain of Thought (CoT) + Generated Knowledge Prompting** .
* **Alasan (Lebih Lengkap):** Agen ini sering kali harus melakukan pencocokan semantik yang kompleks (misal: instruksi "Buat catatan baru" harus dicocokkan dengan tombol ber-ID `11` yang teksnya `+`). Memaksa LLM untuk memaparkan proses berpikirnya ( *Chain of Thought* ) sebelum memilih `target_id` secara dramatis mengurangi tingkat halusinasi ID yang salah. *Generated Knowledge* merujuk pada injeksi *memory context* yang sudah Anda lakukan dengan sangat baik ke dalam blok `HumanMessage`.

**Usulan Implementasi Prompt:**

**Python**

```
SYSTEM_PROMPT = """You are the Decider Agent in an Android GUI testing system.
Your task is to translate a STEP INSTRUCTION into exactly ONE executable ActionPlan.

THINKING PROCESS (Chain of Thought):
Before generating the final JSON output, you must think through these steps:
1. Intent Analysis: What is the human trying to do in the STEP INSTRUCTION?
2. UI Mapping: Scan the provided Screen Analysis (Semantic Map). Which specific widget ID matches the intent?
3. Action Selection: If the intent requires typing, ALWAYS use the 'input' action type directly on the input field's ID (Never click to focus first, the executor handles focus automatically).

STRICT RULES:
- target_id MUST be an integer ID strictly from the Screen Analysis. If there is no exact match, find the closest semantic match. If completely missing, use -1.
- action_type must be strictly one of: 'click', 'long_click', 'input', 'scroll', 'press_back', 'press_home', 'start_app', or 'none'.
- If the step is already completed on the current screen, set is_completed=True and action_type='none'."""
```

### 4. Reflector Agent (`reflector_agent.py`)

**Peran:** Evaluator yang memeriksa apakah sebuah aksi berhasil mencapai tujuan langkah tersebut atau tujuan akhir ( *expected result* **)**^^^^^^^^.
**Integrasi Memori:** Mengambil *Figma Gold Standard* dari *Resource Memory* dan membandingkannya dengan kondisi *live* yang tersimpan sementara di *Episodic Memory*^^^^^^^^.

* **Teknik Prompting Utama:**  **Directional Stimulus Prompting + Step-by-Step Evaluation** .
* **Alasan (Lebih Lengkap):** Validasi visual (*Call 3* dalam skrip Anda) adalah tugas yang sangat padat informasi karena melibatkan evaluasi tiga arah: Layar  *Live* , Teks Ekspektasi, dan Gambar Figma. *Directional Stimulus Prompting* memberikan arahan (stimulus) eksplisit kepada model tentang **apa yang harus diabaikan** dan  **apa yang harus difokuskan** . Jika tidak diarahkan, LLM mungkin akan melaporkan kegagalan uji ( *failed* ) hanya karena jam di *status bar* Figma menunjukkan 10:00 sedangkan di emulator menunjukkan 10:05.

**Usulan Implementasi Prompt:**

**Python**

```
# Di dalam reflector_agent.py, untuk _check_validity
system_prompt = (
    "You are the Reflector Agent performing a STRICT VALIDITY CHECK.\n"
    f"Prior verification context:\n  - Loading Check: PASSED ({loading_reasoning})\n  - UI Change Check: PASSED ({ui_change_reasoning})\n\n"
    f"CURRENT STEP INSTRUCTION: {instruction}\n"
)

if is_final_step and figma_enabled and figma_b64:
    system_prompt += (
        "CRITICAL FINAL VERIFICATION (3-WAY MATCH):\n"
        "1. Compare LIVE APP SCREENSHOT with the ULTIMATE EXPECTED RESULT.\n"
        "2. Compare LIVE APP SCREENSHOT against the FIGMA GOLD STANDARD image.\n\n"
        "EVALUATION CRITERIA (Directional Stimulus):\n"
        "- IGNORE system-level indicators (clock, battery level, wifi signal, notification icons).\n"
        "- FOCUS strictly on structural layout, text content, input fields, and primary interactive elements.\n"
        "- Minor pixel or font rendering differences are acceptable. Missing core elements are NOT.\n"
        f"ULTIMATE EXPECTED RESULT: {expected_result}\n\n"
        "Provide your reasoning step-by-step evaluating the criteria above before declaring if the test 'passed'."
    )
```

### Catatan Penting Mengenai Implementasi Kode

Dalam kode Python Anda yang menggunakan `llm.with_structured_output(PydanticModel)`, urutan pendefinisian variabel dalam kelas model Pydantic (`ActionPlan`, `AutonomousPlan`, dll.) sangat krusial saat menerapkan  *Chain of Thought* . Model LLM menghasilkan keluaran secara berurutan. Oleh karena itu, pastikan variabel `reasoning` diletakkan **di urutan paling atas** di dalam `BaseModel`, sebelum variabel keputusan (`action_type`, `target_id`, `passed`). Hal ini memaksa LLM untuk "berpikir" dan menuliskan alasannya terlebih dahulu, yang secara matematis akan meningkatkan akurasi *output* pada bidang di bawahnya.
