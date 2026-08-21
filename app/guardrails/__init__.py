"""Guardrails — o que nunca pode sair na resposta.

  * código de CID, hipótese diagnóstica ou CPF completo;
  * qualquer informação sobre carteirinha diferente da que abriu a sessão.

O regulamento detalha o que é permitido em cada caso.
"""
import re

def mascarar_cpf(texto: str) -> str:
    """Mascara CPFs formatados ou numéricos no padrão estrito ***.123.456-**."""
    def _sub(m):
        nums = re.sub(r'\D', '', m.group(0))
        if len(nums) == 11:
            return f"***.{nums[3:6]}.{nums[6:9]}-**"
        return m.group(0)

    padrao = r'\b\d{3}[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{2}\b'
    return re.sub(padrao, _sub, texto)

def remover_cid(texto: str) -> str:
    """Remove códigos de CID-10 isolados (ex: F32.9) ou com prefixo, incluindo formatos sem ponto (ex: F321)."""
    padrao_cid = r'\b(?:CID\s*[-:]?\s*)?([A-Z]\d{2}(?:\.?\d{1,2})?)(?!\d)\b'
    return re.sub(padrao_cid, '[DIAGNOSTICO_OMITIDO]', texto)

def aplicar_guardrails(resposta: str) -> str:
    texto_filtrado = mascarar_cpf(resposta)
    texto_filtrado = remover_cid(texto_filtrado)
    return texto_filtrado