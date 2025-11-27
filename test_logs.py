#!/usr/bin/env python3
import requests
import time

# Test the logging by making requests to different endpoints
base_url = "http://localhost:5000"

def test_endpoints():
    print("Testing logging endpoints...")
    
    # Test 1: Index endpoint
    try:
        response = requests.get(f"{base_url}/")
        print(f"Index: {response.status_code}")
    except:
        print("App not running - start with: python app.py")
        return
    
    # Test 2: Debug endpoint
    try:
        response = requests.get(f"{base_url}/debug")
        print(f"Debug: {response.status_code}")
    except:
        pass
    
    # Test 3: Add project (will generate error logs)
    try:
        response = requests.post(f"{base_url}/add-project", json={})
        print(f"Add project (empty): {response.status_code}")
    except:
        pass
    
    # Test 4: Valid add project
    try:
        response = requests.post(f"{base_url}/add-project", json={
            "name": "Test Log Project",
            "deploy_script": "/test/script.sh",
            "slack_webhook": "https://hooks.slack.com/test"
        })
        print(f"Add project (valid): {response.status_code}")
    except:
        pass

if __name__ == "__main__":
    test_endpoints()