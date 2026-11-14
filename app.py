"""Mini App Toko – contoh aplikasi kecil: login, dashboard, CRUD produk, dan download laporan.

Cara menjalankan:
    - Online: unggah app.py, requirements.txt, dan toko.db ke repo GitHub,
      lalu deploy di share.streamlit.io (main file: app.py).
    - Lokal, dari folder materi: streamlit run mini_app/app.py

Akun contoh (dibuat otomatis saat pertama kali dijalankan):
    admin / admin123  -> boleh tambah, ubah, hapus
    staf  / staf123   -> boleh tambah & ubah, tidak boleh hapus
"""
import hashlib
import io
import os
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

FOLDER = Path(__file__).resolve().parent
DB_APP = FOLDER / "toko_app.db"
# toko.db di sebelah app.py (repo GitHub), atau di ../data (folder materi)
DB_SUMBER = next((p for p in [FOLDER / "toko.db", FOLDER.parent / "data" / "toko.db"] if p.exists()),
                 FOLDER / "toko.db")
KATEGORI = ["Minuman", "Makanan", "Kebersihan", "Elektronik"]

st.set_page_config(page_title="Mini App Toko", page_icon="🛒", layout="wide")


# ------------------------------------------------------------------ database
def hash_password(password, salt=None):
    """Password tidak pernah disimpan apa adanya – hanya hasil hash + salt."""
    salt = salt or os.urandom(16).hex()
    hasil = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return salt, hasil


def koneksi():
    return sqlite3.connect(DB_APP)


@st.cache_resource  # cukup sekali per server, walau banyak pengguna membuka aplikasi bersamaan
def siapkan_database():
    if not DB_APP.exists():
        # mulai dari salinan data latihan; salin ke file sementara dulu supaya
        # tidak ada yang sempat membuka file yang baru setengah tersalin
        sementara = DB_APP.with_suffix(".tmp")
        shutil.copy(DB_SUMBER, sementara)
        os.replace(sementara, DB_APP)
    with koneksi() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS pengguna (
                   username TEXT PRIMARY KEY,
                   salt     TEXT NOT NULL,
                   hash     TEXT NOT NULL,
                   peran    TEXT NOT NULL
               )"""
        )
        if con.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0:
            for user, pwd, peran in [("admin", "admin123", "admin"), ("staf", "staf123", "staf")]:
                con.execute("INSERT INTO pengguna VALUES (?, ?, ?, ?)", (user, *hash_password(pwd), peran))


def cek_login(username, password):
    with koneksi() as con:
        baris = con.execute("SELECT salt, hash, peran FROM pengguna WHERE username = ?", (username,)).fetchone()
    if baris is None:
        return None
    salt, hash_tersimpan, peran = baris
    return peran if hash_password(password, salt)[1] == hash_tersimpan else None


def baca(query, params=()):
    with koneksi() as con:
        return pd.read_sql(query, con, params=params)


def jalankan(query, params=()):
    with koneksi() as con:
        return con.execute(query, params).rowcount


def rupiah(x):
    return f"Rp {x:,.0f}".replace(",", ".")


# ------------------------------------------------------------------ halaman
def halaman_login():
    st.title("🛒 Mini App Toko")
    kiri, _ = st.columns([1, 2])
    with kiri, st.form("login"):
        st.subheader("Masuk")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login", type="primary"):
            peran = cek_login(username.strip(), password)
            if peran:
                st.session_state.user = username.strip()
                st.session_state.peran = peran
                st.rerun()
            else:
                st.error("Username atau password salah.")


def halaman_dashboard():
    st.title("📊 Dashboard Penjualan")
    df = baca(
        """SELECT t.tanggal, t.cabang, p.nama_produk, p.kategori, t.qty * t.harga_satuan AS total
           FROM transaksi t JOIN produk p ON p.id_produk = t.id_produk"""
    )
    df["bulan"] = df["tanggal"].str[:7]

    cabang = st.multiselect("Cabang", sorted(df["cabang"].unique()), default=sorted(df["cabang"].unique()))
    df = df[df["cabang"].isin(cabang)]
    if df.empty:
        st.info("Pilih minimal satu cabang.")
        return

    k1, k2, k3 = st.columns(3)
    juta = f"{df['total'].sum() / 1e6:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    k1.metric("Total penjualan", f"Rp {juta} jt")
    k2.metric("Jumlah transaksi", f"{len(df):,}".replace(",", "."))
    k3.metric("Rata-rata / transaksi", rupiah(df["total"].mean()))

    kiri, kanan = st.columns(2)
    per_bulan = df.groupby(["bulan", "cabang"], as_index=False)["total"].sum()
    kiri.plotly_chart(px.line(per_bulan, x="bulan", y="total", color="cabang", markers=True,
                              title="Tren bulanan"), width="stretch")
    per_kategori = df.groupby("kategori", as_index=False)["total"].sum().sort_values("total")
    kanan.plotly_chart(px.bar(per_kategori, x="total", y="kategori", orientation="h",
                              title="Per kategori"), width="stretch")


def halaman_produk():
    st.title("📦 Data Produk")
    cari = st.text_input("Cari nama produk")
    produk = baca("SELECT * FROM produk WHERE nama_produk LIKE ? ORDER BY id_produk", (f"%{cari}%",))
    st.dataframe(produk, hide_index=True, width="stretch")

    tab_tambah, tab_ubah, tab_hapus = st.tabs(["➕ Tambah", "✏️ Ubah", "🗑️ Hapus"])

    # CREATE
    with tab_tambah, st.form("tambah", clear_on_submit=True):
        c1, c2 = st.columns(2)
        id_produk = c1.text_input("ID produk (mis. P020)").strip().upper()
        nama = c2.text_input("Nama produk").strip()
        kategori = c1.selectbox("Kategori", KATEGORI)
        harga = c2.number_input("Harga", min_value=0, step=500)
        stok = c1.number_input("Stok", min_value=0, step=1)
        if st.form_submit_button("Simpan", type="primary"):
            if not id_produk or not nama or harga <= 0:
                st.error("ID, nama, dan harga wajib diisi.")
            elif not baca("SELECT 1 FROM produk WHERE id_produk = ?", (id_produk,)).empty:
                st.error(f"ID {id_produk} sudah dipakai.")
            else:
                jalankan("INSERT INTO produk VALUES (?, ?, ?, ?, ?)",
                         (id_produk, nama, kategori, int(harga), int(stok)))
                st.success(f"Produk {nama} ditambahkan.")
                st.rerun()

    semua = baca("SELECT * FROM produk ORDER BY id_produk")
    pilihan = {f"{r.id_produk} – {r.nama_produk}": r for r in semua.itertuples()}

    # UPDATE
    with tab_ubah:
        label = st.selectbox("Pilih produk", list(pilihan), key="pilih_ubah")
        p = pilihan[label]
        with st.form("ubah"):
            c1, c2 = st.columns(2)
            nama = c1.text_input("Nama produk", p.nama_produk)
            kategori = c2.selectbox("Kategori", KATEGORI, index=KATEGORI.index(p.kategori))
            harga = c1.number_input("Harga", min_value=0, step=500, value=int(p.harga))
            stok = c2.number_input("Stok", min_value=0, step=1, value=int(p.stok))
            if st.form_submit_button("Simpan perubahan", type="primary"):
                jalankan("UPDATE produk SET nama_produk = ?, kategori = ?, harga = ?, stok = ? WHERE id_produk = ?",
                         (nama.strip(), kategori, int(harga), int(stok), p.id_produk))
                st.success("Perubahan disimpan.")
                st.rerun()

    # DELETE
    with tab_hapus:
        if st.session_state.peran != "admin":
            st.warning("Hanya admin yang boleh menghapus produk.")
        else:
            label = st.selectbox("Pilih produk", list(pilihan), key="pilih_hapus")
            p = pilihan[label]
            dipakai = baca("SELECT COUNT(*) AS n FROM transaksi WHERE id_produk = ?", (p.id_produk,))["n"][0]
            if dipakai:
                st.info(f"Produk ini dipakai di {dipakai} transaksi – tidak bisa dihapus.")
            else:
                yakin = st.checkbox(f"Saya yakin menghapus {p.nama_produk}")
                if st.button("Hapus", type="primary", disabled=not yakin):
                    jalankan("DELETE FROM produk WHERE id_produk = ?", (p.id_produk,))
                    st.success("Produk dihapus.")
                    st.rerun()


def halaman_laporan():
    st.title("📄 Laporan")
    df = baca(
        """SELECT t.id_transaksi, t.tanggal, t.cabang, p.nama_produk, p.kategori,
                  t.qty, t.harga_satuan, t.qty * t.harga_satuan AS total
           FROM transaksi t JOIN produk p ON p.id_produk = t.id_produk ORDER BY t.tanggal"""
    )
    bulan = sorted(df["tanggal"].str[:7].unique())
    dari, sampai = st.select_slider("Periode", options=bulan, value=(bulan[0], bulan[-1]))
    df = df[(df["tanggal"].str[:7] >= dari) & (df["tanggal"].str[:7] <= sampai)]
    per_cabang = df.groupby("cabang", as_index=False)["total"].sum().sort_values("total", ascending=False)

    st.dataframe(per_cabang, hide_index=True)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        per_cabang.to_excel(writer, sheet_name="Per Cabang", index=False)
        df.to_excel(writer, sheet_name="Data", index=False)
    st.download_button("⬇️ Download Excel", buffer.getvalue(), file_name=f"laporan_{dari}_{sampai}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), file_name=f"transaksi_{dari}_{sampai}.csv",
                       mime="text/csv")


# ------------------------------------------------------------------ main
siapkan_database()

if "user" not in st.session_state:
    halaman_login()
else:
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user}** ({st.session_state.peran})")
        menu = st.radio("Menu", ["Dashboard", "Produk", "Laporan"])
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()
    {"Dashboard": halaman_dashboard, "Produk": halaman_produk, "Laporan": halaman_laporan}[menu]()
