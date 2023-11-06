import requests
import os
import json
import subprocess
# import logging

try:
    SYNTHETIC_MONITORING_ACCESS = os.environ['SYNTHETIC_MONITORING_ACCESS']
    SUBSCRIPTION_KEY = os.environ['SUBSCRIPTION_KEY']
    STATUS_PAGE_2_API_KEY = os.environ['STATUS_PAGE_2_API_KEY']
    STACK_ID = 780628
    METRICS_INSTANCE_ID = 1269157
    LOGS_INSTANCE_ID = 733624
except KeyError as e:
    print(f"Environment variable {e} not found.")
    exit(1)

GRAFANA_URL = 'https://synthetic-monitoring-api-us-east-0.grafana.net'
TOKEN_ENDPOINT = '/api/v1/register/install'
grafana_headers = {
    'Authorization': f'Bearer {SYNTHETIC_MONITORING_ACCESS}',
    'Content-Type': 'application/json'
}

payload = {
    'stackId': STACK_ID,
    'metricsInstanceId': METRICS_INSTANCE_ID,
    'logsInstanceId': LOGS_INSTANCE_ID
}

try:
    response = requests.post(f'{GRAFANA_URL}{TOKEN_ENDPOINT}', headers=grafana_headers, json=payload)
    response.raise_for_status()
    response_data = response.json()

    if 'accessToken' in response_data:
        access_token = response_data['accessToken']
        tenant_id = response_data['tenantInfo']['id']
        print(f'Successfully obtained tenant ID: {tenant_id}')
    else:
        print(f'Failed to obtain access token: {response_data}')
        exit(1)
except requests.exceptions.RequestException as e:
    print(f"Error during API request: {e}")
    if e.response:
        print(f"Response Content: {e.response.content}")
    exit(1)

grafana_headers['Authorization'] = f'Bearer {access_token}'

def check_exists_in_grafana(job_name, tenant_id):
    url = f"{GRAFANA_URL}/api/v1/check/list"  # Endpoint to list checks
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Ocp-Apim-Subscription-Key': SUBSCRIPTION_KEY
    }
    payload = {'tenantId': tenant_id}
    
    response = requests.get(url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print("Error Response Content while checking existence: " + response.text)
        response.raise_for_status()
    
    checks = response.json()
    for check in checks:
        if check['job'] == job_name:
            return True
    return False

def create_checks_in_grafana(checks_data, tenant_id):
    job_labels = []
    for check_data in checks_data:
        if check_exists_in_grafana(check_data['job'], tenant_id):
            print(f"Check {check_data['job']} already exists in Grafana")
            continue

        url = f"{GRAFANA_URL}/api/v1/check/add"  # Updated endpoint
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Ocp-Apim-Subscription-Key': SUBSCRIPTION_KEY
        }
        payload = {
            'tenantId': tenant_id,
            'job': check_data['job'],
            'target': check_data['url'],
            'probes': [3],
            'frequency': 60000,
            'timeout': 5000,
            'enabled': True,
            'settings': {
                'http': {
                    'method': 'GET',
                    'validStatusCodes': [200],
                    'headers': [f'Ocp-Apim-Subscription-Key: {SUBSCRIPTION_KEY}']
                }
            }
        }

        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print("Error Response Content: " + response.text)
            response.raise_for_status()
        job_labels.append(check_data['job'])
    return job_labels
# ====================== STATUSPAGE ======================

# Statuspage headers and constants
statuspage_base_url = "https://api.statuspage.io/v1/pages/pwpz1wk1fs7z"
statuspage_headers = {
    "Authorization": f"OAuth {os.getenv('STATUS_PAGE_2_API_KEY')}",
    "Content-Type": "application/json"
}

def setup_self_metric_provider(base_url, headers):
    response = requests.get(f"{base_url}/metrics_providers", headers=headers)
    response_data = response.json()
    if isinstance(response_data, list):
        for provider in response_data:
            if provider['type'] == 'Self' and not provider['disabled']:
                return provider['id']

    data = {"metrics_provider": {"type": "Self"}}
    response = requests.post(f"{base_url}/metrics_providers", headers=headers, json=data)
    
    if response.status_code != 201:
        raise ValueError(f"API Error: {response.json().get('error', 'Unknown error')}")
    return response.json()['id']

def component_exists(base_url, headers, component_name):
    response = requests.get(f"{base_url}/components", headers=headers)
    components = response.json()
    for component in components:
        if component['name'] == component_name:
            print(f"Component {component_name} already exists in Components. Skipping creation.")
            return True
    return False

def create_component(base_url, headers, component_name):
    if component_exists(base_url, headers, component_name):
        return
    data = {
        "component": {
            "name": component_name,
            "status": "operational"
        }
    }
    response = requests.post(f"{base_url}/components", headers=headers, json=data)
    if response.status_code != 201:
        raise ValueError(f"API Error while creating component: {response.json().get('error', 'Unknown error')}")
    return response.json()['id']

def metric_exists(base_url, headers, metric_name, metrics_provider_id):
    response = requests.get(f"{base_url}/metrics_providers/{metrics_provider_id}/metrics", headers=headers)
    metrics = response.json()
    for metric in metrics:
        if metric['name'] == metric_name:
            print(f"Metric {metric_name} already exists in Metrics. Skipping creation.")
            return True
    return False

def create_metric(base_url, headers, metric_name, metrics_provider_id):
    if metric_exists(base_url, headers, metric_name, metrics_provider_id):
        return
    data = {
        "metric": {
            "name": metric_name,
            "suffix": "ms",
            "display": True,
            "decimal_places": 2
        }
    }
    response = requests.post(f"{base_url}/metrics_providers/{metrics_provider_id}/metrics", headers=headers, json=data)
    if response.status_code != 201:
        raise ValueError(f"API Error while creating metric: {response.json().get('error', 'Unknown error')}")
    return response.json()['id']

# ... (Previous parts of the script)

def create_statuspage_items(job_labels, headers, base_url):
    try:
        metric_provider_id = setup_self_metric_provider(base_url, headers)
        created_components_metrics = []
        for label in job_labels:
            component_id = create_component(base_url, headers, label)
            metric_id = create_metric(base_url, headers, f"{label} Metric", metric_provider_id)
            created_components_metrics.append((label, component_id, metric_id))
        return created_components_metrics
    except Exception as e:
        print(f"Error creating Statuspage items: {e}")
        exit(1)

# ====================== GIT FUNCTIONS ======================

# def git_has_changes():
#     status = subprocess.check_output(['git', 'status', '--porcelain'])
#     return len(status) > 0

# def git_pull(branch_name):
#     try:
#         subprocess.check_call(['git', 'checkout', branch_name])
#         subprocess.check_call(['git', 'stash'])  # Stash any local changes
#         subprocess.check_call(['git', 'pull', '--rebase', 'origin', branch_name])
#         subprocess.check_call(['git', 'stash', 'pop'])  # Apply stashed changes
#         print("Pulled the latest changes from the remote repository and reapplied local changes.")
#     except subprocess.CalledProcessError as e:
#         print(f"An error occurred while pulling changes: {e}")
#         exit(1)

# def git_push(file_path, commit_message, branch_name, user_name, user_email):
#     try:
#         # Set Git user identity
#         subprocess.check_call(['git', 'config', 'user.email', user_email])
#         subprocess.check_call(['git', 'config', 'user.name', user_name])

#         # Retrieve the personal access token from the environment variable
#         personal_access_token = "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"
#         if not personal_access_token:
#             raise ValueError("The personal access token is not set in the environment variables.")

#         # Set the Git remote URL using the personal access token
#         git_url = f'https://bertrandmbanwi:{personal_access_token}@github.com/bertrandmbanwi/status-page-2.git'
#         subprocess.check_call(['git', 'remote', 'set-url', 'origin', git_url])

#         # Add and commit changes
#         subprocess.check_call(['git', 'add', file_path])
#         subprocess.check_call(['git', 'commit', '-m', commit_message])

#         # Push changes to remote repository
#         subprocess.check_call(['git', 'push', 'origin', branch_name])
#         print(f"Pushed commit to remote branch {branch_name}.")
#     except subprocess.CalledProcessError as e:
#         print(f"An error occurred while pushing changes: {e}")
#         exit(1)


# ====================== MAIN EXECUTION ======================

def main():
    try:
        checks_data = [
            {
                'url': 'https://digital-marketplace-demo-app.azure-api.net/foodinfec-1/foodinfec-1?state=CA',
                'job': 'Food Infection API - CA',
            },
            {
                'url': 'https://digital-marketplace-demo-app.azure-api.net/tusd/upload',
                'job': 'Tusd API',
            }
            # ... (Any additional checks_data items you might have)
        ]
    
        print("Creating checks in Grafana...")
        job_labels = create_checks_in_grafana(checks_data, tenant_id)
        
        print("Creating Statuspage components and metrics...")
        created_items = create_statuspage_items(job_labels, statuspage_headers, statuspage_base_url)
        
        print("Writing to checks_config.json...")
        output_checks = [
            {
                "name": item[0],
                "job_label": item[0],
                "statuspage_metric_id": item[2],
                "statuspage_component_id": item[1]
            } for item in created_items if item[1] is not None and item[2] is not None
        ]

        output = {"checks": output_checks}
        checks_config_content = json.dumps(output, indent=4)
        
        # GitHub API setup
        personal_access_token = os.getenv('ACCESS_TOKEN')
        if not personal_access_token:
            raise ValueError("The personal access token is not set in the environment variables.")
        url = "https://api.github.com/repos/bertrandmbanwi/status-page-2/contents/checks_config.json"
        headers = {
            "Authorization": f"token {personal_access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        # Assuming you have your file content in a variable `content`
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        # Retrieve the file SHA from GitHub to update it
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sha = response.json()['sha']
        else:
            raise Exception(f"Failed to retrieve file SHA: {response.content}")

        # Prepare the payload with the new content
        data = {
            "message": "Update checks configuration",
            "content": encoded_content,
            "sha": sha,
            "branch": "main",
        }

        # Send the request to update the file on GitHub
        response = requests.put(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            print("File updated successfully on GitHub!")
        else:
            print(f"Failed to update file on GitHub: {response.content}")

    except Exception as e:
        print(f"An error occurred in the main execution: {e}")
        exit(1)

if __name__ == "__main__":
    main()