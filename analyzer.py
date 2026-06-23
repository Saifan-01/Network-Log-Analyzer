import re
import json
from collections import Counter

def parse_log(filepath):
    keywords = ['ERROR', 'WARNING', 'FAILED', 'TIMEOUT']
    counts = {kw: 0 for kw in keywords}
    issues = []
    ip_counter = Counter()

    ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    kw_pattern = re.compile(r'\b(' + '|'.join(keywords) + r')\b', re.IGNORECASE)
    
    # Advanced Formats
    apache_pattern = re.compile(r'(?P<ip>(?:\d{1,3}\.){3}\d{1,3}).*?"(?:[A-Z]+) .*? HTTP/.*?" (?P<status>\d{3}) ')
    syslog_pattern = re.compile(r'([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+([^:]+):\s+(.*)')

    # Auto-detect JSON and HAR formats
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if content.startswith('{') and '"log"' in content[:200] and '"entries"' in content[:200]:
            return parse_har_log(content)
        elif content.startswith('[') or content.startswith('{'):
            return parse_json_log(content)
    except Exception:
        pass

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                ips = ip_pattern.findall(line)
                for ip in ips:
                    ip_counter[ip] += 1

                # Try Apache/Nginx Match
                apache_match = apache_pattern.search(line)
                if apache_match:
                    status = int(apache_match.group('status'))
                    if status >= 500:
                        counts['ERROR'] += 1
                        issues.append({'line_num': line_num, 'type': 'ERROR', 'content': f"Apache/Nginx HTTP {status}: {line.strip()[:100]}..."})
                        continue
                    elif status >= 400:
                        counts['FAILED'] += 1
                        issues.append({'line_num': line_num, 'type': 'FAILED', 'content': f"Apache/Nginx HTTP {status}: {line.strip()[:100]}..."})
                        continue
                
                # Try Syslog Match
                syslog_match = syslog_pattern.search(line)
                if syslog_match:
                    message = syslog_match.group(3).lower()
                    if 'fail' in message or 'invalid' in message or 'denied' in message:
                        counts['FAILED'] += 1
                        issues.append({'line_num': line_num, 'type': 'FAILED', 'content': f"Syslog Auth Failure: {syslog_match.group(3)[:100]}..."})
                        continue
                    elif 'error' in message or 'crit' in message or 'fatal' in message:
                        counts['ERROR'] += 1
                        issues.append({'line_num': line_num, 'type': 'ERROR', 'content': f"Syslog Error: {syslog_match.group(3)[:100]}..."})
                        continue

                # Fallback to Generic Keyword Match
                match = kw_pattern.search(line)
                if match:
                    kw_found = match.group(1).upper()
                    counts[kw_found] += 1
                    issues.append({
                        'line_num': line_num,
                        'type': kw_found,
                        'content': line.strip()
                    })
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")

    anomalies = detect_anomalies(issues, ip_counter)
    top_ips = dict(ip_counter.most_common(5))
    return counts, issues, anomalies, top_ips


def parse_json_log(content):
    keywords = ['ERROR', 'WARNING', 'FAILED', 'TIMEOUT']
    counts = {kw: 0 for kw in keywords}
    issues = []
    ip_counter = Counter()
    kw_pattern = re.compile(r'\b(' + '|'.join(keywords) + r')\b', re.IGNORECASE)
    ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            data = [data]
        for idx, entry in enumerate(data, 1):
            line = json.dumps(entry)
            for ip in ip_pattern.findall(line):
                ip_counter[ip] += 1
            match = kw_pattern.search(line)
            if match:
                kw_found = match.group(1).upper()
                counts[kw_found] += 1
                issues.append({'line_num': idx, 'type': kw_found, 'content': line[:300]})
    except Exception as e:
        print(f"Error parsing JSON log: {e}")

    return counts, issues, detect_anomalies(issues, ip_counter), dict(ip_counter.most_common(5))

def parse_har_log(content):
    keywords = ['ERROR', 'WARNING', 'FAILED', 'TIMEOUT']
    counts = {kw: 0 for kw in keywords}
    issues = []
    ip_counter = Counter()

    try:
        data = json.loads(content)
        entries = data.get('log', {}).get('entries', [])
        for idx, entry in enumerate(entries, 1):
            req = entry.get('request', {})
            res = entry.get('response', {})
            url = req.get('url', '')
            status = res.get('status', 0)
            time_ms = entry.get('time', 0)
            
            # Simple IP extraction from URL if present
            ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
            for ip in ip_pattern.findall(url):
                ip_counter[ip] += 1
                
            if status >= 500:
                counts['ERROR'] += 1
                issues.append({'line_num': idx, 'type': 'ERROR', 'content': f"HTTP {status} on {url}"})
            elif status >= 400:
                counts['FAILED'] += 1
                issues.append({'line_num': idx, 'type': 'FAILED', 'content': f"HTTP {status} on {url}"})
            elif time_ms > 2000:
                counts['TIMEOUT'] += 1
                issues.append({'line_num': idx, 'type': 'TIMEOUT', 'content': f"Slow request ({time_ms}ms) on {url}"})
                
    except Exception as e:
        print(f"Error parsing HAR log: {e}")

    return counts, issues, detect_anomalies(issues, ip_counter), dict(ip_counter.most_common(5))


def detect_anomalies(issues, ip_counter):
    anomalies = []
    type_counts = Counter(i['type'] for i in issues)

    for kw, count in type_counts.items():
        if count >= 5:
            anomalies.append({
                'type': 'Error Burst',
                'severity': 'HIGH',
                'message': f"Burst of {count} {kw} events detected — possible systemic failure."
            })

    for ip, count in ip_counter.items():
        if count >= 4:
            anomalies.append({
                'type': 'Suspicious IP',
                'severity': 'MEDIUM',
                'message': f"IP {ip} appeared {count} times — possible loop or repeated access attempt."
            })

    failed_count = type_counts.get('FAILED', 0)
    if failed_count >= 3:
        anomalies.append({
            'type': 'Brute Force Detected',
            'severity': 'CRITICAL',
            'message': f"{failed_count} FAILED events found — possible brute-force or authentication attack."
        })

    timeout_count = type_counts.get('TIMEOUT', 0)
    if timeout_count >= 3:
        anomalies.append({
            'type': 'Network Instability',
            'severity': 'HIGH',
            'message': f"{timeout_count} TIMEOUT events detected — DNS or upstream service may be unreachable."
        })

    return anomalies
