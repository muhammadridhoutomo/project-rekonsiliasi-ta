"""
knowledge_base — Modul Knowledge Base (Pool 3) untuk Sistem Rekonsiliasi.

Struktur folder:
    knowledge_base/
    ├── kb_engine.py             ← Mesin inferensi utama (forward chaining 4 tahap)
    ├── decision_tree_kb.py      ← Aturan klasifikasi hardcoded (rule-based)
    ├── knowledge_base.py        ← Legacy wrapper
    ├── visualisasi_kb_tree.py   ← Visualisasi pohon keputusan KB
    │
    ├── erp/                     ← Koneksi API & ERP iDempiere 13
    │   ├── erp_idempiere.py     ← REST client (auth, GET/POST/PUT endpoint)
    │   └── api_client.py        ← Adapter LIVE (iDempiere) / MOCK otomatis
    │
    └── mapping/                 ← Mapping kategori, CoA & rekanan
        ├── kategori_keuangan.py ← 21 kategori NLP + peta ke ERP iDempiere
        ├── coa.py               ← Chart of Accounts lookup & konversi kode
        └── rekanan_resolver.py  ← Resolver nama rekanan dari teks transaksi

Pipeline:
    Pool 1 (Tabel) → Pool 2 (NLP) → Pool 3 (KB Engine)
                                        ├── mapping/ (kategori, CoA, rekanan)
                                        └── erp/     (query & posting iDempiere)
"""

import sys as _sys

# ---------------------------------------------------------------------------
# Backward-compatible aliases: supaya import lama tetap jalan
# contoh: "from knowledge_base.coa import konversi_kode" masih berfungsi
# meskipun coa.py sudah pindah ke knowledge_base/mapping/coa.py
# ---------------------------------------------------------------------------
from knowledge_base.mapping import kategori_keuangan as _kategori_keuangan
from knowledge_base.mapping import coa as _coa
from knowledge_base.mapping import rekanan_resolver as _rekanan_resolver

_sys.modules.setdefault("knowledge_base.kategori_keuangan", _kategori_keuangan)
_sys.modules.setdefault("knowledge_base.coa", _coa)
_sys.modules.setdefault("knowledge_base.rekanan_resolver", _rekanan_resolver)

from knowledge_base.erp import erp_idempiere as _erp_idempiere
from knowledge_base.erp import api_client as _api_client

_sys.modules.setdefault("knowledge_base.erp_idempiere", _erp_idempiere)
_sys.modules.setdefault("knowledge_base.api_client", _api_client)
