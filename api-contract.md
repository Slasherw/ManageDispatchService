# Manage Dispatch Service API Contract

This document provides the technical specification for the REST APIs exposed by the **Manage Dispatch Service**. These endpoints are primarily used by the **MissionProgress Service** and the internal Dashboard.

## 🌐 Base URL
`https://qj7ip5zv5a.execute-api.us-east-1.amazonaws.com/Prod`

## 🔑 Authentication & Headers
All requests must include the following headers for traceability and identification.

| Header | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `Content-Type` | `string` | Yes | Must be `application/json` |
| `X-Trace-Id` | `string` | No | Unique ID for request tracing. If not provided, the service will generate one. |
| `Authorization` | `string` | No | Bearer token (currently supports mock-validation: `Bearer mock-dispatcher-token-123`) |

---

## 📡 Endpoints

### 1. Retrieve Dispatches
Used to fetch a list of dispatch records. Can be filtered by status or assigned team.

*   **URL:** `/v1/dispatches`
*   **Method:** `GET`
*   **Query Parameters:**
    *   `status` (optional): Filter by dispatch status (e.g., `WAITING`, `DISPATCHED`, `RESOLVED`).
    *   `teamId` (optional): Filter by assigned Team ID. Used by MissionProgress Service to find active missions for a team.

*   **Success Response (200 OK):**
    ```json
    {
      "items": [
        {
          "dispatchId": "uuid-string",
          "requestId": "uuid-string",
          "status": "DISPATCHED",
          "priorityLevel": "HIGH",
          "dispatchedAt": "2024-05-18T10:00:00Z",
          "location": "123 Main St, BKK",
          "teamId": "TEAM-01"
        }
      ],
      "traceId": "trace-id-string",
      "serverTime": "2024-05-18T10:05:00Z"
    }
    ```

---

### 2. Update Dispatch Status
Used to transition a dispatch through its lifecycle. Called by the Dashboard (to Dispatch) or MissionProgress Service (to Resolve).

*   **URL:** `/v1/dispatches/{id}/status`
*   **Method:** `PATCH`
*   **Path Parameters:**
    *   `id`: The `dispatchId` to update.

*   **Request Body:**
    ```json
    {
      "status": "RESOLVED",
      "teamId": "TEAM-01",
      "note": "Mission completed successfully"
    }
    ```

*   **Field Definitions:**

| Field | Type | Required | Possible Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `status` | `string` | Yes | `DISPATCHED`, `RESOLVED`, `CANCELLED`, `ACCEPTED`, `DECLINED` | The target status of the dispatch. |
| `teamId` | `string` | No | String (e.g., `TEAM-A`) | Required when status is `DISPATCHED`. |
| `note` | `string` | No | String | Operational note or reason for the status change. |

*   **Success Response (200 OK):**
    ```json
    {
      "message": "Status updated successfully",
      "dispatchId": "uuid-string",
      "status": "RESOLVED",
      "teamId": "TEAM-01",
      "traceId": "trace-id-string",
      "serverTime": "2024-05-18T10:10:00Z"
    }
    ```

---

## ❌ Error Handling

The service uses standard HTTP status codes and a consistent error response body.

| Status Code | Meaning | Description |
| :--- | :--- | :--- |
| `400` | Bad Request | Missing required fields or invalid `status` value. |
| `404` | Not Found | The specified `dispatchId` does not exist. |
| `500` | Server Error | Internal system failure. Check `traceId` in logs. |

### **Error Response Body:**
```json
{
  "error": "Error Title",
  "message": "Detailed explanation of the error",
  "traceId": "trace-id-string",
  "serverTime": "2024-05-18T10:15:00Z"
}
```

---

## 🔄 Status Definitions

| Status | Description |
| :--- | :--- |
| `WAITING` | Initial state. Request received and triaged, awaiting team assignment. |
| `DISPATCHED` | Team has been selected and dispatched to the location. |
| `RESOLVED` | Mission completed. Team is released and request is closed. |
| `CANCELLED` | Dispatch aborted by the dispatcher. |
| `ACCEPTED` | (Simulated) Team confirmed they are on the way. |
| `DECLINED` | (Simulated) Team rejected the dispatch (requires re-dispatch). |

---

## 📡 Async API (Outbound Events)

The Manage Dispatch Service publishes events to Amazon SNS when specific actions occur. Consumers (like the **MissionProgress Service**) should subscribe to the following topic.

### Topic: `rescue.mission.dispatch.v1`
*   **Topic ARN:** `arn:aws:sns:us-east-1:460581038623:request-dispatch-v1`
*   **Event Name:** `DispatchOrderCreated`
*   **Trigger:** When a dispatcher successfully assigns a team to a request.
*   **SNS Message Attributes:**
    *   `messageType`: `DispatchOrderCreated`

*   **Payload Structure:**
    ```json
    {
      "header": {
        "messageType": "DispatchOrderCreated",
        "traceId": "trace-id-string"
      },
      "body": {
        "dispatchId": "uuid-string",
        "status": "DISPATCHED",
        "requestId": "uuid-string",
        "teamId": "TEAM-01",
        "requestType": "FIRE",
        "priorityLevel": "HIGH",
        "evaluateReason": "Detected smoke via IoT",
        "location": "123 Main St, BKK",
        "description": "Fire reported at warehouse",
        "peopleCount": 2,
        "specialNeeds": "Oxygen required",
        "lastEvaluatedAt": "2024-05-18T09:50:00Z",
        "dispatchedAt": "2024-05-18T10:00:00Z",
        "timestamp": "2024-05-18T10:00:00Z"
      }
    }
    ```

*   **Field Definitions (Body):**

| Field | Type | Description |
| :--- | :--- | :--- |
| `dispatchId` | `string` | Unique identifier for this dispatch mission. |
| `status` | `string` | Current status (always `DISPATCHED` for this event). |
| `requestId` | `string` | Reference to the original emergency request. |
| `teamId` | `string` | The ID of the team assigned to this mission. |
| `location` | `string` | Human-readable address of the incident. |
| `dispatchedAt` | `iso-8601` | Timestamp when the dispatch was confirmed. |
