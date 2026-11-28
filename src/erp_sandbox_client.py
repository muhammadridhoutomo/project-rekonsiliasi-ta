"""
erp_sandbox_client.py
=====================
Klien REST API untuk Sandbox ERP Avolut (iDempiere 13 - tenant SYNO WORLD)
sesuai dokumen "Tanggapan Teknis: API Sandbox ERP Avolut untuk SIREKON" (27 November 2026).

Kredensial dibaca dari environment variable / file .env (JANGAN hardcode password di kode):
  ERP_BASE_URL=https://dev-recon.midsuit.com/api/v1
  ERP_USERNAME=sirekon
  ERP_PASSWORD=...
  ERP_CLIENT_ID=1000015
  ERP_ROLE_ID=1000040
  ERP_ORG_ID=1000015

Catatan Cloudflare: selalu kirim header User-Agent: sirekon/1.0 agar tidak terkena 403 Error 1010.

Uji koneksi live (read-only GET):
  venv\\Scripts\\python.exe src\\erp_sandbox_client.py
"""
import os
from pathlib import Path
from urllib.parse import quote

import httpx


def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class IDempiereClient:
    def __init__(self, base_url=None, username=None, password=None,
                 client_id=None, role_id=None, org_id=None, timeout=20.0):
        _load_dotenv()
        self.base_url = (base_url or os.getenv("ERP_BASE_URL", "https://dev-recon.midsuit.com/api/v1")).rstrip("/")
        self.username = username or os.getenv("ERP_USERNAME", "sirekon")
        self.password = password or os.getenv("ERP_PASSWORD", "")
        self.client_id = int(client_id or os.getenv("ERP_CLIENT_ID", "1000015"))
        self.role_id = int(role_id or os.getenv("ERP_ROLE_ID", "1000040"))
        self.org_id = int(org_id or os.getenv("ERP_ORG_ID", "1000015"))
        self.timeout = timeout
        self.token = None
        self.refresh_token = None
        self.user_id = None
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={
                "User-Agent": "sirekon/1.0",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def login(self):
        if not self.password:
            raise RuntimeError("ERP_PASSWORD belum diset di environment / .env")
        payload = {
            "userName": self.username,
            "password": self.password,
            "parameters": {
                "clientId": self.client_id,
                "roleId": self.role_id,
                "organizationId": self.org_id,
                "language": "en_US",
            },
        }
        r = self._client.post(f"{self.base_url}/auth/tokens", json=payload)
        r.raise_for_status()
        data = r.json()
        self.token = data["token"]
        self.refresh_token = data.get("refresh_token")
        self.user_id = data.get("userId")
        return data

    def refresh(self):
        if not (self.refresh_token and self.user_id):
            return self.login()
        r = self._client.post(
            f"{self.base_url}/auth/refresh",
            json={"refresh_token": self.refresh_token, "clientId": self.client_id, "userId": self.user_id},
        )
        if r.status_code != 200:
            return self.login()
        data = r.json()
        self.token = data["token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        return data

    def _request(self, method, path, params=None, json_body=None):
        if not self.token:
            self.login()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}{path}"
        r = self._client.request(method, url, params=params, json=json_body, headers=headers)
        if r.status_code == 401:
            self.refresh()
            headers = {"Authorization": f"Bearer {self.token}"}
            r = self._client.request(method, url, params=params, json=json_body, headers=headers)
        r.raise_for_status()
        return r.json()

    # --- 4. ENDPOINT GET (LOOKUP) ---
    def get_bpartners(self, is_customer=None, is_vendor=None, is_employee=None, name_contains=None, top=100):
        filters = []
        if is_customer is not None:
            filters.append(f"IsCustomer eq {'true' if is_customer else 'false'}")
        if is_vendor is not None:
            filters.append(f"IsVendor eq {'true' if is_vendor else 'false'}")
        if is_employee is not None:
            filters.append(f"IsEmployee eq {'true' if is_employee else 'false'}")
        if name_contains:
            safe = name_contains.replace("'", "''")
            filters.append(f"contains(Name,'{safe}')")
        params = {"$select": "Value,Name,TaxID,IsCustomer,IsVendor,IsEmployee", "$top": top}
        if filters:
            params["$filter"] = " and ".join(filters)
        return self._request("GET", "/models/c_bpartner", params=params)

    def get_open_invoices(self, is_sotrx=None, bpartner_id=None, open_amt=None, top=100):
        filters = []
        if is_sotrx is not None:
            filters.append(f"IsSOTrx eq {'true' if is_sotrx else 'false'}")
        if bpartner_id is not None:
            filters.append(f"C_BPartner_ID eq {int(bpartner_id)}")
        if open_amt is not None:
            filters.append(f"OpenAmt eq {open_amt}")
        params = {"$top": top}
        if filters:
            params["$filter"] = " and ".join(filters)
        return self._request("GET", "/models/sirekon_openinvoice", params=params)

    def get_bank_accounts(self):
        return self._request(
            "GET", "/models/c_bankaccount",
            params={"$select": "Name,AccountNo,BankAccountType,C_Currency_ID"},
        )

    def get_charges(self, name=None, min_id=1000009):
        if name:
            safe = name.replace("'", "''")
            flt = f"Name eq '{safe}'"
        else:
            flt = f"C_Charge_ID ge {int(min_id)}"
        return self._request(
            "GET", "/models/c_charge",
            params={"$filter": flt, "$select": "Name,Description", "$expand": "C_Charge_Acct($select=Ch_Expense_Acct)"},
        )

    # --- 5. ENDPOINT POST / PUT (PUSH) ---
    def post_payment(self, doc_type_id, bank_account_id, bpartner_id, pay_amt, date_trx,
                     description, invoice_id=None, charge_id=None, tender_type="A", complete=True):
        if invoice_id and charge_id:
            raise ValueError("C_Invoice_ID dan C_Charge_ID tidak boleh diisi bersamaan")
        payload = {
            "AD_Org_ID": self.org_id,
            "C_DocType_ID": int(doc_type_id),
            "C_BankAccount_ID": int(bank_account_id),
            "C_BPartner_ID": int(bpartner_id),
            "PayAmt": float(pay_amt),
            "C_Currency_ID": 303,
            "TenderType": tender_type,
            "DateTrx": date_trx,
            "Description": description,
        }
        if invoice_id:
            payload["C_Invoice_ID"] = int(invoice_id)
        if charge_id:
            payload["C_Charge_ID"] = int(charge_id)
        if complete:
            payload["doc-action"] = "CO"
        return self._request("POST", "/models/c_payment", json_body=payload)

    def post_bank_transfer(self, from_bank_id, to_bank_id, amount, statement_date, description,
                           charge_id=1000010, bpartner_id=1000079):
        payload = {
            "From_C_BankAccount_ID": int(from_bank_id),
            "To_C_BankAccount_ID": int(to_bank_id),
            "C_BPartner_ID": int(bpartner_id),
            "C_Currency_ID": 303,
            "C_Charge_ID": int(charge_id),
            "Amount": float(amount),
            "Description": description,
            "StatementDate": statement_date,
            "DateAcct": statement_date,
            "AD_Org_ID": self.org_id,
            "IsCreateBankTransferDoc": True,
        }
        return self._request("POST", "/processes/c_bankstatement-banktransfer", json_body=payload)

    def void_payment(self, payment_id):
        return self._request("PUT", f"/models/c_payment/{int(payment_id)}", json_body={"doc-action": "VO"})


def main():
    cli = IDempiereClient()
    auth = cli.login()
    print(f"Login OK | userId={auth.get('userId')} | token_len={len(auth.get('token', ''))}")

    banks = cli.get_bank_accounts().get("records", [])
    print(f"\nRekening Bank ({len(banks)}):")
    for b in banks:
        print(f"  - id={b['id']} | {b.get('Name')} | No={b.get('AccountNo')}")

    inv = cli.get_open_invoices().get("records", [])
    print(f"\nOpen Invoices SIREKON ({len(inv)}):")
    for x in inv:
        bp = x.get("C_BPartner_ID", {})
        print(f"  - id={x['id']} | {x.get('DocumentNo')} | IsSOTrx={x.get('IsSOTrx')} | {bp.get('identifier')} | OpenAmt={x.get('OpenAmt')}")

    charges = cli.get_charges().get("records", [])
    print(f"\nCharges SIREKON ({len(charges)}):")
    for ch in charges[:8]:
        acct = ch.get("C_Charge_Acct", [{}])[0].get("Ch_Expense_Acct", {}).get("identifier", "")
        print(f"  - id={ch['id']} | {ch.get('Name'):<28} | {acct}")
    if len(charges) > 8:
        print(f"  ... (+{len(charges) - 8} charge lainnya)")


if __name__ == "__main__":
    main()
