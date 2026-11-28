"""
ERP API Client — adapter layer antara KB Engine dan backend ERP.

Mode operasi (otomatis berdasarkan .env):
  - LIVE: Koneksi ke iDempiere sandbox (ERP_BASE_URL terisi) → query real
  - MOCK: Fallback data statis untuk testing offline
"""

import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

try:
    from knowledge_base.mapping.kategori_keuangan import KATEGORI
    from knowledge_base.mapping.rekanan_resolver import MASTER_CUSTOMERS, MASTER_VENDORS
except ImportError:
    try:
        from knowledge_base.kategori_keuangan import KATEGORI
        from knowledge_base.rekanan_resolver import MASTER_CUSTOMERS, MASTER_VENDORS
    except ImportError:
        from kategori_keuangan import KATEGORI
        from rekanan_resolver import MASTER_CUSTOMERS, MASTER_VENDORS

try:
    from knowledge_base.erp.erp_idempiere import (
        get_idempiere_client, CHARGE_MAP, CHARGE_VARIANTS,
        CHARGE_COA_MAP, BANK_ACCOUNT_MAP,
    )
except ImportError:
    try:
        from knowledge_base.erp_idempiere import (
            get_idempiere_client, CHARGE_MAP, CHARGE_VARIANTS,
            CHARGE_COA_MAP, BANK_ACCOUNT_MAP,
        )
    except ImportError:
        try:
            from erp_idempiere import (
                get_idempiere_client, CHARGE_MAP, CHARGE_VARIANTS,
                CHARGE_COA_MAP, BANK_ACCOUNT_MAP,
            )
        except ImportError:
            get_idempiere_client = None
            CHARGE_MAP = {}
            CHARGE_VARIANTS = {}
            CHARGE_COA_MAP = {}
            BANK_ACCOUNT_MAP = {}

# Mock invoice data untuk testing offline
MOCK_INVOICES = [
    {"invoice_no": "INV-2023-001", "partner_name": "CIOMAS ADISATWA", "partner_type": "VENDOR",
     "amount": 580075045.0, "due_date": "2023-07-31", "status": "UNPAID", "kode_akun": "2.1.01.01"},
    {"invoice_no": "INV-2023-002", "partner_name": "AMERTHA JAYA", "partner_type": "CUSTOMER",
     "amount": 595075045.0, "due_date": "2023-07-30", "status": "UNPAID", "kode_akun": "1.1.04.01"},
    {"invoice_no": "INV-2023-003", "partner_name": "BAREKA LINTAS INDO", "partner_type": "VENDOR",
     "amount": 138500000.0, "due_date": "2023-07-28", "status": "UNPAID", "kode_akun": "2.1.01.01"},
    {"invoice_no": "INV-2023-004", "partner_name": "PANCA BERSAUDARA", "partner_type": "CUSTOMER",
     "amount": 50000000.0, "due_date": "2023-07-25", "status": "UNPAID", "kode_akun": "1.1.04.01"},
    {"invoice_no": "INV-2023-005", "partner_name": "SENTOT PRABOWO", "partner_type": "VENDOR",
     "amount": 15000000.0, "due_date": "2023-07-20", "status": "UNPAID", "kode_akun": "2.1.01.01"},
]


class PerusahaanAPIClient:
    """
    Adapter ERP: otomatis pakai iDempiere live jika ERP_BASE_URL dikonfigurasi,
    fallback ke mock data jika tidak.
    """

    def __init__(self):
        self._idempiere = None
        self._live = False

        if get_idempiere_client:
            self._idempiere = get_idempiere_client()
            self._live = self._idempiere.is_configured

        if self._live:
            logger.info(f"ERP Client: LIVE mode ({self._idempiere.base_url})")
        else:
            logger.info("ERP Client: MOCK mode (ERP_BASE_URL tidak dikonfigurasi)")

    @property
    def is_live(self) -> bool:
        return self._live

    @property
    def charge_map(self) -> Dict[str, int]:
        return CHARGE_MAP

    @property
    def bank_account_map(self) -> Dict[str, int]:
        return BANK_ACCOUNT_MAP

    # --------------------------------------------------------------------------
    # CHART OF ACCOUNTS
    # --------------------------------------------------------------------------
    def get_chart_of_accounts(self) -> Dict:
        if self._live:
            try:
                charges = self._idempiere.get_charges()
                return {c.get("Name", ""): c for c in charges}
            except Exception as e:
                logger.warning(f"Gagal ambil CoA live ({e}), fallback mock")
        return KATEGORI

    # --------------------------------------------------------------------------
    # MASTER PARTNER
    # --------------------------------------------------------------------------
    def get_partners(self, name_contains: Optional[str] = None) -> Dict[str, List]:
        if self._live:
            try:
                bps = self._idempiere.get_business_partners(name_contains=name_contains)
                customers = [bp for bp in bps if bp.get("IsCustomer")]
                vendors = [bp for bp in bps if bp.get("IsVendor")]
                return {"customers": customers, "vendors": vendors}
            except Exception as e:
                logger.warning(f"Gagal ambil partners live ({e}), fallback mock")
        return {
            "customers": sorted(list(MASTER_CUSTOMERS)),
            "vendors": sorted(list(MASTER_VENDORS)),
        }

    # --------------------------------------------------------------------------
    # INVOICE MATCHING
    # --------------------------------------------------------------------------
    def get_unpaid_invoices(self, bp_name: Optional[str] = None) -> List[Dict]:
        if self._live:
            try:
                return self._idempiere.get_open_invoices(bp_name=bp_name)
            except Exception as e:
                logger.warning(f"Gagal ambil invoices live ({e}), fallback mock")
        return MOCK_INVOICES

    def match_invoice(
        self,
        keterangan: str,
        nominal: Optional[float] = None,
        nama_rekanan: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Mencocokkan transaksi bank dengan invoice ERP.
        Live mode → query iDempiere langsung.
        Mock mode → data statis.
        """
        if self._live:
            try:
                return self._idempiere.match_invoice(keterangan, nominal, nama_rekanan)
            except Exception as e:
                logger.warning(f"Match invoice live gagal ({e}), fallback mock")

        # Mock matching
        invoices = MOCK_INVOICES
        k_upper = str(keterangan).upper()

        nom_float = None
        if nominal is not None:
            try:
                nom_float = float(str(nominal).replace(",", "").replace("Rp", "").strip())
            except (ValueError, TypeError):
                nom_float = None

        for inv in invoices:
            if inv["invoice_no"].upper() in k_upper:
                return {
                    "matched": True,
                    "kriteria": "Nomor Invoice Teridentifikasi",
                    "invoice_no": inv["invoice_no"],
                    "partner_name": inv["partner_name"],
                    "kode_akun": inv["kode_akun"],
                    "status_rekonsiliasi": "RECONCILED",
                    "selisih_nominal": abs(nom_float - float(inv["amount"])) if nom_float else 0.0,
                }

        if nom_float is not None and nama_rekanan:
            rek_upper = str(nama_rekanan).upper()
            for inv in invoices:
                p_name = inv["partner_name"].upper()
                if p_name in rek_upper or rek_upper in p_name:
                    if abs(nom_float - float(inv["amount"])) < 1.0:
                        return {
                            "matched": True,
                            "kriteria": "Nama Rekanan & Nominal Tepat",
                            "invoice_no": inv["invoice_no"],
                            "partner_name": inv["partner_name"],
                            "kode_akun": inv["kode_akun"],
                            "status_rekonsiliasi": "RECONCILED",
                            "selisih_nominal": 0.0,
                        }

        return None

    # --------------------------------------------------------------------------
    # POST PAYMENT (hanya live mode)
    # --------------------------------------------------------------------------
    def post_payment(self, **kwargs) -> Optional[Dict]:
        if not self._live:
            logger.warning("post_payment dipanggil dalam mock mode — tidak ada efek")
            return None
        return self._idempiere.post_payment(**kwargs)

    def bank_transfer(self, **kwargs) -> Optional[Dict]:
        if not self._live:
            logger.warning("bank_transfer dipanggil dalam mock mode — tidak ada efek")
            return None
        return self._idempiere.bank_transfer(**kwargs)

    def void_payment(self, payment_id: int) -> Optional[Dict]:
        if not self._live:
            return None
        return self._idempiere.void_payment(payment_id)


# Singleton global
erp_client = PerusahaanAPIClient()

if __name__ == "__main__":
    print("=== PENGUJIAN ERP API CLIENT ===")
    print(f"Mode: {'LIVE' if erp_client.is_live else 'MOCK'}")

    print(f"\nCharge Map ({len(CHARGE_MAP)} kategori):")
    for label, cid in sorted(CHARGE_MAP.items()):
        print(f"  {label:25s} -> C_Charge_ID {cid}")

    print(f"\nBank Account Map:")
    for bank, aid in BANK_ACCOUNT_MAP.items():
        print(f"  {bank:10s} -> C_BankAccount_ID {aid}")

    print("\nUji Invoice Matching:")
    hasil = erp_client.match_invoice(
        keterangan="TRSF E-BANKING INV-2023-001 CIOMAS ADISATWA",
        nominal=580075045.0,
        nama_rekanan="CIOMAS ADISATWA",
    )
    if hasil:
        print(f"  Match: {hasil['invoice_no']} - {hasil['partner_name']} ({hasil['kriteria']})")
    else:
        print("  Tidak ditemukan")
