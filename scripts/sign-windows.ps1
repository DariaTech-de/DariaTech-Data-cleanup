param(
  [Parameter(Mandatory=$true)][string]$FilePath,
  [Parameter(Mandatory=$true)][string]$CertificatePath,
  [Parameter(Mandatory=$true)][string]$CertificatePassword
)

$ErrorActionPreference = "Stop"
$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
  Sort-Object FullName -Descending |
  Select-Object -First 1

if (-not $signtool) {
  throw "signtool.exe was not found. Install the Windows SDK on the build machine."
}

& $signtool.FullName sign /f $CertificatePath /p $CertificatePassword /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $FilePath
