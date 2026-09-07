# Análise Integrada de MSB — Streamlit

Aplicação em Python/Streamlit para importar, tratar, ligar e analisar os
ficheiros usados nas análises integradas de MSB (perfis de manutenção,
frota de veículos, matrículas e prioridade Kinto), num só lugar.

## Como correr

```bash
pip install -r requirements.txt
streamlit run app.py
```

A aplicação abre com 4 páginas na barra lateral, que correspondem ao fluxo
de trabalho descrito no documento do projeto:

1. **📥 Importar Ficheiros** — carregar os 4 ficheiros de origem. Ficam
   guardados na pasta `data/`, que funciona como "base de dados" local.
   - `maintenance_profiles.csv` — delimitador `,`
   - `cars.csv` — delimitador `,`, encoding `utf-8` (colunas em minúsculas:
     `msbKey`, `carId`, `country`, `make`, `status`, etc.)
   - `Matriculas.csv`
   - `kinto_prioridade.csv` — delimitador `;`

2. **🔑 Gerador Keys** — recria a lógica do script Tkinter original (sem a
   UI de desktop): calcula `quality1_key`…`quality4_key`, normaliza
   `make`/`model`/`mark`/`engineSize`/`fuelType`/`powerHp`, e propaga a
   qualidade dos veículos com `msbQuality == 4` para os "irmãos" com
   qualidade menor (`predictedQuality`, `id_copia`, `descricao_copia`).
   Ao guardar, atualiza (ou cria) o `maintenance_profiles_FINAL.csv`,
   preservando outras colunas já existentes e acrescentando as linhas
   novas — tal como o script original fazia em Excel.

3. **🗄️ Construir Maintenance** — liga o `maintenance_profiles_FINAL` ao
   `cars.csv` pelo `msbKey` (normalizado para minúsculas em ambos os
   lados) e acrescenta as colunas novas: contagem de carid's, matrícula,
   VIN, kinto, kinto prioridade, leasys matrículas, checkdate e
   observações. Gera o `maintenance.csv` final (com exportação CSV e
   Excel).

4. **📊 Dashboard & Análises** — filtros (marca, status, kinto,
   combustível, qualidade, pesquisa livre e, por último, diferença de
   anos face ao `maxEndDate`), gráficos e tabela em separadores
   (Gráficos, Qualidade por Marca, Tabela), e exportação Excel (separador
   atual ou todos os separadores num só ficheiro).

## Suposições assumidas (a validar com o negócio)

O documento do projeto deixa alguns pontos em aberto; foram tomadas as
seguintes decisões, todas isoladas em `utils/merge_logic.py` para fácil
ajuste:

- **Contagem de carid's por id** = nº de `carId` distintos em `cars.csv`
  para aquele `msbKey`, considerando apenas os registos com
  `country == "PO"` (configurável na página **Construir Maintenance**;
  os de outro país, ex.: "SQ", contam como 0).
- **Matrícula / VIN por id** = todas as matrículas/VINs encontrados (via
  `carId` → `CARID` em `Matriculas.csv`) para os veículos daquele
  `msbKey`, concatenados por `, ` (um id pode ter vários carid's e,
  portanto, várias matrículas).
- **Leasys matriculas** = nº de matrículas distintas encontradas para
  aquele id.
- **Kinto** = ids com `status` "Ativo" **e** `contagem_carids > 0` são
  kinto (um id com 0 carid's só tem veículos de outro país, ex.: "SQ", e
  por isso não conta). Ids com `status` "Descontinuado" só são kinto se
  também tiverem `contagem_carids > 0` **e** o `maxEndDate` estiver a, no
  máximo, 365 dias de distância (em valor absoluto, passado ou futuro) da
  data de referência (por omissão, hoje). Qualquer outro status nunca é
  kinto. A data de referência e o limite de dias são configuráveis na
  página **Construir Maintenance**.
- **Kinto prioridade** = lookup pelo nome da marca (`make`) no ficheiro
  `kinto_prioridade.csv`, usando a 1ª coluna como número de prioridade e
  a 2ª como marca (por posição, não pelo nome exato do cabeçalho, para
  ser robusto a pequenas variações do ficheiro).
- **checkdate / observações** ficam vazias — são campos de preenchimento
  manual, editáveis na página **Construir Maintenance** (`st.data_editor`).
- **anos_diferenca** = diferença em anos completos (valor absoluto) entre
  `maxEndDate` e a data de referência (hoje, por omissão). Linhas sem
  `maxEndDate` ficam com 0 (tratadas como as mais recentes). É a base do
  último filtro no Dashboard — um `select_slider` construído com a lista
  de anos por ordem decrescente, para que o valor maior fique à esquerda
  e o menor (0) à direita, como pedido.

## Fase 2 — Check Service

Ficheiros: `part_description.csv`, `service_parts.csv`, `task_parts.csv`.
Replica o script `CHECK.py` fornecido (merge por `msbId` + `partId`,
filtrado a `country == "PO"`), com 2 páginas:

1. **🧩 Importar & Gerar Check** — importar os 3 ficheiros e gerar o
   `check_analise.csv` (botão "Gerar ficheiro").
2. **📋 Check Dashboard** — 2 separadores:
   - *Diferenças Service vs Task*: linhas incompletas eliminadas, mostra
     apenas peças com alguma diferença (`check_price`, `check_partnumber`
     ou `check_qtd` a Falso — lógica OU, não E, para captar qualquer
     discrepância).
   - *Peças Recolhidas*: peças com `check_collected` = Falso, mantendo
     linhas vazias/incompletas.

   Exportação Excel — separador atual ou todos os separadores.

## Fase 3 — Kinto Analisis

Ficheiros mensais `kinto_Maintenance_Profile_AAAA_MM_DD.csv` e
`kinto_Vehicle_All_AAAA_MM_DD.csv` (delimitador `;`, mesma estrutura
todos os meses — só muda o nº de linhas e a data no nome). 2 páginas:

1. **🗓️ Kinto Importar** — carregar um ou vários ficheiros mensais de
   uma vez. O mês/ano são detetados automaticamente pelo nome do
   ficheiro (regex `AAAA_MM_DD`), mostrados numa tabela editável para
   confirmar/corrigir antes de importar. Cada mês fica guardado num
   histórico persistido (`kinto_maintenance_historico.csv` /
   `kinto_vehicle_historico.csv`); reimportar o mesmo mês substitui-o
   (upsert), sem duplicar linhas.
2. **📅 Kinto Dashboard** — liga o histórico às bases já existentes da
   Fase 1: `kinto_maintenance_historico` ↔ `maintenance.csv` (chave
   `MsbKeyID` ↔ `id`) e `kinto_vehicle_historico` ↔ `cars.csv` (chave
   `CarID`/`CARID` ↔ `carId`). 2 separadores (Maintenance / Vehicle All),
   cada um com:
   - Filtros por marca, qualidade (ou status, no separador Vehicle All),
     ano e mês — as opções mostradas são só as que existem nos dados
     importados.
   - KPIs de resumo, gráfico de quantidade por marca e por
     qualidade/status.
   - Evolução mensal com alternância **Acumulado** (contagem total por
     mês) ou **Diferença vs. mês anterior** (quantos ids são novos,
     quantos mudaram de valor e quantos ficaram iguais — o que foi
     efetivamente atualizado, e não apenas repetido).
   - Exportação Excel — separador atual ou todos (o separador não
     visitado nesta sessão exporta sem filtros aplicados).

### Suposições da Fase 3 (a validar com dados reais)

Não tive ficheiros reais `kinto_Maintenance_Profile`/`kinto_Vehicle_All`
para confirmar nomes exatos de colunas, por isso a ligação usa resolução
de colunas insensível a maiúsculas/minúsculas (`find_col` em
`utils/kinto_logic.py`), tentando `MsbKeyID`/`id`, `Make`/`make`,
`CarID`/`CARID`/`carId`, `Status`/`status`. Se os ficheiros reais usarem
nomes diferentes destes, é só ajustar as listas de candidatos nesse
ficheiro.

## Estrutura do projeto

```
msb_app/
├── app.py                              # Lançador (st.navigation, agrupa por fase)
├── pages/
│   ├── 0_Home.py                       # Estado do pipeline (todas as fases)
│   ├── 1_Importar_Ficheiros.py         # Fase 1
│   ├── 2_Gerador_Keys.py               # Fase 1
│   ├── 3_Construir_Maintenance.py      # Fase 1
│   ├── 4_Dashboard_Analises.py         # Fase 1
│   ├── 5_Check_Importar.py             # Fase 2
│   ├── 6_Check_Dashboard.py            # Fase 2
│   ├── 7_Kinto_Importar.py             # Fase 3
│   └── 8_Kinto_Dashboard.py            # Fase 3
├── utils/
│   ├── io_utils.py                     # persistência em data/
│   ├── keys_logic.py                   # Fase 1: gerador de keys + qualidade
│   ├── merge_logic.py                  # Fase 1: ligações entre ficheiros
│   ├── check_logic.py                  # Fase 2: lógica do CHECK.py
│   ├── kinto_logic.py                  # Fase 3: mês/ano, upsert, merges, diffs
│   └── branding.py                     # logo FleetData
├── assets/
│   └── logo.png                        # logo da FleetData
├── data/                                # ficheiros importados/gerados
└── requirements.txt
```

**Nota sobre nomes de ficheiro:** todos os ficheiros de página usam nomes
só com texto simples (sem emoji), porque o Windows por vezes corrompe
carateres emoji em nomes de ficheiro ao extrair um `.zip`. Os emojis
continuam a aparecer na barra lateral, mas vêm do parâmetro `icon=` em
`app.py`, não do nome do ficheiro.

## Marca

O logo `assets/logo.png` (FleetData) é mostrado no canto superior esquerdo
em todas as páginas, através de `st.logo()` (requer `streamlit >= 1.37`,
já definido no `requirements.txt`).
