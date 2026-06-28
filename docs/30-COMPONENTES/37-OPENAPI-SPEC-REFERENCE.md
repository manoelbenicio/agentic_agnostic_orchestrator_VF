# OpenAPI Specification Reference: Agnostic Orchestration Platform Control Plane
**Version**: 0.1.0
**Description**: 

## Endpoints

### POST /projects
**Summary**: Create Project
**Tags**: projects

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### GET /projects
**Summary**: List Projects
**Tags**: projects

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /projects/{project_id}
**Summary**: Get Project
**Tags**: projects

#### Parameters
- `project_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /projects/{project_id}
**Summary**: Update Project
**Tags**: projects

#### Parameters
- `project_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### DELETE /projects/{project_id}
**Summary**: Delete Project
**Tags**: projects

#### Parameters
- `project_id` (path, required): 

#### Responses
- **204**: Successful Response
- **422**: Validation Error

### POST /issues
**Summary**: Create Issue
**Tags**: issues

#### Parameters
- `x-agent-id` (header, optional): 

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### GET /issues
**Summary**: List Issues
**Tags**: issues

#### Parameters
- `tenant_id` (query, optional): 
- `project_id` (query, optional): 
- `status` (query, optional): 
- `assignee_runtime` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /issues/my
**Summary**: List My Issues
**Tags**: issues

#### Parameters
- `scope` (query, optional): 
- `agent_id` (query, optional): 
- `tenant_id` (query, optional): 
- `project_id` (query, optional): 
- `issue_status` (query, optional): 
- `x-agent-id` (header, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /issues/{issue_id}
**Summary**: Get Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /issues/{issue_id}
**Summary**: Update Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### DELETE /issues/{issue_id}
**Summary**: Delete Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **204**: Successful Response
- **422**: Validation Error

### POST /issues/{issue_id}/dispatch
**Summary**: Dispatch Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /api/issues
**Summary**: Create Issue
**Tags**: issues

#### Parameters
- `x-agent-id` (header, optional): 

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### GET /api/issues
**Summary**: List Issues
**Tags**: issues

#### Parameters
- `tenant_id` (query, optional): 
- `project_id` (query, optional): 
- `status` (query, optional): 
- `assignee_runtime` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /api/issues/my
**Summary**: List My Issues
**Tags**: issues

#### Parameters
- `scope` (query, optional): 
- `agent_id` (query, optional): 
- `tenant_id` (query, optional): 
- `project_id` (query, optional): 
- `issue_status` (query, optional): 
- `x-agent-id` (header, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /api/issues/{issue_id}
**Summary**: Get Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /api/issues/{issue_id}
**Summary**: Update Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### DELETE /api/issues/{issue_id}
**Summary**: Delete Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **204**: Successful Response
- **422**: Validation Error

### POST /api/issues/{issue_id}/dispatch
**Summary**: Dispatch Issue
**Tags**: issues

#### Parameters
- `issue_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /settings
**Summary**: Get Settings
**Tags**: settings

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /settings
**Summary**: Update Settings
**Tags**: settings

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /settings/profile
**Summary**: Get Profile
**Tags**: settings

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /settings/profile
**Summary**: Update Profile
**Tags**: settings

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /settings/integrations
**Summary**: List Integrations
**Tags**: settings

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /settings/integrations
**Summary**: Create Integration
**Tags**: settings

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### GET /settings/api-tokens
**Summary**: List Tokens
**Tags**: settings

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /settings/api-tokens
**Summary**: Create Token
**Tags**: settings

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### DELETE /settings/api-tokens/{id}
**Summary**: Revoke Token
**Tags**: settings

#### Parameters
- `id` (path, required): 

#### Responses
- **204**: Successful Response
- **422**: Validation Error

### GET /inbox
**Summary**: List Events
**Tags**: inbox

#### Parameters
- `tenant_id` (query, optional): 
- `read` (query, optional): 
- `archived` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /inbox
**Summary**: Create Event
**Tags**: inbox

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### POST /inbox/{event_id}/read
**Summary**: Mark Read
**Tags**: inbox

#### Parameters
- `event_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /inbox/bulk-archive
**Summary**: Bulk Archive
**Tags**: inbox

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /inbox/unread-count
**Summary**: Unread Count
**Tags**: inbox

#### Parameters
- `tenant_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /squads/{squad_id}/topology
**Summary**: Save Topology
**Tags**: squads

#### Parameters
- `squad_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /squads/{squad_id}/topology
**Summary**: Get Topology
**Tags**: squads

#### Parameters
- `squad_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /api/tasks
**Summary**: List Tasks
**Tags**: tasks

#### Parameters
- `status` (query, optional): 
- `agent` (query, optional): 
- `priority` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /api/tasks/board
**Summary**: Get Board
**Tags**: tasks

#### Responses
- **200**: Successful Response

### POST /api/tasks/reconcile
**Summary**: Reconcile Tasks
**Tags**: tasks

#### Responses
- **200**: Successful Response

### GET /api/tasks/herdmaster
**Summary**: List Herdmaster Tasks
**Tags**: tasks

#### Parameters
- `assigned_to` (query, optional): 
- `project_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /api/tasks/{task_id}
**Summary**: Get Task
**Tags**: tasks

#### Parameters
- `task_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /api/tasks/{task_id}
**Summary**: Update Task
**Tags**: tasks

#### Parameters
- `task_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /tasks
**Summary**: List Tasks
**Tags**: tasks

#### Parameters
- `status` (query, optional): 
- `agent` (query, optional): 
- `priority` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /tasks
**Summary**: Create Task

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /tasks/board
**Summary**: Get Board
**Tags**: tasks

#### Responses
- **200**: Successful Response

### POST /tasks/reconcile
**Summary**: Reconcile Tasks
**Tags**: tasks

#### Responses
- **200**: Successful Response

### GET /tasks/herdmaster
**Summary**: List Herdmaster Tasks
**Tags**: tasks

#### Parameters
- `assigned_to` (query, optional): 
- `project_id` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /tasks/{task_id}
**Summary**: Get Task
**Tags**: tasks

#### Parameters
- `task_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /tasks/{task_id}
**Summary**: Update Task
**Tags**: tasks

#### Parameters
- `task_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /seats
**Summary**: Register Seat
**Tags**: seats

#### Responses
- **201**: Successful Response
- **422**: Validation Error

### GET /seats
**Summary**: List Seats
**Tags**: seats

#### Parameters
- `tenant_id` (query, optional): 
- `vendor` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /seats/{seat_id}
**Summary**: Get Seat
**Tags**: seats

#### Parameters
- `seat_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### PATCH /seats/{seat_id}
**Summary**: Update Seat
**Tags**: seats

#### Parameters
- `seat_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### DELETE /seats/{seat_id}
**Summary**: Remove Seat
**Tags**: seats

#### Parameters
- `seat_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /sessions/device-login
**Summary**: Start Device Login
**Tags**: sessions

#### Responses
- **202**: Successful Response
- **422**: Validation Error

### GET /sessions
**Summary**: List Sessions
**Tags**: sessions

#### Parameters
- `seat_id` (query, optional): 
- `tenant_id` (query, optional): 
- `vendor` (query, optional): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /sessions/{session_id}/status
**Summary**: Get Status
**Tags**: sessions

#### Parameters
- `session_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /sessions/{session_id}/renew
**Summary**: Renew Session
**Tags**: sessions

#### Parameters
- `session_id` (path, required): 

#### Responses
- **202**: Successful Response
- **422**: Validation Error

### GET /health
**Summary**: Health

#### Responses
- **200**: Successful Response

### GET /health/ready
**Summary**: Ready

#### Responses
- **200**: Successful Response

### POST /squads/{squad_id}/messages
**Summary**: Send Message

#### Parameters
- `squad_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /agents
**Summary**: List Agents

#### Responses
- **200**: Successful Response

### POST /agents
**Summary**: Create Agent

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### DELETE /agents/{agent_id}
**Summary**: Delete Agent

#### Parameters
- `agent_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /finops/costs/token
**Summary**: Record Token Cost

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /finops/costs/seat
**Summary**: Record Seat Cost

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /finops/projects/{tenant_id}/{project_id}/rollup
**Summary**: Project Rollup

#### Parameters
- `tenant_id` (path, required): 
- `project_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /finops/projects/{tenant_id}/{project_id}/rollup/{dimension}
**Summary**: Project Rollup By Dimension

#### Parameters
- `tenant_id` (path, required): 
- `project_id` (path, required): 
- `dimension` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /tracing/events
**Summary**: Record Trace

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### POST /tracing/artifacts
**Summary**: Record Artifact

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /tracing/agents/{agent_id}
**Summary**: Trace Agent

#### Parameters
- `agent_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /tracing/runtimes/{runtime_id}
**Summary**: Trace Runtime

#### Parameters
- `runtime_id` (path, required): 

#### Responses
- **200**: Successful Response
- **422**: Validation Error

### GET /metrics
**Summary**: Metrics

#### Responses
- **200**: Successful Response

## Schemas

### AgentCreateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `label` (string): Label
- `vendor` (string): Vendor
- `role` (string): Role
- `workspace_id` (['string', 'null']): Workspace Id
- `pane_id` (['string', 'null']): Pane Id
- `stable_key` (['string', 'null']): Stable Key
- `metadata` (object): Metadata

### BoardResponse
#### Properties
- `total_tasks` (integer): Total Tasks
- `done` (integer): Done
- `overall_progress` (number): Overall Progress
- `total_eta_min` (integer): Total Eta Min
- `by_status` (object): By Status

### BulkArchiveRequest
#### Properties
- `event_ids` (array): Event Ids

### DeviceLoginRequest
#### Properties
- `seat_id` (string): Seat Id

### HTTPValidationError
#### Properties
- `detail` (array): Detail

### InboxEventCreateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `type` (unknown): 
- `title` (string): Title
- `message` (string): Message

### InboxEventResponse
#### Properties
- `id` (string): Id
- `tenant_id` (string): Tenant Id
- `type` (unknown): 
- `title` (string): Title
- `message` (string): Message
- `read` (boolean): Read
- `archived` (boolean): Archived
- `created_at` (['string', 'null']): Created At

### InboxEventType
Types of inbox events.

### IntegrationCreateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `provider` (string): Provider
- `config` (object): Config
- `enabled` (boolean): Enabled

### IntegrationResponse
#### Properties
- `integration_id` (string): Integration Id
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `provider` (string): Provider
- `config` (object): Config
- `enabled` (boolean): Enabled
- `created_at` (['string', 'null']): Created At
- `updated_at` (['string', 'null']): Updated At

### IssueCreateRequest
#### Properties
- `issue_id` (['string', 'null']): Issue Id
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `title` (string): Title
- `description` (['string', 'null']): Description
- `status` (unknown): 
- `priority` (unknown): 
- `assignee_runtime` (['string', 'null']): Assignee Runtime
- `operation_mode` (unknown): 
- `due_date` (['string', 'null']): Due Date
- `metadata` (object): Metadata

### IssueDispatchRequest
#### Properties
- `prompt` (['string', 'null']): Prompt
- `assignee_runtime` (['string', 'null']): Assignee Runtime
- `operation_mode` (['unknown', 'null']): 
- `credential_ref` (['string', 'null']): Credential Ref
- `seat_seconds` (['integer', 'null']): Seat Seconds

### IssuePriority
### IssueResponse
#### Properties
- `issue_id` (string): Issue Id
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `title` (string): Title
- `description` (['string', 'null']): Description
- `status` (unknown): 
- `priority` (unknown): 
- `assignee_runtime` (['string', 'null']): Assignee Runtime
- `operation_mode` (unknown): 
- `due_date` (['string', 'null']): Due Date
- `metadata` (object): Metadata
- `created_at` (['string', 'null']): Created At
- `updated_at` (['string', 'null']): Updated At
- `deleted_at` (['string', 'null']): Deleted At

### IssueStatus
### IssueUpdateRequest
#### Properties
- `title` (['string', 'null']): Title
- `description` (['string', 'null']): Description
- `status` (['unknown', 'null']): 
- `priority` (['unknown', 'null']): 
- `assignee_runtime` (['string', 'null']): Assignee Runtime
- `operation_mode` (['unknown', 'null']): 
- `due_date` (['string', 'null']): Due Date
- `metadata` (['object', 'null']): Metadata

### OperationMode
Execution mode selected per task and honored by the dispatcher.

### ProfileResponse
#### Properties
- `tenant_id` (string): Tenant Id
- `profile` (object): Profile

### ProfileUpdateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `profile` (object): Profile

### ProjectCreateRequest
#### Properties
- `project_id` (['string', 'null']): Project Id
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `description` (['string', 'null']): Description
- `status` (unknown): 
- `metadata` (object): Metadata

### ProjectResponse
#### Properties
- `project_id` (string): Project Id
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `description` (['string', 'null']): Description
- `status` (unknown): 
- `metadata` (object): Metadata
- `created_at` (['string', 'null']): Created At
- `updated_at` (['string', 'null']): Updated At
- `deleted_at` (['string', 'null']): Deleted At

### ProjectStatus
Lifecycle states for a project row.

### ProjectUpdateRequest
#### Properties
- `name` (['string', 'null']): Name
- `description` (['string', 'null']): Description
- `status` (['unknown', 'null']): 
- `metadata` (['object', 'null']): Metadata

### ReconcileResponse
#### Properties
- `file` (object): File
- `herdmaster` (object): Herdmaster
- `timestamp` (string): Timestamp

### RuntimeMessageRequest
HTTP body for runtime agent-to-agent messaging.

#### Properties
- `operation` (string): Operation
- `from_agent` (string): From Agent
- `to_agent` (string): To Agent
- `payload` (object): Payload
- `content` (['string', 'null']): Content
- `trace_id` (['string', 'null']): Trace Id
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `issue_id` (string): Issue Id
- `runtime_id` (['string', 'null']): Runtime Id
- `ttl_seconds` (integer): Ttl Seconds

### SeatCostRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `issue_id` (string): Issue Id
- `agent_id` (string): Agent Id
- `runtime_id` (string): Runtime Id
- `seat_id` (string): Seat Id
- `vendor` (string): Vendor
- `used_seconds` (integer): Used Seconds
- `period_seconds` (integer): Period Seconds
- `period_cost_usd` (['number', 'string']): Period Cost Usd
- `trace_id` (['string', 'null']): Trace Id

### SeatCreateRequest
#### Properties
- `seat_id` (string): Seat Id
- `tenant_id` (string): Tenant Id
- `vendor` (string): Vendor
- `home_dir` (string): Home Dir
- `config_dir` (string): Config Dir
- `display_name` (['string', 'null']): Display Name
- `active` (boolean): Active
- `metadata` (object): Metadata

### SeatUpdateRequest
#### Properties
- `tenant_id` (['string', 'null']): Tenant Id
- `vendor` (['string', 'null']): Vendor
- `home_dir` (['string', 'null']): Home Dir
- `config_dir` (['string', 'null']): Config Dir
- `display_name` (['string', 'null']): Display Name
- `active` (['boolean', 'null']): Active
- `metadata` (['object', 'null']): Metadata

### SettingsResponse
#### Properties
- `tenant_id` (string): Tenant Id
- `settings` (object): Settings

### SettingsUpdateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `settings` (object): Settings

### TaskCreateRequest
#### Properties
- `task_id` (string): Task Id
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `issue_id` (string): Issue Id
- `assignee_runtime` (string): Assignee Runtime
- `prompt` (string): Prompt
- `credential_ref` (string): Credential Ref
- `operation_mode` (string): Operation Mode
- `seat_seconds` (integer): Seat Seconds
- `timeout_seconds` (['integer', 'null']): Timeout Seconds
- `account_id` (['string', 'null']): Account Id

### TaskPriority
### TaskResponse
#### Properties
- `task_id` (string): Task Id
- `title` (string): Title
- `priority` (unknown): 
- `agent` (string): Agent
- `pane` (string): Pane
- `status` (unknown): 
- `eta_min` (integer): Eta Min
- `progress` (integer): Progress
- `herdmaster_task_id` (['string', 'null']): Herdmaster Task Id
- `herdmaster_state` (['string', 'null']): Herdmaster State
- `metadata` (object): Metadata
- `created_at` (['string', 'null']): Created At
- `updated_at` (['string', 'null']): Updated At
- `last_seen_at` (['string', 'null']): Last Seen At

### TaskStatus
Squad-task lifecycle states (mirrors squad-tasks.json status values).

### TaskUpdateRequest
#### Properties
- `status` (['unknown', 'null']): 
- `eta_min` (['integer', 'null']): Eta Min
- `progress` (['integer', 'null']): Progress
- `herdmaster_task_id` (['string', 'null']): Herdmaster Task Id
- `herdmaster_state` (['string', 'null']): Herdmaster State
- `metadata` (['object', 'null']): Metadata

### TokenCostRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `issue_id` (string): Issue Id
- `agent_id` (string): Agent Id
- `runtime_id` (string): Runtime Id
- `input_tokens` (integer): Input Tokens
- `output_tokens` (integer): Output Tokens
- `input_token_price_usd` (['number', 'string']): Input Token Price Usd
- `output_token_price_usd` (['number', 'string']): Output Token Price Usd
- `model` (string): Model
- `trace_id` (['string', 'null']): Trace Id

### TokenCreateRequest
#### Properties
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `expires_at` (['string', 'null']): Expires At

### TokenCreateResponse
Returned only on creation — includes the raw token value (shown once).

#### Properties
- `token_id` (string): Token Id
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `prefix` (string): Prefix
- `created_at` (['string', 'null']): Created At
- `expires_at` (['string', 'null']): Expires At
- `raw_token` (string): Raw Token

### TokenResponse
#### Properties
- `token_id` (string): Token Id
- `tenant_id` (string): Tenant Id
- `name` (string): Name
- `prefix` (string): Prefix
- `created_at` (['string', 'null']): Created At
- `expires_at` (['string', 'null']): Expires At

### TopologyEdgeRequest
#### Properties
- `source` (string): Source
- `target` (string): Target

### TopologyNodeRequest
#### Properties
- `id` (string): Id
- `role` (['string', 'null']): Role

### TopologySaveRequest
#### Properties
- `nodes` (array): Nodes
- `edges` (array): Edges

### TraceArtifactRequest
#### Properties
- `trace_id` (string): Trace Id
- `artifact_uri` (string): Artifact Uri
- `runtime_id` (string): Runtime Id
- `agent_id` (string): Agent Id
- `content_type` (string): Content Type
- `metadata` (object): Metadata

### TraceEventRequest
#### Properties
- `trace_id` (string): Trace Id
- `layer` (string): Layer
- `signal_type` (string): Signal Type
- `tenant_id` (string): Tenant Id
- `project_id` (string): Project Id
- `issue_id` (string): Issue Id
- `agent_id` (string): Agent Id
- `runtime_id` (string): Runtime Id
- `message` (string): Message
- `token_burn` (integer): Token Burn
- `seat_seconds` (integer): Seat Seconds
- `details` (object): Details

### UnreadCountResponse
#### Properties
- `count` (integer): Count

### ValidationError
#### Properties
- `loc` (array): Location
- `msg` (string): Message
- `type` (string): Error Type
- `input` (unknown): Input
- `ctx` (object): Context
