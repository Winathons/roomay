# roomay

A Workpeg peg: a UI and a function, described by one manifest.

```
workpeg.json     the manifest — namespace, function entrypoint, runtime
ui/              the interface (workpeg ui serve ui/)
function/        the backend  (workpeg run function/)
```

## Working on it

```bash
workpeg ui serve ui/          # live-reload the UI on localhost
workpeg run function/         # run the function locally
```

`workpeg project submit` will eventually review and release both halves
together to `<namespace>.workpeg.com`. It does not exist yet — until it does,
each half ships through its own command.
