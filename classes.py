from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

# --- Classe para a aba "Documentos" ---
@dataclass
class DocumentoAnexo:
    """
    Representa um único link na aba 'Documentos' (ex: Projeto, Lei, Parecer).
    """
    titulo: str          # Ex: "Projeto" ou "Lei nº 14.244/25"
    url_documento: str   # O link (href) para baixar o PDF/DOCX

# --- Classe para a aba "Votações" ---
@dataclass
class Votacao:
    """
    Representa uma linha na aba 'Votações'.
    """
    data: date
    titulo: str          # Ex: "PLL 135/25 - PROC. 00362/25"
    resultado: str       # Ex: "Aprovado"
    url_detalhes: str    # O link (href) do botão "Ver Detalhes"
    
    # O scraper pode ou não conseguir pegar isso da tela principal
    votos_sim: Optional[int] = None
    votos_nao: Optional[int] = None
    votos_abstencao: Optional[int] = None

# --- Classe Principal (O Projeto de Lei) ---
@dataclass
class ProjetoLei:
    """
    Estrutura principal que armazena todos os dados raspados (scraped)
    de um único Processo/Projeto de Lei.
    """
    # --- Metadados do Scraper ---
    url_processo: str  # A URL da página principal do processo (a do print)

    # --- Aba "Identificação" ---
    processo_id: str           # Ex: "00362/25"
    pl_id: str                 # Ex: "PLL 135/25"
    descricao: str             # Ex: "DECLARA A DESCIDA DA BORGES..."
    data_abertura: date
    autores: List[str]         # Uma lista, pois pode haver mais de um
    situacao: str              # Ex: "ARQUIVADO"
    situacao_plenaria: str     # Ex: "APROVADO"
    localizacao_atual: str     # Ex: "ARQ - SETOR DE ARQUIVO"
    ultima_tramitacao_data: date

    # --- Abas Anexadas (Listas das classes acima) ---
    documentos: List[DocumentoAnexo] = field(default_factory=list)
    votacoes: List[Votacao] = field(default_factory=list)
    
    # --- Texto Original (Etapa Central do MVP) ---
    # Este campo será preenchido pelo scraper após baixar
    # e ler o PDF/DOCX da lista de 'documentos'.
    texto_original: Optional[str] = None