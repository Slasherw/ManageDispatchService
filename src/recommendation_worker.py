import json
import boto3
import os
import decimal
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME', 'ManageDispatchTable')
table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    for record in event['Records']:
        # 1. แกะ Trace ID และ Payload (Microservices Standard)
        message_id = record.get('messageId', 'unknown-msg-id')
        try:
            payload = json.loads(record['body'], parse_float=decimal.Decimal)
            
            # รองรับกรณีจำลองยิงตรงเข้า SQS (ไม่มี SNS คลุม) และกรณีที่มาจาก SNS จริง
            if 'Message' in payload: 
                payload = json.loads(payload['Message'], parse_float=decimal.Decimal)

            trace_id = payload.get('trace_id', f'SQS-{message_id}')
            request_id = payload.get('request_id')
            rec_status = payload.get('recommendation_status')
            ranked_teams = payload.get('ranked_teams', [])

            print(f"📦 [INFO] TraceID: {trace_id} | Processing Recommendation for Request: {request_id}")

            # 2. Validation Rules ตาม Contract
            if rec_status != "GENERATED":
                print(f"⚠️ [SKIP] TraceID: {trace_id} | Status is not GENERATED")
                continue
            if not request_id:
                print(f"⚠️ [SKIP] TraceID: {trace_id} | Missing request_id")
                continue
            if len(ranked_teams) < 1:
                print(f"⚠️ [SKIP] TraceID: {trace_id} | No ranked teams provided")
                continue

            # 3. เตรียมข้อมูลที่จะอัปเดต (ดึงเฉพาะที่ Dashboard ต้องใช้)
            recommendation_data = {
                "recommendationId": payload.get('recommendation_id'),
                "confidenceScore": payload.get('confidence_score'),
                "rankedTeams": ranked_teams, # เก็บลิสต์ทีมทั้งหมดพร้อม explanation
                "evaluatedAt": payload.get('evaluated_at')
            }
            now_time = datetime.now(timezone.utc).isoformat()

            # 4. อัปเดตข้อมูลลงตาราง (อัปเดตเฉพาะ Row ที่ dispatchId ตรงกับ request_id)
            try:
                table.update_item(
                    Key={'dispatchId': request_id},
                    UpdateExpression="SET recommendedTeams = :rt, confidenceScore = :cs, updatedAt = :t",
                    ExpressionAttributeValues={
                        ':rt': ranked_teams,
                        ':cs': payload.get('confidence_score', 0),
                        ':t': now_time
                    },
                    ConditionExpression="attribute_exists(dispatchId)" # 🛡️ อัปเดตเฉพาะเคสที่มีอยู่จริง
                )
                print(f"✅ [SUCCESS] TraceID: {trace_id} | Updated Recommendation for {request_id}")
            except Exception as db_err:
                print(f"🔥 [ERROR] TraceID: {trace_id} | DynamoDB Update Failed: {str(db_err)}")

        except Exception as e:
            print(f"🔥 [FATAL] Message ID: {message_id} | Could not parse message: {str(e)}")
            
    return {"status": "success"}