#requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$Workspace,
    [string]$Vault,
    [string]$Prefix = (Join-Path $HOME '.local'),
    [string]$CodexHome,
    [string]$ClaudeHome,
    [switch]$DryRun,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandArgumentPassing = 'Standard'
$bootstrapArgs = @((Join-Path $PSScriptRoot 'bootstrap.py'), 'install', '--workspace', $Workspace, '--prefix', $Prefix)
if ($Vault) { $bootstrapArgs += @('--vault', $Vault) }
if ($CodexHome) { $bootstrapArgs += @('--codex-home', $CodexHome) }
if ($ClaudeHome) { $bootstrapArgs += @('--claude-home', $ClaudeHome) }
if ($DryRun) { $bootstrapArgs += '--dry-run' }
& $Python @bootstrapArgs
exit $LASTEXITCODE
