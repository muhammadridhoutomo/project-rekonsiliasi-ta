import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
COA_PATH = BASE_DIR / "data" / "CoA.xlsx"

# ---------------------------------------------------------------------------
# Mapping kode placeholder lama → kode CoA riil mitra (Avolut / iDempiere)
#
# Setiap baris bank adalah jurnal dua sisi: sisi bank sudah diketahui (1.1.02.xx),
# KB menentukan akun LAWAN (contra account).
#   - Uang masuk dari customer  → kredit Piutang Dagang 1.1.04.01, bukan revenue
#   - Uang keluar ke vendor     → debit Hutang Dagang 2.1.01.01, bukan expense
#   - Transfer antar rekening   → 1.1.02.98 (Cross Account Bank)
#
# Akun yang belum ada di CoA mitra diberi tanda PERLU_REVIEW.
# ---------------------------------------------------------------------------
MAPPING_LAMA_KE_COA = {
    # Pajak — Tax Payable summary (2.1.05) ada, tapi posting hanya VAT-Out (2.1.05.01).
    # Setoran pajak PPh/PPN umum belum punya akun posting spesifik.
    "6-7000": "2.1.05.01",    # VAT Out (pajak/setoran negara)

    # BPJS → Employee Benefit
    "6-6000": "6.2.02.01",    # Employee Benefit (BPJS Ketenagakerjaan/Kesehatan)

    # Operasional — utilitas & gaji
    "6-2200": "6.2.05.01",    # Utilities-Electricity (PLN)
    "6-2300": "6.2.05.02",    # Utilities-Water/Telephone (Telepon/Internet)
    # Gaji: 6.2.01.01 (produksi) vs 7.1.01.01 (sales/marketing). Default produksi.
    "6-4000": "6.2.01.01",    # Salary & Wages-Base Salary (produksi)
    # BBM/Tol: 6.2.04.01 (transport produksi) vs 7.1.04.01 (transport sales). Default produksi.
    "6-3100": "6.2.04.01",    # Transport-Transport.Out (produksi)

    # Perbankan — tidak ada akun biaya bank, bunga, atau tolakan di CoA mitra
    "6-1100": "8.2.00.08",    # Bank Charge (biaya admin bank)
    "6-8000": "8.2.00.08",    # Bank Charge (biaya tolakan)
    "4-3000": "8.2.00.10",    # Bank Interest (bunga bank/jasa giro)

    # Vendor & Customer (contra account / akun lawan)
    "6-5000": "2.1.01.01",    # Trade Payable - 3rd Party (bayar vendor)
    "4-2000": "1.1.04.01",    # Account Receivable 3rd Party (terima dari customer)
    "4-1000": "1.1.04.01",    # Pendapatan Penjualan — piutang dilunasi

    # Transfer antar rekening sendiri
    "6-9000": "1.1.02.98",    # Cross Account Bank (switching keluar)
    "4-5000": "1.1.02.98",    # Cross Account Bank (switching masuk)

    # Setoran tunai — Cash on Hand di CoA: 1.1.1.01 (bukan 1.1.01.01, pola kode berbeda)
    "4-4000": "1.1.1.01",     # Cash on Hand:IDR
}

# ---------------------------------------------------------------------------
# Mapping label baru Pool 2 (NLP berbasis CoA) -> Kode CoA riil spesifik
# ---------------------------------------------------------------------------
MAPPING_LABEL_NLP_KE_COA = {
    "SALARY": "7.1.01.01",              # Salary & Wages (Operating Expenses)
    "RECEIVABLE_CUSTOMER": "1.1.04.01",  # Account Receivable 3rd Party (invoice match)
    "PAYABLE_VENDOR": "2.1.01.01",       # Trade Payable - 3rd Party (invoice match)
    "UTILITIES": "7.1.05.01",           # Utilities (Operating Expenses)
    "COMMUNICATION": "7.1.06.01",       # Communication (Operating Expenses)
    "TRANSPORT": "7.1.04.01",           # Transport (Operating Expenses)
    "INTERNAL_TRANSFER": "1.1.02.98",   # Cross Account Bank
    "CASH_DEPOSIT": "1.1.1.99",         # Cash Deposit (via charge)
    "RENT": "7.1.10.01",               # Rent (Operating Expenses)
    "LOAN": "2.2.01.03",               # Long Term Loan
    "PETTY_CASH": "1.1.1.97",           # Petty Cash
    "REVENUE_OTHER": "4.1.01.08",       # Other Revenue
    "OFFICE_GENERAL": "7.1.07.03",      # Office Supplies (Operating Expenses)
    "REPAIR_MAINT": "7.1.15.06",        # Repair & Maintenance (Operating Expenses)
    "OTHER_EXPENSE": "7.3.01.08",       # Other Expenses
    "TRAVEL": "7.1.03.01",             # Travel Expense (Operating Expenses)
    "INSURANCE": "7.1.09.01",          # Insurance (Operating Expenses)
    "TAX": "2.1.05.01",                # VAT Out (PPN Keluaran)
    "BANK_CHARGE": "8.2.00.08",        # Bank Charge
    "BANK_INTEREST": "8.2.00.10",      # Bank Interest
    "EMP_BENEFIT": "7.1.02.01",        # Employee Benefit (Operating Expenses)
}

# Akun bank per institusi (sisi bank dari jurnal)
AKUN_BANK = {
    "BCA":     "1.1.02.02",
    "MANDIRI": "1.1.02.01",
    "BNI":     "1.1.02.03",
    "BRI":     "1.1.02.04",
}


def load_coa(path=None):
    """
    Membaca Chart of Accounts dari file Excel mitra.
    Mengembalikan DataFrame dengan kolom: kode, nama, summary_level, account_type.
    Semua kode dibaca sebagai string agar format bertitik tidak rusak.
    """
    p = Path(path) if path else COA_PATH
    if not p.exists():
        raise FileNotFoundError(f"File CoA tidak ditemukan: {p}")

    df = pd.read_excel(p, dtype=str)
    df.columns = df.columns.str.strip()

    col_map = {
        "Search Key": "kode",
        "Name": "nama",
        "Summary Level": "summary_level",
        "Account Type": "account_type",
    }
    df = df.rename(columns=col_map)

    df["kode"] = df["kode"].str.strip()
    df["nama"] = df["nama"].str.strip()
    df["is_posting"] = df["summary_level"].str.strip().str.upper().isin(["NO", "N", "FALSE", "0"])

    return df


def _build_lookup(df):
    """Dict kode → {nama, account_type, is_posting}."""
    lookup = {}
    for _, row in df.iterrows():
        lookup[row["kode"]] = {
            "nama": row["nama"],
            "account_type": row.get("account_type", ""),
            "is_posting": row["is_posting"],
        }
    return lookup


_coa_cache = {}

def get_coa_lookup(path=None):
    """Mengembalikan dict kode→info, di-cache setelah load pertama."""
    key = str(path or COA_PATH)
    if key not in _coa_cache:
        df = load_coa(path)
        _coa_cache[key] = _build_lookup(df)
    return _coa_cache[key]


def coa_nama(kode, path=None):
    """Mengembalikan nama akun untuk kode CoA tertentu, atau None."""
    lookup = get_coa_lookup(path)
    info = lookup.get(kode)
    return info["nama"] if info else None


def is_posting_account(kode, path=None):
    """True jika kode adalah akun posting (bukan summary)."""
    lookup = get_coa_lookup(path)
    info = lookup.get(kode)
    return info["is_posting"] if info else False


def get_parent_kode(kode):
    """
    Mengembalikan kode akun induk berdasarkan hierarki titik.
    Contoh: '6.2.05.01' → '6.2.05', '6.2.05' → '6.2', '6' → None.
    """
    parts = kode.rsplit(".", 1)
    return parts[0] if len(parts) > 1 else None


def konversi_kode(kode_lama):
    """
    Mengonversi kode placeholder lama atau label baru NLP ke kode CoA riil mitra.
    Return dict {kode_coa, nama_coa, status}.
    """
    if kode_lama in MAPPING_LABEL_NLP_KE_COA:
        kode_baru = MAPPING_LABEL_NLP_KE_COA[kode_lama]
    else:
        kode_baru = MAPPING_LAMA_KE_COA.get(kode_lama)

    if kode_baru is None:
        return {
            "kode_coa": kode_lama,
            "nama_coa": "AKUN_BELUM_TERDAFTAR",
            "status": "tidak_terdaftar",
        }

    if kode_baru == "PERLU_REVIEW":
        return {
            "kode_coa": "PERLU_REVIEW",
            "nama_coa": "Akun belum tersedia di CoA mitra",
            "status": "perlu_review",
        }

    nama = coa_nama(kode_baru) if COA_PATH.exists() else kode_baru
    return {
        "kode_coa": kode_baru,
        "nama_coa": nama or kode_baru,
        "status": "terdaftar",
    }


if __name__ == "__main__":
    print("=== CEK MODUL COA ===\n")

    if COA_PATH.exists():
        df = load_coa()
        posting = df[df["is_posting"]]
        summary = df[~df["is_posting"]]
        print(f"Total akun     : {len(df)}")
        print(f"  Posting      : {len(posting)}")
        print(f"  Summary      : {len(summary)}")
        print(f"\nContoh 5 akun posting pertama:")
        for _, r in posting.head().iterrows():
            print(f"  {r['kode']:15s} {r['nama']}")
    else:
        print(f"File CoA tidak ditemukan di {COA_PATH}")
        print("Menggunakan mapping statis saja.\n")

    print("\n=== KONVERSI KODE LAMA -> COA RIIL ===\n")
    for kode_lama in MAPPING_LAMA_KE_COA:
        hasil = konversi_kode(kode_lama)
        print(f"  {kode_lama:8s} -> {hasil['kode_coa']:15s} {hasil['nama_coa']} [{hasil['status']}]")
