import argparse
import json
import os
import sys
from typing import Any

import fitz
from google import genai
from google.genai import types

MODEL_NAME = 'gemini-3-pro-preview'
SYSTEM_PROMPT = """
Você é um analista legislativo e especialista em comunicação cívica.
Sua tarefa é analisar um Projeto de Lei (PL) e extrair metadados semânticos.
Analise o texto completo para extrair resumo, justificativa e evidências (XAI).
"""

LEGISLATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'resumo': {'type': 'string'},
        'justificativa': {'type': 'string'},
        'evidencias': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'ponto_resumo': {'type': 'string'},
                    'citacao_original': {'type': 'string'},
                },
                'required': ['ponto_resumo', 'citacao_original'],
            },
        },
        'categorias': {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': [
                    'Saúde',
                    'Educação',
                    'Transporte',
                    'Meio Ambiente',
                    'Urbanismo',
                    'Assistência Social',
                    'Tecnologia',
                    'Segurança',
                    'Finanças',
                ],
            },
        },
    },
    'required': ['resumo', 'justificativa', 'evidencias', 'categorias'],
}


class LegislationParser:
    def __init__(self, api_key: str | None = None):
        """Initializes the Gemini client. Expects API key via arg or env var."""
        key = api_key or os.environ.get('GEMINI_API_KEY')
        if not key:
            raise ValueError(
                'GEMINI_API_KEY must be set in environment or passed as argument.'
            )
        self.client = genai.Client(api_key=key)

    def _extract_text(self, pdf_path: str) -> str:
        """Extracts raw text from PDF using PyMuPDF."""
        with fitz.open(pdf_path) as doc:
            return chr(12).join([page.get_text() for page in doc]).strip()

    def parse(self, pdf_path: str) -> dict[str, Any]:
        """Orchestrates extraction and semantic analysis."""
        text = self._extract_text(pdf_path)

        response = self.client.models.generate_content(
            model=MODEL_NAME,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type='application/json',
                response_schema=LEGISLATION_SCHEMA,
            ),
        )

        # Return parsed object or fallback to raw text parsing if wrapper fails
        return response.parsed if response.parsed else json.loads(response.text)


def main():
    parser = argparse.ArgumentParser(
        description='Extract semantic metadata from legislation PDFs.'
    )
    parser.add_argument('filepath', type=str, help='Path to the PDF file')
    parser.add_argument(
        '--out', type=str, default='analysis.json', help='Output JSON path'
    )
    args = parser.parse_args()

    try:
        analyzer = LegislationParser()
        print(f'Analyzing {args.filepath}...')
        result = analyzer.parse(args.filepath)

        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f'Success. Data saved to {args.out}')

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
