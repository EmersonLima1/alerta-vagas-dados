# Alerta de vagas remotas de dados no WhatsApp

Automação em Python, agendada no **GitHub Actions**, que busca vagas
**remotas no Brasil** na área de dados, filtra por cargo e nível e envia
as novidades para o meu WhatsApp, sem repetir vagas e sem vagas antigas.

> **Status:** v1 em validação. Lógica coberta por testes automatizados
> (54 testes). A integração real com a Gupy e o CallMeBot ainda precisa ser
> confirmada na primeira execução no Actions (veja [Validação](#validação)).

## Problema

Procurar vagas manualmente todo dia em vários sites é repetitivo e fácil de
esquecer, e vagas boas recebem muitas candidaturas nos primeiros dias.
O objetivo é ser avisado rápido, só com vagas que realmente interessam.

## Escopo da v1

| Critério | Regra |
|---|---|
| Cargos e níveis | Analista de Dados (Jr/Pleno), Analista de BI (Jr/Pleno), Cientista de Dados (Jr), Engenheiro de Dados (Jr) |
| Nível não informado no título | Aceito (é muito comum) e sinalizado na mensagem; configurável |
| Modelo | Somente remoto |
| Localização | Somente Brasil (país vazio é aceito; títulos com "International", "LATAM" etc. são descartados) |
| Idade | Publicada há no máximo **7 dias** |
| Repetição | Cada vaga é enviada uma única vez |
| Frequência | De hora em hora, das 08h às 22h (Brasília) |
| Fonte | Gupy (endpoint JSON do portal público) |

**Fora da v1 (ideias para versões futuras):** outras fontes (LinkedIn não tem
API pública para isso; avaliar Programathor, Remotar e repositórios de vagas no
GitHub), filtro por palavras-chave na descrição (ex.: SQL, Python), resumo
diário, painel com histórico das vagas (ótimo gancho para um projeto de BI).

## Critérios de sucesso

1. Nenhuma vaga sênior, estágio, presencial/híbrida ou internacional chega no WhatsApp.
2. Nenhuma vaga chega duas vezes.
3. Nenhuma vaga com mais de 7 dias chega.
4. Se a fonte ou o envio quebrar, eu fico sabendo (o GitHub manda e-mail quando um workflow falha).

## Como funciona

```
GitHub Actions (cron)                      data/vagas_enviadas.json
        │                                        ▲        │
        ▼                                        │        │ (lê: o que já foi enviado)
  ┌───────────┐   ┌────────────┐   ┌─────────────┴──┐     │
  │ Extrair   │──▶│ Transformar │──▶│ Carregar       │◀────┘
  │ API Gupy  │   │ filtros +   │   │ WhatsApp +     │
  │           │   │ deduplicação│   │ salva estado   │
  └───────────┘   └────────────┘   └────────────────┘
```

É um pequeno ETL: extrai vagas da API, transforma (normaliza, filtra,
remove já enviadas) e carrega (envia e registra).

```
src/alerta_vagas/
├── __main__.py      # orquestra o fluxo; `python -m alerta_vagas [--dry-run]`
├── config.py        # cargos, níveis, idade máxima, limites
├── modelos.py       # Vaga: formato comum a todas as fontes
├── fontes/gupy.py   # busca + paginação + retry + normalização
├── filtros.py       # remota, Brasil, recente, cargo, nível
├── estado.py        # vagas já enviadas (JSON no repo)
└── notificador.py   # formata e envia pelo CallMeBot
tests/               # pytest, sem acessar a internet
.github/workflows/
├── alerta-vagas.yml # agendamento + envio + commit do estado
└── testes.yml       # roda os testes a cada push
```

## Decisões técnicas

**Fonte: endpoint JSON do portal da Gupy.** A Gupy concentra boa parte das
vagas de empresas brasileiras. Ela não tem API oficial de busca para
candidatos; o script usa o mesmo endpoint JSON, sem login, que o portal
público chama no navegador (`portal.gupy.io/api/job-search/jobs`). É mais
leve e estável que raspar HTML, mas é interno e não documentado: já mudou de
endereço em outubro de 2026. Por isso o uso é pessoal e moderado (algumas
requisições por hora) e o código falha de forma explícita se o formato
mudar, em vez de parar de enviar vagas em silêncio. Alternativa oficial para
uma v2: a API do Adzuna, que tem vagas do Brasil e exige cadastro gratuito.

**WhatsApp: CallMeBot.** Comparação feita para uso pessoal:

| | CallMeBot | Twilio | WhatsApp Cloud API (Meta) |
|---|---|---|---|
| Custo | Grátis | Pago após crédito de teste | Grátis para começar, cobra por conversa iniciada pela empresa |
| Configuração | 1 mensagem no WhatsApp para receber a apikey | Conta + sandbox; o sandbox expira e precisa ser reativado | App na Meta, número de teste, token, templates aprovados |
| Mensagem livre | Sim | Só no sandbox ou com template | Fora da janela de 24h, só com template aprovado |
| Confiabilidade | Serviço de um desenvolvedor, sem SLA | Alta | Alta |

O CallMeBot é o único que resolve "mandar texto livre para o meu próprio
número" sem custo e sem burocracia. A desvantagem é não ter garantia de
serviço. Por isso o envio está isolado em `notificador.py`: trocar de
provedor é escrever outra classe com o método `enviar(texto)`.

**Estado em arquivo no repositório, não no cache do Actions.** O cache é
apagado após 7 dias sem uso e pode ser despejado a qualquer momento, o que
faria vagas serem reenviadas. O JSON versionado tem histórico (`git log`),
é fácil de inspecionar e de corrigir à mão. Entradas com mais de 60 dias são
removidas para o arquivo não crescer para sempre.

**Só marca como enviada depois do envio dar certo.** Se o WhatsApp falhar na
2ª mensagem, as vagas da 1ª ficam registradas e as da 2ª são tentadas de novo
na próxima execução.

**7 dias de idade máxima.** As vagas costumam ficar abertas por semanas, mas
as primeiras candidaturas têm mais chance. Na prática, como o script roda de
hora em hora, quase tudo chega com menos de 1 dia; os 7 dias servem de margem
caso o workflow fique parado. Ajustável pela variável `MAX_DIAS`.

**De hora em hora, das 08h às 22h.** "Enviar quando encontrar" num sistema
agendado vira "verificar com frequência". Uma hora é rápido o suficiente
para vagas e evita notificações de madrugada. Cada execução deve durar menos de
1 minuto (confirmar nos primeiros logs), bem dentro da cota gratuita do Actions (ilimitada em repositório
público; 2.000 min/mês em privado, e isto usa cerca de 500). O agendamento
do GitHub pode atrasar alguns minutos em horários de pico, por isso usamos o
minuto 17 e não o 0.

**Teto de 20 vagas por execução.** Evita uma enxurrada na primeira execução;
o restante sai nas próximas, mais recentes primeiro.

## Configuração (passo a passo)

### 1. Obter a apikey do CallMeBot

1. Abra a página oficial: <https://www.callmebot.com/blog/free-api-whatsapp-messages/>
   e copie o número do bot indicado lá (ele muda de tempos em tempos, então
   confira sempre na página).
2. Salve esse número nos contatos do celular.
3. Envie para ele, pelo WhatsApp, a mensagem: `I allow callmebot to send me messages`
4. Você recebe de volta uma mensagem com a sua **apikey**.
5. Teste no navegador (troque os valores):
   `https://api.callmebot.com/whatsapp.php?phone=+5577999999999&text=teste&apikey=123456`

### 2. Cadastrar os segredos no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**

| Nome | Valor |
|---|---|
| `WHATSAPP_PHONE` | Seu número com DDI e DDD, ex.: `+5577999999999` |
| `CALLMEBOT_APIKEY` | A apikey recebida |

Secrets ficam criptografados, não aparecem no código e são mascarados nos
logs. Nunca coloque o número ou a chave no código.

### 3. Primeira execução (sem enviar)

**Actions → Alerta de vagas → Run workflow**, com "Só mostrar no log" marcado.
O log mostra as mensagens que seriam enviadas e o resumo do filtro, por exemplo:

```
Resumo do filtro: {'cargo_fora_do_escopo': 180, 'aceita': 12, 'nivel_senior_nao_aceito_para_Analista de Dados': 30, ...}
```

Confira se as vagas aceitas fazem sentido. Depois rode de novo desmarcando a
opção para testar o envio real. A partir daí o agendamento assume.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                    # testes
PYTHONPATH=src python -m alerta_vagas --dry-run   # busca real, sem enviar
```

Para enviar de verdade localmente, defina `WHATSAPP_PHONE` e
`CALLMEBOT_APIKEY` no ambiente.

## Validação

- [x] Testes unitários: identificação de cargo e nível (incluindo "I/II/III" e
      "BI" não virar nível "I"), filtros de remoto, Brasil e idade, paginação e
      deduplicação da fonte, falha parcial da fonte, falha no meio do envio,
      poda do estado, erro do CallMeBot com HTTP 200, apikey nunca aparece em erro.
- [ ] Primeira execução real na Gupy (dry-run no Actions)
- [ ] Primeiro envio real pelo CallMeBot
- [ ] Uma semana rodando: conferir falsos positivos/negativos e ajustar `config.py`

## Limitações conhecidas

- O filtro de nível usa o **título** da vaga. Vagas sem nível no título são
  aceitas e marcadas como "nível não informado".
- A API da Gupy não é oficial e pode mudar.
- O GitHub desativa workflows agendados em repositórios públicos sem
  atividade por 60 dias (o próprio commit do estado conta como atividade
  quando há vagas novas, mas vale ficar atento ao e-mail de aviso).
