import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'ManageDispatchTable'))

def lambda_handler(event, context):
    method = event.get('httpMethod')
    path = event.get('resource')
    
    # API Contract #2: Get Dispatches by Team [cite: 88-95]
    if method == 'GET' and path == '/v1/dispatches':
        query_params = event.get('queryStringParameters') or {}
        team_id = query_params.get('teamId')
        
        if not team_id:
            return {"statusCode": 400, "body": json.dumps({"error": {"code": "VALIDATION_ERROR", "message": "teamId required"}})}
            
        try:
            response = table.query(
                IndexName='TeamIdIndex',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('teamId').eq(team_id)
            )
            return {
                "statusCode": 200,
                "body": json.dumps({"teamId": team_id, "items": response.get('Items', [])})
            }
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    # API Contract #3: Update Mission Acceptance Status [cite: 128-135]
    elif method == 'PATCH' and '/status' in path:
        dispatch_id = event['pathParameters']['id']
        body = json.loads(event.get('body', '{}'))
        new_status = body.get('status')
        
        if new_status not in ['ACCEPT', 'DECLINE']:
            return {"statusCode": 400, "body": json.dumps({"error": {"code": "VALIDATION_ERROR", "message": "invalid status value"}})}
            
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
                "body": json.dumps({"dispatchId": dispatch_id, "status": new_status, "updatedAt": now_time})
            }
        except Exception as e:
            return {"statusCode": 409, "body": json.dumps({"error": {"code": "CONFLICT_ERROR", "message": "Dispatch order not found or issue updating"}})}

    return {"statusCode": 404, "body": "Not Found"}