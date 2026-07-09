# LLM and Agent Playbook

This project is expected to depend heavily on LLMs and autonomous agents. This document defines how to build safely and predictably.

## 1. Scope of AI Use

### In scope
- Natural language assistance in ERP modules
- Assisted drafting and summarization
- Operational copilots for support and workflow guidance
- AI-assisted analytics and report narratives

### Out of scope for first release
- Fully autonomous financial posting without human approval
- AI actions that bypass role and permission checks
- Direct AI writes to tenant tables outside validated service layer

## 2. Architecture Pattern for AI Features

Use this execution chain for all agent actions:

1. User request
2. Intent parser
3. Policy and permission check
4. Workspace context resolution
5. Feature gate check (subscription)
6. Tool call through explicit service contracts
7. Structured result and audit log

AI must never call ORM models directly. It must use whitelisted service functions.

## 3. Prompt and Tooling Contracts

### Prompt contract
- Must include actor id
- Must include workspace id
- Must include allowed actions list
- Must include safety constraints

### Tool contract
- Every tool input includes `workspace_id`
- Every tool validates permission before execution
- Every tool returns structured result with status and reason

## 4. Data Isolation and Safety

- All AI-executed data access remains subject to PostgreSQL RLS
- No cross-workspace prompts or retrieval
- No global context blending unless explicitly platform-admin and audited
- Redact sensitive fields in model output by default

## 5. Human-in-the-Loop Rules

Require explicit confirmation for high-risk operations:

- Billing-affecting actions
- Data deletion
- Role changes
- Accounting postings
- Contract/loan status changes

## 6. Observability and Audit

Log all agent actions with:

- actor
- workspace
- prompt hash
- tool name
- tool input summary
- tool result status
- latency
- cost tokens (if available)

Keep full prompt and response retention configurable by environment.

## 7. Evaluation and Quality Gates

### Offline evals
- Intent classification quality
- Tool selection accuracy
- Hallucination checks against known facts

### Online guards
- Confidence thresholds for autonomous steps
- Fallback to deterministic flow on low confidence
- User-visible explanation for denied actions

### Regression suite
- Workspace isolation test cases
- Permission enforcement test cases
- Prompt-injection resilience tests

## 8. Security Controls for Agentic Features

- Prompt injection resistance in retrieval/tool execution
- Strict allowlist for tool calls
- Request signing for internal tool invocations
- Rate limiting per user and workspace
- PII redaction strategy for logs and traces

## 9. Recommended Initial AI Backlog

1. Workspace assistant for navigation and FAQs
2. Billing and subscription assistant (read-only first)
3. Report explanation assistant with no write permissions
4. Drafting assistant for email and reminders

## 10. Release Readiness for AI Features

Before enabling an AI feature in production:

- Permission checks are implemented in service layer
- RLS paths are covered by tests
- Prompt and tool contracts are versioned
- Audit logging is complete
- Failure and fallback behavior is documented

## 11. Team Operating Model

- Product defines approved AI use cases
- Platform team owns AI runtime and observability
- Security team reviews tool contracts and logging
- Domain teams implement service methods consumed by AI tools
