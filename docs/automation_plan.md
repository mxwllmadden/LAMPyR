# Automation Rig — Plan & Status

Status: **rig setup refactor complete** — `RigManager` is now generic, so rigs
other than `BanditRig` (e.g. `NullRig`, `AutomationRig`) can be connected.
**116 tests passing.**

---

## Accomplished

### Coordination / locking
- `AbstractService` base class + rig service wiring (`services`, `register_service`,
  `start`/`stop`/`disconnect`).
- `AutomationCoordinationService` (`lampyr/rigs/services.py`) — lease/gate/renewal
  machinery with a shared acquisition gate and background renewal thread.
- `JobReservation` — thin component facade over the coordination service
  (`acquire_colony` / `acquire_session` / `acquire_arbitrary`).
- `SessionJobTracker` — colony discovery + `candidate_sessions(jobs)` filtering
  (version-aware) + `mark_completed(jobid, version, session_id)`.

### Config
- `Config` / `ConfigFile` accept `sync=False` (read-only, in-memory).
- `Config.readonly_copy()` for non-syncing snapshots.
- `Config.rigconfig` — live alias for the nested `rig.configuration` dict
  (the home for all rig-specific data).

### Rig model / setup
- `NullRig` (new default rig type) in `lampyr/rigs/abstract.py`.
- `lampyr rig select` (list + choose rig) and `lampyr rig rename`
  (name defaults to the computer hostname).
- Per-rig `CONFIGURATION` / `CALIBRATION` class declarations with
  `is_configured(config)` / `is_calibrated(config)`.
  - `BanditRig`: `handedness` (1 / -1) + `sipper_calib` (`{size, calibrated_at}`)
    with a 5-day freshness window.
- Removed the old flat flags: `rig.configured`, `rig.calibrated`,
  `rig.sipper_calib`, `rig.handedness`, `rig_type_last_load`,
  `rig_type_last_calibration`.
- Calibration moved into `BanditRig.calibrate(_input_func, _output_func)`;
  `RigManager.connect()` no longer assumes a `reward` component;
  `RigManager.calibrate()` is now a thin connect → `rig.calibrate(...)` →
  disconnect wrapper. I/O functions are passed directly, not stored.

---

## Remaining

1. **Make `AutomationRig` discoverable**
   - It is not imported anywhere, so `all_rig_definitions()` / `rig select`
     cannot see it. Add one import in a central place (e.g. `hardware.py`).

2. **Test the automation rig (smoke test)**
   - Exercise `RigManager.connect()` / `calibrate()` / `is_configured` /
     `is_calibrated` against `NullRig` and `AutomationRig`.

3. **Finish `AutomationSegment.execute()`**
   - Still a stub (`lampyr/segments/automation.py`). Define the automation
     contract: discover candidates → run each job → `mark_completed`.

4. **`AUTOMOUSE` → `AUTOMATION`**
   - The scheduler / TUI still uses the old `AUTOMOUSE` sentinel identity.

---

## Key files
- `lampyr/rigs/abstract.py` — `AbstractHardwareRig`, `AbstractService`, `NullRig`
- `lampyr/rigs/services.py` — `AutomationCoordinationService`, `Lease`
- `lampyr/rigs/automationrig.py` — `AutomationRig`, `JobReservation`, `SessionJobTracker`
- `lampyr/rigs/banditrig.py` — `BanditRig` (CONFIGURATION/CALIBRATION, calibrate)
- `lampyr/managers/hardware.py` — `RigManager` (generic connect/calibrate)
- `lampyr/config.py` — `sync=False`, `readonly_copy`, `rigconfig`
- `lampyr/actions.py` — `start_rig`, `configure_rig`, `select_rig`, `rename_rig`
- `lampyr/ui/click_cli/app.py` — `rig select` / `rig rename`
- `lampyr/ui/textual_tui/app.py` — run/calibration/heartbeat checks
- `lampyr/segments/automation.py` — `AutomationSegment` (to finish)
