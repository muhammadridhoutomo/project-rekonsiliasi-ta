"""
proses_json.py
==============
Jembatan integrasi Python in-memory antara Pool 1 (Arya - Table Recognition),
Pool 2 (Abror - Modul NLP + Feedback Learning), dan Pool 3 (Mario - Backend FastAPI & KB).

Cara Pemakaian di Backend FastAPI (Pool 3 - Mario):
---------------------------------------------------
    from table_recognition.main import process_file
    from src.proses_json import klasifikasi_batch, terapkan_koreksi, catat_koreksi_tunggal

    # 1. Pool 1 (Arya) mengekstrak PDF menjadi list[dict]
    raw_records = process_file(pdf_path)

    # 2. Pool 2 (Abror) mengklasifikasikan list[dict] secara in-memory
    hasil_pool2 = klasifikasi_batch(raw_records)

    # 3. Saat user mengoreksi transaksi di UI (BAIK yang >= 0,72 maupun < 0,72):
    #    otomatis disimpan ke memori feedback + model SVM dilatih ulang agar transaksi serupa
    #    tidak salah klasifikasi di pemanggilan berikutnya.
    json_bersih = terapkan_koreksi(hasil_pool2, {"2": "COMMUNICATION"})

    # Atau jika UI mengirim koreksi satu per satu saat user klik tombol Edit:
    catat_koreksi_tunggal(
        keterangan="TRSF E-BANKING PULSA KANTOR JAN",
        jenis="DB",
        label_baru="COMMUNICATION",
        label_lama="PAYABLE_VENDOR",
        confidence_lama=0.45,
    )

Cara Pemakaian lewat CLI:
-------------------------
    python proses_json.py input.json output.json
    python proses_json.py output.json bersih.json --koreksi koreksi.json
"""
import json
import sys

from feedback_learning import catat_koreksi, latih_ulang_dengan_feedback, peta_memori_koreksi
from kamus_istilah import normalisasi_teks
from kategori_keuangan import LABEL_COA, resolve_erp_target
from routing import klasifikasi_transaksi, load_model

_CACHE_MODEL = None


def _get_model():
    """Load model & threshold sekali saja di memori (singleton) agar cepat saat dipanggil FastAPI."""
    global _CACHE_MODEL
    if _CACHE_MODEL is None:
        _CACHE_MODEL = load_model()
    return _CACHE_MODEL


def refresh_model():
    """Muat ulang model terbaru dari disk ke memori setelah retraining feedback."""
    global _CACHE_MODEL
    _CACHE_MODEL = load_model()
    return _CACHE_MODEL


def _angka(x):
    if x is None:
        return 0.0
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _tentukan_jenis(t):
    """Tentukan arah CR/DB dari output Pool 1 (debit/kredit, tipe C/D, atau jenis CR/DB)."""
    if str(t.get("jenis", "")).upper() in ("CR", "DB"):
        return str(t["jenis"]).upper()
    if str(t.get("tipe", "")).upper() in ("C", "CR"):
        return "CR"
    if str(t.get("tipe", "")).upper() in ("D", "DB"):
        return "DB"
    return "CR" if _angka(t.get("kredit")) > 0 else "DB"


def proses(transaksi, model=None, threshold=None):
    """
    Menerima list[dict] dari Pool 1 (Arya) dan mengembalikan dict hasil klasifikasi Pool 2.
    Memeriksa memori koreksi terlebih dahulu untuk teks persis sama, dan memakai model SVM
    (yang sudah diperbarui dari feedback) untuk seluruh transaksi termasuk transaksi serupa.
    """
    if model is None or threshold is None:
        m_default, t_default = _get_model()
        model = model or m_default
        threshold = t_default if threshold is None else threshold

    memori = peta_memori_koreksi()
    hasil = []
    for i, t in enumerate(transaksi):
        jenis = _tentukan_jenis(t)
        ket = str(t.get("keterangan", ""))
        teks_norm = f"arah{jenis.lower()} " + normalisasi_teks(ket)

        if teks_norm in memori:
            lab = memori[teks_norm]
            h = {
                "label": lab,
                "nama_akun": LABEL_COA[lab]["nama"],
                "confidence": 0.99,
                "status": "OTOMATIS",
                "sumber_label": "feedback_memory",
            }
        else:
            pred = klasifikasi_transaksi(ket, jenis, model, threshold)
            h = {
                "label": pred["label"],
                "nama_akun": pred["nama_akun"],
                "confidence": pred["confidence"],
                "status": "OTOMATIS" if pred["status"] == "OTOMATIS" else "PERLU_REVIEW_MANUAL",
                "sumber_label": "model",
            }

        tanggal = t.get("tanggal") or t.get("waktu_transaksi") or ""
        item = {
            **t,
            "index": i,
            "tanggal": tanggal,
            "waktu_transaksi": t.get("waktu_transaksi") or tanggal,
            "jenis": jenis,
            "label": h["label"],
            "nama_akun": h["nama_akun"],
            "confidence": h["confidence"],
            "sumber_label": h["sumber_label"],
            "status": h["status"],
            "erp_target": resolve_erp_target(h["label"], jenis, ket),
        }
        hasil.append(item)
    return _bungkus(hasil, threshold)


def klasifikasi_batch(transaksi_list, threshold=None):
    """Fungsi utama untuk di-import langsung oleh Backend FastAPI Pool 3 (Mario)."""
    return proses(transaksi_list, threshold=threshold)


def _bungkus(hasil, threshold):
    n_auto = sum(h["status"] == "OTOMATIS" for h in hasil)
    return {
        "threshold": threshold,
        "ringkasan": {
            "total": len(hasil),
            "otomatis": n_auto,
            "perlu_review": len(hasil) - n_auto,
        },
        "transaksi": hasil,
    }


def terapkan_koreksi(paket, koreksi, simpan_feedback=True, latih_ulang=True):
    """
    Menerapkan koreksi manual dari UI Pool 3 ({'index': 'KODE_LABEL'}) menjadi JSON bersih.
    Berlaku untuk SEMUA transaksi yang dikoreksi, baik yang awalnya OTOMATIS (>= 0,72)
    maupun PERLU_REVIEW_MANUAL (< 0,72).
    Jika simpan_feedback=True dan latih_ulang=True, koreksi disimpan dan model langsung
    dilatih ulang agar transaksi serupa di masa depan tidak salah lagi.
    """
    catatan = []
    for h in paket["transaksi"]:
        lab = koreksi.get(str(h["index"]), koreksi.get(h["index"]))
        if lab:
            lab = str(lab).strip().upper()
            if lab not in LABEL_COA:
                raise ValueError(f"label tidak dikenal: {lab}")
            catatan.append({
                "keterangan": h.get("keterangan", ""),
                "jenis": h.get("jenis", "DB"),
                "label_lama": h.get("label", ""),
                "label_baru": lab,
                "confidence_lama": h.get("confidence", 0.0),
                "status_lama": h.get("status", ""),
            })
            h.update(
                label=lab,
                nama_akun=LABEL_COA[lab]["nama"],
                status="OTOMATIS",
                sumber_label="manual",
                erp_target=resolve_erp_target(lab, h.get("jenis", "DB"), h.get("keterangan", "")),
            )

    if simpan_feedback and catatan:
        catat_koreksi(catatan)
        if latih_ulang:
            latih_ulang_dengan_feedback()
            refresh_model()

    return _bungkus(paket["transaksi"], paket["threshold"])


def catat_koreksi_tunggal(keterangan, jenis, label_baru, label_lama="", confidence_lama=0.0,
                          status_lama="", latih_ulang=True):
    """
    Endpoint helper untuk Mario jika UI mengirim koreksi satu transaksi setiap kali user klik Edit
    (baik untuk transaksi auto-match >= 0,72 maupun suggestion < 0,72).
    """
    catat_koreksi([{
        "keterangan": keterangan,
        "jenis": jenis,
        "label_lama": label_lama,
        "label_baru": label_baru,
        "confidence_lama": confidence_lama,
        "status_lama": status_lama,
    }])
    if latih_ulang:
        latih_ulang_dengan_feedback()
        refresh_model()
    return {"status": "learned", "label_baru": str(label_baru).upper()}


def main():
    argv = sys.argv[1:]
    file_koreksi = None
    if "--koreksi" in argv:
        i = argv.index("--koreksi")
        file_koreksi = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 2 or ("--koreksi" in sys.argv and not file_koreksi):
        sys.exit(__doc__)
    src, dst = argv
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    if file_koreksi:
        with open(file_koreksi, encoding="utf-8-sig") as fk:
            koreksi = json.load(fk)
        paket = terapkan_koreksi(data, koreksi)
    else:
        paket = klasifikasi_batch(data)
    with open(dst, "w", encoding="utf-8") as fout:
        json.dump(paket, fout, ensure_ascii=False, indent=2)
    r = paket["ringkasan"]
    print(f"{dst}: total={r['total']} otomatis={r['otomatis']} perlu_review={r['perlu_review']}")


if __name__ == "__main__":
    main()
