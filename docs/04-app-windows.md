# 04 — O app Windows (LUMI ARGB Control Software v2.1)

Baixado de `https://cdn.onixsys.com/assets/downloads/LUMISetupV2.1.zip`
(página oficial: https://onixsys.com/download-en/), versão 2.1, 17/03/2025.
O binário **não** é redistribuído neste repositório — `tools/extract-lumi.py`
reproduz a extração a partir do arquivo original.

## Como extrair (o innoextract do Fedora não serve)

O instalador é Inno Setup **6.3.0**. O `innoextract` 1.9, que é o que o Fedora 44
empacota, morre com `Unexpected setup data version: 6.3.0`. O 7-Zip 26 também não abre.

Não é preciso interpretar os cabeçalhos do Inno. Os arquivos estão num **único stream
LZMA1 sólido**:

```
0x0c6400:  7a 6c 62 1a  5d 00 00 80 00  ...
           "zlb\x1a"    props LZMA1 (lc3/lp0/pb2, dic 8 MiB)
```

Basta sintetizar um cabeçalho `FORMAT_ALONE` (5 bytes de props + 8 bytes de tamanho
desconhecido) e descomprimir: saem 36,8 MiB com 42 executáveis PE, que se recortam pelo
cabeçalho MZ/PE e se nomeiam pelo caminho do PDB no registro CodeView.

## A pilha de acesso ao hardware

```
LUMI.exe                (.NET / WPF, MahApps.Metro)
   └─ P/Invoke
OnixI2CDriver.dll       (x64 nativo, 15 KiB — C:\Wrapper\OnixI2CDriver\)
   └─ DeviceIoControl
NfI2cTestDrv.sys        (KMDF, 55 KiB — "ReferenceCode_I2CPeripheralDriver_Tool")
   └─ \Device\RESOURCE_HUB\  (Windows SPB / I2C peripheral)
```

`NfI2cTestDrv.sys` publica symlinks no formato:

```
\DosDevices\NF_I2C_BUS_%02X_0X%04X       <- número do barramento, endereço do escravo
```

## O achado que fecha o círculo

Dentro do `OnixI2CDriver.dll`, como string UTF-16 literal:

```
\\.\nf_i2c_bus_00_0x0028
```

**Barramento 0, endereço 0x0028.** É exatamente o AMC que a varredura do Linux encontrou
em `/dev/i2c-15`. Confirmado de ponta a ponta: o LED da Onix Lumi é controlado **pelo
AMC**, e não por um MCU dedicado.

Não há, portanto, nenhum caminho que o Windows use e o Linux não tenha — só falta o
conjunto de comandos.

## A API do wrapper

`OnixI2CDriver.dll` exporta seis funções:

| export | o que faz |
|---|---|
| `InitializeDriver` | carrega/abre o driver |
| `OpenConnection` | abre `\\.\nf_i2c_bus_00_0x0028` |
| **`WriteReadAsync`** | **escreve um buffer, lê a resposta** |
| `EnableInterrupts` | habilita o SMBus Alert |
| `DisableInterrupts` | desabilita |
| `CloseConnection` | fecha |

Imports relevantes: `CreateFileW`, `DeviceIoControl`, `CreateEventW`,
`GetOverlappedResult` — I/O sobreposta, assíncrona.

`WriteReadAsync` é precisamente a transação do `xe_amc.c`: escrita seguida de leitura.
E `EnableInterrupts`/`DisableInterrupts` correspondem ao mesmo SMBus Alert que o driver
`xe` trata em `xe_amc_handle_alert()`. As duas implementações estão falando com o mesmo
dispositivo, do mesmo jeito.

## Onde estão os comandos do LED

Em `LUMI.exe` (2,5 MiB, assembly .NET). Os nomes de membro já entregam o modelo de dados:

```
LedMode  LedBrightness  LedDirection  LedModeConfig  ConfigLedModePath
get_RgbColor  get_RGBValue  FormatRGBValue  NormalizeRGBString
InitBreathingMode  InitStackingMode
get_BreathingBrightness  get_BreathingColor  get_BreathingTempo
get_StackingDirection  get_StackingSpeed
get_RunwayChaser  get_RunwayBrightness  get_RainbowBrightness
get_OneColorBrightness  get_SerialBrightness  get_CustomizeBrightness
```

Que batem com os efeitos anunciados pela ONIX: PrismPulse, Chaser, Breathing,
Chroma Flow, Stacking, Taxiway Glow.

**Os pacotes não estão como constantes no binário.** Varredura por templates MCTP
(`8f 01 0c 08 c8`, `7e 80 86`, `7e 20 7e`, `0f 0d 8f`) não achou nada em `LUMI.exe` —
o app monta os buffers em IL, byte a byte. Extrair isso exige descompilar o assembly.

## Próximo passo

Descompilar `LUMI.exe` (`monodis` do mono-devel, ou ILSpy) e ler os métodos de LED:
como o buffer passado a `WriteReadAsync` é montado, e qual o `command` dentro da
mensagem vendor-defined.
