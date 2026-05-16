import json
import boto3
import os
import uuid
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

TABLE_NAME = os.environ.get('TABLE_NAME', 'ManageDispatchTable')
TOPIC_ARN = os.environ.get('TOPIC_ARN', '')

table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    for record in event['Records']:
        # 1. แกะห่อ SQS ออกมา (เป็น JSON string)
        payload = json.loads(record['body'])
        
        # 2. เจาะเข้าไปในก้อน "body" ตาม Doc ของเพื่อน
        data_body = payload.get('body', {})
        
        # 3. ดึง requestId ออกมาจาก data_body
        request_id = data_body.get('requestId')
        
        if not request_id:
            print("❌ ไม่พบ requestId ในข้อมูลที่ได้รับ ข้ามการบันทึก...")
            continue

        # 4. เตรียมข้อมูลสำหรับการอัปเดต (Surgical Update)
        now_time = datetime.now(timezone.utc).isoformat()

        update_expression = (
            "SET requestId = :rid, #s = if_not_exists(#s, :s), teamId = if_not_exists(teamId, :ti), "
            "#t = :t, priorityLevel = :p, #loc = :l, #d = :d, evaluateReason = :er, "
            "peopleCount = :pc, specialNeeds = :sn, createdAt = if_not_exists(createdAt, :cat), updatedAt = :uat"
        )

        try:
            table.update_item(
                Key={'dispatchId': request_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames={
                    '#s': 'status',
                    '#t': 'type',
                    '#loc': 'location',
                    '#d': 'description'
                },
                ExpressionAttributeValues={
                    ':rid': request_id,
                    ':s': 'WAITING',
                    ':ti': 'UNASSIGNED',
                    ':t': data_body.get('requestType', 'GENERAL'),
                    ':p': data_body.get('priorityLevel', 'NORMAL'),
                    ':l': parse_location(data_body),
                    ':d': data_body.get('description', '-'),
                    ':er': data_body.get('evaluateReason', '-'),
                    ':pc': data_body.get('peopleCount', 1),
                    ':sn': data_body.get('specialNeeds', '-'),
                    ':cat': data_body.get('lastEvaluatedAt') or now_time,
                    ':uat': now_time
                }
            )
            print(f"✅ บันทึก/อัปเดตสำเร็จ: {request_id}")
        except Exception as e:
            print(f"❌ DynamoDB Error: {str(e)}")
            
    return {"status": "success"}

def parse_location(data_body):
    loc = data_body.get('location', {})
    if isinstance(loc, dict):
        address = loc.get('addressLine', '')
        district = loc.get('district', '')
        province = loc.get('province', '')
        return f"{address} {district} {province}".strip() or "ไม่ระบุสถานที่"
    return str(loc) if loc else "ไม่ระบุสถานที่"