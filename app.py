# File: webhook_app.py
# Author: Jay Chauhan
# Website: www.dj-jay.in
# Description:
# This script is a Flask-based webhook handler that loads project configurations
# directly from database, validates Git webhook requests, triggers deployment scripts,
# and sends Slack notifications with detailed event information.

from flask import Flask, request, jsonify
import hmac
import hashlib
import subprocess
import json
import requests
import os
import secrets
import string
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from db_config import get_db_connection, execute_query

load_dotenv()

# Initialize the Flask app instance
app = Flask(__name__)

def init_database():
    """Initialize MySQL database with sample projects if tables don't exist"""
    connection = get_db_connection()
    if not connection:
        print("Failed to connect to MySQL database")
        return
    
    try:
        cursor = connection.cursor()
        
        # Check if projects table exists
        cursor.execute("SHOW TABLES LIKE 'projects'")
        if not cursor.fetchone():
            # Projects table
            cursor.execute('''
                CREATE TABLE projects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    deploy_script TEXT NOT NULL,
                    slack_webhook TEXT NOT NULL,
                    secret VARCHAR(255)
                )
            ''')
            
            # Webhook events table
            cursor.execute('''
                CREATE TABLE webhook_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_name VARCHAR(255) NOT NULL,
                    repository_name VARCHAR(255),
                    repository_url TEXT,
                    clone_url TEXT,
                    event_type VARCHAR(100),
                    branch VARCHAR(255),
                    commit_message TEXT,
                    commit_id VARCHAR(255),
                    author_name VARCHAR(255),
                    author_email VARCHAR(255),
                    timestamp VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add sample projects
            projects = [
                ("My First Project", "/path/to/my_first_project/deploy_script.sh", "https://hooks.slack.com/services/XXX/YYY/ZZZ"),
                ("Another Project", "/path/to/another_project/deploy_script.sh", "https://hooks.slack.com/services/AAA/BBB/CCC"),
                ("Test Project", "/path/to/test/deploy.sh", "https://hooks.slack.com/test")
            ]
            
            for name, script, webhook in projects:
                secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
                cursor.execute(
                    "INSERT INTO projects (name, deploy_script, slack_webhook, secret) VALUES (%s, %s, %s, %s)",
                    (name, script, webhook, secret)
                )
            
            connection.commit()
            print("MySQL database initialized with sample projects")
        
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Error initializing database: {e}")
        if connection:
            connection.close()

def load_projects_from_database():
    """Load project configurations directly from MySQL database"""
    projects = defaultdict(dict)
    
    db_projects = execute_query("SELECT name, deploy_script, slack_webhook, secret FROM projects", fetch=True)
    
    if db_projects:
        for name, deploy_script, slack_webhook, secret in db_projects:
            project_key = name.lower().replace(" ", "_").replace("-", "_")
            projects[project_key] = {
                'deploy_script': deploy_script,
                'slack_webhook': slack_webhook,
                'secret': secret,
                'name': name
            }
    
    return projects

def save_webhook_event(project_name, payload_data, event_type):
    """Save webhook event to MySQL database"""
    # Extract data from payload
    repository = payload_data.get('repository', {})
    repo_name = repository.get('name', 'Unknown')
    repo_url = repository.get('html_url', 'N/A')
    clone_url = repository.get('clone_url', 'N/A')
    ref = payload_data.get('ref', '')
    branch = ref.split('/')[-1] if 'refs/heads/' in ref else 'Unknown'
    
    head_commit = payload_data.get('head_commit', {})
    commit_message = head_commit.get('message', 'N/A')
    commit_id = head_commit.get('id', 'N/A')
    
    author = head_commit.get('author', {})
    author_name = author.get('name', 'Unknown')
    author_email = author.get('email', 'Unknown')
    
    timestamp = head_commit.get('timestamp', datetime.now().isoformat())
    
    query = '''
        INSERT INTO webhook_events 
        (project_name, repository_name, repository_url, clone_url, event_type, branch, commit_message, 
         commit_id, author_name, author_email, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    '''
    
    params = (project_name, repo_name, repo_url, clone_url, event_type, branch, commit_message, 
              commit_id, author_name, author_email, timestamp)
    
    execute_query(query, params)

# Global variable for projects
PROJECTS = {}

@app.route('/', methods=['GET'])
def index():
    """Handle requests to the base URL"""
    return jsonify({"status": "success", "message": "Webhook handler is deployed and running successfully."})

@app.route('/debug', methods=['GET'])
def debug_info():
    """Show current configuration and status"""
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    return jsonify({
        "projects_count": len(PROJECTS),
        "projects": list(PROJECTS.keys()),
        "project_details": {name: {k: v for k, v in config.items() if k != 'secret'} for name, config in PROJECTS.items()},
        "database_connected": get_db_connection() is not None
    })

@app.route('/get-secrets', methods=['GET'])
def get_secrets():
    """Get project secrets for testing"""
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    secrets_data = {}
    for project_key, config in PROJECTS.items():
        secrets_data[config['name']] = config['secret']
    
    return jsonify({"secrets": secrets_data})

@app.route('/webhook-events', methods=['GET'])
def get_webhook_events():
    """Get all webhook events from MySQL database"""
    query = '''
        SELECT project_name, repository_name, repository_url, clone_url, event_type, branch, 
               commit_message, author_name, timestamp, created_at
        FROM webhook_events 
        ORDER BY created_at DESC 
        LIMIT 50
    '''
    
    rows = execute_query(query, fetch=True)
    
    if rows is None:
        return jsonify({"error": "Database connection failed"}), 500
    
    events = []
    for row in rows:
        events.append({
            "project_name": row[0],
            "repository_name": row[1],
            "repository_url": row[2],
            "clone_url": row[3],
            "event_type": row[4],
            "branch": row[5],
            "commit_message": row[6],
            "author_name": row[7],
            "timestamp": row[8],
            "created_at": row[9]
        })
    
    return jsonify({"events": events, "count": len(events)})

@app.route('/add-project', methods=['POST'])
def add_project():
    """Add new project with auto-generated secret key"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    name = data.get("name")
    deploy_script = data.get("deploy_script")
    slack_webhook = data.get("slack_webhook")

    if not all([name, deploy_script, slack_webhook]):
        return jsonify({"error": "Missing required fields: name, deploy_script, slack_webhook"}), 400

    try:
        # Generate secret key automatically
        secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        
        query = "INSERT INTO projects (name, deploy_script, slack_webhook, secret) VALUES (%s, %s, %s, %s)"
        params = (name, deploy_script, slack_webhook, secret)
        
        result = execute_query(query, params)
        
        if result is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        # Reload projects
        global PROJECTS
        PROJECTS = load_projects_from_database()
        
        return jsonify({
            "message": f"Project '{name}' added successfully!",
            "project_name": name,
            "secret_key": secret,
            "webhook_url": f"http://localhost:5000/webhook/main",
            "timestamp": datetime.now().strftime('%d %b, %Y %I:%M %p')
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

@app.route('/test-webhook', methods=['POST'])
def test_webhook():
    """Test webhook without signature validation"""
    payload_data = request.get_json()
    
    if not payload_data:
        return jsonify({"error": "No JSON data received"}), 400
    
    return jsonify({
        "status": "success",
        "message": "Test webhook received (no signature validation)",
        "received_data": {
            "repository": payload_data.get('repository', {}).get('name', 'Unknown'),
            "branch": payload_data.get('ref', 'Unknown').split('/')[-1],
            "commit_message": payload_data.get('head_commit', {}).get('message', 'N/A')
        }
    })

@app.route('/webhook/<branch>', methods=['POST'])
def handle_webhook(branch):
    """Handle incoming Git webhook events - Fast response"""
    payload = request.data
    received_signature = request.headers.get('X-Hub-Signature-256', '')
    
    global PROJECTS
    if not PROJECTS:  # Load only if empty
        PROJECTS = load_projects_from_database()
    
    # Fast signature validation
    matching_project = None
    project_config = None
    
    for project_name, config in PROJECTS.items():
        secret = config.get("secret", "")
        if not secret:
            continue

        computed_signature = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed_signature, received_signature):
            matching_project = project_name
            project_config = config
            break

    if not matching_project:
        return jsonify({"error": "Invalid signature"}), 403
    
    # Send immediate response
    response_data = {
        "status": "success",
        "message": "Webhook received",
        "project": project_config['name']
    }
    
    # Process in background (optional - comment out if not needed)
    try:
        payload_data = json.loads(payload)
        event = request.headers.get('X-GitHub-Event', 'push')
        save_webhook_event(project_config['name'], payload_data, event)
    except:
        pass  # Don't let background processing delay response
    
    return jsonify(response_data)

# Initialize database and load projects
init_database()
PROJECTS = load_projects_from_database()

# Start the Flask app if the script is run directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)