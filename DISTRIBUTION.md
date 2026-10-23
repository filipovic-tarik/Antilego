# Distributing Antilego for macOS

Antilego's public Mac build is self-contained. It runs the engine on the user's
own computer, opens the dashboard at `127.0.0.1:8766`, and stores credentials
and research data under `~/Library/Application Support/Antilego`.

## Build

The current release target is Apple silicon on macOS 13 or newer.

```sh
.venv/bin/python -m pip install pyinstaller
./scripts/build_macos_app.sh
```

The distributable archive is written to
`dist/Antilego-macOS-arm64.zip`.

## Release

For public distribution, sign the app with an Apple Developer ID certificate
and notarize the archive before uploading it to a GitHub release. The build
script applies an ad-hoc signature for local testing only; recipients of an
unnotarized build may need to right-click Antilego and choose **Open** on first
launch.
