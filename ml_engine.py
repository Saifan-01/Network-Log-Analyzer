import numpy as np
from sklearn.ensemble import IsolationForest

# Global singleton model for simplicity
_anomaly_model = None
_is_trained = False

def train_anomaly_model(historical_logs):
    """
    Trains the Isolation Forest on historical log error metrics.
    historical_logs should be a list of dicts with 'error_count' and 'warning_count'.
    """
    global _anomaly_model, _is_trained
    
    if not historical_logs or len(historical_logs) < 10:
        # Not enough data to train a meaningful model
        return False
        
    # Extract features: error counts and warning counts
    X = np.array([[log.error_count, log.warning_count] for log in historical_logs])
    
    # Initialize and fit the Isolation Forest
    _anomaly_model = IsolationForest(contamination=0.05, random_state=42)
    _anomaly_model.fit(X)
    
    _is_trained = True
    return True

def predict_anomaly(error_count, warning_count):
    """
    Returns True if the event is anomalous, False otherwise.
    """
    if not _is_trained or _anomaly_model is None:
        # Fallback to static threshold if model isn't trained
        return error_count > 100 or warning_count > 500
        
    # Predict (-1 is anomaly, 1 is normal)
    X_new = np.array([[error_count, warning_count]])
    prediction = _anomaly_model.predict(X_new)[0]
    
    return prediction == -1
