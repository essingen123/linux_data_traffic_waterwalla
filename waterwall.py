import os
import subprocess
import json
import webbrowser
from flask import Flask, request, jsonify, send_from_directory
import logging

# Author: Kilian Lindberg
# License: MIT+%303*

try:
    import psutil
except ImportError:
    import sys
    sys.path.append('/usr/lib/python3/dist-packages')
    import psutil

app = Flask(__name__)

# File to store the state
STATE_FILE = 'waterwall_state.json'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check if the script is run as root
def check_root():
    if os.geteuid() != 0:
        logger.error("This script must be run as root. Please use 'sudo' to run the script.")
        logger.error("To preserve your aliases, run the script with: sudo -E python waterwall.py")
        exit(1)

# Load the state from the file
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save the state to the file
def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# Get a list of all running processes
def get_processes():
    return [p.info for p in psutil.process_iter(['pid', 'name'])]

# Block traffic for a specific process
def block_process(pid):
    subprocess.run(["iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", str(pid), "-j", "DROP"])

# Unblock traffic for a specific process
def unblock_process(pid):
    subprocess.run(["iptables", "-D", "OUTPUT", "-m", "owner", "--uid-owner", str(pid), "-j", "DROP"])

# Set traffic limit for a process (as a percentage of total bandwidth)
def set_traffic_limit(pid, percentage):
    bandwidth_limit = int(1024 * 1024 * percentage / 100)  # Convert to bytes per second
    subprocess.run(["iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", str(pid), "-m", "limit", "--limit-burst", str(bandwidth_limit), "-j", "ACCEPT"])

# Get the current traffic usage for a process
def get_traffic_usage(pid):
    try:
        p = psutil.Process(pid)
        io_counters = p.io_counters()
        return io_counters.read_bytes + io_counters.write_bytes
    except psutil.NoSuchProcess:
        logger.warning(f"Process with PID {pid} no longer exists.")
        return 0
    except psutil.AccessDenied:
        raise PermissionError("Permission denied. Please run with sudo.")

@app.route('/processes', methods=['GET'])
def list_processes():
    try:
        processes = get_processes()
        process_info = []
        state = load_state()
        for p in processes:
            pid = p['pid']
            name = p['name']
            traffic_usage = get_traffic_usage(pid)
            traffic_usage_mb = traffic_usage / (1024 * 1024)
            process_info.append({'pid': pid, 'name': name, 'traffic_usage': traffic_usage, 'traffic_usage_mb': traffic_usage_mb, 'blocked': state.get(pid, {}).get('blocked', False), 'limit': state.get(pid, {}).get('limit', None)})

        # Sort processes by traffic usage
        sort_order = request.args.get('sort', 'desc')
        process_info.sort(key=lambda x: x['traffic_usage'], reverse=(sort_order == 'desc'))

        return jsonify(process_info)
    except PermissionError as e:
        logger.error(str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/block', methods=['POST'])
def block():
    pid = request.json.get('pid')
    block_process(pid)
    state = load_state()
    state[pid] = {'blocked': True, 'limit': None}
    save_state(state)
    return jsonify({'status': 'success'})

@app.route('/unblock', methods=['POST'])
def unblock():
    pid = request.json.get('pid')
    unblock_process(pid)
    state = load_state()
    state[pid] = {'blocked': False, 'limit': None}
    save_state(state)
    return jsonify({'status': 'success'})

@app.route('/limit', methods=['POST'])
def limit():
    pid = request.json.get('pid')
    percentage = request.json.get('percentage')
    set_traffic_limit(pid, percentage)
    state = load_state()
    state[pid] = {'blocked': False, 'limit': percentage}
    save_state(state)
    return jsonify({'status': 'success'})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

def create_static_files():
    os.makedirs('static', exist_ok=True)

    # Create index.html
    with open('static/index.html', 'w') as f:
        f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WaterWall Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bulma/0.9.4/css/bulma.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/spin.js/2.3.2/spin.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            transition: background-color 0.5s, color 0.5s;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        table, th, td {
            border: 1px solid black;
        }
        th, td {
            padding: 8px;
            text-align: left;
        }
        canvas {
            max-width: 100%;
            height: auto;
        }
        #intervalInput {
            margin-right: 10px;
        }
        #analyzeButton, #intruderButton, #darkModeButton, #colorButton, #confettiButton, #synthesizeButton, #refreshButton {
            margin-top: 20px;
            margin-right: 10px;
        }
        #analysisTextarea {
            display: none;
            width: 100%;
            height: 200px;
        }
        @keyframes shake {
            0% { transform: translate(1px, 1px) rotate(0deg); }
            10% { transform: translate(-1px, -2px) rotate(-1deg); }
            20% { transform: translate(-3px, 0px) rotate(1deg); }
            30% { transform: translate(3px, 2px) rotate(0deg); }
            40% { transform: translate(1px, -1px) rotate(1deg); }
            50% { transform: translate(-1px, 2px) rotate(-1deg); }
            60% { transform: translate(-3px, 1px) rotate(0deg); }
            70% { transform: translate(3px, 1px) rotate(-1deg); }
            80% { transform: translate(-1px, -1px) rotate(1deg); }
            90% { transform: translate(1px, 2px) rotate(0deg); }
            100% { transform: translate(1px, -2px) rotate(-1deg); }
        }
        @keyframes gradient {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .loading {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10000;
        }
        .loading .spinner {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 50px;
            height: 50px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <section class="section">
        <div class="container">
            <h1 class="title">WaterWall Control</h1>
            <div class="buttons">
                <button class="button is-primary" onclick="refreshData()">Refresh</button>
                <button class="button is-dark" onclick="toggleDarkMode()">Toggle Dark Mode</button>
                <button class="button is-info" onclick="analyzeCyberSpaceHaze()">AI Analyze Cyber Space Haze</button>
                <button class="button is-warning" onclick="intruderWaterPlay()">IntruderWaterPlay</button>
                <button class="button is-danger" onclick="confettiEffect()">Confetti</button>
                <button class="button is-success" onclick="synthesizeLFOEnvenlopeEqualizerNoiseVocoderFFTDataStream()">Synthesize LFO Envelope Equalizer Noise Vocoder FFT Data Stream</button>
                <button class="button is-link" onclick="changeBackgroundColor()">Random Color</button>
            </div>
            <div>
                <label for="intervalInput">Refresh Interval (ms):</label>
                <input type="number" id="intervalInput" value="5000">
                <button onclick="setIntervalTime()">Set Interval</button>
            </div>
            <canvas id="trafficChart"></canvas>
            <table id="processTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">PID [A]/[D]</th>
                        <th onclick="sortTable(1)">Name [A]/[D]</th>
                        <th onclick="sortTable(2)">Traffic Usage (bytes) [A]/[D]</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
            <textarea id="analysisTextarea"></textarea>
            <div class="loading">
                <div class="spinner"></div>
            </div>
        </div>
    </section>
    <script>
        const dgei = document.getElementById.bind(document);
        const dqsel = document.querySelector.bind(document);
        const dqselAll = document.querySelectorAll.bind(document);

        let intervalTime = 5000;
        let intervalId;
        let isDarkMode = false;
        let colorIndex = 0;
        let sortOrder = 'desc';
        const colorSchemes = [
            { bg: '#f8f9fa', text: '#212529' },
            { bg: '#e9ecef', text: '#343a40' },
            { bg: '#dee2e6', text: '#495057' },
            { bg: '#ced4da', text: '#6c757d' },
            { bg: '#adb5bd', text: '#868e96' }
        ];

        async function fetchProcesses() {
            dqsel('.loading').style.display = 'block';
            const response = await fetch(`/processes?sort=${sortOrder}`);
            const processes = await response.json();
            if (processes.error) {
                alert(processes.error);
                return;
            }
            const tableBody = dqsel('#processTable tbody');
            tableBody.innerHTML = '';
            processes.forEach(process => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${process.pid}</td>
                    <td>${process.name}</td>
                    <td>${process.traffic_usage} bytes (${process.traffic_usage_mb.toFixed(2)} MB)</td>
                    <td>
                        <button ${process.blocked ? 'disabled' : ''} onclick="blockProcess(${process.pid})">Block</button>
                        <button ${!process.blocked ? 'disabled' : ''} onclick="unblockProcess(${process.pid})">Unblock</button>
                        <input type="number" id="limit${process.pid}" min="0" max="100" placeholder="Limit %" value="${process.limit || ''}">
                        <button onclick="setLimit(${process.pid})">Set Limit</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
            updateChart(processes);
            dqsel('.loading').style.display = 'none';
        }

        async function blockProcess(pid) {
            await fetch('/block', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ pid })
            });
            fetchProcesses();
        }

        async function unblockProcess(pid) {
            await fetch('/unblock', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ pid })
            });
            fetchProcesses();
        }

        async function setLimit(pid) {
            const limit = dgei(`limit${pid}`).value;
            await fetch('/limit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ pid, percentage: limit })
            });
            fetchProcesses();
        }

        function updateChart(processes) {
            const labels = processes.map(p => p.name);
            const data = processes.map(p => p.traffic_usage);
            const ctx = dgei('trafficChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Traffic Usage (bytes)',
                        data: data,
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        function setIntervalTime() {
            clearInterval(intervalId);
            intervalTime = parseInt(dgei('intervalInput').value, 10);
            intervalId = setInterval(fetchProcesses, intervalTime);
        }

        function sortTable(columnIndex) {
            const table = dgei('processTable');
            const rows = Array.from(table.rows).slice(1);
            const isNumber = columnIndex === 0 || columnIndex === 2;
            rows.sort((a, b) => {
                const aValue = a.cells[columnIndex].textContent.trim();
                const bValue = b.cells[columnIndex].textContent.trim();
                if (isNumber) {
                    return (sortOrder === 'asc' ? 1 : -1) * (parseInt(aValue, 10) - parseInt(bValue, 10));
                } else {
                    return (sortOrder === 'asc' ? 1 : -1) * aValue.localeCompare(bValue);
                }
            });
            rows.forEach(row => table.tBodies[0].appendChild(row));
            sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
        }

        function analyzeCyberSpaceHaze() {
            const textarea = dgei('analysisTextarea');
            textarea.style.display = 'block';
            textarea.value = JSON.stringify(fetchProcesses(), null, 2);
        }

        function intruderWaterPlay() {
            alert("Surprise! You've been caught watching!");
            document.body.style.animation = 'shake 0.5s';
            setTimeout(() => {
                document.body.style.animation = '';
            }, 500);
        }

        function toggleDarkMode() {
            isDarkMode = !isDarkMode;
            document.body.style.backgroundColor = isDarkMode ? '#333' : '#fff';
            document.body.style.color = isDarkMode ? '#fff' : '#000';
        }

        function changeBackgroundColor() {
            const randomColor = '#' + Math.floor(Math.random() * 16777215).toString(16);
            document.body.style.backgroundColor = randomColor;
        }

        function confettiEffect() {
            const confetti = document.createElement('div');
            confetti.style.position = 'absolute';
            confetti.style.top = '0';
            confetti.style.left = '0';
            confetti.style.width = '100%';
            confetti.style.height = '100%';
            confetti.style.background = 'url("https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif") no-repeat center center';
            confetti.style.backgroundSize = 'cover';
            confetti.style.zIndex = '9999';
            document.body.appendChild(confetti);
            setTimeout(() => {
                document.body.removeChild(confetti);
            }, 3000);
        }

        function synthesizeLFOEnvenlopeEqualizerNoiseVocoderFFTDataStream() {
            alert("Synthesizing LFO Envelope Equalizer Noise Vocoder FFT Data Stream...");
            document.body.style.background = 'linear-gradient(45deg, #ff00ff, #00ffff, #ffff00, #ff00ff, #00ffff, #ffff00)';
            document.body.style.backgroundSize = '400% 400%';
            document.body.style.animation = 'gradient 5s ease infinite';
            setTimeout(() => {
                document.body.style.background = '';
                document.body.style.animation = '';
            }, 5000);
        }

        function changeColorScheme() {
            colorIndex = (colorIndex + 1) % colorSchemes.length;
            const scheme = colorSchemes[colorIndex];
            document.body.style.backgroundColor = scheme.bg;
            document.body.style.color = scheme.text;
        }

        fetchProcesses();
        intervalId = setInterval(fetchProcesses, intervalTime);
        setInterval(changeColorScheme, 30000); // Change color scheme every 30 seconds
    </script>
</body>
</html>

''')

def elevate_permissions():
    logger.info("Elevating permissions...")
    subprocess.run(['sudo', 'python', __file__])

if __name__ == '__main__':
    check_root()
    create_static_files()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=True)