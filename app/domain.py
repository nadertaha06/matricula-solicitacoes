TRANSICOES = {
    'SOLICITADA': {'DEFERIDA', 'INDEFERIDA', 'EM_ESPERA', 'CANCELADA'},
    'EM_ESPERA': {'DEFERIDA', 'INDEFERIDA', 'CANCELADA'},
    'DEFERIDA': {'CANCELADA'},
    'INDEFERIDA': set(),
    'CANCELADA': set(),
}


def validar_transicao(origem, destino):
    if destino not in TRANSICOES.get(origem, set()):
        raise ValueError(f'Transicao invalida: {origem} -> {destino}')
