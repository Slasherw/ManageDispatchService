Manage Dispatch Service (Disaster Response System)
📋 Overview
The Manage Dispatch Service is a critical component of a larger Disaster Response ecosystem. It serves as the primary bridge between help requests and rescue operations. By linking specific rescue teams to active incidents, it enables real-time monitoring of mission progress, ensuring that resources are deployed efficiently and no area is neglected during the chaos of a disaster.

⚠️ Problem Solved
During large-scale disasters, dispatchers often lose track of which units are deployed where. This leads to:

Duplicate Assignments: Multiple teams sent to the same location.

Neglected Areas: Urgent requests being overlooked.

Communication Gaps: No clear record of whether a team has accepted a mission or arrived at the scene.

✨ Key Features
Mission Acceptance Workflow: Manages the lifecycle of a dispatch from initial assignment (PENDING) to team response (ACCEPT/DECLINE) and finalization.

Real-time Operational Tracking: Records critical timestamps including dispatch time, arrival time, and post-mission notes.

Hybrid Communication Architecture:

Synchronous (REST): For immediate data retrieval and status updates.

Asynchronous (Event-Driven): Utilizes message queues to handle high-volume dispatch commands without blocking system performance.

Data Consistency: Enforces strict validation by cross-checking with the Team Service and Request Service before finalizing assignments.

🛠 Tech Stack (AWS Serverless)
Amazon API Gateway: RESTful entry point for synchronous interactions.

AWS Lambda: Serverless compute for processing business logic (REST Handlers & Async Workers).

Amazon DynamoDB: NoSQL database for high-performance storage of Dispatch Records and Mission States.

Amazon SQS: Command queue for reliable, asynchronous dispatch processing.

Amazon SNS: Event bus for broadcasting mission results to downstream services.

🚀 API Summary
POST /v1/dispatches: Create a new dispatch order (Asynchronous command support).

GET /v1/dispatches?teamId={id}: Retrieve active mission history for a specific team.

PATCH /v1/dispatches/{id}/status: Update mission acceptance status (Accept/Decline/Completed).