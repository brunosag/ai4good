from dataclasses import dataclass, field
from datetime import date


@dataclass
class DocumentoAnexo:
    titulo: str
    url: str


@dataclass
class Vereador:
    slug: str  # Ex: 'grazi-oliveira'
    nome: str  # Ex: 'Grazi Oliveira'
    partido: str  # Ex: 'PSOL'


@dataclass
class ProjetoLei:
    id_url: int  # Ex: 140595
    id_processo: str  # Ex: '00005/25'
    id_pl: str  # Ex: 'PLL 001/25'
    titulo: str  # Ex: 'Institui auxílio financeiro para mães...'
    autores: list[Vereador]
    data_abertura: date
    data_ultima_tramitacao: date
    situacao: str  # Ex: 'PARA PARECER'
    situacao_plenaria: str  # Ex: 'EM TRAMITACAO'
    localizacao_atual: str  # Ex: 'ARQ - SETOR DE ARQUIVO'
    documentos: list[DocumentoAnexo] = field(default_factory=list)
    texto_original: str | None = None


@dataclass
class SimplificacaoPL:
    id_url_pl: int  # Ex: 140595
    titulo: str  # Ex: 'Criação de auxílio financeiro para mães...'
    resumo: str  # Ex: ''
    justificativa: str  # Ex: ''
