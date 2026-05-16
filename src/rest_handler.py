import json
import boto3
import os
import decimal
import uuid
import requests
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'ManageDispatchTable'))

sns = boto3.client('sns')
DISPATCH_TOPIC_ARN = os.environ.get('DISPATCH_TOPIC_ARN')
TEAM_SERVICE_URL = os.environ.get('TEAM_SERVICE_URL')

# 🟢 1. DecimalEncoder: ตัวแปลงพิเศษสำหรับข้อมูลตัวเลขจาก DynamoDB
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)
    
# 🟢 2. Helper Function: สำหรับสร้าง Response ที่มีมาตรฐานเดียวกัน (CORS + Trace ID)
def create_response(status_code, body_data, trace_id):
    # รวมข้อมูลหลักเข้ากับ Trace ID เพื่อส่งกลับไปให้ Frontend
    response_body = {
        **body_data,
        "traceId": trace_id,
        "serverTime": datetime.now(timezone.utc).isoformat()
    }
    
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,PATCH,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Trace-Id",
            "X-Trace-Id": trace_id
        },
        "body": json.dumps(response_body, cls=DecimalEncoder)
    }

def get_team_details(team_id, trace_id):
    if not TEAM_SERVICE_URL or not team_id or team_id == 'UNASSIGNED':
        return None
    
    # หมายเหตุ: อิงตาม URL ที่เพื่อนให้มา ถ้าดึงรายตัวอาจจะเป็น /v1/teams/{id}
    # แต่ถ้าเพื่อนยังไม่มีเส้นรายตัว เราสามารถดึงทั้งหมดแล้วมากรองเองได้ 
    # ในที่นี้จะลองเรียกแบบรายตัวตามมาตรฐาน
    url = f"{TEAM_SERVICE_URL}/{team_id}"
    
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
            "Authorization": "Bearer mock-dispatcher-token-123"
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ Team Details not found ({team_id}): {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to fetch Team Details: {str(e)}")
    return None

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
        # Synchronous call as per architecture principles
        response = requests.patch(url, json=payload, headers=headers, timeout=5)
        print(f"📡 Team Service Status Update ({team_id}): {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to update Team Service status: {str(e)}")

def get_dashboard_html():
    try:
        # หาตำแหน่งไฟล์ index.html ที่อยู่ในโฟลเดอร์เดียวกัน
        file_path = os.path.join(os.path.dirname(__file__), 'index.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"<html><body><h1>Error loading dashboard</h1><p>{str(e)}</p></body></html>"

def lambda_handler(event, context):
    # 🔍 3. Trace ID Management: ดึงจาก Header หรือสร้างใหม่
    headers = event.get('headers', {})
    trace_id = headers.get('X-Trace-Id') or headers.get('X-Amzn-Trace-Id') or str(uuid.uuid4())
    
    method = event.get('httpMethod')
    path = event.get('path', '')

    try:
        # 🟢 1. ดึงหน้า Dashboard
        if method == 'GET' and (path == '/' or path == ''):
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/html",  # สำคัญ: บอกเบราว์เซอร์ว่านี่คือหน้าเว็บ
                    "Access-Control-Allow-Origin": "*",
                    "X-Trace-Id": trace_id
                },
                "body": get_dashboard_html()
            }
        
        # --- API Contract: Get Dispatches ---
        elif method == 'GET' and '/v1/dispatches' in path:
            query_params = event.get('queryStringParameters') or {}
            status_filter = query_params.get('status')
            team_id = query_params.get('teamId')

            if status_filter:
                response = table.query(
                    IndexName='StatusIndex',
                    KeyConditionExpression=Key('status').eq(status_filter.upper())
                )
            elif team_id:
                response = table.query(
                    IndexName='TeamIdIndex',
                    KeyConditionExpression=Key('teamId').eq(team_id)
                )
            else:
                response = table.scan(Limit=50) # ป้องกันการดึงข้อมูลเยอะเกินไป (Scan Limit)

            return create_response(200, {"items": response.get('Items', [])}, trace_id)

        # --- API Contract: Update Status (PATCH) ---
        elif method == 'PATCH' and '/status' in path:
            # ดึง ID จาก Path Parameters (ตรวจสอบโครงสร้าง event ของ API Gateway)
            dispatch_id = event.get('pathParameters', {}).get('id')
            body = json.loads(event.get('body', '{}'))
            new_status = body.get('status')
            target_team_id = body.get('teamId')

            allowed_statuses = ['ACCEPTED', 'DECLINED', 'DISPATCHED', 'RESOLVED']
            if not new_status or new_status not in allowed_statuses:
                return create_response(400, {"error": f"Invalid status value. Allowed: {allowed_statuses}"}, trace_id)

            now_time = datetime.now(timezone.utc).isoformat()

            # 1. Update DynamoDB
            update_expr = "set #s = :s, updatedAt = :t, statusNote = :n"
            expr_vals = {
                ':s': new_status,
                ':t': now_time,
                ':n': body.get('note', '-')
            }
            
            # ถ้าเป็นการ DISPATCH ให้ดึงข้อมูลทีมมาเก็บด้วย
            team_details = None
            if new_status == 'DISPATCHED' and target_team_id:
                team_details = get_team_details(target_team_id, trace_id)

            if target_team_id:
                update_expr += ", teamId = :ti"
                expr_vals[':ti'] = target_team_id
                if team_details:
                    update_expr += ", teamDetails = :td"
                    expr_vals[':td'] = team_details

            table.update_item(
                Key={'dispatchId': dispatch_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues=expr_vals,
                ConditionExpression="attribute_exists(dispatchId)"
            )
            
            # 2. ดึงข้อมูลล่าสุดมาเพื่อเตรียมส่ง
            db_item = table.get_item(Key={'dispatchId': dispatch_id}).get('Item', {})
            current_team_id = db_item.get('teamId')
            
            # 3. Handle External Sync Calls (Team Service)
            if new_status == 'DISPATCHED':
                update_team_status(current_team_id, 'BUSY', dispatch_id, trace_id)
            elif new_status == 'RESOLVED':
                update_team_status(current_team_id, 'AVAILABLE', dispatch_id, trace_id)

            # 4. Handle Async Events (SNS)
            if new_status == 'DISPATCHED':
                event_payload = {
                    "header": {
                        "messageType": "RescueMissionDispatchedEvent",
                        "traceId": trace_id
                    },
                    "body": {
                        "dispatchId": db_item.get('dispatchId'),
                        "status": db_item.get('status'),
                        "teamId": db_item.get('teamId'),
                        "location": db_item.get('location'),
                        "type": db_item.get('type'),
                        "description": db_item.get('description'),
                        "caller": db_item.get('caller'),
                        "peopleCount": db_item.get('peopleCount'),
                        "specialNeeds": db_item.get('specialNeeds'),
                        "priority": db_item.get('priority'),
                        "evaluateReason": db_item.get('evaluateReason'),
                        "recommendedTeams": db_item.get('recommendedTeams'),
                        "updatedAt": db_item.get('updatedAt'),
                        "timestamp": now_time
                    }
                }

                sns_response = sns.publish(
                    TopicArn=DISPATCH_TOPIC_ARN,
                    Message=json.dumps(event_payload, cls=DecimalEncoder),
                    MessageAttributes={
                        'messageType': {'DataType': 'String', 'StringValue': 'RescueMissionDispatchedEvent'}
                    }
                )
                print(f"📡 SNS Published: {sns_response['MessageId']}")
    
            return create_response(200, {
                "message": "Status updated successfully",
                "dispatchId": dispatch_id,
                "status": new_status,
                "teamId": current_team_id
            }, trace_id)

        # --- กรณีไม่พบ Path ที่ต้องการ ---
        return create_response(404, {"error": "Endpoint not found"}, trace_id)

    except Exception as e:
        # 🔴 4. Structured Error Logging
        print(f"🔥 [ERROR] TraceID: {trace_id} | Message: {str(e)}")
        
        return create_response(500, {
            "error": "Internal Server Error",
            "message": "ระบบขัดข้องชั่วคราว กรุณาแจ้ง Trace ID ให้ผู้ดูแลระบบ"
        }, trace_id)