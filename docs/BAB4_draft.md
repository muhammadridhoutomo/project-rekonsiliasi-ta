# BAB 4 HASIL DAN PEMBAHASAN

## 4.1 Gambaran Implementasi

Modul Natural Language Processing (NLP) pada Pool 2 diimplementasikan menggunakan bahasa pemrograman Python dengan pustaka utama `scikit-learn`, `sentence-transformers`, dan `transformers`. Alur pemrosesan dimulai dari pembacaan data mutasi rekening koran yang terdiri atas kolom tanggal, keterangan, debit, kredit, dan saldo. Sistem menentukan arah arus kas secara otomatis (kredit atau *cash in* apabila nilai kredit lebih besar dari nol, serta debit atau *cash out* untuk kondisi sebaliknya), kemudian menjalankan tahapan praproses teks, ekstraksi fitur TF-IDF, klasifikasi menggunakan Support Vector Machine (SVM), perhitungan *confidence score*, hingga keputusan *routing* berdasarkan ambang batas (*confidence threshold*). Keluaran modul ini berupa dokumen JSON terstruktur yang memuat kode label akun, nama akun, nilai *confidence*, serta status transaksi (`OTOMATIS` atau `PERLU_REVIEW_MANUAL`). Transaksi yang berstatus perlu pemeriksaan manual akan ditinjau melalui antarmuka pada Pool 3 sebelum digabungkan kembali menjadi JSON bersih untuk pencocokan otomatis terhadap data Enterprise Resource Planning (ERP).

Tabel 4.1 Daftar Modul dan Berkas Implementasi Pool 2

| Nama Berkas | Fungsi Utama dalam Pipeline |
| --- | --- |
| `siapkan_data_coa.py` | Pembacaan mutasi BCA dan Mandiri, pelabelan berbasis aturan CoA, dan pembuatan sampel validasi 20% |
| `kamus_istilah.py` | Normalisasi teks, kamus pemetaan singkatan perbankan, dan daftar *stopword* domain |
| `metrik_preprocessing.py` | Pengukuran metrik praproses teks dan tingkat kerenggangan (*sparsity*) matriks TF-IDF |
| `latih_model_coa.py` | Pelatihan model SVM, evaluasi *5-fold cross-validation*, dan pengujian lintas-bank |
| `bandingkan_model_coa.py` | Perbandingan performa SVM, Random Forest, SBERT, dan FinBERT beserta uji statistik *paired t-test* |
| `eksperimen_perbaikan.py` | Perbandingan kernel RBF terhadap Linear serta uji ketahanan *masking* nama pihak dan *GroupKFold* |
| `threshold_coa.py` | Optimasi nilai ambang *confidence threshold* pada skema *StratifiedKFold* dan *StratifiedGroupKFold* |
| `evaluasi_routing_kb.py` | Pengukuran keempat metrik *confidence routing* dan simulasi integrasi *Knowledge Base* (Pool 3) |
| `simulasi_5bank_coa.py` | Pengujian kompatibilitas format mutasi lima bank (BCA, Mandiri, BNI, BRI, dan BSI) |
| `routing.py`, `proses_json.py` | Inferensi transaksi, penyaringan *confidence threshold*, dan kontrak pertukaran data JSON dengan Pool 3 |
| `feedback_learning.py`, `uji_active_learning.py` | Penyimpanan koreksi manual pengguna, pelatihan ulang model (*feedback loop*), dan evaluasi *active learning* 5 putaran |

## 4.2 Dataset dan Pelabelan Data Transaksi

Dataset transaksi riil yang dikumpulkan dari perusahaan mitra berjumlah **606 baris mutasi**, yang terdiri atas **337 transaksi BCA** (periode tahun 2023) dan **269 transaksi Mandiri** (periode tahun 2025). Setiap baris transaksi dipetakan ke dalam sub-kategori yang bersesuaian dengan struktur *Chart of Accounts* (CoA) perusahaan mitra (313 kode akun). Sebanyak 40 baris mutasi Mandiri yang hanya memuat nomor referensi internal tanpa informasi keterangan tujuan ditandai dengan label `PERLU_REVIEW` dan dikeluarkan dari tahap pelatihan model. Distribusi jumlah transaksi per sub-kategori disajikan pada Tabel 4.2.

Tabel 4.2 Distribusi Sampel Data Transaksi Riil per Sub-Kategori CoA

| Kode Sub-Kategori | Jumlah Transaksi | Kode Sub-Kategori | Jumlah Transaksi |
| --- | --- | --- | --- |
| `PAYABLE_VENDOR` | 164 | `OFFICE_GENERAL` | 6 |
| `RECEIVABLE_CUSTOMER` | 150 | `BANK_INTEREST` | 6 |
| `EMP_BENEFIT` | 53 | `OTHER_EXPENSE` | 5 |
| `LOAN` | 44 | `CASH_DEPOSIT` | 5 |
| `SALARY` | 36 | `TRANSPORT` | 5 |
| `BANK_CHARGE` | 33 | `UTILITIES`, `REVENUE_OTHER`, `REPAIR_MAINT` | masing-masing 2 |
| `INTERNAL_TRANSFER` | 25 | `COMMUNICATION`, `TRAVEL` | masing-masing 1 |
| `PETTY_CASH` | 14 | `TAX` | 12 |

Distribusi data pada Tabel 4.2 menunjukkan ketidakseimbangan kelas (*imbalanced dataset*) yang tinggi, di mana transaksi pembayaran vendor (`PAYABLE_VENDOR`) dan penerimaan piutang pelanggan (`RECEIVABLE_CUSTOMER`) mendominasi lebih dari separuh keseluruhan dataset. Sub-kategori yang memiliki kurang dari 5 sampel tidak diikutsertakan dalam perhitungan validasi silang karena jumlah sampelnya belum mencukupi pembagian 5 *fold*, sehingga menyisakan **558 transaksi** pada **14 sub-kategori** untuk evaluasi model. Pada pembuatan model akhir (*final deployment model*), sub-kategori minoritas (`COMMUNICATION`, `REVENUE_OTHER`, dan `UTILITIES`) diperkuat menggunakan tambahan sampel data sintesis. Untuk menjamin validitas *ground truth*, sebanyak 20% sampel (121 baris transaksi) telah disiapkan pada berkas `sampel_validasi_20persen.xlsx` untuk divalidasi silang oleh staf keuangan perusahaan mitra menggunakan koefisien *Cohen's Kappa* (`hitung_kappa.py`).

## 4.3 Hasil Praproses Teks dan Ekstraksi Fitur TF-IDF

Pengukuran performa tahap praproses teks dan ekstraksi fitur TF-IDF dijalankan pada seluruh 566 transaksi berlabel menggunakan skrip `metrik_preprocessing.py`. Ringkasan hasil pengukuran keempat metrik praproses beserta karakteristik matriks TF-IDF disajikan pada Tabel 4.3.

Tabel 4.3 Hasil Pengukuran Performa Tahap Praproses Teks dan Ekstraksi Fitur

| Metrik Evaluasi | Nilai Hasil Pengukuran |
| --- | --- |
| Total Token Sebelum Praproses | 2.761 token |
| Total Token Sesudah Praproses | 1.821 token |
| *Token Reduction Rate* | 34,05% |
| Jumlah *Stopword* dan *Boilerplate* yang Dieliminasi | 947 token |
| Kemunculan Singkatan yang Berhasil Dipetakan Kamus Sinonim | 122 token |
| Ukuran Kosakata Akhir (*Vocabulary Size*) | 326 token unik |
| Rata-Rata Panjang Token per Transaksi (*Average Token Length*) | 3,22 token/transaksi |
| Dimensi Fitur Matriks TF-IDF (*Unigram* + *Bigram*) | 754 fitur |
| Tingkat Kerenggangan Matriks (*Sparsity* TF-IDF) | 99,28% |

Berdasarkan Tabel 4.3, proses pembersihan teks berhasil mengeliminasi 34,05% token yang bersifat *noise* (seperti kode *switching* bank, kata penghubung, serta penunjuk bulan dan lokasi), sekaligus menormalisasi 122 kemunculan singkatan tidak baku ke bentuk baku melalui `KAMUS_RIIL`. Nilai *sparsity* matriks TF-IDF sebesar **99,28%** (jauh di atas batas karakteristik teks pendek 95%) membuktikan bahwa representasi vektor bersifat sangat renggang (*high-dimensional sparse matrix*), sehingga sesuai dengan karakteristik algoritme Support Vector Machine (SVM). Selain itu, analisis bobot TF-IDF tertinggi per kelas menunjukkan bahwa token paling berpengaruh telah relevan secara semantik terhadap masing-masing sub-kategori, seperti token `gaji` dan `thr` pada `SALARY`, token `bpjs` dan `kesehatan` pada `EMP_BENEFIT`, token `loan` dan `return` pada `LOAN`, serta token `biaya` dan `administrasi` pada `BANK_CHARGE`.

## 4.4 Hasil Klasifikasi dengan 5-Fold Cross-Validation

Evaluasi kinerja klasifikasi dilakukan menggunakan skema *5-fold Stratified Cross-Validation* pada 558 transaksi riil gabungan BCA dan Mandiri. Sebagai pembanding dasar (*baseline*), diuji pula pendekatan tanpa NLP yang hanya menebak sub-kategori mayoritas berdasarkan arah arus kas kredit (CR) atau debit (DB). Perbandingan hasil pengujian disajikan pada Tabel 4.4.

Tabel 4.4 Perbandingan Kinerja Klasifikasi terhadap Baseline pada 5-Fold Cross-Validation

| Metode Klasifikasi | Akurasi | Macro-F1 |
| --- | --- | --- |
| *Baseline* (hanya mengandalkan arah CR/DB tanpa teks) | 0,563 | 0,106 |
| TF-IDF *Word N-Gram* (1–2) + SVM | 0,952 | 0,893 |
| **TF-IDF Gabungan Kata + Karakter *N-Gram* (3–5) + SVM** | **0,955** | **0,895** |

Tabel 4.4 menunjukkan bahwa penambahan analisis teks NLP meningkatkan nilai Macro-F1 secara drastis dari 0,106 pada *baseline* menjadi **0,895** (akurasi **95,5%**). Penggabungan fitur *word n-gram* (1–2) dengan *character n-gram* (3–5) memberikan peningkatan tambahan karena *character n-gram* mampu mengenali potongan karakter pada singkatan yang menempel atau mengalami salah ketik (seperti `bpjstkfeb` atau `pjstk`). Apabila dianalisis per sumber bank, data BCA mencapai akurasi 97,3% (Macro-F1 0,967), sedangkan data Mandiri mencapai akurasi 92,9% (Macro-F1 0,805). Rincian metrik evaluasi untuk masing-masing dari 14 sub-kategori CoA disajikan pada Tabel 4.5.

Tabel 4.5 Kinerja Klasifikasi per Sub-Kategori CoA pada Model Terbaik

| Sub-Kategori CoA | Precision | Recall | F1-Score | Jumlah Sampel (n) |
| --- | --- | --- | --- | --- |
| `RECEIVABLE_CUSTOMER` | 0,97 | 1,00 | 0,99 | 150 |
| `LOAN` | 1,00 | 0,98 | 0,99 | 44 |
| `BANK_INTEREST` | 1,00 | 1,00 | 1,00 | 6 |
| `CASH_DEPOSIT` | 1,00 | 1,00 | 1,00 | 5 |
| `PAYABLE_VENDOR` | 0,99 | 0,94 | 0,96 | 164 |
| `INTERNAL_TRANSFER` | 0,93 | 1,00 | 0,96 | 25 |
| `TAX` | 1,00 | 0,92 | 0,96 | 12 |
| `EMP_BENEFIT` | 0,93 | 0,98 | 0,95 | 53 |
| `SALARY` | 0,97 | 0,92 | 0,94 | 36 |
| `PETTY_CASH` | 1,00 | 0,86 | 0,92 | 14 |
| `BANK_CHARGE` | 0,82 | 0,97 | 0,89 | 33 |
| `TRANSPORT` | 0,80 | 0,80 | 0,80 | 5 |
| `OTHER_EXPENSE` | 0,75 | 0,60 | 0,67 | 5 |
| `OFFICE_GENERAL` | 0,50 | 0,50 | 0,50 | 6 |

Berdasarkan Tabel 4.5, sebelas dari empat belas sub-kategori mencapai nilai F1-Score di atas 0,88. Dua sub-kategori dengan nilai terendah adalah `OFFICE_GENERAL` (0,50) dan `OTHER_EXPENSE` (0,67), yang disebabkan oleh jumlah sampel yang sangat sedikit (5 sampai 6 baris) serta kemiripan pola teks dengan pembayaran vendor (`PAYABLE_VENDOR`). Distribusi prediksi benar dan salah antar-kelas secara menyeluruh dapat dilihat pada matriks konfusi (*confusion matrix*) pada Gambar 4.1.

![Gambar 4.1 Confusion Matrix 5-Fold Cross-Validation pada 14 Sub-Kategori CoA](gambar_4_1_confusion_matrix.svg)

## 4.5 Perbandingan Model Klasifikasi dan Uji Signifikansi Statistik

Untuk memvalidasi pemilihan algoritme SVM sebagai model utama pada Pool 2, dilakukan pengujian komparatif terhadap tiga model pembanding sesuai metodologi penelitian, yaitu Random Forest, Sentence-BERT (SBERT `all-MiniLM-L6-v2`), dan FinBERT (`ProsusAI/finbert`). Seluruh model dievaluasi pada pembagian *5-fold Stratified Cross-Validation* yang identik. Hasil perbandingan keempat model disajikan pada Tabel 4.6 dan divisualisasikan pada Gambar 4.2.

Tabel 4.6 Perbandingan Performa Empat Model Klasifikasi pada 5-Fold Cross-Validation

| Model Klasifikasi | Accuracy | Precision (Macro) | Recall (Macro) | F1-Score Macro (Rata-Rata ± Std) |
| --- | --- | --- | --- | --- |
| **SVM (TF-IDF)** | **0,955** | **0,874** | **0,889** | **0,873 ± 0,068** |
| SBERT + Logistic Regression | 0,873 | 0,774 | 0,822 | 0,780 ± 0,051 |
| Random Forest (TF-IDF) | 0,907 | 0,790 | 0,794 | 0,776 ± 0,037 |
| FinBERT + Logistic Regression | 0,923 | 0,774 | 0,797 | 0,771 ± 0,021 |

![Gambar 4.2 Perbandingan Performa Model Klasifikasi pada 5-Fold Cross-Validation](gambar_4_3_perbandingan_model.svg)

Hasil uji signifikansi statistik *paired t-test* ($\alpha = 0,05$) terhadap nilai Macro-F1 per *fold* menunjukkan bahwa kombinasi **TF-IDF + SVM unggul secara signifikan terhadap FinBERT** ($t = 3,951$; $p = 0,0168 < 0,05$). Terhadap Random Forest ($t = 2,359$; $p = 0,0778$) dan SBERT ($t = 1,867$; $p = 0,1352$), SVM menghasilkan rata-rata F1-Score yang lebih tinggi hampir 10 poin persentase, meskipun secara statistik pada ukuran sampel 5 *fold* belum melewati batas signifikansi 0,05. Rendahnya performa FinBERT disebabkan oleh korpus pelatihan awalnya yang berbahasa Inggris formal finansial, sehingga kurang mampu menangkap semantik singkatan perbankan lokal berbahasa Indonesia dibandingkan representasi leksikal TF-IDF kata dan karakter. Selain unggul secara akurasi, model TF-IDF + SVM memiliki waktu inferensi yang jauh lebih cepat dan tidak membutuhkan perangkat keras GPU.

### 4.5.1 Justifikasi Pemilihan Kernel Linear terhadap RBF dan Uji Ketahanan Model

Untuk memberikan justifikasi empiris atas penggunaan kernel Linear dibandingkan kernel Radial Basis Function (RBF), dilakukan eksperimen perbandingan pada fitur yang sama (`eksperimen_perbaikan.py`). Selain itu, dilakukan dua pengujian ketahanan model, yaitu: (a) penghapusan (*masking*) 112 token nama pihak (vendor/pelanggan), serta (b) validasi ketat menggunakan *StratifiedGroupKFold* di mana seluruh baris yang memiliki teks identik ditempatkan pada *fold* yang sama (mengingat dari 558 baris transaksi terdapat 244 teks unik dan 314 baris transaksi berulang). Hasil eksperimen disajikan pada Tabel 4.7.

Tabel 4.7 Perbandingan Kernel Linear dan RBF pada Berbagai Skema Validasi dan Fitur

| Konfigurasi Fitur | Skema Validasi Silang | Kernel SVM | Akurasi | Macro-F1 |
| --- | --- | --- | --- | --- |
| Dengan nama pihak | *StratifiedKFold* (distribusi transaksi rutin) | **Linear** | **0,955** | **0,873** |
| Dengan nama pihak | *StratifiedKFold* (distribusi transaksi rutin) | RBF | 0,919 | 0,782 |
| Dengan nama pihak | *StratifiedGroupKFold* (teks belum pernah dilihat) | **Linear** | **0,843** | **0,737** |
| Dengan nama pihak | *StratifiedGroupKFold* (teks belum pernah dilihat) | RBF | 0,748 | 0,586 |
| Tanpa nama pihak (*masked*) | *StratifiedKFold* (distribusi transaksi rutin) | Linear | 0,891 | 0,805 |
| Tanpa nama pihak (*masked*) | *StratifiedKFold* (distribusi transaksi rutin) | RBF | 0,866 | 0,722 |
| Tanpa nama pihak (*masked*) | *StratifiedGroupKFold* (teks belum pernah dilihat) | Linear | 0,808 | 0,684 |
| Tanpa nama pihak (*masked*) | *StratifiedGroupKFold* (teks belum pernah dilihat) | RBF | 0,682 | 0,521 |

Tabel 4.7 membuktikan tiga temuan penting. Pertama, kernel Linear secara konsisten mengungguli kernel RBF di seluruh skenario dengan selisih Macro-F1 sebesar 0,09 hingga 0,15 poin, karena ruang fitur TF-IDF yang berdimensi tinggi telah terpisah secara linear. Kedua, pada pengujian terhadap teks transaksi yang benar-benar baru (*StratifiedGroupKFold*), model masih mampu mencapai akurasi **84,3%** dan Macro-F1 **0,737**. Ketiga, penghapusan nama pihak menurunkan Macro-F1 dari 0,873 menjadi 0,805, yang menunjukkan bahwa nama rekanan langganan merupakan sinyal historis yang sah bagi klasifikasi, sedangkan transaksi dari rekanan baru yang belum dikenal akan ditangani melalui mekanisme *confidence threshold*.

## 4.6 Penentuan Confidence Threshold dan Evaluasi Integrasi Knowledge Base

Setiap prediksi dari model SVM disertai nilai *confidence score* terkalibrasi pada rentang 0 hingga 1 yang dihitung secara *out-of-fold*. Pencarian nilai ambang (*grid search*) dilakukan pada rentang 0,50 hingga 0,99 dengan kriteria memaksimalkan nilai Macro-F1 pada transaksi yang diproses otomatis sekaligus menjaga cakupan otomatisasi (*auto-classification rate*) minimal 70%. Ringkasan hasil pencarian nilai ambang disajikan pada Tabel 4.8 dan kurva *trade-off*-nya ditunjukkan pada Gambar 4.3.

Tabel 4.8 Hasil Pencarian Nilai Ambang Confidence Threshold

| Threshold (τ) | Auto-Classification Rate | KB Referral Rate | Akurasi (Auto) | Macro-F1 (Auto) | Prediksi Salah yang Lolos | Prediksi Salah yang Dialihkan ke KB |
| --- | --- | --- | --- | --- | --- | --- |
| 0,50 | 95,2% | 4,8% | 0,972 | 0,886 | 15 | 15 |
| 0,60 | 91,2% | 8,8% | 0,976 | 0,901 | 12 | 18 |
| 0,70 | 84,2% | 15,8% | 0,994 | 0,994 | 3 | 27 |
| **0,72 (Optimal)** | **82,8%** | **17,2%** | **0,996** | **0,995** | **2** | **28** |
| 0,80 | 74,2% | 25,8% | 0,995 | 0,993 | 2 | 28 |
| 0,90 | 5,0% | 95,0% | 1,000 | 1,000 | 0 | 30 |

![Gambar 4.3 Kurva Optimasi Confidence Threshold terhadap Macro-F1 dan Cakupan Otomatisasi](gambar_4_2_kurva_threshold.svg)

Berdasarkan Tabel 4.8, nilai ambang optimal ditetapkan pada **τ* = 0,72**. Pada titik tersebut, sebanyak **82,80%** transaksi (462 dari 558 baris) diklasifikasikan secara otomatis oleh Pool 2 dengan akurasi mencapai **99,57%** (Macro-F1 0,995), sementara **28 dari total 30 kesalahan prediksi (93,3%) berhasil disaring dan dialihkan ke Pool 3**. Sebagai analisis sensitivitas pada skema *StratifiedGroupKFold* (teks yang belum pernah dilihat), penerapan τ = 0,72 menyaring 71 dari 89 kesalahan prediksi ke Pool 3 dengan akurasi otomatis sebesar 94,7%, namun cakupan otomatisasi turun menjadi 60,6%. Artinya, pada transaksi yang benar-benar baru, lebih banyak transaksi akan dirujuk ke Pool 3 dibandingkan pada transaksi rutin.

Selanjutnya, terhadap 96 transaksi yang memiliki *confidence score* di bawah 0,72, dilakukan pengujian integrasi dengan aturan *forward-chaining* pada modul *Knowledge Base* (Pool 3) yang mencakup pencocokan referensi entitas ERP, pencocokan nominal *invoice*/mutasi historis, dan kamus kata kunci operasional (`evaluasi_routing_kb.py`). Hasil pengukuran keempat metrik *routing* disajikan pada Tabel 4.9.

Tabel 4.9 Hasil Pengukuran Performa Confidence Routing dan Integrasi Knowledge Base

| Metrik Evaluasi Routing | Proporsi Transaksi | Nilai Persentase |
| --- | --- | --- |
| *Auto-Classification Rate* (diproses otomatis pada Pool 2) | 462 / 558 transaksi | **82,80%** |
| *KB Referral Rate* (dirujuk ke Pool 3 karena *confidence* < 0,72) | 96 / 558 transaksi | **17,20%** |
| *KB Resolution Rate* (berhasil diselesaikan aturan pada Pool 3) | 66 / 96 transaksi | **68,75%** |
| *Overall System Coverage* (total diselesaikan otomatis Pool 2 + Pool 3) | 528 / 558 transaksi | **94,62%** |
| Sisa Transaksi yang Memerlukan Konfirmasi Manual Staf Keuangan | 30 / 558 transaksi | **5,38%** |
| Akurasi Klasifikasi Otomatis Pool 2 | 462 transaksi | **99,57%** |
| Akurasi Sistem Hibrida Gabungan (Pool 2 + Pool 3) | 528 transaksi | **98,11%** |

Tabel 4.9 menunjukkan bahwa dari 96 transaksi ambigu yang dirujuk ke Pool 3, sebanyak 66 transaksi (**68,75%**) berhasil diklasifikasikan melalui aturan *forward-chaining* (35 transaksi melalui referensi rekanan ERP, 20 transaksi melalui pencocokan nominal *invoice*/mutasi, dan 11 transaksi melalui kamus operasional). Dengan demikian, cakupan otomatisasi sistem secara keseluruhan (*Overall System Coverage*) mencapai **94,62%** dengan tingkat akurasi gabungan **98,11%**, dan hanya menyisakan **5,38%** transaksi (30 baris) yang memerlukan tindakan pemeriksaan manual oleh staf keuangan sebelum menghasilkan keluaran JSON bersih (`proses_json.py`).

### 4.6.1 Mekanisme Pembelajaran Berkelanjutan (*Feedback Loop*) dan Evaluasi 5 Putaran

Sesuai masukan praktisi mitra pada pertemuan evaluasi sistem (23 November 2026), sistem klasifikasi harus mampu belajar dari setiap koreksi pengguna, baik pada transaksi berkepercayaan rendah (*confidence* < 0,72) maupun transaksi berkepercayaan tinggi (*confidence* ≥ 0,72) yang tetap dikoreksi staf keuangan (misalnya koreksi transfer *in-house* antar-rekening perusahaan menjadi `INTERNAL_TRANSFER`). Mekanisme ini diimplementasikan pada `feedback_learning.py` dan diintegrasikan langsung ke `terapkan_koreksi()` serta `catat_koreksi_tunggal()` pada `proses_json.py` melalui dua lapis: (1) pencatatan permanen ke `data/feedback_koreksi.csv` sebagai memori koreksi langsung untuk pola teks yang sama, dan (2) pelatihan ulang model SVM dengan penimpaan (*override*) label lama serta penguatan bobot koreksi manusia agar *hyperplane* turut beradaptasi terhadap transaksi baru yang serupa.

Untuk mengukur efektivitas pembelajaran dari koreksi manusia, dilakukan eksperimen *active learning* 5 putaran (`uji_active_learning.py`) dengan memisahkan 20% teks unik sebagai *hold-out test set* (93 transaksi yang tidak pernah masuk pelatihan), 20% sebagai data latih awal (84 transaksi), dan 60% sisanya dialirkan secara bertahap dalam 5 putaran. Pada setiap putaran, prediksi yang salah dikoreksi dan dimasukkan ke pelatihan ulang, lalu model diuji kembali pada *hold-out test set* yang sama. Hasilnya disajikan pada Tabel 4.10.

Tabel 4.10 Hasil Evaluasi Pembelajaran Berkelanjutan (*Active Learning*) 5 Putaran pada Hold-Out Teks Baru (n = 93)

| Putaran | Keterangan Tahap | Total Data Latih | Transaksi Masuk | Jumlah Dikoreksi | Akurasi Hold-Out | Macro-F1 Hold-Out |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Model Awal (sebelum koreksi) | 84 | 0 | 0 | 0,6559 | 0,4992 |
| 1 | Setelah Koreksi Putaran 1 | 105 | 77 | 21 | 0,6344 | 0,5718 |
| 2 | Setelah Koreksi Putaran 2 | 129 | 76 | 24 | 0,6774 | 0,7218 |
| 3 | Setelah Koreksi Putaran 3 | 137 | 76 | 8 | 0,6774 | 0,7218 |
| 4 | Setelah Koreksi Putaran 4 | 140 | 76 | 3 | **0,8817** | **0,7929** |
| 5 | Setelah Koreksi Putaran 5 | 145 | 76 | 5 | **0,8817** | **0,7929** |

Tabel 4.10 membuktikan bahwa mekanisme *feedback loop* meningkatkan kinerja klasifikasi pada transaksi baru secara nyata: Akurasi *hold-out* meningkat dari **65,59%** pada model awal menjadi **88,17%** (+22,58 poin persentase) dan Macro-F1 meningkat dari **0,4992** menjadi **0,7929** (+0,2937 poin) setelah 5 putaran koreksi (total 61 koreksi kumulatif), sementara beban koreksi pengguna turun drastis dari 21–24 transaksi pada putaran awal menjadi hanya 3–5 transaksi pada putaran ke-4 dan ke-5.

## 4.7 Evaluasi Lintas-Bank dan Kompatibilitas Format Lima Bank

Untuk menguji kemampuan generalisasi model terhadap perbedaan struktur keterangan antar-bank, dilakukan pengujian pelatihan pada satu bank dan pengujian pada bank lainnya (BCA ke Mandiri dan sebaliknya), serta pengujian kompatibilitas terhadap kelima bank dalam ruang lingkup penelitian (BCA, Mandiri, BNI, BRI, dan BSI). Mengacu pada metode pembangkitan data sintesis terstruktur Aluffi et al. (2025), sebanyak 270 transaksi berpola format mutasi standar BNI (BNIDirect/E-Channel), BRI (CMS BRI/BRIVA), dan BSI (BSI Net/Syariah) dibangkitkan dan diuji melalui skrip `simulasi_5bank_coa.py`. Hasil evaluasi lintas-bank dan kompatibilitas lima bank disajikan pada Tabel 4.11.

Tabel 4.11 Hasil Evaluasi Lintas-Bank dan Kompatibilitas Format Lima Bank

| Skema Pengujian | Sumber Data Uji | Jenis Data | Jumlah (n) | Akurasi | Macro-F1 |
| --- | --- | --- | --- | --- | --- |
| Lintas-Bank (Latih BCA, Uji Mandiri) | Mandiri | Riil/Dummy Mitra | 150 | 0,540 | 0,412 |
| Lintas-Bank (Latih Mandiri, Uji BCA) | BCA | Riil Mitra | 328 | 0,470 | 0,364 |
| *Zero-Shot* (Latih BCA + Mandiri Riil) | BNI | Simulasi Format Standar | 90 | 0,911 | 0,706 |
| *Zero-Shot* (Latih BCA + Mandiri Riil) | BRI | Simulasi Format Standar | 90 | 0,933 | 0,765 |
| *Zero-Shot* (Latih BCA + Mandiri Riil) | BSI | Simulasi Format Standar | 90 | 0,844 | 0,732 |
| *5-Fold CV* Gabungan 5 Bank | BCA | Riil Mitra | 333 | 0,964 | 0,942 |
| *5-Fold CV* Gabungan 5 Bank | Mandiri | Riil/Dummy Mitra | 225 | 0,924 | 0,815 |
| *5-Fold CV* Gabungan 5 Bank | BNI, BRI, BSI | Simulasi Format Standar | 270 | 1,000 | 1,000 |
| ***5-Fold CV* Gabungan 5 Bank (Agregat)** | **Seluruh 5 Bank** | **Gabungan (N = 828)** | **828** | **0,965** | **0,941** |

Hasil pada Tabel 4.11 menunjukkan bahwa pelatihan pada satu bank saja menghasilkan F1-Score lintas-bank yang rendah (0,364–0,412) akibat perbedaan kosakata dan rekanan transaksi. Namun, ketika model dilatih pada gabungan BCA dan Mandiri disertai pembersihan *boilerplate* lima bank pada `kamus_istilah.py`, pengujian *zero-shot* terhadap format BNI, BRI, dan BSI mampu mencapai akurasi 84,4% hingga 93,3% (Macro-F1 0,706–0,765). Ketika sampel kelima bank digabungkan dalam pelatihan (*N* = 828), akurasi agregat mencapai **96,5%** (Macro-F1 **0,941**) sekaligus meningkatkan Macro-F1 pada data Mandiri dari 0,805 menjadi **0,815**.

## 4.8 Keterbatasan Penelitian dan Rencana Tindak Lanjut

Beberapa keterbatasan teknis yang ditemukan dalam penelitian ini beserta langkah mitigasinya adalah sebagai berikut:

1. **Ketidakseimbangan Sampel pada Sub-Kategori Minoritas:** Lima sub-kategori CoA (`UTILITIES`, `REVENUE_OTHER`, `REPAIR_MAINT`, `COMMUNICATION`, dan `TRAVEL`) memiliki kurang dari 5 transaksi pada data riil awal. Penanganan dilakukan melalui penguatan data sintesis, aturan *forward-chaining* pada Pool 3, serta mekanisme *feedback learning* yang langsung mempelajari koreksi pengguna.
2. **Validasi dengan Pakar Domain (*Domain Expert*) dan Penyelarasan ERP Avolut:** Pelabelan awal dilakukan secara semi-otomatis berdasarkan aturan kata kunci dan struktur CoA mitra. Pada pertemuan evaluasi sistem bersama perwakilan mitra (23 November 2026), pihak mitra telah meninjau langsung alur kategorisasi dan sampel data secara lisan (*expert walkthrough*) serta memberikan masukan bisnis penting (termasuk pemisahan transaksi *in-house* antar-rekening perusahaan sebagai `INTERNAL_TRANSFER` dan kewajiban pembelajaran dari koreksi manual). Selanjutnya, pada 27 November 2026 tim ERP Avolut telah mengonfirmasi secara resmi seluruh 21 kategori NLP dengan membuatkan **27 objek Charge** pada *sandbox* ERP iDempiere 13 (`dev-recon.midsuit.com`) yang penamaannya identik dengan kode label NLP, sekaligus menetapkan kode akun CoA untuk `BANK_CHARGE` (`8.2.00.08`) serta `BANK_INTEREST` (`8.2.00.10` untuk kredit dan `1.1.08.08` untuk pajak bunga debit). Pemetaan final dan klien integrasi *sandbox* telah diimplementasikan pada `kategori_keuangan.py`, `proses_json.py`, dan `erp_sandbox_client.py`. Validasi tertulis pada 121 baris Excel untuk perhitungan numerik *Cohen's Kappa* tetap dicatat sebagai penguatan formal apabila diperlukan.
3. **Ketersediaan Dokumen Rekening Koran BNI, BRI, dan BSI:** Berdasarkan konfirmasi langsung pihak mitra pada pertemuan 23 November 2026, perusahaan tidak memiliki rekening koran aktif BSI dan mutasi BRI yang tersedia tidak variatif, sehingga mitra menyetujui penggunaan data simulasi berpola format standar bank BNI, BRI, dan BSI (Tabel 4.11) mengacu pada metodologi Aluffi et al. (2025).
