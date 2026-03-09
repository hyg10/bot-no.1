# Kill existing bot processes
$cmds = Get-Process cmd -ErrorAction SilentlyContinue
foreach ($c in $cmds) {
    if ($c.MainWindowTitle -like '*Trading*' -or $c.MainWindowTitle -like '*Bot*') {
        Stop-Process -Id $c.Id -Force
        Write-Host "Killed CMD: $($c.Id) $($c.MainWindowTitle)"
    }
}
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Write-Host "Killed all Python processes"
Start-Sleep 3

# Start bot
Start-Process 'C:\Users\rlask\Downloads\backpack-advanced-bot-v2\start_bot.bat' `
    -WorkingDirectory 'C:\Users\rlask\Downloads\backpack-advanced-bot-v2' `
    -WindowStyle Minimized
Write-Host "Bot started"
