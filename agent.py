import time
import json
import threading
import socket
import socketio
try:
    import psutil
except ImportError:
    print("Please install psutil: pip install psutil")
    exit(1)
try:
    from ping3 import ping
except ImportError:
    print("Please install ping3: pip install ping3")
    exit(1)

# Configuration
SERVER_URL = "http://127.0.0.1:5000"
AGENT_ID = socket.gethostname()
INTERVAL_SECONDS = 2

sio = socketio.Client()

def get_system_metrics():
    net_io = psutil.net_io_counters()
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()

    return {
        "agent_id": AGENT_ID,
        "timestamp": time.time(),
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "bytes_sent": net_io.bytes_sent,
        "bytes_recv": net_io.bytes_recv
    }

@sio.event
def connect():
    print(f"Connected to Dashboard at {SERVER_URL}")
    sio.emit('register_agent', {'agent_id': AGENT_ID})

@sio.event
def disconnect():
    print("Disconnected from Dashboard")

@sio.on('run_diagnostic')
def on_run_diagnostic(data):
    target = data.get('target', '8.8.8.8')
    diag_type = data.get('type', 'ping')
    print(f"Received diagnostic request: {diag_type} on {target}")
    
    result = {"target": target, "type": diag_type, "agent_id": AGENT_ID}
    
    if diag_type == 'ping':
        try:
            latency = ping(target, timeout=2)
            if latency is None:
                result['status'] = 'Failed'
                result['output'] = 'Request timed out'
            elif latency is False:
                result['status'] = 'Error'
                result['output'] = 'Unknown host'
            else:
                result['status'] = 'Success'
                result['output'] = f'Latency: {latency * 1000:.1f} ms'
        except Exception as e:
            result['status'] = 'Error'
            result['output'] = str(e)
            
    elif diag_type == 'dns':
        try:
            ip = socket.gethostbyname(target)
            result['status'] = 'Success'
            result['output'] = f'Resolved IP: {ip}'
        except Exception as e:
            result['status'] = 'Error'
            result['output'] = str(e)
            
    elif diag_type == 'portscan':
        port = int(data.get('port', 80))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        res = sock.connect_ex((target, port))
        if res == 0:
            result['status'] = 'Success'
            result['output'] = f'Port {port} is OPEN'
        else:
            result['status'] = 'Closed'
            result['output'] = f'Port {port} is CLOSED'
        sock.close()

    sio.emit('diagnostic_result', result)
    print(f"Diagnostic completed: {result['status']}")

def telemetry_loop():
    last_sent = 0
    last_recv = 0
    
    metrics = get_system_metrics()
    last_sent = metrics['bytes_sent']
    last_recv = metrics['bytes_recv']
    time.sleep(1)

    while True:
        if sio.connected:
            metrics = get_system_metrics()
            bw_sent = (metrics['bytes_sent'] - last_sent) / INTERVAL_SECONDS
            bw_recv = (metrics['bytes_recv'] - last_recv) / INTERVAL_SECONDS
            
            last_sent = metrics['bytes_sent']
            last_recv = metrics['bytes_recv']
            
            payload = {
                "agent_id": metrics['agent_id'],
                "cpu": metrics['cpu_percent'],
                "memory": metrics['memory_percent'],
                "upload_bps": bw_sent,
                "download_bps": bw_recv
            }
            
            sio.emit('agent_telemetry', payload)
            print(f"Sent telemetry: CPU={payload['cpu']}% MEM={payload['memory']}% UP={payload['upload_bps']/1024:.1f}KB/s DOWN={payload['download_bps']/1024:.1f}KB/s")
            
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    print(f"Starting NetAssist Agent '{AGENT_ID}'...")
    
    # Start telemetry thread
    t = threading.Thread(target=telemetry_loop, daemon=True)
    t.start()
    
    # Connect to server
    try:
        sio.connect(SERVER_URL)
        sio.wait()
    except Exception as e:
        print(f"Failed to connect: {e}")
