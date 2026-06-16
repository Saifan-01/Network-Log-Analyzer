import random

def generate_insights(counts, issues):
    """
    Mock AI module to generate insights based on log counts and content.
    In a real scenario, this would send the parsed issues to an LLM like OpenAI or local Ollama.
    """
    total_issues = sum(counts.values())
    if total_issues == 0:
        return {
            "summary": "No critical issues detected in this log file.",
            "fixes": ["Keep monitoring as usual."]
        }
    
    # Determine primary issue type
    primary_issue = max(counts, key=counts.get)
    
    # Generate mock AI summary
    summary_templates = {
        'ERROR': "The log indicates a high volume of general errors, possibly pointing to application crashes or unhandled exceptions.",
        'WARNING': "There are many warnings. While not fatal, they suggest potential instability or resource degradation.",
        'FAILED': "Multiple operational failures were recorded. This usually indicates broken connections or failed authentications.",
        'TIMEOUT': "A significant number of timeouts were detected. Most failures seem to be timeout-related, indicating severe network instability or unresponsive upstream servers."
    }
    
    summary = f"Analyzed {len(issues)} critical log entries. " + summary_templates.get(primary_issue, "")
    
    # Generate mock AI fixes
    fixes_pool = {
        'ERROR': [
            "Check application stack traces for root cause.",
            "Verify file permissions and disk space.",
            "Restart the affected service if memory leak is suspected."
        ],
        'WARNING': [
            "Review configuration settings for deprecation warnings.",
            "Monitor CPU and Memory usage.",
            "Investigate possible packet loss."
        ],
        'FAILED': [
            "Verify database or API credentials.",
            "Check firewall rules blocking the connection.",
            "Ensure the destination server is online."
        ],
        'TIMEOUT': [
            "Investigate DNS resolution times.",
            "Check for network loops or routing issues.",
            "Increase timeout thresholds in the client application."
        ]
    }
    
    suggested_fixes = random.sample(fixes_pool.get(primary_issue, ["Review generic system health."]), min(3, len(fixes_pool.get(primary_issue))))
    
    return {
        "summary": summary,
        "fixes": suggested_fixes
    }
