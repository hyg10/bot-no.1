$ws = New-Object -ComObject WScript.Shell
$startupPath = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup\BackpackTradingBot.lnk")
$shortcut = $ws.CreateShortcut($startupPath)
$shortcut.TargetPath = "C:\Users\rlask\Downloads\backpack-advanced-bot-v2\start_bot.bat"
$shortcut.WorkingDirectory = "C:\Users\rlask\Downloads\backpack-advanced-bot-v2"
$shortcut.WindowStyle = 7  # Minimized
$shortcut.Save()
Write-Host "Startup shortcut created at: $startupPath"
