"""Build the PT-BR installer: block patches embedded in PowerShell, no complete font files shipped."""
import base64, hashlib, struct, sys
from pathlib import Path

# usage: make_ptbr_installer.py <LanguagePack PT-BR fonts> <fonts from build_dualsense.py> <output folder>
SRC, NEW, OUT = (Path(a) for a in sys.argv[1:4])


def blocks(old: bytes, new: bytes) -> bytes:
    assert len(old) == len(new) and old[:0x800] == new[:0x800]
    out = bytearray()
    for off in range(0x800, len(old), 16):
        if old[off:off + 16] != new[off:off + 16]:
            out += struct.pack('<I', off) + new[off:off + 16]
    return bytes(out)


fonts = []
for name in ('small.xpr', 'large.xpr'):
    old, new = (SRC / name).read_bytes(), (NEW / name).read_bytes()
    fonts.append((name, len(old), hashlib.sha256(old).hexdigest().upper(), hashlib.sha256(new).hexdigest().upper(),
                  base64.b64encode(blocks(old, new)).decode()))

entries = ',\n'.join(
    f"    @{{ Name = '{n}'; Size = {size}; Source = '{src}'; Target = '{dst}'; Blocks = '{b64}' }}"
    for n, size, src, dst, b64 in fonts)

COMMON = r'''
$ErrorActionPreference = 'Stop'
$PackId = 'LanguagePack_PT-BR'
$BackupName = 'DualSensePrompts_PT-BR_backup'

function Write-Ok($text)   { Write-Host $text -ForegroundColor Green }
function Write-Warn($text) { Write-Host $text -ForegroundColor Yellow }
function Write-Fail($text) { Write-Host $text -ForegroundColor Red }

function Get-Sha256([byte[]]$bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '') }
    finally { $sha.Dispose() }
}

# The launcher keeps paths.toml in the default data folder, even after the data folder moves.
function Find-DataFolder {
    $default = Join-Path $env:LOCALAPPDATA 'Shaolin Monks Recomp'
    $toml = Join-Path $default 'paths.toml'
    if (Test-Path -LiteralPath $toml) {
        foreach ($line in Get-Content -LiteralPath $toml -Encoding UTF8) {
            if ($line -match '^\s*data\s*=\s*"(.*)"\s*$') { return $Matches[1].Replace('\\', '\') }
            if ($line -match "^\s*data\s*=\s*'(.*)'\s*$") { return $Matches[1] }
        }
    }
    return $default
}

function Find-FontsFolder {
    $data = Find-DataFolder
    $fonts = Join-Path $data "mods\languages\$PackId\fonts"
    while (-not (Test-Path -LiteralPath (Join-Path $fonts 'large.xpr'))) {
        Write-Warn "Não encontrei as fontes do LanguagePack PT-BR em:"
        Write-Host "  $fonts"
        Write-Host ""
        Write-Host "Abra o launcher, aba 'Files and support', e copie o endereço do campo 'Data folder'."
        $answer = Read-Host "Cole aqui o endereço do Data folder (ou deixe vazio para cancelar)"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $null }
        $data = $answer.Trim().Trim('"')
        $fonts = Join-Path $data "mods\languages\$PackId\fonts"
    }
    return @{ Data = $data; Fonts = $fonts }
}

function Assert-GameClosed {
    while (Get-Process -Name 'ShaolinMonksRecomp' -ErrorAction SilentlyContinue) {
        Write-Warn "O jogo ou o launcher está aberto. Feche os dois e aperte Enter."
        [void](Read-Host)
    }
}

function Write-Atomic([string]$path, [byte[]]$bytes) {
    $temp = "$path.tmp"
    [System.IO.File]::WriteAllBytes($temp, $bytes)
    Move-Item -LiteralPath $temp -Destination $path -Force
}
'''

INSTALL = '''# DualSense Prompts PT-BR 1.1.0 - instalador
# Aplica os ícones DualSense nas fontes do LanguagePack PT-BR 2.0.0.
# O pacote contém só os blocos de textura alterados, não as fontes completas.
''' + COMMON + f'''
$Fonts = @(
{entries}
)

Write-Host ""
Write-Host "DualSense Prompts PT-BR 1.1.0 - Shaolin Monks Recomp" -ForegroundColor Cyan
Write-Host ""
try {{
    Assert-GameClosed
    $where = Find-FontsFolder
    if (-not $where) {{ Write-Warn "Instalação cancelada."; exit 1 }}
    Write-Host "Pasta das fontes: $($where.Fonts)"
    $backup = Join-Path $where.Data $BackupName

    # Check everything first, so nothing changes unless both fonts can be patched.
    $plan = @()
    foreach ($font in $Fonts) {{
        $path = Join-Path $where.Fonts $font.Name
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $hash = Get-Sha256 $bytes
        if ($hash -eq $font.Target) {{ $plan += @{{ Font = $font; Path = $path; Bytes = $null }}; continue }}
        if ($bytes.Length -ne $font.Size -or $hash -ne $font.Source) {{
            throw "$($font.Name) não é a fonte do LanguagePack PT-BR 2.0.0. Reinstale o LanguagePack em Mods e rode o instalador de novo."
        }}
        $plan += @{{ Font = $font; Path = $path; Bytes = $bytes }}
    }}

    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    foreach ($item in $plan) {{
        $font = $item.Font
        if (-not $item.Bytes) {{ Write-Ok "$($font.Name): já estava instalado."; continue }}
        $saved = Join-Path $backup $font.Name
        if (-not (Test-Path -LiteralPath $saved)) {{ [System.IO.File]::WriteAllBytes($saved, $item.Bytes) }}
        $bytes = $item.Bytes
        $patch = [Convert]::FromBase64String($font.Blocks)
        for ($i = 0; $i -lt $patch.Length; $i += 20) {{
            $offset = [BitConverter]::ToInt32($patch, $i)
            [Array]::Copy($patch, $i + 4, $bytes, $offset, 16)
        }}
        if ((Get-Sha256 $bytes) -ne $font.Target) {{ throw "O resultado de $($font.Name) não confere. Nada foi alterado nesse arquivo." }}
        Write-Atomic $item.Path $bytes
        Write-Ok "$($font.Name): instalado."
    }}
    Write-Host ""
    Write-Ok "Pronto! Abra o launcher e jogue em Português (Brasil)."
    Write-Host "Backup das fontes originais: $backup"
    exit 0
}} catch {{
    Write-Host ""
    Write-Fail "Erro: $($_.Exception.Message)"
    exit 1
}}
'''

UNINSTALL = '''# DualSense Prompts PT-BR 1.1.0 - desinstalador
# Restaura as fontes originais do LanguagePack PT-BR a partir do backup do instalador.
''' + COMMON + f'''
$Sources = @{{ {'; '.join(f"'{n}' = '{src}'" for n, _, src, _, _ in fonts)} }}

Write-Host ""
Write-Host "DualSense Prompts PT-BR 1.1.0 - desinstalar" -ForegroundColor Cyan
Write-Host ""
try {{
    Assert-GameClosed
    $where = Find-FontsFolder
    if (-not $where) {{ Write-Warn "Cancelado."; exit 1 }}
    $backup = Join-Path $where.Data $BackupName
    foreach ($name in @('small.xpr', 'large.xpr')) {{
        $saved = Join-Path $backup $name
        if (-not (Test-Path -LiteralPath $saved)) {{
            throw "Backup não encontrado em $backup. Em Mods, remova e instale de novo o LanguagePack PT-BR para restaurar as fontes."
        }}
        $bytes = [System.IO.File]::ReadAllBytes($saved)
        if ((Get-Sha256 $bytes) -ne $Sources[$name]) {{ throw "O backup de $name está diferente do original. Reinstale o LanguagePack PT-BR em Mods." }}
    }}
    foreach ($name in @('small.xpr', 'large.xpr')) {{
        Write-Atomic (Join-Path $where.Fonts $name) ([System.IO.File]::ReadAllBytes((Join-Path $backup $name)))
        Write-Ok "${{name}}: restaurado."
    }}
    Remove-Item -LiteralPath $backup -Recurse -Force
    Write-Host ""
    Write-Ok "Pronto! Os ícones do Xbox voltaram."
    exit 0
}} catch {{
    Write-Host ""
    Write-Fail "Erro: $($_.Exception.Message)"
    exit 1
}}
'''

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'ferramentas').mkdir(exist_ok=True)
# Windows PowerShell 5.1 reads BOM-less scripts as ANSI; the BOM keeps the accents intact.
for name, text in (('instalar.ps1', INSTALL), ('desinstalar.ps1', UNINSTALL)):
    (OUT / 'ferramentas' / name).write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode('utf-8'))
for name, script, title in (('Instalar.bat', 'instalar.ps1', 'Instalar'), ('Desinstalar.bat', 'desinstalar.ps1', 'Desinstalar')):
    bat = (f'@echo off\r\ntitle DualSense Prompts PT-BR - {title}\r\n'
           f'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ferramentas\\{script}"\r\n'
           'echo.\r\npause\r\n')
    (OUT / name).write_bytes(bat.encode('ascii'))
for n, size, src, dst, b64 in fonts:
    print(n, 'blocks', len(base64.b64decode(b64)) // 20, 'source', src[:12], 'target', dst[:12])
