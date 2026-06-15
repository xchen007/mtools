# Jira Sync Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `Jira Sync` through the UI by adding a Jira-local secondary navigation entry and a direct query-page shortcut to `/jira/sync/`.

**Architecture:** Keep the top-level tool switcher unchanged and extend the shared shell navigation view model so Jira routes expose a small secondary route set. Add the contextual query-page shortcut in the existing card header action cluster, keep the query-card sidebar intact, and verify the feature through server-rendered view/template tests plus shell-navigation service tests.

**Tech Stack:** Django 3.2, SQLite test database, server-rendered templates, shared `WorkspaceService` shell context, existing `jira_workspace` CSS.

---

## File Map

- Modify `apps/jira_workspace/services/workspace_service.py`: define Jira-local section items and compute active state for Jira routes.
- Modify `apps/jira_workspace/tests/test_workspace_service.py`: cover Jira-local secondary navigation contents and active-state behavior.
- Modify `templates/jira_workspace/base.html`: render a shared tool-local navigation slot in the shell.
- Create `templates/jira_workspace/partials/tool_context_nav.html`: render the shared current-tool secondary navigation list.
- Modify `templates/jira_workspace/partials/query_card_header.html`: add the direct `Open Jira Sync` shortcut in the existing action cluster.
- Modify `static/jira_workspace/jira.css`: style the shared tool-local navigation and the query-page sync shortcut.
- Modify `apps/jira_workspace/tests/test_views.py`: add template assertions for Jira-local navigation and the query-page shortcut while preserving card-centric sidebar behavior.

## Task 1: Add Jira-Local Secondary Navigation to the Shared Shell

**Files:**
- Modify: `apps/jira_workspace/services/workspace_service.py`
- Modify: `apps/jira_workspace/tests/test_workspace_service.py`
- Modify: `templates/jira_workspace/base.html`
- Create: `templates/jira_workspace/partials/tool_context_nav.html`

- [ ] **Step 1: Write the failing shell-navigation tests**

Add two tests to `apps/jira_workspace/tests/test_workspace_service.py`:

```python
def test_build_shell_navigation_expands_jira_sections_for_query(self):
    shell = WorkspaceService().build_shell_navigation(current_route_name="query")

    assert [item["label"] for item in shell["current_sections"]] == [
        "Dashboard",
        "Query",
        "Sync",
        "Profiles",
    ]
    assert next(item for item in shell["current_sections"] if item["label"] == "Query")["active"] is True
    assert next(item for item in shell["current_sections"] if item["label"] == "Sync")["href"] == reverse("jira_workspace:sync")


def test_build_shell_navigation_marks_sync_section_active(self):
    shell = WorkspaceService().build_shell_navigation(current_route_name="sync")

    assert shell["current_tool"]["key"] == "jira"
    assert next(item for item in shell["current_sections"] if item["label"] == "Sync")["active"] is True
    assert next(item for item in shell["current_sections"] if item["label"] == "Query")["active"] is False
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_workspace_service.WorkspaceServiceTests.test_build_shell_navigation_expands_jira_sections_for_query apps.jira_workspace.tests.test_workspace_service.WorkspaceServiceTests.test_build_shell_navigation_marks_sync_section_active -v 2
```

Expected: FAIL because `current_sections` is currently empty for Jira routes.

- [ ] **Step 3: Implement the shell navigation model and shared partial**

Update `apps/jira_workspace/services/workspace_service.py` to populate Jira-local sections:

```python
def _build_current_sections(self, *, current_tool_key, current_route_name):
    if current_tool_key != "jira":
        return []

    items = [
        ("dashboard", "Dashboard", reverse("jira_workspace:dashboard")),
        ("query", "Query", reverse("jira_workspace:query")),
        ("sync", "Sync", reverse("jira_workspace:sync")),
        ("profiles", "Profiles", reverse("jira_workspace:profiles")),
    ]
    return [
        {
            "key": key,
            "label": label,
            "href": href,
            "active": current_route_name == key,
        }
        for key, label, href in items
    ]
```

Create `templates/jira_workspace/partials/tool_context_nav.html`:

```django
{% if shell_current_sections %}
  <nav class="tool-context-nav" aria-label="Current Tool">
    {% for item in shell_current_sections %}
      <a class="tool-context-nav__link{% if item.active %} active{% endif %}" href="{{ item.href }}">
        <span>{{ item.label }}</span>
      </a>
    {% endfor %}
  </nav>
{% endif %}
```

Render the shared partial in `templates/jira_workspace/base.html` immediately after the top bar:

```django
  <div class="app-shell">
    {% include "jira_workspace/partials/topbar.html" %}
    {% include "jira_workspace/partials/tool_context_nav.html" %}
    {% include "jira_workspace/partials/app_nav.html" %}
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_workspace_service.WorkspaceServiceTests.test_build_shell_navigation_expands_jira_sections_for_query apps.jira_workspace.tests.test_workspace_service.WorkspaceServiceTests.test_build_shell_navigation_marks_sync_section_active -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit the navigation-model change**

```bash
git add apps/jira_workspace/services/workspace_service.py apps/jira_workspace/tests/test_workspace_service.py templates/jira_workspace/base.html templates/jira_workspace/partials/tool_context_nav.html
git commit -m "feat: add jira secondary shell navigation"
```

## Task 2: Add the Query-Page `Open Jira Sync` Shortcut

**Files:**
- Modify: `templates/jira_workspace/partials/query_card_header.html`
- Modify: `apps/jira_workspace/tests/test_views.py`
- Modify: `templates/jira_workspace/queries.html` (only if a dedicated context variable is needed)

- [ ] **Step 1: Write the failing query-page shortcut test**

Add a view test to `apps/jira_workspace/tests/test_views.py`:

```python
def test_query_page_renders_open_jira_sync_shortcut(self):
    response = self.client.get(reverse("jira_workspace:query"))

    assert response.status_code == 200
    content = response.content.decode()
    header = content.split('<header class="query-card-header">', 1)[1].split("</header>", 1)[0]

    assert "Open Jira Sync" in header
    assert f'href="{reverse("jira_workspace:sync")}"' in header
    assert "Run now" in header
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_page_renders_open_jira_sync_shortcut -v 2
```

Expected: FAIL because the query-card header currently has no sync shortcut.

- [ ] **Step 3: Add the direct shortcut in the query-card header**

Modify `templates/jira_workspace/partials/query_card_header.html` so the action cluster includes a direct link:

```django
  <div class="query-card-header__actions">
    <a class="workspace-control" href="{% url 'jira_workspace:sync' %}">Open Jira Sync</a>
    <button class="workspace-control" type="button" data-query-card-editor-open>Edit card</button>
    <form method="post">
      {% csrf_token %}
      <input type="hidden" name="action" value="duplicate_card">
      <input type="hidden" name="card_id" value="{{ selected_card.id }}">
      <button class="workspace-control" type="submit">Duplicate</button>
    </form>
    <button class="workspace-control" type="button" data-copy-text="{{ selected_card.jql_text|default:selected_card.name }}">Copy query</button>
    <form method="post">
      {% csrf_token %}
      <input type="hidden" name="action" value="run_card">
      <input type="hidden" name="card_id" value="{{ selected_card.id }}">
      <button class="workspace-control workspace-control--primary" type="submit">Run now</button>
    </form>
```

- [ ] **Step 4: Run the test to verify GREEN**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_page_renders_open_jira_sync_shortcut -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit the query-page shortcut**

```bash
git add templates/jira_workspace/partials/query_card_header.html apps/jira_workspace/tests/test_views.py
git commit -m "feat: add query page shortcut to jira sync"
```

## Task 3: Style the Secondary Navigation and Add End-to-End Template Regression Coverage

**Files:**
- Modify: `static/jira_workspace/jira.css`
- Modify: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Write the failing template regression tests**

Add two tests to `apps/jira_workspace/tests/test_views.py`:

```python
def test_query_page_renders_jira_secondary_navigation(self):
    response = self.client.get(reverse("jira_workspace:query"))

    assert response.status_code == 200
    content = response.content.decode()
    shell_nav = content.split('aria-label="Current Tool"', 1)[1].split("</nav>", 1)[0]

    assert "Dashboard" in shell_nav
    assert "Query" in shell_nav
    assert "Sync" in shell_nav
    assert "Profiles" in shell_nav


def test_query_cards_remain_in_left_sidebar_after_sync_navigation_addition(self):
    response = self.client.get(reverse("jira_workspace:query"))

    assert response.status_code == 200
    content = response.content.decode()
    app_nav = content.split('<aside class="app-nav app-nav--commercial"', 1)[1].split("</aside>", 1)[0]

    assert 'aria-label="Jira Query Cards"' in app_nav
    assert "New Card" in app_nav
    assert "Sync" not in app_nav
```

- [ ] **Step 2: Run the regression tests to verify RED**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_page_renders_jira_secondary_navigation apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_cards_remain_in_left_sidebar_after_sync_navigation_addition -v 2
```

Expected: the secondary-navigation test FAILS before the CSS/template hooks are finalized; the sidebar-regression test should protect against reintroducing legacy Jira functions into the left nav.

- [ ] **Step 3: Add the minimal styles for the shared secondary nav**

Add compact styles to `static/jira_workspace/jira.css`:

```css
.tool-context-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 0;
}

.tool-context-nav__link {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text-muted);
  padding: 0 12px;
  text-decoration: none;
}

.tool-context-nav__link.active {
  border-color: var(--border-strong);
  background: var(--surface-muted);
  color: var(--text);
}
```

- [ ] **Step 4: Run focused regression tests and then the broader navigation/view suite**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_page_renders_jira_secondary_navigation apps.jira_workspace.tests.test_views.JiraWorkspaceViewTests.test_query_cards_remain_in_left_sidebar_after_sync_navigation_addition -v 2
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_workspace_service apps.jira_workspace.tests.test_views -v 2
```

Expected: PASS, with the secondary navigation visible in Jira pages and query cards still living in the left sidebar.

- [ ] **Step 5: Commit the styling and regression coverage**

```bash
git add static/jira_workspace/jira.css apps/jira_workspace/tests/test_views.py
git commit -m "feat: style jira sync navigation entry points"
```

## Task 4: Final Verification

**Files:**
- Modify: none
- Test: `apps/jira_workspace/tests/test_workspace_service.py`
- Test: `apps/jira_workspace/tests/test_views.py`

- [ ] **Step 1: Run the complete targeted verification suite**

Run:

```bash
./.venv/bin/python manage.py test apps.jira_workspace.tests.test_workspace_service apps.jira_workspace.tests.test_views -v 2
```

Expected: PASS.

- [ ] **Step 2: Check the exact files changed for this feature**

Run:

```bash
git diff --name-only HEAD~3..HEAD
```

Expected output includes only the shell-navigation, query-header, CSS, and test files added or modified for this feature.

- [ ] **Step 3: Capture the final implementation commit summary**

Run:

```bash
git log --oneline -3
```

Expected: the last three commits correspond to:

- `feat: add jira secondary shell navigation`
- `feat: add query page shortcut to jira sync`
- `feat: style jira sync navigation entry points`
```
