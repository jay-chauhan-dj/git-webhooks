import mysql.connector
from mysql.connector import Error
import secrets
import string
import os
from dotenv import load_dotenv

load_dotenv()

def create_mysql_database():
    """Create MySQL database and tables"""
    try:
        # Connect to MySQL server (without database)
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            port=int(os.getenv('DB_PORT', 3306))
        )
        
        cursor = connection.cursor()
        
        # Create database
        db_name = os.getenv('DB_NAME', 'git_webhooks')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                deploy_script TEXT NOT NULL,
                slack_webhook TEXT NOT NULL,
                secret VARCHAR(255)
            )
        ''')
        
        # Webhook events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS webhook_events (
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
        cursor.close()
        connection.close()
        print(f"MySQL database '{db_name}' created successfully with sample projects!")
        
    except Error as e:
        print(f"Error creating MySQL database: {e}")

if __name__ == '__main__':
    create_mysql_database()