# 1215-VPS Runtime Flows

This document captures the important execution paths as swim lanes. Each flow is followed by the contract the implementation must honor.

## 1. Open WebUI Tool-Backed Action

```mermaid
sequenceDiagram
    participant U as User
    participant OWU as Open WebUI
    participant N8N as n8n
    participant B as Broker
    participant M as MinIO / Qdrant / Neo4j
    participant LF as Langfuse

    U->>OWU: Request action or information
    OWU->>LF: Start trace
    OWU->>B: Register session/run event
    OWU->>N8N: Invoke approved workflow/tool
    N8N->>B: Emit workflow-start event
    N8N->>M: Read or write artifacts and retrieval data
    N8N->>B: Emit workflow-result event
    OWU->>B: Register response and artifact links
    OWU->>LF: Close trace
    OWU-->>U: Return answer or result
```

**Trigger**
- User asks Open WebUI for a tool-backed action or enriched answer

**Required state writes**
- session/run registration at start
- workflow start/result events
- response event
- artifact link registration when files or documents are produced

**Trace points**
- Open WebUI request start
- workflow start and end
- artifact publication if applicable
- response completion

**Failure behavior**
- `n8n` failure returns a bounded error to Open WebUI
- broker still records failure state
- Langfuse trace closes with correlated error metadata

## 2. Paperclip Task Through Hermes Gateway

```mermaid
sequenceDiagram
    participant P as Paperclip
    participant G as Hermes gateway
    participant H as Hermes
    participant HON as Honcho
    participant B as Broker
    participant LF as Langfuse

    P->>B: Register task/run
    P->>LF: Start trace
    P->>G: Execute via socket shim
    G->>H: Forward request to Hermes
    H->>HON: Read and write memory
    H-->>G: Return output and session metadata
    G-->>P: Return result
    P->>B: Register outputs, session link, artifacts
    P->>LF: Close trace
```

**Trigger**
- Paperclip heartbeat, approval, or manual task run invokes a Hermes-backed agent execution

**Required state writes**
- task/run creation
- execution result
- Hermes session linkage
- artifact registration when files are produced

**Trace points**
- Paperclip run start
- gateway invocation
- Hermes execution completion
- memory interaction summary if surfaced

**Failure behavior**
- gateway failure is visible to Paperclip as execution failure
- failed execution is still written to broker and trace system
- no direct host fallback path bypasses the gateway

## 3. Approval-Gated Sensitive Workflow

```mermaid
sequenceDiagram
    participant OWU as Open WebUI or Paperclip
    participant N8N as n8n
    participant B as Broker
    participant A as Human approver
    participant LF as Langfuse

    OWU->>N8N: Request sensitive action
    N8N->>B: Record pending approval event
    N8N->>LF: Start approval trace
    N8N-->>A: Request approval
    A-->>N8N: Approve or reject
    N8N->>B: Record approval outcome
    alt Approved
        N8N->>N8N: Execute action
        N8N->>B: Record execution result
    else Rejected
        N8N->>B: Record rejection
    end
    N8N->>LF: Close trace
```

**Trigger**
- A request falls into a policy-defined sensitive class

**Required state writes**
- pending approval event
- approval or rejection event
- final execution event if approved

**Trace points**
- approval requested
- approval granted or denied
- execution result if applicable

**Failure behavior**
- absence of approval must fail closed
- timeout behavior records explicit non-completion or expiration

## 4. Brokered Enrichment Into Retrieval and Artifacts

```mermaid
sequenceDiagram
    participant B as Broker worker
    participant MIN as MinIO
    participant QD as Qdrant
    participant NEO as Neo4j
    participant LF as Langfuse

    B->>MIN: Store artifact/blob if needed
    B->>QD: Upsert semantic representation
    B->>NEO: Upsert entities and relationships
    B->>LF: Emit enrichment trace
    B->>B: Mark artifact and checkpoint state
```

**Trigger**
- A brokered event or artifact becomes eligible for enrichment

**Required state writes**
- artifact manifest
- enrichment status
- provider checkpoint or worker checkpoint

**Trace points**
- artifact write
- vector upsert
- graph upsert
- checkpoint completion

**Failure behavior**
- partial enrichment must be resumable
- one enrichment backend failing must not corrupt broker state

## 5. Memory Write and Recall Path

```mermaid
sequenceDiagram
    participant H as Hermes or broker adapter
    participant HON as Honcho
    participant B as Broker
    participant QD as Qdrant
    participant NEO as Neo4j

    H->>HON: Submit memory-relevant interaction
    HON->>B: Emit structured memory event or recall artifact
    B->>QD: Upsert semantic continuity data
    B->>NEO: Upsert structured relationships if applicable
    H->>HON: Request recall or context
    HON-->>H: Return memory-informed result
```

**Trigger**
- Hermes execution or adapter logic submits memory-relevant interaction data

**Required state writes**
- memory event or recall artifact
- optional vector or graph enrichment records

**Trace points**
- memory ingest
- memory recall
- downstream enrichment if performed

**Failure behavior**
- memory subsystem failure must degrade gracefully without blocking basic execution
- private and shared memory boundaries must remain intact even on failure
