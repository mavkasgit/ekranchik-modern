$base = 'HKCU:\Control Panel\NotifyIconSettings'
$dev = 'C:\Users\user\VibeCoding\ekranchik-modern\launcher\source_code\EkranchikAllInOne\bin\Debug\net9.0-windows\EkranchikAllInOne.exe'
Get-ChildItem $base | ForEach-Object {
  $props = Get-ItemProperty $_.PSPath
  if ($props.ExecutablePath -eq $dev) {
    Set-ItemProperty $_.PSPath -Name IsPromoted -Value 1 -Type DWord
    Write-Output ("promoted " + $_.PSChildName)
  }
}
