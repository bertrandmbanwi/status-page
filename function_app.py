import logging
import azure.functions as func
import os
import requests
import time
import json

# Retrieve environment variables
api_key = os.getenv('STATUS_PAGE_2_API_KEY')
GRAFANA_API_KEY = os.getenv('GRAFANA_API_KEY')

# Statuspage configuration
page_id = 'pwpz1wk1fs7z'
api_base = 'https://api.statuspage.io'

# Grafana configuration
PROMETHEUS_URL = 'https://prometheus-prod-13-prod-us-east-0.grafana.net/api/prom/api/v1/query'

app = func.FunctionApp()

@app.schedule(schedule="0 */2 * * * *", arg_name="myTimer", run_on_startup=True,
              use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function executed.')

# Load checks from configuration file
with open('checks_config.json', 'r') as f:
    checks = json.load(f)['checks']

def fetch_grafana_metrics(job_label):
    reachability = None
    latency = None
    try:
        # Fetching average success rate over the last 5 minutes
        params = {
            'query': f'avg_over_time(probe_success{{job="{job_label}"}}[1m])'
        }
        auth = ("1269157", GRAFANA_API_KEY)
        response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
        response.raise_for_status()  # This will raise an exception for HTTP errors.
        data = response.json()
        
        # Check if the expected keys are in the response
        if 'data' not in data or 'result' not in data['data'] or not data['data']['result']:
            raise ValueError(f"No data available for job_label: {job_label}")
        
        reachability = float(data['data']['result'][0]['value'][1]) * 100  # converted to percentage

        # Fetching average latency over the last 5 minutes
        params = {
            'query': f'avg_over_time(probe_duration_seconds{{job="{job_label}"}}[1m]) * 1000'  # converted to milliseconds
        }
        response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
        response.raise_for_status()
        data = response.json()
        
        if 'data' not in data or 'result' not in data['data'] or not data['data']['result']:
            raise ValueError(f"No data available for job_label: {job_label}")
        
        latency = float(data['data']['result'][0]['value'][1])

    except requests.RequestException as e:
        print(f"Request to Grafana API failed: {e}")
    except KeyError as e:
        print(f"Key error in the Grafana API response: {e}. Response was: {data}")
    except ValueError as e:
        print(f"Value error: {e}")

    return reachability, latency

def determine_component_status(reachability, latency):
        if reachability >= 95:
            status = "operational"
        elif 75 <= reachability < 95:
            status = "degraded_performance"
        else:
            status = "major_outage"

        if latency <= 200:
            latency_status = "operational"
        elif 200 < latency < 1000:
            latency_status = "degraded_performance"
        else:
            latency_status = "major_outage"

        if "major_outage" in [status, latency_status]:
            return "major_outage"
        elif "degraded_performance" in [status, latency_status]:
            return "degraded_performance"
        else:
            return "operational"

for check in checks:
        reachability, latency = fetch_grafana_metrics(check["job_label"])
        if reachability is None or latency is None:
            print(f"Metrics fetch failed for job label: {check['job_label']}")
            continue  # Skip updating this check if the fetch failed
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
                logging.error(f"Error encountered for {check['name']} component. Ensure your keys are correct. Response: {response.text}")
        else:
                logging.info(f"Updated component status for {check['name']}")

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
                logging.error(f"Error encountered for {check['name']} metric. Ensure your keys are correct. Response: {response.text}")
        else:
                logging.info(f"Submitted data for {check['name']} metric")

        time.sleep(1)
