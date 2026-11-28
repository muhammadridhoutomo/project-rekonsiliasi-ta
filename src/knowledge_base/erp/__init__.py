"""
knowledge_base.erp — Koneksi API & ERP iDempiere 13 (Avolut).

Modul:
  - erp_idempiere : REST client langsung ke iDempiere sandbox (auth, GET, POST, PUT)
  - api_client    : Adapter otomatis LIVE (iDempiere) / MOCK (data statis)

Contoh penggunaan:
    from knowledge_base.erp.api_client import erp_client
    hasil = erp_client.match_invoice("INV-2023-001", nominal=580075045.0)
"""
