# 03 — Armadilhas (aprendidas na prática)

## Leitura I²C crua trava o AMC até o próximo boot

**O que aconteceu.** Depois de um `i2cdetect` e leituras `read_byte_data` bem-sucedidas,
foi feita uma leitura I²C crua — `I2C_RDWR` com uma única mensagem `I2C_M_RD`, sem
byte de comando:

```python
bus.raw_read(0x28, 8)   # -> OSError errno 110 (ETIMEDOUT)
```

A partir daí **todo** acesso ao `0x28` passou a dar timeout, e um novo `i2cdetect -y -r 15`
passou a mostrar o barramento vazio. Não recuperou sozinho em 30 s de tentativas.
Nenhum erro no `dmesg`.

**Por quê.** O AMC é um dispositivo SMBus: ele espera `START → addr+W → comando → ...`.
Um read solto o deixa fora de sincronia no meio de uma transação, segurando SDA em nível
baixo. Com SDA preso, o barramento inteiro fica morto — não é o controlador DesignWare que
quebrou, é o escravo que não solta a linha.

**Como recuperar.** `tools/recover-bus.sh` (precisa de root) tenta, em ordem: forçar
runtime PM `on`, depois unbind/rebind do driver `i2c_designware`. Se o AMC estiver mesmo
segurando SDA, nada em userspace resolve — só ciclo de energia (reboot).

**Regra.** Nunca usar `raw_read()`. Para request/response use `write_then_read()`, que faz
`escrita → repeated START → leitura`, o padrão que o dispositivo entende. O método
`raw_read()` continua no código só como documentação e exige `i_know_the_risk=True`.

## O controlador I²C entra em runtime suspend

`/sys/.../i2c_designware.1024/power/runtime_status` fica `suspended` quando ocioso.
Isso é normal e o driver resume sozinho na transferência — não confunda com o barramento
travado. Para diagnosticar, o sintoma que importa é o `i2cdetect` voltar vazio.

## O AMC não é um mapa de registradores plano

Varredura de `0x00..0xff` com `read_byte_data` devolveu quase tudo `0xfe`, com `0x01` em
`0x06`, `0x07` e `0x0f`. Numa segunda rodada, o *receive byte* devolveu `0x01` onde antes
devolvia `0xfe` — ou seja, **a resposta depende do estado**, não do endereço lido.

Interpretação: é protocolo de comando/resposta. Você escreve um comando, ele prepara a
resposta, você lê. `0xFE` é provavelmente "sem resposta pendente" ou "comando inválido".
Ler endereços no escuro não vai revelar o mapa — é preciso o **conjunto de comandos**,
que sai da análise do app Windows.

## O AMC controla ventoinha e VRM

Confirmado pelos atributos de *late binding firmware* do driver `xe` no sysfs da GPU
(`lb_fan_control_version`, `lb_voltage_regulator_version`). Comandos de escrita
desconhecidos podem parar a refrigeração. Qualquer teste de escrita tem que rodar com
`fan*_input` e `temp*_input` monitorados em paralelo.
