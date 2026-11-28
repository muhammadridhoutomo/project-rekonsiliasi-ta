import re

# ==============================================================================
# KAMUS & LOGIKA RESOLUSI REKANAN (VENDOR & CUSTOMER RESOLVER)
# Modul ini bertugas mengekstrak nama pihak lawan transaksi dari keterangan bank
# dan memetakannya ke akun Customer (4-2000 / 1.1.04.01) atau Vendor (6-5000 / 2.1.01.01).
# ==============================================================================

# Kata-kata operasional/keterangan yang bukan nama rekanan
KATA_NOISE = {
    'AYAM', 'KARKAS', 'DAGING', 'AYM', 'BELI', 'BAYAR', 'BYR', 'AY',
    'WHOLE', 'HIDUP', 'HDP', 'HD', 'DLL', 'MDM', 'MEATS', 'BLD', 'BLP',
    'INV', 'INVOICE', 'PEMBAYARAN', 'PEMBY', 'PEMINDAHBUKUAN', 'PEMAN',
    'DJA', 'ELIT', 'JASA', 'SEWA', 'CS', 'TEMPAT', 'KALI',
    'PENGISIAN', 'PENGURUSAN', 'PENG', 'SALDO', 'MIN', 'MINIM',
    'KBB', 'KE', 'VIA', 'RTGS', 'LLG', 'REF', 'NO', 'PPU',
    'TANGGAL', 'TGL', 'PT', 'BANK', 'TXN', 'BIAYA', 'OICE',
    'DR', 'DARI', 'KEPADA', 'TRANSFER', 'TRSF', 'E-BANKING'
}

# Prefix umum pada mutasi rekening bank BCA/Mandiri/dsb
PREFIX_BANK = [
    'TRSF E-BANKING CR', 'TRSF E-BANKING DB', 'TRSF E-BANKING',
    'BYR VIA E-BANKING', 'SWITCHING TRANSFER DR', 'SWITCHING TRANSFER KE',
    'SWITCHING TRANSFER', 'SWITCHING KE', 'SWITCHING DR', 'SWITCHING',
    'BI-FAST TRANSFER', 'BI-FAST', 'BIF', 'SETORAN TUNAI', 'TRANSFER VIA LLG'
]

# Rekening internal / afiliasi grup perusahaan
ENTITAS_INTERNAL = {
    'DARBE JAYA ABADI', 'DARBE INTI NUSANTA', 'DARBE INTI NUSANTARA',
    'DARBE AMERTHA JAYA', 'DARBE ALKAFIE JAYA ABADI'
}

# Master Partner yang sudah teridentifikasi (bisa terus diperluas)
MASTER_CUSTOMERS = {
    'AMERTHA JAYA', 'PANCA BERSAUDARA', 'SERA FOOD INDONESI', 'PRANAFOOD',
    'HARMONIS SENTRA', 'KELANA MAKMUR', 'DANUREJO RAYA FOOD', 'RIFALDI',
    'KETUT MAHAYANI', 'LUH WIRANTINI', 'PUTU SADNYANA', 'MAJU MAPAN BAHAGIA'
}

MASTER_VENDORS = {
    'BAREKA LINTAS INDO', 'BAREKA LINTAS', 'SENTOT PRABOWO', 'CIOMAS ADISATWA',
    'CIOMAS', 'BINA USAHA SANTOSA', 'BINA USAHA SANT', 'RAKHMAD WAHYU',
    'GEDE ARYA WIRATMA', 'TIBAN', 'GUNTUR CENTRA', 'HARYANTO', 'DIDIK HARYANTO',
    'MADE KARMAYASA', 'MADE RUMADIA', 'WAYAN SUWEDEN', 'I WAYAN SUWEDEN',
    'HAMIDAH', 'DANANJAYA', 'ERWIN SOFIANI', 'GEDE RENTADA', 'GEDE JULIANA',
    'BAGAS PUTRA', 'DUTA SELARAS ABADI', 'RUMIATI ALFIYAH'
}

# Penanda jalur transfer antar pihak. Aturan default CR/DB hanya berlaku jika salah satu muncul,
# supaya teks tanpa konteks transfer (mis. 'REF TXN ANOMALI') tidak dipaksa jadi Vendor/Customer.
# 'TRANSFER' sengaja tidak dimasukkan karena juga muncul di biaya bank ("BIAYA TRANSFER SME").
JALUR_TRANSFER = ['TRSF', 'SWITCHING', 'BI-FAST', 'BIFAST', 'BIF', 'LLG', 'RTGS', 'KBB', 'KLIRING']

def _mengandung(frasa, teks):
    """True jika frasa muncul sebagai kata/frasa utuh di teks (keduanya huruf besar)."""
    return re.search(r'(?<![A-Z0-9])' + re.escape(frasa) + r'(?![A-Z0-9])', teks) is not None

def _ada_jalur_transfer(keterangan):
    k = str(keterangan).upper()
    return any(_mengandung(jalur, k) for jalur in JALUR_TRANSFER)

def _is_kode_atau_angka(token):
    """Mendeteksi apakah token adalah kode referensi acak atau murni angka."""
    # Murni angka atau format desimal
    if re.fullmatch(r'[\d.,/-]+', token):
        return True
    # Kode campuran alfanumerik (mis. 5XSK, NWWV, 0080017PT)
    if re.fullmatch(r'[A-Z0-9]{4,12}', token) and re.search(r'\d', token) and re.search(r'[A-Z]', token):
        return True
    # Fragmen sangat pendek (<= 2 huruf) kecuali singkatan nama umum
    if len(token) <= 2 and token not in {'PT', 'CV'}:
        return True
    return False

def ekstrak_nama_rekanan(keterangan):
    """
    Membersihkan teks mutasi untuk mengambil nama vendor/customer.
    Contoh: 'TRSF E-BANKING BAREKA LINTAS INDO' -> 'BAREKA LINTAS INDO'
    """
    if not keterangan or not isinstance(keterangan, str):
        return ""

    k = keterangan.upper()
    for prefix in PREFIX_BANK:
        k = k.replace(prefix, ' ')

    # Buang karakter selain huruf, angka, titik, dan spasi
    k = re.sub(r'[^\w\s.]', ' ', k)
    tokens = k.split()

    hasil = [t for t in tokens if t not in KATA_NOISE and not _is_kode_atau_angka(t)]
    return ' '.join(hasil).strip()

def resolve_rekanan(keterangan, jenis=None):
    """
    Mencocokkan nama rekanan dengan Master Data atau aturan bisnis transaksi.
    
    Return:
    dict berisi { 'nama_pihak', 'kode_akun', 'nama_kategori', 'status', 'metode' }
    atau None jika tidak dapat diidentifikasi sama sekali.
    """
    nama_pihak = ekstrak_nama_rekanan(keterangan)
    j = str(jenis).strip().upper() if jenis else None

    if not nama_pihak:
        return None

    # 1. Cek apakah ini entitas internal (Grup Perusahaan) -> Switching Antar Rekening
    for entitas in ENTITAS_INTERNAL:
        if _mengandung(entitas, nama_pihak):
            return {
                'nama_pihak': nama_pihak,
                'kode_akun': '1.1.02.98',
                'nama_kategori': 'Cross Account Bank',
                'status': 'KB_TEREALISASI',
                'metode': 'Master Entitas Internal'
            }

    # 2. Cek apakah cocok dengan Master Customers yang sudah terdaftar
    for cust in MASTER_CUSTOMERS:
        if _mengandung(cust, nama_pihak):
            # Jika jenis mutasi DB (uang keluar), perlakuan akuntansi adalah pembayaran vendor / kontraktor / rekanan
            if j == "DB":
                return {
                    'nama_pihak': nama_pihak,
                    'kode_akun': '2.1.01.01',
                    'nama_kategori': 'Trade Payable-Local',
                    'status': 'KB_TEREALISASI',
                    'metode': f'Master Partner DB ({cust} -> Vendor)'
                }
            return {
                'nama_pihak': nama_pihak,
                'kode_akun': '1.1.04.01',
                'nama_kategori': 'Trade Receivable-Local',
                'status': 'KB_TEREALISASI',
                'metode': f'Master Customer ({cust})'
            }

    # 3. Cek apakah cocok dengan Master Vendors yang sudah terdaftar
    for vendor in MASTER_VENDORS:
        if _mengandung(vendor, nama_pihak):
            return {
                'nama_pihak': nama_pihak,
                'kode_akun': '2.1.01.01',
                'nama_kategori': 'Trade Payable-Local',
                'status': 'KB_TEREALISASI',
                'metode': f'Master Vendor ({vendor})'
            }

    # 4. Aturan Default Bisnis: Jika ada nama pihak yang jelas, tentukan berdasarkan jenis mutasi (CR/DB)
    # Di perbankan, uang masuk (CR) dari pihak ketiga umumnya piutang customer, sedangkan uang keluar (DB) adalah vendor.
    # Hanya berlaku untuk transaksi transfer; selain itu dikembalikan None agar menuju Manual Review.
    if _ada_jalur_transfer(keterangan):
        if j == "CR":
            return {
                'nama_pihak': nama_pihak,
                'kode_akun': '1.1.04.01',
                'nama_kategori': 'Trade Receivable-Local',
                'status': 'KB_TEREALISASI',
                'metode': 'Aturan Rekanan Bisnis (CR -> Customer)'
            }
        elif j == "DB":
            return {
                'nama_pihak': nama_pihak,
                'kode_akun': '2.1.01.01',
                'nama_kategori': 'Trade Payable-Local',
                'status': 'KB_TEREALISASI',
                'metode': 'Aturan Rekanan Bisnis (DB -> Vendor)'
            }

    return None

if __name__ == '__main__':
    print("=== TEST REKANAN RESOLVER ===")
    test_cases = [
        ("TRSF E-BANKING CR 0707/FTSCY/WS95051 16561371.00 PUTU SADNYANA", "CR"),
        ("TRSF E-BANKING DB 0707/FTFVA/WS95051 89000/BPJS TK", "DB"),
        ("TRSF E-BANKING CR 1007/FTSCY/WS95051 15546634.00 PRANAFOOD", "CR"),
        ("TRSF E-BANKING CIOMAS ADISATWA", "DB"),
        ("SWITCHING TRANSFER KE 009 SENTOT PRABOWO", "DB"),
        ("TRSF E-BANKING bayar ayam darbe 3.384 x 19.200 ALKAFIE JAYA ABADI", "DB"),
        ("TRSF E-BANKING MAJU MAPAN BAHAGIA", "DB"),
        ("TRSF E-BANKING MAJU MAPAN BAHAGIA", "CR"),
        ("TRSF E-BANKING M. FAUZI", "DB"),
        ("REF TXN 99823 ANOMALI", "DB")
    ]

    for teks, jenis in test_cases:
        res = resolve_rekanan(teks, jenis=jenis)
        if res:
            print(f"[{jenis}] {teks[:45]:<45} -> {res['kode_akun']} ({res['nama_pihak']}) via {res['metode']}")
        else:
            print(f"[{jenis}] {teks[:45]:<45} -> Tidak Teridentifikasi (Lanjut ke NLP / Manual Review)")
