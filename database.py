from models import db, User, LogHistory, AlertRule, ActiveAlert

def init_db(app):
    # This will be called from app.py after db.init_app(app)
    with app.app_context():
        db.create_all()

# User Operations
def create_user(username, password_hash):
    if User.query.filter_by(username=username).first():
        return False
        
    # First user gets admin privileges
    role = 'admin' if User.query.count() == 0 else 'viewer'
    
    new_user = User(username=username, password_hash=password_hash, role=role)
    db.session.add(new_user)
    db.session.commit()
    return True

def get_user_by_username(username):
    user = User.query.filter_by(username=username).first()
    if user:
        return {'id': user.id, 'username': user.username, 'password_hash': user.password_hash}
    return None

def get_user_by_id(user_id):
    user = User.query.get(user_id)
    if user:
        return {'id': user.id, 'username': user.username, 'password_hash': user.password_hash}
    return None

# Log Metadata Operations
def save_log_metadata(filename, counts, user_id=None):
    history = LogHistory(
        user_id=user_id,
        filename=filename,
        error_count=counts.get('ERROR', 0),
        warning_count=counts.get('WARNING', 0),
        failed_count=counts.get('FAILED', 0),
        timeout_count=counts.get('TIMEOUT', 0)
    )
    db.session.add(history)
    db.session.commit()
    return history.id

def get_log_metadata(log_id):
    history = LogHistory.query.get(log_id)
    if history:
        return {'filename': history.filename, 'upload_time': str(history.upload_time)}
    return {'filename': 'Unknown', 'upload_time': 'Unknown'}

def get_user_history(user_id):
    histories = LogHistory.query.filter_by(user_id=user_id).order_by(LogHistory.upload_time.desc()).all()
    return [{
        'id': h.id,
        'filename': h.filename,
        'upload_time': str(h.upload_time),
        'error_count': h.error_count,
        'warning_count': h.warning_count,
        'failed_count': h.failed_count,
        'timeout_count': h.timeout_count
    } for h in histories]

# Alerting Operations
def get_alert_rules(user_id=None):
    if user_id:
        rules = AlertRule.query.filter_by(user_id=user_id).all()
    else:
        rules = AlertRule.query.all()
    return [{
        'id': r.id, 'user_id': r.user_id, 'metric': r.metric, 
        'condition': r.condition, 'threshold': r.threshold, 'webhook_url': r.webhook_url
    } for r in rules]

def add_alert_rule(metric, condition, threshold, user_id=None, webhook_url=None):
    rule = AlertRule(metric=metric, condition=condition, threshold=threshold, user_id=user_id, webhook_url=webhook_url)
    db.session.add(rule)
    db.session.commit()

def delete_alert_rule(rule_id):
    rule = AlertRule.query.get(rule_id)
    if rule:
        ActiveAlert.query.filter_by(rule_id=rule_id).delete()
        db.session.delete(rule)
        db.session.commit()

import requests

def create_active_alert(rule_id, message, user_id=None):
    alert = ActiveAlert(rule_id=rule_id, message=message, user_id=user_id)
    db.session.add(alert)
    db.session.commit()
    
    # Trigger webhook if present
    rule = AlertRule.query.get(rule_id)
    if rule and rule.webhook_url:
        try:
            payload = {'metric': rule.metric, 'condition': rule.condition, 'threshold': rule.threshold, 'message': message}
            requests.post(rule.webhook_url, json=payload, timeout=2)
        except Exception as e:
            print(f"Failed to trigger webhook: {e}")

def get_active_alerts(user_id=None):
    if user_id:
        alerts = ActiveAlert.query.filter_by(user_id=user_id).order_by(ActiveAlert.timestamp.desc()).limit(20).all()
    else:
        alerts = ActiveAlert.query.order_by(ActiveAlert.timestamp.desc()).limit(20).all()
    
    result = []
    for a in alerts:
        rule = AlertRule.query.get(a.rule_id)
        result.append({
            'id': a.id, 'rule_id': a.rule_id, 'message': a.message, 
            'timestamp': str(a.timestamp), 'metric': rule.metric if rule else 'UNKNOWN'
        })
    return result

def clear_active_alerts(user_id=None):
    if user_id:
        ActiveAlert.query.filter_by(user_id=user_id).delete()
    else:
        ActiveAlert.query.delete()
    db.session.commit()

def get_global_stats():
    return {
        'total_logs': LogHistory.query.count(),
        'total_errors': db.session.query(db.func.sum(LogHistory.error_count)).scalar() or 0,
        'active_threats': ActiveAlert.query.count(),
        'avg_response_time': 42  # Dummy value for UI
    }
