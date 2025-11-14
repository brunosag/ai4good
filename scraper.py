import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse
import os
import pathlib  

base_url = "https://www.camarapoa.rs.gov.br"
DOWNLOAD_DIR = pathlib.Path("PROJETOS_PDF")
DOWNLOAD_DIR.mkdir(exist_ok=True) 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VozCivicaBot/0.1; +https://github.com/mdfguerra)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}
AJAX_HEADERS = HEADERS.copy()
AJAX_HEADERS.update({
    "Accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
})

def extrair_html_de_sjr(resposta_texto):
    """
    Tenta extrair HTML embutido em respostas JavaScript (SJR).
    Ex: $('#id').html('...html aqui...');
    """
    padrao = r"\.html\(['\"](.*?)['\"]\)"
    match = re.search(padrao, resposta_texto, re.DOTALL)
    if match:
        html_escapado = match.group(1)
        return html_escapado.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
    return resposta_texto

def sanitizar_nome_arquivo(nome):
    """Limpa o nome de um arquivo para evitar caracteres inválidos."""
    nome = re.sub(r'[\\/*?:"<>|]', "", nome)
    return nome.strip() or "documento_sem_nome"


# --- LÓGICA DAS TAREFAS ---

def executar_busca_projetos(client):
    """ Executa a busca inicial e retorna os links dos projetos."""
    url_busca = f"{base_url}/processos?utf8=✓&by_tipo=PLL&commit=Pesquisar" # Filtro PLL
    print(f"🔵  Buscando projetos PLL: {url_busca}")

    try:
        resp_busca = client.get(url_busca, headers=HEADERS)
        
        conteudo_html = resp_busca.text
        if "text/javascript" in resp_busca.headers.get("content-type", ""):
            print("   Detectada resposta SJR (JavaScript). Extraindo HTML...")
            conteudo_html = extrair_html_de_sjr(resp_busca.text)
        else:
            print("   Detectada resposta HTML padrão.")

        print("   Extraindo links de processos...")
        soup_busca = BeautifulSoup(conteudo_html, 'html.parser')
        
        links_processos = []
        for link in soup_busca.find_all('a', href=re.compile(r"/processos/\d+$")):
            if "PLL" in link.get_text(strip=True).upper():
                url_completa = urllib.parse.urljoin(base_url, link['href'])
                if url_completa not in links_processos:
                    links_processos.append(url_completa)
        
        print(f"✅  Sucesso! Encontrados {len(links_processos)} projetos PLL na primeira página.")
        return links_processos

    except httpx.RequestError as e:
        print(f"❌  Erro ao buscar projetos: {e}")
        return []

def processar_projeto(client, url_projeto):
    """ Processa um link de projeto individual (LÓGICA CORRIGIDA)"""
    print(f"\n---   Processando: {url_projeto} ---")
    
    try:
        # 1. Obter página principal 
        resp_main = client.get(url_projeto, headers=HEADERS)
        resp_main.raise_for_status()
        soup_main = BeautifulSoup(resp_main.text, 'html.parser')
        
        # 2. Obter dados de "Identificação"
        print("   Extraindo 'Identificação'...")
        metadata = {'url_projeto': url_projeto}
        id_container = soup_main.find('div', attrs={'data-tab': 'dados'})
        
        if id_container:
            dl_dados = id_container.find('dl', class_='dados')
            if dl_dados:
                for dt in dl_dados.find_all('dt'):
                    label = dt.get_text(strip=True).replace(":", "")
                    dd = dt.find_next_sibling('dd')
                    if label and dd:
                        value = dd.get_text(strip=True)
                        metadata[label] = value
                        print(f"    - {label}: {value[:70]}...") 
            else:
                print("    - AVISO: Div 'dados' encontrada, mas <dl class='dados'> não.")
        else:
            print("    - AVISO: Não foi possível encontrar a <div> 'data-tab=dados'.")

        
        # 3. Obter dados de "Votações" e "Tramitações" 
        if soup_main.find('div', attrs={'data-tab': 'votacoes'}):
            print("   Aba 'Votações' encontrada no HTML.")
        else:
            print("   AVISO: Aba 'Votações' não encontrada.")
            
        if soup_main.find('div', attrs={'data-tab': 'tramitacoes'}):
            print("   Aba 'Tramitações' encontrada no HTML.")
        else:
            print("   AVISO: Aba 'Tramitações' não encontrada.")


        print(f"   Obtendo e baixando 'Documentos'...")
        
        docs_container = soup_main.find('div', attrs={'data-tab': 'documentos'})
        
        if docs_container:
            project_id = url_projeto.split('/')[-1]
            save_dir = DOWNLOAD_DIR / project_id
            save_dir.mkdir(exist_ok=True)
            
            pdf_links_found = 0
            for link in docs_container.find_all('a', href=re.compile(r'\.pdf', re.IGNORECASE)):
                pdf_url = urllib.parse.urljoin(base_url, link['href'])
                link_text_span = link.find('span')
                link_text = link_text_span.get_text(strip=True) if link_text_span else "documento_pdf"
                
                pdf_links_found += 1
                
                # Identificar Projeto
                if "projeto" in link_text.lower():
                    print(f"    - 🟪 IDENTIFICADO 'Projeto': {link_text}")
                
                print(f"    - Baixando: {link_text}")
                pdf_resp = client.get(pdf_url, headers=HEADERS)
                pdf_resp.raise_for_status()
                
                filename = sanitizar_nome_arquivo(link_text)
                if not filename.lower().endswith('.pdf'):
                    filename += ".pdf"
                
                save_path = save_dir / filename
                save_path.write_bytes(pdf_resp.content)
                print(f"    - ✅ Salvo em: {save_path}")
            
            if pdf_links_found == 0:
                print("    - AVISO: Aba 'Documentos' encontrada, mas nenhum link .pdf foi encontrado dentro dela.")
        else:
            print("   AVISO: Não foi possível encontrar a <div> 'data-tab=documentos'.")

        print(f"--- ✅  Processamento de {url_projeto} concluído ---")

    except Exception as e:
        print(f"❌  Erro ao processar {url_projeto}: {e}")


if __name__ == "__main__":
    
    # 'Client' para manter a sessão entre as requisições
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        
        # 1. Obter tokens iniciais 
        print("🔵 (T1) Obtendo tokens/sessão iniciais...")
        resp_inicial = client.get(f"{base_url}/processos", headers=HEADERS)
        soup_inicial = BeautifulSoup(resp_inicial.text, 'html.parser')
        
        # Configura o CSRF-Token para requisições futuras 
        meta_csrf = soup_inicial.find('meta', attrs={'name': 'csrf-token'})
        if meta_csrf:
            AJAX_HEADERS['X-CSRF-Token'] = meta_csrf['content']
            HEADERS['X-CSRF-Token'] = meta_csrf['content']
            print("✅ (T1) Sessão e CSRF-Token configurados.")
        else:
            print("⚠️ (T1) Aviso: X-CSRF-Token não encontrado.")

        # 2. Busca de 2 projetos
        links_de_projetos = executar_busca_projetos(client)

        # 3. Processamento de 3 projetos
        if links_de_projetos:
            links_para_processar = links_de_projetos[:3] 
            print(f"\n🔵  Iniciando processamento de {len(links_para_processar)} projetos...")
            
            for link_proj in links_para_processar:
                processar_projeto(client, link_proj)
        else:
            print("❌  Nenhuma link de projeto encontrado. Encerrando.")
