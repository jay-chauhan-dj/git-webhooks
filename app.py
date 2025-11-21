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
import sqlite3
import secrets
import string
from datetime import datetime
from collections import defaultdict

# Initialize the Flask app instance
app = Flask(__name__)

def init_database():
    """Initialize database with sample projects if it doesn't exist"""
    if not os.path.exists('projects.db'):
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        
        # Projects table
        cursor.execute('''
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                deploy_script TEXT NOT NULL,
                slack_webhook TEXT NOT NULL,
                secret TEXT
            )
        ''')
        
        # Webhook events table
        cursor.execute('''
            CREATE TABLE webhook_events (
                id INTEGER PRIMARY KEY,
                project_name TEXT NOT NULL,
                repository_name TEXT,
                repository_url TEXT,
                clone_url TEXT,
                event_type TEXT,
                branch TEXT,
                commit_message TEXT,
                commit_id TEXT,
                author_name TEXT,
                author_email TEXT,
                timestamp TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                "INSERT INTO projects (name, deploy_script, slack_webhook, secret) VALUES (?, ?, ?, ?)",
                (name, script, webhook, secret)
            )
        
        conn.commit()
        conn.close()
        print("Database initialized with sample projects")

def load_projects_from_database():
    """Load project configurations directly from database"""
    projects = defaultdict(dict)
    
    try:
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, deploy_script, slack_webhook, secret FROM projects")
        db_projects = cursor.fetchall()
        
        for name, deploy_script, slack_webhook, secret in db_projects:
            project_key = name.lower().replace(" ", "_").replace("-", "_")
            projects[project_key] = {
                'deploy_script': deploy_script,
                'slack_webhook': slack_webhook,
                'secret': secret,
                'name': name
            }
        
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    
    return projects

def save_webhook_event(project_name, payload_data, event_type):
    """Save webhook event to database"""
    try:
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        
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
        
        cursor.execute('''
            INSERT INTO webhook_events 
            (project_name, repository_name, repository_url, clone_url, event_type, branch, commit_message, 
             commit_id, author_name, author_email, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (project_name, repo_name, repo_url, clone_url, event_type, branch, commit_message, 
              commit_id, author_name, author_email, timestamp))
        
        conn.commit()
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Error saving webhook event: {e}")
        # Try to add missing columns if table exists
        try:
            cursor.execute('ALTER TABLE webhook_events ADD COLUMN repository_url TEXT')
            cursor.execute('ALTER TABLE webhook_events ADD COLUMN clone_url TEXT')
            conn.commit()
        except:
            pass

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
        "database_exists": os.path.exists("projects.db")
    })

@app.route('/webhook-events', methods=['GET'])
def get_webhook_events():
    """Get all webhook events from database"""
    try:
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT project_name, repository_name, repository_url, clone_url, event_type, branch, 
                   commit_message, author_name, timestamp, created_at
            FROM webhook_events 
            ORDER BY created_at DESC 
            LIMIT 50
        ''')
        
        events = []
        for row in cursor.fetchall():
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
        
        conn.close()
        return jsonify({"events": events, "count": len(events)})
        
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

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
        
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO projects (name, deploy_script, slack_webhook, secret) VALUES (?, ?, ?, ?)",
            (name, deploy_script, slack_webhook, secret)
        )
        
        conn.commit()
        conn.close()
        
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
        
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

@app.route('/add-project-with-secret', methods=['POST'])
def add_project_with_secret():
    """Add new project with manager's secret key"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    name = data.get("name")
    deploy_script = data.get("deploy_script")
    slack_webhook = data.get("slack_webhook")
    secret = data.get("secret")  # Manager provides this

    if not all([name, deploy_script, slack_webhook, secret]):
        return jsonify({"error": "Missing required fields: name, deploy_script, slack_webhook, secret"}), 400

    try:
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO projects (name, deploy_script, slack_webhook, secret) VALUES (?, ?, ?, ?)",
            (name, deploy_script, slack_webhook, secret)
        )
        
        conn.commit()
        conn.close()
        
        # Reload projects
        global PROJECTS
        PROJECTS = load_projects_from_database()
        
        return jsonify({
            "message": f"Project '{name}' added successfully with manager's secret!",
            "secret": secret
        }), 200
        
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

@app.route('/process-payload', methods=['POST'])
def process_payload():
    """Process payload.txt file content with manager's secret"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    payload_content = data.get("payload")
    secret_key = data.get("secret")
    
    if not payload_content or not secret_key:
        return jsonify({"error": "Missing payload or secret"}), 400

    try:
        # Parse payload
        if isinstance(payload_content, str):
            payload_data = json.loads(payload_content)
        else:
            payload_data = payload_content
        
        # Find matching project by secret
        matching_project = None
        for project_name, config in PROJECTS.items():
            if config.get("secret") == secret_key:
                matching_project = project_name
                break
        
        if not matching_project:
            return jsonify({"error": "Invalid secret key"}), 403
        
        # Extract repository info
        repository = payload_data.get('repository', {})
        repo_name = repository.get('name', 'Unknown')
        repo_url = repository.get('html_url', 'N/A')
        clone_url = repository.get('clone_url', 'N/A')
        event_type = 'push'  # Default
        
        # Save to database
        save_webhook_event(PROJECTS[matching_project]['name'], payload_data, event_type)
        
        return jsonify({
            "message": "Payload processed successfully!",
            "project": PROJECTS[matching_project]['name'],
            "repository": repo_name,
            "repository_url": repo_url,
            "clone_url": clone_url,
            "timestamp": datetime.now().strftime('%d %b, %Y %I:%M %p')
        }), 200
        
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in payload"}), 400
    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

@app.route('/search-repos', methods=['POST'])
def search_repos_by_secret():
    """Search repositories by secret key"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    secret_key = data.get("secret")
    if not secret_key:
        return jsonify({"error": "Missing secret key"}), 400

    try:
        # Find matching project by secret
        matching_project = None
        project_config = None
        for project_name, config in PROJECTS.items():
            if config.get("secret") == secret_key:
                matching_project = project_name
                project_config = config
                break
        
        if not matching_project:
            return jsonify({"error": "Invalid secret key"}), 403
        
        # Get webhook events for this project
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT repository_name, repository_url, clone_url, event_type, branch, commit_message, 
                   author_name, timestamp, created_at
            FROM webhook_events 
            WHERE project_name = ?
            ORDER BY created_at DESC
        ''', (project_config['name'],))
        
        events = []
        for row in cursor.fetchall():
            events.append({
                "repository_name": row[0],
                "repository_url": row[1],
                "clone_url": row[2],
                "event_type": row[3],
                "branch": row[4],
                "commit_message": row[5],
                "author_name": row[6],
                "timestamp": row[7],
                "created_at": row[8]
            })
        
        conn.close()
        
        return jsonify({
            "project_name": project_config['name'],
            "secret_valid": True,
            "events_count": len(events),
            "repositories": events,
            "search_timestamp": datetime.now().strftime('%d %b, %Y %I:%M %p')
        }), 200
        
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Search error: {str(e)}"}), 500

@app.route('/webhook/<branch>', methods=['POST'])
def handle_webhook(branch):
    """Handle incoming Git webhook events"""
    payload = request.data
    received_signature = request.headers.get('X-Hub-Signature-256', '')
    
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    # Normal signature validation
    matching_project = None
    for project_name, config in PROJECTS.items():
        secret = config.get("secret", "")
        if not secret:
            continue

        computed_signature = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed_signature, received_signature):
            matching_project = project_name
            break

    if not matching_project:
        return jsonify({"error": "Invalid signature or unknown project."}), 403
    
    project_config = PROJECTS[matching_project]
    event = request.headers.get('X-GitHub-Event', 'push')
    payload_data = json.loads(payload)
    
    # Save webhook event to database
    save_webhook_event(project_config['name'], payload_data, event)
    
    repository = payload_data.get('repository', {})
    repo_name = repository.get('name', 'Unknown')
    
    return jsonify({
        "message": f"Webhook processed for {project_config['name']}",
        "repository": repo_name,
        "project": project_config['name'],
        "timestamp": datetime.now().strftime('%d %b, %Y %I:%M %p')
    })

# Initialize database and load projects
init_database()
PROJECTS = load_projects_from_database()

# Start the Flask app if the script is run directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)