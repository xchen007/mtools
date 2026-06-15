(function () {
  var lastTicketTrigger = null;
  var lastSettingsTrigger = null;
  var liveState = null;
  var NAV_COLLAPSE_KEY = "mtools.nav.collapsed";
  var NAV_WIDTH_KEY = "mtools.nav.width";
  var THEME_STORAGE_KEY = "mtools.theme.mode";
  var SETTINGS_STORAGE_KEY = "mtools.settings.v1";
  var TICKET_COLUMN_WIDTHS = {
    key: 120,
    project: 110,
    status: 140,
    assignee: 150,
    reporter: 150,
    priority: 120,
    updated: 160,
    sprint: 160,
    created: 160
  };

  function markActiveNav() {
    var currentPath = window.location.pathname;
    document.querySelectorAll(".nav-link").forEach(function (link) {
      var href = link.getAttribute("href");
      if (!href || href === "#") {
        return;
      }

      if (href === currentPath) {
        link.classList.add("active");
      }
    });
  }

  function stampRailPlaceholders() {
    document.querySelectorAll("[data-rail-empty]").forEach(function (node) {
      node.setAttribute("data-rail-state", "empty");
    });
  }

  function resolveTarget(trigger) {
    var selector = trigger.getAttribute("data-partial-target");
    if (selector) {
      return document.querySelector(selector);
    }
    return document.querySelector("[data-partial-target]");
  }

  async function refreshPartial(trigger) {
    var url = trigger.getAttribute("data-partial-url") || trigger.getAttribute("href");
    var target = resolveTarget(trigger);

    if (!url || !target || url === "#") {
      return;
    }

    trigger.setAttribute("aria-busy", "true");

    try {
      var response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      if (!response.ok) {
        throw new Error("Partial refresh failed with status " + response.status);
      }

      target.innerHTML = await response.text();
      initializeRichTables(target);
    } catch (error) {
      window.console.error(error);
    } finally {
      trigger.removeAttribute("aria-busy");
    }
  }

  async function refreshAutoTargets() {
    var targets = Array.from(document.querySelectorAll("[data-auto-refresh-url]"));
    await Promise.all(targets.map(async function (target) {
      var url = target.getAttribute("data-auto-refresh-url");
      if (!url) {
        return;
      }

      target.setAttribute("aria-busy", "true");
      try {
        var response = await fetch(url, {
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        if (!response.ok) {
          throw new Error("Auto refresh failed with status " + response.status);
        }

        target.innerHTML = await response.text();
        initializeRichTables(target);
      } catch (error) {
        window.console.error(error);
      } finally {
        target.removeAttribute("aria-busy");
      }
    }));
  }

  async function pollLiveState() {
    try {
      var response = await fetch("/jira/live-state/", {
        cache: "no-store",
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      if (!response.ok) {
        throw new Error("Live state failed with status " + response.status);
      }

      var nextState = await response.json();
      if (!liveState) {
        liveState = nextState;
        return nextState;
      }

      if (nextState.asset_version && nextState.asset_version !== liveState.asset_version) {
        window.location.reload();
        return nextState;
      }

      if (nextState.data_version && nextState.data_version !== liveState.data_version) {
        liveState = nextState;
        await refreshAutoTargets();
        return nextState;
      }

      liveState = nextState;
      return nextState;
    } catch (error) {
      window.console.error(error);
      return liveState;
    }
  }

  function initializeLiveUpdates() {
    if (!window.fetch) {
      return;
    }

    pollLiveState().then(function (state) {
      var interval = (state && state.poll_interval_ms) || 2500;
      window.setInterval(pollLiveState, interval);
    });
  }

  function initializeSyncRefresh() {
    var syncRoot = document.querySelector('[data-sync-refresh="active"]');
    if (!syncRoot) {
      return;
    }
    window.setTimeout(function () {
      window.location.reload();
    }, 3000);
  }

  function drawerValue(row, name) {
    return row.getAttribute("data-ticket-" + name) || "-";
  }

  function drawerDataFromRow(row) {
    return {
      key: drawerValue(row, "key"),
      project: drawerValue(row, "project"),
      summary: drawerValue(row, "summary"),
      status: drawerValue(row, "status"),
      assignee: drawerValue(row, "assignee"),
      reporter: drawerValue(row, "reporter"),
      priority: drawerValue(row, "priority"),
      sprint: drawerValue(row, "sprint"),
      created: drawerValue(row, "created"),
      updated: drawerValue(row, "updated")
    };
  }

  function setDrawerText(drawer, name, value) {
    var node = drawer.querySelector("[data-ticket-drawer-" + name + "]");
    if (node) {
      node.textContent = value || "-";
    }
  }

  function openTicketDrawerFromData(data, trigger) {
    var drawer = document.querySelector("[data-ticket-drawer]");
    if (!drawer || !data) {
      return;
    }

    closeQueryCardEditor();
    lastTicketTrigger = trigger || null;
    setDrawerText(drawer, "key", data.key);
    setDrawerText(drawer, "project", data.project);
    setDrawerText(drawer, "summary", data.summary);
    setDrawerText(drawer, "status", data.status);
    setDrawerText(drawer, "assignee", data.assignee);
    setDrawerText(drawer, "reporter", data.reporter);
    setDrawerText(drawer, "priority", data.priority);
    setDrawerText(drawer, "sprint", data.sprint);
    setDrawerText(drawer, "created", data.created);
    setDrawerText(drawer, "updated", data.updated);
    drawer.querySelectorAll("[data-ticket-copy-active-key]").forEach(function (button) {
      button.setAttribute("data-ticket-copy-active-key", data.key || "");
    });
    drawer.querySelectorAll("[data-ticket-open-external]").forEach(function (link) {
      var browseContainer = trigger && typeof trigger.closest === "function"
        ? trigger.closest("[data-rich-table-ticket-browse-base-url]")
        : null;
      link.href = data.key && data.key !== "-"
        ? ticketBrowseUrlFromBase(browseContainer ? readTicketBrowseBaseUrl(browseContainer) : "", data.key)
        : "#";
    });

    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");

    var closeButton = drawer.querySelector(".ticket-drawer__close");
    if (closeButton) {
      closeButton.focus();
    }
  }

  function openTicketDrawer(row) {
    if (!row) {
      return;
    }
    openTicketDrawerFromData(drawerDataFromRow(row), row);
  }

  function openQueryCardEditor() {
    var editor = document.querySelector("[data-query-card-editor]");
    if (!editor) {
      return;
    }

    closeTicketDrawer();
    editor.classList.add("is-open");
    editor.setAttribute("aria-hidden", "false");
    editor.setAttribute("data-editor-open", "true");

    var firstInput = editor.querySelector("input[name='name'], textarea, select, button");
    if (firstInput && typeof firstInput.focus === "function") {
      firstInput.focus();
    }
  }

  function closeQueryCardEditor() {
    var editor = document.querySelector("[data-query-card-editor]");
    if (!editor) {
      return;
    }

    editor.classList.remove("is-open");
    editor.setAttribute("aria-hidden", "true");
    editor.setAttribute("data-editor-open", "false");
  }

  function syncQueryCardColumnOrder(editor) {
    var input = editor.querySelector("[data-query-card-column-values]");
    if (!input) {
      return;
    }

    var values = [];
    editor.querySelectorAll("[data-column-key]").forEach(function (item) {
      var checkbox = item.querySelector("[data-column-enabled]");
      if (checkbox && checkbox.checked) {
        values.push(item.getAttribute("data-column-key"));
      }
    });
    input.value = values.join(", ");
  }

  function initializeQueryCardColumnEditors(scope) {
    (scope || document).querySelectorAll("[data-query-card-column-editor]").forEach(function (editor) {
      if (editor.dataset.columnEditorInitialized === "true") {
        return;
      }

      editor.addEventListener("click", function (event) {
        var moveButton = event.target.closest("[data-column-move]");
        if (!moveButton) {
          return;
        }

        event.preventDefault();
        var item = moveButton.closest("[data-column-key]");
        var direction = moveButton.getAttribute("data-column-move");
        if (!item || !item.parentNode) {
          return;
        }

        if (direction === "up" && item.previousElementSibling) {
          item.parentNode.insertBefore(item, item.previousElementSibling);
        } else if (direction === "down" && item.nextElementSibling) {
          item.parentNode.insertBefore(item.nextElementSibling, item);
        }
        syncQueryCardColumnOrder(editor);
      });

      editor.addEventListener("change", function (event) {
        if (event.target.closest("[data-column-enabled]")) {
          syncQueryCardColumnOrder(editor);
        }
      });

      syncQueryCardColumnOrder(editor);
      editor.dataset.columnEditorInitialized = "true";
    });
  }

  function collectTicketRows(container) {
    return Array.from(container.querySelectorAll("[data-ticket-row]")).map(function (row) {
      return drawerDataFromRow(row);
    });
  }

  function supportsLocalStorage() {
    try {
      return !!window.localStorage;
    } catch (error) {
      return false;
    }
  }

  function initializeNavCollapse() {
    var button = document.querySelector("[data-nav-toggle]");
    if (!button) {
      return;
    }

    function setCollapsed(collapsed) {
      document.body.classList.toggle("nav-collapsed", collapsed);
      button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      button.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
      button.setAttribute("title", collapsed ? "Expand sidebar" : "Collapse sidebar");
    }

    var collapsed = false;
    if (supportsLocalStorage()) {
      collapsed = window.localStorage.getItem(NAV_COLLAPSE_KEY) === "true";
    }

    setCollapsed(collapsed);

    button.addEventListener("click", function () {
      collapsed = !collapsed;
      setCollapsed(collapsed);

      if (!supportsLocalStorage()) {
        return;
      }

      try {
        window.localStorage.setItem(NAV_COLLAPSE_KEY, collapsed ? "true" : "false");
      } catch (error) {
        window.console.error(error);
      }
    });
  }

  function initializeSidebarResize() {
    var handle = document.querySelector("[data-sidebar-resize-handle]");
    if (!handle) {
      return;
    }

    var root = document.documentElement;
    var minWidth = 196;
    var maxWidth = 420;
    var defaultWidth = 236;

    function clampWidth(width) {
      return Math.min(maxWidth, Math.max(minWidth, Math.round(width)));
    }

    function applyWidth(width, persist) {
      var nextWidth = clampWidth(width);
      root.style.setProperty("--app-nav-width", nextWidth + "px");
      handle.setAttribute("aria-valuenow", String(nextWidth));

      if (persist && supportsLocalStorage()) {
        try {
          window.localStorage.setItem(NAV_WIDTH_KEY, String(nextWidth));
        } catch (error) {
          window.console.error(error);
        }
      }
    }

    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-valuemin", String(minWidth));
    handle.setAttribute("aria-valuemax", String(maxWidth));
    handle.setAttribute("aria-valuenow", String(defaultWidth));

    if (supportsLocalStorage()) {
      var storedWidth = parseInt(window.localStorage.getItem(NAV_WIDTH_KEY) || "", 10);
      if (!Number.isNaN(storedWidth)) {
        applyWidth(storedWidth, false);
      }
    }

    handle.addEventListener("pointerdown", function (event) {
      if (document.body.classList.contains("nav-collapsed")) {
        return;
      }

      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add("sidebar-resizing");

      function onPointerMove(moveEvent) {
        applyWidth(moveEvent.clientX, false);
      }

      function onPointerUp(upEvent) {
        handle.releasePointerCapture(upEvent.pointerId);
        document.body.classList.remove("sidebar-resizing");
        document.removeEventListener("pointermove", onPointerMove);
        document.removeEventListener("pointerup", onPointerUp);
        applyWidth(upEvent.clientX, true);
      }

      document.addEventListener("pointermove", onPointerMove);
      document.addEventListener("pointerup", onPointerUp);
    });

    handle.addEventListener("dblclick", function () {
      applyWidth(defaultWidth, true);
    });

    handle.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }

      event.preventDefault();
      var currentWidth = parseInt(handle.getAttribute("aria-valuenow") || defaultWidth, 10);
      var delta = event.key === "ArrowRight" ? 12 : -12;
      applyWidth(currentWidth + delta, true);
    });
  }

  function preferredDarkQuery() {
    if (!window.matchMedia) {
      return null;
    }
    return window.matchMedia("(prefers-color-scheme: dark)");
  }

  function resolveThemeMode(mode) {
    if (mode === "light" || mode === "dark") {
      return mode;
    }

    var query = preferredDarkQuery();
    return query && query.matches ? "dark" : "light";
  }

  function nextThemeMode(mode) {
    var modes = ["system", "light", "dark"];
    var index = modes.indexOf(mode);
    return modes[(index + 1) % modes.length];
  }

  function themeIconMarkup(mode) {
    if (mode === "light") {
      return '<svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>';
    }
    if (mode === "dark") {
      return '<svg viewBox="0 0 24 24" focusable="false"><path d="M20.99 12.74A8.5 8.5 0 1 1 11.26 3.01 6.5 6.5 0 0 0 20.99 12.74Z"></path></svg>';
    }
    return '<svg viewBox="0 0 24 24" focusable="false"><rect x="4" y="5" width="16" height="11" rx="2"></rect><path d="M9 20h6"></path><path d="M12 16v4"></path></svg>';
  }

  function themeButtonMetadata(mode) {
    if (mode === "light") {
      return { label: "Light", title: "Theme: Light" };
    }
    if (mode === "dark") {
      return { label: "Dark", title: "Theme: Dark" };
    }
    return { label: "Auto", title: "Theme: System" };
  }

  function applyThemeMode(mode) {
    var normalizedMode = mode === "light" || mode === "dark" ? mode : "system";
    document.documentElement.setAttribute("data-theme", normalizedMode);
    document.documentElement.setAttribute("data-resolved-theme", resolveThemeMode(normalizedMode));

    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var metadata = themeButtonMetadata(normalizedMode);
      var icon = button.querySelector("[data-theme-icon]");
      var label = button.querySelector("[data-theme-label]");
      button.setAttribute("data-theme-mode", normalizedMode);
      button.setAttribute("aria-label", metadata.title);
      button.setAttribute("title", metadata.title);
      if (icon) {
        icon.innerHTML = themeIconMarkup(normalizedMode);
      }
      if (label) {
        label.textContent = metadata.label;
      }
    });
  }

  function readThemeMode() {
    if (!supportsLocalStorage()) {
      return "system";
    }

    try {
      return window.localStorage.getItem(THEME_STORAGE_KEY) || "system";
    } catch (error) {
      window.console.error(error);
      return "system";
    }
  }

  function writeThemeMode(mode) {
    if (!supportsLocalStorage()) {
      return;
    }

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch (error) {
      window.console.error(error);
    }
  }

  function initializeThemeSwitcher() {
    var buttons = Array.from(document.querySelectorAll("[data-theme-toggle]"));
    var query = preferredDarkQuery();

    applyThemeMode(readThemeMode());

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var currentMode = document.documentElement.getAttribute("data-theme") || "system";
        var nextMode = nextThemeMode(currentMode);
        writeThemeMode(nextMode);
        applyThemeMode(nextMode);
      });
    });

    if (!query) {
      return;
    }

    function handleSystemThemeChange() {
      if (document.documentElement.getAttribute("data-theme") === "system") {
        applyThemeMode("system");
      }
    }

    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", handleSystemThemeChange);
    } else if (typeof query.addListener === "function") {
      query.addListener(handleSystemThemeChange);
    }
  }

  function defaultWorkspaceSettings() {
    return {
      global: {
        defaultTool: "workspace",
        refreshInterval: "2500",
        compactTables: false
      },
      tools: {
        jira: {
          override: false,
          landingPage: "dashboard",
          pageSize: "20"
        },
        sync2pod: {
          override: false,
          runMode: "manual",
          showLogs: false
        },
        integrations: {
          override: false,
          healthScan: "manual",
          showContracts: false
        }
      }
    };
  }

  function readWorkspaceSettings() {
    if (!supportsLocalStorage()) {
      return defaultWorkspaceSettings();
    }

    try {
      var stored = JSON.parse(window.localStorage.getItem(SETTINGS_STORAGE_KEY) || "null");
      return Object.assign(defaultWorkspaceSettings(), stored || {});
    } catch (error) {
      window.console.error(error);
      return defaultWorkspaceSettings();
    }
  }

  function writeWorkspaceSettings(settings) {
    if (!supportsLocalStorage()) {
      return;
    }

    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    } catch (error) {
      window.console.error(error);
    }
  }

  function hydrateSettingsForm(form, settings) {
    form.querySelectorAll("[data-setting-scope='global'] [data-setting-key]").forEach(function (field) {
      var key = field.getAttribute("data-setting-key");
      if (field.type === "checkbox") {
        field.checked = settings.global[key] === true;
      } else if (settings.global[key] !== undefined) {
        field.value = settings.global[key];
      }
    });

    form.querySelectorAll("[data-tool-settings]").forEach(function (section) {
      var tool = section.getAttribute("data-tool-settings");
      var toolSettings = (settings.tools && settings.tools[tool]) || {};
      var override = section.querySelector("[data-tool-override]");

      if (override) {
        override.checked = toolSettings.override === true;
      }

      section.querySelectorAll("[data-tool-setting]").forEach(function (field) {
        var key = field.getAttribute("data-tool-setting");
        if (field.type === "checkbox") {
          field.checked = toolSettings[key] === true;
        } else if (toolSettings[key] !== undefined) {
          field.value = toolSettings[key];
        }
      });

      updateToolOverrideState(section);
    });
  }

  function collectSettingsForm(form) {
    var settings = defaultWorkspaceSettings();

    form.querySelectorAll("[data-setting-scope='global'] [data-setting-key]").forEach(function (field) {
      var key = field.getAttribute("data-setting-key");
      settings.global[key] = field.type === "checkbox" ? field.checked : field.value;
    });

    form.querySelectorAll("[data-tool-settings]").forEach(function (section) {
      var tool = section.getAttribute("data-tool-settings");
      var override = section.querySelector("[data-tool-override]");
      settings.tools[tool].override = override ? override.checked : false;

      section.querySelectorAll("[data-tool-setting]").forEach(function (field) {
        var key = field.getAttribute("data-tool-setting");
        settings.tools[tool][key] = field.type === "checkbox" ? field.checked : field.value;
      });
    });

    return settings;
  }

  function updateToolOverrideState(section) {
    var override = section.querySelector("[data-tool-override]");
    var inherited = override && !override.checked;
    section.classList.toggle("is-inherited", inherited);
    section.querySelectorAll("[data-tool-setting]").forEach(function (field) {
      field.disabled = inherited;
    });
  }

  function openSettingsDrawer(trigger) {
    var drawer = document.querySelector("[data-settings-drawer]");
    var form = document.querySelector("[data-settings-form]");
    if (!drawer || !form) {
      return;
    }

    lastSettingsTrigger = trigger || null;
    hydrateSettingsForm(form, readWorkspaceSettings());
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");

    document.querySelectorAll("[data-settings-open]").forEach(function (button) {
      button.setAttribute("aria-expanded", "true");
    });

    var closeButton = drawer.querySelector("[data-settings-close]");
    if (closeButton && typeof closeButton.focus === "function") {
      closeButton.focus();
    }
  }

  function closeSettingsDrawer() {
    var drawer = document.querySelector("[data-settings-drawer]");
    if (!drawer) {
      return;
    }

    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    document.querySelectorAll("[data-settings-open]").forEach(function (button) {
      button.setAttribute("aria-expanded", "false");
    });

    if (lastSettingsTrigger && typeof lastSettingsTrigger.focus === "function") {
      lastSettingsTrigger.focus();
    }
  }

  function initializeSettingsDrawer() {
    var drawer = document.querySelector("[data-settings-drawer]");
    var form = document.querySelector("[data-settings-form]");
    if (!drawer || !form) {
      return;
    }

    hydrateSettingsForm(form, readWorkspaceSettings());

    document.querySelectorAll("[data-settings-open]").forEach(function (button) {
      button.addEventListener("click", function () {
        openSettingsDrawer(button);
      });
    });

    drawer.querySelectorAll("[data-settings-close]").forEach(function (button) {
      button.addEventListener("click", closeSettingsDrawer);
    });

    form.querySelectorAll("[data-tool-override]").forEach(function (override) {
      override.addEventListener("change", function () {
        var section = override.closest("[data-tool-settings]");
        if (section) {
          updateToolOverrideState(section);
        }
      });
    });

    var reset = form.querySelector("[data-settings-reset]");
    if (reset) {
      reset.addEventListener("click", function () {
        var settings = defaultWorkspaceSettings();
        writeWorkspaceSettings(settings);
        hydrateSettingsForm(form, settings);
      });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      writeWorkspaceSettings(collectSettingsForm(form));
      closeSettingsDrawer();
    });
  }

  function buildRichTableStorageKey(container) {
    var scope = container.getAttribute("data-rich-table-persist-scope") || window.location.pathname;
    var tableId = container.getAttribute("data-rich-table-id") || "jira-ticket-table";
    return "mtools.rich_table." + scope + "." + tableId;
  }

  function readRichTableState(container) {
    if (!supportsLocalStorage()) {
      return null;
    }

    try {
      return JSON.parse(window.localStorage.getItem(buildRichTableStorageKey(container)) || "null");
    } catch (error) {
      window.console.error(error);
      return null;
    }
  }

  function writeRichTableState(container, state) {
    if (!supportsLocalStorage()) {
      return;
    }

    try {
      window.localStorage.setItem(buildRichTableStorageKey(container), JSON.stringify(state));
    } catch (error) {
      window.console.error(error);
    }
  }

  function normalizeTicketColumnKey(key) {
    var aliases = {
      issue_key: "key",
      project_key: "project",
      updated_at: "updated",
      created_at: "created"
    };
    return aliases[key] || key;
  }

  function readRichTableDefaultColumns(container) {
    return (container.getAttribute("data-rich-table-default-columns") || "")
      .split(",")
      .map(function (key) {
        return normalizeTicketColumnKey(key.trim());
      })
      .filter(Boolean);
  }

  function applyRichTableDefaultColumns(container, columns) {
    var defaultColumns = readRichTableDefaultColumns(container);
    if (!defaultColumns.length) {
      return columns;
    }

    var defaultSet = {};
    defaultColumns.forEach(function (field) {
      defaultSet[field] = true;
    });

    var columnsByField = {};
    columns.forEach(function (column) {
      columnsByField[column.field] = Object.assign({}, column, {
        visible: defaultSet[column.field] === true
      });
    });

    var orderedColumns = [];
    defaultColumns.forEach(function (field) {
      if (!columnsByField[field]) {
        return;
      }
      orderedColumns.push(columnsByField[field]);
      delete columnsByField[field];
    });

    Object.keys(columnsByField).forEach(function (field) {
      orderedColumns.push(columnsByField[field]);
    });
    return orderedColumns;
  }

  function collectRichTableState(table, container) {
    var columns = table.getColumns().map(function (column) {
      var definition = column.getDefinition();
      return {
        field: definition.field,
        title: definition.title,
        visible: column.isVisible(),
        width: typeof column.getWidth === "function" ? column.getWidth() : definition.width,
        frozen: definition.frozen === true
      };
    });

    return {
      searchQuery: table._mtoolsSearchQuery || "",
      statusFilters: table._mtoolsStatusFilters || [],
      activeView: table._mtoolsActiveView || "All",
      density: table._mtoolsDensity || "compact",
      pageSize: typeof table.getPageSize === "function" ? table.getPageSize() : 20,
      sorters: typeof table.getSorters === "function" ? table.getSorters() : [],
      columns: columns
    };
  }

  function buildTicketColumnsFromState(container, state) {
    var baseColumns = buildTicketColumns(container);
    if (!state || !state.columns || !state.columns.length) {
      return applyRichTableDefaultColumns(container, baseColumns);
    }

    var baseColumnsByField = {};
    baseColumns.forEach(function (column) {
      baseColumnsByField[column.field] = column;
    });

    var restoredColumns = [];
    state.columns.forEach(function (savedColumn) {
      var baseColumn = baseColumnsByField[savedColumn.field];
      if (!baseColumn) {
        return;
      }

      restoredColumns.push(
        Object.assign({}, baseColumn, {
          visible: savedColumn.visible !== false,
          width: savedColumn.width || baseColumn.width,
          frozen: savedColumn.frozen === true || baseColumn.frozen === true
        })
      );
      delete baseColumnsByField[savedColumn.field];
    });

    Object.keys(baseColumnsByField).forEach(function (field) {
      restoredColumns.push(baseColumnsByField[field]);
    });

    return restoredColumns;
  }

  function applyRichTableState(table, container) {
    var state = readRichTableState(container);
    if (!state) {
      return;
    }

    if (state.searchQuery) {
      applyRichTableSearch(table, state.searchQuery);
      var search = container.parentNode.querySelector("[data-rich-table-search]");
      if (search) {
        search.value = state.searchQuery;
      }
    }
    if (state.statusFilters && state.statusFilters.length) {
      applyRichTableStatusFilters(table, state.statusFilters);
      container.parentNode.querySelectorAll("[data-rich-table-status-filter]").forEach(function (checkbox) {
        checkbox.checked = state.statusFilters.indexOf(checkbox.value) !== -1;
      });
    }
    if (state.sorters && state.sorters.length && typeof table.setSort === "function") {
      table.setSort(state.sorters);
    }
    if (state.pageSize && typeof table.setPageSize === "function") {
      table.setPageSize(state.pageSize);
    }
    setRichTableDensity(table, state.density || "compact");
  }

  function labelRichTableControls(container) {
    var pageSize = container.querySelector(".tabulator-page-size");
    if (!pageSize) {
      return;
    }

    var labelId = (container.getAttribute("data-rich-table-id") || "rich-table") + "-page-size-label";
    var inputId = (container.getAttribute("data-rich-table-id") || "rich-table") + "-page-size";
    if (!pageSize.id) {
      pageSize.id = inputId;
    }
    if (!document.getElementById(labelId)) {
      var label = document.createElement("label");
      label.id = labelId;
      label.className = "sr-only";
      label.setAttribute("for", pageSize.id);
      label.textContent = "Page size";
      pageSize.parentNode.insertBefore(label, pageSize);
    }
    container.querySelectorAll("label").forEach(function (label) {
      if (!label.control && label.textContent.trim().toLowerCase() === "page size") {
        label.setAttribute("for", pageSize.id);
        label.classList.add("sr-only");
      }
    });
    pageSize.setAttribute("name", "page_size");
    pageSize.setAttribute("aria-label", "Page Size");
  }

  function normalizeTicketTokenClass(value) {
    return String(value || "empty")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "empty";
  }

  function makeTicketToken(value, kind) {
    var token = document.createElement("span");
    var normalized = normalizeTicketTokenClass(value);
    token.className = "ticket-token ticket-token--" + kind + " ticket-token--" + kind + "-" + normalized;
    token.textContent = value || "-";
    return token;
  }

  function ticketTokenFormatter(kind) {
    return function (cell) {
      return makeTicketToken(cell.getValue(), kind);
    };
  }

  function ticketBrowseUrlFromBase(baseUrl, key) {
    var normalizedKey = key || "";
    if (!normalizedKey || normalizedKey === "-") {
      return "#";
    }

    var normalizedBase = (baseUrl || window.mtoolsJiraBrowseBaseUrl || "https://jirap.corp.ebay.com").replace(/\/+$/, "");
    return normalizedBase + "/browse/" + encodeURIComponent(normalizedKey);
  }

  function readTicketBrowseBaseUrl(container) {
    return container.getAttribute("data-rich-table-ticket-browse-base-url") || "";
  }

  function ticketKeyLinkFormatter(container) {
    var baseUrl = readTicketBrowseBaseUrl(container);
    return function (cell) {
      var value = cell.getValue() || "-";
      if (value === "-") {
        return value;
      }

      var link = document.createElement("a");
      link.className = "ticket-key-link";
      link.href = ticketBrowseUrlFromBase(baseUrl, value);
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = value;
      link.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      return link;
    };
  }

  function applyCombinedRichTableFilters(table) {
    var query = (table._mtoolsSearchQuery || "").trim().toLowerCase();
    var statuses = table._mtoolsStatusFilters || [];

    if (!query && !statuses.length) {
      table.clearFilter(true);
      return;
    }

    table.setFilter(function (data) {
      var matchesQuery = true;
      if (query) {
        matchesQuery = Object.keys(data).some(function (key) {
          return String(data[key] || "").toLowerCase().indexOf(query) !== -1;
        });
      }

      var matchesStatus = !statuses.length || statuses.indexOf(data.status || "-") !== -1;
      return matchesQuery && matchesStatus;
    });
  }

  function applyRichTableSearch(table, query) {
    table._mtoolsSearchQuery = query || "";
    applyCombinedRichTableFilters(table);
  }

  function applyRichTableStatusFilters(table, statuses) {
    table._mtoolsStatusFilters = statuses || [];
    applyCombinedRichTableFilters(table);
  }

  function setRichTableDensity(table, density) {
    var normalized = density === "comfortable" ? "comfortable" : "compact";
    table._mtoolsDensity = normalized;
    if (!table.element) {
      return;
    }
    table.element.classList.toggle("rich-table--comfortable", normalized === "comfortable");
    table.element.classList.toggle("rich-table--compact", normalized !== "comfortable");
  }

  function collectTicketStatuses(table) {
    var statuses = {};
    table.getData().forEach(function (row) {
      statuses[row.status || "-"] = true;
    });
    return Object.keys(statuses).sort();
  }

  function buildTicketColumns(container) {
    return [
      { title: "Key", field: "key", frozen: true, sorter: "string", width: TICKET_COLUMN_WIDTHS.key, formatter: ticketKeyLinkFormatter(container) },
      { title: "Project", field: "project", sorter: "string", width: TICKET_COLUMN_WIDTHS.project, formatter: ticketTokenFormatter("project") },
      { title: "Summary", field: "summary", sorter: "string", minWidth: 280 },
      { title: "Status", field: "status", sorter: "string", width: TICKET_COLUMN_WIDTHS.status, formatter: ticketTokenFormatter("status") },
      { title: "Assignee", field: "assignee", sorter: "string", width: TICKET_COLUMN_WIDTHS.assignee },
      { title: "Reporter", field: "reporter", sorter: "string", width: TICKET_COLUMN_WIDTHS.reporter },
      { title: "Priority", field: "priority", sorter: "string", width: TICKET_COLUMN_WIDTHS.priority, formatter: ticketTokenFormatter("priority") },
      { title: "Updated", field: "updated", sorter: "string", width: TICKET_COLUMN_WIDTHS.updated },
      { title: "Sprint", field: "sprint", visible: false, width: TICKET_COLUMN_WIDTHS.sprint },
      { title: "Created", field: "created", visible: false, width: TICKET_COLUMN_WIDTHS.created },
      { title: "", field: "_actions", width: 86, hozAlign: "right", formatter: renderTicketRowActions, headerSort: false, frozen: true }
    ];
  }

  function renderTicketRowActions(cell) {
    var data = cell.getRow().getData();
    var wrap = document.createElement("span");
    var copy = document.createElement("button");
    wrap.className = "rich-table-row-actions";
    copy.type = "button";
    copy.textContent = "Copy";
    copy.setAttribute("data-ticket-copy-key", data.key || "");
    copy.setAttribute("aria-label", "Copy " + (data.key || "ticket key"));
    wrap.appendChild(copy);
    return wrap;
  }

  function ensureRichTableHeader(parent, container) {
    var header = parent.querySelector("[data-rich-table-header]");
    if (!header) {
      header = document.createElement("div");
      header.className = "rich-table-header";
      header.setAttribute("data-rich-table-header", "true");
      parent.insertBefore(header, container);
    }

    var heading = header.querySelector(".rich-table-heading");
    if (!heading) {
      heading = parent.querySelector(".panel__header");
      if (heading && heading.parentNode !== header) {
        heading.classList.add("rich-table-heading");
        header.appendChild(heading);
      }
    }

    return header;
  }

  function renderRichTableViewTabs(container, table) {
    var parent = container.parentNode;
    if (!parent || container.getAttribute("data-rich-table-views") !== "tickets") {
      return;
    }

    var existing = parent.querySelector("[data-rich-table-view-tabs]");
    if (existing) {
      existing.remove();
    }

    var tabs = document.createElement("div");
    tabs.className = "rich-table-view-tabs";
    tabs.setAttribute("data-rich-table-view-tabs", "true");

    [
      { label: "All", status: "" },
      { label: "Blocked", status: "Blocked" },
      { label: "In Progress", status: "In Progress" },
      { label: "Review", status: "Review" }
    ].forEach(function (view, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = view.label;
      button.className = "rich-table-view-tabs__button";
      button.setAttribute("data-rich-table-view", view.label);
      if (index === 0) {
        button.classList.add("is-active");
      }
      button.addEventListener("click", function () {
        tabs.querySelectorAll("button").forEach(function (node) {
          node.classList.remove("is-active");
        });
        button.classList.add("is-active");
        table._mtoolsActiveView = view.label;
        applyRichTableStatusFilters(table, view.status ? [view.status] : []);
        writeRichTableState(container, collectRichTableState(table, container));
      });
      tabs.appendChild(button);
    });

    var header = ensureRichTableHeader(parent, container);
    var toolbar = header.querySelector("[data-rich-table-toolbar]");
    var toolbarLeft = toolbar ? toolbar.querySelector(".rich-table-toolbar__group:not(.rich-table-toolbar__group--right)") : null;
    if (toolbarLeft) {
      toolbarLeft.insertBefore(tabs, toolbarLeft.firstChild);
    } else {
      header.appendChild(tabs);
    }
  }

  function renderRichTableToolbar(container, table) {
    var parent = container.parentNode;
    if (!parent) {
      return;
    }

    var existing = parent.querySelector("[data-rich-table-toolbar]");
    if (existing) {
      existing.remove();
    }

    var toolbar = document.createElement("div");
    toolbar.className = "rich-table-toolbar";
    toolbar.setAttribute("data-rich-table-toolbar", "true");

    var left = document.createElement("div");
    left.className = "rich-table-toolbar__group";

    var searchLabel = document.createElement("label");
    searchLabel.className = "rich-table-search";

    var searchText = document.createElement("span");
    searchText.className = "sr-only";
    searchText.textContent = "Search tickets";

    var search = document.createElement("input");
    search.type = "search";
    search.name = "ticket_search";
    search.autocomplete = "off";
    search.placeholder = "Search tickets";
    search.setAttribute("aria-label", "Search tickets");
    search.setAttribute("data-rich-table-search", "true");

    searchLabel.appendChild(searchText);
    searchLabel.appendChild(search);
    left.appendChild(searchLabel);

    var filterButton = document.createElement("button");
    filterButton.type = "button";
    filterButton.className = "rich-table-toolbar__button";
    filterButton.textContent = "Filter";
    filterButton.setAttribute("data-rich-table-filter", "true");
    filterButton.setAttribute("aria-expanded", "false");

    var filterMenu = document.createElement("div");
    filterMenu.className = "rich-table-menu rich-table-menu--filter";
    filterMenu.hidden = true;

    collectTicketStatuses(table).forEach(function (status) {
      var item = document.createElement("label");
      item.className = "rich-table-menu__item";

      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = status;
      checkbox.setAttribute("data-rich-table-status-filter", "true");

      var text = document.createElement("span");
      text.textContent = status;

      checkbox.addEventListener("change", function () {
        var selected = Array.from(filterMenu.querySelectorAll("[data-rich-table-status-filter]:checked")).map(function (node) {
          return node.value;
        });
        filterButton.classList.toggle("is-active", selected.length > 0);
        applyRichTableStatusFilters(table, selected);
        writeRichTableState(container, collectRichTableState(table, container));
      });

      item.appendChild(checkbox);
      item.appendChild(text);
      filterMenu.appendChild(item);
    });

    left.appendChild(filterButton);
    left.appendChild(filterMenu);

    var sortButton = document.createElement("button");
    sortButton.type = "button";
    sortButton.className = "rich-table-toolbar__button";
    sortButton.textContent = "Sort";
    sortButton.setAttribute("data-rich-table-sort", "true");
    sortButton.addEventListener("click", function () {
      var sorters = typeof table.getSorters === "function" ? table.getSorters() : [];
      var updatedSorter = sorters.find(function (sorter) {
        return sorter.field === "updated";
      });
      var direction = updatedSorter && updatedSorter.dir === "desc" ? "asc" : "desc";
      table.setSort("updated", direction);
      sortButton.classList.add("is-active");
      writeRichTableState(container, collectRichTableState(table, container));
    });
    left.appendChild(sortButton);

    var right = document.createElement("div");
    right.className = "rich-table-toolbar__group rich-table-toolbar__group--right";

    var propertiesButton = document.createElement("button");
    propertiesButton.type = "button";
    propertiesButton.className = "rich-table-toolbar__button";
    propertiesButton.textContent = "Properties";
    propertiesButton.setAttribute("data-rich-table-properties", "true");
    propertiesButton.setAttribute("aria-expanded", "false");

    var menu = document.createElement("div");
    menu.className = "rich-table-menu rich-table-menu--properties";
    menu.hidden = true;

    function rebuildMenu() {
      menu.innerHTML = "";
      table.getColumns().forEach(function (column) {
        var definition = column.getDefinition();
        if (!definition.field) {
          return;
        }

        var item = document.createElement("label");
        item.className = "rich-table-menu__item";

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = column.isVisible();
        checkbox.addEventListener("change", function () {
          if (checkbox.checked) {
            column.show();
          } else {
            column.hide();
          }
          writeRichTableState(container, collectRichTableState(table, container));
        });

        var text = document.createElement("span");
        text.textContent = definition.title;

        item.appendChild(checkbox);
        item.appendChild(text);
        menu.appendChild(item);
      });
    }

    search.addEventListener("input", function () {
      applyRichTableSearch(table, search.value);
      writeRichTableState(container, collectRichTableState(table, container));
    });

    filterButton.addEventListener("click", function () {
      var expanded = filterButton.getAttribute("aria-expanded") === "true";
      filterButton.setAttribute("aria-expanded", expanded ? "false" : "true");
      filterMenu.hidden = expanded;
    });

    propertiesButton.addEventListener("click", function () {
      var expanded = propertiesButton.getAttribute("aria-expanded") === "true";
      propertiesButton.setAttribute("aria-expanded", expanded ? "false" : "true");
      menu.hidden = expanded;
      if (!expanded) {
        rebuildMenu();
      }
    });

    document.addEventListener("click", function (event) {
      if (!toolbar.contains(event.target)) {
        filterButton.setAttribute("aria-expanded", "false");
        propertiesButton.setAttribute("aria-expanded", "false");
        filterMenu.hidden = true;
        menu.hidden = true;
      }
    });

    table.on("columnVisibilityChanged", rebuildMenu);
    table.on("columnMoved", rebuildMenu);

    right.appendChild(propertiesButton);
    right.appendChild(menu);
    toolbar.appendChild(left);
    toolbar.appendChild(right);
    var header = ensureRichTableHeader(parent, container);
    header.appendChild(toolbar);
  }

  function initializeRichTable(container, options) {
    var rows = collectTicketRows(container);
    if (!rows.length) {
      return null;
    }

    var isRestoring = true;
    var initialState = readRichTableState(container);
    var defaultPageSize = parseInt(container.getAttribute("data-rich-table-page-size") || "20", 10);
    if (!defaultPageSize || defaultPageSize < 1) {
      defaultPageSize = 20;
    }
    var fillHeight = container.getAttribute("data-rich-table-fill-height") === "true";
    var table = new Tabulator(container, {
      data: rows,
      layout: "fitDataTable",
      height: fillHeight ? "100%" : "460px",
      pagination: "local",
      paginationSize: initialState && initialState.pageSize ? initialState.pageSize : defaultPageSize,
      paginationSizeSelector: [20, 25, 50, 100],
      movableColumns: true,
      resizableColumns: true,
      placeholder: "No tickets matched the current view.",
      persistence: false,
      columns: buildTicketColumnsFromState(container, initialState)
    });

    if ((options && options.rowClick) === "drawer") {
      table.on("rowClick", function (event, row) {
        if (event.target.closest("[data-ticket-copy-key], .ticket-key-link")) {
          return;
        }
        openTicketDrawerFromData(row.getData(), row.getElement());
      });
    }

    table.on("tableBuilt", function () {
      isRestoring = true;
      window.setTimeout(function () {
        renderRichTableToolbar(container, table);
        renderRichTableViewTabs(container, table);
        setRichTableDensity(table, "compact");
        applyRichTableState(table, container);
        labelRichTableControls(container);
        window.setTimeout(function () {
          isRestoring = false;
        }, 80);
      }, 0);
    });

    function persistState() {
      if (isRestoring) {
        return;
      }
      writeRichTableState(container, collectRichTableState(table, container));
    }

    table.on("columnMoved", persistState);
    table.on("columnResized", persistState);
    table.on("columnVisibilityChanged", persistState);
    table.on("dataSorted", persistState);
    table.on("pageSizeChanged", persistState);

    return table;
  }

  document.addEventListener("click", function (event) {
    var copy = event.target.closest("[data-ticket-copy-key], [data-ticket-copy-active-key]");
    if (!copy) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    var key = copy.getAttribute("data-ticket-copy-key") || copy.getAttribute("data-ticket-copy-active-key");
    if (key && navigator.clipboard) {
      navigator.clipboard.writeText(key);
    }
  });

  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-ticket-drawer-tab]");
    if (!tab) {
      return;
    }

    var drawer = tab.closest("[data-ticket-drawer]");
    var target = tab.getAttribute("data-ticket-drawer-tab");
    if (!drawer || !target) {
      return;
    }

    drawer.querySelectorAll("[data-ticket-drawer-tab]").forEach(function (button) {
      button.classList.toggle("is-active", button === tab);
    });
    drawer.querySelectorAll("[data-ticket-drawer-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-ticket-drawer-panel") !== target;
    });
  });

  function initializeRichTables(scope) {
    if (!window.Tabulator) {
      return;
    }

    (scope || document).querySelectorAll("[data-rich-table]").forEach(function (container) {
      if (container.dataset.richTableInitialized === "true") {
        return;
      }

      if (container.getAttribute("data-rich-table-type") !== "tickets") {
        return;
      }

      var table = initializeRichTable(container, {
        rowClick: container.getAttribute("data-rich-table-row-click") || "drawer"
      });
      if (!table) {
        return;
      }

      container.dataset.richTableInitialized = "true";
      container._richTable = table;
    });
  }

  function initializeQueryResultsViewToggle(scope) {
    (scope || document)
      .querySelectorAll("[data-query-results-view-tab]")
      .forEach(function (button) {
        if (button.dataset.queryResultsToggleInitialized === "true") {
          return;
        }

        button.dataset.queryResultsToggleInitialized = "true";
        button.addEventListener("click", function () {
          var target = button.getAttribute("data-query-results-target") || "results";
          var container = button.closest(".query-workbench__results");
          if (!container) {
            return;
          }

          container
            .querySelectorAll("[data-query-results-view-tab]")
            .forEach(function (tab) {
              var isActive = tab === button;
              tab.classList.toggle("is-active", isActive);
              tab.setAttribute("aria-selected", isActive ? "true" : "false");
            });

          container
            .querySelectorAll("[data-query-results-panel]")
            .forEach(function (panel) {
              var isActive = panel.getAttribute("data-query-results-panel") === target;
              if (isActive) {
                panel.removeAttribute("hidden");
                panel.setAttribute("data-view-active", "true");
              } else {
                panel.setAttribute("hidden", "");
                panel.removeAttribute("data-view-active");
              }
            });

          container
            .querySelectorAll("[data-query-results-summary]")
            .forEach(function (summary) {
              summary.hidden = target !== "results";
            });
        });
      });
  }

  function closeTicketDrawer() {
    var drawer = document.querySelector("[data-ticket-drawer]");
    if (!drawer) {
      return;
    }

    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");

    if (lastTicketTrigger && typeof lastTicketTrigger.focus === "function") {
      lastTicketTrigger.focus();
    }
  }

  document.addEventListener("click", function (event) {
    var editorOpenTrigger = event.target.closest("[data-query-card-editor-open]");
    if (editorOpenTrigger && editorOpenTrigger.tagName !== "A") {
      event.preventDefault();
      openQueryCardEditor();
      return;
    }

    var editorCloseTrigger = event.target.closest("[data-query-card-editor-close]");
    if (editorCloseTrigger) {
      event.preventDefault();
      closeQueryCardEditor();
      return;
    }

    var closeTrigger = event.target.closest("[data-ticket-drawer-close]");
    if (closeTrigger) {
      event.preventDefault();
      closeTicketDrawer();
      return;
    }

    var ticketRow = event.target.closest("[data-ticket-row]");
    if (ticketRow) {
      if (event.target.closest(".ticket-key-link")) {
        return;
      }
      event.preventDefault();
      openTicketDrawer(ticketRow);
      return;
    }

    var trigger = event.target.closest("[data-partial-trigger]");
    if (!trigger) {
      return;
    }

    event.preventDefault();
    refreshPartial(trigger);
  });

  document.addEventListener("keydown", function (event) {
    var ticketRow =
      event.target && typeof event.target.closest === "function"
        ? event.target.closest("[data-ticket-row]")
        : null;
    if (ticketRow && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openTicketDrawer(ticketRow);
      return;
    }

    if (event.key === "Escape") {
      closeSettingsDrawer();
      closeTicketDrawer();
      closeQueryCardEditor();
    }
  });

  function initializeSyncDetailsToggle(scope) {
    (scope || document)
      .querySelectorAll("[data-sync-details-toggle]")
      .forEach(function (button) {
        if (button.dataset.syncDetailsInitialized === "true") {
          return;
        }

        button.dataset.syncDetailsInitialized = "true";
        button.addEventListener("click", function () {
          var target = button.getAttribute("data-sync-details-toggle");
          var container = button.closest(".sync-details");
          if (!container) {
            return;
          }

          container.querySelectorAll("[data-sync-details-toggle]").forEach(function (tab) {
            var active = tab === button;
            tab.classList.toggle("is-active", active);
            tab.setAttribute("aria-selected", active ? "true" : "false");
          });

          container.querySelectorAll("[data-sync-details-panel]").forEach(function (panel) {
            var active = panel.getAttribute("data-sync-details-panel") === target;
            if (active) {
              panel.removeAttribute("hidden");
            } else {
              panel.setAttribute("hidden", "");
            }
          });
        });
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initializeThemeSwitcher();
    initializeSettingsDrawer();
    initializeNavCollapse();
    initializeSidebarResize();
    initializeQueryCardColumnEditors(document);
    markActiveNav();
    stampRailPlaceholders();
    initializeRichTables(document);
    initializeQueryResultsViewToggle(document);
    initializeSyncDetailsToggle(document);
    initializeLiveUpdates();
    initializeSyncRefresh();
  });
})();
