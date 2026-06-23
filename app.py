import os
from dotenv import load_dotenv
load_dotenv()

import csv
import json as json_lib
import io
import uuid
from functools import wraps
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify, make_response, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from reportlab.pdfgen import canvas

from models import db, User
from database import (
    init_db, save_log_metadata, get_log_metadata, create_user, 
    get_user_by_username, get_user_by_id, get_user_history,
    get_alert_rules, add_alert_rule, delete_alert_rule, 
    create_active_alert, get_active_alerts, clear_active_alerts,
    get_global_stats
)
from analyzer import parse_log
from ai_helper import (
    generate_insights,
    generate_incident_report,
    answer_question,
    get_severity,
    generate_security_scores,
    generate_root_cause_analysis
)

app = Flask(__name__)
app.secret_key = 'super_secret_noc_key_2025'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///logs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
init_db(app)

# Train ML model on startup
with app.app_context():
    from models import LogHistory
    from ml_engine import train_anomaly_model
    historical_logs = LogHistory.query.all()
    if train_anomaly_model(historical_logs):
        print("ML Anomaly Detection Model trained successfully on historical data.")
    else:
        print("Not enough historical data to train ML Anomaly Detection Model.")

socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize DB
init_db(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Administrator privileges required to perform this action.', 'danger')
            return redirect(url_for('dashboard_view'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

analysis_store = {}

ALLOWED_EXTENSIONS = {'log', 'txt', 'json', 'har'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    stats = get_global_stats()
    return render_template('landing.html', stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('app_main'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(id=user['id'], username=user['username'])
            login_user(user_obj)
            return redirect(url_for('app_main'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('app_main'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed = generate_password_hash(password)
        if create_user(username, hashed):
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Username already exists.', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/app')
def app_main():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard_view():
    analysis_id = session.get('analysis_id')
    if not analysis_id or analysis_id not in analysis_store:
        flash('Please upload a log file or run a simulation first.', 'info')
        return redirect(url_for('app_main'))
        
    store = analysis_store[analysis_id]
    
    scores = generate_security_scores(store['counts'], store['anomalies'])
    
    # We pass the existing data to dashboard.html
    return render_template(
        'dashboard.html',
        metadata={'filename': store['filename']},
        counts=store['counts'],
        issues=store['issues'][:100],
        anomalies=store['anomalies'],
        top_ips=store['top_ips'],
        analysis_id=analysis_id,
        insights=store['insights'],
        severity="Calculated",
        total_events=sum(store['counts'].values()),
        security_score=scores['overall'],
        scores=scores,
        root_cause="Analyzed",
        executive_summary="Dashboard view activated.",
        critical_findings=store['issues'][:5]
    )

@app.route('/explorer')
def explorer():
    analysis_id = session.get('analysis_id')
    if not analysis_id or analysis_id not in analysis_store:
        flash('Please upload a log file or run a simulation first to explore logs.', 'info')
        return redirect(url_for('app_main'))
        
    store = analysis_store[analysis_id]
    return render_template('explorer.html', issues=store['issues'], filename=store['filename'])

@app.route('/history')
@login_required
def history():
    history_records = get_user_history(current_user.id)
    return render_template('history.html', records=history_records)

@app.route('/docs')
def docs():
    return render_template('docs.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('app_main'))

    file = request.files['file']

    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('app_main'))

    if not allowed_file(file.filename):
        flash('Invalid file type', 'danger')
        return redirect(url_for('app_main'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    counts, issues, anomalies, top_ips = parse_log(filepath)

    user_id = current_user.id if current_user.is_authenticated else None
    log_id = save_log_metadata(filename, counts, user_id=user_id)
    metadata = get_log_metadata(log_id)

    insights = generate_insights(counts, issues, anomalies)
    severity = get_severity(counts, anomalies)
    
    # Evaluate Custom Log Alert Rules
    user_id = current_user.id if current_user.is_authenticated else None
    rules = get_alert_rules(user_id=user_id)
    for rule in rules:
        metric = rule['metric']
        # check if metric exists in counts
        val = counts.get(metric, 0)
        
        condition = rule['condition']
        threshold = float(rule['threshold'])
        
        triggered = False
        if condition == '>' and val > threshold: triggered = True
        elif condition == '<' and val < threshold: triggered = True
        elif condition == '==' and val == threshold: triggered = True
        
        if triggered:
            msg = f"Log file '{filename}' triggered rule: {metric} ({val}) {condition} {threshold}"
            create_active_alert(rule['id'], msg, user_id=user_id)

    analysis_id = str(log_id)

    total_events = sum(counts.values())

    scores = generate_security_scores(counts, anomalies)
    security_score = scores['overall']
    
    root_cause = generate_root_cause_analysis(counts, issues)

    executive_summary = (
        f"{counts.get('FAILED',0)} FAILED, "
        f"{counts.get('ERROR',0)} ERROR, "
        f"{counts.get('WARNING',0)} WARNING events detected. "
        f"Primary issue: {root_cause}"
    )

    analysis_store[analysis_id] = {
        'counts': counts,
        'issues': issues,
        'anomalies': anomalies,
        'top_ips': top_ips,
        'insights': insights,
        'filename': filename
    }

    session['analysis_id'] = analysis_id

    return render_template(
        'dashboard.html',
        metadata=metadata,
        counts=counts,
        issues=issues[:100],
        anomalies=anomalies,
        top_ips=top_ips,
        analysis_id=analysis_id,
        insights=insights,

        severity=severity,
        total_events=total_events,
        security_score=security_score,
        scores=scores,
        root_cause=root_cause,
        executive_summary=executive_summary,
        critical_findings=issues[:5]
    )


@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    question = data.get('question', '')
    analysis_id = data.get('analysis_id', session.get('analysis_id'))

    if not analysis_id or analysis_id not in analysis_store:
        return jsonify({'answer': 'Upload a log file first.'})

    store = analysis_store[analysis_id]

    return jsonify({
        'answer': answer_question(
            question,
            store['counts'],
            store['issues'],
            store['anomalies']
        )
    })


@app.route('/incident-report/<analysis_id>')
def incident_report(analysis_id):
    if analysis_id not in analysis_store:
        flash('Session expired', 'warning')
        return redirect(url_for('app_main'))

    store = analysis_store[analysis_id]

    report = generate_incident_report(
        store['counts'],
        store['issues'],
        store['insights'],
        store['anomalies'],
        store['filename']
    )

    return render_template('incident_report.html', report=report)


@app.route('/export/json/<analysis_id>')
def export_json(analysis_id):
    if analysis_id not in analysis_store:
        return jsonify({'error': 'Session expired'}), 404

    store = analysis_store[analysis_id]

    data = {
        'filename': store['filename'],
        'counts': store['counts'],
        'issues': store['issues'][:200],
        'anomalies': store['anomalies'],
        'top_ips': store['top_ips'],
        'insights': store['insights']
    }

    response = make_response(json_lib.dumps(data, indent=2))
    response.headers['Content-Disposition'] = f'attachment; filename=report_{store["filename"]}.json'
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route('/export/csv/<analysis_id>')
def export_csv(analysis_id):
    if analysis_id not in analysis_store:
        return "Session expired", 404

    store = analysis_store[analysis_id]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Line', 'Type', 'Content'])

    for issue in store['issues']:
        writer.writerow([issue['line_num'], issue['type'], issue['content']])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=report_{store["filename"]}.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


@app.route('/simulate/<scenario>')
def simulate(scenario):
    import random
    
    counts = {'ERROR': 0, 'WARNING': 0, 'FAILED': 0, 'TIMEOUT': 0}
    issues = []
    top_ips = {}
    
    public_ips = [
        "104.28.14.9", "185.199.108.153", "203.0.113.42", "198.51.100.14",
        "8.8.4.4", "172.64.144.12", "104.21.35.120", "54.192.83.11",
        "45.33.32.156", "13.248.118.1"
    ]
    
    for _ in range(5):
        ip = random.choice(public_ips)
        top_ips[ip] = random.randint(1500, 15000)
        public_ips.remove(ip)
    
    if scenario == 'brute_force':
        counts['FAILED'] = random.randint(3000, 8000)
        counts['WARNING'] = random.randint(100, 500)
        counts['ERROR'] = random.randint(10, 50)
        issues.append({'line_num': 1024, 'type': 'FAILED', 'content': 'Syslog Auth Failure: sshd[2314]: Failed password for root from 192.168.1.45 port 22'})
        issues.append({'line_num': 1025, 'type': 'FAILED', 'content': 'Apache/Nginx HTTP 401: POST /api/login HTTP/1.1'})
    elif scenario == 'server_crash':
        counts['ERROR'] = random.randint(1000, 5000)
        counts['TIMEOUT'] = random.randint(500, 2000)
        counts['WARNING'] = random.randint(200, 800)
        issues.append({'line_num': 4051, 'type': 'ERROR', 'content': 'Apache/Nginx HTTP 500: GET /api/data HTTP/1.1'})
        issues.append({'line_num': 4052, 'type': 'ERROR', 'content': 'Syslog Error: postgresql[551]: FATAL: connection to database failed'})
    elif scenario == 'dns_attack':
        counts['TIMEOUT'] = random.randint(4000, 10000)
        counts['WARNING'] = random.randint(1000, 3000)
        issues.append({'line_num': 892, 'type': 'TIMEOUT', 'content': 'Syslog Warning: named[412]: query (cache) denied'})
    elif scenario == 'router':
        counts['WARNING'] = random.randint(5000, 12000)
        counts['ERROR'] = random.randint(100, 500)
        issues.append({'line_num': 12, 'type': 'WARNING', 'content': 'Syslog Warning: kernel: eth0: link down'})
    else:
        flash('Invalid scenario', 'danger')
        return redirect(url_for('app_main'))

    anomalies = []
    insights = generate_insights(counts, issues, anomalies)
    severity = get_severity(counts, anomalies)
    scores = generate_security_scores(counts, anomalies)
    analysis_id = "simulated_" + scenario
    
    # Sort top IPs so they look realistic (descending)
    top_ips = dict(sorted(top_ips.items(), key=lambda item: item[1], reverse=True))

    analysis_store[analysis_id] = {
        'counts': counts,
        'issues': issues * 10,
        'anomalies': anomalies,
        'top_ips': top_ips,
        'insights': insights,
        'filename': f'simulated_{scenario}.log'
    }

    session['analysis_id'] = analysis_id

    # Evaluate rules on simulated data
    # Evaluate rules on simulated data
    user_id = current_user.id if current_user.is_authenticated else None
    rules = get_alert_rules(user_id=user_id)
    for rule in rules:
        metric = rule['metric']
        val = counts.get(metric, 0)
        condition = rule['condition']
        threshold = float(rule['threshold'])
        triggered = False
        if condition == '>' and val > threshold: triggered = True
        elif condition == '<' and val < threshold: triggered = True
        elif condition == '==' and val == threshold: triggered = True
        if triggered:
            msg = f"Simulated attack '{scenario}' triggered rule: {metric} ({val}) {condition} {threshold}"
            create_active_alert(rule['id'], msg, user_id=user_id)

    return redirect(url_for('dashboard_view'))

@app.route('/alerts', methods=['GET', 'POST'])
@login_required
def alerts():
    user_id = current_user.id
    if request.method == 'POST':
        if current_user.role != 'admin':
            flash('Admin role required to modify alerts.', 'danger')
            return redirect(url_for('alerts'))
            
        action = request.form.get('action')
        if action == 'add':
            metric = request.form.get('metric')
            condition = request.form.get('condition')
            threshold = request.form.get('threshold')
            webhook_url = request.form.get('webhook_url')
            if metric and condition and threshold:
                add_alert_rule(metric, condition, float(threshold), user_id=user_id, webhook_url=webhook_url)
                flash('Alert rule added.', 'success')
        elif action == 'delete':
            rule_id = request.form.get('rule_id')
            if rule_id:
                delete_alert_rule(int(rule_id))
                flash('Alert rule deleted.', 'info')
        elif action == 'clear':
            clear_active_alerts(user_id=user_id)
            flash('Active alerts cleared.', 'info')
        return redirect(url_for('alerts'))
        
    rules = get_alert_rules(user_id=user_id)
    active_alerts = get_active_alerts(user_id=user_id)
    return render_template('alerts.html', rules=rules, active_alerts=active_alerts)


@app.route('/export/pdf/<analysis_id>')
def export_pdf(analysis_id):
    # If the request comes from history page, the ID is log_id, not analysis_id.
    # Wait, history page generates `/export/pdf/{{ record.id }}`. We can use get_log_metadata directly for history.
    metadata = get_log_metadata(analysis_id)
    if not metadata:
        return "Log not found", 404

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"NetAssist AI - Security Report: {metadata['filename']}")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 770, f"Upload Time: {metadata['upload_time']}")
    p.drawString(100, 740, f"Errors: {metadata['error_count']}")
    p.drawString(100, 720, f"Warnings: {metadata['warning_count']}")
    p.drawString(100, 700, f"Failed Auth: {metadata['failed_count']}")
    p.drawString(100, 680, f"Timeouts: {metadata['timeout_count']}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=report_{metadata["filename"]}.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@socketio.on('register_agent')
def handle_register_agent(data):
    print(f"Agent registered: {data.get('agent_id')}")

@app.route('/api/logs/ingest', methods=['POST'])
def api_ingest_logs():
    data = request.get_json()
    if not data or 'log_content' not in data:
        return jsonify({'error': 'Missing log_content in JSON payload'}), 400
        
    content = data['log_content']
    filename = f"api_ingest_{uuid.uuid4().hex[:8]}.log"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    from analyzer import parse_log, generate_insights, get_severity, generate_security_scores
    counts, issues, anomalies, top_ips = parse_log(filepath)
    
    user_id = None
    # Support basic auth or token auth in future, for now anonymous/public
    
    log_id = save_log_metadata(filename, counts, user_id=user_id)
    insights = generate_insights(counts, issues, anomalies)
    severity = get_severity(counts, anomalies)
    scores = generate_security_scores(counts, anomalies)
    
    analysis_id = str(log_id)
    analysis_store[analysis_id] = {
        'counts': counts,
        'issues': issues,
        'anomalies': anomalies,
        'top_ips': top_ips,
        'insights': insights,
        'filename': filename
    }
    
    # Evaluate Rules Globally for API
    rules = get_alert_rules(user_id=None)
    for rule in rules:
        metric = rule['metric']
        val = counts.get(metric, 0)
        condition = rule['condition']
        threshold = float(rule['threshold'])
        triggered = False
        if condition == '>' and val > threshold: triggered = True
        elif condition == '<' and val < threshold: triggered = True
        elif condition == '==' and val == threshold: triggered = True
        if triggered:
            msg = f"API Ingest '{filename}' triggered rule: {metric} ({val}) {condition} {threshold}"
            create_active_alert(rule['id'], msg, user_id=rule.get('user_id'))
            
    return jsonify({
        'status': 'success',
        'analysis_id': analysis_id,
        'severity': severity,
        'scores': scores,
        'insights': insights
    })

@socketio.on('agent_telemetry')
def handle_agent_telemetry(data):
    # Evaluate Alert Rules
    rules = get_alert_rules()
    for rule in rules:
        metric = rule['metric']
        val = data.get(metric)
        if val is not None:
            trigger = False
            if rule['condition'] == '>' and val > rule['threshold']: trigger = True
            elif rule['condition'] == '<' and val < rule['threshold']: trigger = True
            
            if trigger:
                msg = f"Alert: {metric} is {val:.1f} (Threshold: {rule['condition']} {rule['threshold']})"
                create_active_alert(rule['id'], msg, user_id=rule['user_id'])
                
                # Push real-time alert to UI
                socketio.emit('new_alert', {'message': msg, 'metric': metric, 'user_id': rule['user_id']})

    # Broadcast to all connected web clients
    emit('telemetry_update', data, broadcast=True)

@socketio.on('request_diagnostic')
def handle_request_diagnostic(data):
    # Web client requests a diagnostic. Relay to agents.
    print(f"Requesting diagnostic from agents: {data}")
    socketio.emit('run_diagnostic', data)

@socketio.on('run_diagnostic')
def handle_run_diagnostic(data):
    # Dummy mock diagnostic logic for demonstration
    target_ip = data.get('ip')
    import time
    time.sleep(2)
    emit('diagnostic_response', {
        'status': 'Success', 
        'output': f'PING {target_ip} 56(84) bytes of data.\n64 bytes from {target_ip}: icmp_seq=1 ttl=119 time=14.2 ms'
    })

@socketio.on('diagnostic_result')
def handle_diagnostic_result(data):
    # Agent sends back diagnostic result. Relay to web clients.
    socketio.emit('diagnostic_response', data)

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Missing query'}), 400
        
    user_id = current_user.id
    alerts = get_active_alerts(user_id=user_id)
    
    from ai_engine import ask_ai_root_cause
    response_text = ask_ai_root_cause(query, alerts)
    
    return jsonify({'response': response_text})

# --- Live Log Streaming Background Task (Phase 4) ---
import threading
import time
import random

def live_log_stream_thread():
    import datetime
    public_ips = ["104.28.14.9", "185.199.108.153", "8.8.4.4", "172.64.144.12", "13.248.118.1"]
    types = ['ERROR', 'WARNING', 'FAILED', 'TIMEOUT']
    
    while True:
        time.sleep(3)
        log_type = random.choice(types)
        ip = random.choice(public_ips)
        messages = {
            'ERROR': f'Syslog Error: postgresql[551]: FATAL: connection to database failed from {ip}',
            'WARNING': f'Apache/Nginx HTTP 404: GET /api/data HTTP/1.1 from {ip}',
            'FAILED': f'Syslog Auth Failure: sshd[2314]: Failed password for root from {ip} port 22',
            'TIMEOUT': f'Syslog Warning: named[412]: query (cache) denied from {ip}'
        }
        
        payload = {
            'type': log_type,
            'message': messages[log_type],
            'timestamp': datetime.datetime.utcnow().strftime('%H:%M:%S'),
            'ip': ip
        }
        
        # ML Anomaly Detection Integration
        from ml_engine import predict_anomaly
        from database import create_active_alert
        
        # Simulate extracted features from the live log message
        error_count = 100 if log_type == 'ERROR' else 0
        warning_count = 500 if log_type == 'WARNING' else 0
        
        # Score the event
        if predict_anomaly(error_count, warning_count):
            with app.app_context():
                # Automatically trigger a Critical ActiveAlert for anomalies
                create_active_alert(
                    rule_id=None, # System generated ML anomaly
                    message=f"ML Anomaly Detected: Highly unusual {log_type} activity from {ip}",
                    user_id=None 
                )
        
        socketio.emit('live_log_stream', payload)

stream_thread = threading.Thread(target=live_log_stream_thread, daemon=True)
stream_thread.start()

# --- Start Syslog UDP Server ---
try:
    from syslog_server import start_syslog_server
    syslog_thread = threading.Thread(target=start_syslog_server, daemon=True)
    syslog_thread.start()
except ImportError as e:
    print(f"Syslog server module not found: {e}")

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)