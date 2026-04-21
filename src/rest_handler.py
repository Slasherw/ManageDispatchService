import json
import boto3
import os
import decimal
import uuid
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'ManageDispatchTable'))

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

            if not new_status or new_status not in ['ACCEPTED', 'DECLINED', 'DISPATCHED']:
                return create_response(400, {"error": "Invalid status value"}, trace_id)

            now_time = datetime.now(timezone.utc).isoformat()

            table.update_item(
                Key={'dispatchId': dispatch_id},
                UpdateExpression="set #s = :s, updatedAt = :t, statusNote = :n, teamId = :ti",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': new_status,
                    ':t': now_time,
                    ':n': body.get('note', '-'),
                    ':ti': body.get('teamId', 'UNASSIGNED')
                },
                ConditionExpression="attribute_exists(dispatchId)"
            )
            
            return create_response(200, {
                "message": "Status updated successfully",
                "dispatchId": dispatch_id,
                "status": new_status
            }, trace_id)

        # --- กรณีไม่พบ Path ที่ต้องการ ---
        return create_response(404, {"error": "Endpoint not found"}, trace_id)

    except Exception as e:
        # 🔴 4. Structured Error Logging: พ่น Error พร้อม Trace ID ลง CloudWatch
        print(f"🔥 [ERROR] TraceID: {trace_id} | Message: {str(e)}")
        
        return create_response(500, {
            "error": "Internal Server Error",
            "message": "ระบบขัดข้องชั่วคราว กรุณาแจ้ง Trace ID ให้ผู้ดูแลระบบ"
        }, trace_id)