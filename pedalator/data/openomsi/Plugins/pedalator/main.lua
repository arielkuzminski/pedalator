-- Pedalator plugin for openOMSI: computes the road gradient from the vehicle's position and sends it over UDP
-- (127.0.0.1:27100) to the Pedalator bridge, which sets the trainer's resistance from it.
local PORT = 27100
local MIN_DIST = 4.0         -- metres travelled before a new gradient sample
local SMOOTH = 0.3           -- exponential smoothing factor
local MAX_GRADE = 15.0       -- smart trainers simulate up to about 15 %
local SHOW_GRADE = true      -- show the gradient on screen every 2 s
local DEBUG = false          -- log the bike's script variables once a second ("[lua pedalator] dbg ...")

local last_x, last_y, last_z
local grade = 0.0

local function sample()
  local x, y, z = omsi.position()
  if not x then last_x = nil; return end
  if last_x then
    local dx, dy = x - last_x, y - last_y
    local d = math.sqrt(dx * dx + dy * dy)
    if d >= MIN_DIST then
      local g = (z - last_z) / d * 100.0
      g = math.max(-MAX_GRADE, math.min(MAX_GRADE, g))
      grade = grade + (g - grade) * SMOOTH
      last_x, last_y, last_z = x, y, z
    end
  else
    last_x, last_y, last_z = x, y, z
  end
end

omsi.every(0.1, sample)

omsi.every(0.25, function()
  omsi.send(PORT, string.format("grade=%.2f;speed=%.1f", grade, omsi.speed() or 0))
end)

if SHOW_GRADE then
  omsi.every(2.0, function()
    omsi.message(string.format("Grade: %.1f %%", grade), 1.5)
  end)
end

-- Rider power from the bridge (UDP 27101, "power=NNN"): needs an openOMSI build with omsi.receive
-- (see engine-patch/). Without it the bike's script reads the throttle key instead.
local POWER_PORT = 27101
local power = 0
if omsi.receive then
  omsi.every(0.1, function()
    local msgs = omsi.receive(POWER_PORT)
    if msgs and #msgs > 0 then
      local p = tonumber(msgs[#msgs]:match("power=([%d%.]+)"))
      if p then power = p end
    end
    omsi.set_var("Trainer_Power", power)
  end)
end

omsi.log("pedalator plugin started" .. (omsi.receive and " (power input on)" or ""))

if DEBUG then
  local VARS = { "Throttle", "Brake", "Clutch", "Gear", "M_Wheel", "Brakeforce", "P_rider",
                 "v_ms", "Velocity", "Trainer_Power", "n_Wheel" }
  omsi.every(1.0, function()
    local t = {}
    for _, n in ipairs(VARS) do
      t[#t + 1] = string.format("%s=%s", n, tostring(omsi.var(n)))
    end
    omsi.log("dbg " .. table.concat(t, " "))
  end)
end
