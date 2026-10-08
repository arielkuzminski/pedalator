-- Pedalator for OpenMW: the character walks as fast as the rider pedals (smart trainer + Zwift Click via the Pedalator bridge).
--
--   PC -> game : the bridge rewrites  pedalator/state.txt  (a data file of this mod) ~20 times a second:
--                  n=<counter>;move=<0..1>;turn=<-1|0|1>;look=<-1|0|1>;atk=<0|1>;jump=<0|1>;draw=<0|1>;power=<watts>;diff=<percent>
--                this script reads it with vfs.open (read only)
--                (turn: right is +1; look: down is +1; draw: toggles the drawn weapon on each press)
--                "use" (open / take / talk) is a key the bridge presses in the game window, not handled here
--   game -> PC : "PEDALATOR grade=<percent>" lines in openmw.log (the bridge reads the end of the log)
--
-- With no fresh state (bridge not running) the normal keyboard controls are left alone.

local core = require('openmw.core')
local self = require('openmw.self')
local vfs = require('openmw.vfs')
local input = require('openmw.input')
local types = require('openmw.types')
local async = require('openmw.async')
local ui = require('openmw.ui')
local I = require('openmw.interfaces')

local Actor = types.Actor
local Player = types.Player

-- ---- settings -------------------------------------------------------------------------------
local STATE_FILE = 'pedalator/state.txt'
local STALE_AFTER = 1.0        -- s without a new counter value: the bridge is gone, give the controls back
local READ_EVERY = 0.04        -- s between reads of the state file
local TURN_RATE = 1.7          -- rad/s at full lock (about 100 degrees a second)
local PITCH_RATE = 1.2         -- rad/s looking up / down
local RUN_ABOVE = 0.55         -- move above this runs, below it walks
local MIN_MOVE = 0.05          -- below this the character stands
-- Morrowind's walking speed depends on the Speed attribute. If the analog movement value turns out not to
-- scale the speed, set this to true: the script then adds up to SPEED_BOOST to Speed in proportion to move.
local USE_SPEED_ATTRIBUTE = false
local SPEED_BOOST = 60
local GRADE_EVERY = 0.25       -- s between "PEDALATOR grade=" lines
local GRADE_MIN_DIST = 100     -- game units (~1.4 m) travelled before a new gradient sample
local GRADE_SMOOTH = 0.3
local DEBUG = false            -- also print what was read (every 2 s)

-- ---- state ----------------------------------------------------------------------------------
local st = { n = -1, move = 0, turn = 0, look = 0, atk = 0, jump = 0, draw = 0, power = 0, diff = nil }
local shownDiff = nil
local lastN, lastChange = nil, 0
local sinceRead, sinceGrade, sinceDebug = 0, 0, 0
local movementOverridden, combatOverridden = false, false
local appliedSpeed = 0
local gx, gy, gz, grade = nil, nil, nil, 0.0
local readErrors = 0
local lastDraw, lastAtk = 0, 0

local function parse(txt)
    local t = {}
    for k, v in string.gmatch(txt, '(%w+)=([%-%d%.eE]+)') do t[k] = tonumber(v) end
    return t
end

local function readState()
    local f, msg = vfs.open(STATE_FILE)
    if not f then
        readErrors = readErrors + 1
        if readErrors == 1 then print('PEDALATOR cannot open ' .. STATE_FILE .. ': ' .. tostring(msg)) end
        return false
    end
    local txt = f:read('*a')
    f:close()
    if not txt or txt == '' then return false end      -- caught mid-write: keep the last values
    local t = parse(txt)
    if t.n == nil or t.move == nil then return false end
    st = {
        n = t.n, move = math.max(0, math.min(1, t.move)), turn = t.turn or 0, look = t.look or 0,
        atk = t.atk or 0, jump = t.jump or 0, draw = t.draw or 0, power = t.power or 0, diff = t.diff,
    }
    return true
end

local function setSpeedBoost(boost)
    local speed = Actor.stats.attributes.speed(self)
    speed.modifier = speed.modifier - appliedSpeed + boost
    appliedSpeed = boost
end

local function release()
    if movementOverridden then
        I.Controls.overrideMovementControls(false)
        movementOverridden = false
    end
    if combatOverridden then
        I.Controls.overrideCombatControls(false)
        combatOverridden = false
    end
    if appliedSpeed ~= 0 then setSpeedBoost(0) end
end

-- the same as the game's own ToggleWeapon / ToggleSpell (those are switched off while we hold the combat controls)
local function toggleWeapon()
    if Actor.getStance(self) == Actor.STANCE.Weapon then
        Actor.setStance(self, Actor.STANCE.Nothing)
    elseif Player.getControlSwitch(self, Player.CONTROL_SWITCH.Fighting) then
        Actor.setStance(self, Actor.STANCE.Weapon)
    end
end
local function toggleSpell()
    if Actor.getStance(self) == Actor.STANCE.Spell then
        Actor.setStance(self, Actor.STANCE.Nothing)
    elseif Player.getControlSwitch(self, Player.CONTROL_SWITCH.Magic) then
        Actor.setStance(self, Actor.STANCE.Spell)
    end
end
-- the keyboard keys keep working while the bridge holds the combat controls
for trigger, fn in pairs({ ToggleWeapon = toggleWeapon, ToggleSpell = toggleSpell }) do
    local ok, err = pcall(input.registerTriggerHandler, trigger, async:callback(function()
        if combatOverridden and not core.isWorldPaused() and not I.UI.getMode() then fn() end
    end))
    if not ok then print('PEDALATOR cannot hook ' .. trigger .. ': ' .. tostring(err)) end
end

local function sampleGrade()
    local p = self.object.position
    if not gx then gx, gy, gz = p.x, p.y, p.z return end
    local dx, dy = p.x - gx, p.y - gy
    local d = math.sqrt(dx * dx + dy * dy)
    if d >= GRADE_MIN_DIST then
        local g = (p.z - gz) / d * 100.0
        g = math.max(-15.0, math.min(15.0, g))
        grade = grade + (g - grade) * GRADE_SMOOTH
        gx, gy, gz = p.x, p.y, p.z
    end
end

local function onFrame(dt)
    -- ---- the gradient goes out through the log, in every state of the game ----
    sinceGrade = sinceGrade + dt
    if sinceGrade >= GRADE_EVERY then
        sinceGrade = 0
        sampleGrade()
        print(string.format('PEDALATOR grade=%.2f', grade))
    end

    -- ---- the state file ----
    local now = core.getRealTime()
    sinceRead = sinceRead + dt
    if sinceRead >= READ_EVERY then
        sinceRead = 0
        if readState() and st.n ~= lastN then
            lastN, lastChange = st.n, now
        end
    end
    if DEBUG then
        sinceDebug = sinceDebug + dt
        if sinceDebug >= 2 then
            sinceDebug = 0
            print(string.format('PEDALATOR dbg n=%s move=%.2f turn=%s look=%s atk=%s jump=%s draw=%s power=%s age=%.1f',
                tostring(st.n), st.move, tostring(st.turn), tostring(st.look), tostring(st.atk), tostring(st.jump),
                tostring(st.draw), tostring(st.power), now - lastChange))
        end
    end

    local fresh = lastN ~= nil and (now - lastChange) < STALE_AFTER
    if not fresh then release() return end

    -- Click + / - changed how much of the hills the trainer simulates: say so
    if st.diff and shownDiff and st.diff ~= shownDiff then
        ui.showMessage(string.format('Pedalator: hills felt %d %%', st.diff))
    end
    shownDiff = st.diff

    -- a menu, a dialogue or a paused world: the player has the controls, the character stands still
    if core.isWorldPaused() or I.UI.getMode() then
        if movementOverridden then
            self.controls.movement = 0
            self.controls.sideMovement = 0
            self.controls.jump = false
        end
        if combatOverridden then self.controls.use = self.ATTACK_TYPE.NoAttack end
        lastDraw, lastAtk = st.draw, st.atk
        return
    end

    if not movementOverridden then
        I.Controls.overrideMovementControls(true)
        movementOverridden = true
    end
    if not combatOverridden then
        I.Controls.overrideCombatControls(true)
        combatOverridden = true
    end

    -- ---- walking, turning, looking, jumping ----
    local move = st.move < MIN_MOVE and 0 or st.move
    self.controls.sideMovement = 0
    self.controls.movement = move
    self.controls.run = move > RUN_ABOVE
    self.controls.jump = st.jump ~= 0
    self.controls.yawChange = st.turn * TURN_RATE * dt
    self.controls.pitchChange = st.look * PITCH_RATE * dt
    if USE_SPEED_ATTRIBUTE then setSpeedBoost(SPEED_BOOST * move) end

    -- ---- the weapon: one press draws or sheathes it ----
    if st.draw ~= 0 and lastDraw == 0 then toggleWeapon() end
    lastDraw = st.draw

    -- ---- attacking: the button or the game's own "Use" (the mouse); held = a charged blow, released = the strike ----
    local pressed = st.atk ~= 0 or input.getBooleanActionValue('Use')
    local stance = Actor.getStance(self)
    if stance == Actor.STANCE.Weapon then
        self.controls.use = pressed and self.ATTACK_TYPE.Any or self.ATTACK_TYPE.NoAttack
    elseif stance == Actor.STANCE.Spell then
        -- a spell is cast once per press
        self.controls.use = (pressed and lastAtk == 0) and self.ATTACK_TYPE.Any or self.ATTACK_TYPE.NoAttack
    else
        self.controls.use = self.ATTACK_TYPE.NoAttack
    end
    lastAtk = pressed and 1 or 0
end

return {
    engineHandlers = {
        onFrame = onFrame,
        onLoad = function() appliedSpeed = 0 end,
        onSave = function() release() return nil end,
    },
}
