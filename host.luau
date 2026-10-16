-- Complete native pane IDs plus a bounded local bridge for ordinary Pi panes.
local last_signature, bridge_signature = nil, nil
local observed = {}
local last_bridge_read = -1000000
local phases = {idle=true,working=true,waiting=true,done=true}
local function read_bridges(ids)
    local now = tern.now()
    if now - last_bridge_read < 150 then return end
    last_bridge_read = now
    local reports, signature, live = {}, {}, {}
    for _, id in ipairs(ids) do
        live[id] = true
        local path = tern.plugin.data .. "/bridge/" .. id .. ".json"
        local ok, value = pcall(function()
            if not tern.fs.exists(path) then return nil end
            return tern.json.decode(tern.fs.read(path, 4096))
        end)
        if ok and type(value) == "table" and value.schema == 1 and value.pane == id
            and phases[value.state] and type(value.generation) == "string"
            and #value.generation <= 96 and string.match(value.generation, "^[%w%-]+:%d+$")
            and type(value.sequence) == "number" and value.sequence > 0 then
            local previous = observed[id]
            if not previous or previous.sequence ~= value.sequence or previous.generation ~= value.generation then
                previous = {sequence=value.sequence,generation=value.generation,seen=now}
                observed[id] = previous
            end
            -- A crashed or killed Pi stops heartbeats; do not leave a working dot forever.
            if now - previous.seen < 15000 then
                reports[id] = {state=value.state,generation=value.generation}
                table.insert(signature, id .. ":" .. value.state .. ":" .. value.generation)
            end
        else
            observed[id] = nil
        end
    end
    for id in pairs(observed) do if not live[id] then observed[id] = nil end end
    table.sort(signature)
    local current = table.concat(signature, "|")
    if current ~= bridge_signature then
        tern.kv.set("bridge-states", reports)
        bridge_signature = current
    end
end
local function publish()
    local ids = {}
    for _, pane in ipairs(tern.pane.list()) do
        table.insert(ids, string.format("%.0f", pane.pane))
    end
    table.sort(ids)
    local signature = table.concat(ids, ",")
    if signature ~= last_signature then
        tern.kv.set("native-panes", ids)
        last_signature = signature
        last_bridge_read = -1000000
    end
    read_bridges(ids)
end
local function poll()
    publish()
    tern.timer(500, poll)
end
for _, event in ipairs({"command_started", "command_finished", "cwd", "title", "pane_exited"}) do
    tern.on(event, publish)
end
poll()
