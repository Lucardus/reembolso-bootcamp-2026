"""Correção da prova: conduz as conversas e decide se passam.

A avaliação é por turno, e não por média.

    1. porta de entrada  respostas repetidas literalmente -> conversa vale zero
    2. turno a turno     cada turno é atendido ou não
    3. desfecho          decisão, valor e dispositivos do último turno

A conversa só passa se todos os turnos passarem e o desfecho bater. A nota é a
proporção de conversas aprovadas — três conversas, então 0, 33, 67 ou 100.

Quem entrega uma tabela de templates indexada por estado não chega ao passo 2.
"""

from .avaliar import Veredito, avaliar, salvar  # noqa: F401
from .checagens import ProblemaObjetivo, checar_transcricao, eh_agente  # noqa: F401
from .dispositivos import existentes  # noqa: F401
from .turno import NotaTurno, avaliar_turno  # noqa: F401
