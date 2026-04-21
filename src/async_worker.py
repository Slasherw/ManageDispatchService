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
        # ถ้าไม่มีก้อน body ให้เป็น dict ว่างไว้ก่อนกันพัง
        data_body = payload.get('body', {})
        
        # 3. ดึง requestId ออกมาจาก data_body
        request_id = data_body.get('requestId')
        
        # 🔴 จุดตรวจสอบสำคัญ: ถ้าหา requestId ไม่เจอ ห้ามบันทึกลง DB
        if not request_id:
            print("❌ ไม่พบ requestId ในข้อมูลที่ได้รับ ข้ามการบันทึก...")
            continue

        # 4. เตรียมข้อมูล (ต้องมั่นใจว่า dispatchId ไม่เป็น None)
        item = {
            'dispatchId': request_id,         # 👈 ตัวนี้ห้ามเป็น NULL เด็ดขาด
            'requestId': request_id,
            'status': 'WAITING',
            'teamId': 'UNASSIGNED',
            'type': data_body.get('requestType', 'GENERAL'),
            'priorityLevel': data_body.get('priorityLevel', 'NORMAL'),
            'location': parse_location(data_body), # ใช้ฟังก์ชันช่วยเพื่อให้โค้ดสะอาด
            'description': data_body.get('description', '-'),
            'evaluateReason': data_body.get('evaluateReason', '-'), # 👈 ต้องมีตัวนี้
            'peopleCount': data_body.get('peopleCount', 1),        # 👈 ต้องมีตัวนี้
            'specialNeeds': data_body.get('specialNeeds', '-'),
            'createdAt': data_body.get('lastEvaluatedAt') or datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }

        try:
            table.put_item(Item=item)
            print(f"✅ บันทึกสำเร็จ: {request_id}")
        except Exception as e:
            print(f"❌ DynamoDB Error: {str(e)}")
            
    return {"status": "success"}

# ฟังก์ชันช่วยประกอบร่างที่อยู่ (ย้ายออกมาข้างนอกจะได้ไม่งง)
def parse_location(data_body):
    loc = data_body.get('location', {})
    if isinstance(loc, dict):
        address = loc.get('addressLine', '')
        district = loc.get('district', '')
        province = loc.get('province', '')
        return f"{address} {district} {province}".strip() or "ไม่ระบุสถานที่"
    return str(loc) if loc else "ไม่ระบุสถานที่"