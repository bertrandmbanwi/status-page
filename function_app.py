import logging
import azure.functions as func
import os
import requests
import time
import json

app = func.FunctionApp()

@app.schedule(schedule="0 */2 * * * *", arg_name="myTimer", run_on_startup=True, use_monitor=False) 
def status_page_timer(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function executed.')

    # Retrieve environment variables
    api_key = os.environ['STATUS_PAGE_2_API_KEY']
    GRAFANA_API_KEY = os.environ['GRAFANA_API_KEY']

    # Statuspage configuration
    page_id = 'pwpz1wk1fs7z'
    api_base = 'https://api.statuspage.io'

    # Grafana configuration
    PROMETHEUS_URL = 'https://prometheus-prod-13-prod-us-east-0.grafana.net/api/prom/api/v1/query'

    # Load checks configuration from checks_config.json file
    try:
        with open('checks_config.json', 'r') as config_file:
            checks_config = json.load(config_file)
            checks = checks_config['checks']
    except FileNotFoundError:
        logging.error('The checks_config.json file was not found.')
        return
    except json.JSONDecodeError:
        logging.error('The checks_config.json file could not be parsed.')
        return

    def fetch_grafana_metrics(job_label):
        params = {
            'query': f'avg_over_time(probe_success{{job="{job_label}"}}[1m])'
        }
        auth = ("1229478", GRAFANA_API_KEY)
        response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
        data = response.json()
        reachability = float(data['data']['result'][0]['value'][1]) * 100  # converted to percentage

        params = {
            'query': f'avg_over_time(probe_duration_seconds{{job="{job_label}"}}[1m]) * 1000'  # converted to milliseconds
        }
        response = requests.get(PROMETHEUS_URL, params=params, auth=auth)
        data = response.json()
        latency = float(data['data']['result'][0]['value'][1])

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
