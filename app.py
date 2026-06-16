import os
from flask import Flask, request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
from database import init_db, save_log_metadata, get_log_metadata
from analyzer import parse_log
from ai_helper import generate_insights

app = Flask(__name__)
app.secret_key = 'super_secret_noc_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max limit

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'log', 'txt'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the log file
        counts, issues = parse_log(filepath)
        
        # Save metadata to DB
        log_id = save_log_metadata(filename, counts)
        
        insights = generate_insights(counts, issues)
        metadata = get_log_metadata(log_id)
        
        return render_template('dashboard.html', 
                               metadata=metadata, 
                               counts=counts, 
                               issues=issues[:100], # Limit to first 100 issues for UI
                               insights=insights)
    else:
        flash('Invalid file type. Please upload a .log or .txt file.', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
