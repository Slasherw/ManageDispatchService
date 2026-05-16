import json
import boto3
import os
import decimal
import requests
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME', 'ManageDispatchTable')
table = dynamodb.Table(TABLE_NAME)
TEAM_SERVICE_URL = os.environ.get('TEAM_SERVICE_URL')

def fetch_all_teams(trace_id):
    if not TEAM_SERVICE_URL:
        return {}
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
            "Authorization": "Bearer mock-dispatcher-token-123"
        }
        response = requests.get(TEAM_SERVICE_URL, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # รองรับทั้งแบบ { teams: [] } และ []
            raw_teams = data if isinstance(data, list) else (data.get('teams') or data.get('items') or [])
            # สร้าง Lookup Map: { team_id: team_full_details }
            return {t.get('team_id'): t for t in raw_teams if t.get('team_id')}
        print(f"⚠️ Team Service returned {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to fetch all teams: {str(e)}")
    return {}

def lambda_handler(event, context):
    for record in event['Records']:
        message_id = record.get('messageId', 'unknown-msg-id')
        try:
            raw_body = json.loads(record['body'])
            
            if isinstance(raw_body, dict) and 'Message' in raw_body:
                payload = json.loads(raw_body['Message'], parse_float=decimal.Decimal)
            else:
                payload = raw_body

            header = payload.get('header', {})
            body = payload.get('body', {})
            
            trace_id = header.get('trace_id') or payload.get('trace_id') or f'SQS-{message_id}'
            request_id = body.get('request_id') or body.get('requestId')
            
            if not request_id:
                print(f"⚠️ [SKIP] TraceID: {trace_id} | Missing request_id")
                continue

            # 🟢 ดึงข้อมูลทีมทั้งหมดมาเพื่อใช้ Enrich ข้อมูล AI
            all_teams_map = fetch_all_teams(trace_id)
            
            # 🟢 รวมร่างข้อมูล AI กับข้อมูลทีมแบบละเอียด
            ranked_teams = body.get('ranked_teams') or []
            enriched_ranked_teams = []
            for rt in ranked_teams:
                team_id = rt.get('team_id')
                full_info = all_teams_map.get(team_id, {})
                
                # รวมข้อมูล (AI Data + Team Details)
                enriched_team = {
                    **rt, # rank, total_score, explanation
                    **full_info # capabilities, specialties, equipment, etc.
                }
                enriched_ranked_teams.append(enriched_team)

            confidence_score = body.get('confidence_score') or 0
            request_type = body.get('request_type') or body.get('requestType', 'GENERAL')
            priority = body.get('priority_level') or body.get('priorityLevel', 'NORMAL')
            description = body.get('description', '-')
            evaluate_reason = body.get('evaluate_reason') or body.get('evaluateReason', '-')
            people_count = body.get('people_count') or body.get('peopleCount', 1)
            special_needs = body.get('special_needs') or body.get('specialNeeds', '-')
            
            location_raw = body.get('location', {})
            location_str = parse_location(location_raw)

            now_time = datetime.now(timezone.utc).isoformat()
            
            print(f"📦 [INFO] TraceID: {trace_id} | Processing New Request + Enriched AI: {request_id}")

            item = {
                'dispatchId': request_id,
                'requestId': request_id,
                'status': 'WAITING',
                'teamId': 'UNASSIGNED',
                'type': request_type,
                'priorityLevel': priority,
                'location': location_str,
                'description': description,
                'evaluateReason': evaluate_reason,
                'peopleCount': people_count,
                'specialNeeds': special_needs,
                'recommendedTeams': enriched_ranked_teams, # บันทึกแบบละเอียดลง DB
                'confidenceScore': confidence_score,
                'createdAt': header.get('sent_at') or now_time,
                'updatedAt': now_time,
                'traceId': trace_id
            }

            try:
                table.put_item(Item=item)
                print(f"✅ [SUCCESS] TraceID: {trace_id} | Created Enriched Dispatch Record: {request_id}")
            except Exception as db_err:
                print(f"🔥 [ERROR] TraceID: {trace_id} | DynamoDB Put Failed: {str(db_err)}")

        except Exception as e:
            print(f"🔥 [FATAL] Message ID: {message_id} | Error: {str(e)}")
            
    return {"status": "success"}

def parse_location(loc):
    if isinstance(loc, dict):
        address = loc.get('addressLine') or loc.get('address_line', '')
        district = loc.get('district', '')
        province = loc.get('province', '')
        return f"{address} {district} {province}".strip() or "ไม่ระบุสถานที่"
    return str(loc) if loc else "ไม่ระบุสถานที่"