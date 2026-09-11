$base = 'HKCU:\Control Panel\NotifyIconSettings'
Get-ChildItem $base | ForEach-Object {
  $props = Get-ItemProperty $_.PSPath
  $name = $props.ExecutablePath
  if (-not $name) { $name = '(no path)' }
  Write-Output ($_.PSChildName + ' | IsPromoted=' + $props.IsPromoted + ' | ' + $name)
}
