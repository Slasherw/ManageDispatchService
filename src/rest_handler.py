import json
import boto3
import os
import decimal
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'ManageDispatchTable'))

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_dashboard_html():
    try:
        # หาตำแหน่งไฟล์ index.html ที่อยู่ในโฟลเดอร์เดียวกัน
        file_path = os.path.join(os.path.dirname(__file__), 'index.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"<html><body><h1>Error loading dashboard</h1><p>{str(e)}</p></body></html>"

def lambda_handler(event, context):
    method = event.get('httpMethod')
    path = event.get('path')
    
    # 1. หน้า Dashboard (Root Path)
    if method == 'GET' and (path == '/' or path == ''):
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html",  # สำคัญมาก: ต้องบอกเบราว์เซอร์ว่าเป็น HTML
                "Access-Control-Allow-Origin": "*" # สำหรับ CORS
            },
            "body": get_dashboard_html()
        }
    
    # API Contract #2: Get Dispatches by Team [cite: 88-95]
    if method == 'GET' and path == '/v1/dispatches':
        query_params = event.get('queryStringParameters') or {}
        team_id = query_params.get('teamId')
        status_filter = query_params.get('status')
        
        try:
            # กรณีที่ 1: ค้นหาตามสถานะ (สำหรับหน้า Dashboard 3 Tab)
            if status_filter:
                response = table.query(
                    IndexName='StatusIndex',
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('status').eq(status_filter.upper())
                )
                items = response.get('Items', [])
            
            # กรณีที่ 2: ค้นหาตาม Team ID (สำหรับฝั่งทีมกู้ภัยดูงานตัวเอง)
            elif team_id:
                response = table.query(
                    IndexName='TeamIdIndex',
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('teamId').eq(team_id)
                )
                items = response.get('Items', [])
            
            # กรณีที่ 3: ถ้าไม่ส่งอะไรมาเลย ให้ดึงทั้งหมด (Scan) - ระวังเรื่อง performance ถ้าข้อมูลเยอะ
            else:
                response = table.scan()
                items = response.get('Items', [])
                
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*" # สำคัญมากเพื่อให้หน้าเว็บดึงข้อมูลได้
                },
                "body": json.dumps({"items": items}, cls=DecimalEncoder)
            }
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    # API Contract #3: Update Mission Acceptance Status [cite: 128-135]
    elif method == 'PATCH' and '/status' in path:
        dispatch_id = event['pathParameters']['id']
        body = json.loads(event.get('body', '{}'))
        new_status = body.get('status')
        
        if new_status not in ['ACCEPT', 'DECLINE']:
            return {"statusCode": 400, "body": json.dumps({"error": {"code": "VALIDATION_ERROR", "message": "invalid status value"}}, cls=DecimalEncoder)}
            
        now_time = datetime.now(datetime.time.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        try:
            table.update_item(
                Key={'dispatchId': dispatch_id},
                UpdateExpression="set #s = :s, updatedAt = :t, statusNote = :n",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': new_status,
                    ':t': now_time,
                    ':n': body.get('note', '')
                },
                ConditionExpression="attribute_exists(dispatchId)" # ต้องมีงานนี้อยู่จริง
            )
            return {
                "statusCode": 200,
                "body": json.dumps({"dispatchId": dispatch_id, "status": new_status, "updatedAt": now_time}, cls=DecimalEncoder)
            }
        except Exception as e:
            return {"statusCode": 409, "body": json.dumps({"error": {"code": "CONFLICT_ERROR", "message": "Dispatch order not found or issue updating"}}, cls=DecimalEncoder)}

    return {"statusCode": 404, "body": "Not Found"}