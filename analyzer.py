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

    # Auto-detect JSON format
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if content.startswith('[') or content.startswith('{'):
            return parse_json_log(content)
    except Exception:
        pass

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                ips = ip_pattern.findall(line)
                for ip in ips:
                    ip_counter[ip] += 1

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
    top_ips = ip_counter.most_common(5)
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

    return counts, issues, detect_anomalies(issues, ip_counter), ip_counter.most_common(5)


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
