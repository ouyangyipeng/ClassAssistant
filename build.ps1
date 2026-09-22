$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& uv run --no-project --python 3.12 scripts/build.py @args
exit $LASTEXITCODE
