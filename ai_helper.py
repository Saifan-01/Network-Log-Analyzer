SEVERITY_LEVELS = {
    'CRITICAL': 'Immediate action required. Critical systems may be compromised.',
    'HIGH': 'High priority. Address within the hour to prevent escalation.',
    'MEDIUM': 'Moderate severity. Investigate within 24 hours.',
    'LOW': 'Low impact. Monitor and log for reference.'
}

def get_severity(counts, anomalies):
    critical = [a for a in anomalies if a['severity'] == 'CRITICAL']
    if critical or counts.get('ERROR', 0) >= 10:
        return 'CRITICAL'
    elif counts.get('ERROR', 0) >= 5 or counts.get('TIMEOUT', 0) >= 5:
        return 'HIGH'
    elif counts.get('WARNING', 0) >= 5 or counts.get('FAILED', 0) >= 3:
        return 'MEDIUM'
    return 'LOW'


def generate_insights(counts, issues, anomalies=[]):
    total = sum(counts.values())
    if total == 0:
        return {
            "summary": "No critical issues detected. System appears healthy.",
            "fixes": ["Continue routine monitoring."],
            "severity": "LOW"
        }

    primary = max(counts, key=counts.get)
    summaries = {
        'ERROR': "High volume of ERROR events detected — application crashes or unhandled exceptions suspected.",
        'WARNING': "Multiple WARNINGs found — potential instability or resource degradation.",
        'FAILED': "Repeated FAILED events — broken connections or failed authentications are likely.",
        'TIMEOUT': "Significant TIMEOUT count — severe network instability or unresponsive upstream servers."
    }
    fixes = {
        'ERROR': ["Check application stack traces.", "Verify disk space and memory usage.", "Restart affected services if memory leak is suspected."],
        'WARNING': ["Review config for deprecated settings.", "Monitor CPU and RAM closely.", "Set up alerting thresholds."],
        'FAILED': ["Verify credentials and API endpoints.", "Check firewall and ACL rules.", "Test connectivity to destination services."],
        'TIMEOUT': ["Investigate DNS resolution latency.", "Check for network routing loops.", "Increase timeout thresholds in client config."]
    }
    return {
        "summary": f"Analyzed {len(issues)} critical log entries. " + summaries.get(primary, ""),
        "fixes": fixes.get(primary, ["Review overall system health."]),
        "severity": get_severity(counts, anomalies)
    }


def generate_incident_report(counts, issues, insights, anomalies, filename):
    severity = insights.get('severity', 'MEDIUM')
    root_causes = []
    if counts.get('TIMEOUT', 0) > 0:
        root_causes.append("Network connectivity issues or unresponsive upstream service (DNS/TCP timeouts)")
    if counts.get('FAILED', 0) > 0:
        root_causes.append("Authentication failures or service endpoint unavailability")
    if counts.get('ERROR', 0) > 0:
        root_causes.append("Application runtime errors causing service degradation")
    if counts.get('WARNING', 0) > 0:
        root_causes.append("Resource saturation or deprecated configuration warnings")
    if not root_causes:
        root_causes = ["No significant root cause identified. Log appears clean."]

    return {
        "filename": filename,
        "severity": severity,
        "severity_description": SEVERITY_LEVELS.get(severity, ""),
        "total_events": sum(counts.values()),
        "counts": counts,
        "root_causes": root_causes,
        "recommended_actions": [
            "Isolate and investigate affected services immediately.",
            "Review the extracted log lines for specific failure points.",
            "Cross-reference with network topology and service dependency maps.",
            "Escalate to Level 2 support if errors persist beyond 30 minutes."
        ],
        "anomalies": anomalies,
        "summary": insights.get('summary', '')
    }


def answer_question(question, counts, issues, anomalies):
    q = question.lower().strip()
    total = sum(counts.values())

    if any(w in q for w in ['error', 'errors']):
        c = counts.get('ERROR', 0)
        note = "This is a high number — investigate immediately." if c >= 5 else ("Minor error count detected." if c > 0 else "No errors found.")
        return f"There are **{c} ERROR events** in this log. {note}"

    elif any(w in q for w in ['warning', 'warn']):
        c = counts.get('WARNING', 0)
        return f"Found **{c} WARNING events**. Warnings indicate risks that haven't caused outages yet but should be monitored."

    elif any(w in q for w in ['timeout', 'timed out']):
        c = counts.get('TIMEOUT', 0)
        note = "This strongly suggests network instability or a DNS issue." if c >= 3 else "Isolated timeouts — possibly transient."
        return f"Detected **{c} TIMEOUT events**. {note}"

    elif any(w in q for w in ['fail', 'failed', 'failure']):
        c = counts.get('FAILED', 0)
        return f"There are **{c} FAILED events**. These often indicate broken authentication, refused connections, or failed DB queries."

    elif any(w in q for w in ['critical', 'worst', 'severe', 'most']):
        primary = max(counts, key=counts.get) if total > 0 else None
        if primary:
            return f"The most critical issue is **{primary}** with **{counts[primary]} occurrences**. Prioritize this in your investigation."
        return "No critical issues found in this log."

    elif any(w in q for w in ['ip', 'address', 'suspicious', 'attack', 'brute']):
        ip_anomalies = [a for a in anomalies if 'IP' in a['type'] or 'Brute' in a['type']]
        if ip_anomalies:
            return "⚠️ **Suspicious Activity Detected:**\n" + "\n".join([f"• [{a['severity']}] {a['message']}" for a in ip_anomalies])
        return "✅ No suspicious IP patterns or brute-force activity detected."

    elif any(w in q for w in ['anomal', 'unusual', 'weird']):
        if anomalies:
            return "🚨 **Anomalies Found:**\n" + "\n".join([f"• [{a['severity']}] {a['message']}" for a in anomalies])
        return "✅ No anomalies detected in this log."

    elif any(w in q for w in ['summary', 'summarize', 'overview', 'what happened', 'tell me']):
        parts = [f"{v} {k}" for k, v in counts.items() if v > 0]
        status = "significant instability detected." if total >= 10 else ("moderate issues found." if total >= 5 else "system looks mostly healthy.")
        return f"**Log Summary:** {total} total critical events — {', '.join(parts) if parts else 'none'}. {status.capitalize()}"

    elif any(w in q for w in ['fix', 'solve', 'how to', 'recommend', 'suggestion', 'help']):
        primary = max(counts, key=counts.get) if total > 0 else None
        fixes = {
            'ERROR': "1. Check error stack traces. 2. Verify memory & disk. 3. Restart affected service.",
            'WARNING': "1. Review config for warnings. 2. Monitor resource usage. 3. Set alerts.",
            'FAILED': "1. Check credentials & endpoints. 2. Review firewall rules. 3. Test connectivity.",
            'TIMEOUT': "1. Check DNS resolution. 2. Verify routing. 3. Increase timeout in config."
        }
        if primary:
            return f"**Recommended Fix for {primary}:** {fixes.get(primary)}"
        return "No fixes needed — log is clean!"

    elif any(w in q for w in ['total', 'count', 'how many', 'number']):
        return f"**Total critical events: {total}** — Errors: {counts.get('ERROR',0)}, Warnings: {counts.get('WARNING',0)}, Failed: {counts.get('FAILED',0)}, Timeouts: {counts.get('TIMEOUT',0)}."

    else:
        return f"I analyzed this log and found **{total} total events**. Try asking: *'Summarize the log'*, *'How many errors?'*, *'Any suspicious activity?'*, or *'What should I fix?'*"
