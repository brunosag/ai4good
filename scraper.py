import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

def extrair_html_de_sjr(resposta_texto):
    """
    Tenta extrair HTML embutido em respostas JavaScript (SJR).
    Muitas vezes o servidor retorna algo como: $('#resultado').html('<table>...</table>');
    """

    padrao = r".html\(['\"](.*?)['\"]\)"  # Padrão genérico para encontrar strings HTML longas dentro de código JS
    match = re.search(padrao, resposta_texto, re.DOTALL)
    if match:
        html_escapado = match.group(1)
        return html_escapado.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
    return resposta_texto

# --- FLUXO PRINCIPAL ---
def executar_scraper_sjr():
    base_url = "https://www.camarapoa.rs.gov.br"
    url_busca = f"{base_url}/processos?utf8=✓&by_tipo=PLL&commit=Pesquisar" # Filtro PLL aplicado

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; VozCivicaBot/0.1)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        print("🔵 1. Obtendo Tokens iniciais...")
        #  GET na raiz ou página de busca para pegar os cookies
        resp_inicial = client.get(f"{base_url}/processos", headers=headers)
        
        # httpx mantém os cookies automaticamente na sessão 'client'
        csrf_token = None
        soup_inicial = BeautifulSoup(resp_inicial.text, 'html.parser')
        meta_csrf = soup_inicial.find('meta', attrs={'name': 'csrf-token'})
        if meta_csrf:
            csrf_token = meta_csrf['content']
            headers['X-CSRF-Token'] = csrf_token
            print("✅ Tokens obtidos e configurados na sessão.")
        else:
            print("⚠️ Aviso: X-CSRF-Token não encontrado (pode não ser necessário para GET, mas bom ter).")

        print(f"🔵 2. Buscando projetos PLL: {url_busca}")
        resp_busca = client.get(url_busca, headers=headers)

        conteudo_html = ""
        if "text/javascript" in resp_busca.headers.get("content-type", ""):
            print("Detectada resposta SJR (JavaScript). Extraindo HTML...")
            conteudo_html = extrair_html_de_sjr(resp_busca.text)
        else:
            print("Detectada resposta HTML padrão.")
            conteudo_html = resp_busca.text

        print("🔵 3. Extraindo links de processos...")
        soup_busca = BeautifulSoup(conteudo_html, 'html.parser')
        
        # encontrar links que correspondam ao padrão /processos/NUMERO
        # pode precisar de ajuste fino dependendo do HTML atual da Câmara
        links_processos = []
        for link in soup_busca.find_all('a', href=True):
            href = link['href']
            # Regex para garantir que é um link de processo e não outra coisa
            if re.search(r"/processos/\d+$", href):
                url_completa = urllib.parse.urljoin(base_url, href)
                if url_completa not in links_processos:
                    links_processos.append(url_completa)

        print(f"\n✅ Sucesso! Encontrados {len(links_processos)} projetos na primeira página.")
        print("Exemplos de links encontrados:")
        for i, link in enumerate(links_processos[:5]):  # mostra top 5
            print(f" [{i+1}] {link}")

        return links_processos

if __name__ == "__main__":
    links = executar_scraper_sjr()
