# NIRA Temporal MCP

> Time-aware scheduling for Claude — manage tasks, reminders, and recurring schedules

[![PyPI version](https://badge.fury.io/py/nira-temporal.svg)](https://pypi.org/project/nira-temporal/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Quick Start

```bash
pip install nira-temporal
```

Add to your Claude Code MCP config (`~/.claude.json`):
```json
{
  "mcpServers": {
    "nira-temporal": {
      "command": "python",
      "args": ["-m", "nira_temporal"]
    }
  }
}
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `NIRA_DATA_DIR` | Optional | Directory for schedule data (default: ~/nira_temporal) |

## License

MIT — built by [pachote](https://github.com/pachote)
