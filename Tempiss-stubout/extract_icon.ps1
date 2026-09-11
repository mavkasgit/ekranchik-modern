Add-Type -AssemblyName System.Drawing
$i = New-Object System.Drawing.Icon('C:\Users\user\VibeCoding\ekranchik-modern\launcher\launcher.ico')
$i.ToBitmap().Save('C:\Users\user\VibeCoding\ekranchik-modern\Tempiss-stubout\launcher_ico.png')
Write-Output ("ok " + $i.Width + "x" + $i.Height)

# Иконки, реально показываемые в трее обоих процессов
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class TrayInfo {
    [DllImport("shell32.dll", SetLastError = true)]
    public static extern int SHExtractIconsW(string pszFileName, int nIconIndex, int cxIcon, int cyIcon, IntPtr[] phIcon, int[] piIconId, int nIcons, int flags);
}
'@
foreach ($exe in @(
  'C:\Users\user\VibeCoding\ekranchik-modern\launcher\source_code\EkranchikAllInOne\bin\Debug\net9.0-windows\EkranchikAllInOne.exe',
  'C:\Users\user\AppData\Local\Ekranchik\EkranchikAllInOne.exe'
)) {
  $icons = New-Object IntPtr[] 1
  $ids = New-Object int[] 1
  $n = [TrayInfo]::SHExtractIconsW($exe, 0, 32, 32, $icons, $ids, 1, 0)
  Write-Output ($exe + " -> SHExtractIconsW count=" + $n)
  if ($n -gt 0) {
    $ico = [System.Drawing.Icon]::FromHandle($icons[0])
    $name = Split-Path $exe -Leaf
    $ico.ToBitmap().Save('C:\Users\user\VibeCoding\ekranchik-modern\Tempiss-stubout\icon_' + $name + '.png')
    Write-Output ("  saved icon_" + $name + ".png")
  }
}
