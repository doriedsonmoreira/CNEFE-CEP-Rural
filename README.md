# Extrator de CEPs de Localidades e Zona Rural - CNEFE (Censo 2022 / IBGE)

Script em Python para extrair, filtrar e consolidar CEPs de **localidades, distritos fora da sede e zonas rurais** a partir dos dados brutos do **CNEFE (Cadastro Nacional de Endereços para Fins Estatísticos - Censo 2022)** do IBGE, cruzando os códigos territoriais com a **DTB 2025 (Divisão Territorial Brasileira)**.

---

## Como Funciona

O script [`cnefe_cep_rural.py`](./cnefe_cep_rural.py) lê os arquivos `.csv` na pasta `UF/` em modo *streaming* (baixo consumo de memória RAM) e aplica **3 regras complementares** para identificar endereços rurais e localidades:

1. **Regra 1 — Área não urbanizada (`NUM_QUADRA == '0'`):** Endereços sem numeração de quadra urbana conforme padrão do CNEFE/IBGE.
2. **Regra 2 — Distrito fora da sede municipal (`COD_DISTRITO` com final diferente de `'05'`):** Captura vilas, povoados e distritos municipais fora da sede urbana principal.
3. **Regra 3 — Termos rurais no logradouro ou na localidade:** Captura registros cujo `NOM_TIPO_SEGLOGR` ou `DSC_LOCALIDADE` contenha termos característicos de área rural (`SITIO`, `FAZENDA`, `POVOADO`, `CHACARA`, `ASSENTAMENTO`, `COMUNIDADE`, `LOCALIDADE`, `ZONA RURAL`, etc.).

Além disso, o script:
- **Extrai sublocalidades nomeadas:** Quando o endereço traz um tipo rural (`SITIO`, `FAZENDA`, `POVOADO`, etc.) combinado ao nome no campo de logradouro (`NOM_SEGLOGR`), gera também o registro específico daquela sublocalidade (ex.: `"SITIO TATAIRA"`).
- **Filtra ruídos de digitação:** Descarta CEPs isolados (1 única ocorrência representando `< 2%` dos endereços de uma localidade que já possui CEP dominante com $\ge 20$ registros).

---

## Estrutura do Projeto

```text
searchScript_CNEFE/
├── cnefe_cep_rural.py                 # Script principal de extração
├── Dicionario_CNEFE_Censo_2022.xls    # Dicionário oficial de variáveis do CNEFE (IBGE)
├── DTB_2025/                          # Relatórios da Divisão Territorial Brasileira (IBGE 2025)
│   ├── RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.csv
│   ├── RELATORIO_DTB_BRASIL_2025_DISTRITOS.csv
│   └── DISTRITOS-SUBDISTRITOS_NOVOS_E_EXTINTOS_2025.csv
├── UF/                                # Arquivos CSV de entrada do CNEFE por estado
│   └── 23_CE_amostra.csv              # Arquivo de amostra real do Ceará (80.000 linhas) para teste imediato
└── RESULTADOS/                        # Pasta onde os arquivos JSON finais são gerados
```

---

## Pré-requisitos

- **Python 3.10+** (utiliza apenas bibliotecas nativas do Python, não é necessário instalar pacotes externos com `pip`).

---

## Como Executar

### 1. Teste Rápido (com o arquivo de amostra do Ceará incluso)

O repositório já inclui o arquivo `UF/23_CE_amostra.csv` (~13 MB) para que você possa testar imediatamente:

```bash
python3 cnefe_cep_rural.py
```

O script processará a amostra e gerará o arquivo `RESULTADOS/23_CE_amostra.json`.

### 2. Processando Estados Completos (Dados Oficiais do IBGE)

Como os arquivos CSV completos do CNEFE possuem centenas de megabytes por estado (ultrapassando o limite de 100 MB do GitHub), baixe os arquivos desejados diretamente do portal oficial do IBGE:

1. Acesse o diretório oficial do CNEFE (Censo 2022) no IBGE:
   - [Download CNEFE 2022 por UF (FTP IBGE)](https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/)
2. Baixe o arquivo `.zip` do estado desejado (ex.: `23_CE.zip`), extraia o arquivo `.csv` na pasta `UF/` e execute:

```bash
python3 cnefe_cep_rural.py
```

*(Dica: remova o arquivo `UF/23_CE_amostra.csv` se quiser processar apenas o arquivo completo).*

### Argumentos Opcionais

Você também pode personalizar os caminhos das pastas via linha de comando:

```bash
python3 cnefe_cep_rural.py --uf-dir ./UF --dtb-dir ./DTB_2025 --out-dir ./RESULTADOS
```

---

## Formato do JSON Gerado

Cada arquivo `.json` salvo na pasta `RESULTADOS/` contém uma lista ordenada de objetos no seguinte formato:

```json
[
  {
    "uf": "CE",
    "cod_municipio": "2300101",
    "nome_municipio": "Abaiara",
    "cod_distrito": "230010105",
    "nome_distrito": "Abaiara",
    "localidade": "SITIO TATAIRA",
    "cep": "63240000"
  }
]
```
