$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskVenvPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskVenvPython)) {
    $taskPython = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $taskPython = (& py -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $taskPython = (Get-Command python).Source
    }
    if (-not $taskPython) { throw 'Install Python 3.11 or newer from https://www.python.org/downloads/ and try again.' }
    & $taskPython -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer is required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
    & $taskPython -m venv (Join-Path $taskRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the bot environment.' }
}
$taskRequirements = Join-Path $taskRoot 'requirements.txt'
$taskFingerprint = (Get-FileHash -LiteralPath $taskRequirements -Algorithm SHA256).Hash
$taskMarker = Join-Path $taskRoot '.venv\requirements-installed.txt'
if (-not (Test-Path -LiteralPath $taskMarker) -or (Get-Content -LiteralPath $taskMarker -Raw).Trim() -ne $taskFingerprint) {
    & $taskVenvPython -m pip install --disable-pip-version-check -r $taskRequirements
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the bot libraries. Check your internet connection and run again.' }
    Set-Content -LiteralPath $taskMarker -Value $taskFingerprint -Encoding ascii
}
$taskEnvFile = Join-Path $taskRoot '.env'
if (-not (Test-Path -LiteralPath $taskEnvFile)) {
    Copy-Item -LiteralPath (Join-Path $taskRoot '.env.example') -Destination $taskEnvFile
}
$taskEnvText = Get-Content -LiteralPath $taskEnvFile -Raw
if ($taskEnvText -match '(?m)^DISCORD_TOKEN=paste_your_bot_token_here\s*$' -or $taskEnvText -notmatch '(?m)^DISCORD_TOKEN=\S+') {
    Write-Host 'Paste your DISCORD BOT token here. It will be saved privately in .env and will not be displayed.'
    Write-Host 'Create it at https://discord.com/developers/applications (Bot > Reset Token).'
    $taskSecureToken = Read-Host 'Bot token' -AsSecureString
    $taskTokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecureToken)
    try { $taskToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskTokenPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskTokenPointer) }
    if ([string]::IsNullOrWhiteSpace($taskToken)) { throw 'No token entered. Run again when you have your bot token.' }
    if ($taskEnvText -match '(?m)^DISCORD_TOKEN=') {
        $taskEnvText = [regex]::Replace($taskEnvText, '(?m)^DISCORD_TOKEN=[^\r\n]*', [System.Text.RegularExpressions.MatchEvaluator]{ param($match) 'DISCORD_TOKEN=' + $taskToken })
    } else { $taskEnvText = 'DISCORD_TOKEN=' + $taskToken + "`r`n" + $taskEnvText }
    [IO.File]::WriteAllText($taskEnvFile, $taskEnvText, [Text.UTF8Encoding]::new($false))
    $taskToken = $null
}
& $taskVenvPython (Join-Path $taskRoot 'bot.py')
if ($LASTEXITCODE -ne 0) { throw 'Bot stopped with an error. See the message above.' }
