# Registra as tarefas agendadas do Mundo Antigo para o usuario atual (sem admin).
#
#   powershell -ExecutionPolicy Bypass -File scripts\registrar-tarefas.ps1
#
# - "MundoAntigo Backup": todo dia no horario abaixo. Se o PC estiver
#   desligado na hora, roda assim que ele ligar (StartWhenAvailable).
#
# Para remover: Unregister-ScheduledTask -TaskName "MundoAntigo Backup"

param(
    [string]$Horario = "12:30"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# uvw e o uv sem janela de console: a tarefa roda sem piscar um terminal.
$uvw = (Get-Command uvw -ErrorAction SilentlyContinue).Source
if (-not $uvw) {
    $env:PATH = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:PATH
    $uvw = (Get-Command uvw -ErrorAction Stop).Source
}

$action = New-ScheduledTaskAction -Execute $uvw `
    -Argument "run --directory `"$repo`" mundoantigo backup" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Horario
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask -TaskName "MundoAntigo Backup" `
    -Description "Espelha banco, videos, bibliotecas e modelos no disco de backup (ADR 0009)." `
    -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Get-ScheduledTask -TaskName "MundoAntigo Backup" |
    Select-Object TaskName, State, @{ n = "Proxima"; e = { ($_ | Get-ScheduledTaskInfo).NextRunTime } }
