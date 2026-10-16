-- Initialized after the tiny window bootstrap yields between module loads.
local M = {}
function M.start(tern, Model, Presentation)
    local POLL_MS, MIN_REFRESH_MS = 500, 150
    local model, legacy_loaded = Model.new(), false
    local previous_css, saved_signatures = nil, {}
    local aliases_cache = {}
    local queued, heartbeat = nil, nil
    local last_refresh = -1000000
    local failures, last_error, last_focused = 0, nil, nil

    local function enabled()
        return tern.kv.get("enabled") ~= false
    end
    local function apply(css)
        if css ~= previous_css then
            tern.css("tabs", css)
            previous_css = css
        end
    end
    local function record_key(id)
        return aliases_cache[id] or id
    end
    local function ack_key(id, record)
        return "read:" .. record_key(id) .. ":" .. (record.generation or "native:0")
    end
    local function acknowledge()
        for id, record in pairs(model.records) do
            if tern.kv.get(ack_key(id,record)) == true then record.read = true end
        end
    end
    local function save()
        for id, record in pairs(model.records) do
            local signature = Model.fingerprint({records={[id]=record}})
            if signature ~= saved_signatures[id] then
                -- Same-generation read receipts only ever go false -> true.
                if record.read then
                    tern.kv.set(ack_key(id,record),true)
                    local history_key = "read-generations:" .. record_key(id)
                    local history = tern.kv.get(history_key) or {}
                    if not table.find(history,record.generation) then
                        table.insert(history,record.generation)
                        while #history > 8 do
                            local expired = table.remove(history,1)
                            tern.kv.set("read:" .. record_key(id) .. ":" .. expired,nil)
                        end
                        tern.kv.set(history_key,history)
                    end
                end
                tern.kv.set("state:" .. record_key(id), record)
                saved_signatures[id] = signature
            end
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
    local function refresh(cx, viewed_pane)
        last_refresh = tern.now()
        last_focused = cx.session:focused()
        if not enabled() then apply(""); return end
        if not legacy_loaded then
            Model.merge(model, tern.kv.get("pane-state") or {})
            legacy_loaded = true
        end
        local panes = cx.session:panes()
        local has_agents = false
        for _, pane in ipairs(panes) do
            if pane.kind == "agent" then has_agents = true; break end
        end
        -- Ordinary shell Pi comes from the lifecycle bridge, never a shell busy guess.
        local native_agents = if has_agents then cx.agents:list() else {}
        local aliases = native_aliases(cx)
        aliases_cache = aliases
        local shared = {}
        for _, pane in ipairs(panes) do
            local id = Model.key(pane.pane)
            local saved = tern.kv.get("state:" .. record_key(id))
            if saved then shared[id] = saved end
        end
        Model.merge(model, shared)
        local reports = tern.kv.get("bridge-states") or {}
        if viewed_pane then
            for _, pane in ipairs(panes) do
                if pane.pane == viewed_pane then
                    local id = aliases[Model.key(viewed_pane)] or Model.key(viewed_pane)
                    local path = tern.plugin.data .. "/bridge/" .. id .. ".json"
                    -- Read the outgoing pane at the focus boundary, not from the
                    -- Host's older 500ms cache. This is bounded metadata, no chat.
                    if tern.fs.exists(path) then
                        local ok, report
                        for _=1,2 do
                            ok, report = pcall(function() return tern.json.decode(tern.fs.read(path,4096)) end)
                            if ok then break end
                        end
                        if not ok then error("Focus checkpoint read failed: " .. tostring(report)) end
                        if type(report)=="table" and report.schema==1 and report.pane==id
                            and type(report.generation)=="string" and #report.generation<=96
                            and string.match(report.generation,"^[%w%-]+:%d+$")
                            and (report.state=="done" or report.state=="idle" or report.state=="working" or report.state=="waiting") then
                            reports[id] = {state=report.state,generation=report.generation}
                        end
                    end
                    pane.focused = true
                end
            end
        end
        local agents = Model.with_bridges(panes, native_agents, aliases, reports)
        Model.update(model, panes, agents, aliases)
        acknowledge()
        local tabs = Model.update(model, panes, agents, aliases)
        save()
        apply(Presentation.render(tabs))
    end
    local function protect(fn)
        local ok, err = pcall(fn)
        if not ok then
            failures += 1
            last_error = string.sub(tostring(err), 1, 240)
            if failures == 1 then
                tern.log.warn("Tab status refresh failed; retrying", last_error)
                pcall(function() tern.css("health", "#sidebar .tn-dk-c::after,#tabbar .tn-dk-c::after{opacity:0.35 !important;}") end)
            end
        end
        return ok
    end
    local function safe_refresh(cx, viewed_pane)
        local ok = protect(function()
            refresh(cx, viewed_pane)
            if failures > 0 then tern.css("health", "") end
        end)
        if ok then failures, last_error = 0, nil end
        return ok
    end
    local function interval()
        return math.min(8000, POLL_MS * 2 ^ math.min(failures, 4))
    end
    local tick
    local function start_heartbeat()
        if heartbeat then heartbeat:cancel() end
        heartbeat = tern.timer(interval(), tick)
    end
    tick = function(cx)
        heartbeat = nil
        if cx then safe_refresh(cx); start_heartbeat() end
    end
    local function request()
        if queued then return end
        if heartbeat then heartbeat:cancel(); heartbeat = nil end
        local delay = math.max(if failures > 0 then interval() else 20, MIN_REFRESH_MS - (tern.now() - last_refresh))
        queued = tern.timer(delay, function(cx)
            queued = nil
            if cx then safe_refresh(cx); start_heartbeat() end
        end)
    end
    tern.on("focus", function(event, cx)
        local previous = last_focused
        last_focused = event.pane
        if not safe_refresh(cx, previous) then
            pcall(function() cx:toast("warn", "离开标签时未能确认最新状态", "已保守保留未读；返回该标签可确认。") end)
        end
        protect(function() Model.focus(model, event.pane); save() end)
        request()
    end)
    tern.on("agent_finished", function(event, cx)
        protect(function() Model.finished(model, event.pane, event.result, cx.session:focused()); save() end)
        request()
    end)
    tern.on("pane_closed", function(event)
        protect(function()
            local id = Model.key(event.pane)
            Model.finished(model, event.pane, "closed", nil)
            tern.kv.set("state:" .. record_key(id),nil)
            local history_key = "read-generations:" .. record_key(id)
            for _, generation in ipairs(tern.kv.get(history_key) or {}) do
                tern.kv.set("read:" .. record_key(id) .. ":" .. generation,nil)
            end
            tern.kv.set(history_key,nil)
            saved_signatures[id] = nil
            save()
        end)
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
        safe_refresh(cx)
        start_heartbeat()
    end})
    tern.command({id = "refresh", title = "刷新标签状态", run = function(cx)
        safe_refresh(cx)
        start_heartbeat()
    end})
    tern.command({id = "health", title = "查看标签状态健康", run = function(cx)
        cx:toast(if failures > 0 then "warn" else "info", if failures > 0 then "状态读取异常，正在重试" else "标签状态刷新正常", last_error)
    end})
    request()
end
return M
