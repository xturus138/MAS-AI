# Bayesian Optimization — TC Reduction (QA Asli)

**Status: BELUM DIMULAI**
**Dibuat:** 2026-08-24

---

## Konteks

Eksperimen ini menguji apakah BO dapat mereduksi subset dari 69 TC QA asli Firebase Chat
(dari Suitmedia) tanpa kehilangan terlalu banyak bug recall.

Ini adalah **interpretasi alternatif** dari arahan sensei — belum dikonfirmasi.
Baca konteks lengkap di:
`D:\Kuliah\SKRIPSI\...\Dokumen Kepake\Hasil AI\JAIST\BO_3_KONTEKS_UTAMA_DISKUSI.md`
`D:\Kuliah\SKRIPSI\...\Dokumen Kepake\Hasil AI\JAIST\BO_2_TC_REDUCTION_ALTERNATIF.md`

---

## Perbedaan dengan prioritization/

| | prioritization/ | reduction/ (ini) |
|---|---|---|
| Semua 69 TC dijalankan? | Ya | **Tidak** — ada yang di-skip |
| BO berhenti kapan? | Setelah semua TC selesai | **Stopping criterion θ** |
| Metric utama | Simple regret | **Bug recall** |
| Oracle | Dummy (13 bug) | Butuh ground truth nyata |

---

## Rencana eksperimen

EXP1–EXP4: sama dengan prioritization (vectorizer, kernel, HP kernel, AF)
EXP5: HP AF — evaluasi berdasarkan bug recall, bukan kecepatan konvergensi
EXP6: Stopping threshold θ ∈ {0.05, 0.1, 0.2, 0.3}
EXP7: Budget constraint max TC ∈ {20, 30, 40, 50} dari 69

---

## Next step

1. Konfirmasi interpretasi ke sensei
2. Jalankan semua 69 TC nyata untuk ground truth
3. Buat notebook reduction di sini
