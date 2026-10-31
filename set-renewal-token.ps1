# Saves the GitHub "renewal" token from your clipboard as the SECRETS_PAT
# secret. The bot uses it only to save each refreshed Instagram token back
# into GitHub, so the Instagram token never expires.
#
# Usage: create the token (Claude opens the pre-filled page), click
# "Generate token", copy it, then double-click "Save Renewal Token.cmd".
# The token is never printed: only its length, first characters, and what
# GitHub says it can do.

$Host.UI.RawUI.WindowTitle = "Save renewal token"
$repo = "gama88/barely-normal-bot"
$log = Join-Path $PSScriptRoot "token-check.log"   # outcome only, never the token
"$(Get-Date -Format s) renewal-token: started" | Out-File $log -Encoding utf8

function Stop-Here($msg) {
    "$(Get-Date -Format s) renewal-token FAILED: $msg" | Out-File $log -Append -Encoding utf8
    Write-Host ""
    Write-Host $msg -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

$token = (Get-Clipboard -Raw)
if (-not $token) { Stop-Here "Your clipboard is empty. Click the copy icon next to the new token, then run this again." }
$token = $token.Trim().Trim([char]0xFEFF).Trim()

if ($token -notmatch '^github_pat_[A-Za-z0-9_]{40,}$') {
    Stop-Here ("Your clipboard doesn't contain a GitHub fine-grained token (it should start with " +
               "'github_pat_'). It has $($token.Length) characters starting with " +
               "'$($token.Substring(0, [Math]::Min(6, $token.Length)))'. Copy the token again, then run this again.")
}

Write-Host "Found a GitHub token: $($token.Length) characters, starting github_pat_..." -ForegroundColor Cyan
Write-Host "Checking it can reach this repo's secrets..."

try {
    $null = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/actions/secrets/public-key" `
        -Headers @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json";
                    "X-GitHub-Api-Version" = "2022-11-28" } -TimeoutSec 30
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Stop-Here ("GitHub says this token can't access the repo's secrets (HTTP $code). When creating it, " +
               "choose 'Only select repositories' -> barely-normal-bot, and set Secrets to 'Read and write'.")
}

"$(Get-Date -Format s) renewal-token: github accepted it for $repo secrets" | Out-File $log -Append -Encoding utf8
Write-Host "GitHub confirms it can manage secrets for $repo" -ForegroundColor Green

# Exact bytes via a temp file: piping from Windows PowerShell would add CRLF.
$tmp = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tmp, $token, (New-Object System.Text.UTF8Encoding $false))
cmd /c "gh secret set SECRETS_PAT -R $repo < `"$tmp`""
$saved = $LASTEXITCODE
Remove-Item $tmp -Force
if ($saved -ne 0) { Stop-Here "Couldn't save it to GitHub (gh secret set failed)." }

"$(Get-Date -Format s) renewal-token: saved to GitHub" | Out-File $log -Append -Encoding utf8
Set-Clipboard -Value " "   # don't leave the token sitting in the clipboard
Write-Host ""
Write-Host "Saved to GitHub as SECRETS_PAT. Your Instagram token will now renew itself." -ForegroundColor Green
Read-Host "Press Enter to close"
