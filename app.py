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
        
        cursor.execute('''
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                deploy_script TEXT NOT NULL,
                slack_webhook TEXT NOT NULL,
                secret TEXT
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
        print("✅ Database initialized with sample projects")

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
                'secret': secret
            }
        
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    
    return projects

# Initialize database and load projects
init_database()
PROJECTS = load_projects_from_database()

@app.route('/', methods=['GET'])
def index():
    """Handle requests to the base URL"""
    return jsonify({"status": "success", "message": "Webhook handler is deployed and running successfully."})

@app.route('/debug', methods=['GET'])
def debug_info():
    """Show current configuration and status"""
    # Reload projects from database
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    return jsonify({
        "projects_count": len(PROJECTS),
        "projects": list(PROJECTS.keys()),
        "project_details": {name: {k: v for k, v in config.items() if k != 'secret'} for name, config in PROJECTS.items()},
        "database_exists": os.path.exists("projects.db")
    })

@app.route('/add-project', methods=['POST'])
def add_project():
    """Add new project directly to database"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    name = data.get("name")
    deploy_script = data.get("deploy_script")
    slack_webhook = data.get("slack_webhook")

    if not all([name, deploy_script, slack_webhook]):
        return jsonify({"error": "Missing required fields: name, deploy_script, slack_webhook"}), 400

    try:
        conn = sqlite3.connect('projects.db')
        cursor = conn.cursor()
        
        # Generate secret
        secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        
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
            "secret": secret
        }), 200
        
    except sqlite3.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

@app.route('/test-webhook/<branch>', methods=['POST'])
def test_webhook(branch):
    """Test endpoint that bypasses signature validation"""
    # Reload projects from database
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    if not PROJECTS:
        return jsonify({"error": "No projects configured in database."}), 400
    
    matching_project = list(PROJECTS.keys())[0]
    project_config = PROJECTS[matching_project]
    
    payload_data = request.get_json() or {}
    event = request.headers.get('X-GitHub-Event', 'push')
    ref = payload_data.get('ref', f'refs/heads/{branch}')
    event_branch = ref.split('/')[-1] if 'refs/heads/' in ref else branch
    commit_message = payload_data.get('head_commit', {}).get('message', 'Test commit')
    timestamp = datetime.now().strftime('%d %b, %Y %I:%M %p')
    
    slack_message = f"TEST: Received `{event}` event on branch `{event_branch}` for `{matching_project}`"
    
    return jsonify({
        "message": slack_message,
        "project": matching_project,
        "branch": event_branch,
        "event": event,
        "test_mode": True
    })

@app.route('/webhook/<branch>', methods=['POST'])
def handle_webhook(branch):
    """Handle incoming Git webhook events"""
    payload = request.data
    received_signature = request.headers.get('X-Hub-Signature-256', '')
    
    # Reload projects from database
    global PROJECTS
    PROJECTS = load_projects_from_database()
    
    print(f"Available projects: {list(PROJECTS.keys())}")
    print(f"Received signature: {received_signature}")
    
    # Test mode - bypass signature validation
    if not received_signature and request.headers.get('X-Test-Mode') == 'true':
        if PROJECTS:
            matching_project = list(PROJECTS.keys())[0]
            print(f"Test mode: Using project {matching_project}")
        else:
            return jsonify({"error": "No projects configured in database."}), 400
    else:
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
            return jsonify({
                "error": "Invalid signature or unknown project.", 
                "debug": {
                    "projects_count": len(PROJECTS), 
                    "has_signature": bool(received_signature),
                    "tip": "Use /test-webhook/<branch> for testing without signature"
                }
            }), 403
    
    project_config = PROJECTS[matching_project]
    event = request.headers.get('X-GitHub-Event', 'unknown')
    payload_data = json.loads(payload)
    ref = payload_data.get('ref', '')
    event_branch = ref.split('/')[-1] if 'refs/heads/' in ref else ''
    commit_message = payload_data.get('head_commit', {}).get('message', 'N/A')
    timestamp = datetime.now().strftime('%d %b, %Y %I:%M %p')
    deployment_response = "N/A"
    
    slack_message = f"Received `{event}` event on branch `{event_branch}` for `{matching_project}`"
    
    return jsonify({"message": slack_message})

def format_slack_payload(repo_name, event_type, when, branch, commit_message, deployment_response):
    """Format the payload for Slack notifications using Slack's Block Kit"""
    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{repo_name.strip('[]').replace('-', ' ').title()}* - Git Event Notification"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Event Type:*\n{event_type.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*When:*\n{when}"},
                    {"type": "mrkdwn", "text": f"*Branch:*\n{branch.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*Commit Message:*\n{commit_message}"},
                    {"type": "mrkdwn", "text": f"*Deployment Script Response:*\n{deployment_response}"}
                ]
            }
        ]
    }

def send_slack_notification(webhook_url, payload):
    """Send a Slack notification using the provided webhook URL and payload"""
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    if response.status_code != 200:
        print(f"Failed to send Slack notification: {response.text}")

# Start the Flask app if the script is run directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)