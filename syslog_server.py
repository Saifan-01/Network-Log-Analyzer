import socketserver
import re
import datetime

# Regex to parse standard syslog (RFC 3164/5424 simplified)
# Format: <PRI>TIMESTAMP HOSTNAME MESSAGE
SYSLOG_REGEX = re.compile(r'^(?:<(\d+)>)?(?:([A-Z][a-z]{2}\s+\d+\s+\d+:\d+:\d+)|([^\s]+))\s+([^\s]+)\s+(.*)$')

class SyslogUDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        from app import app, socketio
        from database import db, save_log_metadata
        
        data = self.request[0].strip().decode('utf-8', errors='ignore')
        client_ip = self.client_address[0]
        
        # Determine log type based on content
        log_type = 'INFO'
        if 'error' in data.lower() or 'fatal' in data.lower():
            log_type = 'ERROR'
        elif 'warning' in data.lower():
            log_type = 'WARNING'
        elif 'fail' in data.lower() or 'denied' in data.lower():
            log_type = 'FAILED'
            
        payload = {
            'type': log_type,
            'message': data,
            'timestamp': datetime.datetime.utcnow().strftime('%H:%M:%S'),
            'ip': client_ip
        }
        
        # Broadcast to dashboard
        socketio.emit('live_log_stream', payload)
        
        # Save to database (as a general log stat)
        with app.app_context():
            counts = {'error': 0, 'warning': 0, 'failed': 0, 'timeout': 0}
            if log_type == 'ERROR': counts['error'] += 1
            if log_type == 'WARNING': counts['warning'] += 1
            if log_type == 'FAILED': counts['failed'] += 1
            
            # Save it under a generic syslog filename
            save_log_metadata(f"syslog_{datetime.datetime.utcnow().strftime('%Y%m%d')}.log", counts, user_id=None)

def start_syslog_server(host='0.0.0.0', port=5140):
    try:
        server = socketserver.UDPServer((host, port), SyslogUDPHandler)
        print(f"Starting UDP Syslog Server on {host}:{port}")
        server.serve_forever()
    except OSError as e:
        print(f"UDP Port {port} is likely already in use (common with Flask reloader). Syslog server not starting in this thread.")
