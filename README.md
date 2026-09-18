# Intel Arc B580 "Onix Lumi" — controle de LED ARGB no Linux

Engenharia reversa do controle de iluminação da placa **ONIX LUMI Intel Arc B580 12GB**
(PCI `8086:e20b`, subsystem `207e:a002`) com o objetivo de escrever um driver para o
[OpenRGB](https://openrgb.org).

No Windows a iluminação é controlada pelo utilitário proprietário **LUMI ARGB Control
Software v2.1** da ONIX. No Linux não existe suporte algum — nem no OpenRGB, nem em
qualquer outro projeto. O issue upstream do OpenRGB para B580 está aberto e vazio.

## Estado

| Etapa | Status |
|---|---|
| Mapear barramentos e achar o controlador | ✅ feito |
| Confirmar que o controlador responde | ✅ feito |
| Extrair o protocolo do app Windows | ✅ feito — tabela de registradores completa |
| Validar os comandos no hardware | 🚧 barramento travado, precisa de reboot |
| Driver OpenRGB (C++) | ⬜ |
| Submeter upstream | ⬜ |

## Achado principal

O LED **não** é um dispositivo USB (a placa não expõe nenhum) e **não** está no SMBus da
placa-mãe. Ele está atrás do **AMC** (*Add-in card Management Controller*), o MCU de
gerenciamento da própria placa:

```
/dev/i2c-15   "Synopsys DesignWare I2C adapter"  (barramento interno da GPU)
  └─ 0x28     client "amc", instanciado pelo driver xe, sem driver ligado
```

O app oficial do Windows confirma o alvo: `OnixI2CDriver.dll` carrega a string literal
`\\.\nf_i2c_bus_00_0x0028` — o mesmo dispositivo.

**O protocolo é escrita de pares `(registrador, valor)`**, vários por transação, seguida
da leitura de 1 byte de status. Tabela completa em
[`docs/05-protocolo-led.md`](docs/05-protocolo-led.md):

```
0x10 modo   0x3E brilho   0x1A/1B/1C cor (Custom)   0xC9/CA/CB cor (Breathing)
modos: 00 Rainbow · 01 Custom · 02 Breathing · 03 Serial · 04 Runway
       05 One Color · 06 Block Stacking
```

Detalhes em [`docs/01`](docs/01-hardware-survey.md) a [`docs/05`](docs/05-protocolo-led.md).

## Onde paramos

O protocolo está extraído e as ferramentas prontas, mas **nada foi validado no
hardware ainda**: uma sondagem malfeita travou o barramento (ver
[`docs/03-armadilhas.md`](docs/03-armadilhas.md)) e o `0x28` só volta com ciclo de
energia. Próximo passo, depois de reiniciar:

```sh
tools/survey.sh                            # confirma que o 0x28 reapareceu
tools/lumi-led.py --dry-run color ff0000   # revisa os bytes
tools/lumi-led.py color ff0000             # o teste de verdade
```

Se não acender mas também não der erro de I²C, mande a init antes
(`tools/lumi-led.py init`) — é o que o app oficial faz.

O material do fabricante fica em `vendor/` (fora do git). Se sumir, o
`tools/extract-lumi.py` reconstrói tudo a partir do instalador; o download original
está documentado em [`docs/04-app-windows.md`](docs/04-app-windows.md).

## Aviso

O AMC também controla **ventoinhas e regulador de tensão** da placa. Escritas às cegas
podem desligar a refrigeração ou corromper configuração. Tudo neste repositório que
escreve no barramento é explicitamente marcado como tal.

## Uso

```sh
tools/lumi-led.py --dry-run color ff0000   # mostra os bytes sem escrever
tools/lumi-led.py color ff0000             # vermelho fixo
tools/lumi-led.py mode rainbow --speed 5
tools/lumi-led.py off

tools/survey.sh                            # inventário de hardware
tools/extract-lumi.py LUMISetupV2.1.exe    # extrai os binários do app oficial
tools/dotnet-il.py LUMI.exe --list         # desmonta o assembly .NET
sudo tools/recover-bus.sh                  # quando o barramento trava
```

Ambos rodam sem root: o `systemd-logind` dá ACL de `/dev/i2c-*` ao usuário da sessão local.
