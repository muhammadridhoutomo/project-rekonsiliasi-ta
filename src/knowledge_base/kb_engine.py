"""
KB Engine — inference engine yang membaca tree + mapping dari Supabase.

Menggantikan hardcoded Python dict dengan data dinamis dari database.
Fallback ke hardcoded jika Supabase gagal dihubungi.
"""

import re
import time
from typing import Optional

# Fallback imports (hardcoded)
try:
    from knowledge_base.decision_tree_kb import klasifikasi_kb as _klasifikasi_hardcoded
    from knowledge_base.kategori_keuangan import KATEGORI as _KATEGORI_HARDCODED
    from knowledge_base.rekanan_resolver import (
        ekstrak_nama_rekanan, PREFIX_BANK, KATA_NOISE,
        JALUR_TRANSFER, _mengandung, _ada_jalur_transfer,
    )
except ImportError:
    from decision_tree_kb import klasifikasi_kb as _klasifikasi_hardcoded
    from kategori_keuangan import KATEGORI as _KATEGORI_HARDCODED
    from rekanan_resolver import (
        ekstrak_nama_rekanan, PREFIX_BANK, KATA_NOISE,
        JALUR_TRANSFER, _mengandung, _ada_jalur_transfer,
    )

try:
    from knowledge_base.api_client import erp_client
except ImportError:
    try:
        from src.knowledge_base.api_client import erp_client
    except ImportError:
        try:
            from api_client import erp_client
        except ImportError:
            erp_client = None

try:
    from knowledge_base.erp_idempiere import CHARGE_MAP, BANK_ACCOUNT_MAP
except ImportError:
    try:
        from src.knowledge_base.erp_idempiere import CHARGE_MAP, BANK_ACCOUNT_MAP
    except ImportError:
        try:
            from erp_idempiere import CHARGE_MAP, BANK_ACCOUNT_MAP
        except ImportError:
            CHARGE_MAP = {}
            BANK_ACCOUNT_MAP = {}


CACHE_TTL = 300  # 5 menit


def _cocok_keyword(keywords: list[str], teks_lower: str) -> bool:
    for kw in keywords:
        pola = r'(?<![a-z0-9])' + re.escape(kw.strip()) + r'(?![a-z0-9])'
        if re.search(pola, teks_lower):
            return True
    return False


def _normalisasi_jenis(jenis) -> Optional[str]:
    if not jenis:
        return None
    j = str(jenis).strip().upper()
    if j in ("CR", "KREDIT", "CASH_IN", "MASUK", "IN"):
        return "CR"
    if j in ("DB", "DEBIT", "CASH_OUT", "KELUAR", "OUT"):
        return "DB"
    return None


class KBEngine:
    """
    Knowledge Base Engine yang membaca aturan dari Supabase.

    Data yang di-load:
    - Tree Pola: keyword patterns + mapping ke kategori
    - Tree Kategori: hierarki kategori + kode akun
    - Tree Perusahaan: vendor, customer, entitas internal
    - Mapping Layer: confidence cross-domain
    - Account Mapping: kode bank -> kode ERP
    """

    def __init__(self, supabase_client, client_id: str):
        self._sb = supabase_client
        self._client_id = client_id
        self._cache = {}
        self._cache_time = 0

    def _is_cache_valid(self) -> bool:
        return (time.time() - self._cache_time) < CACHE_TTL and bool(self._cache)

    def _load_all(self):
        """Load semua data KB dari Supabase, simpan di cache."""
        if self._is_cache_valid():
            return

        # Load semua tree nodes sekaligus
        res = self._sb.table("tree_nodes").select("*") \
            .eq("client_id", self._client_id) \
            .execute()
        all_nodes = res.data

        # Load mapping layer
        res_map = self._sb.table("mapping_layer").select("*") \
            .eq("client_id", self._client_id) \
            .execute()
        all_mappings = res_map.data

        # Load account mapping
        res_acc = self._sb.table("account_mapping").select("*") \
            .eq("client_id", self._client_id) \
            .execute()
        all_account_maps = res_acc.data

        # Index nodes by id and by tree_type
        nodes_by_id = {n["id"]: n for n in all_nodes}
        nodes_by_type = {}
        for n in all_nodes:
            nodes_by_type.setdefault(n["tree_type"], []).append(n)

        # Build pola rules: [{keywords, target_kategori_node_id, confidence}]
        pola_rules = self._build_pola_rules(
            nodes_by_type.get("pola", []),
            nodes_by_id,
            all_mappings,
        )

        # Build kategori lookup: node_id -> {kode, nama, kode_akun, jenis}
        kategori_lookup = self._build_kategori_lookup(
            nodes_by_type.get("kategori", [])
        )

        # Build perusahaan lists
        perusahaan = self._build_perusahaan(
            nodes_by_type.get("perusahaan", [])
        )

        # Build account mapping
        acc_mapping = {
            m["kode_transaksi_bank"]: {
                "kode_akun_erp": m["kode_akun_erp"],
                "nama_akun": m["nama_akun"],
                "bank": m.get("bank"),
            }
            for m in all_account_maps
        }

        self._cache = {
            "pola_rules": pola_rules,
            "kategori_lookup": kategori_lookup,
            "kategori_by_kode": {v["kode"]: v for v in kategori_lookup.values()},
            "perusahaan": perusahaan,
            "account_mapping": acc_mapping,
            "nodes_by_id": nodes_by_id,
        }
        self._cache_time = time.time()

    def _build_pola_rules(self, pola_nodes, nodes_by_id, mappings):
        """
        Dari tree pola + mapping_layer, bangun daftar aturan:
        [{keywords, target_node_id, target_kode_akun, confidence, cabang_nama}]
        """
        # Index: pola group node_id -> mapping data
        mapping_by_source = {}
        for m in mappings:
            if m["relation_type"] == "pola_ke_kategori":
                mapping_by_source[m["source_node_id"]] = m

        # Ambil pola group nodes (level 1, bukan leaf)
        pola_groups = [n for n in pola_nodes if n["level"] == 1 and not n["is_leaf"]]

        rules = []
        for pg in pola_groups:
            meta = pg.get("metadata", {})
            keywords = meta.get("keywords", [])
            if not keywords:
                continue

            # Cari mapping ke kategori
            mapping = mapping_by_source.get(pg["id"])
            if not mapping:
                continue

            target_node_id = mapping["target_node_id"]
            confidence = mapping.get("confidence", 1.0)

            rules.append({
                "node_id": pg["id"],
                "kode": pg["kode"],
                "nama": pg["nama"],
                "keywords": keywords,
                "target_node_id": target_node_id,
                "confidence": confidence,
                "total_kemunculan": mapping.get("total_kemunculan", 0),
                "jumlah_konfirmasi_benar": mapping.get("jumlah_konfirmasi_benar", 0),
            })

        return rules

    def _build_kategori_lookup(self, kategori_nodes):
        """node_id -> {kode, nama, kode_akun, jenis, parent_id, level, is_leaf}"""
        lookup = {}
        for n in kategori_nodes:
            meta = n.get("metadata", {})
            lookup[n["id"]] = {
                "kode": n["kode"],
                "nama": n["nama"],
                "kode_akun": meta.get("kode_akun"),
                "jenis": meta.get("jenis"),
                "parent_id": n.get("parent_id"),
                "level": n["level"],
                "is_leaf": n["is_leaf"],
            }
        return lookup

    def _build_perusahaan(self, perusahaan_nodes):
        """Bangun daftar vendor, customer, internal dari tree perusahaan."""
        internal = []
        customers = []
        vendors = []

        for n in perusahaan_nodes:
            if n["level"] < 2:
                continue
            meta = n.get("metadata", {})
            tipe = meta.get("tipe")
            entry = {
                "nama": n["nama"],
                "kode_akun": meta.get("kode_akun"),
                "node_id": n["id"],
            }
            if tipe == "internal":
                internal.append(entry)
            elif tipe == "customer":
                customers.append(entry)
            elif tipe == "vendor":
                vendors.append(entry)

        return {
            "internal": internal,
            "customers": customers,
            "vendors": vendors,
        }

    def _resolve_kode_akun(self, target_node_id: str) -> tuple[str, str]:
        """
        Dari target kategori node_id, cari kode_akun.
        Jika node sendiri punya kode_akun, pakai itu.
        Jika tidak (non-leaf), cari child leaf yang punya kode_akun.
        Return (kode_akun, nama_akun).
        """
        kat = self._cache["kategori_lookup"]
        node = kat.get(target_node_id)
        if not node:
            return "UNKNOWN", "Unknown"

        if node["kode_akun"]:
            return node["kode_akun"], node["nama"]

        # Cari child leaf
        for nid, n in kat.items():
            if n["parent_id"] == target_node_id and n["kode_akun"]:
                return n["kode_akun"], n["nama"]

        return "PERLU_REVIEW", node["nama"]

    def klasifikasi(self, input_data, jenis=None, mutasi=None, nlp_output=None) -> dict:
        """
        Klasifikasi transaksi menggunakan data dari Supabase.
        Interface sama dengan klasifikasi_kb().
        Fallback ke hardcoded jika DB gagal.
        """
        try:
            self._load_all()
        except Exception:
            return _klasifikasi_hardcoded(input_data, jenis=jenis, mutasi=mutasi, nlp_output=nlp_output)

        # Parse input
        if isinstance(input_data, dict) or hasattr(input_data, 'get'):
            teks = str(input_data.get('keterangan', ''))
            if not jenis:
                jenis = input_data.get('jenis')
            if not mutasi:
                mutasi = input_data.get('mutasi') or input_data.get('debit') or input_data.get('kredit')
        else:
            teks = str(input_data)

        teks_lower = teks.lower()
        jenis_norm = _normalisasi_jenis(jenis)

        teks_bersih_lower = None
        if nlp_output and nlp_output.get("confidence_tinggi"):
            teks_bersih_lower = nlp_output.get("teks_bersih", "").lower()

        def _cek_kw(keywords):
            if _cocok_keyword(keywords, teks_lower):
                return True
            if teks_bersih_lower and _cocok_keyword(keywords, teks_bersih_lower):
                return True
            return False

        # ---- TAHAP 1: POLA MATCHING (dari DB) ----
        pola_rules = self._cache.get("pola_rules", [])
        for rule in pola_rules:
            if not _cek_kw(rule["keywords"]):
                continue

            target_node_id = rule["target_node_id"]
            kat = self._cache["kategori_lookup"].get(target_node_id, {})

            # Context rules: switching/transfer tergantung jenis CR/DB
            if kat.get("kode") in ("KAT_SWITCHING",):
                # Cari child dengan jenis yang sesuai
                kode_akun, nama_akun = self._resolve_switching(jenis_norm)
            else:
                kode_akun, nama_akun = self._resolve_kode_akun(target_node_id)

            confidence_str = ""
            if rule["confidence"] is not None and rule["confidence"] < 1.0:
                confidence_str = f", conf={rule['confidence']}"

            return {
                "teks_input": teks,
                "jenis": jenis_norm,
                "mutasi": mutasi,
                "kode_akun": kode_akun,
                "kategori_prediksi": f"{kode_akun} - {nama_akun}",
                "status": "KB_TEREALISASI",
                "metode": f"KB Engine ({rule['nama']}{confidence_str})",
                "kategori_node_id": target_node_id,
            }

        # Aturan sewa gedung / kantor operasional (CoA 6.2.10.01 Rent-Building)
        if jenis_norm == "DB" and _cek_kw(["sewa gedung", "sewa kantor", "sewa ruko"]):
            kode_akun = "6.2.10.01"
            nama_akun = self._get_nama_akun(kode_akun)
            return {
                "teks_input": teks,
                "jenis": jenis_norm,
                "mutasi": mutasi,
                "kode_akun": kode_akun,
                "kategori_prediksi": f"{kode_akun} - {nama_akun}",
                "status": "KB_TEREALISASI",
                "metode": "KB Engine (Pola Sewa Gedung/Kantor)",
            }

        # ---- TAHAP 2: RESOLUSI REKANAN & INVOICE ERP ----
        rekanan_result = self._resolve_rekanan_db(teks, jenis_norm)

        # Cek pencocokan invoice ERP (Mock / Live Adapter)
        inv_match = None
        if erp_client:
            nama_pihak = rekanan_result.get("nama_pihak") if rekanan_result else ekstrak_nama_rekanan(teks)
            try:
                inv_match = erp_client.match_invoice(teks, nominal=mutasi, nama_rekanan=nama_pihak)
            except Exception:
                inv_match = None

        if rekanan_result:
            if inv_match:
                rekanan_result["invoice_no"] = inv_match["invoice_no"]
                rekanan_result["invoice_status"] = "MATCHED"
                rekanan_result["invoice_amount"] = inv_match.get("amount")
                rekanan_result["invoice_kriteria"] = inv_match["kriteria"]
                rekanan_result["metode"] = f"{rekanan_result['metode']} + Faktur ERP ({inv_match['invoice_no']} Lunas)"
            return rekanan_result

        # Jika rekanan tidak di DB, tapi ada nomor invoice eksplisit di keterangan mutasi
        if inv_match:
            kode_akun = inv_match.get("kode_akun") or ("1.1.04.01" if jenis_norm == "CR" else "2.1.01.01")
            nama_akun = self._get_nama_akun(kode_akun)
            return {
                "teks_input": teks,
                "jenis": jenis_norm,
                "mutasi": mutasi,
                "kode_akun": kode_akun,
                "kategori_prediksi": f"{kode_akun} - {nama_akun}",
                "nama_pihak": inv_match.get("partner_name"),
                "invoice_no": inv_match["invoice_no"],
                "invoice_status": "MATCHED",
                "invoice_kriteria": inv_match["kriteria"],
                "status": "KB_TEREALISASI",
                "metode": f"KB Engine (Faktur ERP: {inv_match['invoice_no']} Match {inv_match['kriteria']})",
            }

        # ---- TAHAP 3: NLP VALIDATED ----
        if nlp_output and nlp_output.get("confidence_tinggi"):
            kategori_nlp = nlp_output["kategori_nlp"]
            kode_akun = self._resolve_nlp_kategori(kategori_nlp)
            nama_akun = self._get_nama_akun(kode_akun)

            return {
                "teks_input": teks,
                "jenis": jenis_norm,
                "mutasi": mutasi,
                "kode_akun": kode_akun,
                "kategori_prediksi": f"{kode_akun} - {nama_akun}",
                "status": "NLP_VALIDATED",
                "metode": f"NLP Confident (conf={nlp_output['confidence']}) -> KB Engine Validated",
            }

        # ---- TAHAP 4: MANUAL REVIEW ----
        return {
            "teks_input": teks,
            "jenis": jenis_norm,
            "mutasi": mutasi,
            "kode_akun": "UNKNOWN",
            "kategori_prediksi": "UNKNOWN",
            "status": "MANUAL_REVIEW",
            "metode": "Manual Review (Akuntan)",
        }

    def _resolve_switching(self, jenis_norm: Optional[str]) -> tuple[str, str]:
        """Cari kode akun switching berdasarkan jenis (CR/DB)."""
        kat = self._cache["kategori_lookup"]
        for nid, n in kat.items():
            if n["kode"] in ("KAT_SWITCH_IN", "KAT_SWITCH_OUT"):
                if n["jenis"] == jenis_norm and n["kode_akun"]:
                    return n["kode_akun"], n["nama"]

        return "1.1.02.98", "Cross Account Bank"

    def _resolve_rekanan_db(self, teks: str, jenis_norm: Optional[str]) -> Optional[dict]:
        """Resolusi vendor/customer dari data perusahaan di DB."""
        nama_pihak = ekstrak_nama_rekanan(teks)
        if not nama_pihak:
            return None

        perusahaan = self._cache.get("perusahaan", {})

        # 1. Entitas internal
        for ent in perusahaan.get("internal", []):
            if _mengandung(ent["nama"], nama_pihak):
                return {
                    "teks_input": teks,
                    "jenis": jenis_norm,
                    "mutasi": None,
                    "kode_akun": ent["kode_akun"] or "1.1.02.98",
                    "kategori_prediksi": f"{ent['kode_akun'] or '1.1.02.98'} - Cross Account Bank",
                    "nama_pihak": nama_pihak,
                    "status": "KB_TEREALISASI",
                    "metode": "KB Engine (Entitas Internal DB)",
                    "kategori_node_id": ent.get("node_id"),
                }

        # 2. Customer
        for cust in perusahaan.get("customers", []):
            if _mengandung(cust["nama"], nama_pihak):
                if jenis_norm == "DB":
                    return {
                        "teks_input": teks,
                        "jenis": jenis_norm,
                        "mutasi": None,
                        "kode_akun": "2.1.01.01",
                        "kategori_prediksi": "2.1.01.01 - Trade Payable - 3rd Party",
                        "nama_pihak": nama_pihak,
                        "status": "KB_TEREALISASI",
                        "metode": f"KB Engine (Master Customer DB: {cust['nama']} -> Vendor)",
                    }
                return {
                    "teks_input": teks,
                    "jenis": jenis_norm,
                    "mutasi": None,
                    "kode_akun": cust["kode_akun"] or "1.1.04.01",
                    "kategori_prediksi": f"{cust['kode_akun'] or '1.1.04.01'} - Account Receivable 3rd Party",
                    "nama_pihak": nama_pihak,
                    "status": "KB_TEREALISASI",
                    "metode": f"KB Engine (Master Customer DB: {cust['nama']})",
                }

        # 3. Vendor
        for vend in perusahaan.get("vendors", []):
            if _mengandung(vend["nama"], nama_pihak):
                return {
                    "teks_input": teks,
                    "jenis": jenis_norm,
                    "mutasi": None,
                    "kode_akun": vend["kode_akun"] or "2.1.01.01",
                    "kategori_prediksi": f"{vend['kode_akun'] or '2.1.01.01'} - Trade Payable - 3rd Party",
                    "nama_pihak": nama_pihak,
                    "status": "KB_TEREALISASI",
                    "metode": f"KB Engine (Master Vendor DB: {vend['nama']})",
                }

        # 4. Default CR/DB jika ada jalur transfer
        if _ada_jalur_transfer(teks):
            if jenis_norm == "CR":
                return {
                    "teks_input": teks,
                    "jenis": jenis_norm,
                    "mutasi": None,
                    "kode_akun": "1.1.04.01",
                    "kategori_prediksi": "1.1.04.01 - Account Receivable 3rd Party",
                    "nama_pihak": nama_pihak,
                    "status": "KB_TEREALISASI",
                    "metode": "KB Engine (Aturan Bisnis CR -> Customer)",
                }
            elif jenis_norm == "DB":
                return {
                    "teks_input": teks,
                    "jenis": jenis_norm,
                    "mutasi": None,
                    "kode_akun": "2.1.01.01",
                    "kategori_prediksi": "2.1.01.01 - Trade Payable - 3rd Party",
                    "nama_pihak": nama_pihak,
                    "status": "KB_TEREALISASI",
                    "metode": "KB Engine (Aturan Bisnis DB -> Vendor)",
                }

        return None

    def _resolve_nlp_kategori(self, kategori_nlp: str) -> str:
        """Konversi nama kategori NLP ke kode akun via DB."""
        # 1. Cek langsung mapping label NLP ke CoA
        try:
            from knowledge_base.coa import MAPPING_LABEL_NLP_KE_COA
        except ImportError:
            from coa import MAPPING_LABEL_NLP_KE_COA
        if kategori_nlp in MAPPING_LABEL_NLP_KE_COA:
            return MAPPING_LABEL_NLP_KE_COA[kategori_nlp]

        # 2. Cari di kategori by nama
        kat = self._cache.get("kategori_lookup", {})
        for nid, n in kat.items():
            if n["nama"] == kategori_nlp and n["kode_akun"]:
                return n["kode_akun"]

        # 3. Cari di account_mapping
        acc = self._cache.get("account_mapping", {})
        for kode_bank, info in acc.items():
            if kode_bank.upper() in kategori_nlp.upper():
                return info["kode_akun_erp"]

        # 4. Fallback: coba konversi via hardcoded
        try:
            from knowledge_base.coa import konversi_kode
        except ImportError:
            from coa import konversi_kode
        nama_ke_kode_lama = {v["nama"]: k for k, v in _KATEGORI_HARDCODED.items() if "-" in k}
        kode_lama = nama_ke_kode_lama.get(kategori_nlp, kategori_nlp)
        hasil = konversi_kode(kode_lama)
        return hasil["kode_coa"]

    def _get_nama_akun(self, kode_akun: str) -> str:
        """Cari nama akun dari kode."""
        kat = self._cache.get("kategori_lookup", {})
        for nid, n in kat.items():
            if n["kode_akun"] == kode_akun:
                return n["nama"]
        return _KATEGORI_HARDCODED.get(kode_akun, {}).get("nama", kode_akun)

    def prepare_erp_posting(self, klasifikasi_result: dict, bank: str = "BCA") -> Optional[dict]:
        """
        Siapkan payload untuk posting ke iDempiere berdasarkan hasil klasifikasi.

        Return dict dengan field siap kirim, atau None jika tidak bisa di-post.
        """
        status = klasifikasi_result.get("status")
        if status not in ("KB_TEREALISASI", "NLP_VALIDATED"):
            return None

        kode_akun = klasifikasi_result.get("kode_akun", "")
        if not kode_akun or kode_akun in ("UNKNOWN", "PERLU_REVIEW"):
            return None

        jenis = klasifikasi_result.get("jenis")
        mutasi = klasifikasi_result.get("mutasi") or 0
        is_receipt = jenis == "CR"

        bank_account_id = BANK_ACCOUNT_MAP.get(bank.upper())
        if not bank_account_id:
            return None

        # Cek apakah ada invoice match
        invoice_id = klasifikasi_result.get("invoice_id")

        # Resolve charge dari NLP label (jika ada di metode)
        charge_id = None
        for label, cid in CHARGE_MAP.items():
            if label.lower() in klasifikasi_result.get("metode", "").lower():
                charge_id = cid
                break

        # Jangan isi charge dan invoice bersamaan
        if invoice_id and charge_id:
            charge_id = None

        return {
            "is_receipt": is_receipt,
            "amount": abs(float(mutasi)),
            "bank_account_id": bank_account_id,
            "charge_id": charge_id,
            "invoice_id": invoice_id,
            "description": klasifikasi_result.get("teks_input", "")[:200],
            "kode_akun": kode_akun,
            "metode": klasifikasi_result.get("metode"),
        }

    def invalidate_cache(self):
        """Force reload dari database pada klasifikasi berikutnya."""
        self._cache_time = 0


# Singleton engine instance (dibuat saat pertama kali dibutuhkan)
_engine: Optional[KBEngine] = None


def get_engine() -> KBEngine:
    """Dapatkan singleton KBEngine instance."""
    global _engine
    if _engine is None:
        from api.db import get_supabase, CLIENT_ID
        _engine = KBEngine(get_supabase(), CLIENT_ID)
    return _engine


def klasifikasi_kb_db(input_data, jenis=None, mutasi=None, nlp_output=None) -> dict:
    """
    Drop-in replacement untuk klasifikasi_kb().
    Baca dari Supabase, fallback ke hardcoded.
    """
    try:
        engine = get_engine()
        return engine.klasifikasi(input_data, jenis=jenis, mutasi=mutasi, nlp_output=nlp_output)
    except Exception:
        return _klasifikasi_hardcoded(input_data, jenis=jenis, mutasi=mutasi, nlp_output=nlp_output)
