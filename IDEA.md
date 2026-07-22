# IDEA.md — Status project MAS AI (update saat ada progress)

## Pointer
Baca `AGENTS.md` terlebih dahulu. Untuk detail arsitektur coding, baca juga `CLAUDE.md`.

Dokumen skripsi / bimbingan / paper: folder terpisah  
`D:\Kuliah\SKRIPSI\RESEARCH TEMA PROKSI\AUTOMATED TESTING ANDROID\Dokumen Kepake\`  
(lihat `AGENTS.md` + `IDEA.md` di sana).

## Status sekarang
- **Repo:** MAS AI (implementasi multi-agent Android GUI testing)
- **Mode utama yang dipakai:** *perlu dikonfirmasi* (`predefined` / `autonomous`)
- **Fokus dev terakhir:** Phase-1 instrumentasi DSE uncertainty untuk Observer sudah landed — measurement only, disabled by default (`OBSERVER_UNCERTAINTY_ENABLED=false`), tidak mempengaruhi Decider/Executor/Reflector/routing/verdict.
- **Blocker teknis:** *isi jika ada* (device, provider LLM, Figma, observer, dll.)
- **Next step:** review & fix gaps antara diagram arsitektur vs implementasi predefined mode — detail di `docs/predefined-workflow-diagram-gaps.md` (Recorder timing, memory box, bridge navigation, retry logic tidak tergambar di diagram)
- **Next step (riset uncertainty):** sisa kerja riset DSE masih PENDING — evaluasi prompt / temperature / sample-count (M) / kalibrasi threshold. Panduan di `docs/observer-uncertainty.md`.

## Catatan sesi (maks. 5 bullet, hapus yang basi)
- Setup memori project: `AGENTS.md` + `IDEA.md` (folder-only).
- `CLAUDE.md` tetap sumber detail arsitektur untuk coding agent.
- Observer DSE uncertainty (Phase 1) didokumentasikan di `docs/observer-uncertainty.md`; desain lengkap di `docs/observer-dse-uncertainty-design.md`.

## Cara update
Setelah sesi produktif, ubah **Status sekarang** dan **Catatan sesi** saja. Jangan menyalin ulang isi `AGENTS.md` / `CLAUDE.md` ke sini.
