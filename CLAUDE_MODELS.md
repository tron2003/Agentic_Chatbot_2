# Claude Models Configuration

## Quick Switch Guide

### 1. **Use Haiku (Default - Dev/Testing)**
```bash
# No env var needed - Haiku is default
python run.py
```
✅ **Best for**: Development, testing, learning
- 💰 Cheapest ($0.80 per million input tokens)
- ⚡ Fastest responses (50-100ms)
- 🧠 Good reasoning for simple-medium tasks
- 📊 200k context window

### 2. **Use Sonnet (Balanced)**
```bash
# Switch to Sonnet for better quality
export CLAUDE_MODEL=sonnet
python run.py
```
✅ **Best for**: Production with good balance
- 💰 Mid-range cost ($3 per million input tokens)
- ⚡ Fast responses (100-200ms)
- 🧠 Excellent reasoning for complex tasks
- 📊 200k context window

### 3. **Use Opus (Best Quality)**
```bash
# Switch to Opus for maximum reasoning
export CLAUDE_MODEL=opus
python run.py
```
✅ **Best for**: Complex research, multi-step agent reasoning
- 💰 Most expensive ($15 per million input tokens)
- ⏱️ Slower responses (200-500ms)
- 🧠 Best reasoning capability
- 📊 200k context window

## Model Comparison

| Feature | Haiku | Sonnet | Opus |
|---------|-------|--------|------|
| Cost | $0.80 | $3.00 | $15.00 |
| Speed | ⚡⚡⚡ | ⚡⚡ | ⚡ |
| Quality | ✓✓ | ✓✓✓ | ✓✓✓✓ |
| Agent Reasoning | ✓ | ✓✓ | ✓✓✓ |
| Tool Use | ✓ | ✓✓ | ✓✓✓ |
| Context | 200k | 200k | 200k |

## Usage Recommendations

### Development Phase
```bash
export CLAUDE_MODEL=haiku
# Test features, build agent workflows
```

### Testing Phase
```bash
export CLAUDE_MODEL=sonnet
# Verify quality, test complex scenarios
```

### Production
```bash
export CLAUDE_MODEL=sonnet  # or opus for critical reasoning
# Balance cost and quality
```

## Cost Estimation

### Haiku (Default)
- Simple chat: ~100 tokens input + 100 output = $0.00016 per message
- Complex agent reasoning: ~2000 tokens = $0.0016 per message

### Sonnet
- Simple chat: ~100 tokens = $0.0006 per message
- Complex agent reasoning: ~2000 tokens = $0.006 per message

### Opus
- Simple chat: ~100 tokens = $0.003 per message
- Complex agent reasoning: ~2000 tokens = $0.03 per message

## Environment Variables

Add to `.env`:
```env
# API Key (required)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional: Override model
# CLAUDE_MODEL=sonnet  # or opus
```

## Runtime Switching

```bash
# In one terminal: Start with Haiku
python run.py

# In another terminal: Check which model is running
curl http://localhost:8001/health
```

The logs will show:
```
🤖 Using Claude: claude-haiku-4-5-20251001
```

## Agent Behavior by Model

### Haiku (Current Default)
- ✅ Good for: Simple reasoning, quick responses
- ⚠️ May struggle with: Very complex multi-step reasoning
- 💡 Best for: Development, learning, demos

### Sonnet
- ✅ Good for: Balanced reasoning + cost
- ✅ Can handle: Complex agent workflows
- 💡 Best for: Production systems

### Opus
- ✅ Good for: Complex research tasks
- ✅ Excels at: Multi-step tool chains
- 💡 Best for: Critical reasoning, verification

## Tips to Save Credits

1. **Use Haiku by default** - Great for most tasks
2. **Use Sonnet for complex reasoning** - When Haiku struggles
3. **Batch requests** - Process multiple queries at once
4. **Cache prompts** - System prompts are cached after 1024 tokens
5. **Limit context** - Use CONVERSATION_CONTEXT_WINDOW=10 in .env

## Testing Each Model

```bash
# Test Haiku
CLAUDE_MODEL=haiku python run.py &

# Send test request
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain quantum computing in 2 sentences",
    "thread_id": "test"
  }'

# Switch to Sonnet
pkill -f "python run.py"
CLAUDE_MODEL=sonnet python run.py &

# Same test with Sonnet
```

## Current Settings

**Default Provider**: `claude`
**Default Model**: `claude-haiku-4-5-20251001`
**Can Switch To**: `sonnet` or `opus`

Start with Haiku, upgrade to Sonnet/Opus only when needed! 🚀
