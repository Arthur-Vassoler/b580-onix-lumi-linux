# Driver OpenRGB para a ONIX LUMI Intel Arc B580

Suporte à iluminação da placa no OpenRGB. O protocolo está documentado em
[`../docs/05-protocolo-led.md`](../docs/05-protocolo-led.md) e foi validado no
hardware ([`../docs/06`](../docs/06-validacao-hardware.md)).

## Arquivos

```
Controllers/OnixArcController/
    OnixArcController.h            mapa de registradores e modos
    OnixArcController.cpp          transações I2C
    RGBController_OnixArc.h
    RGBController_OnixArc.cpp      zonas, modos e efeitos
    OnixArcControllerDetect.cpp    detecção por ID PCI

patches/
    0001-pci_ids-add-onix-arc-b580.patch
    0002-i2c-linux-walk-up-to-pci-parent.patch
```

## Por que os dois patches

**`0001`** só acrescenta identificadores: `INTEL_ARC_B580_DEV` (`0xE20B`),
`ONIX_SUB_VEN` (`0x207E`) e `ONIX_LUMI_ARC_B580` (`0xA002`).

**`0002`** é um conserto de verdade, e vale para além desta placa. O OpenRGB resolve o
caminho real do adaptador I²C e trunca **uma vez** para chegar ao dispositivo PCI pai.
Isso funciona para GPUs AMD, onde o adaptador é filho direto do device PCI:

```
/sys/devices/pci.../0000:03:00.0/i2c-4        ->  0000:03:00.0   ✔
```

Na Arc, o adaptador fica atrás de um device de plataforma intermediário:

```
/sys/devices/pci.../0000:04:00.0/i2c_designware.1024/i2c-15
                                 ^^^^^^^^^^^^^^^^^^^ para aqui, sem vendor/device
```

O barramento acaba registrado com vendor e device zerados, e nenhum
`REGISTER_I2C_PCI_DETECTOR` casa. O patch continua subindo até achar um diretório com
o arquivo `vendor`. É genérico: qualquer GPU que exponha o I²C por um device
intermediário passa a ser reconhecida.

## Aplicar e compilar

```sh
git clone https://gitlab.com/CalcProgrammer1/OpenRGB.git
cd OpenRGB
git apply /caminho/para/openrgb/patches/*.patch
cp -r /caminho/para/openrgb/Controllers/OnixArcController Controllers/
qmake OpenRGB.pro && make -j$(nproc)
sudo ./OpenRGB
```

Os arquivos novos são pegos automaticamente: o `OpenRGB.pro` varre
`Controllers/*/*.cpp`.

## O que o driver expõe

Uma zona, um LED — a placa gera todos os efeitos em firmware e não oferece
endereçamento individual.

| modo OpenRGB | registrador `0x10` | cores |
|---|---|---|
| Direct | `0x01` | por LED |
| Static | `0x01` | específica do modo |
| Breathing | `0x02` | específica do modo |
| Rainbow | `0x00` | nenhuma |
| Chroma Flow | `0x03` | nenhuma |
| Taxiway Glow | `0x04` | nenhuma |
| One Color | `0x05` | nenhuma |
| Stacking | `0x06` | nenhuma |

**Direct** funciona porque, uma vez no modo Custom, basta reescrever os registradores
de cor — medido a 20 Hz sem erro de I²C. O driver evita tocar no registrador de modo
nesse caminho, senão o efeito reinicia a cada quadro.

## Duas restrições do hardware, gravadas no código

1. **Nunca agrupe a troca de modo com outros registradores na mesma transação.** A
   placa aceita o pacote e apaga. Uma operação lógica por transação, com 50 ms entre
   elas.
2. **O brilho precisa ser reaplicado depois de trocar de modo** — um modo acessado
   pela primeira vez sobe apagado.

## Ainda não verificado

- Os intervalos úteis dos parâmetros de velocidade. Os registradores são de 8 bits e
  o driver expõe a faixa inteira, com os padrões do fabricante como ponto de partida.
- Se `speed` maior significa mais rápido ou mais lento em cada efeito.
- O registrador `0x27`, que o utilitário oficial escreve com `0x0E` só na
  inicialização.
