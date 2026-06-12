#!/usr/bin/env pwsh
# scripts/sync-upstream.ps1
#
# Manually runs the same upstream-sync logic the GitHub Actions workflow does.
# Use this on any Windows machine that has git + PowerShell.
#
# Usage:
#   pwsh ./scripts/sync-upstream.ps1
#   pwsh ./scripts/sync-upstream.ps1 -DryRun        # shows what would merge, no push
#   pwsh ./scripts/sync-upstream.ps1 -Branch main   # target a different local branch
#
# Required env vars (or pass as params):
#   UPSTREAM_PAT  — GitHub.com PAT with repo:read on nicksgoat/allworth-companion-demo
#
param(
  [string]$UpstreamPat   = $env:UPSTREAM_PAT,
  [string]$UpstreamRepo  = "https://github.com/nicksgoat/allworth-companion-demo.git",
  [string]$UpstreamBranch = "demo-verified",
  [string]$Branch        = "master",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function git_ {
  $result = git -C $repoRoot @args 2>&1
  if ($LASTEXITCODE -ne 0) { throw "git $args failed: $result" }
  $result
}

Write-Host "==> Configuring sync bot identity"
git_ config user.name  "allworth-sync-bot"
git_ config user.email "allworth-sync-bot@allworth.ghe.com"

# Build authenticated upstream URL if PAT supplied
$upstreamUrl = $UpstreamRepo
if ($UpstreamPat) {
  $upstreamUrl = $UpstreamRepo -replace "https://", "https://${UpstreamPat}@"
}

Write-Host "==> Adding/updating upstream remote"
$remotes = git_ remote
if ($remotes -contains "upstream") {
  git_ remote set-url upstream $upstreamUrl
} else {
  git_ remote add upstream $upstreamUrl
}

Write-Host "==> Fetching upstream/$UpstreamBranch"
git_ fetch upstream $UpstreamBranch --no-tags

Write-Host "==> Checking out $Branch"
git_ checkout $Branch

$newCommits = (git_ rev-list --count "${Branch}..upstream/${UpstreamBranch}").Trim()
Write-Host "==> Upstream has $newCommits new commit(s) ahead of $Branch"

if ($newCommits -eq "0") {
  Write-Host "==> Nothing to do. $Branch is already up to date."
  exit 0
}

if ($DryRun) {
  Write-Host "==> DryRun: would merge $newCommits commit(s) — skipping actual merge and push."
  git_ log --oneline "${Branch}..upstream/${UpstreamBranch}"
  exit 0
}

Write-Host "==> Merging upstream/$UpstreamBranch into $Branch"
git_ merge "upstream/${UpstreamBranch}" --no-edit -m "chore: sync upstream ${UpstreamBranch} -> ${Branch} [automated]"

Write-Host "==> Pushing to origin/$Branch"
git_ push origin $Branch

Write-Host "==> Sync complete."
