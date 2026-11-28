"""
ERP iDempiere REST API Client — koneksi ke sandbox Avolut (dev-recon.midsuit.com).

Modul ini menangani:
  - Autentikasi Bearer token dengan auto-refresh
  - Query Business Partner, Open Invoice, Bank Account, Charge
  - Posting Payment (AR Receipt / AP Payment) dengan doc-action CO
  - Bank Transfer antar rekening
  - Void payment
"""

import os
import time
import logging
from typing import Optional, Dict, List, Any

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping 21 kategori NLP → C_Charge_ID di iDempiere sandbox
# Sumber: Tanggapan_API_ERP_SIREKON.pdf halaman 2-3
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Mapping 21 kategori NLP → C_Charge_ID di iDempiere sandbox
# Sumber: Tanggapan_API_ERP_SIREKON.pdf halaman 2-3 (tabel bagian 3)
#
# Catatan: beberapa kategori punya >1 charge (sub-varian).
#   CHARGE_MAP = charge utama per kategori NLP
#   CHARGE_VARIANTS = charge tambahan untuk kasus khusus
# ---------------------------------------------------------------------------
CHARGE_MAP: Dict[str, int] = {
    "RECEIVABLE_CUSTOMER":  1000009,   # RECEIVABLE_CUSTOMER_UNAPPLIED / 1.1.05.01 (tanpa invoice match)
    "INTERNAL_TRANSFER":    1000010,   # 1.1.02.98 Cross Account Bank
    "LOAN":                 1000011,   # 2.2.01.03
    "BANK_CHARGE":          1000013,   # 8.2.00.08
    "BANK_INTEREST":        1000014,   # 8.2.00.10 (CR: pendapatan bunga)
    "TAX":                  1000016,   # TAX_PPN / 2.1.05.01
    "SALARY":               1000021,   # 7.1.01.01
    "EMP_BENEFIT":          1000022,   # 7.1.02.01
    "UTILITIES":            1000023,   # 7.1.05.01
    "COMMUNICATION":        1000024,   # 7.1.06.01
    "TRANSPORT":            1000025,   # 7.1.04.01
    "OFFICE_GENERAL":       1000026,   # 7.1.07.03
    "OTHER_EXPENSE":        1000027,   # 7.3.01.08
    "PETTY_CASH":           1000028,   # 1.1.1.97
    "REVENUE_OTHER":        1000030,   # 4.1.01.08
    "CASH_DEPOSIT":         1000031,   # 1.1.1.99
    "TRAVEL":               1000032,   # 7.1.03.01
    "INSURANCE":            1000033,   # 7.1.09.01
    "RENT":                 1000034,   # 7.1.10.01
    "REPAIR_MAINT":         1000035,   # 7.1.15.06
    # PAYABLE_VENDOR tidak pakai charge — selalu invoice-based
}

# Charge varian untuk kasus khusus (sub-tipe dari kategori utama)
CHARGE_VARIANTS: Dict[str, Dict[str, int]] = {
    "LOAN": {
        "LOAN_INTERCO_RETURN": 1000012,  # 1.1.04.02 (pengembalian pinjaman intercompany)
    },
    "BANK_INTEREST": {
        "BANK_INTEREST_TAX": 1000015,    # 1.1.08.08 (PPh 4(2) atas bunga, DB)
    },
    "TAX": {
        "TAX_PPN":   1000016,   # 2.1.05.01
        "TAX_PPH21": 1000017,   # 2.1.04.01
        "TAX_PPH23": 1000018,   # 2.1.04.04
        "TAX_PPH4_2": 1000019,  # 2.1.04.06
        "TAX_PPH25": 1000020,   # 1.1.08.07
    },
    "PETTY_CASH": {
        "EMP_ADVANCE": 1000029,  # 1.1.09.03 (uang muka karyawan, BP = karyawan)
    },
}

# Mapping kategori NLP → kode akun CoA yang benar (dari charge di ERP)
CHARGE_COA_MAP: Dict[str, str] = {
    "RECEIVABLE_CUSTOMER":  "1.1.05.01",   # Unapplied; invoice → 1.1.04.01
    "PAYABLE_VENDOR":       "2.1.01.01",   # Trade Payable (invoice-based)
    "INTERNAL_TRANSFER":    "1.1.02.98",
    "LOAN":                 "2.2.01.03",
    "BANK_CHARGE":          "8.2.00.08",
    "BANK_INTEREST":        "8.2.00.10",
    "TAX":                  "2.1.05.01",   # PPN (default)
    "SALARY":               "7.1.01.01",
    "EMP_BENEFIT":          "7.1.02.01",
    "UTILITIES":            "7.1.05.01",
    "COMMUNICATION":        "7.1.06.01",
    "TRANSPORT":            "7.1.04.01",
    "OFFICE_GENERAL":       "7.1.07.03",
    "OTHER_EXPENSE":        "7.3.01.08",
    "PETTY_CASH":           "1.1.1.97",
    "REVENUE_OTHER":        "4.1.01.08",
    "CASH_DEPOSIT":         "1.1.1.99",
    "TRAVEL":               "7.1.03.01",
    "INSURANCE":            "7.1.09.01",
    "RENT":                 "7.1.10.01",
    "REPAIR_MAINT":         "7.1.15.06",
}

# Mapping nama bank → C_BankAccount_ID di sandbox
BANK_ACCOUNT_MAP: Dict[str, int] = {
    "BCA":     1000002,
    "MANDIRI": 1000003,
    "KAS":     1000001,
}

# DocType IDs
DOCTYPE_AR_RECEIPT = 1000008   # Incoming (penerimaan)
DOCTYPE_AP_PAYMENT = 1000009   # Outgoing (pembayaran)

# Business Partner default untuk transaksi charge tanpa lawan spesifik
BP_SW_INTERNAL = 1000079


class IDempiereClient:
    """
    REST API client untuk iDempiere ERP sandbox Avolut.

    Autentikasi otomatis: token di-refresh saat expired (~1 jam).
    Semua request menyertakan User-Agent: sirekon/1.0 (Cloudflare requirement).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[int] = None,
        role_id: Optional[int] = None,
        timeout: int = 15,
    ):
        self.base_url = (base_url or os.getenv("ERP_BASE_URL", "")).rstrip("/")
        self._username = username or os.getenv("ERP_USERNAME", "")
        self._password = password or os.getenv("ERP_PASSWORD", "")
        self._client_id = client_id or int(os.getenv("ERP_CLIENT_ID", "1000015"))
        self._role_id = role_id or int(os.getenv("ERP_ROLE_ID", "1000040"))
        self._org_id = int(os.getenv("ERP_ORG_ID", "1000015"))
        self._timeout = timeout

        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._refresh_token: Optional[str] = None
        self._user_id: Optional[int] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self._username and self._password)

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    def _ensure_token(self):
        if self._token and time.time() < self._token_expires:
            return
        if self._refresh_token and self._user_id:
            try:
                self._refresh()
                return
            except Exception:
                pass
        self._authenticate()

    def _refresh(self):
        url = f"{self.base_url}/auth/refresh"
        payload = {
            "refresh_token": self._refresh_token,
            "clientId": self._client_id,
            "userId": self._user_id,
        }
        resp = requests.post(url, json=payload, headers=self._base_headers(), timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._token_expires = time.time() + 3300
        logger.info("iDempiere token refreshed")

    def _authenticate(self):
        if not REQUESTS_OK:
            raise RuntimeError("Package 'requests' belum terinstal")
        if not self.is_configured:
            raise RuntimeError("Kredensial ERP belum dikonfigurasi di .env")

        url = f"{self.base_url}/auth/tokens"
        payload = {
            "userName": self._username,
            "password": self._password,
            "parameters": {
                "clientId": self._client_id,
                "roleId": self._role_id,
                "organizationId": self._org_id,
                "language": "en_US",
            },
        }
        resp = requests.post(url, json=payload, headers=self._base_headers(), timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        self._token = data.get("token")
        self._refresh_token = data.get("refresh_token")
        self._user_id = data.get("userId")
        if not self._token:
            raise RuntimeError(f"Token tidak diterima dari ERP: {data}")

        self._token_expires = time.time() + 3300
        logger.info("iDempiere token berhasil didapat, berlaku ~55 menit")

    def _base_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sirekon/1.0",
        }

    def _auth_headers(self) -> Dict[str, str]:
        self._ensure_token()
        h = self._base_headers()
        h["Authorization"] = f"Bearer {self._token}"
        return h

    # ------------------------------------------------------------------
    # GET helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._auth_headers(), params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_records(self, path: str, filter_str: Optional[str] = None,
                     top: int = 100, skip: int = 0) -> List[Dict]:
        params = {"$top": top, "$skip": skip}
        if filter_str:
            params["$filter"] = filter_str
        data = self._get(path, params)
        return data.get("records", data.get("value", []))

    # ------------------------------------------------------------------
    # BUSINESS PARTNER
    # ------------------------------------------------------------------

    def get_business_partners(self, name_contains: Optional[str] = None,
                              top: int = 100) -> List[Dict]:
        filt = None
        if name_contains:
            safe = name_contains.replace("'", "''")
            filt = f"contains(Name,'{safe}')"
        return self._get_records("/models/c_bpartner", filter_str=filt, top=top)

    def get_partner_by_id(self, bp_id: int) -> Optional[Dict]:
        try:
            return self._get(f"/models/c_bpartner/{bp_id}")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # OPEN INVOICES
    # ------------------------------------------------------------------

    def get_open_invoices(self, bp_name: Optional[str] = None,
                          top: int = 100) -> List[Dict]:
        records = self._get_records("/models/sirekon_openinvoice", top=top)

        # Normalize nested BP fields and filter client-side
        result = []
        for rec in records:
            bp = rec.get("C_BPartner_ID", {})
            if isinstance(bp, dict):
                rec["_bp_name"] = bp.get("identifier", "")
                rec["_bp_id"] = bp.get("id")
            else:
                rec["_bp_name"] = ""
                rec["_bp_id"] = bp

            if bp_name:
                if bp_name.upper() not in rec["_bp_name"].upper():
                    continue
            result.append(rec)

        return result

    # ------------------------------------------------------------------
    # BANK ACCOUNTS
    # ------------------------------------------------------------------

    def get_bank_accounts(self) -> List[Dict]:
        return self._get_records("/models/c_bankaccount", top=50)

    # ------------------------------------------------------------------
    # CHARGES (kategori biaya)
    # ------------------------------------------------------------------

    def get_charges(self) -> List[Dict]:
        return self._get_records("/models/c_charge", top=50)

    # ------------------------------------------------------------------
    # POST PAYMENT
    # ------------------------------------------------------------------

    def post_payment(
        self,
        is_receipt: bool,
        amount: float,
        bank_account_id: int,
        bp_id: int = BP_SW_INTERNAL,
        charge_id: Optional[int] = None,
        invoice_id: Optional[int] = None,
        description: Optional[str] = None,
        date_trx: Optional[str] = None,
    ) -> Dict:
        """
        Posting payment ke iDempiere.

        is_receipt=True  → AR Receipt (C_DocType_ID 1000008)
        is_receipt=False → AP Payment (C_DocType_ID 1000009)

        charge_id dan invoice_id tidak boleh diisi bersamaan.
        TenderType: A = Direct Deposit (bank), X = Cash (rekening Kas 1000001).
        """
        if charge_id and invoice_id:
            raise ValueError("C_Charge_ID dan C_Invoice_ID tidak boleh diisi bersamaan")

        doc_type = DOCTYPE_AR_RECEIPT if is_receipt else DOCTYPE_AP_PAYMENT
        tender_type = "X" if bank_account_id == BANK_ACCOUNT_MAP.get("KAS") else "A"

        payload: Dict[str, Any] = {
            "AD_Org_ID": self._org_id,
            "C_DocType_ID": doc_type,
            "C_BankAccount_ID": bank_account_id,
            "C_BPartner_ID": bp_id,
            "PayAmt": amount,
            "C_Currency_ID": 303,
            "TenderType": tender_type,
            "doc-action": "CO",
        }

        if charge_id:
            payload["C_Charge_ID"] = charge_id
        if invoice_id:
            payload["C_Invoice_ID"] = invoice_id
        if description:
            payload["Description"] = description[:255]
        if date_trx:
            payload["DateTrx"] = date_trx
            payload["DateAcct"] = date_trx

        url = f"{self.base_url}/models/c_payment"
        resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # BANK TRANSFER
    # ------------------------------------------------------------------

    def bank_transfer(
        self,
        from_bank_id: int,
        to_bank_id: int,
        amount: float,
        description: Optional[str] = None,
        date_trx: Optional[str] = None,
        charge_id: int = 1000010,
    ) -> Dict:
        """
        Bank Transfer via proses iDempiere.
        Membuat Bank Transfer + AP Payment (asal) + AR Receipt (tujuan), langsung Completed.
        """
        payload: Dict[str, Any] = {
            "AD_Org_ID": self._org_id,
            "From_C_BankAccount_ID": from_bank_id,
            "To_C_BankAccount_ID": to_bank_id,
            "C_BPartner_ID": BP_SW_INTERNAL,
            "C_Currency_ID": 303,
            "C_Charge_ID": charge_id,
            "Amount": amount,
            "IsCreateBankTransferDoc": True,
        }
        if description:
            payload["Description"] = description[:255]
        if date_trx:
            payload["StatementDate"] = date_trx
            payload["DateAcct"] = date_trx

        url = f"{self.base_url}/processes/c_bankstatement-banktransfer"
        resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # VOID PAYMENT
    # ------------------------------------------------------------------

    def void_payment(self, payment_id: int) -> Dict:
        url = f"{self.base_url}/models/c_payment/{payment_id}"
        payload = {"doc-action": "VO"}
        resp = requests.put(url, json=payload, headers=self._auth_headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # MATCH INVOICE (untuk KB Engine)
    # ------------------------------------------------------------------

    def match_invoice(
        self,
        keterangan: str,
        nominal: Optional[float] = None,
        nama_rekanan: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Mencocokkan transaksi bank dengan open invoice di iDempiere.

        Strategi:
        1. Cari invoice berdasarkan nama rekanan (fuzzy via contains)
        2. Jika nominal cocok → MATCHED
        """
        if not nama_rekanan:
            return None

        try:
            invoices = self.get_open_invoices(bp_name=nama_rekanan, top=20)
        except Exception as e:
            logger.warning(f"Gagal query open invoices: {e}")
            return None

        if not invoices:
            return None

        nom_float = None
        if nominal is not None:
            try:
                nom_float = float(str(nominal).replace(",", "").replace("Rp", "").strip())
            except (ValueError, TypeError):
                nom_float = None

        for inv in invoices:
            inv_amt = float(inv.get("OpenAmt") or inv.get("GrandTotal") or 0)
            inv_no = inv.get("DocumentNo") or ""
            bp_name = inv.get("_bp_name") or ""
            is_sotrx = inv.get("IsSOTrx", True)

            # Cek keterangan mengandung nomor invoice
            if inv_no and inv_no.upper() in keterangan.upper():
                return {
                    "matched": True,
                    "kriteria": "Nomor Invoice Teridentifikasi",
                    "invoice_no": inv_no,
                    "invoice_id": inv.get("C_Invoice_ID"),
                    "partner_name": bp_name,
                    "kode_akun": "1.1.04.01" if is_sotrx else "2.1.01.01",
                    "amount": inv_amt,
                    "status_rekonsiliasi": "RECONCILED",
                }

            # Cek nominal cocok
            if nom_float and inv_amt > 0 and abs(nom_float - inv_amt) < 1.0:
                return {
                    "matched": True,
                    "kriteria": "Nama Rekanan & Nominal Tepat",
                    "invoice_no": inv_no,
                    "invoice_id": inv.get("C_Invoice_ID"),
                    "partner_name": bp_name,
                    "kode_akun": "1.1.04.01" if is_sotrx else "2.1.01.01",
                    "amount": inv_amt,
                    "status_rekonsiliasi": "RECONCILED",
                }

        return None

    # ------------------------------------------------------------------
    # RESOLVE CHARGE (untuk KB Engine posting)
    # ------------------------------------------------------------------

    def resolve_charge_id(self, nlp_label: str) -> Optional[int]:
        return CHARGE_MAP.get(nlp_label)

    def resolve_bank_account_id(self, bank_name: str) -> Optional[int]:
        return BANK_ACCOUNT_MAP.get(bank_name.upper())

    def resolve_doctype(self, is_incoming: bool) -> int:
        return DOCTYPE_AR_RECEIPT if is_incoming else DOCTYPE_AP_PAYMENT


# ---------------------------------------------------------------------------
# Singleton — dibuat dari .env
# ---------------------------------------------------------------------------
_client: Optional[IDempiereClient] = None


def get_idempiere_client() -> IDempiereClient:
    global _client
    if _client is None:
        _client = IDempiereClient()
        if _client.is_configured:
            logger.info(f"iDempiere client dikonfigurasi: {_client.base_url}")
        else:
            logger.warning("iDempiere client BELUM dikonfigurasi — tambahkan ERP_* di .env")
    return _client
