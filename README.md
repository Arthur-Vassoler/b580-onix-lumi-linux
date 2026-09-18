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
| Extrair o protocolo do app Windows | 🚧 em andamento |
| Validar comandos no hardware | ⬜ |
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

Detalhes em [`docs/01-hardware-survey.md`](docs/01-hardware-survey.md).

## Aviso

O AMC também controla **ventoinhas e regulador de tensão** da placa. Escritas às cegas
podem desligar a refrigeração ou corromper configuração. Tudo neste repositório que
escreve no barramento é explicitamente marcado como tal.

## Uso

```sh
tools/survey.sh          # coleta o inventário de hardware
tools/amc-probe.py       # sondagem somente-leitura do AMC
```

Ambos rodam sem root: o `systemd-logind` dá ACL de `/dev/i2c-*` ao usuário da sessão local.
