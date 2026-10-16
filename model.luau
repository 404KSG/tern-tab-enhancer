-- State and unread semantics follow tty7's agent_row / agent_unread_count.
-- Native idle after a completed turn remains Done until the next turn starts.
local M = {}
local rank = {idle = 0, done = 1, working = 2, waiting = 3}
local function key(value)
    return string.format("%.0f", value)
end
M.key = key

function M.new(saved)
    local records = {}
    for id, record in pairs(saved or {}) do
        records[id] = {done = record.done == true, read = record.read == true, status = record.status or "idle", generation = record.generation}
    end
    return {records = records}
end

function M.finished(self, pane, result, focused)
    local id = key(pane)
    if result == "closed" then
        self.records[id] = nil
        return
    end
    local previous = self.records[id]
    self.records[id] = {done = true, read = (previous and previous.generation and previous.done and previous.read) or pane == focused, status = "done", generation = previous and previous.generation}
end

function M.focus(self, pane)
    local record = self.records[key(pane)]
    if record and record.done then record.read = true end
end

function M.update(self, panes, agents, aliases)
    local pane_by_id, live, tabs = {}, {}, {}
    for _, pane in ipairs(panes) do pane_by_id[key(pane.pane)] = pane end
    for _, agent in ipairs(agents) do
        local id = key(agent.pane)
        local pane = pane_by_id[id]
        if pane and pane.tab and pane.parked ~= true then
            live[id] = true
            local record = self.records[id]
            if not record then
                record = {done = false, read = false, status = "idle"}
                -- Import native attention on first load without importing transcript text.
                if agent.state == "idle" and pane.alert == true then record.done = true end
                self.records[id] = record
            end
            local previous = record.status
            if agent.generation and record.generation ~= agent.generation then
                record.generation = agent.generation
                record.done, record.read, record.status = false, false, "idle"
            end
            if agent.phase == "done" then
                if not record.done then record.read = pane.focused == true end
                record.done, record.status = true, "done"
            elseif agent.phase == "idle" then
                record.status, record.done, record.read = "idle", false, false
            elseif agent.phase == "waiting" then
                -- An idle dialog can interrupt an already-read result in the
                -- same generation; closing it must not create another unread.
                record.status = "waiting"
            elseif agent.state == "working" then
                record.status, record.done, record.read = "working", false, false
            elseif agent.state == "waiting_input" then
                record.status, record.done, record.read = "waiting", false, false
            else
                if previous == "working" or previous == "waiting" or agent.state == "exited" then
                    if not record.done then record.read = pane.focused == true end
                    record.done = true
                end
                record.status = if record.done then "done" else "idle"
            end
            if record.done and pane.focused == true then record.read = true end
            local tab_id = key(pane.tab)
            local tab = tabs[tab_id]
            if not tab then
                tab = {id = pane.tab, state = "idle", unread = 0, agents = 0, selectors = {}}
                tabs[tab_id] = tab
            end
            tab.agents += 1
            if rank[record.status] > rank[tab.state] then tab.state = record.status end
            if record.done and not record.read then tab.unread += 1 end
        end
    end
    -- A tab may display only three of many panes. Match every pane, including
    -- non-agent panes, so reordering or focusing a shell cannot detach its badge.
    for _, pane in ipairs(panes) do
        local tab = pane.tab and tabs[key(pane.tab)]
        if tab then
            local id = key(pane.pane)
            table.insert(tab.selectors, (aliases and aliases[id]) or id)
        end
    end
    for id in pairs(self.records) do
        if not live[id] then self.records[id] = nil end
    end
    local output = {}
    for _, tab in pairs(tabs) do
        table.sort(tab.selectors)
        tab.count = if tab.state == "done" then tab.unread else 0
        tab.label = if tab.count > 0 then tostring(math.min(9, tab.count)) else ""
        table.insert(output, tab)
    end
    table.sort(output, function(a, b) return a.id < b.id end)
    return output
end

function M.fingerprint(self)
    local rows = {}
    for id, record in pairs(self.records) do
        table.insert(rows, id .. ":" .. tostring(record.done) .. ":" .. tostring(record.read) .. ":" .. record.status .. ":" .. tostring(record.generation))
    end
    table.sort(rows)
    return table.concat(rows, "|")
end

-- Adapt the optional Pi bridge without guessing from a shell's lifetime busy bit.
function M.with_bridges(panes, native_agents, aliases, reports)
    local result, indices = {}, {}
    for _, agent in ipairs(native_agents) do
        indices[key(agent.pane)] = #result + 1
        table.insert(result, {pane=agent.pane,state=agent.state})
    end
    for _, pane in ipairs(panes) do
        local id = key(pane.pane)
        local report = reports[(aliases and aliases[id]) or id]
        if report and pane.parked ~= true then
            local state = if report.state == "working" then "working" elseif report.state == "waiting" then "waiting_input" else "idle"
            local value = {pane=pane.pane,state=state,phase=report.state,generation=report.generation}
            local index = indices[id]
            if index then result[index] = value else table.insert(result,value) end
        end
    end
    return result
end

return M
