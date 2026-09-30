"""Write GitHub's summary from coverage.py and pytest output, never hardcoded numbers."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

path = Path('coverage.json')
if not path.exists():
    print('Relatorio de cobertura nao gerado. Consulte o log dos testes.')
    raise SystemExit(0)
data = json.loads(path.read_text())
t = data['totals']
print(f"## Cobertura real: {t['percent_covered']:.2f}%")
print('Minimo exigido: **80%**, incluindo branches. HTML navegavel no artefato desta execucao.\n')
print('| Arquivo | Linhas cobertas | Linhas faltantes | Cobertura |')
print('|---|---:|---:|---:|')
for name, file in data['files'].items():
    s = file['summary']
    print(f"| {name} | {s['covered_lines']} | {s['missing_lines']} | {s['percent_covered']:.2f}% |")
if Path('reports/junit.xml').exists():
    suite = ET.parse('reports/junit.xml').getroot()
    suites = list(suite.iter('testsuite'))
    print('\nTestes: ' + str(sum(int(s.get('tests', 0)) for s in suites)))
    print('Falhas/erros: ' + str(sum(int(s.get('failures', 0)) + int(s.get('errors', 0)) for s in suites)))
