from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import json
import os
import subprocess
import random
import string
import uuid
from datetime import datetime, timedelta
import sys
import shutil
import threading
import time
import zipfile
import psutil
import hashlib
import secrets
import re
import socket
import signal

# ✅ IS_WINDOWS সবার আগে
IS_WINDOWS = sys.platform == 'win32'

app = Flask(__name__)

# ============================================
# Config
# ============================================
app.secret_key = os.environ.get('SECRET_KEY', 'alamin-hosting-CHANGE-ME-IN-PRODUCTION')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_DEBUG', '0') != '1'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ============================================
# Paths
# ============================================
if os.path.exists('/data') and os.access('/data', os.W_OK):
    DATA_DIR = os.environ.get('DATA_DIR', '/data')
else:
    DATA_DIR = os.environ.get('DATA_DIR', os.path.abspath('.'))

os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
BOTS_DIR = os.path.join(DATA_DIR, 'bots')
CPU_HISTORY = {}
CRASH_COUNT = {}

os.makedirs(BOTS_DIR, exist_ok=True)

# FILE SERVER
if os.path.exists('/data') and os.access('/data', os.W_OK):
    FILE_SERVER_ROOT = os.path.join('/data', 'FILE------SERVER')
else:
    FILE_SERVER_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'FILE------SERVER')

FILE_CODE_ROOT = os.path.join(FILE_SERVER_ROOT, 'FILE------CODE')
ALL_JSON_PATH = os.path.join(FILE_CODE_ROOT, 'ALL.json')

os.makedirs(FILE_SERVER_ROOT, exist_ok=True)
os.makedirs(FILE_CODE_ROOT, exist_ok=True)

# HTML SERVER
if os.path.exists('/data') and os.access('/data', os.W_OK):
    HTML_SERVER_ROOT = os.path.join('/data', 'HTML------SERVER')
else:
    HTML_SERVER_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'HTML------SERVER')

HTML_CODE_ROOT = os.path.join(HTML_SERVER_ROOT, 'HTML------CODE')
HTML_ALL_JSON_PATH = os.path.join(HTML_CODE_ROOT, 'ALL.json')

os.makedirs(HTML_SERVER_ROOT, exist_ok=True)
os.makedirs(HTML_CODE_ROOT, exist_ok=True)

# HTML SITES
if os.path.exists('/data') and os.access('/data', os.W_OK):
    HTML_SITES_ROOT = os.path.join('/data', 'HTML_SITES')
else:
    HTML_SITES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'HTML_SITES')

os.makedirs(HTML_SITES_ROOT, exist_ok=True)

# ✅ API SERVER — Termux হোমে (symlink কাজ করার জন্য)
if IS_WINDOWS:
    API_SERVER_ROOT = os.path.join(DATA_DIR, 'API_SERVER')
else:
    _home = os.path.expanduser('~')
    API_SERVER_ROOT = os.path.join(_home, '.alamin_api_server')
    # পুরনো shared storage-এর ডেটা থাকলে সরান
    _old_root = os.path.join(DATA_DIR, 'API_SERVER')
    if os.path.exists(_old_root) and not os.path.exists(API_SERVER_ROOT):
        try:
            shutil.copytree(_old_root, API_SERVER_ROOT)
            print(f"📦 API ডেটা সরানো: {_old_root} → {API_SERVER_ROOT}")
        except Exception as e:
            print(f"⚠️ কপি ব্যর্থ: {e}")

os.makedirs(API_SERVER_ROOT, exist_ok=True)
API_APPS_DIR = os.path.join(API_SERVER_ROOT, 'apps')
os.makedirs(API_APPS_DIR, exist_ok=True)

API_PROCESSES = {}
API_PORT_START = 8000
API_PORT_END = 9000


# ============================================
# ✅ API BACKUP SYSTEM
# ============================================
API_BACKUP_ROOT = os.path.join(DATA_DIR, 'API------SERVER')
API_BACKUP_CODE = os.path.join(API_BACKUP_ROOT, 'API------CODE')
API_ALL_JSON_PATH = os.path.join(API_BACKUP_CODE, 'ALL.json')

os.makedirs(API_BACKUP_ROOT, exist_ok=True)
os.makedirs(API_BACKUP_CODE, exist_ok=True)

_api_all_json_lock = threading.Lock()


def load_api_all_json():
    """API backup রেকর্ড পড়া"""
    if os.path.exists(API_ALL_JSON_PATH):
        try:
            with open(API_ALL_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'backups' in data:
                return data
        except Exception:
            pass
    return {'total_backups': 0, 'last_updated': '', 'backups': {}}


def save_api_all_json(data):
    """API backup রেকর্ড সেভ"""
    with _api_all_json_lock:
        data['total_backups'] = len(data.get('backups', {}))
        data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(API_ALL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)


def create_api_zip(app_id):
    """অ্যাপের সম্পূর্ণ ফোল্ডার ZIP backup তৈরি"""
    app_data, uname, _ = get_api_app_by_id(app_id)
    if not app_data:
        return None, "App not found"

    app_dir = get_api_app_dir(app_id)
    zip_path = os.path.join(API_BACKUP_ROOT, f"{app_id}.zip")

    SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'venv', 'env', '.venv'}
    SKIP_FILES = set()

    try:
        files_count = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, fls in os.walk(app_dir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fl in fls:
                    if fl in SKIP_FILES:
                        continue
                    full = os.path.join(root, fl)
                    rel = os.path.relpath(full, app_dir)
                    try:
                        zf.write(full, rel)
                        files_count += 1
                    except Exception:
                        pass

        zip_size_bytes = os.path.getsize(zip_path)

        all_data = load_api_all_json()
        existing = all_data['backups'].get(app_id, {})
        update_count = existing.get('update_count', 0) + 1
        created_at = existing.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        all_data['backups'][app_id] = {
            'app_id': app_id,
            'app_name': app_data.get('name', 'unknown'),
            'owner_username': uname or 'unknown',
            'language': app_data.get('language', 'node'),
            'zip_name': f"{app_id}.zip",
            'zip_size': format_bytes(zip_size_bytes / 1024),
            'zip_size_bytes': zip_size_bytes,
            'files_count': files_count,
            'created_at': created_at,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'update_count': update_count,
        }
        save_api_all_json(all_data)

        return zip_path, None

    except Exception as e:
        print(f"⚠️ create_api_zip error: {e}")
        return None, str(e)


def update_api_zip(app_id):
    """পুরনো ZIP-এ নতুন ফাইল merge"""
    app_dir = get_api_app_dir(app_id)
    zip_path = os.path.join(API_BACKUP_ROOT, f"{app_id}.zip")

    if not os.path.exists(zip_path):
        return create_api_zip(app_id)

    SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'venv', 'env', '.venv'}
    SKIP_FILES = set()

    folder_files = {}
    for root, dirs, fls in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fl in fls:
            if fl in SKIP_FILES:
                continue
            full = os.path.join(root, fl)
            rel = os.path.relpath(full, app_dir).replace('\\', '/')
            folder_files[rel] = full

    old_entries = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.filename.endswith('/'):
                    continue
                old_entries[info.filename] = zf.read(info.filename)
    except Exception:
        old_entries = {}

    merged = dict(old_entries)
    merged.update(folder_files)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, source in merged.items():
                try:
                    if isinstance(source, bytes):
                        zf.writestr(name, source)
                    else:
                        zf.write(source, name)
                except Exception:
                    pass

        zip_size_bytes = os.path.getsize(zip_path)

        app_data, uname, _ = get_api_app_by_id(app_id)
        all_data = load_api_all_json()
        existing = all_data['backups'].get(app_id, {})
        update_count = existing.get('update_count', 0) + 1
        created_at = existing.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        all_data['backups'][app_id] = {
            'app_id': app_id,
            'app_name': app_data.get('name', 'unknown') if app_data else 'unknown',
            'owner_username': uname or 'unknown',
            'language': app_data.get('language', 'node') if app_data else 'node',
            'zip_name': f"{app_id}.zip",
            'zip_size': format_bytes(zip_size_bytes / 1024),
            'zip_size_bytes': zip_size_bytes,
            'files_count': len(merged),
            'created_at': created_at,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'update_count': update_count,
        }
        save_api_all_json(all_data)

        return zip_path, None

    except Exception as e:
        print(f"⚠️ update_api_zip error: {e}")
        return None, str(e)


# Global Python
GLOBAL_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common_env', 'bin', 'python')
if not os.path.exists(GLOBAL_PYTHON):
    GLOBAL_PYTHON = sys.executable
    print(f"⚠️  common_env নেই! System Python: {sys.executable}")
else:
    print(f"✅ Global Python: {GLOBAL_PYTHON}")

DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'mdalaminmmmnnn037@gmail.com')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'ALAMIN@DD')

_users_lock = threading.Lock()
_html_all_json_lock = threading.Lock()


# ============================================
# Password
# ============================================
def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password, stored):
    if not stored:
        return False
    if '$' not in stored:
        return password == stored
    try:
        salt, hashed = stored.split('$', 1)
        check = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return check == hashed
    except Exception:
        return False


# ============================================
# Helpers
# ============================================
def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


def is_valid_site_name(name):
    if not name or len(name) < 3 or len(name) > 30:
        return False
    return bool(re.match(r'^[a-z][a-z0-9_-]*$', name))


def get_file_type(filename):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    type_map = {
        'py': 'python', 'js': 'javascript', 'json': 'json', 'txt': 'text',
        'html': 'html', 'css': 'css', 'zip': 'archive', 'env': 'config',
        'md': 'markdown', 'yml': 'yaml', 'yaml': 'yaml', 'sh': 'shell',
        'sql': 'sql', 'xml': 'xml', 'png': 'image', 'jpg': 'image',
        'jpeg': 'image', 'gif': 'image', 'svg': 'image', 'webp': 'image',
    }
    return type_map.get(ext, 'other')


def format_bytes(kb):
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


def load_users():
    if not os.path.exists(USERS_FILE):
        default = {
            "admin": {
                "email": DEFAULT_ADMIN_EMAIL,
                "password": hash_password(DEFAULT_ADMIN_PASSWORD),
                "role": "admin"
            }
        }
        save_users(default)
        return default
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

    if 'admin' not in data:
        data['admin'] = {
            "email": DEFAULT_ADMIN_EMAIL,
            "password": hash_password(DEFAULT_ADMIN_PASSWORD),
            "role": "admin"
        }
        save_users(data)
    else:
        if 'email' not in data['admin']:
            data['admin']['email'] = DEFAULT_ADMIN_EMAIL
            save_users(data)

    return data


def save_users(data):
    with _users_lock:
        tmp = USERS_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, USERS_FILE)


# ============================================
# HTML ALL.json helpers
# ============================================
def load_html_all_json():
    if os.path.exists(HTML_ALL_JSON_PATH):
        try:
            with open(HTML_ALL_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'sites' in data:
                return data
        except Exception:
            pass
    return {'total_sites': 0, 'last_updated': '', 'sites': {}}


def save_html_all_json(data):
    with _html_all_json_lock:
        data['total_sites'] = len(data.get('sites', {}))
        data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(HTML_ALL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)


# ============================================
# ZIP Merge Helper
# ============================================
def merge_zip_with_folder(zip_path, folder_path):
    folder_files = {}
    for root, dirs, fls in os.walk(folder_path):
        for fl in fls:
            full_path = os.path.join(root, fl)
            rel_path = os.path.relpath(full_path, folder_path).replace('\\', '/')
            folder_files[rel_path] = full_path

    if os.path.exists(zip_path):
        old_entries = {}
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for info in zf.infolist():
                    if info.filename.endswith('/'):
                        continue
                    old_entries[info.filename] = zf.read(info.filename)
        except Exception as e:
            print(f"ZIP read error: {e}")
            old_entries = {}

        merged = dict(old_entries)
        merged.update(folder_files)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for arcname, source in merged.items():
                try:
                    if isinstance(source, bytes):
                        zf.writestr(arcname, source)
                    else:
                        zf.write(source, arcname)
                except Exception as e:
                    print(f"ZIP merge error for {arcname}: {e}")
    else:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for arcname, source in folder_files.items():
                try:
                    zf.write(source, arcname)
                except Exception as e:
                    print(f"ZIP write error for {arcname}: {e}")


# ============================================
# Rate Limiter
# ============================================
class RateLimiter:
    def check_rate(self, server_id, limit_percent):
        if server_id not in CPU_HISTORY:
            CPU_HISTORY[server_id] = []
        users = load_users()
        server = None
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    server = s
                    break
        if not server or server.get('status') != 'running':
            return False, 0
        pid = server.get('pid')
        if not pid:
            return False, 0
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=1)
            now = time.time()
            CPU_HISTORY[server_id].append({'time': now, 'cpu': cpu})
            CPU_HISTORY[server_id] = [h for h in CPU_HISTORY[server_id] if now - h['time'] < 30]
            recent = [h['cpu'] for h in CPU_HISTORY[server_id] if now - h['time'] < 10]
            if recent:
                avg_cpu = sum(recent) / len(recent)
                if avg_cpu > limit_percent:
                    return True, avg_cpu
        except Exception:
            pass
        return False, 0


rate_limiter = RateLimiter()


def should_auto_restart(server_id):
    if server_id not in CRASH_COUNT:
        CRASH_COUNT[server_id] = {'count': 0, 'last_crash': time.time()}
    crash_info = CRASH_COUNT[server_id]
    if time.time() - crash_info['last_crash'] < 60:
        if crash_info['count'] >= 3:
            return False
    else:
        crash_info['count'] = 0
    crash_info['count'] += 1
    crash_info['last_crash'] = time.time()
    return True


# ============================================
# File Server Helpers
# ============================================
def get_server_dir(server_id):
    server_dir = os.path.join(BOTS_DIR, server_id)
    os.makedirs(server_dir, exist_ok=True)
    return server_dir


def get_server_by_id(server_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                return s, uname
    return None, None


def create_default_files(server_dir):
    main_py = os.path.join(server_dir, 'main.py')
    if not os.path.exists(main_py):
        with open(main_py, 'w', encoding='utf-8') as f:
            f.write('''# ALAMIN HOSTING - Default Bot
import time

print("=" * 40)
print("Bot is running on ALAMIN HOSTING")
print("Server is ready!")
print("=" * 40)

counter = 0
while True:
    counter += 1
    print(f"[{time.strftime('%H:%M:%S')}] Heartbeat #{counter} | Server active")
    time.sleep(10)
''')

    req_file = os.path.join(server_dir, 'requirements.txt')
    if not os.path.exists(req_file):
        with open(req_file, 'w', encoding='utf-8') as f:
            f.write('# ALAMIN HOSTING - Add extra packages here\n')


def load_all_json():
    if os.path.exists(ALL_JSON_PATH):
        try:
            with open(ALL_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'uploads' in data:
                return data
        except Exception:
            pass
    return {'total_uploads': 0, 'last_updated': '', 'uploads': []}


def save_all_json(data):
    data['total_uploads'] = len(data.get('uploads', []))
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(ALL_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ============================================
# Bot Runner
# ============================================
def run_bot(server_id, main_file='main.py', requirements_file='requirements.txt'):
    server_dir = get_server_dir(server_id)
    main_path = os.path.join(server_dir, main_file)
    log_file = os.path.join(server_dir, 'output.log')
    python_exe = GLOBAL_PYTHON

    def log(msg):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")
                f.flush()
        except Exception:
            pass

    if not os.path.exists(main_path):
        return None, f"ERROR: {main_file} not found!"

    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            open(log_file, 'w').close()

    ts = lambda: datetime.now().strftime('%I:%M:%S %p')

    server, _ = get_server_by_id(server_id)
    cpu_limit = server.get('cpu_limit', 80) if server else 80
    log(f"[{ts()}] Rate limit: {cpu_limit}%")
    log("")

    if requirements_file and requirements_file.strip():
        req_path = os.path.join(server_dir, requirements_file.strip())
        if os.path.exists(req_path):
            with open(req_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
            if lines:
                log(f"[{ts()}] Installing custom requirements...")
                try:
                    proc = subprocess.Popen(
                        [python_exe, '-m', 'pip', 'install', '-r', os.path.abspath(req_path), '--disable-pip-version-check', '--quiet'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, universal_newlines=True
                    )
                    for line in iter(proc.stdout.readline, ''):
                        if line.strip():
                            log(f"[{ts()}] {line.rstrip()}")
                    proc.wait()
                    log("")
                except Exception as e:
                    log(f"[{ts()}] pip error: {str(e)}")
            else:
                log(f"[{ts()}] Using global pre-installed packages ✅")
        else:
            log(f"[{ts()}] Using global pre-installed packages ✅")
    else:
        log(f"[{ts()}] Using global pre-installed packages ✅")

    log("")
    log(f"[{ts()}] Run: python {main_file}")
    log("")

    try:
        main_path_abs = os.path.abspath(main_path)
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'

        proc = subprocess.Popen(
            [python_exe, main_path_abs],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=server_dir, text=True, encoding='utf-8', errors='replace',
            bufsize=1, env=env, universal_newlines=True
        )

        log(f"[{ts()}] Server marked as running")
        log(f"[{ts()}] PID: {proc.pid}")
        log("")

        def rate_monitor():
            while proc.poll() is None:
                time.sleep(5)
                exceeded, avg_cpu = rate_limiter.check_rate(server_id, cpu_limit)
                if exceeded:
                    log(f"[{datetime.now().strftime('%I:%M:%S %p')}] CPU Limit! {avg_cpu:.1f}% > {cpu_limit}%")
                    proc.terminate()
                    time.sleep(2)
                    if proc.poll() is None:
                        proc.kill()
                    users = load_users()
                    for uname, data in users.items():
                        if uname == 'admin':
                            continue
                        servers = data.get('servers', [])
                        if not isinstance(servers, list):
                            continue
                        for s in servers:
                            if isinstance(s, dict) and s.get('server_id') == server_id:
                                s['status'] = 'stopped'
                                s['pid'] = None
                                s['rate_limit_exceeded'] = True
                                s['stopped_by_user'] = False
                                save_users(users)
                                break
                    break

        threading.Thread(target=rate_monitor, daemon=True).start()

        def stream_output():
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            line = line.rstrip('\n\r')
                            if line:
                                f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {line}\n")
                                f.flush()
            except Exception:
                pass

        threading.Thread(target=stream_output, daemon=True).start()

        return proc.pid, None
    except Exception as e:
        log(f"[{ts()}] Error: {str(e)}")
        return None, str(e)


def stop_bot_process(pid):
    try:
        if IS_WINDOWS:
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
        else:
            os.kill(pid, 15)
            time.sleep(1)
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        return True
    except Exception:
        return False


def monitor_bot(server_id, pid):
    while True:
        try:
            if IS_WINDOWS:
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                if str(pid) not in result.stdout:
                    break
            else:
                try:
                    os.kill(pid, 0)
                except Exception:
                    break
        except Exception:
            break
        time.sleep(5)

    server, _ = get_server_by_id(server_id)
    if not server:
        return
    if server.get('stopped_by_user') or server.get('rate_limit_exceeded') or server.get('is_locked'):
        return

    if should_auto_restart(server_id):
        time.sleep(3)
        new_pid, error = run_bot(server_id, server.get('main_file', 'main.py'),
                                 server.get('requirements_file', 'requirements.txt'))
        if new_pid:
            users = load_users()
            for uname, data in users.items():
                if uname == 'admin':
                    continue
                servers = data.get('servers', [])
                if not isinstance(servers, list):
                    continue
                for s in servers:
                    if isinstance(s, dict) and s.get('server_id') == server_id:
                        s['status'] = 'running'
                        s['pid'] = new_pid
                        s['started_at'] = str(datetime.now())
                        s['rate_limit_exceeded'] = False
                        s['stopped_by_user'] = False
                        save_users(users)
                        break
            threading.Thread(target=monitor_bot, args=(server_id, new_pid), daemon=True).start()
    else:
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'stopped'
                    s['pid'] = None
                    save_users(users)
                    return


def get_process_stats(pid):
    try:
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=0.5)
        mem = proc.memory_info()
        ram = mem.rss / (1024 * 1024)
        return {
            'cpu_percent': round(cpu, 1),
            'ram_mb': round(ram, 1),
            'ram_display': f"{ram:.1f} MB" if ram < 1024 else f"{ram/1024:.1f} GB",
        }
    except Exception:
        return {'cpu_percent': 0, 'ram_mb': 0, 'ram_display': '0 MB'}


def get_network_stats(psutil_pid):
    try:
        proc = psutil.Process(psutil_pid)
        io = proc.io_counters()
        if io:
            return format_bytes(io.read_bytes / 1024), format_bytes(io.write_bytes / 1024)
    except Exception:
        pass
    return "0 KB", "0 KB"


# ============================================
# ✅ API HOSTING — Core Functions
# ============================================
def get_free_port():
    used = set()
    users = load_users()
    for uname, data in users.items():
        for app in data.get('api_apps', []):
            if isinstance(app, dict) and app.get('port'):
                used.add(app['port'])
    for p in range(API_PORT_START, API_PORT_END):
        if p not in used:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(('0.0.0.0', p))
                s.close()
                return p
            except OSError:
                continue
    return None


def get_api_app_dir(app_id):
    d = os.path.join(API_APPS_DIR, app_id)
    os.makedirs(d, exist_ok=True)
    return d


def get_api_app_by_id(app_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for app in data.get('api_apps', []):
            if isinstance(app, dict) and app.get('app_id') == app_id:
                return app, uname, data
    return None, None, None


def is_port_in_use(port):
    """চেক করুন পোর্ট সত্যিই ব্যবহৃত হচ্ছে কিনা"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result == 0
    except Exception:
        return False


def kill_port_process(port):
    """নির্দিষ্ট পোর্টে চলা প্রসেস kill করুন"""
    if IS_WINDOWS:
        return
    try:
        result = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if f":{port} " in line and 'pid=' in line:
                for pid_str in re.findall(r'pid=(\d+)', line):
                    try:
                        os.kill(int(pid_str), 9)
                        print(f"🔪 পোর্ট {port}-এর পুরনো প্রসেস {pid_str} kill")
                    except Exception:
                        pass
        time.sleep(1)
    except Exception as e:
        print(f"⚠️ kill_port_process ব্যর্থ: {e}")


def stop_api_process(app_id):
    proc = API_PROCESSES.pop(app_id, None)
    if proc:
        try:
            if IS_WINDOWS:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.terminate()
                time.sleep(1)
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            pass

    app, uname, data = get_api_app_by_id(app_id)
    if app:
        users = load_users()
        for a in users.get(uname, {}).get('api_apps', []):
            if a.get('app_id') == app_id:
                a['status'] = 'stopped'
                a['pid'] = None
                break
        save_users(users)


def run_api_app(app_id):
    app_data, uname, user_data = get_api_app_by_id(app_id)
    if not app_data:
        return None, "App not found"

    app_dir = get_api_app_dir(app_id)
    log_file = os.path.join(app_dir, 'output.log')
    language = app_data.get('language', 'node')
    entry = app_data.get('entry_file', 'server.js')
    port = app_data.get('port') or get_free_port()

    if not port:
        return None, "কোনো ফ্রি পোর্ট নেই"

    # ✅ crash counter রিসেট
    users_reset = load_users()
    for a in users_reset.get(uname, {}).get('api_apps', []):
        if a.get('app_id') == app_id:
            a.pop('_crash_count', None)
            break
    save_users(users_reset)

    # ✅ পোর্ট দখল করে থাকলে পুরনো প্রসেস kill
    if is_port_in_use(port):
        print(f"⚠️ পোর্ট {port} ব্যবহৃত — পুরনো প্রসেস kill করা হচ্ছে")
        kill_port_process(port)

    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Starting {language} API...\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Entry: {entry}\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Port: {port}\n\n")
    except Exception:
        pass

    entry_path = os.path.join(app_dir, entry)
    if not os.path.exists(entry_path):
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"❌ {entry} ফাইল পাওয়া যায়নি!\n")
        return None, f"{entry} নেই"

    env = os.environ.copy()
    env['PORT'] = str(port)
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['NODE_ENV'] = 'production'

    try:
        if language == 'node':
            node_check = shutil.which('node')
            if not node_check:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write("❌ Node.js ইনস্টল নেই!\n")
                return None, "Node.js ইনস্টল নেই"

            pkg = os.path.join(app_dir, 'package.json')
            if os.path.exists(pkg):
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write("📦 npm install চলছে...\n")
                try:
                    subprocess.run(
                        ['npm', 'install', '--omit=dev', '--silent',
                         '--registry=https://registry.npmmirror.com',
                         '--fetch-timeout=900000',
                         '--fetch-retries=5'],
                        cwd=app_dir,
                        capture_output=True,
                        timeout=900
                    )
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write("✅ npm install সম্পন্ন\n\n")
                except Exception as e:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"⚠️ npm install failed: {e}\n\n")

            cmd = ['node', entry]

        elif language == 'python':
            cmd = [GLOBAL_PYTHON, '-u', entry]
            req = os.path.join(app_dir, 'requirements.txt')
            if os.path.exists(req):
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write("📦 pip install চলছে...\n")
                try:
                    subprocess.run(
                        [GLOBAL_PYTHON, '-m', 'pip', 'install', '-r', req,
                         '--quiet', '--disable-pip-version-check',
                         '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'],
                        cwd=app_dir, capture_output=True, timeout=900
                    )
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write("✅ pip install সম্পন্ন\n\n")
                except Exception as e:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"⚠️ pip install failed: {e}\n\n")
        else:
            return None, "Unsupported language"

        if IS_WINDOWS:
            proc = subprocess.Popen(
                cmd, cwd=app_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, universal_newlines=True
            )
        else:
            proc = subprocess.Popen(
                cmd, cwd=app_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, universal_newlines=True,
                preexec_fn=os.setsid
            )

        API_PROCESSES[app_id] = proc

        def stream():
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {line.rstrip()}\n")
                            f.flush()
            except Exception:
                pass

        threading.Thread(target=stream, daemon=True).start()

        # ✅ ZIP আপডেট (npm install-এর পর)
        try:
            update_api_zip(app_id)
        except Exception as e:
            print(f"⚠️ ZIP update error: {e}")

        users = load_users()
        for a in users[uname].get('api_apps', []):
            if a.get('app_id') == app_id:
                a['status'] = 'running'
                a['pid'] = proc.pid
                a['port'] = port
                a['started_at'] = str(datetime.now())
                break
        save_users(users)

        # ✅ Monitor — শুধু স্ট্যাটাস আপডেট, অটো-রিস্টার্ট বন্ধ
        def monitor():
            proc.wait()
            time.sleep(2)

            users2 = load_users()
            app_info = None
            for a in users2.get(uname, {}).get('api_apps', []):
                if a.get('app_id') == app_id:
                    app_info = a
                    break

            if app_info:
                app_info['status'] = 'stopped'
                app_info['pid'] = None
                app_info.pop('_crash_count', None)
                save_users(users2)

            API_PROCESSES.pop(app_id, None)

        threading.Thread(target=monitor, daemon=True).start()

        return {
            'pid': proc.pid,
            'port': port,
            'api_url': f"/api-proxy/{app_id}/"
        }, None

    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"❌ Error: {str(e)}\n")
        return None, str(e)


def restore_running_api_apps():
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for app in data.get('api_apps', []):
            if isinstance(app, dict) and app.get('status') == 'running':
                app['status'] = 'stopped'
                app['pid'] = None
    save_users(users)


# ============================================
# Health
# ============================================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': str(datetime.now())}), 200


# ============================================
# Public API
# ============================================
@app.route('/api/create', methods=['GET'])
def api_create_server():
    username = request.args.get('username', '').strip()
    password = request.args.get('password', '').strip()
    server_type = request.args.get('type', 'file_server').strip()
    ram = request.args.get('ram', '1GB').strip()
    disk = request.args.get('disk', '1GB').strip()
    cpu_limit = int(request.args.get('cpu', '30'))
    days = int(request.args.get('days', '3'))

    if not password:
        password = generate_random_password(10)
    if not username:
        username = f"ALAMIN_CODEX{random.randint(10000, 99999)}"
    if len(username) < 3 or len(password) < 4:
        return jsonify({'status': 'error', 'message': 'Invalid!'}), 400

    users = load_users()
    if username in users:
        return jsonify({'status': 'error', 'message': 'Username exists!'}), 400

    server_id = str(uuid.uuid4())[:8]
    if days <= 0:
        expiry_str = 'unlimited'
    else:
        expiry_str = str(datetime.now() + timedelta(days=days))

    create_default_files(get_server_dir(server_id))

    new_server = {
        'server_id': server_id, 'type': server_type,
        'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()), 'expiry': expiry_str,
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit, 'rate_limit_exceeded': False,
        'stopped_by_user': False, 'is_locked': False
    }

    users[username] = {
        'password': hash_password(password),
        'raw_password': password,
        'role': 'user',
        'servers': [new_server]
    }
    save_users(users)

    return jsonify({'status': 'success', 'username': username, 'password': password, 'server_id': server_id}), 200


# ============================================
# Login
# ============================================
@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/landing')
def landing():
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role', 'admin')
        user_input = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if role == 'admin':
            users = load_users()
            admin_data = users.get('admin', {})
            admin_email = (admin_data.get('email') or DEFAULT_ADMIN_EMAIL).strip().lower()
            if user_input.lower() == admin_email and verify_password(password, admin_data.get('password', '')):
                session['user'] = 'admin'
                session['email'] = admin_email
                session['role'] = 'admin'
                return redirect(url_for('admin_dashboard'))
            return render_template('server_login.html', error="❌ Invalid admin email or password!")

        elif role == 'file_server':
            users = load_users()
            if user_input not in users:
                return render_template('server_login.html', error="❌ Invalid username or password!")
            user_data = users[user_input]
            if not verify_password(password, user_data.get('password', '')):
                return render_template('server_login.html', error="❌ Invalid username or password!")
            servers = user_data.get('servers', [])
            file_server = None
            for s in servers:
                if isinstance(s, dict) and s.get('type') == 'file_server':
                    file_server = s
                    break
            if not file_server:
                return render_template('server_login.html', error="⚠️ আপনার কোনো File Server নেই!")
            expiry = file_server.get('expiry', '')
            if expiry and expiry != 'unlimited':
                try:
                    if datetime.now() > datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S.%f'):
                        return render_template('server_login.html', error="⚠️ আপনার File Server expired!")
                except Exception:
                    pass
            if file_server.get('is_locked'):
                return render_template('server_login.html', error="🔒 আপনাকে ব্লক করা আছে!")
            session['user'] = user_input
            session['role'] = 'file_server'
            session['current_server_id'] = file_server.get('server_id')
            return redirect(url_for('file_server_home'))

        elif role == 'html_server':
            users = load_users()
            if user_input not in users:
                return render_template('server_login.html', error="❌ Invalid username or password!")
            user_data = users[user_input]
            if not verify_password(password, user_data.get('password', '')):
                return render_template('server_login.html', error="❌ Invalid username or password!")
            if 'max_sites' not in user_data:
                return render_template('server_login.html', error="⚠️ আপনার কোনো HTML Server নেই!")

            user_expiry = user_data.get('expiry', '')
            if user_expiry and user_expiry != 'unlimited':
                try:
                    if datetime.now() > datetime.strptime(user_expiry, '%Y-%m-%d %H:%M:%S.%f'):
                        return render_template('server_login.html', error="⚠️ আপনার HTML Server expired!")
                except Exception:
                    pass

            session['user'] = user_input
            session['role'] = 'html_server'
            return redirect(url_for('html_panel'))

        elif role == 'api_server':
            users = load_users()
            if user_input not in users:
                return render_template('server_login.html', error="❌ Invalid username or password!")
            user_data = users[user_input]
            if not verify_password(password, user_data.get('password', '')):
                return render_template('server_login.html', error="❌ Invalid username or password!")
            if 'api_limits' not in user_data:
                return render_template('server_login.html', error="⚠️ আপনার কোনো API Server নেই!")

            user_expiry = user_data.get('expiry', '')
            if user_expiry and user_expiry != 'unlimited':
                try:
                    if datetime.now() > datetime.strptime(user_expiry, '%Y-%m-%d %H:%M:%S.%f'):
                        return render_template('server_login.html', error="⚠️ API Server expired!")
                except Exception:
                    pass

            session['user'] = user_input
            session['role'] = 'api_server'
            return redirect(url_for('api_panel'))

        elif role == 'ip_server':
            return render_template('server_login.html', error="⚠️ IP Server login চালু হয়নি!")
        elif role == 'website':
            return render_template('server_login.html', error="⚠️ WEBSITE login চালু হয়নি!")
        else:
            return render_template('server_login.html', error="⚠️ Invalid role!")

    return render_template('server_login.html', error=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============================================
# File Server Panel
# ============================================
@app.route('/file-server/panel')
def file_server_home():
    if 'user' not in session or session.get('role') != 'file_server':
        return redirect(url_for('login'))
    server_id = session.get('current_server_id')
    server, username = get_server_by_id(server_id)
    if not server:
        session.clear()
        return redirect(url_for('login'))
    if server.get('is_locked'):
        session.clear()
        return redirect(url_for('login'))
    return render_template('home.html', username=username, current_server=server, server_id=server_id)


# ============================================
# HTML Panel
# ============================================
@app.route('/html-panel')
def html_panel():
    if 'user' not in session or session.get('role') != 'html_server':
        return redirect(url_for('login'))
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    max_sites = user_data.get('max_sites', 1)
    return render_template('html_panel.html', username=username, max_sites=max_sites)


# ============================================
# API Panel
# ============================================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


@app.route('/api-panel')
def api_panel():
    if 'user' not in session or session.get('role') != 'api_server':
        return redirect(url_for('login'))
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    limits = user_data.get('api_limits', {})
    server_ip = get_local_ip()
    server_port = int(os.environ.get('PORT', 5001))
    return render_template('api_panel.html',
                           username=username,
                           limits=limits,
                           server_ip=server_ip,
                           server_port=server_port)


# ============================================
# HTML User APIs
# ============================================
@app.route('/api/html/list_sites/<username>')
def api_html_list_sites(username):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    if session.get('user') != username and session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    users = load_users()
    user_data = users.get(username, {})
    sites = user_data.get('sites', [])
    max_sites = user_data.get('max_sites', 1)

    total_size = 0
    for s in sites:
        try:
            total_size += s.get('used_size_bytes', 0)
        except Exception:
            pass

    return jsonify({
        'sites': sites,
        'max_sites': max_sites,
        'total_size': format_bytes(total_size / 1024)
    })


@app.route('/api/html/get_site/<site_id>')
def api_html_get_site(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    for s in user_data.get('sites', []):
        if s.get('site_id') == site_id:
            return jsonify(s)
    return jsonify({'error': 'Site not found'}), 404


@app.route('/api/html/create_site', methods=['POST'])
def api_html_create_site():
    if 'user' not in session or session.get('role') != 'html_server':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    site_name = (data.get('site_name') or '').strip().lower()

    if not is_valid_site_name(site_name):
        return jsonify({'error': 'Invalid site name! Use a-z, 0-9, -, _ (3-30 chars)'}), 400

    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    sites = user_data.get('sites', [])
    max_sites = user_data.get('max_sites', 1)

    if len(sites) >= max_sites:
        return jsonify({'error': f'Limit reached! Max {max_sites} sites'}), 400

    for s in sites:
        if s.get('name') == site_name:
            return jsonify({'error': f'Site "{site_name}" already exists!'}), 400

    site_dir = os.path.join(HTML_SITES_ROOT, username, site_name)
    os.makedirs(site_dir, exist_ok=True)

    index_file = os.path.join(site_dir, 'index.html')
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{site_name}</title>
    <style>
        body {{ font-family: Arial; background: linear-gradient(135deg, #0f0c29, #302b63);
            color: white; display: flex; align-items: center; justify-content: center;
            min-height: 100vh; margin: 0; text-align: center; }}
        h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
        p {{ color: #aaa; }}
    </style>
</head>
<body>
    <div>
        <h1>🚀 {site_name}</h1>
        <p>Site is ready! Upload your HTML files.</p>
    </div>
</body>
</html>''')

    host = request.host
    scheme = 'http' if 'localhost' in host or '127.0.0.1' in host else 'https'
    full_url = f"{scheme}://{host}/html/{username}/{site_name}/"

    site_id = str(uuid.uuid4())[:8]

    new_site = {
        'site_id': site_id,
        'name': site_name,
        'url': f'/html/{username}/{site_name}/',
        'full_url': full_url,
        'created': str(datetime.now()),
        'files_count': 1,
        'used_size': '0 KB',
        'used_size_bytes': 0,
        'views': 0,
        'is_locked': False,
        'is_disabled': False,
        'restarted_at': str(datetime.now())
    }

    if 'sites' not in users[username]:
        users[username]['sites'] = []
    users[username]['sites'].append(new_site)
    save_users(users)

    return jsonify({'success': True, 'site_id': site_id, 'name': site_name, 'url': full_url})


@app.route('/api/html/start_site/<site_id>', methods=['POST'])
def api_html_start_site(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    for s in users[username].get('sites', []):
        if s.get('site_id') == site_id:
            s['is_disabled'] = False
            s['restarted_at'] = str(datetime.now())
            save_users(users)
            return jsonify({'success': True, 'msg': 'Site started!'})
    return jsonify({'error': 'Site not found'}), 404


@app.route('/api/html/stop_site/<site_id>', methods=['POST'])
def api_html_stop_site(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    for s in users[username].get('sites', []):
        if s.get('site_id') == site_id:
            s['is_disabled'] = True
            save_users(users)
            return jsonify({'success': True, 'msg': 'Site stopped!'})
    return jsonify({'error': 'Site not found'}), 404


@app.route('/api/html/restart_site/<site_id>', methods=['POST'])
def api_html_restart_site(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    for s in users[username].get('sites', []):
        if s.get('site_id') == site_id:
            s['is_disabled'] = False
            s['restarted_at'] = str(datetime.now())
            save_users(users)
            return jsonify({'success': True, 'msg': 'Site restarted!'})
    return jsonify({'error': 'Site not found'}), 404


@app.route('/api/html/delete_site/<site_id>', methods=['POST'])
def api_html_delete_site(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        username = session.get('user')
        users = load_users()
        if username not in users:
            return jsonify({'error': 'User not found'}), 404
        user_data = users[username]
        sites = user_data.get('sites', [])
        if not isinstance(sites, list):
            sites = []
        target_site = None
        for s in sites:
            if isinstance(s, dict) and s.get('site_id') == site_id:
                target_site = s
                break
        if not target_site:
            return jsonify({'error': 'Site not found'}), 404

        site_name = target_site.get('name', '')

        if site_name:
            site_dir = os.path.join(HTML_SITES_ROOT, username, site_name)
            try:
                if os.path.exists(site_dir):
                    shutil.rmtree(site_dir)
            except Exception as e:
                print(f"Folder delete error: {e}")

        users[username]['sites'] = [s for s in sites if isinstance(s, dict) and s.get('site_id') != site_id]
        save_users(users)
        return jsonify({'success': True, 'deleted': site_name})
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/html/files/<site_id>')
def api_html_files(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    target_site = None
    for s in user_data.get('sites', []):
        if s.get('site_id') == site_id:
            target_site = s
            break
    if not target_site:
        return jsonify({'error': 'Site not found'}), 404

    site_dir = os.path.join(HTML_SITES_ROOT, username, target_site['name'])
    if not os.path.exists(site_dir):
        return jsonify({'files': []})

    files = []
    for root, dirs, fls in os.walk(site_dir):
        for f in fls:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, site_dir)
            try:
                files.append({
                    'name': f,
                    'path': rel_path.replace('\\', '/'),
                    'size': os.path.getsize(full_path)
                })
            except Exception:
                pass
    return jsonify({'files': files})


@app.route('/api/html/upload/<site_id>', methods=['POST'])
def api_html_upload(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    target_site = None
    for s in user_data.get('sites', []):
        if s.get('site_id') == site_id:
            target_site = s
            break
    if not target_site:
        return jsonify({'error': 'Site not found'}), 404
    if target_site.get('is_locked'):
        return jsonify({'error': 'Site locked!'}), 403

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files!'}), 400

    site_name = target_site['name']
    site_dir = os.path.join(HTML_SITES_ROOT, username, site_name)
    os.makedirs(site_dir, exist_ok=True)

    uploaded = 0
    files_info = []
    total_bytes = 0

    for f in files:
        if not f or not f.filename:
            continue
        filename = f.filename.replace('\\', '/').replace('..', '').lstrip('/')
        target_path = os.path.join(site_dir, filename)
        if not os.path.abspath(target_path).startswith(os.path.abspath(site_dir)):
            continue
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        file_data = f.read()
        with open(target_path, 'wb') as nf:
            nf.write(file_data)
        uploaded += 1
        file_size = len(file_data)
        files_info.append({
            'name': filename,
            'size': format_bytes(file_size / 1024),
            'size_bytes': file_size,
            'type': get_file_type(filename)
        })

    total_files = 0
    for root, dirs, fls in os.walk(site_dir):
        for fl in fls:
            total_files += 1
            try:
                total_bytes += os.path.getsize(os.path.join(root, fl))
            except Exception:
                pass

    zip_filename = f"{username}_{site_name}.zip"
    zip_path = os.path.join(HTML_SERVER_ROOT, zip_filename)

    try:
        merge_zip_with_folder(zip_path, site_dir)
        zip_size_bytes = os.path.getsize(zip_path)
    except Exception as e:
        print(f"ZIP creation error: {e}")
        zip_size_bytes = 0

    all_data = load_html_all_json()
    key = f"{username}_{site_name}"

    existing = all_data['sites'].get(key, {})
    prev_count = existing.get('upload_count', 0)

    zip_files_count = 0
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zip_files_count = len([n for n in zf.namelist() if not n.endswith('/')])
    except Exception:
        pass

    all_data['sites'][key] = {
        'owner_username': username,
        'site_name': site_name,
        'zip_name': zip_filename,
        'upload_count': prev_count + 1,
        'last_uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'files_count': total_files,
        'total_size': format_bytes(total_bytes / 1024),
        'total_size_bytes': total_bytes,
        'zip_size': format_bytes(zip_size_bytes / 1024),
        'zip_size_bytes': zip_size_bytes,
        'zip_files_count': zip_files_count,
        'files_info': files_info
    }
    save_html_all_json(all_data)

    target_site['files_count'] = total_files
    target_site['used_size'] = format_bytes(total_bytes / 1024)
    target_site['used_size_bytes'] = total_bytes
    save_users(users)

    return jsonify({
        'success': True,
        'count': uploaded,
        'total_files': total_files,
        'zip_files': zip_files_count,
        'used_size': format_bytes(total_bytes / 1024)
    })


@app.route('/api/html/delete_file/<site_id>', methods=['DELETE'])
def api_html_delete_file(site_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    target_site = None
    for s in user_data.get('sites', []):
        if s.get('site_id') == site_id:
            target_site = s
            break
    if not target_site:
        return jsonify({'error': 'Site not found'}), 404

    data = request.get_json()
    path = data.get('path', '')
    if not path:
        return jsonify({'error': 'No path'}), 400

    site_dir = os.path.join(HTML_SITES_ROOT, username, target_site['name'])
    file_path = os.path.join(site_dir, path)

    if not os.path.abspath(file_path).startswith(os.path.abspath(site_dir)):
        return jsonify({'error': 'Access denied'}), 403

    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)

    total_files = 0
    total_bytes = 0
    for root, dirs, fls in os.walk(site_dir):
        for fl in fls:
            total_files += 1
            try:
                total_bytes += os.path.getsize(os.path.join(root, fl))
            except Exception:
                pass

    target_site['files_count'] = total_files
    target_site['used_size'] = format_bytes(total_bytes / 1024)
    target_site['used_size_bytes'] = total_bytes
    save_users(users)

    return jsonify({'success': True})


@app.route('/html/<username>/<site_name>/')
@app.route('/html/<username>/<site_name>/<path:filename>')
def serve_html_site(username, site_name, filename='index.html'):
    users = load_users()
    if username not in users:
        return "Site not found", 404

    user_data = users[username]
    sites = user_data.get('sites', [])

    target_site = None
    for s in sites:
        if s.get('name') == site_name:
            target_site = s
            break

    if not target_site:
        return "Site not found", 404

    if target_site.get('is_locked'):
        return "Site is locked", 403

    if target_site.get('is_disabled'):
        return """<!DOCTYPE html>
<html><head><title>Site Stopped</title>
<style>body{background:#0f0c29;color:#fff;font-family:Arial;
display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;text-align:center;}
h1{font-size:4rem;margin:0;color:#f59e0b;}
p{color:#aaa;margin-top:1rem;}</style></head>
<body><div><h1>⏸️ Site Stopped</h1><p>This site has been stopped by the owner.</p></div></body></html>""", 503

    user_expiry = user_data.get('expiry', '')
    if user_expiry and user_expiry != 'unlimited':
        try:
            if datetime.now() > datetime.strptime(user_expiry, '%Y-%m-%d %H:%M:%S.%f'):
                return "Site expired", 410
        except Exception:
            pass

    view_key = f'viewed_{username}_{site_name}'
    if view_key not in session:
        session[view_key] = True
        target_site['views'] = target_site.get('views', 0) + 1
        save_users(users)

    site_dir = os.path.join(HTML_SITES_ROOT, username, site_name)
    if not os.path.exists(site_dir):
        return "Site not found", 404

    safe_path = os.path.abspath(os.path.join(site_dir, filename))
    if not safe_path.startswith(os.path.abspath(site_dir)):
        return "Access denied", 403

    if os.path.isdir(safe_path):
        safe_path = os.path.join(safe_path, 'index.html')

    if not os.path.exists(safe_path):
        return """<!DOCTYPE html>
<html><head><title>404</title>
<style>body{background:#0f0c29;color:#fff;font-family:Arial;
display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;text-align:center;}
h1{font-size:5rem;margin:0;}p{color:#aaa;}</style></head>
<body><div><h1>404</h1><p>index.html not found</p></div></body></html>""", 404

    return send_file(safe_path)


# ============================================
# Admin Panel
# ============================================
@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    users = load_users()

    file_users = []
    file_total_servers = 0
    file_total_running = 0

    html_users = []
    html_total_sites = 0
    html_total_active = 0
    html_total_locked = 0

    for uname, data in users.items():
        if uname == 'admin':
            continue

        servers = data.get('servers', [])
        if isinstance(servers, list) and len(servers) > 0:
            running = sum(1 for s in servers if isinstance(s, dict) and s.get('status') == 'running')
            file_total_servers += len(servers)
            file_total_running += running
            file_users.append({
                'username': uname,
                'password': '••••••••',
                'raw_password': data.get('raw_password', '••••••••'),
                'servers': servers,
            })

        sites = data.get('sites', [])
        if isinstance(sites, list) and ('max_sites' in data):
            total_size = sum(s.get('used_size_bytes', 0) for s in sites if isinstance(s, dict))
            has_locked = any(s.get('is_locked') for s in sites if isinstance(s, dict))

            for site in sites:
                if site.get('is_locked'):
                    html_total_locked += 1
                else:
                    html_total_active += 1

            html_total_sites += len(sites)

            user_expiry = data.get('expiry', '')
            if not user_expiry or user_expiry == 'unlimited':
                expiry_display = 'Unlimited'
            else:
                try:
                    expiry_display = user_expiry[:10]
                except Exception:
                    expiry_display = 'Unlimited'

            html_users.append({
                'username': uname,
                'password': '••••••••',
                'raw_password': data.get('raw_password', '••••••••'),
                'sites': sites,
                'site_count': len(sites),
                'max_sites': data.get('max_sites', 1),
                'total_size': format_bytes(total_size / 1024),
                'has_locked': has_locked,
                'expiry_display': expiry_display,
            })

    api_users = []
    api_total_apps = 0
    api_total_running = 0

    for uname, data in users.items():
        if uname == 'admin':
            continue
        if 'api_limits' in data:
            apps = data.get('api_apps', [])
            running = sum(1 for a in apps if isinstance(a, dict) and a.get('status') == 'running')
            api_total_apps += len(apps)
            api_total_running += running

            user_expiry = data.get('expiry', '')
            if not user_expiry or user_expiry == 'unlimited':
                expiry_display = 'Unlimited'
            else:
                try:
                    expiry_display = user_expiry[:10]
                except Exception:
                    expiry_display = 'Unlimited'

            limits = data.get('api_limits', {})
            api_users.append({
                'username': uname,
                'raw_password': data.get('raw_password', '••••••••'),
                'apps': apps,
                'app_count': len(apps),
                'max_apps': limits.get('max_apps', 3),
                'max_ram_mb': limits.get('max_ram_mb', 256),
                'max_cpu': limits.get('max_cpu', 0.5),
                'expiry_display': expiry_display,
            })

    # ✅ API Backups লিস্ট
    api_backups = []
    try:
        backup_data = load_api_all_json()
        for backup_id, info in backup_data.get('backups', {}).items():
            zip_name = info.get('zip_name', f"{backup_id}.zip")
            zip_path = os.path.join(API_BACKUP_ROOT, zip_name)
            info['zip_exists'] = os.path.exists(zip_path)
            api_backups.append(info)
        api_backups.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
    except Exception as e:
        print(f"⚠️ Backup load error: {e}")

    return render_template('admin.html',
                           file_users=file_users,
                           file_total_servers=file_total_servers,
                           file_total_running=file_total_running,
                           html_users=html_users,
                           html_total_sites=html_total_sites,
                           html_total_active=html_total_active,
                           html_total_locked=html_total_locked,
                           api_users=api_users,
                           api_total_apps=api_total_apps,
                           api_total_running=api_total_running,
                           api_backups=api_backups)


@app.route('/admin/create_server', methods=['POST'])
def create_server():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    server_type = data.get('server_type', 'file_server')
    ram = data.get('ram', '512MB')
    disk = data.get('disk', '1GB')
    expiry_days = int(data.get('expiry_days', 30))
    cpu_limit = int(data.get('cpu_limit', 80))

    if not username or not password:
        return jsonify({'error': 'Required!'}), 400

    users = load_users()
    server_id = str(uuid.uuid4())[:8]

    if expiry_days <= 0:
        expiry_str = 'unlimited'
    else:
        expiry_str = str(datetime.now() + timedelta(days=expiry_days))

    create_default_files(get_server_dir(server_id))

    new_server = {
        'server_id': server_id,
        'type': server_type, 'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()), 'expiry': expiry_str,
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit, 'rate_limit_exceeded': False,
        'stopped_by_user': False, 'is_locked': False
    }

    if username not in users:
        users[username] = {
            'password': hash_password(password),
            'raw_password': password,
            'role': 'user',
            'servers': [],
            'sites': []
        }
    else:
        users[username]['raw_password'] = password

    if 'servers' not in users[username]:
        users[username]['servers'] = []

    users[username]['servers'].append(new_server)
    save_users(users)

    return jsonify({
        'success': True, 'username': username, 'password': password,
        'server_id': server_id, 'cpu_limit': cpu_limit
    })


@app.route('/admin/create_html_server', methods=['POST'])
def create_html_server():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    max_sites = int(data.get('max_sites', 1))
    expiry_days = int(data.get('expiry_days', 0))

    if not username or not password:
        return jsonify({'error': 'Username & password required!'}), 400
    if max_sites < 1 or max_sites > 100:
        return jsonify({'error': 'Max sites 1-100!'}), 400

    users = load_users()
    if username in users:
        return jsonify({'error': f'Username "{username}" already exists!'}), 400

    user_dir = os.path.join(HTML_SITES_ROOT, username)
    os.makedirs(user_dir, exist_ok=True)

    if expiry_days <= 0:
        expiry_str = 'unlimited'
        expiry_display = 'Unlimited'
    else:
        expiry_str = str(datetime.now() + timedelta(days=expiry_days))
        expiry_display = expiry_str[:10]

    users[username] = {
        'password': hash_password(password),
        'raw_password': password,
        'role': 'html_user',
        'servers': [],
        'sites': [],
        'max_sites': max_sites,
        'created': str(datetime.now()),
        'expiry': expiry_str,
        'expiry_display': expiry_display,
    }
    save_users(users)

    return jsonify({
        'success': True,
        'username': username,
        'password': password,
        'max_sites': max_sites,
        'expiry_display': expiry_display
    })


@app.route('/admin/create_api_server', methods=['POST'])
def create_api_server():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    max_apps = int(data.get('max_apps', 3))
    max_files = int(data.get('max_files', 10))
    max_disk_mb = int(data.get('max_disk_mb', 100))
    max_ram_mb = int(data.get('max_ram_mb', 256))
    max_cpu = float(data.get('max_cpu', 0.5))
    expiry_days = int(data.get('expiry_days', 0))

    if not username or not password:
        return jsonify({'error': 'Username & password required!'}), 400

    users = load_users()
    if username in users:
        return jsonify({'error': f'"{username}" already exists!'}), 400

    if expiry_days <= 0:
        expiry_str = 'unlimited'
        expiry_display = 'Unlimited'
    else:
        expiry_str = str(datetime.now() + timedelta(days=expiry_days))
        expiry_display = expiry_str[:10]

    users[username] = {
        'password': hash_password(password),
        'raw_password': password,
        'role': 'api_user',
        'servers': [],
        'sites': [],
        'api_apps': [],
        'api_limits': {
            'max_apps': max_apps,
            'max_files': max_files,
            'max_disk_mb': max_disk_mb,
            'max_ram_mb': max_ram_mb,
            'max_cpu': max_cpu,
        },
        'created': str(datetime.now()),
        'expiry': expiry_str,
        'expiry_display': expiry_display,
    }
    save_users(users)

    return jsonify({
        'success': True,
        'username': username,
        'password': password,
        'max_apps': max_apps,
        'expiry_display': expiry_display
    })


@app.route('/admin/delete_api_user/<username>', methods=['POST'])
def admin_delete_api_user(username):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404

    for app in users[username].get('api_apps', []):
        if isinstance(app, dict) and app.get('app_id'):
            stop_api_process(app['app_id'])

    for app in users[username].get('api_apps', []):
        if isinstance(app, dict):
            try:
                shutil.rmtree(get_api_app_dir(app['app_id']))
            except Exception:
                pass

    del users[username]
    save_users(users)
    return jsonify({'success': True})


@app.route('/admin/delete_entire_user/<username>', methods=['POST'])
def admin_delete_entire_user(username):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        users = load_users()
        if username not in users:
            return jsonify({'error': f'User "{username}" not found'}), 404

        user_data = users[username]

        user_dir = os.path.join(HTML_SITES_ROOT, username)
        try:
            if os.path.exists(user_dir):
                shutil.rmtree(user_dir)
        except Exception as e:
            print(f"HTML folder delete error: {e}")

        for s in user_data.get('servers', []):
            if isinstance(s, dict):
                sid = s.get('server_id')
                if sid:
                    if s.get('pid'):
                        try:
                            stop_bot_process(s['pid'])
                        except Exception:
                            pass
                    try:
                        bot_dir = get_server_dir(sid)
                        if os.path.exists(bot_dir):
                            shutil.rmtree(bot_dir)
                    except Exception as e:
                        print(f"Bot folder delete error: {e}")

        for app in user_data.get('api_apps', []):
            if isinstance(app, dict) and app.get('app_id'):
                stop_api_process(app['app_id'])
                try:
                    shutil.rmtree(get_api_app_dir(app['app_id']))
                except Exception:
                    pass

        del users[username]
        save_users(users)

        return jsonify({'success': True, 'deleted': username})
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/admin/delete_html/<username>/<site_id>', methods=['POST'])
def admin_delete_html(username, site_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        users = load_users()
        if username not in users:
            return jsonify({'error': f'User "{username}" not found'}), 404

        user_data = users[username]
        sites = user_data.get('sites', [])
        if not isinstance(sites, list):
            sites = []

        target_site = None
        for s in sites:
            if isinstance(s, dict) and s.get('site_id') == site_id:
                target_site = s
                break

        if not target_site:
            return jsonify({'error': 'Site not found'}), 404

        site_name = target_site.get('name', '')

        if site_name:
            site_dir = os.path.join(HTML_SITES_ROOT, username, site_name)
            try:
                if os.path.exists(site_dir):
                    shutil.rmtree(site_dir)
            except Exception as e:
                print(f"Folder delete error: {e}")

        users[username]['sites'] = [s for s in sites if isinstance(s, dict) and s.get('site_id') != site_id]
        save_users(users)
        return jsonify({'success': True, 'deleted': site_name})
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/admin/lock_html/<site_id>', methods=['POST'])
def admin_lock_html(site_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('sites', []):
            if isinstance(s, dict) and s.get('site_id') == site_id:
                s['is_locked'] = True
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/admin/unlock_html/<site_id>', methods=['POST'])
def admin_unlock_html(site_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('sites', []):
            if isinstance(s, dict) and s.get('site_id') == site_id:
                s['is_locked'] = False
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/admin/set_rate_limit/<server_id>', methods=['POST'])
def set_rate_limit(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    cpu_limit = int(request.get_json().get('cpu_limit', 80))
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('servers', []):
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['cpu_limit'] = cpu_limit
                save_users(users)
                return jsonify({'success': True, 'cpu_limit': cpu_limit})
    return jsonify({'error': 'Not found'}), 404


@app.route('/admin/delete_server/<username>/<server_id>', methods=['POST'])
def delete_server(username, server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    if username in users:
        servers = users[username].get('servers', [])
        if not isinstance(servers, list):
            servers = []
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                if s.get('pid'):
                    stop_bot_process(s['pid'])
                try:
                    shutil.rmtree(get_server_dir(server_id))
                except Exception:
                    pass
                break
        users[username]['servers'] = [s for s in servers if isinstance(s, dict) and s.get('server_id') != server_id]

        if len(users[username].get('servers', [])) == 0 and len(users[username].get('sites', [])) == 0 and users[username].get('role') != 'html_user' and 'api_limits' not in users[username]:
            del users[username]

        save_users(users)
    return jsonify({'success': True})


@app.route('/admin/lock_server/<server_id>', methods=['POST'])
def lock_server(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('servers', []):
            if isinstance(s, dict) and s.get('server_id') == server_id:
                if s.get('pid'):
                    try:
                        stop_bot_process(s['pid'])
                    except Exception:
                        pass
                s['is_locked'] = True
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Server not found'}), 404


@app.route('/admin/unlock_server/<server_id>', methods=['POST'])
def unlock_server(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('servers', []):
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['is_locked'] = False
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Server not found'}), 404


@app.route('/admin/start_all_servers', methods=['POST'])
def start_all_servers():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    started = failed = skipped = 0
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for s in data.get('servers', []):
            if not isinstance(s, dict):
                continue
            if s.get('is_locked'):
                skipped += 1
                continue
            if s.get('status') == 'running':
                continue
            s['rate_limit_exceeded'] = False
            s['stopped_by_user'] = False
            pid, error = run_bot(s.get('server_id'), s.get('main_file', 'main.py'),
                                 s.get('requirements_file', 'requirements.txt'))
            if pid:
                s['status'] = 'running'
                s['pid'] = pid
                s['started_at'] = str(datetime.now())
                started += 1
                threading.Thread(target=monitor_bot, args=(s.get('server_id'), pid), daemon=True).start()
            else:
                failed += 1
    save_users(users)
    return jsonify({'success': True, 'started': started, 'failed': failed, 'skipped': skipped})


@app.route('/admin/stop_all_servers', methods=['POST'])
def stop_all_servers():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    stopped = failed = 0
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for s in data.get('servers', []):
            if not isinstance(s, dict):
                continue
            if s.get('status') != 'running':
                continue
            pid = s.get('pid')
            if pid:
                try:
                    stop_bot_process(pid)
                    stopped += 1
                except Exception:
                    failed += 1
            s['status'] = 'stopped'
            s['pid'] = None
            s['stopped_by_user'] = True
    save_users(users)
    return jsonify({'success': True, 'stopped': stopped, 'failed': failed})


@app.route('/admin/restart_all_servers', methods=['POST'])
def restart_all_servers():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    restarted = failed = skipped = 0
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for s in data.get('servers', []):
            if not isinstance(s, dict):
                continue
            if s.get('is_locked'):
                skipped += 1
                continue
            if s.get('pid'):
                try:
                    stop_bot_process(s['pid'])
                except Exception:
                    pass
            s['status'] = 'stopped'
            s['pid'] = None
            s['rate_limit_exceeded'] = False
            s['stopped_by_user'] = False
            time.sleep(1)
            pid, error = run_bot(s.get('server_id'), s.get('main_file', 'main.py'),
                                 s.get('requirements_file', 'requirements.txt'))
            if pid:
                s['status'] = 'running'
                s['pid'] = pid
                s['started_at'] = str(datetime.now())
                restarted += 1
                threading.Thread(target=monitor_bot, args=(s.get('server_id'), pid), daemon=True).start()
            else:
                failed += 1
    save_users(users)
    return jsonify({'success': True, 'restarted': restarted, 'failed': failed, 'skipped': skipped})


# ═══════════════════════════════════════════════════════════
# ✅ ADMIN CREDENTIAL UPDATE (নতুন — HTML থেকে call হয়)
# ═══════════════════════════════════════════════════════════
@app.route('/admin/update_credentials', methods=['POST'])
def admin_update_credentials():
    """Admin email + password update — verify current password first"""
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    current_password = (data.get('current_password') or '').strip()
    new_email = (data.get('new_email') or '').strip().lower()
    new_password = (data.get('new_password') or '').strip()

    # ── Validation ──
    if not current_password:
        return jsonify({'success': False, 'error': 'Current password required!'}), 400

    if not new_email and not new_password:
        return jsonify({'success': False, 'error': 'Nothing to change!'}), 400

    # ── Load admin ──
    users = load_users()
    admin_data = users.get('admin', {})

    if not verify_password(current_password, admin_data.get('password', '')):
        return jsonify({'success': False, 'error': 'Current password incorrect!'}), 401

    email_changed = False
    password_changed = False

    # ── Email update ──
    if new_email:
        if '@' not in new_email or '.' not in new_email:
            return jsonify({'success': False, 'error': 'Invalid email format!'}), 400
        users['admin']['email'] = new_email
        email_changed = True

    # ── Password update ──
    if new_password:
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'Password must be 6+ characters!'}), 400
        users['admin']['password'] = hash_password(new_password)
        password_changed = True

    save_users(users)

    print(f"✅ Admin credentials updated — email: {email_changed}, password: {password_changed}")

    return jsonify({
        'success': True,
        'email_changed': email_changed,
        'password_changed': password_changed
    })


@app.route('/admin/change_admin_password', methods=['POST'])
def admin_change_password():
    """পুরনো route — backward compatibility-এর জন্য রাখা হয়েছে"""
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    new_email = data.get('new_email', '').strip().lower()

    if not current_password:
        return jsonify({'error': 'Current password required!'}), 400

    users = load_users()
    admin_data = users.get('admin', {})
    if not verify_password(current_password, admin_data.get('password', '')):
        return jsonify({'error': 'Current password incorrect!'}), 401

    changed = False
    if new_password:
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be 8+ chars!'}), 400
        users['admin']['password'] = hash_password(new_password)
        changed = True
    if new_email:
        if '@' not in new_email or '.' not in new_email:
            return jsonify({'error': 'Invalid email!'}), 400
        users['admin']['email'] = new_email
        changed = True

    if not changed:
        return jsonify({'error': 'Nothing to change!'}), 400

    save_users(users)
    return jsonify({'success': True, 'msg': 'Admin credentials updated!'})


# ============================================
# API APP Routes (User Panel)
# ============================================
@app.route('/api/apps/list')
def api_apps_list():
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    users = load_users()
    apps = users.get(username, {}).get('api_apps', [])
    return jsonify({'apps': apps})


@app.route('/api/apps/create', methods=['POST'])
def api_apps_create():
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    name = (data.get('name') or '').strip()
    language = data.get('language', 'node')
    entry_file = (data.get('entry_file') or ('server.js' if language == 'node' else 'main.py')).strip()

    if not name or len(name) < 2:
        return jsonify({'error': 'App name too short!'}), 400
    if language not in ('node', 'python'):
        return jsonify({'error': 'Only node/python supported!'}), 400

    username = session.get('user')
    users = load_users()
    user_data = users.get(username, {})
    limits = user_data.get('api_limits', {})
    apps = user_data.get('api_apps', [])

    if len(apps) >= limits.get('max_apps', 3):
        return jsonify({'error': f'App limit reached ({limits.get("max_apps", 3)})!'}), 400

    app_id = str(uuid.uuid4())[:8]
    subdomain = re.sub(r'[^a-z0-9-]', '-', name.lower())[:20] + '-' + app_id[:4]

    app_entry = {
        'app_id': app_id,
        'name': name,
        'subdomain': subdomain,
        'language': language,
        'entry_file': entry_file,
        'status': 'stopped',
        'pid': None,
        'port': None,
        'created': str(datetime.now()),
        'files_count': 0,
        'used_size_bytes': 0,
    }

    if 'api_apps' not in users[username]:
        users[username]['api_apps'] = []
    users[username]['api_apps'].append(app_entry)
    save_users(users)

    app_dir = get_api_app_dir(app_id)
    if language == 'node':
        with open(os.path.join(app_dir, 'server.js'), 'w', encoding='utf-8') as f:
            f.write(f"""const express = require('express');
const app = express();
app.use(express.json());

app.get('/', (req, res) => {{
  res.json({{ message: 'Hello from {name}!', time: new Date() }});
}});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log('Server running on port ' + PORT));
""")
        with open(os.path.join(app_dir, 'package.json'), 'w', encoding='utf-8') as f:
            f.write('{"name":"my-api","version":"1.0.0","dependencies":{"express":"^4.21.0"}}')
    else:
        with open(os.path.join(app_dir, 'main.py'), 'w', encoding='utf-8') as f:
            f.write(f"""from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({{'message': 'Hello from {name}!'}})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
""")
        with open(os.path.join(app_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
            f.write('flask\n')

    # ✅ ZIP তৈরি
    try:
        create_api_zip(app_id)
    except Exception as e:
        print(f"⚠️ ZIP create error: {e}")

    return jsonify({'success': True, 'app': app_entry})


@app.route('/api/apps/<app_id>/upload', methods=['POST'])
def api_apps_upload(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403

    username = session.get('user')
    app_data, owner, user_data = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'App not found'}), 404

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files!'}), 400

    users = load_users()
    limits = users[username].get('api_limits', {})
    max_files = limits.get('max_files', 10)
    max_disk = limits.get('max_disk_mb', 100) * 1024 * 1024

    app_dir = get_api_app_dir(app_id)
    uploaded = 0
    added_size = 0
    for f in files:
        if not f or not f.filename:
            continue
        filename = f.filename.replace('\\', '/').replace('..', '').lstrip('/')
        target = os.path.join(app_dir, filename)
        if not os.path.abspath(target).startswith(os.path.abspath(app_dir)):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data_bytes = f.read()
        added_size += len(data_bytes)
        with open(target, 'wb') as nf:
            nf.write(data_bytes)
        uploaded += 1

    total_files = sum(len(fls) for _, _, fls in os.walk(app_dir))
    total_bytes = sum(
        os.path.getsize(os.path.join(r, fl))
        for r, _, fls in os.walk(app_dir) for fl in fls
    )

    if total_files > max_files or total_bytes > max_disk:
        for f in files:
            try:
                filename = f.filename.replace('\\', '/').replace('..', '').lstrip('/')
                p = os.path.join(app_dir, filename)
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        return jsonify({'error': f'Limit exceeded! Max {max_files} files / {limits.get("max_disk_mb")}MB'}), 400

    for a in users[username]['api_apps']:
        if a['app_id'] == app_id:
            a['files_count'] = total_files
            a['used_size_bytes'] = total_bytes
            break
    save_users(users)

    # ✅ ZIP আপডেট
    try:
        update_api_zip(app_id)
    except Exception as e:
        print(f"⚠️ ZIP update error: {e}")

    return jsonify({'success': True, 'uploaded': uploaded, 'total_files': total_files})


@app.route('/api/apps/<app_id>/files')
def api_apps_files(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    app_dir = get_api_app_dir(app_id)

    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.vscode',
        'venv', 'env', '.venv', 'dist', 'build', '.next',
        '.cache', 'site-packages', '.pytest_cache',
        '.mypy_cache', 'coverage', '.idea'
    }
    SKIP_EXTENSIONS = (
        '.log', '.pyc', '.pyo', '.pyd', '.so', '.dylib',
        '.lock', '.map', '.tsbuildinfo'
    )
    SKIP_FILES = {
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
        '.DS_Store', 'Thumbs.db', '.gitignore', '.env',
        'output.log', 'github_deploy.log'
    }

    files = []
    for root, dirs, fls in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for fl in fls:
            if any(fl.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            if fl in SKIP_FILES:
                continue
            if fl.startswith('.'):
                continue

            full = os.path.join(root, fl)
            rel = os.path.relpath(full, app_dir).replace('\\', '/')
            try:
                files.append({
                    'name': fl,
                    'path': rel,
                    'size': os.path.getsize(full),
                    'modified': datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M')
                })
            except Exception:
                pass

    files.sort(key=lambda x: x['path'])
    return jsonify({'files': files})


@app.route('/api/apps/<app_id>/delete_file', methods=['POST'])
def api_apps_delete_file(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json()
    filename = data.get('filename', '')
    app_dir = get_api_app_dir(app_id)
    target = os.path.join(app_dir, filename)
    if not os.path.abspath(target).startswith(os.path.abspath(app_dir)):
        return jsonify({'error': 'Invalid path'}), 400
    if os.path.exists(target):
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)

    users = load_users()
    total_files = sum(len(fls) for _, _, fls in os.walk(app_dir))
    total_bytes = sum(
        os.path.getsize(os.path.join(r, fl))
        for r, _, fls in os.walk(app_dir) for fl in fls
    )
    for a in users[username]['api_apps']:
        if a['app_id'] == app_id:
            a['files_count'] = total_files
            a['used_size_bytes'] = total_bytes
            break
    save_users(users)
    return jsonify({'success': True})


@app.route('/api/apps/<app_id>/read_file')
def api_apps_read_file(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'No path'}), 400

    app_dir = get_api_app_dir(app_id)
    target = os.path.join(app_dir, path)

    if not os.path.abspath(target).startswith(os.path.abspath(app_dir)):
        return jsonify({'error': 'Invalid path'}), 403

    if 'node_modules' in path or '__pycache__' in path or path.startswith('.'):
        return jsonify({'error': 'Access denied'}), 403

    if not os.path.exists(target) or os.path.isdir(target):
        return jsonify({'error': 'File not found'}), 404

    if os.path.getsize(target) > 1_000_000:
        return jsonify({'error': 'File too large to edit (max 1MB)'}), 400

    try:
        with open(target, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'path': path})
    except UnicodeDecodeError:
        return jsonify({'error': 'Cannot edit binary file'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apps/<app_id>/write_file', methods=['POST'])
def api_apps_write_file(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json()
    path = data.get('path', '')
    content = data.get('content', '')

    if not path:
        return jsonify({'error': 'No path'}), 400

    app_dir = get_api_app_dir(app_id)
    target = os.path.join(app_dir, path)

    if not os.path.abspath(target).startswith(os.path.abspath(app_dir)):
        return jsonify({'error': 'Invalid path'}), 403

    if 'node_modules' in path or '__pycache__' in path or path.startswith('.'):
        return jsonify({'error': 'Access denied'}), 403

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)

        users = load_users()
        total_files = sum(1 for r, _, fls in os.walk(app_dir) for fl in fls
                          if not fl.endswith('.log') and 'node_modules' not in r)
        for a in users[username]['api_apps']:
            if a['app_id'] == app_id:
                a['files_count'] = total_files
                break
        save_users(users)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apps/<app_id>/rename_file', methods=['POST'])
def api_apps_rename_file(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json()
    old_path = data.get('old_path', '')
    new_path = data.get('new_path', '')

    if not old_path or not new_path:
        return jsonify({'error': 'Missing paths'}), 400

    app_dir = get_api_app_dir(app_id)
    old_target = os.path.join(app_dir, old_path)
    new_target = os.path.join(app_dir, new_path)

    if not os.path.abspath(old_target).startswith(os.path.abspath(app_dir)):
        return jsonify({'error': 'Invalid old path'}), 403
    if not os.path.abspath(new_target).startswith(os.path.abspath(app_dir)):
        return jsonify({'error': 'Invalid new path'}), 403

    if 'node_modules' in old_path or '__pycache__' in old_path:
        return jsonify({'error': 'Access denied'}), 403

    if not os.path.exists(old_target):
        return jsonify({'error': 'Source not found'}), 404

    if os.path.exists(new_target):
        return jsonify({'error': 'Target already exists'}), 400

    try:
        os.makedirs(os.path.dirname(new_target), exist_ok=True)
        os.rename(old_target, new_target)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/apps/<app_id>/start', methods=['POST'])
def api_apps_start(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    stop_api_process(app_id)
    time.sleep(0.5)

    result, err = run_api_app(app_id)
    if err:
        return jsonify({'error': err}), 500

    return jsonify({
        'success': True,
        'port': result['port'],
        'api_url': f"/api-proxy/{app_id}/"
    })


@app.route('/api/apps/<app_id>/stop', methods=['POST'])
def api_apps_stop(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    stop_api_process(app_id)
    return jsonify({'success': True})


@app.route('/api/apps/<app_id>/delete', methods=['POST'])
def api_apps_delete(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    stop_api_process(app_id)
    try:
        shutil.rmtree(get_api_app_dir(app_id))
    except Exception:
        pass

    users = load_users()
    users[username]['api_apps'] = [a for a in users[username].get('api_apps', []) if a.get('app_id') != app_id]
    save_users(users)
    return jsonify({'success': True})


@app.route('/api/apps/<app_id>/logs')
def api_apps_logs(app_id):
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    log_file = os.path.join(get_api_app_dir(app_id), 'output.log')
    content = ''
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            pass
    return jsonify({'logs': content})


# ============================================
# ✅ ERROR DETECTION
# ============================================
def detect_errors_from_log(log_text, language='python', app_id=None):
    """লগ থেকে এরর বের করে — কোন ফাইলে, কোন লাইনে"""
    errors = []
    lines = log_text.split('\n')

    for i, line in enumerate(lines, 1):
        line_stripped = line.strip()

        m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", line)
        if m:
            pkg = m.group(1)
            errors.append({
                'type': 'ModuleNotFoundError',
                'message': f'📦 Python প্যাকেজ "{pkg}" পাওয়া যায়নি',
                'code': line_stripped,
                'file_hint': 'requirements.txt'
            })

        m = re.search(r"ImportError: cannot import name '([^']+)'", line)
        if m:
            name = m.group(1)
            errors.append({
                'type': 'ImportError',
                'message': f'📦 "{name}" ইমপোর্ট করা যাচ্ছে না',
                'code': line_stripped,
                'file_hint': 'main.py'
            })

        if 'SyntaxError' in line and 'SyntaxError' not in [e['type'] for e in errors]:
            line_match = re.search(r'line (\d+)', log_text)
            err_line_no = int(line_match.group(1)) if line_match else 0

            bad_code = ''
            file_name = 'main.py'
            if app_id:
                try:
                    app_dir = get_api_app_dir(app_id)
                    _app_data, _, _ = get_api_app_by_id(app_id)
                    if _app_data:
                        file_name = _app_data.get('entry_file', 'main.py')
                    _file_path = os.path.join(app_dir, file_name)
                    if os.path.exists(_file_path):
                        with open(_file_path, 'r', encoding='utf-8') as _f:
                            _file_lines = _f.readlines()
                        if 0 < err_line_no <= len(_file_lines):
                            bad_code = _file_lines[err_line_no - 1].rstrip()
                except Exception:
                    pass

            errors.append({
                'type': 'SyntaxError',
                'message': f'✏️ Syntax ভুল — লাইন {err_line_no}',
                'code': bad_code or line_stripped,
                'line': err_line_no,
                'file_hint': file_name
            })

        if 'IndentationError' in line and 'IndentationError' not in [e['type'] for e in errors]:
            line_match = re.search(r'line (\d+)', log_text)
            err_line_no = int(line_match.group(1)) if line_match else 0
            errors.append({
                'type': 'IndentationError',
                'message': f'📏 ইন্ডেন্ট ভুল — লাইন {err_line_no}',
                'code': line_stripped,
                'line': err_line_no,
                'file_hint': 'main.py'
            })

        if 'Address already in use' in line:
            m = re.search(r'[Pp]ort\s+(\d+)', line)
            port = m.group(1) if m else '????'
            errors.append({
                'type': 'PortInUse',
                'message': f'🔌 পোর্ট {port} আগে থেকেই ব্যবহৃত',
                'code': line_stripped,
                'file_hint': 'main.py'
            })

        m = re.search(r"Cannot find module '([^']+)'", line)
        if m:
            pkg = m.group(1)
            errors.append({
                'type': 'CannotFindModule',
                'message': f'📦 npm প্যাকেজ "{pkg}" পাওয়া যায়নি',
                'code': line_stripped,
                'file_hint': 'package.json'
            })

        if 'EADDRINUSE' in line:
            m = re.search(r':(\d+)', line)
            port = m.group(1) if m else '????'
            errors.append({
                'type': 'EADDRINUSE',
                'message': f'🔌 পোর্ট {port} ব্যবহৃত',
                'code': line_stripped,
                'file_hint': 'server.js'
            })

    seen = set()
    unique = []
    for e in errors:
        key = e['type']
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique


@app.route('/api/apps/<app_id>/diagnose')
def api_apps_diagnose(app_id):
    """অ্যাপের লগ বিশ্লেষণ করে এরর তথ্য দেয়"""
    if 'user' not in session or session.get('role') != 'api_server':
        return jsonify({'error': 'Unauthorized'}), 403
    username = session.get('user')
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or owner != username:
        return jsonify({'error': 'Not found'}), 404

    log_file = os.path.join(get_api_app_dir(app_id), 'output.log')
    if not os.path.exists(log_file):
        return jsonify({'has_error': False})

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            log_text = f.read()
    except Exception:
        return jsonify({'has_error': False})

    language = app_data.get('language', 'python')
    errors = detect_errors_from_log(log_text, language, app_id=app_id)

    if not errors:
        return jsonify({'has_error': False})

    line_no = 0
    m = re.search(r'line\s+(\d+)', log_text)
    if m:
        line_no = int(m.group(1))

    entry_file = app_data.get('entry_file', 'main.py' if language == 'python' else 'server.js')

    context = []
    if line_no > 0:
        entry_path = os.path.join(get_api_app_dir(app_id), entry_file)
        if os.path.exists(entry_path):
            try:
                with open(entry_path, 'r', encoding='utf-8') as f:
                    file_lines = f.read().split('\n')
                start = max(0, line_no - 6)
                end = min(len(file_lines), line_no + 4)
                for i in range(start, end):
                    context.append({
                        'line_no': i + 1,
                        'code': file_lines[i],
                        'is_error': (i + 1) == line_no
                    })
            except Exception:
                pass

    return jsonify({
        'has_error': True,
        'language': language,
        'entry_file': entry_file,
        'error_line': line_no,
        'errors': errors,
        'context': context
    })


# ============================================
# ✅ API Proxy — with port check
# ============================================
@app.route('/api-proxy/<app_id>/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/api-proxy/<app_id>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def api_proxy(app_id, path):
    app_data, owner, _ = get_api_app_by_id(app_id)
    if not app_data or app_data.get('status') != 'running' or not app_data.get('port'):
        return jsonify({'error': 'API not running'}), 503

    port = app_data['port']

    if not is_port_in_use(port):
        users = load_users()
        for a in users.get(owner, {}).get('api_apps', []):
            if a.get('app_id') == app_id:
                a['status'] = 'stopped'
                a['pid'] = None
                break
        save_users(users)
        return jsonify({
            'error': f'API is not responding on port {port}. Please restart from the panel.',
            'hint': 'Go to /api-panel and click START'
        }), 503

    try:
        import urllib.request
        import urllib.error

        target_url = f"http://127.0.0.1:{port}/{path}"
        if request.query_string:
            target_url += '?' + request.query_string.decode()

        headers = {k: v for k, v in request.headers if k.lower() != 'host'}
        body = request.get_data() if request.method in ('POST', 'PUT', 'PATCH') else None

        req = urllib.request.Request(target_url, data=body, headers=headers, method=request.method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read()
                response = app.response_class(resp_body, status=resp.status)
                ct = resp.headers.get('Content-Type')
                if ct:
                    response.headers['Content-Type'] = ct
                return response
        except urllib.error.HTTPError as e:
            return app.response_class(e.read(), status=e.code)
        except urllib.error.URLError as e:
            return jsonify({'error': f'Upstream error: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# File Server Bot APIs
# ============================================
@app.route('/api/run/<server_id>', methods=['POST'])
def api_run(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'status': 'error', 'msg': 'Server not found!'})
    if server.get('is_locked'):
        return jsonify({'status': 'error', 'msg': '🔒 আপনাকে ব্লক করা আছে!'})
    if server.get('status') == 'running':
        if server.get('pid'):
            stop_bot_process(server['pid'])
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            for s in data.get('servers', []):
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'stopped'
                    s['pid'] = None
                    s['stopped_by_user'] = True
                    save_users(users)
                    break
        return jsonify({'status': 'success', 'msg': '⏹️ Stopped (toggle)!'})

    server['rate_limit_exceeded'] = False
    server['stopped_by_user'] = False
    pid, error = run_bot(server_id, server.get('main_file', 'main.py'),
                         server.get('requirements_file', 'requirements.txt'))
    if pid:
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            for s in data.get('servers', []):
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'running'
                    s['pid'] = pid
                    s['started_at'] = str(datetime.now())
                    save_users(users)
                    break
        threading.Thread(target=monitor_bot, args=(server_id, pid), daemon=True).start()
        return jsonify({'status': 'success', 'msg': '▶️ Started!'})
    return jsonify({'status': 'error', 'msg': error or 'Failed'})


@app.route('/api/stop/<server_id>', methods=['POST'])
def api_stop(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'status': 'error', 'msg': 'Not found'})
    if server.get('pid'):
        stop_bot_process(server['pid'])
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        for s in data.get('servers', []):
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
                save_users(users)
                break
    return jsonify({'status': 'success', 'msg': '⏹️ Stopped'})


@app.route('/api/logs/<server_id>')
def api_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    logs = ""
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
    return jsonify({'logs': logs})


@app.route('/api/clear_logs/<server_id>', methods=['POST'])
def api_clear_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except Exception:
                open(log_file, 'w').close()
        return jsonify({'status': 'success'})
    except Exception:
        return jsonify({'status': 'error'}), 500


@app.route('/api/command', methods=['POST'])
def api_command():
    data = request.get_json()
    cmd = data.get('cmd', '')
    server_id = data.get('server_id', '')
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                cwd=get_server_dir(server_id), timeout=30)
        output = (result.stdout + result.stderr)[:2000]
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] $ {cmd}\n{output}\n")
        return jsonify({'status': 'success', 'output': output})
    except Exception:
        return jsonify({'status': 'error', 'msg': 'Timeout'})


@app.route('/api/stats/<server_id>')
def api_stats(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'cpu': '0%', 'ram': '0 MB', 'uptime': '0h', 'status': 'unknown',
                        'cpu_limit': 80, 'net_in': '0 KB', 'net_out': '0 KB'})

    uptime, cpu, ram, net_in, net_out = "0h 0m", "0%", "0 MB", "0 KB", "0 KB"
    if server.get('status') == 'running' and server.get('pid'):
        stats = get_process_stats(server['pid'])
        cpu = f"{stats['cpu_percent']}%"
        ram = stats['ram_display']
        net_in, net_out = get_network_stats(server['pid'])

    if server.get('status') == 'running' and server.get('started_at'):
        try:
            start = datetime.strptime(server['started_at'], '%Y-%m-%d %H:%M:%S.%f')
            diff = datetime.now() - start
            if diff.days > 0:
                uptime = f"{diff.days}d {diff.seconds//3600}h"
            else:
                h, m, s = diff.seconds // 3600, (diff.seconds % 3600) // 60, diff.seconds % 60
                uptime = f"{h}h {m}m {s}s"
        except Exception:
            pass

    return jsonify({'cpu': cpu, 'ram': ram, 'uptime': uptime, 'net_in': net_in,
                    'net_out': net_out, 'cpu_limit': server.get('cpu_limit', 80),
                    'status': server.get('status', 'stopped')})


@app.route('/api/files/<server_id>')
def api_files(server_id):
    folder = request.args.get('folder', '').strip('/')
    if 'FILE------SERVER' in folder or 'FILE------CODE' in folder:
        return jsonify({'files': [], 'error': 'Access denied'})
    server_dir = get_server_dir(server_id)
    if folder:
        full_path = os.path.join(server_dir, folder)
        if not os.path.abspath(full_path).startswith(os.path.abspath(server_dir)):
            return jsonify({'files': []})
        if not os.path.exists(full_path):
            return jsonify({'files': []})
        scan_dir = full_path
    else:
        scan_dir = server_dir

    files = []
    try:
        for item in os.listdir(scan_dir):
            if item == 'FILE------SERVER':
                continue
            item_path = os.path.join(scan_dir, item)
            files.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),
                'size': os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M')
            })
    except Exception:
        pass
    return jsonify({'files': files})


@app.route('/api/file/<server_id>', methods=['GET'])
def api_get_file(server_id):
    filename = request.args.get('filename', '')
    filepath = os.path.join(get_server_dir(server_id), filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return jsonify({'content': f.read()})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/file/<server_id>', methods=['POST'])
def api_save_file(server_id):
    data = request.get_json()
    filepath = os.path.join(get_server_dir(server_id), data.get('filename', ''))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data.get('content', ''))
    return jsonify({'success': True})


@app.route('/api/file/<server_id>', methods=['DELETE'])
def api_delete_file(server_id):
    data = request.get_json()
    filename = data.get('filename', '')
    if 'FILE------SERVER' in filename:
        return jsonify({'error': 'Access denied'}), 403
    filepath = os.path.join(get_server_dir(server_id), filename)
    if os.path.exists(filepath):
        if os.path.isdir(filepath):
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)
    return jsonify({'success': True})


@app.route('/api/upload/<server_id>', methods=['POST'])
def api_upload(server_id):
    if 'file' not in request.files and 'files' not in request.files:
        return jsonify({'error': 'No file'}), 400
    uploaded_files = request.files.getlist('file') or request.files.getlist('files')
    if not uploaded_files:
        return jsonify({'error': 'No files!'}), 400

    server, owner_username = get_server_by_id(server_id)
    if not server:
        return jsonify({'error': 'Server not found!'}), 404

    server_dir = get_server_dir(server_id)
    current_folder = request.form.get('folder', '').strip('/')
    if current_folder and 'FILE------SERVER' not in current_folder:
        target_dir = os.path.join(server_dir, current_folder)
        os.makedirs(target_dir, exist_ok=True)
    else:
        target_dir = server_dir

    zip_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    zip_name = f"upload_{zip_id}.zip"
    zip_path = os.path.join(FILE_SERVER_ROOT, zip_name)

    files_info = []
    total_size = 0
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in uploaded_files:
                if not f or not f.filename:
                    continue
                safe_name = os.path.basename(f.filename)
                file_data = f.read()
                file_size = len(file_data)
                total_size += file_size
                zf.writestr(safe_name, file_data)
                with open(os.path.join(target_dir, safe_name), 'wb') as nf:
                    nf.write(file_data)
                files_info.append({
                    'name': safe_name,
                    'size': format_bytes(file_size / 1024),
                    'size_bytes': file_size,
                    'type': get_file_type(safe_name)
                })

        zip_size_bytes = os.path.getsize(zip_path)

        new_upload = {
            'zip_name': zip_name,
            'zip_path': f'FILE------SERVER/{zip_name}',
            'owner_server_id': server_id,
            'owner_username': owner_username or 'unknown',
            'folder': current_folder,
            'original_files': [fi['name'] for fi in files_info],
            'files_count': len(files_info),
            'total_size': format_bytes(total_size / 1024),
            'zip_size': format_bytes(zip_size_bytes / 1024),
            'zip_size_bytes': zip_size_bytes,
            'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'files_info': files_info
        }

        all_data = load_all_json()
        all_data['uploads'].append(new_upload)
        save_all_json(all_data)

        return jsonify({
            'success': True,
            'zip_name': zip_name,
            'files_count': len(files_info),
            'total_uploads': all_data['total_uploads'],
            'message': f'{len(files_info)} file(s) uploaded!'
        })
    except Exception as e:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@app.route('/api/create_folder/<server_id>', methods=['POST'])
def api_create_folder(server_id):
    data = request.get_json()
    folder_name = data.get('foldername', '')
    if 'FILE------SERVER' in folder_name or 'FILE------CODE' in folder_name:
        return jsonify({'error': 'Access denied'}), 403
    os.makedirs(os.path.join(get_server_dir(server_id), folder_name), exist_ok=True)
    return jsonify({'success': True})


@app.route('/api/rename/<server_id>', methods=['POST'])
def api_rename(server_id):
    d = request.get_json()
    old_name = d.get('old_name', '')
    new_name = d.get('new_name', '')
    if 'FILE------SERVER' in old_name or 'FILE------SERVER' in new_name:
        return jsonify({'error': 'Access denied'}), 403
    server_dir = get_server_dir(server_id)
    old_path = os.path.join(server_dir, old_name)
    new_path = os.path.join(server_dir, new_name)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/unzip/<server_id>', methods=['POST'])
def api_unzip(server_id):
    data = request.get_json()
    zip_path = os.path.join(get_server_dir(server_id), data.get('filename', ''))
    if os.path.exists(zip_path) and zip_path.endswith('.zip'):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(os.path.dirname(zip_path))
            return jsonify({'status': 'success', 'msg': 'Extracted!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)})
    return jsonify({'status': 'error', 'msg': 'Invalid zip'}), 400


@app.route('/api/get_startup/<server_id>')
def api_get_startup(server_id):
    server, _ = get_server_by_id(server_id)
    if server:
        return jsonify({'main_file': server.get('main_file', 'main.py'),
                        'requirements_file': server.get('requirements_file', 'requirements.txt')})
    return jsonify({'main_file': 'main.py', 'requirements_file': 'requirements.txt'})


@app.route('/api/set_startup/<server_id>', methods=['POST'])
def api_set_startup(server_id):
    d = request.get_json()
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        for s in udata.get('servers', []):
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['main_file'] = d.get('main_file', 'main.py')
                s['requirements_file'] = d.get('requirements_file')
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/change_password/<server_id>', methods=['POST'])
def api_change_password(server_id):
    if 'user' not in session:
        return jsonify({'error': 'Login required!'}), 403
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'All fields required!'})
    if len(new_password) < 4:
        return jsonify({'error': 'Password must be 4+ chars!'})

    users = load_users()
    username = session.get('user')

    if username in users:
        if verify_password(current_password, users[username].get('password', '')):
            users[username]['password'] = hash_password(new_password)
            users[username]['raw_password'] = new_password
            save_users(users)
            return jsonify({'success': True})
        return jsonify({'error': 'Current password incorrect!'})
    return jsonify({'error': 'User not found!'}), 404


# ============================================
# GitHub Deploy
# ============================================
@app.route('/api/github/deploy/<server_id>', methods=['POST'])
def api_github_deploy(server_id):
    data = request.get_json()
    repo_url = data.get('repo_url', '').strip()
    access_token = data.get('access_token', '').strip()
    is_private = data.get('is_private', False)

    if not repo_url:
        return jsonify({'status': 'error', 'msg': 'Repository URL required!'}), 400

    server_dir = get_server_dir(server_id)
    log_file = os.path.join(server_dir, 'github_deploy.log')

    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Starting GitHub deployment...\n")
    except Exception:
        pass

    def deploy_thread():
        try:
            import requests as req
            def deploy_log(msg):
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {msg}\n")
                        f.flush()
                except Exception:
                    pass

            clean_url = repo_url.replace('.git', '').rstrip('/')
            if 'github.com' not in clean_url:
                deploy_log("❌ Only GitHub URLs supported!")
                return
            parts = clean_url.split('github.com/')[-1].split('/')
            if len(parts) < 2:
                deploy_log("❌ Invalid URL!")
                return
            owner = parts[0]
            repo = parts[1]
            branch = 'main'
            if len(parts) > 3 and parts[2] == 'tree':
                branch = parts[3]

            api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if is_private and access_token:
                headers['Authorization'] = f'token {access_token}'

            response = req.get(api_url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                deploy_log("✓ Downloaded")
                temp_zip = os.path.join(server_dir, '_github_temp.zip')
                with open(temp_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        for member in zf.namelist():
                            rel = '/'.join(member.split('/')[1:])
                            if not rel:
                                continue
                            target = os.path.join(server_dir, rel)
                            if member.endswith('/'):
                                os.makedirs(target, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target), exist_ok=True)
                                with zf.open(member) as src, open(target, 'wb') as tgt:
                                    shutil.copyfileobj(src, tgt)
                    deploy_log("✅ Deployment completed!")
                finally:
                    try:
                        os.remove(temp_zip)
                    except Exception:
                        pass
            else:
                deploy_log(f"❌ HTTP {response.status_code}")
        except Exception as e:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"❌ {str(e)}\n")
            except Exception:
                pass

    threading.Thread(target=deploy_thread, daemon=True).start()
    return jsonify({'status': 'success', 'msg': 'Deployment started!'})


@app.route('/api/github/logs/<server_id>')
def api_github_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    logs = "> Ready for deployment..."
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.read()
        except Exception:
            pass
    return jsonify({'logs': logs})


@app.route('/api/github/clear_logs/<server_id>', methods=['POST'])
def api_github_clear_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    try:
        if os.path.exists(log_file):
            os.remove(log_file)
        return jsonify({'status': 'success'})
    except Exception:
        return jsonify({'status': 'error'}), 500


# ============================================
# Startup
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'

    print("\n" + "=" * 50)
    print("🚀 ALAMIN HOSTING - READY")
    print("=" * 50)
    print(f"📍 Port: {port}")
    print(f"📍 Data dir: {DATA_DIR}")
    print(f"📍 FILE------SERVER: {FILE_SERVER_ROOT}")
    print(f"📍 HTML------SERVER: {HTML_SERVER_ROOT}")
    print(f"📍 HTML_SITES: {HTML_SITES_ROOT}")
    print(f"📍 API_SERVER: {API_SERVER_ROOT}")
    print(f"📍 Global Python: {GLOBAL_PYTHON}")
    print(f"📍 Admin email: {DEFAULT_ADMIN_EMAIL}")
    print("=" * 50 + "\n")

    try:
        restore_running_api_apps()
    except Exception as e:
        print(f"⚠️ API restore failed: {e}")

    app.run(debug=debug_mode, host='0.0.0.0', port=port)