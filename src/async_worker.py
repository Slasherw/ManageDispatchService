import json
import boto3
import os
import uuid
import requests
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

TABLE_NAME = os.environ.get('TABLE_NAME', 'ManageDispatchTable')
TOPIC_ARN = os.environ.get('TOPIC_ARN', '')
MOCK_MODE = os.environ.get('MOCK_MODE', 'True') == 'True'

table = dynamodb.Table(TABLE_NAME)

def verify_team_available(team_id):
    if MOCK_MODE:
        return True # จำลองว่าทีมว่างเสมอ
    try:
        url = f"{os.environ['TEAM_SERVICE_URL']}/{team_id}/status"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json().get('status') == 'AVAILABLE'
        return False
    except:
        return False

def verify_request_exists(request_id):
    if MOCK_MODE:
        return True # จำลองว่า Request มีจริงเสมอ
    try:
        url = f"{os.environ['REQUEST_SERVICE_URL']}/{request_id}"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def lambda_handler(event, context):
    for record in event['Records']:
        message_id = record['messageId']
        payload = json.loads(record['body'])
        
        request_id = payload.get('requestId')
        team_id = payload.get('teamId')
        
        status = "REJECTED"
        reason_code = ""
        reason_message = ""
        dispatch_id = f"DSP-{str(uuid.uuid4())[:8].upper()}"
        now_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        # 1. ตรวจสอบ Team Service 
        if not verify_team_available(team_id):
            reason_code = "TEAM_NOT_AVAILABLE"
            reason_message = "The requested rescue team is not available."
        
        # 2. ตรวจสอบ Request Service [cite: 323]
        elif not verify_request_exists(request_id):
            reason_code = "REQUEST_NOT_FOUND"
            reason_message = "The request ID does not exist."
        
        else:
            status = "PENDING"
            
        sns_message = {
            "requestId": request_id,
            "teamId": team_id,
            "status": status
        }

        # ถ้าผ่านการตรวจสอบ ให้บันทึกลง DB [cite: 207-213]
        if status == "PENDING":
            table.put_item(
                Item={
                    'dispatchId': dispatch_id,
                    'requestId': request_id,
                    'teamId': team_id,
                    'status': status,
                    'priorityLevel': payload.get('priorityLevel', 3),
                    'dispatchedAt': now_time,
                    'createdAt': now_time
                }
            )
            sns_message['dispatchId'] = dispatch_id
            sns_message['dispatchedAt'] = now_time
        else:
            sns_message['reasonCode'] = reason_code
            sns_message['reasonMessage'] = reason_message

        # ส่ง Event กลับไปที่ SNS [cite: 338-339]
        if TOPIC_ARN:
            sns.publish(
                TopicArn=TOPIC_ARN,
                Message=json.dumps(sns_message),
                MessageAttributes={
                    'messageType': {'DataType': 'String', 'StringValue': 'DispatchOrderCreated' if status == 'PENDING' else 'DispatchTeamRejected'},
                    'correlationId': {'DataType': 'String', 'StringValue': message_id}
                }
            )
            
    return {"status": "processed"}