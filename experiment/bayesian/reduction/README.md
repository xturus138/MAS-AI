# Bayesian Optimization — TC Reduction (QA Asli)

**Status: EKSPERIMEN JALAN, MENUNGGU KONFIRMASI SENSEI**
**Dibuat:** 2026-08-24 · **Diperbarui:** 2026-08-26

> Baca `Hasil AI/JAIST/BO_5_KEPUTUSAN_SESI_2026-08-26.md` untuk riwayat keputusan lengkap dan
> `Hasil AI/JAIST/BO_3_KONTEKS_UTAMA_DISKUSI.md` untuk konteks diskusi sensei/Pak Adam.
> File ini sengaja diringkas — cuma status teknis notebook di folder ini.

---

## Konteks

Eksperimen ini menguji apakah BO dapat mereduksi subset dari 69 TC QA asli Firebase Chat
(dari Suitmedia) tanpa kehilangan bug recall — dan sekarang juga divalidasi ke data bug
ASLI dunia nyata (bukan cuma dummy) lewat dataset publik GitBugs.

Ini masih **interpretasi alternatif** dari arahan sensei (reduction diterapkan ke 69 TC QA
asli, bukan ke TC generated agent seperti hipotesis utama di `BO_3`) — **belum dikonfirmasi**.

---

## Isi folder ini

| File | Isi |
|---|---|
| `Uji Coba Reduction.ipynb` | Notebook utama. 40 sel, 11 blok eksperimen (Step4/EXP0 kalibrasi theta, EXP1-EXP10). Data: 69 TC QA asli Firebase Chat + oracle 13 bug **dummy** (label buatan peneliti, dikonsentrasikan di 2 Menu "risky"). |
| `Uji Coba Reduction - Data Bug Nyata (GitBugs HBase).ipynb` | Notebook validasi, struktur **full-parity** dengan notebook utama (40 sel, 11 blok eksperimen yang sama persis). Data: 250 bug report **ASLI** Apache HBase (dataset publik [GitBugs](https://github.com/av9ash/gitbugs)), oracle = field `Priority`+`Resolution` asli dari maintainer (BUKAN label buatan). |
| `results/` | Output CSV/JSON/PNG dari kedua notebook (di-generate ulang tiap kali dijalankan). |
| `../data/gitbugs/` | Data mentah + sampel GitBugs (`hbase_bugs_full_cleaned.csv`, `hbase_bugs_sample_for_bo.csv`) yang dipakai notebook validasi. |

---

## Status per 2026-08-26

**Dua bug matematika sudah ditemukan & diperbaiki**, divalidasi lewat run "all" 9-vectorizer sungguhan (bukan cuma quick-mode):

1. `best_method` dulu terkunci ke vectorizer pertama (TF-IDF) untuk EXP2-EXP7/EXP9b — **fixed**, sekarang pakai pemenang aktual EXP1.
2. `best_so_far` di `run_reduction_loop` dulu pakai `np.mean(train_y)` (salah untuk target biner 0/1), seharusnya `np.max(train_y)` — **fixed**. Juga ditemukan inkonsistensi sama di sel demo visualisasi EXP10 (dua notebook) — **fixed juga**.

**Hasil pasca-fix (data dummy, 9 vectorizer):** cuma 2 dari 9 vectorizer capai 100% recall — **Feature Hashing** (47 TC, pemenang baru) dan TF-IDF (56 TC). 7 vectorizer berbasis embedding semantik (termasuk Multilingual E5 yang dulu jadi pemenang SEBELUM bug diperbaiki) gagal berat (15-38% recall). EXP10 gabungan: 49 TC, 100% recall, vs baseline acak yang butuh full 69 TC.

**Hasil validasi data bug ASLI (GitBugs HBase, quick-mode TF-IDF+Feature Hashing):** keunggulan BO atas baca acak nyaris hilang begitu labelnya asli, bukan dummy Menu-clustered — TF-IDF butuh baca 247 dari 250 bug report untuk temukan semua 35 bug serius+fixed asli. Ini memperkuat kekhawatiran bahwa performa di data dummy sangat bergantung pada struktur Menu-clustering buatan, bukan kemampuan generalisasi BO ke pola bug sungguhan.

Detail lengkap (tabel angka, desain eksperimen, keterbatasan yang diakui) ada di `BO_5_KEPUTUSAN_SESI_2026-08-26.md`.

---

## Perbedaan dengan prioritization/

| | prioritization/ | reduction/ (ini) |
|---|---|---|
| Semua 69 TC dijalankan? | Ya | **Tidak** — ada yang di-skip |
| BO berhenti kapan? | Setelah semua TC selesai | **Stopping criterion θ** |
| Metric utama | Simple regret | **Bug recall** |
| Oracle | Dummy (13 bug) | Dummy (13 bug) + validasi data bug ASLI (GitBugs) |

---

## Next step

1. Konfirmasi ke sensei: interpretasi reduction pada TC QA asli vs TC generated agent (masih terbuka, lihat `BO_3`).
2. Jalankan notebook GitBugs mode `all` (9 vectorizer penuh, termasuk embedding) di Hakusan.
3. Update PPT Zenmi supaya cerminkan Feature Hashing (bukan E5) sebagai pemenang pasca-fix.
4. Diskusikan ke sensei: temuan "BO ≈ acak" di data bug ASLI — apakah ini alasan untuk menghentikan/mengubah arah thread BO ini.
