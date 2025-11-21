import sqlite3
import secrets
import string
import os

def create_database():
    """Create database with proper schema"""
    if os.path.exists('projects.db'):
        os.remove('projects.db')
    
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
    
    # Webhook events table with repository URLs
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
    print("Database created successfully with sample projects!")

if __name__ == '__main__':
    create_database()