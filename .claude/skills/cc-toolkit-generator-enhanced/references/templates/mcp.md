# MCP Configuration Template

Use this template to generate .mcp.json for Claude Code projects.

---

## Base Structure

```json
{
  "mcpServers": {
    
  },
  "disabledMcpServers": []
}
```

---

## Common MCP Server Configs

### GitHub
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### PostgreSQL
```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "${DATABASE_URL}"
      }
    }
  }
}
```

### Supabase
```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server"],
      "env": {
        "SUPABASE_URL": "${SUPABASE_URL}",
        "SUPABASE_KEY": "${SUPABASE_KEY}"
      }
    }
  }
}
```

### Slack
```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    }
  }
}
```

### Notion
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-notion"],
      "env": {
        "NOTION_TOKEN": "${NOTION_TOKEN}"
      }
    }
  }
}
```

### Brave Search
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "${BRAVE_API_KEY}"
      }
    }
  }
}
```

### Puppeteer
```json
{
  "mcpServers": {
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-puppeteer"]
    }
  }
}
```

### Sequential Thinking
```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-sequential-thinking"]
    }
  }
}
```

### Memory (KV Store)
```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-memory"]
    }
  }
}
```

### Filesystem
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-filesystem", "/path/to/allowed/dir"]
    }
  }
}
```

---

## Combined Example

For a project with GitHub, PostgreSQL, and Slack:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "${DATABASE_URL}"
      }
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    }
  },
  "disabledMcpServers": []
}
```

---

## Generation Rules

### From Architecture.md

1. Extract `External Integrations` or `Third-Party Services` section
2. Match each integration to known MCP servers
3. Generate config with appropriate env vars
4. Add unmatched integrations as comments

### Matching Priority

1. **Exact match** — use official server
2. **Category match** — use generic server (e.g., any SQL → postgres)
3. **No match** — add comment for custom consideration

### Environment Variables

Always use `${VAR_NAME}` syntax for secrets:
- Never hardcode tokens/keys
- Use descriptive names: `GITHUB_TOKEN`, `DATABASE_URL`
- Document required vars in INSTALL.md

---

## Best Practices

1. **Minimal** — only include servers actually needed
2. **Disabled by default** — use `disabledMcpServers` for optional ones
3. **Env vars** — never hardcode secrets
4. **Test locally** — verify servers work before committing

## Context Window Considerations

| Servers Enabled | Approximate Context Impact |
|-----------------|---------------------------|
| 1-5 | Minimal (~5k tokens) |
| 5-10 | Moderate (~15k tokens) |
| 10-20 | Significant (~30k tokens) |
| 20+ | High risk of overflow |

**Recommendation:** Keep <10 servers enabled per project.

## File Location

- Project-level: `.mcp.json` in project root
- User-level: `~/.config/claude-code/mcp.json`

Project-level takes precedence.

---

## Complete Server Reference

| Integration | Package | Env Vars |
|-------------|---------|----------|
| GitHub | @modelcontextprotocol/server-github | GITHUB_TOKEN |
| GitLab | @modelcontextprotocol/server-gitlab | GITLAB_TOKEN |
| PostgreSQL | @modelcontextprotocol/server-postgres | DATABASE_URL |
| MySQL | @modelcontextprotocol/server-mysql | DATABASE_URL |
| SQLite | @modelcontextprotocol/server-sqlite | DB_PATH |
| MongoDB | @modelcontextprotocol/server-mongodb | MONGODB_URI |
| Redis | @modelcontextprotocol/server-redis | REDIS_URL |
| Supabase | @supabase/mcp-server | SUPABASE_URL, SUPABASE_KEY |
| Slack | @modelcontextprotocol/server-slack | SLACK_BOT_TOKEN |
| Notion | @modelcontextprotocol/server-notion | NOTION_TOKEN |
| Linear | mcp-linear | LINEAR_API_KEY |
| Jira | mcp-atlassian | JIRA_TOKEN |
| AWS | @aws/mcp-server | AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY |
| Vercel | mcp-vercel | VERCEL_TOKEN |
| Stripe | @stripe/mcp-server | STRIPE_API_KEY |
| Twilio | mcp-twilio | TWILIO_SID, TWILIO_TOKEN |
| Brave Search | @anthropic/mcp-server-brave-search | BRAVE_API_KEY |
| Puppeteer | @anthropic/mcp-server-puppeteer | (none) |
| Playwright | mcp-playwright | (none) |
| Memory | @anthropic/mcp-server-memory | (none) |
| Sequential Thinking | @anthropic/mcp-server-sequential-thinking | (none) |
| Filesystem | @anthropic/mcp-server-filesystem | (path arg) |
