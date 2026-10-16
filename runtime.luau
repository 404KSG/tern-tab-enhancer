-- Initialized after the tiny window bootstrap yields between module loads.
local M = {}
function M.start(tern, Model, Presentation)
    local POLL_MS, MIN_REFRESH_MS = 500, 150
    local model = Model.new(tern.kv.get("pane-state"))
    local previous_css, previous_records = nil, Model.fingerprint(model)
    local queued, heartbeat = nil, nil
    local last_refresh = -1000000

    local function enabled()
        return tern.kv.get("enabled") ~= false
    end
    local function apply(css)
        if css ~= previous_css then
            tern.css("tabs", css)
            previous_css = css
        end
    end
    local function save()
        local signature = Model.fingerprint(model)
        if signature ~= previous_records then
            tern.kv.set("pane-state", model.records)
            previous_records = signature
        end
    end
    local function native_aliases(cx)
        local result = {}
        for _, exact in ipairs(tern.kv.get("native-panes") or {}) do
            local pane = cx.session:pane(exact)
            if pane then result[Model.key(pane.pane)] = exact end
        end
        return result
    end
    local function refresh(cx)
        last_refresh = tern.now()
        if not enabled() then apply(""); return end
        local panes = cx.session:panes()
        local has_agents = false
        for _, pane in ipairs(panes) do
            if pane.kind == "agent" then has_agents = true; break end
        end
        -- Ordinary shell Pi comes from the lifecycle bridge, never a shell busy guess.
        local native_agents = if has_agents then cx.agents:list() else {}
        local aliases = native_aliases(cx)
        local agents = Model.with_bridges(panes, native_agents, aliases, tern.kv.get("bridge-states") or {})
        local tabs = Model.update(model, panes, agents, aliases)
        save()
        apply(Presentation.render(tabs))
    end
    local tick
    local function start_heartbeat()
        if heartbeat then heartbeat:cancel() end
        heartbeat = tern.timer(POLL_MS, tick)
    end
    tick = function(cx)
        heartbeat = nil
        if cx then refresh(cx); start_heartbeat() end
    end
    local function request()
        if queued then return end
        if heartbeat then heartbeat:cancel(); heartbeat = nil end
        local delay = math.max(20, MIN_REFRESH_MS - (tern.now() - last_refresh))
        queued = tern.timer(delay, function(cx)
            queued = nil
            if cx then refresh(cx); start_heartbeat() end
        end)
    end
    tern.on("focus", function(event)
        Model.focus(model, event.pane)
        save()
        request()
    end)
    tern.on("agent_finished", function(event, cx)
        Model.finished(model, event.pane, event.result, cx.session:focused())
        save()
        request()
    end)
    tern.on("pane_closed", function(event)
        Model.finished(model, event.pane, "closed", nil)
        save()
        request()
    end)
    for _, event in ipairs({"pane_created", "tab_created", "tab_closed", "command_started", "command_finished", "title", "cwd"}) do
        tern.on(event, request)
    end
    tern.command({id = "pause", title = "暂停标签增强", run = function()
        tern.kv.set("enabled", false)
        apply("")
    end})
    tern.command({id = "resume", title = "恢复标签增强", run = function(cx)
        tern.kv.set("enabled", true)
        refresh(cx)
        start_heartbeat()
    end})
    tern.command({id = "refresh", title = "刷新标签状态", run = function(cx)
        refresh(cx)
    end})
    request()
end
return M
