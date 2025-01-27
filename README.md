
# Webhook Handler for Git Events

This project is a Flask-based webhook handler designed to process Git events dynamically, trigger deployment scripts, and send notifications to Slack. The app supports multiple projects through dynamic configuration using environment variables.

---

## Features

- Handles **Git webhooks** (e.g., `push` events).
- Validates incoming webhook requests using **HMAC** signatures.
- Supports **dynamic project configurations** via environment variables.
- Executes deployment scripts for specific branches and events.
- Sends **rich Slack notifications** with event details.
- Easily scalable to multiple projects with no code changes.

---

## Table of Contents

- [Requirements](#requirements)
- [Setup Guide](#setup-guide)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Deploying with Nginx](#deploying-with-nginx)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

---

## Requirements

- Python 3.8 or higher
- Flask
- Gunicorn
- Nginx (for production deployment)
- Slack Webhook URL
- Git webhook integration

---

## Setup Guide

Follow these steps to set up and run the webhook handler on your local machine or server.

### Step 1: Clone the Repository
\`\`\`bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
\`\`\`

### Step 2: Create a Virtual Environment
Create an isolated Python environment for the project:
\`\`\`bash
python3 -m venv venv
source venv/bin/activate
\`\`\`

### Step 3: Install Dependencies
Install all required Python libraries:
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### Step 4: Configure Environment Variables
1. Copy the example \`.env\` file:
   \`\`\`bash
   cp .env.example .env
   \`\`\`

2. Open the \`.env\` file and add project-specific details:
   \`\`\`dotenv
   # Example configuration for a project
   PROJECT_MY_PROJECT_DEPLOY_SCRIPT=/path/to/deploy/script.sh
   PROJECT_MY_PROJECT_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
   PROJECT_MY_PROJECT_SECRET=supersecretkey
   \`\`\`

3. Repeat for additional projects as needed.

### Step 5: Test the Application Locally
Run the Flask app:
\`\`\`bash
python webhook_app.py
\`\`\`

The app will start at \`http://127.0.0.1:5000\`. You can test it locally by sending webhook requests (see [Usage](#usage)).

---

## Configuration

### Environment Variables

The app uses environment variables for project-specific configurations. Add the following variables to your \`.env\` file:

\`\`\`dotenv
# Example configuration for a project
PROJECT_MY_PROJECT_DEPLOY_SCRIPT=/path/to/deploy/script.sh
PROJECT_MY_PROJECT_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
PROJECT_MY_PROJECT_SECRET=supersecretkey
\`\`\`

### Naming Convention

- **PROJECT_<PROJECT_NAME>_<ATTRIBUTE>**
  - `<PROJECT_NAME>`: A unique identifier for your project.
  - `<ATTRIBUTE>`: One of the following:
    - `DEPLOY_SCRIPT`: Path to the deployment script.
    - `SLACK_WEBHOOK`: Webhook URL for Slack notifications.
    - `SECRET`: Secret key for validating Git webhook requests.

---

## Running the Application

### Locally

1. Start the Flask app:
   \`\`\`bash
   python webhook_app.py
   \`\`\`
2. The app will run on \`http://127.0.0.1:5000\`.

### Using Gunicorn (Production)

1. Run the app with Gunicorn:
   \`\`\`bash
   gunicorn --bind 127.0.0.1:8000 webhook_app:app
   \`\`\`

---

## Deploying with Nginx

1. **Install Nginx**:
   \`\`\`bash
   sudo apt update
   sudo apt install nginx
   \`\`\`

2. **Configure Nginx**:
   Create a configuration file for your app:
   \`\`\`bash
   sudo nano /etc/nginx/sites-available/webhook-app
   \`\`\`
   Add the following:
   \`\`\`nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   \`\`\`

3. **Enable the configuration**:
   \`\`\`bash
   sudo ln -s /etc/nginx/sites-available/webhook-app /etc/nginx/sites-enabled/
   sudo systemctl restart nginx
   \`\`\`

4. **Run Gunicorn as a service**:
   Create a systemd service file for Gunicorn:
   \`\`\`bash
   sudo nano /etc/systemd/system/webhook-app.service
   \`\`\`
   Add the following:
   \`\`\`ini
   [Unit]
   Description=Gunicorn instance to serve webhook-app
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/path/to/your-app
   Environment="PATH=/path/to/your-app/venv/bin"
   ExecStart=/path/to/your-app/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 webhook_app:app

   [Install]
   WantedBy=multi-user.target
   \`\`\`

5. **Start and enable the service**:
   \`\`\`bash
   sudo systemctl start webhook-app
   sudo systemctl enable webhook-app
   \`\`\`

---

## Usage

1. **Set up a Git Webhook**:
   - URL: \`http://your-domain.com/webhook/<branch>\` (e.g., \`main\`).
   - Content type: \`application/json\`.
   - Secret: Use the same secret key defined in your \`.env\` file.

2. **Trigger events**:
   - Push to the configured branch.
   - Check Slack for notifications and verify the deployment script execution.

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch (\`feature/your-feature-name\`).
3. Commit your changes (\`git commit -m 'Add some feature'\`).
4. Push to the branch (\`git push origin feature/your-feature-name\`).
5. Open a Pull Request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Author

**Jay Chauhan**  
- Website: [www.dj-jay.in](http://www.dj-jay.in)
