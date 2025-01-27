# File: webhook_app.py
# Author: Jay Chauhan
# Website: www.dj-jay.in
# Description:
# This script is a Flask-based webhook handler that dynamically loads project configurations
# from environment variables, validates Git webhook requests, triggers deployment scripts,
# and sends Slack notifications with detailed event information.

from flask import Flask, request, jsonify  # Import Flask modules for web app and request handling
import hmac  # Import HMAC for request signature validation
import hashlib  # Import hashlib for hashing algorithms
import subprocess  # Import subprocess for running external commands
import json  # Import JSON to handle webhook payloads
import requests  # Import requests for sending HTTP requests (e.g., Slack notifications)
import os  # Import os to access environment variables
from dotenv import load_dotenv  # Import dotenv to load environment variables from a .env file
from datetime import datetime  # Import datetime for handling timestamps
from collections import defaultdict  # Import defaultdict for constructing dynamic dictionaries

# Load environment variables from a .env file to make sensitive data manageable
load_dotenv()

# Initialize the Flask app instance
app = Flask(__name__)

@app.route('/', methods=['GET'])  # Define the root route
def index():
    """
    Handle requests to the base URL.

    Returns:
        JSON response indicating the application is running.
    """
    return jsonify({"status": "success", "message": "Webhook handler is deployed and running successfully."})

def load_projects_from_env():
    """
    Dynamically load project configurations from environment variables.

    Returns:
        dict: A dictionary where each key is a project name and the value is a dictionary of its settings.
    """
    projects = defaultdict(dict)  # Use defaultdict to handle dynamic project creation
    for key, value in os.environ.items():  # Iterate through all environment variables
        if key.startswith("PROJECT_"):  # Check if the variable is related to a project
            _, project_name, attribute = key.split("_", 2)  # Split the key into project name and attribute
            project_name = project_name.lower()  # Normalize project name to lowercase
            attribute = attribute.lower()  # Normalize attribute name to lowercase
            projects[project_name][attribute] = value  # Add the attribute to the project dictionary
    return projects  # Return the dynamically constructed projects dictionary

# Generate the PROJECTS dictionary dynamically by calling the load_projects_from_env function
PROJECTS = load_projects_from_env()

@app.route('/webhook/<branch>', methods=['POST'])  # Define a POST route to handle incoming webhooks
def handle_webhook(branch):
    """
    Handle incoming Git webhook events.

    Args:
        branch (str): The branch specified in the URL (e.g., 'main').

    Returns:
        JSON response indicating the status of the request handling.
    """
    # Extract the project name from the request headers
    project_name = request.headers.get('X-GitHub-Project', 'unknown').lower()
    project_config = PROJECTS.get(project_name)  # Fetch the project configuration for the given project name
    if not project_config:  # If the project configuration is not found
        return jsonify({"error": "Unknown project"}), 400  # Return an error response with status 400

    # Validate the HMAC signature for the request
    secret = project_config.get("secret", "")  # Retrieve the secret key for the project
    payload = request.data  # Extract the raw payload data from the request
    signature = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()  # Generate the HMAC signature
    if not hmac.compare_digest(signature, request.headers.get('X-Hub-Signature-256', '')):  # Compare signatures securely
        return jsonify({"error": "Invalid signature"}), 403  # Return an error response with status 403

    # Parse the payload to extract event details
    event = request.headers.get('X-GitHub-Event', 'unknown')  # Get the event type from headers
    payload_data = json.loads(payload)  # Convert the JSON payload into a Python dictionary
    ref = payload_data.get('ref', '')  # Get the reference string (e.g., 'refs/heads/main')
    event_branch = ref.split('/')[-1] if 'refs/heads/' in ref else ''  # Extract the branch name from the reference
    commit_message = payload_data.get('head_commit', {}).get('message', 'N/A')  # Get the commit message, default to 'N/A'
    timestamp = datetime.now().strftime('%d %b, %Y %I:%M %p')  # Format the current timestamp for Slack notification
    deployment_response = "N/A"  # Initialize the deployment response message

    # Prepare the Slack message and handle specific Git events
    slack_message = f"Received `{event}` event on branch `{event_branch}` for `{project_name}`"  # Base Slack message
    if event == "push" and branch == "main" and event_branch == branch:  # Check if the event is a push to the main branch
        try:
            # Run the deployment script using subprocess with sudo
            subprocess.run(
                ["sudo", project_config.get("deploy_script")],  # Command to run the deployment script
                check=True,  # Ensure the command raises an exception on failure
                capture_output=True,  # Capture the output of the script
            )
            deployment_response = "Success"  # Update the response to indicate success
            slack_message += " - Deployment started successfully."  # Append success message to Slack notification
        except subprocess.CalledProcessError as e:  # Catch exceptions if the script fails
            deployment_response = f"Failed: {e.output.decode()}"  # Capture and decode the error output
            slack_message += f" - Deployment failed: {deployment_response}"  # Append failure message to Slack notification

    # Send the prepared Slack notification
    send_slack_notification(
        project_config.get("slack_webhook"),  # Get the Slack webhook URL from the project configuration
        format_slack_payload(  # Format the Slack payload with the event details
            project_name,
            event,
            timestamp,
            branch,
            commit_message,
            deployment_response,
        ),
    )
    return jsonify({"message": slack_message})  # Return the Slack message as a JSON response

def format_slack_payload(repo_name, event_type, when, branch, commit_message, deployment_response):
    """
    Format the payload for Slack notifications using Slack's Block Kit.

    Args:
        repo_name (str): Repository name.
        event_type (str): Type of event (e.g., 'push').
        when (str): Timestamp of the event.
        branch (str): Target branch for the event.
        commit_message (str): Commit message associated with the event.
        deployment_response (str): Result of the deployment script.

    Returns:
        dict: Slack notification payload formatted as a JSON object.
    """
    return {
        "blocks": [
            {
                "type": "section",  # Section block for the title
                "text": {
                    "type": "mrkdwn",  # Markdown-enabled text
                    "text": f"*[{repo_name}]* - Git Event Notification"  # Title text with repository name
                }
            },
            {
                "type": "section",  # Section block for event details
                "fields": [
                    {"type": "mrkdwn", "text": f"*Event Type:*\n{event_type.capitalize()}"},  # Event type field
                    {"type": "mrkdwn", "text": f"*When:*\n{when}"},  # Timestamp field
                    {"type": "mrkdwn", "text": f"*Branch:*\n{branch.capitalize()}"},  # Branch field
                    {"type": "mrkdwn", "text": f"*Commit Message:*\n{commit_message}"},  # Commit message field
                    {"type": "mrkdwn", "text": f"*Deployment Script Response:*\n{deployment_response}"}  # Response field
                ]
            }
        ]
    }

def send_slack_notification(webhook_url, payload):
    """
    Send a Slack notification using the provided webhook URL and payload.

    Args:
        webhook_url (str): The Slack webhook URL for sending notifications.
        payload (dict): The payload containing the message details.

    Returns:
        None
    """
    headers = {"Content-Type": "application/json"}  # Set the content type for the Slack API request
    response = requests.post(webhook_url, data=json.dumps(payload), headers=headers)  # Send the POST request to Slack
    if response.status_code != 200:  # Check if the response indicates an error
        print(f"Failed to send Slack notification: {response.text}")  # Log the error if the request fails

# Start the Flask app if the script is run directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Run the app on all network interfaces, listening on port 5000
