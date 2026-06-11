# mtools

> Personal utility tools and APIs - unified integration workspace

## Overview

`mtools` is a utility tool platform consolidating Jira integration, sync operations, and future myscript tools. The project provides both backend services and frontend interfaces for streamlined workflow management.

## Features

### Jira Integration

Advanced Jira query and sync capabilities powered by mjira:

- **Issue Query**: Full-text search with multi-filter support
  - Filter by project, assignee, sprint, status
  - Sort by updated/created date, issue key, or summary
  - Pagination with customizable page sizes
  - Saved views: My Issues, Team Issues, Blocked, This Week
  - Statistics: status and project distribution with progress bars
  - Issue detail drawer with complete information

- **Issues Management**: List-detail interface with saved views, compound filters, and bulk actions
- **Sync Center**: Run presets, dry-run previews, timeline visualization, and error bucket management
- **Real-time Stats**: Project distribution, status metrics, and issue counts

### Sync Operations

- **sync2pod**: Local-to-pod sync tool showcase with full workflow simulation
  - Project configuration manager
  - Sync strategy panel (incremental/force full/dry-run)
  - Execution console with progress stream
  - Watch mode with debounce control
  - Archive/chunk upload insights
  - Exclusion patterns and safety validation

### Integration Catalog

- Grouped tools by type: Issue Ops / Sync Ops / Utilities
- Readiness badges: ready / beta / planned
- Contract surface indicators: input/output schemas and event streams
- Add from myscript onboarding flow placeholder

## Frontend Preview

All pages are built with frontend-only mock data for design review:

- **Shared app shell**: Consistent layout across all tools
- **Unified design tokens**: Colors, typography, spacing, and component patterns
- **Status vocabulary**: `idle` / `running` / `success` / `failed` / `partial` / `queued`
- **Mock data contracts**: `ToolRun`, `LogEvent`, `SyncProjectConfig`, `SyncSessionStats`, `JiraIssue`

### Available Pages

- `ui-preview/index.html` - Workspace entry and design baseline
- `ui-preview/jira-query.html` - Advanced issue search and filtering
- `ui-preview/jira-issues.html` - Issue list with saved views and bulk actions
- `ui-preview/jira-sync.html` - Sync run management and dry-run preview
- `ui-preview/sync2pod.html` - sync2pod tool workflow showcase
- `ui-preview/integrations.html` - Tool catalog and integration status
- `ui-preview/dashboard.html` - Workspace KPIs and tool state overview

## Getting Started

### Preview (Frontend Only)

Open any HTML file in `ui-preview/` directory with your browser:

```bash
open ui-preview/index.html
open ui-preview/jira-query.html
```

### Backend Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI tools
python -m mtools.cli --help
```

## Project Structure

```
mtools/
├── ui-preview/          # Frontend mock pages
│   ├── index.html
│   ├── jira-query.html
│   ├── jira-issues.html
│   ├── jira-sync.html
│   ├── sync2pod.html
│   ├── integrations.html
│   └── dashboard.html
├── apps/                # Django apps (legacy)
│   └── notion/
├── mtools/              # Django project (legacy)
│   ├── __init__.py
│   ├── settings.py
│   └── wsgi.py
├── manage.py            # Django manage script
└── README.md
```

## Design System

### Colors

- `--bg`: `#060b15` - Background
- `--shell`: `rgba(8, 14, 27, 0.92)` - Shell background
- `--surface`: `rgba(12, 21, 42, 0.86)` - Card background
- `--line`: `rgba(129, 167, 255, 0.24)` - Border/line
- `--text`: `#dce8ff` - Primary text
- `--muted`: `#8ea8d8` - Secondary text
- `--ok`: `#65ffbb` - Success/safe
- `--warn`: `#ffce78` - Warning/partial
- `--err`: `#ff8da0` - Error/failed
- `--info`: `#8bb2ff` - Info/running

### Typography

- `--font-title`: "Space Grotesk", sans-serif - Headings
- `--font-body`: "IBM Plex Sans", sans-serif - Body text
- `--font-mono`: "IBM Plex Mono", monospace - Code/metrics

### Component Patterns

- **List-detail**: Shared table + drawer flow for data tools
- **Execution panel**: Run / dry-run / logs / timeline for action tools
- **Status badges**: Unified status vocabulary with visual semantics
- **Progress bars**: Consistent job and transfer indicators
- **KPI cards**: Single-value metrics with labels

## Contributing

This is a personal utility project for streamlined workflow management. Future additions will include:

- Additional myscript tool integrations
- Backend API connections for real data
- Enhanced collaboration features
- Custom dashboard configurations

## License

Personal use only.