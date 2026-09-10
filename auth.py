"""
auth.py — Modul autentikasi & manajemen akses untuk IDX Stock Analyzer Pro.

Menyimpan data pengguna di file JSON lokal (users.json), di folder yang sama dengan
app.py. Password TIDAK pernah disimpan dalam bentuk plaintext — disimpan sebagai
hash PBKDF2-HMAC-SHA256 dengan salt acak per pengguna.

Fitur:
- authenticate(username, password)      -> verifikasi login
- add_user / delete_user / set_admin    -> dikelola dari tab Admin di app.py
- reset_password / change_own_password  -> ganti password
- list_users                            -> untuk ditampilkan di tab Admin

CATATAN PENTING (Streamlit Community Cloud):
Filesystem di Streamlit Community Cloud bersifat *ephemeral* — file users.json bisa
ter-reset saat aplikasi di-redeploy / repo di-push ulang / container restart. Untuk
kebutuhan produksi jangka panjang, pertimbangkan memindahkan penyimpanan pengguna ke
database eksternal (mis. Supabase, Postgres, atau Google Sheets API). Untuk deployment
lokal / server sendiri dengan disk persisten, pendekatan file JSON ini sudah cukup aman
dan sederhana.

Admin awal (default) dibuat otomatis saat users.json belum ada, dengan kredensial dari
st.secrets / environment variable ADMIN_USERNAME & ADMIN_PASSWORD (fallback: admin/admin123).
Admin default WAJIB segera mengganti password setelah login pertama.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover - auth.py tetap bisa di-import tanpa streamlit
    st = None

USERS_FILE = Path(__file__).parent / "users.json"
PBKDF2_ITERATIONS = 260_000


# ================================================================
# HASHING PASSWORD
# ================================================================

def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def _verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    dk_hex, _ = _hash_password(password, salt)
    return hmac.compare_digest(dk_hex, hash_hex)


def _default_admin_credentials() -> tuple[str, str]:
    username, password = "admin", "admin123"
    if st is not None:
        try:
            username = st.secrets.get("ADMIN_USERNAME", username)
            password = st.secrets.get("ADMIN_PASSWORD", password)
        except Exception:
            pass
    username = os.environ.get("ADMIN_USERNAME", username)
    password = os.environ.get("ADMIN_PASSWORD", password)
    return username, password


def _seed_default_admin() -> dict:
    username, password = _default_admin_credentials()
    pw_hash, salt = _hash_password(password)
    return {
        username: {
            "password_hash": pw_hash,
            "salt": salt,
            "is_admin": True,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "created_by": "system",
            "must_change_password": True,
        }
    }


# ================================================================
# PENYIMPANAN (users.json)
# ================================================================

def load_users() -> dict:
    if not USERS_FILE.exists():
        users = _seed_default_admin()
        save_users(users)
        return users
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        if not users:
            users = _seed_default_admin()
            save_users(users)
        return users
    except (json.JSONDecodeError, OSError):
        users = _seed_default_admin()
        save_users(users)
        return users


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


# ================================================================
# AUTENTIKASI
# ================================================================

def authenticate(username: str, password: str) -> dict | None:
    if not username or not password:
        return None
    users = load_users()
    user = users.get(username)
    if not user:
        return None
    if _verify_password(password, user["password_hash"], user["salt"]):
        return {
            "username": username,
            "is_admin": bool(user.get("is_admin", False)),
            "must_change_password": bool(user.get("must_change_password", False)),
        }
    return None


# ================================================================
# MANAJEMEN PENGGUNA (dipakai oleh tab Admin)
# ================================================================

def add_user(username: str, password: str, is_admin: bool = False, created_by: str = "") -> tuple[bool, str]:
    username = (username or "").strip()
    if not username or not password:
        return False, "Username dan password wajib diisi."
    if len(password) < 6:
        return False, "Password minimal 6 karakter."
    users = load_users()
    if username in users:
        return False, f"Username '{username}' sudah terdaftar."
    pw_hash, salt = _hash_password(password)
    users[username] = {
        "password_hash": pw_hash,
        "salt": salt,
        "is_admin": bool(is_admin),
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "created_by": created_by,
        "must_change_password": False,
    }
    save_users(users)
    return True, f"✅ Pengguna '{username}' berhasil ditambahkan."


def delete_user(username: str, requesting_user: str) -> tuple[bool, str]:
    users = load_users()
    if username not in users:
        return False, "Pengguna tidak ditemukan."
    if username == requesting_user:
        return False, "Tidak bisa menghapus akun Anda sendiri saat sedang login."
    admins = [u for u, d in users.items() if d.get("is_admin")]
    if users[username].get("is_admin") and len(admins) <= 1:
        return False, "Tidak bisa menghapus admin terakhir — tunjuk admin lain terlebih dahulu."
    del users[username]
    save_users(users)
    return True, f"🗑️ Pengguna '{username}' berhasil dihapus."


def set_admin(username: str, is_admin: bool) -> tuple[bool, str]:
    users = load_users()
    if username not in users:
        return False, "Pengguna tidak ditemukan."
    admins = [u for u, d in users.items() if d.get("is_admin")]
    if not is_admin and users[username].get("is_admin") and len(admins) <= 1:
        return False, "Tidak bisa mencabut hak admin dari admin terakhir."
    users[username]["is_admin"] = bool(is_admin)
    save_users(users)
    return True, "✅ Peran pengguna berhasil diperbarui."


def reset_password(username: str, new_password: str) -> tuple[bool, str]:
    if len(new_password or "") < 6:
        return False, "Password minimal 6 karakter."
    users = load_users()
    if username not in users:
        return False, "Pengguna tidak ditemukan."
    pw_hash, salt = _hash_password(new_password)
    users[username]["password_hash"] = pw_hash
    users[username]["salt"] = salt
    users[username]["must_change_password"] = False
    save_users(users)
    return True, "✅ Password berhasil direset."


def change_own_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    if not authenticate(username, old_password):
        return False, "Password lama salah."
    return reset_password(username, new_password)


def list_users() -> list[dict]:
    users = load_users()
    return [
        {
            "Username": u,
            "Role": "👑 Admin" if d.get("is_admin") else "User",
            "Dibuat": d.get("created_at", "?"),
            "Dibuat oleh": d.get("created_by", "?") or "system",
        }
        for u, d in users.items()
    ]
