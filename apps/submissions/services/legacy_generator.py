"""Gerador de planilha sintética fiel à estrutura legada do edital (282 processos)."""

from datetime import datetime, timedelta

import openpyxl
from openpyxl.styles import Font, PatternFill


def generate_synthetic_legacy_workbook(
    filepath: str,
    total: int = 282,
    g1_count: int = 9,
    g2_count: int = 34,
    g3_count: int = 212,
    sem_grupo_count: int = 27,
) -> str:
    """Gera um arquivo .xlsx sintético reproduzindo com fidelidade a planilha do Excel Online.

    Contém exatamente:
    - total de 282 linhas na aba DISTRIBUIÇÃO
    - 9 processos G1 (vagas femininas / nutrizes > 0)
    - 34 processos G2 (vagas masculinas em municípios PRONASCI)
    - 212 processos G3 (vagas masculinas nos demais municípios)
    - 27 processos SEM_GRUPO (vagas zeradas)
    - Abas de analistas, revisão, diligência e auxiliares.
    """
    assert g1_count + g2_count + g3_count + sem_grupo_count == total

    wb = openpyxl.Workbook()

    # 1. Aba DISTRIBUIÇÃO
    ws_dist = wb.active
    ws_dist.title = "DISTRIBUIÇÃO"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0C326F", end_color="0C326F", fill_type="solid")

    headers = [
        "Nº Processo SEI",
        "Data/Hora Protocolo",
        "CNPJ Proponente",
        "Razão Social",
        "Município",
        "UF",
        "Vagas Femininas",
        "Vagas Masculinas",
        "Vagas Mães Nutrizes",
        "Total Vagas Solicitadas",
        "Capacidade Instalada",
        "Analista Responsável",
        "Status da Análise",
    ]
    ws_dist.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws_dist.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill

    # Base date
    base_dt = datetime(2026, 1, 15, 9, 0, 0)

    # Municípios PRONASCI para os 34 do G2
    pronasci_cities = [
        ("Maceió", "AL", "2704302"),
        ("Manaus", "AM", "1302603"),
        ("Salvador", "BA", "2927408"),
        ("Fortaleza", "CE", "2304400"),
        ("Brasília", "DF", "5300108"),
        ("Goiânia", "GO", "5208707"),
        ("São Luís", "MA", "2111300"),
        ("Belo Horizonte", "MG", "3106200"),
        ("Belém", "PA", "1501402"),
        ("Recife", "PE", "2611606"),
        ("Curitiba", "PR", "4106902"),
        ("Rio de Janeiro", "RJ", "3304557"),
        ("Porto Alegre", "RS", "4314902"),
        ("São Paulo", "SP", "3550308"),
    ]

    other_cities = [
        ("Campinas", "SP", "3509502"),
        ("Ribeirão Preto", "SP", "3543402"),
        ("Santos", "SP", "3548500"),
        ("Niterói", "RJ", "3303302"),
        ("Petrópolis", "RJ", "3303906"),
        ("Uberlândia", "MG", "3170206"),
        ("Juiz de Fora", "MG", "3136702"),
        ("Londrina", "PR", "4113700"),
        ("Maringá", "PR", "4115200"),
        ("Joinville", "SC", "4209102"),
        ("Florianópolis", "SC", "4205407"),
        ("Caxias do Sul", "RS", "4305108"),
        ("Pelotas", "RS", "4314407"),
        ("Anápolis", "GO", "5201108"),
        ("Feira de Santana", "BA", "2910800"),
        ("Vitória da Conquista", "BA", "2933307"),
    ]

    analysts = ["ANA PAULA", "DANIEL"]

    row_idx = 1
    # G1: 9 processos
    for i in range(g1_count):
        sei = f"71000.{row_idx:06d}/2026-01"
        dt = base_dt + timedelta(minutes=row_idx * 15)
        cnpj = f"{row_idx:014d}"
        inst = f"Instituto de Apoio Social G1 - {i + 1}"
        muni, uf, _ = other_cities[i % len(other_cities)]
        fem = 10 + (i % 5)
        masc = 0
        nutrizes = 5 if i % 2 == 0 else 0
        tot = fem + nutrizes
        cap = tot + 10
        analyst = analysts[i % len(analysts)]
        ws_dist.append(
            [
                sei,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                cnpj,
                inst,
                muni,
                uf,
                fem,
                masc,
                nutrizes,
                tot,
                cap,
                analyst,
                "APTA" if i % 3 != 0 else "INAPTA",
            ]
        )
        row_idx += 1

    # G2: 34 processos (PRONASCI)
    for i in range(g2_count):
        sei = f"71000.{row_idx:06d}/2026-01"
        dt = base_dt + timedelta(minutes=row_idx * 15)
        cnpj = f"{row_idx:014d}"
        inst = f"Comunidade Terapêutica PRONASCI G2 - {i + 1}"
        muni, uf, _ = pronasci_cities[i % len(pronasci_cities)]
        fem = 0
        masc = 20 + (i % 10)
        nutrizes = 0
        tot = masc
        cap = tot + 15
        analyst = analysts[i % len(analysts)]
        ws_dist.append(
            [
                sei,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                cnpj,
                inst,
                muni,
                uf,
                fem,
                masc,
                nutrizes,
                tot,
                cap,
                analyst,
                "APTA" if i % 4 != 0 else "INAPTA",
            ]
        )
        row_idx += 1

    # G3: 212 processos (Demais municípios)
    for i in range(g3_count):
        sei = f"71000.{row_idx:06d}/2026-01"
        dt = base_dt + timedelta(minutes=row_idx * 15)
        cnpj = f"{row_idx:014d}"
        inst = f"Associação Comunitária G3 - {i + 1}"
        muni, uf, _ = other_cities[i % len(other_cities)]
        fem = 0
        masc = 15 + (i % 15)
        nutrizes = 0
        tot = masc
        cap = tot + 10
        analyst = analysts[i % len(analysts)]
        ws_dist.append(
            [
                sei,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                cnpj,
                inst,
                muni,
                uf,
                fem,
                masc,
                nutrizes,
                tot,
                cap,
                analyst,
                "APTA" if i % 5 != 0 else "INAPTA",
            ]
        )
        row_idx += 1

    # Sem grupo: 27 processos (vagas 0)
    for i in range(sem_grupo_count):
        sei = f"71000.{row_idx:06d}/2026-01"
        dt = base_dt + timedelta(minutes=row_idx * 15)
        cnpj = f"{row_idx:014d}"
        inst = f"Entidade Pendente Sem Vagas - {i + 1}"
        muni, uf, _ = other_cities[i % len(other_cities)]
        ws_dist.append(
            [
                sei,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                cnpj,
                inst,
                muni,
                uf,
                0,
                0,
                0,
                0,
                20,
                "",
                "EM_ANALISE",
            ]
        )
        row_idx += 1

    # 2. Aba AUXILIAR PRONASCI
    ws_pro = wb.create_sheet(title="AUX_PRONASCI")
    ws_pro.append(["Código IBGE", "Município", "UF", "Programa"])
    for m, u, c in pronasci_cities:
        ws_pro.append([c, m, u, "PRONASCI"])

    # 3. Aba de Analista: ANA PAULA
    ws_ana = wb.create_sheet(title="ANA PAULA")
    ws_ana.append(["Nº Processo SEI", "4.2-I", "4.2-V", "4.2-XVI", "Parecer Final", "Observações"])
    for r in range(2, 50):
        sei_val = ws_dist.cell(row=r, column=1).value
        ws_ana.append([sei_val, "ATENDE", "ATENDE", "ATENDE", "APTA", "Conforme"])

    # 4. Aba REVISÃO
    ws_rev = wb.create_sheet(title="REVISÃO")
    ws_rev.append(
        ["Nº Processo SEI", "Revisor", "Parecer Revisão", "Itens Divergentes", "Justificativa"]
    )
    ws_rev.append(
        ["71000.000001/2026-01", "DANIEL", "PRE_HABILITADO", "Nenhum", "Revisão confirmada"]
    )

    # 5. Aba DILIGÊNCIA
    ws_dil = wb.create_sheet(title="DILIGÊNCIA")
    ws_dil.append(["Nº Processo SEI", "Motivo", "Data Abertura", "Prazo", "Status"])
    ws_dil.append(["71000.000003/2026-01", "Esclarecer CND", "2026-02-01", "2026-02-15", "ABERTA"])

    wb.save(filepath)
    return filepath
