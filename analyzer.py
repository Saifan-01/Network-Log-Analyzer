import re

def parse_log(filepath):
    # Detects keywords: ERROR, WARNING, FAILED, TIMEOUT
    # Case insensitive
    keywords = ['ERROR', 'WARNING', 'FAILED', 'TIMEOUT']
    counts = {kw: 0 for kw in keywords}
    issues = []

    pattern = re.compile(r'\b(' + '|'.join(keywords) + r')\b', re.IGNORECASE)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                match = pattern.search(line)
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

    return counts, issues
