from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='viewer') # 'admin' or 'viewer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    log_histories = db.relationship('LogHistory', backref='user', lazy=True)
    alert_rules = db.relationship('AlertRule', backref='user', lazy=True)
    active_alerts = db.relationship('ActiveAlert', backref='user', lazy=True)

class LogHistory(db.Model):
    __tablename__ = 'log_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    filename = db.Column(db.String(256), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    error_count = db.Column(db.Integer, default=0)
    warning_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    timeout_count = db.Column(db.Integer, default=0)

class AlertRule(db.Model):
    __tablename__ = 'alert_rules'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    metric = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(10), nullable=False)
    threshold = db.Column(db.Float, nullable=False)
    webhook_url = db.Column(db.String(512), nullable=True)

class ActiveAlert(db.Model):
    __tablename__ = 'active_alerts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('alert_rules.id'), nullable=True)
    message = db.Column(db.String(512), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
