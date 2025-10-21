# Migrating from Dialogflow ES to Dialogflow CX

This guide helps you migrate from the older Dialogflow ES (v2) service to the newer Dialogflow CX (v3) service.

## Quick Comparison

| Feature | Dialogflow ES (v2) | Dialogflow CX (v3) |
|---------|-------------------|-------------------|
| **Service** | `services.dialogflow` | `services.dialogflow_cx` |
| **Connector** | `Dialogflow` | `DialogflowCX` |
| **Config** | `DialogflowConf` | `DialogflowCXConf` |
| **Request** | `GetIntentRequest` | `DetectIntentRequest` |
| **Agent ID** | Not required | **Required** |
| **Location** | Not required | **Required** |
| **API Endpoint** | Global only | Regional (auto-determined) |
| **Training** | Automatic | Manual (click "Train") |
| **Contexts** | Simple strings | Flows and pages |

## Code Changes

### 1. Import Statements

**Before (ES):**
```python
from sic_framework.services.dialogflow.dialogflow import (
    Dialogflow,
    DialogflowConf,
    GetIntentRequest,
    QueryResult,
    RecognitionResult,
)
```

**After (CX):**
```python
from sic_framework.services.dialogflow_cx.dialogflow_cx import (
    DialogflowCX,
    DialogflowCXConf,
    DetectIntentRequest,
    QueryResult,
    RecognitionResult,
)
```

### 2. Configuration

**Before (ES):**
```python
conf = DialogflowConf(
    keyfile_json=keyfile_json,
    sample_rate_hertz=16000,
    language="en"
)
```

**After (CX):**
```python
conf = DialogflowCXConf(
    keyfile_json=keyfile_json,
    agent_id="your-agent-id",      # NEW: Required
    location="us-central1",         # NEW: Required
    sample_rate_hertz=16000,
    language="en"
)
```

### 3. Connector Initialization

**Before (ES):**
```python
dialogflow = Dialogflow(conf=conf, input_source=nao.mic)
```

**After (CX):**
```python
dialogflow_cx = DialogflowCX(conf=conf, input_source=nao.mic)
```

### 4. Request Messages

**Before (ES):**
```python
# With contexts
contexts_dict = {"context_name": 5}
reply = dialogflow.request(GetIntentRequest(session_id, contexts_dict))
```

**After (CX):**
```python
# With parameters (optional)
parameters = {"key": "value"}
reply = dialogflow_cx.request(DetectIntentRequest(session_id, parameters))
```

### 5. Response Handling

The response structure is mostly the same, but some fields are accessed differently:

**Before (ES):**
```python
# Intent from query_result.intent.display_name
intent = reply.intent

# Fulfillment from fulfillment_messages
message = reply.fulfillment_message
```

**After (CX):**
```python
# Intent from query_result.match.intent.display_name
intent = reply.intent  # Helper property extracts this

# Confidence from match.confidence
confidence = reply.intent_confidence  # Helper property

# Fulfillment from response_messages
message = reply.fulfillment_message  # Helper property
```

## Complete Migration Example

### Before (Dialogflow ES)

```python
import json
from sic_framework.devices import Nao
from sic_framework.services.dialogflow.dialogflow import (
    Dialogflow,
    DialogflowConf,
    GetIntentRequest,
)

# Load credentials
keyfile_json = json.load(open("google-key.json"))

# Configure
conf = DialogflowConf(
    keyfile_json=keyfile_json,
    sample_rate_hertz=16000,
    language="en"
)

# Initialize
nao = Nao(ip="192.168.1.100")
dialogflow = Dialogflow(conf=conf, input_source=nao.mic)

# Conversation loop
session_id = 12345
while True:
    contexts_dict = {"context_name": 1}
    reply = dialogflow.request(GetIntentRequest(session_id, contexts_dict))
    
    print(f"Intent: {reply.intent}")
    print(f"Response: {reply.fulfillment_message}")
```

### After (Dialogflow CX)

```python
import json
from sic_framework.devices import Nao
from sic_framework.services.dialogflow_cx.dialogflow_cx import (
    DialogflowCX,
    DialogflowCXConf,
    DetectIntentRequest,
)

# Load credentials
keyfile_json = json.load(open("google-key.json"))

# Configure (with agent_id and location)
conf = DialogflowCXConf(
    keyfile_json=keyfile_json,
    agent_id="your-agent-id",       # NEW: Get from CX console
    location="us-central1",          # NEW: Your agent's location
    sample_rate_hertz=16000,
    language="en"
)

# Initialize
nao = Nao(ip="192.168.1.100")
dialogflow_cx = DialogflowCX(conf=conf, input_source=nao.mic)

# Conversation loop
session_id = 12345
while True:
    reply = dialogflow_cx.request(DetectIntentRequest(session_id))
    
    print(f"Intent: {reply.intent}")
    print(f"Confidence: {reply.intent_confidence}")
    print(f"Response: {reply.fulfillment_message}")
```

## Agent Setup Changes

### Dialogflow ES

1. Create agent at https://dialogflow.cloud.google.com/
2. Add intents with training phrases
3. Save changes (auto-trains)
4. Use contexts for conversation management
5. Only need project ID

### Dialogflow CX

1. Create agent at https://dialogflow.cloud.google.com/cx/
2. Add intents with training phrases
3. Design flows and pages
4. **Explicitly click "Train"** (required!)
5. Note agent ID, location, and project ID
6. Use flows/pages for conversation management

## Finding Your Agent Details

Use the verification tool to get your agent configuration:

```bash
cd sic_applications/utils
python verify_dialogflow_cx_agent.py
```

This will show you:
- Agent ID (required for config)
- Location (required for config)
- API endpoint (auto-determined)
- Agent details (language, timezone, etc.)

## Common Pitfalls

### 1. Forgetting to Train

**Problem**: `404 NLU model does not exist`

**Solution**: In CX, you must explicitly train your agent after making changes.

### 2. Wrong Location

**Problem**: `404 Agent not found`

**Solution**: Verify your agent's location. CX agents can be in different regions.

### 3. Missing Agent ID

**Problem**: Configuration error

**Solution**: Agent ID is required in CX. Find it in the agent settings or URL.

### 4. Regional Endpoints

**Problem**: Connection errors

**Solution**: The service auto-determines the correct regional endpoint. If issues persist, check your location setting.

### 5. Session Path Format

**Problem**: Invalid session path

**Solution**: CX uses a different format. The service handles this automatically.

## Benefits of Migrating to CX

1. **Better scalability**: Handles complex conversations with flows and pages
2. **More control**: Fine-grained control over conversation flow
3. **Regional deployment**: Deploy agents in specific regions for lower latency
4. **Advanced features**: Webhooks, sentiment analysis, knowledge bases
5. **Better analytics**: More detailed conversation analytics
6. **Future-proof**: Google's focus is on CX, not ES

## Backwards Compatibility

Both services can coexist in your project:

```python
# Use ES for legacy agents
from sic_framework.services.dialogflow import Dialogflow, DialogflowConf

# Use CX for new agents
from sic_framework.services.dialogflow_cx import DialogflowCX, DialogflowCXConf
```

## Migration Checklist

- [ ] Create Dialogflow CX agent
- [ ] Import or recreate intents
- [ ] Design flows and pages
- [ ] Train the agent
- [ ] Note agent ID and location
- [ ] Update import statements
- [ ] Update configuration (add agent_id, location)
- [ ] Update connector name (Dialogflow → DialogflowCX)
- [ ] Update request type (GetIntentRequest → DetectIntentRequest)
- [ ] Test with simple intents first
- [ ] Test complete conversation flows
- [ ] Update error handling if needed
- [ ] Deploy and monitor

## Need Help?

1. Run `verify_dialogflow_cx_agent.py` to diagnose configuration issues
2. Check `README.md` for detailed documentation
3. Review demo files in `sic_applications/demos/`
4. Consult [Dialogflow CX Documentation](https://cloud.google.com/dialogflow/cx/docs)

