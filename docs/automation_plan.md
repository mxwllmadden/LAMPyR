# Automation Rig — Plan & Status

Status: **rig setup refactor complete** — `RigManager` is generic, and both
`NullRig` and `AutomationRig` have manager-level connect/calibrate smoke tests.
The full test suite passes (**146 tests**).

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
- `AutomationRig` is imported for rig discovery. Manager-level smoke tests cover
  discovery, configuration/calibration checks, connect, calibrate, and disconnect
  for both `NullRig` and `AutomationRig`.

---

## Remaining

1. **Define and implement job execution in `AutomationSegment.execute()`**
   - It currently classifies jobs but does not instantiate or execute them.
   - Define how jobs receive session/colony data and return or persist analysis
     results; call `mark_completed` only after successful execution.

2. **Finish job-scope semantics**
   - Session jobs have versioned completion markers and reservation filtering.
   - Colony jobs currently have no durable completion tracking and may be yielded
     again on a later pass. Decide how they complete/retry.
   - Arbitrary jobs are classified but not executed; implement them or explicitly
     defer/remove the scope.

3. **Exercise the scheduled automation path end to end**
   - Verify the TUI selects the correct rig type and data context for analysis
     jobs, and that failures/aborts do not leave stale reservations or completion
     markers.

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
