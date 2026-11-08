#!/usr/bin/env python3
"""
cnefe_cep_rural.py — Extrator de CEPs de Localidades e Zona Rural (CNEFE / Censo 2022 - IBGE)

Lê os arquivos CSV do CNEFE na pasta UF/, cruza os códigos de municípios e distritos
com os relatórios oficiais da pasta DTB_2025/ e gera um arquivo JSON por UF
na pasta RESULTADOS/ (ex.: RESULTADOS/23_CE.json).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

COD_UF_TO_SIGLA: dict[str, str] = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

# Tipos de segmento de logradouro que caracterizam área rural ou localidade 
TIPOS_LOGRADOURO_RURAL: set[str] = {
    "SITIO",
    "FAZENDA",
    "POVOADO",
    "CHACARA",
    "ASSENTAMENTO",
    "COMUNIDADE",
    "GLEBA",
    "COLONIA",
    "ACAMPAMENTO",
    "GRANJA",
    "RANCHO",
    "SERINGAL",
    "ENGENHO",
    "USINA",
    "ALDEIA",
    "QUILOMBO",
    "AGROVILA",
    "LOCALIDADE",
    "DISTRITO",
    "RODOVIA",
    "ESTRADA",
}

# Tipos de segmento que representam sub-localidades nomeadas quando combinados com NOM_SEGLOGR
TIPOS_SUBLOCALIDADE_RURAL: set[str] = {
    "SITIO",
    "FAZENDA",
    "POVOADO",
    "CHACARA",
    "ASSENTAMENTO",
    "COMUNIDADE",
    "GLEBA",
    "COLONIA",
    "ACAMPAMENTO",
    "GRANJA",
    "RANCHO",
    "SERINGAL",
    "ENGENHO",
    "USINA",
    "ALDEIA",
    "QUILOMBO",
    "AGROVILA",
    "LOCALIDADE",
}

# Palavras-chave estritamente rurais para busca em DSC_LOCALIDADE 
TERMOS_LOCALIDADE_RURAL: set[str] = TIPOS_SUBLOCALIDADE_RURAL | {"ZONA RURAL"}

RE_SUFIXO_SN = re.compile(r"\s+(?:S/N|SN|S\.N\.)$", re.IGNORECASE)
RE_MULTI_ESPACO = re.compile(r"\s+")


def carregar_dtb(dtb_dir: Path) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """
    Carrega os mapeamentos da pasta DTB_2025:
      - municipios: cod_municipio (7 dígitos) -> (sigla_uf, nome_municipio)
      - distritos:  cod_distrito (9 dígitos)  -> nome_distrito
    """
    municipios: dict[str, tuple[str, str]] = {}
    distritos: dict[str, str] = {}

    arq_mun = dtb_dir / "RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.csv"
    if not arq_mun.exists():
        raise FileNotFoundError(f"Arquivo de municípios não encontrado: {arq_mun}")

    with arq_mun.open("r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        idx_uf = idx_cod_mun = idx_nome_mun = -1
        for row in reader:
            if not row:
                continue
            if idx_cod_mun == -1:
                if "Código Município Completo" in row:
                    idx_uf = row.index("UF")
                    idx_cod_mun = row.index("Código Município Completo")
                    idx_nome_mun = row.index("Nome_Município")
                continue
            if len(row) <= max(idx_uf, idx_cod_mun, idx_nome_mun):
                continue
            cod_mun = row[idx_cod_mun].strip()
            if not cod_mun:
                continue
            cod_uf = row[idx_uf].strip()
            sigla_uf = COD_UF_TO_SIGLA.get(cod_uf, cod_uf)
            nome_mun = row[idx_nome_mun].strip()
            municipios[cod_mun] = (sigla_uf, nome_mun)

    arq_dist = dtb_dir / "RELATORIO_DTB_BRASIL_2025_DISTRITOS.csv"
    if not arq_dist.exists():
        raise FileNotFoundError(f"Arquivo de distritos não encontrado: {arq_dist}")

    with arq_dist.open("r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        idx_cod_dist = idx_nome_dist = -1
        for row in reader:
            if not row:
                continue
            if idx_cod_dist == -1:
                if "Código de Distrito Completo" in row:
                    idx_cod_dist = row.index("Código de Distrito Completo")
                    idx_nome_dist = row.index("Nome_Distrito")
                continue
            if len(row) <= max(idx_cod_dist, idx_nome_dist):
                continue
            cod_dist = row[idx_cod_dist].strip()
            if not cod_dist:
                continue
            distritos[cod_dist] = row[idx_nome_dist].strip()

    # Fallback complementar: distritos novos e extintos (caso constem no Censo 2022)
    arq_ext = dtb_dir / "DISTRITOS-SUBDISTRITOS_NOVOS_E_EXTINTOS_2025.csv"
    if arq_ext.exists():
        with arq_ext.open("r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            idx_cod_dist = idx_nome_dist = -1
            for row in reader:
                if not row:
                    continue
                if "Código de Distrito Completo" in row and "Nome_Distrito" in row:
                    idx_cod_dist = row.index("Código de Distrito Completo")
                    idx_nome_dist = row.index("Nome_Distrito")
                    continue
                if idx_cod_dist != -1 and len(row) > max(idx_cod_dist, idx_nome_dist):
                    cod_dist = row[idx_cod_dist].strip()
                    nome_dist = row[idx_nome_dist].strip()
                    if len(cod_dist) == 9 and cod_dist.isdigit() and nome_dist:
                        distritos.setdefault(cod_dist, nome_dist)

    return municipios, distritos


def contem_termo_rural_localidade(localidade_upper: str) -> bool:
    """Verifica se DSC_LOCALIDADE é ou contém um termo estritamente rural."""
    if not localidade_upper:
        return False
    if "ZONA RURAL" in localidade_upper:
        return True
    palavras = localidade_upper.split()
    return any(p in TERMOS_LOCALIDADE_RURAL for p in palavras)


def extrair_sublocalidade(
    localidade_upper: str,
    tipo_seglogr_upper: str,
    nom_seglogr_upper: str,
) -> str | None:
    """
    Se NOM_TIPO_SEGLOGR for um tipo de sublocalidade rural (SITIO, FAZENDA, POVOADO,
    ASSENTAMENTO, etc.) e NOM_SEGLOGR trouxer um nome diferente de DSC_LOCALIDADE,
    retorna a sublocalidade formatada (ex.: 'SITIO TATAIRA').
    """
    if tipo_seglogr_upper not in TIPOS_SUBLOCALIDADE_RURAL or not nom_seglogr_upper:
        return None

    seg_limpo = RE_SUFIXO_SN.sub("", nom_seglogr_upper).strip()
    seg_limpo = RE_MULTI_ESPACO.sub(" ", seg_limpo)
    if not seg_limpo or seg_limpo in {"SN", "S/N", "SEM DENOMINACAO", "SEM NOME"}:
        return None

    if seg_limpo.startswith(tipo_seglogr_upper + " ") or seg_limpo == tipo_seglogr_upper:
        candidato = seg_limpo
    else:
        candidato = f"{tipo_seglogr_upper} {seg_limpo}"

    if candidato == localidade_upper or seg_limpo == localidade_upper:
        return None

    return candidato


def processar_arquivo_uf(
    csv_path: Path,
    municipios: dict[str, tuple[str, str]],
    distritos: dict[str, str],
    min_noise_ratio: float = 0.02,
    min_dominant_count: int = 20,
) -> list[dict[str, str]]:
    """
    Lê um arquivo CSV de UF do CNEFE em streaming, filtra registros de localidades
    e zona rural, agrega por (cod_municipio, cod_distrito, localidade, cep) e
    remove ruídos isolados.
    """
    # (cod_mun, cod_dist, localidade) -> Counter({cep: qtd})
    contagem_ceps: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    uf_fallback_por_mun: dict[str, str] = {}

    colunas_necessarias = (
        "COD_UF",
        "COD_MUNICIPIO",
        "COD_DISTRITO",
        "NUM_QUADRA",
        "CEP",
        "DSC_LOCALIDADE",
        "NOM_TIPO_SEGLOGR",
        "NOM_SEGLOGR",
    )

    with csv_path.open("r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            header = next(reader)
        except StopIteration:
            return []

        header_clean = [h.strip() for h in header]
        for col in colunas_necessarias:
            if col not in header_clean:
                raise ValueError(
                    f"Coluna obrigatória '{col}' não encontrada em {csv_path.name}"
                )

        idx_uf = header_clean.index("COD_UF")
        idx_mun = header_clean.index("COD_MUNICIPIO")
        idx_dist = header_clean.index("COD_DISTRITO")
        idx_quadra = header_clean.index("NUM_QUADRA")
        idx_cep = header_clean.index("CEP")
        idx_loc = header_clean.index("DSC_LOCALIDADE")
        idx_tipo = header_clean.index("NOM_TIPO_SEGLOGR")
        idx_seg = header_clean.index("NOM_SEGLOGR")
        max_idx = max(
            idx_uf, idx_mun, idx_dist, idx_quadra, idx_cep, idx_loc, idx_tipo, idx_seg
        )

        for row in reader:
            if len(row) <= max_idx:
                continue

            cep = row[idx_cep].strip()
            if len(cep) != 8 or not cep.isdigit():
                continue

            cod_mun = row[idx_mun].strip()
            cod_dist = row[idx_dist].strip()
            num_quadra = row[idx_quadra].strip()
            localidade = RE_MULTI_ESPACO.sub(" ", row[idx_loc].strip().upper())
            tipo_seg = row[idx_tipo].strip().upper()
            nom_seg = row[idx_seg].strip().upper()

            # Regra 1: Área não urbanizada (NUM_QUADRA == '0')
            regra_quadra_zero = num_quadra == "0"
            # Regra 2: Distrito fora da sede municipal (final != '05')
            regra_distrito_nao_sede = bool(cod_dist) and not cod_dist.endswith("05")
            # Regra 3: Termos rurais no tipo de logradouro ou no nome da localidade
            regra_termo_rural = (
                tipo_seg in TIPOS_LOGRADOURO_RURAL
                or contem_termo_rural_localidade(localidade)
            )

            if not (regra_quadra_zero or regra_distrito_nao_sede or regra_termo_rural):
                continue

            if cod_mun not in uf_fallback_por_mun:
                cod_uf = row[idx_uf].strip()
                uf_fallback_por_mun[cod_mun] = COD_UF_TO_SIGLA.get(cod_uf, cod_uf)

            if localidade:
                contagem_ceps[(cod_mun, cod_dist, localidade)][cep] += 1

            subloc = extrair_sublocalidade(localidade, tipo_seg, nom_seg)
            if subloc:
                contagem_ceps[(cod_mun, cod_dist, subloc)][cep] += 1

    resultados: list[dict[str, str]] = []

    for (cod_mun, cod_dist, localidade), cep_counter in contagem_ceps.items():
        total_loc = sum(cep_counter.values())
        sigla_uf, nome_mun = municipios.get(
            cod_mun, (uf_fallback_por_mun.get(cod_mun, ""), "")
        )
        nome_dist = distritos.get(cod_dist, nome_mun)

        for cep, qtd in cep_counter.most_common():
            # Filtra ruído isolado (1 ocorrência < 2% quando a localidade tem CEP dominante >= 20)
            if (
                len(cep_counter) > 1
                and total_loc >= min_dominant_count
                and qtd == 1
                and (qtd / total_loc) < min_noise_ratio
            ):
                continue

            resultados.append(
                {
                    "uf": sigla_uf,
                    "cod_municipio": cod_mun,
                    "nome_municipio": nome_mun,
                    "cod_distrito": cod_dist,
                    "nome_distrito": nome_dist,
                    "localidade": localidade,
                    "cep": cep,
                }
            )

    resultados.sort(
        key=lambda r: (
            r["nome_municipio"],
            r["nome_distrito"],
            r["localidade"],
        )
    )
    return resultados


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Extrai CEPs de localidades e zona rural do CNEFE (IBGE 2022) por UF."
    )
    parser.add_argument(
        "--uf-dir",
        type=Path,
        default=base_dir / "UF",
        help="Pasta contendo os arquivos CSV do CNEFE por UF (padrão: ./UF)",
    )
    parser.add_argument(
        "--dtb-dir",
        type=Path,
        default=base_dir / "DTB_2025",
        help="Pasta contendo os arquivos CSV do DTB 2025 (padrão: ./DTB_2025)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=base_dir / "RESULTADOS",
        help="Pasta de saída para os arquivos JSON gerados (padrão: ./RESULTADOS)",
    )
    args = parser.parse_args()

    if not args.uf_dir.exists():
        print(f"Erro: pasta de entrada '{args.uf_dir}' não encontrada.", file=sys.stderr)
        return 1

    csv_files = sorted(args.uf_dir.glob("*.csv"))
    if not csv_files:
        print(
            f"Nenhum arquivo .csv encontrado em '{args.uf_dir}'.",
            file=sys.stderr,
        )
        return 1

    print(f"Carregando base territorial de '{args.dtb_dir}'...")
    municipios, distritos = carregar_dtb(args.dtb_dir)
    print(
        f"  -> {len(municipios)} municípios e {len(distritos)} distritos carregados."
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in csv_files:
        t0 = time.perf_counter()
        print(f"Processando '{csv_path.name}'...")
        registros = processar_arquivo_uf(csv_path, municipios, distritos)
        out_path = args.out_dir / f"{csv_path.stem}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False, indent=2)
        dt = time.perf_counter() - t0
        print(
            f"  -> {len(registros)} registros salvos em '{out_path}' ({dt:.1f}s)."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
