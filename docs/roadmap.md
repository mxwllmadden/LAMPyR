# LAMPyR roadmap

Planned future features are listed here. These items are not yet implemented, and no delivery dates are committed.

## Flexible input prompts

Add a shared input-prompt interface supporting:

- **Choice input** — select from a supplied set of options.
- **Numerical input** — enter integer or floating-point values.
- **Text input** — enter arbitrary text.

The interface should work in both the CLI and `lampyr go`, allowing rig configuration, calibration, and other routines to request the appropriate input type through their supplied input function.

Currently, `lampyr go` routes input-function calls to a floating-point numpad. The planned interface will replace that restriction with prompt-specific controls while retaining blocking input behavior in worker threads.
