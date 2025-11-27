# Git Webhook Handler - Manager Demo

## What This System Does
- **Automatically manages Git webhook projects**
- **No manual .env file editing needed**
- **Database-driven configuration**
- **Auto-generates secure secrets**
- **Real-time webhook processing**

## Key Features Demonstrated

### 1. Database-Driven (No Manual Config)
- All project data stored in SQLite database
- No need to manually edit configuration files
- Projects can be added via API calls

### 2. Automatic Project Management
```bash
# System automatically creates database with sample projects
python app.py
```

### 3. Add Projects via API
```bash
POST http://localhost:5000/add-project
{
    "name": "New Project",
    "deploy_script": "/path/to/deploy.sh", 
    "slack_webhook": "https://hooks.slack.com/webhook"
}
```

### 4. Real-time Webhook Processing
```bash
POST http://localhost:5000/webhook/main
# Processes GitHub webhooks with signature validation
```

### 5. Testing Without GitHub
```bash
POST http://localhost:5000/test-webhook/main
# Test webhook processing without GitHub signatures
```

## Demo Flow for Manager

1. **Show System Status**
   - `GET /debug` - Shows current projects from database

2. **Add New Project Live**
   - `POST /add-project` - Add project via API
   - Show auto-generated secret
   - Verify in `/debug` endpoint

3. **Test Webhook Processing**
   - `POST /test-webhook/main` - Simulate GitHub webhook
   - Show real-time processing

4. **Show Database Integration**
   - Projects stored in `projects.db`
   - No manual configuration needed
   - Scalable for multiple projects

## Benefits for Production

✅ **No Manual Work** - Projects added via API  
✅ **Secure** - Auto-generated secrets  
✅ **Scalable** - Database-driven  
✅ **Real-time** - Immediate webhook processing  
✅ **Maintainable** - Clean separation of concerns  

## Technical Stack
- **Backend**: Python Flask
- **Database**: SQLite (easily upgradeable to PostgreSQL/MySQL)
- **Security**: HMAC signature validation
- **Integration**: GitHub webhooks, Slack notifications