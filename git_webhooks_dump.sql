-- MySQL dump for git_webhooks database
-- Generated automatically

DROP DATABASE IF EXISTS git_webhooks;
CREATE DATABASE git_webhooks;
USE git_webhooks;

-- Table structure for projects
CREATE TABLE projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    deploy_script TEXT NOT NULL,
    slack_webhook TEXT NOT NULL,
    secret VARCHAR(255)
);

-- Table structure for webhook_events
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
);

-- Data for projects
INSERT INTO projects (id, name, deploy_script, slack_webhook, secret) VALUES (1, 'My First Project', '/path/to/my_first_project/deploy_script.sh', 'https://hooks.slack.com/services/XXX/YYY/ZZZ', '6sFzqHpY4VnJDyMxOqH7W00gOiUgI517');
INSERT INTO projects (id, name, deploy_script, slack_webhook, secret) VALUES (2, 'Another Project', '/path/to/another_project/deploy_script.sh', 'https://hooks.slack.com/services/AAA/BBB/CCC', '1mRN40esffGBrKEQS98wdTrQ2beiMY5j');
INSERT INTO projects (id, name, deploy_script, slack_webhook, secret) VALUES (3, 'Test Project', '/path/to/test/deploy.sh', 'https://hooks.slack.com/test', 'WeJTv2i0U9iSExVo5CjjxoLRUUdY4DbS');

-- Data for webhook_events
