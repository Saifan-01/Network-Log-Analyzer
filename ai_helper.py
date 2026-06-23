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

def generate_security_scores(counts, anomalies):
    # Segmented Scores
    encryption = 100 - (counts.get('WARNING', 0) * 2)
    exposure = 100 - (len(anomalies) * 10) - (counts.get('ERROR', 0) * 3)
    auth = 100 - (counts.get('FAILED', 0) * 8)
    
    # Cap between 0 and 100
    encryption = max(0, min(100, encryption))
    exposure = max(0, min(100, exposure))
    auth = max(0, min(100, auth))
    
    overall = int((encryption + exposure + auth) / 3)
    
    return {
        'encryption': encryption,
        'exposure': exposure,
        'auth': auth,
        'overall': overall
    }

def generate_root_cause_analysis(counts, issues):
    analysis = "System operating normally."
    
    if counts.get('FAILED', 0) >= 10:
        analysis = "Likely under an active Brute-Force or Credential Stuffing attack targeting authentication endpoints."
    elif counts.get('ERROR', 0) >= 10:
        analysis = "Severe Application Instability detected, possibly due to a recent deployment or database failure."
    elif counts.get('TIMEOUT', 0) >= 5:
        analysis = "Network routing failure or extreme upstream latency causing persistent connection drops."
    elif counts.get('FAILED', 0) >= 3:
        analysis = "Multiple authentication failures detected. Review ACLs and user credentials."
    elif counts.get('ERROR', 0) >= 3:
        analysis = "Isolated application errors detected. Check application stack traces."
    elif counts.get('WARNING', 0) >= 5:
        analysis = "Elevated warning levels suggest resource saturation or configuration issues."
        
    return analysis

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

    if any(w in q for w in ['error', 'errors', 'cause', 'what caused']):
        c = counts.get('ERROR', 0)
        if c == 0:
            return "✅ **Good news!** I didn't find any ERROR events in this log. If you're experiencing issues, they might be related to timeouts or failed authentications instead."
        
        examples = [i['content'] for i in issues if i['type'] == 'ERROR'][:2]
        ex_str = "\n".join([f"> `{e}`" for e in examples])
        
        note = "This is a **high number of errors** and indicates a severe problem, such as application crashes or unhandled exceptions." if c >= 5 else "This is a moderate amount, but still requires investigation."
        response = f"There are **{c} ERROR events** in this log. {note}\n\n"
        if examples:
            response += f"Here are examples of what I found:\n{ex_str}\n\n**Action:** Check the application stack traces and verify system resources (memory/disk)."
        return response

    elif any(w in q for w in ['warning', 'warn']):
        c = counts.get('WARNING', 0)
        if c == 0:
            return "✅ **No warnings detected.** Your system config and resource levels appear stable."
        return f"Found **{c} WARNING events**. While warnings aren't fatal errors, a high number suggests potential instability, resource degradation, or deprecated configurations that should be addressed before they cause an outage."

    elif any(w in q for w in ['timeout', 'timed out']):
        c = counts.get('TIMEOUT', 0)
        if c == 0:
            return "✅ **No timeouts found.** Network connectivity and upstream services appear to be responding in time."
        
        note = "This strongly suggests **severe network instability**, a DNS resolution failure, or a completely unresponsive upstream service." if c >= 3 else "These seem to be isolated timeouts — possibly transient network blips."
        return f"🚨 Detected **{c} TIMEOUT events**. {note}\n\n**Action:** Check DNS health, verify routing rules, and ensure upstream APIs are online."

    elif any(w in q for w in ['fail', 'failed', 'failure', 'login']):
        c = counts.get('FAILED', 0)
        if c == 0:
            return "✅ **No failures detected.**"
        
        brute_force = any('Brute Force' in a['type'] for a in anomalies)
        extra = "\n\n⚠️ **WARNING: This looks like a brute-force attack!** Check the anomaly report immediately." if brute_force else ""
        
        return f"There are **{c} FAILED events**. These often indicate broken authentication attempts, refused database connections, or unauthorized access attempts.{extra}"

    elif any(w in q for w in ['critical', 'worst', 'severe', 'most']):
        if total == 0:
            return "✅ **No critical issues found.** The log is clean."
            
        primary = max(counts, key=counts.get)
        return f"The most critical issue category is **{primary}** with **{counts[primary]} occurrences**. You should prioritize investigating these events first to stabilize the system."

    elif any(w in q for w in ['ip', 'address', 'suspicious', 'attack', 'brute']):
        ip_anomalies = [a for a in anomalies if 'IP' in a['type'] or 'Brute' in a['type']]
        if ip_anomalies:
            return "⚠️ **Suspicious Activity Detected:**\n\n" + "\n\n".join([f"• **[{a['severity']}] {a['type']}**\n  {a['message']}" for a in ip_anomalies])
        return "✅ **No suspicious IP patterns or brute-force activity detected.**"

    elif any(w in q for w in ['anomal', 'unusual', 'weird', 'spike']):
        if anomalies:
            return "🚨 **System Anomalies Found:**\n\n" + "\n\n".join([f"• **[{a['severity']}] {a['type']}**\n  {a['message']}" for a in anomalies])
        return "✅ **No anomalies detected.** Event rates are within normal expectations."

    elif any(w in q for w in ['summary', 'summarize', 'overview', 'what happened', 'tell me']):
        if total == 0:
            return "✅ **Log Summary:** I analyzed the log and found zero critical events. The system looks completely healthy."
            
        parts = [f"**{v} {k}**" for k, v in counts.items() if v > 0]
        status = "🚨 **Significant instability detected.** Immediate action required." if total >= 10 else ("⚠️ **Moderate issues found.** Investigation recommended." if total >= 5 else "ℹ️ **Minor events detected.** System looks mostly healthy.")
        
        anomaly_note = f"\n\nI also detected **{len(anomalies)} anomalies** (e.g., suspicious IPs or error bursts)." if anomalies else ""
        
        return f"{status}\n\n**Total critical events: {total}**\nBreakdown: {', '.join(parts)}.{anomaly_note}"

    elif any(w in q for w in ['fix', 'solve', 'how to', 'recommend', 'suggestion', 'help']):
        if total == 0:
            return "✅ **No fixes needed** — the log is clean!"
            
        primary = max(counts, key=counts.get)
        fixes = {
            'ERROR': "1. Review the specific error stack traces to identify the failing component.\n2. Verify system resources (Memory, Disk Space, CPU).\n3. Restart the affected service if a memory leak or locked state is suspected.",
            'WARNING': "1. Review application configuration for deprecated settings.\n2. Monitor resource usage closely for upward trends.\n3. Implement alerting thresholds before warnings become errors.",
            'FAILED': "1. Verify user credentials and API endpoint configurations.\n2. Review firewall (iptables/UFW) and ACL rules.\n3. Test outbound connectivity to destination services.",
            'TIMEOUT': "1. Investigate DNS resolution latency and reachability.\n2. Check for network routing loops or dropped packets.\n3. Consider increasing timeout thresholds in the client configuration if the service is known to be slow."
        }
        return f"Based on the primary issue (**{primary}**), here is the **Recommended Action Plan**:\n\n{fixes.get(primary)}"

    elif any(w in q for w in ['total', 'count', 'how many', 'number']):
        return f"I found **{total} total critical events**.\n\nHere is the breakdown:\n• **Errors:** {counts.get('ERROR',0)}\n• **Warnings:** {counts.get('WARNING',0)}\n• **Failed:** {counts.get('FAILED',0)}\n• **Timeouts:** {counts.get('TIMEOUT',0)}"

    # Fallback: Deep Search through the log lines
    else:
        # Ignore common stop words
        stop_words = {'what', 'why', 'how', 'when', 'where', 'is', 'are', 'do', 'does', 'did', 'a', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'log', 'logs', 'show', 'me', 'tell', 'about'}
        search_terms = [w for w in q.split() if w not in stop_words and len(w) > 2]
        
        if not search_terms:
            return "I can answer specific questions about errors, warnings, IPs, anomalies, or search for exact keywords in your logs. Try asking something like: 'Show me database errors' or 'What happened with 192.168.1.5?'"

        matches = []
        for issue in issues:
            content_lower = issue['content'].lower()
            if any(term in content_lower for term in search_terms):
                matches.append(issue)
                if len(matches) >= 5: # Limit results
                    break
                    
        if matches:
            response = f"I searched the logs for your query and found {len(matches)} relevant events:\n\n"
            for m in matches:
                response += f"• **Line {m['line_num']} [{m['type']}]**: `{m['content']}`\n"
            if len(issues) > 5:
                response += "\n*Showing top 5 matches only.*"
            return response
            
        return f"I searched the logs for **'{' '.join(search_terms)}'** but couldn't find any exact matches. Try checking the **Log Explorer** or asking about 'errors', 'timeouts', or 'anomalies'."
