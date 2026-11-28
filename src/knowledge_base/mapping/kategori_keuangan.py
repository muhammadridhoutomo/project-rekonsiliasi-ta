KATEGORI = {
    # === KODE COA RIIL MITRA (Avolut / iDempiere) ===
    # Akun lawan (contra account) — sisi bank sudah diketahui (1.1.02.xx)

    # Hutang & Kewajiban
    "2.1.01.01": {"nama": "Trade Payable - 3rd Party", "jenis": "cash_out"},       # Bayar vendor

    # Biaya Produksi (grup 6)
    "6.2.01.01": {"nama": "Salary & Wages-Base Salary", "jenis": "cash_out"},      # Gaji (produksi)
    "6.2.05.01": {"nama": "Utilities-Electricity", "jenis": "cash_out"},           # PLN
    "6.2.05.02": {"nama": "Utilities-Water/Telephone", "jenis": "cash_out"},       # Telepon/Internet
    "6.2.04.01": {"nama": "Transport-Transport.Out", "jenis": "cash_out"},         # BBM, Tol (produksi)

    # Piutang & Aset
    "1.1.04.01": {"nama": "Account Receivable 3rd Party", "jenis": "cash_in"},     # Terima dari customer
    "1.1.1.01":  {"nama": "Cash on Hand:IDR", "jenis": "cash_in"},                # Setoran tunai
    "1.1.02.98": {"nama": "Cross Account Bank", "jenis": "cash_in"},               # Transfer antar rekening

    # Akun yang belum ada di CoA mitra (menunggu konfirmasi Pak Depta)
    "PERLU_REVIEW": {"nama": "Akun Belum Tersedia di CoA Mitra", "jenis": "unknown"},

    # === KODE LAMA (backward compatibility untuk evaluasi data lama) ===
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
    "4-1000": {"nama": "Pendapatan Penjualan/Invoice", "jenis": "cash_in"},
    "4-2000": {"nama": "Pembayaran dari Customer", "jenis": "cash_in"},
    "4-3000": {"nama": "Pendapatan Lain-lain", "jenis": "cash_in"},
    "4-4000": {"nama": "Setoran Tunai", "jenis": "cash_in"},
    "4-5000": {"nama": "Transfer Antar Bank (Switching) - Masuk", "jenis": "cash_in"},
}
