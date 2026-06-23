param(
  [string]$RepoUrl = "https://github.com/resign13/video.git",
  [string]$Server = "47.82.169.227",
  [string]$User = "root",
  [string]$AppDir = "/opt/video"
)

$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..
try {
  git add .
  if (-not (git diff --cached --quiet)) {
    git commit -m "update web deployment"
  }
  git branch -M main
  git remote remove origin 2>$null
  git remote add origin $RepoUrl
  git push -u origin main

  ssh "$User@$Server" "set -e; if [ ! -d '$AppDir/.git' ]; then rm -rf '$AppDir'; git clone '$RepoUrl' '$AppDir'; else cd '$AppDir' && git fetch origin main && git reset --hard origin/main; fi; cd '$AppDir' && bash scripts/server_deploy.sh"
}
finally {
  Pop-Location
}
