import time
import json
import requests
import os

# Retrieve environment variables
api_key = os.environ['STATUS_PAGE_2_API_KEY']
GRAFANA_API_KEY = os.environ['GRAFANA_API_KEY']

# Statuspage configuration
page_id = 'pwpz1wk1fs7z'
api_base = 'https://api.statuspage.io'

# Grafana configuration
PROMETHEUS_URL = 'https://prometheus-us-central2.grafana.net/api/prom/api/v1/query'

# Load checks from configuration file
with open('checks_config.json', 'r') as f:
    checks = json.load(f)['checks']

def fetch_grafana_metrics(job_label):
    # Fetching average success rate over the last 5 minutes
    params = {
        'query': f'avg_over_time(probe_success{{job="{job_label}"}}[1m])'
    }
    auth = ("1229478", GRAFANA_API_KEY)
    response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
    data = response.json()
    reachability = float(data['data']['result'][0]['value'][1]) * 100  # converted to percentage

    # Fetching average latency over the last 5 minutes
    params = {
        'query': f'avg_over_time(probe_duration_seconds{{job="{job_label}"}}[1m]) * 1000'  # converted to milliseconds
    }
    response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
    data = response.json()
    latency = float(data['data']['result'][0]['value'][1])
    
    return reachability, latency

def determine_component_status(reachability, latency):
    # Determine component status based on Uptime/Reachability
    if reachability >= 95:
        status = "operational"
    elif 75 <= reachability < 95:
        status = "degraded_performance"
    else:
        status = "major_outage"
    
    # Determine component status based on Request Latency
    if latency <= 200:
        latency_status = "operational"
    elif 200 < latency <= 1000:
        latency_status = "degraded_performance"
    else:
        latency_status = "major_outage"
    
    # Taking the worst of the two statuses
    if "major_outage" in [status, latency_status]:
        return "major_outage"
    elif "degraded_performance" in [status, latency_status]:
        return "degraded_performance"
    else:
        return "operational"

# Main logic
for check in checks:
    reachability, latency = fetch_grafana_metrics(check["job_label"])
    component_status = determine_component_status(reachability, latency)

    # Update component status
    component_payload = {
        'component': {
            'status': component_status
        }
    }
    response = requests.patch(
        f"{api_base}/v1/pages/{page_id}/components/{check['statuspage_component_id']}",
        headers={"Content-Type": "application/json", "Authorization": "OAuth " + api_key},
        json=component_payload
    )
    if response.status_code >= 400:
        print(f"Error encountered for {check['name']} component. Ensure your keys are correct. Response: {response.text}")
    else:
        print(f"Updated component status for {check['name']}")

    # Submit latency metric data
    ts = int(time.time())
    metric_payload = {
        'data': {
            'timestamp': ts,
            'value': latency
        }
    }
    response = requests.post(
        f"{api_base}/v1/pages/{page_id}/metrics/{check['statuspage_metric_id']}/data.json",
        headers={"Content-Type": "application/json", "Authorization": "OAuth " + api_key},
        json=metric_payload
    )
    if response.status_code >= 400:
        print(f"Error encountered for {check['name']} metric. Ensure your keys are correct. Response: {response.text}")
    else:
        print(f"Submitted data for {check['name']} metric")

    time.sleep(1)
