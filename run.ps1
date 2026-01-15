$ErrorActionPreference = "Stop"

# Always validate config first
python C:\GLSCLP\tools\validate_config.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# TODO: call your real entrypoint(s) here
# Examples (pick the one you actually use):
# python C:\GLSCLP\src\main.py
# python C:\GLSCLP\scripts\pipeline_run.py
# python C:\GLSCLP\scripts\watch_incoming.py

Write-Host "Config OK. Add your pipeline entrypoint to run.ps1 next."
