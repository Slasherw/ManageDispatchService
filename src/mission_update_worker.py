import json
import boto3
import os
import requests
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME', 'ManageDispatchTable')
table = dynamodb.Table(TABLE_NAME)

TEAM_SERVICE_URL = os.environ.get('TEAM_SERVICE_URL')
REQUEST_SERVICE_URL = os.environ.get('REQUEST_SERVICE_URL')

def update_team_status(team_id, status, dispatch_id, trace_id):
    if not TEAM_SERVICE_URL or not team_id or team_id == 'UNASSIGNED':
        return
    
    url = f"{TEAM_SERVICE_URL}/{team_id}/status"
    payload = {
        "dispatchId": dispatch_id,
        "teamId": team_id,
        "dispatchedAt": datetime.now(timezone.utc).isoformat(),
        "team_status": status
    }
    
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
            "Authorization": "Bearer mock-dispatcher-token-123"
        }
        response = requests.patch(url, json=payload, headers=headers, timeout=5)
        print(f"📡 Team Service Status Update ({team_id} -> {status}): {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to update Team Service status: {str(e)}")

def update_request_status(request_id, action, trace_id):
    if not REQUEST_SERVICE_URL or not request_id:
        return
    
    url = f"{REQUEST_SERVICE_URL}/rescue-requests/{request_id}/{action}"
    
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id
        }
        response = requests.post(url, json={}, headers=headers, timeout=5)
        print(f"📡 Request Service Status Update ({request_id} -> {action}): {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to update Request Service status: {str(e)}")

def lambda_handler(event, context):
    for record in event['Records']:
        try:
            # 1. Parse EventBridge Message (wrapped in SQS)
            # Note: EventBridge target SQS puts the event JSON in the 'body'
            sqs_body = json.loads(record['body'])
            
            # ดึง detail จาก EventBridge event
            detail = sqs_body.get('detail', {})
            mission_id = detail.get('mission_id')
            incident_id = detail.get('incident_id')
            new_status = detail.get('new_status') # ควรเป็น RESOLVED
            
            trace_id = sqs_body.get('id') or f"EB-{mission_id}"
            
            if not mission_id or new_status != 'RESOLVED':
                print(f"⚠️ [SKIP] Invalid mission update: mission_id={mission_id}, status={new_status}")
                continue

            print(f"📦 [INFO] Processing Mission Resolution: {mission_id} (Incident: {incident_id})")

            # 2. Get current record to find team_id
            db_response = table.get_item(Key={'dispatchId': mission_id})
            item = db_response.get('Item')
            
            if not item:
                print(f"❌ Dispatch record not found: {mission_id}")
                continue

            current_team_id = item.get('teamId')
            request_id = incident_id or item.get('requestId') # ใช้ incident_id จาก event หรือจาก DB

            # 3. Update DynamoDB Status
            now_time = datetime.now(timezone.utc).isoformat()
            table.update_item(
                Key={'dispatchId': mission_id},
                UpdateExpression="set #s = :s, updatedAt = :t, statusNote = :n",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': 'RESOLVED',
                    ':t': now_time,
                    ':n': 'Resolved via Mission Progress Event'
                }
            )

            # 4. Release Team (AVAILABLE)
            if current_team_id and current_team_id != 'UNASSIGNED':
                update_team_status(current_team_id, 'AVAILABLE', mission_id, trace_id)

            # 5. Resolve Request Service
            if request_id:
                update_request_status(request_id, 'resolve', trace_id)

            print(f"✅ [SUCCESS] Mission {mission_id} resolved and team {current_team_id} released.")

        except Exception as e:
            print(f"🔥 Error processing mission update: {str(e)}")

    return {"status": "success"}
