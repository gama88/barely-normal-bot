# Saves the Instagram token from your clipboard as the IG_ACCESS_TOKEN
# GitHub secret — but only after checking Instagram actually accepts it.
# The token is never printed: only its length, first characters, and the
# account name Instagram reports for it.
#
# Usage: copy a fresh token (Meta app -> Use cases -> Customize -> API setup
# with Instagram login -> Generate token -> Copy), then run this script.

$Host.UI.RawUI.WindowTitle = "Save Instagram token"
$repo = "gama88/barely-normal-bot"

$log = Join-Path $PSScriptRoot "token-check.log"   # outcome only, never the token
"$(Get-Date -Format s) started" | Out-File $log -Encoding utf8

function Stop-Here($msg) {
    "$(Get-Date -Format s) FAILED: $msg" | Out-File $log -Append -Encoding utf8
    Write-Host ""
    Write-Host $msg -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

$token = (Get-Clipboard -Raw)
if (-not $token) { Stop-Here "Your clipboard is empty. Click Copy on the Meta token box, then run this again." }
$token = $token.Trim()

if ($token -notmatch '^IG[A-Za-z0-9_-]{50,}$') {
    Stop-Here ("Your clipboard doesn't contain an Instagram token (it should start with 'IG' " +
               "and be one long word). It has $($token.Length) characters starting with " +
               "'$($token.Substring(0, [Math]::Min(4, $token.Length)))'. Copy the token again, then run this again.")
}

Write-Host "Found a token in your clipboard: $($token.Length) characters, starting $($token.Substring(0, 6))..." -ForegroundColor Cyan
Write-Host "Checking it with Instagram..."

try {
    $me = Invoke-RestMethod -Method Get -Uri "https://graph.instagram.com/v21.0/me" `
        -Body @{ fields = "username"; access_token = $token } -TimeoutSec 30
} catch {
    $detail = $_.ErrorDetails.Message
    Stop-Here "Instagram rejected this token: $detail`nGenerate a new token on the Meta page, copy it, and run this again."
}

if (-not $me.username) {
    Stop-Here "Instagram's reply didn't include an account name (got: $($me | Out-String)). Something on this network may be intercepting it."
}
"$(Get-Date -Format s) instagram accepted token for @$($me.username)" | Out-File $log -Append -Encoding utf8
Write-Host "Instagram accepts it - it belongs to @$($me.username)" -ForegroundColor Green
$token | gh secret set IG_ACCESS_TOKEN -R $repo
if ($LASTEXITCODE -ne 0) { Stop-Here "Couldn't save it to GitHub (gh secret set failed)." }

"$(Get-Date -Format s) saved to GitHub" | Out-File $log -Append -Encoding utf8
Set-Clipboard -Value " "   # don't leave the token sitting in the clipboard
Write-Host ""
Write-Host "Saved to GitHub as IG_ACCESS_TOKEN. You can close this window." -ForegroundColor Green
Read-Host "Press Enter to close"
