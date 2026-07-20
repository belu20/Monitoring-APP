from flask import Flask, render_template_string
import os
import re
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
    
    report = []
    
    if not SSH_HOST or not SSH_USER:
        return {"error": "Kredensial SSH di file .env belum lengkap!", "data": []}

    # Inisialisasi koneksi SSH
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASSWORD, timeout=10)
        
        # Menggunakan query SSH tunggal untuk performa optimal (mengurangi latency roundtrip SFTP)
        cmd = f"""
        for d in {BASE_DIR}/*; do
            if [ -d "$d" ]; then
                folder_name=$(basename "$d")
                has_content=0
                has_index=0
                [ -f "$d/content-{today_str}.csv" ] && has_content=1
                [ -f "$d/index-{today_str}.csv" ] && has_index=1
                
                latest_content=$(find "$d" -maxdepth 1 -type f -name "content-*.csv" | sort | tail -n 1)
                if [ -n "$latest_content" ]; then
                    content_mtime=$(stat -c "%y" "$latest_content" | cut -d'.' -f1)
                else
                    content_mtime="-"
                fi
                
                latest_index=$(find "$d" -maxdepth 1 -type f -name "index-*.csv" | sort | tail -n 1)
                if [ -n "$latest_index" ]; then
                    index_mtime=$(stat -c "%y" "$latest_index" | cut -d'.' -f1)
                else
                    index_mtime="-"
                fi
                echo "$folder_name|$has_content|$has_index|$content_mtime|$index_mtime"
            fi
        done
        """
        
        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode('utf-8')
        err_output = stderr.read().decode('utf-8')
        
        if err_output and not output:
            return {"error": f"Error remote server: {err_output}", "data": []}
            
        lines = output.strip().split("\n")
        for line in lines:
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 5:
                continue
            folder, has_content, has_index, content_mtime, index_mtime = parts
            
            content_updated = (has_content == "1")
            index_updated = (has_index == "1")
            
            if content_updated and index_updated:
                status = "OK"
                priority = 1
            elif content_updated or index_updated:
                status = "PARTIAL"
                priority = 2
            else:
                status = "CRITICAL"
                priority = 3
                
            # Ekstrak tanggal dan jam terakhir data masuk untuk content
            content_last_date = "-"
            if content_mtime and content_mtime != "-":
                try:
                    dt = datetime.strptime(content_mtime, "%Y-%m-%d %H:%M:%S")
                    content_last_date = dt.strftime("%d %b %Y %H:%M:%S")
                except Exception:
                    content_last_date = content_mtime
                    
            # Ekstrak tanggal dan jam terakhir data masuk untuk index
            index_last_date = "-"
            if index_mtime and index_mtime != "-":
                try:
                    dt = datetime.strptime(index_mtime, "%Y-%m-%d %H:%M:%S")
                    index_last_date = dt.strftime("%d %b %Y %H:%M:%S")
                except Exception:
                    index_last_date = index_mtime
                    
            report.append({
                "folder_name": folder,
                "content_updated": content_updated,
                "index_updated": index_updated,
                "status": status,
                "priority": priority,
                "content_last_date": content_last_date,
                "index_last_date": index_last_date
            })
            
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
                            <div>
                                {% if item.content_updated %}
                                    <span class="bg-green-900/40 text-green-400 text-xs px-2.5 py-1 rounded-full font-medium border border-green-800/60">Updated</span>
                                {% else %}
                                    <span class="bg-red-900/40 text-red-400 text-xs px-2.5 py-1 rounded-full font-medium border border-red-800/60">Missing</span>
                                {% endif %}
                            </div>
                            <div class="text-[11px] text-gray-400 font-mono mt-1.5">
                                {% if item.content_last_date != '-' %}
                                    {{ item.content_last_date }}
                                {% else %}
                                    <span class="text-gray-600">-</span>
                                {% endif %}
                            </div>
                        </td>
                        <td class="py-3.5 px-6 text-center">
                            <div>
                                {% if item.index_updated %}
                                    <span class="bg-green-900/40 text-green-400 text-xs px-2.5 py-1 rounded-full font-medium border border-green-800/60">Updated</span>
                                {% else %}
                                    <span class="bg-red-900/40 text-red-400 text-xs px-2.5 py-1 rounded-full font-medium border border-red-800/60">Missing</span>
                                {% endif %}
                            </div>
                            <div class="text-[11px] text-gray-400 font-mono mt-1.5">
                                {% if item.index_last_date != '-' %}
                                    {{ item.index_last_date }}
                                {% else %}
                                    <span class="text-gray-600">-</span>
                                {% endif %}
                            </div>
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