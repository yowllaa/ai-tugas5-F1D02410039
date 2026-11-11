import argparse
import json
import os
import sys

BERKAS_BAWAAN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "kb_padi.json"
)


# ---------------------------------------------------------------------------
# Basis pengetahuan
# ---------------------------------------------------------------------------

def muat_kb(jalur):
    """Baca file aturan lalu periksa bentuknya."""
    try:
        with open(jalur, encoding="utf-8") as f:
            kb = json.load(f)
    except (OSError, json.JSONDecodeError) as galat:
        sys.exit(f"Gagal membaca file aturan '{jalur}': {galat}")
    periksa_kb(kb)
    return kb


def periksa_kb(kb):
    """Hentikan program dengan pesan jelas bila file aturan tidak lengkap."""
    for kunci in ("judul", "batas", "sumber", "fakta", "aturan"):
        if kunci not in kb:
            sys.exit(f"File aturan tidak memuat kunci '{kunci}'.")
    for r in kb["aturan"]:
        for kunci in ("id", "jika", "mode", "maka", "sumber"):
            if kunci not in r:
                sys.exit(f"Aturan {r.get('id', '?')} tidak memuat kunci '{kunci}'.")
        if r["mode"] not in ("dan", "atau"):
            sys.exit(f"Aturan {r['id']}: mode harus 'dan' atau 'atau'.")
        for s in r["sumber"]:
            if s not in kb["sumber"]:
                sys.exit(f"Aturan {r['id']} menunjuk sumber {s} yang tidak terdaftar.")
    for fakta in fakta_dasar(kb):
        if fakta not in kb["fakta"]:
            sys.exit(f"Fakta dasar '{fakta}' belum punya kalimat pertanyaan.")


def fakta_dasar(kb):
    """Fakta yang tidak pernah menjadi hasil aturan; inilah yang ditanyakan."""
    hasil_aturan = {r["maka"] for r in kb["aturan"]}
    urut = []
    for r in kb["aturan"]:
        for syarat in r["jika"]:
            if syarat not in hasil_aturan and syarat not in urut:
                urut.append(syarat)
    return urut


# ---------------------------------------------------------------------------
# Input dari pengguna
# ---------------------------------------------------------------------------

def tanya_pengguna(kb, dasar):
    """Mode tanya-jawab. Mengembalikan daftar fakta yang dijawab 'ya'."""
    print("Jawab y/t.")
    ya = []
    for no, fakta in enumerate(dasar, 1):
        while True:
            try:
                jawab = input(f"{no}. {kb['fakta'][fakta]} (y/t) > ").strip().lower()
            except EOFError:
                sys.exit("\nInput berakhir sebelum semua pertanyaan terjawab.")
            if not sys.stdin.isatty():
                print(jawab)  # supaya jawaban ikut terlihat bila input dialirkan
            if jawab in ("y", "ya"):
                ya.append(fakta)
                break
            if jawab in ("t", "tidak"):
                break
            print("   Jawab dengan y atau t.")
    return ya


def dari_argumen(dasar, teks):
    """Mode langsung: '--ya 2,3' berarti pertanyaan nomor 2 dan 3 dijawab ya."""
    ya = []
    for potong in teks.split(","):
        potong = potong.strip()
        if not potong.isdigit():
            sys.exit(f"Nomor pertanyaan tidak valid: '{potong}'.")
        nomor = int(potong)
        if nomor == 0:
            continue
        if not 1 <= nomor <= len(dasar):
            sys.exit(f"Nomor pertanyaan harus 1 sampai {len(dasar)} (atau 0).")
        if dasar[nomor - 1] not in ya:
            ya.append(dasar[nomor - 1])
    return ya


def terapkan_konsistensi(kb, ya):
    """Bila syarat yang lebih ketat 'ya' tetapi yang lebih longgar 'tidak',
    syarat longgar ikut dianggap 'ya'. Opsional: dibaca dari kunci 'konsistensi'
    di file aturan. Mengembalikan catatan perubahan."""
    catatan = []
    for ketat, longgar in kb.get("konsistensi", []):
        if ketat in ya and longgar not in ya:
            ya.append(longgar)
            catatan.append(f"'{ketat}' berarti '{longgar}' juga berlaku")
    return catatan


# ---------------------------------------------------------------------------
# Mesin inferensi (forward chaining)
# ---------------------------------------------------------------------------

def terpenuhi(aturan, memori):
    """mode 'dan': semua syarat ada di memori; mode 'atau': salah satu cukup."""
    ada = [s in memori for s in aturan["jika"]]
    return all(ada) if aturan["mode"] == "dan" else any(ada)


def forward_chaining(kb, fakta_awal):
    """
    memori <- fakta awal
    ULANGI:
        cocok <- aturan yang syaratnya terpenuhi DAN hasilnya belum ada di memori
        JIKA cocok kosong: BERHENTI
        ambil aturan pertama, tambahkan hasilnya ke memori,
        catat asalnya beserta syarat yang dipakai (bahan "alasan")
    """
    memori = set(fakta_awal)
    asal = {}   # hasil -> (aturan, syarat yang dipakai saat aturan dijalankan)
    log = []    # urutan aturan yang dijalankan
    while True:
        cocok = [
            r for r in kb["aturan"]
            if r["maka"] not in memori and terpenuhi(r, memori)
        ]
        if not cocok:
            break
        r = cocok[0]
        pakai = [s for s in r["jika"] if s in memori]
        memori.add(r["maka"])
        asal[r["maka"]] = (r, pakai)
        log.append((r, pakai))
    return memori, asal, log


def kesimpulan_akhir(asal, log):
    """Hasil aturan yang tidak dipakai sebagai syarat oleh aturan lain
    yang dijalankan."""
    dipakai = {s for _, pakai in log for s in pakai}
    return [f for f in asal if f not in dipakai]


# ---------------------------------------------------------------------------
# Tampilan
# ---------------------------------------------------------------------------

def cetak_alasan(fakta, asal, tingkat=1):
    """Telusuri mundur dari kesimpulan sampai ke fakta awal."""
    r, pakai = asal[fakta]
    rujukan = ", ".join(r["sumber"])
    print("  " * tingkat + f"{fakta}  <- {r['id']} ({', '.join(pakai)}) [{rujukan}]")
    for s in pakai:
        if s in asal:
            cetak_alasan(s, asal, tingkat + 1)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description="Sistem pakar forward chaining.")
    ap.add_argument("--kb", default=BERKAS_BAWAAN, help="file aturan JSON")
    ap.add_argument(
        "--ya",
        help="nomor pertanyaan yang dijawab ya (pisah koma), 0 = semua tidak; "
             "tanpa opsi ini program bertanya satu per satu",
    )
    arg = ap.parse_args()

    kb = muat_kb(arg.kb)
    dasar = fakta_dasar(kb)

    print(kb["judul"])
    if arg.ya is None:
        ya = tanya_pengguna(kb, dasar)
    else:
        for no, fakta in enumerate(dasar, 1):
            print(f"{no}. {kb['fakta'][fakta]}")
        ya = dari_argumen(dasar, arg.ya)

    catatan = terapkan_konsistensi(kb, ya)

    print()
    print("Fakta awal: " + (", ".join(ya) if ya else "(tidak ada)"))
    for c in catatan:
        print(f"  (otomatis: {c})")
    print()

    memori, asal, log = forward_chaining(kb, ya)

    for siklus, (r, _) in enumerate(log, 1):
        print(f"Siklus {siklus}: {r['id']} -> {r['maka']}")
    print(f"Siklus {len(log) + 1}: tidak ada aturan baru, berhenti")
    print()

    akhir = kesimpulan_akhir(asal, log)
    sumber_dipakai = set()

    if not akhir:
        print("Kesimpulan: tidak ada kesimpulan yang dapat ditarik dari fakta tersebut.")
        print("Aturan yang tersedia hanya mencakup kondisi yang tercantum pada catatan di bawah.")
    else:
        for no, fakta in enumerate(akhir, 1):
            judul = "Kesimpulan" if len(akhir) == 1 else f"Kesimpulan {no}"
            print(f"{judul}: {fakta}")
            print("Alasan:")
            cetak_alasan(fakta, asal)
            saran = kb.get("saran", {}).get(fakta)
            if saran:
                print(f"Saran: {saran}")
            print()
        for r, _ in log:
            sumber_dipakai.update(r["sumber"])

    if sumber_dipakai:
        pendek = kb.get("nama_pendek", {})
        print("Sumber yang dipakai:")
        for s in sorted(sumber_dipakai):
            print(f"  {s}: {pendek.get(s, kb['sumber'][s])}")
        print()

    print(f"Catatan: {kb['batas']}")


if __name__ == "__main__":
    main()
