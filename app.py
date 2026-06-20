import os
import csv
import json as json_lib
import io
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify, make_response
from werkzeug.utils import secure_filename

from database import init_db, save_log_metadata, get_log_metadata
from analyzer import parse_log
from ai_helper import (
    generate_insights,
    generate_incident_report,
    answer_question,
    get_severity
)

app = Flask(__name__)
app.secret_key = 'super_secret_noc_key_2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
init_db()

analysis_store = {}

ALLOWED_EXTENSIONS = {'log', 'txt', 'json'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('landing.html')

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
        security_score=85,
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

    log_id = save_log_metadata(filename, counts)
    metadata = get_log_metadata(log_id)

    insights = generate_insights(counts, issues, anomalies)
    severity = get_severity(counts, anomalies)

    analysis_id = str(log_id)

    total_events = sum(counts.values())

    security_score = max(
        0,
        100
        - counts.get('ERROR', 0) * 5
        - counts.get('FAILED', 0) * 3
        - counts.get('WARNING', 0) * 2
    )

    root_cause = "System stable"

    if counts.get('FAILED', 0) >= 3:
        root_cause = "Brute-force authentication activity detected"
    elif counts.get('ERROR', 0) >= 3:
        root_cause = "Service instability / runtime errors"
    elif counts.get('TIMEOUT', 0) >= 3:
        root_cause = "Network latency or upstream failure"

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
    sim_logs = {
        'brute_force': 'brute_force_attack.log',
        'server_crash': 'server_outage.log',
        'dns_attack': 'dns_attack.log',
        'router': 'router_issue.log'
    }

    file = sim_logs.get(scenario)

    if not file:
        flash('Invalid scenario', 'danger')
        return redirect(url_for('app_main'))

    path = os.path.join('sample_logs', file)

    if not os.path.exists(path):
        flash('Sample log missing', 'danger')
        return redirect(url_for('app_main'))

    counts, issues, anomalies, top_ips = parse_log(path)

    log_id = save_log_metadata(file, counts)
    metadata = get_log_metadata(log_id)

    insights = generate_insights(counts, issues, anomalies)
    severity = get_severity(counts, anomalies)

    analysis_id = str(log_id)

    analysis_store[analysis_id] = {
        'counts': counts,
        'issues': issues,
        'anomalies': anomalies,
        'top_ips': top_ips,
        'insights': insights,
        'filename': file
    }

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
        total_events=sum(counts.values()),
        security_score=100,
        root_cause="Simulation mode",
        executive_summary="Simulated dataset loaded.",
        critical_findings=issues[:5]
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)