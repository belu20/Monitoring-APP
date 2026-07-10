from flask import Flask, render_template_string
import os
from datetime import datetime
import paramiko
from dotenv import load_dotenv

# Memuat variabel dari file .env
load_dotenv()

app = Flask(__name__)

# Ambil konfigurasi SSH dari .env
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22202))
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
BASE_DIR = os.getenv("BASE_DIR", "/home/log")

def get_remote_directory_status():
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_content = f"content-{today_str}.csv"
    target_index = f"index-{today_str}.csv"
    
    report = []
    
    if not SSH_HOST or not SSH_USER:
        return {"error": "Kredensial SSH di file .env belum lengkap!", "data": []}

    # Inisialisasi koneksi SSH
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASSWORD, timeout=10)
        sftp = ssh.open_sftp()
        
        try:
            items = sftp.listdir(BASE_DIR)
        except IOError:
            return {"error": f"Path remote tidak ditemukan: {BASE_DIR}", "data": []}
            
        # Filter item yang merupakan direktori
        directories = []
        import stat
        for item in items:
            item_path = f"{BASE_DIR}/{item}"
            try:
                mode = sftp.stat(item_path).st_mode
                if stat.S_ISDIR(mode):
                    directories.append(item)
            except IOError:
                continue
                
        directories.sort()

        # Cek ketersediaan file index & content hari ini di setiap folder
        for folder in directories:
            folder_path = f"{BASE_DIR}/{folder}"
            content_path = f"{folder_path}/{target_content}"
            index_path = f"{folder_path}/{target_index}"
            
            content_updated = True
            try:
                sftp.stat(content_path)
            except IOError:
                content_updated = False
                
            index_updated = True
            try:
                sftp.stat(index_path)
            except IOError:
                index_updated = False
            
            if content_updated and index_updated:
                status = "OK"
                priority = 1  # Paling atas
            elif content_updated or index_updated:
                status = "PARTIAL"
                priority = 2  # Tengah
            else:
                status = "CRITICAL"
                priority = 3  # Paling bawah
                
            report.append({
                "folder_name": folder,
                "content_updated": content_updated,
                "index_updated": index_updated,
                "status": status,
                "priority": priority  # Disimpan untuk kebutuhan sorting
            })
            
        sftp.close()
        
        # --- PROSES SORTING DI SINI ---
        # Mengurutkan berdasarkan 'priority' (1 ke 3), lalu berdasarkan nama folder (A-Z)
        report.sort(key=lambda x: (x["priority"], x["folder_name"]))
        
    except Exception as e:
        return {"error": f"Gagal koneksi SSH ke {SSH_HOST}:{SSH_PORT} -> {str(e)}", "data": []}
    finally:
        ssh.close()
        
    return {"error": None, "data": report}

# Template Dashboard HTML menggunakan Tailwind CSS (Dark Mode)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SSH Remote Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <meta http-equiv="refresh" content="60"> </head>
<body class="bg-gray-900 text-gray-100 font-sans p-8">
    <div class="max-w-5xl mx-auto">
        <header class="mb-8 flex justify-between items-center border-b border-gray-700 pb-4">
            <div>
                <h1 class="text-3xl font-bold text-white tracking-tight">🖥️ Remote SSH Directory Monitor</h1>
                <p class="text-gray-400 text-sm mt-1">Memantau server: <span class="font-mono text-amber-400">{{ ssh_info }}</span></p>
            </div>
            <div class="text-right">
                <span class="text-xs bg-gray-800 px-3 py-1.5 rounded text-gray-400 font-mono">Target: {{ date_today }}</span>
            </div>
        </header>

        {% if error_msg %}
        <div class="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-lg mb-6">
            <strong>⚠️ Error:</strong> {{ error_msg }}
        </div>
        {% endif %}

        <div class="overflow-x-auto bg-gray-800 rounded-lg shadow-xl border border-gray-700">
            <table class="w-full text-left border-collapse">
                <thead>
                    <tr class="bg-gray-750 text-gray-300 uppercase text-xs tracking-wider border-b border-gray-700">
                        <th class="py-4 px-6 font-semibold">Nama Direktori</th>
                        <th class="py-4 px-6 font-semibold text-center">Content CSV</th>
                        <th class="py-4 px-6 font-semibold text-center">Index CSV</th>
                        <th class="py-4 px-6 font-semibold text-center">Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-750">
                    {% for item in data %}
                    <tr class="hover:bg-gray-700/50 transition-colors">
                        <td class="py-3.5 px-6 font-mono text-sm text-gray-200">{{ item.folder_name }}</td>
                        <td class="py-3.5 px-6 text-center">
                            {% if item.content_updated %}
                                <span class="bg-green-900/40 text-green-400 text-xs px-2.5 py-1 rounded-full font-medium border border-green-800/60">Updated</span>
                            {% else %}
                                <span class="bg-red-900/40 text-red-400 text-xs px-2.5 py-1 rounded-full font-medium border border-red-800/60">Missing</span>
                            {% endif %}
                        </td>
                        <td class="py-3.5 px-6 text-center">
                            {% if item.index_updated %}
                                <span class="bg-green-900/40 text-green-400 text-xs px-2.5 py-1 rounded-full font-medium border border-green-800/60">Updated</span>
                            {% else %}
                                <span class="bg-red-900/40 text-red-400 text-xs px-2.5 py-1 rounded-full font-medium border border-red-800/60">Missing</span>
                            {% endif %}
                        </td>
                        <td class="py-3.5 px-6 text-center">
                            {% if item.status == 'OK' %}
                                <span class="w-3 h-3 rounded-full bg-green-500 inline-block shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
                            {% elif item.status == 'PARTIAL' %}
                                <span class="w-3 h-3 rounded-full bg-yellow-500 inline-block shadow-[0_0_8px_rgba(234,179,8,0.6)]"></span>
                            {% else %}
                                <span class="w-3 h-3 rounded-full bg-red-500 inline-block shadow-[0_0_8px_rgba(239,68,68,0.6)]"></span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    result = get_remote_directory_status()
    date_today = datetime.now().strftime("%d %B %Y")
    ssh_info = f"{SSH_USER}@{SSH_HOST}:{SSH_PORT}"
    return render_template_string(
        HTML_TEMPLATE, 
        data=result["data"], 
        error_msg=result["error"], 
        date_today=date_today,
        ssh_info=ssh_info
    )

if __name__ == '__main__':
    # Berjalan di port 5000 server lokal Anda
    app.run(host='0.0.0.0', port=5000, debug=True)