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
import logging
import threading
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from db_config import get_db_connection, execute_query

load_dotenv()

# Load configuration from JSON file
def load_config():
    """Load configuration from config.json file"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("config.json file not found")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing config.json: {e}")
        return None

# Global configuration
CONFIG = load_config()
if not CONFIG:
    raise Exception("Failed to load configuration")

# Table names from config
TABLE_PROJECTS = CONFIG['database']['tables']['projects']
TABLE_WEBHOOK_EVENTS = CONFIG['database']['tables']['webhook_events']

# Configure logging with detailed formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('webhook_app.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_section(title, details=None):
    """Log a formatted section with title and optional details"""
    logger.info("#" * 60)
    logger.info(f"# {title}")
    logger.info("#" * 60)
    if details:
        for key, value in details.items():
            logger.info(f"# {key}: {value}")
        logger.info("#" * 60)

def process_webhook_background(project_config, payload_data, event):
    """Process webhook in background thread for fast response"""
    try:
        logger.info(f"🚀 Background processing started for {project_config['name']}")
        
        # Save to database
        logger.info(f"📝 Step 1/3: Saving event to database...")
        save_webhook_event(project_config['name'], payload_data, event)
        
        # Send Slack notification
        if project_config.get('slack_webhook'):
            logger.info(f"📱 Step 2/3: Sending Slack notification...")
            send_slack_notification(project_config['slack_webhook'], payload_data, project_config['name'])
        else:
            logger.info(f"⏭️ Step 2/3: Skipped - No Slack webhook configured")
        
        # Execute deployment script
        if project_config.get('deploy_script'):
            logger.info(f"⚙️ Step 3/3: Executing deployment script...")
            execute_deployment_script(project_config['deploy_script'], project_config['name'])
        else:
            logger.info(f"⏭️ Step 3/3: Skipped - No deployment script configured")
            
        log_section("BACKGROUND PROCESSING COMPLETE", {
            "Project": project_config['name'],
            "Status": "SUCCESS",
            "Thread": threading.current_thread().name
        })
            
    except Exception as e:
        logger.error(f"❌ BACKGROUND ERROR: Processing failed - {e}")
        logger.error(f"   Project: {project_config['name']}")

# Initialize the Flask app instance
app = Flask(__name__)

def init_database():
    """Initialize MySQL database with sample projects if tables don't exist"""
    logger.info(f"Starting database initialization with tables: {TABLE_PROJECTS}, {TABLE_WEBHOOK_EVENTS}")
    connection = get_db_connection()
    if not connection:
        logger.error("Failed to connect to MySQL database")
        return
    
    try:
        cursor = connection.cursor()
        
        # Check if projects table exists
        cursor.execute(f"SHOW TABLES LIKE '{TABLE_PROJECTS}'")
        if not cursor.fetchone():
            # Projects table
            cursor.execute(f'''
                CREATE TABLE {TABLE_PROJECTS} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    deploy_script TEXT NOT NULL,
                    slack_webhook TEXT NOT NULL,
                    secret VARCHAR(255)
                )
            ''')
            
            # Webhook events table
            cursor.execute(f'''
                CREATE TABLE {TABLE_WEBHOOK_EVENTS} (
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
                    f"INSERT INTO {TABLE_PROJECTS} (name, deploy_script, slack_webhook, secret) VALUES (%s, %s, %s, %s)",
                    (name, script, webhook, secret)
                )
            
            connection.commit()
            logger.info(f"MySQL database initialized with tables: {TABLE_PROJECTS}, {TABLE_WEBHOOK_EVENTS}")
        else:
            logger.info(f"Database tables already exist: {TABLE_PROJECTS}")
        
        cursor.close()
        connection.close()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        if connection:
            connection.close()

def load_projects_from_database():
    """Load project configurations directly from MySQL database"""
    logger.info(f"Loading projects from table: {TABLE_PROJECTS}")
    projects = defaultdict(dict)
    
    try:
        db_projects = execute_query(f"SELECT name, deploy_script, slack_webhook, secret FROM {TABLE_PROJECTS}", fetch=True)
        
        if db_projects:
            for name, deploy_script, slack_webhook, secret in db_projects:
                project_key = name.lower().replace(" ", "_").replace("-", "_")
                projects[project_key] = {
                    'deploy_script': deploy_script,
                    'slack_webhook': slack_webhook,
                    'secret': secret,
                    'name': name
                }
            logger.info(f"Loaded {len(projects)} projects from database")
        else:
            logger.warning("No projects found in database")
    except Exception as e:
        logger.error(f"Error loading projects from database: {e}")
    
    return projects

def send_slack_notification(slack_webhook, payload_data, project_name):
    """Send Slack notification with webhook details"""
    log_section("SLACK NOTIFICATION", {
        "Project": project_name,
        "Webhook URL": slack_webhook[:50] + "...",
        "Status": "Preparing"
    })
    
    try:
        repository = payload_data.get('repository', {})
        repo_name = repository.get('name', 'Unknown')
        ref = payload_data.get('ref', '')
        branch = ref.split('/')[-1] if 'refs/heads/' in ref else 'Unknown'
        
        head_commit = payload_data.get('head_commit', {})
        commit_message = head_commit.get('message', 'N/A')
        commit_id = head_commit.get('id', 'N/A')[:7]
        
        author = head_commit.get('author', {})
        author_name = author.get('name', 'Unknown')
        
        logger.info(f"📤 Preparing Slack message:")
        logger.info(f"   Repository: {repo_name}")
        logger.info(f"   Branch: {branch}")
        logger.info(f"   Commit: {commit_id}")
        logger.info(f"   Author: {author_name}")
        logger.info(f"   Message: {commit_message[:100]}...")
        
        message = {
            "text": f"🚀 Deployment triggered for {project_name}",
            "attachments": [{
                "color": "good",
                "fields": [
                    {"title": "Repository", "value": repo_name, "short": True},
                    {"title": "Branch", "value": branch, "short": True},
                    {"title": "Commit", "value": commit_id, "short": True},
                    {"title": "Author", "value": author_name, "short": True},
                    {"title": "Message", "value": commit_message, "short": False}
                ]
            }]
        }
        
        logger.info(f"🌐 Sending POST request to Slack...")
        response = requests.post(slack_webhook, json=message, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ SUCCESS: Slack notification sent successfully")
            logger.info(f"   Response: {response.status_code} - Message delivered")
        else:
            logger.error(f"❌ FAILED: Slack notification failed")
            logger.error(f"   Status Code: {response.status_code}")
            logger.error(f"   Response: {response.text[:200]}")
            
    except Exception as e:
        logger.error(f"❌ ERROR: Slack notification exception - {e}")

def execute_deployment_script(deploy_script, project_name):
    """Execute deployment script"""
    log_section("DEPLOYMENT SCRIPT EXECUTION", {
        "Project": project_name,
        "Script Path": deploy_script,
        "Status": "Starting"
    })
    
    try:
        logger.info(f"🔧 Preparing to execute deployment script...")
        logger.info(f"   Script: {deploy_script}")
        logger.info(f"   Timeout: 300 seconds")
        
        start_time = datetime.now()
        logger.info(f"⏰ Execution started at: {start_time.strftime('%H:%M:%S')}")
        
        result = subprocess.run(["/usr/bin/sudo", deploy_script], capture_output=True, text=True, timeout=300)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"⏱️ Execution completed in {duration:.2f} seconds")
        logger.info(f"📊 Return Code: {result.returncode}")
        
        if result.returncode == 0:
            logger.info(f"✅ SUCCESS: Deployment script executed successfully")
            if result.stdout:
                logger.info(f"📝 Script Output: {result.stdout[:500]}")
        else:
            logger.error(f"❌ FAILED: Deployment script execution failed")
            logger.error(f"   Return Code: {result.returncode}")
            if result.stderr:
                logger.error(f"   Error Output: {result.stderr[:500]}")
            if result.stdout:
                logger.error(f"   Standard Output: {result.stdout[:500]}")
                
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ TIMEOUT: Deployment script exceeded 300 seconds")
        logger.error(f"   Script: {deploy_script}")
    except FileNotFoundError:
        logger.error(f"📁 FILE NOT FOUND: Deployment script does not exist")
        logger.error(f"   Path: {deploy_script}")
    except Exception as e:
        logger.error(f"❌ ERROR: Deployment script execution exception - {e}")

def save_webhook_event(project_name, payload_data, event_type):
    """Save webhook event to MySQL database"""
    try:
        logger.info(f"Saving webhook event for project: {project_name}, event: {event_type}")
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
        
        query = f'''
            INSERT INTO {TABLE_WEBHOOK_EVENTS} 
            (project_name, repository_name, repository_url, clone_url, event_type, branch, commit_message, 
             commit_id, author_name, author_email, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        params = (project_name, repo_name, repo_url, clone_url, event_type, branch, commit_message, 
                  commit_id, author_name, author_email, timestamp)
        
        execute_query(query, params)
        logger.info(f"Webhook event saved successfully for {repo_name}/{branch}")
    except Exception as e:
        logger.error(f"Error saving webhook event: {e}")

# Global variable for projects
PROJECTS = {}

@app.route('/', methods=['GET'])
def index():
    """Handle requests to the base URL"""
    logger.info("Index endpoint accessed")
    return jsonify({"status": "success", "message": "Webhook handler is deployed and running successfully."})

@app.route('/debug', methods=['GET'])
def debug_info():
    """Show current configuration and status"""
    logger.info("Debug endpoint accessed")
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
    query = f'''
        SELECT project_name, repository_name, repository_url, clone_url, event_type, branch, 
               commit_message, author_name, timestamp, created_at
        FROM {TABLE_WEBHOOK_EVENTS} 
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
    logger.info("Add project endpoint accessed")
    data = request.json
    if not data:
        logger.warning("No data received in add-project request")
        return jsonify({"error": "No data received"}), 400

    name = data.get("name")
    deploy_script = data.get("deploy_script")
    slack_webhook = data.get("slack_webhook")

    if not all([name, deploy_script, slack_webhook]):
        logger.warning(f"Missing required fields for project: {name}")
        return jsonify({"error": "Missing required fields: name, deploy_script, slack_webhook"}), 400

    try:
        # Generate secret key automatically
        secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        
        query = f"INSERT INTO {TABLE_PROJECTS} (name, deploy_script, slack_webhook, secret) VALUES (%s, %s, %s, %s)"
        params = (name, deploy_script, slack_webhook, secret)
        
        result = execute_query(query, params)
        
        if result is None:
            logger.error(f"Database connection failed while adding project: {name}")
            return jsonify({"error": "Database connection failed"}), 500
        
        # Reload projects
        global PROJECTS
        PROJECTS = load_projects_from_database()
        
        logger.info(f"Project '{name}' added successfully")
        return jsonify({
            "message": f"Project '{name}' added successfully!",
            "project_name": name,
            "secret_key": secret,
            "webhook_url": f"http://localhost:5000/webhook/main",
            "timestamp": datetime.now().strftime('%d %b, %Y %I:%M %p')
        }), 200
        
    except Exception as e:
        logger.error(f"Database error while adding project '{name}': {e}")
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

@app.route('/webhook-test/<branch>', methods=['POST'])
def test_webhook_fast(branch):
    """Test fast webhook processing without signature validation"""
    start_time = datetime.now()
    
    logger.info(f"🧪 TEST WEBHOOK: {branch} from {request.remote_addr}")
    
    payload_data = request.get_json()
    if not payload_data:
        return jsonify({"error": "No JSON data received"}), 400
    
    global PROJECTS
    if not PROJECTS:
        PROJECTS = load_projects_from_database()
    
    # Use first available project for testing
    if not PROJECTS:
        return jsonify({"error": "No projects configured"}), 404
    
    project_config = list(PROJECTS.values())[0]
    
    # IMMEDIATE RESPONSE
    response_time = (datetime.now() - start_time).total_seconds() * 1000
    
    response_data = {
        "status": "success",
        "message": "TEST webhook received and processing started",
        "project": project_config['name'],
        "response_time_ms": f"{response_time:.2f}",
        "processing": "background",
        "test_mode": True
    }
    
    # Start background processing
    try:
        event = request.headers.get('X-GitHub-Event', 'push')
        
        logger.info(f"⚡ TEST FAST RESPONSE: {response_time:.2f}ms")
        
        # Create and start background thread
        thread = threading.Thread(
            target=process_webhook_background,
            args=(project_config, payload_data, event),
            name=f"test-webhook-{datetime.now().strftime('%H%M%S')}"
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"🧵 Test background thread started: {thread.name}")
            
    except Exception as e:
        logger.error(f"❌ TEST ERROR: {e}")
        response_data["warning"] = str(e)
    
    return jsonify(response_data)

@app.route('/test-slack', methods=['POST'])
def test_slack_simple():
    """Test Slack notification - simpler version"""
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Another Project')
    
    global PROJECTS
    if not PROJECTS:
        PROJECTS = load_projects_from_database()
    
    # Find project
    project_config = None
    for proj_key, config in PROJECTS.items():
        if config['name'].lower() == project_name.lower():
            project_config = config
            break
    
    if not project_config:
        # Use first available project
        if PROJECTS:
            project_config = list(PROJECTS.values())[0]
        else:
            return jsonify({"error": "No projects found"}), 404
    
    # Test payload
    test_payload = {
        "repository": {"name": "test-repo"},
        "ref": "refs/heads/main",
        "head_commit": {
            "message": "Test Slack notification from Postman",
            "id": "abc123def456",
            "author": {"name": "Test User"}
        }
    }
    
    # Send Slack notification
    send_slack_notification(project_config['slack_webhook'], test_payload, project_config['name'])
    
    return jsonify({
        "status": "success",
        "message": f"Slack notification sent to {project_config['name']}",
        "webhook_url": project_config['slack_webhook'][:50] + "..."
    })

@app.route('/test-slack/<project_name>', methods=['POST'])
def test_slack_notification(project_name):
    """Test Slack notification for a specific project"""
    global PROJECTS
    if not PROJECTS:
        PROJECTS = load_projects_from_database()
    
    # URL decode project name
    import urllib.parse
    project_name = urllib.parse.unquote(project_name)
    
    # Find project (case insensitive)
    project_config = None
    for proj_key, config in PROJECTS.items():
        if (config['name'].lower() == project_name.lower() or 
            proj_key.lower() == project_name.lower().replace(' ', '_').replace('-', '_')):
            project_config = config
            break
    
    if not project_config:
        available_projects = [config['name'] for config in PROJECTS.values()]
        return jsonify({
            "error": f"Project '{project_name}' not found",
            "available_projects": available_projects
        }), 404
    
    # Create test payload
    test_payload = {
        "repository": {"name": "test-repo"},
        "ref": "refs/heads/main",
        "head_commit": {
            "message": "Test commit for Slack notification",
            "id": "abc123def456",
            "author": {"name": "Test User"}
        }
    }
    
    # Send test Slack notification
    send_slack_notification(project_config['slack_webhook'], test_payload, project_config['name'])
    
    return jsonify({
        "status": "success",
        "message": f"Test Slack notification sent for {project_config['name']}",
        "slack_webhook": project_config['slack_webhook'][:50] + "..."
    })

@app.route('/webhook/<branch>', methods=['POST'])
def handle_webhook(branch):
    """Handle incoming Git webhook events - FAST response with background processing"""
    start_time = datetime.now()
    
    log_section("WEBHOOK RECEIVED", {
        "Branch": branch,
        "Client IP": request.remote_addr,
        "Content Length": len(request.data),
        "Event Type": request.headers.get('X-GitHub-Event', 'unknown'),
        "Timestamp": start_time.strftime('%Y-%m-%d %H:%M:%S')
    })
    
    payload = request.data
    received_signature = request.headers.get('X-Hub-Signature-256', '')
    
    logger.info(f"🔐 Fast signature validation...")
    
    global PROJECTS
    if not PROJECTS:
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
            logger.info(f"✅ VALIDATED: {config['name']}")
            break

    if not matching_project:
        logger.warning(f"⚠️ INVALID SIGNATURE: {branch} from {request.remote_addr}")
        return jsonify({"error": "Invalid signature"}), 403
    
    # IMMEDIATE RESPONSE - Don't wait for processing
    response_time = (datetime.now() - start_time).total_seconds() * 1000
    
    response_data = {
        "status": "success",
        "message": "Webhook received and processing started",
        "project": project_config['name'],
        "response_time_ms": f"{response_time:.2f}",
        "processing": "background"
    }
    
    # Start background processing in separate thread
    try:
        payload_data = json.loads(payload)
        event = request.headers.get('X-GitHub-Event', 'push')
        
        logger.info(f"⚡ FAST RESPONSE: {response_time:.2f}ms - Starting background thread")
        
        # Create and start background thread
        thread = threading.Thread(
            target=process_webhook_background,
            args=(project_config, payload_data, event),
            name=f"webhook-{project_config['name']}-{datetime.now().strftime('%H%M%S')}"
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"🧵 Background thread started: {thread.name}")
            
    except Exception as e:
        logger.error(f"❌ ERROR: Failed to start background processing - {e}")
        response_data["warning"] = "Background processing failed to start"
    
    return jsonify(response_data)

# Initialize database and load projects
log_section("APPLICATION STARTUP", {
    "Application": CONFIG['application']['name'],
    "Version": CONFIG['application']['version'],
    "Author": CONFIG['application']['author'],
    "Website": CONFIG['application']['website'],
    "Start Time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    "Projects Table": TABLE_PROJECTS,
    "Events Table": TABLE_WEBHOOK_EVENTS
})

init_database()
PROJECTS = load_projects_from_database()

# Start the Flask app if the script is run directly
if __name__ == '__main__':
    app_host = CONFIG['application']['host']
    app_port = int(os.getenv('APP_PORT', CONFIG['application']['port']))
    
    log_section("FLASK SERVER STARTUP", {
        "Host": app_host,
        "Port": app_port,
        "Debug Mode": "False",
        "Projects Loaded": len(PROJECTS),
        "Config File": "config.json"
    })
    logger.info("🚀 Starting Flask application...")
    logger.info(f"📡 Server will be accessible at: http://localhost:{app_port}")
    logger.info(f"🔗 Webhook endpoint: http://localhost:{app_port}/webhook/<branch>")
    logger.info(f"📊 Debug endpoint: http://localhost:{app_port}/debug")
    app.run(host=app_host, port=app_port)
