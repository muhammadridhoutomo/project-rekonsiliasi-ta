"""
Business logic layer — menghubungkan API dengan NLP, KB Engine (Forward Chaining), dan Supabase.
"""

import re
import uuid
import datetime
from typing import Optional, List, Dict, Any
from api.db import get_supabase, CLIENT_ID

# Import KB Engine (baca dari Supabase, fallback ke hardcoded)
from knowledge_base.kb_engine import klasifikasi_kb_db as klasifikasi_kb
from knowledge_base.coa import konversi_kode, MAPPING_LAMA_KE_COA, load_coa, coa_nama, COA_PATH
from knowledge_base.kategori_keuangan import KATEGORI

# Lazy loading model NLP
_nlp_model = None
_nlp_threshold = 0.72
_nlp_vectorizer = None


def get_nlp_model():
    """Memuat model NLP, Threshold (0.72), & Vectorizer secara lazy."""
    global _nlp_model, _nlp_threshold, _nlp_vectorizer
    if _nlp_model is None:
        try:
            from routing import load_model
            loaded = load_model()
            if len(loaded) == 3:
                _nlp_model, _nlp_threshold, _nlp_vectorizer = loaded
            elif len(loaded) == 2:
                _nlp_model, _nlp_vectorizer = loaded
                _nlp_threshold = 0.72
        except Exception as e:
            print(f"Warning: Model NLP tidak dapat dimuat ({e}), fallback KB-only.")
    return _nlp_model, _nlp_threshold, _nlp_vectorizer


def _clean_mutasi(val: Any) -> float:
    """Parse nilai mutasi/nominal menjadi float yang aman."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(',', '').replace('Rp', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_iso_date(raw_date: Any) -> str:
    """Mengubah format tanggal mutasi menjadi format ISO YYYY-MM-DD untuk PostgreSQL."""
    if not raw_date or str(raw_date).strip() in ("-", "", "None"):
        return "2023-01-01"
    
    s = str(raw_date).strip()
    # Jika sudah format YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    
    # Format DD/MM/YYYY atau DD-MM-YYYY
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', s)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{int(mth):02d}-{int(d):02d}"

    # Format DD/MM (asumsikan tahun 2023 berdasarkan data mutasi BCA)
    m2 = re.match(r'^(\d{1,2})[/-](\d{1,2})$', s)
    if m2:
        d, mth = m2.groups()
        return f"2023-{int(mth):02d}-{int(d):02d}"

    return "2023-01-01"


def proses_transaksi_batch(transaksi_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Proses batch transaksi melalui pipeline lengkap:
    1. Ekstraksi kolom standar: Tanggal, Keterangan, Debit, Kredit, Saldo
    2. Modul NLP (Abror): Normalisasi kamus, prediksi kategori CoA, & Confidence Score (ambang batas 0.72)
    3. Modul Knowledge Base - Forward Chaining (Mario): Pencocokan ke aturan & data ERP perusahaan
       (baik untuk transaksi dengan confidence >= 0.72 maupun < 0.72)
    4. Penentuan 3 Status Resmi UI:
       - Auto Match : Confidence NLP >= 0.72 DAN ditemukan kecocokan di sistem ERP
       - Suggestion : Confidence NLP <  0.72 DAN ditemukan kesesuaian via Forward Chaining di ERP (perlu validasi user)
       - Not Found  : Tidak ditemukan pasangannya di sistem ERP (baik dari jalur >= 0.72 maupun < 0.72)
    5. Simpan hasil transaksi ke database Supabase & return daftar hasil terstandarisasi untuk Frontend
    """
    sb = get_supabase()
    model, threshold, vectorizer = get_nlp_model()
    
    results = []
    running_saldo = 500000000.0  # Default saldo awal simulasi jika saldo tidak disertakan

    for trx in transaksi_list:
        keterangan = str(trx.get("keterangan") or trx.get("ket") or "")
        
        debit_raw = _clean_mutasi(trx.get("debit"))
        kredit_raw = _clean_mutasi(trx.get("kredit"))
        mutasi_raw = _clean_mutasi(trx.get("mutasi"))
        saldo_raw = _clean_mutasi(trx.get("saldo"))

        jenis = str(trx.get("jenis") or "").upper()
        if debit_raw > 0:
            jenis = "DB"
            mutasi_float = debit_raw
        elif kredit_raw > 0:
            jenis = "CR"
            mutasi_float = kredit_raw
        else:
            if jenis not in ("DB", "CR"):
                jenis = "DB"
            mutasi_float = mutasi_raw
            if jenis == "DB":
                debit_raw = mutasi_float
            else:
                kredit_raw = mutasi_float

        if saldo_raw > 0:
            running_saldo = saldo_raw
        else:
            if jenis == "CR":
                running_saldo += mutasi_float
            else:
                running_saldo -= mutasi_float
            saldo_raw = running_saldo

        tanggal_raw = trx.get("tanggal") or trx.get("tgl") or trx.get("waktu_transaksi") or "-"
        tanggal_iso = _parse_iso_date(tanggal_raw)

        # 1. Jalankan Modul NLP (Abror)
        nlp_output = trx.get("nlp_output")
        if not nlp_output and model and keterangan:
            try:
                from kamus_istilah import normalisasi_teks
                teks_clean = normalisasi_teks(keterangan)
                if vectorizer is None:
                    # Model CoA baru (Pipeline)
                    inp_teks = f"arah{jenis.lower()} " + teks_clean
                    proba = model.predict_proba([inp_teks])[0]
                else:
                    # Model lama
                    from routing import preprocess_pipeline
                    teks_clean = preprocess_pipeline(keterangan)
                    X = vectorizer.transform([teks_clean])
                    proba = model.predict_proba(X)[0]

                idx = proba.argmax()
                kategori_ml = str(model.classes_[idx])
                confidence = float(proba[idx])
                nlp_output = {
                    "teks_asli": keterangan,
                    "teks_bersih": teks_clean,
                    "kategori_nlp": kategori_ml,
                    "confidence": round(confidence, 4),
                    "confidence_tinggi": confidence >= threshold,
                }
            except Exception:
                nlp_output = None

        # 2. Jalankan Modul KB Engine — Forward Chaining ke ERP (Mario)
        # Dijalankan untuk SEMUA transaksi (baik confidence >= 0.72 maupun < 0.72)
        kb_result = klasifikasi_kb(
            keterangan,
            jenis=jenis,
            mutasi=mutasi_float,
            nlp_output=nlp_output,
        )

        # 3. Tentukan 3 Status Resmi: Auto Match, Suggestion, Not Found
        kb_status = kb_result.get("status", "MANUAL_REVIEW")
        kode_akun = kb_result.get("kode_akun", "-")
        conf_val = float(nlp_output.get("confidence") or 0.0) if nlp_output else 0.0
        conf_tinggi = bool(nlp_output and nlp_output.get("confidence_tinggi", False))

        # Cek apakah hasil Forward Chaining menemukan pasangan/akun valid di sistem ERP
        erp_found = (
            kb_status in ("KB_TEREALISASI", "NLP_VALIDATED")
            and kode_akun not in ("PERLU_REVIEW", "UNKNOWN", "-", "", None)
        )

        if conf_tinggi and erp_found:
            status_db = "auto_match"
            status_ui = "auto_match"
            pool_label = "Jalur >= 0.72 (Auto Match ERP)"
        elif (not conf_tinggi) and erp_found:
            status_db = "suggestion"
            status_ui = "suggestion"
            pool_label = "Jalur < 0.72 (Forward Chaining -> Suggestion)"
        else:
            # Tidak ditemukan di sistem ERP (baik dari jalur >= 0.72 maupun < 0.72) -> Not Found
            # Disimpan sebagai 'manual' di tabel transaksi DB agar sesuai CHECK constraint PostgreSQL
            status_db = "manual"
            status_ui = "not_found"
            pool_label = (
                "Jalur >= 0.72 (Tidak Ditemukan di ERP -> Not Found)"
                if conf_tinggi
                else "Jalur < 0.72 (Tidak Ditemukan di ERP -> Not Found)"
            )

        kategori_node_id = _find_kategori_node(kode_akun)
        teks_bersih_val = kb_result.get("teks_bersih") or (nlp_output.get("teks_bersih") if nlp_output else keterangan)
        kategori_nlp_val = nlp_output.get("kategori_nlp") if nlp_output else "-"

        # 4. Simpan ke database Supabase (dengan graceful fallback jika gagal)
        trx_id = str(uuid.uuid4())
        try:
            row = {
                "client_id": CLIENT_ID,
                "tanggal": tanggal_iso,
                "keterangan": keterangan,
                "keterangan_bersih": teks_bersih_val,
                "jenis": jenis,
                "mutasi": mutasi_float,
                "kode_akun_erp": kode_akun,
                "nama_akun": kb_result.get("kategori_prediksi"),
                "kategori_node_id": kategori_node_id,
                "nlp_confidence": conf_val,
                "metode_matching": kb_result.get("metode"),
                "status": status_db,
                "sumber_file": trx.get("sumber_file"),
                "metadata": {
                    "kb_status": kb_status,
                    "status_ui": status_ui,
                    "kategori_nlp": kategori_nlp_val,
                    "debit": debit_raw,
                    "kredit": kredit_raw,
                    "saldo": saldo_raw,
                    "nama_pihak": kb_result.get("nama_pihak"),
                    "invoice_no": kb_result.get("invoice_no"),
                    "invoice_status": kb_result.get("invoice_status"),
                },
            }
            res = sb.table("transaksi").insert(row).execute()
            if res.data and len(res.data) > 0:
                trx_id = res.data[0]["id"]
        except Exception as e:
            print(f"Notice: Simpan transaksi ke DB dilewati / error: {e}")

        # 5. Output terstandarisasi untuk Frontend
        results.append({
            "id": trx_id,
            "tanggal": tanggal_raw if tanggal_raw != "-" else tanggal_iso,
            "keterangan": keterangan,
            "teks_bersih": teks_bersih_val,
            "kategori_nlp": kategori_nlp_val,
            "jenis": jenis,
            "debit": debit_raw,
            "kredit": kredit_raw,
            "saldo": saldo_raw,
            "mutasi": mutasi_float,
            "kode_akun": kode_akun if erp_found else "NOT_FOUND",
            "nama_akun": kb_result.get("kategori_prediksi") if erp_found else f"Belum Ditemukan di ERP (NLP: {kategori_nlp_val})",
            "kandidat_kode_akun": kode_akun,
            "kandidat_nama_akun": kb_result.get("kategori_prediksi") or "-",
            "status": status_ui,
            "status_db": status_db,
            "metode": kb_result.get("metode") or "-",
            "nama_pihak": kb_result.get("nama_pihak"),
            "invoice_no": kb_result.get("invoice_no"),
            "invoice_status": kb_result.get("invoice_status"),
            "conf": conf_val,
            "confidence_tinggi": conf_tinggi,
            "threshold": threshold,
            "pool": pool_label,
            # Properti alias untuk kompatibilitas frontend
            "tgl": tanggal_raw if tanggal_raw != "-" else tanggal_iso,
            "ket": keterangan,
            "akun": kode_akun if erp_found else "NOT_FOUND",
            "nama": kb_result.get("kategori_prediksi") or "-",
        })

    return results


def get_daftar_coa() -> List[Dict[str, Any]]:
    """
    Mengambil daftar lengkap Bagan Akun (Chart of Accounts / CoA) dari sistem ERP perusahaan
    untuk ditampilkan di UI saat user melakukan pencocokan manual (Not Found / Suggestion).

    Sumber data (prioritas):
      1. Tabel coa_master di Supabase (diimpor dari CoA.xlsx mitra)
      2. Fallback: file CoA.xlsx lokal (untuk development)
      3. Tambahan dari tree_nodes kategori yang belum ada di master
    """
    daftar = []
    seen = set()

    sb = get_supabase()

    # 1. Baca dari tabel coa_master di Supabase (sumber utama production)
    try:
        res = sb.table("coa_master").select("kode, nama, account_type") \
            .eq("is_posting", True) \
            .order("kode") \
            .execute()
        for row in res.data:
            kode = row["kode"].strip()
            nama = row["nama"].strip()
            if kode and kode not in seen:
                seen.add(kode)
                daftar.append({
                    "kode": kode,
                    "nama": nama,
                    "label": f"{kode} - {nama}",
                    "account_type": row.get("account_type", ""),
                })
    except Exception:
        pass

    # 2. Fallback: file CoA.xlsx lokal (development / jika coa_master kosong)
    if not daftar:
        try:
            if COA_PATH.exists():
                df = load_coa()
                for _, row in df.iterrows():
                    if row.get("is_posting"):
                        kode = str(row["kode"]).strip()
                        nama = str(row["nama"]).strip()
                        if kode and kode not in seen:
                            seen.add(kode)
                            daftar.append({
                                "kode": kode,
                                "nama": nama,
                                "label": f"{kode} - {nama}",
                                "account_type": str(row.get("account_type", "")).strip(),
                            })
        except Exception as e:
            print(f"Notice load_coa: {e}")

    # 3. Tambahkan dari tree_nodes kategori di Supabase jika belum ada
    try:
        res = sb.table("tree_nodes").select("nama, metadata") \
            .eq("client_id", CLIENT_ID) \
            .eq("tree_type", "kategori") \
            .execute()
        for n in res.data:
            meta = n.get("metadata") or {}
            kode = meta.get("kode_akun")
            nama = n.get("nama")
            if kode and kode not in ("PERLU_REVIEW", "UNKNOWN", "-") and kode not in seen:
                seen.add(kode)
                daftar.append({
                    "kode": kode,
                    "nama": nama,
                    "label": f"{kode} - {nama}",
                    "account_type": meta.get("jenis", ""),
                })
    except Exception:
        pass

    daftar.sort(key=lambda x: x["kode"])
    return daftar


def _find_kategori_node(kode_akun: str) -> Optional[str]:
    """Cari node ID di tree_nodes berdasarkan kode_akun di metadata."""
    if not kode_akun or kode_akun in ("UNKNOWN", "PERLU_REVIEW", "-", "NOT_FOUND"):
        return None

    try:
        sb = get_supabase()
        res = sb.table("tree_nodes").select("id, metadata") \
            .eq("client_id", CLIENT_ID) \
            .eq("tree_type", "kategori") \
            .execute()

        for node in res.data:
            meta = node.get("metadata", {})
            if isinstance(meta, dict) and meta.get("kode_akun") == kode_akun:
                return node["id"]
    except Exception:
        pass

    return None


def get_tree_nodes(tree_type: str) -> List[Dict[str, Any]]:
    """Ambil semua nodes dari satu tree type, termasuk parent info."""
    sb = get_supabase()
    res = sb.table("tree_nodes").select("*") \
        .eq("client_id", CLIENT_ID) \
        .eq("tree_type", tree_type) \
        .order("level") \
        .execute()
    return res.data


def get_statistik() -> Dict[str, Any]:
    """Hitung statistik rekonsiliasi riil dari database Supabase."""
    sb = get_supabase()
    try:
        all_trx = sb.table("transaksi").select("id, status") \
            .eq("client_id", CLIENT_ID) \
            .execute()

        total = len(all_trx.data)
        if total == 0:
            return {
                "total": 0,
                "auto_match": 0,
                "suggestion": 0,
                "not_found": 0,
                "manual": 0,
                "confirmed": 0,
                "rejected": 0,
                "coverage": 0.0,
            }

        counts = {}
        for trx in all_trx.data:
            s = trx["status"]
            counts[s] = counts.get(s, 0) + 1

        auto = counts.get("auto_match", 0)
        confirmed = counts.get("confirmed", 0)
        suggestion = counts.get("suggestion", 0)
        not_found = counts.get("manual", 0) + counts.get("not_found", 0)
        rejected = counts.get("rejected", 0)

        coverage = (auto + confirmed) / total if total > 0 else 0.0

        return {
            "total": total,
            "auto_match": auto,
            "suggestion": suggestion,
            "not_found": not_found,
            "manual": not_found,
            "confirmed": confirmed,
            "rejected": rejected,
            "coverage": round(coverage, 4),
        }
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return {
            "total": 0,
            "auto_match": 0,
            "suggestion": 0,
            "not_found": 0,
            "manual": 0,
            "confirmed": 0,
            "rejected": 0,
            "coverage": 0.0,
        }
