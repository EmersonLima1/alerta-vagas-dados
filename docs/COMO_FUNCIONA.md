# Como o projeto funciona

Guia para entender o código sem precisar ler tudo, e para saber **onde
mexer** em cada tipo de ajuste. Para instalação e configuração, veja o
[README](../README.md).

## 1. Visão geral: o caminho de uma vaga

A cada hora acontece isto:

```
cron-job.org ──(chama a API do GitHub)──▶ GitHub Actions inicia o workflow
                                                   │
                                                   ▼
                                  python -m alerta_vagas  (__main__.py)
                                                   │
   ┌───────────────────────────────────────────────┼──────────────────────────────┐
   │ 1. EXTRAIR                                    │                              │
   │    fontes/gupy.py busca cada termo de config.py na Gupy (só remotas)         │
   │    e converte cada resultado para o formato comum `Vaga` (modelos.py)        │
   │                                                                              │
   │ 2. TRANSFORMAR                                                               │
   │    filtros.py decide se a vaga serve: remota → Brasil → recente →            │
   │    cargo → nível. estado.py diz se ela já foi enviada antes.                 │
   │                                                                              │
   │ 3. CARREGAR                                                                  │
   │    notificador.py monta as mensagens e envia (Telegram ou WhatsApp).         │
   │    estado.py grava as vagas enviadas em data/vagas_enviadas.json             │
   └──────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
             o workflow faz commit de data/vagas_enviadas.json no repositório
```

É um pequeno **ETL** (Extract, Transform, Load), o mesmo padrão usado em
pipelines de dados maiores. Cada etapa mora num arquivo diferente, então
dá para trocar uma parte sem mexer nas outras.

## 2. O que cada arquivo faz

Todos os arquivos de código ficam em `src/alerta_vagas/`.

### `__main__.py`: o maestro
Ponto de entrada (`python -m alerta_vagas`). Não tem regra de negócio:
só chama as outras partes na ordem certa.
- `executar()` faz uma rodada completa: carrega o estado, busca, filtra,
  ordena (mais recentes primeiro), aplica o teto por execução, envia e salva.
- `main()` lê o argumento `--dry-run` (modo teste, imprime em vez de enviar)
  e transforma erros em código de saída 1. É isso que faz o GitHub marcar a
  execução como falha e te mandar e-mail.
- Detalhe importante: uma vaga só é marcada como enviada **depois** que o
  envio dá certo.

### `config.py`: as regras de negócio
O arquivo que você mais vai editar. Contém:
- `TERMOS_BUSCA`: o que é pesquisado na Gupy.
- `CARGOS`: quais cargos são aceitos, os padrões de texto que os
  identificam no título e os níveis aceitos para cada um.
- `Config`: números do comportamento (idade máxima, vagas por mensagem,
  teto por execução, retenção do estado).
- `Config.do_ambiente()`: permite sobrescrever alguns números por variável
  de ambiente, sem editar código (veja a seção 3).

### `modelos.py`: o formato comum
Define a `Vaga` (título, empresa, link, data, remota, país...). Toda fonte
converte o formato dela para `Vaga`. Por isso filtros e envio não sabem,
nem precisam saber, de onde a vaga veio. A propriedade `chave`
(`"gupy:12345"`) é o identificador usado para não repetir vagas.

### `fontes/gupy.py`: a extração
Conversa com o endpoint JSON do portal da Gupy (`portal.gupy.io/api/job-search/jobs`).
- `buscar(termos)`: para cada termo, pede as vagas **remotas**, percorre as
  páginas e junta tudo sem duplicar.
- `normalizar(item)`: converte o JSON da Gupy em `Vaga`. Se um campo
  obrigatório sumir (a Gupy mudou o formato), dá erro de propósito.
- `_get_json()`: faz a requisição e tenta de novo em erros temporários
  (rede, 429, 5xx), esperando 2s, 4s e 8s (*backoff* exponencial).
- Se um termo falhar, os outros continuam. Se **todos** falharem, a execução
  falha e você recebe e-mail.

### `filtros.py`: a decisão
Funções pequenas, uma para cada regra, aplicadas nesta ordem por `avaliar()`:
1. `eh_remota`: a vaga é remota?
2. `eh_brasil`: o país é Brasil (ou vazio) e o título não tem "International",
   "LATAM" etc.?
3. `eh_recente`: foi publicada há no máximo `max_dias`?
4. `identificar_cargo`: o título bate com algum cargo de `CARGOS`?
5. `identificar_nivel`: Júnior, Pleno, Sênior, Estágio ou não informado.
   Entende "Jr", "Pleno", "Sr" e algarismos romanos (I = Jr, II = Pleno,
   III = Sênior).

`avaliar()` devolve também o **motivo** da decisão. É ele que aparece no log
como `Resumo do filtro: {'antiga_ou_sem_data': 68, 'aceita': 1, ...}`, útil
para entender por que uma vaga não chegou.

### `estado.py`: a memória
Lê e grava `data/vagas_enviadas.json` (chave da vaga → quando foi enviada).
- `podar()` apaga entradas com mais de 60 dias, para o arquivo não crescer
  para sempre.
- `salvar()` grava de forma atômica: escreve num arquivo temporário e depois
  renomeia, para nunca deixar o JSON corrompido pela metade.

### `notificador.py`: o envio
- `Telegram` e `CallMeBot` têm o mesmo método `enviar(texto)`. Isso é uma
  *interface*: o resto do código não sabe qual dos dois está em uso.
- `do_ambiente()` escolhe o canal pelos secrets que existirem. O Telegram
  tem prioridade.
- `Console` é o "canal" do modo teste: só imprime no log.
- `formatar_vaga`, `montar_mensagens` e `texto_do_grupo` definem a **aparência**
  da mensagem e agrupam as vagas, até 5 por mensagem.
- Os erros nunca mostram o token ou a apikey.

### Arquivos fora de `src/`
| Arquivo | Papel |
|---|---|
| `.github/workflows/alerta-vagas.yml` | O workflow principal: instala Python, roda o script e faz commit do estado |
| `.github/workflows/testes.yml` | Roda os testes (`pytest`) a cada push |
| `data/vagas_enviadas.json` | A memória das vagas já enviadas (editado pelo robô) |
| `tests/` | Testes automatizados de cada parte, sem acessar a internet |
| `requirements.txt` / `requirements-dev.txt` | Dependências de execução / de desenvolvimento |

## 3. Ajustes comuns

### Mudar de 7 para 14 dias

**Opção A, sem mexer no código (recomendada):**
no GitHub, **Settings → Secrets and variables → Actions → aba Variables →
New repository variable**. Nome `MAX_DIAS`, valor `14`. Vale a partir da
próxima execução. Para voltar ao padrão, apague a variável.

Funcionam da mesma forma:
| Variável | O que faz | Padrão |
|---|---|---|
| `MAX_DIAS` | Idade máxima da vaga, em dias | `7` |
| `ACEITAR_NIVEL_NAO_INFORMADO` | `true`/`false`: aceitar vagas sem nível no título | `true` |
| `MAX_VAGAS_POR_EXECUCAO` | Teto de vagas enviadas por rodada | `20` |

**Opção B, mudar o padrão no código:** em `config.py`, na classe `Config`,
troque `max_dias: int = 7` por `max_dias: int = 14`.

### Buscar outro tipo de vaga (ex.: Desenvolvedor Java)

São dois lugares em `config.py`, porque a busca e o filtro são separados:

**1. `TERMOS_BUSCA`**: o que é pesquisado na Gupy. Busca ampla.
```python
TERMOS_BUSCA: list[str] = [
    "desenvolvedor java",
    "java developer",
    "engenheiro de software java",
]
```

**2. `CARGOS`**: quais títulos são aceitos e em que níveis. Filtro fino.
```python
CARGOS: dict[str, dict] = {
    "Desenvolvedor Java": {
        "padroes": [
            r"desenvolvedor(a)? java\b",
            r"\bjava developer",
            r"engenheir[oa] de software java\b",
            r"desenvolvedor(a)? back-?end java\b",
        ],
        "niveis": {"junior", "pleno"},
    },
}
```

Regras para os `padroes`:
- São **expressões regulares** comparadas com o título **sem acento e em
  minúsculas**. Escreva `"analista de servicos"`, não `"Analista de Serviços"`.
- `(a)?` aceita "desenvolvedor" e "desenvolvedora". `[oa]` aceita "o" ou "a".
  `-?` aceita "backend" e "back-end".
- `\b` marca limite de palavra. Por isso os padrões acima terminam em
  `java\b`: sem ele, "desenvolvedor java" também casaria com
  "Desenvolvedor JavaScript"!

Níveis possíveis em `niveis`: `"junior"`, `"pleno"`, `"senior"`, `"estagio"`.
Vagas sem nível no título são decididas pela opção
`aceitar_nivel_nao_informado`.

**3. (Opcional) Texto do cabeçalho**: em `notificador.py`, função
`texto_do_grupo`, troque `"Novas vagas remotas de dados"` pelo texto que quiser.

**4. (Recomendado) Testes**: em `tests/test_filtros.py`, acrescente exemplos
de títulos que devem e que **não** devem passar, e rode `pytest`. É a forma
mais rápida de saber se um padrão está largo ou estreito demais. Os testes
atuais de cargos de dados vão falhar se você trocar os cargos, e isso é
esperado: atualize-os para o novo caso.

Antes de ativar de verdade, rode o workflow manualmente com **"Só mostrar no
log" marcado** e confira o `Resumo do filtro` e as mensagens que seriam
enviadas.

### Aceitar vagas híbridas ou presenciais
Hoje há duas travas: `fontes/gupy.py` pede só `"workplaceType": "remote"`, e
`filtros.py` recusa não remotas em `eh_remota`. Mudar isso exige ajustar as
duas, e provavelmente filtrar por cidade (`vaga.cidade`/`vaga.estado`).

### Mudar a frequência
A frequência é definida no **cron-job.org** (o `schedule` do GitHub não
disparou neste repositório). O `cron` dentro do workflow ficou apenas como
reserva.

### Mudar a aparência da mensagem
`notificador.py`, função `formatar_vaga`. O texto entre `*asteriscos*` sai
em negrito: o Telegram converte via `Telegram.para_html`.

## 4. Como verificar se está tudo certo
- **Aba Actions** do repositório: cada execução mostra o log com quantas
  vagas foram lidas por termo e o `Resumo do filtro`.
- **E-mail do GitHub** quando uma execução falha (Gupy fora do ar, mudança de
  formato, token inválido).
- **`data/vagas_enviadas.json`**: o histórico de commits mostra o que foi
  enviado e quando.
- **Testes:** `pip install -r requirements-dev.txt && pytest` roda tudo em
  menos de 1 segundo, sem internet.
