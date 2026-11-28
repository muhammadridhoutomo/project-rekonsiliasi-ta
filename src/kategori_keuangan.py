# =====================================================================
# kategori_keuangan.py  (VERSI 2 - sudah mengacu CoA asli dari Pak Depta)
#
# Isi file ini:
#   1. KATEGORI          -> kategori LAMA (placeholder buatan sendiri). Dibiarkan supaya
#                           skrip lama (generate_data_sintesis.py, label_data_riil.py, dst) tetap jalan.
#   2. LABEL_COA         -> kategori BARU Pool 2, disusun dari kelompok akun di CoA.xlsx
#   3. MAP_LAMA_KE_BARU  -> peta kode lama (6-5000, dst) ke label baru
#   4. MAP_SINTESIS_KE_BARU -> peta nama kategori data sintesis ke label baru
#   5. PEMILIK_REKENING  -> nama perusahaan pemilik rekening (untuk mendeteksi transfer internal)
# =====================================================================

# ---------------------------------------------------------------------
# 1. KATEGORI LAMA (jangan dihapus dulu)
# ---------------------------------------------------------------------
KATEGORI = {
    # Cash Out (Pengeluaran)
    "6-1100": {"nama": "Biaya Administrasi Bank", "jenis": "cash_out"},
    "6-2200": {"nama": "Biaya Listrik", "jenis": "cash_out"},
    "6-2300": {"nama": "Biaya Telepon/Internet", "jenis": "cash_out"},
    "6-3100": {"nama": "Biaya Operasional (BBM, dll)", "jenis": "cash_out"},
    "6-4000": {"nama": "Gaji Karyawan", "jenis": "cash_out"},
    "6-5000": {"nama": "Pembayaran Vendor/Supplier", "jenis": "cash_out"},
    "6-6000": {"nama": "Biaya BPJS Ketenagakerjaan/Kesehatan", "jenis": "cash_out"},
    "6-7000": {"nama": "Pembayaran Pajak/Setoran Negara", "jenis": "cash_out"},
    "6-8000": {"nama": "Biaya Penolakan/Lain-lain", "jenis": "cash_out"},
    "6-9000": {"nama": "Transfer Antar Bank (Switching) - Keluar", "jenis": "cash_out"},

    # Cash In (Pemasukan)
    "4-1000": {"nama": "Pendapatan Penjualan/Invoice", "jenis": "cash_in"},
    "4-2000": {"nama": "Pembayaran dari Customer", "jenis": "cash_in"},
    "4-3000": {"nama": "Pendapatan Lain-lain", "jenis": "cash_in"},
    "4-4000": {"nama": "Setoran Tunai", "jenis": "cash_in"},
    "4-5000": {"nama": "Transfer Antar Bank (Switching) - Masuk", "jenis": "cash_in"},
}

# ---------------------------------------------------------------------
# 2. LABEL BARU POOL 2 (berbasis kelompok akun di CoA Avolut)
#
# Kenapa kelompok (bukan 226 akun detail)?
#   - Data riil kita baru ~600 baris, tidak cukup untuk belajar 226 kelas.
#   - Di CoA, jenis biaya yang sama muncul dua kali: blok 6.x (biaya produksi) dan 7.1.x
#     (biaya penjualan). Dari TEKS transaksi saja, keduanya tidak bisa dibedakan.
#     Pembagian itu urusan Pool 3 (aturan/konteks). Pool 2 cukup menebak KELOMPOK-nya.
#
# arah: "keluar" = biasanya DB (cash out), "masuk" = biasanya CR (cash in), "dua_arah" = bisa keduanya
# coa : kunci akun induk (Search Key) di CoA.xlsx. Kosong [] = BELUM ADA di CoA (perlu ditanyakan).
# ---------------------------------------------------------------------
LABEL_COA = {
    # ----- ARUS KELUAR -----
    "PAYABLE_VENDOR": {"nama": "Pembayaran ke Supplier/Vendor", "arah": "keluar",
                       "coa": ["2.1.01"]},
    "SALARY":         {"nama": "Gaji, Lembur & THR", "arah": "keluar",
                       "coa": ["6.2.01", "7.1.01"]},
    "EMP_BENEFIT":    {"nama": "Tunjangan Karyawan & BPJS", "arah": "keluar",
                       "coa": ["6.2.02", "7.1.02"]},
    "TRAVEL":         {"nama": "Perjalanan Dinas", "arah": "keluar",
                       "coa": ["6.2.03", "7.1.03"]},
    "TRANSPORT":      {"nama": "Transport & BBM", "arah": "keluar",
                       "coa": ["6.2.04", "7.1.04"]},
    "UTILITIES":      {"nama": "Listrik, Air & Gas", "arah": "keluar",
                       "coa": ["6.2.05", "7.1.05"]},
    "COMMUNICATION":  {"nama": "Telepon, Internet & Pulsa", "arah": "keluar",
                       "coa": ["6.2.06", "7.1.06"]},
    "OFFICE_GENERAL": {"nama": "ATK, Konsumsi & Kebersihan Kantor", "arah": "keluar",
                       "coa": ["6.2.07", "6.2.08", "7.1.07", "7.1.08"]},
    "INSURANCE":      {"nama": "Asuransi (non-BPJS)", "arah": "keluar",
                       "coa": ["6.2.09", "7.1.09"]},
    "RENT":           {"nama": "Sewa", "arah": "keluar",
                       "coa": ["6.2.10", "6.2.11", "6.2.12", "6.2.13", "6.2.14",
                               "7.1.10", "7.1.11", "7.1.12", "7.1.13", "7.1.14"]},
    "REPAIR_MAINT":   {"nama": "Perbaikan & Pemeliharaan", "arah": "keluar",
                       "coa": ["6.2.15", "7.1.15"]},
    "OTHER_EXPENSE":  {"nama": "Biaya Lain-lain (donasi, hadiah, pelatihan, dll)", "arah": "keluar",
                       "coa": ["6.4.01", "7.3.01"]},
    "TAX":            {"nama": "Pajak & Setoran Negara", "arah": "keluar",
                       "coa": ["2.1.04", "2.1.05", "1.1.08"]},
    "BANK_CHARGE":    {"nama": "Biaya Bank (admin, transfer, tolakan)", "arah": "keluar",
                       "coa": ["8.2.00.08"],
                       "catatan": "Terkonfirmasi Avolut (27 Nov 2026): B_EXPENSE / Charge ID 1000013"},

    # ----- ARUS MASUK -----
    "RECEIVABLE_CUSTOMER": {"nama": "Penerimaan dari Customer (Piutang)", "arah": "masuk",
                            "coa": ["1.1.04"]},
    "REVENUE_OTHER":  {"nama": "Pendapatan Jasa/Lain-lain", "arah": "masuk",
                       "coa": ["4.1.01"]},
    "CASH_DEPOSIT":   {"nama": "Setoran Tunai", "arah": "masuk",
                       "coa": ["1.1.1.01"]},

    # ----- DUA ARAH -----
    "LOAN":              {"nama": "Pinjaman & Intercompany", "arah": "dua_arah",
                          "coa": ["2.2.01", "1.1.04.02"]},
    "PETTY_CASH":        {"nama": "Kas Kecil, Uang Muka & Reimburse", "arah": "dua_arah",
                          "coa": ["1.1.1.97", "1.1.09.03"]},
    "INTERNAL_TRANSFER": {"nama": "Transfer Antar Rekening Sendiri", "arah": "dua_arah",
                          "coa": ["1.1.02.98"]},
    "BANK_INTEREST":     {"nama": "Bunga & Pajak Bunga Bank", "arah": "dua_arah",
                          "coa": ["8.2.00.10", "1.1.08.08"],
                          "catatan": "Terkonfirmasi Avolut (27 Nov 2026): CR=8.2.00.10 (1000014), DB=1.1.08.08 (1000015)"},
}

# ---------------------------------------------------------------------
# 2B. PEMETAAN FINAL 21 KATEGORI NLP -> OBJEK ERP iDEMPIERE 13 (AVOLUT, 27 NOV 2026)
# Sandbox: dev-recon.midsuit.com (AD_Org_ID=1000015, BP Default Charge=1000079 SW-INTERNAL)
# C_DocType_ID: 1000008 = AR Receipt (CR), 1000009 = AP Payment (DB)
# ---------------------------------------------------------------------
ERP_CONSTANTS = {
    "client_id": 1000015,
    "org_id": 1000015,
    "role_id": 1000040,
    "currency_idr_id": 303,
    "doctype_ar_receipt": 1000008,
    "doctype_ap_payment": 1000009,
    "bpartner_internal_id": 1000079,  # SW-INTERNAL
    "bank_accounts": {
        "bca": {"id": 1000002, "tender_type": "A", "akun": "1.1.02.02"},
        "mandiri": {"id": 1000003, "tender_type": "A", "akun": "8.2.00.49"},
        "kas": {"id": 1000001, "tender_type": "X", "akun": "8.2.00.49"},
    },
}

ERP_MAPPING_IDEMPIERE = {
    "RECEIVABLE_CUSTOMER": {
        "pola": "customer_invoice",
        "charge_fallback": {"name": "RECEIVABLE_CUSTOMER_UNAPPLIED", "id": 1000009, "akun": "1.1.05.01"},
        "akun_default": "1.1.04",
    },
    "PAYABLE_VENDOR": {
        "pola": "vendor_invoice",
        "charge_fallback": None,
        "akun_default": "2.1.01",
    },
    "INTERNAL_TRANSFER": {
        "pola": "bank_transfer_or_charge",
        "charge_cr": {"name": "INTERNAL_TRANSFER", "id": 1000010, "akun": "1.1.02.98"},
        "charge_db": {"name": "INTERNAL_TRANSFER", "id": 1000010, "akun": "1.1.02.98"},
    },
    "LOAN": {
        "pola": "charge",
        "charge_cr": {"name": "LOAN", "id": 1000011, "akun": "2.2.01.03"},
        "charge_db": {"name": "LOAN_INTERCO_RETURN", "id": 1000012, "akun": "1.1.04.02"},
    },
    "BANK_CHARGE": {
        "pola": "charge",
        "charge_db": {"name": "BANK_CHARGE", "id": 1000013, "akun": "8.2.00.08"},
    },
    "BANK_INTEREST": {
        "pola": "charge",
        "charge_cr": {"name": "BANK_INTEREST", "id": 1000014, "akun": "8.2.00.10"},
        "charge_db": {"name": "BANK_INTEREST_TAX", "id": 1000015, "akun": "1.1.08.08"},
    },
    "TAX": {
        "pola": "charge_tax",
        "charge_db": {"name": "TAX_PPN", "id": 1000016, "akun": "2.1.05.01"},
        "varian": {
            "ppn": {"name": "TAX_PPN", "id": 1000016, "akun": "2.1.05.01"},
            "pph21": {"name": "TAX_PPH21", "id": 1000017, "akun": "2.1.04.01"},
            "pph23": {"name": "TAX_PPH23", "id": 1000018, "akun": "2.1.04.04"},
            "pph4_2": {"name": "TAX_PPH4_2", "id": 1000019, "akun": "2.1.04.06"},
            "pph25": {"name": "TAX_PPH25", "id": 1000020, "akun": "1.1.08.07"},
        },
    },
    "SALARY":         {"pola": "charge", "charge_db": {"name": "SALARY", "id": 1000021, "akun": "7.1.01.01"}},
    "EMP_BENEFIT":    {"pola": "charge", "charge_db": {"name": "EMP_BENEFIT", "id": 1000022, "akun": "7.1.02.01"}},
    "UTILITIES":      {"pola": "charge", "charge_db": {"name": "UTILITIES", "id": 1000023, "akun": "7.1.05.01"}},
    "COMMUNICATION":  {"pola": "charge", "charge_db": {"name": "COMMUNICATION", "id": 1000024, "akun": "7.1.06.01"}},
    "TRANSPORT":      {"pola": "charge", "charge_db": {"name": "TRANSPORT", "id": 1000025, "akun": "7.1.04.01"}},
    "OFFICE_GENERAL": {"pola": "charge", "charge_db": {"name": "OFFICE_GENERAL", "id": 1000026, "akun": "7.1.07.03"}},
    "OTHER_EXPENSE":  {"pola": "charge", "charge_db": {"name": "OTHER_EXPENSE", "id": 1000027, "akun": "7.3.01.08"}},
    "PETTY_CASH": {
        "pola": "petty_cash_or_employee",
        "charge_db": {"name": "PETTY_CASH", "id": 1000028, "akun": "1.1.1.97"},
        "charge_cr": {"name": "PETTY_CASH", "id": 1000028, "akun": "1.1.1.97"},
        "charge_employee": {"name": "EMP_ADVANCE", "id": 1000029, "akun": "1.1.09.03"},
    },
    "REVENUE_OTHER":  {"pola": "charge", "charge_cr": {"name": "REVENUE_OTHER", "id": 1000030, "akun": "4.1.01.08"}},
    "CASH_DEPOSIT": {
        "pola": "bank_transfer_or_charge",
        "charge_cr": {"name": "CASH_DEPOSIT", "id": 1000031, "akun": "1.1.1.99"},
    },
    "TRAVEL":         {"pola": "charge", "charge_db": {"name": "TRAVEL", "id": 1000032, "akun": "7.1.03.01"}},
    "INSURANCE":      {"pola": "charge", "charge_db": {"name": "INSURANCE", "id": 1000033, "akun": "7.1.09.01"}},
    "RENT":           {"pola": "charge_or_vendor", "charge_db": {"name": "RENT", "id": 1000034, "akun": "7.1.10.01"}},
    "REPAIR_MAINT":   {"pola": "charge_or_vendor", "charge_db": {"name": "REPAIR_MAINT", "id": 1000035, "akun": "7.1.15.06"}},
}


def resolve_erp_target(label, jenis, keterangan=""):
    """Menentukan metadata posting ERP iDempiere (C_DocType_ID, C_Charge_ID, akun CoA, pola)."""
    jenis = str(jenis).upper()
    doc_type_id = ERP_CONSTANTS["doctype_ar_receipt"] if jenis == "CR" else ERP_CONSTANTS["doctype_ap_payment"]
    spec = ERP_MAPPING_IDEMPIERE.get(label, {})
    pola = spec.get("pola", "charge")
    ket_low = str(keterangan).lower()

    charge = None
    if label == "TAX":
        varian = spec.get("varian", {})
        if "pph 21" in ket_low or "pph21" in ket_low:
            charge = varian["pph21"]
        elif "pph 23" in ket_low or "pph23" in ket_low:
            charge = varian["pph23"]
        elif "pph 4" in ket_low or "pph4" in ket_low or "final" in ket_low:
            charge = varian["pph4_2"]
        elif "pph 25" in ket_low or "pph25" in ket_low:
            charge = varian["pph25"]
        else:
            charge = varian["ppn"]
    elif label == "PETTY_CASH" and any(k in ket_low for k in ("rembes", "reimburse", "kasbon", "uang muka")):
        charge = spec.get("charge_employee")
    else:
        charge = spec.get("charge_cr" if jenis == "CR" else "charge_db") or spec.get("charge_db") or spec.get("charge_cr") or spec.get("charge_fallback")

    return {
        "pola_posting": pola,
        "c_doctype_id": doc_type_id,
        "c_charge_id": charge["id"] if charge else None,
        "charge_name": charge["name"] if charge else None,
        "akun_coa": charge["akun"] if charge else spec.get("akun_default"),
        "default_bpartner_id": ERP_CONSTANTS["bpartner_internal_id"] if pola not in ("customer_invoice", "vendor_invoice") else None,
    }

LABEL_BELUM_PASTI = "PERLU_REVIEW"   # baris yang aturannya belum bisa memutuskan

# ---------------------------------------------------------------------
# 3. PETA KODE LAMA -> LABEL BARU (untuk memigrasi 337 baris BCA yang sudah kamu label)
# ---------------------------------------------------------------------
MAP_LAMA_KE_BARU = {
    "6-1100": "BANK_CHARGE",
    "6-2200": "UTILITIES",
    "6-2300": "COMMUNICATION",
    "6-3100": "PAYABLE_VENDOR",          # 2 baris "pengurusan elit" = pembayaran ke pihak ketiga
    "6-4000": "SALARY",
    "6-5000": "PAYABLE_VENDOR",
    "6-6000": "EMP_BENEFIT",
    "6-7000": "TAX",
    "6-8000": "BANK_CHARGE",             # biaya tolakan & biaya surat referensi
    "6-9000": "PAYABLE_VENDOR",          # "switching" itu jalur transfer, bukan akun -> ikut arah DB
    "4-1000": "RECEIVABLE_CUSTOMER",
    "4-2000": "RECEIVABLE_CUSTOMER",
    "4-3000": "REVENUE_OTHER",
    "4-4000": "CASH_DEPOSIT",
    "4-5000": "RECEIVABLE_CUSTOMER",     # "switching" masuk = customer bayar lewat jalur switching
}

# ---------------------------------------------------------------------
# 4. PETA NAMA KATEGORI DATA SINTESIS (dataset_sintesis_v1.csv) -> LABEL BARU
# ---------------------------------------------------------------------
MAP_SINTESIS_KE_BARU = {
    "Biaya Administrasi Bank": "BANK_CHARGE",
    "Biaya Listrik": "UTILITIES",
    "Biaya Telepon/Internet": "COMMUNICATION",
    "Biaya Operasional (BBM, dll)": "TRANSPORT",
    "Gaji Karyawan": "SALARY",
    "Pembayaran Vendor/Supplier": "PAYABLE_VENDOR",
    "Pendapatan Penjualan/Invoice": "RECEIVABLE_CUSTOMER",
    "Pembayaran dari Customer": "RECEIVABLE_CUSTOMER",
    "Pendapatan Lain-lain": "REVENUE_OTHER",
}

# ---------------------------------------------------------------------
# 5. PEMILIK REKENING (huruf besar) -> dipakai untuk mendeteksi transfer ke rekening sendiri
# ---------------------------------------------------------------------
PEMILIK_REKENING = {
    "bca": ["DARBE JAYA ABADI", "DARBE INTI NUSANTA"],
    "mandiri": ["SANTOSA JAYA MAKMUR"],
}