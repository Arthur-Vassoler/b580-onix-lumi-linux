# 06 — Validação no hardware

Feita em 18/09/2026, Fedora 44, kernel 7.2.5, numa Onix Lumi Arc B580 (`207e:a002`),
depois do reboot que destravou o barramento.

## Resultado

**O protocolo funciona.** Controle completo do LED a partir do Linux, sem root,
sem driver de kernel, sem o software do fabricante.

## A regra que quase custou o projeto

Os primeiros comandos foram enviados assim, tudo num pacote só:

```
10 01 1a ff 1b 00 1c 00 3e 88      # modo Custom + cor vermelha + brilho
```

O AMC **aceitou** (ecoou o último valor, sem erro de I²C) e o **LED apagou**. Duas
tentativas, mesmo resultado. Trocado por três transações separadas, com 50 ms entre
elas, funcionou de primeira:

```
10 01              # modo
    (50 ms)
3e 88              # brilho
    (50 ms)
1a ff 1b 00 1c 00  # cor
```

Foi o que o app oficial sempre fez, e eu não tinha percebido: **cada método do
`LightingController` escreve um comando só.** `SetLedCustomMode` manda apenas `10 01`;
`SetCustomColor` manda apenas as três cores; `LedBrightness` manda apenas `3e v`.
O único lugar onde ele agrupa é a init — e ali não há troca de modo.

**Regra: nunca agrupe uma troca de modo com outros registradores.** Mais seguro ainda:
uma operação lógica por transação, como o app.

Por que isso acontece não está esclarecido. A hipótese mais provável é que a troca de
modo seja processada de forma assíncrona no firmware e sobrescreva o que vier na
sequência — mas não foi comprovado. O que está comprovado é que 50 ms de separação
bastam.

## Confirmado

| | |
|---|---|
| Ordem dos canais | `0x1A` = **R**, `0x1B` = **G**, `0x1C` = **B**, confirmado visualmente |
| Modo Custom | `0x10` = `0x01` acende cor fixa |
| Modo Rainbow | `0x10` = `0x00` acende o arco-íris animado |
| Brilho | `0x3E`, `0x00` apaga, `0x88` é o padrão, `0xFF` funciona |
| Byte de retorno | **eco do último valor escrito**, não um status — `3e 88` devolve `88`, `10 05` devolve `05` |
| Atualização rápida | 120 escritas de cor a 20 Hz, zero erro de I²C |
| Ventoinhas e temperatura | intocadas; o ciclo 0→700 RPM observado é a histerese do modo zero-RPM em idle |

## Brilho parece ser por modo

Ao entrar num modo pela primeira vez, o LED fica apagado até o `0x3E` ser escrito
naquele modo. Combina com o app, que mantém um campo de brilho separado para cada
modo (`RainbowBrightness`, `CustomizeBrightness`, `OneColorBrightness`...), todos com
padrão `0x88`. Por isso `tools/lumi-led.py` sempre escreve o brilho depois de trocar
de modo.

## Implicação para o OpenRGB

Os 20 Hz sem erro mostram que dá para ter um modo **Direct**: escrever só
`1a R 1b G 1c B`, sem tocar no registrador de modo, uma vez que o modo Custom já
esteja ativo. É o que permite sincronizar com o resto da máquina.

## Estado do barramento

Nenhum travamento durante toda a bateria de testes — dezenas de transações, incluindo
a varredura de 120 cores. A leitura de 1 byte logo após a escrita é segura; o que
derrubou o barramento antes foi uma leitura de 8 bytes sem nada pendente
(`docs/03-armadilhas.md`).

## Validação do driver OpenRGB

Compilado contra o master upstream (`0129e58`) com gcc 16.2 e Qt 6.11, em Fedora 44.

```
$ ./openrgb --list-devices
0: ONIX LUMI Intel Arc B580
1: ASUS ROG STRIX B860-G GAMING WIFI
```

O patch de resolução do barramento faz efeito no log de detecção:

```
Registering I2C interface: Synopsys DesignWare I2C adapter (/dev/i2c-15) \
    Device 8086:E20B Subsystem: 207E:A002
```

Sem ele esse barramento apareceria com vendor e device zerados, e nenhum
`REGISTER_I2C_PCI_DETECTOR` casaria.

Os oito modos foram exercitados pela linha de comando do OpenRGB e todos responderam:
Static, Direct, Rainbow, Chroma Flow, Taxiway Glow, Stacking, Breathing e One Color.

### Três defeitos encontrados só ao compilar e rodar

1. **`zone::matrix_map` deixou de ser ponteiro** no OpenRGB atual; atribuir `NULL` não
   compila.
2. **O destrutor precisa chamar `Shutdown()`.** Sem isso a classe base reclama em todo
   encerramento: *"Device thread still active in base class destructor"*.
3. **Os modos animados subiam congelados.** O driver escrevia modo, brilho e velocidade,
   mas não o registrador *response* — que é o que põe o efeito em movimento.

Nenhum dos três apareceria numa revisão de código. É a diferença entre escrever um
driver e ter um driver.
